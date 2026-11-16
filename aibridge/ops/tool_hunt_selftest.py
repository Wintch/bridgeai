#!/usr/bin/env python3
"""Table test for tool_hunt.py on a tiny synthetic state.db with Hermes's column names: one detector at a time (failures,
identical retries, discovery before the first action, install loops, silent stretches, mid-turn messages and their replays after
a compaction, context size), plus the privacy rules: reasoning columns are never read (an authorizer refuses them), no message
text reaches the output, and the database is opened read-only. Stdlib only: python3 ops/tool_hunt_selftest.py"""
import contextlib, hashlib, io, json, os, sqlite3, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tool_hunt as th

fails = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")


tmp = tempfile.mkdtemp(prefix="th-")
db = f"{tmp}/state.db"
c = sqlite3.connect(db)
c.execute("create table messages (id integer primary key, session_id text, role text, content text, tool_call_id text, tool_calls text,"
          " tool_name text, timestamp real, token_count integer, finish_reason text, reasoning text, reasoning_content text,"
          " reasoning_details text, codex_reasoning_items text, active integer default 1)")
CANARY, PERSON = "CANARY-REASONING-XYZ", "PERSON-WORDS-QRS"
T0 = 1_800_000_000.0
oob_text = th.OOB_MARK + " — a direct message from the user]\n" + PERSON + " mid\n[END]"


def add(sid, role, content, ts, tc=None, name=None, tok=None, fin=None):
    c.execute("insert into messages (session_id, role, content, tool_calls, tool_name, timestamp, token_count, finish_reason, reasoning,"
              " reasoning_content, reasoning_details, codex_reasoning_items) values (?,?,?,?,?,?,?,?,?,?,?,?)",
              (sid, role, content, json.dumps(tc) if tc else None, name, T0 + ts, tok, fin, CANARY, CANARY, CANARY, CANARY))


def call(tool, **args):
    return {"id": "c", "function": {"name": tool, "arguments": json.dumps(args)}}


def run(sid, t, name, args, result, dur=1):
    """An assistant row with one call, then its result row; returns the time after the result."""
    add(sid, "assistant", "", t, tc=[call(name, **args)])
    add(sid, "tool", result, t + dur, name=name)
    return t + dur + 1


OK = json.dumps({"output": "fine", "exit_code": 0})
BAD = json.dumps({"output": "boom", "exit_code": 2})
TRACE = json.dumps({"output": "Traceback (most recent call last):\n  File x", "exit_code": None})

# --- session A: turn 1 hunts for a tool, installs in a loop, retries a failing launch, goes quiet, gets a mid-turn message
A = "sessA-0000000a"
add(A, "user", PERSON + " first question", 0, tok=1000)
t = 1
for cmd in ("which ffmpeg", "ls /usr/local/bin", "tool --help", "pip show torch", "find /usr -name x", "echo hi"):
    t = run(A, t, "terminal", {"command": cmd}, BAD if cmd.startswith("which") else OK)
t = run(A, t, "skill_view", {"name": "x"}, OK)                      # discovery too, but after "echo hi" (the first action)
t = run(A, t, "web_search", {"query": "python library for identify song free"}, OK)
for _ in range(3):
    t = run(A, t, "terminal", {"command": "pip install torch==2.1 torchvision"}, BAD)
for _ in range(4):
    t = run(A, t, "terminal", {"command": "python3 launch.py --fast"}, TRACE)
add(A, "user", oob_text, t, tok=0)
t += 5
for i in range(6):
    t = run(A, t, "terminal", {"command": f"echo {i}"}, OK, dur=25)
add(A, "assistant", "Here you go, done.", t + 1, tok=52000, fin="stop")
# turn 2: quick, text first, a clean call
add(A, "user", PERSON + " second", t + 100, tok=53000)
add(A, "assistant", "Looking.", t + 101)
run(A, t + 102, "gateway", {"command": "gateway song a.mp3"}, OK)
add(A, "assistant", "Found.", t + 110, tok=54000, fin="length")

