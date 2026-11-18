#!/usr/bin/env python3
"""Lazy, gate-leased DaVinci Resolve for a stdio MCP server (the successor of ops/resolve_host/resolve_xvfb_stdio.py).

  resolve_session.py <repo> -- <server command...>      (<repo> = the community server's checkout, which holds the
                                                          helper modules resolve_headless and src.utils.resolve_runtime)

Why: the old launcher started Xvfb and Resolve when the MCP client CONNECTED and kept them for the whole connection, so an
idle Hermes stack held the GPU for hours and no other GPU task could be placed. Every GPU use on this host now goes through
the gate (gpu-host/gate) with a lease, so Resolve is one more gate task ("resolve", pseudo-port 8695, not a container):

  * The MCP server child starts at once, WITHOUT Resolve, and every line is proxied unchanged in both directions
    (initialize, tools/list, notifications, server-initiated requests, ids of any type). The community server answers
    initialize and tools/list without Resolve. If a backend does not (the child EXITS before it answers initialize, or does
    not answer within RESOLVE_SESSION_PROBE_S, default 60), that backend falls back to the old way: lease and session at
    connect, child started after it, and a child restart (with the initialize handshake replayed) after every later session
    restart. It is logged. A gate refusal in the fallback answers that initialize with an error naming the reason and keeps
    the process alive: the client can send initialize again (retry or reconnect) and the lease is tried again.
  * The first tools/call or resources/read takes a gate lease (POST /wake, port 8695, stack RESOLVE_GATE_STACK). A refusal
    (409: vr, busy, vram, exclusive, bench) or an unreachable gate answers THAT request with a JSON-RPC error -32000 and
    nothing is started or forwarded: the GPU is never used outside the gate. Xvfb and Resolve are started ONLY when the
    wake reply is 202 with go:true (or Resolve on our display is already up); after a reply without go and with Resolve down
    the call is given back (/done) and woken again, up to 3 tries. Then the call is forwarded. Each call is one /wake before
    it and one /done when its response comes back (also when anything fails after the wake). A wake that times out (the gate
    may be evicting another task) sends POST /off for the stack, so a grant it finished later is not left holding the GPU.
    RESOLVE_GATE_BENCH=<id> adds "bench": id to every /wake, for a power measurement run (bench_gate.py).
  * While calls are in flight or Resolve is rendering, a beat every RESOLVE_GATE_BEAT_S (10 s) keeps the run alive
    (POST /beat). While idle it only polls GET /state: a beat would count as activity and the gate's idle timer would never
    run out. The gate never kills Resolve: when it asks to close (services.resolve.close), this process leaves the set of
    processes "using" Resolve (idle: no call in flight and project.IsRenderingInProgress() is False; if the API cannot
    tell, it stays). The last one out Quits Resolve (the old shutdown path), stops the Xvfb, reaps an orphan idle Xvfb, and
    reports POST /down. The next call re-acquires and starts Resolve again: the open project is lost, which is logged.
  * Ownership: this machinery quits ONLY a Resolve / Xvfb it started itself. When it starts one (or launches Resolve on an
    idle Xvfb it adopts for that), it records the process identities (pid + start time) and the start moment in
    resolve_xvfb_99.owned. At the last user's exit or the gate's close it quits only what that record covers; a Resolve found
    on :99 that it did not start (for example one the old eager launcher started, whose clients are not in this session's user
    set) is USED when a tool call arrives, but never quit, never reported to the gate as down, and its display is never
    stopped. A client that never made a Resolve tool call never quits anything (clean-up only unregisters it).
  * Safety rules kept from the old launcher: a Resolve on any other display (a person's session) is refused and never
    touched; the session is shared and counted between the davinci and davinci-native clients under one flock; shutdown
    order is Quit, forced Quit, wait for the process to leave, then the Xvfb; boot timeout RESOLVE_XVFB_BOOT_TIMEOUT.
  * Two registries in RESOLVE_STATE_DIR (default /tmp): resolve_xvfb_99.clients (connected) and resolve_xvfb_99.using
    (has a lease and uses Resolve). Only "using" decides who is the last one out. resolve_xvfb_99.owned (see
    Ownership) says whether what is running is ours to quit.
  * stdout is the MCP channel; status chatter goes to stderr. The gate token comes from GATE_TOKEN or from host.env
    (GATE_HOST_ENV, default gpu-host/host.env), parsed like gate.py does, never sourced and never printed.

Gate: GATE_URL or http://127.0.0.1:GATE_PORT (8700); GATE_PORT_RESOLVE (8695). Test seam: RESOLVE_SESSION_HOOKS names a
python file with ensure_session() -> (code, started), shutdown(), is_rendering() and resolve_running() and, optionally,
procs() -> [(kind "resolve"|"xvfb", token, started_s)] (identities for the ownership record; default: one "hook" Resolve
while resolve_running()), used instead of the real Resolve helpers (resolve_session_selftest.py). Never set it in production.
"""
import fcntl, importlib.util, json, os, re, signal, subprocess, sys, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.stdout.buffer          # the MCP channel, bytes: lines pass through exactly as they came
sys.stdout = sys.stderr          # whatever the helper modules print must not reach the MCP channel

