#!/usr/bin/env python3
"""Offline checks for ops/early_alert.py: fake clock, fixture workdirs, a telemetry.db with the real schema, a recorder instead of notify
and stubs instead of docker. Run: python3 -I ops/early_alert_selftest.py"""
import contextlib, io, json, os, shutil, sqlite3, sys, tempfile
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
TMP = tempfile.mkdtemp(prefix="ea-")
os.environ.update(EARLY_ALERT_STATE=os.path.join(TMP, "state.json"), EARLY_ALERT_STACKS=os.path.join(TMP, "stacks.json"),
                  EARLY_ALERT_TELEMETRY=os.path.join(TMP, "telemetry.db"), OPS_ENV=os.path.join(TMP, "no-ops.env"))
os.environ.pop("EARLY_ALERT_NOTIFY", None)
import early_alert as ea  # noqa: E402
import key_check  # noqa: E402

NOW = 1_800_000_000
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)[:300]))
    if not cond:
        fails.append(name)


class Rec:
    """Stands in for ops/lib/notify.py."""
    ENV_FILE = os.environ["OPS_ENV"]

    def __init__(self):
        self.sent, self.resolved = [], []

    def alert(self, key, text, quiet=0):
        self.sent.append((key, text, quiet))
        return True

    def resolve(self, key, text=None):
        self.resolved.append((key, text))
        return True


rec = Rec()
ea.notify = rec
DOCKER = {}                                         # brain -> (running, started)
ea.docker_state = lambda brain: DOCKER.get(brain, (False, None))
SCHEMA = """
create table turns(stack, ts real, session, source, model, seconds real, tools int, tool_errors int, failed int, empty int, unique(stack, ts, session));
create table errors(stack, ts real, provider, model, code, unique(stack, ts, provider, model, code));
create table wakes(stack, ts real, reason, seconds real, outcome, unique(stack, ts, outcome));
create table gw(stack, ts real, gateway, host, ok int, fallback int, seconds real, gpu_seconds real, cpu_seconds real, mb_in real, mb_out real, error, down, unique(stack, ts, gateway));
"""


def fresh_db():
    if os.path.exists(ea.TELEMETRY):
        os.remove(ea.TELEMETRY)
    c = sqlite3.connect(ea.TELEMETRY)
    c.executescript(SCHEMA)
    c.commit()
    return c


def new_world(*stacks):
    """Fresh state, db, recorder and workdirs; stacks = (name, extra stack fields). Returns {name: workdir}."""
    for f in (ea.STATE, ea.STATE + ".lock"):
        if os.path.exists(f):
            os.remove(f)
    fresh_db().close()
    rec.sent.clear(), rec.resolved.clear(), DOCKER.clear()
    cfg, dirs = {"stacks": []}, {}
    for name, extra in stacks:
        d = os.path.join(TMP, "w-" + name)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        dirs[name] = d
        cfg["stacks"].append(dict({"name": name, "brain": "b-" + name, "workdir": d}, **extra))
    json.dump(cfg, open(ea.STACKS, "w"))
    return dirs


def line(cat, ago=60, n=1, k=None, v=None, src="router", now=NOW, **extra):
    d = {"ts": now - ago, "cat": cat, "n": n}
    if k is not None:
        d["k"] = k
    if v is not None:
        d["v"] = v
    d["src"] = src
    d.update(extra)
    return json.dumps(d)


def sink(wd, *lines, name=ea.SINK, mode=0o644):
    p = os.path.join(wd, name)
    open(p, "w").write("".join(x + "\n" for x in lines))
    os.chmod(p, mode)


def epoch(wd, name, ago):
    open(os.path.join(wd, name), "w").write(f"{NOW - ago}\n")


def run(*args, now=NOW, notify="1", env=None):
    os.environ["EARLY_ALERT_NOW"] = str(now)
    if notify is None:
        os.environ.pop("EARLY_ALERT_NOTIFY", None)
    else:
        os.environ["EARLY_ALERT_NOTIFY"] = notify
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = ea.main(list(args))
    return rc, out.getvalue(), err.getvalue()


def state():
    try:
        return json.load(open(ea.STATE))
    except OSError:
        return None


