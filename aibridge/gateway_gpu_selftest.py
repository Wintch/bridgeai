#!/usr/bin/env python3
"""Offline checks for the GPU gate side of gateway.py (`gateway gpu`, the wake/done calls around every GPU verb). Run: python3 -I gateway_gpu_selftest.py

A fake gate and fake GPU services stand in for a host (no network beyond 127.0.0.1, no docker, no GPU). Covers: wake 200 then the job and
/done; wake 202 then the wait for /healthz (and giving up at the ready budget); every 409 reason -> its fixed sentence and exit 5 (host text is
never shown); a gate that does not answer -> the old behaviour (used if up, "off" if not, exit 3); a stopped gated host woken instead of
reporting "off" and the next host tried after a refusal; a small clip never wakes a stopped GPU for the local CPU's job; batch start / count /
automatic close / end (a failed release keeps the lease for a retry); `gpu off` (all services, or one kind); `gpu status` without tokens; stt and tts waking
the gate before Groq / Edge; a 200 for a service still loading; a slow /wake; a dead gate asked once; the eta cap; 401 / 403 notes and gate_error; the exclusive retry
after this stack's own idle lease; SIGTERM and gate_finish never changing the exit code."""
import contextlib, importlib.util, io, json, os, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
FAIL = []
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
GT = "gate-token-0123456789abcdef"


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def fake_service():
    """A GPU service: /healthz and /health answer 200 only while st["up"]; every job POST answers a small fixed body."""
    st = {"up": True, "posts": [], "status": None}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def reply(self, code, data, **hdr):
            self.send_response(code); self.send_header("Content-Length", str(len(data)))
            for k, v in hdr.items():
                self.send_header(k.replace("_", "-"), v)
            self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            if self.path == "/status" and st["status"] is not None and st["up"]:
                return self.reply(200, json.dumps(st["status"]).encode())
            self.reply(200 if st["up"] and self.path in ("/healthz", "/health") else 503, b"ok")

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            st["posts"].append(self.path.split("?")[0])
            p = self.path.split("?")[0]
            if p == "/image":
                self.reply(200, PNG, X_Image_Seconds="1.0", X_Image_Seed="7", X_Image_Size="1024x1024")
            elif p == "/upscale":
                self.reply(200, b"UPSCALED")
            elif p == "/transcribe":
                self.reply(200, json.dumps({"text": "hola", "device": "cuda", "language": "es", "audio_seconds": 1.0}).encode())
            elif p == "/v1/audio/speech":
                self.reply(200, b"AUDIO", X_Voice="default")
            else:
                self.reply(404, b"no")

    srv, port = serve(H)
    return st, port


def fake_gate():
    """A gate: records every call; /wake answers what st["wake"][port] says (default 200 with lease L<port>)."""
    st = {"calls": [], "wake": {}, "on_wake": None, "on_off": None, "release": 200, "stopped": ["imggen"], "state": {}}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def reply(self, code, obj):
            data = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            if self.path == "/healthz":
                return self.reply(200, {})
            st["calls"].append(("GET", self.path, self.headers.get("Authorization"), None))
            self.reply(200 if self.path == "/state" else 404, st["state"])

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"null")
            st["calls"].append(("POST", self.path, self.headers.get("Authorization"), body))
            if self.path == "/wake":
                if st["on_wake"]:
                    st["on_wake"](body)
                code, obj = st["wake"].get(body["port"], (200, {"lease": f"L{body['port']}", "running": True, "eta_s": 0}))
                return self.reply(code, obj)
            if self.path == "/off" and st["on_off"]:
                st["on_off"](body)
            if self.path == "/release":
                return self.reply(st["release"], {})
            self.reply(200, {"stopped": st["stopped"]} if self.path == "/off" else {})

    srv, port = serve(H)
    return st, port


def posts(gate, path):
    return [c[3] for c in gate["calls"] if c[0] == "POST" and c[1] == path]


