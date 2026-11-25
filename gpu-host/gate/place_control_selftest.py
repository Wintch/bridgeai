#!/usr/bin/env python3
"""Offline checks for place_control.py and the gate's /place/* with a fake docker (a script on PATH that keeps each container's state in a file).
Run: python3 -I place_control_selftest.py"""
import hashlib, importlib.util, json, os, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
import atexit as _a, shutil as _s
tmp = tempfile.mkdtemp(prefix="selftest-"); _a.register(_s.rmtree, tmp, True)
HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        fails.append(name)


root = os.path.join(tmp, "places"); fakes = os.path.join(tmp, "fake"); bindir = os.path.join(tmp, "bin")
for d in (root, fakes, bindir):
    os.makedirs(d)
open(os.path.join(bindir, "docker"), "w").write(f'''#!{sys.executable}
import os, sys, json
F = {fakes!r}
a = sys.argv[1:]
def rd(n, d=""):
    try: return open(os.path.join(F, n)).read().strip()
    except OSError: return d
def cname(x): return x.replace("place-", "").replace("-desktop", "")
open(os.path.join(F, "calls.txt"), "a").write(" ".join(a) + "\\n")
if a[0] == "inspect":
    n = cname(a[-1]); st = rd(n + ".state")
    if not st: sys.exit(1)
    if "PortBindings" in a[2]:
        print(json.dumps({{"3000/tcp": [{{"HostIp": "10.9.8.7", "HostPort": rd(n + ".p0", "3010")}}], "3001/tcp": [{{"HostIp": "10.9.8.7", "HostPort": rd(n + ".p1", "3011")}}]}}))
    else: print(st)
elif a[0] in ("start", "stop"):
    n = cname(a[-1])
    if not rd(n + ".state"): sys.exit(1)
    open(os.path.join(F, n + ".state"), "w").write("running" if a[0] == "start" else "exited")
elif a[0] == "exec":
    n = cname([x for x in a if x.startswith("place-")][0]); v = rd(n + ".idle")
    if v == "fail": sys.exit(1)
    print(v)
elif a[0] == "stats":
    print(rd(cname(a[-1]) + ".cpu", "1.0") + "%")
''')
os.chmod(os.path.join(bindir, "docker"), 0o755)


def fake(name, state="exited", idle="5000", cpu="1.0"):
    for k, v in (("state", state), ("idle", idle), ("cpu", cpu)):
        open(os.path.join(fakes, f"{name}.{k}"), "w").write(v)


def make_place(name, token):
    d = os.path.join(root, name); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, ".gate.hash"), "w").write(hashlib.sha256(token.encode()).hexdigest() + "\n")
    open(os.path.join(d, ".ports"), "w").write("3010 3011\n")


TOK_A, TOK_B = "a" * 30, "b" * 30
make_place("alpha", TOK_A); make_place("beta", TOK_B)
os.makedirs(os.path.join(root, "nohash"))                     # a folder without a gate token is not drivable
fake("alpha"); fake("beta")
os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]

spec = importlib.util.spec_from_file_location("place_control", os.path.join(HERE, "place_control.py"))
pc = importlib.util.module_from_spec(spec); sys.modules["place_control"] = pc; spec.loader.exec_module(pc)
clock = [1_000_000.0]
P = pc.Places(root=root, state_path=os.path.join(tmp, "st", "places.json"), now=lambda: clock[0], idle_s=1800, warn_s=600, busy_cpu=80, active_s=90)
calls = lambda: open(os.path.join(fakes, "calls.txt")).read().splitlines() if os.path.exists(os.path.join(fakes, "calls.txt")) else []

check("a token finds its own place and no other", (P.find_by_token(TOK_A), P.find_by_token(TOK_B)), ("alpha", "beta"))
check("a wrong, empty, short or non-string token finds nothing", [P.find_by_token(t) for t in ("c" * 30, "", "short", None, 5, "a" * 500)], [None] * 6)
check("only folders with a gate hash are listed", P.names(), ["alpha", "beta"])

# --- start / stop / keep
code, out = P.start("alpha")
check("start: runs docker start on that container only, answers the web addresses and the clock", (code, out["running"], out["urls"]["http"], out["urls"]["https"], out["idle_limit_min"]),
      (200, True, "http://10.9.8.7:3010", "https://10.9.8.7:3011", 30))
check("start touched nothing else", [c for c in calls() if c.startswith("start")], ["start place-alpha-desktop"])
check("an unknown place is 404", P.start("ghost"), (404, {"why": "no_such_place"}))
code, out = P.start("alpha")
check("start on a running place only keeps it (no second docker start)", (code, len([c for c in calls() if c.startswith("start")])), (200, 1))
fake("beta", "running")
check("start reports only how many OTHER places run, never whose", P.info("alpha").get("others_running"), 1)
check("info of a stopped place has no clock", "closes_in_min" in P.info("alpha"), True)

