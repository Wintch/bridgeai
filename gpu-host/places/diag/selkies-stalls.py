#!/usr/bin/env python3
"""selkies-stalls.py CONTAINER [--since DURATION]: the web stream's stalls in a place, from Selkies' own log (docker logs), per session.

A stall is Selkies' "Backpressure TRIGGERED" line: the browser fell N frames behind the server and Selkies held frames until it caught
up (picture and sound stop together). Each line says why:
  path holding    the data did not reach the browser (the network, TCP)  -> the person's connection, or WebRTC/UDP would help
  path delivered  the data arrived but the page did not keep up (decode)  -> the person's browser/device (hardware decoding off?)
Prints per session (a session starts at each "Client ... connected"): minutes, stalls, stalls per hour, frames behind (median, p90,
max), how many were network vs browser; and the encoder Selkies reported. The number to compare before/after a change is the stalls
per hour and their size, with the same game and the same client (see README: test conditions). Read-only; run on the GPU host as root.
"""
import argparse, re, statistics, subprocess, sys
from datetime import datetime

TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)")
STALL = re.compile(r"Backpressure TRIGGERED .*EffDesync:([0-9.]+)f .*path (holding|delivered)")
CONNECT = re.compile(r"Client \(.*\) connected")
ENCODER = re.compile(r"Encoder: (.+)$")


def sessions(lines):
    out, cur, encoder = [], None, ""
    for line in lines:
        m = TS.match(line)
        t = datetime.fromisoformat(m.group(1)) if m else None
        body = line.split(" ", 1)[1] if m and " " in line else line
        e = ENCODER.search(body)
        if e:
            encoder = e.group(1).strip()
        if CONNECT.search(body):
            cur = {"start": t, "end": t, "stalls": [], "encoder": encoder}
            out.append(cur)
            continue
        if cur is None:
            continue
        if t:
            cur["end"] = t
        s = STALL.search(body)
        if s:
            cur["stalls"].append((float(s.group(1)), s.group(2)))
        if e:
            cur["encoder"] = encoder
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("container")
    ap.add_argument("--since", default="24h", help="docker logs --since (default 24h)")
    a = ap.parse_args()
    r = subprocess.run(["docker", "logs", "--timestamps", "--since", a.since, a.container], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(r.stderr.strip() or f"docker logs failed ({r.returncode})")
    ss = sessions((r.stdout + r.stderr).splitlines())
    if not ss:
        print("no web session in the log for that period"); return 0
    print("start     min  stalls  per_h  behind_med  p90  max  network  browser  encoder")
    for s in ss:
        mins = max((s["end"] - s["start"]).total_seconds() / 60, 0.01) if s["start"] and s["end"] else 0.01
        f = sorted(x for x, _ in s["stalls"])
        net = sum(1 for _, w in s["stalls"] if w == "holding")
        med = statistics.median(f) if f else 0
        p90 = f[min(len(f) - 1, int(len(f) * 0.9))] if f else 0
        print(f"{s['start']:%H:%M:%S} {mins:5.0f} {len(f):7d} {len(f) * 60 / mins:6.1f} {med:11.0f} {p90:4.0f} {max(f, default=0):4.0f}"
              f" {net:8d} {len(f) - net:8d}  {s['encoder'][:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