cfgp, logp, batchp = os.path.join(tmp, "gateways.json"), os.path.join(tmp, "log.jsonl"), os.path.join(tmp, "batch.json")
os.environ.update(GATEWAYS_CONFIG=cfgp, GATEWAY_LOG=logp, GATEWAY_GPU_BATCH=batchp, GATEWAY_GATE_POLL="0.05", GATEWAY_GATE_TIMEOUT="3")
spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def setconf(cfg):
    json.dump(cfg, open(cfgp, "w"))


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    old = sys.argv
    sys.argv = ["gateway"] + argv
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = m.main()
        except SystemExit as e:
            code = e.code
    sys.argv = old
    return code, out.getvalue(), err.getvalue()


def logs():
    try:
        return [json.loads(x) for x in open(logp)]
    except OSError:
        return []


svc, sport = fake_service()
gate, gport = fake_gate()
url = f"http://127.0.0.1:{sport}"
G = {"url": f"http://127.0.0.1:{gport}", "token": GT}
IMG = os.path.join(tmp, "o.png")


def image(out=IMG):
    return run(["image", "--", "a red square", out])


# 1. wake 200: the job runs, the gate got the wake with the stack name, then /done
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})
code, out, _ = image()
check("200: the image is made", (code, os.path.exists(IMG)), (0, True))
check("200: wake body has the port, the stack, interactive mode", posts(gate, "/wake"), [{"port": sport, "stack": "stk", "mode": "interactive", "batch": None, "jobs": None}])
check("200: /done for the lease after the job", posts(gate, "/done"), [{"lease": f"L{sport}"}])
check("every gate call carries the Bearer token", {c[2] for c in gate["calls"]}, {f"Bearer {GT}"})
check("a host with no stack name in the config sends 'stack'", (setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G}}), image()[0], posts(gate, "/wake")[-1]["stack"])[1:], (0, "stack"))
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})

# 2. wake 202: the job waits for /healthz, which turns on a moment later
gate["calls"].clear()
svc["up"] = False
gate["wake"][sport] = (202, {"lease": "Lslow", "running": False, "eta_s": 5})
gate["on_wake"] = lambda b: threading.Timer(0.3, lambda: svc.update(up=True)).start()
t = time.time()
code, out, err = image()
check("202: waited for the service then made the image", (code, svc["posts"][-1], 0.25 < time.time() - t < 4), (0, "/image", True))
check("202: /done sent for that lease", posts(gate, "/done"), [{"lease": "Lslow"}])
check("202: the wait is announced on stderr only", ("starting" in err, "starting" in out), (True, False))

# 3. wake 202 but the service never answers within the ready budget: treated as off
gate["calls"].clear()
svc["up"] = False
gate["wake"][sport] = (202, {"lease": "Lnever", "running": False, "eta_s": 0.2})
gate["on_wake"] = None
code, out, _ = image()
check("202 that never turns up: off, exit 3, fixed sentence", (code, out.startswith("GPU: off.")), (3, True))
check("202 that never turns up: /done is still sent", posts(gate, "/done"), [{"lease": "Lnever"}])

# 4. every refusal reason has its fixed sentence and exit 5; host text is never shown
svc["up"] = True
for why, want in (("vr", "in use right now (VR, a game or video editing)"), ("busy", "operator marked the GPU machine busy"),
                  ("vram", "The GPU is busy with another job"), ("exclusive", "still making a video or a picture"),
                  ("<script>alert(1)</script>", "The GPU is busy with another job")):
    gate["calls"].clear()
    gate["wake"][sport] = (409, {"why": why, "detail": "SECRET-HOST-TEXT"})
    code, out, _ = image()
    check(f"409 {why[:10]}: exit 5 with the fixed sentence, nothing from the host", (code, want in out, "SECRET" in out, "<script>" in out), (5, True, False, False))
