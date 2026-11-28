#!/usr/bin/env python3
"""Offline checks for ops/energy_report.py's arithmetic (sleeps from samples or events, awake windows, kWh). Run: python3 -I ops/energy_report_selftest.py"""
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import energy_report as er  # noqa: E402

FAIL = []


def chk(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


ts = [0, 300, 600, 3600, 3900, 4200, 10000]
chk("samples: a gap over 12 min is a sleep; 5-min steps are not", er.sleeps_from_samples(ts), [(600, 3600), (4200, 10000)])
ev = [(100, "down"), (200, "up"), (300, "down"), (350, "down"), (400, "up"), (500, "down")]
chk("events: down/up pairs, a repeated down ignored, an open sleep ends now", er.sleeps_from_events(ev, 600), [(100, 200), (300, 400), (500, 600)])
chk("awake windows between the sleeps, clipped to the range", er.awake_windows([(100, 200), (300, 400)], 50, 350), [(50, 100), (200, 300)])
chk("awake windows: no sleep, awake the whole range", er.awake_windows([], 0, 10), [(0, 10)])
s = er.summary([(0, 3600 * 10)], 0, 3600 * 20, 70, 3, 150)
chk("summary: 10 h of 20 asleep at 70/3 W = 0.67 kWh, a month at that rate, money", (s["asleep_h"], s["share"], s["kwh"], s["kwh_month"], s["money"]), (10.0, 50, 0.7, 24.1, 100))
chk("summary: no price, no money", er.summary([(0, 3600)], 0, 7200, 70, 3)["money"], None)
d = tempfile.mkdtemp(); f = os.path.join(d, "e.env")
open(f, "w").write('ENERGY_HOSTS="docker:55:2 gpu:80:4"\nKWH_PRICE=180\nOTHER=1\n')
w, p, measured = er.energy_conf(f)
chk("conf: watts per host class and the price from the env file", (w["docker"], w["gpu"], p, measured), ((55.0, 2.0), (80.0, 4.0), 180.0, True))
w, p, measured = er.energy_conf(os.path.join(d, "none.env"))
chk("conf: defaults without the file, flagged as not measured", (w["docker"], p, measured), ((70.0, 3.0), None, False))
print("energy_report_selftest: " + ("all ok" if not FAIL else "FAILED: " + "; ".join(FAIL)))
sys.exit(1 if FAIL else 0)
