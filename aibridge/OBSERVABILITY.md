# Observability: what we measure, what we miss, and how it reaches the operator

Status: a mix of what runs today and what is designed. Each section says which. Nothing marked "planned" is to be described to
people as live.

Related: `ops/EARLY_ALERT.md` (minutes-level alerts from category counts), `ops/ZABBIX.md` (tags, actions, webhook, routing),
`ops/VULN_WATCH.md` (software inventory and exploited-vulnerability watch).

## 1. The problem in one paragraph

The platform measures a lot, but the measures hide failures. Hard failures are low (a few percent of turns) while people still say
the assistant "runs badly". What they feel is mostly slow turns after a context compaction, repeated work and drift, and none of
those is a failed turn. Zabbix sees the hosts and the health of the GPU services, but almost nothing of the product. Most product
alerts come from separate Python checkers that talk to the ops bot directly.

The goal is one honest picture: numbers the operator can trust, one route per alert, and a quick answer to "when does a session
start to go wrong".

## 2. Telemetry that exists today

| Source | What it holds | Read by |
|---|---|---|
| `telemetry.db` (host, `ops/telemetry.py`) | `turns` (one row per human turn: counts, tool calls, tool errors, seconds, outcome, model column), `errors`, `awake` (minutes a brain was awake, wakes) | daily report, early-alert, review tools |
| Router eval log (one JSON line per model call, per stack) | result class, time to first byte, completion tokens, finish reason, a counter for non-Latin drift, provider and model | model guard, model menu, review tools |
| Early-signals sink (per stack) | category counts only, no text (see `ops/EARLY_ALERT.md`) | `ops/early_alert.py` |
| Waker journal | wake causes, ready time, evictions, boot timeouts | operator, telemetry |
| Hermes `state.db` (inside each stack) | sessions, messages, compaction summaries | `telemetry.py` (read inside the container), session reviews that print counts only |
| Timers' last-success files | when each ops timer last finished well | alert units (`OnFailure`) |
| Key check and provider status | key state per provider, provider incidents | ops bot, dashboards |

Rules for all of it: counts, enums and timings only. No message text, file name, URL, key or chat id is stored in a metric. A review
reads structure and counts, never raw chats.

## 3. Known gaps

These are measured gaps, not guesses. Fixing them comes before adding new metrics, because every later number depends on them.

1. **Steer and notification messages open fake turns.** A message sent while a turn is running (a correction, a "stop") and a
   system notification each start a row in `turns`. The row is often marked failed because it cut or replaced the real turn. On a
   busy stack this shows a failure rate several times higher than the real one (the real rate is a few percent; this is an estimate).
   *Planned fix:* a steer or a notification does not open a turn; it is attached to the turn it interrupted.
2. **The `errors` table is not fed from the router eval log.** The router logs every non-ok model call, but `errors` stopped
   receiving rows long ago. Anyone reading `errors` sees "no problems" while the eval log shows many. *Planned fix:* feed `errors`
   from the eval log.
3. **The model column is not the real model.** A large share of turns store the routing alias (the "local-first" profile) instead of
   the model that answered. Any per-model curve built from `turns.model` is wrong. *Planned fix:* store the model of the last
   completed call of the turn, joined by timestamp from the eval log.
4. **Long turns are not recorded.** A turn that runs for many minutes (a long tool job) can be missing from `turns`, because the
   row is only written when the turn ends inside the reader's window. The seconds total is also an under-count for slow turns.
   Most failed turns have no `seconds` value at all. *Planned fix:* write the row when the turn starts and update it
   (upsert) until it ends.
5. **Prompt size is not logged.** The router eval log keeps completion tokens only, and the per-message token count in
   `state.db` is empty. Prompt tokens have to be estimated. *Planned fix:* one extra field, `ptok`, with the prompt tokens of
   every call. It is the only measure the session analysis lacked.
6. **Some bots bypass the router.** A bot that talks to its provider directly has no failover, no cooldown and no eval log, so it
   has no per-model data at all. Either put it under the router or remove its dead fallback.
7. **Each user message can be stored twice** in some stacks. Counts of user messages need de-duplication until this is fixed.
8. **Logs do not survive a recreate.** Hermes logs inside a stack are lost when the stack is recreated, and the waker journal has
   a limited history. Old incidents can be reconstructed only from `telemetry.db` and `state.db`.
9. **Rows without a gateway** (`gw` NULL) are mixed into per-gateway counts. They should be labelled or removed.

Until gaps 1 to 4 are closed, do not set thresholds from failed-turn rates. Quote any rate together with its denominator and say
whether the steer filter was applied.

