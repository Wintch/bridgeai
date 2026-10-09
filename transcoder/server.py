#!/usr/bin/env python3
"""
transcoder -- NVENC video transcoding over HTTP for Hermes (runs on the GPU desktop, next to the upscaler).

  GET  /healthz                     "ok nvenc" once a 1 s test encode on the GPU worked, else 503 + why
  POST /transcode?<options>         body = the video bytes -> an .mp4

Options (a closed list, never raw ffmpeg arguments):
  codec=h264|hevc (default h264)   height=<144..2160> (keeps aspect)   hflip=1   vflip=1
  start=<seconds>  duration=<seconds>   cq=<15..40> (quality, lower = better, default 28: about the size of libx264 -crf 23 at 720p, measured 2026-10-09)
  audio=aac|copy|none (default aac)

At most MAX_JOBS encodes at once (consumer NVIDIA cards cap concurrent NVENC sessions); the rest get 429.
Optional TRANSCODE_TOKEN: when set, requests need "Authorization: Bearer <token>". Stdlib only, like upscaler/.
"""
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
SLOTS = threading.BoundedSemaphore(MAX_JOBS)
HEALTH = {"ok": False, "why": "not checked yet"}


def self_test():
    """1 s synthetic clip through h264_nvenc: proves the GPU, driver and NVENC are usable from this container."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30",
                        "-t", "1", "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, text=True, timeout=60)
    HEALTH.update(ok=r.returncode == 0, why=(r.stderr.strip().splitlines() or ["?"])[-1] if r.returncode else "")


def options(query):
    q = {k: v[-1] for k, v in parse_qs(query).items()}
    codec = q.get("codec", "h264")
    if codec not in ("h264", "hevc"):
        raise ValueError("codec must be h264 or hevc")
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
    args = post + ["-c:v", f"{codec}_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(cq), "-b:v", "0"]
    if vf:
        args += ["-vf", ",".join(vf)]
    args += ["-an"] if audio == "none" else ["-c:a", "aac", "-b:a", "160k"] if audio == "aac" else ["-c:a", "copy"]
    return pre, args + ["-movflags", "+faststart"]


class Handler(BaseHTTPRequestHandler):
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
        self._send(404, "not found")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/transcode":
            return self._send(404, "not found")
        if TOKEN and self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._send(401, "bad token")
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= MAX_BYTES:
            return self._send(413, f"body must be 1 byte to {MAX_BYTES // 1048576} MB")
        try:
            pre, args = options(url.query)
        except ValueError as e:
            return self._send(400, str(e))
        if not SLOTS.acquire(blocking=False):
            return self._send(429, f"busy: {MAX_JOBS} encodes running, retry in a minute")
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
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *pre, "-i", src, *args, dst],
                               capture_output=True, text=True, timeout=TIMEOUT_S)
            took = time.time() - t0
            if r.returncode != 0 or not os.path.exists(dst):
                print(f"transcode failed in {took:.1f}s: {(r.stderr.strip().splitlines() or ['?'])[-1][:200]}", flush=True)
                return self._send(500, "ffmpeg failed: " + (r.stderr.strip().splitlines() or ["?"])[-1][:300])
            size = os.path.getsize(dst)
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
            SLOTS.release()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    self_test()
    print(f"transcoder on :{PORT}, nvenc {'ok' if HEALTH['ok'] else 'NOT available: ' + HEALTH['why']}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
