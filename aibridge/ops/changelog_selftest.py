#!/usr/bin/env python3
"""Offline checks for ops/changelog.py: entry text, insertion order, idempotence, commit ranges on a throwaway repo.
Run: python3 -I ops/changelog_selftest.py"""
import importlib.util, os, subprocess, sys, tempfile
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("cl", os.path.join(HERE, "changelog.py"))
cl = importlib.util.module_from_spec(spec); spec.loader.exec_module(cl)
fails = []


def check(name, got, want=True):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"   got {got!r}, want {want!r}"))
    if not ok: fails.append(name)


e = cl.render("bbbbbbb", "aaaaaaa", "2026-01-02", "0123456789ab", "Some stacks were awake and update when idle.", [("c3", "Third"), ("c2", "Second")])
check("entry: heading, image, replaced build, note (one full stop), commits with hashes",
      e, "## bbbbbbb — 2026-01-02\n\nImage 0123456789ab. Replaces aaaaaaa. Some stacks were awake and update when idle.\n\n- Third (`c3`)\n- Second (`c2`)\n\n")
check("entry: a rebuild of the same code says so", "No commits of its own" in cl.render("bbbbbbb", None, "2026-01-02", None, None, []), True)
big = cl.render("bbbbbbb", "aaaaaaa", "2026-01-02", None, None, [(f"h{i}", f"s{i}") for i in range(cl.MAX_COMMITS + 5)])
check("entry: a long range is cut and says how many more", ("… and 5 more" in big, big.count("\n- ") == cl.MAX_COMMITS + 1), (True, True))

g = cl.render("bbbbbbb", "aaaaaaa", "2026-01-02", None, None, [("c3", "Waker fix"), ("c2", "Gateway feature"), ("c1", "Docs")],
              {"c3": "hosts", "c2": "bots", "c1": "docs"})
check("grouped: the bots part first, then hosts, then docs and tests, each commit once",
      (g.index("For the bots") < g.index("Gateway feature") < g.index("Hosts") < g.index("Waker fix") < g.index("Docs and tests") < g.index("- Docs"),
       g.count("(`c"), "Nothing in this deploy reaches the bots" in g), (True, 3, False))
h = cl.render("bbbbbbb", "aaaaaaa", "2026-01-02", None, None, [("c3", "Waker fix")], {"c3": "hosts"})
check("grouped: a deploy without bot changes says so", ("Nothing in this deploy reaches the bots" in h, "For the bots" in h), (True, False))
t = cl.insert("", e, "bbbbbbb")
check("insert: an empty file gets the header", t.startswith("# Changelog") and "## bbbbbbb" in t, True)
t2 = cl.insert(t, cl.render("ccccccc", "bbbbbbb", "2026-01-03", None, None, [("c4", "Fourth")]), "ccccccc")
check("insert: the newest entry goes first", t2.index("## ccccccc") < t2.index("## bbbbbbb"), True)
check("insert: the same revision again changes nothing", cl.insert(t2, "## ccccccc — x\n", "ccccccc"), t2)
check("newest_rev reads the first entry", cl.newest_rev(t2), "ccccccc")
check("newest_rev of a file without entries", cl.newest_rev("# Changelog\n"), None)

# a throwaway repo: A <- B <- merge(M) <- C ; the merge commit is not listed, the range excludes A
with tempfile.TemporaryDirectory() as d:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    def git(*a): return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True, env=env).stdout.strip()
    git("init", "-q", "-b", "main")
    def commit(msg):
        name = msg.replace(" ", "_")   # one file per commit: the merge has nothing to conflict on
        open(os.path.join(d, name), "w").write(msg + "\n"); git("add", name); git("commit", "-q", "-m", msg); return git("rev-parse", "--short", "HEAD")
    a = commit("A first"); git("checkout", "-q", "-b", "side"); b = commit("B on the side"); git("checkout", "-q", "main")
    m = commit("M on main"); git("merge", "-q", "--no-ff", "-m", "Merge side", "side"); c = commit("C after the merge")
    got = cl.commits(d, a, c)
    check("commits: no merges, newest first, the previous build excluded", [s for _, s in got], ["C after the merge", "M on main", "B on the side"])
    check("commits: no previous build lists only that commit", [s for _, s in cl.commits(d, None, c)], ["C after the merge"])
    f = os.path.join(d, "CHANGELOG.md")
    rc = cl.main(["add", "--rev", c, "--prev", a, "--date", "2026-01-04", "--repo", d, "--file", f])
    first = open(f).read()
    check("add: writes the entry", (rc, f"## {c} — 2026-01-04" in first, "C after the merge" in first), (0, True, True))
    cl.main(["add", "--rev", c, "--prev", a, "--repo", d, "--file", f])
    check("add: a second run for the same build changes nothing", open(f).read(), first)
    d2 = commit("D later")
    cl.main(["add", "--rev", d2, "--date", "2026-01-05", "--repo", d, "--file", f])
    txt = open(f).read()
    check("add: without --prev the newest entry is the previous build, so only D is listed",
          (txt.index(f"## {d2}") < txt.index(f"## {c}"), txt.split(f"## {d2}")[1].split("## ")[0].count("\n- ")), (True, 1))

print("\n".join(fails) or "changelog_selftest: all ok")
sys.exit(1 if fails else 0)
