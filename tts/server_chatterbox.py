#!/usr/bin/env python3
"""
tts (chatterbox multilingual) -- OpenAI-compatible TTS wrapper: POST /v1/audio/speech
{"input": "...", "voice": "auto", "response_format": "wav|mp3|opus", "language": "es|ru|en (optional)"} -> audio bytes.
voice "auto": /voices/auto-<lang>.wav, else /voices/auto.wav, else the model's default voice. Any other name that matches
/voices/<name>.wav is used as the reference clip (zero-shot cloning), an unknown one gets the default voice. The language comes from the text (Cyrillic = ru, else Spanish vs English by common words, the rule of
server_piper.py) unless the request sets "language". Every reply is synthesized sentence by sentence (the model drifts on long
inputs). "stream": true sends the audio sentence by sentence (HTTP chunked, format "pcm" = raw 16-bit mono at the
model rate, announced in the X-Sample-Rate header, or "wav" with an open-ended header): the first sentence is audible after
its own synthesis, not after the whole text. Stdlib HTTP server, same convention as the other tts/ services. LAN-only, no auth.
"""
import io
import json
import os
import re
import struct
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import soundfile as sf
import numpy as np
import torch
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
from sentence_split import split_sentences

PORT = int(os.environ.get("PORT", "5002"))
VOICES = os.environ.get("VOICES_DIR", "/voices")
CFG = float(os.environ.get("CFG_WEIGHT", "0.5"))
MAX_S_PER_CHAR = float(os.environ.get("MAX_S_PER_CHAR", "0.11"))
MIN_S_PER_CHAR = float(os.environ.get("MIN_S_PER_CHAR", "0.05"))
TYPICAL_S_PER_CHAR = 0.085
RETRIES = int(os.environ.get("TAKE_RETRIES", "2"))
GAP_S = float(os.environ.get("SENTENCE_GAP_S", "0.12"))  # silence between streamed sentences
_lock = threading.Lock()
model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
SR = model.sr
with torch.inference_mode():
    model.generate("Hola.", language_id="es", cfg_weight=CFG)  # warm-up: the first real request must not pay for CUDA init
print("chatterbox ready, sample rate", SR, flush=True)


# Same language rule as tts/server_piper.py detect_lang and aibridge/gateway.py text_lang (keep the three identical): the
# person's text decides the language, not the voice, and a Spanish sentence without accents ("hola como estas") is still Spanish.
ES_WORDS = set("el la los las de del que y en un una es por con para no se lo le su al como más pero sí muy esta este "
               "está hay ya también porque cuando qué cómo".split())
EN_WORDS = set("the a an of and to in is it that for on with as are was be this you not have at but or from by "
               "what how can will your".split())


def language_of(text, forced=None):
    if forced:
        return forced
    letters = [c for c in text if c.isalpha()]
    if letters and sum("\u0400" <= c <= "\u04ff" for c in letters) / len(letters) > 0.3:
        return "ru"
    words = re.findall(r"[a-záéíóúñü]+", text.lower())
    es, en = sum(w in ES_WORDS for w in words), sum(w in EN_WORDS for w in words)
    return "en" if en > es else "es"


def synth(text, voice, lang):
    kw = {"language_id": lang, "cfg_weight": CFG}
    # voice "auto" looks for a house voice: /voices/auto-<lang>.wav, then /voices/auto.wav; otherwise the model's own voice.
    for name in ([f"auto-{lang}", "auto"] if voice == "auto" else [voice]):
        ref = os.path.join(VOICES, f"{name}.wav")
        if os.path.isfile(ref):
            kw["audio_prompt_path"] = ref
            break
    # The model sometimes fails to stop (a 4 s sentence comes back 9-12 s long, rambling) and sometimes swallows words (45
    # characters in 1.7 s). Outside [MIN, MAX] seconds per character, sample again (up to RETRIES times) and keep the take
    # whose pace is closest to the normal one.
    lo, hi = MIN_S_PER_CHAR * len(text), MAX_S_PER_CHAR * len(text) + 1.5
    best = None
    for attempt in range(1 + RETRIES):
        with _lock, torch.inference_mode():
            audio = model.generate(text, **kw).squeeze(0).cpu().numpy()
        if best is None or abs(len(audio) / SR - TYPICAL_S_PER_CHAR * len(text)) < abs(len(best) / SR - TYPICAL_S_PER_CHAR * len(text)):
            best = audio
        if lo <= len(best) / SR <= hi:
            break
        print(f"odd take ({len(audio) / SR:.1f}s for {len(text)} chars), attempt {attempt + 1}", flush=True)
    return best


