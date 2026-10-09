# bridgeai — GET-to-GET command bridge between AIs

## What bridgeai is today (2026-10-09)

The project grew from the `/ask` bridge described below into **one private Hermes Agent per person**. Each person
gets their own stack (Hermes, Open WebUI, TTS, nginx) on VM105, with their own keys and data. Stacks sleep when idle
and wake on a web visit, a Telegram message or a due cron.

**The `/ask` bridge itself is legacy:** stopped on 2026-10-09 and kept in the compose profile `legacy`. The rest of
this README documents it as it was.

Where to read about each part (all in [`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md)):

| topic | section |
|---|---|
| per-person stacks, sleeping and waking, boot times | "Wake-on-demand", "Boot time after the 2026-10-09 work" |
| adding a person (one command) | "Adding a person" |
| model and key policy, the model guard | "Model and key policy", "Operator alerts and the privacy guard" |
| alerts to the operator (ops Telegram bot) | "Operator alerts and the privacy guard" |
| usage telemetry without personal data, daily and weekly reports | "Usage telemetry without personal data" |
| GPU hosts and Claude machines (`gateway` command) | "Gateways", "GPU desktop as a worker" |
| what hardware to add for more people | "Capacity plan" |
| what was stopped and why | "Legacy services" |

**Privacy rule for this public repo:** no names, chat or session ids, personal domains, LAN addresses or host names.
`aibridge/ops/privacy_scan.sh` (git hooks) enforces it against the operator's private list, which never enters git.

---

*Legacy* (stopped 2026-10-09): the `/ask` bridge used to be served at `https://bridgeai.example.com` (VM105 →
edge VM101). Small server (stdlib Python, no dependencies, `aibridge/app.py`), 100% filesystem state (no DB).

## Key points (for a reader new to this repo)

- **What it is**: a deliberately simple HTTP relay that lets one AI (an
  "asker" — sesame, ChatGPT) ask a question and get it answered by a
  *different*, real AI backend (Claude Code, Antigravity, or Hermes Agent)
  running somewhere else — without the asker needing to speak that
  backend's native protocol. The bridge is the only thing that has to know
  how to talk to every backend; askers only ever speak one simple protocol.
- **Why it exists**: different AI tools are good at different things and
  have independent usage quotas/credits. This lets an operator mix and
  match backends (and route around one running low) without rebuilding
  integration code for each asker.
- **How it works, end to end**: `GET /ask` → a token + a `result_url` to
  poll → the right backend agent picks the request off a filesystem queue,
  processes it with its own real CLI/API, deposits the answer → the asker
  polls `result_url` until it's `done`. No database, no message broker —
  every request and answer is just a file.
- **It's a bridge, not the endpoint.** From here, individual providers
  (right now: `hermes`) delegate further out to other machines that have
  special capabilities the bridge's own host doesn't — a GPU for image
  processing today, more later. See
  [`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md) for how that handoff
  works in practice.
- **Explicitly not trying to be**: a production message queue, a
  multi-tenant SaaS, or a fully autonomous system — see "Intentional
  limitations" at the bottom and the "Architecture decision" sections in
  `HERMES_ARCHITECTURE.md` for what's deliberately left out and why.

Credentials (pve3 root, P1 root, the service's shared key, SSH for the
`aibridge` user) are deliberately NOT in this file — ask the operator for
them. The shared key rotates whenever a leak is detected.

## Current status (2026-10-01): real agents connected, automatic routing

This is **no longer** manual routing. Four containers run on VM105
(`~/aibridge`, `docker compose`):

| container | role | provider it serves | status |
|---|---|---|---|
| `aibridge` | the bridge itself (`app.py`) | — | ✅ |
| `aibridge-claude-agent` | real Claude Code (`claude -p`) | `claude` | ✅ |
| `aibridge-antigravity-agent` | real Antigravity (`agy -p`) | `antigravity` | ✅ |
| `aibridge-hermes-agent` | real Hermes Agent (`hermes gateway run` + its own HTTP API) | `hermes` | ✅ deployed and confirmed fully end-to-end (`/ask?provider=hermes` round trip), **plus** Telegram (text + voice via Groq STT) working directly against the same instance, independent of aibridge |
| — | Grok Build (`grok -p`) | `grok` | 🚧 not deployed — jobs stay pending forever |

Every agent polls `/next` every 10s, processes with the real CLI (**no
permission-bypass flag at all** — no TTY to approve anything, any attempt to
use tools gets blocked; today they answer text only), and deposits via
`/deposit`. `model`/`effort` from `/ask` are actually passed through to the
CLI (used to be informational only — fixed 2026-09-30, see the valid model
catalog in `aibridge/GUIDE_ASKING_AGENT.md`).

**Storage shared between agents of the same "user":** all three agents
belonging to one operator mount the same `./user1-workdir:/workdir` volume
— if an agent ever writes a file there, any other agent of the same user
will be able to see/read it. Each CLI's own auth/config is separate
(`./claude-config`, `./antigravity-config`, future `./grok-config`). A
second "user" (different key, its own storage) is the natural extension,
not built yet.

## Who's who

- **sesame** — the agent that **asks**. Hits `/ask`, stores the
  `result_url`, and polls it until there's an answer. Full guide (valid
  models, real timings, robustness, errors):
  [`aibridge/GUIDE_ASKING_AGENT.md`](aibridge/GUIDE_ASKING_AGENT.md).
- **chatgpt** — second asking agent, same pipeline as sesame, its own key
  (`keys.json`, label `"chatgpt"`), tracked by `source` on every request
  (see "Multiple keys" below). Guide + OpenAPI schema for Custom GPT
  Actions: [`aibridge/GUIDE_CHATGPT_ACTIONS.md`](aibridge/GUIDE_CHATGPT_ACTIONS.md).
- **The answering agents** (`claude-agent`, `antigravity-agent`, future
  `grok-agent`) — poll the queue on their own and deposit the real answer.
  Reference guide (base protocol):
  [`aibridge/GUIDE_RESPONDING_AGENT.md`](aibridge/GUIDE_RESPONDING_AGENT.md).
- **The operator (you)** — decides which providers exist, runs the deploy
  for each new agent (see "How to add a new agent" below), and does the
  interactive login the first time a CLI needs OAuth.

## Configuring hermes-agent

The other answering agents (`claude-agent`, `antigravity-agent`) need only
their own CLI's interactive OAuth login — no `.env` entries of their own.
`hermes-agent` is the exception: it's the most capable answering agent here
(messaging platforms, MCP tool connections, its own fallback-model chain),
and that capability comes with real configuration. All of it lives in
`aibridge/.env.example` — copy it to `aibridge/.env` and fill in what you
need; every section below is independently optional except the first.

| Variable | Required? | What it enables |
|---|---|---|
| `HERMES_API_KEY` | **Yes**, if deploying `hermes-agent` at all | Shared secret between `responder_hermes.py` and Hermes's own local API server. Generate like `AIBRIDGE_KEY`. |
| `GEMINI_API_KEY` | No | First fallback model when Hermes's primary (free Nous tier) is rate-limited. |
| `OPENROUTER_API_KEY` | No | A *second*, independently-hosted fallback pool (free OpenRouter models) — added so a bad patch on one vendor's free tier doesn't take down the whole fallback chain in one go. Also unlocks Hermes's OpenRouter image/video-gen plugins as a side effect. Free account at [openrouter.ai](https://openrouter.ai/sign-up). |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USERS` | No | Telegram as a messaging front end for Hermes, gated to your own numeric user ID(s). Token from @BotFather. |
| `TELEGRAM_API_ID` + `TELEGRAM_API_HASH` | No | Self-hosts Telegram's official "Local Bot API Server" to raise the file-transfer cap from 20MB to 2GB (needed for anything video-sized). **Not** from @BotFather — a one-time, human-only login at [my.telegram.org](https://my.telegram.org). |
| `GROQ_API_KEY` | No | Speech-to-text for Telegram voice messages and uploaded audio files. Free tier at [console.groq.com](https://console.groq.com). |
| `ACOUSTID_API_KEY` | No | Song/recording identification (Shazam-style). Free key at [acoustid.org](https://acoustid.org/api-key). |

Deep dive — why each piece exists, the debugging history behind the
non-obvious ones (the Telegram 2GB cap in particular needed two separate
fixes, not just the API key), and the fallback-chain design — is all in
[`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md), not duplicated here.

## Endpoints (all require `?key=<shared key>`, except `/healthz`)

| Endpoint | Who uses it | What it does |
|---|---|---|
| `GET /ask?text=&model=&effort=&provider=&credit_pct=` | sesame | Creates a request. Returns `token`, `result_url` (points to `.json`, see below), `credits`. **Never** returns the final answer here, no matter how long the agent takes. |
| `GET /next?provider=` | the answering agent | Picks up the oldest pending request for that `provider` (`204` if nothing's there). Polling every 10s today, not push. |
| `GET /deposit?token=&body=&credit_pct=` | the answering agent | Deposits the answer (markdown, URL-encoded) for that `token`. |
| `GET /result/<token>.json` | sesame | **Always `200`**: `{"status":"pending"\|"done"\|"invalid_token","result":...}`. This is what `result_url` has returned since 2026-09-30 (used to be `.md`, see the gotcha below). `invalid_token` = that token was never created by a real `/ask` (not queued, not in progress, no result) — added 2026-09-30 to track the phantom-token gotcha. |
| `GET /result/<token>.md`\|`.txt` | manual debug | The already-deposited answer (`202 pending` while it hasn't arrived) — no longer the default, kept for manual `curl`. |
| `GET /credits` | anyone | Snapshot of the last **self-reported** credit %  — nobody feeds it automatically yet, not a live gauge. |
| `GET /credit?provider=&pct=` | anyone | Updates a provider's credit % without touching the queue. |
| `GET /healthz` | — | `{"ok": true}`, no key needed. |

Full protocol (with `curl` examples, model catalog per provider, error
format) in `aibridge/GUIDE_ASKING_AGENT.md`.

## Multiple keys (2026-09-30): same pipeline, different "askers"

The bridge now accepts **more than one valid key**, each with a label. No
per-key storage or container separation yet — it's tracking, not isolation
(that's the next step, mentioned in the project memory's "Vision" section,
not done).

- `secret.key` — the original key, label `"sesame"`.
- `keys.json` — `{"<key>": "<label>"}`, extra keys. One gets auto-generated
  for `"chatgpt"` on container startup if none exists with that label (see
  the log: `new key generated for 'chatgpt' at /data/keys.json`).
- Every `/ask` stores `job["source"]` = the label of the key used, and logs
  it (`[aibridge] /ask from '<source>' -> provider=... token=...`) — so you
  can see where each request came from without changing the protocol.
- **Dual auth**: `?key=<key>` in the URL (sesame, curl) OR header
  `Authorization: Bearer <key>` (ChatGPT Actions — its UI builds auth as a
  header, not a query string). Both always accepted, for any key.
- To add a new label (e.g. a third caller): use
  `ensure_key_for_label(keys, "<label>")` in `main()`, same pattern as
  `"chatgpt"`.

## Real observed timings (2026-09-30/10-01, for reference — not an SLA)

| provider | processing time | notes |
|---|---|---|
| `claude` | **2–6s** | consistent, warm context cache cuts input tokens to almost zero on follow-up questions. |
| `antigravity` | **9–33s**, quite variable | loads a fair amount of its own context per call (one call seen with **54k uncached input tokens**) — considerably heavier than claude per question. |
| `hermes` | **~4s** (one confirmed real sample: 4.2s, 13301 in / 67 out tokens, free Nous-tier model) | single data point so far, comparable to `claude`. |
| `grok` | no data, not deployed | |

Hard 120s cutoff per request (the `subprocess`/`execFile` timeout in each
responder) — if exceeded, an error message is deposited, it doesn't hang
forever.

## How to add a new agent (e.g. grok)

**I cannot do the deploy myself over SSH** — the Claude Code harness
categorically blocks any action that creates/enables a new agent-CLI on the
server ("Create Unsafe Agents"), even configs without tool access. What I
*can* do: prepare the `Dockerfile.<provider>-agent`, the
`responder_<provider>.py`, the `docker-compose.yml` block, and package it
all into a `deploy_<provider>_agent.sh` script the operator runs by hand
(`scp` + `ssh` + `bash deploy_....sh`). The only real manual step is the
interactive login the first time (OAuth/device-code, not scriptable).

Confirmed, reusable pattern for any Claude-Code-like CLI (`-p "text"
--output-format json`, no bypass flags):
1. Confirm the real binary (`which <bin>`, `<bin> --help`) — exact flag
   names for `-p`/`--print`, `--output-format json`, `--model`, `--effort`.
2. Confirm the real output JSON schema with a real call (it varies per CLI:
   Claude uses `result`/`usage.input_tokens`/`usage.output_tokens`/
   `usage.cache_read_input_tokens`/`duration_ms`; Antigravity uses
   `response`/`status`/`error`/`usage.cache_read_tokens`/`duration_seconds`).
   Each responder's parser is defensive (tries several known keys, falls
   back to raw text if nothing matches) — but it's worth tuning it against
   a real error, as was done for `agy` (see the `responder_antigravity.py`
   commit, the `status=="ERROR"` case).
3. Measure processing time with your own wall-clock (`time.monotonic()`),
   don't trust that the CLI's own duration field exists/has the same name
   across CLIs.
4. Same `./user1-workdir:/workdir` volume as the other agents for the same
   user; a separate config volume of its own for the auth session.

**Different case: `hermes` doesn't follow the CLI-subprocess pattern.**
Claude, Antigravity and Grok get invoked as `<bin> -p "text"
--output-format json`, a new process per request. Hermes Agent instead runs
its own **persistent HTTP server** inside the container — the responder
(`responder_hermes.py`) hits it over HTTP (`POST
http://127.0.0.1:8642/v1/chat/completions`, `Authorization: Bearer
<API_SERVER_KEY>`, OpenAI-compatible format) instead of launching a
subprocess per question. **Mind the command**: it's not `hermes serve`
(that starts the desktop app's backend, port `9119`, a completely different
thing) — it's **`hermes gateway run`**, the `api_server` "platform" of the
messaging gateway (confirmed the hard way on 2026-10-01, see the gotcha
below). `model`/`effort` from `/ask` are ignored for this provider — Hermes
manages its own model internally, configured once with `hermes setup
--portal` + `hermes model` (interactive OAuth login, the operator does it
by hand the first time, same pattern as the Claude/Antigravity login).
Full detail, why it was added, and the real problems hit during the deploy
(Dockerfile, the volume that clobbered the binary, the correct provider
key): [`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md) (English on
purpose).

## Alternate port 8443 (experiment 2026-09-30)

Sesame reported two connectivity problems in a row with no real evidence
behind them (see gotchas below): "outbound blocked" and later "DDoS
detection from hitting the same port repeatedly." Neither holds up against
our own logs (real traffic arriving without interruption, no rate-limit
configured anywhere in the stack). A second public port was added anyway as
a cheap experiment — costs nothing to have it, and it might help if the real
problem is on sesame's network side, not ours:

- **VM101** listens on `8443 ssl` in addition to `443` on the same vhost
  (`/etc/nginx/sites-available/bridgeai.example.com`), same cert,
  same `proxy_pass`.
- **P1** (`/etc/ppp/ip-up.d/dnat-torrent`) forwards `8443` to
  `172.16.0.2:8443`, same pattern as the existing `443` lines (WAN +
  internal hairpin + MASQUERADE). Applied and confirmed working (external
  `curl` to `:8443/healthz` returns `200`).
- **`app.py`**: every `200` response from `/ask`, `/credits`, `/credit`,
  `/result/<token>.json` and `/healthz` now includes `available_ports`
  (fixed list, `AIBRIDGE_PUBLIC_PORTS` env var, default `443,8443`) and
  `try_port` (a random suggestion per response, via `port_hint()`). The
  server doesn't rotate or force anything — it's purely information for the
  asker to decide whether trying the other port changes anything.

## Gotchas already hit (so nobody repeats them)

- **Two sesame connectivity reports, both refuted with evidence:** (1) "the
  outbound is blocked, nothing reaches `/credits` or any route" — the log
  showed real traffic arriving 15 minutes before the report, from the same
  IP sesame always uses, and **zero** real attempts at `/credits` in the
  entire history (the call never actually went out). (2) "hitting the same
  port repeatedly triggers DDoS detection" — reviewed the full log of the
  test session: same token, same IPs, hit repeatedly within minutes, always
  `200`/`202`, never throttled/blocked; `mini-waf.conf` is just a pattern
  filter (`if ($waf_block) return 444`), there's no `limit_req` or anything
  counting requests anywhere in the stack. Both reports match the same
  pattern as the earlier false diagnostics (see below) — the real cause is
  probably that sesame's own HTTP client doesn't reliably complete its
  outbound calls (same root cause as the phantom-token gotcha), and
  misreads that as an external block instead of its own failure.

- **"Can write but can't read" — `result_url` pointed at `.md`, which
  returns `202` while pending.** A client that treats any non-200 as a hard
  error never sees the answer even once it's ready. Fixed 2026-09-30:
  `/ask` now returns `result_url` with `.json` (which is **always** `200`,
  the real state lives in the body's `status` field). Also added explicit
  `Connection: close` on every response (avoids keep-alive ambiguity with
  simple HTTP clients) and `ensure_ascii=True` on all outgoing JSON (avoids
  breaking parsers with low unicode tolerance). `.md`/`.txt` keep the old
  semantics for manual `curl` debugging, no longer the default.

- **Phantom tokens — sesame polls `/result` for tokens that were never
  created by a real `/ask`.** Confirmed at least twice: the token doesn't
  exist in `queue/`, `queue/in_progress/` nor `results/`, and the full nginx
  log has no `/ask` that generated it — the request never actually reached
  our server. No way to recover what the question was (the text never came
  to exist on this side). Likely cause: sesame builds or displays the token
  before confirming the real `/ask` succeeded, and if that call fails/gets
  lost, it's left with a phantom token. Mitigation 2026-09-30: new
  `"status": "invalid_token"` value in `/result/<token>.json` (and `404` on
  `/result/<token>.md`\|`.txt`) when the token isn't anywhere in the system
  — used to return `"pending"`, indistinguishable from a real in-flight
  request, now it can be actively tracked. See `token_is_known()` in
  `app.py`.

- **Negative DNS cache:** if the CNAME was broken for a while before being
  fixed, local resolvers might keep the cached `NXDOMAIN` for ~30 min even
  though the record is already correct. That's why the subdomain is called
  `bridgeai` and not `bridge`. `curl --resolve <domain>:443:<IP>` bypasses
  the local cache to confirm in real time.
- **Never paste the full URL with `?key=...` into a chat with
  auto-preview** (Telegram, WhatsApp, Discord) — the preview bot hits the
  link on its own and leaks the key. **Still happening actively**: every
  real sesame `/ask` arrives duplicated, from two different IPs (Google
  Cloud range) with two different browser user-agents, in the same second —
  each duplicate is an independent token/request, double cost on the real
  backend provider. Not resolved on sesame's side yet. If the key leaks
  further, rotate it (delete `~/aibridge/data/secret.key` on VM105 and
  restart the container — it regenerates itself).
- **`responder-test` (canned/generic) can step on a real agent:** both poll
  the same `/next` for the same `provider` — whoever wins the atomic race
  (`os.rename`) keeps the job. Turned off (2026-09-29) once `claude-agent`
  was in production, because it was answering `grok` questions with
  nonsensical generic phrases (nobody had a real agent there yet) —
  confused sesame, which reported it as a protocol bug when it wasn't.
  Lesson: turn off `responder-test` for any `provider` that already has a
  real agent, or is genuinely unattended (an honest pending beats a made-up
  answer).
- Worth verifying sesame's "bug" reports against the real nginx log
  (`grep 'ask?key\|result/' /var/log/nginx/access.log` on VM101 via `qm
  guest exec 101`) before assuming they're true — happened twice that
  sesame produced plausible-sounding but fabricated diagnoses (an `/ask`
  "bug" returning the answer inline that never happened, and some
  "hypotheses" about v1/v2 API, CDN cache and an orchestrator that don't
  exist in this system).
- `curl -I` sends `HEAD`, not `GET` — the server only implements `GET`,
  returns `501`. Not a bug, on purpose (PoC, didn't need more).
- **The local repo's `docker-compose.yml` can drift from VM105's, and a
  blind `scp` overwrites it** (found 2026-10-01 while adding
  `hermes-agent`): `claude-agent` and `antigravity-agent` were added at the
  time by editing the file **directly on the server** (same pattern as "How
  to add a new agent" above), and those blocks never made it back into the
  local repo. Editing the local compose file to add `hermes-agent` and
  `scp`-ing it over silently wiped VM105's copy, and those two blocks
  disappeared from the file — the containers kept running regardless
  (Docker doesn't touch them just because they stop being listed), but they
  became "orphans" (`docker compose up` warns: `Found orphan containers
  (...)`), and a later `down` or `--remove-orphans` would have actually
  deleted them. Fixed by reconstructing both blocks via `docker inspect
  <container> --format '{{.Config.Image}} {{.Config.Env}} {{.Mounts}}'`
  against the live containers (real ground truth, not memory/guessing) and
  validating with `docker compose config -q` before touching anything live.
  **Lesson**: before `scp`-ing a locally-edited `docker-compose.yml` to
  VM105 again, diff it against the remote first, or reconstruct any missing
  block via `docker inspect` as done here — don't assume the local copy is
  authoritative.
- **The repo's own `.gitignore` (deny-all + extension allowlist) silently
  dropped files with no `.py`/`.sh`/`.md` extension** (found 2026-10-01,
  `git status --ignored` on `aibridge/`): `Dockerfile*` (no extension),
  `docker-compose.yml`, the nginx vhost (`.nginx`), and the ChatGPT Actions
  schema (`.json`) were all silently excluded from any future commit, with
  no warning — `git status` just shows the whole untracked directory, it
  doesn't tell you individual files inside it are being ignored. Fixed with
  scoped `!aibridge/Dockerfile*` / `!aibridge/docker-compose.yml` /
  `!aibridge/*.nginx` / `!aibridge/*.json` / `!upscaler/Dockerfile`
  exceptions, same pattern already used for `<other-project>`'s static
  assets. **Lesson**: after adding a new subproject with file types the
  global `.gitignore` doesn't already allow, run `git status --ignored` on
  it before assuming `git add` will pick up everything that looks present
  on disk.

## Intentional limitations (PoC, not over-engineering)

- `/deposit` travels as a query param — a few-KB ceiling depending on
  nginx. If answers grow, moving to POST with a body is the natural next
  step.
- No reaper: a `/next` that picks up a request and never answers it stays
  stuck in `queue/in_progress/`.
- Single static shared key, no rate-limiting, no deduplication of identical
  requests.
- `/credits` is self-reported — no real agent pushes its own usage yet, not
  a live gauge.
- Pure polling on both ends (`/next` every 10s, `/result` at sesame's own
  interval) — no long-polling or push. Evaluated, not implemented:
  adding `?wait=N` to both `/next` and `/result` so the server blocks until
  there's news (using an in-memory `threading.Condition`, notified from
  `/ask` and `/deposit`) instead of blind polling on both ends — would cut
  "ask → first reaction" latency from up to 10s down to near-instant,
  without leaving stdlib or touching the filesystem-as-source-of-truth
  design.
- No agent has tool access yet (on purpose, see the roadmap section in the
  sesame guide) — planned evolution, timing not decided.
