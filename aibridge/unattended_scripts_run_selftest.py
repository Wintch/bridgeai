#!/usr/bin/env python3
"""patches/unattended_scripts_run.py: applied to the real tools/approval.py of the pinned Hermes when the upstream clone is there
(else a stand-in with the same anchors). No network: python3 -I unattended_scripts_run_selftest.py
The behaviour (a web turn's `python3 -c` passes, `rm -rf /usr` in the same command does not) needs Hermes's own dependencies: it is
checked against the built image in ops/image_smoke.sh (unattended-scripts)."""
import os, shutil, subprocess, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
fails = []
def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(f"{name}: {detail}")

DEF = 'def _unattended_deny(command: str, ctx: _Unattended) -> dict | None:\n'
BODY = ('    pending = _unapproved_findings(command, _is_permanently_approved)\n'
        '    if pending is not None:\n'
        '        keys, description = pending\n')
STAND_IN = ('"""stand-in"""\nimport logging\nimport os\n\nlogger = logging.getLogger(__name__)\n\n\n' + DEF +
            '    """doc"""\n    if ctx.mode() != "deny":\n        return None\n' + BODY + '        return {"approved": False}\n    return None\n\n\n'
            'def _human_decision():\n    pass\n')
patch = os.path.join(here, "patches", "unattended_scripts_run.py")
MARK = "aibridge-patch: unattended_scripts_run"
tmp = tempfile.mkdtemp(prefix="unattended-scripts-selftest-")
try:
    src = os.path.join(tmp, "approval.py")
    real = subprocess.run(["git", "-C", "/mnt/nvme/bridgeai-build/hermes-src", "show",
                           "8fc0374447313e276f6b9a2764bfc750190c966a:tools/approval.py"], capture_output=True, text=True)
    used_real = real.returncode == 0 and DEF in real.stdout and BODY in real.stdout
    open(src, "w").write(real.stdout if used_real else STAND_IN)
    r = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
    check("the patch applies once" + (" (on the pinned Hermes file)" if used_real else " (stand-in)"),
          r.returncode == 0 and "patched" in r.stdout, r.stdout + r.stderr)
    r2 = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
    patched = open(src).read()
    check("applying it again is a no-op", r2.returncode == 0 and "already patched" in r2.stdout and patched.count(MARK) == 2, r2.stdout)
    d = patched.index(DEF)
    nxt = patched.find("\ndef ", d + len(DEF))
    check("the helper sits right before _unattended_deny", patched.index("def _aibridge_script_only(") < d)
    check("the allow sits inside _unattended_deny, after the findings", d < patched.index("_aibridge_script_only(command):") < nxt
          and patched.index(BODY, d) < patched.index("_aibridge_script_only(command):", d))
    check("only the unattended context is touched", 'if ctx.name == "unattended" and _aibridge_script_only(command):' in patched)
    check("the env switch defaults to the stock refusal", '!= "auto":' in patched and "return False" in patched)
    compile(patched, src, "exec")
    for name, text, msg in (("two definitions abort the build", STAND_IN + "\n" + DEF + "    pass\n",
                             "_unattended_deny definition: expected 1 match, found 2"),
                            ("a moved findings block aborts the build", STAND_IN.replace(BODY, "    pass\n"),
                             "_unattended_deny findings: expected 1 match, found 0")):
        bad = os.path.join(tmp, "bad.py")
        open(bad, "w").write(text)
        r3 = subprocess.run([sys.executable, "-I", patch, bad], capture_output=True, text=True)
        check(name, r3.returncode != 0 and msg in (r3.stdout + r3.stderr), r3.stdout + r3.stderr)
    image = open(os.path.join(here, "Dockerfile.hermes-agent")).read()
    check("the image applies it after approvals_no_ask_bridge, with AIBRIDGE_UNATTENDED_SCRIPTS=auto",
          "ENV AIBRIDGE_UNATTENDED_SCRIPTS=auto" in image
          and image.index("approvals_no_ask_bridge.py /root") < image.index("unattended_scripts_run.py /root"))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("\n".join(fails) or "unattended_scripts_run_selftest: all ok")
sys.exit(1 if fails else 0)
