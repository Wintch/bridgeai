#!/usr/bin/env python3
"""Offline test of the analyst (ops/analyst/analyst.py, stage 1): the reader that runs inside the throwaway container (metadata only, never text),
each detector, the watermark (nothing is analysed twice), the dedupe, the private files, the report, and the hook that runs it.

Run from anywhere:  python3 -I ops/analyst/analyst_selftest.py
"""
import importlib.util, json, os, sqlite3, stat, subprocess, sys, tempfile, time
import atexit as _a, shutil as _s, signal as _g
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_a.register(_s.rmtree, tempfile.tempdir, True)
_g.signal(_g.SIGTERM, lambda *_: sys.exit(143))
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("analyst", os.path.join(HERE, "analyst.py"))
an = importlib.util.module_from_spec(spec); spec.loader.exec_module(an)
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

SECRET = "mi-clave-secreta-12345 y el telefono 555-0100"
NOW = 1_900_000_000.0

# ---- the reader, run against a throwaway state.db with the stack's real columns
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "state.db")
c = sqlite3.connect(db)
c.execute("create table messages (id integer primary key, session_id text, role text, content text, tool_call_id text, tool_calls text, tool_name text, "
          "effect_disposition text, timestamp real, token_count integer, finish_reason text)")
c.execute("create table session_model_usage (session_id text, model text, task text, api_call_count integer, input_tokens integer, output_tokens integer, "
          "cache_read_tokens integer, reasoning_tokens integer)")
rows = [
    (1, "S1", "user", "hola, " + SECRET, None, "[]", None, None, NOW, 5, None),
    (2, "S1", "assistant", "Привет, всё готово", None, '[{"function":{"name":"terminal"}}]', None, None, NOW + 1, 9, None),
    (3, "S1", "tool", '{"output": "[Command timed out after 180s]", "exit_code": 124, "error": null}', "t1", None, "terminal", None, NOW + 181, 3, None),
    (4, "S1", "tool", '{"success": false, "error": "Skill \'website\' is disabled. Enable it"}', "t2", None, "skill_view", None, NOW + 182, 3, None),
    (5, "S1", "assistant", "Готово, я всё сделал, проверил результат и сохранил все изменения, можно смотреть. " + SECRET, None, "[]", None, None, NOW + 190, 12, "stop"),
]
c.executemany("insert into messages values (?,?,?,?,?,?,?,?,?,?,?)", rows)
c.executemany("insert into session_model_usage values (?,?,?,?,?,?,?,?)", [
    ("S1", "local-first", "", 3, 18000, 900, 40000, 400),
    ("S1", "nvidia/x", "title_generation", 1, 250, 800, 0, 760),
])
c.commit(); c.close()
env = dict(os.environ, ANALYST_DB=db, ANALYST_AFTER="0")
r = subprocess.run([sys.executable, "-c", an.READER], env=env, capture_output=True, text=True)
meta = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {}
chk(r.returncode == 0 and meta.get("max_id") == 5 and len(meta.get("messages", [])) == 5, "reader: reads the new messages and says the last id")
chk("mi-clave" not in r.stdout and "555-0100" not in r.stdout and "Привет" not in r.stdout and "hola" not in r.stdout,
    "reader: the text of the conversation is not in what it prints (metadata only)")
m = {x["id"]: x for x in meta["messages"]}
chk(m[1]["script"] == "latin" and m[2]["script"] == "ru" and m[5]["script"] == "ru", "reader: a language class per message, no text")
chk(m[3]["err"] == "timeout" and m[4]["err"] == "skill_disabled" and m[3]["tool"] == "terminal", "reader: a short error class for a tool result")
chk(m[2]["calls"] is True and m[5]["calls"] is False, "reader: whether the assistant message asked for a tool")
r2 = subprocess.run([sys.executable, "-c", an.READER], env=dict(env, ANALYST_AFTER="3"), capture_output=True, text=True)
chk(len(json.loads(r2.stdout.strip().splitlines()[-1])["messages"]) == 2, "reader: only what is after the mark")
open(os.path.join(tmp, "x"), "w").close()

# ---- detectors
cfg = dict(an.DEFAULTS, stacks=["demo"], stack_lang={"demo": "ru"})
def M(i, role, ts, **k):
    d = {"id": i, "sid": "20261120_000000_abcdef12", "role": role, "tool": "", "ts": NOW + ts, "tok": 1, "fin": "", "len": 5, "calls": False}
    d.update(k); return d
