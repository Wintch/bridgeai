#!/usr/bin/env python3
"""Give an existing per-person stack one of the person's OWN keys, validated and stored like the keys page does it
(run on VM105 from ~/aibridge, while the stack's Hermes is awake):

  printf '%s\\n' "$KEY" | ops/stack_keys.py <stack> gemini|openrouter|huggingface|nvidia|groq [--no-activate]

Why: the keys page needs the web address (DNS, certificate), and a person who works only through the bot (hertin) does not
have it yet. This runs the SAME code as the page inside the stack's container (keys_server.do_save / do_service_save):
  - gemini, openrouter, huggingface, nvidia: the key is checked against the provider, tried on a model with one test call,
    stored with `hermes auth add`, and (unless --no-activate) that model becomes the one Hermes uses from then on. Only
    ONE provider can be the active model: with several keys, activate the one the person wants and add the others with
    --no-activate (Hermes keeps them in its credential pool).
  - groq (voice notes): stored by `gateway servicios guardar groq`, which checks it first.
The key travels on STDIN only (never on the command line: shell history, `ps`), is never printed, and the answer shows at
most its last 4 characters. The container must be running (it is not touched otherwise): write to the person's bot first,
the waker wakes the stack, then run this within 10 minutes (before it sleeps again).
Test: python3 ops/stack_keys_selftest.py
"""
import json
import re
import subprocess
import sys

NAME_RE = re.compile(r"[a-z][a-z0-9]{1,19}")
LLM = ("gemini", "openrouter", "huggingface", "nvidia")
SERVICES = ("groq",)
# What a key looks like (a hint to catch a wrong paste early; the provider has the last word).
SHAPE = {"gemini": r"AIza[0-9A-Za-z_-]{20,}", "openrouter": r"sk-or-[0-9A-Za-z_-]{20,}", "huggingface": r"hf_[0-9A-Za-z]{20,}",
         "nvidia": r"nvapi-[0-9A-Za-z_-]{20,}", "groq": r"gsk_[0-9A-Za-z]{20,}"}

# Runs INSIDE the container; the key is read from stdin. Prints one JSON line with ok and a message that never has the key.
INSIDE = r"""
import json, sys
sys.path.insert(0, "/app")
import keys_server as k
kind, name, activate = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
key = sys.stdin.readline().strip()
if kind == "llm":
    code, r = k.do_save(name, key, None, activate)
else:
    code, r = k.do_service_save(name, key)
print(json.dumps({"ok": bool(r.get("ok")), "msg": r.get("message") or r.get("error") or ""}))
"""


def container_running(name):
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", f"stack-{name}-hermes"], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def main(argv, stdin=None, run=subprocess.run, running=container_running):
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if len(args) != 2 or flags - {"--no-activate"}:
        print(__doc__, file=sys.stderr)
        return 2
    name, what = args
    if not NAME_RE.fullmatch(name):
        print("stack name: a-z0-9, 2-20 chars", file=sys.stderr)
        return 2
    if what not in LLM + SERVICES:
        print(f"unknown key type {what!r}: one of {', '.join(LLM + SERVICES)}", file=sys.stderr)
        return 2
    key = ((stdin or sys.stdin).readline() or "").strip()
    if not key or any(c.isspace() for c in key) or len(key) < 12:
        print("the key must come on stdin: one line, no spaces (copy it whole)", file=sys.stderr)
        return 2
    if not re.fullmatch(SHAPE[what], key):
        print(f"that does not look like a {what} key (the first characters differ from what {what} issues): not sent anywhere", file=sys.stderr)
        return 2
    if not running(name):
        print(f"stack-{name}-hermes is asleep: write to the person's bot (the waker wakes it, ~20-150 s), then run this again "
              "before it sleeps (10 idle minutes)", file=sys.stderr)
        return 3
    activate = "0" if "--no-activate" in flags else "1"
    kind = "llm" if what in LLM else "service"
    r = run(["docker", "exec", "-i", f"stack-{name}-hermes", "python3", "-c", INSIDE, kind, what, activate],
            input=key + "\n", capture_output=True, text=True, timeout=240)
    try:
        j = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        print(f"FAIL: no usable answer from the container (rc {r.returncode}); the key was not shown or logged", file=sys.stderr)
        return 1
    # the message never carries the key (keys_server returns at most the last 4 characters); belt and braces anyway
    msg = str(j.get("msg", "")).replace(key, "<key>")
    print(("OK: " if j.get("ok") else "FAIL: ") + msg)
    return 0 if j.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
