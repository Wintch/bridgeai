#!/usr/bin/env python3
"""
vidgen -- text-to-video with sound over HTTP for Hermes, on the GPU host (v0; the operator's own stack first).
Model: MiniMax H3 (open weights; licence excludes the EU, UK, South Korea and the USA) through the stock ComfyUI nodes, as measured in
aibridge/VIDEO_BENCH_RESULTS.md (B4b): 5 s of 832x480 with stereo audio in ~395 s at 130 W, 18 GB RAM, 7.6 GB VRAM.

  GET  /healthz     "ok video", or 503 "no gpu: ..." when CUDA cannot see the card (GPU watch below)
  GET  /status      {"state": "idle|running|asleep", "queued": 0, "slots": 1, "busy": 0|1, "eta_s", "avg_s"}   (a bare state, no person data)
  POST /video       JSON {"prompt": str, "secs": 2|3|5|8|10, "seed": int}   (8 s at 704x384, 10 s at 608x352)
                    chained segments (a clip longer than 10 s, joined by the caller): add "chain": true (always 608x352, secs 5 or 10)
                    and, from the second segment on, "tail": base64 of an mp4 with the last TAIL_FRAMES frames of the previous segment
                    optional "first": base64 of a JPEG, PNG or WebP picture (up to 8 MiB) the clip starts from (alone or with "chain": true,
                    never together with "tail"); optional "portrait": true swaps width and height (5 s -> 480x832, a chain -> 352x608)
                    -> 200 video/mp4, headers X-Video-Seconds (generation time), X-Video-Seed, X-Video-Length (clip seconds),
                       X-Video-Size ("WxH", the real size, portrait or not)
                    -> 400 bad_request | 401 | 429 busy | 503 no_vram/no_ram | 504 timeout | 500 failed   (fixed text, never the prompt)

A sibling of gpu-host/imggen (same design, read its docstring): ComfyUI only on 127.0.0.1 inside this container, a closed
request (prompt, length from a short list, seed; the size is fixed), the graph built by node id, one fresh staging directory
per job, one job at a time, ComfyUI started on demand and stopped after IDLE_S. What differs:
- Limits sized for a job of minutes: JOB_TIMEOUT 900 s, READY_TIMEOUT 300 s (cold start reads ~45 GB of weights).
- Before starting ComfyUI it needs nearly the whole card free (VRAM_NEED_MB) AND enough free host RAM (RAM_NEED_MB, from
  MemAvailable): the 16 GB text encoder and the 21 GB model are staged through RAM. Either missing is a 503, never an OOM.
  The VRAM check also keeps vidgen from starting while imggen's ComfyUI holds the card (and the other way round).
- The output is exactly one regular .mp4 with an `ftyp` box, under MAX_MP4; it is remuxed with ffmpeg (streams copied,
  all metadata dropped, faststart for Telegram) so nothing but the video and its sound leaves.
Chained segments (VIDEO_BENCH_RESULTS.md B4c, variant B5n): the next segment anchors the last 5 frames of the previous
one at its frame 0 (MiniMaxH3AddGuide, picture only: anchoring their sound left a gap), so the motion goes on across the join. The
service keeps no chain state: the caller sends the tail back with the next request. The tail is re-encoded here (only its first
TAIL_FRAMES video frames, no sound, nothing else) into the ComfyUI input folder under a random name and removed after the job.
The caller drops the first TAIL_FRAMES frames of each later segment and joins them (aibridge gateway makevideo).
Start picture: "first" feeds the first_frame input of MiniMaxH3ImageToVideo, which stretches the picture to the canvas
with no crop. So the picture is cut to exactly the output size first (ffmpeg: scale to cover, center crop, one PNG with no metadata;
vidgen has no Pillow), staged under a random name in the ComfyUI input folder like the tail, and removed after the job. The bytes
are never logged: only first=True. A chain carries "first" on its first segment only (the later ones carry the tail); every
segment carries the same "portrait", since the size must not change inside a chain.
Stdlib plus ffmpeg (both in the comfy-bench image).
"""
import base64
import binascii
import hashlib
import hmac
import json
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

