#!/bin/bash
# B3: Wan 2.2 TI2V-5B text-to-video, local baseline (VIDEO_TOOLS_EVAL.md section 3). Reuses the 2026-10 bench script
# ~/imggen/video.py (Diffusers weights already on disk, bf16 streamed to the GPU per layer, prompt embedding cached, 30 steps)
# in the tts-chatterbox image with diffusers from ~/imggen/pkgs. measure.py times the whole run (load + denoise + VAE + mux).
# Caps are set with the allowed `sudo -n nvidia-smi -pl` and put back to 100 W on exit (the VR watchdog only acts on changes).
# Usage: b3_wan5b.sh            Results: results/results.jsonl (tag b3/...), results/b3/*.log, ~/imggen/out/wan-*.mp4
set -uo pipefail
cd "$(dirname "$0")"
O=results/b3; mkdir -p $O
trap 'sudo -n nvidia-smi -pl 100 >/dev/null' EXIT
run() {  # tag cap frames HxW
  sudo -n nvidia-smi -pl $2 >/dev/null
  python3 measure.py b3/$1 --out-units $(python3 -c "print(round($3/24,3))") --unit s_video -- \
    docker run --rm --name vb-wan --gpus all --network none -v ~/imggen:/w -v /mnt/resolve_test/bridgeai/models/imggen/hf:/w/hf \
      -e PYTHONPATH=/w/pkgs -e HF_HOME=/w/hf -e HF_HUB_OFFLINE=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
      --entrypoint python3 tts-chatterbox /w/video.py vb-${1//\//_} 30 $3 $4 > $O/${1//\//_}.log 2>&1
  grep -h '^{' $O/${1//\//_}.log | tr '\n' ' '; echo
}
for cap in 100 130 159; do
  for rep in 1 2; do run wan5b-49f-480p-${cap}w/r$rep $cap 49 480x832; done
done
run wan5b-81f-480p-100w 100 81 480x832
run wan5b-49f-704p-100w 100 49 704x1280
