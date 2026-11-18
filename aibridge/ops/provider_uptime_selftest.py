#!/usr/bin/env python3
"""Offline checks for ops/provider_uptime.py: fixture router logs, a fake opener instead of the providers, a recorder instead of the
ops bot, a real localhost socket standing in for the Zabbix trapper port. Run: python3 -I ops/provider_uptime_selftest.py"""
import urllib.request
import contextlib, io, json, math, os, re, socket, struct, sys, tempfile, threading, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
TMP = tempfile.mkdtemp(prefix="pu-")
os.environ.update(PROVIDER_UPTIME_STATE=os.path.join(TMP, "state.json"), PROVIDER_UPTIME_STACKS=os.path.join(TMP, "stacks.json"),
                  PROVIDER_UPTIME_MASTER=os.path.join(TMP, "master.json"), OPS_ENV=os.path.join(TMP, "no-ops.env"))
import provider_uptime as pu  # noqa: E402

NOW = 1_800_000_000
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)[:400]))
    if not cond:
        fails.append(name)


class Rec:
    """Stands in for ops/lib/notify.py."""
    def __init__(self):
        self.sent, self.alerts, self.resolved = [], [], []

    def send(self, text):
        self.sent.append(text)

    def alert(self, key, text, quiet=0):
        self.alerts.append((key, text, quiet))

    def resolve(self, key, text=None):
        self.resolved.append((key, text))


class Resp:
    def __init__(self, status=200, body=b'{"data":[]}'):
        self.status, self._b = status, body

    def read(self, n=-1):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_opener(behaviour, seen=None):
    """behaviour: host -> 200 | 429 | 503 | 'timeout' | 'reset' | callable(req)."""
    def opener(req, timeout=0):
        host = req.full_url.split("/")[2]
        if seen is not None:
            seen.append(req)
        b = behaviour.get(host, 200)
        if callable(b):
            return b(req)
        if b == "timeout":
            raise TimeoutError("timed out")
        if b == "reset":
            raise urllib.error.URLError(ConnectionResetError("reset"))
        if b == 200:
            return Resp(200, b'{"choices":[{"message":{"content":"p"}}]}' if req.data else b'{"data":[]}')
        raise urllib.error.HTTPError(req.full_url, b, "x", {}, io.BytesIO(b""))
    return opener


def lines(rows):
    return ("\n".join(json.dumps(r) for r in rows) + "\n").encode()


def ev(ts, model, result="ok", s=1.0, ttfb=0.5, **extra):
    return {"ts": ts, "model": model, "pos": 0, "mode": "best", "session": "abcd1234", "turn": "ffff0000", "aux": False, "result": result,
            "s": s, "ttfb": ttfb, "finish": "stop", "tools": 0, **extra}


# ---------------------------------------------------------------- classification

for r, want in [("ok", "ok"), ("HTTP 429", "429"), ("HTTP 401", "auth"), ("HTTP 403", "auth"), ("HTTP 500", "5xx"), ("HTTP 503", "5xx"),
                ("HTTP 408", "timeout"), ("HTTP 404", "client"), ("HTTP 400", "client"), ("TimeoutError", "timeout"),
                ("ReadTimeout", "timeout"), ("stream-broken", "net"), ("ConnectionResetError", "net"), ("RemoteDisconnected", "net"),
                ("SSLError", "net"), ("empty answer (stop)", "other")]:
    check(f"classify {r!r}", pu.classify(r) == want, pu.classify(r))
for n, want in [("NVIDIA nemotron-3.5-super", "nvidia"), ("Token Harbor deepseek-v4.1-flash", "tokenharbor"), ("Gemini flash-lite", "gemini"),
                ("OpenRouter ling-3.2-flash", "openrouter"), ("Cloudflare gpt-oss-120b", "cloudflare"), ("local", None), ("", None)]:
    check(f"provider_of {n!r}", pu.provider_of(n) == want, pu.provider_of(n))
try:    # every model name the router can log must map to a provider (a new provider added there must be added here)
    os.environ.setdefault("GATEWAY_LOG", os.path.join(TMP, "gw.jsonl"))
    sys.path.insert(0, os.path.dirname(HERE))
    import router
    names = [c[0] for c in router.CANDIDATES] + [c[0] for c in router.VISION_CLOUD]
    check("every router model name maps to a provider", all(pu.provider_of(n) for n in names), [n for n in names if not pu.provider_of(n)])
    check("every mapped provider has a label", all(pu.provider_of(n) in pu.LABEL for n in names))
except ImportError as e:
    check("router importable for the name check", False, e)

# ---------------------------------------------------------------- statistics

rows = [[NOW - 30, "nvidia", "s1", "ok", 2.0, 0.4], [NOW - 40, "nvidia", "s1", "ok", 3.0, 0.8], [NOW - 50, "nvidia", "s1", "429", 0.1, None],
        [NOW - 60, "nvidia", "s2", "timeout", 60.0, None], [NOW - 70, "nvidia", "s2", "5xx", 1.0, None], [NOW - 80, "nvidia", "s2", "auth", 0.1, None],
        [NOW - 90, "gemini", "s1", "ok", 1.0, 0.3], [NOW - 4000, "nvidia", "s1", "ok", 1.0, 9.0]]
w = pu.window_stats(rows, "nvidia", NOW, 300)
check("window counts", (w["calls"], w["ok"], w["429"], w["timeout"], w["5xx"], w["auth"]) == (6, 2, 1, 1, 1, 1), w)
check("availability ignores 429 and auth (2 ok of ok + timeout + 5xx)", w["avail"] == 50.0, w["avail"])
check("success counts every call", w["success"] == round(100 * 2 / 6, 1), w["success"])
check("ttfb percentiles, ok calls only", (w["ttfb_p50"], w["ttfb_p95"]) == (0.4, 0.8), (w["ttfb_p50"], w["ttfb_p95"]))
check("last success", w["last_ok"] == NOW - 30, w["last_ok"])
check("the window cuts old calls, the 24 h one keeps them", pu.window_stats(rows, "nvidia", NOW, 86400)["calls"] == 7)
check("per stack", pu.window_stats(rows, "nvidia", NOW, 300, stack="s2")["calls"] == 3)
check("empty window", pu.window_stats(rows, "groq", NOW, 300)["avail"] is None)
check("percentile of one value", pu.pct([4.0], 95) == 4.0 and pu.pct([], 95) is None)
check("histogram percentile", pu.hist_percentile([0, 0, 8, 2, 0, 0, 0, 0, 0], 50) == 2 and pu.hist_percentile([0] * 9, 50) is None
      and pu.hist_percentile([0] * 8 + [1], 95) == math.inf)

