#!/usr/bin/env python3
"""Offline test of the waker's always-on stacks ("always": true; no docker, no server, no network): the pure decisions of always.py (config check,
max_awake counting, eviction order and last resort, the auto-start with its settle time, back-off and stability, a person's sleep request
and its end) and their use in waker.py on stack shims: the idle rule and the cron_only path never stop an always brain, the auto-start goes
through wake("always"), a sleep request suspends it until the next real wake, the RAM guard and the watchdog order, warm exclusion and updates.

Run from anywhere:  python3 -I ops/wake/always_selftest.py
"""
import importlib.util, json, os, sys, tempfile, threading, time
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("waker", os.path.join(HERE, "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
al = w.alwayslib
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

H = 3600
NOW = 1_900_000_000.0

# ---- config check
chk(al.parse_always(True) == (True, None) and al.parse_always(False) == (False, None) and al.parse_always(None) == (False, None),
    "parse_always: true switches it on; false and a missing value are the default")
chk(al.parse_always("true") == (False, "str") and al.parse_always(1) == (False, "int") and al.parse_always([True]) == (False, "list"),
    "parse_always: a non-bool (the string \"true\", 1) is a config error, treated as false, the type is named for the log")

# ---- max_awake counts only on-demand brains
chk(al.on_demand_count([True, False, True, False, False]) == 3, "cap: always brains are not counted")
chk(not al.over_cap([True, True, True], 2, True, False), "cap: three always brains awake, max_awake 2: an on-demand wake still fits")
chk(al.over_cap([False, False, True], 2, True, False), "cap: two on-demand brains awake (plus an always one), max_awake 2: the next on-demand wake is over")
chk(not al.over_cap([False, False, False], 2, True, True), "cap: an always brain needs no slot to start")
chk(not al.over_cap([False, False], 2, False, False), "cap: nothing to start (web only): never over")
chk(al.over_cap([False] * 4, 4, True, False) and not al.over_cap([False] * 3, 4, True, False), "cap: unchanged for on-demand stacks (the old len(awake) >= max_awake)")

# ---- eviction order
def cand(name, order, always=False, web=False, brain=True):
    return {"name": name, "always": always, "web_up": web, "brain_up": brain, "order": order}
cs = [cand("al", 0, True, web=True), cand("p1", 1), cand("p2", 2)]
chk(al.evict_candidates(cs) == [("p1", "brain"), ("p2", "brain"), ("al", "web")], "evict: every non-always stack first (their own order), the always stack last and only its web tier")
cs = [cand("al", 0, True), cand("p1", 1)]
chk(al.evict_candidates(cs) == [("p1", "brain")], "evict: an always brain with its web tier asleep is never listed")
chk(al.evict_candidates(cs, last_resort=True) == [("p1", "brain"), ("al", "brain")], "evict: last resort (critical memory): the always brain, after every non-always one")
chk(al.evict_candidates([cand("al", 0, True)], True) == [("al", "brain")] and al.evict_candidates([cand("al", 0, True)]) == [], "evict: only an always brain left: it goes at the last resort only")
chk(al.evict_candidates([cand("al", 0, True, web=True)], True) == [("al", "web")], "evict: its web tier is taken first even at the last resort")
chk(al.evict_candidates([cand("web-only", 0, False, web=True, brain=False)]) == [("web-only", "web")], "evict: an ordinary stack with only its web tier up: the web tier")

# ---- the auto-start: settle, back-off, stability
chk([al.backoff_delay(n) for n in (0, 1, 2, 3, 4, 5, 6, 40)] == [0, 30, 60, 120, 240, 300, 300, 300], "back-off: 30, 60, 120, 240 s, then 300 s at most")
def dec(st, now, **kw):
    a = dict(always=True, suspended=False, mem_ok=True, busy_boot=False); a.update(kw)
    return al.start_decision(st, now, a["always"], a["suspended"], a["mem_ok"], a["busy_boot"])
st = al.new_state()
chk(al.observe(st, True, NOW) == [] and dec(st, NOW) == "wait", "start: brain up (nothing seen down): nothing to do")
chk(al.observe(st, False, NOW) == [("down",)] and dec(st, NOW) == "wait", "start: first sight of a down brain: it settles first (Docker's own restart, a recreate)")
chk(al.observe(st, False, NOW + 10) == [] and dec(st, NOW + 10) == "wait" and dec(st, NOW + al.SETTLE_S) == "start", "start: still down after the settle time: start")
chk(dec(st, NOW + 60, always=False) == "none", "start: not an always stack: never")
chk(dec(st, NOW + 60, busy_boot=True) == "wait", "start: a boot, stop or update in progress: wait")
chk(dec(st, NOW + 60, mem_ok=False) == "memory", "start: not enough memory: wait for it (the reserve)")
st["inflight"] = True
chk(dec(st, NOW + 60) == "wait", "start: a start already in flight: wait")
st["inflight"] = False
# failures back off, exponentially, and recover
d1 = al.finish_start(st, False, NOW + 60)
chk(d1 == 30 and dec(st, NOW + 61) == "backoff" and dec(st, NOW + 91) == "start", "back-off: first failed start: 30 s")
d2 = al.finish_start(st, False, NOW + 91)
d3 = al.finish_start(st, False, NOW + 151)
chk((d2, d3) == (60, 120) and st["fails"] == 3 and dec(st, NOW + 151 + 119) == "backoff" and dec(st, NOW + 151 + 120) == "start", "back-off: 60 s, then 120 s")
for _ in range(10):
    al.finish_start(st, False, NOW + 1000)
chk(st["retry_at"] == NOW + 1000 + 300, "back-off: capped at 5 minutes")
# a start that worked, then the brain dies right away: a failure with back-off, not a loop
st = al.new_state(); al.observe(st, False, NOW); al.finish_start(st, True, NOW + 30)
chk(al.observe(st, True, NOW + 40) == [] and st["started_at"] == NOW + 30, "died: up after the start: judged only after STABLE_S")
ev = al.observe(st, False, NOW + 70)
chk(ev == [("died", 1, 30)] and dec(st, NOW + 70 + al.SETTLE_S) == "backoff" and dec(st, NOW + 100) == "start", f"died: down 40 s after a start: counted as a failure, 30 s back-off (got {ev})")
al.finish_start(st, True, NOW + 100); al.observe(st, True, NOW + 101)
ev = al.observe(st, False, NOW + 130)
chk(ev == [("died", 2, 60)], f"died: again right away: 60 s (got {ev})")
chk(al.observe(st, False, NOW + 140) == [], "died: logged once per state change, not on every tick")
al.finish_start(st, True, NOW + 200); al.observe(st, True, NOW + 201)
ev = al.observe(st, True, NOW + 200 + al.STABLE_S)
chk(ev == [("stable",)] and st["fails"] == 0 and st["retry_at"] == 0.0, "stable: up for STABLE_S after a start: the back-off is forgotten (logged once)")
ev = al.observe(st, False, NOW + 900)
chk(ev == [("down",)] and dec(st, NOW + 900 + al.SETTLE_S) == "start", "crash after a healthy run: not a failure, started after the settle time, no back-off")
# a person's sleep request: suspended until the next real wake
st = al.new_state(); al.observe(st, False, NOW)
chk(dec(st, NOW + 999, suspended=True) == "suspended" and dec(st, NOW + 999) == "start", "sleep request: suspended means no start however long it is down; once resumed it starts")

# ---- the waker on stack shims (no docker)
tmp = tempfile.mkdtemp()
w.STATE_DIR = tmp
w.NO_SLEEP = os.path.join(tmp, "no-such-NO_SLEEP")
w.CFG = {"cron": {"hold_seconds": 180, "retry_seconds": 600}, "reserve_mb": 1500, "critical_mb": 700, "max_awake": 2, "evict_min_idle_seconds": 120,
         "task": {"hold_seconds": 600, "retry_seconds": 600}, **w.warmlib.DEFAULTS}
logs = []
w.log = lambda msg, *a, **k: logs.append(msg)
w.ops = lambda *a, **k: None
w.mem_available_mb = lambda: 9000
w.alwayslib.SETTLE_S = 0     # the settle time is covered above; here a start happens on the second tick
class S:
    announce_sleep = clear_sleep_notes = lambda self, *a, **k: 0   # the 💤 note to Telegram (sleep_request_selftest covers it)
    quiet = lambda self: False   # the person's verbosity (NOTICES.md): normal here
    compact_before_sleep = lambda self, *a: True   # idle compaction (sleep_request_selftest covers it)
    ocio_before_sleep = lambda self, *a: False   # idle-time work (ocio_wake_selftest covers it)
    pass
for m in ("tick", "always_tick", "always_start", "always_held", "always_wedged_check", "wake", "admit", "task_run_watch", "warm_tick", "local_offset", "zone_known", "last_human", "note_human",
          "drop_stale_banner", "save_state", "load_state", "update_tick", "update_blocked", "pending_path", "canary_path", "canary_pinned", "hold_seconds"):
    setattr(S, m, getattr(w.Stack, m))
S.always, S.always_suspended = False, False
def shim(name="x", always=True, **kw):
    s = S(); s.name = name; s.state_file = os.path.join(tmp, f"{name}.state.json"); s.state_lock = threading.Lock()
    s.workdir = os.path.join(tmp, "wd", name); os.makedirs(s.workdir, exist_ok=True)
    s.booting = s.stopping = s.queued = False; s.cron_only = False; s.cron_hold_until = 0.0; s.human_arrived = False
    s.always = always; s.always_suspended = False; s.always_st = al.new_state()
    s.update_grace, s.update_bad_logged, s.canary_logged, s.updating = None, False, False, False
    s.warm_eligible, s.warm_kept = False, False
    s.human_ts = s.web_ts = s.warm_cleared = 0.0; s._human_saved = 0.0; s.notice_ts = None; s.refresh_day = None; s.banner_live = False
    s.day_hours = s.refresh_hour = s.notice_after_hours = None; s.tz_offset_min = -180; s.job_info = {}
    s.last_activity = time.time() - 3 * H; s.idle_web = s.idle_brain = 600; s.web_started = s.brain_started = time.time() - 9 * H
    s.wake_lock = threading.Lock(); s.chats = set(); s.wake_failed = False
    s.est_brain_mb = 700; s.est_web_mb = 300; s.lang = ""; s.tg_on = False; s.is_busy = False; s.up, s.web = True, False
    s.stopped, s.said, s.hooks, s.starts = [], [], [], []
    s.brain_up = lambda: s.up
    s.web_up = lambda: s.web
    s.busy = lambda: s.is_busy
    s.busy_reasons = lambda ignore_gateway=False: []
    s.ui_requests = lambda: 0
    s.refresh_telegram = s.adopt_booted_image = lambda *a: None
    s.sleep_request = lambda: None
    s.clear_sleep_request = lambda: None
    s.confirm_handled = lambda ts: None
    s.gateway_state = lambda: {}
    s.container_started = lambda: time.time() - 21 * H
    s.brain_rss_mb = lambda: 500
    s.warm_tick = lambda *a: False
    s.update_tick = lambda *a: False
    def sleep_brain(recheck=None):
        s.stopped.append("brain"); s.up = False
        return True
    s.sleep_brain = sleep_brain
    s.sleep_web = lambda: (s.stopped.append("web"), setattr(s, "web", False))
    s.tell_person = lambda text: s.said.append(text) or 1
    def start_container(name):
        s.starts.append(name); s.up = True
        return ""
    s.start_container = start_container
    s.brain_ready = lambda need_tg=True: s.up
    s.first_on_image = lambda: False
    s.record_boot = lambda t: None
    s.footprint_mb = lambda: 0
    s.boot_estimate = lambda: 20
    s.brain = f"{name}-hermes"
    s.run_hooks = lambda reason, chat: s.hooks.append(reason)
    s.task_retry_after_hooks = lambda: 0.0
    s.say = lambda chat, text: s.said.append(text) or True
    s.__dict__.update(kw)
    return s
def settle():
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon and t.name.startswith("Thread"):
            t.join(5)

# idle rule: an always brain is never stopped, a plain one is (control)
s = shim("plain", always=False); s.tick()
chk(s.stopped == ["brain"], "control: a plain stack idle for 3 h is stopped by the idle rule, as before")
s = shim("al1"); s.tick()
chk(s.stopped == [] and s.up, "idle rule: an always brain idle for 3 h is NOT stopped")
chk(s.seen is not None and s.seen[1:] == (False, True, False, []) and time.time() - s.seen[0] < 5,
    "the tick leaves its snapshot for GET /__wake/all (web down, brain up, no UI request, nothing busy)")
s = shim("al1b", busy_reasons=lambda ignore_gateway=False: ["un turno del agente"]); s.tick()
chk(s.seen[4] == ["un turno del agente"] and w.stack_overview(s)["turn"] is True, "a turn the tick saw reaches the overview")
s = shim("al2", web=True); s.tick()
chk(s.stopped == ["web"] and s.up, "idle rule: its web tier still sleeps on idle (the brain stays)")
s = shim("al3", cron_only=True, last_activity=time.time() - 400, idle_brain=3600); s.tick()
chk(s.stopped == [] and s.up and s.cron_only is False, "cron_only path: min(idle_brain, hold_seconds) does not stop an always brain")
s = shim("plain2", always=False, cron_only=True, last_activity=time.time() - 400, idle_brain=3600); s.tick()
chk(s.stopped == ["brain"], "control: the same cron_only stack that is not always IS stopped by the short cron limit")
s = shim("al4", is_busy=True); s.tick()
chk(s.stopped == [] and s.up, "idle rule: busy or not, never stopped; nothing else changes")

# the auto-start: a down brain is started by the waker, through wake("always")
w.alwayslib.SETTLE_S = 5
s = shim("st1", up=False); logs.clear()
s.tick(); s.tick()
chk(s.starts == [] and sum("is down" in l for l in logs) == 1, "auto-start: a down brain settles first: nothing started, logged once")
w.alwayslib.SETTLE_S = 0
s.tick(); settle()
chk(s.starts == ["st1-hermes"] and s.up and s.hooks == ["always"] and any("reason always" in l for l in logs),
    f"auto-start: the next tick starts it (log reason always), the on_wake hooks get reason \"always\" (starts={s.starts}, hooks={s.hooks})")
chk(not s.always_st["inflight"] and s.always_st["started_at"] > 0 and s.always_st["fails"] == 0, "auto-start: a start that worked is recorded, no failure")
s.tick(); chk(s.starts == ["st1-hermes"], "auto-start: nothing more once it is up")

# failing start: back-off, logged once per change, not every tick
w.alwayslib.BACKOFF_BASE_S = 30
s = shim("st2", up=False)
s.start_container = lambda name: (s.starts.append(name), "docker start failed: boom")[1]
s.tick(); s.tick(); settle(); logs.clear()
n = len(s.starts)
for _ in range(5):
    s.tick(); settle()
chk(n == 1 and len(s.starts) == 1 and not logs, f"back-off: a failed start is not retried on every tick (starts={len(s.starts)}), and the ticks log nothing")
s.always_st["retry_at"] = time.time() - 1; s.tick(); settle()
chk(len(s.starts) == 2 and s.always_st["fails"] == 2 and 55 <= s.always_st["retry_at"] - time.time() <= 61, "back-off: after the wait it tries again; the second failure waits 60 s")

# memory: waits (logged once), starts when above the reserve; evicts nobody
w.mem_available_mb = lambda: 1800
s = shim("mem1", up=False); other = shim("mem-other", always=False, last_activity=time.time() - 3 * H); w.STACKS.clear(); w.STACKS["o"] = other; w.STACKS["m"] = s
logs.clear(); s.tick(); s.tick(); s.tick(); settle()
chk(s.starts == [] and sum("not enough free memory" in l for l in logs) == 1 and other.stopped == [], "memory: under reserve + footprint it waits, logs ONCE, and never evicts anybody")
w.mem_available_mb = lambda: 9000
s.tick(); settle()
chk(s.starts == ["mem1-hermes"] and other.stopped == [], "memory: back above the reserve: started")
# a start that loses the memory race inside wake(): postponed, counted for the back-off
w.mem_available_mb = lambda: 9000
s = shim("mem2", up=False); s.admit = lambda *a, **k: False
s.tick(); s.tick(); settle()
chk(s.starts == [] and s.always_st["fails"] == 1 and any("always start postponed" in l for l in logs), "memory: wake() finding no memory leaves the container alone and backs off")
# max_parallel_boots, update in progress
s = shim("boot1", up=False); w.BOOT_SEM.acquire()
s.tick(); s.tick()
time.sleep(0.3)
chk(s.starts == [] and s.always_st["inflight"], "boot slots: no free slot: the start waits for it (never starts beside another boot)")
w.BOOT_SEM.release(); settle()
chk(s.starts == ["boot1-hermes"], "boot slots: ...and goes ahead as soon as one is free")
s = shim("upd1", up=False, updating=True); s.tick(); s.tick(); settle()
chk(s.starts == [], "update: never starts the brain while the stack is being updated")
s.updating = False; s.tick(); settle()
chk(s.starts == ["upd1-hermes"], "update: ...and starts it once the update is over")
s = shim("bt", up=False, booting=True); s.tick(); s.tick(); settle()
chk(s.starts == [], "booting: tick leaves a stack that is already booting alone")

# NO_SLEEP pauses every automatic action of tick(), the auto-start included
open(os.path.join(tmp, "NO_SLEEP"), "w").close(); w.NO_SLEEP = os.path.join(tmp, "NO_SLEEP")
s = shim("ns", up=False); s.tick(); s.tick(); settle()
chk(s.starts == [], "NO_SLEEP: the maintenance switch pauses the auto-start too")
w.NO_SLEEP = os.path.join(tmp, "no-such-NO_SLEEP")

# a person's sleep request: stop, suspend, resume at the next real wake
s = shim("sl1")
s.sleep_request = lambda: {"ts": time.time() - 5, "mode": "ahora", "lang": "es"}
s.tick()
chk(s.stopped == ["brain"] and s.always_suspended and s.load_state().get("always_suspended") and any("stopped on request" in l for l in logs),
    "sleep request: the brain stops, the auto-start is suspended (saved, logged)")
s.sleep_request = lambda: None
for _ in range(4):
    s.tick(); settle()
chk(s.starts == [] and not s.up, "sleep request: the stack stays down while suspended, however many ticks")
s.always_suspended = False; s.always_suspended = bool(s.load_state().get("always_suspended"))
chk(s.always_suspended, "sleep request: a waker restart reads the suspension back from the state file")
s.wake("telegram", False, 5)
chk(not s.always_suspended and s.up and s.starts == ["sl1-hermes"] and not s.load_state().get("always_suspended") and any("auto-start is on again" in l for l in logs),
    "resume: the next real wake (telegram) starts it and ends the suspension (saved, logged)")
s.up = False; s.always_st = al.new_state()
s.tick(); s.tick(); settle()
chk(s.starts == ["sl1-hermes", "sl1-hermes"] and s.up, "resume: after that it is always-on again: a crash is restarted by the waker")
for reason in ("web", "cron", "task"):
    s = shim("sl-" + reason, up=False, always_suspended=True)
    s.wake(reason, False, None)
    chk(not s.always_suspended and s.up, f"resume: a {reason} wake also ends the suspension")
s = shim("sl-self", up=False, always_suspended=True); s.tick(); s.tick(); settle()
chk(s.always_suspended and s.starts == [], "resume: the always auto-start itself never ends the suspension (it does not even run)")
s = shim("sl-up", up=True, always_suspended=True); s.tick()
chk(not s.always_suspended, "resume: a brain seen up by other means (a recreate, a manual start) ends the suspension")
s = shim("sl-plain", always=False)
s.sleep_request = lambda: {"ts": time.time() - 5, "mode": "ahora", "lang": "es"}
s.tick()
chk(s.stopped == ["brain"] and not s.always_suspended and not s.load_state().get("always_suspended"), "control: a plain stack's sleep request writes nothing about always")

# a wake of an up stack changes nothing (point 6)
s = shim("up1"); s.wake("telegram", False, 3)
chk(s.up and s.starts == [] and s.stopped == [] and s.human_ts > 0, "wake: the brain already up, a Telegram message: nothing changes")

# admit: only on-demand brains are counted against max_awake
w.mem_available_mb = lambda: 9000
w.CFG["max_awake"] = 2
w.STACKS.clear()
al_a, al_b, al_c = shim("aa"), shim("ab"), shim("ac")
plain1, plain2 = shim("p1", always=False, up=False), shim("p2", always=False)
for x in (al_a, al_b, al_c, plain1, plain2):
    w.STACKS[x.name] = x
chk(plain1.admit(True, False, None, patient=False), "admit: three always brains up and one plain one, max_awake 2: a plain wake is admitted")
plain3 = shim("p3", always=False); w.STACKS["p3"] = plain3
plain1.up = False
chk(not plain1.admit(True, False, None, patient=False), "admit: two plain brains up: the cap holds for the next plain wake")
al_d = shim("ad", up=False); w.STACKS["ad"] = al_d
chk(al_d.admit(True, False, None, patient=False), "admit: an always brain needs no slot even when two plain brains are up")

# eviction: never an always brain; last resort after everything else
w.STACKS.clear()
a = shim("ev-al"); a.last_activity = time.time() - 9 * H
b = shim("ev-p1", always=False); b.last_activity = time.time() - 1 * H
c = shim("ev-p2", always=False); c.last_activity = time.time() - 2 * H
for x in (a, b, c):
    w.STACKS[x.name] = x
chk(w.evict_one() and c.stopped == ["brain"] and b.stopped == [] and a.stopped == [], "evict_one: the oldest idle plain stack goes first, the always brain (idle for 9 h) is not touched")
chk(w.evict_one() and b.stopped == ["brain"] and a.stopped == [], "evict_one: then the other plain one")
chk(w.evict_one() is False and a.stopped == [] and a.up, "evict_one: only an always brain left: the slot-cap / reserve guard never takes it")
chk(w.evict_one(last_resort=True) and a.stopped == ["brain"], "evict_one(last_resort): the always brain goes only now")
a.up = True; a.stopped.clear(); a.is_busy = True
chk(w.evict_one(last_resort=True) is False and a.stopped == [], "evict_one(last_resort): never a busy one")
a.is_busy = False; a.web = True; b.up = c.up = True; b.stopped.clear(); c.stopped.clear()
chk(w.evict_one(last_resort=True) and (b.stopped or c.stopped) and a.stopped == [], "evict_one(last_resort): even then the non-always stacks go before the always one")
b.up = c.up = False
chk(w.evict_one() and a.stopped == ["web"] and a.up, "evict_one: an always stack's web tier may go (it sleeps on idle anyway), its brain stays")
chk(w.evict_one() is False, "evict_one: ...and that is all the normal guard can take from it")

# the watchdog under critical memory: non-always first, the always brain only as the last resort
calls = []
real_evict = w.evict_one
w.evict_one = lambda exclude=None, last_resort=False: (calls.append(last_resort), False)[1]
w.mem_available_mb = lambda: 100
w.ops = lambda *a, **k: None
orig_sleep = w.time.sleep
class Stop(Exception): pass
def one_pass(secs):
    raise Stop
w.time.sleep = one_pass
try:
    w.watchdog_loop()
except Stop:
    pass
w.time.sleep = orig_sleep
chk(calls == [], "watchdog: sleeps before it looks (control of the harness)")
n = {"i": 0}
def sleeps(secs):
    n["i"] += 1
    if n["i"] > 1:
        raise Stop
w.time.sleep = sleeps
try:
    w.watchdog_loop()
except Stop:
    pass
w.time.sleep = orig_sleep
chk(calls == [False, True], f"watchdog: below critical_mb it asks for the normal eviction first, then the last resort (got {calls})")
w.evict_one = real_evict
w.mem_available_mb = lambda: 9000

# warm: an always stack is never a warm candidate and takes no warm_max slot
w.STACKS.clear()
def warm_stack(name, always):
    s = shim(name, always=always, warm_eligible=True)
    s.container_started = lambda: time.time() - 5 * H
    s.last_human = lambda: time.time() - H
    s.warm_cleared = 0.0; s.warm_demoted_logged = False
    return s
wa, wb, wc = warm_stack("w-al", True), warm_stack("w-b", False), warm_stack("w-c", False)
for x in (wa, wb, wc):
    w.STACKS[x.name] = x
w.CFG["max_awake"] = 4; w.CFG["warm_max"] = 2
w.update_warm()
chk([x.warm_kept for x in (wa, wb, wc)] == [False, True, True], "update_warm: the always stack is not a candidate: both warm slots (warm_max 2) go to the other two")
w.CFG["warm_max"] = 3

# updates keep working for an always stack (the brain is up and not warm: it used to be left to the idle rule, which never stops an always brain)
for m in ("read_update_pending", "clear_update_pending", "image_id", "begin_update", "apply_update", "finish_update", "brain_exists", "send_update_notice"):
    setattr(S, m, getattr(w.Stack, m))
def update_shim(name, always):
    s = shim(name, always=always); s.image_id = lambda: "sha256:" + "a" * 64
    open(s.pending_path(), "w").write(json.dumps({"image": "sha256:" + "b" * 64, "ts": time.time()}))
    return s
planned = []
real_step = w.updatelib.update_step
w.updatelib.update_step = lambda *a, **k: (planned.append(a[3]), ("wait", "test"))[1]
w.STACKS.clear()
s = update_shim("upd-al", True); w.STACKS[s.name] = s
w.Stack.update_tick(s, False, True)
chk(planned == [""], "updates: an always brain with a pending image goes through the update planning")
planned.clear(); s = update_shim("upd-plain", False); w.STACKS[s.name] = s
w.Stack.update_tick(s, False, True)
chk(planned == [], "updates (control): an awake stack that is neither warm nor always is left to the idle rule, as before")
w.updatelib.update_step = real_step
# update_blocked: max_awake counts only on-demand brains
w.CFG["max_awake"] = 1
w.STACKS.clear()
o1, o2 = shim("ub-al"), shim("ub-plain", always=False)
me = shim("ub-me", always=False, up=False)
for x in (o1, o2, me):
    w.STACKS[x.name] = x
chk("max_awake" in me.update_blocked(False), "update_blocked: one plain brain up, max_awake 1: a stopped stack's update waits")
o2.up = False
chk("max_awake" not in me.update_blocked(False), "update_blocked: only an always brain up: it takes no slot")
o1.always = False; o1.up = True
chk("max_awake" in me.update_blocked(False), "update_blocked: control: the same brain, not always, is counted")
w.CFG["max_awake"] = 4

# config check inside Stack.__init__ and its default
cfg = {"name": "cfgchk", "bind": "127.0.0.1", "port": 3999, "front": "f", "web": ["w"], "brain": "b", "persist_dir": os.path.join(tmp, "persist")}
w.STATE_DIR = tmp
logs.clear(); s0 = w.Stack(dict(cfg), 0)
chk(s0.always is False and not any("always" in l for l in logs), "Stack: no \"always\" option: today's behaviour, nothing logged")
logs.clear(); s1 = w.Stack({**cfg, "name": "cfgchk1", "always": True}, 0)
chk(s1.always is True and s1.always_suspended is False, "Stack: \"always\": true")
logs.clear(); s2 = w.Stack({**cfg, "name": "cfgchk2", "always": "true"}, 0)
chk(s2.always is False and sum("must be true or false" in l for l in logs) == 1, "Stack: \"always\": \"true\" (not a bool) is treated as false and logged once")
json.dump({"always_suspended": 123.0}, open(os.path.join(tmp, "cfgchk3.state.json"), "w"))
s3 = w.Stack({**cfg, "name": "cfgchk3", "always": True}, 0); s4 = w.Stack({**cfg, "name": "cfgchk3", "always": False}, 0)
chk(s3.always_suspended is True and s4.always_suspended is False, "Stack: the suspension of a person's sleep request is read back at start, only for an always stack")

# the documentation and the example
src = open(os.path.join(HERE, "waker.py")).read()
chk("Always-on stacks (\"always\": true" in src and "\"always\"" in src, "docs: the waker's docstring describes the option")
ex = json.load(open(os.path.join(HERE, "stacks.json.example")))
chk(any(s.get("always") is True for s in ex["stacks"]), "docs: stacks.json.example shows \"always\": true")


# operator holds (canary pin, <name>.hold, recreate lock held with flock) and the wedged-brain restart (second review, 19/11)
import fcntl as _fcntl
w.STATE_DIR = tmp
h = shim("holdx"); h.up = False; h.canary_logged = False
h.always_st = al.new_state(); logs.clear()
open(os.path.join(tmp, "holdx.hold"), "w").close()
h.always_tick(False); h.always_tick(False); time.sleep(0.05)
chk(not h.starts and sum("on hold (holdx.hold)" in l for l in logs) == 1, "hold file: no auto-start, logged once")
os.remove(os.path.join(tmp, "holdx.hold"))
lk = open(os.path.join(tmp, "holdx.recreate.lock"), "a"); _fcntl.flock(lk, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
logs.clear(); h.always_tick(False)
chk(any("on hold (recreate in progress)" in l for l in logs), "recreate lock held by another process: auto-start on hold")
_fcntl.flock(lk, _fcntl.LOCK_UN); lk.close()
open(os.path.join(tmp, "holdx.canary"), "w").write("image=test\n")
logs.clear(); h.always_tick(False)
chk(any("on hold (canary pin)" in l for l in logs), "canary marker: auto-start on hold")
os.remove(os.path.join(tmp, "holdx.canary"))
logs.clear(); h.always_tick(False)
chk(any("hold released" in l for l in logs), "hold released is logged when the last hold goes away")

wd = shim("wedge"); wd.up = True; wd.brain_ready = lambda need_tg=True: False; wd.always_st = al.new_state(); logs.clear()
t0 = time.time()
wd.always_wedged_check(wd.always_st, t0)
wd.always_wedged_check(wd.always_st, t0 + 30)                      # not re-checked before WEDGED_EVERY_S
wd.always_wedged_check(wd.always_st, t0 + al.WEDGED_S - 1)
chk(not wd.stopped, "wedged: running but not ready for less than WEDGED_S: left alone")
wd.always_wedged_check(wd.always_st, t0 + al.WEDGED_S + 61)
chk(wd.stopped == ["brain"] and any("not ready for" in l for l in logs), "wedged: not ready for WEDGED_S: restarted (stopped, auto-start follows)")
wb = shim("wedgebusy"); wb.up = True; wb.brain_ready = lambda need_tg=True: False; wb.is_busy = True; wb.always_st = al.new_state()
for k in range(0, al.WEDGED_S + 200, al.WEDGED_EVERY_S):
    wb.always_wedged_check(wb.always_st, t0 + k)
chk(not wb.stopped, "wedged: a busy brain (a long turn) is never restarted")
wr = shim("wedgeok"); wr.up = True; wr.always_st = al.new_state()
for k in range(0, al.WEDGED_S + 200, al.WEDGED_EVERY_S):
    wr.always_wedged_check(wr.always_st, t0 + k)
chk(not wr.stopped, "wedged: a ready brain is never restarted")

# third review (19/11): wedged restarts honour holds and back off, a hung docker never leaves a start in flight, outside starts are judged,
# an always stack with "warm" keeps the daily refresh
chk([al.wedge_delay(n) for n in (0, 1, 2, 3, 4, 5, 6, 9)] == [0, 0, 300, 600, 1200, 2400, 3600, 3600],
    "wedge_delay: the first wedged restart is immediate, then 5, 10, 20, 40 min, 1 h at most")
st = al.new_state()
r1, r2, r3 = al.record_wedge(st, NOW), al.record_wedge(st, NOW), al.record_wedge(st, NOW)
chk(r1 == (0, False) and r2 == (300, True) and r3 == (600, False) and st["retry_at"] == NOW + 600 and st["fails"] == 0,
    "record_wedge: counted apart from start failures, the alert fires once (at the second), retry_at pushed")
chk(al.wedge_cleared(st) == 3 and st["wedges"] == 0 and al.wedge_cleared(st) == 0, "wedge_cleared: returns the old count once, then 0")
st = al.new_state(); st["fails"] = 2; st["down_since"] = NOW - 50
al.observe(st, True, NOW)
chk(st["started_at"] == NOW, "observe: a brain brought up by someone else after failures is judged like our own start")
al.observe(st, True, NOW + al.STABLE_S)
chk(st["fails"] == 0 and st["retry_at"] == 0, "observe: ... and once it stays up STABLE_S the back-off is forgotten")
st = al.new_state(); st["down_since"] = NOW - 50; al.observe(st, True, NOW)
chk(st["started_at"] == 0.0, "observe: without earlier failures nothing changes (no start to judge)")

alerts = []
w.ops = lambda kind, key, text=None: alerts.append((kind, key))
wh = shim("wedgehold"); wh.up = True; wh.brain_ready = lambda need_tg=True: False; wh.always_st = al.new_state()
open(os.path.join(tmp, "wedgehold.hold"), "w").close()
for k in range(0, 3 * al.WEDGED_S, al.WEDGED_EVERY_S):
    wh.always_wedged_check(wh.always_st, t0 + k)
chk(not wh.stopped and wh.always_st.get("unready_since") is None, "wedged: never restarted while a hold file is there (the operator owns the brain)")
os.remove(os.path.join(tmp, "wedgehold.hold"))
wh.always_wedged_check(wh.always_st, t0 + 3 * al.WEDGED_S + 100)
chk(not wh.stopped, "wedged: after the hold is removed the 10 minutes start again (no restart at once)")

wt = shim("wedgetg", tg_on=True); wt.up = True; wt.brain_ready = lambda need_tg=True: wt.up and not need_tg; wt.always_st = al.new_state(); logs.clear()
def wedge_once(base):
    wt.always_wedged_check(wt.always_st, base)
    wt.always_wedged_check(wt.always_st, base + al.WEDGED_S + 1)
wedge_once(t0)
chk(wt.stopped == ["brain"] and wt.always_st["wedges"] == 1 and wt.always_st["retry_at"] <= t0 + al.WEDGED_S + 1 and not alerts
    and any("Telegram not connected" in l for l in logs), "Telegram outage: the first wedged restart is immediate, says why, no alert")
wt.up = True; wedge_once(t0 + 2000)
chk(wt.stopped == ["brain", "brain"] and wt.always_st["wedges"] == 2 and wt.always_st["retry_at"] >= t0 + 2000 + al.WEDGED_S + 300
    and alerts == [("alert", "always:wedgetg:wedged")], "Telegram outage: the second waits 5 min before the next start and alerts the operator once")
wt.up = True; wedge_once(t0 + 6000)
chk(wt.always_st["wedges"] == 3 and len(alerts) == 1, "Telegram outage: the third waits longer, no second alert")
wt.up = True; wt.brain_ready = lambda need_tg=True: wt.up
wt.always_wedged_check(wt.always_st, t0 + 9000)
chk(wt.always_st["wedges"] == 0 and alerts[-1] == ("resolve", "always:wedgetg:wedged") and any("ready again after 3" in l for l in logs),
    "ready again: the count is cleared and the alert resolved")
w.ops = lambda *a, **k: None

import subprocess as _sp
hz = shim("hung"); hz.always_st = al.new_state(); hz.always_st["inflight"] = True
hz.wake = lambda *a, **k: None
def _hung():
    raise _sp.TimeoutExpired(["docker", "inspect"], 90)
hz.brain_up = _hung; logs.clear()
hz.always_start()
chk(not hz.always_st["inflight"] and hz.always_st["fails"] == 1 and hz.always_st["retry_at"] > time.time()
    and any("checking the start failed (TimeoutExpired" in l for l in logs), "always_start: docker hung after the wake: a failed start with back-off, never left in flight")
hb = shim("hungboot"); hb.always_st = al.new_state(); hb.always_st["inflight"] = True; hb.booting = True; hb.wake = lambda *a, **k: None
hb.always_start()
chk(not hb.always_st["inflight"] and hb.always_st["fails"] == 0, "always_start: another wake is booting it: not a failure, not in flight")

def rss_stack(name, always, kept):
    s = shim(name, always=always, warm_eligible=True, warm_kept=kept)
    lh = time.time() - 2 * H   # fixed: the re-check before the stop compares it with the value read at the decision
    s.last_human = lambda: lh
    s.brain_rss_mb = lambda: 99999
    s.last_activity = time.time() - 3 * H
    s.notice_inflight, s.notice_retry_at = False, 0.0   # the inactivity-note path (no Telegram, no web here: it sends nothing)
    return s
for nm, alw, kept, want in (("rss-al", True, False, ["brain"]), ("rss-plain", False, False, []), ("rss-warm", False, True, ["brain"])):
    x = rss_stack(nm, alw, kept)
    w.Stack.warm_tick(x, False, True)
    chk(x.stopped == want, f"warm refresh (rss): always={alw} warm_kept={kept}: stopped={x.stopped} (want {want})")
x = shim("rss-al-nowarm", always=True, warm_eligible=False); _lh = time.time() - 2 * H; x.last_human = lambda: _lh; x.brain_rss_mb = lambda: 99999
w.Stack.warm_tick(x, False, True)
chk(x.stopped == [], "warm refresh: an always stack without \"warm\" is not refreshed (unchanged)")

# fourth review (19/11): no refresh under a hold, the wedged alert survives a state reset, no double count while a start is in flight
open(os.path.join(tmp, "rss-held.hold"), "w").close()
x = rss_stack("rss-held", True, False)
w.Stack.warm_tick(x, False, True)
chk(x.stopped == [], "warm refresh: an always stack under a hold is not refreshed (the auto-start would not bring it back)")
os.remove(os.path.join(tmp, "rss-held.hold"))
alerts = []
w.ops = lambda kind, key, text=None: alerts.append((kind, key))
wa2 = shim("wedgereset"); wa2.up = True; wa2.brain_ready = lambda need_tg=True: False; wa2.always_st = al.new_state()
for base in (t0, t0 + 2000):
    wa2.up = True
    wa2.always_wedged_check(wa2.always_st, base); wa2.always_wedged_check(wa2.always_st, base + al.WEDGED_S + 1)
chk(alerts == [("alert", "always:wedgereset:wedged")] and wa2.load_state().get("wedge_alerted"), "wedged alert: raised once and kept in the state file")
wa2.always_st = al.new_state(); wa2.up = True; wa2.brain_ready = lambda need_tg=True: True   # a waker restart or a sleep request
wa2.always_wedged_check(wa2.always_st, t0 + 9000)
chk(alerts[-1] == ("resolve", "always:wedgereset:wedged") and not wa2.load_state().get("wedge_alerted"),
    "wedged alert: resolved when ready even after the state was rebuilt, and cleared from the state file")
n = len(alerts); wa2.always_wedged_check(wa2.always_st, t0 + 9100)
chk(len(alerts) == n, "wedged alert: no second resolve")
w.ops = lambda *a, **k: None
st = al.new_state(); st["fails"] = 1; st["down_since"] = NOW - 50; st["inflight"] = True
al.observe(st, True, NOW)
chk(st["started_at"] == 0.0, "observe: while our own start is in flight the outside-start rule does not apply (no double count)")

# suspend of the host (19/11): BOOTTIME-MONOTONIC jumps, stamps that measure awake time move forward
chk(w.suspended_for(10.0, 10.5) == 0 and w.suspended_for(10.0, 910.0) == 900.0 and w.suspended_for(None, 5.0) == 0 and w.suspended_for(10.0, 9.0) == 0,
    "suspended_for: a jump over 2 s is a suspension of exactly that length; small drift, a missing reading or a negative jump are not")
g = w.boot_gap(); chk(g is None or g > -1, f"boot_gap: readable on this host ({g:.3f} s; two reads, so it may be a hair below 0)" if g is not None else "boot_gap: not available here")
S.after_suspend = w.Stack.after_suspend
S.stamp_snapshot = w.Stack.stamp_snapshot; S.SUSPEND_FIELDS = w.Stack.SUSPEND_FIELDS; S.SUSPEND_ALWAYS = w.Stack.SUSPEND_ALWAYS
sp = shim("susp"); t = time.time()
sp.last_activity, sp.web_started, sp.brain_started, sp.cron_hold_until, sp.task_hold_until = t - 50, t - 60, t - 70, t + 30, t + 40
sp.update_grace = {"t0": t - 10, "human0": 123.0, "act0": t - 50}
sp.human_ts = t - 500; sp.always_st = al.new_state(); sp.always_st.update(unready_since=t - 100, down_since=None, started_at=t - 5)
sp.after_suspend(900)
chk(abs(sp.last_activity - (t + 850)) < 1e-6 and abs(sp.cron_hold_until - (t + 930)) < 1e-6 and abs(sp.task_hold_until - (t + 940)) < 1e-6
    and abs(sp.brain_started - (t + 830)) < 1e-6, "after_suspend: idle clock, start times and holds move forward by the time slept")
chk(sp.update_grace["t0"] == t + 890 and sp.update_grace["act0"] == t + 850 and sp.update_grace["human0"] == 123.0,
    "after_suspend: the update grace keeps running only while awake (t0 and act0 move together; the person's stamp does not)")
chk(sp.human_ts == t - 500, "after_suspend: a real event time (the person's last message) is left alone")
chk(sp.always_st["unready_since"] == t + 800 and sp.always_st["down_since"] is None and sp.always_st["started_at"] == t + 895
    and sp.always_st["wedge_checked"] >= t, "after_suspend: always state moves too (no false wedge right after a resume)")
sp3 = shim("susp3"); t = time.time(); sp3.last_activity, sp3.cron_hold_until, sp3.brain_started = t - 50, t + 30, t - 70
sp3.always_st = al.new_state(); sp3.always_st["unready_since"] = t - 100; sp3.update_grace = {"t0": t - 10, "act0": t - 50}
snap = sp3.stamp_snapshot()
sp3.last_activity, sp3.cron_hold_until = t + 1, t + 181          # a message handled right after the resume, before the sleeper noticed
sp3.update_grace = {"t0": t + 1, "act0": t + 1}                  # and a new update plan started then
sp3.after_suspend(28800, snap)
chk(sp3.last_activity == t + 1 and sp3.cron_hold_until == t + 181 and sp3.update_grace == {"t0": t + 1, "act0": t + 1},
    "after_suspend with a snapshot: stamps written after the resume are already right and are not pushed hours ahead")
chk(sp3.brain_started == t - 70 + 28800 and sp3.always_st["unready_since"] == t - 100 + 28800,
    "after_suspend with a snapshot: the stamps still equal to the snapshot do move")
sp2 = shim("susp2"); sp2.cron_hold_until = 0.0; sp2.update_grace = None; sp2.after_suspend(60)
chk(sp2.cron_hold_until == 0.0, "after_suspend: an unset hold (0) stays unset")

# fixed-time crons woken at the slot before their time (19/11: the 07:30 digest arrived at 08:22)
G = 3600
chk(w.early_slot(want=7.5*G, fixed=True, t_after=8*G+1200, grid=G, lower=7*G, early_max=G) == 7*G+1200,
    "early_slot: a 07:30 job with slots at :20 is woken at 07:20, not 08:20")
chk(w.early_slot(7.5*G, False, 8*G+1200, G, 7*G, G) is None, "early_slot: an interval job keeps the slot after (unchanged)")
chk(w.early_slot(7*G+1200, True, 7*G+1200, G, 0, G) is None, "early_slot: a job exactly on a slot keeps it")
chk(w.early_slot(7.5*G, True, 8*G+1200, G, 7.4*G, G) is None, "early_slot: the earlier slot already passed: the next one (late, as before)")
chk(w.early_slot(7.5*G, True, 8*G+1200, G, 7*G, 5*60) is None, "early_slot: a wait longer than early_max keeps the slot after")

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