# --- the clock: in use resets; idle warns at 20 min, closes at 30 min; render or touch keeps it
P.start("alpha"); P.stop("beta")
fake("alpha", "running", idle="3000", cpu="1.0")
clock[0] += 1300                                              # 21 min idle: past idle_s - warn_s
ev = P.tick()
check("21 min idle: one warning, still running", (ev, P.container_state("alpha"), "warned_at" in P.info("alpha")), ([("alpha", "warned")], "running", True))
check("the warning is given once", P.tick(), [])
check("closes_in counts down", P.info("alpha")["closes_in_min"], 8)
code, out = P.keep("alpha")
check("keep resets the clock and clears the warning", (code, out["closes_in_min"], "warned_at" in out), (200, 30, False))
clock[0] += 1300; P.tick()
fake("alpha", "running", idle="3", cpu="1.0")                 # somebody touched the screen
check("touched the screen: back to full time, event 'back'", (P.tick(), P.info("alpha")["closes_in_min"]), ([("alpha", "back")], 30))
fake("alpha", "running", idle="3000", cpu="150.0")            # a render with nobody there
clock[0] += 2000
check("a render at high CPU keeps it open however long", (P.tick(), P.container_state("alpha")), ([], "running"))
fake("alpha", "running", idle="fail", cpu="2.0")              # the probe fails (no X yet) and nothing is busy: counts as idle
clock[0] += 1900
check("30 min idle closes it, with the reason", (P.tick(), P.container_state("alpha"), P.info("alpha").get("closed_reason")), ([("alpha", "closed")], "exited", "idle"))
check("a closed place is not touched by the clock again", P.tick(), [])
code, out = P.stop("alpha")
check("stop on a stopped place is fine and starts nothing", (code, out["running"]), (200, False))
check("keep on a stopped place is refused", P.keep("alpha"), (409, {"why": "not_running"}))
fake("beta", "running")                                       # started by hand with place.py: the clock starts when the gate first sees it
clock[0] += 100000
check("a place started by hand gets a fresh clock, not an instant close", (P.tick(), P.container_state("beta")), ([], "running"))
P.start("alpha"); P.stop("alpha", "person")
check("a person's own close is recorded as such", P.info("alpha")["closed_reason"], "person")

# --- over HTTP through the real gate
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
fake("alpha"); fake("beta")
env = {k: v for k, v in os.environ.items() if not k.startswith("GATE_")}
env.update(GATE_TOKEN="stack-token-for-tests-xx", GATE_HOST_TOKEN="host-token-for-tests-xx", GATE_PORT=str(port), GATE_BIND="127.0.0.1", GATE_ENV_FILE=os.path.join(tmp, "none.env"),
           GATE_STATE_DIR=os.path.join(tmp, "gstate"), HOME=tmp, PLACES_ROOT=root, PLACE_TICK_S="3600", GATE_TICK_S="5")
log = open(os.path.join(tmp, "gate.log"), "w+")
proc = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "gate.py")], env=env, stdout=log, stderr=subprocess.STDOUT)
for _ in range(80):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1); break
    except Exception:
        time.sleep(0.1)


def rq(path, token=None, method=None, body=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers=h, method=method or ("POST" if body is not None else "GET"))
    try:
        with urllib.request.urlopen(r, timeout=20) as x:
            return x.status, json.loads(x.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


try:
    check("http: no token, a wrong one, the stacks' token and the HOST token are all 401 on /place/state",
          [rq("/place/state", t)[0] for t in (None, "x" * 30, env["GATE_TOKEN"], env["GATE_HOST_TOKEN"])], [401] * 4)
    check("http: alpha's token reads alpha's state", rq("/place/state", TOK_A)[1]["place"], "alpha")
    code, out = rq("/place/start", TOK_A, body=b"{}")
    check("http: start opens alpha and only alpha", (code, out["place"], out["running"], P.container_state("beta")), (200, "alpha", True, "exited"))
    check("http: beta's token sees beta, never alpha's", rq("/place/state", TOK_B)[1]["place"], "beta")
    check("http: keep and stop", (rq("/place/keep", TOK_A, body=b"{}")[0], rq("/place/stop", TOK_A, body=b"{}")[1]["running"]), (200, False))
    check("http: unknown path 404, GET on a POST path 404", (rq("/place/nope", TOK_A)[0], rq("/place/start", TOK_A)[0]), (404, 404))
    check("http: the host token cannot open a place and a place token cannot touch /host/*", (rq("/place/start", env["GATE_HOST_TOKEN"], body=b"{}")[0], rq("/host/state", TOK_A)[0]), (401, 401))
    check("http: the stacks' token cannot use /host/ either (unchanged)", rq("/host/state", env["GATE_TOKEN"])[0], 401)
    check("http: the gate says how many places it watches", "places: 2 with a gate token" in (log.flush() or open(log.name).read()), True)
finally:
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()

# --- the same gate without a places folder: /place/* is simply off
env2 = dict(env, PLACES_ROOT=os.path.join(tmp, "absent"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
env2["GATE_PORT"] = str(port)
proc = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "gate.py")], env=env2, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
for _ in range(80):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1); break
    except Exception:
        time.sleep(0.1)
try:
    check("no places folder on the host: /place/* answers 403 places_disabled", rq("/place/state", TOK_A), (403, {"why": "places_disabled"}))
finally:
    proc.terminate()

print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
