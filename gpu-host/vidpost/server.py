#!/usr/bin/env python3
"""
vidpost -- finish a short video on a GPU: 2x upscale (Real-ESRGAN general-x4v3) and/or 2x frame rate (RIFE 4.26), over HTTP for
Hermes. Meant for a second card while the main one generates (aibridge/GPU_RENTAL_AND_MODELS.md, section 7.1):
on the 8 GB Pascal card a 5 s 480p clip took 83 s to upscale to 1664x960 and 20 s more to reach 48 fps; on the 8 GB Ampere card about 25% less.

  GET  /healthz             "ok vidpost", or 503 "no gpu: ..." when CUDA cannot see the card (GPU watch below)
  GET  /status              {"state": "idle|running|asleep", "queued": 0, "slots": 1, "busy": 0|1, "eta_s", "avg_s"}
  POST /enhance?scale=1|2&fps=0|2[&slow=1]   body: the mp4 (max 200 MB), Content-Type video/mp4
                    -> 200 video/mp4, headers X-Enhance-Seconds, X-Enhance-Size ("WxH"), X-Enhance-Fps
                    -> 400 bad_request | 401 | 429 busy | 503 no_vram/no_ram | 504 timeout | 500 failed   (fixed text)

Same design as gpu-host/vidgen and imggen: ComfyUI only on 127.0.0.1 inside, a fixed graph by node id, one job at a time,
ComfyUI started on demand and stopped after IDLE_S, Bearer token required. The upload is checked with ffprobe before any GPU
work: one video stream (h264/hevc/vp9/av1/mpeg4), at most MAX_SECS long and MAX_SIDE pixels on a side, and the output
frames x pixels under MAX_WORK (a bound on time: about 4.5 M pixel-frames a second on the 8 GB Pascal card). Upscale runs before
RIFE (RIFE at the larger size costs less than upscaling twice the frames).

The video goes through ComfyUI in pieces of at most CHUNK_WORK output pixel-frames, so the RAM stays flat whatever the length.
ComfyUI holds every frame of a pass as float32, about 41 bytes per output pixel-frame on top of ~3.4 GB: one pass over a 5 s
480p clip to 1664x960 at 48 fps peaked at 19 GB, 8 s at 1408x768 at 20 GB. Each piece is cut losslessly
with ffmpeg (x264 qp 0). With RIFE the pieces share one frame and every piece after the first drops its first output frame
(ImageFromBatch), so the frames are exactly those of a single pass (RIFE makes 2n-1 from n). The pieces are joined without
re-encoding and the source's sound is put back (at half speed with slow=1). The answer is remuxed without metadata.
Runs in Docker (FROM a torch+ComfyUI image) or straight from a venv on a host whose card the image's torch does not support
(Pascal needs torch <= 2.14 cu126): COMFY_DIR, EXTRA_PATHS and WORK point at that host's folders.
"""
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
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8680"))
TOKEN = os.environ.get("VIDPOST_TOKEN", "")
WORK = os.environ.get("WORK", "/work")
COMFY_DIR = os.environ.get("COMFY_DIR", "/w/ComfyUI")
COMFY_PORT = int(os.environ.get("COMFY_PORT", "8192"))
COMFY_CMD = os.environ.get("COMFY_CMD", "")               # tests replace ComfyUI with a fake
EXTRA_PATHS = os.environ.get("EXTRA_PATHS", "/app/extra_paths.yaml")
IDLE_S = float(os.environ.get("IDLE_S", "120"))
JOB_TIMEOUT = float(os.environ.get("JOB_TIMEOUT", "600"))     # the whole job, every piece
READY_TIMEOUT = float(os.environ.get("READY_TIMEOUT", "120"))
VRAM_NEED_MB = int(os.environ.get("VRAM_NEED_MB", "2500"))   # RIFE 1.3-2.0 GB, general-x4v3 1.4-2.2 GB measured
RAM_NEED_MB = int(os.environ.get("RAM_NEED_MB", "8000"))      # ~3.4 GB + one piece (CHUNK_WORK x 41 B)
MEM_WAIT_S = float(os.environ.get("MEM_WAIT_S", "60"))
NVSMI = os.environ.get("NVSMI", "nvidia-smi")
MEMINFO = os.environ.get("MEMINFO", "/proc/meminfo")
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
MAX_IN = 200 * 1024 * 1024
MAX_MP4 = 400 * 1024 * 1024
MAX_SECS = float(os.environ.get("MAX_SECS", "30"))
MAX_SIDE = int(os.environ.get("MAX_SIDE", "1920"))
MAX_WORK = float(os.environ.get("MAX_WORK", "1.2e9"))    # output frames x output pixels for the whole video (time bound)
CHUNK_WORK = float(os.environ.get("CHUNK_WORK", "8e7"))  # output frames x output pixels per ComfyUI pass (RAM bound)
MAX_PIECE = 1500                                          # input frames per pass (ImageFromBatch takes at most 4096)
CODECS = {"h264", "hevc", "vp9", "av1", "mpeg4"}
UPSCALER = os.environ.get("UPSCALER", "realesr-general-x4v3.safetensors")
INTERP = os.environ.get("INTERP", "rife_v4.26.safetensors")


