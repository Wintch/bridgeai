#!/usr/bin/env python3
"""Offline checks for the synthetic business day harness (ops/synth_day.py, synth_fake_llm.py, synth_stubs.py). No docker, no network beyond loopback,
no token spent. Run: python3 -I ops/synth_day_selftest.py

A fake Hermes API (it builds a request like Hermes does, loops tool calls against the fake model, returns usage) stands in for a test stack.
Checks: the timeline follows the scenario volumes and is deterministic; the safety rules refuse before anything is sent; a day replays and
its numbers add up (turns, tokens against the fake model's own counters); the report holds no text, key or stack name; --dry-run sends nothing;
caps and the kill file stop the replay; task events need a target with tareas; the awake and capacity arithmetic; the stubs count; the fake
model streams, fails and caps as scripted.

Where a check could be circular (the fake Hermes sums the fake model's usage, so "tokens equal the fake's counters" holds by construction), it is
written against something computed on another side: the request sizes the fake Hermes itself measured, the scenario file's own numbers, or a hand
calculation written out in the check. Every scripted command is run through the real argument parser of the command where the repo has one
(tareas.py) and against the real list of gateway commands (gateway.py), so a bare `gateway tareas nueva` cannot come back.
"""
import _thread
import importlib.util
import json
import math
import os
import re
import shlex
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


sd, fl, stubs = load("synth_day"), load("synth_fake_llm"), load("synth_stubs")
ROOT = os.path.dirname(HERE)
_ts = importlib.util.spec_from_file_location("tareas_real", os.path.join(ROOT, "tareas.py"))
tareas = importlib.util.module_from_spec(_ts)
_ts.loader.exec_module(tareas)
GW_CMDS = set(re.findall(r'"([a-z-]+)": cmd_', open(os.path.join(ROOT, "gateway.py")).read()))
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def post(url, body, key=None, headers=None, timeout=20):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    h.update(headers or {})
    req = urllib.request.Request(url, json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


# ------------------------------------------------------------------------------------------------------------------ a fake model
llm_args = fl.parser().parse_args([])
llm = fl.make_server(llm_args)
threading.Thread(target=llm.serve_forever, daemon=True).start()
LLM = f"http://127.0.0.1:{llm.server_port}"

TOOLS = [{"type": "function", "function": {"name": "terminal", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}}}]
KEY = "SYNTH-SELFTEST-KEY-0123456789"
answers = []                 # what the fake Hermes returned (to prove none of it reaches a report)


# ------------------------------------------------------------------------------------------------------------------ a fake Hermes API
class Hermes(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authed(self):
        if self.headers.get("Authorization") != "Bearer " + KEY:
            self.reply(401, {"error": "key"})
            return False
        return True

    def turn(self, text):
        """What Hermes does with a message: a request with a system prompt and tools, a tool loop against the model. -> (status, text, usage, tool_calls)."""
        s = self.server
        msgs = [{"role": "system", "content": "You are a test agent. " + "rules " * 300}, {"role": "user", "content": text}]
        pin = pout = tools = nreq = 0
        for _ in range(80):
            payload = {"model": "synth-fake", "messages": msgs, "tools": TOOLS}
            s.req_log.append((text[:80], len(json.dumps(payload).encode())))      # what THIS side measured: the independent token expectation
            code, raw = post(s.llm + "/v1/chat/completions", payload, timeout=60)
            nreq += 1
            if code != 200:
                return code, "", None, tools
            d = json.loads(raw)
            u = d.get("usage") or {}
            pin += u.get("prompt_tokens", 0)
            pout += u.get("completion_tokens", 0)
            m = d["choices"][0]["message"]
            if m.get("tool_calls"):
                tools += len(m["tool_calls"])
                msgs.append(m)
                for tc in m["tool_calls"]:
                    msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": s.tool_result})
                continue
            if getattr(s, "ping", None):
                post(s.ping, {"jsonrpc": "2.0", "method": "host.get", "params": {}, "id": 1})
            if s.db:
                with s.dblock:
                    c = sqlite3.connect(s.db)
                    cache = pin // 3 if s.cache else 0
                    s.cache_added += cache if ":E0-01]" not in text else 0       # the probe is not a measured turn
                    c.execute("update session_model_usage set api_call_count = api_call_count + ?, input_tokens = input_tokens + ?, output_tokens = output_tokens + ?, "
                              "cache_read_tokens = cache_read_tokens + ?", (nreq, int(pin * s.db_skew), int(pout * s.db_skew), cache))
                    c.execute("update sessions set tool_call_count = tool_call_count + ?", (tools,))
                    c.commit()
                    c.close()
            return 200, m["content"], ({"prompt_tokens": pin, "completion_tokens": pout} if not s.no_usage else None), tools
        return 500, "", None, tools

    def do_POST(self):
        if not self.authed():
            return
        s = self.server
        s.seen.append(self.headers.get("X-Hermes-Session-Id"))
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/v1/chat/completions":
            text = body["messages"][-1]["content"]
            code, out, usage, _ = self.turn(text)
            if code != 200:
                return self.reply(code, {"error": "upstream"})
            answers.append(out)
            r = {"choices": [{"message": {"role": "assistant", "content": out}, "finish_reason": "stop"}]}
            if usage:
                r["usage"] = usage
            return self.reply(200, r)
        if self.path == "/v1/runs":
            rid = "run_%d" % len(s.runs)
            s.runs[rid] = {"status": "running"}

            def work():
                code, out, usage, _ = self.turn(body["input"])
                answers.append(out)
                s.runs[rid] = {"status": "completed" if code == 200 else "failed", "output": out, **({"usage": usage} if usage else {})}
            threading.Thread(target=work, daemon=True).start()
            return self.reply(202, {"run_id": rid})
        self.reply(404, {})

    def do_GET(self):
        if not self.authed():
            return
        rid = self.path.rsplit("/", 1)[-1]
        self.reply(200, self.server.runs.get(rid, {"status": "unknown-run"}))


def start_hermes(db=None, no_usage=False, ping=None, llm=None, tool_result="ok", cache=False, db_skew=1.0):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Hermes)
    srv.daemon_threads = True
    srv.llm, srv.db, srv.no_usage, srv.ping, srv.seen, srv.runs, srv.dblock = llm or LLM, db, no_usage, ping, [], {}, threading.Lock()
    srv.req_log, srv.tool_result, srv.cache, srv.cache_added, srv.db_skew = [], tool_result, cache, 0, db_skew
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


tmp = tempfile.mkdtemp()
keyfile = os.path.join(tmp, "key")
open(keyfile, "w").write(KEY + "\n")
os.environ["SYNTH_SELFTEST_KEY"] = KEY


def write_cfg(name, targets, **extra):
    path = os.path.join(tmp, name)
    json.dump({"targets": targets, "fake_llm": LLM, **extra}, open(path, "w"))
    return path


def target(h, **kw):
    return dict({"api": f"http://127.0.0.1:{h.server_port}", "key_file": keyfile, "roles": ["*"], "no_telegram": True}, **kw)


def expected_input(h):
    """Input tokens the fake model must have estimated for the day's turns: from the request sizes the fake Hermes measured itself (ratio 4.0), probe excluded."""
    return sum(max(1, math.ceil(n / 4.0)) for text, n in h.req_log if ":E0-01]" not in text)


def new_db(path):
    c = sqlite3.connect(path)
    c.execute("create table session_model_usage (session_id text, billing_provider text, model text, api_call_count integer, input_tokens integer, output_tokens integer, cache_read_tokens integer, reasoning_tokens integer)")
    c.execute("create table sessions (id text, tool_call_count integer)")
    c.execute("insert into session_model_usage values ('s','p','m',0,0,0,0,0)")
    c.execute("insert into sessions values ('s',0)")
    c.commit()
    c.close()
    return path


def run(argv):
    return sd.main(argv)


def newest(out, suffix=".json"):
    files = sorted(f for f in os.listdir(out) if f.endswith(suffix))
    return os.path.join(out, files[-1]) if files else None


# ------------------------------------------------------------------------------------------------------------------ 1. scenarios and timeline
profiles = ["burger", "accounting", "shop", "design"]
scens = {p: sd.load_scenario(p) for p in profiles}
for p, sc in scens.items():
    check(f"{p}: loads quiet/normal/busy/idle/runaway exist", all(l in sc["loads"] for l in ("quiet", "normal", "busy", "idle", "runaway")))
    check(f"{p}: every event type of every load has a spec", all(et in sc["events"] for l in sc["loads"].values() for et in l))
    for load in ("quiet", "normal", "busy"):
        tl = sd.build_timeline(sc, load, 7, f"{p}-{load}-a-r1-x")
        got = {}
        for e in tl:
            got[e["etype"]] = got.get(e["etype"], 0) + 1
        want = {k: v for k, v in sc["loads"][load].items() if v}
        check(f"{p}/{load}: event counts equal the volumes", got == want, f"{got} != {want}")
        check(f"{p}/{load}: timeline is sorted", [e["sim_s"] for e in tl] == sorted(e["sim_s"] for e in tl))
