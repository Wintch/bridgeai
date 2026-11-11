# Video tools for the bots

What a person can ask their Hermes to do with a video, which tool does it, and how we check that it went well. The skills are the source of truth for
the bot's behaviour: `SKILL_video_processing.md`, `SKILL_gpu_transcode.md`, `SKILL_effectcraft.md` (its "Which tool" table is the routing rule),
`SKILL_davinci_resolve.md`, `SKILL_video_understanding.md`. Which stack has which tool is set in the operator's private config.

## Tools

| Tool | Good for | Runs on |
|---|---|---|
| ffmpeg | cut, join, flip, crop, re-encode, shrink, speed, colour, plain or sliding text | the bot's own container (CPU) |
| GPU encoding (`gateway transcode`) | the same re-encodes, about 4x faster; AV1 for smaller files | a GPU host (NVENC; AV1 on its CPU) |
| EffectCraft | animated titles, lower thirds, keyframed motion, glow/blur/shadow, keying, compositing | the Resolve machine, headless MCP, CPU render |
| DaVinci Resolve | grading, Resolve's AI tools (Super Scale, Magic Mask, Noise Reduction, Relight), camera RAW | the Resolve machine, needs a GUI session (a private Xvfb) |
| Video understanding (`gateway video`) | "what does this video show / say" | frames plus a transcript, sent to the vision model by the gateway |

EffectCraft (github.com/storytold/effectcraft) is an open-source, After Effects-style compositor written in Rust, alpha, released every few days. It has no ML
runtime and composites on Vulkan or the CPU. It runs only through the forced command of an MCP-only SSH key (`mcp_dispatch.sh`), confined to `~/input` (read)
and `~/output` (read and write); scripts and any other path are refused.

## How to ask

The bot picks the tool from the request. Naming a tool makes it use that one; if it is not available it says why and offers the others instead of
switching silently. Examples (people write in their own language): "which video tools do you have?" lists each tool with its state right now; "add the title
'Happy birthday' sliding in from below, with a shadow" goes to EffectCraft (ffmpeg when EffectCraft is not available); "cut from second 10 to 25 and shrink it
for WhatsApp" goes to ffmpeg or GPU encoding; "with Resolve, flip the video" goes to Resolve when available; "what does this video say?" goes to video
understanding. The bot always says which tool made the file.

## Checking how it went

- `VM=<user>@<docker-host> aibridge/ops/stack_usage.sh [hours]` per stack: each turn answered or not, seconds, tool steps, reply length, tool counts, models,
  router decisions. It never prints message text.
- On the Resolve machine: `ls -lt ~/input ~/output` (EffectCraft's files) and `pgrep -fa 'effectcraft-cli mcp'` (one server per awake bot).
- What "good" looks like: a title request answered in under a minute, under about 8 tool steps, the right tool named, and the output file in `~/output`.

## Ideas, in order

1. **Templates for the common asks** (title card, lower third, subtitle line, corner logo) as EffectCraft templates rendered with `--template ... --values`: one
   call instead of 10-20 steps and the same look every time.
2. **EffectCraft for more stacks** needs a separate key whose forced command can only start EffectCraft, per-person input and output folders passed as the
   confinement roots, and a way to move files without a full-shell key (a dispatcher `put`/`get` mode with a size cap).
3. **Cleanup:** the skill deletes its own input and output after delivery; a daily job removes anything older than 24 h.
4. **Upgrades on purpose:** unpack a new EffectCraft release next to the old one, run the MCP checks (import, text, keyframes, effect, render, confinement),
   then move the `current` symlink.
5. **Fewer steps on the ffmpeg path:** ship tested filter recipes (sliding text, fade, logo overlay, burned subtitles) in `SKILL_video_processing.md`.

## The two DaVinci Resolve MCP servers, and Resolve inside Xvfb

Two MCP servers drive the same Resolve through its scripting API; neither starts Resolve for you unless asked:

| | Vendor (native) | Community |
|---|---|---|
| What | `/opt/resolve/bin/ResolveMCP`, shipped with Resolve 21 | `samuelgursky/davinci-resolve-mcp`, in a venv on the Resolve machine |
| Style | 14 tools, one of which runs your own script against the API | 37 compound tools with typed `action=` values: no code to write |
| Headless | none of its own (`launch_resolve` starts the GUI) | a wrapper boots `-nogui` |
| In Hermes | through `ops/resolve_host/mcp_filter.py`: `run_script_unsafe` removed (a shell behind the MCP-only key); `run_script` stays (its sandbox refuses `os`, files, network, processes) | through `mcp_dispatch.sh` (any command but the forced one is refused) |

**Both answer against a Resolve running with a GUI inside a virtual display** (`Xvfb :99 -screen 0 1920x1080x24 +extension GLX +render -noreset`, then
`DISPLAY=:99 /opt/resolve/bin/resolve`, no `-nogui`). In that Resolve the render queue works (`LoadRenderPreset` returns True; it is False under `-nogui`), so
"render hangs headless" is a `-nogui` limit, not the MCP's. The session is shared and counted: the first server in starts Xvfb and Resolve, the others reuse
them, and the last one out quits Resolve and stops the display (`ops/resolve_host/resolve_xvfb_stdio.py` does this; it refuses a Resolve on another display,
which is a person's own session).

One trap: a modal **"Your GPU memory is full"** in the virtual display blocks the API (calls return `None`). It appears while other GPU containers hold memory;
stop them and click OK on the display. Look at the display with `ffmpeg -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 shot.png` when an API call
returns `None`.

Image and video generation are documented in `GPU_MEDIA_TOOLS.md`.
