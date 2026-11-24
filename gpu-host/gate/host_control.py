#!/usr/bin/env python3
"""Control of a desktop GPU host from the gate: which games it has, start one, suspend or power off. Stdlib only.

A stand-in for what a machine-rental panel's agent does (inventory, launch, suspend), so a bot can say "run gta4" and, later,
"freeze it". The gate serves it under /host/* with its OWN token (GATE_HOST_TOKEN, never the stacks' GATE_TOKEN), off until set.

- inventory: Steam only (appmanifest_*.acf of every library in libraryfolders.vdf); runtimes, Proton and redistributables are left out.
- launch: only an appid that is in that inventory, as `steam steam://rungameid/<appid>` inside the logged-in X session. A game that
  already runs is not started twice.
- power: `suspend` or `poweroff` through `sudo -n systemctl`, three seconds after the answer so the caller still gets it.
No shell is ever built from a request: the appid is an integer checked against the inventory, the action one of two words."""
import glob
import os
import re
import socket
import subprocess
import threading
import time

SKIP = re.compile(r"^(Proton\b|Steam Linux Runtime|Steamworks Common|Steam Controller|SteamVR$)", re.I)
POWER = {"suspend": ["sudo", "-n", "systemctl", "suspend"], "poweroff": ["sudo", "-n", "systemctl", "poweroff"]}
POWER_DELAY_S = 3


def steam_root(env=None):
    env = env or os.environ
    return env.get("HOST_STEAM_ROOT") or os.path.expanduser("~/.steam/debian-installation")


def _libraries(root):
    libs = [root]
    try:
        with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), errors="replace") as f:
            libs += re.findall(r'"path"\s+"([^"]+)"', f.read())
    except OSError:
        pass
    seen, out = set(), []
    for p in libs:
        p = os.path.realpath(p)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def inventory(root=None):
    """[{"appid": int, "name": str}] sorted by name."""
    games = {}
    for lib in _libraries(root or steam_root()):
        for f in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                text = open(f, errors="replace").read()
            except OSError:
                continue
            a = re.search(r'"appid"\s+"(\d{1,10})"', text)
            n = re.search(r'"name"\s+"([^"]{1,120})"', text)
            if a and n and not SKIP.search(n.group(1)):
                games[int(a.group(1))] = n.group(1)
    return sorted(({"appid": k, "name": v} for k, v in games.items()), key=lambda g: g["name"].lower())


def _proc(proc):
    return proc or os.environ.get("GATE_PROC_DIR") or "/proc"


def running(proc=None):
    """Set of appids whose Steam launch wrapper is alive (`reaper SteamLaunch AppId=N --`)."""
    proc = _proc(proc)
    out = set()
    for d in glob.glob(os.path.join(proc, "[0-9]*")):
        try:
            cmd = open(os.path.join(d, "cmdline"), "rb").read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        m = re.search(r"SteamLaunch AppId=(\d{1,10})\b", cmd)
        if m:
            out.add(int(m.group(1)))
    return out


def launch_argv(appid, env):
    """The command that starts the game. By default it runs in its OWN transient user unit (`systemd-run --user`), not in the gate's: a
    game started from the gate's cgroup died the moment the gate was restarted (found the hard way). HOST_LAUNCH_WRAP=none starts it directly
    (the selftest, or a host without systemd user units)."""
    steam = env.get("HOST_STEAM_BIN", "/usr/games/steam")
    cmd = [steam, f"steam://rungameid/{appid}"]
    if env.get("HOST_LAUNCH_WRAP", "systemd-run") == "none":
        return cmd
    return ["systemd-run", "--user", "--quiet", "--collect", f"--unit=bridgeai-game-{appid}-{int(time.time())}", "-p", "KillMode=process",
            f"--setenv=DISPLAY={env.get('DISPLAY', ':0')}", f"--setenv=XAUTHORITY={env.get('XAUTHORITY', '')}"] + cmd


