---
name: job-notify
description: "Get a Telegram message when a long job (render, transcode, remote task) finishes, for free and without polling it yourself: register the job in /workdir/jobs and the always-on `jobwatch` cron job reports it."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [notifications, cron, long-running, telegram]
---

# Job notify

A cron job named `jobwatch` runs every minute with **no LLM** (so it costs nothing) and reads
`/workdir/jobs/*.json`. When a registered job is done it sends the user a Telegram message with
the result and deletes the entry. Use it whenever a task will take more than a couple of minutes
and the user should not have to ask "is it done?". Do not build your own polling loop or webhook
for this: that was tried and never fired.

## Register a job (do this right after starting the long task)

```bash
mkdir -p /workdir/jobs
cat > /workdir/jobs/render-$(date +%s).json <<JSON
{"title": "Render del video X (marca de agua)",
 "pid": $PID,
 "done_file": "/web-outputs/<uuid>/result.mp4",
 "output": "/hermes-files/<uuid>/result.mp4",
 "started": $(date +%s),
 "timeout_min": 60}
JSON
```

Fields (give at least one of `pid`, `done_file`, `check_cmd`; the job counts as done when ANY of
them says so):

- `pid`: the process id of the background command (use the real PID of ffmpeg/the script; a
  finished or zombie process counts as done).
- `done_file`: a path that exists only once the work is complete (write the final file to a
  temporary name and rename it into place so a half-written file never matches).
- `check_cmd`: a shell command that exits 0 when finished, 20s limit. For work on another
  machine, e.g. `ssh resolve-host 'test -f /path/out.mp4'`.
- `title`: what the user will read. `output`: optional, appended to the message (a
  `/hermes-files/...` link only works for the web UI; for Telegram send the file as usual or give
  the path).
- `started`: epoch seconds. `timeout_min`: default 120; after that the user gets a "did not finish"
  notice and the entry is dropped.

## Rules

- Tell the user you registered it and roughly how long you expect it to take; do not claim the
  notification worked before it did. The message arrives on the user's **Telegram** home chat,
  not in the web UI, so for someone using only the web say they must check the chat.
- One JSON file per job; the name does not matter. Never put secrets in it.
- If `hermes cron list` does not show a `jobwatch` job, say so plainly and tell the operator
  instead of inventing another mechanism.
