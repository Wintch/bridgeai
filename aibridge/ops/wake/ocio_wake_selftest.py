#!/usr/bin/env python3
"""Offline test of idle-time work, the waker's side: the pure decisions (ocio_wake.py), the unit runner against a fake Hermes API (ocio_run.py), and the
waker's two moves: at the moment it would stop the brain it starts ONE unit instead (only when queued work, no update waiting and the stack opted in),
and the stack is busy until that unit is over (never cut), then asked again.

Run from anywhere:  python3 -I ops/wake/ocio_wake_selftest.py
"""
import http.server, importlib.util, json, os, subprocess, sys, tempfile, threading, time
import atexit as _a, shutil as _s, signal as _g
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_a.register(_s.rmtree, tempfile.tempdir, True)
_g.signal(_g.SIGTERM, lambda *_: sys.exit(143))
HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
os.environ["WAKE_STATE_DIR"] = tmp
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file)); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
o = load("ocio_wake", "ocio_wake.py")
ok = True
def chk(what, got, want=True):
    global ok; good = got == want; ok &= good
    print(("ok   " if good else "FAIL ") + what + ("" if good else f"  got={got!r} want={want!r}"), flush=True)

NOW = 1_000_000.0
C = o.conf({}, True)
chk("a stack that did not opt in has no settings", o.conf({}, None), None)
chk("opting in gives the defaults, and a global knob overrides one", (C["max_units_per_day"], o.conf({"max_units_per_day": 3, "bogus": 1}, True)["max_units_per_day"], "bogus" in o.conf({"bogus": 1}, True)), (12, 3, False))
d = lambda **k: o.decide(**dict(dict(c=C, now=NOW, st={}, n_waiting=2, busy=False, update_pending=False, ram_ok=True), **k))
chk("queued work, quiet stack: start", d(), ("start", ""))
chk("not opted in: nothing", d(c=None)[0], "none")
chk("nothing waiting: the stack sleeps as always", d(n_waiting=0), ("none", "empty"))
chk("an image update is waiting: it goes first", d(update_pending=True)[0], "none")
chk("anything busy: no new unit", d(busy=True), ("none", "busy"))
chk("no memory room: no unit", d(ram_ok=False)[0], "none")
chk("the daily cap stops it, a new day resets it", (d(st={"day": o.day(NOW), "units": 12})[1], d(st={"day": "1999-01-01", "units": 12})[0]), ("day cap", "start"))
chk("a failed start waits retry_seconds", (d(st={"retry_at": NOW + 5})[1], d(st={"retry_at": NOW - 5})[0]), ("retry later", "start"))
chk("a short gap after the last unit", (d(st={"last_end": NOW - 5})[1], d(st={"last_end": NOW - 60})[0]), ("gap", "start"))
st = o.started({}, NOW); st = o.started(st, NOW)
chk("started counts units per day", (st["units"], st["day"] == o.day(NOW)), (2, True))
chk("failed sets the retry clock", o.failed({}, NOW, 300)["retry_at"], NOW + 300)

# the queue as the waker reads it
q = os.path.join(tmp, "queue.json")
json.dump({"items": [{"state": "pendiente"}, {"state": "en_curso", "claimed": NOW - 10, "tries": 1}, {"state": "en_curso", "claimed": NOW - 4000, "tries": 1},
                     {"state": "en_curso", "claimed": NOW - 4000, "tries": 3}, {"state": "hecho"}, "junk"]}, open(q, "w"))
chk("waiting: pending plus a running unit that was lost, never a fresh running one or a third try", o.waiting(q, NOW), 2)
chk("waiting: no file or a damaged one is zero", (o.waiting(os.path.join(tmp, "none"), NOW), o.waiting(__file__, NOW)), (0, 0))
chk("run_over: young and running keeps the stack", o.run_over({"started": NOW - 10}, NOW, lambda: "running", 1500), "busy")
chk("run_over: finished lets go", o.run_over({"started": NOW - 10}, NOW, lambda: "finished", 1500), "drop")
chk("run_over: unknown while young still holds", o.run_over({"started": NOW - 10}, NOW, lambda: "unknown", 1500), "busy")
chk("run_over: older than the cap lets go without asking", o.run_over({"started": NOW - 2000}, NOW, lambda: 1 / 0, 1500), "drop")
chk("run_over: a damaged record lets go", (o.run_over(None, NOW, lambda: "running", 1500), o.run_over({"started": "x"}, NOW, lambda: "running", 1500)), ("drop", "drop"))

# the runner against a fake Hermes API: the fixed prompt only, no queue text, a record with the run id and nothing else
seen = []
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        out = json.dumps({"run_id": "r1"}).encode(); self.send_response(202); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def do_GET(self):
        out = json.dumps({"status": "completed"}).encode(); self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