DISPLAY = os.environ.get("RESOLVE_XVFB_DISPLAY", ":99")
SIZE = os.environ.get("RESOLVE_XVFB_SIZE", "1920x1080x24")
BOOT_TIMEOUT = float(os.environ.get("RESOLVE_XVFB_BOOT_TIMEOUT", "120"))
NOGUI = os.environ.get("RESOLVE_XVFB_NOGUI", "") == "1"
TAG = DISPLAY.lstrip(":")
STATE = os.environ.get("RESOLVE_STATE_DIR", "/tmp")
LOCK_PATH = f"{STATE}/resolve_xvfb_{TAG}.lock"
CLIENTS = f"{STATE}/resolve_xvfb_{TAG}.clients"     # connected
USING = f"{STATE}/resolve_xvfb_{TAG}.using"         # holds a lease and uses Resolve
OWNED = f"{STATE}/resolve_xvfb_{TAG}.owned"         # identities of the Resolve / Xvfb THIS machinery started
BEAT_S = float(os.environ.get("RESOLVE_GATE_BEAT_S", "10"))
PROBE_S = float(os.environ.get("RESOLVE_SESSION_PROBE_S", "60"))
CALL_MAX_S = float(os.environ.get("RESOLVE_SESSION_CALL_MAX_S", "1800"))   # the gate's INFLIGHT_MAX_S: a call that never answers
CANCEL_GRACE_S = float(os.environ.get("RESOLVE_SESSION_CANCEL_GRACE_S", "30"))
WAKE_TIMEOUT_S = float(os.environ.get("RESOLVE_SESSION_WAKE_TIMEOUT_S", "200"))   # a wake may wait for the gate to evict another task
WAKE_TRIES = 3                   # wakes per call when the gate says "running" or gives no go but Resolve is not up
REWAKE_S = float(os.environ.get("RESOLVE_SESSION_REWAKE_S", "1"))
NO_GO = -1                       # ensure_session: the gate did not let us start and Resolve is not up
BENCH_RE = re.compile(r"[A-Za-z0-9._:-]{1,64}")
GATED = ("tools/call", "resources/read")
SERVICE = "resolve"

NOT_RUNNING = "the Resolve MCP server is not running (its start was refused or it ended): send initialize again to retry"

WHY = {
    "vr": "a person's own DaVinci Resolve session is open on the GPU host",
    "busy": "the GPU is busy with another task",
    "vram": "there is not enough free GPU memory",
    "exclusive": "the GPU is busy with another task (exclusive)",
    "bench": "the GPU is reserved for a power measurement",
}


def log(msg):
    print(f"[resolve_session] {msg}", file=sys.stderr, flush=True)


def id_key(rid):
    """A JSON-RPC id of any type as a dict key (1 and "1" differ)."""
    return json.dumps(rid, sort_keys=True)


def parse(line):
    try:
        return json.loads(line)
    except ValueError:
        return None


def with_nl(line):
    return line if line.endswith(b"\n") else line + b"\n"


# ---------------------------------------------------------------- registries and the session lock

class Lock:
    """One at a time through the start and the stop of the shared session (all processes, davinci and davinci-native)."""
    def __enter__(self):
        os.makedirs(STATE, exist_ok=True)
        self.f = open(LOCK_PATH, "a")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def register(d):
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, str(os.getpid())), "w").close()


def unregister(d):
    try:
        os.unlink(os.path.join(d, str(os.getpid())))
    except OSError:
        pass


def live(d):
    alive = []
    try:
        names = os.listdir(d)
    except OSError:
        return alive
    for n in names:
        if not n.isdigit():
            continue
        try:
            os.kill(int(n), 0)
            alive.append(int(n))
        except ProcessLookupError:
            try:
                os.unlink(os.path.join(d, n))   # died without cleaning up
            except OSError:
                pass
        except PermissionError:
            alive.append(int(n))
    return alive


def pgrep(pattern):
    out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, check=False)
    return [int(p) for p in out.stdout.split() if p.isdigit()]


def resolve_pids():
    # not `pgrep -x resolve`: once Qt is up the process renames its main thread to "GUI Thread" and -x stops matching
    return pgrep("^/opt/resolve/bin/resolve( |$)")


def xvfb_pids():
    return pgrep(f"^Xvfb {DISPLAY} ")


def display_of(pid):
    try:
        for kv in open(f"/proc/{pid}/environ", "rb").read().split(b"\0"):
            if kv.startswith(b"DISPLAY="):
                return kv[8:].decode()
    except OSError:
        pass
    return None


def xvfb_socket():
    return os.path.exists("/tmp/.X11-unix/X" + TAG)


