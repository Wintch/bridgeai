#!/usr/bin/env python3
"""Self-test for patches/memory_keep_removed.py.

Runs the patch on a stand-in of Hermes's tools/memory_tool_store.py (the five anchors verbatim, around a small working store),
checks apply / idempotence / abort, then uses the patched module: an entry that leaves the store (remove, replace, merge batch)
is archived, an add changes nothing, a failed over-budget consolidation carries the hint, the archive is rotated, and a broken
archive folder never blocks the write. Set MEMORY_STORE_REAL=<path to a copy of the real tools/memory_tool_store.py> to also apply
the patch to the real source and run the same behaviour checks on it (its imports are stubbed), e.g. a copy read out of the image
with `docker run --rm --network none --entrypoint sh IMAGE -c "cat /root/.hermes/hermes-agent/tools/memory_tool_store.py"`.
Run: python3 -I memory_keep_removed_selftest.py
"""
import importlib.util
import logging
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.path.join(HERE, "patches", "memory_keep_removed.py")
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


STANDIN = '''import logging
import os
import time
from contextvars import ContextVar
from pathlib import Path

logger = logging.getLogger("tools.memory_tool")
ENTRY_DELIMITER = "\\n§\\n"
FAILURE_CLASS: ContextVar[str] = ContextVar("memory_failure_class", default="other")


def _error(message, failure_class, **extra):
    FAILURE_CLASS.set(failure_class)
    return {"success": False, "error": message, **extra}


class MemoryStore:
    _MAX_CONSOLIDATION_FAILURES_PER_TURN = 3

    def __init__(self, directory, limit=100):
        self.dir, self.limit, self.entries, self._consolidation_failures = Path(directory), limit, [], 0

    def _consolidation_failure(self, response):
        self._consolidation_failures += 1
        if self._consolidation_failures <= self._MAX_CONSOLIDATION_FAILURES_PER_TURN:
            return response
        FAILURE_CLASS.set("retry_cap")
        return {"success": False, "done": True, "error": (
            f"Memory consolidation failed {self._consolidation_failures} times this turn. Stop retrying "
            "memory calls — leave memory unchanged for now and continue with your reply to the user. "
            "The fact can be saved in a later turn.")}

    def _path_for(self, target):
        return self.dir / ("USER.md" if target == "user" else "MEMORY.md")

    def _write_file(self, path, entries):
        path.write_text(ENTRY_DELIMITER.join(entries), encoding="utf-8")

    def _mutate(self, target, mutate):
        path = self._path_for(target)
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        self.entries = [e for e in raw.split(ENTRY_DELIMITER) if e]
        if True:
            result = mutate(self.entries, self.limit)
            if isinstance(result, dict):
                return result
            self.entries = result[0]
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_file(path, result[0])
            return {"success": True, "message": result[1]}

    def add(self, target, content):
        def _add(entries, limit):
            if len(ENTRY_DELIMITER.join(entries + [content])) > limit:
                return self._consolidation_failure(_error("over", "over_budget"))
            return entries + [content], "added"
        return self._mutate(target, _add)

    def batch(self, target, ops):
        def _apply(entries, limit):
            working = list(entries)
            for act, text in ops:
                if act == "add":
                    working.append(text)
                elif act == "remove":
                    working = [e for e in working if text not in e]
                elif act == "replace":
                    old, new = text
                    working = [new if old in e else e for e in working]
            if len(ENTRY_DELIMITER.join(working)) > limit:
                return self._consolidation_failure(_error("over batch", "over_budget"))
            return working, "batch"
        return self._mutate(target, _apply)

    def no_match(self):
        return self._consolidation_failure(_error("no entry matches", "no_match"))
'''
# the stand-in uses the real names for the five anchors; only the two accessors below are added to it
STANDIN = STANDIN.replace("result = mutate(self.entries, self.limit)", "result = mutate(self._entries_for(target), self._char_limit(target))")
STANDIN = STANDIN.replace("    def _path_for(self, target):",
                          "    def _entries_for(self, target):\n        return self.entries\n\n    def _char_limit(self, target):\n        return self.limit\n\n    def _path_for(self, target):")