# --- session B (after a compaction): copies the tail of A's turn 1 at the same instants, plus a compaction note
B = "sessB-0000000b"
add(B, "user", oob_text, 0, tok=0)                                  # moved to the same instant as A's mid-turn message:
c.execute("update messages set timestamp = (select timestamp from messages where session_id = ? and content like ? limit 1)"
          " where session_id = ?", (A, th.OOB_MARK + "%", B))
add(B, "user", th.COMPACTION + " — earlier turns summarised]", t + 200)
add(B, "user", PERSON + " third", t + 300)
add(B, "assistant", "ok", t + 301)
c.commit()
c.close()
before = hashlib.sha256(open(db, "rb").read()).hexdigest()

# --- the detectors
conn = th.open_db(db)
res = th.analyze(th.load_rows(conn))
conn.close()
sa = next(s for s in res["sessions"] if s["session"] == A)
sb = next(s for s in res["sessions"] if s["session"] == B)
t1, t2 = sa["turn_list"]

check("two turns in session A", sa["turns"], 2)
check("calls turn 1", t1["calls"], 6 + 1 + 1 + 3 + 4 + 6)
check("failures: which, 3 pip, 4 traces", t1["failed"], 1 + 3 + 4)
check("failure kinds", t1["fail_kinds"], {"exit 2": 4, "traceback": 4})
check("retries: 2 more pips + 3 more launches", t1["retries"], 2 + 3)
check("worst repeat is the launch, 4 calls, all failed", (t1["worst_repeats"][0]["calls"], t1["worst_repeats"][0]["failed"]),
      (4, 4))
check("worst repeat names the command", t1["worst_repeats"][0]["what"], "python3 launch.py --fast")
check("discovery before the first action", t1["discovery_lead"], 5)
check("discovery in all (5 + skill_view + web_search)", t1["discovery_total"], 7)
check("discovery kinds", t1["discovery_kinds"],
      {"which": 1, "ls-bin": 1, "help": 1, "pkg-query": 1, "find-usr": 1, "skills": 1, "web-capability": 1})
check("install loop counted by manager", t1["installs"], {"pip": 3})
check("install loop flagged, one distinct package set", (t1["install_loop"], t1["install_sets"], t1["install_failed"]),
      (True, {"pip": 1}, 3))
check("silent from the turn start until the first text", t1["silent_max_calls"] >= 20, True)
check("silent stretch has seconds", t1["silent_max_secs"] > 150, True)
check("one mid-turn message in turn 1", len(t1["oob"]), 1)
check("mid-turn message answered after 6 calls", (t1["oob"][0]["answered"], t1["oob"][0]["gap_calls"]), (True, 6))
check("mid-turn gap in seconds", t1["oob"][0]["gap_secs"] >= 150, True)
check("context tokens last and max in turn 1", (t1["ctx_tokens"], t1["ctx_tokens_max"]), (52000, 52000))
check("session context trend", (sa["ctx_first"], sa["ctx_last"], sa["ctx_max"]), (52000, 54000, 54000))
check("odd finish reason shown", t2["odd_finish"], {"length": 1})
check("a short turn is clean", (t2["calls"], t2["failed"], t2["retries"], t2["silent"], t2["discovery_total"]), (1, 0, 0, [], 0))
check("gateway verb in the sequence", t2["sequence"][0][1], "gateway:gateway song")

check("the compaction copy of the mid-turn message was skipped, once", res["oob_replays_skipped"], 1)
check("the copy gives session B no mid-turn message", sb["oob"], 0)
check("compaction note counted, not a turn", (sb["compactions"], sb["turns"]), (1, 2))      # lead rows + "third"
check("rows before the first person message form turn 0", sb["turn_list"][0]["lead"], True)

# an unanswered mid-turn message: text never follows
d2 = f"{tmp}/b.db"
c = sqlite3.connect(d2)
c.execute("create table messages (id integer primary key, session_id text, role text, content text, tool_calls text, tool_name text,"
          " timestamp real, finish_reason text)")
rows = [("user", "hello", None, None, T0), ("user", oob_text, None, None, T0 + 5),
        ("assistant", "", json.dumps([call("terminal", command="ls")]), None, T0 + 6), ("tool", OK, None, "terminal", T0 + 7)]
