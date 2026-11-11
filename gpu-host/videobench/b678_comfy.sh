#!/bin/bash
# B6-B8 and B3b/B4 through the bench ComfyUI server (comfy_server.sh + comfy_run.py), one job at a time under measure.py.
# The server stays up between runs, so run 1 includes the model load (cold) and runs 2-3 are warm.
# Usage: b678_comfy.sh [group ...]   groups: upscale upscale-fast interp matte wan5b wan14b (default: upscale interp matte)
set -uo pipefail
cd "$(dirname "$0")"
trap 'sudo -n nvidia-smi -pl 100 >/dev/null' EXIT
# ComfyUI caches node outputs: an identical prompt returns in about 1 s without recomputing. Each run therefore reads its own
# hard-linked copy of the input video (models stay loaded = a warm service, the work itself is redone) and Wan gets a seed derived from the tag.
J() {  # tag units unit cap job args...
  local tag=$1 units=$2 unit=$3 cap=$4; shift 4
  local run=${tag##*/r} args=() x
  for x in "$@"; do
    case $x in
      video=*) v=${x#video=}; c=${v%.mp4}.$(echo $tag | md5sum | cut -c1-8).mp4; ln -f comfy_in/$v comfy_in/$c; args+=("video=$c") ;;
      *) args+=("$x") ;;
    esac
  done
  case $1 in wan*) args+=("seed=$(( 0x$(echo $tag | md5sum | cut -c1-6) ))") ;; esac   # differs per run and per cap
  set -- "${args[@]}"
  sudo -n nvidia-smi -pl $cap >/dev/null
  python3 measure.py $tag --out-units $units --unit $unit -- docker exec vb-comfy python3 /vb/comfy_run.py "$@" tag=$(echo $tag | tr / _) \
    | tee -a results/comfy_jobs.log | cut -c1-200
  docker exec vb-comfy python3 -c "import urllib.request,json; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8188/history/', data=json.dumps({'clear': True}).encode(), headers={'Content-Type':'application/json'}))" 2>/dev/null
}
free_models() { docker exec vb-comfy python3 -c "import urllib.request,json; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8188/free', data=json.dumps({'unload_models': True, 'free_memory': True}).encode(), headers={'Content-Type':'application/json'}))"; sleep 3; }
for g in ${*:-upscale interp matte}; do
  case $g in
    upscale)   # 72 frames 960x540 -> 1080p
      # slow (ESRGAN x4plus about 4.5 s/frame, SeedVR2 about 7.7 s/frame in the smoke run): fewer repeats
      for r in 1 2; do J b6/esrgan-x4-540to1080-100w/r$r 72 frames 100 esrgan video=up540_3s.mp4; done
      J b6/esrgan-x4-540to1080-130w/r1 72 frames 130 esrgan video=up540_3s.mp4; free_models
      J b6/seedvr2-3b-int8-540to1080-100w/r1 72 frames 100 seedvr2 video=up540_3s.mp4 scale=2
      J b6/seedvr2-3b-int8-540to1080-130w/r1 72 frames 130 seedvr2 video=up540_3s.mp4 scale=2; free_models ;;
    upscale-fast)   # the compact SRVGG model (realesr-general-x4v3), the planned fast default
      for cap in 100 130; do for r in 1 2; do
        J b6/esrgan-general-x4v3-540to1080-${cap}w/r$r 72 frames $cap esrgan video=up540_3s.mp4 model=realesr-general-x4v3.safetensors; done; done; free_models ;;
    interp)    # 120 frames 720p 24 -> 48 fps
      for m in rife_v4.26 rife_v4.25_lite film_net_fp16; do for cap in 100 130; do for r in 1 2 3; do
        J b7/$m-720p-x2-${cap}w/r$r 120 frames $cap interp video=action5_720.mp4 model=$m.safetensors mult=2; done; done; free_models; done ;;
    matte)     # 120 frames 720p
      for cap in 100 130; do for r in 1 2 3; do J b8/birefnet-720p-${cap}w/r$r 120 frames $cap matte video=talk5_720.mp4; done; done; free_models ;;
    wan5b)     # ComfyUI fp16 vs the Diffusers B3 numbers, same prompt, 30 steps
      for r in 1 2; do J b3b/comfy-wan5b-49f-480p-100w/r$r 2.042 s_video 100 wan5b frames=49 w=832 h=480 steps=30; done; free_models ;;
    wan14b)    # I2V 14B fp8 + 4-step LoRA
      for cap in 100 130; do for r in 1 2; do J b4/wan14b-i2v-4step-33f-480p-${cap}w/r$r 2.062 s_video $cap wan14b image=still.png frames=33 w=832 h=480; done; done
      J b4/wan14b-i2v-4step-81f-480p-100w/r1 5.062 s_video 100 wan14b image=still.png frames=81 w=832 h=480; free_models ;;
  esac
done
