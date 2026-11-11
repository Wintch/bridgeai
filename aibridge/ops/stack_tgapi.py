#!/usr/bin/env python3
"""Move per-person stacks' Telegram bots to their OWN Local Bot API server (files up to 2 GB both ways instead of the public API's 20 MB
download cap). Run on the Docker host from ~/aibridge.

  ops/stack_tgapi.py NAME [NAME ...] [--dry-run] [--no-recreate]

For each stack, in an order that never leaves a bot half moved (a step that fails stops that stack and leaves it as it was):
  1. checks: the stack has a bot token (stacks/NAME/.env or the keys page's workdir/.telegram.env), its Hermes container is ASLEEP (a live
     bot polls the cloud; logOut would cut the person off mid-chat), and the operator's TELEGRAM_API_ID/HASH (my.telegram.org, the same pair
     hernik uses) are in ~/aibridge/.env;
  2. starts the stack's telegram-bot-api service (stacks/docker-compose.stack.yml, profile tgapi) with the id and hash given through the
     environment only, so nothing is written yet;
  3. logOut on the public Bot API (Telegram: "you must log out the bot before running it locally"; afterwards the bot cannot go back to the
     cloud for 10 minutes);
  4. getMe through the local server (this logs the bot in there) must answer with the bot's username;
  5. only then writes TELEGRAM_API_ID/HASH into stacks/NAME/.env (backup kept, mode 600) and "telegram_api" into ops/wake/stacks.json.
Then, once for all: stops the waker, resets each moved bot's last-seen update id (the local server numbers updates in its own, lower
sequence: a kept cloud id would hide every new message), starts it again (it reads a sleeping bot through that server from now on) and recreates each moved stack while it
sleeps (ops/recreate_hermes.sh), so its Hermes gets the base_url (start_hermes.sh), the server's file folder and the outbox.
A stack already moved (TELEGRAM_API_ID in its .env and telegram_api in stacks.json) is skipped. Tokens and the hash are never printed.
Undo for one stack: remove TELEGRAM_API_ID/HASH from its .env and telegram_api from stacks.json, `docker rm -f stack-NAME-telegram-bot-api`,
restart the waker and recreate the stack; the bot can use the cloud again 10 minutes after its logOut (Telegram's rule), and the first
cloud call after that logs it back in there.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from stack_telegram import write_env  # noqa: E402  (same KEY=VALUE rewrite: other lines kept, backup, mode 600)

NAME_RE = re.compile(r"^[a-z][a-z0-9]{1,19}$")
TOKEN_RE = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{30,80}$")
STACKS_JSON = os.path.join("ops", "wake", "stacks.json")
PORT = 8081


def env_file(path):
    out = {}
    try:
        for line in open(path, encoding="utf-8"):
            k, sep, v = line.strip().partition("=")
            if sep and not k.startswith("#"):
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def compose(name):
    return ["docker", "compose", "-p", f"stack-{name}", "-f", "stacks/docker-compose.stack.yml", "-f", "stacks/hardening.override.yml",
            "--env-file", f"stacks/{name}/.env"]


def running(container):
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", container], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def container_ip(container):
    r = subprocess.run(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", container], capture_output=True, text=True)
    return (r.stdout.split() or [""])[0] if r.returncode == 0 else ""


def call(base, token, method, timeout=30):
    """-> (ok, result or description). POST with an empty JSON body; the token is only in the URL, which is never printed."""
    req = urllib.request.Request(f"{base}/bot{token}/{method}", data=b"{}", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read())
        except ValueError:
            return False, f"HTTP {e.code}"
    except (OSError, ValueError) as e:
        return False, type(e).__name__
    return bool(j.get("ok")), (j.get("result") if j.get("ok") else str(j.get("description") or "error")[:120])


def stacks_json_set(name, container):
    path = STACKS_JSON
    data = json.load(open(path))
    hit = [s for s in data.get("stacks", []) if s.get("name") == name]
    if not hit:
        raise RuntimeError(f"{name} is not in {path}")
    if hit[0].get("telegram_api") == container:
        return False
    shutil.copy2(path, f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}-tgapi")
    hit[0]["telegram_api"], hit[0]["telegram_api_port"] = container, PORT
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return True


def reset_seen(name):
    """tg_seen = 0 in ops/wake/<name>.state.json (backup kept). Call only while the waker is stopped."""
    p = os.path.join("ops", "wake", f"{name}.state.json")
    try:
        d = json.load(open(p))
    except (OSError, ValueError):
        return
    if d.get("tg_seen"):
        shutil.copy2(p, f"{p}.bak-{time.strftime('%Y%m%d-%H%M%S')}-tgseen")
        d["tg_seen"] = 0
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, p)


def move(name, ids, dry):
    """-> "moved", "skipped: why" or "FAILED: why"."""
    envp = f"stacks/{name}/.env"
    if not NAME_RE.match(name) or not os.path.exists(envp):
        return "FAILED: no such stack"
    env = env_file(envp)
    token = env.get("TELEGRAM_BOT_TOKEN") or env_file(f"stacks/{name}/workdir/.telegram.env").get("TELEGRAM_BOT_TOKEN", "")
    if not TOKEN_RE.match(token or ""):
        return "skipped: no Telegram bot on this stack"
    server = f"stack-{name}-telegram-bot-api"
    conf = next((s for s in json.load(open(STACKS_JSON)).get("stacks", []) if s.get("name") == name), {})
    if env.get("TELEGRAM_API_ID") and conf.get("telegram_api") == server:
        return "skipped: already on its own Local Bot API server"
    if running(f"stack-{name}-hermes"):
        return "skipped: awake (its Hermes polls the cloud right now); run again once it sleeps"
    if dry:
        return f"would: start {server}, logOut from the cloud, getMe through it, write the .env and stacks.json"
    r = subprocess.run(compose(name) + ["--profile", "tgapi", "up", "-d", "telegram-bot-api"], capture_output=True, text=True,
                       env=dict(os.environ, TELEGRAM_API_ID=ids[0], TELEGRAM_API_HASH=ids[1]))
    if r.returncode != 0:
        return "FAILED: could not start the server: " + (r.stderr.strip().splitlines() or ["?"])[-1][:160]
    ip = ""
    for _ in range(30):   # the server takes a few seconds to listen
        ip = container_ip(server)
        if ip:
            try:
                socket.create_connection((ip, PORT), timeout=2).close()
                break
            except OSError:
                pass
        time.sleep(1)
    else:
        return "FAILED: the server does not listen (stack left on the cloud; `docker logs` of the server says why)"
    ok, why = call("https://api.telegram.org", token, "logOut")
    if not ok and "logged out" not in str(why).lower():
        subprocess.run(["docker", "rm", "-f", server], capture_output=True)
        return f"FAILED: logOut refused ({why}); the server was removed and the bot stays on the cloud"
    me = None
    for _ in range(12):   # the first local call logs the bot in
        ok, res = call(f"http://{ip}:{PORT}", token, "getMe")
        if ok and isinstance(res, dict) and res.get("username"):
            me = res["username"]
            break
        time.sleep(5)
    if not me:
        return ("FAILED: getMe through the local server did not answer. The bot is logged OUT of the cloud: fix the server and run this "
                "again (or undo, see the docstring: the cloud takes it back 10 minutes after the logOut)")
    write_env(envp, {"TELEGRAM_API_ID": ids[0], "TELEGRAM_API_HASH": ids[1]})
    stacks_json_set(name, server)
    return f"moved (@{me})"


def main(argv):
    names = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not names or flags - {"--dry-run", "--no-recreate"}:
        print(__doc__, file=sys.stderr)
        return 2
    main_env = env_file(".env")
    ids = (main_env.get("TELEGRAM_API_ID", ""), main_env.get("TELEGRAM_API_HASH", ""))
    if not (re.fullmatch(r"\d{3,12}", ids[0]) and re.fullmatch(r"[0-9a-f]{32}", ids[1])):
        print("TELEGRAM_API_ID / TELEGRAM_API_HASH are not in ~/aibridge/.env (my.telegram.org -> API development tools)", file=sys.stderr)
        return 2
    dry = "--dry-run" in flags
    moved, failed = [], []
    for n in names:
        try:
            out = move(n, ids, dry)
        except Exception as e:   # one stack's surprise must not stop the others
            out = f"FAILED: {type(e).__name__}"
        print(f"{n}: {out}", flush=True)
        if out.startswith("moved"):
            moved.append(n)
        elif out.startswith("FAILED"):
            failed.append(n)
    if not moved:
        return 1 if failed else 0
    # The local server numbers updates in its OWN sequence, far below the cloud's (169931121 against a saved 993879195), so the
    # waker's last-seen id would hide every new message of a moved bot. Reset it with the waker stopped (a running waker saves its own copy).
    subprocess.run(["systemctl", "--user", "stop", "aibridge-waker"])
    for n in moved:
        reset_seen(n)
    r = subprocess.run(["systemctl", "--user", "start", "aibridge-waker"])
    print("waker restarted (last-seen update reset for the moved bots): it reads them through their servers now" if r.returncode == 0
          else "WARNING: start the waker NOW (systemctl --user start aibridge-waker): the moved bots wake nobody until it runs")
    if "--no-recreate" in flags:
        print("not recreating (asked): ops/recreate_hermes.sh NAME for each moved stack, while it sleeps")
        return 0
    rc = 0
    for n in moved:
        print(f"recreating {n} (its Hermes gets the local server; up to 5 minutes)...", flush=True)
        r = subprocess.run([os.path.join(HERE, "recreate_hermes.sh"), n], capture_output=True, text=True)
        last = [l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL", "image"))]
        print("  " + " | ".join(last[-2:]) if last else f"  recreate rc {r.returncode}")
        rc |= 0 if r.returncode == 0 else 1
    return rc | (1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
