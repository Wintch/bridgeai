#!/usr/bin/env python3
"""Keep a shared project (the jobfinder today) up to date in every person's stack, without touching their data.

The operator's desktop publishes a release (ops/project_publish.py: committed files only, private-string check) into
~/aibridge/releases/<project>/<id>.tgz + <id>.json and runs `project_sync.py apply <project> <id>` here. For each
stack in the release, inside stacks/<stack>/workdir/<dest>:
  - a system file the person never edited (it equals some version from the project's history) is replaced by the new
    one; one that is gone from the project is removed;
  - a system file the person (or their agent) edited is a contribution: when the project also changed it, the
    person's version is saved under releases/<project>/aportes/<stack>/<date>/ with a diff and the new one goes in;
    when the project did not change it since the last release, it stays as it is. The operator reviews them by hand;
  - the person's own layer (the release's "protect" list, also checked against a bad release) and the stack's local
    replacements ("keep_local", e.g. the Docker-free `cops`) are never written; nothing is written or removed through
    a symlink or outside the project folder, and a file that cannot be read is left alone and reported;
  - each file is checked again right before it is replaced, so an edit saved meanwhile is kept as a contribution;
  - dependencies are installed when package.json/package-lock.json differ from what node_modules was built from
    (a marker inside it), aside and swapped in by Hermes's own image as root (node_modules is root's, as the
    installer left it); a failed install keeps the old ones and is retried at most hourly;
  - a stack with a long job registered (/workdir/jobs/*.json) waits.
Exit 0 done, 1 done with something to look at, 75 retry later (busy stack, failed install). The operator gets a
message only when something needs a human (contributions, files not written, a failed install); every apply is
logged in releases/<project>/log.jsonl. State per stack: releases/<project>/state-<stack>.json (backup_watch reads
it to leave the project's own files out of its shrink alarms; the person's kept edits stay watched).

  project_sync.py apply PROJECT ID [--dry-run]     project_sync.py estado [PROJECT]     project_sync.py aportes [PROJECT]
"""
import difflib, glob, hashlib, json, os, re, shutil, stat, subprocess, sys, tarfile, time

ROOT = os.environ.get("AIBRIDGE_ROOT", os.path.expanduser("~/aibridge"))
RELEASES = os.environ.get("RELEASES_DIR", os.path.join(ROOT, "releases"))
NPM = os.environ.get("PROJECT_SYNC_NPM", "1") == "1"
IMAGE = os.environ.get("PROJECT_SYNC_IMAGE", "aibridge-hermes-agent:latest")
KEEP_RELEASES, REMOVED_DAYS, NPM_RETRY_S, TEMPFAIL = 5, 14, 3600, 75
UNSAFE, UNREADABLE = "symlink", "unreadable"


def blob(data):
    """git's own object id of a file's bytes, so the desktop can name every version the project ever had."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def workdir(stack):
    w = os.path.join(ROOT, "stacks", stack, "workdir")
    if stack == "hernik" and not os.path.isdir(w):            # the operator's own stack predates stacks/
        return os.path.join(ROOT, "user1-workdir"), "user1-workdir/"
    return w, "workdir/"


def notify(kind, key, text):
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
        import notify as n
        n.send(text) if kind == "send" else n.alert(key, text, quiet=21600) if kind == "alert" else n.resolve(key)
    except Exception as e:                                       # the journal still has the text
        print(f"(notify failed: {type(e).__name__})", file=sys.stderr)


def safe(target, p):
    """True when every component from the project folder down to p is a real directory/file, not a symlink."""
    cur = target
    for part in p.split("/"):
        cur = os.path.join(cur, part)
        try:
            if stat.S_ISLNK(os.lstat(cur).st_mode):
                return False
        except FileNotFoundError:
            return True
    return True


def current(target, p):
    """The blob of the person's file, None when missing, UNSAFE through a symlink, UNREADABLE when it cannot be read."""
    if not safe(target, p):
        return UNSAFE
    try:
        return blob(open(os.path.join(target, p), "rb").read())
    except FileNotFoundError:
        return None
    except (IsADirectoryError, NotADirectoryError):
        return UNSAFE
    except OSError:
        return UNREADABLE


