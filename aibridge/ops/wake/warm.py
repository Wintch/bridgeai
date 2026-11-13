"""Pure decisions of the waker's warm ("siempreviva") package. Stdlib only, no docker, no files, no clock of its own: every
function takes the time and the facts it needs, so ops/wake/warm_selftest.py tests them offline. waker.py gathers the facts
(docker, the stack's workdir, MemAvailable) and applies the answer; nothing in here stops, starts or sends anything.

The package, as the waker uses it:
  * a person's last interaction ("last_human"): the newest of the waker's own human wake times (a Telegram message that woke the
    stack, a web navigation or send) and the epoch the router writes to /workdir/.last_human on every real user turn of an
    awake stack. Crons, tasks, night jobs and hooks are not human.
  * a stack with "warm": true whose person used it in the last warm_hours is NOT stopped by the idle rule (brain, and the web
    tier too when the person used the web). It is still stopped by /dormir, the critical-memory watchdog, the daily refresh and
    eviction. At most warm_max stacks are kept, and keeping them must leave reserve_mb + cache_floor_mb of memory free.
  * eviction order: idle non-warm stacks (least recently used first), then warm stacks by oldest last_human; never a busy one and
    never a warm one whose person was active within evict_min_idle_seconds.
  * a warm stack up for more than 20 h is stopped once a day at its quiet hour (and when the brain's memory grows past
    refresh_rss_mb), if nobody used it for 30 minutes and nothing is busy: the next message wakes it as usual.
  * one proactive "we have not talked for a while" note per idle stretch, in the person's day hours (router.py's own reactive
    question stays quiet when this one was sent first, through /workdir/.idle_notice).
"""
import math
import time

DEFAULTS = {
    "warm_hours": 24,             # a warm stack stays up this long after the person's last use
    "warm_max": 3,                # most warm-kept stacks at once
    "cache_floor_mb": 2000,       # free memory kept for the page cache on top of reserve_mb while stacks are kept warm
    "notice_after_hours": 6,      # the inactivity note starts this long after the last use
    "day_hours": "09-21",         # local hours [from, to) in which a note may be sent
    "refresh_hour": 5,            # local hour of the daily refresh
    "refresh_rss_mb": 1500,       # a brain above this is refreshed (when idle), 0 turns it off
    "refresh_idle_minutes": 30,   # nobody used the stack and nothing ran for this long
    "refresh_min_uptime_hours": 20,
}
FUTURE_SKEW_S = 300               # a stamp this far ahead of the clock is not believed (the agent can write the file)