## 4. When does a session start to go wrong

Question: is there a point in a conversation after which quality drops, so we can tell the person to start a new chat?

Method (read-only, counts only): all stack databases copied to a temporary directory and deleted afterwards; human turns on people's
channels; background and automated turns kept apart; outage bursts removed (they hide everything else); the double-stored user rows
removed. The numbers below are rounded. They come from one deployment, mostly one busy stack, and are observational: sessions that
compact are also the heavy tool users, so this is a correlation.

**Findings**

- **Wall-clock session age shows no trend.** Failure rates are about the same for sessions under an hour and sessions of several
  days. "How long the chat has existed" is the wrong clock.
- **Most failures are provider outage bursts**, independent of position in the chat. After a failed turn the next turn fails far more
  often than after a good one. Raw curves that rise with depth mostly measure those bursts.
- **The first context compaction is the break.** It happens at about the tenth human turn (median). In the turns right after it:
  - a turn that repeats an identical tool call is about a quarter of turns, against well under one percent in sessions that never
    compacted;
  - the person has to correct the assistant (steer) in roughly one turn in seven, against one in fifty;
  - tool-error turns roughly double;
  - a turn that contains the compaction itself takes about five times longer than a normal turn (the p90 is far worse);
  - rates return to baseline after about ten to twenty turns.
- **Very deep sessions (about 40 human turns and more) fail more often**, perhaps two to three times the early rate. The evidence is
  weak: few sessions, nearly all from one stack. Treat it as "flat until about 40, worse after", not as a precise knee.
- **Per model, one model drifts with depth** (repeated calls and foreign-script drift rise), another mostly errors out under load.
  The samples are small. Do not rank models on them; collect per-model counters first (section 5).

"Repeated identical tool calls" is the useful sign of a model forgetting what it already did. It needs no text, only a hash of the
call per turn.

**Use 1: the "start a new chat" nudge** (planned, per-person setting like verbosity)

- After the first compaction in a session, once, and only when the person is between turns, so it never interrupts a running job:
  a short message that the chat was just summarised and that `/new` keeps their memory and answers faster.
- A second nudge at about 40 human turns, repeated every 20. A third when three or more compactions happen within an hour.
- Never reset a chat automatically, and never mid-task.
- Before sending the first nudge, check that `/new` really keeps memory and open background jobs. This has not been verified yet,
  and the nudge must not be sent until it is.

**Use 2: a trigger and a signal**

- "A compaction just happened" is the main session signal for Zabbix and for early-alert, ahead of session depth. Depth is
  secondary. Alerting on length alone is wrong because the data shows no cliff by length.
- It is also the trigger for the mitigation experiments: raise the compaction threshold, protect the recent tool-call tail from the
  summary, use a shorter summary or run it in the background after the reply. Run each as a one-week A/B on one stack and compare
  the repeated-call share. That is the only way to turn the correlation into a cause.

Re-run the same extraction after four to six more weeks. A read-only script that prints counts only (planned, `session_curve.py`)
makes the check repeatable and safe.

## 5. Zabbix design

Zabbix today receives host metrics and the HTTP health of GPU services. This section is the design to bring the product in.

### How data gets in

- A **user timer on the Docker host** reads `telemetry.db` read-only and pushes values to Zabbix trapper items (about every 60 s).
  It is the only path that fits the constraints: the ops user has no root, its home is private so the Zabbix agent's user cannot
  read the state files, the agent has no custom user parameters, and the server port accepts connections.
- Not used: the API `history.push` (it needs an API token with write rights) and agent user parameters (they need root and files
  readable by the agent).
- The trapper link is not encrypted by default. Note this in the setup, and use a pre-shared key if the link leaves the LAN.
- **One Zabbix host per stack**, in group `bridgeai/<unit>`, with tags `project:bridgeai` and `unit:<unit>`. A single shared host
  with a per-stack tag does not work: the hook keeps the first `unit` value it sees, and `unit` is not allowed on triggers, so every
  alert would lose its stack.
- **Items:** one master JSON item per stack plus dependent items with JSONPath. Low-level discovery (LLD) only for sub-dimensions:
  model, provider, session-depth bucket, timer and early-alert category.
- **Import by the operator.** The templates (a stack template and a platform template) are imported by the operator, as the
  software-inventory template is. The admin API token never lives on the Docker host.
- **Content rules:** values are numbers only; trigger names are static. No chat text, model output or any string an attacker could
  control becomes an item value or an alert name. Tag `service` is one of: hermes, router, waker, keys, backup, gpu, host,
  monitoring.
