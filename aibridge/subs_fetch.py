#!/usr/bin/env python3
"""subs-fetch: download the subtitles of a whole YouTube channel/playlist, fast, without repeating work (2026-11-05).

  subs-fetch <channel-or-playlist-url> <dir> --lang <xx>-orig [--pace fast|normal|slow] [--limit N] [--set-lang]
  subs-fetch --all <parent-dir>          resume EVERY channel run before (the ones listed in <parent-dir>/channels.json)
  subs-fetch --status <parent-dir>       files on disk per channel, language, running or not, speed, what is left and the ETA
  subs-fetch --all <parent-dir> --new    only what appeared lately (newest 40 of each channel): cheap, for a schedule every few hours
  (--all without --new first brings the newest 30 of EVERY channel, then goes on with the whole backlog)

What it learned from measuring (2026-11-05, 4-core VM, one yt-dlp per video was the old way):
  * A video costs only about 0.8 s of CPU. The time went into yt-dlp's `--sleep-requests`, which pauses on EVERY request (3 per
    video with the default client): `normal` cost 6.6 s a video of which almost all was waiting. The `ios` client needs 2 requests
    a video and gave the same files on English, Russian and Spanish channels, so it is the default (SUBS_CLIENT to change it).
  * Videos with no captions in the language (2 of 5 on one channel; shorts, streams, premieres) were asked for again on every
    run, because yt-dlp writes nothing to its archive on `--skip-download`. They are now remembered (.nocaps.tsv, retried after
    14 days) and so are the videos already on disk: the channel is listed ONCE, the ids still missing go to yt-dlp as a list.
  * `--convert-subs srt` started an ffmpeg per file (+0.45 s CPU a video); the VTT to SRT conversion is done here in Python.
  * The speed that is safe is set by the REQUEST rate of the whole machine, not by the CPU: 1,100 to 1,300 videos an hour at 3
    requests each ran for hours without a block. Pace profiles and the 5 slots keep the whole machine just under that request rate.

Rules it enforces (see SKILL_downloads.md): one job per channel folder, at most SUBS_SLOTS (5) channels at once, ONE rate limit
pauses every instance for SUBS_COOLDOWN_MIN (60) minutes and ends the job with exit 75, a folder remembers its language.
"""
import argparse, fcntl, html, json, os, re, subprocess, sys, time

# (--sleep-requests, --sleep-subtitles) in seconds. With `ios`: 2 requests and 1 subtitle download a video, plus ~1.5 s of work.
PACE = {"fast": (0.5, 1.5), "normal": (1, 2.5), "slow": (2, 6)}
CLIENT = os.environ.get("SUBS_CLIENT", "ios")
# 5 channels at once. Measured 2026-11-05: a channel runs at ~300 videos an hour with `normal` and the `ios` client (2 requests each), so 5 channels
# make ~0.83 requests a second, BELOW the ~0.95 a second (6 channels, 3 requests each) that ran for hours on two days without a block. With 3 it was
# ~0.5, half of what is proven. Raise it only with a reason; ONE rate limit pauses everything for an hour.
SLOTS = int(os.environ.get("SUBS_SLOTS", "5"))
COOLDOWN_MIN = float(os.environ.get("SUBS_COOLDOWN_MIN", "60"))
NOCAPS_RETRY_DAYS = 14
IDS_CACHE_HOURS = 6
LIMITED = re.compile(r"HTTP Error 429|Too Many Requests|confirm you.re not a bot|rate-limited", re.I)
ID_IN_NAME = re.compile(r"\[([A-Za-z0-9_-]{11})\][^\[\]]*$")
EXTRACTING = re.compile(r"\[youtube\] Extracting URL: \S*[?&]v=([A-Za-z0-9_-]{11})")
WRITING = re.compile(r"\[info\] Writing video subtitles to: (.+)$")
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


# ---------- small pieces that are tested offline ----------
def vtt_to_srt(text):
    """WebVTT to SRT, tags removed. Same content ffmpeg gave, with no process started."""
    def stamp(t):
        parts = t.split(":")
        if len(parts) == 2:
            parts = ["00"] + parts
        h, m, s = parts
        return f"{int(h):02d}:{m}:{s.replace('.', ',')}"
    out, n = [], 0
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = block.split("\n")
        i = next((k for k, l in enumerate(lines) if "-->" in l), None)
        if i is None:
            continue   # the WEBVTT header, NOTE and STYLE blocks
        m = re.match(r"\s*(\S+)\s+-->\s+(\S+)", lines[i])
        body = [html.unescape(re.sub(r"<[^>]+>", "", l)).strip() for l in lines[i + 1:]]
        body = [b for b in body if b]
        if not m or not body:
            continue
        n += 1
        out.append(f"{n}\n{stamp(m.group(1))} --> {stamp(m.group(2))}\n" + "\n".join(body) + "\n")
    return "\n".join(out)


