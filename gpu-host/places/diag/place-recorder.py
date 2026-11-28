#!/usr/bin/env python3
"""Recorder for the GTA IV test rounds on a place (run as root on the GPU host, read-only). Every 5 s: one sample line (CSV); every change
of state: one event line. Only counts, names of games, sizes and times; never a person's files or text.
Usage: sudo python3 ronda.py PLACE UID APPID OUTDIR [max_seconds]"""
import glob, json, os, re, subprocess, sys, time

place, uid, appid, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
max_s = int(sys.argv[5]) if len(sys.argv) > 5 else 5400
cont = place + "doc"
home = f"/srv/bridgeai/places/{place}/desktop"
logs = f"{home}/.steam/debian-installation/logs"
hc = glob.glob(f"/srv/bridgeai/places/hostcache/{place}/SteamLibrary_steamapps_shadercache-*")
hc = hc[0] if hc else ""
os.makedirs(out, exist_ok=True)
ev = open(os.path.join(out, "events.log"), "a", buffering=1)
smp = open(os.path.join(out, "samples.csv"), "a", buffering=1)
if smp.tell() == 0:
    smp.write("time,container,steam,webhelpers,sunshine,sunshine_loops,prep,prep_pct,game,gpu_pct,power_w,vram_mb,mem_mb,swap_mb,mem_max_events,oom_kill,zswap_mb,merged_mb\n")

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

def procs():
    out = []
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if os.stat(d).st_uid != uid:
                continue
            comm = open(d + "/comm").read().strip()
            cmd = open(d + "/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
            out.append((comm, cmd))
        except OSError:
            pass
    return out

def cg():
    cid = sh(["docker", "inspect", "-f", "{{.Id}}", cont])
    p = f"/sys/fs/cgroup/system.slice/docker-{cid}.scope" if cid else ""
    return p if p and os.path.isdir(p) else ""

def rd(p, default=""):
    try:
        return open(p).read().strip()
    except OSError:
        return default

def merged_mb():
    if not hc:
        return ""
    fs = glob.glob(f"{hc}/{appid}/nvidiav1/GLCache/*/*/steamapp_merged_shader_cache.bin")
    return str(max((os.path.getsize(f) for f in fs), default=0) // 1048576)

def log_tail(path, pos):
    try:
        with open(path, errors="replace") as f:
            f.seek(0, 2); end = f.tell()
            if pos is None or pos > end:
                return end, []
            f.seek(pos); return end, f.read().splitlines()
    except OSError:
        return pos, []

last, pos_c, pos_s, t0 = {}, None, None, time.time()
ev.write(f"{time.strftime('%T')} recorder start place={place} appid={appid}\n")
while time.time() - t0 < max_s:
    ps = procs()
    state = sh(["docker", "inspect", "-f", "{{.State.Status}} {{.State.StartedAt}}", cont]).split()
    st = {
        "container": state[0] if state else "none",
        "started": state[1][:19] if len(state) > 1 else "",
        "steam": int(any(c == "steam" for c, _ in ps)),
        "webhelpers": sum(c == "steamwebhelper" for c, _ in ps),
        "sunshine": sum(c == "sunshine" for c, _ in ps),
        "sunshine_loops": sum("place-sunshine" in cmd and c != "sunshine" for c, cmd in ps),
        "prep": " ".join(sorted({m for _, cmd in ps if "fossilize_replay" in cmd for m in re.findall(r"shadercache[^/\s]*/(\d+)/", cmd)})),
        "game": " ".join(sorted({x for _, cmd in ps for x in re.findall(r"([A-Za-z0-9_]+\.exe)\b", cmd)
                                 if not re.match(r"(?i)(steam|wine|explorer|services|plugplay|winedevice|rpcss|svchost|conhost|tabtip|start|rundll32)", x)})),
    }
    pct = ""
    _, lines = log_tail(f"{logs}/shader_log.txt", max(0, os.path.getsize(f"{logs}/shader_log.txt") - 4000) if os.path.exists(f"{logs}/shader_log.txt") else None)
    for l in reversed(lines):
        m = re.search(r"Still replaying (\d+) \((\d+)%, (\d+)/(\d+)\)", l)
        if m:
            pct = f"{m.group(2)}% {m.group(3)}/{m.group(4)}"; break
    nv = sh(["nvidia-smi", "--query-gpu=utilization.gpu,power.draw,memory.used", "--format=csv,noheader,nounits"]).replace(" ", "").split(",")
    c = cg()
    mem = int(rd(c + "/memory.current", "0") or 0) // 1048576 if c else 0
    swap = int(rd(c + "/memory.swap.current", "0") or 0) // 1048576 if c else 0
    evs = dict(l.split() for l in rd(c + "/memory.events").splitlines() if len(l.split()) == 2) if c else {}
    zs = int(rd("/sys/kernel/debug/zswap/pool_total_size", "0") or 0) // 1048576
    smp.write(",".join(map(str, [time.strftime("%T"), st["container"], st["steam"], st["webhelpers"], st["sunshine"], st["sunshine_loops"], st["prep"], pct,
                                 st["game"], *(nv + ["", "", ""])[:3], mem, swap, evs.get("max", ""), evs.get("oom_kill", ""), zs, merged_mb()])) + "\n")
    for k in ("container", "started", "steam", "sunshine", "sunshine_loops", "prep", "game"):
        if last.get(k) != st[k]:
            ev.write(f"{time.strftime('%T')} {k}: {last.get(k)!r} -> {st[k]!r}" + (f"  (mem {mem} MB)" if k in ("game", "prep") else "") + "\n")
    if last.get("oom") is not None and evs.get("oom_kill") != last.get("oom"):
        ev.write(f"{time.strftime('%T')} OOM kill in the place (oom_kill {evs.get('oom_kill')})\n")
    last.update(st); last["oom"] = evs.get("oom_kill")
    for name, attr in (("content_log.txt", "c"), ("shader_log.txt", "s")):
        p = f"{logs}/{name}"
        pos = pos_c if attr == "c" else pos_s
        newpos, lines = log_tail(p, pos)
        for l in lines:
            if appid in l and re.search(r"update started|scheduler finished|Update Queued|Suspended|Starting processing|Done with replay|fossilize_replay completed|Queuing depot", l):
                ev.write(f"{time.strftime('%T')} steam[{name[:-8]}]: {l[:180]}\n")
        if attr == "c":
            pos_c = newpos
        else:
            pos_s = newpos
    time.sleep(5)
ev.write(f"{time.strftime('%T')} recorder end\n")
