#!/usr/bin/env python3
"""Patch Hermes so OUR commands run while the agent is answering, instead of reaching the model as plain text.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: busy_own_commands.py <path to gateway/run_inbound.py>

Why (2026-11-06): on the busy fast-path Hermes recognises a command only through `hermes_cli.commands.resolve_command`, the registry of its own
built-ins (/stop, /new, /status...). Quick commands (/estado, /idioma, /voz, /avisos) and plugin commands (/parar, /dormir, /trabajos,
/manual, /opinion...) never enter that registry, so while a turn ran they were folded into the turn as ordinary text and did nothing: the person
typed /parar to stop the downloads exactly when the agent was busy, and the model "read" it. /parar and /dormir exist so that the person does not
depend on the model, and they must work then most of all.

The fix reuses Hermes's own dispatcher for these commands (`_hm_dispatch_quick_and_plugin_commands`: the same code the idle path runs, the same
access check for quick commands). It acts only when the typed name is one of our quick or plugin commands and the gateway is not draining; any other
text, and every registry command, takes the path it took before.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: busy_own_commands"

ANCHOR = (
    "        # Telegram photo bursts arrive as near-simultaneous updates — never interrupt for a\n"
    "        # photo-only follow-up; adapter-level batching absorbs them.\n"
    "        if event.message_type == MessageType.PHOTO:\n"
)

BLOCK = (
    "        " + MARK + "\n"
    "        # Our quick and plugin commands are not in the registry above: run them now, with the idle path's own dispatcher,\n"
    "        # instead of letting the running turn read them as text.\n"
    "        if _evt_cmd and not self._draining:\n"
    "            try:\n"
    "                from hermes_cli.plugins import get_plugin_command_handler as _own_handler\n"
    "                _own = bool(self._hm_quick_commands().get(_evt_cmd)) or bool(_own_handler(_evt_cmd.replace(\"_\", \"-\")))\n"
    "            except Exception:\n"
    "                _own = False\n"
    "            if _own:\n"
    "                _own_handled, _own_result, _own_cmd = await self._hm_dispatch_quick_and_plugin_commands(event, source, _evt_cmd)\n"
    "                if _own_handled:\n"
    "                    return True, _own_result\n"
    "\n"
)


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
    src = replace_once(src, ANCHOR, BLOCK + ANCHOR, "busy slash/photo fast-path")
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