# ---------------------------------------------------------------- reading the logs and ingesting once

torn = b'ss": "x"}\n'
raw = torn + lines([ev(NOW - 100, "NVIDIA nemotron-3.5-super"), {"ts": NOW - 99, "model": "NVIDIA nemotron-3.5-super", "feedback": 1, "msg": "x"},
                    ev(NOW - 98, "Gemini flash-lite", "HTTP 429", 0.2, None), ev(NOW - 97, "mystery model"), ev(NOW - 97, "x", None)]) + b"not json\n"
reader = lambda stack, name: raw if name == ".model-eval.jsonl" else None
got = pu.read_rows({"name": "s1"}, reader)
check("read_rows skips torn, feedback, garbage and bad types", [r[1] for r in got] == ["NVIDIA nemotron-3.5-super", "Gemini flash-lite", "mystery model"], got)
st = pu.new_state()
check("ingest keeps the mapped ones", pu.ingest(st, "s1", got, NOW) == 2)
check("an unmapped name is counted by its first word only", st["unmapped"] == {"mystery": 1}, st["unmapped"])
check("ingest twice adds nothing", pu.ingest(st, "s1", got, NOW) == 0 and len(st["recent"]) == 2)
more = got + pu.read_rows({"name": "s1"}, lambda s, n: lines([ev(NOW - 98, "Gemini flash-lite", "HTTP 503", 1, None), ev(NOW - 50, "NVIDIA x")]) if n == ".model-eval.jsonl" else None)
check("a new line at the same second as the mark is still taken, a repeated one is not", pu.ingest(st, "s1", more, NOW) == 2, len(st["recent"]))
check("only metadata is kept: no session, turn, text or key", not re.search(r"abcd1234|ffff0000|finish|session|turn", json.dumps(st)), json.dumps(st)[:200])
check("hourly bucket got the calls", sum(sum(b["calls"].values()) for h in st["hours"].values() for b in h.values()) == 4)
old = pu.new_state()
check("rows older than the kept window or from the future are dropped",
      pu.ingest(old, "s1", [(NOW - 3 * 86400, "NVIDIA a", "ok", 1, 1), (NOW + 3600, "NVIDIA a", "ok", 1, 1)], NOW) == 0)

# ---------------------------------------------------------------- probes

seen = []
res = pu.probe_once("nvidia", "keyless", "", "", make_opener({}, seen))
check("keyless probe is a GET of /models with no Authorization", res["ok"] == 1 and seen[0].get_method() == "GET" and seen[0].full_url.endswith("/models")
      and not seen[0].has_header("Authorization"), (res, seen[0].full_url))
seen.clear()
res = pu.probe_once("gemini", "keyed", "probe-key-1", "", make_opener({}, seen))
check("keyed probe sends the probe key as a Bearer", seen[0].get_header("Authorization") == "Bearer probe-key-1" and res["ok"] == 1)
seen.clear()
res = pu.probe_once("nvidia", "chat", "k", "openai/gpt-oss-20b", make_opener({}, seen))
body = json.loads(seen[0].data)
check("chat probe: one token, a fixed word", body["max_tokens"] == 1 and body["messages"] == [{"role": "user", "content": "ping"}] and res["ok"] == 1, body)
for host, beh, want_ok, want_cls in [("integrate.api.nvidia.com", 503, 0, "5xx"), ("integrate.api.nvidia.com", 429, 1, "429"),
                                     ("integrate.api.nvidia.com", 401, 1, "auth"), ("integrate.api.nvidia.com", "timeout", 0, "timeout"),
                                     ("integrate.api.nvidia.com", "reset", 0, "net"), ("integrate.api.nvidia.com", 404, 1, "client")]:
    r = pu.probe_once("nvidia", "keyless", "", "", make_opener({host: beh}))
    check(f"probe answered {beh}: ok={want_ok} class {want_cls}", (r["ok"], r["cls"]) == (want_ok, want_cls), r)
check("a refused PROBE key is flagged (keyed), a 401 without a key is not",
      pu.probe_once("nvidia", "keyed", "k", "", make_opener({"integrate.api.nvidia.com": 401}))["auth"] is False
      and pu.probe_once("nvidia", "keyless", "", "", make_opener({"integrate.api.nvidia.com": 401}))["auth"] is None)
check("a 200 chat probe with no choices is a failure", pu.probe_once("nvidia", "chat", "k", "m", make_opener({"integrate.api.nvidia.com": lambda req: Resp(200, b"{}")}))["ok"] == 0)

conf = {"PROBE_PROVIDERS": "nvidia,gemini", "PROBE_KEY_NVIDIA": "pk", "PROBE_CHAT_NVIDIA": "openai/gpt-oss-20b", "NVIDIA_API_KEY": "person-key"}
st = pu.new_state()
seen.clear()
out = pu.run_probes(st, conf, NOW, make_opener({}, seen))
modes = sorted((r.full_url.split("/")[2], bool(r.data), r.has_header("Authorization")) for r in seen)
check("first pass: nvidia reach (keyed) + chat, gemini reach (keyless)", len(seen) == 3 and out["nvidia"]["reach"]["mode"] == "keyed" and out["nvidia"]["chat"]["mode"] == "chat"
      and out["gemini"]["reach"]["mode"] == "keyless" and "chat" not in out["gemini"], (modes, out))
check("the person's *_API_KEY is never used", all("person-key" not in str(r.headers) for r in seen))
seen.clear()
pu.run_probes(st, conf, NOW + 60, make_opener({}, seen))
check("rate limit: a second pass a minute later probes nothing", seen == [])
pu.run_probes(st, conf, NOW + 300, make_opener({}, seen))
check("five minutes later: reach again, chat not yet (15 min)", sorted(bool(r.data) for r in seen) == [False, False], len(seen))
seen.clear()
pu.run_probes(st, conf, NOW + 900, make_opener({}, seen))
check("fifteen minutes later: chat again", sum(bool(r.data) for r in seen) == 1)
check("load_conf takes only UPTIME_/PROBE_/ZBX_ names from the environment",
      "NVIDIA_API_KEY" not in pu.load_conf({"NVIDIA_API_KEY": "x", "PROBE_KEY_NVIDIA": "y", "UPTIME_AVAIL_MIN": "40"}))
