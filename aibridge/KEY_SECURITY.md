# Key security: keeping client keys on the client's side

Status: direction document. Sections say what is true today, what is the next small step (Phase 0), and what we are building
toward (Phases 1 and 2). Nothing in a later phase is to be described to people as live until it is. Policy text for key
ownership and key hygiene is in `DATA_LAW_AND_KEYS.md` (B.0 and Part B); the person-facing instructions are in
`ops/KEYS_GUIDE.*.md`.

## 1. Roles and responsibility

- **bridgeai is software plus a place where it runs.** We provide the code and the host that runs one assistant per person or
  bot. We are not a key provider: we do not hand out, resell or share keys, and nobody pays us for model access.
- **The person owns the account and the key.** They create their own provider account (NVIDIA, OpenRouter, Gemini, Groq, ...),
  accept that provider's terms, and paste their own key into their own stack on the keys page. An account is a person or a
  company; one account may use one key in several of its own containers, and a key is never shared across accounts.
  *True today:* the code still has a legacy path that can start a new stack on an operator trial key (`--nim-key` in
  `ops/provision_stack.sh`, marked `.starter-key`, with a welcome text that says so), and a stack's `.env` may carry an
  operator key. Phase 0 removes the path; until then the guides say it plainly and do not claim "we never give a key".
- **Testing versus production is between the person and the provider.** Whether a given use is allowed on a trial, a free tier
  or a paid plan is decided by the provider's terms. We advise which providers to try; we cannot know the person's plan and do
  not decide it.
- **Our responsibility is the custody on our side.** Once a key is in a stack, our job is that it is used only to run that
  person's assistant and that we are never the way it leaks.

## 2. Threat model

**What a leak costs.** A free key: lost quota, and abuse under the person's name. A paid key that bills per token: real money,
with no natural ceiling unless the provider enforces one, and it is silent until the invoice. Today nearly everything is free
tier; the design assumes that soon it will not be.

**How a key could leak from our side, ranked** (from reading the code; each item still needs a canary test on the guest stack,
never with a real key):

1. **The agent can reach the key.** Provider keys are stored in plain form in the stack's credential pool and `.env`. The agent,
   its terminal tool, the router and the keys page run as one user in one container. Hermes' own guards (read denylist,
   redaction by key shape, environment scrubbing by name, approval rules) are best-effort and upstream states they are not a
   security boundary. A prompt injection from a web page, a document or a forwarded message is the realistic attack, and the
   container has open internet access.
2. **Our own scripts and fallbacks use or copy keys.** Host-side tools read each stack's keys to check them and probe models;
   a stack can fall back to a key that is not the person's (for example one left from provisioning); backups hold the key files
   in plain form for days.
3. **A key pasted into a chat.** It is stored as typed, goes to the cloud model with the conversation, and stays in the chat
   provider's history.
4. **Transport and second entry paths.** Keys cross the local network in clear text between the public edge and the host; the
   assistant's own dashboard is a second place where keys can be set or revealed.
5. **Smaller items.** A provider's error text echoed to the browser; Authorization headers followed across HTTP redirects by
   standard-library clients; secrets passed on a command line.

**Spend without theft.** A key does not have to leave the container to cost money: anything inside the stack that can call the
local router spends the person's key through it. So a spend limit matters even if no key is ever stolen.

## 3. Principles

1. **Keys stay on the client's side as far as possible.** The master copy is the person's (a vault on their own machine). What
   our side holds is a working copy, and we minimise where it exists and how long.
2. **The agent never sees a key.** Not in its files, environment, tool output, chat or logs. Protection that depends on the
   agent behaving is deterrence, not a boundary.
3. **Least privilege.** Each component gets only what it needs: the model gateway can call allow-listed provider hosts, the agent
   can only talk to the gateway. (A target; today they share one container.)
4. **No key in chat, logs, backups or exports.** Only the last 4 characters or a short fingerprint are ever shown or stored
   as metadata.
5. **One account never uses another's key.** No fallback to a shared or operator key for a person's stack.
6. **A hard stop outside our control.** The only limit that still works after a leak is the one the provider enforces on the key
   (a spending cap). We ask for it and, where the provider exposes it, check it.
7. **Say only what is true.** The website and guides describe what is deployed; planned items are labelled planned.

## 4. Measures in phases

### Phase 0: now, small

- **Redaction.** Upstream's redactor (`agent/redact.py`) has no `nvapi-` or `thk_` shape, and its exact-value mask
  (`register_vault_redaction_value`) is fed only from external secret sources. Add those prefixes, and register every key in
  the credential pool and the stack `.env` with the exact-value mask, in a `patches/` file (same mechanism as the existing
  patches, which abort the build if the upstream text moved). Declare custom key names so Hermes keeps them
  out of the terminal environment, and keep secrets out of the compose `environment:` block where the stack `.env` can carry
  them. Check with `env` and the process environment inside a guest container: no secret-looking name.
- **Inbound guard.** A message that matches a known key shape is not passed to the model and not stored; the person gets the
  instruction to revoke it and use the keys page, in their language (Telegram deletion where the API allows).
