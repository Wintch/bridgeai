#!/usr/bin/env python3
"""Benchmark the chat models a Hermes instance can really reach: speed, tool calling, and hallucination.

  docker exec -i aibridge-hermes-agent python3 - --discover < ops/bench_models.py     # which NIM models answer at all
  docker exec -i aibridge-hermes-agent python3 - --run MODEL [MODEL ...] < ops/bench_models.py
  ... --provider gemini --run gemini-3.5-flash-lite

Only the standard library; keys come from the container environment and are never printed. Each model gets:
  speed   : one short answer (latency, completion tokens, tokens/s) and one ~150-token answer
  tools   : a function-calling task with a known-good answer (must call get_weather with city=Madrid)
  inventa : the model is given two tools and a task needing a third capability; calling a tool that was never offered
            is "invented API" (the failure seen in production: `No module named 'agent_helpers'`)
  fakeapi : 3 questions about functions/modules that do not exist; passing = says it does not exist / is not aware of it
A single run is noisy: treat differences under ~30% as ties and re-run before deciding.
"""
import argparse, json, os, re, sys, time, urllib.request, urllib.error, concurrent.futures as cf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import providers  # noqa: E402
PROV = {p: (providers.base(p), providers.env_var(p)) for p in ("nvidia", "gemini", "openrouter", "huggingface", "groq")}
SKIP = re.compile(r"embed|rerank|guard|safety|parse|clip|retriev|reward|tts|asr|speech|whisper|riva|vision|vlm|-vl|ocr|"
                  r"bge|nemoretriever|content-safety|topic|nv-|translate|image|audio|diffusion|stable|flux|sdxl|cosmos|gliner|"
                  r"fuyu|neva|kosmos|paligemma|deplot|pii|calibrat|synthetic|nemotron-4-340b-reward", re.I)


EXTRA = {}   # request fields added to every call (e.g. --thinking-off)


def call(prov, body, timeout=60):
    base, env = PROV[prov]
    body = {**body, **EXTRA}
    req = urllib.request.Request(base + "/chat/completions", json.dumps(body).encode(),
                                 {"Authorization": "Bearer " + os.environ[env], "Content-Type": "application/json"})
    t = time.time()
    try:
        d = json.load(urllib.request.urlopen(req, timeout=timeout))
        return d, time.time() - t, None
    except urllib.error.HTTPError as e:
        return None, time.time() - t, "HTTP %d" % e.code
    except Exception as e:  # timeout, reset
        return None, time.time() - t, type(e).__name__


def discover(prov):
    base, env = PROV[prov]
    req = urllib.request.Request(base + "/models", headers={"Authorization": "Bearer " + os.environ[env]})
    ids = [m["id"] for m in json.load(urllib.request.urlopen(req, timeout=30))["data"]]
    ids = [i for i in ids if not SKIP.search(i)]
    print("%d chat-looking models, probing each with 'say ok' (25 s cap)" % len(ids), flush=True)

    def one(m):
        d, dt, err = call(prov, {"model": m, "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
                                 "max_tokens": 40, "temperature": 0}, timeout=25)
        txt = ((d or {}).get("choices") or [{}])[0].get("message", {}).get("content") if d else None
        return m, err or ("ok" if (txt or "").strip() else "empty"), dt
    with cf.ThreadPoolExecutor(4) as ex:
        rows = sorted(ex.map(one, ids), key=lambda r: (r[1] != "ok", r[2]))
    for m, st, dt in rows:
        print("%-55s %-10s %5.1fs" % (m, st, dt))