src = open(os.path.join(HERE, "provider_uptime.py")).read()
check("the module never names a person's key variable", not re.search(r"(NVIDIA|GEMINI|GOOGLE|HF|OPENROUTER|TOKENHARBOR|GROQ|CLOUDFLARE)_(API_KEY|TOKEN)|env_var\(", src.replace("*_API_KEY", "")))

# ---------------------------------------------------------------- evaluation

th = pu.thresholds({})
check("default thresholds match the template macros",
      {m: v for m, v, _ in pu.MACROS} == {"{$PROV.PROBE.FAILS}": "3", "{$PROV.CHAT.FAILS}": "2", "{$PROV.AVAIL.MIN}": "50", "{$PROV.MIN.CALLS}": "5",
                                          "{$PROV.TTFB.P95.MAX}": "15", "{$PROV.PROBE.MS.MAX}": "5000", "{$PROV.429.PCT}": "50",
                                          "{$PROV.MIN.CALLS.429}": "10", "{$PROV.NODATA}": "20m", "{$PROV.TRAPPER.HOSTS}": "127.0.0.1"}
      and th["probe_fails"] == 3 and th["chat_fails"] == 2 and th["avail_min"] == 50 and th["min_calls"] == 5 and th["ttfb_p95_max"] == 15
      and th["probe_ms_max"] == 5000 and th["pct429"] == 50 and th["min_calls_429"] == 10)


def state_with(calls, probes=None, models=("NVIDIA m1", "NVIDIA m2"), stacks=("s1",)):
    s = pu.new_state()
    s["recent"] = [[NOW - 60 * i, "nvidia", stacks[i % len(stacks)], cls, 1.0, tf, models[i % len(models)]] for i, (cls, tf) in enumerate(calls)]
    s["probes"] = {"nvidia": probes or {}}
    return s


check("healthy", pu.evaluate("nvidia", state_with([("ok", 0.5)] * 8), NOW, th)[0] == "up")
check("three probes failed in a row: down", pu.evaluate("nvidia", state_with([], {"reach": {"streak": 3, "cls": "timeout"}}), NOW, th)[0] == "down")
check("two probes failed: not yet", pu.evaluate("nvidia", state_with([], {"reach": {"streak": 2}}), NOW, th)[0] == "up")
check("chat probe failed twice: down", pu.evaluate("nvidia", state_with([], {"chat": {"streak": 2, "cls": "5xx"}}), NOW, th)[0] == "down")
s, why = pu.evaluate("nvidia", state_with([("timeout", None)] * 6 + [("ok", 1)] * 2), NOW, th)
check("real traffic: 25 % ok over 10 min with 8 calls is down", s == "down" and "25%" in why[0], (s, why))
# one flaky model among healthy ones (explore mode) is not an outage: 3 failures of m1 out of 5 calls, m2 answers
mixed = [("timeout", None), ("ok", 0.5), ("timeout", None), ("ok", 0.5), ("timeout", None)]
check("failures of one model only (others answer) are not the provider down", pu.evaluate("nvidia", state_with(mixed), NOW, th)[0] == "up"
      and pu.window_stats(state_with(mixed)["recent"], "nvidia", NOW, 600)["wide"] is False)
check("one model, one stack, all failing: the probes decide, not the traffic", pu.evaluate("nvidia", state_with([("timeout", None)] * 8, models=("NVIDIA m1",)), NOW, th)[0] == "up")
check("one model in all, failing on two stacks: provider-wide", pu.evaluate("nvidia", state_with([("timeout", None)] * 8, models=("NVIDIA m1",), stacks=("s1", "s2")), NOW, th)[0] == "down")
check("two models failing: provider-wide", pu.window_stats(state_with([("5xx", None)] * 4)["recent"], "nvidia", NOW, 600)["wide"] is True)
check("records from before the model was kept (6 fields) still load", pu.window_stats([[NOW - 5, "nvidia", "s1", "ok", 1.0, 0.3]], "nvidia", NOW, 600)["calls"] == 1)
check("a few calls say nothing (4 < 5)", pu.evaluate("nvidia", state_with([("timeout", None)] * 4), NOW, th)[0] == "up")
check("auth errors only are not an outage; 429s under the minimum count are not a storm", pu.evaluate("nvidia", state_with([("auth", None)] * 12), NOW, th)[0] == "up"
      and pu.evaluate("nvidia", state_with([("429", None)] * 9), NOW, th)[0] == "up")
s, why = pu.evaluate("nvidia", state_with([("429", None)] * 8 + [("ok", 1)] * 2), NOW, th)
check("429 storm (80 % of 10 calls): degraded", s == "degraded" and "429" in why[0], (s, why))
s, why = pu.evaluate("nvidia", state_with([("ok", 40.0)] * 6), NOW, th)
check("slow first byte (p95 40 s): degraded", s == "degraded" and "p95" in why[0], (s, why))
s, why = pu.evaluate("nvidia", state_with([], {"reach": {"streak": 0, "hist": [[1, 1, 9000], [2, 1, 9000], [3, 1, 9000]]}}), NOW, th)
check("three slow probes: degraded", s == "degraded", (s, why))
check("down wins over degraded", pu.evaluate("nvidia", state_with([("timeout", None)] * 8, {"reach": {"streak": 0, "hist": [[1, 1, 9000]] * 3}}), NOW, th)[0] == "down")
check("a provider with no data is up", pu.evaluate("groq", pu.new_state(), NOW, th)[0] == "up")

# state machine: down -> up needs two good evaluations; outage intervals are recorded
st = pu.new_state()
check("up -> down at once", pu.advance(st, "nvidia", "down", ["x"], NOW) == ("up", "down"))
check("one good evaluation does not close it", pu.advance(st, "nvidia", "up", [], NOW + 300) is None and st["prov"]["nvidia"]["state"] == "down")
check("a bad one in between resets the count", pu.advance(st, "nvidia", "down", ["x"], NOW + 600) is None and st["prov"]["nvidia"]["clear"] == 0)
pu.advance(st, "nvidia", "up", [], NOW + 900)
check("two in a row close it", pu.advance(st, "nvidia", "up", [], NOW + 1200) == ("down", "up") and st["intervals"][0]["e"] == NOW + 1200, st["intervals"])
check("degraded -> down closes one interval and opens another", pu.advance(st, "nvidia", "degraded", ["s"], NOW + 1500) == ("up", "degraded")
      and pu.advance(st, "nvidia", "down", ["d"], NOW + 1800) == ("degraded", "down")
      and [(i["k"], i["e"]) for i in st["intervals"][1:]] == [("degraded", NOW + 1800), ("down", None)], st["intervals"])

