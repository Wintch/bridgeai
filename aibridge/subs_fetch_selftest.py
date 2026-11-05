#!/usr/bin/env python3
"""subs_fetch.py: archive seeding, command shape and rate-limit detection. No network: python3 subs_fetch_selftest.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subs_fetch as s

fails = []
def check(name, got, want):
    print(("ok   " if got == want else "FAIL ") + name)
    if got != want: fails.append(f"{name}: got {got!r}, want {want!r}")

with tempfile.TemporaryDirectory() as d:
    for n in ("Title one [AAAAAAAAAAA].en-orig.srt", "Otro [Bb_-Cc12345].es.srt", "no id.srt", "video [CCCCCCCCCCC].mp4"):
        open(os.path.join(d, n), "w").close()
    open(os.path.join(d, ".archive.txt"), "w").write("youtube ZZZZZZZZZZZ\n")
    check("seed: ids from subtitle names plus the existing archive, nothing from a video file", s.seed_archive(d), 3)
    check("seed is idempotent", s.seed_archive(d), 3)
    check("archive content", sorted(open(os.path.join(d, ".archive.txt")).read().split("\n"))[1:],
          ["youtube AAAAAAAAAAA", "youtube Bb_-Cc12345", "youtube ZZZZZZZZZZZ"])
    c = s.build_cmd("https://www.youtube.com/@Chan", d, "en-orig", "normal")
    check("one process, both caption kinds, one language", (c[0], "--write-subs" in c, "--write-auto-subs" in c, c[c.index("--sub-langs") + 1]),
          ("yt-dlp", True, True, "en-orig"))
    check("bare channel URL gets /videos", c[-1], "https://www.youtube.com/@Chan/videos")
    check("a playlist URL is left alone", s.build_cmd("https://www.youtube.com/playlist?list=PLx", d, "en", "fast")[-1], "https://www.youtube.com/playlist?list=PLx")
    check("resumes through the archive and never overwrites", ("--download-archive" in c, "--no-overwrites" in c), (True, True))
    check("pace slow sleeps more than fast", (s.PACE["slow"][1] > s.PACE["fast"][1]), True)
    check("limit becomes --max-downloads", s.build_cmd("u", d, "en", "fast", 5)[-3:-1], ["--max-downloads", "5"])
with tempfile.TemporaryDirectory() as parent:   # channels.json: remembered once, resumable by --all
    ch = os.path.join(parent, "chan_subs")
    os.makedirs(ch)
    s.remember_channel(ch, "https://www.youtube.com/@Chan", "en-orig")
    s.remember_channel(ch, "https://www.youtube.com/@Chan", "en-orig")
    import json
    check("channel remembered under its folder name, idempotent", json.load(open(os.path.join(parent, "channels.json"))),
          {"chan_subs": {"url": "https://www.youtube.com/@Chan", "lang": "en-orig"}})
    ran = []
    real = s.run_channel
    s.run_channel = lambda url, d, lang, pace, limit: ran.append((os.path.basename(d), lang)) or 0
    json.dump({"b_subs": {"url": "u2", "lang": "ru-orig"}, "a_subs": {"url": "u1", "lang": "en-orig"}}, open(os.path.join(parent, "channels.json"), "w"))
    check("--all runs every channel in order with its own language", (s.main(["--all", parent]), ran), (0, [("a_subs", "en-orig"), ("b_subs", "ru-orig")]))
    ran.clear()
    s.run_channel = lambda url, d, lang, pace, limit: ran.append(os.path.basename(d)) or (75 if url == "u1" else 0)
    check("a rate limit on one channel stops the round (same address)", (s.main(["--all", parent]), ran), (75, ["a_subs"]))
    s.run_channel = real
    check("--all with no registry says so and exits 2", s.main(["--all", tempfile.gettempdir() + "/none-" + str(os.getpid())]), 2)
with tempfile.TemporaryDirectory() as parent:   # shared pause and slots
    ch = os.path.join(parent, "x_subs")
    check("no cooldown at first", s.cooldown_left(ch), 0.0)
    s.start_cooldown(ch)
    check("one rate limit pauses every channel of the folder", 3000 < s.cooldown_left(os.path.join(parent, "other_subs")) <= 3600, True)
    check("a started instance refuses to run during the pause", s.run_channel("u", ch, "en", "normal", None), 75)
    os.unlink(s.cooldown_file(ch))
    a1 = s.try_slot(ch, 2); a2 = s.try_slot(ch, 2); a3 = s.try_slot(ch, 2)
    check("two slots: the third instance gets none", (a1 is not None, a2 is not None, a3), (True, True, None))
    a1.close()
    check("a slot is free again once its holder ends", s.try_slot(ch, 2) is not None, True)
for text, want in (("ERROR: HTTP Error 429: Too Many Requests", True), ("Sign in to confirm you're not a bot", True),
                   ("[info] Writing video subtitles to: x.srt", False)):
    check(f"rate-limit detector: {text[:34]!r}", bool(s.LIMITED.search(text)), want)
print("\n".join(fails) or "subs_fetch_selftest: all ok")
sys.exit(1 if fails else 0)
