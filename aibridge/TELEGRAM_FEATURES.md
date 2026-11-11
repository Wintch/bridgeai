# Telegram feature map for bridgeai

Status: read-only research. The newest Bot API in the changelog read was **10.3 (2026-08-24)**; re-check the changelog before relying on a version.

## 1 How to read it

Columns: **Feature** (what it is) | **Limits** (exact quote plus source) | **Ver** (Bot API version that introduced it) | **Hermes** (upstream support) | **Ours** (what we use today) | **V** (value for us, 0-3) | **E** (effort S/M/L) | **Risk** (privacy or risk note) | **Decision** (ADOPT NOW / LATER / SKIP).

Source keys. Every limit carries one.
- `A:<name>` = https://core.telegram.org/bots/api/methods/<name>.md
- `AT:<name>` = https://core.telegram.org/bots/api/types/<name>.md
- `A` = https://core.telegram.org/bots/api (also served at /bots/api.md)
- `F` = https://core.telegram.org/bots/features
- `Q` = https://core.telegram.org/bots/faq
- `C` = https://core.telegram.org/bots/api-changelog
- `M` = https://core.telegram.org/api/files
- `W` = https://core.telegram.org/bots/webapps
- `P` = https://core.telegram.org/bots/payments-stars.md
- `S` = https://core.telegram.org/stickers
- `H` = https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram
- `BUG` = https://bugs.telegram.org/c/3520 and /c/15667. These are user-submitted and are NOT official statements.
- `T3` = https://limits.tginfo.me/en. This is a third-party fallback.
- `R:` = a path in this repo.

Caveats that apply to the whole document:
1. The fetch tool summarised pages through a small model. Quotes are capped at about 125 characters, and a few are paraphrases (marked "para."). Re-check any limit on the page before encoding it in code.
2. Hermes columns come from the current upstream doc page (`H`). Our image pins **v0.21.6**. Checked in the pinned source: the stream consumer exists (`streaming.enabled`, transport `auto` uses sendMessageDraft in private chats, off by default). Rich messages, `command_menu`, status edit-in-place and message pinning were not checked; those cells are marked "yes*".
3. Not read: bots/inline, api/bots/webapps, and the tail of bots/payments. Material from those pages is marked UNVERIFIED.
4. Portuguese: none of our Telegram-facing text is in Portuguese (es/ru/en only).

## 2 Media and files

