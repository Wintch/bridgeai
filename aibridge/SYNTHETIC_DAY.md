# Synthetic business days: what a multi-bot team consumes per day 

Status: design, plus a v1 harness built and selftested offline (section 10). Nothing was run against a real stack. Every number marked **[assumption]** is a placeholder to be replaced by a
measurement from the first run; every number marked **[measured]** comes from a file in this repo, cited.

Related: `MULTI_BOT_TASKS.md` (the ladder, the board, the key pool), `HERMES_ARCHITECTURE.md` (baselines, wake-on-demand),
`ops/keys_usage.py`, `ops/telemetry.py`, `ops/stack_usage.sh`, `ops/bench_models.py`, `GPU_RENTAL_AND_MODELS.md`, `VIDEO_BENCH_RESULTS.md`.

## 0. Why

Before a team of bots is offered to a business (a person with four to six bots, each on its own stack, handing work down a ladder through
Gitea), the operator has to be able to say three things with a range and not a guess: what it costs per day and per month, how much of a
provider's free allowance it burns, and how many such businesses one VM carries. A person's single assistant is already measured
(about 10.5 model calls per session, about 6.5k input tokens per call, **[measured]**, `HERMES_ARCHITECTURE.md`).
A team is not that times six: the bots run scheduled work with nobody chatting, chains wake bots one after another, and one runaway bot
on a shared key can starve the others (`MULTI_BOT_TASKS.md` section 9.3 point 6). The synthetic day is the test that shows it.

## 1. What is estimated

Per bot and per business, per day, for a quiet, a normal and a busy day:

| Quantity | Unit | Where it comes from today |
|---|---|---|
| Awake time | minutes per bot, count of wakes | `awake` table and waker journal `ready after`, `waking`, evictions (`telemetry.py`, `waker.py:986,1014,1372`); no logged duration, so approximate |
| Turns, tool calls, tool errors, failed and empty turns | counts | `turns` table (`telemetry.py:43-85`) |
| Model calls | count per provider and model, main versus `aux` | `.model-eval.jsonl` (`router.py:1048-1063`) and `session_model_usage` (`keys_usage.py:94-119`) |
| Input and output tokens | tokens per provider and model | `session_model_usage` per session; completion tokens in the eval log only if the provider sends `usage`; otherwise estimated (section 5.2) |
| Latency | seconds per turn, p50 and p95; first-byte time per call | `turns.seconds`; `ttfb` in the eval log |
| Memory | footprint per awake bot (MB), peak concurrent awake bots, evictions and postponed wakes | waker `footprint` lines (`waker.py:1041`); **[measured]** brain 600-700 MB, web tier 300 MB (`MULTI_BOT_TASKS.md:245`) |
| GPU | minutes, watts, Wh | gateway log `gpu_seconds`, `cpu_seconds` (`gateway.py:202-205`); watts and Wh only from bench runs (`VIDEO_BENCH_RESULTS.md`), no production meter |
| External API calls | count per service per day | AudD, Zabbix, Postiz, PBS, Gitea: not logged as a total today; the stubs of section 3 count them |
| Gitea | tasks created, hops, comments, depth reached, tasks refused by the depth or cycle rule | the board itself plus the gateway's `tareas` log lines (no titles or bodies) |
| Money | dollars per day and month where a price exists | none in our code (no cost column is read); computed with the formula of section 5.3 |
| Free-tier burn | percent of each provider's daily or windowed allowance | Cloudflare neurons (10,000 a day), OpenRouter free-model requests (`keys_usage.py:79-91`), Token Harbor 60 requests a minute and 1,800 an hour (`ops/lib/providers.py`, tokenharbor comment) |

Two quantities matter more than the rest for the offer: **peak concurrent awake bots** (it decides how many businesses fit a VM) and
**input tokens** (they are roughly 95 percent of all tokens a day, section 5.1, so they decide the money).

## 2. Four businesses, different on purpose

Role names follow `MULTI_BOT_TASKS.md` sections 10 to 12: novedades (reads feeds and Zabbix, files tasks), tecnico (the site), sysadmin
(root on the host, with owner approval), backupbot (verifies backups), developer (code on a branch, human merge), marketing (owns the
publishing tool; nothing goes out without explicit approval), and a **diseñador** (design and generative media: `gateway image`,
`makevideo`, `enhance`; it is not yet in the ladder documents, so its profile is a proposal of this note). The customer-facing
**atención** bot is later and appears in no profile; section 7 asks whether to model it now.

All names, products and numbers inside the scripts are invented. No real business, person or host appears in the repo.

| | P1 Burger shop | P2 Accounting office | P3 Online shop | P4 Design studio |
|---|---|---|---|---|
| Bots | novedades, tecnico, marketing, backupbot (4) | novedades, sysadmin, backupbot (3) | novedades, tecnico, sysadmin, backupbot, developer, marketing (6) | novedades, diseñador, marketing, developer, backupbot (5) |
| What dominates | social posts, a small ordering page, owner questions about delivery and prices | documents (PDF, spreadsheets), deadlines, a small office server | a shop website, stock, campaigns, a real host to patch | image and video generation, client previews, large files to back up |
| Heavy resource | tokens (many short owner turns) | tokens per turn (documents are long), privacy class | chain depth and wakes (ladder busy) | GPU minutes and neurons |
| Privacy stress | low | high: real use must avoid class C providers (`ops/lib/providers.py` PRIVACY); the synthetic run uses invented documents, so class C is allowed for the test only | medium | medium |
| Ladder use | novedades > tecnico; marketing asks the owner | novedades > sysadmin > backupbot | the full chain novedades > tecnico > sysadmin > backupbot (depth 3, the default maximum) | diseñador > marketing, marketing needs the owner's OK |

### 2.1 The day script

A script is a list of timed events with a tag, a source (owner, schedule, bot, system), the bot that receives it and a volume. Times are
the business's local clock; the harness compresses them (section 3.4). Each event is one row of a script file the harness replays;
the volume columns are how many instances of that event the day holds.

Event types, with what each one touches (so the estimate of section 5 can price them):

