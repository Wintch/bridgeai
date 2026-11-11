# The person's Telegram channel (`gateway canal`, pack `difusion`)

A bot (the "marketing" bot of `MULTI_BOT_TASKS.md` section 11.3, or any stack) runs one Telegram channel for its person: it drafts posts, **the owner approves each
one in their own chat, and code posts it**. Postiz comes later and keeps the same approval step. Tested only against a fake Bot API
(`gateway_canal_selftest.py`), never against a real channel.

## The rules it implements (from `MULTI_BOT_TASKS.md` sections 13 and 14)

1. Publishing to the public needs the owner's OK in their own Telegram chat.
2. A task from the Gitea board, another bot, a page or a file can ask for a draft; none of them can publish. In code this is structural: no model-facing command publishes.
3. The approval is not text the model reads. The owner receives a one-time code in a message the bot sends straight to the Bot API; the model never receives it.

## How it works

```
model:  gateway canal borrador "TEXT" [--foto F | --video F]
          -> stores the draft in /workdir/.canal/N.json (media copied and hashed)
          -> sends the OWNER (first id of TELEGRAM_ALLOWED_USERS) two messages straight to the Bot API:
               1. the exact post, plain text, no parse_mode, no entities
               2. "to publish now send: /publicar N CODE" (a `code` entity, tap to copy), the cancel command, the 24 h life of the code
          -> the model is told only: "borrador N enviado a tu dueño para aprobar; NO está publicado"
owner:  /publicar N CODE   (plugin aibridge-controls, answered by code before the model sees the message)
          -> canal.approve(): the code matches (scrypt over code + salt + SHA-256 of the exact action), one time, not expired, fewer than 5 tries
          -> sendMessage / sendPhoto / sendVideo to the channel, the channel message id is recorded, the owner gets the post link
```

The same mechanism covers every operation, each with its own code bound to its exact content:

| Who asks | Operation | What the owner sees | What `/publicar N CODE` does |
|---|---|---|---|
| model: `borrador` / `reenviar` | publish | the post | posts it now |
| model: `programar N "AAAA-MM-DD HH:MM"` | schedule | the post and the time | stores "publish at T" (at least 60 min ahead); `canal_due.py` posts it at T |
| model: `editar N "TEXT"` (only a post this bot published) | edit | the new text, and the old one | `editMessageText` / `editMessageCaption` |
| model: `borrar N` (only a post this bot published) | delete | the current post | `deleteMessage` |

`/publicar N no` cancels whatever is pending or scheduled for N without a code (the safe direction); the model may also `descartar` a draft or a schedule.
There is no publish command in `gateway canal`, and `canal.py due` / `approve` are refused as sub-commands.

**The schedule.** Hermes cron job `canal` (`--no-agent`, `canal_due.py`, every 1 h) is created **paused** by `start_hermes.sh` where the stack has a `canal` block, resumed by
`canal.py` while something is scheduled and paused when nothing is, so a sleeping stack is not woken for nothing. The waker's cron grid is hourly (`SKILL_cron_policy.md`):
a post leaves at its time **plus up to about an hour**. A post more than 6 h late (the stack was off) is not published; the owner is told and decides again. The approval is
re-verified at T: a record changed after the owner approved it is not published. The 60-minute lead is checked twice: when the model asks and again when the owner approves
(the code lasts 24 h), so a schedule approved too late is refused with a clear sentence instead of leaving at once. At every boot `start_hermes.sh` runs `canal --sync-cron`, which resumes
the job if an approved schedule is waiting (a recreated stack starts with the job paused).

**The schedule key.** The approval of a schedule is not a bare hash of the record: `scheduled.bind` is an HMAC-SHA256 over the record's content and time, keyed by 32 random bytes in
`/hermes-persist/.canal-key` (`KEY_PATH`, mode 0600), outside the drafts folder `/workdir/.canal`. Only `approve()` creates the key, and only when the owner approves a schedule; `due()` never creates one.
A record written by hand into `/workdir/.canal` (a plain file write, the capability of the model's file tool or of an injected instruction) carries no valid MAC: it is not published, its
schedule is dropped and the owner is told "changed after you approved it". If the key is lost (volume wiped) every waiting schedule fails the same safe way and the owner approves again.
This raises the bar from "write a file" to "read a file outside /workdir, then write two"; it is not a wall (see Limits).

## Which path, and why

The task asked for inline buttons, with the one-time code as the fallback. **Implemented: the code path.** Hermes's Telegram adapter owns the `callback_query` handler
(approval prompts, model picker), and the pinned Hermes source is not in this repository (it lives only in the image build, `patches/` anchor on exact lines), so a patch
that routes our callbacks could not be written against code we can read, and an unverified patch would break the image build or silently do nothing. The code gives the
same property (the model cannot produce the approval) and uses only what is proven here: plugin commands run before the model (`aibridge-controls`).
`approve(draft_id, code, sender=None)` already takes the sender id, so a button patch is a small addition: put `canal:ID:CODE` in the button's `callback_data` (64 bytes allowed),
route the callback to `approve(..., sender=<callback user id>)`. Needs a live check on the image first.

Known consequences of the code path: the plugin command handler receives only the argument text, not the sender, so **the owner-only proof is the code**, which only the
owner's private chat receives (`sender` is checked wherever the caller knows it). The owner types a command instead of tapping a button.

## Limits (read these)

- **The stack holds the bot's token.** A model with a shell could call the Bot API itself, write a record and its own preview, or read the schedule key and sign a forged schedule. This design stops every honest path (the gateway,
  a task from Gitea, an injected instruction that can only run `gateway`) and a bare file write into the drafts folder (a forged schedule is not published), not a hijacked shell: inside one container
  anything that can read the key and write a record can forge a schedule, exactly as anything that can read the token can post. The pending-code path (publish now, edit, delete) is stronger: its
  proof is a scrypt hash of a code the stack never holds. The same limit as `MULTI_BOT_TASKS.md` 14.2: a software gate is not a wall around what the
  bot holds. The wall is a **publisher whose token is outside the stack** (the lock-service idea): a second bot, held by a small host service, that only posts a record the owner approved.
  Not built.
