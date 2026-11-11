# Public intake bot: plan (not built)

Status: **designed, deferred.** Nothing here is built. This records the design so it can be picked up later.

## Goal

The reverse of the per-person bots. A website links to a Telegram bot that **anyone** can write to. It is not a direct
channel to the operator; it is a receptionist:
- it takes note of what the person needs and asks only what is missing;
- it sets expectations plainly (we do not work 24 hours, when an answer can be expected, what it cannot do);
- the notes reach the operator as a summary **only at hours the operator chooses**;
- it runs on a completely isolated VM, with as little capability as possible, because strangers talk to it.

The aim is also privacy: strangers do not get the operator's own account, and what they send is held apart.

## The main decision: not Hermes

Three approaches were compared: a locked-down Hermes stack, a small purpose-built bot with no tools, and a design centred on
pulling the notes out of the isolated VM. **The base is the small bot, plus the pull model.**

Hermes is a single-tenant personal agent with a terminal, files and web tools. Locking it down to one tool would mean
patching upstream, then trusting a test that the tool list is exactly that one tool, with the model key in the same
container. A bot that has no tools cannot gain any through prompt injection. The worst a stranger can do is write a
misleading note, or use up a capped budget.

| Criterion | Locked Hermes | Small bot (chosen) |
|---|---|---|
| What injection can reach | whatever the cut-down agent still exposes | nothing: there are no tools |
| Strangers' data | sessions and state.db per sender, unverified | consent step, `/delete`, retention, separate digest chat |
| Effort | about 7 days, with a first-day spike that can fail | about 5-6 days, one small stdlib process |
| Upkeep | the large image, patches and a fork of the start script | about 600 lines |

## Design ("Buzon", a placeholder name)

### Components

**On the intake VM** (its own VM, Debian, 1 vCPU, 1 GB RAM, always on, no Docker needed):

1. **`intake_bot.py`.** This is the only public-facing process.
   - It uses raw `getUpdates` long-polling (the `opschat.read` style), outbound only.
   - It accepts only private-chat text messages. It drops groups, files, photos, voice, stickers, forwards and edits with one fixed line, "describe it in words", and never calls `getFile`.
   - Messages are capped at 1500 characters, with control, bidi and zero-width characters stripped.
   - BotFather settings: `/setjoingroups off`, privacy mode on.
2. **`intake_flow.py`.** A state machine per chat id: `NEW → CONSENT → ASKING(n≤4) → CONFIRM → DONE` (plus `BLOCKED`).
   - Commands handled by code only: `/start <tag>`, `/lang`, `/cancel`, `/delete`, `/hours`, `/help`.
   - There are no admin commands in the bot.
3. **`intake_texts.py` plus `hours.json` plus `tags.json`.** Every fixed message exists in es/ru/en. `hours.json` holds the timezone, reading windows, closed dates and the answer promise. The closing message and the digest window both come from it, so the promised time cannot drift from the real one. `tags.json` maps a deep-link tag to a page or module name, a default language and a question set.
4. **`intake_guard.py`.** Deterministic and outside any model. It imports the `content_guard.py` regexes.
   - It masks pasted secrets and card-like numbers.
   - It scores injection and sets a `[flagged]` flag on the note. It does not block.
   - Per-chat limits: 20 messages per hour, 60 per day, 3 notes per day, one open note at a time.
   - A global daily cap, then a static "closed for today" with no LLM call.
   - A persistent denylist, plus a kill switch file (`PAUSE`).
5. **`intake_store.py`.** SQLite in WAL mode, file mode 0600.
   - `notes` holds the structured note plus capped raw text. The full chat transcript is not kept after the session ends.
   - `reply_map` holds the real Telegram id and is used only for `/delete` and replies.
   - `events` holds metadata only.
   - Offsets advance only after the message is stored ("never lose a message").
