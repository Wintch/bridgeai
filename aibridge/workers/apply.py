#!/usr/bin/env python3
"""Host side of a worker push: put what an always-on worker produced into a person's workdir on the Docker host, by the ownership
rules of WORKERS.md, and nothing else.

The worker (worker.py) never writes into a stack's workdir directly. It copies its outputs with rsync into an inbox it owns on the
Docker host (aibridge/worker-inbox/<stack>/<type>/, the aibridge user's), then runs THIS file there, fed on stdin to `python3 -`:
by default inside a one-shot container of the stack's own image as root (the workdir's files belong to the stack's root, the way
ops/project_sync.py installs node_modules), or with the host's python3 as the aibridge user ("apply": "direct" in workers.json).

  python3 - --type subs     --inbox DIR --workdir DIR [--subs-dir descargas]
  python3 - --type jobnight --inbox DIR --workdir DIR [--jobfinder-dir jobfinder]

What it does with the inbox (an applied file leaves the inbox; one that failed stays and is tried again by the next push):
  subs     srt/<channel>/<file>.srt  -> <workdir>/<subs-dir>/<channel>/   only when that name does NOT exist there (never replaced)
           state/<path>              -> <workdir>/<subs-dir>/<path>       the scan state (.nocaps.tsv, .ids.cache, ...): replaced only
                                                                          when the host's copy is not newer than the worker's
           notices/<name>.txt        -> <workdir>/.worker-notices/        what the cron used to send to Telegram; never replaced
  jobnight pending-<ts>.json         -> merged into <workdir>/<jobfinder-dir>/data/.jobpush-pending.json under the same lock
                                        jobpush.py takes (data/.jobpush-pending.lock), with jobpush.py's own merge rules (merge_pending)
           signals-<ts>.jsonl        -> appended to <workdir>/.early-signals.jsonl (known keys only, O_APPEND)
Nothing is ever deleted in the workdir, and nothing is written through a symlink or outside the workdir.
It prints one JSON line of counts: {"applied", "kept_host", "merged", "appended", "errors"}. Exit 0, or 1 when something failed.
Standard library only (the host's python3 and the image's).
"""
import argparse
import fcntl
import json
import os
import re
import shutil
import sys

PENDING_ROWS_MAX = 200   # as jobpush.py
SIGNAL_KEYS = {"ts", "cat", "n", "k", "v", "src"}


def merge_pending(old, new):
    """Two night summaries into one, the way jobpush.pending_add() merges one run into the file: counters add up, an offer seen again
    keeps its latest verdict and goes last, the latest closing-soon list wins, expired items are added once. old = what waits on the
    host (not delivered yet), new = what the worker found since its last push."""
    if not isinstance(old, dict) or not old:
        return dict(new)
    if not isinstance(new, dict) or not new:
        return dict(old)
    p = dict(old)
    sinces = [x for x in (old.get("since"), new.get("since")) if isinstance(x, (int, float))]
    if sinces:
        p["since"] = min(sinces)
    p["last"] = max(old.get("last") or 0, new.get("last") or 0)
    for k in ("runs", "failed", "checked", "new"):
        p[k] = int(old.get(k) or 0) + int(new.get(k) or 0)
    merged = {}
    for r in list(old.get("rows") or []) + list(new.get("rows") or []):
        if isinstance(r, list) and len(r) == 3 and isinstance(r[0], dict) and r[0].get("url"):
            merged.pop(r[0]["url"], None)
            merged[r[0]["url"]] = r
    p["rows"] = list(merged.values())[-PENDING_ROWS_MAX:]
    if "closing" in new:
        p["closing"] = new["closing"]
    keys = {e.get("key") for e in old.get("expired") or [] if isinstance(e, dict)}
    p["expired"] = list(old.get("expired") or []) + [e for e in new.get("expired") or [] if isinstance(e, dict) and e.get("key") not in keys]
    return p


