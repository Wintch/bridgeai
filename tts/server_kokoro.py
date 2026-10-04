#!/usr/bin/env python3
"""
tts (kokoro) -- OpenAI-compatible TTS wrapper: POST /v1/audio/speech
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
from kokoro import KPipeline

PORT = int(os.environ.get("PORT", "5002"))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SR = 24000
# lang code by voice prefix: a=US en, b=UK en, e=es
LANG = {"a": "a", "b": "b", "e": "e"}
_pipes = {}
_lock = __import__("threading").Lock()


def pipe_for(voice):
    code = LANG.get(voice[0], "a")
    if code not in _pipes:
        _pipes[code] = KPipeline(lang_code=code, device=DEVICE)
    return _pipes[code]


def synth(text, voice, speed):
    with _lock:
        chunks = [np.asarray(a, dtype=np.float32) for _, _, a in pipe_for(voice)(text, voice=voice, speed=speed) if a is not None]
    return np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)


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
        voice = req.get("voice", "ef_dora")
        if voice[0] not in LANG or "_" not in voice:  # OpenAI names (alloy...) -> default
            voice = os.environ.get("DEFAULT_VOICE", "ef_dora")
        fmt = req.get("response_format", "mp3")
        if fmt not in ("wav", "mp3", "opus"):
            return self._send(400, b"unsupported response_format")
        try:
            body, ctype = encode(synth(text, voice, float(req.get("speed", 1.0))), fmt)
        except Exception as e:
            return self._send(500, str(e).encode())
        self._send(200, body, ctype)


if __name__ == "__main__":
    synth("hola", os.environ.get("DEFAULT_VOICE", "ef_dora"), 1.0)  # warm up
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
