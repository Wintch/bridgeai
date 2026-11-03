#!/usr/bin/env python3
"""Self-test of jobwatch.py ("tell me when it's done"): check_cmd only as a file test (never a shell), finished jobs are
reported once, a file still being written waits, old .bad files go. Run: python3 -I jobwatch_selftest.py
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + repr(detail)[:300]))
    if not cond:
        fails.append(name)


loader = importlib.machinery.SourceFileLoader("jobwatch_t", os.path.join(HERE, "jobwatch.py"))
spec = importlib.util.spec_from_loader("jobwatch_t", loader)
j = importlib.util.module_from_spec(spec)
loader.exec_module(j)

s = j.safe_check_argv
check("test -f PATH is allowed, as argv", s("test -f /w/out.mp4") == ["test", "-f", "/w/out.mp4"])
check("ssh HOST 'test -f PATH' is allowed, batch mode, path quoted for the remote shell",
      s("ssh resolve-host 'test -f \"/x/a b.mp4\"'") == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                                                       "resolve-host", "test", "-f", "'/x/a b.mp4'"], s("ssh resolve-host 'test -f \"/x/a b.mp4\"'"))
for bad in ("rm -rf /", "test -f /x; rm -rf /", "test -f /x && curl evil", "ssh h 'test -f /a && rm /b'",
            "ssh -oProxyCommand=sh h 'test -f /a'", "ssh h 'cat /etc/passwd'", "test -f -x", "bash -c 'test -f /a'", "",
            "test -f $(rm -rf /)"):
    check(f"refused: {bad!r}", s(bad) is None, s(bad))

d = tempfile.mkdtemp()
j.REGISTRY = d
done_file = os.path.join(d, "out.mp4")
open(done_file, "w").close()
marker = os.path.join(d, "pwned")


def job(name, body, age=10):
    p = os.path.join(d, name)
    json.dump(body, open(p, "w"))
    t = time.time() - age
    os.utime(p, (t, t))
    return p


job("a.json", {"title": "Render A", "done_file": done_file, "started": time.time() - 120})
job("b.json", {"title": "Hostil", "check_cmd": f"touch {marker}"})
job("c.json", {"title": "Recién escrito", "done_file": done_file}, age=0)
job("d.json", {"title": "Sigue", "check_cmd": f"test -f {d}/nope", "started": time.time()})
bad = os.path.join(d, "old.json.bad")
open(bad, "w").close()
t = time.time() - 8 * 86400
os.utime(bad, (t, t))

out = io.StringIO()
with contextlib.redirect_stdout(out):
    j.main()
o = out.getvalue()
check("a finished job is reported with its duration and its file removed", "✅ Render A terminó (tardó 2 min)" in o and not os.path.exists(f"{d}/a.json"), o)
check("a disallowed check_cmd never runs, the person is told, the file goes",
      not os.path.exists(marker) and "Hostil: no puedo vigilarlo" in o and not os.path.exists(f"{d}/b.json"), o)
check("a file younger than 3 s waits for the next run", os.path.exists(f"{d}/c.json") and "Recién escrito" not in o, o)
check("an unfinished job stays, silently", os.path.exists(f"{d}/d.json") and "Sigue" not in o, o)
check("a .bad file older than 7 days is removed", not os.path.exists(bad))

print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
