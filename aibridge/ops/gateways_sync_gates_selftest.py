#!/usr/bin/env python3
"""Offline check of gates_build in gateways_sync.py. Run: python3 -I gateways_sync_gates_selftest.py

A host in a stack's "gpu" list with a gate_token gets a gate entry; a host only in its "voice" list does not (the gate has one token per
host, so handing it over would let a speech-only stack start the other services); no token or a bad port means no entry."""
import contextlib, importlib.util, io, json, os, sys

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
# lugares: the games/power control of a desktop host, a separate list and token from "gpu"/"gate_token"
lm = {"hosts": {"pc": {"addr": "10.0.0.7", "host_token": "hp", "gate_port": 8700, "gate_token": "gp"},
                "nolist": {"addr": "10.0.0.8", "host_token": "hn"}, "notoken": {"addr": "10.0.0.9"}, "badport": {"addr": "10.0.0.10", "host_token": "hb", "gate_port": 70000}},
      "stacks": {"owner": {"lugar": ["pc", "notoken", "badport", "ghost"], "gpu": ["pc"]}, "gpuonly": {"gpu": ["pc", "nolist"]}, "none": {}}}
lug = {n: gs.lugares_build(lm, n) for n in ("owner", "gpuonly", "none")}
check("a stack with the host in its lugar list gets url and the HOST token (not the gate token)", lug["owner"], {"pc": {"url": "http://10.0.0.7:8700", "token": "hp"}})
check("being allowed gpu jobs on a host never gives its games and power control", lug["gpuonly"], {})
check("a stack with no lugar list gets nothing", lug["none"], {})
with contextlib.redirect_stdout(io.StringIO()):
    full_owner = gs.build(lm, "owner")
check("build() carries lugares and the gate token apart", (full_owner.get("lugares"), full_owner.get("gates", {}).get("pc", {}).get("token")), ({"pc": {"url": "http://10.0.0.7:8700", "token": "hp"}}, "gp"))
summ = json.dumps(gs.summary(full_owner))
check("the check summary names the lugar host and never its token", ("lugar pc" in summ, "hp" in summ.replace("lugar pc", "")), (True, False))
# escritorio: one place per stack, with its own token
em = {"hosts": {"pc": {"addr": "10.0.0.7", "gate_port": 8700}, "noaddr": {}}, "stacks": {"p": {"escritorio": {"host": "pc", "token": "tk-p"}}, "q": {"escritorio": {"host": "pc"}},
      "r": {"escritorio": {"host": "noaddr", "token": "x"}}, "s": {"escritorio": "bad"}, "t": {}}}
check("a stack with an escritorio entry gets the gate address and ITS place token", gs.escritorio_build(em, "p"), {"url": "http://10.0.0.7:8700", "token": "tk-p"})
check("no token, no address, a bad entry or none: nothing is written", [gs.escritorio_build(em, n) for n in "qrst"], [{}] * 4)
sm = gs.summary({"escritorio": {"url": "u", "token": "tk-p"}})
check("the summary says there is a desk and never shows its token", (sm, "tk-p" in str(sm)), ({"escritorio": "desk"}, False))
print("gateways_sync_gates_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
