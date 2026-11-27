#!/usr/bin/env python3
"""patches/code_auto_approve.py: applied to the real tools/approval.py of the pinned Hermes when the upstream clone is there (else a
stand-in), then the patched check is run with a stubbed context. No network: python3 -I code_auto_approve_selftest.py
The real end-to-end check (Hermes imported, an api_server turn) is in ops/image_smoke.sh (code-auto-approve)."""
import os, shutil, subprocess, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
fails = []
def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(f"{name}: {detail}")

ANCHOR = ('    # (-q clears the presence flags, but its unattended context resolves first anyway.)\n'
          '    approval_callback, is_cli, is_gateway, is_ask = _presence()\n')
STAND_IN = ('"""stand-in"""\nimport os\nfrom ctx import _is_unattended_platform_approval_context, _is_cron_approval_context, _is_single_query_approval_context\n\n\n'
            'def _approved() -> dict:\n    return {"approved": True}\n\n\ndef _presence():\n    return None, False, False, False\n\n\n'
            'def check_execute_code_guard(code, env_type, has_host_access=False) -> dict:\n' + ANCHOR + '    return {"approved": False}\n')
tmp = tempfile.mkdtemp(prefix="code-auto-approve-selftest-")
try:
    src = os.path.join(tmp, "approval.py")
    real = subprocess.run(["git", "-C", "/mnt/nvme/bridgeai-build/hermes-src", "show",
                           "8fc0374447313e276f6b9a2764bfc750190c966a:tools/approval.py"], capture_output=True, text=True)
    used_real = real.returncode == 0 and ANCHOR in real.stdout
    open(src, "w").write(real.stdout if used_real else STAND_IN)
    patch = os.path.join(here, "patches", "code_auto_approve.py")
    r = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
    check("the patch applies once" + (" (on the pinned Hermes file)" if used_real else " (stand-in)"), r.returncode == 0 and "patched" in r.stdout, r.stdout + r.stderr)
    r2 = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
    check("applying it again is a no-op", r2.returncode == 0 and "already patched" in r2.stdout
          and open(src).read().count("aibridge-patch: code_auto_approve") == 1, r2.stderr)
    patched = open(src).read()
    check("the new lines sit inside check_execute_code_guard",
          patched.index("def check_execute_code_guard(") < patched.index("aibridge-patch: code_auto_approve"))
    bad = os.path.join(tmp, "bad.py")
    open(bad, "w").write(STAND_IN.replace(ANCHOR, ANCHOR + ANCHOR))
    r3 = subprocess.run([sys.executable, "-I", patch, bad], capture_output=True, text=True)
    check("two anchors abort the build", r3.returncode != 0 and "expected 1 match, found 2" in (r3.stdout + r3.stderr), r3.stderr)
    # behaviour, on the stand-in: the module imports the three context functions from a stub we control
    stub_dir = os.path.join(tmp, "stub")
    os.makedirs(stub_dir)
    open(os.path.join(stub_dir, "approval.py"), "w").write(STAND_IN)
    subprocess.run([sys.executable, "-I", patch, os.path.join(stub_dir, "approval.py")], capture_output=True, check=True)
    def run(env_val, platform, cron=False, single=False):
        open(os.path.join(stub_dir, "ctx.py"), "w").write(
            f"def _is_unattended_platform_approval_context(): return {platform!r} in ('api_server', 'webhook')\n"
            f"def _is_cron_approval_context(): return {cron}\n"
            f"def _is_single_query_approval_context(): return {single}\n")
        env = {k: v for k, v in os.environ.items() if k != "AIBRIDGE_CODE_APPROVAL"}
        if env_val is not None:
            env["AIBRIDGE_CODE_APPROVAL"] = env_val
        out = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import approval; "
                              "print(approval.check_execute_code_guard('print(1)', 'local')['approved'])", stub_dir],
                             capture_output=True, text=True, env=env)
        return out.stdout.strip()
    check("AIBRIDGE_CODE_APPROVAL=auto: a web turn runs", run("auto", "api_server") == "True")
    check("auto: a Telegram turn runs with no prompt", run("auto", "telegram") == "True")
    check("auto: cron and -q runs too", (run("auto", "api_server", cron=True), run("auto", "", single=True)) == ("True", "True"))
    check("unset: stock gate (refused in the stand-in)", run(None, "api_server") == "False")
    check("ask, or any other value: stock gate", (run("ask", "telegram"), run("yes", "telegram")) == ("False", "False"))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("\n".join(fails) or "code_auto_approve_selftest: all ok")
sys.exit(1 if fails else 0)
