# Video benchmarks on a GPU host: measured results

Measured with the plan in `VIDEO_TOOLS_EVAL.md` section 3 (B1-B9) on a host with an 8 GB consumer card, a 12-thread CPU and 32 GB RAM, stock driver. The scripts are in `gpu-host/videobench/` (README in the script headers). Results, models and media stay on the host and are not in the repo.

## Setup

- Power caps are set with `nvidia-smi -pl`; every script restores the idle cap on exit. `measure.py` samples GPU power, VRAM and utilisation every 0.5 s and records CPU busy core-seconds and peak RAM from /proc.
- "Wh" is integrated GPU energy minus an 18 W resting draw times wall time (the idle value sampled before a run was inflated while the card was still in P2). CPU energy is not measured: RAPL needs root.
- Quality: SSIM and PSNR against the mezzanine. VMAF was not used: the distro ffmpeg has no libvmaf.
- Inputs: Tears of Steel 1080p (CC-BY 3.0, Blender Foundation) padded to 1920x1080, mezzanines encoded with x264 crf 12, three clips (talk, action, screen). Its soundtrack is used only for this private test.
- ComfyUI jobs use stock native nodes only, in a container with `--network none` and models mounted read-only. Run 1 includes the model load; later runs are warm. ComfyUI caches node outputs, so each run reads its own hard-linked copy of the input and every Wan run gets its own seed.
- All weights are ungated safetensors, licensed Apache-2.0, MIT or BSD-3, except MiniMax H3 (B4b), whose territory limits are in `GENERATIVE_SAFETY.md`.

## Results by task

### B2: encoding (20 s clips, means over talk, action and screen)

1080p:

| Encoder | Seconds | CPU core-s | GPU Wh | kb/s | SSIM | PSNR |
|---|---|---|---|---|---|---|
| SVT-AV1 2.3 preset 8 crf 35 | 7.3 | 63 | 0 | 1694 | 0.9876 | 43.5 |
| SVT-AV1 1.7 preset 8 crf 35 (old transcoder image) | 10.9 | 92 | 0 | 1696 | 0.9880 | 43.8 |
| SVT-AV1 2.3 preset 6 | 13.8 | 130 | 0 | 1718 | 0.9889 | 44.2 |
| SVT-AV1 2.3 preset 12 | 3.2 | 24 | 0 | 1770 | 0.9841 | 42.1 |
| SVT-AV1 2.3 preset 10 | 4.3 | 36 | 0 | 1824 | 0.9857 | 43.0 |
| x265 medium crf 26 | 11.5 | 102 | 0 | 1950 | 0.9880 | 43.7 |
| x264 veryfast crf 23 | 3.2 | 26 | 0 | 2948 | 0.9882 | 43.4 |
| NVENC HEVC p5 cq 28 | 2.5 | 7 | 0.027 | 3174 | 0.9898 | 45.5 |
| x264 medium crf 23 | 5.9 | 55 | 0 | 3561 | 0.9906 | 44.7 |
| NVENC H.264 p5 cq 28 | 2.5 | 7 | 0.026 | 3715 | 0.9898 | 45.4 |

720p:

| Encoder | Seconds | kb/s | SSIM |
|---|---|---|---|
| SVT-AV1 2.3 preset 8 | 4.6 | 837 | 0.9870 |
| SVT-AV1 2.3 preset 10 | 2.6 | 887 | 0.9848 |
| x264 medium | 2.9 | 1579 | 0.9892 |
| NVENC H.264 / HEVC | 1.5 | 1675 / 1485 | 0.9877 / 0.9885 |

NVENC times are near the 0.5 s sampling step and include decoding the mezzanine. The power cap does not matter for NVENC: the earlier measurement gave 529/537/531 fps at 100/130/200 W.

