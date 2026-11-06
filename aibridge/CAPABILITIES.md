# Capabilities: packs, personal keys and delegation between agents (design, 2026-11-06)

Status: design plus the first piece in code (`needs` in `skill_packs.json`, shown by `paquetes`). The security packs themselves are not built yet;
see "Security tiers". Operator decisions this follows: bridgeai is MIT and public; the operator cannot provide third-party keys because of the
services' terms, so each person gets, pays for and answers for their own; a module is switched on when the person asks for it.

## The four rules

1. **A key is personal.** The person loads it, only their Hermes uses it, it never leaves their stack, and no other agent or person sees it (the
   operator does not either: it lives in the stack's `.env`, loaded through the keys page or `gateway servicios guardar`). The repo never carries a key.
   The operator's own key works on the operator's own stack only. No loan to anybody else, not even a temporary one: until a person loads theirs, the
   module runs on what needs no key and says what is missing.
2. **A module is a pack plus what it needs.** A pack in `skill_packs.json` may list `needs`: `[{"service": "abusech", "env": "ABUSECH_AUTH_KEY", "optional": true}]`.
   `service` is an id of `SERVICES` in `gateway.py`, which already holds the person-facing text in es/ru/en (`gives`, `without`, `how`, `note`, the link) and
   the check that validates a pasted key with a real call. `paquetes list` marks a pack whose key is missing ("🔑 falta tu clave"), and `paquetes on` says
   what is missing. Everything that needs no key keeps working. A service is added to `SERVICES` only together with the command that uses it.
3. **Delegating to another agent is for what needs no personal key.** Two cases:
   - A specialist stack run by the operator that offers only local, keyless capabilities (ClamAV, YARA-X, capa, Ghidra later). Allowed.
   - Another person's Hermes because it has the key. Not allowed: it would use their account for someone else's task and send one person's file to
     another person. A capability that needs a personal key stays with each person.
4. **The verdict is honest.** "Not detected" is never "safe" (wording below).

## What crosses between agents

Hermes already has the transport (verified in the pinned image, commit 818c13be): `hermes peer add/dm/run/status/stop` over the callee's
OpenAI-compatible API server (`/v1/runs`, `/v1/responses`, Bearer `API_SERVER_KEY`), and `model_routes` aliases so the caller sends an alias and never
sees the callee's model keys. A2A v1.0 exists (Linux Foundation, 2026-04) but adds nothing for a few agents on one LAN. So nothing is invented here, only rules:

- Pass the minimum: the question, the file or only its hash, the limits (time, size). Never the caller's memory, transcript, other files or keys.
- The callee is a dedicated specialist stack, never a person's own: a peer message lands in the callee's canonical chat, so it shares that
  person's transcript and memory.
- One hop: the specialist has no peer of its own. Use `peer run` with an idempotency key (async), not `peer dm`.
- The answer comes back as untrusted data: a small structured summary (20 KB or less), quoted by the caller, never able to trigger a tool. Text produced
  by a decompiler, a scanner or a sample can carry prompt injection.
- The caller tells the person that the file went to the specialist agent, and says which.
- The caller holds only the specialist's API key. The specialist holds its own tool keys. Waking the specialist goes through the waker like any stack.

## Measuring what a context set is worth

The same prompts, two profiles on one pinned model, skills off versus on, otherwise identical tools (design of SkillsBench, arXiv 2602.12670, where focused
skills beat exhaustive bundles). 20 to 30 prompts per area, each with 4 to 8 yes/no checklist items written before running; three runs per prompt through
`/v1/runs` with a fresh session; record tokens, seconds, tool calls and errors; a judge from another model family, blind to the arm, plus a pairwise
preference in both orders; report paired differences with a bootstrap interval. Success is the headline, tokens and latency are costs. A skill that does
not move success and adds tokens is dropped. Measured 2026-11-06: the skills index is about 11% of a first request (1,970 of 18,000 tokens), so the
packs alone save at most 7.6%; the bigger fixed part is `SOUL_bridgeai.md`.

## Security tiers (research 2026-11-06)

| Tier | Where | Contents | Weight |
|---|---|---|---|
| 1 Revisión rápida | in the image | hash lookup with the person's own key, file type, gitleaks, bandit, pip-audit | under 100 MB, seconds |
| 2 Auditoría profunda | on-demand sidecar over a file queue | ClamAV, YARA-X with community rules, capa, FLOSS, Detect It Easy, semgrep | 1 to 1.2 GB disk, 1 to 2 GB RAM |
| 3 Ingeniería inversa | not built | Ghidra headless (570 MB zip, JDK 25, 2 GB heap by default) | about 2 GB disk, 2 to 4 GB RAM per binary |

Never by default: executing a sample; scanning hosts the person did not declare as theirs; nuclei; uploading a private file anywhere; printing a secret
found in code. The sidecar (a host service that runs the tool in a container with no network and the file read-only, and returns the summary) is built once
for tiers 2 and 3. ClamAV is one shared container, not one per stack (1.2 GiB or more of RAM when loaded).

## abuse.ch MalwareBazaar: the person's step by step

Terms read 2026-11-06 (page updated 2026-10-21): free for authenticated, not-for-profit use; no high-volume harvesting; the data may not be used to train or
improve an AI model; access may be cut without notice; the portal now announces API rate limits (an account with unusually high volume may be limited for up to
72 hours). So the command caches every result by hash, asks only about executables and archives that came from a public URL (never a person's own
documents: a hash tells a third party the file exists), backs off on any limit answer, and the skill says that results are not saved to memory or any dataset.

1. Sign in at https://auth.abuse.ch/ (the page offers Google, GitHub, X and LinkedIn).
2. Profile Settings: a username (required, unique, used in the login and in the profile's URLs) and a display name (required, shown on the profile); confirm the
   email if it asks. **Do not reuse a name the person already uses anywhere**: the profile is public by default and a reused name links this account to who they are.
   The agent offers a random one on the spot (`python3 -c "import secrets; print('hermes-' + secrets.token_hex(3))"`) and a generic display name, and the person
   switches on **Hide Profile** (the page has it) so the account stays out of the platforms' tables and leaderboards. The sign-in goes through a provider the
   page lists (Google, GitHub, X or LinkedIn) and the account keeps that email, verified: say so, and let the person choose which provider or email to use.
   Not verified: whether there is a sign-up with only an email.
3. Under "Optional", the profile has an **Auth Key** field: copy it. Not verified: the exact click that generates or reveals it was not visible in the page we
   were given; the first person who does it should correct this line.
4. Paste it in the keys page of their Hermes, or give it to the agent only if the person decides to (`gateway servicios guardar abusech`, which checks it with
   a real call before storing it).
5. To remove it: `gateway servicios quitar abusech`, and delete or regenerate it in the abuse.ch profile. Removing it never breaks anything else.

API facts (https://bazaar.abuse.ch/api/): header `Auth-Key`, POST form `query=get_info&hash=<sha256|md5|sha1>` to `https://mb-api.abuse.ch/api/v1/`;
`query_status` is `hash_not_found` when unknown, `illegal_hash`, `no_hash_provided`, `http_post_expected`; what a wrong key returns is not documented, so the
key check accepts only `ok` or `hash_not_found` and shows the status it got for anything else.

## Verdict wording (translate for the person)

- Clean: "Checked: the hash is not in the malware lists I could ask, and the local scan found nothing (signatures dated X). That does NOT prove it is safe, only
  that it is not a known threat. Trainers and mods always carry risk: if you run it, do it on an account or machine you can afford to lose."
- Detected: "<scanner> flagged it as <name>. Game trainers are often flagged wrongly, but I will not send it on unless you tell me to."
- Not scanned: "Not scanned (too large, encrypted, or the scanner is off). Treat it as unchecked."

## Hash lookup versus ClamAV (they answer different questions)

| | Hash lookup (built: `gateway virus`) | ClamAV (not built) |
|---|---|---|
| Question | "is this exact file a known sample?" | "does this file match a known family or pattern?" |
| Finds | only a file whose bytes are already in a list | also variants of a known family, if a signature covers them |
| Misses | anything new, rebuilt or repacked (a changed byte changes the hash) | new families with no signature; game trainers are often flagged by mistake (packers, injection) |
| Cost | no RAM, no disk, a few KB per query; a personal key for MalwareBazaar | 1.2 GiB or more of RAM when loaded (ClamAV advises 3 GiB), about 460 MB of disk, a daily signature update |
| Privacy | the hash goes to two public services | the file never leaves the machine |
| Where | in the image, a skill and a command | one shared container on the VM behind the file queue (one per stack would triple the RAM) |

They complement each other, so the tiers stay: the hash check is tier 1 and is done; ClamAV is tier 2 and waits for free disk and the file queue. A third-party
API that takes the FILE is out: it would send a person's file away.

## Order of work

1. Done: `needs` in the catalog and in `paquetes`; this document.
2. Done (2026-11-06, not yet deployed): `gateway virus FILE` (SHA-256, CIRCL hashlookup with no key, MalwareBazaar with the person's key, cache, daily cap, one-hour back-off),
   `abusech` in `SERVICES` (es/ru/en, key check), the `seguridad` pack with the `file-check` skill and its `needs`. `gateway_virus_selftest.py` runs against fake servers. Not verified
   against the real MalwareBazaar: what it answers to a wrong key, and the exact shape of a `found` answer; the first real key will show it.
3. Free disk on the VM (ClamAV and the sidecar do not fit in 13 GB), then the file queue and the shared ClamAV with one daily signature update (freshclam asks no more than hourly).
4. The specialist stack and the first A/B run.
5. Done (2026-11-06, not yet deployed): `SOUL_bridgeai.md` slimmed from 17,147 to about 11,000 characters (-36%): incident anecdotes (dates, numbers) dropped, every imperative kept, venue-list detail moved to `SKILL_maps.md`, tool recipes left to their skills. Three drafts (about 15k, 10k, 7.4k) were each audited rule by rule against the original; the 10k one was taken with the auditor's fixes. The 7.4k draft lost a safety rule (no `apt`/`sudo`) and seven behaviour rules, and a small local model follows concrete rules better than abstract ones, so a deeper cut waits for the A/B harness (item 4) to show it costs nothing. Dropped anecdotes stay in git history.
