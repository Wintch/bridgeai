#!/usr/bin/env python3
"""Selftest for patches/fresh_session.py: the patch applies once (and on the real pinned Hermes when it is at hand), aborts when Hermes changes, and the chore it
adds does what the docstring says on stand-ins of the runner: it replaces a conversation that holds an old prompt or tools only when the model's view
changed (fingerprint), only while no agent runs, only for conversations idle long enough, through the same /new handler whose reply is thrown away, once
per conversation per round, never for sessions made after the round began or for other platforms, and it gives up after three failed tries.

Run from anywhere:  python3 -I fresh_session_selftest.py
"""
import asyncio, datetime as dt, importlib.util, json, os, subprocess, sys, tempfile
import atexit as _a, shutil as _s, signal as _g
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_a.register(_s.rmtree, tempfile.tempdir, True)
_g.signal(_g.SIGTERM, lambda *_: sys.exit(143))
HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.path.join(HERE, "patches", "fresh_session.py")
ok = True
def chk(what, got, want=True):
    global ok; good = got == want; ok &= good
    print(("ok   " if good else "FAIL ") + what + ("" if good else f"  got={got!r} want={want!r}"), flush=True)

def chkd(what, cond, detail=""):
    chk(what, bool(cond), True)
    if not cond and detail:
        print("     detail:", str(detail)[-160:])

tmp = tempfile.mkdtemp()
STANDIN = '''# a stand-in of Hermes's gateway/run.py: the same anchors and module-level names the patch needs
import asyncio
import json
import os
import time
import logging
logger = logging.getLogger("standin")

class MessageEvent:
    def __init__(self, text, source=None):
        self.text, self.source = text, source

def _housekeeping_memory_trim() -> None:
    pass

CHORES = [
        (1, "gateway housekeeping memory trim", _housekeeping_memory_trim),
]
'''
path = os.path.join(tmp, "run.py"); open(path, "w").write(STANDIN)
r = subprocess.run([sys.executable, "-I", PATCH, path], capture_output=True, text=True)
chkd("the patch applies to a stand-in of run.py", r.returncode == 0 and "chore added" in r.stdout, r.stdout + r.stderr)
r = subprocess.run([sys.executable, "-I", PATCH, path], capture_output=True, text=True)
chkd("applying it again is a no-op", r.returncode == 0 and "already patched" in r.stdout and open(path).read().count("aibridge-patch: fresh_session") == 2, r.stdout)
chkd("the patched file compiles and the chore is in the list", subprocess.run([sys.executable, "-m", "py_compile", path]).returncode == 0 and '"aibridge fresh session"' in open(path).read())
for name, bad in (("no memory-trim chore", STANDIN.replace('        (1, "gateway housekeeping memory trim", _housekeeping_memory_trim),\n', "")),
                  ("two function anchors", STANDIN + "\ndef _housekeeping_memory_trim() -> None:\n    pass\n"),
                  ("no MessageEvent", STANDIN.replace("MessageEvent", "Other")),
                  ("no logger", STANDIN.replace("logger = ", "log = "))):
    p2 = os.path.join(tmp, "bad.py"); open(p2, "w").write(bad)
    r = subprocess.run([sys.executable, "-I", PATCH, p2], capture_output=True, text=True)
    chkd(f"it aborts loudly when Hermes changed: {name}", r.returncode != 0 and open(p2).read() == bad, r.stderr[-100:])
# with a sibling that lost the /new handler it aborts too
os.makedirs(f"{tmp}/gw"); open(f"{tmp}/gw/run.py", "w").write(STANDIN); open(f"{tmp}/gw/slash_commands_session.py", "w").write("# no handler here\n")
r = subprocess.run([sys.executable, "-I", PATCH, f"{tmp}/gw/run.py"], capture_output=True, text=True)
chkd("it aborts when the /new handler it calls is gone from Hermes", r.returncode != 0 and "_handle_reset_command" in r.stderr, r.stderr[-120:])
real = os.environ.get("HERMES_SRC_GATEWAY", "")   # a checkout of the pinned Hermes gateway/ directory, when at hand
if real and os.path.isdir(real):
    shutil_dst = f"{tmp}/real"; _s.copytree(real, shutil_dst)
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "patches", "idle_compact.py"), f"{shutil_dst}/run.py"], capture_output=True)
    r = subprocess.run([sys.executable, "-I", PATCH, f"{shutil_dst}/run.py"], capture_output=True, text=True)
    chkd("it applies and compiles on the real pinned Hermes after the compaction patch", r.returncode == 0 and subprocess.run([sys.executable, "-m", "py_compile", f"{shutil_dst}/run.py"]).returncode == 0, r.stderr[-120:])