def alerts(prefix="early:demo-a"):
    return [s for s in rec.sent if s[0] == prefix]


# ------------------------------------------------------------------ scoring
d = new_world(("demo-a", {}))["demo-a"]
sink(d, *[line("nudge", 100 * i, k="announce", src="patch") for i in range(1, 5)], line("complaint", 200, k="again"), line("deadpage", 300))
rc, out, err = run()
check("incident replay (4 nudges + complaint + deadpage) alerts once", rc == 0 and len(alerts()) == 1, rec.sent)
txt = alerts()[0][1] if alerts() else ""
check("the alert text names the stack, window, counts and the doctor hint",
      all(w in txt for w in ("demo-a", "last 30 min", "promises without action x4", "complaints x1 (again)", "dead page stuck in x1",
                              "stack_doctor.py demo-a", "nothing from the chat", "score 8.0")), txt)
check("alerts are sent with quiet=0 (the collector owns the cooldown)", alerts()[0][2] == 0)
rc, out, err = run(now=NOW + 300)
check("a second run 5 min later is silent (2 h cooldown)", len(alerts()) == 1, rec.sent)
st = state()
check("state remembers last_sent / last_score / open", st and st["demo-a"]["open"] is True and st["demo-a"]["last_score"] == 8.0 and st["demo-a"]["last_sent"] == NOW, st)
check("state file is 0600", (os.stat(ea.STATE).st_mode & 0o777) == 0o600)

for name, lines, want in [
    ("two nudges alone do not alert", [line("nudge", 60, 2, "announce", src="patch")], False),
    ("one complaint alone does not alert", [line("complaint", 60, k="check")], False),
    ("three nudges alone alert", [line("nudge", 60, 3, "announce", src="patch")], True),
    ("two nudges and a complaint alert", [line("nudge", 60, 2, "announce", src="patch"), line("complaint", 90, k="broken")], True),
    ("deadpage alone does not alert (a pasted error title, or a developer asking about a 404, is not a failing bot)", [line("deadpage")], False),
    ("deadpage + a complaint alert", [line("deadpage"), line("complaint", k="broken")], True),
    ("key_notice refused alone alerts", [line("key_notice", k="refused")], True),
    ("key_notice none alone does not", [line("key_notice", k="none")], False),
    ("repeat alone does not (1 point per repeated turn)", [line("repeat")], False),
    ("two repeated turns (the same long message three times) do not alert alone", [line("repeat"), line("repeat", 90)], False),
    ("three repeated turns alert (3 points)", [line("repeat"), line("repeat", 90), line("repeat", 120)], True),
    ("repeat + a complaint alert", [line("repeat"), line("complaint", k="check")], True),
    ("one nudge_ignored + one nudge alert", [line("nudge_ignored", src="patch"), line("nudge", src="patch", k="claim")], True),
    ("per-category cap: 15 nudges count 4, still alert", [line("nudge", 60, 15, "announce", src="patch")], True),
    ("cap: nudge x20 + nothing else = 4 points (not more)", [line("nudge", 60, 20, "announce", src="patch")], True),
    ("events older than the window are ignored", [line("key_notice", k="refused", ago=31 * 60)], False),
    ("a deadpage and a complaint 29 min ago still count", [line("deadpage", ago=29 * 60), line("complaint", ago=29 * 60, k="check")], True),
]:
    d = new_world(("demo-a", {}))["demo-a"]
    sink(d, *lines)
    run()
    check(name, bool(alerts()) == want, rec.sent)
d = new_world(("demo-a", {}))["demo-a"]
sink(d, line("nudge", 60, 20, "announce", src="patch"))
_, out, _ = run("--dry-run", "--json")
check("the per-category cap holds a category at 4 points", json.loads(out)[0]["points"] == {"nudge": 4.0}, out)

