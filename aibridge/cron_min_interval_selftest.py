#!/usr/bin/env python3
"""patches/cron_min_interval.py: applied to a stand-in of Hermes's cron/jobs.py, then every schedule shape is tried. No Hermes, no network: python3 -I cron_min_interval_selftest.py"""
import importlib.util, os, subprocess, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
STAND_IN = '''
import re
from datetime import datetime, timedelta
from typing import Any, Dict
HAS_CRONITER = True
def _ensure_croniter(): return HAS_CRONITER
def _hermes_now(): return datetime(2026, 1, 1, 0, 0)
def _field(spec, value):
    return any((p == "*") or (p.startswith("*/") and value % int(p[2:]) == 0) or (p.isdigit() and int(p) == value) for p in spec.split(","))
class croniter:                      # minutes and hours only: enough to tell 'every minute' from 'daily'
    def __init__(self, expr, base): self.m, self.h = expr.split()[:2]; self.t = base
    def get_next(self, _):
        while True:
            self.t += timedelta(minutes=1)
            if _field(self.m, self.t.minute) and _field(self.h, self.t.hour): return self.t
def parse_duration(s):
    m = re.fullmatch(r"(\\d+)\\s*([mh])", s.strip())
    if not m: raise ValueError("bad duration " + s)
    return int(m.group(1)) * (60 if m.group(2) == "h" else 1)
def parse_schedule(schedule: str) -> Dict[str, Any]:
    """Parse a schedule string."""
    s = schedule.strip().lower()
    if s.startswith("in "): return {"kind": "once", "run_at": "x", "display": "once"}
    if s.startswith("every "): return {"kind": "interval", "minutes": parse_duration(s[6:]), "display": s}
    if len(s.split()) >= 5: return {"kind": "cron", "expr": s, "display": s}
    return {"kind": "interval", "minutes": parse_duration(s), "display": s}
'''
src = os.path.join(tmp, "jobs.py")
open(src, "w").write(STAND_IN)

fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

patch = os.path.join(here, "patches", "cron_min_interval.py")
r = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
check("the patch applies once", r.returncode == 0 and "patched" in r.stdout)
r2 = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
check("applying it again is a no-op", r2.returncode == 0 and "already patched" in r2.stdout and open(src).read().count("aibridge-patch: cron_min_interval") == 1)
bad = os.path.join(tmp, "other.py"); open(bad, "w").write("def something(): pass\n")
r3 = subprocess.run([sys.executable, "-I", patch, bad], capture_output=True, text=True)
check("a Hermes that no longer has the function fails the build loudly", r3.returncode != 0 and "expected 1 match, found 0" in (r3.stderr + r3.stdout))
dup = os.path.join(tmp, "dup.py"); open(dup, "w").write(STAND_IN + STAND_IN)
r4 = subprocess.run([sys.executable, "-I", patch, dup], capture_output=True, text=True)
check("two matches fail too", r4.returncode != 0 and "found 2" in (r4.stderr + r4.stdout))
check("the patched file still compiles", subprocess.run([sys.executable, "-m", "py_compile", src]).returncode == 0)

spec = importlib.util.spec_from_file_location("jobs", src)
jobs = importlib.util.module_from_spec(spec); spec.loader.exec_module(jobs)
os.environ.pop("AIBRIDGE_CRON_MIN_MINUTES", None)

def refused(s):
    try:
        jobs.parse_schedule(s); return None
    except ValueError as e:
        return str(e)

for s in ("every 1m", "1m", "every 2m", "every 4m"):
    check(f"{s!r} is refused", refused(s) is not None)
msg = refused("every 1m") or ""
check("the message says the minimum, the actual period and what to use", "every 5 minutes" in msg and "every 1.0" in msg and "'every 5m'" in msg)
for s in ("every 5m", "5m", "every 30m", "every 2h", "every 180m"):
    check(f"{s!r} is accepted and unchanged", refused(s) is None and jobs.parse_schedule(s)["kind"] == "interval")
check("a one-shot 'in 1m' is not touched", refused("in 1m") is None and jobs.parse_schedule("in 1m")["kind"] == "once")
check("'* * * * *' (every minute) is refused", refused("* * * * *") is not None)
check("'*/2 * * * *' is refused", refused("*/2 * * * *") is not None)
check("'0,1 * * * *' is refused although its first gap after midnight is 1 minute only once an hour", refused("0,1 * * * *") is not None)
check("'*/5 * * * *' is accepted", refused("*/5 * * * *") is None)
check("'0 9 * * *' (daily) is accepted", refused("0 9 * * *") is None and jobs.parse_schedule("0 9 * * *")["kind"] == "cron")
jobs.HAS_CRONITER = False
check("without croniter a cron expression is not guessed at (accepted, the interval path still guards)", refused("* * * * *") is None and refused("every 1m") is not None)
jobs.HAS_CRONITER = True
os.environ["AIBRIDGE_CRON_MIN_MINUTES"] = "0"
check("AIBRIDGE_CRON_MIN_MINUTES=0 turns the floor off", refused("every 1m") is None)
os.environ["AIBRIDGE_CRON_MIN_MINUTES"] = "15"
check("AIBRIDGE_CRON_MIN_MINUTES=15 raises the floor", refused("every 10m") is not None and refused("every 15m") is None)
os.environ["AIBRIDGE_CRON_MIN_MINUTES"] = "abc"
check("a broken value falls back to 5", refused("every 4m") is not None and refused("every 5m") is None)

print("\n".join(fails) or "cron_min_interval_selftest: all ok")
sys.exit(1 if fails else 0)
