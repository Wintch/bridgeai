#!/usr/bin/env python3
"""Patch Hermes so a `type: exec` quick command receives what the person typed after it (`/idioma ru` -> `... ru`).

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: quick_command_args.py <path to gateway/run_inbound_hooks.py>

Why: the bot commands /idioma and /voz (reply language, voice) are quick commands that run
`gateway pref ...` without the model. Hermes runs the configured command as is and drops the arguments, so
`/idioma ru` could not say which language. The arguments are split on whitespace and each word is shell-quoted, so
nothing the person types is ever interpreted by the shell.

v0.23.1: the dispatch moved from gateway/run_inbound.py to gateway/run_inbound_hooks.py (the anchor line is unchanged).
v0.23.4: the call passes `home=` and binds `reply`; the anchor follows it.
Not patched: gateway/session_commands.py has a second exec path (local/desktop sessions, `_hm_run_exec_quick_command(name, shell, cwd=cwd)`)
that still drops the arguments. Telegram does not use it, so it stays as upstream.

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


def write_atomic(path: str, text: str) -> None:
    """Write via a temp file in the same directory + os.replace, so a crash never leaves a half-written target."""
    import os
    import shutil
    tmp = path + ".aibridge-tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    src = replace_once(
        src,
        "                reply = await self._hm_run_exec_quick_command(command, exec_cmd, home=self._hm_quick_commands_home())\n",
        "                " + MARK + "\n"
        "                import shlex as _shlex\n"
        "                _words = (event.get_command_args() or \"\").split()[:4]\n"
        "                if _words:\n"
        "                    exec_cmd = exec_cmd + \" \" + \" \".join(_shlex.quote(w[:64]) for w in _words)\n"
        "                reply = await self._hm_run_exec_quick_command(command, exec_cmd, home=self._hm_quick_commands_home())\n",
        "exec quick command dispatch",
    )
    write_atomic(path, src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
