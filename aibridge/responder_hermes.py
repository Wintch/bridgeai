#!/usr/bin/env python3
"""
responder_hermes -- aibridge poller that handles provider=hermes by
forwarding the request text to a Hermes Agent instance running in the same
container (OpenAI-compatible API, POST /v1/chat/completions), and depositing
the real answer back into aibridge.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("AIBRIDGE_INTERNAL_URL", "http://aibridge:8097")
KEY = os.environ["AIBRIDGE_KEY"]
PROVIDER = os.environ.get("AIBRIDGE_PROVIDER", "hermes")
POLL_SECONDS = float(os.environ.get("AIBRIDGE_POLL_SECONDS", "10"))

HERMES_API_URL = os.environ.get("HERMES_API_URL", "http://127.0.0.1:8642/v1/chat/completions")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")
HERMES_REQUEST_TIMEOUT = float(os.environ.get("HERMES_REQUEST_TIMEOUT", "120"))


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.read()


def ask_hermes(job):
    # Hermes Agent picks its own model/provider internally (configured once
    # via `hermes setup --portal`) -- unlike claude/antigravity, we do NOT
    # pass job['model']/job['effort'] through.
    payload = json.dumps({
        "model": "hermes-agent",
        "messages": [{"role": "user", "content": job["text"]}],
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        HERMES_API_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {HERMES_API_KEY}",
        },
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=HERMES_REQUEST_TIMEOUT) as r:
            status = r.status
            body = r.read()
    except urllib.error.HTTPError as e:
        return f"(hermes error: HTTP {e.code} {e.reason})"
    except urllib.error.URLError as e:
        return f"(hermes error: {e.reason})"
    except Exception as e:
        return f"(error querying hermes: {e})"
    elapsed = time.monotonic() - started

    if status != 200:
        return f"(hermes error: HTTP {status})"

    try:
        parsed = json.loads(body)
        answer = parsed["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        return f"(hermes error: unexpected response, {e})"

    usage = parsed.get("usage") or {}
    in_tok = usage.get("prompt_tokens") or 0
    out_tok = usage.get("completion_tokens") or 0
    total = usage.get("total_tokens") or (in_tok + out_tok)

    footer = f"\n\n---\n_processed in {elapsed:.1f}s"
    if total:
        footer += f" · tokens: {in_tok} in / {out_tok} out = {total} total_"
    else:
        footer += "_"
    return answer + footer


def tick():
    try:
        status, body = get(f"{BASE}/next?key={KEY}&provider={urllib.parse.quote(PROVIDER)}")
    except Exception as e:
        sys.stderr.write(f"[responder_hermes] error querying {PROVIDER}: {e}\n")
        return
    if status != 200 or not body:
        return
    job = json.loads(body)
    reply = ask_hermes(job)
    try:
        get(f"{BASE}/deposit?key={KEY}&token={job['token']}&body={urllib.parse.quote(reply)}")
        sys.stderr.write(f"[responder_hermes] answered {job['token']}: {job.get('text','')!r} -> {reply[:120]!r}\n")
    except Exception as e:
        sys.stderr.write(f"[responder_hermes] error depositing {job.get('token')}: {e}\n")


if __name__ == "__main__":
    sys.stderr.write(f"[responder_hermes] starting, provider={PROVIDER}, poll={POLL_SECONDS}s, hermes_api={HERMES_API_URL}\n")
    while True:
        tick()
        time.sleep(POLL_SECONDS)