f = an.analyze("demo", [M(1, "user", 0, script="latin")], [], cfg, NOW + 1000)
chk([x["detector"] for x in f] == ["unanswered"] and f[0]["severity"] == "high", "unanswered: the last message is the person's and it is old")
f = an.analyze("demo", [M(1, "user", 0, script="latin")], [], cfg, NOW + 10)
chk(f == [], "unanswered: a recent message is not (the turn may still run)")
turn = [M(1, "user", 0, script="latin"), M(2, "assistant", 45, script="ru")]
f = an.analyze("demo", turn, [], cfg, NOW + 100)
chk([x["detector"] for x in f] == ["slow_turn"] and f[0]["evidence"]["seconds"] == [45], "slow_turn: 45 s from the message to the answer")
f = an.analyze("demo", [M(1, "user", 0), M(2, "assistant", 3, calls=True), M(3, "tool", 260, tool="terminal"), M(4, "assistant", 262, calls=True),
                        M(5, "tool", 520, tool="terminal"), M(6, "assistant", 521)], [], cfg, NOW + 600)
chk(any(x["detector"] == "long_tool" and x["count"] == 2 for x in f), "long_tool: two waits of 150 s or more are one finding")
f = an.analyze("demo", [M(i, "tool", i, tool="terminal", err="timeout") for i in (1, 2, 3)], [], cfg, NOW)
chk(len(f) == 1 and f[0]["detector"] == "tool_errors" and f[0]["count"] == 3 and f[0]["severity"] == "medium" and "tiempo" in f[0]["proposal"],
    "tool_errors: grouped by tool and class, with the fix in the language of the log")
f = an.analyze("demo", [M(1, "tool", 1, tool="skill_view", err="skill_disabled")], [], dict(cfg, lang="en"), NOW)
chk("pack disabled" in f[0]["proposal"], "tool_errors: the proposal follows the configured language (en)")
usage = [{"sid": "S", "model": "local-first", "task": "", "calls": 4, "inp": 20000, "out": 100, "cache": 60000, "reason": 0},
         {"sid": "S", "model": "nvidia/x", "task": "title_generation", "calls": 1, "inp": 250, "out": 800, "cache": 0, "reason": 760}]
f = an.analyze("demo", [M(1, "user", 0)], usage, cfg, NOW)
names = [x["detector"] for x in f]
chk("heavy_prompt" in names and "title_reasoning" in names and next(x for x in f if x["detector"] == "heavy_prompt")["evidence"]["avg_tokens_per_call"] == 20000,
    "usage: the prompt weight per call and the reasoning spent on titles")
chk("heavy_prompt" not in [x["detector"] for x in an.analyze("demo", [M(1, "user", 0)], [dict(usage[0], inp=1000, cache=2000)], cfg, NOW)], "heavy_prompt: a light prompt is fine")
lang = [M(1, "user", 0, script="latin"), M(2, "assistant", 1, script="ru"), M(3, "user", 2, script="latin"), M(4, "assistant", 3, script="ru"),
        M(5, "user", 4, script="latin"), M(6, "assistant", 5, script="ru")]
chk(any(x["detector"] == "lang_anchor" and x["count"] == 3 for x in an.analyze("demo", lang, [], cfg, NOW + 100)), "lang_anchor: three Latin messages answered in the stack's language")
chk(not any(x["detector"] == "lang_anchor" for x in an.analyze("other", lang, [], cfg, NOW + 100)), "lang_anchor: only for a stack configured with a language")
chk(an.analyze("demo", [M(1, "assistant", 1, fin="interrupted_during_api_call")], [], cfg, NOW)[0]["detector"] == "interrupted", "interrupted: noted as info")
blob = json.dumps(an.analyze("demo", rows_meta := meta["messages"], meta["usage"], cfg, NOW + 1000), ensure_ascii=False)
chk("mi-clave" not in blob and "555-0100" not in blob and "Привет" not in blob, "no finding carries text from the conversation")
chk(sorted({x["signature"] for x in an.analyze("demo", rows_meta, meta["usage"], cfg, NOW + 1000)}) == sorted(x["signature"] for x in an.analyze("demo", rows_meta, meta["usage"], cfg, NOW + 1000)),
    "signatures are stable between runs")

# ---- run_stack: the watermark, the dedupe, the files
log = os.path.join(tmp, "log")
cfg = dict(an.DEFAULTS, stacks=["demo"], log_dir=log, stack_lang={"demo": "ru"})
batches = {"after": None}
def reader_for(messages, usage_, max_id):
    def rd(root, stack, after, image):
        batches["after"] = after
        return {"max_id": max_id, "messages": [x for x in messages if x["id"] > after], "usage": usage_}
    return rd
msgs = [M(1, "user", 0, script="latin"), M(2, "assistant", 2, calls=True), M(3, "tool", 300, tool="terminal", err="timeout"), M(4, "assistant", 301)]
out = an.run_stack("demo", cfg, tmp, now=NOW + 5000, reader=reader_for(msgs, [], 4))
chk("finding(s) logged" in out and os.path.exists(os.path.join(log, "demo.jsonl")), "run_stack: the findings are appended to <stack>.jsonl")
chk(stat.S_IMODE(os.stat(log).st_mode) == 0o700 and stat.S_IMODE(os.stat(os.path.join(log, "demo.jsonl")).st_mode) == 0o600
    and stat.S_IMODE(os.stat(os.path.join(log, ".mark-demo")).st_mode) == 0o600, "run_stack: a private folder (700) and private files (600)")
