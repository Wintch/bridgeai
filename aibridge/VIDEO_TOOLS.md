# Video tools for the bots

What a person can ask their Hermes to do with a video, which tool does it, how we check that it went well, and what
to improve next. State as of 2026-11-04 (EffectCraft 0.21.0; Resolve through the virtual display, see the section on the two Resolve MCP servers). The skills are the source of truth for the bot's behaviour:
`SKILL_video_processing.md`, `SKILL_gpu_transcode.md`, `SKILL_effectcraft.md` (its "Which tool" table is the routing
rule), `SKILL_davinci_resolve.md`, `SKILL_video_understanding.md`.

## What exists and who has it

| Tool | Good for | Runs on | hernik | herand, hereug, guests |
|---|---|---|---|---|
| ffmpeg | cut, join, flip, crop, re-encode, shrink, speed, colour, plain or sliding text | the bot's own container (CPU) | yes | yes |
| GPU encoding (`gpu-transcode`) | the same re-encodes, ~4x faster | resolve-host, NVENC | yes, when the host is on | no (no access to the host) |
| EffectCraft | animated titles, lower thirds, keyframed motion, glow/blur/shadow, keying, compositing | resolve-host, headless MCP, CPU render | **yes, since 2026-10-29** | no (see proposal 2) |
| DaVinci Resolve | grading, Resolve's AI tools (Super Scale, Magic Mask, Noise Reduction, Relight), camera RAW | resolve-host, needs a GUI session (a private Xvfb since 2026-11-04) | MCP works through `ssh resolve-host-mcp davinci` (37 tools, 9 s cold start, render verified), still disabled in hernik's config | no |
| Video understanding (`gateway video`) | "what does this video show / say" | frames plus a transcript, sent to the vision model by the gateway | yes | yes |

EffectCraft (github.com/storytold/effectcraft) is an open-source, After Effects-style compositor written in Rust,
alpha, with a new release every few days. It has no ML runtime and composites on Vulkan or the CPU, so the GPU
tensor-core unlock does nothing for it. On resolve-host it runs only through `~/bin/mcp_dispatch.sh` (the forced
command of the MCP-only SSH key), confined to `~/input` (read) and `~/output` (read and write); scripts and any other
path are refused. Measured over MCP: a 5 s 720p clip with an animated title and a shadow rendered to H.264 with audio
in about 3 s.

## How to ask

The bot picks the tool from the request. Naming a tool makes it use that one; if it is not available it says why and
offers the others instead of switching silently. Examples (people write in their own language):

- "¿Qué herramientas de video tenés?" lists each tool with its state right now.
- "Poné el título 'Feliz cumple' que entre desde abajo, con sombra" goes to EffectCraft (ffmpeg when EffectCraft is
  not available).
- "Con EffectCraft, un lower third con mi nombre y 'Diseñador' en los primeros 4 segundos" uses EffectCraft.
- "Cortá del segundo 10 al 25 y bajale el peso para WhatsApp" goes to ffmpeg or GPU encoding.
- "Con Resolve, girá el video en horizontal" goes to Resolve when it is available, otherwise it says why.
- "¿Qué dice este video?" goes to video understanding.

The bot always says which tool made the file.

## Checking how it went

- `VM105=<user>@<vm105> aibridge/ops/stack_usage.sh [hours]` per stack: each turn answered or not, seconds, tool
  steps, reply length, tool counts, models, router decisions. Never prints message text.
- On resolve-host: `ls -lt ~/input ~/output` (EffectCraft's files) and `pgrep -fa 'effectcraft-cli mcp'` (one server
  per awake bot).
- What "good" looks like: a title request answered in under a minute, under ~8 tool steps, the right tool named, and
  the output file in `~/output`.

Baseline before EffectCraft (hernik, 2026-10-29, title sliding in from below, done with ffmpeg): 223 s, 20 steps, right
result, but an invented `gateway video` tool call, two runs lost to an unescaped comma and one to a missing `-y`
(the skills now cover all three).