PORT = int(os.environ.get("PORT", "8670"))
TOKEN = os.environ.get("VIDEO_TOKEN", "")
WORK = os.environ.get("WORK", "/work")
COMFY_DIR = os.environ.get("COMFY_DIR", "/w/ComfyUI")
COMFY_PORT = int(os.environ.get("COMFY_PORT", "8190"))
COMFY_CMD = os.environ.get("COMFY_CMD", "")               # tests replace ComfyUI with a fake
EXTRA_PATHS = os.environ.get("EXTRA_PATHS", "/app/extra_paths.yaml")
IDLE_S = float(os.environ.get("IDLE_S", "120"))
JOB_TIMEOUT = float(os.environ.get("JOB_TIMEOUT", "900"))
READY_TIMEOUT = float(os.environ.get("READY_TIMEOUT", "300"))
VRAM_NEED_MB = int(os.environ.get("VRAM_NEED_MB", "7000"))   # H3 peaked at 7.6 GB with dynamic VRAM loading; a free 8 GB card shows ~7.5 GB
RAM_NEED_MB = int(os.environ.get("RAM_NEED_MB", "16000"))
# imggen keeps its model loaded for its IDLE_S (60 s) after a picture: wait for the card to free up before saying 503
# (a video asked 40 s after a picture was refused as busy)
MEM_WAIT_S = float(os.environ.get("MEM_WAIT_S", "90"))    # peak 17.9 GB used during the bench, of which ~3 GB was already in use
NVSMI = os.environ.get("NVSMI", "nvidia-smi")
MEMINFO = os.environ.get("MEMINFO", "/proc/meminfo")
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
MAX_PROMPT = 800
MAX_TAIL = 3 * 1024 * 1024                                    # 5 lossless frames at 608x352 are ~0.3 MB
MAX_FIRST = 8 * 1024 * 1024                                   # a phone photo; the gateway sends it re-encoded and smaller
MAX_BODY = 4096 + MAX_TAIL * 4 // 3 + 4 + MAX_FIRST * 4 // 3 + 4
MAX_MP4 = 200 * 1024 * 1024

FPS = 24.0
# clip length -> size: longer clips at a smaller size keep the same work per job, which is what fits the 8 GB card
# (measured at 130 W: 5 s 832x480 395 s, 8 s 704x384 416 s, 10 s 608x352 421 s; 8 s at 832x480 ran out of VRAM)
SIZE_BY_SECS = {2: (832, 480), 3: (832, 480), 5: (832, 480), 8: (704, 384), 10: (608, 352)}
SECS = tuple(SIZE_BY_SECS)
CHAIN_SIZE = (608, 352)                                       # every segment of a chain at one size (the 10 s size)
CHAIN_SECS = (5, 10)
TAIL_FRAMES = 5                                               # B5n: the smallest clip the guide anchors (17k+5)
STEPS = 8                                                     # with the turbo LoRA (20 without it)
MODEL = {
    "clip": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae": "minimax_h3_video_vae_fp16.safetensors",
    "avae": "minimax_h3_audio_vae_fp32.safetensors",
    "unet": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "lora": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
}


class Refuse(Exception):
    def __init__(self, code, text):
        super().__init__(text)
        self.code, self.text = code, text


def log(**kw):
    print(json.dumps(dict(ts=time.strftime("%Y-%m-%dT%H:%M:%S"), **kw), ensure_ascii=False), flush=True)


def frames(secs):
    """Frames at 24 fps snapped up to the model's 17k+5 grid: 2 s -> 56, 3 s -> 73, 5 s -> 124, 8 s -> 192, 10 s -> 243."""
    n = max(5, round(secs * FPS))
    return n + (5 - n % 17) % 17


def validate(body):
    """The request as (prompt, secs, seed, chain, tail bytes or None, first picture bytes or None, portrait); anything else is
    refused with a fixed sentence."""
    if not isinstance(body, dict) or set(body) - {"prompt", "secs", "seed", "chain", "tail", "first", "portrait"}:
        raise Refuse(400, "bad_request")
    prompt = body.get("prompt")
    if not isinstance(prompt, str):
        raise Refuse(400, "bad_request")
    prompt = "".join(c for c in prompt if c == "\n" or c >= " ").strip()
    if not prompt or len(prompt) > MAX_PROMPT or "embedding:" in prompt.lower():
        raise Refuse(400, "bad_request")
    chain = body.get("chain", False)
    if not isinstance(chain, bool) or ("tail" in body and not chain):
        raise Refuse(400, "bad_request")
    secs = body.get("secs", 2)
    if isinstance(secs, bool) or secs not in (CHAIN_SECS if chain else SECS):
        raise Refuse(400, "bad_request")
    tail = None
    if "tail" in body:
        if not isinstance(body["tail"], str) or len(body["tail"]) > MAX_TAIL * 4 // 3 + 4:
            raise Refuse(400, "bad_request")
        try:
            tail = base64.b64decode(body["tail"], validate=True)
        except (binascii.Error, ValueError):
            raise Refuse(400, "bad_request")
        if not 12 <= len(tail) <= MAX_TAIL or tail[4:8] != b"ftyp":
            raise Refuse(400, "bad_request")
    first = None
    if "first" in body:
        if "tail" in body or not isinstance(body["first"], str) or len(body["first"]) > MAX_FIRST * 4 // 3 + 4:
            raise Refuse(400, "bad_request")
        try:
            first = base64.b64decode(body["first"], validate=True)
        except (binascii.Error, ValueError):
            raise Refuse(400, "bad_request")
        if not 12 <= len(first) <= MAX_FIRST or picture_kind(first) is None:
            raise Refuse(400, "bad_request")
    portrait = body.get("portrait", False)
    if not isinstance(portrait, bool):
        raise Refuse(400, "bad_request")
    seed = body.get("seed")
    if seed is None:
        seed = secrets.randbelow(2 ** 32)
    elif not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2 ** 32:
        raise Refuse(400, "bad_request")
    return prompt, secs, seed, chain, tail, first, portrait


