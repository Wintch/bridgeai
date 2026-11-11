# Messaging fronts: is anything better than Telegram?

Read-only research (Hermes adapters at the pin and a newer release, platform comparison from official docs, web front) plus a live media-format test through the Bot API. Detail for Telegram itself is in `TELEGRAM_FEATURES.md`.
Rule: another front is worth it only if it is better (latency, clients on every OS, usability, open source).
Items marked UNVERIFIED were not confirmed against a primary source.

## 1 Verdict

- **Telegram stays the main front.** It is the only one with all of these together: a 24 h server-side update queue we can peek
  without consuming (that is what makes sleep/wake lose nothing), inline buttons, draft and edit streaming, native voice notes,
  2 GB files through the local Bot API, no per-message cost, no business paperwork, clients on Android, iOS, Windows, macOS,
  Linux and web.
- **Web (Open WebUI over Hermes `api_server`) is already live as the second front** on every stack, Keep it for long documents, files, PDFs and diagrams. Do not swap it for LibreChat or LobeChat: same API limits, heavier,
  and LobeHub's licence is more restrictive.
- **Matrix (Element X) is the only front better on openness**: open source end to end, self-hostable, optional E2EE, feature
  parity in Hermes (edit streaming, native voice bubble, reaction approvals, 100 MB). Worse on phone onboarding. Opt-in second
  front for a person who asks for E2EE or self-hosting, after a small wake patch (section 4).
- **WhatsApp: not now.** Meta's WhatsApp Business terms (section 4.7 "AI Providers", all users since 2026-01-15) bar
  general-purpose AI assistants when AI is the main function; exceptions are per country and paid (Italy about $0.069 per message
  from 2026-02-16; Brazil reported; EU interim order of June 2026 under appeal). Plus the 24 h window and templates (Hermes has no
  template support), per-message billing, 5 MB images, 16 MB video, no streaming. Unofficial bridges (Baileys, whatsmeow) put the
  person's own number at ban risk.
  Sources: https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform ,
  https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing ,
  https://techcrunch.com/2026/01/28/whatsapp-will-now-charge-ai-chatbots-to-operate-in-italy/
- **Slack, Discord, Mattermost, Zulip, Rocket.Chat, Teams, Google Chat**: work or community tools, weaker phone UX and push,
  workspace or tenant per person. Discord has one real edge (live voice channels, below). Signal and SimpleX: privacy, but no
  buttons, no voice bubble, unofficial tooling, quiet upstream adapters.

## 2 What Hermes ships (pin 818c13be = v0.21.6 vs v0.23.0)

All 27 adapters of v0.23.0 already exist at our pin; the adapter code of Telegram, Discord, Slack, Matrix, Signal and both
WhatsApp adapters is nearly identical between the two, so a Hermes bump does not change this comparison. v0.23.0 moved every
adapter under `plugins/platforms/`.

| Front | How it receives | Streaming | Voice out | Files | Buttons / approvals | Wake-on-message for us |
|---|---|---|---|---|---|---|
| Telegram | polling (or webhook) + our local Bot API | draft + edit | native voice note | 2 GB local | inline keyboards | **works today** (waker peeks `getUpdates`) |
| Web (`api_server` + Open WebUI) | HTTP | SSE | via voice-proxy | uploads (workaround) | none: approvals denied, "ask in Telegram" | page navigation only; a message typed in an already open tab while asleep is lost |
| Matrix | homeserver `/sync` | edit, threaded tool panes | native bubble (MSC3245) | 100 MB | by reaction | feasible: homeserver keeps events, but `matrix.py` drops events older than 5 s before startup (`_STARTUP_GRACE_SECONDS`): patch needed |
| WhatsApp Cloud | Meta webhook to public HTTPS | none (no edit) | native bubble with ffmpeg | 5/16/100 MB | 3 buttons then a list | waker must be the public receiver and replay the signed POST |
| WhatsApp Baileys | Node bridge on 127.0.0.1 | edit | always voice note | UNVERIFIED | polls for clarify only | very hard: bridge dies with the container |
| Signal | signal-cli daemon (SSE) | none | file | 100 MB | text `/approve` | hard: SSE copy cannot be replayed into Hermes |
| Slack | Socket Mode | draft + edit | file | UNVERIFIED | Block Kit | hard: no queue while disconnected (UNVERIFIED) |
| Discord | gateway WebSocket | edit | native voice message; **voice channels: join, listen, talk back** | 25 MB | buttons | hard: no offline replay; `missed_message_backfill` is for channels |

Others in the tree: Mattermost, SimpleX, Teams, Google Chat, LINE, email (IMAP/SMTP), SMS (Twilio, paid), ntfy (push topic),
Photon/BlueBubbles (iMessage), IRC and niche ones, six Chinese platforms, `webhook`, and an experimental `gateway/relay` whose
connector buffers events while the gateway sleeps and pokes a wake URL (the one upstream design close to our waker; we would
have to write the connector). The community `plugin-catalog/` lists about 1050 plugins (quality UNVERIFIED).

