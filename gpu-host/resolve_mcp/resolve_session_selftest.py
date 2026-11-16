#!/usr/bin/env python3
"""Offline test of resolve_session.py (the lazy, gate-leased Resolve session) and of the vendored wrapper's dispatch: a fake
MCP server, a fake gate (http.server on a free loopback port, scripted replies) and fake session hooks that only write an event
file (RESOLVE_SESSION_HOOKS). No Resolve, no Xvfb, no GPU, no ssh; the session registries live in a temp dir."""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SESSION = os.path.join(HERE, "resolve_session.py")
TOKEN = "t0ken-for-tests"
FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def wait_until(fn, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return False


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


# A fake MCP server. It records every line it receives (raw) to RECV_LOG. FAKE_NEEDS_RESOLVE=<flag file>: it exits at once
# when the flag does not exist (a server that cannot start without Resolve). FAKE_SILENT_INIT=<flag file>: it ignores
# initialize while the flag does not exist (a server that hangs without Resolve).
FAKE_SERVER = r'''
import json, os, sys, time
log = open(os.environ["RECV_LOG"], "ab")
need = os.environ.get("FAKE_NEEDS_RESOLVE")
if need and not os.path.exists(need):
    sys.exit(3)
silent = os.environ.get("FAKE_SILENT_INIT")
def out(s):
    sys.stdout.write(s + "\n"); sys.stdout.flush()
for raw in sys.stdin.buffer:
    log.write(raw); log.flush()
    try:
        m = json.loads(raw)
    except ValueError:
        continue
    if not isinstance(m, dict) or "method" not in m or "id" not in m:
        continue
    meth, rid = m["method"], m["id"]
    if meth == "initialize":
        if silent and not os.path.exists(silent):
            continue
        out('{"jsonrpc": "2.0",  "method": "notifications/message", "params": {"level": "info", "data": "hello"}}')
        out('{"jsonrpc":"2.0","id":"srv-1","method":"roots/list"}')
        out(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "fake"}}}))
    elif meth == "tools/list":
        out(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"tools": [{"name": "t"}]}}))
    elif meth in ("tools/call", "resources/read"):
        time.sleep(float((m.get("params") or {}).get("arguments", {}).get("sleep", 0)))
        out(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": "ran"}]}}))
    else:
        out(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {}}))
'''

# Fake session hooks: "start" and "stop" events in EVENTS; the running flag, the rendering switch and a start code are files.
HOOKS = r'''
import os, time
D = os.environ["FAKE_DIR"]
def ev(s):
    open(os.path.join(D, "events"), "a").write(s + "\n")
def ensure_session():
    if os.path.exists(os.path.join(D, "raise")):
        raise RuntimeError("boom")
    code = int(open(os.path.join(D, "start_code")).read()) if os.path.exists(os.path.join(D, "start_code")) else 0
    if code:
        ev("start-failed")
        return code, False
    if os.path.exists(os.path.join(D, "running")):
        return 0, False
    time.sleep(0.2)
    open(os.path.join(D, "running"), "w").close()
    ev("start")
    return 0, True
def shutdown():
    if os.path.exists(os.path.join(D, "running")):
        os.unlink(os.path.join(D, "running"))
        ev("stop")
def is_rendering():
    p = os.path.join(D, "rendering")
    v = open(p).read().strip() if os.path.exists(p) else "0"
    return None if v == "none" else v == "1"
def resolve_running():
    return os.path.exists(os.path.join(D, "running"))
'''


class FakeGate:
    """Scripted replies: wake_replies is consumed first (each a (status, body)), then like the real gate for an external task:
    200 running when the session's Resolve is up (run_flag exists), else 202 with go:true. wake_delay seconds slow every /wake.
    `close` is what GET /state and /beat report for services.resolve.close. Every request is recorded as (method, path, body)."""
    def __init__(self):
        self.calls, self.wake_replies, self.close, self.lock = [], [], None, threading.Lock()
        self.run_flag, self.wake_delay = None, 0
        gate = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

            def handle_any(self, method):
                if self.headers.get("Authorization") != "Bearer " + TOKEN:
                    return self.reply(401, {"why": "token"})
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n)) if n else None
                if self.path == "/wake" and gate.wake_delay:
                    with gate.lock:
                        gate.calls.append((method, self.path, body))
                    time.sleep(gate.wake_delay)
                    return self.reply(200, {"lease": "L9", "running": False, "eta_s": 1})
                with gate.lock:
                    gate.calls.append((method, self.path, body))
                    if self.path == "/wake":
                        if gate.wake_replies:
                            return self.reply(*gate.wake_replies.pop(0))
                        if gate.run_flag and os.path.exists(gate.run_flag):
                            return self.reply(200, {"lease": "L1", "running": True, "eta_s": 0})
                        return self.reply(202, {"lease": "L1", "running": False, "eta_s": 1, "go": True})
                    if self.path == "/done":
                        return self.reply(200, {"done": 1, "closed": False})
                    if self.path == "/beat":
                        return self.reply(200, {"close": gate.close})
                    if self.path == "/state":
                        return self.reply(200, {"services": {"resolve": {"close": gate.close}}})
                    if self.path in ("/down", "/off"):
                        return self.reply(200, {"ok": True})
                    if self.path == "/release":
                        return self.reply(200, {"stopped": []})
                self.reply(404, {"why": "not_found"})

            def do_POST(self):
                self.handle_any("POST")

            def do_GET(self):
                self.handle_any("GET")

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def paths(self, *want):
        with self.lock:
            return [p for _, p, _ in self.calls if not want or p in want]

    def bodies(self, path):
        with self.lock:
            return [b for _, p, b in self.calls if p == path]