# standing conditions: soul_cut and scan_zero alert alone, 24 h cooldown
d = new_world(("demo-a", {}))["demo-a"]
sink(d, line("soul_cut", 100, n=33000, v=32000, src="boot"))
run()
check("soul_cut alone alerts with its own key and text", [s[0] for s in rec.sent] == ["early:demo-a:soul_cut"] and "33000/32000" in rec.sent[0][1], rec.sent)
run(now=NOW + 3600)
check("soul_cut is not repeated within 24 h", len(rec.sent) == 1, rec.sent)
sink(d, line("soul_cut", 100, n=33000, v=32000, src="boot"), line("soul_cut", -(25 * 3600 - 200) + 0, n=33100, v=32000, src="boot"))
run(now=NOW + 25 * 3600 + 400)
check("a new soul_cut line after 24 h alerts again", len(rec.sent) == 2, rec.sent)
d = new_world(("demo-a", {}))["demo-a"]
sink(d, line("scan_zero", 100, v=6, src="jobpush"))
run()
check("scan_zero alone alerts (days from v)", len(rec.sent) == 1 and "6 days" in rec.sent[0][1], rec.sent)
run(now=NOW + 37 * 3600)
check("scan_zero resolves when it ages out (36 h)", rec.resolved and rec.resolved[0][0] == "early:demo-a:scan_zero", rec.resolved)

# model_err only beside another category; telemetry sources
d = new_world(("demo-a", {}))["demo-a"]
c = fresh_db()
c.executemany("insert into errors values(?,?,?,?,?)", [("demo-a", NOW - 60 - i, "p", "m", str(500 + i)) for i in range(20)])
c.commit(), c.close()
run()
check("20 model_err alone never alert", not rec.sent, rec.sent)
sink(d, line("complaint", 60, k="check"))
run()
check("model_err counts once another category is present (2 + 4 capped)", len(alerts()) == 1, rec.sent)
d = new_world(("demo-a", {}))["demo-a"]
c = fresh_db()
c.execute("insert into errors values('demo-a', ?, 'p', 'local-only', '500')", (NOW - 60,))
c.executemany("insert into turns values('demo-a', ?, ?, ?, 'm', 3, 0, 0, ?, ?)",
              [(NOW - 100, "s1", "telegram", 1, 0), (NOW - 120, "s2", "api_server", 0, 1), (NOW - 130, "s3", "cron", 1, 1)])
c.executemany("insert into gw values('demo-a', ?, ?, 'h', ?, 0, 1, 0, 0, 0, 0, '', '')", [(NOW - 50, "enlaces", 0), (NOW - 55, "tts", 0), (NOW - 56, "enlaces", 1)])
c.commit(), c.close()
_, out, _ = run("--dry-run", "--json")
rep = json.loads(out)[0]
check("telemetry: failed turn, empty turn and a dead link counted; background model, cron turns, other gateways and ok links are not",
      rep["counts"] == {"failed_turn": 1, "empty_turn": 1, "links_dead": 1}, rep["counts"])
check("telemetry: failed (2) + empty (2) + link (1) = 5 points alert", rep["score"] == 5.0 and rep["decision"] == "send", rep)
os.remove(ea.TELEMETRY)
d = new_world(("demo-a", {}))["demo-a"]
os.remove(ea.TELEMETRY)
sink(d, line("key_notice", k="refused"))
rc, out, err = run()
check("a missing telemetry.db still scores the sink", rc == 0 and len(alerts()) == 1, (rc, err))
open(ea.TELEMETRY, "w").write("this is not a database")
rc, out, err = run(now=NOW + 3 * 3600)
check("a damaged telemetry.db never raises", rc == 0, (rc, err))

# cooldown, escalation, resolve
MIN = 60
d = new_world(("demo-a", {}))["demo-a"]
sink(d, line("nudge", 60, 3, "announce", src="patch"))
run()
check("first alert, score 3", len(rec.sent) == 1)
t1 = NOW + 29 * MIN
sink(d, line("nudge", 60, 3, "announce", src="patch", now=t1), line("key_notice", k="refused", now=t1), line("complaint", k="check", now=t1),
     line("repeat", n=2, now=t1), line("bad_end", n=3, k="length", now=t1))
