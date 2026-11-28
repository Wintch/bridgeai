# Seven days without use: alert, then archive (design, 2026-11-28)

Rule (operator, 2026-11-28): a person who has not used their assistant for **7 days** is alerted to the operator and their stack is
**archived**: its data and its crons are not kept running on the hosts. A simpler, lighter system: no idle stack recreated by every
deploy, backed up every night, sampled by telemetry, or running crons for nobody.

## What counts as use

The person's own messages, as the waker records them (`human_ts` in the stack's waker state): Telegram, web. A cron, a deploy's boot or
an update does not count. Stacks whose crons *are* their work (a business bot publishing to a channel) and the operator's own are listed
in `ARCHIVE_EXEMPT` and never flagged.

## Steps

1. **Detect (built):** `ops/after_batch.py` flags `inactive.<stack>` at 7 days without use, or with no use on record.
2. **Alert (to build):** the ops bot tells the operator once ("herand: 9 days without use; archived on <date> unless you hold it"), with a
   one-day grace for the operator to hold it (`hold` = exempt for N days). Nothing is sent to the person (no machinery notices for people).
3. **Archive (built as `ops/archive_stack.sh`, run by hand for now), when the grace ends:**
   - the stack's crons are paused (Hermes keeps them, marked paused; nothing runs);
   - the brain and web containers are removed; the stack leaves the deploy list (no recreate) and the nightly backup set;
   - its data (persist dir, workdir, keys) is packed into one encrypted archive on the backup host, checked by listing it back, and only
     then removed from the Docker host; the stack's gateways and Telegram bot stay configured;
   - the waker marks it `archived` (state file) and keeps listening for it.
4. **Return:** the person's next message (Telegram or web) restores the archive, recreates the containers on the current image and wakes
   the stack; the waker tells the person once that the first answer takes a few minutes ("I was archived after a week without use"). Their
   crons stay paused until the person (or their assistant, asked) turns them back on: what they no longer used does not come back by itself.

## Toward oblivion (operator, 2026-11-28)

- **Day 7 without use: archive** (above). Today it is run by hand, `ops/archive_stack.sh STACK [--apply]`, on the operator's word: a
  person who comes back writes to the operator directly, nothing restores itself yet (a trigger may come later). The archive goes to a
  **cold disk: an HDD** of an always-on host (no RAM used, still within reach); an SSD would make no sense for it.
- **Two weeks after the archive: slim it.** Destroy what is redundant and keep only what cannot be rebuilt from an image: the person's
  memories, sessions, their own files, their settings and keys. Installs, caches, node_modules, browser profiles, logs and anything the
  image or a shared project brings back go. The slim archive replaces the full one (checked the same way).
- **After that:** offering the person a download and deleting on our side is the operator's call, handled with the testers for now.

## Rules

- Archiving never deletes anything: it moves the data from the running host to the encrypted archive. Deleting is a separate request of the
  person (OFFBOARDING) or a retention limit the operator sets, told to the person before.
- An archive is restorable by script and tested: a restore drill on the guest before the first real archive.
- Exempt or held stacks, a running job or a pending update stop the archive until they end.
- Telemetry keeps only what it keeps for every stack (no text); the archive holds the person's data and is encrypted with the operator's
  backup key, like the nightly backups.

## Order of work

1. alert through the ops bot + `hold`; 2. archive + restore scripts, drilled on the guest; 3. the waker's `archived` state and the restore on
the next message; 4. turn it on for one stack, with the operator watching; then all.
