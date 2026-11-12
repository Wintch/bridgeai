#!/usr/bin/env python3
"""Offline checks for ops/gateways_host_service.py and the image, video and vidpost kinds of ops/gateways_sync.py."""
import importlib.util, io, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def run(cwd, args, stdin=""):
    r = subprocess.run([sys.executable, os.path.join(HERE, "gateways_host_service.py")] + args, cwd=cwd, input=stdin, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "ops"))
master = {"hosts": {"box": {"addr": "10.0.0.5", "upscale": 8600}, "other": {"addr": "10.0.0.6"}}, "stacks": {"hernik": {"gpu": ["box"]}, "hereug": {"gpu": ["other"]}}}
json.dump(master, open(os.path.join(d, "ops", "gateways.json"), "w"))
TOK = "t" * 48
rc, out = run(d, ["box", "image", "8660", "--token-stdin"], TOK + "\n")
m = json.load(open(os.path.join(d, "ops", "gateways.json")))
check("registers the port and the token", (rc, m["hosts"]["box"]["image"], m["hosts"]["box"]["image_token"], m["hosts"]["box"]["upscale"]), (0, 8660, TOK, 8600))
check("never prints the token", TOK in out, False)
check("backs up the master and keeps mode 0600", (len([f for f in os.listdir(os.path.join(d, "ops")) if ".bak-" in f]), oct(os.stat(os.path.join(d, "ops", "gateways.json")).st_mode & 0o777)), (1, "0o600"))
before = open(os.path.join(d, "ops", "gateways.json")).read()
check("--check writes nothing", (run(d, ["box", "image", "9999", "--check"])[0], open(os.path.join(d, "ops", "gateways.json")).read() == before), (0, True))
check("unknown host, service, port and a bad token are refused", [run(d, a, s)[0] for a, s in ((["nope", "image", "8660"], ""), (["box", "evil", "8660"], ""), (["box", "image", "99999"], ""), (["box", "image", "8660", "--token-stdin"], "short\n"), (["box", "image", "8660", "--token-stdin"], "a b " * 12))], [1, 2, 2, 1, 1])
check("a refused call leaves the master untouched", open(os.path.join(d, "ops", "gateways.json")).read() == before, True)

spec = importlib.util.spec_from_file_location("gs", os.path.join(HERE, "gateways_sync.py")); gs = importlib.util.module_from_spec(spec); spec.loader.exec_module(gs)
cfg = gs.build(m, "hernik")
check("a stack allowed the host gets the image entry with its token", cfg.get("image"), [{"name": "box", "url": "http://10.0.0.5:8660", "token": TOK}])
check("a stack not allowed the host gets no image entry and no token", ("image" in gs.build(m, "hereug"), TOK in json.dumps(gs.build(m, "hereug"))), (False, False))

