#!/usr/bin/env bash
# Start (or restart) every service of a GPU host, with the settings measured on 2026-10-09 on the 1070 Ti desktop
# (8 GB). VM105 reaches them by host name (`gpu-desktop` and the others in ops/gateways.json); nothing here is
# person-specific.
#
#   gpu-host/run_services.sh            run all (restarts the ones already running)
#   gpu-host/run_services.sh llm tts    only these
#   gpu-host/run_services.sh stop       stop all, e.g. to free the GPU for VR/games; the stacks use the next host
# GPU power cap: gpu_power.sh (cron every minute, `gpu-host/gpu_power.sh --install`) keeps LLM_POWER_W while llm runs.
#   BUILD=1 gpu-host/run_services.sh    build the images first (from this repo)
#
# Port  Service      What                                                  VRAM (with the others loaded)
# 8600  upscaler     4x image upscale                                      ~0.2 GB idle
# 8610  transcoder   NVENC video jobs                                      only while encoding
# 8620  stt          faster-whisper large-v3-turbo int8, es/ru/en          ~1.0 GB
# 8630  llm          llama.cpp + Gemma 4 E4B (Q4, vision), 2 slots / 80k   ~5.6 GB
# 8640  tts          Piper on CPU, voice by the text's language            0
# Total ~7.1 GB of 8: do not raise the llm context (-c) or add slots without measuring.
#
# MODELS_DIR holds the GGUF files (on the desktop: the NVMe, mounted at /mnt/nvme; needs its fstab line with
# `nofail` or llm cannot start after a reboot). Per-host settings go in gpu-host/host.env (not in git), e.g.
# `MODELS_DIR=/mnt/<data disk>/bridgeai/models` on a host whose system disk is small.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f gpu-host/host.env ] && . gpu-host/host.env
ALL=(upscaler transcoder stt llm tts)
if [ "${1:-}" = stop ]; then
  docker stop "${ALL[@]}" 2>/dev/null || true
  gpu-host/gpu_power.sh            # back to the cap from before the home model ran
  exit 0
fi
MODELS_DIR=${MODELS_DIR:-/mnt/nvme/bridgeai-models}
VOICE_ES=${VOICE_ES:-es_AR-daniela-high}       # chosen by ear by the operator, 2026-10-09
VOICE_RU=${VOICE_RU:-ru_RU-ruslan-medium}
SEL=("$@")
sel() { [ ${#SEL[@]} -eq 0 ] || [[ " ${SEL[*]} " == *" $1 "* ]]; }

if [ "${BUILD:-0}" = 1 ]; then
  sel upscaler   && docker build -t upscaler:latest upscaler
  sel transcoder && docker build -t transcoder:latest transcoder
  sel stt        && docker build -t stt:gpu stt
  sel llm        && docker build -t llm:cuda llm
  sel tts        && docker build -t tts-piper:multi -f tts/Dockerfile.piper tts
fi

run() { local name=$1; shift; docker rm -f "$name" >/dev/null 2>&1 || true; docker run -d --name "$name" --restart unless-stopped "$@" >/dev/null && echo "started $name"; }

sel upscaler   && run upscaler   --gpus all -p 8600:8600 upscaler:latest
sel transcoder && run transcoder --gpus all -e NVIDIA_DRIVER_CAPABILITIES=video,compute,utility -p 8610:8610 transcoder:latest
sel stt        && run stt        --gpus all -p 8620:8620 -v stt-models:/models stt:gpu
if sel llm; then
  [ -f "$MODELS_DIR/gemma-4-E4B_q4_0-it.gguf" ] || { echo "llm: $MODELS_DIR/gemma-4-E4B_q4_0-it.gguf missing (NVMe not mounted?)" >&2; exit 1; }
  # -np 2 -kvu: Hermes's small calls (title, memory) take the second slot instead of evicting the conversation cache.
  # 80k shared: Hermes needs >= 64k; 96k + vision left too little VRAM for the upscaler and NVENC.
  run llm --gpus all -p 8630:8630 -v "$MODELS_DIR":/m:ro llm:cuda \
    -m /m/gemma-4-E4B_q4_0-it.gguf --mmproj /m/gemma-4-E4B-mmproj-Q8_0.gguf --alias gemma-4-e4b \
    -ngl 99 -fa on -c 81920 -np 2 -kvu --jinja
fi
sel tts && run tts --init -p 8640:5002 --cpus 4 --memory 1g -e VOICE_ES="$VOICE_ES" -e VOICE_RU="$VOICE_RU" tts-piper:multi

sleep 3
gpu-host/gpu_power.sh              # the measured optimum cap while llm runs (LLM_POWER_W in host.env)
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
