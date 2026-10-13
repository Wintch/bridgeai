#!/usr/bin/env python3
"""
voice-proxy -- OpenAI-compatible speech to text AND text to speech in front of the home hosts, for Open WebUI's voice mode.

  POST /v1/audio/transcriptions   multipart: file, [language], [model, ignored]  ->  {"text": "..."}
  POST /v1/audio/speech           json: input, [voice], [response_format]        ->  audio bytes (X-Voice says which voice)
  GET  /healthz

Open WebUI used to send the web user's audio straight to Groq (cloud, one key, no fallback: a dead key meant a 401 and
no voice, 2026-10-12). This tries the same hosts as `gateway transcribe`, in the order of the "stt" list of
/etc/aibridge/gateways.json (GPU first, the CPU container last), and never leaves home. No cloud step by design.
Speech: the "tts" hosts of the same file (GPU hosts), then LOCAL_TTS_URL (the Piper container next to Open WebUI) as the
last resort. 2026-10-13: that local Piper alone took ~25 s for a Russian answer and was killed by its memory limit, so
the voice call "stayed thinking"; the GPU hosts answer in ~1 s.
Only open-webui reaches it, over the compose network (not published). Nothing is stored.

A host that does not answer the TCP connect within CONNECT_S is skipped for DOWN_FOR_S: a guest network's firewall DROPS
packets to hosts it may not reach (a plain request hangs for its whole timeout), and a sleeping GPU box does the same.

One-language people (2026-10-13: one speaks only Russian, another only Spanish): STT_LANG fixes the language of every
transcription (no auto-detection to get wrong on a short clip) and TTS_VOICE the voice (a name the hosts know; a host
that lacks it picks a voice by the text's language). Both empty = auto, as for someone who uses all three languages.

Env: GATEWAYS_CONFIG (/etc/aibridge/gateways.json), PORT (8650), MAX_MB (100), CONNECT_S (3), DOWN_FOR_S (30),
FAST_S (60), SLOW_S (300), TTS_S (40), LOCAL_TTS_URL (http://tts-piper:5002; empty = no local fallback),
STT_LANG (es|ru|en|empty), TTS_VOICE (e.g. ru_RU-ruslan-medium, or empty).
"""
import http.client, json, os, time
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

CONF = os.environ.get("GATEWAYS_CONFIG", "/etc/aibridge/gateways.json")
PORT = int(os.environ.get("PORT", "8650"))
MAX_BYTES = int(os.environ.get("MAX_MB", "100")) * 1048576
CONNECT_S, DOWN_FOR_S = float(os.environ.get("CONNECT_S", "3")), int(os.environ.get("DOWN_FOR_S", "30"))
FAST_S, SLOW_S, TTS_S = int(os.environ.get("FAST_S", "60")), int(os.environ.get("SLOW_S", "300")), int(os.environ.get("TTS_S", "40"))
LOCAL_TTS_URL = os.environ.get("LOCAL_TTS_URL", "http://tts-piper:5002")
LANGS = ("es", "ru", "en")
STT_LANG = os.environ.get("STT_LANG", "").strip().lower()
TTS_VOICE = os.environ.get("TTS_VOICE", "").strip()
_down = {}   # host url -> time.time() until which it is skipped


def hosts(kind):
    try:
        return json.load(open(CONF)).get(kind, [])
    except (OSError, ValueError):
        return []


def post(url, path, data, ctype, read_s):
    """(status, headers, body) of one POST. Raises OSError on a connect failure or timeout, quickly for a dropped host."""
    u = urlparse(url)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=CONNECT_S)
    try:
        conn.connect()
        conn.sock.settimeout(read_s)
        conn.request("POST", (u.path.rstrip("/") + path), body=data, headers={"Content-Type": ctype})
        r = conn.getresponse()
        return r.status, r, r.read()
    finally:
        conn.close()


def try_hosts(cands, path, data, ctype, read_s):
    """First (name, headers, body) answering 200 among cands [(name, url, read_s)]; RuntimeError listing why the rest failed."""
    down = []
    for name, url, limit in cands:
        if _down.get(url, 0) > time.time():
            down.append(f"{name}: skipped, down")
            continue
        try:
            status, r, body = post(url, path, data, ctype, limit)
            if status == 200:
                if down:
                    print(f"{path} fell back to {name}: " + "; ".join(down), flush=True)
                return name, r, body
            down.append(f"{name}: HTTP {status}")          # busy (429) or bad audio: the host is up, try the next
        except OSError as e:
            _down[url] = time.time() + DOWN_FOR_S           # no connect or no answer in time: skip it for a while
            down.append(f"{name}: {type(e).__name__}")
    raise RuntimeError("no host answered (" + "; ".join(down or ["none configured"]) + ")")