First night with EffectCraft (2026-10-29/30, details in HERMES_ARCHITECTURE.md, "First night of tests"): the
`effectcraft` MCP was disabled at boot by a bug in the reachability check, so the bot made the title by running
EffectCraft over the full-shell key with its own client (right result, ~3 min, but outside the confinement), and
"what does this video show" failed 5 of 10 times because the cloud vision model reasoned until it ran out of tokens.
All three are fixed in the repo (boot check, skill rule, router); deployed on hernik 2026-10-30 (image `8b8bd79d5755`); retest with the same asks.

## Proposed optimizations (in order)

1. **Templates for the common asks.** A title card, a lower third, a subtitle line and a logo in the corner as
   EffectCraft templates (`.ectemplate`, rendered with `--template ... --values`). One call with the text and colours
   instead of 10-20 steps, and the same look every time. Needs a template mode in `mcp_dispatch.sh` or an MCP command
   that renders a template, and a skill table "ask -> template".
2. **EffectCraft for the guests.** Today only hernik has keys to resolve-host. For herand, hereug and guests:
   - a separate key whose forced command can only start EffectCraft (no Resolve, no shell);
   - per-person folders (`~/input/<person>`, `~/output/<person>`) passed by the dispatcher as the confinement roots, so
     nobody can read someone else's files;
   - a way to move files without the full-shell key: a dispatcher `put`/`get` mode with a size cap, or a small upload
     service on the host;
   - a `GUEST_PINHOLES` entry in the firewall for resolve-host:22 (operator, sudo).
3. **Cleanup.** The skill deletes its own input and output on resolve-host after delivery; a daily job removes
   anything older than 24 h from `~/input` and `~/output`.
4. **Resolve on hernik stays disabled** until a headless render works (the MCP render queue hangs without a GUI
   session, and Resolve and the home model do not fit together in 8 GB). If enabled, use the same
   `-o ConnectTimeout=3 -o BatchMode=yes` as EffectCraft so a host that is off does not slow every boot.
5. **EffectCraft upgrades on purpose, not automatically.** Unpack the new release next to the old one, run the MCP
   checks (import, text, keyframes, effect, render, confinement), then move the `current` symlink. Weekly at most.
6. **Measure the GPU render path** (`effectcraft-cli bench --gpu`, `render.backend gpu`) on long 1080p clips; the CPU
   path rendered 50 fps at 720p, so it only matters for long jobs.
7. **Fewer steps on the ffmpeg path.** Ship tested filter recipes (sliding text, fade in/out, logo overlay, burned
   subtitles) in `SKILL_video_processing.md` as the escaping one was, and measure steps per request.

## The two DaVinci Resolve MCP servers, and Resolve inside Xvfb (2026-11-04)

`resolve-host` is the operator's own machine (RTX 3060 Ti 8 GB, Resolve Studio 21.1.1.10). Two MCP servers drive the
same Resolve through its scripting API; neither starts Resolve for you unless asked:

| | Vendor (native) | Community |
|---|---|---|
| What | `/opt/resolve/bin/ResolveMCP`, shipped with Resolve 21 (server `davinci_resolve` 21.1.1) | `samuelgursky/davinci-resolve-mcp` v4.16.0, in `~/resolve-install/davinci-resolve-mcp` (venv, `src/server.py`) |
| Tools | 14: `launch_resolve`, `get_resolve_status`, `get_whats_new`, `get_scripting_api`, `search_scripting_api`, `run_script` (sandboxed Python 3.14), `run_script_unsafe`, `get_scripting_docs`, `list_dctls`, `list_luts`, `update_dctl`, `delete_dctl`, `delete_lut`, `generate_lut` | 37 compound tools with `action=` values (about 720 actions: `project_manager`, `media_pool`, `timeline`, `render`, `edit_engine`, `timeline_ai`, ...); catalog in `~/Documents/resolve-linux/MCP-CAPABILITIES.md` |
| Style | one tool runs your script against the API: flexible, you write the code | one tool per area, typed actions: no code to write |
| Headless | none of its own (`launch_resolve` starts the GUI) | `wrapper.sh headless` (`resolve_headless_stdio.py`) boots `-nogui` |
| Hermes today | `davinci-native` (`ssh resolve-host-mcp davinci-native`), through `ops/resolve_host/mcp_filter.py`: 13 tools, **`run_script_unsafe` removed** because it gives full system access (a shell behind the MCP-only key); `run_script` stays (its sandbox refuses `os`, files, network, processes) | `davinci-resolve` entry (`ssh resolve-host-mcp davinci`), via `mcp_dispatch.sh` (any command but `effectcraft` and `davinci-native`) |

