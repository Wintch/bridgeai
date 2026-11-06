#!/usr/bin/env python3
"""ops/stack_packs.py against a fake ~/aibridge and a fake docker. No network: python3 ops/stack_packs_selftest.py"""
import json, os, shutil, subprocess, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__))
repo = os.path.join(here, "..")
root = tempfile.mkdtemp()
os.makedirs(os.path.join(root, "ops", "wake"))
json.dump({"stacks": [{"name": "hernik"}, {"name": "herand"}, {"name": "hertin"}]}, open(os.path.join(root, "ops", "wake", "stacks.json"), "w"))
for d in ("user1-workdir", "stacks/herand/workdir", "stacks/hertin/workdir"):
    os.makedirs(os.path.join(root, d))
shutil.copy(os.path.join(repo, "skill_packs.py"), root); shutil.copy(os.path.join(repo, "skill_packs.json"), root)
bindir = os.path.join(root, "bin"); os.makedirs(bindir)
log = os.path.join(root, "docker.log")
open(os.path.join(bindir, "docker"), "w").write(f"""#!/bin/sh
echo "$@" >> {log}
if [ "$1" = inspect ]; then [ "$4" = stack-herand-hermes ] && echo true || echo false; exit 0; fi
if [ "$1" = exec ]; then echo "paquetes: wrote 65 skill(s) disabled"; exit 0; fi
exit 1
""")
os.chmod(os.path.join(bindir, "docker"), 0o755)
env = dict(os.environ, AIBRIDGE_ROOT=root, PATH=bindir + os.pathsep + os.environ["PATH"])

fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)
def run(*a):
    r = subprocess.run([sys.executable, os.path.join(here, "stack_packs.py"), *a], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr
def state(path): return json.load(open(os.path.join(root, path, ".paquetes.json")))["packs"]
dlog = lambda: open(log).read() if os.path.exists(log) else ""

code, out = run("list")
check("list: three people, nobody chose yet, so all are marked as everything on", code == 0 and out.count("sin elección") == 3 and "hernik" in out)
code, out = run("set", "herand", "empleo", "oficina")
check("set on a RUNNING stack: writes the file in its workdir, then runs `paquetes apply` inside",
      code == 0 and state("stacks/herand/workdir") == ["empleo", "oficina"] and "exec stack-herand-hermes paquetes apply" in dlog() and "next conversation" in out)
code, out = run("on", "hertin", "creativo")
check("on for someone who has not chosen: every pack was already on, says so and to use `set`; stopped stack, nothing executed inside",
      code == 0 and len(state("stacks/hertin/workdir")) == 10 and "already on" in out and "use `set hertin" in out and "exec stack-hertin-hermes" not in dlog() and "next boot" in out)
code, out = run("set", "hertin", "creativo")
check("set on a STOPPED stack: exactly that pack, says it applies at the next boot", code == 0 and state("stacks/hertin/workdir") == ["creativo"] and "next boot" in out)
code, out = run("off", "herand", "oficina")
check("off removes only that pack", code == 0 and state("stacks/herand/workdir") == ["empleo"])
code, out = run("set", "hernik", "--none")
check("set --none: only the base, written in hernik's own workdir (user1-workdir)", code == 0 and state("user1-workdir") == [] and "only the base" in out)
code, out = run("all", "hertin")
check("all: every pack written explicitly", code == 0 and len(state("stacks/hertin/workdir")) == 10)
code, out = run("list")
check("list after: nobody is 'sin elección' any more", code == 0 and "sin elección" not in out)
code, out = run("on", "herand", "nope")
check("unknown pack refused, file unchanged", code == 2 and "unknown pack: nope" in out and state("stacks/herand/workdir") == ["empleo"])
code, out = run("on", "ghost", "empleo")
check("unknown person refused with the list of stacks", code == 2 and "hernik" in out and "herand" in out)
code, out = run("on", "../../etc", "empleo")
check("a path-like person name is refused", code == 2)
code, out = run("on", "herand")
check("on without a pack names the packs", code == 2 and "which packs" in out)
code, out = run("show", "herand")
check("show prints that person's packs", code == 0 and "✅ empleo" in out and "⬜ edicion" in out)
shutil.rmtree(root)
print("\n".join(fails) or "stack_packs_selftest: all ok")
sys.exit(1 if fails else 0)
