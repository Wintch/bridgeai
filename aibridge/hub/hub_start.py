#!/usr/bin/env python3
"""hub_start: the host-side starter. A systemd timer runs it every 15 minutes; it decides, cheaply and WITHOUT starting anything,
whether the collector container should run now.

  hub_start.py [--dry-run] [--force]

Starts the hub (`docker compose run --rm hub run`, which exits by itself when nothing is left) only when ALL of these hold:
  - it is not already running;
  - something is due: a source whose time has come (state/next-wake) and we are inside the quiet window (HUB_WINDOW, local time,
    default 01:00-07:00); OR a person's request is waiting in an inbox (any hour, but at most one run per 10 minutes, and then only
    sources never collected yet: `--only-new`);
  - the host has memory for it (HUB_MIN_AVAIL_MB, default 2500) and at most HUB_MAX_AWAKE (default 2) people's brains are awake.
Otherwise it exits 0 saying why (one line in the journal). Nothing is ever started for a sleeping system with nothing to do.

Admin bot (the operator's ops bot, through ops/lib/notify.py; people never get these): the container has no token, so it leaves its
messages in state/admin-outbox.jsonl and this script sends them on EVERY tick (also when it starts nothing). It also says when work is
due but the hub does NOT run because of load ("se duerme por carga": low memory or too many Hermes awake; once, then a "✅" when it runs),
and once a day inside the window it checks what a container cannot see: security updates waiting on the VM's own apt and a pending reboot.

Environment: HUB_DATA (host path of the data root), HUB_COMPOSE (compose file), HUB_ENV (env file), HUB_WINDOW="HH:MM-HH:MM",
HUB_MIN_AVAIL_MB, HUB_MAX_AWAKE.
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ops", "lib"))   # the same relative place in the repo and on the VM
import hubcore  # noqa: E402

try:
    import notify  # noqa: E402
except ImportError:
    notify = None

DATA = os.environ.get("HUB_DATA", os.path.expanduser("~/aibridge/hubdata"))
COMPOSE = os.environ.get("HUB_COMPOSE", os.path.expanduser("~/aibridge/hub/docker-compose.hub.yml"))
ENVFILE = os.environ.get("HUB_ENV", os.path.expanduser("~/aibridge/hub.env"))
WINDOW = os.environ.get("HUB_WINDOW", "01:00-07:00")
MIN_AVAIL_MB = int(os.environ.get("HUB_MIN_AVAIL_MB", "2500"))
MAX_AWAKE = int(os.environ.get("HUB_MAX_AWAKE", "2"))
REQUEST_GAP_S = 600


def in_window(now_struct, window=WINDOW):
    a, b = window.split("-")
    ha, ma = (int(x) for x in a.split(":"))
    hb, mb = (int(x) for x in b.split(":"))
    cur, start, end = now_struct.tm_hour * 60 + now_struct.tm_min, ha * 60 + ma, hb * 60 + mb
    return start <= cur < end if start < end else (cur >= start or cur < end)   # a window may cross midnight


def mem_available_mb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 0


def awake_brains():
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=30).stdout
    return sum(1 for n in out.split() if n.endswith("-hermes") or n == "aibridge-hermes-agent")


def hub_running():
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=30).stdout
    return any(n.startswith("aibridge-hub") for n in out.split())


def read_epoch(path):
    try:
        return float(open(path).read().strip())
    except (OSError, ValueError):
        return None


def decide(now, local, data, avail_mb, awake, running, window=WINDOW, min_avail=MIN_AVAIL_MB, max_awake=MAX_AWAKE):
    """-> (args or None, reason, deferred). args = the arguments of `hub.py run`; deferred = work was due but the LOAD said no (the
    operator hears about it). Pure: every input is a parameter (tested offline)."""
    if running:
        return None, "already running", False
    waiting = hubcore.pending_requests(data)
    next_wake = read_epoch(os.path.join(data, "state", "next-wake"))
    last_start = read_epoch(os.path.join(data, "state", "last-start")) or 0
    full = next_wake is not None and now >= next_wake and in_window(local, window)
    request = waiting > 0 and now - last_start >= REQUEST_GAP_S
    if not (full or request):
        if next_wake is not None and now >= next_wake:
            return None, "something is due but it is not the quiet window", False
        return None, "nothing due" + (f"; {waiting} request(s) wait for the 10-minute gap" if waiting else ""), False
    if avail_mb < min_avail:
        return None, f"not enough free memory ({avail_mb} MB < {min_avail} MB)", True
    if awake > max_awake:
        return None, f"{awake} people's brains are awake (limit {max_awake}): busy hour", True
    return (["run"] if full else ["run", "--only-new"]), "due" if full else f"{waiting} request(s) waiting", False


# ---------- the operator's bot ----------
def flush_admin(data, send=None):
    """Send what the container left for the operator. A message that cannot be sent is put back (notify keeps its own outbox too)."""
    msgs = hubcore.take_admin_outbox(data)
    sent = 0
    for m in msgs:
        try:
            if send:
                send(m)
            elif notify is None:
                raise RuntimeError("no ops/lib/notify.py")
            elif m["level"] == "alert":
                notify.alert(m["key"], m["text"])
            elif m["level"] == "resolve":
                notify.resolve(m["key"], m["text"]) if m.get("text") else notify.resolve(m["key"])
            else:
                notify.send(m["text"])
            sent += 1
        except Exception as exc:
            print(f"hub_start: could not send an admin message ({type(exc).__name__}); kept for the next tick", flush=True)
            hubcore.admin_say(data, m["level"], m["key"], m.get("text", ""))
    return sent


def parse_upgradable(text):
    """`apt list --upgradable` -> (names of the security updates, total). Debian marks them with the -security suite."""
    sec, total = [], 0
    for line in text.splitlines():
        if "/" in line and "[upgradable" in line:
            total += 1
            first = line.split()[0]   # "libssl3/stable-security 3.0.15 amd64 [upgradable from: ...]"
            if "-security" in first.split("/", 1)[1]:
                sec.append(first.split("/")[0])
    return sec, total


def host_checks(data, now, in_win, run=None, say=None, reboot_flag="/var/run/reboot-required"):
    """Once a day inside the window: the VM's own pending security updates and reboot. Read-only (`apt list`, no sudo, no update)."""
    stamp = os.path.join(data, "state", "host-check")
    if not in_win or now - (read_epoch(stamp) or 0) < 20 * 3600:
        return None
    run = run or (lambda: subprocess.run(["apt", "list", "--upgradable"], capture_output=True, text=True, timeout=120, env={**os.environ, "LC_ALL": "C"}).stdout)
    try:
        sec, total = parse_upgradable(run())
    except Exception as exc:
        print(f"hub_start: host check failed ({type(exc).__name__})", flush=True)
        return None
    say = say or (lambda level, key, text: notify and (notify.alert(key, text) if level == "alert" else notify.resolve(key, text)))
    if sec:
        say("alert", "hub:host-patches", f"🛡️ La VM tiene {len(sec)} actualización(es) de seguridad sin aplicar (de {total} pendientes): "
                                         f"{', '.join(sec[:8])}{'…' if len(sec) > 8 else ''}. Requieren ventana y sudo del operador.")
    else:
        say("resolve", "hub:host-patches", "✅ La VM no tiene actualizaciones de seguridad pendientes.")
    if os.path.exists(reboot_flag):
        say("alert", "hub:host-reboot", "🔁 La VM pide reiniciar (reboot-required) para terminar de aplicar actualizaciones.")
    else:
        say("resolve", "hub:host-reboot", "✅ La VM ya no pide reiniciar.")
    os.makedirs(os.path.join(data, "state"), exist_ok=True)
    hubcore.atomic_write(stamp, f"{now:.0f}")
    return {"security": len(sec), "total": total}


