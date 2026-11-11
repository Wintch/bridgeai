#!/usr/bin/env python3
"""Self-test for ops/privacy_scan.sh: runs the real script in a throwaway git repo with a throwaway private list.
No network. Run: python3 ops/privacy_scan_selftest.py

The fake secrets below are assembled at run time so this file itself never matches the scan.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)[:300]))
    if not cond:
        fails.append(name)


repo = tempfile.mkdtemp()
os.makedirs(f"{repo}/aibridge/ops/lib")
shutil.copy(f"{HERE}/privacy_scan.sh", f"{repo}/aibridge/ops/privacy_scan.sh")
shutil.copy(f"{HERE}/lib/private_pattern.sh", f"{repo}/aibridge/ops/lib/private_pattern.sh")
private = f"{repo}/private.txt"
open(private, "w").write("Zorblaxian==>REDACTED\nregex:qq[0-9]{3}zz==>x\n")
env = {**os.environ, "PRIVATE_REPLACEMENTS": private, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org"}
env.pop("PRIVACY_SCAN_SKIP", None)


def git(*a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, env=env)


git("init", "-q")
git("config", "user.email", "t@example.org")
git("add", "aibridge")
git("commit", "-qm", "scanner")


def scan_staged(name, text):
    """Stage one file with `text`, scan, unstage. Returns (rc, output)."""
    p = os.path.join(repo, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)
    git("add", "-f", name)
    r = subprocess.run(["bash", f"{repo}/aibridge/ops/privacy_scan.sh"], capture_output=True, text=True, env=env, cwd=repo)
    git("rm", "-q", "--cached", "-f", name)
    os.remove(p)
    return r.returncode, r.stdout + r.stderr


tg_secret = "AB" + "c" * 20 + "_" + "D" * 12          # 35 chars, NOT starting with AA (the old pattern missed these)
must_block = {
    "a Telegram token not starting with AA": "token " + "123456789:" + tg_secret,
    "a Telegram token starting with AA": "8" * 10 + ":AA" + "x" * 33,
    "an OpenRouter key": "key = '" + "sk-" + "or-v1-" + "a1" * 16 + "'",
    "a HERMES_API_KEY value": "HERMES_API_KEY=" + "hk-" + "0123456789abcdef" * 3,
    "an env password with a literal value": "OPENWEBUI_ADMIN_PASSWORD=" + "Qm7rT2vX9pLs4KwZ",
    "an NVIDIA key": "nvapi-" + "Q" * 30,
    "an Argentine mobile number": "llamame al +54 9 11 " + "4567-8901",
    "a word from the private list": "hola Zorblaxian",
    "a regex from the private list": "id qq123zz",
}
for what, text in must_block.items():
    rc, out = scan_staged("notes.md", text)
    check("blocks " + what, rc == 1 and "PRIVACY" in out, out)
    check("never prints the whole value: " + what, text.split()[-1][6:] not in out or len(text.split()[-1]) <= 10, out)

must_pass = {
    "the word risk-assessment-for-the-new-release": "see the risk-assessment-for-the-new-release page",
    "an env reference, not a value": 'NVIDIA_API_KEY="$(grep -m1 NVIDIA_API_KEY stacks/x/.env | cut -d= -f2-)"',
    "an empty token line": "TELEGRAM_BOT_TOKEN=\nTELEGRAM_ALLOWED_USERS=",
    "a test fixture value": "TMDB_API_KEY=goodkey1234567890abcd",
    "a short placeholder": "HERMES_API_KEY=hk-abc",
    "a sha256 pin": "ARG X_SHA256=" + "ab12" * 16,
    "a US test phone": "+12025550100",
    "a plain id with a colon": "build 12345678:done",
}
for what, text in must_pass.items():
    rc, out = scan_staged("notes.md", text)
    check("lets through " + what, rc == 0, out)

for name in ("stacks/x/.env", "ops/ops.env", "ops/gateways.json", "ops/wake/stacks.json", "stacks/x/workdir/.starter-key",
             "stacks/x/credentials.txt", "hermes-config/state.db"):
    rc, out = scan_staged(name, "nothing secret here\n")
    check("rejects the file name " + name, rc == 1 and "must never be committed" in out, out)
for name in ("ops/gateways.json.example", "ops/wake/stacks.json.example", "docs/env.md"):
    rc, out = scan_staged(name, "nothing secret here\n")
    check("accepts the file name " + name, rc == 0, out)

r = subprocess.run(["bash", f"{repo}/aibridge/ops/privacy_scan.sh", "--push"], capture_output=True, text=True,
                   env={**env, "PRIVATE_REPLACEMENTS": f"{repo}/missing.txt"}, cwd=repo)
check("--push refuses to report clean without the private list", r.returncode == 2, r.stderr)

shutil.rmtree(repo)
print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
