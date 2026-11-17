# Scaling and costs

Status: planning document. Every number here is an estimate unless it says "measured", and even the measured ones come
from a short window on one small shared host with a few users. Use them to size a first plan, then replace them with your
own telemetry. Nothing in the staged resilience plan (section 7) is built yet except what section 7 says is true today.

Marks used below:
- **[M]** measured on a small shared host, as a range;
- **[E]** estimate or design target, not measured.

The cost calculator is `ops/cost_calc.py`. Section 4 explains how to use it.

## 1. Resource profiles per bot type

A Hermes brain (the agent process) sleeps when idle and wakes on demand. What a bot costs is mostly how long its brain is
awake, how many model calls it makes, and how much disk its data takes. These are the four profiles that matter.

| Profile | Awake per day | Model calls per day | Prompt tokens per day | GPU wall time | Backup size |
|---|---|---|---|---|---|
| Personal web bot | about 1 to 1.5 h [M] | about 35 | about 1.4 M | none | 0.1 to 0.2 GB |
| Personal chat-heavy bot | about 4 to 7 h on the sleep rule; about 24 h if kept warm [M] | about 170 | about 7 M | a few hours per month | 1 to 2 GB |
| Business task bot | about 0.1 to 0.6 h [M] | 6 to 30 | 0.1 to 1.1 M | none | a few MB |
| Media bot | about 0.5 to 0.8 h [M] | about 70 | about 3 M | bursty, 10 to 40 h per month [M] | a few hundred MB |

A rarely used personal bot is a fifth profile: under 0.1 h awake and almost no calls. A reception or support bot is a sixth,
and it is not measured. Plan it at 35 to 50 percent of business hours awake [E].

Facts that apply to every profile:
- **A brain uses about 0.5 GB when awake** (0.47 to 0.54 GB resident, peaks to about 0.65 GB; one very heavy chat bot peaked
  near 2 GB) [M]. A bot with a web front needs more [E].
- **The platform base is about 1.4 GB** with no brains awake [M]. The waker also keeps about 1.5 GB free as a reserve.
- **Each stack has a small always-on part** (a chat-API proxy): 15 to 25 MB of RAM, a little CPU, and some network even when
  the brain sleeps [M].
- **A model call carries about 40k prompt tokens and a few hundred output tokens.** 79 to 91 percent of the prompt is served
  from the provider's cache. Hidden reasoning is a large part of the output (roughly a quarter to three quarters) and it is
  billed as output [M].
- **A wake from cold takes tens of seconds.** It is sequential (start the agent, then connect the chat), so more cores do not
  shorten it much [M].
- **Estimated awake share by SME role** [E]: reception and support 35 to 50 percent (business hours only); sales and marketing
  8 to 15; administration 5 to 10; technical or IT 3 to 8; design and content 10 to 20; manager assistant 8 to 15. For six
  agents that is under one brain awake on average, so about 80 to 90 percent of agent time is asleep without a human, and
  65 to 80 percent with a human using them.

## 2. What limits a shared host

On a 12 GB, 4 vCPU host the limits come in this order [M]:

1. **The awake cap.** The waker allows a fixed number of awake brains (`max_awake`). With the cap at 4, this is the first
   limit that binds. RAM alone would allow about twice that, and raising the cap showed no measured downside.
2. **Disk.** Live data plus several backups per bot. It starts to limit somewhere between 60 and 100 stacks, and keeping 20
   percent free is part of the rule.
3. **Not RAM, not CPU, not the model.** Load average stayed low, and the number of brains awake at once almost never reached
   the cap. A brain budget of about 9 GB divided by 0.5 to 0.65 GB gives roughly 14 to 20 brains without web fronts, and
   about 9 with web fronts [E].

Peaks are correlated: a daily digest at a fixed hour, nightly scans, and everyone starting work at the same time. Companies
in the same time zone peak together. So size by the peak, not the average, and apply a haircut of about one third to any
count that assumes independent usage.