def convert_file(path):
    """Replace <name>.vtt with <name>.srt; on any failure the .vtt is left alone."""
    if not path.endswith(".vtt") or not os.path.exists(path):
        return
    try:
        srt = vtt_to_srt(open(path, encoding="utf-8", errors="replace").read())
        if srt.strip():
            with open(path[:-4] + ".srt", "w", encoding="utf-8") as f:
                f.write(srt)
            os.unlink(path)
    except OSError:
        pass


def have_ids(directory):
    return {m.group(1) for f in os.listdir(directory) if f.endswith((".srt", ".vtt")) for m in [ID_IN_NAME.search(f)] if m}


def load_nocaps(directory, lang, now=None):
    """Ids known to have no captions in this language, seen less than NOCAPS_RETRY_DAYS ago."""
    now = now or time.time()
    out = set()
    try:
        for line in open(os.path.join(directory, ".nocaps.tsv")):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3 and parts[2] == lang and VIDEO_ID.match(parts[0]) and now - float(parts[1]) < NOCAPS_RETRY_DAYS * 86400:
                out.add(parts[0])
    except (OSError, ValueError):
        pass
    return out


def add_nocap(directory, vid, lang):
    with open(os.path.join(directory, ".nocaps.tsv"), "a") as f:
        f.write(f"{vid}\t{time.time():.0f}\t{lang}\n")


class NocapGuard:
    """Holds "no captions" findings back until they are believable (2026-11-05 lesson).
    During the first backlog run, at ~1,500 videos an hour, 4,250 videos were written down as caption-less; asked again a few hours later
    at a calm pace, 22 of 24 sampled ones delivered their captions. The site did not refuse: it answered without captions (a soft block),
    and the answer looked like a genuine "no captions". A real channel has a few caption-less videos (shorts, streams), not half of them,
    so a finding is only written to .nocaps.tsv after WINDOW more videos went by and the share of caption-less ones in the window stayed
    under LIMIT. Above it the job stops and everything pauses like for a rate limit; the held findings are dropped and asked again."""
    WINDOW, MIN, LIMIT = 30, 20, 0.5

    def __init__(self):
        self.n, self.held = 0, []

    def seen(self):
        self.n += 1

    def nocap(self, vid):
        self.held.append((self.n, vid))

    def degraded(self):
        w = min(self.n, self.WINDOW)
        return w >= self.MIN and sum(1 for pos, _ in self.held if pos > self.n - self.WINDOW) / w > self.LIMIT

    def ripe(self):
        """Findings that left the window while it looked healthy: safe to write down."""
        if self.degraded():
            return []
        out = [v for pos, v in self.held if pos <= self.n - self.WINDOW]
        self.held = [(pos, v) for pos, v in self.held if pos > self.n - self.WINDOW]
        return out

    def rest(self):
        """At the end of a run: whatever is still held, unless the window looked degraded."""
        out = [] if self.degraded() else [v for _, v in self.held]
        self.held = []
        return out


def todo_ids(all_ids, have, nocaps, limit=None):
    seen, out = set(), []
    for i in all_ids:   # newest first, as listed; duplicates (a video in two tabs) once
        if i not in have and i not in nocaps and i not in seen:
            seen.add(i)
            out.append(i)
    return out[:limit] if limit else out


def listing_url(url):
    if re.search(r"youtube\.com/(@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)/?$", url):
        return url.rstrip("/") + "/videos"   # a bare channel URL lists its tabs; the videos tab is the uploads
    return url


def build_cmd(todo_file, directory, lang, pace):
    rq, sub = PACE[pace]
    return ["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", lang, "--no-overwrites",
            "--ignore-no-formats-error", "--sleep-requests", str(rq), "--sleep-subtitles", str(sub), "--no-warnings", "--newline",
            "--extractor-args", f"youtube:player_client={CLIENT}", "-o", os.path.join(directory, "%(title).150B [%(id)s].%(ext)s"),
            "-a", todo_file]