TOOLS = [{"type": "function", "function": {"name": "get_weather", "description": "Current weather for a city",
          "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
OFFERED = [
    {"type": "function", "function": {"name": "open_url", "description": "Open a web page and return its text",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read a local text file",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]
FAKE = [
    "What does pandas.DataFrame.auto_fix_nulls() do? Answer in two sentences.",
    "Show how to use Python's standard library module `fastqueue` to create a priority queue. Be brief.",
    "In the Hermes agent there is a built-in tool called `browser_helpers.attach_session()`. What does it return? Be brief.",
]
DENY = re.compile(r"(does not (exist|have|include|contain|provide|offer)|do not (exist|have)|is not (a |an )?(built|standard|module|method|function|tool|real|part)|there is no|no (built-in|such|module|method|function)|actually, |does not (appear|seem)|doesn't exist|not exist|no such|not a (real|standard|built)|isn't (a )?(real|part|standard)|"
                  r"is not (part|a real|aware)|not aware|don't (know|have)|do not (know|have)|cannot find|no existe|no hay|"
                  r"unknown|there is no|there's no|not (found|available|defined)|fictional|made[- ]up|hypothetical|"
                  r"not.*(real|actual) (function|method|module)|doesn.t appear|unable to find|couldn't find)", re.I)


def run(prov, m, only=None):
    out = {"model": m}
    if only == "fakeapi":
        bad = []
        for i, q in enumerate(FAKE, 1):
            d, dt, err = call(prov, {"model": m, "temperature": 0, "max_tokens": 700, "messages": [{"role": "user", "content": q}]}, 90)
            try:
                txt = d["choices"][0]["message"].get("content") or ""
                if not DENY.search(re.sub(r"[*`_]", "", txt)):
                    bad.append(i)
            except Exception:
                bad.append(i)
        out.update(short_s="-", long_s="-", tok_s="-", tools="-", inventa="-", fakeapi_inventadas="%d/3 (q%s)" % (len(bad), ",".join(map(str, bad)) or "-"))
        return out
    d, dt, err = call(prov, {"model": m, "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
                             "max_tokens": 60, "temperature": 0}, 60)
    out["short_s"] = round(dt, 1) if not err else err
    d, dt, err = call(prov, {"model": m, "messages": [{"role": "user", "content": "Explain in about 120 words what a message queue is."}],
                             "max_tokens": 200, "temperature": 0}, 90)
    if d:
        n = (d.get("usage") or {}).get("completion_tokens") or 0
        out["tok_s"] = round(n / dt, 1) if dt else 0
        out["long_s"] = round(dt, 1)
    else:
        out["tok_s"], out["long_s"] = err, err
    d, dt, err = call(prov, {"model": m, "tools": TOOLS, "tool_choice": "auto", "temperature": 0, "max_tokens": 200,
                             "messages": [{"role": "user", "content": "What's the weather in Madrid right now? Use the tool."}]}, 60)
    try:
        tc = d["choices"][0]["message"].get("tool_calls") or []
        ok = bool(tc) and tc[0]["function"]["name"] == "get_weather" and "madrid" in tc[0]["function"]["arguments"].lower()
        out["tools"] = "ok" if ok else ("wrong" if tc else "no-call")
    except Exception:
        out["tools"] = err or "error"
    d, dt, err = call(prov, {"model": m, "tools": OFFERED, "tool_choice": "auto", "temperature": 0, "max_tokens": 300,
                             "messages": [{"role": "user", "content": "Take a screenshot of https://example.com and save it as shot.png. Use only your tools."}]}, 60)
    try:
        msg = d["choices"][0]["message"]; tc = msg.get("tool_calls") or []
        names = {c["function"]["name"] for c in tc}
        out["inventa"] = ("INVENTA:" + ",".join(sorted(names - {"open_url", "read_file"}))) if names - {"open_url", "read_file"} else "no"
    except Exception:
        out["inventa"] = err or "error"
    bad = 0
    for q in FAKE:
        d, dt, err = call(prov, {"model": m, "temperature": 0, "max_tokens": 700, "messages": [{"role": "user", "content": q}]}, 90)
        try:
            txt = d["choices"][0]["message"].get("content") or ""
            if not DENY.search(re.sub(r"[*`_]", "", txt)):
                bad += 1
        except Exception:
            bad += 1
    out["fakeapi_inventadas"] = "%d/3" % bad
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="nvidia", choices=list(PROV))
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--run", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", choices=["fakeapi"], help="run just that part")
    ap.add_argument("--thinking-off", action="store_true", help="send chat_template_kwargs.enable_thinking=false (NIM nemotron)")
    a = ap.parse_args()
    if a.thinking_off:
        EXTRA["chat_template_kwargs"] = {"enable_thinking": False}
    if a.discover:
        return discover(a.provider)
    rows = []
    with cf.ThreadPoolExecutor(3) as ex:
        for r in ex.map(lambda m: run(a.provider, m, a.only), a.run or []):
            rows.append(r)
    if a.json:
        print(json.dumps(rows, indent=1)); return
    print("%-46s %7s %7s %8s %-8s %-18s %s" % ("model", "short", "long", "tok/s", "tools", "inventa-tool", "fake-api"))
    for r in rows:
        print("%-46s %7s %7s %8s %-8s %-18s %s" % (r["model"], r["short_s"], r["long_s"], r["tok_s"], r["tools"], r["inventa"], r["fakeapi_inventadas"]))


if __name__ == "__main__":
    main()
