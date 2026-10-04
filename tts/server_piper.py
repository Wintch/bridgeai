#!/usr/bin/env python3
"""
tts (piper, CPU) -- OpenAI-compatible TTS wrapper: POST /v1/audio/speech
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
from piper import PiperVoice

PORT = int(os.environ.get("PORT", "5002"))
DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "es_MX-claude-high")
_voices = {}
_lock = __import__("threading").Lock()
SR = 22050


def voice_for(name):
    if name not in _voices:
        _voices[name] = PiperVoice.load(f"/models/{name}.onnx")
    return _voices[name]


def synth(text, voice, speed):
    global SR
    v = voice_for(voice)
    SR = v.config.sample_rate
    with _lock:
        chunks = [np.frombuffer(c.audio_int16_bytes, dtype=np.int16).astype(np.float32) / 32768 for c in v.synthesize(text)]
    return np.concatenate(chunks)

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
        voice = req.get("voice", DEFAULT_VOICE)
        if not os.path.exists(f"/models/{voice}.onnx"):  # OpenAI names (alloy...) -> default
            voice = DEFAULT_VOICE
        fmt = req.get("response_format", "mp3")
        if fmt not in ("wav", "mp3", "opus"):
            return self._send(400, b"unsupported response_format")
        try:
            body, ctype = encode(synth(text, voice, float(req.get("speed", 1.0))), fmt)
        except Exception as e:
            return self._send(500, str(e).encode())
        self._send(200, body, ctype)


if __name__ == "__main__":
    synth("hola", DEFAULT_VOICE, 1.0)  # warm up
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
