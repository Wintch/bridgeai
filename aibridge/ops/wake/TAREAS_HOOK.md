# Waking a bot for a task (Gitea webhook -> waker -> one run)

The board itself is `gateway tareas` (`tareas.py`, `ops/tareas_setup.py`); the design is in `aibridge/MULTI_BOT_TASKS.md` section 4. The operator steps (secret, unit, firewall, Gitea webhook) are in `ops/TAREAS_SETUP.md` section 7. A few facts about Gitea's payload and Hermes's `/v1/runs` come from their API structs, not from a live check (see "Limits").

## Why our own receiver, and not something Hermes ships

The bots sleep: their container is stopped. Whatever wakes one must run on the host, outside every container. Nothing inside Hermes can
start its own stopped container. What Hermes ships, and where it fits:

| Hermes feature | What it is | Why it does not replace this receiver |
|---|---|---|
| `webhook` platform (`gateway/platforms/webhook.py`, docs `messaging/webhooks.md`) | HTTP ingress with HMAC, `events` and payload filters, coalescing, prompt templates, delivery back to GitHub/Telegram | It runs inside the container, so it is down while the bot sleeps. It could be the last step instead of `/v1/runs`, with the host forwarding the raw body after the wake, but it has no chain rule or `accept_from`, and nothing would be gained. |
| A2A plugin (`plugins/platforms/a2a`, docs `messaging/a2a.md`) | The open Agent2Agent protocol v1.0: Agent Card, `SendMessage`, per-peer tokens, anti-loop turn cap, audit log | It is the modern way for one agent to call another directly. But both agents must be awake, a call is synchronous, and it bypasses the board: the owner cannot see or stop the handoff in Gitea, and Telegram approval and time-locks are not applied. Possible later, behind a waker that wakes the target first. |
| Kanban (`kanban.db`, docs `features/kanban*.md`) | A durable task board in one SQLite file shared by the Hermes profiles of ONE install, with a dispatcher that spawns workers and `notify+wake` subscriptions | It needs every bot as a profile of the same install and filesystem. Our design is one container per bot, with its own keys and packs, so a business's bots cannot share it without giving up that isolation. One container per business could save RAM, but that is a design change, not a wake hook. |
| `gateway/wake.py` | Resumes an existing session after a background job finishes | Only inside a running gateway. |

Outside Hermes, the pattern is the usual one: a forge webhook, then scale-to-zero. Generic HTTP proxies that start a container on the
first request (Sablier and the like) cover web UIs. They cannot cover a Telegram bot, because the bot polls out and nothing comes in to
proxy. Nor do they decide which bot a task is for. The waker already does both jobs, so this receiver is a front for it.

**Sleeping sooner.** Bots that only work on tasks can set a short `idle_brain` and `idle_web` (for example 120 s) in `ops/wake/stacks.json`. The waker never stops a stack that has:
- a turn running, or one that started less than 2 minutes ago;
- a `/v1/runs` task run;
- background processes, downloads or renders;
- registered jobs.

A stack woken for a task keeps the short cron hold (`hold_seconds`, 180 s) after its run. Feedback wakes the bot again: a comment in the task through this receiver, or a Telegram message through the waker.

## What it does

```
Gitea org webhook (events: Issues, Issue comment)
   | POST /gitea, X-Gitea-Signature = HMAC-SHA256 of the raw body
   v
ops/wake/tareas_hook.py   (user service on the VM, bound to one address:port)
   | checks, in order: size, signature, event/action/repo/state, assignee -> stack, own action, the chain rule,
   | delivery id (24 h), rate limit; then writes ops/wake/<stack>.task.json (repo, issue numbers, counts, times: no text)
   v
ops/wake/waker.py  task_tick()   (every 30 s, next to the cron tick)
   | brain down: wake(reason "task") - like a cron wake: RAM guard looks once, never evicts, never waits, retries in 10 min
   | brain up and quiet: starts the hooks itself; brain up and busy (a person is talking): waits
   v
ops/wake/on_wake.d/40-task-run  ->  ops/wake/tareas_run.py
   | ONE POST /v1/runs on the stack's own Hermes API (Bearer key read from the container, never printed),
   | fixed prompt, returns as soon as the API accepted it, writes the run record, removes the request file
   v
the bot runs `gateway tareas listar --mias`, works every pending task oldest first, leaves each result in its task
```

