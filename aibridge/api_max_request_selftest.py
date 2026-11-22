#!/usr/bin/env python3
"""patches/api_max_request.py: applied to a stand-in of Hermes's api_server.py, then the cap is read with several settings. No Hermes, no network: python3 -I api_max_request_selftest.py"""
import importlib.util, os, subprocess, sys, tempfile
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))

here = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
LINE = "MAX_REQUEST_BYTES = 10_000_000  # 10 MB — accommodates long agent conversations with tool calls\n"
STAND_IN = "import os\nMAX_STORED_RESPONSES = 100\n" + LINE + "CHAT = 10.0\n"
src = os.path.join(tmp, "api_server.py")
open(src, "w").write(STAND_IN)

fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

patch = os.path.join(here, "patches", "api_max_request.py")
r = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
check("the patch applies once", r.returncode == 0 and "patched" in r.stdout)
r2 = subprocess.run([sys.executable, "-I", patch, src], capture_output=True, text=True)
check("applying it again is a no-op", r2.returncode == 0 and "already patched" in r2.stdout and open(src).read().count("aibridge-patch: api_max_request") == 1)
bad = os.path.join(tmp, "other.py"); open(bad, "w").write("import os\nMAX_REQUEST_BYTES = 5\n")
r3 = subprocess.run([sys.executable, "-I", patch, bad], capture_output=True, text=True)
check("a Hermes whose line changed fails the build loudly", r3.returncode != 0 and "expected 1 match, found 0" in (r3.stderr + r3.stdout))
dup = os.path.join(tmp, "dup.py"); open(dup, "w").write(STAND_IN + LINE)
r4 = subprocess.run([sys.executable, "-I", patch, dup], capture_output=True, text=True)
check("two matches fail too", r4.returncode != 0 and "found 2" in (r4.stderr + r4.stdout))
check("the patched file still compiles", subprocess.run([sys.executable, "-m", "py_compile", src]).returncode == 0)

def cap(value):
    env = dict(os.environ)
    env.pop("AIBRIDGE_API_MAX_REQUEST_MB", None)
    if value is not None:
        env["AIBRIDGE_API_MAX_REQUEST_MB"] = value
    out = subprocess.run([sys.executable, "-I", "-c", "import importlib.util as u;s=u.spec_from_file_location('m',%r);m=u.module_from_spec(s);s.loader.exec_module(m);print(m.MAX_REQUEST_BYTES)" % src],
                         capture_output=True, text=True, env=env)
    return out.stdout.strip()

check("default is 32 MB", cap(None) == "32000000")
check("a number sets it", cap("64") == "64000000")
check("a fraction above 1 works", cap("1.5") == "1500000")
check("not a number falls back", cap("lots") == "32000000")
check("below 1 falls back", cap("0") == "32000000" and cap("-4") == "32000000")
check("the 7.2 MB photo of the 413 fits (base64 + history)", int(cap(None)) > 7_176_157 * 4 // 3 + 1_000_000)

print("\n".join(fails) or "api_max_request_selftest: all ok")
sys.exit(1 if fails else 0)
