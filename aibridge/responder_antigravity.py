#!/usr/bin/env python3
"""
responder_antigravity -- poller that answers provider=antigravity requests
with real Antigravity (Google) (agy -p), WITHOUT
--dangerously-skip-permissions: any tool-use attempt that needs approval
gets blocked (no TTY to approve it) -> in practice it answers with text
only. Same pattern as responder_claude.js, in Python (agy is a native
binary, no need for Node).
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get("AIBRIDGE_INTERNAL_URL", "http://aibridge:8097")
KEY = os.environ["AIBRIDGE_KEY"]
PROVIDER = os.environ.get("AIBRIDGE_PROVIDER", "antigravity")
POLL_SECONDS = float(os.environ.get("AIBRIDGE_POLL_SECONDS", "10"))
BIN = "agy"


def get(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return r.status, r.read()


def ask_agent(job):
    args = [BIN, "-p", job["text"], "--output-format", "json"]
    if job.get("model"):
        args += ["--model", job["model"]]
    if job.get("effort"):
        args += ["--effort", job["effort"]]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            args,
            cwd="/workdir", timeout=120, capture_output=True, text=True,
        )
    except Exception as e:
        return f"(error querying {BIN}: {e})"
    elapsed = time.monotonic() - started
    stdout = (proc.stdout or "").strip()
    if proc.returncode != 0 and not stdout:
        return f"(error querying {BIN}: {(proc.stderr or '').strip()[:300]})"

    answer = None
    usage = {}
    try:
        parsed = json.loads(stdout)
        if parsed.get("status") == "ERROR" and parsed.get("error"):
            return f"({BIN} error: {parsed['error'][:500]})"
        for key in ("response", "result", "output", "text", "message"):
            if isinstance(parsed.get(key), str) and parsed.get(key).strip():
                answer = parsed[key].strip()
                break
        usage = parsed.get("usage") or {}
    except (json.JSONDecodeError, AttributeError):
        pass

    if answer is None:
        answer = stdout or "(empty response)"

    in_tok = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    out_tok = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    cache_tok = usage.get("cache_read_tokens") or usage.get("cache_read_input_tokens") or 0
    total = in_tok + out_tok + cache_tok
    footer = f"\n\n---\n_processed in {elapsed:.1f}s"
    if total:
        footer += f" · tokens: {in_tok} in / {out_tok} out (+{cache_tok} cache) = {total} total_"
    else:
        footer += "_"
    return answer + footer


def tick():
    try:
        status, body = get(f"{BASE}/next?key={KEY}&provider={PROVIDER}")
    except Exception as e:
        sys.stderr.write(f"[responder_antigravity] error querying next: {e}\n")
        return
    if status != 200 or not body:
        return
    job = json.loads(body)
    reply = ask_agent(job)
    try:
        get(f"{BASE}/deposit?key={KEY}&token={job['token']}&body={urllib.parse.quote(reply)}")
        sys.stderr.write(f"[responder_antigravity] answered {job['token']}: {job.get('text','')!r}\n")
    except Exception as e:
        sys.stderr.write(f"[responder_antigravity] error depositing {job.get('token')}: {e}\n")


if __name__ == "__main__":
    sys.stderr.write(f"[responder_antigravity] starting, provider={PROVIDER}, poll={POLL_SECONDS}s\n")
    while True:
        tick()
        time.sleep(POLL_SECONDS)
