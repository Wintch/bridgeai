#!/usr/bin/env python3
"""subs_fetch.py offline: VTT to SRT, what is skipped, shared pause/slots/locks, language rules, progress and a full run against a fake yt-dlp.
No network: python3 subs_fetch_selftest.py"""
import atexit, contextlib, io, json, os, shutil, sys, tempfile, time, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subs_fetch as s

fails = []
def check(name, got, want=True):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(f"{name}: got {got!r}, want {want!r}")
def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        r = fn(*a, **k)
    return r, buf.getvalue()

# ---- VTT to SRT ----
VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.500 align:start position:0%
Hello &amp; welcome<00:00:02.000><c> back</c>

NOTE a comment

00:03.500 --> 00:05.000
second line
with two rows

00:06.000 --> 00:07.000
<c></c>
"""
srt = s.vtt_to_srt(VTT)
check("vtt: cues numbered, comma milliseconds, tags and entities cleaned",
      srt.startswith("1\n00:00:01,000 --> 00:00:03,500\nHello & welcome back\n") and "2\n00:00:03,500 --> 00:00:05,000\nsecond line\nwith two rows" in srt)
check("vtt: header, NOTE and empty cues are dropped", "WEBVTT" not in srt and "NOTE" not in srt and srt.count("-->") == 2)
check("vtt: mm:ss.mmm gets an hour", "00:00:03,500" in srt)

# ---- what is skipped ----
check("ids: on disk and known-no-captions are skipped, order kept, duplicates once, limit applied",
      s.todo_ids(["a" * 11, "b" * 11, "c" * 11, "b" * 11, "d" * 11], {"a" * 11}, {"c" * 11}), ["b" * 11, "d" * 11])
check("ids: limit", s.todo_ids(["a" * 11, "b" * 11, "c" * 11], set(), set(), 2), ["a" * 11, "b" * 11])
check("listing url: bare channel gets /videos, playlist untouched",
      (s.listing_url("https://www.youtube.com/@Chan"), s.listing_url("https://www.youtube.com/playlist?list=PLx")),
      ("https://www.youtube.com/@Chan/videos", "https://www.youtube.com/playlist?list=PLx"))
cmd = s.build_cmd("/d/.todo.txt", "/d", "ru-orig", "normal")
check("command: one process over a list, one language, light client, no ffmpeg conversion, no per-request storm",
      (cmd[cmd.index("-a") + 1], cmd[cmd.index("--sub-langs") + 1], "player_client=ios" in " ".join(cmd), "--convert-subs" in cmd,
       cmd[cmd.index("--sleep-requests") + 1], cmd[cmd.index("--sleep-subtitles") + 1]), ("/d/.todo.txt", "ru-orig", True, False, "1", "2.5"))
check("pace: slow waits more than normal, normal more than fast",
      s.PACE["gentle"][1] > s.PACE["slow"][1] > s.PACE["normal"][1] > s.PACE["fast"][1] and s.PACE["gentle"][0] > s.PACE["slow"][0] > s.PACE["normal"][0] > s.PACE["fast"][0])

with tempfile.TemporaryDirectory() as d:
    for n in ("Title one [AAAAAAAAAAA].en-orig.srt", "Otro [Bb_-Cc12345].es.vtt", "no id.srt", "video [CCCCCCCCCCC].mp4"):
        open(os.path.join(d, n), "w").close()
    check("have_ids: ids from subtitle names only (not a video file, not a name without id)", s.have_ids(d), {"AAAAAAAAAAA", "Bb_-Cc12345"})
    s.add_nocap(d, "NNNNNNNNNNN", "en-orig")
    with open(os.path.join(d, ".nocaps.tsv"), "a") as f:
        f.write(f"OOOOOOOOOOO\t{time.time() - 20 * 86400:.0f}\ten-orig\nPPPPPPPPPPP\t{time.time():.0f}\tru-orig\n")
    check("nocaps: recent same-language remembered; older than 14 days and other languages are asked again", s.load_nocaps(d, "en-orig"), {"NNNNNNNNNNN"})

# ---- shared pause, slots, locks ----
with tempfile.TemporaryDirectory() as parent:
    ch = os.path.join(parent, "x_subs"); os.makedirs(ch)
    check("no cooldown at first", s.cooldown_left(ch), 0.0)
    s.start_cooldown(ch)
    check("one rate limit pauses every channel of the folder", s.COOLDOWN_MIN * 60 - 600 < s.cooldown_left(os.path.join(parent, "other_subs")) <= s.COOLDOWN_MIN * 60)
    check("a started instance refuses to run during the pause", quiet(s.run_channel, "u", ch, "en-orig", "normal", None)[0], 75)
    os.unlink(s.cooldown_file(ch))
    a1, a2, a3 = s.try_slot(ch, 2), s.try_slot(ch, 2), s.try_slot(ch, 2)
    check("two slots: the third instance gets none", (a1 is not None, a2 is not None, a3), (True, True, None))
    a1.close()
    check("a slot is free again once its holder ends", s.try_slot(ch, 2) is not None)
    l1 = s.channel_lock(ch)
    check("a second job on the same channel is refused (exit 3)", quiet(s.run_channel, "u", ch, "en-orig", "normal", None)[0], 3)
    check("is_running sees the lock", s.is_running(ch))
    l1.close()
    check("lock free after the job", not s.is_running(ch))
    check("a NEW folder without --lang is refused: no silent default", quiet(s.run_channel, "u", os.path.join(parent, "new_subs"), None, "normal", None)[0], 2)
    s.remember_channel(ch, "https://www.youtube.com/@Ru", "ru-orig")
    check("a registered folder refuses another language", quiet(s.run_channel, "u", ch, "en-orig", "normal", None)[0], 2)
    check("registered language is read back", s.registered_lang(ch), "ru-orig")

# ---- a whole run against a fake yt-dlp ----
class FakeProc:
    def __init__(self, cmd, **kw):
        self.cmd, self.returncode = cmd, 0
        d = os.path.dirname(cmd[cmd.index("-o") + 1])
        ids = [l.strip().split("=")[-1] for l in open(cmd[cmd.index("-a") + 1])]
        lines = []
        for i, vid in enumerate(ids):
            lines.append(f"[youtube] Extracting URL: https://www.youtube.com/watch?v={vid}\n")
            if i == 1:
                lines.append("[info] There are no subtitles for the requested languages\n")
            else:
                path = os.path.join(d, f"Video {vid} [{vid}].en-orig.vtt")
                open(path, "w").write("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n")
                lines.append(f"[info] Writing video subtitles to: {path}\n")
                lines.append("[download] 100% of 1KiB in 00:00:00\n")
        if len(ids) > 3:
            lines.append("ERROR: [youtube] zzzzzzzzzzz: Video unavailable\n")
        self.stdout = iter(lines)
    def wait(self): return 0
    def terminate(self): pass

with tempfile.TemporaryDirectory() as parent:
    ch = os.path.join(parent, "run_subs")
    ids = ["A" * 11, "B" * 11, "C" * 11, "D" * 11]
    real_list_ids = s.list_ids
    s.list_ids = lambda url, d, recent=None, sleep=0.3: (ids, False)
    real_popen = s.subprocess.Popen
    s.subprocess.Popen = FakeProc
    os.makedirs(ch)
    open(os.path.join(ch, "Old [AAAAAAAAAAA].en-orig.srt"), "w").write("x")
    code, out = quiet(s.run_channel, "https://www.youtube.com/@Run", ch, "en-orig", "fast", None)
    s.subprocess.Popen = real_popen
    check("run: exit 0", code, 0)
    check("run: the video already on disk is not asked for again",
          "A" * 11 not in open(os.path.join(ch, ".todo.txt")).read() and open(os.path.join(ch, ".todo.txt")).read().count("watch?v=") == 3)
    srts = sorted(f for f in os.listdir(ch) if f.endswith(".srt"))
    check("run: subtitles converted to .srt in Python and no .vtt left", len(srts) == 3 and not [f for f in os.listdir(ch) if f.endswith(".vtt")])
    check("run: the video without captions is remembered", s.load_nocaps(ch, "en-orig"), {"C" * 11})
    prog = s.read_progress(ch)
    check("run: progress has total, to do, looked at, written, no captions, errors",
          (prog["all"], prog["todo"], prog["processed"], prog["written"], prog["nocaps"], prog["errors"], prog["finished"]), (4, 3, 3, 2, 1, 0, True))
    check("run: the channel is registered for --all", json.load(open(os.path.join(parent, "channels.json")))["run_subs"]["lang"], "en-orig")
    check("run: the summary says what was done", "2 new subtitles" in out and "1 with no en-orig captions" in out, True)
    # second run: everything is on disk or known: nothing to do, yt-dlp not even started
    s.subprocess.Popen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("yt-dlp must not start when nothing is left"))
    code, out = quiet(s.run_channel, "https://www.youtube.com/@Run", ch, "en-orig", "fast", None)
    s.subprocess.Popen = real_popen
    check("second run: nothing left, nothing asked of the site", code == 0 and "0 to do" in out)
    check("run: the end of the run says how complete the channel is (no listing cached by the fake: not listed yet)",
          "run_subs: NOT LISTED YET" in out)
    # status: complete only from the files against the channel listing, never from the last run's counters
    code, out = quiet(s.status, parent)
    check("status: never listed -> not complete, total unknown", "NOT LISTED YET (total unknown)" in out and "total: 0 of 1 channels COMPLETE" in out)
    json.dump({"url": "u", "ts": time.time() - 2 * 86400, "ids": ids}, open(os.path.join(ch, ".ids.cache"), "w"))
    code, out = quiet(s.status, parent)
    check("status: 3 on disk + 1 without captions of 4 listed -> COMPLETE, with the numbers and the listing age",
          ("COMPLETE" in out, "3 of     4 subtitled, 1 no captions, 0 unavailable" in out, "listed 2 d ago" in out, "total: 1 of 1 channels COMPLETE" in out),
          (True, True, True, True))
    json.dump({"url": "u", "ts": time.time(), "ids": ["E" * 11] + ids}, open(os.path.join(ch, ".ids.cache"), "w"))
    s.write_progress(ch, dict(s.read_progress(ch), finished=True, todo=0))   # the last run "finished": must not hide what is missing
    code, out = quiet(s.status, parent)
    check("status: a listed video with no file -> INCOMPLETE: 1 missing, even when the last run finished",
          ("INCOMPLETE: 1 missing" in out, "1 not complete with 1 videos missing" in out, "Not complete: say so" in out), (True, True, True))
    lk = s.channel_lock(ch)
    check("status marks a running channel", "RUNNING" in quiet(s.status, parent)[1])
    lk.close()
    # the brief status (what --status prints by default): the same total line, who runs, the channels with the most missing, not 16 lines
    code, out = quiet(s.status, parent, False)
    check("brief status: no per-channel line, the total line is the same", ("subtitled," in out, "1 not complete with 1 videos missing" in out), (False, True))
    check("brief status: names the incomplete channel with its number and points to --full",
          ("Not complete, most missing first: run_subs (1 missing)" in out, "--status" in out and "--full" in out), (True, True))
    lk = s.channel_lock(ch)
    check("brief status keeps the word RUNNING and names who runs", "RUNNING now: run_subs" in quiet(s.status, parent, False)[1])
    lk.close()
    check("brief status says nothing about RUNNING when nothing runs", "RUNNING" not in quiet(s.status, parent, False)[1])
    with tempfile.TemporaryDirectory() as many:
        reg = {}
        for i, miss in enumerate((5, 900, 40, 7000, 2, 310, 61, 88)):
            d = os.path.join(many, f"c{i}_subs"); os.makedirs(d)
            vids = [f"{i}{j:010d}"[:11] for j in range(miss + 1)]
            json.dump({"url": "u", "ts": time.time(), "ids": vids}, open(os.path.join(d, ".ids.cache"), "w"))
            open(os.path.join(d, f"{vids[0]}.srt"), "w").write("x")
            reg[f"c{i}_subs"] = {"url": "u", "lang": "en-orig"}
        json.dump(reg, open(os.path.join(many, "channels.json"), "w"))
        out = quiet(s.status, many, False)[1]
        line = next(l for l in out.splitlines() if l.startswith("Not complete, most missing first"))
        check("brief status: the six channels with the most missing, biggest first, and how many more", 
              (line.split("(")[0].endswith("c3_subs "), line.index("c3_subs") < line.index("c1_subs") < line.index("c5_subs"), "and 2 more" in line, "c4_subs" not in line),
              (True, True, True, True))
        check("brief status: far shorter than the full one", (len(out.splitlines()), len(quiet(s.status, many, True)[1].splitlines())), (3, 10))
    rc, out = quiet(s.main, ["--status", parent])
    check("--status on the command line is the brief one, --full is the long one", ("Not complete, most missing first" in out, "subtitled," in quiet(s.main, ["--status", parent, "--full"])[1]), (True, True))
    # speed and ETA over RUNNING time: a suspension or a long rest between two progress writes is not counted
    real_time = s.time.time
    clock = [1_000_000.0]
    s.time.time = lambda: clock[0]
    try:
        pr = {"pid": 1, "started": clock[0], "processed": 0, "todo": 100, "finished": False}
        s.write_progress(ch, pr)
        clock[0] += 30; s.write_progress(ch, pr)            # 30 s of work
        clock[0] += 8 * 3600; s.write_progress(ch, pr)      # the machine slept 8 h
        clock[0] += 20; s.write_progress(ch, pr)            # 20 s more
        check("progress: running time counts the short gaps only, not an 8 h suspension", round(pr["active"]), 50)
        clock[0] += 599; s.write_progress(ch, pr)
        check("progress: a gap just under the limit still counts", round(pr["active"]), 50 + 599)
    finally:
        s.time.time = real_time
    pr = {"pid": 1, "started": time.time() - 3 * 3600, "processed": 50, "todo": 150, "active": 600.0, "finished": False}
    s.write_progress(ch, pr)
    lk = s.channel_lock(ch)
    out = quiet(s.status, parent)[1]
    check("status: the ETA is from running time (50 videos in 600 s: 100 left is ~0.3 h), not from 3 h of clock",
          ("~0.3 h running" in out, "~6.0 h" in out), (True, False))
    lk.close()
    old_style = {"pid": 1, "started": time.time() - 3600, "processed": 50, "todo": 150, "finished": False}   # a progress file from before: wall clock
    json.dump(dict(old_style, updated=time.time()), open(os.path.join(ch, ".subs-progress.json"), "w"))
    lk = s.channel_lock(ch)
    check("status: a progress file without running time falls back to the clock", "h running" in quiet(s.status, parent)[1])
    lk.close()
    # unavailable videos (private, members only) are remembered and count as checked, like the caption-less ones
    class UnavProc(FakeProc):
        def __init__(self, cmd, **kw):
            self.cmd, self.returncode = cmd, 0
            vids = [l.strip().split("=")[-1] for l in open(cmd[cmd.index("-a") + 1])]
            self.stdout = iter(l for v in vids for l in (f"[youtube] Extracting URL: https://www.youtube.com/watch?v={v}\n",
                                                          f"ERROR: [youtube] {v}: Private video. Sign in if you've been granted access\n"))
    s.list_ids = lambda url, d, recent=None, sleep=0.3: (["E" * 11] + ids, False)
    s.subprocess.Popen = UnavProc
    code, out = quiet(s.run_channel, "https://www.youtube.com/@Run", ch, "en-orig", "fast", None)
    s.subprocess.Popen = real_popen
    check("unavailable: the private video is written down", (code, s.load_unavailable(ch)), (0, {"E" * 11}))
    check("unavailable: the channel is now COMPLETE and the run says so", "run_subs: COMPLETE" in out and "1 unavailable" in out)
    check("unavailable: not asked again on the next run", s.todo_ids(["E" * 11] + ids, s.have_ids(ch), s.load_nocaps(ch, "en-orig") | s.load_unavailable(ch)), [])
    check("unavailable: forgotten after 14 days", s.load_unavailable(ch, now=time.time() + 15 * 86400), set())
    many = ["%011d" % i for i in range(30)]
    s.list_ids = lambda url, d, recent=None, sleep=0.3: (many, False)
    s.subprocess.Popen = UnavProc
    code, out = quiet(s.run_channel, "https://www.youtube.com/@Run", ch, "en-orig", "fast", None)
    s.subprocess.Popen = real_popen
    check("unavailable: 30 of 30 'private' is the site, not the videos: nothing written down", (s.load_unavailable(ch), "not written down" in out), ({"E" * 11}, True))
    for line, want in (("ERROR: [youtube] abcdefghijk: Join this channel to get access to members-only content", "abcdefghijk"),
                       ("ERROR: [youtube] abcdefghijk: Video unavailable. This video has been removed by the uploader", "abcdefghijk"),
                       ("ERROR: [youtube] abcdefghijk: Unable to download webpage: HTTP Error 403", None)):
        m = s.UNAVAILABLE.search(line)
        check(f"unavailable detector: {line[30:70]!r}", m.group(1) if m else None, want)

s.list_ids = real_list_ids   # the full-run test above replaced it
# ---- listing: recent mode merges new ids in front of the cached full list ----
with tempfile.TemporaryDirectory() as d:
    real_run = s.subprocess.run
    class R:
        def __init__(self, out): self.stdout, self.stderr = out, ""
    calls = []
    s.subprocess.run = lambda args, **k: calls.append(args) or R("\n".join(["N" * 11, "A" * 11, "B" * 11]))
    json.dump({"url": "U", "ts": time.time() - 100, "ids": ["A" * 11, "B" * 11, "C" * 11]}, open(os.path.join(d, ".ids.cache"), "w"))
    got, lim = s.list_ids("U", d, 40)
    merged = json.load(open(os.path.join(d, ".ids.cache")))
    s.subprocess.run = real_run
    check("the listing waits as long as the pace says between requests (default 0.3 s only when no pace is given)",
          (calls[0][calls[0].index("--sleep-requests") + 1], s.run_channel.__code__.co_names.count("PACE") > 0), ("0.3", True))
    check("recent listing asks for the newest 40 only", "--playlist-end" in calls[0] and calls[0][calls[0].index("--playlist-end") + 1] == "40")
    check("the new id goes in front of the cached full list, no duplicates", merged["ids"] == ["N" * 11, "A" * 11, "B" * 11, "C" * 11])
    check("the cache time is untouched so the full listing is still due", abs(merged["ts"] - (time.time() - 100)) < 5)
    s.subprocess.run = lambda args, **k: (_ for _ in ()).throw(AssertionError("a fresh cache must not list again"))
    check("without recent, a fresh cache is used and the site is not asked", s.list_ids("U", d)[0] == merged["ids"])
    s.subprocess.run = real_run

# ---- listing a whole channel: one at a time, a rest between, an old listing is used when it is not your turn ----
import fcntl
class Out:
    def __init__(self, out): self.stdout, self.stderr = out, ""
real_run, real_sleep = s.subprocess.run, s.time.sleep
with tempfile.TemporaryDirectory() as parent:
    a_dir, b_dir, c_dir = (os.path.join(parent, n) for n in ("a_subs", "b_subs", "c_subs"))
    for x in (a_dir, b_dir, c_dir): os.makedirs(x)
    t1 = s.try_list_turn(a_dir)
    check("listing turn: the first channel gets it", t1 is not None)
    check("listing turn: a second channel cannot list while the first does", s.try_list_turn(b_dir), None)
    s.end_list_turn(a_dir, t1)
    check("listing turn: the rest after a listing keeps the next one waiting", s.try_list_turn(b_dir), None)
    t2 = s.try_list_turn(b_dir, now=time.time() + s.LIST_GAP_S + 1)
    check("listing turn: after the rest it is free again", t2 is not None)
    t2.close()
    s.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("the site must not be asked when it is not this channel's turn"))
    sleeps = []
    s.time.sleep = lambda x: sleeps.append(x)
    try:
        old = ["A" * 11, "B" * 11]
        json.dump({"url": "U", "ts": time.time() - 99 * 3600, "ids": old}, open(os.path.join(b_dir, ".ids.cache"), "w"))
        (got, lim), out = quiet(s.list_ids, "U", b_dir)
        check("stale listing and not its turn: the old listing is used, the site is not asked, no waiting",
              (got, lim, "older listing" in out, sleeps), (old, False, True, []))
        s.start_cooldown(c_dir, 30)   # a pause starts while a never-listed channel waits for its turn
        try:
            quiet(s.list_ids, "U", c_dir)
            res = "returned"
        except s.ListingPaused:
            res = "ListingPaused"
        check("never listed and not its turn: waits, and stops when a pause starts (nothing asked)", (res, len(sleeps) >= 1), ("ListingPaused", True))
    finally:
        s.subprocess.run, s.time.sleep = real_run, real_sleep
with tempfile.TemporaryDirectory() as parent:
    d1, d2 = os.path.join(parent, "a_subs"), os.path.join(parent, "b_subs")
    os.makedirs(d1); os.makedirs(d2)
    s.subprocess.run = lambda args, **k: Out("\n".join(["X" * 11, "Y" * 11]))
    try:
        got, lim = s.list_ids("U1", d1)
        check("a whole listing with a free turn goes to the site and is cached",
              (got, os.path.isfile(os.path.join(d1, ".ids.cache"))), (["X" * 11, "Y" * 11], True))
        check("...and the turn is free again, but the rest between listings has started",
              (os.path.isfile(os.path.join(parent, ".subs-list-last")), s.try_list_turn(d2)), (True, None))
    finally:
        s.subprocess.run = real_run
with tempfile.TemporaryDirectory() as parent:
    e = os.path.join(parent, "e_subs"); os.makedirs(e)
    s.subprocess.run = lambda args, **k: (_ for _ in ()).throw(RuntimeError("yt-dlp died"))
    try:
        try: s.list_ids("U3", e)
        except RuntimeError: pass
    finally:
        s.subprocess.run = real_run
    lk = open(os.path.join(parent, ".subs-list-lock"), "a")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB); free = True
    except OSError:
        free = False
    lk.close()
    check("a listing that crashes still frees the turn and starts the rest", (free, os.path.isfile(os.path.join(parent, ".subs-list-last"))), (True, True))

with tempfile.TemporaryDirectory() as parent:
    ch = os.path.join(parent, "z_subs")
    real_list = s.list_ids
    def paused(*a, **k): raise s.ListingPaused()
    s.list_ids = paused
    try:
        code, out = quiet(s.run_channel, "https://www.youtube.com/@Z", ch, "en-orig", "gentle", None)
        lk = s.channel_lock(ch)
        check("a channel stopped by a pause while it waited to be listed: exit 75, the resting line, its lock and slot freed",
              (code, "resting for" in out, lk is not None, s.try_slot(ch) is not None), (75, True, True, True))
    finally:
        s.list_ids = real_list

# ---- --all ----
class FakeChild:
    def __init__(self, code): self.code = code
    def wait(self): return self.code
with tempfile.TemporaryDirectory() as parent:
    started = []
    real = s.spawn_channel
    json.dump({"b_subs": {"url": "u2", "lang": "ru-orig"}, "a_subs": {"url": "u1", "lang": "en-orig"}}, open(os.path.join(parent, "channels.json"), "w"))
    def fake(code_for):
        def f(url, d, lang, pace, limit, new=False):
            started.append((os.path.basename(d), lang, pace, limit, new))
            return FakeChild(code_for.get(url, 0))
        return f
    s.spawn_channel = fake({})
    check("--all starts EVERY channel at once, each with its own language, in two waves: newest 30 of each first, then the whole backlog",
          (quiet(s.main, ["--all", parent, "--pace", "fast"])[0], started),
          (0, [("a_subs", "en-orig", "fast", 30, False), ("b_subs", "ru-orig", "fast", 30, False),
               ("a_subs", "en-orig", "fast", None, False), ("b_subs", "ru-orig", "fast", None, False)]))
    started.clear()
    quiet(s.main, ["--all", parent, "--new"])
    check("--all --new is ONE wave of the recent ones only", started, [("a_subs", "en-orig", s.DEFAULT_PACE, None, True), ("b_subs", "ru-orig", s.DEFAULT_PACE, None, True)])
    started.clear(); s.spawn_channel = fake({"u1": 75})
    check("a rate limit in the first wave makes the round exit 75 and the second wave never starts", (quiet(s.main, ["--all", parent])[0], len(started)), (75, 2))
    started.clear(); s.spawn_channel = fake({"u1": 3})
    check("a channel already running elsewhere (3) does not fail the round", quiet(s.main, ["--all", parent])[0], 0)
    s.spawn_channel = fake({"u2": 1})
    check("a real failure is reported", quiet(s.main, ["--all", parent])[0], 1)
    # the round moved to an always-on worker (/workdir/.worker-jobs names it): --all on the stack is refused, --force overrides
    wj = os.path.join(parent, "worker-jobs")
    open(wj, "w").write("jobnight\nsubs-nuevos\n")
    saved = (s.WORKER_JOBS, s.DEFAULT_PARENT)
    s.WORKER_JOBS, s.DEFAULT_PARENT = wj, parent
    try:
        started.clear(); s.spawn_channel = fake({})
        code, out = quiet(s.main, ["--all", parent, "--new"])
        check("worker-owned: --all is refused on the stack (exit 4), nothing started, the answer says where it runs and what to tell",
              (code, started, "always-on" in out and "--status" in out and "--force" in out), (s.WORKER_OWNED_RC, [], True))
        check("worker-owned: --backlog is refused too", quiet(s.main, ["--all", parent, "--backlog", "50"])[0], s.WORKER_OWNED_RC)
        check("worker-owned: --status still answers", quiet(s.main, ["--status", parent])[0] != s.WORKER_OWNED_RC, True)
        started.clear()
        check("worker-owned: --force runs the round here", (quiet(s.main, ["--all", parent, "--new", "--force"])[0], len(started)), (0, 2))
        check("worker-owned: another parent folder is not the worker's", s.worker_owned(os.path.join(parent, "a_subs")), False)
        open(wj, "w").write("jobnight\n")
        started.clear()
        check("a .worker-jobs without the subs round: --all runs as before", (quiet(s.main, ["--all", parent, "--new"])[0], len(started)), (0, 2))
        os.unlink(wj)
        check("no .worker-jobs: not worker-owned", s.worker_owned(parent), False)
    finally:
        s.WORKER_JOBS, s.DEFAULT_PARENT = saved
    s.spawn_channel = real
    seen = []
    real_popen = s.subprocess.Popen
    s.subprocess.Popen = lambda cmd, **k: seen.append(cmd) or None
    s.spawn_channel("U", "/d/x_subs", "ru-orig", "slow", 5)
    s.subprocess.Popen = real_popen
    check("the real spawn builds a command with the channel, folder, language, pace and limit",
          seen[0][2:] == ["U", "/d/x_subs", "--pace", "slow", "--lang", "ru-orig", "--limit", "5"])
    seen.clear(); s.subprocess.Popen = lambda cmd, **k: seen.append(cmd) or None
    s.spawn_channel("U", "/d/x_subs", "ru-orig", "normal", None, True)
    s.subprocess.Popen = real_popen
    check("--new is passed to the child", seen[0][-1] == "--new")
    # --backlog: only the channels that are not complete, the budget shared out among them
    for name, listed, on_disk in (("a_subs", ["A" * 11, "B" * 11], ["A" * 11, "B" * 11]), ("b_subs", ["C" * 11, "D" * 11], ["C" * 11])):
        os.makedirs(os.path.join(parent, name), exist_ok=True)
        json.dump({"url": "u", "ts": time.time(), "ids": listed}, open(os.path.join(parent, name, ".ids.cache"), "w"))
        for v in on_disk:
            open(os.path.join(parent, name, f"V [{v}].x.srt"), "w").write("x")
    started.clear(); s.spawn_channel = fake({})
    code, out = quiet(s.main, ["--all", parent, "--backlog", "300"])
    check("--backlog starts only the incomplete channel, with the whole budget (one channel)",
          (code, started, "1 channels not complete (1 videos missing)" in out), (0, [("b_subs", "ru-orig", s.DEFAULT_PACE, 300, False)], True))
    started.clear()
    quiet(s.main, ["--all", parent, "--backlog", "10"])
    check("--backlog never gives a channel less than the minimum slice", started[0][3], s.BACKLOG_MIN_PER_CHANNEL)
    open(os.path.join(parent, "b_subs", f"V [{'D' * 11}].x.srt"), "w").write("x")
    started.clear()
    code, out = quiet(s.main, ["--all", parent, "--backlog", "300"])
    check("--backlog with every channel complete starts nothing and says so", (code, started, "all 2 channels COMPLETE" in out), (0, [], True))
    started.clear(); s.spawn_channel = fake({"u1": 75})
    os.remove(os.path.join(parent, "a_subs", f"V [{'B' * 11}].x.srt"))
    check("--backlog passes a rate limit on (75)", quiet(s.main, ["--all", parent, "--backlog", "300"])[0], 75)
    s.spawn_channel = real
    for bad in (["--all", parent, "--backlog", "5", "--new"], ["--all", parent, "--backlog", "5", "--limit", "3"], ["--backlog", "5"]):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                s.main(bad); got = "no error"
        except SystemExit as e:
            got = e.code
        check(f"--backlog refused with {bad[2:] if bad[0] == '--all' else bad}", got, 2)
    check("--all with no registry says so and exits 2", quiet(s.main, ["--all", tempfile.gettempdir() + "/none-" + str(os.getpid())])[0], 2)

# ---- soft block: "no captions" findings are held back until believable (4,250 false ones in a fast run) ----
g = s.NocapGuard()
for i in range(10):
    g.seen()
    if i % 3 == 1: g.nocap(f"V{i:010d}")
check("guard: a short healthy run holds its findings and writes them at the end", (g.degraded(), len(g.ripe()), len(g.rest())), (False, 0, 3))
g = s.NocapGuard()
for i in range(100):
    g.seen()
    if i % 3 == 1: g.nocap(f"V{i:010d}")
    ripe_now = g.ripe()
check("guard: one in three (a real channel with shorts and streams) is never degraded and ripens behind the window", not g.degraded() and len(g.held) <= 11, True)
g = s.NocapGuard()
for i in range(25):
    g.seen()
    if i % 4 != 0: g.nocap(f"W{i:010d}")
check("guard: three in four caption-less over 20+ videos is a soft block", g.degraded(), True)
check("guard: a degraded window writes nothing down", (g.ripe(), g.rest()), ([], []))

class SoftBlockProc:
    """Fake yt-dlp whose site answers every video without captions."""
    def __init__(self, cmd, **kw):
        self.returncode = 0
        ids = [l.strip().split("=")[-1] for l in open(cmd[cmd.index("-a") + 1])]
        self.stdout = iter(l for vid in ids for l in (f"[youtube] Extracting URL: https://www.youtube.com/watch?v={vid}\n",
                                                       "[info] There are no subtitles for the requested languages\n"))
    def wait(self): return 0
    def terminate(self): pass

with tempfile.TemporaryDirectory() as parent:
    ch = os.path.join(parent, "soft_subs")
    os.makedirs(ch)
    many = ["%011d" % i for i in range(60)]
    real_list_ids, real_popen = s.list_ids, s.subprocess.Popen
    s.list_ids = lambda url, d, recent=None, sleep=0.3: (many, False)
    s.subprocess.Popen = SoftBlockProc
    code, out = quiet(s.run_channel, "https://www.youtube.com/@Soft", ch, "en-orig", "fast", None)
    s.list_ids, s.subprocess.Popen = real_list_ids, real_popen
    check("soft block: the job ends with 75 and says so", (code, "SOFT BLOCK" in out), (75, True))
    check("soft block: no video is written down as caption-less", s.load_nocaps(ch, "en-orig"), set())
    check("soft block: everything pauses, for the longer soft-block time", s.cooldown_left(ch) > (s.COOLDOWN_MIN + 60) * 60, True)
    s.start_cooldown(ch)
    check("a later, milder pause never shortens the soft block's", s.cooldown_left(ch) > (s.COOLDOWN_MIN + 60) * 60, True)

# ---- the canary: the tail of a backlog is often videos that never had captions; that is not a soft block ----
def tail_run(verdict, n_have=30, n_todo=28):
    """A channel with n_have videos already subtitled and a backlog tail of n_todo that answer without captions."""
    parent = tempfile.mkdtemp(); atexit.register(shutil.rmtree, parent, True)
    ch = os.path.join(parent, "tail_subs"); os.makedirs(ch)
    have = ["H%010d" % i for i in range(n_have)]; tail = ["T%010d" % i for i in range(n_todo)]
    for v in have:
        open(os.path.join(ch, f"V [{v}].ru-orig.srt"), "w").write("x")
    asked = []
    saved = s.list_ids, s.subprocess.Popen, s.canary_check
    s.list_ids = lambda url, d, recent=None, sleep=0.3: (have + tail, False)
    s.subprocess.Popen = SoftBlockProc
    s.canary_check = lambda lang, cands, pace: asked.append(set(cands)) or verdict
    try:
        code, out = quiet(s.run_channel, "https://www.youtube.com/@Tail", ch, "ru-orig", "normal", None)
    finally:
        s.list_ids, s.subprocess.Popen, s.canary_check = saved
    return code, out, s.load_nocaps(ch, "ru-orig"), s.cooldown_left(ch), asked, set(have), set(tail)

code, out, nocaps, pause, asked, have, tail = tail_run("captions")
check("canary delivers: a caption-less tail is genuine, the run ends 0 with no pause", (code, pause), (0, 0))
check("canary delivers: every tail video is written down as caption-less", nocaps, tail)
check("canary delivers: the canary is chosen among the videos that HAVE subtitles", bool(asked) and all(a == have for a in asked), True)
check("canary delivers: the run says why it went on", "the site is not holding captions back" in out and "SOFT BLOCK" not in out, True)
code, out, nocaps, pause, asked, have, tail = tail_run("captions", n_todo=300)
check(f"a long genuine tail is checked at most {s.CANARY_MAX} times, then treated as a soft block (still moving: findings written first)",
      (len(asked), code, len(nocaps) > 100), (s.CANARY_MAX, 75, True))
code, out, nocaps, pause, asked, have, tail = tail_run("none")
check("canary gets nothing either: SOFT BLOCK, exit 75, nothing written, the long pause",
      (code, "SOFT BLOCK" in out and "HAVE subtitles" in out, nocaps, pause > (s.COOLDOWN_MIN + 60) * 60), (75, True, set(), True))
code, out, nocaps, pause, asked, have, tail = tail_run("limited")
check("canary refused by the site: RATE LIMITED, exit 75, the 1-hour pause, nothing written",
      (code, "RATE LIMITED" in out, nocaps, 0 < pause <= s.COOLDOWN_MIN * 60), (75, True, set(), True))

class FakeRun:
    def __init__(self, deliver, out=""): self.deliver, self.out, self.cmds = deliver, out, []
    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        d = os.path.dirname(cmd[cmd.index("-o") + 1])
        for url in cmd:
            if "watch?v=" in url and self.deliver(url.split("=")[-1]):
                open(os.path.join(d, url.split("=")[-1] + ".ru-orig.vtt"), "w").write("WEBVTT\n")
        return types.SimpleNamespace(returncode=0, stdout=self.out, stderr="")
cands = {"H%010d" % i for i in range(10)}
real_run = s.subprocess.run
try:
    fr = FakeRun(lambda v: True); s.subprocess.run = fr
    check("canary_check: all delivered is 'captions'", s.canary_check("ru-orig", cands, "normal"), "captions")
    cmd = fr.cmds[0]
    check("canary_check: asks CANARY_N videos with subtitles, same language and client, skips the video", 
          (sum("watch?v=" in c for c in cmd), cmd[cmd.index("--sub-langs") + 1], "--skip-download" in cmd, f"youtube:player_client={s.CLIENT}" in cmd),
          (s.CANARY_N, "ru-orig", True, True))
    check("canary_check: the command tolerates a site that answers with pictures only (as the main download does)",
          ("--ignore-no-formats-error" in cmd, "--ignore-no-formats-error" in s.build_cmd("todo.txt", "d", "ru-orig", "normal")), (True, True))
    check("canary_check: leaves no temporary folder behind", os.path.exists(os.path.dirname(cmd[cmd.index("-o") + 1])), False)
    first = sorted(cands)[0]
    s.subprocess.run = FakeRun(lambda v: v != first)
    got = {s.canary_check("ru-orig", {first, "H0000000001", "H0000000002"}, "normal") for _ in range(3)}
    check("canary_check: one canary without captions is 'none' (a soft block)", got, {"none"})
    s.subprocess.run = FakeRun(lambda v: False, out="ERROR: HTTP Error 429: Too Many Requests")
    check("canary_check: a refusal is 'limited'", s.canary_check("ru-orig", cands, "normal"), "limited")
    s.subprocess.run = FakeRun(lambda v: True)
    check("canary_check: fewer videos with subtitles than CANARY_N is 'unknown', nothing asked",
          (s.canary_check("ru-orig", {"H0000000001"}, "normal"), s.subprocess.run.cmds), ("unknown", []))
finally:
    s.subprocess.run = real_run

for text, want in (("ERROR: HTTP Error 429: Too Many Requests", True), ("Sign in to confirm you're not a bot", True), ("[info] Writing video subtitles to: x.srt", False)):
    check(f"rate-limit detector: {text[:34]!r}", bool(s.LIMITED.search(text)), want)
# ---- the sweet-spot ledger: numbers only, one line per finished run, summed per day ----
with tempfile.TemporaryDirectory() as parent:
    ch = os.path.join(parent, "x_subs"); os.makedirs(ch)
    t0 = time.time()
    s.record_metrics(ch, "slow", {"started": t0 - 3600, "processed": 150, "errors": 0}, 120, "ok")
    s.record_metrics(ch, "slow", {"started": t0 - 1800, "processed": 20, "errors": 1}, 0, "limited")
    rows = [json.loads(l) for l in open(os.path.join(parent, ".subs-metrics.jsonl"))]
    check("metrics: one line per run, numbers and the outcome only (no channel name)",
          (len(rows), sorted(rows[0]), "x_subs" in open(os.path.join(parent, ".subs-metrics.jsonl")).read()),
          (2, ["errors", "new", "outcome", "pace", "secs", "slots", "ts", "videos"], False))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        s.pace_report(parent)
    line = buf.getvalue()
    check("pace report: the day shows pace, slots, videos, and the rate limit", ("pace slow" in line, "170 videos" in line, "1 rate limit" in line), (True, True, True))
    check("defaults: gentle pace, 2-hour rate-limit rest, soft block rests longer", (s.DEFAULT_PACE, s.COOLDOWN_MIN, s.SOFT_COOLDOWN_MIN > s.COOLDOWN_MIN), ("gentle", 120.0, True))

# ---- the command line: a folder alone, options after --all, one line while resting ----
with tempfile.TemporaryDirectory() as parent:
    ch = os.path.join(parent, "x_subs"); os.makedirs(ch)
    json.dump({"x_subs": {"url": "https://www.youtube.com/@X", "lang": "en-orig"}}, open(os.path.join(parent, "channels.json"), "w"))
    real_run_channel, real_spawn = s.run_channel, s.spawn_channel
    calls = []
    s.run_channel = lambda url, directory, lang, pace, limit, set_lang=False, new=False: calls.append((url, directory, lang, pace)) or 0
    try:
        rc, _ = quiet(s.main, [ch, "--pace", "slow"])
        check("a registered channel folder alone resumes it with its remembered url and language",
              (rc, calls[-1]), (0, ("https://www.youtube.com/@X", ch, "en-orig", "slow")))
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                s.main([os.path.join(parent, "nobody_subs"), "--pace", "slow"])
            code = 0
        except SystemExit as e:
            code = e.code
        check("an unregistered folder alone is refused with a working example", (code, "subs-fetch https://www.youtube.com/@Name" in err.getvalue() and "resume all" in err.getvalue()), (2, True))
    finally:
        s.run_channel = real_run_channel
    rc, out = quiet(s.main, ["--status", "--pace", "slow", parent])
    check("--status with an option before the folder still finds the folder", (rc, "x_subs" in out), (0, True))
    spawned = []
    s.spawn_channel = lambda *a, **k: spawned.append(a) or (_ for _ in ()).throw(AssertionError("spawned while resting"))
    try:
        s.start_cooldown(ch, 30)
        rc, out = quiet(s.main, ["--all", "--pace", "slow", parent])
        lines = [l for l in out.splitlines() if l.strip()]
        check("--all while resting: one line, exit 75, nothing spawned", (rc, len(lines), spawned), (75, 1, []))
        check("the resting line says nothing was requested and avoids the words of the failing-job alarm",
              ("no request was made" in out, "rate limit" in out.lower(), "429" in out), (True, False, False))
    finally:
        s.spawn_channel = real_spawn


print("\n".join(fails) or "subs_fetch_selftest: all ok")
sys.exit(1 if fails else 0)
