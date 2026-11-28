#!/usr/bin/env python3
"""Offline checks of the subagent and resource telemetry in ops/telemetry.py (2026-11-27): the in-container script against a fake
Hermes state.db (person, cron and delegated child sessions, the async_delegations ledger) and fake live manifests; the delegations
table and its reconciliation; turn kinds; the per-container `res` rows from a fake cgroup tree; the Zabbix values against the
template; the subagents report. Nothing here touches docker, the network or the real telemetry.db.
Run: python3 -I ops/telemetry_subagents_selftest.py"""
import importlib.util, json, os, re, sqlite3, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("tel", os.path.join(HERE, "telemetry.py"))
tel = importlib.util.module_from_spec(spec); spec.loader.exec_module(tel)
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"   {detail}"))
    if not ok:
        fails.append(name)


TMP = tempfile.mkdtemp()
SECRET = "SECRET-GOAL-text-that-must-stay-inside"   # must never leave the container script
now = time.time()
h8 = lambda x: __import__("hashlib").sha1(x.encode()).hexdigest()[:8]

# ---------------------------------------------------------------- a fake Hermes state.db (the columns the script reads)
state = os.path.join(TMP, "state.db")
s = sqlite3.connect(state)
s.executescript("""
create table sessions(id text primary key, source text not null, billing_provider text, model text, model_config text,
                      parent_session_id text, started_at real not null, api_call_count int default 0, tool_call_count int default 0,
                      input_tokens int default 0, output_tokens int default 0);
create table messages(id integer primary key autoincrement, session_id text, role text, timestamp real, finish_reason text,
                      display_kind text, tool_calls text, content text);
create table async_delegations(delegation_id text primary key, origin_session text not null, parent_session_id text, state text not null,
                               dispatched_at real not null, completed_at real, updated_at real not null, result_json text, task_json text);
""")
T = now - 3600
sess = [("P1", "telegram", None, None, T - 10), ("C1", "cron", None, None, T - 10),
        ("K1", "subagent", '{"_delegate_from": "P1", "_subagent_id": "a1"}', "P1", T + 0.3),         # child of the async delegation
        ("K2", "subagent", '{"_delegate_from": "P1"}', "P1", T + 600.2),                              # child of the manifest-only one
        ("K3", "telegram", '{"_delegate_from": "P1"}', "P1", T + 900)]                                # a continuation keeping the marker
for sid, src, mc, parent, st in sess:
    s.execute("insert into sessions(id, source, billing_provider, model, model_config, parent_session_id, started_at, api_call_count, "
              "tool_call_count, input_tokens, output_tokens) values(?,?,?,?,?,?,?,?,?,?,?)",
              (sid, src, "nvidia", "m1", mc, parent, st, 7 if sid == "K2" else 0, 5 if sid == "K2" else 0, 900 if sid == "K2" else 0, 90))
for sid, t in (("P1", T), ("C1", T + 5), ("K1", T + 1), ("K2", T + 601), ("K3", T + 901)):
    s.execute("insert into messages(session_id, role, timestamp, content) values(?,?,?,?)", (sid, "user", t, SECRET))
    s.execute("insert into messages(session_id, role, timestamp, finish_reason, content) values(?,?,?,?,?)", (sid, "assistant", t + 4, "stop", "fine"))
res_a = {"results": [{"task_index": 0, "status": "completed", "summary": SECRET, "api_calls": 10, "duration_seconds": 96.0, "model": "m1",
                      "tokens": {"input": 5000, "output": 400}, "tool_trace": [{"tool": "x"}] * 9},
                     {"task_index": 1, "status": "failed", "summary": SECRET, "api_calls": 2, "tokens": {"input": 100, "output": 10},
                      "tool_trace": []}],
         "live_transcripts": ["/root/.hermes/cache/delegation/live/deleg_aaaa1111/task-0.log"]}
s.execute("insert into async_delegations values(?,?,?,?,?,?,?,?,?)",
          ("deleg_aaaa1111", "origin", "P1", "completed", T, T + 100, T + 100, json.dumps(res_a),
           json.dumps({"goal": SECRET, "goals": [SECRET, SECRET], "model": "m1", "user_name": SECRET})))
