#!/usr/bin/env python3
"""Verdict on how a stack's persisted Hermes .env changed across a recreate (used by ops/recreate_hermes.sh).

Input (environment, never printed): BEFORE and AFTER are {variable: sha256 of its value} of the persisted .env before and
after the recreate; CENV is the container's Config.Env as JSON (the list `docker inspect -f '{{json .Config.Env}}'` prints).
Output: one line, "OK <names>" or "BAD <names>", with the names of the changed variables (names only, never values).

A changed variable is accepted when:
  - start_hermes.sh copied it from the stack's compose .env: its new value is the container variable it comes from
    (a key the operator replaced), or
  - it is a provider key that was EMPTY before, is gone after, and the container has no value for it: start_hermes.sh
    stopped writing empty provider key lines and drops the ones an earlier boot left (5c92ac5); the first boot on that image
    removed them on every stack and the old check reported FAIL although no key was lost.
Anything else (a key that had a value and disappeared, a value that does not match the container) is BAD.
"""
import hashlib
import json
import os
import sys

# persisted .env variable -> the container variable start_hermes.sh copies it from
SRC = {"API_SERVER_KEY": "HERMES_API_KEY", "GOOGLE_API_KEY": "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN": "TELEGRAM_BOT_TOKEN",
       "TELEGRAM_ALLOWED_USERS": "TELEGRAM_ALLOWED_USERS", "GROQ_API_KEY": "GROQ_API_KEY",
       "OPENROUTER_API_KEY": "OPENROUTER_API_KEY", "HF_TOKEN": "HF_TOKEN"}
# provider keys start_hermes.sh never writes empty (same set as KEYS in start_hermes.sh's managed .env writer)
DROPPED_WHEN_EMPTY = {"GOOGLE_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "HF_TOKEN"}
EMPTY = hashlib.sha256(b"").hexdigest()


def sha(v):
    return hashlib.sha256(v.encode()).hexdigest()


def verdict(before, after, cenv):
    env = dict(x.split("=", 1) for x in cenv if "=" in x)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))

    def accepted(k):
        if k not in SRC:
            return False
        value = env.get(SRC[k], "")
        if k in after:
            return after[k] == sha(value)
        return k in DROPPED_WHEN_EMPTY and before.get(k) == EMPTY and not value

    ok = bool(changed) and all(accepted(k) for k in changed)
    return ("OK " if ok else "BAD ") + " ".join(changed)


if __name__ == "__main__":
    print(verdict(json.loads(os.environ["BEFORE"]), json.loads(os.environ["AFTER"]), json.loads(os.environ["CENV"])))
    sys.exit(0)
