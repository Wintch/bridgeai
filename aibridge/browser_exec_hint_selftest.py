#!/usr/bin/env python3
"""Self-test for patches/browser_exec_hint.py on a stand-in of Hermes's tools/browser_use_cli.py (the two anchors, verbatim).
The real file is checked at image build time (the patch aborts unless each anchor matches once). Run: python3 -I browser_exec_hint_selftest.py
"""
import os
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


STANDIN = '''
_HELPERS_DIGEST = (
    "HELPERS (pre-imported): new_tab(url) ... Login walls: never guess "
    "credentials; see the vault note below if present, otherwise stop and ask the user."
)


def _find_screenshot(out, started):
    return None


def run(returncode, stdout, stderr):
    class P: pass
    proc = P(); proc.returncode, proc.stdout, proc.stderr = returncode, stdout, stderr
    started = 0
    result = {"success": proc.returncode == 0, "exit_code": proc.returncode, "output": proc.stdout}
    stderr = (proc.stderr or "").strip()
    if stderr:
        result["stderr"] = stderr
    screenshot = _find_screenshot(proc.stdout, started)
    return result
'''

d = tempfile.mkdtemp()
p = os.path.join(d, "browser_use_cli.py")
open(p, "w").write(STANDIN)
patch = os.path.join(HERE, "patches", "browser_exec_hint.py")
r1 = subprocess.run([sys.executable, patch, p], capture_output=True, text=True)
r2 = subprocess.run([sys.executable, patch, p], capture_output=True, text=True)
check("the patch applies to the stand-in", r1.returncode == 0 and "patched" in r1.stdout, r1.stdout + r1.stderr)
check("a second run is a no-op", r2.returncode == 0 and "already patched" in r2.stdout, r2.stdout + r2.stderr)

m = types.ModuleType("bu")
exec(compile(open(p).read(), p, "exec"), m.__dict__)
desc = m._HELPERS_DIGEST
check("the description keeps the upstream text", desc.startswith("HELPERS (pre-imported)") and "ask the user." in desc)
check("the description says synchronous, no await, no Playwright, and names the skill",
      all(w in desc for w in ("SYNCHRONOUS ONLY", "await", "playwright", "browser-exec")), desc)

cases = [
    (1, "", "SyntaxError: 'await' outside function", True, "await outside function"),
    (1, "", "ModuleNotFoundError: No module named 'playwright'", True, "playwright import"),
    (1, "", "TypeError: 'str' object can't be awaited", True, "awaiting a helper"),
    (1, "", "RuntimeError: await is only valid in async functions; expression: await new Promise(r => setTimeout(r, 500))", True, "await inside js()"),
    (1, "", "TimeoutError: page did not load", False, "an unrelated failure"),
    (0, "await is a word in the page text", "", False, "a successful run that prints the word await"),
]
for rc, out, err, want, what in cases:
    res = m.run(rc, out, err)
    check(f"hint {'added' if want else 'not added'}: {what}", ("hint" in res) == want, res)

bad = os.path.join(d, "other.py")
open(bad, "w").write("x = 1\n")
r3 = subprocess.run([sys.executable, patch, bad], capture_output=True, text=True)
check("a file without the anchors fails loudly", r3.returncode != 0 and "expected 1 match" in (r3.stdout + r3.stderr), r3.stderr)

print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
