#!/usr/bin/env python3
"""Patch Hermes so execute_code runs with no approval anywhere (AIBRIDGE_CODE_APPROVAL=auto, the image's default).

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: code_auto_approve.py <path to tools/approval.py>

Why: the people do not read Python. A whole-script approval in Telegram asked them to judge code they cannot read, and a web turn
(Hermes's api_server, no way to show an approval) was refused outright. On 2026-11-26 a long job search had Python refused at every try,
and the model worked around it with file patches and terminal calls. The operator's decision (2026-11-27): scripts are accepted by
default, on every platform. The code runs inside the person's own container, with the image's Python. The same model can already run
`python3 -c` through the terminal, where only flagged commands ask, so the whole-script prompt protected little and cost a lot.

Only the whole-script gate of execute_code changes. A flagged terminal() call made from inside the script still meets its own
per-call guard, and the hardline floor still blocks catastrophic commands. AIBRIDGE_CODE_APPROVAL=ask (or unset) restores the
stock behaviour for a stack whose owner wants to read each script (set it in that stack's compose environment).
Related: NOTICES.md (what each person is told and asked), IMAGE_SECURITY.md.

The anchor must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
The new text is compiled before the file is written, and the write goes through a temp file in the same folder. Re-running on an
already-patched file is a no-op.
"""
import os
import sys
import tempfile

MARK = "# aibridge-patch: code_auto_approve"

OLD = '''    # (-q clears the presence flags, but its unattended context resolves first anyway.)
    approval_callback, is_cli, is_gateway, is_ask = _presence()
'''

NEW = OLD + '''    ''' + MARK + ''': scripts are accepted by default (the people do not read Python); AIBRIDGE_CODE_APPROVAL=ask restores the gate
    if os.environ.get("AIBRIDGE_CODE_APPROVAL", "").strip().lower() == "auto":
        return _approved()
'''



def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    n = src.count(OLD)
    if n != 1:
        sys.exit(f"patch failed: check_execute_code_guard presence line: expected 1 match, found {n}")
    if "\nimport os\n" not in src:
        sys.exit("patch failed: the module no longer imports os at module level")
    if "def _approved() -> dict:" not in src or "def check_execute_code_guard(" not in src:
        sys.exit("patch failed: _approved or check_execute_code_guard is no longer in the module")
    new = src.replace(OLD, NEW, 1)
    if new.index(MARK) < new.index("def check_execute_code_guard("):
        sys.exit("patch failed: the anchor is no longer inside check_execute_code_guard")
    compile(new, path, "exec")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".approval.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new)
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