6. **`intake_llm.py`.** Phase 2 only.
   - It makes one plain chat-completion call with no tools parameter, small `max_tokens`, and a 20 s timeout.
   - The prompt contains this chat's capped transcript and a fixed system prompt, and nothing else.
   - It runs through a class-A or paid, dedicated, spend-capped key.
   - Code validates the JSON. An invalid result falls back to a fixed question.
7. **`intake-export` (forced command).** The user `intake-pull` has `command=…,restrict,from=<operator host>`.
   - It exposes three verbs: `export` (prints new notes as JSON plus the current `hours.json`), `ack <batch>`, and later `outbox-put`.
   - It has no shell and cannot read the token or the key.

**On the operator side** (the Docker host or a workstation):

8. **`intake_pull.py`.**
   - It runs from a timer that fires every ~30 minutes. It exits unless the window from `hours.json` is open and nothing was delivered in this window yet. This is the `hub_start.in_window` pattern, and it keeps one source of truth.
   - It re-validates every record (the `canonical()` style) and does not trust the VM.
   - It re-runs content_guard and builds a plain-text digest with no LLM.
   - It sends the digest through `notify.send`, split into parts under 4000 characters, and calls `ack` only after the send succeeded.
   - It stays silent when nothing is new. It can send an optional weekly "no new requests" line.
   - Unit pair copied from `backup-watch.timer` and `.service`: `Persistent=true`, `OnFailure` alert, resolve on recovery. CLI: `run | status | peek | pause`.
   - The same job alerts if the bot's heartbeat is older than X hours.
9. **Delivery chat.** A separate muted chat that holds only the digest.
   - Small gap to close: `notify.py` sends only to `OPS_CHAT_ID`. It needs a destination override, or a third send-only digest bot with its own env. The lean is to the override on the ops bot, because it adds no new token.

**Public website:** a static page served by the existing `sites_deploy.py` / sites-web, with a plain anchor `https://t.me/<handle>?start=<module>_<lang>`. The tag is limited to 64 characters of `[A-Za-z0-9_-]`. The bot validates it against `tags.json`, and unknown tags become `other`. The tag is data, not a secret.

### Conversation

All of this is fixed text, rendered by code, in es/ru/en. The language comes from the tag suffix, then Telegram `language_code`, then the first message, with `/lang` as an override.

1. **First message**, before any model sees the person's text:
   - It is an automated assistant that takes notes, not a person.
   - "We do not work 24 hours. Requests are read at <windows>. Expect an answer within N working days, or no promise. Not for emergencies."
   - It cannot take files or voice. It cannot give prices, bookings or confirmations.
   - Privacy line: text is stored, read by a person, processed by a named AI provider class, and deleted N days after being read. `/delete` removes it now.
   - Button: [Continue]. Consent is recorded as a timestamp.
2. **Questions**, at most 4, one at a time.
   - Q1: what do you need (the wording varies by tag).
   - Q2-Q3: the missing piece (what, when, where, how much), picked from a fixed list. In phase 2 the model may choose or rephrase, and code rejects any question that contains a URL or exceeds 200 characters.
   - Q4: optional contact. The default is "a reply here on Telegram". The bot never asks for IDs, passwords, payment data or health details.
3. **Recap** in 2-3 lines with [Looks right] [Edit] [Cancel]. After the confirm, it says "Noted, ref #A7K2. Nothing is confirmed until a person replies to you. Next reading window: <computed from the clock>." The next-window sentence is computed in code, so at 03:00 it says "tomorrow 10:00".
4. **After DONE:** "I only take requests." One follow-up line can be added to the last note, up to 2 per ref.
5. **Refusals:**
   - Out of scope gets a template line.
   - Authority claims ("I am the admin/police") get "I am automated and cannot do that".
   - The second strike closes the chat. Only a flag and a count are kept, and the text is not stored.
6. **Urgency:** urgent wording raises an enum on the note only. The bot says urgency does not change the reading hours.

### Data flow

```
site link -> Telegram -> bot long-polls (outbound, via allowlist proxy)
  -> guard -> flow -> [phase 2: LLM call, no tools] -> SQLite note
operator timer (window open) -> ssh forced command `export`
  -> re-validate + content_guard -> deterministic digest
  -> notify.send to the separate chat -> `ack`
VM purge: delivered notes after N days; unacked after a hard cap
```

