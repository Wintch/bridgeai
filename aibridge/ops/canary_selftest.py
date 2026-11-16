#!/usr/bin/env python3
"""Offline test of the canary stage (ops/pipeline.sh canary / canary-undo / deploy) and of what it relies on: ops/recreate_hermes.sh putting the
canary's compose override on every recreate of a canary stack, and ops/redeploy_router.sh refusing one.

No Docker, no ssh, no network. A fake `ssh` runs the commands on a fake home directory, a fake `docker` keeps images and containers in a JSON
file (and runs the little `sh -c` scripts the stage hands to throwaway containers on the real files), and the REAL pipeline.sh,
recreate_hermes.sh and redeploy_router.sh run against them. The waker's side (no update planned or applied for a canary stack) is tested in
ops/wake/updates_selftest.py.

Run from anywhere:  python3 -I ops/canary_selftest.py
"""
import glob, hashlib, json, os, shutil, stat, subprocess, sys, tempfile
OPS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(OPS)
ok = True
def chk(cond, what, extra=""):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what + ("" if cond else "\n     " + str(extra)[-900:]), flush=True)

tmp = tempfile.mkdtemp()
HOME = os.path.join(tmp, "home"); BIN = os.path.join(tmp, "bin"); STATE = os.path.join(tmp, "docker.json"); LOG = os.path.join(tmp, "calls.log")
AB = os.path.join(HOME, "aibridge"); os.makedirs(BIN)
L_ID, P_ID = "sha256:" + "1" * 64, "sha256:" + "2" * 64
TAG = "aibridge-hermes-agent:build-abc1234"

FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, re, subprocess, sys, time
ST, LOG = os.environ["FAKE_STATE"], os.environ["FAKE_LOG"]
args = sys.argv[1:]
open(LOG, "a").write("docker " + " ".join(args) + "\n")
st = json.load(open(ST))
def save(): json.dump(st, open(ST, "w"))
C = "stack-demo-hermes"
FILES = {"config.yaml": "model:\n  default: m\n", ".env": "SOME_API_KEY=a\n", "auth.json": "{}"}
def image_id(ref):
    return st["tags"].get(ref)
if args[:2] == ["image", "inspect"]:
    refs = args[4:]
    ids = [image_id(r) for r in refs]
    if None in ids: sys.exit(1)
    print("\n".join(ids)); sys.exit(0)
if args[0] == "load":
    sys.stdin.buffer.read()
    st["tags"][os.environ["FAKE_LOAD_TAG"]] = os.environ["FAKE_LOAD_ID"]
    st["tags"]["aibridge-hermes-agent:latest"] = os.environ["FAKE_LOAD_ID"]   # the worst case: a tar that also carries `latest`
    save(); print("Loaded image"); sys.exit(0)
if args[0] == "tag":
    old = args[1]; st["tags"][args[2]] = st["tags"].get(old, old); save(); sys.exit(0)
if args[0] == "stop":
    st["c"]["running"] = False; save(); print(args[1]); sys.exit(0)
if args[0] == "inspect":
    fmt, name = args[2], args[3]
    if name != C or not st.get("c"): sys.exit(1)
    c = st["c"]
    out = (fmt.replace("{{.State.Running}}", "true" if c["running"] else "false").replace("{{.Id}}", "cid")
           .replace("{{.Image}}", c["image"]).replace("{{.Config.Image}}", c["ref"]).replace("{{.Config.Hostname}}", c["hostname"])
           .replace("{{.State.StartedAt}}", time.strftime("%Y-%m-%dT%H:%M:%S.0Z", time.gmtime())).replace("{{json .Config.Env}}", "[]"))
    print(out); sys.exit(0)
if args[0] == "exec":
    if any("agent.log" in a for a in args):
        print(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " INFO Turn machinery warmed")
    sys.exit(0)
if args[0] == "logs":
    print("boot config unchanged since last boot"); sys.exit(0)
