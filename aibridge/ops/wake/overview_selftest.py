#!/usr/bin/env python3
"""Offline test of the waker's overview route (waker.py: stack_overview, overview, overview_conf, make_overview_handler): GET /__wake/all
answers every stack's state from the last tick's snapshot, never calls docker, never wakes anything, and only for allowed clients.

Fake stacks (shims built without __init__) and a real listener on 127.0.0.1; docker is replaced by a function that fails the test if called.

Run from anywhere:  python3 -I ops/wake/overview_selftest.py
"""
import importlib.util, json, os, sys, tempfile, threading, time, urllib.error, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("waker", os.path.join(HERE, "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

DOCKER_CALLS = []
def no_docker(*a, **k):
    DOCKER_CALLS.append(a); raise AssertionError("docker called from the overview route")
w.docker = no_docker
w.running = lambda name: no_docker("inspect", name)
TMP = tempfile.mkdtemp(prefix="overview-selftest-")
w.STATE_DIR = TMP
mem = os.path.join(TMP, "mem"); open(mem, "w").write("4321")
w.MEMINFO = mem
w.CFG = {"max_awake": 6}
NOW = float(int(time.time()))


def shim(name, seen=None, **kw):
    s = w.Stack.__new__(w.Stack)
    s.name, s.seen = name, seen
    s.booting = s.queued = s.stopping = False
    s.last_activity, s.human_ts, s.cron_due, s.brain_started = NOW - 1000, 0.0, None, 0.0
    s.state_file = os.path.join(TMP, f"{name}.state.json")
    s.state_lock = threading.Lock()
    s.workdir = os.path.join(TMP, name, "workdir"); os.makedirs(s.workdir, exist_ok=True)
    for k, v in kw.items():
        setattr(s, k, v)
    return s

# ---- one stack's row
asleep = shim("dormido", seen=(NOW - 10, False, False, False, []), cron_due=NOW + 1800)
r = w.stack_overview(asleep, NOW)
chk(r["state"] == "asleep" and r["brain"] is False and r["web"] is False, "a stack the last tick saw down is asleep")
chk(r["idle_s"] is None and r["next_cron_s"] == 1800, "asleep: no idle time, the next planned cron wake in seconds")
chk(r["seen_s"] == 10 and r["image"] is None and r["update_pending"] is False, "snapshot age; no image recorded, no update pending")

busy = shim("ocupado", seen=(NOW - 5, False, True, False, ["un turno del agente", "procesos en segundo plano"]), last_activity=NOW - 5,
            always=True, warm_kept=True)
busy.save_state(image="sha256:c8bb2d3e348ac19322031534abb96fffca5bdc72a7c452c5d794129f4ea4d4e5")
open(busy.pending_path(), "w").write("{}")
r = w.stack_overview(busy, NOW)
chk(r["state"] == "awake" and r["brain"] is True and r["web"] is False, "an always-on brain with its web asleep is awake (the front's /__wake/status says asleep)")
chk(r["turn"] is True and r["busy"] == ["un turno del agente", "procesos en segundo plano"], "a running turn is flagged, with the tick's busy reasons")
chk(r["idle_s"] == 5 and r["always"] is True and r["warm"] is True, "idle seconds since the last activity; always and warm flags")
chk(r["image"] == "c8bb2d3e348a" and r["update_pending"] is True, "the short image id from the state file, and a pending update")
chk(r["next_cron_s"] is None, "an awake stack shows no next cron wake")

recent = shim("reciente", seen=(NOW - 3, True, True, True, []), last_activity=NOW - 3)
open(os.path.join(recent.workdir, ".last_human"), "w").write(str(NOW - 120))
r = w.stack_overview(recent, NOW)
chk(r["web_in_use"] is True and r["turn"] is False, "a UI request in the last tick: the web is in use, no turn")
chk(r["last_human_s"] == 120, "the person's last turn from the router's .last_human stamp")
chk(w.stack_overview(shim("t2", seen=(NOW - 3, False, True, False, ["un turno reciente"])), NOW)["turn"], "a turn that just ended counts as a turn")

stale = shim("viejo", seen=(NOW - 900, False, True, True, ["un turno del agente"]))
r = w.stack_overview(stale, NOW)
chk(r["state"] == "awake" and r["seen_s"] == 900 and r["busy"] == [] and not r["turn"] and not r["web_in_use"],
    "an old snapshot keeps its state with its age, but no stale busy list or turn")
chk(w.stack_overview(shim("nuevo"), NOW)["state"] == "unknown", "no tick yet: unknown, not asleep")
chk(w.stack_overview(shim("b", seen=(NOW - 3, False, False, False, []), booting=True), NOW)["state"] == "starting", "booting: starting")
chk(w.stack_overview(shim("q", queued=True, booting=True), NOW)["state"] == "queued", "waiting for its turn to boot: queued")
chk(w.stack_overview(shim("u", seen=(NOW - 3, False, True, False, []), updating=True), NOW)["state"] == "updating", "an image update: updating")
chk(w.stack_overview(shim("x", seen=(NOW - 3, False, True, False, []), stopping=True), NOW)["state"] == "stopping", "being stopped: stopping")
chk(w.stack_overview(shim("w", seen=(NOW - 20, False, False, False, []), brain_started=NOW - 5), NOW)["state"] == "awake",
    "a wake that ended after the last tick is awake already")

# ---- a stop in tick() refreshes the snapshot at once: a stopped stack never shows awake until the next tick
def tick_shim(name):
    """A stack whose tick() runs the idle path for real; docker is replaced by flags the stubs flip."""
    t = shim(name, seen=(NOW - 30, True, True, False, []), last_activity=time.time() - 10_000, web_started=0.0, brain_started=0.0,
             updating=False, always=False, warm_kept=False, warm_eligible=False, web_ts=0, cron_only=False, cron_hold_until=0.0,
             idle_web=60, idle_brain=60, ticks=0)
    t.up = {"web": True, "brain": True}
    t.calls = []
    noop = lambda *a, **k: None
    for m in ("refresh_telegram", "adopt_booted_image", "task_run_watch", "drop_stale_banner", "announce_sleep"):
        setattr(t, m, noop)
    t.outside_checks = []
    t.note_outside_boot = lambda: t.outside_checks.append(t.up["brain"])   # who started an up brain (a deploy's boot is a background wake)
    t.web_up, t.brain_up = (lambda: t.up["web"]), (lambda: t.up["brain"])
    t.ui_requests, t.busy_reasons, t.sleep_request = (lambda: False), (lambda **k: []), (lambda: None)
    t.warm_tick = t.update_tick = lambda *a: False
    t.busy, t.ocio_before_sleep, t.compact_before_sleep = (lambda: False), (lambda: False), (lambda: True)
    def sleep_web():
        t.calls.append(("web", w.stack_overview(t)["state"])); t.up["web"] = False
    def sleep_brain(recheck=None):
        t.calls.append(("brain", w.stack_overview(t)["state"])); t.up["brain"] = False; return True
    t.sleep_web, t.sleep_brain = sleep_web, sleep_brain
    return t

w.CFG = {"max_awake": 6, "cron": {"hold_seconds": 300}}
w.NO_SLEEP = os.path.join(TMP, "no-sleep-flag-absent")
idle = tick_shim("idle")
idle.tick()
r = w.stack_overview(idle)
chk([c[0] for c in idle.calls] == ["web", "brain"], "tick shim: an idle stack's web and brain are stopped in one tick")
chk(idle.outside_checks == [True], "tick: an up brain is checked once a tick for a start the waker did not make")
chk(r["state"] == "asleep" and r["web"] is False and r["brain"] is False and r["seen_s"] == 0,
    "right after the stop in tick() the overview says asleep, with a fresh snapshot (not awake until the next tick)")
halfway = tick_shim("half")
halfway.compact_before_sleep = lambda: False   # the brain is not stopped this tick: only the web went down
halfway.busy_reasons = lambda **k: []
halfway.tick()
r = w.stack_overview(halfway)
chk(r["state"] == "awake" and r["web"] is False and r["brain"] is True, "only the web stopped: still awake, the web shown down at once")
gone = shim("gone", seen=(NOW - 3, True, True, True, ["procesos en segundo plano"]))
w.seen_after_stop(gone, False, False)
r = w.stack_overview(gone)
chk(r["state"] == "asleep" and r["busy"] == [] and r["web_in_use"] is False, "seen_after_stop: nothing up, no stale busy list or web use")
kept = shim("kept", seen=(NOW - 3, True, True, False, ["procesos en segundo plano"]))
w.seen_after_stop(kept, False, True)
chk(w.stack_overview(kept)["busy"] == ["procesos en segundo plano"], "seen_after_stop: the brain still up keeps its busy reasons")
w.CFG = {"max_awake": 6}

# ---- the whole answer
stacks = [asleep, busy, recent, stale]
d = w.overview(stacks, NOW)
chk([x["name"] for x in d["stacks"]] == ["dormido", "ocupado", "reciente", "viejo"], "every stack, in stacks.json order")
chk(d["mem_available_mb"] == 4321 and d["max_awake"] == 6 and d["awake"] == 3 and d["ts"] == int(NOW), "host numbers: free memory, max_awake, how many are up")
chk(all(k in ("ts", "mem_available_mb", "max_awake", "awake", "stacks") for k in d), "no other top-level field")
chk(not DOCKER_CALLS, "no docker call at all")

# ---- config
oc = w.overview_conf
chk(oc(None)[0] is None and oc({})[0] is None, "no \"overview\" block: off")
chk(oc({"listen": "0.0.0.0:8662", "allow": ["10.9.8.5"]})[0] is None, "a wildcard address is refused")
chk(oc({"listen": "[::]:8662", "allow": ["10.9.8.5"]})[0] is None, "the IPv6 wildcard too")
chk(oc({"listen": "10.9.8.4:8662"})[0] is None and "empty" in oc({"listen": "10.9.8.4:8662", "allow": []})[1], "no allowed client: off")
chk(oc({"listen": "10.9.8.4:x", "allow": ["10.9.8.5"]})[0] is None and oc({"listen": "nombre:8662", "allow": ["10.9.8.5"]})[0] is None,
    "a bad port or a host name is refused")
chk(oc({"listen": "10.9.8.4:8662", "allow": ["no-ip"]})[0] is None, "a bad allow entry is refused")
good = oc({"listen": "10.9.8.4:8662", "allow": ["10.9.8.5", "10.9.8.0/29"]})[0]
chk(good and good[0] == "10.9.8.4" and good[1] == 8662 and len(good[2]) == 2, "address, port and networks parsed")

# ---- the listener: allowed client, other client, paths, methods
def serve(nets):
    srv = w.Server(("127.0.0.1", 0), w.make_overview_handler(lambda: w.overview(stacks, NOW), nets))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]

def call(port, path=w.OVERVIEW_PATH, method="GET"):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method, data=b"{}" if method != "GET" else None)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read()), r.headers.get("Cache-Control")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), None

