#!/usr/bin/env python3
"""
imggen -- text-to-image (and photo-guided image edit) over HTTP for Hermes, on the GPU host (v0; the operator's own stack first).

  GET  /healthz     "ok image", or 503 "no gpu: ..." when CUDA cannot see the card (GPU watch below)
  GET  /status      {"state": "idle|running|asleep", "queued": 0, "slots": 1, "busy": 0|1, "eta_s", "avg_s"}   (a bare state, no person data)
  POST /image       JSON {"prompt": str, "size": "1024x1024|832x1216|1216x832", "quality": "fast|better|photo" (base = photo), "seed": int,
                          "ref": base64 of a JPEG/PNG/WebP photo, 12 bytes..8 MiB (optional; FLUX.2 klein only)}
                    -> 200 image/png, headers X-Image-Seconds, X-Image-Seed, X-Image-Quality, X-Image-Size ("<w>x<h>")
                    -> 400 bad_request | 401 | 429 busy | 503 no_vram | 504 timeout | 500 failed   (fixed text, never the prompt)

Design (GPU_MEDIA_TOOLS.md sections 7, 8, 8.10; it follows the adversarial review, v0 = text only, "ref" added after):
- ComfyUI is NOT exposed. It listens on 127.0.0.1 inside this container and this wrapper is its only client. The agent
  supplies a prompt, a size from a closed list, a quality tier and a seed: never a graph, a file name or a path.
- The graph is built from a template by node id (values set as data, no string substitution). The output prefix is
  "stg/<128-bit random token>/o": one fresh staging directory per job; the file is found by listing that directory
  only (no symlinks, exactly one PNG, magic checked), re-encoded with Pillow (fresh PNG, no text chunks), and the
  staging directory and the ComfyUI history entry are removed before the answer is sent.
- "ref": only the "better" tier takes it (FLUX.2 klein is the edit-capable model; any other
  tier with a ref is 400, and no "quality" with a ref means "better"). Magic bytes are checked, then Pillow opens it (at most 40 million
  pixels; a decode error is 400), EXIF-transposes, converts to RGB, cover-crops (centre) and resizes to exactly the output size, and
  saves a fresh PNG with no metadata as WORK/in/ref-<random token>.png: ComfyUI only ever sees that server-chosen name, never a name or
  path from the request. With no "size" the server takes the entry of SIZES whose aspect ratio is closest to the photo's. The staged
  file is removed after the job (also on failure). The graph adds LoadImage -> VAEEncode -> ReferenceLatent on the positive and the
  negative conditioning. The log says ref=True and nothing else about it (no bytes, no hash, no name).
- One job at a time (a second request gets 429). ComfyUI runs with --disable-metadata, --disable-all-custom-nodes,
  --disable-partner-nodes, --cache-classic and its input, output, temp and user directories on the tmpfs WORK.
- The model stays loaded for IDLE_S seconds after the last job and then the ComfyUI process exits, so the 7 GB of VRAM
  go back to VR, Resolve or the LLM. Before starting it the wrapper checks free VRAM (503 no_vram, never an OOM).
- Logs carry the time, tier, size, seed, a short SHA-256 of the prompt (abuse trail without the text) and the result.
Stdlib plus Pillow, like the other services here.
"""
import base64
import binascii
import hashlib
import hmac
import io
import json
import math
import os
import secrets
import signal
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8660"))
TOKEN = os.environ.get("IMAGE_TOKEN", "")
WORK = os.environ.get("WORK", "/work")
COMFY_DIR = os.environ.get("COMFY_DIR", "/w/ComfyUI")
COMFY_PORT = int(os.environ.get("COMFY_PORT", "8189"))
COMFY_CMD = os.environ.get("COMFY_CMD", "")               # tests replace ComfyUI with a fake
EXTRA_PATHS = os.environ.get("EXTRA_PATHS", "/app/extra_paths.yaml")
IDLE_S = float(os.environ.get("IDLE_S", "60"))
JOB_TIMEOUT = float(os.environ.get("JOB_TIMEOUT", "150"))
READY_TIMEOUT = float(os.environ.get("READY_TIMEOUT", "90"))
VRAM_NEED_MB = int(os.environ.get("VRAM_NEED_MB", "6500"))   # the models are ~6.6 GB staged with dynamic VRAM loading; a free card shows ~7.4 GB
NVSMI = os.environ.get("NVSMI", "nvidia-smi")
MAX_PROMPT = 800
MAX_REF = 8 * 1024 * 1024                  # decoded bytes of the "ref" photo
MAX_REF_PIXELS = 40_000_000                 # decode bound for the ref (Pillow's own bomb guard is 2x this)
MAX_BODY = 4096 + MAX_REF * 4 // 3 + 4     # the JSON with a base64 ref at the limit
MAX_PNG = 40 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# quality tier -> model and sampler (measured at 1024x1024, 100 W, warm; blind panel in aibridge/GPU_RENTAL_AND_MODELS.md):
#   fast   SDXL Lightning 4-step       3.5 s   overall 6.0/10 (merges limbs, drops requested objects, no readable text)
#   better FLUX.2 klein 4B, 4 steps    9.5 s   overall 8.2/10 (keeps the asked style: comic, game, illustration; good text)
#   photo  Z-Image Turbo bf16, 8 steps 18 s    overall 8.4/10 (photoreal look whatever the style; best for photos)
# "base" is kept as a name for "photo" (older gateways send it). Apache-2.0 weights except SDXL (OpenRAIL++).
# bf16 is twice as fast as int8_convrot on the 8 GB Ampere card (18 s vs 36 s warm; peak RAM 10.8 GB vs 6.4 GB)
ZIMAGE_UNET = os.environ.get("ZIMAGE_UNET", "z_image_turbo_bf16.safetensors")
TIERS = {
    "fast": {"kind": "sdxl", "ckpt": "sdxl_lightning_4step.safetensors", "steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "sgm_uniform"},
    "better": {"kind": "klein", "unet": "flux-2-klein-4b.safetensors", "clip": "qwen_3_4b_fp4_flux2.safetensors", "vae": "flux2-vae.safetensors", "steps": 4},
    "photo": {"kind": "zimage", "unet": ZIMAGE_UNET, "clip": "qwen_3_4b_fp8_mixed.safetensors", "vae": "ae.safetensors", "steps": 8},
}
TIERS["base"] = TIERS["photo"]
DEFAULT_TIER = "better"
SIZES = {"1024x1024": (1024, 1024), "832x1216": (832, 1216), "1216x832": (1216, 832)}
NEGATIVE = "blurry, low quality, watermark"


class Refuse(Exception):
    def __init__(self, code, text):
        super().__init__(text)
        self.code, self.text = code, text


def log(**kw):
    print(json.dumps(dict(ts=time.strftime("%Y-%m-%dT%H:%M:%S"), **kw), ensure_ascii=False), flush=True)


def ref_magic_ok(raw):
    return raw.startswith(b"\xff\xd8\xff") or raw.startswith(PNG_MAGIC) or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")


def validate(body):
    """The request as (prompt, size, tier, seed, ref); anything else is refused with a fixed sentence.
    size is None when a ref came without a size (prepare_ref picks it); ref is the decoded photo bytes or None."""
    if not isinstance(body, dict) or set(body) - {"prompt", "size", "quality", "seed", "ref"}:
        raise Refuse(400, "bad_request")
    prompt = body.get("prompt")
    if not isinstance(prompt, str):
        raise Refuse(400, "bad_request")
    prompt = "".join(c for c in prompt if c == "\n" or c >= " ").strip()
    if not prompt or len(prompt) > MAX_PROMPT or "embedding:" in prompt.lower():
        raise Refuse(400, "bad_request")
    ref = None
    if "ref" in body:
        enc = body["ref"]
        if not isinstance(enc, str) or len(enc) > MAX_REF * 4 // 3 + 4:
            raise Refuse(400, "bad_request")
        try:
            ref = base64.b64decode(enc, validate=True)
        except (binascii.Error, ValueError):
            raise Refuse(400, "bad_request")
        if not 12 <= len(ref) <= MAX_REF or not ref_magic_ok(ref):
            raise Refuse(400, "bad_request")
    if "size" in body:                             # present means it must be a listed size: null is refused too
        size = body["size"]
        if not isinstance(size, str) or size not in SIZES:
            raise Refuse(400, "bad_request")
    else:
        size = None if ref else "1024x1024"
    tier = body.get("quality", DEFAULT_TIER)       # DEFAULT_TIER is "better", the one tier that takes a ref
    if not isinstance(tier, str) or tier not in TIERS or (ref and tier != "better"):
        raise Refuse(400, "bad_request")
    seed = body.get("seed")
    if seed is None:
        seed = secrets.randbelow(2 ** 32)
    elif not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2 ** 32:
        raise Refuse(400, "bad_request")
    return prompt, size, tier, seed, ref


def prepare_ref(raw, size):
    """(size, png bytes): the photo EXIF-transposed, RGB, cover-cropped and resized to exactly the output size, as a fresh PNG
    with no metadata. size None picks the SIZES entry whose aspect ratio is closest to the photo's. Any decode problem is 400."""
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = MAX_REF_PIXELS
    try:
        im = Image.open(io.BytesIO(raw))
        if im.format not in ("JPEG", "PNG", "WEBP") or im.width * im.height > MAX_REF_PIXELS:
            raise Refuse(400, "bad_request")
        im.load()
        im = ImageOps.exif_transpose(im).convert("RGB")
        if im.width < 1 or im.height < 1:
            raise Refuse(400, "bad_request")
        if size is None:
            ratio = math.log(im.width / im.height)
            size = min(SIZES, key=lambda k: abs(math.log(SIZES[k][0] / SIZES[k][1]) - ratio))
        w, h = SIZES[size]
        im = ImageOps.fit(im, (w, h), Image.LANCZOS, centering=(0.5, 0.5))
        out = io.BytesIO()
        Image.frombytes("RGB", (w, h), im.tobytes()).save(out, "PNG")
    except Refuse:
        raise
    except Exception:                              # undecodable, truncated, a decompression bomb, ...
        raise Refuse(400, "bad_request")
    return size, out.getvalue()


def build_graph(prompt, size, tier, seed, prefix, ref_name=None):
    """The workflow as data: node ids and input names are fixed here per model, only these values come from the request.
    The graphs follow ComfyUI's own templates (Text to Image (Z-Image-Turbo), Flux.2 Klein 4B) with every required input given.
    ref_name (klein only) is the server-chosen file name of the staged photo in ComfyUI's input folder."""
    t, (w, h) = TIERS[tier], SIZES[size]
    if ref_name is not None and t["kind"] != "klein":
        raise ValueError("ref needs the klein tier")
    save = {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": prefix}}
    if t["kind"] == "sdxl":
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": t["ckpt"]}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": prompt}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": NEGATIVE}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
                                                        "seed": seed, "steps": t["steps"], "cfg": t["cfg"], "sampler_name": t["sampler"],
                                                        "scheduler": t["scheduler"], "denoise": 1.0}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": save,
        }
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": t["unet"], "weight_dtype": "default"}},
        "1c": {"class_type": "CLIPLoader", "inputs": {"clip_name": t["clip"], "type": "lumina2" if t["kind"] == "zimage" else "flux2"}},
        "1v": {"class_type": "VAELoader", "inputs": {"vae_name": t["vae"]}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1c", 0], "text": prompt}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1v", 0]}},
        "7": save,
    }
    if t["kind"] == "zimage":
        g.update({
            "1m": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
            "3": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
            "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1m", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
                                                        "seed": seed, "steps": t["steps"], "cfg": 1.0, "sampler_name": "res_multistep",
                                                        "scheduler": "simple", "denoise": 1.0}},
        })
    else:   # FLUX.2 klein 4B (distilled): 4 steps, CFG 1, empty negative
        g.update({
            "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1c", 0], "text": ""}},
            "4": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
            "4n": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "4s": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "4c": {"class_type": "Flux2Scheduler", "inputs": {"steps": t["steps"], "width": w, "height": h}},
            "4g": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "cfg": 1.0}},
            "5": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["4n", 0], "guider": ["4g", 0], "sampler": ["4s", 0],
                                                                    "sigmas": ["4c", 0], "latent_image": ["4", 0]}},
        })
        if ref_name is not None:     # the photo is encoded once and added to both conditionings (klein's image-edit template)
            g.update({
                "r1": {"class_type": "LoadImage", "inputs": {"image": ref_name}},
                "r2": {"class_type": "VAEEncode", "inputs": {"pixels": ["r1", 0], "vae": ["1v", 0]}},
                "2r": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["2", 0], "latent": ["r2", 0]}},
                "3r": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["3", 0], "latent": ["r2", 0]}},
            })
            g["4g"]["inputs"].update(positive=["2r", 0], negative=["3r", 0])
    return g


