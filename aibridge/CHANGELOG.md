# Changelog

One entry per deployed build, newest first, written by `ops/pipeline.sh deploy` (`ops/changelog.py`). An entry lists the commits the
build brought since the previous deployed one. A build is named by its commit; `git show <hash>` has the detail.

## 7d8011f — 2026-11-28

Image 495d99eb3da4. Replaces 23a4ac8. Some stacks were awake and update when idle.

**For the bots (in the image: what people may notice)**

- Smaller job-search and website skills: each keeps a core with what almost every request needs (job-search 31.6k -> 10k chars, website 14.3k -> 9.7k) and moves the occasional parts to references/ read with skill_view when their case comes up; the core is sent on every model call while the skill is loaded. job-search also says how to answer fast on the web (no notice comes back; code runs without asking) instead of the old 'blocked on the web' lines. skill_refs_selftest.py checks names, files, the image copy and the core size (`7d8011f`)

**Docs and tests**

- Changelog: 23a4ac8 deployed (`5555cbd`)

## 23a4ac8 — 2026-11-28

Image e3213522304c. Replaces 805981d. Some stacks were awake and update when idle.

**For the bots (in the image: what people may notice)**

- Skill updates reach existing stacks again: the baked list of the image's skills is written after the last step that copies skills; design-guide, frontend-design and ascii-art were copied after it, so start_hermes.sh took the persisted copy as made by the bot and an old version won on every stack (the image's new design guide never arrived). image_skills_list_selftest.py keeps the order (`8ebbaf1`)

**Docs and tests**

- Changelog: 805981d deployed (`23a4ac8`)

## 805981d — 2026-11-28

Image e4917af3e524. Replaces f2d037b. Some stacks were awake and update when idle.

**For the bots (in the image: what people may notice)**

- Web chat background work told as it is: there delegate_task runs inside the turn (several tasks of one call in parallel) and a background command never sends a notice, so the bot answers at once, says how long, and asks the person to write again; it never promises 'te aviso' on the web. process_manage is no longer deferred (poll/log is the only way to read a background command there) (`805981d`)

**Docs and tests**

- Changelog: f2d037b deployed (`b329da7`)

## f2d037b — 2026-11-28

Image 133e0e82f7a9. Replaces 97a581e. Some stacks were awake and update when idle.

**For the bots (in the image: what people may notice)**

- Faster compaction: the summary call runs with thinking off (auxiliary.compression extra_body), and HERMES_COMPRESSION_THRESHOLD sets compression.threshold per stack (default 0.5 as before); a browsing web turn compacted 4 times at ~75 s each because after one compaction the prompt already sat near the 64k trigger. The stack compose now passes HERMES_UNATTENDED_MODE, which start_hermes.sh read but never received (`f2d037b`)
- Web turns run terminal scripts like execute_code: on an unattended platform a command whose only findings are script execution (python3 -c, node -e, an interpreter heredoc) runs instead of being refused (patches/unattended_scripts_run.py, AIBRIDGE_UNATTENDED_SCRIPTS=auto); every detector match is checked, so anything else in the same command (delete in root path, pipe to shell, shell heredoc) is still refused, as are the hardline floor and deny rules; cron and -q keep their modes; selftest on the pinned file + image smoke check (`7b0204f`)
- Security policies: hard rules SEC-POL-13 to 16. A confirmation never comes from the agent's side (out-of-band confirmer outside the agent's container, single-use request bound to the person; Telegram button from a confirmer bot the agent has no token for, or a passkey on the web; a deny-list pattern is not a control); every page is read through the same guard, facts yes, obeying never, and the person is told; personal data behind one more layer; agents with the least privilege that works (`e41e147`)

## f83d14e — 2026-11-28

Replaces 202107f. Hosts only: nothing that goes into the image changed, no stack was recreated.

Nothing in this deploy reaches the bots.

**Hosts (waker, deploys, timers, GPU host)**

