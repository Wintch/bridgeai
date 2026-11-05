#!/usr/bin/env python3
"""Offline checks for jobpush.py with a fake scan, a fake triage and temp prefs (no node, no network, no tokens).
Run: python3 -I jobpush_selftest.py"""
import fcntl, importlib.util, json, os, subprocess, sys, tempfile, textwrap, time

HERE = os.path.dirname(os.path.abspath(__file__))
import atexit, shutil
tmp = tempfile.mkdtemp(prefix="jp-")
atexit.register(shutil.rmtree, tmp, True)
MARKER = "jp-fake-scan-marker-" + os.path.basename(tmp)   # unique per run: two selftests at once never see each other's sleeper   # no "jobpush" in any path: scan_running ignores command lines that have it
fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")

PIPE0 = "# Pipeline - Pending URLs\n\n## Pending\n\n## Processed\n"
# The fake scan: appends FAKE_SCAN_NEW (lines separated by \\n) to data/pipeline.md like scan.mjs does, prints a summary.
open(f"{tmp}/fakescan.py", "w").write(textwrap.dedent('''
    import os, sys, time
    n = os.environ.get("FAKE_SCAN_NEW", "")
    lines = [l for l in n.split("\\n") if l]
    if os.environ.get("FAKE_SCAN_SLEEP"):
        time.sleep(float(os.environ["FAKE_SCAN_SLEEP"]))
    open("data/ran", "a").write("x")
    open("data/sawrunning", "w").write("1" if os.path.exists("data/.jobpush-running") else "0")
    open("data/sawprescan", "w").write("1" if os.path.exists("data/.jobpush-prescan.json") else "0")
    if lines:
        t = open("data/pipeline.md").read()
        i = t.index("\\n## Processed")
        open("data/pipeline.md", "w").write(t[:i] + "\\n" + "\\n".join(lines) + "\\n" + t[i:])
    if os.environ.get("FAKE_SCAN_NOSUMMARY") != "1":
        print("Companies scanned:     9")
        print("Total jobs found:      15130")
        print("New offers added:      " + os.environ.get("FAKE_SCAN_SUMMARY", str(len(lines))))
    sys.exit(int(os.environ.get("FAKE_SCAN_RC", "0")))
'''))
# The fake triage: JSON like buscar-empleos --revisar --json; the verdict of a url comes from FAKE_VERDICTS (json), default ok.
open(f"{tmp}/fakerev.py", "w").write(textwrap.dedent('''
    import json, os, sys
    if os.environ.get("FAKE_REVISAR_FAIL") == "1":
        sys.exit(3)
    if os.environ.get("FAKE_REVISAR_KILLPARENT") == "1":
        import signal
        os.kill(os.getppid(), signal.SIGKILL)
        import time; time.sleep(5)
        sys.exit(0)
    if os.environ.get("FAKE_REVISAR_RAW") is not None:
        print(os.environ["FAKE_REVISAR_RAW"])
        sys.exit(0)
    v = json.loads(os.environ.get("FAKE_VERDICTS", "{}"))
    urls = [a for a in sys.argv[1:] if a.startswith("http")]
    open(os.environ["FAKE_REVISAR_LOG"], "a").write(str(len(urls)) + "\\n")
    print(json.dumps([{"url": u, "title": "t", "verdict": v.get(u, "ok"), "why": "fake"} for u in urls]))
'''))
# The fake chain (scheduled-chain.mjs): records its arguments, appends FAKE_SCAN_NEW to data/pipeline.md, prints FAKE_CHAIN_OUT
# (the whole stdout, set by the test) and exits with FAKE_CHAIN_RC.
open(f"{tmp}/fakechain.py", "w").write(textwrap.dedent('''
    import os, sys, time
    open("data/chainargs", "a").write(" ".join(sys.argv[1:]) + "\\n")
    open("data/sawrunning", "w").write("1" if os.path.exists("data/.jobpush-running") else "0")
    if os.environ.get("FAKE_SCAN_SLEEP"):
        time.sleep(float(os.environ["FAKE_SCAN_SLEEP"]))
    lines = [l for l in os.environ.get("FAKE_SCAN_NEW", "").split("\\n") if l]
    if lines:
        t = open("data/pipeline.md").read()
        i = t.index("\\n## Processed")
        open("data/pipeline.md", "w").write(t[:i] + "\\n" + "\\n".join(lines) + "\\n" + t[i:])
    print(os.environ.get("FAKE_CHAIN_OUT", ""))
    sys.exit(int(os.environ.get("FAKE_CHAIN_RC", "0")))
'''))
SECRET = "Zeta Secret Corp"   # stands for a label of the person's own application history: it may reach the chat, never the log


def chain_json(status="ok", new=0, steps=None, closing=(), expired=(), **kw):
    d = {"status": status, "startedAt": "2030-01-01T00:00:00.000Z", "finishedAt": "2030-01-01T00:19:00.000Z",
         "newAdded": {"scan": new, "navent": None}, "newAddedTotal": new, "pendingBefore": 0, "pendingInbox": new,
         "expired": list(expired), "closingSoon": list(closing), "overdue": [],
         "steps": steps or [{"name": "scan", "ok": True, "exitCode": 0, "signal": None, "timedOut": False, "seconds": 578.3},
                            {"name": "liveness", "ok": True, "exitCode": 1, "signal": None, "timedOut": False, "seconds": 301.2},
                            {"name": "closing", "ok": True, "exitCode": 0, "signal": None, "timedOut": False, "seconds": 0.4}]}
    d.update(kw)
    return json.dumps(d)


