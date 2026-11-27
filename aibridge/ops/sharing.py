#!/usr/bin/env python3
"""sharing: what each person lets us look at, read in one place (DATA_SHARING.md sections 2, 4 and 5). Run on the Docker host
from ~/aibridge.

  ops/sharing.py list                  every person in the registry: level, tester since, their stacks
  ops/sharing.py show PERSON           one person, as JSON
  ops/sharing.py review-flags STACK    the flags ops/chat_review.py needs for that stack (used by ops/review_stack.sh):
                                       "--own", "--tester-since YYYY-MM-DD", "" (the person's own level decides) or "SKIP"

Collection is gated at the source: every collector asks `sharing_level(person)` (or `for_stack(stack)`) before it reads anything.

The registry is ops/testers.json (git-ignored; shape in ops/testers.json.example). It says who the operator is, who is a tester and
since when, and which stacks and places belong to each person. A person with several stacks counts once.

The level itself is still the per-stack choice the person made in the bot (/feedback data, opinion.py), stored in the stack's
/workdir/.compartir.json; no file means "uso". A person with several stacks gets the most careful of their choices: a "nada" in
any of them is "nada" for the person. A person in the registry with no stack (a place only, no bot) cannot choose yet, so they read
as "nada", tester or not, until the person record of DATA_SHARING.md section 5 exists. A person or stack the registry does not know
reads as "nada" too: when in doubt, collect nothing.
"""
import datetime
import json
import os
import sys

ROOT = os.environ.get("AIBRIDGE_ROOT", os.path.expanduser("~/aibridge"))
LEVELS = ("nada", "uso", "todo")          # most careful first
MAIN_STACK = "hernik"                     # the main stack's /workdir is ~/aibridge/user1-workdir (same as ops/stack_packs.py)


def registry_path(root=None):
    return os.path.join(root or ROOT, "ops", "testers.json")


def load_registry(root=None):
    """{"people": {person: {...}}}; a missing or broken file is an empty registry (everyone reads as "nada")."""
    try:
        reg = json.load(open(registry_path(root)))
    except (OSError, ValueError):
        return {"people": {}}
    people = reg.get("people") if isinstance(reg, dict) else None
    return {"people": people if isinstance(people, dict) else {}}


def stack_workdir(stack, root=None):
    root = root or ROOT
    if stack == MAIN_STACK:
        return os.path.join(root, "user1-workdir")
    return os.path.join(root, "stacks", stack, "workdir")


def stack_choice(stack, root=None):
    """The level the person chose in this stack's bot; "uso" when they never chose (or the file is unreadable)."""
    try:
        v = json.load(open(os.path.join(stack_workdir(stack, root), ".compartir.json"))).get("level")
    except (OSError, ValueError, AttributeError):
        return "uso"
    return v if v in LEVELS else "uso"


def a_date(v):
    """The value when it is a real YYYY-MM-DD date, else None (a typo must not make someone a tester)."""
    try:
        return datetime.date.fromisoformat(v).isoformat() if isinstance(v, str) and len(v) == 10 else None
    except ValueError:
        return None


def sharing_level(person, root=None, registry=None):
    """{"person", "known", "level", "operator", "tester_since", "stacks", "places"} for one person."""
    reg = registry if registry is not None else load_registry(root)
    p = reg["people"].get(person)
    if not isinstance(p, dict):
        return {"person": person, "known": False, "level": "nada", "operator": False, "tester_since": None,
                "stacks": [], "places": []}
    stacks = [s for s in p.get("stacks") or [] if isinstance(s, str)]
    places = [s for s in p.get("places") or [] if isinstance(s, str)]
    choices = [stack_choice(s, root) for s in stacks]
    level = min(choices, key=LEVELS.index) if choices else "nada"
    return {"person": person, "known": True, "level": level, "operator": bool(p.get("operator")),
            "tester_since": a_date(p.get("tester_since")),
            "stacks": stacks, "places": places}


def owner_of(stack, registry):
    for name, p in registry["people"].items():
        if isinstance(p, dict) and stack in (p.get("stacks") or []):
            return name
    return None


def for_stack(stack, root=None, registry=None):
    reg = registry if registry is not None else load_registry(root)
    owner = owner_of(stack, reg)
    return sharing_level(owner, root, reg) if owner else sharing_level(f"<stack {stack}>", root, {"people": {}})


def review_flags(stack, root=None, registry=None):
    """What ops/chat_review.py may do on this stack. "nada" always wins, over the operator's own stacks too."""
    s = for_stack(stack, root, registry)
    if s["level"] == "nada":
        return "SKIP"
    if s["operator"]:
        return "--own"
    if s["tester_since"]:
        return f"--tester-since {s['tester_since']}"
    return ""


def main(argv):
    if len(argv) == 1 and argv[0] == "list":
        reg = load_registry()
        if not reg["people"]:
            print(f"no registry at {registry_path()} (see ops/testers.json.example): everyone reads as nada")
        for name in sorted(reg["people"]):
            s = sharing_level(name, registry=reg)
            who = "operator" if s["operator"] else f"tester since {s['tester_since']}" if s["tester_since"] else "-"
            print(f"{name:12s} {s['level']:5s} {who:24s} stacks: {', '.join(s['stacks']) or '-'}"
                  f"   places: {', '.join(s['places']) or '-'}")
        return 0
    if len(argv) == 2 and argv[0] == "show":
        print(json.dumps(sharing_level(argv[1]), indent=1))
        return 0
    if len(argv) == 2 and argv[0] == "review-flags":
        print(review_flags(argv[1]))
        return 0
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
