#!/usr/bin/env python3
"""subs-fetch: download the subtitles of a whole YouTube channel/playlist with ONE yt-dlp process (2026-11-04).

  subs-fetch <channel-or-playlist-url> <dir> [--lang en-orig[,es]] [--pace fast|normal|slow] [--limit N]
  subs-fetch --all <parent-dir>          resume EVERY channel run before (the ones listed in <parent-dir>/channels.json)

Why it exists. On 2026-11-04 hernik wrote its own downloader: one yt-dlp process per video, `--write-auto-subs` and then
`--write-subs` as two full extractions, 8-20 s of sleep per video plus 120 s every 10 videos, and the whole channel listing
again at every start. Measured from the files' timestamps it produced about 90 subtitles an hour, against 250-340 an hour on
the earlier days when yt-dlp ran natively over a channel. A native run over 3 videos took 16.5 s, about 5 s a video.

What this does instead: one process over the whole channel, the videos already in <dir> are put in yt-dlp's archive first
(by the `[id]` in their file names, so a resume asks YouTube nothing about them), one language by default (`en-orig` is the
channel's original-language caption; `en.*` fetched two files per video), and a pace profile for the sleeps. On a rate limit
(HTTP 429 or "confirm you're not a bot") it STOPS and exits 75 without retrying: waiting is the person's decision, every extra
request can lengthen the block.
"""
import argparse, json, os, re, subprocess, sys

PACE = {"fast": (0.5, 1), "normal": (1, 2), "slow": (2, 5)}   # --sleep-requests, --sleep-subtitles (seconds)
LIMITED = re.compile(r"HTTP Error 429|Too Many Requests|confirm you.re not a bot|rate-limited", re.I)
ID_IN_NAME = re.compile(r"\[([A-Za-z0-9_-]{11})\][^\[\]]*$")


def seed_archive(directory):
    """Write `youtube <id>` for every subtitle already in the directory; return how many ids the archive holds."""
    archive = os.path.join(directory, ".archive.txt")
    have = set()
    if os.path.exists(archive):
        have = {l.strip() for l in open(archive) if l.strip()}
    for name in os.listdir(directory):
        m = ID_IN_NAME.search(name) if name.endswith((".srt", ".vtt")) else None
        if m:
            have.add("youtube " + m.group(1))
    with open(archive, "w") as f:
        f.write("\n".join(sorted(have)) + ("\n" if have else ""))
    return len(have)


def remember_channel(directory, url, lang):
    """Record the channel next to its folder, so `--all` can resume it later without anyone naming it again."""
    parent, name = os.path.split(os.path.abspath(directory))
    path = os.path.join(parent, "channels.json")
    try:
        reg = json.load(open(path))
    except (OSError, ValueError):
        reg = {}
    if reg.get(name) != {"url": url, "lang": lang}:
        reg[name] = {"url": url, "lang": lang}
        with open(path, "w") as f:
            json.dump(reg, f, indent=1, sort_keys=True)


def build_cmd(url, directory, lang, pace, limit=None):
    rq, sub = PACE[pace]
    cmd = ["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", lang, "--convert-subs", "srt",
           "--no-overwrites", "--download-archive", os.path.join(directory, ".archive.txt"), "--ignore-no-formats-error",
           "--sleep-requests", str(rq), "--sleep-subtitles", str(sub), "--no-warnings", "--newline",
           "-o", os.path.join(directory, "%(title).150B [%(id)s].%(ext)s")]
    if limit:
        cmd += ["--max-downloads", str(limit)]
    if re.search(r"youtube\.com/(@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)/?$", url):
        url = url.rstrip("/") + "/videos"   # a bare channel URL lists its tabs; the videos tab is the uploads
    return cmd + [url]


def run_channel(url, directory, lang, pace, limit):
    os.makedirs(directory, exist_ok=True)
    remember_channel(directory, url, lang)
    known = seed_archive(directory)
    before = sum(1 for f in os.listdir(directory) if f.endswith(".srt"))
    print(f"subs-fetch: {before} subtitles already in {directory}, {known} ids in the archive; pace {pace}, lang {lang}", flush=True)
    proc = subprocess.Popen(build_cmd(url, directory, lang, pace, limit), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    limited = False
    for line in proc.stdout:
        if LIMITED.search(line):
            limited = True
            proc.terminate()
            break
        if line.startswith(("[info] Writing video subtitles", "[download] Finished", "ERROR")):
            print(line.rstrip()[:160], flush=True)
    proc.wait()
    after = sum(1 for f in os.listdir(directory) if f.endswith(".srt"))
    print(f"subs-fetch: {after - before} new subtitles, {after} in total in {directory}", flush=True)
    if limited:
        print("subs-fetch: RATE LIMITED by the site. Stopped, nothing retried. Tell the person; rerun the same command later "
              "(the archive resumes it). Waiting is usually right: each extra request can lengthen the block.", flush=True)
        return 75
    return 0 if proc.returncode in (0, 101) else proc.returncode   # 101 = --max-downloads reached


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("url", nargs="?"); ap.add_argument("directory", nargs="?")
    ap.add_argument("--all", metavar="PARENT", help="resume every channel listed in PARENT/channels.json, one after the other")
    ap.add_argument("--lang", default="en-orig"); ap.add_argument("--pace", choices=PACE, default="normal")
    ap.add_argument("--limit", type=int, help="at most N new subtitles per channel in this run")
    a = ap.parse_args(argv)
    if a.all:
        try:
            reg = json.load(open(os.path.join(a.all, "channels.json")))
        except (OSError, ValueError):
            print(f"subs-fetch: no {a.all}/channels.json yet: run it once per channel with a URL and a folder", flush=True)
            return 2
        worst = 0
        for name, cfg in sorted(reg.items()):
            print(f"== {name}", flush=True)
            code = run_channel(cfg["url"], os.path.join(a.all, name), cfg.get("lang", a.lang), a.pace, a.limit)
            if code == 75:
                return 75   # one rate limit stops the whole round: the other channels share the same address
            worst = worst or code
        return worst
    if not (a.url and a.directory):
        ap.error("give a URL and a folder, or --all PARENT")
    return run_channel(a.url, a.directory, a.lang, a.pace, a.limit)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