def launch(appid, root=None, proc=None, popen=subprocess.Popen, env=None):
    """(http_code, answer). Starts the game unless it already runs; refuses an appid that is not in the inventory."""
    games = {g["appid"]: g["name"] for g in inventory(root)}
    if not isinstance(appid, int) or isinstance(appid, bool) or appid not in games:
        return 404, {"why": "unknown_game"}
    if appid in running(proc):
        return 200, {"started": False, "already_running": True, "name": games[appid]}
    e = dict(env if env is not None else os.environ)
    e.setdefault("DISPLAY", ":0")
    e.setdefault("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
    try:
        popen(launch_argv(appid, e), env=e, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return 500, {"why": "steam_missing"}
    return 200, {"started": True, "already_running": False, "name": games[appid]}


def power(action, run=None, delay=POWER_DELAY_S):
    """(http_code, answer). The command runs after `delay` seconds in a thread; a test passes `run` and delay 0."""
    if action not in POWER:
        return 400, {"why": "bad_action"}
    cmd = POWER[action]
    runner = run or (lambda c: subprocess.run(c, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30))
    t = threading.Timer(delay, runner, args=(cmd,))
    t.daemon = True
    t.start()
    return 200, {"ok": True, "action": action, "in_s": delay}


def stream_up(port=47989, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


_shader_seen = {"at": 0.0, "appids": []}


def shaders(proc=None, now=None, root=None):
    """Steam's shader pre-compilation (`fossilize_replay` workers, one batch after another): the first launch of a game can spend
    minutes on it, and entering before it ends means a stuttering, half-loaded game. {"compiling", "workers", "appids"}.
    The workers come in batches, so the state stays "compiling" for HOST_SHADER_GRACE_S (20 s) after the last one was seen."""
    proc = _proc(proc)
    now = time.time() if now is None else now
    workers, ids = 0, set()
    for d in glob.glob(os.path.join(proc, "[0-9]*")):
        try:
            cmd = open(os.path.join(d, "cmdline"), "rb").read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if "fossilize_replay" in cmd:
            workers += 1
            m = re.search(r"shadercache/(\d{1,10})/", cmd)
            if m:
                ids.add(int(m.group(1)))
    if workers:
        _shader_seen["at"], _shader_seen["appids"] = now, sorted(ids)
    try:
        grace = float(os.environ.get("HOST_SHADER_GRACE_S", "20"))
    except ValueError:
        grace = 20.0
    on = bool(workers) or now - _shader_seen["at"] < grace
    out = {"compiling": on, "workers": workers, "appids": _shader_seen["appids"] if on else []}
    pct = shader_percent(out["appids"], root)
    if on and pct is not None:
        out["percent"] = pct
    return out


def shader_percent(appids, root=None):
    """Steam's own progress (0-100) for the game being compiled, from the last "Still replaying <appid> (NN%, ...)" line of its shader log
    (three passes of about a third each: the percentage jumps back to 33 and 66 as a pass starts). None when there is no such line."""
    if not appids:
        return None
    try:
        path = os.path.join(root or steam_root(), "logs", "shader_log.txt")
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 65536))
            tail = f.read().decode(errors="replace")
    except OSError:
        return None
    last = None
    for m in re.finditer(r"Still replaying (\d{1,10}) \((\d{1,3})%", tail):
        if int(m.group(1)) in appids:
            last = int(m.group(2))
    return last


def state(root=None, proc=None):
    games = {g["appid"]: g["name"] for g in inventory(root)}
    run_ids = sorted(running(proc))
    sh = shaders(proc, root=root)
    try:
        up = int(float(open("/proc/uptime").read().split()[0]))
    except (OSError, ValueError):
        up = None
    up_stream = stream_up()
    return {"running": [{"appid": a, "name": games.get(a, "?")} for a in run_ids], "shaders": sh, "stream_up": up_stream,
            "ready": bool(run_ids) and up_stream and not sh["compiling"], "uptime_s": up, "time": int(time.time())}
