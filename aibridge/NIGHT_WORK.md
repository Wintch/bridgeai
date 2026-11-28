---
title: Night work, a background agent per person, and the person's alarm
scope: design (status per part below); how the slow, tedious work moves out of the person's live turns
related: [jobpush.py, ops/wake/waker.py, workers/worker.py, SKILL_job_search.md, SKILL_long_tasks.md, MULTI_BOT_TASKS.md, KNOWLEDGE_GAPS.md]
---
# Night work, a background agent per person, and the person's alarm

## Why

Measured on one person's stack over 14 days: 196 minutes of waiting, of which the model's own time between tool calls was most of it
(each extra tool call is one model round trip, 6 to 30 s with a large cloud model). Tool time was a quarter. The nightly job scan ran
in about 2 minutes and found 0 or 1 new offer per night, while the work the person actually did (open calls checked by hand, one page
and one edit at a time) happened live, at night, with them waiting.

Principle: compute is cheap and almost nothing of it leaves for the internet; the person's time is not. Whatever can be computed while
they are away is computed then, never in their turn. It must never wake their stack, and it must never do anything that could get an
account banned on a site (scraping bursts): it burns compute, not goodwill.

## Two agents per person

| | Front | Background |
|---|---|---|
| Where | the Docker host (today's stack) | the always-on VM that already holds the person's data |
| Does | talks with the person | the tedious part: evaluations, checks of sources, summaries, drafts |
| Model | the strong one | one of the person's own, cheaper or slower models |
| When | when the person writes | in a queue, while the person is away, before their next use |
| Keys | the person's own | the person's own (see "Keys") |

How they talk: through the person's shared space, not live. The front queues work in the person's folder (the work ledger,
`trabajos plan`); the background takes it, writes the result and a pending summary; the front delivers that summary when the person
next writes (the same path the night job summary uses today: `jobpush.py --pending`, the router on the web chat, the waker hook on
Telegram). Neither needs the other awake. Cron work may wake only the background side, never the front.

Other channels stay for other cases: the Gitea task board (MULTI_BOT_TASKS.md) between different bots or people, the stack's own
`/v1/runs` for a direct call to an awake stack, the event broker (design) for heavy work spread over machines. Hermes's A2A plugin is
synchronous (both awake) and its Kanban is single-host, so neither fits here.

## Keys

- The background agent is one container per person on the VM, the same image and the same keys server as the front: the agent never
  sees the key, and one person's key is never readable by another person's process (a single shared worker user would break that).
- The copy of the key on the VM is backed up encrypted (DATA_LAW_AND_KEYS.md), never as a plain file.
- A cap per night and per person (requests and tokens, the router's request cap, the provider's own spend limit where it has one):
  a night job that loops must not spend the person's daily quota.

## Phases (job search first)

1. **Night evaluation** of the new offers against the CV, after the night scan, with the evaluator the job-search system already ships
   (`openai-eval.mjs` takes an OpenAI-compatible base URL and model), the person's key and model, capped; the scores go into the
   summary, best first. Status: the scan, the shared space and the delivery exist; the key placement and this step do not.
2. **The person's own sources**: sites they check by hand are listed (by their agent, when they ask or when it sees the repetition) in
   `data/manual-sources.md` and checked at night without tokens: news and closing dates.
3. **Self-improving**: at night the background agent looks for new places to apply (boards, open calls, companies starting to hire in
   the field) and proposes them in the summary; with the person's yes they join their sources. Once a week it reads the upstream
   job-search project and our fork for new releases and NOTES what would help; adopting anything is the operator's decision.
4. **The full background agent**: drafts (tailored CV, cover letter) for the 2-3 best offers, ready in the morning.

## The person's alarm (idea)

A person may tell their bot when they will next use it ("tomorrow at 12"). Then the night knows the deadline: what must be ready by
then, which machine to wake and when, how much work fits before it, and a stack can be warmed a few minutes ahead (no boot wait on the
first message). Without an alarm, the person's measured pattern decides (their usual hours from telemetry).

## Maintenance is not spare time

Heavy, delicate maintenance (the btrfs dedupe of the desktop places on the GPU host) runs with the host to itself: it refuses to start
and stops within 2 s while any container runs, and it holds a host-wide maintenance lock that the daily snapshot waits for. A
maintenance window is never used to squeeze in a build or a job; people's work always wins and stops the maintenance.
