---
name: downloads
description: "Download videos (YouTube and ~1800 sites), audio, or torrents for the person, all at once and in the background, with a guard on disk space: `gateway bajar`. Subtitles/transcripts of a whole channel and 'resume the subtitles': `subs-fetch`, never your own loop."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [download, yt-dlp, torrent, aria2, parallel, background]
---

# Downloads

One command does it: `gateway bajar ITEM [ITEM ...]`. Every item downloads **at the same time** (4 at once; 
`--paralelo N` up to 8), never one after another in a shell loop (a long list one by one is what people complain about).

- ITEM is a URL (yt-dlp: YouTube and ~1800 other sites), a `magnet:` link or a `.torrent` (aria2c, stops seeding as
  soon as it finishes), or `buscar:TEXT` for the first YouTube result (`"buscar:Videodrome 1983 trailer"`).
- A plain link to a file (`.avi`, `.zip`, `.pdf`, `.exe`, ...) is fetched too, with its size checked and resumable. Use this, never
  `curl` or `wget` by hand: a hand-made fallback can leave a truncated file and nothing says so.
- Every result is checked when it ends. `dañada` means the file is empty, unfinished or media that cannot be read: tell the person, say
  where the partial is (it is never deleted), and run the same command again to resume. Do not send a `dañada` file as if it were fine.
- `--calidad 720` (default) | `1080` | `max`; `--audio` for mp3 only.
- Files land in `/workdir/descargas/`, which survives a recreate (`/tmp` and `/root` do not). The summary at the end
  prints each file path: send them with MEDIA: lines from there.
- It refuses to start a download while the disk has less than 10 GB free, and cuts one that drives it under 5 GB.
  Say so when it happens; do not work around it by downloading somewhere else.

**Always start it in the background** so the chat keeps going: the terminal tool with `background=true` and
`notify_on_complete=true`. Tell the person what is downloading and keep answering; Hermes tells you when it is done.
`gateway bajar estado` shows what is downloading, done or failed, and the free space, when they ask how it goes.
A download started this way keeps running when the person types `/new` (the image makes a job that notifies at its end
survive it), and the next conversation is told about it in its notes. When the person comes back and asks how it goes,
check the job (`process` list, then the log) before answering from memory: the notes may be hours old.

Several requests in one turn (trailers for a list of films): put every item in **one** `gateway bajar` call. Find the
URLs first with parallel searches if needed, but you can also pass `buscar:` items and let it search.

Trailers, clips, music videos, talks and any ordinary YouTube video: download and send, with no remark about copyright.
Full films and series by torrent: the person decides; mention once, briefly, that a torrent shares from the home
connection while it downloads (copyright notices go to the home IP). Prefer legal sources when they exist. Decide from this
rule, once: never refuse and then do it when the person asks again.
Whatever you download, `archivo buscar` can find it later, and `/workdir/descargas` is where it must stay.

## Subtitles or transcripts only

`gateway bajar` cannot do this: it takes only `--calidad`, `--paralelo` and `--audio`, and any other flag (`--write-sub`,
`--skip-download`, `--help`) makes it exit with code 2 and download nothing. Do not retry it with other flags. Do not write a
downloader loop of your own either (one yt-dlp per video with 8-20 s of sleep each is more than ten times slower than `subs-fetch`). Use `subs-fetch`.

**Start a channel** (once per channel; the background tool with `notify_on_complete=true`, never `nohup`/`&` by hand, or nobody is told when it ends):

`subs-fetch <channel url> /workdir/descargas/<channel>_subs --lang <xx>-orig [--pace fast|normal|slow] [--limit N]`

- `--lang` is required for a new folder and is the channel's OWN language: `en-orig`, `ru-orig`, `es-orig` (the original caption,
  one file per video; `en.*` fetches two). There is no default on purpose: a channel in another language run as `en-orig` produces almost nothing. A folder already started remembers its language and refuses a different one (`--set-lang` changes it).
- Every channel is remembered in `/workdir/descargas/channels.json`. **"Resume the subtitles" is `subs-fetch --all /workdir/descargas`**:
  every channel already started, one after the other. Do not ask which channel.
- **How far is it? `subs-fetch --status /workdir/descargas`**: files on disk per channel, the language, RUNNING or idle, how many
  appeared in the last 10 minutes and the last hour, and whether a rate-limit pause is active. Report from that. Never from your own
  notes or a JSON of your own: a count from memory is wrong and can call a channel "blocked" that is not.
- Pace: `fast` / `normal` (default) / `slow` set the pauses (about 4, 6 and 11 seconds per video). What limits the speed is the number of
  requests the site accepts from this address, not the CPU (a video costs 0.8 s of CPU on the 4-core VM). `normal` with 5 channels at
  once is about 1,500 videos an hour, below the request rate that ran for hours without a block. Do not raise it on your
  own; if the person wants it faster, say that it risks the block that stops everything for an hour, and let them decide.