The fixed prompt (in `tareas_run.py`): "Tenés tareas nuevas en el tablero. Revisalas con gateway tareas listar --mias y trabajá todas las pendientes,
una por una, de la más vieja a la más nueva, según la skill tareas, hasta que no quede ninguna pendiente. Dejá el resultado de cada una en su tarea; la que
no puedas terminar, dejala en bloqueado con el motivo y seguí con la siguiente." Nothing from an issue ever goes into it; the bot reads the
issue through the gateway, which quotes it as data. The run's output is not sent anywhere: the bot reports in the task and, if
`SKILL_tareas.md` says so, with a short Telegram note to its owner.

### Receiver rules (code, not model)

| Check | Result |
|---|---|
| path is `/gitea` (or `/gitea/<org>`, which only chooses that org's secret) | else 404 |
| body larger than 64 KB, or no Content-Length | 413, nothing read |
| `X-Gitea-Signature` missing, empty or wrong (constant-time compare, before any parsing); a receiver with no secret does not start | 401, nothing else happens |
| event `issues` with action `opened`, `assigned` or `reopened`; event `issue_comment` with action `created` (not on a pull request); anything else | ignored (200) |
| `repository.full_name` equals the `tareas.repo` of some stack in `ops/gateways.json`; issue is open and not a pull request | else ignored |
| each assignee login is matched, case-insensitively, to a stack by `tareas.me`; humans and unknown accounts | ignored |
| the actor is the bot itself (a comment by `comment.user`, otherwise `sender`) | ignored: a bot's own action never wakes it |
| the actor (the one who assigned or commented) or the issue's author is not the bot itself, a human or in that stack's `accept_from` (default `peers`) | not woken (`not-accepted`), stays on the board |
| the header cannot be read (bad or repeated field, `salto` not equal to `len(cadena) - 1`, a cycle inside `cadena`), or its `salto` is above the stack's `max_cadena` (default 3, 1 to 5), or the assignee is already EARLIER in `cadena` | not woken (`chain-ignored`), stays on the board. A task AT the maximum wakes |
| payload timestamp (`comment.created_at` for a comment, else `issue.updated_at`) older than 24 h | `stale-payload`, nothing done (a payload with no timestamp is judged by the hash alone) |
| same `X-Gitea-Delivery` **or the same SHA-256 of the raw body** seen in the last 24 h (kept across restarts) | `duplicate`, nothing done |
| request file already pending for that stack | the task joins it (`coalesced`): several tasks, one run |
| last kick of that stack less than 2 minutes ago | a new request is written with `not_before` set to the 2-minute mark |

**Replay.** `X-Gitea-Delivery` is not covered by the HMAC, so an eavesdropper on the plain-HTTP LAN delivery could re-send a captured signed
body under a new (or no) id and wake the bot again every couple of minutes. The body hash closes that, and the timestamp check closes it
past the 24 h memory: a replay is a duplicate for 24 h and stale afterwards. The listener is still plain HTTP, so anyone who can sniff it
can read the (title-free) payload; the HMAC only stops forging. A Gitea "Redeliver" of the same body is therefore `duplicate` too: to
re-send an event on purpose, change the task (that moves `updated_at`). The service also refuses to start with a secret shorter than 32
characters or one that starts with `<` (the example file's placeholder), so an unedited copy is never a public secret.

The header is read by a copy of `tareas.py`'s `parse_body` and `chain_info` (only the first block counts; the host does not get `tareas.py`); the selftest
compares the source text of the copies with the originals and runs both on the same header fixtures at every maximum. `accept_from` and `max_cadena` come from each
stack's `tareas` block in `ops/gateways.json`, read fresh on every delivery and with the same defaults as `gateway tareas` (the selftest compares them too).

Logs (journal): one JSON line per event with `stack`, `issue`, `action`, `outcome`. Never a title, body, comment, signature,
secret or key.

### Polling, when Gitea cannot reach the receiver

If Gitea sits on another subnet (its webhook page shows deliveries with `Response 0`: the router, the host firewall or `ALLOWED_HOST_LIST` blocks them) the receiver can **ask** Gitea instead:

1. `ops/tareas_setup.py --vigia` (with the admin token on stdin, `--url` and `--org` as before, no `--stack` needed) makes the account `bot-vigia`. It has ONE token, scopes `read:issue` and `read:repository`, written as `poll_token` into `ops/wake/tareas_hook.json`. No bot token is ever put on the host.
2. `systemctl --user restart aibridge-tareas-hook`. The start line then says `"polling": 60`.

Every 60 s (`poll_seconds`) it reads the issues that changed since its cursor, then their timeline. It turns each new assignment, comment, close, reopen or label change into the event a webhook would have sent and passes it through the same rules. Log lines carry `"via": "poll"`.

- **Dedupe:** the key is the timeline item's id, so a working webhook and the poller can run together.
- **First look:** it goes 6 h back, so tasks filed while nothing listened are picked up.
- **Errors:** an answer other than 200 advances nothing. The same window is read again next time.

The cost is up to one minute of delay and a few small reads per minute. Nothing has to change on the router or in Gitea.

### The result goes back

When the assignee closes a task, or sets it `estado/bloqueado`, the receiver wakes the bot that **filed** it, under `"done"` in that bot's
request file. That run gets its own fixed prompt (`tareas_run.DONE_PROMPT`): read the result with `gateway tareas ver N` and go on with your
part. The waker also sends the person one fixed line through that bot, for example "🔔 bot-disenador cerró la tarea #1 que pedí en el
tablero", in the stack's language. The line carries only the number and the closer's login.

Rules:
- The closer must be an assignee of the task and in the author's `peers`, `accept_from` or `humans`.
- The author's own close wakes nobody.
- A comment or another state wakes nobody, so two bots cannot ping-pong.
- One task tells its author at most once per kind (closed, bloqueado) per 24 h (`already-told`).
- A task a person filed has no bot to wake (`ignored-author`): the person sees it in Gitea.

The fields Gitea sends for a close and a label change (`action` `closed` and `label_updated`, `issue.labels[].name`, `sender.login`,
`issue.user.login`) are read as in its API structs. Like the rest of the payload, they are **unverified until the first real delivery**.

### What the chain rule does and does not do

The rule is the one of `MULTI_BOT_TASKS.md` section 10.3, the same that `gateway tareas` applies when a bot files or reassigns: the receiver wakes a bot only for a task it may act on, and it decides from what the payload and the header say, never from what a bot marked.

What it does not do: it cannot tell a task a bot filed on its own initiative from one a person asked for (depth is what the header says, and the gateway writes the header); the board token can edit an issue body, so the header is discipline of the normal tool, not a wall; it does not look at what a task asks. The receiver holds no board token, so it does **not** post a "needs a person" comment or message the owner for a refused task; it stays on the board until the bot lists it (and the gateway hides it anyway if it is outside `accept_from`). A bot that ends a chain wakes when its task arrives; waking the parent holder when a child closes is only done for the filer, as described above.

## Setup

See `ops/TAREAS_SETUP.md` section 7: the secret file, the user unit, the firewall rule for the Gitea host and the Gitea organisation webhook.

## Testing it

1. Open the webhook in Gitea and press **Test delivery**: the receiver answers 200 (`ignored-event` or `ignored-repo`, it is not a task)
   and the journal shows one line. A 401 means the secret differs.
2. Put the stack to sleep (`/dormir` in its chat, or wait), then file a task for its bot with the person's account in the web page
   (assignee = the bot), or `gateway tareas nueva` from another bot's chat. Watch:
   `journalctl --user -u aibridge-tareas-hook -u aibridge-waker -f`. Expected: `kick` (receiver), `waking for a task request` and
   `waking (task)` (waker), `hook 40-task-run: rc=0` and `run started` (starter), and the bot's comment on the task.
3. **Check the real payload once**: Gitea's "Recent deliveries" shows the JSON. Confirm `issue.assignees[].login`, `repository.full_name`,
   `comment.user.login` and `sender.login` exist as the receiver reads them (they are from Gitea's API structs, not from its webhook page).
4. Offline: `python3 -I ops/wake/tareas_hook_selftest.py` (receiver + starter with fake Gitea and fake Hermes API) and
   `python3 -I ops/wake/tareas_waker_selftest.py` (the waker's decision and wake). `ops/wake/selftest.py` (needs docker, run on the server)
   has a scenario 8 for the task reason.

## Turning it off

- Stop taking new tasks: `systemctl --user disable --now aibridge-tareas-hook` (or untick *Active* on the webhook in Gitea).
  Open tasks stay on the board; bots still read them when someone talks to them.
- Drop what is already waiting: `rm ~/aibridge/ops/wake/*.task.json` (the waker never acts on a missing file).
- The waker's side needs no switch: with no request file `task_tick` does nothing. A request older than 6 hours is dropped by itself.
- Maintenance: `touch ops/wake/NO_SLEEP` still only stops sleeping; it does not stop task wakes.

## Limits

1. **Gitea payload names** (`issue.assignees`, `issue.assignee`, `repository.full_name`, `comment.user`, `sender`, `is_pull`, `issue.pull_request`) come from Gitea's API structs; the docs page does not list them. Whether creating an issue with assignees fires `issues/opened`, `issue_assign` or both varies; both are accepted. Read one real delivery before relying on a new Gitea version.
2. **`POST /v1/runs`.** The starter sends `{"input": "<prompt>"}` and accepts 200, 201 or 202; it takes `run_id` or `id` from the answer. If Hermes wants another field name the run fails with `API answered 4xx` in the waker's journal (the `tareas_run:` lines) and the fix is one line in `tareas_run.py`.
3. **Approvals.** `patches/approvals_no_ask_bridge.py` makes a flagged command on `/v1/runs` get denied at once (`unattended_mode: deny`). A task that needs a spend, a publication or a message to a third party cannot be approved in Telegram from a headless run: the bot must set the task `bloqueado` (or hand it to the person) and say so.
4. **Does an API run count as busy?** When the API accepts a run, `tareas_run.py` writes the run record and `busy_reasons()` reports "una tarea en curso" until the run is seen finished (the waker asks `tareas_run.py --stack NAME --check`, at most every 30 s, which does `GET /v1/runs/<id>` and reads `status`). That reason holds off the idle sleep, the RAM guard's `evict_one()` and a new task request, for up to `task.max_run_seconds` (1 h). If the API answers with status words the check does not know, it says `unknown` and only the first `task.hold_seconds` count as busy; a longer task can then be cut by the idle sleep or by `evict_one()`. Fix `RUNNING` / `FINISHED` in `tareas_run.py` if the words differ.
5. **No Telegram line from the host** for a refused task. Only the bot can message the owner, if the skill tells it to.
6. **One run per request, not per task.** A burst of 3 tasks starts one run and no further delivery comes for tasks 2 and 3, so the fixed prompt tells the bot to work every pending task of its own, oldest first, until the list is empty (one it cannot finish goes to `bloqueado` with the reason). A task that arrives while a run is working is a new request (one kick per 2 minutes) and waits for the run to end.
7. **Request file and retries.** `tareas_run.py` retries a failed start 3 times, 5 minutes apart, then drops the request (exit 2, ops alert); the task stays open. The waker also counts how many times it ran the task hooks for one request (`task.max_tries`, default 5) and drops the request with an alert at the cap, so a broken hook cannot wake the stack every ~10 minutes until the request goes stale (6 h). A stack with no free RAM is retried every 10 minutes for up to 6 hours, silently.
