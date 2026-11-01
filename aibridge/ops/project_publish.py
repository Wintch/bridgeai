#!/usr/bin/env python3
"""Desktop side of the project sync: when a shared project (the jobfinder) has a new commit on its branch, pack it and
hand it to VM105, which installs it in every listed stack (ops/project_sync.py: the people's data and their own edits
are never overwritten silently). Meant for a systemd --user timer on the operator's desktop; a run with nothing new
does nothing.

  project_publish.py [run] [PROJECT] [--dry-run] [--force]   publish what changed (--dry-run: check, simulate on the VM)
  project_publish.py aportes [PROJECT]                        copy the people's saved contributions down to review them

What travels: the files git tracks at the branch's last COMMIT (work in progress never ships; symlinks neither), plus
the few untracked system files listed in "extra" (from the working tree), once the commit is "settle_min" minutes old
(an agent commits in bursts). Before anything leaves the desktop:
  - content and file names are checked against the operator's private strings (~/.config/bridgeai/private-replacements.txt,
    the list privacy_scan.sh uses), and names against its forbidden file names. "leak_allow" ({"path": regex, "text":
    literal}) lets one exact string through in matching paths only (upstream test fixtures with example LAN addresses);
  - a package-lock.json that does not match package.json is refused (npm ci would fail on every stack).
A refused release alerts the operator once (notify.py alert, quiet 6 h) and is not retried until the commit changes.
The manifest carries every version each file had in the last 180 days of history, so the VM can tell a person's edit
from a file that is merely old.

Config (private, never in git): ~/.config/bridgeai/projects.json, see ops/projects.json.example.
State: ~/.local/state/bridgeai/projects.json (last release fully applied per project; a refused one).
"""
import base64, hashlib, io, json, os, re, shlex, shutil, subprocess, sys, tarfile, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.environ.get("PROJECTS_CONFIG", os.path.expanduser("~/.config/bridgeai/projects.json"))
STATE = os.environ.get("PROJECTS_STATE", os.path.expanduser("~/.local/state/bridgeai/projects.json"))
PRIVATE = os.environ.get("PRIVATE_REPLACEMENTS", os.path.expanduser("~/.config/bridgeai/private-replacements.txt"))
HISTORY = os.environ.get("PROJECTS_HISTORY", "180 days ago")
FORBIDDEN_NAMES = re.compile(r"(^|/)(credentials\.txt|auth\.json|state\.db|webui\.db|\.env)$")   # as privacy_scan.sh
DEP_KEYS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
TEMPFAIL = 75


class Refused(Exception):
    """The release must not go out as it is; the text says why (file names and counts only)."""


def git(src, *a, raw=False):
    r = subprocess.run(["git", "-C", src, *a], capture_output=True, check=True)
    return r.stdout if raw else r.stdout.decode()


def blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def leak_pattern():
    r = subprocess.run(["bash", "-c", f'. {shlex.quote(HERE)}/lib/private_pattern.sh && private_pattern {shlex.quote(PRIVATE)}'],
                       capture_output=True, text=True)
    if r.returncode or not r.stdout:
        raise Refused(f"no hay lista privada en {PRIVATE} (o está vacía): sin ese chequeo no se publica nada")
    return r.stdout


def grep(pat, cwd=None, text=None, args=("-rlaiP",)):
    r = subprocess.run(["grep", *args, "--", pat, *(["."] if text is None else [])], cwd=cwd, input=text,
                       capture_output=True, text=True)
    if r.returncode >= 2:
        raise Refused("el patrón privado no compila (grep -P): no se publica nada")
    return r.stdout


def leaks(files, names, allow):
    """Paths whose content (after taking out the allowed exact strings in their paths) or whose name matches a
    private string, plus forbidden file names."""
    pat = leak_pattern()
    allow = [(re.compile(a["path"]), re.compile(rb"(?<![\w.])" + re.escape(a["text"].encode()) + rb"(?![\w])")) for a in allow]
    with tempfile.TemporaryDirectory() as d:
        for p, (data, _) in files.items():
            for pr, tr in allow:
                if pr.search(p):
                    data = tr.sub(b"", data)
            os.makedirs(os.path.join(d, os.path.dirname(p)), exist_ok=True)
            open(os.path.join(d, p), "wb").write(data)
        hits = {l[2:] for l in grep(pat, cwd=d).splitlines()}
    hits |= set(grep(pat, text="\n".join(names) + "\n", args=("-aiP",)).splitlines())
    hits |= {n for n in names if FORBIDDEN_NAMES.search(n)}
    return sorted(hits)


def lock_in_sync(files):
    """npm ci refuses a lock whose root entry differs from package.json; catch that here, once, not on every stack."""
    if "package.json" not in files or "package-lock.json" not in files:
        return True
    try:
        pj = json.loads(files["package.json"][0])
        root = json.loads(files["package-lock.json"][0]).get("packages", {}).get("", {})
    except ValueError:
        return False
    return all((pj.get(k) or {}) == (root.get(k) or {}) for k in DEP_KEYS)


