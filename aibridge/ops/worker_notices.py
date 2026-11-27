#!/usr/bin/env python3
"""The always-on workers' notices, handed over when the person next writes. Operator tool, the Docker host, ~/aibridge.

  python3 ops/worker_notices.py wake --stack NAME --chat ID [--reason telegram] [--delay S]   (ops/wake/on_wake.d/60-worker-notices)
  python3 ops/worker_notices.py peek --stack NAME     how many are waiting (counts only, the text is never printed here)

Why: a job moved from a stack to an always-on worker (workers/WORKERS.md) no longer reaches Telegram itself. What the stack's cron used to
send (the subs job: "the site rate-limited us", "the backlog has not moved for N hours") is left as a file in the person's
/workdir/.worker-notices/. This script, run after a wake caused by the person's own Telegram message, sends those files to that chat
through the stack's own bot, oldest first, and moves each sent one to .worker-notices/sent/ (a failed send leaves it for the next wake).
Rules (as ops/job_summary.py):
- Only a wake from the person's own Telegram message, and only to the stack's allowed user.
- The person's verbosity (NOTICES.md): these are notices about the machinery, so a person at "critical" is not sent them; the files
  are moved to .worker-notices/skipped/ so they do not pile up.
- The files are read and moved inside the stack's own container (they may sit on an NFS mount from the always-on machine, root-owned).
- ops/worker_notices.log gets counts and codes, never the text; the bot token is never printed.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.environ.get("WORKER_NOTICES_LOG", os.path.join(HERE, "worker_notices.log"))
DIR = "/workdir/.worker-notices"
MAX_PER_WAKE = 5


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


daily_ad = _load("daily_ad")
job_summary = _load("job_summary")


def log(**kw):
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(dict(ts=int(time.time()), **kw)) + "\n")
    except OSError:
        pass


def in_stack(brain, script, *args, timeout=60):
    """(exit code, stdout) of a small python snippet inside the brain container; (None, "") when docker failed."""
    try:
        r = subprocess.run(["docker", "exec", "-i", brain, "python3", "-", *args], input=script, capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return None, ""


LIST = r'''
import json, os, sys
d = sys.argv[1]
try:
    names = sorted(n for n in os.listdir(d) if n.endswith(".txt") and os.path.isfile(os.path.join(d, n)))
except OSError:
    names = []
level = "normal"
try:
    p = json.load(open("/workdir/.prefs.json"))
    v = p.get("verbosity")
    level = v if v in ("critical", "normal", "detailed") else ("detailed" if p.get("verbose") is True else "normal")
except (OSError, ValueError, AttributeError):
    pass
out = []
for n in names[: int(sys.argv[2])]:
    try:
        out.append({"name": n, "text": open(os.path.join(d, n), encoding="utf-8", errors="replace").read()[:3500]})
    except OSError:
        pass
print(json.dumps({"level": level, "waiting": len(names), "notices": out}))
'''

MOVE = r'''
import os, sys
d, sub, name = sys.argv[1], sys.argv[2], sys.argv[3]
if "/" in name or name.startswith("."):
    sys.exit(2)
os.makedirs(os.path.join(d, sub), exist_ok=True)
os.replace(os.path.join(d, name), os.path.join(d, sub, name))
'''


def waiting(brain):
    rc, out = in_stack(brain, LIST, DIR, str(MAX_PER_WAKE))
    if rc != 0:
        return None
    try:
        d = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return d if isinstance(d, dict) else None


def cmd_wake(a):
    if a.reason != "telegram" or not a.chat:
        return 0
    st = daily_ad.stack_of(a.stack)
    if not st or not st.get("brain"):
        log(event="skip", stack=a.stack, why="unknown stack")
        return 0
    time.sleep(max(0.0, a.delay))
    d = waiting(st["brain"])
    if not d or not d.get("notices"):
        return 0
    if d.get("level") == "critical":                      # machinery notices are not for this person (NOTICES.md)
        for n in d["notices"]:
            in_stack(st["brain"], MOVE, DIR, "skipped", n["name"])
        log(event="skipped", stack=a.stack, n=len(d["notices"]), why="critical")
        return 0
    tgt = daily_ad.target(st)
    if not tgt:
        log(event="skip", stack=a.stack, why="no bot token for this stack")
        return 2
    if tgt[2] and str(a.chat) not in tgt[2]:
        log(event="skip", stack=a.stack, why="chat is not the stack's allowed user")
        return 2
    sent = 0
    for n in d["notices"]:
        if not n.get("text", "").strip():
            in_stack(st["brain"], MOVE, DIR, "sent", n["name"])
            continue
        if not job_summary.send(tgt, a.chat, n["text"]):
            log(event="failed", stack=a.stack, sent=sent)
            return 1                                      # the rest waits for the next wake
        in_stack(st["brain"], MOVE, DIR, "sent", n["name"])
        sent += 1
    log(event="sent", stack=a.stack, n=sent, waiting=d.get("waiting", 0) - sent)
    return 0


def cmd_peek(a):
    st = daily_ad.stack_of(a.stack)
    if not st or not st.get("brain"):
        print("unknown stack")
        return 2
    d = waiting(st["brain"])
    if d is None:
        print("could not read (is the stack up?)")
        return 1
    print(f"{a.stack}: {d.get('waiting', 0)} notice(s) waiting, verbosity {d.get('level')}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wake")
    w.add_argument("--stack", required=True)
    w.add_argument("--chat", required=True)
    w.add_argument("--reason", default="telegram")
    w.add_argument("--delay", type=float, default=12.0)
    p = sub.add_parser("peek")
    p.add_argument("--stack", required=True)
    a = ap.parse_args(argv)
    return cmd_wake(a) if a.cmd == "wake" else cmd_peek(a)


if __name__ == "__main__":
    sys.exit(main())