# a second unit of the same batch, with its own ledger id: grouped under the live directory's id
s.execute("insert into async_delegations values(?,?,?,?,?,?,?,?,?)",
          ("deleg_bbbb2222", "origin", "P1", "completed", T + 1, T + 120, T + 120,
           json.dumps({"results": [{"task_index": 2, "status": "timeout", "api_calls": 1, "tokens": {}, "tool_trace": []}]}),
           json.dumps({"goals": [SECRET], "task_transcripts": ["/root/.hermes/cache/delegation/live/deleg_aaaa1111/task-2.log"]})))
s.commit(); s.close()

# ---------------------------------------------------------------- fake live manifests
live = os.path.join(TMP, "live")
lt = lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))
def manifest(did, started, tasks, completed=None, model=None):
    d = os.path.join(live, did); os.makedirs(d, exist_ok=True)
    for t in tasks:
        open(t["log"], "w").write(f"goal: {SECRET}\n")
    m = {"delegation_id": did, "started": lt(started), "task_count": len(tasks), "model": model, "provider": "nvidia",
         "tasks": [dict(t, goal=SECRET) for t in tasks]}
    if completed:
        m["completed"] = lt(completed)
    json.dump(m, open(os.path.join(d, "manifest.json"), "w"))
    return d
# the async one: its manifest says completed
manifest("deleg_aaaa1111", T, [{"index": 0, "status": "completed", "log": os.path.join(live, "deleg_aaaa1111", "task-0.log")}], T + 100)
# a running one (sync, no ledger row): one fresh transcript, one stale (> 15 min quiet)
d2 = manifest("deleg_cccc3333", T + 600, [{"index": 0, "status": "running", "log": os.path.join(live, "deleg_cccc3333", "task-0.log")},
                                           {"index": 1, "status": "running", "log": os.path.join(live, "deleg_cccc3333", "task-1.log")}],
              model="m2")
os.utime(os.path.join(d2, "task-1.log"), (now - 3000, now - 3000))
open(os.path.join(live, "junk.json"), "w").write("{")              # not a manifest dir
os.makedirs(os.path.join(live, "deleg_bad"), exist_ok=True)
open(os.path.join(live, "deleg_bad", "manifest.json"), "w").write("not json")

r = subprocess.run([sys.executable, "-I", "-", str(now - 7200), state, "900", live], input=tel.TURNS_SCRIPT, capture_output=True,
                   text=True, timeout=60)
check("the in-container script runs", r.returncode == 0, r.stderr[-400:])
check("no goal, summary or transcript text leaves the container script", SECRET not in r.stdout and "SECRET" not in r.stderr)
out = tel.parse_stack_read(r.stdout)
kinds = {t["session"]: t["kind"] for t in out["turns"]}
check("turn kinds: person, cron, subagent (source) and subagent (continuation with the marker)",
      kinds == {h8("P1"): "person", h8("C1"): "cron", h8("K1"): "subagent", h8("K2"): "subagent", h8("K3"): "subagent"}, kinds)
dl = {d["id"]: d for d in out["delegs"]}
a, c3 = dl.get(h8("deleg_aaaa1111")), dl.get(h8("deleg_cccc3333"))
check("two delegations: the batch's two ledger units grouped under the live id", len(dl) == 2 and a and c3, list(dl))
check("async: parent hash, statuses from the results, counts summed over both units",
      a and a["parent"] == h8("P1") and a["st"] == {"completed": 1, "failed": 1, "timeout": 1} and a["api"] == 13 and a["tools"] == 9
      and a["tin"] == 5100 and a["tout"] == 410 and a["tasks"] == 3, a)
check("async: started at dispatch, ended at the last unit's completion", a and abs(a["started"] - T) < 1 and abs(a["ended"] - (T + 120)) < 1, a)
check("manifest only: parent found through its child session, counters from the child's session row",
      c3 and c3["parent"] == h8("P1") and c3["api"] == 7 and c3["tools"] == 5 and c3["tin"] == 900 and c3["ended"] is None, c3)
check("manifest only: running tasks, one live (fresh transcript), model and provider", c3 and c3["st"] == {"running": 2} and c3["live"] == 1
      and c3["model"] == "m2" and c3["provider"] == "nvidia", c3)
check("running now: only subagents whose transcript moved in the last 15 min", out["running"] == 1, out["running"])
r2 = subprocess.run([sys.executable, "-I", "-", str(now - 7200), state, "900", "/nonexistent"], input=tel.TURNS_SCRIPT,
                    capture_output=True, text=True, timeout=60)
o2 = tel.parse_stack_read(r2.stdout)
check("a stopped stack (no manifests): the ledger still gives the delegation, nothing running",
      r2.returncode == 0 and len(o2["delegs"]) == 1 and o2["running"] == 0, (r2.stderr[-300:], o2["delegs"], o2["running"]))
