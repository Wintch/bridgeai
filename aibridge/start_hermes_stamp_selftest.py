#!/usr/bin/env python3
"""start_hermes.sh: the boot-config stamp follows the script's own config sets, and every plugin in hermes_plugins/ is enabled. python3 start_hermes_stamp_selftest.py"""
import os, re, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, "start_hermes.sh")).read()
fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

want = next(l for l in src.splitlines() if l.startswith('BOOT_CFG_WANT="'))
check("the stamp includes a hash of the script's own config-set lines", 'sets=$(grep -E' in want and "sha256sum" in want)
pat = r"^[[:space:]]*(cfg_set |hermes (config set|plugins enable) )"
def stamp(text):
    open("/tmp/_shs_selftest.sh", "w").write(text)
    return subprocess.run(["bash", "-c", f"grep -E '{pat}' /tmp/_shs_selftest.sh | sha256sum | cut -c1-12"], capture_output=True, text=True).stdout.strip()
base = stamp(src)
check("adding a plugin enable line changes the hash", stamp(src + "\nhermes plugins enable something-new >/dev/null\n") != base)
check("adding a cfg_set line changes the hash", stamp(src + "\ncfg_set foo.bar 1\n") != base)
check("an unrelated comment does not", stamp(src + "\n# just a comment\n") == base)
plugins = [d for d in os.listdir(os.path.join(here, "hermes_plugins")) if os.path.isfile(os.path.join(here, "hermes_plugins", d, "plugin.yaml"))]
for d in plugins:
    check(f"plugin {d} is enabled at boot", f"hermes plugins enable {d} " in src)
    check(f"plugin {d} is copied into the image", f"COPY hermes_plugins/{d} " in open(os.path.join(here, "Dockerfile.hermes-agent")).read())
print("\n".join(fails) or "start_hermes_stamp_selftest: all ok")
sys.exit(1 if fails else 0)
