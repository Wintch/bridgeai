---
title: What a person hears from the system, and what they are asked
scope: every message the host (waker), the router and the gateway send a person on their own, the verbosity level that gates them, and the approvals a person is (not) asked for
when_to_use: adding any message a person receives without asking for it; changing a stack's verbosity; a person says the bot "wakes and sleeps by itself" or bothers them; changing approvals
related: [AGENDA.md, ops/wake/waker.py (person_level, quiet, announce_sleep, WAKE_WHY), router.py (person_verbose), gateway.py (cmd_pref verbosidad), patches/code_auto_approve.py, DATA_SHARING.md, KNOWLEDGE_GAPS.md, hub/HUB.md]
---
# What a person hears, and what they are asked

**Rule (operator, 2026-11-27): a person's bot must not bother them.** The machinery (sleeping, waking, updating, booting) matters to us,
not to them. A message a person did not ask for has to earn its place. One person saw their bot wake and sleep by itself, and did not
understand what was happening.

## 1. Verbosity, per person

`verbosity` in the stack's `/workdir/.prefs.json`. It is set with `gateway pref verbosidad critico|normal|detallado` from the bot, or
by the operator in the file. The older `"verbose": true` reads as `detailed`. The gateway writes the file 0644 (preferences, not
secrets): the waker reads it on the host as another account, and the workdir is an NFS share where the container's root owns what it
makes. No file means `normal`; a file the waker cannot read or parse means `critical`, the quietest level, with one log line per stack.

| Level | Who | What they hear |
|---|---|---|
| `critical` | people who should not be bothered with the machinery (most testers; which stacks: CURRENT_INSTALLATION.md, git-ignored) | answers, the results they asked for, and real problems only |
| `normal` | the default | today's set (table below) |
| `detailed` | the operator's own stack: full diagnosis | everything, and every 💤 names what woke the stack and why it slept |

## 2. Every message, and the level that sends it

| Message | From | critical | normal | detailed |
|---|---|---|---|---|
| 😴 Me eché una siesta… vuelvo en unos N s (they wrote to a sleeping bot) | waker, Telegram wake (`NAP_TEXT`) | yes | yes | yes |
| 💤 Soñando · N s (the stack went to sleep) | waker `announce_sleep` | no; a 💤 left from before is deleted | yes, plain, never with a reason; not after a background wake (below) | yes, every sleep, with "desperté por … · me dormí por …" |
| 🧊 Congelado · N s (host suspend) | waker `host_freezing` | no | yes | yes |
| 🕐 Hay otro Hermes encendiéndose | waker, queued wake | no | yes | yes |
| ✅ Listo para trabajar | waker, after the boot | no | yes | yes |
| Inactivity note of a warm stack | waker `send_idle_notice` | no | yes | yes |
| ⏰ The cron asks to run every N min | waker `plan_cron` | no | yes | yes |
| Update coming / back after the update | waker update notes | no | no | yes |
| Release notice (what changed) | router | no | no | yes |
| ⚠️ No free memory / the boot takes too long | waker | yes | yes | yes |
| Answer to /dormir ("Pedido recibido", "No me pude dormir") | waker | yes | yes | yes |
| Board task results (📋) and done notes | waker | yes | yes | yes |
| An always-on worker's notice (subs: rate limit, stalled backlog), at the person's next message | `ops/worker_notices.py` (hook 60-worker-notices) | no | yes | yes |
| 🕖 Programado · <label>: whatever a run of the person's agenda sends or leaves for them (a reminder, a summary), always with this header so it is never taken for the bot's own words in a chat | the agenda runner on the always-on space (AGENDA.md) | yes, what the entry is for (they asked for it); a failed run follows the worker-notice row | yes | yes |
| 🔒 Cloud consent question, ☁️ cloud line, ⚓ submarine note | router | yes (they are about the person's data) | yes | yes |
| 💡 Pack suggestion (KNOWLEDGE_GAPS.md) | router | yes, only when the person asked for that kind of thing | yes | yes |

**Sleeping, as the person sees it.** They hear about it once, when they write to a sleeping bot: "😴 Me eché una siesta", with the time
to come back. That line goes to every level, because it answers their own message. A scheduled job, a board task, an auto-start, or a
boot the waker did not make (a deploy's or an image update's recreate, `ops/recreate_hermes.sh`) that wakes the stack while nobody talks
to it leaves the person's chat alone: the 💤 already there is kept, and no new one is posted when it sleeps again, also when that sleep is
an update's own stop. A person who uses the stack meanwhile (the waker's wake or the router's `.last_human`) makes it an ordinary sleep. Updates and daily refreshes are never named to anyone but the operator. At the detailed level every 💤 says what woke the
stack (their message too) and why it slept (inactivity, memory for another stack, a request, an update, the daily refresh). The last
background wake is kept in the waker's state (`last_background_wake`).

**Periodic work belongs in the background, not in a person's stack.** Polling and collecting (feeds, job boards, subtitles) run in the
hub (`hub/HUB.md`), which wakes nobody: the stack reads the files when the person comes. Waking a whole stack for a periodic job is the
exception, for work that needs the person's own model. Per-person scheduled scripts (the subtitle round, the night job scan) run on an
always-on machine (`workers/WORKERS.md`): what they used to send becomes a file the stack picks up, never a message from the worker.
What the person asks to repeat is an entry in their agenda (`gateway agenda`, AGENDA.md), never a Hermes cron: the runner on the
always-on space runs it, records it in the work ledger as 🕖 Programado, and anything it sends carries "🕖 Programado · <label>".

**Keeping them company is a hard rule** (operator, 2026-11-27; SOUL "Keep them company"). Before a slow step, the agent says in one
plain line what it is doing, what for and about how long. The people may know nothing about code, but they know life. Quiet about the
machinery, talkative about their task.

## 3. Approvals: what a person is asked

- **Scripts (execute_code): never asked.** The people do not read Python. A whole-script prompt asked them to judge code they cannot
  read, and on a web-only stack it was refused every time, since the web cannot show the prompt. Accepted by default since 2026-11-27
  (`patches/code_auto_approve.py`, `AIBRIDGE_CODE_APPROVAL=auto`). A flagged terminal command run from inside the script still meets
  its own guard. `AIBRIDGE_CODE_APPROVAL=ask` in a stack's compose environment brings the prompt back for that stack.
- **Flagged terminal commands** keep Hermes's approval rules (`approvals.mode: manual`). On a web or API turn they are refused
  (`unattended_mode: deny`).
- **The cloud** is asked once, with what would travel (router, 🔒), unless the stack is `cloud_direct`.
- **Sharing for reviews** is the person's own choice (`/feedback data`, DATA_SHARING.md). It is never asked again unprompted.

## 4. Open

- Which other messages should be quieter at `normal`: decide after a week of the new levels.
- A per-person view for the operator of the last wakes and their reasons, next to the overview (`GET /__wake/all`).
