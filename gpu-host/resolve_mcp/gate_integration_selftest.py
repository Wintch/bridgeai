#!/usr/bin/env python3
"""Offline end-to-end test of the REAL gpu-host/gate/gate.py and the REAL resolve_session.py proxy, wired together over HTTP.
Nothing real is touched: the gate runs with the stub docker, nvidia-smi and sudo and the fake /proc of gate_selftest.py, the
proxy fronts the fake MCP server of resolve_session_selftest.py, and its "start Resolve" hook writes a fake /proc/<pid>
(cmdline /opt/resolve/bin/resolve -nogui, environ DISPLAY=:99) into the gate's fake proc dir; "stop" removes it. No Resolve, no
Xvfb, no GPU, no ssh. Both selftests are loaded by path (python3 -I has no script dir in sys.path)."""
import importlib.util, os, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gt = load("gate_selftest", os.path.join(HERE, "..", "gate", "gate_selftest.py"))
rt = load("resolve_session_selftest", os.path.join(HERE, "resolve_session_selftest.py"))
Env, Gate, Session = gt.Env, gt.Gate, rt.Session
wait_until = gt.wait_until


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


# The proxy's session hooks: "start Resolve" writes a fake /proc/<pid> into the gate's proc dir, "stop" removes it. Rendering is
# a file in FAKE_DIR: "0" (default), "1", or "none" (the scripting API cannot tell).
HOOKS = r'''
import os, shutil, time
D = os.environ["FAKE_DIR"]
P = os.path.join(os.environ["FAKE_PROC_DIR"], os.environ.get("FAKE_PID", "7001"))
def ev(s):
    open(os.path.join(D, "events"), "a").write(s + "\n")
def resolve_running():
    return os.path.exists(os.path.join(P, "cmdline"))
def ensure_session():
    if resolve_running():
        return 0, False
    time.sleep(0.2)
    os.makedirs(P, exist_ok=True)
    open(os.path.join(P, "environ"), "wb").write(b"HOME=/x\0DISPLAY=:99\0LANG=C\0")
    open(os.path.join(P, "cmdline"), "wb").write(b"/opt/resolve/bin/resolve\0-nogui\0")
    ev("start")
    return 0, True
def shutdown():
    if os.path.exists(P):
        shutil.rmtree(P, ignore_errors=True)
        ev("stop")
def is_rendering():
    p = os.path.join(D, "rendering")
    v = open(p).read().strip() if os.path.exists(p) else "0"
    return None if v == "none" else v == "1"
'''
rt.HOOKS = HOOKS      # Session writes its hooks file from this module global

IDLE = 3.0            # GATE_IDLE_RESOLVE


class World:
    """One gate and its fake world."""
    def __init__(self, idle=IDLE, extra=None):
        self.env = Env()
        e = {"GATE_IDLE_RESOLVE": str(idle), "GATE_EXT_CLOSE_WAIT_S": "20", "GATE_TICK_S": "0.2", "GATE_IDLE_S": "600"}
        e.update(extra or {})
        self.gate = Gate(self.env, extra=e)
        self.sessions = []

    def session(self, **extra_env):
        env = {"GATE_PORT_RESOLVE": str(self.gate.ports["resolve"]), "FAKE_PROC_DIR": self.env.proc}
        env.update(extra_env)
        s = Session("http://127.0.0.1:%d" % self.gate.port, env, beat="0.3")
        self.sessions.append(s)
        return s

    def svc(self):
        return self.gate.state()["services"]["resolve"]

    def proc_up(self, pid="7001"):
        return os.path.exists(os.path.join(self.env.proc, pid, "cmdline"))

    def resolve_ledger(self):
        return [r for r in self.env.ledger() if r["service"] == "resolve"]

    def reasons(self):
        return [r["stop_reason"] for r in self.resolve_ledger()]

    def close(self):
        for s in self.sessions:
            s.cleanup()
        self.gate.stop()
        shutil.rmtree(self.env.d, ignore_errors=True)


def call(s, rid, timeout=20.0):
    s.call(rid)
    return s.reply_to(rid, timeout)


def text_of(r):
    return ((r or {}).get("result") or {}).get("content", [{}])[0].get("text")


def err_of(r):
    e = (r or {}).get("error") or {}
    return e.get("code"), e.get("message")


