#!/usr/bin/env python3
"""patches/code_python.py: applied to the real tools/code_execution_env.py of the pinned Hermes when the upstream clone is there
(else a stand-in), then _resolve_child_python is run with several settings. No network: python3 -I code_python_selftest.py"""
import os, shutil, subprocess, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
fails = []
def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(f"{name}: {detail}")

HEAD = '''def _resolve_child_python(mode: str) -> str:
    """Child interpreter: ``sys.executable`` in strict mode; in project mode the active
    VIRTUAL_ENV/CONDA_PREFIX python if it exists and passes the 3.8+ probe, else ``sys.executable``."""
'''
STAND_IN = ("import os\nimport sys\n\n\ndef _is_usable_python(python_path: str) -> bool:\n    return not python_path.endswith('broken')\n\n\n"
            + HEAD + "    return sys.executable\n")
tmp = tempfile.mkdtemp(prefix="code-python-selftest-")
try:
    src = os.path.join(tmp, "code_execution_env.py")
    real = subprocess.run(["git", "-C", "/mnt/nvme/bridgeai-build/hermes-src", "show",
                           "8fc0374447313e276f6b9a2764bfc750190c966a:tools/code_execution_env.py"], capture_output=True, text=True)
    used_real = real.returncode == 0 and HEAD in real.stdout
    open(src, "w").write(real.stdout if used_real else STAND_IN)
    patch = os.path.join(here, "patches", "code_python.py")
    r = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
    check("the patch applies once" + (" (on the pinned Hermes file)" if used_real else " (stand-in)"), r.returncode == 0 and "patched" in r.stdout, r.stdout + r.stderr)
    r2 = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
    check("applying it again is a no-op", r2.returncode == 0 and "already patched" in r2.stdout and open(src).read().count("aibridge-patch: code_python") == 1, r2.stderr)
    check("no temp file is left next to the target", not [f for f in os.listdir(tmp) if f.startswith(".code_exec_env.")], os.listdir(tmp))
    check("the patched file still compiles", subprocess.run([sys.executable, "-m", "py_compile", src]).returncode == 0)
    bad = os.path.join(tmp, "other.py"); open(bad, "w").write("import os\ndef _is_usable_python(p): return True\ndef _resolve_child_python(mode):\n    return 1\n")
    r3 = subprocess.run([sys.executable, "-I", patch, bad], capture_output=True, text=True)
    check("a Hermes whose function changed fails the build loudly, the file untouched",
          r3.returncode != 0 and "expected 1 match, found 0" in (r3.stderr + r3.stdout) and open(bad).read().endswith("return 1\n"), r3.stderr)

    # The function itself, on a stand-in module (the real one imports Hermes): same head, the patch, stock fallback
    stand = os.path.join(tmp, "stand.py"); open(stand, "w").write(STAND_IN)
    subprocess.run([sys.executable, "-I", patch, stand], capture_output=True)
    fake = os.path.join(tmp, "py3"); open(fake, "w").write("#!/bin/sh\n"); os.chmod(fake, 0o755)
    noexec = os.path.join(tmp, "py-noexec"); open(noexec, "w").write("x"); os.chmod(noexec, 0o644)
    broken = os.path.join(tmp, "py-broken"); open(broken, "w").write("#!/bin/sh\n"); os.chmod(broken, 0o755)
    def pick(value, mode="project"):
        env = dict(os.environ); env.pop("AIBRIDGE_CODE_PYTHON", None)
        if value is not None:
            env["AIBRIDGE_CODE_PYTHON"] = value
        code = ("import importlib.util as u, sys; s=u.spec_from_file_location('m', %r); m=u.module_from_spec(s); s.loader.exec_module(m);"
                "r=m._resolve_child_python(%r); print('STOCK' if r == sys.executable else r)") % (stand, mode)
        out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env)
        return out.stdout.strip() or out.stderr.strip()
    check("set to a usable interpreter: it is used, in project mode", pick(fake) == fake, pick(fake))
    check("... and in strict mode too", pick(fake, "strict") == fake, pick(fake, "strict"))
    check("unset or empty: the stock choice", pick(None) == "STOCK" and pick("") == "STOCK", (pick(None), pick("")))
    check("a relative path, a missing file, a file that cannot run, or one failing the probe: the stock choice",
          [pick(v) for v in ("py3", os.path.join(tmp, "nope"), noexec, broken)] == ["STOCK"] * 4,
          [pick(v) for v in ("py3", os.path.join(tmp, "nope"), noexec, broken)])
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("\n".join(fails) or "code_python_selftest: all ok")
sys.exit(1 if fails else 0)
