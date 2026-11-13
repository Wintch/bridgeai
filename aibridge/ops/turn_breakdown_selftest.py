#!/usr/bin/env python3
"""Offline test of ops/turn_breakdown.py, ops/turn_cpu_sampler.py and the timing fields the router and the gateway now log.
Invented state.db, logs and cgroup files in a temp dir; no network, no docker. Run: python3 -I ops/turn_breakdown_selftest.py"""
import contextlib, datetime as dt, io, json, os, sqlite3, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix="turnbd-")
os.environ["GATEWAY_LOG"] = os.path.join(tmp, "gw-real.jsonl")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import turn_breakdown as tb, turn_cpu_sampler as sampler
import gateway

fails = []


def check(name, got, want):
    ok = (abs(got - want) < 0.051 if isinstance(want, float) and isinstance(got, (int, float)) else got == want)
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f": got {got!r}, want {want!r}"))
    if not ok:
        fails.append(name)


CANARY = "CANARY-PRIVATE-TEXT"
E = tb.utc("2026-11-13 10:00:10")                       # the woken turn's anchor, whole seconds like the journal
db_path = os.path.join(tmp, "state.db")
db = sqlite3.connect(db_path)
db.executescript("create table sessions(id text, source text); create table messages(id integer primary key autoincrement, session_id text, "
                 "role text, content text, tool_calls text, tool_name text, finish_reason text, timestamp real);")
db.execute("insert into sessions values('S1','telegram'),('S2','telegram')")


def msg(sid, role, ts, fin=None, tools=None, tname=None, content=CANARY):
    tc = json.dumps([{"id": "c", "function": {"name": n, "arguments": json.dumps({"cmd": CANARY})}} for n in tools]) if tools else None
    db.execute("insert into messages(session_id, role, content, tool_calls, tool_name, finish_reason, timestamp) values(?,?,?,?,?,?,?)",
               (sid, role, content, tc, tname, fin, ts))


# A: awake, two model calls, a gateway command in between (and a copy of the first rows stored under a compaction child session)
msg("S1", "user", 1000.0)
msg("S1", "assistant", 1003.0, "tool_calls", ["terminal"], content="")
msg("S1", "tool", 1008.0)
msg("S1", "assistant", 1010.0, "stop")
msg("S2", "user", 1000.0)
msg("S2", "assistant", 1003.0, "tool_calls", ["terminal"], content="")
# D: a burst of two messages, a plain answer the router never logged
msg("S1", "user", 2000.0)
msg("S1", "user", 2002.0, content=CANARY + "2")
msg("S1", "assistant", 2005.0, "stop")
# E: a tool with a hostile name and no gateway line: its CPU comes from the cgroup counters
msg("S1", "user", 3000.0)
msg("S1", "assistant", 3001.0, "tool_calls", ["bad name " + CANARY])
msg("S1", "tool", 3005.0)
msg("S1", "assistant", 3006.0, "stop")
# C: never answered
msg("S1", "user", 4000.0)
# B: the first message after a wake
msg("S1", "user", E + 24)
msg("S1", "assistant", E + 27, "stop")
db.commit()
db.close()

ev = [{"ts": 1001.0, "model": "aux-m", "aux": True, "result": "ok", "s": 0.4},
      {"ts": 1002.9, "model": "m1", "pos": 0, "aux": False, "result": "ok", "s": 2.4, "ttfb": 0.8, "pre": 0.1, "tok": 50, "ptok": 3000, "in_b": 12000},
      {"ts": 1008.5, "model": "m0", "pos": 0, "aux": False, "result": "HTTP 429", "s": 0.3},
      {"ts": 1009.9, "model": "m1", "pos": 1, "aux": False, "result": "ok", "s": 1.5, "ttfb": 0.5, "buf": 1},
      {"ts": E + 26.9, "model": "m2", "pos": 0, "aux": False, "result": "ok", "s": 2.5, "ttfb": 1.0, "tok": 20},
      {"ts": 1010.0, "model": "m1", "feedback": 1}]