def picture_kind(data):
    """The ffmpeg demuxer for a JPEG, PNG or WebP picture by its magic bytes, None for anything else."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg_pipe"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png_pipe"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp_pipe"
    return None


def size_of(secs, chain, portrait=False):
    w, h = CHAIN_SIZE if chain else SIZE_BY_SECS[secs]
    return (h, w) if portrait else (w, h)


def stage_first(data, token, w, h):
    """The start picture as one clean PNG of exactly w x h in ComfyUI's input folder: scaled to cover, center-cropped, RGB, no
    metadata (MiniMaxH3ImageToVideo stretches first_frame to the canvas, so the crop has to happen here). Returns the file name
    LoadImage takes; a picture ffmpeg cannot decode, or decodes only in part (a cut upload), is refused (400). The source copy is always removed."""
    src = os.path.join(WORK, "in", f"first-{token}.src")
    name = f"first-{token}.png"
    dst = os.path.join(WORK, "in", name)
    with open(src, "wb") as f:
        f.write(data)
    try:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=rgb24"
        r = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-f", picture_kind(data), "-i", src, "-frames:v", "1", "-vf", vf,
                            "-map_metadata", "-1", "-update", "1", "-f", "image2", "-c:v", "png", dst], capture_output=True, timeout=60)
        # a cut JPEG still exits 0 (ffmpeg fills the rest with grey) but says "overread" at -v error: any message refuses it
        ok = r.returncode == 0 and not r.stderr.strip() and os.path.getsize(dst) > 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    finally:
        try:
            os.unlink(src)
        except OSError:
            pass
    if not ok:
        try:
            os.unlink(dst)
        except OSError:
            pass
        raise Refuse(400, "bad_request")
    return name


def stage_tail(data, token):
    """The previous segment's tail as a clean clip in ComfyUI's input folder: only its first TAIL_FRAMES video frames, at 24 fps,
    lossless, no sound and no metadata. Returns the file name LoadVideo takes; a clip with fewer frames is refused (400)."""
    src = os.path.join(WORK, "in", f"tail-{token}.src")
    name = f"tail-{token}.mp4"
    dst = os.path.join(WORK, "in", name)
    with open(src, "wb") as f:
        f.write(data)
    try:
        r = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-an", "-sn", "-dn",
                            "-frames:v", str(TAIL_FRAMES), "-vf", f"setpts=N/({int(FPS)}*TB)", "-r", str(int(FPS)),
                            "-c:v", "libx264", "-qp", "0", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                            "-map_metadata", "-1", "-map_chapters", "-1", "-f", "mp4", dst], capture_output=True, timeout=60)
        ok = r.returncode == 0 and count_frames(dst) == TAIL_FRAMES
    except (OSError, subprocess.SubprocessError):
        ok = False
    finally:
        try:
            os.unlink(src)
        except OSError:
            pass
    if not ok:
        try:
            os.unlink(dst)
        except OSError:
            pass
        raise Refuse(400, "bad_request")
    return name


def count_frames(path):
    """Video frames in a clip, counted by decoding it with ffmpeg (no ffprobe needed); None when unreadable."""
    try:
        r = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-i", path, "-map", "0:v:0", "-f", "framemd5", "-"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return sum(1 for line in r.stdout.splitlines() if line and not line.startswith("#"))


def build_graph(prompt, secs, seed, prefix, chain=False, tail=None, first=None, portrait=False):
    """The workflow as data (from gpu-host/videobench/comfy_run.py job h3): node ids and input names are fixed here, only
    the prompt, the length, the seed, the staging prefix, the portrait flag and the staged tail's and first picture's random
    file names come from the request. Every
    required input is given, so no server defaults are filled in (checked against /object_info of ComfyUI 0df1646)."""
    w, h = size_of(secs, chain, portrait)
    g = {
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": MODEL["clip"], "type": "minimax"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": MODEL["vae"]}},
        "avae": {"class_type": "VAELoader", "inputs": {"vae_name": MODEL["avae"]}},
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": MODEL["unet"], "weight_dtype": "default"}},
        "lora": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["unet", 0], "lora_name": MODEL["lora"], "strength_model": 1.0}},
        "i2v": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"clip": ["clip", 0], "vae": ["vae", 0], "prompt": prompt,
                                                                   "width": w, "height": h, "length": frames(secs)}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "smp": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "sch": {"class_type": "BasicScheduler", "inputs": {"model": ["lora", 0], "scheduler": "simple", "steps": STEPS, "denoise": 1.0}},
        "gd": {"class_type": "BasicGuider", "inputs": {"model": ["lora", 0], "conditioning": ["i2v", 0]}},
        "ks": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["noise", 0], "guider": ["gd", 0], "sampler": ["smp", 0],
                                                                 "sigmas": ["sch", 0], "latent_image": ["i2v", 1]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["vae", 0]}},
        "adec": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["ks", 0], "vae": ["avae", 0]}},
        "cv": {"class_type": "CreateVideo", "inputs": {"images": ["dec", 0], "fps": FPS, "audio": ["adec", 0]}},
        "sv": {"class_type": "SaveVideo", "inputs": {"video": ["cv", 0], "filename_prefix": prefix, "format": "mp4", "codec": "h264"}},
    }
    if first:     # the staged PNG is already exactly w x h; the node's own input stretches it to the canvas
        g["fi"] = {"class_type": "LoadImage", "inputs": {"image": first}}
        g["i2v"]["inputs"]["first_frame"] = ["fi", 0]
    if tail:      # B5n: the previous segment's last frames anchored at frame 0, picture only (their sound left a gap at the join)
        g["tv"] = {"class_type": "LoadVideo", "inputs": {"file": tail}}
        g["tc"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["tv", 0]}}
        g["guide"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {"positive": ["i2v", 0], "latent": ["i2v", 1], "frame_idx": 0,
                                                                     "vae": ["vae", 0], "image": ["tc", 0]}}
        g["gd"]["inputs"]["conditioning"] = ["guide", 0]
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


def free_ram_mb():
    try:
        with open(MEMINFO) as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
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
        self.avg = 420.0                       # rolling mean of a job's seconds (a fifth of each new one)
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
        deadline = time.time() + MEM_WAIT_S
        while True:
            free, ram = free_vram_mb(), free_ram_mb()
            short = ("no_vram" if free is not None and free < VRAM_NEED_MB else
                     "no_ram" if ram is not None and ram < RAM_NEED_MB else None)
            if short is None:
                break
            if time.time() >= deadline:
                raise Refuse(503, short)
            time.sleep(3)
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
                time.sleep(0.5)
        self.stop()
        raise Refuse(504, "timeout")

    def stop(self):
        p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(20)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(5)
        for d in ("out", "tmp", "in", "user"):          # nothing of a job outlives the process
            shutil.rmtree(f"{WORK}/{d}", ignore_errors=True)

    def generate(self, graph, token):
        """Run one graph and return the mp4 bytes found in this job's own staging directory."""
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
                    self.stop()                          # backstop: the process goes, and with it the VRAM and RAM
                    raise Refuse(504, "timeout")
                if not self.alive():
                    raise Refuse(500, "failed")
                h = http_json("GET", f"/history/{pid}").get(pid)
                if h and h.get("status", {}).get("completed") is not None:
                    if h["status"].get("status_str") == "error":
                        raise Refuse(500, "failed")
                    break
                time.sleep(1.0)
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
    """Exactly one regular .mp4 in the staging directory, remuxed without metadata so nothing but the streams leaves."""
    try:
        entries = list(os.scandir(stage))
    except OSError:
        raise Refuse(500, "failed")
    files = [e for e in entries if e.is_file(follow_symlinks=False) and not e.is_symlink() and e.name.endswith(".mp4")]
    if len(entries) != 1 or len(files) != 1:
        raise Refuse(500, "failed")
    fd = os.open(files[0].path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        head = f.read(12)
        size = os.fstat(f.fileno()).st_size
    if size > MAX_MP4 or len(head) < 12 or head[4:8] != b"ftyp":
        raise Refuse(500, "failed")
    clean = os.path.join(stage, "clean.mp4")
    try:
        r = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", files[0].path, "-map", "0:v:0", "-map", "0:a?",
                            "-c", "copy", "-map_metadata", "-1", "-map_chapters", "-1", "-fflags", "+bitexact",
                            "-movflags", "+faststart", clean], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        raise Refuse(500, "failed")
    if r.returncode != 0:
        raise Refuse(500, "failed")
    with open(clean, "rb") as f:
        out = f.read(MAX_MP4 + 1)
    if len(out) > MAX_MP4 or out[4:8] != b"ftyp":
        raise Refuse(500, "failed")
    return out


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


