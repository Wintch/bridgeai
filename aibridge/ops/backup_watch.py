#!/usr/bin/env python3
"""Notice when a person's files are damaged, from the nightly backups, and keep their small files for a month.

Why (2026-11-01): on 2026-10-28 hereug's agent copied an old narrow variant over his job-search config (portals.yml:
151 tracked companies to 11, title keywords 16 to 4) and every scan for four days found ~1 950 postings and kept none.
Nobody noticed until he said the bot "finds nothing". The nightly backup (backup-stacks.sh, 04:15, 7 days) held the good
file, but nothing compared one night with the next, and in three more days the good copy would have been pruned.

Every night after the backup (backup-watch.timer, 05:00) this reads each new archive in ~/backups (read-only, no docker):
  * a fingerprint per text file: lines, list items ("- ...") and, for YAML/TOML files, list items per section, kept 30
    days in ~/backups/.fp/<name>/<stamp>.json.gz. Paths and counts only, never content;
  * the newest fingerprint against the last 14 days (30 while an alert is open), and an operator alert per person when:
      - a file shrank to half of its maximum or less (by lines, list items or a section's items) where the maximum was
        at least 30 lines, 20 items or 8 items in one section; a file that swung that much before needs a fall to a
        quarter, below its earlier minimum;
      - a file present on at least 5 nights is gone since its last night;
      - no new backup in 26 hours, or an archive that cannot be read (checked to the end of its gzip stream).
    The alert repeats each night while it holds and resolves when it clears. A change the person asked for: `ack`;
  * small/<name>-<stamp>.tar.gz: the person's small text files (configs, CVs, memories; at most 256 KB each; no .env,
    keys, tokens, credentials, cookies or OAuth stores), kept 30 days, so a good version survives the 7-day prune.
Built from the 2026-11-01 design panel; a dry run over the real backups (4 people x 7 nights) flagged the one real
incident on each of its nights and nothing else, and an adversarial review hardened it.

  backup_watch.py run [--dry-run]        fingerprint new archives, alert, snapshot, prune (the timer)
  backup_watch.py backfill [--dry-run]   fingerprint every archive; with --dry-run, say which nights would have alerted
  backup_watch.py status                 newest backup per person and the open alerts
  backup_watch.py ack NAME               a change the person asked for: silence what is reported now, for 14 days or
                                         until that file falls to half again or comes back
  backup_watch.py forget NAME            a person who is gone: stop watching NAME
  backup_watch.py restore NAME PATH [--stamp YYYYMMDD-HHMM]
        extract one file (by default from the night it was largest in the last 30 days) to ~/restore/NAME/STAMP/,
        never over the live file, and print how to put it back (the stack must be stopped: see backup-stacks.sh)
"""
import argparse, collections, gzip, json, os, re, sys, tarfile, time, zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
DEST = os.path.expanduser(os.environ.get("BACKUP_DIR", "~/backups"))
RESTORE = os.path.expanduser(os.environ.get("RESTORE_DIR", "~/restore"))
ARCHIVE = re.compile(r"^(?P<name>[A-Za-z0-9._-]+?)-(?P<stamp>\d{8}-\d{4})\.tar\.gz$")
TEXT = re.compile(r"\.(ya?ml|json|toml|md|txt|csv|tsv|ini|cfg|conf|html?|xml|sh|py|js|mjs)$", re.I)
YAML = re.compile(r"\.(ya?ml|toml)$", re.I)       # section names come only from real config files, never from notes
SECRET = re.compile(r"(^|/)(\.env[^/]*|auth[^/]*\.json|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|[^/]*\.(pem|key|p12|pfx)|"
                    r"[^/]*(token|secret|password|passwd|credential|oauth|cookie|api[_-]?keys?)[^/]*|keys?\.json)$|"
                    r"(^|/)(\.ssh|secrets?|[^/]*tokens?|[^/]*credentials?|[^/]*oauth[^/]*)/", re.I)
NOISE = re.compile(r"(^|/)(cache|sessions?|logs?|node_modules|\.git|tmp|__pycache__|\.npm|output|separated|web-outputs)/|"
                   r"\.(log|jsonl|lock)$|(^|/)\.gateway-log|scan-history\.tsv$", re.I)
