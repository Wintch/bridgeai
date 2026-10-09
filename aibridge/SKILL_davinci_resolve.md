---
name: davinci-resolve
description: "Drive DaVinci Resolve on the operator's Resolve machine (SSH alias resolve-host) through the davinci-resolve MCP: get an uploaded video onto it, edit it, render it to ~/output there."
version: 1.0.0
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
- Never use `run_script_unsafe` or an ssh shell to drive Resolve when an
  MCP action exists.
- Report elapsed time per phase at the end (find / import / edit / render):
  the operator is measuring this to optimise it.
