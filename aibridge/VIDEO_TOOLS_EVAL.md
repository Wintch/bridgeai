# Video tools evaluation: generation, AI editing and classic editing

Status: research. The benchmarks were run and the measured numbers and the decisions they changed are in `VIDEO_BENCH_RESULTS.md`, which wins over this document where they differ. Figures here that are not marked MEASURED are EXPECTED.

Terms used:
- Privacy classes A, B and C are defined in `DATA_LAW_AND_KEYS.md`.
- "The GPU workstation" is a GPU host with an 8 GB card.
- "The production VM" has CPU only.
- Wh is watt-hours per output.

## 1. Summary

Rule for the agent: walk the ladder from cheapest to most expensive. Use the cheapest tool that does the job. Escalate to generative AI only when the request needs it. Cloud is used only for what the 8 GB card cannot do: clips over 10 s, 1080p, audio, or hosted video editing.

### 1.1 Expected best choice per area

| Area | Expected best (local, class A) | Expected fallback | Cloud, only if needed |
|---|---|---|---|
| Video generation | Wan 2.2 I2V-14B fp8 with the 4-step LoRA in ComfyUI (MEASURED: 1.0 Wh and 33 s per output second at 130 W, needs 29 GB RAM). Wan 2.2 TI2V-5B in ComfyUI for text-to-video (MEASURED: 1.7 Wh and 75 s per output second). LTX-2.3 not tested (gated weights). | Wan 5B | Gemini Omni 1.2 Flash on the paid tier (class B, about $0.07/s at 720p). Then cheap class C options. |
| AI editing (upscale, interpolation, matting, object removal, restyle) | Real-ESRGAN general-x4v3 (MEASURED 0.6 s per frame), RIFE 4.26 (MEASURED 11 s for 5 s of 720p x2), BiRefNet (MEASURED 0.6 s per frame at 130 W). RobustVideoMatting not tested. | SeedVR2 3B (MEASURED 8.6-10 s per frame, clearly the best detail), FILM, SAM + ProPainter, Wan VACE | Runway Aleph 2 for hosted video-to-video edits (class C, $0.28/s). Not recommended for private material. |
| Classic editing | ffmpeg with NVENC for encode. ffmpeg CPU for filter-only edits. EffectCraft for titles. Resolve Studio for grading and its own AI tools. | melt (MLT) for multi-track timelines, SVT-AV1 for the smallest files | None needed |

### 1.2 Expected ranking by consumption, speed and privacy

Tie-break order: privacy first, then Wh per finished output, then time to a verified file.

| Rank | Tool | Expected consumption | Expected speed | Class |
|---|---|---|---|---|
| 1 | CPU-only helpers: auto-editor, PySceneDetect, ffmpeg grade and filters | No GPU use | Near I/O speed (UNVERIFIED) | A |
| 2 | ffmpeg NVENC encode | About 95 W for 3-5 s per 60 s of 1080p30 (about 0.1 Wh per minute, derived, UNVERIFIED as integrated) | 384-544 fps (MEASURED) | A |
| 3 | EffectCraft titles (CPU) | CPU only, Wh not measured | 50 fps at 720p (MEASURED) | A |
| 4 | Resolve Studio plain render | MEASURED 0.22 Wh and 2 GB VRAM for a 60 s edit | 64 s clip in 4-5 s (MEASURED), plus 8 s cold start. The scripting API cannot do transitions, volume or ducking. | A |
| 5 | Small GPU models: RIFE, Real-ESRGAN general-x4v3, BiRefNet | MEASURED: RIFE 0.16 Wh, general-x4v3 0.6 Wh per 3 s, BiRefNet 2.1 Wh per 5 s | MEASURED: below realtime. RIFE about 2x, general-x4v3 about 14x, BiRefNet about 14x the clip length. | A |
| 6 | SVT-AV1 2.3 on the workstation CPU | CPU Wh not measured (63 core-s per 20 s of 1080p) | MEASURED: 20 s of 1080p in 7.3 s at preset 8, half the size of NVENC at the same SSIM | A |
| 7 | Medium GPU models: SAM 2.1, ProPainter, Demucs, MuseTalk | To be measured | Minutes per short clip | A |
| 8 | Heavy diffusion: SeedVR2, GIMM-VFI, VACE, LatentSync | SeedVR2 MEASURED at 16-17 Wh per 3 s | SeedVR2 MEASURED at 8.6-10 s per frame | A |
| 9 | Local video generation: Wan 14B 4-step, Wan 5B | MEASURED 1.0-2.2 Wh per output second | MEASURED 33-115 s of compute per output second | A |
| 10 | Cloud generation | No local energy | Roughly 15 s to 5 min per clip (vendor claims, UNVERIFIED) | B only for Gemini paid, otherwise C |

