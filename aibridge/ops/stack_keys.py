#!/usr/bin/env python3
"""Give an existing per-person stack one of the person's OWN keys, validated and stored like the keys page does it
(run on the Docker host from ~/aibridge, while the stack's Hermes is awake):

  printf '%s\\n' "$KEY" | ops/stack_keys.py <stack> gemini|openrouter|huggingface|nvidia|groq [--no-activate] [--model ID]

Why: the keys page needs the web address (DNS, certificate), and a person who works only through the bot does not
have it yet. This runs the SAME code as the page inside the stack's container (keys_server.do_save / do_service_save):
  - gemini, openrouter, huggingface, nvidia: the key is checked against the provider, tried on a model with one test call,
    stored with `hermes auth add`, and (unless --no-activate) that model becomes the one Hermes uses from then on. Only
    ONE provider can be the active model: with several keys, activate the one the person wants and add the others with
    --no-activate (Hermes keeps them in its credential pool).
  - groq (voice notes): stored by `gateway servicios guardar groq`, which checks it first.
--model ID: test and use THAT model instead of letting the page's code pick one (a free Gemini plan answers 429 for some
models, and then the key is kept but the model is not switched; e.g. --model gemini-flash-lite-latest).
The key travels on STDIN only (never on the command line: shell history, `ps`), is never printed, and the answer shows at
most its last 4 characters. If the stack is asleep this starts its Hermes container itself and waits for it (1-3 minutes, it says so); the waker puts
it back to sleep after the idle time.
Test: python3 ops/stack_keys_selftest.py
"""
import contextlib
import json
import os
import re
import subprocess
import sys
import time

NAME_RE = re.compile(r"[a-z][a-z0-9]{1,19}")
LLM = ("gemini", "openrouter", "huggingface", "nvidia")
SERVICES = ("groq",)
# What a key looks like (a hint to catch a wrong paste early; the provider has the last word).
# Google is moving Gemini keys from AIza... to AQ.... (AI Studio only issues AQ. since 2026): accept both.
SHAPE = {"gemini": r"(AIza[0-9A-Za-z_-]{20,}|AQ\.[0-9A-Za-z._-]{20,})", "openrouter": r"sk-or-[0-9A-Za-z_-]{20,}", "huggingface": r"hf_[0-9A-Za-z]{20,}",
         "nvidia": r"nvapi-[0-9A-Za-z_-]{20,}", "groq": r"gsk_[0-9A-Za-z]{20,}"}

# Runs INSIDE the container; the key is read from stdin. Prints one JSON line with ok and a message that never has the key.
INSIDE = r"""
import json, sys
sys.path.insert(0, "/app")
import keys_server as k
kind, name, activate = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
model = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
key = sys.stdin.readline().strip()
if kind == "llm":
    code, r = k.do_save(name, key, model, activate)
else:
    code, r = k.do_service_save(name, key)
print(json.dumps({"ok": bool(r.get("ok")), "msg": r.get("message") or r.get("error") or ""}))
"""


def container_running(name):
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", f"stack-{name}-hermes"], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


@contextlib.contextmanager
def hold_awake(name):
    """Tell the waker the stack is busy while this runs. Without it the waker put the stack back to sleep 33 s after this
    script started it, before the key was stored: an idle container with no turn is exactly what it stops.
    Uses the waker's own busy marker (a file in the stack's workdir, honoured for 90 minutes: `busy_marker`), written from
    the host so the container need not be running; removed afterwards unless it was already there (a real job's)."""
    path = os.path.join("stacks", name, "workdir", "jobfinder", "data", ".jobpush-running")
    made = False
    if os.path.isdir(os.path.dirname(path)):
        if not os.path.exists(path):
            open(path, "w").close()
            made = True
    else:
        print("note: no jobfinder/data folder in this stack, so the waker may put it to sleep while this runs; "
              "if the answer is a failure, write to the person's bot first and run it again", file=sys.stderr)
    try:
        yield
    finally:
        if made:
            with contextlib.suppress(OSError):
                os.remove(path)


def container_wake(name, max_s=300):
    """Start the stack's Hermes container (it exists, it is only stopped) and wait until its API answers /health. The waker
    notices it is up and puts it back to sleep after its idle time, so nothing else has to be undone. True = answering."""
    c = f"stack-{name}-hermes"
    r = subprocess.run(["docker", "start", c], capture_output=True, text=True)
    if r.returncode != 0:
        return False
    t0 = time.time()
    while time.time() - t0 < max_s:
        h = subprocess.run(["docker", "exec", c, "curl", "-sf", "-m", "2", "http://localhost:8642/health"], capture_output=True)
        if h.returncode == 0:
            return True
        time.sleep(3)
        if int(time.time() - t0) % 30 < 3:
            print(f"  still booting ({int(time.time() - t0)} s)...", flush=True)
    return False


def main(argv, stdin=None, run=subprocess.run, running=container_running, wake=container_wake, hold=hold_awake):
    argv = list(argv)
    model = ""
    if "--model" in argv:   # --model ID: the one option with a value
        i = argv.index("--model")
        if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            print("--model needs a model id", file=sys.stderr)
            return 2
        model = argv[i + 1]
        del argv[i:i + 2]
        if not re.fullmatch(r"[A-Za-z0-9._:/-]{3,100}", model):
            print("that model id has characters a model id does not have", file=sys.stderr)
            return 2
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
    if model and what not in LLM:
        print("--model only applies to Gemini/OpenRouter/Hugging Face/NVIDIA keys", file=sys.stderr)
        return 2
    with hold(name):
        if not running(name):
            print(f"stack-{name}-hermes is asleep: starting it (the first boot can take 1-3 minutes; the waker puts it back to sleep "
                  "after its idle time)...", flush=True)
            if not wake(name):
                print(f"could not start stack-{name}-hermes or it did not answer /health in 5 minutes: check `docker logs "
                      f"stack-{name}-hermes`; nothing was stored", file=sys.stderr)
                return 3
        activate = "0" if "--no-activate" in flags else "1"
        kind = "llm" if what in LLM else "service"
        # The check below calls the provider (several test calls for Gemini/OpenRouter, a model switch afterwards) and prints
        # nothing until it ends: say so, or it looks hung (the operator could not tell).
        print(f"checking the {what} key with the provider and storing it in {name}'s Hermes; this takes 10-60 seconds"
              + (" (a model switch can add up to 20 s more)" if kind == "llm" and activate == "1" else "") + ", do not cancel...", flush=True)
        r = run(["docker", "exec", "-i", f"stack-{name}-hermes", "python3", "-c", INSIDE, kind, what, activate, model],
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