# ---------- shared state on disk: pause, slots, channel lock, registry, progress ----------
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


def channel_lock(directory):
    """Exclusive non-blocking lock on the channel folder: a second job on the same channel is refused."""
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


def registered_lang(directory):
    parent, name = os.path.split(os.path.abspath(directory))
    try:
        return json.load(open(os.path.join(parent, "channels.json")))[name]["lang"]
    except (OSError, ValueError, KeyError):
        return None


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


def write_progress(directory, prog):
    prog["updated"] = time.time()
    tmp = os.path.join(directory, ".subs-progress.json.tmp")
    try:
        with open(tmp, "w") as f:
            json.dump(prog, f)
        os.replace(tmp, os.path.join(directory, ".subs-progress.json"))
    except OSError:
        pass


def read_progress(directory):
    try:
        return json.load(open(os.path.join(directory, ".subs-progress.json")))
    except (OSError, ValueError):
        return None


FIRST_WAVE = 30   # --all without --new: the newest videos of every channel first
RECENT = 40   # --new looks at this many of the newest videos of each channel


def list_ids(url, directory, recent=None):
    """All video ids of the channel, newest first. Cached for IDS_CACHE_HOURS so a /parar and /retomar does not list it again.
    recent=N lists only the N newest (one request) and puts the ones the cache did not know in front of it: what --new needs."""
    cache = os.path.join(directory, ".ids.cache")
    try:
        c = json.load(open(cache))
    except (OSError, ValueError):
        c = {}
    fresh = c.get("url") == url and time.time() - c.get("ts", 0) < IDS_CACHE_HOURS * 3600 and c.get("ids")
    if fresh and not recent:
        return c["ids"], False
    args = ["yt-dlp", "--flat-playlist", "--print", "%(id)s", "--no-warnings", "--sleep-requests", "0.3"]
    if recent:
        args += ["--playlist-end", str(recent)]
    p = subprocess.run(args + [url], capture_output=True, text=True, timeout=3600)
    limited = bool(LIMITED.search(p.stdout + p.stderr))
    ids = [l.strip() for l in p.stdout.splitlines() if VIDEO_ID.match(l.strip())]
    if ids and not limited:
        if recent and c.get("url") == url and c.get("ids"):
            merged = ids + [i for i in c["ids"] if i not in set(ids)]   # new ones first; the old full list behind them
            with open(cache, "w") as f:
                json.dump({"url": url, "ts": c.get("ts", 0), "ids": merged}, f)   # ts untouched: a full listing is still due
        elif not recent:
            with open(cache, "w") as f:
                json.dump({"url": url, "ts": time.time(), "ids": ids}, f)
    return ids, limited


