#!/usr/bin/env python3
"""Offline test of the Pages publisher (publish-from-gitea.sh + check-new-assets.py) on throwaway git repos and stub deploys: the seed, a bot push,
a deploy that confirms nothing (the case that fooled the first version), the retry backoff, uncommitted and unpushed local work, the lock, the gate
for files that do not exist yet, and the status branch the bot reads.

Run from anywhere:  python3 -I ops/pages-publisher/pages_publisher_selftest.py
"""
import json, os, subprocess, sys, tempfile
import atexit as _a, shutil as _s, signal as _g
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_a.register(_s.rmtree, tempfile.tempdir, True)
_g.signal(_g.SIGTERM, lambda *_: sys.exit(143))
HERE = os.path.dirname(os.path.abspath(__file__))
PUB, GATE = os.path.join(HERE, "publish-from-gitea.sh"), os.path.join(HERE, "check-new-assets.py")
ok = True
def chk(what, cond, detail=None):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what + ("" if cond or detail is None else f"  [{detail!r}]"), flush=True)

T = tempfile.mkdtemp()
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
def git(*a, cwd=None):
    return subprocess.run(["git", *a], cwd=cwd, env=ENV, capture_output=True, text=True)
def sh(path, body):
    open(path, "w").write("#!/bin/bash\n" + body); os.chmod(path, 0o755); return path

origin, src, site = f"{T}/o.git", f"{T}/src", f"{T}/sites/demo"
git("init", "-q", "--bare", "-b", "main", origin); git("clone", "-q", origin, src); os.makedirs(f"{T}/sites")
git("clone", "-q", origin, site); git("checkout", "-q", "-b", "main", cwd=site)
os.makedirs(f"{site}/ev"); open(f"{site}/index.html", "w").write('<img src="ev/a.avif"><img src="gone-already.avif">\n'); open(f"{site}/ev/a.avif", "w").write("x")
git("add", "-A", cwd=site); git("commit", "-q", "-m", "v1", cwd=site); git("remote", "rename", "origin", "gitea", cwd=site); git("push", "-q", "gitea", "main", cwd=site)
git("checkout", "-q", "-B", "main", "origin/main", cwd=src) if git("fetch", "-q", cwd=src).returncode == 0 and False else git("pull", "-q", "origin", "main", cwd=src)
state = f"{T}/state"; os.makedirs(state)
open(f"{state}/.published-demo", "w").write(git("rev-parse", "HEAD", cwd=site).stdout)   # seeded, as the install does
deploys = f"{T}/deploys.txt"
ok_sh = sh(f"{T}/ok.sh", f'echo "deploy $1" >> {deploys}\necho "✨ Deployment complete! Take a peek over at https://x.pages.dev"\n')
silent = sh(f"{T}/silent.sh", 'echo "Getting User settings..."\necho "Logs were written to /x.log"\necho "== cache == ok"\n')   # a rejected token: no error word, no success
auth = sh(f"{T}/auth.sh", 'echo "Authentication error [code: 10000]"\n')
bad = sh(f"{T}/bad.sh", 'echo "wrangler Error: boom"\n')
def run(deploy, retry=600, status="publish-status"):
    return subprocess.run(["bash", PUB, "demo"], env=dict(os.environ, SITES_DIR=f"{T}/sites", STATE_DIR=state, DEPLOY_CMD=deploy, GATE=GATE,
                                                          RETRY_AFTER=str(retry), STATUS_REF=status), capture_output=True, text=True)
def bot(shell_edit, msg):
    git("pull", "-q", "origin", "main", cwd=src)
    shell_edit(); git("add", "-A", cwd=src); git("commit", "-q", "-m", msg, cwd=src); git("push", "-q", "origin", "main", cwd=src)
def write(path, text):
    def f():
        os.makedirs(os.path.dirname(f"{src}/{path}") or src, exist_ok=True); open(f"{src}/{path}", "w").write(text)
    return f
def n_deploys():
    return len(open(deploys).read().splitlines()) if os.path.exists(deploys) else 0
def log():
    return open(f"{state}/publish-demo.log").read() if os.path.exists(f"{state}/publish-demo.log") else ""
