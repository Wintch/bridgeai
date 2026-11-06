#!/usr/bin/env python3
"""security-overrides.txt: every line is name==version with a sha256 hash, and the Dockerfile copies and applies it. No network: python3 security_overrides_selftest.py"""
import os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

lines = [l.strip() for l in open(os.path.join(here, "security-overrides.txt")) if l.strip() and not l.startswith("#")]
check("there is at least one override", len(lines) >= 1)
check("each line is name==exact-version --hash=sha256:<64 hex> (nothing unhashed, no ranges)",
      all(re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][A-Za-z0-9.]*\s+--hash=sha256:[0-9a-f]{64}", l) for l in lines))
check("no package twice", len({l.split("==")[0].lower() for l in lines}) == len(lines))
docker = open(os.path.join(here, "Dockerfile.hermes-agent")).read()
check("the Dockerfile COPYs the file", "COPY security-overrides.txt /tmp/security-overrides.txt" in docker)
check("it installs with hashes required and no dependencies", "--require-hashes --no-deps -r /tmp/security-overrides.txt" in docker)
# the versions the build asserts must be the ones in the file
want = dict(l.split()[0].split("==") for l in lines)
check("the build asserts the versions of the file (jwt, certifi)",
      f"jwt.__version__ == '{want.get('pyjwt')}'" in docker and f"certifi.__version__ == '{want.get('certifi')}'" in docker)
print("\n".join(fails) or "security_overrides_selftest: all ok")
sys.exit(1 if fails else 0)
