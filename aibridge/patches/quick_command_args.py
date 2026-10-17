#!/usr/bin/env python3
"""Patch Hermes so a `type: exec` quick command receives what the person typed after it (`/idioma ru` -> `... ru`).

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: quick_command_args.py <path to gateway/run_inbound.py>

Why (2026-10-17): the bot commands /idioma and /voz (reply language, voice) are quick commands that run
`gateway pref ...` without the model. Hermes runs the configured command as is and drops the arguments, so
`/idioma ru` could not say which language. The arguments are split on whitespace and each word is shell-quoted, so
nothing the person types is ever interpreted by the shell.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: quick_command_args"


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
        "                return True, await self._hm_run_exec_quick_command(command, exec_cmd), command\n",
        "                " + MARK + "\n"
        "                import shlex as _shlex\n"
        "                _words = (event.get_command_args() or \"\").split()[:4]\n"
        "                if _words:\n"
        "                    exec_cmd = exec_cmd + \" \" + \" \".join(_shlex.quote(w[:64]) for w in _words)\n"
        "                return True, await self._hm_run_exec_quick_command(command, exec_cmd), command\n",
        "exec quick command dispatch",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