Findings:
- For Telegram, AV1 preset 8 gives half the size of NVENC and x264 at the same SSIM (within 0.003).
- Preset 6 saves only 1-2 % more size at twice the time: not worth it. Preset 10 is the fast option at about 7 % larger.
- SVT-AV1 2.3 is 1.5x faster than 1.7 at the same size and quality. The transcoder image moved to Debian trixie for it (see "Changes made").
- NVENC is the speed and energy choice: about 0.03 Wh and 7 core-s for 20 s of 1080p.
- x265 is dominated by AV1 preset 10: slower and larger.

### B1: a 60 s reference edit (REF-60)

The REF-60 edit:
- Two 30 s cuts with a 1 s crossfade.
- A warm 3D LUT plus brightness and saturation.
- A title from 1 to 5 s and a logo overlay.
- Music at -18 dB, ducked under the dialogue with a sidechain.
- Loudness normalised to -14 LUFS.
- Output: 1080p24, 59 s.

| Tool | Wall s (median of 3) | GPU Wh | CPU core-s | Output | Complete? |
|---|---|---|---|---|---|
| ffmpeg one filter graph + NVENC H.264 | 19.0 | 0.22 | 127 | 45.7 MB | Yes, every step. 59.0 s, -14.8 LUFS |
| ffmpeg + SVT-AV1 2.3 preset 8 crf 32 | 29.6 | 0.01 | 269 | 14.2 MB | Yes |
| ffmpeg + x264 medium crf 20 | 31.1 | 0 | 282 | 38.8 MB | Yes |
| Resolve Studio 21.1 via its scripting API | 16.0 (8 s cold start, 2.4 s build, 4.5 s render) | 0.22 | 25 | 64.9 s H.264 | No, see below |

Findings:
- In an edit, the filter graph (decode, LUT, overlays, audio) costs more CPU than the encoder. AV1 adds almost nothing over x264 and gives a file 2.7x smaller. For a Telegram delivery, the edit should end in AV1.
- ffmpeg with NVENC is the fastest complete edit.

What the Resolve API can and cannot do (probed on 21.1.1):

| Works | Does not work |
|---|---|
| Cuts (endFrame is exclusive) | Transitions and crossfades: no API call. |
| Extra tracks | Clip volume: `SetProperty("Volume")` returns False. |
| Logo position and zoom | Ducking: Fairlight automation is UI-only. |
| CDL | A still such as the logo keeps the default 5 s, whatever endFrame says. |
| A LUT, but only from the system LUT folder, by absolute path, after `RefreshLUTList` | `InsertFusionTitleIntoTimeline` is a ripple insert: every track moves 5 s later. It fails when the other tracks are locked. |
| Text+ titles | No AV1 render. Only H.264/H.265 NVIDIA and YUV 422 10-bit are offered. |
| Rendering with H.264/H.265 NVIDIA | The user LUT folder, relative names and the node graph's `SetLUT` all fail. |

So for an agent, Resolve is a render and grading engine, not a scripted editor. Use it for grading with LUT and CDL, its own AI tools (Super Scale, Magic Mask, NR), and Resolve projects a person made by hand. Scripted edits go through ffmpeg.

### B3/B4: local video generation (480p)

| Model and runtime | Cap | Output | Wall s | Wh | s per output second | Wh per output second | VRAM / RAM peak |
|---|---|---|---|---|---|---|---|
| Wan 2.2 TI2V-5B, Diffusers bf16, 30 steps | 100 W | 49 f, 24 fps (2.0 s) | 235 | 4.44 | 115 | 2.2 | 7.7 GB / 24 GB |
| same | 130 W | 49 f | 181 | 4.31 | 89 | 2.1 | same |
| same | 159 W | 49 f | 170 | 4.99 | 83 | 2.4 | same |
| same | 100 W | 81 f (3.4 s) | 351 | 7.07 | 104 | 2.1 | same |
| same, 1280x704 | 100 W | 49 f | failed after 447 s | | | | VAE decode out of memory (Diffusers decodes untiled) |
| Wan 2.2 TI2V-5B, ComfyUI fp16, 30 steps | 100 W | 49 f (2.0 s) | 153 | 3.41 | 75 | 1.7 | 7.6 GB / 14 GB |
| Wan 2.2 I2V-14B fp8 + lightx2v 4-step LoRA, ComfyUI | 100 W | 33 f, 16 fps (2.1 s) | 113 | 2.50 | 55 | 1.2 | 7.7 GB / 29 GB |
| same | 130 W | 33 f | 69 | 2.06 | 33 | 1.0 | 7.1 GB / 29 GB |
| same | 100 W | 81 f (5.1 s) | 322 | 7.20 | 64 | 1.4 | 6.1 GB / 29 GB |

