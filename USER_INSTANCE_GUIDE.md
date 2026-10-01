# User instance guide: what runs where, and how to add your own agent

Audience: a trusted person who gets their own Hermes instance (see
"Architecture decision: one full Hermes instance per human user" in
[`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md)). Written for someone
who is *not* the infrastructure operator, but should still understand
where their data goes and what isolation does and doesn't exist.

**Status note**: today there is exactly one running instance (the
operator's own). This guide covers two things: (a) facts that are already
true about that instance and would stay true for any future one, and
(b) a proposed design for onboarding a second instance, explicitly marked
as not built yet. Don't read (b) as documentation of something that
exists — it's a plan, written down before being built on purpose, so the
security model is decided before anyone's real data depends on it.

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
  generating their container and a key for them to confirm) but the actual
  provisioning script does not exist yet.

## Adding your own agent (design proposal, not built yet)

**Scenario**: you have your own Claude Pro subscription and want your
Hermes instance to be able to delegate a heavy or high-quality request to a
real Claude Code agent authenticated as *you* — running with more compute
than your own instance's container, and not sharing the operator's own
Claude usage/quota.

**Proposed flow** (reusing `aibridge`'s existing protocol instead of
inventing a new one — this is the same "it's a bridge, from here you jump
to machines with special capabilities" pattern already proven by the
image-upscale skill, just pointed at a CPU/compute-heavy VM instead of a
GPU one):

1. The operator provisions a `claude-agent` container specifically for you
   (same shape as the existing `claude-agent` block in
   `aibridge/docker-compose.yml`), on a VM with spare compute. You log in
   interactively once with your own account (`claude login` inside that
   container) — same one-time manual pattern already used for every other
   agent in this project.
2. `aibridge` issues a new key/label for it (same mechanism already used
   for `"chatgpt"` — `ensure_key_for_label()` in `aibridge/app.py`), tied
   to a provider name meant only for your Hermes instance, e.g.
   `claude-<your-name>`.
3. Your Hermes instance gets a small skill (same shape as
   `SKILL_image_upscale.md`) that tells it explicitly: *"for heavy or
   complex requests, you can delegate to a separate, more capable Claude
   instance on another machine by calling `aibridge`'s
   `/ask?provider=claude-<your-name>&key=<your key>` and polling
   `result_url`."* The skill needs to say plainly that this is a
   **different machine with more compute**, not itself — so the agent uses
   it deliberately for requests that actually need it, not reflexively for
   everything (same cost-awareness framing as the image skill: say so if
   it fails, don't retry in a loop, don't fabricate a result).
4. This needs Hermes to make one specific outbound HTTP call — today no
   agent in this project has broad tool access by design (see the
   roadmap note in `aibridge/GUIDE_ASKING_AGENT.md`). A skill scoped to
   exactly one `curl` call against `aibridge`'s own API is the same narrow
   shape already proven safe by `image-upscale`, not a general
   compute/write capability — the same reasoning applies here.

**Not decided or built yet**: the actual per-user `claude-agent` container,
the key-issuance step, the skill file itself, which VM would host it. This
section is the design to build toward, not a working feature.

## Open questions (explicitly deferred)

- How automated container provisioning should ever become, beyond the
  single manual step the operator already decided on (see
  `HERMES_ARCHITECTURE.md`).
- Whether the heavy-tools host should eventually become per-user
  (authenticated, quota'd) or stay shared infrastructure indefinitely.
- How this transparency information should actually reach a new user when
  they sign up — today it's only written down here, not surfaced as an
  actual onboarding message inside the bot itself.
