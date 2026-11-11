#!/usr/bin/env python3
"""
stt -- faster-whisper speech to text over HTTP. The same image runs on a GPU host (CUDA) or on a CPU-only host.

  GET  /healthz                         "ok <device> <model>" once the model is loaded
  POST /transcribe?lang=auto|es|ru|en   body = any audio or video file -> JSON:
       {"text", "language", "language_prob", "seconds", "audio_seconds", "device", "model", "compute_type"}

lang=auto (default) detects the language but only among LANGS (es, ru, en): whisper's free detection called short
Spanish and Russian clips Norwegian or Swedish (seen 2026-10). One transcription at a time per process (the model is
not shared across threads); others wait up to WAIT_S, then get 429. Nothing is stored: the upload lives in a temp file
for the request only. Stdlib HTTP server, like the other services here.

Env: MODEL (default large-v3-turbo), DEVICE (auto|cuda|cpu), COMPUTE_TYPE (default int8: works on Pascal GPUs and on
CPUs), CPU_THREADS (0 = all), PORT (8620), LANGS (es,ru,en).
"""
import json, os, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from faster_whisper import WhisperModel

MODEL = os.environ.get("MODEL", "large-v3-turbo")
DEVICE = os.environ.get("DEVICE", "auto")
COMPUTE = os.environ.get("COMPUTE_TYPE", "int8")
PORT = int(os.environ.get("PORT", "8620"))
LANGS = os.environ.get("LANGS", "es,ru,en").split(",")
WAIT_S = int(os.environ.get("WAIT_S", "120"))
MAX_BYTES = int(os.environ.get("MAX_MB", "1024")) * 1048576

if DEVICE == "auto":
    try:
        import ctranslate2
        DEVICE = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        DEVICE = "cpu"
t0 = time.time()
model = WhisperModel(MODEL, device=DEVICE, compute_type=COMPUTE, cpu_threads=int(os.environ.get("CPU_THREADS", "0")))
LOAD_S = time.time() - t0
LOCK = threading.Lock()


def transcribe(path, lang):
    if lang == "auto":
        # restrict detection to LANGS: take whisper's probabilities and keep the best allowed one
        from faster_whisper.audio import decode_audio
        audio = decode_audio(path, sampling_rate=16000)
        try:
            lang_probs = model.detect_language(audio[: 16000 * 30])[2]
            allowed = [(l, p) for l, p in lang_probs if l in LANGS]
            info_lang = max(allowed, key=lambda x: x[1]) if allowed else None
        except Exception:
            info_lang = None
        segments, info = model.transcribe(audio, language=info_lang[0] if info_lang else None, beam_size=5, vad_filter=True)
        prob = info_lang[1] if info_lang else info.language_probability
    else:
        segments, info = model.transcribe(path, language=lang, beam_size=5, vad_filter=True)
        prob = 1.0
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, info.language, prob, info.duration


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path == "/healthz":
            body = f"ok {DEVICE} {MODEL}".encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/transcribe":
            return self._json(404, {"error": "not found"})
        lang = parse_qs(url.query).get("lang", ["auto"])[-1]
        if lang != "auto" and lang not in LANGS:
            return self._json(400, {"error": f"lang must be auto or one of {LANGS}"})
        n = int(self.headers.get("Content-Length", 0))
        if not 0 < n <= MAX_BYTES:
            return self._json(413, {"error": "empty or too large"})
        with tempfile.NamedTemporaryFile(prefix="stt-") as f:
            left = n
            while left:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    return self._json(400, {"error": "body ended early"})
                f.write(chunk)
                left -= len(chunk)
            f.flush()
            if not LOCK.acquire(timeout=WAIT_S):
                return self._json(429, {"error": "busy"})
            try:
                t = time.time()
                text, language, prob, dur = transcribe(f.name, lang)
                took = time.time() - t
            except Exception as e:
                return self._json(500, {"error": f"{type(e).__name__}: {str(e)[:200]}"})
            finally:
                LOCK.release()
        print(f"transcribed {dur:.0f}s of audio in {took:.1f}s ({language})", flush=True)
        self._json(200, {"text": text, "language": language, "language_prob": round(prob, 3), "seconds": round(took, 2),
                         "audio_seconds": round(dur, 1), "device": DEVICE, "model": MODEL, "compute_type": COMPUTE})


if __name__ == "__main__":
    print(f"stt on :{PORT}, {MODEL} on {DEVICE} ({COMPUTE}), loaded in {LOAD_S:.1f}s, langs {LANGS}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
