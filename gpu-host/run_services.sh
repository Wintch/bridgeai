#!/usr/bin/env bash
# Start (or restart) every service of a GPU host, with settings measured on an 8 GB card.
# The Docker host reaches them by the host names in ops/gateways.json; nothing here is person-specific.
#
#   gpu-host/run_services.sh            run all (restarts the ones already running)
#   gpu-host/run_services.sh llm tts    only these
#   gpu-host/run_services.sh stop       stop all, e.g. to free the GPU for VR/games; the stacks use the next host
# GPU power cap: gpu_power.sh (cron every minute, `gpu-host/gpu_power.sh --install`) keeps LLM_POWER_W while llm runs.
#   BUILD=1 gpu-host/run_services.sh    build the images first (from this repo)
#
# Port  Service      What                                                  VRAM alone (measured on the media host, warm)
# 8600  upscaler     4x image upscale                                      ~0.2 GB, ready in ~3 s
# 8610  transcoder   NVENC video jobs                                      ~0 GB idle, ready in ~1 s
# 8620  stt          faster-whisper large-v3-turbo int8, es/ru/en          ~1.1 GB, ready in ~3 s warm (~13 s right after a cold boot)
# 8630  llm          llama.cpp + Gemma 4 E4B (Q4, vision), 2 slots / 80k   ~5.1 GB, ready in ~3 s warm
# 8640  tts          Piper on CPU, voice by the text's language            0, ready in ~2 s
# 8650  tts-hq       Chatterbox Multilingual (opt-in: TTS_HQ=1 in host.env) ~3.5 GB, ready in ~35 s ALWAYS (PyTorch model
#                    load + GPU warm-up, not disk I/O, so this one never gets faster on a warm host) -- and Pascal cards
#                    can't run it at all, recent PyTorch dropped Pascal support.
# 8660  imggen       text to image (klein/Z-Image/SDXL, IMAGE_TOKEN)        0 idle, ~7.5 GB during a job and IDLE_S after it
# 8670  vidgen       text to video with sound (MiniMax H3, VIDEO_TOKEN)    0 idle, ~7.6 GB + ~18 GB RAM during a job (minutes)
# 8680  vidpost      2x upscale and 48 fps for a short video (VIDPOST_TOKEN) 0 idle, ~6 GB RAM during a job (in pieces); Pascal: vidpost/run_venv.sh
# 8690  mosher       datamosh with FFglitch (MOSH_TOKEN), CPU only            0 VRAM; work in a 1 GB tmpfs (RAM), no disk writes
# llm + tts-hq together need ~8.6 GB: never fits on an 8 GB card. Set LLM=0 in host.env to dedicate a host to voice
# (stt + tts-hq + tts, ~4.9 GB, leaves ~3 GB of headroom) instead of swapping the two in and out on demand.
# Total with llm: ~6.4 GB of 8. Do not raise the llm context (-c) or add slots without measuring.
#
# MODELS_DIR holds the GGUF files (on the desktop: the NVMe, mounted at /mnt/nvme; needs its fstab line with
# `nofail` or llm cannot start after a reboot). Per-host settings go in gpu-host/host.env (not in git), e.g.
# `MODELS_DIR=/mnt/<data disk>/bridgeai/models` on a host whose system disk is small.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f gpu-host/host.env ] && . gpu-host/host.env
ALL=(upscaler transcoder stt tts imggen vidgen vidpost mosher)
[ "${LLM:-1}" = 1 ] && ALL+=(llm)
[ "${TTS_HQ:-0}" = 1 ] && ALL+=(tts-hq)
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
  sel imggen     && docker build -t imggen:latest gpu-host/imggen
  sel vidgen     && docker build -t vidgen:latest gpu-host/vidgen
  sel vidpost    && docker build -t vidpost:latest gpu-host/vidpost
  sel mosher     && docker build -t mosher:latest gpu-host/mosher
  sel stt        && docker build -t stt:gpu stt
  sel llm        && docker build -t llm:cuda llm
  sel tts        && docker build -t tts-piper:multi -f tts/Dockerfile.piper tts
  sel tts-hq     && docker build -t tts-chatterbox -f tts/Dockerfile.chatterbox tts
fi

# GPU_BIND_ADDR (host.env, e.g. the LAN address the production VM reaches): publish every port only there instead of on all
# interfaces (4.1/13.1). GPU_RESTART (host.env): the restart policy, default "no" (on demand: a service runs only while
# needed, and a reboot leaves the GPU free); "unless-stopped" only for a host dedicated to these services.
run() {
  local name=$1; shift; local args=() prev=
  for a in "$@"; do
    if [ "$prev" = -p ] && [ -n "${GPU_BIND_ADDR:-}" ]; then a="$GPU_BIND_ADDR:$a"; fi
    args+=("$a"); prev=$a
  done
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --restart "${GPU_RESTART:-no}" "${args[@]}" >/dev/null && echo "started $name"
}

