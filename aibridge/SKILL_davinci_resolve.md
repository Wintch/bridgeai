---
name: davinci-resolve
description: "Drive DaVinci Resolve on a Resolve machine (SSH alias `resolve-host`) through the davinci-resolve MCP: get an uploaded video onto it, edit it, render it to ~/output there."
version: 1.3.1
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, davinci, resolve, mcp, render]
---

# DaVinci Resolve (via MCP)

> **Deployment-specific.** Paths and the SSH alias of the Resolve machine (written `resolve-host` here: the `Host` entry that `start_hermes.sh`
> put in `~/.ssh/config`) are one operator's own setup. Adapt or delete for your deployment.

Follow the recipe below instead of exploring: the time goes into finding the video, rediscovering render settings, and a last call that hangs.

## When to use

The user asks to edit/flip/trim/colour/render a video "in DaVinci" or
"con Resolve". For plain ffmpeg jobs that don't need Resolve, use the
`video-processing` skill instead. Titles, lower thirds, animated text, overlays and
effects go to the `effectcraft` skill (same host, CPU only, and it
works while the home model runs); its "Which tool" table is the routing rule.

## Recipe (do these in order, don't search around)

0. **Check this instance has the tool.** `grep -q '^Host resolve-host' ~/.ssh/config` (not `ssh -G`, which always
   succeeds). With no match, tell the person plainly that DaVinci Resolve is not available on this instance and
   stop; do not try other hosts.
   Then **check the card is free** (see "Limits": no Resolve while a GPU service holds the card on resolve-host).
1. **Find the input.** Telegram uploads land in
   `/root/.hermes/cache/videos/` inside this container. Don't grep the whole
   cache or SSH around looking for it: `ls -t /root/.hermes/cache/videos | head`.
2. **Get it to resolve-host.** Resolve cannot see this container's disk.
   `R=$(ssh resolve-host 'mkdir -p ~/input ~/output && echo $HOME')` gives the remote home (the SSH alias already
   carries user and key), then `scp <file> resolve-host:input/`. Import `$R/input/<file>` (absolute path: Resolve
   does not expand `~`) with `media_pool` / `safe_import_media`.
3. **Use a named project, never the unsaved default.** Check
   `project_manager` for the current project. If it is called `Untitled
   Project ...`, create/load a named one first (e.g. `hermes-work`). An unsaved project raises a save dialog
   that the `-nogui` Resolve cannot show, so the call never returns.
4. **Edit.** Every MCP tool takes `tool(action="<action_name>", params={...})`. All arguments go inside `params`;
   top-level arguments are ignored without an error.
   - Import: `media_pool(action="safe_import_media", params={"paths": ["$R/input/<file>"]})`, which gives the
     clip ID.
   - Timeline: `media_pool(action="create_timeline_from_clips", params={"name": "edit_tl", "clip_ids": ["<clip_id>"]})`,
     or `create_timeline` and then `media_pool(action="append_to_timeline", params={"clip_ids": ["<clip_id>"]})`.
   - Video track: `timeline(action="get_track_count", params={"track_type": "video"})`. If it is 0,
     `timeline(action="add_track", params={"track_type": "video"})`.
   - Change the clip with `timeline_item` (`set_transform`, e.g. `FlipX: true` for a horizontal flip, or color
     properties), and read the value back with `get_transform` before moving on.
   **What works under `-nogui` and what does not** (measured on Resolve 21.2):
   - Works, and can be read back: project load/create, `safe_import_media` (video and audio), timeline from clips,
     `append_to_timeline` with the `clip_infos` form, `add_track`, `set_transform` / `get_transform` (flip, position).
   - Returns success but changes nothing in the output: color properties through `set_property` (Lift, Gamma,
     Gain, Offset, Saturation), `insert_title`, `insert_generator`. Do these in the ffmpeg render instead:
     `eq=brightness=..:contrast=..:saturation=..`, `drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='...':x=10:y=H-30:fontsize=24:fontcolor=white:box=1:boxcolor=0x00000099`.
   - OFX effects can be added by script (Resolve 21.2), through `davinci-native` `run_script`:
     `TimelineItem.AddEffect("ofx", id)` with an id from `Resolve.GetEffectsList("video")` (e.g.
     `"Resolve FX/Resolve FX Film Emulation/Film Grain"`); `GetEffects` / `DeleteEffects` read and remove them.
   - There are no pages without a GUI: the Color page cannot be opened and `GrabStill` does not work. To look at a
     frame or prove an edit, use the `davinci-native` tools: `get_image` (the graded frame as JPEG, up to 1024 px; a
     timecode `HH:MM:SS:FF` can be given; the playhead does not move), `get_thumbnails` (a grid of several frames),
     `describe_grade` (what each node contains), or `Timeline.ExportFrame` through `run_script` (lossless PNG;
     `frameOffset` is 0-based from the timeline start).
   - After 2 failed MCP edit calls, stop trying and replicate the edit in ffmpeg (step 5); say so in the report.
