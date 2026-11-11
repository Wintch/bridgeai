#!/bin/bash
# Second pass: B1 ffmpeg (xfade fix), B1 Resolve (LUT fix), and the ComfyUI groups with cache busting. The first
# pass's ComfyUI rows are moved to results/results_comfy_cached.jsonl (runs 2-3 hit ComfyUI's output cache: not real timings).
cd "$(dirname "$0")"
step() { echo "== $(date +%T) $1"; shift; "$@" > results/$STEP.log 2>&1; echo "   rc=$? $(date +%T)"; }
python3 - <<'PY'
import json
rows = [l for l in open("results/results.jsonl") if l.strip()]
bad = lambda l: json.loads(l)["tag"].split("/")[0] in ("b3b", "b4", "b6", "b7", "b8") or json.loads(l)["tag"].startswith("b1/")
open("results/results_comfy_cached.jsonl", "a").writelines(l for l in rows if bad(l))
open("results/results.jsonl", "w").writelines(l for l in rows if not bad(l))
PY
STEP=b1_ffmpeg2  step "B1 ffmpeg" ./b1_ffmpeg.sh
STEP=b1_resolve2 step "B1 Resolve" bash -c 'rm -f results/b1_resolve.jsonl; ./b1_resolve.sh 3'
STEP=comfy_up2   step "ComfyUI up" ./comfy_server.sh start
STEP=b678v2      step "B6-B8, B3b, B4 (cache-busted)" ./b678_comfy.sh upscale interp matte wan5b wan14b
STEP=comfy_down2 step "ComfyUI down" ./comfy_server.sh stop
sudo -n nvidia-smi -pl 100 >/dev/null
python3 summarize.py > results/summary.md
echo "== all done $(date +%T)"
