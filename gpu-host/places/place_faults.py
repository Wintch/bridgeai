#!/usr/bin/env python3
"""place_faults.py: provoke a failure in a place on purpose and check that every link of the chain saw it (run on the GPU host, as root).

Scenarios:
  ram_hog NAME [--to-mb N]   a process of the place's own user takes memory in 512 MB steps until it is over the place's limit (what
                             Metro 2033 Redux did by itself on 2026-11-28). Expected: place_memguard kills it within ~2 s, writes an incident,
                             the gate picks it up (places-incidents.csv, desktop notice, the person's bot, the bus).
Run it only on a place where a notice to the person is fine (the operator's own, or a test place): the person IS told, that is the point.
Prints one line per link with ok/FAIL and the seconds it took; exit 1 if a link failed.
"""
import argparse, glob, json, os, subprocess, sys, time

SPOOL = os.environ.get("MEMGUARD_SPOOL", "/var/lib/bridgeai-incidents")
ROOT = os.environ.get("PLACES_ROOT", "/srv/bridgeai/places")
GATE_STATE = os.environ.get("GATE_STATE_DIR", "/home/aishur/.local/state/bridgeai-gate")
HOG = r"""
import sys, time
step, to = 512 * 1024 * 1024, int(sys.argv[1]) * 1024 * 1024
held = []
while sum(len(b) for b in held) < to:
    b = bytearray(step)
    for i in range(0, step, 4096):
        b[i] = 1                       # touch every page: real resident memory, like a runaway game
    held.append(b)
    print(sum(len(x) for x in held) // 1048576, flush=True)
    time.sleep(0.2)
time.sleep(30)
"""


def settings(name):
    return json.load(open(os.path.join(ROOT, name, ".settings.json")))


def ram_hog(name, to_mb):
    s = settings(name)
    uid = s.get("uid")
    limit = s.get("mem") or os.environ.get("PLACE_MEM", "9g")
    to_mb = to_mb or (int(limit[:-1]) * (1024 if limit.endswith("g") else 1) + 1536)
    before = set(os.listdir(SPOOL)) if os.path.isdir(SPOOL) else set()
    print(f"ram_hog in {name} (uid {uid}, limit {limit}): up to {to_mb} MB")
    t0 = time.time()
    p = subprocess.Popen(["docker", "exec", "-u", f"{uid}:{uid}", f"{name}doc", "python3", "-c", HOG, str(to_mb)],
                         stdout=subprocess.PIPE, text=True)
    last = 0
    for line in p.stdout:
        last = int(line.strip() or 0)
    rc = p.wait()
    t_end = time.time() - t0
    results = []
    killed = rc in (137, -9)
    results.append(("the hog was killed (SIGKILL), not finished", killed, f"rc={rc}, reached {last} MB in {t_end:.1f} s"))
    inc, t_inc = None, None
    for _ in range(20):
        new = sorted(set(os.listdir(SPOOL)) - before) if os.path.isdir(SPOOL) else []
        mine = [n for n in new if n.endswith(f"-{name}.json")]
        if mine:
            inc, t_inc = json.load(open(os.path.join(SPOOL, mine[-1]))), time.time() - t0
            break
        time.sleep(0.5)
    results.append(("the guardian wrote an incident", inc is not None and inc.get("reason") == "over_place_limit",
                    f"{inc and inc.get('reason')}, rss {inc and inc.get('rss_mb')} MB, after {t_inc and round(t_inc, 1)} s"))
    seen = False
    for _ in range(40):
        try:
            seen = any(n in json.load(open(os.path.join(GATE_STATE, "incidents-seen.json"))) for n in [mine[-1]] if inc)
        except (OSError, ValueError, NameError):
            seen = False
        if seen:
            break
        time.sleep(1)
    results.append(("the gate picked it up (told the person, logged it)", seen, os.path.join(GATE_STATE, "places-incidents.csv")))
    bad = 0
    for what, ok, detail in results:
        print(f"{'ok  ' if ok else 'FAIL'} {what}  ({detail})")
        bad += not ok
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=["ram_hog"])
    ap.add_argument("name")
    ap.add_argument("--to-mb", type=int, default=0)
    a = ap.parse_args()
    return ram_hog(a.name, a.to_mb)


if __name__ == "__main__":
    sys.exit(main())
