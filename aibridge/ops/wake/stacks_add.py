#!/usr/bin/env python3
"""Add a per-person stack to ops/wake/stacks.json from its .env (run from ~/aibridge by ops/provision_stack.sh).

  python3 ops/wake/stacks_add.py <name>      no-op when the stack is already listed

Everything the waker needs comes from stacks/<name>/.env: the bind address is the gateway of STACK_SUBNET, container
names follow docker-compose.stack.yml, and a stack with TELEGRAM_BOT_TOKEN gets telegram_env (the waker then wakes
it on a message through the public Bot API). Before 2026-10-09 this block was copied and edited by hand.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "stacks.json")


def env(path):
    out = {}
    for line in open(path):
        k, sep, v = line.rstrip("\n").partition("=")
        if sep and not k.startswith("#"):
            out[k.strip()] = v.strip()
    return out


def main(name):
    envf = os.path.join(os.getcwd(), "stacks", name, ".env")
    e = env(envf)
    subnet = e["STACK_SUBNET"]                       # 172.28.N.0/24
    bind = subnet.rsplit(".", 1)[0] + ".1"
    cfg = json.load(open(CONF)) if os.path.exists(CONF) else {"stacks": []}
    if any(s["name"] == name for s in cfg["stacks"]):
        print(f"stacks.json: {name} already listed")
        return 0
    block = {"name": name, "bind": bind, "port": 3099, "front": f"stack-{name}-web",
             "web": [f"stack-{name}-open-webui", f"stack-{name}-tts"], "brain": f"stack-{name}-hermes",
             "idle_web": 600, "idle_brain": 600, "est_brain_mb": 600, "est_web_mb": 300}
    if e.get("TELEGRAM_BOT_TOKEN"):
        block["telegram_env"] = envf
    cfg["stacks"].append(block)
    tmp = CONF + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(tmp, CONF)
    print(f"stacks.json: added {name} (bind {bind}{', telegram' if 'telegram_env' in block else ''})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
