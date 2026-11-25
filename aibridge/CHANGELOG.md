# Changelog

One entry per deployed build, newest first, written by `ops/pipeline.sh deploy` (`ops/changelog.py`). An entry lists the commits the
build brought since the previous deployed one. A build is named by its commit; `git show <hash>` has the detail.

## fdbbe8f — 2026-11-24

Image f6854c3d7978. Replaces dd0f01e. Some stacks were awake and update when idle.

- Review fixes: [SILENT] never answers a message the person wrote (SOUL, net -3 chars); website skill says which check it did (live vs working copy), asks one question on ambiguous layout words, tables renumbered labels, keeps preview habits in the prefs file, no background servers (`fdbbe8f`)
- Patching guide: unattended production web servers (security-only, reboot in a window, needrestart), alert when a machine stops patching, runtimes past upstream end of life, prefer the distro's own packages (SEC-PATCH-22 to 25) (`c79b3f7`)
- Game PC heat alert: the gate pushes its minute reading to Zabbix trapper items, template GPU host heat (hot and thermal slowdown page, warm is dashboard only, sleep closes the problem), provision.py heat-host, selftests (`d86412e`)
- Game PC: heat in the gate (thermal state, minute log, /host/thermal), a warning in gateway lugar estado, and a boot/resume GPU power-limit unit (`136d6f9`)
- LUGAR.md: waking and freezing through the rental panel measured end to end (suspend 7.2 s, back 8.4 s, game alive) (`2572862`)
- Changelog: dd0f01e (`279d27f`)

## dd0f01e — 2026-11-24

Image bc6e03e0ed03. Replaces b5eb824. Some stacks were awake and update when idle.

