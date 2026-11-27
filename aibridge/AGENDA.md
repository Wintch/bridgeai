---
title: The person's agenda - scheduled work without waking the bot
scope: gateway agenda (what the bot writes), /workdir/.agenda.json (format, lock), the runner contract the always-on space implements (when to run, last_run/last_state, trabajos registrar, the 🕖 Programado header), the type list and its 1:1 map to worker types
when_to_use: a person asks for something repeated or a reminder; writing or changing the agenda runner on the always-on space; adding an agenda type; a 🕖 Programado line looks wrong
related: [gateway.py (cmd_agenda, AGENDA_TYPES, agenda_schedule, agenda_mutate), gateway_agenda_selftest.py, trabajos.py (registrar, record_scheduled), workers/WORKERS.md, NOTICES.md, SKILL_cron_policy.md, SOUL_bridgeai.md]
---
# The person's agenda

**Rule (operator, 2026-11-27): the Docker host wakes only for a human.** A Hermes cron wakes it (and a stack), so a person's
repeating work is not a cron: it is an entry in their agenda, `/workdir/.agenda.json`, in their always-on space. That folder lives on
the always-on VM and the Docker host mounts it over NFS, so the bot writes the entry while the person talks to it, and a runner on the
VM executes it while the Docker host sleeps. **Everything a scheduled run does is marked as done by a schedule**, never as something
the person or the bot did in a chat.

The bot writes entries with `gateway agenda add|list|pause|resume|remove` (SKILL_cron_policy.md); the runner reads them and writes
back only `last_run`, `last_state` (and `paused` after a `once` run). Status: the bot side is built (gateway.py, trabajos.py); the
runner is not yet (it belongs next to workers/worker.py).

## 1. Types (one list, gateway.py `AGENDA_TYPES`)

| Agenda type | Params | Worker type it runs (workers/WORKERS.md) | Ledger `--tipo` |
|---|---|---|---|
| `subs` | none | `subs` | `subs` |
| `jobnight` | none | `jobnight` | `other` |
| `revista` | none | `revista` (coming) | `other` |
| `recordatorio` | `text` (required, one line, at most 300 chars) | `recordatorio` (new: sends `text`, nothing else) | `other` |

A type maps 1:1 to a worker type: the method (what to copy, how to run, what goes back) stays in the worker; the entry names only the
type and its parameters. **An entry never holds code or a prompt**: params are data, `text` is sent verbatim to the person and never
reaches a shell or a model. A new type is a row in `AGENDA_TYPES` (its params), a worker type, and a row here.

## 2. The file

`/workdir/.agenda.json`, mode 0600, UTF-8 JSON:

```json
{"v": 1, "next": 4, "entries": [
  {"id": "a3", "type": "recordatorio", "schedule": "0 9 * * 1-5", "params": {"text": "tomar agua"}, "label": "agua",
   "created": 1795700000, "paused": false, "once": false, "tz": "America/Argentina/Buenos_Aires",
   "last_run": 1795766400, "last_state": "listo"}]}
```

| Field | Written by | Meaning |
|---|---|---|
| `id` | bot | `a<N>`, from `next`; never reused |
| `type` | bot | one of section 1 |
| `schedule` | bot | normalized: a 5-field cron (`minute hour day month weekday`; numbers, `*`, `a-b`, lists, `/step`, `jan..dec`, `sun..sat`, weekday 7 = 0) or `every <N>m` / `every <N>h`. Validated: at least 30 min between runs over a whole day and across midnight; `every` at most 168 h |
| `params` | bot | the type's params only (section 1) |
| `label` | bot | how the person calls it (at most 60 chars); the default is the type's name in their language |
| `created` | bot | epoch seconds |
| `paused` | bot; runner after a `once` run | a paused entry is not run |
| `once` | bot | run once, then the runner sets `paused: true` (cron schedules only) |
| `tz` | bot | the cron's time zone: the stack's `HERMES_TZ`, else America/Argentina/Buenos_Aires |
| `last_run` | runner | epoch seconds of the last run's start (`null` = never) |
| `last_state` | runner | `corriendo`, `listo`, `fallo` or `omitido` (skipped: another run of that type held its lock) |