class Refuse(Exception):
    def __init__(self, code, text):
        super().__init__(text)
        self.code, self.text = code, text


def log(**kw):
    print(json.dumps(dict(ts=time.strftime("%Y-%m-%dT%H:%M:%S"), **kw), ensure_ascii=False), flush=True)


def probe(path):
    """(width, height, fps, seconds, frames) of the upload's single video stream as cut() will see it, or a 400: the size upright
    (a portrait phone video is stored sideways with a rotation that ffmpeg applies) and cropped to even numbers (x264 4:2:0), and
    the frames that really decode. Packets are not frames: a trimmed mp4 keeps hidden pre-roll packets behind an edit list, and
    counting them planned a last piece past the end."""
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                            "stream=codec_type,codec_name,width,height,avg_frame_rate,nb_read_frames:stream_tags=rotate:stream_side_data_list:format=duration",
                            "-count_frames", "-of", "json", path], capture_output=True, text=True, timeout=120)
        j = json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        raise Refuse(400, "bad_request")
    vs = [s for s in j.get("streams", []) if s.get("codec_type") == "video"]
    if r.returncode != 0 or len(vs) != 1 or vs[0].get("codec_name") not in CODECS:
        raise Refuse(400, "bad_request")
    v = vs[0]
    try:
        w, h = int(v["width"]), int(v["height"])
        num, den = (int(x) for x in v.get("avg_frame_rate", "0/1").split("/"))
        fps = num / den if den else 0.0
        secs = float(j.get("format", {}).get("duration", 0))
        frames = int(v.get("nb_read_frames") or 0)
        rot = [float(d["rotation"]) for d in v.get("side_data_list", []) if "rotation" in d] or [float(v.get("tags", {}).get("rotate", 0))]
    except (KeyError, ValueError, TypeError):
        raise Refuse(400, "bad_request")
    if not (1 <= fps <= 61) or not (0 < secs <= MAX_SECS) or not (16 <= w <= MAX_SIDE and 16 <= h <= MAX_SIDE):
        raise Refuse(400, "bad_request")
    if not 1 <= frames <= fps * secs * 1.5 + 2:      # nonsense counts are refused
        raise Refuse(400, "bad_request")
    if round(abs(rot[0])) % 180 == 90:
        w, h = h, w
    return w // 2 * 2, h // 2 * 2, fps, secs, frames