### Capacity per 12 GB host

These ranges already include the one-third haircut. They are estimates [E].

| What you host | Awake cap 4 | Awake cap 8 |
|---|---|---|
| Business task bots | 30 to 70 | 70 to 165 |
| Media bots | 17 to 28 | 40 to 65 |
| Personal web bots | 9 to 15 | 22 to 37 |
| Personal chat-heavy bots | 3 to 4 | 6 to 9 |
| SMEs of 6 agents, with a heavy human user | 1 to 2 | 3 to 6 |
| SMEs of 6 agents, with a light human user | 5 to 11 | 13 to 28 |

Rule of thumb: **plan one to two SMEs of six agents per 12 GB host at the peak.** The reason is that one SME brings three to
four brains awake at once, and the usable awake cap after the haircut is under three at cap 4.

The calculator's host count (section 4) is more conservative than the table, about 2.5 to 6 agents per active host once
standby hosts and the correlated peak are counted. If your own numbers say 12 to 18 agents per host, check that your peaks
really do not coincide.

## 3. More CPU or RAM does not make turns faster

A turn (one user message and the agent's answer) was timed on the heaviest chat bot, and the time was split by cause:

| Where the time goes | Share of turn wall time (heavy chat bot) |
|---|---|
| Model rounds | about 40 to 45 percent. Other bots spend 55 to 97 percent here. |
| Long terminal waits (sleeps, timeouts, builds) | about 30 percent |
| Overhead between calls | about 10 percent (cause not verified) |
| Context compaction | about 3 percent directly, more in the turns that contain it |
| Cold start | extra, outside the turn |

The host was mostly idle while this happened. The consequences:

| Resource | Verdict |
|---|---|
| More RAM | No gain. Free memory stayed far above the reserve and nothing was evicted. |
| More vCPU | Under one second. Throttling was rare. A wake takes about the same with one core or two. |
| Faster disk | Gains only on the first boot after a new image, which a prewarm step gives for free. |
| Moving the VM to a faster node | About ten seconds on cold wakes at best, with risk and downtime. Not worth it for latency. |
| Raising `max_awake` | Not needed for speed. The cap was hit in only a small share of samples. |

What does pay off is small software fixes, mostly in the waker and the skills:
- end a task's hold as soon as its run ends, instead of waiting for a fixed hold to expire;
- recognise every run state, so a stack is never put to sleep with a run half done;
- ask for several independent reads in one message;
- start long jobs in the background and end the turn instead of polling;
- set a speed floor and a per-call time limit when the router explores models;
- keep delegation capped (section 8).

Parallelism today: bots run in parallel as separate containers. Inside one bot, only read-only tools run together, and a
new message joins the running turn instead of starting another. Background processes are the parallelism that already
works. Delegating to child agents helps only for research with three or more independent branches. It multiplies token cost
and the chance of a rate-limit error, so it is not a general speed-up.

## 4. Using `ops/cost_calc.py`

The calculator uses only the Python standard library.

```
python3 -I ops/cost_calc.py                      # run with the defaults
python3 -I ops/cost_calc.py --template > my.json # print every parameter as JSON
python3 -I ops/cost_calc.py --params my.json     # change only the keys you list
```

The defaults for hosting, token prices and hourly rates are examples, not quotes. Put in your own region's values:

- `region.vps_per_gb_ram_month`, `vps_per_vcpu_month`, `storage_per_gb_month`, `egress_per_gb` (it is zero by default, so set
  it if your provider bills traffic: large media files and restoring backups from off-host storage can cost real money);
- `region.gpu_per_hour`, `electricity_per_kwh`, and `host_mode` (`vps` or `own`);
- `region.human_hourly` for each role: `sre`, `dev`, `qa`, `security`, `support`, `sales`, `product`. Use fully loaded cost,
  with employer charges. The example support rate is low, so check it;
- `model.classes`: three price classes per million tokens (`cheap`, `mid`, `premium`);
- `margins`: markup, payment fee (local payment methods can cost more than the example), and a minimum price.

The output has five parts:
1. monthly cost per bot type (infrastructure, tokens at three price classes, staffing at two incident rates);
2. SME packages of 3, 6 and 10 agents, with and without a human helping, at the current and the target incident rate;
3. hosts needed for 10, 50 and 200 agents, including standby hosts, and which limit binds;
4. staffing, in two views that overlap, so never add them (see section 5);
5. a sensitivity check on usage (0.6 times to 1.7 times the awake hours and tokens).

Reading the output:
- "Breakeven" excludes tokens, unless `include_tokens_in_price` is true. The package price is before taxes.
- The host count includes warm standby hosts once the fleet is large enough. It is higher than the marginal cost per bot
  in part 1, on purpose.
- With example region values, the infrastructure for one agent is a few currency units per month, and one 12 GB host costs
  about the same as a few hours of an operator's time. Infrastructure is not the cost that decides the price.

## 5. Pricing model

**People time dominates.** In the calculator, staffing is 83 to 99 percent of the cost of an agent. Infrastructure is almost
irrelevant. Usage changes the price per agent only slightly across a wide range (0.6 times to 1.7 times).

Show two prices side by side, because they answer different questions:

| Price | What it covers | Example output (illustrative) |
|---|---|---|
| **Marginal price per agent** | Infrastructure, plus incident and support hours only. | About 85 to 90 per agent per month at today's assumed incident rate; about 20 at the target rate. |
| **Price that covers the whole team** | A fixed team (operator, developers, QA, security, support, sales) shared over the agents. | About 850 per agent at 10 agents, 450 at 50, 310 at 200. |

How to read them:
- The marginal price is real only once the team is already paid for another way, or at a scale where the team is diluted.
- Up to about 50 agents the team-covering price rules. Even at 200 agents it stays more than three times the marginal price.
- The markup in the calculator sits on almost pure operator cost. It does not fund development, sales or product.
- Team size by scale, as estimates: about 1.5 to 2 FTE for 10 agents (a few clients), 3.5 to 5 for 50 agents, 11 to 15 for
  200 agents.

**The incident rate is the main lever.** Incidents per agent per week times hours per incident is what drives staffing. A
rate near 0.2 is a plausible start for an early system (range 0.1 to 0.4). The target after regression tests, early
detection and consented auto-repair is 0.03 or less. Two cautions:
- The rate does not scale linearly with agents. A bad release hits every agent at once and counts as one incident.
- At the early rate, a large fleet needs several full-time operators just for incidents. That is expensive, not impossible,
  but it is why the rate has to fall before the fleet grows past a few dozen agents.

**Keys: each person brings their own.** Tokens are paid by each person to their own provider with their own key, so they are
not in the price by default. If a client expects tokens included, price that explicitly. In the calculator's example
numbers, a heavy personal bot goes from about 10 (cheap class) to about 60 (mid) to about 230 (premium) per month, and an
SME package of six agents goes from about 17 to about 100 to about 380. Free tiers have rate and daily-token limits that a
heavy bot will probably exceed.

**Costs the calculator does not include, add them yourself:**
- taxes (sales tax or VAT, local business taxes, income tax) and withholdings. State whether your price is net or gross;
- payment fees higher than the example, plus chargebacks, late payment and currency exchange;
- employer charges, if you only entered salaries;
- off-host backup storage, restore traffic, and the off-site node of stage E4 (a small VPS, an estimate to quote locally);
- legal costs of a paid beta: terms of service, registration of personal-data files where the law requires it (see
  `DATA_LAW_AND_KEYS.md`), invoicing, and a security review before accepting third-party data.

Compare against per-seat chat plans from model vendors only with care: those plans include no dedicated agent, no memory
across sessions and no operation. Verify any competitor price on the provider's own page, because aggregator sites disagree.

## 6. SME guidance

| Question | Answer |
|---|---|
| How many agents to start | **3**: for example a manager or reception assistant, administration, and sales or marketing. |
| Maximum | **6**: add design and content, and a technical or IT agent. |
| Rule | One agent per role, and one named human responsible for each agent. |
| Moving from 3 to 6 | Only after the first three have stayed within their error budget for four weeks. |
| With no human helping | Only 2 or 3 agents make sense on their own: reception with escalation, IT driven by alerts, marketing in draft form with approval. |
| With a human helping | 4 to 6 agents. One person can supervise 2 to 4, so six agents need about two part-time humans. |
| Human in the loop | **Any effect outside the company goes through a human gate**: sending a message or email, publishing, paying, changing infrastructure. Known failure classes include announcing an action without doing it and inventing links, so an agent's claim that it did something is not evidence. |
| Warm mode | Only for reception during business hours. The others wake on demand (about 25 to 30 s) and the price should reflect the difference. |

Size a company by its peak of awake brains (three to four at once for six agents, about 2 to 2.5 GB), not by the average.

## 7. Staged resilience

Direction: harden the shared host first, then make a whole bot portable, then spread over hosts. Do not move bots between
hosts before E0 and E1.

True today:
- there is a daily backup per stack and a restore with a dry-run drill;
- there is a waker, GPU leasing, and remote power control for machines;
- the backups sit on the same storage that runs the VMs. This is the biggest concrete risk;
- there is no failover. Whole-bot export and import, warm standby, shared blob storage, a placement market and the swarm
  are designs only.

| Stage | What | Effort [E] | Needs | RPO target | RTO target |
|---|---|---|---|---|---|
| **E0** | Hardened shared host: encrypted off-host backup (a tool such as restic), keys kept out of the backup archives, an alert that does not depend on the monitored host, a limit on work in progress, reliable telemetry | 1 to 2 weeks | nothing | 24 h | hours to days, manual restore |
| **E1** | A whole bot is portable: a manifest per stack and tested `export` and `import`, proven on a guest | about 10 to 14 days | E0 | 24 h | 15 to 40 min (hours by hand today) |
| **E2** | Multi-host: scripted bootstrap of a host, deploy by image digest, edge routes kept as data | about 8 to 10 days | E1, and knowing where the edge runs | 24 h | 15 to 40 min per move |
| **E3** | Warm standby per company: a fresh VM kept in sync by pull, promotion with confirmation | 2 to 4 weeks | E1, E2, E0 backups | personal data 5 min; small files 15 min; large files and business data 24 h | personal 30 min; end to end 30 to 45 min; business data days |
| **E4** | Off-site node for datacenter loss: a small external VPS, and a tunnel or DNS switch driven by an application health check | 4 to 8 weeks | E3 | same as E3 | 30 to 45 min, to verify in a game day |
| **Swarm** | One-shot workers on other hosts, a queue on the task board, leases for GPU and CPU, results through blob storage | long | E1, E2, blob storage, idempotent tasks | per task | minutes (stateless workers) |

The effort figures come from earlier designs and carry an optimistic bias of about 50 percent. Run in series for one
person, E0 to E4 are about 16 to 30 weeks, which overlaps a paid beta. RPO and RTO for E3 and E4 are proposals, not
measurements. Only E4 covers the loss of the whole site.

Rules:
- **Promotion is the operator's decision** until there is real fencing (a smart plug or a BMC). Automatic promotion without
  fencing can create two writers.
- **One chat bot token cannot have two pollers.** The fence is to confirm the old VM is off, or to rotate the token.
- **The edge** (reverse proxy, DNS, TLS) must be documented and backed up. If it shares a host with the bots, one host
  failure takes the public route down too.
- **The first drill** must include "primary hung", "primary powered off" and "edge unreachable".
- A network that survives a whole-site loss is three things: encrypted data replicated off-site, an image that can be rebuilt
  from git by digest, and public routing that does not depend on one location.
- **Do not do yet:** a VM per client (only when a trigger exists, such as a paying or untrusted client), powering hosts off
  by schedule (the saving is small), active-active, or more RAM and CPU for the shared host.
- **Release criteria for a first usable version** should include an off-host backup and a tested restore, not only a restore
  of a local copy.

## 8. Harness priorities

The harness is the test and monitoring around the agents. In priority order:

1. **A quality regression set.** Logic self-tests are plentiful, but cases for agent quality are missing. Build about 25
   cases from real failure classes (no chat text), and run them as a gate before every image, on a guest stack, with a fake
   model first. Add a synthetic day. Effort small to medium.
2. **Reliable telemetry.** Count a turn once, ignore false turns caused by mid-turn steering, record errors, record the model
   actually used and the prompt tokens. Without this, no improvement can be measured. Effort medium.
3. **One application health check.** Process alive, router route present, key valid, and a write to the session database
   works. Expose it as `/health` for any balancer or failover. Effort small to medium.
4. **The router in front of every bot**, including business bots, so each has failover and an evaluation log. Effort small.
5. **Waker fixes.** Account for running tasks and pending delegations before sleeping a stack, and recognise the states
   "waiting for approval", "stopping" and "interrupted". Effort small.
6. **A per-stack capability manifest** inside the stack manifest of E1: tools, gateways, hosts, models, data class, and the
   requirements of a target host. Effort small.
7. **Delegation caps** before any swarm work: about 3 concurrent children, a 15 minute child timeout, and a limit on
   iterations. Effort small.
8. **A compaction policy and a burst alert.** In a small sample, quality dropped at the first compaction (around the tenth
   turn): the share of repeated tool calls jumped from under one percent to about a quarter, and a turn with a compaction
   took several times longer. Warn the person that a long chat should be restarted, check that a restart keeps memory and open
   jobs, and consider protecting the recent tool tail. Alert on compaction bursts, not on length alone. Effort medium.

## 9. RAG priorities

Today there is Hermes memory (a few thousand characters injected each turn), full-text search over past sessions, skills,
feeds, and a document extractor with embeddings off. There is no per-company knowledge base.

1. **RAG v1: SQLite FTS5 only, one index per company.** Effort medium.
   - A `docs` table (id, origin, hash, mtime, level, language, expiry) and a chunk table.
   - Ingestion through one narrow gateway (`kb add`, `ls`, `rm`, `search`) that reuses the document extractor and the content
     guard. The agent searches through the gateway and never opens the index.
   - An access level from L0 to L3, set at ingestion (L1 by default). A query filters by the bot's level and by the highest
     provider class the bot may use.
2. **Freshness.** A nightly re-hash by timer with no tokens, expiry dates, a date on every citation, and deletion that
   reaches chunks, vectors, caches and backups, with a receipt.
3. **Embeddings (v2), only after v1 works.** Choose with about 30 real questions from the company, not by benchmark.
   Local multilingual small models and a cloud embedding model on a free daily quota are both options. Cloud embeddings are
   for low-sensitivity data only. An SME with 500 to 5,000 pages is about 0.5 to 5 M tokens, indexed once.
4. **Rules.** The index belongs to the stack manifest and is rebuilt from the source if lost. Leave Hermes memory alone: one
   fact per entry.

## 10. What to measure from now on

To replace these estimates with data:
- incidents per week, with detection, fix and deploy times separate;
- items opened and closed per week;
- operator hours per incident;
- support contacts per agent per month;
- a series of awake hours per stack.

Then: weeks to reach a target = open items divided by items closed per week, plus a clean-run window. Staffing in FTE =
(incidents per week times hours per incident, plus support minutes) divided by about 30 to 35 useful hours per person. The
first formula only works if the backlog is actually shrinking.