import ipaddress
p = serve([ipaddress.ip_network("127.0.0.1/32")])
st, body, cc = call(p)
chk(st == 200 and body["stacks"][1]["turn"] is True and cc == "no-store", "an allowed client gets every stack (no-store)")
chk(call(p, w.OVERVIEW_PATH + "?x=1")[0] == 200, "a query string does not matter")
chk(call(p, "/__wake/status")[0] == 404 and call(p, "/")[0] == 404, "nothing else is served there")
chk(call(p, method="POST")[0] == 405 and call(p, method="DELETE")[0] == 405, "read-only: other methods get 405")
q = serve([ipaddress.ip_network("10.9.8.5/32")])
chk(call(q)[0] == 403 and call(q, "/")[0] == 403, "a client outside the allow list gets 403, whatever the path")
r6 = serve([ipaddress.ip_network("::1/128")])
chk(call(r6)[0] == 403, "an IPv6 rule does not let an IPv4 client in")

def boom():
    raise RuntimeError("broken")
srv = w.Server(("127.0.0.1", 0), w.make_overview_handler(boom, [ipaddress.ip_network("127.0.0.0/8")]))
threading.Thread(target=srv.serve_forever, daemon=True).start()
w.log = lambda msg: None
chk(call(srv.server_address[1])[0] == 500, "an error inside gives a clean 500, not a dropped connection")
chk(not DOCKER_CALLS, "still no docker call after the HTTP requests")

# ---- the front handler does NOT serve it (fronts are reachable from the internet through the edge)
class FakeFront:
    name, lang, web = "f", "es", ["fake"]
    def public_state(self): return "asleep"
front = w.Server(("127.0.0.1", 0), w.make_handler(FakeFront()))
threading.Thread(target=front.serve_forever, daemon=True).start()
try:
    urllib.request.urlopen(f"http://127.0.0.1:{front.server_address[1]}{w.OVERVIEW_PATH}", timeout=5)
    front_code = 200
except urllib.error.HTTPError as e:
    front_code, front_body = e.code, e.read()
chk(front_code == 503 and b"stacks" not in front_body, "a stack's front answers /__wake/all like any other path (asleep), never with the list")

# ---- the example config shows it with test addresses
ex = json.load(open(os.path.join(HERE, "stacks.json.example")))
chk(w.overview_conf(ex.get("overview"))[0] is not None and ex["overview"]["listen"].startswith("10.9.8."), "stacks.json.example documents \"overview\" with test addresses")

print("ALL OK" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