# UPSCALE_TOKEN / TRANSCODE_TOKEN (host.env; recommended, these ports are reachable from the LAN): the service then requires
# "Authorization: Bearer <token>"; register the same token for the stacks with
#   python3 ops/gateways_host_service.py HOST upscale 8600 --token-stdin   (and: HOST transcode 8610 --token-stdin), then gateways_sync.
# Both run without capabilities, without privilege escalation and with a process and memory cap.
HARDEN=(--cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --log-opt max-size=1m --log-opt max-file=2)
sel upscaler   && run upscaler   --gpus all "${HARDEN[@]}" --memory 12g -p 8600:8600 ${UPSCALE_TOKEN:+-e UPSCALE_TOKEN="$UPSCALE_TOKEN"} upscaler:latest
sel transcoder && run transcoder --gpus all "${HARDEN[@]}" --memory 8g -e NVIDIA_DRIVER_CAPABILITIES=video,compute,utility -p 8610:8610 ${TRANSCODE_TOKEN:+-e TRANSCODE_TOKEN="$TRANSCODE_TOKEN"} transcoder:latest
[ -n "${UPSCALE_TOKEN:-}" ] || ! sel upscaler || echo "upscaler: no UPSCALE_TOKEN in host.env: anyone on the LAN can use it" >&2
[ -n "${TRANSCODE_TOKEN:-}" ] || ! sel transcoder || echo "transcoder: no TRANSCODE_TOKEN in host.env: anyone on the LAN can use it" >&2
# imggen (8660): text to image. IMAGE_TOKEN is required (host.env); the SDXL checkpoints are read from IMGGEN_CKPT_BASE and IMGGEN_CKPT_GPU,
# FLUX.2 klein 4B and Z-Image Turbo (videobench/fetch_models.sh img) from IMGGEN_DIT, the
# ComfyUI code from IMGGEN_COMFY. The ComfyUI process lives only inside this container, starts on the first request and exits after
# IDLE_S seconds (default 60) so the 7 GB of VRAM return to VR, Resolve or the LLM. Fails with 503 when there is not enough free VRAM.
if sel imggen && [ -n "${IMAGE_TOKEN:-}" ]; then
  run imggen --gpus all -p 8660:8660 -e IMAGE_TOKEN="$IMAGE_TOKEN" -e IDLE_S="${IMGGEN_IDLE_S:-60}" --cap-drop ALL --security-opt no-new-privileges \
    --pids-limit 512 --memory 16g --tmpfs /work:rw,size=3g --user 1000:1000 \
    -v "${IMGGEN_COMFY:-$HOME/imggen/ComfyUI}":/w/ComfyUI:ro -v "${IMGGEN_CKPT_BASE:-$MODELS_DIR/comfyui/checkpoints}":/models/base:ro \
    -v "${IMGGEN_CKPT_GPU:-$MODELS_DIR/../gpu-media/models/checkpoints}":/models/gpu:ro -v "${IMGGEN_DIT:-$MODELS_DIR/../videogen/models}":/models/dit:ro \
    --log-opt max-size=1m --log-opt max-file=2 imggen:latest
elif sel imggen; then
  echo "imggen: IMAGE_TOKEN is not set in host.env: not started" >&2
fi
# vidgen (8670): text to video with sound (MiniMax H3, aibridge/SKILL_video_generation.md). VIDEO_TOKEN is required (host.env); the weights
# (videobench/fetch_models.sh h3, ~45 GB) are read from VIDGEN_MODELS, the ComfyUI code from IMGGEN_COMFY. Idle, the wrapper holds no
# VRAM: ComfyUI starts on a request only when ~7 GB of VRAM and 16 GB of RAM are free (else 503), and exits after VIDGEN_IDLE_S.
# A job peaks at ~18 GB of RAM: the container is capped at 26 GB (+18 GB swap) so a runaway is killed here, not the desktop.
# A 5 s clip took 395 s at 130 W (VIDEO_BENCH_RESULTS.md, B4b); nothing raises the power cap for it yet.
if sel vidgen && [ -n "${VIDEO_TOKEN:-}" ]; then
  run vidgen --gpus all -p 8670:8670 -e VIDEO_TOKEN="$VIDEO_TOKEN" -e IDLE_S="${VIDGEN_IDLE_S:-120}" --cap-drop ALL --security-opt no-new-privileges \
    --pids-limit 512 --memory 26g --memory-swap 44g --tmpfs /work:rw,size=3g --user 1000:1000 \
    -v "${IMGGEN_COMFY:-$HOME/imggen/ComfyUI}":/w/ComfyUI:ro -v "${VIDGEN_MODELS:-$MODELS_DIR/../videogen/models}":/models:ro \
    --log-opt max-size=1m --log-opt max-file=2 vidgen:latest