Findings:
- **Use ComfyUI, not Diffusers.** For the same Wan 5B model it is 35 % faster, uses 23 % less energy and needs 10 GB less RAM. Its tiled VAE decode should also make the 704p size possible.
- **Wan 14B with the 4-step LoRA is the best local option.** It is the cheapest per output second and looked the most coherent: the people in the photo smiled and gestured believably. Two catches:
  - It outputs 16 fps; interpolate with RIFE to reach 24-32 fps (adds about 0.1 Wh and about 10 s per 5 s).
  - It peaks at 29 GB of system RAM out of 32. Nothing else heavy (the LLM, a second job) may run next to it.
- Image-to-video follows the image. A text prompt unrelated to the photo (the fox) was ignored.
- **The power cap matters for generation:**
  - 130 W is faster and uses no more energy (Wan 5B: -23 % time, -3 % Wh; Wan 14B: -39 % time, -18 % Wh).
  - 159 W gains 6 % time for 16 % more energy.
  - Use 130 W for generation, not 100 W as the research assumed.
- Text-to-video with Wan 5B: both runtimes gave a plausible scene (a fox in snow). Short clips only: 5 s of video costs about 6-9 minutes and 9-11 Wh.

### B4b: MiniMax H3, video with stereo audio

MiniMax H3 (Hailuo 3) is open-weight and its Hugging Face repo is ungated.

- **Runtime:** stock ComfyUI already supports it natively (`comfy_extras/nodes_minimax_h3.py`). It also ships the blueprint "Image to Video (MiniMax H3)". No custom node or extra code is needed.
- **Files used, from that blueprint (about 45 GB, `fetch_models.sh h3`):**

  | File | Size |
  |---|---|
  | `minimax_h3_fl2va_pruned_int8_convrot` | 21 GB |
  | `qwen3vl_32b_minimax_h3_nvfp4_awq` (text encoder; ComfyUI emulates nvfp4 on this Ampere card) | 16 GB |
  | Video VAE fp16 | 5.2 GB |
  | Audio VAE | 0.6 GB |
  | lightx2v turbo 8-step LoRA | 2 GB |

- **Job:** `comfy_run.py h3`. It is text-to-video with an optional first frame. Settings: 8 steps, res_multistep sampler, simple scheduler, no CFG, 24 fps.
- **Licence:** territory limits (not licensed in the EU, UK, South Korea and USA) are in `GENERATIVE_SAFETY.md`.

| Clip | Cap | Wall s | GPU Wh | s per output second | Wh per output second | VRAM / RAM peak |
|---|---|---|---|---|---|---|
| 832x480, 56 frames (2.3 s), turbo 8 steps | 130 W | 204 | 3.72 | 87 | 1.6 | 7.6 GB / 17.9 GB |
| 832x480, 124 frames (5.2 s), turbo 8 steps | 130 W | 395 | 7.62 | 76 | 1.5 | 7.6 GB / 17.9 GB |

Findings:
- **The best local generator tested.**
  - The prompt asked for an 8-bit NES-style Spider-Man swinging over a city at night, with chiptune music. H3 delivered exactly that: a consistent palette and pixel grid, a parallax skyline, a believable swing, landing and pose, and a game HUD (the HUD text is invented letters).
  - The audio, generated in the same pass, has rhythmic beats and pitched tones.
  - Wan 5B and Wan 14B follow a style request far less closely, and neither makes sound.