def boot_now():
    """Seconds since boot, the clock /proc/<pid>/stat start times are on."""
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def proc_start(pid):
    """Start time of a process in seconds since boot, or None."""
    try:
        raw = open(f"/proc/{pid}/stat", "rb").read().decode("utf-8", "replace")
        fields = raw[raw.rindex(")") + 2:].split()      # after "pid (comm)": field 3 is index 0, starttime is field 22
        return int(fields[19]) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None


def proc_token(pid):
    """pid plus start time: a reused pid is not the same process."""
    st = proc_start(pid)
    return None if st is None else f"{pid}:{int(st * 1000)}"


def load_owned():
    """{"t0": float, "tokens": [str]} written by whoever started what runs now; empty when there is no record."""
    try:
        rec = json.load(open(OWNED))
        if isinstance(rec, dict) and isinstance(rec.get("tokens"), list) and isinstance(rec.get("t0"), (int, float)):
            return {"t0": float(rec["t0"]), "tokens": [str(t) for t in rec["tokens"]]}
    except (OSError, ValueError):
        pass
    return {"t0": 0.0, "tokens": []}


def save_owned(rec):
    """Under the session lock. An empty record removes the file."""
    if not rec["tokens"]:
        try:
            os.unlink(OWNED)
        except OSError:
            pass
        return
    tmp = f"{OWNED}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, OWNED)


def record_owned(t0, launched, alive):
    """Under the session lock: add what this machinery just started or adopted to the record (older tokens that are still
    alive stay: another process of this machinery may have started them)."""
    old = load_owned()
    keep = [t for t in old["tokens"] if t in alive]
    tokens = sorted(set(keep) | set(launched))
    save_owned({"t0": min(old["t0"], t0) if keep else t0, "tokens": tokens})


def is_ours(procs, rec):
    """Do the running Resolve / Xvfb on our display belong to this machinery? procs = [(kind, token, started_s)].
    Resolve up: ours only when one of its processes is in the record and every other one is newer than the record's start
    (a re-exec or helper of ours), so a Resolve that was already there, or one started after ours died, is not.
    No Resolve: the display is ours only when its Xvfb is in the record. Nothing running: nothing to quit."""
    resolve = [(t, st) for k, t, st in procs if k == "resolve"]
    if resolve:
        return any(t in rec["tokens"] for t, _ in resolve) and all(t in rec["tokens"] or st >= rec["t0"] for t, st in resolve)
    return any(k == "xvfb" and t in rec["tokens"] for k, t, _ in procs)


def kill_all(pids, sig):
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


# ---------------------------------------------------------------- the real Resolve (same code as resolve_xvfb_stdio.py)

