#!/usr/bin/env python3
"""Offline checks of the per-stack diagnostics in ops/telemetry.py (2026-11-27): the in-container script against a fake Hermes state.db
(a person session, its compaction child, a subagent and an old session), the session-counter deltas kept in telemetry.db (baseline on
the first look, a new session counted from 0, an old one never counted whole, no double count on a re-read, a counter that went down),
context per call, provider cache %, per-turn averages, waits, cost, the tool ranking with terminal program names, the Zabbix values
against the template, and the stacks dashboard of provision.py. A SECRET string sits in every message, argument and tool output and
must never come out. Nothing here touches docker, the network or the real telemetry.db.
Run: python3 -I ops/telemetry_diag_selftest.py"""
import fnmatch, importlib.util, json, os, re, sqlite3, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("tel", os.path.join(HERE, "telemetry.py"))
tel = importlib.util.module_from_spec(spec); spec.loader.exec_module(tel)
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"   {detail}"))
    if not ok:
        fails.append(name)


TMP = tempfile.mkdtemp()
SECRET = "SECRET-person-text-that-must-stay-inside"
now = time.time()
T0 = now - 1800
state = os.path.join(TMP, "state.db")
s = sqlite3.connect(state)
s.executescript("""
create table sessions(id text primary key, source text not null, billing_provider text, model text, model_config text,
                      parent_session_id text, started_at real not null, api_call_count int default 0, tool_call_count int default 0,
                      input_tokens int default 0, output_tokens int default 0, cache_read_tokens int default 0, cache_write_tokens int default 0,
                      reasoning_tokens int default 0, estimated_cost_usd real);
create table messages(id integer primary key autoincrement, session_id text, role text, timestamp real, finish_reason text,
                      display_kind text, tool_calls text, tool_name text, tool_call_id text, content text);
""")


def sess(sid, src, started, parent=None, mc=None):
    s.execute("insert into sessions(id, source, billing_provider, model, model_config, parent_session_id, started_at) values(?,?,?,?,?,?,?)",
              (sid, src, "prov", "m1", mc, parent, started))


def counters(sid, api, tools, tin, tout, cr, cw, rs, cost):
    s.execute("update sessions set api_call_count=?, tool_call_count=?, input_tokens=?, output_tokens=?, cache_read_tokens=?, "
              "cache_write_tokens=?, reasoning_tokens=?, estimated_cost_usd=? where id=?", (api, tools, tin, tout, cr, cw, rs, cost, sid))


def msg(sid, role, ts, fin=None, calls=None, tool=None, cid=None, content=SECRET, dk=None):
    s.execute("insert into messages(session_id, role, timestamp, finish_reason, display_kind, tool_calls, tool_name, tool_call_id, content) "
              "values(?,?,?,?,?,?,?,?,?)", (sid, role, ts, fin, dk, json.dumps(calls) if calls else None, tool, cid, content))


