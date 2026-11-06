#!/usr/bin/env python3
"""skill_packs.py: what is switched off for which choice, and what it writes. A fake `hermes` stands in. No network: python3 skill_packs_selftest.py"""
import contextlib, io, json, os, stat, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
fake = os.path.join(tmp, "hermes")
conf = os.path.join(tmp, "disabled.json")
open(fake, "w").write(f"""#!/usr/bin/env python3
import json, os, sys
f = {conf!r}
a = sys.argv[1:]
if a[:3] == ["config", "get", "skills.disabled"]:
    for n in (json.load(open(f)) if os.path.exists(f) else []): print("  - " + n)
    print("warning: not a recognized key")
elif a[:3] == ["config", "set", "--force"] and a[3] == "skills.disabled":
    open(f, "w").write(a[4])
    open(f + ".calls", "a").write("set\\n")
else:
    sys.exit(2)
""")
os.chmod(fake, 0o755)
os.environ.update(PAQUETES_CATALOG=os.path.join(here, "skill_packs.json"), PAQUETES_STATE=os.path.join(tmp, "paquetes.json"), PAQUETES_HERMES=fake)
sys.path.insert(0, here)
import skill_packs as sp

fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)
def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = sp.main(list(argv))
    return code, buf.getvalue()
def disabled(): return set(json.load(open(conf))) if os.path.exists(conf) else set()
def calls(): return open(conf + ".calls").read().count("set") if os.path.exists(conf + ".calls") else 0

cat = sp.load_catalog()
base, packs = set(cat["base"]["skills"]), cat["packs"]
every = set().union(*[set(p["skills"]) for p in packs.values()])
check("catalog: no skill is both in the base and in a pack", not (base & every))
check("catalog: hermes-agent is in the base (it cannot be switched off)", "hermes-agent" in base)
check("catalog: the base holds what the operator named (browsing, YouTube, speech to text)",
      {"browser-exec", "downloads", "youtube-content", "audio-transcription"} <= base)
check("catalog: notion is in a pack, not in the base", "notion" in packs["oficina"]["skills"] and "notion" not in base)

code, out = run("apply")
check("legacy (no choice file): nothing is disabled and nothing is written", code == 0 and disabled() == set() and calls() == 0 and "unchanged" in out)
code, out = run("list")
check("legacy list says everything is on", code == 0 and "todos activos" in out and out.count("✅") == len(packs))
code, out = run("apply", "--first-boot")
check("first boot: only the base, every pack skill disabled, and the choice is saved",
      code == 0 and disabled() == every and sp.load_state() == set() and "only the base" in out)
check("first boot: no base skill and no essential skill is ever disabled", not (disabled() & base) and "hermes-agent" not in disabled())
n = calls()
run("apply")
check("apply again: unchanged, nothing written", calls() == n)
code, out = run("on", "empleo")
check("on: that pack's skills are enabled, the rest stay off", code == 0 and not (disabled() & {"job-search", "job-portal-scraping"}) and "notion" in disabled() and "empleo" in out)
code, out = run("on", "oficina", "edicion")
check("on several at once", code == 0 and not (disabled() & {"notion", "pdf", "video-processing", "effectcraft"}) and "job-search" not in disabled())
code, out = run("off", "oficina")
check("off: its skills are disabled again, the others keep their state", code == 0 and {"notion", "docx"} <= disabled() and "video-processing" not in disabled())
check("pdf is in empleo too: it stays on while empleo is on, though oficina is off", "pdf" not in disabled())
code, out = run("on", "nope")
check("unknown pack: refused with the list, nothing changed", code == 2 and "No conozco: nope" in out and "empleo" in out and "video-processing" not in disabled())
code, out = run("on")
check("on without a name: refused", code == 2)
code, out = run("set", "creativo")
check("set: exactly that pack", code == 0 and sp.load_state() == {"creativo"} and "image-requests" not in disabled() and "video-processing" in disabled())
code, out = run("set", "--none")
check("set --none: only the base", code == 0 and sp.load_state() == set() and disabled() == every)
# a skill that lives in two packs stays on while either is on
cat2 = json.loads(json.dumps(cat)); cat2["packs"]["empleo"]["skills"].append("pdf")
check("a skill in two packs is disabled only when both are off",
      "pdf" not in sp.disabled_skills(cat2, {"empleo"}) and "pdf" in sp.disabled_skills(cat2, set()) and "pdf" not in sp.disabled_skills(cat2, {"oficina"}))
check("a skill in no pack is never in the disabled list", "location-pin-tracking" not in sp.disabled_skills(cat, set()))
os.unlink(sp.STATE)
open(sp.STATE, "w").write("not json")
check("a broken choice file is treated as no choice (legacy), not a crash", sp.load_state() is None)
# packs that need a key of the person's own (CAPABILITIES.md): the catalog names the service, the listing says what is missing
envf = os.path.join(tmp, "env")
sp.ENVFILE = envf
cat3 = json.loads(json.dumps(cat)); cat3["packs"]["codigos"]["needs"] = [{"service": "abusech", "env": "ABUSECH_AUTH_KEY", "optional": True}]
check("needs: no .env and no variable means the key is missing", sp.missing_keys(cat3["packs"]["codigos"]) != [] and sp.missing_keys(cat3["packs"]["empleo"]) == [])
txt = sp.listing(cat3, {"codigos"})
check("needs: the listing marks the pack and says the key is personal", "🔑 falta tu clave: abusech (opcional)" in txt and "solo las usa tu Hermes" in txt)
check("needs: a catalog with no needs prints no key line (today's catalog)", "🔑" not in sp.listing(cat, {"codigos"}))
open(envf, "w").write("OTHER=1\nABUSECH_AUTH_KEY=\n")
check("needs: an empty value is still missing", sp.missing_keys(cat3["packs"]["codigos"]) != [])
open(envf, "w").write('OTHER=1\nABUSECH_AUTH_KEY="abc123abc123abc123"\n')
check("needs: the key in the stack's .env counts, and the listing stops asking", sp.missing_keys(cat3["packs"]["codigos"]) == [] and "falta tu clave" not in sp.listing(cat3, {"codigos"}))
check("needs: the key value is never printed", "abc123" not in sp.listing(cat3, {"codigos"}))
json.dump(cat3, open(os.path.join(tmp, "cat3.json"), "w")); sp.CATALOG = os.path.join(tmp, "cat3.json"); os.unlink(envf)
sp.save_state(set())
code, out = run("on", "codigos")
check("needs: `on` for a pack with a missing key says so, personal and removable, and still switches it on",
      code == 0 and "Falta tu clave de abusech" in out and "solo la usa tu Hermes" in out and "codigos" in out and "gateway servicios" in out)
code, out = run("on", "empleo")
check("needs: `on` for a pack with no needs adds no key line", code == 0 and "Falta tu clave" not in out)
print("\n".join(fails) or "skill_packs_selftest: all ok")
sys.exit(1 if fails else 0)
