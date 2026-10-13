#!/usr/bin/env python3
"""
stt-proxy -- OpenAI-compatible speech to text in front of the home STT hosts, for Open WebUI's voice mode.

  POST /v1/audio/transcriptions   multipart: file, [language], [model, ignored]  ->  {"text": "..."}
  GET  /healthz

Open WebUI used to send the web user's audio straight to Groq (cloud, one key, no fallback): a dead key meant a 401 and
no voice (2026-10-12). This tries the same hosts as `gateway transcribe`, in the order of the "stt" list of
/etc/aibridge/gateways.json (GPU first, the CPU container last), and never leaves home. No cloud step by design.
Only open-webui reaches it, over the compose network (not published). Nothing is stored.

Env: GATEWAYS_CONFIG (/etc/aibridge/gateways.json), PORT (8650), MAX_MB (100), FAST_S (60), SLOW_S (300).
"""
import json, os, time, urllib.error, urllib.request
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

CONF = os.environ.get("GATEWAYS_CONFIG", "/etc/aibridge/gateways.json")
PORT = int(os.environ.get("PORT", "8650"))
MAX_BYTES = int(os.environ.get("MAX_MB", "100")) * 1048576
FAST_S, SLOW_S = int(os.environ.get("FAST_S", "60")), int(os.environ.get("SLOW_S", "300"))
LANGS = ("es", "ru", "en")


def hosts():
    try:
        return json.load(open(CONF)).get("stt", [])
    except (OSError, ValueError):
        return []


def transcribe(audio, lang):
    """(text, host name) from the first STT host that answers; raises RuntimeError listing the ones that did not."""
    down = []   # also logged when a later host answers: a GPU that keeps failing must not stay invisible
    for h in sorted(hosts(), key=lambda h: bool(h.get("slow"))):   # fast hosts first, the slow CPU one last
        req = urllib.request.Request(h["url"].rstrip("/") + f"/transcribe?lang={lang}", data=audio, method="POST",
                                     headers={"Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(req, timeout=SLOW_S if h.get("slow") else FAST_S) as r:
                text = json.load(r)["text"]
            if down:
                print(f"fell back to {h['name']}: " + "; ".join(down), flush=True)
            return text, h["name"]
        except Exception as e:   # down, busy (429), timeout, bad audio: try the next one
            down.append(f"{h['name']}: " + (f"HTTP {e.code}" if isinstance(e, urllib.error.HTTPError) else type(e).__name__))
    raise RuntimeError("no STT host answered (" + "; ".join(down or ["none configured"]) + ")")


def parse_multipart(content_type, body):
    """{field name: bytes} of a multipart/form-data body."""
    msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    return {p.get_param("name", header="content-disposition"): p.get_payload(decode=True) for p in msg.iter_parts()}


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
        self._send(200, {"ok": True, "hosts": [h["name"] for h in hosts()]}) if urlparse(self.path).path == "/healthz" \
            else self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if urlparse(self.path).path not in ("/v1/audio/transcriptions", "/audio/transcriptions"):
            return self._send(404, {"error": {"message": "not found"}})
        try:
            body = read_body(self)
        except ValueError:
            return self._send(400, {"error": {"message": "bad chunked body"}})
        if body is None:
            return self._send(413, {"error": {"message": "empty or too large"}})
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
            text, host = transcribe(audio, lang if lang in LANGS else "auto")
        except RuntimeError as e:
            print(f"failed: {e}", flush=True)
            return self._send(502, {"error": {"message": str(e)}})
        print(f"{host}: {len(audio) // 1024} KB in {time.time() - t:.1f}s (lang {lang or 'auto'})", flush=True)
        self._send(200, {"text": text})


if __name__ == "__main__":
    print(f"stt-proxy on :{PORT}, hosts {[h['name'] for h in hosts()]}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