def build(name, p):
    """(release id, manifest, tar bytes, files) of the project's current commit + extras."""
    src = os.path.expanduser(p["src"])
    commit = git(src, "rev-parse", p.get("ref", "HEAD")).strip()
    files, links = {}, set()
    for line in git(src, "ls-tree", "-r", "-z", commit).split("\0"):
        if not line:
            continue
        meta, path = line.split("\t", 1)
        mode, kind, obj = meta.split()
        if kind != "blob" or mode == "120000":
            links.add(path)                                    # symlinks and submodules are not shipped, nor judged
            continue
        files[path] = (git(src, "cat-file", "blob", obj, raw=True), 0o755 if mode == "100755" else 0o644)
    for path in p.get("extra", []):
        full = os.path.join(src, path)
        if os.path.isfile(full) and not os.path.islink(full):
            files[path] = (open(full, "rb").read(), 0o755 if os.stat(full).st_mode & 0o100 else 0o644)
    protect = [re.compile(x) for x in p.get("protect", [])]
    hit = [f for f in files if any(r.search(f) for r in protect)]
    if hit:
        raise Refused(f"el commit versiona rutas protegidas ({', '.join(hit[:5])})")
    known = {}
    tok = [t.lstrip("\n") for t in git(src, "log", "-z", f"--since={HISTORY}", "-m", "--raw", "--no-abbrev", "--no-renames",
                                      "--format=", commit).split("\0")]
    i = 0
    while i < len(tok) - 1:                                   # ":oldmode newmode oldsha newsha S" NUL path NUL
        if tok[i].startswith(":"):
            m, path = tok[i][1:].split(), tok[i + 1]
            if "120000" in m[:2] or "160000" in m[:2]:
                links.add(path)
            else:
                known.setdefault(path, set()).update(x for x in m[2:4] if set(x) != {"0"})
            i += 2
        else:
            i += 1
    for path, (data, _) in files.items():
        known.setdefault(path, set()).add(blob(data))
    for path in links:
        known.pop(path, None)
    ver = files.get("VERSION", (b"", 0))[0].decode(errors="replace").split("#")[0].strip()
    shape = json.dumps([p.get(k) for k in ("dest", "stacks", "keep_local", "protect")], sort_keys=True).encode()
    digest = hashlib.sha1(b"".join(files[x][0] for x in p.get("extra", []) if x in files) + shape).hexdigest()[:6]
    rid = commit[:12] + "-" + digest
    man = {"project": name, "id": rid, "commit": commit, "version": ver, "created": int(time.time()), "dest": p["dest"],
           "stacks": p["stacks"], "keep_local": p.get("keep_local", []), "protect": p.get("protect", []),
           "links": sorted(links), "files": {f: {"blob": blob(d), "mode": m} for f, (d, m) in files.items()},
           "known": {f: sorted(v) for f, v in known.items()}}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for f, (d, m) in sorted(files.items()):
            ti = tarfile.TarInfo(f)
            ti.size, ti.mode, ti.mtime = len(d), m, man["created"]
            t.addfile(ti, io.BytesIO(d))
    return rid, man, buf.getvalue(), files


def vm_run(vm, cmd):
    """A command in ~/aibridge on the VM (or, for tests, "local:<aibridge root>")."""
    if vm.startswith("local:"):
        return subprocess.run(cmd, shell=True, env=dict(os.environ, AIBRIDGE_ROOT=vm[6:]), cwd=vm[6:], capture_output=True, text=True)
    return subprocess.run(["ssh", "-o", "BatchMode=yes", vm, f"cd ~/aibridge && {cmd}"], capture_output=True, text=True, timeout=1800)


def vm_put(vm, project, rid, man, tar):
    """Upload the release unless the VM already has it (a busy stack retries every 15 min: 25 MB each time otherwise).
    The manifest is renamed into place last: a release is complete only when its .json exists."""
    q = shlex.quote(project)
    if vm_run(vm, f"test -s releases/{q}/{rid}.json -a -s releases/{q}/{rid}.tgz").returncode == 0:
        return
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, rid + ".tgz"), "wb").write(tar)
        json.dump(man, open(os.path.join(d, rid + ".json.part"), "w"))
        if vm.startswith("local:"):
            dst = os.path.join(vm[6:], "releases", project)
            os.makedirs(dst, exist_ok=True)
            for f in (rid + ".tgz", rid + ".json.part"):
                shutil.copyfile(os.path.join(d, f), os.path.join(dst, f))
        else:
            subprocess.run(["ssh", "-o", "BatchMode=yes", vm, f"mkdir -p ~/aibridge/releases/{q}"], check=True, timeout=60)
            subprocess.run(["scp", "-q", "-o", "BatchMode=yes", os.path.join(d, rid + ".tgz"), os.path.join(d, rid + ".json.part"),
                            f"{vm}:aibridge/releases/{project}/"], check=True, timeout=1800)
    if vm_run(vm, f"mv releases/{q}/{rid}.json.part releases/{q}/{rid}.json").returncode:
        raise OSError("could not finish the upload on the VM")


