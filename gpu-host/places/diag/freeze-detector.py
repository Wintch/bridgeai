#!/usr/bin/env python3
"""Freeze detector for a place (root, read-only): every 100 ms reads the container's pressure-stall counters (PSI "full" = every task in
the container waiting at once: what the person feels as a freeze, audio included) for io, memory and cpu, plus reclaim hits (memory.events
max), page cache refaults and disk reads. A window with >= 20 ms of full stall starts a freeze; consecutive windows join. One line per
freeze (start, length, ms stalled per cause, reclaims, refaults, MB read) and a per-minute summary. Usage: freeze.py CONTAINER OUTDIR SECONDS"""
import os, subprocess, sys, time

cont, out, secs = sys.argv[1], sys.argv[2], int(sys.argv[3])
def resolve():
    cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", cont], capture_output=True, text=True).stdout.strip()
    return f"/sys/fs/cgroup/system.slice/docker-{cid}.scope"
cg = resolve()
os.makedirs(out, exist_ok=True)
fz = open(os.path.join(out, "freezes.log"), "a", buffering=1)
mn = open(os.path.join(out, "freeze-minutes.csv"), "a", buffering=1)
if mn.tell() == 0:
    mn.write("minute,freezes,longest_ms,stall_ms_io,stall_ms_mem,stall_ms_cpu,reclaims,refaults,read_mb\n")

def full(res):
    try:
        for l in open(f"{cg}/{res}.pressure"):
            if l.startswith("full"):
                return int(l.split("total=")[1])
    except (OSError, IndexError, ValueError):
        pass
    return 0

def stat(key, path="memory.stat"):
    try:
        for l in open(f"{cg}/{path}"):
            k, v = l.split()[:2]
            if k == key:
                return int(v)
    except (OSError, ValueError):
        pass
    return 0

def ev():
    try:
        for l in open(f"{cg}/memory.events"):
            k, v = l.split()
            if k == "max":
                return int(v)
    except (OSError, ValueError):
        pass
    return 0

def rbytes():
    try:
        for l in open(f"{cg}/io.stat"):
            pass
        return sum(int(x.split("=")[1]) for l in open(f"{cg}/io.stat") for x in l.split() if x.startswith("rbytes="))
    except (OSError, ValueError, IndexError):
        return 0

def snap():
    return {"io": full("io"), "mem": full("memory"), "cpu": full("cpu"), "rec": ev(), "ref": stat("workingset_refault_file"), "rd": rbytes()}

prev, t0 = snap(), time.time()
cur = None
minute = {"k": time.strftime("%H:%M"), "n": 0, "long": 0, "io": 0, "mem": 0, "cpu": 0, "rec": 0, "ref": 0, "rd": 0}
fz.write(f"{time.strftime('%T')} freeze detector start {cont}\n")
while time.time() - t0 < secs:
    time.sleep(0.1)
    if not os.path.isdir(cg):                       # the place was stopped or recreated: wait for its new container
        time.sleep(2); cg = resolve()
        if os.path.isdir(cg):
            fz.write(f"{time.strftime('%T')} following the new container\n"); prev = snap(); cur = None
        continue
    now = snap()
    d = {k: now[k] - prev[k] for k in now}
    prev = now
    k = time.strftime("%H:%M")
    if k != minute["k"]:
        mn.write(f"{minute['k']},{minute['n']},{minute['long']},{minute['io']//1000},{minute['mem']//1000},{minute['cpu']//1000},{minute['rec']},{minute['ref']},{minute['rd']//1048576}\n")
        minute = {"k": k, "n": 0, "long": 0, "io": 0, "mem": 0, "cpu": 0, "rec": 0, "ref": 0, "rd": 0}
    for x in ("io", "mem", "cpu", "rec", "ref", "rd"):
        minute[x] += d[x]
    stalled = max(d["io"], d["mem"], d["cpu"])          # microseconds of full stall in this 100 ms window
    if stalled >= 20000:
        if cur is None:
            cur = {"start": time.time(), "io": 0, "mem": 0, "cpu": 0, "rec": 0, "ref": 0, "rd": 0, "win": 0}
        for x in ("io", "mem", "cpu", "rec", "ref", "rd"):
            cur[x] += d[x]
        cur["win"] += 1
    elif cur is not None:
        length = int((time.time() - cur["start"]) * 1000)
        minute["n"] += 1
        minute["long"] = max(minute["long"], length)
        cause = max(("io", "mem", "cpu"), key=lambda x: cur[x])
        fz.write(f"{time.strftime('%T', time.localtime(cur['start']))} FREEZE ~{length} ms  cause={cause}  full_ms io={cur['io']//1000} mem={cur['mem']//1000} "
                 f"cpu={cur['cpu']//1000}  reclaims={cur['rec']} refaults={cur['ref']} read={cur['rd']//1048576}MB\n")
        cur = None
fz.write(f"{time.strftime('%T')} freeze detector end\n")
