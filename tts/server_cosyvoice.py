#!/usr/bin/env python3
"""
tts (fun-cosyvoice3) -- OpenAI-compatible TTS wrapper: POST /v1/audio/speech
{"input": "...", "voice": "auto", "response_format": "wav|mp3|opus"} -> audio bytes.
CosyVoice clones a reference clip: voice "auto" uses /voices/<language>.wav (es, ru, en; language from the text: Cyrillic = ru,
Spanish accents or " el " = es, else en), any other name uses /voices/<name>.wav. Cross-lingual mode (no transcript needed).
The model is run with stream=True and the chunks are joined; the header X-First-Chunk-Seconds says when the first chunk was ready
(what a streaming client would wait). Stdlib HTTP server like the other tts/ services. LAN-only, no auth.
"""
import io
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf
import torch
from huggingface_hub import snapshot_download
from cosyvoice.cli.cosyvoice import AutoModel

PORT = int(os.environ.get("PORT", "5002"))
VOICES = os.environ.get("VOICES_DIR", "/voices")
REPO = os.environ.get("COSYVOICE_REPO", "FunAudioLLM/Fun-CosyVoice3-0.5B-2512")
PREFIX = "You are a helpful assistant.<|endofprompt|>"
_lock = threading.Lock()
model = AutoModel(model_dir=snapshot_download(REPO))
SR = model.sample_rate
print("cosyvoice ready, sample rate", SR, flush=True)


def language_of(text):
    low = text.lower()
    if any("а" <= c <= "я" or c == "ё" for c in low):
        return "ru"
    return "es" if any(c in low for c in "áéíóúñ¿¡") or " el " in f" {low} " else "en"


def synth(text, voice):
    name = language_of(text) if voice == "auto" else voice
    ref = os.path.join(VOICES, f"{name}.wav")
    if not os.path.isfile(ref):
        raise FileNotFoundError(f"no reference clip {ref}")
    t0, first, parts = time.time(), None, []
    with _lock, torch.inference_mode():
        for chunk in model.inference_cross_lingual(PREFIX + text, ref, stream=True):
            if first is None:
                first = time.time() - t0
            parts.append(chunk["tts_speech"].squeeze(0).cpu().numpy())
    return np.concatenate(parts), first


def encode(audio, fmt):
    buf = io.BytesIO()
    sf.write(buf, audio, SR, format="WAV", subtype="PCM_16")
    wav = buf.getvalue()
    if fmt == "wav":
        return wav, "audio/wav"
    args = {"mp3": ["-f", "mp3"], "opus": ["-c:a", "libopus", "-f", "ogg"]}[fmt]
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", *args, "pipe:1"], input=wav, capture_output=True, check=True).stdout
    return out, {"mp3": "audio/mpeg", "opus": "audio/ogg"}[fmt]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body=b"", ctype="text/plain", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
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
        if fmt not in ("wav", "mp3", "opus"):
            return self._send(400, b"unsupported response_format")
        voice = str(req.get("voice", "auto"))
        if "/" in voice or ".." in voice:
            return self._send(400, b"invalid voice")
        try:
            audio, first = synth(text, voice)
            body, ctype = encode(audio, fmt)
        except Exception as e:
            return self._send(500, str(e).encode())
        self._send(200, body, ctype, {"X-First-Chunk-Seconds": f"{first or 0:.2f}"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
