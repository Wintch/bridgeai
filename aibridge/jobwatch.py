#!/usr/bin/env python3
"""jobwatch: free "tell me when it's done" for long jobs (renders, transcodes, remote tasks).

Runs as a Hermes cron job with --no-agent (no LLM, no cost): every minute Hermes executes this script
and delivers its stdout verbatim to Telegram; EMPTY stdout = silence. Nothing here talks to Telegram.

Registry: one JSON file per job in /workdir/jobs/ (the bind-mounted dir, so it survives rebuilds):
  {"title": "Render del video X",          # shown in the message
   "pid": 1234,                             # done when this process is gone (or a zombie), and/or
   "done_file": "/workdir/out/video.mp4",   # done when this file exists, and/or
   "check_cmd": "ssh resolve-host 'test -f /x'",  # done when this shell command exits 0 (20s limit)
   "output": "/hermes-files/<uuid>/x.mp4",  # optional, appended to the message
   "started": 1791150000,                   # epoch seconds (set by the writer; used for duration)
   "timeout_min": 120}                      # optional, default 120: reports "not finished" and drops it

A job is reported once, then its file is deleted. Unreadable files are renamed *.bad and reported.
"""
import glob
import json
import os
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


def is_done(job: dict) -> bool:
    checks = []
    if job.get("pid"):
        checks.append(pid_gone(int(job["pid"])))
    if job.get("done_file"):
        checks.append(os.path.exists(job["done_file"]))
    if job.get("check_cmd"):
        try:
            checks.append(subprocess.run(job["check_cmd"], shell=True, timeout=20,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0)
        except subprocess.TimeoutExpired:
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


def check(path: str) -> bool:
    """Handle one job file; True when it was reported (and removed)."""
    job = json.load(open(path))
    assert isinstance(job, dict) and (job.get("pid") or job.get("done_file") or job.get("check_cmd"))
    started = num(job.get("started"), os.path.getmtime(path))   # a writer that forgot it: the file's own age
    timeout_min = num(job.get("timeout_min"), 120)
    title = job.get("title") or os.path.basename(path)
    extra = f"\n{job['output']}" if job.get("output") else ""
    if is_done(job):
        report(f"✅ {title} terminó (tardó {minutes(started)}).{extra}")
    elif time.time() - started > timeout_min * 60:
        report(f"⚠️ {title}: no terminó tras {timeout_min:g} min, dejo de vigilarlo.")
    else:
        return False
    os.remove(path)
    return True


def main() -> None:
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
