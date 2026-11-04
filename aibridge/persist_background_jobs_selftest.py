#!/usr/bin/env python3
"""Selftest for patches/persist_background_jobs.py: the patch applies once, aborts when Hermes changes, and the patched
handler makes a bounded background job (notify / notify_on_complete / heartbeat) persist across /new while a silent one
(a server), a pattern watcher and a foreground command do not. Run: python3 persist_background_jobs_selftest.py (offline)."""
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.path.join(HERE, "patches", "persist_background_jobs.py")
spec = importlib.util.spec_from_file_location("pbj", PATCH)
pbj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pbj)

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


# The shape of Hermes's terminal handler (tools/terminal_tool.py, commit pinned in the Dockerfile), reduced to what the
# patch touches: the flags are normalised, then terminal_tool(...) is called with them.
HANDLER = (
    "CALLS = []\n"
    "def terminal_tool(**kw):\n"
    "    CALLS.append(kw)\n"
    "\n"
    "def handler(args, **kw):\n"
    "    notify_on_complete = args.get('notify_on_complete', False)\n"
    "    watch_patterns = args.get('watch_patterns')\n"
    "    heartbeat = args.get('heartbeat') or 0\n"
    "    persist_on_release = bool(args.get('persist_on_release', False))\n"
    "    if args.get('notify') is True:\n"
    "        notify_on_complete = True\n"
    "    elif isinstance(args.get('notify'), list):\n"
    "        watch_patterns = args['notify']\n"
    "    if heartbeat:\n"
    "        notify_on_complete = True\n"
    "    return terminal_tool(\n"
    "        command=args.get('command'),\n"
    "        background=args.get('background', False),\n"
    "        notify_on_complete=notify_on_complete,\n"
    "        watch_patterns=watch_patterns,\n"
    "        heartbeat=heartbeat,\n"
    "        persist_on_release=persist_on_release,\n"
    "    )\n"
)


def run_patch(src):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "t.py")
    open(p, "w").write(src)
    r = os.system(f"{sys.executable} {PATCH} {p} >/dev/null 2>&1")
    return r, open(p).read()


rc, patched = run_patch(HANDLER)
check("the patch applies to the handler", rc == 0 and pbj.MARK in patched)
rc2 = os.system(f"{sys.executable} {PATCH} {os.path.join(tempfile.gettempdir(), 'nonexistent-x')} >/dev/null 2>&1")
check("a missing file is an error, not a silent pass", rc2 != 0)
d = tempfile.mkdtemp()
p = os.path.join(d, "t.py")
open(p, "w").write(patched)
os.system(f"{sys.executable} {PATCH} {p} >/dev/null 2>&1")
check("re-running changes nothing", open(p).read() == patched)
rc3, _ = run_patch(HANDLER.replace("persist_on_release=persist_on_release,", "persist_on_release=persist_on_release, extra=1,"))
check("a Hermes change that moves the anchor aborts the build", rc3 != 0)
rc4, _ = run_patch(HANDLER + HANDLER)
check("a duplicated anchor aborts the build (exactly one match)", rc4 != 0)

ns = {}
exec(compile(patched, "patched_handler", "exec"), ns)


def persists(args):
    ns["CALLS"].clear()
    ns["handler"](args)
    return ns["CALLS"][-1]["persist_on_release"]


check("notify_on_complete background job persists (the downloads case)", persists({"command": "yt-dlp x", "background": True, "notify_on_complete": True}) is True)
check("notify=true background job persists", persists({"command": "make", "background": True, "notify": True}) is True)
check("a watch-pattern background job (a watcher that never exits) does NOT persist", persists({"command": "tail -f x", "background": True, "notify": ["ERROR"]}) is False)
check("a heartbeat background job persists", persists({"command": "ffmpeg x", "background": True, "heartbeat": 120}) is True)
check("a SILENT background job (a server) does not persist", persists({"command": "python3 -m http.server", "background": True}) is False)
check("a foreground command does not persist", persists({"command": "ls", "notify_on_complete": True}) is False)
check("an explicit true is kept", persists({"command": "x", "background": True, "persist_on_release": True}) is True)
check("an explicit false does not switch the default off (providers send false for every property)",
      persists({"command": "x", "background": True, "notify_on_complete": True, "persist_on_release": False}) is True)

# against the real file when HERMES_TERMINAL_TOOL points at a copy of it (the image build is the real check)
real = os.environ.get("HERMES_TERMINAL_TOOL")
if real and os.path.isfile(real):
    rc5, out = run_patch(open(real).read())
    check("the patch applies to the real terminal_tool.py", rc5 == 0 and pbj.MARK in out)
    try:
        compile(out, "terminal_tool.py", "exec")
        check("the patched real file compiles", True)
    except SyntaxError as e:
        check(f"the patched real file compiles ({e})", False)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all persist_background_jobs checks passed")