for anchor in ("class MemoryStore:\n",
               "        if self._consolidation_failures <= self._MAX_CONSOLIDATION_FAILURES_PER_TURN:\n            return response\n",
               '"The fact can be saved in a later turn.")}',
               "            result = mutate(self._entries_for(target), self._char_limit(target))\n",
               "            self._write_file(path, result[0])\n"):
    assert STANDIN.count(anchor) == 1, anchor


def run_patch(path):
    return subprocess.run([sys.executable, "-I", PATCH, path], capture_output=True, text=True)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def stub_real_imports(memdir):
    """The real store imports Hermes modules; give it the few names it reads."""
    utils = types.ModuleType("utils")
    utils.atomic_write_text = lambda p, t, *a, **k: Path(p).write_text(t, encoding="utf-8")
    threat = types.ModuleType("tools.threat_patterns")
    threat.first_threat_message = lambda text, scope=None: None
    tools = types.ModuleType("tools")
    mt = types.ModuleType("tools.memory_tool")
    mt.get_memory_dir = lambda: Path(memdir)
    mt.fcntl = None
    mt.msvcrt = None
    hc = types.ModuleType("hermes_constants")
    hc.mkdir_under_hermes_home = lambda p: Path(p).mkdir(parents=True, exist_ok=True)
    tools.memory_tool, tools.threat_patterns = mt, threat
    sys.modules.update({"utils": utils, "tools": tools, "tools.threat_patterns": threat, "tools.memory_tool": mt,
                        "hermes_constants": hc})


def archive_text(memdir, name="MEMORY-removed.md"):
    p = Path(memdir) / "archive" / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def behaviour(mod, memdir, make, add, replace_batch, remove_batch, label):
    """make() -> store; add(store, text) -> result; replace_batch / remove_batch(store, old, new_or_None) -> result."""
    s = make()
    add(s, "alpha fact one")
    add(s, "bravo fact two")
    check(f"{label}: adds archive nothing", archive_text(memdir) == "")
    remove_batch(s, "alpha", None)
    a = archive_text(memdir)
    check(f"{label}: a removed entry is archived whole", "alpha fact one" in a and "bravo fact two" not in a, a)
    check(f"{label}: the archive line has a timestamp heading", a.startswith("## 20") or "\n## 20" in a, a)
    replace_batch(s, "bravo", "bravo shorter")
    a = archive_text(memdir)
    check(f"{label}: an overwritten entry keeps its old text", "bravo fact two" in a, a)
    check(f"{label}: the new text is not archived", "bravo shorter" not in a, a)
    before = archive_text(memdir)
    add(s, "charlie new")
    check(f"{label}: a later add leaves the archive as it was", archive_text(memdir) == before)
    check(f"{label}: the archive sits in memories/archive, away from MEMORY.md",
          (Path(memdir) / "archive" / "MEMORY-removed.md").is_file() and "alpha" not in (Path(memdir) / "MEMORY.md").read_text())


