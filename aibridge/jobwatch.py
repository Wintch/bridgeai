#!/usr/bin/env python3
"""jobwatch: free "tell me when it's done" for long jobs (renders, transcodes, remote tasks).

Runs as a Hermes cron job with --no-agent (no LLM, no cost): every minute Hermes executes this script
and delivers its stdout verbatim to Telegram; EMPTY stdout = silence. Nothing here talks to Telegram.

Registry: one JSON file per job in /workdir/jobs/ (the bind-mounted dir, so it survives rebuilds):
  {"title": "Render del video X",          # shown in the message
   "pid": 1234,                             # done when this process is gone (or a zombie), and/or
   "done_file": "/workdir/out/video.mp4",   # done when this file exists, and/or
   "check_cmd": "ssh resolve-host 'test -f /x'",  # done when this check exits 0 (20s limit); only `test -e|-f|-s|-d PATH`,
                                            # here or as `ssh HOST 'test -f PATH'` (no shell: see safe_check_argv)
   "output": "/hermes-files/<uuid>/x.mp4",  # optional, appended to the message
   "started": 1791150000,                   # epoch seconds (set by the writer; used for duration)
   "timeout_min": 120}                      # optional, default 120: reports "not finished" and drops it

A job is reported once, then its file is deleted. Unreadable files are renamed *.bad and reported (and removed after 7
days). A file younger than 3 seconds is left for the next run: the agent may still be writing it.
"""
import glob
import json
import os
import re
import shlex
import subprocess
import time

REGISTRY = os.environ.get("JOBWATCH_DIR", "/workdir/jobs")


def pid_gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    try:  # a zombie is finished too
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] == "Z"
    except OSError:
        return True


HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,99}$")
TEST_FLAGS = ("-e", "-f", "-s", "-d")


def safe_check_argv(cmd):
    """The argv for a check_cmd, or None when it is not one of the allowed shapes. This runs every minute with nobody
    watching and outside Hermes's command approval, so it is never handed to a shell (2026-11-03 review: `shell=True` ran
    whatever text the agent wrote into the job file). Allowed: `test -e|-f|-s|-d PATH`, and the same on another machine as
    `ssh HOST 'test -f PATH'` (or unquoted)."""
    try:
        parts = shlex.split(str(cmd))
    except ValueError:
        return None
    def test_argv(p):
        if len(p) == 3 and p[0] == "test" and p[1] in TEST_FLAGS and p[2] and not p[2].startswith("-"):
            return p
        return None
    if test_argv(parts):
        return parts
    if len(parts) >= 3 and parts[0] == "ssh" and HOST_RE.match(parts[1]):
        inner = parts[2:]
        if len(inner) == 1:
            try:
                inner = shlex.split(inner[0])
            except ValueError:
                return None
        t = test_argv(inner)
        if t:
            return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", parts[1], "test", t[1], shlex.quote(t[2])]
    return None


def is_done(job: dict) -> bool:
    checks = []
    if job.get("pid"):
        checks.append(pid_gone(int(job["pid"])))
    if job.get("done_file"):
        checks.append(os.path.exists(job["done_file"]))
    if job.get("check_cmd"):
        argv = safe_check_argv(job["check_cmd"])
        if argv is None:
            raise NotAllowed(job["check_cmd"])
        try:
            checks.append(subprocess.run(argv, timeout=20, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0)
        except (subprocess.TimeoutExpired, OSError):
            checks.append(False)
    # Several conditions given: the job is done when ANY of them says so (e.g. process gone OR file there).
    return any(checks)


def num(value, default: float) -> float:
    """A finite number from whatever the writer put in the file, else the default."""
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return f if f == f and f not in (float("inf"), float("-inf")) else default


def minutes(started) -> str:
    try:
        m = max(0, int((time.time() - float(started)) / 60))
        return f"{m} min"
    except (TypeError, ValueError, OverflowError):
        return "?"


def report(line: str) -> None:
    print(line, flush=True)   # out before the file is deleted: a later failure must not lose a finished job's message


class NotAllowed(Exception):
    pass


def check(path: str) -> bool:
    """Handle one job file; True when it was reported (and removed)."""
    if time.time() - os.path.getmtime(path) < 3:
        return False
    with open(path) as f:
        job = json.load(f)
    assert isinstance(job, dict) and (job.get("pid") or job.get("done_file") or job.get("check_cmd"))
    started = num(job.get("started"), os.path.getmtime(path))   # a writer that forgot it: the file's own age
    timeout_min = num(job.get("timeout_min"), 120)
    title = job.get("title") or os.path.basename(path)
    extra = f"\n{job['output']}" if job.get("output") else ""
    try:
        done = is_done(job)
    except NotAllowed:
        report(f"⚠️ {title}: no puedo vigilarlo, la comprobación no está permitida (solo `test -f RUTA`, también como "
               f"`ssh HOST 'test -f RUTA'`). Dejo de vigilarlo.")
        os.remove(path)
        return True
    if done:
        report(f"✅ {title} terminó (tardó {minutes(started)}).{extra}")
    elif time.time() - started > timeout_min * 60:
        report(f"⚠️ {title}: no terminó tras {timeout_min:g} min, dejo de vigilarlo.")
    else:
        return False
    os.remove(path)
    return True


def main() -> None:
    for bad in glob.glob(os.path.join(REGISTRY, "*.json.bad")):
        try:
            if time.time() - os.path.getmtime(bad) > 7 * 86400:
                os.remove(bad)
        except OSError:
            pass
    for path in sorted(glob.glob(os.path.join(REGISTRY, "*.json"))):
        try:
            check(path)
        except (ValueError, TypeError, OverflowError, OSError, AssertionError, AttributeError):
            # One bad file must not stop the others (a crash here leaves every later job unwatched, every run).
            try:
                os.replace(path, path + ".bad")
            except OSError:
                pass
            report(f"⚠️ Registro de trabajo ilegible: {os.path.basename(path)} (lo dejé como .bad)")


if __name__ == "__main__":
    main()