def closing_row(num, days, company=SECRET, role="Secret Role"):
    return {"num": num, "company": company, "role": role, "status": "Evaluated", "source": "notes", "closes": "2030-01-07", "daysLeft": days, "marker": "closes"}


def expired_row(i):
    return {"label": f"#{i} {SECRET} {i} · Secret Role (Applied)", "url": f"https://example.com/applied/{i}", "reason": "ATS API 404"}


def offer(i, role=None, company=None):
    return f"- [ ] https://example.com/jobs/{i} | {company or 'Acme ' + str(i)} | {role or 'Role ' + str(i)} | Remote"


class Case:
    def __init__(self, avisos=None, lang=None, gw_lang=None, chain=False, portals=None):
        self.root = tempfile.mkdtemp(dir=tmp, prefix="jf-")
        os.makedirs(f"{self.root}/data")
        open(f"{self.root}/scan.mjs", "w").write("")
        if chain:
            open(f"{self.root}/scheduled-chain.mjs", "w").write("")
        if portals is not None:
            open(f"{self.root}/portals.yml", "w").write(portals)
        open(f"{self.root}/data/pipeline.md", "w").write(PIPE0)
        self.prefs = f"{self.root}/prefs.json"
        p = {k: v for k, v in (("avisos", avisos), ("lang", lang)) if v}
        json.dump(p, open(self.prefs, "w"))
        self.gw = f"{self.root}/gw.json"
        json.dump({"lang": gw_lang} if gw_lang else {}, open(self.gw, "w"))
        self.revlog = f"{self.root}/revisar.log"

    def run(self, new=(), rc=0, verdicts=None, now=1_800_000_000, args=(), **env):
        e = dict(os.environ, JOBPUSH_ROOT=self.root, JOBPUSH_PREFS=self.prefs, GATEWAYS_CONFIG=self.gw, JOBPUSH_NOW=str(now),
                 JOBPUSH_SCAN_CMD=f"{sys.executable} {tmp}/fakescan.py", JOBPUSH_CHAIN_CMD=f"{sys.executable} {tmp}/fakechain.py",
                 JOBPUSH_REVISAR_CMD=f"{sys.executable} {tmp}/fakerev.py",
                 JOBPUSH_SCAN_PATTERN=MARKER, FAKE_SCAN_NEW="\n".join(new), FAKE_SCAN_RC=str(rc),
                 FAKE_VERDICTS=json.dumps(verdicts or {}), FAKE_REVISAR_LOG=self.revlog)
        e.update({k: str(v) for k, v in env.items()})
        r = subprocess.run([sys.executable, "-I", f"{HERE}/jobpush.py", *args], env=e, capture_output=True, text=True, timeout=60)
        self.stderr = r.stderr
        return r.stdout

    def data(self, name):
        try:
            return open(f"{self.root}/data/{name}", encoding="utf-8").read()
        except OSError:
            return None

    def ran(self):
        return len(self.data("ran") or "")

    def state(self):
        return json.loads(self.data(".jobpush-state.json") or "{}")


U = lambda i: f"https://example.com/jobs/{i}"

# off: missing key, "no" -> nothing printed, no scan at all
for av in (None, "no"):
    c = Case(avisos=av)
    check(f"off ({av}): silent", c.run(new=[offer(1)]), "")
    check(f"off ({av}): the scan did not run", c.ran(), 0)

c = Case(avisos="nuevo")
os.unlink(f"{c.root}/scan.mjs")
check("no scan.mjs: silent and nothing created", (c.run(new=[offer(1)]), c.ran()), ("", 0))

# nuevo, 2 new, one kept
c = Case(avisos="nuevo")
out = c.run(new=[offer(1, "Environment Artist", "Studio One"), offer(2, "3D Render Artist", "Studio Two")], verdicts={U(2): "excluida"})
check("nuevo: first line", out.splitlines()[0], "Encontré 1 oferta nueva que encaja:")
check("nuevo: the kept offer as role — company — full url", f"Environment Artist — Studio One — {U(1)}" in out, True)
check("nuevo: the dropped one is not named", "Studio Two" in out or U(2) in out, False)
check("nuevo: the offer to evaluate and how to change", ("evaluá" in out, "/avisos diario | nuevo | no" in out), (True, True))
check("nuevo: plain text, no markdown table or bold", any(ch in out for ch in ("|||", "**", "---")), False)
pl = c.data("push-last.md")
check("push-last.md: both urls, one offered", (U(1) in pl, U(2) in pl, pl.count("offered: yes"), "excluida" in pl), (True, True, 1, True))
log = c.data("jobpush.log")
check("jobpush.log: one metadata line, counts only", (len(log.splitlines()), "new=2 kept=1" in log, "Studio" in log or "example.com" in log), (1, True, False))
check("state: last message time", c.state().get("last_message"), 1_800_000_000)
check("triage got the urls once", open(c.revlog).read().split(), ["2"])

# the diff, not the summary's number, decides what is new
c = Case(avisos="nuevo")
out = c.run(new=[offer(1)], FAKE_SCAN_SUMMARY=5)
check("diff beats the summary number", ("Encontré 1 oferta" in out, "new=1 " in c.data("jobpush.log")), (True, True))
# checked and struck lines are not new offers
c = Case(avisos="nuevo")
out = c.run(new=["- [x] https://example.com/jobs/9 | Old | Done", "- [ ] ~~https://example.com/jobs/8 | Gone | Role~~"])
check("checked / struck lines are not offers", out, "")

