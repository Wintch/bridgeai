#!/usr/bin/env python3
"""Submit one benchmark job to the bench ComfyUI server (comfy_server.sh) and wait for it. Stdlib only; runs inside the
container (docker exec vb-comfy python3 /vb/comfy_run.py JOB [key=value ...]). Missing widget inputs are filled from the
server's /object_info defaults, so the prompts below only name what matters. Prints one JSON line.

Jobs (inputs are file names in the server's input dir, outputs land in its output dir):
  esrgan   video=  model=RealESRGAN_x4plus.safetensors           Real-ESRGAN x4 per frame
  seedvr2  video=  scale=2                                       SeedVR2 3B int8, one-step, tiled VAE
  interp   video=  model=rife_v4.26.safetensors mult=2           RIFE / FILM frame interpolation
  matte    video=                                                BiRefNet foreground mask per frame, saved as a grey video
  wan5b    frames=49 w=832 h=480 steps=30                        Wan 2.2 TI2V-5B fp16, text to video
  wan14b   image=  frames=33 w=832 h=480                         Wan 2.2 I2V 14B fp8 + lightx2v 4-step LoRAs (2+2 steps)
  h3       secs=2 w=832 h=480 turbo=1 [image=] [tail=] [prompt=]   MiniMax H3 pruned int8, video + stereo audio (ComfyUI's
                                                                 "Image to Video (MiniMax H3)" blueprint: turbo = 8-step LoRA, else 20 steps)
  zimage   [prompt=] w=1024 h=1024 seed=                          Z-Image Turbo int8, 8 steps, CFG 1 (ComfyUI's "Text to Image (Z-Image-Turbo)")
  klein    [prompt=] w=1024 h=1024 seed= steps=4                  FLUX.2 klein 4B distilled, 4 steps, CFG 1 (text to image)
  sdxl     [prompt=] w=1024 h=1024 seed= ckpt=                    SDXL Lightning 4-step, the deployed imggen "fast" tier, for side-by-side
"""
import json, os, sys, time, urllib.request, uuid

S = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")   # another host or port for a second GPU (e.g. the 8 GB Pascal card test)
PROMPT = ("A red fox trots through fresh snow in a pine forest at sunrise, breath steaming, soft golden light, "
          "the camera slowly tracks beside it, cinematic, detailed fur")
IMG_PROMPT = ("Spider-Man crouching on a rooftop ledge at night, full body, two arms and two legs, red and blue suit with web pattern, "
              "city lights below, comic book style, dynamic pose")
NEG = "blurry, low quality, distorted, static, watermark, text"


def call(path, data=None):
    req = urllib.request.Request(S + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def video_in(p, name):
    p["lv"] = {"class_type": "LoadVideo", "inputs": {"file": name}}
    p["gc"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["lv", 0]}}
    return ["gc", 0], ["gc", 1], ["gc", 2]


def video_out(p, images, fps, prefix, audio=None):
    cv = {"images": images, "fps": fps}
    if audio:
        cv["audio"] = audio
    p["cv"] = {"class_type": "CreateVideo", "inputs": cv}
    p["sv"] = {"class_type": "SaveVideo", "inputs": {"video": ["cv", 0], "filename_prefix": prefix, "format": "mp4", "codec": "h264"}}