check("409: no lease, so no /done", posts(gate, "/done"), [])
check("409: the metadata line names the reason", [l.get("gate_refused") for l in logs() if l.get("error") == "gate_vr"], ["vr"])
gate["wake"][sport] = (409, {"why": "vr"})
up_path = os.path.join(tmp, "up.png")
fake_in = os.path.join(tmp, "in.png"); open(fake_in, "wb").write(PNG)
setconf({"upscale": [{"name": "box", "url": url}], "gates": {"box": G}})
code, out, _ = run(["upscale", fake_in, up_path])
check("409 on upscale: exit 5, sentence, nothing written", (code, "in use right now" in out, os.path.exists(up_path)), (5, True, False))
setconf({"video": [{"name": "box", "url": url}], "gates": {"box": G}})
gate["wake"][sport] = (409, {"why": "busy"})
code, out, _ = run(["makevideo", "--secs", "2", "--", "a slow tide", os.path.join(tmp, "v.mp4")])
check("409 on makevideo: exit 5 and the busy sentence, no video queue wait", (code, "operator marked" in out, "/video" in svc["posts"]), (5, True, False))
setconf({"mosh": [{"name": "box", "url": url}], "gates": {"box": G}})
mot = os.path.join(tmp, "motion.mp4"); open(mot, "wb").write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
code, out, _ = run(["mosh", mot, os.path.join(tmp, "mo.mp4")])
check("409 on mosh: exit 5", (code, "operator marked" in out), (5, True))
setconf({"vidpost": [{"name": "box", "url": url}], "gates": {"box": G}})
code, out, _ = run(["enhance", mot, os.path.join(tmp, "en.mp4")])
check("409 on enhance: exit 5", (code, "operator marked" in out), (5, True))

# 5. gate down: the host is used if it answers, "off" (exit 3) if not: the old behaviour
dead = {"url": "http://127.0.0.1:1", "token": GT}
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": dead}})
svc["up"] = True
check("gate down, service up: the job still runs", image()[0], 0)
svc["up"] = False
code, out, _ = image()
check("gate down, service down: off, exit 3", (code, out.startswith("GPU: off.")), (3, True))
svc["up"] = True

# 6. several hosts: a refusal moves on to the next host (an ungated one), a stopped gated host is woken before "off"
other, oport = fake_service()
gate["calls"].clear()
gate["wake"][sport] = (409, {"why": "vr"})
setconf({"image": [{"name": "box", "url": url}, {"name": "plain", "url": f"http://127.0.0.1:{oport}"}], "gates": {"box": G}})
n = len(other["posts"])
code, out, _ = image()
check("refused host skipped, the ungated one makes the picture", (code, len(other["posts"]) - n, len(posts(gate, "/done"))), (0, 1, 0))
svc["up"] = False
gate["wake"][sport] = (202, {"lease": "Lw", "running": False, "eta_s": 5})
gate["on_wake"] = lambda b: svc.update(up=True)
other["up"] = False
setconf({"image": [{"name": "plain", "url": f"http://127.0.0.1:{oport}"}, {"name": "box", "url": url}], "gates": {"box": G}})
code, out, _ = image()
check("nothing up: the stopped gated host is woken instead of reporting off", (code, svc["posts"][-1]), (0, "/image"))
gate["on_wake"] = None
gate["wake"].clear()
other["up"] = True

# 7. a small clip is not worth waking a stopped GPU: the local CPU does it (stubbed), the gate is not asked
m.vprobe = lambda p: None
ran = []


def fake_run(args, **kw):
    ran.append(args[0])
    open(args[-1], "wb").write(b"x")
    return m.subprocess.CompletedProcess(args, 0)
