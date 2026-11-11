#!/usr/bin/env python3
"""Run one benchmark command on the GPU workstation and record what it cost (VIDEO_TOOLS_EVAL.md section 3).

  measure.py TAG [--out-units N --unit frames|s] -- command ...

Samples every 0.5 s while the command runs: GPU power draw, VRAM used, GPU utilisation (nvidia-smi -lms 500), system RAM
used (MemTotal - MemAvailable) and CPU busy time from /proc/stat. Idle GPU power is the median of 2 s sampled before the
start, so net Wh = gross Wh - idle W x duration. CPU energy is NOT measured here (RAPL needs root on this host): busy
core-seconds are recorded instead. One JSON line per run is appended to results/results.jsonl and printed.
"""
import json, os, statistics, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.environ.get("VB_RESULTS", os.path.join(HERE, "results", "results.jsonl"))


def gpu_sampler(stop, rows):
    p = subprocess.Popen(["nvidia-smi", "--query-gpu=power.draw,memory.used,utilization.gpu", "--format=csv,noheader,nounits",
                          "-lms", "500"], stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        try:
            w, mem, util = (float(x) for x in line.split(","))
        except ValueError:
            continue
        rows.append((time.time(), w, mem, util))
        if stop.is_set():
            break
    p.terminate()


def cpu_busy():
    f = open("/proc/stat").readline().split()[1:]
    v = [int(x) for x in f]
    idle = v[3] + v[4]
    return (sum(v) - idle) / os.sysconf("SC_CLK_TCK")


def ram_used_gb():
    m = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":")
        m[k] = int(v.split()[0])
    return (m["MemTotal"] - m["MemAvailable"]) / 2**20


def main():
    a = sys.argv[1:]
    if "--" not in a or not a or a[0] == "--":
        sys.exit(__doc__)
    i = a.index("--")
    opts, cmd = a[:i], a[i + 1:]
    tag = opts[0]
    units = float(opts[opts.index("--out-units") + 1]) if "--out-units" in opts else None
    unit = opts[opts.index("--unit") + 1] if "--unit" in opts else "frames"

    idle_rows, stop0 = [], threading.Event()
    th = threading.Thread(target=gpu_sampler, args=(stop0, idle_rows), daemon=True); th.start()
    time.sleep(2.2); stop0.set(); th.join(3)
    idle_w = statistics.median(r[1] for r in idle_rows) if idle_rows else 0.0
    base_ram = ram_used_gb()

    rows, stop = [], threading.Event()
    th = threading.Thread(target=gpu_sampler, args=(stop, rows), daemon=True); th.start()
    ram_peak, c0, t0 = base_ram, cpu_busy(), time.time()
    proc = subprocess.Popen(cmd)
    while proc.poll() is None:
        ram_peak = max(ram_peak, ram_used_gb())
        time.sleep(0.5)
    t1, c1 = time.time(), cpu_busy()
    stop.set(); th.join(3)

    dur = t1 - t0
    run = [r for r in rows if t0 <= r[0] <= t1] or rows
    wh = 0.0
    pts = [(t0, run[0][1])] + [r[:2] for r in run] + [(t1, run[-1][1])] if run else []   # cover the whole window
    for (ta, wa), (tb, wb) in zip(pts, pts[1:]):
        wh += (wa + wb) / 2 * (tb - ta) / 3600
    res = {
        "tag": tag, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "rc": proc.returncode, "wall_s": round(dur, 2),
        "power_limit_w": subprocess.run(["nvidia-smi", "--query-gpu=power.limit", "--format=csv,noheader,nounits"],
                                        capture_output=True, text=True).stdout.strip(),
        "gpu_idle_w": round(idle_w, 1),
        "gpu_avg_w": round(statistics.mean(r[1] for r in run), 1) if run else None,
        "gpu_peak_w": round(max(r[1] for r in run), 1) if run else None,
        "gpu_wh": round(wh, 4), "gpu_net_wh": round(max(0.0, wh - idle_w * dur / 3600), 4),
        "vram_peak_mib": int(max(r[2] for r in run)) if run else None,
        "gpu_util_avg": round(statistics.mean(r[3] for r in run), 1) if run else None,
        "ram_peak_gb": round(ram_peak, 2), "ram_delta_gb": round(ram_peak - base_ram, 2),
        "cpu_busy_core_s": round(c1 - c0, 1), "samples": len(run),
    }
    if units:
        res["out_units"], res["unit"] = units, unit
        res["s_per_unit"] = round(dur / units, 4)
        res["gpu_net_wh_per_unit"] = round(res["gpu_net_wh"] / units, 5)
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "a") as f:
        f.write(json.dumps(res) + "\n")
    print(json.dumps(res), flush=True)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