# judged files leave out the skills: an image deploy rewrites the shipped ones (2026-11-01: a skill's tag list 14 -> 6 on
# every stack); they are still fingerprinted and copied
WATCH_SKIP = re.compile(r"(^|/)skills(-merged|-replaced)?/")
KEY = re.compile(r"^(\s*)([A-Za-z_][\w.-]*)\s*:\s*(#.*)?$")
ITEM = re.compile(r"^(\s*)-\s")
WINDOW, OPEN_WINDOW, KEEP_FP, KEEP_SMALL, STALE_H, SMALL_MAX, ACK_DAYS = 14, 30, 30, 30, 26, 256 * 1024, 14
BROKEN = (OSError, EOFError, zlib.error, tarfile.TarError, ValueError)   # a damaged archive or fingerprint raises any of these
_cache = {}   # a dry run keeps its fingerprints here instead of writing them


def state_dir(*parts):
    p = os.path.join(DEST, ".fp", *parts)
    os.makedirs(p, mode=0o700, exist_ok=True)             # makedirs gives the mode to the last level only
    for d in {os.path.join(DEST, ".fp"), p}:
        os.chmod(d, 0o700)
    return p


def forgotten():
    try:
        return set(json.load(open(os.path.join(DEST, ".fp", "forgotten.json"))))
    except (OSError, ValueError):
        return set()


def archives():
    """{name: [(stamp, path)] oldest first} of the dated archives in DEST (hand-kept ones in keep/ are not touched)."""
    out = collections.defaultdict(list)
    for f in sorted(os.listdir(DEST)) if os.path.isdir(DEST) else []:
        m = ARCHIVE.match(f)
        if m:
            out[m["name"]].append((m["stamp"], os.path.join(DEST, f)))
    gone = forgotten()
    return {n: v for n, v in out.items() if n not in gone}


def counts(text, sections):
    """(lines, list items, {yaml.section.path: items}). The section is the nearest key above with a smaller indent, so
    `title_filter: / positive: / - a` counts under title_filter.positive."""
    lines = text.splitlines()
    stack, sec, items = [], collections.Counter(), 0
    for ln in lines:
        m = KEY.match(ln) if sections else None
        if m:
            ind = len(m[1])
            while stack and stack[-1][0] >= ind:
                stack.pop()
            stack.append((ind, m[2]))
            continue
        m = ITEM.match(ln)
        if m:
            items += 1
            path = [k for i, k in stack if i <= len(m[1])]
            if path:
                sec[".".join(path)[:120]] += 1
    return len(lines), items, dict(sec)


def verify(path):
    """Read the whole gzip stream: a damaged archive can otherwise look like a shorter one (tarfile takes a bad header
    in the middle for the end), and its missing files would read as deleted."""
    with gzip.open(path, "rb") as f:
        while f.read(1 << 20):
            pass


def fingerprint(path):
    """{member path: {"size", "lines", "items", "sec"}} for the text files of one archive; sizes only for the rest."""
    verify(path)
    fp = {}
    with tarfile.open(path, "r:gz") as t:
        for m in t:
            if not m.isfile():
                continue
            e = {"size": m.size}
            if TEXT.search(m.name) and not SECRET.search(m.name) and not NOISE.search(m.name) and m.size <= 4 * 1024 * 1024:
                e["lines"], e["items"], sec = counts(t.extractfile(m).read().decode("utf-8", "replace"), bool(YAML.search(m.name)))
                if sec:
                    e["sec"] = sec
            fp[m.name] = e
    return fp


def fp_path(name, stamp):
    return os.path.join(DEST, ".fp", name, stamp + ".json.gz")


def load_fp(name, stamp):
    if (name, stamp) in _cache:
        return _cache[(name, stamp)]
    try:
        with gzip.open(fp_path(name, stamp), "rt") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except BROKEN:
        return None                                       # missing or damaged: fingerprinted again from the archive


def save_fp(name, stamp, fp):
    state_dir(name)
    p = fp_path(name, stamp)
    with gzip.open(p + ".part", "wt") as f:
        json.dump(fp, f)
    os.replace(p + ".part", p)


def fp_stamps(name):
    """Every night with a fingerprint (kept 30 days, past the 7-day prune of the archives themselves)."""
    d = os.path.join(DEST, ".fp", name)
    on_disk = {f[:-8] for f in os.listdir(d) if f.endswith(".json.gz")} if os.path.isdir(d) else set()
    return sorted(on_disk | {s for n, s in _cache if n == name})


