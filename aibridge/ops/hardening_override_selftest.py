#!/usr/bin/env python3
"""Selftest: stacks/hardening.override.yml merges onto the REAL person-stack template the way ops/hardening_trial_stack.sh
needs (the hermes service gets the profile, keeps its cpu and memory limits, no other service changes), matches the profile
ops/container_hardening.py checks, and the trial script refuses names that are not 'hardtest*'.
Needs `docker compose` (renders the files, starts nothing); skipped when it is not installed.
Run: python3 ops/hardening_override_selftest.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import container_hardening as ch  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


ENV = """STACK_NAME=hardtest
STACK_DIR=/tmp/x
REPO_DIR=/tmp/r
LAN_IP=127.0.0.1
PUBLIC_HOST=hardtest.invalid
STACK_SUBNET=172.28.99.0/24
WEB_PORT=3999
DASH_PORT=9999
HERMES_API_KEY=hk-x
DASH_USER=u
DASH_PASSWORD=p
DASH_SECRET=s
ADMIN_EMAIL=a@b.c
OPENWEBUI_SECRET_KEY=k
OPENWEBUI_ADMIN_PASSWORD=p
NVIDIA_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USERS=
"""


def render(files, env_path):
    cmd = ["docker", "compose", "-p", "stack-hardtest"]
    for f in files:
        cmd += ["-f", os.path.join(ROOT, f)]
    r = subprocess.run(cmd + ["--env-file", env_path, "config", "--format", "json"], capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout) if r.returncode == 0 else None


have_compose = subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0 if os.system("command -v docker >/dev/null") == 0 else False
if not have_compose:
    print("SKIP  docker compose is not installed: the render checks need it")
else:
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
        f.write(ENV)
    base = render(["stacks/docker-compose.stack.yml"], f.name)
    both = render(["stacks/docker-compose.stack.yml", "stacks/hardening.override.yml"], f.name)
    os.unlink(f.name)
    check("both the template and template+override render", base is not None and both is not None)
    if base and both:
        h, h0 = both["services"]["hermes"], base["services"]["hermes"]
        check("the override sets no-new-privileges", h.get("security_opt") == ["no-new-privileges:true"])
        check("the override drops ALL capabilities", h.get("cap_drop") == ["ALL"])
        check("the capabilities added back are exactly the profile's", set(h.get("cap_add") or []) == ch.WANT_CAPS)
        check("the pids limit is the profile's maximum", h["deploy"]["resources"]["limits"].get("pids") == ch.MAX_PIDS)
        check("the cpu and memory limits survive the merge", all(h["deploy"]["resources"]["limits"].get(k) == h0["deploy"]["resources"]["limits"].get(k) and h0["deploy"]["resources"]["limits"].get(k) for k in ("cpus", "memory")))
        check("nothing else of the hermes service changed (volumes, ports, environment)",
              all(h.get(k) == h0.get(k) for k in ("volumes", "ports", "environment", "image", "container_name")))
        check("no other service is touched", all(both["services"][n] == base["services"][n] for n in base["services"] if n != "hermes"))

# the script must never touch a real person's stack
script = os.path.join(HERE, "hardening_trial_stack.sh")
for name, want in (("hernik", 2), ("hertin", 2), ("hardtest", None), ("../hertin", 2), ("hardtest; rm", 2), ("", None)):
    if want is None:
        continue
    r = subprocess.run(["bash", script, "check", name], capture_output=True, text=True, timeout=30, cwd=ROOT)
    check(f"the trial script refuses the name {name!r}", r.returncode == want and "must start with 'hardtest'" in r.stderr)
r = subprocess.run(["bash", script, "nonsense"], capture_output=True, text=True, timeout=30, cwd=ROOT)
check("an unknown action prints the usage and exits 2", r.returncode == 2)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all hardening_override checks passed")
