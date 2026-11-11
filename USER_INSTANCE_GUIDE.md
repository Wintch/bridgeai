# User instance guide: what runs where

Audience: a trusted person who gets their own Hermes instance. Written for someone who is not the infrastructure operator but should
understand where their data goes and what isolation does and does not exist. The person's day-to-day manual is in
[`aibridge/manual/`](aibridge/manual/); the reasoning for one instance per person is in the architecture decision in
[`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md).

## Where your data is processed

- **Text and conversation:** inside your own container on the shared Docker host. Your memory and config live in your own volumes and are not
  shared with any other instance.
- **Images, video and speech:** not inside your container. A gateway command (`gateway image`, `transcode`, `upscale`, `makevideo`, ...) sends the file
  over the private network to a **shared GPU host**. Every instance that has such a skill uses the same host. Some services require a bearer token
  (image, video, datamosh); the transcoder and upscaler accept an optional one. Hosts are never exposed to the internet. Your file exists on the
  host's disk only while it is processed.
- **Model calls:** go through `aibridge/router.py`, which uses your own keys. With a local model running it asks you before anything goes to a cloud
  provider (see the manual).

## What is persistent

Ask for things to be filed under a **named project**, or they may not survive a rebuild. Conversation history and memory persist. A file you send, or one
Hermes generates, is kept as raw storage but is not organized unless you say which project it belongs to (see
[`aibridge/SKILL_project_workspace.md`](aibridge/SKILL_project_workspace.md)). There is no "switch project" command: tell Hermes what you are working on.

## Security model

- **Separate container per person:** own config, conversation memory, session state and credentials (bot token, API keys). Hermes's own profile
  feature is not a security boundary between humans.
- **Not isolated per person:** the GPU host has no per-person quota or audit trail; whoever's instance has a media skill can use it.
- **Secrets stay in your container's environment** (`.env`), never shared across instances and never committed (`.gitignore` excludes keys, `.env`
  files and data directories).
- **Provisioning is an operator step**, not self-service: `aibridge/ops/provision_stack.sh <name>` (runbook `aibridge/ops/NEW_PERSON_STACK.md`).
  A bot can be added later by the person on `/keys/` or by the operator with `aibridge/ops/stack_telegram.py`.

## Your own keys

Nothing works until your instance has a key of its own. Free options first, paid last, and how to load a key at `/keys/`:
`aibridge/ops/KEYS_GUIDE.en.md` (Spanish `KEYS_GUIDE.es.md`, Russian `KEYS_GUIDE.ru.md`).

## Your own Claude machine (optional)

`gateway claude` reaches a Claude Code machine of your own over a restricted SSH key (`aibridge/ops/install_claude_gate.sh`), so a heavy task runs
authenticated as you, with your own quota.

## Wake on demand

One Hermes container and one Telegram bot per person (two gateways cannot long-poll the same bot token). A stack sleeps after 10 idle minutes; the
waker (`aibridge/ops/wake/waker.py`) peeks a sleeping bot's `getUpdates` without advancing the offset, so no Telegram message is lost, and starts the
stack within a RAM budget.
