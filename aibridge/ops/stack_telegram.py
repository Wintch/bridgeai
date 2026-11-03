#!/usr/bin/env python3
"""Give an existing per-person stack its Telegram bot, administrator-managed (run on VM105 from ~/aibridge).

  printf '%s\\n' "$TOKEN" | ops/stack_telegram.py <stack> <numeric Telegram user id> [--no-recreate] [--no-waker]

Why: a person who works only through the bot (job search) must not wait for the web address, DNS and certificate before
the bot answers. This is the same path as `provision_stack.sh --telegram-token`, usable after the stack exists:
  1. the token is read from STDIN (never from the command line: it would land in the shell history and `ps`) and checked
     with Telegram's getMe; the numeric id must be digits (not a phone number, not an @name);
  2. TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USERS go into stacks/<stack>/.env (the previous file is kept as
     .env.bak-<date>, mode 600), which compose passes to Hermes: the keys page then shows "connected by the
     administrator" and the person cannot overwrite it;
  3. ops/wake/stacks_add.py adds telegram_env to the stack's block in ops/wake/stacks.json, and the waker is restarted so
     it starts watching the bot (a message wakes the stack);
  4. ops/recreate_hermes.sh applies it to the container, only while the stack is asleep (otherwise it says to rerun that
     script later; the sleeping stack is never touched).
The token is never printed. One token can serve one stack only (a second stack using it gets Telegram error 409).
Test: python3 ops/stack_telegram_selftest.py
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "wake"))
import stacks_add  # noqa: E402

TOKEN_RE = re.compile(r"\d{8,10}:[A-Za-z0-9_-]{35}")
ID_RE = re.compile(r"\d{5,15}")
NAME_RE = re.compile(r"[a-z][a-z0-9]{1,19}")


def get_me(token):
    """(bot username, None) or (None, 'bad_token' | 'unreachable'). The token is in the URL: never print it."""
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=15) as r:
            j = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return None, ("bad_token" if e.code in (401, 404) else "unreachable")
    except (OSError, ValueError):
        return None, "unreachable"
    res = j.get("result") or {}
    return (res.get("username"), None) if j.get("ok") and res.get("is_bot") and res.get("username") else (None, "bad_token")


def write_env(path, updates):
    """Rewrite a KEY=VALUE file keeping every other line and its order; a new key is appended. Mode 600, backup kept."""
    lines = open(path, encoding="utf-8").read().splitlines()
    done = set()
    out = []
    for line in lines:
        k = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else None
        if k in updates:
            if k not in done:
                out.append(f"{k}={updates[k]}")
                done.add(k)
            continue
        out.append(line)
    for k, v in updates.items():
        if k not in done:
            out.append(f"{k}={v}")
    backup = f"{path}.bak-{datetime.date.today():%Y%m%d}"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
        os.chmod(backup, 0o600)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def container_running(name):
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", f"stack-{name}-hermes"],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def main(argv, stdin=None, token_check=get_me, run=subprocess.run, running=container_running):
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if len(args) != 2 or flags - {"--no-recreate", "--no-waker"}:
        print(__doc__, file=sys.stderr)
        return 2
    name, uid = args
    if not NAME_RE.fullmatch(name):
        print("stack name: a-z0-9, 2-20 chars", file=sys.stderr)
        return 2
    envf = os.path.join(os.getcwd(), "stacks", name, ".env")
    if not os.path.exists(envf):
        print(f"no such stack: {envf} (run from ~/aibridge)", file=sys.stderr)
        return 2
    if not ID_RE.fullmatch(uid):
        print("the Telegram id is a number of 5 to 15 digits (@userinfobot gives it); not a phone number, not an @name", file=sys.stderr)
        return 2
    token = ((stdin or sys.stdin).readline() or "").strip()
    if not TOKEN_RE.fullmatch(token):
        print("the token must come on stdin and look like 123456789:AA... (digits, a colon, 35 letters or digits)", file=sys.stderr)
        return 2
    bot, why = token_check(token)
    if not bot:
        print("Telegram does not recognise that token" if why == "bad_token" else "could not reach Telegram, try again", file=sys.stderr)
        return 1
    cur = stacks_add.env(envf)
    if cur.get("TELEGRAM_BOT_TOKEN") and cur["TELEGRAM_BOT_TOKEN"] != token:
        print(f"note: replacing the bot already set for {name}")
    write_env(envf, {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_ALLOWED_USERS": uid})
    stacks_add.main(name)
    print(f"bot @{bot} set for {name}, allowed user id ending ...{uid[-3:]} (token not shown)")
    if "--no-waker" not in flags:
        r = run(["systemctl", "--user", "restart", "aibridge-waker"])
        print("waker restarted" if r.returncode == 0 else "WARNING: could not restart the waker: systemctl --user restart aibridge-waker")
    if "--no-recreate" in flags:
        print(f"not recreating (asked). Apply with: ops/recreate_hermes.sh {name}   (stack asleep)")
    elif running(name):
        print(f"{name} is awake: not recreating. Once it sleeps: ops/recreate_hermes.sh {name}")
    else:
        print(f"recreating {name}'s container; this waits for Hermes to boot and can take up to 5 minutes (do not cancel)...")
        r = run([os.path.join(HERE, "recreate_hermes.sh"), name])
        return 0 if r.returncode == 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
