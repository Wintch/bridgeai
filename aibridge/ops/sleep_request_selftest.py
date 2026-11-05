#!/usr/bin/env python3
"""Offline test of the on-demand sleep decision in ops/wake/waker.py (no docker, no server): python3 ops/sleep_request_selftest.py"""
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("waker", os.path.join(os.path.dirname(os.path.abspath(__file__)), "wake", "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
ok = True
def chk(got, want, what):
    global ok; ok &= got == want; print(("ok   " if got == want else f"FAIL (got {got!r}, want {want!r}) ") + what)

N = 10_000.0
d = w.sleep_decision
chk(d(None, N, False, False), "none", "no request: nothing to do")
chk(d({"x": 1}, N, False, False), "none", "garbage in the file is not a request")
chk(d({"ts": N - 5, "mode": "ahora"}, N, True, False), "wait", "ahora: the turn that asked is still answering -> wait")
chk(d({"ts": N - 5, "mode": "ahora"}, N, False, False), "sleep", "ahora: turn over, nothing busy -> sleep")
chk(d({"ts": N - 5, "mode": "ahora", "force": True}, N, False, True), "sleep", "ahora forced: busy work does not stop it")
chk(d({"ts": N - 5, "mode": "ahora", "force": False}, N, False, True), "wait", "ahora not forced: work that started after the check -> wait")
chk(d({"ts": N - 300, "mode": "ahora", "force": False}, N, False, True), "drop", "ahora not forced: still busy after the grace -> drop, never cut unasked")
chk(d({"ts": N - 300, "mode": "ahora"}, N, True, False), "sleep", "ahora: a turn stuck for more than the grace does not hold the stop")
chk(d({"ts": N - 5, "mode": "cuando-termine"}, N, False, True), "wait", "cuando-termine: busy -> wait")
chk(d({"ts": N - 5, "mode": "cuando-termine"}, N, True, False), "wait", "cuando-termine: turn running -> wait")
chk(d({"ts": N - 5, "mode": "cuando-termine"}, N, False, False), "sleep", "cuando-termine: idle -> sleep at once (not after 10 minutes)")
chk(d({"ts": N - 2000, "mode": "cuando-termine"}, N, False, False), "drop", "a request older than 15 minutes is stale")
chk(d({"ts": N + 500, "mode": "ahora"}, N, False, False), "drop", "a request dated in the future is not trusted")
chk("subs-fetch" in w.Stack.DETACHED_SCRIPT and "yt-dlp" in w.Stack.DETACHED_SCRIPT, True, "detached-job scan knows subs-fetch and yt-dlp")
compile(w.Stack.DETACHED_SCRIPT.replace("MAXMIN", "360"), "detached", "exec")
print("sleep_request_selftest: all ok" if ok else "sleep_request_selftest: FAILED")
sys.exit(0 if ok else 1)