# GPU watch: a systemd reload on the host can take the GPU away from a container that is already running
# (cgroup v2 + nvidia-container-toolkit); afterwards every job failed within seconds while /healthz still said ok. A child
# process asks the CUDA driver (libcuda: cuInit + cuDeviceGetCount) every GPU_CHECK_S seconds; while that fails /healthz
# answers 503 "no gpu", so the gateway skips this host and Zabbix (which polls /healthz) raises the problem.
# GPU_CHECK_S=0 turns it off; GPU_PROBE (tests) replaces the probe with a command whose exit code is the answer.
GPU_CHECK_S = float(os.environ.get("GPU_CHECK_S", "60"))
GPU_PROBE = os.environ.get("GPU_PROBE", "")
GPU = {"ok": True, "why": ""}
_CUDA_PY = ("import ctypes, sys\n"
            "try:\n    c = ctypes.CDLL('libcuda.so.1')\nexcept OSError:\n    sys.exit(3)\n"
            "n = ctypes.c_int(0)\n"
            "sys.exit(0 if c.cuInit(0) == 0 and c.cuDeviceGetCount(ctypes.byref(n)) == 0 and n.value > 0 else 4)\n")


def gpu_probe():
    """(ok, why): whether CUDA sees a GPU from inside this container right now."""
    cmd = GPU_PROBE.split() if GPU_PROBE else [sys.executable, "-c", _CUDA_PY]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return False, type(e).__name__
    return r.returncode == 0, {0: "", 3: "no CUDA driver library", 4: "CUDA sees no GPU"}.get(r.returncode, f"probe exit {r.returncode}")


