---
title: Always-on workers - scheduled jobs away from the sleeping Docker host
scope: the worker runner (workers/worker.py), the host-side apply step (workers/apply.py), the two job types (subs, jobnight), who owns which file, the pull/push rules, local data (local_workdir), the events, installing it on an always-on host, and moving a job off a stack
when_to_use: a scheduled or always-running job wakes a person's stack; adding a job type to the worker; a file the worker pushed looks wrong; moving a cron off a stack or back; planning the broker's WORK_<type> queues
related: [workers/worker.py, workers/apply.py, workers/install.sh, workers/workers.json.example, workers_selftest.py, subs_new.py, subs_fetch.py, jobnight.py, jobpush.py, ops/wake/on_wake.d/50-job-summary, ops/job_summary.py, ops/project_publish.py (host_awake), ops/project_sync.py, ops/lib/bus.py, start_hermes.sh (jobnight), gateway.py (avisos_cron), NOTICES.md, hub/HUB.md]
---
# Always-on workers

**Rule (operator, 2026-11-27): a person's bot wakes only because a person talks to it.** Scheduled or always-running work moves to an
always-on machine: one of the Proxmox hosts that never sleep, a Debian VM with Docker. The Docker host that holds the stacks suspends
itself when idle; until now two Hermes crons woke it (and a stack) on their own:

| Type | The cron it replaces | What it runs (already in the stacks' image) | Default schedule | What goes back to the person |
|---|---|---|---|---|
| `subs` | `subs-nuevos`, every 3 h, `--no-agent --script subs_new.py --deliver telegram` | `/root/.hermes/scripts/subs_new.py` (calls `/usr/local/bin/subs-fetch`) | `*-*-* 00/3:00:00` | new subtitle files, the scan state, notice files |
| `jobnight` | `jobnight`, 04:30, `--no-agent --script jobnight.py --deliver local` | `/root/.hermes/scripts/jobnight.py` (= `jobpush.py --night`) | `*-*-* 04:30:00 <person's zone>` | the night summary (merged), early-alert lines |

A **worker** is one run of one job type for one person: a one-shot container of the stacks' own image on the always-on machine, fed
with a local copy of exactly the files the script reads, and whose results go back to the person's workdir on the Docker host by fixed
ownership rules. The job names only its TYPE and the person's paths (workers.json); the method (what to copy, how to run, what goes
back) lives in worker.py. No broker yet: files.

```
 always-on host (systemd --user timers)                                Docker host (asleep most of the time)
 worker.py run <type>  ──ssh true? ── no ──► use the last copy (or skip)
        │ yes                                                          aibridge/stacks/<stack>/workdir/  (the person's)
        ├─ pull: rsync ◄─────────────── only the files the job reads ── descargas/ (registered channels) | jobfinder/ + .prefs.json
        ├─ docker run --rm <image> (no keys, caps, timeout) on copy/
        ├─ outputs -> outgoing/   (wait there while the host sleeps)
        └─ push (and every few min: worker.py sync, when awake):
             rsync outgoing/ ─────────────────────────────────────────► aibridge/worker-inbox/<stack>/<type>/ (the worker's)
             ssh: apply.py (one-shot container of the image, as root) ─► by the ownership rules into the workdir
```

## 1. Who owns which file

The worker never writes a file the person or their bot owns. A file it owns goes back; a file both sides write goes back only when the
host's copy is not newer; anything else stays on the worker. Nothing is ever deleted on the Docker host (no `--delete` towards it).

**subs** (the person's `/workdir/descargas`; only `channels.json`, the folders it registers and `.subs-cooldown` are copied: the rest of
their downloads never leaves the host)

