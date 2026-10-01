#!/usr/bin/env python3
"""
responder_test -- test poller for aibridge. Answers any pending request with
a generic phrase (different every time, chosen at random), just to test the
timing of the ask -> next -> deposit -> result loop without depending on a
human/AI answering by hand every time. NOT a real agent: it doesn't
understand the request, it only confirms the ping-pong works.
"""
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get("AIBRIDGE_INTERNAL_URL", "http://aibridge:8097")
KEY = os.environ["AIBRIDGE_KEY"]
PROVIDERS = os.environ.get("AIBRIDGE_PROVIDERS", "grok,claude,antigravity,sesame").split(",")
POLL_SECONDS = float(os.environ.get("AIBRIDGE_POLL_SECONDS", "10"))

REPLIES = [
    "Got it, everything working on this end.",
    "Ping-pong confirmed, carrying on.",
    "Here, send the next one.",
    "Came through fine, the bridge is responding fast.",
    "All good, testing the loop.",
    "Copy that, waiting for the next one.",
    "Running without issues, go ahead.",
    "Test received and answered.",
]


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.read()


def tick():
    for provider in PROVIDERS:
        provider = provider.strip()
        if not provider:
            continue
        try:
            status, body = get(f"{BASE}/next?key={KEY}&provider={urllib.parse.quote(provider)}")
        except Exception as e:
            sys.stderr.write(f"[responder_test] error querying {provider}: {e}\n")
            continue
        if status != 200 or not body:
            continue
        job = json.loads(body)
        reply = random.choice(REPLIES)
        try:
            get(f"{BASE}/deposit?key={KEY}&token={job['token']}&body={urllib.parse.quote(reply)}")
            sys.stderr.write(f"[responder_test] answered {provider}/{job['token']}: {job.get('text','')!r} -> {reply!r}\n")
        except Exception as e:
            sys.stderr.write(f"[responder_test] error depositing {job.get('token')}: {e}\n")


if __name__ == "__main__":
    sys.stderr.write(f"[responder_test] starting, providers={PROVIDERS}, poll={POLL_SECONDS}s\n")
    while True:
        tick()
        time.sleep(POLL_SECONDS)
