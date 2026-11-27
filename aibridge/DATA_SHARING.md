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

The three levels are a start. A person may ask for something in between, and that is valid. The choice can be made for one bot or
for everything of theirs (all their bots and places). The three levels stay as presets.

### 6.1 Local or third-party processing: where the data goes

What matters is where the data goes, not whether a human or an AI looks at it.

- **Local processing.** Our own machines (the Docker host, the GPU hosts) and what runs on them: the operator, scripts, and an AI
  that runs there. Nothing leaves. A local AI is a tool in the operator's hands, like their own eyes or their own script.
- **Third-party processing.** Anything that sends the material to an outside company: a cloud AI (Anthropic, OpenAI, Google, NVIDIA,
  any API), a cloud storage, a cloud transcription service. That is handing it to a third party, so it needs the person's choice that
  allows third-party processing for that kind of data.
- **Once data leaves the building, we cannot answer for it.** What a third party does with it is between that company and its own
  terms. That is why sending anything out needs the person's yes, and why the person is told so plainly.
- **Answering is a separate purpose.** To answer, the bot already sends messages to the provider whose turn it is, and voice notes to
  a transcription service (section 3, the providers page). That is the service the person uses, governed by their provider choices.
  The choices on this page govern **reviewing to improve the product**.
- Whether a human or an AI looks only matters for the operator's own comfort (section 6.4, disturbing material).

### 6.2 What is measured always, and what is optional

- **Essential technical data, nothing more.** This is what every place's session measures when the person allows `usage`:
  - when a game starts and stops;
  - frames per second, drops, latency and refresh rate;
  - running out of memory or disk space.

  No screen content, no text, no names of files.
- **Optional diagnosis**, only when the person turns it on. For example, looking for a visual glitch in a frame (Quake III showed a
  black full screen on the virtual display), a short screen recording around a fault, or reading a conversation to see what failed.
  For each kind, the person chooses where it may be processed: nowhere, only locally, or also by a third party.
- **"Full" (`all`) means diagnosis.** It allows the optional kinds above, to find and fix faults. It is not a licence for anything else.

### 6.3 The axes

| Axis | Values |
|---|---|
| Scope | one bot or place, or everything of the person's |
| Kind of data | essential technical data, conversation text, voice notes, files and images, screen frames and recordings |
| Where it may be processed | nowhere, local only (our machines: the operator, scripts, a local AI), local and third-party |
| What for | find and fix faults (the default), or also train or tune models (never without an explicit yes) |

Examples a person may ask for:
- "Metrics yes, no screen recordings."
- "Reviews of my conversations only on your machines, never sent to an outside AI."
- "Screen frames may go to a cloud AI to find a glitch, nothing else."

### 6.4 Rules that follow

- **Local only.** What may only be processed locally never goes to a third party, by any route: nobody who saw it pastes it into a
  cloud AI tool, an issue, a chat or a message. So it never becomes anyone's training data.
- **Conclusions, not material.** What a third party processed comes back to the operator as conclusions, never as a copy of the
  material.
- **Disturbing material.** The operator chooses how much detail they see. An AI that meets graphic material (blood in a game,
  violence, anything disturbing) identifies it and confirms what it is in neutral words, without passing the material on. The operator
  can say "never show me the detail", and is then not exposed to it needlessly. The AI's notes say what was found and where, not what
  it looked like.
- **Training is its own yes.** Testers agreed to reviews that improve the product (section 3), not to training models on their data.
  Training would need a separate, explicit choice per kind of data.
- **Same source gate.** Every collector reads the person's choice for that kind of data and destination before it collects (section 1).
  A screen recorder checks "screen frames and recordings"; the FPS sampler checks "essential technical data".

### 6.5 What no permission allows

- **The law comes first.** Some things cannot be done even with every permission the person gave, such as anything Ley 25.326 forbids
  or anything outside the stated purpose. A permission never stretches past that.
- **Nothing personal is ever passed on.** No personal data, whether a conversation, a recording, a file or what anyone saw, goes to
  any other party by either route (human or AI), except by a court order. Only anonymous conclusions about use leave.

## 7. Open questions and problems (2026-11-26)

1. **Answering already sends data out.** The bot's model, voice transcription when the home GPU sleeps (Groq), the model that
   describes photos, web search queries, and Telegram itself all carry a person's material out of the building. They are the
   service, not reviews, but the person should see them in one place: a per-person list of where their messages go today.
2. **Reviews by Claude Code are third-party processing.** Reading a tester's conversation in a session of the operator's coding
   assistant sends it to Anthropic. For a person who allows only local processing, the review needs a local model. The home GPU's
   LLM is stopped today, so for them only scripts (counters, detectors) can review.
3. **Few people, so "anonymous" is weak.** With a handful of testers, a conclusion like "Russian voice notes are misheard" points to
   one or two people. Conclusions that leave the building should be written so that they do not single anyone out (no stack names,
   no languages when that identifies), or stay local.
4. **Where backups, logs and alerts go.** Backups, Zabbix and the ops bot's alerts: does any of them leave the building, and with
   what in them? The ops bot talks over Telegram (a third party): an alert must carry counts and names of hosts, never a person's
   content.
5. **How long local material is kept.** Screen recordings and diagnostic dumps need a deadline after which they are deleted, even
   when the review never happened.
6. **Court orders.** Who receives one, who checks it, and what is handed over (and only that) need writing down before it happens.
7. **Who is a tester.** The registry (section 2) needs each person's start date and their stacks and places. A person with several
   stacks counts once.

## 8. Status

- **Built:** the levels, the bot command, `chat_review.py` / `stack_usage.sh` honouring them, the manual section and the site page
  (2026-11-26).
- **To build, in order:**
  1. The tester registry read by `chat_review.py`.
  2. `sharing_level(person)`.
  3. The gate endpoint and the door panel.
  4. The `sharing` MCP server.
  5. Finer choices per scope, kind of data, destination (local or third party) and purpose (section 6), with the three levels as presets.
  6. Recording and metrics in places, gated by the level.