| Id | Event | Touches |
|---|---|---|
| E1 | Morning revista: one scheduled agent turn per day (`SKILL_revista.md`, `hub/HUB.md:169`) | wake by cron or by first message, 1 turn, hub reads (no tokens) |
| E2 | Security advisory crossed with Zabbix: novedades reads a feed and the inventory, files a task for tecnico or sysadmin (`MULTI_BOT_TASKS.md` 10.4) | Zabbix reads, Gitea issue create and labels, 1 wake per rung, depth up to 3 |
| E3 | Owner message: a question, an order, a correction | 1 turn on one bot, some tool rounds |
| E4 | Task handed down the ladder and answered back by comment | Gitea create, comment, close; waker task wake (`tareas_hook.py`); 1 `/v1/runs` turn on the receiver |
| E5 | Design request with a cost justification: diseñador estimates the generation cost (GPU seconds, rental price or neurons) before doing it, owner approves | text turns, `gateway image` or `makevideo`, GPU seconds, approval |
| E6 | Backup verification: backupbot verifies the latest backup and restores it to a scratch place (`MULTI_BOT_TASKS.md` 11.4) | PBS (stub), 1 small-model turn, a stamp |
| E7 | Campaign needing every party's OK: marketing drafts, developer supplies text or a page, diseñador supplies a picture, the owner approves each step, marketing schedules (`gateway postiz`) | Postiz (stub), 2 to 3 hops, 2 to 4 approvals, one `schedule` call |
| E8 | A bot misbehaves (runaway or flood) on a shared key: a loop of calls for a fixed number of minutes | the test of section 9.3 point 6: quota burn and cross-bot starvation |
| E9 | Song or other media lookup, weather, places: occasional owner asks that call a paid or limited external API (`gateway song`, AudD) | external call counter |
| E10 | The idle day: nothing but crons, hub collectors and sleep timers | wakes with no chat; shows the floor cost |

