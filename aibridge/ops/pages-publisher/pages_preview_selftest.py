#!/usr/bin/env python3
"""Offline test of the PREVIEW publisher (publish-preview.sh + deploy-preview.sh): a bot's push to the dev branch becomes a Pages preview, never touches
production or the working clone, shows broken references instead of blocking, and says what happened on the preview-status branch.

Run from anywhere:  python3 -I ops/pages-publisher/pages_preview_selftest.py
"""
import json, os, subprocess, sys, tempfile
import atexit as _a, shutil as _s, signal as _g
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_a.register(_s.rmtree, tempfile.tempdir, True)
_g.signal(_g.SIGTERM, lambda *_: sys.exit(143))
HERE = os.path.dirname(os.path.abspath(__file__))
PREV, GATE, DEPLOY = (os.path.join(HERE, n) for n in ("publish-preview.sh", "check-new-assets.py", "deploy-preview.sh"))
ok = True
def chk(what, cond, detail=None):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what + ("" if cond or detail is None else f"  [{detail!r}]"), flush=True)

T = tempfile.mkdtemp()
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
def git(*a, cwd=None): return subprocess.run(["git", *a], cwd=cwd, env=ENV, capture_output=True, text=True)
def sh(path, body):
    open(path, "w").write("#!/bin/bash\n" + body); os.chmod(path, 0o755); return path

origin, src, site = f"{T}/o.git", f"{T}/src", f"{T}/sites/demo"
git("init", "-q", "--bare", "-b", "main", origin); git("clone", "-q", origin, src); os.makedirs(f"{T}/sites")
git("clone", "-q", origin, site); git("checkout", "-q", "-b", "main", cwd=site)
os.makedirs(f"{site}/ev"); open(f"{site}/index.html", "w").write('<img src="ev/a.avif">\n'); open(f"{site}/ev/a.avif", "w").write("x")
git("add", "-A", cwd=site); git("commit", "-q", "-m", "v1", cwd=site); git("remote", "rename", "origin", "gitea", cwd=site); git("push", "-q", "gitea", "main", cwd=site)
git("pull", "-q", "origin", "main", cwd=src)
prod_sha = git("rev-parse", "HEAD", cwd=site).stdout.strip()
state = f"{T}/state"; os.makedirs(state); open(f"{state}/.published-demo", "w").write(prod_sha)   # production: v1 is live
calls = f"{T}/calls.txt"
ok_sh = sh(f"{T}/ok.sh", f'echo "deploy $1 $2" >> {calls}\necho "✨ Deployment complete! Take a peek over at https://267c4588.demo-qe9.pages.dev"\n')
silent = sh(f"{T}/silent.sh", 'echo "Getting User settings..."\necho "Logs were written to /x.log"\n')
auth = sh(f"{T}/auth.sh", 'echo "Authentication error [code: 10000]"\n')
def run(deploy, retry=600, status="preview-status", branch="dev"):
    return subprocess.run(["bash", PREV, "demo", branch], env=dict(os.environ, SITES_DIR=f"{T}/sites", STATE_DIR=state, DEPLOY_CMD=deploy, GATE=GATE,
                                                                   RETRY_AFTER=str(retry), STATUS_REF=status), capture_output=True, text=True)
def bot(edit, msg, branch="dev"):
    git("fetch", "-q", "origin", cwd=src)
    if git("rev-parse", "--verify", "-q", f"origin/{branch}", cwd=src).returncode == 0:
        git("checkout", "-q", "-B", branch, f"origin/{branch}", cwd=src)
    else:
        git("checkout", "-q", "-B", branch, "origin/main", cwd=src)
    edit(); git("add", "-A", cwd=src); git("commit", "-q", "-m", msg, cwd=src); git("push", "-q", "origin", branch, cwd=src)
def write(path, text):
    def f():
        os.makedirs(os.path.dirname(f"{src}/{path}") or src, exist_ok=True); open(f"{src}/{path}", "w").write(text)
    return f
