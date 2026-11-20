#!/usr/bin/env python3
"""spread_report.py: the parent, each child and the total from a made-up log. No network: python3 spread_report_selftest.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spread_report as sr

fails = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")


ev = [
    {"ts": 100, "model": "A", "mode": "best", "result": "ok", "ptok": 1000, "tok": 50, "s": 2.0},
    {"ts": 101, "model": "A", "mode": "best", "result": "ok", "ptok": 1100, "tok": 60, "s": 2.5, "aux": True},     # a title: left out
    {"ts": 102, "model": "B", "mode": "spread", "result": "ok", "ptok": 500, "tok": 30, "s": 1.0, "sub": "c1"},
    {"ts": 103, "model": "B", "mode": "spread", "result": "ok", "ptok": 700, "tok": 40, "s": 1.5, "sub": "c1"},
    {"ts": 104, "model": "C", "mode": "spread", "result": "ok", "tok": 20, "s": 1.0, "sub": "c2"},                 # no usage block
    {"ts": 105, "model": "C", "mode": "spread", "result": "timeout", "s": 90, "sub": "c2"},
    {"ts": 200, "model": "A", "mode": "best", "result": "ok", "ptok": 9, "tok": 9, "s": 9.0},                     # outside the window
    {"ts": 106, "model": "V", "mode": "vision", "result": "ok", "ptok": 5, "tok": 5, "s": 1.0},                     # vision: left out
]
r = sr.report(ev, 100, 150)
check("parent counts the person's call only", (r["parent"]["calls"], r["parent"]["ptok"]), (1, 1000))
check("two children", sorted(r["children"]), ["c1", "c2"])
check("child sums", (r["children"]["c1"]["ptok"], r["children"]["c1"]["tok"], r["children"]["c1"]["seconds"]), (1200, 70, 2.5))
check("a failed call counts as a call, not as ok", (r["children"]["c2"]["calls"], r["children"]["c2"]["ok"]), (2, 1))
check("a call with no usage is flagged", r["children"]["c2"]["no_usage"], 1)
check("total = parent + children", (r["total"]["calls"], r["total"]["ptok"]), (5, 2200))
check("models among children", r["models_in_children"], 2)
check("the window cuts the log", sr.report(ev, 150, 300)["parent"]["calls"], 1)

with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "eval.jsonl")
    open(p, "w").write("not json\n" + "\n".join(__import__("json").dumps(e) for e in ev) + "\n")
    check("read skips a broken line", len(list(sr.read([p]))), len(ev))
    check("read of a missing file is not fatal", list(sr.read([os.path.join(d, "none")])), [])

print("\n".join(fails) or "spread_report_selftest: all ok")
sys.exit(1 if fails else 0)
