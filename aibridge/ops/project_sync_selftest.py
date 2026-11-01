#!/usr/bin/env python3
"""End-to-end test of project_publish.py + project_sync.py on a throwaway git repo and two fake stacks: the people's
data and the stack's local replacements are never written, an untouched old file is updated, a person's edit is kept
for review (saved when the project changed it too, left in place when not), a file gone from the project is removed
only when untouched, a busy stack waits, a release with private strings never leaves, a bad release is refused whole,
and a second run with nothing new does nothing. Stdlib + git: python3 ops/project_sync_selftest.py"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix="psync-")
root, src = f"{tmp}/aibridge", f"{tmp}/project"
os.makedirs(f"{root}/stacks")
os.symlink(HERE, f"{root}/ops")
open(f"{tmp}/private.txt", "w").write("Secretname Lastname==>REDACTED\n")
env = dict(os.environ, PROJECTS_CONFIG=f"{tmp}/projects.json", PROJECTS_STATE=f"{tmp}/state.json", PROJECT_SYNC_NPM="0",
           PRIVATE_REPLACEMENTS=f"{tmp}/private.txt", OPS_ENV=f"{tmp}/none.env", HOME=tmp,
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@x", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@x")
fails = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")


def G(*a):
    return subprocess.run(["git", "-C", src, *a], capture_output=True, text=True, env=env)


def put(base, files):
    for p, body in files.items():
        os.makedirs(os.path.dirname(f"{base}/{p}") or base, exist_ok=True)
        open(f"{base}/{p}", "w").write(body)


def publish(*a):
    r = subprocess.run([sys.executable, f"{HERE}/project_publish.py", *a], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


rd = lambda stack, p: open(f"{root}/stacks/{stack}/workdir/jobfinder/{p}").read()
exists = lambda stack, p: os.path.exists(f"{root}/stacks/{stack}/workdir/jobfinder/{p}")

# the project, v1 then v2
os.makedirs(src)
G("init", "-q", "-b", "integration")
v1 = {"VERSION": "1.0.0\n", "scan.mjs": "scan v1\n", "modes/oferta.md": "modo v1\n", "docs/old.md": "vieja\n",
      "docs/kept.md": "igual\n", "cops": "upstream cops\n", "package.json": "{}\n", "data/.gitkeep": ""}
put(src, v1)
G("add", "-A"); G("commit", "-qm", "v1")
installed = dict(v1)                                          # what both stacks got by hand on day one
put(src, {"VERSION": "2.0.0\n", "scan.mjs": "scan v2\n", "modes/oferta.md": "modo v2\n", "docs/kept.md": "igual\n"})
os.remove(f"{src}/docs/old.md")
G("add", "-A"); G("commit", "-qm", "v2")
put(src, {"modes/watch.md": "watch extra\n"})                # an untracked system file listed in "extra"
put(src, {"scan.mjs": "work in progress\n"})                 # uncommitted: must not ship

for stack in ("eug", "and"):
    base = f"{root}/stacks/{stack}/workdir/jobfinder"
    put(base, installed)
    put(base, {"cv.md": f"cv de {stack}\n", "portals.yml": "151 empresas\n", "data/applications.md": "postulaciones\n",
               "cops": "docker-free cops\n"})
put(f"{root}/stacks/eug/workdir/jobfinder", {"modes/oferta.md": "modo de la persona\n", "docs/kept.md": "igual, con nota de la persona\n"})
put(f"{root}/stacks/eug/workdir/jobfinder", {"docs/old.md": "vieja, editada\n"})
os.makedirs(f"{root}/stacks/and/workdir/jobs")
open(f"{root}/stacks/and/workdir/jobs/scan.json", "w").write("{}")      # the other person has a long scan running

proj = {"src": src, "ref": "integration", "extra": ["modes/watch.md"], "dest": "jobfinder", "stacks": ["eug", "and", "nobody"],
        "keep_local": ["cops"], "protect": [r"^cv\.md$", r"^portals\.yml$", r"^data/(?!(.*/)?\.gitkeep$)", r"^config/profile\.yml$"],
        "leak_allow": [{"path": "^tests/", "text": "Secretname Lastname"}]}
conf = lambda **kw: json.dump({"vm": f"local:{root}", "projects": {"jobfinder": dict(proj, **kw)}}, open(f"{tmp}/projects.json", "w"))
conf()
rc, out = publish()
check("a commit younger than settle_min waits (an agent commits in bursts)", (rc, out.strip(), exists("eug", "modes/watch.md")), (0, "", False))
conf(settle_min=0)

rc, out = publish("--dry-run")
check("dry run changes nothing", (rc, rd("eug", "scan.mjs"), "simulación" in out), (0, "scan v1\n", True))
rc, out = publish()
check("a busy stack makes the run retry (exit 0 from publish, state not saved)", (rc, os.path.exists(f"{tmp}/state.json")), (0, False))
check("committed content ships, work in progress does not", rd("eug", "scan.mjs"), "scan v2\n")
check("an extra system file ships", rd("eug", "modes/watch.md"), "watch extra\n")
check("the person's data is never written", (rd("eug", "cv.md"), rd("eug", "portals.yml"), rd("eug", "data/applications.md")),
      ("cv de eug\n", "151 empresas\n", "postulaciones\n"))
check("a local replacement is kept", rd("eug", "cops"), "docker-free cops\n")
check("an edit the project also changed: the new one goes in", rd("eug", "modes/oferta.md"), "modo v2\n")
saved = [os.path.join(dp, f) for dp, _, fs in os.walk(f"{root}/releases/jobfinder/aportes/eug") for f in fs]
check("...and the person's version is saved with a diff", sorted(os.path.basename(f) for f in saved if "oferta" in f), ["oferta.md", "oferta.md.diff"])
check("an edit of a file the project did not change: saved too on the first run (no earlier release to compare)",
      any("kept.md" in f for f in saved), True)
check("a file gone from the project but edited by the person stays", rd("eug", "docs/old.md"), "vieja, editada\n")
check("a busy stack is not touched", rd("and", "scan.mjs"), "scan v1\n")
check("a stack without the project is skipped", "nobody: no tiene jobfinder" in out, True)
check("the report names the contributions", ("Aportes para revisar" in out, "modes/oferta.md" in out), (True, True))

os.remove(f"{root}/stacks/and/workdir/jobs/scan.json")      # that scan ended
rc, out = publish()
check("the next run applies to the stack that was busy", (rc, rd("and", "scan.mjs"), exists("and", "docs/old.md")), (0, "scan v2\n", False))
check("...and remembers it is done", json.load(open(f"{tmp}/state.json")).get("jobfinder", "").startswith(G("rev-parse", "HEAD").stdout[:12]), True)
rc, out = publish()
check("nothing new: nothing happens", (rc, out.strip()), (0, ""))

# v3 changes a file the person edited only in v1 times (keep-local now that a release is known) and adds a secret
put(f"{root}/stacks/eug/workdir/jobfinder", {"scan.mjs": "scan v2 + idea de la persona\n"})
put(src, {"modes/oferta.md": "modo v3\n"})
G("checkout", "-q", "--", "scan.mjs"); G("add", "modes/oferta.md"); G("commit", "-qm", "v3")
rc, out = publish()
check("an edit of a file the project did not change since the last release stays", rd("eug", "scan.mjs"), "scan v2 + idea de la persona\n")
check("...reported once as the person's", "scan.mjs (se dejó el de la persona)" in out, True)
check("a file the person never touched follows the project", rd("and", "modes/oferta.md"), "modo v3\n")
put(src, {"docs/new.md": "contacto: Secretname Lastname\n"}); G("add", "-A"); G("commit", "-qm", "oops")
rc, out = publish()
check("private strings stop the release before it leaves", (rc, "no se publicó" in out, "docs/new.md" in out, exists("eug", "docs/new.md")), (1, True, True, False))
rc, out = publish()
check("a refused release is not retried (nor alerted again) until the commit changes", (rc, out.strip()), (0, ""))
G("rm", "-q", "docs/new.md")
put(src, {"tests/fixture.test.mjs": "const who = 'Secretname Lastname'\n"}); G("add", "-A"); G("commit", "-qm", "fixture")
rc, out = publish()
check("an allowed exact string passes in its paths only", (rc, rd("eug", "tests/fixture.test.mjs")), (0, "const who = 'Secretname Lastname'\n"))
put(src, {"docs/Secretname Lastname.md": "x\n"}); G("add", "-A"); G("commit", "-qm", "named")
rc, out = publish()
check("a private string in a file name is caught too", (rc, "no se publicó" in out), (1, True))
G("rm", "-q", "docs/Secretname Lastname.md"); G("commit", "-qm", "unnamed")

# a symlinked folder and an unreadable file in a person's tree: left alone, reported, the rest goes in
outside = f"{tmp}/outside"; os.makedirs(outside)
A = f"{root}/stacks/and/workdir/jobfinder"
os.rename(f"{A}/docs", f"{tmp}/docs-moved"); os.symlink(outside, f"{A}/docs")
os.chmod(f"{A}/modes/oferta.md", 0)
put(src, {"docs/kept.md": "igual v4\n", "modes/oferta.md": "modo v4\n", "scan.mjs": "scan v4\n"}); G("add", "-A"); G("commit", "-qm", "v4")
rc, out = publish()
os.chmod(f"{A}/modes/oferta.md", 0o644)
check("nothing is written through a symlink", os.listdir(outside), [])
check("an unreadable file is left alone and reported, the rest goes in",
      (rd("and", "modes/oferta.md"), rd("and", "scan.mjs"), "no se puede leer" in out, "symlink" in out), ("modo v3\n", "scan v4\n", True, True))

# a release that tries to write the person's data is refused whole (a hand-made manifest)
man = json.load(open(sorted(p for p in (os.path.join(f"{root}/releases/jobfinder", f) for f in os.listdir(f"{root}/releases/jobfinder"))
                            if p.endswith(".json") and "state-" not in p)[-1]))
man["files"]["cv.md"] = {"blob": "0" * 40, "mode": 420}
json.dump(man, open(f"{root}/releases/jobfinder/{man['id']}.json", "w"))
r = subprocess.run([sys.executable, f"{HERE}/project_sync.py", "apply", "jobfinder", man["id"]], capture_output=True, text=True,
                   env=dict(env, AIBRIDGE_ROOT=root))
check("a release that would write protected paths is refused", (r.returncode != 0, "refused" in r.stdout + r.stderr, rd("eug", "cv.md")),
      (True, True, "cv de eug\n"))

rc, out = publish("aportes")
check("contributions come down for review", os.path.isfile(f"{tmp}/Documents/jobfinder-aportes/aportes/eug/" +
      os.listdir(f"{tmp}/Documents/jobfinder-aportes/aportes/eug")[0] + "/modes/oferta.md"), True)
state = json.load(open(f"{root}/releases/jobfinder/state-eug.json"))
check("the state lists the system files for backup_watch, never the person's", ("scan.mjs" in state["files"], "cv.md" in state["files"],
      state["prefix"]), (True, False, "workdir/jobfinder/"))
os.environ["RELEASES_DIR"] = f"{root}/releases"
sys.path.insert(0, HERE)
import backup_watch
sk = backup_watch.synced("eug")
check("backup_watch skips the project's files but keeps watching the person's kept edits",
      ("workdir/jobfinder/modes/watch.md" in sk, bool(state["local"]), any("workdir/jobfinder/" + p in sk for p in state["local"])),
      (True, True, False))

# a lockfile that does not match package.json never ships
put(src, {"package-lock.json": json.dumps({"packages": {"": {"dependencies": {"left-pad": "^1"}}}})})
conf(settle_min=0, extra=["modes/watch.md", "package-lock.json"])
rc, out = publish()
check("a lock out of sync with package.json is refused before it leaves", (rc, "package-lock.json no coincide" in out), (1, True))

print("\n".join(fails) or "project_sync_selftest: all ok")
sys.exit(1 if fails else 0)
