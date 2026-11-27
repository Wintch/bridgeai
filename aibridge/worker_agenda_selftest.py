#!/usr/bin/env python3
"""Offline test of the always-on agenda runner (workers/worker.py agenda-tick, workers/agenda_file.py; AGENDA.md, WORKERS.md section 11).

No container, no network: a fake `docker` first in PATH (it runs `python3 -` scripts with this python3 on the mounted folders, runs the
real trabajos.py for `trabajos registrar`, plays the subs container), and a fake Telegram Bot API on 127.0.0.1.
Covers: the schedule parser is still gateway.py's; due times (cron in the entry's zone, day-of-month OR weekday, weekday 7, `every`,
a missed time runs once, the hour going back runs once, paused and bad entries never due); the start write is under the POSIX lock
on .agenda.lock (held by another process) and never starts one due time twice; a reminder is sent through the stack's bot with the
🕖 Programado header in the person's language, a `once` entry is paused after it; `trabajos registrar --origen programado` runs in a
one-shot without network with the right arguments and lands in the person's ledger; the omitido reasons (not_configured, job_active,
busy, bad_entry) and fallo no_bot; the fixed timer goes quiet while the agenda holds its type; a long type runs detached; the agenda
writes through a container when the file is not this user's; no reminder text, token or label in the events.
Run: python3 -I worker_agenda_selftest.py
"""
import datetime
import http.server
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "workers"))
import agenda_file  # noqa: E402
import worker  # noqa: E402

FAILS = []


def ok(cond, what, detail=""):
    print(("ok   " if cond else "FAIL ") + what + ("" if cond else f"  {detail}"))
    if not cond:
        FAILS.append(what)


TG_TOKEN = "4343:fake-bot-token-agenda-selftest"
TEXT_MARK = "REMINDERTEXT88"
LABEL_MARK = "aguaLABEL"

FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, sys
ctl = os.environ["FAKE_CTL"]
a = sys.argv[1:]
with open(os.path.join(ctl, "docker.log"), "a") as f:
    f.write(json.dumps(a) + "\n")
if a[0] != "run":
    sys.exit(0)
VAL = {"--name", "--restart", "--network", "--memory", "--memory-swap", "--cpus", "--pids-limit", "--security-opt", "--cap-drop",
       "--cap-add", "--label", "-v", "-e", "--entrypoint", "--user"}
mounts, entry, i = {}, None, 1
while i < len(a) and a[i].startswith("-"):
    k = a[i]
    if "=" in k:
        i += 1; continue
    if k in VAL:
        v = a[i + 1]
        if k == "-v":
            p = v.split(":"); mounts[p[1]] = p[0]
        elif k == "--entrypoint":
            entry = v
        i += 2
    else:
        i += 1
image, rest = a[i], a[i + 1:]
def host(p):
    for dst in sorted(mounts, key=len, reverse=True):
        if p == dst or p.startswith(dst + "/"):
            return mounts[dst] + p[len(dst):]
    return p
if entry == "python3" and rest[:1] == ["-"]:             # agenda_file.py, the space reader, apply.py
    os.execvp("python3", ["python3", "-"] + [host(x) for x in rest[1:]])
if entry == "python3" and rest[:1] == ["/usr/local/bin/trabajos"]:
    wd = host("/workdir")
    os.environ.update(TRABAJOS_DIR=os.path.join(wd, ".trabajos"), AIBRIDGE_PREFS=os.path.join(wd, ".prefs.json"))
    os.execvp("python3", ["python3", os.environ["FAKE_TRABAJOS"]] + rest[1:])
if entry == "/bin/sh":                                    # a worker type's container (subs)
    out = os.path.join(ctl, "subs_out")
    if os.path.exists(out):
        sys.stdout.write(open(out).read())
    sys.exit(0)