- **Cost is close to Wan 14B 4-step:** 1.5 vs 1.0-1.4 Wh per output second. The extra pays for the audio and the far better prompt following.
- **Load:** about 30 s per run (text encoder, then the model streamed from RAM). The remaining time grows roughly linearly with length.
- **Memory:**
  - RAM stayed at 18 GB and no swap was used. ComfyUI streams both 16-21 GB models instead of holding them together.
  - The bench container was capped at 26 GB anyway (`VB_MEM=26g`), so an overflow kills ComfyUI and not the desktop.
  - The LLM must still not share the card.
- **Not yet tested:**
  - 768p, the trained size; 10-15 s clips; image-to-video with a first frame.
  - The 4-step turbo LoRA, and the int8 text encoder instead of nvfp4.
  - The model card says the trained range is 124-362 frames (about 5-15 s).

### B4c: chained H3 segments for clips longer than 10 s

`gpu-host/videobench/chain_bench.sh` at 130 W, 832x480. A text-only 5 s segment, then a second 5 s segment
with the same prompt and another seed, continued from the first. Each pair is joined: the second segment loses the frames
it repeats, and the sound crossfades. Times are for the second segment.

| Variant | How segment 2 continues | Time | Tail reproduced | Picture at the join | Sound at the join |
|---|---|---|---|---|---|
| A | `first_frame` = last frame of segment 1 | 417 s | 33.7 dB | no cut, but **the motion stops** in segment 2 | continuous |
| B5 | `MiniMaxH3AddGuide`: last 5 frames **with** their sound at frame 0 | 421 s | 34.4 dB | the motion continues | **~100 ms of silence** |
| B22 | the same with the last 22 frames (0.9 s) | 453 s | 34.2 dB | the motion continues | **~100 ms of silence** |
| **B5n** | last 5 frames **without** their sound (`tailaudio=0`), 100 ms crossfade | 423 s | 34.5 dB | the motion continues, **no visible seam** | continuous |
| B22n | the same with the last 22 frames | 449 s | 34.3 dB | the motion continues, a seam the eye can catch | continuous |

- The audio guide leaves about 100 ms of silence where the anchored sound ends. It does not reproduce that sound either:
  the correlation with segment 1's tail is -0.14 and -0.36.
- The picture join step is 1.2-1.3x a normal frame-to-frame change in every variant.
- Judged by eye on all five: B5n is the best, B22n's join is visible, and in the earlier ones the seam showed only when scrubbing.
- **Decision:** chain with B5n. Each segment after the first anchors the last 5 frames of the previous one, without
  sound, drops those 5 frames when joining, and crossfades 100 ms of its own sound. That is about 7 minutes per segment;
  30 s are three 10 s segments.
- **Open, minor:** Telegram Desktop's progress bar draws a small break near the end of a joined clip (seen on B22n). The picture and sound play fine. Suspects: the audio track ends about 35 ms after the video (AAC
  padding after the crossfade), or how the join's MP4 is laid out. Check `ffprobe` of the join (stream durations, edit
  list), and try `-shortest` or trimming the audio to the video length.

### B6: video upscale, 72 frames 960x540 to 1080p (3 s)

| Model | Cap | Wall s | s per frame | Wh | VRAM | Look |
|---|---|---|---|---|---|---|
| Real-ESRGAN general-x4v3 (compact SRVGG) | 100 W | 43.5 | 0.60 | 0.60 | 1.4 GB | Clean and slightly smoothed |
| same | 130 W | 41.0 | 0.57 | 0.65 | 1.4 GB | |
| Real-ESRGAN x4plus | 100 W | 325 | 4.5 | 6.97 | 5.4 GB | Same look as general-x4v3, plasticky skin |
| same | 130 W | 241 | 3.3 | 6.85 | 5.4 GB | |
| SeedVR2 3B int8, temporal chunks | 100 W | 736 | 10.2 | 16.4 | 6.9 GB | Clearly the best: real skin texture and stubble, no flicker seen |
| same | 130 W | 616 | 8.6 | 17.2 | 7.0 GB | |

