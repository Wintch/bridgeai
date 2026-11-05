# The hub: a collector that works while people are away

Status 2026-11-05 (end of day): **installed on VM105 and proven live** with hernik: the container (hardened, exits by itself), the two security sources, an RSS feed shared by two people
(one fetch), the admin-bot message crossing container -> host -> bot, the read-only `/hub` and `/hub-shared` mounts, `hub status/feed/requests` from inside the stack, and the module loop
(a source refused for lack of a module, the request, the admin message, the approval). **Not live yet:** YouTube (waits for the canary of `HERMES_ARCHITECTURE.md` item 104), the shared job fetch
(`jobfetch`: needs the fetcher checkout and a Chromium test, below), summaries, and the other three stacks (not attached). `modules.json` exists: a stack attached from now on has NO module until
`ops/stack_modules.py add`. The commit that carries all of it is in git history under "The hub".

## The problem

Polling is the same work for every person (the same YouTube channel, the same news feed, the same job boards) and it does not need a
person, a model or a Telegram chat. Today each stack does it for itself: the subtitle backlog runs inside hernik's container, every stack
would run its own job scan, and the site's rate limit is one for the whole VM address while every stack fights it separately (the soft block
of 2026-11-05, items 102 and 104). Meanwhile a stack that has to be awake to poll cannot sleep.

## The shape

```
          quiet hours, host timer (every 15 min)             a person's stack wakes (any hour)
 hub_start.py ── due? window? memory? ──► hub container ─┐          ┌── hub feed / show / subscribe ──┐
   (host, nothing started if nothing due)     │ fetch, excerpt, summarise (optional)                   │
                                              ▼                                                        │
  hubdata/people/<p>/  feed.db  feed.json  requests.json  full/<item>.txt   ──(read-only mount /hub)──►┘
                       inbox/ ◄──(the only writable mount, small JSON files)── person's stack
                                              │ exits when nothing is left (container is gone: that IS "se baja")
```

- **One collector container for everybody** (`aibridge-hub`), never "up": `docker compose run --rm`, started by a host timer, exits by itself.
- **The people's stacks only read files.** Each stack mounts its own folder `hubdata/people/<name>` at `/hub` read-only, and its `inbox`
  subfolder writable. They never talk to the hub over a network, and the hub does not need to be running for them to read.
- **Expanding an item is a local read.** The feed carries the title, link, excerpt and summary; the full caption text of a YouTube video is
  a hardlink in `/hub/full/`, and the person's own agent (their key, their model) works on it ("ampliar" costs the collector nothing).

### Who manages it: not Hermes

You said "lo maneja Hermes seguramente, propone mejor opción". My proposal is that **Hermes is the front door, not the engine**:

| | Hermes (agent) in the loop | deterministic collector + host timer (chosen) |
|---|---|---|
| tokens | every poll is a turn | zero; the LLM is used only for optional summaries of public text, in batches |
| sleeping stack | a Hermes cron cannot tick while its stack sleeps (the waker has to wake it) | the hub is its own container, nobody else wakes |
| reliability | "the model says done without doing it" (three times, see "Things learned") | a script either did it or logged why not |
| one address, one rate limit | N agents, N cooldowns | one process, one cooldown file, one place to be polite |
| fits "se baja si no hay tareas" | needs idle detection | exits when the queue is empty; if nothing is due the container is never started |

Hermes still does what it is good at, through the `hub` command (`SKILL_hub.md`): the person says "seguí este canal", "qué hay de nuevo",
"ampliame ese", and their agent runs `hub subscribe / feed / show --full`.

### Why files and not an API