class RealBackend:
    def __init__(self, repo):
        os.environ.setdefault("RESOLVE_SCRIPT_API", "/opt/resolve/Developer/Scripting")
        os.environ.setdefault("RESOLVE_SCRIPT_LIB", "/opt/resolve/libs/Fusion/fusionscript.so")
        modules = "/opt/resolve/Developer/Scripting/Modules/"
        os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH", "") + (":" if os.environ.get("PYTHONPATH") else "") + modules
        sys.path.append(modules)
        sys.path.insert(0, f"{repo}/scripts")
        global rh, rr
        import resolve_headless as rh  # noqa: E402
        from src.utils import resolve_runtime as rr  # noqa: E402

    def child_env(self):
        env = rh.scripting_env()
        env["DISPLAY"] = DISPLAY
        env.pop("XAUTHORITY", None)
        return env

    def resolve_running(self):
        return bool(resolve_pids())

    def procs(self):
        """Identities of the Resolve and Xvfb on OUR display: [(kind, token, started_s)]."""
        out = []
        for kind, pids in (("resolve", [p for p in resolve_pids() if display_of(p) == DISPLAY]), ("xvfb", xvfb_pids())):
            for p in pids:
                tok, st = proc_token(p), proc_start(p)
                if tok is not None and st is not None:
                    out.append((kind, tok, st))
        return out

    def up_here(self):
        """Resolve is up on OUR display (one on another display is a person's, not ours)."""
        return any(display_of(p) == DISPLAY for p in resolve_pids())

    def is_rendering(self):
        """True / False, or None when the scripting API cannot tell (then nobody closes anything)."""
        try:
            resolve = rh._connect()
            if resolve is None:
                return None
            project = resolve.GetProjectManager().GetCurrentProject()
            if project is None:
                return False
            return bool(project.IsRenderingInProgress())
        except Exception:
            return None

    def ensure_session(self):
        """Under the lock: leave Resolve scriptable on our display. (0, started) = ready, else (exit code, False).
        self.launched = identities of what this call started or adopted (for the ownership record), even on a failure."""
        self.launched = []
        pids = resolve_pids()
        if pids:
            other = [p for p in pids if display_of(p) != DISPLAY]
            if other:
                log(f"REFUSE: Resolve (pid {other[0]}) is running on display {display_of(other[0])}, not {DISPLAY}: "
                    "that is a person's session; quit it first or use another backend.")
                return 1, False
            if rh.wait_until_scriptable(BOOT_TIMEOUT) is None:
                log("FAILED: the Resolve in the virtual display does not answer")
                return 4, False
            log("reusing the Resolve already running in the virtual display")
            return 0, False
        if not xvfb_pids():
            if xvfb_socket():
                log(f"FAILED: {DISPLAY} is taken by something that is not our Xvfb")
                return 3, False
            subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", SIZE, "+extension", "GLX", "+render", "-noreset"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            for _ in range(50):
                if xvfb_socket():
                    break
                time.sleep(0.1)
            else:
                log("FAILED: Xvfb did not come up")
                return 3, False
            self.launched += [t for k, t, _ in self.procs() if k == "xvfb"]
        else:
            log("adopting the idle Xvfb left on " + DISPLAY + " (Resolve is launched on it next, so it is ours from here on)")
            self.launched += [t for k, t, _ in self.procs() if k == "xvfb"]
        command = rr.launch_command(headless=NOGUI)
        if not command:
            log("REFUSE: no DaVinci Resolve install found")
            return 3, False
        env = self.child_env()
        log("starting " + " ".join(command) + f" on {DISPLAY}")
        t0 = time.monotonic()
        proc = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        if rh.wait_until_scriptable(BOOT_TIMEOUT) is None:
            log(f"FAILED: not scriptable after {BOOT_TIMEOUT:.0f}s; cleaning up")
            rh._kill_process(proc)
            # Resolve re-execs: what we spawned may not be the process that stayed. Only ours (on our display): a person may
            # have started their own Resolve on another display meanwhile.
            kill_all([p for p in resolve_pids() if display_of(p) == DISPLAY], signal.SIGKILL)
            kill_all(xvfb_pids(), signal.SIGTERM)
            return 4, False
        log(f"ready in {time.monotonic() - t0:.1f}s")
        self.launched += [t for _, t, _ in self.procs()]
        return 0, True

    def shutdown(self):
        """Under the lock, when no process uses Resolve AND the ownership check passed (Proxy.stop_if_ours): Quit it, then
        stop the display. Never called for a Resolve or Xvfb this machinery did not start."""
        if any(display_of(p) != DISPLAY for p in resolve_pids()):
            return   # a person's own Resolve is up (we refused it): never quit it
        if resolve_pids():
            if rh.stop(30.0) != 0:
                rh.stop(20.0, force=True)
            for _ in range(60):   # never pull the display from under a Resolve that is still leaving
                if not resolve_pids():
                    break
                time.sleep(0.5)
        if not resolve_pids():
            kill_all(xvfb_pids(), signal.SIGTERM)


class HookBackend:
    """The test seam: the same four functions, from a python file."""
    def __init__(self, path):
        spec = importlib.util.spec_from_file_location("resolve_session_hooks", path)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.shutdown = self.m.shutdown
        self.is_rendering, self.resolve_running = self.m.is_rendering, self.m.resolve_running
        self.up_here = self.m.resolve_running
        self.launched = []

    def ensure_session(self):
        self.launched = []
        code, started = self.m.ensure_session()
        if started:
            self.launched = [t for _, t, _ in self.procs()]
        return code, started

    def procs(self):
        if hasattr(self.m, "procs"):
            return list(self.m.procs())
        return [("resolve", "hook", 0.0)] if self.m.resolve_running() else []

    def child_env(self):
        env = dict(os.environ)
        env["DISPLAY"] = DISPLAY
        return env


# ---------------------------------------------------------------- the gate

class GateError(Exception):
    """The gate cannot be asked: the message is for the MCP client."""


class GateTimeout(GateError):
    """The gate was reached but did not answer in time (a grant may still have been made)."""


def parse_env_file(path):
    """Same parse as gate.py: KEY=VALUE lines, optional `export `, optional quotes, never sourced."""
    out = {}
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        k, sep, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
            continue
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k] = v
    return out


class Gate:
    def __init__(self):
        vals = parse_env_file(os.environ.get("GATE_HOST_ENV") or os.path.join(HERE, "..", "host.env"))

        def get(key, default=None):
            return os.environ.get(key) or vals.get(key) or default
        self.token = get("GATE_TOKEN")
        self.url = os.environ.get("GATE_URL") or "http://127.0.0.1:%s" % get("GATE_PORT", "8700")
        self.port = int(get("GATE_PORT_RESOLVE", "8695"))
        self.stack = os.environ.get("RESOLVE_GATE_STACK") or "resolve-mcp"
        self.bench = os.environ.get("RESOLVE_GATE_BENCH") or None
        if self.bench is not None and not BENCH_RE.fullmatch(self.bench):
            sys.exit("RESOLVE_GATE_BENCH must match [A-Za-z0-9._:-]{1,64}")

    def call(self, method, path, body=None, timeout=10.0):
        """(status, dict). GateError when the gate cannot be reached or there is no token."""
        if not self.token:
            raise GateError("the GPU gate token was not found on the host: Resolve was not started (the GPU is never used outside the gate)")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        except (urllib.error.URLError, OSError, ValueError) as e:
            reason = getattr(e, "reason", e)
            if isinstance(e, TimeoutError) or isinstance(reason, TimeoutError):
                raise GateTimeout(f"the GPU gate did not answer in {timeout:g} s: Resolve was not started; try again later")
            raise GateError("the GPU gate is not reachable: Resolve was not started (the GPU is never used outside the gate); try again later")
        try:
            reply = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            reply = {}
        return status, reply if isinstance(reply, dict) else {}