# ---------- the work ----------
def run_channel(url, directory, lang, pace, limit, set_lang=False, new=False):
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
    lock = channel_lock(directory)
    if lock is None:
        print(f"subs-fetch: another job is already downloading into {directory}. Not starting a second one on the same channel.", flush=True)
        return 3
    left = cooldown_left(directory)
    if left:
        lock.close()
        print(f"subs-fetch: paused for another {left / 60:.0f} min (a rate limit was hit; every instance waits). Nothing started.", flush=True)
        return 75
    slot, waited = try_slot(directory), False
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
    srt_before = sum(1 for f in os.listdir(directory) if f.endswith(".srt"))
    prog = {"pid": os.getpid(), "started": time.time(), "lang": lang, "pace": pace, "client": CLIENT, "all": 0, "todo": 0,
            "processed": 0, "written": 0, "nocaps": 0, "errors": 0, "finished": False}
    write_progress(directory, prog)
    ids, limited = list_ids(listing_url(url), directory, RECENT if new else None)
    if not ids:
        slot.close(); lock.close()
        print("subs-fetch: could not list the channel" + (" (RATE LIMITED)" if limited else "") + ". Nothing done.", flush=True)
        if limited:
            start_cooldown(directory)
            return 75
        return 1
    have = have_ids(directory)
    nocaps = load_nocaps(directory, lang)
    todo = todo_ids(ids, have, nocaps, limit)
    prog.update(all=len(ids), todo=len(todo), have=len(have & set(ids)), known_nocaps=len(nocaps & set(ids)))
    write_progress(directory, prog)
    print(f"subs-fetch: {len(ids)} videos in the channel, {len(have & set(ids))} already on disk, {len(nocaps & set(ids))} known to have no "
          f"{lang} captions, {len(todo)} to do; pace {pace}, client {CLIENT}", flush=True)
    code, no_caps_now, soft_blocked = 0, 0, False
    guard = NocapGuard()
    if todo:
        todo_file = os.path.join(directory, ".todo.txt")
        with open(todo_file, "w") as f:
            f.write("\n".join("https://www.youtube.com/watch?v=" + i for i in todo) + "\n")
        proc = subprocess.Popen(build_cmd(todo_file, directory, lang, pace), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        current, pending, last_check, last_write = None, None, time.time(), 0.0
        for line in proc.stdout:
            line = line.rstrip("\n")
            if LIMITED.search(line):
                limited = True
                start_cooldown(directory)
                proc.terminate()
                break
            m = EXTRACTING.search(line)
            if m:
                if pending:
                    convert_file(pending); pending = None
                current = m.group(1)
                prog["processed"] += 1
                guard.seen()
            elif WRITING.search(line):
                pending = WRITING.search(line).group(1).strip()
                prog["written"] += 1
            elif "There are no subtitles for the requested languages" in line and current:
                guard.nocap(current)
                prog["nocaps"] += 1
                no_caps_now += 1
            elif line.startswith("ERROR"):
                prog["errors"] += 1
                if prog["errors"] <= 5:
                    print(line[:160], flush=True)
            for vid in guard.ripe():
                add_nocap(directory, vid, lang)
            if guard.degraded():   # the site answers without captions: a soft block, not a channel without captions
                soft_blocked = True
                start_cooldown(directory)
                proc.terminate()
                break
            now = time.time()
            if now - last_write > 5:
                last_write = now
                write_progress(directory, prog)
            if now - last_check > 5:   # another instance may have hit the limit: stop too, same address
                last_check = now
                if cooldown_left(directory):
                    limited = True
                    proc.terminate()
                    break
        proc.wait()
        if pending:
            convert_file(pending)
        code = proc.returncode
    for f in os.listdir(directory):   # anything left from an interrupted run
        if f.endswith(".vtt"):
            convert_file(os.path.join(directory, f))
    if not limited and not soft_blocked:
        for vid in guard.rest():
            add_nocap(directory, vid, lang)
    prog["finished"] = not (limited or soft_blocked)
    write_progress(directory, prog)
    slot.close()
    lock.close()
    after = sum(1 for f in os.listdir(directory) if f.endswith(".srt"))
    print(f"subs-fetch: {after - srt_before} new subtitles, {after} in total in {directory}; {prog['processed']} videos looked at, "
          f"{no_caps_now} with no {lang} captions (remembered, not asked again for {NOCAPS_RETRY_DAYS} days), {prog['errors']} errors", flush=True)
    if prog["errors"] and prog["errors"] * 5 > max(prog["processed"], 1):
        print("subs-fetch: MANY errors (more than 1 in 5): do not keep going blindly, look at the first lines above.", flush=True)
    if soft_blocked:
        print(f"subs-fetch: SOFT BLOCK: more than {int(NocapGuard.LIMIT * 100)} % of the last {NocapGuard.WINDOW} videos answered with no captions. "
              f"That is the site holding captions back, not a channel without them. Nothing of the last {NocapGuard.WINDOW} was written down; "
              f"everything pauses {COOLDOWN_MIN:.0f} minutes. Rerun later.", flush=True)
        return 75
    if limited:
        print("subs-fetch: RATE LIMITED by the site. Stopped, nothing retried. Tell the person; rerun the same command later "
              "(what is on disk is skipped). Waiting is usually right: each extra request can lengthen the block.", flush=True)
        return 75
    return 0 if code in (0, 101) else code


def status(parent):
    """One line per registered channel, from the files themselves, with the speed and what is left."""
    if not os.path.isdir(parent):
        print(f"subs-fetch: {parent} is not a folder")
        return 2
    try:
        reg = json.load(open(os.path.join(parent, "channels.json")))
    except (OSError, ValueError):
        reg = {}
    names = sorted(set(reg) | {d for d in os.listdir(parent) if d.endswith("_subs") and os.path.isdir(os.path.join(parent, d))})
    now = time.time()
    files_total, per_hour, left_total = 0, 0, 0
    for name in names:
        d = os.path.join(parent, name)
        srt = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".srt")] if os.path.isdir(d) else []
        times = [os.path.getmtime(f) for f in srt]
        r10 = sum(1 for t in times if now - t < 600)
        r60 = sum(1 for t in times if now - t < 3600)
        lang = reg.get(name, {}).get("lang", "?")
        running = os.path.isdir(d) and is_running(d)
        prog = read_progress(d) if os.path.isdir(d) else None
        extra = ""
        if prog:
            remaining = max(0, prog.get("todo", 0) - prog.get("processed", 0))
            if running and prog.get("processed", 0) >= 5:
                rate = prog["processed"] / max(60.0, prog["updated"] - prog["started"]) * 3600   # videos looked at an hour
                extra = f"  left {remaining} of {prog['todo']}" + (f", ~{remaining / rate:.1f} h" if rate else "")
                left_total += remaining
            elif running:
                extra = f"  left {remaining} of {prog['todo']}"
                left_total += remaining
            elif not prog.get("finished") and remaining:
                extra = f"  STOPPED with {remaining} of {prog['todo']} left"
            else:
                extra = "  done"
            if prog.get("nocaps"):
                extra += f", {prog['nocaps']} without captions"
        print(f"{name:28} {len(srt):5} files  {lang:8} {'RUNNING' if running else 'idle   '} last 10 min {r10:3}  last hour {r60:4}{extra}")
        files_total += len(srt)
        per_hour += r10 * 6 if running else 0
    left = cooldown_left(os.path.join(parent, "x"))
    print(f"total {files_total} files on disk; about {per_hour} an hour at the last 10 minutes"
          + (f"; {left_total} videos left in the running channels" if left_total else "") + "; "
          + (f"PAUSED by a rate limit for {left / 60:.0f} more min" if left else "no rate-limit pause"))
    return 0