Hermes's own newer fronts:
- **Hermes Desktop** (Electron: macOS, Windows, Linux; no phone app) and **Hermes Webapp** (v0.22.6+, the Desktop workspace in a
  browser, off by default, needs HTTPS for the mic). Upstream says they share one conversation history with the messaging
  channels and have an approvals UI. This is the only candidate that could beat Open WebUI. It needs the pin bump to v0.22.7+
  and a test on `guests/prueba` (auth not tied to Nous sign-in, HTTPS and mic, PWA, wake). UNVERIFIED until then.
- The Hermes web dashboard (pin) is an admin tool (edits `.env`), never for a person.

## 3 One person, several fronts

- **Memory and skills: shared.** Memory is per Hermes home, not per platform; one stack can run Telegram, web and Matrix at once.
- **Conversation: separate.** The session key includes the platform and chat id (`gateway/session.py` `build_session_key`), so a
  Telegram chat and a web chat are two transcripts. `api_server` cannot bind a Telegram session (409). Cross-front `/resume` works
  only for a configured admin (`_resume_caller_is_admin`); making each person admin of their own one-person stack is an untested idea.
- Quick commands (`/trabajos`, `/parar`, `/dormir`) and tool approvals exist only in Telegram today.

## 4 Cost of adding a front

Telegram-only pieces to redo per front: `patches/telegram_large_files.py`, `telegram_live_location.py`,
`telegram_long_reply_file.py`, `telegram_replied_audio.py`, `telegram_video_note.py`, `telegram_image_preview.py`, half of
`help_menu.py`, the Telegram block in `start_hermes.sh`, the bot-token page in `keys_server.py`, cron `--deliver telegram`, the
sleep notice, and in `ops/wake/waker.py` the sentinel, notices, offset confirm and readiness check. The generic patches (busy,
steer, notices, runaway cap, reply language, approvals bridge) keep working; some user-facing text says "Telegram".
STT and TTS are gateway-level, so `stt.provider=bridge` and `tts.provider=bridge` carry over to any front.

## 5 Best media format per platform

Tested on Telegram (phone and PC); the rest from docs.

| Platform | Pictures | Re-encodes pictures? | Video | Caps |
|---|---|---|---|---|
| Telegram (tested) | JPEG, PNG, WebP as photo. **AVIF refused** (`IMAGE_PROCESS_FAILED`) and never previews as a file, even with a thumbnail; our patch converts it to JPEG | yes, to its own JPEG (270-291 KB for 1024 px whatever we send) | **not re-encoded**: AV1, HEVC, H.264 MP4 play; WebM/VP9 arrives as a file; AV1 gets no thumbnail from Telegram (Hermes sends its own) | photo 10 MB, file 50 MB (2 GB local) |
| WhatsApp Cloud | JPEG, PNG, static WebP (to JPEG); 4096 px max | yes | H.264 + AAC only, MP4/3GP, faststart | image 5 MB, video 16 MB, doc 100 MB |
| Signal | JPEG (long edge about 1600 px at standard quality) | yes, even at High | H.264 MP4 (UNVERIFIED) | about 100 MB (UNVERIFIED) |
| Matrix / Element | JPEG, PNG, WebP; AVIF depends on the client (UNVERIFIED) | no (thumbnails only) | what the client plays; H.264 safe | server setting (Synapse default 50 MB) |
| Slack, Discord, Mattermost | JPEG, PNG (WebP on Mattermost) | UNVERIFIED | H.264 MP4; Discord desktop/web also HEVC | Discord 10-25 MB free (sources conflict) |
| Web browsers | JPEG, PNG, WebP everywhere; AVIF about 93-95 %; JPEG XL partial; HEIC Safari only | n/a | H.264 everywhere; HEVC Safari and hardware-decode Chrome/Edge | n/a |

Rule: **pictures as JPEG q85-90** on every front (Telegram re-encodes anyway, so a lighter upload saves the person nothing).
**Video: AV1 or HEVC MP4 for Telegram and the web when the person's devices play it** (Telegram does not re-encode, so the
lighter file is what they download; AV1 encodes on CPU), **H.264/AAC MP4 for WhatsApp, unknown or old devices**. Voice: OGG/Opus
mono works on Telegram, WhatsApp and Matrix.

## 6 Next steps (each small, guest first)

1. Keep Telegram.
2. After a pin bump (`HERMES_UPSTREAM_SCAN.md`), test Hermes Webapp on `guests/prueba` (shared history, approvals, auth, wake).
3. If a wake-aware web path is wanted: a static PWA shell that queues the message (IndexedDB) and calls a new authenticated POST
   wake endpoint in `waker.py`; it is the only web design that meets "never lose a message".
4. Matrix only on request: patch `_STARTUP_GRACE_SECONDS` for wake, extend the waker, test voice and streaming on Element X.
5. Realtime voice stays the planned Pipecat WebRTC page (`consult_agent`), not a chat front. Discord voice channels are a turn
   pipeline (STT, LLM, TTS), not realtime duplex.
6. Push for an away person: test Hermes `ntfy` next to Telegram if ever needed.
7. Measure AV1 vs HEVC vs H.264 on real footage on the CPU host before making AV1 the Telegram default for video.
