#!/usr/bin/env python3
"""The test machines' profiles (ops/test_profiles.json, ops/FEATURE_MAP.md §1b): read them with their defaults, check them against the
feature map and the code, and pick the ones a deploy needs.

  test_profiles.py list                      every profile: kind, bench group, ready, the features it covers
  test_profiles.py show ID                   one profile with its defaults filled in (JSON)
  test_profiles.py validate                  the problems found (exit 1 when any)
  test_profiles.py for-deploy PREV REV       the profiles to run for a deploy: the ready ones covering the features it touched (ops/change_kind.py),
                                             one bench group once, and the touched features no ready profile covers

load / validate / for_features are pure apart from reading the files (tested offline).
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AIB = os.path.dirname(HERE)
PROFILES = os.path.join(HERE, "test_profiles.json")
KINDS = ("stack", "place", "scripts")
RESETS = ("new_session", "wipe_workdir", "wipe_memory", "load_persona")
FIELD = re.compile(r"^[a-z_]+(:\d{1,2})?$")


def load(path=PROFILES):
    """[profile] with the defaults filled in (caps merged key by key; network, reset and image replaced when the profile sets them)."""
    d = json.load(open(path, encoding="utf-8"))
    base = d.get("defaults", {})
    out = []
    for p in d.get("profiles", []):
        q = dict(p)
        q["caps"] = {**base.get("caps", {}), **p.get("caps", {})}
        for k in ("network", "reset", "image"):
            q.setdefault(k, base.get(k))
        out.append(q)
    return out


def gateway_verbs(path=os.path.join(AIB, "gateway.py")):
    """The verbs gateway.py's main() knows (its cmds table)."""
    m = re.search(r"cmds = \{(.*?)\}\n", open(path, encoding="utf-8").read(), re.S)
    return set(re.findall(r'"([a-z][a-z-]*)": cmd_', m.group(1))) if m else set()


def validate(profiles, features, verbs, repo=AIB):
    """[problem] of the profiles against the feature map (ids of features.json), the gateway's verbs and the skills in the repo. Pure apart
    from checking that a skill file exists."""
    out, ids = [], set()
    fids = {f["id"] for f in features}
    for p in profiles:
        pid = p.get("id", "?")
        if pid in ids:
            out.append(f"{pid}: duplicate id")
        ids.add(pid)
        if p.get("kind") not in KINDS:
            out.append(f"{pid}: kind {p.get('kind')!r} is not one of {KINDS}")
        for f in p.get("features", []):
            if f not in fids:
                out.append(f"{pid}: feature {f!r} is not in features.json")
        if not p.get("features"):
            out.append(f"{pid}: covers no feature")
        st = p.get("stack", {})
        for v in st.get("gateways", []):
            if v not in verbs:
                out.append(f"{pid}: gateway verb {v!r} does not exist")
        for sk in st.get("skills", []):
            if not os.path.isfile(os.path.join(repo, sk)):
                out.append(f"{pid}: skill {sk} not found")
        for fld in p.get("persona", {}).get("fields", []):
            if not FIELD.match(fld):
                out.append(f"{pid}: persona field {fld!r} is not name or name:count")
        if not p.get("persona", {}).get("langs"):
            out.append(f"{pid}: the persona has no language")
        for r in p.get("reset", []):
            if r not in RESETS:
                out.append(f"{pid}: reset step {r!r} unknown")
        if p.get("kind") == "scripts" and not p.get("scripts"):
            out.append(f"{pid}: a scripts machine with no scripts")
        if p.get("kind") != "scripts" and not p.get("tasks") and not p.get("scripts"):
            out.append(f"{pid}: nothing to run (no task, no script)")
        for t in p.get("tasks", []):
            if not t.get("id") or not t.get("es"):
                out.append(f"{pid}: a task without id or text")
        if not p.get("ready") and not p.get("needs"):
            out.append(f"{pid}: not ready but does not say what it needs")
        c = p.get("caps", {})
        for k in ("cpus", "memory_mb", "pids", "run_minutes"):
            if not isinstance(c.get(k), (int, float)) or c[k] <= 0:
                out.append(f"{pid}: cap {k} missing or not positive")
        if c.get("memory_mb", 0) > 4096 or c.get("run_minutes", 0) > 60:
            out.append(f"{pid}: caps above the bench's limits (4 GB, 60 min)")
        if c.get("gpu") and p.get("ready") and "night" not in (p.get("needs") or "") and p.get("kind") != "place":
            out.append(f"{pid}: a GPU profile must run in the night window")
    return out


def for_features(touched, profiles):
    """(profiles to run, features no ready profile covers) for the touched feature ids. One profile per bench group (the one covering most of
    the touched features), plus every profile with no group that covers something. Pure."""
    t = set(touched)
    ready = [p for p in profiles if p.get("ready") and t & set(p.get("features", []))]
    run, groups = [], {}
    for p in ready:
        g = p.get("bench")
        if g is None:
            run.append(p)
        elif g not in groups or len(t & set(p["features"])) > len(t & set(groups[g]["features"])):
            groups[g] = p
    run += list(groups.values())
    covered = set().union(*(set(p["features"]) for p in run)) if run else set()
    return sorted(run, key=lambda p: p["id"]), sorted(t - covered)


def main(argv):
    profiles = load()
    if argv[:1] == ["list"]:
        for p in profiles:
            print(f"{p['id']:<15} {p['kind']:<8} bench={p.get('bench') or '-':<6} {'ready' if p.get('ready') else 'NOT READY'}  "
                  f"{', '.join(p['features'])}" + ("" if p.get("ready") else f"  (needs {p.get('needs')})"))
        return 0
    if len(argv) == 2 and argv[0] == "show":
        p = next((p for p in profiles if p["id"] == argv[1]), None)
        if not p:
            print(f"no profile {argv[1]}")
            return 1
        print(json.dumps(p, ensure_ascii=False, indent=1))
        return 0
    if argv[:1] == ["validate"]:
        feats = json.load(open(os.path.join(HERE, "features.json"), encoding="utf-8"))["features"]
        probs = validate(profiles, feats, gateway_verbs())
        print("\n".join(probs) if probs else f"{len(profiles)} profiles: ok")
        return 1 if probs else 0
    if len(argv) == 3 and argv[0] == "for-deploy":
        sys.path.insert(0, HERE)
        import change_kind
        pk = change_kind.pack(change_kind.git("diff", "--name-only", f"{argv[1]}..{argv[2]}"),
                              json.load(open(change_kind.FEATURES, encoding="utf-8")))
        bot_feats = [f for f in pk["features"] if f in {x["id"] for x in pk["bot_tasks"]} | {x["id"] for x in pk["not_ready"]}]
        run, left = for_features(bot_feats, profiles)
        print("profiles to run: " + (", ".join(f"{p['id']} ({p['kind']}{', bench ' + p['bench'] if p.get('bench') else ''})" for p in run) or "none"))
        if left:
            print("touched, no ready profile yet: " + ", ".join(left))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
