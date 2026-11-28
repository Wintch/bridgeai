#!/usr/bin/env python3
"""ops/lib/lane_lock.sh: a second run on the same lane waits (and says so) instead of colliding, and gives up after its wait."""
import os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "lib", "lane_lock.sh")
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


tmp = tempfile.mkdtemp()
env = dict(os.environ, XDG_RUNTIME_DIR=tmp)
run = lambda body: subprocess.Popen(["bash", "-c", f". {LIB}; {body}"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
holder = run("lane_lock t 5; sleep 2")
time.sleep(0.4)
t0 = time.time()
second = run("lane_lock t 10 && echo got")
out, err = second.communicate(timeout=20)
waited = time.time() - t0
holder.wait(timeout=20)
check("a second run on the same lane waits for the first, says so, then goes on", second.returncode == 0 and "got" in out and waited >= 1.2 and "waiting" in err and "free" in err,
      (second.returncode, out, err, round(waited, 2)))
other = run("lane_lock other 1 && echo got")
o2, _ = other.communicate(timeout=10)
check("another lane is not held up", other.returncode == 0 and "got" in o2)
holder = run("lane_lock t 5; sleep 3")
time.sleep(0.4)
late = run("lane_lock t 1 || echo gave-up rc=$?")
o3, e3 = late.communicate(timeout=20)
holder.wait(timeout=20)
check("a run that waits past its limit gives up with rc 75 and says so", "gave-up rc=75" in o3 and "gave up" in e3, (o3, e3))
src = open(os.path.join(HERE, "run_selftests.sh")).read() + open(os.path.join(HERE, "pipeline.sh")).read()
check("the test battery and the pipeline's stages take their lanes", "lane_lock selftests" in src and "lane_lock deploy" in src and "lane_lock build" in src)
print("lane_lock_selftest: " + ("FAILED: " + ", ".join(fails) if fails else "all ok"))
sys.exit(1 if fails else 0)
