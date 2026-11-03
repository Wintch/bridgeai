#!/usr/bin/env python3
"""Offline test of ops/stack_keys.py: no Docker, no network. Run: python3 ops/stack_keys_selftest.py"""
import contextlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stack_keys as sk  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


class R:
    def __init__(self, out="", rc=0):
        self.stdout, self.returncode = out, rc


GEM = "AIza" + "x" * 35
GROQ = "gsk_" + "y" * 40
OR = "sk-or-v1-" + "z" * 40


def go(args, key, awake=True, answer=None):
    calls = []
    out, err = io.StringIO(), io.StringIO()

    def fake_run(cmd, **k):
        calls.append((cmd, k.get("input")))
        return R(json.dumps(answer or {"ok": True, "msg": "Clave válida y guardada (…xxxx)."}) + "\n")

    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = sk.main(args, stdin=io.StringIO(key + "\n"), run=fake_run, running=lambda n: awake)
    return rc, out.getvalue() + err.getvalue(), calls


rc, out, calls = go(["hx", "gemini"], GEM)
check("gemini: ok, key only on stdin (never in argv), activate on by default",
      rc == 0 and calls and GEM not in " ".join(calls[0][0]) and calls[0][1] == GEM + "\n" and calls[0][0][-4:] == ["llm", "gemini", "1", ""], (rc, out, calls))
rc, out, calls = go(["hx", "openrouter", "--no-activate"], OR)
check("openrouter with --no-activate passes 0", rc == 0 and calls[0][0][-2] == "0", (rc, out))
rc, out, calls = go(["hx", "gemini", "--model", "gemini-flash-lite-latest"], GEM)
check("--model is passed to the container (and the key still is not in argv)",
      rc == 0 and calls[0][0][-1] == "gemini-flash-lite-latest" and GEM not in " ".join(calls[0][0]), (rc, out, calls))
rc, out, calls = go(["hx", "gemini", "--model"], GEM)
check("--model without a value is refused", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "groq", "--model", "x-model"], GROQ)
check("--model on a service key (groq) is refused", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "gemini", "--model", "bad model;rm"], GEM)
check("a model id with odd characters is refused", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "groq"], GROQ)
check("groq goes the service way", rc == 0 and calls[0][0][-4] == "service" and calls[0][0][-3] == "groq", (rc, out, calls))
rc, out, calls = go(["hx", "gemini"], "AQ." + "w" * 40)
check("a new-format Gemini key (AQ.) is accepted", rc == 0 and calls, (rc, out))
rc, out, calls = go(["hx", "gemini"], "not a key at all")
check("a wrong shape is refused before anything runs", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "gemini"], GROQ)
check("a groq key given as gemini is refused", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "gemini"], GEM, awake=False)
check("an asleep stack is not touched and the way to wake it is said", rc == 3 and not calls and "asleep" in out, out)
rc, out, calls = go(["hx", "mapbox"], GEM)
check("an unknown type is refused", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "gemini"], GEM, answer={"ok": False, "msg": "Google Gemini rechazó la clave (HTTP 400) " + GEM})
check("a refusal exits 1 and the key is scrubbed from the text", rc == 1 and GEM not in out and "FAIL" in out, out)
rc, out, calls = go(["hx", "gemini", "--bogus"], GEM)
check("an unknown flag is refused", rc == 2, out)
print("\nall passed" if not fails else f"\n{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
