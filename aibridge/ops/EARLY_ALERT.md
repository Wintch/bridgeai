# Early alert

The operator hears within minutes (about 10 in the worst case) that a person's bot is failing them, instead of at the next review.
Phase 1: collect category counts, score them, tell the ops bot. Nothing is sent to the person, nothing is fixed automatically.

## What is read (and what never is)

Only categories, small counts and short enum words. The person's words are matched by regex in memory (in the router) and only the
category leaves the matcher. No message text, URL, file name, key, chat id or user id is ever written or read.

| Source | Written by | Read by |
|---|---|---|
| `/workdir/.early-signals.jsonl` (+ `.1`) | router, announced-action patch, jobpush, the reply-language check of the `aibridge-jobs` plugin, `start_hermes.sh` (boot) | `ops/early_alert.py` |
| `/workdir/.last_human`, `.last_reply`, `.last_model_call` (epoch) | router | `ops/early_alert.py` |
| `~/.local/state/telemetry.db` | `ops/telemetry.py` (already running) | `ops/early_alert.py`, read-only |

The sink is one more host-readable file, the same pattern as `.last_human` (the writer sets 0644 although Hermes runs with umask 077). One
line is `{"ts":1789000000,"cat":"nudge","n":1,"k":"announce","src":"patch"}`: `cat` from the fixed list below, `n` an int (1 to 20; for
`soul_cut` the SOUL length in characters), optional `k` (`[a-z0-9_]{1,16}`) and int `v`, `src` one of router, patch, jobpush, boot, plugin.
A writer drops anything else, never follows a symlink, writes at most 40 lines a minute and rotates the file at 200 KB (one old
generation). The collector opens every file with `O_NOFOLLOW`, accepts regular files only, reads the last 256 KB, at most 2000 lines, and
skips a line with an unknown category, an out-of-range count, a timestamp outside the last 24 h (36 h for the two once-a-day standing categories), or any extra field. The agent can write
the directory as root and could forge lines: the worst effect is a false alert. A root-only (0600) file is read through a bounded `docker cp`
(works while the stack sleeps): at most the size cap of the tar stream is held in memory, then the copy is killed and the file counts as
unreadable, so a multi-GB file made on purpose cannot take the host's RAM (the unit also has `MemoryMax=256M` as a backstop). The
collector never uses `docker exec`.

A signal whose source file is absent (an image without the writers, a stack with no router) is simply missing: absence never alerts.

## Categories and weights