def synth_text(text, voice, lang):
    """The whole text as one array: sentence by sentence (the model drifts on long inputs), edges trimmed and faded, fixed gap."""
    gap = np.zeros(int(SR * GAP_S), dtype="float32")
    parts = []
    for sentence in split_sentences(text) or [text]:
        if parts:
            parts.append(gap)
        parts.append(trim_silence(synth(sentence, voice, lang), SR))
    return np.concatenate(parts)


def pcm16(audio):
    return (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def trim_silence(audio, sr, thresh=0.01, keep_s=0.04, fade_in_s=0.01, fade_out_s=0.05):
    """Cut the model's leading/trailing silence of one sentence (up to a second of it) so the fixed gap sets the pause, then
    fade the edges: the model often ends a sentence at full volume, and a hard cut to digital silence is an audible click."""
    loud = np.flatnonzero(np.abs(audio) > thresh)
    if loud.size == 0:
        return audio
    keep = int(sr * keep_s)
    out = audio[max(0, loud[0] - keep): loud[-1] + keep].astype("float32").copy()
    for n, rising in ((int(sr * fade_in_s), True), (int(sr * fade_out_s), False)):
        n = min(n, len(out) // 2)
        if n:
            ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n, dtype="float32"))  # raised cosine 0 -> 1
            if rising:
                out[:n] *= ramp
            else:
                out[-n:] *= ramp[::-1]
    return out


def open_wav_header(sr):
    """44-byte WAV header with unknown length (0xFFFFFFFF), the usual convention for streamed WAV."""
    return b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16) + b"data" + struct.pack("<I", 0xFFFFFFFF)


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
    protocol_version = "HTTP/1.1"  # chunked streaming needs it; every other reply sends Content-Length

    def _stream(self, text, voice, lang, fmt):
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav" if fmt == "wav" else "audio/L16")
        self.send_header("X-Sample-Rate", str(SR))
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def chunk(b):
            self.wfile.write(f"{len(b):x}\r\n".encode() + b + b"\r\n")
            self.wfile.flush()

        try:
            if fmt == "wav":
                chunk(open_wav_header(SR))
            gap = pcm16(np.zeros(int(SR * GAP_S), dtype="float32"))
            for i, sentence in enumerate(split_sentences(text)):
                chunk((gap if i else b"") + pcm16(trim_silence(synth(sentence, voice, lang), SR)))
        except Exception as e:  # headers are out already: cut the stream, the client sees a short audio
            print("stream failed:", e, flush=True)
        self.wfile.write(b"0\r\n\r\n")

    def _send(self, code, body=b"", ctype="text/plain", voice=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if voice:
            self.send_header("X-Voice", voice)  # gateway speak logs it, same as the Piper server
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
        stream = bool(req.get("stream"))
        fmt = req.get("response_format", "pcm" if stream else "mp3")
        if fmt not in (("wav", "pcm") if stream else ("wav", "mp3", "opus")):
            return self._send(400, b"unsupported response_format")
        voice = str(req.get("voice", "auto"))
        if "/" in voice or ".." in voice:
            return self._send(400, b"invalid voice")
        if stream:
            return self._stream(text, voice, language_of(text, req.get("language")), fmt)
        try:
            lang = language_of(text, req.get("language"))
            body, ctype = encode(synth_text(text, voice, lang), fmt)
        except Exception as e:
            return self._send(500, str(e).encode())
        self._send(200, body, ctype, f"chatterbox-{voice}-{lang}")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
