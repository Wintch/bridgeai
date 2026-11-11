#!/bin/bash
# Model weights for B3b-B8, all ungated, safetensors only (no pickles, no code), into models/<comfy folder>/ for the stock
# ComfyUI's native nodes (blueprints in ComfyUI/blueprints name these exact files). Resumable (curl -C -). Licences:
# Wan 2.2/2.1 repack Apache-2.0, SeedVR2 Apache-2.0, Real-ESRGAN BSD-3, BiRefNet MIT, frame_interpolation MIT/Apache-2.0.
# Not fetched: LTX-2.5/2.3 (gated on Hugging Face: needs an account token, against the plan's rule), SAM 3.1 + VOID/VACE (B9, deferred).
set -uo pipefail
cd "$(dirname "$0")"
HF=https://huggingface.co
get() {  # folder url
  mkdir -p models/$1; f=models/$1/$(basename "${2%%\?*}")
  [ -s "$f" ] && [ ! -e "$f.part" ] && { echo "have $f"; return; }
  touch "$f.part"; curl -fL --retry 5 -C - -o "$f" "$2" && rm -f "$f.part" && echo "got $f $(du -h "$f" | cut -f1)" || echo "FAILED $f"
}
get frame_interpolation $HF/Comfy-Org/frame_interpolation/resolve/main/frame_interpolation/film_net_fp16.safetensors
get frame_interpolation $HF/Comfy-Org/frame_interpolation/resolve/main/frame_interpolation/rife_v4.26.safetensors
get frame_interpolation $HF/Comfy-Org/frame_interpolation/resolve/main/frame_interpolation/rife_v4.25_lite.safetensors
get background_removal  $HF/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors
get upscale_models      $HF/Comfy-Org/Real-ESRGAN_repackaged/resolve/main/RealESRGAN_x4plus.safetensors
get diffusion_models    $HF/Comfy-Org/SeedVR2/resolve/main/diffusion_models/seedvr2_3b_int8_convrot.safetensors
get vae                 $HF/Comfy-Org/SeedVR2/resolve/main/vae/seedvr2_ema_vae_fp16.safetensors
W22=$HF/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files W21=$HF/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files
get text_encoders       $W21/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors
get vae                 $W22/vae/wan2.2_vae.safetensors
get vae                 $W21/vae/wan_2.1_vae.safetensors
get diffusion_models    $W22/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors
get loras               $W22/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors
get loras               $W22/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors
get diffusion_models    $W22/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors
get diffusion_models    $W22/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors
# The compact video-oriented Real-ESRGAN (SRVGG, 4.7 MB, BSD-3) exists only as an official .pth release: fetched to models/_pth
# and converted to safetensors with torch.load(weights_only=True), which refuses anything but plain tensors.
get _pth https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth
[ -s models/upscale_models/realesr-general-x4v3.safetensors ] || docker run --rm -v "$PWD/models:/models" comfy-bench python3 -c "
import torch, safetensors.torch as st
sd = torch.load('/models/_pth/realesr-general-x4v3.pth', map_location='cpu', weights_only=True)
sd = sd.get('params', sd)
st.save_file({k: v.contiguous() for k, v in sd.items()}, '/models/upscale_models/realesr-general-x4v3.safetensors'); print('converted', len(sd))"
# MiniMax H3 (ungated; MiniMax H3 Community License: not licensed in the EU, UK, South Korea
# or the USA, outputs included; commercial use allowed below US$20M yearly revenue with "MiniMax H3" shown). Opt-in (`fetch_models.sh h3`, about 45 GB): the files of ComfyUI's
# "Image to Video (MiniMax H3)" blueprint. The nvfp4 text encoder is dequantized per layer on cards older than Blackwell.
if [ "${1:-}" = h3 ]; then
  H3=$HF/Comfy-Org/MiniMax-H3/resolve/main
  get diffusion_models $H3/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors
  get text_encoders    $H3/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
  get vae              $H3/vae/minimax_h3_video_vae_fp16.safetensors
  get vae              $H3/vae/minimax_h3_audio_vae_fp32.safetensors
  get loras            $HF/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors
fi
# Newer text-to-image candidates for the 8 GB card (aibridge/GPU_RENTAL_AND_MODELS.md, section 2), both Apache-2.0 and ungated.
# Opt-in (`fetch_models.sh img`, about 24 GB): Z-Image Turbo int8 (6B, 8 steps) and FLUX.2 klein 4B (4 steps, also edits).
if [ "${1:-}" = img ]; then
  ZI=$HF/Comfy-Org/Z-Image-Turbo/resolve/main/split_files FK=$HF/Comfy-Org/Flux-2-Klein-4B/resolve/main/split_files
  get diffusion_models $ZI/diffusion_models/z_image_turbo_bf16.safetensors          # 12.3 GB; twice as fast as int8_convrot on Ampere
  get text_encoders    $ZI/text_encoders/qwen_3_4b_fp8_mixed.safetensors
  get vae              $ZI/vae/ae.safetensors
  get diffusion_models $FK/diffusion_models/flux-2-klein-4b.safetensors
  get text_encoders    $FK/text_encoders/qwen_3_4b_fp4_flux2.safetensors
  get vae              $FK/vae/flux2-vae.safetensors
fi
du -sh models