check("doc volumes: burger normal E3 = 8, shop busy E3 = 40, design normal E5 = 8, accounting normal E6 = 2",
      scens["burger"]["loads"]["normal"]["E3"] == 8 and scens["shop"]["loads"]["busy"]["E3"] == 40 and scens["design"]["loads"]["normal"]["E5"] == 8
      and scens["accounting"]["loads"]["normal"]["E6"] == 2)
a = sd.build_timeline(scens["shop"], "normal", 3, "shop-normal-a-r1-x")
b = sd.build_timeline(scens["shop"], "normal", 3, "shop-normal-a-r1-x")
c = sd.build_timeline(scens["shop"], "normal", 4, "shop-normal-a-r1-x")
check("same seed, same day; another seed, another day", a == b and [e["sim_s"] for e in a] != [e["sim_s"] for e in c])
check("every message carries its tag", all(sd.TAG_RE.match(st["text"]) for e in a for st in e["steps"]))
idle = sd.build_timeline(scens["burger"], "idle", 1, "burger-idle-a-r1-x")
check("idle day: one cron review and the marker only", sorted(e["etype"] for e in idle) == ["E1", "E10"])
check("burger rush clusters put E3 messages near 11:30 and 18:30", sum(1 for e in sd.build_timeline(scens["burger"], "busy", 1, "burger-busy-a-r1-x")
      if e["etype"] == "E3" and (11 * 3600 + 1800 <= e["sim_s"] <= 11 * 3600 + 3000 or 18 * 3600 + 1800 <= e["sim_s"] <= 18 * 3600 + 3000)) >= 5)
acct = sd.build_timeline(scens["accounting"], "normal", 1, "accounting-normal-a-r1-x")
e3 = [e for e in acct if e["etype"] == "E3"][0]
check("accounting E3 messages carry a document-sized body", len(e3["steps"][0]["text"]) > 5000)

# ------------------------------------------------------------------------------------------------------------------ 1b. every scripted command is a real one
READ_ONLY = ("gateway tareas listar", "hub feed", "gateway status", "gateway zabbix", "gateway postiz listar", "gateway dato")


def valid_command(cmd, proposed):
    """True when the command line is well formed for the real command: tareas through tareas.py's own parser, the others against gateway.py's list of
    commands and the documented usage. `proposed` gateways (postiz, pbs) do not exist yet: only their name is checked."""
    argv = shlex.split(cmd)
    if argv[0] == "hub":
        return len(argv) > 1 and argv[1] in ("feed", "status", "show", "read", "revista")
    if argv[0] != "gateway" or len(argv) < 2:
        return False
    sub = argv[1]
    if any(p.split()[1] == sub for p in proposed):
        return len(argv) > 2
    if sub not in GW_CMDS:
        return False
    try:
        if sub == "tareas":
            if argv[2] == "nueva":
                pos, o = tareas.parse(argv[3:], valued=("--para", "--cuerpo", "--desde"), flags=("--pedido-persona",))
                return len(pos) == 1 and "--para" in o and 0 < len(pos[0]) <= tareas.MAX_TITLE and "\n" not in pos[0]
            if argv[2] == "listar":
                tareas.parse(argv[3:], flags=("--mias", "--todas", "--abiertas", "--cerradas"))
                return True
            return False
        if sub in ("image", "makevideo"):
            return "--" in argv and len(argv) - argv.index("--") - 1 == 2
        if sub == "zabbix":
            return argv[2] in ("groups", "focus", "hosts", "problems", "host", "item", "events")
        if sub == "dato":
            return argv[2] in ("clima", "dolar", "economia", "feriados", "wiki", "aviones", "noticias", "pelis")
        if sub == "song":
            return len(argv) > 2 and not argv[2].startswith("--")
    except Exception:
        return False
    return True


check("gateway.py lists the commands the scripts use (the list is read from the real file)", {"tareas", "image", "makevideo", "zabbix", "song", "dato", "status"} <= GW_CMDS, str(sorted(GW_CMDS)))
check("the validator is not a rubber stamp: a bare tareas nueva, an unknown gateway and a bare image are refused",
      not valid_command("gateway tareas nueva", []) and not valid_command('gateway tareas nueva "x"', []) and not valid_command("gateway nope x", [])
      and not valid_command("gateway image", []) and valid_command('gateway tareas nueva "x" --para bot', []))
for p, sc in scens.items():
    used = {}
    for lname, vols in sc["loads"].items():
        for et, n in vols.items():
            if n:
                used.setdefault(et, []).append(lname)
    bad, dup, nueva_bad = [], [], []
    for et, spec in sc["events"].items():
        if et not in used or spec.get("kind") == "marker":
            continue
        plans = [(i, st.get("plan") or spec.get("plan") or {}) for i, st in enumerate(spec["steps"], 1)] if spec.get("steps") else [(1, spec.get("plan") or {})]
        hop_role = (spec.get("hops") or [{}])[0].get("role", "")
        for i, plan in plans:
            rounds, calls = int(plan.get("rounds") or 0), plan.get("calls") or []
            run_cmds = [fl.fill(calls[k % len(calls)], et, 1, hop_role) for k in range(rounds)] if calls else []
            for c in run_cmds:
                if fl.PLACEHOLDER_RE.search(c) or not valid_command(c, sc.get("proposed_commands", [])):
                    bad.append((et, i, c))
            for c in set(run_cmds):
                if run_cmds.count(c) > 1 and not c.startswith(READ_ONLY):
                    dup.append((et, i, c))
            made = [c for c in run_cmds if " tareas nueva " in c]
            if len(made) != (1 if (spec["kind"] == "task" and i == 1) else 0):
                nueva_bad.append((et, i, made))
            if made and (("--pedido-persona" in made[0]) != (spec["source"] == "owner")):
                nueva_bad.append((et, i, "pedido-persona does not match the source"))
    check(f"{p}: every scripted command is complete and valid (placeholders filled, real parser for tareas)", not bad, str(bad[:3]))
    check(f"{p}: no write command is repeated within a plan (a task or a picture is made once)", not dup, str(dup[:3]))
    check(f"{p}: exactly one `tareas nueva` in the first step of each task event, none elsewhere, --pedido-persona for owner requests", not nueva_bad, str(nueva_bad[:3]))

# ------------------------------------------------------------------------------------------------------------------ 2. safety: refuse before sending
h0 = start_hermes()
out0 = os.path.join(tmp, "out-refuse")
base = ["--profile", "burger", "--load", "quiet", "--out", out0]
rc = run(base + ["--targets", os.path.join(tmp, "nope.json")])
check("no private config: refused (exit 2)", rc == 2)
rc = run(base + ["--targets", write_cfg("c1.json", {"hernik": target(h0)})])
check("a target that is not syn-* or a guest: refused", rc == 2)
rc = run(base + ["--targets", write_cfg("c2.json", {"syn-x": target(h0, telegram=True)})])
check("a target with a Telegram bot, not a test bot: refused", rc == 2)
rc = run(base + ["--targets", write_cfg("c2a.json", {"syn-x": {"api": f"http://127.0.0.1:{h0.server_port}", "key_file": keyfile, "roles": ["*"]}}), "--dry-run"])
check("default-deny: a syn-* target that does not say no_telegram or test_bot is refused (the harness cannot see a bot token)", rc == 2)
rc = run(base + ["--targets", write_cfg("c2b.json", {"guest-x": {"api": f"http://127.0.0.1:{h0.server_port}", "key_file": keyfile, "roles": ["*"], "guest": True}}), "--dry-run"])
check("default-deny: a guest that does not say no_telegram or test_bot is refused too", rc == 2)
rc = run(base + ["--targets", write_cfg("c2c.json", {"syn-x": target(h0, test_bot=True, no_telegram=False)}), "--dry-run"])
check("a marked test bot is accepted (dry run)", rc == 0)
rc = run(base + ["--targets", write_cfg("c2d.json", {"syn-x": target(h0, no_telegram=True, test_bot=True)}), "--dry-run"])
check("no_telegram and test_bot together are contradictory: refused", rc == 2)
rc = run(base + ["--targets", write_cfg("c3.json", {"guest-x": target(h0, guest=True)}), "--dry-run"])
check("a guest with a stated no_telegram is accepted (guest: true)", rc == 0)
rc = run(base + ["--targets", write_cfg("c3b.json", {"other-x": target(h0)}), "--dry-run"])
check("neither syn-* nor guest, even with no_telegram: refused", rc == 2)
rc = run(base + ["--targets", write_cfg("c4.json", {"syn-x": dict(target(h0), api="http://127.0.0.1:1/v1/runs")})])
check("api with a path: refused", rc == 2)
rc = run(base + ["--targets", write_cfg("c5.json", {"syn-x": target(h0, key_file=os.path.join(tmp, "missing"))})])
check("unreadable key: refused", rc == 2)
k_manifest = [{"label": "k", "provider": "p"}]
rc = run(base + ["--mode", "b", "--max-tokens", "100000", "--targets", write_cfg("c6.json", {"syn-x": target(h0)}, keys=k_manifest)])
check("mode b without --approve-spend: refused", rc == 2)
rc = run(base + ["--mode", "b", "--approve-spend", "--max-tokens", "100000", "--targets", write_cfg("c7.json", {"syn-x": target(h0)})])
check("mode b without a key manifest: refused", rc == 2)
rc = run(base + ["--mode", "b", "--approve-spend", "--targets", write_cfg("c7a.json", {"syn-x": target(h0)}, keys=k_manifest)])
check("mode b without a token or dollar budget: refused", rc == 2)
rc = run(base + ["--mode", "b", "--approve-spend", "--max-usd", "1", "--targets", os.path.join(tmp, "c7a.json")])
check("--max-usd without a --price: refused", rc == 2)
rc = run(base + ["--mode", "b", "--approve-spend", "--max-tokens", "100000", "--max-turns", "2", "--targets", os.path.join(tmp, "c7a.json")])
check("mode b with a cap below the planned day: refused unless --allow-truncate", rc == 2)
rc = run(["--profile", "burger", "--load", "runaway", "--out", out0, "--mode", "b", "--approve-spend", "--max-tokens", "100000", "--targets", os.path.join(tmp, "c7a.json")])
check("mode b runaway load without --allow-runaway: refused", rc == 2)
rc = run(["--profile", "burger", "--load", "runaway", "--out", out0, "--mode", "b", "--approve-spend", "--allow-runaway", "--max-tokens", "100000", "--targets", os.path.join(tmp, "c7a.json")])
check("mode b runaway load without a cap_check_cmd: refused", rc == 2)
rc = run(base + ["--targets", write_cfg("c7b.json", {"syn-x": target(h0)}, fake_llm=None)])
check("mode a without fake_llm in the config: refused", rc == 2)
check("unknown profile / load: refused", run(["--profile", "../etc", "--targets", os.path.join(tmp, "c1.json")]) == 2
      and run(["--profile", "burger", "--load", "weekend", "--targets", os.path.join(tmp, "c6.json"), "--out", out0]) == 2)
