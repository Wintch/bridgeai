#!/usr/bin/env python3
"""Selftest: every provider has a privacy class (A, B or C) in ops/lib/providers.py, so adding one forces the decision.
Run: python3 ops/provider_privacy_selftest.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import providers  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


check("every provider in PROVIDERS has a privacy class", all(p in providers.PRIVACY for p in providers.PROVIDERS))
check("the classes are A, B or C", set(providers.PRIVACY.values()) <= {"A", "B", "C"})
check("no class for a provider that does not exist, except Cloudflare (not wired into the monitors yet)",
      set(providers.PRIVACY) - set(providers.PROVIDERS) <= {"cloudflare"})
check("the decisions of 2026-11-03: Token Harbor and free Gemini and OpenRouter :free are C",
      all(providers.PRIVACY[p] == "C" for p in ("tokenharbor", "gemini", "openrouter")))
check("NVIDIA is B (the operator accepted B)", providers.PRIVACY["nvidia"] == "B")
check("Cloudflare is A", providers.PRIVACY["cloudflare"] == "A")
print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all provider_privacy checks passed")
