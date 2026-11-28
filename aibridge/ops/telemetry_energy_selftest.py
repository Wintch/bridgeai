#!/usr/bin/env python3
"""Offline checks for the daily report's energy and inactivity lines (ops/telemetry.py). Run: python3 -I ops/telemetry_energy_selftest.py"""
import importlib.util, json, os, sqlite3, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix="selftest-energy-")
os.environ["OPS_ENV"] = os.path.join(tmp, "ops.env")
spec = importlib.util.spec_from_file_location("telemetry", os.path.join(HERE, "telemetry.py"))
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
FAIL = []


def chk(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


H = 3600
ts = [0, 300, 600, 600 + 4 * H, 600 + 4 * H + 300]           # one 4-hour sleep
h, span, kwh = t.sleep_saving(ts, 0, 600 + 4 * H + 300, 70, 3)
chk("sleep_saving: a 4 h gap counts, 5-min steps do not; kWh at 70/3 W", (round(h, 2), round(span, 2), round(kwh, 3)), (4.0, 4.25, 0.268))
h, span, kwh = t.sleep_saving([0, 300], 0, 300 + 2 * H, 70, 3)
chk("sleep_saving: asleep since the last sample (still asleep at report time) counts too", round(h, 2), 2.0)
chk("sleep_saving: too few samples, nothing", t.sleep_saving([5], 0, 10, 70, 3), (0.0, 0.0, 0.0))
c = sqlite3.connect(":memory:"); c.execute("create table host (ts, mem_avail_mb, swap_used_mb, disk_pct)")
now = time.time()
for x in (now - 6 * H, now - 6 * H + 300, now - 2 * H, now - 2 * H + 300, now - 60):
    c.execute("insert into host values (?,?,?,?)", (x, 1, 1, 1))
line = t.energy_line(c, now - 6 * H, now)
chk("energy_line: hours, share, kWh, and 'estimate' while ENERGY_DOCKER_W is not set", (len(line), "slept" in line[0], "estimate at 70/3 W" in line[0]), (1, True, True))
open(os.environ["OPS_ENV"], "w").write('ENERGY_DOCKER_W="55:2"\nARCHIVE_EXEMPT="ops boss"\n')
line = t.energy_line(c, now - 6 * H, now)
chk("energy_line: measured watts from ops.env, no estimate note", "estimate" in line[0], False)
wd = os.path.join(tmp, "wake"); os.makedirs(wd)
json.dump({"human_ts": now - 9 * 86400}, open(os.path.join(wd, "old.state.json"), "w"))
json.dump({"human_ts": now - 86400}, open(os.path.join(wd, "fresh.state.json"), "w"))
json.dump({}, open(os.path.join(wd, "never.state.json"), "w"))
json.dump({"human_ts": now - 30 * 86400}, open(os.path.join(wd, "ops.state.json"), "w"))
got = t.inactive_line([{"name": n} for n in ("old", "fresh", "never", "ops", "nofile")], now, wd)
chk("inactive_line: 7+ days and never used are listed, a fresh one and an exempt one are not", got,
    ["• 7+ days without use: old (9 days), never (no use on record), nofile (no use on record) — archive by hand: ops/archive_stack.sh"])
chk("inactive_line: nobody to list, no line", t.inactive_line([{"name": "fresh"}], now, wd), [])
print("telemetry_energy_selftest: " + ("all ok" if not FAIL else "FAILED: " + "; ".join(FAIL)))
sys.exit(1 if FAIL else 0)
