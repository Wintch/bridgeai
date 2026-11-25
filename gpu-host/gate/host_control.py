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


LEVELS = {"ok": 0, "warm": 1, "hot": 2}


def zbx_items(host, t):
    """The heat reading as Zabbix trapper values: (host, key, value). `heat.level` is 0 ok, 1 warm, 2 hot; `heat.slowdown` is 1 while the
    driver reports a thermal slowdown. A missing reading (no driver answer, no hwmon) is left out, never sent as 0."""
    items = [(host, "heat.level", LEVELS.get(t.get("level"), -1)),
             (host, "heat.slowdown", 1 if any("thermal" in n for n in t.get("throttle", [])) else 0)]
    for key, field in (("heat.gpu_c", "gpu_c"), ("heat.gpu_w", "gpu_w"), ("heat.cpu_c", "cpu_c")):
        if t.get(field) is not None:
            items.append((host, key, t[field]))
    return items


def zbx_send(items, server, port=10051, timeout=5):
    """Zabbix trapper protocol over TCP, no zabbix_sender needed (the same packet ops/provider_uptime.py sends). Returns (processed, failed);
    raises OSError / ValueError."""
    import json
    import struct
    body = json.dumps({"request": "sender data", "data": [{"host": h, "key": k, "value": str(v)} for h, k, v in items]}).encode()
    with socket.create_connection((server, int(port)), timeout=timeout) as s:
        s.sendall(b"ZBXD\x01" + struct.pack("<Q", len(body)) + body)
        buf = b""
        while len(buf) < 13:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
        if len(buf) < 13 or buf[:4] != b"ZBXD":
            raise ValueError("no Zabbix header in the answer")
        size = struct.unpack("<Q", buf[5:13])[0]
        while len(buf) < 13 + size:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    info = json.loads(buf[13:13 + size].decode())
    m = re.search(r"processed: (\d+); failed: (\d+)", info.get("info", ""))
    if info.get("response") != "success" or not m:
        raise ValueError("Zabbix refused the values")
    return int(m.group(1)), int(m.group(2))


def push_heat(t, env=None, send=None):
    """One push of the reading when HOST_ZBX_SERVER and HOST_ZBX_HOST are set (the Zabbix server and the host name made by `provision.py heat-host`).
    Never raises: a Zabbix that is down must not stop the gate. Returns (processed, failed) or None when off or refused."""
    env = env or os.environ
    server, host = env.get("HOST_ZBX_SERVER", ""), env.get("HOST_ZBX_HOST", "")
    if not server or not host:
        return None
    try:
        return (send or zbx_send)(zbx_items(host, t), server, env.get("HOST_ZBX_PORT", "10051"))
    except (OSError, ValueError):
        return None


def start_thermal_log(path, every_s=60):
    """A daemon thread that logs once a minute for as long as the gate runs (the file survives its restarts), and pushes the same
    reading to Zabbix when HOST_ZBX_SERVER is set."""
    def loop():
        while True:
            push_heat(log_thermal(path))
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


SHOT_MAX_W = 1280
_shot_lock = threading.Lock()


def screenshot_argv(env):
    """ffmpeg grabs the whole X screen once (every monitor, as the person sees it) and writes one JPEG on stdout, at most SHOT_MAX_W wide."""
    w = int(env.get("HOST_SHOT_MAX_W", SHOT_MAX_W))
    return [env.get("HOST_FFMPEG", "ffmpeg"), "-nostdin", "-loglevel", "error", "-f", "x11grab", "-draw_mouse", "1", "-i", env.get("DISPLAY", ":0"),
            "-frames:v", "1", "-vf", f"scale='min({w},iw)':-2", "-q:v", "5", "-f", "image2pipe", "-c:v", "mjpeg", "-"]


