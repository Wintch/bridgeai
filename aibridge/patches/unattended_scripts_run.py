#!/usr/bin/env python3
"""Patch Hermes so a terminal command whose ONLY findings are "script execution" (-c/-e flag, interpreter heredoc) runs on an
unattended platform (web / api_server) instead of being refused (AIBRIDGE_UNATTENDED_SCRIPTS=auto, the image's default).

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: unattended_scripts_run.py <path to tools/approval.py>

Why: the operator's decision (2026-11-28): code runs without asking on every platform, the web included. execute_code already does
(patches/code_auto_approve.py), but the same script typed as `python3 -c ...`, `node -e ...` or `python3 - <<EOF` in the terminal
was still refused on the web with "BLOCKED: Command flagged as dangerous (script execution ...) but this session runs on an
unattended platform". A web-only person got 12 such refusals in November and the model worked around them with extra calls, which
made long turns longer. The command runs inside the person's own container, exactly as execute_code does.

What still blocks, unchanged: the hardline floor, the person's approvals.deny rules, a command the scanner could not read to the end
(all of them run before this code), and every other finding: a command that also matches anything else (delete in root path,
pipe to shell, credential upload, ...) keeps the stock refusal. The check walks EVERY match of the detector, not only the first
one the stock gate reports, so `python3 -c x; rm -rf /usr` is still refused. Only the "unattended" context changes: cron and -q
keep their own modes. AIBRIDGE_UNATTENDED_SCRIPTS=deny (or unset) restores the stock behaviour for a stack.
Related: NOTICES.md, IMAGE_SECURITY.md.

The anchors must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
The new text is compiled before the file is written, and the write goes through a temp file in the same folder. Re-running on an
already-patched file is a no-op.
"""
import os
import sys
import tempfile

MARK = "# aibridge-patch: unattended_scripts_run"

DEF_ANCHOR = '''def _unattended_deny(command: str, ctx: _Unattended) -> dict | None:
'''

HELPER = MARK + ''': the findings that alone may run on an unattended platform (AIBRIDGE_UNATTENDED_SCRIPTS=auto)
_AIBRIDGE_SCRIPT_ONLY = frozenset({"script execution via -e/-c flag", "script execution via heredoc"})


def _aibridge_script_only(command: str) -> bool:
    """True when every dangerous match of *command* is a script-execution finding (and there is at least one)."""
    if os.environ.get("AIBRIDGE_UNATTENDED_SCRIPTS", "").strip().lower() != "auto":
        return False
    try:
        from tools import approval_detection as _det
        if _det.hardline_scan_incomplete(command):
            return False
        with _det._parser_budget.parser_budget(command):
            found = set(_det._iter_dangerous_descriptions(command))
        found |= set(_det.detect_content_rule_keys(command))
    except Exception:  # any doubt keeps the stock refusal
        return False
    return bool(found) and found <= _AIBRIDGE_SCRIPT_ONLY


'''

BODY_ANCHOR = '''    pending = _unapproved_findings(command, _is_permanently_approved)
    if pending is not None:
        keys, description = pending
'''

BODY_NEW = BODY_ANCHOR + '''        ''' + MARK + ''': a script the person's own container runs, as execute_code does
        if ctx.name == "unattended" and _aibridge_script_only(command):
            logger.warning("AUTO-APPROVED script command on an unattended platform (%s; AIBRIDGE_UNATTENDED_SCRIPTS=auto)",
                           description)
            return None
'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    for name, anchor in (("_unattended_deny definition", DEF_ANCHOR), ("_unattended_deny findings", BODY_ANCHOR)):
        n = src.count(anchor)
        if n != 1:
            sys.exit(f"patch failed: {name}: expected 1 match, found {n}")
    if "\nimport os\n" not in src or "\nlogger = " not in src:
        sys.exit("patch failed: the module no longer imports os or defines logger at module level")
    new = src.replace(DEF_ANCHOR, HELPER + DEF_ANCHOR, 1)
    start = new.index(DEF_ANCHOR)
    nxt = new.find("\ndef ", start + len(DEF_ANCHOR))
    seg = new[start:nxt]
    if seg.count(BODY_ANCHOR) != 1:
        sys.exit("patch failed: the findings anchor is no longer inside _unattended_deny")
    new = new[:start] + seg.replace(BODY_ANCHOR, BODY_NEW, 1) + new[nxt:]
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
