#!/usr/bin/env python3
"""Selftest for ocio.py: the idle-time queue. Units are claimed oldest first and one at a time, a unit that was claimed and never finished goes back and is
blocked after three tries, finishing and blocking keep a short result, text is cleaned and cut, 'nuevos' lists what the person has not been told once, two
processes never take the same unit, and nothing but counts reaches the log.

Run from anywhere:  python3 -I ocio_selftest.py
"""
import importlib.util, json, os, subprocess, sys, tempfile
import atexit as _a, shutil as _s, signal as _g
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_a.register(_s.rmtree, tempfile.tempdir, True)
_g.signal(_g.SIGTERM, lambda *_: sys.exit(143))
HERE = os.path.dirname(os.path.abspath(__file__))
ok = True
def chk(what, got, want=True):
    global ok; good = got == want; ok &= good
    print(("ok   " if good else "FAIL ") + what + ("" if good else f"  got={got!r} want={want!r}"), flush=True)

tmp = tempfile.mkdtemp()
os.environ.update(GATEWAY_WORKDIR=tmp, OCIO_DIR=f"{tmp}/ocio", GATEWAY_LOG=f"{tmp}/log.jsonl")
spec = importlib.util.spec_from_file_location("ocio", os.path.join(HERE, "ocio.py")); o = importlib.util.module_from_spec(spec); spec.loader.exec_module(o)

chk("an empty queue: nothing to claim", o.claim(), None)
a, b, c = o.add("sketch one"), o.add("sketch two", "ten variants, small"), o.add("render test")
chk("units get numbers in order", (a, b, c), (1, 2, 3))
u = o.claim()
chk("the oldest pending unit is claimed first, now running", (u["id"], u["state"], u["tries"]), (1, "en_curso", 1))
chk("the next claim takes the next one, never the running one", o.claim()["id"], 2)
chk("counts", o.counts(), {"pendiente": 1, "en_curso": 2, "hecho": 0, "bloqueado": 0})
o.finish(1, "made 6 sketches", ["a.png", "b.png"])
chk("a finished unit keeps its summary and files", [(i["state"], i["result"], i["files"]) for i in o._load()["items"] if i["id"] == 1], [("hecho", "made 6 sketches", ["a.png", "b.png"])])
o.give_back(2)
chk("give back: a running unit returns to the queue", [i["state"] for i in o._load()["items"] if i["id"] == 2], ["pendiente"])
o.block(3, "needs the GPU")
chk("a blocked unit leaves the queue", (o.counts()["bloqueado"], o.claim()["id"]), (1, 2))
# a unit that was claimed and never finished: stale, goes back, blocked on the third failed try
q = o._load(); i2 = [i for i in q["items"] if i["id"] == 2][0]; i2["claimed"] = 1; i2["tries"] = 1; o._save(q)
chk("a unit claimed long ago and never finished goes back to the queue and is claimed again", (o.claim(now=10 ** 9) or {}).get("id"), 2)
q = o._load(); i2 = [i for i in q["items"] if i["id"] == 2][0]; i2["claimed"] = 1; i2["tries"] = 3; o._save(q)
o.claim(now=10 ** 9)
chk("after three tries it is blocked, not retried forever", [i["state"] for i in o._load()["items"] if i["id"] == 2], ["bloqueado"])
# cleaning and limits
n = o.add("x\x00y\x07z" + "t" * 500, "d" * 5000)
it = [i for i in o._load()["items"] if i["id"] == n][0]
chk("control characters are removed and text is cut", ("\x00" not in it["title"], "\x07" not in it["title"], len(it["title"]), len(it["detail"])), (True, True, 200, 2000))
try:
    o.add("   "); empty = False
except ValueError:
    empty = True
chk("a unit with no title is refused", empty)
# told once
chk("nuevos lists finished and blocked units not told yet", sorted(i["id"] for i in o.untold()), [1, 2, 3])
o.untold(mark=True)
chk("after --visto they are not listed again", o.untold(), [])
o.finish(n, "done again"); chk("a unit finished later is new again", [i["id"] for i in o.untold()], [n])
# the queue cap
for _ in range(o.MAX_ITEMS): 
    try: o.add("filler")
    except ValueError: break
try:
    o.add("one more"); capped = False
except ValueError as e:
    capped = "waiting" in str(e)
chk("the queue refuses more than MAX_ITEMS waiting units", capped)
# two processes, one unit each: no unit goes to both
fresh = tempfile.mkdtemp(); env = dict(os.environ, OCIO_DIR=f"{fresh}/ocio", GATEWAY_LOG=f"{fresh}/l.jsonl", GATEWAY_WORKDIR=fresh)
for k in range(4): subprocess.run([sys.executable, "-I", os.path.join(HERE, "ocio.py"), "agregar", f"u{k}"], env=env, capture_output=True)
procs = [subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "ocio.py"), "siguiente"], env=env, stdout=subprocess.PIPE, text=True) for _ in range(4)]
outs = [p.communicate()[0] for p in procs]
ids = sorted(int(x.split("#")[1].split(":")[0]) for x in outs if x.startswith("Unit #"))
chk("four processes claiming at once get four different units", ids, [1, 2, 3, 4])
# the CLI and the log
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ocio.py"), "agregar", "secret title", "--detalle", "secret detail"], env=env, capture_output=True, text=True)
chk("the CLI queues a unit and tells the number", "Queued as #5" in r.stdout, True)
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ocio.py"), "siguiente"], env=env, capture_output=True, text=True)
chk("the unit text names the folder and how to finish", "gateway ocio hecho 5" in r.stdout and "resultados/5/" in r.stdout, True)
logtxt = open(f"{fresh}/l.jsonl").read()
chk("the log has numbers and counts, never a title or a detail", ("secret" not in logtxt, "agregar" in logtxt), (True, True))
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ocio.py"), "hecho", "abc"], env=env, capture_output=True, text=True)
chk("a bad number is a usage message, not a crash", (r.returncode, "usage" in r.stdout), (2, True))
import stat as _stat
um = tempfile.mkdtemp(); env_um = dict(os.environ, OCIO_DIR=f"{um}/ocio", GATEWAY_LOG=f"{um}/l.jsonl", GATEWAY_WORKDIR=um)
subprocess.run([sys.executable, "-I", os.path.join(HERE, "ocio.py"), "agregar", "x"], env=env_um, capture_output=True, preexec_fn=lambda: os.umask(0o077))
chk("queue.json is 0644 and its folder 0711 under Hermes's umask 077 (the host's waker counts the waiting units)",
    (oct(_stat.S_IMODE(os.stat(f"{um}/ocio/queue.json").st_mode)), oct(_stat.S_IMODE(os.stat(f"{um}/ocio").st_mode))), (oct(0o644), oct(0o711)))
print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