- What it skips, so a resume or a second round costs almost nothing: videos already on disk (by the `[id]` in the file name) and videos
  known to have NO captions in that language (shorts, streams, premieres, or a channel that never captions: one had 6 of 12). The channel
  is listed once and cached for 6 hours. Those caption-less videos are asked again after 14 days (auto captions can appear later).

**Rules `subs-fetch` enforces, so you do not have to remember them:**
- One job per channel: a second one on the same folder is refused ("already downloading", exit 3). Check `--status` before starting.
- At most 2 channels download at the same time (`SUBS_SLOTS`; with 5 running, the site held captions back; raise it only after a day with no soft block); the rest wait for a slot. They share one address.
- ONE rate limit (HTTP 429, "confirm you're not a bot") pauses every instance for an hour (`SUBS_COOLDOWN_MIN`, the file
  `/workdir/descargas/.subs-cooldown`) and the job ends with exit 75 and the words "RATE LIMITED". That is the failing-job case
  below: tell the person, do not rerun it on your own.
- Progress is in the channel folder (`.subs-progress.json`): channel size, how many to do, looked at, written, without captions, errors.
  `--status` turns it into "left N of M, ~X h" for each running channel. Use that for "how long is left", never your own guess.
- At the end it says how many videos had no captions in that language and how many errors. Many without captions is normal on some
  channels (half of one); if it is nearly ALL of them, the language is wrong. "MANY errors" (more than 1 in 5) means stop and look.
  If more than half of the last 30 videos answer with no captions, `subs-fetch` stops with "SOFT BLOCK" (exit 75) and everything pauses an hour:
  the site is holding captions back, the channel is not caption-less. Those findings are not written down. Never tell the person a video
  "has no subtitles" because of a list from a fast run; ask again at a calm pace.

**Keeping up with new videos, and the morning summary** (set up for the person's channels; two scheduled jobs):
- `subs-fetch --all /workdir/descargas --new` (what the job `subs-nuevos` runs every 3 hours, with no model and silent unless something
  fails): looks at the newest 40 videos of each channel, fetches only the ones not on disk. It is cheap when nothing is new.
  `--all` without `--new` first brings the newest 30 of EVERY channel, then goes on with the whole backlog.
- `subs-digest` prints the material for a summary: per channel, the newest videos that have subtitles and were not summarised yet
  (default 2 per channel, 18 in all), with title, link, length and excerpts spread over the whole video (up to 6,000 characters each,
  fewer when 18 videos have to share the 30,000-character budget of one run, so your tool result is never cut). It marks the videos it
  printed as summarised, so the next run gives the next ones. `--peek` does not mark; `--again` repeats the last one. If it says
  NADA NUEVO there is nothing to summarise: say that in one line. **If the output ends with `FALTAN N`, N videos did not fit: write
  the summary of what you have, then run `subs-digest` again for the rest (up to 3 times), and never say you covered everything while
  the last output said FALTAN.**
- The scheduled agent turn (`resumen-subs`, every morning) runs `subs-digest` and writes the summary: per video what it says in two or
  three points and whether it is worth the time, the link on each, never anything that is not in the excerpts, and a note when an
  excerpt is a sample ("extractos") and not the whole video. If the person asks for it by hand, do the same.

**Totals.** The channel size is counted by listing the channel (the "of M" in `--status` and the first line of the run). Never give a
percentage or "N left" from memory or from a page you read. Say that videos without captions will never become files (on one channel,
half), so the number of files ends below the number of videos.

## When a job is failing

Hermes raises one alarm for any background job that is failing: a message that starts "THIS BACKGROUND JOB IS FAILING,
NOT PROGRESSING" (a provider refusing requests, HTTP 429, "rate-limited", an error flood). When it arrives:

1. **Tell the person first**, in their language and before anything else: what is failing (quote the sample), how far
   the job got (count the files or read the log), and the options. Never leave it running silently.
2. **Let the person decide.** Do not stop it, restart it or switch method on your own. Say that with a rate limit every
   extra request can lengthen the block (YouTube's says "up to an hour"), so waiting before trying again is usually right.
3. Options to offer for a rate-limited site: stop now and resume later from where it stopped, slow down (a pause of
   several seconds between requests, `--sleep-requests`, `-t sleep` for yt-dlp), or use the person's own login cookies
   if they want to provide them. Do not claim the block is per IP or per account: nobody has verified which.

A whole YouTube channel (thousands of videos) is not one `gateway bajar` item. For video files, do it in slices
(`--playlist-start` / `--playlist-end`) and report after each slice; for subtitles use `subs-fetch` above.
