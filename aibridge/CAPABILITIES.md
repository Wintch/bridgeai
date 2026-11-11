# Capabilities: packs, personal keys and delegation between agents

Status: `needs` in `skill_packs.json` (shown by `paquetes`), the hash lookup (`gateway virus`, tier 1) and the local ClamAV scan (`gateway virus --deep`,
tier 2, a host service next to the waker) are built; tier 3 (Ghidra) and the specialist stack are not. See "Security tiers". Policy this follows:
bridgeai is MIT and public; the operator cannot provide third-party keys because of the services' terms, so each person gets, pays for and answers
for their own; a module is switched on when the person asks for it.

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

Hermes already has the transport (verified in the pinned image): `hermes peer add/dm/run/status/stop` over the callee's
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

## Measuring what a context set is worth (planned)

Not built: an A/B run of the same prompts on two profiles of one pinned model, skills off versus on, judged blind by a model from another family with
paired differences (design of SkillsBench, arXiv 2602.12670, where focused skills beat exhaustive bundles). Success is the headline; tokens and
latency are costs; a skill that does not move success and adds tokens is dropped. The skills index is about 11% of a first request, so packs alone
save at most about 8%; the bigger fixed part is `SOUL_bridgeai.md`.

## Security tiers

| Tier | Where | Contents | Weight |
|---|---|---|---|
| 1 Revisión rápida | in the image | hash lookup with the person's own key, file type, gitleaks, bandit, pip-audit | under 100 MB, seconds |
| 2 Auditoría profunda | on-demand sidecar over a file queue | ClamAV, YARA-X with community rules, capa, FLOSS, Detect It Easy, semgrep | 1 to 1.2 GB disk, 1 to 2 GB RAM |
| 3 Ingeniería inversa | not built | Ghidra headless (570 MB zip, JDK 25, 2 GB heap by default) | about 2 GB disk, 2 to 4 GB RAM per binary |

Never by default: executing a sample; scanning hosts the person did not declare as theirs; nuclei; uploading a private file anywhere; printing a secret
found in code. The sidecar (a host service that runs the tool in a container with no network and the file read-only, and returns the summary) is built once
for tiers 2 and 3. ClamAV is one shared container, not one per stack (1.2 GiB or more of RAM when loaded).

## abuse.ch MalwareBazaar: the person's step by step

Terms as read in 2026-11 (re-read before relying on them): free for authenticated, not-for-profit use; no high-volume harvesting; the data may not be used to train or
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
`query_status` is `ok` (with `data`: a list of one record) or `hash_not_found` when unknown (also `illegal_hash`, `no_hash_provided`, `http_post_expected`).
Verified live with a real key: a wrong key answers **HTTP 403** with `{"query_status": "unknown_auth_key"}`; no `Auth-Key` header at all answers
**HTTP 401** with `{"error": ...}`; a known hash answers HTTP 200, `query_status: ok`, and a record whose fields include `signature`, `tags`, `file_type`, `first_seen`,
`sha256_hash`, `file_size`, `yara_rules`, `vendor_intel`; an unknown hash answers HTTP 200 `hash_not_found` with no `data`. The key check therefore accepts only `ok` or
`hash_not_found` and reports HTTP 401/403 as a rejected key; the code reads only `signature`, `tags`, `file_type` and `first_seen`, and keeps nothing else.

## Verdict wording (translate for the person)

- Clean: "Checked: the hash is not in the malware lists I could ask, and the local scan found nothing (signatures dated X). That does NOT prove it is safe, only
  that it is not a known threat. Trainers and mods always carry risk: if you run it, do it on an account or machine you can afford to lose."
- Detected: "<scanner> flagged it as <name>. Game trainers are often flagged wrongly, but I will not send it on unless you tell me to."
- Not scanned: "Not scanned (too large, encrypted, or the scanner is off). Treat it as unchecked."

## Hash lookup versus ClamAV (they answer different questions)

| | Hash lookup (built: `gateway virus`) | ClamAV (built: `gateway virus --deep`) |
|---|---|---|
| Question | "is this exact file a known sample?" | "does this file match a known family or pattern?" |
| Finds | only a file whose bytes are already in a list | also variants of a known family, if a signature covers them |
| Misses | anything new, rebuilt or repacked (a changed byte changes the hash) | new families with no signature; game trainers are often flagged by mistake (packers, injection) |
| Cost | no RAM, no disk, a few KB per query; a personal key for MalwareBazaar | 1.2 GiB or more of RAM when loaded (ClamAV advises 3 GiB), about 460 MB of disk, a daily signature update |
| Privacy | the hash goes to two public services | the file never leaves the machine |
| Where | in the image, a skill and a command | one shared container on the VM behind the file queue (one per stack would triple the RAM) |

They complement each other, so the tiers stay: the hash check is tier 1 and ClamAV is tier 2; both are done. A third-party
API that takes the FILE is out: it would send a person's file away.

## Feedback, the manual and what the administrator sees

The person can leave a note the administrator reads and keep one private. The administrator reviews which calls were made, to improve the assistant,
within the level the person chose. The person-facing text is in `aibridge/manual/`.

