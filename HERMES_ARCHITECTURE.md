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
  earlier the same day, asked to review whether `<person-domain-1>`
  and `<person-domain-2>` were "solid/optimized," Hermes had to
  improvise the check ad-hoc with no dedicated skill for it.
- **`mcp-oauth-remote-gateway`** (`mcp`) — ships most of the design
  already sketched under "Planned next step: a resolve-gateway
  aggregator" above (MCP-over-HTTP instead of MCP-over-SSH). Worth
  reading before building that aggregator from scratch — it may cover
  most of the groundwork already.

## Wake-on-demand: stacks that sleep when nobody uses them (2026-10-07)

Goal: save RAM and CPU as more people are added. Every stack (hernik, herand, hereug) is two tiers: **web** (Open WebUI
+ TTS, ~300 MB) and **brain** (Hermes, ~500 MB; a whole awake stack measures 926 MB with nginx). Nothing is recreated:
`docker stop/start` on containers whose data lives in bind mounts, so chats, logins (fixed `WEBUI_SECRET_KEY`) and
files survive. One host service does all of it: `ops/wake/waker.py` (`systemd --user`, `aibridge-waker.service`,
config `ops/wake/stacks.json` from `stacks.json.example`, no docker.sock inside any container).

### How a stack wakes (and when it does NOT)

| Trigger | What happens |
|---|---|
| a browser **navigation** to the web UI | nginx gets 502 (Open WebUI stopped), `error_page` hands it to the waker (`$waker`, per stack from `web/wake/` or `stacks/<name>/wake/upstream.conf`); the person sees "Despertando a Hermes… ~N s" (N = median of the last boots), which polls `/__wake/status` and reloads itself |
| a **Telegram** message to an allowed user (hernik; the "Encendiendo" / "Listo para trabajar" notices were confirmed received by the operator on 2026-10-07 after a direct `sendMessage` test through the same Bot API path) | while the brain is stopped the waker peeks at `getUpdates` **without confirming** (the message stays queued), starts Hermes, answers "⏳ Encendiendo Hermes… tarda unos N s" and, once Telegram is connected, "✅ Listo para trabajar". Needs `platforms.telegram.extra.drop_pending_on_cold_boot: false` (set by `start_hermes.sh`) or Hermes drops the waking message on a cold boot |
| a **cron** that is due | see Crons |
| background traffic of an old tab (websocket, XHR, `/_app/version.json`, `/api/version`) | 503 and nothing else: it never wakes anything and never counts as activity. Open WebUI polls `/_app/version.json` once a minute from every open tab: counting it would keep a stack awake behind a forgotten tab (seen in herand's nginx log) |
| an unknown person on Telegram | ignored (only `TELEGRAM_ALLOWED_USERS` wake it) |

Hooks: after the brain is ready every executable in `ops/wake/on_wake.d/` runs (env `WAKE_NAME`, `WAKE_REASON`,
`WAKE_CHAT_ID`): the place for "summarise the previous session".

### When it sleeps

**10 minutes** (`idle_web` = `idle_brain` = 600 s, all three stacks, set 2026-10-07) without a real UI request or a running
turn, counted from the same last activity: web stops first, then the brain, in the same tick. Only if nothing is busy. **Busy** (never stopped) = a turn running, a UI request in the last 2 min, a booting/stopping stack, a cron in its hold
time, or a registered long job in `/workdir/jobs` (that is what makes `jobwatch` useful: while a job exists the stack stays
awake). `touch ops/wake/NO_SLEEP` stops all sleeping (maintenance).

### RAM budget: never leave the limits

- **Entering together takes turns.** Boots are serialised (`max_parallel_boots`, default 1): the second person sees "hay otra
  persona encendiendo su Hermes y sos la siguiente", the first one's boot finishes, then the next starts. Two wakes can
  never count the same free memory. With many users the last one waits N boots; raise `max_parallel_boots` only if RAM
  and CPU allow.
- Before starting anything: `MemAvailable - expected footprint >= reserve_mb` (1500) and fewer than `max_awake` brains
  (4, only a cap). Otherwise it stops the least recently used **idle** stack (web first, then brain); if that is not
  enough the wake waits up to 5 min (telling the Telegram user) and **never starts anyway**.
- A watchdog every 10 s stops idle stacks below `critical_mb` (700). It never stops a busy stack.
- Each container keeps its compose cgroup limit, so a runaway dies alone. Honest limit: simultaneous spikes of several busy
  stacks are bounded by those limits and the reserve, not prevented.

### Crons (policy decided 2026-10-07)

A sleeping stack's Hermes cannot tick, so the waker reads each stack's `cron/jobs.json` (`docker cp`, works on a stopped
container) and wakes the brain only when there is something to run:

1. **Nothing to run, nothing wakes.** Empty cron list, only `ignore_names` jobs (`jobwatch`), or jobs not due yet: no wake.
2. **At most once per hour.** Jobs run on an hourly grid (`grid_minutes` 60, shifted 10 min per stack so stacks do not
   share a minute). One wake per period serves every job due by then. A job asking "every 1m" fires at most every
   `min_interval_min` (60). The person is told: hernik's owner gets a Telegram message once per job; everybody gets it from
   the `cron-policy` skill (baked in the image and installed live in all three), which makes Hermes say "se dispara como
   máximo una vez por hora" before creating any recurring task and use `/workdir/jobs` for near-real-time needs.
3. **Last look before waking.** Right before spending RAM it re-reads the jobs: if the stack already ran them while awake
   (they are no longer due) it does not wake.
4. **Never at another stack's expense.** A cron wake never evicts anybody and never waits: no free RAM = postponed 10 min.
5. **One at a time**, 240 s apart (`slot_seconds`), and the brain gets only 180 s after the run before sleeping again.

Reviewed 2026-10-07: the only cron anywhere is hernik's `jobwatch` (no LLM, every minute, a no-op unless a long job is
registered). herand and hereug have none.

### Firewall (guests)

Containers cannot reach host ports (ufw drops INPUT from docker networks): hernik's network works with
`ufw allow from 172.21.0.0/16 to any port 3099`. Guests need more: `docker-user-fw.sh` inserts
`INPUT 1 -s 172.28.0.0/16 -j DROP`, **above** ufw, so a ufw rule for a guest subnet never applies. The script adds one
pinhole per guest network: that subnet -> its own gateway:3099 only. Applied 2026-10-07 and checked: each nginx reaches its
own waker; a guest reaching another stack's waker, or the host's ssh, times out. A new stack needs: its `wake/upstream.conf`
(`provision_stack.sh` creates it), a block in `stacks.json`, `sudo /usr/local/sbin/docker-user-fw.sh`, and
`systemctl --user restart aibridge-waker`.

### Bugs found while building it (each would have bitten in production)

- `start_hermes.sh` as PID 1 ignored SIGTERM: `docker stop` waited out the grace period and SIGKILLed with up to 30 s of
  sessions/memory unsynced. It now traps TERM: stops the gateway, flushes `PERSIST_PATHS`, exits (2-7 s). **Only containers
  created from the new image have it** (hernik yes; herand and hereug still run the old image: their stop takes the full
  45 s grace; harmless because a brain is only stopped after 15 idle minutes, so the 30 s sync has long run).
- the stop flag lives in `/tmp`, which survives `docker stop`+`start`: a stale flag made the gateway loop skip the gateway after
  a wake (Hermes "up", Telegram dead). Cleared at boot.
- `drop_pending_on_cold_boot` defaults to true: the message that wakes Hermes would be dropped.
- `gateway_state.json` keeps "connected" from the previous life: readiness trusts it only if written after the **container**
  started (first version compared with the wake time and made a web-only wake wait 40 s).
- a ufw rule for a guest subnet is useless (see Firewall); a first `max_awake=2` made hernik wait for a slot while RAM was
  plentiful.
- the cron planner planned overdue jobs in the past (two stacks at once), ignored the wake that had just happened (7 s gap),
  and marked a job as "woken" even when the wake was postponed.
- the loop that waits for memory never ran for a non-patient (cron) wake.

### Measured

Open WebUI alone: 15.7 s from `docker start` to first request (7 s of Python imports, 5 s migrations). Web wake with Hermes
already up: ~20 s end to end; a real guest (hereug) cold: **22.5 s**. Hermes after `docker start`: 38-49 s to "Connected
to Telegram" (first boot after a recreate: 161 s). Freed memory per sleeping stack: ~900 MB. **Data check on hereug (real
sleep/wake through its nginx):** 8 chats, 1 user, 140 messages, 35 Hermes sessions, 883 messages and the memory hash identical
before and after.

### Tests

`python3 ~/aibridge/ops/wake/selftest.py` runs the real `waker.py` against three fake stacks (tiny containers, short timings,
fake `MemAvailable`): 31 checks, all passing. Background traffic does not wake; a forgotten tab polling `version.json` does
not keep a stack awake; navigation wakes; two simultaneous visitors boot one after the other (`WRWR`); idle sleep in reverse
order; `NO_SLEEP`; LRU eviction at the cap; low memory makes a wake wait; the watchdog stops idle stacks at critical memory;
empty cron list and a job due in 2099 wake nothing; a cron with no free RAM is postponed without evicting anyone; crons are
staggered, on the grid, rate limited; `jobwatch` never wakes. Run it after any change to `waker.py`.

### Boot time after the 2026-10-09 work (measured, web wake, steady state)

| | before | after |
|---|---|---|
| hernik (Telegram + Resolve MCP) | 36-47 s | 17 s |
| herand / hereug | 16-17 s | 13-14 s |
| stop of a stack | up to 45 s (TTS alone 30 s) | ~3 s |

What did it:
- **Config sets skipped:** `start_hermes.sh` skips the per-boot `hermes config set` calls (2-5 s each) when a stamp
  says config.yaml is unchanged.
- **MCP check:** ssh MCP servers whose host is down are disabled for that boot.
- **`init: true`:** TTS and Open WebUI stop on SIGTERM now.
- **Web wakes:** they wait for the Hermes API only, not for Telegram. Hermes reports Telegram "connected" only after
  one full 10 s getUpdates cycle; a Telegram wake is fast anyway because the waiting message ends that poll at once.
- **Shorter sentinel poll:** 2 s with a local Bot API.

What is left:
- Open WebUI's own start (~13 s, mostly Python imports on this CPU), which is now the slowest part of a web wake.
- The Hermes gateway's import/init (~8 s).

The next lever is `docker pause` for the first minutes of idleness (item 9 below), or faster hardware.

### Proposals to boot faster and use less (1, 2 and 4 done 2026-10-09; ordered by gain / effort)

Where the time goes, hernik Hermes (40 s): **13 s** ~15 serial `hermes config set` at every boot (each starts a Python) ·
**22 s** the DaVinci Resolve MCP: the gateway waits for 3 failed `ssh resolve-host-mcp` attempts (resolve-host is usually off) before it
opens the API and Telegram · 5 s everything else. Open WebUI (15.7 s): 7 s imports.

1. **Skip the config sets that are already applied** (compare a hash of the wanted values, or `hermes config get` first):
   -12 s per boot, trivial.
2. **Do not block the gateway on an unreachable MCP**: check `nc -z -w2 resolve-host 22` before boot and set
   `mcp_servers.davinci-resolve.enabled` accordingly, or put `-o ConnectTimeout=3 -o BatchMode=yes` on that ssh: up to -20 s.
   Together with (1) Hermes would be ready in about 8-10 s instead of 40.
3. **Recreate herand/hereug from the new image while they sleep** (no extra downtime): they get the clean-stop trap (stop
   2-7 s instead of 45-66 s), `rg`, `uuidgen`, `procps`, the video-note and STT fixes. Cost: whatever is not in
   `PERSIST_PATHS` (cron jobs, logs, request dumps) is lost; today that is nothing for them. Needs the operator's OK.
