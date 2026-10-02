---
name: davinci-resolve
description: "Drive DaVinci Resolve on the operator's iashur host through the davinci-resolve MCP: get an uploaded video onto iashur, edit it, render it to /home/iam/output."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, davinci, resolve, mcp, render]
---

# DaVinci Resolve (via MCP)

> **Deployment-specific.** Paths and the host name (`iashur`) are one
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
2. **Get it to iashur.** Resolve cannot see this container's disk.
   `scp -i /root/.ssh-hermes/id_ed25519_iashur <file> iam@iashur:/home/iam/input/`
   (create the directory once with ssh `mkdir -p`). Then import
   `/home/iam/input/<file>` with `media_pool` / `safe_import_media`.
3. **Use a named project, never the unsaved default.** Check
   `project_manager` for the current project. If it is called `Untitled
   Project ...`, create/load a named one first (e.g. `hermes-work`). An
   unsaved project can block render-queue calls in headless mode.
4. **Edit.** Create the timeline from the clip, then change it with
   `timeline_item` (`set_transform`, e.g. `FlipX: true` for a horizontal
   flip), and read the value back with `get_transform` before moving on.
5. **Queue the render in ONE call** with `render` / `prepare_render_job`:
   - `target_dir`: `/home/iam/output`
   - `require_temp_target`: `false` (the default refuses anything outside
     the system temp dir, which is what sent the last attempt to `/tmp`)
   - `from_preset`: `"TikTok - 720p"` for vertical social video, or another
     name from `render` / `list_presets`. Passing a preset pins the base
     state; without it the job inherits whatever the Deliver page had.
   - `custom_name`: output file name without extension.
   - Don't call `describe_api`, `get_resolutions`, `probe_render_matrix`
     or loop on `validate_render_settings`; one `dry_run: true` first is
     enough if unsure.
6. **Start it:** `render` / `start`. Then poll `render` / `is_rendering`,
   and `get_job_status` for the job id.
7. **Verify** the file exists in `/home/iam/output` and has a video stream
   (`ssh iashur ffprobe ...`) before telling the user it is done. Report the
   path, size and duration.

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
