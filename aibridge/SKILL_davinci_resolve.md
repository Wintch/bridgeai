---
name: davinci-resolve
description: "Drive DaVinci Resolve on a Resolve machine (SSH alias `resolve-host`) through the davinci-resolve MCP: get an uploaded video onto it, edit it, render it to ~/output there."
version: 1.2.0
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
effects go to the `effectcraft` skill (same host, no GUI session needed, and it
works while the home model runs); its "Which tool" table is the routing rule.

## Recipe (do these in order, don't search around)

0. **Check this instance has the tool.** `grep -q '^Host resolve-host' ~/.ssh/config` (not `ssh -G`, which always
   succeeds). With no match, tell the person plainly that DaVinci Resolve is not available on this instance and
   stop; do not try other hosts.
   Then **check the GPU is free** (see "Limits": no Resolve while the home model runs on resolve-host).
1. **Find the input.** Telegram uploads land in
   `/root/.hermes/cache/videos/` inside this container. Don't grep the whole
   cache or SSH around looking for it: `ls -t /root/.hermes/cache/videos | head`.
2. **Get it to resolve-host.** Resolve cannot see this container's disk.
   `R=$(ssh resolve-host 'mkdir -p ~/input ~/output && echo $HOME')` gives the remote home (the SSH alias already
   carries user and key), then `scp <file> resolve-host:input/`. Import `$R/input/<file>` (absolute path: Resolve
   does not expand `~`) with `media_pool` / `safe_import_media`.
3. **Use a named project, never the unsaved default.** Check
   `project_manager` for the current project. If it is called `Untitled
   Project ...`, create/load a named one first (e.g. `hermes-work`). An
   unsaved project can block render-queue calls in headless mode.
4. **Edit.** Every MCP tool takes `tool(action="<action_name>", params={...})`. All arguments go inside `params`;
   top-level arguments are ignored without an error.
   - Import: `media_pool(action="safe_import_media", params={"file_paths": ["$R/input/<file>"]})`, which gives the
     clip ID.
   - Timeline: `media_pool(action="create_timeline_from_clips", params={"name": "edit_tl", "clip_ids": ["<clip_id>"]})`,
     or `create_timeline` and then `media_pool(action="append_to_timeline", params={"clip_ids": ["<clip_id>"]})`.
   - Video track: `timeline(action="get_track_count", params={"track_type": "video"})`. If it is 0,
     `timeline(action="add_track", params={"track_type": "video"})`.
   - Change the clip with `timeline_item` (`set_transform`, e.g. `FlipX: true` for a horizontal flip, or color
     properties), and read the value back with `get_transform` before moving on.
   **What works headless and what does not** (measured on Resolve 21):
   - Works, and can be read back: project load/create, `safe_import_media` (video and audio), timeline from clips,
     `append_to_timeline` with the `clip_infos` form, `add_track`, `set_transform` / `get_transform` (flip, position).
   - Returns success but changes nothing in the output: color properties through `set_property` (Lift, Gamma,
     Gain, Offset, Saturation), `insert_title`, `insert_generator`. Do these in the ffmpeg render instead:
     `eq=brightness=..:contrast=..:saturation=..`, `drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='...':x=10:y=H-30:fontsize=24:fontcolor=white:box=1:boxcolor=0x00000099`.
   - After 2 failed MCP edit calls, stop trying and replicate the edit in ffmpeg (step 5); say so in the report.
