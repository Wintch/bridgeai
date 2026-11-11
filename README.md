# bridgeai: one private Hermes Agent per person

bridgeai runs a separate [Hermes Agent](https://github.com/NousResearch/hermes-agent) for each person who uses it,
on one VM, with optional GPU machines at home for voice, pictures and video. Each person has their own memory, keys and
files, talks to it on Telegram (their own bot) or a web chat, in Spanish, Russian or English, by text, voice notes,
photos and files. MIT licence.

Terms used in these docs: a **stack** is one person's set of containers; the **operator** is whoever runs the servers; a **pack** is a switchable
group of skills (`aibridge/skill_packs.json`); the **waker** is the host service that sleeps and wakes stacks; **gateway** is the one command the
agent uses for tools; a **GPU host** is a machine that runs the media services.

## What it does

- **One stack per person.** Hermes Agent, an Open WebUI web chat, a voice proxy and nginx. A stack sleeps after
  10 idle minutes; a host service (the waker) wakes it on a web visit, a Telegram message or a due `hermes cron` job,
  in 20-30 s. Adding a person is one command (`aibridge/ops/NEW_PERSON_STACK.md`).
- **Models.** `aibridge/router.py` sits between Hermes and the models: a ranked list of free cloud models (NVIDIA NIM,
  DeepSeek through Token Harbor, Gemini, OpenRouter, ...) with timeouts, cooldowns and remembered allowance resets.
  With a local model running it is local-first and asks the person before anything goes to the cloud. Each person adds
  their own free keys on the stack's `/keys/` page.
- **Tools.** One command, `gateway` (`aibridge/gateway.py`): maps and routes with checked places, weather and other live
  data, QR codes, parallel downloads, video understanding, virus lookups (hash + local ClamAV), monitoring (Zabbix,
  Proxmox, read-only), and the GPU media verbs `image`, `makevideo`, `enhance`, `prompt-of`, `upscale`, `transcode`.
  The skills (`aibridge/SKILL_*.md`), the packs that switch groups of them on (`aibridge/skill_packs.json`) and the
  operator rules (`aibridge/SOUL_bridgeai.md`) tell the agent when to use what.
- **GPU machines, on demand.** `gpu-host/run_services.sh` starts the services on a GPU host (containers with
  `GPU_RESTART=no` in `host.env`, so they stay off until needed): image generation (imggen), text-to-video with sound
  (vidgen, MiniMax H3, 2 to 10 s per clip, or 15 to 30 s chained from 10 s parts), video finishing (vidpost: 2x upscale and 48 fps, processed in pieces), upscaler, transcoder, speech in
  and out, and an optional local LLM. An older Pascal card runs vidpost from a venv (`gpu-host/vidpost/run_venv.sh`).
- **Hermes changes.** Build-time patches to Hermes (`aibridge/patches/`, applied by `aibridge/Dockerfile.hermes-agent`)
  and plugins (`aibridge/hermes_plugins/`). Each patch aborts the build if Hermes's code moved.

## Where things are

| Path | What |
|---|---|
| `aibridge/` | the Hermes image (Dockerfiles, `router.py`, `gateway.py`, skills, SOUL, patches, plugins, manual) and its selftests |
| `aibridge/ops/` | operator scripts: deploy, recreate, backups, waker (`wake/`), keys page, guides for new people |
| `aibridge/manual/` | the person's manual in es, en, ru (also as a PDF from the bot) |
| `aibridge/hub/` | the read-only feed collector shared by the stacks |
| `gpu-host/` | GPU services (imggen, vidgen, vidpost), `run_services.sh`, power cap, benchmarks (`videobench/`) |
| `upscaler/`, `transcoder/`, `stt/`, `tts/`, `llm/` | the older GPU service images (`stt/` also holds the VM's voice proxy) |
| `seams/`, `crossweft.json` | the seams check run by the git hooks |
| `reports/`, `research_notes/` | research working notes, not maintained documentation |

## Documentation

| Topic | Read |
|---|---|
| architecture, decisions and the change log | [`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md) (long; search for the section) |
| what the bot can do, per pack | [`aibridge/CAPABILITIES.md`](aibridge/CAPABILITIES.md), [`aibridge/manual/`](aibridge/manual/) |
| every API and MCP integration, with diagrams | [`aibridge/INTEGRATIONS_MAP.md`](aibridge/INTEGRATIONS_MAP.md) |
| adding a person; the person's own guides | [`aibridge/ops/NEW_PERSON_STACK.md`](aibridge/ops/NEW_PERSON_STACK.md), [`USER_INSTANCE_GUIDE.md`](USER_INSTANCE_GUIDE.md), `aibridge/ops/KEYS_GUIDE.*.md`, `TELEGRAM_GUIDE.ru.md` |
| GPU media: what is built, models per card, renting, measured results | [`aibridge/GPU_RENTAL_AND_MODELS.md`](aibridge/GPU_RENTAL_AND_MODELS.md), [`aibridge/GPU_MEDIA_TOOLS.md`](aibridge/GPU_MEDIA_TOOLS.md), [`aibridge/VIDEO_BENCH_RESULTS.md`](aibridge/VIDEO_BENCH_RESULTS.md) |
| remote machines with credit (`gateway maquina`), a person's Telegram channel (`gateway canal`), a blob store design | [`aibridge/MACHINES.md`](aibridge/MACHINES.md), [`aibridge/CANAL.md`](aibridge/CANAL.md), [`aibridge/BLOB_STORAGE.md`](aibridge/BLOB_STORAGE.md) |
| Telegram feature map and other chat fronts | [`aibridge/TELEGRAM_FEATURES.md`](aibridge/TELEGRAM_FEATURES.md), [`aibridge/MESSAGING_FRONTS.md`](aibridge/MESSAGING_FRONTS.md) |
| image hardening and audits | [`aibridge/ops/IMAGE_SECURITY.md`](aibridge/ops/IMAGE_SECURITY.md) |
| upstream Hermes releases against our pin | [`aibridge/HERMES_UPSTREAM_SCAN.md`](aibridge/HERMES_UPSTREAM_SCAN.md) |
| a public intake bot linked from a website (planned, not built) | [`aibridge/PUBLIC_INTAKE_PLAN.md`](aibridge/PUBLIC_INTAKE_PLAN.md) |
| "Persona del día": one community member's service, once a day on wake | [`aibridge/ops/DAILY_AD.md`](aibridge/ops/DAILY_AD.md) |
| personal-data law (Argentina, Ley 25.326) and key hygiene with KeePassXC | [`aibridge/DATA_LAW_AND_KEYS.md`](aibridge/DATA_LAW_AND_KEYS.md) |
| generative safety: model licences and built-in safety, legal duties when running them for others, guard plan | [`aibridge/GENERATIVE_SAFETY.md`](aibridge/GENERATIVE_SAFETY.md) |
| layered review of people's websites: automatic gate, specialist reviewer Hermes per concern, previews, per-person site parts (design only) | [`aibridge/WEB_REVIEW_LAYERS.md`](aibridge/WEB_REVIEW_LAYERS.md) |
| `sysadmin`: a person audits and looks after their own servers from their Hermes (phase F0 built), and the security guide it cites | [`aibridge/SYSADMIN_PLAN.md`](aibridge/SYSADMIN_PLAN.md), [`aibridge/security/`](aibridge/security/README.md) |
| several bots for one person, a local Gitea as task board and audit trail between them, handing a bot to another person, an interpreter idea (design only) | [`aibridge/MULTI_BOT_TASKS.md`](aibridge/MULTI_BOT_TASKS.md) |
| setting up that task board for one owner's bots: admin token, `ops/tareas_setup.py`, firewall lines, who files for whom, packs, test (runbook, not run yet) | [`aibridge/ops/TAREAS_SETUP.md`](aibridge/ops/TAREAS_SETUP.md) |
| step-up authentication for dangerous operations: risk classes, TOTP bound to the action, passkeys on our own page, signed approvals (design only) | [`aibridge/STEP_UP_AUTH.md`](aibridge/STEP_UP_AUTH.md) |

## Test and deploy

- **Test:** `aibridge/ops/run_selftests.sh` runs every offline selftest (fake hosts, fake ComfyUI, no GPU, about a
  minute). The pre-push hook runs it too, with `aibridge/ops/privacy_scan.sh`.
- **Deploy is by hand, by the operator** (the VM holds a copy, not a clone):
  - `AIBRIDGE_HOST=user@host aibridge/ops/redeploy_router.sh [stack ...]`: selftests, copies every file the image needs,
    tags the old image `prev-<date>`, builds, then recreates each sleeping stack and checks it runs the new image.
  - `AIBRIDGE_HOST=user@host aibridge/ops/deploy_ops.sh [--apply]`: the VM's `ops/` and timers in line with the repo.
  - Backups: `aibridge/ops/backup-stacks.sh` daily, checked by `backup_watch.py`; `restore_stack.sh NAME --drill`
    proves an archive boots.
- **Gotcha:** before copying a locally edited `aibridge/docker-compose.yml` to the VM, diff it against the VM's copy.
  A blind copy drops service blocks that exist only on the server, and their containers become orphans.

## Privacy

This repo is public. Personal data may be read on the servers to diagnose a problem and is never committed: no people's
names, contacts, chat or session ids, message text, personal domains, LAN addresses or private host names. Each person's
memory, keys, files and backups live only on the VM. `aibridge/ops/privacy_scan.sh` (git hooks) enforces the rule
against the operator's private list, which never enters git.

## Open work

- Splitting the long architecture document into a `docs/` tree.
- Open designs (pool broker and GPU lease, blob store, step-up authentication, public intake bot) are listed in their own documents above.

The job-search engine is a separate fork (`career-ops`, installed per person in `/workdir/jobfinder`).
