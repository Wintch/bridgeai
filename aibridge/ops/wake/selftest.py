#!/usr/bin/env python3
"""Self-test of waker.py against three FAKE stacks (tiny containers), never touching a real stack.

Run on the server:  python3 ~/aibridge/ops/wake/selftest.py
It creates selftest-{a,b,c}-{web,ui,brain} containers, starts the real waker.py with short timings and a fake
MemAvailable, drives it over HTTP, checks docker state, and removes everything. Exit code 0 = all checks passed.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = "aibridge-hermes-base:latest"
NAMES = ["a", "b", "c"]
PORT = {"a": 3191, "b": 3192, "c": 3193}
TMP = tempfile.mkdtemp(prefix="wake-selftest-")
MEM = os.path.join(TMP, "mem")
LOG = os.path.join(TMP, "waker.log")
NOSLEEP = os.path.join(HERE, "NO_SLEEP")
fails = []


def sh(*a, check=False):
    return subprocess.run(list(a), capture_output=True, text=True, check=check)


def running(n):
    return sh("docker", "inspect", "-f", "{{.State.Running}}", n).stdout.strip() == "true"


def check(ok, what):
    print(("PASS " if ok else "FAIL ") + what, flush=True)
    if not ok:
        fails.append(what)


def until(cond, timeout, step=0.5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


def get(port, path="/", nav=True):
    h = {"Sec-Fetch-Mode": "navigate", "Accept": "text/html"} if nav else {"Accept": "application/json"}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def state(x):
    return json.loads(get(PORT[x], "/__wake/status")[1])["state"]


def log_lines():
    return open(LOG).read().splitlines() if os.path.exists(LOG) else []


def make_fakes():
    srv = "mkdir -p /srv && echo ok > /srv/health && cd /srv && exec python3 -m http.server {port}"
    for x in NAMES:
        sh("docker", "rm", "-f", f"selftest-{x}-web", f"selftest-{x}-ui", f"selftest-{x}-brain")
        sh("docker", "run", "-d", "--name", f"selftest-{x}-web", "nginx:alpine", check=True)
        sh("docker", "create", "--init", "--name", f"selftest-{x}-ui", IMAGE, "sh", "-c", srv.format(port=8080), check=True)
        sh("docker", "create", "--init", "--name", f"selftest-{x}-brain", IMAGE, "sh", "-c", srv.format(port=8642), check=True)


def put_jobs(x, jobs):
    d = tempfile.mkdtemp(dir=TMP)
    os.makedirs(os.path.join(d, "root/.hermes/cron"))
    json.dump({"jobs": jobs}, open(os.path.join(d, "root/.hermes/cron/jobs.json"), "w"))
    sh("docker", "cp", d + "/.", f"selftest-{x}-brain:/", check=True)


def cleanup(proc=None):
    if proc:
        proc.terminate()
    for x in NAMES:
        sh("docker", "rm", "-f", f"selftest-{x}-web", f"selftest-{x}-ui", f"selftest-{x}-brain")
    if os.path.exists(NOSLEEP):
        os.remove(NOSLEEP)


def main():
    make_fakes()
    long_ago = "2020-01-01T00:00:00+00:00"
    put_jobs("a", [{"id": "ja", "name": "daily-a", "enabled": True, "next_run_at": long_ago}])
    put_jobs("b", [{"id": "jb", "name": "daily-b", "enabled": True, "next_run_at": long_ago}])
    put_jobs("c", [{"id": "jc", "name": "jobwatch", "enabled": True, "next_run_at": long_ago}])
    open(MEM, "w").write("4000")
    stacks = []
    for i, x in enumerate(NAMES):
        stacks.append({"name": x, "bind": "127.0.0.1", "port": PORT[x], "front": f"selftest-{x}-web",
                       "web": [f"selftest-{x}-ui"], "brain": f"selftest-{x}-brain",
                       "idle_web": 8 if x == "c" else 600, "idle_brain": 8 if x == "c" else 600,
                       "est_brain_mb": 400, "est_web_mb": 100})
    cfg = {"reserve_mb": 1000, "critical_mb": 400, "max_awake": 2, "evict_min_idle_seconds": 15,
           "cron": {"min_interval_min": 0.3, "slot_seconds": 20, "stack_offset_seconds": 5, "hold_seconds": 10}, "stacks": stacks}
    cfgp = os.path.join(TMP, "stacks.json")
    json.dump(cfg, open(cfgp, "w"))
    # the cron planner would wake a/b right away (their fake jobs are overdue): park them for the first scenarios
    for x in ("a", "b"):
        put_jobs(x, [])
    env = dict(os.environ, WAKE_CONFIG=cfgp, WAKE_TICK="2", WAKE_TEST_MEMINFO=MEM)
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "waker.py")], env=env,
                            stdout=open(LOG, "w"), stderr=subprocess.STDOUT)
    try:
        time.sleep(2)
        # 1. a visit wakes the stack; background traffic does not
        code, body = get(PORT["b"], "/api/x", nav=False)
        time.sleep(1)
        check(code == 503 and not running("selftest-b-brain"), "background request answers 503 and does NOT wake")
        code, body = get(PORT["a"])
        check(code == 503 and "Despertando" in body, "navigation gets the loading page")
        check(until(lambda: state("a") == "ready", 30), "stack A wakes (web + brain) and reports ready")
        # 2. idle sleep: C wakes, then web sleeps, then brain sleeps
        get(PORT["c"])
        check(until(lambda: state("c") == "ready", 30), "stack C wakes")
        check(until(lambda: not running("selftest-c-ui"), 40), "C web sleeps after its idle time")
        check(until(lambda: not running("selftest-c-brain"), 40), "C brain sleeps after the web (reverse order)")
        # 3. NO_SLEEP switch
        get(PORT["c"])
        until(lambda: state("c") == "ready", 30)
        open(NOSLEEP, "w").close()
        time.sleep(22)
        check(running("selftest-c-ui") and running("selftest-c-brain"), "NO_SLEEP keeps an idle stack awake")
        os.remove(NOSLEEP)
        check(until(lambda: not running("selftest-c-brain"), 45), "removing NO_SLEEP lets it sleep again")
        # 4. max_awake=2: with A and B awake, C must evict the least recently used idle stack
        get(PORT["a"])
        check(until(lambda: state("a") == "ready", 30), "stack A is awake again")
        time.sleep(1)
        get(PORT["b"])
        check(until(lambda: state("b") == "ready", 30), "stack B wakes (2 awake = max_awake)")
        get(PORT["c"])
        time.sleep(2)
        check(not running("selftest-c-brain"), "C waits while A and B are both recently active (nothing evictable yet)")
        check(until(lambda: running("selftest-c-brain"), 40), "C starts once an idle stack was evicted")
        check(any("[a] evicted by the RAM guard" in l for l in log_lines()), "the LEAST recently used stack (A) was the one evicted")
        check(not running("selftest-a-brain") and not running("selftest-a-ui"), "evicted stack stopped web and brain")
        until(lambda: not running("selftest-c-brain"), 40)   # let C go back to sleep by itself
        # 5. low RAM: wake must wait, never start anyway
        open(MEM, "w").write("900")
        get(PORT["a"])
        time.sleep(8)
        check(not running("selftest-a-brain"), "with MemAvailable below reserve, A does NOT start (it waits)")
        check(until(lambda: any("evicted by the RAM guard" in l for l in log_lines()[-30:]) and not running("selftest-b-brain"), 30),
              "idle stacks were evicted trying to make room")
        check(not running("selftest-a-brain"), "...and A still did not start while memory stayed low")
        open(MEM, "w").write("4000")
        check(until(lambda: running("selftest-a-brain"), 30), "A starts as soon as memory is available again")
        # 6. watchdog: critical memory stops idle stacks
        get(PORT["b"])
        until(lambda: running("selftest-b-brain"), 30)
        time.sleep(7)
        open(MEM, "w").write("300")
        check(until(lambda: not running("selftest-a-brain") and not running("selftest-b-brain"), 40),
              "below critical_mb the watchdog stops the idle stacks")
        open(MEM, "w").write("4000")
        # 7. crons: overdue jobs wake sleeping stacks one at a time, staggered, rate limited; jobwatch ignored
        put_jobs("a", [{"id": "ja", "name": "daily-a", "enabled": True, "next_run_at": "2020-01-01T00:00:00+00:00"}])
        put_jobs("b", [{"id": "jb", "name": "daily-b", "enabled": True, "next_run_at": "2020-01-01T00:00:00+00:00"}])
        until(lambda: not running("selftest-a-brain") and not running("selftest-b-brain"), 20)
        t0 = time.time()
        check(until(lambda: sum("waking for a scheduled cron" in l for l in log_lines()) >= 2, 90),
              "both overdue crons wake their (sleeping) stacks")
        wakes = [l for l in log_lines() if "waking for a scheduled cron" in l]
        stamp = lambda l: time.mktime(time.strptime(l[:19], "%Y-%m-%d %H:%M:%S"))
        gap = abs(stamp(wakes[1]) - stamp(wakes[0])) if len(wakes) > 1 else 0
        check(gap >= 15, f"cron wakes are staggered, not simultaneous (gap {gap:.0f}s, slot 20s)")
        check(not any("[c] waking for a scheduled cron" in l for l in log_lines()), "a job named jobwatch never wakes its stack")
        first_a = next((stamp(l) for l in wakes if "[a]" in l), 0)
        until(lambda: sum("[a] waking for a scheduled cron" in l for l in log_lines()) >= 2, 60)
        again = [stamp(l) for l in log_lines() if "[a] waking for a scheduled cron" in l]
        check(len(again) < 2 or again[1] - again[0] >= 17, "the same cron is not woken again before min_interval (18s)")
        check(until(lambda: not running("selftest-a-brain"), 40), "after the cron's hold time the stack sleeps again")
    finally:
        cleanup(proc)
        print("\n--- waker log (tail) ---")
        print("\n".join(log_lines()[-25:]))
    print("\nRESULT:", "ALL PASSED" if not fails else f"{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
