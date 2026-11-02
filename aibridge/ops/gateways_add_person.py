#!/usr/bin/env python3
"""Add a person to the operator's master gateway list from an existing one (run on VM105 from ~/aibridge).

  python3 ops/gateways_add_person.py <new stack> --like <existing stack> [--lang es|ru|en] [--dry-run]

Copies what is shared by design (the speech/GPU hosts the person may use, cloud_direct and the cloud model order) and
leaves out what belongs to one person: their named TTS voices, their Claude box, their web-deploy settings. The master
(ops/gateways.json, never in git) is backed up as ops/gateways.json.bak-<date> first; nothing is written when the new
name is already there. Afterwards: python3 ops/gateways_sync.py writes stacks/<new>/gateways/gateways.json.
Test: python3 ops/gateways_add_person.py --selftest
"""
import copy
import datetime
import json
import os
import re
import shutil
import sys
import tempfile

PERSONAL = ("tts_voice", "tts_voices", "claude", "web", "lang")
NAME_RE = re.compile(r"[a-z][a-z0-9]{1,19}")


def add_person(master, new, like, lang=None):
    stacks = master.get("stacks") or {}
    if new in stacks:
        raise SystemExit(f"{new} is already in the master list: nothing to do")
    if like not in stacks:
        raise SystemExit(f"{like} is not in the master list (stacks: {', '.join(stacks)})")
    entry = {k: copy.deepcopy(v) for k, v in stacks[like].items() if k not in PERSONAL}
    if lang in ("ru", "en"):
        entry["lang"] = lang
    out = copy.deepcopy(master)
    out["stacks"][new] = entry
    return out


def main(argv):
    if "--selftest" in argv:
        return selftest()
    args = [a for a in argv if not a.startswith("--")]
    opts = {}
    i = 0
    while i < len(argv):
        if argv[i] in ("--like", "--lang"):
            opts[argv[i][2:]] = argv[i + 1]
            args = [a for a in args if a != argv[i + 1]]
            i += 1
        i += 1
    if len(args) != 1 or "like" not in opts or not NAME_RE.fullmatch(args[0]):
        print(__doc__, file=sys.stderr)
        return 2
    path = os.path.join("ops", "gateways.json")
    master = json.load(open(path))
    new = add_person(master, args[0], opts["like"], opts.get("lang"))
    shown = new["stacks"][args[0]]
    print(f"{args[0]}: " + json.dumps({k: (v if k != "cloud_order" else f"{len(v)} models") for k, v in shown.items()}))
    if "--dry-run" in argv:
        print("dry run: nothing written")
        return 0
    shutil.copy2(path, f"{path}.bak-{datetime.date.today():%Y%m%d}")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(new, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    print("written; next: python3 ops/gateways_sync.py")
    return 0


def selftest():
    m = {"hosts": ["h1"], "stacks": {"a": {"voice": ["h1"], "gpu": ["h1"], "tts_voice": "a-es", "tts_voices": ["a-es"],
                                         "cloud_direct": True, "cloud_order": ["x", "y"], "claude": [{"name": "c"}],
                                         "web": {"repo": "r"}, "lang": "ru"}}}
    n = add_person(m, "b", "a")
    e = n["stacks"]["b"]
    ok = [e == {"voice": ["h1"], "gpu": ["h1"], "cloud_direct": True, "cloud_order": ["x", "y"]},
          n["stacks"]["a"] == m["stacks"]["a"], "b" not in m["stacks"],
          add_person(m, "b", "a", "ru")["stacks"]["b"]["lang"] == "ru",
          "lang" not in add_person(m, "b", "a", "es")["stacks"]["b"]]
    e["cloud_order"].append("z")
    ok.append(m["stacks"]["a"]["cloud_order"] == ["x", "y"])
    for bad in (lambda: add_person(m, "a", "a"), lambda: add_person(m, "c", "zzz")):
        try:
            bad()
            ok.append(False)
        except SystemExit:
            ok.append(True)
    print("selftest:", "all passed" if all(ok) else f"FAILED {ok}")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
