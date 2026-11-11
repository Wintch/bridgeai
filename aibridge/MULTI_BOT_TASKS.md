# Several bots for one person, and a task board between them

Status: the board command (`aibridge/tareas.py`), the task receiver (`ops/wake/tareas_hook.py`), the config sync (`ops/gateways_sync.py`) and the board
setup (`ops/tareas_setup.py`, runbook `ops/TAREAS_SETUP.md`) are built; sections 3, 4 and 10.3 say where. The key pool of section 9 (the table there
marks what exists and what does not) and the roles of sections 10 to 21 are design.

Scenario: one person has several bots (for example accounting, social media, job applications, website design), the bots hand work to each other, a
local Gitea records who asked what and what was done (mostly text and code), and a bot can be handed over to another person who drives it from then on.
Later sections add roles (developer, marketing, designer, datamanager), two Zabbix-connected bots, the rule that only Telegram counts as human approval,
and time-locks for dangerous operations.

Reused, not repeated: `CAPABILITIES.md` (what crosses between agents: `hermes peer`, minimum data, untrusted answers), `WEB_REVIEW_LAYERS.md` (git hand-off,
reviewer stacks, human merge), `INTEGRATIONS_MAP.md` section 3.1 (own gateway command over a vendor MCP), `DATA_LAW_AND_KEYS.md`, `GENERATIVE_SAFETY.md`,
and in `HERMES_ARCHITECTURE.md` the waker, the RAM guard, `stacks.json` and `gateway web`.

## 1. The model

**One stack per bot role.** Today the unit is "one Hermes per person". A person with four roles gets four stacks (`<person>-<role>`),
each with its own memory, files, skills pack, model route and Telegram bot (its own BotFather token). This is not a new kind of object:
the waker, `provision_stack.sh`, `stack_modules.py` and the backups already work per stack. A role bot that nobody talks to for days is
just a sleeping stack (section 8 has the RAM numbers). Four bots in one Hermes would share one memory, which is exactly what the
privacy walls in section 5 forbid.

**Two kinds of person per stack.**

| | Owner | Controller |
|---|---|---|
| How many | exactly one | zero or more |
| Telegram | their id is in `TELEGRAM_ALLOWED_USERS` and is the one stored as owner | ids in `TELEGRAM_ALLOWED_USERS` (already a comma list in our scripts) and in a new `controllers` list |
| Talks to the bot, gives it work, approves its risky steps | yes | yes |
| Sees the board of this bot, approves merges of this bot's repo | yes | yes, only this bot's repo |
| Keys page, `gateway servicios guardar`, Telegram bot token | yes | no |
| `/compartir`, `/opinion privado`, `/dormir`, adding or removing a controller | yes | no |
| Export or wipe of memory and files | owner (through the operator today) | no |
| Hands the bot to somebody else | yes | no |

Hermes itself has no roles: every allowed Telegram id is an equal. The owner-only column therefore needs a small change to
the controls plugin: it reads the owner id from the stack's config and refuses owner-only slash commands from any other id. The keys page
is a separate web login that controllers are never given. Two limits to say out loud, because the manual already says similar things about the operator:

1. A slash-command gate is not a wall around what the bot knows. A controller can ask the bot what it remembers and it will answer.
   The only real wall is what the bot holds. That is why handover (section 6) starts by cleaning the bot.
2. Telegram group chats were never tested here (see `HERMES_ARCHITECTURE.md`), so a controller means a second private chat with the bot,
   not a shared group.

**Whose keys a bot uses.** The rule stays: a key is personal, the person loads it, and only that person's Hermes stacks use it
(`CAPABILITIES.md` rule 1; the repo ships no keys). Policy: the bots of the SAME person may share that person's keys,
but each bot gets only the keys its role needs (section 9, design only). A key never crosses from one person to another. So a handover has two modes:

- **Ceder (give).** Ownership moves. The old owner's keys are removed from the bot (the exit flow of `DATA_LAW_AND_KEYS.md` B.5, keys part only; in the
  pool design of section 9 this is: empty the stack's `keys` allowlist and run the sync, which deletes every owner key from its `.env`), the new owner loads
  theirs on the keys page, and creates their own Telegram bot. A handed-over bot gets no owner keys, ever. Nobody ever holds the old token, and the old owner revokes it with `/token`.
  This is the default and the only mode that follows rule 1 with no interpretation.
- **Prestar (lend).** The owner stays the owner; a controller drives the bot on the owner's keys and quota. The bot holds only the keys its role needs
  (section 9), the controller cannot read them, so the key is not lent, the bot is. Whether this reading of rule 1 is acceptable is the operator's call.
  If accepted, the owner sets a spending cap at the provider first (their own keys, their own risk), and the controller learns in the first
  message whose quota this uses.

## 2. The task board in Gitea

**Layout, per owner.**

- One Gitea organisation per owner (`<owner>`), private. Humans are in it as users (owner and controllers, one account each, created by the operator).
- One repo per bot (`<owner>/<role>`): that bot's code and text work (the design bot's repo is the site repo of `WEB_REVIEW_LAYERS.md`; accounting holds
  templates and reports it chooses to keep; none holds secrets, per `security/policies.md`).
- One repo `<owner>/tareas` for the owner's cross-bot work: tasks that concern no single bot, or that a person files for several.
- **Recommended refinement:** a task for bot X is an issue in repo X, not in `tareas`. The inbox is the bot's own repo. That makes the handover a repo move
  with its history intact, and it keeps a controller of the design bot from reading accounting requests, which a single shared `tareas` repo could not.
  `tareas` then holds the owner's own overview issues.

**One Gitea user per stack** (`bot-<stack>`), a normal user, not an admin. Its credentials:

- A token with only `write:issue` and `read:repository` (scope names verified on the Gitea token-scopes page, below). Nothing else: no `write:repository`, no
  `write:organization`, no `admin`, no `user`.
- **Gitea scopes are categories, not repos.** The scopes page lists `read`/`write` pairs per category and says nothing about limiting a token to given repos
  (a newer version may differ, check ours). What limits a bot to its repos is the account's membership, not the token. So: one Gitea team per
  stack in the org, `includes_all_repositories` false, containing only the repos that bot may touch, with the Issues unit at write and the Code unit at read on the
  repos where it only files tasks.
- Code does not travel through the token. As with `gateway web`, a bot that edits its own repo holds a deploy key with write on that one repo
  (`ops/install_git_key.sh`). Token for tasks, deploy key for code, two small credentials with two small blast radii.
- The token sits in the stack's `.env` (mode 600) like every other service key, loaded by the operator at provisioning. It is shown once by Gitea.
  It is per stack and is never part of the owner keyring of section 9: sharing one board token between bots would erase the per-bot teams.

**A task is an issue.**

| Field | Use |
|---|---|
| author | a human account (the owner or a controller, filing it in the Gitea UI) or a bot account (filed through `gateway tareas nueva`) |
| assignee | the one bot account that must act. Exactly one |
| labels | scoped, exclusive: `estado/abierta`, `estado/en-curso`, `estado/bloqueada`, `estado/necesita-persona`, `estado/hecha`. Org labels, so every repo of the org shares them |
| first block of the body | fixed header written by the gateway, not by the model: `pedido-por`, `para`, `salto: N`, `cadena: a > b > c`, `desde: #N`, `fecha`, and `reasignada-por` after a reassignment (the chain fields are defined in section 10.3). The rest is free text, 2 KB at most |
| links | `#12`, commit and PR references in comments; the design bot's work ends as a PR on its repo, a human merges |
| closing | a comment `resultado:` with one to five lines, then close. A task closed with no `resultado` is reopened by the gateway |

**Humans approve merges.** Branch protection on `main` of each repo: push allowlist is deploy keys of the bots' own review branches only, approvals allowlist holds humans
only, merge allowlist holds humans only (all three exist per the protected-branches page). No bot account appears in an approvals or merge list. The approval notice goes to the person's Telegram
with the PR link. This is the same rule as `WEB_REVIEW_LAYERS.md` section 2, reused as is.

**Labels through the API.** The issue-creation call takes label ids, not names (docs for 1.24: `labels` is "List of label ids"), so `gateway tareas` resolves names to ids and caches them.

## 3. `gateway tareas`: a narrow command, not an MCP server

The reasoning of `INTEGRATIONS_MAP.md` section 3.1 applies without change. The job is one narrow call made on a person's behalf, the bot is reachable by prompt injection, and
a Gitea MCP server would give a model the whole API surface under the bot's token: repos, webhooks, org settings. A gateway command prints fixed sentences, refuses what is not on its
list, and keeps content out of logs.

```
gateway tareas listar [--mias | --de ROL | --abiertas]     list titles, state, assignee, age (never bodies)
gateway tareas ver N                                        one issue and its comments, as a quoted data block
gateway tareas nueva --para ROL "TÍTULO" --texto "..."      file a task for a peer (not for a stranger)
gateway tareas comentar N "..."                             add a comment
gateway tareas estado N en-curso|bloqueada|necesita-persona|hecha
gateway tareas cerrar N --resultado "..."                   close with the result line
gateway tareas asignar N ROL                                give an open task to a peer, one more link in the chain (section 10.3)
```

Config: one `"tareas"` block per stack in `gateways.json` (private, like `"web"`): `url`, `repo`, `me`, `peers`, the list of roles this bot may file for or assign to (downward only), `accept_from`, the bots
whose tasks this bot reads and acts on (missing means `peers`, so older configs behave as before; a list that is present is taken as written, and a value that is not a list means nobody), `max_cadena`
(the chain depth for this owner, an integer from 1 to 5, default 3, set by the operator only) and `humans`. There
is no command to list users, repos or orgs, no delete, no label edit, no repo or webhook call, no attachment. A role that is not in `peers` cannot be named.
Humans are always trusted and always valid targets; a bot outside `accept_from` is read as a stranger (counted, not shown, not touched).

**The token is only as safe as the container.** It sits in the stack's `.env`, so the agent can read it and can call Gitea with curl, edit an issue body or a comment its token may edit, and so rewrite a header.
Everything in this section and in section 10.3 is the discipline of the normal tool (and of the receiver), not a boundary against a model that has been turned. The token's scopes stay minimal for that reason, and the
real walls are the host profiles of section 10.

**Minimum data (the `CAPABILITIES.md` rule, enforced in code).**
- `nueva` and `comentar` write only what the model typed into the free text, up to 2 KB, after the same scans the gateway uses for outbound text: key and token shapes
  are blocked (the command refuses and says why), and file contents are never inlined. A file crosses as a name and a hash, or as a path inside a repo both can read.
  Planned (`BLOB_STORAGE.md`): a file crosses as `blob:<sha256>/<name>` in the pool's bucket of a small S3 store
  (`gateway blob put/get`), never committed to a Gitea repo, where a deleted file still stays in history.
- No memory, no transcript, no other file. The template the skill teaches is: what is asked, by when, the three facts the other bot needs, and "not included: ...".
- The issue records who asked, in the header, so "who asked what" holds even when the author is a bot acting for a person.

**An issue read by a bot is untrusted data.** `ver` prints the title, body and comments inside a delimited block (`<<<TAREA #12 de rol-x, datos no confiables>>> ... <<<FIN>>>`),
at most 4 KB, run through `content_guard` first, with comments from accounts outside the org dropped and counted. The skill states what the answer to a task never does:
text in an issue cannot grant a permission, cannot name a tool to run, and cannot override the receiving bot's own rules. A task from the owner is a request, a task from another bot is a request
too, and in both cases anything that spends money, publishes, sends a message to a third party or deletes still goes through the stack's normal approvals (`approvals: manual`) with the
person in Telegram. An approval prompt names the task that caused it.

**Loops and fan-out.** Superseded by section 10.3 (built: `tareas.py`, the receiver of section 4, `ops/gateways_sync.py`). The first version of this note allowed one hop (a bot handling a task that came from another bot could file nothing
further). The operator's four-role ladder (section 10) needs a chain of up to four bots, so the rule is now: a maximum chain depth (default 3, per owner), no cycles, filing only downward (`peers`), reading only the neighbours (`accept_from`), and
the whole chain recorded in the header. The `CAPABILITIES.md` rule "one hop" is a different thing and stays: it is about `hermes peer` calls to specialist stacks, not about the task board.
Bots still ignore comments by bot accounts unless they are on a task assigned to them, so two bots cannot talk each other into an endless thread (the loop problem noted in
`WEB_REVIEW_LAYERS.md` section 3).