# nuevo with nothing: silent; diario with nothing: one line with the count
c = Case(avisos="nuevo")
check("nuevo, 0 new: silent", c.run(), "")
check("nuevo, 0 new: the scan did run", c.ran(), 1)
c = Case(avisos="diario")
out = c.run()
check("diario, 0 new: one line with the number checked", out, "Revisé 15.130 avisos: nada nuevo que encaje.\n")
c = Case(avisos="diario")
out = c.run(new=[offer(1)], verdicts={U(1): "muerta"})
check("diario, new but none passes: one line", out, "Revisé 15.130 avisos: 1 nuevos, pero ninguno pasó tus filtros.\n")
c = Case(avisos="nuevo")
check("nuevo, new but none passes: silent", c.run(new=[offer(1)], verdicts={U(1): "muerta"}), "")

# languages
c = Case(avisos="nuevo", lang="ru")
out = c.run(new=[offer(1), offer(2), offer(3)])
check("ru: header", out.splitlines()[0], "Нашёл 3 новые вакансии, которые подходят:")
check("ru: asks to evaluate and how to change", ("«оцени»" in out, "/avisos ежедневно | новые | нет" in out), (True, True))
c = Case(avisos="diario", lang="ru")
check("ru: diario, nothing", c.run(), "Проверил 15 130 объявлений: ничего нового, что подходит.\n")
c = Case(avisos="nuevo", lang="en")
out = c.run(new=[offer(1), offer(2)])
check("en: header and ask", (out.splitlines()[0], 'Reply "evaluate"' in out), ("Found 2 new jobs that fit:", True))
c = Case(avisos="nuevo", lang="auto", gw_lang="ru")
check("lang auto: the stack's lang from gateways.json", c.run(new=[offer(1)]).startswith("Нашёл 1 новую вакансию"), True)
c = Case(avisos="nuevo", lang="en", gw_lang="ru")
check("the person's /idioma beats the stack's lang", c.run(new=[offer(1)]).startswith("Found 1 new job"), True)
spec = importlib.util.spec_from_file_location("jp", f"{HERE}/jobpush.py")
jp = importlib.util.module_from_spec(spec); spec.loader.exec_module(jp)
check("ru plurals", [jp.found_header("ru", n, True).split()[1:3] for n in (1, 2, 5, 11, 21, 22, 25)],
      [["1", "новую"], ["2", "новые"], ["5", "новых"], ["11", "новых"], ["21", "новую"], ["22", "новые"], ["25", "новых"]])
check("every language has the same texts", {k: sorted(set(v) - {"found_1", "found_n"}) for k, v in jp.TEXT.items()},
      {k: sorted(set(jp.TEXT["es"]) - {"found_1", "found_n"}) for k in jp.TEXT})

# more than five: five named, "+N more", all of them in push-last.md
c = Case(avisos="nuevo")
out = c.run(new=[offer(i) for i in range(1, 8)])
check("7 offers: five lines and +2", (sum(1 for l in out.splitlines() if "example.com" in l), "+2 más" in out), (5, True))
check("7 offers: push-last.md has all", c.data("push-last.md").count("offered: yes"), 7)

# the triage cannot run: the offers go out unverified, and the message says so
c = Case(avisos="nuevo")
out = c.run(new=[offer(1)], FAKE_REVISAR_FAIL=1)
check("triage failure: unverified, said so", ("sin verificar" in out, U(1) in out), (True, True))

# scan failure: silent once, one message the second time, silent again, and again after a success
c = Case(avisos="nuevo")
r1 = c.run(rc=1, now=1_800_000_000)
r2 = c.run(rc=1, now=1_800_086_400)
r3 = c.run(rc=1, now=1_800_172_800)
check("failure 1 silent", r1, "")
check("failure 2: one message", r2, "No pude hacer la revisión diaria de ofertas (falló dos veces seguidas). Quedó anotado en el registro del sistema.\n")
check("failure 3 silent", r3, "")
check("failure counters", (c.state()["failures"], c.state()["failure_notified"]), (3, True))
check("failure goes to stderr for the operator", "scan failed" in c.stderr, True)
c.run(now=1_800_259_200)
check("success resets the failure state", (c.state()["failures"], c.state()["failure_notified"]), (0, False))
c.run(rc=1, now=1_800_345_600)
check("a new streak is silent at first and speaks at the second", (c.run(rc=1, now=1_800_432_000) != ""), True)
c = Case(avisos="nuevo")
check("exit 0 but no summary counts as a failure", (c.run(FAKE_SCAN_NOSUMMARY=1), c.state()["failures"]), ("", 1))
# a timeout is a failure and the scan is killed
c = Case(avisos="nuevo")
t0 = time.time()
check("timeout: failure, silent the first time", (c.run(JOBPUSH_SCAN_TIMEOUT=1, FAKE_SCAN_SLEEP=30), c.state()["failures"]), ("", 1))
check("timeout: the scan was killed, not waited for", time.time() - t0 < 20, True)
check("timeout: the log says so", "exit=timeout" in c.data("jobpush.log"), True)
# offers a failed scan wrote before dying are not lost
c = Case(avisos="nuevo")
c.run(rc=1, new=[offer(1)])
out = c.run()
check("offers from a failed scan are offered by the next run", (U(1) in out, c.data(".jobpush-carry.json")), (True, "[]"))

# heartbeat after 7 days without any message (nuevo only)
c = Case(avisos="nuevo")
json.dump({"first_run": 1_800_000_000 - 9 * 86400, "last_message": 1_800_000_000 - 8 * 86400}, open(f"{c.root}/data/.jobpush-state.json", "w"))
out = c.run()
check("heartbeat after 8 silent days", out.startswith("Sigo revisando ofertas todos los días"), True)
check("no second heartbeat the next day", c.run(now=1_800_086_400), "")
c = Case(avisos="nuevo")
json.dump({"last_message": 1_800_000_000 - 3 * 86400}, open(f"{c.root}/data/.jobpush-state.json", "w"))
check("no heartbeat after 3 days", c.run(), "")
c = Case(avisos="nuevo")
check("first run: silent (the clock starts)", c.run(), "")
check("a week after the first run: heartbeat", c.run(now=1_800_000_000 + 7 * 86400).startswith("Sigo revisando"), True)
c = Case(avisos="nuevo", lang="ru")
c.run()
check("heartbeat in Russian", c.run(now=1_800_000_000 + 8 * 86400).startswith("Я на связи"), True)

