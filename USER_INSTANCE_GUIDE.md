# User instance guide: what runs where, and how to add your own agent

Audience: a trusted person who gets their own Hermes instance (see
"Architecture decision: one full Hermes instance per human user" in
[`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md)). Written for someone
who is *not* the infrastructure operator, but should still understand
where their data goes and what isolation does and doesn't exist.

**Status note** (updated 2026-11-03): the operator's instance plus one per
person (`aibridge/ops/provision_stack.sh <name>` creates a full stack; the
waker sleeps idle ones, `aibridge/ops/wake/waker.py`). This guide covers two
things: (a) facts that are true for every instance, and (b) a design for
delegating heavy work to a Claude Code machine of your own. (b) is built a
different way than the proposal below: `aibridge/ops/install_claude_gate.sh`
sets up a restricted SSH gate, see "Delegating hard tasks to Claude over SSH"
in [`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md). The proposal text is
kept as history.

## Where does my data actually get processed?

- **Text / conversation**: inside your own container, on the shared Docker
  host (VM105/<docker-host> today). Your conversation memory and config stay
  in your own container's volumes, not shared with anyone else's instance.
- **Images** (e.g. the upscale skill): **not** inside your container.
  They're sent over the LAN, unauthenticated, to a separate machine that
  has a GPU (currently `<gpu-desktop-ip>`). That machine is **shared
  infrastructure** — every instance that gets an image/GPU skill talks to
  the same box, not a copy of it. There is no authentication on that
  service today, and it's explicitly LAN-only (never exposed to the
  internet) — see the "Limits" section of
  [`aibridge/SKILL_image_upscale.md`](aibridge/SKILL_image_upscale.md).
  Your image briefly exists on that machine's disk while it's processed.
- **Anything routed through `aibridge` itself** (e.g. a Claude/Antigravity
  question): processed by whichever agent container answers that
  `provider`, which may be on a different VM than your own Hermes
  instance. See [`README.md`](README.md) for the full request flow.
- Any future heavy-tools service (video, more GPU work, etc.) is expected
  to follow the same pattern as images: a separate, shared machine, called
  over plain LAN HTTP, documented in a skill that says exactly what it does
  and doesn't do — not folded into your own container.

## What's persistent, what's not

Short version: **ask for things to be filed under a named project, or they
might not survive a rebuild.** Full table and the reasoning behind each
line: "What's persistent, what's not" in
[`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md).

- Your conversation history/memory: persistent.
- A file/image you send, or one Hermes generates for you: persistent as
  raw storage (as of 2026-10-01), but **not organized** unless you tell
  Hermes what project it belongs to — see
  [`aibridge/SKILL_project_workspace.md`](aibridge/SKILL_project_workspace.md)
  for exactly how that works. If you want to find something again later,
  say which project/site it's for.
- There is no "switch project" button or command — it's conversational:
  tell Hermes what you're working on, it uses a folder named for that.

## Security model

- **Each user gets a fully separate container**: own config, own
  conversation memory/session state, own credentials (bot tokens, API
  keys). Not a "profile" inside someone else's instance — Hermes's own
  profile feature is explicitly *not* a security boundary between
  different humans (full reasoning in HERMES_ARCHITECTURE.md's
  "Architecture decision" section).
- **What is NOT isolated per-user today**: the heavy-tools host (the GPU
  machine) has no per-user auth or quota. Anyone whose instance has an
  image/video skill can use it, and there's currently no way to tell whose
  request is whose from that machine's side. If this ever needs to change
  (per-user quotas, audit trail, access control), that's new work, not
  something the current design provides.
- **Secrets stay in your own container's environment only** — your bot
  token, your API keys, go in your own instance's `.env` /
  `docker-compose.yml` environment block, never shared across instances,
  never committed to this repo (see this repo's `.gitignore` — anything
  that looks like a key, a `.env` file, or a `*-config`/`data`/workdir
  directory is excluded by design).
- **Provisioning a new instance is a manual, operator-triggered step**, not
  self-service automation — the operator explicitly chose not to automate
  full container creation given how sensitive this project's own tooling
  already is to anything that spins up a new agent-capable container (see
  "Create Unsafe Agents" throughout `README.md` and
  `HERMES_ARCHITECTURE.md`). An invite-key flow has been discussed (a
  trusted person confirms an invite key, which triggers the operator
  generating their container and a key for them to confirm) but that
  invite flow is not built. The provisioning itself is a script the operator
  runs: `aibridge/ops/provision_stack.sh <name>`.

## Getting your own LLM key

Nothing works until your instance has a key of its own. Where to get one (free options first, ordered from simplest to most
involved, paid ones last) and how to load it at `/keys/` is in `aibridge/ops/KEYS_GUIDE.en.md`
(Spanish: `KEYS_GUIDE.es.md`, Russian: `KEYS_GUIDE.ru.md`). Free OpenRouter keys allow 50 requests a day, roughly five working sessions.

## Your own Claude machine (optional)

What exists instead of the old `/ask` proposal (retired 2026-10-11, code removed 2026-11-03): a per-person Claude
machine reached with `gateway claude` over a restricted SSH key (`aibridge/ops/install_claude_gate.sh`), so a heavy task
runs on a machine authenticated as you, with your own quota.

## Scaling (built)

- **One Hermes container per person, one Telegram bot per person**: two gateways cannot long-poll the same bot token,
  and a shared bot would need a router that sees everyone's conversations.
- `aibridge/ops/provision_stack.sh <name>` creates a full stack (runbook: `aibridge/ops/NEW_PERSON_STACK.md`); a bot can
  be added later by the person on `/keys/` or by the operator with `aibridge/ops/stack_telegram.py`.
- **Wake on demand** (`aibridge/ops/wake/waker.py`): stacks sleep after 10 idle minutes; the waker peeks a sleeping
  bot's `getUpdates` without advancing the offset, so no message is lost, and starts the stack within a RAM budget
  (VM105 has 7 GB; four people's stacks and a guest fit because most sleep).

## Open questions (explicitly deferred)

- How automated container provisioning should ever become, beyond the
  single manual step the operator already decided on (see
  `HERMES_ARCHITECTURE.md`).
- Whether the heavy-tools host should eventually become per-user
  (authenticated, quota'd) or stay shared infrastructure indefinitely.
- How this transparency information should reach a new person beyond the web welcome banner and the bot's first
  reply about a shared key (`aibridge/ops/welcome*.md`).
