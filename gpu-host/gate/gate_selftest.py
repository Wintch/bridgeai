#!/usr/bin/env python3
"""Offline test of gpu-host/gate/gate.py and install_gate.sh: fake `docker`, `nvidia-smi`, `sudo`, `systemctl` and `crontab`
executables first in PATH (they keep their state in one JSON file and record every call), fake service HTTP servers, a fake
/proc. Nothing real is touched: no Docker, no GPU, no sudo, no network beyond loopback."""
import fcntl, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
GATE_PY = os.path.join(HERE, "gate.py")
FAIL = []
TOKEN = "t0ken-for-tests"
NAMES = ["upscaler", "transcoder", "stt", "llm", "tts", "tts-hq", "imggen", "vidgen", "vidpost", "mosher"]


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def wait_until(fn, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.1)
    return False


STUB_COMMON = '''#!/usr/bin/env python3
import fcntl, json, os, sys
SP = os.environ["STUB_STATE"]
def update(fn):
    with open(SP + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        st = json.load(open(SP)); r = fn(st)
        json.dump(st, open(SP + ".tmp", "w")); os.replace(SP + ".tmp", SP); return r
'''
STUBS = {
    "docker": '''
import time
_a = sys.argv[1:]
if _a[:1] in (["stop"], ["start"]):
    time.sleep(float(os.environ.get("STUB_" + _a[0].upper() + "_DELAY", "0")))
def run(st):
    a = sys.argv[1:]
    if a[:2] == ["ps", "-a"]:
        print("\\n".join(n + "\\t" + s for n, s in st["containers"].items()) + "\\n" + "other\\trunning"); return 0
    if len(a) == 2 and a[0] in ("start", "stop"):
        st["calls"].append("docker " + a[0] + " " + a[1])
        if a[1] not in st["containers"] or (a[0] == "start" and a[1] in st["start_fail"]): return 1
        st["containers"][a[1]] = "running" if a[0] == "start" else "exited"; return 0
    if a and a[0] in ("create", "run", "rm", "inspect"):
        name = a[a.index("--name") + 1] if "--name" in a else a[-1]
        st["calls"].append("docker " + a[0] + " " + name)
        if a[0] == "inspect": print("false")
        return 0
    st["calls"].append("UNEXPECTED docker " + " ".join(a)); return 2
sys.exit(update(run))
''',
    "sudo": '''
def run(st):
    a = sys.argv[1:]
    if len(a) == 4 and a[:3] == ["-n", "/usr/bin/nvidia-smi", "-pl"] and a[3].isdigit():
        st["calls"].append("sudo " + " ".join(a))
        w = int(a[3])
        if st["sudo_fail"] or not st["min"] <= w <= st["max"]: return 1
        st["limit"] = w; return 0
    st["calls"].append("UNEXPECTED sudo " + " ".join(a)); return 2
sys.exit(update(run))
''',
    "nvidia-smi": '''
st = update(lambda s: s)
if not any(x.startswith("--query-gpu=") for x in sys.argv):
    update(lambda s: s["calls"].append("UNEXPECTED nvidia-smi " + " ".join(sys.argv[1:]))); sys.exit(2)
if st.get("smi_fail"): sys.exit(1)
free = st["free"] - sum(st.get("use", {}).get(n, 0) for n, c in st["containers"].items() if c == "running")
print(", ".join(str(x) for x in (st["gpu"], "%.2f" % st["limit"], "%.2f" % st["default"], "%.2f" % st["min"], "%.2f" % st["max"], free, "%.2f" % st["draw"])))
''',
    "systemctl": '''
update(lambda s: s["calls"].append("systemctl " + " ".join(sys.argv[1:])))
''',
    "crontab": '''
def run(st):
    if sys.argv[1:] == ["-l"]:
        print(st["cron"], end=""); return 0
    if sys.argv[1:] == ["-"]:
        st["cron"] = sys.stdin.read(); return 0
    return 2
sys.exit(update(run))
''',
}