# another scan running: silent, the scan is not started, a log line says why
c = Case(avisos="nuevo")
sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", MARKER])
time.sleep(0.3)
try:
    check("another scan running: silent", c.run(new=[offer(1)]), "")
    check("another scan running: not started, logged", (c.ran(), "skip-scan-running" in c.data("jobpush.log")), (0, True))
    check("scan_running() sees a process by its command line", jp.scan_running(MARKER), True)
finally:
    sleeper.kill()
sleeper.wait()
check("scan_running() is false when nothing matches", jp.scan_running("jp-no-such-process-marker"), False)

# two jobpush runs never overlap
c = Case(avisos="nuevo")
lk = open(f"{c.root}/data/.jobpush.lock", "w")
fcntl.flock(lk, fcntl.LOCK_EX)
check("lock held: silent, nothing run", (c.run(new=[offer(1)]), c.ran(), "skip-locked" in c.data("jobpush.log")), ("", 0, True))
fcntl.flock(lk, fcntl.LOCK_UN)
check("lock free: runs", c.run(new=[offer(1)]).startswith("Encontré"), True)

# more offers than the cap: the rest waits for the next run
c = Case(avisos="nuevo")
c.run(new=[offer(i) for i in range(1, 6)], JOBPUSH_MAX_TRIAGE=3)
check("cap: three triaged, two carried", (open(c.revlog).read().split(), len(json.loads(c.data(".jobpush-carry.json")))), (["3"], 2))
out = c.run(JOBPUSH_MAX_TRIAGE=3)
check("cap: the carried ones are offered the next day", (out.splitlines()[0], U(4) in out, U(5) in out), ("Encontré 2 ofertas nuevas que encajan:", True, True))

# --dry-run: prints the message, changes nothing, and what it found is still offered by the real run
c = Case(avisos="nuevo")
out = c.run(new=[offer(1)], args=["--dry-run"])
check("dry-run prints the message", out.startswith("Encontré 1 oferta"), True)
check("dry-run: no state, no push-last, no log", (c.data(".jobpush-state.json"), c.data("push-last.md"), c.data("jobpush.log")), (None, None, None))
check("the real run after a dry run still offers it", c.run().startswith("Encontré 1 oferta"), True)
c = Case(avisos="no")
out = c.run(args=["--dry-run", "--mode", "diario"])
check("dry-run --mode previews another mode", out, "Revisé 15.130 avisos: nada nuevo que encaje.\n")
check("--mode is ignored without --dry-run", Case(avisos="no").run(args=["--mode", "diario"]), "")

# a portal that would not open a posting ("sin-verificar") is offered, marked unverified; only real rejections drop it
c = Case(avisos="nuevo")
out = c.run(new=[offer(1), offer(2), offer(3)], verdicts={U(1): "sin-verificar", U(2): "sospechosa", U(3): "sin-requisito"})
check("sin-verificar is offered as unverified", (U(1) in out, "[sin verificar]" in out, U(2) in out, U(3) in out), (True, True, False, False))
check("sin-verificar: push-last says offered", c.data("push-last.md").count("offered: yes"), 1)
c = Case(avisos="diario")
out = c.run(new=[offer(1), offer(2)], verdicts={U(1): "sin-verificar", U(2): "sin-verificar"})
check("diario: unverified offers are not 'none passed your filters'", ("ninguno pasó" in out, "Ofertas nuevas: 2" in out), (False, True))

# the busy marker exists during the scan and is gone after; the prescan file likewise
c = Case(avisos="nuevo")
c.run(new=[offer(1)])
check("busy marker held during the scan, prescan written before it", (c.data("sawrunning"), c.data("sawprescan")), ("1", "1"))
check("busy marker and prescan removed after the run", (c.data(".jobpush-running"), c.data(".jobpush-prescan.json")), (None, None))
c = Case(avisos="nuevo")
c.run(rc=1)
check("busy marker and prescan removed after a failed scan too", (c.data(".jobpush-running"), c.data(".jobpush-prescan.json")), (None, None))

# a run killed during the triage (the stack stopped): the offers are in pipeline.md, but the next run still offers them
c = Case(avisos="nuevo")
c.run(new=[offer(1), offer(2)], FAKE_REVISAR_KILLPARENT=1)
check("killed during triage: prescan kept, carry untouched", (c.data(".jobpush-prescan.json") is not None, c.data(".jobpush-carry.json")), (True, None))
out = c.run()
check("next run offers what the killed run had written", (U(1) in out, U(2) in out, c.data(".jobpush-prescan.json")), (True, True, None))
# a run killed during the scan: lines it appended are new against the saved prescan list, not against the current pipeline
c = Case(avisos="nuevo")
json.dump([], open(f"{c.root}/data/.jobpush-prescan.json", "w"))
open(f"{c.root}/data/pipeline.md", "w").write(PIPE0.replace("## Pending\n", "## Pending\n" + offer(7) + "\n"))
check("killed during the scan: the next run offers the lines it appended", U(7) in c.run(), True)

