#!/usr/bin/env python3
"""Sample one container's CPU, memory and stall counters every few seconds, so a turn's time can be split into "the machine was busy"
and "the machine was waiting" (ops/turn_breakdown.py --cpu reads the file). Numbers only: no names, no text.

  ops/turn_cpu_sampler.py --cgroup /sys/fs/cgroup/system.slice/docker-<id>.scope --out ~/turn-cpu.jsonl [--every 2]

--cgroup is the container's cgroup v2 directory (the staging docker:dind container's includes everything running inside it, which is what
we want: the whole stack). Find it with `docker inspect -f '{{.Id}}' NAME` and /sys/fs/cgroup/system.slice/docker-<id>.scope (systemd
driver) or /sys/fs/cgroup/docker/<id> (cgroupfs driver). Run it on the machine that runs the stack, one process per stack, under
`systemd-run --user` or nohup; it only reads files and appends a line per sample (~70 bytes: 3 MB for a day at 2 s).

One line: {"ts", "cpu_us", "thr_us", "mem_mb", "cpu_psi_us", "io_psi_us", "mem_psi_us"}
  cpu_us      cpu.stat usage_usec: CPU time used by everything in the cgroup, microseconds (monotonic)
  thr_us      cpu.stat throttled_usec: time the cgroup was held back by its CPU cap (monotonic; > 0 means the cap, not the CPU, was the limit)
  mem_mb      memory.current
  *_psi_us    pressure stall "some total": microseconds in which at least one task waited for CPU / disk / memory (monotonic; absent when the
              kernel has no PSI for the cgroup). io_psi_us is the disk wait: the number that tells SATA from NVMe.
"""
import argparse, json, os, sys, time


def read_kv(path):
    """A flat "key value" file (cpu.stat) as {key: int}; {} when unreadable."""
    out = {}
    try:
        for line in open(path):
            k, _, v = line.partition(" ")
            try:
                out[k] = int(v)
            except ValueError:
                pass
    except OSError:
        pass
    return out


def read_psi(path):
    """The `total=` of the "some" line of a pressure file, or None."""
    try:
        for line in open(path):
            if line.startswith("some "):
                for part in line.split():
                    if part.startswith("total="):
                        return int(part[6:])
    except (OSError, ValueError):
        pass
    return None


def sample(cg, now=None):
    st = read_kv(os.path.join(cg, "cpu.stat"))
    if "usage_usec" not in st:
        return None
    try:
        mem = int(open(os.path.join(cg, "memory.current")).read()) // 1048576
    except (OSError, ValueError):
        mem = None
    rec = {"ts": round(now if now is not None else time.time(), 2), "cpu_us": st["usage_usec"], "thr_us": st.get("throttled_usec", 0), "mem_mb": mem}
    for name, f in (("cpu_psi_us", "cpu.pressure"), ("io_psi_us", "io.pressure"), ("mem_psi_us", "memory.pressure")):
        v = read_psi(os.path.join(cg, f))
        if v is not None:
            rec[name] = v
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="sample a container's cgroup counters")
    ap.add_argument("--cgroup", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--every", type=float, default=2.0, help="seconds between samples (default 2)")
    ap.add_argument("--count", type=int, default=0, help="stop after N samples (0 = run until stopped; the selftest uses it)")
    a = ap.parse_args(argv)
    if sample(a.cgroup) is None:
        print(f"{a.cgroup}: no cpu.stat there (cgroup v2 directory of the container?)", file=sys.stderr)
        return 2
    n = 0
    with open(a.out, "a", buffering=1) as f:
        while True:
            rec = sample(a.cgroup)
            if rec:
                f.write(json.dumps(rec) + "\n")
            n += 1
            if a.count and n >= a.count:
                return 0
            time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
