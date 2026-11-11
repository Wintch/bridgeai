#!/usr/bin/env python3
"""Offline test of gpu-host/imggen/server.py with a fake ComfyUI (no GPU, no model, no network beyond loopback)."""
import base64, io, json, os, signal, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Svc:
    def __init__(self, mode="ok", vram=20000, idle=2.0, job_timeout=6.0, token="tok"):
        self.work = tempfile.mkdtemp(prefix="imggen-work-")
        self.log = os.path.join(tempfile.mkdtemp(prefix="imggen-log-"), "graphs.jsonl")
        self.port, self.cport, self.token = free_port(), free_port(), token
        nv = os.path.join(self.work, "..", f"nvsmi-{self.port}.sh")
        open(nv, "w").write(f"#!/bin/sh\necho {vram}\n"); os.chmod(nv, 0o755)
        env = dict(os.environ, GPU_PROBE=os.environ.get('GPU_PROBE_TEST', 'true'), GPU_CHECK_S='1', PORT=str(self.port), IMAGE_TOKEN=token, WORK=self.work, COMFY_PORT=str(self.cport),
                   COMFY_CMD=f"{sys.executable} {HERE}/fake_comfy.py", COMFY_DIR="", IDLE_S=str(idle), JOB_TIMEOUT=str(job_timeout),
                   READY_TIMEOUT="20", NVSMI=nv, FAKE_MODE=mode, COMFY_FAKE_LOG=self.log, VRAM_NEED_MB="7500")
        self.out = tempfile.NamedTemporaryFile("w+", delete=False)
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")], env=env, stdout=self.out, stderr=subprocess.STDOUT)
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/healthz", timeout=1); break
            except Exception:
                time.sleep(0.1)

    def req(self, body=None, auth=True, path="/image", raw=None):
        data = raw if raw is not None else json.dumps(body).encode()
        h = {"Content-Type": "application/json"}
        if auth:
            h["Authorization"] = f"Bearer {self.token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=h, method="POST"), timeout=30) as r:
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

    def logtext(self):
        self.out.flush(); return open(self.out.name).read()

    def close(self):
        self.p.send_signal(signal.SIGTERM)
        try:
            self.p.wait(20)
        except subprocess.TimeoutExpired:
            self.p.kill()


PNG_MAGIC_T = b"\x89PNG\r\n\x1a\n"


def png_info(b):
    from PIL import Image
    im = Image.open(io.BytesIO(b)); return im.size, dict(im.info), im.format


