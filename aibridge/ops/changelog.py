#!/usr/bin/env python3
"""Keep CHANGELOG.md: one entry per deployed build, made from the commits it brought.

  ops/changelog.py add --rev 9142a69 [--prev 39f4ca9] [--image b4dd4f447bbb] [--note "..."] [--date 2026-11-21]
  ops/changelog.py show [N]        the newest N entries (default 1)

Why: a build is a commit, and what changed in it is spread over many commits and merges. `ops/pipeline.sh deploy` calls `add` after a
deploy went through, with the revision it replaced (the DEPLOYED file next to the tars), so the file answers "what did build X bring"
and "which build has this fix" without reading the log. The entry lists commit subjects (no merges, newest first, each with its short
hash) between the previous deployed revision and this one. Only what the public history already says goes in: no host, stack or
person names, no operational events. Per-stack details stay in the private deploy log next to the tars (BUILD_DIR/out/deploys.log).

Without --prev the previous revision is the newest entry already in the file; with neither, the entry holds just this commit.
Running `add` again for a revision that is already there changes nothing. The file is not committed by this script: the deploy
leaves it changed on purpose, commit it with the next change.
"""
import argparse, datetime, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FILE = os.path.join(HERE, "..", "CHANGELOG.md")
HEADER = """# Changelog

One entry per deployed build, newest first, written by `ops/pipeline.sh deploy` (`ops/changelog.py`). An entry lists the commits the
build brought since the previous deployed one. A build is named by its commit; `git show <hash>` has the detail.

"""
MAX_COMMITS = 80
ENTRY = re.compile(r"^## ([0-9a-f]{7,40}) ", re.M)


def commits(repo, prev, rev):
    """[(short hash, subject)], newest first, no merges, for the commits in rev that prev does not have."""
    span = f"{prev}..{rev}" if prev else f"{rev}^!"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    p = subprocess.run(["git", "-C", repo, "log", "--no-merges", "--pretty=%h%x09%s", span], capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise SystemExit(f"changelog: git could not list {span}: {p.stderr.strip()[:200]}")
    return [tuple(l.split("\t", 1)) for l in p.stdout.splitlines() if "\t" in l]


def render(rev, prev, date, image, note, items):
    lines = [f"## {rev} — {date}", ""]
    meta = []
    if image:
        meta.append(f"Image {image}.")
    if prev:
        meta.append(f"Replaces {prev}.")
    if note:
        meta.append(note.rstrip(".") + ".")
    if meta:
        lines += [" ".join(meta), ""]
    shown = items[:MAX_COMMITS]
    lines += [f"- {subject} (`{h}`)" for h, subject in shown] or ["- No commits of its own (a rebuild of the same code)."]
    if len(items) > len(shown):
        lines.append(f"- … and {len(items) - len(shown)} more: `git log --no-merges {prev}..{rev}`")
    return "\n".join(lines) + "\n\n"


def insert(text, entry, rev):
    """text with entry after the header; unchanged when the revision already has an entry."""
    if re.search(rf"^## {re.escape(rev)} ", text, re.M):
        return text
    if not text.startswith("# Changelog"):
        text = HEADER + text
    m = ENTRY.search(text)
    at = m.start() if m else len(text)
    return text[:at] + entry + text[at:]


def newest_rev(text):
    m = ENTRY.search(text)
    return m.group(1) if m else None


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("add")
    a_.add_argument("--rev", required=True); a_.add_argument("--prev"); a_.add_argument("--image"); a_.add_argument("--note")
    a_.add_argument("--date", default=datetime.date.today().isoformat()); a_.add_argument("--file", default=DEFAULT_FILE)
    a_.add_argument("--repo", default=os.path.join(HERE, ".."))
    s_ = sub.add_parser("show"); s_.add_argument("n", nargs="?", type=int, default=1); s_.add_argument("--file", default=DEFAULT_FILE)
    a = ap.parse_args(argv)
    try:
        text = open(a.file, encoding="utf-8").read()
    except OSError:
        text = ""
    if a.cmd == "show":
        parts = ENTRY.split(text)   # [header, rev, body, rev, body, ...]
        for i in range(1, min(len(parts), 1 + 2 * a.n), 2):
            print(f"## {parts[i]} {parts[i + 1].rstrip()}\n")
        return 0
    prev = a.prev or newest_rev(text)
    if prev and prev == a.rev:
        prev = None
    new = insert(text, render(a.rev, prev, a.date, a.image, a.note, commits(a.repo, prev, a.rev)), a.rev)
    if new == text:
        print(f"changelog: {a.rev} is already in {os.path.basename(a.file)}")
        return 0
    with open(a.file, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"changelog: added {a.rev} to {os.path.basename(a.file)}; commit it with the next change")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