def screenshot(run=None, env=None):
    """(http_code, jpeg bytes or an error dict). One grab at a time (a second request waits at most 10 s, then 429), 20 s at most per grab.
    The picture is the X screen: what a person sees on the monitor or in the stream, black only when the game owns the screen exclusively."""
    e = dict(env if env is not None else os.environ)
    e.setdefault("DISPLAY", ":0")
    e.setdefault("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
    if not _shot_lock.acquire(timeout=10):
        return 429, {"why": "busy"}
    try:
        r = (run or subprocess.run)(screenshot_argv(e), env=e, stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
    except FileNotFoundError:
        return 503, {"why": "no_ffmpeg"}
    except subprocess.TimeoutExpired:
        return 504, {"why": "timeout"}
    finally:
        _shot_lock.release()
    img = r.stdout or b""
    if r.returncode != 0 or img[:2] != b"\xff\xd8" or len(img) > 8 * 1024 * 1024:
        return 503, {"why": "no_display"}
    return 200, img


CAPTURE_PATH = os.path.expanduser(os.environ.get("HOST_CAPTURE_FILE", "~/.local/state/bridgeai-gate/capture.json"))
CLIP_DEFAULT_S, CLIP_MAX_S = 10, 30
# Recording profiles: what a clip costs the game against what it shows. `full` is the target (full HD at 60 fps); the light ones exist because
# the grab (x11grab copies the screen through the CPU) and the encoder both take from the game: pick the lightest that answers the question.
# `ligero` is 480p at 30 fps and 1 Mbit/s with a narrow mono audio track, still something Telegram plays inline.
PROFILES = {
    "full": {"w": 1920, "fps": 60, "vb": "8M", "maxrate": "10M", "ab": "128k", "ar": 48000, "ac": 2, "about": "1080p60, 8 Mbit/s, stereo 128k"},
    "medio": {"w": 1280, "fps": 30, "vb": "3M", "maxrate": "4M", "ab": "96k", "ar": 44100, "ac": 2, "about": "720p30, 3 Mbit/s, stereo 96k"},
    "calidad": {"w": 1280, "fps": 30, "vb": "1M", "maxrate": "1300k", "ab": "64k", "ar": 32000, "ac": 2, "about": "720p30, 1 Mbit/s, stereo 64k"},
    "ligero": {"w": 854, "fps": 30, "vb": "1M", "maxrate": "1300k", "ab": "48k", "ar": 22050, "ac": 1, "about": "480p30, 1 Mbit/s, mono 48k"},
}
DEFAULT_PROFILE = "full"
_clip_lock = threading.Lock()
_rec = {"active": False, "profile": None, "secs": 0, "since": 0}


def capture_conf(path):
    """{"enabled": bool, "profile": name}: whether recording is allowed on this host (off until a person turns it on: it takes from the game) and the
    profile used when the caller names none. Missing or unreadable file = off, `full`."""
    import json
    try:
        with open(path) as f:
            d = json.load(f)
        prof = d.get("profile")
        return {"enabled": d.get("enabled") is True, "profile": prof if prof in PROFILES else DEFAULT_PROFILE}
    except (OSError, ValueError, AttributeError):
        return {"enabled": False, "profile": DEFAULT_PROFILE}


def set_capture(path, enabled=None, profile=None):
    """(http_code, answer). Changes only what is given; an unknown profile is a 400 and nothing changes."""
    import json
    if profile is not None and profile not in PROFILES:
        return 400, {"why": "bad_profile", "profiles": sorted(PROFILES)}
    if enabled is not None and not isinstance(enabled, bool):
        return 400, {"why": "bad_request"}
    cur = capture_conf(path)
    if enabled is not None:
        cur["enabled"] = enabled
    if profile is not None:
        cur["profile"] = profile
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"
        with open(tmp, "w") as f:
            json.dump(cur, f)
        os.replace(tmp, path)
    except OSError:
        return 500, {"why": "not_saved"}
    return 200, capture_status(path)


def capture_status(path):
    """What the bot reports: allowed or not, the default profile, the profiles on offer, and whether a recording is running right now."""
    c = capture_conf(path)
    rec = dict(_rec) if _rec["active"] else {"active": False}
    if rec.get("active"):
        rec["elapsed_s"] = int(time.time() - rec["since"])
        rec["kind"] = "clip"
    with _lr_lock:
        pr, nm = _lr["proc"], _lr["name"]
        if pr is not None and pr.poll() is None:
            segs = rec_segments(nm)
            rec = {"active": True, "kind": "long", "name": nm, "profile": _lr["profile"], "elapsed_s": int(time.time() - _lr["since"]), "segments": len(segs),
                   "bytes": rec_bytes(), "cap_bytes": REC_CAP_BYTES}
        elif nm and _lr["stopped"] in ("cap", "disk", "failed"):
            rec = dict(rec, last_stop={"name": nm, "why": _lr["stopped"]})
    return {"enabled": c["enabled"], "profile": c["profile"], "profiles": {k: v["about"] for k, v in PROFILES.items()}, "recording": rec,
            "kept": rec_list(), "kept_bytes": rec_bytes(), "cap_bytes": REC_CAP_BYTES}


# ---- Long recording: a background ffmpeg that writes ten-minute Matroska segments in a folder on this host until it is stopped or the cap is reached.
# The original stays here only until it has been delivered (the bot downloads it in parts, Telegram keeps it, the person says it can go).
REC_DIR = os.path.expanduser(os.environ.get("HOST_REC_DIR", "~/recordings"))
REC_CAP_BYTES = int(float(os.environ.get("HOST_REC_CAP_GB", "10")) * 1e9)     # all kept recordings together; a test cap the operator chose
REC_MIN_FREE = int(float(os.environ.get("HOST_REC_MIN_FREE_GB", "5")) * 1e9)
REC_SEG_S = 600                                                                 # a segment ends after this many seconds ...
REC_SEG_BYTES = int(float(os.environ.get("HOST_REC_SEG_GB", "1")) * 1e9)       # ... or before it could pass this many bytes, whichever comes first
REC_PART_BYTES = 1_800_000_000                                                  # one delivered file: under Telegram's 2000 MB on the local Bot API
_lr = {"proc": None, "name": None, "dir": None, "profile": None, "since": 0, "stopped": None, "thread": None}
_lr_lock = threading.Lock()


def _rec_name_ok(name):
    return isinstance(name, str) and re.fullmatch(r"rec-\d{8}-\d{6}", name) is not None


def rec_segments(name, root=None):
    d = os.path.join(root or REC_DIR, name)
    try:
        return sorted(os.path.join(d, f) for f in os.listdir(d) if re.fullmatch(r"seg_\d{3}\.mkv", f))
    except OSError:
        return []


def rec_bytes(root=None):
    """Bytes of every kept recording together (what the cap counts)."""
    root = root or REC_DIR
    total = 0
    try:
        for dp, _dn, fn in os.walk(root):
            for f in fn:
                try:
                    total += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def rec_list(root=None):
    """The kept recordings: [{"name", "bytes", "segments", "parts"}], oldest first; `parts` is how many files of at most REC_PART_BYTES they will be delivered in."""
    root = root or REC_DIR
    out = []
    try:
        names = sorted(n for n in os.listdir(root) if _rec_name_ok(n))
    except OSError:
        return out
    for n in names:
        segs = rec_segments(n, root)
        sizes = [os.path.getsize(x) for x in segs if os.path.exists(x)]
        out.append({"name": n, "bytes": sum(sizes), "segments": len(sizes), "parts": len(rec_parts(n, root))})
    return out


def rec_parts(name, root=None):
    """The segments grouped, in order, into delivery parts of at most REC_PART_BYTES each (a lone bigger segment is its own part): [[paths]]."""
    parts, cur, size = [], [], 0
    for f in rec_segments(name, root):
        try:
            sz = os.path.getsize(f)
        except OSError:
            continue
        if cur and size + sz > REC_PART_BYTES:
            parts.append(cur)
            cur, size = [], 0
        cur.append(f)
        size += sz
    if cur:
        parts.append(cur)
    return parts


def _bits(rate):
    """"10M" -> 10_000_000, "1300k" -> 1_300_000 (ffmpeg's bitrate spelling)."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmM]?)", str(rate))
    return float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()] if m else 0.0


def rec_segment_seconds(profile, audio=True, env=None):
    """How long a segment may run: REC_SEG_S, or less so that even at the profile's ceiling bitrate (video maxrate plus its audio) it stays under REC_SEG_BYTES.
    ffmpeg's segment muxer cuts by time only, so "10 minutes or 1 GB, whichever first" is guaranteed through the bitrate ceiling: with the VBR maxrate and a
    buffer of the same size, a segment cannot outgrow it by more than a few percent (the stop summary reports the largest one actually written)."""
    p = PROFILES[profile]
    env = os.environ if env is None else env
    ceiling = _bits((env.get("HOST_CLIP_BITRATE") and max(_bits(env["HOST_CLIP_BITRATE"]), _bits(p["maxrate"]))) or p["maxrate"]) + (_bits(p["ab"]) if audio else 0)
    return max(10, min(REC_SEG_S, int(REC_SEG_BYTES * 8 / ceiling))) if ceiling > 0 else REC_SEG_S


def rec_argv(env, out_pattern, audio, profile):
    p = PROFILES[profile]
    seg = rec_segment_seconds(profile, bool(audio), env)
    vb = env.get("HOST_CLIP_BITRATE") or p["vb"]
    a = [env.get("HOST_FFMPEG", "ffmpeg"), "-loglevel", "error", "-f", "x11grab", "-framerate", str(p["fps"]), "-draw_mouse", "1", "-i", env.get("DISPLAY", ":0")]
    if audio:
        a += ["-f", "pulse", "-i", audio]
    a += ["-vf", f"scale='min({p['w']},iw)':-2,format=yuv420p", "-c:v", "hevc_nvenc", "-preset", "p4", "-rc", "vbr", "-b:v", vb, "-maxrate", p["maxrate"], "-bufsize", p["maxrate"],
          "-g", str(p["fps"] * 2), "-force_key_frames", f"expr:gte(t,n_forced*{seg})"]
    a += ["-c:a", "aac", "-b:a", p["ab"], "-ar", str(p["ar"]), "-ac", str(p["ac"])] if audio else ["-an"]
    return a + ["-f", "segment", "-segment_time", str(seg), "-segment_format", "matroska", "-reset_timestamps", "1", out_pattern]


def _free_bytes(path):
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize
    except OSError:
        return 1 << 60


def _rec_watch(proc, name, root, cap, min_free, tick=5.0, sleep=time.sleep, size=None, free=None):
    """Until ffmpeg ends: stop it when the kept recordings reach the cap or the disk runs low; note why in `_lr["stopped"]`."""
    size = size or (lambda: rec_bytes(root))
    free = free or (lambda: _free_bytes(root))
    while proc.poll() is None:
        sleep(tick)
        if proc.poll() is not None:
            break
        why = "cap" if size() >= cap else ("disk" if free() < min_free else None)
        if why:
            with _lr_lock:
                if _lr["name"] == name and not _lr["stopped"]:
                    _lr["stopped"] = why
            _rec_quit(proc)
            break
    with _lr_lock:
        if _lr["name"] == name and not _lr["stopped"]:
            _lr["stopped"] = "ended" if proc.returncode == 0 else "failed"


def _rec_quit(proc, wait=25):
    """Ask ffmpeg to finish cleanly (`q` on its stdin closes the file properly), then insist."""
    try:
        if proc.stdin:
            proc.stdin.write(b"q")
            proc.stdin.flush()
    except (OSError, ValueError):
        pass
    try:
        proc.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def rec_start(conf_path, profile=None, popen=None, run=None, env=None, root=None, cap=None, min_free=None, watcher=True):
    """(http_code, answer). Needs recording switched on (403 capture_off), refuses a second one (409), a full store (507) or an unknown profile (400)."""
    e = dict(env if env is not None else os.environ)
    e.setdefault("DISPLAY", ":0")
    e.setdefault("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
    e.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    root = root or REC_DIR
    c = capture_conf(conf_path)
    if not c["enabled"]:
        return 403, {"why": "capture_off"}
    profile = profile or c["profile"]
    if profile not in PROFILES:
        return 400, {"why": "bad_profile", "profiles": sorted(PROFILES)}
    cap = REC_CAP_BYTES if cap is None else cap
    min_free = REC_MIN_FREE if min_free is None else min_free
    with _lr_lock:
        if _lr["proc"] is not None and _lr["proc"].poll() is None:
            return 409, {"why": "already_recording", "name": _lr["name"]}
    if _clip_lock.locked():
        return 429, {"why": "busy"}
    os.makedirs(root, mode=0o700, exist_ok=True)
    if rec_bytes(root) >= cap:
        return 507, {"why": "store_full", "bytes": rec_bytes(root), "cap": cap}
    if _free_bytes(root) < min_free:
        return 507, {"why": "disk_low"}
    name = time.strftime("rec-%Y%m%d-%H%M%S")
    d = os.path.join(root, name)
    os.makedirs(d, mode=0o700, exist_ok=True)
    audio = clip_audio_source(run or subprocess.run, e)
    try:
        log = open(os.path.join(d, "ffmpeg.log"), "wb")
        proc = (popen or subprocess.Popen)(rec_argv(e, os.path.join(d, "seg_%03d.mkv"), audio, profile), env=e, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                           stderr=log, start_new_session=True)
    except FileNotFoundError:
        return 503, {"why": "no_ffmpeg"}
    with _lr_lock:
        _lr.update(proc=proc, name=name, dir=d, profile=profile, since=time.time(), stopped=None)
    if watcher:
        th = threading.Thread(target=_rec_watch, args=(proc, name, root, cap, min_free), daemon=True)
        _lr["thread"] = th
        th.start()
    return 200, {"started": True, "name": name, "profile": profile, "audio": bool(audio), "cap_bytes": cap}


def rec_stop(root=None):
    """(http_code, summary). Finishes the running recording cleanly and says how long it was, how big, and why it ended."""
    root = root or REC_DIR
    with _lr_lock:
        proc, name, since = _lr["proc"], _lr["name"], _lr["since"]
    if proc is None or name is None:
        return 409, {"why": "not_recording"}
    if proc.poll() is None:
        with _lr_lock:
            _lr["stopped"] = _lr["stopped"] or "requested"
        _rec_quit(proc)
    th = _lr.get("thread")
    if th is not None and th is not threading.current_thread():
        th.join(timeout=15)
    segs = rec_segments(name, root)
    sizes = [os.path.getsize(x) for x in segs if os.path.exists(x)]
    return 200, {"name": name, "why": _lr["stopped"] or "requested", "elapsed_s": int(time.time() - since), "segments": len(segs),
                 "bytes": sum(sizes), "largest_segment_bytes": max(sizes, default=0), "parts": len(rec_parts(name, root))}


def rec_delete(name, root=None):
    """(http_code, answer). Removes one finished recording (never the one that is running); the name must look like ours."""
    import shutil
    root = root or REC_DIR
    if not _rec_name_ok(name):
        return 400, {"why": "bad_name"}
    with _lr_lock:
        if _lr["proc"] is not None and _lr["proc"].poll() is None and _lr["name"] == name:
            return 409, {"why": "still_recording"}
    d = os.path.join(root, name)
    if not os.path.isdir(d) or os.path.islink(d):
        return 404, {"why": "unknown"}
    freed = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))
    shutil.rmtree(d)
    return 200, {"deleted": name, "freed_bytes": freed}


def rec_part_file(name, part, run=None, root=None, tmpdir=None):
    """(http_code, path of a finished mp4 or an error dict). Joins the segments of delivery part `part` (1-based) without re-encoding, `hvc1`-tagged and
    with `faststart`. The caller sends the file and removes it."""
    root = root or REC_DIR
    if not _rec_name_ok(name):
        return 400, {"why": "bad_name"}
    parts = rec_parts(name, root)
    if not isinstance(part, int) or not 1 <= part <= len(parts):
        return 404, {"why": "no_such_part", "parts": len(parts)}
    import tempfile
    d = tempfile.mkdtemp(prefix="bridgeai-recpart-", dir=tmpdir)
    lst, out = os.path.join(d, "list.txt"), os.path.join(d, f"{name}-p{part}.mp4")
    with open(lst, "w") as f:
        for seg in parts[part - 1]:
            f.write("file '" + seg.replace("'", "'\\''") + "'\n")
    try:
        r = (run or subprocess.run)(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-tag:v", "hvc1",
                                     "-movflags", "+faststart", "-y", out], capture_output=True, timeout=900)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        import shutil
        shutil.rmtree(d, ignore_errors=True)
        return 503, {"why": "no_ffmpeg"}
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
        return 503, {"why": "join_failed"}
    return 200, out


def clip_audio_source(run, env):
    """The PipeWire/Pulse source to record the sound from, or None for a silent clip. HOST_CLIP_AUDIO: `none`, a source name, or `auto` (default):
    the monitor of the default sink, which is what the game plays into (never a microphone)."""
    want = env.get("HOST_CLIP_AUDIO", "auto")
    if want == "none":
        return None
    if want != "auto":
        return want
    try:
        r = run(["pactl", "get-default-sink"], env=env, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    name = (r.stdout or "").strip()
    return name + ".monitor" if r.returncode == 0 and re.fullmatch(r"[A-Za-z0-9_.:+-]{1,120}", name) else None


def clip_argv(env, secs, out, audio, profile=DEFAULT_PROFILE):
    """One ffmpeg: the X screen at the profile's frame rate (at most its width, 4:2:0) to H.265 on the GPU (hevc_nvenc), the game's sound to AAC,
    an mp4 whose `hvc1` tag Telegram and phones play. The length is the caller's, already clamped."""
    p = PROFILES[profile]
    vb = env.get("HOST_CLIP_BITRATE") or p["vb"]
    a = [env.get("HOST_FFMPEG", "ffmpeg"), "-nostdin", "-loglevel", "error", "-f", "x11grab", "-framerate", str(p["fps"]), "-draw_mouse", "1", "-i", env.get("DISPLAY", ":0")]
    if audio:
        a += ["-f", "pulse", "-i", audio]
    a += ["-t", str(secs), "-vf", f"scale='min({p['w']},iw)':-2,format=yuv420p", "-c:v", "hevc_nvenc", "-preset", "p4", "-rc", "vbr", "-b:v", vb,
          "-maxrate", p["maxrate"], "-bufsize", p["maxrate"], "-tag:v", "hvc1"]
    a += ["-c:a", "aac", "-b:a", p["ab"], "-ar", str(p["ar"]), "-ac", str(p["ac"])] if audio else ["-an"]
    return a + ["-movflags", "+faststart", "-y", out]


def clip(secs, profile=None, run=None, env=None, conf_path=None):
    """(http_code, {"mp4", "secs", "audio", "profile"} or an error dict). With `conf_path`, a host where recording is off answers 403 capture_off and
    records nothing; `profile` None takes the configured one. One recording at a time (a second request is a 429 at once), `secs` clamped to
    1..CLIP_MAX_S. The video encoder is the GPU's (NVENC): a few percent of the card next to a game; the grab is CPU, and it is what a 60 fps profile pays for."""
    e = dict(env if env is not None else os.environ)
    e.setdefault("DISPLAY", ":0")
    e.setdefault("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
    e.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    if conf_path is not None:
        c = capture_conf(conf_path)
        if not c["enabled"]:
            return 403, {"why": "capture_off"}
        profile = profile or c["profile"]
    profile = profile or DEFAULT_PROFILE
    if profile not in PROFILES:
        return 400, {"why": "bad_profile", "profiles": sorted(PROFILES)}
    try:
        secs = max(1, min(CLIP_MAX_S, int(secs)))
    except (TypeError, ValueError):
        secs = CLIP_DEFAULT_S
    runner = run or subprocess.run
    if not _clip_lock.acquire(blocking=False):
        return 429, {"why": "busy"}
    _rec.update(active=True, profile=profile, secs=secs, since=time.time())
    try:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="bridgeai-clip-") as d:
            out = os.path.join(d, "clip.mp4")
            audio = clip_audio_source(runner, e)
            try:
                r = runner(clip_argv(e, secs, out, audio, profile), env=e, stdin=subprocess.DEVNULL, capture_output=True, timeout=secs + 40)
            except FileNotFoundError:
                return 503, {"why": "no_ffmpeg"}
            except subprocess.TimeoutExpired:
                return 504, {"why": "timeout"}
            try:
                with open(out, "rb") as f:
                    data = f.read(50 * 1024 * 1024 + 1)
            except OSError:
                data = b""
            if r.returncode != 0 or len(data) < 1000 or data[4:8] != b"ftyp" or len(data) > 50 * 1024 * 1024:
                return 503, {"why": "no_clip"}
            return 200, {"mp4": data, "secs": secs, "audio": bool(audio), "profile": profile}
    finally:
        _rec["active"] = False
        _clip_lock.release()


def sunshine_port(env=None):
    """The base port of THIS host's Sunshine (HOST_SUNSHINE_PORT, default 47989): moved when the router already forwards the default range to another service."""
    try:
        return int((env if env is not None else os.environ).get("HOST_SUNSHINE_PORT") or 47989)
    except ValueError:
        return 47989


def stream_up(port=None, host="127.0.0.1"):
    port = port or sunshine_port()
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


def display_mode(run=None, env=None):
    """{"output", "mode", "hz"} of the first output with a current mode (`xrandr --current`), or {} when there is no X display."""
    e = dict(env if env is not None else os.environ)
    e.setdefault("DISPLAY", ":0")
    e.setdefault("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
    try:
        out = (run or (lambda c: subprocess.run(c, env=e, capture_output=True, text=True, timeout=6, stdin=subprocess.DEVNULL).stdout))(["xrandr", "--current"])
    except (OSError, subprocess.SubprocessError):
        return {}
    cur_out, res = None, {}
    for line in out.splitlines():
        m = re.match(r"^(\S+) connected", line)
        if m:
            cur_out = m.group(1)
            continue
        m = re.match(r"^\s+(\S+)\s+(.*)$", line)
        if m and cur_out and not res:
            h = re.search(r"([\d.]+)\*", m.group(2))
            if h:
                res = {"output": cur_out, "mode": m.group(1), "hz": float(h.group(1))}
    return res


def encoder_stats(run=None):
    """The NVENC sessions' own numbers from the driver: {"sessions", "fps", "latency_ms"} (fps and latency are averages over what is running);
    {} when nvidia-smi does not answer. This is the host's view of the stream: it cannot see what the network lost on the way to the player."""
    q = "encoder.stats.sessionCount,encoder.stats.averageFps,encoder.stats.averageLatency"
    try:
        out = (run or (lambda c: subprocess.run(c, capture_output=True, text=True, timeout=8, stdin=subprocess.DEVNULL).stdout))(
            ["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"])
        f = [x.strip() for x in out.strip().splitlines()[0].split(",")]
        return {"sessions": int(f[0]), "fps": float(f[1]), "latency_ms": round(float(f[2]) / 1000.0, 1)}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return {}


# Sunshine log lines that appear on every healthy start (probing encoders, an AV1 the card lacks, the gamepad daemon): never a warning to the person.
SUN_NOISE = re.compile(r"NvFBC context from current thread: *$|cuda_t doesn't support|av1_nvenc|Codec not supported|Function not implemented|"
                       r"Provided device doesn't support required NVENC|Failed to create client: Daemon not running|Ignore any errors")
_SUN_TS = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.\d+\]: (\w+): (.*)$")


def parse_sunshine(text, now=None, window_s=600):
    """What Sunshine's log says about the stream: {"client": bool (a player is connected), "codec", "bitrate_mbps", "resolution", "problems": [lines of
    the last `window_s` seconds that are warnings or errors and not startup noise, newest last, at most 5], "problem_count"}. Times in the log are local."""
    now = time.time() if now is None else now
    ev, problems, info = None, [], {}
    for line in text.splitlines():
        m = _SUN_TS.match(line)
        if not m:
            continue
        stamp, level, msg = m.groups()
        if "CLIENT CONNECTED" in msg:
            ev, info = True, {}
        elif "CLIENT DISCONNECTED" in msg:
            ev = False
        elif ev:
            b = re.match(r"Streaming bitrate is (\d+)", msg)
            if b:
                info["bitrate_mbps"] = round(int(b.group(1)) / 1e6, 1)
            c = re.match(r"Creating encoder \[(\w+)\]", msg)
            if c:
                info["codec"] = c.group(1)
            r = re.match(r"Virtual Desktop: (\S+)", msg)
            if r:
                info["resolution"] = r.group(1)
        if level in ("Warning", "Error") and not SUN_NOISE.search(msg):
            try:
                t = time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                continue
            if now - t <= window_s:
                problems.append(msg.strip()[:140])
    out = {"client": bool(ev), "problem_count": len(problems), "problems": problems[-5:]}
    out.update(info if ev else {})
    return out


def sunshine_status(path=None, now=None):
    path = path or os.environ.get("HOST_SUNSHINE_LOG") or os.path.expanduser("~/.config/sunshine/sunshine.log")
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400_000))
            return parse_sunshine(f.read().decode("utf-8", "replace"), now)
    except OSError:
        return {}