Four facts shape the plan:
1. Nothing local is slower in Wh per output second than video generation. It is always a batch job at 100 W. The person gets a ready message.
2. No free video API exists. Cloud video is always paid and always a person's own key.
3. Veo 3.1 was retired on the Gemini API on 2026-10-22, and Sora 2 was shut down on 2026-09-24. Do not design around either.
4. The 8 GB card is the limit for exclusive jobs. System RAM (32 GB) is the second limit for Wan 14B and LTX.

Sources: aibridge/GPU_MEDIA_TOOLS.md, aibridge/SKILL_gpu_transcode.md, aibridge/SKILL_effectcraft.md, gpu-host/IMAGES.md, https://aistudio.google.com/docs/video, https://openai.com/api (model page for sora-2-pro, as cited in the research).

## 2. Per task: ordered chains

Chain format: local GPU, then local CPU, then cloud. "No" means we do not recommend it. The power mode is the first one to try. Full-eco is 100 W and smart-eco is 130 W. Max-reasonable is about 159 W. Turbo is 210-250 W.

Cloud prices are per output second. Gemini and Alibaba prices were read from official pages. Kling, MiniMax and Pika prices are secondhand and UNVERIFIED.

| Task | Local GPU | Local CPU | Cloud (price, class) | Power mode first |
|---|---|---|---|---|
| Text-to-video | 1. Wan 2.2 5B in ComfyUI (MEASURED). 2. A still from the image verb, then Wan 14B 4-step image-to-video. 3. LTX-2.3 distilled (with audio, up to 20 s; not tested, gated weights). | None. Too slow, and the CPU-only VM must never do it. | Gemini Omni 1.2 Flash $0.07/s at 720p (class B, paid tier only, non-personal prompts). Kling 2.6 on fal $0.07/s (C). Alibaba wan2.6-i2v-flash $0.025-0.05/s (C). | 130 W (MEASURED: faster at the same or lower Wh than 100 W; 159 W costs 16 % more Wh for 6 % less time). |
| Image-to-video (a person's photo) | Wan 14B 4-step first (MEASURED best and cheapest per second, 16 fps, then RIFE). Wan 5B next. LTX-2.3 if audio or length is needed. | None | Private photos stay local. Cloud only for non-personal images (same providers as above). | 130 W |
| Upscale (video) | 1. Real-ESRGAN general-x4v3 (MEASURED 0.6 s per frame, 0.2 Wh per second of video). 2. SeedVR2 3B int8 (MEASURED 8.6 s per frame at 130 W, best detail). 3. Resolve Super Scale (MEASURED 7.1 fps at 1080p, 200 W). Real-ESRGAN x4plus is dropped: same look as general-x4v3 at 8x the time. | None for video. The image verb has no CPU fallback by rule. | No cloud option evaluated. Not needed. | 100 W for ESRGAN, 130 W for SeedVR2 |
| Interpolation | RIFE 4.26 through ComfyUI's native node (MEASURED). FILM for hard clips (MEASURED 6x slower). GIMM-VFI not tested. | None. CPU is too slow. | No | 100 W |
| Matting (background removal) | BiRefNet per frame (MEASURED, uses the whole 8 GB). RobustVideoMatting for people (not tested, needs its code). SAM for prompted masks. | None | No | 130 W |
| Object removal and watermark removal | SAM 2.1 mask, then ProPainter fp16 at 480p. DiffuEraser does not fit 8 GB. | None | Runway Aleph 2 $0.28/s (C), not for private material. | 100 W |
| Subtitles | faster-whisper large-v3-turbo (already running, MEASURED 2.5 s per 161 s of audio). Add an SRT/VTT writer and ffmpeg burn-in. | ffmpeg for burn-in only | Not needed | 100 W |
| Auto-cut | auto-editor (silence and motion), PySceneDetect (scene cuts) | Same tools, they are CPU-only | Not needed | Not applicable |
| Dubbing and lip-sync | faster-whisper (STT), then LLM translation, then existing TTS, then optional MuseTalk 1.5 (MIT, 4 GB, MEASURED elsewhere: 8 s clip in about 5 min on a laptop card). LatentSync 1.6 needs 18 GB, so only 1.5 fits. | Audio-only dubbing can run on CPU with ffmpeg mux | No cloud lip-sync evaluated | 100 W |
| Restyle (video-to-video) | Wan 2.1 VACE 1.3B at 480p. It is slow and a creative tool, not a general editor. | None | Runway Aleph 2 $0.28/s (C) | 100 W |
| Colour and grade | Resolve Studio (LUT, nodes, Magic Mask, NR, RAW). ffmpeg lut3d/eq/colorbalance for simple grades. | ffmpeg lut3d (CPU, no VRAM) | None. Cloud grading is class C and not recommended. | 100 W (Resolve NR chain is not flat across caps: 3.49 fps at 100 W vs 6.36 fps at 200 W) |
| Render and export | ffmpeg NVENC (H.264/HEVC). Resolve render for Resolve timelines. | ffmpeg x264/x265. melt for multi-track timelines. | None | 100 W (NVENC is flat: 529/537/531 fps at 100/130/200 W) |
| Encode (Telegram, archive) | NVENC for speed. | SVT-AV1 on the workstation CPU for the smallest files (27-35 % smaller than x264 on a phone clip). Last-resort ffmpeg x264 on the production VM (26.6 s vs 6 s for 30 s of 1080p60 to 720p). | None | 100 W |

Notes for the agent:
- Telegram does not re-encode video and plays H.264, HEVC and AV1 MP4. AV1 has no hardware encoder on the 8 GB consumer card, so AV1 is CPU only.
- Wan 2.2 5B outputs 24 fps. Wan 14B quick workflows output 16 fps; RIFE x2 to 32 fps costs about 0.1 Wh and 10 s per 5 s (MEASURED for RIFE at 720p).
- Tools to skip: FramePack and HunyuanVideo 1.5 (RAM and VRAM limits, licence unclear), CogVideoX/Mochi/SVD (superseded), Kdenlive MCPs (weeks old), ffmpeg MCP servers (no confinement), Blender MCPs (execute_blender_code, a known CVE), Natron, Olive, GStreamer and VapourSynth for editing.

Sources: research on the repo docs, https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B, https://lilting.ch/en/articles/wan22-comfyui-rtx4060-i2v, https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler, https://github.com/nihui/rife-ncnn-vulkan, https://github.com/PeterL1n/RobustVideoMatting, https://github.com/sczhou/ProPainter, https://github.com/WyattBlue/auto-editor, https://github.com/TMElyralab/MuseTalk.

## 3. Benchmark plan for the GPU workstation

Rules for every run:
- Run one benchmark at a time.
- Stop Resolve, the local LLM, the transcoder and the upscaler containers first. A co-tenant caused a "GPU memory is full" modal in Resolve before.
- Warm up once, then do 3 timed runs. Record the median and the worst.
- Install everything under `/mnt/resolve_test/bridgeai/videogen/<id>`. Nothing lands on the root disk (24 GB free). The models disk has 318 GB free.
- Read each Hugging Face model card for the licence and the exact file names before downloading. Nothing may need a personal token (no gated weights).
- Power modes: 100 W, 130 W and about 159 W.
- Record: seconds, average and peak watts, Wh per output (integrate power samples every 0.5 s, because repo Wh figures are derived from 2 s samples), VRAM peak, RAM peak, and a sample output file.
- Net Wh means gross minus idle (17-20 W).
- Total downloads below: about 90 GB, under the 120 GB limit.

Shared reference workloads:
- REF-GEN: one fixed prompt, one CC0 still image, seed fixed, 832x480, 49 frames. Also 81 frames at 480p and 1280x704 where the model allows it.
- REF-CLIP: a 10 s 540p and a 15 s 720p CC0 or self-shot clip with speech, a cut and a moving subject. No personal footage.
- REF-60: the classic edit. Inputs: a 90 s 1080p30 H.264 source with speech, a 60 s music track, a logo PNG, a .cube LUT. Steps: cut 10-40 s and 55-85 s, 1 s crossfade (about 60 s final), lower-third text from 1 s to 5 s, music at -18 dB with sidechain ducking and -14 LUFS loudness, LUT plus +0.05 brightness and +10 % saturation, logo overlay, export 1080p30 H.264 with faststart plus an AV1 variant.
- Quality judge: libvmaf (CPU first) against an x264 slow crf 16 reference. The repo rule is VMAF 95 or more for transcodes. Check whether the transcoder build has libvmaf (UNVERIFIED).

| ID | Why | Exact downloads | Install path (under `/mnt/resolve_test/bridgeai/videogen`) | Workload and power modes | Record | Time cap |
|---|---|---|---|---|---|---|
| B1 | Reference edit across classic tools, to rank ffmpeg CPU, ffmpeg NVENC, melt, EffectCraft (titles only) and Resolve Studio | None for ffmpeg, EffectCraft and Resolve (installed). melt: system package (small, size UNVERIFIED). The CC0 inputs: self-shot or CC0 only. | `b1-ref60/` (inputs, recipes, outputs) | REF-60. GPU tools at 100/130/159 W. CPU tools once. Fresh Resolve per run. | Seconds split into cold start, edit-build, render. Agent steps and failed calls. CPU watts via RAPL or wall meter (not measured today). Wh gross and net. VMAF/SSIM. Hash on two runs. | 15 min per tool |
| B2 | Encode table: x264/x265, NVENC, SVT-AV1 presets 6-12, plus SVT-AV1 4.3.0 vs the transcoder build. Also vid.stab presence in the ffmpeg build. | None (MEASURED: the old transcoder image had ffmpeg 6.1.1 with SVT-AV1 1.7; the image now uses Debian trixie, ffmpeg 7.1 with SVT-AV1 2.3, 1.5x faster; vidstab is present). SVT-AV1 4.3.0 source or build is optional (size UNVERIFIED). | `b2-encode/` | A content mix: phone clip, screen capture, talking head. 1080p and 720p. NVENC at 100/130/159 W. | fps, seconds, Wh (GPU), CPU Wh, size, VMAF. | 10 min per codec |
| B3 | Local generation baseline. Re-measure Wan 2.2 TI2V-5B with per-stage timing (load, encode, steps, VAE). Compare Diffusers weights (already on disk, 36 GB) against the ComfyUI fp8 build. | Already present: Diffusers weights. Optional fp8 build: https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged (wan2.2_ti2v_5B fp16 about 10 GB, umt5_xxl_fp8_e4m3fn_scaled about 6.7 GB, wan2.2_vae about 1.4 GB; sizes UNVERIFIED). Total about 18 GB. | `b3-wan5b/` (symlink the existing Diffusers cache, do not copy) | REF-GEN 49 and 81 frames at 480p, and one 1280x704 run. 100/130/159 W. Known baseline: 166 s and 4.6 Wh at 100 W (unlocked). | Seconds, avg/peak W, Wh per output and per second of video, VRAM and RAM peak, sample. | 15 min per run |
| B4 | Best quality that fits: Wan 2.2 14B I2V with a 4-step Lightning-style LoRA, GGUF Q4, offload. | Official Wan 2.2 I2V-A14B GGUF Q4_K_M, high-noise and low-noise experts (about 9-10 GB each, UNVERIFIED), UMT5 GGUF Q3/Q4 (about 3-3.7 GB), Wan 2.1 VAE (254 MB), Lightning LoRAs (about 0.7 GB). Prefer the official weights plus LoRA over the Rapid-AIO merge (licence unclear). Hugging Face page for each: check on the model cards (exact URLs UNVERIFIED). Total about 35 GB. | `b4-wan14b/` | REF-GEN at 480p, 33 and 81 frames. 100/130/159 W. Third-party reference: about 55 s per second of video on a 4060 8 GB. | Same as B3, plus RAM peak (about 11 GB offloaded). Interpolation need from 16 fps. | 20 min per run |
| B5 | Longest clips and audio: LTX-2.3 distilled Q4_K_M, and an fp8/INT8 build. Test base resolution plus separate x2 spatial upscaler. LTX-2.5 only if its nodes support it. | LTX-2.3 distilled Q4_K_M (about 14.2 GB), Gemma 3 12B QAT Q3_K_XL text encoder (about 6.1 GB), text projection (about 2.3 GB), video VAE (about 1.45 GB), audio VAE (0.37 GB), spatial upscaler x2 (about 1.0 GB). About 25.5 GB total. Hugging Face pages: check LTX and Unsloth model cards (exact URLs UNVERIFIED). | `b5-ltx/` | REF-GEN at 512x768 for 5 s and 10 s. 100/130/159 W. Stop the LLM first (RAM). | Same as B3, plus audio check. | 25 min per run |
| B6 | Video upscale: Real-ESRGAN video model (baseline) vs SeedVR2 3B GGUF with BlockSwap and tiled VAE. | Real-ESRGAN `realesr-general-x4v3` (tens of MB, https://github.com/xinntao/Real-ESRGAN releases). SeedVR2 3B GGUF Q4_K_M (about 1.9 GB) and VAE, from https://huggingface.co/numz/SeedVR2_comfyUI (file names UNVERIFIED). Node: https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler (needs code review first). About 5 GB total. | `b6-upscale/` | REF-CLIP 10 s 540p to 1080p. 100/130 W. | Seconds per frame, Wh, VRAM peak, flicker (visual check), VMAF vs source downscaled. | 10 min per tool |
| B7 | Interpolation: rife-ncnn-vulkan (model 4.6) vs Practical-RIFE 4.25 fp16. Check artifacts at a cut. | Prebuilt Linux binary from https://github.com/nihui/rife-ncnn-vulkan/releases (tens of MB, models bundled). Practical-RIFE: https://github.com/hzwer/Practical-RIFE (weights tens of MB). | `b7-rife/` | REF-CLIP 15 s 720p, 30 to 60 fps. 100/130 W. Use PySceneDetect to skip cuts. | fps, Wh, VRAM, artifact notes. Disk use of frames (use JPEG or short clips). | 10 min per tool |
| B8 | Matting: RobustVideoMatting MobileNetV3 vs BiRefNet per frame vs SAM 2.1 small (prompted). | RVM weights (tens of MB) from https://github.com/PeterL1n/RobustVideoMatting. BiRefNet weights (MIT, about 1 GB, not RMBG-2.0) from https://github.com/ZhengPeng7/BiRefNet. SAM 2.1 small (Apache 2.0, about 0.2 GB) from https://github.com/facebookresearch/sam2. Do not use SAM 3 (gated). About 2 GB. | `b8-matting/` | REF-CLIP 10 s, one person, static camera. 100/130 W. | fps, VRAM, Wh, edge quality, flicker. | 10 min per tool |
| B9 | Object removal: ProPainter fp16 with a SAM 2.1 mask at 480p, 5 s. | ProPainter weights (three files: ProPainter.pth, raft-things.pth, recurrent_flow_completion.pth, about 0.5 GB, UNVERIFIED) from https://github.com/sczhou/ProPainter. SAM 2.1 weights are already pulled in B8. | `b9-inpaint/` | 5 s 480p clip with a mask. 100/130 W. | Seconds, peak VRAM (README: 8 GB at 720x480 for 80 frames), Wh, quality. | 10 min |

Download total, estimated: B3 about 18 GB (optional, the Diffusers set is already present), B4 about 35 GB, B5 about 25.5 GB, B6 about 5 GB, B7 and B8 about 2.5 GB, B9 about 0.5 GB. That is about 87 GB.

Smoke tests, no deep benchmark: auto-editor, PySceneDetect, deface, faster-whisper plus SRT burn-in end to end, Demucs one GPU timing, MuseTalk 1.5 only after the TTS and translation chain exists.

Cloud check, run after the local benchmarks: one 5 s 720p clip per provider with the person's own key. Providers: Gemini Omni 1.2 Flash, fal (Kling 2.6 and Wan), Alibaba wan2.6-i2v-flash. Record price and wall time. Latency figures in vendor blogs conflict (8 s to 5 min), so measure before routing on speed.

## 4. Integration design

Gateway verbs for the tools above follow the closed-option-list rule: every option is a fixed list, never free text, and a verb refuses what it cannot
do. What is built today is documented in `GPU_MEDIA_TOOLS.md` (`image`, `makevideo`, `enhance`, `transcode`, `upscale`, `mosh`); the rest of the
verb list (`gpu video upscale`, `interp`, `matte`) is design only.

## 5. Cloud options table

All of these need the person's own key. No cloud option qualifies as class A. Video has no free tier anywhere. The only free quota found is 30-50 s on old Alibaba models, valid 90 days. Prices are per output second. "Read" means taken from an official page. "Secondhand" means from an aggregator and UNVERIFIED.

| Provider and model | Price per second | Free quota | Class | Own key | Notes |
|---|---|---|---|---|---|
| Gemini Omni 1.2 Flash (read) | $0.023 at 360p, $0.07 at 720p, $0.104 at 1080p, $0.209 at 4K | None | B (paid tier with billing only, non-personal content). The unpaid terms allow human review, so never use an unbilled key. | Gemini API key | 3-15 s clips, native audio, edit and extend. Best value per quality. |
| Kling 3.0 official (secondhand) | About $0.084 at 720p silent, $0.112 with audio, $0.14 at 1080p audio | None | C | Access key and secret | Up to 15-30 s. Prefer Kling 2.6 on fal for price. |
| Kling 2.6 on fal (read) | $0.07 | None | C | fal key | Cheapest good tier. |
| Luma Ray 3.2 (partly secondhand) | About $0.03 at 540p, $0.06 at 720p, $0.24 at 1080p (credit conversion UNVERIFIED) | None | C (no training guarantee on pay-as-you-go) | Luma key | Good for drafts. |
| Alibaba Model Studio (read) | wan2.6/2.7 $0.10 at 720p, $0.15 at 1080p. wan2.6-i2v-flash $0.05 at 720p with audio, $0.025 silent. | 30-50 s on old models, 90 days | C (China-hosted, data terms unread) | DashScope-style key | Failed jobs are free. |
| Runway API (read) | gen4_turbo $0.05, gen4.5 $0.12, Aleph 2 $0.28 | None | C (consumer terms reportedly allow training, UNVERIFIED) | Runway key | Aleph is the strongest hosted video editor. |
| MiniMax Hailuo H3 (secondhand) | Lite $0.025-0.04, Highspeed $0.06, H3 $0.08 at 768p, $0.13 at 2K | None | C (terms unread) | MiniMax key | Quality unconfirmed at the low end. |
| fal.ai (read) | Wan 2.2 A14B $0.04-0.08. Kling 2.6 $0.07. Kling v3 $0.14. | None | C. Payloads kept 90 days unless `X-Fal-Store-IO: 0`. CDN media kept at least 7 days. | fal key | One key for many models. Use the privacy headers on every call. |
| Replicate (partly read) | Wavespeed Wan 2.1 480p $0.09, 720p $0.25. Other models UNVERIFIED. | None | C. Inputs and outputs deleted after 1 hour by default. | Replicate token | Prices look higher than fal and Alibaba direct. |
| Pika 2.x (secondhand, conflicting) | $0.04 at 720p, $0.06 at 1080p | None | C (terms unread) | Pika key | Skip unless the effects are wanted. |
| Cloudflare Workers AI video | No per-second price published | Not documented for proxied models | C (two companies on the data path) | Cloudflare token | Skip for video. Image models stay the free image route. |
| OpenAI Sora 2 | Retired 2026-09-24 | Not applicable | Not applicable | Not applicable | Remove from any plan. |
| Google Veo 3.1 (Gemini API) | Retired 2026-10-22 | Not applicable | Not applicable | Not applicable | Replaced by Omni. May still appear stale on Runway and Cloudflare lists (UNVERIFIED). |

Routing order proposal: local (class A), then Gemini Omni paid (class B), then cheap class C (Kling 2.6, Alibaba flash, Luma 540p) for non-private jobs only. Use fal as the single integration point if one key and easy price A/B are wanted.

Sources: https://aistudio.google.com/docs/pricing, https://aistudio.google.com/docs/video, https://docs.dev.runwayml.com/guides/pricing/, https://www.alibabacloud.com/help/en/model-studio/model-pricing, https://docs.agents.lumalabs.ai/guides/pricing/, https://fal.ai/pricing, https://fal.ai/docs/model-apis/faq, https://replicate.com/docs/topics/predictions/data-retention, https://developers.cloudflare.com/ai/models/, https://invideo.io/blog/ai-video-model-pricing (secondhand), https://ugccopilot.ai/research/ai-video-model-price-index/ (secondhand).
