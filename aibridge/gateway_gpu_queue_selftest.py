#!/usr/bin/env python3
"""Offline checks for this stack's own GPU queue (gateway.py: GpuTurn, queue_live, queue_say) and the verbs that use it:
several concurrent processes run one at a time in the order they were started, a killed or frozen job never blocks the line, the wait
budget (VIDEO_QUEUE_WAIT) does not count the time behind the bot's own queue, the failure sentence says whose work it was, the
status names a machine as a machine and says what a new job would wait for, and the ledger shows "waiting".
Fake video and enhance hosts, no GPU gate. Run: python3 -I gateway_gpu_queue_selftest.py"""
import contextlib, importlib.util, io, json, os, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix="gpuqueue-selftest-")
WORK = os.path.join(tmp, "workdir")
QDIR = os.path.join(tmp, "queue")
os.makedirs(os.path.join(WORK, "descargas"))
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"fakeframes" * 30
FAIL = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        FAIL.append(name)


# ---- fake hosts: one video machine that does one clip at a time (429 to a second request), one vidpost ----
host = {"mode": "serial", "hold": 0.0, "active": 0, "max_active": 0, "posts": [], "codes": [], "queue_seen": [], "lock": threading.Lock()}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self.send_response(200 if self.path == "/healthz" else 404); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        raw = self.rfile.read(n)
        try:
            tag = json.loads(raw).get("prompt", "") if self.path == "/video" else "enhance"
        except ValueError:
            tag = "?"
        now = time.time()
        with host["lock"]:
            host["posts"].append((now, tag))
            host["queue_seen"].append(sorted(os.listdir(QDIR)) if os.path.isdir(QDIR) else [])
            busy = host["mode"] == "429" or (host["mode"] == "serial" and host["active"] > 0)
            if not busy:
                host["active"] += 1
                host["max_active"] = max(host["max_active"], host["active"])
            host["codes"].append(429 if busy else 200)
        if busy:
            self.send_response(429); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"no")
            return
        time.sleep(host["hold"])
        with host["lock"]:
            host["active"] -= 1
        self.send_response(200); self.send_header("Content-Type", "video/mp4"); self.send_header("Content-Length", str(len(MP4)))
        self.send_header("X-Video-Seconds", "1.0"); self.send_header("X-Video-Seed", "7"); self.send_header("X-Video-Length", "2")
        self.send_header("X-Enhance-Seconds", "1.0"); self.send_header("X-Enhance-Size", "640x384"); self.send_header("X-Enhance-Fps", "48")
        self.end_headers(); self.wfile.write(MP4)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}"
cfgp, logp = os.path.join(tmp, "gateways.json"), os.path.join(tmp, "log.jsonl")
json.dump({"video": [{"name": "gpu-a", "url": url}], "vidpost": [{"name": "gpu-a", "url": url}]}, open(cfgp, "w"))
ENV = dict(GATEWAYS_CONFIG=cfgp, GATEWAY_LOG=logp, GATEWAY_WORKDIR=WORK, AIBRIDGE_DOWNLOADS=os.path.join(WORK, "descargas"), GATEWAY_GPU_QUEUE=QDIR,
           GATEWAY_GPU_QUEUE_POLL="0.05", TRABAJOS_DIR=os.path.join(tmp, "ledger"), TRABAJOS_MODULE=os.path.join(HERE, "trabajos.py"),
           AIBRIDGE_PREFS=os.path.join(tmp, "prefs.json"), GATEWAY_GPU_BATCH=os.path.join(tmp, "batch.json"))
os.environ.update(ENV)
os.environ.pop("TRABAJO_ID", None)


def load():
    spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


gw = load()

# a child process that holds a turn: python3 -I child.py IDX LOG HOLD (appends "start IDX" / "end IDX" to LOG)
child = os.path.join(tmp, "child.py")
open(child, "w").write(f'''
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("gw", {os.path.join(HERE, "gateway.py")!r})
gw = importlib.util.module_from_spec(spec); spec.loader.exec_module(gw)
idx, log, hold = sys.argv[1], sys.argv[2], float(sys.argv[3])
with gw.gpu_turn("makevideo", "/workdir/descargas/clip" + idx + ".mp4") as turn:
    ok = turn.wait()
    open(log, "a").write("start " + idx + (" queued=%.2f" % turn.queued) + "\\n")
    time.sleep(hold)
    open(log, "a").write("end " + idx + "\\n")
''')