# an older Hermes without model_config or async_delegations still reads
old = os.path.join(TMP, "old.db")
o = sqlite3.connect(old)
o.executescript("create table sessions(id text, source text, billing_provider text, model text);"
                "create table messages(id integer primary key, session_id, role, timestamp real, finish_reason, display_kind, tool_calls, content);"
                "insert into sessions values('Z', 'subagent', 'p', 'm');"
                f"insert into messages(session_id, role, timestamp, finish_reason) values('Z', 'user', {T}, null), ('Z', 'assistant', {T + 2}, 'stop');")
o.commit(); o.close()
r3 = subprocess.run([sys.executable, "-I", "-", str(now - 7200), old], input=tel.TURNS_SCRIPT, capture_output=True, text=True, timeout=60)
o3 = tel.parse_stack_read(r3.stdout)
check("old schema: turns still read, kind from the source, no delegations",
      r3.returncode == 0 and [t["kind"] for t in o3["turns"]] == ["subagent"] and o3["delegs"] == [], (r3.stderr[-300:], o3))

# ---------------------------------------------------------------- telemetry.db: turns kind, delegations, reconciliation
tel.DB = os.path.join(TMP, "state", "telemetry.db")
os.makedirs(os.path.dirname(tel.DB))
pre = sqlite3.connect(tel.DB)   # a db from before this change: turns without kind
pre.executescript("create table turns(stack, ts real, session, source, model, seconds real, tools int, tool_errors int, failed int, empty int, "
                  "unique(stack, ts, session));"
                  "insert into turns values('a', 1, 's1', 'telegram', 'm', 1, 0, 0, 0, 0), ('a', 2, 's2', 'subagent', 'm', 1, 0, 0, 1, 0), "
                  "('a', 3, 's3', 'cron', 'm', 1, 0, 0, 0, 0);")
pre.commit(); pre.close()
c = tel.db()
check("migration: old turns classified by their source",
      c.execute("select group_concat(kind, ',') from (select kind from turns order by ts)").fetchone()[0] == "person,subagent,cron")
c.execute("delete from turns")

stack = {"name": "a", "brain": "a-brain"}
tel.stack_read = lambda st, since: out
tel.stack_errors = lambda st: []
tel.stack_gateway_log = lambda st, since: []
new_turns, running = [], {}
tel.collect_stack(c, stack, now, now - 300, False, new_turns, running)
check("collect_stack: every turn stored with its kind", dict(c.execute("select kind, count(*) from turns group by 1").fetchall())
      == {"person": 1, "cron": 1, "subagent": 3})
check("collect_stack: subagent turns never reach the person alerts", sorted(t["kind"] for _, t in new_turns) == ["cron", "person"], new_turns)
check("collect_stack: running subagents handed to the resource sample", running == {"a": 1}, running)
row = lambda d: c.execute("select status, parent, tasks, ok, failed, interrupted, timeout, running, api_calls, tool_calls, tokens_in, "
                          "tokens_out, ended is null, model from delegations where stack='a' and deleg=?", (h8(d),)).fetchone()
check("delegations: the finished one", row("deleg_aaaa1111") == ("done", h8("P1"), 3, 1, 1, 0, 1, 0, 13, 9, 5100, 410, 0, "m1"),
      row("deleg_aaaa1111"))
check("delegations: the running one", row("deleg_cccc3333")[:3] == ("running", h8("P1"), 2) and row("deleg_cccc3333")[7] == 2
      and row("deleg_cccc3333")[12] == 1, row("deleg_cccc3333"))
check("delegations hold no goal text", SECRET not in json.dumps(c.execute("select * from delegations").fetchall()))
# next tick: Hermes pruned the running one's manifest (or the stack was recreated): reconciled as gone, ended at its last sighting
seen_at = c.execute("select last_seen from delegations where deleg=?", (h8("deleg_cccc3333"),)).fetchone()[0]
out2 = dict(out, delegs=[d for d in out["delegs"] if d["id"] != h8("deleg_cccc3333")])
tel.stack_read = lambda st, since: out2
tel.collect_stack(c, stack, now + 300, now, False, [], {})
check("reconcile: a vanished running delegation ends as gone at its last sighting",
      c.execute("select status, ended, duration from delegations where deleg=?", (h8("deleg_cccc3333"),)).fetchone()
      == ("gone", seen_at, round(seen_at - c3["started"], 1)))
