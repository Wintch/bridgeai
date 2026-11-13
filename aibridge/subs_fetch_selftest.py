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
      s.PACE["slow"][1] > s.PACE["normal"][1] > s.PACE["fast"][1] and s.PACE["slow"][0] > s.PACE["normal"][0] > s.PACE["fast"][0])

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
    check("one rate limit pauses every channel of the folder", 3000 < s.cooldown_left(os.path.join(parent, "other_subs")) <= 3600)
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
    s.list_ids = lambda url, d, recent=None: (ids, False)
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
    # unavailable videos (private, members only) are remembered and count as checked, like the caption-less ones
    class UnavProc(FakeProc):
        def __init__(self, cmd, **kw):
            self.cmd, self.returncode = cmd, 0
            vids = [l.strip().split("=")[-1] for l in open(cmd[cmd.index("-a") + 1])]
            self.stdout = iter(l for v in vids for l in (f"[youtube] Extracting URL: https://www.youtube.com/watch?v={v}\n",
                                                          f"ERROR: [youtube] {v}: Private video. Sign in if you've been granted access\n"))
    s.list_ids = lambda url, d, recent=None: (["E" * 11] + ids, False)
    s.subprocess.Popen = UnavProc
    code, out = quiet(s.run_channel, "https://www.youtube.com/@Run", ch, "en-orig", "fast", None)
    s.subprocess.Popen = real_popen
    check("unavailable: the private video is written down", (code, s.load_unavailable(ch)), (0, {"E" * 11}))
    check("unavailable: the channel is now COMPLETE and the run says so", "run_subs: COMPLETE" in out and "1 unavailable" in out)
    check("unavailable: not asked again on the next run", s.todo_ids(["E" * 11] + ids, s.have_ids(ch), s.load_nocaps(ch, "en-orig") | s.load_unavailable(ch)), [])
    check("unavailable: forgotten after 14 days", s.load_unavailable(ch, now=time.time() + 15 * 86400), set())
    many = ["%011d" % i for i in range(30)]
    s.list_ids = lambda url, d, recent=None: (many, False)
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
    check("recent listing asks for the newest 40 only", "--playlist-end" in calls[0] and calls[0][calls[0].index("--playlist-end") + 1] == "40")
    check("the new id goes in front of the cached full list, no duplicates", merged["ids"] == ["N" * 11, "A" * 11, "B" * 11, "C" * 11])
    check("the cache time is untouched so the full listing is still due", abs(merged["ts"] - (time.time() - 100)) < 5)
    s.subprocess.run = lambda args, **k: (_ for _ in ()).throw(AssertionError("a fresh cache must not list again"))
    check("without recent, a fresh cache is used and the site is not asked", s.list_ids("U", d)[0] == merged["ids"])
    s.subprocess.run = real_run

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
    check("--all --new is ONE wave of the recent ones only", started, [("a_subs", "en-orig", "normal", None, True), ("b_subs", "ru-orig", "normal", None, True)])
    started.clear(); s.spawn_channel = fake({"u1": 75})
    check("a rate limit in the first wave makes the round exit 75 and the second wave never starts", (quiet(s.main, ["--all", parent])[0], len(started)), (75, 2))
    started.clear(); s.spawn_channel = fake({"u1": 3})
    check("a channel already running elsewhere (3) does not fail the round", quiet(s.main, ["--all", parent])[0], 0)
    s.spawn_channel = fake({"u2": 1})
    check("a real failure is reported", quiet(s.main, ["--all", parent])[0], 1)
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
          (code, started, "1 channels not complete (1 videos missing)" in out), (0, [("b_subs", "ru-orig", "normal", 300, False)], True))
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
    s.list_ids = lambda url, d, recent=None: (many, False)
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
    s.list_ids = lambda url, d, recent=None: (have + tail, False)
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
print("\n".join(fails) or "subs_fetch_selftest: all ok")
sys.exit(1 if fails else 0)