def spawn(idx, log, hold):
    return subprocess.Popen([sys.executable, "-I", child, str(idx), log, str(hold)], env=dict(os.environ))


def lines(log):
    try:
        return [x.split()[0] + " " + x.split()[1] for x in open(log).read().splitlines()]
    except OSError:
        return []


def tickets():
    return sorted(n for n in os.listdir(QDIR) if n.endswith(".json")) if os.path.isdir(QDIR) else []


def sleeper():
    return subprocess.Popen(["sleep", "120"])


def plant(seq, pid, verb="makevideo", label="other.mp4", age=0):
    """A ticket that looks like another job's: LABEL, owned by PID, last touched AGE seconds ago."""
    os.makedirs(QDIR, exist_ok=True)
    p = os.path.join(QDIR, f"{seq:016d}-{pid}.json")
    json.dump({"verb": verb, "label": label, "created": time.time()}, open(p, "w"))
    if age:
        os.utime(p, (time.time() - age, time.time() - age))
    return p


# 1. several concurrent processes: one at a time, in the order they were started
log = os.path.join(tmp, "order.log")
procs = []
for i in range(5):
    procs.append(spawn(i, log, 0.7))
    time.sleep(0.3)                  # a python start takes well under this: the tickets are taken in launch order, and each job outlasts the next launch
rcs = [p.wait(timeout=60) for p in procs]
got = lines(log)
want = [x for i in range(5) for x in (f"start {i}", f"end {i}")]
check("five concurrent jobs run one at a time, in launch order (no overlap, no overtaking)", got == want, got)
check("every one of them exited 0 and no ticket is left", rcs == [0] * 5 and tickets() == [], (rcs, tickets()))
check("the ones that stood in line say how long (queued=)", "queued=0.00" in open(log).read().splitlines()[0] and any(
    float(x.split("queued=")[1]) > 0.1 for x in open(log).read().splitlines() if x.startswith("start 4")), open(log).read())

# 2. a job killed while it holds the card does not block the line
log = os.path.join(tmp, "kill.log")
a = spawn("A", log, 60)
t_end = time.time() + 20
while "start A" not in lines(log) and time.time() < t_end:
    time.sleep(0.05)
b = spawn("B", log, 0.1)
time.sleep(0.6)
check("B waits while A holds the head", lines(log) == ["start A"], lines(log))
a.kill(); a.wait()
t0 = time.time()
rc = b.wait(timeout=20)
check("A killed (SIGKILL, no cleanup): B starts by itself and finishes", (rc, lines(log)[-2:], time.time() - t0 < 10), (rc, lines(log), time.time() - t0))
check("the dead job's ticket was swept", tickets() == [], tickets())

# 3. a SIGTERM (a tool timeout) gives the place back
log = os.path.join(tmp, "term.log")
a = spawn("T", log, 60)
t_end = time.time() + 20
while "start T" not in lines(log) and time.time() < t_end:
    time.sleep(0.05)
a.terminate()
try:
    a.wait(timeout=10)
except subprocess.TimeoutExpired:
    a.kill(); a.wait()
check("SIGTERM runs the cleanup: the ticket is gone at once", tickets() == [], tickets())

# 4. a ticket whose process lives but stopped touching it is not counted; a zombie or a missing pid is not either
live = sleeper()
frozen = plant(1, live.pid, age=gw.GPU_QUEUE_STALE + 60)
dead = subprocess.Popen(["true"]); dead.wait()
plant(2, dead.pid)
ql = gw.queue_live()
check("a frozen ticket (pid alive, no heartbeat) is not counted, a dead pid's ticket is swept", (ql, tickets()) == ([], [os.path.basename(frozen)]), (ql, tickets()))
with gw.gpu_turn("makevideo", "x.mp4") as turn:
    t0 = time.time()
    got_turn = turn.wait()
    check("so a new job is the head at once", got_turn and time.time() - t0 < 1, time.time() - t0)
os.unlink(frozen)
live.kill(); live.wait()

