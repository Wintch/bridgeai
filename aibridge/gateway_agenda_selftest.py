#!/usr/bin/env python3
"""Offline checks for `gateway agenda` (AGENDA.md): the fixed type list, schedule validation (5-field cron, "every Nm|Nh", at least
30 min apart, across midnight), the file (/workdir/.agenda.json: 0600, atomic, never code or a prompt), the POSIX lock on .agenda.lock
held by another process, pause/resume/remove, duplicates, the person's language, and the metadata-only log line.
Run: python3 -I gateway_agenda_selftest.py"""
import contextlib, importlib.util, io, json, os, stat, subprocess, sys, tempfile, threading, time
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
os.environ.update(GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log", GATEWAY_WORKDIR=f"{tmp}/workdir",
                  HERMES_TZ="America/Argentina/Buenos_Aires")
os.environ.pop("AGENDA_FILE", None)
os.makedirs(f"{tmp}/workdir")
json.dump({}, open(f"{tmp}/gw.json", "w"))
spec = importlib.util.spec_from_file_location("gw", f"{HERE}/gateway.py")
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)
AG = f"{tmp}/workdir/.agenda.json"

fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def lang(code):
    json.dump({"lang": code}, open(f"{tmp}/prefs.json", "w"))


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = gw.cmd_agenda(list(argv))
    return rc, out.getvalue().strip()


def entries():
    return json.load(open(AG))["entries"]


lang("es")
check("the file is /workdir/.agenda.json and the lock /workdir/.agenda.lock", gw.AGENDA_FILE == AG and gw._agenda_lock_path() == f"{tmp}/workdir/.agenda.lock")
check("the types are kept in one place, with the reminder's text", list(gw.AGENDA_TYPES) == ["subs", "jobnight", "revista", "recordatorio"]
      and gw.AGENDA_TYPES["recordatorio"] == {"text": True})

# --- schedules ------------------------------------------------------------------------------------------------------
S = gw.agenda_schedule
check("cron: daily, weekdays, ranges, steps, lists, names", [S(x)[0] for x in ("30 4 * * *", "0 9 * * 1-5", "0 */3 * * *", "0,30 8 * * mon", "15 7 1 jan,jul *", "0 9 * * 7")]
      == ["30 4 * * *", "0 9 * * 1-5", "0 */3 * * *", "0,30 8 * * mon", "15 7 1 jan,jul *", "0 9 * * 7"])
check("every: minutes and hours, normalized", [S(x)[0] for x in ("every 30m", "every 90m", "every 2h", "Every 60 min", "every 1 hour")]
      == ["every 30m", "every 90m", "every 2h", "every 1h", "every 1h"])
check("too often is refused (every, cron minutes, across midnight)", [S(x)[1] for x in ("every 29m", "*/20 * * * *", "* * * * *", "0,15 9 * * *", "50 23 * * *")][:4]
      == [("often", 30)] * 4 and S("50 23 * * *")[0] == "50 23 * * *" and S("10,50 0,23 * * *")[1] == ("often", 30))
check("a malformed schedule is refused", all(S(x)[1] == ("sched", 0) for x in ("", "0 9 * *", "60 9 * * *", "0 24 * * *", "0 9 32 * *", "0 9 * 13 *",
                                                                                  "0 9 * * 8", "0 9 * * funday", "5-1 * * * *", "*/0 * * * *", "0 9 * * * *", "@daily", "every", "rm -rf /")), "")
check("a day that month never has is refused", S("0 9 31 2 *")[1] == ("never_runs", 0) and S("0 9 29 2 *")[0] == "0 9 29 2 *")
check("every 0h is too often, beyond a week too rare", S("every 0h")[1] == ("often", 30) and S("every 200h")[1] == ("rare", 168))

# --- add, list ------------------------------------------------------------------------------------------------------
rc, out = run("list")
check("an empty agenda says so (es)", rc == 0 and out == "Tu agenda está vacía.", out)
rc, out = run("add", "recordatorio", "0 9 * * 1-5", "--param", "text=tomar agua\nahora", "--label", "agua")
check("add a reminder: id a1, short answer in Spanish with the 🕖 mark", rc == 0 and out.startswith("Agendado a1: «agua» (recordatorio), 0 9 * * 1-5.") and "🕖 Programado" in out, out)
e = entries()[0]
check("the entry has exactly the agreed fields, the text on one line, never code or a prompt",
      set(e) == {"id", "type", "schedule", "params", "label", "created", "paused", "once", "tz", "last_run", "last_state"}
      and e["params"] == {"text": "tomar agua ahora"} and e["paused"] is False and e["last_run"] is None and e["tz"] == "America/Argentina/Buenos_Aires", str(e))
check("the file is 0600 and no temp file is left", stat.S_IMODE(os.stat(AG).st_mode) == 0o600
      and sorted(os.listdir(f"{tmp}/workdir")) == [".agenda.json", ".agenda.lock"], str(os.listdir(f"{tmp}/workdir")))
rc, out = run("add", "recordatorio", "0 9 * * 1-5", "--param", "text=tomar agua ahora")
check("the same type, schedule and params again is not repeated", rc == 0 and "Ya está en la agenda: a1" in out and len(entries()) == 1, out)
rc, out = run("add", "subs", "every 3h")
check("add subs with a default label in the person's language", rc == 0 and "«subtítulos nuevos» (subs), every 3h" in out and entries()[1]["params"] == {}, out)
rc, out = run("add", "jobnight", "30 4 * * *", "--once")
check("--once is kept on a cron schedule", rc == 0 and entries()[2]["once"] is True and ", una sola vez" in out, out)
rc, out = run("add", "revista", "every 2h", "--once")
check("--once with every is refused", rc == 2 and "--once" in out and len(entries()) == 3, out)

