#!/usr/bin/env python3
"""Scheduled, no model: fetch the subtitles of videos published lately in every registered channel, then a slice of any backlog.

Hermes runs this as `hermes cron create "every 3h" --name subs-nuevos --no-agent --script subs_new.py --deliver telegram`: what it prints
is sent to the person, EMPTY output = silence. So it prints only when something needs a human: the site rate-limited us, or the run failed.

1. `subs-fetch --all /workdir/descargas --new` looks at the newest 40 videos of each channel (one request each), asks for the ones not on
   disk and not known to lack captions, and exits quickly when there are none. A channel already being downloaded by a long job is skipped
   (exit 3), not an error.
2. `subs-fetch --all /workdir/descargas --backlog N` then works on the channels that are NOT complete (videos of the listing with no file,
   not known caption-less or unavailable), about N videos in all. Before this step existed a backlog stopped by a rate limit on
   2026-11-05 stayed stopped: 4,026 videos were missing a week later and nothing said so. Silent too; a rate limit here is not repeated to
   the person (step 1 already says it when it happens, and the next round tries again by itself).

Hermes kills a no-agent cron script after 1 h, so both steps share DEADLINE_S.
"""
import os, shlex, subprocess, sys, time

PARENT = os.environ.get("SUBS_PARENT", "/workdir/descargas")
CMD = shlex.split(os.environ.get("SUBS_FETCH_CMD", "subs-fetch"))
BACKLOG = int(os.environ.get("SUBS_BACKLOG_PER_RUN", "300"))   # ~30 min at 2 channels x ~300 videos an hour
DEADLINE_S = 55 * 60
NEW_TIMEOUT_S = 20 * 60
MIN_BACKLOG_S = 5 * 60   # less time than this left: no backlog slice this round


def run(args, timeout):
    try:
        r = subprocess.run(CMD + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return None, ""
    except OSError as exc:
        return "oserror", str(exc)


def main():
    t0 = time.time()
    code, out = run(["--all", PARENT, "--new"], NEW_TIMEOUT_S)
    if code == "oserror":
        print(f"subs-nuevos: no pude ejecutar subs-fetch: {out}")
        return 0
    if code is None:
        print(f"subs-nuevos: la revisión de canales tardó más de {NEW_TIMEOUT_S // 60} minutos y se cortó.")
        return 0
    if code == 75 or "RATE LIMITED" in out:
        print("subs-nuevos: YouTube frenó las peticiones; pausa de 1 hora, se reintenta solo en la próxima vuelta.")
        return 0
    if code not in (0, 3):
        tail = "\n".join(out.strip().splitlines()[-3:])
        print(f"subs-nuevos: falló (código {code}).\n{tail}")
        return 0
    left = DEADLINE_S - (time.time() - t0)
    if BACKLOG <= 0 or left < MIN_BACKLOG_S:
        return 0
    code, out = run(["--all", PARENT, "--backlog", str(BACKLOG)], left)
    if code not in (0, 3, 75, None) and "RATE LIMITED" not in out and "SOFT BLOCK" not in out:
        tail = "\n".join(out.strip().splitlines()[-3:])
        print(f"subs-nuevos: el pendiente de subtítulos falló (código {code}).\n{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
