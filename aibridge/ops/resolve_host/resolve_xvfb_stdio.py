#!/usr/bin/env python3
"""`resolve_headless.py run -- <cmd>`, but Resolve runs WITH its GUI inside a private Xvfb instead of `-nogui`.

Why: under `-nogui` LoadRenderPreset returns False and render calls hang; with a GUI (here an invisible one) the
render queue works (measured: 64 s of 1080p to H.264 in 4.2 s). The operator's own desktop is never touched.

Hermes keeps TWO Resolve MCP servers connected at once (the vendor ResolveMCP and the community davinci-resolve-mcp),
each started through this script, so the Resolve session is shared and counted:

  * every instance registers itself in a clients directory; the first one in starts Xvfb (:99, RESOLVE_XVFB_DISPLAY,
    RESOLVE_XVFB_SIZE) and Resolve and waits until it is scriptable (the others wait on the lock, then reuse it);
  * the LAST one out Quits Resolve (forced after the grace time: a GUI Quit can ask to save) and stops the Xvfb;
  * a Resolve running on any OTHER display (a person's own session) is refused, never touched;
  * on SIGTERM/SIGHUP/SIGINT, EOF or a vanished client (closed pipe) the clean-up still runs;
  * status chatter goes to stderr: stdout is the MCP JSON-RPC channel.

Usage: resolve_xvfb_stdio.py <repo> -- <server command...>      (<repo> = the community server's checkout)
"""
import fcntl, os, signal, subprocess, sys, time

repo, *argv = sys.argv[1:]
argv = [a for a in argv if a != "--"]
if not argv:
    sys.exit("usage: resolve_xvfb_stdio.py <repo> -- <command...>")
# the wrapper exports these; set them here too so the script also works when run by hand
os.environ.setdefault("RESOLVE_SCRIPT_API", "/opt/resolve/Developer/Scripting")
os.environ.setdefault("RESOLVE_SCRIPT_LIB", "/opt/resolve/libs/Fusion/fusionscript.so")
os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH", "") + (":" if os.environ.get("PYTHONPATH") else "") + "/opt/resolve/Developer/Scripting/Modules/"
sys.path.append("/opt/resolve/Developer/Scripting/Modules/")
sys.path.insert(0, f"{repo}/scripts")
import resolve_headless as rh  # noqa: E402
from src.utils import resolve_runtime as rr  # noqa: E402

sys.stdout = sys.stderr
DISPLAY = os.environ.get("RESOLVE_XVFB_DISPLAY", ":99")
SIZE = os.environ.get("RESOLVE_XVFB_SIZE", "1920x1080x24")
BOOT_TIMEOUT = float(os.environ.get("RESOLVE_XVFB_BOOT_TIMEOUT", "120"))
TAG = DISPLAY.lstrip(":")
LOCK_PATH = f"/tmp/resolve_xvfb_{TAG}.lock"
CLIENTS = f"/tmp/resolve_xvfb_{TAG}.clients"


def log(msg):
    print(f"[resolve_xvfb] {msg}", file=sys.stderr, flush=True)


class Lock:
    """One at a time through the start and the stop of the shared session."""
    def __enter__(self):
        self.f = open(LOCK_PATH, "a")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def register():
    os.makedirs(CLIENTS, exist_ok=True)
    open(os.path.join(CLIENTS, str(os.getpid())), "w").close()


def unregister():
    try:
        os.unlink(os.path.join(CLIENTS, str(os.getpid())))
    except OSError:
        pass


def live_clients():
    alive = []
    try:
        names = os.listdir(CLIENTS)
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
                os.unlink(os.path.join(CLIENTS, n))   # a client that died without cleaning up
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


def kill_all(pids, sig):
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def ensure_session():
    """Under the lock: leave Resolve scriptable on our display. 0 = ready, else an exit code."""
    pids = resolve_pids()
    if pids:
        other = [p for p in pids if display_of(p) != DISPLAY]
        if other:
            log(f"REFUSE: Resolve (pid {other[0]}) is running on display {display_of(other[0])}, not {DISPLAY}: "
                "that is a person's session; quit it first or use another backend.")
            return 1
        if rh.wait_until_scriptable(BOOT_TIMEOUT) is None:
            log("FAILED: the Resolve in the virtual display does not answer")
            return 4
        log("reusing the Resolve already running in the virtual display")
        return 0
    if not xvfb_pids():
        if xvfb_socket():
            log(f"FAILED: {DISPLAY} is taken by something that is not our Xvfb")
            return 3
        subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", SIZE, "+extension", "GLX", "+render", "-noreset"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        for _ in range(50):
            if xvfb_socket():
                break
            time.sleep(0.1)
        else:
            log("FAILED: Xvfb did not come up")
            return 3
    else:
        log("adopting the idle Xvfb left on " + DISPLAY)
    command = rr.launch_command(headless=False)
    if not command:
        log("REFUSE: no DaVinci Resolve install found")
        return 3
    env = rh.scripting_env()
    env["DISPLAY"] = DISPLAY
    env.pop("XAUTHORITY", None)
    log("starting " + " ".join(command) + f" on {DISPLAY}")
    t0 = time.monotonic()
    proc = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    if rh.wait_until_scriptable(BOOT_TIMEOUT) is None:
        log(f"FAILED: not scriptable after {BOOT_TIMEOUT:.0f}s; cleaning up")
        rh._kill_process(proc)
        kill_all(resolve_pids(), signal.SIGKILL)   # Resolve re-execs: what we spawned may not be the process that stayed
        kill_all(xvfb_pids(), signal.SIGTERM)
        return 4
    log(f"ready in {time.monotonic() - t0:.1f}s")
    return 0


def shutdown():
    """Under the lock, when no client is left: Quit Resolve, then stop the display."""
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


def main():
    registered = False
    try:
        with Lock():
            register()
            registered = True
            code = ensure_session()
        if code != 0:
            return code
        env = rh.scripting_env()
        env["DISPLAY"] = DISPLAY
        env.pop("XAUTHORITY", None)
        return subprocess.run(argv, env=env, check=False).returncode
    finally:
        _quiet()   # the client may be gone: any print to a closed pipe would abort the cleanup below
        if registered:
            with Lock():
                unregister()
                if not live_clients():
                    shutdown()


def _terminate(signum, frame):
    raise SystemExit(128 + signum)   # so `finally` runs (the client closing the session sends TERM/HUP)


for _sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
    signal.signal(_sig, _terminate)

raise SystemExit(main())
