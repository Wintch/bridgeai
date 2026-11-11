#!/usr/bin/env python3
"""Give an existing per-person stack one of the optional SERVICES of `gateway servicios` (zabbix, audd, groq, tmdb, ...), validated and
stored by the gateway itself, exactly as the keys page does it (run on the Docker host from ~/aibridge):

  printf '%s\\n' "$VALUE" | ops/stack_service.py <stack> <service>        save: the value on stdin, one line
  ops/stack_service.py <stack> <service> --remove                        take the person's own value out again

It runs `gateway servicios guardar <service>` (or `quitar`) INSIDE the stack's Hermes container, so the real call that proves the value
(a Zabbix API answer, a provider's key check...) is made from where the bot will use it, and the answer printed is the gateway's own.
Examples (the value is the one the service's card on the keys page takes; `gateway servicios` in the stack lists them):
  zabbix   "https://zabbix.example.com TOKEN [HOST GROUP]"   the address, a READ-ONLY API token (Zabbix: Users -> API tokens, a user
                                                             with a role of type User) and optionally the host group to look at first
  groq     the key        audd  the token        tmdb  the key        acrcloud  host:access key:access secret
The value travels on STDIN only (never on the command line: shell history, `ps`), is never printed (the gateway shows the last 4
characters of the key at most; anything of the value that comes back is scrubbed), and is never logged. Use a hidden prompt:
  read -rsp 'value: ' V; echo; printf '%s\\n' "$V" | ops/stack_service.py NAME zabbix; unset V
If the stack is asleep this starts its Hermes container itself and waits for it (1-3 minutes, it says so); the waker puts it back to
sleep after the idle time. The check is made from the container, so the service has to be reachable from it (a Zabbix on the LAN needs
the stack's firewall to allow that address). Exit codes: 0 saved or removed, 1 the gateway refused it (its sentence says why), 2 usage,
3 the stack could not be started. An OK that ends with "Ojo: ..." was saved but something could not be verified (for Zabbix: the token's role
could not be read, so check in Zabbix that it belongs to a read-only User role).
Keys for the AI providers (gemini, openrouter, huggingface, nvidia) are not services: use ops/stack_keys.py.
Test: python3 ops/stack_service_selftest.py
"""
import re
import subprocess
import sys

import stack_keys as sk   # the same container helpers: running, wake, hold_awake (the waker's busy marker)

SVC_RE = re.compile(r"[a-z]{2,20}")
MAX_VALUE = 700


def scrub(text, value):
    """The gateway never prints the value; belt and braces: the whole value and each long part of it (the token, the address) go out."""
    for part in sorted({value, *value.split()}, key=len, reverse=True):
        if len(part) >= 8:
            text = text.replace(part, "<value>")
    return text


def main(argv, stdin=None, run=subprocess.run, running=sk.container_running, wake=sk.container_wake, hold=sk.hold_awake):
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if len(args) != 2 or flags - {"--remove"}:
        print(__doc__, file=sys.stderr)
        return 2
    name, svc = args
    if not sk.NAME_RE.fullmatch(name):
        print("stack name: a-z0-9, 2-20 chars", file=sys.stderr)
        return 2
    if not SVC_RE.fullmatch(svc):
        print("service: lower-case letters, 2-20 (the list: `gateway servicios` inside the stack)", file=sys.stderr)
        return 2
    remove = "--remove" in flags
    value = ""
    if not remove:
        value = ((stdin or sys.stdin).readline() or "").strip()
        if not value or len(value) > MAX_VALUE or re.search(r"[\x00-\x08\x0a-\x1f\x7f]", value):
            print(f"the value must come on stdin: one line, up to {MAX_VALUE} characters", file=sys.stderr)
            return 2
    with hold(name):
        if not running(name):
            print(f"stack-{name}-hermes is asleep: starting it (the first boot can take 1-3 minutes; the waker puts it back to sleep "
                  "after its idle time)...", flush=True)
            if not wake(name):
                print(f"could not start stack-{name}-hermes or it did not answer /health in 5 minutes: check `docker logs "
                      f"stack-{name}-hermes`; nothing was stored", file=sys.stderr)
                return 3
        if not remove:
            print(f"checking the {svc} value with the service and storing it in {name}'s Hermes; this takes up to a minute, do not cancel...", flush=True)
        r = run(["docker", "exec", "-i", f"stack-{name}-hermes", "gateway", "servicios", "quitar" if remove else "guardar", svc],
                input="" if remove else value + "\n", capture_output=True, text=True, timeout=240)
    out = scrub(((r.stdout or "").strip() or (r.stderr or "").strip()), value)
    if not out:
        print(f"FAIL: no answer from the gateway in the container (rc {r.returncode}); the value was not shown or logged", file=sys.stderr)
        return 1
    ok = r.returncode == 0
    print(("OK: " if ok else "FAIL: ") + out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
