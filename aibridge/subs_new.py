#!/usr/bin/env python3
"""Scheduled, no model: fetch the subtitles of videos published lately in every registered channel.

Hermes runs this as `hermes cron create "every 3h" --name subs-nuevos --no-agent --script subs_new.py --deliver telegram`: what it prints
is sent to the person, EMPTY output = silence. So it prints only when something needs a human: the site rate-limited us, or the run failed.
`subs-fetch --all --new` looks at the newest 40 videos of each channel (one request each), asks for the ones not on disk and not known to
lack captions, and exits quickly when there are none. A channel already being downloaded by a long job is skipped (exit 3), not an error.
"""
import subprocess, sys

try:
    r = subprocess.run(["subs-fetch", "--all", "/workdir/descargas", "--new"], capture_output=True, text=True, timeout=3000)
except subprocess.TimeoutExpired:
    print("subs-nuevos: la revisión de canales tardó más de 50 minutos y se cortó.")
    sys.exit(0)
except OSError as exc:
    print(f"subs-nuevos: no pude ejecutar subs-fetch: {exc}")
    sys.exit(0)
out = (r.stdout or "") + (r.stderr or "")
if r.returncode == 75 or "RATE LIMITED" in out:
    print("subs-nuevos: YouTube frenó las peticiones; pausa de 1 hora, se reintenta solo en la próxima vuelta.")
elif r.returncode not in (0, 3):
    tail = "\n".join(out.strip().splitlines()[-3:])
    print(f"subs-nuevos: falló (código {r.returncode}).\n{tail}")
