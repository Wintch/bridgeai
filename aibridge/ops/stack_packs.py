#!/usr/bin/env python3
"""stack_packs: choose, per person, which skill packs are on, even while the stack sleeps. Run on VM105 from ~/aibridge. 2026-11-06.

  ops/stack_packs.py list                       who has which packs (a person with no choice yet has everything on)
  ops/stack_packs.py show PERSON                one person: each pack on or off
  ops/stack_packs.py on  PERSON PACK...         switch packs on
  ops/stack_packs.py off PERSON PACK...         switch packs off
  ops/stack_packs.py set PERSON PACK...         exactly these packs (`set PERSON --none` = only the base pack)
  ops/stack_packs.py all PERSON                 write the choice "every pack" (same as before the packs existed, but explicit)

It writes the person's choice file /workdir/.paquetes.json (skill_packs.py; hernik's /workdir is ~/aibridge/user1-workdir, the others
stacks/<name>/workdir), so it works with the container stopped: the stack applies the choice into Hermes's skills.disabled at its next boot
(start_hermes.sh). When the container is running it also runs `paquetes apply` inside, and the person gets it from the next conversation (/new).
Nothing is deleted and no skill file is touched: a pack that is off only stops the skills from being offered to the model.
The catalog is skill_packs.json (copied to ~/aibridge by ops/redeploy_router.sh with the other files the Dockerfile COPYs).
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.environ.get("AIBRIDGE_ROOT", os.path.expanduser("~/aibridge"))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [ROOT, os.path.join(HERE, "..")]
PERSON = re.compile(r"^[a-z][a-z0-9]{1,19}$")


def load_skill_packs():
    try:
        import skill_packs as sp
    except ImportError:
        sys.exit("stack_packs: skill_packs.py not found in ~/aibridge (run ops/redeploy_router.sh, it copies the files the Dockerfile COPYs)")
    for cat in (os.path.join(ROOT, "skill_packs.json"), os.path.join(HERE, "..", "skill_packs.json")):
        if os.path.exists(cat):
            sp.CATALOG = cat
            return sp
    sys.exit("stack_packs: skill_packs.json not found")


def people():
    """name -> (workdir on the host, container). The names come from the waker's list, so a person's stack is never missed."""
    try:
        names = [s["name"] for s in json.load(open(os.path.join(ROOT, "ops", "wake", "stacks.json")))["stacks"]]
    except (OSError, ValueError, KeyError):
        sys.exit("stack_packs: cannot read ops/wake/stacks.json")
    out = {}
    for n in names:
        if n == "hernik":
            out[n] = (os.path.join(ROOT, "user1-workdir"), "aibridge-hermes-agent")
        else:
            out[n] = (os.path.join(ROOT, "stacks", n, "workdir"), f"stack-{n}-hermes")
    return out


def running(container):
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", container], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def mark(sp, cat, state, name):
    return "✅" if name in sp.enabled_packs(cat, state) else "⬜"


def main(argv):
    sp = load_skill_packs()
    cat = sp.load_catalog()
    who = people()
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        names = list(cat["packs"])
        print(f"{'':10s} " + " ".join(n[:6].ljust(6) for n in names))
        for p, (wd, _) in who.items():
            sp.STATE = os.path.join(wd, ".paquetes.json")
            st = sp.load_state()
            print(f"{p:10s} " + " ".join(mark(sp, cat, st, n).ljust(6) for n in names) + ("  (sin elección: todo activo)" if st is None else ""))
        return 0
    if cmd not in ("show", "on", "off", "set", "all") or len(argv) < 2:
        print(__doc__)
        return 2
    person, rest = argv[1], argv[2:]
    if not PERSON.match(person) or person not in who:
        print(f"unknown person {person!r}; the stacks are: {', '.join(who)}")
        return 2
    wd, container = who[person]
    if not os.path.isdir(wd):
        print(f"{wd} does not exist: no such workdir")
        return 2
    sp.STATE = os.path.join(wd, ".paquetes.json")
    st = sp.load_state()
    if cmd == "show":
        print(sp.listing(cat, st))
        return 0
    names = [a for a in rest if not a.startswith("--")]
    if cmd == "all":
        new = set(cat["packs"])
    else:
        if cmd == "set" and "--none" in rest:
            names = []
        elif not names:
            print("which packs? " + ", ".join(cat["packs"]))
            return 2
        bad = [n for n in names if n not in cat["packs"]]
        if bad:
            print("unknown pack: " + ", ".join(bad) + ". Packs: " + ", ".join(cat["packs"]))
            return 2
        cur = sp.enabled_packs(cat, st)
        new = cur | set(names) if cmd == "on" else cur - set(names) if cmd == "off" else set(names)
    if cmd == "on" and st is None:
        print(f"{person} has not chosen yet, so every pack was already on: `on` changes nothing. To give them only some, use `set {person} PACK...`.")
    sp.save_state(new)
    print(f"{person}: packs on = {', '.join(sorted(new)) or 'only the base'} (written to {sp.STATE})")
    if running(container):
        r = subprocess.run(["docker", "exec", container, "paquetes", "apply"], capture_output=True, text=True)
        out = (r.stdout or r.stderr).strip().splitlines()
        print(f"{container} is running: {out[-1] if out else 'no output'}; the person gets it from the next conversation (/new)"
              if r.returncode == 0 else
              f"{container} is running but `paquetes apply` failed ({out[-1] if out else 'no output'}): its image may not have `paquetes` yet; the choice applies at the next boot of an image that has it")
    else:
        print(f"{container} is stopped: the choice is applied at its next boot")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