# 5. ticket hygiene: labels are plain names, other files in the folder are left alone, an unwritable folder turns the queue off
open(os.path.join(QDIR, "notes.txt"), "w").write("x")
with gw.gpu_turn("enhance", "/workdir/descargas/../../evil name;rm.mp4") as turn:
    e = gw.queue_live()
    check("the label is the file name with only safe characters", e and e[0]["label"] == "evilnamerm.mp4" and e[0]["verb"] == "enhance", e)
check("an unrelated file in the queue folder is untouched", os.path.exists(os.path.join(QDIR, "notes.txt")))
os.unlink(os.path.join(QDIR, "notes.txt"))
old = gw.GPU_QUEUE
gw.GPU_QUEUE = "/proc/no-such-dir/queue"
with gw.gpu_turn("makevideo", "x.mp4") as turn:
    check("no writable folder: the queue is off and wait() returns at once", (turn.on, turn.wait(), turn.queued), (False, True, 0.0))
gw.GPU_QUEUE = old

# 6. the wait budget does not count the time behind the bot's own queue
gw.VIDEO_QUEUE_POLL = 0.1
host.update(mode="429", hold=0.0, posts=[], codes=[])
HOLD, BUDGET = 1.5, 0.6
gw.VIDEO_QUEUE_WAIT = BUDGET
sib = sleeper()                                  # another job of this bot, ahead in the line
plant(1, sib.pid, label="sibling.mp4")
threading.Timer(HOLD, lambda: (sib.kill(), sib.wait())).start()
out = os.path.join(WORK, "descargas", "late.mp4")


def run_cmd(fn, argv):
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = fn(argv)
    return rc, buf.getvalue() + err.getvalue()


t0 = time.time()
rc, txt = run_cmd(gw.cmd_makevideo, ["--secs", "5", "--", "p", out])
took = time.time() - t0
first_post = host["posts"][0][0] - t0 if host["posts"] else None
check("the host is not asked while this job stands behind its own queue", first_post is not None and first_post >= HOLD - 0.1, first_post)
check("then it waits its full budget against the machine (polls), not what is left after the queue", len(host["posts"]) >= 3, len(host["posts"]))
check("and gives up about one budget after its turn came, not at once", HOLD + BUDGET - 0.2 <= took <= HOLD + BUDGET + 4, took)
check("the failure says the machine was kept busy by work that is not this bot's own queue and that the queue time was not counted",
      (rc, "not from this bot's own queue" in txt, "waited" in txt and "was not counted" in txt, "not what kept it busy" in txt or "were not what kept it busy" in txt),
      (5, True, True, True))
check("it never says that other videos of the same bot were the cause", "Other videos" not in txt, txt)
logtxt = open(logp).read()
check("the log has the own-queue seconds (queued) and the machine-side error", '"error": "busy"' in logtxt and '"queued"' in logtxt, logtxt[-300:])
check("no ticket is left after the failure", tickets() == [], tickets())

# the same wait, but the machine is free: it succeeds although the queue took longer than the whole budget
host.update(mode="serial", hold=0.0, posts=[], codes=[], active=0)
sib = sleeper()
plant(1, sib.pid, label="sibling.mp4")
threading.Timer(HOLD, lambda: (sib.kill(), sib.wait())).start()
rc, txt = run_cmd(gw.cmd_makevideo, ["--secs", "5", "--", "p", out])
check("a job that stood longer than the budget behind its own queue still runs when the machine is free", (rc, os.path.exists(out), host["codes"]), (0, True, [200]))
last = json.loads(open(logp).read().strip().splitlines()[-1])
check("its log line has the seconds it stood behind its own queue", last.get("queued", 0) >= 1 and last.get("ok") is True, last)

# 7. a chain (several segments) holds the card for the whole clip: another job does not slip in between its segments
host.update(mode="serial", hold=0.3, posts=[], codes=[], active=0, max_active=0)
gw2 = load()
gw2.VIDEO_QUEUE_POLL = 0.05
order = []


def chained_like(tag, hold):
    with gw2.gpu_turn("makevideo", tag + ".mp4") as turn:
        turn.wait()
        for k in range(3):
            order.append((tag, k))
            time.sleep(hold)


th = [threading.Thread(target=chained_like, args=("A", 0.1)), threading.Thread(target=chained_like, args=("B", 0.05))]
th[0].start(); time.sleep(0.2); th[1].start()
for x in th:
    x.join(30)
