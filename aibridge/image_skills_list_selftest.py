#!/usr/bin/env python3
"""Dockerfile.hermes-agent: the baked list of the image's skills (/app/image-skills.json) is written AFTER every step that writes under
/root/.hermes/skills. A skill copied later was missing from it, so start_hermes.sh took the persisted copy as one the bot made and an old
version kept winning over the image's on every stack (design-guide, frontend-design, ascii-art; found 2026-11-28).
No network, no Docker: python3 -I image_skills_list_selftest.py"""
import os, sys

here = os.path.dirname(os.path.abspath(__file__))
lines = open(os.path.join(here, "Dockerfile.hermes-agent"), encoding="utf-8").read().split("\n")
fails = []
def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(f"{name}: {detail}")

baked = [n for n, l in enumerate(lines) if "/app/image-skills.json" in l and l.startswith("RUN ")]
check("exactly one step writes the baked list", len(baked) == 1, str(baked))
writes = [n for n, l in enumerate(lines) if "/root/.hermes/skills" in l and not l.lstrip().startswith("#")
          and n not in baked and not l.startswith(("ENV ", "ARG "))]
if baked:
    late = [n + 1 for n in writes if n > baked[0]]
    check("no step touches /root/.hermes/skills after the baked list", not late, f"Dockerfile lines {late}")
print("\n".join(fails) or "image_skills_list_selftest: all ok")
sys.exit(1 if fails else 0)