- Post-deploy validation, steps 1-2 of the feature map: after_batch checks that each stack the last deploy recreated is asleep again (or was woken by someone, from the waker log), each skipped awake stack got or still awaits its update, telemetry ran recently with a clean Zabbix push, the keys page answers on every awake stack that has it, and every place image's requirements fit the GPU host; ops/features.json is the map as data and change_kind.py features PREV REV gives a deploy's pack (touched features, script checks, the bot's guides, what is not validated yet and why) (`f83d14e`)
- Deploys say what reaches the bots: ops/change_kind.py classifies a commit by the files it touched (a COPY source of the agent image = the bots; else hosts, docs, tests); each changelog entry groups its commits under For the bots / Hosts / Docs and tests; and when nothing that goes into the image changed since the deployed build, build and smoke skip the image and deploy ships only the ops files (no stack recreated, DEPLOYED unchanged; IMAGE_FORCE=1 overrides). Measured on the 202107f deploy: 3 of 9 commits reached the bots (`0449a3a`)
- model_menu skips a stack while recreate_hermes.sh holds its recreate lock (a deploy replacing the container made the write fail half-way and sent a false alert); after_batch gives the guest up to 60 s (a deploy may have just recreated it) and says when a failed unit last ran (`a97daed`)

**Docs and tests**

- Feature map: every feature with its code, how it is validated after a deploy (script or the tecnico bot, which gets a task per deploy and invents tests around the change), what it needs and the effort to automate it; the loop classify / skip / host checks / canary / bot pack / test subject / judge, linked to what exists, and the easy next steps (`3432178`)
- Changelog: deploy of 202107f (`2784bf6`)

## 202107f — 2026-11-28

Image f0d6a96a50d1. Replaces 21fe0f3. Some stacks were awake and update when idle.

- Selftest: the tick-order check reads the new keep_brain line (a suspended always-on brain is not kept) (`202107f`)
- Machines: what each image needs from its host and what each host offers (REQUIREMENTS.md): org.bridgeai.requires labels at the end of every Dockerfile (CPU level x86-64-v1..v4, GPU vendor, VRAM, driver, encoder, user namespaces, RAM), host_caps.py measures a host and names what an image lacks; every desktop gets its own look (its name big on a background of its own colour, spread by its slot, optional label/purpose/colour from the gate); ports by layer (a block per service, the machine's slot inside it) and versions per machine as one more monitored host (ACCESS.md) (`495ccfb`)
- Places: one requirement for every machine's ways in (ACCESS.md): each machine declares its purpose and ways (web through the door, LAN web, temporary direct web, Moonlight, LAN games, bot, later agent endpoints), each way with why it is open, who uses it, its credential and how it is closed; the create / change / close / remove / review checklist (`e7f4457`)
- Deploy scheduler: a recreated stack waiting for the waker's stop takes no max_awake slot (idle, about to stop; its memory still counts through MemAvailable), and the deploy ends with the last recreate, logging the stops it did not see as pending (DEPLOY_WAIT_STOPS=1 waits as before). Measured on the A/B bench: max_awake held the last two stacks back while earlier ones waited 5-32 s for their stop, and the last stop added up to 32 s at the end (`82a8d37`)
- Several desktop places per person (a machine per purpose: editing, games...): gateways.json "escritorios" lists them, each with its own place token, name, label, purpose and aliases (ops/gateways_sync.py builds it from the stack's list; the single "escritorio" stays for older readers). `gateway escritorio` with several lists how many there are, what each is for and whether it is open; `gateway escritorio NAME abrir|cerrar|...` picks one by label or alias; an action without a name asks which instead of guessing. One place per stack works as before (`15b74dd`)
- Waker: an always-on stack a person put to sleep stays asleep through a deploy or an update: the boot that checks the new image keeps the suspension and the brain goes back to sleep like an on-demand one (it used to stay up, undoing the request); a person who writes after that boot ends the suspension as before (`95a43a0`)
- Known problems are told on use: ops/feature_status.py writes feature-status.json next to every stack's gateways.json; a gateway command with an entry says it first in the person's language (off: not tried, exit 3; degraded: said, then run), /estado lists them, and the router's home-model notice reads the same file (llm_local: not probed while off, the operator's words in the reason). ops/after_batch.py: one pass over what people use after every batch (stacks on latest, waker, units, disk, guest, wake service, registry, GPU host; --wake drill, --place open/close through the gate, --chat), compared with the previous pass: NEW / STILL / FIXED (`9d8fb69`)
- Changelog: deploy of 21fe0f3 (update notes after a restart) (`b42b881`)
- Deploy scheduler: an awake stack is started at once and takes no launch gap (its recreate only refuses it); the gap between boots goes from 10 s to 3 s. Measured over two deploys: load stayed at 0.25/CPU of 16 with 9 GB spare and no admit check ever waited, so the gap set the pace (11 stacks ~170 s, of which ~60 s were gaps spent on awake stacks). Load, memory and max_awake checks unchanged (`5fc7bde`)

## 21fe0f3 — 2026-11-28

Image 10e7174aecd4. Replaces 6078c20. Some stacks were awake and update when idle.

- Waker: the update note helpers are optional on a stack object (the offline tests' shims copy only some methods) (`21fe0f3`)
- Update restarts are told once: the waker names what the restart cut (background programs, the browser, live subagents; names only) in the stack's workdir right before it stops a brain for an update; the person's next message carries a note for the model: one 🔧 line in their language, the conversation and files are as before, what was cut and whether to resume it. Nothing cut: only people with detailed notices get the line. The note stays on that one message (prompt cache) for a few hours (`866440e`)
- Waker: a closed browser means the person left: the stack sleeps once no chat tab has been open for 60 s (the Open WebUI container's established connections on its port; a reload or a page still loading is not a departure), never while a turn or a job runs, so a pending update applies right away (`aebcde3`)
- Docs: night work and a background agent per person (front/back, shared space, keys per person, phases, the person's alarm, maintenance has the host to itself); delirium tests design; the heavy-tools review loop (`5e55021`)
- Stack diagnostics: context per model call, provider cache, compactions, tokens, cost, per-turn calls/tools, waits and tool ranking per stack (`04cad13`)
- Docs: the pipeline at a glance (Mermaid: stages, machines by role, the protocol and auth of each hop) and a message's path in time (Telegram, wake VM, waker, plugin, router, model or GPU gate, data over NFS); changelog: b27a226, 4037340 and 6078c20 deployed (`bc18120`)

## 6078c20 — 2026-11-27

Image ae836090f19b. Replaces 4037340. Some stacks were awake and update when idle.

- Registry cleanup: registry_gc.py keeps the images of the last KEEP builds (8, from the pipeline's digest files) and deletes the rest, then the registry's garbage collection; dry run by default, never during a build; a weekly user timer on the build machine (`6078c20`)
- Places dedupe is exclusive maintenance: it needs every container stopped (not only the places) and a host-wide maintenance lock (`50d361f`)
- Reply language: no note at all when neither the person nor the stack set a language (the per-message rule applies only on top of a configured stack language), as before; the router smoke caught the change (`d00b8f5`)
- Reply language: a message clearly in one language is answered in it; the stack's language is only for unclear ones (`e7f9838`)
- Job search: the setup review is a tool the agent uses when it helps (asked, or the person repeats the same work by hand), never offered on a calendar (`9afce9c`)

## 4037340 — 2026-11-27

Image 5a12d027a918. Replaces b27a226. Some stacks were awake and update when idle.

- Job search: a courtesy setup review every two weeks; /lgtm for the person's yes to production (`4037340`)
- /produccion publishes by itself; web answers count as answered in telemetry (`74dfdf7`)
- Job search in batches and a warmer night summary; the site folder refuses a plain git push (`a3d6d1c`)

## b27a226 — 2026-11-27

Image e3db380bd259. Replaces 1f7b20c. Some stacks were awake and update when idle.

- Deploy pipeline: image through the private registry by digest, sleeping stacks recreated in parallel within the host's limits, phase times in the deploy log (`b27a226`)
- Telemetry: a mid-turn message redelivered with a date prefix after an interruption continues the running turn as well (the last false failed turns on three stacks) (`9474e12`)
- Telemetry: a compaction's re-inserted active request (same second as its summary) and the 'still in progress' marker continue the running turn too; a 29-minute background continuation that ended with an answer was counted as two failed turns (`f76d6f8`)
- Telemetry: a context compaction summary, a message sent mid-turn (steer) or a background notification continues the running turn instead of opening a new one; each was counted as a failed turn, so a long coding turn with many compactions raised a false failed-turns alert (one stack showed 9 of 12 failed, 2 after the fix) (`865c76b`)
- Telemetry for background subagents and per-container resources (`3b02792`)
- Changelog: 1f7b20c deployed (long tasks to a background subagent) (`62467dc`)
- Waker: a stack stopped for its update goes back to sleep at once when nobody came during the recreate (the idle rule kept it up a whole period; a person had to ask hermic to sleep again after each update); someone who wrote meanwhile keeps it up; always-on stacks untouched (`b0f3d44`)
- Changelog: a2220bd deployed (long-tasks skill, smaller tool results in context) (`c7ee419`)

## 1f7b20c — 2026-11-27

Image e3db380bd259. Replaces a2220bd. Some stacks were awake and update when idle.

- Long tasks go to a background subagent: delegate_task is no longer deferred (Hermes runs it in the background in gateway sessions; the result re-enters as a new message), the long-tasks skill sends research and multi-step work there and ends the turn at once; the waker counts a running subagent (manifest 'running', live transcript moved in the last 15 min) as busy, so a sleep or an update does not halt it (`1f7b20c`)

## a2220bd — 2026-11-27

Image 37f3b768d363. Replaces 8546675. Some stacks were awake and update when idle.

- Long tasks: a skill (long-tasks) and one SOUL line. A task over ~5 min starts with a plan (steps, times, where to check), runs its long part in the background so the chat stays free, reports each step, and ends with where to check; over the estimate it says why and asks. Research is capped at about 20 calls. The GPU is asked once per batch and released. (`a2220bd`)
- Smaller tool results in context: terminal 6000 -> 4000 chars, MCP results capped at 12000 (Hermes default 50000), web pages 5000 (our own earlier 8000 pin is lowered; a value the person chose stays); a review found 19- and 29-minute web turns with four compactions (`63293e4`)
- Changelog: 8546675 deployed (host-readable prefs, deploy boots are background wakes, worker-owned subtitle rounds, busy probes fail closed) (`21af161`)

## 8546675 — 2026-11-27

Image 070f33089413. Replaces ced968c. Some stacks were awake and update when idle.

- Waker busy probes: an unanswered probe is busy, not idle; a promised "done" notice holds the stop (`8546675`)
- subs-fetch --all refuses on a stack whose subtitle round runs on an always-on worker (`c979084`)
- Waker: a boot from a deploy, an update or a recreate is a background wake (`bedcf12`)
- Host-readable prefs: the gateway writes .prefs.json 0644, the waker treats an unreadable one as "critical" (`af4ca2c`)
- Zabbix fleet dashboard (provision.py fleet-dashboard): bridgeai problems, each GPU machine's card side by side, VRAM per service bucket, use outside the gate, heat; SVG graphs by item-name pattern, no item ids; the outside-the-gate items are renamed so the per-bucket pattern catches only buckets (`50c5797`)
- gtm: a GPU process that exited between the snapshot and the container lookup is marked gone, not taken for a host program: no false 'program on the host' finding, no VRAM counted for it (a recording folded after its service stopped showed every process as host) (`9dca466`)
- Zabbix templates: a trapper item's allowed senders are allowed_hosts in the 7.0 YAML (trapper_hosts is the API field, and configuration.import refuses it); fixed in the GPU usage, GPU heat and provider uptime templates and in the provider template generator; a selftest keeps it (`82f80c6`)
- GPU use in Zabbix: gpu_outside.py pushes once a minute (trapper, template "GPU host usage") the whole card and the use per bucket (each gate service, places, host, other; no process, container or person name), plus the outside-the-gate status, whose trigger pages instead of gpu_watch; three looks a minute apart before 'outside'; GPU_NO_GATE=1 for a machine with no gate; provision.py gpu-usage-host (`790eb27`)
- gpu_watch: one gate reachable under two host names (a renamed host whose old entry keeps the stacks' service tokens) is checked once, under the first name, so its alerts are not sent twice (`45d2fba`)
- gputaskman on the GPU hosts: per-process profiles in bench_gate (gpu_procs per job: container, program, peak VRAM, peak load per engine; the recording kept in ~/bench_gate/gputaskman) and a look every 5 min at GPU use that did not go through the gate (gpu_outside.py: a gate service running with no lease, an unknown container, a program on the host; two looks in a row before it counts), shown by the gate as fixed words and numbers in /state and alerted by gpu_watch as gpu-outside:HOST; names stay on the host (`f8dd23e`)
- Changelog: ced968c deployed (persist sync over NFS, telemetry by build, SOUL trims) (`138abd2`)

## ced968c — 2026-11-27

Image 95fca64b7e76. Replaces affd737. Some stacks were awake and update when idle.

- Persist sync-out over NFS: logs every 10 min (and on stop) instead of every 30 s, an unchanged directory is skipped (mtime/ctime stamp) instead of walked by cp -au, and an empty -wal no longer makes a .db look newer; the three always-loaded stacks were sending ~350 KB/s around the clock, enough to keep the Docker host from counting as idle (`ced968c`)
- Architecture: the 2026-11-27 decisions (always-on spaces over NFS, workers and the hub out of the bots, the agenda with its runner mark, quiet bots and verbosity, maintenance in the host's awake window, telemetry by build) (`17e2524`)
- Telemetry by build: each turn is stored with the image its stack booted (ops/wake/<stack>.booted_image), and 'telemetry.py builds' compares builds on real use (turns, failed and empty share, median seconds, stacks): the data for rolling out by build (`6616cea`)
- SOUL trims (195 chars of headroom): big downloads without the pip-era wheel and pin advice, a video's status from trabajos lista, a shorter Zabbix line; changelog: affd737 (agenda, scheduled runs, browse-page, worker notices) on every stack, the awake ones when idle (`44a213d`)

## affd737 — 2026-11-27

Image 96baa74c22ae. Replaces 8888e56. agenda (gateway agenda, refuses without a live runner mark), trabajos with scheduled runs, night search from the agenda, browse-page main content, worker notices, revista worker; 8 stacks recreated, disenador/hereug/hernik when idle.

- No silent agenda: the runner renews .agenda-runner in every workdir it reads; gateway agenda add refuses (exit 3, nothing saved, tells the bot to say the administrator must switch it on) while that mark is missing or older than 3 h; /avisos noche moves the night scan to the agenda only when the entry really exists, else the stack's own cron runs as before (`affd737`)
- Night job search from the agenda: /avisos noche (and the boot that follows it) makes sure there is an active jobnight entry in the person's agenda and names it in .worker-jobs, so the stack's Hermes cron stays paused and the Docker host is not woken at 04:30; other modes pause the entry; the night summary starts with '🕖 Programado · búsqueda nocturna de empleos' (`22fc9cd`)
- WORKERS.md section 11: the agenda runner; AGENDA.md: the runner is built; skills point to the agenda for revista, jobnight, subs (`b902a26`)
- workers: the agenda runner (agenda-tick) runs the person's agenda entries on the always-on space (`107c34d`)
- Maintenance in the host's awake window: the telemetry report covers the span since the last one (it now runs at irregular hours; the mark moves once the message is handed to notify, so a stopped run repeats a span at most once, never half); deploy_ops leaves alone the timers the host runs itself (ops/host-managed-timers, git-ignored) (`235518a`)
- browse-page returns the page's own content: the JSON-LD description, else the main/article block, else the body; 4000 characters by default, the whole text saved to /workdir/.browse/<id>.txt when cut; at most 40 unique links (a long job search filled a model's context with menus, side lists and footers); selftest (`dc4f02f`)
- recreate_hermes: a container that is missing for a moment (the waker recreating it, or a move to the always-on space renaming it for a minute) is waited for up to 90 s instead of failing the deploy and leaving the stack on the old image with no update note (`8e72c0d`)
- AGENDA.md: the runner contract for the always-on space; NOTICES.md: the scheduled-run header (`645f88c`)
- gateway agenda: the person's repeating tasks, run by the always-on space instead of a Hermes cron (`f170cf8`)
- trabajos: POSIX ledger lock and scheduled runs recorded from outside the bot (`0f2d156`)
- Revista: the message starts with '🕖 Programado · revista 07:30' so it is clear a schedule sent it, not the bot in a chat; the saved copy keeps the plain text (`fc45657`)
- Worker type revista: the morning magazine written on the always-on machine, so the Docker host is not woken for it (`5a82328`)
- HUB.md: running the hub on the always-on machine (data over NFS at the same path so no compose changes, any-hour window, no busy-hour limit, outbox credentials, timer moved off pve4) (`8246654`)
- Changelog: 8888e56 (locks across NFS) on herkos, hereug and hernik (`1ba9176`)
- backup-stacks: a stack folder that is an NFS mount lives in the person's always-on space, which backs it up there: skipped here with one line instead of being copied over the network every night; a stack with nothing local left is skipped (`6198945`)
- Worker notices reach the person: wake hook 60-worker-notices (ops/worker_notices.py) sends what an always-on worker left in /workdir/.worker-notices through the stack's own bot at the person's next Telegram message, moves each to sent/; at verbosity critical they are moved to skipped/ unsent; selftest (`fb8374b`)

## 8888e56 — 2026-11-27

Image 94ba3e7a36be. Replaces 9813b42. locks that hold across NFS (jobpush, subs-fetch, the workers' apply) for the stacks whose data lives in their always-on space; deployed to herkos (PASS), hereug and hernik when idle; the other stacks take it as latest on their move.

- subs-fetch locks hold across NFS: channel, slot and listing locks are POSIX (lockf) so the always-on worker and a hand run in the stack exclude each other; a held lock is tracked per process, since a POSIX lock never refuses its own process and any close of the file drops it (is_running never opens a lock this process holds) (`8888e56`)
- Locks that hold across NFS: jobpush and the workers' apply.py use fcntl.lockf (POSIX) for the files the stack and the night worker share; a BSD flock on the always-on machine and the stack's NFS lock never excluded each other; the selftest holds the lock from another process, as in life (`de09f5a`)
- canary-undo --restore works in place: the canary's own data becomes a tar beside the backup, persist is emptied and refilled, never moved or recreated (on a stack whose data lives in its always-on space it is an NFS mount) (`86ab942`)
- Changelog: 9813b42 (budget skill searches the guides first) on every stack, the awake ones when idle (`c0aa6b3`)
- Workers: local data mode (local_workdir) for a person whose workdir already lives on the always-on machine: no pull, push or ssh, the real folders are mounted and jobnight works in place as the stack's own cron did; only early-alert lines and subs notices go through apply.py, run locally; no chown of the person's files; host optional when every person is local; selftest covers it (80 checks) (`c11edf9`)

## 9813b42 — 2026-11-27

Image 9c5f9f6e78a9. Replaces 584a7ea. budget skill searches the guides first (budgetai tools/buscar.py, published to hertin and hernik); 8 stacks recreated, disenador/hereug/hernik when idle.

- Budget skill: search the guides (budgetai tools/buscar.py: the 1-2 sections that answer, with status and expiry) before any page; the index only when nothing matched; never a whole page into the conversation (`9813b42`)
- project_sync: the operator's stack always installs into user1-workdir (an empty stacks/hernik/workdir left from 11-11 would have taken the files) (`c14f4b3`)
- Changelog: 584a7ea (job check on the posting text, worker-held jobs stay paused) on every stack, the awake ones when idle (`3d57636`)

## 584a7ea — 2026-11-27

Image 33fd9a19d33b. Replaces b21cb01. job check reads the posting's own description; stacks keep jobs moved to an always-on worker paused (.worker-jobs); 7 stacks recreated, disenador/hernik/herkos when idle, hereug's recreate raced a waker start and was given the update note by hand.

- A job moved to an always-on worker stays paused in its stack (`584a7ea`)
- Always-on workers: subs and jobnight run on a machine that never sleeps (`f375c96`)
- Job check reads the posting, not the page: the board's JobPosting description first, then the main or article block, then the body; closed/blocked banners are still read from the whole page; more 'similar jobs' markers (a fitting 2D ad had been excluded for a 3D role in the page's side list) (`2d53ed4`)
- Changelog: b21cb01 (quiet bots, scripts accepted by default, keep-them-company rule) on every stack, the awake ones when idle (`67b654c`)

## b21cb01 — 2026-11-27

Image 8e33dba833f1. Replaces da62e13. quiet bots: verbosity per person, the nap line, reasons only at the detailed level (waker, already live); execute_code needs no approval anywhere (code_auto_approve); SOUL keep-them-company rule; gateway pref verbosidad; 8 stacks recreated, disenador/hereug/hernik when idle.

- project_publish: the selftests' local stand-in host is always awake (`b21cb01`)
- A nap, not machinery: a message that finds the bot asleep gets a playful 'I took a nap, back in about N s' at every level (it replaces the boot line); sleep reasons, updates and refreshes are named to the detailed level only; SOUL 'Keep them company': before a slow step, one plain line on what, what for and how long; the project publisher targets the Docker host and waits quietly while it sleeps (it pointed at the retired VM since 11-19, so jobfinder and budgetai had stopped reaching the stacks) (`f5ed3b4`)
- Quiet bots: a verbosity level per person (critical: no sleep/boot/ready/idle/cron notes; normal: as before; detailed: every sleep names what woke the stack and why it slept); background wakes leave the person's chat alone; execute_code needs no approval on any platform (patch code_auto_approve); NOTICES.md lists every message a person can get and its level (`d00f37d`)
- review_stack.sh: the file its output is redirected to is set to mode 600 (umask inside the script does not reach a redirect the caller opened) (`d17d90c`)
- Changelog: da62e13 (pack suggestions) on every stack, the awake ones when idle (`c009781`)
- Capabilities index: no Ghostscript in the image, so a PDF page becomes an image with pdftoppm (ImageMagick's convert fails on PDFs; the smoke check im-pdf-page-policy has failed for that reason on every image); two rows shortened to stay under the SOUL cap (`93cce7a`)

## da62e13 — 2026-11-27

Image 270f4d802dd4. Replaces c2d093b. pack suggestions: a message one of our off packs covers gets a note for the model (offer it, do not improvise) and a tip in the cloud question; the pack name is noted in the stack's own .sugerencias.jsonl (none under /compartir nada); 8 stacks recreated, disenador/hereug/hernik when idle.

- Pack suggestions: a person's message that one of our packs covers, with that pack off, gets a note for the model (offer it, do not improvise) and a tip in the cloud question (the home model may be enough with it); one line with the pack name in the stack's own suggestions file, none under /compartir nada; hints per pack in skill_packs.json, narrowed after a check on everyday phrases (`da62e13`)
- Changelog: c2d093b (sharing registry, submarine mode steps 1-2, both inert until switched on) on every stack, the awake ones when idle; KNOWLEDGE_GAPS.md: offer to connect missing knowledge, and gaps as suggested topics for the next packs (design) (`0c7a6a5`)

## c2d093b — 2026-11-27

Image efb5deb4bcb0. Replaces c9a1ff8. sharing registry (ops/sharing.py, review_stack.sh, chat_review --tester-since); submarine mode steps 1-2 (router local_only, gateway without Groq/Edge under it), off on every stack; 8 stacks recreated, disenador/hereug/hernik when idle.

- Submarine mode step 2: with local_only the gateway gives no Groq key (voice notes, bench, /estado) and speak refuses instead of using Edge voices; the web front's own Groq speech input and pinned cloud models are written down as still open (`c2d093b`)
- Submarine mode step 1: the router's local_only (home model or nowhere: no classification, no consent question, no cloud vision; a plain busy note when home cannot answer; wins over cloud_direct), reported by /router/state and /estado (smoke section 10b); telemetry knows the submarino route as a failed answer (`fd50c86`)
- Sharing registry: ops/sharing.py reads who is the operator, who is a tester and since when (ops/testers.json, git-ignored) with each stack's own choice; chat_review --tester-since reads nothing before that day; ops/review_stack.sh picks the flags so nobody types them; none always wins, an unknown stack is skipped (`448d15c`)
- Changelog: c9a1ff8 (vehiculos pack) on every stack, the awake ones when idle (`d78a830`)

## c9a1ff8 — 2026-11-26

Image db3124b90f33. Replaces 3279fa9. Some stacks were awake and update when idle.

- Vehiculos on main: its capability row; shorter wording of a few rows; the index and the SOUL no longer send the agent to pip or a venv (the image carries every library and a venv cannot be made there; a missing one is for the administrator); size cap 6900 (`c9a1ff8`)
- Vehiculos guide README: situation rows English-first, Spanish phrase in parentheses (`e2f9725`)
- Vehiculos pack: Argentine vehicles guide (law, fines, TelePASE, insurance, paperwork, trips, maintenance, VW Gol 1994), helper and skill (`dc92c51`)
- Submarine mode: the name, after a submarine's silent running, and the opposite of airplane mode (`19efca7`)
- Submarine mode (design): the whole fleet self-hosted only (router local_only as the mirror of cloud_direct, gateway STT/TTS without cloud steps, web tools refuse at once, egress allow-list at the Docker host, home models awake), how people are told before, during and after, and the drill (`6649142`)
- Data sharing: local versus third-party processing is the axis (where data goes, not who looks); once data leaves the building we cannot answer for it; answering is a separate purpose; open questions (answering already sends data out, reviews by a cloud coding assistant are third-party, weak anonymity with few testers, backups/logs/alerts, retention, court orders, the tester registry) (`5560453`)
- Data sharing: first-party (a local AI on our own machines counts as the operator) versus third-party AI (a cloud vendor: the 'AI' of the policy); essential technical data only by default (game start/stop, FPS, drops, latency, refresh rate, out of memory or disk), optional diagnosis chosen per kind and viewer, per bot or for all; the law and 'nothing personal passed on, except a court order' above any permission (`0b26d43`)
- Data sharing: finer choices per kind of data (text, voice, files, screen recordings, session metrics), viewer (nobody, AI only, human only, both) and purpose (fixing faults; training only with its own yes); AI-only material never reaches a human and graphic material is confirmed in neutral words without exposing the operator (design) (`6d6b440`)
- Data sharing: the testing-stage policy in the bot manual (es/ru/en: an AI from the major vendors reviews conversations to improve the assistant, keeps or hands over nothing, only anonymous conclusions; answering and reviewing are two different things; /feedback data none opts out) and DATA_SHARING.md (collection gated at the source, the levels, testers, places' sessions and metrics, choosing the level without the bot through the gate, the door and an MCP: design) (`bf0078e`)
- Changelog: 3279fa9 (chat-review fixes) on every stack, disenador, hereug and hernik when idle (`bff660b`)

## 3279fa9 — 2026-11-26

Image 675c3e64e7b4. Replaces 0c828a9. Some stacks were awake and update when idle.

- SOUL: the voice-note rule in fewer words (the longer one put the worst case over the 32000 pin) (`3279fa9`)
- Live location note: for how long until they get somewhere, run gateway mapa ruta from their newest point; never estimate distances from memory or an earlier answer (ETAs drifted 2-7 km within a minute) (`f31e851`)
- Voice notes: Groq's auto detection outside the people's languages (AIBRIDGE_STT_LANGS, es,ru,en) is transcribed again with the nearest one (Slavic -> ru, Romance -> es, else en): Russian notes came back as Serbian or Polish in Latin letters; SOUL: a quoted voice line is already transcribed, never transcribe it again nor say speech-to-text is down, a garbled one is the transcription mishearing (`b252e96`)
- trabajos selftest: a queued job's bound may read 'mañana HH:MM' (NOW is the real time; near midnight UTC the check failed) (`6e8fd16`)
- Selftests: a port for a server started in another process comes from outside the kernel's ephemeral range (bind(0) handed out ports the parallel tests' client connections also draw from: gate, vidgen and vidpost failed now and then in a full run) (`6706c15`)
- Places dedupe: a part whose shares the kernel refused is not written down as done; tried again in later windows, 3 times at most (`e7eb1cb`)
- Places dedupe: options by duperemove version; 0.13+ (whole-file hashes, so files the snapshots also hold are shared; read-only opens built in; no partial by default, PLACE_DEDUPE_PARTIAL=1) and 0.11 back to partial with fiemap (with nofiemap the kernel refused every share: Invalid argument, nothing shared in the first window of parts) (`18de3af`)
- Changelog: 0c828a9 (code_python) on every stack, disenador, hereug and hernik when idle (`1533583`)

## 0c828a9 — 2026-11-26

Image 8d345869dcd8. Replaces c305a50. Some stacks were awake and update when idle.

- Hermes patch code_python: execute_code runs the system Python (AIBRIDGE_CODE_PYTHON=/usr/bin/python3) with the image's office, PDF and image libraries instead of Hermes's own interpreter; tested offline in the real image: tool calls from the code and the session kernel's state still work (`0c828a9`)
- Changelog: c305a50 (mcp_parked_probe_cap) on every stack, disenador and hereug when idle (`f93b3fb`)
- Selftests: a test that fails among the parallel ones runs once more alone; passing then is FLAKY (printed, its parallel output kept in the git dir's selftest-flaky/, last 50) and does not stop a push; failing alone too is a FAIL (`202b2e3`)

## c305a50 — 2026-11-26

Image f963416be457. Replaces 07e8d85. Some stacks were awake and update when idle.

- Hermes patch mcp_parked_probe_cap: a parked MCP server is probed again every 5 min at most (AIBRIDGE_MCP_PARKED_PROBE_MAX_S), as on v0.21.6; v0.23 backs off up to an hour, too long for MCP servers on a GPU host that sleeps when idle (`c305a50`)
- Docs: Hermes v0.23.4 is the pin (what it changed for us: rollback by backup, settings we keep, lazy installs off, office libraries, resume patch, the prompt-cache warmer, the advisory that did not apply, fixed hostnames) (`aa86633`)
- Places dedupe: 8 GB parts and a memory guard (a part stops under PLACE_DEDUPE_MIN_AVAIL_MB, 4096, of available memory: an uncapped whole run reached ~47 GB of RAM and swap on a 32 GB host); 'a place started (or docker did not answer)' (`4e16423`)
- Compose: a fixed hostname per Hermes container (the stack's name, guest-NAME, hernik), as the canary stage sets, so the turn-lease patch reclaims a lease left by a kill during a recreate at once (`e2b89c5`)
- Places dedupe in parts: the same file of a game in every place is always in one part of at most PLACE_DEDUPE_CHUNK_GB (16); finished parts are written down (root-only, hashes only), so a window cut by its time goes on from there an hour later instead of starting from zero (a cut run never finished), and a game update redoes only that game; a fresh hash file per part as before (`bd5c2f9`)
- gateway_web selftest: the publisher's-word checks wait up to 30 s and pass under 20 (6 s with a 4 s bar failed under the full suite's load) (`850c84c`)
- Changelog: 07e8d85, Hermes v0.23.4 on every stack (disenador, hereug and hernik when idle) (`47d510e`)

## 07e8d85 — 2026-11-26

Image c3c44fbc82e5. Replaces 18bd9f9. Hermes v0.23.4 (was v0.21.6) on every stack; disenador, hereug and hernik update when idle. Backups of every stack taken right before (pve4 ~/backups, 1813).

- Hermes v0.23.4: python-docx, python-pptx and xlsxwriter by hash for the microsoft-office skill (it no longer builds a venv from the network), and security.allow_lazy_installs off (`63d7f1d`)
- admission_auto_resume real-code test on the v0.23.4 persistence layer (storage handle, admissions/messages repositories, ledger in state.db) (`57fe9e6`)
- Hermes v0.23.4: pin, vendored installer and every patch re-anchored (`c8c3d1c`)
- Changelog: 18bd9f9 (hereug, hernik and disenador when idle) (`7e66d07`)
- Hermes v0.23.1: a twice-lost turn sends one notice, not a second "Recovered reply" (`af96e74`)
- Hermes v0.23.1: resume round 2 (boot notice, one note naming the tool, text once) and no lease stall after a restart (`891a2cf`)
- Hermes v0.23.1: a turn lost to a restart resumes by itself again; router handles stamped web turns (`ae33497`)
- Hermes v0.23.1: re-anchored patches, write-safe patching, vendored installer (`6b2ec4b`)

## 18bd9f9 — 2026-11-26

Image c89b3d907330. Replaces 09cda2d. Deployed to hereug, hernik and disenador only (awake: they update when idle); the other stacks get it with the next deploy.

- Image: openpyxl 3.1.5 (and et-xmlfile 2.0.0) by hash in the system Python, for Hermes's bundled xlsx skill in the oficina pack; the build writes and reads back a workbook, the smoke imports it (`18bd9f9`)
- Changelog: 09cda2d (8 stacks now, disenador, hereug and hernik when idle) (`fbbfb17`)

## 09cda2d — 2026-11-26

Image d6bfe351ec74. Replaces 2cc1992. Some stacks were awake and update when idle.

- Pipeline: the smoke stage finds its baseline tar again (`grep -v -e -- "-dirty.tar$"` took `--` as the pattern and the next one as options) (`09cda2d`)
- Image: yt-dlp back on the stable channel, 2026.11.23 (YouTube STS workaround, ios_producer client, web_embedded policies; newer than the nightly 2026.11.20.232656 it replaces) (`e78522c`)
- Places: dedupe without fiemap (every extent is also shared with the place's own snapshots, so duperemove skipped them as done: the first run shared 1.7 GB of 10.6 GB) (`ea2d338`)
- Places and gate: the machine's own profile (card, VRAM, driver, ray tracing from the card's own Vulkan section, CPU, RAM, places disk; refreshed hourly in the gate's tick), the games installed per place (place.py inventory, root, written daily and before the host sleeps; robust to a person's own files, at most 500 per place, written under a lock), 'needs' in the game profiles and which games fit this machine; all in the operator's /host/overview; the open LAN page shows only how many games each place has, never which; reviewed (`ffc49d5`)
- Places: shared game files (place.py dedupe): identical game files of 1 MB and up stored once on disk with duperemove (reflinks, block matching, read-only opens, a fresh hash file per run), only with every place stopped the whole run (a place that starts stops it within 2 s); it runs in the GPU host's new 'before sleep' window (gpu-host-sleep before.d: tasks run only when the host is about to suspend; a long one makes it check every reason again before sleeping), never wakes the host, does nothing when no game changed; reviewed adversarially (link races, stale hash paths, extent-only matching, fail-open checks) (`b93ee1b`)
- Places: each place runs as its own uid (3001 + port slot, host account place-NAME without login) instead of 1000, the operator's own account on the host: set-uid moves a place (only uid 1000's files, find -P -xdev, under the gate's lock, recreate in the same lock), input/output keep the gate's group with setgid and umask 002 so the gate still uploads, reads and deletes there, execs use the uid by number, restore re-owns files from older snapshots; all of ~/.cache is now a local cache (out of snapshots and any sync); the gate checks the library mount point only when a library is mounted; reviewed adversarially (`ccc7cf1`)
- Changelog: 2cc1992 on every stack (`2541e92`)
- Firewall: a guest stack may talk to its own containers on its own bridge (brain to its Telegram Bot API, web to brain): once br_netfilter is loaded (any network made with enable_icc=false), same-bridge frames went through DOCKER-USER and the guest DROP cut every stack off from its own Telegram; traffic between two stacks stays dropped (`18e2191`)

## 2cc1992 — 2026-11-26

Image 8f690c369162. Replaces 65e439a. all stacks (awake ones applied by the waker when idle): no desktop watch job, expired jobs do not keep a stack awake.

- Docs: opening a place from the bot on the best host (needs, who else uses each host, where the person's data is, wake cost, warm caches; the machine-power provider's machines as more hosts), and the traffic between hosts measured per place (only the person's data travels: first copy once ahead of time, then incrementals; LAN direct, internet only inside WireGuard with ssh, compressed and rate-limited; a week of measurements decides) (`2cc1992`)
- Places: an old cache folder in the home that the person's uid cannot delete (left root-owned by a program run as root in the place) is removed by root, only under the lock, with find -P -xdev (`6a4fb98`)
- Waker and gateway: the waker tells the wake service when it takes a person's message after a host wake (/posta, so its 'waking the server' notice goes away by event); registered jobs past their own timeout no longer keep a stack awake; 'escritorio abrir' registers no watch job any more (the gate sends the warnings through the wake service), and drops one left by an older version (`133e3cb`)
- Places: GPU shader caches local to each host (place.py hostcache): hostcache/NAME mounted once at /hostcache, outside the person's home, and links at the usual paths in the home (NVIDIA, Mesa, every Steam library's shadercache, Heroic prefixes), moved there once as the person with a reflink copy; not in snapshots, never backed up or sent; emptied on a GPU or driver change (never on an nvidia-smi failure); recreate holds the lock the gate honours and rechecks the place is stopped; the gate and recreate refuse a SteamLibraryExtra that is a link; shared libraries left alone; reviewed twice adversarially (`9fbac22`)
- Changelog: 65e439a for the operator's stack (gateway lan, /estado with the LAN summary) (`d185d47`)

## 65e439a — 2026-11-26

Image 0ef318e84f1d. Replaces 2f20b46. hernik only (applied by the waker when idle): gateway lan and the LAN summary at the end of /estado.

- Docs: games installed per host only where the hardware meets their needs (checked before the install, inventory read from the host), the person's data and Proton prefixes synced from the copy used last, GPU caches local and never backed up at the same paths; btrfs hardlinks stay inside one subvolume (libraries go to 'library', reflinks elsewhere) (`65e439a`)
- Docs: one place on more than one GPU host (one active copy with a lease, incremental btrfs send from the copy used last, split brain kept apart instead of merged, GPU shader caches in a nested subvolume that send and snapshots skip, host hardware profile and per-game needs such as ray tracing, settings per hardware class, build order) (`4be22bd`)
- Overview, door and bot: the bots' host stacks in the LAN overview (a read-only, LAN-only /__wake/all listener in the waker with an allow list; never asked while that machine sleeps), /estado in the operator's bot ends with the LAN summary (gateway lan: machines, desktops, bots, game servers, alerts), the door shows 'playing now' per game server (players and map, bots apart, cached 15 s, never blocks); maintenance page at the door (nginx flag); review fixes: queries in parallel and unknown machines never asked, UDP sockets connected, numbers type-checked (`b379911`)
- Docs: every state of the machines, the places, the bots and the game servers (with diagrams, what is built), how games are shared (own account and copy, own library, identical large files hardlinked on one btrfs disk, updates and uninstall), and the idea of rotating the places' internal password (`297c65c`)
- Places migration: look inside an NTFS partition with the ntfs3 driver first (a bare mount tried the old ntfs type and the look failed) (`937d262`)
- Places: btrfs snapshots (place.py snapshot|snapshots|restore|prune, 7 days, daily timer; restore locks the place against the gate, keeps the place's own settings and token, records whether a snapshot is clean or crash-consistent, keeps the old state if anything started during the swap) and the migration to a btrfs disk (migrate-places-btrfs.sh prepare|copy|switch with a runbook: only an empty or NTFS partition is formatted, copies keep owners, hardlinks, xattrs and sparse files, the old folder is kept for rollback); reviewed adversarially, 13 fixes with tests (`6e16e0d`)
- Overview: the operator's LAN page (every machine awake or asleep, every desktop place with watchers, game, countdown and resources, every game server with map and players through Quake III's getstatus); read-only, stdlib, the gate's host token as a systemd credential (`fc740ea`)
- Gate: /host/overview for the operator (the machine's load and every place: state, watchers, sound, open game, countdown, CPU, memory, VRAM; from the last tick, names and numbers only); the game check runs without the timeout wrapper, whose command line held the pattern and made pgrep find itself (every running place looked like it had a game open) (`62d2ddd`)
- Gate: every command run inside a place carries its own timeout, so a request that gives up never leaves a process running in the place (a listing ran 26 minutes at full CPU and kept the place 'busy') (`90997a1`)
- Changelog: 2f20b46 (hernik, applied by the waker when idle) (`c960855`)
- Games: a Control profile (Epic through Heroic with Proton Experimental, ProtonDB platinum, tested: plays well); the Quake profile's detect pattern matches '. ioquake3' like the gate's (`de621b4`)

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