def spawn_channel(url, directory, lang, pace, limit, new=False):
    cmd = [sys.executable, os.path.abspath(__file__), url, directory, "--pace", pace] + (["--lang", lang] if lang else []) \
          + (["--limit", str(limit)] if limit else []) + (["--new"] if new else [])
    return subprocess.Popen(cmd)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("url", nargs="?"); ap.add_argument("directory", nargs="?")
    ap.add_argument("--all", metavar="PARENT", help="resume every channel listed in PARENT/channels.json, one after the other")
    ap.add_argument("--status", metavar="PARENT", help="print what is on disk per channel and what runs now")
    ap.add_argument("--lang", default=None); ap.add_argument("--pace", choices=PACE, default="normal")
    ap.add_argument("--limit", type=int, help="at most N new videos per channel in this run")
    ap.add_argument("--set-lang", action="store_true", help="change the language registered for this folder")
    ap.add_argument("--new", action="store_true", help="only the newest %d videos of each channel (cheap; for a schedule)" % RECENT)
    a = ap.parse_args(argv)
    if a.status:
        return status(a.status)
    if a.all:
        try:
            reg = json.load(open(os.path.join(a.all, "channels.json")))
        except (OSError, ValueError):
            print(f"subs-fetch: no {a.all}/channels.json yet: run it once per channel with a URL and a folder", flush=True)
            return 2
        # One process per channel, all started at once: the slots (SUBS_SLOTS) decide how many download, the rest wait. Running them
        # one after the other would use a single slot and a third of the speed.
        def wave(limit):
            procs = [spawn_channel(cfg["url"], os.path.join(a.all, name), cfg.get("lang") or a.lang, a.pace, limit, a.new)
                     for name, cfg in sorted(reg.items())]
            return [p.wait() for p in procs]
        # Without --new or --limit: first the newest FIRST_WAVE videos of every channel (so a late-starting channel is not left behind a
        # 4,000-video one for hours), then the whole backlog.
        codes = wave(a.limit or (FIRST_WAVE if not a.new else None))
        if 75 not in codes and not a.new and not a.limit:
            codes += wave(None)
        if 75 in codes:
            return 75   # one rate limit stops the whole round: the other channels share the same address
        return next((c for c in codes if c not in (0, 3)), 0)   # 3 = that channel already runs elsewhere: fine
    if not (a.url and a.directory):
        ap.error("give a URL and a folder, or --all PARENT, or --status PARENT")
    return run_channel(a.url, a.directory, a.lang, a.pace, a.limit, a.set_lang, a.new)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