real_run = m.subprocess.run
m.subprocess.run = fake_run
svc["up"] = False
gate["calls"].clear()
setconf({"transcode": [{"name": "box", "url": url}], "gates": {"box": G}})
clip = os.path.join(tmp, "clip.mp4"); open(clip, "wb").write(b"\x00" * 2048)
code, out, _ = run(["transcode", clip, os.path.join(tmp, "clip2.mp4")])
check("small clip, stopped gated host: done on this container, no wake", (code, ran[:1], posts(gate, "/wake")), (0, ["ffmpeg"], []))
m.LOCAL_MAX_S = 0
ran.clear()
gate["wake"][sport] = (409, {"why": "vr"})
code, out, _ = run(["transcode", clip, os.path.join(tmp, "clip3.mp4")])
check("no local fallback and the gate refused: exit 5 with the sentence, nothing run here", (code, "in use right now" in out, ran), (5, True, []))
m.LOCAL_MAX_S = 900
m.subprocess.run = real_run
gate["wake"].clear()
svc["up"] = True

# 8. batch: start, count, automatic close at the last job, end, refusals
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})
gate["calls"].clear()
code, out, _ = run(["gpu", "batch", "start", "--jobs", "2", "--name", "night run"])
b = json.load(open(batchp))
check("batch start --jobs 2: file written", (code, b["jobs"], b["done"], b["name"], len(b["id"])), (0, 2, 0, "night run", 8))
check("a second batch start is refused", run(["gpu", "batch", "start", "--until-end"])[0], 2)
image()
w = posts(gate, "/wake")[-1]
check("job 1 wakes in batch mode with the batch id and jobs", (w["mode"], w["batch"], w["jobs"]), ("batch", b["id"], 2))
b = json.load(open(batchp))
check("job 1 counted, lease kept in the file, no release yet", (b["done"], b["leases"], posts(gate, "/release")), (1, {"box": f"L{sport}"}, []))
image()
check("job 2 closes the batch: release close=true and the file is gone", (posts(gate, "/release"), os.path.exists(batchp)), ([{"lease": f"L{sport}", "close": True}], False))
check("after the batch a wake is interactive again", (image()[0], posts(gate, "/wake")[-1]["mode"]), (0, "interactive"))
gate["calls"].clear()
run(["gpu", "batch", "start", "--until-end"])
b = json.load(open(batchp))
image(); image(); image()
check("--until-end: jobs null, three jobs counted, nothing released", (b["jobs"], json.load(open(batchp))["done"], posts(gate, "/release")), (None, 3, []))
code, out, _ = run(["gpu", "batch", "end"])
check("batch end: release close=true on the gate, file deleted", (code, posts(gate, "/release"), os.path.exists(batchp), "3 job" in out), (0, [{"lease": f"L{sport}", "close": True}], False, True))
check("batch end with none open is harmless", (run(["gpu", "batch", "end"])[0], "no batch" in run(["gpu", "batch", "end"])[1]), (0, True))
for argv in (["start"], ["start", "--jobs", "0"], ["start", "--jobs", "x"], ["start", "--jobs", "2", "--until-end"], ["start", "--jobs", "2", "--name", "bad;name"], ["bogus"]):
    check(f"batch {' '.join(argv)}: refused (exit 2), no file", (run(["gpu", "batch"] + argv)[0], os.path.exists(batchp)), (2, False))
open(batchp, "w").write(json.dumps({"id": "abcdef01", "name": None, "jobs": 5, "done": 0, "started": time.time() - 7 * 3600, "leases": {}}))
gate["calls"].clear()
image()
check("a batch file older than 6 h is ignored: the wake is interactive", posts(gate, "/wake")[-1]["mode"], "interactive")
check("...and batch start replaces it", (run(["gpu", "batch", "start", "--jobs", "1"])[0], json.load(open(batchp))["id"] != "abcdef01"), (0, True))
run(["gpu", "batch", "end"])
setconf({"image": [{"name": "box", "url": url}]})
check("batch start without any gate changes nothing", (run(["gpu", "batch", "start", "--until-end"])[0], os.path.exists(batchp)), (0, False))
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})