def refusal(why):
    return f"{WHY.get(why) or 'the GPU gate refused the request (%s)' % why}; try again later"


# ---------------------------------------------------------------- the proxy

class Child:
    def __init__(self, proc):
        self.proc = proc
        self.retired = False


class Proxy:
    def __init__(self, argv, backend, gate):
        self.argv, self.backend, self.gate = argv, backend, gate
        self.st = threading.RLock()        # the fields below
        self.phase = threading.Lock()      # one acquire or one leave at a time
        self.out_lock = threading.Lock()
        self.child_lock = threading.Lock()
        self.child = None
        self.child_ready = threading.Event()
        self.stop = threading.Event()
        self.exit_code = 0
        self.lease = None
        self.using = False                 # in the USING registry
        self.had_session = False           # this process has used Resolve before: a fresh start loses the project
        self.inflight = {}                 # key -> {"id", "t", "cancelled"}: forwarded calls whose response is not back
        self.gating = {}                   # key -> {"cancelled"}: calls waiting for the lease or the session
        self.acquiring = 0
        self.fallback = False
        self.needs_fallback = False        # a fallback start was refused: the next initialize tries it again
        self.init_line = None
        self.init_key = None
        self.init_answered = threading.Event()
        self.initialized_line = None
        self.swallow = {}                  # key of a replayed initialize -> Event
        self.replays = 0
        self._rend_thread = None

    # -- output to the client

    def emit(self, line):
        try:
            with self.out_lock:
                OUT.write(with_nl(line))
                OUT.flush()
        except (BrokenPipeError, OSError, ValueError):
            self.stop.set()                # the client is gone

    def emit_error(self, rid, message, code=-32000):
        self.emit(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}).encode())

    # -- the server child

    def start_child(self):
        proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=self.backend.child_env())
        c = Child(proc)
        with self.child_lock:
            self.child = c
        threading.Thread(target=self.read_child, args=(c,), daemon=True).start()
        return c

    def retire_child(self):
        with self.child_lock:
            c, self.child = self.child, None
        if c is None:
            return
        c.retired = True
        try:
            c.proc.stdin.close()               # EOF first: a filter in between passes it on to the server it started
        except OSError:
            pass
        for step in (None, c.proc.terminate, c.proc.kill):
            if step:
                step()
            try:
                c.proc.wait(timeout=4)
                return
            except subprocess.TimeoutExpired:
                pass

    def write_child(self, c, line):
        try:
            c.proc.stdin.write(with_nl(line))
            c.proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError, ValueError):
            return False

    def forward(self, line):
        """To the server. Waits while the child is being restarted. False when it cannot be delivered."""
        while not self.child_ready.wait(0.5):
            if self.stop.is_set():
                return False
        with self.child_lock:
            c = self.child
        return c is not None and not c.retired and self.write_child(c, line)

    def read_child(self, c):
        for line in c.proc.stdout:
            if c.retired:
                return
            self.on_server_line(line)
        if c.retired:
            return
        if not self.init_answered.is_set() and not self.fallback:
            threading.Thread(target=self.fallback_start, args=("the server exited before it answered initialize",), daemon=True).start()
            return
        self.exit_code = c.proc.wait()
        self.stop.set()

    def on_server_line(self, line):
        msg = parse(line)
        if isinstance(msg, dict) and "method" not in msg and "id" in msg and ("result" in msg or "error" in msg):
            key = id_key(msg["id"])
            with self.st:
                ev = self.swallow.pop(key, None)
            if ev is not None:                 # the answer to a replayed initialize: the client never asked for it
                ev.set()
                return
            if key == self.init_key:
                self.init_answered.set()
            with self.st:
                entry = self.inflight.pop(key, None)
            self.emit(line)
            if entry:
                self.gate_done()
            return
        self.emit(line)

    # -- the client

    def read_client(self):
        for line in sys.stdin.buffer:
            if line.strip():
                self.on_client_line(line)
        self.stop.set()                        # EOF: the client closed the session

    def on_client_line(self, line):
        msg = parse(line)
        if isinstance(msg, list):              # fail closed, like mcp_filter.py: a batch could hide a tools/call
            self.emit_error(None, "this connection does not accept batches", -32600)
            return
        if not isinstance(msg, dict):
            self.forward(line)
            return
        method, has_id = msg.get("method"), "id" in msg
        if method in GATED:
            if not has_id:
                log(f"dropped a {method} notification (no id: nothing could answer it)")
                return
            threading.Thread(target=self.handle_gated, args=(line, msg), daemon=True).start()
            return
        if method == "initialize" and has_id:
            self.init_line, self.init_key = line, id_key(msg["id"])
            if self.needs_fallback:            # there is no server child: the earlier start was refused, try again
                threading.Thread(target=self.fallback_start, args=("initialize again after a refused start",), daemon=True).start()
                return
            threading.Thread(target=self.probe, daemon=True).start()
        elif method == "notifications/initialized":
            self.initialized_line = line
        elif method == "notifications/cancelled":
            self.cancel(msg)
        if not self.forward(line) and has_id and method and not self.stop.is_set():
            self.emit_error(msg["id"], NOT_RUNNING)

    def cancel(self, msg):
        params = msg.get("params")
        if not isinstance(params, dict) or "requestId" not in params:
            return
        key = id_key(params["requestId"])
        with self.st:
            if key in self.gating:
                self.gating[key]["cancelled"] = True
            if key in self.inflight:
                self.inflight[key]["cancelled"] = time.monotonic()

    # -- gated calls

    def handle_gated(self, line, msg):
        key, rid = id_key(msg["id"]), msg["id"]
        if self.needs_fallback:                # no server to forward to: do not take the GPU for nothing
            self.emit_error(rid, NOT_RUNNING)
            return
        with self.st:
            self.acquiring += 1
            self.gating[key] = {"cancelled": False}
        ok, err = False, None
        try:
            with self.phase:
                if not self.gating[key]["cancelled"]:
                    err = self.acquire(restart_child=True)
                    ok = err is None
        except Exception as e:                 # a bug here must still answer the request
            err = f"internal error in the Resolve session layer: {e}"
        finally:
            with self.st:
                g = self.gating.pop(key, None)
                cancelled = bool(g and g["cancelled"])
                if ok and not cancelled:
                    self.inflight[key] = {"id": rid, "t": time.monotonic(), "cancelled": None}
                self.acquiring -= 1
        if err:
            self.emit_error(rid, err)
            return
        if cancelled:                          # the client withdrew it: no answer is expected
            if ok:
                self.gate_done()
            return
        if not self.forward(line):
            with self.st:
                self.inflight.pop(key, None)
            self.emit_error(rid, "the Resolve MCP server is not running")
            self.gate_done()

    def gate_post(self, path, body, timeout=10.0):
        try:
            return self.gate.call("POST", path, body, timeout)
        except GateError as e:
            log(f"{path}: {e}")
            return None, {}

    def gate_done(self):
        with self.st:
            lease = self.lease
        if lease:
            self.gate_post("/done", {"lease": lease})

    def wake(self):
        """POST /wake (counts one call in flight on the gate). (error message, None) or (None, reply with a clean "go")."""
        body = {"port": self.gate.port, "stack": self.gate.stack, "mode": "interactive"}
        if self.gate.bench:
            body["bench"] = self.gate.bench
        try:
            status, reply = self.gate.call("POST", "/wake", body, WAKE_TIMEOUT_S)
        except GateTimeout as e:
            # the gate may finish the grant after we gave up: end this stack's leases so nothing keeps the GPU
            self.gate_post("/off", {"stack": self.gate.stack, "port": self.gate.port})
            return str(e), None
        except GateError as e:
            return str(e), None
        if status == 409:
            return refusal(reply.get("why")), None
        if status not in (200, 202) or not reply.get("lease"):
            return f"the GPU gate refused the request (HTTP {status} {reply.get('why', '')})".replace(" )", ")"), None
        with self.st:
            self.lease = reply["lease"]
        reply["go"] = status == 202 and reply.get("go") is True
        return None, reply

    def acquire(self, restart_child):
        """With self.phase held: lease (one /wake), then Resolve up. None, or the error for the client. Resolve is started only
        on go:true; without it and with Resolve down the call is given back and woken again."""
        for attempt in range(WAKE_TRIES):
            err, reply = self.wake()
            if err:
                return err
            res = self.leased(reply["go"], restart_child)
            if res is not NO_GO:
                return res
            log(f"wake {attempt + 1}/{WAKE_TRIES}: the gate gave no go and Resolve is not up: not starting it")
            if attempt + 1 < WAKE_TRIES and self.stop.wait(REWAKE_S):
                return "the Resolve session is closing"
        return "the GPU gate did not grant a start for Resolve; try again later"

    def leased(self, go, restart_child):
        """After a successful wake: None (ready), an error message, or NO_GO. The lease's call is always given back on a failure."""
        released = False
        try:
            code, started = self.ensure_session(go)
            if code != 0:
                released = True
                self.gate_done()
                if code == NO_GO:
                    return NO_GO
                with self.st:
                    idle = not self.inflight
                if idle:
                    self.leave("start failed")
                return {1: "a person's own DaVinci Resolve session is open on the GPU host; try again later",
                        4: "DaVinci Resolve did not become scriptable in time; try again later"}.get(
                    code, f"DaVinci Resolve could not be started on the GPU host (code {code})")
            if started:
                if self.had_session:
                    log("session restarted: the open project was closed")
                if self.fallback and restart_child:
                    self.restart_child()
            self.had_session = True
            return None
        except BaseException:
            if not released:
                self.gate_done()
            raise

    def ensure_session(self, go):
        """(code, started). Registers this process as using Resolve before it starts, under the session lock. Without go and
        with Resolve down: (NO_GO, False), nothing registered or started."""
        if self.using and self.backend.up_here():
            return 0, False
        with Lock():
            if not go and not self.backend.up_here():
                return NO_GO, False
            if not self.using:
                register(USING)
                self.using = True
            t0 = boot_now()
            try:
                return self.backend.ensure_session()
            finally:                           # even a failed start may have left an Xvfb we spawned
                launched = list(getattr(self.backend, "launched", []))
                if launched:
                    record_owned(t0, launched, {t for _, t, _ in self.backend.procs()})

    def stop_if_ours(self):
        """Under the session lock, when no process uses Resolve: quit Resolve and stop the display, but only what this
        machinery started (the ownership record). A Resolve that was already running when we got here (the old eager
        launcher's) is left alone. True when Resolve is down afterwards (we quit it, or none was up on our display): the
        gate may be told so. False when a Resolve that is not ours is still up."""
        procs = self.backend.procs()
        if not procs:
            save_owned({"t0": 0.0, "tokens": []})
            return True
        if is_ours(procs, load_owned()):
            self.backend.shutdown()
            procs = self.backend.procs()
            if not procs:
                save_owned({"t0": 0.0, "tokens": []})
        else:
            log("not quitting what runs on " + DISPLAY + ": this session layer did not start it")
        return not any(k == "resolve" for k, _, _ in procs)

    def leave(self, reason):
        """Leave the set of processes using Resolve. The last one out quits it and reports /down. The lease is released."""
        with Lock():
            unregister(USING)
            self.using = False
            last = not live(USING)
            down = last and self.stop_if_ours()
        with self.st:
            lease, self.lease = self.lease, None
        if lease:
            if down:
                self.gate_post("/down", {"lease": lease})
            self.gate_post("/release", {"lease": lease, "close": False})
        log(f"left Resolve ({reason})" + ("; it was the last one: Resolve is down" if down else
                                          "; it was the last one, but Resolve is not ours: left running" if last else ""))

    # -- beat, idle close

    def beat_loop(self):
        while not self.stop.wait(BEAT_S):
            try:
                self.beat_once()
            except Exception as e:
                log(f"beat: {e}")

    def rendering(self):
        """True / False / None, with a time limit: a Resolve blocked by a modal can hang any API call."""
        if self._rend_thread is not None and self._rend_thread.is_alive():
            return None
        res = []

        def run():
            try:
                res.append(self.backend.is_rendering())
            except Exception:
                res.append(None)
        self._rend_thread = threading.Thread(target=run, daemon=True)
        self._rend_thread.start()
        self._rend_thread.join(15.0)
        return res[0] if res else None

    def reap_calls(self):
        """Drop calls that will never answer: cancelled ones after a grace time, and any past the gate's in-flight limit."""
        now, gone = time.monotonic(), 0
        with self.st:
            for key, e in list(self.inflight.items()):
                if (e["cancelled"] and now - e["cancelled"] > CANCEL_GRACE_S) or now - e["t"] > CALL_MAX_S:
                    del self.inflight[key]
                    gone += 1
        for _ in range(gone):
            self.gate_done()

    def beat_once(self):
        self.reap_calls()
        with self.st:
            using, lease, calls = self.using, self.lease, len(self.inflight) + self.acquiring
        if not using:
            return
        busy = calls > 0
        rendering = False if busy else self.rendering()
        if busy or rendering:
            if lease:
                status, _ = self.gate_post("/beat", {"lease": lease})
                if status == 404:
                    self.relink()
            return
        if rendering is None:                  # cannot tell whether a render runs: never close on a guess
            return
        try:
            status, body = self.gate.call("GET", "/state", None, 10.0)
        except GateError:
            return
        svc = (body.get("services") or {}).get(SERVICE) if isinstance(body.get("services"), dict) else None
        close = svc.get("close") if isinstance(svc, dict) else None
        if close:
            self.try_leave(close)

    def relink(self):
        """The gate forgot our lease (a release by another process on the same stack, a gate restart): take a new one and count
        the calls still in flight again, so their /done lines balance."""
        with self.st:
            self.lease = None
            n = len(self.inflight)
        for _ in range(max(1, n)):
            err, _ = self.wake()
            if err:
                log(f"lease lost and not renewed: {err}")
                return
        if not n:
            self.gate_done()

    def try_leave(self, reason):
        with self.phase:
            with self.st:
                if not self.using or self.inflight or self.acquiring:
                    return False
            if self.rendering() is not False:
                return False
            with self.st:
                if self.inflight or self.acquiring:
                    return False
            self.leave(f"the gate asked to close it: {reason}")
            return True

    # -- fallback: a server that cannot start without Resolve

    def probe(self):
        if not self.init_answered.wait(PROBE_S) and not self.stop.is_set() and not self.needs_fallback:
            self.fallback_start(f"no answer to initialize within {PROBE_S:g} s")

    def fallback_start(self, why):
        with self.st:
            if self.fallback:
                return
            self.fallback, self.needs_fallback = True, False
        log(f"FALLBACK: {why}. This backend needs Resolve to answer: starting the session at connect, as the old launcher did.")
        self.child_ready.clear()
        try:
            self.retire_child()
            with self.phase:
                try:
                    err = self.acquire(restart_child=False)
                except Exception as e:
                    err = f"internal error in the Resolve session layer: {e}"
                if err is None:
                    self.gate_done()            # the /wake counted a call, and this one is not a call
            if err:
                log(f"fallback: {err}")
                if self.init_line is not None and not self.init_answered.is_set():
                    msg = parse(self.init_line)
                    self.emit_error(msg.get("id") if isinstance(msg, dict) else None, err)
                with self.st:                   # stay alive: the client may send initialize again, which tries once more
                    self.fallback, self.needs_fallback = False, True
                return
            c = self.start_child()
            if self.init_line is not None and not self.init_answered.is_set():
                self.write_child(c, self.init_line)   # the client is still waiting for this one: its own id
        finally:
            self.child_ready.set()

    def restart_child(self):
        """Fallback backends only: a new server child after a new Resolve session, handshake replayed under a private id."""
        self.child_ready.clear()
        try:
            self.retire_child()
            with self.st:
                stale = list(self.inflight.values())
                self.inflight.clear()
            for e in stale:                    # their server is gone: no answer will come
                self.emit_error(e["id"], "the Resolve MCP server was restarted with a new Resolve session")
                self.gate_done()
            c = self.start_child()
            if self.init_line is None:
                return
            init = parse(self.init_line)
            self.replays += 1
            rid = f"resolve-session-replay-{self.replays}"
            ev = threading.Event()
            with self.st:
                self.swallow[id_key(rid)] = ev
            init["id"] = rid
            self.write_child(c, json.dumps(init).encode())
            if ev.wait(20.0) and self.initialized_line is not None:
                self.write_child(c, self.initialized_line)
        finally:
            self.child_ready.set()

    # -- run and clean up

    def run(self):
        self.child_ready.set()
        self.start_child()
        threading.Thread(target=self.read_client, daemon=True).start()
        threading.Thread(target=self.beat_loop, daemon=True).start()
        while not self.stop.wait(0.5):
            pass
        return self.exit_code

    def cleanup(self):
        log("closing")
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(sig, signal.SIG_IGN)   # a second signal must not cut the clean-up short
        _quiet()   # the client may be gone: any print to a closed pipe would abort the cleanup below
        self.stop.set()
        self.retire_child()
        unregister(CLIENTS)
        with self.st:
            using, lease = self.using, self.lease
        if using:
            self.leave("exit")
            return
        # never used Resolve (no tool call): quit nothing, whatever runs on the display belongs to someone else
        if lease:
            self.gate_post("/release", {"lease": lease, "close": False})