def norm(member):
    return member[2:] if member.startswith("./") else member


def ts(stamp):
    return time.mktime(time.strptime(stamp, "%Y%m%d-%H%M"))


def measures(e):
    out = {}
    if "lines" in e:
        out["líneas"], out["elementos"] = e["lines"], e["items"]
        out.update(e.get("sec") or {})
    return out


def judge(history, new):
    """history: older fingerprints (oldest first, within the window); new: the newest.
    [(path, metric, top, now)] for shrinks; (path, None, None, None) for a file that is gone."""
    problems = []
    if not history:
        return problems
    for path, e in new.items():
        if "lines" not in e or WATCH_SKIP.search(path):
            continue
        old = [h[path] for h in history if path in h]
        found = []
        for key, now in measures(e).items():
            vals = [v for v in (measures(o).get(key) for o in old) if v is not None]
            if not vals:
                continue
            top = max(vals)
            if top < {"líneas": 30, "elementos": 20}.get(key, 8):   # a section: 8 items (16 title keywords were cut to 4)
                continue
            # a file that halved now and then before (a scratch list) needs a deeper fall. The nights at the end that
            # are already this low are the same drop going on, not a swing (the first dry run reported the 2026-10-28
            # cut on its first night only)
            base = list(vals)
            while base and base[-1] <= top / 2:
                base.pop()
            swung = bool(base) and min(base) <= top / 2
            if now <= top / (4 if swung else 2) and not (swung and now >= min(base)):
                found.append((path, key, top, now))
        precise = [f for f in found if f[1] not in ("líneas", "elementos")]
        problems += (precise or found)[:3]                # the section says where; bare counts when nothing finer moved
    for path in sorted({p for h in history for p in h} - set(new)):
        if WATCH_SKIP.search(path):
            continue
        if sum(1 for h in history if path in h and "lines" in h[path]) >= 5:   # a text file kept 5 nights or more
            problems.append((path, None, None, None))
    return problems


def describe(problems):
    """One line per file: "path: se achicó: section 151 → 11; other 16 → 4" or "path: desapareció"."""
    by = collections.OrderedDict()
    for path, key, top, now in problems:
        by.setdefault(path, []).append(None if key is None else f"{key} {top} → {now}")
    return [f"{path}: desapareció" if None in what else f"{path}: se achicó: " + "; ".join(what) for path, what in by.items()]


def ack_file(name):
    return os.path.join(state_dir(name), "ack.json")


def load_acks(name):
    try:
        d = json.load(open(ack_file(name)))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def silenced(p, acks, now):
    """An ack holds ACK_DAYS while the file is still gone, or while it has not fallen to half of the acked value again."""
    a = acks.get(f"{p[0]}|{p[1]}")
    if not isinstance(a, dict) or now > a.get("until", 0):
        return False
    return p[1] is None or p[3] > a.get("value", 0) / 2


def alert_text(name, stamp, problems):
    lines = [f"Copia nocturna de {name} ({stamp[6:8]}/{stamp[4:6]}): archivos que cambiaron mucho respecto de las últimas semanas."]
    files = describe(problems)
    lines += [f"• {f}" for f in files[:5]]
    if len(files) > 5:
        lines.append(f"• y {len(files) - 5} archivos más")
    lines.append(f"Si no lo pidió la persona, la versión anterior sale con: ops/backup_watch.py restore {name} RUTA. "
                 f"Si lo pidió: ops/backup_watch.py ack {name}")
    return "\n".join(lines)


def window(name, upto, days):
    """Fingerprints of the nights before `upto` within `days`, oldest first."""
    t0 = ts(upto) - days * 86400
    return [fp for fp in (load_fp(name, s) for s in fp_stamps(name) if s < upto and ts(s) >= t0) if fp is not None]


def snapshot(name, stamp, path):
    """The person's small text files from one archive into small/<name>-<stamp>.tar.gz."""
    d = os.path.join(DEST, "small")
    os.makedirs(d, mode=0o700, exist_ok=True)
    out = os.path.join(d, f"{name}-{stamp}.tar.gz")
    if os.path.exists(out):
        return out
    with tarfile.open(path, "r:gz") as t, tarfile.open(out + ".part", "w:gz") as o:
        for m in t:
            if m.isfile() and m.size <= SMALL_MAX and TEXT.search(m.name) and not SECRET.search(m.name) and not NOISE.search(m.name):
                o.addfile(m, t.extractfile(m))
    os.replace(out + ".part", out)
    return out