class Applier:
    def __init__(self, workdir):
        self.wd = os.path.realpath(workdir)
        self.counts = {"applied": 0, "kept_host": 0, "merged": 0, "appended": 0, "errors": 0}

    def inside(self, path):
        """The real parent of path is the workdir or under it, and path itself is not a symlink."""
        parent = os.path.realpath(os.path.dirname(path))
        if parent != self.wd and not parent.startswith(self.wd + os.sep):
            return False
        return not os.path.islink(path)

    def makedirs(self, d):
        """Create d below the workdir, one component at a time, refusing any symlink on the way."""
        rel = os.path.relpath(d, self.wd)
        if rel.startswith(".."):
            raise OSError("outside the workdir")
        cur = self.wd
        for part in [] if rel == "." else rel.split(os.sep):
            cur = os.path.join(cur, part)
            if os.path.islink(cur):
                raise OSError("symlink on the way")
            if not os.path.isdir(cur):
                os.mkdir(cur, 0o755)

    def _write_tmp(self, src, dest):
        tmp = os.path.join(os.path.dirname(dest), "." + os.path.basename(dest)[:180] + ".worker-tmp")
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        os.chmod(tmp, 0o644)
        st = os.stat(src)
        os.utime(tmp, (st.st_atime, st.st_mtime))
        return tmp

    def copy_new(self, src, dest):
        """Only when nothing has that name yet: a file the person or their bot made is never replaced. True = done with src."""
        self.makedirs(os.path.dirname(dest))
        if not self.inside(dest):
            raise OSError("unsafe destination")
        if os.path.lexists(dest):
            self.counts["kept_host"] += 1
            return True
        tmp = self._write_tmp(src, dest)
        try:
            os.link(tmp, dest)             # fails if the name appeared meanwhile: the host's file wins
            self.counts["applied"] += 1
        except FileExistsError:
            self.counts["kept_host"] += 1
        finally:
            os.unlink(tmp)
        return True

    def copy_if_newer(self, src, dest):
        """Shared scan state: replaced only when the host's copy is not newer than the worker's (rsync --update's rule)."""
        self.makedirs(os.path.dirname(dest))
        if not self.inside(dest):
            raise OSError("unsafe destination")
        if os.path.lexists(dest) and os.lstat(dest).st_mtime > os.stat(src).st_mtime:
            self.counts["kept_host"] += 1
            return True
        tmp = self._write_tmp(src, dest)
        if os.path.lexists(dest) and os.lstat(dest).st_mtime > os.stat(src).st_mtime:   # changed while we copied
            os.unlink(tmp)
            self.counts["kept_host"] += 1
            return True
        os.replace(tmp, dest)
        self.counts["applied"] += 1
        return True

    def merge_pending_file(self, src, data_dir):
        path, lock = os.path.join(data_dir, ".jobpush-pending.json"), os.path.join(data_dir, ".jobpush-pending.lock")
        if not (self.inside(path) and self.inside(lock)):
            raise OSError("unsafe destination")
        new = json.load(open(src, encoding="utf-8"))
        with open(lock, "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                old = json.load(open(path, encoding="utf-8"))
            except (OSError, ValueError):
                old = {}
            tmp = path + ".part"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(merge_pending(old, new), ensure_ascii=False))
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        self.counts["merged"] += 1
        return True

    def append_signals(self, src, path):
        if not self.inside(path):
            raise OSError("unsafe destination")
        out = []
        for line in open(src, encoding="utf-8", errors="replace"):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and set(rec) <= SIGNAL_KEYS and isinstance(rec.get("cat"), str) and re.match(r"^[a-z0-9_]{1,32}$", rec["cat"]):
                out.append(json.dumps(rec, separators=(",", ":")) + "\n")
        if out:
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, "a") as f:
                f.write("".join(out))
            self.counts["appended"] += len(out)
        return True

    def take(self, fn, src, *a):
        """Run one step; the inbox file goes once it is done with, and stays for the next push when the step failed."""
        try:
            if fn(src, *a):
                os.unlink(src)
        except (OSError, ValueError) as e:
            self.counts["errors"] += 1
            print(f"apply: {os.path.basename(src)}: {type(e).__name__}", file=sys.stderr)


def files_under(root):
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if not os.path.islink(os.path.join(d, x)))
        out += [os.path.relpath(os.path.join(d, f), root) for f in sorted(files) if not os.path.islink(os.path.join(d, f))]
    return out


def prune_empty(root):
    for d, dirs, files in os.walk(root, topdown=False):
        if d != root and not os.listdir(d):
            try:
                os.rmdir(d)
            except OSError:
                pass


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True, choices=("subs", "jobnight"))
    ap.add_argument("--inbox", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--subs-dir", default="descargas")
    ap.add_argument("--jobfinder-dir", default="jobfinder")
    a = ap.parse_args(argv)
    ap_ = Applier(a.workdir)
    if not os.path.isdir(a.inbox):
        print(json.dumps(ap_.counts))
        return 0
    if not os.path.isdir(ap_.wd):
        print(json.dumps(dict(ap_.counts, errors=1)))
        return 1
    if a.type == "subs":
        base = os.path.join(ap_.wd, a.subs_dir)
        for rel in files_under(os.path.join(a.inbox, "srt")):
            if rel.endswith(".srt"):
                ap_.take(ap_.copy_new, os.path.join(a.inbox, "srt", rel), os.path.join(base, rel))
        for rel in files_under(os.path.join(a.inbox, "state")):
            ap_.take(ap_.copy_if_newer, os.path.join(a.inbox, "state", rel), os.path.join(base, rel))
        for rel in files_under(os.path.join(a.inbox, "notices")):
            ap_.take(ap_.copy_new, os.path.join(a.inbox, "notices", rel), os.path.join(ap_.wd, ".worker-notices", os.path.basename(rel)))
    else:
        data = os.path.join(ap_.wd, a.jobfinder_dir, "data")
        names = sorted(os.listdir(a.inbox))
        if any(n.startswith("pending-") for n in names) and not os.path.isdir(data):
            ap_.counts["errors"] += 1
            print("apply: the jobfinder has no data folder on this host", file=sys.stderr)
        else:
            for n in names:
                if re.match(r"^pending-[0-9T:.Z-]+\.json$", n):
                    ap_.take(ap_.merge_pending_file, os.path.join(a.inbox, n), data)
        for n in names:
            if re.match(r"^signals-[0-9T:.Z-]+\.jsonl$", n):
                ap_.take(ap_.append_signals, os.path.join(a.inbox, n), os.path.join(ap_.wd, ".early-signals.jsonl"))
    prune_empty(a.inbox)
    print(json.dumps(ap_.counts))
    return 1 if ap_.counts["errors"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
