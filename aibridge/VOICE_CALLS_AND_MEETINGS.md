# Voice calls and meetings (design)

Status: **design only, nothing built or deployed.** Every number marked EST is an estimate. Nothing here was measured on our hardware.
Provider prices and terms come from public documentation. Read them again before relying on them.

## 1. Goal

- A person puts on a headset and talks to one bot at a time. Each bot covers one topic (a sector bot).
- Later, the same person sits in a meeting with two or three bots and talks to all of them. The bots answer in turn.
- VR comes later, through the sister OpenXR project. The call transport must not assume a browser.
- A pay-per-minute option is an idea, not a plan. It needs the cost cap of section 7 first.
- Natural speech is the quality bar. One commercial voice demo set that bar. It is **not connectable**: its terms train on user audio by
  default, which clashes with local-first. We copy the goal, not the product.
- We do not adopt a call platform. We take one method from the platforms we looked at: a fast voice model holds the conversation and
  asks the slow agent through one tool.

## 2. A 1:1 call with a sector bot

```
Browser or headset (WebRTC or WebSocket)  ->  call process (CPU only)
   VAD + end-of-turn detection (a small multilingual model that runs on CPU)
   STT on the GPU, through the gate
   Fast front model (small talk, barge-in)  --consult tool-->  the bot's Hermes
   TTS on the GPU (a per-bot voice), streamed sentence by sentence
```

Design rules:

- **Hermes is never in the speech path.** A Hermes turn takes about 10 s with no tools and much longer with tools or compaction (EST
  range 10 to 115 s, from earlier measurements under different conditions). The front model answers small talk alone.
- **Filler while Hermes works.** The front model says a short pre-recorded phrase and gives an ETA. Fillers are synthesized once on the
  GPU and stored as audio. Nothing is synthesized on the VM CPU.
- **One consult at a time per call.** A second request gets "busy, try again". There is a hard timeout.
- **Read-only tool policy for spoken requests.** "How are things in your area" is answered from memory and the bot's task board. A spoken
  request never writes or spends without a written confirmation. Prompts do not guarantee this. Hermes must expose a per-request tool
  restriction, or the call uses a separate read-only toolset or a narrow gateway command. This is **not verified yet**.
- **What the caller says never widens permissions.**
- **Own session per call.** What a call may write to memory is decided before building. The default is nothing.
- **Echo guard.** The bot's own voice must not feed back into the mic. Headsets are the default.
- **Credentials.** The browser gets only an ephemeral token. No provider key and no Hermes API key reaches the browser or the agent.
  The call process holds the keys it needs, and each key has one owner process (see `KEY_SECURITY.md`).
- **GPU through the gate.** A start step asks for STT and TTS leases for the length of the call, plus the idle tail, and wakes the bot's
  stack. If the gate refuses (busy, no VRAM, exclusive job), the person sees a clear message. Leases have a maximum duration.
- **Wake by API.** Stacks wake today only from messaging, web navigation and tasks. A call needs a wake API. It is new work.

Already available: STT, a streaming TTS endpoint, a voice proxy per stack, the gate, the waker, the Hermes API server, one SOUL per bot.
Missing: realtime transport, VAD, end-of-turn detection, barge-in, streaming STT, the front model with its consult tool, and a client
that plays streamed TTS (today the proxy reads the whole body).

## 3. The meeting

```
One mic input -> one STT -> MODERATOR
   Shared transcript with a speaker label per line
   The moderator picks the next speaker. A named bot answers. Otherwise the most relevant bot answers. Others hear the text and stay silent.
   Each bot: its own fast front model (role + short memory) -> consult its Hermes only when needed, one at a time
   One TTS, one voice per bot, one speaker at a time
   Barge-in: if a human speaks, queued audio is cancelled
   At the end: minutes (decisions, open items per bot) -> task board
```

