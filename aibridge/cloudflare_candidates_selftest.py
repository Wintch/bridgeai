#!/usr/bin/env python3
"""Selftest: router.py adds its Cloudflare explore candidates only where CLOUDFLARE_ACCOUNT_ID is a valid 32-hex id, never in
the default CLOUD order, and treats a Cloudflare 429 as the account's shared allowance. Each case imports the router in a
fresh process with its own environment. Run: python3 cloudflare_candidates_selftest.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def load(acc):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLOUDFLARE_")}
    env["GATEWAY_LOG"] = os.path.join(tempfile.gettempdir(), "cf-selftest.jsonl")
    if acc is not None:
        env["CLOUDFLARE_ACCOUNT_ID"] = acc
    code = ("import router as r, json; print(json.dumps({'cand': [c for c in r.CANDIDATES], 'cloud': [c[0] for c in r.CLOUD], "
            "'shared': sorted(r.SHARED_ALLOWANCE)}))")
    p = subprocess.run([sys.executable, "-c", code], cwd=HERE, env=env, capture_output=True, text=True, timeout=60)
    return json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else None


ACC = "0123456789abcdef0123456789abcdef"
for label, acc in (("no account id", None), ("empty", ""), ("too short", "36befcaccc03"), ("with a quote", '"' + ACC), ("33 characters", ACC + "0")):
    d = load(acc)
    check(f"{label}: the router loads and has no Cloudflare candidate", d is not None and not [c for c in d["cand"] if "Cloudflare" in c[0]])
d = load(ACC)
cf = [c for c in (d or {"cand": []})["cand"] if "Cloudflare" in c[0]]
check("a valid id adds the three candidates", len(cf) == 3)
check("each uses the account's OpenAI-compatible URL and the token variable",
      all(c[1] == f"https://api.cloudflare.com/client/v4/accounts/{ACC}/ai/v1" and c[3] == "CLOUDFLARE_API_TOKEN" for c in cf))
check("the models are the three that passed the bench", sorted(c[2] for c in cf) == ["@cf/google/gemma-4-26b-a4b-it", "@cf/openai/gpt-oss-120b", "@cf/zai-org/glm-4.7-flash"])
check("none is in the default best-first CLOUD order", d is not None and not [n for n in d["cloud"] if "Cloudflare" in n])
check("a 429 from Cloudflare cools every model of the account", d is not None and "api.cloudflare.com" in d["shared"])
base = load(None)
check("without Cloudflare the candidates are exactly CLOUD plus the three NVIDIA/Token Harbor extras",
      base is not None and len(base["cand"]) == len(base["cloud"]) + 3)
# Cloudflare answers 256 tokens at most unless the request says otherwise: the router says so for it, and only for it
code = ("import router as r, json; u='https://api.cloudflare.com/client/v4/accounts/x/ai/v1'; "
        "print(json.dumps([r.with_output_cap(u, {'messages': []}), r.with_output_cap(u, {'max_tokens': 99}), "
        "r.with_output_cap(u, {'max_completion_tokens': 77}), r.with_output_cap(u, {'max_tokens': None}), "
        "r.with_output_cap('https://integrate.api.nvidia.com/v1', {'messages': []}), r.CF_DEFAULT_MAX_TOKENS]))")
env = dict(os.environ, GATEWAY_LOG=os.path.join(tempfile.gettempdir(), "cf-selftest.jsonl"))
p = subprocess.run([sys.executable, "-c", code], cwd=HERE, env=env, capture_output=True, text=True, timeout=60)
a = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else [None] * 6
check("a Cloudflare call with no length gets the router's cap", a[0] == {"messages": [], "max_tokens": a[5]} and a[5] >= 4096)
check("a length the request names is never overridden", a[1] == {"max_tokens": 99} and a[2] == {"max_completion_tokens": 77})
check("a null max_tokens counts as none", a[3] == {"max_tokens": a[5]})
check("another provider's request is left alone", a[4] == {"messages": []})

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all cloudflare_candidates checks passed")