# buscar-empleos prints valid JSON that is not a list: no crash, offers go out unverified, nothing is lost
c = Case(avisos="nuevo")
out = c.run(new=[offer(1)], FAKE_REVISAR_RAW="5")
check("non-list triage output: unverified offer, no crash", (U(1) in out, "sin verificar" in out, c.data(".jobpush-carry.json")), (True, True, "[]"))
check("non-list triage output: exit 0", "unexpected" in c.stderr, False)

# the time budget: batches it does not reach are carried, then offered by the next run
c = Case(avisos="nuevo")
out = c.run(new=[offer(1), offer(2)], JOBPUSH_RUN_BUDGET=-1)
check("budget spent: nothing triaged, both carried, silent", (out, c.revlog and os.path.exists(c.revlog), len(json.loads(c.data(".jobpush-carry.json")))), ("", False, 2))
out = c.run()
check("budget: the carried offers go out on the next run", (U(1) in out, U(2) in out), (True, True))

# ---------------------------------------------------------------- scheduled-chain.mjs (the jobfinder's one-command chain)
NAV = "navent_searches:\n  - site: bumeran\n    keywords: [devops]\n    max_pages: 2\n"
c = Case(avisos="nuevo", chain=True)
out = c.run(new=[offer(1, "Environment Artist", "Studio One")], FAKE_CHAIN_OUT="log line before\n" + chain_json(new=1, closing=[closing_row(7, 2)]) + "\nlog line after")
args = c.data("chainargs").split()
check("chain: run instead of scan.mjs, liveness on, no navent without portals.yml, step timeout",
      (c.ran(), args), (0, ["--with-liveness", "--step-timeout", "1500"]))
check("chain: new offers come from the pipeline diff", (out.splitlines()[0], f"Environment Artist — Studio One — {U(1)}" in out), ("Encontré 1 oferta nueva que encaja:", True))
check("chain: closing-soon block before the ask", (f"Cierran pronto, de tu lista:\n- {SECRET} — Secret Role: cierra en 2 días (2030-01-07)" in out, out.index("Cierran pronto") < out.index("evaluá")), (True, True))
log = c.data("jobpush.log")
check("chain: log has per-step seconds/ok and counts", ("chain=scan:578s:ok,liveness:301s:ok,closing:0s:ok" in log, "chain_new=1" in log, "diff=1" in log, "chain_closing=1" in log), (True,) * 4)
check("chain: no label, company or url in jobpush.log", (SECRET in log, "Secret" in log, "example.com" in log), (False, False, False))
check("chain: busy marker held during the run, scratch stdout deleted", (c.data("sawrunning"), c.data(".jobpush-chain.out"), c.data(".jobpush-running")), ("1", None, None))
check("chain: told hashes only in the state file", (SECRET in (c.data(".jobpush-state.json") or ""), len(c.state()["closing_told"])), (False, 1))
# nothing new at all: a closing-soon item alone makes a "nuevo" message, once; again in its last day; never twice at the same stage
c = Case(avisos="nuevo", chain=True)
out = c.run(FAKE_CHAIN_OUT=chain_json(closing=[closing_row(7, 5)]))
check("chain: closing-soon alone makes a nuevo message", out, f"Cierran pronto, de tu lista:\n- {SECRET} — Secret Role: cierra en 5 días (2030-01-07)\n")
check("chain: same item the next day is not repeated", c.run(FAKE_CHAIN_OUT=chain_json(closing=[closing_row(7, 4)]), now=1_800_086_400), "")
out = c.run(FAKE_CHAIN_OUT=chain_json(closing=[closing_row(7, 1)]), now=1_800_172_800)
check("chain: and it is told once more in its last day", out, f"Cierran pronto, de tu lista:\n- {SECRET} — Secret Role: cierra mañana\n")
check("chain: last-day reminder is not repeated", c.run(FAKE_CHAIN_OUT=chain_json(closing=[closing_row(7, 0)]), now=1_800_259_200), "")
c = Case(avisos="nuevo", chain=True)
out = c.run(FAKE_CHAIN_OUT=chain_json(closing=[closing_row(i, i % 3) for i in range(1, 6)]))
check("chain: at most three closing lines and +2", (sum(1 for l in out.splitlines() if l.startswith("- ")), "+2 más" in out), (3, True))
out2 = c.run(FAKE_CHAIN_OUT=chain_json(closing=[closing_row(i, i % 3) for i in range(1, 6)]), now=1_800_086_400)
check("chain: the closing items past the cap are not marked told, they ride on the next message",
      (len(c.state()["closing_told"]), sum(1 for l in out2.splitlines() if l.startswith("- ")), "+" in out2), (5, 2, False))
# no company/role/days: defensive output
c = Case(avisos="nuevo", chain=True)
out = c.run(FAKE_CHAIN_OUT=chain_json(closing=[{"num": 4}, {"closes": "2030-01-09"}, "junk", None, 5]))
check("chain: odd closing rows do not crash", ("- #4: cierra pronto" in out, "- una oferta de tu lista: cierra el 2030-01-09" in out, "unexpected" in c.stderr), (True, True, False))
# expired: never a message by itself in nuevo, but it rides on the next one, once
c = Case(avisos="nuevo", chain=True)
exp = [expired_row(1), expired_row(2), expired_row(3), expired_row(4)]
check("chain: expired alone is silent in nuevo", c.run(FAKE_CHAIN_OUT=chain_json(expired=exp), now=1_800_000_000), "")
out = c.run(new=[offer(1)], FAKE_CHAIN_OUT=chain_json(new=1, expired=exp), now=1_800_086_400)
check("chain: expired rides on the next message: count, three labels, +1", ("4 de tus ofertas evaluadas o postuladas ya cerraron:" in out, f"- #1 {SECRET} 1 · Secret Role (Applied)" in out,
      f"#4 {SECRET}" in out, "+1 más" in out, "example.com/applied" in out), (True, True, False, True, False))
