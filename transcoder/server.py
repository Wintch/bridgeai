#!/usr/bin/env python3
"""
transcoder -- NVENC video transcoding over HTTP for Hermes (runs on the GPU desktop, next to the upscaler).

  GET  /healthz                     "ok nvenc" once a 1 s test encode on the GPU worked, else 503 + why
  GET  /status                      load for the gateway's host choice (no file names, no person data):
                                    {"state", "lanes": {"gpu"|"cpu": {"slots", "busy", "eta_s", "avg_s"}},
                                     "speed": {codec: Mpx/s}, "load1", "ncpu", "mem_free_mb"}
  POST /transcode?<options>         body = the video bytes -> an .mp4

Options (a closed list, never raw ffmpeg arguments):
  codec=h264|hevc|av1 (default h264; av1 is SVT-AV1 on this machine's CPU: this generation of card has no AV1 encoder)
  height=<144..2160> (keeps aspect)   hflip=1   vflip=1
  start=<seconds>  duration=<seconds>   cq=<15..40> (quality, lower = better, default 28: about the size of libx264 -crf 23 at 720p, measured)
  audio=aac|copy|none (default aac)

At most MAX_JOBS NVENC encodes and CPU_JOBS AV1 encodes at once; the rest get 429.
AV1 (real 15 s 720x1280 phone clip on a 6-core Zen 3 desktop CPU): preset 8 crf 35 encoded in 4.3 s, 35 % smaller than
libx264 crf 23 at a slightly lower SSIM (0.985 vs 0.989); preset 6 was 27 % smaller at the same SSIM in 7.5 s. Telegram does
not re-encode videos, so the smaller file is what the person downloads; AV1 and HEVC played on the operator's phone and PC.
Those timings were taken with SVT-AV1 1.7 (Ubuntu 24.04). The image now uses Debian trixie (SVT-AV1 2.3): a 20 s 1080p clip takes
6.5 s instead of 9.4 s at the same size (aibridge/VIDEO_BENCH_RESULTS.md).
Optional TRANSCODE_TOKEN: when set, requests need "Authorization: Bearer <token>". Stdlib only, like upscaler/.
"""
import hmac
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "8610"))
MAX_JOBS = int(os.environ.get("MAX_JOBS", "2"))
MAX_BYTES = int(os.environ.get("MAX_MB", "4096")) * 1024 * 1024
TIMEOUT_S = int(os.environ.get("TIMEOUT_S", "1800"))
TOKEN = os.environ.get("TRANSCODE_TOKEN", "")
CPU_JOBS = int(os.environ.get("CPU_JOBS", "1"))
AV1_PRESET = os.environ.get("AV1_PRESET", "8")
SLOTS = threading.BoundedSemaphore(MAX_JOBS)
CPU_SLOTS = threading.BoundedSemaphore(CPU_JOBS)
HEALTH = {"ok": False, "why": "not checked yet"}
# Host choice: the gateway asks every host for /status and sends the job to the one expected to finish first. Each
# running job keeps its start time and estimate; SPEED is a rolling mean of frames x (input + output) megapixels per second per
# codec, the same work measure the gateway uses, so its estimate for this host improves with every job.
SPEED = {"h264": 600.0, "hevc": 500.0, "av1": 200.0}
AVG_S = {"gpu": 30.0, "cpu": 120.0}
JOBS = {"gpu": {}, "cpu": {}}
JOBS_LOCK = threading.Lock()


def vprobe(path):
    """(w, h, fps, frames) of the first video stream, or None."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", path],
                           capture_output=True, text=True, timeout=30)
        j = json.loads(r.stdout or "{}")
        s, f = (j.get("streams") or [{}])[0], j.get("format") or {}
        num, den = (str(s.get("r_frame_rate") or "30/1") + "/1").split("/")[:2]
        fps = float(num) / float(den) if float(den) > 0 and float(num) > 0 else 30.0
        nb = str(s.get("nb_frames") or "")
        frames = int(nb) if nb.isdigit() else int(float(f.get("duration") or 0) * fps)
        return int(s["width"]), int(s["height"]), fps, max(1, frames)
    except Exception:
        return None


def work_mpx(probe, q):
    """frames x (input + output pixels) / 1e6 for this request, or None when the input could not be read."""
    if not probe:
        return None
    w, h, fps, n = probe
    if "start" in q:
        n -= int(float(q["start"]) * fps)
    if "duration" in q:
        n = min(n, int(float(q["duration"]) * fps))
    oh = int(q["height"]) if "height" in q else h
    return max(1, n) * (w * h + round(w * oh / h) * oh) / 1e6


def status():
    now = time.time()
    lanes = {}
    with JOBS_LOCK:
        for lane, cap in (("gpu", MAX_JOBS), ("cpu", CPU_JOBS)):
            left = [max(1.0, j["est"] - (now - j["t0"])) for j in JOBS[lane].values()]
            lanes[lane] = {"slots": cap, "busy": len(left), "avg_s": round(AVG_S[lane], 1),
                           "eta_s": round(min(left), 1) if left else 0.0}
    mem = None
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                mem = int(line.split()[1]) // 1024
    except OSError:
        pass
    return {"state": "running" if any(v["busy"] for v in lanes.values()) else "idle", "lanes": lanes,
            "speed": {k: round(v, 1) for k, v in SPEED.items()}, "load1": round(os.getloadavg()[0], 2),
            "ncpu": os.cpu_count() or 1, "mem_free_mb": mem}


def self_test():
    """1 s synthetic clip through h264_nvenc: proves the GPU, driver and NVENC are usable from this container."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30",
                        "-t", "1", "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, text=True, timeout=60)
    HEALTH.update(ok=r.returncode == 0, why=(r.stderr.strip().splitlines() or ["?"])[-1] if r.returncode else "")


