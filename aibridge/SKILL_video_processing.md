---
name: video-processing
description: "Edit a video with ffmpeg (brightness, contrast, color, text or watermark, overlays, crops, grain, audio extraction): probe, encode, verify, say which tool made the file. Plain re-encode, shrink, flip or trim goes to the GPU with `gateway transcode`."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, ffmpeg, filters, watermark, audio]
---

# Video processing

Recipes written from real jobs and folded into the image for every stack.

## Which tool

- **Re-encode, shrink, change height, flip, trim, change codec**: `gateway transcode` (skill `gpu-transcode`):
  NVENC on a GPU host, about 4x faster than this container's CPU. AV1 ("optimizalo", "que pese menos") is ALWAYS `gateway transcode
  ... codec=av1`, never ffmpeg here.
- **Make a short video smoother (48 fps) or 2x larger**: `gateway enhance IN.mp4 OUT.mp4` (GPU, RIFE and Real-ESRGAN; run it in the
  background), not ffmpeg `minterpolate` or scale filters. If it says `GPU: off`, say so; do not fall back to ffmpeg unless they ask.
  If it says `GPU: in use`, `GPU: reserved` or `GPU: busy` (exit 5: VR, a game or video editing is using the machine, the operator marked it busy, or
  another job runs), say so and offer to try later; no loop and no ffmpeg substitute. For a planned run of many clips use `gateway gpu batch`
  (see `GPU_MEDIA_TOOLS.md`); if the person asks to turn the GPU off, `gateway gpu off`.
- **Datamosh / glitch where one clip's movement drags another picture (the MoshUp effect)**: `gateway mosh` (skill `datamosh`),
  never an ffmpeg imitation.
- **Anything else** (brightness/contrast/saturation, text or watermark, overlays, crops, grain or denoise, audio
  only): ffmpeg here, on the CPU. This container has no GPU: do not try `h264_nvenc` locally, use `libx264`.
- **"What does this video show / say"**: not this skill, run `gateway video` in the terminal (skill
  `video-understanding`); it is a shell command, not a tool name.
- **"In DaVinci" / "con Resolve"**: skill `davinci-resolve`.
- **Animated titles, lower thirds, keyframed motion, effects**: skill `effectcraft` when it is available (its "Which
  tool" table); a simple sliding text is fine here (recipe below).

## Always-on rules

- Probe the input with `ffprobe` first. Keep frame rate, size, audio and duration unless asked to change them.
- Tell the person which tool wrote the final file. Never say Resolve or the GPU did it when ffmpeg on the CPU did.
- Use a moderate value when the person gives no amount (e.g. `eq=brightness=0.06`) and say which value you used.
- Text with punctuation in `drawtext`: write it to a file and use `textfile=`, not `text=`.
- An expression with commas inside a filter option must be quoted or escaped, or ffmpeg fails ("No option name
  near ..." or "Failed to inject frame into filter network"): `y='if(lt(t,2),H+80-70*t,H-60)'` or `min(t\,2)`.
- Always pass `-y`: without it ffmpeg stops at the "Overwrite? [y/N]" prompt when the output exists.
- Text that slides in from below and stays: `drawtext=...:x=(w-text_w)/2:y='if(lt(t,2),H+80-70*t,H-60)':shadowx=3:shadowy=3:shadowcolor=black@0.8`
  (checked). Without the `if`, `y=H+80-40*t` keeps moving and leaves the frame.
- Long jobs: run ffmpeg in the background with a completion notice (skill `job-notify`); never deliver a partial file.
- Clean up temporary files (extracted frames, audio clips) in `/root/.hermes/cache/scratch/` as soon as they are no
  longer needed: stale frames get mistaken for the person's media later.

## Procedure

1. **Inspect**: codec, size, frame rate, duration, audio streams, file size.
2. **Filter**: `eq=brightness=..:contrast=..:saturation=..`, `hflip`, `crop=w:h:x:y`, `noise=alls=20:allf=t+u` (grain),
   `hqdn3d` (denoise), `drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile=/tmp/t.txt:x=10:y=H-30:fontsize=24:fontcolor=white:box=1:boxcolor=0x00000099`.
3. **Encode**: `-c:v libx264 -preset veryfast -crf 23`, audio `-c:a copy` when compatible (else `-c:a aac`),
   `-movflags +faststart` for MP4. Audio only: `-vn`, same audio rules.
4. **Verify**: `ffprobe` the result (duration, streams, size, frame rate) and look at one frame from the middle to
   check the change is visible.
5. **Deliver** the file and say what changed, the values used and which tool encoded it.