# ---- the logic, on stand-ins of the runner
ns = {"__name__": "standin"}
exec(compile(open(path).read(), path, "exec"), ns)
fp_files = [f"{tmp}/SOUL.md", f"{tmp}/paquetes.json", f"{tmp}/missing.json"]
open(fp_files[0], "w").write("rules v1"); open(fp_files[1], "w").write("{}")
ns["_AIBRIDGE_FRESH_FILES"] = tuple(fp_files)
ns["_AIBRIDGE_FRESH_STATE"] = f"{tmp}/fresh.json"
NOW = 1_900_000_000.0
D = lambda t: dt.datetime.fromtimestamp(t)
class Plat:
    def __init__(self, v): self.value = v
class Origin:
    def __init__(self, key, plat="telegram"): self.key, self.platform = key, Plat(plat)
class Entry:
    def __init__(self, key, created, updated, plat="telegram"):
        self.session_key, self.created_at, self.updated_at, self.origin = key, D(created), D(updated), Origin(key, plat)
class Store:
    def __init__(self, entries): self.entries = entries
    def list_sessions(self, active_minutes=None): return list(self.entries)
class Runner:
    def __init__(self, entries, fail=None):
        self._running_agents, self.session_store, self.resets, self.fail = {}, Store(entries), [], fail or set()
    async def _handle_reset_command(self, event):
        k = event.source.key
        if k in self.fail: raise RuntimeError("boom")
        assert event.text == "/new"
        self.resets.append(k)
        for e in self.session_store.entries:
            if e.session_key == k: e.created_at = e.updated_at = D(NOW + 1)      # like the real one: a new session, active just now
        return "✨ new session started (the reply the person must NOT get)"
step = lambda r, idle=600, now=NOW: asyncio.run(ns["_aibridge_fresh_async"](r, idle, now))

r1 = Runner([Entry("tg:A", NOW - 9000, NOW - 5000)])
out = step(r1)
chk("first time (no state): an old idle conversation is replaced through the /new handler", (out["status"], r1.resets), ("reset", ["tg:A"]))
st = json.load(open(ns["_AIBRIDGE_FRESH_STATE"]))
chk("the state keeps counts and session keys only, and the round is complete", (st["complete"], st["done"], sorted(st)), (True, ["tg:A"], ["complete", "done", "fp", "since", "tries"]))
chk("nothing is sent to the person: the handler's reply is dropped (the chore never sends anything)", "send" not in open(path).read().split("_aibridge_fresh_async")[1].split("def _aibridge_fresh(")[0].lower().replace("session_store", ""))
r1.resets.clear(); out = step(r1, now=NOW + 5)
chk("same fingerprint afterwards: nothing to do", (out["status"], r1.resets), ("same", []))
open(fp_files[0], "w").write("rules v2 (a new capability)")
out = step(r1, now=NOW + 100)
chk("the model's view changed (SOUL.md): a new round opens, and tg:A (reset a moment ago, so newer than the previous round) is not reset twice for a round it is not older than",
    (json.load(open(ns["_AIBRIDGE_FRESH_STATE"]))["fp"] == ns["_aibridge_fresh_fingerprint"](), out["status"] in ("complete", "waiting")), (True, True))
open(fp_files[0], "w").write("rules v3")
r2 = Runner([Entry("tg:A", NOW - 9000, NOW - 5000), Entry("tg:B", NOW - 9000, NOW - 30)])   # B is in use right now
step(r2, now=NOW + 200)        # first sighting of v3 opens the round: A idle, B busy
chk("a conversation idle long enough is replaced, one in use is not (nobody is cut mid-sentence)", r2.resets, ["tg:A"])
st = json.load(open(ns["_AIBRIDGE_FRESH_STATE"]))
chk("the round stays open while a session waits", st["complete"], False)
out = step(r2, now=NOW + 200 + 700)
chk("later, once B has been idle long enough, it is replaced and the round completes", (r2.resets, json.load(open(ns["_AIBRIDGE_FRESH_STATE"]))["complete"]), (["tg:A", "tg:B"], True))
out = step(r2, now=NOW + 5000)
chk("and it does not repeat", (out["status"], r2.resets), ("same", ["tg:A", "tg:B"]))

