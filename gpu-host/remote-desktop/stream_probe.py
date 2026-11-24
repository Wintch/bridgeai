#!/usr/bin/env python3
"""Light sampler for a game-streaming session on a GPU host (stdlib only). One CSV line every 2 s, a few extras every 10-30 s.
What it records follows what a rental panel's agent reports (GPU %, GPU watts, CPU, RAM, NIC rx/tx, is the stream up) plus what decides whether the
stream keeps its frame rate: the NVENC session's average fps and latency, the display refresh, power/thermal throttle reasons, clocks.
Stops after MAX_H hours, 20 min after the last encoder session, or when STOP_FILE exists. Output: ~/pipeline-measure/<start>/samples.csv + events.log"""
import os, re, subprocess, sys, threading, time, json, datetime
OUT = os.path.expanduser(f"~/pipeline-measure/{datetime.datetime.now():%Y%m%d-%H%M%S}")
os.makedirs(OUT, exist_ok=True)
STOP_FILE = "/tmp/stop_probe"; MAX_H = 5; IDLE_STOP_S = 1200; NIC = os.environ.get("NIC", "enp3s0")
SUN_LOG = os.path.expanduser("~/.config/sunshine/sunshine.log")
env = dict(os.environ, DISPLAY=":0")
enc_dec = {"enc": "", "dec": ""}
def dmon():
    p = subprocess.Popen(["nvidia-smi", "dmon", "-s", "u", "-d", "2"], stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        if line.startswith("#"): continue
        f = line.split()
        if len(f) >= 5: enc_dec["enc"], enc_dec["dec"] = f[3], f[4]
threading.Thread(target=dmon, daemon=True).start()
Q = "utilization.gpu,utilization.memory,power.draw,power.limit,clocks.sm,clocks.mem,temperature.gpu,pstate,clocks_event_reasons.active,encoder.stats.sessionCount,encoder.stats.averageFps,encoder.stats.averageLatency"
def smi():
    r = subprocess.run(["nvidia-smi", f"--query-gpu={Q}", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
    return [x.strip() for x in r.stdout.strip().split(",")]
def cpu():
    with open("/proc/stat") as f: v = list(map(int, f.readline().split()[1:8]))
    return sum(v), v[3] + v[4]
def nic():
    with open("/proc/net/dev") as f:
        for l in f:
            if l.strip().startswith(NIC + ":"):
                x = l.split(":")[1].split(); return int(x[0]), int(x[8])
    return 0, 0
def meminfo():
    for l in open("/proc/meminfo"):
        if l.startswith("MemAvailable"): return int(l.split()[1]) // 1024
def run(cmd):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=8, env=env).stdout
    except Exception: return ""
def refresh():
    m = re.search(r"^\s*(\S+)\s+([\d.]+)\*", run(["xrandr", "--current"]), re.M); return f"{m.group(1)}@{m.group(2)}" if m else ""
def client():
    ips = set(re.findall(r"(\d+\.\d+\.\d+\.\d+):\d+\s+users", run(["sh", "-c", "ss -tnp state established '( sport = :47984 or sport = :47989 or sport = :48010 or sport = :47990 )' 2>/dev/null"])))
    peers = re.findall(r"\s(\d+\.\d+\.\d+\.\d+):\d+\s", run(["sh", "-c", "ss -tn state established '( sport = :47984 or sport = :47989 or sport = :48010 )' 2>/dev/null"]))
    return ",".join(sorted(set(peers)))
def game():
    return "1" if run(["pgrep", "-f", "Proton|wine|GTAIV|GTA"]).strip() else "0"
ev = open(f"{OUT}/events.log", "a", buffering=1)
def event(msg): ev.write(f"{datetime.datetime.now():%H:%M:%S} {msg}\n")
sun_pos = os.path.getsize(SUN_LOG) if os.path.exists(SUN_LOG) else 0
csv = open(f"{OUT}/samples.csv", "a", buffering=1)
csv.write("t,gpu_pct,mem_pct,enc_pct,dec_pct,power_w,power_limit_w,sm_mhz,mem_mhz,temp_c,pstate,throttle_hex,enc_sessions,enc_avg_fps,enc_avg_latency_us,cpu_pct,load1,ram_avail_mb,rx_kBps,tx_kBps,game\n")
t0 = time.time(); last_c = cpu(); last_n = nic(); last_t = t0; last_stream = t0; seen_stream = False
event(f"start; display {refresh()}; client {client() or 'none yet'}")
tick = 0; last_mode = None; last_cli = None
while True:
    time.sleep(2); now = time.time(); tick += 1
    try: s = smi()
    except Exception as e: event(f"nvidia-smi failed: {e}"); continue
    c = cpu(); n = nic(); dt = now - last_t
    cpu_pct = round(100 * (1 - (c[1] - last_c[1]) / max(1, c[0] - last_c[0])), 1)
    rx = round((n[0] - last_n[0]) / dt / 1000, 1); tx = round((n[1] - last_n[1]) / dt / 1000, 1)
    last_c, last_n, last_t = c, n, now
    row = [f"{now:.0f}", s[0], s[1], enc_dec["enc"], enc_dec["dec"], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], s[10], s[11], cpu_pct, open("/proc/loadavg").read().split()[0], meminfo(), rx, tx, game() if tick % 5 == 0 else ""]
    csv.write(",".join(map(str, row)) + "\n")
    sess = int(s[9]) if s[9].isdigit() else 0
    if sess > 0: last_stream = now; seen_stream = True
    if tick % 15 == 0:
        m = refresh()
        if m != last_mode: event(f"display mode {m}"); last_mode = m
        cl = client()
        if cl != last_cli: event(f"stream client(s): {cl or 'none'}"); last_cli = cl
    if tick % 30 == 0 and os.path.exists(SUN_LOG):
        sz = os.path.getsize(SUN_LOG)
        if sz < sun_pos: sun_pos = 0
        with open(SUN_LOG, errors="replace") as f:
            f.seek(sun_pos); new = f.read(); sun_pos = f.tell()
        for l in new.splitlines():
            if re.search(r"Warning|Error|fps|Frame|frame|dropped|IDR|bitrate|Client|client|Resolution|resolution", l) and "NvFBC context" not in l and "cuda_t doesn't" not in l:
                event("sunshine: " + l[-160:])
    if os.path.exists(STOP_FILE) or now - t0 > MAX_H * 3600 or (seen_stream and now - last_stream > IDLE_STOP_S):
        event("stop: " + ("stop file" if os.path.exists(STOP_FILE) else "time limit" if now - t0 > MAX_H * 3600 else "stream ended 20 min ago")); break