| cat (k) | emitted when | weight |
|---|---|---|
| `nudge` (announce, claim) | the announced-action patch re-prompts a reply that promised work without doing it | 1 |
| `nudge_ignored` | the model repeated the promise after its one nudge | 2 |
| `complaint` (check, agreed, broken, didnt, again) | the person's message matches the complaint table in `router.py` (one per turn) | 2 |
| `repeat` | the same text (25+ chars) in a second distinct turn within 10 minutes; one line per repeated turn | 1 each |
| `deadpage` | the person pasted a short (up to 300 chars) browser error page title or code; alone it does not alert (a developer asking about a 404 is not a failing bot) | 2 |
| `key_notice` (refused, none) | the person was told their key was refused / that no key exists | 3 / 1 |
| `bad_end` (length, empty) | an answer cut by the length limit, or stopped with nothing | 1 |
| `wrong_lang` (k = language code when the plugin wrote it: fr, pt, zh...) | an answer of 120+ letters in another language than the person's (router), or any reply in a language other than the chosen one / outside Spanish, Russian, English while none is chosen (`aibridge-jobs` plugin, `replylang.py`) | 1 |
| `scan_zero` (v = streak) | 5 or more night job searches in a row found nothing (standing condition) | 3 |
| `soul_cut` (n chars, v cap) | `SOUL.md` is longer than `context_file_max_chars` at boot (standing condition) | 3 |
| `long_turn` (k minutes / calls, v the minutes or the call count) | the router saw ONE turn (a person's message and its tool loop) run past `ROUTER_LONG_TURN_MIN` (30) minutes, or make `ROUTER_LONG_TURN_CALLS` (100) model calls; once per turn and kind. The clock is checked on each model call, so a turn stuck inside one call shows up when that call ends | 3 (minutes) / 1 (calls) |
| `db_lock` (k stopped / retry, n a count) | every 5 minutes, on a model call, the router counts what Hermes logged since its last look about its turn lease on `state.db`: `stopped` = the turn was cut ("Lost session turn lease", "Failed to refresh session turn lease", "could not be refreshed", "stayed locked"), `retry` = a renewal waited for the SQLite lock. Counts only, never the lines (`ROUTER_DB_LOGS`, `ROUTER_DB_SCAN_EVERY`) | 3 each (stopped) / 0.5 each (retry) |
| `unanswered` | computed: awake brain, last message newer than the last reply, 30 min of silence with no model call, no registered job (`/workdir/jobs/*.json`) and no fresh job-scan marker, message under 3 h old, brain up 3+ min | 3 |
| `model_err` | telemetry: failed model API calls (not Hermes's background model) | 0.5 each |
| `failed_turn`, `empty_turn` | telemetry: failed / empty turns of people's channels (not cron) | 2 each |
| `links_dead` | telemetry: `gateway enlaces` calls that found a dead link | 1 each |

## Scoring, cooldown, resolve

Score over a sliding window (30 min): sum over categories of `min(weight * count, 4)`, so one noisy category cannot dominate. Alert at
3.0 or more. One complaint (2) alone does not alert; two nudges and a complaint (4) do; three nudges do; three repeated turns do;
a dead page alone does not (2); the weight-3 categories (`key_notice` refused, `scan_zero`, `soul_cut`, `unanswered`, `long_turn` past the minutes threshold, a `db_lock` stopped) do alone. `model_err` counts only when another category has points.

After an alert the stack is silent for 2 h. It is sent again earlier only when the score reaches `last * 1.5 + 2` and 30 min have passed,
or when it is still failing after the 2 h. When the score has been 0 for 60 min the alert resolves once. `soul_cut` and `scan_zero`
are standing conditions with their own key (`early:<stack>:<cat>`), a 24 h cooldown, no escalation, and resolve when they age out
(36 h without a new line, so a nightly line that comes a few minutes later each day never resolves and re-alerts).
`scan_zero` counts night runs only (`mode=noche`): daytime digests with nothing new are not days of a broken search.

The alert goes through `ops/lib/notify.py` (outbox, journal) with `quiet=0`: the collector owns the cooldown. State:
`~/.local/state/early_alert.json` (written atomically under a file lock).

## Operating

- Install: `AIBRIDGE_HOST=user@host ops/deploy_ops.sh --apply` copies the tracked files and enables `early-alert.timer` (5 min).
- Safe by default: **nothing is sent until `EARLY_ALERT_NOTIFY=1` is in `ops/ops.env`.** Until then each run only prints the per-stack table
  to the journal (`journalctl --user -u early-alert`), without writing state. Watch it for a day, then enable.
- Try it by hand: `python3 ~/aibridge/ops/early_alert.py --dry-run` (table, would-be text, no state, no send); `--stack NAME`, `--window MIN` (sink events and telemetry rows both look back that far, at least 2 h), `--json`.
- Rollout order: the ops files first (the collector is live at once on telemetry signals and on `.last_human`); the container signals
  (the sink, `.last_reply`, `.last_model_call`) arrive with the next Hermes image and a recreate of each stack. Until a stack runs the
  new image its router signals are simply missing.
- Look at one stack: `python3 ~/aibridge/ops/stack_doctor.py STACK` (read-only; `--json` for the ops brain): state and ages, last turns
  (model, finish, tools, seconds, failed calls), keys (provider and last 4), signals of the last 2 h, the job search's last line, SOUL size.
- Silence a test stack: `"early_alert": false` in its entry in `ops/wake/stacks.json`. It is still scored in `--dry-run` and never notified.
  A stack that is not in `stacks.json` is never scanned.
- Exit code: 1 only when every stack failed; one flaky stack is logged to stderr and skipped.

Out of scope for phase 1: reading chats or `state.db`, any model judging replies, alerts to the person, auto-remediation, an `on_wake.d` hook.
