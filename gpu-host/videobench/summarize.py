#!/usr/bin/env python3
"""Tables from results/results.jsonl (+ b2_quality2.jsonl): median of the repeated runs per config, Markdown out.
Usage: summarize.py [results dir]"""
import collections, json, os, statistics, sys

D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
rows = [json.loads(l) for l in open(os.path.join(D, "results.jsonl")) if l.strip()]
groups = collections.OrderedDict()
for r in rows:
    key = r["tag"].rsplit("/r", 1)[0] if "/r" in r["tag"] else r["tag"]
    groups.setdefault(key, []).append(r)
q = {}
qf = os.path.join(D, "b2_quality2.jsonl")
if os.path.exists(qf):
    for l in open(qf):
        if l.strip():
            x = json.loads(l); q[(x["clip"], x["enc"])] = x


IDLE_W = float(os.environ.get("VB_IDLE_W", "18"))   # the measured idle is inflated when the GPU has not yet left P2 after the
                                                     # previous run (seen: 47-51 W), so net Wh uses the real resting draw


def net(r):
    return max(0.0, r["gpu_wh"] - IDLE_W * r["wall_s"] / 3600)


def med(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


print(f"Net Wh = gross GPU Wh minus {IDLE_W:.0f} W idle x wall time. CPU energy not measured (RAPL needs root).\n")
print("| config | runs | wall s (median / worst) | GPU avg W | GPU net Wh | VRAM MiB | RAM peak GB | CPU core-s | size kb/s | SSIM | PSNR |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for k, rs in groups.items():
    ok = [r for r in rs if r.get("rc") == 0]
    if not ok:
        print(f"| {k} | {len(rs)} | FAILED rc={rs[-1].get('rc')} | | | | | | | | |"); continue
    w = [r["wall_s"] for r in ok]
    extra = ["", "", ""]
    if k.startswith("b2/"):
        _, clip, enc = k.split("/")
        x = q.get((clip, enc))
        if x:
            extra = [str(x["kbps"]), f"{x['ssim']:.4f}" if x.get("ssim") else "", f"{x['psnr']:.2f}" if x.get("psnr") else ""]
    print(f"| {k} | {len(ok)} | {med(w):.1f} / {max(w):.1f} | {med([r['gpu_avg_w'] for r in ok]):.0f} | "
          f"{med([net(r) for r in ok]):.3f} | {max(r['vram_peak_mib'] for r in ok)} | {max(r['ram_peak_gb'] for r in ok):.1f} | "
          f"{med([r['cpu_busy_core_s'] for r in ok]):.0f} | " + " | ".join(extra) + " |")