run(now=t1)
check("a rise inside 30 min of the last alert does not escalate", len(rec.sent) == 1, rec.sent)
run(now=NOW + 31 * MIN)
check("escalation: score >= last*1.5+2 and 30 min apart sends again", len(rec.sent) == 2 and state()["demo-a"]["last_score"] >= 3 * 1.5 + 2, (rec.sent, state()))
run(now=NOW + 40 * MIN)
check("no repeat right after the escalation", len(rec.sent) == 2, rec.sent)
d = new_world(("demo-a", {}))["demo-a"]
sink(d, line("key_notice", 60, k="refused"))
run()
t2 = NOW + 2 * 3600 + 60
sink(d, line("key_notice", 60, k="refused", now=t2))
run(now=t2)
check("still failing after the 2 h cooldown sends again", len(rec.sent) == 2, rec.sent)
d = new_world(("demo-a", {}))["demo-a"]
sink(d, line("key_notice", 60, k="refused"))
run()
t3 = NOW + 35 * MIN
sink(d, line("complaint", 60, k="check", now=t3))               # the deadpage has aged out: the score is 2
run(now=t3)
check("a score under 3 sends nothing and keeps the alert open", len(rec.sent) == 1 and not rec.resolved and state()["demo-a"]["open"], state())
sink(d)
run(now=NOW + 70 * MIN)                                         # 30 min window empty: score 0 from here
run(now=NOW + 120 * MIN)
check("not resolved before 60 min at score 0", not rec.resolved, rec.resolved)
run(now=NOW + 131 * MIN)
check("resolved once after 60 min at score 0", rec.resolved == [("early:demo-a", "demo-a: back to normal")], rec.resolved)
run(now=NOW + 140 * MIN)
check("resolve is sent only once", len(rec.resolved) == 1 and state()["demo-a"]["open"] is False)
t4 = NOW + 141 * MIN
sink(d, line("key_notice", 60, k="refused", now=t4))
run(now=t4)
check("a new problem after the resolve alerts as new", len(rec.sent) == 2, rec.sent)

# ------------------------------------------------------------------ modes
d = new_world(("demo-a", {}))["demo-a"]
sink(d, line("key_notice", k="refused"))
rc, out, err = run("--dry-run")
check("--dry-run sends nothing and writes no state", not rec.sent and state() is None, (rec.sent, state()))
check("--dry-run prints the table with the would-be text", "== demo-a" in out and "would send" in out and "score 3.0" in out, out)
rc, out, err = run(notify=None)
check("by default (notifications not enabled) nothing is sent and no state is written", not rec.sent and state() is None, (rec.sent, state()))
check("by default the table is printed and says notifications are off", "notifications OFF" in out and "== demo-a" in out, out)
open(os.environ["OPS_ENV"], "w").write("EARLY_ALERT_NOTIFY=1\n")
rc, out, err = run(notify=None)
check("EARLY_ALERT_NOTIFY=1 in ops.env enables sending", len(rec.sent) == 1, rec.sent)
os.remove(os.environ["OPS_ENV"])
_, out, _ = run("--json", "--window", "5", notify="1")
check("--json parses and --window narrows the window", json.loads(out)[0]["stack"] == "demo-a")
check("--stack of an unknown name exits 2", run("--stack", "nope")[0] == 2)

d = new_world(("demo-a", {"early_alert": False}), ("demo-b", {}))
sink(d["demo-a"], line("key_notice", k="refused")), sink(d["demo-b"], line("key_notice", k="refused"))
_, out, _ = run("--dry-run")
check("an early_alert:false stack is scored in dry-run, marked silenced", "== demo-a" in out and "silenced" in out.split("== demo-b")[0], out)
run()
check("an early_alert:false stack is never notified, the other one is", [s[0] for s in rec.sent] == ["early:demo-b"], rec.sent)
d = new_world(("demo-a", {"operator": True}))["demo-a"]
sink(d, line("key_notice", k="refused"))
run()
check("a stack marked operator:true alerts like any other", len(alerts()) == 1)

# ------------------------------------------------------------------ unanswered matrix
def una(awake=True, started=NOW - 7200, human=2400, reply=None, call=2400, expect=True, label="", setup=None):
    d = new_world(("demo-a", {}))["demo-a"]
    DOCKER["b-demo-a"] = (awake, started)
    if human is not None:
        epoch(d, ".last_human", human)
    if reply is not None:
        epoch(d, ".last_reply", reply)
    if call is not None:
        epoch(d, ".last_model_call", call)
    if setup:
        setup(d)
    run()
    got = bool(alerts()) and "no reply for" in alerts()[0][1]
    check("unanswered: " + label, got == expect, (rec.sent, ))