| Piece | Design |
|---|---|
| Room | One process on the app VM. At most 3 bots plus the humans. Transport, VAD and rules only. |
| Moderator | A small model with fixed rules and no vote. It adds no facts of its own. Human first. Never two bots in a row without a human turn. After a long silence it asks or summarizes. It adds about 0.3 to 0.8 s per turn (EST). |
| Turns | Strictly alternating. The TTS serializes synthesis, which matches "one speaker at a time". |
| Front model per bot | Each bot answers fast by itself, from its role and a short memory summary. It consults Hermes only for slow work, with a filler. Without this, three bots consulting in series would take 30 to 60 s or more per round (EST). |
| One voice per bot | A reference clip per bot, stored with the TTS. Any cloned voice needs the consent of the person whose voice it is. Use your own voice or synthetic voices. Never a third party's. Using one person's clone for several bots confuses listeners, so give each bot a distinct synthetic voice. |
| Memory | Each bot keeps its own stack and memory. A meeting writes only what the bot's area may store. A per-area rule says what a bot may tell the others. It is defined before the voice phase. |
| Minutes | A model summarizes the transcript and posts tasks to the board, with an owner per bot. Retention of transcript and minutes is decided first. |
| Cost cap | A cap per meeting (minutes and consults), with a warning at 80%. |
| Other people | If anyone else speaks into the mic or joins, they are told and must consent. Their voice is biometric data. By default, meetings have the operator only. |
| Awake limits | The waker allows a fixed number of awake stacks. A meeting of three bots can use all of them and block other people. Wake one bot at a time. Business bots sleep after a short idle time, so a silent bot needs a keep-alive that does not count as human activity. |

Text first: a round table on the web where people type or speak and the bots answer in order. Voice comes after.

## 4. Local and cloud, honestly

"Local" here means local STT and TTS. A small LLM does not fit next to them on an 8 GB card, so the front model is a cloud text model.
The person's transcript leaves home through that model. Treat it as a privacy decision (section 8).

| | STT/TTS local, front LLM in the cloud | Cloud realtime model (opt-in) |
|---|---|---|
| Time to first audio, 1:1 | **4 to 6 s (EST, summed)** with a streaming Chatterbox-class TTS. 2 to 3 s only if a faster TTS meets the bar. | 0.5 to 1.0 s (provider claims, EST) |
| Meeting | Slower than 1:1: add the moderator, and consults take longer | 1.2 to 2.5 s (EST, cascade) |
| Cost per minute | Electricity is far below one US cent per minute at 130 to 250 W (EST, depends on tariff). The real cost is the lease idle tail and any rented GPU. | Published per-minute rate plus the tokens of Hermes consults |
| Cold start | Waking a sleeping GPU and stack can take 80 to 145 s for the first reply. A stack start alone is about 25 s p50. These are different things. Avoid it with a warm window. | Only the bot's stack |
| Russian | Covered by the TTS, but must be heard live | No documented data for the realtime model: test it |

The time-to-first-audio budget for the local path (all EST):

| Stage | EST |
|---|---|
| End of turn | 0.3 to 0.5 s |
| STT (whole clip) | about 1.1 s |
| First token of the fast model | 0.8 to 1.9 s |
| TTS to first audio (streaming, 8 GB card) | 2.0 to 2.9 s, with stalls of 0 to 1.3 s |
| **Sum, 1:1** | **4 to 6 s** |

Reaching 2 to 3 s needs one of two things:

- A faster TTS. A candidate to test by ear and by latency was rejected earlier (fp16 gave NaN, fp32 was slower than realtime on an old
  Pascal card). The current card is a newer architecture, so repeating the test is valid.
- A cloud realtime model with the person's **own paid key**. Never a free tier: free tiers train on inputs and allow human review.
  Provider terms for live-voice models are not verified here. Read them before use. Some providers cut audio sessions at about 15 minutes
  without session management and may bill audio tokens again per turn (secondary sources).

Where the TTS comes close to the natural-speech bar, a local voice is less natural than the best cloud realtime voices. Say so to users.

## 5. Phases