# ---------------------------------------------------------------- Zabbix: the trapper protocol against a local socket

received, refuse = [], [0]


def fake_zabbix(srv):
    while True:
        try:
            c, _ = srv.accept()
        except OSError:
            return
        with c:
            head = c.recv(13)
            n = struct.unpack("<Q", head[5:13])[0]
            data = b""
            while len(data) < n:
                data += c.recv(n - len(data))
            req = json.loads(data)
            received.append(req)
            total = len(req["data"])
            failed = min(refuse[0], total)
            body = json.dumps({"response": "success", "info": f"processed: {total - failed}; failed: {failed}; total: {total}; seconds spent: 0.001"}).encode()
            c.sendall(b"ZBXD\x01" + struct.pack("<Q", len(body)) + body)


srv = socket.socket()
srv.bind(("127.0.0.1", 0))
srv.listen(4)
threading.Thread(target=fake_zabbix, args=(srv,), daemon=True).start()
port = srv.getsockname()[1]
items = [("provider-nvidia", "provider.state", 0), ("provider-nvidia", "provider.traffic.avail[10m]", 97.5)]
check("native trapper send", pu.trapper_send(items, "127.0.0.1", port) == (2, 0) and received[-1]["request"] == "sender data"
      and received[-1]["data"][1] == {"host": "provider-nvidia", "key": "provider.traffic.avail[10m]", "value": "97.5"}, received[-1:])
check("push: not configured -> None", pu.push(items, {}) is None)
check("push: accepted", pu.push(items, {"ZBX_SERVER": "127.0.0.1", "ZBX_PORT": str(port)}) == (True, "2 values"))
refuse[0] = 1
okp = pu.push(items, {"ZBX_SERVER": "127.0.0.1", "ZBX_PORT": str(port)})
check("push: one value refused is reported as a failure", okp[0] is False and "refused" in okp[1], okp)
srv2 = socket.socket()
srv2.bind(("127.0.0.1", 0))
dead = srv2.getsockname()[1]
srv2.close()
check("push: nothing listening is a failure, not a crash", pu.push(items, {"ZBX_SERVER": "127.0.0.1", "ZBX_PORT": str(dead)})[0] is False)
refuse[0] = 0
fake = os.path.join(TMP, "zabbix_sender")
open(fake, "w").write('#!/bin/sh\ncat > "%s/sender-input"\necho "Response from \\"x:10051\\": \\"success\\" processed: 2; failed: 0; total: 2"\n' % TMP)
os.chmod(fake, 0o755)
check("push through the zabbix_sender binary", pu.push(items, {"ZBX_SERVER": "z", "ZBX_SENDER": fake}) == (True, "2 values")
      and open(os.path.join(TMP, "sender-input")).read() == '"provider-nvidia" "provider.state" "0"\n"provider-nvidia" "provider.traffic.avail[10m]" "97.5"\n')
check("push: a missing binary is a failure", pu.push(items, {"ZBX_SERVER": "z", "ZBX_SENDER": "/nonexistent/zabbix_sender"})[0] is False)

# ---------------------------------------------------------------- fallback plan

master = {"hosts": {"gpu-a": {"addr": "h", "llm": 8630, "llm_model": "gemma-4-e4b"}, "gpu-b": {"addr": "h2", "transcode": 8610}},
          "stacks": {"s1": {"gpu": ["gpu-a"], "cloud_direct": True}, "s2": {"gpu": []}, "s3": {"gpu": ["gpu-a"]},
                     "s4": {"gpu": ["gpu-a"], "gpu_only": {"gpu-a": ["transcode"]}}, "s6": {"gpu": []}}}
stacks = [{"name": n} for n in ("s1", "s2", "s3", "s4", "s5", "s6")]
st = pu.new_state()
st["recent"] = ([[NOW - 100 - i, "nvidia", "s1", "timeout", 60, None] for i in range(6)]
                + [[NOW - 100, "nvidia", "s2", "timeout", 60, None]] + [[NOW - 90 - i, "gemini", "s2", "ok", 1, 0.3] for i in range(3)]
                + [[NOW - 100, "nvidia", "s3", "ok", 1, 0.3]] + [[NOW - 100, "gemini", "s5", "ok", 1, 0.3]] + [[NOW - 100, "nvidia", "s6", "5xx", 1, None]])
cfg = lambda s: {"s3": 'model:\n  # c\n  default: "x"\n  provider: "nvidia"\n', "s4": 'model:\n  provider: "custom"\n'}.get(s["name"])
plan = pu.fallback_plan("nvidia", st, NOW, stacks, master, cfg)
by = {r["stack"]: r for r in plan["stacks"]}
check("only-this-provider stack FAILS", by["s1"]["verdict"] == "FAILS" and by["s1"]["mode"] == "cloud_direct" and by["s1"]["local"] == ["gpu-a:gemma-4-e4b"], by["s1"])
check("stack with another provider answering is degraded, not failing", by["s2"]["verdict"] == "degraded" and by["s2"]["alternatives"] == ["gemini"], by["s2"])
check("a pinned stack fails whatever it used", by["s3"]["verdict"] == "FAILS" and by["s3"]["mode"] == "pinned", by["s3"])
check("gpu_only without llm leaves no local set", by["s4"]["local"] == [] and by["s4"]["verdict"] == "no effect")
check("a stack that did not use it is unaffected", by["s5"]["verdict"] == "no effect")
text = pu.plan_text(plan)
cmds = " ".join(c for s in plan["steps"] for c in s["commands"])
check("steps: start the llm on its host, drop cloud_direct, dry-run sync, sync, switch the pinned stack",
      "gpu-host/run_services.sh start llm" in cmds and 'delete "cloud_direct": true from s1' in cmds and "gateways_sync.py --check" in cmds
      and "ops/switch_to_local_first.sh s3" in cmds and "ops/recreate_hermes.sh s3" in cmds, cmds)
titles = " ".join(s["title"] for s in plan["steps"] if s["title"].startswith("No local LLM"))
check("a failing stack without a local set is called out, a degraded one is not asked to move", "s6" in titles and "s2" not in titles and "s2" not in cmds, (titles, cmds))
check("the plan names its dry-run and says nothing is switched", "fallback --provider nvidia" in text and "nothing is switched automatically" in text)
check("the plan carries no address or token", not re.search(r"\d+\.\d+\.\d+\.\d+|[A-Za-z0-9_-]{30,}", text), text)
none = pu.fallback_plan("groq", st, NOW, stacks, master, cfg)
check("a provider nobody used: nothing to move", none["steps"] == [] and "nothing to move" in pu.plan_text(none))
check("config_provider reads only model.provider", pu.config_provider('foo:\n  provider: "x"\nmodel:\n  default: "a"\n  provider: gemini # c\nother:\n  provider: y\n') == "gemini"
      and pu.config_provider("") is None and pu.config_provider("model:\n  default: a\n") is None)

