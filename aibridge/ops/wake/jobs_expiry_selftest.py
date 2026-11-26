#!/usr/bin/env python3
"""Offline test of the waker's registered-jobs count (waker.py: Stack.JOBS_SCRIPT, run inside the container by pending_jobs): a job past its
own timeout no longer keeps the stack awake; one within it, or one that cannot be read, still does.

Run from anywhere:  python3 -I ops/wake/jobs_expiry_selftest.py
"""
import importlib.util, json, os, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("waker", os.path.join(HERE, "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
ok = True
def chk(c, what):
    global ok; ok &= bool(c); print(("ok   " if c else "FAIL ") + what, flush=True)

d = tempfile.mkdtemp(prefix="jobs-selftest-")
count = lambda: int(subprocess.run([sys.executable, "-I", "-c", w.Stack.JOBS_SCRIPT, d], capture_output=True, text=True).stdout.strip())
now = int(time.time())
chk(count() == 0, "no jobs: 0")
json.dump({"watch": "escritorio", "started": now - 7200, "timeout_min": 1440}, open(os.path.join(d, "a.json"), "w"))
chk(count() == 1, "a job within its timeout counts")
json.dump({"watch": "escritorio", "started": now - 90000, "timeout_min": 1440}, open(os.path.join(d, "a.json"), "w"))
chk(count() == 0, "a job past its timeout (25 h of 24) no longer counts")
json.dump({"started": str(now - 60)}, open(os.path.join(d, "b.json"), "w"))
chk(count() == 1, "no timeout_min: 24 h by default (started as a string works too)")
open(os.path.join(d, "c.json"), "w").write("{not json")
chk(count() == 2, "a file that cannot be read still counts, as before")
open(os.path.join(d, "d.txt"), "w").write("x")
chk(count() == 2, "only .json files are jobs")
print("jobs_expiry_selftest: " + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
