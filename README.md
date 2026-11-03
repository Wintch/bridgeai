# bridgeai: one private Hermes Agent per person

## What bridgeai is today (2026-11-03)

Each person gets their own stack on VM105: a Hermes Agent with their own memory, keys and files, an Open WebUI web
chat, a voice proxy and nginx. Four stacks run today (`hernik`, `herand`, `hereug`, `hertin`), plus a test guest. A
stack sleeps after 10 idle minutes and a host service (the waker) wakes it on a web visit, a Telegram message or a due
`hermes cron` job. People talk to it in Spanish, Russian or English, by text, voice notes, photos and files, on Telegram
(their own bot) or the web.

**Models.** `aibridge/router.py` sits between Hermes and the models. Today every stack runs "cloud direct": a ranked list
of free cloud models (NVIDIA NIM, Token Harbor's DeepSeek, Gemini, OpenRouter...), best first, with timeouts, cooldowns
and the memory of a weekly allowance that announced its reset. The home GPU hosts (local Gemma, Whisper, Piper,
upscaler, transcoder) are off on purpose since 2026-10-27; with them on, the router is local-first and asks the person
(🔒) before anything goes to the cloud. Each person can add their own free keys on their stack's `/keys/` page.

**Tools beyond Hermes's own** come through one command, `gateway` (`aibridge/gateway.py`): maps and routes with checked
places, weather, the dollar and other live data, QR codes, parallel downloads, video understanding, GPU transcoding,
optional keyed services, monitoring (Zabbix, Proxmox). The skills in `aibridge/SKILL_*.md` and the operator rules in
`aibridge/SOUL_bridgeai.md` tell the agent when to use what. The job-search system (`jobfinder`) is installed per person.

**History.** The project started as `/ask`, a GET-to-GET relay that let one AI ask another. It was stopped on
2026-10-09, retired for its two askers (Sesame, ChatGPT) on 2026-10-11 over Sesame's new terms, and its code was removed
on 2026-11-03 (commit `ec93456`; git history has it, and `HERMES_ARCHITECTURE.md` explains why).

Where to read about each part (all in [`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md)):

| topic | section |
|---|---|
| per-person stacks, sleeping and waking, boot times | "Wake-on-demand", "Boot time after the 2026-10-09 work" |
| adding a person (one command) | "Adding a person" |
| model and key policy, the model guard | "Model and key policy", "Operator alerts and the privacy guard" |
| alerts to the operator (ops Telegram bot) | "Operator alerts and the privacy guard" |
| usage telemetry without personal data, daily and weekly reports | "Usage telemetry without personal data" |
| GPU hosts and Claude machines (`gateway` command) | "Gateways", "GPU desktop as a worker" |
| local first: voice in and out, a local model, videos, rules for small models | "Local first: voice notes and a local model on the GPU host" |
| starting or stopping a GPU host's services, comparing hosts | `gpu-host/run_services.sh`, `gpu-host/bench_hosts.py`, "Runbook: the GPU hosts" |
| local-first router, consent before the cloud, what travels | "Local first with consent: the router" |
| talking with the operator through the ops bot | `aibridge/ops/opschat.py`, "Operator alerts and the privacy guard" |
| what hardware to add for more people | "Capacity plan" |
| what was stopped and why | "Legacy services", "The `/ask` gateway is retired for Sesame and ChatGPT" |
| adding a person whose bot comes later | [`aibridge/ops/NEW_PERSON_STACK.md`](aibridge/ops/NEW_PERSON_STACK.md) |
| the numbered change log (items 1-89) | the numbered list near the top |

**Privacy rule for this public repo:** no names, chat or session ids, personal domains, LAN addresses or host names.
`aibridge/ops/privacy_scan.sh` (git hooks) enforces it against the operator's private list, which never enters git.

## Where things live (which repo, which machine, what never goes to git)

This repo is **public** (`github.com/Wintch/bridgeai`). Rule of the operator (2026-10-09): personal data can be read on the
servers to diagnose a specific problem and is never committed; `aibridge/ops/privacy_scan.sh` (hooks, `--install`) enforces it
against a private list kept outside any repo.

| What | Where | Notes |
|---|---|---|
| bridgeai code, ops scripts, skills, image recipe, docs, lessons that apply to everyone | **this repo** (`bridgeai`, public) | Generic only: stack names (`hernik`, `hereug`, `herand`, `hertin`) are fine, people's names, contacts, chat ids, CV names, message text are not. Use placeholders. |
| The job-search engine (`career-ops`: modes, `scan`, `liveness-*.mjs`, `title_filter`) | the **`jobfinder`** checkout, a fork (`Wintch/career-ops`, branch `integration`, upstream `career-ops-hq`) | Copied into each person's `/workdir/jobfinder`. `buscar-empleos` (Argentine-portal shortcut) is NOT there: it lives here in `aibridge/` and overlaps with the fork's liveness and title filters (open item 20). Generic engine fixes go to the fork. |
| The operator's own job profile (portals list history) | `jobfinder-profile.git`, a local bare repo | Personal. Not this repo. |
| Each person's data: Hermes memory (`USER.md`, `MEMORY.md`), `state.db`, `config.yaml`, `auth.json`, keys, CV and profile, exclusion list (`workdir/jobfinder/config/buscar-empleos.excluir`), uploads | **VM105 only**: `stacks/<name>/persist` and `workdir` (hernik: `hermes-config` and `user1-workdir`) | Root-owned 0600 in part. Backed up by `ops/backup-stacks.sh` (daily, kept on the VM). Never in git. |
| Evidence from diagnosing a person's chat (what they wrote, what Hermes answered) | read on VM105, summarised in the docs without content | Counts, timings, error strings and the shape of the problem go in `HERMES_ARCHITECTURE.md`; quotes and names do not. |
| Forbidden strings for the privacy scan | `~/.config/bridgeai/private-replacements.txt` on the operator's machine | The only place they may be written. |
| Claude Code's own working notes | `~/.claude/projects/.../memory/` | Not part of the product. |

**Deploying is by hand, by the operator** (the agent harness cannot write to VM105, a copy, not a clone):
- `AIBRIDGE_HOST=user@host aibridge/ops/redeploy_router.sh [stack ...]`: every selftest (`ops/run_selftests.sh`), every
  file the image copies, a `prev-<date>` rollback tag, the build (a failed build stops it), then
  `ops/recreate_hermes.sh` for each sleeping stack, which checks the container runs the new image and prints `PASS`.
- `AIBRIDGE_HOST=user@host aibridge/ops/deploy_ops.sh [--apply]`: the VM's `ops/` and user timers in line with the repo.
- Backups: `ops/backup-stacks.sh` daily (people's data plus the operator's config), checked by `ops/backup_watch.py`;
  `ops/restore_stack.sh NAME --drill` proves an archive boots.

## Gotchas already hit (so nobody repeats them)

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