out = c.run(new=[offer(2)], FAKE_CHAIN_OUT=chain_json(new=1, expired=exp), now=1_800_172_800)
check("chain: ... the one past the cap rides on the following message, the three told are not repeated", ("1 de tus ofertas evaluadas o postuladas ya cerró:" in out, f"#4 {SECRET}" in out, "#1 " in out), (True, True, False))
check("chain: ... and then nothing is repeated", c.run(new=[offer(4)], FAKE_CHAIN_OUT=chain_json(new=1, expired=exp), now=1_800_216_000).count("cerr"), 0)
out = c.run(new=[offer(3)], FAKE_CHAIN_OUT=chain_json(new=1, expired=exp + [expired_row(9)]), now=1_800_259_200)
check("chain: only the newly closed one is told", ("1 de tus ofertas evaluadas o postuladas ya cerró:" in out, "#9" in out, "#1 " in out), (True, True, False))
c = Case(avisos="nuevo", chain=True)
exp5 = [expired_row(i) for i in range(1, 6)]
out = c.run(new=[offer(1)], FAKE_CHAIN_OUT=chain_json(new=1, expired=exp5), now=1_800_000_000)
out2 = c.run(new=[offer(2)], FAKE_CHAIN_OUT=chain_json(new=1, expired=exp5), now=1_800_086_400)
check("chain: expired items past the cap are named on a later message, not lost",
      ("#4 " in out, "#4 " in out2, "#5 " in out2, "#1 " in out2, len(c.state()["expired_told"])), (False, True, True, False, 5))
c = Case(avisos="diario", chain=True)
out = c.run(FAKE_CHAIN_OUT=chain_json(expired=[expired_row(1)]))
check("chain: diario nothing new + expired in one message", out, f"Revisé las ofertas de hoy: nada nuevo que encaje.\n\n1 de tus ofertas evaluadas o postuladas ya cerró:\n- #1 {SECRET} 1 · Secret Role (Applied)\n")
c = Case(avisos="nuevo", chain=True)
c.run(FAKE_CHAIN_OUT=chain_json(closing=[closing_row(7, 5)]), args=["--dry-run"])
check("chain: a dry run tells nothing for good", c.data(".jobpush-state.json"), None)
c = Case(avisos="nuevo", lang="ru", chain=True)
out = c.run(FAKE_CHAIN_OUT=chain_json(closing=[closing_row(1, 0), closing_row(2, 1), closing_row(3, 5)], expired=[expired_row(1)]))
check("chain: ru texts", ("Скоро закрываются, из вашего списка:" in out, "закрывается сегодня" in out, "закрывается завтра" in out, "через 5 дней (2030-01-07)" in out,
      "Закрылась 1 из ваших оценённых или поданных вакансий:" in out), (True,) * 5)
c = Case(avisos="nuevo", lang="en", chain=True)
out = c.run(FAKE_CHAIN_OUT=chain_json(closing=[closing_row(1, 3)], expired=[expired_row(1), expired_row(2)]), new=[offer(1)], FAKE_SCAN_NEW=offer(1))
check("chain: en texts", ("Closing soon, from your list:" in out, "closes in 3 days (2030-01-07)" in out, "2 of your evaluated or applied jobs closed:" in out), (True,) * 3)
# busy: silent, logged, no failure counted, nothing left behind
c = Case(avisos="nuevo", chain=True)
c.run(FAKE_CHAIN_OUT='{"status":"busy"}', now=1_800_000_000)
out = c.run(FAKE_CHAIN_OUT='{"status":"busy"}', now=1_800_086_400)
check("chain busy: silent, no failure counted, logged, prescan and marker gone",
      (out, c.state().get("failures"), c.data("jobpush.log").count("skip-chain-busy"), c.data(".jobpush-prescan.json"), c.data(".jobpush-running"), c.stderr), ("", None, 2, None, None, ""))
c.run(FAKE_CHAIN_OUT=chain_json(), now=1_800_172_800)
check("chain busy: no failure streak either way", c.state()["failures"], 0)
# a prescan left by a dead run survives a busy skip
c = Case(avisos="nuevo", chain=True)
json.dump([], open(f"{c.root}/data/.jobpush-prescan.json", "w"))
open(f"{c.root}/data/pipeline.md", "w").write(PIPE0.replace("## Pending\n", "## Pending\n" + offer(7) + "\n"))
c.run(FAKE_CHAIN_OUT='{"status":"busy"}')
check("chain busy: the dead run's prescan is kept", c.data(".jobpush-prescan.json"), "[]")
check("chain busy: ... so the next real run offers its lines", U(7) in c.run(FAKE_CHAIN_OUT=chain_json()), True)
# failures: outage, non-zero exit, unparseable, timeout all use the failure state machine
c = Case(avisos="nuevo", chain=True)
r1 = c.run(FAKE_CHAIN_OUT=chain_json("outage"), FAKE_CHAIN_RC=2, now=1_800_000_000)
r2 = c.run(FAKE_CHAIN_OUT=chain_json("outage"), FAKE_CHAIN_RC=2, now=1_800_086_400)
check("chain outage: silent once, a message the second time", (r1, r2.startswith("No pude hacer la revisión diaria")), ("", True))
check("chain outage: failure counted, logged with exit and steps", (c.state()["failures"], "result=scan-failed exit=2" in c.data("jobpush.log"), "chain=scan:578s:ok" in c.data("jobpush.log")), (2, True, True))
c = Case(avisos="nuevo", chain=True)
check("chain: status outage with exit 0 is a failure too", (c.run(FAKE_CHAIN_OUT=chain_json("outage")), c.state()["failures"], "exit=outage" in c.data("jobpush.log")), ("", 1, True))
c = Case(avisos="nuevo", chain=True)
check("chain: ok JSON but non-zero exit is a failure", (c.run(FAKE_CHAIN_OUT=chain_json(), FAKE_CHAIN_RC=1), c.state()["failures"]), ("", 1))
for name, raw in (("garbage", "Error: something broke"), ("empty", ""), ("truncated", chain_json()[:60]), ("no status", '{"steps":[]}'), ("unknown status", chain_json("weird"))):
    c = Case(avisos="nuevo", chain=True)
    check(f"chain {name}: failure, silent the first time", (c.run(FAKE_CHAIN_OUT=raw), c.state().get("failures")), ("", 1))
