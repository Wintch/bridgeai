---
name: downloads
description: "Download videos (YouTube and ~1800 sites), audio, or torrents for the person, all at once and in the background, with a guard on disk space: `gateway bajar`."
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

Full films and series by torrent: the person decides; mention once, briefly, that a torrent shares from the home
connection while it downloads (copyright notices go to the home IP). Prefer legal sources when they exist.

## Subtitles or transcripts only

`gateway bajar` cannot do this: it takes only `--calidad`, `--paralelo` and `--audio`, and any other flag (`--write-sub`,
`--skip-download`) makes it exit with code 2 and download nothing. Do not retry it with other flags (on 2026-11-04 it was
tried four times, each failing the same way). Run `yt-dlp` directly, in the background with `notify_on_complete=true`, one
folder per channel under `/workdir/descargas/`:

`yt-dlp --skip-download --write-subs --write-auto-subs --sub-langs "es.*,en.*" --convert-subs srt --no-overwrites
--download-archive /workdir/descargas/<channel>/.archive.txt --sleep-requests 1 --sleep-subtitles 3
-o "/workdir/descargas/<channel>/%(upload_date)s - %(title)s.%(ext)s" <channel url>`

- **Resuming:** run the same command again. `--no-overwrites` keeps the files already there and the archive file lists the
  videos already processed, so YouTube is not asked about them again. Check that the archive file grows; if it does not,
  say so instead of assuming the resume works.
- **One job per channel.** Before starting, look at the running jobs (`process` list, or `ps` for `yt-dlp`): two jobs on the
  same channel write the same files and double the requests that make a site rate-limit. If one already runs, report it and
  do not start another.
- Count the files (`ls | wc -l`) before saying how far it got; never say "downloaded" from a command that has not finished.
- **Never give a percentage of a channel you did not count.** The total comes from the site, not from memory:
  `yt-dlp --flat-playlist --print id <channel url>/videos | wc -l` (and `/shorts`, `/streams` if they matter). On 2026-11-04
  a summary said "~462 videos, 80 %" with no count behind it, while the same job had processed lists of 138 and 324 items.

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

A whole YouTube channel (thousands of videos) is not one `gateway bajar` item: do it in slices (for yt-dlp,
`--playlist-start` / `--playlist-end`) and report after each slice; `--skip-download` runs write no `archive.txt`, so a
resume needs the slice number, not the archive.
