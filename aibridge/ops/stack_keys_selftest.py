#!/usr/bin/env python3
"""Offline test of ops/stack_keys.py: no Docker, no network. Run: python3 ops/stack_keys_selftest.py"""
import contextlib
import types
import tempfile
import os
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stack_keys as sk  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


class R:
    def __init__(self, out="", rc=0):
        self.stdout, self.returncode = out, rc


GEM = "AIza" + "x" * 35
GROQ = "gsk_" + "y" * 40
OR = "sk-or-v1-" + "z" * 40


def go(args, key, awake=True, answer=None, wake_ok=True):
    calls = []
    out, err = io.StringIO(), io.StringIO()

    def fake_run(cmd, **k):
        calls.append((cmd, k.get("input")))
        return R(json.dumps(answer or {"ok": True, "msg": "Clave válida y guardada (…xxxx)."}) + "\n")

    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = sk.main(args, stdin=io.StringIO(key + "\n"), run=fake_run, running=lambda n: awake, wake=lambda n: wake_ok, hold=lambda n: contextlib.nullcontext())
    return rc, out.getvalue() + err.getvalue(), calls


rc, out, calls = go(["hx", "gemini"], GEM)
check("gemini: ok, key only on stdin (never in argv), activate on by default",
      rc == 0 and calls and GEM not in " ".join(calls[0][0]) and calls[0][1] == GEM + "\n" and calls[0][0][-4:] == ["llm", "gemini", "1", ""], (rc, out, calls))
rc, out, calls = go(["hx", "openrouter", "--no-activate"], OR)
check("openrouter with --no-activate passes 0", rc == 0 and calls[0][0][-2] == "0", (rc, out))
rc, out, calls = go(["hx", "gemini", "--model", "gemini-flash-lite-latest"], GEM)
check("--model is passed to the container (and the key still is not in argv)",
      rc == 0 and calls[0][0][-1] == "gemini-flash-lite-latest" and GEM not in " ".join(calls[0][0]), (rc, out, calls))
rc, out, calls = go(["hx", "gemini", "--model"], GEM)
check("--model without a value is refused", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "groq", "--model", "x-model"], GROQ)
check("--model on a service key (groq) is refused", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "gemini", "--model", "bad model;rm"], GEM)
check("a model id with odd characters is refused", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "groq"], GROQ)
check("groq goes the service way", rc == 0 and calls[0][0][-4] == "service" and calls[0][0][-3] == "groq", (rc, out, calls))
rc, out, calls = go(["hx", "gemini"], "AQ." + "w" * 40)
check("a new-format Gemini key (AQ.) is accepted", rc == 0 and calls, (rc, out))
rc, out, calls = go(["hx", "gemini"], "not a key at all")
check("a wrong shape is refused before anything runs", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "gemini"], GROQ)
check("a groq key given as gemini is refused", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "gemini"], GEM, awake=False)
check("an asleep stack is started, the user is told, and the key is then stored", rc == 0 and calls and "asleep: starting it" in out, (rc, out))
rc, out, calls = go(["hx", "gemini"], GEM, awake=False, wake_ok=False)
check("if the stack cannot be started nothing is sent", rc == 3 and not calls and "nothing was stored" in out, (rc, out))
rc, out, calls = go(["hx", "mapbox"], GEM)
check("an unknown type is refused", rc == 2 and not calls, out)
rc, out, calls = go(["hx", "gemini"], GEM, answer={"ok": False, "msg": "Google Gemini rechazó la clave (HTTP 400) " + GEM})
check("a refusal exits 1 and the key is scrubbed from the text", rc == 1 and GEM not in out and "FAIL" in out, out)
rc, out, calls = go(["hx", "gemini", "--bogus"], GEM)
check("an unknown flag is refused", rc == 2, out)
# a container stopped under the run (rc 137, what the waker's docker stop did to herkos): the failure says what to do, and still no key
err = io.StringIO()
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
    rc = sk.main(["hx", "gemini"], stdin=io.StringIO(GEM + "\n"), run=lambda cmd, **k: types.SimpleNamespace(returncode=137, stdout="", stderr=""),
                 running=lambda n: True, wake=lambda n: True, hold=lambda n: contextlib.nullcontext())
check("rc 137 says the container was stopped and what to do, without the key", rc == 1 and "rc 137" in err.getvalue() and "run it again" in err.getvalue() and GEM not in err.getvalue(), err.getvalue())
# the busy marker that keeps the waker from stopping the stack while the key is being stored
d = tempfile.mkdtemp()
os.makedirs(f"{d}/stacks/hx/workdir/jobfinder/data")
cwd = os.getcwd()
os.chdir(d)
marker = "stacks/hx/workdir/jobfinder/data/.jobpush-running"
with sk.hold_awake("hx"):
    check("the busy marker exists while the key is being stored", os.path.exists(marker))
check("...and is removed afterwards", not os.path.exists(marker))
open(marker, "w").close()
with sk.hold_awake("hx"):
    pass
check("a marker that was already there (a real job's) is left alone", os.path.exists(marker))
os.remove(marker)
try:
    with sk.hold_awake("hx"):
        raise RuntimeError("boom")
except RuntimeError:
    pass
check("the marker is removed even when the load fails", not os.path.exists(marker))
err = io.StringIO()
with contextlib.redirect_stderr(err), sk.hold_awake("nofolder"):
    pass
check("a stack with no workdir at all only gets a note", "note:" in err.getvalue())
# a stack without the jobfinder module (herkos): the folders are made for the run and taken away again
os.makedirs("stacks/nojf/workdir")
err = io.StringIO()
with contextlib.redirect_stderr(err), sk.hold_awake("nojf"):
    check("a stack without jobfinder gets the marker while the key is stored", os.path.exists("stacks/nojf/workdir/jobfinder/data/.jobpush-running"))
check("...and no note", "note:" not in err.getvalue())
check("...and the folders it made are gone afterwards", not os.path.exists("stacks/nojf/workdir/jobfinder") and os.path.isdir("stacks/nojf/workdir"))
try:
    with sk.hold_awake("nojf"):
        raise RuntimeError("boom")
except RuntimeError:
    pass
check("the folders are removed even when the load fails", not os.path.exists("stacks/nojf/workdir/jobfinder"))
os.makedirs("stacks/halfjf/workdir/jobfinder")
open("stacks/halfjf/workdir/jobfinder/keep.txt", "w").close()
with sk.hold_awake("halfjf"):
    pass
check("a jobfinder folder that was already there keeps its files and only the made data folder goes",
      os.path.exists("stacks/halfjf/workdir/jobfinder/keep.txt") and not os.path.exists("stacks/halfjf/workdir/jobfinder/data"))
os.makedirs("stacks/fulljf/workdir/jobfinder/data")
with sk.hold_awake("fulljf"):
    pass
check("existing folders are left in place", os.path.isdir("stacks/fulljf/workdir/jobfinder/data"))
os.chdir(cwd)
print("\nall passed" if not fails else f"\n{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