check("nothing reached the stack during the refusals", h0.seen == [], str(h0.seen))
rc = run(["--profile", "burger", "--load", "normal", "--dry-run", "--targets", os.path.join(tmp, "c6.json"), "--out", out0])
check("--dry-run prints the plan and sends nothing", rc == 0 and h0.seen == [], str(h0.seen))
check("--dry-run wrote no report", not os.path.isdir(out0) or not os.listdir(out0))

# the probe: a stack whose model is NOT the fake is refused after one probe turn, and nothing else is sent
other_fake = fl.make_server(fl.parser().parse_args([]))
threading.Thread(target=other_fake.serve_forever, daemon=True).start()
h_off = start_hermes(llm=f"http://127.0.0.1:{other_fake.server_port}")
out_off = os.path.join(tmp, "out-off")
rc = run(["--profile", "burger", "--load", "normal", "--out", out_off, "--targets", write_cfg("c8.json", {"syn-off": target(h_off)})])
check("mode a: a target whose model is not the fake is refused (exit 2) after the probe, before the day", rc == 2 and len(h_off.seen) == 1 and not os.path.isdir(out_off), f"rc={rc} seen={len(h_off.seen)}")
check("the probe went to the stack's own fake (it saw the E0-01 tag), and the configured fake saw none of it",
      any(":E0-01]" in k for k in other_fake.fake.snapshot()["events"]) and not any(":E0-01]" in k for k in llm.fake.snapshot()["events"]))
rc = run(["--profile", "burger", "--load", "normal", "--out", out_off, "--targets", write_cfg("c8b.json", {"syn-off": target(h_off)}, fake_llm="http://127.0.0.1:1")])
check("mode a: a fake that does not answer is refused before anything is sent to a stack", rc == 2 and len(h_off.seen) == 1)

# ------------------------------------------------------------------------------------------------------------------ 3. a day, mode A, no tareas
zab = stubs.start("zabbix", 0)
h1 = start_hermes(ping=f"http://127.0.0.1:{zab.server_port}/api_jsonrpc.php")
out1 = os.path.join(tmp, "out1")
cfg1 = write_cfg("t1.json", {"syn-burger-main": target(h1, label="burger-all", model_tier="cheap")},
                 stubs={"zabbix": f"http://127.0.0.1:{zab.server_port}"}, keys=[{"label": "test key 1", "provider": "fakeprov", "roles": ["tecnico"]}])
llm.fake.reset()
rc = run(["--profile", "burger", "--load", "normal", "--mode", "a", "--speed", "0", "--seed", "5", "--targets", cfg1, "--out", out1, "--price", "tier=1.0/2.0",
          "--session-header", "X-Hermes-Session-Id"])
rep_path = newest(out1)
rep = json.load(open(rep_path)) if rep_path else {}
T = rep.get("totals", {})
vols = scens["burger"]["loads"]["normal"]
tl1 = sd.build_timeline(scens["burger"], "normal", 5, "x")
steps_total = sum(len(e["steps"]) for e in tl1 if e["kind"] != "marker")
check("day replayed, report and summary written", rc == 0 and rep and os.path.exists(os.path.join(out1, "burger-normal-a-summary.md")))
check("turns add up: sent + skipped = scripted turns", T.get("turns_sent", 0) + T.get("turns_skipped", 0) == steps_total, f"{T} vs {steps_total}")
check("sent = ok + error, no errors on a clean day", T.get("turns_ok", 0) + T.get("turns_error", 0) == T.get("turns_sent") and T.get("turns_error") == 0, str(T))
check("task events skipped for a target without tareas, later steps still sent",
      T.get("skipped_by_reason", {}).get("target_has_no_tareas", 0) == vols["E2"] + vols["E4"] + vols["E7"] and "E7-01.2" in json.dumps(rep["events"]))
snap = llm.fake.snapshot(rep["run_id"])
check("input tokens equal what the fake Hermes's own request sizes imply at 4 characters per token (independent of the fake model's counters)",
      T.get("input_tokens") == expected_input(h1), f"{T.get('input_tokens')} vs {expected_input(h1)}")
check("the fake model's own counters agree with that too", T.get("input_tokens") == sum(r["prompt_tokens"] for r in snap["events"].values()) and T.get("output_tokens") == sum(r["completion_tokens"] for r in snap["events"].values()))
check("events sum to the totals", sum(e["input_tokens"] or 0 for e in rep["events"]) == T["input_tokens"] and sum(e["calls"] or 0 for e in rep["events"]) == T["model_calls"])
check("mode a labels EVERY token figure fake_estimate, whatever file it was read from (and keeps the source)",
      T.get("tokens_methods") == {"fake_estimate": T.get("turns_sent")} and {t["tokens_source"] for e in rep["events"] for t in e["turns"] if t["status"] == "ok"} == {"api"}, str(T.get("tokens_methods")))
e1 = [e for e in rep["events"] if e["id"] == "E1-01"][0]
sc_e1 = scens["burger"]["events"]["E1"]["plan"]
check("E1 scripted as 1 tool round + final text = 2 calls, 1 tool call (the scenario file says rounds = 1)", sc_e1["rounds"] == 1 and e1["calls"] == 2 and e1["tool_calls"] == 1, str(e1["calls"]))
lo, hi = sc_e1["out_tokens"]
check("E1 output tokens fall inside the scenario's own range for the final text (plus a short tool call)", lo <= e1["output_tokens"] <= hi + 40, f"{e1['output_tokens']} not in [{lo}, {hi}+40]")
check("mode a computes no calibration (the 'reported' tokens are the fake's own): it says where the ratio comes from", rep["calibration"] is None and "calibrate" in rep["calibration_note"])
check("mode a report and summary say plainly that dollars are for scale only", any("MODE A" in n for n in rep["notes"]) and "fake model's estimate" in open(os.path.join(out1, "burger-normal-a-summary.md")).read())
sent_events = [e for e in rep["events"] if e["steps_sent"] > 0]
sess = [x for x in h1.seen if x]
check("one session id per EVENT: steps of an event share it (E7 has 2 sent steps, one session)",
      len(sess) == T["turns_sent"] and len(set(sess)) == len(sent_events) < T["turns_sent"], f"{len(set(sess))} sessions, {len(sent_events)} events, {T['turns_sent']} turns")
check("stubs delta counts the calls the fake Hermes made", rep["stubs_delta"]["zabbix"]["calls"].get("host.get") == T["turns_sent"], str(rep["stubs_delta"]))
check("projection fills skipped event types from the first-order table and says so",
      {"E2", "E4", "E7"} <= set(rep["projection_from_unit_costs"]["normal"]["assumed_event_types"]))
pn = rep["projection_from_unit_costs"]["normal"]
check("dollar arithmetic: tier 1.0/2.0 per million", abs(pn["usd"]["tier"] - round(pn["input_tokens"] / 1e6 + pn["output_tokens"] / 1e6 * 2, 3)) < 0.002, str(pn))
check("month = 4 quiet + 22 normal + 4 busy", rep["projection_from_unit_costs"]["month_4q_22n_4b"]["input_tokens"] ==
      4 * rep["projection_from_unit_costs"]["quiet"]["input_tokens"] + 22 * pn["input_tokens"] + 4 * rep["projection_from_unit_costs"]["busy"]["input_tokens"])
