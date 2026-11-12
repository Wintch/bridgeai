#!/usr/bin/env python3
"""Offline test of the night jobs in waker.py (no docker, no server): the pure window/idle decision, due_jobs() moving a night that
already ran, and night_tick/night_run on a stack shim (which action, the done mark, the retry clock).

Run from anywhere:  python3 -I ops/wake/night_waker_selftest.py
"""
import calendar, importlib.util, json, os, sys, tempfile, threading, time
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("waker", os.path.join(HERE, "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

OFF = -3 * 3600   # the stacks' zone (UTC-3)
def local(y, mo, d, h, mi):   # a local wall-clock time in that zone as epoch
    return calendar.timegm((y, mo, d, h, mi, 0)) - OFF
RUN = local(2030, 3, 5, 4, 30)          # the fixed run: 04:30 on the 5th
H = 3600

# ---- the pure parts
chk(w.iso_offset("2030-03-05T04:30:00-03:00") == OFF and w.iso_offset("2030-03-05T04:30:00") is None and w.iso_offset(None) is None,
    "iso_offset: -03:00, none without a zone, none for junk")
chk(w.night_key(local(2030, 3, 4, 23, 0), OFF) == w.night_key(RUN, OFF) == "2030-03-04", "23:00 and 04:30 of one night share a key")
chk(w.night_key(local(2030, 3, 5, 23, 0), OFF) == "2030-03-05", "the next evening is the next night")
chk(w.night_window_start(RUN, OFF, "23:00") == local(2030, 3, 4, 23, 0), "a 04:30 run opens at 23:00 the evening before")
chk(w.night_window_start(local(2030, 3, 5, 23, 30), OFF, "23:00") == local(2030, 3, 5, 23, 0), "a 23:30 run opens at 23:00 the same evening")
chk(w.night_next(RUN, OFF, None) == RUN and w.night_next(RUN, OFF, "2030-03-04") == RUN + 24 * H, "a done night moves the fixed run a day on")

def dec(now, idle=2 * H, up=False, done=None, retry=0, nxt=RUN):
    return w.night_decision(now, nxt, OFF, done, "23:00", idle, H, up, retry)
chk(dec(local(2030, 3, 4, 22, 59)) == "none", "22:59: outside the window")
chk(dec(local(2030, 3, 4, 23, 0)) == "wake", "23:00, idle 2 h, asleep: wake")
chk(dec(local(2030, 3, 4, 23, 30), idle=30 * 60) == "wait", "idle only 30 min: wait (the person may still be there)")
chk(dec(local(2030, 3, 5, 2, 0), up=True) == "run", "02:00, brain up and idle: run (the caller checks busy)")
chk(dec(local(2030, 3, 5, 1, 0), retry=local(2030, 3, 5, 1, 5)) == "wait", "retry clock after a failed wake: wait")
chk(dec(RUN) == "none", "04:30 itself: the fixed run takes it (no early start)")
chk(dec(local(2030, 3, 5, 1, 0), done="2030-03-04") == "none", "this night already ran: nothing until the next evening")
chk(dec(local(2030, 3, 5, 23, 10), done="2030-03-04") == "wake", "the next evening (next_run_at not refreshed yet): wake again")
chk(dec(local(2030, 3, 7, 23, 10), done="2030-03-04", nxt=RUN) == "none",
    "next_run_at stale for days (never woken): left to the regular cron catch-up")

# ---- due_jobs moves a night that already ran (no wake for tonight's 04:30)
tmp = tempfile.mkdtemp()
w.CFG = {"cron": {"hold_seconds": 180, "retry_seconds": 600, "slot_seconds": 240, "ignore_names": ["jobwatch"]},
         "night": {"after": "23:00", "idle_minutes": 60, "jobs": ["jobnight"]}}
jobs = {"jobs": [
    {"id": "n1", "name": "jobnight", "enabled": True, "schedule": {"kind": "cron", "expr": "30 4 * * *"}, "next_run_at": "2030-03-05T04:30:00-03:00"},
    {"id": "d1", "name": "other", "enabled": True, "schedule": {"kind": "cron", "expr": "30 4 * * *"}, "next_run_at": "2030-03-05T04:30:00-03:00"},
    {"id": "h1", "name": "jobnight", "enabled": True, "schedule": {"kind": "cron", "expr": "0 */6 * * *"}, "next_run_at": "2030-03-05T06:00:00-03:00"},
]}
os.makedirs(os.path.join(tmp, "persist", "cron"))
json.dump(jobs, open(os.path.join(tmp, "persist", "cron", "jobs.json"), "w"))

class S:
    pass
for m in ("due_jobs", "night_tick", "night_run", "save_state", "load_state"):
    setattr(S, m, getattr(w.Stack, m))
def shim(**kw):
    s = S(); s.name = "x"; s.brain = "nobrain"; s.persist_dir = os.path.join(tmp, "persist")
    s.state_file = os.path.join(tmp, "x.state.json"); s.state_lock = threading.Lock()
    s.booting = s.stopping = False; s.cron_hold_until = 0.0
    s.job_info, s.night_done, s.night_retry_at, s.night_starting, s.night_jobs = {}, {}, 0.0, False, (0.0, [])
    s.up, s.is_busy, s.wakes, s.execs, s.wake_brings_up, s.exec_rc = False, False, [], [], True, 0
    s.last_activity = 0.0
    s.brain_up = lambda: s.up
    s.busy = lambda: s.is_busy
    def wake(reason, want_web=False, chat_id=None):
        s.wakes.append(reason); s.up = s.wake_brings_up
    s.wake = wake
    s.__dict__.update(kw)
    return s
import shutil
def fake_docker(*a, **k):
    """docker cp of jobs.json works on any container (as the real one does); exec is recorded with STATE["exec_rc"]."""
    if a[0] == "cp":
        shutil.copy(os.path.join(tmp, "persist", "cron", "jobs.json"), a[2])
        rc = 0
    else:
        STATE["execs"].append(a); rc = STATE["exec_rc"]
    return type("R", (), {"returncode": rc, "stdout": "", "stderr": ""})()
w.docker = fake_docker
STATE = {"exec_rc": 0, "execs": []}
w.STACKS = {}
def threads_done():
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon:
            t.join(2)

s = shim()
due = {j[0]: j[2] for j in s.due_jobs()}
chk(due.get("n1") == RUN and due.get("d1") == RUN and "h1" in due, "due_jobs: the night not done yet keeps its 04:30")
chk(s.job_info["n1"] == ("jobnight", OFF, True) and s.job_info["h1"][2] is False, "job_info: zone and daily read from jobs.json")
s.night_done = {"n1": "2030-03-04"}
due = {j[0]: j[2] for j in s.due_jobs()}
chk(due.get("n1") == RUN + 24 * H and due.get("d1") == RUN, "due_jobs: a done night moves only the night job a day on")

# ---- night_tick / night_run on the shim
real_time = time.time
def at(t):
    time.time = lambda: t
def run_tick(s, t):
    at(t); w.LAST_CRON_WAKE[0] = 0.0; STATE["execs"].clear(); s.night_jobs = (0.0, []); s.night_tick(); threads_done()

s = shim(); s.last_activity = local(2030, 3, 4, 22, 0)
run_tick(s, local(2030, 3, 4, 22, 30))
chk(s.wakes == [] and STATE["execs"] == [], "22:30: nothing")
run_tick(s, local(2030, 3, 4, 23, 30))
chk(s.wakes == ["cron"] and [e[:4] for e in STATE["execs"]] == [("exec", "nobrain", "hermes", "cron")] and STATE["execs"][0][-1] == "n1",
    "23:30, idle 90 min, asleep: woken like a cron, then hermes cron run n1 (the hourly one is not daily: left alone)")
chk(s.night_done == {"n1": "2030-03-04"} and json.load(open(s.state_file)).get("night_done") == {"n1": "2030-03-04"},
    "the night is marked done, also in the state file (survives a restart)")
chk(s.cron_hold_until > local(2030, 3, 4, 23, 30), "held awake until Hermes's next tick starts it")
s.up = False
run_tick(s, local(2030, 3, 5, 1, 0))
chk(s.wakes == ["cron"], "later the same night: no second wake")
chk(w.Stack.load_state(s).get("night_done") == {"n1": "2030-03-04"} and shim(state_file=s.state_file).load_state().get("night_done"),
    "a new Stack would read the mark back")

s = shim(); s.last_activity = local(2030, 3, 4, 23, 0)
run_tick(s, local(2030, 3, 4, 23, 30))
chk(s.wakes == [], "the person was there 30 min ago: wait")

s = shim(up=True, is_busy=True); s.last_activity = local(2030, 3, 4, 21, 0)
run_tick(s, local(2030, 3, 4, 23, 30))
chk(s.wakes == [] and STATE["execs"] == [], "awake and busy (a download): wait")
s.is_busy = False
run_tick(s, local(2030, 3, 4, 23, 35))
chk(s.wakes == [] and len(STATE["execs"]) == 1, "awake and quiet: started without a wake")

s = shim(wake_brings_up=False); s.last_activity = local(2030, 3, 4, 21, 0)
run_tick(s, local(2030, 3, 4, 23, 30))
chk(s.night_done == {} and s.night_retry_at == local(2030, 3, 4, 23, 30) + 600 and STATE["execs"] == [],
    "no RAM for the wake: not marked, retried after retry_seconds")
run_tick(s, local(2030, 3, 4, 23, 35))
chk(s.wakes == ["cron"], "inside the retry time: no new wake")

STATE["exec_rc"] = 1
s = shim(); s.last_activity = local(2030, 3, 4, 21, 0)
run_tick(s, local(2030, 3, 4, 23, 30))
chk(s.night_done == {} and s.night_retry_at > 0, "hermes cron run failed: not marked, retry later")
STATE["exec_rc"] = 0

s = shim(); s.last_activity = local(2030, 3, 4, 21, 0)
at(local(2030, 3, 4, 23, 30)); w.LAST_CRON_WAKE[0] = local(2030, 3, 4, 23, 29); s.night_jobs = (0.0, []); s.night_tick(); threads_done()
chk(s.wakes == [], "another stack took a cron slot a minute ago: wait for the next one")

w.CFG["night"]["jobs"] = []
s = shim(); s.last_activity = local(2030, 3, 4, 21, 0)
run_tick(s, local(2030, 3, 4, 23, 30))
chk(s.wakes == [], "night jobs off (empty list): nothing")
time.time = real_time

print("night_waker_selftest: " + ("all ok" if ok else "FAILED"))
sys.exit(0 if ok else 1)