- `/publicar N CODE` is a message in the chat with the bot; Hermes may log inbound messages at its own level (the plugin never logs the code). A code is single-use, so a logged code
  is dead once used; a failed attempt that leaves the code valid (Telegram refused) could be read from a log by the model, which still cannot send the owner's command.
- A stolen phone or a taken-over Telegram account is human input (`MULTI_BOT_TASKS.md` 13.2, honest limit; `STEP_UP_AUTH.md` for a stronger step later).
- The first post on a new channel is class 3 in the time-lock table (`MULTI_BOT_TASKS.md` 14.1). Not enforced here: the owner's code is the only gate.
- Plain text only (no bold, no hidden links; it is how injection of formatting is closed). Telegram still turns URLs and hashtags into links by itself.
- One channel per stack, text 4096 / caption 1024 (counted in UTF-16 units, the stricter reading), photo JPEG or PNG at most 10 MB, video MP4 at most 50 MB (the cloud Bot API cap; the
  local Bot API server allows more, not used). Media posts have a caption only: editing changes the caption. Deleting is subject to what Telegram allows for a channel admin
  (not verified for old posts); its error is shown to the owner as it comes.
- Only Telegram's own refusal (a 4xx with a JSON `ok:false`, 429 included) counts as "nothing was done" and leaves the approval pending or retries the schedule. A 5xx, a proxy's HTML
  error page or a timeout is "I do not know if it went out", because the post may already exist: that is how a duplicate public post is avoided.
- A dropped connection while posting is "I do not know if it went out": the item is marked, nothing is repeated automatically, the owner looks at the channel and closes the doubt with `/publicar N no`.
- Never verified against a real channel: whether `entities` with `code` copies on tap in every client, `supports_streaming`, the edit and delete rights of the bot, and the local Bot API server's
  base URL (read from `~/.hermes/config.yaml`, set by `start_hermes.sh` when `TELEGRAM_API_ID` exists).

## Operator steps

1. In the private master (`ops/gateways.json`, never in git) add to the stack: `"canal": {"chat": "@ChannelName", "title": "Name"}` (a private channel: `"-100..."`; optional `"tz"`).
   Run `python3 ops/gateways_sync.py --check`, then without `--check` (it validates and says when it drops an entry).
2. Create the channel, add the stack's bot as **administrator** with *Post messages*, *Edit messages* and *Delete messages*. Without the rights, Telegram refuses and the owner is told why.
3. Switch the pack on for that stack: `/settings packs on difusion` (it exists only where the block does), or `ops/stack_packs.py` from the operator side.
4. Rebuild and recreate the image (new files: `canal.py`, `canal_due.py`, `SKILL_canal.md`; changed: the controls plugin, `gateway.py`, `start_hermes.sh`, the manuals). The cron job `canal`
   appears paused after the first boot. If the stack has no Telegram token at that boot, create it by hand: `hermes cron create "every 1h" --name canal --no-agent --script canal_due.py --deliver telegram --paused`.
5. Test on a channel made for the test, not the real one, with a draft, `/publicar`, an edit, a delete and a schedule 70 minutes ahead (and check the cron resumes, then pauses).

## Files

`canal.py` (installed as `/usr/local/bin/canal`; `gateway canal` runs it), `canal_due.py` (the cron script), `SKILL_canal.md`, the controls plugin (`/publicar`, `/publish`),
`gateway_canal_selftest.py` (including forged schedules, 5xx doubt, late approval and the boot sync), `ops/gateways_sync.py` (the validated `canal` entry), `ops/gateways_add_person.py` (a new person never inherits a channel), `skill_packs.json` (pack `difusion`),
`start_hermes.sh` (the paused cron job).