def status():
    r = subprocess.run(["git", f"--git-dir={origin}", "show", "publish-status:status.json"], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None
def head(): return git(f"--git-dir={origin}", "rev-parse", "main").stdout.strip()

run(ok_sh); chk("seeded: nothing is published at start, no status written", n_deploys() == 0 and status() is None)
bot(write("index.html", '<img src="ev/a.avif"><img src="gone-already.avif"><img src="ev/new.avif">\n'), "tile without image")
run(ok_sh)
s = status()
chk("a commit introducing a missing image is blocked, nothing deployed", n_deploys() == 0 and "BLOCKED" in log() and "ev/new.avif" in log())
chk("the status branch says blocked for that commit and names the file", s and s["state"] == "blocked" and s["sha"] == head() and any("ev/new.avif" in m for m in s["missing"]), s)
chk("an image that was ALREADY missing in the live site is not reported", s and not any("gone-already" in m for m in s["missing"]))
n = log().count("BLOCKED"); run(ok_sh); run(ok_sh)
chk("a blocked commit is logged once, not every tick", log().count("BLOCKED") == n)
bot(write("ev/new.avif", "x"), "add the image")
run(ok_sh); s = status()
chk("once a commit adds the file it is published by itself, and the status says published", n_deploys() == 1 and s and s["state"] == "published" and s["sha"] == head(), s)
chk("the site tree (main) never gets the status file", subprocess.run(["git", f"--git-dir={origin}", "ls-tree", "-r", "--name-only", "main"], capture_output=True, text=True).stdout.count("status.json") == 0)
bot(write("p.html", "<p>x</p>\n"), "v3")
run(silent); s = status()
chk("a deploy with no success line (token rejected, no error word) is a failure, not marked published", n_deploys() == 1 and "FAILED" in log()
    and open(f"{state}/.published-demo").read().strip() != head())
chk("the status says failed", s and s["state"] == "failed" and s["sha"] == head(), s)
m = log().count("publishing"); run(ok_sh)
chk("right after a failure it does NOT retry (backoff)", log().count("publishing") == m and n_deploys() == 1)
run(auth, retry=0); s = status()
chk("an authentication failure says the operator has to renew the token", s and s["state"] == "failed" and "token" in s["note"] and "operator" in s["note"], s)
run(ok_sh, retry=0); s = status()
chk("after the backoff it retries, publishes and the status becomes published", n_deploys() == 2 and s and s["state"] == "published", s)
bot(write("p.html", "<p>y</p>\n"), "v4"); run(bad, retry=0)
chk("an explicit error is a failure too", n_deploys() == 2 and status()["state"] == "failed")
run(ok_sh, retry=0); run(ok_sh, retry=0)
chk("it recovers, and a published sha never repeats", n_deploys() == 3)
count = int(git(f"--git-dir={origin}", "rev-list", "--count", "publish-status").stdout.strip())
chk("the status branch stays ONE commit however many decisions were written (force-pushed)", count == 1, count)
open(f"{site}/scratch.txt", "w").write("local"); bot(write("p.html", "<p>z</p>\n"), "v5"); run(ok_sh, retry=0)
chk("uncommitted local work blocks everything: nothing merged or published", n_deploys() == 3 and "local work" in log())
os.remove(f"{site}/scratch.txt"); run(ok_sh, retry=0)
chk("work gone: the pending push is published", n_deploys() == 4)
open(f"{site}/p.html", "w").write("mine\n"); git("commit", "-qam", "mine", cwd=site); bot(write("p.html", "<p>w</p>\n"), "v6"); run(ok_sh, retry=0)
chk("a local commit not on Gitea is never overwritten", n_deploys() == 4 and open(f"{site}/p.html").read() == "mine\n")
r = run(ok_sh, retry=0, status="")
chk("STATUS_REF empty turns the status off and nothing else changes", r.returncode == 0)
chk("a path-like site name is refused", subprocess.run(["bash", PUB, "../etc"], env=dict(os.environ, SITES_DIR=f"{T}/sites", STATE_DIR=state), capture_output=True).returncode == 2)
chk("the shipped service and timer are valid and the timer fires every 30 s",
    "ExecStart=%h/sitios-tools/publish-from-gitea.sh %i" in open(f"{HERE}/publish@.service").read() and "OnUnitActiveSec=30" in open(f"{HERE}/publish@.timer").read())

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
