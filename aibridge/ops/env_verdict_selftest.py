#!/usr/bin/env python3
"""Offline test of ops/env_verdict.py (the .env part of recreate_hermes.sh's before/after check). Fake values only."""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_verdict import verdict  # noqa: E402

fails = 0


def check(name, cond, got=""):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1


h = lambda v: hashlib.sha256(v.encode()).hexdigest()  # noqa: E731
KEEP = {"API_SERVER_KEY": h("test-api-server-0001"), "GROQ_API_KEY": h("test-value-groq-0001")}
CENV = ["HERMES_API_KEY=test-api-server-0001", "GROQ_API_KEY=test-value-groq-0001", "PATH=/usr/bin"]

before = dict(KEEP, GOOGLE_API_KEY=h(""), OPENROUTER_API_KEY=h(""), HF_TOKEN=h(""))
r = verdict(before, dict(KEEP), CENV)
check("empty provider key lines removed by the new boot pass", r == "OK GOOGLE_API_KEY HF_TOKEN OPENROUTER_API_KEY", r)

r = verdict(dict(KEEP, OPENROUTER_API_KEY=h("test-value-or-0001")), dict(KEEP), CENV)
check("a provider key that HAD a value and disappeared fails", r.startswith("BAD ") and "OPENROUTER_API_KEY" in r, r)

r = verdict(dict(KEEP, OPENROUTER_API_KEY=h("")), dict(KEEP), CENV + ["OPENROUTER_API_KEY=test-value-or-0002"])
check("an empty line dropped while the container HAS a value fails (it should have been written)", r.startswith("BAD "), r)

r = verdict(dict(KEEP, TELEGRAM_BOT_TOKEN=h("")), dict(KEEP), CENV)
check("a non-provider variable that disappears fails even if it was empty", r.startswith("BAD "), r)

r = verdict(dict(KEEP), dict(KEEP, GROQ_API_KEY=h("test-value-groq-0002")), ["GROQ_API_KEY=test-value-groq-0002"])
check("a key replaced in the compose .env passes", r == "OK GROQ_API_KEY", r)

r = verdict(dict(KEEP), dict(KEEP, GROQ_API_KEY=h("test-value-groq-0003")), CENV)
check("a new value that does not match the container fails", r.startswith("BAD "), r)

r = verdict(dict(KEEP), dict(KEEP, UNKNOWN_VAR=h("x")), CENV)
check("an unknown variable appearing fails", r.startswith("BAD "), r)

r = verdict(dict(KEEP), dict(KEEP), CENV)
check("nothing changed is not OK (the caller only asks when something changed)", r.startswith("BAD "), r)

r = verdict(dict(KEEP, GOOGLE_API_KEY=h("")), dict(KEEP, GOOGLE_API_KEY=h("test-value-gem-0001")), CENV + ["GEMINI_API_KEY=test-value-gem-0001"])
check("GOOGLE_API_KEY is checked against the container's GEMINI_API_KEY", r == "OK GOOGLE_API_KEY", r)

print("all env_verdict checks passed" if not fails else f"{fails} env_verdict check(s) failed")
sys.exit(1 if fails else 0)