def prune(now):
    for root, keep in ((os.path.join(DEST, ".fp"), KEEP_FP), (os.path.join(DEST, "small"), KEEP_SMALL)):
        for dirpath, _, files in os.walk(root):
            for f in files:
                p = os.path.join(dirpath, f)
                if f.endswith((".json.gz", ".tar.gz", ".part")) and now - os.path.getmtime(p) > keep * 86400:
                    os.remove(p)


def watch_one(name, items, a, notify, now):
    """Fingerprint, judge, alert and snapshot one person. A damaged archive is an alert, not a crash."""
    bad = []
    for stamp, path in items:
        if load_fp(name, stamp) is None:
            try:
                fp = fingerprint(path)
            except BROKEN as e:
                bad.append(f"{os.path.basename(path)} ({type(e).__name__})")
                continue
            if a.dry_run:
                _cache[(name, stamp)] = fp
            else:
                save_fp(name, stamp, fp)
    if bad:
        notify.alert(f"bw:{name}:unreadable", f"No pude leer {len(bad)} copia(s) de {name}: " + ", ".join(bad[:3]), quiet=20 * 3600)
    newest, path = items[-1]
    age = now - ts(newest)
    if age > STALE_H * 3600:
        notify.alert(f"bw:{name}:stale", f"{name}: no hay copia nocturna nueva hace {int(age / 3600)} h (la última es del "
                                         f"{newest[6:8]}/{newest[4:6]}). ¿Corre backup-stacks.timer? Si la persona ya no está: "
                                         f"ops/backup_watch.py forget {name}", quiet=20 * 3600)
    else:
        notify.resolve(f"bw:{name}:stale", f"{name}: volvió la copia nocturna")
    new = load_fp(name, newest)
    if new is None:
        return                                            # an unreadable newest archive says nothing about the files
    if not bad:
        notify.resolve(f"bw:{name}:unreadable", f"{name}: las copias nocturnas se leen bien otra vez")
    days = OPEN_WINDOW if notify.active(f"bw:{name}:files") else WINDOW
    acks = load_acks(name)
    problems = [p for p in judge(window(name, newest, days), new) if not silenced(p, acks, now)]
    if problems:
        notify.alert(f"bw:{name}:files", alert_text(name, newest, problems), quiet=20 * 3600)
    else:
        notify.resolve(f"bw:{name}:files", f"{name}: los archivos de la copia nocturna volvieron a su tamaño habitual")
    if not a.dry_run:
        snapshot(name, newest, path)


def cmd_run(a, notify):
    now, rc = time.time(), 0
    try:
        for name, items in sorted(archives().items()):
            try:
                watch_one(name, items, a, notify, now)
                notify.resolve(f"bw:{name}:crash")
            except Exception as e:                        # one person's failure must not leave the others unchecked
                rc = 1
                notify.alert(f"bw:{name}:crash", f"backup_watch falló con {name}: {type(e).__name__}", quiet=20 * 3600)
    finally:
        if not a.dry_run:
            prune(now)
    return rc


def cmd_backfill(a):
    for name, items in sorted(archives().items()):
        for stamp, path in items:
            if load_fp(name, stamp) is None:
                try:
                    fp = fingerprint(path)
                except BROKEN as e:
                    print(f"{name} {stamp}: ilegible ({type(e).__name__})")
                    continue
                if a.dry_run:
                    _cache[(name, stamp)] = fp
                else:
                    save_fp(name, stamp, fp)
        for stamp, _ in items:
            fp = load_fp(name, stamp)
            problems = judge(window(name, stamp, WINDOW), fp) if fp else []
            print(f"{name} {stamp}: " + (" | ".join(describe(problems)[:5]) if problems else "sin novedades"))
    return 0