# ---------------------------------------------------------------- one run, end to end

def fixture_reader(timeouts_for_s1=True):
    def r(stack, name):
        if name != ".model-eval.jsonl":
            return None
        if stack["name"] == "s1":
            return lines([ev(NOW - 20 * i - 10, "NVIDIA nemotron-3.5-super", "TimeoutError" if timeouts_for_s1 else "ok", 60, None) for i in range(7)])
        return lines([ev(NOW - 10, "NVIDIA nemotron-3.5-super", "TimeoutError", 60, None)] + [ev(NOW - 30 - i, "Gemini flash-lite") for i in range(3)])
    return r


ZB = {"ZBX_SERVER": "127.0.0.1", "ZBX_PORT": str(port), "PROBE_PROVIDERS": "nvidia,gemini", "ZBX_PROVIDERS": "nvidia,gemini"}
stacks2 = [{"name": "s1"}, {"name": "s2"}]
master2 = {"hosts": master["hosts"], "stacks": {"s1": {"gpu": ["gpu-a"], "cloud_direct": True}, "s2": {"gpu": []}}}
cfg2 = lambda s: 'model:\n  provider: "custom"\n'

# 1. no Zabbix: the ops bot gets the alert, with the plan
rec = Rec()
st, rep = pu.run({"PROBE_PROVIDERS": "nvidia,gemini"}, NOW, opener=make_opener({}), reader=fixture_reader(), notify=rec, stacks=stacks2, master=master2, config_reader=cfg2)
check("no Zabbix: transition nvidia up -> down by real traffic", [(t[0], t[1], t[2]) for t in rep["transitions"]] == [("nvidia", "up", "down")], rep["transitions"])
check("...alerted through the ops bot with the stacks and the steps", len(rec.alerts) == 1 and rec.alerts[0][0] == "provider-uptime:nvidia" and rec.alerts[0][2] == 0
      and "s1" in rec.alerts[0][1] and "FAILS" in rec.alerts[0][1] and "fallback --provider nvidia" in rec.alerts[0][1] and "gateways_sync" in pu.plan_text(pu.fallback_plan("nvidia", st, NOW, stacks2, master2, cfg2)), rec.alerts)
check("...and zabbix reported as not configured", rep["zabbix"] is None)
check("gemini stays up", st["prov"].get("gemini", {}).get("state") == "up")
st_json = json.dumps(st)
check("state holds no session, turn, text or key", not re.search(r"abcd1234|ffff0000|probe-key", st_json))
rec = Rec()
st, rep = pu.run({"PROBE_PROVIDERS": "nvidia,gemini"}, NOW + 60, opener=make_opener({}), reader=fixture_reader(), notify=rec, stacks=stacks2, master=master2, state=st, config_reader=cfg2)
check("the same outage on the next run is not alerted again and the calls are not counted twice", rec.alerts == [] and rep["read"] == 0 and len(st["recent"]) == 11, (rec.alerts, rep["read"], len(st["recent"])))

# 2. recovery: needs two clean evaluations (calls age out of the 10 min window)
rec = Rec()
for k, t in enumerate((NOW + 1000, NOW + 1300, NOW + 1600)):
    st, rep = pu.run({"PROBE_PROVIDERS": "nvidia,gemini"}, t, opener=make_opener({}), reader=lambda s, n: None, notify=rec, stacks=stacks2, master=master2, state=st, config_reader=cfg2)
check("recovery after two clean runs, with the duration", len(rec.resolved) >= 1 and rec.resolved[-1][0] == "provider-uptime:nvidia" and "is answering again" in rec.resolved[-1][1]
      and "lasted" not in rec.resolved[-1][1], rec.resolved)   # notify.resolve adds the duration itself

# 3. probes alone: three failures in a row (spaced by the interval) make it down
rec, st = Rec(), pu.new_state()
bad = make_opener({"integrate.api.nvidia.com": 503})
for k in range(3):
    st, rep = pu.run({"PROBE_PROVIDERS": "nvidia"}, NOW + 300 * k, opener=bad, reader=lambda s, n: None, notify=rec, stacks=[], master=master2, state=st, config_reader=cfg2)
    check(f"probe failure {k + 1}: " + ("down" if k == 2 else "still up"), st["prov"]["nvidia"]["state"] == ("down" if k == 2 else "up"), st["prov"])
check("down by probes alerted exactly once", len(rec.alerts) == 1 and "3 probes" in rec.alerts[0][1], rec.alerts)

# 4. Zabbix accepting: Zabbix owns the paging, we add the plan once
rec = Rec()
received.clear()
st, rep = pu.run(ZB, NOW, opener=make_opener({}), reader=fixture_reader(), notify=rec, stacks=stacks2, master=master2, config_reader=cfg2)
check("Zabbix took the values", rep["zabbix"] and rep["zabbix"][0] is True, rep["zabbix"])
check("hosts and keys pushed", {i["host"] for i in received[-1]["data"]} == {"provider-nvidia", "provider-gemini"}
      and any(i["key"] == "provider.state" and i["host"] == "provider-nvidia" and i["value"] == "2" for i in received[-1]["data"]))
rec0 = Rec()
received.clear()
pu.run({"ZBX_SERVER": "127.0.0.1", "ZBX_PORT": str(port), "PROBE_PROVIDERS": "nvidia"}, NOW, opener=make_opener({}), reader=lambda s, n: None, notify=rec0, stacks=[], master=master2)
check("by default every hosted provider gets a heartbeat, data or not (the silence alarm needs it)",
      {i["host"] for i in received[-1]["data"] if i["key"] == "provider.heartbeat"} == {"provider-" + p for p in pu.HOSTED}, received[-1]["data"][:2])
rec1 = Rec()
received.clear()
cf_reader = lambda stack, name: lines([ev(NOW - 5 - i, "Cloudflare gpt-oss-120b", "TimeoutError", 30, None) for i in range(6)]) if name == ".model-eval.jsonl" else None
pu.run({"ZBX_SERVER": "127.0.0.1", "ZBX_PORT": str(port), "ZBX_PROVIDERS": "nvidia"}, NOW, opener=make_opener({}), notify=rec1, stacks=[{"name": "s1"}, {"name": "s2"}], master=master2, reader=cf_reader)
check("a provider with traffic but no Zabbix host is alerted by us and never pushed",
      [a[0] for a in rec1.alerts] == ["provider-uptime:cloudflare"] and all(i["host"] != "provider-cloudflare" for i in received[-1]["data"]), (rec1.alerts, received[-1]["data"][:1]))