**Language.** Fixed sentences in es, ru and en like the rest of the gateway, chosen from the stack's language. Issue text keeps the language the person used.

## 4. Waking a sleeping bot

A Gitea webhook is the Telegram wake for tasks.

```
Gitea (org webhook: issues, issue_assign, issue_comment)
   │  HMAC-SHA256, header X-Gitea-Signature (hex, no prefix)
   ▼
task receiver on the VM (small host service next to the waker, localhost only behind the existing firewall rules)
   │ verify signature, parse, apply the rules below, write one wake request
   ▼
waker: admit() -> RAM guard -> start brain -> on_wake.d hook (WAKE_REASON=task)
   ▼
hook calls the stack's own API server /v1/runs with a FIXED prompt: "Run `gateway tareas listar --mias` and handle the oldest open task."
   ▼
the bot reads the issue itself (`gateway tareas ver`), works, comments, closes, tells its person in Telegram in one line
```

Facts from the Gitea webhook docs (https://docs.gitea.com/usage/webhooks): the event types include `issues`, `issue_assign` (actions `assigned`, `unassigned`)
and `issue_comment` (`created`); signature headers are `X-Gitea-Signature`, `X-Hub-Signature-256` and `X-Hub-Signature`; there are organisation-scoped hooks, so one hook per owner org is enough;
`X-Gitea-Delivery` is a unique id per attempt. The org-hook creation endpoint is in the 1.24 API index (`org-create-hook`). Not verified: the exact payload field names for the assignee and the author
(read one real delivery before writing the parser), and whether our Gitea version delivers hooks to a LAN address. It blocks private addresses by default, so the receiver's host must be in
`[webhook] ALLOWED_HOST_LIST` (`security/static-sites-deploy-keys.md` already documents the symptom: a hook that never fires with no error in the UI).

Receiver rules (code, not model):
- Verify the signature before parsing, with a constant-time compare; the secret is per org.
- Wake only for: an issue just assigned to `bot-<stack>`, or a comment on an open task assigned to it. Ignore everything else, and ignore events caused by the bot's own account.
- The chain rule (section 10.3, the same one `gateway tareas` applies): wake only if the assignee may act. The actor (who assigned or commented) and the issue's author must each be a human, the bot itself or in that stack's `accept_from`;
  the header must be readable and its `salto` not above the owner's `max_cadena`; and the assignee must not already be earlier in `cadena`. A task that fails any of these stays on the board (outcomes `not-accepted` and `chain-ignored` in the log)
  and the bot finds it, if it should, with its next `gateway tareas listar`. A task AT the maximum wakes (the bot may act on it; it cannot file anything further). A header that cannot be read does not wake.
  The receiver holds no Gitea token, so it does not post a "needs a person" comment or message the owner; that would need a token on the host (not decided).
- The receiver parses the header with a copy of `tareas.py`'s `parse_body` and `chain_info` (it runs on the host, which does not get `tareas.py`); its selftest compares the source text and the results of both on the same fixtures.
- Idempotency: one wake per `X-Gitea-Delivery`, and one run per (issue number, last-updated) so a retry does not run a task twice.
- The prompt is fixed. The issue text never goes into the prompt that starts the run; the bot fetches it through the gateway, which wraps it as data.

**RAM guard.** A task wake goes through `admit()` like any wake. Treat it like a cron wake (look once, never evict somebody's live conversation, never wait), and
retry on the waker's retry grid (10 minutes) instead of queueing. `max_awake` and `reserve_mb` apply unchanged, so four bots of one person plus other people's stacks cannot push the host over the line:
the task waits as an open issue, which is exactly what a task board is for. After the run the stack gets the same short hold as a cron run, then sleeps. A person talking to the bot at the same moment has priority
(a busy stack is never stopped by the guard, and a task is only started in a quiet moment). Not verified here: that the API server answers `/v1/runs` for a person stack with the stack's key, and how a headless run sends the owner a Telegram line
(`jobpush.py` already sends from a stack with no chat turn, so the pattern exists; check it with the first prototype).

## 5. Privacy walls

- **Bots never read each other's memory or files.** Each stack has its own `/workdir`, and nothing in the design mounts one into another. What crosses is only what is written in the issue.
  `peer dm` is not used between role bots: a peer message lands in the callee's canonical chat and would share its transcript (`CAPABILITIES.md`). The board replaces it.
- **Accounting data stays in the accounting bot.** Figures, statements and invoices are never put in an issue. The accounting bot can file "prepare the monthly summary for the social bot's post: 3 numbers I authorise
  you to use" and write those three numbers itself. A task asking the accounting bot for data goes to the person for a yes first (`estado/necesita-persona`).
- **A controller sees one bot.** A team per bot (section 2) gives the controller the repo of the bot they drive and no more. Because tasks live in the receiving bot's repo, requests the owner filed to other bots
  stay unreadable to the controller.
- **The board is stored on the operator's Gitea.** An admin of that Gitea can read every issue. The `/compartir nada` level cannot hide it, and the manual must say so
  (the levels are an agreement, not a technical wall). Two consequences: the minimum-data rule above is the real protection, and an owner who wants more runs their own Gitea.
- **Personal data law.** Issue text can hold personal data of third parties (a customer, a recruiter). Apply `DATA_LAW_AND_KEYS.md`: collect only what is needed, retention for closed issues (proposal: bodies
  of tasks closed over 90 days are blanked by a timer, titles and `resultado` kept), deletion on exit through the org deletion step of the exit flow, backups of Gitea expire on the same period as the stacks.
  A controller is a new data subject: they get the art. 6 notice and consent before their first message to the bot, and the notice names the board and the owner.
- **Generative safety.** A task is never permission. "Make a picture of this person" filed by one bot to a media bot is judged by the media bot's own rules on whose face may be used
  (`GENERATIVE_SAFETY.md`), and the answer comes back as data.
- **Secrets.** Never in an issue, a comment, a repo or a commit message; the gateway blocks key shapes and the repo-side hook is `privacy_scan.sh` plus `gitleaks` where the repo holds code.

## 6. Handover step by step

The owner writes to the design bot: "pasale el bot de diseño a X" (give) or "dejá que X use el bot de diseño" (lend). The bot does not act on the sentence alone: it
replies with the checklist below and files a task in `tareas` for the operator, because creating accounts, teams and keys needs the operator (the harness blocks writes to the VM, so these are commands the operator runs).

**Ceder (give).**
1. **Consent and identity.** The new person agrees and sends their Telegram id and (if they want the board) the name they use in Gitea. They get the manual and the privacy notice in their language.
2. **Clean the bot.** The owner and the bot list what the bot's memory and `/workdir` hold. The owner decides what stays. Sessions and memory about the owner are wiped; skills, the site repo and the style notes stay.
   Nothing else is moved: a wipe is easier to defend than a promise.
3. **Close the board.** Open tasks for this bot are finished, closed, or re-filed by the owner in `tareas` as the owner's own requests. A peer's permission (team) on the design repo is removed.
4. **Move the repo.** Gitea repo transfer to the new owner's org (the API has a transfer call with `new_owner` and a `202` pending result and a separate accept call; our version's exact behaviour is to be tested). History and closed tasks go with it. The
   old owner may stay as a read collaborator if the new owner agrees; the default is no access.
5. **Move the stack.** Ownership changes in the stack's config: new owner id, no controllers. The old Telegram bot token is revoked by the old owner (`/token`); the new owner creates their own bot and sends the token through the keys page. The old owner's keys are removed and the new owner loads theirs.
6. **New credentials.** A new `bot-<stack>` token for the new org; the old one is revoked. The deploy key is replaced. The bot's `peers` list is emptied: it has no peers until the new owner adds some.
7. **Check.** The operator runs the read-only checks (the stack answers on its new bot, the old id is refused, `gateway web verificar` passes, the old owner's keys are gone) and tells the old owner and the new owner what changed.
8. **Receipt.** A short note in both orgs' `tareas`: date, what moved, what was wiped. No content.

**Prestar (lend).** Steps 1 and 2 as above (the owner still reviews what the controller will be able to ask the bot). Then: add the controller's id to the allowed list and `controllers`, create their Gitea user, add them to the bot's team (this repo only),
a spending cap at the provider, and a first message to the controller that says it is the owner's bot, whose quota it uses, and what they cannot do. The owner keeps the stack, the Telegram bot token, the keys and the owner-only commands.

**Taking it back.** Lend: remove the controller from the allowed list, from `controllers` and from the team, then rotate the bot's session (so the controller's chat is not in the memory the owner keeps: wipe or archive it according to the controller's wish) and tell both.
Give: the old owner cannot simply take it back; it is a new give in the other direction, with the same eight steps, because the stack now holds the new owner's data. The board makes both directions auditable: the issues show who asked what before and after.

## 7. The interpreter ("ping-pong") idea, for later

A person speaks English and the other person sees Russian text, then answers in audio and the first sees English text. Step 1 is a single-bot mode
(`/interprete en ru`): each voice note is transcribed with the existing speech path (never on the VM CPU), translated by the model and shown as original
plus translation, with a small state file for the language pair and `/interprete fin` to end it. Step 2, two bots, would use a keyless relay stack
reached with `peer run` (no personal data, one hop, an answer that is data), not Gitea issues as a chat. The board is used only to record that both owners
approved the pairing. Any reply voice is a stock voice, never a clone (`GENERATIVE_SAFETY.md`).

## 8. Costs and phases

- **RAM per stack:** the waker estimates 600 to 700 MB for the brain and 300 MB for the web tier (a Telegram-only bot needs the brain only). Role bots that
  nobody talks to sleep after 10 idle minutes, and `max_awake` bounds how many run together, so "four bots" means up to four stacks that rarely run at once.
- **Gitea:** a small server on the VM or a LAN host; load is a handful of API calls per task. Backups join the nightly stack backups.
- **Model tokens:** a task run is one short turn plus the work; `ver` limits to 4 KB.
- **Operator time:** creating a stack, an org, a team, a bot user, a token and a deploy key per bot is the real cost; `ops/tareas_setup.py` does the Gitea side.
- **Phases, each usable alone:** P1 board command, skill and the `equipo` pack; P2 task receiver and wake (webhook, HMAC, idempotency, depth and cycle rule);
  P2b owner keyring and per-role key allowlist (section 9); P3 owners, controllers, the controls-plugin gate and the handover runbook.

## 9. Same-owner pool: shared keys, least privilege

Status: design only, except where a row of the table says "exists". Policy: (1) bots of the SAME person may share that person's API keys;
(2) not every bot needs every key, so each bot gets only the keys its role needs and nothing more; (3) each bot does its own job. Keys never cross between two different people.
This also fits the public showcase idea: a person's bots, each with a narrow job, one board, one keyring, as a worked example of an agentic setup. The page uses generic role names only.

### 9.1 What each role needs (from the code, nothing run, nothing changed)

"Opt." means the feature works without the key and says so. The paths are under `aibridge/`.

| Role / pack | Credentials it needs | Required? | Where it is read |
|---|---|---|---|
| Any bot (base) | One LLM provider key: NVIDIA, Gemini, OpenRouter, HF or Token Harbor | Required | `router.py` (cloud chain, key lookup), `ops/lib/providers.py`, `keys_server.py`, `stacks/docker-compose.stack.yml` |
| Any bot on Telegram | Its own BotFather token plus the owner's numeric id | Required for Telegram | `ops/stack_telegram.py`, `keys_server.py`, `ops/provision_stack.sh` |
| Any bot other bots call (`hermes peer`) | Its own `HERMES_API_KEY`, auto-generated | Generated per stack | `ops/provision_stack.sh`, `CAPABILITIES.md` |
| Voice notes (base skill `audio-transcription`) | `GROQ_API_KEY` | Opt.; without it only a powered-on home GPU PC understands voice notes | `gateway.py`, `ops/stack_keys.py` |
| Songs (`mundo`, `edicion`; skill `audio-identify`) | `AUDD_API_TOKEN`; optionally `ACRCLOUD_CREDENTIALS` (one value `host:key:secret`) | Opt.; without one the bot does not name the song | `gateway.py` |
| Maps and places (`base`, `mundo`) | `GEOAPIFY_API_KEY`, `CARTO_API_KEY` | Opt.; falls back to OpenStreetMap | `gateway.py` |
| Films and series (`gateway dato pelis`, base `live-data`) | `TMDB_API_KEY` | Opt.; falls back to Wikipedia only | `gateway.py` |
| Weather, dollar, holidays, news, aircraft (`gateway dato`) | None in the code read | n/a | `gateway.py` |
| File check (`seguridad`) | `ABUSECH_AUTH_KEY` | Opt.; the only pack with a declared `needs` | `skill_packs.json`, `gateway.py` |
| Website bot (`sitio`) | A git deploy key with write on one repo, in the stack's `/workdir/.ssh`, plus a `"web"` block in the private master. No hosting, Cloudflare or DNS token | Required for `gateway web` | `ops/install_git_key.sh`, `gateway.py`, `ops/SITES.md`, `ops/gateways.json.example` |
| Sysadmin (`sysadmin`) | Zabbix read-only API token and url; Proxmox `PROXMOX_*` url, token and fingerprint in `.env`. The credentials list stores names and dates, never values | Opt.; each tool works only where configured | `gateway.py`, `skill_packs.json` |
| Remote machines (`maquinas`) | The person's provider key in the `"maquinas"` block of the private master | Required; the pack exists only where the block exists | `gateway.py`, `skill_packs.json`, `ops/gateways.json.example` |
| Job search (`empleo`) | No portal key or login (public pages; the skill says never to ask for a login) | n/a | `SKILL_job_search.md` |
| Morning revista, hub reader (`revista`) | No key for reading (public previews and feeds, no login, no bot); the digest uses the stack's own LLM key | LLM only | `hub/collectors.py`, `hub/HUB.md`, `ops/revista_enable.sh` (being added with the revista pack) |
| Claude Code box (`programacion`) | An ssh key to a claude box (`ssh_config`) | Opt. | `gateway.py` |
| Home GPU hosts: transcode, upscale, mosh, vidpost (`edicion`, `creativo`) | Per-host bearer token in the private master | Opt. | `gateway.py` |
| Task board (Gitea bot token) | `write:issue` plus `read:repository` for `bot-<stack>`, one team per stack | DESIGN ONLY (section 2) | this note |
| Accounting (`presupuesto`), office (`oficina`), research (`investigacion`), QR (`codigos`) | No service key found beyond the LLM key | n/a | `skill_packs.json` (skill lists only; each skill's own scripts were not audited) |

Which of these are owner keys that the pool may hold, and which are never pooled:

- **Pool candidates (the person's own, same value usable by several bots):** the LLM provider keys, `GROQ_API_KEY`, `AUDD_API_TOKEN`, `ACRCLOUD_CREDENTIALS`, `GEOAPIFY_API_KEY`,
  `CARTO_API_KEY`, `TMDB_API_KEY`, `ABUSECH_AUTH_KEY`, and the Zabbix and Proxmox values where the owner has them. The set is a fixed list of known names, the same one `SERVICES` and `ops/stack_keys.py` validate; anything else is refused.
- **Never pooled, one per stack by construction:** the Telegram bot token (each bot has its own BotFather bot), `HERMES_API_KEY`, the Gitea `bot-<stack>` token, the deploy key, and the ssh key of the claude box.
- **Not owner keys, so not in the keyring:** the per-host bearer tokens of home GPU hosts (operator infrastructure, in the private master), and the machines-provider key stays in its `"maquinas"` block.

### 9.2 What exists today, and what does not

**Exists today** (verified in code, one stack at a time):
- One stack per person or role: `ops/provision_stack.sh`, `ops/stack_packs.py` (packs on or off per stack, `/workdir/.paquetes.json`), `ops/gateways_add_person.py`.
- Optional services: `SERVICES` in `gateway.py`, `gateway servicios guardar|quitar|no|si`, the weekly hint, a real-call check of a pasted key. Service keys land in the stack's Hermes `.env` at mode 600 under the same `flock` the keys page uses.
- LLM keys pasted on the keys page go to Hermes's credential pool (`hermes auth add`, key on stdin) and only the last 4 characters go to `/workdir/.keys-status.json`. The router reads the pool first, then `.env`, then the stack environment.
- `ops/stack_keys.py`: operator-side injection of one provider into one stack per run, key on stdin only, wakes the stack first. It supports gemini, openrouter, huggingface, nvidia and groq only; the other service keys have no operator-side path.
- The operator's starter key (`provision_stack.sh --nim-key`, marked `workdir/.starter-key`); a key the person pastes wins over it.
- `ops/gateways_add_person.py` never copies `tts_voice`, `tts_voices`, `claude`, `web`, `lang`, `zabbix` to a new stack. It does NOT list `maquinas`, so a `--like` copy of a stack that has that block carries the machines key over. Adding `maquinas` to that list is a one-word fix to make with the pool (design: not changed here).
- "Pool" in the code means Hermes's own credential pool, which is per stack. There is no per-person pool.

**Designed only, nothing built:** the owner keyring, the `keys` allowlist, the sync step, the wipe path for service keys and persisted copies (still unbuilt in `DATA_LAW_AND_KEYS.md`), the Gitea board (sections 2 to 4), owners and controllers, handover, `<person>-<role>` stacks as a convention (section 1; nothing prevents the stacks today, only the tooling is missing).

**Today's cost of sharing:** one Groq or NVIDIA key for four role bots means loading it four times, one `ops/stack_keys.py` run per stack and provider, and for service keys by hand through each bot's keys page. Rotation means repeating all of that and remembering which stack holds which key. The pool replaces that with "change once, sync".

### 9.3 Design

1. **Owner keyring.** One file per owner on the VM, outside the repo and outside any stack's mounts, owned by the operator account, mode 600, never in git (the privacy scan and `gitleaks` cover the repo side). It maps a known key name to a value and a created date. It is the only place where a shared value is stored on the VM. Later it is fed from the person's KeePassXC vault as `DATA_LAW_AND_KEYS.md` describes (the operator never holds the vault itself, only what the person exports into the keyring); until then the person sends each key the way keys arrive today, and the operator files it with a small command that reads it from stdin.
2. **Per-stack allowlist.** A `keys` list per stack in the private master `ops/gateways.json` (never in git): `"keys": ["groq", "audd"]`. Names come from the fixed list in 9.1. The default for a new stack is an empty list, so a new role bot starts with no shared key and the operator adds what the role needs. `ops/gateways.json.example` shows only the shape, with generic names.
3. **Sync step** (proposed `ops/stack_keys_sync.py`, one owner or one stack per run). For each stack of the owner:
   - read the allowlist and the keyring; refuse an allowlist name not in the fixed list or not in the keyring (clear error, nothing written);
   - validate each value the way `ops/stack_keys.py` does (known shape, and for pasted LLM keys the same real-call check where one exists), and refuse values with a newline or control character;
   - write the allowed keys into the stack's `.env` at mode 600 under the shared `flock`, and remove keys it wrote earlier that are no longer allowed. It remembers what it manages in a small file of names only (`/workdir/.keys-managed.json`, no values), so it never touches a key the person pasted themselves;
   - never print a value: at most the name and the last 4 characters; a dry run is the default and shows names, stacks and "add", "keep" or "remove" only;
   - leave the person's own pasted keys alone (a pasted key wins over a synced one, as with the starter key);
   - LLM provider keys use the existing pool path of `ops/stack_keys.py`; removing one from Hermes's pool needs `hermes auth remove`, not verified here (check before building).
4. **Rotation.** The owner changes the value once in the keyring (or the vault), and the operator runs the sync for that owner's stacks. A running stack reads its environment at start: a sleeping stack picks the new value on its next wake, an awake one needs a restart. Whether the waker can recreate it on demand is to be checked. The old value is revoked at the provider by the owner, and the allowlist plus `.keys-managed.json` give the list of stacks that held it.
5. **Handover (`ceder`).** The stack's allowlist is emptied and the sync removes every owner key from its `.env`; the owner keyring is untouched. The new owner loads their own keys. A lent bot (`prestar`) keeps only its role's allowlist and the owner narrows it first.
6. **Blast radius.** Sharing one LLM key makes one runaway bot spend the quota of all of that person's bots, and a provider cap is per key. Where the provider allows several keys, give the costly or exposed bots (website, social, anything reading outside text) their own LLM key and keep one shared key for quiet roles.
7. **Auditing.** `ops/stack_keys_sync.py --report` lists, per stack, key names and last 4 characters, and flags any key present in a stack's `.env` that is not allowed by the master. The report is read-only and is what the operator runs before and after a handover.

### 9.4 Role to allowlist (proposal, a starting point per bot)

| Bot role | `keys` allowlist | Not given, and why |
|---|---|---|
| Accounting | LLM key only | no maps, songs or voice: it reads the person's figures and must not be able to call out |
| Social media | LLM key, `groq` (voice notes), `audd` (songs) | no `maquinas`, `sysadmin` or deploy keys |
| Job applications | LLM key | portals need no key; nothing else is useful |
| Website design | LLM key; deploy key for its own repo (not a pool key) | no hosting, DNS or Cloudflare token, ever |
| Sysadmin | LLM key, Zabbix and Proxmox values as the owner has them | no media or personal-assistant keys |
| Designer (17) | LLM key, plus only the media keys its tools need (names from the list of 9.1) | no Zabbix or monitoring token, no SSH or hostcare key, no social-network or Postiz key, no cloud-GPU account (19) |

Developer, marketing, novedades, tecnico and datamanager are in 10.2, 11 and 12: the Postiz key, the per-stack Zabbix tokens, the PBS or cloud read credential and the deploy keys are per stack by construction, never pooled.

### 9.5 What is shared through Gitea, and what is not

Shared between the bots of one owner, through the owner's board (sections 2 and 3): tasks and results, as text, code and links. That is all.
Never shared: a bot's memory, the files of another bot's `/workdir`, sessions, and anything secret. `gateway tareas` refuses key and token shapes in `nueva` and `comentar` (section 3), and the repos hold no secrets (section 5, "Secrets").
Keys travel by the keyring and the sync step, never by an issue, a comment or a commit. A bot that needs a key it does not have files a task for the person ("estado/necesita-persona"); it does not ask a sibling bot for it.

## 10. A privilege ladder: four roles

Status: built offline in `tareas.py`, the receiver `ops/wake/tareas_hook.py` and `ops/gateways_sync.py` (the "As built" notes after 10.3 list where the build chose); not deployed, and the
host profiles it relies on (`ops/hostcare/HOSTCARE.md`) are still design. It adds no new mechanism: it is a way to use the board (sections 2 to 4),
the key pool (section 9) and `ops/hostcare/` (`ops/hostcare/HOSTCARE.md`, "Role profiles") so that the bot that finds a problem is not the bot that can fix it, and the bot that can fix
it is not the bot that can touch the backups.

### 10.1 The idea

One owner has bots for one website host. Each bot holds only what its job needs. When the job needs more than the bot holds, the bot does not ask for the key: it files a task for the bot one rung up, through the
Gitea board, as text. The rungs are:

1. **novedades** reads news and feeds, and reads Zabbix read-only. It knows what is installed (for example "PHP 8.1 on the site host") because Zabbix reports it, crosses that inventory with what the feeds say, and files
   a task for tecnico. It touches no machine.
2. **tecnico** has an SSH account limited to the website: the site files, the site's own database, the app's configuration, deploy. It cannot update the operating system, change PHP versions, install packages or become root.
   When a fix needs one of those, it files a requirement for sysadmin.
3. **sysadmin** has root on the host: packages, versions, services. It has no rights over backups. Before a big change it asks datamanager to confirm a fresh, verified backup.
4. **datamanager** owns the backups: verifies them, tests restores, alerts when they are stale (11.4 narrows this: it does not run or prune them, and its credential lists, verifies and reads only). It writes to neither the system nor the site (it only reads what it copies).

Why this split and not one strong "ops" bot: the bot that reads outside text all day (feeds, advisories) is the one most exposed to prompt injection, so it holds the least; root is held by a bot that only receives tasks from
two neighbours and acts only with the owner's approval; and a bot that has root cannot also delete the only copy that would let the owner recover from its mistake.

An honest limit, stated once: the table below says what each bot's credentials allow. It is only a wall where the host enforces it (separate accounts, forced commands, files and storage the account cannot read; `ops/hostcare/HOSTCARE.md`,
"Role profiles"). Root on a host can read anything on that host. "Sysadmin has no rights over backups" is therefore real only if the backups live where the sysadmin account cannot reach, and the backup credentials sit in a file only
the backup account reads: pull from another machine, or push to storage that accepts appends and not deletions. On a single box where root can read the backup directory, the hostcare `NEVER` patterns are a guardrail against a mistaken or injected
model, not a boundary against a model that has been turned. The design should say which of the two the owner has.

### 10.2 The ladder as a table

Names are generic. Keys come from the pool of section 9 (shared, same owner, by allowlist) or are per stack by construction. "hostcare profile" is the key and allowlist of `ops/hostcare/HOSTCARE.md`, "Role profiles".

| | novedades | tecnico | sysadmin | datamanager |
|---|---|---|---|---|
| Holds | LLM key; Zabbix url and read-only token (a Zabbix user whose role and host groups are read-only and limited to the owner's hosts); news and feed reading, which needs no key; Gitea board token | LLM key; Gitea board token; deploy key for the site repo; hostcare `web` key (care level 0 and 1, and an exec key at level 2) | LLM key; Gitea board token; hostcare `sysadmin` keys (care level 0 and 1, exec level 2); Zabbix and Proxmox read values as the owner has them | LLM key (a small model is enough); Gitea board token; its own read-only Zabbix token (11.5); hostcare `backup` key (named tools only, no exec key); the backup tool's credentials stay on the host in the backup account's file, not in the bot |
| Never holds | any SSH or hostcare key (at most the optional level-0 `read` key of a host with no Zabbix); a deploy key; Proxmox values; root; backup access | root or sudo; package managers; PHP, OS or service-version changes; Zabbix, Proxmox and backup credentials; the DB's admin password (it never sees even the limited DB user's password: it lives in a file on the host) | backup credentials, backup tools and backup paths (hostcare `never` list for this profile); the deploy key; media and personal-assistant keys | system or site write access; package, version and service changes; the deploy key; Proxmox values (the backup system's read credential is its own, 11.4); any Zabbix token with write rights; root |
| Asks whom (files a task for) | tecnico | sysadmin (and, if the owner enables the optional edge, datamanager) | datamanager | nobody; when it cannot continue it sets `estado/necesita-persona` and tells the owner |
| Reads text from (`accept_from`; a task is assigned only by the rung below it or the owner, results are read from the rung above) | tecnico, the owner | novedades, sysadmin, the owner | tecnico, datamanager, the owner | sysadmin, the owner |
| Keys from the pool (section 9) | `keys`: LLM, `zabbix` | LLM | LLM, `zabbix`, Proxmox values | LLM |
| Never pooled (per stack) | Telegram token, `HERMES_API_KEY`, Gitea token | the same, plus the deploy key and the hostcare keys | the same, plus the hostcare keys | the same, plus the hostcare key |
| hostcare profile | none (Zabbix is its eyes). If a host has no Zabbix, a `read` profile with level 0 only | `web` | `sysadmin` | `backup` |
| Approval | nothing it does needs one: it files text | level 2 commands: the owner approves | level 2 commands: the owner approves; big changes also need a fresh verified backup | restores onto live data are not its job; it makes a verified copy and a sysadmin or tecnico task applies it |

The ladder also has two side roles, developer and marketing (section 11); novedades and tecnico each hold their own Zabbix token (section 12) and datamanager its own read-only one (11.5); datamanager never prunes or runs backups and holds a list-verify-read credential only (11.4);
and the dangerous steps in this table (a restore onto live data, an OS upgrade, anything that deletes) are subject to the approval-source rule and the time-locks of sections 13 and 14. The site repo write key in tecnico's column moves to developer (11.1): tecnico keeps the hostcare `web` deploy of what a human merged and no code-editing write.

Two properties of this table that the board config must keep:
- Direction is in `peers` (who a bot may file for or assign to): novedades `[tecnico]`, tecnico `[sysadmin]`, sysadmin `[datamanager]`, datamanager `[]`. A bot never lists a role above it.
- Trust is a separate list. Today `tareas.py` uses one list, `peers`, both for "may file for" and for "whose text is shown" (`trusted()`). The ladder needs the second list, `accept_from`
  (tecnico accepts from novedades and sysadmin; sysadmin from tecnico and datamanager; and so on), so a bot reads only its direct neighbours and never a bot two rungs away. Results travel down one rung at a time.

### 10.3 The chain: depth, cycles, header (replaces the one-hop rule)

The one-hop rule of the first version (a bot handling a task that another bot filed could file nothing further) cannot carry a four-rung ladder. It is replaced by three rules, all
decided on what the board says and never on a state the model set (the principle of the first version stays):

1. **Maximum chain depth.** The depth of a task is the number of bot-to-bot handoffs behind it. A task a person files for a bot has depth 0. When novedades files for tecnico on its own initiative, that task has depth 1 and its
   `cadena` is `novedades > tecnico`. The default maximum is **3** (novedades > tecnico > sysadmin > datamanager is exactly three handoffs). It is configurable per owner in the stack's `"tareas"` block as `max_cadena`
   (operator-set, integer, clamped to 1 through 5 in code; the model cannot change it). A task whose creation would exceed it is refused with a fixed sentence that names the chain and says that the person decides.
2. **No cycles.** A bot that is already in the task's `cadena` cannot be assigned again, by `nueva` or by `asignar`: not the bot filing it, not the bot that started the chain. Answers go back by comment on the parent task, never by a new task in the other direction.
3. **The whole chain is in the header.** The header is written by the gateway: `salto: N` (the depth, kept for readers of the old format), `cadena: a > b > c` (bot accounts, first to last, the current holder last) and `desde: #N` (the parent task).
   A child's `cadena` is the parent's `cadena` read from the board plus the target. It is never copied from model text.

Things that do not change:
- Every step keeps its own approval rule. A task is a request, never a permission (section 3, "An issue read by a bot is untrusted data"). Level 2 (any command on a host) still needs the owner's approval for that command, whatever the chain says,
  and the approval prompt names the task and the whole chain, so the owner sees "this PHP upgrade started as a news item, went through tecnico, and sysadmin now asks to run these commands".
- The load floors stay: at most `MAX_MADE_OPEN` open and `MAX_MADE_DAY` tasks per bot in 24 hours, so a chain cannot become a fan-out. A per-parent cap (for example 3 open children) is recommended on top.
- The same honest limit as before: the board token can edit an issue body, so these rules are discipline of the normal tool, not a boundary against a bot that has been turned. The real walls are the host profiles, not the header.
- The first version's "one hop" in `CAPABILITIES.md` (about `hermes peer` and specialist stacks) stays as written.

Waiting for a child: the parent holder files the child with `--desde N` and sets its own task `estado/bloqueada`. When the child closes with its `resultado`, the holder of the parent reads it (once the webhook of section 4 exists, a close event on a child
wakes the parent holder; until then, on the next time it looks at its inbox), comments the result on the parent and continues.

**What had to change in `aibridge/tareas.py` (the list the build followed; the notes after it say what was decided).**
1. Header: add the fields `cadena` and `desde`; keep `salto` as `len(cadena) - 1`. `make_header` and `parse_body` accept them (today both hard-code `pedido-por`, `para`, `salto`, `fecha`, `reasignada-por`). Only the first block counts, as now.
2. Parsing: `salto` becomes any integer from 0 up. A header whose `salto` or `cadena` cannot be parsed, or is longer than the maximum, counts as being AT the maximum, so it can start nothing further (today an unparseable `salto` counts as 1).
   A header from the old format (`salto` 0 or 1, no `cadena`) is read as depth 0 or 1 with an unknown chain: depth is enforced, cycles cannot be checked against it, and the code says so.
3. Config: `max_cadena` (default 3, clamp 1 to 5) and a second list `accept_from` next to `peers`; `trusted()` uses `accept_from` plus the humans, `resolve_target()` uses `peers` plus the humans. `peers` stays the only list that can be an assignee. If `accept_from` is missing, it defaults to `peers`, so existing configs behave as today.
4. Refusal rule in `nueva`: replace the "holds a hop-1 task, so create nothing" check and the `salto_of(src) >= 1` check with: new depth = depth of the `--desde` task + 1 (a `nueva` with no parent: 0 for a person's task, 1 if filed by a bot on its own initiative that the owner enabled);
   refuse if the new depth is above `max_cadena`; refuse if the target is in the parent's `cadena` (case-insensitive) or is the bot itself; keep `desde_required` while the bot holds a task that another bot filed; keep `desde_bad` (the parent must be assigned to this bot).
   The parent's chain is read from the board through `trusted_issue`, so a parent from a stranger gives nothing.
5. Refusal rule in `asignar`: the same depth and cycle checks, with the new member appended to the task's own `cadena`; drop the rule "refuse while the bot holds a hop-1 task".
6. Strings: rewrite `S["hop"]`, `S["hop_assign"]` and `S["desde_required"]` (they say "one hop"), and add `S["depth"]` (names the chain and the maximum) and `S["cycle"]` (names the bot that is already in it), in the same Argentine Spanish register as the others.
7. Display: `ver` shows `salto N de M` and the chain; `listar` may show only the depth.
8. Waker side (`ops/wake/tareas_hook.py`, now rewritten to this rule): its own `salto_of()` and `hop_creators()` treat `salto` as 0 or 1 and ignore a task at 1 while the creator is busy. It must read the same header, compare to the owner's `max_cadena`, and ignore a task whose `cadena` holds the assignee twice.
   The skill `SKILL_tareas.md` and the `CAPABILITIES.md` pointer need the new wording.
9. Selftest cases to add to `gateway_tareas_selftest.py` (and to change: the cases that assert the old rule, "a task created from a hop-1 task is refused", "hop-1 task cannot be reassigned", "holding an open hop-1 task blocks `nueva`", and the one asserting "salto 1: ya no puede pasar por otro salto"):
   - a person's task is depth 0 with `cadena` of one bot; a task filed by a bot on its own initiative is depth 1;
   - the full ladder passes at the default: novedades > tecnico > sysadmin > datamanager, and a fifth link is refused with the chain named; with `max_cadena` 2 the third link is refused; with 7 the value is clamped to 5; with 0 or a string it is the default;
   - cycles: sysadmin cannot file for tecnico, nor for itself, nor for novedades; the same with different capitalisation; `asignar` back up is refused as well;
   - direction: tecnico cannot name novedades as a target (not in `peers`) even though it reads its tasks (in `accept_from`); a bot two rungs away is not accepted as author or commenter;
   - forged text: a second header block in the body, a header line in a comment, and a stranger's issue never change depth or chain; an unparseable `salto`, a negative one and one above the maximum count as the maximum;
   - old-format header (`salto: 1`, no `cadena`) enforces depth and is reported as chain unknown;
   - the child's `cadena` equals the parent's plus the target, even if the model passes a different `--desde` text;
   - `--desde` on a task not assigned to this bot is still refused; the load floors still hold along a chain; the per-parent cap, if added, is enforced;
   - the log line still has no title, body or comment.

**As built (offline; where the build had to choose).**
- Depth of a task with no parent. `gateway tareas nueva` with no `--desde`: `--pedido-persona` (the model says a person asked in the chat) gives `salto: 0` and `cadena` of the target alone; without it the task is the bot's own initiative,
  `salto: 1` and `cadena: me > target` (open decision 11 is the question of whether that is allowed at all; nothing blocks it yet). A task for itself is a note, `salto 0`. `--pedido-persona` is the one input that is not judged from the board
  (nothing on the board says a person asked), so a bot that lies about it can restart a chain at 0 only where it holds no task that another bot filed; the skill says when to use it.
- A bot that holds a task another bot filed (open, or closed in the last 60 minutes: `RECENT_CLOSE_MIN`, read from `closed_at`, so closing the parent first does not reset the count) must give `--desde N`, and N must be one of those tasks (`S["desde_other"]` otherwise): choosing a shallower parent, such as a person's task, cannot be used to restart the count while a deep one is open.
- A task for a person is not another link: it has no depth or cycle check and keeps the chain as it was, so a bot at the maximum can still leave a note for the person (the ladder's "needs a person").
- Depth is a brake with limits, not a proof. After the hour a bot that closed its parent can start a new chain at depth 1, so two mutual peers can still hand work back and forth, one task per bot per hour at depth 1, bounded then only by `MAX_MADE_OPEN` and `MAX_MADE_DAY` (30 tasks a day per bot, each one a wake). The `--pedido-persona` flag is set by the model and is judged on the same held-task rule, so it gives depth 0 only when nothing from a bot is held. Watch for repeated salto-1 tasks between the same pair in the board; nothing alerts on it yet.
- A header that was attempted but cannot be read (the marker with no separator, blanks or a BOM before the marker, the marker later on its first line, wrong-case or misspelled keys, an empty block) reads as unreadable (the maximum), never as "no header". A task with no header at all from an account that is a bot (this bot or any in its lists) is also unreadable, in `tareas.py` and in the receiver (which does not wake for it); only a person's typed task has no header and is depth 0.
- `asignar` appends the target to the task's own `cadena`. A task with no header (typed in the web page by a person) is depth 0 held by the bot, so the result is `salto 1`, `cadena: me > target`. The receiving bot only sees the task if the original author is in
  its own `accept_from`; on the ladder prefer `nueva --desde`, whose author is always the bot just above.
- Unreadable headers: an unreadable or repeated field, a cycle inside `cadena`, a `salto` that is not `len(cadena) - 1`, or a `salto` above the maximum counts as the maximum in `tareas.py` (the bot may read and answer it, it can file nothing from it).
  The receiver is stricter and does not wake for it. An old-format header (`salto` only) is depth N with an unknown chain: the child gets `salto N+1` and no `cadena`, and `ver` says the chain is unknown.
- Not built: the per-parent cap on open children (recommended above), and a wake of the parent holder when a child closes (the receiver wakes only for assignments and comments, section 4).

## 11. Two more roles on the ladder, and datamanager made concrete

Status: design only. It extends section 10 and changes three of its lines (the site repo write key moves to developer, deploy applies only what a human merged, and the restore step is gated). Generic names again:
the site host, the backup system, the owner. Items marked **[unverified]** were not confirmed from a primary source or by a real call.

### 11.1 Where the roles sit

Section 10's four roles stay. `developer` and `marketing` are **branches off the ladder, not rungs**: they sit beside tecnico, each with its own narrow credentials, and they use the same board, pool and chain rules.

| Role | Job in one line | Files tasks for (`peers`) | Reads tasks from (`accept_from`) | hostcare profile |
|---|---|---|---|---|
| novedades | crosses advisories with the Zabbix inventory (section 12) | tecnico | tecnico, owner | none |
| tecnico | health of the site: Zabbix problems, the site's own files, config, app restart, deploy of what a human merged (section 12); also reviews the designer's requests and sources GPU time (18, 19) | developer, sysadmin | novedades, developer, sysadmin, designer, marketing, owner | `web` |
| **developer** (new) | changes code: branch, push, checks, preview link, variants, a PR a human merges (11.2) | marketing, designer | tecnico, marketing, designer, owner | none (no SSH to any host) |
| **designer** (new, section 17) | generative media and video editing; hands finished assets to developer or marketing | tecnico (request for review), developer, marketing | developer, marketing, tecnico, owner | none |
| sysadmin | root on the host | datamanager | tecnico, datamanager, owner | `sysadmin` |
| datamanager | the backup system and nothing else (11.4) | none | sysadmin, owner | `backup` |
| **marketing** (new) | guides publications; owns the publishing tool (11.3); collects every party's OK before scheduling (section 20) | developer, designer, tecnico | developer, designer, tecnico, owner | none |

Why developer is separate from tecnico: the design wants one bot that changes code and a different one that watches the site. The bot that reads monitoring and feeds all day should not also be the one that writes code and the one that can restart production.
So tecnico's `deploy` only applies what a human merged, and it does not edit code (the PHP-advisory example's deploy step moves to developer).

Chains stay inside the default depth of 3. Examples: `novedades > tecnico > developer` (a deprecated call found in the site code), `novedades > tecnico > developer > marketing` ("announce the new release", depth 3), and the section 10 ladder unchanged. Direction is in `peers`, trust is in `accept_from`, and the cycle rule of 10.3 stops `marketing > developer > marketing` inside one chain.
A longer chain needs a person. Developer and marketing list each other in `peers`, so the rule "a bot never lists a role above it" (10.2) does not apply to this pair: they are branches, not rungs, and the cycle rule keeps any single chain from coming back to a bot already in it.

### 11.2 developer: git is the single history, previews are private, a human merges

**Pipeline** (the research is in `WEB_REVIEW_LAYERS.md` sections 1 and 2 and `security/static-sites-deploy-keys.md`; this is how the new role uses it):

1. The developer works on a branch and pushes to git. Every change is a commit; nothing is edited on a server. It never pushes to `main`.
2. A **server-side gate** runs on every push: the same deterministic code for everyone, no model in it (`web_checks`, the portable checks, the deny patterns of SEC-SITE-4, a paths check).
3. If the gate passes, the **publisher** (operator side) deploys a preview for that branch and keeps it private (below).
4. A PR is opened against `main` by an operator-side listener that holds the Gitea token. The owner gets one Telegram message: gate result, preview link, `vista` screenshots.
5. A human merges in Gitea. Merging to `main` triggers the production deploy, then SEC-SITE-7 (served bytes equal the commit) and the cache check.
6. Rollback is a `git revert` through a PR (a human merges it). The quick static path `gateway web deshacer` stays.

**Variants.** "Propose different versions" is one branch per variant, named `v/<slug>`, each with its own preview address. Cloudflare Pages builds the alias by lower-casing the branch name and turning non-alphanumerics into hyphens, so `v/a` and `v-a` would collide;
allow only `^(dev|v)/[a-z0-9-]{1,30}$` (30 characters because the truncation of long names at the 63-character DNS label limit is **[unverified]**). Source: https://developers.cloudflare.com/pages/configuration/preview-deployments/.
The owner picks one in Telegram, that PR is merged, the other variants are closed, and the publisher deletes their previews when each PR closes (`wrangler pages deployment delete`; the latest deployment of a branch cannot be deleted).

**The deploy command is built by the publisher, never by the bot.** `wrangler pages deploy <dir> --branch=<b>` makes a preview; without `--branch` it deploys to production (https://developers.cloudflare.com/pages/get-started/direct-upload/).
So only `refs/heads/main` maps to production, previews are allowed only for refs matching the regex above, and the command is an argv list, never a shell string, with no bot-supplied `--branch`.

**Previews stay private.**
- Pages previews are public by default and carry `X-Robots-Tag: noindex` (same page as above). The project setting "Enable access policy" puts Cloudflare Access in front of previews only, not production or custom domains
  (https://developers.cloudflare.com/pages/platform/known-issues/). A custom domain needs its own Access app.
- The rule: allow only the person's own email, as an email rule (a bare one-time-PIN login lets anyone in; the PIN lasts 10 minutes and mail scanners can consume it): https://developers.cloudflare.com/cloudflare-one/policies/access/ and https://developers.cloudflare.com/cloudflare-one/identity/one-time-pin/.
- After enabling, check with curl: production answers 200, a preview answers an Access redirect. Whether the policy applies to **Direct Upload projects** is **[unverified]**, because the docs describe it for git-integrated ones. Test on a throwaway project first.
- A preview link is never pasted into a public place, and the marketing bot never puts one in a post (11.3). Content that must not even be briefly exposed stays on `gateway web vista`, which makes screenshots and no URL.
- Free-plan limits (https://developers.cloudflare.com/pages/platform/limits/): 100 projects per account, unlimited active previews, 25 MiB per file, 20,000 files per site.

**What the developer holds** (per stack, nothing shared with another person):
- Its LLM key from the pool, its own BotFather token, the owner's Telegram id, its Gitea board token (section 2).
- One write deploy key per repo it works on (SEC-SITE-3). `main` is protected with a push allowlist that excludes deploy keys, so the key pushes branches only; Gitea accepts deploy keys on that list (https://docs.gitea.com/usage/access-control/protected-branches).
- A working copy in `/workdir` and the gateway commands. No shell on any operator machine.
- Later and optional: a Cloudflare Access service token that can only read previews, one per bot, so it can compare its own preview bytes (https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/: limit 50, secret shown once, expires).

**What it never holds:** any Cloudflare Pages, DNS or Access-admin token (SEC-SITE-2); a Gitea token that can write `main` or merge, or an admin token; Gitea Actions secrets and the runner registration token; production app secrets and database credentials (previews of dynamic apps use fake data and preview-only variables);
the publisher's read key; ssh to any host; another repo's key; social-network credentials (marketing's) and backup credentials (datamanager's).
A deploy key is SSH only and cannot call the Gitea API, so the developer only pushes. The status and the PR come from the operator-side listener. That is also why the bot cannot fake a green check. The Gitea token scope the listener needs for statuses and PR creation is **[unverified]**; test it on a throwaway repo.

**Operator side holds:** the Pages API token (permission "Pages Write", shown in the dashboard as Account > Cloudflare Pages > Edit, account-level per the sources read; our own site guide once saw a token behave as project-scoped, so per-project scoping is **[unverified]**; keep it minimal, with expiry and an IP filter),
the read-only deploy key, the webhook HMAC secret and the Gitea listener token.

**Gitea Actions is not the gate.** Actions is built in since Gitea 1.19 and "mostly compatible" with GitHub Actions (https://docs.gitea.com/usage/actions/overview); `environment` is ignored and the `statuses`, `checks`, `pages` and `id-token` token scopes are unsupported
(https://docs.gitea.com/usage/actions/comparison). The workflow file lives in the repo the bot can write, so the bot could edit it to always pass or to print a secret. Host-label runners "run as the runner's user without isolation. Use them only for trusted repositories" (https://docs.gitea.com/usage/actions/act-runner).
If Actions is added later, for a site with an npm build or app tests: `docker://` labels only, on a dedicated VM, no secrets, no LAN egress, no docker socket (the docs do not cover the socket risk, so treat it as one). Which workflow file a same-repo PR run uses, the PR head's or the base's, was **[unverified]**.

**Class of the developer's actions (section 14):** push a branch, a preview, an opened PR are class 1 (no approval). The merge is the human's, and the production deploy follows the rule of 13.3.

### 11.3 marketing: a separate role that owns the publishing tool

**Recommendation: publishing belongs to marketing, not to developer.** The operator first said the developer would push (for example with Postiz) and asked whether a marketing role is worth it. After the research, yes:

1. **Blast radius.** A publishing key speaks in public as the person or the business. The developer holds repo push and the deploy path. One stack with both would join "can ship code" and "can speak in public".
   I found no documented scoping of a Postiz API key, so treat it as control of the whole organisation's posts and channels **[unverified]**. Only the marketing stack gets it; the developer holds no publishing power and hands over text and links as a task.
2. **The approval gate has to be ours.** Postiz has no real approval flow: a post's preview link is public and has no password, and the docs say there is "no 'approved' flag that blocks publishing" (https://docs.postiz.com/general/approvals.md). You keep a post as a draft while it is under review and schedule it yourself.
   That gate belongs in a role whose whole job is the guided flow, not in a role whose job is code.
3. **The guided flow already exists as a plan.** The operator's earlier Postiz notes describe eight steps (start, content, target networks, adaptation, preview, when, send, published) with nothing published without explicit approval, one Postiz organisation per business, and comments handled by per-network Hub modules.
   A bot role is the natural home for that conversation, and a role bot can be asked to run it on a schedule or a trigger.
4. **Different inputs.** Marketing reads brand text, the calendar and what the developer or the owner hands over. Developer reads code and previews. Keeping them apart limits what an injected text in either can reach.

**What Postiz is, as verified from its docs.**
- Licence AGPL-3.0 (https://raw.githubusercontent.com/gitroomhq/postiz-app/main/LICENSE). Running it unmodified for our own use is fine. Offering a modified fork to others as a service would oblige us to publish the fork's source. Our MIT code only talks to it over HTTP, which should not make it a derivative work: my reading, not legal advice **[unverified]**.
- "Schedule and publish to 34 social platforms from one calendar" (https://docs.postiz.com/introduction); the provider index (https://docs.postiz.com/llms.txt) names, among others, X, LinkedIn, Facebook, Instagram, Threads, Bluesky, Mastodon, YouTube, TikTok, Reddit, Pinterest, Telegram and Google My Business.
- Per-network rules the skill can carry as data (https://docs.postiz.com/general/platforms/overview.md): Instagram 2,200 characters and at least one attachment; YouTube 5,000 characters and exactly one video; Facebook Page 63,206; TikTok 2,000 and one video or several pictures; Bluesky 300 and up to 4 images or 1 video; Mastodon 500; Telegram 4,096.
- Public REST API (https://docs.postiz.com/public-api/introduction.md): cloud base `https://api.postiz.com/public/v1`; the key goes in the `Authorization` header with no prefix; an OpenAPI spec exists (https://docs.postiz.com/public-api/openapi.json). The self-hosted base path is not in the pages read (probably `<host>/api/public/v1`: a guess, confirm on the running instance **[unverified]**).
- Post types `draft`, `schedule` and `now` (https://docs.postiz.com/public-api/posts/create.md). `draft` is stored and not published; `now` publishes at once. Changing a post's status between `draft` and `schedule` is its own call, and setting `draft` stops the running publish workflow (https://docs.postiz.com/public-api/posts/change-status.md).
  Some networks need extra settings (YouTube title and visibility, Instagram `post_type`, TikTok `DIRECT_POST` or `UPLOAD`, where `UPLOAD` only sends the media to the person's TikTok inbox).
- Rate limit on create-post: 90 requests per hour by default (100 on the cloud), one global value per instance, changed with `API_LIMIT`. One call can carry several posts.
- One webhook event, when a post publishes; payload and signing are undocumented (https://docs.postiz.com/general/automations/webhooks.md) and no failure event is documented, so a failed publish needs polling.
- Postiz does not read or answer a network's inbound comments. Reading them stays with the per-network Hub modules (`hub/HUB.md`).
- Self-hosting needs Temporal, Redis, Postgres and Elasticsearch: the operator measured 8 containers and 2.4 GB of RAM idle on the dev machine, which is not the small VM that runs the stacks. `DISABLE_REGISTRATION=true` allows one sign-up and then closes it; `JWT_SECRET` is required; pin an image version (https://docs.postiz.com/self-host/configuration/reference.md).
- Meta (Instagram and Facebook): the app and its review are the long pole; public use needs business verification and advanced-permission review, a public HTTPS redirect address is needed, and until then only accounts with a role on the app can publish (https://docs.postiz.com/self-host/providers/instagram.md).
  YouTube and TikTok audits are the other long poles.

**Integration: a narrow `gateway postiz`, not the Postiz MCP server, for the role bot.** The reasoning of `INTEGRATIONS_MAP.md` section 3.1 and section 3 above: the bot is reachable by prompt injection, and an MCP server hands a model the whole API under one key.
The MCP server stays an option for the operator's own interactive use, which is the "broad, own account" case of that section. Proposed command shape (design; Spanish names like the rest):

```
gateway postiz canales                         list the connected channels (names, networks; never tokens)
gateway postiz borrador --canal C --texto ...  create a post as `draft` ONLY, checked against the network's limits
gateway postiz ver N | listar                  read one draft or the calendar
gateway postiz programar N FECHA               draft -> schedule: only through the stack's manual approval (Telegram), at least a minimum lead from now
gateway postiz volver-a-borrador N             schedule -> draft (the cancel path, reversible, no approval)
gateway postiz estado N                        poll one post, because a failed publish raises no event
```

Not offered at all: `now`, deleting a post or a channel, uploading from an arbitrary URL, webhook or key calls, analytics beyond read. The text goes through the same outbound scans as `tareas` (key and token shapes refused), the link check (no preview address, no private address), and the generative-safety rules for any picture of a person (`GENERATIVE_SAFETY.md`).

**Keys and walls.** One Postiz API key per business, stored only in the marketing stack's `.env` (per stack by construction, not in the pool of section 9). The networks' OAuth secrets and tokens stay inside Postiz and never reach a bot stack.
The scheduling approval is class 2 of section 14 and uses the stack's manual approval; the minimum lead (proposal 60 minutes) is the first, small time-lock, and the cancel command works until the post goes out. The first post on a new channel is class 3.

**Blockers before anything real:** (1) today Postiz listens only on the loopback of the dev machine, so no bot stack can reach it, and Meta needs a public HTTPS domain for OAuth; a real deployment on a host with the RAM comes first, reachable from the marketing stack only (firewall rule);
(2) set `DISABLE_REGISTRATION=true` once the admin account exists, pin the image, and keep Stripe and every unused key unset; (3) the Meta, YouTube and TikTok reviews take weeks; (4) no channel has been connected to a real account yet, so nothing in the Postiz section is proven by a live call.
Networks that need no app review (a Telegram channel, Mastodon) are the low-friction first step the operator already noted; both are on Postiz's provider list.

### 11.4 datamanager on PBS or cloud object storage: it reaches only the backup system

The principle: datamanager's credential is one that **the backup system itself** limits to listing, verifying and reading. A rule in the bot's instructions is not the wall; the ACL on the backup system is. Nothing here was run against any system.

**On Proxmox Backup Server (PBS).** Facts are from the PBS docs and source (https://pbs.proxmox.com/docs/user-management.html, https://raw.githubusercontent.com/proxmox/proxmox-backup/master/pbs-api-types/src/acl.rs, https://raw.githubusercontent.com/proxmox/proxmox-backup/master/src/api2/admin/datastore.rs). Where docs and code differ, I say so.

- A new user or token has no permissions. A token's effective rights are its own ACL entries intersected with its user's, so the bot's user needs the same role as the token. The user must have no usable password (whether PBS allows a password-less user is **[unverified]**).
- Role contents (code): `DatastoreReader` = Audit + Verify + Read; `DatastoreBackup` = Backup only; `DatastorePowerUser` = Backup + Prune; `DatastoreAdmin` = everything but Allocate. The docs page describes the reader as "inspect content and do restores"; the code also grants Verify, which is exactly what the bot needs.
- What a reader cannot do (handlers): forget a snapshot or group, prune, run garbage collection, create or delete a namespace, clear the "protected" flag, edit prune or sync jobs. Writers with `DatastoreBackup` cannot delete either, because forgetting needs Modify or Prune: PBS is effectively append-only for them.
  One caveat from the code: a Backup-role token that owns a group can clear the protected flag of its own snapshots, so writer tokens must not be the ones that protect milestones.

Setup, done by the human admin of the backup system:
1. One namespace per owner (or per host); each host's backups land in its owner's namespace.
2. Create `datamanager@pbs` and a token `datamanager@pbs!watch`, both with `DatastoreReader` on that namespace path (`proxmox-backup-manager acl update /datastore/<store>/<ns> DatastoreReader --auth-id ...`). No ACL at the datastore root.
3. One `DatastoreBackup` token per backup writer, on its own namespace only. Never Prune, never Modify.
4. Prune jobs, GC schedule, verify jobs and the admin account stay on the PBS side. Their credentials never reach the bot host or any stack.
5. **Negative test before trusting it:** with the bot's token, a forget, a prune call and a GC call must each return 403.

Bot tools (they match the `backup` profile of `ops/hostcare/HOSTCARE.md`):
- `backup_list`, `backup_status`: age per group, verify state, size; a read-only API poll, no shell, no exec key.
- `backup_verify`: verify the newest snapshot per group, plus a weekly sample of older ones. A corrupt chunk found by verify is renamed `*.bad`, the only datastore change this role can cause, and it is benign. Whether verify needs the encryption key is **[unverified]**; whether read-only maintenance mode blocks verify is **[unverified]**.
- `backup_restore_test`: restore into `scratch_dir` on the bot's own account, check the files, wipe. Whether the bot holds the encryption key for encrypted backups is an owner decision. Restore **onto live data is not a tool**: datamanager makes a verified copy, a sysadmin or tecnico task applies it, class 3 of section 14.
- Stale alert: the equivalent of the 26-hour rule of `ops/backup_watch.py` (`STALE_H`): tell the owner when the newest snapshot of a group is older than the threshold or a verify state is `failed`. The file-level "shrunk or vanished" idea cannot be done cheaply on PBS (it would mean restoring); use a snapshot-size delta plus a sampled restore test. Whether the snapshot catalogue can serve as a cheap file listing is **[unverified]**.
- A **special request**, for example "restore this snapshot", arrives as a task from sysadmin or from the owner and runs as a restore into scratch. It never becomes a delete or an overwrite.

Two lines of `ops/hostcare/HOSTCARE.md` (`backup` profile) must change: drop `prune` from the tool list (the bot never deletes; the retention floor lives in the PBS prune job, which the bot cannot edit) and drop `backup_run` (a host-side systemd timer the bot does not control runs the backup with the writer token).
`ops/backup_watch.py` deletes only its own fingerprints and 30-day small-file copies under the operator's backup folder: derived data, acceptable, and not a PBS pattern.

**Protection and a second copy** (https://pbs.proxmox.com/docs/backup-client.html, https://pbs.proxmox.com/docs/maintenance.html, https://pbs.proxmox.com/docs/managing-remotes.html):
- The protected flag blocks prune and `snapshot forget`; it is not carried over by sync, so set it again on the target. Prune removes snapshot metadata and garbage collection frees chunks after a 24 h 5 min grace period.
- Sync jobs can pull or push; `remove-vanished` deletes on the receiving side what vanished at the source, so it is a human-only setting. Datastore maintenance modes (`read-only`, `offline`) are a human switch for incidents.
- Tape can go off-site; WORM cartridges need a media pool with retention `keep` (https://pbs.proxmox.com/docs/tape-backup.html). The S3 datastore backend was a tech preview in PBS 4.0 and is supported from 4.2 per a news report (https://heise.de/-11278487); how it interacts with Object Lock is **[unverified]** (garbage collection deletes objects, so it probably conflicts with locked ones).

**On cloud object storage (the other option).** The shape is the same, in the provider's vocabulary (S3 names below; check each provider's S3-compatible implementation **[unverified]**):
- datamanager's credential: list and get only (`s3:ListBucket`, `s3:GetObject`, `s3:GetObjectVersion`), on the owner's bucket or prefix. No delete of any kind, no lifecycle or retention or bucket-policy change, no bypass of retention.
- writers: put-only credentials, one per host.
- **Object Lock in compliance mode** gives a time-lock with no executor: a locked object version cannot be deleted or have its retention shortened by any user until the date (https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html; not re-read in this session **[unverified]**). It needs versioning, and its lifecycle and retention settings are owner-only.
  The price is cost: locked data cannot be removed early, even by mistake, so the retention period is a deliberate choice.
- The cloud account root and the keys that can change lock and lifecycle live in the owner's vault, outside every bot host.

**Where the backups live decides what "no rights over backups" means** (section 10.1): a PBS on another machine, or cloud storage with the credentials above, makes it a wall. A backup folder on the site host does not.

### 11.5 datamanager: a text-only expert in keeping the business's data

The backup role needs no voice and no big model: text only (no speech, no image or video skills), the smallest LLM that is enough, packs `equipo` plus
one narrow backup pack. It is mostly a monitor and reporter: it reads freshness, verify and sync state from the backup system, compares them with a
short written policy, alerts through Zabbix and the ops-bot path, and otherwise sends only a periodic summary. It only reads, lists and verifies, and tests
restores into scratch; it holds no delete or write right on any backup target. Anything that would remove data is a proposal through `gateway cerrojo pedir`
that the owner arms with the proof of `STEP_UP_AUTH.md`.

Three physically separate places: A production, B a backup server on another machine and admin account, C an off-site copy; plus one offline or immutable copy
that a compromised B or C cannot alter. Its policy table per data class (recovery point and time objectives, places, restore-test calendar, legal retention
flagged for a lawyer) is operator-set and lives in the backup system's own jobs; the bot compares reality with it. Checks include the age of the newest verified
snapshot, verify state, last copy to C, offline-copy age, space on each backup host, and the age of the last restore and key-recovery tests. It informs and never acts.

## 12. Two Zabbix-connected bots: novedades and tecnico

Both bots see the monitoring, each through **its own Zabbix user and its own read-only API token** and its own focus. The intent is that neither token can change anything in Zabbix; what makes that true is the read-only permission set on the Zabbix user, which the owner configures. The gateway's save-time check only refuses Admin and Super admin roles: a "User" role that was granted write permission cannot be detected from the gateway (its own help text says so). This is already the shape of the existing code: `gateway zabbix` is read-only, takes the url and token from the stack's `.env` (`gateway servicios guardar zabbix`, or the keys page) or from the operator's `"zabbix"` entry, and its save-time check refuses a token whose role is Admin or Super admin.

| | novedades | tecnico |
|---|---|---|
| Question it answers | "What is installed and which versions, and does any advisory touch it?" | "Is the site healthy, and what changed?" |
| Focus group | the owner's hosts, but only what the inventory needs | the host group of the site it looks after (`gateway zabbix focus GROUP`) |
| Reads | agent and user-parameter items that report versions (OS, web server, PHP, database engine) as far as Zabbix is configured to report them; host list and tags | problems and events, triggers, availability, load, disk, memory, certificate expiry, web checks, and the backup stamp item if the owner adds one |
| Does with it | crosses it with advisories and feeds, files a task for tecnico | files tasks for developer (code) or sysadmin (host), or fixes within its own profile |
| Token | its own Zabbix user, role type "User" (not Admin, not Super admin), read permission on its host groups only | its own Zabbix user, same role, read on the site's host group only |

Rules:
- **Two users, two tokens, not one shared value.** The pool of section 9.1 lists `zabbix` as one owner value usable by several bots; for these two bots it is per stack instead, so one leaked token reveals one focus and can be revoked alone. Section 10.2's rows "Keys from the pool: `zabbix`" read as "its own `zabbix` token, per stack".
- **Zabbix text is untrusted data.** Host names, tags and item values are written by other people and machines; the gateway already prints them capped on one line (`gateway.py`, the Zabbix helpers). Novedades reads outside text all day, which is why it holds no SSH key and no deploy key.
- API tokens need Zabbix 6.4 or newer per the gateway's own check; token creation is in the Zabbix user settings (https://www.zabbix.com/documentation/current/en/manual/web_interface/frontend_sections/users/api_tokens; not re-read in this session **[unverified]**).

**Can the keys be loaded now? Partly yes.** The command exists, takes a per-stack token, and checks it with real calls before saving. What is not ready, in order:
1. Zabbix itself: the two users, their role and their read-only host-group permissions, and the host groups for each focus have to exist first. That is the operator's side of Zabbix.
2. The pack: today Zabbix comes with the `sysadmin` pack (`skill_packs.json`: sysadmin, network diagnostics and Proxmox view together). Turning that pack on for novedades gives it more skills than its job needs, with no keys behind the extra ones. A narrower pack with only the Zabbix view (name to choose, for example `monitoreo`) is the clean answer; it is a change in `skill_packs.json`, not made here.
3. The save-time token check is **unverified against a real Zabbix**: the selftest uses a fake and the code says so (`user.checkAuthentication` with `{"token"}`, role type returned by Zabbix 7). Load the first token on one stack, read the result, then the second.
4. The two stacks for novedades and tecnico have to exist (provisioning and the `equipo` pack, phase P1).

So: loading can start as soon as 1 and 3 are done on one stack; 2 can wait if the extra skills are accepted for now.

## 13. The approval-source rule

The rule: **where an order or approval arrives decides whether it counts as human.** Telegram is the human channel. Gitea is a place where bots write, so it is not.

### 13.1 Sources

| Source | Counts as | May request or propose | May authorize a class 3 or 4 operation (class 5 has no channel at all) |
|---|---|---|---|
| The owner's Telegram chat, an owner-only command (`/armar`, `/ejecutar`, `/cancelar` below) typed by the owner's id | human input | yes | yes, per 13.2 |
| A controller's Telegram chat | human input of a lower rank | yes | class 3 only if the owner allows it; never 4 |
| A Gitea task, comment, PR text, commit message, or anything a bot account wrote | bot-sourced: may be hallucinated or injected | yes: it can **request and propose** | **never** |
| A Gitea comment or task written by a human account | still treated as bot-sourced: text in Gitea cannot be told from pasted or forwarded text | yes | **never** |
| Another bot's answer, a `hermes peer` reply | untrusted data | no | never |
| Zabbix, feeds, advisories, web pages, email, a forwarded Telegram message, a file | untrusted data | no | never |
| The model's own statement ("the owner approved") | nothing | no | never |

**Never authorizes** covers: deletes, restores over live data, prune and retention changes, OS or version upgrades, and publishing to the public. A bot reading a Gitea task that asks for one of these may call `gateway cerrojo pedir` (13.2); that creates a **proposal**, nothing more.

### 13.2 What "approved by Telegram" must mean in practice

A model can type "the owner said yes". So the approval cannot be text the model reads. It must be:
1. **A command handled by code, not by the model:** `/armar <id> <code>`, `/ejecutar <id> <code>`, `/cancelar <id>`, owner-only, intercepted before the model like `/parar` and `/dormir` today (the owner-only gate of section 1). How strong the proof must be for each class (a button, a TOTP code bound to the action, a passkey on our own page), and how the executor checks a signed approval, is in `STEP_UP_AUTH.md`; the `<code>` below is the weakest form of it and is superseded there for classes 3 and 4.
2. **Bound to the exact action:** `<code>` is the first characters of a hash of the action, so a habitual tap on "ok" cannot approve a different action.
3. **Described by the system, not by the bot:** the Telegram message shows the action rendered from the catalogue entry and its validated parameters (for example "forget snapshot X of group Y in namespace Z"), plus who proposed it with the whole chain and the Gitea task number if any. The bot's own prose is not shown as the description.
4. **Sent by a channel the role bot does not control** for class 4 (and for class 3 if the owner chooses): a small lock service (14.2) with its own Telegram bot token, answering only to the owner's id. A hijacked role stack then cannot forge "the owner armed it". For class 3 the arm command may instead come through the stack's own owner-only commands, but the delay, the re-confirmation and the checks of 14.2 still run in the lock service. For class 2 the stack's existing `approvals: manual` prompt (a Telegram tap by the owner's id) is enough.
5. **Honest limit:** a stolen phone or a taken-over Telegram account is human input to the system. The delays of section 14 exist partly for this, and so does the optional second channel (a lock service on another channel). `STEP_UP_AUTH.md` narrows it: for classes 3 and 4 a second factor on a different device means the Telegram account alone cannot arm or run the operation (section 1 of that note lists how accounts are taken over; section 9 is the owner's Telegram hygiene checklist, doable today).

### 13.3 The one exception that is not text: the human merge

Merging a PR on a site repo is an authenticated action by a human account, and branch protection (section 2) keeps every bot out of the approvals and merge lists. It is not "text in Gitea". It stays the approval for the **production deploy of site code**, which is reversible (`git revert`, rollback) and class 2 (section 14).
Everything irreversible, and the first publication of a new site or domain, still goes through Telegram. This is a reading to confirm: the stricter alternative is a Telegram confirmation on every production deploy.

## 14. Time-locks for dangerous operations

Principle: a human yes is necessary and not sufficient. Destructive operations also wait, so that a mistaken, injected or hallucinated request, and a stolen session, have time to be noticed. **Nothing irreversible happens in a hurry**, and there is no "urgent" flag that shortens a delay: the only faster path is the human at the system console (class 6).

### 14.1 Operation classes

The delays below are proposals for the operator to set. The proof the owner must give at each level (low: the Telegram id; medium: id plus a button showing the exact action; high, class 3 and **spending money**: plus a TOTP code bound to the action and a re-ask at the end; irreversible, class 4: a passkey on our own TLS page, days of delay, a second-channel notice and optionally a second human) is designed in `STEP_UP_AUTH.md`, which also fixes the build order: TOTP first, passkeys second.

| Class and examples | Who may request | Who may approve | Delay | Where it is enforced |
|---|---|---|---|---|
| **0 Observe.** Read Zabbix, list or verify backups, read a repo, read a preview | any role, within its profile | nobody | none | read-only credentials on the host (Zabbix read-only user, PBS `DatastoreReader`, forced commands, hostcare level 0) |
| **1 Reversible, own scope.** Push a branch, open a PR, deploy a private preview, draft a post, restore into scratch, file a task | the role that owns the scope | nobody; reported in one line | none | deploy key limited to branches, `gateway postiz` creates drafts only, `scratch_dir` only, board token scopes |
| **2 Reversible on live, small.** Merged-code deploy, restart one app or unit, a config change inside the site, schedule a post, a package update whose rollback is tested | tecnico, developer (through the merge), sysadmin, marketing | the owner in Telegram (the stack's manual approval); for site code the human merge (13.3) | none; scheduled posts keep a minimum lead (proposal 60 min) and a cancel | hostcare level-2 prompt and `NEVER` list on the host, branch protection in Gitea, `gateway postiz` policy |
| **3 Risky.** OS or PHP or database engine upgrade, schema migration, firewall or sshd change, DNS or domain change, restore over live data, the first post on a new channel | sysadmin or tecnico (a restore is requested by them; datamanager only prepares the verified copy) | the owner only, in Telegram, with the exact action shown | hours (proposal 4 h from arming; the owner may lengthen) and a **re-confirmation** at the end | the lock service plus the host's own gate: the backup stamp must be recent and verified (`needs_backup_ref`), checked by the host, not by the bot |
| **4 Irreversible.** Forget one snapshot or a group, run prune or garbage collection, shorten retention, destroy a VM, disk or volume, drop a database, delete a repo or an org, destroy or rotate away an encryption key | proposal from any role in the chain; **armed only by the owner**, from Telegram | the owner only, from Telegram, **twice** (arm, then confirm at the end) | days (proposal 72 h; 7 days for a retention change or anything bulk) | on the system that holds the credential: PBS ACLs (the bot has no Modify or Prune), protected flags, Object Lock on cloud storage, the only delete credential held by the lock service; a floor the service refuses to go below (never fewer than the newest N verified copies per group) |
| **5 Console only.** Delete all or most backups, remove the last verified copy, change ACLs, tokens or users, change the lock service's approver list or delays, disable verify or prune jobs, datastore maintenance mode, encryption key custody | nobody through any bot, any channel, any chat | the human at the system with the admin account | not applicable: a deliberate act at the console (a written cool-off note is recommended) | the credentials for these exist on no bot host and the lock service has no catalogue entry for them: there is no path to refuse, because there is none |

"Delete everything" is therefore class 5 by definition. A request of that shape is refused by the catalogue and reported to the owner as a refused proposal.

### 14.2 The mechanism

A small **lock service**, run by the operator on a host that is not a bot stack, with one instance per system that holds a dangerous credential (the backup system; each site host for class 3). It is design only.

1. **A fixed catalogue of operations.** Each entry has an id (for example `backup.forget_snapshot`, `host.os_upgrade`, `restore.apply`), typed parameters, its class, its delay, its precondition checks and the fixed argv it runs. An operation not in the catalogue cannot be requested. The bot calls `gateway cerrojo pedir <id> <params>`; `gateway cerrojo estado` lists the bot's own proposals; the gateway has no arm, run or cancel command.
2. **A request becomes a pending record:** id, class, rendered action, action hash, the chain and source (Telegram, or which Gitea task), created, `not_before`, expiry. A proposal from a Gitea task or from a bot starts as `propuesta` and the clock does not run.
3. **Arm.** The owner sees the rendered action in Telegram and sends `/armar <id> <code>` (13.2; the code and its binding to the action are specified in `STEP_UP_AUTH.md` section 4, and the executor accepts only an approval signed by this service, section 3 there). The clock starts at arming, not at the proposal. The message says the exact action, the delay and `/cancelar <id>`.
4. **Wait.** Reminders at the midpoint and one hour before. `/cancelar <id>` works at any moment, from Telegram or the console. Any change to the action (a different parameter) is a new record and restarts everything. At most one irreversible (class 4) operation is armed at a time, and the next one cannot arm until 24 h after the previous one ran (proposals).
5. **Re-confirm at the end.** At `not_before` the owner is asked again, with the same rendered action, and has a window (proposal 24 h) to send `/ejecutar <id> <code>`. No answer means the record expires and nothing runs.
6. **Re-check, then act.** The service verifies the preconditions at that moment (fresh verified backup, the target still exists and is the same, the floor of verified copies, the protected flag) and runs the fixed argv with the one credential only it holds. The result goes to the owner and to the board as a `resultado`, with names and ids, never contents.
7. **Where each system helps by itself.** PBS has no built-in delayed delete (https://pbs.proxmox.com/docs/maintenance.html), so the delay lives in this service; Object Lock on cloud storage gives a delay with no service at all (11.4); PBS protected flags and the garbage-collection grace period are a second layer.

**Honest limits of the service.** It holds the one delete credential (class 4), so whoever has root on its host holds that power and can bypass the delay: the wait is software, and it stops a mistaken, injected or hallucinated request and a hijacked bot stack, not a person or a model that has taken over the lock host. Only storage that enforces the wait itself (Object Lock in compliance mode, PBS protected flags, WORM tape) is a wall against that, which is why 11.4 prefers it where available. Keep the service on its own small host, with its credential files readable by its own account only, and treat its host as part of the backup system's trust boundary. Class 5 is stricter than the operator's wording (no bot channel at all, even with a human yes): it is a deliberate choice, change it only by decision.

Time comes from the service's own host clock, never from a message. Telegram text is only the carrier of the owner's command; the model is never in the path of arming or executing.

### 14.3 What a bot may do instead

Everything a bot needs short of the dangerous step: prepare (a verified copy in scratch, a branch with the fix, a written rollback), propose (through `gateway cerrojo pedir`), explain to the owner in one line what it asks and why, and wait. A bot that cannot continue sets `estado/necesita-persona`.

## 17. The designer role: generative media and video editing

Status: design only. A branch off the ladder like developer and marketing (11.1): it uses the same board, pool and chain rules and adds no mechanism.

**Job.** Make images, video, sound and edits with the generative tools and the editors (`gateway image`, `gateway makevideo`, `gateway enhance`, `gateway transcode`, the DaVinci Resolve and EffectCraft tools, `gateway maquina`), and hand the finished assets to the developer (for the site) or to marketing (for a post). It does not look at monitoring, news or advisories, has no SSH, and holds no social-network account.

| | designer |
|---|---|
| Holds | its LLM key from the pool; only the media keys its role needs (section 9: allowlist per role); its own access to the machine-power provider through `gateway maquina` (the person turns a machine on, not the bot, `MACHINES.md`); Gitea board token; a write deploy key for the owner's **assets** repo (branches only, below) |
| Never holds | Zabbix or any monitoring token; news, feed or advisory skills; any SSH or hostcare key; any social-network or Postiz key (marketing's); the site repo's deploy key (developer's); backup credentials; any Cloudflare or DNS token; a cloud-GPU account (section 19) |
| Packs | `creativo`, `edicion`, `maquinas`, `equipo`; not `sitio`, `sysadmin`, `revista` |
| Files tasks for (`peers`) | tecnico (the request for review, section 18), developer, marketing |
| Reads tasks from (`accept_from`) | developer, marketing, tecnico, owner |
| hostcare profile | none |
| Approval | the stack's normal ones; anything that spends money goes through section 18 and the step-up level "high" of `STEP_UP_AUTH.md` |

**Handing over an asset.** The privacy rule of section 3 stands: a file crosses as a name and a hash, or as a path inside a repo both can read. So the owner has an **assets** repo; the designer pushes to branches named `a/<slug>` (deploy key, branches only), and developer and marketing hold a read key. The task says: path, hash, size, what it is for, where it may be used, and "not included: the prompt or the person's photos used as input". Gitea limits for large video files in git were not checked **[not verified]**; until they are, large video is handed over by a path on an agreed share or not at all.

**Generative safety applies to every request** (`GENERATIVE_SAFETY.md`): a task is never permission to make a picture of a real person; the designer's own rules decide, and the answer comes back as data. Class A prompts only may go to a free cloud tier; a private chat's prompt never goes to a marketplace or community GPU host (`GPU_RENTAL_AND_MODELS.md`).

**Chains.** `owner > designer` is depth 0. `designer > developer` ("the hero picture is ready: path, hash, put it on page X", depth 1) and `designer > marketing` are depth 1; the request for review `designer > tecnico` is depth 1 and tecnico may then file for developer or sysadmin but never back for the designer (cycle rule, 10.3): the answer returns as a comment on the designer's task.

## 18. The designer's request, the cost estimate and the tecnico's review

**Why.** Generative work uses scarce, sometimes paid resources: a card that blocks everything else, rented hours, a provider's credit. The designer states what it wants and what it will cost before it spends, and a second bot with the machine view checks the estimate.

**The fixed template.** `gateway tareas nueva --para tecnico --plantilla pedido-diseno` (design; the gateway refuses a request with a missing field, in the fixed es, ru and en sentences like the rest). The fields are text the model fills, bounded to the 2 KB of section 3:

```
objetivo:       what is to be made and for whom (no personal data, no prompt text if it came from a private chat)
herramienta:    the tool or model, and WHY this one and not a cheaper one
costo:          GPU seconds, Wh, peak VRAM and RAM, where it runs (home / machine provider / cloud), money if any;
                every number tagged [M] measured, [Q] quoted, [E] estimate, with the row it comes from
alternativas:   at least one cheaper or faster path and what it gives up
bloquea:        the resources it occupies and for how long (the home card, RAM, a reservation)
```

A number with no tag is refused. A number tagged [M] must name its row in the measured documents (`VIDEO_BENCH_RESULTS.md`, `GPU_RENTAL_AND_MODELS.md` sections 2 and 7.1); a lookup file of those rows (`ops/measured_costs.json`, not built) would let the gateway check it. The measured numbers come from one 8 GB consumer card with 32 GB of RAM; nothing was measured on a rented card.

**Numbers the designer may quote** come from `VIDEO_BENCH_RESULTS.md` and `GPU_RENTAL_AND_MODELS.md` (time, energy, peak VRAM and RAM per task), never from its own prose.

**The tecnico's review.** Tecnico reads the request as data (an issue, section 3) and answers with a comment and a `resultado:`:
- **Feasible?** Does it fit the VRAM and RAM of the machine named, with what else is running (Wan 14B leaves no RAM for anything heavy)? Is the licence territory right (H3 and Hunyuan exclude the EU, UK and South Korea, and H3 also the USA, so a rented card must sit outside them **[LAWYER]**)?
- **Cheaper path?** The measured alternatives of the table (klein for images, 130 W, ComfyUI against Diffusers, fewer seconds, post-processing on the second card).
- **A corrected estimate**, with tags.
- **One recommendation:** `adelante` (go), `adelante-mas-barato` (go with the cheaper path), `necesita-dueno` (spends money or blocks something others need) or `no`.

**The review is a recommendation, not an approval.** Text from a bot never authorizes (13.1). So:
1. **Zero cost** means: a run on the home card that is already on, or that the owner's own machine account serves with no credit drawn. Electricity at home is stated in Wh in the request and is not counted as spending. The designer may proceed once the tecnico's review is on the task, and the review's comment number goes in its own note ("run proceeded after review #N"), so the board shows who looked.
2. **Anything that spends money** (provider credit, a rented card, a cloud bill) needs the owner's yes in Telegram. At the step-up level "high" (`STEP_UP_AUTH.md` section 2): the message is rendered by the lock service from the catalogue entry (`gpu.lease`: provider class, time limit, maximum rate, worst-case cost), shows tecnico's corrected estimate, and the owner proves themselves with the code bound to that action. Waking a machine on the machine-power provider draws the person's credit, so it is money, not zero cost. Today the person's own `/machine on NAME yes` (`MACHINES.md`) asks only for the word `yes`; the step-up level is a change to design, not a description of what runs now.
3. **No review within 24 hours** (a sleeping stack, the RAM guard) **[E]**: the designer does not proceed silently. It tells the owner in one line and asks whether to go without the review.
4. The numbers the owner sees are the service's, never the bot's prose.

## 19. GPU sourcing by tecnico

The tecnico, which already sees the machines through monitoring and the site's host, chooses where a GPU job runs and when. It recommends and prepares; it
does not hold a payment method. Sources in order of preference: the home GPU (no money, bounded by its 8 GB card), owned machines reached through the
machine-power provider (`MACHINES.md`), then cloud spot or variable-price GPUs for non-urgent work. A non-urgent task carries a deadline, a maximum runtime
and a maximum price per hour, and waits for a low price; the lease rules (hard time limit, reaper, prepaid balance, daily cap) are those of the `gpu-lease`
design in `GPU_RENTAL_AND_MODELS.md` (not built).

## 20. Marketing collects every party's OK before scheduling

**Rule.** Marketing schedules a post only when every party the post depends on has said OK to **this exact content**, and the owner says the last OK in Telegram. The OKs are a coordination list, not authority: bot text never authorizes (13.1), and the owner's step-up OK (class 2, `STEP_UP_AUTH.md` section 6) is the only approval that counts.

| Party | When required | What the OK means | How it is given |
|---|---|---|---|
| designer | the post has a picture, video or sound | the delivered asset is final | a comment `OK <digest>` on marketing's task, by the designer's account |
| developer | the post links to a page or release | the link is live and shows what the post says | the OK comment, **plus** a deterministic check by `gateway postiz` that the link answers 200, is not a preview address and is not private |
| tecnico | the post starts a campaign or an expected burst of visits (a size to set) | the host can take the load; where a campaign needs a GPU or machine, there is capacity | the OK comment |
| owner | always, last | schedule this | the stack's manual approval in Telegram |

**How it is built (design).** Marketing files one child task per required party (`marketing > designer`, `marketing > developer`, `marketing > tecnico`; depth 1 each, three open children, which is exactly the per-parent cap recommended in 10.3 and not yet built), each carrying the digest of the draft (SHA-256 of the post text, target networks and asset hashes). `gateway postiz programar N FECHA` refuses until, for the current digest, each required role's account has commented OK, then asks the owner. **Any change to the draft changes the digest and cancels every earlier OK**, the same invalidate-on-change rule as `STEP_UP_AUTH.md` section 3. Results come back as comments on marketing's task, never as new tasks upward. The first post on a new channel stays class 3.

**When a required party is already in the chain.** The cycle rule (10.3) refuses a child for a bot that is in marketing's `cadena`: a post that started as `developer > marketing` or `designer > marketing` cannot file a child back for that role. For that party the OK is asked and given by comment on the parent task that started the chain (the same digest, from that role's account), not by a new task. `gateway postiz programar` accepts either form, and the deterministic link check for developer's OK runs in both cases. The selftest of the gateway needs a case for it **(not built)**.

## 21. Where a task may start

- **Default: novedades.** The one bot that may file a task on its own initiative is novedades (it reads the feeds and the inventory). Other roles file only when the owner asks.
- **Any bot, when the owner asks it in its own chat.** The owner can ask designer, developer, marketing, tecnico or any other bot directly, and that bot may then file the follow-on tasks of the work (`nueva --pedido-persona`, depth 0, 10.3 "As built"). The flag is set by the model and is judged only on the held-task rule, so a lie can restart a chain at depth 0 where the bot holds no task that another bot filed. **Improvement to build:** the controls plugin, which runs before the model, records the time of the owner's latest message in a file only code writes, and the gateway accepts `--pedido-persona` only if that time is within a short window (15 minutes **[E]**). Then "a person asked" rests on something the model cannot set.
- **The board records the origin.** The header gains a gateway-written field `origen:` with one of `novedades`, `owner-chat` or `tarea #N` (the parent), next to `cadena`. It is derived from the same facts the depth rule uses, never from model text. Each task then shows who started the work as well as who asked whom.
- **The ladder rules apply to every origin:** maximum depth, no cycles, downward `peers`, neighbour-only `accept_from`, the load floors, and the approvals of 13 and 14. A task from the board is a request and never a permission.
