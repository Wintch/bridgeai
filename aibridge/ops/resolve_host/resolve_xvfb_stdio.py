#!/usr/bin/env python3
"""`resolve_headless.py run -- <cmd>`, but Resolve runs WITH its GUI inside a private Xvfb instead of `-nogui` (2026-11-04).

Why: under `-nogui` LoadRenderPreset returns False and render calls hang; with a GUI (here an invisible one) the
render queue works (measured: 64 s of 1080p to H.264 in 4.2 s). The operator's own desktop is never touched.

  * Xvfb on :99 (RESOLVE_XVFB_DISPLAY, RESOLVE_XVFB_SIZE) is started if missing and stopped again only if this script
    started it.
  * A Resolve already running on that display is reused; one on any OTHER display (the operator's session) is refused.
  * Resolve is Quit() at the end only if this script started it (force after the grace time: a GUI Quit can ask to save).
  * Status chatter goes to stderr: stdout is the MCP JSON-RPC channel.

Usage: resolve_xvfb_stdio.py <repo> -- <server command...>
"""
import os, signal, subprocess, sys, time

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


def log(msg):
    print(f"[resolve_xvfb] {msg}", file=sys.stderr, flush=True)


def resolve_pids():
    # not `pgrep -x resolve`: once Qt is up the process renames its main thread to "GUI Thread" and -x stops matching
    out = subprocess.run(["pgrep", "-f", "^/opt/resolve/bin/resolve( |$)"], capture_output=True, text=True, check=False)
    return [int(p) for p in out.stdout.split() if p.isdigit()]


def display_of(pid):
    try:
        for kv in open(f"/proc/{pid}/environ", "rb").read().split(b"\0"):
            if kv.startswith(b"DISPLAY="):
                return kv[8:].decode()
    except OSError:
        pass
    return None


def xvfb_pids():
    out = subprocess.run(["pgrep", "-f", f"^Xvfb {DISPLAY} "], capture_output=True, text=True, check=False)
    return [int(p) for p in out.stdout.split() if p.isdigit()]


def xvfb_socket():
    return os.path.exists("/tmp/.X11-unix/X" + DISPLAY.lstrip(":"))


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
    xvfb = None
    owned_xvfb = False
    we_started = False
    pids = resolve_pids()
    if pids:
        other = [p for p in pids if display_of(p) != DISPLAY]
        if other:
            log(f"REFUSE: Resolve (pid {other[0]}) is running on display {display_of(other[0])}, not {DISPLAY}: "
                "that is a person's session; quit it first or use another backend.")
            return 1
        log("reusing the Resolve already running in the virtual display")
    else:
        orphan = xvfb_pids()          # a display left behind by a session that died before it could clean up
        if orphan:
            log(f"adopting the idle Xvfb {orphan[0]} left on {DISPLAY}")
            owned_xvfb = True
        elif not xvfb_socket():
            owned_xvfb = True
            xvfb = subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", SIZE, "+extension", "GLX", "+render", "-noreset"],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
            for _ in range(50):
                if xvfb_socket():
                    break
                time.sleep(0.1)
            else:
                log("FAILED: Xvfb did not come up")
                xvfb.kill()
                return 3
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
            log(f"FAILED: not scriptable after {BOOT_TIMEOUT:.0f}s; cleaning up what this script started")
            rh._kill_process(proc)
            for pid in resolve_pids():   # Resolve re-execs: what we spawned may not be the process that stayed
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
            for pid in xvfb_pids():
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
            return 4
        we_started = True
        log(f"ready in {time.monotonic() - t0:.1f}s")
    env = rh.scripting_env()
    env["DISPLAY"] = DISPLAY
    env.pop("XAUTHORITY", None)
    try:
        return subprocess.run(argv, env=env, check=False).returncode
    finally:
        _quiet()   # the client may be gone: any print to a closed pipe would abort the cleanup below
        if we_started:
            if rh.stop(30.0) != 0:
                rh.stop(20.0, force=True)
        if owned_xvfb:
            for _ in range(60):   # Resolve needs a moment to leave after Quit; never pull the display from under it
                if not resolve_pids():
                    break
                time.sleep(0.5)
            if not resolve_pids():
                for pid in xvfb_pids():
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except OSError:
                        pass


def _terminate(signum, frame):
    raise SystemExit(128 + signum)   # so `finally` runs and Resolve is Quit (the client closing the session sends TERM/HUP)


for _sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
    signal.signal(_sig, _terminate)

raise SystemExit(main())