def options(query):
    q = {k: v[-1] for k, v in parse_qs(query).items()}
    codec = q.get("codec", "h264")
    if codec not in ("h264", "hevc", "av1"):
        raise ValueError("codec must be h264, hevc or av1")
    vf = []
    if "height" in q:
        h = int(q["height"])
        if not 144 <= h <= 2160:
            raise ValueError("height out of range")
        vf.append(f"scale=-2:{h}")
    if q.get("hflip") == "1":
        vf.append("hflip")
    if q.get("vflip") == "1":
        vf.append("vflip")
    cq = int(q.get("cq", "28"))
    if not 15 <= cq <= 40:
        raise ValueError("cq out of range")
    audio = q.get("audio", "aac")
    if audio not in ("aac", "copy", "none"):
        raise ValueError("audio must be aac, copy or none")
    pre, post = [], []
    if "start" in q:
        pre += ["-ss", str(max(0.0, float(q["start"])))]
    if "duration" in q:
        post += ["-t", str(max(0.1, float(q["duration"])))]
    if codec == "av1":   # cq 28 -> crf 35: about the size/quality step of the NVENC default
        args = post + ["-c:v", "libsvtav1", "-preset", AV1_PRESET, "-crf", str(min(63, cq + 7)), "-pix_fmt", "yuv420p"]
    else:
        args = post + ["-c:v", f"{codec}_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(cq), "-b:v", "0"]
    if vf:
        args += ["-vf", ",".join(vf)]
    args += ["-an"] if audio == "none" else ["-c:a", "aac", "-b:a", "160k"] if audio == "aac" else ["-c:a", "copy"]
    return pre, args + ["-movflags", "+faststart"]


class Handler(BaseHTTPRequestHandler):
    timeout = 60  # socket timeout: a half-open or stalled upload cannot hold a MAX_JOBS slot forever

    def _send(self, code, body, ctype="text/plain"):
        body = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # one line per job is printed below; no per-request noise
        pass

    def do_GET(self):
        if urlparse(self.path).path == "/healthz":
            return self._send(200, "ok nvenc") if HEALTH["ok"] else self._send(503, "no nvenc: " + HEALTH["why"])
        if urlparse(self.path).path == "/status":
            return self._send(200, json.dumps(status()), "application/json")
        self._send(404, "not found")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/transcode":
            return self._send(404, "not found")
        if TOKEN and not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {TOKEN}"):
            return self._send(401, "bad token")
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= MAX_BYTES:
            return self._send(413, f"body must be 1 byte to {MAX_BYTES // 1048576} MB")
        try:
            pre, args = options(url.query)
        except ValueError as e:
            return self._send(400, str(e))
        lane = "cpu" if "libsvtav1" in args else "gpu"
        slots, cap = (CPU_SLOTS, CPU_JOBS) if lane == "cpu" else (SLOTS, MAX_JOBS)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        codec = q.get("codec", "h264")
        job = object()
        if not slots.acquire(blocking=False):
            return self._send(429, f"busy: {cap} encodes of this kind running, retry in a minute")
        tmp = tempfile.mkdtemp(prefix="tc-")
        try:
            src, dst = os.path.join(tmp, "in"), os.path.join(tmp, "out.mp4")
            with open(src, "wb") as f:
                left = length
                while left:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        return self._send(400, "body ended early")
                    f.write(chunk)
                    left -= len(chunk)
            t0 = time.time()
            work = work_mpx(vprobe(src), q)
            with JOBS_LOCK:
                JOBS[lane][job] = {"t0": t0, "est": work / SPEED[codec] if work else AVG_S[lane]}
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *pre, "-i", src, *args, dst],
                               capture_output=True, text=True, timeout=TIMEOUT_S)
            took = time.time() - t0
            if r.returncode != 0 or not os.path.exists(dst):
                print(f"transcode failed in {took:.1f}s: {(r.stderr.strip().splitlines() or ['?'])[-1][:200]}", flush=True)
                return self._send(500, "ffmpeg failed: " + (r.stderr.strip().splitlines() or ["?"])[-1][:300])
            size = os.path.getsize(dst)
            with JOBS_LOCK:     # rolling means (a fifth of each new job): the gateway's estimates follow this machine
                AVG_S[lane] = 0.8 * AVG_S[lane] + 0.2 * took
                if work and took > 1:
                    SPEED[codec] = 0.8 * SPEED[codec] + 0.2 * (work / took)
            print(f"transcode {length / 1048576:.1f} MB -> {size / 1048576:.1f} MB in {took:.1f}s ({url.query})", flush=True)
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(size))
            self.send_header("X-Encode-Seconds", f"{took:.1f}")
            self.end_headers()
            with open(dst, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 1 << 20)
        except subprocess.TimeoutExpired:
            self._send(504, f"encode took more than {TIMEOUT_S}s")
        finally:
            with JOBS_LOCK:
                JOBS[lane].pop(job, None)
            slots.release()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    self_test()
    print(f"transcoder on :{PORT}, nvenc {'ok' if HEALTH['ok'] else 'NOT available: ' + HEALTH['why']}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