## 3. The lock

Every change is a read-modify-write under `fcntl.lockf(LOCK_EX)` on `/workdir/.agenda.lock`, opened for writing (`O_RDWR|O_CREAT`,
0600), then the new content goes to a temp file in the same folder (fsync, chmod 0600) and `os.replace` puts it in place. The runner
writes locally on the VM and the bot over NFS: a BSD `flock` on one side does not exclude the NFS client on the other, a POSIX lock
does (WORKERS.md "Locks across NFS"). Two POSIX rules matter: the lock never blocks its own process (a runner with threads takes a
threading lock first), and ANY close of the file in that process drops it (open the lock file once per change, close it at the end).
Hold the lock only for the read-modify-write, never across a run. A reader that only reads needs no lock (the replace is atomic).
An unreadable file is moved to `.agenda.json.bad` by the next writer (gateway) and never written over.

## 4. The runner contract

1. **When.** For each entry not paused: a cron is due at its next match in `tz` after `last_run` (else after `created`); `every N` is
   due N after `last_run` (else at once). Missed while the VM was down: run once, never catch up run by run.
2. **Start.** Under the lock: re-read the entry (it may be gone or paused now: skip), set `last_run` = now, `last_state` = `corriendo`.
3. **Run** the worker type with the entry's params (WORKERS.md: one-shot container of the stacks' image, no keys, caps, timeout).
4. **End.** Under the lock: set `last_state` = `listo` or `fallo` (and `paused: true` for `once`). If the entry was removed meanwhile,
   change nothing in the file; the run is still recorded in the ledger.
5. **Record it in the work ledger**, inside the person's space, with trabajos.py from the image as a one-shot (the workdir mounted, so
   the ledger is `/workdir/.trabajos/ledger.json`, the same file the stack reads over NFS; trabajos.py also locks with lockf):

   ```
   docker run --rm --network none -v <space>/workdir:/workdir <image> python3 /usr/local/bin/trabajos registrar \
     --origen programado --agenda a3 --etiqueta "agua" --estado listo|fallo --inicio <start> --fin <end> \
     [--tipo subs|other] [--archivos /workdir/... ...] [--motivo "timeout"]
   ```

   Times are epoch seconds or ISO 8601; paths as the stack sees them (`/workdir/...`); `--motivo` is a fixed short reason (timeout,
   exit code), never the job's output. It prints the entry id. The same `--agenda` and `--inicio` again updates that entry (a retry
   never makes two). The entry gets `origin: "programado"` and `agenda_id`; `trabajos lista` shows it as "🕖 Programado: <label>"
   (ru "🕖 По расписанию:", en "🕖 Scheduled:"), and the block the model reads says it was a scheduled run, not asked in that chat.
6. **Anything it sends or leaves for the person** starts with the header `🕖 Programado · <label>` (ru `🕖 По расписанию · <label>`,
   en `🕖 Scheduled · <label>`; the language is `lang` of `/workdir/.prefs.json`, es by default), so it is never taken for the bot's
   own words in a chat (NOTICES.md). A failure the person did not ask to hear about follows the worker-notice rule (not at verbosity
   `critical`).

## 5. Open for the runner

- **How a reminder reaches the person on time.** Today a worker never sends Telegram messages: its notices are files in
  `/workdir/.worker-notices/` sent at the person's next message (hook 60-worker-notices). That is late for a reminder. Either the runner
  sends through the stack's own bot (Bot API `sendMessage` with the stack's token: no wake, but the token must reach the VM), or the
  despertador VM's Bot API relay does it. Operator decision.
- **Moving the existing Hermes crons** (`subs-nuevos`, `jobnight`, `revista`) into agenda entries, and making `gateway pref avisos
  noche` and start_hermes.sh write an agenda entry instead of resuming the `jobnight` cron; SKILL_revista.md and SKILL_job_search.md
  still describe the crons.
- The runner's events (as `ev.worker.*`: ids, counts, durations only) and a `status` view for the operator.
