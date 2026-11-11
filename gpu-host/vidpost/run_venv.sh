#!/bin/bash
# Start vidpost from a Python venv instead of Docker, for a Pascal card (GTX 10xx): comfy-bench's torch no longer supports it,
# torch 2.14 cu126 still does (measured on a 8 GB Pascal card, aibridge/GPU_RENTAL_AND_MODELS.md section 7.1).
#
# One-time setup in a folder on a disk with ~10 GB free (VIDPOST_HOME):
#   git clone https://github.com/comfyanonymous/ComfyUI.git && git -C ComfyUI checkout 0df1646
#   uv venv -p 3.12 venv && VIRTUAL_ENV=$PWD/venv uv pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu126
#   grep -vE "^(torch|torchvision|torchaudio)([<>= ]|$)" ComfyUI/requirements.txt > req.txt && VIRTUAL_ENV=$PWD/venv uv pip install -r req.txt
#   models/upscale_models/realesr-general-x4v3.safetensors and models/frame_interpolation/rife_v4.26.safetensors (videobench/fetch_models.sh)
# Then: VIDPOST_HOME=/path gpu-host/vidpost/run_venv.sh [start|stop|status]. VIDPOST_TOKEN comes from gpu-host/host.env.
# It listens on all interfaces like the containers (GPU_BIND_ADDR in host.env narrows it); ComfyUI itself stays on 127.0.0.1.
set -uo pipefail
cd "$(dirname "$0")/../.."
[ -f gpu-host/host.env ] && . gpu-host/host.env
H=${VIDPOST_HOME:?set VIDPOST_HOME to the folder with venv/, ComfyUI/ and models/}
PIDF=$H/vidpost.pid
case "${1:-start}" in
  start)
    [ -n "${VIDPOST_TOKEN:-}" ] || { echo "vidpost: VIDPOST_TOKEN is not set in gpu-host/host.env: not started" >&2; exit 1; }
    [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null && { echo "vidpost already running (pid $(cat "$PIDF"))"; exit 0; }
    mkdir -p "$H/work" && chmod 700 "$H/work"
    printf 'vidpost:\n  base_path: %s/models\n  upscale_models: upscale_models\n  frame_interpolation: frame_interpolation\n' "$H" > "$H/extra_paths.yaml"
    cp gpu-host/vidpost/server.py "$H/vidpost_server.py"
    VIDPOST_TOKEN="$VIDPOST_TOKEN" WORK="$H/work" COMFY_DIR="$H/ComfyUI" EXTRA_PATHS="$H/extra_paths.yaml" IDLE_S="${VIDPOST_IDLE_S:-120}" \
      PORT=8680 BIND="${GPU_BIND_ADDR:-0.0.0.0}" nohup "$H/venv/bin/python" "$H/vidpost_server.py" >> "$H/vidpost.log" 2>&1 &
    echo $! > "$PIDF"; sleep 2
    curl -s -m 3 http://127.0.0.1:8680/healthz && echo " (pid $(cat "$PIDF"))" ;;
  stop)
    [ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null; rm -f "$PIDF"; echo "vidpost stopped" ;;
  status)
    [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null && echo "running (pid $(cat "$PIDF"))" || echo "not running" ;;
esac