def cmd_ack(a):
    stamps = fp_stamps(a.name)
    if not stamps:
        print(f"No hay huellas de {a.name}.")
        return 1
    now = time.time()
    acks = {k: v for k, v in load_acks(a.name).items() if isinstance(v, dict) and v.get("until", 0) > now}
    probs = judge(window(a.name, stamps[-1], OPEN_WINDOW), load_fp(a.name, stamps[-1]) or {})
    for p in probs:
        acks[f"{p[0]}|{p[1]}"] = {"value": p[3] if p[3] is not None else 0, "until": now + ACK_DAYS * 86400}
    with open(ack_file(a.name), "w") as f:
        json.dump(acks, f)
    print(f"{a.name}: {len(probs)} aviso(s) silenciado(s) por {ACK_DAYS} días (vuelven si el archivo cae a la mitad otra vez).")
    return 0


def cmd_forget(a):
    state_dir()
    with open(os.path.join(DEST, ".fp", "forgotten.json"), "w") as f:
        json.dump(sorted(forgotten() | {a.name}), f)
    print(f"Dejo de vigilar a {a.name}.")
    return 0


def cmd_status(notify):
    now = time.time()
    for name, items in sorted(archives().items()):
        s = items[-1][0]
        print(f"{name}: última copia {s} (hace {int((now - ts(s)) / 3600)} h), {len(items)} copias")
    for k, v in sorted(notify.active("bw:").items()):
        print(f"abierta: {k} desde {time.strftime('%d/%m %H:%M', time.localtime(v.get('since', now)))}")
    return 0


def cmd_restore(a):
    want = norm(a.path)
    if os.path.isabs(want) or ".." in want.split("/"):
        print("La ruta tiene que ser relativa al stack, sin '..' (como la muestra el aviso).")
        return 2
    cands = []                                            # (stamp, archive) of this person, newest first
    for d in (os.path.join(DEST, "small"), DEST):
        for f in sorted(os.listdir(d), reverse=True) if os.path.isdir(d) else []:
            m = ARCHIVE.match(f)
            if m and m["name"] == a.name and (not a.stamp or m["stamp"] == a.stamp):
                cands.append((m["stamp"], os.path.join(d, f)))
    best = None
    for stamp, path in cands:
        try:
            with tarfile.open(path, "r:gz") as t:
                m = next((x for x in t if x.isfile() and norm(x.name) == want), None)
        except BROKEN:
            continue
        if m and (best is None or m.size > best[2]):
            best = (stamp, path, m.size)
        if best and a.stamp:
            break
    if not best:
        print(f"No encontré {a.path} de {a.name} en las copias" + (f" del {a.stamp}" if a.stamp else "") + ".")
        return 1
    stamp, path, size = best
    out = os.path.realpath(os.path.join(RESTORE, a.name, stamp))
    target = os.path.realpath(os.path.join(out, want))
    if not target.startswith(out + os.sep):
        print("Esa ruta saldría de la carpeta de restauración: no la extraigo.")
        return 2
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    with tarfile.open(path, "r:gz") as t:
        m = next(x for x in t if x.isfile() and norm(x.name) == want)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(t.extractfile(m).read())
    print(f"Extraído de la copia del {stamp} ({size} bytes): {target}")
    print("Nada vivo fue tocado. Para ponerlo en su lugar: parar el stack de la persona, copiar el archivo sobre el suyo "
          "(si es de root, con un contenedor: docker run --rm -i -v <dir>:/j busybox:1.37.0 sh -c 'cat > /j/ARCHIVO' < "
          f"{target}) y hacer docker rm del contenedor Hermes antes de arrancarlo (ver RESTORE en ops/backup-stacks.sh).")
    return 0


def main(argv):
    os.umask(0o077)                                       # everything written here holds personal data or its shape
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("run", "backfill"):
        sub.add_parser(c).add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    sub.add_parser("ack").add_argument("name")
    sub.add_parser("forget").add_argument("name")
    r = sub.add_parser("restore")
    r.add_argument("name")
    r.add_argument("path")
    r.add_argument("--stamp")
    a = ap.parse_args(argv)
    if a.cmd in ("backfill", "restore", "ack", "forget"):
        return {"backfill": cmd_backfill, "restore": cmd_restore, "ack": cmd_ack, "forget": cmd_forget}[a.cmd](a)
    import notify
    if a.cmd == "status":
        return cmd_status(notify)
    if a.dry_run:
        class Show:
            def alert(self, k, t, quiet=0):
                print(f"[alerta {k}]\n{t}\n")

            def resolve(self, k, t=None):
                pass

            def active(self, prefix=""):
                return {}
        notify = Show()
    return cmd_run(a, notify)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