| Phase | What | Done when |
|---|---|---|
| 0, baseline | STT+TTS round trip on the current host, a Hermes turn with no tools, a cold start of a sector bot | A table of measured versus estimated numbers, per stage |
| 1, minimal demo | One sector bot in a test profile with sample data. Call process, STT and TTS through the gate, a fast model with the consult tool, filler while consulting, one consult at a time | A per-turn timeline is visible (end of turn, STT, first token, first TTS packet). The filler plays within 1.5 s (EST) while Hermes works. The bot never invents an answer instead of consulting. The first-audio target is set from phase 0, not from this document |
| 2, calls per sector | A call button per bot. Start step with gate and waker. Role and voice per bot. Read-only status of the area | Each bot reports its area from real board data. Nothing is written without confirmation. A cold start shows a visible state |
| 3a, text meeting | Moderator, shared transcript, two bots plus the human, minutes to the board | 10 of 10 test meetings end with correct minutes and no two bots speaking at once |
| 3b, voice meeting | One voice per bot, barge-in that cancels the queue, cost cap | A 15-minute meeting with three bots finishes without drops. The turn latency target comes from phase 0 |

Fixed recorded tests for each phase: informal Spanish address, Russian, English, and a language switch in the middle of a call. All tests
run in a test profile, not in a real person's profile.

## 6. Network and operations