# 9. gpu off: the whole stack, or one kind
gate["calls"].clear()
code, out, _ = run(["gpu", "off"])
check("gpu off: POST /off for this stack, every service", (code, posts(gate, "/off"), "stopped imggen on box" in out), (0, [{"stack": "stk", "port": None}], True))
gate["calls"].clear()
code, out, _ = run(["gpu", "off", "image"])
check("gpu off image: only the port of the image entry", (code, posts(gate, "/off")), (0, [{"stack": "stk", "port": sport}]))
gate["calls"].clear()
check("gpu off with a kind this host does not have: no call", (run(["gpu", "off", "stt"])[0] in (0, 3), posts(gate, "/off")), (True, []))
check("gpu off with an unknown kind is refused", run(["gpu", "off", "toaster"])[0], 2)
gate["stopped"] = ["vidgen; rm -rf /", "tts-hq"]
out = run(["gpu", "off"])[1]
check("gpu off prints only service names that look like names", ("tts-hq" in out, "rm -rf" in out), (True, False))
gate["stopped"] = []
check("gpu off with nothing held says so", "nothing of this stack was holding" in run(["gpu", "off"])[1], True)
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": dead}})
check("gpu off with the gate unreachable: exit 3", run(["gpu", "off"])[0], 3)
setconf({"image": [{"name": "box", "url": url}]})
check("gpu off with no gate configured: exit 0, says so", (run(["gpu", "off"])[0], "no GPU gate" in run(["gpu", "off"])[1]), (0, True))

# 10. gpu status: no tokens, only fixed words and numbers
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G, "gone": dead}, "stack": "stk"})
gate["state"] = {"gpu": {"name": "SECRET GPU", "limit_w": 130, "default_w": 200, "min_w": 100, "max_w": 200, "free_mb": 4000}, "blocked": "vr",
                 "services": {"imggen": {"port": sport, "running": True, "leases": 2, "mode": "batch", "idle_left_s": 12},
                              "llm": {"port": 2, "running": True, "leases": ["x"], "mode": "interactive", "idle_left_s": 5},
                              "vidgen": {"port": 1, "running": False}, "bad name!": {"running": True}}}
run(["gpu", "batch", "start", "--jobs", "4", "--name", "x"])
code, out, _ = run(["gpu", "status"])
check("status: blocked state, power, running service, no tokens, no host text", (code, "in use (VR, a game or video editing)" in out, "130 W" in out, "imggen: running, batch, 2 lease" in out,
      GT in out, "SECRET" in out, "vidgen" in out, "bad name" in out), (0, True, True, True, False, False, False, False))
check("status: the lease count is read as an integer (the gate's shape) or as a list", ("imggen: running, batch, 2 lease" in out, "llm: running, interactive, 1 lease(s), stops after 5 s idle" in out), (True, True))
check("status: an unreachable gate is said, and the open batch is shown", ("gone: the GPU machine does not answer" in out, "0 of 4 jobs done" in out), (True, True))
run(["gpu", "batch", "end"])
check("`gateway status` lists the gate", "gate      box" in run(["status"])[1], True)
check("gpu with a bad subcommand: usage, exit 2", (run(["gpu", "x"])[0], "usage: gateway gpu" in run(["gpu", "x"])[1]), (2, True))

