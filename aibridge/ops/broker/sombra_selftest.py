#!/usr/bin/env python3
"""Offline test of ops/broker/sombra.py's recording: bounded lines for any payload, hostile JSON never raises, rotation.
Run from anywhere:  python3 -I ops/broker/sombra_selftest.py
"""
import importlib.util, json, os, sys, tempfile
import atexit as _st_atexit, shutil as _st_shutil
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
os.environ["STATE_DIRECTORY"] = tempfile.tempdir
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sombra", os.path.join(HERE, "sombra.py"))
sb = importlib.util.module_from_spec(spec); spec.loader.exec_module(sb)
sb.log = lambda m: logs.append(m); logs = []
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)
def lines():
    return [json.loads(l) for l in open(sb.OUT)] if os.path.exists(sb.OUT) else []

sb.record("ev.wake.pve4.telegram", "NATS/1.0\r\nNats-Msg-Id: tg.x.5\r\n\r\n", b'{"bot": "x", "n": 1}')
l = lines()[-1]
chk(l["subject"] == "ev.wake.pve4.telegram" and l["msg_id"] == "tg.x.5" and l["data"] == {"bot": "x", "n": 1}, "a normal event: subject, msg id and payload recorded")
for p in (b'{"a":"\\ud800"}', b"[" * 200000, json.dumps("y" * 900000).encode(), json.dumps(list(range(200000))).encode(), b"\xff\xfe not json"):
    sb.record("ev.x", "", p)
ls = lines()
chk(len(ls) == 6 and all(len(json.dumps(x)) < 1200 for x in ls), f"hostile payloads (lone surrogate, deep nesting, huge string, huge list, bad bytes): recorded, every line bounded ({len(ls)} lines)")
chk(not any("skipped" in m for m in logs), "none of them needed the skip path")
sb.ROTATE_BYTES = 200
for i in range(10):
    sb.record("ev.y", "", b'{"i": %d}' % i)
chk(os.path.exists(sb.OUT + ".1") and not os.path.exists(sb.OUT + ".4"), "rotation: old files kept, at most KEEP of them")
print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
