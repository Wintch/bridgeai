#!/usr/bin/env python3
"""
tts (qwen3-tts) -- OpenAI-compatible TTS wrapper: POST /v1/audio/speech
{"input": "...", "voice": "ef_dora", "response_format": "wav|mp3|opus"} -> audio bytes.
Stdlib HTTP server, same convention as upscaler/. LAN-only, no auth.
"""
import io
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

PORT = int(os.environ.get("PORT", "5002"))
MODEL = os.environ.get("QWEN_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
DEFAULT_SPEAKER = os.environ.get("DEFAULT_VOICE", "Ryan")
SR = 24000
_lock = __import__("threading").Lock()
model = Qwen3TTSModel.from_pretrained(
    MODEL, device_map="cuda:0", dtype=getattr(torch, os.environ.get("QWEN_DTYPE", "float32")), attn_implementation="sdpa"
)
print("supported speakers:", model.get_supported_speakers(), flush=True)
print("supported languages:", model.get_supported_languages(), flush=True)


def synth(text, voice, speed):
    global SR
    lang = "Spanish" if any(c in text.lower() for c in "áéíóúñ¿¡") or " el " in f" {text.lower()} " else "English"
    with _lock:
        wavs, SR = model.generate_custom_voice(text=text, language=lang, speaker=voice)
    return np.asarray(wavs[0], dtype=np.float32)

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
    def _send(self, code, body=b"", ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            return self._send(200, b"ok")
        self._send(404)

    def do_POST(self):
        if self.path != "/v1/audio/speech":
            return self._send(404)
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            text = req["input"]
        except Exception:
            return self._send(400, b"invalid request")
        voice = req.get("voice", DEFAULT_SPEAKER)
        fmt = req.get("response_format", "mp3")
        if fmt not in ("wav", "mp3", "opus"):
            return self._send(400, b"unsupported response_format")
        try:
            body, ctype = encode(synth(text, voice, float(req.get("speed", 1.0))), fmt)
        except Exception as e:
            return self._send(500, str(e).encode())
        self._send(200, body, ctype)


if __name__ == "__main__":
    synth("hola", DEFAULT_SPEAKER, 1.0)  # warm up
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
