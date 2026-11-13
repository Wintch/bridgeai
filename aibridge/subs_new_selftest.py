#!/usr/bin/env python3
"""subs_new.py offline, with a fake subs-fetch: the --new round, then a --backlog slice; silent unless a person must know.
Run: python3 -I subs_new_selftest.py"""
import json, os, subprocess, sys, tempfile, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(f"{name}: got {got!r}, want {want!r}")

import atexit, shutil
tmp = tempfile.mkdtemp(prefix="subsnew-")
atexit.register(shutil.rmtree, tmp, True)
fake = os.path.join(tmp, "fake_subs_fetch.py")
open(fake, "w").write(textwrap.dedent('''
    import json, os, sys
    log = os.environ["FAKE_LOG"]
    open(log, "a").write(json.dumps(sys.argv[1:]) + "\\n")
    mode = "backlog" if "--backlog" in sys.argv else ("status" if "--status" in sys.argv else "new")
    print(os.environ.get("FAKE_OUT_" + mode.upper(), ""))
    sys.exit(int(os.environ.get("FAKE_RC_" + mode.upper(), "0")))
'''))

def run(**env):
    """Runs subs_new.py; returns its exit code, what it printed and the subs-fetch calls other than the last --status."""
    log = os.path.join(tmp, "log.jsonl")
    if os.path.exists(log): os.remove(log)
    e = dict(os.environ, SUBS_FETCH_CMD=f"{sys.executable} {fake}", SUBS_PARENT="/p", FAKE_LOG=log)
    e.update(env)
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "subs_new.py")], env=e, capture_output=True, text=True, timeout=60)
    calls = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    if calls and calls[-1][0] == "--status":
        calls = calls[:-1]
    return r.returncode, r.stdout.strip(), calls

code, out, calls = run()
check("all fine: --new, then a --backlog slice of 300, nothing printed",
      (code, out, calls), (0, "", [["--all", "/p", "--new"], ["--all", "/p", "--backlog", "300"]]))
code, out, calls = run(SUBS_BACKLOG_PER_RUN="120")
check("the slice size comes from SUBS_BACKLOG_PER_RUN", calls[1], ["--all", "/p", "--backlog", "120"])
code, out, calls = run(SUBS_BACKLOG_PER_RUN="0")
check("SUBS_BACKLOG_PER_RUN=0 turns the backlog step off", len(calls), 1)
code, out, calls = run(FAKE_RC_NEW="75", FAKE_OUT_NEW="subs-fetch: RATE LIMITED by the site")
check("rate limit in --new: the person is told once, no backlog slice", ("frenó" in out, len(calls)), (True, 1))
code, out, calls = run(FAKE_RC_NEW="3")
check("a channel already running elsewhere (3) is fine: backlog still runs, silent", (out, len(calls)), ("", 2))
code, out, calls = run(FAKE_RC_NEW="1", FAKE_OUT_NEW="boom")
check("a real failure of --new is told, no backlog", ("falló (código 1)" in out, len(calls)), (True, 1))
code, out, calls = run(FAKE_RC_BACKLOG="75", FAKE_OUT_BACKLOG="subs-fetch: SOFT BLOCK: more than 50 %")
check("rate limit / soft block in the backlog: silent (the next round tries again)", out, "")
code, out, calls = run(FAKE_RC_BACKLOG="1", FAKE_OUT_BACKLOG="line1\nline2")
check("a real failure of the backlog step is told", "pendiente de subtítulos falló (código 1)" in out, True)
code, out, calls = run(SUBS_FETCH_CMD="/nonexistent/subs-fetch")
check("subs-fetch missing: said once, exit 0", ("no pude ejecutar subs-fetch" in out, code), (True, 0))

# ---- step 3: a backlog that does not go down for STALL_H hours is told once ----
import time
par = os.path.join(tmp, "parent"); os.makedirs(par)
st_path = os.path.join(par, ".subs-stall.json")
def status_out(n): return f"total: 2 of 9 channels COMPLETE, 7 not complete with {n} videos missing; no rate-limit pause"
code, out, calls = run(SUBS_PARENT=par, FAKE_OUT_STATUS=status_out(3985))
log = [json.loads(l) for l in open(os.path.join(tmp, "log.jsonl"))]
check("step 3 asks --status after the rounds, first time silent", (log[-1], out), (["--status", par], ""))
check("step 3 remembers the count and since when", (json.load(open(st_path))["last"], json.load(open(st_path))["told"]), (3985, False))
json.dump({"since": time.time() - 25 * 3600, "told": False, "last": 3985}, open(st_path, "w"))
code, out, calls = run(SUBS_PARENT=par, FAKE_OUT_STATUS=status_out(3985))
check("not lower for 25 h: the person is told, with the number", ("no baja desde hace 25 h" in out and "faltan 3985" in out), True)
code, out, calls = run(SUBS_PARENT=par, FAKE_OUT_STATUS=status_out(3990))
check("told once: a later round of the same stall is silent (new uploads raising the count change nothing)", out, "")
code, out, calls = run(SUBS_PARENT=par, FAKE_OUT_STATUS=status_out(3700))
check("it went down: the clock starts again, silent", (out, json.load(open(st_path))["told"], json.load(open(st_path))["last"]), ("", False, 3700))
json.dump({"since": time.time() - 23 * 3600, "told": False, "last": 3700}, open(st_path, "w"))
code, out, calls = run(SUBS_PARENT=par, FAKE_OUT_STATUS=status_out(3700))
check("23 h without moving: still silent", out, "")
code, out, calls = run(SUBS_PARENT=par, FAKE_OUT_STATUS="total: 9 of 9 channels COMPLETE; no rate-limit pause")
check("all COMPLETE: silent and the state is cleared", (out, os.path.exists(st_path)), ("", False))
code, out, calls = run(SUBS_PARENT=par, FAKE_RC_STATUS="2", FAKE_OUT_STATUS=status_out(10))
check("--status failing: silent, nothing remembered", (out, os.path.exists(st_path)), ("", False))
code, out, calls = run(SUBS_PARENT=par, SUBS_STALL_HOURS="0", FAKE_OUT_STATUS=status_out(5))
check("SUBS_STALL_HOURS sets the threshold", "faltan 5" in out, True)

print("\n".join(fails) or "subs_new_selftest: all ok")
sys.exit(1 if fails else 0)