if args[0] == "cp":
    src = args[1].split(":", 1)[1]; open(args[2], "w").write(FILES[os.path.basename(src)]); sys.exit(0)
if args[0] == "compose":
    if os.environ.get("FAKE_UP_FAIL"): print("boom", file=sys.stderr); sys.exit(1)
    files = [args[i + 1] for i, a in enumerate(args) if a == "-f"]
    ref, host = "aibridge-hermes-agent:latest", "random" + str(int(time.time() * 1000) % 10000)
    for f in files:
        if f.endswith("canary.override.yml"):
            txt = open(f).read()
            ref = re.search(r"image: (\S+)", txt).group(1); host = re.search(r"hostname: (\S+)", txt).group(1)
    st["c"] = {"running": True, "ref": ref, "image": st["tags"][ref], "hostname": host}
    save(); print(" Container " + C + "  Started"); sys.exit(0)
if args[0] == "run":
    mounts, env, ep, i = {}, dict(os.environ), None, 1
    while i < len(args):
        a = args[i]
        if a == "--rm": i += 1
        elif a == "-v": s, d = args[i + 1].split(":")[:2]; mounts[d] = s; i += 2
        elif a == "-e": k, v = args[i + 1].split("=", 1); env[k] = v; i += 2
        elif a == "--entrypoint": ep = args[i + 1]; i += 2
        else: break
    rest = args[i + 1:]                         # args[i] is the image
    def host(s): return re.sub(r"(?<![\w.])(/[psb])(?![\w])", lambda m: mounts.get(m.group(1), m.group(1)), s)
    if ep == "python3":
        code = rest[1]
        print("{}" if "hashlib.sha256(v.encode" in code else json.dumps(FILES)); sys.exit(0)
    if ep == "du":
        print("7\t" + mounts["/p"]); sys.exit(0)
    if ep == "sh" and rest[0] == "-c":
        r = subprocess.run(["sh", "-c", host(rest[1])] + rest[2:], env=env, cwd=os.environ.get("FAKE_CWD") or None)
        sys.exit(r.returncode)
sys.exit("fake docker: not handled: " + " ".join(args))
'''
FAKE_SSH = r'''#!/usr/bin/env python3
import os, sys
rest = sys.argv[2:]
open(os.environ["FAKE_LOG"], "a").write("ssh " + " ".join(rest)[:160].replace("\n", " ") + "\n")
if os.environ.get("FAKE_SSH_CANARIES") is not None and "*.canary" in " ".join(rest):
    if "printf" in " ".join(rest): print(os.environ["FAKE_SSH_CANARIES"])      # "<stack> <image>" lines (pipeline.sh)
    else: print("\n".join(l.split()[0] for l in os.environ["FAKE_SSH_CANARIES"].splitlines()))   # names (redeploy_router.sh)
    sys.exit(0)
