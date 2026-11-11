#!/usr/bin/env python3
"""Print one provider's API key for Hermes's `key_cmd` (the curated /model menu rows written by ops/model_menu.py).

  provider_key.py nvidia NVIDIA_API_KEY

Order: the person's own key saved from the keys page (auth.json credential_pool, same pick as ops/model_menu.py
probes), then the variable in $HERMES_HOME/.env, then the process environment. Prints only the key; nothing when none.
A `key_env` row could not see keys that live only in the credential pool, so a person's own key would be ignored.
"""
import json
import os
import sys


def main(prov, *env_vars):
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    try:
        pool = json.load(open(os.path.join(home, "auth.json"))).get("credential_pool", {}).get(prov, [])
    except (OSError, ValueError, AttributeError):
        pool = []
    for e in pool if isinstance(pool, list) else []:
        key = isinstance(e, dict) and (e.get("api_key") or e.get("access_token") or e.get("key"))
        if key:
            print(key)
            return
    dotenv = {}
    try:
        for line in open(os.path.join(home, ".env")):
            k, sep, v = line.partition("=")
            if sep and not k.lstrip().startswith("#"):
                dotenv[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    for var in env_vars:
        key = dotenv.get(var) or os.environ.get(var)
        if key:
            print(key)
            return


if __name__ == "__main__":
    main(*sys.argv[1:])