check("with Zabbix there is no alert of ours, only the plan, once", rec.alerts == [] and len(rec.sent) == 1 and "FAILS" in rec.sent[0] and rec.sent[0].startswith("ℹ️"), (rec.alerts, rec.sent))
st, rep = pu.run(ZB, NOW + 30, opener=make_opener({}), reader=fixture_reader(), notify=rec, stacks=stacks2, master=master2, state=st, config_reader=cfg2)
check("the plan is not repeated while the outage lasts", len(rec.sent) == 1)

# 5. Zabbix refusing: we alert ourselves, and say why
rec = Rec()
refuse[0] = 3
st, rep = pu.run(ZB, NOW, opener=make_opener({}), reader=fixture_reader(), notify=rec, stacks=stacks2, master=master2, config_reader=cfg2)
refuse[0] = 0
check("Zabbix refused: our own alert plus the sender problem", {a[0] for a in rec.alerts} == {"provider-uptime:nvidia", pu.OUTBOX_KEY}, rec.alerts)
rec = Rec()
st, rep = pu.run(ZB, NOW + 300, opener=make_opener({}), reader=lambda s, n: None, notify=rec, stacks=stacks2, master=master2, state=st, config_reader=cfg2)
check("when Zabbix accepts again the sender problem resolves", (pu.OUTBOX_KEY, "Zabbix accepts the provider metrics again") in rec.resolved, rec.resolved)

# 6. a refused probe key is said once, not read as an outage
rec = Rec()
st, rep = pu.run({"PROBE_PROVIDERS": "nvidia", "PROBE_KEY_NVIDIA": "pk"}, NOW, opener=make_opener({"integrate.api.nvidia.com": 401}), reader=lambda s, n: None, notify=rec,
                 stacks=[], master=master2, config_reader=cfg2)
check("probe key refused: its own alert, provider still up", [a[0] for a in rec.alerts] == ["provider-uptime:probe-key:nvidia"] and st["prov"]["nvidia"]["state"] == "up", rec.alerts)

# 7. a dry run writes and sends nothing
rec = Rec()
pu.run({"PROBE_PROVIDERS": "nvidia"}, NOW, opener=make_opener({}), reader=fixture_reader(), notify=None, stacks=stacks2, master=master2, config_reader=cfg2)
check("dry run (notify=None) sends nothing", rec.alerts == [] and rec.sent == [])

# 8. the VM's own network is down: one condition, no provider is called down, nothing about them goes to Zabbix
def dns_fail(req, timeout=0):
    raise urllib.error.URLError(socket.gaierror(-3, "Temporary failure in name resolution"))


ALL6 = "nvidia,gemini,huggingface,openrouter,tokenharbor,groq"
rec, st, received_before = Rec(), pu.new_state(), len(received)
ZB6 = {"ZBX_SERVER": "127.0.0.1", "ZBX_PORT": str(port), "PROBE_PROVIDERS": ALL6}
for k in range(4):
    st, rep = pu.run(ZB6, NOW + 300 * k, opener=dns_fail, reader=lambda s_, n: None, notify=rec, stacks=[], master=master2, state=st, config_reader=cfg2)
check("DNS failure on the VM: no provider is down after four runs", all(v["state"] == "up" for v in st["prov"].values()) and not st["intervals"], st["prov"])
check("...one 'collector network down' alert, no per-provider alert, no plan", [a[0] for a in rec.alerts] == [pu.NET_KEY] and rec.sent == [], (rec.alerts, rec.sent))
check("...the Zabbix pushes carry only heartbeat and state, never a failed probe",
      all(i["key"] in ("provider.heartbeat", "provider.state") for r_ in received[received_before:] for i in r_["data"]) and len(received) > received_before)
rec = Rec()
st, rep = pu.run(ZB6, NOW + 1500, opener=make_opener({}), reader=lambda s_, n: None, notify=rec, stacks=[], master=master2, state=st, config_reader=cfg2)
check("network back: the condition resolves, providers stay up", (pu.NET_KEY, "The VM has network again; provider alerts resume") in rec.resolved
      and all(v["state"] == "up" for v in st["prov"].values()) and not st["net"].get("down"), (rec.resolved, st["net"]))
# a real provider outage with the control answering is still down
rec, st = Rec(), pu.new_state()
down_only = make_opener({"integrate.api.nvidia.com": "reset"})
for k in range(3):
    st, rep = pu.run({"PROBE_PROVIDERS": "nvidia,gemini"}, NOW + 300 * k, opener=down_only, reader=lambda s_, n: None, notify=rec, stacks=[], master=master2, state=st, config_reader=cfg2)
check("one provider failing while the control and the others answer is down", st["prov"]["nvidia"]["state"] == "down" and st["net"]["ok"] == 1, st["prov"])
# control answering but every provider failing is a real, wide outage, not a network loss
rec, st = Rec(), pu.new_state()
every = make_opener({h: 503 for h in ("integrate.api.nvidia.com", "generativelanguage.googleapis.com")})
for k in range(3):
    st, rep = pu.run({"PROBE_PROVIDERS": "nvidia,gemini"}, NOW + 300 * k, opener=every, reader=lambda s_, n: None, notify=rec, stacks=[], master=master2, state=st, config_reader=cfg2)
check("all probed providers failing while the control answers: both are down", {p_ for p_, v in st["prov"].items() if v["state"] == "down"} == {"nvidia", "gemini"}, st["prov"])
# PROBE_CONTROL=off: no control, no verdict on the network (the old behaviour)
check("PROBE_CONTROL=off disables the control probe", pu.probe_control({"PROBE_CONTROL": "off"}, dns_fail) is None and pu.control_urls({}) == list(pu.CONTROL_URLS)
      and pu.control_urls({"PROBE_CONTROL": "http://x,https://dns.example/"}) == ["https://dns.example/"])

