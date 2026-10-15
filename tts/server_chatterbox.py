#!/usr/bin/env python3
"""
tts (chatterbox multilingual) -- OpenAI-compatible TTS wrapper: POST /v1/audio/speech
{"input": "...", "voice": "auto", "response_format": "wav|mp3|opus", "language": "es|ru|en (optional)"} -> audio bytes.
voice "auto" (or any unknown name): the model's default voice. A name that matches /voices/<name>.wav is used as the reference
clip (zero-shot cloning). The language comes from the text (Cyrillic = ru, Spanish accents or " el " = es, else en) unless the
request sets "language". Stdlib HTTP server, same convention as the other tts/ services. LAN-only, no auth.
"""
import io
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import soundfile as sf
import torch
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

PORT = int(os.environ.get("PORT", "5002"))
VOICES = os.environ.get("VOICES_DIR", "/voices")
CFG = float(os.environ.get("CFG_WEIGHT", "0.5"))
_lock = threading.Lock()
model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
SR = model.sr
print("chatterbox ready, sample rate", SR, flush=True)


def language_of(text, forced=None):
    if forced:
        return forced
    low = text.lower()
    if any("а" <= c <= "я" or c == "ё" for c in low):
        return "ru"
    return "es" if any(c in low for c in "áéíóúñ¿¡") or " el " in f" {low} " else "en"


def synth(text, voice, lang):
    ref = os.path.join(VOICES, f"{voice}.wav")
    kw = {"language_id": lang, "cfg_weight": CFG}
    if voice != "auto" and os.path.isfile(ref):
        kw["audio_prompt_path"] = ref
    with _lock, torch.inference_mode():
        wav = model.generate(text, **kw)
    return wav.squeeze(0).cpu().numpy()


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
            body, ctype = encode(synth(text, voice, language_of(text, req.get("language"))), fmt)
        except Exception as e:
            return self._send(500, str(e).encode())
        self._send(200, body, ctype)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
