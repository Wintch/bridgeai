---
name: gpu-transcode
description: "Re-encode, shrink, flip or trim a video, or make it AV1 to weigh less, on a GPU host (NVENC, or its CPU for AV1) instead of this container's single CPU: much faster. Optimizá el video, comprimilo, pasalo a AV1, que pese menos. Never run AV1 in ffmpeg here."
version: 1.2.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, ffmpeg, transcode, nvenc, gpu]
---

# GPU transcoding (NVENC)

> **Deployment-specific.** A GPU host on the private network runs `../transcoder/`; the host list is in the stack's `gateways.json`. A host is NOT always on.

## When to use

Any plain video job without DaVinci Resolve that the person is waiting for:
- convert or compress;
- lower the resolution;
- flip;
- cut a segment.

Measured on 30 s of 1080p60 down to 720p:
- this container's CPU (libx264 veryfast): 26.6 s;
- a GPU host: 6 s including upload and download.

The gap grows with the length of the video.

## Recipe

One command does everything:
- it asks every video host how busy it is and sends the job to the one that will finish first;
- when all are full it waits for a free slot (up to 10 min) and says so;
- it uses this container's CPU only when that is quick: a small clip, or nothing else answering and the estimate under 15 min. Here a
  video bigger than 1080p is made at 1080p (it says so; give `height=` for another size), so it fits this container's memory;
- otherwise it refuses with a clear sentence (exit 3). Tell the person in one line and offer a smaller `height=`;
- when the GPU machine itself says it is in use (`GPU: in use`: VR, a game or video editing; `GPU: reserved`: the operator marked it busy; `GPU: busy`:
  another job) and the clip is too big for this container, it stops with exit 5: say so and offer to try later (no loop). A GPU machine that starts its
  services on demand may add half a minute to the first job after a quiet while; the command waits by itself.

This container has one CPU and 2.5 GB: a 4K AV1 encode by hand runs for hours and is killed for memory.

**Never encode video by hand for a delivery** in the terminal. `ffmpeg` here refuses AV1 encoders (`libsvtav1`, `libaom-av1`,
`librav1e`) and points to `gateway transcode ... codec=av1`; for 4K material by hand even h264 takes a very long time. Never retry a
refused job another way, and never hand over a file that is still being written: a growing `.mp4` has no index and does not play.

**4K or bigger for a chat:** ask for `height=720` (or `480` for a quick preview). A 72 s 4K clip became 15 MB at 480p.

```
gateway transcode <input> <output.mp4> [option=value ...]
```

**Options** (a closed list; anything else is refused):

| option | values | default |
|---|---|---|
| `codec` | `h264`, `hevc`, `av1` | `h264` |
| `height` | 144-2160 (keeps the aspect ratio) | unchanged |
| `hflip`, `vflip` | `1` to mirror | off |
| `start`, `duration` | seconds, to cut a segment | whole video |
| `cq` | 15-40, lower = better and bigger | `28` |
| `audio` | `aac`, `copy`, `none` | `aac` |

Example: `gateway transcode in.mp4 out.mp4 height=720 hflip=1 start=10 duration=30`.

**Which codec:** to send a video in Telegram use `codec=av1`: Telegram does not re-encode videos, so the person downloads
exactly this file, and AV1 was 27-35 % smaller than H.264 at about the same quality on a real phone clip (it encodes on the GPU
host's CPU, about a third of the clip's length for 720p). It played on current phones and PCs. Use `h264` when the person says
it does not play (old phone), for WhatsApp, or for a file they will edit elsewhere. Never `.webm`: Telegram sends it as a file.

**After it runs:**
- The last line says where it ran (GPU host or "this container's CPU") and how long it took. Tell the person.
- A CPU run of a long video can take several minutes. Say so up front when `gateway status` shows no GPU host UP.
- Verify the output with `ffprobe` before saying it is done.
- Never call the GPU hosts with curl yourself: `gateway` records every job (only time, size and where it ran) so
  the operator can see whether the GPU hosts are worth keeping on.

## Limits

- Up to 4 GB per file and 30 minutes per encode.
- Only these operations. Filters, subtitles or anything exotic stay on local `ffmpeg`.
- `gateway status` lists the GPU hosts this person may use. With none listed, everything runs on the CPU, which is
  expected for most guests.