def job_file(d):
    os.makedirs(os.path.join(d, "jobs"))
    open(os.path.join(d, "jobs", "render.json"), "w").write("{}")


def marker(age):
    def f(d):
        p = os.path.join(d, *ea.BUSY_MARKER)
        os.makedirs(os.path.dirname(p))
        open(p, "w").write("")
        os.utime(p, (NOW - age, NOW - age))
    return f


una(label="awake, 40 min, no reply, no model call -> alert", expect=True)
una(awake=False, label="asleep brain -> no alert", expect=False)
una(started=NOW - 100, label="brain up for under 3 min -> no alert", expect=False)
una(call=100, label="a model call 100 s ago (tool loop) -> no alert", expect=False)
una(human=3600, call=3600, reply=60, label="replied after the message -> no alert", expect=False)
una(human=3600, call=3600, reply=4000, label="a reply older than the message -> alert", expect=True)
una(human=4 * 3600, call=4 * 3600, label="older than 3 h -> no alert", expect=False)
una(human=300, call=300, label="only 5 min of silence -> no alert", expect=False)
una(human=1500, call=1500, label="25 min of silence is still under the 30 min limit (a long tool) -> no alert", expect=False)
una(human=None, label="no .last_human -> no alert", expect=False)
una(call=None, label="no .last_model_call (an image without the writers) -> no alert", expect=False)
una(human=3600, call=2000, label="last model call newer than the message counts from it (33 min) -> alert", expect=True)
una(human=3600, call=1500, label="last model call 25 min ago -> no alert", expect=False)
una(label="a registered long job (jobs/*.json) -> no alert", expect=False, setup=job_file)
una(label="a fresh job-scan marker -> no alert", expect=False, setup=marker(600))
una(label="a job-scan marker older than 90 min is a dead run, not a busy stack -> alert", expect=True, setup=marker(2 * 3600))
una(label="an empty jobs dir -> alert", expect=True, setup=lambda d: os.makedirs(os.path.join(d, "jobs")))
d = new_world(("demo-a", {}))["demo-a"]
DOCKER["b-demo-a"] = (True, NOW - 3600)
open(os.path.join(d, ".last_human"), "w").write(f"{NOW + 99999}\n")
epoch(d, ".last_model_call", 900)
run()
check("unanswered: a forged future .last_human is ignored", not rec.sent, rec.sent)

# ------------------------------------------------------------------ absence and hostile files
d = new_world(("demo-a", {}))["demo-a"]
rc, out, err = run()
check("absent sink and epoch files never alert", rc == 0 and not rec.sent and state() and "demo-a" in state(), (rec.sent, err))
shutil.rmtree(d)
rc, out, err = run()
check("an absent workdir does not alert or fail", rc == 0 and not rec.sent, (rc, err))

d = new_world(("demo-a", {}))["demo-a"]
victim = os.path.join(TMP, "victim.jsonl")
open(victim, "w").write(line("key_notice", k="refused") + "\n")
os.symlink(victim, os.path.join(d, ea.SINK))
run()
check("a symlink at the sink is not followed", not rec.sent, rec.sent)
os.remove(os.path.join(d, ea.SINK))
os.mkfifo(os.path.join(d, ea.SINK))
rc, _, _ = run()
check("a FIFO at the sink is skipped without blocking", rc == 0 and not rec.sent)
os.remove(os.path.join(d, ea.SINK))
with open(os.path.join(d, ea.SINK), "wb") as f:
    f.write(os.urandom(512 * 1024))
    f.write(b"\n")
    f.write((line("key_notice", k="refused") + "\n").encode())
run()
check("binary noise before a valid last line: the line still counts", len(alerts()) == 1, rec.sent)
d = new_world(("demo-a", {}))["demo-a"]
with open(os.path.join(d, ea.SINK), "w") as f:
    f.write(line("key_notice", k="refused", ago=3600 * 5) + "\n")
    f.write(("x" * 100 + "\n") * 150000)              # ~15 MB of junk after it
