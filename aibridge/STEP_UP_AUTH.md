# Step-up authentication for dangerous operations 

Status: design only. Nothing here is built, installed or tested. It refines sections 13 and 14 of `MULTI_BOT_TASKS.md` (the approval-source rule and the time-locks): those sections say that a human must approve and that the approval must come from Telegram. This note says how strongly the human must prove who they are, and how the executor knows the approval is real.

Tags: **[E]** is an estimate or inference, **[LAWYER]** is a legal point to confirm with counsel, "not verified" means the primary source was not read or no real call was made. External facts carry their URL. Nothing in this note is a recommendation to buy a product; every component named is open source or a free standard.

## 1. Why a Telegram user id alone is not enough

An id is an identifier, not a credential. The Bot API defines `User.id` as a stable integer of at most 52 significant bits (https://core.telegram.org/bots/api#user), and Telegram's servers fill in `message.from`, so another user cannot spoof it. That is exactly the problem: whoever controls the account **is** that id, however they got in.

- **Login-code phishing.** A fake login page asks for the phone number, Telegram sends a real code, the page asks for it. AhnLab described the technique in May 2026 and notes the page serves decoys to crawlers (https://asec.ahnlab.com/en/93790/).
- **Takeover through a hijacked contact.** A contact's link to a fake contest or petition ends in a login step; the QR variant links an extra device or web session with no code at all. Without two-step verification, a code typed into the fake site gives full control (Kaspersky, 2023: https://www.kaspersky.com/blog/telegram-takeover-contest/27866).
- **SIM swap.** The attacker ports the number and receives the code. FBI IC3 complaint counts were 2,026 (2022), 1,075 (2023) and 982 (2024), with about USD 26M reported lost in 2024; I saw these figures only on secondary sites, so treat them as indicative. The primary 2022 advisory is https://www.ic3.gov/PSA/2022/PSA220208. NIST also lists SIM change and number porting as risk indicators for phone-based authenticators (https://pages.nist.gov/800-63-4/sp800-63b.html, 3.1.3.x).
- **Stale sessions and an unlocked phone** are takeover with extra steps: an old desktop, a forgotten web login or a handset picked up unlocked all send valid messages with the right id. Telegram's own advice is to review and terminate sessions (https://telegram.org/faq).
- **Bot chats are not end-to-end encrypted.** Only Secret Chats are, and they are one-to-one (https://core.telegram.org/api/end-to-end). That bots cannot join Secret Chats is my inference **[E]**; the page does not mention bots. So anything typed in a bot chat, including a code, sits in server history and on every logged-in device. Consequence for the design: a chat message may carry names, ids and digests, never contents.

Conclusion for 13.2 point 5 of `MULTI_BOT_TASKS.md`: "a stolen phone or taken-over account is human input" stays true for the weakest class. Step-up narrows it: for the dangerous classes a second factor held on a different device (or a hardware or platform key) means the Telegram account alone cannot arm or run an operation.

## 2. Risk classes and what each one needs

The classes are the ones of section 14.1 of `MULTI_BOT_TASKS.md`; this table adds the proof required.

| Level | Classes of 14.1 | Examples | Proof from the owner | Delay | Extra |
|---|---|---|---|---|---|
| **Low** | 0, 1 | read, list, verify, push a branch, draft, restore into scratch | the Telegram id (the stack's owner-only gate) | none | one line reported |
| **Medium** | 2 | merged-code deploy, restart one unit, schedule a post | id **plus** a confirmation button showing the exact action, rendered by the service | none (scheduled posts keep their lead) | button is single-use and expires |
| **High** | 3 | restore over live data, OS or engine version upgrade, schema migration, **spending money** | + a **TOTP code bound to the action** (section 4), re-asked at the end | hours (proposal 4 h) | a notice on a second channel |
| **Irreversible** | 4 | forget a snapshot, prune, shorten retention, destroy a volume, drop a database | + a **passkey on our own TLS page** (section 5) | days (proposal 72 h; 7 days for retention or bulk) | second-channel notice; optional second human |
| **Console only** | 5 | delete all or most backups, change ACLs, users, tokens, approver list | no bot channel exists | n/a | the human at the system with the admin account |

Spending money is **high** by the operator's decision. How that sits with small, frequent amounts (a GPU lease of a few cents) is open decision 29 in section 22 of `MULTI_BOT_TASKS.md`: a bounded, prepaid balance could use a short delay without changing the factor.

Three rules that apply to every level:
1. **The approval is verified outside the model.** The model is never in the path of arming or running. A command typed to a bot (`/armar`, `/ejecutar`, `/cancelar`) is intercepted by code (a plugin, or better the lock service's own bot) before any prompt is built, like `/parar` today.
2. **The service renders the action, not the bot.** The text the owner sees comes from the catalogue entry and its validated parameters (13.2 point 3 of `MULTI_BOT_TASKS.md`). The bot's prose is never the description.
3. **The executor checks a signed approval** (section 3), so a message saying "approved" is worth nothing by itself.

## 3. The signed approval: how the executor knows

The lock service (14.2 of `MULTI_BOT_TASKS.md`) is the only thing that sees the owner's proof. The executor, the small program on the backup or site host that holds the dangerous credential, must not take the service's word over a plain socket.

1. **Catalogue entry.** Each operation has an id, typed parameters, a class, a delay and the fixed argv it runs. The executor holds the same catalogue.
2. **Digest.** `digest = SHA-256(operation id || canonical parameters || target identity || class)`. The pending record stores it. Any change to a parameter makes a new record, a new digest, and invalidates every earlier code.
3. **Approval blob.** After the proof of the required level succeeds and `not_before` has passed, the service signs `{record id, digest, class, not_before, expires, nonce, level of proof used}` with an **Ed25519** key whose private half exists only on the lock host. This is the usual public-key signature scheme (RFC 8032: https://datatracker.ietf.org/doc/html/rfc8032); a library such as `cryptography` provides it, no custom crypto.
4. **Executor check.** The executor holds only the public key. It runs the operation only if: the signature is valid, `expires` has not passed by its own clock, the digest equals the digest **it computes itself** from the arguments it is about to run, the nonce was never seen (it stores used nonces), the class and level of proof match its own catalogue, and the preconditions of 14.2 step 6 hold (fresh verified backup, floor of verified copies, same target).
5. **Why public-key and not a shared secret.** If the executor held a shared HMAC key, a compromised executor host could forge approvals for others, and the key would be one more secret on a host with a delete credential. With a public key the executor can only verify.

Honest limit, as in 14.2: whoever has root on the lock host holds the signing key and can sign anything. The signature stops a hijacked bot stack, a forged message and a replay. It does not stop a person who has taken over the lock host. Storage that enforces the wait itself (Object Lock in compliance mode, PBS protected flags, WORM tape) remains the only wall against that.

## 4. TOTP bound to the action (high level, built first)

**Standards.** RFC 6238 section 5.2 (https://datatracker.ietf.org/doc/html/rfc6238): the verifier MUST NOT accept a second attempt of an OTP after a successful validation, allow at most one time step of network delay, default step 30 s; section 5.1: keep the secret in a secure key store with limited access. RFC 4226 section 7.3 (https://datatracker.ietf.org/doc/html/rfc4226): throttle failures with a growing delay or lockout, and the throttle MUST apply across login sessions. Secret length (at least 128 bits, 160 recommended) and encryption at rest are from RFC 4226 sections 4 and 7.5, which I did not re-read.

**What "bound" means.** A TOTP code cannot carry the action inside it. The binding is procedural, and it is the same pattern as the OWASP Transaction Authorization cheat sheet (https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html: transaction data generated and held on the server (2.3), any change invalidates earlier codes (2.6), single-use per operation within a window (1.5, 2.9, 2.10), server enforces everything (2.1), failed attempts restart the process (2.4)):
1. The service creates a pending record with an id and the digest of section 3, and renders the action itself.
2. The owner sends `/armar <id> <digest-prefix> <code>`. The service verifies the code and marks **only that record** armed.
3. The service stores the last accepted time step per secret, so a code is never accepted twice, even for another record.
4. At `not_before` the owner is asked again and must send `/ejecutar <id> <digest-prefix> <code>` with a **new** code. A code used to arm cannot run it.

The same idea is EU PSD2 "dynamic linking" (Delegated Regulation 2018/389 art. 5, https://legislation.gov.uk/eur/2018/389/article/5; the EBA says it prescribes no technical method: https://www.eba.europa.eu/single-rule-book-qa/qna/view/publicId/2018_4435). It is not our law and is cited only as a benchmark. OATH OCRA (RFC 6287, https://datatracker.ietf.org/doc/html/rfc6287) has a signature mode that really binds the data, but it needs a hardware token or a special app, so it is not used. The honest statement is that plain TOTP binds procedurally.

**Residual weakness.** TOTP is not phishing-resistant: NIST 3.2.5 says manual entry does not bind the output to the session, and OWASP lists real-time relay proxies (https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html). A relay needs the owner to type a code into the attacker's page, and the code is useless for a different digest. Acceptable for class 3; for class 4 use section 5.

**Keeping the code away from the model.**
- The best layout is a **lock service with its own bot**, which no role stack ever sees: the code is typed to that bot, never to a bot that has an LLM behind it.
- If the owner-only commands live in a role stack's plugin instead, the plugin must intercept before the model and must not write the message to the transcript, memory or logs. Whether an intercepted message is persisted in session history is to be verified in the code (not read here).
- After a successful or failed attempt the service deletes the owner's message with `deleteMessage`. A bot can delete incoming messages in private chats within 48 hours (https://core.telegram.org/bots/api#deletemessage; the exact wording was not verified on the official page). Single use and expiry make a leftover code harmless anyway.
- Alternative: type the code on the TLS page instead of in chat, so the chat carries only a link. The page shows the rendered action (what you see is what you sign). The cost is a link in chat, which is itself the phishing pattern, so use a bookmarked address and never a link from a message.

**Enrolment.**
- On the keys page, over TLS. The QR is rendered **server-side with a local library**, never by a third-party QR service, with `Cache-Control: no-store`. Enrolment completes only after the owner enters a first valid code. The secret is never shown again.
- The secret lives on the lock host, mode 600, readable by the service account only (RFC 4226 section 7.5); optionally encrypted with a key held elsewhere.
- Library: `pyotp` 2.10.0, MIT, uploaded 2026-06-14 (https://pypi.org/pypi/pyotp/json, https://github.com/pyauth/pyotp). It does not enforce single use, so we store the last accepted step ourselves.
- Issue single-use recovery codes, stored hashed. Enrol two factors (OWASP MFA sheet). Changing or resetting a factor needs an existing factor, and **the recovery path must not be Telegram**.
- Starting values **[E]**: window of plus or minus 1 step, so about 3 valid codes out of 10^6 at any moment; lock for 15 minutes after 5 failures and send a notice on the second channel.
- Caveat: an authenticator app on the same phone as Telegram collapses two factors into one device. Cloud sync of authenticator apps has been reported as not end-to-end encrypted, so turn it off (https://www.malwarebytes.com/blog/news/2023/05/google-will-eventually-add-end-to-end-encryption-to-google-authenticator; a 2023 report, current status not verified). Best: the TOTP secret lives on a second device or in a hardware key's own OATH slot.

## 5. Passkey on our own TLS page (irreversible level, built second)

**Why.** A WebAuthn credential is bound to the origin and the relying-party id, so a look-alike page gets nothing; NIST 3.2.5 names WebAuthn as the verifier-name-binding example. A fresh server challenge makes each assertion single-use. WebAuthn Level 3 is a W3C Recommendation (25 Aug 2026, https://www.w3.org/TR/webauthn-3/).

**Real transaction binding.** The challenge is `hash(digest || nonce || not_before)`. The assertion is then a digital signature over this exact action, which is stronger than any code. Set `userVerification: required` and check the UV flag server-side: OWASP says a touch alone is not a second factor. The verification steps I rely on (challenge, origin, rpIdHash, UP and UV flags, signature over authenticatorData and the hash of clientDataJSON) are the known ones; the section 7.2 text itself was beyond what I could read. Section 6.1.1: if the stored signCount and the new one are both non-zero and the new one is not greater, flag a possible clone.

**Authenticator types** (https://passkeys.dev/docs/reference/terms/).
- Synced passkeys (cloud-account backed) are convenient but recoverable through the cloud account; NIST says syncable authenticators cannot be used at AAL3 because their keys are exportable.
- Device-bound keys (FIDO2 security keys) cannot leave the device. For class 4 register one as the main key and a **second one as a spare, kept off the phone**.
- A platform authenticator with biometrics stops "stolen unlocked phone" only if UV is required.

**Libraries.**

| Library | Version | Licence | Note |
|---|---|---|---|
| `webauthn` (py_webauthn) | 3.0.1, 2026-09-25 | BSD-3-Clause | Python 3.10+, depends on pyasn1, cbor2, cryptography, pyOpenSSL; registration and authentication option and verify functions. https://pypi.org/pypi/webauthn/json, https://github.com/duo-labs/py_webauthn |
| `fido2` (Yubico) | 2.2.1, 2026-06-29 | BSD-2-Clause (HID part Apache-2.0, bundled suffix list MPL-2.0) | mostly client and authenticator side, secondary server module. https://pypi.org/pypi/fido2/json, https://github.com/Yubico/python-fido2 |
| `webauthn-rs` | not stated | MPL-2.0 | Rust; README states a SUSE product-security audit. https://github.com/kanidm/webauthn-rs |

Recommendation: `py_webauthn`, attestation `none` (we do not need device models). SimpleWebAuthn (Node) was not checked. A hand-written verifier is possible with `cryptography` but subtle mistakes are the risk, so use the library unless the dependency list is a problem.

**Telegram Mini Apps do not carry it.** The official Mini Apps page never mentions WebAuthn (https://core.telegram.org/bots/webapps). A FIDO developer thread reports `NotAllowedError` in Telegram's in-app browser and Mini App, with embedded webviews as the cause (https://groups.google.com/a/fidoalliance.org/g/fido-dev/c/wRXe-oU5MZ4); that is community discussion, not documentation. Android describes passkeys in a WebView only through host-app integration (https://developer.android.com/identity/sign-in/credential-manager-webview). Assume it does not work in a Mini App: the ceremony runs in the **system browser** (Telegram's `openLink`), and a Mini App's `initData` can at most identify the Telegram id to our page (validate server-side with the HMAC, check `auth_date`); it proves only the id, which is the weak thing. **Test on the real phones before committing.**

## 6. Medium level: the confirmation button

For class 2 the owner taps an inline button under a message sent by the lock service (or the stack's `approvals: manual` prompt today). The message text is the rendered action; the button carries only the record id and a digest prefix. The service checks that the callback came from the owner's id, that the record is pending and unexpired, and that the digest matches, then marks it approved once. Telegram limits the callback data of a button to a short string (64 bytes, from the Bot API page https://core.telegram.org/bots/api#inlinekeyboardbutton, not re-read in this session), so the id and prefix must be short.

This is a weak factor (a stolen session can tap it) and is used only where the action is reversible. It already beats a habitual "ok" typed in chat because the description is the service's and the tap is bound to one record.

## 7. Second channel and second human

- **Second-channel notice** (open decision 24 of `MULTI_BOT_TASKS.md`): every arming, expiry, execution and lockout of classes 3 and 4 is also sent to a channel that is not the Telegram account (mail to an address the owner reads on another device, or a second Telegram id of another person or device). It carries names and ids only. A taken-over Telegram account then cannot arm silently: the owner sees an arming they did not make and cancels at the console.
- **Optional second human** for class 4: a named second approver sends their own `/armar` with their own factor, and the service requires both. Off by default for one-person businesses; recommended where a business has a partner or an accountant. Changing the approver list is class 5.
- The record is a **pending state, never a fait accompli**: cancelling needs only the owner's id (cancel is always cheap and reversible); arming and running need the factor. A taken-over account can therefore cancel work, which is a nuisance, not a loss.

## 8. Build order

1. **Now, no code:** the owner's Telegram hygiene (section 9).
2. **Step A, with the lock service:** the approval blob and executor check (section 3), the medium button, and TOTP for the high level with single-use, throttle, recovery codes and enrolment on the keys page (section 4).
3. **Step B:** passkeys on the TLS page for class 4 (section 5), after a test on the owner's real devices and with a spare device-bound key. Until B exists, class 4 uses TOTP plus the full delay plus the second-channel notice, and the catalogue refuses a class 4 entry that has no executor check.
4. **Step C, optional:** second human; hardware-key-held TOTP; Cloudflare Access style hardening of the page.

Selftests to write with each step (offline, no real Telegram): replayed code refused; code for another digest refused; changed parameter invalidates; expired record refused; wrong signature, wrong digest recomputed by the executor, reused nonce refused; lockout after five failures across "sessions"; the model transcript never contains a code (a canary code in a fake chat must not appear in any log or memory file).

## 9. Telegram hygiene for the owner, today

Cheap, no code, and useful even if nothing else here is built. All are from Telegram's own guidance or from section 1 (https://telegram.org/faq):
1. Turn on **two-step verification** (a cloud password) so a login code alone does not give access, and keep its recovery e-mail on an account that has its own two-step.
2. Open the list of **active sessions** and end every one you do not recognise or no longer use; repeat monthly. Shorten the automatic session expiry if the app offers it.
3. Set a **passcode lock** on the phone and in the app, and a short auto-lock.
4. Never type a Telegram login code into any website or send it to anyone, and treat a link from a contact about a contest, petition or "verify your account" as hostile even if the contact is known: their account may be hijacked.
5. Ask the mobile carrier for a **SIM PIN and a port-out lock** where the carrier offers one **[E]**, because SIM swap defeats an SMS-only login.
6. Keep recovery codes and the TOTP secret **off Telegram and off the phone that runs it** (a second device, paper in a safe place).
7. Keep one second person or device informed (the second channel of section 7) so an arming you did not make is noticed.

## 10. What this does not solve

- A person or model that has taken over the lock host can sign approvals (section 3). Defence: small dedicated host, its own account, storage that enforces the wait itself.
- An owner who is tricked into approving a **correctly rendered** action (for example by a convincing task text) approves it. Defence: the action shown is the real one, the delay gives time to ask "why is this happening", and the first line of the Telegram message names the chain and the task that started it.
- Class 5 has no remote path at all. It is a deliberate choice, not a gap.

## 11. Open decisions (continue the numbering of `MULTI_BOT_TASKS.md`)

29. Does a small, bounded spend (prepaid balance, hard cap) get a short delay with the same factor, or the full class 3 delay? (Section 2.)
30. Where does the TOTP secret live: the owner's phone (simple, one device), a second device, or a hardware key's OATH slot (strongest, costs a key)?
31. Does the owner buy two device-bound FIDO2 keys for class 4, or accept a synced passkey for now? Synced is recoverable through a cloud account, so it is weaker.
32. Which second channel: e-mail to a separate mailbox, a second Telegram id, or both?
33. A second human approver for class 4: who, and does the business have one?

## 12. Not verified (so nobody builds on it)

Whether Telegram's in-app browser or Mini App runs WebAuthn on the owner's phones; whether an intercepted owner-only command is persisted in a role stack's session history; the current `deleteMessage` wording and limits; the current sync behaviour of authenticator apps; FBI IC3 figures against the primary source; WebAuthn L3 section 7.2 and 13 text; RFC 4226 sections 4 and 7.5; SimpleWebAuthn. The whole mechanism is a design with no code.

## 13. Sources read

Telegram: https://core.telegram.org/bots/api, https://core.telegram.org/api/end-to-end, https://core.telegram.org/bots/webapps, https://telegram.org/faq. Standards: RFC 6238, RFC 4226, RFC 6287, RFC 8032 on https://datatracker.ietf.org/; NIST SP 800-63B-4 https://pages.nist.gov/800-63-4/sp800-63b.html; W3C https://www.w3.org/TR/webauthn-3/; passkeys terms https://passkeys.dev/docs/reference/terms/; OWASP cheat sheets for Transaction Authorization and Multifactor Authentication; PSD2 RTS art. 5 (legislation.gov.uk and the EBA Q&A above). Attack reports: AhnLab, Kaspersky, FBI IC3 (links in section 1). Libraries: PyPI and GitHub pages in sections 4 and 5.