def plan(params, w, h, fps, frames):
    """(scale, interp, slow, out_w, out_h, out_fps) from the query, refused when nothing is asked or the work is too large.
    slow=1 (with fps=2) keeps the original frame rate, so the RIFE frames make the clip twice as long: slow motion."""
    scale, f2, slow = params.get("scale", ["2"])[0], params.get("fps", ["2"])[0], params.get("slow", ["0"])[0]
    if (scale not in ("1", "2") or f2 not in ("0", "2") or slow not in ("0", "1") or (scale == "1" and f2 == "0")
            or (slow == "1" and f2 != "2") or set(params) - {"scale", "fps", "slow"}):
        raise Refuse(400, "bad_request")
    k = int(scale)
    ow, oh = (w * k) // 2 * 2, (h * k) // 2 * 2
    of = 2 * frames - 1 if f2 == "2" else frames
    ofps = fps if slow == "1" else fps * (2 if f2 == "2" else 1)
    if of * ow * oh > MAX_WORK:
        raise Refuse(400, "too_much")
    return k == 2, f2 == "2", slow == "1", ow, oh, ofps


def build_graph(name, upscale, interp, ow, oh, ofps, prefix, drop_first=False):
    """One piece's workflow as data (the bench jobs esrgan + interp of gpu-host/videobench/comfy_run.py chained). No sound:
    the source's sound is put back once over the joined pieces. drop_first: the frame this piece shares with the previous one."""
    g = {"lv": {"class_type": "LoadVideo", "inputs": {"file": name}},
         "gc": {"class_type": "GetVideoComponents", "inputs": {"video": ["lv", 0]}}}
    img = ["gc", 0]
    if upscale:
        g["ml"] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": UPSCALER}}
        g["up"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["ml", 0], "image": img}}
        g["rs"] = {"class_type": "ImageScale", "inputs": {"image": ["up", 0], "upscale_method": "lanczos", "width": ow, "height": oh, "crop": "disabled"}}
        img = ["rs", 0]
    if interp:
        g["fl"] = {"class_type": "FrameInterpolationModelLoader", "inputs": {"model_name": INTERP}}
        g["fi"] = {"class_type": "FrameInterpolate", "inputs": {"interp_model": ["fl", 0], "images": img, "multiplier": 2}}
        img = ["fi", 0]
    if drop_first:
        g["fb"] = {"class_type": "ImageFromBatch", "inputs": {"image": img, "batch_index": 1, "length": 4096}}
        img = ["fb", 0]
    g["cv"] = {"class_type": "CreateVideo", "inputs": {"images": img, "fps": float(round(ofps, 3))}}
    g["sv"] = {"class_type": "SaveVideo", "inputs": {"video": ["cv", 0], "filename_prefix": prefix, "format": "mp4", "codec": "h264"}}
    return g


