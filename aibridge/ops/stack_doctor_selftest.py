#!/usr/bin/env python3
"""Offline checks for ops/stack_doctor.py: fixtures instead of a stack (docker cp and docker inspect stubbed), sentinel strings planted in
every field that must never reach the screen. Run: python3 -I ops/stack_doctor_selftest.py"""
import contextlib, io, json, os, shutil, sqlite3, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
TMP = tempfile.mkdtemp(prefix="sd-")
os.environ.update(EARLY_ALERT_STATE=os.path.join(TMP, "state.json"), EARLY_ALERT_STACKS=os.path.join(TMP, "stacks.json"),
                  EARLY_ALERT_TELEMETRY=os.path.join(TMP, "telemetry.db"), STACK_DOCTOR_KEY_STATUS=os.path.join(TMP, "key_status.json"),
                  OPS_ENV=os.path.join(TMP, "none.env"), EARLY_ALERT_NOW="1800000000")
import early_alert as ea  # noqa: E402
import stack_doctor as sd  # noqa: E402

NOW = 1_800_000_000
S = "SENTINEL-PRIVATE-"
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)[:400]))
    if not cond:
        fails.append(name)


wd = os.path.join(TMP, "w")
os.makedirs(wd)
json.dump({"stacks": [{"name": "demo-a", "brain": "b-demo-a", "workdir": wd}]}, open(ea.STACKS, "w"))
for n, ago in ((".last_human", 600), (".last_reply", 700), (".last_model_call", 650)):
    open(os.path.join(wd, n), "w").write(f"{NOW - ago}\n")
ea.docker_state = lambda brain: (True, NOW - 7200)
db = sqlite3.connect(ea.TELEMETRY)
db.executescript("""create table turns(stack, ts real, session, source, model, seconds real, tools int, tool_errors int, failed int, empty int);
create table errors(stack, ts real, provider, model, code);
create table wakes(stack, ts real, reason, seconds real, outcome);
create table gw(stack, ts real, gateway, host, ok int, fallback int, seconds real, gpu_seconds real, cpu_seconds real, mb_in real, mb_out real, error, down);""")
db.execute("insert into wakes values('demo-a', ?, 'telegram', 50, 'ok')", (NOW - 100,))
db.execute("insert into errors values('demo-a', ?, 'p', 'm', '500')", (NOW - 100,))
db.commit(), db.close()
open(ea.SINK and os.path.join(wd, ea.SINK), "w").write(
    json.dumps({"ts": NOW - 100, "cat": "nudge", "n": 2, "k": "announce", "src": "patch"}) + "\n" +
    json.dumps({"ts": NOW - 90, "cat": "complaint", "n": 1, "k": "check", "src": "router"}) + "\n")

EVAL = [{"ts": NOW - 3000 + i * 10, "model": "NVIDIA nemotron-3.5-super", "pos": 0, "mode": "x", "session": S + "session", "turn": "aaaa1111",
         "aux": False, "result": "ok" if i else "HTTP 500", "ttfb": 1.0, "s": 5.5, "finish": "tool_calls" if i < 2 else "stop", "tools": 1 if i < 2 else 0,
         "bad_args": 0, "out": 10, "odd": 2 if i == 1 else 0, "leak": 0} for i in range(3)]
EVAL += [{"ts": NOW - 500, "model": "Gemini flash", "turn": "bbbb2222", "aux": False, "result": "ok", "s": 3, "finish": "stop", "tools": 0, "out": 5,
          "session": S + "s2"},
         {"ts": NOW - 400, "model": "title-model", "turn": "cccc", "aux": True, "result": "ok", "s": 1, "finish": "stop", "session": S + "aux"},
         {"ts": NOW - 300, "model": "Gemini flash", "feedback": 1, "session": S + "fb", "msg": S + "msg-id"},
         {"ts": NOW - 200, "model": S + "weird model name\n with newline", "turn": "dddd", "aux": False, "result": "ok", "s": 1, "finish": S + "finish", "tools": 0,
          "msg": S + "msg"}]
JOBLOG = ("2030-01-01T08:00:00Z mode=noche result=ok exit=0 new=0 kept=0 carried=0 unverified=0 secs=120 sent=0 " + f"secretkey={S}JOB\n"
          "2030-01-01T18:00:00Z mode=nuevo result=ok exit=0 new=0 kept=0 secs=20 sent=0\n"   # a daytime run is not a night: must not add to the streak
          "2030-01-02T08:00:00Z mode=noche result=ok exit=0 new=0 kept=0 carried=0 unverified=0 secs=130 sent=0 store=shared " + f"company={S}CO\n")
JOBLOG = JOBLOG.replace("2030-01-01", "2027-01-14").replace("2030-01-02", "2027-01-15")
FILES = {
    "/workdir/.model-eval.jsonl": "\n".join(json.dumps(r) for r in EVAL).encode() + b"\nnot json\n",
    "/workdir/.keys-status.json": json.dumps({"nvidia": {"ok": True, "at": "2027-01-15T07:00:00+00:00", "last4": S + "L4", "extra": S + "x"},
                                              "gemini": {"ok": False, "at": "2027-01-15T07:00:00+00:00"}}).encode(),
    "/workdir/jobfinder/data/jobpush.log": JOBLOG.encode(),
    "/root/.hermes/SOUL.md": ("é" * 27431).encode(),
    "/root/.hermes/config.yaml": b"model: x\ncontext_file_max_chars: 32000\n",
}
json.dump({"stacks": {"demo-a": {"nvidia:abcd": {"status": "ok", "since": "x", "detail": S + "detail", "notified": None},
                                 "gemini:wxyz": {"status": "rejected", "since": "x", "detail": S + "d2", "notified": None}}}}, open(sd.KEY_STATUS, "w"))