c = Case(avisos="nuevo", chain=True)
c.run(FAKE_CHAIN_OUT="not json", new=[offer(1)])
check("chain unparseable: exit=nojson logged, offers the chain wrote are carried", ("exit=nojson" in c.data("jobpush.log"), c.data(".jobpush-carry.json") == json.dumps([U(1)])), (True, True))
c = Case(avisos="nuevo", chain=True)
t0 = time.time()
check("chain timeout: failure, killed", (c.run(JOBPUSH_CHAIN_TIMEOUT=1, FAKE_SCAN_SLEEP=30, FAKE_CHAIN_OUT=chain_json()), c.state()["failures"], time.time() - t0 < 20), ("", 1, True))
check("chain timeout: logged", "exit=timeout" in c.data("jobpush.log"), True)
# a dead scan step beside a working liveness step is a scan failure, not a clean run
dead_scan = [{"name": "scan", "ok": False, "exitCode": None, "signal": "SIGTERM", "timedOut": True, "seconds": 1500.0, "stderrTail": "scan boom line"},
             {"name": "liveness", "ok": True, "exitCode": 1, "signal": None, "timedOut": False, "seconds": 301.2, "stderrTail": "liveness " + SECRET},
             {"name": "closing", "ok": False, "exitCode": 1, "signal": None, "timedOut": False, "seconds": 0.4, "stderrTail": "closing " + SECRET}]
c = Case(avisos="diario", chain=True)
r1 = c.run(new=[offer(1)], FAKE_CHAIN_OUT=chain_json(steps=dead_scan), now=1_800_000_000)
r2 = c.run(FAKE_CHAIN_OUT=chain_json(steps=dead_scan), now=1_800_086_400)
check("chain scan step failed (status ok): failure counted, no false 'nada nuevo', the second day says it could not run",
      (r1, r2.startswith("No pude hacer la revisión diaria"), c.state()["failures"], "exit=scanstep" in c.data("jobpush.log")), ("", True, 2, True))
check("chain scan step failed: the offers it wrote are carried", c.data(".jobpush-carry.json") == json.dumps([U(1)]), True)
check("chain: failed scan step -> its stderr tail in jobpush-scan.log, never the closing / liveness tails",
      ("scan boom line" in (c.data("jobpush-scan.log") or ""), SECRET in (c.data("jobpush-scan.log") or ""), SECRET in (c.data("jobpush.log") or "")), (True, False, False))
c = Case(avisos="nuevo", chain=True)
c.run(FAKE_CHAIN_OUT="Error [ERR_MODULE_NOT_FOUND]: cannot find lib/dir-lock.mjs\n{\"x\": \"" + SECRET + "\"", FAKE_CHAIN_RC=1)
lg = c.data("jobpush-scan.log") or ""
check("chain nojson: the plain error line is logged, JSON-looking lines are not", ("ERR_MODULE_NOT_FOUND" in lg, SECRET in lg), (True, False))
c = Case(avisos="nuevo", chain=True)
c.run(FAKE_CHAIN_OUT=chain_json())
check("chain ok: nothing added to jobpush-scan.log", (c.data("jobpush-scan.log") or "").strip(), "")

# a pretty-printed JSON among log lines is found, and the last object with a status wins
check("parse_chain_json: pretty-printed between log lines", jp.parse_chain_json("x {not json\n" + json.dumps(json.loads(chain_json(new=2)), indent=2) + "\ntail {")["newAddedTotal"], 2)
check("parse_chain_json: nothing", (jp.parse_chain_json(""), jp.parse_chain_json('{"a":1}')), (None, None))
# fallback: no scheduled-chain.mjs (an older jobfinder) -> the plain scan, exactly as before
c = Case(avisos="nuevo", chain=False)
out = c.run(new=[offer(1)], FAKE_CHAIN_OUT=chain_json())
check("fallback: chain file missing -> scan.mjs path", (c.ran(), c.data("chainargs"), out.startswith("Encontré 1 oferta")), (1, None, True))
check("fallback: log has no chain fields", "chain" in c.data("jobpush.log"), False)
# --with-navent only when portals.yml has an enabled Bumeran/ZonaJobs search
def navent_args(portals):
    c = Case(avisos="nuevo", chain=True, portals=portals)
    c.run(FAKE_CHAIN_OUT=chain_json())
    return "--with-navent" in c.data("chainargs").split()