def n_calls(): return len(open(calls).read().splitlines()) if os.path.exists(calls) else 0
def log(): return open(f"{state}/preview-demo.log").read() if os.path.exists(f"{state}/preview-demo.log") else ""
def status():
    r = subprocess.run(["git", f"--git-dir={origin}", "show", "preview-status:status.json"], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None
def dev(): return git(f"--git-dir={origin}", "rev-parse", "dev").stdout.strip()

r = run(ok_sh)
chk("no dev branch yet: nothing happens, quietly", r.returncode == 0 and n_calls() == 0 and status() is None)
bot(write("index.html", '<img src="ev/a.avif"><p>nuevo</p>\n'), "first change")
run(ok_sh); s = status()
chk("a push to dev is deployed as a preview of THAT branch", n_calls() == 1 and open(calls).read().split() == ["deploy", "demo", "dev"], open(calls).read() if os.path.exists(calls) else None)
chk("the status says published, for that commit, with the branch address built from wrangler's hash address",
    s and s["state"] == "published" and s["sha"] == dev() and s["url"] == "https://dev.demo-qe9.pages.dev" and s["deploy_url"] == "https://267c4588.demo-qe9.pages.dev", s)
chk("nothing is flagged missing when the preview has no new broken reference", s and s["missing"] == [], s)
n = n_calls(); run(ok_sh); run(ok_sh)
chk("a previewed commit is not previewed again", n_calls() == n)
chk("production is untouched: marker and working clone stay where they were",
    open(f"{state}/.published-demo").read().strip() == prod_sha and git("rev-parse", "HEAD", cwd=site).stdout.strip() == prod_sha and git("branch", "--show-current", cwd=site).stdout.strip() == "main")
bot(write("index.html", '<img src="ev/a.avif"><img src="ev/nuevo.avif">\n'), "a tile whose picture is not there yet")
run(ok_sh); s = status()
chk("a commit with a broken reference is STILL previewed (the person must see it), and the status names the missing file",
    n_calls() == 2 and s["state"] == "published" and any("ev/nuevo.avif" in m for m in s["missing"]), s)
bot(write("p.html", "<p>otra</p>\n"), "more"); run(silent); s = status()
chk("a deploy with no success line is a failed preview, not marked, and the status says failed", s and s["state"] == "failed" and s["sha"] == dev() and n_calls() == 2, s)
m = log().count("previewing"); run(ok_sh)
chk("right after a failure it does not retry (backoff)", log().count("previewing") == m)
run(auth, retry=0); s = status()
chk("an authentication failure tells the operator to renew the token", s and s["state"] == "failed" and "token" in s["note"] and "operator" in s["note"], s)
run(ok_sh, retry=0); s = status()
chk("after the backoff it retries and the status becomes published", n_calls() == 3 and s["state"] == "published" and s["sha"] == dev(), s)
count = int(git(f"--git-dir={origin}", "rev-list", "--count", "preview-status").stdout.strip())
chk("the status branch stays ONE commit", count == 1, count)
chk("the production status branch is not touched by the preview publisher", subprocess.run(["git", f"--git-dir={origin}", "rev-parse", "--verify", "-q", "publish-status"], capture_output=True).returncode != 0)
chk("STATUS_REF empty turns the status off", run(ok_sh, retry=0, status="").returncode == 0)
chk("a path-like site or branch name is refused", subprocess.run(["bash", PREV, "../etc"], env=dict(os.environ, SITES_DIR=f"{T}/sites", STATE_DIR=state), capture_output=True).returncode == 2
    and subprocess.run(["bash", PREV, "demo", "../x"], env=dict(os.environ, SITES_DIR=f"{T}/sites", STATE_DIR=state), capture_output=True).returncode == 2)
# deploy-preview.sh itself: the guards that run before wrangler (no network, no token needed)
fake_home = f"{T}/home"; os.makedirs(f"{fake_home}/sites"); open(f"{fake_home}/.cloudflare.env", "w").write("export CF_API_TOKEN=x\nexport CF_ACCOUNT_ID=y\n")
r = subprocess.run(["bash", DEPLOY, "demo", "dev"], env=dict(os.environ, HOME=fake_home), capture_output=True, text=True)
chk("deploy-preview.sh: a site that is not a git repo is refused before anything is sent", r.returncode == 1 and "no es repo git" in r.stdout, r.stdout[-120:])
chk("deploy-preview.sh: valid shell, deploys a BRANCH with --branch and the project is the site", subprocess.run(["bash", "-n", DEPLOY]).returncode == 0
    and '--branch="$branch"' in open(DEPLOY).read() and '--project-name="$site"' in open(DEPLOY).read() and "git -C \"$d\" archive \"$REMOTE/$branch\"" in open(DEPLOY).read())
chk("the shipped preview service and timer are valid, every 30 s", "ExecStart=%h/sitios-tools/publish-preview.sh %i dev" in open(f"{HERE}/preview@.service").read() and "OnUnitActiveSec=30" in open(f"{HERE}/preview@.timer").read())

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
