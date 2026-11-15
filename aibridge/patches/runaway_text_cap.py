#!/usr/bin/env python3
"""Patch Hermes so one streamed reply cannot grow without limit: the visible text of a single model call is cut at
AIBRIDGE_TEXT_MAX_CHARS (default 40000) and the turn ends, exactly as Hermes already does for a verbatim repetition loop.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: runaway_text_cap.py <agent/repetition_guard.py> <agent/chat_completion_helpers.py>

Why (on Telegram, stepfun-ai/step-5-preview): asked for a comparison of the spoken voices, the model never
called a tool. It wrote its deliberation as the reply ("Plan:" 96 times, the same
`hermes config get tts` line 79 times, reworded each time) for two hours: one stream ended cleanly at 02:01, Hermes asked for
four continuations (each hit the output cap) and kept the 806k-character partial as the final answer. Telegram got ~30
messages, then flood control for 257 s; the shutdown notice that the waker's stop triggers was refused by that same ban, and
the failed delivery stayed in the ledger to be resent whole on the next boot.
`RunawayStreamWatch` did not trip: it looks for exact repeats covering half the text, and this loop reworded itself (3495
lines, 3024 distinct). A line-repeat detector was measured and rejected: it only fired at 122k chars (55k with 10 repeats),
after this cap. The cap alone is enough: across every stack the only assistant message above 40k is this one.

Only the visible-text watches get the cap; reasoning channels keep Hermes's behaviour (long thinking is legitimate). A cut
sets `_runaway_repetition`, so `recover_from_truncation` ends the turn without any continuation, discards the partial and
tells the person to resend or switch model. Logged as "aibridge runaway_text_cap" (ops/wake/waker.py alerts the operator).

Write-safe: both new texts are computed before either file is written, and each write goes through a temp file + os.replace.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build
loudly. Re-running on already-patched files is a no-op.

Write safety: both files are patched in memory first and written only after every anchor matched, each through a temp file in
the same directory + os.replace. An earlier version opened the target with 'w' before the anchor checks, so a miss left
agent/repetition_guard.py empty and py_compile accepted it (found when scanning Hermes v0.23.1).

v0.23.1: only `RunawayStreamWatch.__slots__` changed (now sorted: "_chars", "_next_check", "_parts"); the other anchors are
unchanged. The new `detail_watch` (reasoning details) stays uncapped, like the other reasoning channels.
"""
import os
import shutil
import sys
import tempfile

MARK = "# aibridge-patch: runaway_text_cap"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


def patch_guard(src: str) -> str:
    src = replace_once(
        src,
        "import math\nfrom collections import Counter\n",
        "import logging\nimport math\nimport os\nfrom collections import Counter\n\n"
        f"logger = logging.getLogger(__name__)  {MARK}\n"
        "# Visible text of one model call above this ends the turn (0 = off). See patches/runaway_text_cap.py in aibridge.\n"
        "TEXT_ONLY_MAX_CHARS = int(os.environ.get(\"AIBRIDGE_TEXT_MAX_CHARS\") or \"40000\")  # empty = default, \"0\" = off\n",
        "imports")
    src = replace_once(
        src,
        '    __slots__ = ("_chars", "_next_check", "_parts")\n\n'
        "    def __init__(self) -> None:\n"
        "        self._parts: list[str] = []\n"
        "        self._chars = 0\n"
        "        self._next_check = STOP_PATH_MIN_CHARS\n",
        '    __slots__ = ("_chars", "_next_check", "_parts", "_max_chars")\n\n'
        f"    def __init__(self, max_chars: int = 0) -> None:  {MARK}\n"
        "        self._parts: list[str] = []\n"
        "        self._chars = 0\n"
        "        self._next_check = STOP_PATH_MIN_CHARS\n"
        "        self._max_chars = max_chars\n",
        "watch constructor")
    src = replace_once(
        src,
        "        self._parts.append(text)\n"
        "        self._chars += len(text)\n"
        "        if self._chars < self._next_check:\n",
        "        self._parts.append(text)\n"
        "        self._chars += len(text)\n"
        f"        if self._max_chars and self._chars >= self._max_chars:  {MARK}\n"
        "            logger.warning(\"aibridge runaway_text_cap: visible text reached %d chars in one model call (cap %d), \"\n"
        "                           \"cutting the stream\", self._chars, self._max_chars)\n"
        "            return True\n"
        "        if self._chars < self._next_check:\n",
        "size check in feed")
    return src


def patch_helpers(src: str) -> str:
    src = replace_once(
        src,
        "from agent.repetition_guard import RunawayStreamWatch, is_repetition_dominated\n",
        f"from agent.repetition_guard import RunawayStreamWatch, is_repetition_dominated, TEXT_ONLY_MAX_CHARS  {MARK}\n",
        "helpers import")
    src = replace_once(
        src,
        "        content_watch, reasoning_watch = RunawayStreamWatch(), RunawayStreamWatch()\n",
        f"        content_watch, reasoning_watch = RunawayStreamWatch(TEXT_ONLY_MAX_CHARS), RunawayStreamWatch()  {MARK}\n",
        "chat_completions watches")
    src = replace_once(
        src,
        "        text_watch, thinking_watch = RunawayStreamWatch(), RunawayStreamWatch()\n",
        f"        text_watch, thinking_watch = RunawayStreamWatch(TEXT_ONLY_MAX_CHARS), RunawayStreamWatch()  {MARK}\n",
        "second wire watches")
    return src


def write_atomic(path: str, text: str) -> None:
    """Write via a temp file in the same directory, then os.replace: a failure never leaves a truncated target."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aibridge-patch-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(guard_path: str, helpers_path: str) -> None:
    results = []  # (path, new text or None when already patched); nothing is written until all anchors matched
    for path, fn in ((guard_path, patch_guard), (helpers_path, patch_helpers)):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        results.append((path, None if MARK in src else fn(src)))
    for path, new in results:
        if new is None:
            print("already patched, nothing to do:", path)
            continue
        write_atomic(path, new)
        print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