# --- refusals -------------------------------------------------------------------------------------------------------
rc, out = run("add", "backup", "0 3 * * *")
check("an unknown type is refused and the valid ones are listed", rc == 2 and "backup" in out and "subs, jobnight, revista, recordatorio" in out, out)
rc, out = run("add", "recordatorio", "0 9 * * *")
check("a reminder without its text is refused", rc == 2 and "--param text=" in out, out)
rc, out = run("add", "subs", "every 3h", "--param", "cmd=rm -rf /")
check("a parameter the type does not take is refused (nothing to run is ever stored)", rc == 2 and "no lleva --param cmd" in out, out)
rc, out = run("add", "recordatorio", "0 9 * * *", "--param", "text")
check("a parameter without k=v is refused", rc == 2 and "k=v" in out, out)
rc, out = run("add", "subs", "*/5 * * * *")
check("too often is refused with the minimum", rc == 2 and "30 min" in out, out)
rc, out = run("add", "subs", "every 3h", "--bogus")
check("an unknown option points to the help", rc == 2 and "gateway help agenda" in out, out)
check("nothing refused was written", len(entries()) == 3)

# --- pause, resume, remove --------------------------------------------------------------------------------------------
rc, out = run("pause", "a2")
check("pause", rc == 0 and out == "En pausa: a2 (subtítulos nuevos)." and entries()[1]["paused"] is True, out)
rc, out = run("pause", "a2")
check("pause twice says so, rc 0", rc == 0 and "ya estaba en pausa" in out, out)
rc, out = run("list")
check("list shows every entry, the paused one marked, never run yet", rc == 0 and out.splitlines()[0].startswith("Tu agenda") and "• a2 · subtítulos nuevos · subs · every 3h · en pausa" in out
      and "a1 · agua (text=tomar agua ahora) · recordatorio" in out and "todavía no corrió" in out, out)
rc, out = run("resume", "a2")
check("resume", rc == 0 and "Reanudada: a2" in out and entries()[1]["paused"] is False, out)
rc, out = run("remove", "a9")
check("an unknown id", rc == 2 and "a9" in out, out)
rc, out = run("borrar", "a3")
check("remove (Spanish alias)", rc == 0 and "Borrada de la agenda: a3" in out and [e["id"] for e in entries()] == ["a1", "a2"], out)
rc, out = run("add", "revista", "30 7 * * *")
check("ids never come back after a remove", rc == 0 and entries()[-1]["id"] == "a4", out)

# --- what the runner writes is shown --------------------------------------------------------------------------------
d = json.load(open(AG))
d["entries"][0].update(last_run=int(time.time()) - 60, last_state="listo")
json.dump(d, open(AG, "w"))
rc, out = run("list")
check("the runner's last_run and last_state are shown", "a1 · agua" in out and "última: " in out and " bien" in out.splitlines()[1], out)

# --- languages --------------------------------------------------------------------------------------------------------
lang("ru")
rc, out = run("pause", "a1")
check("Russian", rc == 0 and out.startswith("На паузе: a1"), out)
lang("en")
rc, out = run("list")
check("English", rc == 0 and out.startswith("Your agenda") and "paused" in out and "🕖 Scheduled" in out, out)
rc, out = run("add", "nope", "every 1h")
check("English refusal lists the types", rc == 2 and "Types: subs, jobnight, revista, recordatorio." in out, out)

# --- the lock: POSIX, held by another process (the runner on the always-on space) -------------------------------------------
holder = subprocess.Popen([sys.executable, "-c", "import fcntl, sys; f = open(sys.argv[1], 'r+'); fcntl.lockf(f, fcntl.LOCK_EX); "
                           "print('held', flush=True); sys.stdin.readline()", f"{tmp}/workdir/.agenda.lock"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
holder.stdout.readline()
done = []
w = threading.Thread(target=lambda: done.append(run("resume", "a1")))
t0 = time.monotonic()
w.start()
time.sleep(1.0)
check("a change waits while another process holds the lock", not done)
holder.stdin.close(); holder.wait(timeout=10)
w.join(timeout=30)
check("and is made once it is released", bool(done) and done[0][0] == 0 and time.monotonic() - t0 >= 0.9 and entries()[0]["paused"] is False, str(done))

# --- a damaged file is kept aside, never written over ---------------------------------------------------------------
open(AG, "w").write("{not json")
rc, out = run("add", "subs", "every 4h")
check("a damaged agenda is set aside as .bad and a new one starts", rc == 0 and os.path.exists(AG + ".bad") and [e["type"] for e in entries()] == ["subs"], out)

# --- the log line: metadata only --------------------------------------------------------------------------------------
lines = [json.loads(x) for x in open(f"{tmp}/log") if '"agenda"' in x]
check("every call logs one line with sub, type and rc only", lines and all(set(x) <= {"cmd", "sub", "type", "rc", "ts"} for x in lines)
      and not any("agua" in json.dumps(x) or "every" in json.dumps(x) for x in lines), str(lines[:3]))

# --- the help and the verb table ------------------------------------------------------------------------------------
check("gateway help agenda shows its usage lines", "agenda" in gw.usage_areas() and any("never a Hermes cron" in x for x in gw.usage_areas()["agenda"]))
r = subprocess.run([sys.executable, "-I", f"{HERE}/gateway.py", "agenda", "list"], capture_output=True, text=True, timeout=60, env=dict(os.environ))
check("`gateway agenda list` runs from the command line", r.returncode == 0 and "Your agenda" in r.stdout, r.stdout + r.stderr)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("gateway_agenda_selftest: all ok")