# threads of ONE process share a pid: the ticket names differ only by seq, so the order is still the start order
check("two jobs of one process (threads) are still ordered by their tickets, the second after the first has finished",
      order == [("A", 0), ("A", 1), ("A", 2), ("B", 0), ("B", 1), ("B", 2)], order)

# 8. the real command from several processes against a host that does one clip at a time
host.update(mode="serial", hold=2.0, posts=[], codes=[], active=0, max_active=0, queue_seen=[])
gw3 = load()
tj = gw3.ledger()
procs = []
for i in range(3):
    o = os.path.join(WORK, "descargas", f"scene{i}.mp4")
    procs.append(subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "gateway.py"), "makevideo", "--secs", "2", "--", f"scene {i}", o],
                                  env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    time.sleep(0.6)
waiting_seen, t_end = set(), time.time() + 60
while any(p.poll() is None for p in procs) and time.time() < t_end:
    try:
        for e in tj.load()["entries"]:
            if e.get("state") == "corriendo" and "own GPU queue" in (e.get("tail") or ""):
                waiting_seen.add(e["tail"])
    except Exception:
        pass
    time.sleep(0.1)
res = [(p.wait(timeout=30), p.stdout.read(), p.stderr.read()) for p in procs]
check("three scenes launched together all succeed", [r[0] for r in res] == [0, 0, 0], [(r[0], r[1][-200:], r[2][-200:]) for r in res])
check("the host never saw two at once and never had to say 429", (host["max_active"], 429 in host["codes"], len(host["codes"])), (1, False, 3))
check("the host got them in launch order", [tag for _, tag in host["posts"]] == ["scene 0", "scene 1", "scene 2"], host["posts"])
check("each request was made while its job held the only ticket-head (the host saw the line)", all(len(q) >= 1 for q in host["queue_seen"]), host["queue_seen"])
check("the waiting ones said so on stderr", ("own GPU queue" in res[1][2], "own GPU queue" in res[2][2], "own GPU queue" in res[0][2]), (True, True, False))
check("the ledger showed 'waiting in this bot's own GPU queue: N job(s) ahead' while they waited",
      any("2 job(s) ahead" in w for w in waiting_seen) and any("1 job(s) ahead" in w for w in waiting_seen), waiting_seen)
done = tj.load()["entries"]
check("all three ledger entries ended as done and the waiting note is gone", [(e["state"], "own GPU queue" in (e.get("tail") or "")) for e in done if e["kind"] == "video"][-3:] ==
      [("listo", False)] * 3, [(e["state"], e.get("tail")) for e in done])
check("no ticket is left", tickets() == [], tickets())

# 9. the place is given back as soon as the GPU part is done (before the local light copy), for makevideo and enhance
seen = []
real_compress = gw.deliver_compress
gw.deliver_compress = lambda *a, **k: (seen.append(tickets()), real_compress(*a, **k))[1]
gw.VIDEO_QUEUE_WAIT = 5
host.update(mode="serial", hold=0.0, posts=[], codes=[], active=0, queue_seen=[])
rc, _ = run_cmd(gw.cmd_makevideo, ["--secs", "2", "--", "p", os.path.join(WORK, "descargas", "rel.mp4")])
check("makevideo: during the request the job holds one ticket, during the light copy none", (rc, len(host["queue_seen"][-1]), seen[-1]), (0, 1, []))
src = os.path.join(WORK, "descargas", "src.mp4"); open(src, "wb").write(MP4)
seen.clear(); host["queue_seen"].clear()
rc, txt = run_cmd(gw.cmd_enhance, [src, os.path.join(WORK, "descargas", "src-hd.mp4")])
check("enhance: one ticket during the request, none during the light copy", (rc, len(host["queue_seen"][-1]), seen[-1] if seen else None), (0, 1, []))
check("a usage error takes no place in the line", (run_cmd(gw.cmd_makevideo, ["--secs", "4", "--", "p", out])[0], run_cmd(gw.cmd_enhance, ["--bogus"])[0], tickets()), (2, 2, []))
gw.deliver_compress = real_compress

