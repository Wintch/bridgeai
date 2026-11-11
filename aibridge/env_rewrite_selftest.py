#!/usr/bin/env python3
"""Self-test of the .env writers: gateway.py env_rewrite (gateway servicios guardar/quitar) and keys_server.py
_dotenv_write (the keys page). Both keep every other line, comments included, and never rewrite a file they could not
read. Run: python3 -I env_rewrite_selftest.py
"""
import importlib.machinery
import importlib.util
import os
import stat
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + repr(detail)))
    if not cond:
        fails.append(name)


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


gw = load("gateway_t", os.path.join(HERE, "gateway.py"))
ks = load("keys_server_t", os.path.join(HERE, "keys_server.py"))
writers = {"gateway": lambda p, u: gw.env_rewrite(p, u), "keys_server": lambda p, u: ks._dotenv_write(p, u)}
START = "# keys for this person\nGROQ_API_KEY=keep1\n\nTMDB_API_KEY=old\nOTHER=x=y\n"

for who, write in writers.items():
    d = tempfile.mkdtemp()
    p = os.path.join(d, ".env")
    open(p, "w").write(START)
    write(p, {"TMDB_API_KEY": "new"})
    txt = open(p).read()
    check(f"{who}: a value is replaced in place", txt == START.replace("TMDB_API_KEY=old", "TMDB_API_KEY=new"), txt)
    check(f"{who}: the file is mode 600", stat.S_IMODE(os.stat(p).st_mode) == 0o600)
    write(p, {"CARTO_API_KEY": "c1", "TMDB_API_KEY": None})
    txt = open(p).read()
    check(f"{who}: comments, blank lines and values with '=' stay; removal and addition work",
          txt == "# keys for this person\nGROQ_API_KEY=keep1\n\nOTHER=x=y\nCARTO_API_KEY=c1\n", txt)
    open(p, "a").write("CARTO_API_KEY=dup\n")
    write(p, {"CARTO_API_KEY": "c2"})
    check(f"{who}: a duplicated variable ends as one line", open(p).read().count("CARTO_API_KEY=") == 1, open(p).read())
    q = os.path.join(d, "new.env")
    write(q, {"A": "1"})
    check(f"{who}: a missing file is created", open(q).read() == "A=1\n")
    if os.geteuid() != 0:   # root reads a 000 file anyway
        before = open(p).read()
        os.chmod(p, 0)
        try:
            write(p, {"X": "1"})
            raised = False
        except OSError:
            raised = True
        os.chmod(p, 0o600)
        check(f"{who}: a file that cannot be read raises and is left as it was", raised and open(p).read() == before)
    check(f"{who}: no temporary file is left", not [f for f in os.listdir(d) if f.endswith(".tmp")], os.listdir(d))

# both writers at once on one file: every variable lands (they share PATH.lock)
d = tempfile.mkdtemp()
p = os.path.join(d, ".env")
open(p, "w").write(START)
errs = []


def many(who, n):
    try:
        for i in range(40):
            writers[who](p, {f"{who.upper()}_{n}_{i}": str(i)})
    except Exception as e:  # noqa: BLE001
        errs.append(repr(e))


ts = [threading.Thread(target=many, args=(w, n)) for w in writers for n in range(3)]
[t.start() for t in ts]
[t.join() for t in ts]
txt = open(p).read()
check("gateway and keys page writing at once: no error and no lost variable",
      not errs and all(f"{w.upper()}_{n}_{i}={i}" in txt for w in writers for n in range(3) for i in range(40))
      and "GROQ_API_KEY=keep1" in txt, errs[:1])

print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
