#!/usr/bin/env python3
"""Patch Hermes so freeing memory space is safe: every entry that leaves MEMORY.md / USER.md is kept in an archive file, and
a failed consolidation tells the model how to free space without losing a fact.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: memory_keep_removed.py <path to tools/memory_tool_store.py>

Why: the built-in memory is bounded (memory_char_limit / user_char_limit) and goes into every prompt. When it is full the model
must remove or shorten entries in the same call that adds the new one. Two risks follow:
  * a removed or overwritten entry exists nowhere afterwards (the tool result shows it once, in a session log nobody reads), so
    a useful fact can be lost to make room for a less useful note;
  * the over-budget message only says how many characters to free, not how, so a model can repeat the same failing batch until
    Hermes's per-turn cap on consolidation failures.

What it does (memory_tool_store.py):
  1. `_mutate` (every write path: add, replace, remove, batch, and an approved staged write) compares the entries before and after
     and appends each one that is gone (removed, or overwritten by a replace) to <HERMES_HOME>/memories/archive/MEMORY-removed.md
     or USER-removed.md, under a "## YYYY-MM-DD HH:MM" line. Never read into the prompt. The file is rotated to *.1.md at 64 KB (one
     older generation kept). Best effort: a failure to archive is logged and never blocks the memory write.
  2. The first three over-budget failures of a turn get a sentence appended to their error: merge related entries and
     shorten the longest, one fact and at most about 300 characters per entry, never remove a technical fact or a preference to fit a
     to-do, a progress note or a one-off result (skip that note instead), and removed entries are kept in memories/archive/.
  3. The terminal "failed N times" message also says that when the person asked for the save, they are told in one line that it was
     not saved.
The limits themselves are set in start_hermes.sh (memory.memory_char_limit, memory.user_char_limit), not here.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build
loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: memory_keep_removed"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


HELPER = '''_AIBRIDGE_ARCHIVE_MAX = 64 * 1024  # aibridge-patch: memory_keep_removed
_AIBRIDGE_HINT = (" To make room: MERGE related entries into one shorter entry and shorten the longest ones (one fact per entry, "
                  "at most about 300 chars). Never remove a technical fact or a preference to fit a to-do, a progress note or a "
                  "one-off result: skip that note instead. Removed entries are kept in memories/archive/.")


def _aibridge_archive_removed(path, before, after):
    """Append every entry of *before* that is not in *after* to <memories>/archive/<STEM>-removed.md. Best effort."""
    try:
        gone = [e for e in before if e not in after]
        if not gone:
            return
        folder = path.parent / "archive"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{path.stem}-removed.md"
        if target.exists() and target.stat().st_size > _AIBRIDGE_ARCHIVE_MAX:
            os.replace(target, folder / f"{path.stem}-removed.1.md")
        stamp = time.strftime("%Y-%m-%d %H:%M")
        with open(target, "a", encoding="utf-8") as fh:
            for entry in gone:
                fh.write(f"## {stamp}\\n{entry}\\n\\n")
    except Exception:
        logger.warning("could not archive removed memory entries", exc_info=True)


'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    src = replace_once(src, "class MemoryStore:\n", HELPER + "class MemoryStore:\n", "helper before class MemoryStore")
    src = replace_once(
        src,
        "        if self._consolidation_failures <= self._MAX_CONSOLIDATION_FAILURES_PER_TURN:\n            return response\n",
        "        if self._consolidation_failures <= self._MAX_CONSOLIDATION_FAILURES_PER_TURN:\n"
        f"            if FAILURE_CLASS.get() == \"over_budget\" and isinstance(response.get(\"error\"), str):  {MARK}\n"
        "                response = {**response, \"error\": response[\"error\"] + _AIBRIDGE_HINT}\n"
        "            return response\n",
        "hint on a failed consolidation",
    )
    src = replace_once(
        src,
        '"The fact can be saved in a later turn.")}',
        '"The fact can be saved in a later turn. If the person asked for it, tell them in one line that it was not saved "\n'
        '            "because memory is full.")}',
        "terminal retry-cap message",
    )
    src = replace_once(
        src,
        "            result = mutate(self._entries_for(target), self._char_limit(target))\n",
        f"            before = list(self._entries_for(target))  {MARK}\n"
        "            result = mutate(self._entries_for(target), self._char_limit(target))\n",
        "entries before the mutation",
    )
    src = replace_once(
        src,
        "            self._write_file(path, result[0])\n",
        "            self._write_file(path, result[0])\n"
        f"            _aibridge_archive_removed(path, before, result[0])  {MARK}\n",
        "archive after the write",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
