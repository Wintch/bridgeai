#!/usr/bin/env python3
"""Selftest: the router's evaluation log carries the Neurons a Cloudflare call spent, and ops/model_scores.py reports them
against the free plan's 10,000 a day. Offline. Run: python3 neurons_log_selftest.py"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["GATEWAY_LOG"] = os.path.join(tempfile.gettempdir(), "neurons-selftest.jsonl")
sys.path.insert(0, HERE)
import router as r  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def chunk(content=None, usage=None, finish=None):
    d = {"choices": [{"index": 0, "delta": ({"content": content} if content is not None else {}), "finish_reason": finish}]}
    if usage is not None:
        d["usage"] = usage
    return b"data: " + json.dumps(d).encode()


# the shape seen on 2026-11-03 from gpt-oss-120b: usage on EVERY chunk, neurons added chunk by chunk
m = r.Meter()
for ln in (chunk("", {"prompt_tokens": 130, "completion_tokens": 0, "neurons": 4.1363396644592285}),
           chunk("hola", {"prompt_tokens": 0, "completion_tokens": 4, "neurons": 0.27272719144821167}),
           chunk(" mundo", {"prompt_tokens": 0, "completion_tokens": 4, "neurons": 0.27272719144821167}, "stop")):
    m.line(ln)
rec = m.record()
check("a stream's neurons are added up", abs(rec["neurons"] - 4.6818) < 0.01)
m = r.Meter()
m.chunk({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"completion_tokens": 3, "neurons": 7.5}})
check("a whole (non-streamed) answer keeps its total", m.record()["neurons"] == 7.5)
m = r.Meter()
m.chunk({"choices": [{"message": {"content": "ok"}}], "usage": {"completion_tokens": 3, "total_tokens": 20}})
check("a provider that reports no neurons leaves the key out of the log line", "neurons" not in m.record())
m = r.Meter()
m.chunk({"usage": {"neurons": True}})
m.chunk({"usage": {"neurons": "5"}})
check("a boolean or a string is not counted as neurons", "neurons" not in m.record())
check("the other fields of the line are untouched", {"ttfb", "s", "finish", "tools", "bad_args", "out", "tok", "odd", "leak"} <= set(rec))

# model_scores.py over a temporary log
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "user1-workdir"))
now = time.time()
rows = [{"ts": now - 60 * i, "model": "Cloudflare gpt-oss-120b", "result": "ok", "s": 2.0, "ttfb": 0.5, "out": 100, "neurons": 20.0} for i in range(5)]
rows += [{"ts": now - 60 * i, "model": "NVIDIA nemotron-3.5-super", "result": "ok", "s": 1.5, "ttfb": 0.4, "out": 100} for i in range(5)]
open(os.path.join(d, "user1-workdir", ".model-eval.jsonl"), "w").write("\n".join(json.dumps(x) for x in rows) + "\n")
p = subprocess.run([sys.executable, os.path.join(HERE, "ops", "model_scores.py"), "--hours", "24", "--min-calls", "1"],
                   cwd=d, capture_output=True, text=True, timeout=60)
check("model_scores prints the Cloudflare neurons line", "Neurons (Cloudflare): Cloudflare gpt-oss-120b 100 (20.0 por llamada)" in p.stdout)
check("it compares with the day's 10,000", "de 10000" in p.stdout)
check("a model without neurons is not listed there", "NVIDIA nemotron-3.5-super 0" not in p.stdout)
js = json.loads(subprocess.run([sys.executable, os.path.join(HERE, "ops", "model_scores.py"), "--hours", "24", "--min-calls", "1", "--json"],
                               cwd=d, capture_output=True, text=True, timeout=60).stdout)
check("--json carries the neurons per model", {x["model"]: x["neurons"] for x in js["ranked"]}.get("Cloudflare gpt-oss-120b") == 100.0)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all neurons_log checks passed")