chk(open(os.path.join(log, ".mark-demo")).read() == "4", "run_stack: the mark is the last message analysed")
n = len(open(os.path.join(log, "demo.jsonl")).read().splitlines())
out = an.run_stack("demo", cfg, tmp, now=NOW + 6000, reader=reader_for(msgs, [], 4))
chk(batches["after"] == 4 and "waiting for" in out and len(open(os.path.join(log, "demo.jsonl")).read().splitlines()) == n, "run_stack: nothing new, nothing analysed twice, nothing logged")
msgs2 = msgs + [M(5, "user", 400, script="latin"), M(6, "assistant", 401, calls=True), M(7, "tool", 700, tool="terminal", err="timeout"), M(8, "assistant", 701)]
out = an.run_stack("demo", cfg, tmp, now=NOW + 7000, reader=reader_for(msgs2, [], 8))
chk(batches["after"] == 4 and "already known" in out, "run_stack: new messages are read from the mark, a known problem is not logged again within the dedupe days")
rows = [json.loads(l) for l in open(os.path.join(log, "demo.jsonl"))]
chk(all(r["status"] == "new" and r["stack"] == "demo" and {"ts", "detector", "severity", "signature", "count", "evidence", "proposal"} <= set(r) for r in rows), "run_stack: every line has the fields the operator triages by")
out = an.run_stack("demo", cfg, tmp, now=NOW + 7000 + 8 * 86400, reader=reader_for(msgs2 + [M(9, "user", 900), M(10, "assistant", 901), M(11, "user", 902), M(12, "assistant", 903, calls=True)], [], 12))
chk(batches["after"] == 8 and "finding" in out, "run_stack: after the dedupe days the same problem can be logged again")
chk(an.run_stack("nope", cfg, tmp, reader=reader_for([], [], 0)).startswith("not reviewed"), "run_stack: a stack not listed in the config is not touched")
before = open(os.path.join(log, ".mark-demo")).read()
def broken(*a, **k): raise RuntimeError("docker down")
try:
    an.run_stack("demo", cfg, tmp, reader=broken); raised = False
except RuntimeError:
    raised = True
chk(raised and open(os.path.join(log, ".mark-demo")).read() == before, "run_stack: a failing reader leaves the mark where it was (analysed again next time)")
dry = an.run_stack("demo", dict(cfg, log_dir=os.path.join(tmp, "log2")), tmp, dry=True, now=NOW + 5000, reader=reader_for(msgs, [], 4))
chk(dry.startswith("dry run") and not os.path.exists(os.path.join(tmp, "log2", ".mark-demo")), "dry run: shows what it would log and writes no mark")

# ---- seed: a stack with history starts from now
sl = dict(cfg, log_dir=os.path.join(tmp, "log3"))
out = an.seed("demo", sl, tmp, reader=reader_for(msgs2, [], 8))
chk(out.startswith("seeded at message 8") and open(os.path.join(tmp, "log3", ".mark-demo")).read() == "8" and not os.path.exists(os.path.join(tmp, "log3", "demo.jsonl")),
    "seed: marks what exists as seen, logs nothing")
out = an.run_stack("demo", sl, tmp, now=NOW + 9000, reader=reader_for(msgs2, [], 8))
chk(batches["after"] == 8 and "waiting for" in out, "seed: the next run reads only what comes after")
chk(an.seed("nope", sl, tmp, reader=reader_for([], [], 0)).startswith("not reviewed"), "seed: a stack that is not listed is not touched")

# ---- report, main and the hook
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    an.report(cfg, None, "new")
chk("tool_errors" in buf.getvalue() and "finding(s)" in buf.getvalue() and "id=" in buf.getvalue(), "report: lists the open findings, most severe first")
cfgf = os.path.join(tmp, "analyst.json"); json.dump(cfg, open(cfgf, "w"))
chk(an.main(["--stack", "../etc", "--config", cfgf]) == 2, "main: a stack name that is not a name is refused")
hook = os.path.join(os.path.dirname(HERE), "wake", "on_sleep.d", "60-analyst")
chk(subprocess.run(["bash", "-n", hook]).returncode == 0 and os.access(hook, os.X_OK), "on_sleep.d/60-analyst: valid shell and executable")
src = open(hook).read()
chk("analyst.json" in src and "WAKE_NAME" in src and "exec python3 ops/analyst/analyst.py" in src, "on_sleep.d/60-analyst: runs the analyst for the stack that went to sleep, only when configured")

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
