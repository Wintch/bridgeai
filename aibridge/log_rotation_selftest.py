#!/usr/bin/env python3
"""Self-test of append_line (gateway.py, router.py, content_guard.py): JSON lines are appended, and a log past LOG_MAX
moves to NAME.1.jsonl before the next line, keeping one older generation. Run: python3 -I log_rotation_selftest.py
"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


for mod in ("gateway", "router", "content_guard"):
    m = load(mod + "_t", os.path.join(HERE, mod + ".py"))
    d = tempfile.mkdtemp()
    p = os.path.join(d, ".gateway-log.jsonl")
    m.LOG_MAX = 300
    for i in range(5):
        m.append_line(p, {"i": i, "pad": "x" * 50})
    lines = [json.loads(x) for x in open(p)]
    check(f"{mod}: lines are appended as JSON", [x["i"] for x in lines] == [0, 1, 2, 3, 4], lines)
    check(f"{mod}: under the limit nothing rotates", not os.path.exists(os.path.join(d, ".gateway-log.1.jsonl")))
    m.append_line(p, {"i": 5})
    old = os.path.join(d, ".gateway-log.1.jsonl")
    check(f"{mod}: past the limit the log moves to NAME.1.jsonl first",
          os.path.exists(old) and [json.loads(x)["i"] for x in open(old)] == [0, 1, 2, 3, 4], os.listdir(d))
    check(f"{mod}: the new line starts a fresh log", [json.loads(x)["i"] for x in open(p)] == [5])
    for i in range(6, 12):
        m.append_line(p, {"i": i, "pad": "x" * 50})
    gens = sorted(os.listdir(d))
    check(f"{mod}: only one older generation is kept", gens == [".gateway-log.1.jsonl", ".gateway-log.jsonl"], gens)
    m.append_line(os.path.join(d, "missing-dir", "x.jsonl"), {"i": 0})
    check(f"{mod}: an unwritable path is silent", True)

print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