- **Backups carry no keys.** Today the per-person archives (`ops/backup-stacks.sh`, 7 days) include the whole Hermes state
  with `auth.json`, and the operator-config archive includes each stack's `.env` and `credentials.txt`. The small-files store
  (`ops/backup_watch.py`, 30 days) already skips secret-looking names. Exclude `auth.json`, `.env`, `.telegram.env` (the
  Telegram bot token copy in the workdir) and `credentials.txt` from the per-person archives; encrypt the operator-config
  archive to a recipient whose private key is not on the host. The web UI's database holds the speech-to-text key and cannot
  be filtered by file name: move that key out of it, or list it as a residual. After a restore the person pastes the key again
  (cheap, unlike a chat history). A check fails the backup run if an archive contains a listed path.
- **No fallback key.** Today `router.py` takes the person's own key first and then the stack's environment key, and
  provisioning can write a shared one. Change both: the router and helper tools return "no key" instead of using an operator
  key for a person's stack, and the person is told. Operator keys serve operator bots only. Remove `--nim-key` and the
  starter-key marker.
- **Fingerprint audit.** A read-only check compares short key fingerprints (never values) across all stacks and alerts when two
  accounts share one, or a person's stack holds an operator key. Runs daily and before a new stack goes live.
- **Host tools stop spending client keys.** Today `ops/key_check.py` reads every stack's keys on the host and calls each
  provider. Probes move into the stack (the keys page already checks keys in-container and writes `.keys-status.json`); the
  host reads only that status file (provider, ok or rejected, last 4, time). For a paid key, automated probes are opt-in and
  limited to a free listing call at most daily.
- **A spend ceiling in the router.** A per-key daily request and token counter with a hard stop, a per-request output limit, a
  local shared secret so only the agent can call the router, and a notice to the person at 50 and 80 percent.
- **Keys page.** Ask "free or paid?". For a paid key show the provider's own cap steps and a confirmation that a cap is set
  (friction and a record, not enforcement); where the provider API shows it, warn when the key has no limit. Never echo a
  provider's error text that could contain the key; keep a one-line audit trail (time, provider, last 4, action) the person can
  read, and show "last changed".
- **Transport.** Firewall the web and dashboard ports to the edge only, remove the dashboard where it is not needed so keys
  have one entry path, rate-limit the keys path, and encrypt the edge-to-host hop.
