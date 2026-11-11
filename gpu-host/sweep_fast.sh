#!/bin/bash
# Power sweep of fast SDXL variants, same method as ~/imggen/sweep.sh: for each cap run bench_fast.py in the comfy-bench
# container while sampling power.draw, SM clock and utilisation every 0.5 s; prints median seconds, average watts and Wh per image.
# Usage: sweep_fast.sh LABEL CKPT STEPS CFG SAMPLER SCHEDULER "CAPS" [runs]   e.g. sweep_fast.sh l4 sdxl_lightning_4step.safetensors 4 1.0 euler sgm_uniform "100 130 160 200"
# Needs the NOPASSWD rule for `nvidia-smi -pl`; restores the 100 W idle cap on exit (also on error). Never run while VR or Resolve is in use.
LABEL=$1 CKPT=$2 STEPS=$3 CFG=$4 SAMPLER=$5 SCHED=$6 CAPS=$7 RUNS=${8:-8}
trap 'sudo -n nvidia-smi -pl 100 >/dev/null; nvidia-smi --query-gpu=power.limit --format=csv,noheader' EXIT
cd ~/imggen
cat > extra_paths.yaml <<'YAML'
bench:
  base_path: /models
  checkpoints: |
    base
    gpu
YAML
for w in $CAPS; do
  sudo -n nvidia-smi -pl $w >/dev/null; t=fast-$LABEL-${w}w; rm -f out/$t.pwr
  nvidia-smi --query-gpu=power.draw,clocks.sm,utilization.gpu --format=csv,noheader,nounits -lms 500 > out/$t.pwr &
  smi=$!
  docker run --rm --gpus all -v ~/imggen:/w -v /mnt/resolve_test/bridgeai/models/comfyui/checkpoints:/models/base:ro \
    -v /mnt/resolve_test/bridgeai/gpu-media/models/checkpoints:/models/gpu:ro -e W=${W:-1024} -e H=${H:-1024} \
    comfy-bench python3 /w/bench_fast.py $LABEL-${w}w $CKPT $STEPS $CFG $SAMPLER $SCHED $RUNS > out/$t.json 2> out/$t.err
  kill $smi 2>/dev/null; wait $smi 2>/dev/null
  python3 - "$t" <<'PY'
import json, sys
t = sys.argv[1]
try:
    d = json.loads(open(f"out/{t}.json").read().strip().splitlines()[-1])
except Exception as e:
    print(t, "FAILED", e); raise SystemExit
imgs = sorted(d["image_s"]); med = imgs[len(imgs) // 2]
pw = []
for l in open(f"out/{t}.pwr"):
    p = [x.strip() for x in l.split(",")]
    if len(p) >= 3 and p[2].replace(".", "").isdigit() and float(p[2]) > 60:
        pw.append((float(p[0]), float(p[1])))
aw = sum(x for x, _ in pw) / len(pw) if pw else 0
print(f"{t}: ready {d['server_ready_s']}s warmup {d['warmup_s']}s median {med}s ({d['steps']} steps) avg {aw:.0f} W {sum(m for _, m in pw)/max(1, len(pw)):.0f} MHz -> {aw*med/3600:.3f} Wh/img (n={len(pw)})")
PY
done
