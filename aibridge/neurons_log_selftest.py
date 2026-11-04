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

m = r.Meter()
m.chunk({"choices": [{"delta": {"content": "<|channel|>analysis: need to check the status<|end|><|start|>assistant to=functions.terminal<|call|>"}}]})
check("gpt-oss's raw harmony markers in the reply count as a leak", m.record()["leak"] == 1)
m = r.Meter()
m.chunk({"choices": [{"delta": {"content": "Los subtítulos ya están en /workdir/descargas."}}]})
check("a normal reply is not a leak", m.record()["leak"] == 0)

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

# the observed cap, day by day, and conversations that changed model (the 2026-11-04 session on Cloudflare, then nemotron)
import importlib.util
spec = importlib.util.spec_from_file_location("ms", os.path.join(HERE, "ops", "model_scores.py"))
ms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ms)
T = 1_793_800_000    # 2026-11-04 UTC
day = time.strftime("%Y-%m-%d", time.gmtime(T))
log = [{"ts": T + i, "model": "Cloudflare gpt-oss-120b", "result": "ok", "neurons": 1000.0, "session": "a"} for i in range(3)]
log += [{"ts": T + 10, "model": "Cloudflare gpt-oss-120b", "result": "HTTP 429", "session": "a"},
        {"ts": T + 11, "model": "Cloudflare gpt-oss-120b", "result": "HTTP 429", "session": "a"},
        {"ts": T + 12, "model": "NVIDIA nemotron-3-ultra", "result": "ok", "session": "a"},
        {"ts": T + 20, "model": "NVIDIA nemotron-3-ultra", "result": "ok", "session": "b"},
        {"ts": T + 21, "model": "NVIDIA nemotron-3-ultra", "result": "ok", "session": "c", "aux": True},
        {"ts": T + 22, "model": "Cloudflare gpt-oss-120b", "result": "ok", "neurons": 500.0, "session": "c", "aux": True},
        {"ts": T + 30, "vote": 1, "feedback": True, "model": "Cloudflare gpt-oss-120b"}]
cf = ms.cloudflare_days(log)
d = cf.get(day, {})
check("the day is keyed by its UTC date and counts calls, answers and quota errors", d.get("calls") == 6 and d.get("ok") == 4 and d.get("quota") == 2)
check("the Neurons spent before the day's FIRST 429 are the observed cap", d.get("before_429") == 3000)
check("Neurons per answered call and how many calls fit in 10,000", d.get("neurons") == 3500 and d.get("per_call") == 875 and d.get("fits") == 11)
check("only Cloudflare models and no votes are counted", sum(x["calls"] for x in cf.values()) == 6)
check("a day with no 429 has no observed cap", ms.cloudflare_days([x for x in log if "429" not in str(x.get("result"))])[day]["before_429"] is None)
check("conversations that changed model are counted once, helper calls and votes ignored", ms.model_switches(log) == (2, 1))
empty = subprocess.run([sys.executable, os.path.join(HERE, "ops", "model_scores.py"), "--hours", "24"], cwd=tempfile.mkdtemp(),
                       capture_output=True, text=True, timeout=60)
check("model_scores runs without any log", empty.returncode == 0 and "Traceback" not in empty.stderr)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all neurons_log checks passed")