def pieces(frames, interp, ow, oh):
    """[(first, last)] input frame ranges, inclusive, each under CHUNK_WORK output pixel-frames. With RIFE consecutive pieces
    share one frame (the last of one is the first of the next), so the in-between frame is still made."""
    per_frame = ow * oh * (2 if interp else 1)
    size = int(max(2, min(MAX_PIECE, CHUNK_WORK // per_frame)))
    out, first = [], 0
    while True:
        last = min(first + size - 1, frames - 1)
        out.append((first, last))
        if last >= frames - 1:
            return out
        first = last if interp else last + 1


def cut(src, first, last, fps, dst, timeout=300):
    """Frames first..last of the source, losslessly (x264 qp 0), no sound, constant frame rate. `-r` is needed: without it the mp4
    lost its last frame when ComfyUI read it (39 of 40) and reported 320/13 fps."""
    vf = f"crop=trunc(iw/2)*2:trunc(ih/2)*2:0:0,select='between(n,{first},{last})',setpts=N/({fps:.6f}*TB)"
    try:
        r = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-vf", vf, "-r", f"{fps:.6f}",
                            "-an", "-c:v", "libx264", "-qp", "0", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                            "-map_metadata", "-1", dst], capture_output=True, timeout=max(5, timeout))
        n = subprocess.run([FFPROBE, "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries", "stream=nb_read_packets",
                            "-of", "csv=p=0", dst], capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise Refuse(500, "failed")
    if r.returncode != 0 or n != str(last - first + 1):     # an empty or short piece is a failure, never a silent gap
        raise Refuse(500, "failed")


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
        self.avg = 300.0                       # rolling mean of a job's seconds (a fifth of each new one)
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

    def run_piece(self, graph, stage, keep, deadline):
        """Run one piece's graph; its single mp4 (found in its own staging directory) is moved to `keep`."""
        pid = str(uuid.uuid4())
        try:
            http_json("POST", "/prompt", {"prompt": graph, "prompt_id": pid})
            while True:
                if time.time() > deadline:
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
                time.sleep(0.5)
            os.replace(pick(stage), keep)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
            try:
                http_json("POST", "/history", {"delete": [pid]})
            except Exception:
                pass
            shutil.rmtree(os.path.join(WORK, "tmp"), ignore_errors=True)
            os.makedirs(os.path.join(WORK, "tmp"), exist_ok=True)


def pick(stage):
    """The path of exactly one regular .mp4 (ftyp, under MAX_MP4) in a piece's staging directory, or a 500."""
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
    return files[0].path


def join(parts, source, slow, folder):
    """The pieces joined without re-encoding, with the source's sound (at half speed, pitch kept, for slow motion), and no
    metadata, so nothing but the streams leaves."""
    lst, clean = os.path.join(folder, "list.txt"), os.path.join(folder, "clean.mp4")
    with open(lst, "w") as f:
        f.writelines(f"file '{p}'\n" for p in parts)          # our own paths: WORK/job/<token>/pNNN.mp4
    audio = ["-af", "atempo=0.5"] if slow else []
    try:
        r = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", source,
                            "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy"] + audio + ["-c:a", "aac", "-b:a", "160k",
                            "-map_metadata", "-1", "-map_chapters", "-1", "-fflags", "+bitexact", "-movflags", "+faststart", clean],
                           capture_output=True, timeout=300)
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


MESSAGES = {400: "bad request: not a short mp4 video, nothing asked, or too long or too large for this (shorten it or skip the upscale)",
            401: "unauthorized", 429: "busy: one video at a time, try again in a minute",
            503: "the GPU is busy with something else right now (no free graphics or system memory)",
            504: "the video took too long and was stopped", 500: "the video could not be finished"}