check("reconcile: the finished one is untouched", row("deleg_aaaa1111")[0] == "done")
# the same one seen again later (a read that had failed): back to running, a counter never goes down
out3 = dict(out, delegs=[dict(d, api=0) if d["id"] == h8("deleg_cccc3333") else d for d in out["delegs"]])
tel.stack_read = lambda st, since: out3
tel.collect_stack(c, stack, now + 600, now, False, [], {})
check("seen again: running, ended cleared, counters kept", row("deleg_cccc3333")[0] == "running" and row("deleg_cccc3333")[12] == 1
      and row("deleg_cccc3333")[8] == 7, row("deleg_cccc3333"))
tel.end_gone(c, "a")
check("a stack that stopped: its running delegations end as gone", row("deleg_cccc3333")[0] == "gone")
# a forged record from a compromised container: bad hash, text in the status, negative counts
tel.store_delegations(c, "a", [{"id": "not-a-hash", "started": now}, {"id": "12345678", "started": now, "st": {SECRET: 3, "completed": -4},
                                                                     "api": -5, "model": SECRET + " x"}], now, None)
f = c.execute("select ok, other, api_calls, model from delegations where deleg='12345678'").fetchone()
check("container values re-checked: bad id skipped, odd words -> other, negatives -> 0, bad model dropped",
      f == (0, 3, 0, None) and c.execute("select count(*) from delegations where deleg='not-a-hash'").fetchone()[0] == 0, f)

# ---------------------------------------------------------------- res: a fake cgroup v2 tree
cg = os.path.join(TMP, "cgroup")
tel.CGROUP_ROOT = cg
ids = {n: (str(i) * 64)[:64] for i, n in enumerate(["a-brain", "a-open-webui", "a-voice", "a-web", "a-tg"], 1)}
def cgw(name, usec, mem, peak, pids, legacy=False):
    d = os.path.join(cg, "docker", ids[name]) if legacy else os.path.join(cg, "system.slice", f"docker-{ids[name]}.scope")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "cpu.stat"), "w").write(f"usage_usec {usec}\nuser_usec 1\nsystem_usec 1\n")
    open(os.path.join(d, "memory.current"), "w").write(f"{mem}\n")
    open(os.path.join(d, "memory.peak"), "w").write(f"{peak}\n")
    open(os.path.join(d, "pids.current"), "w").write(f"{pids}\n")
st_full = {"name": "a", "brain": "a-brain", "web": ["a-open-webui", "a-voice"], "front": "a-web", "telegram_api": "a-tg"}
check("stack containers and roles", tel.stack_containers(st_full) == [("brain", "a-brain"), ("webui", "a-open-webui"), ("voice", "a-voice"),
                                                                       ("web", "a-web"), ("telegram-bot-api", "a-tg")])
MB = 1048576
cgw("a-brain", 10_000_000, 600 * MB, 700 * MB, 30); cgw("a-web", 1_000_000, 50 * MB, 60 * MB, 4, legacy=True)
running_c = {"a-brain": ids["a-brain"], "a-web": ids["a-web"]}
t1 = now
agg = tel.sample_res(c, [st_full], t1, {"a": 2}, running_c)
r1 = c.execute("select role, secs, cpu_s, mem_mb, peak_mb, pids, subagents from res order by role").fetchall()
check("first sample: one row per running container (systemd and cgroupfs paths), no delta yet",
      r1 == [("brain", None, None, 600.0, 700.0, 30, 2), ("web", None, None, 50.0, 60.0, 4, None)], r1)
check("first sample: no CPU % for Zabbix yet", agg["a"]["secs"] is None and agg["a"]["mem_mb"] == 650.0 and agg["a"]["subagents"] == 2, agg)
cgw("a-brain", 40_000_000, 650 * MB, 700 * MB, 31)
cgw("a-web", 500_000, 40 * MB, 40 * MB, 4, legacy=True)                     # restarted: usage went down
cgw("a-voice", 2_000_000, 100 * MB, 100 * MB, 3)                            # new since the last sample
running_c["a-voice"] = ids["a-voice"]
agg = tel.sample_res(c, [st_full], t1 + 300, {"a": 0}, running_c)
r2 = {x[0]: x[1:] for x in c.execute("select role, secs, cpu_s, subagents from res where ts=?", (t1 + 300,))}
check("delta: 30 CPU-s over 300 s on the brain", r2["brain"] == (300.0, 30.0, 0), r2)
check("restarted container: its whole new usage", r2["web"] == (300.0, 0.5, None), r2)
check("new container: its whole usage since the last sample", r2["voice"] == (300.0, 2.0, None), r2)
check("Zabbix totals: CPU % of one core over the interval", agg["a"]["secs"] == 300.0 and round(100 * agg["a"]["cpu_s"] / 300, 1) == 10.8, agg)
check("a container without a cgroup dir is skipped", tel.cgroup_read("f" * 64) is None)

