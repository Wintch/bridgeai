#!/usr/bin/env python3
"""Patch Hermes so a tool call the model wrote as plain text is re-prompted instead of ending the turn as if it ran.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: text_tool_call_retry.py <path to agent/turn_final_response.py>

Why (on Telegram): asked for a short clip, nemotron-3.5-super answered "it takes 3-7 minutes, I start
it in the background" followed by `[{"name": "terminal", "arguments": {"command": "gateway makevideo ...",
"background": true}}]` as reply text, finish_reason=stop, no real tool call. Nothing was started. Twelve minutes later
"did it finish?" got "not yet, I'll check again" (it looked for the file, then for a tool that does not exist), and the
stack went to sleep with the person still waiting. The router's evaluation log marked the answer leak=1 (1 of 527
answers of that model), but a streamed answer cannot be retried there.

Hermes already re-prompts the twin case, finish_reason="tool_calls" with no tool call (`_dropped_toolcall_retries`, at
most 3 in a row, both halves of the retry pair flagged `_dropped_toolcall_nudge` so they are never persisted). This patch
sends a text answer into that same path when, outside ``` code blocks, it holds a JSON object (or a list of them) whose
"name" (or "tool"/"tool_name", or function.name) is one of the session's real tools and which carries "arguments"
("parameters"/"args"/"input"). The re-prompt names the tool, says nothing ran, and says not to run it when it was only an
example the person asked to see. Code blocks are skipped on purpose: a person may ask to see a call written out.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: text_tool_call_retry"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


HELPER = '''def _text_tool_call(text, agent):  # aibridge-patch: text_tool_call_retry
    """Name of a real tool whose call the model wrote as reply text (outside ``` blocks), else None."""
    import json as _json
    import re as _re
    names = set(getattr(agent, "valid_tool_names", None) or ())
    if not names or not isinstance(text, str) or '"' not in text:
        return None
    prose = _re.sub(r"```.*?(?:```|$)", "", text[:20000], flags=_re.S)
    dec, i = _json.JSONDecoder(), 0
    while True:
        starts = [k for k in (prose.find("{", i), prose.find("[", i)) if k >= 0]
        if not starts:
            return None
        j = min(starts)
        try:
            obj, end = dec.raw_decode(prose, j)
        except ValueError:
            i = j + 1
            continue
        for c in obj if isinstance(obj, list) else [obj]:
            if not isinstance(c, dict):
                continue
            f = c["function"] if isinstance(c.get("function"), dict) else c
            n = f.get("name") or f.get("tool") or f.get("tool_name")
            if isinstance(n, str) and n in names and any(isinstance(f.get(k), (dict, str)) for k in ("arguments", "parameters", "args", "input")):
                return n
        i = max(end, j + 1)


def _text_tool_call_nudge(name):  # aibridge-patch: text_tool_call_retry
    return (f"Your previous reply wrote a `{name}` tool call as plain text instead of calling the tool, so it did NOT run "
            "and nothing was started. Do not tell the person that anything is running. If you meant to run it, make the "
            "call now through the tool-calling interface (never as text) and answer from its result. If it was only an "
            "example the person asked to see, reply again without running anything.")


'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    src = replace_once(src, "@dataclass\nclass FinalResponseVerdict:", HELPER + "@dataclass\nclass FinalResponseVerdict:",
                       "helper insertion point")
    src = replace_once(
        src,
        """    if (
        finish_reason == "tool_calls"
        and not assistant_message.tool_calls
        and getattr(agent, "_dropped_toolcall_retries", 0) < 3
    ):""",
        """    _leaked_tool = None if finish_reason == "tool_calls" else _text_tool_call(final_response, agent)  # aibridge-patch: text_tool_call_retry
    if (
        (finish_reason == "tool_calls" or _leaked_tool)
        and not assistant_message.tool_calls
        and getattr(agent, "_dropped_toolcall_retries", 0) < 3
    ):""",
        "dropped tool-call condition")
    src = replace_once(
        src,
        """            "content": _DROPPED_TOOLCALL_NUDGE_CONTENT,""",
        """            "content": _text_tool_call_nudge(_leaked_tool) if _leaked_tool else _DROPPED_TOOLCALL_NUDGE_CONTENT,""",
        "nudge content")
    open(path, "w", encoding="utf-8").write(src)
    print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
