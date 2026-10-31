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

Several requests in one turn (trailers for a list of films): put every item in **one** `gateway bajar` call. Find the
URLs first with parallel searches if needed, but you can also pass `buscar:` items and let it search.

Full films and series by torrent: the person decides; mention once, briefly, that a torrent shares from the home
connection while it downloads (copyright notices go to the home IP). Prefer legal sources when they exist.
