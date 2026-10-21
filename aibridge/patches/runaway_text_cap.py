#!/usr/bin/env python3
"""Patch Hermes so one streamed reply cannot grow without limit: the visible text of a single model call is cut at
AIBRIDGE_TEXT_MAX_CHARS (default 40000) and the turn ends, exactly as Hermes already does for a verbatim repetition loop.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: runaway_text_cap.py <agent/repetition_guard.py> <agent/chat_completion_helpers.py>

Why (2026-10-21, hernik on Telegram, stepfun-ai/step-5-preview): asked for a comparison of the spoken voices, the model never
called a tool. It wrote its deliberation as the reply ("Plan:" 96 times, the same
`hermes config get tts` line 79 times, reworded each time) for two hours: one stream ended cleanly at 02:01, Hermes asked for
four continuations (each hit the output cap) and kept the 806k-character partial as the final answer. Telegram got ~30
messages, then flood control for 257 s; the shutdown notice that the waker's stop triggers was refused by that same ban, and
the failed delivery stayed in the ledger to be resent whole on the next boot.
`RunawayStreamWatch` did not trip: it looks for exact repeats covering half the text, and this loop reworded itself (3495
lines, 3024 distinct). A line-repeat detector was measured and rejected: it only fired at 122k chars (55k with 10 repeats),
after this cap. The cap alone is enough: across hernik, herand and hereug the only assistant message above 40k is this one.

Only the visible-text watches get the cap; reasoning channels keep Hermes's behaviour (long thinking is legitimate). A cut
sets `_runaway_repetition`, so `recover_from_truncation` ends the turn without any continuation, discards the partial and
tells the person to resend or switch model. Logged as "aibridge runaway_text_cap" (ops/wake/waker.py alerts the operator).

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build
loudly. Re-running on already-patched files is a no-op.
"""
import sys

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
        '    __slots__ = ("_parts", "_chars", "_next_check")\n\n'
        "    def __init__(self) -> None:\n"
        "        self._parts: list[str] = []\n"
        "        self._chars = 0\n"
        "        self._next_check = STOP_PATH_MIN_CHARS\n",
        '    __slots__ = ("_parts", "_chars", "_next_check", "_max_chars")\n\n'
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


def main(guard_path: str, helpers_path: str) -> None:
    for path, fn in ((guard_path, patch_guard), (helpers_path, patch_helpers)):
        src = open(path, encoding="utf-8").read()
        if MARK in src:
            print("already patched, nothing to do:", path)
            continue
        open(path, "w", encoding="utf-8").write(fn(src))
        print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
