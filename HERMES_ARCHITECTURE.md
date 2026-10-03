# Hermes Agent in this project

**Repo is live on GitHub (2026-10-01)**: [`github.com/Wintch/bridgeai`](https://github.com/Wintch/bridgeai),
public, `main` branch, connected via SSH remote. Merged with a
pre-existing MIT `LICENSE` GitHub auto-created on repo creation
(`--allow-unrelated-histories`, no conflicts — `LICENSE` was the only
file in that initial commit). Local branch renamed `master` → `main` to
match.

**Status (2026-10-01): deployed and working.** `hermes` is a real backend
provider in `aibridge`, confirmed end-to-end via `/ask?provider=hermes` →
`/result/<token>.json`. The same running instance is also reachable
directly via Telegram (text + voice), independent of aibridge — two doors
into one container, not two instances.

## Architecture: sesame → aibridge → hermes

`hermes` is a third real backend provider, the same tier as `claude` and
`antigravity` — not a layer above `aibridge`. Callers (sesame, ChatGPT)
only ever speak aibridge's own GET-based queue protocol; they have no way
to talk to Hermes's own OpenAI-compatible API directly, so aibridge stays
the thing in the middle:

```
sesame / chatgpt
   │  GET /ask?provider=hermes&text=...
   ▼
aibridge   (queue/result on filesystem — see README.md)
   │  GET /next?provider=hermes  →  POST /deposit
   ▼
aibridge-hermes-agent   (container)
   │  HTTP: POST http://127.0.0.1:8642/v1/chat/completions
   ▼
hermes gateway run   (Hermes's own messaging-gateway "api_server" platform)
```

`aibridge` itself needed zero changes — it already treats providers as an
open set (see "How to add a new agent" in `README.md`).

## What's deployed

- `aibridge-hermes-agent` container — Dockerfile, responder script,
  compose block, same pattern as `antigravity-agent`.
- Unlike `claude`/`antigravity` (which shell out to a CLI subprocess per
  request), Hermes runs a **persistent HTTP API server**
  (`hermes gateway run`, not `hermes serve` — see below) inside the
  container. The responder talks to it over
  `POST http://127.0.0.1:8642/v1/chat/completions`,
  `Authorization: Bearer <API_SERVER_KEY>`, OpenAI-compatible shape.
- `model`/`effort` from `/ask` are ignored for this provider — Hermes
  manages its own model/provider choice internally.
- One-time manual step: `hermes setup --portal` (OAuth, picks a model
  provider, enables the Tool Gateway) run once inside the container.
- `Dockerfile.hermes-agent` runs the official install script
  (`curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`)
  — any edit to this file has to go through a human paste step, since the
  harness this project runs under blocks writing a `curl | bash` pattern
  directly ("[Code from External]").

## Hermes Agent facts worth knowing

Source: hermes-ai.net, github.com/NousResearch/hermes-agent.

- Built by **Nous Research**. Free, open source, MIT license.
- One agent core across CLI/TUI, a messaging gateway (~20 platforms:
  Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Email, SMS, ...),
  and an Electron desktop app.
- Self-improving: builds skills and a model of the user from experience,
  persistent across sessions — `aibridge` itself intentionally has none
  of this.
- Skills system, compatible with agentskills.io. MCP client support
  (`hermes mcp` can also run Hermes *as* an MCP server). Built-in cron
  (`hermes cron`).
- Config: `~/.hermes/.env` (secrets) + `~/.hermes/config.yaml`
  (everything else).
- **`hermes serve` is NOT the API server** — it's the JSON-RPC/WebSocket
  backend the Electron desktop app talks to (port 9119). The OpenAI-
  compatible API is a messaging-gateway "platform"
  (`gateway/platforms/api_server.py`), read by **`hermes gateway run`**
  ("recommended for WSL and Docker" per its own `--help`) — the command
  `start_hermes.sh` actually runs.
- API server: off by default, `API_SERVER_ENABLED=true` +
  `API_SERVER_KEY=<key>`, listens on `127.0.0.1:8642`.
  - `POST /v1/chat/completions` — the one this project uses.
  - `POST /v1/responses`, `POST /v1/runs` (+ polling/SSE) — richer
    async alternatives, not used here.
  - `POST /api/jobs` — Hermes's own scheduled-job CRUD, separate from
    aibridge's queue, not used here.

## Deploy gotchas

- `node:20-slim` needs `git` (the installer requires it) and `libatomic1`
  (the installer's staged Node runtime won't even run `--version`
  without it).
- **Do not mount a persistence volume at `/root/.hermes`.** Unlike
  Claude Code/Antigravity, Hermes's installer puts the executable
  *inside* `~/.hermes` itself
  (`~/.hermes/hermes-agent/.hermes/bin/hermes`) — mounting an empty host
  dir there erases the binary on container start (`exec: ... not found`
  crash loop). Fix: mount `./hermes-config:/hermes-persist` instead, and
  have `start_hermes.sh` selectively copy a known list of mutable files
  in on boot and back out every 30s (not a blanket sync — that would
  reclobber a newer installed binary with a stale one). See "What's
  persistent" below for the current list.
- Nous's config key is `nous`, not `nous_portal` (`nous_portal` is
  silently accepted by `hermes config set` but fails at call time).
  Confirmed constant: `NOUS_MANAGED_PROVIDER = "nous"`. Non-interactive
  model switch: `hermes config set model.provider nous` +
  `hermes config set model.default "<slug>"`.
