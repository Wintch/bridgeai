"""Pure decisions of the waker's "updates reach warm stacks" package. Stdlib only, no docker, no files, no clock of its own: every
function takes the time and the facts it needs, so ops/wake/updates_selftest.py tests them offline. waker.py gathers the facts and
applies the answer; nothing in here stops, recreates or sends anything.

The problem: ops/redeploy_router.sh never recreates a stack that is awake (recreate_hermes.sh refuses a running container, exit 3),
and a warm ("siempreviva") stack may never sleep, so it would never get a new image. The script now leaves a note,
ops/wake/<name>.update_pending (JSON: the new image id and an epoch), for every stack it skipped, and the waker applies it:

  * the stack must run an image DIFFERENT from the pending one, be idle for update_idle_seconds (nobody used it, nothing happened) and
    not busy; no boot may be in progress anywhere, no other update running, and memory must allow one more boot;
  * a Telegram stack gets one short note (es/ru/en, like the inactivity note; only inside the person's day hours, never at night; once
    per pending image; update_notice false turns it off), a web-only stack none;
  * then update_grace_seconds (300) during which ANY use or activity cancels the plan until the next idle window (the person's turn,
    a UI request, a cron, a busy marker);
  * then the brain goes through the same re-checked stop the daily refresh uses (sleep_brain(recheck=...) under the wake lock) and
    ops/recreate_hermes.sh <name> runs as a subprocess with a timeout. PASS clears the note; FAIL keeps it, alerts the operator once and
    retries at most once a day. The container the script booted is stopped by the idle rule after one idle period.

A canary (ops/pipeline.sh canary <tar> <stack>) pins ONE stack to a test build: while ops/wake/<name>.canary exists, no update to latest is
planned, announced or applied for that stack (update_tick returns at once, and logs once that it is pinned), and ops/recreate_hermes.sh puts the
canary's compose override on every recreate of it, so a recreate by any other route (the deploy, a Telegram token change) keeps the pinned image.
The waker itself only ever `docker start`s the existing container, which keeps the image it was created with.
"""
import json
import math
import re

DEFAULTS = {
    "update_idle_seconds": 600,       # idle this long (nobody used it, nothing happened) before an update is planned
    "update_grace_seconds": 300,      # after the plan (and the note) any use postpones it to the next idle window
    "update_notice": True,            # tell a Telegram person ("I restart in a few minutes")
    "update_retry_seconds": 86400,    # after a FAILED recreate, not before this long
    "update_timeout_seconds": 1500,   # a recreate that takes longer is killed (it waits up to 5 min for /health and more for the config)
    # "fast_rolling": true on a stack (stacks.json, per stack, off by default): the update starts after a short quiet period, also on an awake
    # stack that is not kept warm, and the note says when the stack is back
    "fast_rolling_idle_seconds": 120,
    "fast_rolling_grace_seconds": 20,
    "update_eta_default_seconds": 240,   # until a first update of the stack has been timed
}
PENDING_MAX_BYTES = 4096
CANARY_IMAGE_RE = re.compile(r"^aibridge-hermes-agent:build-[A-Za-z0-9._-]{1,64}$")
IMAGE_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{12,64}$")


# ---- the pending note
def parse_pending(raw):
    """{"image": "sha256:...", "ts": epoch} from the file's text, or None when it is not a usable note (junk, no image id)."""
    try:
        d = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("image"), str) or not IMAGE_RE.match(d["image"]):
        return None
    ts = d.get("ts")
    ts = float(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) and math.isfinite(ts) else 0.0
    return {"image": d["image"], "ts": ts}


# ---- the canary marker
def parse_canary(raw):
    """What ops/wake/<name>.canary says (written by `ops/pipeline.sh canary`): {"image": "aibridge-hermes-agent:build-<rev>", "rev", "ts",
    "backup"} with a field None when it is missing or not usable. The MARKER'S EXISTENCE is what pins a stack, not its content: a file that
    cannot be read still pins (the safe side: no update is applied over a canary), so this only feeds the log line."""
    try:
        d = json.loads(raw)
    except (TypeError, ValueError):
        d = None
    if not isinstance(d, dict):
        d = {}
    image = d.get("image")
    image = image if isinstance(image, str) and CANARY_IMAGE_RE.match(image) else None
    ts = d.get("ts")
    ts = float(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) and math.isfinite(ts) else None
    rev = d.get("rev")
    return {"image": image, "rev": rev if isinstance(rev, str) and re.match(r"^[A-Za-z0-9._-]{1,64}$", rev) else None, "ts": ts,
            "backup": d.get("backup") if isinstance(d.get("backup"), str) else None}


def _bare(image):
    return image[7:] if image.startswith("sha256:") else image