class Handler(BaseHTTPRequestHandler):
    server_version = "vidpost"

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
            return self._send(200, "ok vidpost") if GPU["ok"] else self._send(503, "no gpu: " + GPU["why"])
        if self.path == "/status":
            state = "running" if COMFY.running else "idle" if COMFY.alive() else "asleep"
            return self._send(200, json.dumps({"state": state, "queued": 0, "slots": 1, "busy": int(COMFY.running), "avg_s": round(COMFY.avg, 1),
                                                    "eta_s": round(max(5.0, COMFY.avg - (time.time() - COMFY.t0)), 1) if COMFY.running else 0.0}), "application/json")
        self._send(404, "not found")

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path != "/enhance":
            return self._send(404, "not found")
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        # An early answer must first read the upload: a client still sending gets a reset otherwise and reports the host as off
        # instead of busy or unauthorized. Above MAX_IN nothing is read and the connection is closed.
        if not self._auth():
            return self._early(401, n)
        if not 0 < n <= MAX_IN:
            return self._early(400, n)
        if not COMFY.lock.acquire(blocking=False) and not (COMFY.stopping and COMFY.lock.acquire(timeout=40)):
            log(event="busy", bytes_in=n)
            return self._early(429, n, {"Retry-After": "30"})
        t0, token = time.time(), secs_hex()
        name = f"up_{token}.mp4"
        src = os.path.join(WORK, "up", name)              # outside WORK/in, which ComfyUI's cold start wipes
        job = os.path.join(WORK, "job", token)              # the finished pieces and the joined answer
        COMFY.running, COMFY.t0 = True, time.time()
        try:
            os.makedirs(os.path.join(WORK, "up"), exist_ok=True)
            with open(src, "wb") as f:
                left = n
                while left:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        raise Refuse(400, "bad_request")
                    f.write(chunk)
                    left -= len(chunk)
            with open(src, "rb") as f:
                if f.read(12)[4:8] != b"ftyp":
                    raise Refuse(400, "bad_request")
            w, h, fps, secs, frames = probe(src)
            upscale, interp, slow, ow, oh, ofps = plan(urllib.parse.parse_qs(u.query, keep_blank_values=True), w, h, fps, frames)
            COMFY.ensure()
            os.makedirs(job, exist_ok=True)
            parts, deadline = [], t0 + JOB_TIMEOUT
            todo = pieces(frames, interp, ow, oh)
            for i, (a, b) in enumerate(todo):
                piece = f"p_{token}_{i:03d}.mp4"
                inp = os.path.join(WORK, "in", piece)
                os.makedirs(os.path.join(WORK, "in"), exist_ok=True)
                cut(src, a, b, fps, inp, deadline - time.time())
                keep = os.path.join(job, f"p{i:03d}.mp4")
                try:
                    COMFY.run_piece(build_graph(piece, upscale, interp, ow, oh, ofps, f"stg/{token}/{i:03d}/o", interp and i > 0),
                                    os.path.join(WORK, "out", "stg", token, f"{i:03d}"), keep, deadline)
                finally:
                    try:
                        os.unlink(inp)
                    except OSError:
                        pass
                parts.append(keep)
            if time.time() > deadline:
                raise Refuse(504, "timeout")
            mp4 = join(parts, src, slow, job)
            took = round(time.time() - t0, 1)
            log(event="done", upscale=upscale, interp=interp, slow=slow, size=f"{ow}x{oh}", fps=round(ofps, 2), pieces=len(todo), seconds=took, bytes_in=n, bytes=len(mp4))
            return self._send(200, mp4, "video/mp4", {"X-Enhance-Seconds": took, "X-Enhance-Size": f"{ow}x{oh}", "X-Enhance-Fps": round(ofps, 2)})
        except Refuse as e:
            log(event="refused", code=e.code, why=e.text, seconds=round(time.time() - t0, 1), bytes_in=n)
            return self._send(e.code, MESSAGES.get(e.code, "failed"))
        except Exception as e:
            log(event="error", kind=type(e).__name__)
            return self._send(500, MESSAGES[500])
        finally:
            try:
                os.unlink(src)
            except OSError:
                pass
            shutil.rmtree(job, ignore_errors=True)
            shutil.rmtree(os.path.join(WORK, "out", "stg", token), ignore_errors=True)
            for e in os.scandir(os.path.join(WORK, "in")) if os.path.isdir(os.path.join(WORK, "in")) else []:
                if e.name.startswith(f"p_{token}_"):
                    try:
                        os.unlink(e.path)
                    except OSError:
                        pass
            if time.time() - COMFY.t0 > 5:              # quick refusals do not drag the mean down
                COMFY.avg = 0.8 * COMFY.avg + 0.2 * (time.time() - COMFY.t0)
            COMFY.running = False
            COMFY.last = time.time()
            COMFY.lock.release()


    def _early(self, code, n, headers=None):
        if 0 < n <= MAX_IN:
            left = n
            while left:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    break
                left -= len(chunk)
        else:
            self.close_connection = True
        return self._send(code, MESSAGES[code], headers=headers)


def secs_hex():
    return secrets.token_hex(16)


def main():
    if not TOKEN:
        sys.exit("VIDPOST_TOKEN is required: the service never runs without a token")
    os.makedirs(WORK, exist_ok=True)
    for d in ("up", "job"):          # an upload or pieces left by a job cut short (SIGTERM, a kill, a power loss): this process owns WORK
        shutil.rmtree(os.path.join(WORK, d), ignore_errors=True)
    threading.Thread(target=idle_loop, daemon=True).start()
    threading.Thread(target=gpu_loop, daemon=True).start()
    srv = ThreadingHTTPServer((os.environ.get("BIND", "0.0.0.0"), PORT), Handler)   # BIND: GPU_BIND_ADDR when run outside Docker
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