5. **Rendering.** Two ways; the report says which one produced the file.
   - **Resolve's own render (MCP render queue).** It works on the `-nogui` Resolve (output H.264 video + PCM audio). Use it when the edit lives in Resolve (transforms, OFX effects added by
     script) or the person wants Resolve's own render. First create the output folder inside `~/Videos` (the Media Storage root):
     `ssh resolve-host 'mkdir -p ~/Videos/hermes-render'`. Then, with `davinci-resolve`, in this order:
     `resolve_control(action="open_page", params={"page": "deliver"})` (a no-op without pages, but part of the
     verified sequence), `render(action="load_preset", params={"name": "H.264 Master"})`,
     `render(action="set_settings", params={"settings": {"TargetDir": "$R/Videos/hermes-render", "CustomName": "<name>", "SelectAllFrames": true}})`
     (the keys go inside `settings`; a key outside it is ignored without an error), `render(action="add_job")`,
     `render(action="start")`, then poll `render(action="is_rendering")` until it is false. `TargetDir` must be an absolute
     path to a folder that exists and is inside `~/Videos`: a missing folder or one elsewhere raises a "Render Path
     Inaccessible" dialog that nobody can dismiss without a GUI, and the call never returns. Then copy the file:
     `ssh resolve-host 'cp ~/Videos/hermes-render/<name>.* ~/output/'`.
   - **ffmpeg NVENC on resolve-host (fallback).** After a failed Resolve render, or for a plain deliverable when
     the person does not need Resolve's render, replicate the edit in ffmpeg (e.g. flip horizontal = `-vf hflip`):
     `ssh resolve-host 'ffmpeg -y -i ~/input/<file> -vf hflip -c:v h264_nvenc -preset p5 -c:a aac ~/output/<name>.mp4'`
6. **Verify** the file exists in `~/output` on resolve-host and has a video stream
   (`ssh resolve-host ffprobe ...`) before telling the user it is done. Report the
   path, size, duration, and honestly which tool produced the final file
   (Resolve render, or Resolve edit + ffmpeg render).

## Limits and failure handling

- You have TWO Resolve tool sets, both against the same Resolve session `davinci-resolve` (the broad
  compound-tool set: projects, timeline, render, Fusion, colour) and `davinci-native` (the vendor's tools:
  scripting-API search, sandboxed scripts, frame and grade inspection, LUTs). Try `davinci-resolve` first; use
  `davinci-native` to look up an API call, to look at a frame, or when the first one has no tool for it. There is no
  unrestricted-script tool on either: do not look for one.
  Resolve runs with `-nogui` in a private virtual display, shared by both tool sets and independent of any desktop
  session. The first call starts it, so a slow first answer is normal. If a person has their own
  Resolve open on that machine, the MCP refuses to start one and never touches theirs: say so and tell the operator.
- MCP calls time out after 300 s (`davinci-resolve`) or 120 s (`davinci-native`). If one times out, check the Resolve state
  (`resolve_control` / snapshot) once; don't retry the same call more than
  once. Tell the user what is stuck instead of looping.
- A dialog raised by the `-nogui` Resolve cannot be shown, so the call that raised it never returns (e.g. a render
  `TargetDir` that does not exist or is outside `~/Videos`, or saving a project that was never saved). Avoid those
  triggers; if scripting fails everywhere, say so and tell the operator. Don't try to restart Resolve yourself.
- **Resolve and the GPU services of resolve-host do not fit together in its VRAM.** While Resolve runs, the GPU
  gate there refuses to start any GPU service (gateway jobs answer exit 5 `GPU: in use`). Before starting Resolve,
  check the card: `ssh resolve-host "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits"`. If more than
  about 1000 (MiB) is in use, a GPU service is running: do not start Resolve, do the edit with ffmpeg on resolve-host
  (step 5) and tell the person that Resolve is not available right now. Never stop a service yourself.
- Never use an ssh shell to drive Resolve when an MCP action exists (`run_script_unsafe` is hidden and refused).
- Known traps on Resolve 21.2 with these MCP servers:
  - Never use `TimelineItem.RippleDeleteSilence`: under `-nogui` it reports success and deletes the whole audio clip, at
    any threshold. Cut silence with ffmpeg (`silenceremove`) instead.
  - `timeline(action="probe_interchange_roundtrip")` leaves another timeline current when it cleans up: set yours again
    (`timeline(action="set_current", params={"name": "<your timeline>"})`) before editing.
  - Neither import action checks Media Storage: Resolve imports any path it is given. `media_pool(action="import_media")`
    does not check the path at all; `safe_import_media` only rejects a path that does not exist. Import only the files
    you copied to `$R/input`, with `safe_import_media`, as in steps 2 and 4.
- Report elapsed time per phase at the end (find / import / edit / render).

## Scripting API notes

- Render only into a Media Storage root (e.g. `~/Videos`), as in step 5: any other `TargetDir` raises the "Render Path Inaccessible" dialog and the call never returns.
- On Linux the mp4 codecs are `H264_NVIDIA`, `H265_NVIDIA` and `APVYUV422_10`; `"H264"` is not a valid name. Read `GetRenderCodecs("mp4")` instead of guessing.
- `pgrep -x resolve` does not find it (its process name is "GUI Thread"); use `pgrep -f /opt/resolve/bin/resolve`. A second launch just exits. Never `pkill -f` a pattern
  that your own ssh command line also contains.
