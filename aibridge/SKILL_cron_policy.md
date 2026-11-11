---
name: cron-policy
description: "Rules for scheduled/recurring tasks (cron, 'avisame cada X', 'todos los días', 'каждый день', reminders, watchers): only when the person asked, only with `hermes cron`, never crontab or apt; a task fires at most once per hour. Read it BEFORE creating any schedule and tell the person."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [cron, schedule, reminders, resources]
---

# Scheduled tasks on this server

This instance **sleeps when nobody is using it** (to save RAM). A sleeping instance cannot run anything, so a host
service wakes it only when a scheduled task is due, and only on an hourly grid:

- A task fires **at most once per hour**, whatever schedule it asks for. "Every minute" or "every 5 minutes" will in
  practice run every ~60 minutes, at a time shifted by the server (not at an exact minute).
- Several tasks due in the same hour are run together in one wake-up, then the instance goes back to sleep.
- Nothing wakes the instance if no task is due.

## Only when asked, only `hermes cron`

- Create a schedule only when the person asked for one in this conversation. Never add one on your own initiative
  "to keep it updated", and never after they said no or "on demand" (an agent once installed `cron` with
  `apt-get` and scheduled a daily scrape the person had just declined; it vanished on the next restart anyway).
- Use only `hermes cron` (the host service that wakes the instance reads its list). Never `crontab`, `/etc/cron.d`,
  `apt-get install cron`, `systemctl`, a `nohup`/`while true`/`sleep` loop or a background daemon: they do not survive
  the instance sleeping or being recreated, nothing wakes the instance for them, and nobody can see them.
- Never install system packages (`apt`, `apt-get`, `dpkg`, `sudo`). If something is missing, say what and that the
  person can ask the administrator.

## What to do when the person asks for a recurring task

1. **Tell them first**, in their language and in one line: "Las tareas programadas acá se disparan como máximo una vez
   por hora (el servidor duerme las instancias que no se usan); no puedo prometer exactitud al minuto."
2. (Hermes itself refuses any schedule that runs more often than every 5 minutes; the rule below is stricter on purpose.) Create it with an interval of **60 minutes or more** (`every 1h`, daily, weekly). Do **not** create `every 1m`/`5m`/`15m`.
3. If they need something near real time ("avisame apenas termine el render"), do not use a cron: register the job as
   described in the `job-notify` skill (`/workdir/jobs`): while a registered job exists the instance is kept awake and
   they get a message when it finishes.
4. Do not create duplicates: list the existing jobs first (`hermes cron list`).
5. If it is a one-off ("recordame mañana a las 10"), use a one-shot schedule, not a recurring one, and say that the
   reminder can be up to an hour late.
