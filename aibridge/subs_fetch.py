#!/usr/bin/env python3
"""subs-fetch: download the subtitles of a whole YouTube channel/playlist with ONE yt-dlp process (2026-11-04).

  subs-fetch <channel-or-playlist-url> <dir> [--lang en-orig[,es]] [--pace fast|normal|slow] [--limit N]
  subs-fetch --all <parent-dir>          resume EVERY channel run before (the ones listed in <parent-dir>/channels.json)
  subs-fetch --status <parent-dir>       what is on disk per channel, how fast it grows, what runs now (counts the files: no JSON)

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
import argparse, fcntl, json, os, re, subprocess, sys, time

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


SLOTS = int(os.environ.get("SUBS_SLOTS", "3"))               # channels downloading at the same time from this address
COOLDOWN_MIN = float(os.environ.get("SUBS_COOLDOWN_MIN", "60"))   # how long ONE rate limit pauses every instance


def cooldown_file(directory):
    return os.path.join(os.path.dirname(os.path.abspath(directory)), ".subs-cooldown")


def cooldown_left(directory):
    """Seconds until the shared pause ends (0 = none). One instance hitting a rate limit pauses all of them: they share the address."""
    try:
        return max(0.0, float(open(cooldown_file(directory)).read().strip()) - time.time())
    except (OSError, ValueError):
        return 0.0


def start_cooldown(directory):
    with open(cooldown_file(directory), "w") as f:
        f.write(str(time.time() + COOLDOWN_MIN * 60))


def try_slot(directory, slots=None):
    """A non-blocking flock on one of N slot files; returns the open file (keep it open while downloading) or None."""
    parent = os.path.dirname(os.path.abspath(directory))
    for i in range(slots or SLOTS):
        f = open(os.path.join(parent, f".subs-slot-{i}"), "a")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except OSError:
            f.close()
    return None


def registered_lang(directory):
    parent, name = os.path.split(os.path.abspath(directory))
    try:
        return json.load(open(os.path.join(parent, "channels.json")))[name]["lang"]
    except (OSError, ValueError, KeyError):
        return None


def channel_lock(directory):
    """Exclusive non-blocking lock on the channel folder: a second job on the same channel (the old loop next to
    subs-fetch, two launches by mistake) is refused, because both write the same files and double the requests."""
    f = open(os.path.join(directory, ".subs.lock"), "a")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except OSError:
        f.close()
        return None


def is_running(directory):
    try:
        f = channel_lock(directory)
    except OSError:   # read-only view (a throwaway container looking at the volume): cannot tell, say idle
        return False
    if f is None:
        return True
    f.close()
    return False


def status(parent):
    """One line per registered channel, from the files themselves."""
    if not os.path.isdir(parent):
        print(f"subs-fetch: {parent} is not a folder")
        return 2
    try:
        reg = json.load(open(os.path.join(parent, "channels.json")))
    except (OSError, ValueError):
        reg = {}
    names = sorted(set(reg) | {d for d in os.listdir(parent) if d.endswith("_subs") and os.path.isdir(os.path.join(parent, d))})
    now = time.time()
    total = {"files": 0, "h": 0}
    for name in names:
        d = os.path.join(parent, name)
        srt = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".srt")] if os.path.isdir(d) else []
        times = [os.path.getmtime(f) for f in srt]
        r10 = sum(1 for t in times if now - t < 600)
        r60 = sum(1 for t in times if now - t < 3600)
        lang = reg.get(name, {}).get("lang", "?")
        running = "RUNNING" if os.path.isdir(d) and is_running(d) else "idle   "
        print(f"{name:28} {len(srt):5} files  {lang:8} {running} last 10 min {r10:3}  last hour {r60:4}")
        total["files"] += len(srt)
        total["h"] += r10 * 6
    left = cooldown_left(os.path.join(parent, "x"))
    print(f"total {total['files']} files on disk; about {total['h']} an hour at the last 10 minutes; "
          + (f"PAUSED by a rate limit for {left / 60:.0f} more min" if left else "no rate-limit pause"))
    return 0


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


def run_channel(url, directory, lang, pace, limit, set_lang=False):
    os.makedirs(directory, exist_ok=True)
    known_lang = registered_lang(directory)
    lang = lang or known_lang
    if not lang:
        print("subs-fetch: say the language of the channel's own captions: --lang en-orig, ru-orig, es-orig, ... (no default: a wrong one "
              "downloads almost nothing, and a new folder has none registered yet)", flush=True)
        return 2
    if known_lang and known_lang != lang and not set_lang:
        print(f"subs-fetch: this folder is registered as {known_lang} and you asked for {lang}. A wrong language downloads almost nothing "
              f"(2026-11-05: a Russian channel ran for an hour with en-orig). Use --lang {known_lang}, or --set-lang to change the registry on purpose.", flush=True)
        return 2
    left = cooldown_left(directory)
    lock = channel_lock(directory)
    if lock is None:
        print(f"subs-fetch: another job is already downloading into {directory}. Not starting a second one on the same channel.", flush=True)
        return 3
    if left:
        lock.close()
        print(f"subs-fetch: paused for another {left / 60:.0f} min (a rate limit was hit; every instance waits). Nothing started.", flush=True)
        return 75
    slot = try_slot(directory)
    waited = False
    while slot is None:   # more channels than slots: wait for one, never hit the site with all of them at once
        if not waited:
            print(f"subs-fetch: {SLOTS} channels already downloading from this address; waiting for a free slot", flush=True)
            waited = True
        time.sleep(5)
        if cooldown_left(directory):
            lock.close()
            return 75
        slot = try_slot(directory)
    remember_channel(directory, url, lang)
    known = seed_archive(directory)
    before = sum(1 for f in os.listdir(directory) if f.endswith(".srt"))
    print(f"subs-fetch: {before} subtitles already in {directory}, {known} ids in the archive; pace {pace}, lang {lang}", flush=True)
    proc = subprocess.Popen(build_cmd(url, directory, lang, pace, limit), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    limited, last_check, no_caps = False, time.time(), 0
    for line in proc.stdout:
        if LIMITED.search(line):
            limited = True
            start_cooldown(directory)
            proc.terminate()
            break
        if time.time() - last_check > 5:   # another instance may have hit the limit: stop too, same address
            last_check = time.time()
            if cooldown_left(directory):
                limited = True
                proc.terminate()
                break
        if "There are no subtitles for the requested languages" in line:
            no_caps += 1
        if line.startswith(("[info] Writing video subtitles", "[download] Finished", "ERROR")):
            print(line.rstrip()[:160], flush=True)
    proc.wait()
    slot.close()
    lock.close()
    after = sum(1 for f in os.listdir(directory) if f.endswith(".srt"))
    print(f"subs-fetch: {after - before} new subtitles, {after} in total in {directory}", flush=True)
    if no_caps:
        print(f"subs-fetch: {no_caps} videos have no {lang} captions (shorts, streams and premieres often have none; if it is MOST of "
              f"them, check the language is the channel's own)", flush=True)
    if limited:
        print("subs-fetch: RATE LIMITED by the site. Stopped, nothing retried. Tell the person; rerun the same command later "
              "(the archive resumes it). Waiting is usually right: each extra request can lengthen the block.", flush=True)
        return 75
    return 0 if proc.returncode in (0, 101) else proc.returncode   # 101 = --max-downloads reached


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("url", nargs="?"); ap.add_argument("directory", nargs="?")
    ap.add_argument("--all", metavar="PARENT", help="resume every channel listed in PARENT/channels.json, one after the other")
    ap.add_argument("--lang", default=None); ap.add_argument("--pace", choices=PACE, default="normal")
    ap.add_argument("--limit", type=int, help="at most N new subtitles per channel in this run")
    ap.add_argument("--status", metavar="PARENT", help="print what is on disk per channel and what runs now")
    ap.add_argument("--set-lang", action="store_true", help="change the language registered for this folder")
    a = ap.parse_args(argv)
    if a.status:
        return status(a.status)
    if a.all:
        try:
            reg = json.load(open(os.path.join(a.all, "channels.json")))
        except (OSError, ValueError):
            print(f"subs-fetch: no {a.all}/channels.json yet: run it once per channel with a URL and a folder", flush=True)
            return 2
        worst = 0
        for name, cfg in sorted(reg.items()):
            print(f"== {name}", flush=True)
            code = run_channel(cfg["url"], os.path.join(a.all, name), cfg.get("lang") or a.lang, a.pace, a.limit)
            if code == 75:
                return 75   # one rate limit stops the whole round: the other channels share the same address
            worst = worst or code
        return worst
    if not (a.url and a.directory):
        ap.error("give a URL and a folder, or --all PARENT")
    return run_channel(a.url, a.directory, a.lang, a.pace, a.limit, a.set_lang)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