4. **`init: true` in compose for Open WebUI and TTS**: PID 1 python ignores SIGTERM, so `docker stop` waits the full grace
   (hereug's web took ~40 s to stop). Faster eviction when RAM is critical.
5. **The Hermes dashboard (163 MB RSS per guest, only used to change model/keys) could start on demand** instead of living in
   the Hermes container; ~160 MB x each awake guest.
6. **Disk, not RAM** (done 2026-10-07): the build cache was 41 GB; `docker builder prune -f` freed 26.8 GB (disk 76% -> 45%,
   images and containers untouched; the next rebuild re-downloads, so it is slower). The Hermes image is 8.7 GB (base
   4.4 GB), shared by all stacks.
7. **Memory limits:** guests cap Hermes at 2.5 GB, hernik at 3.5 GB; measured use is 0.3-0.5 GB idle. Fine as safety caps.
   `aibridge-claude-agent`/`antigravity-agent` have no cap (6.9 GB shown): give them one.
8. **Services that look unused**: decided 2026-10-09, see "Legacy services" below (stopped, compose profile `legacy`).
9. If the first-boot wait still matters: `docker pause` instead of `stop` for the first minutes of idleness (wake in <1 s, no
   RAM freed), then `stop`. Not worth it unless people complain about the 20 s.

## Operator alerts and the privacy guard (2026-10-09)

**Why.** On 2026-10-09 hernik's Telegram chat had a `/model` pin to a Hugging Face model with no credit left. Every turn
failed with a 402 before it fell back, and nothing told anybody. `model_guard` only counted errors of the primary
provider. It also looked for pins in `sessions/sessions.json`, which no longer exists since v0.21.6 (pins now live in
`state.db` → `gateway_routing.entry_json.model_override`). On top of that, operator alerts went out through hernik's
own bot, which sleeps.

**Ops bot** (`ops/lib/notify.py`). It sends from the host straight to `api.telegram.org`, so no stack has to be awake.
- **Config:** `~/aibridge/ops/ops.env` (untracked) with `OPS_BOT_TOKEN` and `OPS_CHAT_ID`.
- **Alerts:**
  - Every alert has a key and is sent once, then again every 6 h while it lasts.
  - A "✅ resolved" message goes out when the problem clears.
  - Failed sends wait in `~/.local/state/ops_outbox.jsonl`, at most the 30 newest, and any later call retries them.
- **Users:**
  - `model_guard`:
    - no provider answers;
    - primary switched;
    - a `/model` pin that does not answer (reported by a hash of the session key, never the chat id);
    - ≥3 failed calls to one provider in 15 min.
  - `key_check`:
    - dead keys per stack (Gemini's `400 API_KEY_INVALID` counts as dead);
    - keys answering 429 for more than a day.
  - `waker`:
    - boot timeout, or a boot slower than 90 s;
    - no memory to wake;
    - RAM critical;
    - a failing hook.
  - Every user unit: `OnFailure=ops-alert@%n.service`.
- **Exit codes:** `key-check` exit 1 and `model-guard` exit 2 mean "found and already reported" (`SuccessExitStatus`).
  That way a known problem does not also page as a failed unit.

**Privacy guard** (`ops/privacy_scan.sh`). The repo is public. People's names, chat or session ids, personal domains,
LAN addresses and host names never go in it.
- **The forbidden strings** live only in `~/.config/bridgeai/private-replacements.txt` on the operator's desktop, in
  git-filter-repo `--replace-text` format, so the same file can rewrite history.
- **Modes:** `--install` adds pre-commit and pre-push hooks; `--tree` and `--history` are audits.
- **LAN layout:** it now comes from untracked files:
  - `~/aibridge/.env`: `LAN_IP`, `RESOLVE_HOST_IP`, `RESOLVE_HOST_USER`, `RESOLVE_HOST_ALIASES`, `GPU_DESKTOP_IP`;
  - `/etc/default/aibridge-fw`: `LAN_CIDR`, `EDGE_IP`, `GUEST_PINHOLES`.
- **Generic names in skills:** they use `resolve-host` / `resolve-host-mcp` (SSH aliases written by `start_hermes.sh`)
  and `gpu-desktop` (compose `extra_hosts`). Older alias names that a persisted `config.yaml` may still use keep
  working through `RESOLVE_HOST_ALIASES`.

## Usage telemetry without personal data (2026-10-09)

`ops/telemetry.py` runs every 5 min (`telemetry.timer`). It sends a daily summary at 09:00 Argentina
(`telemetry-report.timer`) and, on Mondays, a "what to improve" ranking (impact = occurrences × people affected).
Data lives in `~/.local/state/telemetry.db` (0600) on VM105 only.

| table | columns |
|---|---|
| turns | stack, time, channel, seconds to the final answer, tool calls, tool errors, failed, empty, model, 8-char hash of the session id |
| errors | provider, model and HTTP code of failed model calls (agent.log) |
| wakes | reason, seconds, outcome (waker journal) |
| host | free RAM, swap, disk |

Message text never leaves SQLite: the queries compute "empty answer" and "tool error" as booleans inside the database.

**Where it reads from:**
- A running stack is read with `docker exec`, from the live db including its WAL.
- A sleeping stack is read from its persisted copy, through a throwaway `--network none` container that mounts it
  read-only (the files are root 0600).

**How turns are counted:**
- A turn is a user message up to the next one.
- A burst of messages sent before any answer counts as one turn. Measured: 35 of hernik's 58 "unanswered" Telegram
  messages were followed within 30 s by another one, and Hermes answered them together.
- **Failed** = Hermes marked it `failed_turn`, or no final answer came within 15 min.

**Instant alerts (ops bot):**
- a failed turn, or an empty answer;
- an answer with no tool calls that took more than 60 s;
- the TTS of an awake stack not answering a one-phrase probe;
- disk at 85% or more;
- a backup older than 26 h.

**First week's numbers** (2026-10-02 to 10-09):
- hernik: 27 of 191 Telegram turns ended without an answer (14%): 10 marked `failed_turn` by Hermes, ~9 long tool
  chains that never produced a final answer, the rest unanswered bursts.
- herand and hereug: 1-2% on the web.
- hernik has no backup: `backup-stacks.sh` only covers `stacks/*`.

**Durability gap, also found here:** `PERSIST_PATHS` copies `state.db` with `cp` but not its `-wal`. A container that
dies without the clean stop loses the messages written since the last checkpoint. The fix is to copy with SQLite's
backup API instead of `cp`.

## Legacy services (stopped 2026-10-09)

The project started as **aibridge**, a queue where one AI asks and another answers ("Architecture: sesame → aibridge →
hermes" above). Per-person Hermes stacks replaced that use, and these containers were still running on VM105 without
traffic. All come from the compose project `aibridge` (`~/aibridge/docker-compose.yml` on VM105). They now sit in the
compose profile `legacy`: a plain `docker compose up -d` no longer starts them.

| Container | Code | What it does | Evidence it is unused |
|---|---|---|---|
| `aibridge` | `app.py`, `Dockerfile` | HTTP queue: `/ask` (an AI posts a question), `/result/<token>.json` (polls for the answer), providers take work with `/next` and post the answer with `/deposit`; `/credits` meters use. Published on all interfaces, port 8010; the edge vhost proxies the public bridge domain to it. Guides: `GUIDE_ASKING_AGENT.md`, `GUIDE_RESPONDING_AGENT.md`, `GUIDE_CHATGPT_ACTIONS.md`, `chatgpt-actions-schema.json` | 0 HTTP requests in the 72 h before 2026-10-09 |
| `aibridge-claude-agent` | `responder_claude.js`, `Dockerfile.claude-agent` | Polls the queue every 10 s and answers requests addressed to provider `claude` with Claude Code (`./claude-config` holds its login) | Only "arrancando" in its log; the queue was empty |
| `aibridge-antigravity-agent` | `responder_antigravity.py`, `Dockerfile.antigravity-agent`, `deploy_antigravity_agent.sh` | Same, for provider `antigravity` (Gemini through the Antigravity CLI, `./antigravity-config`) | Same |
| `aibridge-responder-test` | `responder_test.py`, `Dockerfile.responder` | Answers any pending request with a random phrase, to time the round trip | Already stopped 2026-09-29, but compose still had `restart: unless-stopped` |
| responder inside Hermes | `responder_hermes.py` (started by `start_hermes.sh`) | Hermes's own poller for provider `hermes` | Now only runs with `AIBRIDGE_QUEUE=on` |

Not ours: `hosts-pg-postgres-1` (compose project `hosts-pg`, another user's directory) also runs on VM105 and publishes
Postgres on all interfaces, port 5432. Leave it alone; tell its owner about the open port.

Bring the queue back: set `AIBRIDGE_QUEUE=on` in `~/aibridge/.env`, then
`docker compose --profile legacy up -d aibridge claude-agent antigravity-agent` and recreate `hermes-agent` while it
sleeps. Stop them again: `docker compose --profile legacy stop aibridge claude-agent antigravity-agent responder-test`.

## Usage audit 2: three instances, 2026-10-05 to 10-07 (written 2026-10-07)

Source: `agent.log`/`errors.log` of hernik, hereug and herand (about 200 user turns, 70 sessions; web users
through Open WebUI, hernik mostly Telegram). Per-person content stays in each instance: this records only
failure patterns and what was done. Method: count `Tool X returned error`, turn endings and zero-tool turns;
then read the failing sessions.

| Finding | Where | Cause | Status |
|---|---|---|---|
| **Voice transcribed as English** | hernik (all 21 STT calls logged `lang=en`) | Hermes ships `stt.language: "en"` as a GLOBAL hint; Spanish/Russian speech came out as a bad English "translation" that the agent then answered. Same audio: `en` gave "No, make all audio transcripts on Russian...", auto gave correct Russian | **fixed live** (`stt.language ""`, backup `config.yaml.bak-stt`) and set at first boot for new instances |
| `web_search`/`web_extract` failing, "I can't reach Mercado Libre or Google" | hernik, since 10-06 21:25 | no `web:` block in hernik's config, so Hermes fell back to `openai-native` (needs the Codex transport). `web.backend` was only set at first boot of guests | **fixed live** (`keenable`) and now set at every boot when missing. Google answers with a CAPTCHA to `browse-page` (use `web_search`); Mercado Libre needs `browse-page <url> --links --scroll 1` |
| "LinkedIn is not available" | hereug | her persistent memory said "LinkedIn without login is not available... search the other portals", read as "LinkedIn is excluded"; plus the vault cannot prompt from Open WebUI (`prompt_unavailable`, 5x) | memory entry rewritten (public LinkedIn search works via `buscar-empleos --portales linkedin`; login/vault not offered); skill description + LinkedIn section added; she must open a new chat |
| `execute_code` BLOCKED on unattended platform | hereug 14, herand 6 | `approvals.unattended_mode` not yet `approve` | none since 10-05 23:33, resolved |
| `terminal` waits 300s for an approval nobody answers | hereug 12, herand 3 (10-05/06) | commands needing approval on a surface with no one to approve (mostly the `hermes vault add` attempts) | none since 10-06 19:46; watch |
| `search_files` refused (no ripgrep) | herand 8, hereug 3 | `rg` not installed | `ripgrep` added to the base image (needs rebuild) |
| `uuidgen: command not found` | herand 2, hereug 3 | not installed | `uuid-runtime` added to the base image (needs rebuild); skills already mention `/proc/sys/kernel/random/uuid` |
| `pdflatex not found` | herand 3, hereug 2 | texlive deliberately not installed | none; the PDF path is weasyprint + `generate-pdf.mjs` |
| `web_extract` returns an error page | ZonaJobs (herand), LinkedIn jobs (hereug, `Keyless Keenable extract fail`) | anti-bot; `web_extract` is the wrong tool for portals | skill already says `buscar-empleos` + `browse-page`; the agent still tries `web_extract` first sometimes |
| `skill_manage` refused 12x per instance | all three | the background self-improvement review tries to patch user-owned skills (`created_by=None`); harmless but burns a tool turn each time | open, low priority |
| `read_file` on `/hermes-files/...` not found | herand, hereug | that is the URL path; the file is under `/web-outputs/<uuid>/` | open: the `web-interface` skill could say it louder |
| `max_iterations_reached` | hereug 2, herand 1 | all in the *background review* turns (16-iteration cap), not user turns | none |
| deferred-tool names wrong (`mcp__davinci_resolve__...` unknown) | hernik 21 | the agent guesses the name instead of using what `tool_search` returns | open |
| TTS: `openai` has no key, `piper` package missing | hernik 2 | the TTS provider chosen in that call was not the working one (Piper runs as its own container) | open: check which provider the agent picks |

Reading of the numbers: 30-40% of turns on the web instances answered with no tool at all (`tool_turns=0`),
which is expected for chat but is also how the LinkedIn mistake survived: the model answered from its memory and
history without loading the skill. **Memory entries that forbid something are read broadly**: write them as "X
works, Y does not" with the exact command, never "not available".

## Usage audit: tracing a real day of Telegram use (2026-10-01)

Separate from the heavy tool-call activity driving the Resolve pipeline
(documented above): a direct audit of the operator's own Telegram
conversation with Hermes that same day (`docker logs
aibridge-hermes-agent` grepped for Telegram activity, plus direct
`sqlite3` queries against `~/.hermes/state.db`'s `messages` table for
session `<session-id>`, chat `<chat-id>`), to see what the
operator actually asked for and where Hermes fell short in practice
rather than in theory.

**What happened, in order**: morning conversation (image-upscale
request, a song-ID audio clip, a network check, then review requests for
`<person-domain-1>` and `<person-domain-2>` — the gap that
led to enabling `page-agent` above); 09:27 the Resolve/`resolve-host` work
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

- **Host**: operator's desktop, `<gpu-desktop-ip>`, NVIDIA GTX 1070 Ti
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

## TTS (voice replies): candidate comparison, in progress (2026-10-03)

Goal: Hermes/OpenClaw answering with voice notes. Original target was
Sesame CSM-1B (best naturalness), but two things ruled out going through
**Sesame's own product/gateway**: it can't be trusted as a pipeline step
(operator's own assessment, not tested to destruction: restricted to a
validated set of outbound sites, reports commands as sent and invents IDs
to say everything is fine, steers conversation toward its own training
purpose, and could change or break without notice). Decision: **reliability
over quality** — local, self-hosted models only, no third party that can
change under us.

Note CSM-1B (the open model) is not what powers Sesame's demo (a fine-tuned
variant, not published). CSM-1B itself is English-only, has no voice
cloning, needs gated `Llama-3.2-1B` access on HF, and was **not benchmarked**
yet. Expected to be too slow on this GPU (Pascal, no bf16) — unverified.

`tts/` has one OpenAI-compatible service per candidate (`POST /v1/audio/speech`,
`GET /healthz`, `response_format` wav/mp3/opus, stdlib HTTP server like
`upscaler/`) plus `tts/bench/bench.py` (median of 3 runs after a discarded
warm-up; no streaming, so TTFB == total). Measured on the GTX 1070 Ti desktop:

| Model | Runs on | short (1.5s audio) | long (11.5s audio) | RTF | Spanish |
|---|---|---|---|---|---|
| Kokoro 82M (`Dockerfile.kokoro`, `:5002`) | GPU | 0.09s | 0.39s | 0.03–0.06 | native `ef_dora` |
| Kokoro 82M | CPU | 0.39s | 2.87s | ~0.25 | native |
| Piper `es_MX-claude-high` (`Dockerfile.piper`, `:5004`) | CPU | 0.11s | 0.56s | 0.04–0.07 | native |
| Qwen3-TTS 0.6B fp32 (`Dockerfile.qwen`) | GPU | 3.7s | 20s | 1.3–1.5 | no native voice (accent) |

- **Qwen3-TTS: discarded on this GPU.** fp16 yields NaN probabilities
  (`probability tensor contains either inf, nan or element < 0` → CUDA
  device-side assert) on Pascal; fp32 works but is slower than real time.
  Its preset speakers are zh/en/ja/ko only.
- **Dockerfile gotchas hit**: Ubuntu 22.04's pip crashes in the resolver
  (`AssertionError` in `get_topological_weights`) — upgrade pip first.
  `qwen-tts` pulls a CUDA-13 `torchaudio`, which fails to load against
  torch cu124 (`libcudart.so.13`) — force-reinstall `torchaudio==2.6.0`
  from the cu124 index with `--no-deps`.
- Kokoro `opus` output verified (ffprobe: opus 48kHz) for Telegram voice bubbles.
- **Sound quality not yet judged** — WAVs are in `tts/bench/out/<model>/`
  (git-ignored); the operator listens and picks between Kokoro and Piper.
- Not done: Chatterbox, CSM-1B, Orpheus benchmarks; wiring into Hermes
  (`tts.provider: openai` + `base_url`, or a `type: command` provider) and
  OpenClaw (`tts.providers.openai.baseUrl`, `responseFormat: "wav"`).
- Demo containers (`tts-kokoro`, `tts-kokoro-cpu`, `tts-piper`) stopped, not
  removed; weights live in the `tts-models` Docker volume.

## DaVinci Resolve MCP: video editing delegation

Same "one machine processes, another one runs the pipeline" pattern as
the upscaler, on `resolve-host` (`<user>@resolve-host`, a physical Debian 13
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
  resolve-host-mcp "~/Documents/resolve-linux/pipelines/mcp-benchmark/resolve_mcp_wrapper.sh headless"
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

A security audit flagged that the original `resolve-host` key (see "SSH
access for real infrastructure" below) grants a full interactive shell
as its user, not just the ability to run the Resolve wrapper — if the
`hermes-agent` container were ever compromised, that key would allow
arbitrary commands on `resolve-host`, not just MCP traffic. Live traffic
capture during a real MCP task confirmed Hermes never issues a raw
SSH/terminal command against `resolve-host` for Resolve work — only
`mcp__davinci_resolve__*` tool calls over the one stdio channel — so a
second, more restricted key costs nothing functionally:

- **New key**, `resolve-host-mcp` alias, `authorized_keys` forced command:
  `command="~/Documents/resolve-linux/pipelines/mcp-benchmark/resolve_mcp_wrapper.sh headless",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty,no-user-rc`
  — whatever Hermes's SSH client actually sends is ignored server-side;
  only the wrapper ever runs. Verified live: sending
  `whoami; id; kill -9 1` over this key produced only the wrapper's own
  output.
- `config.yaml`'s `mcp_servers.davinci-resolve` now points at
  `resolve-host-mcp`, not `resolve-host`.
- The original `resolve-host` key stays as-is (full shell, same
  `no-port-forwarding,no-X11-forwarding,no-agent-forwarding` restrictions
  as before) because `SKILL_network_diagnostics.md`'s ping/traceroute/
  etc. exception genuinely needs arbitrary read-only commands and uses
  that alias.
- A third, unexplained key (`hermes@mcp`, no restrictions at all, no
  matching private key found anywhere on VM105 or `resolve-host`) was found in
  the same audit and removed.

**Incident, same audit**: heavy concurrent MCP testing left 3 orphaned
`server.py` processes on `resolve-host`, causing new tool calls to hang for
40–90s before timing out. Killing the stale processes triggered
Resolve's own crash-recovery flow, which relaunched it in GUI mode (not
headless) — cleared by killing the resulting `-reportCrash` process and
letting the wrapper relaunch cleanly in `-nogui`. Confirmed fixed via a
real MCP call (13.5s round trip, real project data back).

### Health re-check found a real bug: `restart_app` drops headless mode (2026-10-02)

A re-check (independent of the "confirmed working end-to-end" test above)
found `resolve_headless.py status` reporting `headless: False` — Resolve
running in GUI mode, not the documented `-nogui` design. Process chain
and the hardened `resolve-host-mcp` key were both otherwise intact, no drift
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
  reproducible bug in `~/resolve-install/davinci-resolve-mcp` (a fork
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
  round trip through Hermes and the `resolve-host-mcp` key reports
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

### Resolve MCP goes down whenever resolve-host leaves its X11 session (2026-10-02)

Headless Resolve (`-nogui`) still binds to the X server it was launched
against. Around 00:19 resolve-host's graphical session switched from KDE/X11 to
GNOME/Wayland for VR work (Monado, `hello_xr`, a Monado build). Resolve's
process survived and `resolve_headless.py status` kept reporting
`running: True, headless: True`, but `scriptapp("Resolve")` hung — so
Hermes's Resolve MCP is **effectively down until Resolve is restarted
under an X11 session**. Not restarted: the GPU was in use for VR at the
time, and Resolve doesn't run under Wayland on that rig.

Two consequences:
- The still-unapplied X11/Wayland session-switch scripts (see "resolve-host
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
| Locating the input video | ~2.5 min (23:21:35 → 23:23:58) | ~9 | Wasted: it grepped `/root/.hermes/cache` for the file, then SSHed to resolve-host to look for it. The video was in `cache/videos` inside the container, then had to be copied to resolve-host. No fixed "where do user uploads land" hint in the skill. |
| Import, timeline, `FlipX` via `set_transform` | ~1.5 min | 6 | The flip itself was applied and read back by 23:25:29, ~5 min into the task. |
| Choosing render settings | ~11 min (23:25:39 → 23:37:06) | ~25 | The real cost. `describe_api`, `list_presets`, `get_resolutions`, `validate_render_settings`, several `prepare_render_job` retries, plus `read_file` on the spillover cache. Typical step 15-37 s (model latency dominates; the MCP calls themselves return in 1-3 s). |
| `prepare_render_job` (final) | hung 286 s | 1 | Never returned; cancelled by an explicit `/stop` from the operator (`MCP call interrupted: user sent a new message`). Resolve itself answered a scripting round trip right afterwards, so this is not the dead-session case above. Suspect: the project is an unsaved `Untitled Project`, and `AddRenderJob` can block on a modal in `-nogui` mode. Not confirmed. |

Totals: 51 model turns, 132 tool turns, ~17 min wall time, **no rendered file**
(`~/output/..._davinci.mp4` does not exist). Average gap between steps
~14 s; the p90 is ~36 s.

What to optimise, in order of payoff:
1. **Give the skill a render recipe.** Hermes spent half the task rediscovering
   which codec/preset/resolution strings the MCP accepts. A short
   `davinci-resolve` skill with one known-good `prepare_render_job` payload
   (H264_NVIDIA, 720x1280, `~/output`) would collapse ~25 steps to ~3.
2. **Save the project first.** A named project avoids the unsaved-project
   modal risk and gives renders somewhere to live.
3. **Say where uploads land and how to hand them to resolve-host** (one `scp` line in
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
| Fallback: ffmpeg NVENC on resolve-host + `ffprobe` check | ~15 s render |
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
  resolve-host against the `MCP-Benchmark` fixture only, not wired into Hermes:
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
human noticing. Three pieces, all on `resolve-host`:

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

**Deployment**: `systemd --user` on `resolve-host`, same pattern as
`fallback_watchdog.py` on VM105 (no `cron`, no sudo needed).
`loginctl enable-linger <user>` was run 2026-10-01 (operator's own root
access, a one-time step) so the service survives a host reboot
unattended. Nothing in this design needs root beyond that one command.

**File transfer stays out of the MCP channel** — SSH/rsync is the right
tool for reliable, resumable, checksummed bulk transfer, no reason to
reinvent it inside MCP messages. Two more dedicated, forced-command keys:

- **Upload**: `command="rrsync -wo ~/resolve-inbox/"` (write-only).
- **Download**: `command="rrsync -ro ~/resolve-outbox/"` (read-only),
  separate directory.

**Pipeline**: Hermes `rsync`s footage to `resolve-host:~/resolve-inbox/<job-id>/`
(upload key) → calls the gateway's MCP tools over HTTP, referencing
`<job-id>` (gateway checks `hardware_status` first, returns "busy"
immediately if unavailable) → import/edit/render writes to
`resolve-host:~/resolve-outbox/<job-id>/` → Hermes `rsync`s the result back
(download key).

**Not decided**: exact skill/request shape on Hermes's side, which
Python framework serves the HTTP endpoint (`mcp` SDK vs. `FastMCP`, not
evaluated), concurrent-job queuing.

### resolve-host session/power config: a reboot resets both (found 2026-10-01, fix not yet applied)

A render job silently failed (`AddRenderJob` → `None`, a tool-reported
`database_attached: false`) after heavy concurrent MCP testing left Resolve
in a crash loop (SIGABRT in `QApplicationPrivate::init`, signal 6 — the
same signature as the original Wayland display-auth crash earlier in this
doc). A full reboot of `resolve-host` cleared the crash loop and confirmed the
database re-attaches fine on a clean boot, but exposed two config gaps
that will keep recurring on every future reboot unless fixed:

- **SDDM autologin is hardcoded to Wayland** (`/etc/sddm.conf`,
  `[Autologin] Session=gnome-wayland.desktop`) — needed for a separate VR
  project that requires Wayland, but it's exactly the display mode that
  crashes Resolve (documented earlier: Wayland's rootless Xwayland hits
  `Invalid MIT-MAGIC-COOKIE-1 key`). Every reboot reverts to the
  Resolve-hostile mode with no prompt. Fix designed, not yet applied —
  two root-run toggle scripts, `/usr/local/sbin/resolve-host-session-x11.sh`
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
  applied: `/usr/local/sbin/resolve-host-performance-mode.sh` (writes
  `performance` to every `scaling_governor`, calls `powerprofilesctl set
  performance`) plus a `oneshot` systemd unit,
  `resolve-host-performance-mode.service`, `WantedBy=multi-user.target`, so it
  self-applies on every future boot without anyone remembering to.

**Also found during the same incident, already fixed**: a raw Python
script invoked directly over the (non-MCP) `resolve-host` SSH key — bypassing
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

### resolve-host: a repeating ~1s alert sound, and three wrong diagnoses before the right one (2026-10-01)

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
3. **The `reverb-g2` VR project** (`~/Documents/reverb-g2`,
   resolve-host's other resident project — an HP Reverb G2 driver/support repo)
   was suspected next, since it ships a deliberate beep-feedback tool
   (`scripts/reseat_audio.py`, played by `voice-guide.py` and
   `drift-measure.py` during headset cable-reseating/drift-measurement
   procedures). Checked and ruled out directly: neither script was
   running, and the three `reverb-g2` processes that *were* running
   (`vr-power-watchdog.py`, `<other-project>-agent.py`, `status-dashboard.py`)
   don't touch audio and don't match the ~1s cadence. (`<other-project>-agent.py`
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

### One Hermes per person: guest instances (2026-10-04, prototype in test)

Decision: each person gets their own Hermes in their own container, so data and
keys are not shared (the shared web UI showed why: anyone with an account could
reach the operator's keys). Default delivery = **a URL + a key** (OpenAI-compatible
API) plus a **dashboard login** where the user picks the model and enters their own
keys (bring-your-own NVIDIA NIM key: free tier, no operator key inside the
instance). **Telegram is optional**. Files: `guests/docker-compose.guest.yml`,
`ops/provision_guest.sh <name> [--nim-key K] [--model p/m] [--telegram-token T
--telegram-user ID]`, per-guest data under `guests/<name>/` (`.env` 0600,
`credentials.txt`).

- What a guest does NOT get: any operator API key (checked: zero of the operator's
  key values present in its env or `.env`), SSH keys, Resolve MCP, an aibridge key,
  or any shared volume (the Telegram Bot API volume is out because its directory
  names ARE the bot tokens; also not the Open WebUI uploads/outputs). Own compose
  project = own docker network. Measured: ~435MB RAM idle, 33s to boot.
- `start_hermes.sh` changes (the main instance was restarted on it and verified:
  Telegram up, `jobwatch` recreated, all keys present, API 200): `.env` is now
  persisted and merged (managed values override only when non-empty, so keys a user
  saves from the dashboard survive restarts; before, it was rewritten from scratch
  each boot); the starting model is seeded on first boot from
  `HERMES_MODEL_PROVIDER/DEFAULT`; the dashboard (`hermes dashboard`, basic auth via
  `HERMES_DASHBOARD_BASIC_AUTH_*`, verified to redirect to `/login`) starts only when
  credentials exist; no `AIBRIDGE_KEY` = standalone instance; `jobwatch` only if
  Telegram is configured.
- **Blocker found and fixed on paper (needs root)**: VM105's `docker-user-fw.sh`
  only let docker subnets 172.17-172.21 out, so a new compose project (172.22) had ALL
  outbound traffic dropped (DNS resolved, connections died: Hermes "APITimeoutError"
  to NIM while the same call worked from the main instance and from outside). The
  updated `docker-user-fw.sh` gives guests the supernet 172.28.0.0/16 (one /24 each,
  chosen by `provision_guest.sh`): internet yes; LAN, RFC1918, other docker networks
  and the host itself (INPUT) no. Applied and validated (2026-10-05, see below).
- Still open: dashboard
  model picker and key entry exercised by a person in a browser, per-guest edge domain
  (`herand`), resource budget (VM105 has 5.9GB: ~2-3 more instances), 24/7 cost of
  idle guests.

### Job portals for a person: web access that actually works (2026-10-05)

The herand tester hit two errors on `herand`. (1) *"missing FIRECRAWL_API_KEY"*: with no web backend configured Hermes defaults
to Firecrawl, which needs a key. Fix: `web.backend: keenable` (keyless search + fetch), seeded on first boot of a
stack (`HERMES_WEB_BACKEND`) and set live on `herand`; `web_search` verified. Hermes's `web_extract` is NOT enough for
job portals (ZonaJobs returned an error page) and its `browser_*` tools get **"Sorry, you have been blocked" from
Cloudflare** on ZonaJobs (default headless fingerprint). The image's own Chromium with a normal fingerprint (UA,
es-AR locale, Buenos Aires timezone, no `webdriver` flag) reads ZonaJobs, Bumeran, Computrabajo and LinkedIn jobs.
So two commands ship in the image: `browse-page <url> [--links] [--scroll N]` (generic reader; reports
an explicit anti-bot warning instead of faking content) and **`buscar-empleos "<words>" [--zona X] [--n 6]`**, which
searches the four portals one at a time (ZonaJobs and Bumeran loaded together made one come back empty; one retry)
and prints postings with URLs in ~25s. Verified URL recipes live in `SKILL_job_search.md`.
Why a command and not just a skill: given "go to ZonaJobs" the free model improvised (wrong URLs, blocked tools) and
took **217-329s**; with `buscar-empleos` named in the preset's system prompt (`JOBS=1`, set by `provision_stack.sh
--jobfinder`) the same request took **34s** with the same three real postings. Not a stealth tool: one page at a
time, no login bypass, no CAPTCHA solving; sites can still block.

(2) *"Response payload is not completed: TransferEncodingError"*: Open WebUI lost the stream because Hermes's
gateway was restarted mid-response. The cause was ours: the keys page restarted the gateway after every key/model
change, and several container recreations during testing happened while the person was using it. Verified that
Hermes **hot-reloads** both (a bad key at priority 0 was tried, got 403, and Hermes rotated to the next one in the
same turn; a changed model applied to the very next request), so the keys page no longer restarts anything. Rule for
operators: do not recreate a live person's container to ship a file; `docker cp` the file (skills and scripts are read
at use) and restart only the helper process (e.g. `keys_server.py`), leaving the gateway alone. Rebuild the image
afterwards so the next natural recreate matches.

### Keys page + welcome banner for per-person stacks (2026-10-05)

A new person has no LLM key, and Hermes cannot answer without one, so keys cannot be entered by
chatting. `keys_server.py` + `keys_page.html` (inside the Hermes container, port 8700, enabled by
`HERMES_KEYS_UI=1`) serve **`/keys/`** through the stack's nginx, behind the Open WebUI login
(`auth_request`) and, on top, the server re-checks with Open WebUI that the caller has the **admin**
role (a second account gets 403). POSTs need an `X-Keys: 1` header. No key is ever logged or returned
(last 4 only) and it never touches the chat history. Flow: paste a key -> listing check -> a real
one-token chat call to the chosen model -> only then `hermes auth add --type api-key --priority 0
--label web-<date>` (Hermes's own credential pool, persisted in `auth.json`) -> gateway restarted so
it is picked up. Providers: NVIDIA NIM (recommended, free), OpenRouter, Google Gemini, Hugging Face.
Also: change the active model (`hermes config set model.*`), and remove keys loaded from the page
(never the environment ones). The "change model" list is **probed**: NIM lists 81 models but only ~5
of 16 candidates answered on the free account, so the page shows only models that actually respond.
Verified on `herand`: no session 401, non-admin 403, missing header 400, fake keys rejected with the
right message (NVIDIA 403, OpenRouter 401, Gemini 400) and nothing stored, valid key stored in 7s,
survives recreating the container, model switch and refusal of an unavailable model, removal.
Lessons: NVIDIA's and OpenRouter's `/models` are public, so a bad key still gets 200 there: validity
comes from the chat call, not the listing; Gemini answers 400 (not 401) for a bad key.
The operator's temporary NIM key in a stack's env stays as priority 1 behind the person's own one;
drop it from `stacks/<name>/.env` once the person has loaded theirs.
The welcome banner (`ops/welcome.es.md`, set by `openwebui_setup.sh` with `WELCOME=1`, which
`provision_stack.sh` does) tells the person where to get a key and links `/keys/`. Not seen
rendered in a browser (the person's login is theirs); content and links verified through the API.
Not enabled on hernik (its keys come from the operator's environment).

Host-side firewall bug found while testing: the INPUT DROP for the guests' network also dropped the
*replies* to connections VM105 itself opens to a guest's published port, so `curl` from VM105 to a
stack's web port timed out while the LAN got 200. `docker-user-fw.sh` now accepts ESTABLISHED/RELATED
first. **Applied and validated 2026-10-05**: installed script identical to the repo; VM105 reaches
<docker-host-ip>:3000/:3001 (200); from the herand container 172.28.1.1:22, host 22/3000/3001/8642 and
the router are closed, only the internet is open (NIM answers 200). Install command, for a future
change: `sudo install -m 755 ~/aibridge/docker-user-fw.sh /usr/local/sbin/ && sudo systemctl restart
docker-user-fw.service`. Note: stack web ports are published on the LAN IP only, so 127.0.0.1:3001
does not answer (expected).

SSH on VM105: `PasswordAuthentication yes` is in effect through `/etc/ssh/sshd_config.d/60-pwauth.conf`
(since 2026-07-21, operator's choice; overrides the `no` in sshd_config). Nothing in bridgeai depends on
it; key login works. To harden: delete that file and `systemctl reload ssh`.

PDF/DOCX upload 503 (2026-10-05, reported by the herand tester): Open WebUI `main-slim` ships no document extractor, so
`process_file` raised "503: This file type requires an external document extractor in slim" and the UI refused the
file. Fix without another container or a heavy image: `aibridge/doc_extractor.py` (started by `start_hermes.sh` next to
the keys server, port 9998, inside the stack's Hermes container) speaks the Tika protocol (`PUT /tika/text`), using
`pdftotext` for PDFs and zip/XML parsing for DOCX/ODT (it sniffs the type: Open WebUI sends no Content-Type; no pandoc
in the image). `ops/openwebui_setup.sh` (`DOC_EXTRACTOR_URL`, set by `provision_stack.sh`) switches the engine to
`tika` and turns embedding/retrieval off (`BYPASS_EMBEDDING_AND_RETRIEVAL`), since Hermes reads the real file anyway.
Verified on herand with a real PDF and DOCX (status `completed`, text extracted); applied live with `docker cp` +
config API, no container recreated. Scanned PDFs come back as a note (the agent can OCR with tesseract); other types
(xlsx, pptx, images) are still rejected with a clear error. **hernik is not covered yet** (its image has no extractor):
needs its next image rebuild plus `DOC_EXTRACTOR_URL=http://hermes-agent:9998 ops/openwebui_setup.sh`.

Resuming where a person left off (2026-10-05): checking herand showed that what Hermes *learns about a person*
was not persisted, only sessions/config/keys were: `~/.hermes/memories/` (USER.md, MEMORY.md) and `skills/` (e.g.
the `job-portal-scraping` recipe Hermes wrote and patched itself) would be lost on any container recreate or image
change. Now `memories` is in PERSIST_PATHS and `skills/` is synced out every 30 s and restored **without
overwriting** (`cp -n`) so newer skills baked into the image still win. Current herand memories/skills were copied into
`/hermes-persist` by hand (no restart); the image was rebuilt so the next restart has it. Not persisted on purpose:
cron jobs (Hermes-created schedules are lost on recreate; re-create them), logs, caches. Added
`ops/backup-stacks.sh` + user timer `backup-stacks.timer` (daily 04:15, keeps 7): one `~/backups/<stack>-<stamp>.tar.gz`
per stack with persist/ + workdir/ + owui-data/ (chat history, accounts, memories, jobfinder data), written 0600 into a
0700 dir, since some files are root-owned it runs through a throwaway busybox container. First run: herand 36 MB.
The archives hold personal data and API keys: do not copy them off the VM unencrypted. Restore = stop the stack,
untar into `stacks/<name>/`, start. Also removed seven stray files my own network probe had left in herand's `/workdir`.

FOLLOW-UP (resume here): herand is with its tester; her feedback decides what comes next. When it arrives,
first check: (1) did she load her own NIM key at /keys/ (then drop the operator's `NVIDIA_API_KEY` from
`stacks/herand/.env`); (2) jobfinder has no `cv.md`/`config/profile.yml` yet, only examples; (3) PDF/DOCX uploads
and `buscar-empleos` in real use; (4) `docker logs stack-herand-hermes` for errors; (5) the 04:15 backups exist in
`~/backups`; (6) Hermes-created cron jobs are not persisted. Reminder to the operator: follow her feedback closely.

Deploy status (2026-10-05): **herand is deployed and live** on its own public domain through the edge VM
(Let's Encrypt, CORS matches, web port 3001 behind it); the herand tester is testing it and will send feedback.
Public domains of the per-person stacks are deliberately NOT kept in this repo (privacy): they live in each
stack's untracked `.env` (`PUBLIC_HOST`; for hernik `HERNIK_PUBLIC_HOST` in `aibridge/.env`), and
`ops/provision_stack.sh` takes `PUBLIC_DOMAIN` from the environment. Docs use `<hernik-domain>`.

Open items at close (2026-10-05): the herand tester loads her own NIM key at /keys/, then remove the temporary
operator `NVIDIA_API_KEY` from `stacks/herand/.env`;
staged `file://` outbound path still unverified with a real Telegram send; do not recreate a live
person's container (ship hotfixes with `docker cp`; Hermes hot-reloads keys/models).

### Per-person web stacks: `herand` (2026-10-04)

`ops/provision_stack.sh <name>` creates a full stack like hernik for another person
(`stacks/docker-compose.stack.yml`): own Hermes + Open WebUI + nginx + Piper TTS, own data
under `stacks/<name>/`, own docker network (a /24 of 172.28.0.0/16), none of the operator's
keys (checked on `herand`: 0 operator key values in its env), no SSH/Resolve/aibridge, no
shared volumes, and it cannot resolve hernik's containers. Same preset as hernik (files,
PDF, Mermaid, vision, private model). Differences on purpose: STT is the browser's (no key)
unless the person adds their own, because a Groq key stored in their Open WebUI would be
readable by them; the LLM key is theirs (NVIDIA NIM free), entered in the Hermes dashboard
(`stacks/<name>/credentials.txt` has the logins; web port is what the edge VM proxies).
`herand`: web `<docker-host-ip>:3001`, dashboard `:9130`; ~830MB RAM for the four containers.
Verified: login, signup closed (403), files 401 without session, model with vision. **Not
verified**: any LLM call, because outbound traffic from the 172.28 network is dropped until
`docker-user-fw.sh` is applied (needs root, see the guest section). The cleanup timer does
not yet prune `stacks/*/web-outputs`.

### Job search for a person: jobfinder in `herand` (2026-10-04)

The operator's career-ops fork (`~/Documents/jobfinder`) is installed for one person in
`stacks/herand/workdir/jobfinder` (persistent volume, never leaves that instance).
`ops/make_jobfinder_bundle.sh` (desktop) packs only git-tracked system files (+ the
untracked system mode `watch.md` and `package-lock.json`); the operator's user layer is
gitignored and not packed (cv.md, profile.yml, portals.yml, `modes/_*.md`, data, jds,
output, local, interview-prep) and the script aborts if personal strings leak (checked: the
installed tree has none). `ops/install_jobfinder.sh <stack> <bundle>` unpacks it and runs
`npm ci --ignore-scripts` with Hermes's own Node (no Playwright download; refuses to
overwrite a tree that already has the person's `cv.md`/`profile.yml`);
`provision_stack.sh --jobfinder <bundle>` does both. `node doctor.mjs` runs and reports
exactly what a new person must still provide (CV, profile, portals): that is the
onboarding, driven by the `job-search` skill (`SKILL_job_search.md`, baked into the
image), which tells Hermes to read the system's own `AGENTS.md` and router, where files
go (web-interface rules), and the integrity rules (never invent experience).
- Gaps found by doctor: Node 20 in the image (tracker SQLite index needs >= 22.5; Hermes
  carries Node 26 under `~/.hermes/tools/`, optional); **Chromium was missing**, now baked
  into the base image (`playwright@1.63.0`, `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`,
  same version as the jobfinder's lockfile): base image 3.2GB -> 4.4GB.
- The person's LLM key: `herand` got the operator's NVIDIA NIM free key as a temporary
  working key (revocable at build.nvidia.com); the OAuth sessions Hermes holds for Nous and
  Codex (`auth.json`) were deliberately NOT copied, as they are logins to personal accounts.
  Replace with the person's own key in the dashboard. Still needs the firewall change
  (guest section) before this instance can reach any API.

### Third instance `hereug`, key onboarding, and what the usage report showed (2026-10-05)

`hereug` is the third per-person stack (web `:3002`, dashboard `:9131`, own /24), created with
`ops/provision_stack.sh`; the person already had a career-ops checkout on another VM, and its user layer
(`cv.md`, `config/profile.yml`, `portals.yml`, `modes/_*.md`, `voice-dna.md`, `data`, `reports`, `output`, `jds`,
`interview-prep`, `documents`, `writing-samples`) was migrated into `workdir/jobfinder` with `cp -an` (never
overwriting; the old tree stays as a backup; no tokens or SSH keys copied). Lessons that apply to every per-person stack:

- **No Docker inside the Hermes container.** Upstream jobfinder's `./cops` drives `docker compose` and fails there.
  `ops/cops-nodocker` has the same interface but runs `npm run <script>` / `node` directly; `install_jobfinder.sh` now
  installs it over `cops`. (The base image already ships Chromium, `/opt/ms-playwright`; an earlier note here saying
  otherwise was wrong, and `generate-pdf.mjs` works as is.)
- **PDF recipe that works:** the agent writes a JSON payload -> `node build-cv-html.mjs payload.json output/cv-<n>.html` ->
  `node generate-pdf.mjs output/cv-<n>.html output/cv-<n>.pdf --format=a4` (there is no `pdf.mjs`; the flag needs the `=`),
  then copies it to `/web-outputs/<dir>/` and links `/hermes-files/<dir>/<file>`.
- **Why a person got text instead of a PDF:** with an attachment, Open WebUI wraps the message in its RAG template
  ("respond to the user query using the provided context") and the agent answered with text only, never reaching the tools.
  Replacing the template with one that says "you are an agent: produce the file and link it" fixed the prompt side (applied to
  `herand` and `hereug`; keep a backup of the original). Free models still sometimes write an example id in the link instead
  of the real directory; the skill now says to confirm it with `ls`.
- **Skills live in the container and sync OUT to `persist/` every ~30 s.** Editing `persist/skills/...` from the host is
  overwritten; write the live copy (`docker cp`), then check the persistent copy matches. The agent also edits its own
  skill and can invent things (a recipe using the non-existent `pdf.mjs`): review before copying to other instances.
  The `job-search` skill is kept identical across `herand` and `hereug`.
- **Changing the model needs a Hermes restart.** `hermes config set model.*` rewrites `config.yaml`, but the running gateway
  keeps the old model: after switching `hereug` to OpenRouter its sessions were still billed to the old provider until
  `docker restart stack-<name>-hermes` (up again in ~18 s; it cuts turns in progress). Keys are picked up hot; the model is not.
  (This corrects the "Hermes hot-reloads keys/models" remark above.)
- **Onboarding for a new person is a guide, not a chat:** `ops/KEYS_GUIDE.{es,en,ru}.md` lists where to get a key ordered
  simplest to most involved (OpenRouter, Gemini, Hugging Face, NVIDIA NIM, then paid; NVIDIA requires phone verification) and how
  to load it at `/keys/`; the welcome banner (`ops/welcome.es.md`) carries the same ordered list. Source of truth for providers,
  links and prefixes is `keys_server.py` (`PROVIDERS`); keep the three guides in sync with it.

**`ops/keys_usage.py`** (run as root on the Docker host; `--days`, `--json`, `--no-live`) reports per instance: configured
provider/model, credentials (label and last 4 only), sessions, model calls, tokens by model, activity per day and hour, and for
OpenRouter the live state of each key (free-model requests used today, USD usage, credit, expiry). It warns about keys expiring
within 72 h, <= 10 free requests left, and **drift** (last session billed to a provider other than the configured one: this is how
the missing-restart problem above was found). What can and cannot be measured: Hermes's own counters
(`session_model_usage`, `sessions`, `messages` in `state.db`) exist for every provider but show consumption, not what is left;
a remaining quota exists only where the provider has an API (OpenRouter `/auth/key` and `/credits`); NVIDIA, Gemini and Hugging Face
expose none for a plain key.

First real numbers (7 days, 2026-10-05): about 10.5 model calls per session on `herand` and `hereug` (14.6 on hernik); mean input
~6.5-6.7k tokens per call on the per-person stacks (~8.9k on hernik), with prompt caching doing most of the work (`hereug`: 7.2M cached
tokens read vs 1.07M fresh input). A one-word "ok" through Open WebUI costs ~14k prompt tokens (system prompt + skills + memory).
OpenRouter's free tier is **50 requests/day** (`free_model_daily_requests`), and each model call counts as one, so a free key sustains about
**5 sessions a day**; buying credit raises the cap (the value could not be read from the API). The first OpenRouter key of the person on
`hereug` also **expires after ~2 days** (`expires_at`): ask for a non-expiring key.

### Free-tier wall and `ops/model_guard.py` (2026-10-05)

`hereug` stopped answering and then `hernik` fell off its fallback chain. Causes found:

- OpenRouter's free tier is 50 requests/day **per key, shared by every `:free` model**, so a fallback chain made only of
  OpenRouter free models (hernik's tail: gemma, qwen, nemotron `:free`) is one single point of failure.
- A fallback entry can be skipped as `Fallback skip: ... credential pool is exhausted (every entry in cooldown)` while
  `auth.json` is clean and a fresh Python process sees the credential available (checked with `load_pool(...).has_available`).
  A restart did **not** clear it in hernik (it reappeared 3 minutes after), so the cause is not established: do not assume a
  restart fixes it. Chains also held dead entries (Hugging Face 402, Nous quota) that were tried before good ones.
- **A persisted `/model` override beats `config.yaml` and the guard.** The Telegram DM kept `/model deepseek/deepseek-v4.1-flash`
  (provider nous, a paid model, no credits -> `404 insufficient_credits_for_paid_model`) and the gateway logs
  `Rehydrated persisted /model override for session=...` on every restart. Clear it with `/model` in that chat (pick a working
  model) or `/new`; the guard cannot see it because it only edits `config.yaml`.
- **A key that exists only as a container environment variable is not "connected" for the running gateway.** In hernik
  `NVIDIA_API_KEY` (and `GEMINI_API_KEY`) were in the container env (and in `/proc/<gateway>/environ`) but not in
  `/root/.hermes/.env`, which holds the keys Hermes actually uses (`GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, `HF_TOKEN`). The pool
  entry is `source: env:NVIDIA_API_KEY` with no secret stored. A fresh `docker exec` python process resolved it fine (so
  `model_guard.py` probes and a manual `load_pool` looked healthy), while `/model nvidia` in Telegram answered
  `Nvidia is not connected: no API key or login was found for it`, and the fallback entry was skipped as "exhausted".
  Fix: `hermes config set NVIDIA_API_KEY "$NVIDIA_API_KEY"` inside the container (writes `.env`, which syncs to `persist/`).
  Hypothesis, applied 2026-10-05: confirm with `/model` in the chat, and restart if the gateway does not pick it up hot.
  Never validate a key with a fresh `docker exec` process alone: use the gateway's own answer.
- Order matters at restart: `hermes config set` must reach `persist/` (~30 s sync-out) **before** `docker restart`, or the old
  `config.yaml` is restored and the change looks ignored. The per-session `/model` pin in Telegram is separate from `config.yaml`.

`ops/model_guard.py` (dry run by default; `--apply`, `--restart`, `--only <container>`; docker only, no sudo, keys never leave
the container) probes the catalog with a 1-token call per entry, keeps only HTTP 200, switches the primary when it fails or has
>= 3 recent 429/402, rewrites `fallback_providers` with healthy entries only and restarts only when the primary changed.
OpenRouter free is probed only when nothing else is healthy. `model-guard.{service,timer}` (user units, every 5 min, flock,
log in `~/model_guard.log`). `herand`/`hereug` share the operator's NVIDIA key and have no second provider, so for them the
guard can only report: they need their own key plus a second provider.

### Key failures are never silent (2026-10-09)

Incident: the operator's Groq key expired; voice notes silently stopped being transcribed and the agent told the user
"no STT installed" (and even saved that as a memory). A dead key must be loud and must name itself.

`aibridge/ops/key_check.py` (user timer `key-check.timer`, every 30 min, no sudo) collects every key each stack can use
(Hermes `.env`, container environment, and the person's saved keys in `auth.json` `credential_pool`), asks each provider
a free read-only question (Groq, NVIDIA, Gemini, Hugging Face, OpenRouter) and treats only 401/403 as "dead" (network
errors and 429 are "unknown": nobody is paged for a flaky link). When a key turns bad it says WHICH one (provider, last
4 characters, where it lives, what stops working):

- **Telegram**: the stack's own bot to its allowed users; a failure in any other stack also reaches the operator through
  hernik's bot, prefixed with the stack name. Repeats every 24 h while it stays bad.
- **Web**: a non-dismissible warning banner `key-alert` in that stack's Open WebUI, removed when all keys are fine
  (other banners such as the welcome one are kept). Open WebUI sleeps with its stack, so it is re-applied on each check
  where it is reachable.
- **On every wake**: `ops/wake/on_wake.d/10-key-check` runs `key_check.py --wake --stack NAME` once Hermes is ready, so
  a person who walks in with a dead key is told immediately, on the chat that woke it.

State: `~/.local/state/key_status.json` (no keys, only provider + last 4). `key_check.py --dry-run` prints without sending.
Renewing a Groq key: new key in `~/aibridge/.env`, then recreate the brain **while it sleeps**
(`docker compose up -d --no-deps --no-start hermes-agent`): the container env wins over its `.env` at every boot.
Local `faster-whisper` as STT fallback was measured and rejected as default: `small` = ~850 MB RAM, and short es/ru
clips are misdetected as Norwegian/Swedish because Hermes takes one fixed language hint.

### Model and key policy: the same for every person (design + status, 2026-10-05)

**Target behaviour (agreed with the operator).** Identical for every stack, each with the person's own keys:

1. **Preferred model first**, then the **fallback chain** in order. The preferred one is *not defined yet* (open decision below).
2. If the active provider is exhausted, or **about to be**, switch by itself to the next healthy one **and tell the person**
   (one line in the chat: from what to what, and why).
3. **A model the person chose themselves** (today only possible with `/model` in Telegram) is respected: it stays until its
   tokens run out, or until we know very little is left; only then it moves to the next provider (and says so).
4. A **coding model** (e.g. Claude, Gemini) as an extra, used for programming tasks, not as the general default.
5. The Web UI shows a single model, **"Hermes"**, on purpose: Open WebUI talks to one Hermes API and the choice of
   provider/model happens *inside* Hermes (config + fallback chain). Listing providers in the web picker would not change
   anything; a person-chosen model there is a separate feature (see "Not built yet").

**Where each part lives**

| Part | Mechanism | Status |
|---|---|---|
| Preferred + fallback order | `model.provider/default` + `fallback_providers` in the person's `config.yaml` | works; chain rewritten by `ops/model_guard.py` |
| Never try a dead entry / never skip a healthy one | guard probes each catalog entry, keeps HTTP 200 only | works (every 5 min, all stacks) |
| Switch when the primary fails | guard: probe fails or >= 3 recent 429/402 -> `hermes config set` + restart | works; reacts to errors, not to remaining quota |
| Switch when a **pinned** `/model` fails | Hermes itself (`Primary X rate-limited ... staying on fallback Y`) as long as the chain is healthy; the guard reports pins that do not answer | partly: reported, not auto-cleared |
| Keys actually connected for the gateway | guard syncs env-only keys into Hermes `.env` (all stacks, idempotent) | works |
| Tell the person about a switch | Hermes prints `Model fallback: A -> B (reason)` in the chat when it falls back at run time | exists for run-time fallbacks; **not** for the guard's config switches |
| Switch *before* the wall (remaining quota) | needs per-provider remaining-quota readers | only OpenRouter exposes some (`/auth/key`, `/credits`); NVIDIA/Gemini unknown |
| Coding model | a second role/catalog | not built |

**Decided 2026-10-05: preference order = `CATALOG` order in `ops/model_guard.py`: NVIDIA NIM first, Gemini as fallback**
(Gemini spends paid tokens, NIM does not). The guard now makes the first *healthy* catalog entry the primary and switches back
to it when it recovers (restart on a change). Applied to hernik (it was on Gemini); herand and hereug only have NVIDIA.

**Releasing a pinned `/model` without Telegram** (hernik had `deepseek/deepseek-v4.1-flash` via Nous, no credit, rehydrated on
every restart): the official `/model <model> --global` in the chat clears it; from the host, with the gateway's own venv python,
`SessionStore(Path("/root/.hermes/sessions"), load_gateway_config()).set_model_override("agent:main:telegram:dm:<chat id>", None)`
(read it first with `get_model_override`), then restart so the running gateway drops its in-memory copy. Verified: the override
is gone from `sessions.json` and the restart logged no `Rehydrated persisted /model override`.

**Not built yet / decisions pending (operator)**
- **Preferred model per person** and the order of the chain (global order is decided above; per person is not). Suggestion to decide: general = the provider with the largest
  verified quota; OpenRouter `:free` last (50/day shared); a paid model never as an automatic fallback without the person's say.
- **"Soon" threshold** (e.g. N consecutive 429, or X% of a known cap) and the **notice channel** (chat message from the guard,
  not only `~/model_guard.log`).
- **Coding model**: which provider/model (Claude via its own key, Gemini), and how Hermes selects it (a task-type rule, a slash
  command, or a second preset). Needs each person to have that key.
- **Pin lifecycle**: when a pinned model must be left (hard failure vs "little left"), and clearing/rewriting the pin in
  `sessions.json` `model_override` (the gateway holds it in memory and rehydrates it on restart, so it cannot be edited safely
  from outside while running).
- **Per-person catalog** (today one global `CATALOG` in `model_guard.py`; a person with different keys only gets probed on the
  entries whose key exists in their container).
- A person-chosen model from the Web UI.

**Rules every new stack must satisfy** (check with `python3 ops/model_guard.py`, dry run): a probe `200` for each provider they
loaded; no key left only in the container env (the guard syncs it); a chain with at least two independent providers; no pin
pointing to a provider that does not answer. While `herand`/`hereug` use the operator's NVIDIA key it lives in **two** places
(`stacks/<name>/.env` and the container's Hermes `.env`): remove both when the person loads their own.

### Principle: each person runs their own key set; limits are verified per provider (2026-10-05)

**Rule.** Every person's stack holds only that person's keys (loaded at `/keys/`). The operator's keys are a temporary bridge
(today `herand` and `hereug` still use the operator's NVIDIA key: remove it once they load their own). A limit is never assumed:
each provider's cap is **measured or read from its own error/API**, written down here with how it was observed, and anything
not yet observed is marked *unverified*. A person with a single provider has no safety net, so onboarding should give them at
least two independent ones (see `ops/KEYS_GUIDE.*.md`, ordered simplest to most involved).

**What we know (observed, 2026-10-05)**

| Provider | Limit / failure observed | How it was seen | Can the key's usage be read? |
|---|---|---|---|
| OpenRouter free (`:free`) | 50 requests/day per key, **shared by all free models**; resets 00:00 UTC; 10 credits raise it to 1000/day. Error `429 free-models-per-day`. | `X-RateLimit-Limit/Remaining/Reset` in the 429 | Partly: `/auth/key` and `/credits` (used by `keys_usage.py`); the free-request counter only through the 429 headers |
| Hugging Face router | `402` when the account has no credit left | probe | Not observed |
| Nous Portal | quota-exhausted state with a reset time (`rate-limited until ...`) | Hermes log / `auth.json` | Reset time only |
| NVIDIA NIM | no daily cap seen so far (a 1-token call is 200 in ~1 s); per-minute limit and behaviour under shared use **unverified** | probe | Not observed |
| Gemini (free key) | per-day/per-minute quota **unverified** (not hit yet) | probe | Not observed |

When a new provider is added, add its row here from a real observation (a probe, the 429/402 body, its headers) before relying
on it in a chain.

**How each person can consult their own usage** (give them these, do not ask them to read logs):
1. Provider dashboard of their own account (the links per provider are in `ops/KEYS_GUIDE.{es,en,ru}.md`).
2. The `/keys/` page of their stack, which shows which keys are loaded (label and last 4 only).
3. The operator runs `ops/keys_usage.py` (needs root on the Docker host) for sessions, calls, tokens by model and the live
   OpenRouter state, and `ops/model_guard.py` (dry run, no sudo) for "which of this person's providers answer right now".

**Automatic behaviour per person.** `ops/model_guard.py` already works per instance: it probes with the keys *inside that
container's own environment*, so each person is judged only on what they actually loaded, and it rewrites that instance's chain
with the healthy entries only (see the section above). Open items: a per-person catalog (today one global `CATALOG`), reading the
remaining quota where a provider exposes it instead of reacting to the first 429/402, and a message to the person (not only the
operator's log) when their only provider is failing.

### Web UI: PDF delivery that actually links (2026-10-05, herand)

The herand tester asked for her CV PDF and got no link, while `hereug` worked. The file was fine (generated, in `/web-outputs`, readable
by nginx, same permissions as hereug); the **answer** was wrong, in three successive ways with the same model
(`nemotron-3-super`): a bare path `/web-outputs/<d>/x.pdf`, then bare text `/hermes-files/<d>/x.pdf` (Open WebUI only makes
`[name](url)` clickable), then a proper markdown link to a folder it never created (`/hermes-files/root/x.pdf`, 404) because
it found the file in `/root` and linked it without copying. Longer skill wording did not fix the third case.

Fix that held: **`ops/deliver <file>`** (installed as `/workdir/deliver` by `install_jobfinder.sh`) copies the file to
`/web-outputs/<random>/`, `chmod 644`, and prints the markdown link; `SKILL_web_interface.md` says "run it and paste its
output, never build the link by hand", and herand's `MEMORY.md` (injected on every message) carries the same rule. Verified
in the real UI (Open WebUI, new chat): a clickable link, PDF opens. Also noted in the skill: `uuidgen` is not installed
(use the python one-liner); a failed `uuidgen` plus an approval prompt that timed out after 301 s is what made the first
attempt improvise.

Operational finding: **herand's container predates the `skills/` sync-out loop** (up since 00:34, old `start_hermes.sh`),
so skill edits there do not reach `persist/` until `docker restart stack-herand-hermes`; copy by hand
(`docker exec ... cp -a ... /hermes-persist/...`) meanwhile. hereug syncs. Diagnosing this from the host: the session text is
in `state.db` (`strings state.db state.db-wal | grep ...`); the API on `:8642` inside the container takes the key from
`/root/.hermes/.env` (`API_SERVER_KEY`) and lets you reproduce a request without the UI. Switching herand to OpenRouter like
hereug is deferred until she has her own keys.

### herand: "I cannot access external domains" (2026-10-05)

Symptom: asked to improve her CV, the agent said it could not find `/hermes-files/<id>/person_cv.pdf`, and when the herand tester showed the
public link it answered "no puedo acceder a dominios externos... solo tengo acceso al sistema de archivos local". Diagnosis:

- **Network was fine.** From the herand container `curl` to example.com / google / a job portal returns 200, `browse-page` on a
  job board returns 200, and the web, browser and terminal toolsets are enabled. Its own public domain answers **401** (the
  edge asks for the login), which is reachable-but-unauthenticated, not "no internet".
- **The agent mixed up a URL with a path.** `/hermes-files/<id>/<file>` is the web URL; on disk it is `/web-outputs/<id>/<file>`
  (`/hermes-files` is not a folder). It then saved the wrong path in its own memory (`MEMORY.md` and `USER.md`) as the place of her
  CV, so every later session failed the same way, and generalised the failure to "no external access". Its memory also said
  job search "requires API keys (FIRECRAWL...)", which is false here (`browse-page` works).
- Related and unchanged: on the `api_server` platform (what Open WebUI uses) Hermes treats the session as unattended and
  **denies `execute_code`** (and anything that needs an approval) instead of asking. hernik allows it through
  `command_allowlist`; herand and hereug do not, deliberately: the PDF recipe needs only `terminal` (node, curl, python3 files).

Fix: herand's `MEMORY.md`/`USER.md` corrected (backups `*.bak-20261005`, copied to `persist/memories`) with two explicit rules
(**you DO have internet**; **a `/hermes-files` link maps to `/web-outputs`**) and the real CV paths. Her CV and its `.md` now
live in `/workdir/jobfinder/output/` because `/web-outputs` is pruned after about a day. The same two rules are now in
`SKILL_web_interface.md` (installed live in herand and hereug, persist copy verified). Verified with a fresh conversation:
the agent read the CV from the quoted link and confirmed it has internet. Second round (same day): it kept saying "I can only access files under /hermes-files, /openwebui-uploads or /web-outputs".
That came from the **Open WebUI preset prompt** (`ops/openwebui_setup.sh`, injected on every message), which listed only those
three folders as the agent's world; the model read it as a restriction. The preset prompt now says the folders are where files
live, not a limit, that it has internet, and how a quoted `/hermes-files` link maps to disk; reapplied to herand, hereug and
hernik (hernik's preset was the untouched base prompt), and the skill got a rule that names the wrong sentence. Verified through
Open WebUI in a fresh chat: it read the CV from the quoted link and returned two real job offers from the internet.
Lesson: when an agent reports a capability it
lacks, test the capability from the container before touching the network or firewall; the cause is usually a bad belief
saved in its memory or an instruction that lists what it *has*, which it reads as what it is *limited to*.

### Trusted users: what every person's Hermes may do, and what stays blocked (2026-10-05)

The three people on this system (hernik, herand, hereug) are trusted. Every stack must let them browse the internet, handle
files, run commands and run code from the web chat, and answer them in rioplatense Spanish (voseo) when they write Spanish.

**Why the web chat was restrictive.** Open WebUI reaches Hermes through its `api_server` platform, which Hermes classifies as
"unattended": nobody can answer an approval prompt, so anything needing approval is **denied** (`BLOCKED: ... unattended platform
(api_server)`), `execute_code` included. Only hernik had a partial exception (`command_allowlist: execute_code`). That is a
safety default for a webhook, not a statement about these users.

**Setting (all three, 2026-10-05):** `approvals.unattended_mode: approve` in each `config.yaml` (applied by the operator with
`hermes config set`, persisted to `persist/`, picked up without a restart; verified by running `execute_code` from the chat in
herand and hereug, which returned the right result with no `BLOCKED`). New stacks get it on first boot from `start_hermes.sh`
(`HERMES_UNATTENDED_MODE`, default `approve`, `deny` reverts); it only reaches a new stack once the image/script includes it.

**Still blocked whatever the setting is** (Hermes enforces them before any approval mode): hardline catastrophic commands,
deleting the interpreter/venv Hermes runs from, `sudo -S` password guessing, and any operator `approvals.deny` rules. Isolation
is the other half: each person has their own container, own keys and own volume, so "trusted" never means "can touch someone
else's data or the operator's keys". The remaining boundary is that container.

**Tone.** The Open WebUI preset prompt (`ops/openwebui_setup.sh`) tells the agent to talk in voseo when the user writes Spanish,
to do the work instead of explaining why it could not, and that it may use terminal, code, internet and files freely. Reapply
with the same invocation `provision_stack.sh` uses (the script is idempotent). The model still drifts to neutral phrasing now
and then; the instruction lowers it, it does not guarantee it.

Check for any stack: `execute_code` from its chat returns a result; `browse-page https://example.com` returns 200; no
`BLOCKED: execute_code` in `docker logs`.

### Speed, resources, model benchmark and hallucination log (2026-10-06)

**Is it CPU or RAM?** VM105 has 4 vCPU (AMD FX-8320E, old) and **5.9 GB RAM** for three Hermes, three Open WebUI, the TTS, the
Telegram Bot API and other projects. CPU is idle (load 0.4): the models run in the cloud. **RAM is the tight resource**: ~3.4 GB used,
~2.5 GB available, ~1 GB of 2 GB swap occupied (no swap traffic and memory PSI at 0 when measured, but Hermes logged
`system memory pressure is elevated` earlier). Each Chromium launch (`browse-page`, playwright) adds several hundred MB, and hernik's
new image now ships Chromium too. Recommendation: raise VM105 to **8 GB or more** in Proxmox. **Done 2026-10-06 (operator): the VM now sees ~7 GB**; after the
reboot swap was at 0 and ~3.4 GB were available. Container caps were raised to match, live with `docker update` (no restart) and in
the compose files so a recreate keeps them: Hermes of each person's stack **1.5 -> 2.5 GB** (`stacks/docker-compose.stack.yml`, so new
stacks get it too) and hernik's Hermes **3 -> 3.5 GB**. Open WebUI (~250 MB used of 1.5 GB) and the TTS were left alone. The caps add up
to more than the RAM (3.5 + 2.5 + 2.5 + the rest) on purpose: they bound a runaway process, they do not reserve memory; observed peaks
are 0.8-1.3 GB per Hermes. Watch `free -m` and `/proc/pressure/memory` if all three run Chromium at once.

**What slows a turn down (from `agent.log`, per model call):** `nemotron-3-super` on NVIDIA has median **4.6-5.7 s**, p90 15-18 s, max
197 s, with **~46-75 % of its output tokens being hidden reasoning** (e.g. 198 946 of 263 318 in hernik). The same model through
OpenRouter free is faster (median 2.2-3.4 s, p90 4-6 s) but capped at 50/day; Gemini flash-lite median 2.2 s. Input is large:
~30k tokens per call in herand/hereug and ~119k in hernik (long sessions), which costs time on every call.
`reasoning_effort` in Hermes is only translated for OpenRouter/Nous, so it does nothing on NVIDIA (tested: no change). Turning
thinking off for the main NIM model needs a *custom provider* with `extra_body.chat_template_kwargs.enable_thinking: false`
(`custom_providers`); measured with the API directly it takes a 200-token answer from 3.2 s to 2.0 s with the same tool-call result.
Not applied: it changes the provider name everything else keys on and its effect on hard multi-step work is not measured.

**Which NIM models answer today** (`ops/bench_models.py --discover`, 50 chat-looking models probed): only `nemotron-3-super` (0.9 s),
`openai/gpt-oss-20b` (1.4 s), `nemotron-3-ultra-550b` (2.3 s), `nemotron-3.5-lightning-30b` (19.7 s) and `gemma-4-31b-it` (21.8 s). Everything
else: 404 (e.g. every Llama 3.x text model, Mistral, Mixtral, `kimi-k2.6`), 503, empty (`meta/muse-glimmer`) or a 25 s timeout
(`glm-5.3`, `glm-5.3-flash`, `kimi-k3`, `deepseek-v4.1-flash`). The catalog moves: re-run before relying on a name.

**Benchmark** (single run, `ops/bench_models.py`; differences under ~30 % are ties):

| Model | short | 200-token answer | tool call | invents a tool | fake internal API |
|---|---|---|---|---|---|
| nemotron-3-super (NIM) | 1.2 s | 3.2 s, 64 tok/s | ok | no | invents (q3) |
| nemotron-3-super, thinking off | 0.9 s | 2.0 s | ok | no | invents (q3) |
| gpt-oss-20b (NIM) | 1.8 s | 7.5 s, 27 tok/s | ok | no | invents (q3) |
| gemini-3.5-flash-lite | 0.8 s | 1.4 s, 107 tok/s | ok | no | invents (q3) |
| gemma-4-31b-it (NIM) | 52 s | 20 s, 6.6 tok/s | ok | no | invents (q3) |
| nemotron-3-ultra-550b (NIM) | 1.6 s | 7.3 s | **HTTP 500** | no | invents |
| nemotron-3.5-lightning-30b (NIM) | 1.0 s | 1.7 s, 115 tok/s | ok | no | unreliable: **prints its chain of thought inside the answer** |

Method note: a first version of the fake-API check used too strict a denial detector (it missed "does **not** include") and reported 3/3
for most models; reading the answers showed all of them correctly deny a non-existent pandas method and a non-existent stdlib module and
all of them **invent** the third one, a plausible-sounding internal Hermes tool (`browser_helpers.attach_session()`). That is the
failure that matters in production.

**Chosen:** main `nemotron-3-super` (NIM); fallback chain `gpt-oss-20b` (NIM, free, model-level backup for people whose only provider is
NVIDIA) then `gemini-3.5-flash-lite` (fast, but it spends paid tokens, so it is last). Not chosen: `nemotron-3-ultra` (fails tool calling),
`nemotron-3.5-lightning` (fast but leaks its reasoning into replies), `gemma-4-31b` (20-52 s). `ops/model_guard.py` `CATALOG` order is this
preference.

**Models that hallucinated** (from tool results in `state.db` plus the benchmark; "command not found" for tools that are simply not
installed, such as `docker` or `nvidia-smi`, is an environment gap and is not counted here):
- `nvidia/nemotron-3-super-120b-a12b` (herand, hereug): invented Python modules `agent_helpers` and `browser_helpers` (most of the 15
  module-not-found errors across the two instances; `weasyprint` is a real module that was not installed, a different case); assumed `uuidgen` exists; said it had a CV it did not have, told a person it "cannot
  access external domains", and built links to folders it never created. Invents the meaning of a plausible internal tool in the benchmark.
- `Qwen/Qwen3.8-27B` (hernik, free route): imported modules that do not exist for Resolve scripting (`pyDavinciResolve`) and assumed
  CLIs (`claude`, `gh`).
- `gemini-3.5-flash-lite`, `gpt-oss-20b`, `gemma-4-31b-it`: invent the fake internal API in the benchmark (they do deny non-existent
  public ones).
- Not usable for another reason: `nemotron-3.5-lightning` (chain of thought in the reply), `nemotron-3-ultra` (500 on tool calls),
  `gpt-5.3-codex*` (no entitlement on the account).
Mitigation is not a model switch (all of them do it): tell the agent what it really has (skills and rules listing real commands),
keep modules/commands out of guesses (`ls`, `command -v` first), and send hard code to Claude (see below).

**Bug found and fixed in `ops/model_guard.py`:** for herand and hereug it logged `applied: true` but wrote nothing, because their
`config.yaml` has no `fallback_providers` key (hernik's does) and the code only knew how to replace it. It now creates the key at the end
of the file and sets `applied` only when the file really changed; after writing, check that Hermes still loads the config
(`hermes auth list`). Lesson: a tool that reports success must verify the effect, not the intent.

**hernik recreated (2026-10-06, operator approved):** it was running an image from 2026-10-04 that predated Chromium, `browse-page`,
`buscar-empleos`, `deliver`, the keys UI and the document extractor. Steps: tar backup of `/root/.hermes` without the reproducible
parts (`~/backups/hernik-pre-recreate-20261006.tar.gz`, 0600), memories, `auth.json` and skills copied by hand into `/hermes-persist`
(the old start script had not persisted them), `docker compose build hermes-agent` (12 s, cached base), `docker compose up -d
--no-deps hermes-agent`, then `deliver` copied into `/workdir`. Verified through its API: text, `execute` guardian (`42`), vision
("azul"), `browse-page`; gateway, Telegram and API connected, `jobwatch` re-created, config and memories restored. No image rollback exists (the
old image was already gone from disk): the way back is that tar. Still failing and unrelated: the `davinci-resolve` MCP reports
`Connection closed` (resolve-host answers on :22; the Resolve wrapper there is probably not running).

### hereug trace: a 40-minute loop, no vision, lost context (2026-10-06)

Traced from `state.db` (tool calls and results per session, secrets masked) after the person said Hermes was guiding them wrong.
What the history showed, in order of cost:

1. **A 300 s hang on every terminal command that needed approval, repeated 12 times (3 in herand).** Hermes runs "smart
   approvals": a guardian model reads the flagged command and answers one word. The guardian was the main model,
   `nemotron-3-super` (a reasoning model), called with `max_tokens=16`: it spent them thinking and returned an empty answer
   (`finish_reason=length`, log: `Smart approvals: guardian returned an empty answer ... escalating`). Escalation goes to a human;
   the web chat has none, so it waited 300 s and answered `BLOCKED: ... timed out without user response`. The agent then asked
   "yes/no?" in the chat, the person said yes eight times, and each retry waited another 300 s. `approvals.unattended_mode` does not
   cover this path (it applies when no human is registered; terminal gates for an api_server session register one).
   Reproduced against NVIDIA: default -> empty; `chat_template_kwargs.enable_thinking=false` -> `APPROVE` in 0.8 s.
   Fix (all three instances): `auxiliary.approval` pinned to `nvidia / nemotron-3-super-120b-a12b` with
   `extra_body.chat_template_kwargs.enable_thinking: false`. Verified: a flagged `python3 -c` command returns in seconds and the
   log shows no new empty answer. Pinned to NVIDIA on purpose: the `extra_body` could be rejected by another provider if the
   primary falls back (hernik falls back to Gemini).
2. **Images failed (`No endpoints found that support image input`).** The vision tool defaults to the main model, which is text-only.
   NIM catalog check (2026-10-06): `meta/llama-3.1-8b-instruct`, `meta/llama-3.3-70b-instruct` are gone (410) and
   `mistral-7b-instruct-v0.3` 404; `meta/llama-3.2-11b-vision-instruct` answers in 0.8 s (90b in 1.2 s), `gemma-4-31b-it` in 27 s.
   `auxiliary.vision` pinned to the 11b on all three; checked with an image through Hermes ("rojo").
3. **The model invented helper modules** in browser code (`No module named 'agent_helpers'` / `'browser_helpers'`, 11 times). That
   is model quality, not configuration; it is the case for delegating hard work to Claude (see below) rather than a setting.
4. **Misleading guidance saved in its own memory:** the agent told the person to run `hermes vault add ...` and `hermes auth add ...`
   (there is no terminal in the web chat) and stored that as a rule. Removed from hereug's `MEMORY.md`; the preset now says the
   person has no terminal and must not be asked to paste keys or run `hermes` commands (keys go to `/keys/`).
5. **Secrets pasted in the chat** (several API keys and a site password). They are now in that instance's `state.db` and in
   `sessions/request_dump_*.json`. They must be rotated by their owner; nothing was copied anywhere else. Deleting them from the
   history is a separate, destructive step that was not done.
6. **"Where did everything go?"** Each Open WebUI chat starts a new Hermes session with no memory of the previous one. Persistence
   itself is healthy (`state.db`, memories and config sync to `persist/` within ~30 s, backups at 04:15), so nothing was lost, it was
   just not visible to the new session. Fix: `/workdir/PROGRESS.md` on the persistent volume, which the preset (job-search stacks)
   tells the agent to read first in every conversation and update after each step; seeded for hereug. Verified: a new chat answered
   in Russian with the exact point where the work stood.

Also: the user's language is a fact to store (`USER.md`): hereug's person writes Russian and had to ask three times.
New stacks get items 1 and 2 on first boot from `start_hermes.sh` when the provider is NVIDIA.
Left for the operator (a permission check refused it): telling the agent in the preset not to ask the person to confirm terminal
commands and to take another route when one is blocked for lack of approval. With item 1 fixed it should not be needed.

### Delegating hard tasks to Claude over SSH (hereug, 2026-10-06; installed and tested)

Goal: Hermes handles the routine; when a task is complex it hands it to Claude (Sonnet) through **Claude Code on a machine
where it is already logged in** (the person's own Pro). No API key and no subscription plugin: Claude Code stays on that machine.

Facts checked: the machine is on the LAN; Claude Code 2.1.x lives in `~/.local/bin/claude` (not on a non-interactive `PATH`, so
scripts must use the full path); its login at the time of checking was the **operator's Pro account and expired**
(`claude auth status`: "Not logged in"). Guest containers cannot reach the LAN by design (`docker-user-fw.sh`), so a single
pinhole is needed.

Design (least privilege):
- A key created **inside the person's container** (`/workdir/.ssh/id_ed25519_claude`, persistent), never shared with another stack.
- On the remote it is authorized as `restrict,from="<docker host LAN ip>",command="~/bin/claude-gate"`: no shell, no pty, no
  forwarding, only from the Docker host. `claude-gate` reads the task from stdin and runs `claude -p` in `~/hermes-tasks` with
  file tools only (`Read,Write,Edit,Glob,Grep`) and `--max-turns 15`. Widen `--allowedTools` only on purpose.
- One firewall exception for that stack to that host:port (`GUEST_PINHOLES` in `docker-user-fw.sh`).
- A skill (`ops/SKILL_claude_remote.md`) tells Hermes when to delegate and to **ask first**, because it spends the Pro allowance
  the person also uses by hand. Automatic delegation by complexity is a prompt rule, not a Hermes feature.
- Installer: `ops/install_claude_gate.sh <user@host> [container] [source-ip]` (run in a terminal; ssh asks for the remote password
  once). The password is not stored anywhere; disable password login on the remote afterwards and change it if it was pasted in
  a chat. Host names and addresses stay out of the repo; the ssh config lives in the container.

Installed and verified for hereug (VM105 container -> the person's machine on the LAN): firewall pinhole applied (22 only; other
ports and the rest of the LAN stay closed); `echo ... | ssh -F /workdir/.ssh/config claude-box` returns Claude's answer; a different
command is ignored (the gate runs instead, `empty task`) and a shell/pty is refused. Port forwarding was not exercised with traffic.
Things that went wrong on the way, worth knowing:
- A key authorized on the wrong side or a typo gives `Permission denied (publickey)` with the key *offered*; read the remote
  `authorized_keys` / `auth.log`, not the container. The container's source address on the LAN is the Docker host's (`from=` must
  match that, here the host IP).
- Claude Code on the remote lives in `~/.local/bin` (not on a non-interactive PATH) and its **login had expired**: check
  `claude auth status` there first.
- **A skill does nothing unless the model is told to load it.** A memory rule alone was ignored: hereug built a 5-service system
  itself instead of asking. The rule that works is in the Open WebUI **system prompt** (`CLAUDE_REMOTE=1` in
  `ops/openwebui_setup.sh`, only for stacks that have the machine): complex task -> reply only "Esto es complejo, ¿querés que se
  lo pase a Claude?" and wait. Verified: it now asks. The built-in `claude-code` skill assumes a local `claude`; the prompt
  tells the agent not to use it here.

Open: whose Claude account the remote uses (it spends that plan), whether Anthropic's terms allow this automated use of a Pro
plan (check before relying on it), and extending it to other people (each one would need their own machine/login).

### yt-dlp in every Hermes (2026-10-06)

`yt-dlp` (pinned official binary, 2026.08.19) and `ffmpeg` are in the base image (`Dockerfile.hermes-agent-base`), so hernik,
herand and hereug all have them and so will any new stack. Checked in each container: YouTube lists 32 formats, `node` is present,
and a full download works (hernik: 15 min video, ~40 MB mp4 with audio; hereug: video + audio merged).

How hernik "did it": it needed about 15 attempts. YouTube now serves video and audio as separate streams, so the formats the
agent kept asking for (`-f 'best[ext=mp4]'`, `-f best`) find nothing usable; it got there with `--js-runtimes node`, `--list-formats`
and a hand-picked video-only itag (`-f 135`). A 403 from `googlevideo` also shows up when ffmpeg downloads a slice
(`--download-sections`), which is a quirk of that option, not a broken install.

Fix: a default config at `/root/.config/yt-dlp/config` in all three (reference copy `ops/yt-dlp.conf`, written on boot by
`start_hermes.sh` only if missing): `--js-runtimes node`, `-S res:720,vcodec:h264,acodec:m4a`, `-f bv*+ba/b`,
`--merge-output-format mp4`, `--no-playlist`. Plain `yt-dlp <url>` now picks 720p H.264+AAC merged into one mp4, which plays in
Telegram and browsers. Flags on the command line still override it. yt-dlp needs frequent updates to follow site changes; the
version is pinned in the image, so when a site stops working, bump the pin and rebuild.

### Web UI: image recognition (2026-10-04)

The "Hermes" preset had `capabilities.vision=false`, so hernik did not offer image
attachments. Hermes's API itself takes `image_url` parts and understood a test PNG
(text + shapes, 8s direct, 21s through hernik). Preset now `vision: true`.

### Job-done notifications: `jobwatch` (2026-10-04)

Closes audit finding #1 (the "push when the render finishes" Hermes said it had
built never fired: `hermes webhook list` shows no subscription at all, and no
cron job existed). Replacement, free and with no LLM: a Hermes cron job
`jobwatch` (`every 1m --no-agent --script jobwatch.py --deliver telegram`; empty
stdout = silent). Hermes registers a long job by dropping a JSON file in
`/workdir/jobs/` (`pid`, `done_file` and/or `check_cmd`, e.g. an `ssh resolve-host
'test -f ...'`); `jobwatch.py` reports it once on Telegram when done or after
`timeout_min`, then deletes it. Instructions for the model: `SKILL_job_notify.md`.
Cron jobs are not persisted, so `start_hermes.sh` re-creates `jobwatch` on every
boot if missing. **Verified for real**: a test job finished and Hermes's
`cron/executions.db` recorded `delivery_outcome=delivered` (the previous empty tick
was `suppressed`). Limits: the message goes to the Telegram home chat only (a
web-only user gets nothing pushed); granularity is one minute; whether Hermes
reliably registers jobs by itself when asked for a render is **not yet verified**.

### Live voice on the web, free (2026-10-04, deployed; browser call UI not verified)

Telegram cannot do live calls (the Bot API has no voice calls): it stays on voice
notes. The web UI has Open WebUI's "Call" mode, which needs the mic, hence HTTPS:
now available through the edge (`https://<hernik-domain>`).

- **STT**: Groq `whisper-large-v3-turbo` through its OpenAI-compatible endpoint (free
  tier; limits seen in headers: 7200 audio-seconds/hour, 2000 requests/day), ~0.5s,
  near-perfect Spanish. Audio from web users therefore goes to Groq (as Telegram
  voice notes already do). The key is read from `.env` by `ops/openwebui_setup.sh` and
  stored in Open WebUI's DB (admin-only).
- **TTS**: `tts-piper` service (`tts/Dockerfile.piper`, image 1.5GB, ~160MB RAM,
  `es_MX-claude-high`), not published, reached by Open WebUI over the compose network.
  On VM105's CPU: 0.9s for a short phrase, 3.1s for ~8s of audio (this desktop does
  0.33s). Open WebUI splits on punctuation and speaks sentence by sentence, so first
  audio comes earlier than those totals. Kokoro (better sounding, not yet judged by
  the operator) is 3.4s on CPU for a short phrase: needs the GPU box.
- **Measured one-turn cycle through the public URL**: TTS 3.3s (non-split, mp3) + STT
  0.5s + Hermes 16.4s (a trivial question; "listo" usually takes 3-5s) + TTS 3.5s
  = ~20s. The Hermes agent turn dominates, so this is turn-based talking, not
  instant. Idea if it must feel live: a second preset that talks straight to a fast
  free LLM (NVIDIA NIM, ~1s) without tools, and falls back to the full "Hermes" for
  tasks. Not built.
- Real phone calls are not free (Twilio/Vapi): see the telephony section.

### Telegram big-file upload: read timeout, not the 2GB cap (2026-10-04)

Two real uploads of a 261MB video failed with `Failed to cache video: Timed
out` (`telegram.error.TimedOut` in `get_file`), a different failure from the
earlier `InvalidToken`. Cause: with the local Bot API server, `getFile`
blocks until the server has downloaded the whole file from Telegram, and
Hermes's HTTP read timeout defaults to 20s (`HERMES_TELEGRAM_HTTP_READ_TIMEOUT`,
`plugins/platforms/telegram/adapter.py`). The server side was fine: both
attempts left a full 261MB copy in `telegram-bot-api-data/<bot>/videos/`
(one per retry, so failed retries also waste disk). Fix: compose now sets
`HERMES_TELEGRAM_HTTP_READ_TIMEOUT` to 600 (needs a Hermes restart). Side
effect: that timeout applies to the general Telegram HTTP pool, so a hung
send can now wait up to 10 minutes. The timeout fix worked, and the
same upload then hit a second limit: `Inbound video payload is too large
(261391146 > 134217728)`, i.e. `gateway.max_inbound_media_bytes` (128 MiB
default, `config.yaml`). That cap is deliberate: Hermes reads the whole file
into memory (`download_as_bytearray()` then `bytes(data)`, so ~2x the file
plus the ~800MB baseline), and the cap prevents OOM-killing the gateway.
Raised to 512 MiB and the container memory limit from 1.5GB to 3GB
(`docker-compose.yml`) to give it room; VM105 has ~4.5GB available. This does
**not** make true 2GB uploads work: that would need Hermes to stream the
download to disk instead of buffering it, which is a code change in Hermes,
not a setting. Effective inbound limit is therefore ~512 MiB. Not yet
re-verified with a real upload.

#### Local patch: big files through disk, not RAM (2026-10-04)

Both directions buffered whole files in RAM (inbound: `download_as_bytearray()` +
`bytes()`, ~2x the file; outbound: PTB reads an open file handle fully before
uploading), with timeouts sized for the public 50MB cap. `bridgeai` is our own
fork of the deployment, so the fix is a patch script applied at image build:
`aibridge/patches/telegram_large_files.py`, run from `Dockerfile.hermes-agent`
right after the pinned-commit install. It does string replacements that must
each match exactly once, so **bumping the Hermes commit pin fails the build
loudly if this code changed**: re-check the patch then (or drop it if upstream
fixed it). What it does:

- **Inbound video** (as video or as a document): copies the file from the
  shared Bot API volume to the video cache with `shutil.copyfile` in a thread
  (no RAM, event loop not blocked); falls back to PTB's `download_to_drive`
  without a local server. No longer subject to `max_inbound_media_bytes`
  (still limited by Telegram's own 2GB and by free disk). **Verified
  2026-10-04**: a 261MB video was cached on disk and processed; Hermes stayed
  at ~700MB. Hermes mounts the server's data volume **read-only** on purpose
  (it must not write into the server's storage), so it can't delete the
  server's copy: `ops/telegram-media-cleanup.sh` + a `systemd --user` timer on
  VM105 (`~/.config/systemd/user/telegram-media-cleanup.timer`, hourly) prune
  media older than 180 min from the server volume and the outbox.
- **Outbound video/document over 50MB**: stages a copy in `/telegram-outbox`
  and sends a `file://` URI, which PTB's `local_mode` passes through untouched.
  That is a **separate volume** (`./telegram-outbox`): rw for Hermes, ro for
  `telegram-bot-api`, same path in both. (First attempt staged under the
  server's data volume and failed with `Errno 30 Read-only file system`; the
  code then silently falls back to the old RAM path.) Thumbnails are staged too
  (the server can't see Hermes's `/tmp`). Staged files are removed after the
  send. Smaller files keep the old path.
- **Timeouts** now come from env: `HERMES_TELEGRAM_MEDIA_SEND_READ_TIMEOUT`
  (compose default 1200s) and `HERMES_TELEGRAM_MEDIA_SEND_DEADLINE` (1800s).
- Not covered: images, audio, and non-video documents still use the RAM path
  (small, or bounded by the 512 MiB cap).

Build note: `docker compose build hermes-agent` re-uses the cached install
layer, so adding/changing the patch takes seconds. Status: inbound verified
(261MB). Outbound verified only via the RAM fallback (803MB video sent
successfully with the long timeouts, Hermes peaked at 1.29GB); the staged
`file://` path was deployed afterwards and is **not yet verified**.

#### Local patch: round videos / video notes (2026-10-06)

Symptom: the bot silently ignored the circle videos. Cause: the adapter registers
`PHOTO | VIDEO | AUDIO | VOICE | Document | Sticker` and not `filters.VIDEO_NOTE`, so a
`message.video_note` never reached `_handle_media_message`. Second patch script,
`aibridge/patches/telegram_video_note.py`, run from `Dockerfile.hermes-agent` after
`telegram_large_files.py` (same rules: each replacement must match exactly once, so a
commit-pin bump fails the build loudly; re-running is a no-op). It does four things:

- registers `filters.VIDEO_NOTE` on the media handler;
- classifies `video_note` as `MessageType.VIDEO` and handles it like `msg.video`
  (mp4 cached on disk, goes to vision); also covers replied-to/observed media;
- **extracts the audio track** with ffmpeg (`-vn -ac 1 -c:a libopus -b:a 32k`, 60s
  timeout) into an `.ogg` next to the mp4 and appends it as a second attachment typed
  `audio/ogg`. Needed because the gateway's STT (`_classify_inbound_media` /
  `_event_media_is_stt_input`) only takes `audio/*` attachments: a plain `video/mp4`
  goes to vision only, so the speech was never transcribed (Groq STT, same path as
  voice notes). Best effort: no audio stream or ffmpeg failure leaves a plain video;
- the circle is a normal square mp4 up to 1 min, so no size handling is needed.

Extended the same day to **regular videos** (`msg.video`) and **videos sent as a
document**: the same `_attach_video_audio_track` runs after they are cached, so their
speech is transcribed too (ffmpeg timeout raised to 300s for big files). A video with
no audio stream is left as a plain video. The document hook anchors on code changed by
`telegram_large_files.py`, so that patch must run first (it does in the Dockerfile).

Deployed **live on hernik only** (`aibridge-hermes-agent`) on 2026-10-06: `docker cp` of
the patched `adapter.py` + SIGTERM to the gateway (the `start_hermes.sh` loop restarts
it in ~1 min; `pkill`/`pgrep` don't exist in the image, find the PID via `/proc`).
**Verified by the operator with a real circle with speech and with a regular video: both transcribed correctly.**
The hereug and herand stacks are not patched; the hernik container loses the patch if
recreated until the image is rebuilt from the updated Dockerfile.

### LAN access: OpenAI-compatible API and Open WebUI (2026-10-04)

Two doors besides Telegram, both published on VM105's LAN IP and limited to
`<lan-cidr>` + the edge VM by `docker-user-fw.sh` (DOCKER-USER). **Since
2026-10-04 the web UI is also on the internet**: the operator put it behind the
edge VM at `https://<hernik-domain>` (valid Let's Encrypt cert, HTTP
redirects to HTTPS, websockets work, a 93s Hermes turn passes, uploads up to at
least 30MB pass and 150MB gets a 413 from the edge). The Hermes API on :8642
remains LAN-only (checked: unreachable from outside). Facts that matter now:

- **Anyone with a web account can run commands through Hermes** and so reach the
  API keys in its environment (Gemini, NVIDIA, Groq, OpenRouter, the Telegram bot
  token) and the SSH key to resolve-host. Therefore: signup off, new users default to
  `pending`, and the "Hermes" model preset is **private** (`access_control` with
  empty read/write lists, set by `ops/openwebui_setup.sh`): verified that a freshly
  created ordinary user sees no model and gets "Model not found". Grant access to a
  specific user/group only for people trusted with those keys. Open WebUI has no
  2FA; consider OIDC (e.g. Google) or edge-level access control later.
- Open WebUI rate-limits sign-in (429 from the 16th failed attempt, tested).
- Hardening added: `ENV=prod` (disables `/docs` and `/openapi.json`, which were
  public), CORS limited to the two own origins, security headers in nginx
  (`nosniff`, `X-Frame-Options`, `Referrer-Policy`, HSTS), cookies are not
  `Secure` on purpose (the LAN IP is plain http).
- The edge still sees a request-size cap; for videos beyond it use Telegram or the
  LAN address.

Details of each door:

- **Hermes API** `http://<docker-host-ip>:8642/v1` (`API_SERVER_HOST=0.0.0.0` in
  compose, Bearer `HERMES_API_KEY`). 401 without or with a wrong key. Whoever
  holds the key can drive Hermes and all its tools (including SSH to resolve-host),
  and there is no per-user accounting.
- **Web UI** `http://<docker-host-ip>:3000` = `web` (nginx, the only published port) in
  front of `open-webui` (image pinned by digest, `main-slim`, ~280MB RAM).
  Login only: signup disabled, one admin (`admin@aibridge.local`, password in
  VM105's `.env` as `OPENWEBUI_ADMIN_PASSWORD`, never in the repo) who creates
  other users from the UI. The UI exposes one model, **"Hermes"**, a preset
  (`ops/openwebui_setup.sh`, idempotent) = Hermes's API + a system prompt that
  says it is on the web UI. **All users share the same Hermes instance** (one
  memory, one tool set): a single-tenant fallback to Telegram, not the
  per-person isolation planned in `USER_INSTANCE_GUIDE.md`.
  - **Files in**: Open WebUI never forwards upload bytes to Hermes, only an
    `<attached_files>` stub. Its `uploads/` dir is mounted read-only into Hermes
    at `/openwebui-uploads/<id>_<name>` and the skill/system prompt say so.
    (First try: Hermes searched the whole disk and answered "not found".)
  - **Files out**: Hermes writes to `/web-outputs/<uuid>/<file>` and answers with a
    **relative** markdown link `/hermes-files/<uuid>/<file>` (images inline).
    nginx serves it only to a logged-in Open WebUI session (`auth_request` against
    Open WebUI's `/api/v1/auths/`, same `token` cookie, same origin: no second
    login, inline images work). Without a session: 401. HTML/SVG/JS/XML are forced
    to download (they would run on Open WebUI's origin, whose JWT is in
    localStorage). Path traversal checked. Pruned after ~24h by the cleanup timer.
    nginx's worker runs as root (`web/nginx-main.conf`) because Hermes's umask 077
    makes outputs 0600 root; the container only has that volume read-only.
    `proxy_pass` uses variables + docker DNS so recreating `open-webui` doesn't
    leave nginx on a stale IP.
  - **PDF**: base image gained `weasyprint`, `qpdf`, `reportlab`, `pypdf`,
    `python-is-python3` (apt) and pip-pinned `pdfplumber==0.11.10`,
    `pypdfium2==5.14.0` (the bundled `pdf` skill needs them). Cost: base image
    1.9GB -> 3.2GB, and the pip step upgraded Pillow to 12.3.0 over Debian's.
    Verified: 120-page PDF read (found a keyword on page 47, correct page
    count); a generated A4 PDF delivered via link, opened and rasterized.
  - **Mermaid**: Open WebUI renders ```mermaid blocks natively (mermaid 11.10 is
    bundled); Hermes emitted a valid flowchart. Visual rendering in a browser was
    **not** verified by me (the browser session I tried froze); the container has
    no Mermaid CLI/Chromium, so exporting a diagram to an image uses Graphviz.
  - **Video**: 6s clip uploaded, brightened by Hermes, downloaded through the
    link; mean luma measured 124.6 -> 150.8.
  - Gotchas found: (1) Open WebUI stores its settings in its DB after first boot,
    so env vars like `DEFAULT_MODELS` / `ENABLE_EVALUATION_ARENA_MODELS` are
    ignored afterwards: the setup script sets them via the API. (2) Hiding the
    base model with `is_active:false` makes the preset stop resolving ("Model not
    found"); use `meta.hidden:true`. (3) The resolved model list is cached until
    `/api/models` is requested, so API clients can get a stale "Model not found"
    right after a config change. (4) The slim image has no embedding engine, so
    Open WebUI logs a 503 for every upload's RAG step; harmless here because
    Hermes reads the file itself. (5) `AIOHTTP_CLIENT_TIMEOUT` is 3600 (default
    300s would cut a long transcode); helper generations (titles, tags,
    autocomplete, follow-ups, retrieval queries) are off since each is a full
    Hermes turn.
- **Not exposed on purpose**: `hermes dashboard` (port 9119) is an admin panel
  for config, API keys and sessions.

### NVIDIA NIM added as first fallback (2026-10-04)

Operator created the account and key. Wired on VM105: `NVIDIA_API_KEY` in
`.env` + compose `environment`, and `provider: nvidia / model:
nvidia/nemotron-3-super-120b-a12b` as the **first** `fallback_providers`
entry (backups `*.bak-20261004-193100`). Key checked live: `/v1/models`
lists 81 models but not all are invocable on this account (`kimi-k2.6`
returned 404, `glm-5.3-flash` timed out at 60s); `nemotron-3-super` answered
in ~0.85s. Not yet verified: tool-calling with this model, and a real
fallback activation (needs Gemini's daily 250k-token free quota to run out).
**Correction + follow-up (same day)**: a real fallback activation *was*
verified later (`hermes chat --provider openai-codex -m gpt-5.3-codex-spark`
fell through to NIM and answered). An earlier note here claimed the
`openai-codex` fallback had no OAuth token; that was wrong. The OAuth
credential in `auth.json`'s pool is valid (device-code login, expires
2026-10-12) and `hermes auth status openai-codex` says logged in. The real
problem was the **model**: the account has no entitlement for
`gpt-5.3-codex-spark`, `gpt-5.3-codex` or `gpt-5.6-codex` ("model
entitlement" error, silently falls to the next entry). `gpt-5.6-luna` and
`gpt-5.5` do work, so the chain entry now uses `gpt-5.6-luna`. The
`resolve_provider_client: openai-codex requested but no Codex OAuth token`
warning in the logs comes from the auxiliary-client path and was not
reproduced by the main fallback path; its cause is not resolved. Note:
the Codex OAuth is a ChatGPT-account login, not an API key.

#### Original survey (before it was added)

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
directly on `resolve-host`, bypassing its normal human-controlled OAuth login,
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
  forwarding restrictions at all) on `resolve-host`, no matching private key
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
  sent a real SSH password for `resolve-host` over Telegram mid-conversation
  (2026-10-01, ~09:30), which persisted verbatim in `~/.hermes/state.db`
  — once in the original message, and a second time inside a later
  context-compaction summary (compaction re-writes/duplicates recent
  history into a handoff blob, so a secret present when compaction runs
  can end up copied). Same operator policy as `FLOW.md`'s secrets
  earlier this project (see `<other-project-notes>`
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

**Grants so far, both scoped to `resolve-host` only** (see "Hardened SSH
access" above for the fuller MCP-specific key):

- A dedicated ed25519 keypair (not a reuse of any fleet/admin key),
  mounted read-only into the container, wired into `~/.ssh/config` fresh
  every boot (no persistence needed for the config itself).
- `authorized_keys` carries `no-port-forwarding,no-X11-forwarding,
  no-agent-forwarding`. its user has no sudo on `resolve-host`, so this key
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
of it fits the 768MB container. If built, the host is decided (`resolve-host`,
reusing the existing SSH identity) and the connection would be direct
Bolt (`bolt://resolve-host:7687`), not SSH-wrapped — not started.

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

### OpenClaw evaluated (2026-10-08): not adopted, but its realtime-call method is the one to port

**Decision**: do not migrate to OpenClaw (v2026.8.1, "2.0"). Reasons: a heavy CVE record in 2026 (nine in four days
in March, one CVSS 9.9), ClawHub audits reporting 12-20% of skills with malware (methods differ, order of magnitude only),
sandbox and approvals **off by default**, and its own docs say the new multiplayer sessions are *not* a tenant boundary
(one Gateway = one trust domain; separate people need separate Gateways, which is what we already do with one Hermes per
person). Its real advantages are breadth (50+ chat channels, e.g. WhatsApp, which Hermes lacks) and a big skill market,
which we deliberately do not use (our skills are our own or agent-written). Worth a look only for a concrete gap (a
WhatsApp user), in a throwaway VM with sandbox on, no real keys, no third-party skills. Claims come from comparison blogs
and press, not from running it.

**The method worth porting (how OpenClaw does live voice).** Two ideas, both visible in its Talk mode and `voice-call`
plugin docs:
1. **A fast realtime voice model owns the conversation; the slow agent is a tool.** The realtime model (OpenAI
   `gpt-realtime-2`, or Gemini Live) listens, speaks, handles barge-in and chit-chat on its own. For anything needing
   tools, fresh information or deep reasoning it calls one shared tool, `openclaw_agent_consult`, which goes to the real
   agent through gateway policy (`realtime.brain: agent-consult`). The person never waits on the agent for small talk.
2. **Credentials never reach the browser.** The browser gets an ephemeral/constrained session token (WebRTC for OpenAI,
   a Gateway-side WebSocket relay for Gemini and others), never the API key. Telephony adds mu-law 8 kHz audio, VAD-based
   commit and barge-in that aborts playback and flushes queued audio. It also has a non-realtime cascade
   (streaming STT -> agent -> TTS) when a native speech-to-speech model is not wanted.

**Telephony details of its `voice-call` plugin** (from docs.openclaw.ai, read not run). It runs inside the Gateway process.
- Providers: Twilio (Programmable Voice + **Media Streams**: call audio over a WebSocket to the Gateway), Telnyx (Call Control v2),
  Plivo (XML transfer + GetInput), plus a `mock` for development.
- Needs a **public webhook URL** (Twilio: number's Voice webhook POST, Status Callback to the same URL with `?type=status`);
  setup refuses a `publicUrl`/tunnel/Tailscale URL that resolves to loopback or private space. Webhook hardening:
  `allowedHosts`, `trustForwardingHeaders`, `trustedProxyIPs`.
- Audio modes, only one active at a time: **realtime** (full-duplex OpenAI or Gemini Live; the model transcribes, reasons and
  speaks in one connection) or **streaming** (live STT from OpenAI/xAI -> agent -> core TTS such as ElevenLabs, converted to
  8 kHz mu-law). Also notify (one-way outbound) and turn-based conversation.
- Inbound is **off by default**: `inboundPolicy: allowlist` + `allowFrom`, per-number routes (`numbers` map by dialed number)
  that can override greeting, TTS, agent and prompt. The allowlist is a low-assurance screen (proves the provider delivered the
  webhook, not that the caller owns the number).
- Barge-in: caller speech during playback aborts the audio and clears queued TTS; older automatic replies still being generated
  are discarded too; suppressed only while the initial greeting plays. In realtime the stream supplies its own opening turn (no
  `<Say>` update, which would detach `<Connect><Stream>`). A dropped Twilio stream waits 2 s before ending the call.
- What ports to us: the two-layer pattern, barge-in handling and ephemeral browser tokens apply to Open WebUI's web call with no
  phone at all. The Twilio/number/public-webhook part is the already-noted telephony path (per-minute cost, public endpoint)
  and is **not needed** to improve the voice.

**Why it fits us.** Our measured web call (see "Live voice on the web") is ~20 s per turn because the Hermes turn
dominates (16 s on a trivial question), so it is turn-based talk, not a call. The idea already noted there ("a fast LLM
without tools, falling back to the full Hermes") is exactly OpenClaw's agent-consult pattern. Hermes already exposes the
brain endpoint (`/v1/chat/completions` on :8642) that the consult tool would call.

**Target languages: Spanish, Russian, English.** Status of each piece (to verify before building):
- STT: Groq `whisper-large-v3-turbo` is multilingual and already near-perfect in Spanish; Russian and English are
  expected to be fine, language auto-detect is already the default in the stacks (usage audit 2026-10-07).
- TTS today: Piper `es_MX-claude-high` only. Kokoro has native Spanish and English but, to our knowledge, **no Russian**.
  Piper ships Russian voices; other Russian-capable candidates (Silero, XTTS v2 with its non-commercial license,
  Chatterbox multilingual) are unbenchmarked. Qwen3-TTS lists Spanish/Russian/English but fp16 gives NaN on the Pascal
  GPU and fp32 runs slower than real time (tts/ benchmarks above), so it needs different hardware or is out.
- A native speech-to-speech cloud model would cover all three languages with one voice, at the price of sending call
  audio to a third party (OpenAI or Google) and per-minute cost, against the earlier "local only, reliability over
  quality" decision for TTS. That trade-off is the open question below.

**Open decision (operator)**: (a) cloud realtime model + `agent_consult` into Hermes (best latency/quality, audio leaves,
cost), or (b) local cascade (Groq STT -> fast free LLM with tools-less chat -> better local TTS per language, consult
Hermes for tasks), which keeps the earlier policy but needs a Russian-capable TTS chosen by listening.

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
| Infrastructure | GPU heavy-tools host (CUDA, `<gpu-desktop-ip>`) | ✅ confirmed working (CUDA); Vulkan passthrough confirmed broken on the same host |
| Infrastructure | Telegram file-transfer cap (20MB → 2GB, Local Bot API Server) | ✅ fully wired (`--local` flag + shared volume + client `local_mode`); final confirmation from a real user upload still pending |
| Infrastructure | Fallback resilience (5 vendors + `fallback_watchdog.py`) | ✅ live — 9-entry chain, primary `gemini-3.5-flash-lite` (pinned to `provider: gemini`, swapped from `gemini-3.8-flash` 2026-10-01 to compare quota/speed empirically), `nous`/`openai-codex`/`openrouter`/`huggingface` fallbacks, watchdog running as a `systemd --user` service on VM105 |
| Infrastructure | resolve-host "mystery noise" (2026-10-01) | ✅ root-caused — operator's own auto-opening Chrome page ringing the system bell; closed, confirmed gone. Resolve/PipeWire/KDE/reverb-g2 all checked and cleared first |
| Infrastructure | NVIDIA NIM as a 6th fallback vendor | 💡 researched 2026-10-01 (genuine free tier, ~40 RPM resetting every minute, no card) — natively supported, blocked on operator creating a `build.nvidia.com` account |
| Infrastructure | Telegram usage audit (2026-10-01) | ✅ done — real day traced end-to-end, 5 findings (unconfirmed render-push notification, untagged voice transcriptions, 6 gateway interruptions, plaintext password fixed, benign compaction duplication) |
| Skill | `page-agent`, `mcp-oauth-remote-gateway` (official bundled) | ✅ enabled 2026-10-01 via `hermes skills repair-official --restore` — gap found during the usage audit above |
| Infrastructure | DaVinci Resolve MCP connection | ⚠️ editing works; **rendering through the MCP does not work headless** (`LoadRenderPreset` False, render call hangs to the timeout, reproduced twice). Hermes falls back to ffmpeg NVENC; `/ask` run took ~7.5 min vs 17 min and no file on Telegram. See the two timing sections |
| Evaluation | `unofficial-davinci-mcp` as a third Resolve MCP server | 🚧 code reviewed and installed on resolve-host (not wired into Hermes); live tests on `MCP-Benchmark` paused until resolve-host is back on X11 |
| Infrastructure | `hermes-agent` container resources | ✅ bumped 2026-10-01, 1.0 CPU/768M → 2.0 CPU/1.5GB (host had ample headroom; old limit was measured at 76% memory near-idle) |
| Infrastructure | Security audit (world-readable `.env`, stray SSH key) | ✅ fixed — orphaned `.env` deleted, `umask 077` added, unexplained `hermes@mcp` key removed; tirith's fail-open default accepted as-is |
| Caller | ChatGPT (Custom GPT Actions) | 🚧 key + schema configured, first real authenticated call not yet confirmed in logs |
| Future, not started | Second human user (own Hermes instance, invite-key onboarding) | 💡 design agreed, blocked on RAM sizing, provisioning script not built |
| Future, not started | SSH access for Hermes into real infrastructure | 💡 explicitly deferred, separate decision |
| Future, not started | DaVinci Resolve MCP *delegation* (phone footage → edited video, the actual skill/request shape) | 💡 connection is live (see above), nothing wired into a skill yet |
| Future, not started | `resolve-gateway` aggregator (MCP-over-HTTP, hardware-busy gate, rsync-based upload/download) | 💡 full design documented 2026-10-01 ("Planned next step" above), zero implementation |
| Infrastructure | resolve-host session/power config (X11-vs-Wayland autologin, CPU governor/power profile persistence) | 🚧 root cause found and two fix scripts written 2026-10-01, not yet run on the machine |
| Future idea, not started | Hermes Agent as the human-facing Assistant (voice/messaging) | 💡 confirmed by the operator as a real future direction, zero implementation beyond what already exists as a side effect (Telegram) |
| Future idea, not started | Real phone-call / telephony interaction | 💡 a concrete candidate path found 2026-10-01 — Twilio (number) → Vapi (realtime audio/STT/TTS, "custom LLM" mode) → Hermes's own existing `/v1/chat/completions` endpoint as the brain, no OpenClaw framework needed; costs real money per-minute, needs a new public-facing endpoint, open questions not yet answered by the operator |
| Future idea, not started | `aibridge-mcp` adapter | 💡 designed on paper only, not built |

Note the asymmetry already in play: today, **ChatGPT is a caller into
aibridge** (it asks Claude/Antigravity/Hermes questions through the
bridge), same role sesame has — not an Assistant the human talks to.

### Recreate from the new image (2026-10-07)
The three Hermes containers were recreated while asleep (`docker compose ... up -d --no-deps --no-start`), data intact
(bind mounts + `/hermes-persist`). The image now has `rg`, `uuidgen`, `pgrep` and the cron-policy skill; the stop trap makes
`docker stop` exit 0 quickly. Measured wake: herand 28 s, hereug 23 s, hernik 137 s on the first boot of the new image
(Telegram DoH discovery and davinci MCP retries; to recheck on the next cycle). Guests keep `stt.language` from their persisted
config: it was set to "" by hand in herand and hereug. Auto sleep after 10 idle minutes confirmed live on all three.

### Hermes pin bumped to v0.21.6 (2026-10-08)
Pin moved from canary `8d940d2` (v0.21.4+canary, 2026-10-01) to the stable release **v0.21.6** (`818c13be`, 3905 commits
ahead). Both local Telegram patches (`telegram_large_files`, `telegram_video_note`) still match exactly once. Previous image
kept as `aibridge-hermes-agent:prev-20261008` for rollback (retag as `latest` and recreate).

**Gotcha found while validating**: v0.21.6 no longer installs `python-telegram-bot` with the `all` extra ("installed on
first use"), and that lazy install did NOT happen at gateway start: hernik booted but logged `Platform 'Telegram'
requirements not met` / `adapter creation failed`, so the bot was dead (the web side looked fine and the waker reported
`starting` until its 240 s timeout). Fix in `Dockerfile.hermes-agent`: `hermes pm install --extra telegram` right after the
installer. Check on any future pin bump: `grep "requirements not met"` in the hernik log after a wake.

All three recreated on the final image (asleep, data intact) and woken one at a time through the waker (a navigation
request to the stack's waker port; `docker start` by hand does not work, the waker stops what it did not start):
herand ready in 137 s, hereug 144 s (first boot of the image, before the telegram fix), hernik 58 s with Telegram
connected in polling mode. Harmless new warning on every boot: `Failed to load bundled provider plugin solstice: No
module named 'httpx'` (a model provider we do not use).
