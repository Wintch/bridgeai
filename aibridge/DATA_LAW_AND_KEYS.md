# Personal data law (Argentina) and key hygiene with KeePassXC

Design note from a research pass that checked each claim against official sources (argentina.gob.ar, AAIP, keepassxc.org, provider docs).

Status: draft. This is research and design, not legal advice. Confirm the registration conclusion with an Argentine data-protection lawyer or AAIP (registrobasesdedatos@aaip.gob.ar, datospersonales@aaip.gob.ar) before relying on it. Items marked UNVERIFIED were not confirmed on an official page.

Reading limits: the law and decree texts come from the official argentina.gob.ar pages, which carry the original text. infoleg.gob.ar blocked scripted fetches. Re-check the Boletín Oficial before each review.

---

## Privacy classes (the canonical definition)

Other documents say "class A", "class B" or "class C" for where a person's data may go. The class is decided by who runs the service and where, not by
how sensitive one message looks:
- **Class A:** stays on our own machines, or goes to a provider whose terms say it does not train on or keep the inputs (for example Cloudflare Workers AI
  for images). A person's photos may go here.
- **Class B:** a trusted provider used by agreement with the person.
- **Class C:** an ordinary third-party cloud (free model tiers, community hosts). It must never carry a person's chat, memory or private files without
  the person's consent.

---

## Part A. Argentine data-law obligations

### A.0 Status of the law
- Ley 25.326 (2000) is still in force. Texts: https://www.argentina.gob.ar/normativa/nacional/ley-25326-64790/texto and Decreto 1558/2001, https://www.argentina.gob.ar/normativa/nacional/decreto-1558-2001-70368/texto.
- The control body is now AAIP, not the old DNPDP (Decreto 899/2017 substitution note).
- A replacement bill, expediente 3397-D-2026 (filed 2026-07-16, same text as the 2023 bill), is at an early stage. This comes from law-firm summaries only. Verify it on hcdn.gob.ar. It creates no current duties.
- Argentina is party to Convenio 108 (Ley 27.483) and ratified 108+ on 2023-04-17. Entry into force of 108+ is unconfirmed. It adds no separate duty for a small operator.

### A.1 Role
A person who runs assistants for others holds their chats, memory, files and keys on their own server. That is plausibly a "responsable" (art. 2) whose use exceeds "uso exclusivamente personal" (art. 24; Decreto 1558/2001 Anexo I art. 1). This is an inference. The law has no size or hobby exemption, and no small-operator guidance exists.

### A.2 Checklist