gw = [{"ts": 1008.0, "gateway": "transcode", "host": "gpu-a", "seconds": 4.0, "proc_wall": 4.2, "proc_cpu": 3.8}]
fn = lambda n: os.path.join(tmp, n)
with open(fn("eval.jsonl"), "w") as f:
    f.write('{"cut first line\n' + "\n".join(json.dumps(x) for x in ev) + "\n")
with open(fn("gw.jsonl"), "w") as f:
    f.write("\n".join(json.dumps(x) for x in gw) + "\n")
with open(fn("journal.txt"), "w") as f:
    f.write("2026-11-13 10:00:10 [stack-a] telegram wake: update 5 (message), sent 6s ago\n"
            "2026-11-13 10:00:12 [stack-a] waking (telegram): brain=True web=False avail=5000MB\n"
            "2026-11-13 10:00:32 [stack-a] ready after 20.0s (telegram)\n"
            "2026-11-13 10:00:40 [other] ready after 99.0s (telegram)\n")
# a core busy during D (2000-2005), a twentieth of one during E's tool (3001-3005), half a second of disk wait in D
rates = [(2000, 2005, 1.0), (3000, 3006, 0.05)]
cum = lambda t: sum(r * max(0.0, min(t, b) - a) for a, b, r in rates)
iowait = lambda t: 0.1 * max(0.0, min(t, 2005) - 2000)
with open(fn("cpu.jsonl"), "w") as f:
    for t in list(range(995, 1016)) + list(range(1995, 2011)) + list(range(2995, 3011)):
        f.write(json.dumps({"ts": float(t), "cpu_us": int(cum(t) * 1e6), "thr_us": 0, "io_psi_us": int(iowait(t) * 1e6)}) + "\n")
front_t = dt.datetime.fromtimestamp(1010.5, dt.timezone.utc).strftime("%d/%b/%Y:%H:%M:%S +0000")
with open(fn("front.log"), "w") as f:
    f.write(f'1.2.3.4 - - [{front_t}] "POST /api/chat/completions HTTP/1.1" 200 5000 "-" "ua" auth=1 rt=10.400 urt=10.390\n')

out = io.StringIO()
with contextlib.redirect_stdout(out):
    rc = tb.main(["run", "--db", db_path, "--eval", fn("eval.jsonl"), fn("missing.jsonl"), "--gateway", fn("gw.jsonl"), "--journal", fn("journal.txt"),
                  "--stack", "stack-a", "--cpu", fn("cpu.jsonl"), "--front-log", fn("front.log"), "--label", "A", "--json", fn("a.json")])
printed = out.getvalue()
d = json.load(open(fn("a.json")))
turns = {round(t["ts"]): t for t in d["turns"]}
check("exit code 0", rc, 0)
check("copies under a compaction session are not turns; the unanswered one is skipped, not counted", (len(d["turns"]), d["summary"]["turns_skipped_unanswered"]), (4, 1))
A = turns[1000]
check("A total and chain", (A["total_s"], A["chain_s"], A["users"], A["source"]), (10.0, 10.0, 1, "telegram"))
check("A two calls matched, the aux call kept out of the chain", ([c["matched"] for c in A["calls"]], A["aux_calls"]), ([True, True], 1))
check("A call 1: model, ttfb, generation, router pre, hermes gap", (A["calls"][0]["model_s"], A["calls"][0]["ttfb_s"], A["calls"][0]["gen_s"],
      A["calls"][0]["pre_s"], A["calls"][0]["hermes_s"]), (2.4, 0.8, 1.6, 0.1, 0.5))
check("A call 1 prompt tokens and bytes", (A["calls"][0]["ptok"], A["calls"][0]["in_b"], A["calls"][0]["tried"]), (3000, 12000, 1))
check("A call 2: failed try counted as retry, buffered answer has no generation time", (A["calls"][1]["retry_s"], A["calls"][1]["gen_s"],
      A["calls"][1]["buf"], A["calls"][1]["hermes_s"], A["calls"][1]["tried"]), (0.3, None, True, 0.2, 2))
