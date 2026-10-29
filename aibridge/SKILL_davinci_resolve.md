---
name: davinci-resolve
description: "Drive DaVinci Resolve on the operator's Resolve machine (SSH alias resolve-host) through the davinci-resolve MCP: get an uploaded video onto it, edit it, render it to ~/output there."
version: 1.2.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, davinci, resolve, mcp, render]
---

# DaVinci Resolve (via MCP)

> **Deployment-specific.** Paths and the host name (`resolve-host`) are one
> operator's own setup. Adapt or delete for your deployment.

Written after a real task (horizontal flip of a Telegram video) took ~17 min
and never produced a file: ~2.5 min was spent finding the video, ~11 min was
spent rediscovering render settings, and the last call hung. Follow the
recipe below instead of exploring.

## When to use

The user asks to edit/flip/trim/colour/render a video "in DaVinci" or
"con Resolve". For plain ffmpeg jobs that don't need Resolve, use the
`video-processing` skill instead.

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
   top-level arguments are ignored without an error. (Learned by Hermes on 2026-10-05 and lost when the container
   was recreated; restored here.)
   - Import: `media_pool(action="safe_import_media", params={"file_paths": ["$R/input/<file>"]})`, which gives the
     clip ID.
   - Timeline: `media_pool(action="create_timeline_from_clips", params={"name": "edit_tl", "clip_ids": ["<clip_id>"]})`,
     or `create_timeline` and then `media_pool(action="append_to_timeline", params={"clip_ids": ["<clip_id>"]})`.
   - Video track: `timeline(action="get_track_count", params={"track_type": "video"})`. If it is 0,
     `timeline(action="add_track", params={"track_type": "video"})`.
   - Change the clip with `timeline_item` (`set_transform`, e.g. `FlipX: true` for a horizontal flip, or color
     properties), and read the value back with `get_transform` before moving on.
   **What works headless and what does not** (measured by Hermes on resolve-host, Resolve 21, 2026-10-05/06):
   - Works, and can be read back: project load/create, `safe_import_media` (video and audio), timeline from clips,
     `append_to_timeline` with the `clip_infos` form, `add_track`, `set_transform` / `get_transform` (flip, position).
   - Returns success but changes nothing in the output: color properties through `set_property` (Lift, Gamma,
     Gain, Offset, Saturation), `insert_title`, `insert_generator`. Do these in the ffmpeg render instead:
     `eq=brightness=..:contrast=..:saturation=..`, `drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='...':x=10:y=H-30:fontsize=24:fontcolor=white:box=1:boxcolor=0x00000099`.
   - After 2 failed MCP edit calls, stop trying and replicate the edit in ffmpeg (step 5); say so in the report.
5. **Rendering: do NOT use the MCP render queue on the headless Resolve.**
   Measured 2026-10-02: in `-nogui` mode `LoadRenderPreset` returns False
   (so `from_preset` is useless) and `render` / `prepare_render_job` hangs
   until the MCP timeout. Don't retry it and don't try other presets. The
   edit in Resolve (steps 3-4) is still worth doing/verifying; for the
   deliverable, render with ffmpeg on resolve-host instead, replicating the edit
   (e.g. flip horizontal = `-vf hflip`), NVENC for speed:
   `ssh resolve-host 'ffmpeg -y -i ~/input/<file> -vf hflip -c:v h264_nvenc -preset p5 -c:a aac ~/output/<name>.mp4'`
   A real Resolve render needs a Resolve with a GUI session; say so if the
   user specifically needs Resolve's own render (grain, LUTs, Fusion, ...).
6. **Verify** the file exists in `~/output` on resolve-host and has a video stream
   (`ssh resolve-host ffprobe ...`) before telling the user it is done. Report the
   path, size, duration, and honestly which tool produced the final file
   (Resolve edit + ffmpeg render).

## Limits and failure handling

- MCP calls time out after 60 s. If one times out, check the Resolve state
  (`resolve_control` / snapshot) once; don't retry the same call more than
  once. Tell the user what is stuck instead of looping.
