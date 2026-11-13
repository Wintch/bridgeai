#!/usr/bin/env python3
"""Offline test of the waker's "updates reach warm stacks" package (no docker, no server, no network): the pure decisions of updates.py (the
pending note, image comparison, when to plan, postpone and apply, the notice, the meaning of a recreate's result) and their use in waker.py on
stack shims: an update is applied only when the stack is idle and not busy, never during a turn, postponed by any use (also in the grace
period), told once, the stop goes through the re-checked path under the wake lock, a failed recreate keeps the note and alerts once, only one
recreate runs at a time and never during a boot, and a wake that arrives while the update runs waits for it.

Run from anywhere:  python3 -I ops/wake/updates_selftest.py
"""
import fcntl, importlib.util, json, os, shutil, stat, subprocess, sys, tempfile, threading, time, types
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("waker", os.path.join(HERE, "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
ul, wm = w.updatelib, w.warmlib
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

H = 3600
NOW = 1_900_000_000.0
IMG_A, IMG_B = "sha256:" + "a" * 64, "sha256:" + "b" * 64

# ---- the pending note
good = ul.parse_pending(json.dumps({"image": IMG_B, "ts": NOW}))
chk(good == {"image": IMG_B, "ts": NOW}, "parse_pending: the note redeploy_router.sh writes")
chk(ul.parse_pending('{"image": "sha256:abcdef012345", "ts": 5}')["image"] == "sha256:abcdef012345", "parse_pending: the 12-digit id the script writes")
chk(all(ul.parse_pending(x) is None for x in ("", "junk", "[]", "null", '{"image": 5}', '{"ts": 1}', '{"image": "../../etc/passwd"}', '{"image": "sha256:xyz"}',
                                               '{"image": "sha256:abc"}', '{"image": "; rm -rf /"}')), "parse_pending: junk, a missing or bad image id: no note")
chk(ul.parse_pending('{"image": "sha256:abcdef012345", "ts": "x"}')["ts"] == 0.0 and ul.parse_pending('{"image": "sha256:abcdef012345", "ts": NaN}')["ts"] == 0.0,
    "parse_pending: a bad time is zero, the note still counts")
chk(ul.same_image(IMG_A, IMG_A) and ul.same_image("sha256:abcdef012345", "sha256:abcdef012345" + "0" * 52) and ul.same_image("abcdef012345", "sha256:abcdef0123450000"),
    "same_image: prefix, short form and plain form")
chk(not ul.same_image(IMG_A, IMG_B) and not ul.same_image("sha256:abc", "sha256:abc") and not ul.same_image(None, IMG_A) and not ul.same_image(IMG_A, ""),
    "same_image: different images, ids too short to compare, missing: no")
chk(ul.pending_needed(good, IMG_A) and not ul.pending_needed(good, IMG_B) and not ul.pending_needed(good, None) and not ul.pending_needed(None, IMG_A),
    "pending_needed: only a known, different image (an unreadable container is not guessed at)")
chk(ul.memory_ok(2000, 700, 1500, True) and not ul.memory_ok(1400, 700, 1500, True) and ul.memory_ok(2300, 700, 1500, False) and not ul.memory_ok(2100, 700, 1500, False),
    "memory_ok: a stopped brain needs its footprint on top of the reserve, a running one only the reserve")

# ---- update_step
def step(grace=None, needed=True, retry_at=0, blocked="", human=None, act=None, idle=600, g=300, busy=False, now=NOW):
    calls = []
    r = ul.update_step(now, needed, retry_at, blocked, grace, human, act, idle, g, lambda: calls.append(1) or busy)
    return r[0], len(calls)
chk(step(needed=False) == ("none", 0), "step: image already current: nothing, and no expensive fact asked")
chk(step(retry_at=NOW + 5) == ("none", 0), "step: a failed attempt not yet due: nothing")
chk(step(human=NOW - 100, act=NOW - 900)[0] == "none" and step(human=NOW - 900, act=NOW - 100)[0] == "none", "step: the person OR the waker active within 10 min: not idle")
chk(step(human=NOW - 700, act=NOW - 900) == ("start", 1) and step() == ("start", 1), "step: idle (or never used) and not busy: plan it")
chk(step(human=NOW - 700, act=NOW - 900, busy=True) == ("none", 1), "step: idle but busy (a turn, a job, a cron marker): nothing")
chk(step(blocked="boot") == ("none", 0), "step: something booting elsewhere: not planned")
G = {"t0": NOW - 100, "human0": NOW - 700, "act0": NOW - 900}
chk(step(G, human=NOW - 700, act=NOW - 900) == ("wait", 1), "step: inside the grace period: wait")
chk(step({**G, "t0": NOW - 301}, human=NOW - 700, act=NOW - 900) == ("apply", 1), "step: grace over and still quiet: apply")
chk(step(G, human=NOW - 10, act=NOW - 900)[0] == "reset" and step(G, human=NOW - 700, act=NOW - 5)[0] == "reset",
    "step: ANY use or activity in the grace period postpones it to the next idle window")
chk(step({**G, "t0": NOW - 400}, human=NOW - 700, act=NOW - 900, busy=True)[0] == "reset", "step: busy when the grace ends: postponed, never applied")
chk(step({**G, "t0": NOW - 400}, human=NOW - 700, act=NOW - 900, blocked="boot")[0] == "wait", "step: grace over but a boot is running: wait")
chk(step(retry_at=NOW - 1, human=NOW - 700)[0] == "start", "step: the retry time has passed: planned again")
chk(ul.notice_wanted(True, True, True, True, False) and not ul.notice_wanted(False, True, True, True, False) and not ul.notice_wanted(True, False, True, True, False)
    and not ul.notice_wanted(True, True, False, True, False) and not ul.notice_wanted(True, True, True, False, False) and not ul.notice_wanted(True, True, True, True, True),
    "notice_wanted: Telegram stacks, day hours, known zone, enabled, once per image: all needed")
chk(ul.failure_decision(0, False) == ("ok", 0) and ul.failure_decision(3, False) == ("busy", 600) and ul.failure_decision(1, False)[0] == "fail"
    and ul.failure_decision(2, False)[0] == "fail" and ul.failure_decision(None, False)[0] == "fail" and ul.failure_decision(0, True)[0] == "fail",
    "failure_decision: PASS ok, a running container is not a failure, FAIL / error / timeout / killed fail (even a 0 after a timeout)")
chk(ul.notice_text("es").startswith("🔄 Hay una actualización") and "tus conversaciones y tu memoria quedan igual" in ul.notice_text("es")
    and ul.notice_text("ru").startswith("🔄 Есть обновление") and ul.notice_text("en").startswith("🔄 There is an update") and ul.notice_text("fr") == ul.notice_text("es"),
    "notice: es/ru/en, any other language is Spanish")

# ---- recreate as a subprocess
tmp = tempfile.mkdtemp()
def script(name, body):
    p = os.path.join(tmp, name); open(p, "w").write("#!/bin/bash\n" + body); os.chmod(p, 0o755); return p
w.RECREATE = script("pass.sh", 'echo "before : x"; echo "PASS: $1 config identical"; exit 0\n')
rc, to, line = w.run_recreate("demo", 20)
chk(rc == 0 and not to and line.startswith("PASS: demo"), "run_recreate: the script gets the stack name; its PASS line comes back")
w.RECREATE = script("fail.sh", 'echo "FAIL: $1 .env differs" >&2; exit 1\n')
rc, to, line = w.run_recreate("demo", 20)
chk(rc == 1 and not to and line.startswith("FAIL: demo"), "run_recreate: a FAIL exit and its line (stderr is read too)")
marker = os.path.join(tmp, "survivor")
w.RECREATE = script("hang.sh", f'(sleep 5; touch {marker}) &\nsleep 30\n')
t0 = time.time(); rc, to, line = w.run_recreate("demo", 1)
chk(to and time.time() - t0 < 10 and rc != 0, "run_recreate: a script that hangs is killed at the timeout")
time.sleep(0.2)
chk(not os.path.exists(marker), "run_recreate: the whole process group is killed (no child outlives the timeout)")
w.RECREATE = os.path.join(tmp, "no-such-script.sh")
rc, to, line = w.run_recreate("demo", 5)
chk(rc != 0 and not to, "run_recreate: a missing script is a failure, not a crash")

# ---- the waker's use of them, on stack shims (no docker)
WORK = os.path.join(tmp, "workdir"); os.makedirs(WORK)
w.STATE_DIR = tmp
w.NO_SLEEP = os.path.join(tmp, "no-such-NO_SLEEP")
w.CFG = {"cron": {"hold_seconds": 180, "retry_seconds": 600}, "reserve_mb": 1500, "evict_min_idle_seconds": 120, **wm.DEFAULTS, **ul.DEFAULTS}
logs, alerts = [], []
w.log = lambda msg, *a, **k: logs.append(msg)
w.ops = lambda kind, key, text=None: alerts.append((kind, key, text))
w.mem_available_mb = lambda: 9000
recreated = []
def fake_recreate(result):
    def run(name, timeout):
        recreated.append((name, timeout)); return result
    return run
w.run_recreate = fake_recreate((0, False, "PASS: config identical"))
class S:
    pass
for m in ("tick", "update_tick", "begin_update", "apply_update", "finish_update", "update_blocked", "send_update_notice", "pending_path", "read_update_pending",
          "clear_update_pending", "warm_tick", "local_offset", "zone_known", "last_human", "note_human", "save_state", "load_state", "drop_stale_banner",
          "first_on_image", "adopt_booted_image", "wake", "cron_tick"):
    setattr(S, m, getattr(w.Stack, m))
def tz_for(hour):
    return ((hour - time.gmtime().tm_hour) % 24) * 60
def shim(name="x", **kw):
    s = S(); s.name = name; s.state_file = os.path.join(tmp, f"{name}.state.json"); s.state_lock = threading.Lock()
    s.workdir = os.path.join(WORK, name); os.makedirs(s.workdir, exist_ok=True)
    s.booting = s.stopping = s.queued = s.updating = False; s.cron_only = False; s.cron_hold_until = 0.0; s.human_arrived = False
    s.update_grace, s.update_bad_logged = None, False
    s.warm_eligible, s.warm_kept = True, True
    s.human_ts = s.web_ts = s.warm_cleared = 0.0; s.notice_ts = None; s.refresh_day = None; s.banner_live = False
    s.day_hours = s.refresh_hour = s.notice_after_hours = None; s.tz_offset_min = tz_for(12); s.job_info = {}
    s.warm_demoted_logged = False; s._human_saved = 0.0; s.notice_inflight = False; s.notice_retry_at = 0.0; s._adopt_at = 0.0
    s.last_activity = time.time() - 3 * H; s.idle_web = s.idle_brain = 600; s.web_started = s.brain_started = time.time() - 9 * H
    s.wake_lock = threading.Lock()
    s.brain_exists = lambda: True; s.cron_due = None
    s.est_brain_mb = 700; s.lang = ""; s.tg_on = True; s.is_busy = False; s.up, s.web = True, False
    s.stopped, s.said, s.chats, s.wake_failed = [], [], set(), False
    s.image = IMG_A
    s.image_id = lambda: s.image
    s.brain_up = lambda: s.up
    s.web_up = lambda: s.web
    s.busy = lambda: s.is_busy
    s.busy_reasons = lambda ignore_gateway=False: []
    s.ui_requests = lambda: 0
    s.refresh_telegram = lambda *a: None
    s.sleep_request = lambda: None
    s.gateway_state = lambda: {}
    s.container_started = lambda: time.time() - 21 * H
    s.brain_rss_mb = lambda: 500
    def sleep_brain(recheck=None):   # the real one asks `recheck` under the wake lock right before the stop
        with s.wake_lock:
            if recheck is not None and not recheck():
                return False
            s.stopping = True
        s.stopped.append(("brain", s.updating)); s.up = False; s.stopping = False
        return True
    s.sleep_brain = sleep_brain
    s.sleep_web = lambda: (s.stopped.append("web"), setattr(s, "web", False))
    s.tell_person = lambda text: s.said.append(text) or 1
    s.__dict__.update(kw)
    return s
def put_human(s, age):
    w.write_epoch_file(os.path.join(s.workdir, ".last_human"), time.time() - age)
def note(s, image=IMG_B):
    open(s.pending_path(), "w").write(json.dumps({"image": image, "ts": time.time()}))
def settle():
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon and t.name.startswith("Thread"):
            t.join(3)
def free_locks():
    got = w.BOOT_SEM.acquire(blocking=False)
    if got: w.BOOT_SEM.release()
    return got and not w.RECREATE_LOCK.locked()
def idle_stack(name, **kw):
    s = shim(name, **kw); put_human(s, 2 * H); s.last_activity = time.time() - 2 * H; note(s)
    w.STACKS.clear(); w.STACKS[name] = s
    return s
def life(name, **kw):
    """plan -> (grace over) -> apply, the way the tick calls it"""
    s = idle_stack(name, **kw)
    s.tick(); settle()
    return s
def after_grace(s):
    if s.update_grace: s.update_grace["t0"] -= 400
    s.tick(); settle()

# 1: the whole path on an idle warm Telegram stack
recreated.clear(); alerts.clear()
s = life("u1")
chk(s.update_grace is not None and s.stopped == [] and recreated == [], "update: an idle warm stack with a pending image is only PLANNED first (nothing stopped yet)")
chk(len(s.said) == 1 and s.said[0].startswith("🔄 Hay una actualización") and s.load_state().get("update_noticed") == IMG_B, "update: one short note through the stack's bot, remembered")
s.tick(); settle()
chk(len(s.said) == 1 and s.stopped == [] and recreated == [], "update: inside the grace period nothing happens and the note is not repeated")
after_grace(s)
chk(s.stopped == [("brain", True)] and recreated == [("u1", float(ul.DEFAULTS["update_timeout_seconds"]))],
    "update: grace over, still quiet: the brain is stopped through sleep_brain(recheck), `updating` already set at the stop, then recreate runs with the timeout")
chk(not os.path.exists(s.pending_path()) and s.load_state().get("update_noticed") is None and not s.updating and free_locks()
    and ("resolve", "update:u1:failed", "u1: la actualización quedó aplicada") in alerts, "update: PASS clears the note, the state, `updating` and both locks")
chk(time.time() - s.last_activity < 5, "update: the recreated container gets a full idle period before the idle rule may stop it (a message that came meanwhile is not cut)")
s.tick(); settle()
chk(len(recreated) == 1, "update: nothing more after PASS")

# 2: Russian note, language of the stack
s = life("u2", lang="ru")
chk(s.said and s.said[0].startswith("🔄 Есть обновление"), "notice: in the stack's language")

# 3: any use in the grace period postpones; one notice per image even across windows
recreated.clear()
s = life("u3")
put_human(s, 0)
s.tick(); settle()
chk(s.update_grace is None and s.stopped == [] and recreated == [] and len(s.said) == 1, "grace: the person wrote during the grace period: postponed, nothing stopped")
s.tick(); settle()
chk(s.update_grace is None, "grace: not planned again while they are active (not idle)")
put_human(s, 2 * H); s.last_activity = time.time() - 2 * H
s.tick(); settle()
chk(s.update_grace is not None and len(s.said) == 1, "grace: the next idle window plans it again, WITHOUT a second note for the same image")
s.last_activity = time.time()            # a UI request / a held message: the waker's own activity clock moves
after_grace(s)
chk(s.stopped == [] and recreated == [] and s.update_grace is None, "grace: waker activity in the grace period postpones it as well")

# 4: never during a turn
recreated.clear()
s = idle_stack("u4", is_busy=True)
s.tick(); settle()
chk(s.update_grace is None and s.stopped == [] and s.said == [], "busy (a turn, a job, a cron marker): not even planned or announced")
s.is_busy = False; s.tick(); settle()
s.is_busy = True; after_grace(s)
chk(s.stopped == [] and recreated == [] and s.update_grace is None, "busy when the grace ends: postponed, never stopped under a turn")

# 5: the A1 race: the person arrives between the last check and the stop
recreated.clear()
s = idle_stack("u5")
s.tick(); settle()
s.update_grace["t0"] -= 400
def busy_then_person():
    put_human(s, 0); return False        # the router records the person's turn while busy() is being asked
s.busy = busy_then_person
s.tick(); settle()
chk(s.stopped == [] and recreated == [] and s.up and not s.updating and free_locks(), "race: a person arriving just before the stop: NO stop, no recreate, locks released")
s = idle_stack("u5b")
s.tick(); settle()
s.update_grace["t0"] -= 400
s.busy = lambda: (setattr(s, "last_activity", time.time()), False)[1]
s.tick(); settle()
chk(s.stopped == [] and recreated == [], "race: waker activity just before the stop: NO stop")
# between update_step and the stop (inside the re-check under the wake lock)
s = idle_stack("u5c")
s.tick(); settle()
s.update_grace["t0"] -= 400
real_still = wm.stop_still_ok
def late_person(h0, a0, hn, an, booting=False, stopping=False):
    put_human(s, 0); return real_still(h0, a0, s.last_human(), an, booting, stopping)
wm.stop_still_ok = late_person
s.tick(); settle()
wm.stop_still_ok = real_still
chk(s.stopped == [] and recreated == [] and not s.updating and free_locks(), "race: a person who appears under the wake lock, right before docker stop, cancels the update")

# 6: FAIL: the note stays, one alert, at most one try a day
recreated.clear(); alerts.clear()
w.run_recreate = fake_recreate((1, False, "FAIL: x .env differs"))
s = life("u6"); after_grace(s)
chk(len(recreated) == 1 and os.path.exists(s.pending_path()) and sum(1 for a in alerts if a[0] == "alert" and a[1] == "update:u6:failed") == 1
    and "FAIL: x .env differs" in alerts[-1][2], "FAIL: the note is kept and the operator is alerted once (with the script's FAIL line)")
st = s.load_state()
chk(st.get("update_failed") == IMG_B and st["update_retry_at"] > time.time() + 23 * H and not s.updating and free_locks(), "FAIL: retry not before a day, state recorded, locks released")
s.up = True; s.last_activity = time.time() - 2 * H; s.update_grace = None
for _ in range(3):
    s.tick(); settle()
chk(len(recreated) == 1 and s.update_grace is None, "FAIL: not planned again before the retry time")
s.save_state(update_retry_at=time.time() - 1); s.up = True; s.last_activity = time.time() - 2 * H
s.tick(); settle(); after_grace(s)
chk(len(recreated) == 2 and sum(1 for a in alerts if a[0] == "alert") == 1, "FAIL: a day later it tries again, and does NOT alert a second time for the same image")
new_pending = IMG_A[:7] + "c" * 64
note(s, new_pending); s.up = True; s.image = IMG_A; s.last_activity = time.time() - 2 * H; s.update_grace = None
s.tick(); settle()
chk(s.update_grace is not None, "FAIL: a NEWER deploy (another image) is not held back by the old failure's retry time")
w.run_recreate = fake_recreate((None, True, ""))
s = life("u6b"); alerts.clear(); after_grace(s)
chk(os.path.exists(s.pending_path()) and any(a[0] == "alert" and "tiempo agotado" in a[2] for a in alerts), "timeout: a recreate that never finishes is a failure: note kept, alert")
w.run_recreate = fake_recreate((3, False, "")); alerts.clear()
s = life("u6c"); after_grace(s)
chk(os.path.exists(s.pending_path()) and not alerts and 500 < s.load_state()["update_retry_at"] - time.time() <= 600,
    "exit 3 (the container was running after all): not a failure, no alert, next idle window")
w.run_recreate = fake_recreate((0, False, "PASS: config identical"))

# 7: a stopped stack: applied at once, nothing to stop, nobody to tell
recreated.clear()
s = idle_stack("u7", up=False)
s.tick(); settle()
chk(recreated == [("u7", float(ul.DEFAULTS["update_timeout_seconds"]))] and s.stopped == [] and s.said == [] and not os.path.exists(s.pending_path()),
    "asleep: recreated straight away, no stop, no note, no grace")
s = idle_stack("u7b", up=False); put_human(s, 60)
s.tick(); settle()
chk(len(recreated) == 1, "asleep: but not within the idle window after a person's wake (their boot may be starting)")
s = idle_stack("u7c", up=False, booting=True)
s.tick(); settle()
chk(len(recreated) == 1, "asleep: never while a boot is in progress (tick does nothing then)")

# 8: stacks that are awake but not kept warm are the idle rule's business
recreated.clear()
s = idle_stack("u8", warm_kept=False)
s.tick(); settle()
chk(recreated == [] and s.update_grace is None and s.stopped == [("brain", False)], "not warm: the update does not touch it; the idle rule stops it as before")
s.tick(); settle()
chk(len(recreated) == 1 and not os.path.exists(s.pending_path()), "...and once it sleeps the update is applied to the stopped container")

# 9: already on the pending image, an unreadable container, junk notes
recreated.clear()
s = idle_stack("u9", image=IMG_B); s.image_id = lambda: IMG_B
s.tick(); settle()
chk(recreated == [] and not os.path.exists(s.pending_path()), "same image: the note is removed, nothing recreated")
s = idle_stack("u9b"); s.image_id = lambda: None
s.tick(); settle()
chk(recreated == [] and os.path.exists(s.pending_path()) and s.update_grace is None, "container image unreadable: nothing done on a guess, note kept")
s = idle_stack("u9c"); open(s.pending_path(), "w").write("not json")
logs.clear(); s.tick(); s.tick(); settle()
chk(recreated == [] and sum("not a usable update note" in m for m in logs) == 1 and os.path.exists(s.pending_path()), "junk note: ignored, said once, left for the operator")
s = idle_stack("u9d"); os.unlink(s.pending_path())
s.tick(); settle()
chk(recreated == [] and s.update_grace is None, "no note: the tick does nothing (one stat per stack)")
s = idle_stack("u9e"); note(s, IMG_A)
other = IMG_B
s.clear_update_pending(other)
chk(os.path.exists(s.pending_path()), "clear: a note rewritten for ANOTHER image by a newer deploy is not removed")
s.clear_update_pending(IMG_A)
chk(not os.path.exists(s.pending_path()), "clear: the note of the applied image is removed")

# 10: notices: web-only stacks, night, switched off
s = life("u10", tg_on=False, web=True)
chk(s.said == [] and s.update_grace is not None, "web-only stack: no note, the update is still planned")
recreated.clear(); after_grace(s)
chk(s.stopped == ["web", ("brain", True)] and len(recreated) == 1, "web-only stack: the web tier stops first, then the brain, then the recreate")
s = life("u10b", tz_offset_min=tz_for(3))
chk(s.said == [] and s.update_grace is not None, "night (03:xx local): no note ever reaches the person; the update is planned")
w.CFG["update_notice"] = False
s = life("u10c")
chk(s.said == [] and s.update_grace is not None, "update_notice false: no note")
w.CFG["update_notice"] = True
s = life("u10d", tz_offset_min=None); w.host_offset, real_host = (lambda: 0), w.host_offset
s2 = idle_stack("u10e", tz_offset_min=None); s2.tick(); settle(); w.host_offset = real_host
chk(s2.said == [], "zone unknown (host on UTC): no note")
w.CFG["update_idle_seconds"] = 3600
s = idle_stack("u10f"); s.last_activity = time.time() - 1800; put_human(s, 1800)
s.tick(); settle()
chk(s.update_grace is None, "update_idle_seconds is honoured (30 min idle is not enough for 1 h)")
w.CFG["update_idle_seconds"] = ul.DEFAULTS["update_idle_seconds"]

# 11: one recreate at a time, never during a boot, memory
recreated.clear()
s = life("u11"); other = shim("u11-other", booting=True); w.STACKS["o"] = other
s.update_grace["t0"] -= 400
s.tick(); settle()
chk(recreated == [] and s.stopped == [] and s.update_grace is not None, "boot elsewhere: the planned update waits (not stopped, not recreated)")
other.booting = False
w.RECREATE_LOCK.acquire()
s.tick(); settle()
chk(recreated == [] and s.stopped == [], "another update running (the global lock): waits")
w.RECREATE_LOCK.release()
w.BOOT_SEM.acquire()
s.tick(); settle()
chk(recreated == [] and s.stopped == [] and not w.RECREATE_LOCK.locked(), "max_parallel_boots: no free boot slot: waits, and the update lock is given back")
w.BOOT_SEM.release()
w.mem_available_mb = lambda: 1200
s.tick(); settle()
chk(recreated == [] and s.stopped == [], "no memory for one more boot: waits")
w.mem_available_mb = lambda: 9000
s.tick(); settle()
chk(len(recreated) == 1 and free_locks(), "...and goes ahead once the boot is over, the locks are free and memory is there")

# 12: two stacks with notes: one after the other
recreated.clear()
a, b = idle_stack("u12a"), shim("u12b"); put_human(b, 2 * H); b.last_activity = time.time() - 2 * H; note(b); w.STACKS["b"] = b
for _ in range(2):
    a.tick(); b.tick(); settle()
a.update_grace["t0"] -= 400; b.update_grace["t0"] -= 400
hold = threading.Event(); w.run_recreate = lambda name, timeout: (recreated.append((name, 0)), hold.wait(5), (0, False, "PASS: x"))[2]
a.tick(); b.tick()
time.sleep(0.3)
chk([r[0] for r in recreated] == ["u12a"] and b.stopped == [] and b.up, "two updates due together: only one recreate runs, the other stack is not even stopped")
hold.set(); settle()
b.tick(); settle()
chk([r[0] for r in recreated] == ["u12a", "u12b"] and free_locks(), "...the second one follows when the first is done")
w.run_recreate = fake_recreate((0, False, "PASS: config identical"))

# 13: tick and wake while an update runs
s = idle_stack("u13", updating=True, warm_kept=False)
s.tick(); settle()
chk(s.stopped == [], "tick: a stack being updated is left alone (no idle stop while its container is recreated)")
s = shim("u13b", updating=True)
threading.Timer(0.6, lambda: setattr(s, "updating", False)).start()
t0 = time.time(); s.wake("telegram", False, 5)
chk(time.time() - t0 >= 0.5 and s.human_ts > 0, "wake: a person's message during an update waits for it, then reaches the stack")

# 14: NO_SLEEP is the maintenance switch for updates too
open(os.path.join(tmp, "NO_SLEEP"), "w").close(); w.NO_SLEEP = os.path.join(tmp, "NO_SLEEP")
recreated.clear(); s = idle_stack("u14"); s.tick(); settle()
chk(recreated == [] and s.update_grace is None, "NO_SLEEP: no update is planned or applied")
w.NO_SLEEP = os.path.join(tmp, "no-such-NO_SLEEP")

# 15: review pass. An update's stack is "busy" to everybody else: the RAM guard must not stop the container the recreate script is booting
recreated.clear()
s = shim("u15", updating=True); s.busy = lambda: s.updating and bool(w.Stack.busy_reasons(s)); s.last_activity = time.time() - 2 * H
chk(w.Stack.busy_reasons(s) != [] and s.busy(), "busy_reasons: a stack being updated counts as busy")
w.STACKS.clear(); w.STACKS["u15"] = s
chk(w.evict_one() is False and s.stopped == [], "RAM guard: never evicts a stack in the middle of an update (it would cut the recreate's boot and FAIL it)")
s.updating = False
chk(w.evict_one() is True and s.stopped == [("brain", False)], "RAM guard (control): the same stack is evictable once the update is over")
s = shim("u15b", updating=True); s.cron_due = time.time() - 5; s.up = False
w.Stack.cron_tick(s)
chk(s.cron_due is None, "cron planner: nothing is planned or woken for a stack being updated")

# 16: max_awake: a recreate boots a brain, so it counts like a person's wake
recreated.clear(); w.CFG["max_awake"] = 2
s = idle_stack("u16", up=False); w.STACKS["o1"] = shim("u16-o1"); w.STACKS["o2"] = shim("u16-o2")
s.tick(); settle()
chk(recreated == [], "max_awake: a sleeping stack is not recreated while max_awake other brains run")
w.STACKS["o2"].up = False
s.tick(); settle()
chk(len(recreated) == 1, "max_awake: ...and goes ahead when a slot is free")
w.CFG.pop("max_awake")

# 17: a failed recreate that left no container says so (the stack is down until the operator acts)
alerts.clear(); w.run_recreate = fake_recreate((2, False, "no container stack-u17-hermes"))
s = idle_stack("u17", brain_exists=lambda: False); s.tick(); settle(); after_grace(s)
chk(any(a[0] == "alert" and "EL CONTENEDOR NO EXISTE" in a[2] for a in alerts) and os.path.exists(s.pending_path()), "FAIL with no container: the alert says the stack is down")
alerts.clear(); s = idle_stack("u17b"); s.tick(); settle(); after_grace(s)
chk(any(a[0] == "alert" for a in alerts) and not any("NO EXISTE" in a[2] for a in alerts if a[0] == "alert"), "FAIL with the container present: the usual alert")
w.run_recreate = fake_recreate((0, False, "PASS: config identical"))

# 18: recreate_hermes.sh takes a per-stack lock: the waker and redeploy_router.sh cannot recreate one stack at the same time
root = tempfile.mkdtemp(); os.makedirs(os.path.join(root, "ops", "wake")); os.makedirs(os.path.join(root, "stacks", "demo", "persist"))
shutil.copy(os.path.join(os.path.dirname(HERE), "recreate_hermes.sh"), os.path.join(root, "ops", "recreate_hermes.sh"))
lockf = open(os.path.join(root, "ops", "wake", "demo.recreate.lock"), "w"); fcntl.flock(lockf, fcntl.LOCK_EX)
r = subprocess.run(["bash", os.path.join(root, "ops", "recreate_hermes.sh"), "demo"], capture_output=True, text=True, timeout=60)
chk(r.returncode == 3 and "another recreate of demo is running" in r.stderr, "recreate_hermes.sh: a second recreate of the same stack backs off with the busy code (3)")
fcntl.flock(lockf, fcntl.LOCK_UN); lockf.close()
r = subprocess.run(["bash", os.path.join(root, "ops", "recreate_hermes.sh"), "demo"], capture_output=True, text=True, timeout=60)
chk(r.returncode != 3, "recreate_hermes.sh: with no other recreate running it goes on to its own checks (no docker / image here: exit 2)")
shutil.rmtree(root, ignore_errors=True)

# ---- redeploy_router.sh writes the note the waker reads (static check; the script needs ssh)
src = open(os.path.join(os.path.dirname(HERE), "redeploy_router.sh")).read()
chk("mark_pending" in src and ".update_pending" in src and "rm -f aibridge/ops/wake/$1.update_pending" in src and "The waker will apply the update when the stack is idle" in src,
    "redeploy_router.sh: a stack skipped as awake gets a note and the message says the waker applies it; a recreate that succeeds removes it")
out = subprocess.run(["bash", "-c", "new_id=abcdef012345; printf '{\"image\": \"sha256:%s\", \"ts\": %s}\\n' \"$new_id\" \"$(date +%s)\""],
                     capture_output=True, text=True).stdout
p = ul.parse_pending(out)
chk(p is not None and p["image"] == "sha256:abcdef012345" and p["ts"] > 1.7e9, "redeploy_router.sh: the note printf writes is exactly what the waker parses")
chk(subprocess.run(["bash", "-n", os.path.join(os.path.dirname(HERE), "redeploy_router.sh")]).returncode == 0, "redeploy_router.sh: valid shell")
rec = open(os.path.join(os.path.dirname(HERE), "recreate_hermes.sh")).read()
chk('[ "$state" = false ] || { echo "$C is running (awake): not recreating a live container' in rec and "exit 3" in rec,
    "recreate_hermes.sh still refuses a running container (exit 3): the waker stops first and the script is the last guard")

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