# 11. voice: the gate is asked for a stopped stt/tts host BEFORE Groq / Edge
audio = os.path.join(tmp, "a.ogg"); open(audio, "wb").write(b"OggS" + b"\x00" * 64)
groq_calls = []
m.groq_key = lambda: "gsk-test"
m.groq_stt = lambda path, key: groq_calls.append(path) or {"text": "cloud", "language": "es", "wall": 0.1, "audio_seconds": 1, "device": "cloud"}
svc["up"] = False
gate["calls"].clear()
gate["wake"][sport] = (202, {"lease": "Lstt", "running": False, "eta_s": 5})
gate["on_wake"] = lambda b: svc.update(up=True)
setconf({"stt": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})
code, out, _ = run(["transcribe", audio, "es", "--voice"])
check("transcribe --voice: a stopped GPU host is woken and used, Groq is not called", (code, out.strip(), groq_calls, svc["posts"][-1]), (0, "hola", [], "/transcribe"))
check("transcribe --voice: /done after the job", posts(gate, "/done"), [{"lease": "Lstt"}])
svc["up"] = False
gate["on_wake"] = None
gate["wake"][sport] = (202, {"lease": "Lslow", "running": False, "eta_s": 40})
m.GATE_VOICE_BUDGET = 0.3
t = time.time()
code, out, _ = run(["transcribe", audio, "es", "--voice"])
check("transcribe --voice: a host that does not come up within the voice budget goes to Groq", (code, out.strip(), len(groq_calls), time.time() - t < 5), (0, "cloud", 1, True))
gate["wake"][sport] = (409, {"why": "vr"})
groq_calls.clear()
code, out, _ = run(["transcribe", audio, "es", "--voice"])
check("transcribe --voice: a refusal goes to Groq (VR keeps the GPU)", (code, groq_calls != []), (0, True))
m.GATE_VOICE_BUDGET = 20
svc["up"] = False
gate["calls"].clear()
gate["wake"][sport] = (202, {"lease": "Ltts", "running": False, "eta_s": 5})
gate["on_wake"] = lambda b: svc.update(up=True)
setconf({"tts": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})
txt = os.path.join(tmp, "t.txt"); open(txt, "w").write("hola mundo")
code, out, _ = run(["speak", txt, os.path.join(tmp, "s.mp3")])
check("speak: a stopped GPU voice host is woken and used", (code, svc["posts"][-1], open(os.path.join(tmp, "s.mp3"), "rb").read()), (0, "/v1/audio/speech", b"AUDIO"))
svc["up"] = False
gate["on_wake"] = None
gate["wake"][sport] = (409, {"why": "busy"})
gate["calls"].clear()
real_which = m.shutil.which
m.shutil.which = lambda x: None
code, out, err = run(["speak", txt, os.path.join(tmp, "s2.mp3")])
m.shutil.which = real_which
check("speak: the gate was asked first; refused, it goes on to Edge (none installed here: exit 3)", (len(posts(gate, "/wake")), code, "no edge-tts" in err), (1, 3, True))

# 12. llm (llama.cpp answers /health): the wait uses that path
svc["up"] = False
gate["wake"][sport] = (202, {"lease": "Lllm", "running": False, "eta_s": 5})
gate["on_wake"] = lambda b: threading.Timer(0.2, lambda: svc.update(up=True)).start()
h = {"name": "box", "url": url, "model": "m"}
check("gate_ready for llm waits on /health", (m.gate_ready(h, "llm"), h["_up"]), (True, True))
gate["on_wake"] = None
m.GATE["leases"].clear()            # the direct call above is not a command: nothing to tell the gate

# 13. garbage from a gate is never trusted
svc["up"] = True
gate["calls"].clear()
gate["wake"][sport] = (200, {"lease": {"x": 1}, "running": True, "eta_s": "soon"})
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G}})
check("a wake answer with a bad lease still lets the job run, and no /done is sent for it", (image()[0], posts(gate, "/done")), (0, []))
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": {"url": G["url"]}}})
gate["calls"].clear()
check("a gate entry without a token is not used", (image()[0], gate["calls"]), (0, []))

# 14. a 200 only means "started": a service that is not healthy yet is waited for, like after a 202
svc["up"] = False
gate["calls"].clear()
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})
gate["wake"][sport] = (200, {"lease": "Lrun", "running": True, "eta_s": 0})
gate["on_wake"] = None
threading.Timer(0.4, lambda: svc.update(up=True)).start()
code, out, err = image()
check("200 on a service still loading: waits for /healthz, then the job runs", (code, svc["posts"][-1], "starting" in err), (0, "/image", True))
svc["up"] = False
setconf({"stt": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})
groq_calls.clear()
threading.Timer(0.4, lambda: svc.update(up=True)).start()
code, out, _ = run(["transcribe", audio, "es", "--voice"])
check("200 on a loading stt host (voice, no ranking): waited for, Groq not called", (code, out.strip(), groq_calls), (0, "hola", []))
svc["up"] = False
m.GATE_READY_S["image"] = 0.2
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})
t = time.time()
code, out, _ = image()
m.GATE_READY_S["image"] = 150
check("200 on a service that never comes up: off after the default budget, exit 3", (code, out.startswith("GPU: off."), time.time() - t < 4), (3, True, True))
svc["up"] = True

