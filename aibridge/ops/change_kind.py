#!/usr/bin/env python3
"""Which changes reach the bots, read from the files a commit touched (run from aibridge/).

A file "reaches the bots" when the agent image is built from it: a source of a COPY/ADD in Dockerfile.hermes-agent, or one of the two
Dockerfiles themselves (the build context is aibridge/). Everything else is the hosts' (the waker, the deploy, timers, the GPU host), the
docs, or the tests. The changelog groups a deploy's commits that way, and the pipeline skips the image (no build, no smoke, no stack
recreated) when nothing that reaches the bots changed since the last deploy.

  change_kind.py image-changed PREV REV   exit 0 and the image files that changed when one did; exit 1 when none did; exit 2 on a git error
  change_kind.py commit REV               the kind of one commit (bots | hosts | tests | docs)

kind_of_file / kind_of_commit are pure (tested offline).
"""
import fnmatch, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AIB = os.path.dirname(HERE)                                   # aibridge/
DOCKERFILES = ("Dockerfile.hermes-agent", "Dockerfile.hermes-agent-base", ".dockerignore")
KINDS = ("bots", "hosts", "tests", "docs")                     # a commit is the first kind any of its files has


def image_sources(dockerfiles=None):
    """The COPY/ADD sources of the agent image, relative to aibridge/ (files, folders, globs)."""
    out = set()
    for name in dockerfiles or DOCKERFILES[:2]:
        try:
            text = open(os.path.join(AIB, name), encoding="utf-8").read()
        except OSError:
            continue
        text = re.sub(r"\\\n", " ", text)
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) < 3 or parts[0].upper() not in ("COPY", "ADD"):
                continue
            args = [p for p in parts[1:] if not p.startswith("--")]
            if any(p.startswith("--from") for p in parts[1:]) or len(args) < 2:
                continue                                           # a copy between build stages carries no file of ours
            out.update(a.rstrip("/") for a in args[:-1])
    return sorted(out)


def is_test(path):
    b = os.path.basename(path)
    return b.endswith("_selftest.py") or b == "selftest.py" or "/selftest_data/" in path


def kind_of_file(path, sources):
    """path relative to the repo root (aibridge/gateway.py) -> bots | hosts | tests | docs. Pure."""
    if is_test(path):
        return "tests"
    if path.startswith("aibridge/"):
        rel = path[len("aibridge/"):]
        if rel in DOCKERFILES:
            return "bots"
        for s in sources:
            if rel == s or rel.startswith(s + "/") or (any(c in s for c in "*?[") and fnmatch.fnmatch(rel, s)):
                return "docs" if rel == "CHANGELOG.md" else "bots"
    if path.endswith(".md"):
        return "docs"
    return "hosts"


def kind_of_commit(files, sources):
    kinds = {kind_of_file(f, sources) for f in files}
    return next((k for k in KINDS if k in kinds), "docs")


def git(*args):
    """git in this repo (paths in its answers are relative to the repo root); hook variables dropped, as in the selftests."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    p = subprocess.run(["git", "-C", AIB, *args], capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:200])
    return [l for l in p.stdout.splitlines() if l]


def main(argv):
    try:
        if len(argv) == 3 and argv[0] == "image-changed":
            hit = [f for f in git("diff", "--name-only", f"{argv[1]}..{argv[2]}") if kind_of_file(f, image_sources()) == "bots"]
            for f in hit:
                print(f)
            return 0 if hit else 1
        if len(argv) == 2 and argv[0] == "commit":
            print(kind_of_commit(git("show", "--name-only", "--format=", argv[1]), image_sources()))
            return 0
    except RuntimeError as e:
        print(f"change_kind: git: {e}", file=sys.stderr)
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