# 9. probe values go out only in a run that probed (PROBE_INTERVAL_S above the timer period)
rec, st = Rec(), pu.new_state()
bad = make_opener({"integrate.api.nvidia.com": 503})
cnf = {"ZBX_SERVER": "127.0.0.1", "ZBX_PORT": str(port), "PROBE_PROVIDERS": "nvidia", "ZBX_PROVIDERS": "nvidia", "PROBE_INTERVAL_S": "900"}
probe_pushes, probed_runs = [], []
for k in range(3):
    n0 = len(received)
    st, rep = pu.run(cnf, NOW + 300 * k, opener=bad, reader=lambda s_, n: None, notify=rec, stacks=[], master=master2, state=st, config_reader=cfg2)
    probed_runs.append(rep["probed"])
    probe_pushes.append(sum(1 for r_ in received[n0:] for i in r_["data"] if i["key"] == "provider.probe.ok"))
check("a probe interval of 900 s: one probe in three runs, and one probe.ok pushed, not three", probed_runs == [1, 0, 0] and probe_pushes == [1, 0, 0], (probed_runs, probe_pushes))

# 10. recovery is resolved even when Zabbix owns the provider by then (our alert may have been opened while it refused the values)
rec, st = Rec(), pu.new_state()
refuse[0] = 1000
st, rep = pu.run(ZB, NOW, opener=make_opener({}), reader=fixture_reader(), notify=rec, stacks=stacks2, master=master2, state=st, config_reader=cfg2)
refuse[0] = 0
check("(setup) our own alert is open", "provider-uptime:nvidia" in [a[0] for a in rec.alerts], rec.alerts)
rec = Rec()
for t in (NOW + 1000, NOW + 1300, NOW + 1600):
    st, rep = pu.run(ZB, t, opener=make_opener({}), reader=lambda s_, n: None, notify=rec, stacks=stacks2, master=master2, state=st, config_reader=cfg2)
check("Zabbix owns by then: the alert we opened is still resolved, once, without a duration of our own",
      [r_ for r_ in rec.resolved if r_[0] == "provider-uptime:nvidia"] == [("provider-uptime:nvidia", "NVIDIA NIM is answering again")], rec.resolved)

# state file: atomic, private, round trip
sp = os.path.join(TMP, "sub", "s.json")
pu.save_state(st, sp)
check("state file is private and round-trips", oct(os.stat(sp).st_mode & 0o777) == "0o600" and pu.load_state(sp)["runs"] == st["runs"])
check("a damaged state file starts clean", pu.load_state(os.path.join(TMP, "none.json"))["runs"] == 0)
open(sp, "w").write("{broken")
check("...also a half-written one", pu.load_state(sp)["runs"] == 0)

# ---------------------------------------------------------------- monthly report

DAY = 86400
m_start = 1_801_000_000 - (1_801_000_000 % 3600)
month = pu.time.strftime("%Y-%m", pu.time.gmtime(m_start))
lo, hi = pu.month_bounds(month)
st = pu.new_state()
for h in range(10):                                   # ten monitored hours
    b = pu.bucket(st, "nvidia", lo + h * 3600)
    b["probe"], b["calls"] = [12, 11 if h == 3 else 12], {"ok": 9, "timeout": 1 if h == 3 else 0, "429": 2}
    b["ttfb"][2] = 9
st["intervals"] = [{"p": "nvidia", "k": "down", "s": lo + 3 * 3600, "e": lo + 3 * 3600 + 1800, "why": "3 probes"},
                   {"p": "nvidia", "k": "degraded", "s": lo + 5 * 3600, "e": lo + 5 * 3600 + 600, "why": "slow"},
                   {"p": "nvidia", "k": "down", "s": lo - 7200, "e": lo + 1200, "why": "started last month"}]
rep = pu.month_report(st, month, hi + 10)
r = rep["providers"]["nvidia"]
check("uptime = 1 - down time / monitored time (30 min + 20 min clipped to the month, of 10 h)", r["down_min"] == 50 and r["uptime"] == round(100 * (1 - 3000 / 36000), 3), r)
check("degraded minutes, outages, probes", r["degraded_min"] == 10 and len(r["outages"]) == 2 and r["probes"] == 120 and r["probe_success"] == round(100 * 119 / 120, 2), r)
check("traffic availability ignores 429", r["traffic_avail"] == round(100 * 90 / 91, 2) and r["r429"] == 20, r)
check("ttfb from the histogram", r["ttfb_p50"] == 2 and r["ttfb_p95"] == 2, r)
check("report text mentions the provider, the month and the outage", "NVIDIA NIM" in pu.report_text(rep) and month in pu.report_text(rep) and "outage" in pu.report_text(rep))
check("report --json is valid JSON even with the open top bucket (p95 over 64 s)", (lambda t: "Infinity" not in t and json.loads(t, parse_constant=lambda c: 1 / 0))(
      json.dumps(pu.json_safe({"a": [math.inf, 2.5], "b": {"c": math.inf}}))) == {"a": [">64", 2.5], "b": {"c": ">64"}})
check("an empty month says so", "No data" in pu.report_text(pu.month_report(pu.new_state(), month, hi)))
check("previous month rolls over the year", pu.previous_month(1_767_300_000) == "2025-12" and pu.previous_month(1_780_000_000) == "2026-04")
st2 = pu.new_state()
st2["recent"] = [[NOW - 10, "nvidia", "s1", "ok", 1.0, 0.5]]
st2["last_ok"] = {"nvidia": NOW - 10}
check("status text renders a row per provider", pu.status_text(pu.status_table(st2, NOW), NOW).startswith("nvidia"))

# ---------------------------------------------------------------- the Zabbix template

tpl = pu.build_template()
path = os.path.join(HERE, "zabbix", "template_provider_uptime.yaml")
check("the template file in git is what the generator makes", os.path.exists(path) and open(path).read() == tpl, "run: python3 ops/provider_uptime.py template > ops/zabbix/template_provider_uptime.yaml")
item_keys = set(re.findall(r"^          key: '([^']+)'$", tpl, re.M))
st = pu.new_state()
st["probes"] = {"nvidia": {"reach": {"last": NOW, "ok": 1, "ms": 5, "code": 200}}}
st["prov"] = {"nvidia": {"state": "up"}}
pushed = {k for k, _ in pu.metrics("nvidia", st, NOW, {"nvidia": {"reach": {"ok": 1, "ms": 5, "code": 200}, "chat": {"ok": 1, "ms": 9}}})}
check("every pushed key is an item of the template", pushed <= item_keys, sorted(pushed - item_keys))
check("every item of the template is pushed", item_keys <= pushed, sorted(item_keys - pushed))
refs = set(re.findall(r"/Cloud provider uptime/([A-Za-z0-9_.]+(?:\[[^\]]*\])?)", " ".join(re.findall(r"expression: '([^\n]*)'", tpl))))
check("trigger expressions use only items that exist", refs and refs <= item_keys, sorted(refs - item_keys))
uuids = re.findall(r"uuid: ([0-9a-f]{32})$", tpl, re.M)
check("uuids are unique, 32 hex, version 4", len(uuids) == len(set(uuids)) >= 40 and all(u[12] == "4" and u[16] in "89ab" for u in uuids), len(uuids))
check("three triggers with the severities the hook routes on", re.findall(r"name: '(Cloud provider down|Cloud provider degraded|Provider uptime collector not reporting)'\n\s+priority: (\w+)", tpl)
      == [("Provider uptime collector not reporting", "AVERAGE"), ("Cloud provider down", "HIGH"), ("Cloud provider degraded", "AVERAGE")], re.findall(r"priority: (\w+)", tpl))