The stacks live on isolated networks (internet only, no LAN, no other stack). Giving them a route to the hub would be a new firewall
pinhole per stack plus an authentication scheme, and it would still need the hub awake at the moment the person asks, which is the
opposite of the goal. A read-only bind mount needs no network, no token, and works while the hub is down.
SQLite files are published whole and replaced atomically (`feed.db`: rename), and the client opens them `mode=ro&immutable=1`, so the read-only
mount (which cannot hold SQLite's journal files) is fine.

## Two kinds of work, one scheduler

The point is to save the person's time: when their bot wakes, what they asked for is mostly already there, gathered at night while their stack
was off. The hub does two kinds of work, in one ordered queue:

1. **General work, nobody asked for it** (`system.json`, written only by the operator: no stack mounts it). Today: `security` (new Debian security
   advisories for packages installed in the image: the hub runs the same image as the stacks, so it knows what is installed; and a newer yt-dlp than the
   pinned one). Next: the general job scan (jobfinder session). Findings go to **the admin bot only** (`🛡️ ... novedad(es)`), through the host
   (the container has no token: it leaves lines in `state/admin-outbox.jsonl`, `hub_start.py` sends them with `ops/lib/notify.py` every 15 minutes).
   The first look at a source is a baseline: old advisories are stored, not announced (a newer yt-dlp is, because that one is actionable).
   Things a container cannot see, the host starter checks once a day inside the window: the VM's own pending security updates (`apt list
   --upgradable`, no sudo) and a pending reboot, as a ✅/alert pair.
2. **Work for people** (`hub subscribe ...`): the same sources, requested by a person, collected once however many follow them, published to
   their feed. The "resumen que pidió" at wake is then a read of the feed (SKILL_hub.md tells the agent to run `hub status` and `hub feed --new`
   first), not a poll.

**Order inside a run:** a source nobody has collected yet (a person is waiting for the first items), then by the kind's priority (security 10,
feeds 30, YouTube 60: cheap and urgent before the slow download), then whoever waited longest. **Load:** the host starter does not start the hub
under `HUB_MIN_AVAIL_MB` or with more than `HUB_MAX_AWAKE` Hermes awake; the operator hears once ("🌙 El hub tiene trabajo pendiente pero no corre: ...")
and gets a ✅ when it runs. A run that is already going checks memory between sources (`HUB_MIN_AVAIL_RUN_MB`, 1200) and, if it fell, stops, publishes what it
has and says "se durmió por carga". The timer is the cron; `HUB_WINDOW` is the quiet window. All hub messages go to the admin bot for now: nothing is sent to a person.

### What goes in the hub and what stays in the person's own poll

A moving line, decided case by case. The rule of thumb: it moves here when several people (or nobody, but the operator) want the same public thing, and
it gains from quiet hours; it stays in the person's own stack when it needs their identity, keys or private criteria, or when running it centrally
saves nothing.

| What | Where today | Why |
|---|---|---|
| YouTube channels, news feeds | hub (new), hernik's backlog still the old way until the canary of item 104 | shared sources, one rate limit for the address |
| security advisories, new yt-dlp, host patches | hub / host starter, to the admin bot | general, nobody should have to ask |
| general job scan (the fetch) | hub: `jobfetch`, `hubdata/shared/jobs-http` | the same boards for everybody; readers parse the kept answers |
| a person's own job triage (their requirements), `jobpush` | the person's stack | needs their criteria and chat; moves only if it proves to save time |
| per-person background jobs ("por rama") | the person's stack | nothing shared to save |

## The job scan: one fetcher, everybody's scans read what it kept

Built on the jobfinder's own design (`docs/SHARED_FETCH.md` in the jobfinder repo) and the operator's decisions of 2026-11-05.

- **The fetcher is a `system.json` source**, `{"kind":"jobfetch","key":"union"}` (optionally `"params":{"profiles":[...]}`: a baseline profile of the operator's own, so the
  general scan runs even if nobody asked). Once a day, in the quiet window, it builds the union of the profiles, runs `scan.mjs` over it with the jobfinder's own
  cache pointed at `hubdata/shared/jobs-http`, and writes `.fetched` (when, TTL 30 h, how many profiles: nothing about who). It runs the hub's OWN jobfinder checkout
  (`hubdata/fetcher`, installed by `ops/hub_fetcher_install.sh` from a bundle of the clean system layer), never a person's copy.
- **A person asks with a profile, not a portals.yml**: `hub jobs-profile --regions ar,latam --sectors tech [--remote ...] [--roles ...]`. The words must be ones the
  catalog really has (`hub jobs-profile --list`); the fetcher builds the employer list with `select-portals.mjs` from the operator's catalog, so no person can make the hub
  request an address of their own. (A person's own extra entries and `job_boards` keep running in their own scan: `select-portals` selects employers, not boards yet.)
- **Readers:** `hubdata/shared` is mounted READ-ONLY at `/hub-shared` in every stack (a reader must never prune it; the cache would try). `jobpush` uses it only while the
  marker is fresh (`use_shared_store`): cache-only, no requests to the boards; a stale or missing marker (the fetch failed, the hub is not installed) = the scan runs as
  before. `jobpush.log` records `store=shared|own`.
- **`no-store`: kept, fetcher only** (`HUB_JOBS_STORE_NO_STORE=1`, 0 turns it off). Workday's public job list is the biggest cost (one board = 559 requests).
- **Egress is not blocked, it is measured.** `docker-user-fw.sh` works by address ranges and the ATS hosts sit behind CDNs; a domain allowlist would need an outbound proxy
  and would break the people's normal browsing. The sites see the VM's one address either way, so what matters is the total of requests: a reader prints how many requests
  were not in the store, and `--verify` and liveness are dozens a day per person. If that is too much they move into the hub (verify the union of new postings once).
- **Open, jobfinder side:** (1) `select-portals --boards` so a profile can cover boards too; (2) a switch for `union-portals` that leaves out requests built from title keywords
  (decision: keep them out of the shared store; `HUB_JOBFETCH_UNION_ARGS` passes it through once it exists); (3) Bumeran/ZonaJobs (`scan-navent`) stay targeted per person and
  `scan-ats-full` should run once per machine on the union, with its results in `shared/` for readers to filter: neither is in the store yet.
- **Not tested here:** a real `scan.mjs` run (needs the network, ~an hour cold); the fetcher's Chromium under the hub's `cap_drop ALL` (scan-navent launches it without
  `--no-sandbox`: try it on a throwaway container first). `select-portals` and `union-portals` were run for real through the collector in a temp copy of the jobfinder.

## Modules: each person has only what they need

Not everybody needs everything: jobfinder for the one who is looking for work, budgetai for the one who wants it, YouTube channels or news feeds for the ones who follow them.
The catalog (`hub/modules_catalog.json`: jobfinder, budgetai, youtube, news) says what each module covers: the kinds of source they may subscribe to, the other requests the hub accepts
(`jobs_profile`), and the shared project it goes with. **Who has what is `hubdata/modules.json`**, written only by `ops/stack_modules.py` on the VM (no stack mounts it):

```
ops/stack_modules.py init                  # once: everybody already attached keeps everything they can do today
ops/stack_modules.py remove <p> news youtube ...   # then take away what they do not need
ops/stack_modules.py add <p> jobfinder     # switch one on (a module with a project reminds you of the second step)
ops/stack_modules.py list | pending
```

- **The hub enforces it.** A subscription of a kind the person does not have, or a job profile without `jobfinder`, is refused with "the module «x» is not switched on for you: hub modules request x". The
  shared job fetch only covers the profiles of people who still have `jobfinder`. Without `modules.json` nothing is restricted (how it was before); a file that cannot be read gives nobody anything and
  alerts the operator.
- **The person can ask**: `hub modules` (what is on/off) and `hub modules request NAME`. The request stays pending, the admin bot says "🧩 <person> pide el módulo «x»" with the exact command, and when
  you switch it on the person's request turns ok at the next run. Nothing is switched on by the person alone: a module may install code in their workdir.
- **The hub does not install projects.** For jobfinder and budgetai the second step is adding the stack to that project's `"stacks"` list in the desktop's `projects.json` so `ops/project_sync.py` puts it in their
  workdir (the jobfinder's daily check then creates itself at the stack's next boot, paused until the person chooses `/avisos`). `remove` stops the hub side only; their project files and data stay.
- **Skills are the same in every image**, so the `hub` skill tells the agent to offer only what `hub modules` shows as on.

## Security and privacy model

- **A person's request is data, never code.** A request names a `kind` and a `key`; the collector of that kind validates the key
  (`canonical()`: YouTube channel URLs only, RSS addresses that resolve to public servers only) and builds every path and command itself. Request
  files are read without following symlinks, capped at 4 KB, JSON only, at most 100 per person per run, at most 30 subscriptions per person.
- **The hub never mounts a person's workdir, keys or Telegram token** and executes nothing that came from a person. (This is why the
  job scan will use hub-owned code with the person's portals as data, not the person's own copy of the jobfinder: a prompt-injected agent
  could plant a script there.)
- **People cannot see each other.** Each stack mounts only its own folder; `feed.db`, `feed.json` and `full/` contain only that person's
  subscriptions. The shared store (`store/`) and the private database (`state/hub.db`) are not mounted into any stack. Shared sources are
  collected once (two people following the same channel = one source), the per-person files are hardlinks.
- **Failure reasons stay with the operator.** A person sees "failing" on a source; the error text is in the hub log and `hub.py status`.
- Container: read-only rootfs, `cap_drop ALL` (+CHOWN, DAC_OVERRIDE, FOWNER), no-new-privileges, 1.5 GB, 1 CPU, 512 pids, a network in
  172.28.0.0/16 (internet only, per `docker-user-fw.sh`; no pinhole needed).
- Summaries (optional) go only through the `HUB_LLM_*` endpoint and only carry public material (captions, news): privacy class A, never a
  person's chat. Text from a feed or a video is told to the model as data to summarise, not instructions.

## When it runs

`hub_start.py` (timer every 15 minutes) starts the container only when ALL hold: it is not already running; something is due (`state/next-wake`
reached, inside `HUB_WINDOW`, default 01:00-07:00 local) **or** a person's request waits in an inbox (any hour, at most one run per 10
minutes, and then `--only-new`: just the sources never collected, so a new subscription gets its first items fast without waking
every old source); the host has `HUB_MIN_AVAIL_MB` (2500) free; at most `HUB_MAX_AWAKE` (2) people's brains are awake. If not, it exits
saying why. A run takes at most 90 minutes of starting new sources, then publishes and exits.

Per source: YouTube every 3 h, RSS every 2 h. A failing source backs off (interval x2, x4 ... up to a day). A rate limit
(`subs-fetch` exit 75, or HTTP 429/503 from a feed) pauses **the whole kind** for as long as the site asked (YouTube: `subs-fetch`'s own
shared pause, extend-only, 3 h for a soft block); the other kinds keep going. YouTube collection reuses `subs_fetch.py` unchanged, so every
anti-block rule of items 102 and 104 (2 slots, `NocapGuard`, the `.nocaps` ledger) applies inside the hub.

## What a person sees

`hub status`: what they follow, unread counts, when each source was last looked at, and **"N checks without anything new"** (the manifest keeps
`last_new` and `checks_since_new` per source: the data for the "no encontré nada desde las X" summary, see below). `hub feed --new`,
`hub show ITEM [--full]`, `hub read`, `hub subscribe youtube URL --captions es-orig --lang es`, `hub subscribe rss URL`, `hub unsubscribe`, `hub requests`.
Read marks live in the person's own workdir (`/workdir/.hub-read.json`): the hub never learns what was read.

## Installing (operator, in this order)

1. Tests: `ops/run_selftests.sh` (includes `hub_selftest.py`).
2. Collector on the VM, dry run then apply: `AIBRIDGE_HOST=... ops/hub_install.sh` / `--apply`. It copies `~/aibridge/hub/`, creates `hubdata/` and
   `hub.env` (a reserved /24, empty LLM settings), installs and starts `aibridge-hub.timer`. With no subscriptions the timer starts nothing.
3. Image: `docker compose build hermes-agent` carries the `hub` command, the skill and the new `/hub` mounts (they already come with the
   compose changes in `docker-compose.yml` and `stacks/docker-compose.stack.yml`; stacks that are not attached mount an empty folder).
4. Per person, on the VM: `ops/hub_attach.sh <name>` (**re-run it after every recreate of that stack until the image is rebuilt with the `hub` client**: the client is copied into the container, and a recreate from the old image throws the copy away, found 2026-11-05) (creates their folder, `.attached`, `HUB_DIR`, copies the client into the container, asleep or not),
   then `ops/recreate_hermes.sh <name>` while the stack sleeps.
5. Choose the person's modules: `ops/stack_modules.py init` (first time only), then `add <name> <module>` / `remove <name> <module>` (see "Modules"). A newly attached stack has none until you add them.
6. First test with ONE source: `hub subscribe rss <feed>` (YouTube only after the canary), then on the VM
   `docker compose -p aibridge-hub -f hub/docker-compose.hub.yml --env-file hub.env run --rm --name aibridge-hub-run hub run --only-new` once by hand (the `--name` goes BEFORE the service), then `hub feed`.
   If a source failed and is backing off, `... hub retry` makes the next run try it again.
7. Optional summaries: fill `HUB_LLM_*` in `~/aibridge/hub.env` (see "Open decisions").
8. The shared job fetch: `ops/make_jobfinder_bundle.sh` on the desktop, `ops/hub_fetcher_install.sh <bundle>` on the VM, add `{"kind":"jobfetch","key":"union"}` to `hubdata/system.json`.

What the first real run taught (all fixed, listed so they are not rediscovered): the live Debian feed is `/security/dsa`; a Docker tmpfs is `noexec` by default and yt-dlp (PyInstaller) cannot start from it, so the
hub's `/tmp` is `tmpfs ... exec`; the VM's compose files are behind the repo, so `ops/hub_compose_patch.py` inserts only the hub's mount lines (a `.bak-hub` copy is kept); a sleeping stack makes
`docker exec` fail, so requests to it are written straight into `hubdata/people/<name>/inbox`.

Operations: `docker compose ... run --rm hub status` (no network), `systemctl --user list-timers aibridge-hub.timer`, `journalctl --user -u aibridge-hub`.

## Adding a kind (the job scan, news with full text, ...)

Subclass `hubcore.Collector` in `collectors.py` and add it to `registry()`: `canonical(key, params)` validates what a person typed (the only code
that sees it) and `collect(ctx, source)` returns items (`ext_id`, `title`, `url`, `excerpt`, optional `fulltext` = a path under `store/`, `duration`).
Raise `Throttled(minutes)` to make the whole kind wait. Then add the kind to `hub_client.py`'s `subscribe` choices and the skill. Item ids are
global (`<prefix>:<id>`), so give them a salt when two sources can carry the same thing (RSS does).

## Not built yet

- **The job scan beyond the fetcher:** boards in profiles, the keyword-provider switch, `scan-ats-full` and Bumeran in the hub (see "The job scan" above for what is open). What this framework already gives it: per-person sources, hub-owned code with
  the person's portals as data, a long run budget inside the quiet window, a "found something" signal in the feed. Open: where the person's
  portals and requirements live (the hub needs them as data, from the inbox), and how triage by the person's own requirements is split.
- **Telling the person** (everything above goes to the admin bot only, by decision). When it is time: (a) "found something" at once, (b) quiet when nothing,
  (c) one wake summary "no encontré nada desde las X" with how many checks ran. The data is in `feed.json` (`last_new`, `checks_since_new`, `generated_at`). Delivery needs a host-side step after each run that
  reads the manifests and sends through the person's own bot the way the waker does (`tell_person`), plus a wake hook in `ops/wake/on_wake.d` for
  (c). Not written: it depends on the jobfinder session and on hereug's bot.
- **Migrating hernik's subtitle backlog.** hernik's `/workdir/descargas` (about 4,000 videos left after the soft block) keeps running the old way;
  moving it means pointing the hub's `store/youtube/` folders at the same files and retiring the `subs-nuevos` and `resumen-subs` crons. Not before
  the pause ends and the canary of item 104 passes: the hub must not hit YouTube from this address until then.
- **Garbage collection** of sources nobody follows any more (their items stay in `store/`; the hub just stops polling them).
- **Full text for news.** RSS items carry the feed's own text only; `hub fetch` on such an item says so.

## Open decisions for the operator

1. **Who pays for the summaries?** Optional and off by default (items then carry a 6,000-character excerpt spread over the whole video, and the person's agent
   summarises, as `subs-digest` does today). If on: one summary per (item, language) for everybody, through one endpoint of your choice (a free
   tier is enough at this volume: about 40 a run).
2. **Quiet window.** Default 01:00-07:00 server local time; requests from people bypass it for new sources only.
3. **Pre-armed or on request** (your own question from the job-scan idea): nothing is pre-armed in this slice; a person's agent subscribes when asked.
