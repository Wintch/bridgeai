# mosher: datamosh over HTTP

mosher is a CPU-only HTTP service behind `gateway mosh`. It runs on any Docker host and needs no GPU. It uses
[FFglitch](https://ffglitch.org) (GPL), which edits the MPEG-4 motion vectors inside the bitstream. That makes it a real
datamosh, unlike tools that simulate the look by shifting blocks of frames that are already decoded (some ComfyUI nodes).

## The technique

mosher copies one clip's motion vectors onto a "carrier" that stands still. Decoded, the still picture is dragged by the
other clip's movement, and none of that clip's own pixels appear.

1. Both clips are scaled to the same size and set to 30 fps.
2. The carrier is the picture (a photo or a video) followed by its last frame held (`tpad=stop_mode=clone`). Held
   P-frames have no motion and no residual.
3. `ffgac` encodes both clips as MPEG-4 part 2 with one I-frame and forced vectors on every macroblock:
   `-c:v mpeg4 -qscale:v 1 -bf 0 -g max -sc_threshold max -mpv_flags +nopimb+forcemv -fcode 6 -an`
4. `ffedit -f mv -e` exports both sets of vectors to JSON.
5. The carrier's vectors, from the first held frame on, are replaced by the motion clip's, multiplied by `gain` and clamped
   to the range `-fcode 6` allows.
6. `ffedit -f mv -a` writes them back. ffmpeg decodes the result and encodes H.264, with the motion clip's audio.

Modes:

- **One video, in cycles (default).** Each cycle lasts `cycle` seconds (4 by default): the clip plays clean for `hold`
  seconds, then the last clean frame freezes and the clip's own motion drags it (the strength ramps in over 0.3 s), and
  over the last `heal` seconds (0.8 by default) the result fades back to the real video. Every cycle starts on a fresh
  I-frame (`-g` equals the cycle length), so it breaks and heals again and again. Only whole cycles are kept.
- **One video, once** (`cycle=0`). The clip plays clean for `hold` seconds, then freezes and stays broken.
- **Picture + motion clip.** The picture shows for `hold` seconds, then the motion clip's movement drags it. It breaks once.

## Service API

Port 8690, Python standard library only. `POST /mosh` needs `Authorization: Bearer <MOSH_TOKEN>`.

| Route | Auth | Notes |
| --- | --- | --- |
| `GET /healthz` | none | 200 `ok mosher` once `ffgac`, `ffedit`, ffmpeg and ffprobe answered at start, else 503 with the reason |
| `POST /mosh?hold=&gain=&height=&audio=&cycle=&heal=` | Bearer | Body `[picture bytes][motion bytes]`, header `X-Picture-Length` = the picture's size (0 or absent: one video only). Returns `video/mp4` (H.264 + AAC) with `X-Mosh-Seconds` and `X-Mosh-Size` (`WxH`) |

| Parameter | Range | Default |
| --- | --- | --- |
| `hold` | 0 to 10 s | one video: 1 s; photo: 0.5 s; picture video: the whole video, up to `PIC_MAX_S` |
| `gain` | 0.25 to 4 | 1 |
| `height` | even, 240 to 720 px | 480 |
| `audio` | 0 or 1 | 1 (the motion clip's sound) |
| `cycle` | 0 (break once), or 1.5 to 20 s | 4 (`CYCLE_DEFAULT`); only for one video |
| `heal` | 0 (hard cut) to 3 s | 0.8 |

Cycle mode needs a cycle of at least `hold` + `heal` + 0.5 s, and a video at least that long. The width follows the motion
clip's aspect ratio (a multiple of 16, 128 to 1280 px). The picture is scaled to cover that size and cropped. At most
`MOTION_MAX_S` seconds of the motion clip are used. Any other parameter gets a 400.

| Code | Meaning | Gateway reaction |
| --- | --- | --- |
| 200 | Clip ready | Writes `OUT.part`, renames it to OUT when complete, exit 0 |
| 400 | Unreadable file, bad option, or a video too short for `hold` | Stops, exit 2 |
| 401 | Wrong or missing token | Prints a note for the operator, tries the next host |
| 413 | Body empty or over `MAX_MB` | Stops, exit 2 |
| 429 | Busy (`JOBS` running) | Tries the next host; if all are busy, exit 5 |
| 500 | The job failed on these files | Tries the next host; if all fail, exit 3 (`mosh: failed`) |
| 504 | The job ran past `TIMEOUT_S` | Tries the next host; exit 3 (`mosh: too slow`) |
| 507 | Less than `FREE_NEED_MB` free in `WORK` | Same as 429 |

Before refusing, mosher reads and discards the upload, so the gateway sees the status code, not a dropped connection.

Host environment variables (main ones): `MOSH_TOKEN`, `PORT` (8690), `WORK` (`/work`), `FFGLITCH` (`/opt/ffglitch`),
`FFMPEG`, `FFPROBE`, `JOBS` (1), `MAX_MB` (200), `MOTION_MAX_S` (20), `PIC_MAX_S` (10), `TIMEOUT_S` (600),
`FREE_NEED_MB` (300), `CYCLE_DEFAULT` (4; 0 brings back the single break).

## How the gateway picks hosts

`gateway mosh` reads the `mosh` entries of the stack's gateways list and ranks them with `ranked('mosh')`: hosts that answer
`/healthz` come first, ordered by the wait time from their `/status`, and config order breaks ties. mosher has no `/status`,
so config order decides between mosh hosts. A host that is off is skipped, and if none answers the gateway prints
`mosh: off`. There is no local fallback: no ffmpeg filter on the Hermes side imitates a real datamosh.

## Logging

mosher prints one line per job to stdout (sizes, output dimensions, time, mode, option query), never file names or content;
a failed job logs the step name and the error type. The gateway also writes one line per job (seconds and sizes). Only the
401 note names a host, for the operator. The text the agent sees is fixed and never echoes host replies.

## Running it

The image is built `FROM transcoder:latest`, so it shares that image's Debian and ffmpeg layers and adds about 60 MB: the
FFglitch `ffgac` and `ffedit` binaries, fetched at build time and checked against a pinned SHA-256. Build commands are in
`gpu-host/IMAGES.md`.

`gpu-host/run_services.sh mosher` starts it with the `HARDEN` options (`--cap-drop ALL`, `no-new-privileges`, a pids limit,
capped logs), `--memory 3g`, `--cpus ${MOSH_CPUS:-4}`, `--user 1000:1000` and a 1 GB tmpfs at `/work`, so jobs never write to
disk and each job deletes its files. It is skipped with a message when `MOSH_TOKEN` is unset in `gpu-host/host.env`. The
restart policy comes from `GPU_RESTART` and defaults to `no`: the service is started only when needed.

Build both and start: `BUILD=1 gpu-host/run_services.sh transcoder mosher`. Check: `curl -s http://<gpu-host>:8690/healthz`.

## Registering the host

On the machine that holds the master gateways list, from the `aibridge` directory (the token goes through a pipe and is
never printed):

```
<read MOSH_TOKEN from <gpu-host>'s host.env> | python3 ops/gateways_host_service.py <host> mosh 8690 --token-stdin
python3 ops/gateways_sync.py
```

Add the host to the `gpu` list of every stack that may use it before running the sync. The sync writes the `mosh` entry
(`url` and `token`) into each stack's `gateways.json`. The `video` skill pack carries `aibridge/SKILL_datamosh.md`, which
tells the agent when and how to call `gateway mosh`. Usage and options: that skill and `gateway mosh --help`.

## Tests

- `aibridge/gateway_mosh_selftest.py`: the gateway against fake hosts (only media is sent, option ranges, body framing,
  token, a busy host moving on to the next, 400 stopping at once, nothing configured or answering, whole-file output).
  Run `python3 -I gateway_mosh_selftest.py` from `aibridge/`. It needs neither ffmpeg nor FFglitch.
- `gpu-host/mosher/server_selftest.py`: the service with the real FFglitch: routes, token, option limits, output size,
  frame counts, sound, the picture really moving (PSNR), the cycle (clean, smeared, healed, smeared again), an empty `WORK`
  afterwards, 507 and a missing `MOSH_TOKEN`. Skipped when ffmpeg, ffprobe or `ffgac`/`ffedit` (in `$FFGLITCH`) are
  missing. Inside the image: `docker run --rm -v $PWD/gpu-host/mosher:/t:ro mosher:latest python3 -I /t/server_selftest.py`

`aibridge/ops/run_selftests.sh` runs both.
