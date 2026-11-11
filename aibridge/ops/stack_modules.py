#!/usr/bin/env python3
"""stack_modules: choose, per person, which modules are switched on (jobfinder, budgetai, youtube, news, ...). Run on the Docker host from ~/aibridge.

  ops/stack_modules.py list                      who has what (and what each module needs)
  ops/stack_modules.py add PERSON MODULE...      switch modules on for a person
  ops/stack_modules.py remove PERSON MODULE...   switch them off (their data is never deleted)
  ops/stack_modules.py pending                   modules people asked for (`hub modules request NAME`) and nobody switched on yet
  ops/stack_modules.py init                      first use: every person already attached to the hub gets every module (what they can do today)

The registry is hubdata/modules.json, written only here (no stack mounts it). Until it exists the hub restricts nothing; once it exists the hub refuses what a
person's modules do not cover: a subscription of a kind they do not have, a job profile without «jobfinder». What the hub does NOT do is install a
shared project: for a module with a project (jobfinder, budgetai) `add` tells you the second step, adding the stack to that project's "stacks" list in the
desktop's projects.json so ops/project_sync.py puts it in their workdir. `remove` stops the hub side only: the project files stay in their workdir (the
person's own layer is theirs) and the project sync keeps updating them until you take the stack out of that list.
The catalog (hub/modules_catalog.json in the repo, ~/aibridge/hub/ on the VM) says what each module covers.
"""
import json
import os
import re
import sys
import tempfile

ROOT = os.environ.get("AIBRIDGE_ROOT", os.path.expanduser("~/aibridge"))
DATA = os.environ.get("HUB_DATA", os.path.join(ROOT, "hubdata"))
HERE = os.path.dirname(os.path.abspath(__file__))
CATALOGS = [os.path.join(ROOT, "hub", "modules_catalog.json"), os.path.join(HERE, "..", "hub", "modules_catalog.json")]
PERSON = re.compile(r"^[a-z][a-z0-9]{1,19}$")


def catalog():
    for p in CATALOGS:
        try:
            return json.load(open(p))["modules"]
        except (OSError, ValueError, KeyError):
            continue
    sys.exit("stack_modules: modules_catalog.json not found (run ops/hub_install.sh first)")


def attached():
    d = os.path.join(DATA, "people")
    try:
        return sorted(p for p in os.listdir(d) if PERSON.match(p) and os.path.isfile(os.path.join(d, p, ".attached")))
    except OSError:
        return []


def load():
    path = os.path.join(DATA, "modules.json")
    if not os.path.exists(path):
        return None
    try:
        people = json.load(open(path))["people"]
        assert isinstance(people, dict)
        return {p: sorted(m) for p, m in people.items()}
    except (OSError, ValueError, KeyError, AssertionError, TypeError):
        sys.exit(f"stack_modules: {path} exists but cannot be read; fix it by hand (it is plain JSON: {{\"people\": {{\"name\": [\"module\", ...]}}}})")


def save(people):
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "modules.json")
    fd, tmp = tempfile.mkstemp(dir=DATA, prefix=".modules.")
    with os.fdopen(fd, "w") as f:
        json.dump({"version": 1, "people": {p: sorted(set(m)) for p, m in sorted(people.items())}}, f, indent=1)
        f.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def check(person, mods, cat):
    if not PERSON.match(person):
        sys.exit(f"stack_modules: '{person}' is not a stack name")
    if person not in attached():
        sys.exit(f"stack_modules: {person} is not attached to the hub (ops/hub_attach.sh {person} first)")
    bad = [m for m in mods if m not in cat]
    if bad:
        sys.exit(f"stack_modules: unknown module(s) {', '.join(bad)} (known: {', '.join(sorted(cat))})")


def main(argv):
    cat = catalog()
    cmd = argv[0] if argv else "list"
    reg = load()
    if cmd == "list":
        if reg is None:
            print("hubdata/modules.json does not exist: the hub restricts nothing yet (every attached person can use every module). `init` creates it.")
        print(f"{'':10}" + " ".join(f"{m:9}" for m in sorted(cat)))
        for p in attached():
            have = set(reg.get(p, ())) if reg is not None else set(cat)
            print(f"{p:10}" + " ".join(f"{'on' if m in have else '-':9}" for m in sorted(cat)))
        print()
        for m, spec in sorted(cat.items()):
            print(f"{m}: {spec['label']}" + (f"  [project: {spec['project']}]" if spec.get("project") else ""))
        return 0
    if cmd == "init":
        if reg is not None:
            sys.exit("stack_modules: modules.json already exists; use add / remove")
        save({p: list(cat) for p in attached()})
        print(f"created modules.json: {len(attached())} person(s) with every module (what they could do before). Now `remove` what they do not need.")
        return 0
    if cmd in ("add", "remove"):
        if len(argv) < 3:
            sys.exit(__doc__)
        person, mods = argv[1], argv[2:]
        check(person, mods, cat)
        if reg is None:
            sys.exit("stack_modules: run `init` first: creating the file with only one person would lock everybody else out")
        have = set(reg.get(person, ()))
        have = have | set(mods) if cmd == "add" else have - set(mods)
        reg[person] = sorted(have)
        save(reg)
        print(f"{person}: {', '.join(sorted(have)) or '(none)'}")
        for m in mods:
            proj = cat[m].get("project")
            if cmd == "add" and proj:
                print(f"  {m}: also add \"{person}\" to the \"stacks\" list of project \"{proj}\" in the desktop's projects.json (private) so ops/project_sync.py installs it in their workdir.")
            if cmd == "remove" and proj:
                print(f"  {m}: their {proj} files stay in their workdir and keep being updated until you take \"{person}\" out of that project's \"stacks\" list.")
        return 0
    if cmd == "pending":
        import sqlite3
        db_path = os.path.join(DATA, "state", "hub.db")
        if not os.path.exists(db_path):
            print("no hub.db yet")
            return 0
        db = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        rows = db.execute("SELECT person, detail, created FROM requests WHERE op='module_request' AND status='pending' ORDER BY id").fetchall()
        if not rows:
            print("nobody is waiting for a module")
        for person, name, ts in rows:
            print(f"{person} asks for {name}: ops/stack_modules.py add {person} {name}")
        return 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