| Piece | What it is |
|---|---|
| `opinion.py` (`/opinion`, `/compartir`) | `/opinion TEXT` writes `.opiniones.jsonl` in the person's `/workdir` (the administrator reads it with `ops/opiniones.py`); `/opinion privado TEXT` writes `.opiniones-privadas.jsonl`, which no tool of ours opens; a key pasted into a note is blanked; the slash command never logs the text. |
| `/compartir nada\|uso\|todo` | `.compartir.json`; no file means `uso`. **nada**: the administrator does not review the person's use, not even counts (technical records the server needs stay, no message text). **uso** (default): tools used, counts, errors, timings, model; never message text or file contents. **todo**: the administrator may read the conversation, only to improve; secrets are masked. |
| `ops/chat_review.py`, `ops/stack_usage.sh` | Read the person's `/workdir` (mounted at `/w`) and obey the level: `nada` refuses even the structure; text mode needs `todo`, or `--own` on the operator's own stack (never over a `nada`). Test: `ops/chat_review_consent_selftest.py`. |
| `manual.py` (`/manual`) | Copies `manual/MANUAL.{es,ru,en}.md` to `/app/manual`; `/manual` answers a short guide and the PDF; `manual_selftest.py` checks the three keep the same sections and promise nothing false. |
| 👍/👎 on a reply | `aibridge-feedback`: a vote for the model that answered, no text. |

The levels are an agreement about what the administrator looks at, not a technical barrier (the administrator runs the server), and the manual says so.
Keys are not used or shared by the administrator, but some free models run on a shared server key until the person loads their own, and the manual says that too.

## Tier 2, the local ClamAV scan

`gateway virus --deep FILE` (agent side, `gateway.py`) and `ops/scan/scanner.py` (host side, a `--user` service next to the waker). They talk through files in the stack's
own `/workdir/.scan/`, the same way `dormir` talks to the waker: `scanner.json` (heartbeat), `req-ID.json` (from the agent: only the file's path inside its container and
the language, the id being the first 16 hex of its SHA-256), `st-ID.json` and `res-ID.json` (from the host: a few validated fields). The file never travels in a request;
the host copies it out of the container with `docker cp` (a tar stream, size-capped at 300 MB, symlinks refused, path checked), puts it in a private temp dir and scans it in a
throw-away container: `clamav/clamav` pinned by digest, `--network none --read-only --cap-drop ALL --no-new-privileges --user 100:101 --memory 2g`, the file and the
signature volume mounted read-only, `clamscan` with the size, time and recursion limits raised to the 300 MB cap and set to ALERT (the defaults would call a 125 MB file clean),
and encrypted archives and documents set to alert (a password-protected zip is exactly what trainers ship as). One scan at a time; started only if
`MemAvailable - 1800 MB >= reserve` (the waker's own reserve), else the answer is "busy: no memory" at once; the host never evicts or waits. A scan costs RAM, not a third party's
quota, so the agent caps it at 10 cache misses per day per person. A result is reused while the signatures have the same date and it is under a week old.

What the agent sees: the hash lines as before, then one "Análisis local" line (clean, partial, found with at most five validated names, busy, no memory, too big,
timeout, error code, not installed) and a combined verdict. A scan still running exits 4 with "pendiente" and the same command joins it (one call waits 150 s, the terminal
tool's limit is 180 s; the total cap is 600 s). `--deep` also accepts a document: only the local scan runs, no hash leaves.

What it does NOT do, and the report says so: ClamAV is signature-based (no sandbox, no behaviour), cannot see a brand-new sample, and flags game trainers, cracks and patches
by mistake; a name starting `PUA.` or `Heuristics.` is a weak suspicion. A clean pass is "no known signature matched", never "safe". A real detection next to a scanner error line is
reported as found with partial set. Unconfirmed until the first real run: the exact `clamscan --version` format on the VM, volume ownership on first creation, scan time on a real 125 MB file
(measured here: about 12 s for a small file and 36 s for 125 MB of random data, plus about 10 s to load the signatures; a real 125 MB installer took about 200 s), and whether `docker cp` of a 125 MB file behaves on the VM.

Install (operator, once; `deploy_ops.sh` ships only tracked files, so commit first; it installs the units and enables the timer but never starts the service):
```
AIBRIDGE_HOST=user@host ops/deploy_ops.sh --apply
# on the VM
python3 ~/aibridge/ops/scan/scanner.py --update --init     # pulls the pinned image, creates the volume, downloads the signatures (about 108 MB)
python3 ~/aibridge/ops/scan/scanner.py --check             # everything should say ok
systemctl --user enable --now aibridge-scan.service
```
Not done: a waker change to subtract a running scan from its own RAM check (today only the scan's own 2 GB cgroup limit and a second RAM check right before it starts protect against a race with a wake: at 7 GB total, reserve 1500 and a 1800 MB scan, a wake admitted during the scan leaves about 900 MB, under the reserve; the scanner writes a `scan.running` marker so the waker patch is small), a ClamAV daemon (a scan
loads the signatures each time, about 10 s), YARA-X, capa and Ghidra (tier 3).

## Not built yet

The specialist stack for tiers 2 and 3 as a peer agent, the first A/B run, YARA-X and capa in the sidecar, Ghidra (tier 3), and a waker change that
subtracts a running scan from its own RAM check (today the scan's own 2 GB limit and a second RAM check right before it starts protect against a race with a wake).
