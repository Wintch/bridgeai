#!/usr/bin/env python3
"""Patch Hermes so a turn its own repetition guard cuts short tells the person something broke, instead of
silence.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: repetition_loop_notice.py <path to gateway/run.py>

Why (2026-10-24, hernik on Telegram): the local model got stuck repeating itself while building a
`text_to_speech` tool call's arguments. Hermes's own `agent.repetition_guard` correctly cut the stream
(`agent/turn_api_call.py::handle_api_interrupt`) and set `final_response` to its internal sentinel
(`agent.repetition_guard.REPETITION_LOOP_INTERRUPTED`, "[the reply degenerated into a repetition loop and
was interrupted]"), hidden from the replayed transcript by design so the looped bytes can't poison later
context (upstream #112764). `_sanitize_gateway_final_response` already special-cases one sentinel of this
shape -- `INTERRUPT_WAITING_FOR_MODEL_PREFIX` becomes silence, because a person who pressed Stop already
knows -- but nobody pressed Stop here, and nothing recognized the repetition guard's own sentinel: it either
went out verbatim in English brackets or never reached the person at all, depending on the turn's path.
hernik watched the chat sit with nothing, then the stack's idle-sleep closed the container a few minutes
later, looking like it had fallen asleep mid-thought.

Now this sentinel becomes the same already-localized "I had to stop before finishing" notice Hermes uses for
a truncated/partial turn (`gateway.errors.stopped_before_finishing`, already translated into every locale
with its own `/retry` hint), instead of the raw internal English text or nothing.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this
code fails the build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: repetition_loop_notice"


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
        '    # Cancellation metadata, not prose; ACP/TUI already suppress this sentinel, chat surfaces should too.\n'
        '    # See #7921.\n'
        '    if str(text).strip().startswith(INTERRUPT_WAITING_FOR_MODEL_PREFIX):\n'
        '        return ""\n',
        '    # Cancellation metadata, not prose; ACP/TUI already suppress this sentinel, chat surfaces should too.\n'
        '    # See #7921.\n'
        '    if str(text).strip().startswith(INTERRUPT_WAITING_FOR_MODEL_PREFIX):\n'
        '        return ""\n'
        '\n'
        f'    # The model degenerated into a repetition loop and was cut short (nobody pressed Stop): say so,\n'
        f'    # in the person\'s own language, instead of the raw internal sentinel or silence.  {MARK}\n'
        '    from agent.repetition_guard import REPETITION_LOOP_INTERRUPTED\n'
        '    if str(text).strip() == REPETITION_LOOP_INTERRUPTED:\n'
        '        return t("gateway.errors.stopped_before_finishing", reason="")\n',
        "repetition-loop sentinel",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
