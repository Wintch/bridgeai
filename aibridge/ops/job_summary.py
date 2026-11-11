#!/usr/bin/env python3
"""The night job summary, handed over when the person next writes. Operator tool, the Docker host, ~/aibridge.

  python3 ops/job_summary.py wake --stack NAME --chat ID [--reason telegram] [--delay S]   (ops/wake/on_wake.d/50-job-summary)
  python3 ops/job_summary.py peek --stack NAME     what is waiting for that person: counts only, the text is never printed here

Why: "para él y todos los que usan el módulo de buscar trabajo (una vez seteado acorde) hay que hacer un
scan nocturno. Así cuando entra al bot, ya tiene el resumen hecho." The scan is jobnight.py inside the stack (04:30, no LLM, prints
nothing); it keeps the summary in the person's data/.jobpush-pending.json. This script, run after a wake caused by the person's own
Telegram message, asks the stack for it (`jobpush.py --pending peek`), sends it to that chat through the stack's own bot, and only
then confirms it (`--pending ack ID`): a failed send leaves it for the next wake, and a run that finished in between is not lost.
Rules:
- Only a wake from the person's own Telegram message, and only to the stack's allowed user (same check as ops/daily_ad.py).
- Plain text, link previews off; sent DELAY seconds after the wake so "listo para trabajar" comes first.
- The summary is the person's own job search: it goes to their chat only. ops/job_summary.log gets counts and codes, never the text.
- Never prints the bot token (it travels only inside the request URL, which is never logged).
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.environ.get("JOB_SUMMARY_LOG", os.path.join(HERE, "job_summary.log"))
SCRIPT = "/root/.hermes/scripts/jobpush.py"

_spec = importlib.util.spec_from_file_location("daily_ad", os.path.join(HERE, "daily_ad.py"))
daily_ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(daily_ad)


def log(**kw):
    try:
        with open(LOG, "a") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + " ".join(f"{k}={v}" for k, v in kw.items()) + "\n")
    except OSError:
        pass


def in_stack(brain, *args, timeout=60):
    """(exit code, stdout) of jobpush.py inside the stack's brain container; (None, "") when docker itself failed."""
    try:
        r = subprocess.run(["docker", "exec", brain, "python3", SCRIPT, *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return None, ""


def peek(brain):
    rc, out = in_stack(brain, "--pending", "peek")
    if rc != 0:
        return None, rc
    try:
        d = json.loads(out.strip() or "{}")
    except ValueError:
        return None, "bad-json"
    return (d if isinstance(d, dict) else {}), 0


def send(tgt, chat, text):
    token, base, _ = tgt
    body = {"chat_id": chat, "text": text[:4000], "link_preview_options": {"is_disabled": True}}
    req = urllib.request.Request(f"{base}/bot{token}/sendMessage", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("ok") is True
    except Exception as e:                                # never print the URL: it carries the bot token
        log(event="send_failed", kind=type(e).__name__)
        return False


def cmd_wake(a):
    if a.reason != "telegram" or not a.chat:
        return 0                                          # only a wake from the person's own message
    st = daily_ad.stack_of(a.stack)
    if not st or not st.get("brain"):
        log(event="skip", stack=a.stack, why="unknown stack")
        return 0
    time.sleep(max(0.0, a.delay))
    d, why = peek(st["brain"])
    if d is None:                                         # old image without --pending, or no jobfinder: nothing to hand over
        log(event="skip", stack=a.stack, why=f"peek rc={why}")
        return 0
    if not d.get("text"):
        return 0
    tgt = daily_ad.target(st)
    if not tgt:
        log(event="skip", stack=a.stack, why="no bot token for this stack")
        return 2
    if tgt[2] and str(a.chat) not in tgt[2]:              # only the stack's own person, never another chat id
        log(event="skip", stack=a.stack, why="chat is not the stack's allowed user")
        return 2
    if not send(tgt, a.chat, d["text"]):
        log(event="failed", stack=a.stack)
        return 1                                          # kept: the next wake tries again
    rc, _ = in_stack(st["brain"], "--pending", "ack", str(d.get("id", "")))
    log(event="sent", stack=a.stack, ack=rc, chars=len(d["text"]))
    return 0 if rc in (0, 3) else 1


def cmd_peek(a):
    st = daily_ad.stack_of(a.stack)
    if not st or not st.get("brain"):
        print("unknown stack")
        return 2
    d, why = peek(st["brain"])
    if d is None:
        print(f"could not ask the stack (rc={why}; asleep, old image or no jobfinder)")
        return 1
    print("nothing waiting" if not d.get("text") else f"a summary is waiting: id {d.get('id')}, {len(d['text'])} characters, "
          f"{d['text'].count(chr(10)) + 1} lines (the text is the person's, not shown here)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wake")
    w.add_argument("--stack", required=True)
    w.add_argument("--chat", default="")
    w.add_argument("--reason", default="telegram")
    w.add_argument("--delay", type=float, default=float(os.environ.get("JOB_SUMMARY_DELAY", "5")))
    p = sub.add_parser("peek")
    p.add_argument("--stack", required=True)
    a = ap.parse_args(argv)
    return {"wake": cmd_wake, "peek": cmd_peek}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
