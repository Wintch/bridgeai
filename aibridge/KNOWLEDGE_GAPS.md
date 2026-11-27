---
title: Knowledge gaps and suggested topics: offer to connect what is missing, and learn which packs to build next
scope: what the bot says when it lacks knowledge or a source for a request, the record it leaves, and how the operator reads them across stacks
when_to_use: adding a pack, an MCP server or an API source; changing the SOUL rule on packs; reading what people asked for that the fleet cannot do well
related: [skill_packs.py, skill_packs.json, SOUL_bridgeai.md (skill packs rule), gen_capabilities.py, opinion.py, DATA_SHARING.md, INTEGRATIONS_MAP.md]
---
# Knowledge gaps and suggested topics

Operator's direction (2026-11-26/27). **The source is our own packs**: the modules built in bridgeai (vehicles, electricity, office,
job search...). Connecting one means switching it on for the person (`paquetes on NAME`, as copying a pack in). Nothing is pushed:
a pack is offered only when the person asks for something of that kind and does not have it. A small model then does not try it
with whatever tools it has and lose the person's time. It can also spare the cloud: with the pack's guide, the home model may be
enough.

## 1. What happens (built 2026-11-27, router.py)

- **The match.** Each pack in `skill_packs.json` has `hints`, regular expressions in es/ru/en ("fotomulta", "peaje", "штраф",
  "parking fine"). `off_packs_for(text)` returns at most two packs whose hints match the person's message and that are off for
  them.
  - Never on a legacy stack: with no choice file, every pack is on.
  - Never a pack that needs the operator's set-up (`gateway_config`: lugar, maquinas, equipo...).
- **The note for the model.** A message that matches gets a short note after it, on the outgoing copy only (Hermes's history
  never stores it): the pack covers this and is off; say so in one line and offer it; after a yes run `paquetes on NAME` and ask
  for /new; if they already said no, answer without it.
  - Every matching message keeps its note, so the prompt cache holds (as with the reply-language note).
  - It is not added to aux calls, subagents, cron runs or Hermes's own prompts.
- **The 🔒 question.** When the router asks for the cloud and an off pack matches, the question adds one line: "💡 Para esto hay
  un paquete de bridgeai, «…», que tenés apagado: con él el modelo de casa tiene la guía armada y puede que no haga falta la
  nube" (es/ru).
- **The record.** One line per matching message in the stack's own `/workdir/.sugerencias.jsonl`: `{ts, caso: "pack", tema: NAME}`.
  It holds the pack name only, never text. Nothing is written under `/compartir nada`. It stays in the stack: no message to the
  operator (decision 1).
- The SOUL rule on packs (name it, ask, `paquetes on` after a yes, /new) is unchanged; the note makes the model apply it at the
  right moment.

## 2. Hints: keep them narrow

A false match costs one line of the person's time and some trust, so a hint must name the thing itself, not a word that also
means something else. Checked on 2026-11-27:
- "rust" (óxido in a car) and a bare "virus" (an illness) matched before they were narrowed.
- "arca" now needs a context: "página de ARCA", "clave de ARCA".

When a pack is added, its hints go with it, and they are tried on everyday phrases in the three languages. `router_selftest.py`
covers the mechanics.

## 3. Still to build

1. `ops/sugerencias.py` on the Docker host. It goes through every stack's `.sugerencias.jsonl` (checking `ops/sharing.py` first)
   and counts per pack how often it was offered and on how many stacks. It also tells, from the person's pack choice, whether the
   offer was then taken.
2. **Topics no pack covers.** The bot answers as well as it can, says how sure it is, and asks whether to note the topic. That needs
   `gateway sugerir` writing `{caso: "nada", tema: CATEGORY}` (decision 2 below) and a few words in the SOUL, which is near its
   32000-character cap. These notes decide the next packs, the way the vehicles pack came about.

## 4. Decisions

1. Kept in the stack only, no notice to the operator (2026-11-27).
2. Open: the categories for an uncovered topic under `usage`. The default until decided is the pack names plus "other", so no free
   text is ever stored.
3. Suggesting a pack: yes, but only when the person asks for something of that kind (2026-11-27). Nothing unprompted.
4. The source is bridgeai's own packs, switched on for the person (2026-11-27).