def write_atomic(target, p, data, mode):
    full = os.path.join(target, p)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    if not safe(target, p):
        raise OSError(0, "symlink en el camino")
    tmp = os.path.join(os.path.dirname(full), f".{os.path.basename(full)}.sync-tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(tmp, mode)
    os.replace(tmp, full)


def load_release(project, rid):
    base = os.path.join(RELEASES, project, rid)
    man = json.load(open(base + ".json"))
    if man.get("project") != project or man.get("id") != rid:
        raise SystemExit(f"{base}.json is not release {project}/{rid}")
    protect = [re.compile(p) for p in man.get("protect", [])]
    if not protect:
        raise SystemExit("release without a protect list: refused (it is what keeps the person's data out of reach)")
    bad = [p for p in man["files"] if any(r.search(p) for r in protect) or p.startswith("/") or ".." in p.split("/")]
    if bad:
        raise SystemExit(f"release {rid} would write protected or unsafe paths ({', '.join(bad[:5])}): refused whole")
    data = {}
    with tarfile.open(base + ".tgz") as t:
        for m in t.getmembers():
            if m.isfile() and m.name in man["files"]:
                data[m.name] = t.extractfile(m).read()
    wrong = [p for p, f in man["files"].items() if p not in data or blob(data[p]) != f["blob"]]
    if wrong:
        raise SystemExit(f"release {rid}: {len(wrong)} file(s) missing or different from the manifest ({', '.join(wrong[:3])}): refused")
    return man, data, protect


def state_path(project, stack):
    return os.path.join(RELEASES, project, f"state-{stack}.json")


def plan(man, protect, target, state):
    """[(action, path, blob seen)] for one stack. action: write | remove | keep-local | save-and-write |
    keep-edited-gone | skip-unsafe | skip-unreadable."""
    keep = set(man.get("keep_local", [])) | set(man.get("links", []))
    known, shipped = man.get("known", {}), state.get("files", {})
    out = []
    for p, f in sorted(man["files"].items()):
        if p in keep:
            continue
        cur = current(target, p)
        if cur == f["blob"]:
            continue
        if cur in (UNSAFE, UNREADABLE):
            out.append(("skip-" + ("unsafe" if cur == UNSAFE else "unreadable"), p, cur))
        elif cur is None or cur in known.get(p, ()) or cur == shipped.get(p):
            out.append(("write", p, cur))                    # missing, or a version the project itself had
        elif shipped.get(p) == f["blob"]:
            out.append(("keep-local", p, cur))                # the person's edit; the project did not touch it since
        else:
            out.append(("save-and-write", p, cur))            # both changed it: theirs is kept for review, ours goes in
    for p in sorted((set(known) | set(shipped)) - set(man["files"]) - keep):
        if any(r.search(p) for r in protect):
            continue
        cur = current(target, p)
        if cur is None:
            continue
        if cur in (UNSAFE, UNREADABLE):
            out.append(("skip-" + ("unsafe" if cur == UNSAFE else "unreadable"), p, cur))
        else:
            out.append(("remove", p, cur) if cur in known.get(p, ()) or cur == shipped.get(p) else ("keep-edited-gone", p, cur))
    return out


def save_contribution(project, stack, stamp, target, p, new):
    d = os.path.join(RELEASES, project, "aportes", stack, stamp)
    dst = os.path.join(d, p)
    os.makedirs(os.path.dirname(dst), mode=0o700, exist_ok=True)
    os.chmod(os.path.join(RELEASES, project, "aportes"), 0o700)
    shutil.copyfile(os.path.join(target, p), dst)
    try:
        theirs = open(dst, encoding="utf-8").read().splitlines(keepends=True)
        ours = new.decode("utf-8").splitlines(keepends=True) if new is not None else []
        with open(dst + ".diff", "w") as f:
            f.writelines(difflib.unified_diff(ours, theirs, f"proyecto/{p}", f"{stack}/{p}"))
    except (UnicodeDecodeError, ValueError):
        pass                                                   # a binary file: the copy alone
    return os.path.relpath(dst, RELEASES)


def deps_sha(target):
    h = hashlib.sha1()
    for f in ("package.json", "package-lock.json"):
        try:
            h.update(open(os.path.join(target, f), "rb").read())
        except OSError:
            h.update(b"-")
    return h.hexdigest()


def npm_needed(target):
    if not os.path.isfile(os.path.join(target, "package.json")):
        return False
    try:
        return open(os.path.join(target, "node_modules", ".sync-deps")).read().strip() != deps_sha(target)
    except OSError:
        return True


def npm_install(target):
    """npm ci in a side folder and swap, all inside Hermes's image as root (node_modules belongs to root, as
    install_jobfinder.sh made it; Hermes's node has the right ABI). The old node_modules stays unless ci worked."""
    sha = deps_sha(target)
    script = ("set -u; cd /jf; rm -rf .sync-npm; mkdir .sync-npm && cp package.json .sync-npm/ && "
              "{ [ ! -f package-lock.json ] || cp package-lock.json .sync-npm/; } && cd .sync-npm && "
              "npm ci --ignore-scripts --no-audit --no-fund >/dev/null 2>&1 && test -d node_modules || { cd /jf; rm -rf .sync-npm; exit 1; }; "
              f"echo {sha} > node_modules/.sync-deps; cd /jf; rm -rf .node_modules.old; "
              "[ ! -d node_modules ] || mv node_modules .node_modules.old; mv .sync-npm/node_modules node_modules; "
              "rm -rf .node_modules.old .sync-npm")
    try:
        r = subprocess.run(["docker", "run", "--rm", "--network", "aibridge_default", "--entrypoint", "sh", "-v", f"{target}:/jf",
                            IMAGE, "-c", script], capture_output=True, text=True, timeout=1200)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def apply_stack(project, man, data, protect, stack, dry):
    """One stack. Returns (status, summary line, contributions)."""
    wd, prefix = workdir(stack)
    target = os.path.join(wd, man["dest"])
    if not os.path.isdir(target) or os.path.islink(target):
        return "absent", f"{stack}: no tiene {man['dest']} instalado (ops/install_jobfinder.sh), salteado", []
    if glob.glob(os.path.join(wd, "jobs", "*.json")):
        return "busy", f"{stack}: tiene un trabajo largo corriendo; se aplica en el próximo intento", []
    sp = state_path(project, stack)
    state = json.load(open(sp)) if os.path.isfile(sp) else {}
    steps = plan(man, protect, target, state)
    if dry:
        counts = {}
        for a, _, _ in steps:
            counts[a] = counts.get(a, 0) + 1
        return "dry", f"{stack}: " + (", ".join(f"{a} {n}" for a, n in sorted(counts.items())) or "al día"), \
            [p for a, p, _ in steps if a not in ("write", "remove")]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    contrib, failed, changed, removed = [], [], set(), dict(state.get("removed", {}))
    local = dict(state.get("local", {}))
    for a, p, seen in steps:
        try:
            if a.startswith("skip-"):
                failed.append(f"{p} ({'symlink' if a == 'skip-unsafe' else 'no se puede leer'})")
                continue
            now = current(target, p)
            if now != seen:                                      # edited between the plan and now: theirs is kept
                a = {"write": "save-and-write", "remove": "keep-edited-gone"}.get(a, a)
                if now in (UNSAFE, UNREADABLE, None):
                    failed.append(f"{p} (cambió durante la actualización)")
                    continue
            if a in ("write", "save-and-write"):
                if a == "save-and-write":
                    contrib.append(save_contribution(project, stack, stamp, target, p, data[p]))
                write_atomic(target, p, data[p], man["files"][p].get("mode", 0o644))
                changed.add(p)
                local.pop(p, None)
            elif a == "remove":
                os.remove(os.path.join(target, p))
                changed.add(p)
                removed[p] = int(time.time())
                local.pop(p, None)
            else:                                                # keep-local / keep-edited-gone: reported once per content
                if local.get(p) != now:
                    contrib.append(f"{stack}/{p} (se dejó el de la persona)")
                local[p] = now
        except OSError as e:
            failed.append(f"{p} ({e.strerror or type(e).__name__})")
    status, npm = ("partial" if failed else "ok"), ""
    if NPM and npm_needed(target):
        if time.time() - state.get("npm_failed", 0) < NPM_RETRY_S:
            status, npm = "npm-wait", ", dependencias pendientes (reintento en menos de una hora)"
        elif npm_install(target):
            npm = ", dependencias instaladas"
            state.pop("npm_failed", None)
            notify("resolve", f"ps:{project}:{stack}:npm", None)
        else:
            status, npm = "npm-failed", ", FALLÓ la instalación de dependencias (quedaron las anteriores; se reintenta)"
            state["npm_failed"] = int(time.time())
    shipped = {p: f["blob"] for p, f in man["files"].items() if p not in man.get("keep_local", [])}
    cutoff = time.time() - REMOVED_DAYS * 86400
    json.dump({"release": man["id"], "version": man.get("version"), "applied": int(time.time()), "prefix": prefix + man["dest"] + "/",
               "files": shipped, "local": {p: b for p, b in local.items() if os.path.isfile(os.path.join(target, p))},
               "removed": {p: t for p, t in removed.items() if t > cutoff},
               **({"npm_failed": state["npm_failed"]} if "npm_failed" in state else {})}, open(sp + ".tmp", "w"))
    os.replace(sp + ".tmp", sp)
    try:
        write_atomic(target, ".release.json", json.dumps({"project": project, "version": man.get("version"), "commit":
                     man.get("commit", "")[:12], "applied": time.strftime("%Y-%m-%d %H:%M")}).encode(), 0o644)
    except OSError:
        pass
    line = f"{stack}: {len(changed)} archivo(s) actualizados{npm}" if changed or npm else f"{stack}: ya estaba al día"
    if failed:
        line += f"; NO toqué {len(failed)}: {', '.join(failed[:3])}"
    return status, line, contrib


def cmd_apply(project, rid, dry):
    man, data, protect = load_release(project, rid)
    results = []
    for s in man["stacks"]:
        try:
            results.append(apply_stack(project, man, data, protect, s, dry))
        except Exception as e:                                   # one stack never stops the others or the report
            results.append(("error", f"{s}: ERROR {type(e).__name__}: {str(e)[:120]}", []))
    head = f"{project} {man.get('version') or ''} ({rid[:8]})"
    lines, contrib = [r[1] for r in results], [c for r in results for c in r[2]]
    if dry:
        print(head + " — simulación\n" + "\n".join(lines))
        if contrib:
            print("aportes que se guardarían/conservarían, o archivos que no se tocarían:\n" + "\n".join(f"  {c}" for c in contrib[:40]))
        return 0
    text = f"🔄 {head} aplicado\n" + "\n".join(lines)
    if contrib:
        text += f"\nAportes para revisar ({len(contrib)}):\n" + "\n".join(f"  {c}" for c in contrib[:12]) + \
                ("\n  …" if len(contrib) > 12 else "") + f"\nproject_sync.py aportes {project}"
    print(text)
    st = {r[0] for r in results}
    with open(os.path.join(RELEASES, project, "log.jsonl"), "a") as f:
        f.write(json.dumps({"ts": int(time.time()), "release": rid, "stacks": [r[1] for r in results], "contributions": len(contrib)}) + "\n")
    if contrib or st & {"partial", "error"}:
        notify("send", None, text)                               # routine updates stay in the log: the branch moves often
    for s, r in zip(man["stacks"], results):
        if r[0] == "npm-failed":
            notify("alert", f"ps:{project}:{s}:npm", f"⚠️ {project}: {r[1]}")
    jsons = [j for j in glob.glob(os.path.join(RELEASES, project, "*.json")) if not os.path.basename(j).startswith("state-")]
    for old in sorted(jsons, key=os.path.getmtime)[:-KEEP_RELEASES]:
        for ext in (".json", ".tgz"):
            try:
                os.remove(old[:-5] + ext)
            except OSError:
                pass
    return TEMPFAIL if st & {"busy", "npm-failed", "npm-wait"} else 1 if st & {"partial", "error"} else 0


def cmd_estado(project):
    for sp in sorted(glob.glob(os.path.join(RELEASES, project or "*", "state-*.json"))):
        s = json.load(open(sp))
        print(f"{sp.split('/')[-2]} {os.path.basename(sp)[6:-5]}: versión {s.get('version')} ({s.get('release', '')[:8]}), "
              f"aplicada {time.strftime('%Y-%m-%d %H:%M', time.localtime(s.get('applied', 0)))}, "
              f"{len(s.get('local', {}))} archivo(s) editados por la persona conservados"
              + (", dependencias pendientes" if "npm_failed" in s else ""))
    return 0


def cmd_aportes(project):
    rows = sorted(glob.glob(os.path.join(RELEASES, project or "*", "aportes", "*", "*")))
    if not rows:
        print("No hay aportes guardados.")
    for d in rows:
        files = [os.path.relpath(os.path.join(dp, f), d) for dp, _, fs in os.walk(d) for f in fs if not f.endswith(".diff")]
        print(f"{os.path.relpath(d, RELEASES)}: {len(files)} archivo(s): {', '.join(sorted(files)[:8])}")
    return 0


def main(argv):
    if argv[:1] == ["apply"] and len(argv) >= 3:
        return cmd_apply(argv[1], argv[2], "--dry-run" in argv)
    if argv[:1] == ["estado"]:
        return cmd_estado(argv[1] if len(argv) > 1 else None)
    if argv[:1] == ["aportes"]:
        return cmd_aportes(argv[1] if len(argv) > 1 else None)
    print(__doc__)
    return 2


if __name__ == "__main__":
    os.umask(0o022)
    sys.exit(main(sys.argv[1:]))