UNIT = "Unit #7: boceto de prueba\ntres variantes chicas\nSave what you make in /workdir/ocio/resultados/7/"
env = dict(os.environ, OCIO_RUN_TEST_CLAIM=UNIT, TAREAS_RUN_TEST_URL=f"http://127.0.0.1:{srv.server_address[1]}", TAREAS_RUN_TEST_KEY="k", WAKE_STATE_DIR=tmp)
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ocio_run.py"), "--stack", "x"], env=env, capture_output=True, text=True)
rec = json.load(open(os.path.join(tmp, "x.ocio.run.json")))
chk("the runner starts one run with the fixed idle-time prompt carrying the unit it claimed", (r.returncode, len(seen), seen[0]["input"].startswith("[SYSTEM: idle-time work run"), "Unit #7: boceto de prueba" in seen[0]["input"], "already claimed" in seen[0]["input"]), (0, 1, True, True, True))
chk("the prompt forbids publishing, sending, spending and deleting", all(w in seen[0]["input"] for w in ("publish", "send", "spend", "delete")), True)
seen_n = len(seen)
r0 = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ocio_run.py"), "--stack", "z"], env=dict(env, OCIO_RUN_TEST_CLAIM="NADA"), capture_output=True, text=True)
chk("an empty queue starts no run at all and leaves no record", (r0.returncode, len(seen) == seen_n, os.path.exists(os.path.join(tmp, "z.ocio.run.json"))), (0, True, False))
chk("the record holds the run id and the start time, never a key or a text", (sorted(rec), rec["run_id"]), (["run_id", "stack", "started"], "r1"))
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ocio_run.py"), "--stack", "x", "--check"], env=env, capture_output=True, text=True)
chk("--check says finished for a completed run", r.stdout.strip(), "finished")
bad = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ocio_run.py"), "--stack", "X; rm"], env=env, capture_output=True, text=True)
chk("a bad stack name is refused", bad.returncode != 0, True)
env2 = dict(env, TAREAS_RUN_TEST_URL="http://127.0.0.1:1")
chk("an API that does not answer: exit 1, no record", (subprocess.run([sys.executable, "-I", os.path.join(HERE, "ocio_run.py"), "--stack", "y"], env=env2, capture_output=True, text=True).returncode, os.path.exists(os.path.join(tmp, "y.ocio.run.json"))), (1, False))

# the waker's two moves, on a shim (no docker)
w = load("waker", "waker.py")
w.CFG = {"cron": {"hold_seconds": 180}, "task": {"poll_seconds": 0, "hold_seconds": 600}}
w.STATE_DIR = tmp
class S: pass
for m in ("ocio_state", "ocio_save", "ocio_before_sleep", "ocio_poll_run", "ocio_run_busy"):
    setattr(S, m, getattr(w.Stack, m))
def shim(opt=True, **kw):
    s = S(); s.name = "x"; s.workdir = os.path.join(tmp, "wd"); s.ocio = o.conf({}, opt); s.ocio_run_file = os.path.join(tmp, "x.ocio.run.json")
    s.ocio_state_file = os.path.join(tmp, "x.ocio.json"); s.ocio_poll = (0.0, "unknown"); s.__dict__.update(kw); return s
os.makedirs(os.path.join(tmp, "wd", "ocio"), exist_ok=True)
json.dump({"items": [{"state": "pendiente"}]}, open(os.path.join(tmp, "wd", "ocio", "queue.json"), "w"))
for f in ("x.ocio.run.json", "x.ocio.json"):
    try: os.unlink(os.path.join(tmp, f))
    except OSError: pass
w.OCIO_RUN_SCRIPT = os.path.join(HERE, "ocio_run.py")
w.sys.executable = sys.executable
w.CONFIG = os.path.join(tmp, "stacks.json"); json.dump({"stacks": []}, open(w.CONFIG, "w"))
os.environ.update(TAREAS_RUN_TEST_URL=env["TAREAS_RUN_TEST_URL"], TAREAS_RUN_TEST_KEY="k", OCIO_RUN_TEST_CLAIM=UNIT)
s = shim(opt=None)
chk("a stack that did not opt in sleeps as always", s.ocio_before_sleep(), False)
s = shim()
seen.clear()
chk("opted in, queued work, nothing else: ONE unit is started instead of sleeping", (s.ocio_before_sleep(), len(seen)), (True, 1))
chk("the unit is counted for the day", s.ocio_state()["units"], 1)
chk("the fake API says completed at once: the unit is over and the stack is free", s.ocio_run_busy(), False)    # the fake API says completed at once: the run is over
chk("...and once it is over the record is gone and the gap clock is set", (os.path.exists(s.ocio_run_file), s.ocio_state().get("last_end", 0) > 0), (False, True))
# a run that is still going keeps the stack busy
class H2(H):
    def do_GET(self):
        out = json.dumps({"status": "running"}).encode(); self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
srv2 = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H2); threading.Thread(target=srv2.serve_forever, daemon=True).start()
os.environ["TAREAS_RUN_TEST_URL"] = f"http://127.0.0.1:{srv2.server_address[1]}"
s = shim(); json.dump({"stack": "x", "run_id": "r2", "started": time.time()}, open(s.ocio_run_file, "w"))
chk("a unit that is still running keeps the stack busy", s.ocio_run_busy(), True)
json.dump({"stack": "x", "run_id": "r2", "started": time.time() - 4000}, open(s.ocio_run_file, "w"))
chk("a unit older than unit_max_seconds no longer holds the stack", s.ocio_run_busy(), False)
os.makedirs(os.path.join(tmp, "wd", "ocio"), exist_ok=True)
open(os.path.join(tmp, "x.update_pending"), "w").write("{}")
for f in ("x.ocio.json",):
    try: os.unlink(os.path.join(tmp, f))
    except OSError: pass
chk("an image update waiting goes first: no unit", shim().ocio_before_sleep(), False)
os.unlink(os.path.join(tmp, "x.update_pending"))
os.environ["TAREAS_RUN_TEST_URL"] = "http://127.0.0.1:1"
s = shim(); r_ = s.ocio_before_sleep()
chk("the run cannot be asked for: sleep as always, and wait before trying again", (r_, s.ocio_state().get("retry_at", 0) > time.time()), (False, True))
print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
