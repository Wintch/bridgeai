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


# --- heat: summer made this a thing to watch ------------------------------------------------------------------------------------
# GPU: the driver holds the card at its target temperature (83 C on the reference RTX 3060 Ti), slows down at 95. CPU: a Ryzen 5 5600X boosts
# until it is hot (86 C seen on GTA IV). Levels, overridable: HOST_GPU_WARM_C 78, HOST_GPU_HOT_C 83, HOST_CPU_WARM_C 85, HOST_CPU_HOT_C 90.
THROTTLE_BITS = {0x4: "power cap", 0x8: "hardware slowdown", 0x20: "thermal slowdown", 0x40: "hardware thermal slowdown", 0x80: "power brake"}


def _num(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def cpu_temp_c(hwmon=None):
    """Tctl of the AMD CPU (k10temp) or the package sensor of an Intel one (coretemp), in C; None when there is no such sensor."""
    root = hwmon or os.environ.get("HOST_HWMON_DIR") or "/sys/class/hwmon"
    for d in sorted(glob.glob(os.path.join(root, "hwmon*"))):
        try:
            if open(os.path.join(d, "name")).read().strip() in ("k10temp", "coretemp"):
                return round(int(open(os.path.join(d, "temp1_input")).read().strip()) / 1000, 1)
        except (OSError, ValueError):
            continue
    return None


def gpu_reading(run=None):
    """{"gpu_c", "gpu_w", "limit_w", "clock_mhz", "throttle": [names]} from one nvidia-smi query, or {} when it fails."""
    q = "temperature.gpu,power.draw,power.limit,clocks.sm,clocks_event_reasons.active"
    try:
        out = (run or (lambda c: subprocess.run(c, capture_output=True, text=True, timeout=8, stdin=subprocess.DEVNULL).stdout))(
            ["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"])
        f = [x.strip() for x in out.strip().splitlines()[0].split(",")]
        bits = int(f[4], 16) if f[4].lower().startswith("0x") else int(f[4])
        return {"gpu_c": float(f[0]), "gpu_w": float(f[1]), "limit_w": float(f[2]), "clock_mhz": float(f[3]),
                "throttle": [name for bit, name in THROTTLE_BITS.items() if bits & bit]}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return {}


def heat_level(gpu_c, cpu_c):
    """"hot" at or above the hot limits, "warm" above the warm ones, else "ok" ("unknown" with no reading at all)."""
    if gpu_c is None and cpu_c is None:
        return "unknown"
    gc, cc = gpu_c if gpu_c is not None else 0, cpu_c if cpu_c is not None else 0
    if gc >= _num("HOST_GPU_HOT_C", 83) or cc >= _num("HOST_CPU_HOT_C", 90):
        return "hot"
    if gc >= _num("HOST_GPU_WARM_C", 78) or cc >= _num("HOST_CPU_WARM_C", 85):
        return "warm"
    return "ok"


def thermal(run=None, hwmon=None):
    g = gpu_reading(run)
    c = cpu_temp_c(hwmon)
    out = dict(g)
    out["cpu_c"] = c
    out["level"] = heat_level(g.get("gpu_c"), c)
    return out


def log_thermal(path, run=None, hwmon=None, now=None, max_bytes=2_000_000):
    """One CSV line: epoch, gpu C, gpu W, limit W, clock MHz, cpu C, level, throttle names. Starts a new file past max_bytes (one generation kept)."""
    t = thermal(run, hwmon)
    row = [int(now if now is not None else time.time()), t.get("gpu_c", ""), t.get("gpu_w", ""), t.get("limit_w", ""), t.get("clock_mhz", ""),
           t.get("cpu_c", "") if t.get("cpu_c") is not None else "", t["level"], "+".join(t.get("throttle", []))]
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > max_bytes:
            os.replace(path, path + ".1")
        new = not os.path.exists(path)
        with open(path, "a") as f:
            if new:
                f.write("t,gpu_c,gpu_w,limit_w,clock_mhz,cpu_c,level,throttle\n")
            f.write(",".join(str(x) for x in row) + "\n")
    except OSError:
        pass
    return t


def start_thermal_log(path, every_s=60):
    """A daemon thread that logs once a minute for as long as the gate runs (the file survives its restarts)."""
    def loop():
        while True:
            log_thermal(path)
            time.sleep(every_s)
    th = threading.Thread(target=loop, daemon=True)
    th.start()
    return th


def thermal_history(path, minutes=60, now=None):
    """The logged lines of the last `minutes` as dicts, plus the peaks."""
    cutoff = (now if now is not None else time.time()) - minutes * 60
    rows = []
    try:
        with open(path) as f:
            next(f, None)
            for line in f:
                p = line.rstrip("\n").split(",")
                if len(p) >= 8 and p[0].isdigit() and int(p[0]) >= cutoff:
                    rows.append({"t": int(p[0]), "gpu_c": _f(p[1]), "gpu_w": _f(p[2]), "cpu_c": _f(p[5]), "level": p[6], "throttle": p[7]})
    except OSError:
        pass
    peaks = {k: max((r[k] for r in rows if r[k] is not None), default=None) for k in ("gpu_c", "gpu_w", "cpu_c")}
    return {"minutes": minutes, "samples": len(rows), "peaks": peaks, "rows": rows[-120:]}


def _f(x):
    try:
        return float(x)
    except ValueError:
        return None


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
    return {"thermal": thermal(), "running": [{"appid": a, "name": games.get(a, "?")} for a in run_ids], "shaders": sh, "stream_up": up_stream,
            "ready": bool(run_ids) and up_stream and not sh["compiling"], "uptime_s": up, "time": int(time.time())}