def main(argv):
    now = time.time()
    local = time.localtime(now)
    try:
        flush_admin(DATA)   # every tick: findings and problems reach the operator even when the hub does not start
        host_checks(DATA, now, in_window(local))
    except Exception as exc:   # the admin side must never stop the hub from running
        print(f"hub_start: admin side failed ({type(exc).__name__}: {exc})", flush=True)
    args, reason, deferred = decide(now, local, DATA, mem_available_mb(), awake_brains(), hub_running())
    if "--force" in argv and args is None and reason != "already running":
        args, reason = ["run"], "forced"
    print(f"hub_start: {'start ' + ' '.join(args) if args else 'not starting'} ({reason})", flush=True)
    if deferred and notify is not None and "--dry-run" not in argv:
        notify.alert("hub:deferred", f"🌙 El hub tiene trabajo pendiente pero no corre: {reason}. Reintenta cada 15 min y avisa cuando corra.")
    if args is None or "--dry-run" in argv:
        return 0
    os.makedirs(os.path.join(DATA, "state"), exist_ok=True)
    hubcore.atomic_write(os.path.join(DATA, "state", "last-start"), f"{now:.0f}")
    cmd = ["docker", "compose", "-p", "aibridge-hub", "-f", COMPOSE, "--env-file", ENVFILE, "run", "--rm", "--name", "aibridge-hub-run", "hub"] + args
    rc = subprocess.run(cmd).returncode
    flush_admin(DATA)   # what this run left (findings, "se durmió por carga", "✅ corrió")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
