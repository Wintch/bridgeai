#!/usr/bin/env python3
"""places_report: what the desktop places cost and how many sessions the host could carry, from the gate's metrics log (places-metrics.csv).

  places_report.py [CSV] [--since MINUTES] [--threads N] [--reserve-threads N] [--ram-gb G] [--target PCT]

The gate appends one row per running place per minute (`place_control.py`): whether the person was using it, its container's CPU, memory and outgoing
network rate, the video memory it holds, and the card's totals (use, encoder, VRAM, power, temperature). This reads it and prints
  1. the cost of one session in use (mean of the rows where somebody touched the screen; all rows if nobody did),
  2. how the card scales with the number of places open (mean card figures grouped by how many places were running),
  3. an estimate of how many sessions like those fit, per resource, and which one runs out first.
The estimate is only as good as the log: it assumes the next session costs what the logged ones did (a Quake-class game and a modern one differ by an order of
magnitude in VRAM), keeps --target % (default 80) of the card's use and encoder, and --reserve-threads (default 2) threads and 1 GB of VRAM for the host's own desktop.
Stdlib only."""
import argparse, csv, os, sys
from collections import defaultdict

DEFAULT = os.path.join(os.path.expanduser("~"), ".local", "state", "bridgeai-gate", "places-metrics.csv")


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def load(path, since_min=None):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("ts"):
                rows.append(r)
    if since_min and rows:
        last = max(fnum(r["ts"]) or 0 for r in rows)
        rows = [r for r in rows if (fnum(r["ts"]) or 0) >= last - since_min * 60]
    return rows


def analyse(rows, threads, reserve, ram_gb, target):
    if not rows:
        return None
    used = [r for r in rows if r.get("in_use") == "1"]
    basis, basis_name = (used, "rows with the screen in use") if used else (rows, "all rows (nobody was using a screen)")
    cost = {"cpu_cores": (mean(fnum(r["cpu_pct"]) for r in basis) or 0) / 100, "mem_mb": mean(fnum(r["mem_mb"]) for r in basis), "net_kbps": mean(fnum(r["net_tx_kbps"]) for r in basis),
            "vram_mb": mean(fnum(r["place_vram_mb"]) for r in basis)}
    by_ts = defaultdict(list)
    for r in rows:
        by_ts[r["ts"]].append(r)
    ticks = []
    for ts, rs in by_ts.items():
        g = rs[0]
        n = len(rs)
        placev = sum(fnum(r["place_vram_mb"]) or 0 for r in rs)
        ticks.append({"n": n, "sm": fnum(g["gpu_sm_pct"]), "enc": fnum(g["gpu_enc_pct"]), "used": fnum(g["gpu_vram_used_mb"]), "total": fnum(g["gpu_vram_total_mb"]),
                      "power": fnum(g["gpu_power_w"]), "temp": fnum(g["gpu_temp_c"]), "host_vram": (fnum(g["gpu_vram_used_mb"]) or 0) - placev,
                      "cpu": sum(fnum(r["cpu_pct"]) or 0 for r in rs) / 100})
    curve = {}
    for n in sorted({t["n"] for t in ticks}):
        ts_n = [t for t in ticks if t["n"] == n]
        curve[n] = {k: mean(t[k] for t in ts_n) for k in ("sm", "enc", "used", "power", "temp", "cpu")} | {"ticks": len(ts_n)}
    total_vram = mean(t["total"] for t in ticks) or 0
    host_vram = mean(t["host_vram"] for t in ticks) or 0
    per_enc = mean((t["enc"] or 0) / t["n"] for t in ticks if t["n"]) or 0
    per_sm = mean((t["sm"] or 0) / t["n"] for t in ticks if t["n"]) or 0
    caps = {}
    if cost["vram_mb"] and cost["vram_mb"] > 0:
        caps["VRAM"] = int(max(0, total_vram - host_vram - 1024) // cost["vram_mb"])
    if per_enc > 0:
        caps["NVENC"] = int(target // per_enc)
    if per_sm > 0:
        caps["GPU use"] = int(target // per_sm)
    if cost["cpu_cores"] > 0:
        caps["CPU"] = int(max(0, threads - reserve) // cost["cpu_cores"])
    if cost["mem_mb"]:
        caps["RAM"] = int(max(0, ram_gb * 1000 - 6000) // cost["mem_mb"])
    return {"basis": basis_name, "n_rows": len(rows), "cost": cost, "curve": curve, "host_vram": host_vram, "total_vram": total_vram, "caps": caps,
            "span_min": round(((max(fnum(r["ts"]) for r in rows) - min(fnum(r["ts"]) for r in rows)) / 60), 1)}


def fmt(x, nd=1, unit=""):
    return "-" if x is None else f"{x:.{nd}f}{unit}"


def render(a):
    if a is None:
        return "no rows in the log yet (the gate writes one per running place per minute)"
    out = [f"{a['n_rows']} rows over {a['span_min']} min; the cost below is the mean of the {a['basis']}.", "",
           "One session:", f"  CPU        {fmt(a['cost']['cpu_cores'], 2)} cores", f"  RAM        {fmt(a['cost']['mem_mb'], 0)} MB",
           f"  VRAM       {fmt(a['cost']['vram_mb'], 0)} MB", f"  stream out {fmt(a['cost']['net_kbps'], 0)} kbit/s", "",
           f"The card by places open (the host's own desktop holds about {a['host_vram']:.0f} MB of {a['total_vram']:.0f} MB):",
           "  places  ticks   GPU%   NVENC%   VRAM MB   power W   temp C   place CPU cores"]
    for n, c in a["curve"].items():
        out.append(f"  {n:>6}  {c['ticks']:>5}  {fmt(c['sm'], 0):>5}  {fmt(c['enc'], 0):>7}  {fmt(c['used'], 0):>8}  {fmt(c['power'], 0):>8}  {fmt(c['temp'], 0):>7}   {fmt(c['cpu'], 2)}")
    out.append("")
    if a["caps"]:
        first = min(a["caps"], key=a["caps"].get)
        out.append("Sessions like these that fit, by resource: " + ", ".join(f"{k} {v}" for k, v in a["caps"].items()))
        out.append(f"  -> about {a['caps'][first]}, and {first} runs out first.")
    else:
        out.append("Not enough data for an estimate.")
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("csv", nargs="?", default=os.environ.get("PLACE_METRICS_FILE") or DEFAULT)
    p.add_argument("--since", type=float, help="only the last MINUTES of the log")
    p.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    p.add_argument("--reserve-threads", type=int, default=2)
    p.add_argument("--target", type=float, default=80.0)
    ram = 32.0
    try:
        ram = int(next(l for l in open("/proc/meminfo") if l.startswith("MemTotal")).split()[1]) / 1e6
    except (OSError, StopIteration, ValueError):
        pass
    p.add_argument("--ram-gb", type=float, default=ram)
    a = p.parse_args(argv)
    try:
        rows = load(a.csv, a.since)
    except OSError:
        print(f"no log at {a.csv}", file=sys.stderr)
        return 1
    print(render(analyse(rows, a.threads, a.reserve_threads, a.ram_gb, a.target)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
