---
name: gpu-transcode
description: "Re-encode, shrink, flip or trim a video on the operator's GPU desktop (NVIDIA NVENC) instead of this container's CPU: about 4x faster. Falls back to local ffmpeg when the desktop is off."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, ffmpeg, transcode, nvenc, gpu]
---

# GPU transcoding (NVENC)

> **Deployment-specific.** `gpu-desktop` is a LAN desktop running `../transcoder/`. The container resolves the name
> through compose `extra_hosts` (GPU_DESKTOP_IP in the untracked .env). That desktop is NOT always on.

## When to use

Any plain video job without DaVinci Resolve that the person is waiting for:
- convert or compress;
- lower the resolution;
- flip;
- cut a segment.

Measured 2026-10-09 on 30 s of 1080p60 down to 720p:
- this container's CPU (libx264 veryfast): 26.6 s;
- the desktop: 6 s including upload and download.

The gap grows with the length of the video.

## Recipe

1. **Check the desktop is up** (2 s):
   `curl -s -m 2 http://gpu-desktop:8610/healthz`
   - `ok nvenc`: use it.
   - Anything else, or no answer: the desktop is off. Use local `ffmpeg` as usual and do not retry the desktop
     during this task.
2. **Send the file and get the result back in one call:**
   `curl -s -f --data-binary @<input> -o <output.mp4> "http://gpu-desktop:8610/transcode?<options>"`
3. **Options.** It is a closed list; anything else is rejected with 400.

   | option | values | default |
   |---|---|---|
   | `codec` | `h264`, `hevc` | `h264` |
   | `height` | 144-2160 (keeps the aspect ratio) | unchanged |
   | `hflip`, `vflip` | `1` to mirror | off |
   | `start`, `duration` | seconds, to cut a segment | whole video |
   | `cq` | 15-40, lower = better and bigger | `28` (similar size to x264 crf 23) |
   | `audio` | `aac`, `copy`, `none` | `aac` |

   Example: `?height=720&hflip=1&start=10&duration=30`.
4. **Errors:**
   - `429`: two encodes are already running. Wait a minute and retry once, else do it locally.
   - `400`: an option is wrong. Fix it, don't loop.
   - `500` / `504`: say what failed and do it locally.
5. **Verify** the output with `ffprobe` (has a video stream, the duration you expect) before telling the person it
   is done. Say which machine encoded it and how long it took: the `X-Encode-Seconds` response header gives the
   GPU time.

## Limits

- Up to 4 GB per file and 30 minutes per encode.
- Only these operations. Filters, subtitles or anything exotic stay on local `ffmpeg`.
- Guest stacks cannot reach the LAN (firewall), so for them step 1 fails and they use local `ffmpeg`. That is
  expected.
