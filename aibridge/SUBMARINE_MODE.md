---
title: Submarine mode: the whole fleet self-hosted only, no external communication
scope: a switch that runs every stack on our own machines only, the notice people get, and the drill that tests it
when_to_use: planning or running the drill; any change to the router, the gateway's STT/TTS/vision paths, web tools or the Docker host's egress
related: [DATA_SHARING.md (local versus third-party processing), router.py (cloud_direct, local_entry), gateway.py (transcribe, tts), ops/gateways.json.example, ops/web_banner.sh, SYNTHETIC_DAY.md]
---
# Submarine mode

**Goal.** Run everything on our own machines, with nothing leaving the building. It answers two needs:

- **Local-only processing** (DATA_SHARING.md section 6.1). A person, or the whole fleet, can be served without any third party: no
  cloud model, no cloud transcription, no web.
- **Resilience.** It keeps working when the internet line, a provider or a key fails.

It is the mirror of `cloud_direct` (the router's switch that sends everything to the cloud). Name in the bots: "modo submarino"
(es), "режим подлодки" (ru), "submarine mode" (en).

The name comes from a submarine's [silent running](https://en.wikipedia.org/wiki/Silent_running_(submarine)): the boat keeps working,
but sends nothing out that could be heard. It is the opposite of a phone's airplane mode. In airplane mode the phone cuts its link
and loses the service. Here the service keeps running, all of it at home, and only the outside link is cut.

## 1. What changes when it is on

| Piece | Normal | Submarine |
|---|---|---|
| Main model | router: home model first, then the cloud chain; or a pinned provider | router: home models only (`local_only`); a pinned cloud model is set aside for the duration |
| Small calls (titles, memory review, vision, approval guard) | `local-only` already | unchanged |
| Voice to text | home GPU, then Groq | home GPU only; a voice note that cannot be transcribed says so plainly |
| Text to voice | home GPU voices, else a cloud voice | home voices only (Piper/Kokoro/Chatterbox on the GPU hosts) |
| Web search, web extract, browser, maps, downloads, job search | on | off; the tools answer "submarine mode: no outside access" right away, never a timeout |
| Telegram | the front for most people | cut: the bots are reachable only through the LAN web front (Open WebUI) |
| Egress from the stacks | open | dropped at the Docker host (DOCKER-USER), except to the home GPU hosts on the LAN |

## 2. The switches

1. **The router's `local_only`.** It goes in `gateways.json` (master, synced per stack), next to `cloud_direct`, and the two cannot
   both be true. With it on, a turn whose home model is asleep or full waits for the model or says plainly that it is busy. It never
   falls back to the cloud.
2. **The gateway.** `gateway transcribe` and `gateway tts` skip every cloud step. The tools that need the outside answer at once.
3. **Egress at the Docker host.** An allow-list in DOCKER-USER for the stack networks: the GPU hosts' service ports, nothing else,
   so a missed switch still cannot leak. One command turns it on and one turns it off, both idempotent. They are run by the
   operator, because this changes the host firewall.
4. **The home models awake.** Before the switch, the GPU hosts are woken and their models loaded: LLM, STT, TTS and vision.
   Their state is checked through the gate. The hosts stay awake for the duration, since the stacks have no other place to go.

## 3. Telling people

- **Before:** one message through each person's bot, in their language, while Telegram still works. It says when it starts, how
  long it lasts, that the assistant will answer only on the home network web page with home models (slower, no web), and how to
  reach it. For a drill, it also says it is a drill.
- **During:**
  - The web front shows a banner with `ops/web_banner.sh`: "Self-hosted only: no internet, home models".
  - `/estado` (gateway estado) says the same.
  - Every reply carries no "from the cloud" line, since none goes there.
- **After:** one message saying it is over, and anything that waited (Telegram messages that arrived while cut off) is answered
  first.

## 4. The drill

1. Announce it (section 3), with the date, the time window and how to reach the bot during it.
2. Wake the GPU hosts and load the models. Record the load time and the VRAM used.
3. Turn on the switches in order: router, gateway, egress. Check that a request to a cloud host from inside a stack is refused.
4. During the window:
   - People use the bots on the LAN web front.
   - The synthetic-day harness (`SYNTHETIC_DAY.md`) runs a short day against one stack.
   - Measure: time to the first token, turns per minute, failures, and what people could not do.
5. Turn it off in reverse order. Check that Telegram messages that arrived meanwhile are answered.
6. Write it up: what worked, what broke, and how far the home models are from good enough. That is the list of what to build
   next.

## 5. Open decisions (operator)

- Which bot runs the first drill, and whether it is a single stack or the whole fleet.
- Which home models are loaded on which card, since the cards decide quality and speed.
- How long the window lasts, and whether people are asked to take part or it runs on the operator's stack only.
- Whether submarine mode can also be turned on per person, permanently (local-only processing for someone who asks for it), and not
  only for the fleet in a drill.

## 6. Status

Order of the work:
1. **Built (2026-11-26):** the router's `local_only`.
   - Every call (turns, subagents, /btw, Hermes's own small calls and pictures) goes to the home model or nowhere, with no
     classification, no 🔒 question and no cloud vision on an earlier consent.
   - A turn home cannot take gets "⚓ Modo submarino … mandá el mensaje de nuevo en un rato" (es/ru); Hermes's own calls and
     subagents get a 503. It is logged as `route: submarino`.
   - It wins over `cloud_direct` if both are set. `/router/state` reports it, and `/estado` opens with "⚓ Modo submarino" and
     never offers the cloud.
   - Tested in `router_smoke.py` (section 10b) and `gateway_pref_selftest.py`.
   - Not yet: a model pinned with `/model` bypasses the router, so a pinned cloud model still answers. Setting it aside for the
     duration is part of step 2. `/estado`'s voice lines still say Groq until step 2 turns it off.
2. The gateway's cloud steps off.
3. The tools' quick refusal.
4. The egress allow-list commands.
5. The notices and the banner.
6. The first drill.
