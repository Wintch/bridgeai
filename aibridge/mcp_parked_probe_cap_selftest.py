#!/usr/bin/env python3
"""patches/mcp_parked_probe_cap.py: applied to the real tools/mcp_tool.py of the pinned Hermes when the upstream clone is there (else a
stand-in), then the cap is read with several settings. No network: python3 -I mcp_parked_probe_cap_selftest.py"""
import os, shutil, subprocess, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
fails = []
def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(f"{name}: {detail}")

tmp = tempfile.mkdtemp(prefix="mcp-parked-selftest-")
try:
    STAND_IN = "import asyncio\nimport os\n\n_PARKED_RETRY_INTERVAL = 300\n"
    LINE = "_PARKED_PROBE_BACKOFF_MAX = 3600\n"
    src = os.path.join(tmp, "mcp_tool.py")
    real = subprocess.run(["git", "-C", "/mnt/nvme/bridgeai-build/hermes-src", "show",
                           "8fc0374447313e276f6b9a2764bfc750190c966a:tools/mcp_tool.py"], capture_output=True, text=True)
    open(src, "w").write(real.stdout if real.returncode == 0 and LINE in real.stdout else STAND_IN + LINE + "_STDIO_RESPAWN_WAIT_SEC = 15.0\n")
    patch = os.path.join(here, "patches", "mcp_parked_probe_cap.py")
    r = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
    check("the patch applies once", r.returncode == 0 and "patched" in r.stdout, r.stdout + r.stderr)
    r2 = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
    check("applying it again is a no-op", r2.returncode == 0 and "already patched" in r2.stdout
          and open(src).read().count("aibridge-patch: mcp_parked_probe_cap") == 1, r2.stdout + r2.stderr)
    check("no temp file is left next to the target", not [f for f in os.listdir(tmp) if f.startswith(".mcp_tool.")], os.listdir(tmp))
    bad = os.path.join(tmp, "other.py"); open(bad, "w").write("import os\n_PARKED_PROBE_BACKOFF_MAX = 7200\n")
    r3 = subprocess.run([sys.executable, "-I", patch, bad], capture_output=True, text=True)
    check("a Hermes whose line changed fails the build loudly, the file untouched",
          r3.returncode != 0 and "expected 1 match, found 0" in (r3.stderr + r3.stdout) and open(bad).read().endswith("7200\n"), r3.stderr)
    noos = os.path.join(tmp, "noos.py"); open(noos, "w").write("import asyncio\n" + LINE)
    r4 = subprocess.run([sys.executable, "-I", patch, noos], capture_output=True, text=True)
    check("a module that no longer imports os fails instead of breaking at import", r4.returncode != 0 and "imports os" in (r4.stderr + r4.stdout), r4.stderr)

    # The cap itself: only the patched block, run with the module's own os (no Hermes imports needed)
    body = open(src).read()
    block = body[body.index("# aibridge-patch: mcp_parked_probe_cap"):]
    block = block[:block.index("_PARKED_PROBE_BACKOFF_MAX = _aibridge_parked_probe_max()") + len("_PARKED_PROBE_BACKOFF_MAX = _aibridge_parked_probe_max()")]
    def cap(value):
        env = dict(os.environ); env.pop("AIBRIDGE_MCP_PARKED_PROBE_MAX_S", None)
        if value is not None:
            env["AIBRIDGE_MCP_PARKED_PROBE_MAX_S"] = value
        out = subprocess.run([sys.executable, "-I", "-c", "import os\n" + block + "\nprint(_PARKED_PROBE_BACKOFF_MAX)"], capture_output=True, text=True, env=env)
        return out.stdout.strip() or out.stderr
    check("default: 300 s, the first interval (no backoff, as on v0.21.6)", cap(None) == "300.0", cap(None))
    check("a setting is honoured", cap("900") == "900.0", cap("900"))
    check("not a number, or below 60: the default", cap("x") == "300.0" and cap("5") == "300.0", (cap("x"), cap("5")))
    check("the patched file still compiles", subprocess.run([sys.executable, "-m", "py_compile", src]).returncode == 0)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("\n".join(fails) or "mcp_parked_probe_cap_selftest: all ok")
sys.exit(1 if fails else 0)