s = Svc()
try:
    check("healthz answers", s.get("/healthz"), (200, "ok image"))
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
    st, body, hdr = s.req({"prompt": SECRET, "quality": "fast", "size": "832x1216", "seed": 7})
    check("a valid request returns a PNG", (st, body[:8], hdr.get("Content-Type")), (200, b"\x89PNG\r\n\x1a\n", "image/png"))
    size, info, fmt = png_info(body)
    check("the delivered PNG has no text chunks (metadata stripped by the re-encode)", (fmt, [k for k in info if k in ("prompt", "workflow", "parameters")]), ("PNG", []))
    check("headers carry seed and tier only", (hdr.get("X-Image-Seed"), hdr.get("X-Image-Quality")), ("7", "fast"))
    g = s.graphs()[-1]
    check("the graph is the fixed template with the request values", (g["1"]["inputs"]["ckpt_name"], g["2"]["inputs"]["text"], g["4"]["inputs"]["width"], g["4"]["inputs"]["height"], g["5"]["inputs"]["steps"], g["5"]["inputs"]["seed"], g["5"]["inputs"]["cfg"]),
          ("sdxl_lightning_4step.safetensors", SECRET, 832, 1216, 4, 7, 1.0))
    check("only the seven fixed nodes exist", sorted(g), ["1", "2", "3", "4", "5", "6", "7"])
    check("the output prefix is a random staging path", g["7"]["inputs"]["filename_prefix"].startswith("stg/") and len(g["7"]["inputs"]["filename_prefix"].split("/")[1]) == 32, True)
    check("the staging directory is gone after the answer", os.path.exists(os.path.join(s.work, "out", "stg", g["7"]["inputs"]["filename_prefix"].split("/")[1])), False)
    check("the prompt text never appears in the service log", SECRET.split()[-1] in s.logtext() or "lighthouse" in s.logtext(), False)

    st2, body2, _ = s.req({"prompt": "a different picture", "seed": 8})
    g2 = s.graphs()[-1]
    check("two jobs use two different staging tokens and different images", (g["7"]["inputs"]["filename_prefix"] != g2["7"]["inputs"]["filename_prefix"], body != body2, st2), (True, True, 200))
    check("no leftover staging directory after two jobs", os.listdir(os.path.join(s.work, "out", "stg")) if os.path.isdir(os.path.join(s.work, "out", "stg")) else [], [])

    # validation: every refusal is a fixed sentence, never the input
    bad = [{"prompt": ""}, {"prompt": "x" * 801}, {"prompt": "ok", "size": "99999x1"}, {"prompt": "ok", "quality": "ultra"}, {"prompt": "ok", "seed": -1},
           {"prompt": "ok", "seed": True}, {"prompt": "ok", "size": None}, {"prompt": "ok", "size": ["1024x1024"]},
           {"prompt": "ok", "quality": None}, {"prompt": "ok", "extra": 1}, {"prompt": 5}, {"prompt": "use embedding:evil now"}, {"prompt": "ok", "ckpt_name": "../../x"},
           {"prompt": "ok", "filename_prefix": "../../etc"}, ["not", "a", "dict"]]
    codes = [s.req(b)[0] for b in bad]
    check("bad requests are all refused with 400", codes, [400] * len(bad))
    st, body, _ = s.req({"prompt": "ok", "ckpt_name": "../../PWNED"})
    check("a refusal never echoes the input", b"PWNED" in body or b"../" in body, False)
    check("invalid JSON and an oversized body are 400", (s.req(raw=b"{not json")[0], s.req(raw=b"x" * 5000)[0]), (400, 400))
    check("no token is 401, a wrong token is 401", (s.req({"prompt": "ok"}, auth=False)[0], Svc.req(type("X", (), {"port": s.port, "token": "wrong"})(), {"prompt": "ok"})[0]), (401, 401))
    check("an unknown path is 404", s.req({"prompt": "ok"}, path="/admin")[0], 404)
    def model_of(q):
        st_ = s.req({"prompt": "t"} if q is None else {"prompt": "t", "quality": q})[0]
        g_ = s.graphs()[-1]["1"]["inputs"]
        return st_, g_.get("ckpt_name") or g_.get("unet_name")
    check("all tiers map to their models (base = photo; no quality = better)", [model_of(q) for q in ("fast", "better", "photo", "base", None)],
          [(200, "sdxl_lightning_4step.safetensors"), (200, "flux-2-klein-4b.safetensors"), (200, "z_image_turbo_bf16.safetensors"),
           (200, "z_image_turbo_bf16.safetensors"), (200, "flux-2-klein-4b.safetensors")])
    gk = (s.req({"prompt": "comic KLEIN-TEXT", "quality": "better", "size": "1216x832", "seed": 9}), s.graphs()[-1])[1]
    check("the klein graph: flux2 text encoder, 4 steps, size and seed in place, prompt only in the positive node",
          (gk["1c"]["inputs"]["type"], gk["4c"]["inputs"]["steps"], gk["4"]["inputs"]["width"], gk["4"]["inputs"]["height"], gk["4n"]["inputs"]["noise_seed"],
           gk["2"]["inputs"]["text"], gk["3"]["inputs"]["text"], gk["7"]["inputs"]["filename_prefix"].startswith("stg/")),
          ("flux2", 4, 1216, 832, 9, "comic KLEIN-TEXT", "", True))
    gz = (s.req({"prompt": "photo ZIMAGE-TEXT", "quality": "photo", "seed": 5}), s.graphs()[-1])[1]
    check("the z-image graph: lumina2 text encoder, AuraFlow shift 3, 8 steps, CFG 1, zeroed negative",
          (gz["1c"]["inputs"]["type"], gz["1m"]["inputs"]["shift"], gz["5"]["inputs"]["steps"], gz["5"]["inputs"]["cfg"], gz["3"]["class_type"], gz["5"]["inputs"]["seed"]),
          ("lumina2", 3.0, 8, 1.0, "ConditioningZeroOut", 5))

    # the X-Image-Size header on every 200, with or without a ref
    st, _, hdr = s.req({"prompt": "size header", "size": "832x1216"})
    check("a text-only request answers with X-Image-Size", (st, hdr.get("X-Image-Size")), (200, "832x1216"))
    check("and the default size is 1024x1024", s.req({"prompt": "size header"})[2].get("X-Image-Size"), "1024x1024")

    # "ref": a photo to edit (klein only)
    from PIL import Image, PngImagePlugin
    def photo(w, h, fmt="JPEG", orient=None, text=False):
        im = Image.new("RGB", (w, h), (200, 120, 40))
        for x in range(0, w, 7):                                   # some structure, so the crop and resize do real work
            im.putpixel((x, x % h), (10, 20, 30))
        b = io.BytesIO()
        kw = {}
        if orient:
            ex = Image.Exif(); ex[0x0112] = orient; kw["exif"] = ex.tobytes()
        if text:
            meta = PngImagePlugin.PngInfo(); meta.add_text("prompt", "SECRET-PROMPT-IN-METADATA"); kw["pnginfo"] = meta
        im.save(b, fmt, **kw)
        return b.getvalue()
    b64 = lambda raw: base64.b64encode(raw).decode()
    in_dir = os.path.join(s.work, "in")
    def staged_left():
        return [f for f in os.listdir(in_dir) if f.startswith("ref-")] if os.path.isdir(in_dir) else []
    SECRET_REF = "a portrait SECRET-REF-PROMPT"
    ref_raw = photo(600, 900, text=False)
    n0 = len(s.graphs())
    st, body, hdr = s.req({"prompt": SECRET_REF, "ref": b64(ref_raw), "seed": 11})
    gr = s.graphs()[-1] if len(s.graphs()) > n0 else {}
    check("a ref with no size and no quality is accepted (tall photo -> klein, 832x1216)",
          (st, body[:8], hdr.get("X-Image-Size"), hdr.get("X-Image-Quality"), hdr.get("X-Image-Seed")), (200, b"\x89PNG\r\n\x1a\n", "832x1216", "better", "11"))
    if gr:
        name = gr["r1"]["inputs"]["image"]
        check("the graph has the four ref nodes and the guider uses the ReferenceLatent conditionings",
              ([gr[k]["class_type"] for k in ("r1", "r2", "2r", "3r")], gr["r2"]["inputs"], gr["2r"]["inputs"], gr["3r"]["inputs"], gr["4g"]["inputs"]["positive"], gr["4g"]["inputs"]["negative"]),
              (["LoadImage", "VAEEncode", "ReferenceLatent", "ReferenceLatent"], {"pixels": ["r1", 0], "vae": ["1v", 0]}, {"conditioning": ["2", 0], "latent": ["r2", 0]},
               {"conditioning": ["3", 0], "latent": ["r2", 0]}, ["2r", 0], ["3r", 0]))
        check("the klein graph is otherwise the text-only one (unet, size, prompt only in the positive node)",
              (gr["1"]["inputs"]["unet_name"], gr["4"]["inputs"]["width"], gr["4"]["inputs"]["height"], gr["2"]["inputs"]["text"], gr["3"]["inputs"]["text"], gr["5"]["inputs"]["guider"]),
              ("flux-2-klein-4b.safetensors", 832, 1216, SECRET_REF, "", ["4g", 0]))
        check("ComfyUI gets a server-chosen name, and the file was in the input folder during the job as a clean exact-size PNG",
              (len(name) == len("ref-") + 32 + 4 and name.startswith("ref-") and name.endswith(".png") and "/" not in name, gr["_ref_staged"], gr["_ref_info"]),
              (True, True, ["PNG", 832, 1216, "RGB", []]))
        check("the staged ref is gone after the job", staged_left(), [])
    check("neither the ref nor the prompt reaches the log, which only says ref=True",
          ("SECRET-REF" in s.logtext() or b64(ref_raw)[:40] in s.logtext(), '"ref": true' in s.logtext()), (False, True))
    # shapes: EXIF rotation, explicit size, a square PNG with metadata, a WebP
    n0 = len(s.graphs())
    st, _, hdr = s.req({"prompt": "r", "ref": b64(photo(900, 600, orient=6))})
    check("a landscape JPEG with EXIF orientation 6 is transposed to portrait first -> 832x1216", (st, hdr.get("X-Image-Size")), (200, "832x1216"))
    st, _, hdr = s.req({"prompt": "r", "ref": b64(photo(600, 900)), "size": "1216x832"})
    g_ = s.graphs()[-1]
    check("an explicit size is honoured (the photo is cover-cropped to it)", (st, hdr.get("X-Image-Size"), g_["4"]["inputs"]["width"], g_["_ref_info"][1:3]), (200, "1216x832", 1216, [1216, 832]))
    st, _, hdr = s.req({"prompt": "r", "ref": b64(photo(500, 480, "PNG", text=True)), "quality": "better"})
    g_ = s.graphs()[-1]
    check("a nearly square PNG with a text chunk -> 1024x1024, and no metadata reaches ComfyUI", (st, hdr.get("X-Image-Size"), g_["_ref_info"]), (200, "1024x1024", ["PNG", 1024, 1024, "RGB", []]))
    st, _, hdr = s.req({"prompt": "r", "ref": b64(photo(1200, 700, "WEBP"))})
    check("a WebP is accepted; a wide one -> 1216x832", (st, hdr.get("X-Image-Size")), (200, "1216x832"))
    check("all those jobs cleaned up their staged files", staged_left(), [])
    # refusals: nothing reaches ComfyUI and nothing is left behind
    n0 = len(s.graphs())
    good = b64(ref_raw)
    big = b"\xff\xd8\xff" + b"\0" * (8 * 1024 * 1024 - 2)          # one byte over MAX_REF
    ok_edge = b"\xff\xd8\xff" + b"\0" * (8 * 1024 * 1024 - 3)       # exactly MAX_REF: passes the size gates, fails the decode
    bad = {
        "quality photo": {"prompt": "r", "ref": good, "quality": "photo"},
        "quality fast": {"prompt": "r", "ref": good, "quality": "fast"},
        "quality base": {"prompt": "r", "ref": good, "quality": "base"},
        "bad size": {"prompt": "r", "ref": good, "size": "5x5"},
        "size null": {"prompt": "r", "ref": good, "size": None},
        "garbage bytes": {"prompt": "r", "ref": b64(os.urandom(300))},
        "bad base64": {"prompt": "r", "ref": "not base64 !!!"},
        "base64 with a newline": {"prompt": "r", "ref": good[:40] + "\n" + good[40:]},
        "empty ref": {"prompt": "r", "ref": ""},
        "ref not a string": {"prompt": "r", "ref": 5},
        "ref null": {"prompt": "r", "ref": None},
        "11 bytes": {"prompt": "r", "ref": b64(b"\xff\xd8\xff" + b"\0" * 8)},
        "jpeg magic, undecodable": {"prompt": "r", "ref": b64(b"\xff\xd8\xff\xe0" + os.urandom(500))},
        "png magic, undecodable": {"prompt": "r", "ref": b64(PNG_MAGIC_T + os.urandom(500))},
        "truncated jpeg": {"prompt": "r", "ref": b64(ref_raw[:len(ref_raw) // 2])},
        "riff but not webp": {"prompt": "r", "ref": b64(b"RIFF\0\0\0\0WAVEfmt " + b"\0" * 40)},
        "a gif": {"prompt": "r", "ref": b64(photo(40, 40, "GIF"))},
        "over 8 MiB": {"prompt": "r", "ref": b64(big)},
        "exactly 8 MiB of nothing": {"prompt": "r", "ref": b64(ok_edge)},
    }
    got = {k: s.req(v)[0] for k, v in bad.items()}
    check("every bad ref is refused with 400 (wrong tier, garbage, bad base64, undecodable, oversize)", got, {k: 400 for k in bad})
    st, body, _ = s.req(bad["jpeg magic, undecodable"])
    check("a refused ref says nothing about it", (body, len(s.graphs()) - n0, staged_left()), (b"bad request", 0, []))
    check("a 70 kB body that is not JSON is 400", s.req(raw=b"x" * 70000)[0], 400)
    raw_sock = socket.create_connection(("127.0.0.1", s.port), timeout=10)      # a Content-Length over MAX_BODY is refused without reading it
    raw_sock.sendall(f"POST /image HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {s.token}\r\nContent-Length: 20000000\r\n\r\n".encode())
    check("a Content-Length over the body limit is 400 at once", raw_sock.recv(64)[:12], b"HTTP/1.0 400"); raw_sock.close()
    check("the service still works after the refusals", s.req({"prompt": "text only again"})[0], 200)

    # idle stop and restart on demand
    check("ComfyUI is alive right after a job", s.comfy_alive(), True)
    time.sleep(5)
    check("ComfyUI is stopped after the idle window (VRAM goes back)", s.comfy_alive(), False)
    check("status says asleep again", json.loads(s.get("/status")[1])["state"], "asleep")
    check("the next request starts it again", s.req({"prompt": "again"})[0], 200)
finally:
    s.close()

# one job at a time
s = Svc(mode="slow", job_timeout=6.0)
try:
    res = []
    t = threading.Thread(target=lambda: res.append(s.req({"prompt": "slow one"})[0]))
    t.start(); time.sleep(1.5)
    check("a second request during a job gets 429", s.req({"prompt": "second"})[0], 429)
    t.join(30)
    check("a job that never completes is stopped with 504 and the process is killed", (res, s.comfy_alive()), ([504], False))
finally:
    s.close()

# a hostile output directory: symlink plus an extra file
s = Svc(mode="symlink")
try:
    st, body, _ = s.req({"prompt": "x"})
    check("a staging directory with a symlink or extra file is refused (500), nothing is read", (st, b"PNG" in body[:8], b"localhost" in body), (500, False, False))
    check("and it is cleaned up", os.listdir(os.path.join(s.work, "out", "stg")) if os.path.isdir(os.path.join(s.work, "out", "stg")) else [], [])
finally:
    s.close()

s = Svc(mode="error")
try:
    check("ComfyUI reporting an error is a fixed 500", s.req({"prompt": "x"})[0], 500)
    from PIL import Image
    _b = io.BytesIO(); Image.new("RGB", (64, 48), (1, 2, 3)).save(_b, "JPEG")
    check("a failed job with a ref still removes the staged ref", (s.req({"prompt": "x", "ref": base64.b64encode(_b.getvalue()).decode()})[0],
          [f for f in os.listdir(os.path.join(s.work, "in")) if f.startswith("ref-")]), (500, []))
finally:
    s.close()

# no VRAM
s = Svc(vram=3000)
try:
    st, body, _ = s.req({"prompt": "x"})
    check("without free VRAM the answer is 503 and ComfyUI is never started", (st, s.comfy_alive(), s.graphs()), (503, False, []))
finally:
    s.close()

# no token configured: the service refuses to run
env = dict(os.environ, IMAGE_TOKEN="", PORT=str(free_port()), WORK=tempfile.mkdtemp())
r = subprocess.run([sys.executable, os.path.join(HERE, "server.py")], env=env, capture_output=True, text=True, timeout=20)
check("the service refuses to start without a token", (r.returncode != 0, "IMAGE_TOKEN" in r.stderr), (True, True))

s = Svc(idle=60)
st = s.req({"prompt": "orphan check"})[0]; alive = s.comfy_alive(); s.close(); time.sleep(0.5)
check("SIGTERM to the service stops its ComfyUI too (no orphan holding RAM, VRAM and the port)", (st, alive, s.comfy_alive()), (200, True, False))

print("imggen server_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