| File | Owner | Pull (host -> worker) | Push (worker -> host) |
|---|---|---|---|
| `channels.json` (the registry: the person adds channels through their bot) | person | always, the host's wins | never |
| `<channel>/*.srt` already on the host | person | when the worker lacks it (`--ignore-existing`) | never |
| `<channel>/*.srt` the worker's run created | worker | - | only when that name does not exist on the host; never replaced; a file the person deleted after a push is not sent again |
| `<channel>/.nocaps.tsv .unavailable.tsv .ids.cache .subs-progress.json`, `.subs-cooldown` (scan state, the pause) | shared | when the host's is newer (`--update`) | when the host's is not newer |
| `.subs-metrics.jsonl .subs-stall.json .subs-slot-* .subs-list-*` (the schedule's own bookkeeping) | worker | never | never |
| `.subs.lock .todo.txt *.vtt *.part` (transient) | - | never | never |
| `/workdir/.worker-notices/subs-<time>.txt` | worker | - | new files only |

The shared scan state is "last writer wins by time": if the person's bot runs `subs-fetch` by hand on the stack while the worker also
works, a line of `.nocaps.tsv` can be lost; the cost is asking a few videos again, never a lost subtitle. Two places downloading at once
also share one address's rate limit (`.subs-cooldown` travels both ways, the newer wins), so keep the hand runs on the stack rare.

**jobnight** (the person's `/workdir/jobfinder`, without `.git/ output/ reports/ interview-prep/ batch/logs/`, plus `/workdir/.prefs.json`)

| File | Owner | Pull | Push |
|---|---|---|---|
| code, `node_modules/`, `portals.yml`, `config/`, `cv.md`, `jds/`, tracker (`data/applications.md`), `data/pipeline.md` | person (and project_sync for the code) | always, the host's wins (`--delete` on the LOCAL copy only, the worker's files excluded) | **never** |
| `/workdir/.prefs.json` (`avisos`, `lang`) | person | always (mounted read-only) | never |
| `data/.jobpush-pending.json` (the night summary) | worker -> person | never | **merged** into the host's file under jobpush.py's own lock (`data/.jobpush-pending.lock`), with jobpush.py's merge rules, so a summary still waiting there is kept and added to |
| `data/.jobpush-state.json` | split | only `closing_told`, `expired_told`, `last_message`, `night_done` (what the hand-over and an old stack run write) are merged in | never |
| `data/scan-history.tsv jobpush.log .jobpush-carry.json scan-runs.tsv run-timings.tsv` | worker (seeded once from the host) | only when the worker has none | never |
| `data/.jobpush-prescan.json .jobpush-running .jobpush-chain.out jobpush-scan.log *.lock` | worker | never | never |
| `/workdir/.early-signals.jsonl` (ops/early_alert.py's sink) | append-only | - | lines appended (known keys only) |

**jobpush --night writes person-owned files**: the scan (`scan.mjs`, through `scheduled-chain.mjs`) appends the new offers to
`data/pipeline.md`, which the person's bot also edits. Copying it back would undo whatever the bot did there since the pull. So only the
summary goes back (the safe option). It carries every offer with its link, title and company; when the person gets it (waker hook
`50-job-summary` on Telegram, the router on the web chat, or the bot's own `--pending peek/ack`), `--pending ack` writes `push-last.md`
on the host, and "evaluá" works on those offers as before. What changes: the host's `pipeline.md` no longer receives the night's
offers. On the worker, the offers its runs added are remembered (`pipeline-added.jsonl`, 14 days) and added again to the LOCAL
`pipeline.md` after each pull, so an offer carried to the next night (more than 40 new, or the time budget) is not lost. If the operator
wants them in the host's `pipeline.md` too, the safe way is a person-side merge (the bot or a stack hook appends under scan.mjs's
pipeline lock), not the worker.

## 2. Pull and push

- **Awake?** `ssh -o BatchMode=yes -o ConnectTimeout=8 aibridge@<host> true` (ops/project_publish.py `host_awake`). Asleep means
  "later": no pull, no push, never a wake, never an alert.
- **Pull** only when awake, right before a run. Asleep: the run uses the last copy; with no copy yet, it is skipped
  (`skipped_host_asleep` with `has_copy=false`). A pull that fails with a copy present runs on the copy.
- **Push** right after a run when awake, else the outputs wait in `<state_dir>/<stack>/<type>/outgoing/` and `worker.py sync` (timer,
  every `sync_every_min`, default 2) sends them once the host is up for any reason. The worker writes only into its inbox
  (`aibridge/worker-inbox/<stack>/<type>/`, the aibridge user's), then runs apply.py on the host: by default in a one-shot container of
  the image as root with `--network none` (the workdir's files belong to the stack's root, as for ops/project_sync.py's node_modules);
  `"apply": "direct"` uses the host's python3 as aibridge. Applied files leave the inbox; a failed one stays and is retried.
- **Timing of the summary**: the Docker host sleeps at 04:30, so the summary usually reaches the host when someone next uses it. If the
  person's own Telegram message is what wakes it, the `50-job-summary` hook may run before the sync lands (sync every 2 min, a stack boot
  takes 80-145 s): then the summary waits for their next wake. On the web chat the router reads it on every answer, so there it is never late.

## 2b. Local data (`local_workdir`)

When the operator has moved a person's workdir to the always-on machine itself (it lives there, and the Docker host mounts it back over
NFS), copying it back and forth is pointless: the data is already where the worker runs. A person with
`"local_workdir": "/abs/path/to/their/workdir"` (instead of `remote_workdir`) runs in **local mode**:

- no pull, no push, no ssh, no "is the host awake?" (an asleep Docker host does not matter); `host` may be left out of the config when
  every person is local;
- the container mounts the **real** folders: jobnight `<local_workdir>/<jobfinder_dir>` (rw) and `<local_workdir>/.prefs.json` (ro);
  subs `<local_workdir>/<subs_dir>` (rw). Same image, caps, limits, no keys, no gateways.json, no shared store;
- jobnight works **in place, exactly as the stack's own cron did**: jobpush writes the night summary (merged under its own lock with
  one still waiting), its state and the pipeline in the person's jobfinder. So the ownership table of section 1 does not apply to
  those files in this mode; the person's bot and the night run share them as they did when both ran in the stack;
- only what the cron printed or sent elsewhere goes through apply.py, run on this machine with the same rules (`apply`: `docker` = a
  one-shot container of `host_image` as root with no network; `direct` = this python3): the early-alert lines (appended, known keys)
  and the subs notices (`.worker-notices/`, never replaced);
- the files the job wrote are **not** chowned to the worker's user (they stay the stack's, as its own cron left them).

