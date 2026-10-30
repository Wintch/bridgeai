---
name: effectcraft
description: "Motion graphics on a video through the EffectCraft MCP (open-source After Effects-style app) on the operator's Resolve machine: animated titles, lower thirds, overlays, effects, keyframes, then an H.264 render. Also lists which video tools are available right now and picks between EffectCraft, DaVinci Resolve and ffmpeg."
version: 1.2.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, motion-graphics, titles, effectcraft, mcp, render]
---

# EffectCraft (via MCP)

> **Deployment-specific.** The host name (`resolve-host`) and paths are one operator's own setup. Adapt or delete for
> your deployment.

EffectCraft (github.com/storytold/effectcraft, alpha, MIT/Apache) is an After Effects-style compositor. Its MCP
server runs headless on resolve-host, needs no GUI session and no GPU (it renders on the CPU), and was measured
2026-10-29: import a 5 s 720p video, add an animated text layer with a drop shadow and render it to H.264 with audio
in about 3 s.

## Which tool

| The person wants | Use |
|---|---|
| Titles, lower thirds, animated text or shapes, overlays, keyframed motion, glow/blur/shadow, keying, compositing | **this skill** |
| Cut, trim, join, flip, re-encode, shrink, speed, plain burned-in text | `video-processing` / `gpu-transcode` (ffmpeg) |
| "In DaVinci" / "con Resolve", color grading with Resolve, Resolve AI tools (Super Scale, Magic Mask, Noise Reduction, Relight), camera RAW | `davinci-resolve`, within its limits (GUI session, no home model running) |

When Resolve is not available (the home model is up, no GUI session, or its MCP fails), titles and effects still go
through this skill; say which tool made the file.

**If the person names a tool, use that one.** If it is not available, say why and offer the others; do not switch
silently.

**"Which video tools do you have?"** (or the request is ambiguous): check, then answer with one line per tool and its
state right now, and let the person pick:
- ffmpeg (cuts, joins, re-encodes, plain text): always available in this container.
- GPU encoding on resolve-host (`gpu-transcode`): `ssh -o ConnectTimeout=3 resolve-host true` succeeds.
- EffectCraft (titles, animation, effects): the host answers and the `effectcraft` MCP tools are listed.
- DaVinci Resolve (grading, Resolve AI tools): the host answers and
  `ssh resolve-host 'curl -s -m3 localhost:8630/health'` does not say `ok` (the home model would not fit next to it).

## Recipe

0. **Check this instance has it:** `grep -q '^Host resolve-host' ~/.ssh/config` and the `effectcraft` MCP tools are
   listed. If not, say EffectCraft is not available here and use ffmpeg instead. **Only through the MCP tools:** never
   start `effectcraft-cli` over the shell key, never write your own MCP client or script for it, never pass other read
   or write roots. The MCP key is what keeps it inside `input/` and `output/`; going around it was the one thing that
   went wrong in the first night of tests (2026-10-29).
1. **Find the input:** `ls -t /root/.hermes/cache/videos | head`.
2. **Copy it over:** `R=$(ssh resolve-host 'mkdir -p ~/input ~/output && echo $HOME')`, then
   `scp <file> resolve-host:input/`. The MCP server only reads `$R/input` and `$R/output` and only writes
   `$R/output`; any other path is refused. Use absolute paths (`$R/input/<file>`).
3. **Build it** (every call returns JSON; layers are referenced by name, id or `"#n"`, times in seconds):
   - `execute_command {"command":"file.import","params":{"paths":["$R/input/<file>"]}}`, then `get_project` for
     the clip's size and duration.
   - `execute_command comp.new {"name":"Main","width":W,"height":H,"frameRate":F,"duration":D}`.
   - `execute_command layer.addItem {"item":"<file name>","time":0}`.
   - Text: `execute_command layer.newText {"text":"...","size":72,"fill":"#ffffff","name":"Title"}`.
   - Motion: `add_keyframe {"layer":"Title","path":"transform/position","keys":[{"time":0,"value":[x,y]},{"time":1,"value":[x,y]}],"interpolation":"easyEase"}`
     (also `transform/opacity`, `transform/scale`).
   - Effects: `list_effects {"filter":"glow"}`, then `add_effect {"layer":"Title","effect":"Drop Shadow","values":{}}`.
   - Unknown command: `list_commands {"filter":"..."}` then `describe_command`. Unknown parameter keys are rejected
     with the accepted list; read it instead of guessing.
4. **Look before rendering:** `render_frame {"time":<s>,"max_side":640,"path":"$R/output/check.png"}` and check the
   image.
5. **Save, then render:** `save_project {"path":"$R/output/<name>.ecproj"}`, then
   `execute_command renderQueue.add {"comp":"Main","format":"h264","output":"$R/output/<name>.mp4"}` and
   `execute_command renderQueue.render {"wait":true}` (blocks until done; `failed` must be 0).
6. **Verify and deliver:** `ssh resolve-host ffprobe -v error -show_entries stream=codec_type,duration -of csv=p=0 output/<name>.mp4`,
   then `scp resolve-host:output/<name>.mp4 /root/.hermes/cache/videos/` and send it. Report what was added, the
   values used, and that EffectCraft rendered it.

## Limits

- Alpha software: if two MCP calls fail on the same step, stop and do it with ffmpeg (`drawtext`, `overlay`), and say so.
- Layer keyframe times are layer time; on a layer that does not start at 0 pass `"timeBase":"comp"`.
- The headless server keeps the project in memory only: save it (step 5) before rendering.
- No `run_script` here (refused by the confinement); use commands.
- MCP tools missing although the host answers: say so ("EffectCraft is off in this instance right now"), do it with
  ffmpeg, and leave the fix to the operator. Do not work around it.
