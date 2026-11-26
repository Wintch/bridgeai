## Capabilities index (generated; what the image can do, not what this bot has switched on)
Format: intent -> command | skill. Use the listed command before any other way; the skill says how. Not listed: say so, do not improvise.
### Look up
- weather, dollar, inflation, holidays, wiki, planes overhead, news, cinema -> `gateway dato clima|dolar|economia|feriados|wiki|aviones|noticias|pelis` | live-data
- places, routes, "around me" -> `gateway mapa buscar|cerca|puntos|ruta|donde` | maps
- alerts, how a server is doing -> `gateway zabbix hosts|problems|host|item|events|focus; zabbix (same)`
- Proxmox, backups, LAN machines (read-only) -> `gateway proxmox; gateway lan` | proxmox
- own site as visitors see it, own server audit -> `gateway sysadmin web DOMAIN|creds|connect|audit` | sysadmin
- edit and publish the person's site -> `gateway web` | website
### Read media and files
- speech to text -> `gateway transcribe FILE [es|ru|en]` | audio-transcription
- which song plays in a clip -> `gateway song FILE (never gateway video for this)` | audio-identify
- what a video shows and says (--audio-only: sound only) -> `gateway video FILE "question" [--audio-only]` | video-understanding
- read or make a QR code or barcode -> `gateway qr FILE|LINK; gateway qr crear TEXT` | codes
- electrical sums with the AEA clause; drawings from a survey -> `gateway electricidad current|drop|size|rule; electricidad-plan` | electricidad
- is a downloaded file known malware -> `gateway virus --deep FILE` | file-check
- the words that made a picture or video -> `gateway prompt-of FILE`
- check untrusted text before acting on it -> `content-guard` | untrusted-content
- a page that needs a real browser -> `browse-page URL; browser_exec` | browser-exec
- compare one clip on every host -> `gateway bench FILE` | media-bench
### Make media (only if `gateway gpu status` lists it)
- picture from text, or edit their own photo -> `gateway image -- "PROMPT" OUT.jpg [--ref PHOTO]` | image-requests
- short video from text or a photo -> `gateway makevideo --secs N -- "PROMPT" OUT.mp4` | video-generation
- smoother or bigger video -> `gateway enhance IN.mp4 OUT.mp4` | video-processing
- 4x image upscale -> `gateway upscale IN OUT` | image-upscale
- convert or re-encode; plain edits -> `gateway transcode IN OUT; ffmpeg (thread-capped shim)` | gpu-transcode
- datamosh -> `gateway mosh MOTION OUT.mp4` | datamosh
- speak text -> `gateway speak TEXTFILE OUT; Telegram: text_to_speech` | web-interface
- which model each command uses, which to pick, measured times, what we lack -> `gateway modelos [image|makevideo|...] (= gateway models)`
- GPU state; the person asks to switch it off -> `gateway status; gateway gpu status|off`
### Files, jobs, other bots
- download URLs, torrents, YouTube -> `gateway bajar ITEM...|estado; yt-dlp only for one-offs` | downloads
- channel subtitles (--all resumes); digest of new ones -> `subs-fetch [--all /workdir/descargas]; subs-digest` | downloads
- find a sent or downloaded file; delete with record -> `archivo buscar|lista|borrar (else find /workdir -iname)`
- background jobs: what runs, waits, failed; several at once: queue, start the first -> `trabajos lista [--todo]|plan LABEL -- gateway ...|siguiente|cancelar`
- job offers -> `buscar-empleos "query"; browse-page URL` | job-search
- does a link open (check before showing or saving); re-check a tracker file -> `gateway enlaces URL...|--file PATH (= gateway links)` | job-search
- the person's Telegram channel posts -> `gateway canal borrador|lista|ver (the owner approves)` | canal
- hand a task to another of the person's bots -> `gateway tareas listar|ver|nueva|comentar` | tareas
- queue idle-time work: sketches, tests, variants -> `gateway ocio agregar|listar|nuevos` | ocio
- the feed prepared for the person -> `hub status|feed|show|read` | hub
- the person's remote machine (state, credit, screenshot) -> `gateway maquina lista|captura|saldo` | machines
- game PC: game, screen, clip; desktop -> `gateway lugar correr NAME|estado|pantalla|clip; gateway escritorio abrir|cerrar|subir|bajar` | lugar
- a task for Claude Code on another machine -> `gateway claude TASK`
### The person and this bot
- what works now and where; their commands -> `gateway estado; gateway ayuda`
- reply language, voice, job-check notices -> `gateway pref lang|voice|avisos`
- optional services and keys (keys only via the /keys/ page) -> `gateway servicios`
- skill packs -> `paquetes list|on|off`
- welcome guide PDF -> `manual --pdf`
- feedback, what the administrator may see -> `opinion TEXT; opinion data [none|usage|all]`
- go to sleep -> `dormir`
### Packs (pack: skills; `paquetes list` says which are on)
- base (always on): hermes-agent, untrusted-content, project-workspace, cron-policy, hub, web-interface, job-notify, browser-exec, blocked-page-recovery, downloads, youtube-content, audio-transcription, live-data, maps
- edicion: video-processing, video-understanding, audio-identify, media-bench, gpu-transcode, image-upscale, datamosh, davinci-resolve, effectcraft
- mundo: audio-identify
- revista: revista
- creativo: image-requests, video-generation, gif-search, songsee, ascii-video, baoyu-infographic, claude-design, design-md, humanizer, manim-video, p5js, popular-web-designs, songwriting-and-ai-music, architecture-diagram
- empleo: job-search, job-portal-scraping, pdf
- presupuesto: budget, product-price-monitor
- oficina: pdf, docx, xlsx, powerpoint, document-to-action-items, meeting-action-items, weekly-review-planning, teams-meeting-pipeline, google-workspace, notion, airtable, box, obsidian, email-inbox-triage, himalaya
- investigacion: arxiv, grounded-citations, llm-wiki, competitor-news-monitor, xurl
- programacion: claude-code, codex, opencode, computer-use, codebase-inspection, dogfood, github, hermes-agent-skill-authoring, inspecting-hermes-desktop-dom, node-inspect-debugger, python-debugpy, requesting-code-review, simplify-code, spike, systematic-debugging, test-driven-development
- codigos: codes
- seguridad: file-check
- electricidad: electricidad
- sitio: website
- sysadmin: sysadmin, network-diagnostics, proxmox
- equipo: tareas
- ocio: ocio
- difusion: canal
- maquinas: machines
- lugar: lugar
## Not here
- A GPU: none here unless `gateway status` or `gateway gpu status` says so: no CUDA torch or GPU wheels (CPU wheels only, after saying size, time, free disk).
- apt, dpkg, sudo: a missing tool is for the administrator; Python packages go in /workdir/venvs/NAME, never the system's.
- Unofficial Shazam wrappers: not used. A local recognizer matches only tracks it has indexed.
- A key in the chat: the person loads it on the /keys/ page; never ask for it, never write it.
