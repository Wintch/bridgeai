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

One command does everything: it picks the first GPU host that answers, and falls back to this container's ffmpeg
when none does.

```
gateway transcode <input> <output.mp4> [option=value ...]
```

**Options** (a closed list; anything else is refused):

| option | values | default |
|---|---|---|
| `codec` | `h264`, `hevc` | `h264` |
| `height` | 144-2160 (keeps the aspect ratio) | unchanged |
| `hflip`, `vflip` | `1` to mirror | off |
| `start`, `duration` | seconds, to cut a segment | whole video |
| `cq` | 15-40, lower = better and bigger | `28` |
| `audio` | `aac`, `copy`, `none` | `aac` |

Example: `gateway transcode in.mp4 out.mp4 height=720 hflip=1 start=10 duration=30`.

**After it runs:**
- The last line says where it ran (GPU host or "this container's CPU") and how long it took. Tell the person.
- A CPU run of a long video can take several minutes. Say so up front when `gateway status` shows no GPU host UP.
- Verify the output with `ffprobe` before saying it is done.
- Never call the GPU hosts with curl yourself: `gateway` records every job (only time, size and where it ran) so
  the operator can see whether the GPU machines are worth keeping on.

## Limits

- Up to 4 GB per file and 30 minutes per encode.
- Only these operations. Filters, subtitles or anything exotic stay on local `ffmpeg`.
- `gateway status` lists the GPU hosts this person may use. With none listed, everything runs on the CPU, which is
  expected for most guests.
