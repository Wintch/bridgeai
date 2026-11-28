#!/usr/bin/env python3
"""place_memguard.py: the host's memory guardian for the places (root, every second).

Why: a place's memory limit (its cgroup) does not hold everything a game takes. Memory the NVIDIA driver pins for a game is not charged to
the place: on 2026-11-28 Metro 2033 Redux (native build) grew to 61 GB of RSS in ~25 s inside a place limited to 20 GB, the whole host fell
to 0.19 GB available, the driver failed (NV_ERR_NO_MEMORY) and every place and service on the machine was at risk. Only the host can see that.

Rules (a process "of a place" is one whose uid is a place's uid, 3001-3999 as place.py hands them out, or a uid listed in a .settings.json):
  1. a single process of a place over its place's RAM limit ("mem" in .settings.json, else PLACE_MEM, else 9g)  -> SIGKILL that process
  2. host MemAvailable under the floor (MEMGUARD_FLOOR_MB, default 3072) -> SIGKILL the place process with the most RSS, if it has over 1 GB
Never the host's own processes, never two kills of the same place within MEMGUARD_COOLDOWN_S (10 s). MEMGUARD_DRY_RUN=1 logs what it would kill.
After a kill: one JSON line in the log (MEMGUARD_LOG) and one incident file in MEMGUARD_SPOOL (read by the gate, which tells the person and the
operator). Only numbers, the place, the program name and the game's .exe name: never a person's files.

  sudo python3 place_memguard.py            run (a systemd unit: place-memguard.service)
  python3 place_memguard.py --once --dry-run one pass, print what it sees
"""
import glob, json, os, re, signal, sys, time

ROOT = os.environ.get("PLACES_ROOT", "/srv/bridgeai/places")
FLOOR_MB = int(os.environ.get("MEMGUARD_FLOOR_MB", "3072"))
MIN_KILL_MB = int(os.environ.get("MEMGUARD_MIN_KILL_MB", "1024"))
COOLDOWN_S = int(os.environ.get("MEMGUARD_COOLDOWN_S", "10"))
INTERVAL_S = float(os.environ.get("MEMGUARD_INTERVAL_S", "1"))
LOG = os.environ.get("MEMGUARD_LOG", "/var/log/bridgeai-memguard.jsonl")
SPOOL = os.environ.get("MEMGUARD_SPOOL", "/var/lib/bridgeai-incidents")
DRY = os.environ.get("MEMGUARD_DRY_RUN", "") == "1"
PROC = os.environ.get("MEMGUARD_PROC", "/proc")
DEFAULT_MEM = os.environ.get("PLACE_MEM", "9g")
UID_RANGE = range(3001, 4000)


def size_mb(v):
    m = re.fullmatch(r"(\d+)([mg])", str(v or ""))
    return int(m.group(1)) * (1024 if m.group(2) == "g" else 1) if m else None


def places():
    """{uid: (place, limit_mb)} from the places' .settings.json."""
    out = {}
    for f in glob.glob(os.path.join(ROOT, "*", ".settings.json")):
        try:
            s = json.load(open(f))
        except (OSError, ValueError):
            continue
        uid = s.get("uid")
        if isinstance(uid, int) and uid in UID_RANGE:
            out[uid] = (os.path.basename(os.path.dirname(f)), size_mb(s.get("mem")) or size_mb(DEFAULT_MEM) or 9216)
    return out


def mem_available_mb():
    try:
        for line in open(os.path.join(PROC, "meminfo")):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def game_name(cmd):
    m = re.findall(r"([A-Za-z0-9_ .-]+\.exe)\b", cmd)
    return os.path.basename(m[-1].replace("\\", "/")).strip() if m else ""


def place_procs(owners):
    """[(rss_mb, pid, uid, comm, game)] of the places' processes."""
    out = []
    for d in glob.glob(os.path.join(PROC, "[0-9]*")):
        try:
            uid = os.stat(d).st_uid
            if uid not in owners:
                continue
            rss = 0
            for line in open(os.path.join(d, "status")):
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1]) // 1024
                    break
            comm = open(os.path.join(d, "comm")).read().strip()
            cmd = open(os.path.join(d, "cmdline"), "rb").read().replace(b"\0", b" ").decode(errors="replace")
            out.append((rss, int(os.path.basename(d)), uid, comm, game_name(cmd)))
        except (OSError, ValueError):
            continue
    return out


def decide(owners, procs, avail_mb, last_kill, now):
    """[(pid, place, reason, rss_mb, comm, game)] to kill now (pure: testable)."""
    kills, busy = [], set()
    for rss, pid, uid, comm, game in sorted(procs, reverse=True):
        place, limit = owners[uid]
        if place in busy or now - last_kill.get(place, 0) < COOLDOWN_S:
            continue
        if rss > limit:
            kills.append((pid, place, "over_place_limit", rss, comm, game)); busy.add(place)
    if avail_mb is not None and avail_mb < FLOOR_MB and not kills:
        for rss, pid, uid, comm, game in sorted(procs, reverse=True):
            place = owners[uid][0]
            if rss >= MIN_KILL_MB and place not in busy and now - last_kill.get(place, 0) >= COOLDOWN_S:
                kills.append((pid, place, "host_low_memory", rss, comm, game))
                break
    return kills


def record(entry):
    line = json.dumps(entry, sort_keys=True)
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(line + "\n")
        if not entry.get("dry_run"):
            os.makedirs(SPOOL, mode=0o755, exist_ok=True)
            p = os.path.join(SPOOL, f"{int(entry['ts'] * 1000)}-{entry['place']}.json")
            with open(p + ".tmp", "w") as f:
                json.dump(entry, f)
            os.chmod(p + ".tmp", 0o644)
            os.replace(p + ".tmp", p)
    except OSError as e:
        print(f"memguard: could not write the record: {e}", file=sys.stderr, flush=True)


def step(last_kill, now=None):
    now = time.time() if now is None else now
    owners = places()
    if not owners:
        return []
    procs = place_procs(owners)
    avail = mem_available_mb()
    done = []
    for pid, place, reason, rss, comm, game in decide(owners, procs, avail, last_kill, now):
        killed = False
        if not DRY:
            try:
                os.kill(pid, signal.SIGKILL); killed = True
            except OSError:
                pass
        last_kill[place] = now
        entry = {"ts": round(now, 3), "event": "memguard_kill", "place": place, "pid": pid, "program": comm, "game": game,
                 "rss_mb": rss, "reason": reason, "host_available_mb": avail, "floor_mb": FLOOR_MB,
                 "place_limit_mb": next((l for p, l in owners.values() if p == place), None),
                 "killed": killed, "dry_run": DRY}
        record(entry)
        done.append(entry)
    return done


def main(argv):
    global DRY
    if "--dry-run" in argv:
        DRY = True
    last_kill = {}
    if "--once" in argv:
        owners = places()
        procs = place_procs(owners)
        print(json.dumps({"host_available_mb": mem_available_mb(), "floor_mb": FLOOR_MB,
                          "places": {p: l for p, l in owners.values()},
                          "top": [{"place": owners[u][0], "rss_mb": r, "program": c, "game": g} for r, _, u, c, g in sorted(procs, reverse=True)[:5]]},
                         indent=1))
        step(last_kill)
        return 0
    print(f"memguard: watching places under {ROOT}, floor {FLOOR_MB} MB, every {INTERVAL_S} s{' (dry run)' if DRY else ''}", flush=True)
    while True:
        try:
            step(last_kill)
        except Exception as e:                      # the guardian never stops on its own error
            print(f"memguard: step failed: {e}", file=sys.stderr, flush=True)
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
