#!/usr/bin/env python3
"""Offline test of the "task" reason in waker.py (no docker, no server): the pure decision, task_tick's dispatch and the wake with no RAM.

Run from anywhere:  python3 -I ops/wake/tareas_waker_selftest.py
(selftest.py next to it drives the whole waker against fake containers on the server; this one only needs python.)
"""
import importlib.util, json, os, sys, tempfile, threading, time, types
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("waker", os.path.join(HERE, "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

NOW, MAXAGE = 1_000_000.0, 6 * 3600
def dec(req, retry_at=0, blocked=False, up=False, busy=False, now=NOW):
    return w.task_decision(req, now, retry_at, blocked, up, busy, MAXAGE)
fresh = {"first_ts": NOW - 5, "not_before": NOW - 5}
chk(dec(None) == "none", "no request: none")
chk(dec(fresh) == "wake", "request, brain down: wake")
chk(dec(fresh, up=True) == "run", "request, brain up and quiet: run (hooks do not run for an awake stack, so the waker starts them)")
chk(dec(fresh, up=True, busy=True) == "wait", "brain up and busy (a person talking): wait")
chk(dec({"first_ts": NOW - 5, "not_before": NOW + 60}) == "wait", "receiver's not_before in the future: wait")
chk(dec(fresh, retry_at=NOW + 10) == "wait", "retry clock after a failed wake: wait (even with the brain down)")
chk(dec(fresh, blocked=True) == "wait" and dec(fresh, blocked=True, up=True) == "wait", "booting, stopping or a run already starting: wait")
chk(dec({"first_ts": NOW - MAXAGE - 1, "not_before": 0}) == "drop", "older than 6 h: drop (the task stays open on the board)")
chk(dec({"first_ts": NOW - MAXAGE + 1, "not_before": 0}) == "wake", "just under 6 h: still wakes")
chk(dec({"not_before": 0}) == "drop" and dec({"first_ts": "x"}) == "drop" and dec([1]) == "drop" and dec(0) == "drop", "malformed request: drop")
chk(dec({"first_ts": NOW - 5}) == "wake", "no not_before: treated as due")

# task_tick on a stack shim: which action it takes, never touching docker
tmp = tempfile.mkdtemp()
w.CFG = {"cron": {"hold_seconds": 180, "retry_seconds": 600}, "task": {"max_age_seconds": MAXAGE, "hold_seconds": 600, "retry_seconds": 600}}
class S:
    pass
for m in ("read_task_request", "drop_task_request", "run_task_hooks", "task_tick", "wake", "admit", "tell_done"):
    setattr(S, m, getattr(w.Stack, m))
def shim(**kw):
    s = S(); s.name = "x"; s.task_file = os.path.join(tmp, "x.task.json"); s.task_retry_at = 0.0; s.task_starting = False
    s.booting = s.stopping = False; s.cron_hold_until = 0.0
    s.up, s.is_busy, s.calls, s.hooks = False, False, [], []
    s.brain_up = lambda: s.up
    s.busy = lambda: s.is_busy
    s.run_hooks = lambda reason, chat: s.hooks.append((reason, chat))
    s.wake = lambda *a, **k: s.calls.append(a)
    s.told = []
    s.tell_person = lambda text: s.told.append(text) or 1
    s.__dict__.update(kw)
    return s
def put(req):
    json.dump(req, open(os.path.join(tmp, "x.task.json"), "w"))
def threads_done():
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon and t.name.startswith("Thread"):
            t.join(2)
s = shim(); s.read_task_request = lambda: None; s.task_tick()
chk(s.calls == [] and s.hooks == [], "no request file: nothing happens")
t = time.time(); put({"first_ts": t, "not_before": t}); s = shim(); s.task_tick(); threads_done()
chk(s.calls == [("task", False, None)] and s.hooks == [], "brain down: wake('task') in a thread, no hooks run directly")
s = shim(up=True); s.task_tick(); threads_done()
chk(s.hooks == [("task", None)] and s.calls == [] and s.cron_hold_until > time.time() + 500 and not s.task_starting,
    "brain up and quiet: the task hooks run, the stack is held awake for task.hold_seconds, the guard flag is released")
chk(s.task_retry_at > time.time() + 500, "...and a request a hook left behind is not rerun on every tick (retry clock set)")
s = shim(up=True, is_busy=True); s.task_tick(); threads_done()
chk(s.hooks == [] and s.calls == [], "brain up and busy: nothing started")
s = shim(up=True); s.task_starting = True; s.task_tick(); threads_done()
chk(s.hooks == [], "a run already starting: no second one")
put({"first_ts": t - MAXAGE - 5, "not_before": 0}); s = shim(); s.task_tick()
chk(not os.path.exists(s.task_file) and s.calls == [], "stale request: removed, nobody woken")
open(s.task_file, "w").write("not json"); s = shim(); s.task_tick()
chk(not os.path.exists(s.task_file), "unreadable request: removed")
open(s.task_file, "w").write(" " * (w.TASK_REQUEST_MAX_BYTES + 5)); s = shim(); s.task_tick()
chk(not os.path.exists(s.task_file), "oversized request file: removed, not read whole")
real = os.path.join(tmp, "real.json"); json.dump({"first_ts": t}, open(real, "w")); os.unlink(s.task_file) if os.path.exists(s.task_file) else None
os.symlink(real, s.task_file); s = shim(); s.task_tick()
chk(not os.path.exists(s.task_file) and os.path.exists(real) and s.calls == [], "a symlink in the state dir is not followed (dropped, target kept)")

# wake("task") with no RAM: postponed, nobody told, no eviction, no alert, request file untouched
alerts, said = [], []
w.ops = lambda *a, **k: alerts.append(a)
w.mem_available_mb = lambda: 100
w.BOOT_SEM = threading.BoundedSemaphore(1)
put({"first_ts": t, "not_before": t})
s = shim(); s.wake = types.MethodType(w.Stack.wake, s)
s.wake_lock = threading.Lock(); s.chats = set(); s.queued = False; s.wake_failed = False
s.say = lambda *a, **k: said.append(a)
adm = []
s.admit = lambda need_brain, need_web, chat_id, patient=True: adm.append(patient) or False
s.wake("task")
chk(adm == [False], "task wake asks the RAM guard with patient=False (never evicts, never waits)")
chk(s.task_retry_at > time.time() + 500 and not s.wake_failed, "no RAM: retry clock set 10 min on, not a failed wake")
chk(alerts == [] and said == [] and os.path.exists(s.task_file), "no ops alert, no message to anybody, request kept")
chk(not s.booting, "booting flag released")

# ---- the waker's own cap on task hook runs (a hook that never counts its failures must not loop for 6 h) ----
for m in ("run_hooks", "_run_hooks", "count_task_try"):
    setattr(S, m, getattr(w.Stack, m))
hooks_dir = os.path.join(tmp, "hooks"); os.makedirs(hooks_dir)
ran = os.path.join(tmp, "hook-ran")
hook_path = os.path.join(hooks_dir, "40-task-run")
open(hook_path, "w").write(f"#!/bin/sh\necho x >> {ran}\nexit 1\n"); os.chmod(hook_path, 0o755)
w.HOOKS_DIR = hooks_dir
w.CFG["task"]["max_tries"] = 3
w.log = lambda *a, **k: None
def real_hooks_shim():
    s = shim(up=True)
    for m in ("run_hooks", "_run_hooks", "count_task_try"):
        setattr(s, m, types.MethodType(getattr(w.Stack, m), s))
    s.task_tries = [None, 0]
    return s
def ran_n():
    try: return len(open(ran).read().split())
    except OSError: return 0
alerts.clear(); t = time.time(); put({"first_ts": t, "not_before": t})
s = real_hooks_shim()
for _ in range(3): s.run_hooks("task", None)
chk(ran_n() == 3 and os.path.exists(s.task_file), "a hook that fails (rc 1, the 'reported itself' code) and leaves the request: it runs max_tries times")
s.run_hooks("task", None)
chk(ran_n() == 3 and not os.path.exists(s.task_file), "the next try is refused by the waker itself: hook not run, request dropped")
chk(len(alerts) == 1 and alerts[0][0] == "alert" and alerts[0][1] == "task:x:stuck", "...and the operator is told once")
chk(s.task_tries == [None, 0], "...the counter starts clean")
os.unlink(ran)
put({"first_ts": t + 1, "not_before": t}); s = real_hooks_shim(); s.run_hooks("task", None); s.run_hooks("task", None)
put({"first_ts": t + 2, "not_before": t}); s.run_hooks("task", None); s.run_hooks("task", None)
chk(os.path.exists(s.task_file) and ran_n() == 4, "a new request (another first_ts) starts its own count")
os.chmod(hook_path, 0o644); os.unlink(ran)
alerts.clear(); put({"first_ts": t + 3, "not_before": t}); s = real_hooks_shim()
for _ in range(4): s.run_hooks("task", None)
chk(ran_n() == 0 and not os.path.exists(s.task_file) and len(alerts) == 1, "a hook that is not executable (never runs, never counts) is stopped by the same cap, with an alert")
os.chmod(hook_path, 0o755)
open(hook_path, "w").write(f"#!/bin/sh\necho x >> {ran}\nrm -f {os.path.join(tmp, 'x.task.json')}\nexit 0\n"); os.chmod(hook_path, 0o755)
put({"first_ts": t + 4, "not_before": t}); s = real_hooks_shim(); s.task_tries = [t + 4, 2]; s.run_hooks("task", None)
chk(s.task_tries == [None, 0], "a hook that takes the request clears the count")
put({"first_ts": t + 5}); s = real_hooks_shim(); s.task_tries = [t + 5, 1]
for _ in range(10): s.run_hooks("cron", None)
chk(s.task_tries == [t + 5, 1] and ran_n() >= 10, "other wake reasons run the hooks and are not counted")
os.path.exists(s.task_file) and os.unlink(s.task_file)

# ---- a task run in progress is busy ----
NOWT = 5_000_000.0
def rdec(rec, poll="unknown", now=NOWT, hold=600, mx=3600):
    return w.task_run_decision(rec, now, lambda: poll, hold, mx)
rec = lambda age, rid="run_1": {"run_id": rid, "started": NOWT - age}
chk(rdec(rec(60), "running") == "busy" and rdec(rec(3000), "running") == "busy", "run seen running: busy, far beyond task.hold_seconds")
chk(rdec(rec(60), "finished") == "drop", "run seen finished: record dropped, not busy")
chk(rdec(rec(3601), "running") == "drop", "a record older than task.max_run_seconds is dropped even if the API says running")
chk(rdec(rec(100), "unknown") == "busy" and rdec(rec(700), "unknown") == "free", "API does not say: only the first task.hold_seconds count (the old behaviour)")
chk(rdec(rec(100, ""), "running") == "busy" and rdec(rec(700, ""), "running") == "free", "no run id: only the hold counts, the API is not asked")
asked = []
w.task_run_decision(rec(10, ""), NOWT, lambda: asked.append(1) or "running", 600, 3600)
chk(not asked, "...really not asked")
chk(rdec(None) == "drop" and rdec({"run_id": "x"}) == "drop" and rdec({"started": "x"}) == "drop", "malformed record: dropped")
for m in ("busy", "busy_reasons", "task_run_busy", "poll_task_run"):
    setattr(S, m, getattr(w.Stack, m))
def busy_shim(poll):
    s = shim(up=True)
    s.task_run_file = os.path.join(tmp, "x.task.run.json"); s.task_poll = (0.0, "unknown")
    s.container_started = lambda: 0.0; s.newest_turn_age = lambda: None; s.gateway_state = lambda: {}; s.marker_fresh = lambda: False
    s.background_processes = lambda: 0; s.detached_jobs = lambda: 0; s.pending_jobs = lambda: 0
    s.poll_task_run = lambda: poll[0]
    s.busy_reasons = types.MethodType(w.Stack.busy_reasons, s); s.busy = types.MethodType(w.Stack.busy, s)
    s.task_run_busy = types.MethodType(w.Stack.task_run_busy, s)
    return s
poll = ["running"]
runf = os.path.join(tmp, "x.task.run.json")
json.dump({"run_id": "run_1", "started": time.time() - 1500}, open(runf, "w"))   # 25 min in: far past the 10 min hold
s = busy_shim(poll)
chk(s.busy_reasons() == [w.TASK_RUN_REASON] and s.busy(), "busy_reasons says 'una tarea en curso' for a run seen running (even long after the hold)")
w.STACKS.clear(); w.STACKS["x"] = s
s.web_up = lambda: False; s.last_activity = 0.0; s.stopped = []; s.sleep_brain = lambda: s.stopped.append(1)
w.CFG["evict_min_idle_seconds"] = 0; w.NO_SLEEP = os.path.join(tmp, "no-such-NO_SLEEP")
chk(w.evict_one() is False and not s.stopped, "evict_one (RAM guard) does not stop a stack that is mid-task")
poll[0] = "finished"
s.reported = []
s.report_task_run = lambda: s.reported.append(os.path.exists(runf))
chk(s.busy_reasons() == [] and not os.path.exists(runf), "run seen finished: not busy and the record is removed")
chk(s.reported == [True], "...and its answer is passed to the person once, BEFORE the record goes away")
json.dump({"run_id": "run_1", "started": time.time() - 99999}, open(runf, "w"))   # far past max_run_seconds: dropped without asking
s.reported = []
chk(s.busy_reasons() == [] and not os.path.exists(runf) and s.reported == [], "a record dropped for age (not seen finished) reports nothing")
chk(w.evict_one() is True and s.stopped == [1], "...then the stack can be evicted again")
w.STACKS.clear()
json.dump({"run_id": "run_1", "started": time.time() - 1500}, open(runf, "w")); poll[0] = "unknown"
chk(busy_shim(poll).busy_reasons() == [], "API unknown 25 min in: not busy (the hold has run out, as before)")
os.path.exists(runf) and os.unlink(runf)
chk(busy_shim(poll).busy_reasons() == [], "no record: nothing to say")

# poll_task_run: asks the starter, takes its LAST line, caches for task.poll_seconds
fake = os.path.join(tmp, "fake_run.py"); calls = os.path.join(tmp, "calls")
open(fake, "w").write(f"import sys\nopen({calls!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\nprint('2026 tareas_run: noise')\nprint('running')\n")
w.TASK_RUN_SCRIPT = fake
s = shim(up=True); s.task_poll = (0.0, "unknown"); s.poll_task_run = types.MethodType(w.Stack.poll_task_run, s)
w.CFG["task"]["poll_seconds"] = 30
chk(s.poll_task_run() == "running" and s.poll_task_run() == "running", "poll: the last line of the starter's output is the answer")
chk(open(calls).read().split("\n")[0] == "--stack x --check" and len(open(calls).read().split("\n")) == 2, "...asked with --stack NAME --check, and once (cached for poll_seconds)")
open(fake, "w").write("print('banana')\n"); s.task_poll = (0.0, "unknown")
chk(s.poll_task_run() == "unknown", "poll: any other word is 'unknown'")
w.TASK_RUN_SCRIPT = os.path.join(tmp, "missing.py"); s.task_poll = (0.0, "unknown")
chk(s.poll_task_run() == "unknown", "poll: a starter that cannot run is 'unknown', not an exception")

# a request with a result that came back: the person hears it once, through this stack's bot, before the run
t = time.time(); put({"first_ts": t, "not_before": t, "done": [{"n": 5, "by": "bot-b", "kind": "closed"}]}); s = shim(); s.task_tick(); threads_done()
s.task_tick(); threads_done()
chk(s.told == [w.DONE_NOTICE["es"]["closed"].format(by="bot-b", n=5)], "a result that came back is told to the person once, with the fixed line")
os.unlink(os.path.join(tmp, "x.task.json"))
print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