# ---------------------------------------------------------------- Zabbix: values vs the template, off unless configured
tpl = open(os.path.join(HERE, "zabbix", "template_bridgeai_stacks.yaml")).read()
keys = set(re.findall(r"^\s+key: '([^']+)'", tpl, re.M))
vals = tel.zbx_values("bridgeai-stacks", agg)
sent = {re.sub(r"\[a\]$", "[{#STACK}]", k) for _, k, _ in vals}
check("the push sends exactly the template's keys", sent == keys, (sent ^ keys))
check("discovery names the stacks", json.loads(dict((k, v) for _, k, v in vals)["stack.discovery"]) == [{"{#STACK}": "a"}])
check("template: allowed_hosts, never trapper_hosts, no triggers", "trapper_hosts:" not in tpl and "allowed_hosts:" in tpl and "triggers:" not in tpl)
check("unknown values are left out, never sent as 0",
      not any(k.startswith("stack.cpu_pct") for _, k, _ in tel.zbx_values("h", {"b": {"awake": 0, "cpu_s": 0, "secs": None, "mem_mb": 0,
                                                                                      "subagents": None}})))
check("push off without STACKS_ZBX_HOST", tel.push_stacks(agg, {"server": "z", "host": "", "port": "10051"}) is None)
check("push off without a server", tel.push_stacks(agg, {"server": "", "host": "h", "port": "10051"}) is None)
got = []
check("push sends to the configured host", tel.push_stacks(agg, {"server": "z", "host": "h", "port": "10051"},
                                                           send=lambda v, s_, p: (got.append((s_, p, v)), (len(v), 0))[1]) == (len(vals), 0)
      and got[0][0] == "z" and all(h == "h" for h, _, _ in got[0][2]))
def down(v, s_, p): raise OSError("refused")
check("a Zabbix that is down never raises", tel.push_stacks(agg, {"server": "z", "host": "h", "port": "1"}, send=down) == (0, -1))
envf = os.path.join(TMP, "ops.env"); open(envf, "w").write("ZBX_SERVER=10.0.0.5\nSTACKS_ZBX_HOST=bridgeai-stacks\nPROBE_KEY_X=secret\n")
tel.OPS_ENV = envf
zc = tel.zbx_conf({})
check("conf: ZBX_SERVER as the fallback server, other ops.env names never read", zc == {"server": "10.0.0.5", "host": "bridgeai-stacks",
                                                                                          "port": "10051"}, zc)
spec2 = importlib.util.spec_from_file_location("provision", os.path.join(HERE, "zabbix", "provision.py"))
pv = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(pv)
check("provision.py stacks-host loads this template by its name", pv.STACKS_TEMPLATE == "bridgeai stacks" and "template: 'bridgeai stacks'" in tpl)
calls = []
pv._trapper_host = lambda *a: calls.append(a)
pv.stacks_host("bridgeai-stacks", "192.168.0.2", "pve4", True)
check("stacks-host goes through _trapper_host with the stacks template, file and macro",
      calls and calls[0][5:9] == ("bridgeai stacks", "template_bridgeai_stacks.yaml", "{$STACKS.TRAPPER.HOSTS}", pv.STACKS_MARK), calls)

# ---------------------------------------------------------------- the subagents report
c.execute("delete from delegations"); c.execute("delete from res")
D = [("d1", 1000, 1600, "done", 2, 2, 0, 0, 0, 0), ("d2", 1300, 1900, "done", 1, 0, 1, 0, 0, 0), ("d3", 5000, 5100, "gone", 1, 0, 0, 0, 0, 1)]
base = now - 86400
for d, s0, s1, stt, tasks, ok, failed, intr, to, run in D:
    c.execute("insert into delegations(stack, deleg, started, ended, last_seen, status, tasks, ok, failed, interrupted, timeout, running, "
              "duration, api_calls, tool_calls, tokens_in, tokens_out) values('a',?,?,?,?,?,?,?,?,?,?,?,?,3,4,100,10)",
              (d, base + s0, base + s1, base + s1, stt, tasks, ok, failed, intr, to, run, s1 - s0))