cmd = ["bash"] + rest[1:] if rest[0] == "bash" else ["bash", "-c", " ".join(rest)]
os.execvp("bash", cmd)
'''
for name, body in (("docker", FAKE_DOCKER), ("ssh", FAKE_SSH), ("systemctl", "#!/bin/sh\nexit 0\n"), ("sleep", "#!/bin/sh\nexit 0\n")):
    p = os.path.join(BIN, name); open(p, "w").write(body); os.chmod(p, 0o755)

def world():
    """A fresh fake Docker host: one stack `demo`, awake on latest, with persisted files."""
    shutil.rmtree(HOME, ignore_errors=True)
    for d in ("stacks/demo/persist", "ops/wake", "backups"):
        os.makedirs(os.path.join(AB if not d.startswith("backups") else HOME, d))
    shutil.copy(os.path.join(OPS, "recreate_hermes.sh"), os.path.join(AB, "ops", "recreate_hermes.sh"))
    shutil.copy(os.path.join(OPS, "wake", "waker.py"), os.path.join(AB, "ops", "wake", "waker.py"))
    open(os.path.join(AB, "stacks", "demo", ".env"), "w").write("STACK_NAME=demo\n")
    for f, t in (("state.db", "original"), ("config.yaml", "x")): open(os.path.join(AB, "stacks", "demo", "persist", f), "w").write(t)
    json.dump({"tags": {"aibridge-hermes-agent:latest": L_ID, TAG: P_ID},
               "c": {"running": True, "ref": "aibridge-hermes-agent:latest", "image": L_ID, "hostname": "orig"}}, open(STATE, "w"))
    open(LOG, "w").close()
    del_tag = json.load(open(STATE)); del del_tag["tags"][TAG]; json.dump(del_tag, open(STATE, "w"))   # build-<rev> arrives with `docker load`

def tarfile_(rev="abc1234"):
    d = os.path.join(tmp, "out"); os.makedirs(d, exist_ok=True)
    t = os.path.join(d, f"aibridge-hermes-agent-{rev}.tar"); open(t, "w").write("fake image tar " + rev)
    open(t + ".sha256", "w").write(hashlib.sha256(open(t, "rb").read()).hexdigest() + "  " + os.path.basename(t) + "\n")
    return t

def run(cmd, extra=None, cwd=ROOT, timeout=300):
    env = {**os.environ, "HOME": HOME, "PATH": BIN + ":" + os.environ["PATH"], "FAKE_STATE": STATE, "FAKE_LOG": LOG, "FAKE_LOAD_TAG": TAG,
           "FAKE_LOAD_ID": P_ID, "AIBRIDGE_HOST": "fake@host", "MIN_FREE_GB": "1", "BUILD_DIR": os.path.join(tmp, "build"),
           "FAKE_CWD": AB, **(extra or {})}
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
def st(): return json.load(open(STATE))
def calls(): return open(LOG).read().splitlines()
MARK = lambda: os.path.join(AB, "ops", "wake", "demo.canary")
OVR = lambda: os.path.join(AB, "stacks", "demo", "canary.override.yml")
PERSIST = lambda: os.path.join(AB, "stacks", "demo", "persist")
def backups(): return glob.glob(os.path.join(HOME, "backups", "keep", "demo-pre-canary-abc1234-*.tar.gz"))
PIPE = ["ops/pipeline.sh"]

# ---- 1: the whole canary
world(); tar = tarfile_()
r = run(PIPE + ["canary", tar, "demo"])
out = r.stdout + r.stderr
chk(r.returncode == 0, "canary: the stage passes on a stack with persisted data", out)
chk(st()["tags"]["aibridge-hermes-agent:latest"] == L_ID, "canary: `latest` is where it was before the load (the tar moved it, the stage put it back)")
c = st()["c"]
chk(c["ref"] == TAG and c["image"] == P_ID and c["hostname"] == "demo" and c["running"], "canary: the stack runs build-<rev> with the fixed hostname = the stack name", c)
chk(open(OVR()).read() == f"services:\n  hermes:\n    image: {TAG}\n    hostname: demo\n", "canary: the override pins the image and the hostname")
mk = json.load(open(MARK()))
chk(mk["image"] == TAG and mk["rev"] == "abc1234" and backups() == [mk["backup"]], "canary: the marker names the image, the revision and the backup", mk)
sys.path.insert(0, os.path.join(OPS, "wake"))
import updates
chk(updates.parse_canary(open(MARK()).read())["image"] == TAG, "canary: the waker parses the marker the stage wrote")
bk = backups()[0]
lst = subprocess.run(["tar", "tzf", bk], capture_output=True, text=True).stdout
chk("./state.db" in lst and stat.S_IMODE(os.stat(bk).st_mode) == 0o600 and not glob.glob(bk + ".part"), "canary: the backup lists state.db, is 0600 and no .part is left")
cl = calls()
i_stop = next(i for i, l in enumerate(cl) if l.startswith("docker stop")); i_run = next(i for i, l in enumerate(cl) if l.startswith("docker run") and "tar czf" in l)
i_up = next(i for i, l in enumerate(cl) if l.startswith("docker compose"))
chk(i_stop < i_run < i_up, "canary: graceful stop, then the backup, then the recreate (in that order)", cl)
up = cl[i_up]
chk("-f stacks/demo/canary.override.yml" in up and "force-recreate hermes" in up, "canary: the recreate runs WITH the override", up)
chk(open(os.path.join(AB, "ops", "wake", "demo.booted_image")).read().strip() == P_ID, "canary: booted_image records the pinned image (the waker's first-boot estimate)")
chk("canary-undo demo --restore" in out and "canary-undo demo" in out and "PASS" in out, "canary: it prints the way back", out)

# ---- 2: a second canary on the same stack is refused, nothing is touched
before = open(MARK()).read(); n = len(calls())
r = run(PIPE + ["canary", tar, "demo"])
chk(r.returncode == 1 and "already under canary" in r.stdout + r.stderr and open(MARK()).read() == before
    and not any(l.startswith("docker load") for l in calls()[n:]), "canary: a second canary on the stack is refused before anything is loaded", r.stdout + r.stderr)

# ---- 3: any other recreate of a canary stack keeps the canary (the waker's update, redeploy_router.sh, a Telegram token change)
s = st(); s["c"]["running"] = False; s["c"]["hostname"] = "changed"; json.dump(s, open(STATE, "w"))
r = run(["bash", os.path.join(AB, "ops", "recreate_hermes.sh"), "demo"], cwd=AB)
chk(r.returncode == 0 and "canary : demo is pinned to " + TAG in r.stdout and st()["c"]["ref"] == TAG and st()["c"]["hostname"] == "demo",
    "recreate_hermes.sh: with a marker it starts the stack WITH the override (pinned image, stable hostname) and verifies that image, not latest", r.stdout + r.stderr)
s = st(); s["c"]["running"] = False; json.dump(s, open(STATE, "w"))
os.unlink(OVR())
r = run(["bash", os.path.join(AB, "ops", "recreate_hermes.sh"), "demo"], cwd=AB)
chk(r.returncode == 2 and "demo.canary exists but stacks/demo/canary.override.yml does not" in r.stderr,
    "recreate_hermes.sh: a marker without its override is refused (never silently on latest)", r.stdout + r.stderr)
open(OVR(), "w").write(f"services:\n  hermes:\n    image: aibridge-hermes-agent:latest\n    hostname: demo\n")
r = run(["bash", os.path.join(AB, "ops", "recreate_hermes.sh"), "demo"], cwd=AB)
chk(r.returncode == 2 and "does not pin an aibridge-hermes-agent:build-<rev> image" in r.stderr, "recreate_hermes.sh: an override that does not pin a build tag is refused", r.stderr)
open(OVR(), "w").write(f"services:\n  hermes:\n    image: {TAG}\n    hostname: demo\n")

# ---- 4: deploy refuses while a marker exists; --include-canary only ends it after the other checks
world(); tar = tarfile_()
r = run(PIPE + ["deploy", tar], {"FAKE_SSH_CANARIES": f"demo {TAG}"})
chk(r.returncode == 1 and "canary markers exist" in r.stderr and f"demo {TAG}" in r.stderr and "--include-canary" in r.stderr, "deploy: refuses while a canary marker exists, naming it", r.stderr)
chk(not any("rm -f ops/wake" in l for l in calls()), "deploy: the refusal removes nothing")
r = run(PIPE + ["deploy", tar, "--include-canary"], {"FAKE_SSH_CANARIES": f"demo {TAG}"})
chk(r.returncode == 1 and "HEAD is" in r.stderr and not any("canary.override.yml" in l for l in calls()),
    "deploy --include-canary: a failed check (the tar is not HEAD's) ends no canary", r.stderr)
r = run(PIPE + ["deploy", tar], {"FAKE_SSH_CANARIES": ""})
chk("canary markers exist" not in r.stderr, "deploy: without markers the canary check is silent", r.stderr)
src = open(os.path.join(OPS, "pipeline.sh")).read()
i_inc, i_check = src.index("--include-canary: canary of"), src.index("origin/main does not have")
i_ops = src.index('ops/deploy_ops.sh --apply || exit 1')
i_rr = src.index('ops/redeploy_router.sh "$@"')
chk(i_check < i_ops < i_inc < i_rr, "deploy --include-canary: ends the canaries after every check and deploy_ops.sh, right before redeploy_router.sh")

# ---- 5: redeploy_router.sh refuses a canary stack (a stub stands in for the selftests so the guard's pass-through is visible)
root = os.path.join(tmp, "router"); os.makedirs(os.path.join(root, "ops"), exist_ok=True)
shutil.copy(os.path.join(OPS, "redeploy_router.sh"), os.path.join(root, "ops", "redeploy_router.sh"))
open(os.path.join(root, "ops", "run_selftests.sh"), "w").write("#!/bin/bash\nexit 1\n"); os.chmod(os.path.join(root, "ops", "run_selftests.sh"), 0o755)
r = run(["ops/redeploy_router.sh", "demo", "other"], {"FAKE_SSH_CANARIES": f"demo {TAG}"}, cwd=root)
chk(r.returncode == 1 and "stack demo is under canary" in r.stderr and "a selftest failed" not in r.stderr, "redeploy_router.sh: refuses a stack under canary before anything is shipped", r.stderr)
r = run(["ops/redeploy_router.sh", "other"], {"FAKE_SSH_CANARIES": f"demo {TAG}"}, cwd=root)
chk(r.returncode == 1 and "a selftest failed" in r.stderr and "under canary" not in r.stderr, "redeploy_router.sh: a stack without a marker goes on (here to the stubbed selftests)", r.stderr)
r = run(["ops/redeploy_router.sh", "demo"], {"FAKE_SSH_CANARIES": ""}, cwd=root)
chk("under canary" not in r.stderr, "redeploy_router.sh: no markers, no refusal", r.stderr)

# ---- 6: canary-undo
world(); tar = tarfile_()
r = run(PIPE + ["canary", tar, "demo"]); assert r.returncode == 0, r.stdout + r.stderr
open(os.path.join(PERSIST(), "canary-note"), "w").write("written during the canary"); open(os.path.join(PERSIST(), "state.db"), "w").write("migrated")
r = run(PIPE + ["canary-undo", "demo"])
c = st()["c"]
chk(r.returncode == 0 and not os.path.exists(MARK()) and not os.path.exists(OVR()) and c["ref"] == "aibridge-hermes-agent:latest" and c["image"] == L_ID,
    "canary-undo: marker and override are gone and the stack is recreated on latest", r.stdout + r.stderr)
chk(os.path.exists(os.path.join(PERSIST(), "canary-note")) and open(os.path.join(PERSIST(), "state.db")).read() == "migrated" and backups(),
    "canary-undo: without --restore the persisted data is untouched and the backup stays")
r = run(PIPE + ["canary-undo", "demo"])
chk(r.returncode == 1 and "no canary on demo" in r.stdout + r.stderr, "canary-undo: a stack with no canary says so", r.stdout + r.stderr)

# ---- 7: canary-undo --restore
world(); tar = tarfile_()
r = run(PIPE + ["canary", tar, "demo"]); assert r.returncode == 0, r.stdout + r.stderr
open(os.path.join(PERSIST(), "canary-note"), "w").write("written during the canary"); open(os.path.join(PERSIST(), "state.db"), "w").write("migrated")
r = run(PIPE + ["canary-undo", "demo", "--restore"])
kept = glob.glob(os.path.join(AB, "stacks", "demo", "persist.canary-*"))
chk(r.returncode == 0 and open(os.path.join(PERSIST(), "state.db")).read() == "original" and not os.path.exists(os.path.join(PERSIST(), "canary-note")),
    "canary-undo --restore: the persisted data is the pre-canary backup again", r.stdout + r.stderr)
chk(len(kept) == 1 and open(os.path.join(kept[0], "state.db")).read() == "migrated" and not os.path.exists(MARK()) and st()["c"]["image"] == L_ID,
    "canary-undo --restore: the canary's own data is kept aside, the canary is ended, the stack is on latest")
world(); r = run(PIPE + ["canary", tarfile_(), "demo"]); assert r.returncode == 0
for b in backups(): os.unlink(b)
n = len(calls()); r = run(PIPE + ["canary-undo", "demo", "--restore"])
chk(r.returncode == 1 and "is not there: nothing was changed" in r.stdout + r.stderr and os.path.exists(MARK()) and st()["c"]["ref"] == TAG
    and not any(l.startswith("docker stop") for l in calls()[n:]), "canary-undo --restore: a missing backup is refused before the stack is stopped", r.stdout + r.stderr)
r = run(PIPE + ["canary-undo", "demo"]); chk(r.returncode == 0 and not os.path.exists(MARK()), "canary-undo: without --restore it works with no backup")

# ---- 8: failures
world()
os.unlink(os.path.join(PERSIST(), "state.db"))
r = run(PIPE + ["canary", tarfile_(), "demo"])
chk(r.returncode == 1 and "does not list state.db" in r.stdout + r.stderr and not os.path.exists(MARK()) and not os.path.exists(OVR())
    and not backups() and not glob.glob(os.path.join(HOME, "backups", "keep", "*.part")) and not st()["c"]["running"],
    "canary: a backup without state.db aborts, removes the marker and override and leaves no .part", r.stdout + r.stderr)
world()
r = run(PIPE + ["canary", tarfile_(), "demo"], {"FAKE_UP_FAIL": "1"})
chk(r.returncode == 1 and os.path.exists(MARK()) and backups() and "canary-undo demo --restore" in r.stdout + r.stderr,
    "canary: a failed recreate keeps the marker (the stack stays pinned) and says how to retry or abandon", r.stdout + r.stderr)
world()
r = run(PIPE + ["canary", tarfile_(), "hernik"])
chk(r.returncode == 1 and "hernik" in r.stderr and not any(l.startswith("docker load") for l in calls()), "canary: hernik (no per-stack compose) is refused", r.stderr)
r = run(PIPE + ["canary", tarfile_(), "../x"]); chk(r.returncode == 1 and "bad stack name" in r.stderr, "canary: a path-like stack name is refused", r.stderr)
r = run(PIPE + ["canary", tarfile_()]); chk(r.returncode == 1 and "usage" in r.stderr, "canary: the stack is required")
os.unlink(os.path.join(AB, "ops", "recreate_hermes.sh"))
shutil.copy(os.path.join(OPS, "recreate_hermes.sh"), os.path.join(AB, "ops", "recreate_hermes.sh"))
s = open(os.path.join(AB, "ops", "recreate_hermes.sh")).read().replace("canary", "kanary"); open(os.path.join(AB, "ops", "recreate_hermes.sh"), "w").write(s)
n = len(calls()); r = run(PIPE + ["canary", tarfile_(), "demo"])
chk(r.returncode == 1 and "do not know canaries" in r.stdout + r.stderr and not any(l.startswith("ssh docker load") for l in calls()[n:]) and not os.path.exists(MARK()),
    "canary: a host whose recreate script does not know canaries is refused before the load", r.stdout + r.stderr)

# ---- 9: syntax of everything touched
for f in ("pipeline.sh", "recreate_hermes.sh", "redeploy_router.sh"):
    chk(subprocess.run(["bash", "-n", os.path.join(OPS, f)]).returncode == 0, f"{f}: valid shell")

shutil.rmtree(tmp, ignore_errors=True)
print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
