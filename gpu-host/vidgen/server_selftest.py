#!/usr/bin/env python3
"""Offline test of gpu-host/vidgen/server.py with a fake ComfyUI (no GPU, no model, no network beyond loopback; needs ffmpeg)."""
import json, os, shutil, signal, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []
if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
    print("vidgen server_selftest: skipped (ffmpeg/ffprobe not installed)")
    sys.exit(0)


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Svc:
    def __init__(self, mode="ok", vram=20000, ram_mb=30000, idle=2.0, job_timeout=6.0, token="tok", mem_wait=0):
        self.work = tempfile.mkdtemp(prefix="vidgen-work-")
        tmp = tempfile.mkdtemp(prefix="vidgen-aux-")
        self.log = os.path.join(tmp, "graphs.jsonl")
        self.port, self.cport, self.token = free_port(), free_port(), token
        nv = self.nv = os.path.join(tmp, "nvsmi.sh")
        open(nv, "w").write(f"#!/bin/sh\necho {vram}\n"); os.chmod(nv, 0o755)
        mi = os.path.join(tmp, "meminfo")
        open(mi, "w").write(f"MemTotal:       32000000 kB\nMemFree:  1000 kB\nMemAvailable:   {ram_mb * 1024} kB\n")
        env = dict(os.environ, GPU_PROBE=os.environ.get('GPU_PROBE_TEST', 'true'), GPU_CHECK_S='1', PORT=str(self.port), VIDEO_TOKEN=token, WORK=self.work, COMFY_PORT=str(self.cport),
                   COMFY_CMD=f"{sys.executable} {HERE}/fake_comfy.py", COMFY_DIR="", IDLE_S=str(idle), JOB_TIMEOUT=str(job_timeout),
                   READY_TIMEOUT="20", NVSMI=nv, MEMINFO=mi, FAKE_MODE=mode, COMFY_FAKE_LOG=self.log, VRAM_NEED_MB="7000", RAM_NEED_MB="16000", MEM_WAIT_S=str(mem_wait))
        self.out = tempfile.NamedTemporaryFile("w+", delete=False)
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")], env=env, stdout=self.out, stderr=subprocess.STDOUT)
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/healthz", timeout=1); break
            except Exception:
                time.sleep(0.1)

    def req(self, body=None, auth=True, path="/video", raw=None, token=None):
        data = raw if raw is not None else json.dumps(body).encode()
        h = {"Content-Type": "application/json"}
        if auth:
            h["Authorization"] = f"Bearer {token or self.token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=h, method="POST"), timeout=60) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as r:
            return r.status, r.read().decode()

    def comfy_alive(self):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.cport}/system_stats", timeout=1); return True
        except Exception:
            return False

    def graphs(self):
        return [json.loads(l) for l in open(self.log)] if os.path.exists(self.log) else []

    def stg(self):
        d = os.path.join(self.work, "out", "stg")
        return os.listdir(d) if os.path.isdir(d) else []

    def logtext(self):
        self.out.flush(); return open(self.out.name).read()

    def close(self):
        self.p.send_signal(signal.SIGTERM)
        try:
            self.p.wait(20)
        except subprocess.TimeoutExpired:
            self.p.kill()


def probe(b):
    f = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False); f.write(b); f.close()
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format_tags", "-of", "json", f.name], capture_output=True, text=True)
    os.unlink(f.name)
    j = json.loads(r.stdout or "{}")
    return sorted(s["codec_type"] for s in j.get("streams", [])), j.get("format", {}).get("tags", {})


