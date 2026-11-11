#!/bin/bash
# Power sweep of the Blender Cycles benchmark, same method as sweep_fast.sh: for each cap run ~/imggen/blender_bench.py
# (procedural 4K scene, OptiX, three denoise modes, best of 3 after a warm-up) while sampling power.draw, SM clock and utilisation every
# 0.5 s; prints the benchmark's best times, the average busy watts and Wh per render. Restores the 100 W idle cap on exit.
# Usage: sweep_blender.sh LABEL "CAPS"      e.g. sweep_blender.sh stock "100 130 200"
LABEL=$1 CAPS=$2
BL=/mnt/resolve_test/tools/blender/blender-5.1.2-linux-x64/blender
trap 'sudo -n nvidia-smi -pl 100 >/dev/null; nvidia-smi --query-gpu=power.limit --format=csv,noheader' EXIT
cd ~/imggen
for w in $CAPS; do
  sudo -n nvidia-smi -pl $w >/dev/null; t=blender-$LABEL-${w}w; rm -f out/$t.pwr
  nvidia-smi --query-gpu=power.draw,clocks.sm,utilization.gpu --format=csv,noheader,nounits -lms 500 > out/$t.pwr &
  smi=$!
  $BL -b --factory-startup -P blender_bench.py -- $LABEL-${w}w > out/$t.log 2>&1
  kill $smi 2>/dev/null; wait $smi 2>/dev/null
  python3 - "$t" <<'PY'
import json, sys
t = sys.argv[1]
try:
    d = json.loads([l for l in open(f"out/{t}.log") if l.startswith("{")][-1])
except Exception as e:
    print(t, "FAILED", e); raise SystemExit
pw = []
for l in open(f"out/{t}.pwr"):
    p = [x.strip() for x in l.split(",")]
    if len(p) >= 3 and p[2].replace(".", "").isdigit() and float(p[2]) > 60:
        pw.append((float(p[0]), float(p[1])))
aw = sum(x for x, _ in pw) / len(pw) if pw else 0
mhz = sum(m for _, m in pw) / max(1, len(pw))
out = []
for k in ("off", "optix", "oidn_gpu"):
    s = d[k]["best_s"]; out.append(f"{k} {s}s {aw*s/3600:.3f}Wh")
print(f"{t}: blender {d['blender']} avg {aw:.0f} W {mhz:.0f} MHz | " + " | ".join(out) + f" (n={len(pw)})")
PY
done
