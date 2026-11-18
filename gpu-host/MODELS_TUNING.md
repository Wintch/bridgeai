# GPU models: one table per service (power, tuning, VRAM, timings, energy)

The single place that says, for every GPU service the gate can start, which model files it runs, at which power cap, with
which NVIDIA tuning, how much VRAM the gate reserves against what was measured, how long a job takes cold and warm, and
what it costs in energy. Every number carries a source key (section 9) and a date. A cell that says **not measured** is an
open measurement, not a zero. Nothing here is a promise: when a number is replaced, replace its source with it.

This file is checked against the code by `gpu-host/models_tuning_selftest.py` (run by `aibridge/ops/run_selftests.sh`).
It fails when a service of `gate/gate.py` `SERVICES` has no row or section, when a cap here differs from
`power_profiles.conf`, when a model file of `imggen` (`TIERS`), `vidgen` (`MODEL`) or `vidpost` is missing, or when the text the agent
reads (`aibridge/gateway.py` `MEDIA_MODELS`) is not quoted in section 6. So changing a model, a cap or a catalog line means
changing this file in the same commit.

Conventions:

- **Cap** is the GPU power limit in watts that the gate sets while the service runs and restores afterwards
  (`power_profiles.conf`, section for the card's name). A service with no value leaves the limit alone.
- **Cold** is the first job after the service slept (container start, ComfyUI start, weights read from disk or RAM). **Warm** is a job
  while the model is loaded. A time says which one and at which cap, or that the cap was not recorded.
- **Wh gross** is average watts x seconds. **Wh net** is the integrated energy minus a resting draw of 18 W x wall time (the method
  of `aibridge/VIDEO_BENCH_RESULTS.md`). Compare models with net, cost a job with gross. Never mix them in one comparison.
- **Status** is one of `measured`, `partly measured`, `to measure` or `evaluated, not installed`. A `to measure` item names the step
  of the plan in section 8.

## 1. Scope

Reference card: RTX 3060 Ti (Ampere GA104), 8 GB, 32 GB system RAM, 12 CPU threads, Debian 13. Other cards are listed only where
`power_profiles.conf` has a section for them (section 3.1). Services that are not containers (Resolve, EffectCraft) are in section 7.

## 2. Platform, shared by every service

Read from the host on 2026-11-17 (source S8) unless another source is named.

| Item | State | Source |
|---|---|---|
| Driver | NVIDIA 595.112.07 (security update from 595.71.05; every number above S13 was measured on 595.71.05 and the A/B in S13 shows no change), persistence mode on, 8192 MiB | S8, S13 |
| Card power limits | minimum 100 W, default 240 W, maximum 250 W. At rest the gate restores the limit it found before the first start, so a card nobody has touched rests at 240 W | S8, S7 |
| Driver patches | four local DKMS patches, all about display and VR (DisplayID/DSC, DRM lease, a DisplayPort link fix, a 6 bpc limit). None touches compute or power | S7 |
| gpu-unlock | on and permanent: `gpu_unlock.targets=all` on the kernel command line, module parameter reads `all`, package `gpu-unlock-dkms` 2.0.0 built per kernel. Effects and A/B in section 5 | S8, S3 |
| Kernel | 6.12.115 running. After a kernel update the DKMS module must exist for the new kernel before the next reboot (`dkms status`), or the card boots stock | S8, S3 |
| Clocks at 130 W | about 1320-1455 MHz under load (maximum 2115 MHz), throttle reason "software power cap", 57-59 C. Clocks were never pinned | S7 |
| CPU governor | `powersave` on all 12 threads with amd-pstate-epp, energy preference `balance_performance`, boost on. No A/B with `performance` (H3 streams 16-21 GB through RAM per job, so it may matter) | S8, S7 |
| `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` | set only in the `vidgen` image. `imggen` and `vidpost` do not set it. ComfyUI also adds `cudaMallocAsync` to this variable by default, so the allocator actually in effect is not confirmed. No A/B | S1, S7 |
| ComfyUI dynamic VRAM | on by default in every ComfyUI-based service (no flag turns it off). A ComfyUI or torch upgrade can change it silently | S7 |
| `--fast` (fp16 accumulation, autotune) | not passed by any service. Never A/B tested | S1, S7 |
| ComfyUI flags used by imggen, vidgen, vidpost | `--disable-metadata --disable-all-custom-nodes --disable-partner-nodes --cache-classic` | S1 |

Three energy sources exist and they must not be mixed: the bench recorder (GPU power sampled every 0.5 s, net and gross, per job),
the gate's own usage ledger (GPU power every 10 s split between services, gross, and it includes the idle wait before a service
stops: about 95% of an image job's ledger energy is that wait, so it is not a job energy), and old sweeps with the method written
beside them. The ledger stays on the GPU host.

## 3. Services at a glance

One row per service in `gate/gate.py` `SERVICES`. `Cap` is the production power cap (watts) from `power_profiles.conf` for the
RTX 3060 Ti section, or `none` when the service has no profile (it then runs at whatever limit is set: 240 W at rest). `VRAM declared`
and `Ready budget` are what the gate uses to admit a start.

| Service | Port | Cap (W) | Cap set by | VRAM declared (MB) | Ready budget (s) | VRAM peak measured | Status |
|---|---|---|---|---|---|---|---|
| `upscaler` | 8600 | 100 | gate profile | 380 | 30 | 755 MiB card use for a 640x360 x4 (327 MiB over rest) (S11); 1.4 GB general-x4v3 on video frames, 5.4 GB x4plus (S2) | measured |
| `transcoder` | 8610 | 100 | gate profile | 300 | 30 | 624 MiB card use (197 MiB over rest) (S11) | measured |
| `stt` | 8620 | 100 | gate profile | 1540 | 40 | 1767 MiB card use (1339 MiB over rest) (S11) | measured |
| `llm` | 8630 | 130 | gate profile | 5200 | 60 | 5.1 GB documented, not a sampled peak | measured |
| `tts` | 8640 | none | CPU service, no GPU | 0 | 20 | 0 (CPU) | to measure |
| `tts-hq` | 8650 | 130 | gate profile | 5300 | 90 | 4613-5033 MiB card use (up to 4606 MiB over rest) (S11) | measured |
| `imggen` | 8660 | 130 | gate profile | 6500 | 150 | 7.5-7.8 GiB card use (S7, S12) | measured |
| `vidgen` | 8670 | 130 | gate profile | 7000 | 360 | 7.58-7.81 GiB, 18 GB RAM (S7, S12) | measured |
| `vidpost` | 8680 | 100 | gate profile | 2500 | 150 | 1317 MiB card use for a 5 s 832x480 clip, both steps (S11); 1.3-2.2 GB (S2, S7) | measured |
| `mosher` | 8690 | none | CPU service, no GPU | 0 | 30 | 0 (CPU) | measured |

When several services run together the highest cap among them applies, and when the last one stops the gate restores the limit it
found. Anything started outside the gate (Resolve, Blender, manual tests) runs at the limit in force, normally 240 W.

### 3.1 Other cards in `power_profiles.conf`

| Card section | Service | Cap (W) | Source |
|---|---|---|---|
| `GTX 1070 Ti` | `llm` | 100 | S9: Pascal sweep 2026-10-09, Gemma turn 100 W 16.7 s / 0.46 Wh, 180 W 14.5 s / 0.66 Wh |

## 4. Per service

### `imggen`

Text to image through ComfyUI inside the container, one job at a time, ComfyUI started on demand and stopped after 60 s idle.
Sizes: 1024x1024, 832x1216, 1216x832. `base` is an alias of `photo`.

| Tier | Model | Files | Steps | Sampler and CFG | Production cap | Status |
|---|---|---|---|---|---|---|
| `fast` | SDXL-Lightning 4-step | `sdxl_lightning_4step.safetensors` | 4 | euler, sgm_uniform, CFG 1 | 130 W | measured |
| `better` (default) | FLUX.2 klein 4B | `flux-2-klein-4b.safetensors`, `qwen_3_4b_fp4_flux2.safetensors`, `flux2-vae.safetensors` | 4 | distilled, CFG 1, empty negative | 130 W | measured |
| `photo` | Z-Image Turbo bf16 | `z_image_turbo_bf16.safetensors`, `qwen_3_4b_fp8_mixed.safetensors`, `ae.safetensors` | 8 | res_multistep, CFG 1, ModelSamplingAuraFlow shift 3.0 | 130 W | measured |

| Field | Value |
|---|---|
| Model files | the files above; weights are read-only mounts, the tier list is closed (no model chosen by the caller) |
| Quantisation | `fast`: full SDXL checkpoint (one 6.9 GB file). `better`: klein unet unquantised bf16, text encoder `fp4` (nvfp4 is emulated on Ampere: it saves memory and costs speed). `photo`: unet bf16 (12.3 GB; the faster file on this card), text encoder fp8 weights (no hardware fp8 on Ampere) |
| Power | 130 W for every tier, set by the gate from `power_profiles.conf` (`imggen = 130`). Confirmed per tier by a sweep through the gate: 130 W has the lowest Wh per picture for `better` (100, 130, 160, 200 W), `photo` (same caps) and `fast` (100, 130 W), and it is faster than 100 W in all three (S12) |
| NVIDIA tuning | gpu-unlock on: measured for SDXL and Lightning only (SDXL 25 steps at 130 W 16.0 s stock vs 12.3 s unlocked; Lightning 4 steps 2.67 s vs 2.20 s; none at 100 W, section 5). No A/B for klein or Z-Image. No `expandable_segments`, no `--fast`, dynamic VRAM by default |
| Model-specific settings | `better --ref` adds a ReferenceLatent: one photo, at most 8 MiB and 40 Mpx. `photo` has no `--ref`. Prompt at most 800 characters. Alternative Z-Image files measured at 100 W, not in service: nvfp4 and int8_convrot (see timings) |
| VRAM | declared 6500 MB (the start threshold: free VRAM must be at least this). Measured peak 7.6 GiB (`fast`), 7.8 GiB (`better`), 7.5-7.8 GiB (`photo`) with dynamic loading. Container memory 16 GB with a 3 GB tmpfs against a Z-Image bf16 RAM peak of 10.8 GB: margin about 2 GB, not tested under load (S1, S7, S10) |
| Timings, `fast` | through the gate (S12): 2.65-2.67 s warm at 130 W, 3.3 s at 100 W. Earlier: warm 3.6 s median (n=13, production, older 100 W setting; bench 3.5-4.5 s warm and 13.0 s cold at 100 W, S10); 2.20 s warm at 130 W unlocked and 2.78 s at 100 W unlocked (S3); first picture after idle 10.4 s at 100 W (S3); ComfyUI cold about 10 s; container wake adds 18-38 s (S7). No `fast` job since 2026-11-08 |
| Timings, `better` | through the gate (S12): 9.3 s at 100 W, 6.95 s at 130 W, 6.4 s at 160 W, 6.2 s at 200 W, warm, n=5 each. Earlier: production at 130 W (n=37): warm 7.1 s, ComfyUI cold 16.9 s, with container wake 27.5 s (n=8) and 37.8 s (n=3) (S5). Bench at 100 W: warm 9.5-10 s, cold 16.5 s (S10). Test instance at 130 W: warm 6.5 s, cold 19 s (S6). `--ref`: warm 12.0 s (n=10), cold 21.8-30.8 s, cap not recorded (S7) |
| Timings, `photo` | bf16 through the gate (S12): 26.1 s at 100 W, 21.1 s at 130 W, 20.3 s at 160 W, 19.5 s at 200 W, warm, n=5 (4 at 200 W). Earlier: bf16 at 100 W warm 18.0 s (another setup); nvfp4 21.0 s; int8_convrot 36-38 s (S7, bench notes outside the repo; S10 has int8 at 38 s warm, 43 s cold). Test instance at 130 W with the **int8** file: 27.5 s warm, 37 s cold (S6): not the file in service. bf16 at 130 W: **not measured**. Two old production jobs 37 s and 40 s, both cold |
| Energy per job | through the gate, gross, 1024x1024 (S12): `fast` 0.071 Wh at 130 W, 0.078 at 100 W (about 14 pictures per Wh); `better` 0.244 / 0.226 / 0.248 / 0.285 Wh at 100 / 130 / 160 / 200 W (4.4 per Wh at 130 W); `photo` 0.643 / 0.607 / 0.663 / 0.740 Wh (1.65 per Wh at 130 W). Earlier, other methods: `fast` 0.08-0.09 Wh at 100 W (S10); `photo` bf16 0.487 Wh, nvfp4 0.566 Wh, int8 about 1.0-1.04 Wh at 100 W (S7, S10) |
| Sources | S1, S3, S4, S5, S6, S7, S10 |
| Status | measured through the gate, warm (S12). Open: klein `--ref`, cold starts, `expandable_segments` (step 6), gpu-unlock A/B (step 9) |

### `vidgen`

Text or picture to video with sound, MiniMax H3 through the stock ComfyUI nodes, one job at a time. The gate's ready budget is 360 s.

| Field | Value |
|---|---|
| Model files | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (unet, 21 GB), `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` (text encoder, 16 GB), `minimax_h3_video_vae_fp16.safetensors` (5.2 GB), `minimax_h3_audio_vae_fp32.safetensors` (0.6 GB), `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` (turbo LoRA, 2 GB) |
| Quantisation | unet int8_convrot, text encoder nvfp4 (emulated on Ampere), video VAE fp16, audio VAE fp32, LoRA bf16. The int8 text encoder and a 4-step LoRA were not tried (S2) |
| Power | 130 W from the gate (`vidgen = 130`): a 5 s clip took 562-579 s at 100 W and 395 s at 130 W; 250 W gave no further gain (S2, S7) |
| NVIDIA tuning | `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (image environment), dynamic VRAM by default, no `--fast`. gpu-unlock was on for every H3 run (S7), but H3 was never compared against a stock boot: effect **not measured** |
| Model-specific settings | 8 steps with the turbo LoRA (20 without), sampler res_multistep, scheduler simple, no CFG, 24 fps. Frames snap to 17k+5: 2 s = 56, 3 s = 73, 5 s = 124, 8 s = 192, 10 s = 243. Sizes: 832x480 for 2, 3 and 5 s, 704x384 for 8 s, 608x352 for 10 s and for chained segments (5 or 10 s each). A chained segment anchors the last 5 frames of the previous one; clips longer than 10 s are chained |
| VRAM | declared 7000 MB; measured 7.58-7.81 GiB with dynamic loading. RAM: the service waits for 16000 MB free, measured peak about 18 GB; container memory 26 GB (swap to 44 GB total) with a 3 GB tmpfs (S1, S7) |
| Timings, warm, 130 W (production) | 2 s about 213 s, 3 s about 256 s, 5 s about 418 s, 8 s about 434 s, 10 s about 446 s; chained 15 s 706 s, 20 s about 946 s, 30 s about 1301 s. A cleaner 5 s figure from the bench is 395 s (about 395-421 s in production). Rough model: about 45 s fixed plus about 72 s per second of output at 832x480; the smaller sizes at 8 and 10 s are why those times are not linear. Waking the container adds only 12-20 s (S5, S7, S2) |
| Timings, other caps | 2 s clip (56 frames, 832x480) through the gate (S12): 294.6 s at 100 W, 209.3 s at 130 W, 190.5 s at 170 W (one valid job; the other had a thermal slowdown). Earlier: 5 s clip at 100 W 562-579 s (S2) |
| Energy per job | 5.2 s clip (124 frames) at 130 W: gross 13.72 Wh, net of 18 W idle 11.75 Wh (2.3 Wh per second of video), recalculated from the raw record. The 7.62 Wh printed in `VIDEO_BENCH_RESULTS.md` subtracted the 55.7 W loaded-idle draw instead of 18 W and is not comparable with the other rows of that file. The 2.3 s clip prints 3.72 Wh at 130 W with the same method as the 7.62 Wh row; not recomputed. The gate ledger shows about 14.7 Wh per job gross, which includes queue and idle wait (S2, S7) |
| Energy, 2 s clip through the gate | 7.88 Wh at 100 W, **7.02 Wh at 130 W** (8.0 frames per Wh, 0.125 Wh per frame), 8.00 Wh at 170 W (one job): 130 W stays the cap (S12) |
| Sources | S1, S2, S5, S7, S12 |
| Status | measured through the gate on 2 s (S12). Open: gpu-unlock A/B (step 9); CPU governor (step 7); int8 text encoder (step 10) |

### `vidpost`

2x upscale (Real-ESRGAN) and/or 2x frame rate (RIFE) for a short video, in ComfyUI pieces so RAM stays flat. At most 30 s, 1920 px a side.

| Field | Value |
|---|---|
| Model files | `realesr-general-x4v3.safetensors` (upscale), `rife_v4.26.safetensors` (interpolation, multiplier 2) |
| Quantisation | upscaler: general-x4v3 (the small compact network); the dtype ComfyUI uses for it and for RIFE was not recorded |
| Power | 100 W from the gate (`vidpost = 100`). RIFE gains almost nothing from watts (most of its time is video decode and encode): 11.0 s at 100 W vs 10.5 s at 130 W. ESRGAN 43.5 s vs 41.0 s (S2) |
| NVIDIA tuning | gpu-unlock effect on the upscaler: -7 to -11% for Real-ESRGAN x4plus measured through spandrel (S3); RIFE and general-x4v3 not measured. No `expandable_segments` in this image |
| Model-specific settings | upscale runs before RIFE; pieces of at most 8e7 output pixel-frames; 41 bytes per output pixel-frame of RAM on top of about 3.4 GB; the sound is put back and slowed with `slow=1` |
| VRAM | declared 2500 MB; measured RIFE 1.3 GB (up to 2.0), general-x4v3 1.4 GB (up to 2.2); RAM need 8000 MB (S1, S2, S7) |
| Timings | RIFE x2 on 120 frames of 720p: 11.0 s at 100 W, 10.5 s at 130 W. Real-ESRGAN general-x4v3 on 72 frames 960x540 to 1080p: 43.5 s at 100 W, 41.0 s at 130 W (0.60 s per frame at 100 W). A whole `enhance` of a 5 s 832x480 clip (2x size and 48 fps, 239 frames out) through the gate at 100 W: 59.2 s warm (n=3), ready 1 s after the wake (S11). The earlier catalog text (20-40 s) was too low and was corrected (S2, S7, S11) |
| Energy per job | the whole 5 s `enhance` above: 1.281 Wh gross, 0.985 Wh net of 18 W, 77.7 W average: 187 frames out per Wh gross (S11). RIFE 0.16 Wh at 100 W, 0.18 Wh at 130 W. Real-ESRGAN general-x4v3 72 frames 0.60 Wh at 100 W, 0.65 Wh at 130 W; method: integrated minus 18 W (S2) |
| Sources | S1, S2, S3, S7 |
| Status | measured through the gate at 100 W (S11). Open: other caps (RIFE gains little from watts, S2) and a cold ComfyUI start |

### `upscaler`

Real-ESRGAN picture upscale over HTTP (`POST /upscale`, raw bytes in and out). The service image and its model file are not in this
repository (only the gate, the ports and the bench). Fixed 4x, JPEG output quality 92, at most 16 Mpx and 64 MB in, one request at a time
and it never answers 429 (it queues).

| Field | Value |
|---|---|
| Model files | `realesr-general-x4v3` in service (S7, read from the running image); `x4plus` was benched and dropped: 8x slower with the same look (S2) |
| Quantisation | fp16, tile 512 |
| Power | 100 W from the gate (`upscaler = 100`). The cap matters little: the model is mostly memory bound (S2) |
| NVIDIA tuning | gpu-unlock: -7% (FP32 with TF32) and -11% (FP16) on a 512 to 2048 px x4plus run at 200 W; the rest of the time is memory (S3) |
| Model-specific settings | scale 4 fixed; 16 Mpx and 64 MB limits above |
| VRAM | declared 380 MB: a 640x360 photo x4 peaks at 755 MiB of card use, 327 MiB over rest, plus 15 % (S11). Video frames through vidpost reach 1.4 GB (x4plus 5.4 GB) (S2, S7) |
| Timings | a 640x360 photo x4 (3.69 Mpx out) through the gate at 100 W: 0.1 s warm (n=3), ready 4 s after the wake (S11). Video frames: 0.60 s per frame at 100 W (S2) |
| Energy per job | the photo above: 0.0016 Wh gross, too short a job for a reliable figure (S11); video frames 0.60 Wh per 72 frames at 100 W (S2) |
| Sources | S1, S2, S3, S7 |
| Status | measured through the gate at 100 W (S11) |

### `transcoder`

NVENC video encoding on the GPU, AV1 on the CPU (SVT-AV1), from a closed list of options (never raw ffmpeg arguments).

| Field | Value |
|---|---|
| Model files | none (fixed function). NVENC p5, vbr, cq 28 (H.264 and HEVC); SVT-AV1 2.3 preset 8, crf 35, on the CPU |
| Quantisation | not applicable |
| Power | 100 W from the gate (`transcoder = 100`). The cap does not change NVENC speed: 529, 537 and 531 fps at 100, 130 and 200 W (S2) |
| NVIDIA tuning | gpu-unlock does not apply (fixed function, not re-run with it on) (S3) |
| Model-specific settings | AV1 is requested explicitly and runs on the CPU, never silently replaced by H.264 |
| VRAM | declared 300 MB; 60 s 1080p to 720p H.264 peaks at 624 MiB of card use, 197 MiB over rest (S11) |
| Timings | 20 s of 1080p: NVENC about 2.5 s, SVT-AV1 preset 8 7.3 s with 63 CPU core-seconds; 720p: NVENC 1.5 s, AV1 4.6 s (S2). The AV1 figure has three versions in the notes (6.5/9.4, 7.3/10.9 and 7.0/10.5 s); the table in `VIDEO_BENCH_RESULTS.md` is the one used here |
| Energy per job | through the gate at 100 W, 60 s of 1080p (1440 frames) to 720p H.264: 2.56 s, 0.034 Wh gross, about 42,600 frames per Wh (S11). NVENC about 0.03 Wh for 20 s of 1080p (S2); CPU energy is not measured (RAPL needs root) |
| Sources | S2, S3 |
| Status | measured through the gate at 100 W (S11); AV1 on the CPU not re-measured |

### `stt`

faster-whisper (CTranslate2) speech to text for voice notes, es/ru/en.

| Field | Value |
|---|---|
| Model files | large-v3-turbo (CTranslate2 format), downloaded into the `stt-models` volume |
| Quantisation | int8 (default). float16 and int8_float16 were compared (below) |
| Power | 100 W from the gate (`stt = 100`). A 3 min clip: 5.3 s at 100 W, 4.9 s at 130 W, 4.7 s at 240 W: 240 W is 11 % faster than 100 W for 28 % more energy (S11) |
| NVIDIA tuning | gpu-unlock changes nothing: 161 s of audio, float16 6.21 s stock vs 6.01 s unlocked, int8 2.49 s vs 2.47 s at 200 W (S3). The stop is SIGKILL after 10-11 s (no `--init` in the container) |
| Model-specific settings | languages es, ru, en; the container's transcription options are fixed by the image in service |
| VRAM | declared 1540 MB: peak 1767 MiB of card use, 1339 MiB over rest, plus 15 % (S11) |
| Timings | production median 0.7 s for a 12 s note (n=16, cap not recorded) (S5). Bench: 161 s of audio in 2.47 s (int8), 2.48 s (int8_float16), about 6 s (float16) at 200 W unlocked (S3). Cloud speech to text, for comparison only: median 0.5 s, p90 0.9 s (S5) |
| Energy per job | a 182 s Spanish clip (synthetic speech, int8): 0.131 Wh gross at 100 W, 0.145 at 130 W, 0.168 at 240 W, so 1391, 1256 and 1088 audio seconds per Wh (S11). Real speech with noise is harder; not measured. The gate ledger shows 0.68 Wh per job, almost all idle wait |
| Sources | S3, S5, S7 |
| Status | measured through the gate (S11). Open: 30 s and 300 s clips (short voice notes are the common case) |

### `llm`

llama.cpp serving a local chat and vision model, two slots. The gate has never started it in production, so its numbers predate the
gate and gpu-unlock.

| Field | Value |
|---|---|
| Model files | `gemma-4-E4B_q4_0-it.gguf` and the vision projector `gemma-4-E4B-mmproj-Q8_0.gguf` |
| Quantisation | Q4_0 weights, Q8_0 projector |
| Power | 130 W from the gate (`llm = 130`) on the RTX 3060 Ti; 100 W on the Pascal card (section 3.1) |
| NVIDIA tuning | gpu-unlock gives nothing for Q4: 3487 vs 3499 tok/s prompt and 91.0 vs 91.0 tok/s generation at 130 W; 3978/100.1 vs 3980/100.2 at 200 W. A BF16 prefill on a small model gains 26-30% (section 5) |
| Model-specific settings | `-ngl 99 -fa on -c 81920 -np 2 -kvu --jinja`: 80k context shared by two slots because the agent needs at least 64k; 96k plus vision left too little VRAM for the upscaler and NVENC |
| VRAM | declared 5200 MB; documented 5.1 GB (not a sampled peak). With every other service loaded, 7.1-7.5 GB of the 8 GB |
| Timings | a Hermes-sized turn, sweep 2026-10-10 (before gpu-unlock): 100 W 7.3 s, 130 W 5.7 s, 159 W 5.3 s, 210 W 5.1 s, 250 W 5.0 s (S4) |
| Energy per job | same turn: 0.20, 0.20, 0.23, 0.29 and 0.33 Wh at 100, 130, 159, 210 and 250 W (S4) |
| Sources | S3, S4 |
| Status | measured, before the gate and before gpu-unlock. Re-measure only if the local model comes back into service |

### `tts`

Piper text to speech on the CPU, voice chosen by the text's language. No GPU use.

| Field | Value |
|---|---|
| Model files | one Piper voice per language, set by `VOICE_ES` and `VOICE_RU` |
| Quantisation | not applicable (CPU, ONNX) |
| Power | not applicable (CPU service) |
| NVIDIA tuning | not applicable |
| Model-specific settings | 4 CPU cores, 1 GB memory |
| VRAM | 0 |
| Timings | 2.6 s for 88 characters, measured on the CPU of another machine. On the GPU host: **not measured** |
| Energy per job | **not measured** (CPU) |
| Sources | S7 |
| Status | to measure on the GPU host (time only; plan step 2 uses it to make test audio) |

### `tts-hq`

Chatterbox Multilingual speech synthesis, opt-in (`TTS_HQ=1`), Ampere or newer only.

| Field | Value |
|---|---|
| Model files | the Chatterbox Multilingual weights (about 3 GB, downloaded on first start into the `tts-hq-models` volume) |
| Quantisation | none: plain fp32, PyTorch 2.6 (CUDA 12.4), no TF32, no `torch.compile`, no alloc conf. On Ampere fp32 is the slowest path (about 12 TFLOPS fp32 against 31 TF32 and 61 fp16 with the unlock) |
| Power | 130 W from the gate (`tts-hq = 130`). 47.2 s per job at 100 W, 40.2 s at 130 W (18 % faster for 6 % more energy), 43.4 s at 240 W: slower than 130 W, with a thermal slowdown in one of three jobs (S11) |
| NVIDIA tuning | gpu-unlock would apply (fp32 matmuls could use TF32) but nothing was enabled or measured |
| Model-specific settings | reference voices are the `.wav` files in the voices folder; ready in about 35 s every time (model load and warm-up, not disk). Russian has no test data |
| VRAM | declared 5300 MB: peak 5033 MiB of card use, plus 15 % over the resting use (S11). It cannot share the card with `llm` |
| Timings | three public-domain paragraphs (es, en, ru), about 65 s of speech per job: 40.2 s at 130 W, warm; ready 35 s after the wake (model load) (S11). Earlier setup: 16.2 s for 329 characters (S7) |
| Energy per job | 1.29 Wh gross at 100 W, 1.42 at 130 W, 1.89 at 240 W: 49.6, 47.0 and about 35 seconds of speech per Wh (S11) |
| Sources | S1, S7 |
| Status | measured in fp32 through the gate (S11). Open: TF32 or bf16 (gpu-unlock would apply) |

### `mosher`

Datamosh effect service (FFglitch), CPU only: no GPU memory, no power.

| Field | Value |
|---|---|
| Model files | none (an effect, not a model) |
| Quantisation | not applicable |
| Power | not applicable |
| NVIDIA tuning | not applicable |
| Model-specific settings | 4 CPUs, 3 GB memory, 1 GB tmpfs for the work |
| VRAM | 0 |
| Timings | 2.7-3.0 s typical, 7.4 s for a 3.9 MB clip (n=3) (S7) |
| Energy per job | not applicable (CPU energy is not measured) |
| Sources | S7 |
| Status | measured |

## 5. gpu-unlock: what it changes, and the A/B behind the power choice

Recovered from the measurement notes of 2026-10-28/29 and 2026-11-07 (they were lost from the repository in a history squash).
Source S3 for everything in this section; the 2026-11-17 platform facts are S8.

**What it is.** A third-party DKMS module (`Zagitta/gpu-unlock` 2.0.0, with firmware extracted from a newer NVIDIA driver) that lifts the
half-rate limit GeForce cards put on tensor-core math with FP32 accumulate and on TF32, before the stock driver binds, through a
firmware bug. Nothing is flashed. It does nothing unless `gpu_unlock.targets=all` is on the kernel command line, and a boot without
it is stock. It does not apply to Pascal cards (no tensor cores). FP16 with FP16 accumulate, INT8 and plain FP32 already run at full
rate and do not change.

**Where it pays and where it does not** (same host, kernel and driver 595.71.05, two boots with the parameter and three without; 200 W unless noted):

| Workload | Cap | Stock | Unlocked | Change |
|---|---|---|---|---|
| Matmul 8192, FP16 / BF16 with FP32 accumulate (TFLOPS) | 200 W | 36.1 / 36.9 | 61.4 / 61.0 | +65 to +70% |
| TF32 matmul / cuDNN conv3x3 FP16 (TFLOPS) | 200 W | 18.4 / 36.8 | 31.0 / 60.9 | +68% / +65% |
| FP16 accumulate / INT8 (TOPS) / FP32 CUDA cores | 200 W | 57.4 / 33.9 / 12.3 | 57.9 / 34.0 / 12.3 | 0% |
| Matmul BF16 8192 | 100 W | 26.0 | 27.1 | +4% (power bound) |
| ComfyUI SDXL 1024, 25 steps (s per image) | 100 W | 18.8 | 18.2 | -3% |
| | 130 W | 16.0 | 11.8 | -26% |
| | 160 W | 14.8 | 10.7 | -28% |
| | 200 W | 14.0 | 9.9 | -29% |
| | 250 W | 13.6 | 9.5 | -30% |
| Wan 2.2 TI2V-5B, 832x480, 49 frames, 30 steps (s per step) | 100 W | 6.04 | 5.51 | -9% |
| | 200 W | 4.83 | 3.57 | -26% |
| | 250 W | 4.77 | 3.49 | -27% |
| llama.cpp Gemma 4 E4B Q4_0, prompt / generation (tok/s) | 130 W | 3487 / 91.0 | 3499 / 91.0 | 0% |
| | 250 W | 4134 / 101.5 | 4098 / 101.2 | 0% |
| llama.cpp Gemma 3 1B **BF16**, pp512 / pp4096 (tok/s) | 200 W | 13311 / 14193 | 16793 / 18382 | +26% / +30% (generation 0%) |
| faster-whisper large-v3-turbo, 161 s audio, float16 / int8 (s) | 200 W | 6.21 / 2.49 | 6.01 / 2.47 | about 0% |
| Real-ESRGAN x4plus 512 to 2048 px, FP32 with TF32 / FP16 (s) | 200 W | 1.452 / 0.697 | 1.344 / 0.618 | -7% / -11% |
| Blender 5.1 Cycles OptiX, 4K, 64 spp (s) | 200 W | 14.14 | 14.18 | 0% |
| Resolve 21.1.1, 1080p Noise Reduction + Beauty (render fps) | 100 W / 200 W | 3.49 / 6.36 | 3.64 / 6.75 | about 0% |
| Resolve Super Scale 2x, 1080p (render fps) | 100 W / 200 W | 4.54 / 7.10 | 4.74 / 7.41 | about 0% |
| Resolve 4K DNG, Super Scale 2x + Noise Reduction + Relight, 48 frames, fresh Resolve per render (s) | 200 W | 389 | 393 | 0% |
| Resolve Magic Mask, 240 frames 1080p (s) | 200 W | 18.5 | 21.4 | about 0% (node graph differed: read as "no gain") |
| NVENC | any | no change from the cap | not re-run | fixed function |

The 2026-11-07 repeat of the image workloads (7 images per cap, first discarded, power sampled every 0.5 s, seconds / Wh gross per image):

| Workload | Cap | Stock | Unlocked |
|---|---|---|---|
| SDXL base 25 steps | 100 W | 18.8 / 0.517 | 18.8 / 0.518 |
| | 130 W | 16.0 / 0.570 | 12.3 / 0.434 |
| | 160 W | 14.8 / 0.645 | 11.1 / 0.482 |
| | 200 W | 14.0 / 0.772 | 10.3 / 0.555 |
| Lightning 4 steps | 100 W | 2.96 / 0.079 | 2.78 / 0.074 |
| | 130 W | 2.67 / 0.087 | 2.20 / 0.069 |
| | 160 W | 2.51 / 0.095 | 2.06 / 0.072 |
| | 200 W | 2.42 / 0.107 | 1.97 / 0.081 |
| Lightning 8 steps | 100 W | 4.43 / 0.119 | 4.17 / 0.112 |
| | 130 W | 3.92 / 0.133 | 3.13 / 0.103 |
| | 200 W | 3.52 / 0.171 | 2.75 / 0.127 |
| Blender Cycles 4K, no denoise | 100 W | 15.9 / 0.434 | 16.0 / 0.436 |
| | 130 W | 14.6 / 0.512 | 14.7 / 0.515 |

**Why 130 W.** At 100 W the unlocked card is power bound (about 788 MHz under load for SDXL) and gains 0-9%. From 130 W up the gain is
23-30% less time for 21-24% less energy per image, so the best energy per image moved from 100 W (stock) to 130 W (unlocked) for every
image workload. That is the reason `imggen`, `vidgen` and `llm` are at 130 W while the rest are at 100 W. The 130 W line therefore
**assumes gpu-unlock is on**: with a stock boot the cheapest point for SDXL is 100 W. Blender and NVENC are unaffected and stay at 100 W.
Wan 5B video also gained (-9% at 100 W, -26% from 200 W up), but H3, klein and Z-Image were **never compared** stock against unlocked:
their 130 W is extrapolated.

**Stability and energy** (15 minutes of sustained BF16 8192 matmul at 200 W, one 1024-cubed product per minute checked against an FP64 reference):

| | Stock | Unlocked |
|---|---|---|
| TFLOPS, first to last minute | 36.2 to 35.6 | 59.2 to 58.5 |
| Maximum relative error vs FP64 | 0.00355 | 0.00355 |
| Average power | 199.3 W | 199.5 W |
| Temperature, average / maximum | 70.3 / 73 C | 70.5 / 73 C |
| Fan, maximum | 83% | 82% |
| Average SM clock | 1865 MHz | 1585 MHz |
| GFLOPS per watt | 179 | 293 (+64%) |
| New Xid / AER / DPC kernel messages | 0 | 0 |

Diffusion outputs were bit-identical in the Wan A/B. Nothing measured got slower. The card does more work per joule, so at the cap it
runs lower clocks. The reported clock is live, not the frozen clock of an upstream report about another card.

**Reading.** It pays where software does FP16/BF16 math with FP32 accumulate or TF32 on the tensor cores (PyTorch's default): diffusion
image and video, BF16/FP16 prefill, FP16/TF32 CNNs such as upscalers (7-11% here). It does not pay for INT8 and FP16-accumulate paths:
TensorRT-built apps (Resolve), quantised llama.cpp models, faster-whisper, Cycles, NVENC.

**Costs and how to undo.** A tainted kernel (unsigned out-of-tree module), third-party code exploiting NVIDIA's signed boot firmware at
every boot, about 88 MB more per initramfs (`/boot` holds two kernels, so purge the oldest before a kernel update), and the module must
be built for every new kernel. It re-unlocks on resume from suspend to RAM, not hibernation. Undo: remove `gpu_unlock.targets=all` from
`GRUB_CMDLINE_LINUX_DEFAULT`, `update-grub`, reboot; `apt remove gpu-unlock-dkms gpu-unlock-firmware` removes the module and the
initramfs hooks. For one stock boot, delete the parameter in the GRUB edit screen. Two upstream reports to know (state of 2026-10-29): five
cards behind one PCIe switch lost the whole switch (DPC, Xid) hours after unlocking and recovered when stock; and in a passthrough guest a
reboot without the parameter kept the card unlocked until a power cycle. On this bare-metal host a warm reboot without the
parameter gave stock numbers every time.

**Trap when measuring Resolve.** Compare fresh Resolve instances only: the same render took 626 s in a Resolve open for hours and 389 s
in a fresh one (a stale stock run against a fresh unlocked run looked like -40 to -52%, which was the session, not the unlock). Start and
quit Resolve around every timed render. A second large 4K render in a row failed with GPU memory full, stock and unlocked alike.

**Not measured.** gpu-unlock on H3, klein, Z-Image, general-x4v3, RIFE, Chatterbox (plan step 9: two reboots, one stock boot).

## 6. What the agent is told, next to what was measured

`gateway modelos` prints these lines (`MEDIA_MODELS` in `aibridge/gateway.py`). They are quoted verbatim: the selftest fails when the
catalog changes and this table does not. "Measured here" is this file's number for comparison; a mismatch is an item to fix in the
catalog or to re-measure, not something to hide.

| Verb | Mode (catalog) | Bench text (catalog) | Measured here |
|---|---|---|---|
| image | `--quality better (default)` | `1024x1024: 6.5 s (19 s cold)` | test instance 130 W 6.5 s / 19 s (S6); production 130 W warm 7.1 s, 27.5-37.8 s when the container had to wake (S5) |
| image | `--quality photo` | `1024x1024: about 21 s warm` | bf16 through the gate 21.1 s warm at 130 W (S12) |
| image | `--quality fast` | `1024x1024: about 2.7 s warm` | 2.65-2.67 s warm at 130 W through the gate (S12) |
| makevideo | `--secs 2\|3\|5\|8\|10\|15\|20\|30 [--from PHOTO\|VIDEO]` | `measured per job (GPU free, model may need loading): 2 s ~3.7 min, 3 s ~4.3 min, 5 s ~7 min, 10 s ~7.5-15 min, 30 s ~22 min; waiting behind other jobs or a running Resolve comes on top` | section 4 `vidgen` timings: 2 s about 213 s, 3 s about 256 s, 5 s about 418 s, 10 s about 446 s (S5) |
| enhance | `--fps 48 \| --scale 2 \| --slow` | `a 5 s 832x480 clip, both (2x size and 48 fps): about 60 s warm, plus about 1 s to wake the service` | 59.2 s warm at 100 W, ready 1 s after the wake (S11) |
| upscale | `IN OUT` | `seconds per picture` | 1.1 s for one old job; the current image never ran (S7) |
| transcode | `IN OUT` | `depends on length` | NVENC 2.5 s for 20 s of 1080p; AV1 7.3 s (S2) |
| mosh | `MOTION OUT.mp4` | `depends on length` | 2.7-3.0 s typical (S7) |

## 7. Evaluated, not installed, and tools outside the gate

None of these is started automatically. The gate has no tier, service or entry for the first two, and nothing launches them.

| Item | What was measured | Status |
|---|---|---|
| MiniMax H3-Image w4a8 (12.5 GB) with the Qwen3-VL nvfp4_awq encoder (15.7 GB, shared with video) | 130 W set by hand with the gate in busy mode, `expandable_segments`. 56-64 s for a 1 MP picture, 72 s at 1536, 94 s at 2048, 52 s at 1216x832; an edit with one photo 128 s; with two photos 184 s and a wrong result. Peak 7.5 GB VRAM and about 15 GB RAM: the model does not fit in 8 GB and is streamed from RAM every step. Energy not measured (upper bound 130 W x 60 s = 2.2 Wh). The limits of today's `imggen` (150 s job timeout, 16 GB container) would not hold it. Offering it to other people needs written authorisation from the vendor (catalog, section 6) (S6) | evaluated, not installed. To measure for the decision only: 100 and 160 W, 3 runs of 1 MP (plan step 12) |
| ComfyUI-H3-FaceRefine (re-draws small faces in an H3 video) | canvas 512, denoise 0.4, 8 steps, er_sde, yolov8m face detector. Adds 222-234 s to a 3 s clip (the clip itself took 277 s). A face of 8 px fails, 49 px works, the node uses 30 px: the 20 px figure in the catalog is not measured. About 8.3 Wh gross, estimated, not measured. VRAM and RAM peak not recorded (S6) | evaluated, not installed. To measure: pixel threshold 15/20/30 px and peak memory (plan step 11) |
| Wan 2.2 14B I2V fp8 + 4-step LoRA (ComfyUI) | bench only, 29 GB RAM peak so never next to the LLM. 33 frames at 130 W 69 s / 2.06 Wh; at 100 W 113 s / 2.50 Wh; 81 frames at 100 W 322 s / 7.20 Wh. About 1.0-1.4 Wh per second of video (S2) | evaluated, installed on the host as a bench model, no service |
| Wan 2.2 TI2V-5B (ComfyUI fp16) | 49 frames at 100 W 153 s / 3.41 Wh (S2) | bench only |
| SeedVR2 3B int8 | 72 frames to 1080p: 736 s / 16.4 Wh at 100 W, 616 s / 17.2 Wh at 130 W, 6.9-7.0 GB (S2) | bench only, slow premium option |
| BiRefNet (matting) | run at 130 W in the bench; figures not kept in this repo | bench only, **not measured** here |
| DaVinci Resolve | not a gate service on `main`: no lease, no cap, runs at 240 W. Noise Reduction + Beauty 1080p 3.49 fps at 100 W and 6.36 fps at 200 W, flat above 200 W (memory bound). While it runs it takes about 7 GB of VRAM, so it cannot sit next to `imggen` or `vidgen`. gpu-unlock changes nothing (section 5) (S3) | to measure: best cap above 200 W and Wh per render, fresh Resolve per render (plan step 13). A branch that makes Resolve a gate-leased task is not merged |
| EffectCraft | CPU effects engine. Rendering a 5 s 720p title took about 3 s. "CPU only" is assumed, not measured (no VRAM sampling was done); CPU energy cannot be measured without RAPL (S7) | to measure VRAM use once (plan step 1) |

## 8. Measurement plan and the rules for a clean measurement

### 8.1 Rules (what keeps the numbers uncontaminated)

1. Everything runs through the gate, one service at a time, or with the operator's busy switch on and announced. Never with the gate
   competing.
2. Before a run: the gate shows no lease and no job in flight (a stuck in-flight counter from a chained job can last 30 minutes and
   makes the gate refuse other services), no VR session, no Resolve, no game, no other compute process on the card (only small desktop
   processes), and the card has rested to the same temperature. Record `nvidia-smi` process memory before the run.
3. Inputs are synthetic or public: fixed prompts, fixed seeds, generated test audio from public text, public-domain paragraphs, a
   generated test clip. Never a person's photo, voice, video or chat.
4. Record with every run: boot mode (gpu-unlock on or stock), driver, kernel, CPU governor, cap read back from `nvidia-smi` (not the
   requested one), cold or warm, seed, size, model file names, and Wh both gross and net of 18 W.
5. One discarded warm-up, then at least 3 timed runs (5 for jobs under a minute); report the median and the worst, cold and warm
   separately. VRAM is sampled every 0.5 s for the whole run (peak), with 20 s idle before and after.
6. Never change the cap outside the plan's cap sweep steps, always restore the previous limit, never leave a service up.
7. Resolve: one render per fresh instance.
8. Results go to a file on the host first. A number enters this document only with its source key, date and method.

The gate's bench mode (`POST /bench/start|watts|end`) and the recorder `bench_gate.py` implement rules 1, 2, 4 and 5 for stt, tts-hq,
Resolve, EffectCraft and, with `--recheck`, the existing profiles (45 minutes, 95 with `--recheck`). They live on the branch
`feat/gpu-gate-resolve` and are not merged or deployed; until then the same steps are done by hand under rule 1.

### 8.2 Plan (cheapest and most useful first; about 2.5 to 3 hours of card time in total)

| Step | What to measure | GPU minutes | Closes |
|---|---|---|---|
| 0 | No GPU: recompute H3 Wh at 18 W (done in section 4), clean medians per verb and length from the logs (queue wait and start separated), summarise the gate ledger, confirm the allocator ComfyUI actually uses | 0 | the Wh and timing contradictions |
| 1 | Peak VRAM per service (stt, tts-hq, upscaler, transcoder, vidpost, imggen, EffectCraft), sampled during steps 2-5 | 0 extra | the declared 300, 1200 and 3600 MB |
| 2 | `stt` at 100, 130 and 240 W, Wh per minute of audio, int8 | about 5 | whether `stt` needs a profile |
| 3 | `tts-hq` at 100, 130 and 240 W, with and without TF32 or bf16 | about 12 | a profile or a documented "no gain" |
| 4 | klein, klein `--ref` and Z-Image bf16 at 100, 130, 160 and 200 W, warm and cold, through the gate | about 25 | the 130 W of `imggen` and the catalog times |
| 5 | First run through the gate of `upscaler` (photo), `vidpost` (5 s H3 clip), `transcoder`, `mosher`, including the wake | about 10 | the 100 W of those four and the `enhance` time |
| 6 | `expandable_segments` on and off in `imggen` and `vidpost` | about 8 | whether to copy it to the other images |
| 7 | CPU governor `performance` and energy preference `performance` on H3 2 s, Z-Image bf16 and AV1 | about 20 | the governor question |
| 8 | H3 at 100, 130, 159 and 250 W, same seed, 2 s clip | about 16 | the `vidgen` row |
| 9 | gpu-unlock stock against unlocked for H3, klein, Z-Image bf16, upscaler and RIFE (two reboots; check DKMS for the running kernel first) | about 35 | the biggest gap in section 5 |
| 10 | H3 text encoder int8 against nvfp4; a 4-step LoRA if one exists (about 16 GB download) | about 20 | quantisation choice |
| 11 | FaceRefine pixel threshold and peak memory | about 15 | the 20 px claim |
| 12 | H3-Image at 100 and 160 W (manual, busy switch) | about 10 | the install decision |
| 13 | Resolve best cap above 200 W and Wh per render | about 20 | Resolve's cap |
| 14 | Queue behaviour under load (code review plus one two-part chained job; not a power measurement) | about 15 | the video queue |

Done (S11): steps 2, 3 and 5 (stt, tts-hq, upscaler, transcoder, vidpost; `mosher` is a CPU service) and step 1 for those five.
Done (S12): steps 4 (warm; `--ref` and cold starts still open), 8 (2 s clip at 100, 130, 170 W) and step 1 for imggen.
Still open: step 1 for EffectCraft, and steps 6, 7 and 9 to 14.

Suggested order: 0, then one session of about an hour with steps 1 to 6, a second with 7 and 8, a third with 9 (it needs reboots).

## 9. Sources

| Key | Source | Date |
|---|---|---|
| S1 | code in this directory: `gate/gate.py` (`SERVICES`), `power_profiles.conf`, `imggen/server.py`, `vidgen/server.py`, `vidpost/server.py`, the Dockerfiles, `run_services.sh` | main, 2026-11-17 |
| S2 | `aibridge/VIDEO_BENCH_RESULTS.md` and `gpu-host/videobench/` (bench recorder: GPU power every 0.5 s) | 2026-11-07 and 2026-11-08 |
| S3 | gpu-unlock A/B (section 5), measurement notes kept outside the repo | 2026-10-28, 2026-10-29, 2026-11-07 |
| S4 | power sweeps: Gemma turn on both cards (2026-10-09, 2026-10-10) and the SDXL and Lightning caps (2026-11-07), measurement notes kept outside the repo | 2026-10-09 to 2026-11-07 |
| S5 | the production job logs and the gate's usage ledger (39 runs: `vidgen`, `imggen`, `stt`) | 2026-11-08 to 2026-11-17 |
| S6 | manual image and FaceRefine tests on a separate ComfyUI, gate in busy mode, 130 W | 2026-11-17 |
| S7 | read-only measurement audit that recounted S2 to S6 and checked the running images and code | 2026-11-17 |
| S8 | read-only query of the GPU host (`nvidia-smi`, kernel command line, cpufreq) | 2026-11-17 |
| S9 | Pascal-card benchmark of the local model (comments of `gpu_power.sh`) | 2026-10-09 |
| S10 | `aibridge/GPU_RENTAL_AND_MODELS.md`, image bench at 100 W (ComfyUI 0df1646, 1024x1024) | 2026-11-07 |
| S11 | `bench_gate.py` session through the gate's bench mode (gpu-unlock on, driver 595.71.05, CPU governor powersave), with a 0.5 s `nvidia-smi` sidecar: 2515 samples, peak 68 C, no swap-out; invalid jobs left out (one thermal slowdown at 240 W, two warm-ups) | 2026-11-17 |
| S12 | `bench_gate.py` sessions through the gate's bench mode for imggen (three tiers) and vidgen, same setup as S11; the cache canary passed for every task (a second new (prompt, seed) as slow as the first, identical repeats 4-200x faster: the node cache is on, as in production) | 2026-11-17 to 2026-11-18 |
| S13 | driver 595.71.05 -> 595.112.07 (security), same bench method and caps, after the update: stt 100 W 5.37 s / 0.132 Wh (was 5.3 / 0.131); tts-hq 130 W 46.9 audio s per Wh (was 47.0); imggen `better` 130 W 6.91 s / 0.225 Wh (was 6.95 / 0.226); vidgen 2 s 130 W 206.9 s / 6.93 Wh (was 209.3 / 7.02); selfcheck ratio 1.14 (was 1.13), 0.3726 TFLOPS/W (was 0.3718): no change beyond noise, the unlock survived | 2026-11-18 |