Move the job off the stack the same way (section 7). The Docker host still delivers the summary (waker hook `50-job-summary`, the web
router): it reads the same file through its NFS mount.

## 3. Notices (what the cron delivered to Telegram)

`subs_new.py` prints only when a human must know (a rate limit, a failure, a backlog stalled for 24 h); Hermes delivered that to
Telegram. The worker never sends Telegram messages. **Choice:** each printed block becomes a file
`/workdir/.worker-notices/subs-<UTC time>.txt` in the person's workdir (never replaced), plus a `notice` event (a count) for the
operator. The bot is told in SKILL_downloads.md where they are. At the person's next Telegram message, the wake hook
`ops/wake/on_wake.d/60-worker-notices` (`ops/worker_notices.py`) sends them through the stack's own bot and moves each to
`.worker-notices/sent/`; a person at verbosity "critical" is not sent these machinery notices (moved to `skipped/`, NOTICES.md).

## 4. The container

`docker run --rm --restart=no --network bridge` (the default bridge, never the host network) of `image` (the stacks' image, the same
build), `--memory/--memory-swap`, `--cpus`, `--pids-limit` and a hard timeout from `types.<type>` (on timeout: `docker kill`, event
`failed` reason `timeout`). The stacks' hardening profile: `no-new-privileges`, `--cap-drop ALL` plus CHOWN DAC_OVERRIDE FOWNER KILL
SETGID SETUID NET_RAW (ops/container_hardening.py). Root inside, because the scripts live in `/root/.hermes/scripts`; the files the job
wrote are given back to the worker's user at the end (`chown -R`). Mounted: only the local copy (and for jobnight the prefs read-only,
a two-line `timezone:` file and an out folder). No `.env`, no keys, no `gateways.json`: `job_decide` (the person's Gemini key) is off
in the worker, and the scan reads the boards itself (no hub store). Container output stays on the worker in `last-run.log` (mode 600).

## 5. Events

Every step is one line in `<state_dir>/events.jsonl` (mode 600, append-only) and, when ops/lib/bus.py finds its config
(`$BUS_CONFIG` or `~/.config/aibridge-bus/bus.json`, the same switch the waker uses for BUS_ON), the same event on the bus, sent
synchronously (a one-shot command cannot wait for a background queue). Subjects `ev.worker.<type>.<event>`:

| Event | When | Payload (besides `stack`, `run`) |
|---|---|---|
| `skipped_host_asleep` | a run found the host asleep (`step` pull or push) | `has_copy`, `waiting` |
| `skipped` | another run holds the lock, or nothing to run | `reason` |
| `pulled` | the copy was refreshed | `files`, `channels` (subs), `secs` |
| `started` | the container starts | `copy_age_s` |
| `done` / `failed` | the run ended (`failed`: `reason` timeout, exit, docker, pull, pull_no_channels, pull_no_jobfinder, push_rsync, push_apply, data_root_elsewhere) | `secs`, `rc`, `new_files`, `state_files`, `notices` / `pipeline_new`, `pending`, `signals` |
| `notice` | the job printed something for a human | `count` |
| `pushed` | outputs applied on the host | `files`, `secs`, `applied`, `kept_host`, `merged`, `appended`, `errors` |

Ids, counts, durations and short enums only: the emitter drops any other value. Never text, paths, channel names or offers.

## 6. Install on an always-on host

1. A Debian VM with Docker, rsync, python3; a user in the docker group (that is root-equivalent on that VM: keep the VM for this).
2. This user's ssh key in the Docker host's `aibridge` `authorized_keys`; first connection by hand once to accept the host key.
3. The image: copy the tar the build machine made (`ops/build_local.sh`, the same `IMAGE_TAR` ops/redeploy_router.sh takes, with its
   `.sha256`) to this host.
4. A checkout of the repo (or just `aibridge/workers/` and `aibridge/ops/lib/bus.py`), then
   `aibridge/workers/install.sh --dry-run` (prints every step and the units), then `IMAGE_TAR=<tar> aibridge/workers/install.sh`.
   The first run writes `~/.config/aibridge-workers/workers.json` from the example and stops: fill in `host`, the people (stack,
   `remote_workdir`, `timezone` for jobnight) and the schedules, run it again. It installs `~/.local/lib/aibridge-workers/`, one timer
   per type plus `aibridge-worker-sync.timer`, and says when `sudo loginctl enable-linger <user>` is still needed.
5. Optional: the bus config, `~/.config/aibridge-bus/bus.json` (mode 600), as on the Docker host.
6. Try it: `systemctl --user start aibridge-worker-subs.service`, `journalctl --user -u aibridge-worker-subs`,
   `python3 ~/.local/lib/aibridge-workers/worker.py status`, `tail ~/.local/share/aibridge-workers/events.jsonl`.

A new image of the stacks: load its tar here too (`IMAGE_TAR=... install.sh`), so the worker runs the same scripts as the stacks.

## 7. Moving a job off a stack (and back)

The operator does this on the Docker host, while the stack is awake (`docker ps --format '{{.Names}}' | grep <stack>` gives the Hermes
container, `stack-<stack>-hermes` or the operator stack's own name). Only after the worker's first run of that type succeeded
(`worker.py status`, event `done` then `pushed`):

```
C=<the stack's Hermes container>
# subs
docker exec $C sh -c 'grep -qsx subs-nuevos /workdir/.worker-jobs || echo subs-nuevos >> /workdir/.worker-jobs'
docker exec $C hermes cron pause subs-nuevos
# jobnight
docker exec $C sh -c 'grep -qsx jobnight /workdir/.worker-jobs || echo jobnight >> /workdir/.worker-jobs'
docker exec $C hermes cron pause jobnight
docker exec $C hermes cron list        # both show as paused
```

Paused, not removed: a paused job is skipped by the waker (no wake), stays in the list (nothing recreates it), and is one command from
coming back. `/workdir/.worker-jobs` (one job name a line) is what keeps it paused: start_hermes.sh resumes `jobnight` at every boot
when `/avisos` is noche, and `gateway pref avisos noche` resumes it too, unless the file names it (both read it since this change:
**the image with it must be deployed first**, or the next boot resumes `jobnight`). The bot's skills say not to resume or recreate a
job named there. `ops/install_subs_tools.sh` with CRON=1 only creates `subs-nuevos` when it is missing, so a paused one stays.

Back to the stack: remove the line from `/workdir/.worker-jobs`, `docker exec $C hermes cron resume <job>`, and take the person's job
out of workers.json (or the whole type's timer: `systemctl --user disable --now aibridge-worker-<type>.timer`).

## 8. Adding a type

A subclass of `Job` in worker.py: `pull()` (what the script reads, and who owns it), `container()` (mounts and env, never a key),
`before_run()/after_run()` (what goes to outgoing/), `apply_args()`, and its section in apply.py. Then its ownership table here,
a test in workers_selftest.py and a `types.<name>` entry in the example.

## 9. Next: the broker

Today the "ticket" is a workers.json entry (type + stack + paths) fired by a timer, and the queue is a folder: `outgoing/` on the
worker, the inbox on the host. With the broker (local notes: broker phase 3, job distributor): a `WORK_<type>` JetStream stream
(workqueue, `discard new`), ONE durable pull consumer per type shared by every worker that can run it (an asleep host simply does not
pull), explicit ack after the push is applied, `MaxDeliver` with explicit `nak` delays. The ticket keeps the same fields, as references
only: `id`, `type` (the capability), `stack`/`owner`, `inputs` (the remote paths), `budget` (timeout, memory, cpus), `ttl`,
`privacy_class`. The timers become producers of tickets; `run` becomes "pull one ticket"; the `ev.worker.*` events already published
in shadow mode are the trace to compare against before anything acts on the bus.

## Locks across NFS (2026-11-27)

In local data mode the worker writes the person's files on the always-on machine while their stack reaches the same files over NFS. A
BSD `flock` taken on one side and the NFS client's lock on the other do not exclude each other on Linux, so the files both sides write
(`.jobpush.lock`, `.jobpush-pending.lock`, and apply.py's merge of the night summary) are locked with `fcntl.lockf` (POSIX), which nfsd
and a local process both honour. A new shared file needs the same: lockf, opened for writing.
