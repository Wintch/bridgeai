#!/usr/bin/env python3
"""Skills split into a core SKILL.md and references/ (skill_refs/<skill>/): every `references/<file>` the core names exists, every
reference file is named by the core (else the model never finds it), the image copies the folder next to the core, and the core stays
small (it is sent on every model call while the skill is loaded; job-search was 31.6k chars, 2026-11-28).
No network: python3 -I skill_refs_selftest.py"""
import os, re, sys

here = os.path.dirname(os.path.abspath(__file__))
fails = []
def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(f"{name}: {detail}")

# skill name -> (core file in the repo, folder under /root/.hermes/skills, max core chars)
SPLIT = {
    "job-search": ("SKILL_job_search.md", "devops/job-search", 12000),
    "website": ("SKILL_website.md", "productivity/website", 11000),
}
docker = open(os.path.join(here, "Dockerfile.hermes-agent"), encoding="utf-8").read()
for name, (core_file, dest, cap) in SPLIT.items():
    core = open(os.path.join(here, core_file), encoding="utf-8").read()
    refdir = os.path.join(here, "skill_refs", name)
    have = sorted(f for f in os.listdir(refdir) if f.endswith(".md")) if os.path.isdir(refdir) else []
    named = sorted(set(re.findall(r"references/([a-z0-9-]+\.md)", core)))
    check(f"{name}: every reference the core names exists", set(named) <= set(have), str(sorted(set(named) - set(have))))
    check(f"{name}: every reference file is named by the core", set(have) <= set(named), str(sorted(set(have) - set(named))))
    check(f"{name}: the core says how to read them", f'skill_view("{name}", "references/<file>")' in core)
    check(f"{name}: core under {cap} chars", len(core) <= cap, str(len(core)))
    check(f"{name}: the image copies skill_refs/{name}/ into the skill's references/",
          f"COPY skill_refs/{name}/ /root/.hermes/skills/{dest}/references/" in docker)
print("\n".join(fails) or "skill_refs_selftest: all ok")
sys.exit(1 if fails else 0)
