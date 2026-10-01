#!/usr/bin/env python3
"""
aibridge -- GET-to-GET command bridge between two AIs (PoC).

One AI (the asker) requests something via GET /ask; the server gives it a
token and a result_url where the answer will show up in markdown. The other
AI (the consumer, e.g. "antigravity") polls GET /next, processes it, and
deposits the answer via GET /deposit. Every call also returns the last known
credit % of each provider (self-reported), to help decide whether to keep
asking or switch providers.

100% filesystem state (no DB, no in-memory state): every request and every
answer is a file. Same stdlib pattern as arjplayer/app.py and
x96_pmadminka/status_server.py (BaseHTTPRequestHandler, no dependencies).

Every 200 JSON response on "public" endpoints (ask/credits/credit/
result.json/healthz) also includes available_ports/try_port -- confirmed
public ports on the edge (443 and 8443 today), with a semi-random suggestion
of which to try. Experiment from 2026-09-30, see README.md.

Endpoints (all require ?key=<shared secret>, 403 if it doesn't match):
  GET /ask?text=&model=&effort=&provider=&credit_pct=
      -> {"token","result_url","credits","available_ports","try_port"}
  GET /next?provider=
      -> {"token","text","model","effort"}  or 204 if nothing is pending
  GET /deposit?token=&body=&credit_pct=
      -> {"ok": true}
  GET /result/<token>.json
      -> always 200: {"status":"pending"|"done","result":...} (the default
         that /ask returns in result_url -- compatible with clients that
         treat any non-200 as a hard error)
  GET /result/<token>.md|.txt
      -> the deposited text, or 202 "pending" if it hasn't arrived yet (for
         manual curl/debug, no longer what's offered by default)
  GET /healthz -> ok (no key needed)

BASE_DIR (default /opt/aibridge):
  queue/<provider>__<token>.json       pending requests
  queue/in_progress/<provider>__<token>.json   picked up, not yet answered
  results/<token>.md                   completed answers
  credit.json                          {"<provider>": {"pct":N,"updated_at":iso}}
  secret.key                           legacy key (label "sesame"), self-generates
  keys.json                            {"<key>": "<label>"} -- extra keys (e.g. "chatgpt"),
                                        auto-generated if a requested label is missing. Same
                                        pipeline for all of them: the key used gets stored
                                        as job["source"] on every request, to track who's
                                        asking without isolating storage yet.
"""
import glob
import json
import os
import random
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

BASE_DIR = os.environ.get("AIBRIDGE_BASE_DIR", "/opt/aibridge")
QUEUE_DIR = os.path.join(BASE_DIR, "queue")
INPROGRESS_DIR = os.path.join(QUEUE_DIR, "in_progress")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
CREDIT_FILE = os.path.join(BASE_DIR, "credit.json")
SECRET_FILE = os.path.join(BASE_DIR, "secret.key")
KEYS_FILE = os.path.join(BASE_DIR, "keys.json")

BIND = os.environ.get("AIBRIDGE_BIND", "127.0.0.1")
PORT = int(os.environ.get("AIBRIDGE_PORT", "8097"))
PUBLIC_BASE_URL = os.environ.get("AIBRIDGE_PUBLIC_BASE_URL", f"http://{BIND}:{PORT}").rstrip("/")

# Alternate public ports (experiment 2026-09-30): if the asker's egress
# intermittently filters 443, having another confirmed port (8443, same
# vhost/cert on the edge) gives it something else to try. Travels in every
# response along with a semi-random suggestion -- the point isn't that "the
# good one" is always the same, it's to see whether rotating actually helps
# or not.
PUBLIC_PORTS = [int(p) for p in os.environ.get("AIBRIDGE_PUBLIC_PORTS", "443,8443").split(",") if p.strip()]


def port_hint():
    return {"available_ports": PUBLIC_PORTS, "try_port": random.choice(PUBLIC_PORTS)}

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PROVIDER_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
RESULT_PATH_RE = re.compile(r"^/result/([A-Za-z0-9_-]{1,64})\.(md|txt|html|json)$")
RESULT_CTYPE = {
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "json": "application/json; charset=utf-8",
}

_credit_lock = threading.Lock()


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(path, data_bytes):
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "wb") as f:
        f.write(data_bytes)
    os.replace(tmp, path)


def load_secret():
    try:
        return open(SECRET_FILE, "r").read().strip()
    except FileNotFoundError:
        key = secrets.token_urlsafe(24)
        atomic_write(SECRET_FILE, key.encode())
        os.chmod(SECRET_FILE, 0o600)
        sys.stderr.write(f"[aibridge] shared key generated at {SECRET_FILE}: {key}\n")
        return key