# the video kind (vidgen): same token handling as image, its own kind and token key
VT = "v" * 48
rc, out = run(d, ["box", "video", "8670", "--token-stdin"], VT + "\n")
m = json.load(open(os.path.join(d, "ops", "gateways.json")))
check("video: registers the port and its own token, keeps the image ones", (rc, m["hosts"]["box"]["video"], m["hosts"]["box"]["video_token"], m["hosts"]["box"]["image"], m["hosts"]["box"]["image_token"]), (0, 8670, VT, 8660, TOK))
check("video: never prints the token", (VT in out, TOK in out), (False, False))
check("video: a bad token on stdin is refused and the master is untouched", (run(d, ["box", "video", "8670", "--token-stdin"], "short\n")[0], json.load(open(os.path.join(d, "ops", "gateways.json"))) == m), (1, True))
cfg = gs.build(m, "hernik")
check("video: a stack allowed the host gets the video entry with the video token", cfg.get("video"), [{"name": "box", "url": "http://10.0.0.5:8670", "token": VT}])
check("video: the image entry keeps the image token", cfg.get("image"), [{"name": "box", "url": "http://10.0.0.5:8660", "token": TOK}])
other = gs.build(m, "hereug")
check("video: a stack not allowed the host gets no video entry and no token", ("video" in other, VT in json.dumps(other)), (False, False))
m2 = json.loads(json.dumps(m)); m2["hosts"]["other"].update(video=8670, video_token="w" * 48)
check("video: each stack gets only its own host's video token", (gs.build(m2, "hernik")["video"][0]["token"], gs.build(m2, "hereug")["video"][0]["token"]), (VT, "w" * 48))
check("video: a host without a video port gives no video entry", "video" in gs.build({"hosts": {"b": {"addr": "1.1.1.1", "image": 8660}}, "stacks": {"x": {"gpu": ["b"]}}}, "x"), False)
# the vidpost kind (gateway enhance): same token handling, its own kind and token key
PT = "p" * 48
rc, out = run(d, ["box", "vidpost", "8680", "--token-stdin"], PT + "\n")
m = json.load(open(os.path.join(d, "ops", "gateways.json")))
check("vidpost: registers the port and its own token, keeps the image and video ones", (rc, m["hosts"]["box"]["vidpost"], m["hosts"]["box"]["vidpost_token"], m["hosts"]["box"]["video_token"], m["hosts"]["box"]["image_token"]), (0, 8680, PT, VT, TOK))
check("vidpost: never prints the token", (PT in out, VT in out, TOK in out), (False, False, False))
check("vidpost: a bad token on stdin is refused and the master is untouched", (run(d, ["box", "vidpost", "8680", "--token-stdin"], "short\n")[0], json.load(open(os.path.join(d, "ops", "gateways.json"))) == m), (1, True))
cfg = gs.build(m, "hernik")
check("vidpost: a stack allowed the host gets the vidpost entry with the vidpost token", cfg.get("vidpost"), [{"name": "box", "url": "http://10.0.0.5:8680", "token": PT}])
check("vidpost: the video and image entries keep their own tokens", (cfg["video"][0]["token"], cfg["image"][0]["token"]), (VT, TOK))
other = gs.build(m, "hereug")
check("vidpost: a stack not allowed the host gets no vidpost entry and no token", ("vidpost" in other, PT in json.dumps(other)), (False, False))
m2 = json.loads(json.dumps(m)); m2["hosts"]["other"].update(vidpost=8680, vidpost_token="q" * 48)
check("vidpost: each stack gets only its own host's vidpost token", (gs.build(m2, "hernik")["vidpost"][0]["token"], gs.build(m2, "hereug")["vidpost"][0]["token"]), (PT, "q" * 48))
check("vidpost: a host without a vidpost port gives no vidpost entry", "vidpost" in gs.build({"hosts": {"b": {"addr": "1.1.1.1", "video": 8670}}, "stacks": {"x": {"gpu": ["b"]}}}, "x"), False)
# the gate (gpu-host/gate): `gate` stores gate_port and gate_token; each stack gets only the gates of the hosts it may use
GT = "g" * 48
rc, out = run(d, ["box", "gate", "8700", "--token-stdin"], GT + "\n")
m = json.load(open(os.path.join(d, "ops", "gateways.json")))
check("gate: registers gate_port and gate_token, keeps the other tokens", (rc, m["hosts"]["box"]["gate_port"], m["hosts"]["box"]["gate_token"], m["hosts"]["box"]["vidpost_token"], "gate" in m["hosts"]["box"]), (0, 8700, GT, PT, False))
check("gate: never prints the token", GT in out, False)
cfg = gs.build(m, "hernik")
check("gate: a stack allowed the host gets its gate and its own name", (cfg.get("gates"), cfg.get("stack")), ({"box": {"url": "http://10.0.0.5:8700", "token": GT}}, "hernik"))
other = gs.build(m, "hereug")
check("gate: a stack not allowed the host gets no gate, no token and no stack key", ("gates" in other, "stack" in other, GT in json.dumps(other)), (False, False, False))
check("gate: the check summary names the host and never the token", (GT in json.dumps(gs.summary(cfg)), gs.summary(cfg)["gates"]), (False, "gate box"))
m3 = json.loads(json.dumps(m)); m3["hosts"]["box"]["gate_port"] = 8801
check("gate: gate_port overrides the default 8700", gs.build(m3, "hernik")["gates"]["box"]["url"], "http://10.0.0.5:8801")
m3["hosts"]["box"].pop("gate_token")
check("gate: a gate_port without a gate_token writes no gate", "gates" in gs.build(m3, "hernik"), False)
m4 = {"hosts": {"v": {"addr": "1.1.1.1", "stt": 8620, "gate_token": GT}}, "stacks": {"y": {"gpu": [], "voice": ["v"]}}}
check("gate: a voice-only host gets no gate token (one token per host would hand over every service)", list(gs.build(m4, "y").get("gates", {})), [])
check("gate: a host reached by container name (no addr) has no gate", "gates" in gs.build({"hosts": {"c": {"mosh_url": "http://mosher:8690", "gate_token": GT}}, "stacks": {"z": {"gpu": ["c"]}}}, "z"), False)
check("gate: a bad port is refused", run(d, ["box", "gate", "0"])[0], 2)
print("gateways_host_service_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
