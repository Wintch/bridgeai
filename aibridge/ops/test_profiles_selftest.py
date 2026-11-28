#!/usr/bin/env python3
"""Offline checks for ops/test_profiles.py: defaults, validation against the feature map and the gateway, the choice per deploy, and the real
profiles file. Run: python3 -I ops/test_profiles_selftest.py"""
import json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_profiles as tp  # noqa: E402

FAIL = []


def chk(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


d = tempfile.mkdtemp()
f = os.path.join(d, "p.json")
json.dump({"defaults": {"image": "shipped", "caps": {"cpus": 1, "memory_mb": 1024, "pids": 128, "run_minutes": 5, "gpu": False},
                        "network": ["model-route"], "reset": ["new_session", "load_persona"]},
           "profiles": [{"id": "a", "kind": "stack", "bench": "chat", "ready": True, "features": ["f1", "f2"], "caps": {"memory_mb": 2048},
                         "persona": {"langs": ["es"], "fields": ["name"]}, "tasks": [{"id": "t", "es": "x"}]},
                        {"id": "b", "kind": "scripts", "ready": True, "features": ["f2"], "network": [], "scripts": ["gateway ayuda"],
                         "persona": {"langs": ["es"], "fields": ["name"]}}]}, open(f, "w"))
P = tp.load(f)
chk("load: caps merged key by key", P[0]["caps"], {"cpus": 1, "memory_mb": 2048, "pids": 128, "run_minutes": 5, "gpu": False})
chk("load: network/reset/image from the defaults unless the profile sets them", (P[0]["network"], P[1]["network"], P[1]["reset"], P[1]["image"]),
    (["model-route"], [], ["new_session", "load_persona"], "shipped"))
FE = [{"id": "f1"}, {"id": "f2"}, {"id": "f3"}]
chk("validate: a good set has no problem", tp.validate(P, FE, {"ayuda", "estado"}), [])
bad = [dict(P[0], id="a"), dict(P[0], kind="vm", features=["nope"], stack={"gateways": ["nada"], "skills": ["SKILL_none.md"]},
                                 persona={"langs": [], "fields": ["Bad Field"]}, reset=["format_disk"], ready=False, tasks=[{"id": ""}],
                                 caps={"cpus": 0, "memory_mb": 99999, "pids": 1, "run_minutes": 999})]
probs = tp.validate(bad, FE, {"ayuda"})
for want in ("duplicate id", "kind 'vm'", "feature 'nope'", "gateway verb 'nada'", "skill SKILL_none.md", "persona field 'Bad Field'",
             "persona has no language", "reset step 'format_disk'", "task without id", "does not say what it needs", "cap cpus", "above the bench"):
    chk(f"validate: names the problem ({want})", any(want in p for p in probs), True)
G = [{"id": "chat-1", "bench": "chat", "ready": True, "features": ["lang"]},
     {"id": "chat-2", "bench": "chat", "ready": True, "features": ["lang", "note"]},
     {"id": "solo", "ready": True, "features": ["note"]},
     {"id": "later", "ready": False, "features": ["desk"]}]
run, left = tp.for_features(["lang", "note", "desk"], G)
chk("for_features: one profile per bench group (the one covering most), every ungrouped one, the uncovered features named",
    ([p["id"] for p in run], left), (["chat-2", "solo"], ["desk"]))
chk("for_features: nothing touched, nothing to run", tp.for_features([], G), ([], []))
# the real files
real = tp.load()
feats = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "features.json"), encoding="utf-8"))["features"]
chk("the real profiles validate against the real feature map and gateway", tp.validate(real, feats, tp.gateway_verbs()), [])
chk("the gateway's verbs are read (escritorio, estado, qr)", {"escritorio", "estado", "qr"} <= tp.gateway_verbs(), True)
chk("no profile sends a person's data: every persona is generated (fields only, no values)",
    all(set(p["persona"]) <= {"langs", "fields"} for p in real), True)
print("test_profiles_selftest: " + ("all ok" if not FAIL else "FAILED: " + "; ".join(FAIL)))
sys.exit(1 if FAIL else 0)
