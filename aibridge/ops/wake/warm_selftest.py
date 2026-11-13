#!/usr/bin/env python3
"""Offline test of the waker's warm ("siempreviva") package (no docker, no server, no network): the pure decisions of warm.py (warm keep and
expiry, eligibility, warm_max and cache-floor demotion, eviction order, daily refresh, inactivity note, once per stretch, night skip) and their
use in waker.py on stack shims (the idle rule, /dormir, the A1 race "a person arrives just before a planned stop", the honest boot estimate
with ops/wake/<name>.booted_image, the safe reading and writing of the stamp files in a workdir the agent can write to).

Run from anywhere:  python3 -I ops/wake/warm_selftest.py
(The router's half, .last_human and .idle_notice, is tested in router_selftest.py.)
"""
import importlib.util, json, os, sys, tempfile, threading, time, types
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("waker", os.path.join(HERE, "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
wm = w.warmlib
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

H = 3600
NOW = 1_900_000_000.0     # a fixed "now" for the pure functions (any epoch will do)

# ---- stamps and hours
chk(wm.clamp_epoch(NOW - 5, NOW) == NOW - 5 and wm.clamp_epoch(NOW + 30, NOW) == NOW, "clamp_epoch: past kept, a few seconds ahead counts as now")
chk(wm.clamp_epoch(NOW + 10 * H, NOW) is None and wm.clamp_epoch("x", NOW) is None and wm.clamp_epoch(0, NOW) is None
    and wm.clamp_epoch(float("nan"), NOW) is None and wm.clamp_epoch(-5, NOW) is None, "clamp_epoch: far future (the agent can write the file), junk, zero, NaN: none")
chk(wm.merge_human(NOW - 10 * H, NOW - H, NOW) == NOW - H and wm.merge_human(None, NOW - H, NOW) == NOW - H
    and wm.merge_human(NOW - 3 * H, None, NOW) == NOW - 3 * H and wm.merge_human(None, None, NOW) is None, "merge_human: the newest of the waker's own time and the file")
chk(wm.merge_human(NOW - 2 * H, NOW + 99 * H, NOW) == NOW - 2 * H, "merge_human: a file stamped in the far future cannot keep a stack warm forever")
chk(wm.parse_hours("09-21") == (9, 21) and wm.parse_hours("22-06") == (22, 6) and wm.parse_hours("nonsense") == (9, 21)
    and wm.parse_hours("5-5") == (9, 21) and wm.parse_hours("0-24") == (0, 24) and wm.parse_hours(None) == (9, 21), "parse_hours: ranges, wrap, junk gives the default")
def at_local(hour, offset=0, day=3):   # an epoch whose local hour is `hour` in a zone `offset` s from UTC (2030-03-day)
    import calendar
    return calendar.timegm((2030, 3, day, hour, 15, 0)) - offset
OFF = -3 * H
chk(wm.in_day_hours(at_local(9, OFF), OFF, "09-21") and wm.in_day_hours(at_local(20, OFF), OFF, "09-21"), "day hours: 09:15 and 20:15 inside")
chk(not wm.in_day_hours(at_local(8, OFF), OFF, "09-21") and not wm.in_day_hours(at_local(21, OFF), OFF, "09-21") and not wm.in_day_hours(at_local(3, OFF), OFF, "09-21"),
    "day hours: 08:15, 21:15 and 03:15 are not (a note is never sent at night)")
chk(wm.in_day_hours(at_local(23, OFF), OFF, "22-06") and wm.in_day_hours(at_local(2, OFF), OFF, "22-06") and not wm.in_day_hours(at_local(12, OFF), OFF, "22-06"), "day hours may wrap midnight")
chk(wm.local_parts(at_local(5, OFF), OFF) == (5, "2030-03-03"), "local_parts: hour and date in the person's zone")

# ---- warm keep / expire / eligibility
START = NOW - 5 * H     # the container started 5 h ago
def cand(**kw):
    a = dict(eligible=True, brain_up=True, last_human=NOW - 2 * H, started=START, cleared=0.0, now=NOW, warm_hours=24)
    a.update(kw)
    return wm.warm_candidate(a["eligible"], a["brain_up"], a["last_human"], a["started"], a["cleared"], a["now"], a["warm_hours"])
chk(cand(), "warm: eligible, brain up, the person used it 2 h ago during this run: kept")
chk(cand(last_human=NOW - 23.9 * H, started=NOW - 30 * H), "warm: 23.9 h after the last use: still kept")
chk(not cand(last_human=NOW - 24.1 * H, started=NOW - 30 * H), "warm: 24 h without the person: expired, normal idle rules again")
chk(not cand(eligible=False), "not eligible (\"warm\" missing or false): never kept")
chk(not cand(brain_up=False), "brain down: nothing to keep")
chk(not cand(last_human=None), "nobody ever used it: not warm")
chk(not cand(last_human=START - 600), "last use BEFORE this run of the container (a cron woke it later): not warm, a cron is not a person")
chk(cand(last_human=START + 1), "the person came after the start: warm")
chk(not cand(started=float("inf")) and not cand(started=None), "container start unreadable: not warm (never trusted)")
chk(not cand(cleared=NOW - H, last_human=NOW - 2 * H), "/dormir after the last use: not warm until the person is back")
chk(cand(cleared=NOW - 3 * H, last_human=NOW - 2 * H), "...the person used it AFTER the /dormir: warm again")
chk(not cand(last_human=NOW + 60), "a last use in the future (clock skew) is not warm")

# ---- warm_max and the cache floor
def cands(*ages_est):
    return [{"name": n, "last_human": NOW - a * H, "est_mb": est} for n, a, est in ages_est]
kept, dem = wm.warm_plan(cands(("a", 1, 700), ("b", 5, 700), ("c", 9, 700)), 9000, 3500, 3)
chk(kept == ["a", "b", "c"] and dem == [], "plan: three warm stacks and plenty of memory: all kept, most recent first")
kept, dem = wm.warm_plan(cands(("a", 1, 700), ("b", 5, 700), ("c", 9, 700), ("d", 3, 700)), 9000, 3500, 3)
chk(kept == ["a", "d", "b"] and dem == ["c"], "plan: more than warm_max: the oldest last_human is demoted")
kept, dem = wm.warm_plan(cands(("a", 1, 700), ("b", 5, 700), ("c", 9, 700)), 3000, 3500, 3)
chk(kept == ["a", "b"] and dem == ["c"], "plan: free memory under reserve + cache floor: the LRU warm stack becomes a normal idle stack (its 700 MB are counted)")
kept, dem = wm.warm_plan(cands(("a", 1, 700), ("b", 5, 700), ("c", 9, 700)), 1500, 3500, 3)
chk(kept == [] and sorted(dem) == ["a", "b", "c"], "plan: nowhere near enough memory: none kept")
chk(wm.warm_plan([], 100, 3500, 3) == ([], []) and wm.warm_plan(cands(("a", 1, 700)), 9000, 3500, 0) == ([], ["a"]), "plan: nothing to do; warm_max 0 keeps none")
chk(wm.web_kept(True, NOW - 3 * H, NOW, 24) and not wm.web_kept(True, NOW - 30 * H, NOW, 24) and not wm.web_kept(True, 0, NOW, 24)
    and not wm.web_kept(False, NOW - H, NOW, 24), "web tier: kept only for a warm brain AND a web use inside the warm period")

# ---- eviction order
def ev(name, act_h, warm=False, human_h=None, busy=False):
    return {"name": name, "busy": busy, "warm": warm, "last_activity": NOW - act_h * H, "last_human": None if human_h is None else NOW - human_h * H}
order = wm.evict_order([ev("warm-old", 5, True, 5), ev("idle-new", 1), ev("idle-old", 3), ev("warm-new", 2, True, 2)], NOW, 120)
chk(order == ["idle-old", "idle-new", "warm-old", "warm-new"], f"eviction: idle non-warm by LRU first, then warm by oldest last_human (got {order})")
chk(wm.evict_order([ev("b", 9, busy=True), ev("w", 9, True, 9, busy=True)], NOW, 120) == [], "eviction: a busy stack is never listed, warm or not")
chk(wm.evict_order([{"name": "x", "busy": False, "warm": False, "last_activity": NOW - 60, "last_human": None}], NOW, 120) == [], "eviction: active within evict_min_idle_seconds: not listed")
chk(wm.evict_order([{"name": "x", "busy": False, "warm": True, "last_activity": NOW - 3 * H, "last_human": NOW - 60}], NOW, 120) == [],
    "eviction: a warm stack whose person was active a minute ago is not listed even if its activity clock is old")
chk(wm.evict_order([{"name": "x", "busy": False, "warm": False, "last_activity": NOW - 3 * H, "last_human": NOW - 30}], NOW, 120) == [],
    "eviction: a NON-warm stack whose person wrote 30 s ago (the router's stamp, before any activity clock moved) is not listed either")
chk(wm.evict_order([{"name": "x", "busy": False, "warm": True, "last_activity": NOW - 3 * H, "last_human": NOW - 3 * H}], NOW, 120) == ["x"], "eviction: ...and is the last resort once the person is gone")

# ---- daily refresh
T5 = at_local(5, OFF)   # 05:15 local
def refresh(now=T5, done=None, human_age=2 * H, act_age=2 * H, uptime=21 * H, busy=False, rss=500, limit=1500, hour=5):
    calls = []
    got = wm.refresh_decision(now, OFF, hour, done, human_age, act_age, lambda: calls.append("up") or uptime, lambda: calls.append("busy") or busy,
                              lambda: calls.append("rss") or rss, limit)
    return got, calls
chk(refresh()[0] == "daily", "refresh: up 21 h, 05:15 local, idle 2 h, not busy: daily")
chk(refresh(uptime=19 * H)[0] is None, "refresh: up only 19 h: not yet")
chk(refresh(now=at_local(6, OFF))[0] is None and refresh(now=at_local(4, OFF))[0] is None, "refresh: only in the quiet hour")
chk(refresh(done="2030-03-03")[0] is None and refresh(done="2030-03-02")[0] == "daily", "refresh: once a day (done today: no; done yesterday: yes)")
chk(refresh(human_age=20 * 60)[0] is None and refresh(act_age=20 * 60)[0] is None, "refresh: the person or any activity within 30 min: no")
chk(refresh(busy=True)[0] is None, "refresh: busy: no")
chk(refresh(now=at_local(14, OFF), rss=1800)[0] == "rss" and refresh(now=at_local(14, OFF), rss=900)[0] is None, "refresh: the brain's memory above refresh_rss_mb: rss, at any hour")
chk(refresh(now=at_local(14, OFF), rss=1800, busy=True)[0] is None and refresh(now=at_local(14, OFF), rss=None)[0] is None
    and refresh(now=at_local(14, OFF), rss=1800, limit=0)[0] is None, "refresh: rss still needs not busy; unreadable or switched off: no")
got, calls = refresh(human_age=60)
chk(got is None and calls == [], "refresh: the cheap idle check comes first (no docker call is made for a stack somebody is using)")
got, calls = refresh(now=at_local(14, OFF), rss=900)
chk(calls == ["rss"], f"refresh: outside the window only the (cached) memory reading is asked, never busy (got {calls})")
chk(wm.stop_still_ok(NOW - 2 * H, NOW - 2 * H, NOW - 2 * H, NOW - 2 * H), "A1: nobody came back: the stop may go on")
chk(not wm.stop_still_ok(NOW - 2 * H, NOW - 2 * H, NOW - 1, NOW - 2 * H), "A1: the person's last_human moved after the decision: no stop")
chk(not wm.stop_still_ok(NOW - 2 * H, NOW - 2 * H, NOW - 2 * H, NOW - 1), "A1: any activity after the decision: no stop")
chk(not wm.stop_still_ok(NOW - 2 * H, NOW - 2 * H, NOW - 2 * H, NOW - 2 * H, booting=True) and not wm.stop_still_ok(1, 1, 1, 1, stopping=True), "A1: booting or already stopping: no stop")

# ---- inactivity note
def note(age_h, notice_ts=None, local_hour=12, after=6, warm_h=24):
    now = at_local(local_hour, OFF)
    return wm.notice_decision(now, now - age_h * H, notice_ts, OFF, "09-21", after, warm_h)
chk(note(6.1) and note(10, local_hour=20) and note(23.5), "note: between 6 h and 24 h after the last use, in the day hours: sent")
chk(not note(5.9) and not note(24.1), "note: not before notice_after_hours, not after the warm period")
chk(not note(7, local_hour=3) and not note(7, local_hour=22) and not note(7, local_hour=8), "note: never at night or outside the person's day hours")
now12 = at_local(12, OFF)
chk(not wm.notice_decision(now12, now12 - 8 * H, now12 - H, OFF, "09-21", 6, 24), "note: once per stretch (one already sent after the last use)")
chk(wm.notice_decision(now12, now12 - 8 * H, now12 - 20 * H, OFF, "09-21", 6, 24), "note: ...a note from an EARLIER stretch does not count (the person wrote since)")
# the stamp the waker keeps is last_human + 1 s, not the send time: a person who wrote while the send was in flight starts a stretch of their own
lh1 = now12 - 8 * H
chk(not wm.notice_decision(now12, lh1, lh1 + 1, OFF, "09-21", 6, 24), "note: stamp = last use + 1 s: the told stretch stays told")
now_next = at_local(12, OFF, day=4)   # the next day at noon, the person wrote at 03:00 local in between (a note sent after their message would have hidden this stretch)
chk(wm.notice_decision(now_next, now_next - 8 * H, lh1 + 1, OFF, "09-21", 6, 24), "note: ...and their next idle stretch is told again")
chk(not wm.notice_decision(now12, None, None, OFF, "09-21", 6, 24), "note: no known last use: nothing to say")
chk(wm.notice_text("es", 7.4).startswith("🕓 Hace 7 h que no hablamos.") and "/new arranca limpio" in wm.notice_text("es", 7) and "/dormir me apaga" in wm.notice_text("es", 7),
    "note: the Spanish text of the spec")
chk(wm.notice_text("ru", 7).startswith("🕓 Прошло 7 ч") and wm.notice_text("en", 7).startswith("🕓 It has been 7 h") and wm.notice_text("fr", 7) == wm.notice_text("es", 7),
    "note: Russian and English in the same style; any other language is Spanish")

# ---- the waker's use of them, on stack shims (no docker)
tmp = tempfile.mkdtemp()
WORK = os.path.join(tmp, "workdir"); os.makedirs(WORK)
w.STATE_DIR = tmp
w.NO_SLEEP = os.path.join(tmp, "no-such-NO_SLEEP")
w.CFG = {"cron": {"hold_seconds": 180, "retry_seconds": 600}, "reserve_mb": 1500, "evict_min_idle_seconds": 120, **wm.DEFAULTS}
logs = []
w.log = lambda msg, *a, **k: logs.append(msg)
w.ops = lambda *a, **k: None
class S:
    pass
for m in ("tick", "warm_tick", "local_offset", "zone_known", "last_human", "note_human", "send_idle_notice", "clear_idle_banner", "drop_stale_banner",
          "save_state", "load_state", "first_on_image", "adopt_booted_image", "wake", "update_tick", "pending_path"):
    setattr(S, m, getattr(w.Stack, m))
def tz_for(hour):   # a tz_offset_min that puts the local hour of "now" at `hour`
    return ((hour - time.gmtime().tm_hour) % 24) * 60
def shim(name="x", **kw):
    s = S(); s.name = name; s.state_file = os.path.join(tmp, f"{name}.state.json"); s.state_lock = threading.Lock()
    s.workdir = os.path.join(WORK, name); os.makedirs(s.workdir, exist_ok=True)
    s.booting = s.stopping = False; s.cron_only = False; s.cron_hold_until = 0.0; s.human_arrived = False
    s.warm_eligible, s.warm_kept = True, True
    s.human_ts = s.web_ts = s.warm_cleared = 0.0; s.notice_ts = None; s.refresh_day = None; s.banner_live = False
    s.day_hours = s.refresh_hour = s.notice_after_hours = None; s.tz_offset_min = tz_for(12); s.job_info = {}
    s.warm_demoted_logged = False; s._human_saved = 0.0; s.notice_inflight = False; s.notice_retry_at = 0.0; s._adopt_at = 0.0
    s.last_activity = time.time() - 3 * H; s.idle_web = s.idle_brain = 600; s.web_started = s.brain_started = time.time() - 9 * H
    s.wake_lock = threading.Lock()
    s.est_brain_mb = 700; s.lang = ""; s.tg_on = False; s.is_busy = False; s.up, s.web = True, False
    s.stopped, s.said, s.banner, s.threads = [], [], [], []
    s.brain_up = lambda: s.up
    s.web_up = lambda: s.web
    s.busy = lambda: s.is_busy
    s.busy_reasons = lambda ignore_gateway=False: []
    s.ui_requests = lambda: 0
    s.refresh_telegram = s.adopt_booted_image = lambda *a: None
    s.sleep_request = lambda: None
    s.gateway_state = lambda: {}
    s.container_started = lambda: time.time() - 21 * H
    s.brain_rss_mb = lambda: 500
    def sleep_brain(recheck=None):   # the real one asks `recheck` under the wake lock right before the stop
        if recheck is not None and not recheck():
            return False
        s.stopped.append("brain"); s.up = False
        return True
    s.sleep_brain = sleep_brain
    s.sleep_web = lambda: (s.stopped.append("web"), setattr(s, "web", False))
    s.tell_person = lambda text: s.said.append(text) or 1
    s.idle_banner = lambda text: s.banner.append(text) or True
    s.__dict__.update(kw)
    return s
def put_human(s, age):   # the router's /workdir/.last_human, `age` seconds old
    w.write_epoch_file(os.path.join(s.workdir, ".last_human"), time.time() - age)
def threads_done():
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon and t.name.startswith("Thread"):
            t.join(3)

# stamp files: a workdir the stack's agent can write to
f = os.path.join(WORK, "stamp")
w.write_epoch_file(f, 1234567890)
chk(w.read_epoch_file(f) == 1234567890.0 and os.stat(f).st_mode & 0o777 == 0o644, "stamp file: written atomically as text, read back")
real = os.path.join(tmp, "elsewhere"); open(real, "w").write("keep me")
os.unlink(f); os.symlink(real, f)
chk(w.read_epoch_file(f) is None, "stamp file: a symlink is not followed when reading")
chk(w.write_epoch_file(f, 5) and open(real).read() == "keep me" and not os.path.islink(f) and w.read_epoch_file(f) == 5.0,
    "stamp file: writing over a planted symlink replaces the link, the target stays untouched")
open(f, "w").write("9" * 200); chk(w.read_epoch_file(f) is None, "stamp file: an oversized file is ignored")
open(f, "w").write("not a number"); chk(w.read_epoch_file(f) is None, "stamp file: junk is ignored")
fifo = os.path.join(WORK, "fifo"); os.mkfifo(fifo); t0 = time.time()
chk(w.read_epoch_file(fifo) is None and time.time() - t0 < 2, "stamp file: a FIFO is ignored without blocking")
chk(w.write_epoch_file(os.path.join(tmp, "no-such-dir", "x"), 1) is False and w.read_epoch_file(os.path.join(tmp, "missing")) is None, "stamp file: a missing directory or file is not an error")

# last_human: the waker's own time and the router's file
s = shim("lh")
chk(s.last_human() is None, "last_human: nothing known")
put_human(s, 7200)
chk(abs(s.last_human() - (time.time() - 7200)) < 3, "last_human: from the router's file (a turn the person started while the brain was awake)")
s.note_human(web=True)
chk(abs(s.last_human() - time.time()) < 3 and abs(s.web_ts - time.time()) < 3 and s.load_state().get("human_ts"), "note_human: the waker's own wake time wins when newer, and is saved")
w.write_epoch_file(os.path.join(s.workdir, ".last_human"), time.time() + 9 * H)
chk(abs(s.last_human() - time.time()) < 3, "last_human: a file stamped far ahead cannot move it")

# a person reaching an awake stack ends what a cron planned for it; one arriving during a cron boot is remembered (A1)
s = shim("early", cron_only=True, cron_hold_until=time.time() + 170)
s.note_human(early=True)
chk(not s.cron_only and s.cron_hold_until == 0.0, "A1: a person reaching an awake stack clears the cron's short idle limit and hold")
s = shim("arr", booting=True, cron_only=True)
s.note_human()
chk(s.human_arrived and s.cron_only, "A1: a person calling during somebody else's boot sets human_arrived (the boot's owner ends the cron limit)")
s = shim("arr2", booting=False)
s.note_human()
chk(not s.human_arrived, "...not when nothing is booting")
# wake(): a human reason on an awake stack takes the early-return path and clears the cron limit; a cron reason does not
s = shim("wk", cron_only=True, cron_hold_until=time.time() + 100)
s.wake_lock = threading.Lock(); s.chats = set(); s.wake_failed = False
s.wake("telegram", False, 77)
chk(not s.cron_only and s.cron_hold_until == 0.0 and s.human_ts > 0 and s.stopped == [], "wake('telegram') on an awake stack: marked human, cron limit cleared, nothing stopped")
s = shim("wk2", cron_only=True, cron_hold_until=time.time() + 100)
s.wake_lock = threading.Lock(); s.chats = set(); s.wake_failed = False
s.wake("cron", False, None)
chk(s.cron_only and s.human_ts == 0.0, "wake('cron') on an awake stack: not a person, nothing changes")

# tick: the idle rule with and without warm
w.STACKS.clear()
s = shim("idle"); put_human(s, 2 * H)
s.warm_tick = lambda *a: False        # the refresh/note part is tested below; here only the idle rule
s.tick()
chk(s.stopped == [], "tick: a warm stack idle for 3 h is NOT stopped by the idle rule")
s = shim("cold", warm_kept=False); s.warm_tick = lambda *a: False
s.tick()
chk(s.stopped == ["brain"], "tick: the same stack not warm (expired, not eligible, or demoted) is stopped as before")
s = shim("web1", web=True, web_ts=time.time() - H); s.warm_tick = lambda *a: False
s.tick()
chk(s.stopped == [] and s.web, "tick: warm stack, the person used the web: web tier and brain both stay")
s = shim("web2", web=True, web_ts=0.0); s.warm_tick = lambda *a: False
s.tick()
chk(s.stopped == ["web"] and s.up, "tick: warm stack, the web NOT used in the period: only the web tier sleeps, the brain stays")
s = shim("web3", web=True, warm_kept=False, web_ts=time.time() - H); s.warm_tick = lambda *a: False
s.tick()
chk(s.stopped == ["web", "brain"], "tick: not warm: web then brain sleep in the same tick, as before")
s = shim("busy1", warm_kept=False, is_busy=True); s.warm_tick = lambda *a: False
s.tick()
chk(s.stopped == [], "tick: not warm but busy: still not stopped")
s = shim("cr", cron_only=True); s.warm_tick = lambda *a: False
s.tick()
chk(s.cron_only is False and s.stopped == [], "tick: a warm stack drops the cron's short limit (a person is using it)")
# /dormir: stops it and ends the warm period; the person's next use starts it again
s = shim("dorm"); put_human(s, 2 * H)
s.sleep_request = lambda: {"ts": time.time() - 5, "mode": "ahora", "lang": "es"}
s.clear_sleep_request = lambda: None
s.confirm_handled = lambda ts: None
s.warm_tick = lambda *a: False
s.tick()
chk(s.stopped == ["brain"] and s.warm_cleared > 0 and not s.warm_kept and s.load_state().get("warm_cleared"), "/dormir: the stack stops and its warm state is cleared (saved)")
lh = s.last_human()
chk(not wm.warm_candidate(True, True, lh, time.time() - 3 * H, s.warm_cleared, time.time(), 24), "/dormir: with the old last use it is not warm again...")
chk(wm.warm_candidate(True, True, time.time() + 1, time.time() - 3 * H, s.warm_cleared, time.time() + 2, 24), "...until the person is back")

# warm_tick: the daily refresh, through the tick, and the A1 race
w.CFG["refresh_hour"] = 5
def refresh_shim(name, **kw):
    s = shim(name, **{"tz_offset_min": tz_for(5), **kw}); put_human(s, 2 * H)
    s.last_activity = time.time() - 2 * H
    return s
s = refresh_shim("r1")
s.warm_tick(False, True)
chk(s.stopped == ["brain"] and s.refresh_day == time.strftime("%Y-%m-%d", time.gmtime(time.time() + s.local_offset())) and s.load_state().get("refresh_day"),
    "refresh: a warm stack up 21 h, idle 2 h, in its quiet hour: put to sleep once, the day is recorded")
s = refresh_shim("r1b"); s.refresh_day = time.strftime("%Y-%m-%d", time.gmtime(time.time() + tz_for(5) * 60)); s.warm_tick(False, True)
chk(s.stopped == [], "refresh: not twice on the same day")
s = refresh_shim("r1c", web=True); s.warm_tick(True, True)
chk(s.stopped == ["web", "brain"], "refresh: a warm stack with its web up sleeps web then brain")
s = refresh_shim("r2"); s.container_started = lambda: time.time() - 10 * H; s.warm_tick(False, True)
chk(s.stopped == [], "refresh: up only 10 h: left alone")
s = refresh_shim("r3", is_busy=True); s.warm_tick(False, True)
chk(s.stopped == [], "refresh: busy: left alone")
s = refresh_shim("r4"); put_human(s, 600); s.warm_tick(False, True)
chk(s.stopped == [], "refresh: the person was here 10 min ago: left alone")
s = shim("r5", tz_offset_min=tz_for(14)); put_human(s, 2 * H); s.last_activity = time.time() - 2 * H; s.brain_rss_mb = lambda: 1800; s.warm_tick(False, True)
chk(s.stopped == ["brain"] and s.refresh_day is None, "refresh: memory above refresh_rss_mb restarts it even at 14:00, without using up the day's refresh")
s = refresh_shim("r6", warm_kept=False); s.warm_tick(False, True)
chk(s.stopped == [], "refresh: a stack that is not being kept warm is the idle rule's business, not the refresh's")
# A1: the person's message arrives while busy() is being evaluated, a moment before the planned stop
s = refresh_shim("race")
def busy_then_person():
    w.write_epoch_file(os.path.join(s.workdir, ".last_human"), time.time())   # the router records the person's new turn
    return False
s.busy = busy_then_person
s.warm_tick(False, True)
chk(s.stopped == [] and s.refresh_day is None and any("cancelled" in m for m in logs), "A1 race: a person arrives just before the planned stop: NO stop, and today's refresh is not used up")
s = refresh_shim("race2")
def busy_then_activity():
    s.last_activity = time.time()       # a held web request is replayed: the waker's own activity clock moves
    return False
s.busy = busy_then_activity
s.warm_tick(False, True)
chk(s.stopped == [], "A1 race: activity noted by the waker just before the stop: NO stop")
s = refresh_shim("race3")
def busy_then_boot():
    s.booting = True
    return False
s.busy = busy_then_boot
s.warm_tick(False, True)
chk(s.stopped == [], "A1 race: a wake started meanwhile: NO stop")

# warm_tick: the inactivity note, once per stretch, in the person's day hours, through the stack's bot or a banner
def note_shim(name, **kw):
    s = shim(name, **{"tz_offset_min": tz_for(12), "tg_on": True, **kw}); put_human(s, 7 * H)
    s.last_activity = time.time() - 7 * H
    return s
s = note_shim("n1")
s.warm_tick(False, True); threads_done()
nfile = os.path.join(s.workdir, ".idle_notice")
chk(len(s.said) == 1 and s.said[0].startswith("🕓 Hace 7 h") and s.notice_ts and s.load_state().get("notice_ts"), "note: a warm Telegram stack idle 7 h at noon: one message through its bot, kept in the state")
chk(abs((w.read_epoch_file(nfile) or 0) - time.time()) < 5, "note: /workdir/.idle_notice written, so the router does not ask its own question")
s.warm_tick(False, True); threads_done()
chk(len(s.said) == 1, "note: not a second one in the same idle stretch")
s2 = note_shim("n1b")
s2.__dict__["notice_ts"] = None
s2.save_state(notice_ts=time.time() - 30 * H); s2.notice_ts = time.time() - 30 * H
s2.warm_tick(False, True); threads_done()
chk(len(s2.said) == 1, "note: a note from an earlier stretch does not block this one")
s = note_shim("n2", lang="ru"); s.warm_tick(False, True); threads_done()
chk(s.said and s.said[0].startswith("🕓 Прошло 7 ч"), "note: in the stack's language")
s = note_shim("n3", tz_offset_min=tz_for(3)); s.warm_tick(False, True); threads_done()
chk(s.said == [] and not os.path.exists(os.path.join(s.workdir, ".idle_notice")), "note: at 03:xx local: nothing (never at night), nothing written")
s = note_shim("n4", is_busy=True); s.warm_tick(False, True); threads_done()
chk(s.said == [], "note: a busy stack is not told 'we have not talked' (retried on a later tick)")
s = note_shim("n5", warm_kept=False); s.warm_tick(False, True); threads_done()
chk(s.said == [], "note: only for a warm stack that is being kept up")
s = note_shim("n6"); put_human(s, 2 * H); s.warm_tick(False, True); threads_done()
chk(s.said == [], "note: the person used it 2 h ago: too soon")
s = note_shim("n7"); s.tell_person = lambda text: 0
s.warm_tick(False, True); threads_done()
chk(s.notice_ts is None and s.notice_retry_at > time.time() + 500 and not os.path.exists(os.path.join(s.workdir, ".idle_notice")),
    "note: Telegram refused: not counted as sent, no .idle_notice, retry in 10 min")
s.warm_tick(False, True); threads_done()
chk(s.notice_ts is None, "note: ...and not retried on the very next tick")
s = note_shim("n8", tg_on=False, web=True); s.warm_tick(True, True); threads_done()
chk(len(s.banner) == 1 and s.banner[0].startswith("🕓 Hace 7 h") and s.said == [] and s.load_state().get("notice_banner") and s.banner_live,
    "note: a web-only stack gets the banner (key_check mechanism for one stack), not a Telegram message")
s = note_shim("n9", tg_on=False, web=False); s.warm_tick(False, True); threads_done()
chk(s.banner == [] and s.said == [], "note: a web-only stack whose web tier is down: nothing (the banner needs Open WebUI)")
s = note_shim("n10", tg_on=False, web=True); s.warm_tick(True, True); threads_done()
put_human(s, 60); s.notice_ts -= 600   # the person is back (their message is newer than the note)
s.tick(); threads_done()
chk(s.banner[-1] is None and not s.banner_live and not s.load_state().get("notice_banner"), "note: the web person is back: the banner is taken down")

# update_warm: who is kept, warm_max, the cache floor, a failure
w.STACKS.clear()
def fleet(n, free):
    w.mem_available_mb = lambda: free
    for i in range(n):
        s = shim(f"f{i}"); put_human(s, (i + 1) * H); w.STACKS[s.name] = s
        s.est_brain_mb = 700; s.warm_cleared = 0.0
    return list(w.STACKS.values())
w.STACKS.clear(); fl = fleet(3, 9000); w.update_warm()
chk(all(s.warm_kept for s in fl), "update_warm: three eligible stacks used today, plenty of memory: all kept")
w.STACKS.clear(); fl = fleet(5, 9000); w.update_warm()
chk([s.warm_kept for s in fl] == [True, True, True, False, False], "update_warm: warm_max 3: the three most recently used")
w.STACKS.clear(); fl = fleet(3, 3000); w.update_warm()
chk([s.warm_kept for s in fl] == [True, True, False], "update_warm: free memory below reserve + cache floor: the LRU warm stack goes back to normal rules")
w.STACKS.clear(); fl = fleet(3, 9000); fl[0].warm_eligible = False; fl[1].up = False; w.update_warm()
chk([s.warm_kept for s in fl] == [False, False, True], "update_warm: not eligible, or brain down: not kept")
w.STACKS.clear(); fl = fleet(2, 9000); fl[1].container_started = lambda: time.time() - 30 * 60; w.update_warm()   # last use 2 h ago, container started 30 min ago
chk([s.warm_kept for s in fl] == [True, False], "update_warm: a brain started after the person's last use (a cron woke it) is not warm")
w.STACKS.clear(); fl = fleet(2, 9000); fl[0].last_human = lambda: (_ for _ in ()).throw(OSError("boom")); w.update_warm()
chk([s.warm_kept for s in fl] == [False, True] and any("warm update failed" in m for m in logs),
    "update_warm: a failure keeps the state of a stack inside its warm period (a transient fault must not stop a brain somebody uses); a stack whose facts cannot be read is dropped")
w.STACKS.clear(); fl = fleet(2, 9000); put_human(fl[1], 30 * H); fl[1].warm_kept = True
w.mem_available_mb = lambda: (_ for _ in ()).throw(OSError("meminfo"))
w.update_warm()
chk([s.warm_kept for s in fl] == [True, False], "update_warm: failure for a stack past warm_hours: not carried (warm cannot outlive the period through errors)")
w.STACKS.clear(); fl = fleet(2, 9000); fl[0].container_started = lambda: float("inf"); w.update_warm()
chk([s.warm_kept for s in fl] == [True, True], "update_warm: docker inspect failing for one stack this cycle keeps its warm state (inside the period)")
w.STACKS.clear(); fl = fleet(2, 9000); fl[0].container_started = lambda: float("inf"); fl[0].warm_kept = False; w.update_warm()
chk([s.warm_kept for s in fl] == [False, True], "update_warm: ...but never turns warm on from unreadable facts")
w.STACKS.clear(); fl = fleet(2, 9000); fl[0].container_started = lambda: float("inf"); put_human(fl[0], 25 * H); w.update_warm()
chk([s.warm_kept for s in fl] == [False, True], "update_warm: ...and not past warm_hours")
seen = []
w.STACKS.clear(); fl = fleet(2, 9000)
fl[1].container_started = lambda: (seen.append([x.warm_kept for x in fl]), time.time() - 21 * H)[1]
w.update_warm()
chk(seen and all(v for row in seen for v in row), "update_warm: no stack flickers to not-warm while the cycle is computed (the RAM guard reads the flag from another thread)")
w.CFG["max_awake"] = 3
w.STACKS.clear(); fl = fleet(5, 9000); w.update_warm()
chk([s.warm_kept for s in fl] == [True, True, False, False, False], "update_warm: warm_max never exceeds max_awake - 1 (a free slot stays for the other stacks' crons)")
w.CFG["max_awake"] = 4

# evict_one: the RAM guard's order with real stacks
w.STACKS.clear()
a = shim("ev-warm", warm_kept=True); put_human(a, 5 * H); a.last_activity = time.time() - 5 * H
b = shim("ev-idle", warm_kept=False); b.last_activity = time.time() - H
c = shim("ev-new-warm", warm_kept=True); put_human(c, 2 * H); c.last_activity = time.time() - 2 * H
for s in (a, b, c):
    w.STACKS[s.name] = s
w.CFG["evict_min_idle_seconds"] = 120
chk(w.evict_one() and b.stopped == ["brain"] and a.stopped == [] and c.stopped == [], "evict_one: the idle NON-warm stack goes first, even though the warm ones are older")
chk(w.evict_one() and a.stopped == ["brain"] and c.stopped == [], "evict_one: then the warm stack with the oldest last_human")
c.last_activity = time.time() - 60
chk(w.evict_one() is False and c.stopped == [], "evict_one: a warm stack active within evict_min_idle_seconds is never taken")
c.last_activity = time.time() - 2 * H; put_human(c, 30); chk(w.evict_one() is False and c.stopped == [], "evict_one: ...nor one whose person wrote 30 s ago")
put_human(c, 2 * H); c.is_busy = True; chk(w.evict_one() is False, "evict_one: ...nor a busy one")
c.is_busy = False; chk(w.evict_one() and c.stopped == ["brain"], "evict_one: the last resort once nothing else is left and the person is gone")
w.STACKS.clear()

# ---- concurrency and message loss (review pass): the idle rule, the refresh's re-checks, the stop/wake lock, the note's stretch
# a demoted warm stack (memory dip) is not cut while its person is active: the router's stamp counts as activity for it
s = shim("dem1", warm_kept=False); put_human(s, 60); s.warm_tick = lambda *a: False
s.tick()
chk(s.stopped == [], "tick: a warm-eligible stack that was just demoted is NOT stopped while its person wrote a minute ago (the idle clock only knows turns)")
s = shim("dem2", warm_kept=False); put_human(s, 2 * H); s.warm_tick = lambda *a: False
s.tick()
chk(s.stopped == ["brain"], "tick: ...and is stopped once the person has been idle for longer than the idle limit")
s = shim("dem3", warm_kept=False, warm_eligible=False); put_human(s, 60); s.warm_tick = lambda *a: False
s.tick()
chk(s.stopped == ["brain"], "tick: a stack that is not warm-eligible keeps the old idle rule exactly")

# the refresh looks again after the slow web stop, and a cancelled one does not use up the day
s = refresh_shim("rw", web=True)
n = [0]
def busy_after_web():
    n[0] += 1
    return bool(s.stopped)          # false while the decision is taken, true once the web tier has been stopped
s.busy = busy_after_web
r = s.warm_tick(True, True)
chk(s.stopped == ["web"] and s.up and s.refresh_day is None and r is True, "refresh: something started while the web tier was stopping: the brain is NOT stopped and today's refresh is kept")
s = refresh_shim("rw2", web=True)
s.sleep_web = lambda: (s.stopped.append("web"), setattr(s, "web", False), put_human(s, 0))
s.warm_tick(True, True)
chk(s.stopped == ["web"] and s.up and s.refresh_day is None, "refresh: the person came back while the web tier was stopping: the brain stays up")

# sleep_brain(recheck): the check runs under the wake lock, the stop does not hold it, a refusal stops nothing
class B:
    name = "bs"; brain = "bs-brain"
    def scan_incidents(self): pass
B.sleep_brain = w.Stack.sleep_brain
real_docker = w.docker
dk = []
w.docker = lambda *a, **k: dk.append((a, b.stopping, b.wake_lock.locked())) or types.SimpleNamespace(returncode=0, stdout="", stderr="")
b = B(); b.stopping = False; b.wake_lock = threading.Lock()
seen = {}
def ask():
    seen["locked"] = b.wake_lock.locked(); return False
chk(b.sleep_brain(recheck=ask) is False and seen["locked"] and dk == [] and not b.stopping, "sleep_brain(recheck): refused under the wake lock: nothing stopped, flag clear")
chk(b.sleep_brain(recheck=lambda: True) is True and len(dk) == 1 and dk[0][1] is True and dk[0][2] is False and not b.stopping,
    "sleep_brain(recheck): accepted: `stopping` is set before the lock is released, and the lock is NOT held during the 45 s docker stop")
dk.clear(); b.sleep_brain()
chk(len(dk) == 1 and dk[0][1] is True and b.sleep_brain() is True, "sleep_brain(): the old path (no recheck) is unchanged")
w.docker = real_docker

# wake(): a stop that starts between its wait and its claim (the refresh sets `stopping` under the wake lock) is waited for, not raced
class Lk:
    def __init__(self, owner): self.owner, self.entries, self.stopping_at = owner, 0, []
    def __enter__(self):
        self.entries += 1
        if self.entries == 1:                 # a refresh took the lock first and began its stop
            self.owner.stopping = True
            threading.Timer(0.3, lambda: setattr(self.owner, "stopping", False)).start()
        self.stopping_at.append(self.owner.stopping)
        return self
    def __exit__(self, *a): return False
s = shim("wl"); s.wake_lock = Lk(s); s.chats = set(); s.wake_failed = False
s.wake("telegram", False, 5)
chk(s.wake_lock.entries == 2 and s.wake_lock.stopping_at == [True, False], "wake(): a stop that began between the wait and the claim is waited for (second pass sees `stopping` clear)")
s = shim("wl2", booting=True); s.wake_lock = threading.Lock(); s.chats = set(); s.wake_failed = False; s.note_human = lambda *a, **k: None
s.wake("telegram", False, 5)
chk(s.human_arrived, "wake(): a person arriving during another reason's boot is flagged under the lock, not only by the unlocked pre-check")
s = shim("wl3", booting=True); s.wake_lock = threading.Lock(); s.chats = set(); s.wake_failed = False; s.note_human = lambda *a, **k: None
s.wake("cron", False, None)
chk(not s.human_arrived, "wake(): a cron arriving during a boot is not a person")

# the note: a person who writes while the send is in flight starts a new stretch (the stamp is the old stretch's last use + 1 s)
s = note_shim("nrace")
def tell_slowly(text):
    put_human(s, 0)                    # the person writes while the Bot API call is in flight
    s.said.append(text); return 1
s.tell_person = tell_slowly
lh_decided = s.last_human()
s.warm_tick(False, True); threads_done()
chk(len(s.said) == 1 and s.notice_ts is not None and s.notice_ts < s.last_human() and abs(s.notice_ts - (lh_decided + 1)) < 2,
    "note: a person who wrote during the send: the note is stamped just after the use it was about, so their NEXT idle stretch is not taken as told")
# unknown zone: never at night, so never from a guess
real_host = w.host_offset
w.host_offset = lambda: 0
s = note_shim("z1", tz_offset_min=None); s.warm_tick(False, True); threads_done()
chk(s.said == [], "note: zone unknown (no tz_offset_min, no job zone, host on UTC): not sent (a UTC guess would reach a person at 06:00)")
w.host_offset = lambda: tz_for(12) * 60 or 86400
s = note_shim("z2", tz_offset_min=None); s.warm_tick(False, True); threads_done()
chk(len(s.said) == 1, "note: the host's own zone (not UTC) is a usable guess")
s = note_shim("z3", tz_offset_min=None, job_info={"j": ("job", tz_for(12) * 60, False)}); w.host_offset = lambda: 0
s.warm_tick(False, True); threads_done()
chk(len(s.said) == 1, "note: the zone of the stack's own jobs counts as known")
w.host_offset = real_host
# the banner removal is not retried on every tick when Open WebUI does not answer
s = note_shim("bb", tg_on=False, web=True); s.warm_tick(True, True); threads_done()
put_human(s, 60); s.notice_ts -= 600
s.idle_banner = lambda text: s.banner.append(text) and False
s.tick(); threads_done(); n1 = len(s.banner)
s.tick(); threads_done()
chk(n1 == 2 and len(s.banner) == n1 and s.banner_live and s.notice_retry_at > time.time() + 500, "note: a banner removal that failed is retried in 10 min, not on every tick")

# the honest boot estimate: ops/wake/<name>.booted_image
IMG = {"id": "sha256:aaa"}
class E:
    name = "boot"; state_file = os.path.join(tmp, "boot.state.json"); state_lock = threading.Lock(); _adopt_at = 0.0
for m in ("first_on_image", "boot_estimate", "record_boot", "load_state", "save_state", "boots", "adopt_booted_image"):
    setattr(E, m, getattr(w.Stack, m))
E.image_id = lambda self: IMG["id"]
e = E()
bi = os.path.join(tmp, "boot.booted_image")
chk(e.first_on_image() and e.boot_estimate() == w.FIRST_BOOT_S, "boot estimate: an image nobody has seen boot: FIRST_BOOT_S")
open(bi, "w").write("sha256:aaa\n")
chk(not e.first_on_image() and e.boot_estimate() == 60, "boot estimate: the image recreate_hermes.sh verified booted is known: the usual estimate, not 150 s")
open(bi, "w").write("sha256:bbb\n")
chk(e.first_on_image() and e.boot_estimate() == w.FIRST_BOOT_S, "boot estimate: a booted_image of ANOTHER image (a stale file) vouches for nothing")
open(bi, "w").write("sha256:aaa\n")
e.adopt_booted_image()
chk(e.load_state().get("image") == "sha256:aaa", "adopt: the next tick records the verified image in the waker's own state")
os.unlink(e.state_file); e._adopt_at = 0.0; open(bi, "w").write("sha256:zzz\n"); e.adopt_booted_image()
chk(e.load_state().get("image") is None, "adopt: a file that does not match the container's image is not adopted")
os.unlink(bi); e._adopt_at = 0.0; e.adopt_booted_image()
chk(e.load_state().get("image") is None and e.first_on_image(), "adopt/estimate: no file: exactly the old behaviour")
chk(w.booted_image_of("nobody") is None, "booted_image_of: a stack with no file")

# recreate_hermes.sh writes the file only after PASS and removes it on FAIL (static check of the script, which needs docker to run)
src = open(os.path.join(os.path.dirname(HERE), "recreate_hermes.sh")).read()
chk("ops/wake/$NAME.booted_image" in src and src.count("record_booted\n") >= 2 and src.count('rm -f "$BOOTED_FILE"') >= 3 and "Turn machinery warmed" in src
    and "boot config unchanged since last boot" in src and 'HEALTH_OK" = 1' in src, "recreate_hermes.sh: waits for the warm line, says whether the boot config was skipped, records booted_image only after PASS with /health answered")

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