| # | Duty | Basis | Notes |
|---|---|---|---|
| 1 | Register operator and database in the Registro Nacional de Bases de Datos (via TAD) | Ley arts. 3, 21, 24; Decreto Anexo I art. 1; https://www.argentina.gob.ar/aaip/datospersonales/responsables/obligaciones and https://www.argentina.gob.ar/aaip/datospersonales/tramites | Plausible, not certain (open question a). Art. 21 alone targets databases "destinado a proporcionar informes". Art. 24 is the one that reaches bridgeai. The register is public (art. 13), so the operator's name and address would appear (art. 21(2)). Art. 21(3) bars holding data types not declared. AAIP's AI guide, footnote 18, says databases feeding an AI system must be registered. No fee or renewal is stated on the AAIP pages. A "natural person with CUIT" requirement is UNVERIFIED. |
| 2 | Show the art. 6 notice before collecting, and record express consent with date, language and notice version | Ley arts. 5, 6; Decreto art. 5 | Consent must be free, express and informed. It can be non-written if authorship and integrity are assured. It is revocable at any time, without retroactive effect (that phrase is UNVERIFIED in the fetched text). Res AAIP 14/2018 (visible-place rule) formally targets "dar informes" databases, so follow it as good practice, not a binding rule. It also requires the AAIP complaints statement. |
| 3 | Collect only what is needed and use it only to run that person's assistant | Ley art. 4 | No unrelated use, no training, no profiling. |
| 4 | Delete data that is no longer needed, including on exit, without waiting for a request | Ley art. 4.7; Decreto art. 4 | Legal anchor for the delete-on-exit goal. The schedule is an inference. |
| 5 | Security and confidentiality measures | Ley arts. 9, 10; Res AAIP 47/2018 (https://www.argentina.gob.ar/normativa/nacional/resolución-47-2018-312662/texto) | Res 47/2018 is a recommended yardstick (Anexos I and II "de modo referencial"), not mandatory. Areas: collection, access control, change control, backup, vulnerabilities and logging, destruction, incidents, dev environments. Secrecy survives the end of the relationship. |
| 6 | Limit operator access to stated purposes | Ley art. 10; Código Penal 157 bis | Technical ability to see everything is not permission. 157 bis text is in force via Ley 26.388 art. 8 (https://www.argentina.gob.ar/normativa/nacional/ley-26388-141790/texto), not from Ley 25.326 art. 32 as originally added. It punishes, with 1 month to 2 years, illegitimate access to a personal database, illegitimately revealing information one must keep secret, and illegitimately inserting data. Write down when the operator looks: support at the person's request, security or abuse, legal order. |
| 7 | Sensitive data | Ley arts. 2, 7 | Health, politics, religion, union, sexual life, and under AAIP Res 4/2019 also biometric, genetic, disability and gender identity (per the AI guide). Art. 7 has no consent route, and art. 7(3) bars databases that reveal sensitive data. A free-form assistant cannot avoid receiving some. Reduce it by warning people, not mining or profiling it, keeping it out of logs and backups where feasible, and allowing deletion at any time. This is a real legal gap (open question b). |
| 8 | Transfers to non-adequate countries (US providers) | Ley art. 12; Decreto Anexo I art. 12; https://www.argentina.gob.ar/aaip/datospersonales/transferencias-internacionales | Express consent comes from the Decreto's regulation of art. 12, not from the law text. The US is not on AAIP's adequate list (Disposición 60/2016, Res 34/2019). The ARTI trade deal (2026-02-05) only commits Argentina to recognize it, and no formal act was found. Treat the US as non-adequate. Name each provider and country in the consent. Model clauses (Disposición 60/2016, Res 198/2023) are the alternative. Storage on the operator's Argentine server is not a transfer. Local-first models avoid transfers. |
| 9 | Providers as processors | Ley art. 25; Decreto Anexo I art. 25 | Providers are better seen as "encargados" than as recipients of a cesión (open question d). The "only on instructions, bound by art. 9" wording is in the Decreto. Art. 11 cesión consent must be informed, including recipients and purpose. Standard provider terms are not negotiable, so prefer providers with no-training and no-retention terms. |
| 10 | Answer rights requests | Ley arts. 14, 16, 19, 33; Decreto art. 14; https://www.argentina.gob.ar/aaip/datospersonales/derechos | Access within 10 calendar days, free every 6 months. Rectification, update or deletion within 5 business days, free. Block or flag data during verification. No special form is required. A Telegram or web request is acceptable if identity is assured (an inference). Log and timestamp each request and give a receipt, because a complaint to AAIP needs proof of receipt. Remedies are a complaint to AAIP or habeas data (art. 33). |
| 11 | Warn people about sensitive and third-party data | Ley art. 7; AAIP AI guide | Tell people not to paste other people's data. |

Penalties: fine ceilings of 3M, 10M and 15M pesos by level (Res AAIP 244/2022, https://www.argentina.gob.ar/normativa/nacional/norma-376196/texto), plus criminal and civil exposure. Classification and graduation come from Res 126/2024, known only through a law-firm summary. Amounts after 2022 are UNVERIFIED. The likeliest trigger for a hobby operator is a complaint or a leak, so security and clean exits matter most.

Good practice (AAIP AI guide, non-binding: https://argentina.gob.ar/sites/default/files/aaip-argentina-guia_para_usar_la_ia_de_manera_responsable.pdf):
- a short impact assessment, written once;
- stated retention periods;
- a breach log;
- a review whenever a provider or the law changes.

A Data Protection Delegate is not needed at this scale.

### A.3 Refuted or corrected in review
- The old claim "157 bis added by art. 32 of the law" is outdated. Use Ley 26.388.
- "Express consent is in art. 12 text" is wrong. It is in Decreto art. 12.
- "Decreto art. 1" should read Anexo I art. 1.
- "Recipient must be named" in art. 11 is not in the text. It comes from the art. 6 duty to inform.
- Res 14/2018 is not clearly binding for this kind of database.
- There is no AAIP guidance specific to Telegram or chatbots. Telegram bot chats are not end-to-end encrypted (general knowledge, not researched).

### A.4 People abroad and Russian speakers
Art. 2 protects data subjects "con domicilio legal o delegaciones o sucursales en el país". Whether friends living abroad are covered is unclear. The reform bill widens scope toward foreign controllers, not toward protecting people abroad. Foreign law (for example GDPR for EU residents, or Russian rules) was not researched and may apply on its own. Policy: apply the Argentine standard to everyone, ask where each person lives, and make no claims about foreign law.

### A.5 Draft privacy notice outline (es primary, with ru and en)
Keep it short and in the person's language. Add an explicit "I accept" action, and link to the notice from first contact and from the keys page.

1. Who is responsible: name, Buenos Aires address, contact email, registration number if registered.
2. Purpose: to run your private assistant. No sale, no ads, no training by the operator, no other use.
3. What is stored and where: chat messages, memory notes, uploaded files, settings, and the API keys you provide.
4. What is optional: only what the assistant needs is required. Sensitive data is optional and discouraged.
5. Who receives data: model, speech, search and map providers, named with country. Telegram also holds your messages under its own terms. Say which countries are non-adequate (for example the US), and that accepting is express consent to that transfer.
6. Operator access: the operator can technically see everything. State exactly when they look (support at your request, security or abuse, legal order) and that they do not otherwise.
7. Security in plain words, and how an incident would be notified.
8. Retention and exit: how long chats and memory are kept. On exit, the deletion date, the backup expiry date, and that you must revoke or rotate your keys at each provider.
9. Your rights: access, rectification, update, suppression, confidentiality and revoking consent. Response times: 10 calendar days for access (free every 6 months) and 5 business days for the rest.
10. The right to complain to AAIP (datospersonales@aaip.gob.ar, (54-11) 3988-3968) and to bring habeas data in court.
11. Where you live: ask. Argentine law applies, and other laws may apply to you.
12. Version, date, and how changes are announced.

---

## Part B. Key hygiene built around KeePassXC (operator never holds the vault)

### B.1 Principle
KeePassXC is a local, client-side vault: a .kdbx file encrypted at all times, decrypted only in the person's memory (https://keepassxc.org/docs/KeePassXC_GettingStarted, https://keepassxc.org/docs/KeePassXC_UserGuide). bridgeai never holds the vault, its master key or its key file. Never ask for the vault, a screenshot of it, or the master password.

The vault protects the person's master copy and their ability to rotate. It does not stop the server from using a key already pasted into it. Only revoking at the provider does that.

### B.2 What the person keeps in their vault
- One entry per provider key, plus the Telegram bot token if they made one.
- Recommended setup:
  - KDBX 4 with Argon2id (User Guide, Database Settings > Security);
  - a long diceware master passphrase;
  - optionally a key file or YubiKey, only for people who can keep a backup, because losing the master credentials locks the vault permanently.
- Set the entry "Expires" date. KeePassXC shows expired entries, and entries expiring within 3 days by default, after unlock. This is the person's own reminder and involves no server. The CLI man page lists no expiry option, so treat expiry as a GUI feature (medium confidence).
- Enable idle lock in Tools → Settings → Security. Check the exact labels in the app. Disable Quick Unlock on shared computers.
- Keep TOTP secrets in a separate database from passwords, or the 2FA benefit is lost.
- Exports are unencrypted, so delete them.
- Mobile apps:
  - Android: KeePassDX or KeePass2Android;
  - iOS: KeePassium or Strongbox (check Strongbox's key-file and Argon2 support before recommending it).
- Sync:
  - put only the .kdbx in a synced folder, and keep the key file elsewhere;
  - use a service with version history;
  - use Database > Merge From Database for conflict copies.
- A stale synced copy holding an old key is harmless once that key is revoked.
- For terminal users, `keepassxc-cli add -p vault.kdbx providers/<name>` stores a new key. `keepassxc-cli clip vault.kdbx providers/<name> 20` copies it for pasting on the keys page. Everything runs on the person's machine.
- The offline `analyze --hibp` check helps the master password and reused human passwords, not random API keys. Do not promise a GUI health panel (not documented).

### B.3 Rotation routine (create new, update bridgeai, test, delete old)
Recommend a project interval, for example 90 days. This is a recommendation, not a provider requirement, and no law requires rotation. It is good security practice under art. 9.

- **OpenRouter** (https://openrouter.ai/settings/keys; docs https://openrouter.ai/docs/api-reference/authentication):
  - one key per app, with a credit limit on every key (daily, weekly or monthly reset);
  - expiry is fixed at creation (`expires_at` in the OpenAPI spec, https://openrouter.ai/openapi.json), and an expired key returns 401;
  - if a key leaks, delete it on the key settings page and create a new one.
- **Google AI Studio (Gemini)** (https://aistudio.google.com/api-keys; docs https://aistudio.google.com/docs/api-key):
  - restrict the key to the Gemini API and set billing alerts;
  - rotate by creating the new key, deploying, testing, and only then deleting the old one;
  - for a leak, disable the key in the Cloud console and review usage.
- **Hugging Face** (https://huggingface.co/settings/tokens; docs https://huggingface.co/docs/hub/security-tokens):
  - use one fine-grained or read-only token per app, never a write token;
  - Manage offers delete or refresh.
- **Cloudflare** (https://developers.cloudflare.com/fundamentals/api/get-started/create-token/):
  - least-privilege policy;
  - set Token expiration and IP filtering where possible. The docs describe the fields but not what happens at expiry, so test it;
  - Roll (three-dot menu > Roll > Confirm) invalidates the previous token (https://developers.cloudflare.com/fundamentals/api/how-to/roll-token/), but those steps are for user tokens;
  - account-owned tokens are under Manage account > Account API tokens, managed by Super Administrators (https://developers.cloudflare.com/fundamentals/api/get-started/account-owned-tokens/);
  - the docs fetched do not describe delete or revoke, so check the UI before writing that step.
- **NVIDIA** (NGC personal key; https://docs.nvidia.com/rag/2.6.0/api-key.html, https://docs.nvidia.com/ngc/latest/ngc-catalog-user-guide.html):
  - there is an Expiration field and a Rotate action, and the fetched pages mention only "Never Expire";
  - UNVERIFIED: whether the old key keeps working after a rotation. The person must test it.
- **Groq** (console.groq.com/keys, inferred): UNVERIFIED. The official pages say nothing about revoking or expiry. Do not write a revocation step as fact. The operator should check the console and record what they see.
- **Telegram bot token** (BotFather, https://core.telegram.org/bots/features): `/token` regenerates the token and invalidates the old one. `/deletebot` deletes the bot and cannot be undone.

For every provider, tell the person to confirm the old key now fails at the provider. The exact status code (401 or 403) is not verified for any provider.

### B.4 What bridgeai does today, and the gaps
Verified in `aibridge/keys_server.py`:
- Provider keys are validated, then stored through `hermes auth add` in the Hermes credential pool at `~/.hermes/auth.json`. They are not in `.env`.
- The Telegram bot token and user ID go to `~/.hermes/.env` and `/workdir/.telegram.env`, which the host waker reads.
- `/workdir/.keys-status.json` holds metadata only: provider, ok, at, last4, model. The Telegram entry has ok, at and bot.
- Warm stacks (HERMES_ARCHITECTURE.md, "Warm stacks") keep two more timestamp-only files in `/workdir`: `.last_human` (the router writes the epoch of the person's last real turn) and `.idle_notice` (the waker writes the epoch of its last inactivity note). A number and nothing else: no message text, no chat or user id. The waker's per-stack `ops/wake/<name>.state.json` keeps the same kind of times (last human wake, last web use, `/dormir`, notice, day of the last refresh), and `ops/wake/<name>.booted_image` and `ops/wake/<name>.update_pending` hold an image id (and a time) only.
- `do_remove()` only removes credentials labelled "web-". Credentials seeded another way cannot be removed from the page.
- The persisted copies (persist/ folder) and backups also hold keys.
- Service keys (maps, movies, groq) are stored by `gateway servicios`. Their file location was not traced and must be checked before they go into a wipe list.
- Deleting a message the person pasted in Telegram is not built.

### B.5 Exit flow (closing a session or leaving)
Honest guarantee: server-side deletion is necessary but not sufficient, because the operator, backups and logs may have held the key. Only revocation at the provider makes a key unusable. Order:

1. **Person revokes first.** bridgeai shows each provider's link and last4 so they know which key to revoke. For the Telegram bot, they use `/token` or `/deletebot`.
2. **Operator-side wipe.**
   - Remove provider credentials from `auth.json`, including non-"web-" ones.
   - Remove the Telegram token and ID from `.env` and `.telegram.env`, and the persisted copies.
   - Remove service keys.
   - Stop and remove the stack's containers.
   - End Open WebUI sessions and disable or delete the web account.
   - Remove the person's Telegram ID from the allow-list and the waker config, and delete the stack's `ops/wake/<name>.state.json`, `<name>.booted_image` and `<name>.update_pending` (use times and an image id; no content). Their `/workdir/.last_human` and `.idle_notice` go with the `/workdir` wipe in step 3.
3. **Content on request or on schedule.** Wipe `/workdir` and memory, and say plainly which copies cannot go instantly: backups and provider-side logs. Fix and publish a backup retention period (for example 30 days, a policy choice). Backup expiry is the real deletion date.
4. **Receipt.** Send a written deletion receipt covering what was deleted and when, with no content.
5. **Verification is the person's.** The old key should now fail at the provider.

A key pasted in Telegram counts as compromised. The message stays in the chat, so rotate it and use the web keys page instead.

### B.6 What the bot may remind, without seeing keys
- It may use only the metadata already stored: provider, `at` and last4. Note that `at` is the last save time, which equals the date added unless the key is re-saved.
- At the policy interval, send a Telegram nudge with the provider link and the "create new, test, delete old" steps.
- On the keys page, show the age of each key and an "I rotated it" flow that validates the new key before replacing the old one. The page already validates before storing.
- Suggest provider-side expiry and spend caps as hard stops (OpenRouter limit and expiry, Cloudflare expiry, NVIDIA expiration, Gemini billing alerts). Use existing usage counters to flag runaway use, which is the real trigger for emergency rotation.
- Reminders only link to docs. They never request the vault, a screenshot or the master password.

### B.7 Honest limits to state to people
- KeePassXC protects the vault contents, not a key already pasted into bridgeai.
- The software is provided as is, and losing the master password means permanent loss.
- Auto-Type can type into the wrong window.
- Linux Secret Service integration requires disabling other providers, so it suits the operator and technical people, not typical Telegram users.

---

## Open questions
1. Registration: do you register as a responsable now (CUIT and TAD, public name and address), or first ask AAIP or a lawyer? Is the answer the same for each person's stack?
2. Sensitive data (art. 7): will you accept the residual gap with warnings and deletion on request, or want a lawyer's view on free-form chats?
3. Foreign residents and Russian speakers: ask each person's residence, and decide whether to seek GDPR or Russian-law advice.
4. US providers: rely on express named consent now? Will you re-check the Boletín Oficial for an adequacy act before each review?
5. Fixed backup retention period (30 days proposed). Who may look at chats, and under what stated purposes?
6. Rotation interval (90 days proposed), and whether the bot nudges by default or only on opt-in.
7. Build order: Telegram message deletion for pasted keys, an operator-side wipe command that covers non-"web-" credentials, persisted copies and service keys, and a consent step with a stored version.
8. Check in the real consoles: Groq revocation, NVIDIA rotate behavior, Cloudflare delete and expiry, and where `gateway servicios` stores its keys.
9. Where does the notice live (keys page plus first Telegram contact), and who answers rights requests within 10 calendar and 5 business days?