- Resolve dies with its graphical session: if scripting fails everywhere
  right after the operator used the machine for VR/GPU work, say so and ask
  the operator to restart headless Resolve. Don't try to restart it
  yourself.
- **resolve-host is also a GPU host for the home model, and the two do not fit together in its 8 GB of VRAM.**
  Operator rule (2026-10-09): **never start or use Resolve there while the home model is up.** Check first:
  `ssh resolve-host 'curl -s -m3 localhost:8630/health'`. If it answers `ok`, do not touch Resolve: do the edit with
  ffmpeg on resolve-host (step 5, NVENC is fine) and tell the person that Resolve is not available right now because
  that machine is serving the home model. Do not stop the model yourself. Only when it does not answer, go ahead
  with Resolve.
- Never use `run_script_unsafe` or an ssh shell to drive Resolve when an
  MCP action exists.
- Report elapsed time per phase at the end (find / import / edit / render):
  the operator is measuring this to optimise it.

## Scripting API with a GUI session (measured 2026-10-28, Resolve Studio 21.1.1, Python API)

Found while benchmarking Resolve's AI tools from a script, with Resolve open in the desktop session:

- **Rendering works with a GUI**, but only into a Media Storage root (Preferences > Media Storage; on resolve-host
  `~/Videos` and `/mnt/videos`). Any other `TargetDir` pops a modal "Render Path Inaccessible" dialog, and
  every later call (even `CreateProject`) fails or hangs until someone clicks OK.
- On Linux the mp4 codecs are `H264_NVIDIA`, `H265_NVIDIA` and `APVYUV422_10`; `"H264"` is not a valid name.
  Read `GetRenderCodecs("mp4")` instead of guessing.
- **Super Scale set from the API may not engage the AI upscaler.** Set in the GUI (Clip Attributes) it does: 1080p to
  3840x2160, 245 frames, 27 s with the GPU at 100% vs 2.6 s without. Set with `SetClipProperty("Super Scale", 2)`
  (readback 2, same NR/sharpness 0.5) it rendered in 3.4 s on one clip and 6.0 s on another (vs 2.9 s plain, output
  only slightly different, PSNR 51 dB), twice in a row. Check the render time or the GPU, not just the readback.
- **Magic Mask tracks from the API once a point exists.** With no point, `CreateMagicMask("F"|"B"|"BI")` and
  `RegenerateMagicMask()` return False at once. After one click on the subject in the viewer with the Magic Mask
  palette open on that node (the palette must say "Click 1", not "No Mask"), `CreateMagicMask("BI")` returned True
  and blocked while tracking: 240 frames of 1080p in 21.4 s, GPU 98%, ~185 W (3060 Ti, unlocked, 200 W cap). A repeat
  call returns True at once (already tracked); `RegenerateMagicMask()` still returned False. The API acts on the
  selected node, and there is no API to select a node or to place the point.
- **Magic Mask tracking processes every node upstream for each frame.** With Temporal Noise Reduction in node 1 and
  Super Scale on the clip, the same 240-frame track took 352 s instead of 18.5 s. Disable heavy upstream nodes and
  Super Scale while tracking. A track already done is not redone: delete the point (trash icon next to "Click 1")
  and click again. While a track runs, other API calls return None.
- A 3D Keyer stroke is not a Magic Mask stroke: both are drawn in the viewer, but the keyer's picker leaves the
  Magic Mask palette at "No Mask".
- **Keys and masks change nothing without a correction in the same node.** A node with only a 3D Keyer and a Magic
  Mask rendered bit-identical to the node off (PSNR inf), though it cost the GPU (+0.6 to +1.8 s on 240 frames, GPU
  100%). `TimelineItem.SetCDL({"NodeIndex": "2", ...})` adds a correction from the API; if the combined key is empty
  (check with Highlight, Shift+H) the output still does not change. Compare outputs with
  `ffmpeg -i a.mp4 -i b.mp4 -lavfi psnr -f null -`; file size is no proof, NVENC sizes repeat across different grades.