open(fp_files[1], "w").write('{"packs": ["sitio"]}')           # a pack switched on
r3 = Runner([Entry("tg:C", NOW - 9000, NOW - 5000)]); r3._running_agents = {"x": object()}
out = step(r3, now=NOW + 6000)
chk("while an agent runs it does nothing (busy), and the round stays open", (out["status"], r3.resets, json.load(open(ns["_AIBRIDGE_FRESH_STATE"]))["complete"]), ("busy", [], False))
r3._running_agents = {}; out = step(r3, now=NOW + 6060)
chk("when the agent is done, the pack change reaches the conversation", (out["status"], r3.resets), ("reset", ["tg:C"]))

open(fp_files[1], "w").write('{"packs": ["sitio", "edicion"]}')
r4 = Runner([Entry("tg:D", NOW - 9000, NOW - 5000, plat="api_server"), Entry("tg:E", NOW - 9000, NOW - 5000)])
step(r4, now=NOW + 7000)
chk("only Telegram conversations are touched (a web chat is its own conversation)", r4.resets, ["tg:E"])

open(fp_files[1], "w").write('{"packs": []}')
r5 = Runner([Entry("tg:F", NOW - 9000, NOW - 5000)], fail={"tg:F"})
for i in range(4):
    step(r5, now=NOW + 8000 + i)
st = json.load(open(ns["_AIBRIDGE_FRESH_STATE"]))
chk("a session whose reset keeps failing is tried three times, then given up for this round, and the round completes", (st["tries"].get("tg:F"), "tg:F" in st["done"], st["complete"]), (3, True, True))

open(fp_files[1], "w").write('{"packs": ["x"]}')
r6 = Runner([Entry("tg:G", NOW + 50, NOW + 50)])           # created AFTER the round starts: already new
st0 = {"fp": ns["_aibridge_fresh_fingerprint"](), "since": NOW + 20, "done": [], "tries": {}, "complete": False}
json.dump(st0, open(ns["_AIBRIDGE_FRESH_STATE"], "w"))
out = step(r6, now=NOW + 5000)
chk("a conversation created after the round began is already new: nothing to reset, round complete", (r6.resets, out["status"]), ([], "complete"))

# fingerprint
f1 = ns["_aibridge_fresh_fingerprint"](); f2 = ns["_aibridge_fresh_fingerprint"]()
open(fp_files[0], "w").write("changed"); f3 = ns["_aibridge_fresh_fingerprint"]()
chk("the fingerprint is stable and follows the files", (f1 == f2, f1 != f3, len(f1)), (True, True, 16))
# the chore wrapper
class BoomLoop:
    def __getattr__(self, n): raise AssertionError("the chore must not touch the loop")
ns["_AIBRIDGE_FRESH_ON"] = False
ns["_aibridge_fresh"](object(), BoomLoop())
chk("AIBRIDGE_FRESH_SESSION=0 turns the chore off (it never touches the loop)", True)
ns["_AIBRIDGE_FRESH_ON"] = True
ns["_aibridge_fresh"](None, BoomLoop())
chk("no runner yet (startup): nothing happens", True)
ns["_AIBRIDGE_FRESH_STATE"] = "/nonexistent-folder/x.json"
ns["_aibridge_fresh"](object(), BoomLoop())
chk("no /workdir (a test image): nothing happens", True)
src_text = open(PATCH).read()
chk("the Dockerfile applies it after the compaction patch", "fresh_session.py" in open(os.path.join(HERE, "Dockerfile.hermes-agent")).read()
    and open(os.path.join(HERE, "Dockerfile.hermes-agent")).read().index("idle_compact.py") < open(os.path.join(HERE, "Dockerfile.hermes-agent")).read().index("fresh_session.py"))

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
