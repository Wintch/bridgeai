# Video tools for the bots

What a person can ask their Hermes to do with a video, which tool does it, how we check that it went well, and what
to improve next. State as of 2026-10-29. The skills are the source of truth for the bot's behaviour:
`SKILL_video_processing.md`, `SKILL_gpu_transcode.md`, `SKILL_effectcraft.md` (its "Which tool" table is the routing
rule), `SKILL_davinci_resolve.md`, `SKILL_video_understanding.md`.

## What exists and who has it

| Tool | Good for | Runs on | hernik | herand, hereug, guests |
|---|---|---|---|---|
| ffmpeg | cut, join, flip, crop, re-encode, shrink, speed, colour, plain or sliding text | the bot's own container (CPU) | yes | yes |
| GPU encoding (`gpu-transcode`) | the same re-encodes, ~4x faster | resolve-host, NVENC | yes, when the host is on | no (no access to the host) |
| EffectCraft | animated titles, lower thirds, keyframed motion, glow/blur/shadow, keying, compositing | resolve-host, headless MCP, CPU render | **yes, since 2026-10-29** | no (see proposal 2) |
| DaVinci Resolve | grading, Resolve's AI tools (Super Scale, Magic Mask, Noise Reduction, Relight), camera RAW | resolve-host, needs its GUI session | MCP present but disabled | no |
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

## Short text for people (es)

> Con videos puedo: cortar, unir, girar, achicar para WhatsApp, cambiar color y brillo, ponerle textos y títulos
> animados, y contarte qué se ve o qué se dice. Mandame el video y decime qué querés. Si querés una herramienta en
> particular (ffmpeg, EffectCraft o DaVinci Resolve), nombrala; si me preguntás "¿qué herramientas de video tenés?"
> te digo cuáles están disponibles ahora.