def load_keys():
    """Map {key: label} of all valid keys. The legacy key from secret.key
    keeps the label "sesame" (the one using it since day one). New keys
    (e.g. "chatgpt") are stored in keys.json and auto-generated the first
    time a requested label is missing -- same auto-generation logic as
    load_secret(), just extended to support more than one identity on the
    same pipeline, so we can *track* (not isolate yet) who sends each
    request."""
    keys = {load_secret(): "sesame"}
    try:
        extra = json.load(open(KEYS_FILE))
    except (FileNotFoundError, json.JSONDecodeError):
        extra = {}
    keys.update(extra)
    return keys


def ensure_key_for_label(keys, label):
    if label in keys.values():
        return keys
    try:
        extra = json.load(open(KEYS_FILE))
    except (FileNotFoundError, json.JSONDecodeError):
        extra = {}
    new_key = secrets.token_urlsafe(24)
    extra[new_key] = label
    atomic_write(KEYS_FILE, json.dumps(extra, ensure_ascii=False, indent=2).encode())
    os.chmod(KEYS_FILE, 0o600)
    sys.stderr.write(f"[aibridge] new key generated for '{label}' at {KEYS_FILE}: {new_key}\n")
    keys[new_key] = label
    return keys


def read_credits():
    try:
        return json.load(open(CREDIT_FILE))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def update_credit(provider, pct):
    if pct is None:
        return read_credits()
    try:
        pct = int(float(pct))
    except (TypeError, ValueError):
        return read_credits()
    with _credit_lock:
        credits = read_credits()
        credits[provider] = {"pct": pct, "updated_at": _now_iso()}
        atomic_write(CREDIT_FILE, json.dumps(credits, ensure_ascii=False, indent=2).encode())
        return credits


def queue_file(provider, token, in_progress=False):
    d = INPROGRESS_DIR if in_progress else QUEUE_DIR
    return os.path.join(d, f"{provider}__{token}.json")


def find_in_progress(token):
    matches = glob.glob(os.path.join(INPROGRESS_DIR, f"*__{token}.json"))
    return matches[0] if matches else None


def token_is_known(token):
    """True if the token corresponds to a real request that actually went
    through /ask (it's in the queue, being processed, or already has a
    result). Lets us distinguish "genuinely pending" from a token that was
    never created (made up / lost on the asker's side) -- see the
    invalid_token status in /result."""
    if find_in_progress(token):
        return True
    if glob.glob(os.path.join(QUEUE_DIR, f"*__{token}.json")):
        return True
    return False


