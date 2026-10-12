#!/usr/bin/env python3
"""
upscaler -- minimal HTTP wrapper around Real-ESRGAN (x4) for GPU image
upscaling. POST raw image bytes to /upscale, get back a JPEG (quality 92).
Requests are queued one at a time on the shared GPU (never 429: the gateway
treats 429/5xx as host down); inputs over MAX_PIXELS get 413. Stdlib HTTP
server only, matching the rest of this project's convention.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

MODEL_PATH = "/app/weights/RealESRGAN_x4plus.pth"
PORT = int(os.environ.get("PORT", "8600"))
MAX_PIXELS = int(os.environ.get("MAX_PIXELS", str(16_000_000)))  # input pixels; the output is 16x that
MAX_BYTES = int(os.environ.get("MAX_MB", "64")) * 1024 * 1024
GPU_LOCK = threading.Lock()  # one enhance() at a time: the GPU is shared with the other services

model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
upsampler = RealESRGANer(
    scale=4,
    model_path=MODEL_PATH,
    model=model,
    tile=256,
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
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"ok device={DEVICE}".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        import sys
        sys.stderr.write("[upscaler] " + (fmt % args) + "\n")


if __name__ == "__main__":
    print(f"[upscaler] listening on :{PORT}, device={DEVICE}, cuda_available={torch.cuda.is_available()}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