- **Pattern to reuse:** a pusher with a heartbeat and an alarm for rejected values (the same shape as the existing intrusion
  monitor). Every pusher must report that it ran and how many values the server refused.

### Severities and the one-route rule

Routing as delivered today (see `ops/ZABBIX.md`):

| Severity | What happens |
|---|---|
| High | the ops bot is told at once |
| Average | told after about five minutes (a problem that clears first never sends) |
| Warning, Information | dashboard only, never delivered |

A problem without a `unit` tag is never delivered, whatever its severity.

**One route per condition.** A condition that a Python checker already pages starts in Zabbix as Warning (dashboard only), so
nobody is paged twice. After the replay (below) and about a week of agreement between the two, paging moves to Zabbix for that
condition, one condition at a time, and the Python path is removed. Exceptions that may page from the start: dead-man alarms and
host-level conditions the Python checkers do not see (disk, RAM, failed units).

Warning is also the wrong place for "an alert has been open for a week": an alert that old is exactly the silence we want to
end. Keep that one at Average, or put it in the weekly report.

### Minimal set (about 15 items, no container changes)

| Item | Trigger | Severity |
|---|---|---|
| Push heartbeat (epoch of the last push) | no data for 10 min | High |
| Telemetry age | older than 15 min | High |
| Free disk of the Docker host | under the image-build floor / under a critical floor | Average / High |
| Available RAM | low / very low | Average / High |
| Failed user units | any for 10 min | Average |
| Ops-bot alerts open for more than 7 days | any | Average |
| Awake brains versus the configured maximum | over the maximum | Information |
| Turns per hour, per stack | count only | Information |
| Failed turns per hour, per stack | burst: 3 or more in 1 h, or a high share of at least 5 turns | Warning (duplicates early-alert) |
| p95 seconds of plain turns (no tools) | high for 15 min | Warning |
| Bad model calls per hour (429, timeout, 5xx, broken stream) | a burst | Warning |
| Router with no route | 2 or more in 30 min | Average |
| Early-alert score and unanswered flag | score threshold / flag set | Warning |
| Wake problems in 24 h (timeout, no memory, evicted) and last wake time | any / slow | Warning |
| Key refused count and age of unknown key state | any / old | Warning |
| Last compaction depth and session age | informational | Information |

Failed-turn thresholds depend on fixing gaps 1 to 4. Without that fix, a stack with many corrections looks much worse than it is.

### Full set (later phases)

- **Session** (the thresholds are proposals; keep them at Information until the replay and four to six more weeks of data support
  them, because they rest on few deep sessions):
  - session depth in human turns: soft and hard level;
  - compactions in 1 h: 3 or more;
  - compaction duration: slow and very slow;
  - compaction failures in 24 h: any;
  - consecutive failed turns: 3 or more;
  - repeated-tool-call share over 6 h with enough turns (the base is a few percent);
  - p90 seconds per turn;
  - failures and turns per depth bucket `{#BUCKET}`, with the percentage computed and a seven-day graph; later the same cut by
    prompt tokens, once `ptok` exists.
- **Per model `{#MODEL}`:** share of bad calls over the last N calls, time to first byte p95, tokens per second (a very slow
  model stands out), timeouts per hour, bad arguments and drift counters as Information.
- **Per provider `{#PROVIDER}`:** key state, age of the last good check, provider incidents (Information), model-guard findings.
- **Platform:** waker (wakes by cause, p95 wake time, evictions, boot timeouts, hook exit codes), timers `{#TIMER}` (age since last
  success, Average beyond about three intervals), ops-bot outbox not draining, simple port checks on the hook receivers, image
  drift per stack, Docker disk, backup age per stack and the backup watcher's verdict.
- **Gateways:** calls, share ok and p95 per gateway. A gateway that should always be on and has fallen back to CPU is Average.
- **Early-alert:** a count per `{#CAT}`, plus the standing conditions.
- **Config drift (numbers only):** size and hash of each stack's SOUL file, hashes of the router and patch files, file permissions of
  the gateway list, image id per stack. A change-count trigger on a hash that must not move.
- **Security events (counts only):** guard hits, key-shaped text seen in a chat, denied approvals.

A "last success" item per timer matters more than a "ran" item: a timer that exits 0 without being configured looks like coverage and
is not.

### Dead-man switches

- The heartbeat item (epoch of the last push) has a server-side no-data trigger. It fires if the pusher dies, the host sleeps or the
  link breaks.