check("peak awake bots and capacity are computed", rep["awake"]["peak_concurrent_awake_bots"] >= 1 and rep["capacity"]["businesses_by_vm_gb"]["16"]["f_1.0"] >= 1)
check("key manifest has labels only", rep["key_manifest"] == [{"label": "test key 1", "provider": "fakeprov", "used_by_roles": ["tecnico"]}])
check("default caps come from the plan: planned 20 + margin, nothing truncated", T["planned_turns"] == T["turns_sent"] + 0 and T["cap_turns"] == math.ceil(T["planned_turns"] * 1.2) + 3 and T["turns_skipped"] == vols["E2"] + vols["E4"] + vols["E7"], str(T))
check("awake figures say how many steps were assumed (the skipped task steps)", rep["awake"]["steps_assumed"] == vols["E2"] + vols["E4"] + vols["E7"] and any("ASSUMED" in w for w in rep["warnings"]), str(rep["awake"]))

# ------------------------------------------------------------------------------------------------------------------ 4. no text, no key, no stack name
blob = open(rep_path).read() + open(os.path.join(out1, "burger-normal-a-summary.md")).read()
templates = [t for spec in scens["burger"]["events"].values() for t in spec.get("templates", []) + [s.get("template", "") for s in spec.get("steps", [])] if len(t) > 20]
check("report and summary hold no message template", not any(t[:24] in blob for t in templates))
check("no tag, no key, no stack name, no address in the report", "[SYN:" not in blob and KEY not in blob and "syn-burger-main" not in blob and "127.0.0.1" not in blob)
check("no answer text of the stack in the report", answers and not any(a[:30] in blob for a in answers if a))
check("report keys carry only sizes and counts (no 'text' or 'content' field)", '"text"' not in blob and '"content"' not in blob)
mode = oct(os.stat(rep_path).st_mode & 0o777)
check("report file is private (0600)", mode == "0o600", mode)

# ------------------------------------------------------------------------------------------------------------------ 5. tareas target, runs endpoint, estimated tokens, state.db
db = new_db(os.path.join(tmp, "state.db"))
h2 = start_hermes(db=db, no_usage=True)
out2 = os.path.join(tmp, "out2")
cfg2 = write_cfg("t2.json", {"syn-shop-main": target(h2, label="shop-all", tareas=True, state_db=db)})
llm.fake.reset()
rc = run(["--profile", "shop", "--load", "quiet", "--mode", "a", "--speed", "0", "--endpoint", "runs", "--poll-s", "0.05", "--targets", cfg2, "--out", out2])
r2 = json.load(open(newest(out2)))
T2 = r2["totals"]
check("runs endpoint with tareas target: nothing skipped, no errors", rc == 0 and T2["turns_skipped"] == 0 and T2["turns_error"] == 0, str(T2))
check("state.db difference is the token source when present (labelled fake_estimate in mode a, source state_db)",
      T2["tokens_methods"] == {"fake_estimate": T2["turns_sent"]} and {t["tokens_source"] for e in r2["events"] for t in e["turns"] if t["status"] == "ok"} == {"state_db"}, str(T2["tokens_methods"]))
check("state.db token sums equal the request sizes the fake Hermes measured (independent), not only the fake's counters", T2["input_tokens"] == expected_input(h2), f"{T2['input_tokens']} vs {expected_input(h2)}")
e2 = [e for e in r2["events"] if e["etype"] == "E2"][0]
check("task event E2: 4 scripted tool rounds + final = 5 calls, 4 tool calls, depth planned 3 (the shop chain)", e2["calls"] == 5 and e2["tool_calls"] == 4 and e2["depth_planned"] == 3, str(e2))
check("all steps of the day were sent, so nothing in the awake model is assumed", r2["awake"]["steps_assumed"] == 0)
check("task events were sent and there is no waker journal: the report says hops were not observed", any("hops are not observed" in w for w in r2["warnings"]), str(r2["warnings"]))
check("tool results that are fine are not counted as failures", T2["tool_errors"] == 0)

# a stack where the tool results are usage errors: counted, and a task event that created no task is reported
h2e = start_hermes(tool_result="Uso: gateway tareas listar [--mias|--todas] | nueva \"TITULO\" --para NOMBRE")
out2e = os.path.join(tmp, "out2e")
run(["--profile", "shop", "--load", "quiet", "--targets", write_cfg("t2e.json", {"syn-shop-err": target(h2e, tareas=True)}), "--out", out2e])
r2e = json.load(open(newest(out2e)))
check("every scripted tool call whose result is a usage error is counted (tool_errors = tool_calls)", r2e["totals"]["tool_errors"] == r2e["totals"]["tool_calls"] > 0, str(r2e["totals"]))
check("the report warns about failing tool results and about task events that created no task",
      any("usage error" in w for w in r2e["warnings"]) and any("no task was created" in w for w in r2e["warnings"]), str(r2e["warnings"]))

# a waker journal with no wake at all: task events were sent, no hop happened
nowake = os.path.join(tmp, "waker-empty.txt")
open(nowake, "w").write("")
out2w = os.path.join(tmp, "out2w")
run(["--profile", "shop", "--load", "quiet", "--targets", write_cfg("t2w.json", {"syn-shop-w": target(start_hermes(), tareas=True)}, logs={"waker": nowake}), "--out", out2w])
check("a waker journal that shows no wake while task events were sent warns that no hop happened",
      any("no hop happened" in w for w in json.load(open(newest(out2w)))["warnings"]))

h3 = start_hermes(no_usage=True)
out3 = os.path.join(tmp, "out3")
llm.fake.reset()
rc = run(["--profile", "design", "--load", "quiet", "--targets", write_cfg("t3.json", {"syn-design": target(h3, tareas=True)}), "--out", out3])
r3 = json.load(open(newest(out3)))
check("no usage from the API: the source is the fake's request estimate (fake_estimate in mode a), tokens match the measured request sizes",
      r3["totals"]["tokens_methods"] == {"fake_estimate": r3["totals"]["turns_sent"]} and {t["tokens_source"] for e in r3["events"] for t in e["turns"] if t["status"] == "ok"} == {"request_estimate"}
      and r3["totals"]["input_tokens"] == expected_input(h3), str(r3["totals"]["tokens_methods"]))
check("design E5 declares GPU seconds on the approved step", r3["totals"]["gpu_seconds_declared"] == sum(
    e["gpu_seconds_declared"] for e in r3["events"] if e["status"] in ("ok", "error")) and r3["totals"]["gpu_seconds_declared"] >= 45)

# profile matching: a target made for another profile never gets a turn
h_shop, h_burg = start_hermes(), start_hermes()
out_pf = os.path.join(tmp, "out-pf")
run(["--profile", "burger", "--load", "quiet", "--out", out_pf, "--targets", write_cfg("tpf.json", {"syn-for-shop": target(h_shop, label="shop-only", profile="shop"),
                                                                                                   "syn-for-burger": target(h_burg, label="burger-only", profile="burger")})])
rpf = json.load(open(newest(out_pf)))
check("a target with profile shop gets only the probe in a burger run; the burger target gets the day",
      len(h_shop.seen) == 1 and len(h_burg.seen) == 1 + rpf["totals"]["turns_sent"] and rpf["totals"]["turns_sent"] == 4, f"{len(h_shop.seen)} {len(h_burg.seen)}")

# key_env instead of key_file
out_ke = os.path.join(tmp, "out-ke")
h_ke = start_hermes()
rc = run(["--profile", "burger", "--load", "idle", "--out", out_ke, "--targets", write_cfg("tke.json", {"syn-ke": {"api": f"http://127.0.0.1:{h_ke.server_port}", "key_env": "SYNTH_SELFTEST_KEY", "roles": ["*"], "no_telegram": True}})])
check("key_env: the key is read from the named variable", rc == 0 and json.load(open(newest(out_ke)))["totals"]["turns_error"] == 0)

# cache reads are carried, and a skewed state.db is reported against the API usage
db_c = new_db(os.path.join(tmp, "state-cache.db"))
h_c = start_hermes(db=db_c, cache=True)
out_c = os.path.join(tmp, "out-cache")
run(["--profile", "burger", "--load", "quiet", "--out", out_c, "--price", "p=1.0/2.0/0.1", "--targets", write_cfg("tc.json", {"syn-cache": target(h_c, state_db=db_c)})])
rc_ = json.load(open(newest(out_c)))
check("cache_read_tokens are carried through the row, the totals and the projection", rc_["totals"]["cache_read_tokens"] == h_c.cache_added > 0
      and rc_["projection_from_unit_costs"]["normal"]["cache_read_tokens"] > 0 and any("cache_read_tokens" in w for w in rc_["warnings"]), str(rc_["totals"]))