def transcribe(audio, lang):
    """(text, host name) from the first STT host that answers."""
    lang = STT_LANG or (lang if lang in LANGS else "auto")
    cands = [(h["name"], h["url"], SLOW_S if h.get("slow") else FAST_S)
             for h in sorted(hosts("stt"), key=lambda h: bool(h.get("slow")))]   # fast hosts first, the slow CPU one last
    name, _, body = try_hosts(cands, f"/transcribe?lang={lang}", audio, "application/octet-stream", 0)
    return json.loads(body)["text"], name


def speak(payload):
    """(audio bytes, content type, voice, host) from the first TTS host that answers: GPU hosts, then the local Piper."""
    cands = [(h["name"], h["url"], TTS_S) for h in hosts("tts")]
    if LOCAL_TTS_URL:
        cands.append(("tts-local", LOCAL_TTS_URL, TTS_S))
    name, r, body = try_hosts(cands, "/v1/audio/speech", payload, "application/json", 0)
    return body, r.getheader("Content-Type", "audio/mpeg"), r.getheader("X-Voice", ""), name


def read_body(h):
    """Request body bytes, or None when empty or over MAX_BYTES. Open WebUI (aiohttp) sends it chunked, with no Content-Length."""
    if "chunked" in h.headers.get("Transfer-Encoding", "").lower():
        out = bytearray()
        while True:
            size = int(h.rfile.readline().split(b";")[0].strip() or b"0", 16)
            if size == 0:
                while h.rfile.readline().strip():   # trailer headers, up to the blank line
                    pass
                return bytes(out) or None
            out += h.rfile.read(size)
            h.rfile.readline()                      # CRLF after each chunk
            if len(out) > MAX_BYTES:
                return None
    n = int(h.headers.get("Content-Length", 0))
    return h.rfile.read(n) if 0 < n <= MAX_BYTES else None


def parse_multipart(content_type, body):
    """{field name: bytes} of a multipart/form-data body."""
    msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    return {p.get_param("name", header="content-disposition"): p.get_payload(decode=True) for p in msg.iter_parts()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, {"ok": True, "stt": [h["name"] for h in hosts("stt")], "tts": [h["name"] for h in hosts("tts")],
                         "stt_lang": STT_LANG or "auto", "tts_voice": TTS_VOICE or "auto"}) \
            if urlparse(self.path).path == "/healthz" else self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/v1/audio/transcriptions", "/audio/transcriptions", "/v1/audio/speech", "/audio/speech"):
            return self._send(404, {"error": {"message": "not found"}})
        try:
            body = read_body(self)
        except ValueError:
            return self._send(400, {"error": {"message": "bad chunked body"}})
        if body is None:
            return self._send(413, {"error": {"message": "empty or too large"}})
        (self._speech if path.endswith("/speech") else self._transcription)(body)

    def _transcription(self, body):
        try:
            form = parse_multipart(self.headers.get("Content-Type", ""), body)
        except Exception:
            return self._send(400, {"error": {"message": "bad multipart body"}})
        audio = form.get("file")
        if not audio:
            return self._send(400, {"error": {"message": "no file field"}})
        lang = (form.get("language") or b"").decode("utf-8", "replace").strip().lower()[:2]
        t = time.time()
        try:
            text, host = transcribe(audio, lang)
        except RuntimeError as e:
            print(f"transcription failed: {e}", flush=True)
            return self._send(502, {"error": {"message": str(e)}})
        print(f"{host}: {len(audio) // 1024} KB in {time.time() - t:.1f}s (lang {STT_LANG or lang or 'auto'})", flush=True)
        self._send(200, {"text": text})

    def _speech(self, body):
        t = time.time()
        try:
            req = json.loads(body)
            text = req["input"]
        except (ValueError, KeyError, TypeError):
            return self._send(400, {"error": {"message": "need json with input"}})
        req["voice"] = TTS_VOICE or "auto"   # never the voice Open WebUI has stored: it once pinned Spanish for every language
        try:
            audio, ctype, voice, host = speak(json.dumps(req).encode())
        except RuntimeError as e:
            print(f"speech failed: {e}", flush=True)
            return self._send(502, {"error": {"message": str(e)}})
        print(f"speech {host}: {len(text)} chars, {len(audio) // 1024} KB in {time.time() - t:.1f}s ({voice})", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)


if __name__ == "__main__":
    print(f"voice-proxy on :{PORT}, stt {[h['name'] for h in hosts('stt')]}, tts {[h['name'] for h in hosts('tts')]} "
          f"+ local {LOCAL_TTS_URL or 'none'}, language {STT_LANG or 'auto'}, voice {TTS_VOICE or 'auto'}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