- A second, independent watchdog covers the case where Zabbix itself is down: a small script outside the monitoring path that checks
  the heartbeat and sends through the ops bot's outbox. If it runs on the same host as the pusher, it needs a read-only API token
  stored there. That breaks the rule "no Zabbix token on the host". Either accept it as a stated exception with a read-only token,
  or run the watchdog on another host, or rely on the server's no-data trigger for the pusher and keep the watchdog only for the
  loss of Zabbix.
- A disk-full host can silence its own alert path. Add a disk trigger whose delivery does not write to that disk.

### Replay before paging

Before any trigger may page, run it over the stored history and count how many pages it would have sent per week per stack
(`ops/zbx_replay.py`, planned). A trigger is allowed to page only if it stays at about two pages per week per stack or fewer. In a
sibling project, requiring three consecutive failures cut a 30-day simulation from dozens of pages to a couple. Use the same
approach here, and keep the replay result with the trigger.

### Maintenance during deploys

A redeploy recreates stacks and makes health checks fail on purpose. The deploy script should open a Zabbix maintenance window with
tags for the units it touches (or use the local `scope mute` switch of the hook), and close it when the smoke test passes. A deploy
that pages is a bug in the deploy script. A window expires by itself.

### Conventions

- Keep `project=bridgeai` for the product and a separate project value for platform infrastructure. A `scope only project:bridgeai`
  then does not silence the infrastructure hosts.
- Keep host names and client details in a private repository, not in public docs.
- One physical machine, one host, one unit. If an old duplicate host exists for the same machine, remove it.
- Agent tokens stay read-only and scoped to their own unit (see `ops/ZABBIX.md`).

## 6. Relation to the early-alert collector

`ops/EARLY_ALERT.md` and Zabbix answer different questions, and they must not page twice.

| | Early-alert | Zabbix |
|---|---|---|
| Speed | minutes, a score over a 30-minute window | trigger with its own delay |
| Input | category counts from inside the stack and from `telemetry.db` | the pushed items, host metrics, GPU health |
| Output | one message per stack to the ops bot, with cooldown and resolve | problems with severity, dashboards, history |
| Strength | understands the person's experience (complaints, unanswered, announced-but-not-done) | trends, per-model and per-depth curves, dead-man |

Plan: the collector keeps paging while Zabbix mirrors its counters (one item per category plus the score) at Warning. Zabbix gains
the compaction and session signals first, because the collector has no such category yet. A compaction start/end line with its
duration is a good new early-signal category. Only after the replay agrees does a condition move to a single route.

The collector's own limits apply to the pusher: counts and enums only, bounded reads, no `docker exec`, a memory cap, and absence of
a source never alerts.

## 7. Regression eval set built from real failures

There are many offline self-tests of logic and no test of answer quality. A new image can make answers worse and nothing notices.
The eval set closes that gap.

- **Source of cases:** each real failure class we have seen, rewritten as a synthetic case. The text is invented. No real chat
  content, name or id enters the file.
- **Format (planned, `ops/regression/cases.jsonl`):** one line per case with the category, a short invented prompt or tool-result
  fixture, what a pass looks like (a check on structure, not on exact words) and, for a patch, the retirement condition of the patch
  the case guards.
- **Seed categories:**
  - the assistant announces work and does not do it;
  - the instruction file is cut by a size limit;
  - a flood or runaway after correction messages;
  - an invented result presented as verified (a decoder or lookup that was never run);
  - an answer in the wrong language for the person;
  - several nights in a row where a scheduled search finds nothing;
  - the memory store is full;
  - tool-call text leaks into the reply;
  - a very long web result;
  - a tool that needs a backend which is not available (it must say so at once and hand off).
- **How it runs:** first in the image smoke test against a mock model, which proves the harness and the patches. A run against a real
  provider (for example nightly on the guest) comes later and only after confirming that the provider's terms allow that kind of
  automated use on the account that pays for it.
- **Pass rule:** a new image must not lower the pass rate of the base image.
- **Discipline:** every new incident adds a case before its fix is merged. Every new patch to upstream code brings its retirement
  condition and its case.

## 8. Order of work

1. Fix the data (gaps 1 to 4), because everything else depends on them.
2. Write the routing rules in `ops/ZABBIX.md`, and make a read-only routing audit (hosts without tags, problems at Average or above
   that nothing delivers, groups the notifier cannot see).
3. Install the sender path, then the pusher, the two templates and the per-stack hosts, with the minimal set and the dead-man.
4. Replay, then maintenance in the deploy script.
5. `ptok`, a `sessions` table (length, compactions, compaction failures, chain depth, first failed message, longest streak) and the
   full set.
6. The regression set in the smoke test, then the nudge, then the compaction A/B.
7. Move paging, one condition at a time, to a single route.