def result_file(token):
    return os.path.join(RESULTS_DIR, f"{token}.md")


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    KEYS = {}  # {key: label}, set in __main__

    def _send(self, code, body=b"", ctype="application/json", extra_headers=None):
        if isinstance(body, (dict, list)):
            # ensure_ascii=True (default): escapes unicode as \uXXXX instead
            # of raw UTF-8 -- more compatible with HTTP/JSON clients on the
            # consuming side that are less tolerant.
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # New connection per request: avoids any keep-alive ambiguity with a
        # simple HTTP client that doesn't handle it well.
        self.send_header("Connection", "close")
        self.close_connection = True
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _params(self):
        qs = urlsplit(self.path).query
        raw = parse_qs(qs, keep_blank_values=True)
        return {k: unquote(v[0]) for k, v in raw.items()}

    def _key_from_request(self, params):
        # ChatGPT Actions compatibility: its auth UI expects the API key in
        # the Authorization header (Bearer), not in the query string. Both
        # forms are accepted, without breaking the existing ?key= flow
        # (sesame, curl).
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return params.get("key")

    def _authorized(self, params):
        return self._key_from_request(params) in self.KEYS

    def _caller(self, params):
        return self.KEYS.get(self._key_from_request(params), "unknown")

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)

        if path == "/healthz":
            return self._send(200, {"ok": True, **port_hint()}, "application/json")

        params = self._params()

        m = RESULT_PATH_RE.match(path)
        if m:
            if not self._authorized(params):
                return self._send(403, {"error": "forbidden"})
            token, ext = m.group(1), m.group(2)
            rf = result_file(token)
            done = os.path.exists(rf)
            body_text = open(rf, "r", encoding="utf-8").read() if done else ""
            # status: "done" (answer ready) / "pending" (real token, queued
            # or in progress) / "invalid_token" (never created via /ask --
            # see the phantom-token gotcha in README.md).
            if done:
                status = "done"
            elif token_is_known(token):
                status = "pending"
            else:
                status = "invalid_token"
            if ext == "json":
                # always 200: some clients treat any non-200 as a hard error.
                return self._send(200, {"status": status, "result": body_text or None, **port_hint()},
                                   RESULT_CTYPE["json"])
            if ext == "html":
                shown = body_text if done else f"{status}..."
                html = f"<!doctype html><meta charset=utf-8><pre>{shown}</pre>"
                return self._send(200, html, RESULT_CTYPE["html"])
            # md / txt: original semantics (202 while not ready), but 404 if
            # the token never existed at all (instead of staying pending
            # forever).
            if done:
                return self._send(200, body_text, RESULT_CTYPE[ext])
            if status == "invalid_token":
                return self._send(404, "invalid_token\n", RESULT_CTYPE[ext])
            return self._send(202, "pending\n", RESULT_CTYPE[ext])

        if not self._authorized(params):
            return self._send(403, {"error": "forbidden"})

        if path == "/ask":
            return self._do_ask(params)
        if path == "/next":
            return self._do_next(params)
        if path == "/deposit":
            return self._do_deposit(params)
        if path == "/credits":
            return self._send(200, {"credits": read_credits(), **port_hint()})
        if path == "/credit":
            return self._do_credit(params)

        return self._send(404, {"error": "not found"})

    def _do_credit(self, params):
        provider = params.get("provider", "")
        if not PROVIDER_RE.match(provider or "") or "pct" not in params:
            return self._send(400, {"error": "missing 'provider' or 'pct'"})
        credits = update_credit(provider, params.get("pct"))
        return self._send(200, {"credits": credits, **port_hint()})

    def _do_ask(self, params):
        text = params.get("text", "")
        provider = params.get("provider", "")
        if not text or not PROVIDER_RE.match(provider or ""):
            return self._send(400, {"error": "missing 'text' or invalid 'provider'"})
        token = secrets.token_urlsafe(9)
        source = self._caller(params)
        job = {
            "token": token,
            "text": text,
            "model": params.get("model", ""),
            "effort": params.get("effort", ""),
            "provider": provider,
            "source": source,  # who asked (identified by which key was used), for tracking
            "ts": _now_iso(),
        }
        atomic_write(queue_file(provider, token), json.dumps(job, ensure_ascii=False).encode())
        sys.stderr.write(f"[aibridge] /ask from '{source}' -> provider={provider} token={token}\n")
        credits = update_credit(provider, params.get("credit_pct")) if "credit_pct" in params else read_credits()
        return self._send(200, {
            "token": token,
            # .json (not .md): always 200, real status inside the body --
            # .md/.txt still work for manual curl/debug, but are no longer
            # what's offered by default to consumers.
            "result_url": f"{PUBLIC_BASE_URL}/result/{token}.json",
            "credits": credits,
            **port_hint(),
        })

    def _do_next(self, params):
        provider = params.get("provider", "")
        if not PROVIDER_RE.match(provider or ""):
            return self._send(400, {"error": "invalid 'provider'"})
        candidates = sorted(
            glob.glob(os.path.join(QUEUE_DIR, f"{provider}__*.json")),
            key=lambda p: os.path.getmtime(p),
        )
        for src in candidates:
            fname = os.path.basename(src)
            dst = os.path.join(INPROGRESS_DIR, fname)
            try:
                os.rename(src, dst)  # atomic: if another poller already took it, this fails and we keep looking
            except FileNotFoundError:
                continue
            job = json.load(open(dst))
            return self._send(200, {
                "token": job["token"],
                "text": job["text"],
                "model": job.get("model", ""),
                "effort": job.get("effort", ""),
            })
        return self._send(204)

    def _do_deposit(self, params):
        token = params.get("token", "")
        body = params.get("body", "")
        if not TOKEN_RE.match(token or ""):
            return self._send(400, {"error": "invalid 'token'"})
        src = find_in_progress(token)
        provider = None
        if src:
            try:
                provider = json.load(open(src)).get("provider")
            except (OSError, json.JSONDecodeError):
                pass
        atomic_write(result_file(token), body.encode())
        if src:
            try:
                os.remove(src)
            except OSError:
                pass
        credits = read_credits()
        if provider and "credit_pct" in params:
            credits = update_credit(provider, params.get("credit_pct"))
        return self._send(200, {"ok": True, "credits": credits})

    def log_message(self, *a):
        pass


def main():
    for d in (QUEUE_DIR, INPROGRESS_DIR, RESULTS_DIR):
        os.makedirs(d, exist_ok=True)
    keys = load_keys()
    keys = ensure_key_for_label(keys, "chatgpt")
    H.KEYS = keys
    srv = ThreadingHTTPServer((BIND, PORT), H)
    sys.stderr.write(f"aibridge on {BIND}:{PORT} (base={BASE_DIR}, public={PUBLIC_BASE_URL})\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