class Session:
    """One resolve_session.py process in front of the fake server, with its own state dir and event file."""
    def __init__(self, gate, extra_env=None, beat="0.3"):
        gate_url = gate if isinstance(gate, str) else gate.url
        self.dir = tempfile.mkdtemp(prefix="rs_selftest_")
        if not isinstance(gate, str):
            gate.run_flag = os.path.join(self.dir, "running")
        for name, src in (("fake_server.py", FAKE_SERVER), ("hooks.py", HOOKS)):
            open(os.path.join(self.dir, name), "w").write(src)
        env = dict(os.environ, RESOLVE_STATE_DIR=os.path.join(self.dir, "state"), FAKE_DIR=self.dir,
                   RECV_LOG=os.path.join(self.dir, "recv"), RESOLVE_SESSION_HOOKS=os.path.join(self.dir, "hooks.py"),
                   GATE_URL=gate_url, GATE_TOKEN=TOKEN, RESOLVE_GATE_BEAT_S=beat, RESOLVE_SESSION_PROBE_S="1.5",
                   RESOLVE_GATE_STACK="selftest-stack", PYTHONUNBUFFERED="1", RESOLVE_SESSION_REWAKE_S="0.1")
        env.update({k: v.replace("{dir}", self.dir) for k, v in (extra_env or {}).items()})
        self.proc = subprocess.Popen([sys.executable, SESSION, self.dir, "--", sys.executable, os.path.join(self.dir, "fake_server.py")],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.lines, self.err, self.cv = [], [], threading.Condition()
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read_out(self):
        for raw in self.proc.stdout:
            with self.cv:
                self.lines.append(raw.rstrip(b"\n")); self.cv.notify_all()

    def _read_err(self):
        for raw in self.proc.stderr:
            self.err.append(raw.decode("utf-8", "replace"))

    def send(self, obj):
        raw = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.proc.stdin.write(raw + b"\n"); self.proc.stdin.flush()

    def reply_to(self, rid, timeout=10.0):
        """The response (a dict with no method) for id rid, or None."""
        def find():
            for raw in self.lines:
                try:
                    m = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(m, dict) and "method" not in m and m.get("id") == rid:
                    return m
        end = time.time() + timeout
        with self.cv:
            while time.time() < end:
                m = find()
                if m is not None:
                    return m
                self.cv.wait(0.1)
        return None

    def events(self):
        p = os.path.join(self.dir, "events")
        return open(p).read().split() if os.path.exists(p) else []

    def recv_log(self):
        p = os.path.join(self.dir, "recv")
        return open(p, "rb").read().split(b"\n") if os.path.exists(p) else []

    def set(self, name, value):
        open(os.path.join(self.dir, name), "w").write(value)

    def stderr_text(self):
        return "".join(self.err)

    def init(self):
        self.send({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        r = self.reply_to(0)
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return r

    def call(self, rid, sleep=0, method="tools/call"):
        params = {"name": "t", "arguments": {"sleep": sleep}} if method == "tools/call" else {"uri": "x://y"}
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill(); self.proc.wait()
        return self.proc.returncode

    def cleanup(self):
        if self.proc.poll() is None:
            self.proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


def is_error(m, text):
    return bool(m) and m.get("error", {}).get("code") == -32000 and text in m["error"].get("message", "")


def scenario_lazy_start_and_calls():
    print("-- lazy start, pairing, pass-through, release on exit")
    gate = FakeGate(); s = Session(gate)
    try:
        r = s.init()
        check("initialize answered with Resolve down", bool(r) and r["result"]["serverInfo"]["name"] == "fake", True)
        s.send({"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"})
        check("tools/list answered with Resolve down", (s.reply_to("list-1") or {}).get("result", {}).get("tools"), [{"name": "t"}])
        time.sleep(0.5)
        check("no Resolve start on connect + list", s.events(), [])
        check("no gate call on connect + list", gate.paths(), [])

        # lines pass through unchanged, both ways
        odd = b'{"jsonrpc": "2.0",  "method":"notifications/progress", "params": {"progressToken": "p", "a": [1, 2.50, null]}}'
        s.send(odd)
        s.send({"jsonrpc": "2.0", "id": "srv-1", "result": {"roots": []}})
        s.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": "nothing", "reason": "x"}})
        check("client notification reaches the server byte for byte", wait_until(lambda: odd in s.recv_log()), True)
        check("a response to a server request reaches the server", wait_until(
            lambda: any(b'"srv-1"' in l and b'"roots"' in l for l in s.recv_log())), True)
        check("cancel notification reaches the server", any(b"notifications/cancelled" in l for l in s.recv_log()), True)
        check("server notification reaches the client byte for byte", any(
            l == b'{"jsonrpc": "2.0",  "method": "notifications/message", "params": {"level": "info", "data": "hello"}}' for l in s.lines), True)
        check("server-initiated request (string id) reaches the client", any(
            l == b'{"jsonrpc":"2.0","id":"srv-1","method":"roots/list"}' for l in s.lines), True)
        check("still no start after notifications", s.events(), [])

        # first tools/call: lease, start, forward, done
        s.call(7)
        r = s.reply_to(7)
        check("first tools/call answered", (r or {}).get("result", {}).get("content", [{}])[0].get("text"), "ran")
        check("Resolve started once, by the call", s.events(), ["start"])
        wakes = gate.bodies("/wake")
        check("one /wake with port, stack and mode", wakes, [{"port": 8695, "stack": "selftest-stack", "mode": "interactive"}])
        check("/done after the response, with the lease", wait_until(lambda: gate.bodies("/done") == [{"lease": "L1"}]), True)

        # pairing by id, ids of any type, a resources/read too
        s.call("a", sleep=0.6); s.call(8); s.call(9, method="resources/read")
        for rid in ("a", 8, 9):
            check(f"call {rid!r} answered", (s.reply_to(rid) or {}).get("result", {}).get("content", [{}])[0].get("text"), "ran")
        check("one /wake per call, one /done per response", (wait_until(lambda: len(gate.bodies("/done")) == 4) and len(gate.bodies("/wake"))), 4)
        check("no second start while the session runs", s.events(), ["start"])
        check("registry: connected and using", (os.listdir(os.path.join(s.dir, "state", "resolve_xvfb_99.clients")),
                                                os.listdir(os.path.join(s.dir, "state", "resolve_xvfb_99.using"))),
              ([str(s.proc.pid)], [str(s.proc.pid)]))
        s.send([{"jsonrpc": "2.0", "id": 5, "method": "tools/call"}])
        time.sleep(0.3)
        check("a batch is refused, not forwarded", (any(b'"id": 5' in l or b'"id":5' in l for l in s.recv_log())), False)

        rc = s.close()
        check("exit code 0 on client EOF", rc, 0)
        check("exit: release, last user, down and stop", (gate.paths("/down", "/release"), s.events()),
              (["/down", "/release"], ["start", "stop"]))
        check("release does not close the service", gate.bodies("/release"), [{"lease": "L1", "close": False}])
        check("registries empty after exit", (os.listdir(os.path.join(s.dir, "state", "resolve_xvfb_99.clients")),
                                              os.listdir(os.path.join(s.dir, "state", "resolve_xvfb_99.using"))), ([], []))
    finally:
        s.cleanup()


def scenario_refusals():
    print("-- refusals: 409 and an unreachable gate")
    gate = FakeGate(); s = Session(gate)
    try:
        s.init()
        gate.wake_replies.append((409, {"why": "exclusive"}))
        s.call(1)
        r = s.reply_to(1)
        check("409 exclusive -> JSON-RPC error -32000 naming the reason", is_error(r, "the GPU is busy with another task (exclusive); try again later"), True)
        gate.wake_replies.append((409, {"why": "vr"}))
        s.call(2)
        check("409 vr names a person's session", is_error(s.reply_to(2), "a person's own DaVinci Resolve session"), True)
        gate.wake_replies.append((409, {"why": "bench"}))
        s.call(3)
        check("409 bench -> error", is_error(s.reply_to(3), "power measurement"), True)
        check("nothing started, nothing forwarded", (s.events(), [l for l in s.recv_log() if b"tools/call" in l]), ([], []))
        check("no /done for a refused wake", gate.paths("/done"), [])
        # tools/list still works after refusals
        s.send({"jsonrpc": "2.0", "id": "l", "method": "tools/list"})
        check("tools/list unaffected by refusals", bool(s.reply_to("l")), True)
        # then the gate grants: it starts
        s.call(4)
        check("granted after the refusals: runs", ((s.reply_to(4) or {}).get("result") is not None, s.events()), (True, ["start"]))
    finally:
        s.cleanup()

    # a start that fails: error, /done, /down, /release, and the next call tries again
    gate = FakeGate(); s = Session(gate)
    try:
        s.init()
        s.set("start_code", "4")
        s.call(1)
        check("a failed start answers the call with an error", is_error(s.reply_to(1), "did not become scriptable"), True)
        check("a failed start gives the lease back (done, down, release)", wait_until(lambda: gate.paths("/done", "/down", "/release") == ["/done", "/down", "/release"]), True)
        s.set("start_code", "0")
        s.call(2)
        check("the next call after a failed start works", ((s.reply_to(2) or {}).get("result") is not None, s.events()), (True, ["start-failed", "start"]))
    finally:
        s.cleanup()

    s = Session("http://127.0.0.1:%d" % free_port())
    try:
        s.init()
        s.call(1)
        check("gate unreachable -> error, not a start", (is_error(s.reply_to(1), "gate is not reachable"), s.events()), (True, []))
        check("gate unreachable: nothing reached the server", [l for l in s.recv_log() if b"tools/call" in l], [])
    finally:
        s.cleanup()


def scenario_close_rules():
    print("-- close on the gate's request: idle, in flight, rendering, re-acquire")
    gate = FakeGate(); s = Session(gate)
    try:
        s.init()
        s.call(1)
        s.reply_to(1)
        check("started by the call", s.events(), ["start"])
        # idle, rendering: no close, and the run is kept alive with beats
        gate.close = "idle"
        s.set("rendering", "1")
        time.sleep(1.5)
        check("no close while Resolve is rendering", s.events(), ["start"])
        check("beats while rendering", len(gate.paths("/beat")) >= 2, True)
        s.set("rendering", "none")
        n_beats = len(gate.paths("/beat"))
        time.sleep(1.2)
        check("no close when the render state cannot be read", s.events(), ["start"])
        check("no beats on a guess", len(gate.paths("/beat")), n_beats)
        # a call in flight when the close request arrives: no close until it ends
        s.set("rendering", "0")
        gate.calls.clear()
        s.call(2, sleep=1.8)
        time.sleep(1.2)
        check("no close while a call is in flight", s.events(), ["start"])
        check("beats while a call is in flight", len(gate.paths("/beat")) >= 1, True)
        check("the call still answers", (s.reply_to(2) or {}).get("result") is not None, True)
        check("closed after the call, idle, once the gate asked", wait_until(lambda: s.events() == ["start", "stop"]), True)
        check("close reports down and releases the lease", wait_until(lambda: gate.paths("/down", "/release")[-2:] == ["/down", "/release"]), True)
        check("idle poll reads GET /state", "/state" in gate.paths(), True)
        check("using registry emptied by the close", os.listdir(os.path.join(s.dir, "state", "resolve_xvfb_99.using")), [])
        # re-acquire
        gate.close = None
        gate.calls.clear()
        s.call(3)
        check("next call re-acquires and starts again", ((s.reply_to(3) or {}).get("result") is not None, s.events()), (True, ["start", "stop", "start"]))
        check("the next call took a new lease", gate.paths("/wake"), ["/wake"])
        check("session restart is logged", "session restarted: the open project was closed" in s.stderr_text(), True)
        check("connected process survived the close", s.proc.poll(), None)
    finally:
        s.cleanup()


def scenario_beat_404():
    print("-- the gate forgot the lease")
    gate = FakeGate(); s = Session(gate)
    try:
        s.init()
        s.set("rendering", "1")
        s.call(1)
        s.reply_to(1)
        orig = gate.srv.RequestHandlerClass.handle_any
        state = {"n": 0}

        def patched(self, method):
            if self.path == "/beat" and state["n"] == 0:
                state["n"] = 1
                n = int(self.headers.get("Content-Length") or 0); self.rfile.read(n)
                with gate.lock:
                    gate.calls.append((method, self.path, None))
                return self.reply(404, {"why": "unknown_lease"})
            return orig(self, method)
        gate.srv.RequestHandlerClass.handle_any = patched
        gate.calls.clear()
        check("a 404 beat takes a new lease (wake) and balances it (done)", wait_until(lambda: gate.paths("/wake") and gate.paths("/done")), True)
    finally:
        s.cleanup()


def scenario_fallback_exit():
    print("-- fallback: the server exits without Resolve")
    gate = FakeGate()
    s = Session(gate, {"FAKE_NEEDS_RESOLVE": "{dir}/running"})
    try:
        r = s.init()
        check("initialize answered through the fallback, with the client's own id", (r or {}).get("id"), 0)
        check("fallback is logged clearly", "FALLBACK" in s.stderr_text(), True)
        check("Resolve started at connect", s.events(), ["start"])
        check("the connect-time /wake is balanced by a /done", wait_until(lambda: gate.paths("/wake", "/done") == ["/wake", "/done"]), True)
        s.call(1)
        check("a call works in fallback mode", (s.reply_to(1) or {}).get("result") is not None, True)
        # idle close, then a call: Resolve and the server child restart, the handshake is replayed and its answer swallowed
        gate.close = "idle"
        check("closed on request", wait_until(lambda: s.events() == ["start", "stop"]), True)
        gate.close = None
        s.call(2)
        check("call after the close works (new session, new child)", (s.reply_to(2) or {}).get("result") is not None, True)
        check("events: restarted", s.events(), ["start", "stop", "start"])
        log = s.recv_log()
        replays = [l for l in log if b"resolve-session-replay" in l]
        check("handshake replayed to the new child under a private id", len(replays), 1)
        check("the replay's answer never reached the client", any(b"resolve-session-replay" in l for l in s.lines), False)
        check("initialized replayed after it", any(b"notifications/initialized" in l for l in log[log.index(replays[0]):]), True)
    finally:
        s.cleanup()


def scenario_fallback_probe():
    print("-- fallback: the server does not answer initialize without Resolve")
    gate = FakeGate()
    s = Session(gate, {"FAKE_SILENT_INIT": "{dir}/running"})
    try:
        s.send({"jsonrpc": "2.0", "id": "init-x", "method": "initialize", "params": {}})
        r = s.reply_to("init-x", timeout=15)
        check("initialize answered after the probe time, with the client's own id", bool(r) and "result" in r, True)
        check("probe fallback is logged", "FALLBACK" in s.stderr_text() and "no answer to initialize" in s.stderr_text(), True)
        check("Resolve started at connect", s.events(), ["start"])
    finally:
        s.cleanup()


def scenario_fallback_refused():
    print("-- fallback with the gate refusing: the process stays alive and initialize can be retried")
    # the server hangs on initialize (probe path): deterministic, the initialize is already waiting when the fallback runs
    gate = FakeGate()
    gate.wake_replies.append((409, {"why": "busy"}))
    s = Session(gate, {"FAKE_SILENT_INIT": "{dir}/running"})
    try:
        s.send({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        r = s.reply_to(0, timeout=15)
        check("fallback refused by the gate: initialize gets the reason", is_error(r, "busy with another task"), True)
        time.sleep(0.5)
        check("the process stays alive", s.proc.poll(), None)
        check("nothing started", s.events(), [])
        s.call(5)
        check("a call while there is no server answers with an error, takes no lease", (
            bool((s.reply_to(5) or {}).get("error")), gate.paths("/wake")), (True, ["/wake"]))
        s.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        r = s.reply_to(1, timeout=15)
        check("initialize again: the gate grants, answered with the client's own id", bool(r) and "result" in r, True)
        check("Resolve started by the retry", s.events(), ["start"])
        check("still one process, exit code unset", s.proc.poll(), None)
    finally:
        s.cleanup()

    # the server exits without Resolve: whichever side of the initialize the refusal lands on, the process lives and a retry works
    gate = FakeGate()
    gate.wake_replies.append((409, {"why": "busy"}))
    s = Session(gate, {"FAKE_NEEDS_RESOLVE": "{dir}/running"})
    try:
        s.send({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        r = s.reply_to(0, timeout=5)
        if r is not None and "error" in r:
            check("exit variant: initialize gets the reason", is_error(r, "busy with another task"), True)
            s.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            r = s.reply_to(1, timeout=15)
        check("exit variant: initialize answered after the retry", bool(r) and "result" in r, True)
        check("exit variant: the process stays alive", s.proc.poll(), None)
        check("exit variant: started once", s.events(), ["start"])
    finally:
        s.cleanup()


def scenario_bench_env():
    print("-- RESOLVE_GATE_BENCH: on /wake only, validated")
    gate = FakeGate(); s = Session(gate, {"RESOLVE_GATE_BENCH": "run-1.A:b_2"})
    try:
        s.init()
        s.set("rendering", "1")
        s.call(1)
        check("call answered in a bench run", (s.reply_to(1) or {}).get("result") is not None, True)
        wakes = gate.bodies("/wake")
        check("/wake carries the bench id", wakes, [{"port": 8695, "stack": "selftest-stack", "mode": "interactive", "bench": "run-1.A:b_2"}])
        wait_until(lambda: len(gate.paths("/beat")) >= 1)
        s.close()
        others = [b for pth in ("/beat", "/done", "/release", "/down") for b in gate.bodies(pth)]
        check("no bench field on beat, done, release, down", ["bench" in b for b in others], [False] * len(others))
        check("those paths were really called", sorted(set(gate.paths("/beat", "/done", "/release", "/down"))), ["/beat", "/done", "/down", "/release"])
    finally:
        s.cleanup()

    gate = FakeGate(); s = Session(gate)
    try:
        s.init(); s.call(1); s.reply_to(1)
        check("no bench env: no bench field", gate.bodies("/wake"), [{"port": 8695, "stack": "selftest-stack", "mode": "interactive"}])
    finally:
        s.cleanup()

    gate = FakeGate(); s = Session(gate, {"RESOLVE_GATE_BENCH": "bad id/../x"})
    try:
        rc = s.proc.wait(timeout=10)
        wait_until(lambda: "RESOLVE_GATE_BENCH" in s.stderr_text())
        check("an invalid bench id ends the process", (rc != 0, "RESOLVE_GATE_BENCH" in s.stderr_text()), (True, True))
        check("and nothing reached the gate", gate.paths(), [])
    finally:
        s.cleanup()


def scenario_go_rules():
    print("-- start only on go:true (or Resolve already up); otherwise give the call back and wake again")
    gate = FakeGate(); s = Session(gate)
    try:
        s.init()
        # the gate says "running" but our Resolve is gone, then gives a go
        gate.wake_replies.append((200, {"lease": "L1", "running": True, "eta_s": 0}))
        s.call(1)
        check("running + process gone: the call still runs after a re-wake", (s.reply_to(1) or {}).get("result") is not None, True)
        check("started once, only after the go", s.events(), ["start"])
        check("two wakes", len(gate.bodies("/wake")), 2)
        check("the first wake was given back before the second", gate.paths("/wake", "/done")[:3], ["/wake", "/done", "/wake"])
        check("every wake balanced by a done", wait_until(lambda: len(gate.bodies("/done")) == 2), True)
    finally:
        s.cleanup()

    # never a go: 3 tries, no start, an error
    gate = FakeGate(); s = Session(gate)
    try:
        s.init()
        gate.wake_replies += [(200, {"lease": "L1", "running": True, "eta_s": 0}), (202, {"lease": "L1", "running": False, "eta_s": 5}),
                              (202, {"lease": "L1", "running": False, "eta_s": 5, "go": False})]
        s.call(1)
        r = s.reply_to(1)
        check("no go in 3 tries -> error", is_error(r, "did not grant a start"), True)
        check("never started", s.events(), [])
        check("3 wakes, 3 dones", (len(gate.bodies("/wake")), wait_until(lambda: len(gate.bodies("/done")) == 3)), (3, True))
        check("nothing reached the server", [l for l in s.recv_log() if b"tools/call" in l], [])
    finally:
        s.cleanup()

    # go:true on a 200 is not a go: only 202 grants a start
    gate = FakeGate(); s = Session(gate)
    try:
        s.init()
        gate.wake_replies.append((200, {"lease": "L1", "running": True, "eta_s": 0, "go": True}))
        s.call(1)
        r = s.reply_to(1)
        check("go on a 200 does not start; re-woken and started on the real go", ((r or {}).get("result") is not None, s.events(), len(gate.bodies("/wake"))), (True, ["start"], 2))
    finally:
        s.cleanup()

    # Resolve already up on our display and a reply without go: no start, the call is forwarded
    gate = FakeGate(); s = Session(gate)
    try:
        s.init()
        s.set("running", "")
        gate.wake_replies.append((202, {"lease": "L1", "running": False, "eta_s": 5}))
        s.call(1)
        check("Resolve already up, no go: forwarded, not started", ((s.reply_to(1) or {}).get("result") is not None, s.events(), len(gate.bodies("/wake"))), (True, [], 1))
    finally:
        s.cleanup()


def scenario_acquire_failures():
    print("-- an exception after a granted wake gives the call back")
    gate = FakeGate(); s = Session(gate)
    try:
        s.init()
        s.set("raise", "")
        s.call(1)
        r = s.reply_to(1)
        check("a backend exception answers the call with an error", is_error(r, "internal error"), True)
        check("the lease's call was given back", wait_until(lambda: gate.paths("/wake", "/done") == ["/wake", "/done"]), True)
        os.unlink(os.path.join(s.dir, "raise"))
        s.call(2)
        check("the next call works", ((s.reply_to(2) or {}).get("result") is not None, s.events()), (True, ["start"]))
    finally:
        s.cleanup()

    # the session lock cannot be taken (its path is a directory)
    gate = FakeGate(); s = Session(gate)
    try:
        s.init()
        os.makedirs(os.path.join(s.dir, "state", "resolve_xvfb_99.lock"))
        s.call(1)
        check("a lock failure answers the call with an error", is_error(s.reply_to(1), "internal error"), True)
        check("a lock failure gives the call back", wait_until(lambda: gate.paths("/wake", "/done") == ["/wake", "/done"]), True)
        check("nothing started", s.events(), [])
    finally:
        s.cleanup()


def scenario_wake_timeout():
    print("-- a wake that times out releases the stack")
    gate = FakeGate(); gate.wake_delay = 2.5
    s = Session(gate, {"RESOLVE_SESSION_WAKE_TIMEOUT_S": "1"})
    try:
        s.init()
        s.call(1)
        r = s.reply_to(1, timeout=10)
        check("timeout -> error naming it", is_error(r, "did not answer"), True)
        check("POST /off for the stack and port", wait_until(lambda: gate.bodies("/off") == [{"stack": "selftest-stack", "port": 8695}]), True)
        check("nothing started, nothing forwarded", (s.events(), [l for l in s.recv_log() if b"tools/call" in l]), ([], []))
        check("no /done for a wake that never answered", gate.paths("/done"), [])
    finally:
        s.cleanup()


def scenario_defaults():
    print("-- defaults")
    env = {k: v for k, v in os.environ.items() if not k.startswith("RESOLVE_")}
    code = ("import importlib.util,sys\n"
            "spec=importlib.util.spec_from_file_location('rs', %r)\nm=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(m)\n"
            "sys.__stdout__.write('%%s %%s' %% (m.PROBE_S, m.WAKE_TIMEOUT_S))") % SESSION
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env).stdout
    check("probe 60 s, wake timeout 200 s", out, "60.0 200.0")


def scenario_dispatch():
    print("-- mcp_dispatch.sh picks the vendored wrapper")
    root = tempfile.mkdtemp(prefix="rs_disp_")
    try:
        os.makedirs(os.path.join(root, "resolve_mcp"))
        shutil.copy(os.path.join(HERE, "..", "mcp_dispatch.sh"), root)
        stub = os.path.join(root, "resolve_mcp", "resolve_mcp_wrapper.sh")
        open(stub, "w").write('#!/bin/sh\necho "vendored $*"\n')
        os.chmod(stub, 0o755)
        other = os.path.join(root, "old_wrapper.sh")
        open(other, "w").write('#!/bin/sh\necho "old $*"\n')
        os.chmod(other, 0o755)

        def run(cmd, **env):
            e = {k: v for k, v in os.environ.items() if not k.startswith("RESOLVE_MCP") and k != "GPU_HOST_DIR"}
            e.update(env, SSH_ORIGINAL_COMMAND=cmd)
            return subprocess.run(["bash", os.path.join(root, "mcp_dispatch.sh")], env=e, capture_output=True, text=True).stdout.strip()
        check("davinci -> vendored nogui", run("davinci"), "vendored nogui")
        check("anything else -> vendored nogui", run("whatever"), "vendored nogui")
        check("davinci-native -> vendored native-nogui", run("davinci-native"), "vendored native-nogui")
        check("RESOLVE_MCP_WRAPPER restores the old wrapper", run("davinci", RESOLVE_MCP_WRAPPER=other), "old nogui")
        check("backend override still passed", run("davinci", RESOLVE_MCP_BACKEND="xvfb", RESOLVE_MCP_WRAPPER=other), "old xvfb")
        check("GPU_HOST_DIR finds the wrapper for a copy elsewhere",
              run("davinci", GPU_HOST_DIR=root), "vendored nogui")
        wrapper = os.path.join(HERE, "resolve_mcp_wrapper.sh")
        check("wrapper refuses a GUI backend", subprocess.run(["bash", wrapper, "xvfb"], capture_output=True, text=True,
                                                              env=dict(os.environ, RESOLVE_MCP_COMMUNITY_REPO=root)).returncode, 2)
        check("wrapper and dispatcher parse", [subprocess.run(["bash", "-n", p]).returncode for p in (wrapper, os.path.join(HERE, "..", "mcp_dispatch.sh"))], [0, 0])
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    for fn in (scenario_lazy_start_and_calls, scenario_refusals, scenario_close_rules, scenario_beat_404,
               scenario_fallback_exit, scenario_fallback_probe, scenario_fallback_refused, scenario_bench_env, scenario_go_rules,
               scenario_acquire_failures, scenario_wake_timeout, scenario_defaults, scenario_dispatch):
        fn()
    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED: {FAIL}")
        sys.exit(1)
    print("all resolve_session checks passed")