s = Svc()
try:
    check("healthz answers", s.get("/healthz"), (200, "ok video"))
    # the GPU watch: a container that lost the card answers 503 on /healthz (the gateway skips it, Zabbix alerts)
    os.environ["GPU_PROBE_TEST"] = "false"; nogpu = Svc(); os.environ.pop("GPU_PROBE_TEST")
    try:
        time.sleep(1.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{nogpu.port}/healthz", timeout=5); got = 200
        except urllib.error.HTTPError as e:
            got = (e.code, e.read().decode()[:6])
        check("healthz is 503 'no gpu' when CUDA cannot see the card", got, (503, "no gpu"))
    finally:
        nogpu.close()
    check("status says asleep before the first job", json.loads(s.get("/status")[1])["state"], "asleep")
    SECRET = "a lighthouse at dawn SECRET-PROMPT-TEXT"
    st, body, hdr = s.req({"prompt": SECRET, "secs": 5, "seed": 7})
    check("a valid request returns an mp4", (st, body[4:8], hdr.get("Content-Type")), (200, b"ftyp", "video/mp4"))
    streams, tags = probe(body)
    check("the mp4 keeps video and sound", streams, ["audio", "video"])
    check("the delivered mp4 carries no metadata title (remuxed with -map_metadata -1)", "SECRET" in json.dumps(tags) or b"SECRET-PROMPT" in body, False)
    check("headers carry seed and length", (hdr.get("X-Video-Seed"), hdr.get("X-Video-Length")), ("7", "5"))
    g = s.graphs()[-1]
    check("the graph is the fixed H3 template with the request values",
          (g["i2v"]["inputs"]["prompt"], g["i2v"]["inputs"]["width"], g["i2v"]["inputs"]["height"], g["i2v"]["inputs"]["length"],
           g["noise"]["inputs"]["noise_seed"], g["sch"]["inputs"]["steps"], g["clip"]["inputs"]["type"]),
          (SECRET, 832, 480, 124, 7, 8, "minimax"))
    check("only the fixed nodes exist", sorted(g), sorted(["clip", "vae", "avae", "unet", "lora", "i2v", "noise", "smp", "sch", "gd", "ks", "dec", "adec", "cv", "sv"]))
    pre = g["sv"]["inputs"]["filename_prefix"]
    check("the output prefix is a random staging path", pre.startswith("stg/") and len(pre.split("/")[1]) == 32, True)
    check("the staging directory is gone after the answer", s.stg(), [])
    check("the prompt text never appears in the service log", "lighthouse" in s.logtext() or "SECRET-PROMPT" in s.logtext(), False)
    lens = [(lambda r: (lambda i: (i["length"], i["width"], i["height"]))(s.graphs()[-1]["i2v"]["inputs"]))(s.req({"prompt": "t", "secs": n})) for n in (2, 3, 8, 10)]
    check("lengths map to the 17k+5 frame grid, and 8 s / 10 s to their smaller sizes", lens, [(56, 832, 480), (73, 832, 480), (192, 704, 384), (243, 608, 352)])
    st2, body2, hdr2 = s.req({"prompt": "a different clip"})
    check("default length is 2 s and a random seed is set", (st2, hdr2.get("X-Video-Length"), (hdr2.get("X-Video-Seed") or "").isdigit()), (200, "2", True))
    check("no leftover staging directory after several jobs", s.stg(), [])

    bad = [{"prompt": ""}, {"prompt": "x" * 801}, {"prompt": "ok", "secs": 4}, {"prompt": "ok", "secs": 60}, {"prompt": "ok", "secs": 15}, {"prompt": "ok", "secs": "5"},
           {"prompt": "ok", "secs": True}, {"prompt": "ok", "seed": -1}, {"prompt": "ok", "seed": True}, {"prompt": "ok", "size": "1920x1080"},
           {"prompt": 5}, {"prompt": "use embedding:evil now"}, {"prompt": "ok", "unet_name": "../../x"}, {"prompt": "ok", "filename_prefix": "../../etc"},
           ["not", "a", "dict"]]
    check("bad requests are all refused with 400", [s.req(b)[0] for b in bad], [400] * len(bad))
    st, body, _ = s.req({"prompt": "ok", "unet_name": "../../PWNED"})
    check("a refusal never echoes the input", b"PWNED" in body or b"../" in body, False)
    check("invalid JSON and an oversized body are 400", (s.req(raw=b"{not json")[0], s.req(raw=b"x" * 5000)[0]), (400, 400))
    check("no token is 401, a wrong token is 401", (s.req({"prompt": "ok"}, auth=False)[0], s.req({"prompt": "ok"}, token="wrong")[0]), (401, 401))
    check("an unknown path is 404", s.req({"prompt": "ok"}, path="/image")[0], 404)

    # chained segments (B5n): one size for every segment, the tail anchored through MiniMaxH3AddGuide, nothing kept afterwards
    import base64, re
    def clip(n, size="608x352"):
        f = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False); f.close()
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=24", "-frames:v", str(n),
                        "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p", f.name], check=True)
        b = open(f.name, "rb").read(); os.unlink(f.name); return base64.b64encode(b).decode()
    sizes = []
    for n in (5, 10):
        st, _, hdr = s.req({"prompt": "c", "secs": n, "chain": True})
        i = s.graphs()[-1]["i2v"]["inputs"]
        sizes.append((st, i["width"], i["height"], i["length"], hdr.get("X-Video-Size"), "guide" in s.graphs()[-1]))
    check("a chain's first segment: 608x352 for 5 s and 10 s, no guide", sizes, [(200, 608, 352, 124, "608x352", False), (200, 608, 352, 243, "608x352", False)])
    st, body, hdr = s.req({"prompt": "c2", "secs": 10, "seed": 8, "chain": True, "tail": clip(5)})
    g = s.graphs()[-1]
    check("a later segment anchors the staged tail at frame 0, picture only",
          (st, body[4:8], g["guide"]["class_type"], g["guide"]["inputs"]["frame_idx"], "audio" in g["guide"]["inputs"], g["gd"]["inputs"]["conditioning"],
           g["tv"]["class_type"], g["tc"]["inputs"]["video"], g["ks"]["inputs"]["latent_image"], g.get("_tail_staged")),
          (200, b"ftyp", "MiniMaxH3AddGuide", 0, False, ["guide", 0], "LoadVideo", ["tv", 0], ["i2v", 1], True))
    check("the tail gets a random name in the input folder", re.fullmatch(r"tail-[0-9a-f]{32}\.mp4", g["tv"]["inputs"]["file"]) is not None, True)
    check("no tail file is left after the job", [f for f in os.listdir(os.path.join(s.work, "in")) if f.startswith("tail-")], [])
    st, _, _ = s.req({"prompt": "c3", "secs": 5, "chain": True, "tail": clip(12, "832x480")})
    check("a longer or bigger tail is cut to its first 5 frames (the model resizes it)", (st, s.graphs()[-1].get("_tail_staged")), (200, True))
    n0 = len(s.graphs())
    badc = [{"prompt": "x", "tail": clip(5)}, {"prompt": "x", "chain": True, "secs": 3}, {"prompt": "x", "chain": True, "secs": 8},
            {"prompt": "x", "chain": "yes", "secs": 5}, {"prompt": "x", "chain": True, "secs": 5, "tail": "@@not base64@@"},
            {"prompt": "x", "chain": True, "secs": 5, "tail": base64.b64encode(b"<html>not a video</html>").decode()},
            {"prompt": "x", "chain": True, "secs": 5, "tail": 5}, {"prompt": "x", "chain": True, "secs": 5, "tail": clip(3)},
            {"prompt": "x", "chain": True, "secs": 5, "tail": base64.b64encode(b"\0\0\0\x18ftypisom" + b"garbage" * 50).decode()}]
    check("bad chain requests are 400 (a tail without chain, other lengths, junk or a 3-frame tail)", [s.req(b)[0] for b in badc], [400] * len(badc))
    check("and no graph was submitted for them", len(s.graphs()), n0)
    check("no tail or source file is left after the refusals", [f for f in os.listdir(os.path.join(s.work, "in")) if f.startswith("tail-")], [])

    # start picture ("first") and portrait: the picture is cut to exactly the output size and staged for LoadImage, then removed
    def pic(ext, size="640x360"):
        f = tempfile.NamedTemporaryFile(suffix="." + ext, delete=False); f.close()
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=1", "-frames:v", "1", f.name], check=True)
        b = open(f.name, "rb").read(); os.unlink(f.name); return b
    b64 = lambda b: base64.b64encode(b).decode()
    jpg, png, tall = pic("jpg"), pic("png"), pic("jpg", "360x640")
    left = lambda: [f for f in os.listdir(os.path.join(s.work, "in")) if f.startswith(("first-", "tail-"))]
    for label, data in (("a JPEG", jpg), ("a PNG", png)):
        st, body, hdr = s.req({"prompt": "f", "secs": 5, "first": b64(data)})
        g = s.graphs()[-1]
        check(f"{label} as first: LoadImage 'fi' feeds i2v.first_frame, staged during the job at exactly 832x480",
              (st, body[4:8], g["fi"]["class_type"], g["i2v"]["inputs"]["first_frame"], g.get("_first_staged"), g.get("_first_size"),
               hdr.get("X-Video-Size")), (200, b"ftyp", "LoadImage", ["fi", 0], True, [832, 480], "832x480"))
    check("the staged picture has a random png name", re.fullmatch(r"first-[0-9a-f]{32}\.png", g["fi"]["inputs"]["image"]) is not None, True)
    check("no first picture or source copy is left after the job", left(), [])
    check("a request without first has no 'fi' node and no first_frame", ("fi" in s.graphs()[0], "first_frame" in s.graphs()[0]["i2v"]["inputs"]), (False, False))
    st, body, hdr = s.req({"prompt": "p", "secs": 5, "portrait": True})
    g = s.graphs()[-1]
    check("portrait swaps width and height: 5 s is 480x832",
          (st, hdr.get("X-Video-Size"), g["i2v"]["inputs"]["width"], g["i2v"]["inputs"]["height"], "fi" in g), (200, "480x832", 480, 832, False))
    st, body, hdr = s.req({"prompt": "p", "secs": 8, "portrait": False})
    check("portrait false changes nothing", (st, hdr.get("X-Video-Size")), (200, "704x384"))
    st, body, hdr = s.req({"prompt": "p", "secs": 5, "portrait": True, "first": b64(tall)})
    g = s.graphs()[-1]
    check("portrait with first: the picture is cut to 480x832",
          (st, hdr.get("X-Video-Size"), g.get("_first_staged"), g.get("_first_size")), (200, "480x832", True, [480, 832]))
    st, body, hdr = s.req({"prompt": "p", "secs": 10, "chain": True, "portrait": True, "first": b64(jpg)})
    g = s.graphs()[-1]
    check("a chain with first and portrait: 352x608, no guide, picture staged at that size",
          (st, hdr.get("X-Video-Size"), g["i2v"]["inputs"]["width"], g["i2v"]["inputs"]["height"], "guide" in g, g.get("_first_size")),
          (200, "352x608", 352, 608, False, [352, 608]))
    st, body, hdr = s.req({"prompt": "p", "secs": 5, "chain": True, "first": b64(png)})
    g = s.graphs()[-1]
    check("a chain's first segment with first: 608x352, i2v.first_frame set", (st, hdr.get("X-Video-Size"), g["i2v"]["inputs"].get("first_frame")), (200, "608x352", ["fi", 0]))
    st, body, hdr = s.req({"prompt": "p", "secs": 5, "chain": True, "portrait": True, "tail": clip(5, "352x608")})
    g = s.graphs()[-1]
    check("a later portrait segment keeps the tail and the portrait size", (st, hdr.get("X-Video-Size"), "guide" in g, "fi" in g), (200, "352x608", True, False))
    check("the picture bytes never appear in the service log", b64(jpg)[:40] in s.logtext(), False)
    check("the log notes first and portrait as flags", ('"first": true' in s.logtext(), '"portrait": true' in s.logtext()), (True, True))
    n1 = len(s.graphs())
    webp_like = b"RIFF\0\0\0\0WEBP" + b"garbage" * 20
    badf = [{"prompt": "x", "chain": True, "secs": 5, "first": b64(jpg), "tail": clip(5)}, {"prompt": "x", "first": b64(jpg), "tail": clip(5)},
            {"prompt": "x", "first": "@@not base64@@"}, {"prompt": "x", "first": 5}, {"prompt": "x", "first": ""},
            {"prompt": "x", "first": b64(b"short")}, {"prompt": "x", "first": b64(b"<html>not a picture</html>" * 3)},
            {"prompt": "x", "first": b64(b"\xff\xd8\xff" + b"garbage" * 40)}, {"prompt": "x", "first": b64(webp_like)},
            {"prompt": "x", "first": b64(b"\x89PNG\r\n\x1a\n" + b"garbage" * 40)},
            {"prompt": "x", "first": b64(jpg[:len(jpg) * 6 // 10])}, {"prompt": "x", "first": b64(png[:len(png) * 6 // 10])},
            {"prompt": "x", "first": b64(b"\xff\xd8\xff" + b"\0" * (8 * 1024 * 1024))},
            {"prompt": "x", "portrait": "yes"}, {"prompt": "x", "portrait": 1}, {"prompt": "x", "portrait": None}]
    check("bad first/portrait requests are 400 (with tail, junk, undecodable, a real picture cut short, over 8 MiB, non-bool portrait)", [s.req(b)[0] for b in badf], [400] * len(badf))
    check("no graph was submitted for the refused ones", len(s.graphs()), n1)
    check("no first picture or source copy is left after the refusals", left(), [])

    check("ComfyUI is alive right after a job", s.comfy_alive(), True)
    time.sleep(5)
    check("ComfyUI is stopped after the idle window (VRAM and RAM go back)", s.comfy_alive(), False)
    check("the next request starts it again", s.req({"prompt": "again"})[0], 200)
finally:
    s.close()

s = Svc(mode="slow", job_timeout=6.0)
try:
    res = []
    t = threading.Thread(target=lambda: res.append(s.req({"prompt": "slow one"})))
    t.start(); time.sleep(1.5)
    st, _, hdr = s.req({"prompt": "second"})
    check("a second request during a job gets 429 with Retry-After", (st, hdr.get("Retry-After")), (429, "60"))
    t.join(40)
    check("a job that never completes is stopped with 504 and the process is killed", ([r[0] for r in res], s.comfy_alive()), ([504], False))
finally:
    s.close()

for mode, name in (("symlink", "a staging directory with a symlink next to the video"), ("notmp4", "a file named .mp4 that is not an mp4"), ("error", "ComfyUI reporting an error")):
    s = Svc(mode=mode)
    try:
        st, body, _ = s.req({"prompt": "x"})
        check(f"{name} is a fixed 500 and nothing is sent", (st, body[4:8] == b"ftyp", b"localhost" in body or b"html" in body), (500, False, False))
        check(f"{name}: staging cleaned up", s.stg(), [])
    finally:
        s.close()

s = Svc(vram=5000)
try:
    st, body, _ = s.req({"prompt": "x"})
    check("without free VRAM the answer is 503 and ComfyUI is never started", (st, s.comfy_alive(), s.graphs()), (503, False, []))
finally:
    s.close()
s = Svc(ram_mb=9000)
try:
    st, body, _ = s.req({"prompt": "x"})
    check("without free RAM the answer is 503 and ComfyUI is never started", (st, s.comfy_alive(), s.graphs()), (503, False, []))
    check("the RAM refusal is logged as no_ram", '"no_ram"' in s.logtext(), True)
finally:
    s.close()

# the card frees up while the request waits (imggen's idle stop): the video is made instead of a 503
s = Svc(vram=5000, mem_wait=20)
try:
    threading.Timer(4, lambda: open(s.nv, "w").write("#!/bin/sh\necho 20000\n")).start()
    t0 = time.time(); st, body, _ = s.req({"prompt": "x"})
    check("a request waits for VRAM that frees up within MEM_WAIT_S, then the video is made", (st, body[4:8], time.time() - t0 >= 3.5), (200, b"ftyp", True))
finally:
    s.close()

env = dict(os.environ, VIDEO_TOKEN="", PORT=str(free_port()), WORK=tempfile.mkdtemp())
r = subprocess.run([sys.executable, os.path.join(HERE, "server.py")], env=env, capture_output=True, text=True, timeout=20)
check("the service refuses to start without a token", (r.returncode != 0, "VIDEO_TOKEN" in r.stderr), (True, True))

s = Svc(idle=60)
st = s.req({"prompt": "orphan check"})[0]; alive = s.comfy_alive(); s.close(); time.sleep(0.5)
check("SIGTERM to the service stops its ComfyUI too (no orphan holding RAM, VRAM and the port)", (st, alive, s.comfy_alive()), (200, True, False))

print("vidgen server_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