class Env:
    """A temp world: stubs, state file, fake /proc, profile file."""

    def __init__(self):
        self.d = tempfile.mkdtemp(prefix="gate-test-")
        self.bin = os.path.join(self.d, "bin"); os.makedirs(self.bin)
        for n, body in STUBS.items():
            p = os.path.join(self.bin, n)
            open(p, "w").write(STUB_COMMON + body); os.chmod(p, 0o755)
        self.sp = os.path.join(self.d, "stub.json")
        self.proc = os.path.join(self.d, "proc"); os.makedirs(self.proc)
        self.state_dir = os.path.join(self.d, "gate-state")
        self.profiles = os.path.join(self.d, "profiles.conf")
        open(self.profiles, "w").write("[RTX 3060 Ti]\nllm = 130\ntranscoder = 100\nupscaler = 100  # comment\nimggen = 130\nvidpost = 100\n"
                                       "[GTX 1070 Ti]\nllm = 100\n")
        self.reset()

    def reset(self, **over):
        st = {"containers": {n: "exited" for n in NAMES if n != "mosher"}, "calls": [], "limit": 200, "default": 200, "min": 100,
              "max": 200, "free": 7000, "draw": 120.0, "gpu": "NVIDIA GeForce RTX 3060 Ti", "sudo_fail": False, "start_fail": [], "cron": ""}
        st.update(over)
        json.dump(st, open(self.sp, "w"))

    def st(self):
        with open(self.sp + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_SH)
            return json.load(open(self.sp))

    def mod(self, **kw):
        with open(self.sp + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            st = json.load(open(self.sp)); st.update(kw); json.dump(st, open(self.sp, "w"))

    def mod_container(self, name, state):
        with open(self.sp + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            st = json.load(open(self.sp)); st["containers"][name] = state; json.dump(st, open(self.sp, "w"))

    def running(self, name):
        return self.st()["containers"].get(name) == "running"

    def calls(self, prefix=""):
        return [c for c in self.st()["calls"] if c.startswith(prefix)]

    def ledger(self):
        p = os.path.join(self.state_dir, "usage.jsonl")
        return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


class Gate:
    def __init__(self, env, token=TOKEN, extra=None, wait=True):
        self.env = env
        self.port = free_port()
        self.ports = {n: free_port() for n in NAMES}
        e = {k: v for k, v in os.environ.items() if not k.startswith("GATE_") and k != "GPU_BIND_ADDR"}
        e.update(PATH=env.bin + os.pathsep + os.environ.get("PATH", ""), STUB_STATE=env.sp, HOME=env.d, GATE_ENV_FILE=os.path.join(env.d, "none.env"),
                 GATE_PORT=str(self.port), GATE_BIND="127.0.0.1", GATE_STATE_DIR=env.state_dir, GATE_POWER_PROFILES=env.profiles,
                 GATE_PROC_DIR=env.proc, GATE_TICK_S="0.25", GATE_IDLE_S="1.5", GATE_BATCH_TTL_S="7200", GATE_IDLE_VIDPOST="60")
        if token:
            e["GATE_TOKEN"] = token
        for n, p in self.ports.items():
            e["GATE_PORT_" + n.upper().replace("-", "_")] = str(p)
        e.update(extra or {})
        self.log = tempfile.NamedTemporaryFile("w+", delete=False)
        self.p = subprocess.Popen([sys.executable, "-I", GATE_PY], env=e, stdout=self.log, stderr=subprocess.STDOUT)
        if wait:
            for _ in range(60):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{self.port}/healthz", timeout=1); break
                except Exception:
                    time.sleep(0.1)

    def req(self, path, body=None, token=TOKEN, raw=None, method=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=h, method=method or ("POST" if data is not None else "GET"))
        try:
            with urllib.request.urlopen(r, timeout=30) as x:
                return x.status, x.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def j(self, path, body=None, **kw):
        code, text = self.req(path, body, **kw)
        try:
            return code, json.loads(text)
        except ValueError:
            return code, text

    def wake(self, name, stack="stackA", mode="interactive", batch=None, jobs=None):
        b = {"port": self.ports[name], "stack": stack, "mode": mode}
        if mode == "batch":
            b.update(batch=batch, jobs=jobs)
        return self.j("/wake", b)

    def state(self):
        return self.j("/state")[1]

    def logtext(self):
        self.log.flush(); return open(self.log.name).read()

    def stop(self):
        self.p.terminate()
        try:
            self.p.wait(5)
        except subprocess.TimeoutExpired:
            self.p.kill()


class FakeService:
    """A service's /status (the gate reads it to see that a job is running) and /healthz (ready when `healthy`)."""

    def __init__(self, port):
        self.state = "idle"
        self.healthy = True
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = json.dumps({"state": me.state, "queued": 0}).encode()
                self.send_response(503 if self.path == "/healthz" and not me.healthy else 200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        self.srv = ThreadingHTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


def main_scenario():
    env = Env()
    g = Gate(env)
    fakes = {n: FakeService(g.ports[n]) for n in NAMES}
    svc = fakes["imggen"]
    P = g.ports

    # --- basics, auth, validation
    check("healthz needs no token", g.req("/healthz", token=None), (200, "ok gate"))
    check("state without token", g.req("/state", token=None)[0], 401)
    check("state wrong token", g.req("/state", token="nope")[0], 401)
    check("wake wrong token", g.req("/wake", {"port": P["llm"], "stack": "a"}, token="nope")[0], 401)
    s = g.state()
    check("state gpu", s["gpu"], {"name": "NVIDIA GeForce RTX 3060 Ti", "limit_w": 200, "default_w": 200, "min_w": 100, "max_w": 200, "free_mb": 7000})
    check("state blocked none", s["blocked"], None)
    check("state services", sorted(s["services"]), sorted(NAMES))
    check("state service shape", s["services"]["llm"], {"port": P["llm"], "running": False, "leases": 0, "mode": None, "idle_left_s": None})
    check("wake unknown port", g.j("/wake", {"port": 9, "stack": "a"}), (404, {"why": "unknown"}))
    check("wake container missing", g.wake("mosher"), (503, {"why": "not_installed"}))
    check("wake bad json", g.req("/wake", raw=b"{nope")[0], 400)
    check("wake empty body", g.req("/wake", raw=b"")[0], 400)
    check("wake bad mode", g.j("/wake", {"port": P["llm"], "stack": "a", "mode": "x"})[0], 400)
    check("wake batch without id", g.j("/wake", {"port": P["llm"], "stack": "a", "mode": "batch"})[0], 400)
    check("wake bad jobs", g.j("/wake", {"port": P["llm"], "stack": "a", "mode": "batch", "batch": "b", "jobs": -1})[0], 400)
    check("wake bad port type", g.j("/wake", {"port": "8630", "stack": "a"})[0], 400)
    check("wake bad stack", g.j("/wake", {"port": P["llm"], "stack": "a b/../"})[0], 400)
    check("done bad body", g.j("/done", {"lease": 5})[0], 400)
    check("body over 4 KB", g.req("/wake", raw=b'{"stack": "' + b"a" * 5000 + b'"}')[0], 413)
    check("unknown path", g.req("/nope", {"a": 1})[0], 404)
    check("nothing started so far", env.calls("docker start"), [])

    # --- wake, power apply, refresh
    code, w = g.wake("llm")
    check("wake llm 202", (code, w["running"], w["eta_s"]), (202, False, 60))
    lease_llm = w["lease"]
    check("docker start llm", env.calls("docker start"), ["docker start llm"])
    check("power 130 with the fixed argv", env.calls("sudo"), ["sudo -n /usr/bin/nvidia-smi -pl 130"])
    check("limit applied", env.st()["limit"], 130)
    check("done 200", g.j("/done", {"lease": lease_llm}), (200, {"done": 1, "closed": False}))
    code, w2 = g.wake("llm")
    check("wake again 200 same lease", (code, w2), (200, {"lease": lease_llm, "running": True, "eta_s": 0}))
    s = g.state()["services"]["llm"]
    check("state running llm", (s["running"], s["leases"], s["mode"]), (True, 1, "interactive"))
    check("idle_left_s counts down", 0 <= s["idle_left_s"] <= 1, True)
    code, w = g.wake("transcoder")
    check("wake transcoder 202", (code, w["eta_s"]), (202, 30))
    lease_tr = w["lease"]
    check("lower profile keeps the higher limit", (env.st()["limit"], len(env.calls("sudo"))), (130, 1))

    # --- refusals
    check("vidgen exclusive while llm runs", g.wake("vidgen"), (409, {"why": "exclusive"}))
    env.mod(free=1000)
    check("stt refused for vram", g.wake("stt"), (409, {"why": "vram"}))
    check("upscaler fits in 1000 MB", g.wake("upscaler")[0], 202)
    g.j("/off", {"stack": "stackA", "port": P["upscaler"]})
    env.mod(free=7000)
    open(os.path.join(env.state_dir, "busy"), "w").close()
    check("busy refuses a new wake", g.wake("stt"), (409, {"why": "busy"}))
    check("busy shows in state", g.state()["blocked"], "busy")
    check("busy keeps a running service", g.wake("llm")[0], 200)
    os.unlink(os.path.join(env.state_dir, "busy"))
    os.makedirs(os.path.join(env.proc, "4242"))
    open(os.path.join(env.proc, "4242", "cmdline"), "wb").write(b"/usr/bin/vrserver\0--secret-arg\0")
    code, text = g.req("/wake", raw=json.dumps({"port": P["stt"], "stack": "stackA"}).encode())
    check("VR refuses", (code, json.loads(text)), (409, {"why": "vr"}))
    check("VR answer hides the process", "vrserver" in text or "secret" in text, False)
    check("VR shows in state", g.state()["blocked"], "vr")
    shutil.rmtree(os.path.join(env.proc, "4242"))
    os.makedirs(os.path.join(env.proc, "4243"))
    open(os.path.join(env.proc, "4243", "cmdline"), "wb").write(b"/opt/resolve/bin/resolve\0")
    check("Resolve refuses", g.wake("stt"), (409, {"why": "vr"}))
    shutil.rmtree(os.path.join(env.proc, "4243"))
    check("free again", g.state()["blocked"], None)
    check("refusals started nothing but llm, transcoder, upscaler", env.calls("docker start"), ["docker start llm", "docker start transcoder", "docker start upscaler"])

    # --- off: another stack's lease keeps the service
    code, wb = g.wake("llm", stack="stackB")
    check("second stack lease", (code, wb["lease"] != lease_llm), (200, True))
    check("off one port, other stack holds it", g.j("/off", {"stack": "stackA", "port": P["llm"]}), (200, {"stopped": []}))
    check("llm still up", env.running("llm"), True)
    check("off all of stack B", g.j("/off", {"stack": "stackB", "port": None}), (200, {"stopped": ["llm"]}))
    check("llm stopped", env.running("llm"), False)
    check("limit follows the remaining service", wait_until(lambda: env.st()["limit"] == 100), True)
    check("off unknown port", g.j("/off", {"stack": "stackB", "port": 9})[0], 404)

    # --- idle: a wake without done is a job in flight
    time.sleep(3.2)
    check("in-flight job is never idle-stopped", env.running("transcoder"), True)
    g.j("/done", {"lease": lease_tr})
    check("idle stop after done", wait_until(lambda: not env.running("transcoder"), 6), True)
    check("limit restored to what was found", wait_until(lambda: env.st()["limit"] == 200), True)
    led = env.ledger()
    by = {r["service"]: r for r in led}
    check("ledger services", sorted(by), ["llm", "transcoder", "upscaler"])
    check("ledger llm reason and stacks", (by["llm"]["stop_reason"], by["llm"]["stacks"]["stackA"], sorted(by["llm"]["stacks"])),
          ("off", {"jobs": 1, "mode": "interactive", "batches": []}, ["stackA", "stackB"]))
    check("ledger transcoder", (by["transcoder"]["stop_reason"], by["transcoder"]["stacks"]["stackA"]["jobs"]), ("idle", 1))
    check("ledger fields", sorted(by["llm"]), ["end", "limit_w", "seconds", "service", "stacks", "start", "stop_reason", "wh"])
    check("ledger energy counted", by["transcoder"]["wh"] > 0, True)
    check("ledger has no tokens", TOKEN in open(os.path.join(env.state_dir, "usage.jsonl")).read(), False)

    # --- the service's own /status keeps it alive
    code, w = g.wake("imggen")
    check("wake imggen 202", (code, w["eta_s"]), (202, 150))
    g.j("/done", {"lease": w["lease"]})
    svc.state = "running"
    time.sleep(3.2)
    check("running job keeps the service", env.running("imggen"), True)
    svc.state = "idle"
    check("idle then stops", wait_until(lambda: not env.running("imggen"), 6), True)
    check("limit restored again", wait_until(lambda: env.st()["limit"] == 200), True)

    # --- batch: counts dones, holds the service, closes after N
    code, w = g.wake("transcoder", mode="batch", batch="b1", jobs=2)
    lease_b = w["lease"]
    check("batch wake 202", code, 202)
    check("batch done 1", g.j("/done", {"lease": lease_b}), (200, {"done": 1, "closed": False}))
    time.sleep(3.2)
    check("batch lease holds past idle", env.running("transcoder"), True)
    check("batch mode in state", g.state()["services"]["transcoder"]["mode"], "batch")
    check("batch idle_left unknown", g.state()["services"]["transcoder"]["idle_left_s"], None)
    check("batch done 2 closes", g.j("/done", {"lease": lease_b}), (200, {"done": 2, "closed": True}))
    check("service stopped at once", env.running("transcoder"), False)
    r = [x for x in env.ledger() if x["service"] == "transcoder"][-1]
    check("ledger batch", (r["stop_reason"], r["stacks"]["stackA"]), ("batch_done", {"jobs": 2, "mode": "batch", "batches": ["b1"]}))
    check("done on a closed lease", g.j("/done", {"lease": lease_b})[0], 404)

    # --- batch done does not stop a service another lease holds
    code, wi = g.wake("transcoder", stack="stackB")
    g.j("/done", {"lease": wi["lease"]})
    code, wb = g.wake("transcoder", mode="batch", batch="b2", jobs=1)
    check("batch joins running service", (code, wb["running"]), (200, True))
    check("batch closes, interactive holder keeps it", (g.j("/done", {"lease": wb["lease"]})[1]["closed"], env.running("transcoder")), (True, True))
    check("off stops it", g.j("/off", {"stack": "stackB"}), (200, {"stopped": ["transcoder"]}))

    # --- release
    code, wb = g.wake("upscaler", mode="batch", batch="b3", jobs=None)
    check("until-end batch wake", code, 202)
    check("release close=true", g.j("/release", {"lease": wb["lease"], "close": True}), (200, {"stopped": ["upscaler"]}))
    check("upscaler stopped", env.running("upscaler"), False)
    check("ledger released", [x for x in env.ledger() if x["service"] == "upscaler"][-1]["stop_reason"], "released")
    check("release unknown lease", g.j("/release", {"lease": wb["lease"], "close": True})[0], 404)
    check("release needs a bool", g.j("/release", {"lease": "abc", "close": "yes"})[0], 400)
    code, wi = g.wake("upscaler")
    g.j("/done", {"lease": wi["lease"]})
    check("release close=false", g.j("/release", {"lease": wi["lease"], "close": False}), (200, {"stopped": []}))
    check("still up after close=false", env.running("upscaler"), True)
    check("then the idle rule stops it", wait_until(lambda: not env.running("upscaler"), 6), True)

    # --- a service started by hand follows the idle rule
    env.mod_container("tts-hq", "running")
    check("hand-started service is stopped when idle", wait_until(lambda: not env.running("tts-hq"), 6), True)
    wait_until(lambda: [x for x in env.ledger() if x["service"] == "tts-hq"], 3)
    check("hand-started run in ledger", [x["stop_reason"] for x in env.ledger() if x["service"] == "tts-hq"], ["idle"])

    # --- per-service idle override
    code, w = g.wake("vidpost")
    g.j("/done", {"lease": w["lease"]})
    check("idle override shows", g.state()["services"]["vidpost"]["idle_left_s"] > 30, True)
    g.j("/off", {"stack": "stackA"})

    # --- power: clamp, failure, someone else, start failure
    env.mod(limit=110, max=120)
    code, w = g.wake("llm")
    check("clamped to the card's maximum", env.st()["limit"], 120)
    g.j("/off", {"stack": "stackA"})
    check("restored to found after clamp", wait_until(lambda: env.st()["limit"] == 110), True)
    env.mod(limit=200, max=200, sudo_fail=True)
    code, w = g.wake("llm")
    check("wake works when power fails", code, 202)
    check("failure is logged", "FAILED" in g.logtext(), True)
    g.j("/off", {"stack": "stackA"})
    env.mod(sudo_fail=False)
    check("failed power leaves limit alone", env.st()["limit"], 200)
    code, w = g.wake("llm")
    env.mod(limit=150)
    g.j("/off", {"stack": "stackA"})
    check("someone else's change is left", env.st()["limit"], 150)
    check("and logged", "changed by someone else" in g.logtext(), True)
    env.mod(limit=200, start_fail=["stt"])
    check("docker start failure", g.wake("stt"), (503, {"why": "start_failed"}))
    check("no power change for a failed start", env.st()["limit"], 200)
    check("no unexpected tool calls", env.calls("UNEXPECTED"), [])
    check("token never in the log", TOKEN in g.logtext(), False)
    for f in fakes.values():
        f.srv.shutdown()
    g.stop()


def ttl_scenario():
    env = Env()
    g = Gate(env, extra={"GATE_BATCH_TTL_S": "1", "GATE_IDLE_S": "1"})
    code, w = g.wake("transcoder", mode="batch", batch="b", jobs=None)
    check("ttl: batch started", code, 202)
    check("ttl: a silent batch lease is dropped and the service idles out", wait_until(lambda: not env.running("transcoder"), 8), True)
    wait_until(lambda: env.ledger(), 3)
    check("ttl: ledger idle", [x["stop_reason"] for x in env.ledger()], ["idle"])
    g.stop()


def startup_scenarios():
    env = Env()
    g = Gate(env, token="", wait=False)
    code = g.p.wait(10)
    check("no token: the gate refuses to start", code != 0, True)
    check("no token: says why", "GATE_TOKEN" in g.logtext(), True)
    # a gate that died with a limit set: the next one restores it when nothing runs
    env = Env()
    env.mod(limit=130)
    os.makedirs(env.state_dir)
    json.dump({"found": 200, "set": 130}, open(os.path.join(env.state_dir, "power.json"), "w"))
    g = Gate(env)
    check("restart restores the found limit", wait_until(lambda: env.st()["limit"] == 200), True)
    g.stop()
    # services keep running when the gate exits, and the run is closed in the ledger
    env = Env()
    g = Gate(env)
    g.wake("llm")
    g.stop()
    check("service survives a gate stop", env.running("llm"), True)
    check("run closed with gate_stop", [x["stop_reason"] for x in env.ledger()], ["gate_stop"])
    # unknown GPU: no power changes
    env = Env()
    env.mod(gpu="Some Other Card")
    g = Gate(env)
    check("unknown GPU still starts", g.wake("llm")[0], 202)
    check("unknown GPU: no sudo call", env.calls("sudo"), [])
    g.stop()
    # block patterns from the config
    env = Env()
    g = Gate(env, extra={"GATE_BLOCK_PROCS": "mygame, other-thing"})
    os.makedirs(os.path.join(env.proc, "77"))
    open(os.path.join(env.proc, "77", "cmdline"), "wb").write(b"/games/mygame\0")
    check("GATE_BLOCK_PROCS replaces the defaults", g.wake("llm"), (409, {"why": "vr"}))
    g.stop()


def ready_scenario():
    """A second wake right after a start is not "running" until the service's own /healthz answers."""
    env = Env()
    g = Gate(env)
    fk = FakeService(g.ports["llm"]); fk.healthy = False
    code, w = g.wake("llm", stack="stackA")
    check("ready: first wake 202", (code, w["running"], w["eta_s"]), (202, False, 60))
    code, w2 = g.wake("llm", stack="stackB")
    check("ready: second wake while booting is 202 with the time left", (code, w2["running"], 1 <= w2["eta_s"] <= 60), (202, False, True))
    code, w3 = g.wake("llm", stack="stackA")
    check("ready: same stack keeps its lease", (code, w3["lease"]), (202, w["lease"]))
    fk.healthy = True
    check("ready: healthy now, 200", g.wake("llm", stack="stackB"), (200, {"lease": w2["lease"], "running": True, "eta_s": 0}))
    fk.healthy = False
    check("ready: once ready it stays ready", g.wake("llm", stack="stackA")[0], 200)
    check("ready: no unexpected calls", env.calls("UNEXPECTED"), [])
    fk.srv.shutdown(); g.stop()
    # a service that never answers: after its budget the gate stops holding callers back
    env = Env()
    g = Gate(env)
    g.wake("tts")
    time.sleep(0.2)
    code, w = g.wake("tts", stack="stackB")
    check("ready: no healthz at all, still within budget -> 202", code, 202)
    g.stop()


def slow_docker_scenario():
    """A slow docker stop or start must not stall other requests (the gateway waits 5 s)."""
    env = Env()
    g = Gate(env, extra={"STUB_STOP_DELAY": "2", "STUB_START_DELAY": "0", "GATE_IDLE_S": "600"})
    fakes = {n: FakeService(g.ports[n]) for n in ("llm", "upscaler")}
    code, w = g.wake("llm")
    g.j("/done", {"lease": w["lease"]})
    box = {}
    t = threading.Thread(target=lambda: box.update(off=g.j("/off", {"stack": "stackA"})))
    t0 = time.time(); t.start(); time.sleep(0.4)
    code, wu = g.wake("upscaler", stack="stackB")
    check("slow stop: another service wakes at once", (code, time.time() - t0 < 1.8), (202, True))
    t1 = time.time(); g.state()
    check("slow stop: /state answers at once", time.time() - t1 < 1.0, True)
    t1 = time.time()
    code, wl = g.wake("llm", stack="stackB")
    check("slow stop: a wake on the stopping service waits for the stop, then starts it", (code, wl["running"], time.time() - t0 >= 1.9), (202, False, True))
    t.join()
    check("slow stop: off answered", box["off"], (200, {"stopped": ["llm"]}))
    check("slow stop: llm is up again", env.running("llm"), True)
    check("slow stop: ledger kept the stop", [x["stop_reason"] for x in env.ledger() if x["service"] == "llm"], ["off"])
    for f in fakes.values():
        f.srv.shutdown()
    g.stop()
    # a slow start: a second wake joins it instead of queueing behind it
    env = Env()
    g = Gate(env, extra={"STUB_START_DELAY": "2"})
    box = {}
    t = threading.Thread(target=lambda: box.update(w=g.wake("imggen", stack="stackA")))
    t.start(); time.sleep(0.6)
    t1 = time.time()
    code, w2 = g.wake("imggen", stack="stackB")
    check("slow start: second wake answers at once with 202", (code, w2["running"], time.time() - t1 < 1.0, 1 <= w2["eta_s"] <= 150), (202, False, True, True))
    check("slow start: state answers", g.state()["services"]["imggen"]["running"] in (True, False), True)
    t.join()
    check("slow start: one docker start only", env.calls("docker start"), ["docker start imggen"])
    check("slow start: both stacks hold the service", g.state()["services"]["imggen"]["leases"], 2)
    check("slow start: leases are different", box["w"][1]["lease"] != w2["lease"], True)
    g.stop()
    # a failed start drops the leases that joined meanwhile
    env = Env(); env.mod(start_fail=["stt"])
    g = Gate(env, extra={"STUB_START_DELAY": "1"})
    t = threading.Thread(target=lambda: box.update(w=g.wake("stt", stack="stackA")))
    t.start(); time.sleep(0.4)
    code, w2 = g.wake("stt", stack="stackB")
    t.join()
    check("failed start: first caller gets 503", box["w"], (503, {"why": "start_failed"}))
    check("failed start: no lease left", g.state()["services"]["stt"]["leases"], 0)
    g.stop()


def inflight_scenario():
    """Overlapping jobs of one stack: the first done must not make the service idle while the second runs."""
    env = Env()
    g = Gate(env, extra={"GATE_IDLE_S": "1.5"})
    code, w = g.wake("llm")
    code, w2 = g.wake("llm")
    check("inflight: same lease", w2["lease"], w["lease"])
    g.j("/done", {"lease": w["lease"]})
    time.sleep(3.5)
    check("inflight: one job still running keeps the service", env.running("llm"), True)
    g.j("/done", {"lease": w["lease"]})
    g.j("/done", {"lease": w["lease"]})                      # an extra done never goes below zero
    code, w3 = g.wake("llm")
    g.j("/done", {"lease": w3["lease"]})
    check("inflight: all done, idle stop", wait_until(lambda: not env.running("llm"), 6), True)
    g.stop()


def busy_stop_scenario():
    """Immediate stops (batch done, release, off) leave a service alone when its own /status says it works."""
    env = Env()
    g = Gate(env, extra={"GATE_IDLE_S": "1.5"})
    fk = FakeService(g.ports["imggen"])
    code, w = g.wake("imggen", mode="batch", batch="b", jobs=1)
    fk.state = "running"
    check("busy stop: batch closes", g.j("/done", {"lease": w["lease"]}), (200, {"done": 1, "closed": True}))
    check("busy stop: service left running", env.running("imggen"), True)
    time.sleep(2.5)
    check("busy stop: idle rule keeps a working service", env.running("imggen"), True)
    fk.state = "idle"
    check("busy stop: then the idle rule stops it", wait_until(lambda: not env.running("imggen"), 6), True)
    wait_until(lambda: env.ledger(), 3)                     # the ledger line is written just after the stop returns
    check("busy stop: ledger idle", [x["stop_reason"] for x in env.ledger()], ["idle"])
    code, w = g.wake("imggen")
    fk.state = "running"
    check("busy stop: off leaves a working service", g.j("/off", {"stack": "stackA"}), (200, {"stopped": []}))
    code, w = g.wake("imggen", mode="batch", batch="c", jobs=None)
    check("busy stop: release close leaves it too", g.j("/release", {"lease": w["lease"], "close": True}), (200, {"stopped": []}))
    fk.state = "idle"
    check("busy stop: idle again, stops", wait_until(lambda: not env.running("imggen"), 6), True)
    fk.srv.shutdown(); g.stop()


def evict_scenario():
    """exclusive / vram refusals do not count idle services under interactive leases: they are stopped first."""
    env = Env(); env.mod(free=8000, use={"llm": 5200, "imggen": 6500})
    g = Gate(env, extra={"GATE_IDLE_S": "600"})
    fakes = {n: FakeService(g.ports[n]) for n in ("llm", "imggen", "vidgen")}
    code, w = g.wake("imggen")
    g.j("/done", {"lease": w["lease"]})
    check("evict: idle imggen makes room for vidgen", g.wake("vidgen", stack="stackB")[0], 202)
    check("evict: imggen stopped, vidgen up", (env.running("imggen"), env.running("vidgen")), (False, True))
    check("evict: ledger reason", [x["stop_reason"] for x in env.ledger() if x["service"] == "imggen"], ["evicted"])
    check("evict: imggen lease gone", g.state()["services"]["imggen"]["leases"], 0)
    g.j("/off", {"stack": "stackB"})
    # vram: llm idle, imggen needs more than what is free
    code, w = g.wake("llm")
    g.j("/done", {"lease": w["lease"]})
    check("evict: vram, idle llm is stopped for imggen", g.wake("imggen", stack="stackB")[0], 202)
    check("evict: llm stopped for vram", (env.running("llm"), env.running("imggen")), (False, True))
    g.j("/off", {"stack": "stackB"})
    # never evicted: job in flight, busy by its own status, batch lease, no lease at all
    code, w = g.wake("imggen")                               # no done: in flight
    check("evict: in-flight job is not evicted", g.wake("vidgen", stack="stackB"), (409, {"why": "exclusive"}))
    g.j("/done", {"lease": w["lease"]})
    fakes["imggen"].state = "running"
    check("evict: working service is not evicted", g.wake("vidgen", stack="stackB"), (409, {"why": "exclusive"}))
    fakes["imggen"].state = "idle"
    g.j("/off", {"stack": "stackA"})
    code, wb = g.wake("imggen", mode="batch", batch="b", jobs=None)
    g.j("/done", {"lease": wb["lease"]})
    check("evict: batch-held service is not evicted", g.wake("vidgen", stack="stackB"), (409, {"why": "exclusive"}))
    g.j("/release", {"lease": wb["lease"], "close": True})
    env.mod_container("imggen", "running")                   # started by hand, nobody holds it
    check("evict: unleased service is left to the idle rule", g.wake("vidgen", stack="stackB"), (409, {"why": "exclusive"}))
    env.mod_container("imggen", "exited")
    # evicting is not enough: the others stay (not stopped for nothing)
    env.mod(use={"llm": 5200, "imggen": 6500, "stt": 4000})
    code, w = g.wake("llm"); g.j("/done", {"lease": w["lease"]})
    env.mod(free=3000)
    check("evict: vram that eviction cannot fix is refused", g.wake("imggen", stack="stackB"), (409, {"why": "vram"}))
    check("evict: llm untouched then", env.running("llm"), True)
    check("evict: no unexpected calls", env.calls("UNEXPECTED"), [])
    for f in fakes.values():
        f.srv.shutdown()
    g.stop()


def power_retry_scenario():
    """The saved limit survives a failed read or a failed restore at the last stop and is restored on a later tick."""
    env = Env()
    g = Gate(env)
    code, w = g.wake("transcoder")                           # profile 100 W
    check("power retry: lowered to 100", env.st()["limit"], 100)
    env.mod(smi_fail=True)
    g.j("/done", {"lease": w["lease"]})
    g.j("/off", {"stack": "stackA"})
    check("power retry: service stopped", wait_until(lambda: not env.running("transcoder")), True)
    check("power retry: unreadable limit does not restore or forget", env.st()["limit"], 100)
    check("power retry: state kept", json.load(open(os.path.join(env.state_dir, "power.json"))), {"found": 200, "set": 100})
    env.mod(smi_fail=False)
    check("power retry: restored on a later tick", wait_until(lambda: env.st()["limit"] == 200, 4), True)
    check("power retry: state dropped after the restore", wait_until(lambda: not os.path.exists(os.path.join(env.state_dir, "power.json"))), True)
    # sudo fails at the restore
    code, w = g.wake("transcoder")
    check("power retry: lowered again", env.st()["limit"], 100)
    env.mod(sudo_fail=True)
    g.j("/done", {"lease": w["lease"]})
    g.j("/off", {"stack": "stackA"})
    time.sleep(1.0)
    check("power retry: failed restore leaves the limit and keeps the state", (env.st()["limit"], os.path.exists(os.path.join(env.state_dir, "power.json"))), (100, True))
    check("power retry: the failure is logged once", g.logtext().count("restore failed, will retry"), 1)
    env.mod(sudo_fail=False)
    check("power retry: restored once sudo works", wait_until(lambda: env.st()["limit"] == 200, 4), True)
    g.stop()
    check("power retry: no unexpected calls", env.calls("UNEXPECTED"), [])


def block_match_scenario():
    """Only the program (argv[0]) counts, not a file or argument that happens to contain a name."""
    env = Env()
    g = Gate(env)

    def proc(pid, *args):
        d = os.path.join(env.proc, str(pid)); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "cmdline"), "wb").write(b"\0".join(a.encode() for a in args) + b"\0")

    def clear():
        shutil.rmtree(env.proc); os.makedirs(env.proc)

    for i, cmd in enumerate([("tail", "-f", "/home/u/.steam/logs/vrserver.txt"), ("less", "vrserver.txt"), ("sh", "-c", "pgrep -f vrserver"),
                             ("pgrep", "-f", "vrserver"), ("vi", "/opt/resolve/bin/resolve"), ("less", "SteamLaunch.log"),
                             ("grep", "monado-service", "notes.txt"), ("vi", "/x/proton", "run")]):
        proc(100 + i, *cmd)
    check("block: names in arguments do not block", g.state()["blocked"], None)
    clear()
    for name, cmd in [("vrserver", ("/home/u/.steam/steam/steamapps/common/SteamVR/bin/linux64/vrserver",)),
                      ("vrcompositor", ("/x/vrcompositor", "--arg")), ("monado", ("/usr/bin/monado-service",)), ("monado bare", ("monado-service",)),
                      ("resolve", ("/opt/resolve/bin/resolve", "-nogui")),
                      ("steam game", ("/home/u/.steam/ubuntu12_32/reaper", "SteamLaunch", "AppId=620", "--", "/x/game")),
                      ("proton", ("python3", "/x/proton", "waitforexitandrun", "/g/game.exe")),
                      ("proton run", ("/usr/bin/python3.11", "/x/proton", "run", "/g/game.exe"))]:
        proc(200, *cmd)
        check("block: " + name + " blocks", g.state()["blocked"], "vr")
        clear()
    check("block: clear again", g.state()["blocked"], None)
    g.stop()
    # the config: a plain pattern matches the program, a cmd: pattern the whole line
    env = Env()
    g = Gate(env, extra={"GATE_BLOCK_PROCS": "mygame, cmd:--fullscreen"})
    proc2 = os.path.join(env.proc, "5"); os.makedirs(proc2)
    open(os.path.join(proc2, "cmdline"), "wb").write(b"/usr/bin/other\0--fullscreen\0")
    check("block: cmd: pattern matches arguments", g.state()["blocked"], "vr")
    open(os.path.join(proc2, "cmdline"), "wb").write(b"/usr/bin/tail\0/x/mygame.log\0")
    check("block: plain pattern ignores arguments", g.state()["blocked"], None)
    g.stop()


def socket_scenario():
    """Idle or half-sent connections are dropped, and a flood is capped, so the gate keeps answering."""
    env = Env()
    g = Gate(env, extra={"GATE_SOCKET_TIMEOUT_S": "1", "GATE_MAX_CONNS": "4"})
    socks = [socket.create_connection(("127.0.0.1", g.port)) for _ in range(3)]
    check("socket: healthz answers with idle peers connected", g.req("/healthz", token=None), (200, "ok gate"))
    half = socket.create_connection(("127.0.0.1", g.port))
    half.sendall(b"POST /wake HTTP/1.0\r\nAuthorization: Bearer " + TOKEN.encode() + b"\r\nContent-Length: 100\r\n\r\n{\"port\"")
    time.sleep(2.0)
    for sk in socks + [half]:
        sk.settimeout(2)
        try:
            data = sk.recv(100)
        except OSError:
            data = b"error"
        check("socket: idle connection closed by the gate", data in (b"", ), True)
        sk.close()
    check("socket: still answers after the timeout", g.req("/healthz", token=None), (200, "ok gate"))
    flood = [socket.create_connection(("127.0.0.1", g.port)) for _ in range(12)]
    time.sleep(0.3)
    dead = 0
    for sk in flood:
        sk.settimeout(0.3)
        try:
            if sk.recv(1) == b"":
                dead += 1
        except OSError:
            pass
    check("socket: connections over the cap are closed at once", dead >= 8, True)
    time.sleep(1.5)
    for sk in flood:
        sk.close()
    check("socket: healthy again after the flood", wait_until(lambda: g.req("/healthz", token=None) == (200, "ok gate"), 5), True)
    g.stop()


def power_profile_unit():
    sys.path.insert(0, HERE)
    import gate as G
    prof = G.load_profiles(os.path.join(os.path.dirname(HERE), "power_profiles.conf"))
    check("repo profile: 3060 Ti", G.profile_for(prof, "NVIDIA GeForce RTX 3060 Ti")["vidgen"], 130)
    check("repo profile: 1070 Ti", G.profile_for(prof, "NVIDIA GeForce GTX 1070 Ti"), {"llm": 100})
    check("repo profile: unknown card", G.profile_for(prof, "NVIDIA GeForce GTX 1060"), {})
    check("env file parser", G.parse_env_file(os.path.join(tempfile.mkdtemp(), "none")), {})


def install_scenario():
    env = Env()
    script = os.path.join(HERE, "install_gate.sh")
    host_env = os.path.join(env.d, "host.env")
    base = {k: v for k, v in os.environ.items() if not k.startswith("GATE_")}
    base.update(PATH=env.bin + os.pathsep + os.environ.get("PATH", ""), STUB_STATE=env.sp, HOME=env.d, GATE_ENV_FILE=host_env)
    open(host_env, "w").write("LLM_POWER_W=130\n")
    r = subprocess.run(["bash", script], env=base, capture_output=True, text=True)
    check("install without GATE_TOKEN fails", r.returncode != 0 and "GATE_TOKEN" in (r.stdout + r.stderr), True)
    check("install without token wrote nothing", os.path.exists(os.path.join(env.d, ".config/systemd/user/bridgeai-gate.service")), False)
    open(host_env, "w").write(f"GATE_TOKEN='{TOKEN}'\nGATE_PORT=8711\n")
    env.mod(cron="* * * * * flock -n /tmp/x '/r/gpu-host/gpu_power.sh'\n0 3 * * * /usr/bin/other-job\n")
    r = subprocess.run(["bash", script], env=base, capture_output=True, text=True)
    check("install ok", r.returncode, 0)
    unit = os.path.join(env.d, ".config/systemd/user/bridgeai-gate.service")
    text = open(unit).read() if os.path.exists(unit) else ""
    check("unit ExecStart", f"ExecStart=/usr/bin/env python3 -I {HERE}/gate.py" in text, True)
    check("unit restarts on failure", "Restart=on-failure" in text, True)
    check("unit has no token", TOKEN in text, False)
    check("systemctl calls", env.calls("systemctl"), ["systemctl --user daemon-reload", "systemctl --user enable bridgeai-gate.service", "systemctl --user restart bridgeai-gate.service"])
    check("install says the restart drops leases", "restart" in r.stdout and "adopts" in r.stdout, True)
    check("gpu_power cron line removed, others kept", env.st()["cron"], "0 3 * * * /usr/bin/other-job\n")
    check("firewall reminder with the port", "8711" in r.stdout, True)
    check("token not printed", TOKEN in r.stdout + r.stderr, False)
    # gpu_power.sh steps aside once the gate is installed
    gp = os.path.join(os.path.dirname(HERE), "gpu_power.sh")
    env2 = dict(base, XDG_CONFIG_HOME=os.path.join(env.d, ".config"))
    env.mod(calls=[])
    r = subprocess.run(["bash", gp], env=env2, capture_output=True, text=True, timeout=20)
    check("gpu_power.sh exits at once with the gate installed", (r.returncode, env.st()["calls"]), (0, []))


def run_services_scenario():
    """run_services.sh in a copy of the layout (no host.env: nothing real is read), against the stub docker."""
    env = Env()
    root = os.path.join(env.d, "repo"); os.makedirs(os.path.join(root, "gpu-host"))
    for f in ("run_services.sh", "gpu_power.sh"):
        shutil.copy(os.path.join(os.path.dirname(HERE), f), os.path.join(root, "gpu-host", f))
    rs = os.path.join(root, "gpu-host", "run_services.sh")
    base = {k: v for k, v in os.environ.items() if not k.startswith(("GATE_", "GPU_", "LLM"))}
    base.update(PATH=env.bin + os.pathsep + os.environ.get("PATH", ""), STUB_STATE=env.sp, HOME=env.d,
                XDG_CONFIG_HOME=os.path.join(env.d, "cfg"), GATE_STATE_DIR=env.state_dir)

    def run(*args):
        env.mod(calls=[])
        r = subprocess.run(["bash", rs, *args], env=base, capture_output=True, text=True, timeout=60)
        return r.returncode, env.calls("docker")

    check("create makes the container, starts nothing", run("create", "stt"),
          (0, ["docker inspect stt", "docker rm stt", "docker create stt"]))
    check("busy on", (run("busy", "on")[0], os.path.exists(os.path.join(env.state_dir, "busy"))), (0, True))
    check("busy status", subprocess.run(["bash", rs, "busy", "status"], env=base, capture_output=True, text=True).stdout.strip(), "busy: on")
    check("busy off", (run("busy", "off")[0], os.path.exists(os.path.join(env.state_dir, "busy"))), (0, False))
    check("busy bad word", run("busy", "maybe")[0], 2)
    os.makedirs(os.path.join(env.d, "cfg/systemd/user"))
    open(os.path.join(env.d, "cfg/systemd/user/bridgeai-gate.service"), "w").write("[Service]\n")
    check("gate installed: no blind start", run("stt"), (0, ["docker inspect stt", "docker rm stt", "docker create stt"]))
    check("gate installed: start is explicit", run("start", "stt")[1], ["docker rm stt", "docker run stt"])
    os.unlink(os.path.join(env.d, "cfg/systemd/user/bridgeai-gate.service"))
    check("no gate: default still starts", run("stt")[1], ["docker rm stt", "docker run stt"])
    check("no unexpected calls", env.calls("UNEXPECTED"), [])


if __name__ == "__main__":
    for fn in (power_profile_unit, main_scenario, ttl_scenario, startup_scenarios, ready_scenario, slow_docker_scenario, inflight_scenario,
               busy_stop_scenario, evict_scenario, power_retry_scenario, block_match_scenario, socket_scenario, install_scenario,
               run_services_scenario):
        try:
            fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            check(fn.__name__ + " crashed", type(e).__name__, None)
    print("FAILED: " + ", ".join(FAIL) if FAIL else "all gate tests passed")
    sys.exit(1 if FAIL else 0)