check("A tool: gateway line gives the CPU (3.8 of 5 s) and the class", (A["tools"][0]["name"], A["tools"][0]["gw"], A["tools"][0]["host"], A["tools"][0]["cpu_s"],
      A["tools"][0]["class"], A["tools"][0]["src"]), ("terminal", "transcode", "gpu-a", 3.8, "cpu", "gateway"))
check("A sums: machine 4.6, provider 4.2, external 1.2, unknown 0", (A["machine_s"], A["provider_s"], A["external_s"], A["unknown_s"]), (4.6, 4.2, 1.2, 0.0))
check("A four buckets add up to the human wait", round(A["machine_s"] + A["provider_s"] + A["external_s"] + A["unknown_s"], 2), A["human_s"])
check("A is on an awake stack", A["wake"], None)
check("A web request time is matched by when it ended", A.get("web_rt_s"), 10.4)
B = turns[round(E + 24)]
check("B wake steps: detect 6, admit 2, boot 20, intake 2, wait 30", (B["wake"]["detect_s"], B["wake"]["admit_s"], B["wake"]["boot_s"],
      B["wake"]["intake_s"], B["wake"]["wait_s"]), (6.0, 2.0, 20.0, 2.0, 30.0))
check("B human wait is wake wait + turn: 33", B["human_s"], 33.0)
check("B machine 24.5 (boot, intake, admit, hermes gap), provider 2.5, external 6", (B["machine_s"], B["provider_s"], B["external_s"]), (24.5, 2.5, 6.0))
check("B buckets add up", round(B["machine_s"] + B["provider_s"] + B["external_s"] + B["unknown_s"], 2), B["human_s"])
D = turns[2000]
check("D burst: one turn from the first message, chain from the last", (D["users"], D["burst_s"], D["total_s"], D["chain_s"]), (2, 2.0, 5.0, 3.0))
check("D no router line: its time is unknown, not invented", (D["calls"][0]["matched"], D["model_s"], D["unknown_s"]), (False, 0.0, 3.0))
check("D cgroup figures: a full core, no throttling, disk wait 0.5 s", (D["cpu_s"], D["throttled_s"], D["io_stall_s"]), (5.0, 0.0, 0.5))
Et = turns[3000]
check("E tool name is sanitised, CPU from the cgroup, waiting class", (Et["tools"][0]["name"], Et["tools"][0]["src"], Et["tools"][0]["cpu_s"], Et["tools"][0]["class"]),
      ("?", "cgroup", 0.2, "wait"))
check("E tool wait counted as external", (Et["tools_wait_s"], Et["external_s"]), (3.8, 3.8))
sm = d["summary"]
check("summary: turns, matched calls, aux in windows", (sm["turns"], sm["calls"]["n"], sm["calls"]["matched"], sm["calls"]["aux_in_windows"]), (4, 6, 3, 1))
check("summary: woken group has the wake steps", (sm["woken"]["turns"], sm["woken"]["wake_boot_s"]["p50"], sm["awake"]["turns"]), (1, 20.0, 3))
check("summary: per model figures", (sm["models"]["m1"]["n"], sm["models"]["m1"]["ptok_p50"], sm["models"]["m1"]["ttfb_p50"]), (2, 3000.0, 0.8))
check("kind of turn is the set of tools (gateway commands by name), plain when none", (A["kind"], B["kind"], D["kind"], Et["kind"]),
      ("gateway:transcode", "plain", "plain", "?"))
check("summary: kinds, days and the slowest step", (sm["kinds"]["plain"]["turns"], sm["kinds"]["gateway:transcode"]["turns"], sum(v["turns"] for v in sm["days"].values()),
      sm["slowest"][0]["step"], sm["slowest"][0]["s"], "p90" in sm["all"]["human_s"]), (2, 1, 4, "wake boot", 20.0, True))
check("summary: gateway tool is listed by its command", "gateway:transcode" in sm["tools"], True)
check("no message text, tool argument or hostile tool name reaches the output", (CANARY in printed, CANARY in open(fn("a.json")).read()), (False, False))
check("the json is private (0600)", oct(os.stat(fn("a.json")).st_mode & 0o777), "0o600")