elif sel vidgen && [ ${#SEL[@]} -gt 0 ]; then
  echo "vidgen: VIDEO_TOKEN is not set in host.env: not started" >&2
fi
# vidpost (8680): finishes a short video (Real-ESRGAN general-x4v3 2x and/or RIFE 4.26 to 48 fps), meant for a second card while
# another one generates. VIDPOST_TOKEN is required; the two small models (videobench/fetch_models.sh) are read from VIDPOST_MODELS.
# This container needs a card the comfy-bench torch supports (Turing or newer); on a GTX 10xx run vidpost/run_venv.sh instead.
if sel vidpost && [ -n "${VIDPOST_TOKEN:-}" ]; then
  run vidpost --gpus all -p 8680:8680 -e VIDPOST_TOKEN="$VIDPOST_TOKEN" -e IDLE_S="${VIDPOST_IDLE_S:-120}" "${HARDEN[@]}" --pids-limit 512 \
    --memory 16g --tmpfs /work:rw,size=6g --user 1000:1000 -v "${IMGGEN_COMFY:-$HOME/imggen/ComfyUI}":/w/ComfyUI:ro \
    -v "${VIDPOST_MODELS:-$MODELS_DIR/../videogen/models}":/models:ro vidpost:latest
elif sel vidpost && [ ${#SEL[@]} -gt 0 ]; then
  echo "vidpost: VIDPOST_TOKEN is not set in host.env: not started" >&2
fi
# mosher (8690): datamosh (FFglitch moves one clip's motion vectors onto another picture). CPU only, no --gpus: it
# can run on any machine with Docker. MOSH_TOKEN is required (host.env). Disk: the image shares transcoder's Debian + ffmpeg layer and
# adds ~56 MB; every job works in the tmpfs below (RAM) and deletes its files, so nothing grows on disk.
if sel mosher && [ -n "${MOSH_TOKEN:-}" ]; then
  run mosher "${HARDEN[@]}" --memory 3g --cpus "${MOSH_CPUS:-4}" --user 1000:1000 --tmpfs /work:rw,size=1g,uid=1000,gid=1000 \
    -p 8690:8690 -e MOSH_TOKEN="$MOSH_TOKEN" mosher:latest
elif sel mosher && [ ${#SEL[@]} -gt 0 ]; then
  echo "mosher: MOSH_TOKEN is not set in host.env: not started" >&2
fi
sel stt        && run stt        --gpus all -p 8620:8620 -v stt-models:/models stt:gpu
if sel llm && [ "${LLM:-1}" = 1 ]; then
  [ -f "$MODELS_DIR/gemma-4-E4B_q4_0-it.gguf" ] || { echo "llm: $MODELS_DIR/gemma-4-E4B_q4_0-it.gguf missing (NVMe not mounted?)" >&2; exit 1; }
  # -np 2 -kvu: Hermes's small calls (title, memory) take the second slot instead of evicting the conversation cache.
  # 80k shared: Hermes needs >= 64k; 96k + vision left too little VRAM for the upscaler and NVENC.
  run llm --gpus all -p 8630:8630 -v "$MODELS_DIR":/m:ro llm:cuda \
    -m /m/gemma-4-E4B_q4_0-it.gguf --mmproj /m/gemma-4-E4B-mmproj-Q8_0.gguf --alias gemma-4-e4b \
    -ngl 99 -fa on -c 81920 -np 2 -kvu --jinja
fi
sel tts && run tts --init -p 8640:5002 --cpus 4 --memory 1g -e VOICE_ES="$VOICE_ES" -e VOICE_RU="$VOICE_RU" tts-piper:multi
# Chatterbox: the clips in VOICES_DIR (optional, <name>.wav) are the reference voices; first start downloads ~3 GB of weights.
# A host that runs llm cannot also hold this too (~5.1 + 3.5 GB): set LLM=0 in that host's host.env to dedicate it to voice.
sel tts-hq && [ "${TTS_HQ:-0}" = 1 ] && run tts-hq --gpus all -p 8650:5002 -v tts-hq-models:/models ${VOICES_DIR:+-v "$VOICES_DIR":/voices:ro} tts-chatterbox

sleep 3
gpu-host/gpu_power.sh              # the measured optimum cap while llm runs (LLM_POWER_W in host.env)
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