# 15. the wait is the gate's budget plus 10 %, and never more than the cap, whatever the host says
svc["up"] = False
gate["wake"][sport] = (202, {"lease": "Lm", "running": False, "eta_s": 2})
gate["on_wake"] = lambda b: threading.Timer(2.1, lambda: svc.update(up=True)).start()
check("202: the margin over eta_s is kept (a service ready at 105 % of eta is still waited for)", image()[0], 0)
svc["up"] = False
gate["on_wake"] = None
gate["wake"][sport] = (202, {"lease": "Lbig", "running": False, "eta_s": 100000000})
m.GATE_WAIT_MAX = 0.4
t = time.time()
code, out, _ = image()
m.GATE_WAIT_MAX = 600
check("202 with a huge eta_s: the wait is capped, then off (exit 3)", (code, time.time() - t < 3), (3, True))
svc["up"] = True
gate["wake"].clear()

# 16. a slow /wake (the gate starts the container under its lock) is not "gate unreachable"; a gate that does not answer is asked once
m.GATE_TIMEOUT, m.GATE_WAKE_TIMEOUT = 0.3, 5
svc["up"] = False
gate["calls"].clear()
gate["wake"][sport] = (202, {"lease": "Lsl", "running": False, "eta_s": 5})
gate["on_wake"] = lambda b: (time.sleep(0.8), svc.update(up=True))
code, out, _ = image()
check("slow /wake (longer than the short timeout): the job still runs", (code, svc["posts"][-1]), (0, "/image"))
gate["on_wake"] = None
gate["wake"].clear()
m.GATE_TIMEOUT, m.GATE_WAKE_TIMEOUT = 3, 60
svc["up"] = True
probes = []
real_healthy = m.healthy
m.healthy = lambda u, *a, **k: probes.append(u) or real_healthy(u, *a, **k)
m.GATE["alive"], m.GATE["dead"] = set(), set()
hh = [{"name": "box", "url": url, "_up": False} for _ in range(3)]
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": dead}})
res = [m.gate_ready(x) for x in hh]
m.healthy = real_healthy
check("a gate that does not answer is probed once for the whole command, the host's own health decides", (res, [u for u in probes if u == dead["url"]]), ([False] * 3, [dead["url"]]))
m.GATE["alive"], m.GATE["dead"], m.GATE["error"] = set(), set(), None
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})

# 17. a refused token is said on stderr and in the log; other odd answers are logged by code
for c in (401, 403, 503):
    gate["wake"][sport] = (c, {"why": "SECRET-HOST-TEXT"})
    n = len(logs())
    code, out, err = image()
    lg = logs()[n:]
    check(f"gate answers {c}: the service that is up is still used, nothing from the host shown", (code, "SECRET" in out + err), (0, False))
    check(f"gate answers {c}: gate_error in the log", [l.get("gate_error") for l in lg], [f"http_{c}"])
    if c != 503:
        check(f"gate answers {c}: the operator is told about the token on stderr", "refused this stack's token" in err, True)
    else:
        check("gate answers 503: no token note", "token" in err, False)
gate["wake"][sport] = (401, {})
svc["up"] = False
code, out, err = image()
check("401 and the service stopped: off (exit 3) and the token note is there", (code, "refused this stack's token" in err), (3, True))
svc["up"] = True
gate["wake"].clear()
n = len(logs())
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": dead}})
image()
check("gate down: gate_error=unreachable in the log", [l.get("gate_error") for l in logs()[n:]], ["unreachable"])
setconf({"image": [{"name": "box", "url": url}], "gates": {"box": G}, "stack": "stk"})