5. **Rendering: do NOT use the MCP render queue on the headless Resolve.**
   In `-nogui` mode `LoadRenderPreset` returns False
   (so `from_preset` is useless) and `render` / `prepare_render_job` hangs
   until the MCP timeout. Don't retry it and don't try other presets. The
   edit in Resolve (steps 3-4) is still worth doing/verifying; for the
   deliverable, render with ffmpeg on resolve-host instead, replicating the edit
   (e.g. flip horizontal = `-vf hflip`), NVENC for speed:
   `ssh resolve-host 'ffmpeg -y -i ~/input/<file> -vf hflip -c:v h264_nvenc -preset p5 -c:a aac ~/output/<name>.mp4'`
   A real Resolve render needs a Resolve with a GUI session; say so if the
   user specifically needs Resolve's own render (grain, LUTs, Fusion, ...).
   **The MCP runs Resolve WITH a GUI inside a private virtual
   display** (`mcp_dispatch.sh` backend `xvfb`), where the render queue works
   (`LoadRenderPreset` True; 64 s of 1080p in about 5 s). Use it only when the
   person needs Resolve's own render: `open_page deliver` first, then
   `render load_preset` / `set_settings` / `add_job` / `start`, with `TargetDir`
   inside `~/Videos` (the Media Storage root; any other folder pops a modal
   that blocks every call), then copy the file to `~/output`. The first calls
   right after the page change can fail once: retry once, and if every call
   returns `success: false` tell the operator (a modal such as "Your GPU memory
   is full" is open in the virtual display). Not verified through Hermes yet:
   for an ordinary deliverable keep using ffmpeg.
6. **Verify** the file exists in `~/output` on resolve-host and has a video stream
   (`ssh resolve-host ffprobe ...`) before telling the user it is done. Report the
   path, size, duration, and honestly which tool produced the final file
   (Resolve edit + ffmpeg render).

## Limits and failure handling

- You have TWO Resolve tool sets, both against the same Resolve session `davinci-resolve` (37 compound
  tools, the broad one: projects, timeline, render, Fusion, colour) and `davinci-native` (the vendor's 13 tools,
  scripting-API search and sandboxed scripts). Try `davinci-resolve` first; use `davinci-native` to look up an API call
  or when the first one has no tool for it. There is no unrestricted-script tool on either: do not look for one.
  The first call of a session starts Resolve (about 10 s), so a slow first answer is normal.
- MCP calls time out after 300 s (`davinci-resolve`) or 120 s (`davinci-native`). If one times out, check the Resolve state
  (`resolve_control` / snapshot) once; don't retry the same call more than
  once. Tell the user what is stuck instead of looping.
- Resolve dies with its graphical session: if scripting fails everywhere
  right after the machine was used for other GPU work, say so and ask
  the operator to restart headless Resolve. Don't try to restart it
  yourself.
- **resolve-host is also a GPU host for the home model, and the two do not fit together in its VRAM.**
  Rule: **never start or use Resolve there while the home model is up.** Check first:
  `ssh resolve-host 'curl -s -m3 localhost:8630/health'`. If it answers `ok`, do not touch Resolve: do the edit with
  ffmpeg on resolve-host (step 5, NVENC is fine) and tell the person that Resolve is not available right now because
  that machine is serving the home model. Do not stop the model yourself. Only when it does not answer, go ahead
  with Resolve.
- Never use `run_script_unsafe` or an ssh shell to drive Resolve when an
  MCP action exists.
- Report elapsed time per phase at the end (find / import / edit / render).

## Scripting API with a GUI session (rules learned from benchmarking)

- **Rendering works with a GUI**, but only into a Media Storage root (Preferences > Media Storage, e.g. `~/Videos`). Any other `TargetDir` pops a modal
  "Render Path Inaccessible" dialog, and every later call (even `CreateProject`) fails or hangs until someone clicks OK.
- On Linux the mp4 codecs are `H264_NVIDIA`, `H265_NVIDIA` and `APVYUV422_10`; `"H264"` is not a valid name. Read `GetRenderCodecs("mp4")` instead of guessing.
- **Super Scale set from the API may not engage the AI upscaler.** Set in the GUI (Clip Attributes) it does; set with `SetClipProperty("Super Scale", 2)` it reads
  back 2 but renders in about the time of no upscale. Check the render time or the GPU, not just the readback. Setting it to 1 (off) from the API does work.
- **Magic Mask tracks from the API only once a point exists.** With no point, `CreateMagicMask` and `RegenerateMagicMask()` return False at once. The point must be
  placed in the viewer by a person; the API acts on the selected node and cannot select a node or place a point. Tracking processes every node upstream for each
  frame, so disable heavy upstream nodes and Super Scale while tracking; a track already done is not redone. While a track runs, other API calls return None.
- A 3D Keyer stroke is not a Magic Mask stroke. **Keys and masks change nothing without a correction in the same node** (`TimelineItem.SetCDL({"NodeIndex": "2", ...})`
  adds one); if the combined key is empty the output does not change. Compare outputs with `ffmpeg -i a.mp4 -i b.mp4 -lavfi psnr -f null -`; file size is no proof.
- **Smart Reframe** returns True and changes nothing visible, and it needs the timeline aspect changed, a project setting you must put back afterwards.
  **Face Refinement** needs a human face and its Analyze step run in the GUI, and OFX parameters cannot be set from the API.
- `GetToolsInNode()` lists Magic Mask as "AI Magic Mask" once it has a point, and OFX tools as "OFX: <name>".
- **VRAM is the wall, not compute.** Super Scale 2x plus Noise Reduction plus an OFX on an 8 GB card exhausts memory: `ResolveDebug.txt` fills with `cudaMalloc failed`
  and H.264/H.265 NVIDIA renders fail with `nvEncInitializeEncoder ... return: 10` (out of memory), "Cannot find appropriate codec" or "Failed to encode the video frame".
  The same jobs render to `mov`/`ProRes422` without error, because NVENC needs VRAM of its own. Noise Reduction after Super Scale works on 4K frames and dominates the time;
  more power above a moderate cap does not help (memory bound).
- **A long session gets much slower.** Restart Resolve before a long final render, and benchmark only fresh instances, one render each. Even fresh, a second render of a heavy
  chain in a row can fail with "GPU memory full".
- **Super Scale runs even on a 1080p timeline** (upscale, then back down). Edit at 1920x1080 with Super Scale off; for the final, render the graded 1080p to ProRes, then
  Super Scale that file in a 4K timeline.
- `pgrep -x resolve` does not find it (its process name is "GUI Thread"); use `pgrep -f /opt/resolve/bin/resolve`. A second launch just exits. Never `pkill -f` a pattern
  that your own ssh command line also contains.
- A "Software Update" dialog may sit on screen and, after a fresh launch, block every call (they return None) until Skip is pressed. Leave Skip/Download to the operator.
- The Color page can be inspected from a shell with `import -window <id>` (ImageMagick, with the display's Xwayland auth file); a root-window grab is black under Wayland.