# ---- time
def clamp_epoch(value, now):
    """A usable epoch: a positive finite number not (much) in the future; a stamp a few seconds ahead counts as now. None otherwise."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or v <= 0 or v > now + FUTURE_SKEW_S:
        return None
    return min(v, now)


def merge_human(own, from_file, now):
    """last_human: the newest valid of the waker's own human wake time and the router's file stamp, None when neither is."""
    vals = [v for v in (clamp_epoch(own, now), clamp_epoch(from_file, now)) if v is not None]
    return max(vals) if vals else None


def parse_hours(spec, default=(9, 21)):
    """"09-21" -> (9, 21): local hours [from, to). A range may wrap midnight ("22-06"). Anything unusable gives `default`."""
    try:
        a, b = str(spec).split("-")
        a, b = int(a), int(b)
    except (TypeError, ValueError):
        return default
    if not (0 <= a <= 24 and 0 <= b <= 24) or a == b:
        return default
    return a % 24, b % 24 if b != 24 else 24


def local_parts(now, offset):
    """(local hour, local date "YYYY-MM-DD") of epoch `now` in a zone `offset` seconds from UTC."""
    t = time.gmtime(now + offset)
    return t.tm_hour, time.strftime("%Y-%m-%d", t)


def in_day_hours(now, offset, spec):
    hour = local_parts(now, offset)[0]
    a, b = parse_hours(spec)
    return a <= hour < b if a < b else (hour >= a or hour < b)


# ---- who is kept warm
def warm_candidate(eligible, brain_up, last_human, started, cleared, now, warm_hours):
    """Is this stack warm right now (before the memory limits)? It must be eligible ("warm": true), its brain up, and its person
    must have used it DURING THIS run of the container (a brain a cron woke is not warm: nobody is there), after any /dormir
    (`cleared` = when it was last put to sleep on request), and less than warm_hours ago."""
    if not (eligible and brain_up) or last_human is None:
        return False
    if started is None or not math.isfinite(started) or last_human < started - 1:
        return False
    if cleared and last_human <= cleared:
        return False
    age = now - last_human
    return 0 <= age < warm_hours * 3600


def warm_plan(cands, avail_mb, need_mb, warm_max):
    """Which warm candidates stay warm. cands: [{"name", "last_human", "est_mb"}]. Returns (kept, demoted) as name lists; kept is most
    recently used first. Demoted ones become normal idle stacks (the idle rule stops them): the oldest go first when there are
    more than warm_max, and then while the free memory (plus what the demoted ones will free, est_mb each) is below need_mb
    (= reserve_mb + cache_floor_mb)."""
    order = sorted(cands, key=lambda c: (-(c["last_human"] or 0), c["name"]))
    kept, demoted = order[:max(0, int(warm_max))], order[max(0, int(warm_max)):]
    freed = sum(c.get("est_mb", 0) for c in demoted)
    while kept and avail_mb + freed < need_mb:
        c = kept.pop()
        demoted.append(c)
        freed += c.get("est_mb", 0)
    return [c["name"] for c in kept], [c["name"] for c in demoted]


def web_kept(brain_kept, web_ts, now, warm_hours):
    """The web tier of a warm stack stays up only when the person used the web in the warm period."""
    t = clamp_epoch(web_ts, now)
    return bool(brain_kept) and t is not None and now - t < warm_hours * 3600


# ---- eviction
def evict_order(cands, now, min_idle):
    """Names in the order the RAM guard may stop them. cands: [{"name", "busy", "warm", "last_activity", "last_human"}].
    1. idle non-warm stacks, least recently active first; 2. warm stacks by oldest last_human. A busy stack is never listed, nor
    one active within min_idle seconds, nor any stack (warm or not) whose person was active within min_idle seconds."""
    plain, warm = [], []
    for c in cands:
        if c.get("busy") or now - c["last_activity"] <= min_idle:
            continue
        if now - (c.get("last_human") or 0) <= min_idle:   # a person's turn on an awake stack moves last_human before any activity clock
            continue
        if c.get("warm"):
            warm.append(c)
        else:
            plain.append(c)
    plain.sort(key=lambda c: (c["last_activity"], c["name"]))
    warm.sort(key=lambda c: (c.get("last_human") or 0, c["name"]))
    return [c["name"] for c in plain + warm]


# ---- daily refresh
def refresh_decision(now, offset, hour, done_day, human_age_s, activity_age_s, uptime_fn, busy_fn, rss_fn, rss_limit_mb,
                     min_uptime_h=20, min_idle_s=1800):
    """None, "daily" or "rss": should this warm stack be put to sleep now to start fresh? Expensive facts come as functions and
    are asked only when the cheap ones allow: idle for min_idle_s (nobody used it AND nothing happened), then either the daily window
    (local hour == `hour`, not done today, up more than min_uptime_h) or a brain above rss_limit_mb; busy_fn() last."""
    if human_age_s < min_idle_s or activity_age_s < min_idle_s:
        return None
    reason = None
    h, today = local_parts(now, offset)
    if h == hour and done_day != today and uptime_fn() > min_uptime_h * 3600:
        reason = "daily"
    elif rss_limit_mb:
        rss = rss_fn()
        if rss is not None and rss > rss_limit_mb:
            reason = "rss"
    if reason is None or busy_fn():
        return None
    return reason


def stop_still_ok(human_before, activity_before, human_now, activity_now, booting=False, stopping=False):
    """The re-check right before an automatic stop (a refresh or a demotion): False when a person (or any activity) showed up since
    the decision was taken. The decision needs several docker calls; a message that arrives meanwhile must never meet a `docker stop`."""
    if booting or stopping:
        return False
    return (human_now or 0) <= (human_before or 0) and (activity_now or 0) <= (activity_before or 0)


# ---- the inactivity note
NOTICE = {
    "es": "🕓 Hace {h} h que no hablamos. Si lo próximo es otro tema, /new arranca limpio, gasta menos y toma las últimas mejoras. "
          "Si por ahora no me vas a usar, /dormir me apaga y libera recursos; cuando escribas me despierto solo.",
    "ru": "🕓 Прошло {h} ч с нашего последнего разговора. Если дальше будет другая тема, /new начнёт с чистого листа: это дешевле, "
          "и подхватятся последние улучшения. Если пока я не нужен, /dormir выключит меня и освободит ресурсы; "
          "когда напишете, я проснусь сам.",
    "en": "🕓 It has been {h} h since we last talked. If what comes next is another topic, /new starts clean, costs less and picks up "
          "the latest improvements. If you will not need me for now, /dormir shuts me down and frees resources; when you write, "
          "I wake up on my own.",
}


def notice_text(lang, hours):
    return NOTICE.get(lang, NOTICE["es"]).format(h=int(round(hours)))


def notice_decision(now, last_human, notice_ts, offset, day_hours, after_h, warm_h):
    """Send the inactivity note now? (The caller has already checked: warm stack kept up, brain up, not busy.) Only between after_h
    and warm_h hours after the last use, inside the person's day hours, and once per idle stretch: a note sent after the last use
    covers the stretch (a new message moves last_human past it and starts a new one)."""
    if last_human is None:
        return False
    age = now - last_human
    if not (after_h * 3600 <= age < warm_h * 3600):
        return False
    if notice_ts is not None and notice_ts > last_human:
        return False
    return in_day_hours(now, offset, day_hours)