check("navent: bumeran search -> flag", navent_args(NAV), True)
check("navent: zonajobs search, quoted, between other keys -> flag", navent_args("title_filter:\n  positive: [a]\nnavent_searches:\n  - site: \"zonajobs\"  # mirror\n    keywords:\n      - devops\njob_boards:\n  - name: X\n"), True)
check("navent: no portals.yml -> no flag", navent_args(None), False)
check("navent: empty / inline-empty section -> no flag", (navent_args("navent_searches: []\n"), navent_args("navent_searches:\njob_boards:\n  - name: Bumeran\n    enabled: true\n")), (False, False))
check("navent: commented-out section -> no flag", navent_args("# navent_searches:\n#   - site: bumeran\n#     keywords: [devops]\n"), False)
check("navent: entry switched off -> no flag", navent_args(NAV + "    enabled: false\n"), False)
check("navent: a Bumeran board elsewhere (job_boards / search queries) is not enough", navent_args("job_boards:\n  - name: Bumeran\n    enabled: true\nsearch_queries:\n  - name: Bumeran x\n    enabled: true\n"), False)
check("navent: entry without keywords or with another site -> no flag", (navent_args("navent_searches:\n  - site: bumeran\n"), navent_args("navent_searches:\n  - site: computrabajo\n    keywords: [a]\n")), (False, False))
for name, por in (("keywords: []", "navent_searches:\n  - site: bumeran\n    keywords: []\n"), ("bare keywords:", "navent_searches:\n  - site: bumeran\n    keywords:\nportals: x\n"),
                  ("keywords: ''", "navent_searches:\n  - site: bumeran\n    keywords: ''\n"), ("empty block list", "navent_searches:\n  - site: bumeran\n    keywords:\n    max_pages: 2\n"),
                  ("query nested under another key", "navent_searches:\n  - site: bumeran\n    filters:\n      query: x\n")):
    check(f"navent: {name} -> no flag (scan-navent would throw)", navent_args(por), False)
check("navent: query, scalar keywords and a block list at the key's own indent -> flag",
      (navent_args("navent_searches:\n  - site: bumeran\n    query: devops\n"), navent_args("navent_searches:\n  - site: zonajobs\n    keywords: sre\n"),
       navent_args("navent_searches:\n  - site: bumeran\n    keywords:\n    - devops\n")), (True, True, True))
check("navent: a bad entry beside a good one -> flag for the good one", navent_args("navent_searches:\n  - site: bumeran\n    keywords: []\n  - site: zonajobs\n    keywords: [sre]\n"), True)
check("navent: one of several entries off, another on -> flag", navent_args(NAV + "  - site: zonajobs\n    keywords: [x]\n    enabled: no\n  - site: zonajobs\n    keywords: [y]\n"), True)

# the waker keeps a stack with a fresh jobpush busy marker awake (docker mocked)
wspec = importlib.util.spec_from_file_location("waker", f"{HERE}/ops/wake/waker.py")
wk = importlib.util.module_from_spec(wspec); wspec.loader.exec_module(wk)
class R:
    def __init__(self, rc, out): self.returncode, self.stdout, self.stderr = rc, out, ""
calls = []
def fake_docker(*a, **k):
    calls.append(a)
    if a[:2] == ("exec", "brain") and a[2] == "find":
        return R(0, "/workdir/jobfinder/data/.jobpush-running\n" if fake_docker.fresh else "")
    return R(0, "")
fake_docker.fresh = True
wk.docker = fake_docker
st = wk.Stack.__new__(wk.Stack)
st.brain, st.busy_marker, st.busy_marker_minutes = "brain", "/workdir/jobfinder/data/.jobpush-running", 90
check("waker: fresh busy marker", st.marker_fresh(), True)
fake_docker.fresh = False
check("waker: no or stale busy marker", st.marker_fresh(), False)
check("waker: asks find for a recent mtime", [a for a in calls if a[2] == "find"][0][3:], ("/workdir/jobfinder/data/.jobpush-running", "-mmin", "-90"))
st.busy_marker = ""
check("waker: marker check can be disabled", st.marker_fresh(), False)

# ---- the shared store: used only while the fetcher's marker says it is fresh ----
_spec = importlib.util.spec_from_file_location("jobpush_store_t", os.path.join(HERE, "jobpush.py"))
_jp = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_jp)
_store = os.path.join(tmp, "shared-store"); os.makedirs(_store)
def _env(**kw):
    return {"JOBPUSH_SHARED_STORE": _store, **kw}
_now = 1_000_000.0
check("store: no marker -> own", _jp.use_shared_store({"now": _now}, _env()), "own")
json.dump({"at": _now - 3600, "ttl_ms": 108000000}, open(os.path.join(_store, ".fetched"), "w"))
e = _env()
check("store: fresh marker -> shared", _jp.use_shared_store({"now": _now}, e), "shared")
check("store: cache-only on, pointed at the store", (e["CAREER_OPS_HTTP_CACHE_ONLY"], e["CAREER_OPS_HTTP_CACHE_DIR"], e["CAREER_OPS_HTTP_CACHE_TTL_MS"]), ("1", _store, "108000000"))
check("store: never asks to keep no-store bodies (that is the fetcher's option)", "CAREER_OPS_HTTP_CACHE_STORE_NO_STORE" in e, False)
e = _env()
check("store: marker older than its TTL -> own, env untouched", (_jp.use_shared_store({"now": _now + 31 * 3600}, e), "CAREER_OPS_HTTP_CACHE_ONLY" in e), ("own", False))
check("store: a marker from the future is not trusted", _jp.use_shared_store({"now": _now - 7200}, _env()), "own")
open(os.path.join(_store, ".fetched"), "w").write("{broken")
check("store: a broken marker -> own", _jp.use_shared_store({"now": _now}, _env()), "own")
json.dump({"at": _now, "ttl_ms": 108000000}, open(os.path.join(_store, ".fetched"), "w"))
check("store: hand-set operator variables are respected", _jp.use_shared_store({"now": _now}, _env(CAREER_OPS_HTTP_CACHE_DIR="/x")), "own")

print("\n".join(fails) or "jobpush_selftest: all checks passed")
sys.exit(1 if fails else 0)
