#!/usr/bin/env python3
"""Offline checks for ops/sharing.py: the registry, the per-stack choices and the flags chat_review gets.
Run: python3 -I ops/sharing_selftest.py"""
import json, os, subprocess, sys, tempfile
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all temp files in one folder, removed on exit
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sharing  # noqa: E402

root = tempfile.mkdtemp()
os.makedirs(f"{root}/ops")
fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)


def choose(stack, level):
    d = sharing.stack_workdir(stack, root)
    os.makedirs(d, exist_ok=True)
    p = f"{d}/.compartir.json"
    if level is None:
        if os.path.exists(p): os.unlink(p)
    else:
        json.dump({"level": level, "ts": 1}, open(p, "w"))


check("no registry: everyone reads as nada", sharing.sharing_level("anyone", root)["level"] == "nada")
check("no registry: a stack is skipped", sharing.review_flags("somebot", root) == "SKIP")
json.dump({"people": {
    "op": {"operator": True, "stacks": ["hernik", "disenador"], "places": ["hernik"]},
    "ana": {"tester_since": "2026-11-20", "stacks": ["ana1", "ana2"]},
    "bob": {"stacks": ["bob"]},
    "cat": {"tester_since": "2026-11-21", "places": ["cat"]},
    "dan": {"tester_since": "not-a-date", "stacks": ["dan"]},
}}, open(f"{root}/ops/testers.json", "w"))
for s in ("hernik", "disenador", "ana1", "ana2", "bob", "dan"):
    choose(s, None)

check("the main stack's workdir is user1-workdir", sharing.stack_workdir("hernik", root).endswith("/user1-workdir"))
check("no choice file reads as uso", sharing.sharing_level("bob", root)["level"] == "uso")
check("operator's stack: --own", sharing.review_flags("disenador", root) == "--own")
check("tester's stack: --tester-since with their date", sharing.review_flags("ana2", root) == "--tester-since 2026-11-20")
check("person who is neither: their own level decides (no flag)", sharing.review_flags("bob", root) == "")
check("unknown stack: skipped", sharing.review_flags("stranger", root) == "SKIP")
check("a malformed tester date is not a tester", sharing.review_flags("dan", root) == "")
check("a place-only person cannot choose yet: nada, even as a tester", sharing.sharing_level("cat", root)["level"] == "nada")

choose("ana1", "nada")
check("nada in one of a person's stacks is nada for the person", sharing.sharing_level("ana", root)["level"] == "nada")
check("...and skips their other stack too, tester or not", sharing.review_flags("ana2", root) == "SKIP")
choose("ana1", "todo"); choose("ana2", "uso")
check("the most careful of two choices wins (todo + uso = uso)", sharing.sharing_level("ana", root)["level"] == "uso")
choose("hernik", "nada")
check("nada wins over the operator's own flag", sharing.review_flags("hernik", root) == "SKIP")
choose("bob", "bogus")
check("an unknown stored value reads as uso", sharing.sharing_level("bob", root)["level"] == "uso")
open(f"{root}/ops/testers.json", "w").write("{broken")
check("a broken registry: everyone reads as nada", sharing.review_flags("ana2", root) == "SKIP")

r = subprocess.run([sys.executable, "-I", f"{HERE}/sharing.py", "review-flags", "x"], capture_output=True, text=True,
                   env={**os.environ, "AIBRIDGE_ROOT": root})
check("CLI review-flags prints SKIP for an unknown stack", r.returncode == 0 and r.stdout.strip() == "SKIP")
r = subprocess.run([sys.executable, "-I", f"{HERE}/sharing.py", "bogus"], capture_output=True, text=True,
                   env={**os.environ, "AIBRIDGE_ROOT": root})
check("CLI: an unknown verb prints the usage and exits 2", r.returncode == 2 and "review-flags" in r.stderr)

print("\n".join(fails) or "sharing_selftest: all ok")
sys.exit(1 if fails else 0)