def stream_verdict(display, enc, sun, target_hz=144.0, pct=0.9):
    """The plain facts for the person: {"hz_ok": bool or None (the screen is at the refresh the stream is meant to run at), "frames": "ok" | "loss" |
    "idle" | "unknown", "fps": the encoder's, "of": the screen's refresh}. The encoder's average fps against the screen's refresh is how frames lost on the
    host show; what the network lost only the player's own statistics overlay can say."""
    hz = display.get("hz")
    v = {"hz_ok": (hz is not None and abs(hz - target_hz) < 1.0) if hz is not None else None, "frames": "unknown"}
    if not enc or not display:
        return v
    if enc.get("sessions", 0) <= 0 or not sun.get("client", False):
        v["frames"] = "idle"
        return v
    v["fps"], v["of"] = enc.get("fps"), hz
    v["frames"] = "ok" if hz and enc.get("fps", 0) >= pct * hz else "loss"
    return v


def state(root=None, proc=None):
    games = {g["appid"]: g["name"] for g in inventory(root)}
    run_ids = sorted(running(proc))
    sh = shaders(proc, root=root)
    try:
        up = int(float(open("/proc/uptime").read().split()[0]))
    except (OSError, ValueError):
        up = None
    up_stream = stream_up()
    disp, enc, sun = display_mode(), encoder_stats(), sunshine_status()
    return {"display": disp, "encoder": enc, "sunshine": sun, "stream": stream_verdict(disp, enc, sun, _num("HOST_TARGET_HZ", 144.0)),
            "capture": capture_status(CAPTURE_PATH), "thermal": thermal(), "running": [{"appid": a, "name": games.get(a, "?")} for a in run_ids], "shaders": sh, "stream_up": up_stream,
            "ready": bool(run_ids) and up_stream and not sh["compiling"], "uptime_s": up, "time": int(time.time())}
