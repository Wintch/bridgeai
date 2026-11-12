#!/usr/bin/env python3
"""Offline check of gates_build in gateways_sync.py. Run: python3 -I gateways_sync_gates_selftest.py

A host in a stack's "gpu" list with a gate_token gets a gate entry; a host only in its "voice" list does not (the gate has one token per
host, so handing it over would let a speech-only stack start the other services); no token or a bad port means no entry."""
import contextlib, importlib.util, io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("gs", os.path.join(HERE, "gateways_sync.py"))
gs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gs)
FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


master = {"hosts": {"a": {"addr": "10.0.0.1", "gate_token": "ta"},
                    "b": {"addr": "10.0.0.2", "gate_token": "tb", "gate_port": 9000},
                    "c": {"addr": "10.0.0.3"},
                    "d": {"addr": "10.0.0.4", "gate_token": "td", "gate_port": 99999}},
          "stacks": {"full": {"gpu": ["a", "b", "c", "d"]},
                     "speech": {"voice": ["a", "b"]},
                     "mixed": {"gpu": ["b"], "voice": ["a"]}}}
with contextlib.redirect_stdout(io.StringIO()):
    full, speech, mixed = (gs.gates_build(master, n) for n in ("full", "speech", "mixed"))
check("gpu hosts with a token get a gate (default and custom port); no token or a bad port: none",
      full, {"a": {"url": "http://10.0.0.1:8700", "token": "ta"}, "b": {"url": "http://10.0.0.2:9000", "token": "tb"}})
check("a stack with hosts only in its voice list gets no gate token", speech, {})
check("a voice-only host next to a gpu host stays out", mixed, {"b": {"url": "http://10.0.0.2:9000", "token": "tb"}})
m2 = {"hosts": {"g": {"addr": "10.0.0.9", "transcode": 8610, "video": 8670, "image": 8660, "video_token": "v", "gate_token": "tg"}},
      "stacks": {"lim": {"gpu": ["g"], "gpu_only": {"g": ["transcode"]}}, "all": {"gpu": ["g"]}, "bad": {"gpu": ["g"], "gpu_only": {"g": "transcode"}},
                "typo": {"gpu": ["g"], "gpu_only": {"g": ["transcoder"]}}, "notdict": {"gpu": ["g"], "gpu_only": ["g"]}}}
notes = {}
for n in ("lim", "all", "bad", "typo", "notdict"):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        built = gs.build(m2, n)
    notes[n] = (built, buf.getvalue())
lim, allk, bad = (notes[n][0] for n in ("lim", "all", "bad"))
check("gpu_only keeps only the listed services of that host", (len(lim.get("transcode", [])), lim.get("video", []), lim.get("image", [])), (1, [], []))
check("gpu_only still hands over the host's gate", sorted(lim.get("gates", {})), ["g"])
check("without gpu_only every service of the host is listed", (len(allk["transcode"]), len(allk["video"]), len(allk["image"])), (1, 1, 1))
check("a gpu_only value that is not a list allows nothing of that host", (bad.get("transcode", []), bad.get("video", [])), ([], []))
check("a gpu_only that is not a list says so and leaves the host empty", ("must be a list" in notes["bad"][1], "leaves no service" in notes["bad"][1]), (True, True))
check("a gpu_only with an unknown kind says so", ("unknown kind 'transcoder'" in notes["typo"][1], notes["typo"][0].get("transcode", [])), (True, []))
check("a gpu_only that is not an object says it is ignored (the host keeps its services)", ("must be an object" in notes["notdict"][1], len(notes["notdict"][0]["video"])), (True, 1))
check("a valid gpu_only prints no note", notes["lim"][1], "")
print("gateways_sync_gates_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
