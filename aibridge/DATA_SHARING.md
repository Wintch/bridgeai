---
title: Data sharing: what each person lets us look at, testers, and collection gated at the source
scope: the sharing levels, the testing-stage policy, conversations and desktop/game sessions, and choosing the level without the bot (API and MCP)
when_to_use: any tool that reads a person's conversations, logs, recordings or metrics; any new collector; adding a person or a place
related: [opinion.py, ops/chat_review.py, ops/stack_usage.sh, manual/MANUAL.es.md (section 5), DATA_LAW_AND_KEYS.md, ../gpu-host/places/PLACES.md, site: /testers/]
---
# Data sharing

## 1. The rule

**Collection is gated at the source.** A collector checks the person's level before it reads or records anything. It never reads first
and filters afterwards. A person who does not share must cost us nothing to leave out. Their data is never gathered, so it never has to be
deleted, masked or kept apart.

## 2. Who is who

| Kind | Who | What may be looked at |
|---|---|---|
| Operator | The operator's own stacks and places | Everything, read by the operator (`chat_review.py --own`) |
| Tester | People in the testing stage who agreed with the operator | Section 3, from the day they were set up, unless they chose `none` |
| Everyone else | Anyone else | Their level (section 4); `usage` when they never chose |

The list of testers with their start date, and which stacks and places belong to the operator, is ops data. It is kept in
`ops/testers.json` on the Docker host, a git-ignored file like `ops/testers.json.example`. It never goes into the repository.

## 3. Testing-stage policy

Published for the people in the bot manual (section 5, es/ru/en) and on the site (`/testers/`):

- **Conversations.** An AI reviews them to find faults and improve the assistant.
- **Desktop and game sessions (places).** A session may be recorded for an AI to analyse. Frames per second, drops, stutters, latency,
  and GPU and memory use are measured, because they are essential to improve the product.
- **Which AI.** Any of the major vendors: Anthropic (Claude), OpenAI (ChatGPT), Google (Gemini) or NVIDIA.
- **What is not done.** What the AI reads or sees is not kept, copied, sold or handed over. Only anonymous conclusions about use come
  out (for example "Russian voice notes are sometimes transcribed wrong", "this game drops to 40 FPS while a map loads"), together with
  the changes that follow from them.
- **Two different things.** Answering a message goes to the model whose turn it is: the home machine, then the cloud services in order,
  or a model the person chose (`/model`, the providers page). The review for improvements is separate and changes neither route.
- **Opting out.** `/feedback data none` leaves the person out of every review and recording from then on.
- **Revisited before production.** The policy is explained to people again and adjusted before the service opens to more people.

How the tools apply it:

- `chat_review.py` reads a tester's text only from their start date, only on this machine (never copied into the repo, notes or
  messages), and its output for the operator is conclusions without quotes. Working files sit in a private scratch folder and are
  deleted after the review.
- `none` always wins over tester status.

## 4. The levels

Stored per stack in `/workdir/.compartir.json` as `{"level": "nada"|"uso"|"todo", "ts": ...}`. No file means `uso`. They are set with
`/feedback data none|usage|all` in the bot (`opinion.py`; the stored values never change):

- `none` (`nada`): nothing is looked at, not even counts. Collectors skip the person entirely.
- `usage` (`uso`): the shape only (tools used, counts, errors, times, which model answered), never text, files, images or recordings.
- `all` (`todo`): the conversation may be read to find what failed, only to improve the assistant.

## 5. Choosing the level without the bot (to build)

**The gap.** Today the level can only be set from the bot. A person who uses only a desktop or game place (through the door or
Moonlight, with no bot of their own) cannot choose it. For them, recording and metrics would have no level to check.

**Design.** One record per person, one function to read it, and three ways to write it:

1. **One record per person, not per stack.** A person can have several stacks and places. The record says the level and when it was
   set. Today's per-stack `.compartir.json` stays readable, and the person's record wins once it exists.
2. **One reading function for every collector.** `sharing_level(person)` returns `none|usage|all` and whether they are a tester and
   since when. The chat review, `stack_usage.sh`, the session recorder and the game metrics all use it. An unknown person reads as
   `none`: when in doubt, collect nothing.
3. **Three ways to write the level:**
   - **The bot**, as today (`/feedback data ...`).
   - **The door.** It gets a "Mis datos / My data / Мои данные" panel with the three levels and the tester text, behind the person's
     own login. The door calls the gate (`GET/POST /me/sharing`, authenticated with the person's own place token).
   - **An MCP server** (`sharing`), with tools `get_sharing_level` and `set_sharing_level`, scoped by the token to that one person. A
     client app, or a bot on another front, can show and change the level without knowing where it is stored. Every change is
     logged with its time and from where it came (bot, door, mcp).
4. **Places check it before recording.** The session recorder and the FPS/drops sampler run only when the level allows it, checked when
   a session starts and again every few minutes (a change takes effect without a restart). Until the person's record exists, a place
   with no bot is treated as `none`, even for a tester.

**Open decisions (operator):**
- Where the person record lives (gate host, Docker host, or both kept in sync).
- How long a recording may wait for its analysis before it is deleted.
- Whether the door shows the panel to everybody or only to testers first.

## 6. Finer choices (design, from the operator 2026-11-26)

The three levels are a start. A person may ask for something in between, and that is valid. The record of section 5 should hold
a choice per kind of data, per kind of viewer and per purpose. The three levels stay as presets.

| Axis | Values |
|---|---|
| Kind of data | conversation text, voice notes, files and images, desktop/game screen recordings, session metrics (FPS, drops, latency, GPU/RAM) |
| Who may look | nobody, an AI only, a human only, both |
| What for | find and fix faults (the default), or also train or tune models (never without an explicit yes) |

Examples a person may ask for:
- "Metrics yes, no screen recordings."
- "Only an AI may read my conversations, no human."
- "Only the operator, no AI."

Rules that follow:

- **Human only.** What only a human may see is never handed to an AI. A human who saw it cannot paste it into an AI tool, so it can
  never become training data.
- **AI only.** What only an AI may see never reaches a human. The operator gets the AI's conclusion, never the material itself.
- **Disturbing material.** The operator chooses how much detail they see. An AI that meets graphic material (blood in a game,
  violence, anything disturbing) identifies it and confirms what it is in neutral words, without passing the material on. The operator
  can say "never show me the detail", and is then not exposed to it needlessly. The AI's notes say what was found and where, not
  what it looked like.
- **Training is its own yes.** Testers agreed to reviews that improve the product (section 3), not to training models on their data.
  Training would need a separate, explicit choice per kind of data.
- **Same source gate.** Every collector reads the person's choice for that kind of data and viewer before it collects (section 1).
  A screen recorder checks "screen recordings"; the FPS sampler checks "session metrics".

## 7. Status

- **Built:** the levels, the bot command, `chat_review.py` / `stack_usage.sh` honouring them, the manual section and the site page
  (2026-11-26).
- **To build, in order:**
  1. The tester registry read by `chat_review.py`.
  2. `sharing_level(person)`.
  3. The gate endpoint and the door panel.
  4. The `sharing` MCP server.
  5. Finer choices per kind of data, viewer and purpose (section 6), with the three levels as presets.
  6. Recording and metrics in places, gated by the level.