for r in rows:
    c.execute("insert into messages (session_id, role, content, tool_calls, tool_name, timestamp) values ('s',?,?,?,?,?)", r)
c.commit()
c.close()
conn = th.open_db(d2)
r2 = th.analyze(th.load_rows(conn))
conn.close()
o = r2["sessions"][0]["turn_list"][0]["oob"]
check("a missing column set still loads; unanswered mid-turn message", (len(o), o[0]["answered"], o[0]["gap_calls"]), (1, False, 1))
check("no token_count column: context is an estimate", r2["sessions"][0]["turn_list"][0]["ctx_tokens"], None)
check("estimate present", r2["sessions"][0]["turn_list"][0]["ctx_est"] is not None, True)

# --- result classification
check("clean exit code beats words in the output", th.result_failure(json.dumps({"output": "Traceback in a log line", "exit_code": 0})), None)
check("non-zero exit", th.result_failure(json.dumps({"output": "", "exit_code": 127})), "exit 127")
check("plain-text not found", th.result_failure("bash: foo: command not found"), "not-found")
check("argparse usage error", th.result_failure("usage: x [-h]\nx: error: unrecognized arguments: --y"), "usage")
check("plain success text", th.result_failure("Downloaded 3 files, no problems"), None)
check("install segments in a chain", [m for m, _ in th.installs_in({"name": "terminal", "args": {"command": "cd x && pip3 install -q a b; npm i c"}})],
      ["pip", "npm"])
check("a pipeline is judged by its head", th.discovery_kind({"name": "terminal", "args": {"command": "which ffmpeg | head -1"}}), "which")
check("a real command is not discovery", th.discovery_kind({"name": "terminal", "args": {"command": "ffmpeg -i a.mp4 b.wav"}}), None)
check("a plain web search is not discovery", th.discovery_kind({"name": "web_search", "args": {"query": "weather tomorrow"}}), None)

# --- privacy: no message text, no reasoning, read-only, copy untouched
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = th.main([db])
text_out = buf.getvalue()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rcj = th.main([db, "--json"])
json_out = buf.getvalue()
check("exit codes", (rc, rcj), (0, 0))
for label, out in (("table", text_out), ("json", json_out)):
    check(f"{label} output has no person text", PERSON in out, False)
    check(f"{label} output has no reasoning", CANARY in out, False)
    check(f"{label} output has no assistant or tool text", ("Here you go" in out) or ("fine" in out) or ("boom" in out), False)
check("json parses", isinstance(json.loads(json_out)["sessions"], list), True)
check("table has the flags", all(k in text_out for k in ("install loop:", "silent:", "identical call x4", "mid-turn message", "discovery:")), True)
check("table names the session and the retry command", (A[-8:] in text_out) and ("python3 launch.py --fast" in text_out), True)

check("SELECT names no reasoning column", any(n in ", ".join(th.COLUMNS) for n in th.NEVER), False)
conn = th.open_db(db)
for col in th.NEVER:
    try:
        conn.execute(f"select {col} from messages").fetchall()
        fails.append(f"authorizer let {col} be read")
    except sqlite3.DatabaseError:
        pass
    try:
        conn.execute("select * from messages").fetchall()
        fails.append("authorizer let select * read the reasoning columns")
    except sqlite3.DatabaseError:
        pass
try:
    conn.execute("insert into messages (session_id) values ('x')")
    fails.append("the database was opened writable")
except sqlite3.OperationalError:
    pass
conn.close()
check("the copy is byte-for-byte unchanged", hashlib.sha256(open(db, "rb").read()).hexdigest(), before)

# --- options
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    th.main([db, "--json", "--session", "sessB"])
check("--session keeps one session", [s["session"] for s in json.loads(buf.getvalue())["sessions"]], [B])
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    th.main([db, "--json", "--since", "0.01"])
check("--since counts back from the newest row", [s["session"] for s in json.loads(buf.getvalue())["sessions"]], [B])
with contextlib.redirect_stderr(io.StringIO()):
    check("a missing file is an error code", th.main([f"{tmp}/nope.db"]), 2)

if fails:
    print("\n".join("FAIL " + f for f in fails))
    sys.exit(1)
print("ok tool_hunt selftest")