MESSAGES = {400: "bad request", 401: "unauthorized", 429: "busy: one video at a time, try again in a few minutes",
            503: "the GPU is busy with something else right now (no free graphics or system memory for the video model)",
            504: "the video took too long and was stopped", 500: "the video could not be made"}


class Handler(BaseHTTPRequestHandler):
    server_version = "vidgen"

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
            return self._send(200, "ok video") if GPU["ok"] else self._send(503, "no gpu: " + GPU["why"])
        if self.path == "/status":
            state = "running" if COMFY.running else "idle" if COMFY.alive() else "asleep"
            return self._send(200, json.dumps({"state": state, "queued": 0, "slots": 1, "busy": int(COMFY.running), "avg_s": round(COMFY.avg, 1),
                                                    "eta_s": round(max(5.0, COMFY.avg - (time.time() - COMFY.t0)), 1) if COMFY.running else 0.0}), "application/json")
        self._send(404, "not found")

    def do_POST(self):
        if self.path != "/video":
            return self._send(404, "not found")
        if not self._auth():
            return self._send(401, MESSAGES[401])
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= MAX_BODY:
                raise Refuse(400, "bad_request")
            prompt, secs, seed, chain, tail, first, portrait = validate(json.loads(self.rfile.read(n)))
        except (Refuse, ValueError, UnicodeError):
            return self._send(400, MESSAGES[400])
        sha = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        if not COMFY.lock.acquire(blocking=False) and not (COMFY.stopping and COMFY.lock.acquire(timeout=40)):
            log(event="busy", secs=secs, prompt_sha=sha)
            return self._send(429, MESSAGES[429], headers={"Retry-After": "60"})
        t0 = time.time()
        COMFY.running, COMFY.t0 = True, time.time()
        try:
            COMFY.ensure()
            token = secrets.token_hex(16)
            w, h = size_of(secs, chain, portrait)
            tail_name = first_name = None
            try:
                tail_name = stage_tail(tail, token) if tail else None
                first_name = stage_first(first, token, w, h) if first else None
                mp4 = COMFY.generate(build_graph(prompt, secs, seed, f"stg/{token}/o", chain, tail_name, first_name, portrait), token)
            finally:
                for staged in (tail_name, first_name):
                    if staged:
                        try:
                            os.unlink(os.path.join(WORK, "in", staged))
                        except OSError:
                            pass
            took = round(time.time() - t0, 1)
            log(event="done", secs=secs, seed=seed, prompt_sha=sha, seconds=took, bytes=len(mp4), chain=chain or None, tail=bool(tail) or None,
                first=bool(first) or None, portrait=portrait or None)
            return self._send(200, mp4, "video/mp4", {"X-Video-Seconds": took, "X-Video-Seed": seed, "X-Video-Length": secs,
                                                      "X-Video-Size": f"{w}x{h}"})
        except Refuse as e:
            log(event="refused", code=e.code, why=e.text, secs=secs, prompt_sha=sha, seconds=round(time.time() - t0, 1))
            return self._send(e.code, MESSAGES.get(e.code, "failed"))
        except Exception as e:
            log(event="error", kind=type(e).__name__, secs=secs, prompt_sha=sha)
            return self._send(500, MESSAGES[500])
        finally:
            if time.time() - COMFY.t0 > 5:              # quick refusals do not drag the mean down
                COMFY.avg = 0.8 * COMFY.avg + 0.2 * (time.time() - COMFY.t0)
            COMFY.running = False
            COMFY.last = time.time()
            COMFY.lock.release()


def main():
    if not TOKEN:
        sys.exit("VIDEO_TOKEN is required: the service never runs without a token")
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