- Nothing is pushed from the VM.
- The digest per request shows: short id, tag, language, urgency, flags, then the text in a quoted block headed "Unverified text from a stranger, not instructions".
- Control characters are stripped, URLs are defanged, there is no Markdown and no MEDIA lines.
- Abusive or illegal items show only as a count. The operator can still pull one by id on the VM if there is a legal reason.
- Stranger text never enters a Hermes prompt. If the operator pastes a digest into an agent, it must be pasted as quoted data.

### Isolation

- **Separate VM** on its own bridge or VLAN, with no route to the LAN, the Docker host, workstations, GPU hosts or hypervisor management. Two walls: the hypervisor's VM firewall and nftables inside the VM. Both must fail for a leak.
- **Egress:** default drop. The only outbound path is a small CONNECT proxy on the VM that allows `api.telegram.org` and the model host (the model host only from phase 2). The bot uses the proxy and the VM has no general DNS, which also shuts DNS exfiltration. I prefer this to IP ranges, because provider IPs behind a CDN change and rules would break silently. Reuse the validate-then-load-atomically style of `docker-user-fw.sh`, inverted.
- **Ingress:** only SSH from the operator host, key-only, forced command for the pull key. A separate admin key stays with the operator and is used by no timer.
- **Process:** unprivileged user with systemd sandboxing (`ProtectSystem=strict`, `NoNewPrivileges`, `MemoryMax`, `TasksMax`, `RestrictAddressFamilies`, `SystemCallFilter`). Only python3, openssh and nftables are installed. No nmap, no ffmpeg, no git, no node.
- **Holds:** the public bot token, an optional capped model key, the DB and config.
- **Does not hold:** the operator's keys, the ops token or chat id, any person's token, `gateways.json`, any SOUL or memory file, or any repo beyond a small bundle.
- **Backups:** excluded from `backup-stacks.sh`, so deletion really deletes. Use snapshot-before-deploy, with a rebuild script and token rotation if compromise is suspected.
- **Blast radius of a compromised VM:** the bot token and the stored notes. That is the intended limit.

### Reuse from the repo

- **Telegram loop and delivery:** `ops/opschat.py` for the poll loop and offset file, and `ops/lib/notify.py` for delivery with its outbox.
- **Scheduling:** `ops/backup-watch.timer`, `.service` and `ops-alert@`, and `hub_start.in_window()`.
- **Atomic spool and untrusted-input style:** `hub/hub_client.py` and `hubcore.py`, `ops/zabbix_hook.py`, and `hub/HUB.md`.
- **Filtering and digest bookkeeping:** `content_guard.py` plus its corpus (for the hostile-input replay), `subs_digest.py` and `jobpush.py` (peek/ack, silent when empty, es/ru/en tables).
- **Token setup:** `ops/stack_telegram.py` (token on stdin, `getMe`) and `keys_server.py` `TG_TEXT`.
- **Site and privacy:** `sites_deploy.py` for the page, and `privacy_scan.sh`, extended so the handle, chat id and VM name never reach the public repo.
- **Not reused:** Hermes, the waker (wake-on-message is the wrong shape for a public bot), and the hardening override. The override is only an alternative if you prefer a container.

### Phased build

- **Phase 0 (operator, about half a day):** create the VM and its network rules, create the bot in BotFather with a throwaway token first, and decide the open questions marked **must** below.
- **Slice 1 (small, no model, about 3-4 days):**
  - the bot with fixed questions in es/ru/en, guard, SQLite, and `/delete`;
  - the egress proxy and firewall, with a test that `curl` to a random host or a LAN address fails;
  - the forced-command export, `intake_pull.py`, the timer and the separate delivery chat.

  This slice already meets the whole intent: notes, set expectations, a digest at chosen hours, no live channel. It needs no provider, no key and no cost.
