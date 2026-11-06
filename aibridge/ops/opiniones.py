#!/usr/bin/env python3
"""opiniones: what people wrote with /opinion, across every stack (2026-11-06). Run on VM105 from ~/aibridge (reads the host copies of each /workdir).

  ops/opiniones.py [--days N] [--stack NAME]     newest first; default the last 30 days, every stack

Reads only .opiniones.jsonl, the notes addressed to the administrator. The private notes (/opinion privado, .opiniones-privadas.jsonl) are never
opened here, and neither is anything else of the person's folder. The sharing level next to each note is what the person had chosen when they wrote it.
"""
import argparse
import glob
import json
import os
import time

ROOT = os.environ.get("AIBRIDGE_ROOT", os.path.expanduser("~/aibridge"))


def folders():
    yield "hernik", os.path.join(ROOT, "user1-workdir")
    for d in sorted(glob.glob(os.path.join(ROOT, "stacks", "*", "workdir"))):
        yield os.path.basename(os.path.dirname(d)), d


def notes(days=30, stack=None, root=None):
    rows = []
    for name, d in folders() if root is None else root:
        if stack and name != stack:
            continue
        try:
            lines = open(os.path.join(d, ".opiniones.jsonl"), encoding="utf-8").read().splitlines()
        except OSError:
            continue
        for ln in lines:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("ts", 0) >= time.time() - days * 86400:
                rows.append((r["ts"], name, r))
    return sorted(rows, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=30)
    ap.add_argument("--stack")
    a = ap.parse_args()
    rows = notes(a.days, a.stack)
    for _, name, r in rows:
        print(f"[{r.get('when', '?')}] {name} ({r.get('lang', '?')}, comparte {r.get('level', '?')})\n  {r.get('text', '').replace(chr(10), chr(10) + '  ')}\n")
    print(f"{len(rows)} nota(s) en los últimos {a.days:g} días.")


if __name__ == "__main__":
    main()