| Feature (what) | Limits (quote) [src] | Ver | Hermes | Ours | V | E | Risk | Decision |
|---|---|---|---|---|---|---|---|---|
| sendPhoto (inline picture) | "The photo must be at most 10 MB in size." / "The photo's width and height must not exceed 10000 in total." / "Width and height ratio must be at most 20." / caption "0-1024 characters after entities parsing". The doc names NO accepted file formats. [A:sendphoto] | old; has_spoiler 6.4 | yes, method chosen by extension (png jpg jpeg gif webp bmp tiff svg) [H] | yes, `.jpg` via `MEDIA:` | 3 | S | Telegram keeps server-side sizes up to "bounded by 1280x1280 pixels" [M]. Tall screenshots (ratio over 20) must go as a document | ADOPT NOW: JPEG (PNG only if under 10 MB) |
| Formats AVIF, HEIC/HEIF, JPEG XL, animated WebP as photos | NO official statement in any page read. Bug tracker: a file is "currently the only option for AVIF." Animated AVIF: "Only the first frame is displayed as picture, but video does not playback." [BUG]. WebP "is unnecessarily limited to stickers" (commenter) [BUG] | n/a | Hermes list includes webp, not avif, heic or jxl [H] | rule: never send `.avif` or `.webp` [R:aibridge/SKILL_image_requests.md:28-32] | 3 | S | UNVERIFIED for all four on sendPhoto. See "What happened with AVIF" below | ADOPT NOW: convert to JPEG, original as document |
| sendDocument (lossless, PDF, any file) | "Bots can currently send files of any type of up to 50 MB in size". Thumbnail: JPEG, under 200 kB, max 320 px. URL works only for PDF and ZIP: "In sendDocument, sending by URL will currently only work for .PDF and .ZIP files." [A:senddocument, A] | 4.0 thumbnails | yes (pdf txt md csv json office archive) [H] | yes, from `/workdir/descargas` | 3 | S | No preview in chat. A photo can never be re-sent as a document by file_id | ADOPT NOW |
| sendVideo (inline player) | "Telegram clients support MPEG4 videos (other formats may be sent as Document)." 50 MB upload on the cloud. Has `supports_streaming`, `cover`, `start_timestamp` (8.3). `Video.qualities` added in 9.4 (meaning UNVERIFIED) [A:sendvideo, AT:video, C] | cover 8.3; qualities 9.4 | yes | yes, generated videos via `MEDIA:`. Whether `supports_streaming` or thumbnails are set is UNVERIFIED | 3 | S | H.264/AAC MP4 with moov atom first is my recommendation. Codec profile is UNVERIFIED in the docs | ADOPT NOW: 720p or lower for slow phones |
| sendAnimation (silent loop) | "GIF or H.264/MPEG-4 AVC video without sound". 50 MB cloud [A:sendanimation] | old | `MEDIA:` .gif only | no | 2 | S | Animated WebP/AVIF not listed: UNVERIFIED | ADOPT NOW: MP4 without audio track, not GIF |
| sendVoice (voice reply) | "your audio must be in an .OGG file encoded with OPUS, or in .MP3 format, or in .M4A format". Upload: "Bots can currently send voice messages of up to 50 MB in size". By URL only: "the file must have the type audio/ogg and be no more than 1MB in size", and "1-20MB voice notes will be sent as files" [A:sendvoice, A] | 2015; InputMediaVoiceNote 10.2 | yes; `voice_compatible` needed | yes: `tts.provider=bridge`, OGG/Opus, `voice_compatible true`. Without it the file arrives as a document [R:aibridge/start_hermes.sh:562-572] | 3 | S | Pass `duration`; send `record_voice` first | ADOPT NOW (already) |
| Inbound voice notes | Cloud getFile "bots can download files of up to 20MB in size." [A:getfile, Q] | old | yes (STT) | yes: `stt.provider=bridge`, never the VM CPU | 3 | S | 20 MB is never a problem for speech | ADOPT NOW (already) |
| sendAudio (music player) | "Your audio must be in the .MP3 or .M4A format." 50 MB [A:sendaudio] | old | yes | no | 0 | S | Not for speech replies | SKIP |
| sendVideoNote (circle) | "a rounded square MPEG4 video of up to 1 minute long." "Sending video notes by a URL is currently unsupported." Size cap UNVERIFIED (T3: 384 px, 12 MB) [A:sendvideonote] | 3.0 | inbound yes (PR #147572 merged 2026-11-01) | inbound via our patch `telegram_video_note.py` (adds ffmpeg audio track) | 1 | M | Outbound niche. No caption parameter | SKIP outbound |
| sendMediaGroup (album) | "must include 2-10 items". "Documents and audio files can be only grouped in an album with messages of the same type." [A:sendmediagroup] | 3.5; doc/audio albums 5.0 | inbound merged (item 70). Outbound albums UNVERIFIED | no | 2 | M | Each item counts toward the 1 msg/s per chat guidance [Q] | LATER |
| file_id reuse, URL, multipart | "There are no limits for files sent this way." (file_id). "5 MB max size for photos and 20 MB max for other types of content." (URL). "10 MB max size for photos, 50 MB for other files." (upload). "file_id is unique for each individual bot and can't be transferred from one bot to another." FAQ: "Yes, file_ids can be treated as persistent." [A "Sending files", Q] | 2.2 | no file_id cache | no | 2 | M | Upload once, store file_id, reuse. Saves bandwidth on slow links and wakes | LATER |
| getFile (inbound download) | "It is guaranteed that the link will be valid for at least 1 hour." "This function may not preserve the original file name and MIME type." Photos arrive as several PhotoSize entries; take the largest [A:getfile, AT:file] | old | yes | yes, plus our disk-copy patch for big files | 3 | S | file_size can exceed 2^31, use 64-bit ints | ADOPT NOW (already) |
| Local Bot API server (`--local`) | "Download files without a size limit." "Upload files up to 2000 MB." "Upload files using their local path and the file URI scheme". Cloud limits: 20 MB down, 50 MB up [A "Using a Local Bot API Server", F] | 5.0 | yes (needs `TELEGRAM_API_ID`) | yes. `telegram-bot-api` in compose; patches `telegram_large_files.py`; hourly media cleanup [R:aibridge/docker-compose.yml] | 3 | done | Without `--local` the server still caps at 20/50 MB (found 2026-10-01). The file:// outbound path for files over 50 MB is not confirmed exercised since deploy (UNVERIFIED) | ADOPT NOW (already) |
| editMessageMedia | "Use this method to edit animation, audio, document, live photo, photo, or video messages" or "to replace a text or a rich message with a media". Inline messages: "a new file can't be uploaded" [A:editmessagemedia] | 7.11 (text to media) | UNVERIFIED | no | 1 | M | Handy for "drawing..." placeholder then picture | LATER |
| Spoiler, caption above media | `has_spoiler`: "Pass True if the photo needs to be covered with a spoiler animation". Also `show_caption_above_media` [A:sendphoto] | 6.4 | UNVERIFIED | no | 1 | S | Useful for sensitive images | LATER |
| Live photos (new) | "The video must be no longer than 10 seconds and must not exceed 10 MB in size." "Sending live photos by a URL is currently unsupported." [A:sendlivephoto] | 10.0 (2026-05-08) | no | no | 1 | M | Old-client rendering UNVERIFIED | SKIP |
| Stickers | "Use this method to send static .WEBP, animated .TGS, or video .WEBM stickers." Pack limits: TGS 64 KB, WEBM 256 KB, one side exactly 512 px [A:sendsticker, S] | 4.4, 5.7 | inbound only (static vision) | no | 0 | M | None | SKIP |
| Paid media (Stars) | "The number of Telegram Stars that must be paid to buy access to the media; 1-25000" [A:sendpaidmedia] | 9.3 raised cap | no | no | 0 | L | Policy: we supply no keys or billing | SKIP |

### What happened with AVIF, and the format test

An `.avif` sent as `MEDIA:` arrived in Telegram as a plain file with no preview. We then sent the same 1024x1024 picture and an
8 s 720p clip in every format straight through the Bot API (ops bot, operator's own chat) and the operator checked phone and PC.

| # | Sent as | Telegram's answer | Shown |
|---|---|---|---|
| 1 | sendPhoto JPEG q85, 263 KB | photo, largest size 1024 px, 270 KB | preview |
| 2 | sendPhoto WebP q80, 184 KB | photo, 278 KB | preview |
| 3 | sendPhoto AVIF, 216 KB | `Bad Request: IMAGE_PROCESS_FAILED` | nothing |
| 4 | sendPhoto PNG, 1.9 MB | photo, 291 KB | preview |
| 5 | sendDocument AVIF | document `image/avif`, no thumbnail | **no preview** |
| 13 | sendDocument AVIF + our JPEG thumbnail | document with thumbnail | **no preview** |
| 6 | sendDocument WebP | turned into a **sticker** | shown as sticker |
| 7 | sendVideo H.264/AAC MP4, 1.76 MB | video, thumbnail made by Telegram | plays |
| 8 | sendVideo HEVC (hvc1) MP4, 0.69 MB | video, thumbnail made by Telegram | plays |
| 9 | sendVideo AV1 MP4, 1.11 MB | video, **no thumbnail made** | plays |
| 14 | sendVideo AV1 + our thumbnail, `supports_streaming` | video with thumbnail | plays |
| 10 | sendVideo VP9/Opus WebM | arrived as a **document** | **no preview** |
| 11, 12, 15 | sendAnimation H.264 / AV1 (no audio) | animation | plays |

What this settles:
- **AVIF cannot be shown in Telegram** in any way: refused as a photo, no preview as a file even with a thumbnail. It is
  Telegram, not Hermes. Fix: `patches/telegram_image_preview.py` converts AVIF, HEIC/HEIF, JPEG XL, BMP, TIFF (and a WebP that
  would go out as a file) to a JPEG and sends a photo.
- **Photos are re-encoded by Telegram**: the person downloads Telegram's JPEG (270-291 KB here) whatever we upload. A lighter
  upload format (WebP, AVIF) saves the person nothing; JPEG q85-90 stays the default because every platform shows it.
- **Videos are not re-encoded**: the file we upload is the file the person downloads, so the codec matters for their data.
  AV1 and HEVC play on the operator's phone and PC; H.264 is the safe choice for unknown or old devices and for WhatsApp.
  Telegram makes no thumbnail for AV1; the pinned Hermes `send_video` already sends its own JPEG thumbnail and real geometry.
  The clip here is a zoom over one picture, so the sizes do not rank the codecs for real footage (measure on real video).
- **WebM/VP9 goes as a file**: never send `.webm` as a video.

### DELIVERY GUIDE (what to send, with which method)

| Output | Method and format | Notes |
|---|---|---|
| AI picture (e.g. 1024x1024) | sendPhoto, JPEG about q90 (100-250 KB), caption under 1024 characters | Far inside the 10 MB, 10000 and ratio-20 limits [A:sendphoto]. Offer the lossless file separately on request |
| Lossless original (PNG, TIFF, AVIF, HEIC, upscales) | sendDocument, up to 50 MB (2000 MB local), JPEG thumbnail under 200 kB and at most 320 px | Pair with a JPEG preview sent as photo. A 13 MB PNG upscale once failed as a photo (10 MB cap); JPEG q92 fixed it [R:HERMES_ARCHITECTURE.md ~4319] |
| Short silent loop | sendAnimation, H.264 or AV1 MP4 with no audio track, set width, height and duration | Not GIF (larger). Both played (tested) |
| Voice reply | sendVoice, OGG/Opus mono, `duration` set, preceded by `record_voice` chat action; reuse file_id | MP3 and M4A also accepted. Keep `voice_compatible true` or it arrives as a file |
| Video | Not re-encoded by Telegram. AV1 or HEVC in MP4 play on current clients and are the lightest; H.264/AAC for unknown or old devices. Never WebM/VP9 (arrives as a file). Long video: cloud transcode to MP4 under 50 MB and send as sendVideo (`supports_streaming`, thumbnail). Local server: up to 2000 MB | For a slow phone prefer the smaller file even when the server allows more |
| PDF | sendDocument. By URL only up to 20 MB; by upload 50 MB. Reuse file_id | No inline preview. Opens as a file |
| AVIF / HEIC / JPEG XL / BMP / TIFF | Converted to a JPEG photo by our patch. AVIF never previews in Telegram, even as a document with a thumbnail (tested) | WebP as a photo previews; WebP as a document becomes a sticker (tested) |
| Send as document, not photo | Any lossless or non-JPEG/PNG image; images over 10 MB; width+height over 10000 or ratio over 20; STL/3MF (with PNG preview, UNVERIFIED) | Never send as photo something you cannot afford to have recompressed |

## 3 Interaction and UI

| Feature (what) | Limits (quote) [src] | Ver | Hermes | Ours | V | E | Risk | Decision |
|---|---|---|---|---|---|---|---|---|
| Inline keyboard buttons (confirmations, choices) | "callback_data: 1-64 bytes". `copy_text` "1-256 characters" (UNVERIFIED: not on the InlineKeyboardButton page; would be on CopyTextButton). `answerCallbackQuery` text 0-200 chars [A "InlineKeyboardButton"] | copy_text 7.11; colors and icons 9.4 | yes: /model picker, clarify buttons [H] | Hermes only. A callback wakes a sleeping stack via the waker. No own buttons | 3 | M | A sleeping stack cannot answer the callback in time. The waker should call answerCallbackQuery | ADOPT NOW |
| Exec approvals (buttons or typed yes/no?) | Hermes doc: dangerous commands "prompt for a reply of yes/y ... no/n". Our SOUL says buttons [H, R:aibridge/SOUL_bridgeai.md:23] | n/a | typed per doc; buttons per v0.23 "stale-card" | DISCREPANCY: unknown for pin v0.21.6. One prompt waited 300 s and was BLOCKED | 3 | S | Test on `guests/prueba`. Bot API 10.3 `DisabledButton` / `disabled` lets a stale approval card be greyed out instead of left live | ADOPT NOW: verify |
| Reply keyboards (request_location etc.) | `input_field_placeholder` "1-64 characters"; special buttons "private chats only" [A "ReplyKeyboardMarkup"] | style 9.4 | no | no | 1 | S | Location sharing is sensitive. Make it opt-in | LATER |
| Commands, scopes, language menu | "At most 100 commands can be specified." `language_code` is a two-letter code. Lookup: chat+lang, chat, all_private_chats+lang ... default [A "BotCommandScope"] | old | `command_menu` (max 60 default) [H] | yes, `help_menu.py` (7 names). Whether `language_code` is used is UNVERIFIED | 2 | S | Command names are lowercase latin only. Russian speakers type latin | ADOPT NOW: per-language lists ru/es/en/pt |
| Reactions by the bot | "Currently, as non-premium users, bots can set up to one reaction per message." [A "setMessageReaction"] | 7.0 | `telegram.reactions`, default false (eyes, then thumbs up or down) [H] | no | 2 | S | Our feedback plugin must ignore the bot's own reactions | ADOPT NOW (guest first) |
| Reactions from the person | Bot must be admin and list `message_reaction` in `allowed_updates`. Private-chat behaviour UNVERIFIED [A "Update"] | 7.0 | yes (platform event) | yes: `aibridge-feedback` votes on the model [R:aibridge/hermes_plugins/aibridge-feedback] | 2 | done | Only vote and message id travel | ADOPT NOW (already) |
| sendMessageDraft (streaming) | Private chats only. text "0-4096 characters after entities parsing". "Pass True to show the user a button to stop further drafts." [A "sendMessageDraft"] | 9.3; all bots 9.5; stop button 10.3 | `streaming.transport` auto/draft/edit/off, "Telegram restricts sendMessageDraft to private chats" [H]. Present in our pin (checked), off by default | no: streaming off on all stacks (flood incident 2026-10-21) | 3 | M | Edit-based streaming caused flood control. Drafts are a different path but untested by us. Extras: empty text shows a "Thinking..." placeholder (10.0); `keep_on_stop`; the bot gets a `MessageGenerationStopped` update when the person presses stop (10.3) | LATER: pilot on guest |
| Chat actions (typing, upload_photo, record_voice ...) | "The status is set for 5 seconds or less." [A:sendchataction] | old | typing yes (UNVERIFIED which actions) | waker sends a text only | 3 | S | Repeat every ~4 s while waking or drawing | ADOPT NOW |
| Edit message for progress | Text 1-4096 chars. Edit and delete rules differ by case. No general edit window for bot messages found (UNVERIFIED) [A "Updating messages"] | old | status edit-in-place [H] (yes*) | no | 2 | M | Rapid edits risk 429 | LATER |
| Text formatting (HTML, MarkdownV2, entities) | "Text of the message to be sent, 1-4096 characters after entities parsing". "Offset in UTF-16 code units to the start of the entity". Expandable blockquote exists [A "Formatting options"] | blockquote 7.0; expandable 7.4 | MarkdownV2 conversion, tables to bullets [H] | via Hermes | 2 | S | HTML needs 3 escapes, MarkdownV2 about 18. Prefer HTML for model output | LATER |
| Expandable blockquote for long answers | Same source. We now send over 12000 chars as preview plus `reply.md` [R:aibridge/patches/telegram_long_reply_file.py] | 7.4 | no | n/a | 1 | S | Fine between 4096 and 12000 chars | LATER |
| Rich messages | "Up to 32768 UTF-8 characters in the rich message text". "Up to 500 blocks". "Up to 50 media attachments in total." [https://core.telegram.org/bots/api/rich-messages.md]. Input may be HTML or Markdown directly (`InputRichMessage`), and `sendRichMessageDraft` streams them (10.1) | 10.1 (2026-06-11) | opt-in `rich_messages` [H] (yes*) | no | 2 | M | New. Test Android, iOS and desktop. Keep a plain fallback | LATER |
| Link preview options | "URL to use for the link preview. If empty, then the first URL found in the message text will be used." [A "LinkPreviewOptions"] | 7.0 | `disable_link_previews`, default false [H] | not set (UNVERIFIED) | 2 | S | Every link in a venue list shows a card. Privacy: previews can fetch the URL | ADOPT NOW |
| Deep links / start parameter | "The parameter can be up to 64 characters long." "A-Z, a-z, 0-9, _ and - are allowed." [F "Deep linking"] | old | UNVERIFIED | no | 1 | S | Never put secrets or personal data in the link | LATER |
| Mini Apps | CloudStorage "up to 1024 items per user"; DeviceStorage "up to 5 MB per user" [W] | 6.0; 8.0, 9.0 | UNVERIFIED | no | 1 | L | Needs public HTTPS hosting. Conflicts with our privacy posture | SKIP (revisit for a settings page) |
| Inline mode | "No more than 50 results per query are allowed." [A "answerInlineQuery"] | 2016 | no | no | 0 | L | Must answer during the request, which fights with sleeping stacks | SKIP |
| Polls and quizzes | question "1-300 characters"; "1-12 answer options"; `open_period` "5-2628000" [A "sendPoll"] | multi-answer 9.6; poll media 10.0 | no | no | 0 | S | Buttons are better for single choices | SKIP |
| Topics in private chats | "Topic name, 1-128 characters" [F] | 9.3; bot-created 9.4 | Private Chat Topics [H] (yes*) | no | 1 | M | Needs Threaded Mode in BotFather | LATER |
| Bot profile (name, descriptions, per language) | description "0-512 characters"; short description "0-120 characters" [F] | 7.x | `status_indicator` default false [H] | no | 1 | S | Localise ru/es/en/pt | LATER |
| Delete messages | "A message can only be deleted if it was sent less than 48 hours ago." "Bots can delete incoming messages in private chats." [A "deleteMessage"] | old | UNVERIFIED | no (open task: delete the message that carries a key) | 2 | S | Our key-handling task must delete within 48 h | ADOPT NOW |
| Guest mode, bot-to-bot, managed bots | "Up to 3 guest bots can be mentioned in one message." "Bot-to-bot communication can easily result in infinite interaction loops." [F] | 10.0; managed bots 9.6 | guest_mode, bot_loop_guard [H] | no | 0 | L | Expose the bot to chats we do not control, or loop risk, or one bot reads every managed token | SKIP |
| Business, checklists, dice, effects, ephemeral, stories, gifts, verification | Business: replies only "private chats with incoming messages in the last 24 hours". Checklists need `business_connection_id` [F, C] | various | no | no | 0 | L | Privacy heavy. Not for personal assistants | SKIP |

## 4 Platform, limits and operations

| Feature (what) | Limits (quote) [src] | Ver | Hermes | Ours | V | E | Risk | Decision |
|---|---|---|---|---|---|---|---|---|
| Update delivery | "There are two mutually exclusive ways of receiving updates for your bot". Undelivered updates "will not be kept longer than 24 hours." [A; the FAQ does not say this] | old | polling default; webhook needs `TELEGRAM_WEBHOOK_SECRET` [H] | polling. The waker peeks `getUpdates` with no offset while the stack sleeps [R:aibridge/ops/wake/waker.py] | 3 | done | A sleep over 24 h loses messages. Only one consumer may poll (409) | ADOPT NOW (already) |
| getUpdates | "Defaults to 0, i.e. usual short polling." "This method will not work if an outgoing webhook is set up." Limit 1-100 (para.) [A:getupdates] | old | yes | yes | 3 | done | Our waker: 100 queued non-allowed updates hide a person's message | ADOPT NOW (already) |
| `allowed_updates` | Empty list means all types except `chat_member`, `message_reaction`, `message_reaction_count` (para.) [A:getupdates, AT:update] | old | yes | waker looks at message, edited_message, channel_post, callback_query only | 2 | S | A reaction or `my_chat_member` never wakes a stack. Probably fine | ADOPT NOW |
| Webhook | Ports "443, 80, 88, 8443". "A webhook requires SSL/TLS encryption, no matter which port is used." "allow traffic from 149.154.160.0/20 and 91.108.4.0/22." "IPv6 is currently not supported for webhooks." `secret_token` 1-256 chars in `X-Telegram-Bot-Api-Secret-Token` [https://core.telegram.org/bots/webhooks for SSL, IPs and IPv6; A:setwebhook for the secret] | secret 6.1 | yes [H] | no | 1 | L | While a webhook is set `getUpdates` is refused. The waker would have to become the receiver | LATER |
| Webhook failures | A 2xx answer is needed. Retry count UNVERIFIED. A webhook returning 410 for over 23 h can be removed (para.) [C 4.0, A:setwebhook] | 4.0 | n/a | n/a | 1 | S | Answer 200 at once (queue), do not hold while a VM boots. Deduplicate on `update_id` | n/a |
| Replay hazard | Hermes: "a preserved queue can redeliver an update the crashed instance partially processed." [H] | n/a | `drop_pending_on_cold_boot` | we set it false so the waking message survives. Open item "every message stored twice since 10-29" may be related (lead, UNVERIFIED) | 2 | S | Check the replay path | ADOPT NOW: investigate |
| Rate limits | "In a single chat, avoid sending more than one message per second." "In a group, bots are not be able to send more than 20 messages per minute." "bots are not able to broadcast more than about 30 messages per second" [Q] | n/a | n/a | flood incident 2026-10-21 (806k-char runaway, `retry_after` 257 s) | 3 | done | Queue per chat. Honour `retry_after` [AT:responseparameters] | ADOPT NOW (already) |
| Paid broadcasts | Official pages DISAGREE. api.md: "a bot must have at least 10,000 Stars on its balance." FAQ: "a bot must have at least 100,000 Stars on its balance" [A, Q] | 7.11 | n/a | no | 0 | n/a | Verify in @BotFather before relying on either | SKIP |
| Cloud to local server migration | "You **must** log out the bot before running it locally." After logOut the bot cannot return to the cloud for 10 minutes; `close` gives 429 for the first 10 minutes (para.) [A:logout, A:close] | 5.0 | `base_url`, `local_mode` | whether logOut was done per bot is UNVERIFIED (no script does it) | 2 | S | Test with a spare bot, never a person's | ADOPT NOW: check |
| Privacy of chats | "Secret chats use end-to-end encryption, thanks to which we don't have any data to disclose." Bot chats are cloud chats [https://telegram.org/faq] | n/a | n/a | n/a | 3 | n/a | Telegram and the bot host can read bot chats. Bots in secret chats: UNVERIFIED (inferred no). Say this plainly to users | ADOPT NOW |
| What a bot knows about a user | "The language_code is an optional field – it could be empty." Phone number only if the user shares a contact [AT:user] | n/a | n/a | per-person language kept by us | 2 | n/a | Keep per-person language as the source of truth | ADOPT NOW (already) |
| Access control | `TELEGRAM_ALLOWED_USERS` numeric ids; "Always set TELEGRAM_ALLOWED_USERS to restrict who can interact with your bot." [H] | n/a | yes | yes, keys page and `stack_telegram.py` | 3 | done | Bot token message stays in the person's chat | ADOPT NOW (already) |
| Stars and payments | "Payments for digital goods and services must be carried out exclusively in Telegram Stars." Pre-checkout answer "within 10 seconds" [P, https://core.telegram.org/bots/payments] | 7.4 | no | no | 0 | L | Policy: no keys supplied by the operator | SKIP |
| Network (proxy, fallback IPs) | `proxy_url`, DoH fallback IPs [H] | n/a | yes | no | 0 | S | Only if a person's network blocks Telegram. No evidence in the repo | SKIP |

Version timeline [C]:

| Version | Date | Relevant additions |
|---|---|---|
| 7.4 | 2024-05-28 | Stars, message effects |
| 7.11 | 2024-10-31 | `allow_paid_broadcast`, `copy_text`, text-to-media edit |
| 8.0 | 2024-11-17 | Mini App fullscreen, storage, sensors, subscriptions |
| 8.3 | 2025-02-12 | video cover, start_timestamp |
| 9.0 | 2025-04-11 | paid media 10000 Stars, business tools |
| 9.1 | 2025-07-03 | checklists, polls up to 12 options |
| 9.3 | 2025-12-31 | `sendMessageDraft`, topics in private chats, paid media 25000 |
| 9.4 | 2026-02-09 | button colors, bots create private topics, `Video.qualities` |
| 9.5 | 2026-03-01 | `sendMessageDraft` for all bots, `date_time` entity |
| 9.6 | 2026-04-03 | managed bots, multi-answer quizzes |
| 10.0 | 2026-05-08 | guest mode, `sendLivePhoto`, bot-to-bot, poll media |
| 10.1 | 2026-06-11 | rich messages |
| 10.2 | 2026-07-14 | ephemeral messages, `InputMediaVoiceNote`, Mini App hardening (on 2026-07-20) |
| 10.3 | 2026-08-24 | draft stop button (`can_stop`, `keep_on_stop`, `MessageGenerationStopped`), rich message buttons, `DisabledButton` and a `disabled` field on inline buttons, `force_reply` inside keyboards, `EphemeralMessageParameters`, `replace_callback_query_message`, compact tables, expandable quotes and document blocks in rich messages (changelog read through a summariser, para.) |

Deprecations to watch [C]: `Poll.correct_option_id` became `correct_option_ids` (9.6), and `can_send_gift` became `accepted_gift_types` (9.0). Pin the library version.

Doc conflicts to remember:
- The FAQ says bots never see other bots' messages "regardless of mode". Features and changelog 10.0 describe an opt-in mode, so the FAQ is stale.
- Poll `open_period` is now 5-2628000 s. Older notes saying 5-600 are outdated.

## 5 Gaps: Telegram features neither Hermes nor we use well, ranked by value for us

| # | Gap | Why for us | V | E | Notes |
|---|---|---|---|---|---|
| 1 | Convert non-JPEG images and add a delivery rule | AVIF arrived as a file. People expect to see pictures | 3 | S | The delivery guide above. |
| 2 | Chat action while waking or drawing | Wake takes 20-60 s. The waker sends only a text. `typing` or `upload_photo` shows life | 3 | S | Repeat every ~4 s. The waker already holds the token |
| 3 | Localised wake notice (ru, pt) | The waker's wake line is hardcoded Spanish. A Russian-only person gets Spanish. No Portuguese anywhere | 3 | S | `R:aibridge/ops/wake/waker.py` |
| 4 | Buttons for confirmations instead of typing yes/no | Phone users on slow links. Fewer typos | 3 | M | First resolve the approval discrepancy (row in section 3) |
| 5 | Delete key-bearing messages | Our open task. Bot token and key messages remain in chat | 2 | S | `deleteMessage` works within 48 h in private chats |
| 6 | Reactions by the bot as acknowledgement | Cheap "received" signal, no extra message | 2 | S | `telegram.reactions`. Make sure the feedback plugin ignores the bot's own reactions |
| 7 | Disable link previews by default | Venue lists show many cards | 2 | S | `disable_link_previews` |
| 8 | Per-language command menus | ru, es, en, pt people see their own language | 2 | S | `setMyCommands` with `language_code` |
| 9 | Outbound location or venue for walking people | Today we send a Maps link. A bot can send a location | 2 | M | `sendLocation` / `sendVenue`. No code exists |
| 10 | Streaming drafts | "Thinking..." while the model writes, fits slow phones | 3 | M | Present in v0.21.6, off. Pilot on a guest stack only |
| 11 | Albums for several pictures | Fewer messages, one flood-count each | 2 | M | Hermes outbound support UNVERIFIED |
| 12 | Edit-message progress for long jobs | One message updated instead of many | 2 | M | Hermes has status edit-in-place upstream (yes*) |
| 13 | file_id cache | Faster resends, no re-upload | 2 | M | Per bot only |
| 14 | Deep links to open a skill pack | `t.me/bot?start=<token>` could open a skill pack | 1 | S | Parameter max 64 chars. No secrets |
| 15 | Expandable blockquote for long answers | Keeps 4096-12000 char answers compact | 1 | S | Beyond 12000 we already send a file |
| 16 | Rich messages, topics in private chats | Tables and parallel sessions | 2 | M | New, test on all clients |
| 17 | Voice improvements | Pass `duration`, use `record_voice`, reuse file_id | 1 | S | Voice already works |
| 18 | Mini App for settings or manual | Needs public HTTPS and hosting | 1 | L | Conflicts with privacy posture |
| 19 | Webhook mode | Only useful if the waker becomes the receiver | 1 | L | Waker polling works |

### Found by the verifier, not in the tables above

- `sendRichMessageDraft` (10.1): streamed rich messages; `editMessageText` accepts rich messages.
- `DisabledButton` (10.3): grey out a stale button. Relevant to the exec-approval cards.
- `deleteMessageReaction`, `deleteAllMessageReactions` and the `can_react_to_messages` permission (10.0).
- Ephemeral messages (10.2, reworked 10.3): group messages visible to one user and the bot. Groups only, so SKIP for private assistants.
- Communities (10.2, 10.3), `BotSubscriptionUpdated` (10.2), `answerChatJoinRequestQuery` and `sendChatJoinRequestWebApp` (10.1): SKIP.
- 9.4: custom emoji in bot messages, `setMyProfilePhoto` / `removeMyProfilePhoto`, `getUserProfileAudios`, bots can stop users creating or deleting topics in private chats.
- 9.3 and 10.1-10.2: message effects on forward and copy, link media in polls (`InputMediaLink`), voice blocks inside rich messages (`RichBlockVoiceNote`), `is_rtl` for right-to-left text.
- Still not read: the changelog before 9.0, bots/features in full, bots/webapps, api/files, bots/payments, bots/inline.

## 6 Recommended next steps (in order, each small and reversible)

Done: image formats (tested through the Bot API; `patches/telegram_image_preview.py` and the skill converted to JPEG). Still open:
1. Localise the wake notice (add ru and pt, take the person's `notice_lang`) in `ops/wake/waker.py`.
2. Waker `sendChatAction`: send `typing` every ~4 s while waking, behind an env flag.
3. Resolve the approvals discrepancy (buttons or typed yes/no): test on the guest stack, then align `SOUL_bridgeai.md` and the architecture doc.
4. Quiet defaults, guest first: `disable_link_previews` and `telegram.reactions` via `cfg_set` in `start_hermes.sh`; confirm the feedback plugin ignores the bot's own reactions.
5. Per-language command menus (`patches/help_menu.py` for `language_code` ru/es/en/pt).
6. Pilot draft streaming (`streaming.enabled: true`, transport `draft`) on the guest stack only.

## Unverified, summarised

- Settled by test: sendPhoto takes JPEG, PNG, WebP; refuses AVIF; AVIF never previews as a file.
- Webhook retry count and schedule; whether bots receive reaction updates in private chats.
- Official size cap for video notes, `live_period` range on the first `sendLocation`, and the meaning of `Video.qualities`.
- The paid-broadcast Stars threshold (the two official pages disagree).
- Whether logOut was done per bot before moving to the local server.
- Whether the pinned release has rich messages, status edit-in-place and `command_menu` (drafts: yes, checked).