- WebSocket goes through the edge proxy. WebRTC also needs UDP and a TURN relay.
- The call process needs the app VM's CPU and RAM, which are already tight. Estimate the load of VAD and end-of-turn detection first.
- A speech fallback to a cloud STT is off by default. Call audio and third-party audio never go to a cloud STT without opt-in.
- A cloud 429 cools down a provider for every stack. Keep consult concurrency at 1 and wake bots one at a time.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Local first audio is 4 to 6 s | Measure first. Stream by sentence. Test another TTS. Offer the opt-in cloud path |
| Hermes is slow (10 s to over a minute) | Filler, ETA, hard timeout. The front never waits for Hermes |
| Cold GPU and stack | Start step with a visible state, warm windows by schedule |
| The small model decides badly when to consult | Test "consult on substance" against "always consult" in each language. Only a test closes this |
| Russian in the TTS, end-of-turn model and small models has no data | Listen and measure with mixed speech before promising it |
| A bot says too much (one area's data in a shared meeting) | A per-area rule, read-only, and meeting talk never widens permissions |
| Meeting cost multiplies (each bot is an LLM plus a TTS) | At most 3 bots, only the speaker consults, a cap per meeting |
| Awake-stack limit blocks other people | Wake one at a time, schedule meetings off-peak, keep-alive for silent bots |
| The TTS engine is unmaintained and adds a watermark | Hide it behind one interface. Keep a second engine in the queue |
| Biometric voice data and cloned voices | Consent per clip, local by default, no recordings unless decided |
| Providers change terms | Keep the engine swappable behind the same consult tool, with no change to Hermes |
| This design comes from documentation, not tests | Phases 0 and 1 replace estimates with measurements |

## 8. Privacy and keys

- A person's chat (privacy class C) never reaches a cloud front model without that person's opt-in. Class C stays on local models only.
- Cloud use is opt-in, with the person's own paid key. The operator provides no keys.
- Transcripts and minutes need a retention decision. Recordings are biometric data under the Argentine data-protection law. Decide
  whether they are stored at all. The default is no.
- A cloud TTS for several bot voices is another vendor that receives the meeting text. Name it and read its terms first.

## 9. Benchmark: the "doubles" debate

A fixed benchmark that measures the meeting system, not the people. It is a doubles match: two humans and two AIs, two teams, one human
and one AI each. A draw is a normal result. If one side wins, it should be because of its arguments, not because its court was different.

### 9.1 The match

- A fixed 15-minute match, repeated unchanged on each version of the system (text, local voice, cloud voice).
- A fictitious company with a job queue that falls behind on one 8 GB GPU. The question: **buy a bigger GPU now, or optimize and rent
  by the hour**. The final decision does not score. The process and the quality of the grounds score.
- Budget in abstract units, so numbers do not cross currencies. A fixed fictitious exchange rate is set if a question needs one.
- The moderator is a system role with no vote and no opinion. It gives turns, keeps time, asks six fixed provocations, and closes with a
  spoken summary.
- Scripted events make runs comparable: two language switches (one human asks in the other human's language), two forced interruptions
  (the target AI is made to be speaking), a cross-question where each AI asks for the source of a rival's number, and a closing round.

### 9.2 Evidence folders

- Each AI may say a number only if it comes from its folder, the shared scenario data, a rival quote, or a logged tool call
  (`evidence(id)` and `calculate(expression)`). Everything else counts as invented.
- The AIs read a derived, clean evidence file only, never raw reports.
- Each datum is typed: measured, estimate, or unverified. Saying "I do not have that figure" earns points. Citing an estimate as firm
  loses points.
- The folders hold deliberate traps: two sources that disagree, unverified figures, a placeholder price, and a missing figure that
  neither side has. The checker detects them and the judge scores them.

### 9.3 Symmetry and fairness rules

**Same system on both sides.**
- Both AIs use the same model, version, base prompt (only the stance changes), voice pipeline, turn time limit and number of Hermes
  consults.
- **Balanced folders.** The same count of private data per side, the same mix of measured, estimate and unverified, and the same count
  of traps. Balance is checked before the first match. If one side has more, add to the other or cut to the smaller and move the rest to
  shared data.

**Mirror matches.**
- Each match is played twice with sides swapped: the human who argued to buy argues to wait, and the AIs swap teams. A **set** is the
  pair.
- The opener alternates, like serving in tennis. In the second half the other team opens.
- If one side (stance, human or AI) wins both halves of mirrors systematically across many sets, look for system or judge bias before
  reading it as merit.

**Draws are normal.**
- Score by blocks (opening, rebuttals, closing). A draw is possible in each block and in the match.
- Track system versions over time with a rating that handles draws (Glicko-style), kept per **system version**, not per person. The
  question is "does this version keep the court level?".
- Health indicator: balanced sets show a high draw rate. If it drops and one side starts winning with no change in arguments, something
  in the system has tilted.

**Parity is measured, and a match can be invalid.**

| Layer | What is recorded, per team and per match |
|---|---|
| Mechanical and electronic | Latency to first audio (p50 and p90), audio cuts, lost packets, STT word error rate, consult time, cold start, provider retries |
| Biological | Mic quality and signal-to-noise, language and accent with their error rate, total speaking time, interruptions received, fatigue (same time slot and same duration) |

- Invalid-match threshold (EST, calibrated in the text version): if teams differ by more than 20% in p50 latency, by 2x in audio cuts, or
  by 10 points of word error rate, the match is marked **invalid** and repeated. A glitch is never read as merit.
- System failures are counted apart from the result and go to the board as bugs.

**Blind judge.**
- The AI judge reads the minutes blind: neutral labels (Team 1 and Team 2), no voices, no names, everything translated to one language,
  blocks in shuffled order.
- The judge comes from a different model family than the fronts.
- Fixed bias tests before use: position (does it reward the last speaker), length (does it reward more words) and language (the same
  minutes in two languages must score the same). Two passes per transcript with reversed order. If they disagree, discard.
- Three passes and the median. Maximum spread between passes is 1 point (EST). Calibrate on two transcripts scored by hand.
- Both humans also score. The judge is compared with the humans, and each human with themself across the mirror.
- The automatic checker rules on numbers. The judge scores only what the checker cannot see.

### 9.4 Metrics

| Metric | Definition |
|---|---|
| Latency to first audio | End of the trigger (human speech, moderator decision or the previous AI's audio) to first audible audio. Turns with a Hermes consult are reported apart |
| Filler latency | Time to the filler phrase when a consult starts (target 1.5 s, EST) |
| AI over AI overlap | Time with two AIs audible together. Target 0 |
| Barge-in handled | Share of interruptions where the AI stops within 500 ms (EST) |
| Verified claims | Numbers that match a folder, the scenario, a rival quote, or a tool result, out of all numbers. A fifth class, "unclassifiable", keeps shares adding up |
| Invented claims | Numbers with no support. Target 5% or less |
| Labelled estimates | Share of estimate or unverified figures cited with their label (EST: 80% or more) |
| Language switches followed | How many of two scripted switches are answered in the new language in one turn |
| Complete minutes | Decision, grounds with two or more evidence IDs, tasks with owner and date, disagreements, language, summary |
| Turn balance | Speaking-time split between teams, measured in the free rebuttal block only (the script fixes the other blocks) |
| Moderator violations | Turns outside the rules. Target 0 |
| Cost of a run | Tokens and lease minutes |

Rubric, 0 to 5, scored by the judge on the transcript:

| Criterion | What a 5 looks like |
|---|---|
| Grounding | Every number has an ID or a tool call. Nothing invented |
| Rebuttal | Answers the latest specific objection |
| Honesty | Labels estimates and unverified data, says "I do not have it", catches the traps |
| Clarity | One point per turn, within the time the script gives |
| Coherence | Holds the role and complements its human |
| Contribution to the close | A proposal with a number, a date and an owner |

Humans score both AIs and the room: intelligibility, turn naturalness, trust in the data, usefulness of their AI partner, handling of
interruptions, language following and minutes fidelity. Intelligibility and language following do not apply to the text version. With
two humans and three runs, human scores are indicative, not statistical.

### 9.5 Versions

The match is identical in every version. Only the medium changes. If a model changes between runs, it is a new version, not a repeat.

| Version | Medium | Compares |
|---|---|---|
| Text | On-screen round table, people type | Grounding, turns, minutes, judge, moderator |
| Local voice | Local STT and TTS through the gate, front models and moderator in a cloud text model. Label every result "STT/TTS local, LLM in the cloud" | Per-stage latency, barge-in, language, cold start |
| Cloud voice (optional) | A cascade, or one session per AI, with the person's own paid key | Latency against local voice, naturalness, cost |

Three runs per version and per role assignment. Report median and range. Targets are estimates until the first real run replaces them
with measured values. If a version misses its target, record it anyway and go back to the stage table to find which stage failed.

During a local-voice run, the GPU holds STT and TTS and cannot run other heavy jobs. That is a real cost of a single card, and it is
part of the debate.

### 9.6 What the benchmark needs

- The evidence folder as data, and a derived clean file for the AIs.
- A checker that extracts numbers with units, compares them with a 5% tolerance, and classifies each claim.
- The `evidence` and `calculate` tools with a log.
- The moderator, two front models, a labelled transcript, a per-turn timing log (one JSON line per turn), and a minutes generator with a
  fixed schema.
- A round-table screen for two humans (a command line is enough at first).
- A judge harness: blind transcript, random order, three passes, median, spread.
- An automatic report that compares versions.
- For voice: realtime transport with two channels, VAD and end-of-turn per channel, streaming STT, streaming TTS with three voices,
  barge-in with queue cancel, the start step with gate leases, keep-alive for sleeping stacks, and a cost cap.

### 9.7 Risks to the benchmark

| Risk | What it would measure instead | Avoidance |
|---|---|---|
| Judge bias (own model family, length, first speaker, language) | The judge's taste | Different family, blind labels, shuffled order, three passes, length-normalized scores, hand calibration |
| Judge and checker disagree | Evaluator noise | The checker rules on numbers. Human review of a sample |
| Cold start | The wake-up, not the meeting | Wake everything first. Record readiness apart. Run one warm-up that does not count |
| Sleeping stacks | A silent bot that costs seconds to speak | Keep-alive. Count how many times one slept |
| Mic noise, echo, speakers instead of headsets | STT errors | Headsets required. Read 20 reference phrases before each session. Exclude low-confidence turns |
| Humans play differently each time | The people, not the system | Fixed script, swapped roles, median and range |
| Uneven folders | Whoever has more data wins | Count and balance before the first match |
| Provider rate limit | Other load on the run | Run off-peak. Note any 429 and repeat that run |
| Voices or data of real people | A real risk in a game | Synthetic voices, or the operator's own with consent. Fictitious data only. Generic bot names |
| Changing more than one thing between versions | Meaningless comparisons | Change only the medium |
| Estimated targets | False confidence | Mark them EST. Replace them after the first run |

## 10. Decisions needed from the operator

1. Scope first: one sector bot before the meeting.
2. Local only, or an opt-in cloud realtime path per person, with the person's own paid key.
3. Which sector bots go first and what each one reports.
4. Meeting first by text or by voice.
5. What each bot may store from a meeting, and the retention of transcripts and minutes.
6. Whether recordings are stored at all.
7. The cost cap per meeting, and the maximum lease duration.
8. Approval of a stack wake API.
9. The network path for calls (WebSocket or WebRTC with TURN).
10. A second human for the benchmark, who accepts that only text is stored.