check("usd_of: cache read at its own price, input excluding or including the cache (hand-calculated 3.05 and 2.55)",
      abs(sd.usd_of(10**6, 10**6, 5 * 10**5, (1.0, 2.0, 0.1), False) - 3.05) < 1e-9 and abs(sd.usd_of(10**6, 10**6, 5 * 10**5, (1.0, 2.0, 0.1), True) - 2.55) < 1e-9
      and abs(sd.usd_of(10**6, 0, 10**6, (1.0, 2.0, None), False) - 2.0) < 1e-9)
db_s = new_db(os.path.join(tmp, "state-skew.db"))
h_s = start_hermes(db=db_s, db_skew=0.4)
out_s = os.path.join(tmp, "out-skew")
run(["--profile", "burger", "--load", "quiet", "--out", out_s, "--targets", write_cfg("ts.json", {"syn-skew": target(h_s, state_db=db_s)})])
check("a state.db that disagrees with the API usage by more than the tolerance is warned about", any("differ by more than" in w for w in json.load(open(newest(out_s)))["warnings"]))

# ------------------------------------------------------------------------------------------------------------------ 6. caps, kill file, failures
h4 = start_hermes()
out4 = os.path.join(tmp, "out4")
cfg4 = write_cfg("t4.json", {"syn-cap": target(h4)})
llm.fake.reset()
run(["--profile", "burger", "--load", "busy", "--targets", cfg4, "--out", out4, "--max-turns", "5"])
r4 = json.load(open(newest(out4)))
check("--max-turns is a hard cap, and the truncation is announced as a warning", r4["totals"]["turns_sent"] == 5 and r4["totals"]["skipped_by_reason"].get("turn_cap", 0) > 0
      and any("truncated" in w for w in r4["warnings"]), str(r4["totals"]))
out4b = os.path.join(tmp, "out4b")
run(["--profile", "burger", "--load", "busy", "--targets", write_cfg("t4b.json", {"syn-cap": target(h4, label="only")}), "--out", out4b, "--max-turns-per-bot", "3"])
r4b = json.load(open(newest(out4b)))
check("--max-turns-per-bot is a hard cap on a target", r4b["totals"]["turns_sent"] == 3 and r4b["totals"]["skipped_by_reason"].get("turn_cap", 0) > 0, str(r4b["totals"]))
n_before = len(h4.seen)
out5 = os.path.join(tmp, "out5")
os.makedirs(out5)
open(os.path.join(out5, "KILL"), "w").close()
marker = os.path.join(tmp, "killed")
run(["--profile", "burger", "--load", "normal", "--targets", write_cfg("t5.json", {"syn-cap": target(h4)}, on_kill_cmd=["touch", marker]), "--out", out5])
r5 = json.load(open(newest(out5)))
check("kill file stops the replay before any turn (only the probe went), runs on_kill_cmd once", len(h4.seen) == n_before + 1 and r5["totals"]["turns_sent"] == 0 and r5["stopped"] == "kill file" and os.path.exists(marker), str(r5["stopped"]))

# the kill file is polled while waiting for the next event: a slow real-time replay ends within seconds and on_kill_cmd runs at once
out5b = os.path.join(tmp, "out5b")
os.makedirs(out5b)
marker2 = os.path.join(tmp, "killed2")
threading.Timer(1.5, lambda: open(os.path.join(out5b, "KILL"), "w").close()).start()
t_slow = time.time()
run(["--profile", "burger", "--load", "normal", "--speed", "1", "--targets", write_cfg("t5b.json", {"syn-cap": target(h4)}, on_kill_cmd=["touch", marker2]), "--out", out5b])
r5b = json.load(open(newest(out5b)))
check("kill during a long wait (--speed 1, next event hours away): the run ends in seconds, on_kill_cmd has run, the partial report is written",
      time.time() - t_slow < 20 and r5b["stopped"] == "kill file" and os.path.exists(marker2) and r5b["totals"]["turns_sent"] >= 1, f"{time.time() - t_slow:.1f}s {r5b['stopped']}")

# Ctrl-C: a partial report is still written
out5c = os.path.join(tmp, "out5c")
threading.Timer(1.5, _thread.interrupt_main).start()
run(["--profile", "burger", "--load", "normal", "--speed", "1", "--targets", write_cfg("t5c.json", {"syn-cap": target(h4)}, on_kill_cmd=["touch", os.path.join(tmp, "killed3")]), "--out", out5c])
r5c = json.load(open(newest(out5c)))
check("Ctrl-C keeps the counts of a partial run (report written, stopped says interrupted, on_kill_cmd run)", r5c["stopped"].startswith("interrupted") and r5c["totals"]["turns_sent"] >= 1
      and os.path.exists(os.path.join(tmp, "killed3")))

# cap_check_cmd: before the first turn and every N turns; a non-zero exit stops the run before a turn
cc_log = os.path.join(tmp, "cc.log")
out6c = os.path.join(tmp, "out6c")
run(["--profile", "burger", "--load", "normal", "--cap-check-every", "5", "--max-turns", "11", "--targets",
     write_cfg("t6c.json", {"syn-cc": target(h4)}, cap_check_cmd=["sh", "-c", f"echo x >> {cc_log}"]), "--out", out6c])
r6c = json.load(open(newest(out6c)))
check("cap_check_cmd runs before the first turn and every 5 turns (turns 1, 5, 10 of 11 sent)", r6c["totals"]["turns_sent"] == 11 and open(cc_log).read().count("x") == 3, str(open(cc_log).read().count("x")))
out6d = os.path.join(tmp, "out6d")
n_h4 = len(h4.seen)
run(["--profile", "burger", "--load", "normal", "--targets", write_cfg("t6d.json", {"syn-cc": target(h4)}, cap_check_cmd=["sh", "-c", "exit 1"], on_kill_cmd=["touch", os.path.join(tmp, "killed4")]), "--out", out6d])
r6d = json.load(open(newest(out6d)))
check("a failing cap_check_cmd stops the run before the first turn and runs on_kill_cmd", r6d["totals"]["turns_sent"] == 0 and "cap_check_cmd exited 1" in r6d["stopped"]
      and len(h4.seen) == n_h4 + 1 and os.path.exists(os.path.join(tmp, "killed4")), str(r6d["stopped"]))

fl_args = fl.parser().parse_args(["--fail-mode", "429", "--fail-every", "2"])
failing = fl.make_server(fl_args)
threading.Thread(target=failing.serve_forever, daemon=True).start()
h6 = start_hermes()
h6.llm = f"http://127.0.0.1:{failing.server_port}"
out6 = os.path.join(tmp, "out6")
run(["--profile", "burger", "--load", "quiet", "--targets", write_cfg("t6.json", {"syn-fail": target(h6)}, fake_llm=h6.llm), "--out", out6])
r6 = json.load(open(newest(out6)))
check("a provider 429 shows as an error code per turn and counts, the day goes on", 0 < r6["totals"]["turns_error"] and r6["totals"]["turns_sent"] == 4
      and r6["totals"]["errors_by_code"].get("http_429") == r6["totals"]["turns_error"], str(r6["totals"]["errors_by_code"]))
cap_args = fl.parser().parse_args(["--max-calls", "3"])
capped = fl.make_server(cap_args)
threading.Thread(target=capped.serve_forever, daemon=True).start()
codes = [post(f"http://127.0.0.1:{capped.server_port}/v1/chat/completions", {"messages": [{"role": "user", "content": "hi"}]})[0] for _ in range(5)]
check("fake model call cap: 429 past the cap, counted", codes == [200, 200, 200, 429, 429] and capped.fake.totals["cap_refused"] == 2, str(codes))
dead = start_hermes()
out7 = os.path.join(tmp, "out7")
rc = run(["--profile", "burger", "--load", "idle", "--targets", write_cfg("t7.json", {"syn-dead": target(dead, api="http://127.0.0.1:1")}), "--out", out7])
check("mode a: an unreachable stack is refused by the probe (exit 2), no day, no report", rc == 2 and not os.path.isdir(out7))
rc = run(["--profile", "burger", "--load", "idle", "--mode", "b", "--approve-spend", "--max-tokens", "1000", "--targets",
          write_cfg("t7b.json", {"syn-dead": target(dead, api="http://127.0.0.1:1")}, keys=k_manifest, fake_llm=None), "--out", out7])
check("an unreachable stack is a connect error in the report (mode b, nothing spent: the budget does not stop on it), not a crash",
      rc == 0 and json.load(open(newest(out7)))["totals"]["errors_by_code"] == {"connect": 1})

# ------------------------------------------------------------------------------------------------------------------ 6b. mode b: budget, happy path, runaway, calibration
db_b = new_db(os.path.join(tmp, "state-b.db"))
h_b = start_hermes(db=db_b)
out_b = os.path.join(tmp, "out-b")
cfg_b = write_cfg("tb.json", {"syn-real": target(h_b, state_db=db_b, label="real-1")}, keys=k_manifest)
rc = run(["--profile", "shop", "--load", "quiet", "--mode", "b", "--approve-spend", "--max-tokens", "10000000", "--price", "tier=1.0/2.0", "--targets", cfg_b, "--out", out_b,
          "--endpoint", "runs", "--poll-s", "0.05"])