Volumes per profile (instances per day; Q = quiet, N = normal, B = busy; a bot's own count in brackets where it differs):

| Event | P1 Burger shop Q/N/B | P2 Accounting Q/N/B | P3 Online shop Q/N/B | P4 Design studio Q/N/B |
|---|---|---|---|---|
| E1 revista | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 |
| E2 advisory | 0/1/3 | 0/1/2 | 1/2/5 | 0/1/2 |
| E3 owner messages | 2/8/25 | 3/10/30 | 3/12/40 | 3/10/30 |
| E4 hand-downs (not counting E2 and E7) | 0/2/6 | 1/3/8 | 2/6/15 | 1/4/12 |
| E5 design requests | 0/1/3 | 0/0/1 | 0/1/2 | 2/8/20 |
| E6 backup verifications | 1/1/2 | 1/2/3 | 1/1/2 | 1/2/4 |
| E7 campaigns | 0/1/2 | 0/0/0 | 0/1/3 | 0/2/5 |
| E9 external lookups | 0/2/6 | 0/1/3 | 0/1/3 | 0/1/3 |
| E10 idle days | one extra run per profile with all of the above set to 0 | | | |

The timeline of a normal P3 day, as an example of what a script file holds (clock times local; payloads are templates with invented
values, never real text):

| Time | Event | To | Notes |
|---|---|---|---|
| 07:00 | E1 revista | novedades | cron wake; reads hub and feed items; no task |
| 07:30 | E2 advisory "PHP 8.1 loses security fixes" crossed with a Zabbix item that reports 8.1 | novedades > tecnico | depth 1, then 2 sysadmin, then 3 backupbot only if tecnico finds the host must change |
| 07:35 to 08:10 | chain rungs wake one after another | tecnico, sysadmin, backupbot | a rung wakes in about 20 to 30 s unless the RAM guard postpones it (`MULTI_BOT_TASKS.md` 10.4) |
| 09:15 | E3 owner: "how many orders did we get today and is stock low on item 12" | tecnico | stock is a fake JSON file served by a stub |
| 09:40 | E4 owner: "ask the developer to fix the footer on the cart page" | developer | task from a person, depth 0 |
| 10:30 | E7 campaign start: owner asks marketing for a weekend promotion | marketing | asks developer for a landing text, asks the owner for the discount |
| 11:00 | owner approves the discount; marketing drafts three posts | marketing | Postiz stub `draft` only |
| 11:20 | owner approves the draft; marketing calls `programar` | marketing | the one `schedule` call, 60 minute lead |
| 13:00 | E3 owner: delivery-time question | tecnico | |
| 15:00 | E6 backup verification | backupbot | PBS stub returns a verified stamp, one run stamped stale on busy days |
| 16:30 | E5 design request: "a banner for the promotion, tell me what it costs first" | marketing > developer | for P3 the banner is a gateway image call; P4 asks diseñador |
| 18:00 | E3 owner: end-of-day question | tecnico | |
| 22:00 | system: sleep timers, nothing | all | idle sleeps confirm the floor |

The other three profiles get script files of the same shape. Their distinguishing events:

- **P1 Burger shop.** 11:30 and 18:30 delivery-rush clusters of E3 (6 to 12 messages inside 20 minutes: they test burst handling and the
  bot staying awake); marketing asks the owner for a photo of the day's special (image gateway call, class A provider); one E9 song or
  weather lookup. Tecnico serves the ordering page; sysadmin is absent, so an advisory that needs root ends in `estado/necesita-persona`
  (the ladder's "needs a person").
- **P2 Accounting office.** Deadline items from novedades; E3 owner messages that attach documents (the `doc_extractor` path: PDF and
  spreadsheet text goes into the prompt, so the input tokens per turn are the highest of the four, **[assumption]** 2 to 4 times the
  baseline); a backup verification before a quarterly close, twice on a normal day. No marketing, no developer.
- **P4 Design studio.** Diseñador is the busiest bot: eight design requests on a normal day, each with a cost justification turn
  (GPU seconds times a rental price, or neurons against the daily 10,000), then one generation, then an owner approval; one `makevideo`
  call per two requests; client preview posts through marketing. Backupbot verifies a large media store (the PBS stub returns bigger
  sizes). Developer touches the studio's portfolio page.

Scripts are data, in JSON next to the harness (proposed `aibridge/synthetic/scripts/<profile>.json`), so a new business is a new file and
not new code. Message templates carry a tag `[SYN:<run-id>:<event-id>]` so the fake model (section 3.1) knows which scripted answer to
give and the harness can match every log line back to its event.

## 3. Two run modes

### 3.1 Mode A: fake model, real pipeline, no tokens spent

An OpenAI-compatible stub (proposed `aibridge/synthetic/fake_llm.py`, one small container) answers `/v1/chat/completions`, streaming and
not, with scripted text and scripted tool calls chosen by the `[SYN:...]` tag in the latest user message and by the step number inside the
turn. The tool calls it emits are complete command lines with the arguments the real command needs (`gateway tareas nueva "TITLE" --para BOT
[--pedido-persona]`, `hub feed --new`, `gateway zabbix problems`, `gateway image ... -- PROMPT OUT`), with `{n}`, `{event}` and `{next}` (the role of
the event's first hop) filled in by the fake; the real gateway, the real Gitea board, the waker, the receiver hook, the RAM guard and the router
all run. Two honest limits: `gateway postiz` and `gateway pbs` are only PROPOSED (`MULTI_BOT_TASKS.md` 11.3, 11.4), so their arguments follow that
design and on a stack without them the call fails; and the fake READS the tool results, counting every one that looks like a usage error or a failed
command (`tool_errors`), so a scripted command that did nothing is a warning in the report and not a silent pass. The selftest runs every scripted
command through the real parser of `tareas.py` and against the real command list of `gateway.py`.
What it measures is **infrastructure**: wakes, boot times, RAM, evictions, depth and cycle refusals, Gitea call counts, whether a chain
completes, how long, and what the RAM guard postpones.

Three properties make mode A better than a toy:

1. **The input is real.** Hermes builds the real prompt (system text, the skills index, tool schemas, history) and sends it to the stub.
   Only the answer is scripted. So the **input size of every call is the real size**, and it is the larger part of the tokens (section 5.1).
   The stub records, for each request and counts only, the character length of the request body, the number of messages, the number of
   tools and a hash of the tag. It estimates prompt tokens as characters divided by a calibrated ratio (section 5.2) and returns that in
   the `usage` object, so everything downstream that reads `usage` gets a number. This closes gap 1 of the instrumentation list (no
   prompt tokens per turn in any log we control) for the synthetic runs.
2. **The output is shaped, not guessed once.** Scripted answers draw their length from a distribution per event type (a short owner reply,
   a 150-token answer, a tool call with arguments), set in the script file, and the stub reports `completion_tokens` accordingly. The
   distribution is the **[assumption]** that mode B replaces with measurements (section 5.2).
3. **Failure is scriptable.** The stub can answer 429 with `Retry-After`, hang past the router's timeout, return invalid tool-call
   arguments, or answer with no `usage` at all, to exercise the router's fallback chain (`router.py:587,613,653`) and cooldowns, and the
   runaway of event E8 (a scripted loop of tool calls).

Where the stub runs is not settled and is the first thing to verify: a guest's egress is internet only (LAN, RFC1918 and other docker
networks are dropped by `docker-user-fw.sh`), so a stub on the LAN is unreachable. Options, to verify on a test stack: a sidecar container
on the stack's own compose network, or a firewall pinhole for the stub's address on test stacks only. Whether a person-style stack's
router can be pointed at a custom base URL (it has provider URLs in `ops/lib/providers.py`, and `router_smoke.py:25-72` already runs a
fake endpoint in-process) is **not verified**; if it cannot, mode A on router-bearing stacks needs a small override in the test stack's
config, never a change to the shared providers table.

External services in mode A are stubs too, one tiny HTTP server each, each counting calls and returning canned, invented data:

| Stub | Answers | Counts |
|---|---|---|
| Zabbix | `user.checkAuthentication`, host and item reads (a PHP version item, a backup stamp item, a few problems) | calls per method |
| Postiz | channels, `draft`, `schedule`, status; refuses `now` like the real narrow gateway does | calls per endpoint; the 90 requests an hour limit is enforced to see if a campaign trips it |
| PBS (or object storage) | a list of snapshots, a verify result (fresh, stale, failed per script), a restore-test result | calls per action |
| Gitea | not stubbed: a real local Gitea on the test side, one organisation per business (`MULTI_BOT_TASKS.md` section 2), so the board's cost and the receiver hook are real | issues, comments, labels (read from Gitea's own counters or the hook's journal) |
| AudD and similar | one canned song name | calls |
| Stock, orders, documents | fake JSON files and generated PDFs with invented text | none |

Stubs listen only on the test side; real endpoints are never reachable from a test stack unless the operator points to a real test
instance in the private config (section 4).

### 3.2 Mode B: real keys on test stacks, measuring tokens, latency, quota burn

The same scripts, the same stacks, with the stub replaced by real providers using the operator's keys. What it measures is
**tokens, latency and quota burn**: real prompt and completion tokens per call, real first-byte and turn seconds, 429s and cooldowns,
the share of Cloudflare neurons and free requests used, and the real behaviour of tool calls on the models offered. Message templates
are invented, so class C providers (which train on or log prompts, `PRIVACY` in `ops/lib/providers.py`) are acceptable **for this
test only**, exactly as `bench_models.py` already treats them ("benchmarks with synthetic prompts only").

Order of work: run mode A first to debug the pipeline and fix the harness for free, then run mode B for one profile and one provider at a
time, then compare. The comparison is itself a result: mode A input characters (the fake's request sizes) against mode B input tokens (provider's
`usage` or `session_model_usage`) per call gives the calibration ratio of section 5.2, per provider. It is computed OFFLINE, by joining a mode a
report and a mode b report of the same profile, load and seed (`ops/synth_day.py --calibrate A.json B.json`), and never inside one run: in mode A
the "reported" tokens are the fake's own estimate (the stack only relays them), so a ratio taken there is 4.0 by construction. Mode A dollars come from
that estimate and from scripted output sizes, and are for scale only.

Probes mode B must include, because the repo does not say: whether NVIDIA, Token Harbor, Gemini, OpenRouter and Hugging Face return
`usage` in a stream, and whether `stream_options.include_usage=true` is needed (the router passes `stream_options` through, never sets it:
`router.py:112`). A stack whose provider returns no `usage` falls back to the estimate and says so in the result row.

### 3.3 What is stubbed or real, in short

| Piece | Mode A | Mode B |
|---|---|---|
| Model | stub | real providers, invented prompts |
| Hermes, router (where present), gateway, tareas, waker, hook, RAM guard | real | real |
| Gitea | real, local, test organisations | same |
| Zabbix, Postiz, PBS, AudD | stubs | stubs, unless the operator names a real test instance in the private config |
| GPU gateways (image, makevideo, enhance) | stub that sleeps for a configured `gpu_seconds` and returns a tiny file | the real gateway on the GPU host for a few calls per profile, or a rented card (`GPU_RENTAL_AND_MODELS.md`); otherwise stub |
| Telegram | not used: the harness drives each stack through its OpenAI-compatible API (below) | same |

### 3.4 Driving a stack without Telegram, and compressing the clock

Each test stack exposes `http://<host>:<port>/v1` with a key (`provision_guest.sh` prints it; a person-style stack has the same API
inside its network). The harness posts each event as a chat message to that stack's API, tagged `[SYN:...]`, at its scheduled time. Task
events and the receiver are driven the other way round: the harness creates the Gitea issue as the owner's account and the receiver wakes
the assigned bot as it would in production.

The clock can be compressed: a day of events replayed in 30 to 60 minutes of wall time. What does not compress is the waker's idle timers
(600 s for web and brain, `waker.py:363`), boot time and RAM: compressing the timeline without compressing those makes the test **more**
crowded than a real day, which is a safe error for capacity, and a wrong one for awake minutes. So the awake minutes of section 5.4 are
computed from the real script times and the measured per-event active seconds, not read from a compressed run. One full real-time normal
day per profile is part of phase 3 as the control.

The tools that read the results all need the VM side (SSH and docker): `ops/telemetry.py`, `ops/stack_usage.sh`, `ops/keys_usage.py`,
`ops/chat_review.py`. The harness therefore runs on the VM, next to them; this repo checkout cannot run it. The operator runs it and
brings back the counts file of section 6.

## 4. Safety

1. **Only test stacks, never a person's bot.** The harness accepts a stack only if its name is in a private config the operator writes
   (proposed `aibridge/ops/synthetic.json`, to be added to `.gitignore` when built, like `ops/gateways.json`), and the name must also
   start with `syn-` or be a guest created by `provision_guest.sh`. It refuses any other name, and refuses any stack whose
   Telegram token or chat id is set unless the operator listed it with a flag saying the bot is a test bot. **What the harness can and cannot see:** only
   its private config. It cannot see a stack's bot token, nor whether a stack really is a guest, so both are the operator's statements, and the check
   is default-deny: every target must say `"no_telegram": true` or `"test_bot": true`, or it is refused. An operator-run preflight (section 10) reads the stack's own env for a token. The same file lists any real
   test instance of Zabbix, Postiz or PBS the operator wants used; otherwise stubs. The repo carries `synthetic.json.example` only, with
   placeholders.
2. **No personal data, host name, IP or key in the repo.** Scripts and templates are invented. The private config, the keys, the counts
   files and the report with real numbers stay on the VM or the operator's machine; the repo gets only the harness and the example
   files. The usual `ops/privacy_scan.sh` runs on the harness before any commit.
3. **Keys of the operator are for testing only, recorded per provider.** Each key the run uses is listed in a run manifest (provider,
   a label such as "test key 1", the date, the stacks that used it, never the value). A test key is not shared with a real person's
   stack; if a run exhausts a free allowance, that is a result and also a cost to the operator that the manifest makes visible. A paid key
   has a spending cap set at the provider before the run, and the harness stops the run when `keys_usage.py` shows the cap approached.
   (Keys are one per bot on the test stacks, or a few shared ones per business, so the shared-key effect of event E8 can be measured; see
   open decision 2.)
4. **Results without content.** The harness and the stub log counts and sizes only: event id, tag hash, bot, provider, model, number of
   calls, characters, tokens (reported or estimated and marked), seconds, tool names and counts, HTTP codes, Gitea call counts, depth
   reached, refusals by code. No message text, no task titles or bodies, no tool arguments. The `/compartir nada` opt-out stays at its
   default on test stacks so `stack_usage.sh` and `chat_review.py` can read them (`stack_usage.sh:19-23`, `chat_review.py:35-41`); a
   synthetic conversation is checked with `chat_review.py`'s structure view, not by reading text.
5. **Egress and blast radius.** Test stacks keep the standard firewall. The stub and the fake services are reachable only from test
   stacks. The harness has a hard cap on the number of model calls per run and per bot, and a kill switch that stops event replay and puts
   the test stacks to sleep.
6. **Generative content.** Design events use invented prompts that follow `GENERATIVE_SAFETY.md` (no real person, no brand); nothing the
   run produces is published: Postiz is a stub, and the real narrow gateway cannot send `now` anyway.

## 5. The estimate model

### 5.1 From per-event costs to a day

The estimate is a sum over events. For each event type *e* and bot role *r* the runs give a **unit cost vector**
`u(e, r) = (calls, input_tokens, output_tokens, tool_calls, active_seconds, gpu_seconds, ext_calls)`, measured as the median and the 90th
percentile over repeated runs of the event in isolation (phase 2). A day is

```
day(profile, load) = sum over e in script of  volume(e, load) * u(e, r(e))   +   floor(profile)
floor(profile)     = wakes with no chat (crons, hub, sleep timers) of E10
```

Tokens are priced separately because inputs dominate: with the baseline of about 6.5k input tokens per call and **[assumption]** about
350 output tokens per call, input is about 95 percent of the tokens of a call. That is why mode A, which measures input faithfully, is
already most of the answer.

First-order unit costs to start from, until phase 2 replaces them (calls per event are **[assumption]**; the 6.5k per call and the
person-stack baselines are **[measured]**):

| Event | Calls | Input tokens | Output tokens | Notes |
|---|---|---|---|---|
| E1 revista | 4 | 26k | 1.4k | one agent turn plus hub reads |
| E2 advisory, novedades side | 8 | 52k | 2.8k | feed and Zabbix reads, one task filed |
| E3 owner message | 4 | 26k | 1.4k | median; 12 or more in a burst; the longest turn seen had 27 tool steps (`HERMES_ARCHITECTURE.md:4512`) |
| E4 hand-down, sender side | 4 | 26k | 1.4k | an owner turn that files the task, priced like E3 |
| Receiver rung, per hop of an E2 or an E4 (only those) | 5 | 33k | 1.8k | one wake, one `/v1/runs`, a comment back; `RECEIVER_SIDE` in the harness |
| E5 design request | 6 text calls | 39k | 2.1k | plus gateway work and GPU seconds; the row spans every bot of the event, no add-on |
| E6 backup verification | 4 | 16k | 1.4k | small model and narrow pack, so a smaller prompt (assumption 4k per call) |
| E7 campaign | about 20 across bots | 130k | 7k | three hops, two to four approvals; spans every bot of the event, no receiver add-on |
| aux per turn | 1 | small | small | titles and memory review go to the router as `local-only`, not the main model; counted apart |

Worked example, **P1 Burger shop, normal day**, every event type assumed (the harness computes the same figure from the same table and the selftest
checks it, so the example and the code cannot drift apart again). Calls: 1 revista (4) + 1 advisory (8) + 8 owner messages (32) + 2 hand-downs, sender
side (2 x 4 = 8) + 1 design request (6) + 1 backup verification (4) + 1 campaign (20, the whole event) + 2 external lookups (2 x 4 = 8) = 90, plus a receiver
rung for the advisory's hop and for each hand-down's hop (3 x 5 = 15) = **105 calls**. Input: 26k + 52k + 208k + 52k + 39k + 16k + 130k + 52k = 575k, plus 3 x
33k = 99k, so **about 0.67M input tokens**; output about 31.5k plus 3 x 1.8k = **about 37k**. A month (4 quiet, 22 normal, 4 busy) is about 3,500
calls, 22.6M input and 1.24M output tokens. Quiet (0.094M input) and busy (1.85M) bracket the day. The same arithmetic for P2 with documents (2 to 4
times input per owner turn, **[assumption]**) can exceed P1 even with fewer events. An earlier version of this example gave 66 calls and 0.42M input
because it left out the design request, the lookups, the campaign's other bots and the sender side of the hand-downs; the code and the table now agree.

### 5.2 When tokens are not reported

Order of preference, each row of the result marked with the method used:

1. **Reported:** the provider's `usage` in the response (`prompt_tokens`, `completion_tokens`) or Hermes's `session_model_usage` per
   session and model (`input_tokens`, `output_tokens`, `cache_read_tokens`). Per-turn numbers come from differencing
   `session_model_usage` before and after a turn on a session that is new for the test (one event per session), because it is stored per
   session, not per turn.
2. **Estimated from the request:** characters of the request body divided by a **calibration ratio**, kept per provider and per model
   family. The ratio comes from mode B: for every call where both a character count (the stub's own measure, or the router's `sent`) and a
   reported `prompt_tokens` exist, the ratio is the quotient; its median and spread are written to the report. Start at 4 characters per
   token **[assumption]**, the usual rule of thumb, and replace it.
3. **Estimated from the output:** `out` characters in the eval log divided by the same kind of ratio (the log keeps the answer length in
   characters, `router.py:1048-1056`).
4. **Cloudflare:** its own unit, neurons, summed per call (`router.py:1009,1034-1036`), converted to a percent of the 10,000 a day cap;
   not converted to tokens.

A model call that carries tool schemas is larger than its messages: the estimate counts the full request body, tools included, since
that is what the provider counts.

### 5.3 Money and free-tier burn

Money, per day and per profile:

```
dollars = sum over provider/model of ( input_tokens / 1e6 * price_in  +  output_tokens / 1e6 * price_out )
          + GPU: gpu_seconds / 3600 * rental_price_per_hour   (or owned card: Wh from VIDEO_BENCH_RESULTS times the electricity price)
          + paid external APIs: calls * price per call
```

Prices are not in the repo and change; the day-of-run price page is read and written into the run manifest. For scale only, the
same 0.67M input and 37k output tokens priced at three **illustrative** tiers (per million input/output): 0.10/0.40 gives about $0.08 a day
($2.8 a month); 0.50/2.00 gives about $0.41 ($14 a month); 3.00/15.00 gives about $2.60 ($86 a month). The spread across tiers is
thirty-fold, which is why the model choice per bot (a small model for backupbot, a stronger one for sysadmin) is part of the offer and of
the test: the harness runs each profile on at least two model tiers.

GPU: rental at the prices in `GPU_RENTAL_AND_MODELS.md:103-112` (for example a 4090 at $0.89 an hour is about $0.015 a GPU minute, plus
warm-up), or watts: Wh = (average draw minus the 18 W resting draw) times seconds divided by 3600, the definition in
`VIDEO_BENCH_RESULTS.md:10`; 130 W is the measured best for generation. There is no production meter, so GPU cost in the first runs is
`gpu_seconds` from the gateway log times a constant from the bench documents, and the report says so.

Free-tier burn, as a percent of the daily or windowed allowance, per provider key and per run:
- Cloudflare: neurons per day against 10,000 (a design studio's busy day is the case most likely to hit it; image calls have a
  neuron equivalent per image that the first runs measure).
- OpenRouter: free-model requests per day, read live from `keys_usage.py` (`free_model_daily_requests`, remaining limit and credits).
- Token Harbor: requests per minute against 60 and per hour against 1,800, and the 429 with `Retry-After`; the weekly window has no
  published size, so it is reported as tokens used, not as a percent.
- NVIDIA, Gemini, Hugging Face: no remaining-quota API (`keys_usage.py:7-11`): calls and tokens only, plus any 429 seen.

The per-minute limits matter more than the daily ones for a team: a chain wakes bots within seconds of each other, and several bots on
one key share one minute.

### 5.4 Memory, concurrency and awake time

- **Footprint per awake bot:** the waker's `footprint` line, **[measured]** about 600 to 700 MB for the brain and about 300 MB for the
  web tier, so about 1 GB for a bot with its web tier up. The compose limits (2560M on a stack, 1536M on a guest) are ceilings, not
  footprints.
- **Awake minutes per bot per day:** events are grouped into clusters; a cluster is a run of events less than 10 minutes apart (the
  idle timer, 600 s). Each cluster keeps the bot awake for its span plus its boot time (median `ready after`) plus 10 minutes of idle.
  `awake_minutes = sum over clusters (span + boot + 10)`. A bot with only a morning revista and one afternoon owner message is awake
  about 2 x (boot + 10 + active) minutes, around 30 to 40 minutes, not the whole day; a delivery-rush burst keeps one bot awake through
  the rush.
- **Peak concurrent awake bots:** the maximum over the day of the number of bots awake at once, computed from the same clusters. It is
  the number that sizes the VM. A chain contributes at most the rungs awake inside the same 10 minute idle window, which is more than
  one at a time when a rung is slow.
- **What the RAM guard does:** it postpones wakes (`task wake postponed .. not enough free memory`) and evicts a stack
  (`evicted by the RAM guard`), so a memory shortage appears as **latency and refused work**, not as a crash. Each run records postponed
  wakes, their delay, evictions and chains that did not finish in a stated time.

### 5.5 Businesses per VM

```
businesses = floor( usable_RAM / ( f * mean_peak_awake_bots * 1.0 GB ) )
usable_RAM = VM RAM - reserve for the host, Gitea, the waker, the hub collectors, the stubs excluded (reserve measured, start 4 GB [assumption])
f          = share of businesses whose peaks coincide (1.0 worst case, all at once; 0.5 typical; below 0.5 if wakes are staggered)
```

Peak awake bots per profile, **[assumption]** until the first run: P1 2, P2 3, P3 4, P4 3 (mean 3). With a mean of 3 and the 4 GB
reserve:

| VM RAM | usable | f = 1.0 | f = 0.5 |
|---|---|---|---|
| 16 GB | 12 GB | 4 | 8 |
| 32 GB | 28 GB | 9 | 18 |
| 64 GB | 60 GB | 20 | 40 |

These are upper bounds on memory only. Three other limits can bind first and the run must report them: **CPU** (a boot and a document
extraction are CPU work; not measured here), **provider rate limits** on a key shared by many businesses (Token Harbor's 60 a minute is
per account), and the **morning correlation**: every business has a revista around the same clock hour, so f is high at 07:00 unless the
operator staggers them. Staggering the scheduled wakes is a cheap, measurable lever; the harness runs both a synchronised and a
staggered morning for the same set of businesses.

### 5.6 Ranges, not points

Every figure is reported as `p50 (p10 to p90)` over at least 5 repeated days per profile and load, never a single run. The report
separates three sources of spread: variation across repeats of the same day (model nondeterminism), the quiet/normal/busy load, and the
model tier. A month is thirty days of the mixture the operator chooses (default: 4 quiet, 22 normal, 4 busy), with the busy tail shown on its
own because the free-tier caps are decided by it.

### 5.7 What the first results should answer

1. Tokens per business per day for each profile, and which event types account for 80 percent of them.
2. Awake minutes and peak awake bots per profile, and the effect of staggering.
3. How many businesses a 16, 32 and 64 GB VM carries before the RAM guard starts postponing wakes (section 5.5), and which other limit binds.
4. Dollars per business per month at two or three model tiers; free-tier burn per provider key.
5. Whether a shared key survives one bot's runaway (event E8): the other bots' failure rate and delay while it runs, and how fast
   the router's cooldown and the per-bot limits (`MAX_MADE_DAY` of `tareas.py`, call caps) stop it.
6. How long a three-rung chain takes end to end, and how often a rung is postponed by the RAM guard.

## 6. The result file

One JSON file per run, counts only, written on the VM, brought back by the operator, and summarised in a table in a dated section of this
file or of a separate results note (no private names). Per run: run id, mode (A or B), profile, load, stacks used by role (not names), the
manifest of keys (labels only), script version; then per event: id, bot role, calls, input and output tokens with the method flag
(reported, estimated from request, estimated from output), tool calls and errors, seconds, wakes caused, postponed wakes, depth reached,
Gitea call counts, external call counts, GPU seconds; and per bot: awake minutes, peak footprint. A reader (proposed
`aibridge/synthetic/report.py`) builds the per-day and per-month estimate of section 5 from a set of such files and from nothing else.

## 7. Phases

0: close the instrumentation gaps (a per-turn token reader on `session_model_usage` differencing). 1: the harness skeleton, stubs and counts file (built, section 10).
2: unit costs per event type on the fake model, then on one provider. 3: full days, one profile at a time (quiet, normal, busy), five repeats plus one real-time control day.
4: capacity and stress (staggered versus synchronised mornings, the runaway bot on a shared key, a shrunk VM). 5: the offer numbers: a per-business monthly range, the fit table and a
model-tier recommendation per role. Phases 0 and 1 spend no model tokens; the size of phase 3 is fixed from phase 2 and approved before it starts.

## 8. Open decisions

How long to run (five repeated days per profile is a statistical minimum), which price pages to use for paid providers and for GPU electricity or rental, and whether the
`atención` bot is modelled. They are set in the private run config, not here.

## 9. Not verified

Everything tagged **[assumption]**. The profiles' volumes should be replaced by what an owner of each kind actually does, once a real run exists.

## 10. v1 harness (built, offline only)

What exists, all in `aibridge/ops/` (standard library only, no docker, nothing deployed; paths differ from the proposals above):

| File | What it is |
|---|---|
| `synth_day.py` | The runner: loads a scenario, lays the day on a clock from the load's volumes (seeded, so a day repeats), replays it against test stacks through their Hermes API, writes a counts-only JSON report per run and a markdown summary. `--dry-run` prints the plan only. |
| `synth/<profile>.json` | The four businesses (`burger`, `accounting`, `shop`, `design`) with loads `quiet`, `normal`, `busy` (the volumes of section 2.1), `idle` (E1 and E10 only) and `runaway` (normal plus the E8 loop). Data, so a new business is a new file. All invented. |
| `synth_fake_llm.py` | The OpenAI-compatible fake model of mode A: scripted text and tool calls chosen by the `[SYN:<run>:<event>]` tag and the step number, streaming or not, `usage` from request size, scriptable failures (429, hang, bad arguments, no `usage`), hard call caps, `GET /counters`. |
| `synth_stubs.py` | Local stubs that count calls: Zabbix, Postiz (refuses `now`, 90 an hour), PBS (fresh, stale, failed, large), AudD, and a GPU stub that sleeps a configured time. |
| `synth_targets.example.json` | The shape of the private config `ops/synth_targets.json` (git-ignored, like `ops/synth_results/`). |
| `synth_day_selftest.py` | about 180 offline checks against the fake model and a fake Hermes API; picked up by `ops/run_selftests.sh`. Checks that could be circular (the fake Hermes sums the fake model's usage) are written against the request sizes the fake Hermes measured itself, the scenario file's own numbers, or a hand calculation; every scripted command goes through the real `tareas.py` parser and `gateway.py`'s command list. |

Decisions taken in v1 that the design left open:

- A target is accepted only if the private config lists it AND its name starts with `syn-` or it is marked `"guest": true`, AND it says either
  `"no_telegram": true` or `"test_bot": true`. Refusal is exit code 2 before any request. **The harness cannot see a stack's Telegram bot token,
  nor whether a stack is really a guest**: those lines are the operator's own statement, and a mislabelled real stack would pass. That is why the
  statement is required (default-deny) and why the preflight below exists. Mode b also needs `--approve-spend`, a `keys` manifest in the config
  (labels only) and a hard budget (`--max-tokens` and/or `--max-usd`).
- **Mode a proves the model is the fake.** It needs `fake_llm` in the config and, before the day, sends one tagged probe turn (event E0-01) to every
  target and reads the fake's `/counters` for it; a target the fake did not see is refused (exit 2) with nothing but the probes sent. The probe itself
  goes wherever the stack's model points, so on a stack that is still on a real provider it is one small real turn; that is the price of knowing.
- **Caps come from the plan.** Default `--max-turns` and `--max-turns-per-bot` are the planned turn count (per target for the second) x 1.2 + 3, printed
  as `planned N turns ... caps M` before a run; an explicit cap below the plan warns (mode a) or refuses (mode b, unless `--allow-truncate`). The old fixed
  defaults (60 and 25 in mode b) were below a normal day.
- **Mode b limits.** `--max-tokens` and `--max-usd` (at the dearest `--price`) are summed from the state.db difference or the API usage and checked
  before every turn; a turn that reports no token figure stops the run, since the budget cannot then be enforced. They cannot interrupt a turn already
  running: the overshoot is at most the turns in flight (`--workers`), and a stack's agent keeps running after `--turn-timeout` abandons the client, so a
  timed-out E8 turn runs `on_kill_cmd` at once. The runaway load (E8) needs `--allow-runaway` and a `cap_check_cmd`, which runs right before that turn;
  `cap_check_cmd` also runs before the first turn and then every `--cap-check-every` turns.
- **Kill and Ctrl-C.** The `KILL` file is polled every half second, also while the replay waits hours for the next event: `on_kill_cmd` runs at once
  and the run ends. Ctrl-C does the same and still writes a partial report. A turn already running is not interrupted (a `/v1/runs` poll stops).
- One session id per EVENT (its steps share it), so a unit cost is a **fresh-session cost**, not the cost of a long owner conversation with history and
  compaction; the E3 variant `--continue-e3` puts all E3 turns of a role in one session. Whether the stack honours the header is unverified.
- A task event (a bot files a task for the next rung) is driven only against a target with `"tareas": true`; otherwise its first step is
  skipped with the reason `target_has_no_tareas` and the estimate fills that event type from the first-order table of 5.1 and says so. A
  guest has no waker and no task hook (open decision 3), so on a guest the E2, E4 and E7 numbers are assumed, not measured. **Skipped steps still
  count in the awake model**: the sender at the script's `active_s` (default 60 s), every hop at its `active_s`, all marked assumed, and the summary
  warns how many steps were assumed; the capacity table is therefore never built from fewer events than the script has. A task event whose first step
  returns a failing tool result (the fake counts them) is warned about as "no task was created"; with a waker journal in the config a task event
  with no wake in the window is warned about as "no hop happened", and without one the report says hops are not observed.
- Hop rungs (the bots woken by a task) are not driven or counted by the harness: their turns run with the waker's fixed prompt and show in the
  fake model's `untagged` counters. Their cost in the projection is the first-order receiver side, added for E2 and E4 only (E5 and E7 rows already
  span every bot of the event; an assumed E4 is its sender, priced like E3, plus the receiver). Awake minutes for hops use the script's `active_s` (assumed).
- Tokens per turn, best source first: the difference of `session_model_usage` in a stack's `state.db` around the turn (config `state_db`, one
  turn at a time on that target), then the `usage` the API returned, then the fake model's request-size estimate. Each turn carries its source
  (`tokens_source`) and its method: in mode b `reported_state_db`, `reported_api` or `estimated_request`; in mode a always `fake_estimate`. Cache
  reads are carried apart (`cache_read_tokens`, `--price NAME=IN/OUT/CACHED`, `--cache-in-input` says whether `input_tokens` already includes them: not
  known, so the report warns whenever there are any). state.db figures are Hermes's own (an estimate when the provider returned no `usage`), include any other
  traffic on that file during the turn (crons, aux calls, woken hops), and the API usage is assumed to cover the whole turn; the harness warns when the
  two differ by more than `--usage-tolerance` (15 percent), and the first mode b run should check them by hand once.
- The report names roles and target labels, never stack names; it holds counts and sizes only (the selftest greps it for templates, tags, the
  key, the stack name, the address and answers).
- Awake minutes and peak concurrent awake bots are computed from the script times and measured seconds (5.4), not read from the compressed run.
  Boot time is the waker journal's median `ready after` if the journal is given, else 25 s (assumed).

Not built in v1: the reader that merges many reports into one results note (the summary covers the runs of one invocation), the per-profile
mixture across profiles on one VM, `docker ps` sampling to check the awake reconstruction, reading `ops/telemetry.py`'s database or
`ops/keys_usage.py` directly (both need the VM; the operator runs them after the day), a Gitea stub (the board is real or absent), and the
`atencion` bot. Not verified: that the Hermes API honours a session header (`--session-header`, default `X-Hermes-Session-Id`; one message per
request is stateless anyway), the `/v1/runs` status field names (a run whose status field is unreadable fails as `run_status_unknown`, which
is how the first run verifies them), and whether a stack's model can be pointed at the fake (below).

### Operator steps, mode A on a guest stack (no tokens spent)

All on the VM, from `~/aibridge`, and the writes are the operator's (the harness never writes to a stack).

1. Create the test guest: `./ops/provision_guest.sh syn-burger` (2 to 20 characters, a-z 0-9 and dashes). It prints the API URL and the API key.
   Save the key in a file outside the repo, mode 600.
2. Start the fake model and the stubs where the guest can reach them. A guest reaches the internet only (`docker-user-fw.sh` drops the LAN, other docker
   networks and the host), so a process on the host is not reachable. Two ways, to try in this order:
   - a pinhole for the test guest only: a line `<guest subnet> <host address> 8700` in `GUEST_PINHOLES` of `ops/aibridge-fw.conf` (one line per port
     used; the file's comments say how), then `python3 ops/synth_fake_llm.py --bind <host address> --port 8700` and
     `python3 ops/synth_stubs.py --bind <host address> --zabbix 8701 --postiz 8702 --pbs 8703 --audd 8704 --gpu 8705`;
   - or the same two programs in a small container attached to the guest's compose network.
3. Point the guest's model at the fake. In the guest's dashboard, or with `hermes config set` inside its container (not verified for this Hermes
   version): `model.provider custom`, `model.base_url http://<host address>:8700/v1`, `model.default synth-fake`, and any placeholder key the
   custom provider asks for. A stack with the router (a person-style stack) can instead take the fake as its home model: an `llm` entry with the
   fake's URL in that stack's `gateways.json`, then `ops/gateways_sync.py`; never change the shared providers table.
4. Preflight, read-only, because the harness cannot see a bot token: on the VM, for each test stack's container, both of these must print 0 (the first
   counts lines that set a Telegram bot token in the stack's Hermes env file, the second counts the characters of that variable in the container's
   environment; neither prints the value):
   `docker exec <container> sh -c 'grep -c "^TELEGRAM_BOT_TOKEN=." /root/.hermes/.env'` and `docker exec <container> sh -c 'printenv TELEGRAM_BOT_TOKEN | wc -c'`.
   A stack that prints anything else has a bot: it is not a target (unless the bot is one made for tests and the target says `"test_bot": true`).
   Then write `ops/synth_targets.json` from the example: the guest as a target with `"guest": true`, `"no_telegram": true` (your statement after the
   preflight; the harness refuses a target without it), `"api"`, `"key_file"`, `"roles": ["*"]`, `"fake_llm": "http://<host address>:8700"` at the top
   level (required in mode a), the stubs, and optionally `logs` (copies of `.model-eval.jsonl`, `.gateway-log.jsonl` and a text export of the waker
   journal). Task events need `"tareas": true` on a stack whose tasks config names the role names as peers (or start the fake with `--peer ROLE=BOT`).
5. Look at the plan: `python3 ops/synth_day.py --profile burger --load normal --dry-run`.
6. One event first, then the day: `python3 ops/synth_day.py --profile burger --load idle --mode a`, then
   `python3 ops/synth_day.py --profile burger --load normal --mode a --speed 600 --repeats 5 --price cheap=0.1/0.4 --price mid=0.5/2.0`.
   Before the day the harness sends one probe turn to each target and refuses (exit 2, `did not reach the fake model`) if step 3 did not take effect;
   that probe is one small turn on whatever the stack's model really is. The warning `the fake model saw none of this run's events` is the same
   thing noticed late. It prints `planned N turns ... caps M` first: read it.
7. Read `ops/synth_results/burger-normal-a-summary.md` and the JSON files. Then, on the VM, the tools the harness cannot run: `ops/stack_usage.sh`,
   `ops/chat_review.py` on one of the run's sessions (structure only), and `ops/telemetry.py report daily --print`.
8. Stop: `touch ops/synth_results/KILL` ends a running replay within half a second (also while it waits for the next event) and runs `on_kill_cmd` at
   once; Ctrl-C does the same and keeps a partial report. A turn already running is not interrupted. Remove the guest when done.

A first run is also the check of three unverified things: that the fake is reached (the warning above), that the tag survives into the model request
(the fake's `/counters` has the run's events), and that the API answers `chat` (try `--endpoint runs` if it does not).

### Operator steps, mode B with keys (tokens spent)

1. Decide the size first: turns per day times days times repeats (mode A tells the turns; the first-order table tells the tokens), and turn it into a
   budget the run cannot pass: `--max-tokens N` and/or `--max-usd X` with `--price` are REQUIRED in mode b (hard stops, checked before every turn; a
   turn in flight is not interrupted, and a turn that reports no token figure stops the run). Also set a spending cap at each paid provider.
   Free-tier keys: note the daily allowance.
2. A key per bot or a few per business (open decisions 1 and 2): put each key on a TEST stack only, through that stack's own key mechanism (a guest's
   dashboard, or `ops/stack_keys.py` for a person-style test stack). Never a person's stack, never a key already in use there.
3. In `ops/synth_targets.json` add `"keys": [{"label": "test key 1", "provider": "...", "roles": ["..."]}]` (labels only; the harness refuses mode b
   without it) and, per target, `"model_tier"` and, if the state database can be copied or mounted read-only, `"state_db"` for per-turn tokens.
   Remove `fake_llm` or leave it: the report warns if the fake saw the events.
4. Optional guard: `"cap_check_cmd"`, an argv that exits non-zero when a provider cap is approached (a wrapper around `ops/keys_usage.py`), run before the
   first turn and then every `--cap-check-every` turns; and `"on_kill_cmd"` to put the test stacks to sleep when a run stops. The runaway load (E8) is
   refused unless you pass `--allow-runaway` AND the config has a `cap_check_cmd`, which then also runs right before the E8 turn; a timed-out E8 turn
   runs `on_kill_cmd`, because the stack's agent keeps running after the client gives up.
5. Run one profile and one provider at a time: `python3 ops/synth_day.py --profile design --load normal --mode b --approve-spend --max-tokens 2000000
   --price mid=0.5/2.0`. The default caps follow the planned day (printed first); a cap below the plan refuses unless `--allow-truncate`. Run mode a with
   the same profile, load and seed first, then join the two reports offline for the calibration of section 3.2:
   `python3 ops/synth_day.py --calibrate ops/synth_results/<mode-a>.json ops/synth_results/<mode-b>.json` (per-call means, approximate; not part of a
   single run's report). Do one check by hand on the first mode b run that the state.db figures and the provider's `usage` agree (the harness warns past 15
   percent) and whether input tokens include cache reads (`--cache-in-input`, `--price NAME=IN/OUT/CACHED`).
6. Afterwards read `ops/keys_usage.py` for the keys used, and record each key in the run manifest (the report has the labels). A key whose free
   allowance ran out is a result: say so in the results note.