A third, `unofficial-davinci-mcp`, is installed but not wired (HERMES_ARCHITECTURE, evaluation row).

**Both answer against a Resolve running with a GUI inside a virtual display**: `Xvfb :99 -screen 0 1920x1080x24
+extension GLX +render -noreset`, then `DISPLAY=:99 /opt/resolve/bin/resolve` (no `-nogui`). Measured the same day, the
scripting API in that Resolve: `LoadRenderPreset("H.264 Master")` True (it is False under `-nogui`), `SetRenderSettings`,
`AddRenderJob`, `StartRendering` all work, a 64 s 1080p clip rendered to H.264 in 4.2 s on NVENC; `run_script` (vendor)
and `resolve_control get_version` (community) both returned 21.1.1.10. The earlier "render hangs headless" finding is
therefore a `-nogui` limit, not the MCP's.

One trap: a modal **"Your GPU memory is full"** in the virtual display blocks the API (calls return `None`:
`GetCurrentPage()`, `OpenPage`, `SetRenderSettings`, `AddRenderJob`). It appeared while the transcoder and upscaler
containers held about 1.6 GB of the GPU; it went away after stopping them and clicking OK
(`xdotool mousemove 1133 608 click 1` on `:99`). Look at the display with
`ffmpeg -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 shot.png` when an API call returns `None`.

Both servers are meant to be connected at the same time, so the session is shared and counted: the first one in starts
Xvfb and Resolve, the others reuse them, the last one out quits Resolve and stops the display (tested from hernik's
container: both up in 9 s, one leaves, the other keeps answering, nothing left behind).

Done the same day: `~/Documents/resolve-linux/pipelines/mcp-benchmark/resolve_xvfb_stdio.py` (a copy is in
`ops/resolve_host/`) starts Xvfb and Resolve when no session is open, reuses a Resolve already on `:99`, refuses one
on another display (a person's own session), and on SIGTERM/SIGHUP or when the client leaves it Quits Resolve and
stops the Xvfb it started. `resolve_mcp_wrapper.sh xvfb` runs the community server through it and `~/bin/mcp_dispatch.sh`
now defaults to that backend (`RESOLVE_MCP_BACKEND=headless` brings back `-nogui`; backups `*.bak-20261104`). Verified
through the community MCP itself: cold start to first answer 8-10 s, then `project_manager.create`,
`resolve_control.open_page deliver`, `media_pool.import_media`, `folder.get_clips`, `create_timeline_from_clips`,
`render.load_preset`, `set_settings`, `add_job`, `start`: a 64 s 1080p clip rendered to a 147 MB H.264 .mov in 5.3 s.
Not yet through Hermes (`davinci-resolve` is still disabled in hernik's config), and one run in four failed its first
render calls right after the page change (retry fixed it). The vendor MCP answers against the same Resolve
(`run_script` returned the version); it has no launcher of its own here.

## Short text for people (es)

> Con videos puedo: cortar, unir, girar, achicar para WhatsApp, cambiar color y brillo, ponerle textos y títulos
> animados, y contarte qué se ve o qué se dice. Mandame el video y decime qué querés. Si querés una herramienta en
> particular (ffmpeg, EffectCraft o DaVinci Resolve), nombrala; si me preguntás "¿qué herramientas de video tenés?"
> te digo cuáles están disponibles ahora.
