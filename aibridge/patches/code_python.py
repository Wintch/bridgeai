#!/usr/bin/env python3
"""Patch Hermes so execute_code runs the image's system Python (AIBRIDGE_CODE_PYTHON) instead of Hermes's own interpreter.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: code_python.py <path to tools/code_execution_env.py>

Why: execute_code picks its child interpreter in _resolve_child_python: an active VIRTUAL_ENV/CONDA_PREFIX python in project
mode, else sys.executable, which is Hermes's own Python (3.14 under ~/.hermes/tools). Everything the skills need is baked into
the system Python by hash (openpyxl, python-docx and python-pptx for the office skill, pdfplumber, pypdf, reportlab, Pillow and the
rest), and Hermes's interpreter has none of it. So a model that writes a workbook with execute_code got ModuleNotFoundError, then
tried pip and a venv (both closed on purpose) before it found the terminal. With AIBRIDGE_CODE_PYTHON set (the Dockerfile sets
/usr/bin/python3) and that interpreter passing upstream's own probe (_is_usable_python: 3.8+ and starts), it is used in either
mode. Upstream already supports an interpreter outside its environment (a project venv): the hermes_tools stub it generates is
standard library only, and Hermes's own root is left off that interpreter's PYTHONPATH. Unset, missing or failing the probe: the
stock choice.

The replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
The new text is compiled before the file is written, and the write goes through a temp file in the same folder. Re-running on an
already-patched file is a no-op.
"""
import os
import re
import sys
import tempfile

MARK = "# aibridge-patch: code_python"

OLD = '''def _resolve_child_python(mode: str) -> str:
    """Child interpreter: ``sys.executable`` in strict mode; in project mode the active
    VIRTUAL_ENV/CONDA_PREFIX python if it exists and passes the 3.8+ probe, else ``sys.executable``."""
'''

NEW = OLD + '''    ''' + MARK + '''
    _aib = os.environ.get("AIBRIDGE_CODE_PYTHON", "").strip()
    if _aib and os.path.isabs(_aib) and os.path.isfile(_aib) and os.access(_aib, os.X_OK) and _is_usable_python(_aib):
        return _aib
'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    n = src.count(OLD)
    if n != 1:
        sys.exit(f"patch failed: _resolve_child_python head: expected 1 match, found {n}")
    if not re.search(r"^import (?:[\w.]+, *)*os\b", src, re.M):
        sys.exit("patch failed: the module no longer imports os at module level")
    if "def _is_usable_python(" not in src:
        sys.exit("patch failed: _is_usable_python is no longer in the module")
    new = src.replace(OLD, NEW, 1)
    compile(new, path, "exec")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".code_exec_env.", suffix=".tmp")
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