sys.exit(125)
'''


class Fake(http.server.BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        Fake.seen.append({"path": self.path, "body": body})
        data = json.dumps({"ok": True, "result": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def ts(y, mo, d, h, mi, tz):
    return int(datetime.datetime(y, mo, d, h, mi, tzinfo=agenda_file.zone(tz)).timestamp())


BA = "America/Argentina/Buenos_Aires"


def entry(aid, typ, schedule, **kw):
    e = {"id": aid, "type": typ, "schedule": schedule, "params": {}, "label": typ, "created": int(time.time()) - 3 * 86400,
         "paused": False, "once": False, "tz": BA, "last_run": None, "last_state": None}
    e.update(kw)
    return e


def test_parser_parity():
    """agenda_file's parser is a copy of gateway.py's: same sets for the same fields."""
    tmp = tempfile.mkdtemp(prefix="agenda-gw-")
    os.environ.update(GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log",
                      GATEWAY_WORKDIR=f"{tmp}/workdir")
    os.makedirs(f"{tmp}/workdir")
    json.dump({}, open(f"{tmp}/gw.json", "w"))
    spec = importlib.util.spec_from_file_location("gw_for_agenda", os.path.join(HERE, "gateway.py"))
    gw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gw)
    fields = ["*", "*/3", "0,30", "1-5", "mon", "jan,jul", "7", "sun-sat", "10-50/20", "5/15", "mon-fri"]
    same = True
    for i in range(5):
        for f in fields:
            try:
                g = gw._cron_field(f, i)
            except ValueError:
                g = "err"
            try:
                a = agenda_file._cron_field(f, i)
            except ValueError:
                a = "err"
            same = same and g == a
    ok(same, "the schedule parser is the same as gateway.py's (_cron_field, every field, names, steps, weekday 7)")
    ok(list(gw.AGENDA_TYPES) == list(agenda_file.TYPES) and gw.AGENDA_TZ == agenda_file.DEFAULT_TZ,
       "the type list and the default zone match gateway.py")
    every = [gw.agenda_schedule(x)[0] for x in ("every 30m", "every 2h", "every 90m")]
    ok([agenda_file.parse(x) for x in every] == [("every", 30), ("every", 120), ("every", 90)],
       "every Nm/Nh as gateway.py normalizes it")
    shutil.rmtree(tmp, ignore_errors=True)


def test_due():
    d = agenda_file.due_at
    created = ts(2026, 11, 20, 8, 0, BA)
    e = entry("a1", "recordatorio", "0 9 * * *", created=created)
    ok(d(e, created + 3600) == ts(2026, 11, 20, 9, 0, BA), "cron: the first match after created, in the entry's zone")
    e["last_run"] = ts(2026, 11, 20, 9, 0, BA) + 30
    ok(d(e, e["last_run"] + 60) == ts(2026, 11, 21, 9, 0, BA), "cron: after a run, the next day's time (never the same due time twice)")
    e["last_run"] = ts(2026, 11, 17, 9, 0, BA) + 30
    now = ts(2026, 11, 20, 12, 0, BA)
    first = d(e, now)
    ok(first == ts(2026, 11, 18, 9, 0, BA) and first <= now, "missed for days: due (at the first missed time)")
    e["last_run"] = now
    ok(d(e, now) > now, "missed for days: runs once, then the next is in the future (no catch-up run by run)")
    midnight = ts(2026, 11, 20, 0, 0, "UTC")
    m, b = (entry("a2", "recordatorio", "0 9 * * *", tz=z, created=midnight) for z in ("Europe/Moscow", BA))
    ok(d(m, 0) == ts(2026, 11, 20, 9, 0, "Europe/Moscow") and d(b, 0) == ts(2026, 11, 20, 9, 0, BA) and d(b, 0) - d(m, 0) == 6 * 3600,
       "the zone of the entry decides the hour")
    fri13 = entry("a3", "recordatorio", "0 9 13 * 5", created=ts(2026, 11, 1, 0, 0, BA))   # 6 Nov is a Friday, 13 Nov too
    ok(d(fri13, 0) == ts(2026, 11, 6, 9, 0, BA), "day of month and weekday both set: either matches (as cron)")
    sun = entry("a4", "recordatorio", "0 9 * * 7", created=ts(2026, 11, 23, 0, 0, BA))      # Mon 23 Nov -> Sun 29 Nov
    ok(d(sun, 0) == ts(2026, 11, 29, 9, 0, BA), "weekday 7 is Sunday")
    ev = entry("a5", "recordatorio", "every 2h")
    ok(d(ev, 1000000) == 1000000, "every: at once when it never ran")
    ev["last_run"] = 2000000
    ok(d(ev, 2000001) == 2000000 + 7200, "every: N after the last run")
    mad = entry("a6", "recordatorio", "30 2 * * *", tz="Europe/Madrid", created=ts(2026, 10, 24, 12, 0, "Europe/Madrid"))
    t1 = d(mad, 0)
    mad["last_run"] = t1 + 10
    t2 = d(mad, 0)
    ok(t2 - t1 > 20 * 3600, "the hour going back (02:30 twice): one run that day, the next one the day after", f"{t1} {t2}")
    ok(d(entry("a7", "recordatorio", "0 9 * * *", paused=True), 0) is None, "a paused entry is never due")
    ok(d(entry("a8", "recordatorio", "bogus"), 0) is None and d(entry("a9", "nope", "0 9 * * *"), 0) is None,
       "a bad schedule or an unknown type is never due")


def wait_for(fn, secs=20):
    end = time.time() + secs
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.1)
    return False


def main():
    test_parser_parity()
    test_due()
    tmp = tempfile.mkdtemp(prefix="agenda-selftest-")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    bot_api = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        run_all(tmp, bot_api)
    finally:
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED")
        return 1
    print("all agenda runner checks passed")
    return 0


def run_all(tmp, bot_api):
    shims, ctl = os.path.join(tmp, "shims"), os.path.join(tmp, "ctl")
    os.makedirs(shims)
    os.makedirs(ctl)
    with open(os.path.join(shims, "docker"), "w") as f:
        f.write(FAKE_DOCKER)
    os.chmod(os.path.join(shims, "docker"), 0o755)
    os.environ.update(PATH=shims + os.pathsep + os.environ.get("PATH", ""), FAKE_CTL=ctl, HOME=os.path.join(tmp, "home"),
                      BUS_CONFIG=os.path.join(tmp, "no-bus.json"), FAKE_TRABAJOS=os.path.join(HERE, "trabajos.py"))
    spaces = os.path.join(tmp, "spaces")
    wd, persist = {}, {}
    for s in ("ana", "bob"):
        wd[s], persist[s] = os.path.join(spaces, s, "workdir"), os.path.join(spaces, s, "persist")
        os.makedirs(os.path.join(wd[s], "descargas"))
        os.makedirs(os.path.join(persist[s], "cron"))
        with open(os.path.join(persist[s], ".env"), "w") as f:
            f.write(f"TELEGRAM_BOT_TOKEN={TG_TOKEN}\nTELEGRAM_ALLOWED_USERS=111,222\nNVIDIA_API_KEY=never-read-here\n")
    json.dump({"lang": "es"}, open(os.path.join(wd["ana"], ".prefs.json"), "w"))
    cfg_raw = {"image": "img:t", "apply": "docker", "state_dir": os.path.join(tmp, "state"),
               "types": {"subs": {"schedule": "*-*-* 00/3:00:00"}},
               "people": {"ana": {"local_workdir": wd["ana"], "bot_api": bot_api, "jobs": {"subs": {}}},
                          "bob": {"local_workdir": wd["bob"]}}}
    cfgfile = os.path.join(tmp, "workers.json")
    json.dump(cfg_raw, open(cfgfile, "w"))
    os.environ["WORKERS_CONFIG"] = cfgfile
    cfg = worker.load_config(cfgfile)
    ok(worker.validate(cfg_raw) == [], "config: a person with only local_workdir (reminders) and a person-level bot_api are valid",
       worker.validate(cfg_raw))
    bad = json.loads(json.dumps(cfg_raw))
    bad["people"]["ana"]["bot_api"] = "http://x:1/bot123/"
    bad["people"]["cid"] = {"remote_workdir": "aibridge/stacks/cid/workdir", "bot_api": "http://x:1", "jobs": {"subs": {}}}
    errs = worker.validate(bad)
    ok(any("people.ana.bot_api" in x for x in errs) and any("people.cid" in x and "local data" in x for x in errs),
       "config: a bot_api with a path, and bot_api without local_workdir, are refused", errs)

    def write_agenda(s, entries):
        p = os.path.join(wd[s], ".agenda.json")
        with open(p, "w") as f:
            json.dump({"v": 1, "next": 50, "entries": entries}, f)
        os.chmod(p, 0o600)

    def agenda(s):
        return {e["id"]: e for e in json.load(open(os.path.join(wd[s], ".agenda.json")))["entries"]}

    def events():
        try:
            return [json.loads(x) for x in open(os.path.join(cfg["state_dir"], "events.jsonl"))]
        except OSError:
            return []

    def docker_calls():
        try:
            return [json.loads(x) for x in open(os.path.join(ctl, "docker.log"))]
        except OSError:
            return []

    def jobs_json(s, enabled):
        json.dump({"jobs": [{"name": "subs-nuevos", "prompt": "", "schedule": {"kind": "cron", "expr": "0 */3 * * *"},
                             "enabled": enabled, "state": "scheduled" if enabled else "paused"}]},
                  open(os.path.join(persist[s], "cron", "jobs.json"), "w"))

    def ledger(s):
        try:
            return json.load(open(os.path.join(wd[s], ".trabajos", "ledger.json")))["entries"]
        except (OSError, ValueError):
            return []

    def reset_logs():
        for p in (os.path.join(ctl, "docker.log"), os.path.join(cfg["state_dir"], "events.jsonl")):
            if os.path.exists(p):
                os.remove(p)
        Fake.seen.clear()

    # --- 1. a reminder: the header, the bot, the ledger, once -> paused ------------------------------------------------------------
    created = int(time.time()) - 2 * 86400
    write_agenda("ana", [entry("a1", "recordatorio", "0 9 * * *", params={"text": TEXT_MARK + " tomar agua"}, label=LABEL_MARK,
                               created=created, once=True)])
    reset_logs()
    rc = worker.cmd_agenda_tick(cfg, spawn=False)
    sends = [x for x in Fake.seen if "/sendMessage" in x["path"]]
    want_head = f"🕖 Programado · {LABEL_MARK} 09:00\n\n"
    ok(rc == 0 and len(sends) == 2 and {x["body"]["chat_id"] for x in sends} == {"111", "222"},
       "reminder: sent once to each allowed user through the stack's bot", (rc, len(sends)))
    ok(all(x["body"]["text"] == (want_head + TEXT_MARK + " tomar agua").strip() for x in sends) and all(TG_TOKEN in x["path"] for x in sends),
       "reminder: the first line is '🕖 Programado · <label> 09:00', then the text", sends[:1])
    a1 = agenda("ana")["a1"]
    ok(a1["last_state"] == "listo" and a1["paused"] is True and a1["last_run"] and a1["last_run"] >= created,
       "reminder: last_run set, last_state listo, a `once` entry is paused after its run", a1)
    reg = [c for c in docker_calls() if "/usr/local/bin/trabajos" in c]
    want = ["registrar", "--origen", "programado", "--agenda", "a1", "--etiqueta", LABEL_MARK, "--estado", "listo",
            "--inicio", str(a1["last_run"])]
    ok(len(reg) == 1 and reg[0][reg[0].index("/usr/local/bin/trabajos") + 1:][:len(want)] == want
       and reg[0][-2:] == ["--tipo", "other"] and "--motivo" not in reg[0],
       "ledger: trabajos registrar --origen programado --agenda --etiqueta --estado --inicio --fin --tipo other", reg)
    r0 = reg[0] if reg else []
    ok(r0[r0.index("--network") + 1] == "none" and "-e" not in r0 and f"{wd['ana']}:/workdir" in r0 if r0 else False,
       "ledger: a one-shot with no network, no env, the person's workdir at /workdir")
    led = [x for x in ledger("ana") if x.get("agenda_id") == "a1"]
    ok(len(led) == 1 and led[0]["origin"] == "programado" and led[0]["state"] == "listo",
       "ledger: the run is in the person's ledger as origin programado", led)
    evs = events()
    subj = [x["subject"] for x in evs]
    ok(subj == ["ev.worker.agenda.due", "ev.worker.agenda.started", "ev.worker.agenda.done"], "events: due, started, done", subj)
    raw = open(os.path.join(cfg["state_dir"], "events.jsonl")).read()
    ok(TEXT_MARK not in raw and TG_TOKEN not in raw and LABEL_MARK not in raw and evs[-1]["data"].get("sent") == 2,
       "events: counts only (no text, no label, no token)")
    reset_logs()
    worker.cmd_agenda_tick(cfg, spawn=False)
    ok(not Fake.seen and not events(), "a paused `once` entry does not run again")

    # --- 2. never twice for one due time: two ticks, and the start write itself ----------------------------------------------------
    write_agenda("ana", [entry("a2", "recordatorio", "every 30m", params={"text": "x"}, label="t")])
    reset_logs()
    worker.cmd_agenda_tick(cfg, spawn=False)
    worker.cmd_agenda_tick(cfg, spawn=False)
    ok(len([x for x in Fake.seen if "/sendMessage" in x["path"]]) == 2, "two ticks in a row: one run (2 users), not two")
    write_agenda("ana", [entry("a3", "recordatorio", "every 30m", params={"text": "x"})])
    now = int(time.time())
    first, second = agenda_file.start(wd["ana"], "a3", now), agenda_file.start(wd["ana"], "a3", now)
    ok(first and first["entry"]["last_state"] == "corriendo" and second is None,
       "start: the first takes the due time (corriendo), a second start of the same due time gets nothing")
    ok(agenda_file.end(wd["ana"], "a3", now - 5, "listo") is False and agenda("ana")["a3"]["last_state"] == "corriendo",
       "end: only the run that started at that time sets the state")

    # --- 3. the POSIX lock: another process holds .agenda.lock --------------------------------------------------------------------
    write_agenda("ana", [entry("a4", "recordatorio", "every 30m", params={"text": "x"})])
    holder = subprocess.Popen([sys.executable, "-c", "import fcntl, os, sys, time\n"
                               "fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)\nfcntl.lockf(fd, fcntl.LOCK_EX)\n"
                               "print('held', flush=True)\ntime.sleep(1.5)", os.path.join(wd["ana"], ".agenda.lock")],
                              stdout=subprocess.PIPE, text=True)
    holder.stdout.readline()
    t0 = time.time()
    got = agenda_file.start(wd["ana"], "a4", int(time.time()))
    waited = time.time() - t0
    holder.wait()
    ok(got is not None and waited >= 1.0, f"start waits for a POSIX lock held by another process (waited {waited:.1f}s)")
    src = open(os.path.join(HERE, "workers", "agenda_file.py")).read()
    ok("fcntl.lockf(fd, fcntl.LOCK_EX)" in src and "flock" not in src.replace("BSD `flock`", ""),
       "agenda_file locks with lockf (POSIX), never flock")

    # --- 4. the language of the header ---------------------------------------------------------------------------------------------
    json.dump({"lang": "ru"}, open(os.path.join(wd["ana"], ".prefs.json"), "w"))
    write_agenda("ana", [entry("a5", "recordatorio", "0 9 * * *", params={"text": "вода"}, label="вода", created=created)])
    reset_logs()
    worker.cmd_agenda_tick(cfg, spawn=False)
    texts = [x["body"]["text"] for x in Fake.seen if "/sendMessage" in x["path"]]
    ok(texts and texts[0].startswith("🕖 По расписанию · вода 09:00\n\nвода"), "the header in the person's language (.prefs.json lang ru)", texts[:1])
    json.dump({"lang": "es"}, open(os.path.join(wd["ana"], ".prefs.json"), "w"))

    # --- 5. fallo no_bot: a person without bot_api ---------------------------------------------------------------------------------
    write_agenda("bob", [entry("a1", "recordatorio", "every 30m", params={"text": "x"}, label="b")])
    reset_logs()
    worker.cmd_agenda_tick(cfg, only="bob", spawn=False)
    b1 = agenda("bob")["a1"]
    last = events()[-1]
    reg = [c for c in docker_calls() if "/usr/local/bin/trabajos" in c]
    ok(not Fake.seen and b1["last_state"] == "fallo" and last["subject"] == "ev.worker.agenda.failed" and last["data"].get("reason") == "no_bot",
       "reminder without bot_api: nothing sent, fallo, event failed reason=no_bot", (b1, last))
    ok(reg and reg[0][-4:] == ["--tipo", "other", "--motivo", "no_bot"] and "fallo" in reg[0],
       "a failed run is recorded too, with its short reason (--estado fallo --motivo no_bot)", reg)

    # --- 6. omitido: the type is not configured for the person; a bad entry is said once -------------------------------------------
    write_agenda("bob", [entry("a2", "subs", "every 3h"), entry("a3", "recordatorio", "bogus", params={"text": "x"})])
    reset_logs()
    worker.cmd_agenda_tick(cfg, only="bob", spawn=False)
    ag = agenda("bob")
    evs = events()
    ok(ag["a2"]["last_state"] == "omitido" and any(e["subject"] == "ev.worker.agenda.skipped" and e["data"].get("reason") == "not_configured" for e in evs),
       "subs for a person without jobs.subs: omitido, reason not_configured")
    ok(not [c for c in docker_calls() if "/usr/local/bin/trabajos" in c], "an omitido run is not recorded in the ledger (it did not run)")
    ok(ag["a3"]["last_state"] == "omitido" and ag["a3"]["last_run"] is None
       and any(e["data"].get("reason") == "bad_entry" for e in evs), "a schedule the runner cannot read: omitido once, reason bad_entry")
    reset_logs()
    worker.cmd_agenda_tick(cfg, only="bob", spawn=False)
    ok(not [e for e in events() if e["data"].get("reason") == "bad_entry"], "the bad entry is not reported again every tick (no loop)")

    # --- 7. subs from the agenda: job_active, then it runs, notice with the header, ledger --tipo subs -------------------------------
    jobs_json("ana", True)
    write_agenda("ana", [entry("a6", "subs", "every 3h", label="subs")])
    reset_logs()
    worker.cmd_agenda_tick(cfg, spawn=False)
    ok(agenda("ana")["a6"]["last_state"] == "omitido" and events()[-1]["data"].get("reason") == "job_active"
       and not [c for c in docker_calls() if "--entrypoint" in c and c[c.index("--entrypoint") + 1] == "/bin/sh"],
       "subs while the stack's own subs-nuevos cron is on: omitido job_active, nothing run")
    rd = [c for c in docker_calls() if "nokeys" in c]
    ok(rd and rd[0][rd[0].index("--network") + 1] == "none" and f"{persist['ana']}:/p:ro" in rd[0],
       "the stack's cron is read without keys, read-only, no network")
    jobs_json("ana", False)
    write_agenda("ana", [entry("a7", "subs", "every 3h", label="subs")])
    with open(os.path.join(ctl, "subs_out"), "w") as f:
        f.write("subs: rate limited, paused 2 h\n")
    reset_logs()
    worker.cmd_agenda_tick(cfg, spawn=False)
    a7 = agenda("ana")["a7"]
    ok(a7["last_state"] == "listo", "subs with the stack's cron paused: it runs through the subs type, listo", a7)
    notes = [os.path.join(wd["ana"], ".worker-notices", n) for n in os.listdir(os.path.join(wd["ana"], ".worker-notices"))] \
        if os.path.isdir(os.path.join(wd["ana"], ".worker-notices")) else []
    hm = datetime.datetime.fromtimestamp(a7["last_run"], agenda_file.zone(BA)).strftime("%H:%M")
    ok(len(notes) == 1 and open(notes[0]).read().startswith(f"🕖 Programado · subs {hm}\n\nsubs: rate limited"),
       "the notice a scheduled subs run leaves starts with the 🕖 Programado header", [open(n).read()[:60] for n in notes])
    reg = [c for c in docker_calls() if "/usr/local/bin/trabajos" in c]
    ok(reg and reg[0][-2:] == ["--tipo", "subs"] and "listo" in reg[0], "ledger: a subs run is --tipo subs")
    os.remove(os.path.join(ctl, "subs_out"))

    # --- 8. busy: another subs run holds the type's lock ---------------------------------------------------------------------------
    write_agenda("ana", [entry("a8", "subs", "every 3h", label="subs")])
    lk = worker.SubsJob(cfg, "ana").lock()
    reset_logs()
    worker.cmd_agenda_tick(cfg, spawn=False)
    lk.close()
    ok(agenda("ana")["a8"]["last_state"] == "omitido" and events()[-1]["data"].get("reason") == "busy",
       "another run of the type holds its lock: omitido, reason busy")

    # --- 9. the fixed timer goes quiet while the agenda holds the type --------------------------------------------------------------
    write_agenda("ana", [entry("a9", "subs", "every 3h", last_run=int(time.time()), last_state="listo")])
    reset_logs()
    worker.cmd_run(cfg, "subs", None)
    evs = events()
    ok([e["subject"] for e in evs] == ["ev.worker.subs.skipped"] and evs[0]["data"].get("reason") == "agenda"
       and not [c for c in docker_calls() if "/bin/sh" in c], "fixed timer: skipped reason=agenda, no container, when the agenda holds subs")
    write_agenda("ana", [entry("a9", "subs", "every 3h", paused=True)])
    reset_logs()
    worker.cmd_run(cfg, "subs", None)
    ok(any(e["subject"] == "ev.worker.subs.done" for e in events()), "fixed timer: runs again once the agenda's entry is paused")

    # --- 10. a long type runs detached (agenda-run in its own process) ---------------------------------------------------------------
    write_agenda("ana", [entry("b1", "subs", "every 3h", label="subs")])
    reset_logs()
    worker.cmd_agenda_tick(cfg, spawn=True)
    ok(wait_for(lambda: agenda("ana")["b1"]["last_state"] == "listo"), "the detached run ends listo and writes its state",
       agenda("ana")["b1"])
    ok(wait_for(lambda: any(e["subject"] == "ev.worker.agenda.done" for e in events())), "the detached run emits done")

    # --- 11. the agenda through a container when the file is not this user's -------------------------------------------------------
    write_agenda("ana", [entry("b2", "recordatorio", "every 30m", params={"text": "x"}, label="t")])
    saved = worker.agenda_in_process
    worker.agenda_in_process = lambda cfg_, lwd, write: False
    try:
        reset_logs()
        worker.cmd_agenda_tick(cfg, spawn=False)
    finally:
        worker.agenda_in_process = saved
    ops = [c[c.index("-") + 1] for c in docker_calls() if "-" in c and f"{wd['ana']}:/workdir" in c and c[c.index("-") + 1] in ("read", "start", "end")]
    ok(ops == ["read", "start", "end"] and agenda("ana")["b2"]["last_state"] == "listo",
       "container mode: read, start and end run as root in a one-shot (agenda_file.py on stdin)", ops)
    one = [c for c in docker_calls() if "start" in c][0]
    ok(one[one.index("--network") + 1] == "none" and "-i" in one, "container mode: no network, the script on stdin")
    ok(oct(os.stat(os.path.join(wd["ana"], ".agenda.json")).st_mode & 0o777) == "0o600", "the agenda stays 0600 after the runner's writes")

    # --- 12. the timer -------------------------------------------------------------------------------------------------------------
    r = subprocess.run([sys.executable, os.path.join(HERE, "workers", "worker.py"), "schedule", "agenda"], capture_output=True, text=True)
    ok(r.stdout.strip() == "*:0/5", "worker.py schedule agenda: every 5 minutes by default", r.stdout + r.stderr)
    inst = open(os.path.join(HERE, "workers", "install.sh")).read()
    ok("sync agenda; do" in inst and "KillMode=process" in inst and "agenda_file.py" in inst,
       "install.sh writes the agenda timer (KillMode=process) and installs agenda_file.py")


if __name__ == "__main__":
    sys.exit(main())
