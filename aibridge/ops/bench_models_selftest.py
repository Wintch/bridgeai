#!/usr/bin/env python3
"""Selftest for ops/bench_models.py (offline: `call` is replaced by canned answers, nothing is sent anywhere).
Covers what changed on 2026-11-03: the Cloudflare provider (account id inside the URL, validated) and --quick.
Run: python3 ops/bench_models_selftest.py"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bm", os.path.join(HERE, "bench_models.py"))
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def exits(fn):
    try:
        fn()
    except SystemExit as e:
        return str(e)
    return None


ACC = "0123456789abcdef0123456789abcdef"
os.environ.pop("CLOUDFLARE_ACCOUNT_ID", None)
check("cloudflare is a provider and uses CLOUDFLARE_API_TOKEN", bm.PROV["cloudflare"][1] == "CLOUDFLARE_API_TOKEN")
check("no account id: a clear error", "32-character" in (exits(lambda: bm.base_of("cloudflare")) or ""))
for bad in ("", " ", "36befcaccc03", ACC + "0", '"' + ACC, "g" * 32):
    os.environ["CLOUDFLARE_ACCOUNT_ID"] = bad
    check(f"a malformed account id is refused: {bad!r}", exits(lambda: bm.base_of("cloudflare")) is not None)
os.environ["CLOUDFLARE_ACCOUNT_ID"] = " " + ACC + " "
check("a good id (stray spaces trimmed) builds the OpenAI-compatible URL",
      bm.base_of("cloudflare") == f"https://api.cloudflare.com/client/v4/accounts/{ACC}/ai/v1")
check("other providers keep their fixed base", bm.base_of("nvidia") == "https://integrate.api.nvidia.com/v1")
check("--discover is refused for cloudflare (no /models list)", "no /models" in (exits(lambda: bm.discover("cloudflare")) or ""))

calls = []


def fake_call(prov, body, timeout=60):
    calls.append(body)
    if body.get("tools") is bm.TOOLS:
        msg = {"tool_calls": [{"function": {"name": "get_weather", "arguments": '{"city": "Madrid"}'}}]}
    elif body.get("tools") is bm.OFFERED:
        msg = {"tool_calls": [{"function": {"name": "open_url", "arguments": "{}"}}]}
    elif "pandas" in str(body.get("messages")) or "fastqueue" in str(body.get("messages")) or "browser_helpers" in str(body.get("messages")):
        msg = {"content": "That function does not exist."}
    else:
        msg = {"content": "ok"}
    return {"choices": [{"message": msg}], "usage": {"completion_tokens": 20}}, 1.0, None


bm.call = fake_call
bm.QUICK = True
calls.clear()
r = bm.run("cloudflare", "@cf/x/y")
check("--quick makes 3 calls (short, tool, invented tool)", len(calls) == 3)
check("--quick still judges the tool call and the invented-tool test", r["tools"] == "ok" and r["inventa"] == "no")
check("--quick leaves the skipped columns as '-'", r["long_s"] == "-" and r["tok_s"] == "-" and r["fakeapi_inventadas"] == "-")
bm.QUICK = False
calls.clear()
r = bm.run("cloudflare", "@cf/x/y")
check("the full run makes 7 calls and fills every column", len(calls) == 7 and r["fakeapi_inventadas"] == "0/3" and r["tok_s"] != "-")

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all bench_models checks passed")