def main_scenario():
    """Scenarios 1 to 5 on one gate and one proxy: lazy connect, grant, idle close, rendering, eviction."""
    w = World()
    g, env = w.gate, w.env
    s = w.session()
    # 1. connect and tools/list: no gate call, no Resolve
    r = s.init()
    check("1 initialize answered by the server", ((r or {}).get("result") or {}).get("serverInfo"), {"name": "fake"})
    s.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    r = s.reply_to(1)
    check("1 tools/list answered", ((r or {}).get("result") or {}).get("tools"), [{"name": "t"}])
    time.sleep(1.0)
    st = w.svc()
    check("1 no lease, not running", (st["leases"], st["running"]), (0, False))
    check("1 no fake Resolve, no start event", (w.proc_up(), s.events()), (False, []))
    check("1 the gate never granted anything, no power change", ("grant" in g.logtext(), env.calls("sudo")), (False, []))

    # 2. first tools/call: grant with go, power profile, Resolve appears, gate state running
    r = call(s, 2)
    check("2 first tools/call answered", text_of(r), "ran")
    cmd = open(os.path.join(env.proc, "7001", "cmdline"), "rb").read() if w.proc_up() else b""
    envb = open(os.path.join(env.proc, "7001", "environ"), "rb").read() if w.proc_up() else b""
    check("2 fake Resolve in the gate's proc dir", (cmd, b"DISPLAY=:99\0" in envb), (b"/opt/resolve/bin/resolve\0-nogui\0", True))
    check("2 gate state running with one lease", wait_until(lambda: w.svc()["running"]), True)
    check("2 one lease", w.svc()["leases"], 1)
    check("2 the gate granted with go", "grant resolve" in g.logtext(), True)
    check("2 power profile applied (stub sudo saw -pl 120)", ("sudo -n /usr/bin/nvidia-smi -pl 120" in env.calls("sudo"), env.st()["limit"]), (True, 120))
    check("2 the person-session check did not trip on our own Resolve", g.state()["blocked"], None)
    check("2 one start event", s.events(), ["start"])
    check("2 a second call reuses the running Resolve", (text_of(call(s, 3)), s.events()), ("ran", ["start"]))

    # 3. idle: the gate sets close, the proxy closes, Resolve gone, ledger idle, power restored
    check("3 idle close: Resolve stopped by the proxy", wait_until(lambda: s.events() == ["start", "stop"], 15), True)
    check("3 fake Resolve gone", w.proc_up(), False)
    check("3 gate asked to close for idle", "close requested for resolve (idle)" in g.logtext(), True)
    check("3 ledger line with reason idle", wait_until(lambda: w.reasons() == ["idle"], 8), True)
    check("3 gate state not running", wait_until(lambda: not w.svc()["running"]), True)
    check("3 power restored to the found limit", wait_until(lambda: env.st()["limit"] == 200, 8), True)

    # 4a. the API cannot tell if a render runs: the close request is not followed, nothing is closed on a guess
    check("4 call after an idle close starts Resolve again", (text_of(call(s, 4)), s.events()), ("ran", ["start", "stop", "start"]))
    s.set("rendering", "none")
    check("4 the gate still asks to close for idle", wait_until(lambda: w.svc()["close"] == "idle", 10), True)
    time.sleep(1.5)
    check("4 unknown rendering keeps Resolve open past the close request", (w.proc_up(), s.events()), (True, ["start", "stop", "start"]))
    s.set("rendering", "0")
    check("4 not rendering: the proxy closes", wait_until(lambda: not w.proc_up(), 10), True)
    check("4 ledger: second idle line", wait_until(lambda: w.reasons() == ["idle", "idle"], 8), True)
    # 4b. rendering: beats keep the run alive past the idle time
    check("4 restart for the render", (text_of(call(s, 5)), w.proc_up()), ("ran", True))
    s.set("rendering", "1")
    time.sleep(2 * IDLE + 1.0)
    st = w.svc()
    check("4 rendering blocks the idle close (beats keep the run alive)", (st["running"], st["close"], w.proc_up(), w.reasons()), (True, None, True, ["idle", "idle"]))
    check("4 the idle clock is being refreshed by the beats", st["idle_left_s"] >= 2, True)
    s.set("rendering", "0")
    check("4 render over: idle close follows", wait_until(lambda: not w.proc_up(), 15), True)
    check("4 ledger: third idle line", wait_until(lambda: w.reasons() == ["idle"] * 3, 8), True)

    # 5. a vidgen wake while Resolve idle-holds: eviction close request, the proxy closes, vidgen starts
    check("5 restart for the eviction", (text_of(call(s, 6)), w.proc_up()), ("ran", True))
    code, v = g.wake("vidgen", stack="stackV")
    check("5 vidgen granted after the eviction", code, 202)
    check("5 vidgen started", wait_until(lambda: env.running("vidgen")), True)
    check("5 Resolve closed by the proxy", (w.proc_up(), s.events()[-1]), (False, "stop"))
    check("5 ledger line with reason evicted", wait_until(lambda: w.reasons()[3:] == ["evicted"], 8), True)
    check("5 power: vidgen has no profile, the found limit is back", wait_until(lambda: env.st()["limit"] == 200, 8), True)
    n_events = len(s.events())
    code, msg = err_of(call(s, 7))
    check("5 a call while vidgen works gets a clear refusal", (code, msg), (-32000, "the GPU is busy with another task (exclusive); try again later"))
    check("5 refused call started nothing", (w.proc_up(), len(s.events())), (False, n_events))
    g.j("/off", {"stack": "stackV"})
    check("5 vidgen stopped by off", wait_until(lambda: not env.running("vidgen"), 10), True)
    check("5 after vidgen leaves a call works again", (text_of(call(s, 8)), w.proc_up()), ("ran", True))
    check("5 the gate sees that run (its tick is not skipped by the close below)", wait_until(lambda: w.svc()["running"]), True)
    rc = s.close()
    check("5 proxy exits cleanly", rc, 0)
    check("5 closing the proxy removed Resolve", w.proc_up(), False)
    check("5 ledger: the last run is released by its client", wait_until(lambda: w.reasons()[-1:] == ["released"], 8), True)
    check("5 power back to the found limit", wait_until(lambda: env.st()["limit"] == 200, 8), True)
    check("no unexpected calls", env.calls("UNEXPECTED"), [])
    check("no stderr traceback in the proxy", "Traceback" in s.stderr_text(), False)
    w.close()