def call(cid, name, **args):
    return {"id": cid, "call_id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


# ---- before the first look: one answered turn in P1, an old session O1 with history from long ago
sess("P1", "telegram", T0 - 100); counters("P1", 10, 4, 1000, 200, 9000, 0, 50, 0.01)
sess("O1", "telegram", now - 30 * 86400); counters("O1", 50, 20, 50000, 5000, 1, 0, 0, 0.5)
msg("O1", "user", now - 20 * 86400); msg("O1", "assistant", now - 20 * 86400 + 3, "stop")
msg("P1", "user", T0); msg("P1", "assistant", T0 + 5, "stop", content="fine")
s.commit()


def read(since, last_id):
    r = subprocess.run([sys.executable, "-I", "-", str(since), state, "900", "/nonexistent", str(last_id)], input=tel.TURNS_SCRIPT,
                       capture_output=True, text=True, timeout=60)
    read.raw.append(r.stdout + r.stderr)
    if r.returncode:
        print(r.stderr[-600:])
    return tel.parse_stack_read(r.stdout) if r.returncode == 0 else None
read.raw = []

tel.DB = os.path.join(TMP, "st", "telemetry.db"); os.makedirs(os.path.dirname(tel.DB))
c = tel.db()
tel.stack_read = lambda st, since, last_id=-1: read(since, last_id)
tel.stack_errors = lambda st: []
tel.stack_gateway_log = lambda st, since: []
stack = {"name": "a", "brain": "a-brain"}
N1 = T0 + 300
tel.collect_stack(c, stack, N1, N1 - 300, False, [], {})
check("first look: only the baseline (no diag row, no tool row), the message id and the start are kept",
      c.execute("select count(*) from diag").fetchone()[0] == 0 and c.execute("select count(*) from tooluse").fetchone()[0] == 0
      and tel.meta_get(c, "diag_last_id:a") == 2 + 2 and float(tel.meta_get(c, "diag_start:a")) == N1,
      (c.execute("select * from diag").fetchall(), tel.meta_get(c, "diag_last_id:a")))
check("first look: the session counters are the baseline", c.execute("select api, cr from sess_seen where stack='a' and session=?",
                                                                     (tel._hash8(__import__("hashlib").sha1(b"P1").hexdigest()[:8]),)).fetchone() == (10, 9000))

# ---- after the first look: P1's second turn with three tool calls (two terminal in one answer, then read_file with an error), a
# compaction that continues in a child session P2, a subagent K1 with its own tool, and the old O1 that comes back
msg("P1", "user", T0 + 600)
msg("P1", "assistant", T0 + 601, "tool_calls", [call("c1", "terminal", command=f"cd /workdir && python3 /workdir/tools/report_job.py --q '{SECRET}'"),
                                                 call("c2", "terminal", command=f"gateway song --title '{SECRET}'")], content="")
msg("P1", "tool", T0 + 611, tool="terminal", cid="c1", content=f"output {SECRET}")
msg("P1", "tool", T0 + 614, tool="terminal", cid="c2", content=f"output {SECRET}")
msg("P1", "assistant", T0 + 615, "tool_calls", [call("c3", "read_file", path=f"/workdir/{SECRET}.txt")], content="")
msg("P1", "tool", T0 + 616, tool="read_file", cid="c3", content='{"error": "' + SECRET + '"}')
msg("P1", "assistant", T0 + 618, "stop", content="done")
counters("P1", 14, 7, 1400, 260, 13000, 100, 70, 0.015)
sess("P2", "telegram", T0 + 620, parent="P1"); counters("P2", 3, 0, 300, 30, 600, 0, 0, 0.005)
msg("P2", "user", T0 + 620, content="[CONTEXT COMPACTION — REFERENCE ONLY] " + SECRET)
msg("P2", "assistant", T0 + 630, "stop", content="ok")
sess("K1", "subagent", T0 + 605, parent="P1", mc='{"_delegate_from": "P1"}'); counters("K1", 5, 1, 500, 50, 0, 0, 0, 0.002)
msg("K1", "user", T0 + 605)
msg("K1", "assistant", T0 + 606, "tool_calls", [call("k1", "terminal", command=f"mkdir -p /tmp/{SECRET} && export X={SECRET}; node /app/x/build.js {SECRET}")], content="")
msg("K1", "tool", T0 + 608, tool="terminal", cid="k1", content=SECRET)
msg("K1", "assistant", T0 + 609, "stop", content="ok")
msg("O1", "user", T0 + 700); msg("O1", "assistant", T0 + 702, "stop", content="ok"); counters("O1", 51, 20, 50100, 5010, 1, 0, 0, 0.5)
s.commit()
N2 = T0 + 1000
tel.collect_stack(c, stack, N2, N1, False, [], {})
d = dict(zip(("sessions", "api", "tools", "tin", "tout", "cr", "cw", "rs", "cost", "pmax", "comp"), c.execute(
    "select sessions, api, tools, tin, tout, cr, cw, rs, cost, prompt_max, compactions from diag where kind='person' and ts=?", (N2,)).fetchone() or ()))
check("deltas: P1's increase plus the whole of its new compaction child P2; the old O1 is only a baseline",
      d.get("sessions") == 2 and d.get("api") == 7 and d.get("tin") == 700 and d.get("cr") == 4600 and d.get("cw") == 100 and d.get("tout") == 90
      and d.get("rs") == 20 and abs(d.get("cost", 0) - 0.01) < 1e-9, d)
check("max prompt per call: the largest session window average ((400 + 4000 + 100) / 4)", d.get("pmax") == 1125.0, d)
check("compactions counted on the new messages (person)", d.get("comp") == 1, d)
k = c.execute("select api, tin, tout from diag where kind='subagent' and ts=?", (N2,)).fetchone()
check("the subagent's counters go to its own kind", k == (5, 500, 50), k)
tu = {(r[0], r[1], r[2]): r[3:] for r in c.execute("select kind, tool, prog, calls, seconds, errors from tooluse where ts=?", (N2,))}
check("tool use: terminal split by program (script basename, gateway subcommand, node script), sequential seconds, errors",
      tu == {("person", "terminal", "python3 report_job.py"): (1, 10.0, 0), ("person", "terminal", "gateway song"): (1, 3.0, 0),
             ("person", "read_file", None): (1, 1.0, 1), ("subagent", "terminal", "node build.js"): (1, 2.0, 0)}, tu)
turn = c.execute("select calls, tools, tool_errors, seconds from turns where stack='a' and ts=?", (T0 + 600,)).fetchone()
check("turns carry their model calls (assistant messages)", turn == (3, 3, 1, 18.0), turn)

w = tel.diag_window(c, "a", N2 - 3600, N2)
pt = c.execute("select seconds, calls, tools, failed from turns where stack='a' and kind='person' and ts>? and ts<=?", (N2 - 3600, N2)).fetchall()
secs = sorted(r[0] for r in pt)
check("window: context per call = (fresh + cache read + cache write) / calls, max, cache %",
      w["ctx_tokens_avg"] == round(5400 / 7) and w["ctx_tokens_max"] == 1125 and w["cache_pct"] == round(100 * 4600 / 5400, 1), w)
check("window: tokens, compactions, cost", w["out_tokens"] == 90 and w["reasoning_tokens"] == 20 and w["compactions"] == 1
      and w["cost_usd"] == 0.01, w)
check("window: per-turn averages from the person's turns", w["turns"] == len(pt) and w["calls_per_turn"] == round(sum(r[1] for r in pt) / len(pt), 2)
      and w["tools_per_turn"] == round(sum(r[2] for r in pt) / len(pt), 2) and w["tool_errors"] == 1 and w["failed"] == 0, (w, pt))
check("window: waits p50 / p90 of the person's turns", w["wait_p50"] == tel.pct(secs, 50) and w["wait_p90"] == tel.pct(secs, 90)
      and w["wait_p90"] == 18.0, (w, secs))
check("window: no subagent turn among the person's", all(r[0] != 4.0 for r in pt))   # K1's turn took 4 s
empty = tel.diag_window(c, "a", N2 + 10, N2 + 20)
check("an empty window: averages unknown (None), counts 0", empty["ctx_tokens_avg"] is None and empty["cache_pct"] is None
      and empty["wait_p50"] is None and empty["calls_per_turn"] is None and empty["turns"] == 0 and empty["compactions"] == 0, empty)

# ---- a re-read (the turns' one-hour lookback, nothing new): nothing counted twice
before = (c.execute("select count(*), sum(api), sum(compactions) from diag").fetchone(), c.execute("select count(*) from tooluse").fetchone())
tel.collect_stack(c, stack, N2 + 300, N2, False, [], {})
after = (c.execute("select count(*), sum(api), sum(compactions) from diag").fetchone(), c.execute("select count(*) from tooluse").fetchone())
check("re-read: no new diag or tool rows, sums unchanged", before == after, (before, after))
# ---- counters that went down (a replaced state.db): a new baseline, never a negative; then only the increase counts
counters("P1", 2, 0, 100, 10, 0, 0, 0, 0.0); s.commit()
tel.collect_stack(c, stack, N2 + 600, N2 + 300, False, [], {})
check("counters down: nothing stored", c.execute("select count(*) from diag where ts=?", (N2 + 600,)).fetchone()[0] == 0
      and c.execute("select min(api), min(tin), min(cost) from diag").fetchone()[0] >= 0)
counters("P1", 3, 0, 150, 12, 50, 0, 0, 0.001); s.commit()
tel.collect_stack(c, stack, N2 + 900, N2 + 600, False, [], {})
check("then the increase over the new baseline", c.execute("select api, tin, cr from diag where ts=?", (N2 + 900,)).fetchone() == (1, 50, 50))
# ---- the tool ranking report
rep = tel.tools_report(c, 7, N2 + 1000)
print(rep)
lines = rep.splitlines()
i_py = next((i for i, l in enumerate(lines) if "terminal (python3 report_job.py)" in l), -1)
i_gw = next((i for i, l in enumerate(lines) if "terminal (gateway song)" in l), -1)
check("tools report: ranked by total seconds, terminal by program, errors shown",
      0 < i_py < i_gw and "read_file: " in rep and "1 failed" in rep and "terminal (node build.js)" in rep, rep)
check("tools report: nothing in an empty window", "No tool calls recorded." in tel.tools_report(c, 1, N2 + 30 * 86400))
text, _ = tel.stack_lines(c, "a", N2 - 3600)
check("daily report: a diagnostics line", text and "tokens/call" in text and "provider cache" in text, text)

# ---- a state.db replaced by a smaller one (message ids restart): counted from its start, not lost
c.execute("update meta set v=99999 where k='diag_last_id:a'")
tel.collect_stack(c, stack, N2 + 1200, N2 + 900, False, [], {})
check("message ids above the top: counted again from the start (a new state.db)",
      int(tel.meta_get(c, "diag_last_id:a")) < 99999 and c.execute("select sum(compactions) from diag where ts=?", (N2 + 1200,)).fetchone()[0] == 1)

# ---- Zabbix: the diagnostics' keys are the template's, values as computed, unknown ones left out
tpl = open(os.path.join(HERE, "zabbix", "template_bridgeai_stacks.yaml")).read()
keys = set(re.findall(r"^\s+key: '([^']+)'", tpl, re.M))
agg = {"a": {"awake": 1, "cpu_s": 3.0, "secs": 300.0, "mem_mb": 700.0, "subagents": 0, "diag": w}}
vals = tel.zbx_values("bridgeai-stacks", agg)
sent = {re.sub(r"\[a\]$", "[{#STACK}]", k) for _, k, _ in vals}
check("Zabbix: every diagnostic key is a template item", {f"stack.{k}[{{#STACK}}]" for k in tel.DIAG_KEYS} <= keys and sent == keys, sent ^ keys)
v = {k: x for _, k, x in vals}
check("Zabbix: values as the window says", v["stack.ctx_tokens_avg[a]"] == w["ctx_tokens_avg"] and v["stack.cache_pct[a]"] == w["cache_pct"]
      and v["stack.compactions[a]"] == 1 and v["stack.cost_usd[a]"] == 0.01, v)
agg["a"]["diag"] = empty
ek = {k for _, k, _ in tel.zbx_values("h", agg)}
check("Zabbix: unknown averages left out, counts sent as 0", "stack.ctx_tokens_avg[a]" not in ek and "stack.wait_p50[a]" not in ek
      and "stack.turns[a]" in ek and "stack.compactions[a]" in ek, ek)
proto = re.findall(r"- uuid: (\w+)\n\s+name: '(Stack \{#STACK\}: [^']+)'\n(?:.*\n){1,2}?\s+key: 'stack\.(\w+)\[\{#STACK\}\]'\n\s+delay: '0'\n"
                   r"\s+history: (\w+)\n\s+trends: (\w+)\n\s+value_type: (\w+)", tpl)
diag_proto = {p[2]: p for p in proto if p[2] in tel.DIAG_KEYS}
check("template: every diagnostic prototype is a FLOAT trapper with 90d history and 365d trends",
      len(diag_proto) == len(tel.DIAG_KEYS) and all(p[3:] == ("90d", "365d", "FLOAT") for p in diag_proto.values()), diag_proto)
check("template: unique uuids, allowed_hosts, no trapper_hosts, no triggers",
      len(set(re.findall(r"uuid: (\w+)", tpl))) == len(re.findall(r"uuid: (\w+)", tpl)) and "trapper_hosts:" not in tpl and "triggers:" not in tpl)

# ---- the stacks dashboard (provision.py stacks-dashboard)
spec2 = importlib.util.spec_from_file_location("provision", os.path.join(HERE, "zabbix", "provision.py"))
pv = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(pv)
names = re.findall(r"^\s+name: '(Stack \{#STACK\}: [^']+)'", tpl, re.M)
ws = pv.stacks_widgets(["bridgeai-stacks"])
pats = [f["value"] for x in ws for f in x["fields"] if ".items." in f["name"]]
check("dashboard: every item pattern matches exactly one prototype", all(len([n for n in names if fnmatch.fnmatchcase(n, p)]) == 1 for p in pats),
      {p: [n for n in names if fnmatch.fnmatchcase(n, p)] for p in pats})
covered = {n for n in names for p in pats if fnmatch.fnmatchcase(n, p)}
check("dashboard: every per-stack item has a graph", covered == set(names), set(names) - covered)
check("dashboard: widgets fit the 72-column grid and do not overlap",
      all(0 <= x["x"] and x["x"] + x["width"] <= 72 for x in ws) and
      not any(a is not b and a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"] and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]
              for a in ws for b in ws))
calls = []


def fake_api(method, params, auth=True):
    calls.append((method, params))
    if method == "user.get" or method == "user.checkAuthentication":
        return [{"roleid": "3", "type": "3"}]
    if method == "template.get":
        return [{"templateid": "T1"}]
    if method == "host.get":
        return [{"host": "bridgeai-stacks"}] if params.get("templateids") == ["T1"] else []
    return []
pv.api = fake_api
pv.require_super_admin = lambda: None
pv.stacks_dashboard()
cr = [p for m, p in calls if m == "dashboard.create"]
check("dashboard: created by name with one page 'Stacks' on the host linked to the template",
      cr and cr[0]["name"] == pv.STACKS_DASHBOARD and [pg["name"] for pg in cr[0]["pages"]] == ["Stacks"]
      and all(f["value"] == "bridgeai-stacks" for x in cr[0]["pages"][0]["widgets"] for f in x["fields"] if ".hosts." in f["name"]), cr)

# ---- nothing of a person's text ever leaves
dump = "\n".join(c.iterdump())
check("no message text, argument or tool output in the script output, telemetry.db, reports or the Zabbix values",
      not any("SECRET" in x for x in read.raw) and "SECRET" not in dump and "SECRET" not in rep and "SECRET" not in (text or "")
      and "SECRET" not in json.dumps(vals))
print("\n".join(fails) or "telemetry_diag_selftest: all ok")
sys.exit(1 if fails else 0)
