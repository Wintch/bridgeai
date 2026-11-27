---
title: Knowledge gaps and suggested topics: offer to connect what is missing, and learn which packs to build next
scope: what the bot says when it lacks knowledge or a source for a request, the record it leaves, and how the operator reads them across stacks
when_to_use: adding a pack, an MCP server or an API source; changing the SOUL rule on packs; reading what people asked for that the fleet cannot do well
related: [skill_packs.py, skill_packs.json, SOUL_bridgeai.md (skill packs rule), gen_capabilities.py, opinion.py, DATA_SHARING.md, INTEGRATIONS_MAP.md]
---
# Knowledge gaps and suggested topics

Design, from the operator (2026-11-27). Nothing below is built except case 1.

**Goal.** When a person asks for something the bot does not know well, it offers to connect the knowledge instead of guessing. Each
gap also leaves an anonymous mark, so the operator sees which topics people need. That list of suggested topics decides the next
packs: the vehicles pack (law, fines, tolls, papers in Argentina) is the kind of thing it should surface.

## 1. The three cases

| Case | Example | What the bot says | Built |
|---|---|---|---|
| A pack has it, but it is off | a job search with `empleo` off | names the pack, asks, and after a yes runs `paquetes on NAME` and asks for /new | yes (SOUL rule) |
| A source exists that we could connect | an MCP server, an official API, a public dataset, a guide | "I have no reliable source for this. I can ask for X to be connected (free, or with your own key). Do you want me to?" | no |
| Nothing known | a topic with no pack and no known source | answers as well as it can, says plainly how sure it is, and asks whether to note the topic for the administrator | no |

Rules for all three:
- **Ask first, never connect alone.** The bot cannot install anything (no pip, no apt). Connecting is the administrator's job. The
  bot only records the request after the person's yes.
- **No guessing presented as knowledge.** When the answer comes from general knowledge, with no pack or source behind it, the bot
  says so in one short line.
- **Once per topic per conversation.** No repeated offers. A "no" is remembered until /new.
- **Keys stay the person's.** A source that needs a key is offered as "with your own key" (KEYS_GUIDE), never with a shared one.

## 2. The record

`gateway sugerir TOPIC [--caso pack|fuente|nada] [--fuente URL] [--si]` appends one line to `/workdir/.sugerencias.jsonl`:
`{ts, caso, tema, fuente, si}`.

- **`tema` is the topic in a few generic words**, written by the bot: "vehicle fines Argentina", "tax forms", "plant care". It
  never holds a name, a place, a number, a quote or anything about the person.
- **The person's level is checked first** (DATA_SHARING.md section 1, gated at the source):
  - `none`: nothing is written;
  - `usage`: only `caso` and a topic from a fixed list of categories (the pack names plus "other");
  - `all`: the generic words too.
- `si` records that the person said yes to connecting. Only those become requests to the operator. The rest are counts.

## 3. What the operator sees

- `ops/sugerencias.py` (to build) runs on the Docker host. It goes through every stack's file, checks `ops/sharing.py` first, and
  prints a table with the topic, how many times it was asked, how many people asked, how many said yes, and the sources named.
  The table holds counts only, never which stack asked.
- A topic asked by several people, or with yeses, is a candidate for a pack (like `vehiculos`), an MCP server, or a gateway command
  (INTEGRATIONS_MAP.md: a narrow gateway command often beats a vendor's MCP).
- The ops bot's daily summary could carry one line: "suggested topics this week: N new, top 3".

## 4. Suggesting topics to the person (the other direction)

The other half of "suggested topics" is the bot telling a person what it can do that they have not used. Suggestions run under
these limits:
- At most one suggestion per day, only at the end of an answer that was about something close (a question about a trip, then
  "I also have a vehicles guide: tolls, papers, fines").
- Never for a pack the person switched off themselves.
- The person turns suggestions off by saying so; `/verbosidad` (to build) quiet means none.

## 5. Open decisions (operator)

1. Is the record kept per stack only, or does the yes also send a note to the operator at once (the ops bot)?
2. The categories under `usage`: the pack names plus "other", or a broader list?
3. Should section 4 (suggesting packs to the person) exist at all, and at what pace?
4. Who connects a source: the operator only, or `tecnico` (the bot team) proposing it on Gitea as a task?

## 6. Order to build

1. The SOUL rule for cases 2 and 3 (few words: the SOUL is near its 32000-character cap).
2. `gateway sugerir` with the level check, and its selftest.
3. `ops/sugerencias.py`.
4. Section 4, if the operator wants it.