rb = json.load(open(newest(out_b)))
check("mode b happy path: exit 0, reported_state_db labels, budget accounted (the fake is configured here, so it also warns that it saw the events)",
      rc == 0 and rb["mode"] == "b" and rb["totals"]["tokens_methods"] == {"reported_state_db": rb["totals"]["turns_sent"]} and rb["budget"]["tokens_used"] ==
      rb["totals"]["input_tokens"] + rb["totals"]["output_tokens"] + rb["totals"]["cache_read_tokens"] > 0 and any("fake model saw" in w for w in rb["warnings"]), str(rb["totals"]))
check("mode b report carries no calibration of its own", rb["calibration"] is None)

# --calibrate: offline join, hand-calculated expectation
rep_a = {"mode": "a", "profile": "p", "load": "l", "seed": 1, "events": [{"etype": "E3", "turns": [
    {"tag_id": "E3-01", "request_chars": 8000, "model_calls": 2}, {"tag_id": "E3-02", "request_chars": 3000, "model_calls": 1}]}]}
rep_b = {"mode": "b", "profile": "p", "load": "l", "seed": 1, "events": [{"etype": "E3", "turns": [
    {"tag_id": "E3-01", "input_tokens": 2000, "model_calls": 2, "tokens_method": "reported_state_db"},
    {"tag_id": "E3-02", "input_tokens": 1000, "model_calls": 1, "tokens_method": "reported_api"},
    {"tag_id": "E3-03", "input_tokens": 500, "model_calls": 1, "tokens_method": "reported_api"}]}]}
cal = sd.calibrate(rep_a, rep_b)
check("calibrate: (8000/2)/(2000/2) = 4.0 and (3000/1)/(1000/1) = 3.0, a turn present in one report only is left out: p50 3.5, n 2",
      cal["chars_per_token_p50"] == 3.5 and cal["n_turns"] == 2 and cal["by_event_type"]["E3"]["n"] == 2, str(cal))
bad_seed = False
try:
    sd.calibrate(rep_a, dict(rep_b, seed=2))
except sd.Refuse:
    bad_seed = True
check("calibrate refuses reports of a different seed (not the same tags), and a mode b report first", bad_seed)
pa = os.path.join(tmp, "cal-a.json")
pb = os.path.join(tmp, "cal-b.json")
json.dump(rep_a, open(pa, "w"))
json.dump(rep_b, open(pb, "w"))
check("--calibrate on the command line prints the ratio (exit 0) and needs no config", run(["--calibrate", pa, pb]) == 0 and run(["--calibrate", pb, pa]) == 2)
out_a2 = os.path.join(tmp, "out-a2")
db_a2 = new_db(os.path.join(tmp, "state-a2.db"))
h_a2 = start_hermes(db=db_a2)
run(["--profile", "shop", "--load", "quiet", "--mode", "a", "--endpoint", "runs", "--poll-s", "0.05", "--targets", write_cfg("ta2.json", {"syn-real": target(h_a2, state_db=db_a2, label="real-1")}), "--out", out_a2])
cal2 = sd.calibrate(json.load(open(newest(out_a2))), rb)
check("calibrate on a real mode a and mode b pair of the same profile, load and seed: a ratio near 4 (the two runs differ only in label)", cal2["n_turns"] > 0 and abs(cal2["chars_per_token_p50"] - 4.0) < 0.5, str(cal2))

# budgets stop the run
db_t = new_db(os.path.join(tmp, "state-t.db"))
h_t = start_hermes(db=db_t)
out_t = os.path.join(tmp, "out-tok")
run(["--profile", "burger", "--load", "normal", "--mode", "b", "--approve-spend", "--max-tokens", "1", "--allow-truncate", "--targets", write_cfg("tt.json", {"syn-real": target(h_t, state_db=db_t)}, keys=k_manifest, on_kill_cmd=["touch", os.path.join(tmp, "killed5")]), "--out", out_t])
rt = json.load(open(newest(out_t)))
check("--max-tokens: the first turn runs, the next does not, the run stops and on_kill_cmd runs", rt["totals"]["turns_sent"] == 1 and rt["stopped"].startswith("token budget")
      and os.path.exists(os.path.join(tmp, "killed5")), str(rt["stopped"]))
out_u = os.path.join(tmp, "out-usd")
run(["--profile", "burger", "--load", "normal", "--mode", "b", "--approve-spend", "--max-usd", "0.000001", "--price", "dear=100/200", "--price", "cheap=1/2", "--targets",
     os.path.join(tmp, "tt.json"), "--out", out_u])
ru = json.load(open(newest(out_u)))
check("--max-usd stops at the dearest --price", ru["totals"]["turns_sent"] == 1 and ru["stopped"].startswith("dollar budget"), str(ru["stopped"]))
h_n = start_hermes(no_usage=True)
out_n = os.path.join(tmp, "out-nofig")
run(["--profile", "burger", "--load", "normal", "--mode", "b", "--approve-spend", "--max-tokens", "10000000", "--targets", write_cfg("tn.json", {"syn-real": target(h_n)}, keys=k_manifest), "--out", out_n])
rn = json.load(open(newest(out_n)))
check("a mode b turn that reports no token figure stops the run (the budget cannot be enforced)", rn["totals"]["turns_sent"] == 1 and "no token figure" in rn["stopped"], str(rn["stopped"]))

# the runaway load: allowed only with the flag and a cap check, which runs before the E8 turn
cc2 = os.path.join(tmp, "cc2.log")
db_r = new_db(os.path.join(tmp, "state-r.db"))
h_r = start_hermes(db=db_r)
out_r = os.path.join(tmp, "out-run")
rc = run(["--profile", "burger", "--load", "runaway", "--mode", "b", "--approve-spend", "--allow-runaway", "--max-tokens", "50000000", "--cap-check-every", "1000", "--targets",
          write_cfg("tr.json", {"syn-real": target(h_r, state_db=db_r)}, keys=k_manifest, cap_check_cmd=["sh", "-c", f"echo x >> {cc2}"]), "--out", out_r])
rr = json.load(open(newest(out_r)))
e8 = [e for e in rr["events"] if e["etype"] == "E8"][0]
check("runaway load in mode b: the E8 turn ran, and the cap check ran before the first turn and again right before E8 (2 runs with --cap-check-every 1000)",
      rc == 0 and e8["steps_sent"] == 1 and open(cc2).read().count("x") == 2, f"{open(cc2).read().count('x')} {rr['stopped']}")

# --continue-e3: the E3 turns of a role share one session
out_ce = os.path.join(tmp, "out-ce")
h_ce = start_hermes()
run(["--profile", "burger", "--load", "normal", "--seed", "5", "--continue-e3", "--targets", write_cfg("tce.json", {"syn-ce": target(h_ce)}), "--out", out_ce])
roles_e3 = {e["role"] for e in tl1 if e["etype"] == "E3"}
sess_ce = [x for x in h_ce.seen if x]
check("--continue-e3: all E3 turns of a role share one session id (one per role), other events keep one per event",
      len({x for x in sess_ce if "-owner-" in x}) == len(roles_e3) and len([x for x in sess_ce if "-owner-" in x]) == vols["E3"], f"{len({x for x in sess_ce if '-owner-' in x})} vs {len(roles_e3)}")

# compressed clock (threads, overlap) and repeats
h8 = start_hermes()
out8 = os.path.join(tmp, "out8")
t8 = time.time()
run(["--profile", "burger", "--load", "quiet", "--speed", "100000", "--repeats", "2", "--seed", "9", "--workers", "4", "--targets", write_cfg("t8.json", {"syn-fast": target(h8)}), "--out", out8])
reps8 = [json.load(open(os.path.join(out8, f))) for f in sorted(os.listdir(out8)) if f.endswith(".json")]
check("--speed compresses the clock: two repeats, distinct run ids, every turn sent, quickly", len(reps8) == 2 and len({r["run_id"] for r in reps8}) == 2
      and all(r["totals"]["turns_sent"] == 4 and r["totals"]["turns_error"] == 0 for r in reps8) and time.time() - t8 < 20, str([r["totals"] for r in reps8]))
check("repeats use consecutive seeds (different days)", reps8[0]["seed"] != reps8[1]["seed"])
smd = open(os.path.join(out8, "burger-quiet-a-summary.md")).read()
check("summary gives p50 with p10 and p90 over the repeats", "| turns sent | 4.0 | 4.0 | 4.0 |" in smd or "| turns sent | 4 | 4 | 4 |" in smd, smd[:600])
pj = [r["projection_from_unit_costs"]["normal"]["input_tokens"] for r in reps8]
check("the summary's projection table shows p50 and the spread over the repeats (not the last run only)",
      f"{sd.pct(pj, .5):g}" in smd and (len(set(pj)) == 1 or f"({sd.pct(pj, .1):g} to {sd.pct(pj, .9):g})" in smd), smd[smd.find("## Projection"):][:500])

