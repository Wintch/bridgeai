---
name: datamosh
description: "Datamosh a video (the MoshUp app effect): the movement of one clip drags the pixels of a photo or another video, or a clip freezes and its own later movement smears that frame, with `gateway mosh` (FFglitch on a mosh host). For: datamosh, mosh, moshup, glitch de movimiento, que el movimiento arrastre la foto, píxeles derretidos, датамош, глитч."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, datamosh, glitch, ffglitch, effects]
---

# Datamosh (`gateway mosh`)

A real datamosh: the video's own motion vectors (MPEG-4, edited with FFglitch) are moved onto another picture, so its pixels
are dragged and smeared by the other clip's movement. ffmpeg filters here do not do this: never imitate it with blends,
`minterpolate` or `tblend`, and never say a fake one is a datamosh.

## Which form

Ask only if it is not clear from what they sent:

- **One video** ("moshealo", "datamosh a este video"): it loops like the MoshUp app. Each cycle (default 4 s) plays clean
  for `--hold` seconds (default 1), then freezes and its own movement smears the picture, then over `--heal` seconds
  (default 0.8) it fades back to the real video, and the next cycle breaks it again. Best with a clip that moves a lot.
  `gateway mosh /workdir/in.mp4 /workdir/descargas/mosh.mp4`
  Shorter, faster loops: `--cycle 2.5`. A hard cut back instead of a fade: `--heal 0`. Break once and stay broken (the
  older look): `--once`. The clip keeps whole cycles only (a 10 s clip with 4 s cycles gives 8 s).
- **A photo or video + a video with movement** ("que el movimiento de este video arrastre esta foto"): the picture shows
  first (a photo 0.5 s, a video plays up to 10 s, or `--hold` s of it), then the other clip's movement drags it.
  `gateway mosh --picture /workdir/foto.jpg /workdir/movimiento.mp4 /workdir/descargas/mosh.mp4`
  The picture is `--picture`, the clip whose movement they want is MOTION (the first plain argument).

## Options

| option | what | default |
|---|---|---|
| `--hold S` | seconds of the clean picture before the movement takes over (0-10) | 1 (one video), 0.5 (photo), the whole picture video (up to 10 s) |
| `--gain G` | strength of the movement, 0.25-4: 2-3 for a wilder smear, 0.5 for a gentle melt | 1 |
| `--height H` | output height, 240-720 (even); width follows MOTION's aspect | 480 |
| `--cycle S` | one video: length of each break-and-heal loop, 1.5-20 s; 0 or `--once` = break once | 4 |
| `--heal S` | one video: seconds of the fade back to the real video, 0-3 (0 = a hard cut) | 0.8 |
| `--mute` | no sound (default: MOTION's sound, lined up with its movement) | sound on |

At most 20 s of MOTION are used; longer clips are cut. Files up to 200 MB together.

## After it runs

Say in one line what they will see before sending it: one video "se ve limpio, se derrite con el movimiento y se vuelve a
armar, en loop"; a picture and a video "la foto se ve un momento y después el movimiento la arrastra".

- `done: OUT (WxH, made in N s, K KB)`: send it with the `MEDIA:OUT` line it prints, and offer one variation (another
  `--gain` or `--hold`) instead of making several unasked.
- `mosh: busy`: another clip is being moshed; tell them to try in a minute. Never retry in a loop.
- `GPU: in use` / `GPU: reserved` / `GPU: busy` (exit 5): the machine hosting the mosher is in use (VR, a game or video editing), marked busy by the operator, or busy with another job; try later, never in a loop.
- `mosh: off`: no mosh machine answers; say so plainly. There is no local fallback.
- `GPU: not on this bot` or `GPU: not reachable from this bot`: say no at once and offer what the sentence names (the operator, or `gateway tareas` if this bot has a board); no imitation.
- `mosh: failed`: the machine is on but could not mosh these files; offer once to try another clip or other options.
- `mosh: too slow`: the job took too long; a shorter clip or a lower `--height` may work, once.
- `mosh: not available`: the machine refused this assistant's access key; the operator has to fix it.
- `the mosh host refused these files`: not a readable video/picture, or `--hold` as long as the video (nothing is left to
  move it): fix that once.
- Do not name the machine or its address; say "the mosh machine".
- Never call the mosh hosts with curl: `gateway` logs each job (time and size only) for the operator.