def gpu_loop():
    while GPU_CHECK_S > 0:
        ok, why = gpu_probe()
        if ok != GPU["ok"]:
            log(event="gpu", ok=ok, why=why)
        GPU.update(ok=ok, why=why)
        time.sleep(GPU_CHECK_S)


def free_vram_mb():
    try:
        out = subprocess.run([NVSMI, "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
        return int(out.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def http_json(method, path, body=None, timeout=10):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{COMFY_PORT}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw.strip() else {}


class Comfy:
    """The ComfyUI process: started on demand, stopped after IDLE_S without a job."""

    def __init__(self):
        self.proc = None
        self.last = 0.0
        self.running = False
        self.t0 = 0.0                          # start of the running job (for /status eta_s)
        self.avg = 30.0                       # rolling mean of a job's seconds (a fifth of each new one)
        self.stopping = False                  # the idle loop holds the lock to stop ComfyUI (a few seconds)
        self.lock = threading.Lock()          # one job at a time (taken without waiting, except behind an idle stop)

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def command(self):
        if COMFY_CMD:
            return COMFY_CMD.split()
        return [sys.executable, "main.py", "--listen", "127.0.0.1", "--port", str(COMFY_PORT),
                "--output-directory", f"{WORK}/out", "--temp-directory", f"{WORK}/tmp", "--input-directory", f"{WORK}/in",
                "--user-directory", f"{WORK}/user", "--extra-model-paths-config", EXTRA_PATHS, "--disable-auto-launch",
                "--disable-metadata", "--disable-all-custom-nodes", "--disable-partner-nodes", "--cache-classic"]

    def ensure(self):
        if self.alive():
            return
        free = free_vram_mb()
        if free is not None and free < VRAM_NEED_MB:
            raise Refuse(503, "no_vram")
        for d in ("out", "tmp", "in", "user", "home"):
            shutil.rmtree(f"{WORK}/{d}", ignore_errors=True)
            os.makedirs(f"{WORK}/{d}", exist_ok=True)
        env = dict(os.environ, HOME=f"{WORK}/home", COMFY_FAKE_WORK=WORK, COMFY_FAKE_PORT=str(COMFY_PORT))
        self.proc = subprocess.Popen(self.command(), cwd=COMFY_DIR if os.path.isdir(COMFY_DIR) else None, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        while time.time() - t0 < READY_TIMEOUT:
            if not self.alive():
                raise Refuse(500, "failed")
            try:
                http_json("GET", "/system_stats", timeout=2)
                return
            except Exception:
                time.sleep(0.4)
        self.stop()
        raise Refuse(504, "timeout")

    def stop(self):
        p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(15)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(5)
        for d in ("out", "tmp", "in", "user"):          # nothing of a job outlives the process
            shutil.rmtree(f"{WORK}/{d}", ignore_errors=True)

    def generate(self, graph, token):
        """Run one graph and return the PNG bytes found in this job's own staging directory."""
        pid = str(uuid.uuid4())
        stage = os.path.join(WORK, "out", "stg", token)
        try:
            http_json("POST", "/prompt", {"prompt": graph, "prompt_id": pid})
            t0 = time.time()
            while True:
                if time.time() - t0 > JOB_TIMEOUT:
                    try:
                        http_json("POST", "/interrupt", {"prompt_id": pid})
                    except Exception:
                        pass
                    self.stop()                          # backstop: the process goes, and with it the VRAM
                    raise Refuse(504, "timeout")
                if not self.alive():
                    raise Refuse(500, "failed")
                h = http_json("GET", f"/history/{pid}").get(pid)
                if h and h.get("status", {}).get("completed") is not None:
                    if h["status"].get("status_str") == "error":
                        raise Refuse(500, "failed")
                    break
                time.sleep(0.2)
            return collect(stage)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
            try:
                http_json("POST", "/history", {"delete": [pid]})
            except Exception:
                pass
            shutil.rmtree(os.path.join(WORK, "tmp"), ignore_errors=True)
            os.makedirs(os.path.join(WORK, "tmp"), exist_ok=True)


def collect(stage):
    """Exactly one regular PNG in the staging directory, re-encoded so nothing but pixels leaves."""
    from PIL import Image
    try:
        entries = list(os.scandir(stage))
    except OSError:
        raise Refuse(500, "failed")
    files = [e for e in entries if e.is_file(follow_symlinks=False) and not e.is_symlink()]
    if len(entries) != 1 or len(files) != 1:
        raise Refuse(500, "failed")
    fd = os.open(files[0].path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        raw = f.read(MAX_PNG + 1)
    if len(raw) > MAX_PNG or not raw.startswith(PNG_MAGIC):
        raise Refuse(500, "failed")
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        if im.width * im.height > 4096 * 4096:
            raise Refuse(500, "failed")
        out = io.BytesIO()
        Image.frombytes("RGB", im.size, im.convert("RGB").tobytes()).save(out, "PNG")
    except Refuse:
        raise
    except Exception:
        raise Refuse(500, "failed")
    return out.getvalue()


COMFY = Comfy()


def idle_loop():
    while True:
        time.sleep(max(0.2, min(5.0, IDLE_S / 4)))
        if COMFY.alive() and not COMFY.running and time.time() - COMFY.last > IDLE_S and COMFY.lock.acquire(blocking=False):
            COMFY.stopping = True                    # set at once: a request arriving now waits instead of getting 429
            try:
                if not COMFY.running and time.time() - COMFY.last > IDLE_S:
                    log(event="idle_stop")
                    COMFY.stop()
            finally:
                COMFY.stopping = False
                COMFY.lock.release()


MESSAGES = {400: "bad request", 401: "unauthorized", 429: "busy: one image at a time, try again in a few seconds",
            503: "the GPU is busy with something else right now (no free memory for the image model)",
            504: "the image took too long and was stopped", 500: "the image could not be made"}


class Handler(BaseHTTPRequestHandler):
    server_version = "imggen"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/plain", headers=None):
        body = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self):
        got = self.headers.get("Authorization", "")
        return bool(TOKEN) and hmac.compare_digest(got.encode(), f"Bearer {TOKEN}".encode())

    def do_GET(self):
        if self.path == "/healthz":                  # 503 while the GPU watch says CUDA sees no GPU
            return self._send(200, "ok image") if GPU["ok"] else self._send(503, "no gpu: " + GPU["why"])
        if self.path == "/status":
            state = "running" if COMFY.running else "idle" if COMFY.alive() else "asleep"
            return self._send(200, json.dumps({"state": state, "queued": 0, "slots": 1, "busy": int(COMFY.running), "avg_s": round(COMFY.avg, 1),
                                                    "eta_s": round(max(5.0, COMFY.avg - (time.time() - COMFY.t0)), 1) if COMFY.running else 0.0}), "application/json")
        self._send(404, "not found")

    def do_POST(self):
        if self.path != "/image":
            return self._send(404, "not found")
        if not self._auth():
            return self._send(401, MESSAGES[401])
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= MAX_BODY:
                raise Refuse(400, "bad_request")
            prompt, size, tier, seed, ref = validate(json.loads(self.rfile.read(n)))
            if ref:
                size, ref = prepare_ref(ref, size)   # from here on ref is only the clean, exact-size PNG
        except (Refuse, ValueError, UnicodeError) as e:
            return self._send(400, MESSAGES[400])
        sha = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        if not COMFY.lock.acquire(blocking=False) and not (COMFY.stopping and COMFY.lock.acquire(timeout=40)):
            log(event="busy", quality=tier, size=size, prompt_sha=sha, ref=True if ref else None)
            return self._send(429, MESSAGES[429], headers={"Retry-After": "5"})
        t0 = time.time()
        COMFY.running, COMFY.t0 = True, time.time()
        ref_path = None
        flag = True if ref else None
        try:
            COMFY.ensure()                         # (it wipes the input folder when it starts ComfyUI: stage after it)
            token = secrets.token_hex(16)
            ref_name = None
            if ref:
                ref_name = f"ref-{token}.png"
                ref_path = os.path.join(WORK, "in", ref_name)
                os.makedirs(os.path.dirname(ref_path), exist_ok=True)
                fd = os.open(ref_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as f:
                    f.write(ref)
            png = COMFY.generate(build_graph(prompt, size, tier, seed, f"stg/{token}/o", ref_name), token)
            secs = round(time.time() - t0, 2)
            log(event="done", quality=tier, size=size, seed=seed, prompt_sha=sha, seconds=secs, bytes=len(png), ref=flag)
            return self._send(200, png, "image/png", {"X-Image-Seconds": secs, "X-Image-Seed": seed, "X-Image-Quality": tier, "X-Image-Size": size})
        except Refuse as e:
            log(event="refused", code=e.code, quality=tier, size=size, prompt_sha=sha, seconds=round(time.time() - t0, 1), ref=flag)
            return self._send(e.code, MESSAGES.get(e.code, "failed"))
        except Exception as e:
            log(event="error", kind=type(e).__name__, quality=tier, size=size, prompt_sha=sha, ref=flag)
            return self._send(500, MESSAGES[500])
        finally:
            if ref_path:
                try:
                    os.unlink(ref_path)
                except OSError:
                    pass
            if time.time() - COMFY.t0 > 5:              # quick refusals do not drag the mean down
                COMFY.avg = 0.8 * COMFY.avg + 0.2 * (time.time() - COMFY.t0)
            COMFY.running = False
            COMFY.last = time.time()
            COMFY.lock.release()


def main():
    if not TOKEN:
        sys.exit("IMAGE_TOKEN is required: the service never runs without a token")
    os.makedirs(WORK, exist_ok=True)
    threading.Thread(target=idle_loop, daemon=True).start()
    threading.Thread(target=gpu_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    # SIGTERM (docker stop, run_venv.sh stop, a test closing it) leaves through `finally`, so ComfyUI goes with the service
    # instead of living on with its RAM, VRAM and port (a real one held 8.9 GB and broke the next start).
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    log(event="start", port=PORT, idle_s=IDLE_S)
    try:
        srv.serve_forever()
    finally:
        COMFY.stop()


if __name__ == "__main__":
    main()
