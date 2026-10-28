#!/usr/bin/env python3
"""Patch Hermes so a memory batch whose operations are not objects is refused with a clear error, instead of
crashing the background-review delete gate.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: memory_batch_ops_shape.py <path to tools/memory_tool.py>

Why (2026-10-28, hereug, cloud model, background memory review): the model called `memory` with `operations` as a
list of strings instead of {action, content?, old_text?} objects. `_memory_tool` only checks that `operations` is a
list, so the strings reached `_background_delete_gate` -> `destructive_ops`, which does `(op or {}).get("action")`
and raised `AttributeError: 'str' object has no attribute 'get'`. Nothing was written (the exception aborted the
call), but the fail-closed gate for unattended deletes crashed instead of answering, and the model got a traceback
instead of a message it can act on. The same list would also have reached `store.apply_batch` on the attended path.
Still present upstream in v0.22.5 and on main (2026-10-28).

Fix: the existing shape check also requires every element to be a dict, so the model gets the usual
"operations must be a list of {action, content?, old_text?} objects." and can retry.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code
fails the build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: memory_batch_ops_shape"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    src = replace_once(
        src,
        "        if not isinstance(operations, list):\n",
        f"        if not isinstance(operations, list) or not all(isinstance(op, dict) for op in operations):  {MARK}\n",
        "operations shape check",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