def person_scenario():
    """6. A person's Resolve on DISPLAY=:0: the call gets a -32000 error naming the reason and nothing starts."""
    w = World()
    env = w.env
    env.fake_proc(9001, "/opt/resolve/bin/resolve", ":0")
    check("6 the gate sees a person's session", wait_until(lambda: w.gate.state()["blocked"] == "vr"), True)
    s = w.session()
    s.init()
    code, msg = err_of(call(s, 1))
    check("6 error -32000", code, -32000)
    check("6 the error names the person's session", ("person's own DaVinci Resolve session" in (msg or ""), "vr" in (msg or "") or "person" in (msg or "")), (True, True))
    check("6 nothing started", (s.events(), w.proc_up(), w.svc()["leases"], w.svc()["running"]), ([], False, 0, False))
    check("6 the person's process was not touched", os.path.exists(os.path.join(env.proc, "9001", "cmdline")), True)
    check("6 no power change", env.calls("sudo"), [])
    check("6 the gate logged the refusal", "refuse resolve for a stack: vr" in w.gate.logtext(), True)
    env.drop_proc(9001)
    check("6 the person leaves", wait_until(lambda: w.gate.state()["blocked"] is None), True)
    check("6 the next call works", (text_of(call(s, 2)), s.events()), ("ran", ["start"]))
    s.close()
    check("6 no unexpected calls", env.calls("UNEXPECTED"), [])
    w.close()


def bench_scenario():
    """7. Bench: a proxy with RESOLVE_GATE_BENCH is admitted, one without gets the bench refusal, /bench/end restores."""
    w = World(idle=60)
    g, env = w.gate, w.env
    env.mod(limit=200)
    code, b = g.j("/bench/start", {"stack": "bench", "watts": 110})
    bid = b.get("bench") if code == 200 else None
    check("7 bench started, cap 110", (code, env.st()["limit"]), (200, 110))
    sa = w.session(RESOLVE_GATE_BENCH=bid or "x", FAKE_PID="7001")
    sb = w.session(FAKE_PID="7002")
    sa.init(); sb.init()
    check("7 the proxy with the bench id is admitted", (text_of(call(sa, 1)), sa.events()), ("ran", ["start"]))
    check("7 the gate sees Resolve running", wait_until(lambda: w.svc()["running"]), True)
    check("7 the bench cap stays, the profile is not applied", (env.st()["limit"], [c for c in env.calls("sudo") if c.endswith("-pl 120")]), (110, []))
    code, msg = err_of(call(sb, 1))
    check("7 the proxy without the id gets the bench error", (code, msg), (-32000, "the GPU is reserved for a power measurement; try again later"))
    check("7 the refused proxy started nothing", (sb.events(), w.proc_up("7002")), ([], False))
    check("7 a plain wake of another service is refused too", g.wake("llm"), (409, {"why": "bench"}))
    check("7 bench watts change", g.j("/bench/watts", {"bench": bid, "watts": 130}), (200, {"bench": bid, "watts": 130}))
    check("7 cap follows", env.st()["limit"], 130)
    check("7 /bench/end", g.j("/bench/end", {"bench": bid}), (200, {"ok": True}))
    check("7 the cap was restored (200) and the Resolve profile applies after", wait_until(lambda: env.st()["limit"] == 120, 8), True)
    check("7 the restore went through the found limit", "sudo -n /usr/bin/nvidia-smi -pl 200" in env.calls("sudo"), True)
    code, msg = err_of(call(sa, 2))
    check("7 after the end the old bench id is refused", (code, msg), (-32000, "the GPU is reserved for a power measurement; try again later"))
    check("7 the open Resolve was left alone", w.proc_up("7001"), True)
    rc = sa.close()
    check("7 the benched proxy exits cleanly and Resolve is gone", (rc, wait_until(lambda: not w.proc_up("7001"), 10)), (0, True))
    check("7 power back to the found limit", wait_until(lambda: env.st()["limit"] == 200, 8), True)
    check("7 the proxy without the id works now", (text_of(call(sb, 2)), sb.events(), wait_until(lambda: env.st()["limit"] == 120, 8)), ("ran", ["start"], True))
    sb.close()
    check("7 no unexpected calls", env.calls("UNEXPECTED"), [])
    w.close()


if __name__ == "__main__":
    for fn in (main_scenario, person_scenario, bench_scenario):
        try:
            fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            check(fn.__name__ + " crashed", type(e).__name__, None)
    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED: {FAIL}")
        sys.exit(1)
    print("all gate integration checks passed")
