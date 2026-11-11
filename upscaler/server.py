#!/usr/bin/env python3
"""
upscaler -- minimal HTTP wrapper around Real-ESRGAN (x4) for GPU image
upscaling. POST raw image bytes to /upscale, get back a JPEG (quality 92).
UPSCALE_MODEL: general (default, realesr-general-x4v3, a compact SRVGG net) or x4plus (RRDBNet). Measured
(aibridge/VIDEO_BENCH_RESULTS.md B6, 8 GB Ampere card): general-x4v3 is about 8x faster with the same look and 1.4 GB of VRAM
against 5.4 GB, so x4plus is only kept to compare.
Requests are queued one at a time on the shared GPU (never 429: the gateway
treats 429/5xx as host down); inputs over MAX_PIXELS get 413. Stdlib HTTP
server only, matching the rest of this project's convention.
Optional UPSCALE_TOKEN: when set, POST needs "Authorization: Bearer <token>" (gateways_sync passes the host's upscale_token).
"""
import hmac
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer
from realesrgan.archs.srvgg_arch import SRVGGNetCompact

MODEL_NAME = os.environ.get("UPSCALE_MODEL", "general")
PORT = int(os.environ.get("PORT", "8600"))
MAX_PIXELS = int(os.environ.get("MAX_PIXELS", str(16_000_000)))  # input pixels; the output is 16x that
MAX_BYTES = int(os.environ.get("MAX_MB", "64")) * 1024 * 1024
TOKEN = os.environ.get("UPSCALE_TOKEN", "")
GPU_LOCK = threading.Lock()  # one enhance() at a time: the GPU is shared with the other services

if MODEL_NAME == "x4plus":
    MODEL_PATH, TILE = "/app/weights/RealESRGAN_x4plus.pth", 256
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
elif MODEL_NAME == "general":
    MODEL_PATH, TILE = "/app/weights/realesr-general-x4v3.pth", 512   # small net: bigger tiles, fewer seams, still ~1.5 GB
    model = SRVGGNetCompact(num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=32, upscale=4, act_type="prelu")
else:
    raise SystemExit(f"UPSCALE_MODEL must be general or x4plus, not {MODEL_NAME!r}")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
upsampler = RealESRGANer(
    scale=4,
    model_path=MODEL_PATH,
    model=model,
    tile=TILE,
    tile_pad=10,
    pre_pad=0,
    half=(DEVICE == "cuda"),
    device=DEVICE,
)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/upscale":
            self.send_response(404)
            self.end_headers()
            return
        if TOKEN and not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {TOKEN}"):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"bad token")
            return
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BYTES:
            self.send_response(413)
            self.end_headers()
            self.wfile.write(b"body too large")
            return
        data = self.rfile.read(length)
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"invalid image")
            return
        if img.shape[0] * img.shape[1] > MAX_PIXELS:
            self.send_response(413)
            self.end_headers()
            self.wfile.write(f"image over {MAX_PIXELS} pixels".encode())
            return
        try:
            with GPU_LOCK:
                try:
                    output, _ = upsampler.enhance(img, outscale=4)
                finally:
                    if DEVICE == "cuda":
                        torch.cuda.empty_cache()  # give back the blocks an OOM left cached
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())
            return
        ok, buf = cv2.imencode(".jpg", output, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"jpeg encode failed")
            return
        body = buf.tobytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":                  # 503 while the GPU watch says CUDA sees no GPU
            self.send_response(200 if GPU["ok"] else 503)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write((f"ok device={DEVICE} model={MODEL_NAME}" if GPU["ok"] else "no gpu: " + GPU["why"]).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        import sys
        sys.stderr.write("[upscaler] " + (fmt % args) + "\n")


# GPU watch: a systemd reload on the host can take the GPU away from a container that is already running
# (cgroup v2 + nvidia-container-toolkit); the upscaler then failed every request while /healthz said ok. A child process asks
# the CUDA driver every GPU_CHECK_S seconds and /healthz answers 503 "no gpu" while it fails (gateway skips the host, Zabbix
# alerts). Only when the service started on CUDA: a CPU-only start is a choice, not a fault. GPU_CHECK_S=0 turns it off.
GPU_CHECK_S = float(os.environ.get("GPU_CHECK_S", "60"))
GPU = {"ok": True, "why": ""}
_CUDA_PY = ("import ctypes, sys\n"
            "try:\n    c = ctypes.CDLL('libcuda.so.1')\nexcept OSError:\n    sys.exit(3)\n"
            "n = ctypes.c_int(0)\n"
            "sys.exit(0 if c.cuInit(0) == 0 and c.cuDeviceGetCount(ctypes.byref(n)) == 0 and n.value > 0 else 4)\n")


def gpu_loop():
    while GPU_CHECK_S > 0 and DEVICE == "cuda":
        try:
            r = subprocess.run([sys.executable, "-c", _CUDA_PY], capture_output=True, timeout=30)
            ok, why = r.returncode == 0, {0: "", 3: "no CUDA driver library", 4: "CUDA sees no GPU"}.get(r.returncode, f"probe exit {r.returncode}")
        except (OSError, subprocess.SubprocessError) as e:
            ok, why = False, type(e).__name__
        if ok != GPU["ok"]:
            print(f"[upscaler] gpu ok={ok} {why}", flush=True)
        GPU.update(ok=ok, why=why)
        time.sleep(GPU_CHECK_S)


if __name__ == "__main__":
    threading.Thread(target=gpu_loop, daemon=True).start()
    print(f"[upscaler] listening on :{PORT}, device={DEVICE}, model={MODEL_NAME}, cuda_available={torch.cuda.is_available()}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