def same_image(a, b):
    """Two image ids name the same image (with or without the sha256: prefix, one may be the short form of the other, 12 digits at least)."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    a, b = _bare(a.strip()), _bare(b.strip())
    return len(a) >= 12 and len(b) >= 12 and (a.startswith(b) or b.startswith(a))


def pending_needed(pending, container_image):
    """Does the container still run something else than the pending image? False when there is no note or the container's image
    cannot be read (nothing is done on a guess)."""
    return bool(pending) and bool(container_image) and not same_image(pending["image"], container_image)


def memory_ok(avail_mb, est_mb, reserve_mb, brain_up):
    """Room for one more boot: the same rule as the RAM guard (free minus the stack's footprint stays above the reserve). A running brain's
    own memory comes back when it is stopped, so for it the free memory itself must stay above the reserve."""
    return (avail_mb if brain_up else avail_mb - est_mb) >= reserve_mb


# ---- when
def update_step(now, needed, retry_at, blocked, grace, human, activity, idle_s, grace_s, busy_fn):
    """("none"|"start"|"wait"|"reset"|"apply", why): the next move for a stack with an update pending.
    grace: None before the plan, else {"t0", "human0", "act0"} (the start of the grace period and the person's/the waker's newest times
    then). human/activity: the person's newest use (None when unknown) and the waker's own activity clock now.
      none   nothing to do (not needed, a failed attempt not yet due, blocked, not idle yet, busy)
      start  idle and quiet: begin the grace period (the caller sends the note)
      wait   in the grace period (or blocked for a moment): not yet
      reset  somebody used the stack or something started since the plan: drop it, the next idle window starts over
      apply  the grace period is over and everything is still quiet: stop (when up) and recreate
    The expensive fact (busy_fn) is asked last."""
    if not needed:
        return "none", "not needed"
    if now < retry_at:
        return "none", "retry later"
    h, a = human or 0, activity or 0
    if grace is None:
        if blocked:
            return "none", blocked if isinstance(blocked, str) else "blocked"
        if now - max(h, a) < idle_s:
            return "none", "not idle yet"
        if busy_fn():
            return "none", "busy"
        return "start", ""
    if h > grace["human0"] or a > grace["act0"]:
        return "reset", "used again"
    if busy_fn():
        return "reset", "busy"
    if blocked:
        return "wait", blocked if isinstance(blocked, str) else "blocked"
    if now - grace["t0"] < grace_s:
        return "wait", "grace"
    return "apply", ""


def timing(fast, get):
    """(idle_s, grace_s) for a stack's update: the global settings, or the short fast-rolling ones for a stack that opted in. `get` is the
    waker's update_cfg."""
    if fast:
        return float(get("fast_rolling_idle_seconds")), float(get("fast_rolling_grace_seconds"))
    return float(get("update_idle_seconds")), float(get("update_grace_seconds"))


def eta_minutes(last_s, default_s=240):
    """Whole minutes to tell the person: the last timed update of this stack (stop to ready), else the default; at least 2, at most 15,
    always rounded up (a promise of 'about 3 minutes' that takes 4 is worse than 'about 4')."""
    try:
        x = float(last_s)
        x = x if math.isfinite(x) and x > 0 else float(default_s)
    except (TypeError, ValueError):
        x = float(default_s)
    return max(2, min(15, int(math.ceil(x / 60.0))))


def notice_wanted(enabled, has_bot, in_day, zone_known, already_noticed, fast_recent=False):
    """Send the "I restart in a few minutes" note? Telegram stacks only, inside the person's day hours and with a known zone (it must
    never reach anybody at night; then the update simply goes ahead), and once per pending image. A fast-rolling stack whose person was
    active in the last half hour needs neither: they are plainly awake, and a new stack has no known zone yet."""
    if fast_recent:
        return bool(enabled and has_bot and not already_noticed)
    return bool(enabled and has_bot and in_day and zone_known and not already_noticed)


def failure_decision(rc, timed_out):
    """What a recreate result means: ("ok", 0), ("busy", seconds) (the container was running after all: not a failure, try again soon) or
    ("fail", 0) (keep the pending note, alert once, retry at most once a day)."""
    if timed_out:
        return "fail", 0
    if rc == 0:
        return "ok", 0
    if rc == 3:
        return "busy", 600
    return "fail", 0


# ---- the note to the person
NOTICE = {
    "es": "🔄 Hay una actualización. Me reinicio en unos minutos para aplicarla; tus conversaciones y tu memoria quedan igual. "
          "Si me estás usando, lo dejo para más tarde.",
    "ru": "🔄 Есть обновление. Через несколько минут я перезапущусь, чтобы применить его; ваши разговоры и память останутся прежними. "
          "Если я вам нужен, отложу на потом.",
    "en": "🔄 There is an update. I restart in a few minutes to apply it; your conversations and your memory stay the same. "
          "If you are using me, I will leave it for later.",
}


NOTICE_FAST = {
    "es": "🔄 Hay una mejora. Me reinicio ahora para aplicarla y vuelvo a estar disponible en unos {n} min; tus conversaciones y tu memoria quedan igual.",
    "ru": "🔄 Есть улучшение. Перезапускаюсь сейчас, чтобы применить его, и снова буду доступен примерно через {n} мин; ваши разговоры и память останутся прежними.",
    "en": "🔄 There is an improvement. I restart now to apply it and will be available again in about {n} min; your conversations and your memory stay the same.",
}


def notice_text(lang, minutes=None):
    """The note. With `minutes` (fast rolling) it says when the stack is back; without, the older "in a few minutes" text."""
    if minutes:
        return NOTICE_FAST.get(lang, NOTICE_FAST["es"]).format(n=int(minutes))
    return NOTICE.get(lang, NOTICE["es"])