# ------------------------------------------------------------------------------------------------------------------ 7. the fake model by itself
url = f"http://127.0.0.1:{llm.server_port}/v1/chat/completions"
tag = "[SYN:burger-normal-a-r1-zz:E2-01]"
msgs = [{"role": "user", "content": tag + " go"}]
code, raw = post(url, {"messages": msgs, "tools": TOOLS})
d = json.loads(raw)
check("tagged request: scripted tool call with valid JSON arguments and usage", code == 200 and d["choices"][0]["finish_reason"] == "tool_calls"
      and json.loads(d["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])["command"].startswith("hub feed") and d["usage"]["prompt_tokens"] > 0)
code, raw = post(url, {"messages": msgs, "tools": []})
check("no shell tool offered: text answer, tool_missing counted", json.loads(raw)["choices"][0]["finish_reason"] == "stop" and llm.fake.totals["tool_missing"] >= 1)
code, raw = post(url, {"messages": [{"role": "user", "content": "just a title please"}]})
check("untagged request: short canned answer, counted as untagged", json.loads(raw)["choices"][0]["message"]["content"] and llm.fake.untagged["calls"] >= 1)
req = urllib.request.Request(url, json.dumps({"messages": msgs, "tools": TOOLS, "stream": True, "stream_options": {"include_usage": True}}).encode(), headers={"Content-Type": "application/json"})
sse = urllib.request.urlopen(req, timeout=10).read().decode()
chunks = [json.loads(l[6:]) for l in sse.splitlines() if l.startswith("data: {")]
args_joined = "".join(tc["function"].get("arguments", "") for c in chunks for ch in c["choices"] for tc in ch["delta"].get("tool_calls", []))
check("streamed tool call: arguments in pieces join to valid JSON, usage in the stream, [DONE] closes", json.loads(args_joined)["command"].startswith("hub feed")
      and any(c.get("usage") for c in chunks) and sse.rstrip().endswith("[DONE]"))
so_args = fl.parser().parse_args(["--usage", "stream_opt"])
so = fl.make_server(so_args)
threading.Thread(target=so.serve_forever, daemon=True).start()


def stream_usage(body):
    r = urllib.request.Request(f"http://127.0.0.1:{so.server_port}/v1/chat/completions", json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    cs = [json.loads(l[6:]) for l in urllib.request.urlopen(r, timeout=10).read().decode().splitlines() if l.startswith("data: {")]
    return any(c.get("usage") for c in cs)


m1 = [{"role": "user", "content": "hello"}]
check("usage in a stream only with stream_options.include_usage when --usage stream_opt",
      not stream_usage({"messages": m1, "stream": True}) and stream_usage({"messages": m1, "stream": True, "stream_options": {"include_usage": True}}))
ba = fl.make_server(fl.parser().parse_args(["--fail-mode", "bad_args", "--fail-every", "1"]))
threading.Thread(target=ba.serve_forever, daemon=True).start()
code, raw = post(f"http://127.0.0.1:{ba.server_port}/v1/chat/completions", {"messages": msgs, "tools": TOOLS})
try:
    json.loads(json.loads(raw)["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
    bad = False
except ValueError:
    bad = True
check("--fail-mode bad_args: tool-call arguments that are not JSON", bad)
nu = fl.make_server(fl.parser().parse_args(["--fail-mode", "no_usage", "--fail-every", "1"]))
threading.Thread(target=nu.serve_forever, daemon=True).start()
code, raw = post(f"http://127.0.0.1:{nu.server_port}/v1/chat/completions", {"messages": m1})
check("--fail-mode no_usage: an answer without usage", "usage" not in json.loads(raw))
a1 = [json.loads(post(url, {"messages": [{"role": "user", "content": "[SYN:burger-normal-a-r1-yy:E3-01] x"}]})[1])["choices"][0]["message"]["content"] for _ in range(2)]
check("same request, same scripted answer (deterministic)", a1[0] == a1[1])
lg = os.path.join(tmp, "fake.log")
lg_srv = fl.make_server(fl.parser().parse_args(["--log", lg]))
threading.Thread(target=lg_srv.serve_forever, daemon=True).start()
post(f"http://127.0.0.1:{lg_srv.server_port}/v1/chat/completions", {"messages": [{"role": "user", "content": "[SYN:burger-normal-a-r1-q:E3-01] SECRET-WORDS"}]})
logtxt = open(lg).read()
check("fake model log: sizes and a tag hash only, no text and no tag", "SECRET-WORDS" not in logtxt and "[SYN" not in logtxt and '"chars"' in logtxt)


def round_msgs(tag, k, tool_content="ok"):
    """The messages Hermes would send after k tool rounds of a turn."""
    ms = [{"role": "user", "content": tag + " go"}]
    for i in range(k):
        ms.append({"role": "assistant", "content": None, "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": "terminal", "arguments": "{}"}}]})
        ms.append({"role": "tool", "tool_call_id": f"c{i}", "content": tool_content})
    return ms


def command_at(srv_url, tag, k):
    code, raw = post(srv_url + "/v1/chat/completions", {"messages": round_msgs(tag, k), "tools": TOOLS})
    return json.loads(json.loads(raw)["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])["command"]


check("placeholders are filled by the fake: round 4 of advisory E2-03 files a task titled with the event number for the first hop's role",
      command_at(LLM, "[SYN:burger-normal-a-r1-zz:E2-03]", 3) == 'gateway tareas nueva "Synthetic advisory task 3" --para tecnico')
peer_srv = fl.make_server(fl.parser().parse_args(["--peer", "tecnico=bot-tec"]))
threading.Thread(target=peer_srv.serve_forever, daemon=True).start()
check("--peer ROLE=BOT maps a role to the bot's name on the board",
      command_at(f"http://127.0.0.1:{peer_srv.server_port}", "[SYN:burger-normal-a-r1-zz:E2-03]", 3).endswith("--para bot-tec"))
check("a hand-down by the owner is filed as a person's request, for the next rung", command_at(LLM, "[SYN:shop-normal-a-r1-zz:E4-02]", 1) ==
      'gateway tareas nueva "Synthetic hand-down 2" --para tecnico --pedido-persona')
tf = fl.make_server(fl.parser().parse_args([]))
threading.Thread(target=tf.serve_forever, daemon=True).start()
TF = f"http://127.0.0.1:{tf.server_port}/v1/chat/completions"
for n_case, (label, content, want) in enumerate((("a usage line", "Uso: gateway tareas listar | nueva", 1), ("english usage", "usage: x", 1), ("a non-zero exit code", '{"output": "x", "exit_code": 2}', 1),
                             ("command not found", "sh: gateway: command not found", 1), ("a zero exit code", '{"output": "Listo: tarea #4", "exit_code": 0}', 0), ("plain output", "Listo: tarea #4 creada", 0)), 1):
    tag = f"[SYN:burger-normal-a-r1-tf:E3-{n_case:02d}]"
    post(TF, {"messages": round_msgs(tag, 1, content), "tools": TOOLS})
    got = tf.fake.snapshot()["events"][tag]["tool_errors"]
    check(f"tool result is read: {label} counts {want} tool error(s)", got == want, str(got))
tag = "[SYN:burger-normal-a-r1-tf:E3-99]"
bad_then_ok = round_msgs(tag, 2)
bad_then_ok[2]["content"] = "Uso: x"
post(TF, {"messages": bad_then_ok, "tools": TOOLS})
check("only the NEWEST tool results are counted (a replayed history is not counted twice)", tf.fake.snapshot()["events"][tag]["tool_errors"] == 0)

# ------------------------------------------------------------------------------------------------------------------ 8. awake model, capacity, scanners
ev = lambda i, role, s, steps_after=0: {"id": i, "etype": "E3", "kind": "turn", "sim_s": s, "steps": [{"tag_id": i, "after_s": 0, "role": role}], "hops": [], "ext": {}}
evs = [ev("E3-01", "a", 7 * 3600), ev("E3-02", "a", 7 * 3600 + 300), ev("E3-03", "a", 15 * 3600), ev("E3-04", "b", 7 * 3600 + 100)]
rows = {e["id"]: {"status": "ok", "seconds": 10.0} for e in evs}
aw = sd.awake_model(evs, rows, 20.0)
# cluster 1 of a: [25200, 25510] -> (310 + 20 + 600) / 60 = 15.5 min; cluster 2: (10 + 20 + 600) / 60 = 10.5 -> 26.0
check("awake minutes: clusters of activity less than 10 minutes apart, span + boot + idle", aw["per_role"]["a"] == {"wakes": 2, "awake_minutes": 26.0}, str(aw["per_role"]))
check("peak concurrent awake bots counts overlapping bots", aw["peak_concurrent_awake_bots"] == 2, str(aw))
check("capacity table matches SYNTHETIC_DAY.md 5.5 for a peak of 3", sd.capacity(3)["businesses_by_vm_gb"] == {"16": {"f_1.0": 4, "f_0.5": 8}, "32": {"f_1.0": 9, "f_0.5": 18}, "64": {"f_1.0": 20, "f_0.5": 40}})
now = time.time()
ev_log = os.path.join(tmp, "eval.jsonl")
with open(ev_log, "w") as f:
    for i in range(5):
        f.write(json.dumps({"ts": now + i, "model": "p/m", "result": "ok" if i else "429", "tok": 100, "ttfb": 1.5, "neurons": 50.0}) + "\n")
    f.write(json.dumps({"ts": now - 9999, "model": "old"}) + "\nnot json\n")
sc = sd.scan_eval_log(ev_log, now - 1, now + 10)
check("eval log scan: window, results, neurons percent, peak per minute", sc["calls"] == 5 and sc["models"]["p/m"]["results"] == {"429": 1, "ok": 4}
      and sc["neurons_pct_of_10000"] == 2.5 and sc["peak_calls_per_minute"] == 5, str(sc))
gw_log = os.path.join(tmp, "gw.jsonl")
open(gw_log, "w").write(json.dumps({"gateway": "image", "ts": now, "ok": True, "gpu_seconds": 12.5}) + "\n" + json.dumps({"gateway": "router", "ts": now, "route": "nube", "reason": "x"}) + "\n")
g = sd.scan_gateway_log(gw_log, now - 1, now + 1)
check("gateway log scan: gpu seconds and router routes", g["gateways"]["image"]["gpu_seconds"] == 12.5 and g["router_routes"] == {"nube/x": 1})
wk = os.path.join(tmp, "waker.txt")
stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now))
open(wk, "w").write(f"{stamp} [syn-a] waking (task): brain=True web=False avail=9000MB\n{stamp} [syn-a] ready after 21.5s (task)\n"
                    f"{stamp} [syn-a] footprint 812MB, host avail=7000MB\n{stamp} [syn-a] task wake postponed 60s: not enough free memory (avail=1MB)\n"
                    f"{stamp} [other] ready after 99.0s (task)\nnov 09 x waker: {stamp} [syn-a] evicted by the RAM guard (avail=1MB)\n")
w = sd.scan_waker(wk, now - 5, now + 5, ["syn-a"])["syn-a"]
check("waker journal scan: wakes, ready after, footprint, postponed, evictions; other stacks ignored",
      w["wakes"] == 1 and w["ready_after_s"] == [21.5] and w["footprint_mb_max"] == 812 and w["postponed"] == 1 and w["evictions"] == 1, str(w))

# skipped events still count in the awake model: hand-calculated (a task event at 08:00, sender a, hop b of 90 s starting 40 s later, boot 20 s)
tev = {"id": "E2-01", "etype": "E2", "kind": "task", "sim_s": 8 * 3600, "steps": [{"tag_id": "E2-01", "after_s": 0, "role": "a"}],
       "hops": [{"role": "b", "after_s": 40, "active_s": 90}], "ext": {}}
aw1 = sd.awake_model([tev], {"E2-01": {"status": "ok", "seconds": 10.0}}, 20.0)
# a: 10 + 20 + 600 = 630 s = 10.5 min; b: 90 + 20 + 600 = 710 s = 11.8 min; they overlap
check("hop awake time: the hop's bot is awake for its active_s + boot + idle (11.8 min), the sender 10.5 min, both at once",
      aw1["per_role"]["b"] == {"wakes": 1, "awake_minutes": 11.8} and aw1["per_role"]["a"] == {"wakes": 1, "awake_minutes": 10.5} and aw1["peak_concurrent_awake_bots"] == 2, str(aw1))
aw2 = sd.awake_model([tev], {"E2-01": {"status": "skipped", "skip_reason": "target_has_no_tareas"}}, 20.0)
# the skipped sender keeps 60 s assumed: 60 + 20 + 600 = 680 s = 11.3 min; the hop is still there
check("a SKIPPED task event still counts: the sender at the assumed 60 s (11.3 min), the hop as before, one step marked assumed",
      aw2["per_role"]["a"] == {"wakes": 1, "awake_minutes": 11.3} and aw2["per_role"]["b"]["awake_minutes"] == 11.8 and aw2["steps_assumed"] == 1 and aw2["peak_concurrent_awake_bots"] == 2, str(aw2))
shop_busy = sd.build_timeline(scens["shop"], "busy", 3, "shop-busy-a-r1-x")
every = {st["tag_id"]: {"status": "ok", "seconds": 60.0} for ev in shop_busy if ev["kind"] != "marker" for st in ev["steps"]}
awA, awB = sd.awake_model(shop_busy, every, 25.0), sd.awake_model(shop_busy, {}, 25.0)
check("a day where nothing was sent has the awake figures of the same day sent at the assumed 60 s each (shop busy): skipped events no longer drop out",
      awA["per_role"] == awB["per_role"] and awA["peak_concurrent_awake_bots"] == awB["peak_concurrent_awake_bots"] and awB["steps_assumed"] == awB["steps_total"] > 0
      and awB["peak_concurrent_awake_bots"] >= 3, str((awA["peak_concurrent_awake_bots"], awB["peak_concurrent_awake_bots"])))
# the all-assumed burger normal day, written out by hand from the first-order table:
#   calls   E1 4, E2 8, E3 8x4, E4 2x4 (the sender, priced like E3), E5 6, E6 4, E7 20, E9 2x4 = 90; receiver rung for E2 (1 hop) and E4 (2 x 1 hop) = 3 x 5 = 15  -> 105
#   input   26k + 52k + 8x26k + 2x26k + 39k + 16k + 130k + 2x26k = 575k; 3 receiver rungs x 33k = 99k                                                         -> 674000
#   output  1.4k + 2.8k + 8x1.4k + 2x1.4k + 2.1k + 1.4k + 7k + 2x1.4k = 31.5k; 3 x 1.8k = 5.4k                                                                 -> 36900
pr0 = sd.projections(scens["burger"], {}, {"t": (1.0, 2.0, None)}, 0.0)["normal"]
check("projection of an all-assumed burger normal day: 105 calls, 674000 input, 36900 output (hand calculation; E7 gets no receiver add-on, E4 is sender plus receiver)",
      (pr0["calls"], pr0["input_tokens"], pr0["output_tokens"]) == (105, 674000, 36900), str(pr0))
check("the receiver add-on is for E2 and E4 only: a design day with E7 hops adds nothing for them",
      sd.projections(scens["design"], {}, {}, 0.0)["normal"]["calls"] == sum(n * sd.FIRST_ORDER[et][0] for et, n in scens["design"]["loads"]["normal"].items() if et not in ("E8", "E10", "E4"))
      + scens["design"]["loads"]["normal"]["E4"] * (sd.FIRST_ORDER["E3"][0] + sd.RECEIVER_SIDE[0]) + scens["design"]["loads"]["normal"]["E2"] * len(scens["design"]["events"]["E2"]["hops"]) * sd.RECEIVER_SIDE[0]
      + scens["design"]["loads"]["normal"]["E4"] * len(scens["design"]["events"]["E4"]["hops"]) * 0)

# ------------------------------------------------------------------------------------------------------------------ 9. stubs
pz = stubs.start("postiz", 0, postiz_hourly=3)
pu = f"http://127.0.0.1:{pz.server_port}"
codes = [post(pu + "/public/v1/posts", {"type": "draft"})[0] for _ in range(2)] + [post(pu + "/public/v1/posts", {"type": "now"})[0], post(pu + "/public/v1/posts", {"type": "schedule"})[0]]
check("postiz stub: drafts accepted, 'now' refused, hourly limit gives 429", codes == [200, 200, 400, 429], str(codes))
check("postiz stub counts", get(pu + "/_counters")["calls"].get("POST draft") == 2)
g_stub = stubs.start("gpu", 0, gpu_seconds=0.2)
post(f"http://127.0.0.1:{g_stub.server_port}/image", {})
check("gpu stub: sleeps and counts declared gpu seconds", get(f"http://127.0.0.1:{g_stub.server_port}/_counters")["gpu_seconds"] == 0.2)
pb = stubs.start("pbs", 0, pbs_verify="alternate")
v = [json.loads(post(f"http://127.0.0.1:{pb.server_port}/api2/json/admin/datastore/d/verify", {})[1])["data"]["state"] for _ in range(2)]
check("pbs stub alternates a fresh and a failed verification", v == ["ok", "failed"], str(v))
zu = f"http://127.0.0.1:{zab.server_port}/api_jsonrpc.php"
check("zabbix stub answers JSON-RPC and counts per method", json.loads(post(zu, {"jsonrpc": "2.0", "method": "item.get", "params": {}, "id": 1})[1])["result"][0]["name"] == "PHP version"
      and get(f"http://127.0.0.1:{zab.server_port}/_counters")["calls"].get("item.get") == 1)

# ------------------------------------------------------------------------------------------------------------------ 10. the repo hygiene bits
root = os.path.dirname(HERE)
gi = open(os.path.join(os.path.dirname(root), ".gitignore")).read()
check(".gitignore covers the private config and the results", "aibridge/ops/synth_targets.json" in gi and "aibridge/ops/synth_results/" in gi)
ex = json.load(open(os.path.join(HERE, "synth_targets.example.json")))
check("example config has only placeholders (no address, no key)", "127.0.0.1" in json.dumps(ex["fake_llm"]) and "<" in json.dumps(ex["targets"]) and not any(
    (t.get("api", "")[7:8].isdigit()) for t in ex["targets"].values()))

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all synthetic day checks passed")
