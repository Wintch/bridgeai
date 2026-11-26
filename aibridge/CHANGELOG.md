# Changelog

One entry per deployed build, newest first, written by `ops/pipeline.sh deploy` (`ops/changelog.py`). An entry lists the commits the
build brought since the previous deployed one. A build is named by its commit; `git show <hash>` has the detail.

## 2f20b46 — 2026-11-26

Image 5fa9b4f835bf. Replaces 0a047ee. Deployed to hernik only (awake: the waker applies it when idle).

- Places assistant, read-only first: gate /place/screen (a JPEG of the place, the person is told on the desktop) and /place/games (installed Steam and Epic games), only where the operator turns the assistant on; bot verbs escritorio pantalla|captura and escritorio juegos; the shader watch and the games list look only in Steam's library folders (a recursive search through a 42 GB game took over 30 s); uninstall rule for shared games documented (`2f20b46`)
- Design: the bot acts through fixed gate verbs (decided), and only after each place's home can be snapshotted and rolled back; the games disk becomes btrfs (subvolume homes, instant snapshots without extra writes, hardlinks still shared) (`fd35942`)
- Design: the person's bot working inside their own place (install or start a game, open a page, a screenshot) through fixed gate verbs with the place's own token, compared with SSH and an in-place agent; index updated (`57b4b09`)
- Door guide: a ProtonDB search for games places (opens ProtonDB's search in a new tab, tiers explained); away design: the choice lasts 3 hours, bends to free RAM and to letting the host sleep, and applies to containers without a GPU too (`6cf3dd1`)
- Places: design for when the person is away (switch off by default, keep working at the lowest priority, freeze in RAM best effort with a notice when lost, no suspend to SSD; the person picks at the first away notice; 6-hour sessions; rush hour; the host sleeps when every place sleeps) and the disk-write measurements and plan (`666dda5`)
- Places: the games images install their packages and the Quake demo data before copying the small scripts, so a rebuild for a script reuses the heavy layer instead of writing gigabytes to the host's disk (`650cd2b`)
- Places: 'in use' means human activity: somebody watching (a web connection or a Moonlight client) and touching, playing or with sound playing; a game left open with nobody watching closes after 10 minutes and gets the low CPU weight; a render without a game still keeps a place open; the guide says so (`1e830a4`)
- Door guide: copy and paste (both ways in the browser after the clipboard permission; Moonlight types the client's clipboard into the desktop with Ctrl+Alt+Shift+V, one way only) (`41bb333`)
- Door: a fuller guide in three languages (what the load panel and the start estimate mean, the desktop look, the panel widget, auto-off and its warnings, Moonlight's game list, playing together, the weekly co-op as coming soon), checked line by line against the code; places: Force-close game also ends the Quake engine started as '. ioquake3'; design for the weekly co-op game and confined guest places; idea of a ProtonDB badge per game (`4c068bd`)
- Places: no dock in the modern XFCE look (it got in the way); a dock left running is closed, plank leaves the images, the door's text and preview follow (`ec829b7`)
- Docs: the door is built (index, places table, login at /_door, Apagar), what is still not done on it, the Moonlight game list is built (`431642d`)
- Places: the game detector also sees the Quake engine started as '. ioquake3' (the Quake-only place's launcher), so its CPU weight and idle rule apply (`93341da`)
- Places: load on the desktop's panel (machine vs this desktop's own cap), CPU shared by weight instead of a fixed slice (game, in use, untouched; live docker update), the place's name instead of abc on the desktop, how to install software without sudo, and the shared-games design (each place its own library, identical large files hardlinked on one filesystem: one copy on disk and in memory) (`faf6c79`)
- Gate: watches Steam preparing a game's shaders (game, progress, start and end logged, whether a game was open and the person there; told to the person only in diagnostic mode, desktop and bot) and measures the machine's load once a minute; door: the machine's load for everybody (four meters and a plain verdict, a count of open desktops, no names), an estimate while switching on learned from the last starts, diagnostic lines per person (`8e29b39`)
- Door: a desktop showroom (pick the look with previews, Encender or change it live; KDE shown as coming); gate: /place/start takes the chosen look from a fixed list and writes it into the place; places: place-desktop-style applies modern or classic XFCE live (theme, icons, gradient, dock), in the games images (`b25410c`)
- Places: choosing the desktop at the door (design) with what was tried: XFCE as today, XFCE styled, KDE Plasma (same idle memory), and what the image's Wayland mode is (`e5357d6`)
- Places: Moonlight lists every installed game of the place with its cover (Sunshine's app list kept current by place-desktop-links, reloaded through the local admin API without cutting a stream) (`c937d08`)
- Places: desktop icons for every installed game (all Steam libraries, Epic through Heroic) and the place's launchers, kept current every minute, trusted so a click starts them; in the games images, with a selftest (`ef0962a`)
- Places: idea of a game launcher per way in (Moonlight app list and the door page, built from the installed games) (`f11c166`)
- Door: two how-to guides, one for the browser and one for Moonlight (tabs, a step flow drawn in plain HTML, keys shown as keys, Ctrl+Alt+Shift+Q to quit Moonlight); the Moonlight one only for people who have it (`b6e255f`)
- Places: a Moonlight stream sizes the place's screen to the client first (place-sunshine-res via Sunshine's own app list, written on each start) (`3125716`)
- Door: the front page without a session is a plain welcome with no links (the login is reached at /_door), noindex on every answer (`0ad7074`)
- Places: Sunshine runs without the session's LD_PRELOAD (Selkies' interposer turned its keyboard and mice into devices X never reads, so Moonlight had no input); door: a how-to page per person in Spanish, Russian and English, showing only the parts each person has (games, Quake only, Moonlight address) (`408eb91`)
- Places: gamepad state per way in (host, place Moonlight, place browser), what was checked, and the plan to tell browser, place and game apart; a uinput-free shim designed for Moonlight pads in a place (`e499beb`)
- Places: the idle warning escalates (10, 5 and 1 min before, soft to urgent on the desktop; only the first also to the bot); wording: the desktop is switched off, the machine rests (`3b98a4c`)
- Door: DDNS for its DNS-only record (Cloudflare token limited to one zone) and a Let's Encrypt certificate through the DNS challenge, with a deploy hook (`4366282`)
- Places: state notices to the person (desktop warning + the person's own bot through the wake service, the first one with the how-to); place.py keeps settings keys it does not manage; idea of play aliases, warm machines and reservations (`c8544b9`)
- Door: the web front for places (login, state, Encender/Entrar/Cerrar through the gate and the wake service, nginx reverse proxy with the place's auth added), installer and selftest; places: kill-game (menu entry and place.py) force-closes a hung game (`4d6b33f`)
- Places: game profiles folder (one JSON per game, quake3-demo first); the headless server's memory and CPU are settable for a small always-on VM (`98a23f2`)
- Places: design of the web door (one always-on front: password, state, wake/open/enter/close through the gate, reverse proxy, night schedule) (`382d586`)
- Places: the headless Quake III server takes its limits and network subnet from the environment (a no-limit q3dm17 server can sit on the GPU host inside the places' pool) (`eb01dc2`)
- Places: document the web client's game mode (Ctrl+Shift+X) for the mouse in games, in the docs and the bot's desktop skill (`ee97875`)
- Places: a Quake-only place image (no Steam); place.py hold keeps a place open past the idle clock (`51bdce4`)
- Places: an open game holds the place (never closed as idle by the gate; place.py stop refuses it without --force) (`37ae064`)
- Places: --library mounts one extra host folder (another disk, under PLACE_LIBRARY_ROOTS only) as a game library; notes on sharing game files across places (`8a67f61`)
- Places: games image uses the real bubblewrap for Steam's runtime (the base image pointed BWRAP at proot); place.py notify shows a desktop notification in a running place (`fe4d563`)
- Places: Quake III demo never switches the virtual display's video mode (fills the screen borderless by default, a 1280x720 window entry instead of the full-HD one) (`0617c45`)
- Places: drop places' traffic to the home's public addresses (router and hairpin forwards); places-net unit never removes the rules on stop; bigger rate-limit sets; LAN relay hardened (worker threads, answer size cap, send errors caught, BPF filter) (`7722162`)
- Places: relay games' LAN broadcast discovery between places and to a headless Quake III demo LAN server on another Docker host; relay answers leave the host untracked; places-net loads its table in one transaction (`af4ff3e`)
- Places: a full-HD Quake III demo entry (borderless 1920x1080 window: a video mode switch hangs on the virtual display) (`f62d028`)
- Places: NAMEdoc names for the container, hostname, network and host interface; per-place firewall rules and counters; Heroic (Epic) in the games image; designs for network segmentation and ephemeral game sessions (`d352594`)
- Places: the Quake III demo launcher turns the joystick on and hosts non-pure games, so a map keeps the native libraries (`74b6870`)
- Places: the Quake III demo launcher runs ioquake3's native game, menu and client libraries (the demo's own QVMs are an older interface) (`3fa1a5d`)
- Places: the games image carries the Quake III Arena demo on ioquake3 with a menu entry (`956cbdf`)
- Places: games places (Steam and Proton) with a narrow user-namespace profile, a GPU device with the 32-bit driver libraries, and the studio pipeline design (`60f45be`)
- Changelog: 0a047ee (`40cbc0f`)

## 0a047ee — 2026-11-25

Image c8bb2d3e348a. Replaces 37b4679. Some stacks were awake and update when idle.

- Places: the bot confirms a Moonlight PIN and lists or revokes paired devices (gateway escritorio pin|dispositivos|revocar) (`0a047ee`)
- Host: Sunshine on its own base port (48989) reachable from the internet behind a per-address limit; the gate exports HOST_* settings from host.env (`53d0106`)
- Places: a Moonlight stream of a place's own desktop (Sunshine inside, own ports, no /dev/uinput); address-conflict guard in places-net (`9704da4`)
- Changelog: 37b4679 (`fec18d4`)

## 37b4679 — 2026-11-25

Image 1e24be073df2. Replaces bdc1358. Some stacks were awake and update when idle.

- Places: rate limit on new connections from public addresses to a place's web ports; PLACES.md on reaching a place from outside through a router forward (`37b4679`)
- Places: places-net waits for the default route at boot instead of failing (`e2affdf`)
- Places: files between the chat and a desktop (gateway escritorio archivos|subir|convertir|bajar|borrar) (`a767607`)
- Sleep README: say what was not tested about the root ports (`fd17025`)
- Sleep: gpu-host-wake-sources turns off the wake sources (WAKE_OFF) that wake the host the instant it suspends; README on how to find them; reference host GPP0 and GPP8 (`3ef914c`)
- Sleep check: an idle Sunshine's GPU context is not work (a stream still shows as an encoder session); README on what keeps the host awake (`645e2b2`)
- Changelog: bdc1358 (`653cba4`)

## bdc1358 — 2026-11-25

Image b7cf6d975c77. Replaces 35b7990. Some stacks were awake and update when idle.

- PLACES.md: the proxy-first flow, edit on proxies and final pass on the paid copy (`bdc1358`)
- Places: metrics log in the gate clock (one row per running place per minute) and places_report.py (cost of a session, scaling curve, sessions that fit); PLACES.md gets the status, runbook, measurements, export sizes, project-sharing recommendation, known problems (`13880e7`)
- Places: a narrow game-port exception between places (PLACE_GAME_UDP) and place.py --udp to publish a game's UDP port on the place's own address; LAN game between two places measured; dynamic ports designed (`9d2d16b`)
- to-resolve says where the converted files are, each output's size and where Resolve imports from (`16b3f03`)
- Places: to-resolve rebuilt as a tool for files and folders (free and Studio editions, DNxHR tiers, constant frame rate, deinterlace, PCM for every audio track, GPU decode with CPU retry, resume, dry run, mirrored tree); measured DNxHR sizes (`7d821c8`)
- Places: to-resolve looks at the file (H.264/H.265 always re-encoded to DNxHR since the free edition cannot decode them, variable frame rate made constant, interlaced deinterlaced, copy only when readable), helpers mounted from the host copy, PLACES.md on the free edition's real limits (`5bf70f5`)
- Places: own docker network per place, own LAN address, memory/CPU/process limits, an egress firewall (a place reaches the internet and nothing else, places-net.sh + unit), VLC and htop in the image, recreate --bind (`2243f8f`)
- gateway usage text lists escritorio (the pre-push usage check) (`8b427f7`)
- Desktop places from the bot: gateway escritorio abrir|cerrar|seguir|estado, a gate /place/* with one token per place, an idle close after 30 minutes with a warning 10 minutes before (through jobwatch), place.py recreate/gate-token/--ports (`0e7ec12`)
- Place: the Resolve layer mounts the .deb files instead of copying them (image 20.6 GB instead of 28.3 GB) (`6c97e72`)
- Place: to-resolve (full or --audio) and from-resolve as tested scripts, build-resolve.sh runs the package maker in the installer's folder, PLACES.md on files through Telegram and on the ports (`9bb0b01`)
- Person's desktop place: Dockerfile.place (webtop + Brave + Telegram + English environment + to-resolve), place.py to create/start/stop one container per person on a LAN-only address, the Resolve free-edition layer (Dockerfile.resolve, build-resolve.sh refuses Studio), PLACES.md with the on-demand door as a design (`7fccff3`)
- Long recording: segments end after 10 minutes or 1 GB, whichever comes first (length from the bitrate ceiling), largest segment reported at stop; changelog 35b7990 (`c860437`)

## 35b7990 — 2026-11-24

Image 7a6607a22925. Replaces 5dacd67. Some stacks were awake and update when idle.

- Game PC: long recording at the origin (ten-minute segments, 10 GB cap, delivery in parts under 1.8 GB, delete after the person confirms), profile calidad (720p30 1 Mbit/s), gateway lugar largo start|stop|lista|enviar|borrar (`35b7990`)
- Changelog: 5dacd67 (`95b60e4`)

## 5dacd67 — 2026-11-24

Image c5bb35c541ae. Replaces fdbbe8f. Some stacks were awake and update when idle.

- Game PC: recording profiles (full 1080p60, medio 720p30, ligero 480p30 1 Mbit mono), recording off until the person turns it on (/lugar rec), recording status, and the host's own stats in estado (refresh, encoder fps against it, who is connected, Sunshine problems) (`5dacd67`)
- Game PC: gateway lugar pantalla and clip (one picture or a 10-30 s H.265 + AAC recording of the screen, taken by the gate itself, sent as MEDIA:), /host/screenshot and /host/clip, no 144 Hz flag for a real monitor, skill and docs (`0840359`)
- Game PC: Sunshine autostart waits for the display mode change (Moonlight error -1 came from a capture probe that overlapped it), start-sunshine.sh template and the symptom documented (`2af7b95`)
- GPU host docs: the LAN card's name moves when PCI hardware is added (network config and the Wake-on-LAN rule went stale at once); templates to arm WoL by MAC and to pin a name; changelog for fdbbe8f (`549ded3`)

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

