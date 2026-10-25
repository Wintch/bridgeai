#!/usr/bin/env python3
"""tts (Sesame CSM-1B via Hugging Face Transformers) -- minimal OpenAI-compatible wrapper, default voice only, no
cloning, no context, no sentence splitting or retries: deliberately bare-bones, built only to compare by ear
against Chatterbox on the same default-voice footing (2026-10-25). English only per the model's own card; not
meant to serve real replies.

POST /v1/audio/speech {"input": "...", "response_format": "wav|mp3"} -> audio bytes. GET /healthz.
Needs HF_TOKEN (docker run -e HF_TOKEN=...) from an account with access granted to the gated sesame/csm-1b repo.
"""
import io
import json
import os
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from transformers import AutoProcessor, CsmForConditionalGeneration

MODEL_ID = "sesame/csm-1b"
PORT = int(os.environ.get("PORT", "5002"))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
processor = AutoProcessor.from_pretrained(MODEL_ID)

# The checkpoint is stored as F32 (~8 GB for 2B params, too tight to compare alongside anything else on an 8 GB
# card); bf16 halves that to ~4 GB, close enough to Chatterbox's ~3.5 GB for a fair side-by-side.
model = CsmForConditionalGeneration.from_pretrained(MODEL_ID, device_map=DEVICE, torch_dtype=torch.bfloat16)
print("csm-1b ready", flush=True)


def synth_to_wav_bytes(text):
    inputs = processor(f"[0]{text}", add_special_tokens=True).to(DEVICE)
    # generate()'s default max_new_tokens (~125, per a community generation_config) cuts off anything past a
    # short sentence; scale it with the text instead of hardcoding one number for every request.
    audio = model.generate(**inputs, output_audio=True, max_new_tokens=min(4096, 20 * len(text)))
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        processor.save_audio(audio, f.name)
        return open(f.name, "rb").read()


def encode(text, fmt):
    wav = synth_to_wav_bytes(text)
    if fmt == "wav":
        return wav, "audio/wav"
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-f", "mp3", "pipe:1"],
                          input=wav, capture_output=True, check=True).stdout
    return out, "audio/mpeg"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body=b"", ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, b"ok") if self.path == "/healthz" else self._send(404)

    def do_POST(self):
        if self.path != "/v1/audio/speech":
            return self._send(404)
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            text = req["input"]
        except Exception:
            return self._send(400, b"invalid request")
        try:
            body, ctype = encode(text, req.get("response_format", "mp3"))
        except Exception as e:
            return self._send(500, str(e).encode())
        self._send(200, body, ctype)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