# a journal with two stacks needs --stack; a missing db column set (no finish_reason/tool_name) still reads
buf = io.StringIO()
with contextlib.redirect_stderr(buf):
    rc2 = tb.main(["run", "--db", db_path, "--journal", fn("journal.txt")])
check("journal with several stacks asks for --stack", rc2, 2)
db2 = os.path.join(tmp, "old.db")
c2 = sqlite3.connect(db2)
c2.executescript("create table messages(id integer primary key, session_id text, role text, content text, tool_calls text, timestamp real);"
                 "insert into messages(session_id, role, content, timestamp) values('s','user','x',10),('s','assistant','y',12);")
c2.commit()
c2.close()
with contextlib.redirect_stdout(io.StringIO()):
    rc3 = tb.main(["run", "--db", db2, "--label", "old"])
check("a db without finish_reason reads (no turn has a final answer, none crashes)", rc3, 0)

# two runs side by side
with contextlib.redirect_stdout(io.StringIO()):
    tb.main(["run", "--db", db_path, "--eval", fn("eval.jsonl"), "--gateway", fn("gw.jsonl"), "--label", "B", "--json", fn("b.json")])
cmp = io.StringIO()
with contextlib.redirect_stdout(cmp):
    tb.main(["compare", fn("a.json"), fn("b.json")])
check("compare also lines up the same kinds of turn", "[kind plain]" in cmp.getvalue(), True)
check("compare prints both labels and a ratio per field", ("A" in cmp.getvalue() and "B" in cmp.getvalue() and "machine_s p50" in cmp.getvalue()), True)

# D's buckets add up to the human wait although the turn is a burst (the person's last message starts the wait)
check("D buckets add up (burst: human wait runs from the last message)", (round(D["machine_s"] + D["provider_s"] + D["external_s"] + D["unknown_s"], 2), D["human_s"]), (3.0, 3.0))
check("E buckets add up", round(Et["machine_s"] + Et["provider_s"] + Et["external_s"] + Et["unknown_s"], 2), Et["human_s"])

# a cold start made by hand (a stack with no waker), a first try that failed (its router pre-work still counts), a buffered answer, a restarted counter
R = tb.utc("2026-11-13 11:00:00")
db3 = os.path.join(tmp, "stg.db")
c3 = sqlite3.connect(db3)
c3.executescript("create table messages(id integer primary key autoincrement, session_id text, role text, content text, tool_calls text, tool_name text, "
                 "finish_reason text, timestamp real); create table sessions(id text, source text);")
for ts_u, ts_a in ((R - 500, R - 497), (R + 40, R + 44), (R + 100, R + 102)):
    c3.execute("insert into messages(session_id, role, content, timestamp) values('S',  'user', 'x', ?)", (ts_u,))
    c3.execute("insert into messages(session_id, role, content, finish_reason, timestamp) values('S', 'assistant', 'y', 'stop', ?)", (ts_a,))
c3.commit()
c3.close()
ev3 = [{"ts": R + 42.0, "model": "m0", "pos": 0, "aux": False, "result": "HTTP 500", "s": 1.0, "pre": 0.2},
       {"ts": R + 43.9, "model": "m1", "pos": 1, "aux": False, "result": "ok", "s": 1.5, "ttfb": 1.5, "buf": 1}]
with open(fn("ev3.jsonl"), "w") as f:
    f.write("\n".join(json.dumps(x) for x in ev3) + "\n")
with open(fn("restarts.txt"), "w") as f:
    f.write("# docker start times\n2026-11-13 11:00:00 12.5\nnot a time\n")
with contextlib.redirect_stdout(io.StringIO()):
    tb.main(["run", "--db", db3, "--eval", fn("ev3.jsonl"), "--restarts", fn("restarts.txt"), "--label", "stg", "--json", fn("stg.json")])
