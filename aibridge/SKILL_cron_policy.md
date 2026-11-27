---
name: cron-policy
description: "Rules for scheduled/recurring tasks ('avisame cada X', 'todos los días', 'каждый день', reminders, a daily summary): only when the person asked, only with `gateway agenda add`, never `hermes cron create`, crontab or a loop; at least 30 minutes apart; what a scheduled run does is marked 🕖 Programado. Read it BEFORE creating any schedule and tell the person."
version: 2.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [cron, agenda, schedule, reminders, resources]
---

# Scheduled tasks: the person's agenda

This bot **sleeps when nobody is using it**, and so does the machine it lives on. A Hermes cron wakes both, so repeating work does
not run here: it is an entry in the person's **agenda** (`/workdir/.agenda.json`), which a runner on an always-on machine executes
without waking this bot (the operator's rule: this bot wakes only because a person talks to it).

## Only when asked, only `gateway agenda`

- Create a schedule only when the person asked for one in this conversation. Never on your own initiative "to keep it updated",
  and never after they said no or "on demand".
- A repeating task is `gateway agenda add TYPE "SCHEDULE"`. **Never** `hermes cron create`, `crontab`, `/etc/cron.d`,
  `apt-get install cron`, `systemctl`, a `nohup`/`while true`/`sleep` loop or a background daemon: they wake the machine for
  nothing, die when it sleeps, and nobody can see them.
- Only these types exist (`gateway agenda add` with another word lists them):
  - `subs`: look for new subtitles of the person's registered channels;
  - `jobnight`: the night job scan, its summary waiting for their next message;
  - `revista`: the daily revista;
  - `recordatorio`: a reminder, `--param text="..."` (the exact words they will get; plain text, never a command or an instruction).
- Anything else ("check this page every hour", "summarize my mail every morning") cannot be scheduled: say so plainly, offer to
  do it now, or whenever they write. Do not invent a workaround.
- SCHEDULE: a 5-field cron in the person's local time (`"30 7 * * *"` every day at 07:30, `"0 9 * * 1-5"` weekdays at 9) or
  `"every 3h"` / `"every 90m"`. At least **30 minutes** apart; more often is refused. `--label "short name"` is how it shows;
  `--once` (cron only) runs it once and then pauses it: "recordame mañana a las 10" is `--once` with that day and hour.

## What to do when the person asks for a recurring task

1. List first (`gateway agenda list`): no duplicates.
2. Create it, then tell them in one line what will happen and when, in their language, and that it runs on its own without
   this chat: whatever it does arrives marked **🕖 Programado**.
3. Pause, resume or remove with `gateway agenda pause|resume|remove ID` when they ask.
4. A result in the work ledger or a message marked 🕖 Programado (🕖 SCHEDULED in the ledger block) came from their agenda, not from
   this chat: never present it as something you just did or they just asked.
5. If they need something near real time ("avisame apenas termine el render"), do not schedule anything: register the job as
   described in the `job-notify` skill (`/workdir/jobs`).