def alert(vm, key, text):
    vm_run(vm, f"python3 ops/lib/notify.py alert {shlex.quote(key)} {shlex.quote(text)} --quiet 21600")


def resolve(vm, key):
    vm_run(vm, f"python3 ops/lib/notify.py resolve {shlex.quote(key)}")


def save(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(state, open(STATE + ".tmp", "w"), indent=1)
    os.replace(STATE + ".tmp", STATE)


def publish_one(vm, name, p, state, dry, force):
    src = os.path.expanduser(p["src"])
    age = time.time() - int(git(src, "log", "-1", "--format=%ct", p.get("ref", "HEAD")).strip())
    if age < 60 * p.get("settle_min", 10) and not force:
        return 0                                                # the agent may still be committing: next run
    rid, man, tar, files = build(name, p)
    if not force and not dry and rid in (state.get(name), state.get(name + "#refused")):
        return 0
    try:
        bad = leaks(files, list(files), p.get("leak_allow", []))
        # names of files the project HAD (only used to clean them up on the stacks) never block a release, but one
        # with a private string in it does not travel either: that old copy is simply not cleaned up
        hidden = set(grep(leak_pattern(), text="\n".join(man["known"]) + "\n", args=("-aiP",)).splitlines())
        if hidden:
            man["known"] = {k: v for k, v in man["known"].items() if k not in hidden}
        if bad:
            raise Refused(f"{len(bad)} archivo(s) con datos privados o nombres prohibidos: {', '.join(bad[:5])}")
        if not lock_in_sync(files):
            raise Refused("package-lock.json no coincide con package.json (npm ci fallaría en cada stack): en el repo, "
                          "npm install --package-lock-only")
        vm_put(vm, name, rid, man, tar)
        r = vm_run(vm, f"python3 ops/project_sync.py apply {shlex.quote(name)} {rid}" + (" --dry-run" if dry else ""))
    except Refused as e:
        msg = f"⛔ {name}: no se publicó {rid[:8]}: {e}"
        print(msg)
        if not dry:
            state[name + "#refused"] = rid
            save(state)
            alert(vm, f"pp:{name}", msg)
        return 1
    print((r.stdout + r.stderr).strip())
    if dry:
        return r.returncode
    # 0 applied; 1 applied but something needs a look (the VM already said so); 75 a stack was busy or its npm failed:
    # try again next run (same release, not uploaded again); anything else: the VM refused it
    if r.returncode in (0, 1):
        state[name] = rid
        state.pop(name + "#refused", None)
        save(state)
        resolve(vm, f"pp:{name}")
    elif r.returncode != TEMPFAIL:
        state[name + "#refused"] = rid
        save(state)
        alert(vm, f"pp:{name}", f"⛔ {name}: la VM rechazó {rid[:8]} (exit {r.returncode}): {(r.stdout + r.stderr).strip()[-200:]}")
        return 1
    return 0


def run(conf, only, dry, force):
    state = json.load(open(STATE)) if os.path.isfile(STATE) else {}
    rc = 0
    for name, p in conf["projects"].items():
        if only and name != only:
            continue
        try:
            rc |= publish_one(conf["vm"], name, p, state, dry, force)
            resolve(conf["vm"], f"pp:{name}:run") if not dry else None
        except (subprocess.SubprocessError, OSError, ValueError, KeyError) as e:
            err = getattr(e, "stderr", None)
            detail = (err.decode(errors="replace") if isinstance(err, bytes) else str(err or e)).strip()[-200:]
            print(f"{name}: {type(e).__name__}: {detail}")
            alert(conf["vm"], f"pp:{name}:run", f"⚠️ {name}: el publicador falló ({type(e).__name__}); reintenta cada 15 min")
            rc = 1
    return rc


def aportes(conf, only):
    """Copy releases/<project>/aportes from the VM to the project's "aportes" folder (default ~/Documents/<project>-aportes)."""
    for name, p in conf["projects"].items():
        if only and name != only:
            continue
        dst = os.path.expanduser(p.get("aportes", f"~/Documents/{name}-aportes"))
        os.makedirs(dst, mode=0o700, exist_ok=True)
        q = shlex.quote(name)
        r = vm_run(conf["vm"], f"[ -d releases/{q}/aportes ] && tar -C releases/{q} -cf - aportes | base64 -w0")
        if r.returncode == 0 and r.stdout:
            with tarfile.open(fileobj=io.BytesIO(base64.b64decode(r.stdout)), mode="r:") as t:
                t.extractall(dst, filter="data")
        print(f"{name}: aportes en {dst}/aportes")
    return 0


def main(argv):
    conf = json.load(open(CONF))
    args = [a for a in argv if not a.startswith("--")]
    if args[:1] == ["aportes"]:
        return aportes(conf, args[1] if len(args) > 1 else None)
    if args[:1] == ["run"]:
        args = args[1:]
    return run(conf, args[0] if args else None, "--dry-run" in argv, "--force" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
