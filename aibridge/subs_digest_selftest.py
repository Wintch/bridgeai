#!/usr/bin/env python3
"""subs_digest.py: what it picks, what it cleans, what it never repeats. No network: python3 subs_digest_selftest.py"""
import io, json, os, sys, tempfile, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subs_digest as d

fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

SRT = "1\n00:00:01,000 --> 00:00:03,000\nhello there\nthis is the start\n\n2\n00:00:03,000 --> 00:00:05,000\nthis is the start\nand it goes on\n\n3\n00:20:00,000 --> 00:20:04,000\nthe end\n"
lines, secs = d.clean_srt(SRT)
check("clean: numbers and timestamps gone, rolling duplicate removed", lines == ["hello there", "this is the start", "and it goes on", "the end"])
check("clean: length from the last cue", secs == 1204)
long = [f"sentence number {i} with some words" for i in range(2000)]
text, cut = d.excerpts(long, 6000)
check("excerpts: bounded, flagged as cut, spread over the whole transcript",
      cut and len(text) < 6600 and "sentence number 0 " in text and "sentence number 1999" in text and " […] " in text)
check("excerpts: a short transcript is complete", d.excerpts(["a b c"], 6000) == ("a b c", False))
check("title: id and language suffix removed", d.title_of("My video [abcdefghijk].en-orig.srt") == "My video")

with tempfile.TemporaryDirectory() as parent:
    reg = {}
    for name, ids in (("alpha_subs", ["A" * 11, "B" * 11, "C" * 11]), ("beta_subs", ["D" * 11, "E" * 11])):
        ch = os.path.join(parent, name); os.makedirs(ch)
        reg[name] = {"url": "u", "lang": "en-orig"}
        json.dump({"url": "u", "ts": 1, "ids": ids}, open(os.path.join(ch, ".ids.cache"), "w"))
        for i in ids[:2] if name == "alpha_subs" else ids:      # alpha's newest two have files; its third does not
            open(os.path.join(ch, f"Video {i[0]} [{i}].en-orig.srt"), "w").write(SRT)
    # alpha: A, B have files, C (newest-first order A,B,C) has none; beta: D, E have files
    json.dump(reg, open(os.path.join(parent, "channels.json"), "w"))
    text, picks = d.build(parent, per_channel=1, max_videos=18, chars=6000, mark=False)
    check("peek: one newest video per channel, nothing marked", [p[1] for p in picks] == ["A" * 11, "D" * 11] and not os.path.exists(os.path.join(parent, "alpha_subs", ".digested.tsv")))
    check("output has channel, title, link and the length", "## alpha — Video A" in text and "https://youtu.be/" + "A" * 11 in text and "20 min" in text)
    text, picks = d.build(parent, per_channel=1)
    text2, picks2 = d.build(parent, per_channel=1)
    check("marked: the next run gives the NEXT video of each channel, never the same", [p[1] for p in picks2] == ["B" * 11, "E" * 11])
    text3, picks3 = d.build(parent, per_channel=1)
    check("when everything with a file was done: NADA NUEVO", text3.startswith("NADA NUEVO") and not picks3)
    json.dump({"url": "u", "ts": 1, "ids": ["Z" * 11] + ["A" * 11, "B" * 11, "C" * 11]}, open(os.path.join(parent, "alpha_subs", ".ids.cache"), "w"))
    open(os.path.join(parent, "alpha_subs", "New [" + "Z" * 11 + "].en-orig.srt"), "w").write(SRT)
    text4, picks4 = d.build(parent, per_channel=3)
    check("a new video (listed first) appears on the next run", [p[1] for p in picks4] == ["Z" * 11])
    check("max limits the total", len(d.build(parent, per_channel=5, max_videos=1, mark=False)[1]) <= 1)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        d.main([parent, "--per-channel", "5", "--max", "5", "--peek"])
    check("main --peek prints and writes no .digest-last", "NADA NUEVO" in buf.getvalue() and not os.path.exists(os.path.join(parent, ".digest-last.txt")))

# The output budget: 18 long videos must neither be cut silently nor lose any marker.
BIG = "1\n00:00:01,000 --> 00:00:03,000\n" + "\n".join(f"line {i} " + "x" * 40 for i in range(1500)) + "\n"
with tempfile.TemporaryDirectory() as parent:
    reg = {}
    for c in range(9):
        name = f"chan{c}_subs"; ch = os.path.join(parent, name); os.makedirs(ch)
        reg[name] = {"url": "u", "lang": "en-orig"}
        ids = [f"{c}{j}".ljust(11, "q") for j in range(2)]
        json.dump({"url": "u", "ts": 1, "ids": ids}, open(os.path.join(ch, ".ids.cache"), "w"))
        for i in ids:
            open(os.path.join(ch, f"Vid {i} [{i}].en-orig.srt"), "w").write(BIG)
    json.dump(reg, open(os.path.join(parent, "channels.json"), "w"))
    text, picks = d.build(parent, per_channel=2, max_videos=18, mark=False)
    check("budget: 18 long videos fit the total and all are shown", len(picks) == 18 and len(text) <= d.TOTAL_CHARS + 2500 and "FALTAN" not in text)
    check("budget: each video gets a share, not the full 6,000", all(len(e) < 3000 for e in text.split("\n## ")[1:]))
    text, picks = d.build(parent, per_channel=2, max_videos=18, mark=False, total_chars=9000)
    check("budget: too small a total shows fewer, says how many are missing", 0 < len(picks) < 18 and f"FALTAN {18 - len(picks)} videos" in text)
    text, picks = d.build(parent, per_channel=2, max_videos=18, total_chars=9000)
    done = sum(len(open(os.path.join(parent, n, ".digested.tsv")).read().split("\n")) - 1 for n in reg if os.path.exists(os.path.join(parent, n, ".digested.tsv")))
    check("budget: only the videos shown are marked as summarised", done == len(picks))
    text2, picks2 = d.build(parent, per_channel=2, max_videos=18, mark=False)
    check("budget: the ones left over come on the next run", len(picks2) == 18 - len(picks) and not set(p[1] for p in picks) & set(p[1] for p in picks2))
check("no registry: NADA NUEVO, no crash", d.build("/nonexistent-" + str(os.getpid()))[0].startswith("NADA NUEVO"))
print("\n".join(fails) or "subs_digest_selftest: all ok")
sys.exit(1 if fails else 0)
