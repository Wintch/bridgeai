#!/bin/bash
# Post-processing on the 8 GB Pascal card (Pascal, torch 2.14 cu126, stock ComfyUI 0df1646): the B6/B7 jobs measured on the 8 GB Ampere card.
cd "${PASCAL_DIR:-$(dirname "$0")}"
export COMFY_URL=http://127.0.0.1:8191
J() { tag=$1; n=$2; shift 2; venv/bin/python measure.py $tag $n frames -- venv/bin/python comfy_run.py "$@" tag=$(echo $tag | tr / _) | tee -a results.log; }
nvidia-smi --query-gpu=name,power.limit,power.default_limit --format=csv,noheader
for r in 1 2; do J p7/rife426-720p-x2/r$r 120 interp video=action5_720.mp4 model=rife_v4.26.safetensors mult=2; done
for r in 1 2; do J p6/general-x4v3-540to1080/r$r 72 esrgan video=up540_3s.mp4 model=realesr-general-x4v3.safetensors; done
J p7/rife426-h3-480p-x2/r1 124 interp video=h3_5s.mp4 model=rife_v4.26.safetensors mult=2
echo "== done $(date +%T)"
