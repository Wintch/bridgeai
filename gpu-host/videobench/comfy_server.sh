#!/bin/bash
# Bench ComfyUI server for B3b-B8: the stock ComfyUI checkout (~/imggen/ComfyUI, read-only) in the comfy-bench image, no network,
# models from ./models (fetch_models.sh), inputs from ./comfy_in, outputs to ./results/comfy. Jobs: comfy_run.py via docker exec.
#   comfy_server.sh start|stop|logs
set -uo pipefail
cd "$(dirname "$0")"
V=$PWD
case "${1:-start}" in
  start)
    mkdir -p comfy_in results/comfy
    cat > comfy_paths.yaml <<'EOF'
vb:
  base_path: /models
  diffusion_models: diffusion_models
  text_encoders: text_encoders
  vae: vae
  loras: loras
  upscale_models: upscale_models
  frame_interpolation: frame_interpolation
  background_removal: background_removal
vbck:
  base_path: /ckpt
  checkpoints: .
EOF
    docker rm -f vb-comfy >/dev/null 2>&1
    # VB_CKPT (optional): a folder of SDXL checkpoints (imggen's) mounted at /ckpt (not inside the read-only /models), for the sdxl side-by-side job.
    # VB_MEM caps the container (e.g. 26g for MiniMax H3, whose 16 GB text encoder and 21 GB model exceed the 31 GB of RAM
    # together): if ComfyUI does not unload in time the kernel kills it, not the desktop. Swap is allowed up to VB_MEM + 18g.
    docker run -d --name vb-comfy --gpus all --network none -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
      ${VB_MEM:+--memory $VB_MEM --memory-swap $(( ${VB_MEM%g} + 18 ))g} ${VB_CKPT:+-v $VB_CKPT:/ckpt:ro} \
      -v ~/imggen/ComfyUI:/w/ComfyUI:ro -v $V/models:/models:ro -v $V/comfy_in:/in:ro -v $V/results/comfy:/out \
      -v $V/comfy_paths.yaml:/w/paths.yaml:ro -v $V:/vb:ro --tmpfs /w/tmp:rw,size=2g --tmpfs /w/user:rw,size=256m \
      --entrypoint python3 comfy-bench /w/ComfyUI/main.py --listen 127.0.0.1 --port 8188 --extra-model-paths-config /w/paths.yaml \
        --input-directory /in --output-directory /out --temp-directory /w/tmp --user-directory /w/user --disable-auto-launch
    for _ in $(seq 90); do docker exec vb-comfy python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8188/system_stats', timeout=2)" 2>/dev/null && { echo "vb-comfy up"; exit 0; }; sleep 2; done
    echo "vb-comfy did not come up"; docker logs --tail 30 vb-comfy; exit 1 ;;
  stop) docker rm -f vb-comfy ;;
  logs) docker logs --tail ${2:-40} vb-comfy ;;
esac