for ts, role, cpu, mem in ((1300, "brain", 10, 500), (1300, "web", 1, 50), (1600, "brain", 20, 800), (1900, "brain", 5, 600),
                           (3000, "brain", 99, 900), (5100, "brain", 7, 400)):
    c.execute("insert into res(ts, stack, role, secs, cpu_s, mem_mb) values(?,?,?,?,?,?)", (base + ts, "a", role, 300, cpu, mem))
rep = tel.subagents_report(c, 7, now)
print(rep)
check("report: delegations, tasks, median and max duration, failed share",
      "a: 3 delegations, 4 tasks" in rep and "median 10.0 min" in rep and "max 10.0 min" in rep and "failed 25%" in rep, rep)
check("report: cut ones and the children's counts", "1 cut by a stop or a prune" in rep and "9 model calls, 12 tool calls" in rep, rep)
check("report: CPU over the merged intervals, each sample once, labelled as an upper bound",
      "at most 43 CPU-s (upper bound" in rep and "brain RAM up to 800 MB" in rep, rep)
check("report: nothing in an empty window", "No subagents." in tel.subagents_report(c, 1, now + 30 * 86400))
# the daily report's per-stack lines leave subagent turns out and mention the subagents
c.execute("delete from turns")
for i, k in enumerate(["person", "subagent", "subagent", "cron"]):
    c.execute("insert into turns(stack, ts, session, source, model, seconds, tools, tool_errors, failed, empty, kind) values(?,?,?,?,?,?,?,?,?,?,?)",
              ("a", base + 100 + i, f"s{i}", "telegram" if k == "person" else k, "m", 5, 0, 0, int(k == "subagent"), 0, k))
text, stats = tel.stack_lines(c, "a", base)
check("daily: subagent turns are not the person's turns", stats["turns"] == 2 and stats["failed"] == 0, stats)
check("daily: a subagents line", "subagents: 3 delegations, 4 tasks" in text, text)
# a compaction summary and a mid-turn (steer) message continue the running turn; a notification after the answer is a new turn
st2 = os.path.join(TMP, "state2.db")
s = sqlite3.connect(st2)
s.executescript("create table sessions(id text primary key, source text not null, billing_provider text, model text, model_config text);"
                "create table messages(id integer primary key autoincrement, session_id text, role text, timestamp real, finish_reason text,"
                " display_kind text, tool_calls text, content text);")
s.execute("insert into sessions values('P2', 'telegram', 'p', 'm', null)")
T2 = now - 3000
for dt, role, fin, dk, tc, content in [
        (0, "user", None, None, None, SECRET), (2, "assistant", "tool_calls", None, "[1]", ""), (3, "tool", None, None, None, "ok"),
        (60, "user", None, None, None, "[CONTEXT COMPACTION — REFERENCE ONLY] " + SECRET), (62, "assistant", "tool_calls", None, "[1]", ""),
        (70, "user", None, "steer", None, "[OUT-OF-BAND USER MESSAGE — a direct message] " + SECRET),
        (75, "user", None, None, None, SECRET), (75.4, "user", None, None, None, "[STILL IN PROGRESS — this is the active request] "),
        (75.5, "user", None, None, None, "[CONTEXT COMPACTION — REFERENCE ONLY] " + SECRET),
        (80, "assistant", "stop", None, None, "done"),
        (200, "user", None, "internal_notification", None, SECRET), (205, "assistant", "stop", None, None, "noted")]:
    s.execute("insert into messages(session_id, role, timestamp, finish_reason, display_kind, tool_calls, content) values(?,?,?,?,?,?,?)",
              ("P2", role, T2 + dt, fin, dk, tc, content))
s.commit(); s.close()
r3 = subprocess.run([sys.executable, "-I", "-", str(now - 7200), st2, "900", "/nonexistent"], input=tel.TURNS_SCRIPT,
                    capture_output=True, text=True, timeout=60)
t3 = tel.parse_stack_read(r3.stdout)["turns"] if r3.returncode == 0 else []
check("continuations: compaction (and its re-inserted request) + steer stay in one answered turn, the later notification is its own",
      [(round(t["seconds"] or -1), t["failed"], t["tools"]) for t in t3] == [(80, 0, 1), (5, 0, 0)], [r3.stderr[-300:], t3])
print("\n".join(fails) or "telemetry_subagents_selftest: all ok")
sys.exit(1 if fails else 0)