json.dump({"demo-a": {"last_sent": NOW - 1800, "last_score": 6.0, "open": True}}, open(ea.STATE, "w"))
LIMITS = []
ea.cp_read = lambda c, p, limit=None: LIMITS.append(limit) or (FILES.get(p) if c == "b-demo-a" else None)


def run(*args, files=None):
    global FILES
    keep = FILES
    if files is not None:
        FILES = files
        ea.cp_read = lambda c, p, limit=None: LIMITS.append(limit) or (FILES.get(p) if c == "b-demo-a" else None)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = sd.main(list(args))
    FILES = keep
    ea.cp_read = lambda c, p, limit=None: LIMITS.append(limit) or (FILES.get(p) if c == "b-demo-a" else None)
    return rc, out.getvalue(), err.getvalue()


rc, out, err = run("demo-a")
check("exit 0 and every section is on the screen", rc == 0 and all(w in out for w in ("Estado:", "Últimos turnos", "Keys (chequeo del host)",
      "Keys (estado en el stack)", "Señales últimas 2 h", "Búsqueda de empleo", "SOUL")), out)
check("estado: awake, uptime, ages and the wake count", "despierto, prendido hace 2h00" in out and "último mensaje 10m" in out and "despertares hoy 1" in out, out)
check("turns: the multi-call turn is one row, with the model, final finish, summed tools and its failed call",
      "NVIDIA nemotron-3.5-super  fin=stop  llamadas=3  tools=2  16.5s  FALLÓ x1 odd=2" in out, out)
check("turns: aux calls and feedback lines are left out, the other turn is there", "Gemini flash  fin=stop" in out and "title-model" not in out, out)
check("keys: host check shows provider, last 4 and status only", "nvidia …abcd ok" in out and "gemini …wxyz rejected" in out, out)
check("keys: stack status shows provider, ok and time", "nvidia ok 2027-01-15T07:00:00+00:00" in out and "gemini NO" in out, out)
check("signals: counts per category over 2 h, the model error, the score and the last alert",
      "complaint x1" in out and "nudge x2" in out and "model_err x1" in out and "puntaje ahora (30 min): 4.5" in out
      and "último aviso: hace 30m (abierto)" in out, out)
check("job search: whitelisted keys, the age of the line and the streak",
      "mode=noche result=ok exit=0 new=0" in out and "store=shared" in out and "rachas sin novedades: 2" in out, out)
check("SOUL: chars over the cap are flagged (characters, not bytes)", "SOUL 27431/32000 (86%)" in out and "RECORTADO" not in out, out)
check("no sentinel (session, msg, unlisted job key, key extras, detail, odd model or finish value) reaches the screen", S not in out and S not in err, out)
rc, js, _ = run("demo-a", "--json")
d = json.loads(js)
check("every docker cp is bounded (a limit is always passed, never the unbounded copy)", LIMITS and all(x == sd.CP_LIMIT for x in LIMITS), set(LIMITS))
check("--json parses and holds the same sections", rc == 0 and set(d) == {"stack", "estado", "turnos", "claves", "senales", "empleo", "soul"}, js[:200])
check("--json holds no sentinel either", S not in js)
check("--json turns carry only whitelisted fields", all(set(t) == {"ts", "model", "finish", "calls", "tools", "s", "not_ok", "odd", "leak", "bad_args"} for t in d["turnos"]), d["turnos"])
rc, js, _ = run("demo-a", "--n", "1", "--json")
check("--n limits the number of turns", len(json.loads(js)["turnos"]) == 1)
over = dict(FILES, **{"/root/.hermes/SOUL.md": ("x" * 33000).encode()})
_, out2, _ = run("demo-a", files=over)
check("a SOUL over the cap is flagged", "SOUL 33000/32000 (103%)" in out2 and "RECORTADO" in out2, out2)
nocfg = dict(FILES)
del nocfg["/root/.hermes/config.yaml"]
_, out3, _ = run("demo-a", files=nocfg)
check("without a config the default cap is named", "/20000 (por defecto)" in out3, out3)

# missing sources print n/d, never an error
os.remove(ea.STATE)
os.remove(sd.KEY_STATUS)
os.remove(ea.TELEMETRY)
os.remove(os.path.join(wd, ea.SINK))
for n in (".last_human", ".last_reply", ".last_model_call"):
    os.remove(os.path.join(wd, n))
rc, out4, err4 = run("demo-a", files={})
check("every source missing: exit 0, n/d everywhere, no traceback", rc == 0 and out4.count("n/d") >= 8 and "Traceback" not in out4 + err4, out4)
check("missing sources: the sections are still all printed", all(w in out4 for w in ("Estado:", "Últimos turnos", "Señales", "SOUL")), out4)
ea.cp_read = lambda c, p, limit=None: (_ for _ in ()).throw(RuntimeError("docker down"))
rc, out5, err5 = run("demo-a", files=None)
check("a failing docker cp is n/d, not an error", rc == 0 and "Traceback" not in out5 + err5, out5)
rc, out6, err6 = run("nope")
check("an unknown stack exits 2 with a clear message", rc == 2 and "no stack named" in err6 and out6 == "", (rc, err6))

print("stack_doctor selftest: " + ("FAILED: " + "; ".join(fails) if fails else "all ok"))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if fails else 0)