- Docs for the game PC (LUGAR.md), the files that lived only on the GPU host (templates, probe, boot and freeze tests), waker and ledger behaviour, example config; capabilities index gets the lugar line; the sync summary never shows the host token (`dd0f01e`)
- gateway lugar: run a game on the person's own game PC by a loose name, say when Steam is still compiling shaders, /lugar freeze|shutdown (`0094b90`)
- GPU gate: /host/* (games, state with shader compilation and ready, launch, suspend/poweroff) under its own token; games start in their own transient unit (`88955d0`)
- gateway maquina: congelar (/machine freeze) suspends with everything open and keeps the reservation; waking it only wakes (`ad50013`)
- Remote desktop doc: Sunshine did not start on a cold boot (XFCE never reaches graphical-session.target); autostart fix and measured boot stages (`2ce1db0`)
- GPU host: frozen_test.sh (suspend with a game open, wake by WoL, time the stages) and the measured result (`fd1508f`)
- GPU host: inbound firewall template (own nft table, LAN-only SSH and Sunshine, gate from two clients) and how to apply it safely (`254cb5c`)
- Remote desktop doc: 1080p144 on the plug that advertises only 1080p60 (Xorg mode validation + runtime mode at login) (`4275976`)
- Waker: every status message (booting, waiting, ready, warnings) is silent; only Hermes's answers make a sound (`00f4d00`)
- Changelog: b5eb824 (`e15e2c7`)

## b5eb824 — 2026-11-24

Image 934d28b2a8d3. Replaces 0f8ced7. Some stacks were awake and update when idle.

- Hernik review fixes: ffmpeg's clean stop is not a failure, the ledger block says answer first, live-trip rules in the maps skill (`b5eb824`)
- Architecture: the router's fixed 81920 window plus the Gemini output reservation made compaction run every turn (`9902bab`)
- API request cap: stack and guest compose set 96 MB (the chat history with its pictures is resent on every turn) (`6e5682a`)
- Remote desktop doc: what DaVinci Resolve Studio needed on the GPU host (ALSA config, media storage, AAC, crash dialog) (`e14f31d`)
- Stack compose: Open WebUI shrinks attached images to 2560 px (seeds new databases) (`577465e`)
- Remote desktop doc: WirePlumber spinning on an idle GPU host and the config that stops it (`2fde527`)
- bus.py: optional TLS verified against a CA from the config (no "ca" key = plain, as before) (`78221fc`)
- Remote desktop on a GPU host: the recipe, what was measured and the known problems (`facf049`)
- Changelog: 0f8ced7 (SOUL done/saved rules, sysadmin F1, AudD out, imggen on CUDA 13, GPU host sleep, image skill, stack_keys fix) (`daf2f56`)

## 0f8ced7 — 2026-11-23

Image 6776e03e9dd6. Replaces bef5849. Some stacks were awake and update when idle.

- Image skill: say plainly when a named image service is paid or not available (`0f8ced7`)
- stack_keys: make the keep-awake folders when the stack has no jobfinder, and say what rc 137 means (`9ede42f`)
- GPU host sleep observer: suspend to RAM when nothing needs the host (`60dfe0c`)
- run_services.sh: imggen gets a small exec tmpfs for Triton's cache (`b348d44`)
- imggen: an image on current ComfyUI and torch for CUDA 13, and the gpu-unlock A/B of the image tiers (`f8ea52f`)
- SOUL: a claim of "done/saved" needs a successful call; asked again means a read-only check again (`6a9fab4`)
- Integrations map: remote desktop, Steam and Epic, EffectCraft in a container, NVIDIA package sources (`df620ad`)
- Drop AudD: gateway song uses ACRCloud only (`423f2bb`)
- sysadmin: pin INSTALL_COMMIT to the commit that holds the installer files (`eb96540`)
- sysadmin pack F1: audit a person's own server from inside, read-only (`fc3a51b`)
- Changelog: bef5849 (turn watch, subtitle status and ETA, map links, web reemplazar warnings, revista naming, skill header test) (`3e76793`)

## bef5849 — 2026-11-22

Image ad528bb0323d. Replaces 29b1c16. Some stacks were awake and update when idle.

- Architecture notes: turn watch, subtitle bookkeeping, map links, web reemplazar and the small-photo warning, skill header test (`bef5849`)
- Tests: every SKILL_*.md must open with a front matter that parses (`2387ac2`)
- Revista skill: "la revista" can be a printed magazine, so ask and name the digest in full (`7e00d4c`)
- gateway web: a photo much smaller than the site's own images is said so (`3f8bf45`)
- gateway mapa: a pasted map link is a place (short links followed, only through map services) (`6c85447`)
- Subtitles: speed, ETA and the pace report count running time, not the clock (`9f4d423`)
- Subtitles: --status prints a short summary by default, --full the long list (`0b02871`)
- Early alert: count the turn-lease trouble Hermes logs, so a cut turn leaves a trace (`59e08f2`)
- Early alert: a turn that runs very long, or makes very many model calls, is told to the operator (`012a63d`)
- Changelog: 29b1c16 (the router carries out the sharing level typed in the web chat) (`be100c6`)

## 29b1c16 — 2026-11-22

Image 09ad992bf768. Replaces fad3d3f. Some stacks were awake and update when idle.

- Router: the sharing level typed in the web chat is carried out by the router (`29b1c16`)
- Changelog: fad3d3f (listing turn for subtitles, /compartir in the web chat, gateway web reemplazar) (`8bffe76`)

## fad3d3f — 2026-11-22

Image 809bee016338. Replaces 91fa650. Some stacks were awake and update when idle.

- gateway web reemplazar: change one work's picture in a single command (`f910a51`)
- SOUL: /compartir and /feedback data typed in the web chat run opinion compartir (`92adff0`)
- Subtitles: whole-channel listings go one at a time with a rest between (`6a271a1`)
- Architecture notes: api_max_request patch row and the router's keepalive rule (`05bb03f`)
- Changelog: 91fa650 (router keepalive fix, configurable web request cap) (`f2f84da`)

## 91fa650 — 2026-11-22

Image 080a577695e5. Replaces 9142a69. Some stacks were awake and update when idle.

- Web chat: the API server's request cap is configurable (default 32 MB) and the web skill states the real limit (`91fa650`)
- Router: keepalive lines are not life, a model that only sends them is cut at the idle window (`0f84800`)
- Changelog: one entry per deployed build, written by the deploy stage (`7077ec8`)

## 9142a69 — 2026-11-21

Image b4dd4f447bbb. Replaces 39f4ca9. Some stacks were awake and update when idle.

- Review follow-ups: subs-fetch command line, resting runs, times and system notices, review error counts (`9142a69`)
- Subtitles: the channel listing follows the pace between requests (a big new channel was a burst of fast requests) (`92cb9d3`)
- Subtitles: gentle pace by default, backlog slice sized for it, one reference file with every pace, limit and time (`5ae22cc`)
- Architecture: design note for subtitle downloads over more than one egress (`9be8df6`)
- Subtitles: slow pace and longer rests by default, a numbers-only ledger and --pace-report to find the pace the site tolerates (`c230f17`)
- Subtitles: the canary command ignores a missing-formats error (it called every backlog tail a soft block); yt-dlp on the nightly build (`31bc2b2`)
- Architecture: planned separate egress for subtitle downloads (SUBS_PROXY design, nothing built) (`8e47a47`)
- Idle-time work: the waker's runner claims the unit itself and hands it over; an empty queue starts no run (`b8e1581`)
- SFTP access: a random account name too, account files written before ssh-keygen needs them (`a2e9c9b`)
- SFTP file access for one person (backup of website and images): chrooted internal-sftp container, password login, system folders left out (`1bdee6d`)
- Production needs the person's own /produccion; the bot is told to go background when a GPU start outlasts a foreground command (`46fb7e8`)
- Publisher: a confirmed deploy whose public-address check failed is published with a warning, not marked failed and redeployed every 10 minutes (`8a3951d`)
- Idle-time work: index row, manual lines, usage text and test shims that the full suite asked for (`4b5b8e2`)
- Idle-time work (ocio): a queue the bot fills, the waker runs ONE unit when a stack would sleep, never cut, never waking anything (`8c3edf6`)
- Router: the evaluation log records where a call's characters go (system, tools, history, last), never the text (`9f7d20f`)
- Router: auxiliary cloud calls (titles, summaries) go out with the model's reasoning off (`e2b2f19`)
- Router pins llama.cpp slots: conversation on one, auxiliary calls on the last; the cold estimate counts the saved cache only when it is the conversation's (`40d1bc5`)
- Compose: HERMES_APPROVALS_MODE reaches the container (default manual) (`a5f33dc`)
- RAW and undecodable picture documents are previewed, not refused (`832a140`)
- router_smoke: the release notice is opt-in, check both the quiet default and the verbose person (`f6e6e5f`)
- Automatic fresh conversations, verificar looks once, logs survive a recreate, news only for those who ask (`29940f6`)
- Waker: the update note (and the fast-rolling ETA) only for a person who chose the detailed level (`86e7a79`)
- Web preview: a dev branch shows the bot's work first, production only with the person's yes (`cbc70ba`)
- Analyst reader: read a copy of state.db (the persisted folder is mounted read-only) (`d67889e`)
- Web publishing: the publisher tells the bot why a commit is not live, and the publisher is in the repo (`8f015de`)
- Analyst stage 1: a background reviewer of each stack's sessions, run by the waker when a stack goes to sleep (`6ca6285`)
- Waker: fast rolling, an opt-in per stack update that starts after 2 quiet minutes and says when it is back (`2130d71`)
- Router: optional per-subagent model spread, prompt tokens and child id in the eval log (`01959b0`)
- Router reads the person's words without the plugin context Hermes appends to the message (`e5f8e50`)
- Selftests in parallel: ~10 min one by one, 161 s eight at a time (`d80eb50`)
- Router: a powered-off gated host is skipped in a second, and a GET never wakes the home model (`06205cc`)
- Idle compaction only with enough messages; no gateway shutdown pings in the person's chat (`bc81062`)
- MODELS_TUNING: long-prompt and compaction measurements of the home model on both cards, prompt cache setting (`cbf76a9`)
- Idle compaction: the waker asks Hermes to compact a long conversation right before an idle stop (`79764fc`)
- Home model: prompt cache kept across the gate's idle stop; a cold long read asks for the cloud first (`129ff7f`)
- Waker: a silent sleep note with the wake time on every sleep, a frozen note on host suspend (`8014e86`)
- Electricidad docs: media allow dir in the architecture note, no-key row in the pack key table (`f22e9d0`)
- Electricidad pack: Argentine electrical installations guide, calculator, survey-to-drawings tool and skill (`f0e5f73`)