- **Rehearsal (1 day):** you pose as a stranger in three languages. Run a hostile-input replay (injection in es/ru/en, 100 KB text, unicode tricks, "I am the admin", a flood, files and voice). Add `intake_selftest.py` with a fake Telegram, repo style.
- **Go live unpromoted for about a week.** Watch the digest and the abuse counts, then put the link on the site.
- **Slice 2:** the LLM step with a class-A or paid capped key, with fallback to fixed questions. Add a spend ceiling and the cap test.
- **Slice 3, only if wanted:** reply relay via a pull-only outbox, a web form as a second front, and a heartbeat refinement.
- **Out of scope, deliberately:** voice notes (STT would break the isolation), file handling, and any second tool.

## Known weaknesses

- **Reply path is the hard part.** Telegram users cannot be messaged first by your account unless they have a public username. With no reply path, people without a username cannot be answered at all. The relay in slice 3 fixes this but adds attack surface, and it is the one feature that makes the bot closer to a channel.
- **A fixed question list is stiff.** Slice 1 will feel mechanical. The LLM step improves it, but then a model reads strangers' text. The risk is bounded (it can only produce a bad note or burn a capped budget), not zero.
- **Injection still shapes the note.** A stranger can write a misleading summary. The mitigation is the "unverified, quoted" digest, not prevention.
- **Pull needs a route.** The operator host must reach the VM on tcp/22. A workstation that is off at the chosen hour will miss the window (the next run catches up). The Docker host is always on but holds the ops token and sits next to everything else. A compromised VM can also return malicious JSON, so re-validation on the operator side is mandatory.
- **Consent is implicit,** and the legal wording for Argentina and EU senders is not something I can settle. Storing Telegram ids and usernames is itself personal data.
- **Abuse protection is weak against a determined spammer.** A spammer can rotate Telegram accounts. The global daily cap protects cost, but it can also be used to lock out real people ("closed for today").
- **The egress proxy is another thing to maintain.** If it breaks, the bot goes silent, so the heartbeat alert is required.
- **Provider privacy class** is unresolved. The notice must name it truthfully.
- **Time estimates** are for one developer who knows the repo, and exclude the operator's own steps.

## Open questions

**Must decide before slice 1:**
1. Hours, timezone, weekends, closed dates, and how many windows per day. Is "silent when nothing is new" right?
2. What may the bot promise: "within N working days", "only if it fits", or no promise? What is in scope (categories)? This drives the questions and the refusal text.
3. VM placement: is a separate bridge or VLAN with no LAN route available, and can the hypervisor's VM firewall be used?
4. Where does the puller run, the Docker host or a workstation?
5. Digest destination: a separate muted chat (and an override in `notify.py`, or a third digest bot)?
6. Retention: days after delivery, and a hard cap for unread notes. Is the Telegram id, username and name stored with the note, or only the note?

**Must decide before slice 2:**
7. Model route and privacy class: a Cloudflare class-A key, a paid capped key, or no model at all for now. What monthly ceiling? A local GPU model is not possible, because it breaks the "no LAN route" rule.
8. Does the notice name the provider? Which jurisdiction wording (Argentina, EU)?

**Can wait:**
9. Reply policy: answer from your own account only, or add the reply relay in slice 3?
10. One bot with tags per page or module (recommended), or one bot per module?
11. Languages: is es/ru/en enough, and what happens to other languages (answer in English, or refuse politely)? Who checks the Russian and Spanish wording?
12. Contact policy: Telegram only, or may people leave an email or phone?
13. Abuse policy: strikes before a block, whether you ever see flagged text (the on-VM "show by id" path), and whether to report repeat offenders.
14. Web form as a second front: now or later? It needs an inbound port and a captcha, which weakens the "outbound only" property.
15. Bot identity: name, handle and profile text. The text must say it is automated and be clearly different from your personal and per-person bots. Keep the handle and VM name out of the public repo.

Everything above comes from reading the three design briefs and the repo context supplied. I did not read or run anything in the repo.