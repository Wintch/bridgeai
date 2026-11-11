#!/bin/bash
# Everything after B2, strictly one benchmark at a time: inputs, B2 quality, B1 (ffmpeg, Resolve), B3 (Wan 5B Diffusers),
# then the ComfyUI groups once fetch_models.sh is done. Each step logs to results/<step>.log. Usage: nohup ./run_all.sh &
cd "$(dirname "$0")"
step() { echo "== $(date +%T) $1"; shift; "$@" > results/$STEP.log 2>&1; echo "   rc=$? $(date +%T)"; }
STEP=inputs   step inputs ./make_inputs.sh
STEP=quality  step "B2 quality" bash -c './quality.sh > results/b2_quality2.jsonl'
STEP=b1_ffmpeg  step "B1 ffmpeg" ./b1_ffmpeg.sh
STEP=b1_resolve step "B1 Resolve" ./b1_resolve.sh 3
STEP=b3       step "B3 Wan 5B Diffusers" ./b3_wan5b.sh
while pgrep -f fetch_models.sh >/dev/null; do sleep 30; done
STEP=comfy_up step "ComfyUI up" ./comfy_server.sh start
STEP=b678     step "B6-B8, B3b, B4" ./b678_comfy.sh upscale interp matte wan5b wan14b
STEP=comfy_down step "ComfyUI down" ./comfy_server.sh stop
STEP=b1_ffmpeg2 step "B1 ffmpeg (fixed)" ./b1_ffmpeg.sh
sudo -n nvidia-smi -pl 100 >/dev/null
python3 summarize.py > results/summary.md
echo "== all done $(date +%T)"