run()
check("a 15 MB file is read by its tail only (old valid line is out of reach, nothing breaks)", not rec.sent, rec.sent)
d = new_world(("demo-a", {}))["demo-a"]
sink(d, json.dumps({"ts": NOW - 5, "cat": "forged", "n": 1}),
     line("complaint", n=99, k="check"), line("complaint", k="Bad Value!"), line("complaint", k="x" * 30),
     json.dumps({"ts": NOW + 3600, "cat": "key_notice", "k": "refused", "n": 1}), json.dumps({"ts": NOW - 2 * 86400, "cat": "key_notice", "k": "refused", "n": 1}),
     json.dumps({"ts": float(NOW - 5), "cat": "key_notice", "k": "refused", "n": 1}), json.dumps({"ts": True, "cat": "key_notice", "k": "refused", "n": 1}),
     json.dumps({"ts": NOW - 5, "cat": "key_notice", "k": "refused", "n": 1, "extra": "text"}), json.dumps({"ts": NOW - 5, "cat": "key_notice", "k": "refused", "n": 0}),
     json.dumps({"ts": NOW - 5, "cat": "key_notice", "k": "refused", "n": 1, "src": "evil"}), json.dumps({"ts": NOW - 5, "cat": "key_notice", "k": "refused", "n": 1, "v": -1}),
     json.dumps([1, 2]), "not json", "", "\x00\x00")
run()
check("forged cat / huge n / bad k / future or ancient ts / float or bool ts / extra key / n=0 / unknown src: every line is skipped",
      not rec.sent, rec.sent)
check("parse_line accepts exactly the writers' shape", ea.parse_line(line("soul_cut", n=30000, v=32000, src="boot"), NOW) is not None
      and ea.parse_line(line("nudge", n=21, src="patch"), NOW) is None and ea.parse_line(line("soul_cut", n=1_000_001), NOW) is None)
d = new_world(("demo-a", {}))["demo-a"]
sink(d, line("complaint", k="sentinelzz"), line("complaint", k="check"), line("key_notice", k="refused"))
run()
check("the alert text holds only table labels and integers (a valid but unknown k is dropped)", len(alerts()) == 1 and "sentinelzz" not in alerts()[0][1]
      and "complaints x2 (check)" in alerts()[0][1], alerts())

# PermissionError -> docker cp fallback (works asleep). A fake `docker` executable on PATH serves `docker cp brain:/workdir/x -` from a
# directory tree (FAKE_DOCKER_ROOT) as a real tar stream, so the real bounded copy runs, not a stub.
FAKE = os.path.join(TMP, "fakebin")
os.makedirs(FAKE)
open(os.path.join(FAKE, "docker"), "w").write('''#!/usr/bin/env python3
import os, sys, tarfile
a = sys.argv[1:]
root = os.environ["FAKE_DOCKER_ROOT"]
if a[:1] != ["cp"]:
    sys.exit(2)
src = a[1].split(":", 1)[1]
open(os.path.join(root, "_cp.log"), "a").write(src + "\\n")
out = sys.stdout.buffer
if os.environ.get("FAKE_DOCKER_HUGE"):
    ti = tarfile.TarInfo("huge")
    ti.size = 10 ** 10
    out.write(ti.tobuf())
    sent = 0
    try:
        while sent < 300 * 2 ** 20:
            out.write(b"\\0" * 65536)
            out.flush()
            sent += 65536
            open(os.path.join(root, "_huge.tmp"), "w").write(str(sent))
            os.replace(os.path.join(root, "_huge.tmp"), os.path.join(root, "_huge.log"))
    except (BrokenPipeError, OSError):
        pass
    sys.exit(0)
host = os.path.join(root, src.lstrip("/"))
if not os.path.exists(host):
    sys.exit(1)
import io
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w") as t:
    t.add(host, arcname=os.path.basename(host))
data = buf.getvalue()
last = max(i for i, c in enumerate(data) if c)
out.write(data[:(last // 512 + 1) * 512 + 1024])      # docker's tar ends with 1 KB of zeros, not python's 10 KB record padding
''')
os.chmod(os.path.join(FAKE, "docker"), 0o755)
DFS = os.path.join(TMP, "dockerfs")
os.environ["FAKE_DOCKER_ROOT"] = DFS
OLD_PATH = os.environ["PATH"]


