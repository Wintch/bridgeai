#!/usr/bin/env python3
"""subs-digest: the material for the morning summary of the newest videos, built from the subtitles on disk.

  subs-digest [PARENT=/workdir/descargas] [--per-channel 2] [--max 18] [--chars 6000] [--total 30000] [--peek] [--again]

For each channel registered by subs-fetch it takes the newest videos (the order of the channel listing, newest first) that have a
subtitle file and were NOT summarised before, cleans the captions (no numbers or timestamps, the rolling duplicates of automatic
captions removed) and prints, per video: channel, title, link, length, and excerpts spread over the whole transcript, ~6,000 characters
(a 20-minute video is ~15,000 tokens whole; the summary of 18 of them must fit in one turn). Printed ids are written to .digested.tsv
so the next run gives the next ones; --peek prints without marking, --again prints the last output again (a failed delivery).
When there is nothing new it prints NADA NUEVO. It never contacts the site: it reads files.
The scheduled agent turn (see SKILL_downloads.md, "Morning summary") runs this and writes the summary; nothing here calls a model.
"""
import argparse, json, os, re, sys, time

ID_IN_NAME = re.compile(r"\[([A-Za-z0-9_-]{11})\](?:\.[A-Za-z0-9_-]+)*\.(?:srt|vtt)$")
TS = re.compile(r"(\d+):(\d\d):(\d\d)[,.]\d+\s+-->\s+(\d+):(\d\d):(\d\d)")


def clean_srt(text):
    """(lines without numbers/timestamps/duplicates, length in seconds)."""
    lines, last_end, prev = [], 0, ""
    for raw in text.replace("\r", "").split("\n"):
        raw = raw.strip()
        if not raw or raw.isdigit():
            continue
        m = TS.search(raw)
        if m:
            last_end = int(m.group(4)) * 3600 + int(m.group(5)) * 60 + int(m.group(6))
            continue
        raw = re.sub(r"<[^>]+>", "", raw).strip()
        if not raw or raw == prev or (lines and raw in lines[-3:]):   # automatic captions repeat the previous line in every cue
            continue
        lines.append(raw)
        prev = raw
    return lines, last_end


def excerpts(lines, budget):
    """Text of at most ~budget characters, taken from evenly spaced places so the whole video is represented."""
    text = " ".join(lines)
    if len(text) <= budget:
        return text, False
    pieces, n = [], 10
    size = budget // n
    for i in range(n):
        start = int(i * (len(text) - size) / (n - 1))
        pieces.append(text[start:start + size].strip())
    return " […] ".join(pieces), True


def title_of(filename):
    t = re.sub(r"\s*\[[A-Za-z0-9_-]{11}\].*$", "", filename)
    return t.strip() or filename


TOTAL_CHARS = 30000      # everything one run prints, so the agent's tool result is never cut
MIN_PER_VIDEO = 1200     # fewer characters than this per video is no summary
ENTRY_OVERHEAD = 250     # channel, title, link and length lines around each video's excerpts


def build(parent, per_channel=2, max_videos=18, chars=6000, mark=True, now=None, total_chars=TOTAL_CHARS):
    now = now or time.time()
    try:
        reg = json.load(open(os.path.join(parent, "channels.json")))
    except (OSError, ValueError):
        return "NADA NUEVO (no hay canales registrados)", []
    picks = []
    for name in sorted(reg):
        d = os.path.join(parent, name)
        if not os.path.isdir(d):
            continue
        try:
            order = json.load(open(os.path.join(d, ".ids.cache"))).get("ids", [])
        except (OSError, ValueError):
            order = []
        files = {}
        for f in os.listdir(d):
            m = ID_IN_NAME.search(f)
            if m and f.endswith((".srt", ".vtt")):
                files.setdefault(m.group(1), f)
        done = set()
        try:
            done = {l.split("\t")[0] for l in open(os.path.join(d, ".digested.tsv"))}
        except OSError:
            pass
        n = 0
        for vid in order:
            if vid in files and vid not in done:
                picks.append((name, vid, os.path.join(d, files[vid])))
                n += 1
                if n >= per_channel:
                    break
    picks = picks[:max_videos]
    if not picks:
        return "NADA NUEVO", []
    # The agent's terminal tool cuts what a command prints at about 50 KB, and Russian text takes ~6x as many bytes once
    # JSON-escaped (18 videos x 6,000 characters were cut and only 10 of 18 videos reached the summary, with
    # nothing in the output saying so). So the whole output has a budget: each video gets an equal share (never more than
    # --chars, never less than MIN_PER_VIDEO) and, if even that does not fit, the rest wait for the next run, said in words.
    per = max(MIN_PER_VIDEO, min(chars, total_chars // len(picks) - ENTRY_OVERHEAD))
    entries, shown = [], []
    used = 0
    for name, vid, path in picks:
        lines, secs = clean_srt(open(path, encoding="utf-8", errors="replace").read())
        text, cut = excerpts(lines, per)
        entry = (f"\n## {name.replace('_subs', '')} — {title_of(os.path.basename(path))}\nhttps://youtu.be/{vid}"
                 f" · {secs // 60} min · {'extractos repartidos por todo el video' if cut else 'transcripción completa'}\n{text}")
        if shown and used + len(entry) > total_chars:
            break
        entries.append(entry)
        shown.append((name, vid, path))
        used += len(entry)
    left = len(picks) - len(shown)
    out = [f"# Subtítulos nuevos: {len(shown)} videos de {len({p[0] for p in shown})} canales"] + entries
    if left:
        out.append(f"\nFALTAN {left} videos nuevos que no entraron en esta tanda (no se marcaron): después de escribir este resumen, "
                   f"corre subs-digest otra vez para recibirlos.")
    if mark:
        for name, vid, _ in shown:
            with open(os.path.join(parent, name, ".digested.tsv"), "a") as f:
                f.write(f"{vid}\t{now:.0f}\n")
    return "\n".join(out), shown


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("parent", nargs="?", default="/workdir/descargas")
    ap.add_argument("--per-channel", type=int, default=2); ap.add_argument("--max", type=int, default=18)
    ap.add_argument("--chars", type=int, default=6000, help="most characters of excerpts per video")
    ap.add_argument("--total", type=int, default=TOTAL_CHARS, help="most characters the whole output may have")
    ap.add_argument("--peek", action="store_true", help="print without marking the videos as summarised")
    ap.add_argument("--again", action="store_true", help="print the last digest again")
    a = ap.parse_args(argv)
    last = os.path.join(a.parent, ".digest-last.txt")
    if a.again:
        try:
            print(open(last).read())
            return 0
        except OSError:
            print("NADA NUEVO (todavía no hubo un resumen)")
            return 0
    text, picks = build(a.parent, a.per_channel, a.max, a.chars, mark=not a.peek, total_chars=a.total)
    if picks and not a.peek:
        try:
            open(last, "w").write(text)
        except OSError:
            pass
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