Findings:
- Default: general-x4v3 at 100 W. It is 8x faster than x4plus with the same look, so x4plus has no place. One minute of 24 fps video takes about 15 minutes and 12 Wh.
- Premium: SeedVR2 at 130 W, for short clips only (one minute takes about 3.4 hours). Offer it as a slow "best quality" batch job with a ready message.

### B7: frame interpolation, 120 frames 720p, x2 (24 to 48 fps)

| Model | 100 W | 130 W | VRAM |
|---|---|---|---|
| RIFE 4.26 | 11.0 s, 0.16 Wh | 10.5 s, 0.18 Wh | 1.3 GB |
| RIFE 4.25 lite | 11.0 s, 0.16 Wh | 10.5 s, 0.18 Wh | 1.3 GB |
| FILM fp16 | 64 s, 1.36 Wh | 50.5 s, 1.41 Wh | 4.6 GB |

- RIFE 4.26 at 100 W is the default. The lite model gains nothing here.
- Most of the RIFE time is decoding and encoding, so the power cap does not help.
- FILM is 6x slower. Keep it only for large motion, if RIFE shows artefacts.

### B8: matting, BiRefNet per frame, 120 frames 720p

- 100 W: 103.5 s and 2.32 Wh. 130 W: 70.5 s and 2.12 Wh.
- It uses 7.8 GB of VRAM, the whole card, so it is an exclusive job.
- The masks were clean on a dialogue shot.
- Use 130 W: faster and less energy.
- RobustVideoMatting (people, recurrent, much lighter) was not tested: it needs its own code.

### Not measured

- **B5, LTX-2.3/2.5:** the weights are gated on Hugging Face and need a personal account token. That is against the plan's rule.
- **RVM, ProPainter and auto-editor:** each needs external code that was not reviewed and installed for this run.
- **B9, SAM + inpainting (object removal):** deferred. It needs the same external code and review.
- **VMAF:** see Setup.
- **CPU energy:** see Setup.

## Ranking by consumption, speed and privacy (all class A, local)

| Rank | Task and tool | Energy | Time for the test clip | Power mode |
|---|---|---|---|---|
| 1 | NVENC encode | 0.03 Wh per 20 s of 1080p | 2.5 s | 100 W (cap does not matter) |
| 2 | SVT-AV1 2.3 preset 8 (CPU) | 0 GPU, 63 core-s per 20 s of 1080p | 7.3 s | Not applicable |
| 3 | ffmpeg scripted edit (REF-60) | 0.22 Wh (NVENC) or about 270 core-s (AV1) | 19-30 s per minute | 100 W |
| 4 | Resolve render, grade and LUT | 0.22 Wh, 2 GB VRAM | 16 s with a cold start | 100 W |
| 5 | RIFE interpolation | 0.16 Wh per 5 s of 720p | 11 s | 100 W |
| 6 | Real-ESRGAN general-x4v3 upscale | 0.6 Wh per 3 s | 43 s | 100 W |
| 7 | BiRefNet matting | 2.1 Wh per 5 s of 720p | 70 s | 130 W |
| 8 | Wan 14B 4-step image-to-video | 1.0 Wh per output second | 33 s per output second | 130 W |
| 8b | MiniMax H3 text-to-video with audio (best quality) | 1.5 Wh per output second | 76 s per output second | 130 W |
| 9 | Wan 5B text-to-video (ComfyUI) | 1.7 Wh per output second | 75 s per output second (at 100 W) | 130 W |
| 10 | SeedVR2 upscale | 16-17 Wh per 3 s | 10-12 minutes per 3 s | 130 W |

## Consequences

- The transcoder image uses a Debian trixie base (ffmpeg 7.1, SVT-AV1 2.3), which encodes AV1 faster than the older image at the same size.
- Power modes: generation, matting and SeedVR2 run best at 130 W; everything else at 100 W.