def fakefs(**files):
    shutil.rmtree(DFS, ignore_errors=True)
    os.makedirs(os.path.join(DFS, "workdir"))
    for name, data in files.items():
        p = os.path.join(DFS, "workdir", name.replace("__", "/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(data)


def cp_calls():
    try:
        return open(os.path.join(DFS, "_cp.log")).read().split()
    except OSError:
        return []


d = new_world(("demo-a", {}))["demo-a"]
fakefs(**{ea.SINK: line("key_notice", k="refused") + "\n"})
real_read_small = ea.read_small


def deny(path, limit):
    if path.endswith(ea.SINK):
        raise PermissionError(path)
    return real_read_small(path, limit)


os.environ["PATH"] = FAKE + os.pathsep + OLD_PATH
ea.read_small = deny
rc, out, err = run()
ea.read_small = real_read_small
check("a 0600 sink is read through docker cp of the brain container", "/workdir/" + ea.SINK in cp_calls() and len(alerts()) == 1, (cp_calls(), rec.sent))
check("the fallback is used for that file only (never docker exec: the fake docker refuses anything but cp)", all(c == "/workdir/" + ea.SINK for c in cp_calls()), cp_calls())

# the copy is bounded: a file the agent made huge (multi-GB) is never buffered, the copy is killed and the file is skipped
os.environ["FAKE_DOCKER_HUGE"] = "1"
shutil.rmtree(DFS, ignore_errors=True)
os.makedirs(DFS)
check("a huge docker cp stream is refused (None) and the copy is killed after about the cap", ea.cp_read("b-demo-a", "/workdir/x") is None
      and int(open(os.path.join(DFS, "_huge.log")).read()) < 2 * 2 ** 20, os.listdir(DFS))
d = new_world(("demo-a", {}))["demo-a"]
ea.read_small = deny
t0 = __import__("time").time()
rc, out, err = run(now=NOW + 5 * 3600)
ea.read_small = real_read_small
check("an unreadable 0600 sink that is huge: no alert, no error, no hang", rc == 0 and not rec.sent and __import__("time").time() - t0 < 20, (rc, err))
os.environ.pop("FAKE_DOCKER_HUGE")
fakefs(**{"small": "x" * 5000, "ok": "hello"})
check("a file over the limit is None even when its tar fits the slack", ea.cp_read("b", "/workdir/small", 1000) is None)
check("a file within the limit is returned whole", ea.cp_read("b", "/workdir/ok", 1000) == b"hello")
check("a missing file is None", ea.cp_read("b", "/workdir/nope") is None)
os.environ["PATH"] = OLD_PATH
check("no docker at all is None, never an exception", (lambda: (os.environ.__setitem__("PATH", "/nonexistent"), ea.cp_read("b", "/workdir/ok"))[1])() is None)
os.environ["PATH"] = OLD_PATH

# jobs and the job-scan marker behind permissions the host does not have: read as headers through the same bounded docker cp
if os.geteuid() != 0:
    os.environ["PATH"] = FAKE + os.pathsep + OLD_PATH
    for label, tree, expect in (("a registered job", {"jobs__render.json": "{}"}, False), ("only other files in jobs/", {"jobs__notes.txt": "x"}, True),
                                ("a fresh job-scan marker", {"jobfinder__data__.jobpush-running": ""}, False)):
        def hide(wd):
            for sub in ("jobs", "jobfinder/data"):
                os.makedirs(os.path.join(wd, sub), exist_ok=True)
                os.chmod(os.path.join(wd, sub), 0)
        fakefs(**tree)
        for root_, _, fs_ in os.walk(DFS):                    # file times on the fake clock: 10 minutes ago
            for f_ in fs_:
                os.utime(os.path.join(root_, f_), (NOW - 600, NOW - 600))
        una(label=f"{label} behind 0700 dirs is seen through docker cp -> " + ("alert" if expect else "no alert"), expect=expect, setup=hide)
        for sub in ("jobs", "jobfinder/data"):
            try:
                os.chmod(os.path.join(TMP, "w-demo-a", sub), 0o755)
            except OSError:
                pass
    os.environ["PATH"] = OLD_PATH

d = new_world(("demo-a", {}))["demo-a"]
ea.read_small = deny
os.environ["PATH"] = "/nonexistent"
rc, out, err = run(now=NOW + 3 * 3600)
ea.read_small = real_read_small
os.environ["PATH"] = OLD_PATH
check("a failing docker cp is not an error", rc == 0, (rc, err))

# telemetry rows are read for the whole --window, not a fixed 2 h
d = new_world(("demo-a", {}))["demo-a"]
c = fresh_db()
c.executemany("insert into errors values(?,?,?,?,?)", [("demo-a", NOW - 3 * 3600 - i, "p", "m", str(i)) for i in range(5)])
c.execute("insert into turns values('demo-a', ?, 's1', 'telegram', 'm', 3, 0, 0, 1, 0)", (NOW - 3 * 3600,))
c.commit(), c.close()
_, out, _ = run("--dry-run", "--json", "--window", "240")
check("--window 240 reads telemetry rows 3 h old too (same lookback as the sink events)", json.loads(out)[0]["counts"].get("failed_turn") == 1, out)
_, out, _ = run("--dry-run", "--json")
check("the default window ignores them", "failed_turn" not in json.loads(out)[0]["counts"], out)

# a once-a-night standing line that arrives a little later each day must not resolve and re-alert
d = new_world(("demo-a", {}))["demo-a"]
sink(d, line("scan_zero", 60, v=5, src="jobpush"))
run()
check("scan_zero alerts", len(rec.sent) == 1, rec.sent)
t5 = NOW + 24 * 3600 + 5 * 60                              # 24 h 5 min later: today's line is just over 24 h old, tomorrow's has not come yet
run(now=t5)
check("the first line is 24 h 5 min old and the next one is not there yet: still standing, no resolve", not rec.resolved and len(rec.sent) == 1, (rec.resolved, rec.sent))
sink(d, line("scan_zero", 60, v=5, src="jobpush"), line("scan_zero", 60, v=6, src="jobpush", now=t5 + 600))
run(now=t5 + 600)
check("tomorrow's line (10 min late) alerts once after the 24 h cooldown, still with no resolve in between", len(rec.sent) == 2 and not rec.resolved, (rec.sent, rec.resolved))

# one unreadable stack does not stop the others
d = new_world(("demo-a", {}), ("demo-b", {}), ("demo-c", {}))
for n in d:
    sink(d[n], line("key_notice", k="refused"))
real_gather = ea.gather


def flaky(s, now, since=None):
    if s["name"] == "demo-a":
        raise OSError("disk exploded")
    return real_gather(s, now, since)


ea.gather = flaky
rc, out, err = run()
check("one failing stack is logged to stderr and skipped, exit 0, the others alert", rc == 0 and "[demo-a] skipped" in err
      and [s[0] for s in rec.sent] == ["early:demo-b", "early:demo-c"], (rc, err, rec.sent))
ea.gather = lambda s, now, since=None: (_ for _ in ()).throw(OSError("x"))
rc, out, err = run(now=NOW + 1)
ea.gather = real_gather
check("exit 1 only when every stack failed", rc == 1, rc)
check("a missing stacks.json fails clearly", (lambda: (os.remove(ea.STACKS), run()[0])[1])() == 1)

# one wrong-language reply on a routed stack is written by the router and by the plugin: it counts once
both = [ea.parse_line(line("wrong_lang", 30, k="ru", src="router"), NOW), ea.parse_line(line("wrong_lang", 28, k="ru", src="plugin"), NOW)]
check("a router line and a plugin line seconds apart are one reply", ea.score(both, NOW)[2].get("wrong_lang") == 1, ea.score(both, NOW))
apart = [ea.parse_line(line("wrong_lang", 600, k="ru", src="router"), NOW), ea.parse_line(line("wrong_lang", 28, k="ru", src="plugin"), NOW)]
check("two replies minutes apart still count twice", ea.score(apart, NOW)[2].get("wrong_lang") == 2, ea.score(apart, NOW))
check("a router line alone (plugin off) and a plugin line alone each count",
      ea.score(both[:1], NOW)[2].get("wrong_lang") == 1 and ea.score(both[1:], NOW)[2].get("wrong_lang") == 1)

print("early_alert selftest: " + ("FAILED: " + "; ".join(fails) if fails else "all ok"))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if fails else 0)