with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "memory_tool_store.py")
    open(path, "w", encoding="utf-8").write(STANDIN)
    r = run_patch(path)
    check("patch applies to the stand-in", r.returncode == 0 and "patched:" in r.stdout, r.stderr + r.stdout)
    first = open(path, encoding="utf-8").read()
    r = run_patch(path)
    check("second run is a no-op", r.returncode == 0 and "already patched" in r.stdout and open(path).read() == first, r.stderr)
    compile(first, path, "exec")
    check("patched source compiles", True)

    mod = load(path, "standin_patched")
    memdir = os.path.join(tmp, "m1")
    behaviour(mod, memdir, lambda: mod.MemoryStore(memdir, 100),
              lambda s, t: s.add("memory", t),
              lambda s, old, new: s.batch("memory", [("replace", (old, new))]),
              lambda s, old, new: s.batch("memory", [("remove", old)]), "stand-in")

    # a merge batch: two entries out, one shorter in -> both originals archived
    memdir2 = os.path.join(tmp, "m2")
    s = mod.MemoryStore(memdir2, 100)
    s.add("memory", "one long entry about X")
    s.add("memory", "another long entry about X")
    s.batch("memory", [("remove", "one long"), ("remove", "another long"), ("add", "X: merged")])
    a = archive_text(memdir2)
    check("stand-in: a merge archives both originals", "one long entry about X" in a and "another long entry about X" in a, a)

    # the hint on a failed consolidation, only on over-budget, only under the cap; the terminal message
    memdir3 = os.path.join(tmp, "m3")
    s = mod.MemoryStore(memdir3, 20)
    res = s.add("memory", "x" * 50)
    check("failure: over-budget carries the merge hint", "MERGE related entries" in res["error"] and "skip that note" in res["error"], res)
    check("failure: the hint says removed entries are kept", "memories/archive/" in res["error"])
    res = s.no_match()
    check("failure: a zero-match failure gets no make-room hint", "MERGE" not in res["error"], res)
    s2 = mod.MemoryStore(memdir3, 20)
    for _ in range(3):
        s2.add("memory", "y" * 50)
    res = s2.add("memory", "y" * 50)
    check("failure: past the cap the message is terminal and tells the person it was not saved",
          res.get("done") is True and "tell them in one line that it was not saved" in res["error"], res)

    # rotation at 64 KB and a broken archive folder never blocks the write
    memdir4 = os.path.join(tmp, "m4")
    s = mod.MemoryStore(memdir4, 10 ** 6)
    s.add("memory", "seed")
    folder = Path(memdir4) / "archive"
    folder.mkdir()
    (folder / "MEMORY-removed.md").write_text("z" * (64 * 1024 + 10))
    s.batch("memory", [("remove", "seed"), ("add", "next")])
    check("rotation: the big archive moves to *.1.md", (folder / "MEMORY-removed.1.md").is_file()
          and (folder / "MEMORY-removed.1.md").stat().st_size > 64 * 1024)
    check("rotation: a fresh archive starts with the new entry", "seed" in archive_text(memdir4) and "zzzz" not in archive_text(memdir4))
    logging.disable(logging.CRITICAL)  # the next case logs the expected archive warning
    memdir5 = os.path.join(tmp, "m5")
    os.makedirs(memdir5)
    Path(memdir5, "archive").write_text("a file where the folder should be")
    s = mod.MemoryStore(memdir5, 100)
    s.add("memory", "keepme")
    res = s.batch("memory", [("remove", "keepme"), ("add", "fresh")])
    check("a failing archive does not block the memory write", res.get("success") is True and "fresh" in Path(memdir5, "MEMORY.md").read_text(), res)

    logging.disable(logging.NOTSET)
    # an anchor that does not match aborts the build
    broken = os.path.join(tmp, "broken.py")
    open(broken, "w").write(STANDIN.replace("self._write_file(path, result[0])", "self._write_file(path, result[0] )"))
    r = run_patch(broken)
    check("an anchor that moved aborts the patch", r.returncode != 0 and "patch failed" in (r.stderr + r.stdout))

real = os.environ.get("MEMORY_STORE_REAL")
if real:
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "memory_tool_store.py")
        open(copy, "w", encoding="utf-8").write(open(real, encoding="utf-8").read())
        r = run_patch(copy)
        check("patch applies to the real source", r.returncode == 0, r.stderr + r.stdout)
        memdir = os.path.join(tmp, "mem")
        stub_real_imports(memdir)
        mod = load(copy, "tools.memory_tool_store")
        make = lambda: mod.MemoryStore(1000, 500)
        batch = lambda s, ops: s.apply_batch("memory", ops)
        behaviour(mod, memdir, make, lambda s, t: s.add("memory", t),
                  lambda s, old, new: batch(s, [{"action": "replace", "old_text": old, "content": new}]),
                  lambda s, old, new: batch(s, [{"action": "remove", "old_text": old}]), "real")
        s = mod.MemoryStore(200, 500)
        s.add("memory", "q" * 100)
        res = s.add("memory", "w" * 100)
        check("real: over-budget add carries the hint and the live entries", "MERGE related entries" in res["error"] and res.get("current_entries"), res)
        res = batch(s, [{"action": "add", "content": "e" * 100}])
        check("real: over-budget batch carries the hint", "MERGE related entries" in res["error"], res)
        s.reset_consolidation_failures()
        res = s.remove("memory", "q" * 20)
        check("real: single remove archives too", "q" * 100 in archive_text(memdir), res)
else:
    print("skip real source (set MEMORY_STORE_REAL to check it)")

print("\n".join(fails) or "memory_keep_removed_selftest: all ok")
sys.exit(1 if fails else 0)