def _quiet():
    """Point stdout/stderr at /dev/null and ignore SIGPIPE, so cleanup survives a vanished client."""
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    null = os.open(os.devnull, os.O_WRONLY)
    for fd in (1, 2):
        try:
            os.dup2(null, fd)
        except OSError:
            pass
    sys.stdout = sys.stderr = open(os.devnull, "w")


def _terminate(signum, frame):
    raise SystemExit(128 + signum)   # so the clean-up runs (the client closing the session sends TERM/HUP)


def main():
    repo, *argv = sys.argv[1:] or [""]
    argv = [a for a in argv if a != "--"]
    if not repo or not argv:
        sys.exit("usage: resolve_session.py <repo> -- <server command...>")
    hooks = os.environ.get("RESOLVE_SESSION_HOOKS")
    backend = HookBackend(hooks) if hooks else RealBackend(repo)
    proxy = Proxy(argv, backend, Gate())
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, _terminate)
    register(CLIENTS)
    code = 1
    try:
        code = proxy.run()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    finally:
        proxy.cleanup()
    return code


if __name__ == "__main__":
    code = main()
    try:
        sys.stderr.flush()
    except (OSError, ValueError):
        pass
    os._exit(code)   # daemon threads may still be blocked on stdin: exiting normally could abort at interpreter shutdown