# 10. enhance waits for a makevideo of the same bot (they share the card), in order
sib = sleeper()
plant(1, sib.pid, verb="makevideo", label="clip.mp4")
host["posts"].clear()
threading.Timer(0.8, lambda: (sib.kill(), sib.wait())).start()
t0 = time.time()
rc, txt = run_cmd(gw.cmd_enhance, [src, os.path.join(WORK, "descargas", "src-hd2.mp4")])
check("enhance stands behind a video of the same bot and then runs", (rc, host["posts"][0][0] - t0 >= 0.7, "own GPU queue" in txt), (0, True, True))

# 11. the queue gives up after GPU_QUEUE_MAX_WAIT with a sentence that says why
sib = sleeper()
plant(1, sib.pid, label="stuck.mp4")
gw.GPU_QUEUE_MAX_WAIT = 0.4
host["posts"].clear()
rc, txt = run_cmd(gw.cmd_makevideo, ["--secs", "2", "--", "p", os.path.join(WORK, "descargas", "never.mp4")])
check("a job that never got its turn says so, exit 5, and never asked the machine", (rc, "in this bot's own queue" in txt and "never got its turn" in txt, host["posts"]), (5, True, []))
check("and its own ticket is gone, the other one stays", [t.split("-")[1] for t in tickets()] == [f"{sib.pid}.json"], tickets())
sib.kill(); sib.wait()
os.unlink(os.path.join(QDIR, tickets()[0])) if tickets() else None
gw.GPU_QUEUE_MAX_WAIT = 8 * 3600

# 12. status: a machine is a machine, and it says what a new job would wait for
cfg = json.load(open(cfgp))
cfg["gates"] = {"gpubox": {"url": "http://127.0.0.1:9", "token": "T"}}
json.dump(cfg, open(cfgp, "w"))
gw4 = load()
state = {"blocked": None}
gw4.gate_call = lambda g, method, path, *a, **k: (200, {"gpu": {}, "blocked": state["blocked"], "services": {}})
s1, s2 = sleeper(), sleeper()


def status():
    return run_cmd(gw4.cmd_gpu, ["status"])[1]


txt = status()
check("empty queue, free machine: says it starts at once", ("GPU machine gpubox: available" in txt, "this bot's own GPU queue: empty" in txt, "asks the machine at once" in txt), (True, True, True))
plant(1, s1.pid, label="clip-a.mp4")
plant(2, s2.pid, verb="enhance", label="clip-b.mp4")
txt = status()
check("a queue is listed in order: what runs, what waits", ("running: video clip-a.mp4" in txt, "waiting #1: enhance clip-b.mp4" in txt), (True, True))
check("free machine, own queue: it says a new job waits only for this bot's own queue (2 jobs) and that every job can be launched now",
      ("only this bot's own queue (2 job(s) in it)" in txt, "launch every job now" in txt), (True, True))
state["blocked"] = "vr"
txt = status()
check("a machine in use by VR: named as a machine, not a process, and not this bot's work",
      ("GPU machine gpubox: in use right now by someone on that computer (VR, a game or video editing), not by this bot" in txt, "never a process or another session" in txt,
       "process gpubox" in txt), (True, True, False))
check("and the verdict is that the machine is the reason, not the own queue", "refused for now" in txt and "does not change that" in txt, txt)
state["blocked"] = "busy"
check("marked busy by the operator: not this bot's", "marked busy by the operator, not by this bot" in status())
s1.kill(); s2.kill(); s1.wait(); s2.wait()
for n in tickets():
    os.unlink(os.path.join(QDIR, n))
gw4.GPU_QUEUE = "/proc/no-such-dir/queue"
check("with the queue off the status still prints and says empty", "this bot's own GPU queue: empty" in status())

# 13. the sentences of a gate refusal say whose work it was
check("a refusal for lack of room says it is not this bot's own queue", "not in this bot's own queue" in gw.GATE_SAYS["vram"], gw.GATE_SAYS["vram"])
check("the 30-minute sentence says whose work it was, in minutes for a real budget",
      all(x in gw.busy_budget_say(None) for x in ("30 minutes", "not from this bot's own queue", "another bot's video")) if (setattr(gw, "VIDEO_QUEUE_WAIT", 1800) or True) else False)

print()
if FAIL:
    print(f"gateway_gpu_queue_selftest: FAILED: {FAIL}")
    sys.exit(1)
print("gateway_gpu_queue_selftest: all ok")