def build(job, a):
    p = {}
    tag = a.get("tag", job)
    if job == "esrgan":
        img, aud, fps = video_in(p, a["video"])
        p["ml"] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": a.get("model", "RealESRGAN_x4plus.safetensors")}}
        p["up"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["ml", 0], "image": img}}
        p["rs"] = {"class_type": "ImageScale", "inputs": {"image": ["up", 0], "upscale_method": "lanczos",
                                                          "width": int(a.get("w", 1920)), "height": int(a.get("h", 1080)), "crop": "disabled"}}
        video_out(p, ["rs", 0], fps, tag, aud)
    elif job == "seedvr2":
        img, aud, fps = video_in(p, a["video"])
        p["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": "seedvr2_ema_vae_fp16.safetensors"}}
        p["unet"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "seedvr2_3b_int8_convrot.safetensors", "weight_dtype": "default"}}
        p["rz"] = {"class_type": "ResizeImageMaskNode", "inputs": {"input": img, "resize_type": "scale by multiplier",
                                                                   "resize_type.multiplier": float(a.get("scale", 2)), "scale_method": "lanczos"}}
        p["pre"] = {"class_type": "SeedVR2Preprocess", "inputs": {"resized_images": ["rz", 0]}}
        p["enc"] = {"class_type": "VAEEncodeTiled", "inputs": {"pixels": ["pre", 0], "vae": ["vae", 0], "tile_size": 512,
                                                               "overlap": 128, "temporal_size": 64, "temporal_overlap": 8}}
        # the whole 72-frame 1080p latent does not fit 8 GB: split it in time (auto = largest chunk that fits free VRAM)
        p["chunk"] = {"class_type": "SeedVR2TemporalChunk", "inputs": {"latent": ["enc", 0], "temporal_overlap": int(a.get("overlap", 0)),
                                                                       "chunking_mode": a.get("chunking", "auto")}}
        if a.get("chunking") == "manual":
            p["chunk"]["inputs"]["chunking_mode.frames_per_chunk"] = int(a.get("fpc", 21))
        p["cond"] = {"class_type": "SeedVR2Conditioning", "inputs": {"model": ["unet", 0], "vae_conditioning": ["chunk", 0]}}
        p["ks"] = {"class_type": "KSampler", "inputs": {"model": ["unet", 0], "positive": ["cond", 0], "negative": ["cond", 1],
                                                        "latent_image": ["chunk", 0], "seed": 1, "steps": 1, "cfg": 1.0,
                                                        "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}}
        p["merge"] = {"class_type": "SeedVR2TemporalMerge", "inputs": {"latents": ["ks", 0], "temporal_overlap": ["chunk", 1]}}
        p["dec"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["merge", 0], "vae": ["vae", 0], "tile_size": 512,
                                                               "overlap": 128, "temporal_size": 64, "temporal_overlap": 8}}
        p["post"] = {"class_type": "SeedVR2PostProcessing", "inputs": {"images": ["dec", 0], "original_resized_images": ["rz", 0],
                                                                        "color_correction_method": "none"}}
        video_out(p, ["post", 0], fps, tag, aud)
    elif job == "interp":
        img, aud, fps = video_in(p, a["video"])
        mult = int(a.get("mult", 2))
        p["ml"] = {"class_type": "FrameInterpolationModelLoader", "inputs": {"model_name": a.get("model", "rife_v4.26.safetensors")}}
        p["fi"] = {"class_type": "FrameInterpolate", "inputs": {"interp_model": ["ml", 0], "images": img, "multiplier": mult}}
        video_out(p, ["fi", 0], float(a.get("fps_out", 48)), tag, aud)
    elif job == "matte":
        img, aud, fps = video_in(p, a["video"])
        p["ml"] = {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": "birefnet.safetensors"}}
        p["rb"] = {"class_type": "RemoveBackground", "inputs": {"image": img, "bg_removal_model": ["ml", 0]}}
        p["mi"] = {"class_type": "MaskToImage", "inputs": {"mask": ["rb", 0]}}
        video_out(p, ["mi", 0], fps, tag)
    elif job in ("wan5b", "wan14b"):
        fr, w, h = int(a.get("frames", 49)), int(a.get("w", 832)), int(a.get("h", 480))
        p["clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}}
        p["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": a.get("prompt", PROMPT)}}
        p["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": NEG}}
        if job == "wan5b":
            p["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}}
            p["unet"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}}
            p["ms"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": ["unet", 0], "shift": 8.0}}
            p["lat"] = {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["vae", 0], "width": w, "height": h, "length": fr, "batch_size": 1}}
            p["ks"] = {"class_type": "KSampler", "inputs": {"model": ["ms", 0], "positive": ["pos", 0], "negative": ["neg", 0],
                                                            "latent_image": ["lat", 0], "seed": int(a.get("seed", 42)), "steps": int(a.get("steps", 30)),
                                                            "cfg": 5.0, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}}
            last, fps = ["ks", 0], 24.0
        else:
            p["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}}
            p["img"] = {"class_type": "LoadImage", "inputs": {"image": a["image"]}}
            p["i2v"] = {"class_type": "WanImageToVideo", "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0],
                                                                    "start_image": ["img", 0], "width": w, "height": h, "length": fr, "batch_size": 1}}
            for k, noise in (("hi", "high"), ("lo", "low")):
                p[f"u{k}"] = {"class_type": "UNETLoader", "inputs": {"unet_name": f"wan2.2_i2v_{noise}_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}}
                p[f"l{k}"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": [f"u{k}", 0], "lora_name": f"wan2.2_i2v_lightx2v_4steps_lora_v1_{noise}_noise.safetensors", "strength_model": 1.0}}
                p[f"m{k}"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": [f"l{k}", 0], "shift": 5.0}}
            common = {"positive": ["i2v", 0], "negative": ["i2v", 1], "noise_seed": int(a.get("seed", 42)), "steps": 4, "cfg": 1.0,
                      "sampler_name": "euler", "scheduler": "simple"}
            p["k1"] = {"class_type": "KSamplerAdvanced", "inputs": dict(common, model=["mhi", 0], latent_image=["i2v", 2], add_noise="enable",
                                                                        start_at_step=0, end_at_step=2, return_with_leftover_noise="enable")}
            p["k2"] = {"class_type": "KSamplerAdvanced", "inputs": dict(common, model=["mlo", 0], latent_image=["k1", 0], add_noise="disable",
                                                                        start_at_step=2, end_at_step=4, return_with_leftover_noise="disable")}
            last, fps = ["k2", 0], 16.0
        p["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": last, "vae": ["vae", 0]}}
        video_out(p, ["dec", 0], fps, tag)
    elif job == "h3":
        w, h = int(a.get("w", 832)), int(a.get("h", 480))
        n = max(5, round(float(a.get("secs", 2)) * 24)); n += (5 - n % 17) % 17     # the model's 17k+5 frame grid, as the blueprint
        turbo = a.get("turbo", "1") == "1"
        p["clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax"}}
        p["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}}
        p["avae"] = {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}}
        p["unet"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}}
        model = ["unet", 0]
        if turbo:
            p["lora"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", "strength_model": 1.0}}
            model = ["lora", 0]
        i2v = {"clip": ["clip", 0], "vae": ["vae", 0], "prompt": a.get("prompt", PROMPT), "width": w, "height": h, "length": n}
        if a.get("image"):
            p["img"] = {"class_type": "LoadImage", "inputs": {"image": a["image"]}}
            i2v["first_frame"] = ["img", 0]
        p["i2v"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": i2v}
        cond = ["i2v", 0]
        if a.get("tail"):        # chained segments: anchor a clip (5, 22, 39... frames) and, unless tailaudio=0, its sound at frame 0
            p["tv"] = {"class_type": "LoadVideo", "inputs": {"file": a["tail"]}}
            p["tc"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["tv", 0]}}
            g = {"positive": cond, "latent": ["i2v", 1], "frame_idx": 0, "vae": ["vae", 0], "image": ["tc", 0]}
            if a.get("tailaudio", "1") == "1":
                g.update(audio_vae=["avae", 0], audio=["tc", 1])
            p["guide"] = {"class_type": "MiniMaxH3AddGuide", "inputs": g}
            cond = ["guide", 0]
        p["noise"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": int(a.get("seed", 42))}}
        p["smp"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}}
        p["sch"] = {"class_type": "BasicScheduler", "inputs": {"model": model, "scheduler": "simple", "steps": int(a.get("steps", 8 if turbo else 20)), "denoise": 1.0}}
        p["gd"] = {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": cond}}
        p["ks"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["noise", 0], "guider": ["gd", 0], "sampler": ["smp", 0],
                                                                     "sigmas": ["sch", 0], "latent_image": ["i2v", 1]}}
        p["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["vae", 0]}}
        p["adec"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["ks", 0], "vae": ["avae", 0]}}
        video_out(p, ["dec", 0], 24.0, tag, ["adec", 0])
    elif job in ("zimage", "klein", "sdxl"):
        w, h, seed, text = int(a.get("w", 1024)), int(a.get("h", 1024)), int(a.get("seed", 42)), a.get("prompt", IMG_PROMPT)
        if job == "sdxl":
            p["ck"] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": a.get("ckpt", "sdxl_lightning_4step.safetensors")}}
            p["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["ck", 1], "text": text}}
            p["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["ck", 1], "text": "blurry, low quality, watermark"}}
            p["lat"] = {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
            p["ks"] = {"class_type": "KSampler", "inputs": {"model": ["ck", 0], "positive": ["pos", 0], "negative": ["neg", 0], "latent_image": ["lat", 0],
                                                         "seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "sgm_uniform", "denoise": 1.0}}
            p["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["ck", 2]}}
        elif job == "zimage":
            p["clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b_fp8_mixed.safetensors", "type": "lumina2"}}
            p["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}}
            p["unet"] = {"class_type": "UNETLoader", "inputs": {"unet_name": a.get("unet", "z_image_turbo_int8_convrot.safetensors"), "weight_dtype": "default"}}
            p["ms"] = {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["unet", 0], "shift": 3.0}}
            p["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": text}}
            p["neg"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["pos", 0]}}
            p["lat"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
            p["ks"] = {"class_type": "KSampler", "inputs": {"model": ["ms", 0], "positive": ["pos", 0], "negative": ["neg", 0], "latent_image": ["lat", 0],
                                                         "seed": seed, "steps": 8, "cfg": 1.0, "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1.0}}
            p["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["vae", 0]}}
        else:
            p["clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b_fp4_flux2.safetensors", "type": "flux2"}}
            p["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}}
            p["unet"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-4b.safetensors", "weight_dtype": "default"}}
            p["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": text}}
            p["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": ""}}
            p["lat"] = {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
            steps = int(a.get("steps", 4))
            p["noise"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
            p["smp"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
            p["sch"] = {"class_type": "Flux2Scheduler", "inputs": {"steps": steps, "width": w, "height": h}}
            p["gd"] = {"class_type": "CFGGuider", "inputs": {"model": ["unet", 0], "positive": ["pos", 0], "negative": ["neg", 0], "cfg": 1.0}}
            p["ks"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["noise", 0], "guider": ["gd", 0], "sampler": ["smp", 0],
                                                                         "sigmas": ["sch", 0], "latent_image": ["lat", 0]}}
            p["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["vae", 0]}}
        p["save"] = {"class_type": "SaveImage", "inputs": {"images": ["dec", 0], "filename_prefix": tag}}
    else:
        sys.exit(f"unknown job {job}")
    return p


def fill_defaults(p, info):
    for nid, n in p.items():
        spec = info.get(n["class_type"])
        if not spec:
            sys.exit(f"node {n['class_type']} not on this server")
        for name, val in (spec["input"].get("required") or {}).items():
            if name in n["inputs"]:
                continue
            typ, opt = val[0], (val[1] if len(val) > 1 else {})
            if isinstance(typ, list) and typ:
                n["inputs"][name] = typ[0]
            elif typ == "COMBO" and opt.get("options"):
                n["inputs"][name] = opt["options"][0]
            elif "default" in opt:
                n["inputs"][name] = opt["default"]
    return p


def main():
    job = sys.argv[1]
    a = dict(x.split("=", 1) for x in sys.argv[2:])
    p = build(job, a)
    info = call("/object_info")
    p = fill_defaults(p, info)
    if a.get("dump"):
        print(json.dumps(p, indent=1)); return
    pid = call("/prompt", {"prompt": p, "client_id": str(uuid.uuid4())}).get("prompt_id")
    t0 = time.time()
    while True:
        h = call(f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            outs = [f for o in h[pid].get("outputs", {}).values() for k in ("images", "videos", "gifs") for f in o.get(k, [])]
            msgs = [m for m in st.get("messages", []) if m[0] in ("execution_error",)]
            print(json.dumps({"job": job, "tag": a.get("tag", job), "ok": st.get("status_str") == "success", "s": round(time.time() - t0, 1),
                              "outputs": [o.get("filename") for o in outs], "error": msgs[0][1].get("exception_message", "")[:400] if msgs else None}))
            sys.exit(0 if st.get("status_str") == "success" else 1)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