- **Redirects.** Standard-library HTTP clients that carry a key (`http_json` in `keys_server.py`, and any other `urllib`
  caller; the router's provider calls use `http.client`, which does not follow them) refuse redirects.
- **Regression checks** in the self-tests: a fake key put through save, a failing provider and a failover appears in no log,
  response or output; the privacy scan stays clean; a canary key in the guest never shows in any log or chat store.

### Phase 1: the agent holds no provider key

- **Credential proxy (sidecar).** Move the router and the keys page into a second container in the same stack, with its own user
  and its own volume that the agent container does not mount. The agent talks to it with a per-stack local token that is useless
  outside the stack; the sidecar adds the provider key itself, forwards only to allow-listed provider hosts, and enforces the
  spend ceiling. Provider calls made by auxiliary features (vision, speech, web) and any pinned model that bypasses the router
  go through it as well.
- **Egress.** The agent network has no direct route to provider hosts; the sidecar's outbound is an allow-list. The agent keeps
  internet access for browsing (a product feature) but never to the host, the local network, other stacks or the metadata
  address. Remaining exfiltration is chat data, which is a privacy matter rather than a key matter.
- **Encrypted at rest.** The sidecar's key volume sits on an encrypted filesystem or a host-bound credential store, so a stolen
  disk, image or backup reveals nothing.
- **Operator tools** that must check a key do it through the sidecar and read only fingerprints and last 4.

### Phase 2: the person holds the lock

- **Optional locked mode** for high-value paid keys: the key is sealed with a passphrase only the person has, and is unsealed
  into the sidecar's memory from the keys page. Cost: after each sleep or restart it is locked again until the person unlocks
  it, so background jobs, scheduled work and wake-on-demand pause while locked. Offered as opt-in, with that cost stated.
  An alternative to evaluate: a small relay that runs on the person's own machine and injects the key, so it never reaches
  us at all.
- **Usage anomaly alerts.** A rolling count per stack against its own median and a hard ceiling; and, where a provider reports
  usage per key, a comparison with our own count. Provider spend rising while ours does not means the key is in other hands:
  alert "rotate now".
- **A "my key was exposed" button** that shows the provider's revoke link and clears the stored key, including keys that were
  not entered through the page.

### Key gateway (concept, not built)

Where Phases 1 and 2 lead: one service, the key gateway, is the only place provider keys exist. Agents never hold one.

- **Shape.** The gateway speaks the OpenAI-compatible API to the stacks. Each stack gets a scoped, revocable stack token; the
  gateway maps (stack, token) to that account's keys, adds the real key and forwards to the provider. A token copied out of a
  stack is useless elsewhere.
- **Where it runs, in two steps.** First a separate container on the Docker host (own user, own network, no terminal, no agent
  tools): this already removes the main risk, prompt injection in the agent. Then a small dedicated VM running only the
  gateway, so a broken container or a compromised Docker host still does not reach the keys. Its firewall lets in only the
  stacks' networks and lets out only the provider hosts.
- **Who may call it (our side).** Source networks of the stacks AND the per-stack token, so one stack cannot use another
  account's key even from inside the same network.
- **Who may use the key (provider side).** Where a provider can restrict a key to source IPs, the person restricts it to the
  gateway's public egress address: a leaked key is then useless anywhere else. This is the strongest single control after a
  spend cap; it depends on each provider supporting it, so the guide says "if your provider allows it, do it".
- **Encryption at rest (envelope).** Each key is encrypted with its own data key; data keys are wrapped by a master key. Options
  for the master key:

  | Master key held by | Protects against | Cost |
  |---|---|---|
  | Sealed to the gateway VM (virtual TPM) | stolen disk, image or backup | not against root on the gateway |
  | Operator, unlocked at boot | the same | the operator could read keys: must be stated |
  | The person (passphrase or hardware key) | everyone, including us | the bot works only while unlocked (e.g. 12 h); night jobs pause |

  Default: sealed to the VM; the person-held lock as the opt-in high-security mode (Phase 2).
- **What it enforces.** Per-key and per-stack budgets (requests and tokens per day) with a hard stop and alerts at 50 and 80
  percent; a per-request token ceiling; an allow-list of providers and models per key; anomaly alerts (loops, sudden spend);
  metadata-only logs (who, when, how much; never content or keys).
- **How keys get in.** The keys page talks to the gateway directly over HTTPS terminated at the gateway, never through the
  agent's container. The person sees the last 4 only, can revoke and replace, and sees their daily usage and an audit line for
  every use of their key.
- **Honest limit.** Whoever runs the gateway holds a key in memory while using it. This is offset by transparency (the
  person's audit view) and by the person's own controls at the provider (spend cap, IP restriction, revocation).
- **Order.** Phase 0 items; the gateway as a container with budgets; the gateway on its own VM with sealed encryption; the
  person-held lock as an option.

## 5. What the person must do

These matter most, because they work even if our side fails.

1. **Set a spending limit** at the provider before pasting a paid key, an amount they can afford to lose, plus a usage alert.
   Each provider differs; the guide lists what we have verified and marks the rest "check in your console".
2. **One key per app or bot.** Never reuse a key used elsewhere.
3. **Rotate** on a schedule they choose (90 days is a suggestion), by creating the new key, testing, then deleting the old one.
4. **Revoke at the provider first** if in doubt, then replace the key on the keys page.
5. **Never paste a key in a chat or email.** A key pasted into a chat is treated as compromised.
6. **Tell us** about any suspected leak so we can check our side.

## 6. Incident response

1. **Contain.** The person revokes the key at the provider now (we never do that for them and never need their account).
   We stop the affected stack's gateway if it is still running.
2. **Size it.** The provider's usage view shows the window and origin; the person can ask the provider for a review with those
   timestamps.
3. **Rotate.** New key on the keys page (it is validated before it is stored), old key deleted at the provider.
4. **Find the cause on our side.** Search backups, logs and chat stores for the key's fingerprint, never printing the value.
5. **Tell the person plainly** through their own channel, with a note that contains no content.
6. **Fix and add a regression check.** A runbook (`ops/KEY_INCIDENT.md`) will be written once the Phase 0 pieces exist, and
   practised once on the guest stack with a free key.

## 7. Honest limits

- A running service must hold the key in memory to call the provider. The operator can technically read what a stack holds
  while it runs, and until Phase 1 the assistant's own process can too. Encryption protects against theft of disks and
  backups, not against a live host. This is why the provider-side cap, usage alerts and quick revocation are the real safety
  net.
- Hermes' redaction and approval rules reduce accidents; they are not a boundary.
- A person's vault protects their master copy, not a key already pasted.
- Provider behaviour changes. Cap, revoke and expiry features are verified per provider and dated; NVIDIA and OpenAI rows still
  need a hand check in the real consoles.
- Items in Phases 1 and 2 are design, not product.

## 8. Open points for the operator

- Hand-check the NVIDIA and OpenAI consoles for per-key limits, expiry and revocation.
- Confirm backups may drop the credential files (a restore means pasting keys again).
- Decide whether locked mode, or a relay on the person's machine, is worth offering, given the pause in background jobs.
- Decide the order: the cap checklist, guide and website text and backup change first, then the sidecar.
- Which providers are treated as paid, for the cap prompts.
- Whether the public edge's dashboard route is reachable from outside (not visible from the repo).
- Whether any copy of the backup folder exists off the host.
- B.0 in `DATA_LAW_AND_KEYS.md` says a key belongs to one natural person; the decided rule is an account (a person or a
  company). Align B.0 when the operator confirms.
- Who still runs on a legacy starter key, and by when they move to their own (it gates removing `--nim-key`).