- Confirmed free-tier Nous models (from
  `~/.hermes/cache/nous_recommended_cache.json`'s `freeRecommendedModels`):
  `meituan/longcat-2.5-preview:free`, `stealth/space-bunny-alpha` (1M
  context), `inclusionai/ling-3.0-flash-sante:free` (262144 context),
  `poolside/laguna-xs-2.1:free`, `poolside/laguna-s-2.1:free`,
  `stepfun/step-3.7-flash:free`.

## Telegram: a second, independent channel

- Long-polling (Hermes reaches out to Telegram, not the other way) — no
  public port needed.
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USERS` (numeric user ID) in
  `~/.hermes/.env`. Get the numeric ID from the bot's own `getUpdates`
  after messaging it once.
- Voice messages need an STT provider configured — Hermes's default
  cascade is local `faster-whisper` → Groq → OpenAI, none configured by
  default. Fixed with a free `GROQ_API_KEY`.
- `platform_toolsets.telegram` defaults to the `hermes-telegram` preset,
  which already includes `vision` — image messages work without extra
  config.

### File-transfer cap: 20MB → 2GB

Public Telegram Bot API caps file transfer at 20MB. First-party fix,
confirmed from Hermes's own source
(`plugins/platforms/telegram/adapter.py`): `self._max_doc_bytes = 2GB if
extra.get("base_url") else 20MB`. Needs `TELEGRAM_API_ID` /
`TELEGRAM_API_HASH` (from my.telegram.org, a personal-account login step
— not automatable, not from @BotFather).

Three pieces, **all required** — `base_url` alone is not enough:

1. `docker-compose.yml`'s `telegram-bot-api` service
   (`aiogram/telegram-bot-api`, pinned by digest) needs `TELEGRAM_LOCAL: "1"`
   — without `--local`, a self-hosted server enforces the *same*
   20MB/50MB caps as the public API. The image's own
   `/docker-entrypoint.sh` only appends `--local` when `TELEGRAM_LOCAL`
   is set.
2. `start_hermes.sh` sets `platforms.telegram.extra.base_url` **and**
   `platforms.telegram.extra.local_mode: true`. `--local` mode changes
   what `getFile` returns: an absolute path on the server's *own*
   filesystem, not a URL. Confirmed in `python-telegram-bot`'s
   `file.py`: `download_as_bytearray()` reads the path directly off disk
   when it looks local, falls back to an HTTP GET via `base_file_url`
   otherwise. Without `local_mode` set client-side, PTB took the HTTP
   path and hit a malformed URL, surfacing as a misleading
   `telegram.error.InvalidToken: Not Found: method not found` (nothing
   to do with the actual token).
3. `docker-compose.yml` mounts the same `telegram-bot-api-data` volume
   into `hermes-agent` at the identical path `/var/lib/telegram-bot-api`
   (read-only) — `hermes-agent` and `telegram-bot-api` are separate
   containers with separate filesystems, so the absolute path `getFile`
   returns has to resolve on both sides.

Confirmed via `agent.log` (not `docker logs`, which only shows
`WARNING`+): both `Using custom Telegram base_url: ...` and `Using
Telegram local_mode (read files from disk)` fire on boot. **Deployed;
final confirmation from a real user video upload still pending.**

## Skills added

Baked into the image at `/root/.hermes/skills/devops/<name>/SKILL.md` via
`Dockerfile.hermes-agent` `COPY` (a skill name absent from Hermes's own
`.bundled_manifest` is untouched by its curator).

- **`network-diagnostics`** — condensed version of
  [`github.com/Wintch/network_check_guide`](https://github.com/Wintch/network_check_guide)
  (MIT). Diagnose closest-to-home-first (NIC → gateway → LAN → ISP →
  remote). Grants **no SSH/login access** by itself — see "SSH access"
  below for the one explicit exception.
- **`image-upscale`** — calls the GPU upscaling microservice below.
  Confirmed working end-to-end via real Telegram usage.
- **`project-workspace`** — folder convention under `/workdir`, one
  folder per project; see "Project workspaces" below.
- **`audio-transcription`** / **`audio-identify`** — Groq Whisper via
  `curl` for transcription; `fpcalc` + AcoustID for Shazam-style song ID
  (told to say plainly if `ACOUSTID_API_KEY` isn't configured rather
  than guess).

### Official bundled skills enabled (2026-10-01)

Separate from the local skills above: Hermes ships a larger catalog of
**official, bundled-but-not-seeded** skills under
`hermes-agent/optional-skills/<category>/<name>/` — present in the image
but not registered until explicitly restored
(`hermes skills repair-official <name> --restore --yes`, confirmed via
`hermes skills list` before/after: neither showed up in the 58
builtin+local skills already active). Found via a usage audit (below) and
enabled:

- **`page-agent`** (`web-development`) — a repeatable method for
  auditing/optimizing a live website. Enabled because the gap was real:
  earlier the same day, asked to review whether `niko.loadsavedelete.com`
  and `kino.loadsavedelete.com` were "solid/optimized," Hermes had to
  improvise the check ad-hoc with no dedicated skill for it.
- **`mcp-oauth-remote-gateway`** (`mcp`) — ships most of the design
  already sketched under "Planned next step: a resolve-gateway
  aggregator" above (MCP-over-HTTP instead of MCP-over-SSH). Worth
  reading before building that aggregator from scratch — it may cover
  most of the groundwork already.

## Usage audit: tracing a real day of Telegram use (2026-10-01)

Separate from the heavy tool-call activity driving the Resolve pipeline
(documented above): a direct audit of the operator's own Telegram
conversation with Hermes that same day (`docker logs
aibridge-hermes-agent` grepped for Telegram activity, plus direct
`sqlite3` queries against `~/.hermes/state.db`'s `messages` table for
session `20261001_080618_bf76f444`, chat `262501424`), to see what the
operator actually asked for and where Hermes fell short in practice
rather than in theory.

**What happened, in order**: morning conversation (image-upscale
request, a song-ID audio clip, a network check, then review requests for
`niko.loadsavedelete.com` and `kino.loadsavedelete.com` — the gap that
led to enabling `page-agent` above); 09:27 the Resolve/`iashur` work
started; four failed Telegram video/audio uploads (`InvalidToken`)
between 11:10 and 19:25 before the `local_mode` fix (documented earlier)
actually took effect; at 19:46 and 20:14 the operator explicitly asked
for a fire-and-forget pattern for long renders — poll every 5 minutes,
push a Telegram message on completion. Hermes said at 20:40 that it had
wired this via webhooks, but the day ended in the crash-loop/reboot
before any real push was ever observed firing.

**Findings, each grounded in an actual log/DB entry, not a general
impression:**

1. **The long-render push-notification mechanism is unconfirmed.**
   Hermes reported building it; no evidence it has ever actually fired.
   Test with a short render before relying on it for a long one.
2. **Voice-message transcriptions are stored indistinguishable from
   typed text.** Two messages in `state.db` are clearly transcribed
   audio (telltale phrasing) but carry `role=user` with no marker that
   they came from a voice note rather than the keyboard — a model
   reading back history has no way to tell the difference, which matters
   if a transcription is ever imperfect.
3. **6 `gateway.run` interruptions in one day** — some are this
   session's own container rebuilds, but not all are accounted for;
   worth checking whether `hermes gateway run` is crashing on its own
   more than expected.
4. **A real password sent in plaintext over Telegram, persisted in
   `state.db`** — see "Security audit findings" above (same finding,
   fixed there).
5. **Cosmetic message duplication around each context compaction** —
   confirmed benign (nothing lost, compaction re-writes/duplicates
   recent history into its own handoff summary by design), flagged only
   so it isn't mistaken for a delivery bug if ever noticed directly.

## Heavy-tools host: GPU microservices on a LAN desktop

Hermes's own container is RAM-constrained and not meant for heavy
workloads. Pattern: a separate, deliberately simple heavy-tools host on
the LAN — Hermes stays light, skills call out over plain HTTP.

- **Host**: operator's desktop, `192.168.1.144`, NVIDIA GTX 1070 Ti
  (8GB VRAM). Docker GPU access fixed via the standard NVIDIA Container
  Toolkit install.
- **CUDA passthrough: confirmed working. Vulkan: confirmed broken**
  (`vulkaninfo` inside `--gpus all` only shows Mesa's `llvmpipe` CPU
  renderer) — ruled out the NCNN-Vulkan build of Real-ESRGAN in favor of
  PyTorch/CUDA.
- **First service: image upscaling** (`upscaler/`). Real-ESRGAN
  (`xinntao`), `RRDBNet` + `RealESRGANer`, official
  `RealESRGAN_x4plus.pth` weights. 128×128 → 512×512 (4x) in ~0.35s.
  Minimal stdlib `http.server` wrapper (`POST /upscale` raw bytes
  in/out, `GET /healthz`), matching the rest of this repo's small
  services. No auth, LAN-only by design.
- **`basicsr`/`torchvision` break, patched**: `basicsr`'s
  `degradations.py` imports `rgb_to_grayscale` from
  `torchvision.transforms.functional_tensor`, removed in newer
  torchvision. Fixed with a build-time `sed` patch to
  `torchvision.transforms.functional`. The file to patch can't be
  located via `python3 -c "import basicsr"` (that import itself
  triggers the same broken chain) — the Dockerfile hardcodes the known
  path instead.
- **Output format bug, fixed**: upscaled output was a 13MB PNG,
  exceeding Telegram's 10MB photo limit; the adapter's document-fallback
  path hit the same limit again and failed silently (no user-facing
  error). Fixed by encoding output as JPEG (quality 92) instead — safely
  under the limit, visually lossless for this use case. General lesson:
  check real output size against Telegram's media limits for anything a
  GPU service sends back, don't assume a lossless format is safe.
- **Not built**: a second, more elaborate preset beyond plain upscaling
  (scoped, not started).

## DaVinci Resolve MCP: video editing delegation

Same "one machine processes, another one runs the pipeline" pattern as
the upscaler, on `iashur` (`iam@192.168.1.171`, a physical Debian 13
machine — not a Proxmox VM). Reference implementation:
[`github.com/Wintch/resolve-linux`](https://github.com/Wintch/resolve-linux)
(operator's own repo), which pairs official DaVinci Resolve for Linux
with `davinci-resolve-mcp` (wraps Resolve's scripting API — 338 methods
grouped into 37 MCP tools: `project_manager`, `media_pool`, `timeline`,
`color_group`, `render`, etc., each taking an `action` argument).

**Known operational constraints** (from the resolve-linux repo):
≥16GB VRAM for the AI-enhancement modules specifically (core
editing/color/render via the scripting API needs much less); requires an
Xorg/X11 session (GPU detection breaks under Wayland/XWayland);
Blackmagic gates the Linux download behind a free-account login (not
automatable); the official `.run` installer needs `makeresolvedeb` to
become a `.deb` on Debian; hard dependency on `libglu1-mesa`; no
scripting-API method to add an OFX/ResolveFX filter; AAC encode/decode
unsupported on Linux; H.264/H.265 encode needs Studio edition + NVIDIA
GPU, no software fallback.

**Transport**: stdio-only by upstream design — `davinci-resolve-mcp`'s
own README: "a local stdio process launched by your MCP client; it does
not expose a network listener." SSH wraps the stdio pipe as the spawn
command:
```
hermes mcp add davinci-resolve --command ssh --args \
  iashur-mcp "/home/iam/Documents/resolve-linux/pipelines/mcp-benchmark/resolve_mcp_wrapper.sh headless"
```
Enabled via `hermes config set mcp_servers.davinci-resolve.enabled true`
(`hermes mcp configure` is an interactive tool-picker, not scriptable).

**Readiness wrapper**: `scripts/resolve_headless.py` (ships with
resolve-linux) — `status` / `guard` (refuse to start on top of an
existing instance) / `start` (`-nogui`, wait until scriptable) / `stop`
(clean `Quit()`) / `run -- <cmd>` (guard, start, run, stop — but only if
it was the one that started Resolve, so it never tears down a session
someone else has open).

**Two environment fixes needed to actually launch Resolve over SSH**,
both now in the wrapper's `headless` backend
(`resolve-linux`, commits `f6e740b`/`7681eda`, local only, not pushed):

1. An SSH session carries no `DISPLAY`/`XAUTHORITY` — bare
   `resolve_headless.py run --` over SSH crashed Resolve
   (`SIGABRT` in `QApplicationPrivate::init`). Fixed by discovering the
   Wayland auth cookie glob (`.mutter-Xwaylandauth.<random>`, a new
   random suffix every login).
2. Even with that fix, Qt init still aborted with `Invalid
   MIT-MAGIC-COOKIE-1 key` under the rig's Wayland/Xwayland session —
   resolved when the operator switched the desktop session to native
   X11. A native X11 session keeps its own per-session cookie at
   `/tmp/xauth_<random>` — a different location from both the Wayland
   glob and the greeter's own `/run/sddm/xauth_*` (which authenticates
   the login screen, not the user session — must not be used). Added as
   a third fallback in the same wrapper.

**Confirmed working end-to-end through Hermes itself** (not just a
direct SSH test): asked Hermes via its own chat API to use the MCP tool
to list projects — it genuinely called the tool and returned real data.

**Footage transfer is a separate step** — `hermes mcp add`'s `--args`
are static, so they can't carry a per-request source path. Hermes
`scp`/`rsync`s footage over SSH as an explicit step before calling any
Resolve MCP tool (not yet built as a skill — see the planned
`resolve-gateway` design below for where this is headed).

### Hardened SSH access (2026-10-01)

A security audit flagged that the original `iashur` key (see "SSH
access for real infrastructure" below) grants a full interactive shell
as `iam`, not just the ability to run the Resolve wrapper — if the
`hermes-agent` container were ever compromised, that key would allow
arbitrary commands on `iashur`, not just MCP traffic. Live traffic
capture during a real MCP task confirmed Hermes never issues a raw
SSH/terminal command against `iashur` for Resolve work — only
`mcp__davinci_resolve__*` tool calls over the one stdio channel — so a
second, more restricted key costs nothing functionally:

- **New key**, `iashur-mcp` alias, `authorized_keys` forced command:
  `command="/home/iam/Documents/resolve-linux/pipelines/mcp-benchmark/resolve_mcp_wrapper.sh headless",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty,no-user-rc`
  — whatever Hermes's SSH client actually sends is ignored server-side;
  only the wrapper ever runs. Verified live: sending
  `whoami; id; kill -9 1` over this key produced only the wrapper's own
  output.
- `config.yaml`'s `mcp_servers.davinci-resolve` now points at
  `iashur-mcp`, not `iashur`.
- The original `iashur` key stays as-is (full shell, same
  `no-port-forwarding,no-X11-forwarding,no-agent-forwarding` restrictions
  as before) because `SKILL_network_diagnostics.md`'s ping/traceroute/
  etc. exception genuinely needs arbitrary read-only commands and uses
  that alias.
- A third, unexplained key (`hermes@mcp`, no restrictions at all, no
  matching private key found anywhere on VM105 or `iashur`) was found in
  the same audit and removed.

**Incident, same audit**: heavy concurrent MCP testing left 3 orphaned
`server.py` processes on `iashur`, causing new tool calls to hang for
40–90s before timing out. Killing the stale processes triggered
Resolve's own crash-recovery flow, which relaunched it in GUI mode (not
headless) — cleared by killing the resulting `-reportCrash` process and
letting the wrapper relaunch cleanly in `-nogui`. Confirmed fixed via a
real MCP call (13.5s round trip, real project data back).

### Health re-check found a real bug: `restart_app` drops headless mode (2026-10-02)

A re-check (independent of the "confirmed working end-to-end" test above)
found `resolve_headless.py status` reporting `headless: False` — Resolve
running in GUI mode, not the documented `-nogui` design. Process chain
and the hardened `iashur-mcp` key were both otherwise intact, no drift
there. Root-caused, not left as a mystery:

- **Cause**: `ps -o pid,ppid` on the Resolve process showed its parent
  was the MCP server (`server.py`) itself, not a human or a fresh SSH
  session — meaning a `restart_app` MCP tool call had cleanly quit and
  relaunched Resolve. The bug: `restart_resolve_app()` in
  `davinci-resolve-mcp/src/utils/app_control.py` relaunches Resolve on
  Linux with `subprocess.Popen([resolve_path])` — **zero arguments**, no
  `-nogui`. Unlike `resolve_headless.py` (which always launches with
  `-nogui`), this restart path silently drops headless mode every time
  it fires, with no error or warning anywhere. This is a real,
  reproducible bug in `~iam/resolve-install/davinci-resolve-mcp` (a fork
  of `github.com/samuelgursky/davinci-resolve-mcp`), not a one-off.
- **Fix applied**: one-line patch, Linux branch only —
  `subprocess.Popen([resolve_path, '-nogui'])`. Committed locally in the
  vendored clone (`e7bcfd1`, `fix(app-control): restart_resolve_app
  relaunches headless on Linux`). **Not pushed there** — that repo's
  `origin` is the original author's upstream
  (`samuelgursky/davinci-resolve-mcp`), not the operator's own fork, so
  pushing isn't appropriate. Since that vendored copy gets periodically
  refreshed via `git pull --ff-only` (per its own project history), a
  local-only commit there would be at risk of being lost on the next
  update — so the actual source of truth is a tracked patch file in the
  operator's own `resolve-linux` repo instead:
  [`github.com/Wintch/resolve-linux`](https://github.com/Wintch/resolve-linux),
  `pipelines/mcp-benchmark/patches/app_control-headless-restart.patch`,
  with reapply instructions in that pipeline's own `README.md` (2026-10-02
  update there has the full writeup, this doc only summarizes it).
- **Upgraded to v4.8.26 the same day**, patch reapplied via that
  documented procedure (upstream still hasn't fixed it). Re-validated:
  `validate_client.py` passes live in headless mode, and a read-only
  round trip through Hermes and the `iashur-mcp` key reports
  `mcp.version: 4.8.26`. Full verification record in `resolve-linux`.
- **Live instance cycled back to headless** (operator confirmed not in
  use at the time): `resolve_headless.py stop` refused (Resolve wasn't
  answering scripting calls — consistent with 3+ hours of no real MCP
  traffic seen earlier); `--force` reported success but the process was
  still alive (the known unreliable-force-stop issue, caught by always
  verifying with `pgrep`); manual `SIGTERM` → `SIGKILL` was needed, which
  triggered the already-documented `crash_archive.txt` gotcha (next
  launch goes into a blocking `-reportCrash` dialog instead of `-nogui`)
  — moved aside, then a clean `resolve_headless.py start` succeeded.
  Confirmed via `status`: `running: True, headless: True`, responsive.
  The MCP server process itself (`server.py`) never went down through
  any of this — it reconnects to whichever Resolve instance is live, so
  nothing needed restarting on that side.
- **No harm to in-progress work**: this happened right as Hermes reported
  finishing the redone `pipeline_v7` render (720x1280, vertical flip,
  diagnostic overlay, 15.19s, NVENC-encoded). Checked file timestamps on
  the output directly: the finished video and both verification frames
  were written at 19:16-19:17, before any of the stop/kill sequence above
  started — the timing was coincidental, not a collision.

### Resolve MCP goes down whenever iashur leaves its X11 session (2026-10-02)

Headless Resolve (`-nogui`) still binds to the X server it was launched
against. Around 00:19 iashur's graphical session switched from KDE/X11 to
GNOME/Wayland for VR work (Monado, `hello_xr`, a Monado build). Resolve's
process survived and `resolve_headless.py status` kept reporting
`running: True, headless: True`, but `scriptapp("Resolve")` hung — so
Hermes's Resolve MCP is **effectively down until Resolve is restarted
under an X11 session**. Not restarted: the GPU was in use for VR at the
time, and Resolve doesn't run under Wayland on that rig.

Two consequences:
- The still-unapplied X11/Wayland session-switch scripts (see "iashur
  session/power config" above) should also restart headless Resolve
  when switching back to X11, or Hermes silently loses Resolve.
- A real health check needs a scripting round trip with a timeout, not
  `status`. That's also the signal a future `resolve-gateway` (below)
  should use for its "hardware busy" answer: a VR session holding the
  GPU is exactly the case it was designed to report.

Full record in `resolve-linux`'s `pipelines/mcp-benchmark/README.md`.

### First real Resolve task through Hermes, with per-step timings (2026-10-02)

Task sent over Telegram: take a video the operator had sent and flip it
horizontally in DaVinci Resolve via the MCP. Primary model for the turn was
`gpt-6-luna` via `openai-codex` (so the Codex OAuth credential works: it is in
`auth.json`'s `credential_pool`, persisted to `/hermes-persist/auth.json`).
Timings come from `state.db` (`messages.timestamp` deltas, so each number is
"model thinking + tool run" for that step).

| Phase | Wall time | Steps | Notes |
|---|---|---|---|
| Skill + tool discovery (`video-processing`, tool search, load schemas) | ~1 min | 5 | Fine. |
| Locating the input video | ~2.5 min (23:21:35 → 23:23:58) | ~9 | Wasted: it grepped `/root/.hermes/cache` for the file, then SSHed to iashur to look for it. The video was in `cache/videos` inside the container, then had to be copied to iashur. No fixed "where do user uploads land" hint in the skill. |
| Import, timeline, `FlipX` via `set_transform` | ~1.5 min | 6 | The flip itself was applied and read back by 23:25:29, ~5 min into the task. |
| Choosing render settings | ~11 min (23:25:39 → 23:37:06) | ~25 | The real cost. `describe_api`, `list_presets`, `get_resolutions`, `validate_render_settings`, several `prepare_render_job` retries, plus `read_file` on the spillover cache. Typical step 15-37 s (model latency dominates; the MCP calls themselves return in 1-3 s). |
| `prepare_render_job` (final) | hung 286 s | 1 | Never returned; cancelled by an explicit `/stop` from the operator (`MCP call interrupted: user sent a new message`). Resolve itself answered a scripting round trip right afterwards, so this is not the dead-session case above. Suspect: the project is an unsaved `Untitled Project`, and `AddRenderJob` can block on a modal in `-nogui` mode. Not confirmed. |

Totals: 51 model turns, 132 tool turns, ~17 min wall time, **no rendered file**
(`/home/iam/output/..._davinci.mp4` does not exist). Average gap between steps
~14 s; the p90 is ~36 s.

What to optimise, in order of payoff:
1. **Give the skill a render recipe.** Hermes spent half the task rediscovering
   which codec/preset/resolution strings the MCP accepts. A short
   `davinci-resolve` skill with one known-good `prepare_render_job` payload
   (H264_NVIDIA, 720x1280, `/home/iam/output`) would collapse ~25 steps to ~3.
2. **Save the project first.** A named project avoids the unsaved-project
   modal risk and gives renders somewhere to live.
3. **Say where uploads land and how to hand them to iashur** (one `scp` line in
   the skill) instead of letting it search.
4. **Put a timeout on MCP calls** (`mcp_servers.<name>.timeout`) so a hung
   `AddRenderJob` fails in ~30 s instead of 5 minutes.
5. **Persist `cache/videos`.** Telegram-received videos live there and it is not
   in `PERSIST_PATHS`, so a container restart loses them (images are covered).
   A bind-mounted volume is better than the 30 s `cp` loop for large files.

Applied the same day (2026-10-02):
- New baked-in skill `SKILL_davinci_resolve.md` with the recipe. The reason the
  earlier attempts kept landing in `/tmp`: `prepare_render_job` defaults to
  `require_temp_target=true` and refuses any other directory, so the recipe
  passes `require_temp_target: false`, `from_preset: "TikTok - 720p"`, then
  `render/start`. **That render recipe turned out not to work headless and was
  replaced by an ffmpeg fallback (see the `/ask` repeat below).** Installed live
  in the running container and added to `Dockerfile.hermes-agent`.
- `mcp_servers.davinci-resolve.timeout: 60.0` (default was 300 s) in both
  `config.yaml` copies. Takes effect when the gateway restarts.
- `cache/videos` is now a bind mount (`./hermes-videos`, gitignored) instead
  of a `PERSIST_PATHS` entry. Takes effect on the next `docker compose up`.
- Not yet re-measured: re-run the same task and compare with the 17 min /
  51 turn baseline. Whether the unsaved-project modal really caused the hang
  is still unconfirmed.

Measuring going forward: the query that produced the table is a window
function over `messages` (`ts - LAG(ts) OVER (ORDER BY id)`, assistant rows only,
starting at the first message of the task). Re-run it after each change to
compare against the 17 min / 51 turn baseline.

### Talking to Hermes: Telegram vs. aibridge `/ask` vs. the other options (2026-10-02)

Measured with a trivial prompt ("reply only: pong") while Hermes was busy with
a Telegram turn (a Resolve render test).

| | Telegram | aibridge `/ask?provider=hermes` |
|---|---|---|
| Path | Telegram adapter -> gateway -> the long-lived Telegram session | caller -> aibridge queue -> `responder_hermes.py` poller (every 10 s) -> gateway `POST /v1/chat/completions` |
| Session / context | One session that has grown across days (a compaction at 202k tokens took 91 s on Qwen) | A **fresh `api-...` session per request**, no history: 14.9k-token fixed prompt, ~82% served from the provider cache, 1 API call |
| Model | Whatever `/model` last set for that session (it had been switched to `Qwen/Qwen3.8-27B` on HF) | The configured primary (`gemini-3.5-flash-lite`) |
| While Hermes is mid-turn | New messages queue behind the running turn; a hung turn blocks them (a 28-char message sat 4+ min unprocessed) | **Not blocked**: answered while the Telegram session was still working, because it is a separate session |
| Latency | Interactive | Round trips ~11 s (2.4 s of processing, first run) and ~20 s (10.9 s and 9.9 s of processing, Gemini flash-lite taking ~10 s for ~90 output tokens); add up to 10 s of poll delay. Not suitable for chatty use. |
| Cost per call | Grows with context | ~15k input tokens even for "pong", mostly cached |
| Auth | Telegram user allow-list | `AIBRIDGE_KEY` (per caller; identified in the log as e.g. `sesame`) |
| Visibility | `state.db` messages | The `api-...` turn shows in `agent.log` (`Turn ended ... api_calls=1`); result file in `data/results/<token>.md` |

Use `/ask` for scripted, independent tasks and for status probes that must not
wait behind a stuck Telegram turn. It does not share the Telegram session's
context, so "continue what we were doing" does not work there.

Other direct options, **not tested**: `hermes mcp serve` exposes Hermes
conversations as an MCP server (would make Hermes a tool inside Claude Code,
e.g. over stdio via SSH like the Resolve MCP); `hermes acp` runs it as an ACP
server; the gateway's own OpenAI-compatible API on 8642 is only reachable
inside the container (no published port).

**Bug found while testing**: with `AIBRIDGE_PUBLIC_PORTS` unset, compose passes
an empty string, so `PUBLIC_PORTS` became `[]` and `random.choice` raised
`IndexError` inside `_do_ask` **after** the job was already queued. The caller
got an empty reply while the job still ran (so a retry would have duplicated
it). Fixed in `app.py` (empty means the 443,8443 default; `port_hint()`
returns `{}` if still empty). It also means every `/ask` since that
setting was empty returned a connection error to the caller even though the
request worked.

### Repeat of the Resolve task through `/ask`, and what it showed (2026-10-02)

Same task (flip `input_video.mp4` in Resolve via MCP, render with the TikTok
preset), sent through `/ask?provider=hermes` after the skill, timeout and
persistence changes (the timeout change was **not yet active**: no restart).
Run 00:51:32 -> 00:59:10 UTC, session `api-289f...`.

| Step | Time |
|---|---|
| Skill load, tool search, project/timeline checks, flip verified (`FlipX` already set from the Telegram run) | ~20 s (28 turns later; 1.4-3.2 s per model call, tools ~0 s) |
| `render` / `prepare_render_job` (MCP) | **hung exactly 300 s**, `TimeoutError` |
| Diagnosis after the hang (`ps`, `execute_code` blocked, `LoadRenderPreset` -> False) | ~1 min |
| Fallback: ffmpeg NVENC on iashur + `ffprobe` check | ~15 s render |
| Total | ~7.5 min (about 2.5 min without the hang), vs. 17 min and no file on Telegram |

Result: `video_aee164fedeb1_hflip_ask_davinci.mp4` exists, H.264 + AAC,
720x1280, 15.19 s. **It was produced by ffmpeg, not by Resolve**: Hermes
concluded the MCP cannot render headless and said so in its answer. 

Findings:
1. **Rendering through the MCP in `-nogui` Resolve does not work.** Reproduced
   twice: `LoadRenderPreset` returns False and the render call hangs for the
   full tool timeout. This is consistent across a named project
   (`flip_h_720p`) and an unsaved one, so the earlier "unsaved project modal"
   suspicion is not the cause. The edit side (import, timeline, `FlipX`) works.
   Which exact call blocks (format/codec set vs `AddRenderJob`) was not isolated.
   The skill recipe was corrected: edit in Resolve, render with ffmpeg, say so.
2. The fix for point 1 is a Resolve with a GUI session, or an ffmpeg-only
   path; if Resolve-native renders are required, the headless design needs
   revisiting.
3. **The `/ask` poller gives up long before Hermes does**: aibridge returned
   `(error consultando hermes: timed out)` at 00:53 while the turn kept running
   and finished at 00:59. For long tasks the caller must read the file
   afterwards, or the responder timeout must be raised.
4. **Mid-turn model fallback**: Gemini errored (`GeminiAPIError`, 2 retries)
   and the turn finished on `meituan/longcat-2.5-preview:free` (22 calls on
   Gemini, 20 on longcat). The fallback chain worked silently.
5. **Hermes edits its own skills**: after the turn, a background curator
   pass ran `skill_manage` on `davinci-resolve` (first attempt refused, the
   second reported success). The live copy matched the repo version at the time
   of the check, so check the diff before the next rebuild.

### Other Resolve MCP servers, and limiting what Hermes can call (2026-10-02)

Surveyed alternatives to the two servers already in use (native
`ResolveMCP` and `samuelgursky/davinci-resolve-mcp`):
- Hermes's own plugin catalog lists `wassermanproductions/hermes-davinci-resolve-plugin`,
  which is **macOS-only** and runs in-process in Hermes (needs Resolve on
  the same machine as Hermes). Not usable here.
- OpenClaw needs no separate integration: `hermes skills search` already
  queries ClawHub. Its Resolve-related skills don't drive Resolve live.
- `wassermanproductions/unofficial-davinci-mcp` is being evaluated on
  iashur against the `MCP-Benchmark` fixture only, not wired into Hermes:
  code reviewed (no script-execution tool, no telemetry, dry-run/confirm
  on every mutation), 37 tools listed, live tests paused by the session
  issue above. Evaluation record in `resolve-linux`.

**Hermes can restrict which tools of an MCP server it exposes**:
`mcp_servers.<name>.tools.include` / `.exclude` (confirmed in source,
`tools/mcp_tool_registration.py` and `tools/mcp_schema_cache.py`; not yet
exercised). This is the lever for adding the native server safely
(exclude `run_script_unsafe`, full OS access). For the community server
it's coarse: tools are compound (`resolve_control` bundles `quit`,
`restart_app`, `get_version`, ...), so excluding a tool removes all its
actions.

### Planned next step: a resolve-gateway aggregator, taking SSH out of the MCP hot path

**Status: designed, zero implementation.**

Every MCP tool call today still pays for a fresh SSH-wrapped stdio hop,
and there's no explicit "don't touch Resolve right now" signal beyond a
human noticing. Three pieces, all on `iashur`:

1. **`davinci-resolve-mcp`** (existing, untouched).
2. **`hardware_status` check** (new, small — not a separate service,
   just a function the gateway calls first): `resolve_headless.py
   status` (`headless: False` = a human has Resolve open at the
   physical seat right now — the exact signal behind the incident
   above), optionally `nvidia-smi` utilization, optionally a manual
   "do not disturb" marker file.
3. **`resolve-gateway` aggregator** (new) — a persistent process, not
   spawned per-connection. Proxies to `davinci-resolve-mcp` locally (no
   SSH needed for that hop), gates every tool call behind
   `hardware_status` first, exposes the result as ONE MCP endpoint over
   **Streamable HTTP**, not stdio-over-SSH — `hermes mcp add`'s `--url`
   option (HTTP/SSE), not `--command`. Auth: a bearer token, same
   app-level pattern as `HERMES_API_KEY`, bound to the LAN interface
   only.

**Deployment**: `systemd --user` on `iashur`, same pattern as
`fallback_watchdog.py` on VM105 (no `cron`, no sudo needed).
`loginctl enable-linger iam` was run 2026-10-01 (operator's own root
access, a one-time step) so the service survives a host reboot
unattended. Nothing in this design needs root beyond that one command.

**File transfer stays out of the MCP channel** — SSH/rsync is the right
tool for reliable, resumable, checksummed bulk transfer, no reason to
reinvent it inside MCP messages. Two more dedicated, forced-command keys:

- **Upload**: `command="rrsync -wo ~/resolve-inbox/"` (write-only).
- **Download**: `command="rrsync -ro ~/resolve-outbox/"` (read-only),
  separate directory.

**Pipeline**: Hermes `rsync`s footage to `iashur:~/resolve-inbox/<job-id>/`
(upload key) → calls the gateway's MCP tools over HTTP, referencing
`<job-id>` (gateway checks `hardware_status` first, returns "busy"
immediately if unavailable) → import/edit/render writes to
`iashur:~/resolve-outbox/<job-id>/` → Hermes `rsync`s the result back
(download key).

**Not decided**: exact skill/request shape on Hermes's side, which
Python framework serves the HTTP endpoint (`mcp` SDK vs. `FastMCP`, not
evaluated), concurrent-job queuing.

### iashur session/power config: a reboot resets both (found 2026-10-01, fix not yet applied)

A render job silently failed (`AddRenderJob` → `None`, a tool-reported
`database_attached: false`) after heavy concurrent MCP testing left Resolve
in a crash loop (SIGABRT in `QApplicationPrivate::init`, signal 6 — the
same signature as the original Wayland display-auth crash earlier in this
doc). A full reboot of `iashur` cleared the crash loop and confirmed the
database re-attaches fine on a clean boot, but exposed two config gaps
that will keep recurring on every future reboot unless fixed:

- **SDDM autologin is hardcoded to Wayland** (`/etc/sddm.conf`,
  `[Autologin] Session=gnome-wayland.desktop`) — needed for a separate VR
  project that requires Wayland, but it's exactly the display mode that
  crashes Resolve (documented earlier: Wayland's rootless Xwayland hits
  `Invalid MIT-MAGIC-COOKIE-1 key`). Every reboot reverts to the
  Resolve-hostile mode with no prompt. Fix designed, not yet applied —
  two root-run toggle scripts, `/usr/local/sbin/iashur-session-x11.sh`
  and `-wayland.sh`, each `sed`-replacing the `Session=` line in
  `/etc/sddm.conf` and reminding the operator that `systemctl restart
  sddm` is needed to apply it immediately (and that doing so kills
  whatever graphical session is currently active — intentionally a
  manual, deliberate switch, not automatic).
- **CPU governor resets to `powersave`, GNOME power profile to
  `balanced`, on every boot** — previously tuned for Resolve performance,
  lost on reboot since neither is itself persistent (AMD `amd_pstate`
  driver, confirmed via `scaling_governor`; `powerprofilesctl` is a live
  D-Bus setting with no enforced default). NVIDIA persistence mode was
  already correctly persistent (`nvidia-persistenced.service`, enabled) —
  only the CPU/power-profile side needs the fix. Designed, not yet
  applied: `/usr/local/sbin/iashur-performance-mode.sh` (writes
  `performance` to every `scaling_governor`, calls `powerprofilesctl set
  performance`) plus a `oneshot` systemd unit,
  `iashur-performance-mode.service`, `WantedBy=multi-user.target`, so it
  self-applies on every future boot without anyone remembering to.

**Also found during the same incident, already fixed**: a raw Python
script invoked directly over the (non-MCP) `iashur` SSH key — bypassing
the MCP server entirely — was stuck in a blocking `AddRenderJob` call,
monopolizing Resolve's single scripting lock and making every other
caller (the MCP server, `resolve_headless.py stop`, project loads) look
"wedged." Killing it was necessary but not sufficient — the actual
crash loop (above) was a separate, deeper issue underneath it, only
resolved by the reboot. The in-progress edit (`pipeline_final` project,
a `pipeline_v7` timeline at 720x1280 with a vertical flip and a
diagnostic text overlay) did not survive — the project reopened post-reboot
with only its last-saved state (a 1920x1080 `pipeline_final` timeline, no
`pipeline_v7`). Operator's call: redo it rather than recover it, no
further action needed here.

### iashur: a repeating ~1s alert sound, and three wrong diagnoses before the right one (2026-10-01)

While Hermes was mid-work on the Resolve pipeline, a short "tilín" (~100ms
tone) started firing roughly every 1-2 seconds. It took three rounds of
live diagnosis to find the real cause, and every round pointed at
infrastructure first:

1. **Hermes's own read**: DaVinci Resolve opening/closing an audio
   sink-input — wrong. Its 5-sample capture showed the *total* PipeWire
   stream count fluctuate (because the bell's own stream was appearing
   alongside), not Resolve's own stream, which a 10-sample check confirmed
   stable throughout. Its `xset q` also came back "no bell configured"
   (exit 1) — a false negative from missing `DISPLAY`/`XAUTHORITY` over
   SSH, not real evidence.
2. **KWin's X11 system bell**, confirmed genuinely firing (`xset q` with
   the correct `DISPLAY`/`XAUTHORITY` showed `bell percent: 50, pitch:
   400, duration: 100` — exactly a short tilín; live PipeWire captures
   showed a fresh `kwin_x11`/`media.name=bell` sink-input each cycle,
   never the same stream ID twice). This mechanism was real, but the
   trigger behind it (suspected: a stuck/auto-repeating key via KDE's
   `kaccess` accessibility daemon) was never confirmed and turned out not
   to be it.
3. **The `reverb-g2` VR project** (`/home/iam/Documents/reverb-g2`,
   iashur's other resident project — an HP Reverb G2 driver/support repo)
   was suspected next, since it ships a deliberate beep-feedback tool
   (`scripts/reseat_audio.py`, played by `voice-guide.py` and
   `drift-measure.py` during headset cable-reseating/drift-measurement
   procedures). Checked and ruled out directly: neither script was
   running, and the three `reverb-g2` processes that *were* running
   (`vr-power-watchdog.py`, `pmadminka-agent.py`, `status-dashboard.py`)
   don't touch audio and don't match the ~1s cadence. (`pmadminka-agent.py`
   *was* found spamming the journal with a DNS failure every ~5s —
   confirmed real, unrelated to the sound, left as a known issue, not
   fixed.)

**Actual cause**: a Chrome page the operator had built themselves,
configured to auto-open on this machine, ringing the browser/system bell
in a loop. Closing it stopped the sound immediately — confirmed by the
operator directly, no infrastructure change needed anywhere.

**Why this is worth keeping**: the cheapest explanation (a stray
auto-opening browser tab) was checked last, after real time was spent
confirming/refuting Resolve, PipeWire, X11, KDE's accessibility daemon,
and a whole separate project's scripts. Next time a transient alert/noise
shows up on this host, check for an open/auto-launched browser tab
*before* going deep on any of the above.

## Fallback resilience: a second model pool, plus a degradation watchdog

### A correlated outage exposed a single-vendor risk

At 18:38 UTC, Hermes's entire fallback chain failed within ~2 minutes:
the primary (`inclusionai/ling-3.0-flash-sante:free` via Nous) and the
`gemini-3.8-flash` fallback both hit rate limits; of the three remaining
Nous fallbacks, one (`meituan/longcat-2.0:free`) had been silently moved
to paid-only (`404`) while the other two were also rate-limited in the
same window. Hermes gave up (`Rebuilt-message restart limit (3)
exceeded`) with no answer for that turn — self-recovered ~2 minutes
later, no intervention. The correlation itself was never fully
root-caused (3 of 5 were Nous-hosted, the leading guess); flagged open,
not solved.

**Fixes**:

1. Swapped the dead `meituan/longcat-2.0:free` for
   `meituan/longcat-2.5-preview:free`.
2. Added **OpenRouter** as a second, independently-hosted free-model
   pool — `OPENROUTER_API_KEY` wired through `.env.example` →
   `docker-compose.yml` → `start_hermes.sh` (Hermes's plugin source
   expects this exact name, unlike Gemini which maps to
   `GOOGLE_API_KEY`). Three free models added:
   `google/gemma-4-31b-it:free`, `qwen/qwen3.8-27b:free`,
   `nvidia/nemotron-3-super-120b-a12b:free`. Side effect: also unlocks
   Hermes's OpenRouter `image_gen`/`video_gen` plugins. (The account
   itself had to be created by the operator by hand — an AI assistant
   creating third-party accounts is a hard policy line, not a judgment
   call, even on explicit request.)

**Gotcha**: editing `config.yaml` only inside the running container is
not enough — `start_hermes.sh` restores `config.yaml` *from*
`/hermes-persist` on every start, so an edit not copied to **both**
`/root/.hermes/config.yaml` and `/hermes-persist/config.yaml` gets
silently clobbered on the next restart.

### A weak primary model caused a real outage: the repetition-detection incident (2026-10-01)

The primary model had drifted to `inclusionai/ling-3.0-flash-sante:free`
(a free Nous model, not a deliberate choice — likely left over from
earlier fallback testing). While Hermes was driving the Resolve pipeline,
this model got stuck for ~13 minutes (23:11-23:24 UTC) writing broken
Python one-liners against Resolve's scripting API via its raw `terminal`
tool (not the MCP tools) — syntax errors, `NoneType` calls, wrong types —
re-reasoning each time without ever converging. Every response was
~31,000 characters of repeated reasoning, which tripped Hermes's own
anti-repetition guard (`🔁 Response dominated by repeated text — stopping
before delivery`) before any answer reached the user. A second guard also
fired (`Interrupt recursion depth 3 reached`) from repeated manual
interrupts during the stall. 188 tool-turns burned, no usable output.

**Fix**: moved `gemini-3.8-flash` (already in the fallback chain, a far
more capable model) up to primary —
`hermes config set model.default gemini-3.8-flash`.

**Gotcha found applying the fix**: `model.default` (the model name) and
`model.provider` (which backend serves it) are **independent config
keys** — setting only the former left `model.provider: "nous"` in place
from the old primary, so the *same model name* silently resolved through
Nous's catalog (shared free-tier quota, the same correlated-outage risk
from above) instead of the operator's own `GEMINI_API_KEY`. `hermes
fallback list` surfaced it clearly (`Primary: gemini-3.8-flash (via
nous)`) once compared against the fallback chain's own correctly-pinned
entry (`(via gemini)`). Second command needed: `hermes config set
model.provider gemini` — this also auto-cleared a stale `model.base_url`
left pointing at Nous's endpoint. **Takeaway: always verify both the
model name AND the `(via <provider>)` tag together after any primary-model
change, not just that the name matches.**

Promoting `gemini-3.8-flash` to primary left a dead duplicate as fallback
entry #1 (the exact same model+provider that had just failed, retried
pointlessly before moving to a genuinely different vendor) — removed
directly from `fallback_providers` in `config.yaml` (`hermes fallback
remove` has no non-interactive/by-index form, so this was a direct regex
edit, same pattern `fallback_watchdog.py` uses, synced to both config
paths).

**Known limitation, accepted**: Gemini's free-tier API key has no
usage-introspection endpoint (same as Nous) — purely reactive on a 429.
The now-clean fallback chain is the safety net; no proactive monitoring
built for it.

### Hugging Face added as a third fallback vendor (2026-10-01)

`HF_TOKEN` wired through `.env.example` → `docker-compose.yml` →
`start_hermes.sh`, same pattern as `OPENROUTER_API_KEY` (confirmed exact
env var name from `plugins/model-providers/huggingface/__init__.py`'s
`ProviderProfile`). Added `openai/gpt-oss-20b` (via `router.huggingface.co`)
as the last fallback entry.

**Important correction to the original premise**: Hugging Face's
"Inference Providers" catalog is **not a free tier like OpenRouter's**
— queried the full model list (`GET /v1/models` against the router) and
found zero `is_free: true` entries; every model is pay-per-token, routed
to third-party backends (deepinfra, novita, fireworks, etc.). It's
zero-risk here specifically because the operator's HF account has
`canPay: false` (prepaid, no card on file, confirmed via
`/api/whoami-v2`) — a 429/insufficient-credit failure is the worst case,
handled like any other fallback exhaustion, never an actual charge.
Picked `openai/gpt-oss-20b` for being cheap ($0.03/$ input) and a known
model rather than an obscure one.

### OpenAI Codex (ChatGPT OAuth) added as a fifth vendor (2026-10-01)

Direct answer to the earlier open question ("can we add free ChatGPT
models with the operator's own account?") — yes: `provider: openai-codex`
is OAuth-only (`auth_type="oauth_external"`, no API key, confirmed in
`plugins/model-providers/openai-codex/__init__.py`), and the operator ran
the login themselves (as it must be — a real OAuth grant with their own
ChatGPT account is not something to automate on their behalf):
`docker exec -it aibridge-hermes-agent hermes auth add openai-codex`
(device-code flow — prints a URL + short code, approved from any
browser). Confirmed afterward in `hermes auth list`
(`openai-codex-oauth-1`, `oauth`, `device_code`).

Model picked: `gpt-5.3-codex-spark` — found by grepping Hermes's own
source (`agent/auxiliary_client.py`) rather than guessing; comments there
call it out as "Codex-OAuth-only, native 128K" (the `-spark` naming and
OAuth-only gating both point at a fast/light model built specifically
for this route). Added to `fallback_providers` as entry #4, right after
the three `nous` entries and before the pay-per-token ones
(`openrouter`/`huggingface`) — same tier of trust as the other
account-based providers (`nous`, `gemini`), ahead of the ones billed per
token.

Current chain, 9 entries (1 primary + 8 fallback), **5 vendors**:
`gemini` (primary) → `nous` (3) → `openai-codex` (1) → `openrouter` (3)
→ `huggingface` (1).

### Comparing primaries empirically: `gemini-3.5-flash-lite` (2026-10-01)

Querying `GET /v1beta/models` against the Gemini API directly (not
guessing from docs) surfaced several "lite" variants
(`gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`,
`gemini-flash-lite-latest`, etc.) alongside the full `-flash` models —
lite variants are generally faster and carry a materially higher free-
tier daily request cap than their full counterparts. Switched primary
from `gemini-3.8-flash` (hit its 20/day cap within minutes of real use,
see above) to `gemini-3.5-flash-lite` to compare empirically against both
prior primaries (`inclusionai/ling-3.0-flash-sante:free` via Nous, and
`gemini-3.8-flash`) — not yet concluded, monitor `docker logs
aibridge-hermes-agent | grep "Model fallback"` over the following days
for how often it exhausts.

### NVIDIA NIM surveyed as the next vendor to add, not yet added

Researched live (not from training-data memory, which could be stale by
now): `build.nvidia.com`'s NIM API offers a genuine free tier — no credit
card, ~40 requests/minute (the forums mention a path to 200 RPM on
request), 100+ hosted models. The meaningful advantage over every
provider added so far: **the limit resets every 60 seconds** rather than
being a hard daily cap that stays dead until the next day (Gemini's 20/
day) or a credit pool that just runs out (HuggingFace, OpenRouter's
1000/day-once-funded). Natively supported
(`provider: nvidia`, env var `NVIDIA_API_KEY`) — same wiring pattern as
every other API-key provider here. Recommended as the next addition;
blocked on the operator creating their own `build.nvidia.com` account
(hard policy: third-party account creation is the operator's own action)
and generating a key.

**Other providers surveyed, lower priority or not applicable:**
- `copilot` — supported (`GITHUB_TOKEN`), but only useful if the operator
  already holds a qualifying GitHub Copilot entitlement — unconfirmed.
- Mistral — **not** in Hermes's native provider list; would need
  `provider: custom` pointed at Mistral's own (OpenAI-compatible)
  endpoint — more manual, lower priority, not attempted.
- `GROQ_API_KEY` — already configured and working, but it isn't in
  Hermes's chat-model provider list at all; confirmed (via
  `.env.example`'s own comment) it's used for Telegram voice-message
  speech-to-text, a different subsystem — deliberately not added to the
  fallback chain.

### A request to bypass Claude Code's own login was declined (2026-10-01)

The operator asked for a way to let Hermes drive the `claude` CLI
directly on `iashur`, bypassing its normal human-controlled OAuth login,
so Hermes could use it unattended. Declined — not a technical limitation,
a deliberate policy boundary: Claude Code's auth model ties usage to a
human-controlled session, and automating that for an unattended agent
conflicts with Anthropic's intended use. Not something to find a
workaround for, same category as the existing "an AI assistant creating
third-party accounts is a hard policy line" note above (OpenRouter).

Legitimate alternatives, for when Claude models are actually wanted in
the fallback chain: `provider: "anthropic"` with a real
`ANTHROPIC_API_KEY` (pay-as-you-go Claude API, already in Hermes's native
provider list, same wiring pattern as every other API-key provider here)
— **surveyed, not added**, no key configured yet. If Claude-Code-like
agentic capability specifically is wanted (not just the chat model), the
Claude Agent SDK is the sanctioned path for building that — not
explored further, no concrete need yet.

### `fallback_watchdog.py`: a reactive degradation watchdog

[`aibridge/fallback_watchdog.py`](aibridge/fallback_watchdog.py) (own
docstring is authoritative). Rather than let every turn re-discover a
bad-patch provider the hard way, it learns from recent failures and
de-prioritizes automatically:

- Tails `docker logs aibridge-hermes-agent` for the failure lines Hermes
  already prints — no new instrumentation.
- Rolling per-provider failure count in a JSON state file next to the
  script. 2 failures within 15 minutes → that provider's entries move to
  the **end** of `fallback_providers` (never removed). Restored after a
  full 15-minute window with zero failures.
- Validated end-to-end with injected synthetic failure events before
  going live (both reorder and restore confirmed against the real
  container).
- **Deliberately not predictive** — Nous's free pool exposes no
  advance-warning signal before a 429 (confirmed empirically). OpenRouter
  does expose real usage via `hermes usage --provider openrouter`
  (confirmed working); a natural next step would be proactively
  deprioritizing it before its daily free-tier cap (50/day, or 1000/day
  once the account has held $10 of credit) — not built.
- Reordering `fallback_providers` does **not** need a container restart
  — confirmed in source (`hermes_cli/cli_chat_turn_mixin.py`'s
  `_sync_fallback_chain_with_config()` re-reads and re-applies it every
  turn) and verified live. Only new env vars need one.

**Deployment, VM105, user `aibridge`**: no `cron` installed, `aibridge`
has no sudo — runs as a `systemd --user` service instead
(`~/.config/systemd/user/fallback-watchdog.service`, a `while true; run;
sleep 300; done` loop, `Restart=always`). Lingering enabled via `pve3`'s
QEMU guest agent: `qm guest exec 105 -- loginctl enable-linger aibridge`
— runs as root with **no VM105-specific password needed at all**
(confirmed: `qm guest exec 105 -- whoami` → `root`). This is the general
answer for getting root on VM105 going forward.

## Security audit findings (2026-10-01)

A read-only audit of the live deployment (not the repo's own code/config
— that was separately secret-scanned clean) found:

- **Fixed — world-readable `.env` with a live key.** A stale,
  no-longer-synced copy of Hermes's `~/.hermes/.env` sat at
  `/home/aibridge/aibridge/hermes-config/.env`, mode `644`, root-owned,
  on VM105 (a host shared with other tenants). It was orphaned — not in
  `start_hermes.sh`'s `PERSIST_PATHS` list, so nothing read it back —
  deleted rather than just re-permissioned. The live, actually-used
  `~/.hermes/.env` inside the container was already `600`. `umask 077`
  added near the top of `start_hermes.sh` so any future write defaults
  owner-only.
- **Fixed — unexplained, fully unrestricted SSH key** (`hermes@mcp`, no
  forwarding restrictions at all) on `iashur`, no matching private key
  found anywhere — removed. See "Hardened SSH access" above for the
  rest of the SSH-key hardening from this same audit.
- **Accepted, by design**: tirith (the pre-exec command scanner) is
  fail-open — if the binary crashes, times out, or trips its circuit
  breaker, commands proceed unscanned rather than being blocked. This is
  Hermes's own documented default (`tirith_fail_open`), not overridden.
  Confirmed wired into the real approval path (`tools/approval.py` calls
  it before a terminal command executes), zero log hits of it ever
  firing in this deployment.
- **Fixed — a real password landed in plaintext in conversation history.**
  Found during a usage audit (below), not a security scan: the operator
  sent a real SSH password for `iashur` over Telegram mid-conversation
  (2026-10-01, ~09:30), which persisted verbatim in `~/.hermes/state.db`
  — once in the original message, and a second time inside a later
  context-compaction summary (compaction re-writes/duplicates recent
  history into a handoff blob, so a secret present when compaction runs
  can end up copied). Same operator policy as `FLOW.md`'s secrets
  earlier this project (see `project_pmadminka_migration_to_vm105`
  memory): redact from the record, don't bother rotating the credential
  itself. Redacted both rows directly in `state.db` via a server-side
  `UPDATE ... SET content = replace(...)` (never copied the secret to
  local disk to search for it — an attempt to do so via `grep` on a
  locally-copied file was itself blocked by the operator's own sandbox
  classifier as credential materialization, confirmed working as
  intended), then rebuilt both FTS indexes (`messages_fts`,
  `messages_fts_trigram` — external-content FTS5 tables that cache their
  own tokenized copy and do **not** auto-sync when the source `messages`
  row changes; `INSERT INTO <fts_table>(<fts_table>) VALUES('rebuild')`
  is the required step, easy to forget). Verified zero remaining matches
  in both the table and both indexes before considering it done.
- **No issues found**: network exposure (`docker-compose.yml` has no
  `cap_add`/`privileged`/`network_mode`/`pid:` anywhere; `hermes-agent`'s
  8642 and `telegram-bot-api`'s 8081/8082 have no host port mapping,
  unreachable from the LAN); `gh` unauthenticated as intended; the
  multi-key `AIBRIDGE_KEY` system has no rate limiting or expiry (already
  documented as an intentional PoC limitation in `README.md`).

## Resource limits

`hermes-agent` bumped 2026-10-01 from `1.0 CPU / 768M` to
`2.0 CPU / 1.5GB` — measured at 76% memory (588MiB/768MiB) near-idle,
and the container does meaningfully more now (MCP, 2 fallback pools,
Telegram file handling) than when 768M was first chosen. VM105 had
ample headroom (4 cores, ~4.4GB free at the time).

## Gotcha: a deprecated Gemini model ID broke more than it looked like

A real user-facing error (`Gemini HTTP 404: model models/gemini-2.5-flash
is no longer available to new users`) traced to one stale pin: the
`fallback_providers` entry for Gemini had `model: gemini-2.5-flash`,
retired by Google. This single pin was also the cause of two
already-visible-but-unconnected symptoms (`Title generation failed`,
`Smart approvals: LLM call failed`), since both route through the same
fallback resolution. Fixed: `gemini-2.5-flash` → `gemini-3.8-flash`
(Google's own suggested replacement), edited live and synced to
`/hermes-persist` immediately (no rebuild needed). **Lesson**: a pinned
external-provider model ID is a live liability on its own schedule,
especially as a fallback (triggered only when the primary fails) — a
break can sit silent for a while.

## Tool gaps: tracking what Hermes reaches for

**Method**: grep the container's own log for the error shapes a missing
tool produces — no new instrumentation needed, `agent.tool_executor`
WARNING lines already say exactly what failed:
```
docker logs aibridge-hermes-agent 2>&1 | grep -niE \
  "not installed|command not found|No module named|ModuleNotFoundError|which:|convert:|identify:|is not on PATH"
```

Real gaps found and fixed this way, roughly in order:

1. **PIL/ImageMagick missing** — Hermes burned ~4 tool-call round trips
   and over a minute improvising a workaround (a manual Python `struct`
   magic-byte check) instead of just saying the tools were missing.
   Fixed: `file`, `python3-pil`, `imagemagick` added.
2. **Proactive round**: `bc`, `wget`, `sqlite3`, `php-cli` added ahead
   of any live gap, operator-requested.
3. **Audio tooling**: `ffmpeg`, `libchromaprint-tools` (`fpcalc`),
   `python3-pip` added after a real "no transcription tools installed"
   complaint; two new skills (`SKILL_audio_transcription.md`,
   `SKILL_audio_identify.md`).
4. **`gh`**: self-installed live by Hermes (`apt-get install -y -qq gh`)
   when a task needed it, then hit a dead end with no `GH_TOKEN`
   configured. Baked into the Dockerfile's approved list so it's free
   every boot; whether to configure `GH_TOKEN` at all (a fine-grained,
   read-only-scoped PAT would be the minimum-blast-radius option) is
   left to the operator.
5. **`iproute2`/`ethtool`/`brotli`**: not Hermes freelancing — root
   cause was `SKILL_network_diagnostics.md`'s own checklist assuming
   `ip` was available when `iproute2` was never in the package list.
   Lesson: re-check every `SKILL_*.md` against the actual package list
   rather than assuming a shipped skill already has what it calls for.
6. **PDF/diagram/design tooling** (operator-requested ahead of any live
   gap): `tesseract-ocr` (+ eng/spa packs), `graphviz`, `poppler-utils`,
   free fonts (`fonts-liberation2`, `fonts-noto-core`,
   `fonts-urw-base35`, `fonts-dejavu`) — all apt, judged not to need
   newer-than-Debian treatment (poppler-utils deliberately kept on the
   security channel specifically since it parses user-supplied PDF
   content). `pandoc` and `typst` got the pinned-static-binary treatment
   instead (apt's pandoc is a real 2-major-version-behind gap; typst
   chosen over a multi-GB texlive install).

**Also surfaced, not a tool gap**: Hermes's own `skill_manage` tool
tried to author a brand-new skill on its own, unprompted, and failed on
a system-side validation (description too long) — the capability is
real (Hermes can write and register its own skills at runtime, separate
from the `SKILL_*.md` files this repo ships), just not acted on either
way yet.

**Mermaid diagrams: deliberately not added.** `mermaid-cli` needs
headless Chromium via Puppeteer — too much weight/RAM for this
768MB-limited container. Graphviz/DOT already covers most diagram-as-code
needs; the two live options if Mermaid is needed later are accepting the
Chromium weight here, or pushing it to a heavy-tools-host as its own
endpoint (same pattern as the upscaler).

**Ongoing method**: the same grep, treated as an ongoing "heat map" —
cheap, no new code. Tools get approved deliberately into the Dockerfile
rather than letting the container `apt-get install`/`pip install`
anything mid-conversation on its own.

## Build speed: splitting the Dockerfile in two

Builds felt slow. First check ruled out the host (`uptime`/`free`/
`vmstat`/a network test all came back clean). Real cause: a build
**failure** (`tirith depends on sudo; however: Package sudo is not
installed` — missing from the apt list, needed only to satisfy tirith's
`.deb` postinst check) being misread as the build "hanging," plus two
steps that are just genuinely slow while working correctly:
`apt-get install` (~117s) and Hermes's own installer (~5 min, outside
this repo's control).

Fix for paying that cost on every unrelated change: split
`Dockerfile.hermes-agent` into two:

- **`Dockerfile.hermes-agent-base`** — the stable layer (all apt
  packages, pinned yt-dlp/pandoc/typst binaries, tirith), tagged as its
  own image: `docker build -f Dockerfile.hermes-agent-base -t
  aibridge-hermes-base:latest .`
- **`Dockerfile.hermes-agent`** — `FROM aibridge-hermes-base:latest`,
  just the Hermes install + `COPY` of the responder/start
  script/skills. `docker compose build hermes-agent`.

Both Dockerfiles also use BuildKit cache mounts
(`RUN --mount=type=cache,target=/var/cache/apt,sharing=locked`, same for
`uv`/`npm`) — persist downloaded packages outside the image layer, so
even a full base rebuild doesn't re-fetch everything over the network
(unlike plain layer caching, a cache mount survives instruction-text
changes).

**Measured**: a change confined to `Dockerfile.hermes-agent` now rebuilds
in **~11 seconds** against a warm base, down from the full ~6-7 minute
chain. A genuine cold base rebuild (first time, or a new apt package)
still takes several minutes — that cost didn't disappear, it just
stopped being paid for unrelated changes.

**Gotcha**: `aibridge-hermes-base:latest` is a separately tagged image,
not watched/rebuilt by Compose automatically — adding a package to
`Dockerfile.hermes-agent-base` requires manually re-running its `docker
build` *before* `docker compose build hermes-agent`, or the app layer
silently builds on a stale base.

## What's persistent, what's not

The container's own home directory (`~/.hermes`) is almost entirely
ephemeral — only a short, deliberate list survives a rebuild:

| Path | Persisted? | What it is |
|---|---|---|
| `/workdir` (host `./user1-workdir`) | ✅ real bind mount | The `terminal` tool's working directory. Empty in practice until a skill explicitly uses it. |
| `~/.hermes/auth.json`, `config.yaml`, `shared/nous_auth.*` | ✅ synced every 30s | Login + chosen model. |
| `~/.hermes/state.db`, `shared-state.db` | ✅ | Conversation memory. Before this fix, every rebuild reset Hermes's memory of every past conversation. |
| `~/.hermes/kanban.db`, `projects.db` | ✅ | State for `hermes kanban`/`hermes project` — small, kept even though neither is wired into the gateway. |
| `~/.hermes/cache/images/` | ✅ | Where every Telegram-received photo and every tool-generated image actually lands — was **not** persisted before, silently lost on every rebuild. |
| `~/.hermes/response_store.db`, `runs_idempotency.db`, `cron/executions.db` | ❌ on purpose | Pure idempotency/log caches, cheap to regenerate. |
| Everything else under `~/.hermes` (plugin venvs, model caches, scratch files) | ❌ | Regenerated/re-downloaded as needed. |

Practical upshot: raw uploads/generated files now survive a rebuild but
land in one undifferentiated cache folder. `/workdir` is the intended
place for anything a user wants to keep and find again (next section).

## Project workspaces

- Hermes does have a built-in `hermes project` feature (named,
  multi-folder workspaces) — but it's **not reachable from Telegram**
  (confirmed via source grep of `gateway/run.py`,
  `gateway/slash_commands.py`: no reference to the project registry) —
  CLI/desktop-session only. `projects.db` exists (persisted) but is
  empty.
- The actual mechanism today is a plain folder convention under
  `/workdir`, documented as
  [`aibridge/SKILL_project_workspace.md`](aibridge/SKILL_project_workspace.md):
  one folder per project (`/workdir/<slug>/`), ask which project an
  upload belongs to when ambiguous, copy anything worth keeping there
  explicitly (it doesn't land there on its own). "Switching projects" is
  just which folder the current conversation is about.
- Deliberately the simpler option — wiring `hermes project` into the
  gateway would be a feature request against upstream Hermes, not
  something to build inside this container.

## SSH access for real infrastructure

The `network-diagnostics` skill gives Hermes a methodology and the right
CLI tools, but **zero login access** to any host by design — it can only
diagnose what's reachable from inside its own container. Whether to grant
real SSH access, and to what, is a separate decision per host.

**Grants so far, both scoped to `iashur` only** (see "Hardened SSH
access" above for the fuller MCP-specific key):

- A dedicated ed25519 keypair (not a reuse of any fleet/admin key),
  mounted read-only into the container, wired into `~/.ssh/config` fresh
  every boot (no persistence needed for the config itself).
- `authorized_keys` carries `no-port-forwarding,no-X11-forwarding,
  no-agent-forwarding`. `iam` has no sudo on `iashur`, so this key
  cannot be used for system-level changes regardless.
- `SKILL_network_diagnostics.md` documents this as the one explicit
  exception to its own "grants no SSH access" rule, naming the host so
  Hermes doesn't generalize it.

No other host is wired this way — extending this to any other machine in
the operator's infrastructure is a separate decision each time.

## Open question: multi-user onboarding

The operator wants to share a Hermes instance with a second, trusted
person via an invite-key flow: a friend confirms an invite key in a
shared bot, which triggers generation of their own persistent container
plus a second key for them to validate. Agreed in principle as a single
operator-triggered manual provisioning step (see the architecture
decision below for why), but `provision_hermes_user.sh` is **not built**
— blocked on measuring available RAM for a second full instance. The
transparency/security questions a second real user would need answered
are written up as a proposed design in
[`USER_INSTANCE_GUIDE.md`](USER_INSTANCE_GUIDE.md) — decided on paper,
not built.

## Architecture: one full Hermes instance per human user

Hermes's own "profiles" feature (`hermes -p <profile> <command>`) is the
right tool for **one person** running multiple specialized agents, each
fully isolated — but it is **not** a security boundary between different
humans (Nous's own team has stated true multi-tenant isolation is still
"in development"). Sharing this system with a second real person means a
second, separate, full container, not a second profile inside this one.

Full automated self-service provisioning was deliberately not built: the
harness this project runs under is sensitive to anything that creates or
enables a new agent-capable container ("Create Unsafe Agents"), so a
single manual, operator-triggered step stays in the loop.

## Architecture principle: one brain, not one per machine

A second full Hermes/agent instance on every heavy-tools host would mean
redoing every hardening step per instance (commit pin, tirith, the whole
tool heat-map) and fragmenting Hermes's own self-improving memory, which
is per-install and doesn't sync between instances. The right shape is
specialized **services** on the heavy host (a database, a rendering
process, a scripting-API bridge), called from the one Hermes brain — same
pattern as the upscaler and the Resolve MCP design.

**SSH-wrap vs. direct network connection**: follows the target service's
own native protocol, not a blanket rule. Resolve's MCP server is
stdio-only by upstream design, so SSH wraps it. A service with its own
persistent-connection protocol (e.g. Neo4j's Bolt over TCP with its own
auth) gets a direct authenticated connection instead — wrapping every
query in an SSH invocation would fight the protocol for no benefit.

## Future direction, not started: OKF + Neo4j knowledge graph

Pointer: [lyonwj.com/blog/google-okf-neo4j-knowledge-graph](https://lyonwj.com/blog/google-okf-neo4j-knowledge-graph).
OKF (Open Knowledge Format, Google Cloud, June 2026) represents
organizational knowledge as markdown + YAML-frontmatter files, one
concept per file, consumed by AI agents; `neo4j-okf` materializes the
implicit graph (files → `:Concept` nodes, markdown links →
`:LINKS_TO`). Vector embeddings are optional and deliberately paired
with the graph rather than replacing it — pure vector similarity can't
distinguish a deprecated definition from the current one without the
graph's status/trust properties.

Not a fit for `hermes-agent` itself: Neo4j is a real database, not a
lightweight CLI tool, and embeddings optionally call an LLM API — none
of it fits the 768MB container. If built, the host is decided (`iashur`,
reusing the existing SSH identity) and the connection would be direct
Bolt (`bolt://iashur:7687`), not SSH-wrapped — not started.

## Future direction, not started: Hermes Agent as the human-facing Assistant

The now-deployed instance (aibridge provider + Telegram) could later be
reconfigured/extended into a single Assistant the operator talks to by
voice/phone, which decides on its own when to delegate to specialized
Agents (Claude, ChatGPT, Antigravity, Grok) via MCP:

```
Human
  │ voice / phone / Telegram / WhatsApp / Signal / SMS / Discord / Slack
  ▼
Hermes Agent  (as Assistant: memory, personality, decides when to delegate)
  │ MCP tool call
  ▼
aibridge-mcp  (NOT BUILT — thin MCP-server wrapper around /ask + /result/<token>.json)
  ▼
aibridge  (same bridge, unchanged)
  ▼
Agents: claude · antigravity · grok · hermes(-as-a-plain-provider, see above)
```

Not implemented — `aibridge-mcp` does not exist.

### Voice: confirmed working via Telegram, still no telephony

- **Built-in voice mode**: STT → agent turn → TTS. Default cascade: local
  `faster-whisper` → Groq → OpenAI (STT); Edge TTS free, with
  ElevenLabs/OpenAI as paid upgrades. **Confirmed working end-to-end**
  via a real Telegram voice message once `GROQ_API_KEY` was set.
- Works in CLI/TUI (push-to-talk), Discord/Telegram voice messages, and
  Discord voice channels (join, transcribe live, speak replies back) —
  the closest thing to "a call" without building telephony.
- One true full-duplex mode exists (OpenAI's `gpt-live-1`) but is
  **desktop-app only**.
- Extra plugins: `hermes-speech` (unified TTS+STT catalog),
  `openrouter-voice` (~20 STT models via OpenRouter), `hermes-omnivoice`
  (local multilingual TTS with voice cloning).
- **Confirmed gap**: no telephony anywhere in Hermes Agent — no phone
  number, no SIP, no real phone call.

**Sesame AI** (sesame.com, the "Maya"/"Miles" demo — not to be confused
with "sesame" the external caller in this project's own protocol, same
name, different thing): their open-source release
(`github.com/SesameAILabs/csm`, Apache 2.0) is **text-to-speech
generation only** per the repo's own FAQ — no ASR/STT, no roadmap for
one. The larger 8B model used in the actual demos was never
open-sourced, only a smaller 1B variant. Contributes nothing usable here
beyond "good TTS," and even that is the weaker model.

### Telephony: a concrete candidate path found 2026-10-01

Researched whether to integrate OpenClaw for its voice-call feature.
Conclusion: don't port OpenClaw itself — its voice-call plugin runs
inside OpenClaw's own Gateway process, requires a public webhook, and
using it would mean running a second, competing "brain" alongside
Hermes. Better path found instead: Hermes already ships a first-party
telephony skill (`official/productivity/telephony`, Twilio +
Bland.ai/Vapi) whose own docs state plainly it doesn't cover real-time
inbound calls. **Vapi** (already one of its supported providers) has a
"custom LLM" mode: point it at any OpenAI-compatible endpoint, and Vapi
handles telephony signaling + STT + TTS while that endpoint generates
every reply. Hermes already exposes exactly that
(`http://127.0.0.1:8642/v1/chat/completions`). Shape: **Twilio (phone
number) → Vapi (realtime audio/STT/TTS) → Hermes's own existing endpoint
as the brain** — no OpenClaw framework, no audio processing inside the
768MB container.

Real costs: Twilio (~$1-2/mo + per-minute), Vapi (usage-based, roughly
$0.10-0.20+/min all-in). New exposure: a public HTTPS endpoint for Vapi
to reach Hermes — a genuinely different posture than today's
outbound-polling-only pattern. Not started — open questions (recurring
cost acceptable? public endpoint acceptable? inbound/outbound/both?) not
yet answered.

## The bigger picture

The operator's own framing for this whole project:

> "If you're such a good programmer, why do you still use the keyboard?
> We need to add a layer of abstraction, so people can relax on the
> coast while good machines handle everything behind the scenes. A
> super friendly interface on top, and underneath it we put in whatever
> limits each project actually needs."

The harness restrictions hit throughout this document ("Create Unsafe
Agents", "[Code from External]", credential-leakage and
unauthorized-persistence blocks) are the *correct shape* of that second
layer, by the operator's own read — not an obstacle, a working example
of what per-project limits should look like underneath the friendly
interface.

## Status table

| Layer | Component | Status |
|---|---|---|
| Agent backend | `hermes` as an aibridge provider | ✅ deployed and working — confirmed fully end-to-end through aibridge's own `/ask?provider=hermes` |
| Agent backend | Claude (`claude -p`) | ✅ real, automatic |
| Agent backend | Antigravity (`agy -p`) | ✅ real, automatic |
| Agent backend | Grok (`grok -p`) | 🚧 prepared, not deployed |
| Direct channel | Telegram (text) | ✅ confirmed working, independent of aibridge |
| Direct channel | Telegram (voice, via Groq STT) | ✅ confirmed working |
| Skill | `network-diagnostics` | ✅ baked into the image, methodology + tools only, zero SSH access granted |
| Skill | `image-upscale` | ✅ baked into the image, confirmed working end-to-end via real Telegram usage (after the PNG→JPEG size fix) |
| Skill | `project-workspace` | ✅ baked into the image, folder convention under `/workdir`; not yet exercised by a real multi-project conversation |
| Infrastructure | Conversation memory + raw uploads persistence (`state.db`, `cache/images`) | ✅ fixed — was silently lost on every rebuild before |
| Infrastructure | GPU heavy-tools host (CUDA, `192.168.1.144`) | ✅ confirmed working (CUDA); Vulkan passthrough confirmed broken on the same host |
| Infrastructure | Telegram file-transfer cap (20MB → 2GB, Local Bot API Server) | ✅ fully wired (`--local` flag + shared volume + client `local_mode`); final confirmation from a real user upload still pending |
| Infrastructure | Fallback resilience (5 vendors + `fallback_watchdog.py`) | ✅ live — 9-entry chain, primary `gemini-3.5-flash-lite` (pinned to `provider: gemini`, swapped from `gemini-3.8-flash` 2026-10-01 to compare quota/speed empirically), `nous`/`openai-codex`/`openrouter`/`huggingface` fallbacks, watchdog running as a `systemd --user` service on VM105 |
| Infrastructure | iashur "mystery noise" (2026-10-01) | ✅ root-caused — operator's own auto-opening Chrome page ringing the system bell; closed, confirmed gone. Resolve/PipeWire/KDE/reverb-g2 all checked and cleared first |
| Infrastructure | NVIDIA NIM as a 6th fallback vendor | 💡 researched 2026-10-01 (genuine free tier, ~40 RPM resetting every minute, no card) — natively supported, blocked on operator creating a `build.nvidia.com` account |
| Infrastructure | Telegram usage audit (2026-10-01) | ✅ done — real day traced end-to-end, 5 findings (unconfirmed render-push notification, untagged voice transcriptions, 6 gateway interruptions, plaintext password fixed, benign compaction duplication) |
| Skill | `page-agent`, `mcp-oauth-remote-gateway` (official bundled) | ✅ enabled 2026-10-01 via `hermes skills repair-official --restore` — gap found during the usage audit above |
| Infrastructure | DaVinci Resolve MCP connection | ⚠️ editing works; **rendering through the MCP does not work headless** (`LoadRenderPreset` False, render call hangs to the timeout, reproduced twice). Hermes falls back to ffmpeg NVENC; `/ask` run took ~7.5 min vs 17 min and no file on Telegram. See the two timing sections |
| Evaluation | `unofficial-davinci-mcp` as a third Resolve MCP server | 🚧 code reviewed and installed on iashur (not wired into Hermes); live tests on `MCP-Benchmark` paused until iashur is back on X11 |
| Infrastructure | `hermes-agent` container resources | ✅ bumped 2026-10-01, 1.0 CPU/768M → 2.0 CPU/1.5GB (host had ample headroom; old limit was measured at 76% memory near-idle) |
| Infrastructure | Security audit (world-readable `.env`, stray SSH key) | ✅ fixed — orphaned `.env` deleted, `umask 077` added, unexplained `hermes@mcp` key removed; tirith's fail-open default accepted as-is |
| Caller | ChatGPT (Custom GPT Actions) | 🚧 key + schema configured, first real authenticated call not yet confirmed in logs |
| Future, not started | Second human user (own Hermes instance, invite-key onboarding) | 💡 design agreed, blocked on RAM sizing, provisioning script not built |
| Future, not started | SSH access for Hermes into real infrastructure | 💡 explicitly deferred, separate decision |
| Future, not started | DaVinci Resolve MCP *delegation* (phone footage → edited video, the actual skill/request shape) | 💡 connection is live (see above), nothing wired into a skill yet |
| Future, not started | `resolve-gateway` aggregator (MCP-over-HTTP, hardware-busy gate, rsync-based upload/download) | 💡 full design documented 2026-10-01 ("Planned next step" above), zero implementation |
| Infrastructure | iashur session/power config (X11-vs-Wayland autologin, CPU governor/power profile persistence) | 🚧 root cause found and two fix scripts written 2026-10-01, not yet run on the machine |
| Future idea, not started | Hermes Agent as the human-facing Assistant (voice/messaging) | 💡 confirmed by the operator as a real future direction, zero implementation beyond what already exists as a side effect (Telegram) |
| Future idea, not started | Real phone-call / telephony interaction | 💡 a concrete candidate path found 2026-10-01 — Twilio (number) → Vapi (realtime audio/STT/TTS, "custom LLM" mode) → Hermes's own existing `/v1/chat/completions` endpoint as the brain, no OpenClaw framework needed; costs real money per-minute, needs a new public-facing endpoint, open questions not yet answered by the operator |
| Future idea, not started | `aibridge-mcp` adapter | 💡 designed on paper only, not built |

Note the asymmetry already in play: today, **ChatGPT is a caller into
aibridge** (it asks Claude/Antigravity/Hermes questions through the
bridge), same role sesame has — not an Assistant the human talks to.