# 18. exclusive: this stack's own idle lease is ended and the wake retried once; a busy or unknown service keeps the refusal
def exclusive_case(status, label, want_off):
    svc["status"] = status
    gate["calls"].clear()
    gate["wake"][sport] = (409, {"why": "exclusive"})
    gate["on_off"] = lambda b: gate["wake"].pop(sport, None)       # the lease is gone: the next wake is 200
    code, out, _ = image()
    check(f"exclusive, {label}: /off sent {want_off} time(s)", (len(posts(gate, "/off")), len(posts(gate, "/wake"))), (want_off, 2 if want_off else 1))
    return code, out
code, out = exclusive_case({"state": "idle", "busy": 0, "queued": 0}, "own service idle", 1)
check("exclusive, own service idle: /off for this stack (all services) then the picture is made", (code, posts(gate, "/off")), (0, [{"stack": "stk", "port": None}]))
code, out = exclusive_case({"state": "running", "busy": 1, "queued": 0}, "own service working", 0)
check("exclusive, own service working: refused, exit 5", code, 5)
code, out = exclusive_case(None, "no status (older image)", 0)
check("exclusive, no status: refused, exit 5, the sentence names `gateway gpu off`", (code, "gateway gpu off" in out), (5, True))
gate["calls"].clear()
gate["wake"][sport] = (409, {"why": "vr"})
svc["status"] = {"state": "idle", "busy": 0, "queued": 0}
image()
check("vr is never answered with /off", posts(gate, "/off"), [])
gate["on_off"] = None
gate["wake"].clear()
svc["status"] = None

# 19. a command killed by SIGTERM still tells the gate (handler -> SystemExit -> main()'s finally); gate_finish never changes the exit code
import signal
old_term = signal.getsignal(signal.SIGTERM)
signal.signal(signal.SIGTERM, signal.SIG_DFL)
m.GATE["term"] = False
image()
h_term = signal.getsignal(signal.SIGTERM)
try:
    h_term(signal.SIGTERM, None)
    raised = None
except SystemExit as e:
    raised = e.code
check("after a lease, SIGTERM raises SystemExit(143) so the finally block runs", (callable(h_term), raised), (True, 143))
signal.signal(signal.SIGTERM, old_term)
m.GATE["term"] = False
run(["gpu", "batch", "start", "--jobs", "1"])
real_save = m.batch_save
m.batch_save = lambda b: (_ for _ in ()).throw(OSError("disk full"))
code, out, _ = image()
m.batch_save = real_save
check("an OSError inside gate_finish does not replace the command's exit code", code, 0)
run(["gpu", "batch", "end"])

# 20. a release the gate did not answer keeps the lease in the batch file, so `batch end` can retry; no false "stop by idle" claim
run(["gpu", "batch", "start", "--until-end"])
image()
gate["release"] = 500
gate["calls"].clear()
code, out, _ = run(["gpu", "batch", "end"])
kept = json.load(open(batchp)) if os.path.exists(batchp) else None
check("batch end with the gate failing: file kept with the lease, message says run it again, no 'idle' claim", (code, kept and kept["leases"], "again" in out, "idle time" in out), (0, {"box": f"L{sport}"}, True, False))
gate["release"] = 200
code, out, _ = run(["gpu", "batch", "end"])
check("batch end retried: released and the file is gone", (code, os.path.exists(batchp), "released on 1" in out), (0, False, True))
run(["gpu", "batch", "start", "--jobs", "1"])
gate["release"] = 500
image()
check("auto-close with the gate failing: the file stays, with the lease", (os.path.exists(batchp), json.load(open(batchp))["leases"]), (True, {"box": f"L{sport}"}))
gate["release"] = 200
run(["gpu", "batch", "end"])
check("batch with no lease at all: ended, says it held no GPU service", (run(["gpu", "batch", "start", "--until-end"])[0], "held no GPU service" in run(["gpu", "batch", "end"])[1]), (0, True))

print("gateway_gpu_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
