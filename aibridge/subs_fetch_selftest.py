#!/usr/bin/env python3
"""subs_fetch.py offline: VTT to SRT, what is skipped, shared pause/slots/locks, language rules, progress and a full run against a fake yt-dlp.
No network: python3 subs_fetch_selftest.py"""
import contextlib, io, json, os, sys, tempfile, time
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
    # status shows the files, the language and 'done'
    code, out = quiet(s.status, parent)
    check("status: files, language, idle, done", "run_subs" in out and "3 files" in out.replace("    3 files", "3 files") and "en-orig" in out and "idle" in out and "done" in out)
    lk = s.channel_lock(ch)
    check("status marks a running channel", "RUNNING" in quiet(s.status, parent)[1])
    lk.close()

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
    check("--all with no registry says so and exits 2", quiet(s.main, ["--all", tempfile.gettempdir() + "/none-" + str(os.getpid())])[0], 2)

# ---- soft block: "no captions" findings are held back until believable (2026-11-05: 4,250 false ones in a fast run) ----
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
    check("soft block: everything pauses like for a rate limit", s.cooldown_left(ch) > 0, True)

for text, want in (("ERROR: HTTP Error 429: Too Many Requests", True), ("Sign in to confirm you're not a bot", True), ("[info] Writing video subtitles to: x.srt", False)):
    check(f"rate-limit detector: {text[:34]!r}", bool(s.LIMITED.search(text)), want)
print("\n".join(fails) or "subs_fetch_selftest: all ok")
sys.exit(1 if fails else 0)
