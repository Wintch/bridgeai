#!/usr/bin/env python3
"""Patch Hermes's `browser_exec` tool so the model is told, in the tool's own description and in a failed result, that
the code is synchronous (no await, no asyncio, no Playwright).

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: browser_exec_hint.py <path to tools/browser_use_cli.py>

Why (2026-11-02/03, hernik): `browser_exec` runs the code with `exec()` at the top level of a fresh interpreter, with
blocking helpers (new_tab, wait_for_load, js, ...) already imported. Models write Playwright or asyncio code out of habit:
10 of 17 calls failed on 11-01/02 and 7 of 8 on 11-02/03 ("'await' outside function", "'str' object can't be awaited",
"No module named 'playwright'", "await is only valid in async functions" from js()). The skill `browser-exec` explains the
pattern, but the agent never loaded it before calling the tool. The description travels with every request; the hint on
a failed result catches the retry.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: browser_exec_hint"

RULE = (
    "SYNCHRONOUS ONLY: `code` is run with exec() at the top level and every helper is a plain blocking function. "
    "Never write await, async def or asyncio, and never import playwright or selenium (not installed). Wait with "
    "wait_for_load() or time.sleep(); inside js() use plain expressions (no await, no Promise). "
    "Pattern: new_tab(url); wait_for_load(); print(js('document.title')). More: skill browser-exec."
)

# Words in a failed run that mean the code was written for Playwright/asyncio
ASYNC_SIGNS = ("await", "asyncio", "playwright", "coroutine", "can't be awaited", "async def")


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
    # 1. the description: the rule goes right after the helpers digest, which every variant of the schema carries
    src = replace_once(
        src,
        '    "credentials; see the vault note below if present, otherwise stop and ask the user."\n)\n',
        '    "credentials; see the vault note below if present, otherwise stop and ask the user."\n'
        f'    "\\n\\n" {RULE!r}  {MARK}\n)\n',
        "helpers digest end",
    )
    # 2. a failed run whose output shows async/Playwright code gets the rule back as `hint`
    src = replace_once(
        src,
        "    screenshot = _find_screenshot(proc.stdout, started)\n",
        f"    if proc.returncode != 0:  {MARK}\n"
        "        _blob = ((stderr or \"\") + \" \" + (result.get(\"output\") or \"\")).lower()\n"
        f"        if any(_s in _blob for _s in {ASYNC_SIGNS!r}):\n"
        f"            result[\"hint\"] = {RULE!r}\n"
        "    screenshot = _find_screenshot(proc.stdout, started)\n",
        "result before screenshot lookup",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
