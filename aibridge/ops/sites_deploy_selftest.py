#!/usr/bin/env python3
"""Selftest of ops/sites_deploy.py against a throwaway local git repo (no network, no docker, no notify)."""
import importlib.util, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix="sites-selftest-")
os.environ.update(SITES_CONFIG=os.path.join(tmp, "sites.json"), SITES_ROOT=os.path.join(tmp, "live"),
                  SITES_STATE=os.path.join(tmp, "state.json"), SITES_KEYS=os.path.join(tmp, "keys"),
                  SITES_CONTAINER="sites-selftest-none")
spec = importlib.util.spec_from_file_location("sd", os.path.join(HERE, "sites_deploy.py"))
sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)
sd.notify = lambda *a: notes.append(a)
notes = []
fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    fails += not cond


def sh(*a, cwd=None):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


src = os.path.join(tmp, "src")
os.makedirs(src)
sh("git", "init", "-q", "-b", "main", cwd=src)


def commit(files, msg, delete=()):
    for p, body in files.items():
        full = os.path.join(src, p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if isinstance(body, tuple):                    # ("symlink", target)
            os.symlink(body[1], full)
        else:
            open(full, "w").write(body)
    for p in delete:
        os.unlink(os.path.join(src, p))
    sh("git", "add", "-A", cwd=src)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg, cwd=src)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True).stdout.strip()


json.dump({"sites": {"demo": {"repo": "ssh://unused/x.git", "hosts": ["demo.example.org"]}}}, open(os.environ["SITES_CONFIG"], "w"))
# Local repo instead of ssh: the fetch reads the path directly
orig_git = sd.git
sd.git = lambda mirror, *a, **k: orig_git(mirror, *[src if x == "ssh://unused/x.git" else x for x in a],
                                         **{kk: v for kk, v in k.items() if kk != "name"})

c1 = commit({"index.html": "<h1>uno</h1>", "css/s.css": "a{}", ".gitignore": "x"}, "one")
sd.run_once()
live = os.path.join(tmp, "live", "demo", "current")
check(open(os.path.join(live, "index.html")).read() == "<h1>uno</h1>", "first commit is live")
check(not os.path.exists(os.path.join(live, ".gitignore")), "dot files are not unpacked")
check(oct(os.stat(os.path.join(live, "css/s.css")).st_mode & 0o777) == "0o644", "files are 0644")
conf = open(os.path.join(tmp, "live", "_nginx", "sites.conf")).read()
check("server_name demo.example.org;" in conf and "root /sites/demo/current;" in conf, "nginx server block written")

c2 = commit({"index.html": "<p>internal 10.9.8.7</p>"}, "leak")
sd.run_once()
st = json.load(open(os.environ["SITES_STATE"]))
check(open(os.path.join(live, "index.html")).read() == "<h1>uno</h1>", "a private address is refused, old version stays")
check(st["demo"].get("refused") == c2 and any(n[0] == "alert" for n in notes), "refusal recorded and alerted")
n = len(notes)
sd.run_once()
check(len(notes) == n, "a refused commit is not retried or re-alerted")

c3 = commit({"index.html": "<h1>tres</h1>", "link": ("symlink", "/etc/passwd")}, "symlink")
sd.run_once()
check(open(os.path.join(live, "index.html")).read() == "<h1>uno</h1>", "a symlink in the commit is refused")

c4 = commit({}, "drop link and index", delete=("link", "index.html"))
sd.run_once()
check(os.path.exists(os.path.join(live, "index.html")), "a commit without index.html is refused")

c5 = commit({"index.html": "<h1>cinco</h1> v10.2 ok"}, "good")
sd.run_once()
st = json.load(open(os.environ["SITES_STATE"]))
check(open(os.path.join(live, "index.html")).read().startswith("<h1>cinco</h1>"), "a good commit after refusals goes live")
check("refused" not in st["demo"] and any(n[0] == "resolve" for n in notes), "refusal cleared and resolved")
check(os.readlink(live) == "releases/" + c5[:12], "current points at the new release (relative link)")

for i in range(8):
    commit({"index.html": f"<h1>{i}</h1>"}, f"n{i}")
    sd.run_once()
rels = os.listdir(os.path.join(tmp, "live", "demo", "releases"))
check(len(rels) == sd.KEEP, f"only the last {sd.KEEP} releases are kept ({len(rels)})")

json.dump({"sites": {"demo": {"repo": "ssh://unused/x.git", "hosts": ["demo.example.org"]},
                     "otro": {"repo": "ssh://unused/x.git", "hosts": ["demo.example.org"]}}}, open(os.environ["SITES_CONFIG"], "w"))
try:
    sd.load_conf()
    check(False, "a domain listed for two sites is rejected")
except SystemExit:
    check(True, "a domain listed for two sites is rejected")

subprocess.run(["rm", "-rf", tmp])
print("FAILED" if fails else "all ok")
sys.exit(1 if fails else 0)