check("tier tags: critical on the down trigger", "value: critical" in tpl and tpl.count("value: normal") == 2)
check("the template carries the service tag and a closed trapper default", "tag: service\n          value: llm" in tpl and "'{$PROV.TRAPPER.HOSTS}'" in tpl)
macros_used = set(re.findall(r"\{\$PROV\.[A-Z0-9.]+\}", " ".join(re.findall(r"expression: '([^\n]*)'", tpl))))
check("every macro of an expression is defined", macros_used <= {m for m, _, _ in pu.MACROS}, macros_used)
check("the degraded trigger has no min()/avg() of a probe item (no data would make it Unknown)", not re.search(r"(min|max|avg)\(/Cloud provider uptime/provider\.probe", tpl)
      and "count(/Cloud provider uptime/provider.probe.ms,#3,\"gt\"" in tpl)
check("the traffic rule of the down trigger needs the provider-wide flag", 'last(/Cloud provider uptime/provider.traffic.wide[10m])=1' in tpl)
check("trigger names are static (no event text)", not re.search(r"name: '[^']*\{(HOST|ITEM|EVENT)", tpl))
check("the host name matches what provision.py will create", pu.zbx_host("nvidia") == "provider-nvidia")

# ---------------------------------------------------------------- provision.py provider-hosts, against a stub of the Zabbix API

sys.path.insert(0, os.path.join(HERE, "zabbix"))
import provision as pv  # noqa: E402

check("provision.py knows the same providers and template name", pv.PROVIDER_HOSTS == pu.HOSTED and pv.PROVIDER_TEMPLATE == pu.TEMPLATE_NAME)
calls, db = [], {"hosts": {}, "groups": {}}


def fake_api(method, params, auth=True):
    calls.append((method, params))
    if method == "template.get":
        return [{"templateid": "9"}]
    if method == "usergroup.get":
        return [{"usrgrpid": "5", "hostgroup_rights": [{"id": "1", "permission": "2"}]}]
    if method == "hostgroup.get":
        return [{"groupid": db["groups"][params["filter"]["name"]], "name": params["filter"]["name"]}] if params.get("filter", {}).get("name") in db["groups"] else []
    if method == "hostgroup.create":
        db["groups"][params["name"]] = str(100 + len(db["groups"]))
        return {"groupids": [db["groups"][params["name"]]]}
    if method == "host.get":
        return [{"hostid": db["hosts"][params["filter"]["host"]]}] if params.get("filter", {}).get("host") in db["hosts"] else []
    if method == "host.create":
        db["hosts"][params["host"]] = str(200 + len(db["hosts"]))
        return {"hostids": [db["hosts"][params["host"]]]}
    return {}


pv.api, pv.require_super_admin = fake_api, lambda: None
with contextlib.redirect_stdout(io.StringIO()):
    pv.provider_hosts(["nvidia", "groq"], "192.0.2.7", True)
created = [p for m, p in calls if m == "host.create"]
check("one host per provider, tagged for the hook, linked to the template, in its own group",
      [c["host"] for c in created] == ["provider-nvidia", "provider-groq"] and all(c["templates"] == [{"templateid": "9"}] for c in created)
      and created[0]["tags"] == [{"tag": "project", "value": "bridgeai"}, {"tag": "unit", "value": "provider-nvidia"}] and "interfaces" not in created[0], created[:1])
check("the trapper items accept only the sender address", [p["macros"] for m, p in calls if m == "host.update"] == [[{"macro": "{$PROV.TRAPPER.HOSTS}", "value": "192.0.2.7"}]] * 2)
imp = [p for m, p in calls if m == "configuration.import"][0]
check("the template is imported as YAML from the repo file", imp["format"] == "yaml" and imp["source"] == tpl and imp["rules"]["templates"]["updateExisting"] is True)
rights = [p for m, p in calls if m == "usergroup.update"][0]["hostgroup_rights"]
check("bridgeai-ops gets read on the new groups and keeps what it had", {r["id"] for r in rights} == {"1", "100", "101"} and all(r["permission"] == "2" for r in rights), rights)
n = len(calls)
with contextlib.redirect_stdout(io.StringIO()):
    pv.provider_hosts(["nvidia", "groq"], "192.0.2.7", False)
check("repeating it creates nothing twice", not [1 for m, p in calls[n:] if m in ("host.create", "hostgroup.create")])
try:
    pv.provider_hosts(["nvidia"], "", False)
    check("a missing sender address is refused", False)
except SystemExit:
    check("a missing sender address is refused", True)

# a probe never follows a redirect, so its key cannot reach another host
import http.server
_hits = {"b": []}
class _B(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        _hits["b"].append(self.headers.get("Authorization"))
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a): pass
_srv_b = http.server.HTTPServer(("127.0.0.1", 0), _B)
class _A(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302); self.send_header("Location", f"http://127.0.0.1:{_srv_b.server_port}/models"); self.end_headers()
    def log_message(self, *a): pass
_srv_a = http.server.HTTPServer(("127.0.0.1", 0), _A)
for _s in (_srv_a, _srv_b):
    threading.Thread(target=_s.serve_forever, daemon=True).start()
_req = urllib.request.Request(f"http://127.0.0.1:{_srv_a.server_port}/models", headers={"Authorization": "Bearer fake-test-key"})
try:
    with pu.open_probe(_req, timeout=5) as _r:
        _code = _r.status
except urllib.error.HTTPError as _e:
    _code = _e.code
check("a keyed probe answered with a redirect does not follow it: the key never reaches the other host", _code == 302 and _hits["b"] == [], (_code, _hits))
for _s in (_srv_a, _srv_b):
    _s.shutdown()

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ok provider_uptime selftest")
