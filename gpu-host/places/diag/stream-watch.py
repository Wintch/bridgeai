#!/usr/bin/env python3
"""stream_watch.py IFACE UID OUTDIR SECONDS: the stream leaving a place, every 100 ms (root on the GPU host, read-only).
IFACE is the place's network on the host (place.py names it NAMEdoc). Bytes the place sends out = the bridge's rx. A gap is >= 200 ms in a
row with under 5 % of the last 10 s median rate while that median is above 1 Mbit/s (someone is watching). One line per gap with its
length and the CPU of selkies and sunshine (the place's streamers) in that moment; one line per second with the rate (Mbit/s)."""
import collections, glob, os, statistics, sys, time

iface, uid, out, secs = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
os.makedirs(out, exist_ok=True)
gaps = open(os.path.join(out, "stream-gaps.log"), "a", buffering=1)
per_s = open(os.path.join(out, "stream-rate.csv"), "a", buffering=1)
if per_s.tell() == 0:
    per_s.write("time,mbit_out,selkies_cpu_pct,sunshine_cpu_pct\n")
HZ = os.sysconf("SC_CLK_TCK")

def rx():
    try:
        return int(open(f"/sys/class/net/{iface}/statistics/rx_bytes").read())
    except OSError:
        return None

def cpu_of(names):
    tot = 0
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if os.stat(d).st_uid != uid:
                continue
            if open(d + "/comm").read().strip() not in names:
                continue
            f = open(d + "/stat").read().rsplit(")", 1)[1].split()
            tot += int(f[11]) + int(f[12])
        except (OSError, IndexError, ValueError):
            pass
    return tot

hist = collections.deque(maxlen=100)          # last 10 s of 100 ms deltas
prev, t_prev = rx(), time.time()
sec_bytes, sec_start = 0, int(time.time())
c_prev = {"selkies": cpu_of({"selkies", "python3"}), "sunshine": cpu_of({"sunshine"})}
gap_start, gap_win = None, 0
gaps.write(f"{time.strftime('%T')} stream watch start {iface}\n")
t0 = time.time()
while time.time() - t0 < secs:
    time.sleep(0.1)
    cur, now = rx(), time.time()
    if cur is None or prev is None:
        prev = cur; continue
    d = cur - prev; prev = cur
    sec_bytes += d
    med = statistics.median(hist) if len(hist) >= 20 else 0
    watching = med * 10 * 8 > 1_000_000
    if watching and d < 0.05 * med:
        if gap_start is None:
            gap_start, gap_win = now - 0.1, 0
        gap_win += 1
    else:
        if gap_start is not None and gap_win >= 2:
            gaps.write(f"{time.strftime('%T', time.localtime(gap_start))} GAP ~{gap_win * 100} ms (median before {med * 80 / 1e6:.1f} Mbit/s)\n")
        gap_start, gap_win = None, 0
        hist.append(d)
    if int(now) != sec_start:
        c = {"selkies": cpu_of({"selkies", "python3"}), "sunshine": cpu_of({"sunshine"})}
        per_s.write(f"{time.strftime('%T', time.localtime(sec_start))},{sec_bytes * 8 / 1e6:.2f},"
                    f"{(c['selkies'] - c_prev['selkies']) * 100 / HZ:.0f},{(c['sunshine'] - c_prev['sunshine']) * 100 / HZ:.0f}\n")
        c_prev, sec_bytes, sec_start = c, 0, int(now)
gaps.write(f"{time.strftime('%T')} stream watch end\n")
