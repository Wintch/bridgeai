#!/usr/bin/env python3
"""tts (Sesame CSM-1B) -- minimal OpenAI-compatible wrapper, default voice only, no cloning, no sentence
splitting, no retries: deliberately bare-bones, built only to compare by ear against Chatterbox on the same
default-voice footing (2026-10-25). English only per the model's own card; not meant to serve real replies.

POST /v1/audio/speech {"input": "...", "response_format": "wav|mp3"} -> audio bytes. GET /healthz.
Needs HF_TOKEN (docker run -e HF_TOKEN=...) from an account with access granted to the gated sesame/csm-1b and
meta-llama/Llama-3.2-1B repos on huggingface.co.
"""
import io
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import soundfile as sf
import torch
from generator import load_csm_1b

PORT = int(os.environ.get("PORT", "5002"))
device = "cuda" if torch.cuda.is_available() else "cpu"
generator = load_csm_1b(device=device)
print("csm-1b ready, sample rate", generator.sample_rate, flush=True)


def encode(audio, sr, fmt):
    buf = io.BytesIO()
    sf.write(buf, audio.cpu().numpy(), sr, format="WAV", subtype="PCM_16")
    wav = buf.getvalue()
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
        fmt = req.get("response_format", "mp3")
        try:
            audio = generator.generate(text=text, speaker=0, context=[], max_audio_length_ms=20_000)
            body, ctype = encode(audio, generator.sample_rate, fmt)
        except Exception as e:
            return self._send(500, str(e).encode())
        self._send(200, body, ctype)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