t3 = sorted(json.load(open(fn("stg.json")))["turns"], key=lambda t: t["ts"])
check("manual restart: the first turn after it is cold with the stopwatch boot, the others are not", ([(t["wake"] or {}).get("kind") for t in t3], t3[1]["wake"]["boot_s"]),
      ([None, "manual", None], 12.5))
check("cold turn: human wait = boot + chain, boot counts as machine time", (t3[1]["human_s"], t3[1]["machine_s"]), (16.5, 14.0))
check("first try failed: its pre-work is charged, the failure is a retry, a buffered ttfb is not a first token",
      (t3[1]["calls"][0]["pre_s"], t3[1]["calls"][0]["retry_s"], t3[1]["ttfb_s"], t3[1]["calls"][0]["gen_s"]), (0.2, 1.0, 0.0, None))
check("cold turn buckets add up", round(t3[1]["machine_s"] + t3[1]["provider_s"] + t3[1]["external_s"] + t3[1]["unknown_s"], 2), t3[1]["human_s"])
rc5 = io.StringIO()
with contextlib.redirect_stdout(rc5):
    tb.main(["compare", fn("a.json"), fn("stg.json")])
check("compare warns when the two sides did not use the same models", "NOTE: not the same models" in rc5.getvalue(), True)

# counters of a restarted container are never interpolated across the reset, nor across a hole
cr = tb.Cpu([{"ts": 100.0, "cpu_us": 9_000_000}, {"ts": 102.0, "cpu_us": 10_000_000}, {"ts": 104.0, "cpu_us": 300_000}, {"ts": 106.0, "cpu_us": 1_300_000},
             {"ts": 200.0, "cpu_us": 2_000_000}])
check("cpu delta inside normal samples", cr.delta("cpu_us", 100.0, 102.0), 1.0)
check("cpu delta across a counter reset is unknown, not a negative or zero", cr.delta("cpu_us", 101.0, 105.0), None)
check("cpu delta after the reset works again", cr.delta("cpu_us", 104.0, 106.0), 1.0)
check("cpu delta across a hole in the sampler's file is unknown", cr.delta("cpu_us", 110.0, 150.0), None)
check("since: -90m, -2d, epoch", (round(tb.time.time() - tb.since_of("-90m")), round((tb.time.time() - tb.since_of("-2d")) / 3600), tb.since_of("123")), (5400, 48, 123.0))

# the sampler
cg = os.path.join(tmp, "cg")
os.makedirs(cg)
open(os.path.join(cg, "cpu.stat"), "w").write("usage_usec 5000000\nuser_usec 3000000\nthrottled_usec 250000\nnr_throttled 3\n")
open(os.path.join(cg, "memory.current"), "w").write(str(512 * 1048576) + "\n")
open(os.path.join(cg, "io.pressure"), "w").write("some avg10=0.00 avg60=0.00 avg300=0.00 total=777\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=5\n")
out_f = fn("sample.jsonl")
rc4 = sampler.main(["--cgroup", cg, "--out", out_f, "--every", "0", "--count", "2"])
lines = [json.loads(x) for x in open(out_f)]
check("sampler writes numbers only", (rc4, len(lines), lines[0]["cpu_us"], lines[0]["thr_us"], lines[0]["mem_mb"], lines[0]["io_psi_us"], "cpu_psi_us" in lines[0]),
      (0, 2, 5000000, 250000, 512, 777, False))
with contextlib.redirect_stderr(io.StringIO()):
    check("sampler refuses a directory with no cpu.stat", sampler.main(["--cgroup", tmp, "--out", out_f, "--count", "1"]), 2)

# the new fields of the logs that feed it
gateway.log(gateway="selftest")
rec = json.loads(open(os.environ["GATEWAY_LOG"]).read().splitlines()[-1])
check("gateway log carries proc_wall and proc_cpu (numbers)", (isinstance(rec["proc_wall"], float), isinstance(rec["proc_cpu"], float), rec["proc_wall"] >= 0, rec["proc_cpu"] > 0),
      (True, True, True, True))

print("\n".join(fails) or "turn_breakdown_selftest: all ok")
sys.exit(1 if fails else 0)
