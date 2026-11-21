#!/usr/bin/env python3
"""Offline test of the waker's on_sleep.d hooks: they run after a stack was stopped (never inside the stop, in a thread), sorted, with WAKE_NAME,
one at a time per stack, a failing or slow hook does not stop the next, non-executable files are ignored, and sleep_brain starts them only when
the brain really went down.

Run from anywhere:  python3 -I ops/wake/sleep_hooks_selftest.py
"""
import importlib.util, os, stat, sys, tempfile, threading, time
import atexit as _a, shutil as _s, signal as _g
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_a.register(_s.rmtree, tempfile.tempdir, True)
_g.signal(_g.SIGTERM, lambda *_: sys.exit(143))
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("waker", os.path.join(HERE, "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

tmp = tempfile.mkdtemp()
hooks = os.path.join(tmp, "on_sleep.d"); os.makedirs(hooks)
out = os.path.join(tmp, "ran.txt")
def hook(name, body, mode=0o755):
    p = os.path.join(hooks, name); open(p, "w").write("#!/bin/bash\n" + body); os.chmod(p, mode); return p
hook("10-first", f'echo "first $WAKE_NAME" >> {out}; echo "line one"; echo "done first"\n')
hook("20-fails", f'echo "second" >> {out}; exit 7\n')
hook("30-last", f'echo "third $WAKE_NAME" >> {out}\n')
hook("40-not-exec", f'echo "NEVER" >> {out}\n', 0o644)
open(os.path.join(hooks, "README.md"), "w").write("not a hook")
w.SLEEP_HOOKS_DIR = hooks
logs = []
w.log = lambda msg, *a, **k: logs.append(msg)
class S:
    pass
S.run_sleep_hooks = w.Stack.run_sleep_hooks
s = S(); s.name = "demo"
s.run_sleep_hooks()
ran = open(out).read().splitlines()
chk(ran == ["first demo", "second", "third demo"], "hooks run sorted, with WAKE_NAME; a failing one does not stop the next; a non-executable file and the README are ignored")
chk(any("sleep hook 20-fails: rc=7" in m for m in logs) and any("sleep hook 10-first: rc=0 done first" in m for m in logs), "rc and the last line of each hook go to the journal")
alerts = []
w.ops = lambda *a, **k: alerts.append(a)
hook("50-boom", 'exit 3\n'); s.run_sleep_hooks()
chk(alerts == [], "a hook never raises an ops alert (it reviews, it does not keep anything alive)")
# one at a time per stack
hook("05-slow", f'sleep 1; echo "slow" >> {out}\n')
for n in ("10-first", "20-fails", "30-last", "50-boom"):
    os.chmod(os.path.join(hooks, n), 0o644)
open(out, "w").close()
t = threading.Thread(target=s.run_sleep_hooks); t.start(); time.sleep(0.3)
s.run_sleep_hooks()   # a second call while the first still runs returns at once
t.join()
chk(open(out).read().splitlines() == ["slow"], "a second request while one runs does nothing (one run at a time per stack)")
# a hook that hangs past the limit is killed and logged
w.SLEEP_HOOK_TIMEOUT = 1
for n in os.listdir(hooks):
    if n != "README.md": os.chmod(os.path.join(hooks, n), 0o644)
hook("06-hang", 'sleep 20\n'); hook("07-after", f'echo "after" >> {out}\n')
open(out, "w").close(); logs.clear(); t0 = time.time(); s.run_sleep_hooks()
chk(time.time() - t0 < 6 and any("06-hang failed: TimeoutExpired" in m for m in logs) and open(out).read().splitlines() == ["after"], "a hook that hangs is killed at the limit and the next one still runs")
# a missing folder is not an error
w.SLEEP_HOOKS_DIR = os.path.join(tmp, "nope")
s.run_sleep_hooks()
chk(True, "no on_sleep.d folder: nothing happens")
# sleep_brain starts the hooks only after a real stop, in a thread
src = open(os.path.join(HERE, "waker.py")).read()
i = src.index("def sleep_brain"); j = src.index("def start_sleep_hooks"); k = src.index("def run_sleep_hooks")
body, starter = src[i:j], src[j:k]
chk('getattr(self, "start_sleep_hooks", None)' in body and body.index("self.stopping = False") < body.index("start_sleep_hooks"),
    "sleep_brain: the hooks are started after the stop finished (and an object without the method, as in the other waker tests, skips them)")
chk("threading.Thread(target=self.run_sleep_hooks, daemon=True).start()" in starter and "not self.brain_up()" in starter and "os.path.isdir(SLEEP_HOOKS_DIR)" in starter,
    "start_sleep_hooks: a thread, only when the brain is down and the folder exists")
class T2:
    start_sleep_hooks = w.Stack.start_sleep_hooks
    def __init__(self, up): self.up, self.started = up, []
    def brain_up(self): return self.up
    def run_sleep_hooks(self): self.started.append(1)
w.SLEEP_HOOKS_DIR = hooks
for up, expect in ((False, 1), (True, 0)):
    t2 = T2(up); t2.start_sleep_hooks(); time.sleep(0.3)
    chk(len(t2.started) == expect, "start_sleep_hooks: brain %s -> hooks %s" % ("still up" if up else "down", "not started" if not up is False else "started") if False else ("start_sleep_hooks: brain down -> hooks start" if not up else "start_sleep_hooks: brain still up -> no hooks"))
# the shipped hook folder
real = os.path.join(HERE, "on_sleep.d")
chk(os.path.isdir(real) and os.path.exists(os.path.join(real, "README.md")) and os.access(os.path.join(real, "60-analyst"), os.X_OK), "on_sleep.d ships with the analyst hook and its README")

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
