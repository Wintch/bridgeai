#!/usr/bin/env python3
"""Offline test of the wake-time estimate and the warm-up check in waker.py (no docker, no server): usual boots vs the first wake on a new image.

Run from anywhere:  python3 ops/wake/estimate_selftest.py
(selftest.py next to it drives the whole waker against fake containers on the server; this one only needs python.)
"""
import importlib.util, json, os, sys, tempfile, threading, types
spec = importlib.util.spec_from_file_location("waker", os.path.join(os.path.dirname(os.path.abspath(__file__)), "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
tmp = tempfile.mkdtemp()
IMG = {"id": "sha256:aaa"}
w.docker = lambda *a, **k: types.SimpleNamespace(stdout=IMG["id"] + "\n", returncode=0)
class S:                      # just what the methods under test touch
    brain = "fake-brain"; state_file = os.path.join(tmp, "x.state.json"); state_lock = threading.Lock(); name = "x"
for m in ("image_id", "first_on_image", "boot_estimate", "record_boot", "load_state", "save_state", "boots", "warm"):
    setattr(S, m, getattr(w.Stack, m))
s = S()
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what)

chk(s.boot_estimate() == w.FIRST_BOOT_S, f"no state yet (first wake on an image): estimate {s.boot_estimate()} == {w.FIRST_BOOT_S}")
s.record_boot(138.8)
chk(s.load_state()["image"] == "sha256:aaa" and s.load_state()["boots_full"] == [138.8], "long boot goes to boots_full, image remembered")
chk(not s.first_on_image(), "after that boot the image is no longer 'first'")
chk(s.boot_estimate() == 60, "no usual boots yet: default 60")
for t in (9.5, 10.5, 11.0): s.record_boot(t)
chk(s.boot_estimate() == 10, f"usual boots: median 10 (got {s.boot_estimate()})")
IMG["id"] = "sha256:bbb"   # recreate with a new image
chk(s.first_on_image() and s.boot_estimate() == 138, f"new image: estimate from boots_full median ({s.boot_estimate()})")
s.record_boot(95.0)
chk(s.load_state()["boots_full"] == [138.8, 95.0] and s.load_state()["image"] == "sha256:bbb", "second full boot appended")
chk(s.boot_estimate() == 10, "same image again: back to the usual 10")
IMG["id"] = "sha256:ccc"; chk(s.boot_estimate() == 116, f"next new image: median of full boots 138.8/95 = {s.boot_estimate()}")
w.docker = lambda *a, **k: (_ for _ in ()).throw(OSError("no docker"))
chk(s.image_id() is None and not s.first_on_image(), "docker failing: no image id, never claims 'first'")
# warm(): the "Listo para trabajar" of a Telegram wake waits for Hermes's own "Turn machinery warmed" line in agent.log (INFO lines never
# reach `docker logs`), counting only lines after this container started (agent.log keeps the earlier boots)
import calendar, time as _t
STARTED = calendar.timegm(_t.strptime("2026-10-20 11:12:38", "%Y-%m-%d %H:%M:%S"))
S.container_started = lambda self: STARTED
S.warm = w.Stack.warm
LOG = {"out": ""}
calls = []
def fake(*a, **k):
    calls.append(a)
    return types.SimpleNamespace(stdout=LOG["out"], stderr="", returncode=0)
w.docker = fake
s = S()
OLD = "2026-10-20 10:50:52,048 INFO gateway.run: Turn machinery warmed in 10.5s (25 tool schema(s) materialized)\n"
NEW = "2026-10-20 11:12:52,048 INFO gateway.run: Turn machinery warmed in 10.5s (25 tool schema(s) materialized)\n"
LOG["out"] = "2026-10-20 11:12:43,618 INFO gateway.run: Gateway running with 3 platform(s)\n"
chk(not s.warm(), "warm: connected but not warmed yet -> False")
chk(calls and calls[0][:2] == ("exec", "fake-brain") and calls[0][-1].endswith("agent.log"), "warm: reads agent.log of the brain with docker exec")
LOG["out"] = OLD
chk(not s.warm(), "warm: the line from the PREVIOUS boot does not count")
LOG["out"] = OLD + NEW
chk(s.warm(), "warm: this boot's line counts even with an old one above it")
LOG["out"] = "garbage Turn machinery warmed\n"
chk(not s.warm(), "warm: unparsable timestamp is ignored, no crash")
S.container_started = lambda self: float("inf")
LOG["out"] = NEW
chk(not s.warm(), "warm: container start unknown -> False (the cap in waker.py ends the wait)")
S.container_started = lambda self: STARTED
w.docker = lambda *a, **k: (_ for _ in ()).throw(OSError("no docker"))
chk(not s.warm(), "warm: docker failing -> False")
print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
