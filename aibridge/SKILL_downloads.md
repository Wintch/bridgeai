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
`--paralelo N` up to 8), never one after another in a shell loop (on 2026-10-31 twelve trailers went one by one and
the person asked for everything in parallel).

- ITEM is a URL (yt-dlp: YouTube and ~1800 other sites), a `magnet:` link or a `.torrent` (aria2c, stops seeding as
  soon as it finishes), or `buscar:TEXT` for the first YouTube result (`"buscar:Videodrome 1983 trailer"`).
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
rule, once: never refuse and then do it when the person asks again (it happened on 2026-11-05 with a trailer).
Whatever you download, `archivo buscar` can find it later, and `/workdir/descargas` is where it must stay.

## Subtitles or transcripts only

`gateway bajar` cannot do this: it takes only `--calidad`, `--paralelo` and `--audio`, and any other flag (`--write-sub`,
`--skip-download`, `--help`) makes it exit with code 2 and download nothing. Do not retry it with other flags. Do not write a
downloader loop of your own either (on 2026-11-04 yours reached about 90 subtitles an hour, one yt-dlp per video and 8-20 s of
sleep each; `subs-fetch` reached about 1,100 an hour on the same machine). Use `subs-fetch`.

**Start a channel** (once per channel; the background tool with `notify_on_complete=true`, never `nohup`/`&` by hand, or nobody is told when it ends):

`subs-fetch <channel url> /workdir/descargas/<channel>_subs --lang <xx>-orig [--pace fast|normal|slow] [--limit N]`

- `--lang` is required for a new folder and is the channel's OWN language: `en-orig`, `ru-orig`, `es-orig` (the original caption,
  one file per video; `en.*` fetches two). There is no default on purpose: on 2026-11-05 a Russian channel ran an hour as `en-orig`
  and produced almost nothing. A folder already started remembers its language and refuses a different one (`--set-lang` changes it).
- Every channel is remembered in `/workdir/descargas/channels.json`. **"Resume the subtitles" is `subs-fetch --all /workdir/descargas`**:
  every channel already started, one after the other. Do not ask which channel.
- **How far is it? `subs-fetch --status /workdir/descargas`**: files on disk per channel, the language, RUNNING or idle, how many
  appeared in the last 10 minutes and the last hour, and whether a rate-limit pause is active. Report from that. Never from your own
  notes or a JSON of your own: on 2026-11-05 a report said 570 while 1,339 were on disk, and called a channel "blocked" that had 328.
- `normal` waits 1 s between requests and 2 s per subtitle; `fast` halves that, `slow` doubles it and more. The machine has 4 cores
  and each video costs CPU (yt-dlp runs a small Node program), so the speed is limited by the machine as much as by the pauses:
  more channels in parallel does not make it faster.

**Rules `subs-fetch` enforces, so you do not have to remember them:**
- One job per channel: a second one on the same folder is refused ("already downloading", exit 3). Check `--status` before starting.
- At most 3 channels download at the same time (`SUBS_SLOTS`); the rest wait for a slot. They share one address.
- ONE rate limit (HTTP 429, "confirm you're not a bot") pauses every instance for an hour (`SUBS_COOLDOWN_MIN`, the file
  `/workdir/descargas/.subs-cooldown`) and the job ends with exit 75 and the words "RATE LIMITED". That is the failing-job case
  below: tell the person, do not rerun it on your own.
- A resume asks YouTube nothing about what is already in the folder: before starting it records those ids (from the `[id]` in the
  file names) in yt-dlp's archive. yt-dlp itself writes nothing to that archive on `--skip-download` runs, so do not use the
  archive's size as progress: use `--status`.
- At the end it says how many videos had no captions in that language. A few is normal (shorts, streams, premieres have none: Vex
  stays at 337 of 368). If it is most of them, the language is wrong.

**Totals.** Never give a percentage or "N left" for a channel you did not count. The total comes from the site, not from memory:
`yt-dlp --flat-playlist --print id <channel url>/videos | wc -l` (add `/shorts`, `/streams` if they matter), and say that videos
without captions will not reach it. On 2026-11-04 a summary said "~462 videos, 80 %" with no count behind it.

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