- **Smart Reframe** returns True in 0.05 s and changes nothing visible; it also needs the timeline aspect changed,
  and changing it is a project setting, so put it back afterwards.
- **Face Refinement** (OFX on a node) needs a human face and its Analyze step run in the GUI. With default sliders it
  renders bit-identical to the node off, even analyzed, on a face clip (+0 to +0.2 s on 240 frames); without faces
  it costs +0.26 s. A slider has to move before it does anything, and OFX parameters cannot be set from the API.
- `GetToolsInNode()` lists Magic Mask as "AI Magic Mask" once it has a point, and OFX tools as "OFX: <name>".
- The Color page can be inspected from a shell with `import -window <id>` (ImageMagick, `DISPLAY=:0` and the
  mutter Xwayland auth file); a root-window grab is black under Wayland. `xdotool search --pid` gives the ids.
- **8 GB of VRAM is the wall, not compute.** Super Scale 2x (1080p to 3840x2160) plus Noise Reduction plus the Beauty
  OFX on a 3060 Ti 8 GB: Resolve alone held 7.2 GB at idle after a few renders; `ResolveDebug.txt` filled with
  `cudaMalloc failed` (a 3232 MiB request for Super Scale) and H.264/H.265 NVIDIA renders failed with
  `nvEncInitializeEncoder ... return: 10` (NV_ENC_ERR_OUT_OF_MEMORY), "Cannot find appropriate codec" or "Failed to
  encode the video frame". The same jobs rendered to `mov`/`ProRes422` with no error: NVENC needs VRAM of its own.
  Noise Reduction after Super Scale works on 4K frames and dominates: 24 frames at 0.63 fps (100 W cap), 1.58 fps
  (200 W), 1.38 fps (250 W); Super Scale alone 4.5 / 7.1 / 7.7 fps; Super Scale + Beauty 1.7 / 2.7 / 2.9 fps.
  Above 200 W nothing improves (memory bound). On that chain a restart did not help: a fresh instance (1.8 GB) reached
  7.35 GB in its first such render and gave the same rates (0.67 / 1.18 / 1.17 fps for all three effects), and
  H.264 NVIDIA still failed 1 of 4 jobs at 200 W.
- **A long session can get much slower, though** (2026-10-29, 4K DNG, Super Scale 2x + Noise Reduction + Relight,
  48 frames to ProRes, 200 W): 626 s in a Resolve open for hours with many renders, 389 s in a fresh one; NR alone
  50 vs 23 s, Relight 148 vs 73 s, GPU 51 to 78% busy vs 89 to 99%. Restart Resolve before a long final render, and
  benchmark only fresh instances, one render each (`~/imggen/resolve_fresh.sh`). Even fresh, a second render of that
  chain in a row failed with "GPU memory full".
- **Super Scale runs even on a 1080p timeline** (upscale, then back down): no nodes, 4.7 fps at 100 W. With the
  timeline at 1920x1080 *and* Super Scale off, the same NR + Beauty grade ran 3.6 fps (100 W) / 6.0 fps (200 W)
  vs 0.67 / 1.18 at 4K with Super Scale, using 3.7 GB instead of 7.8. NR alone 4.8 / 8.4 fps, Beauty alone ~14 fps.
  Edit like that; for the final, render the graded 1080p to ProRes, then Super Scale that file in a 4K timeline.
- Confirmed: `SetClipProperty("Super Scale", 2)` from the API reads back 2 but renders at 34 fps with ~150 W (the
  AI path set in the GUI does 7.8 fps at 200 W). Setting it to 1 (off) from the API does work.
- `pgrep -x resolve` does not find it (its process name is "GUI Thread"); use `pgrep -f /opt/resolve/bin/resolve`.
  A second launch just exits. Never `pkill -f` a pattern that your own ssh command line also contains.
- A "Software Update" dialog may sit on screen. In one session it did not block scripting; after a fresh launch it
  did, once the first render finished: every call returned None (`GetCurrentPage()`, `DeleteAllRenderJobs()`,
  `AddRenderJob()`) until Skip was pressed. Leave Skip/Download to the operator.
