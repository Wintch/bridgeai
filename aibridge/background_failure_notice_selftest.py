#!/usr/bin/env python3
"""Selftest for patches/background_failure_notice.py: the patch applies once and aborts when Hermes changes, and the
method it adds raises ONE alarm for a failing background job and none for normal
output. Run: python3 background_failure_notice_selftest.py (offline, no Hermes needed)."""
import importlib.util
import os
import queue
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bfn", os.path.join(HERE, "patches", "background_failure_notice.py"))
bfn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bfn)

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


# --- 1. the text patch ------------------------------------------------------------------------------------------
REG = (
    "class ProcessRegistry:\n"
    "    def _check_watch_patterns(self, session: ProcessSession, new_text: str) -> None:\n"
    '        """doc"""\n'
    "        if not session.watch_patterns or session._watch_disabled:\n"
    "            return\n"
    "        # Late chunks after the reader declared exit, nothing more\n"
    "        return\n"
    "\n"
    "    def _emit_watch_disabled(self, session: ProcessSession, suppressed: int, why: str) -> None:\n"
    "        pass\n"
)
BG = (
    "def _apply_async_support(proc_session, result_data, notify_on_complete, watch_patterns):\n"
    "    if not (notify_on_complete or watch_patterns):\n"
    "        return notify_on_complete, watch_patterns\n"
    "    from gateway.session_context import async_delivery_supported, get_session_env\n"
    "    return notify_on_complete, watch_patterns\n"
)


def run_patch(reg, bg):
    d = tempfile.mkdtemp()
    a, b = os.path.join(d, "r.py"), os.path.join(d, "b.py")
    open(a, "w").write(reg)
    open(b, "w").write(bg)
    try:
        bfn.main(a, b)
        return open(a).read(), open(b).read(), None
    except SystemExit as e:
        return None, None, str(e)


r1, b1, err = run_patch(REG, BG)
check("applies to both files", err is None and bfn.MARK in r1 and bfn.MARK in b1)
check("registry: the call sits before the watch-pattern gate",
      r1 is not None and r1.index("_aibridge_failure_notice(session, new_text)") < r1.index("if not session.watch_patterns"))
check("registry: both files compile", r1 is not None and compile(r1, "r", "exec") and compile(b1, "b", "exec"))
r2, b2, err2 = run_patch(r1 or "", b1 or "")
check("re-running is a no-op", err2 is None and r2 == r1 and b2 == b1)
_, _, err3 = run_patch(REG.replace("if not session.watch_patterns", "if not session.watch_x"), BG)
check("aborts when the registry anchor moved", err3 is not None and "expected 1 match" in err3)
_, _, err4 = run_patch(REG, BG.replace("        return notify_on_complete, watch_patterns\n    from", "        return None\n    from"))
check("aborts when the routing anchor moved", err4 is not None and "expected 1 match" in err4)
_, _, err5 = run_patch(r1, BG)
check("aborts when only one file carries the patch", err5 is not None and "only one" in err5)

# --- 2. the method it adds --------------------------------------------------------------------------------------
ns = {"ProcessSession": object, "_redact_process_result": lambda n: None}
exec("class Reg:\n    def __init__(self):\n        self.completion_queue = queue.Queue()\n"
     "    def _watch_event_base(self, s):\n        return {'session_id': s.id, 'command': s.command}\n" + bfn.METHOD, {**ns, "queue": queue}, ns)
Reg = ns["Reg"]


def session(platform="telegram", exited=False):
    return types.SimpleNamespace(id="proc_1", command="yt-dlp CHANNEL", exited=exited, watcher_platform=platform)


def feed(reg, s, text):
    reg._aibridge_failure_notice(s, text)
    out = []
    while not reg.completion_queue.empty():
        out.append(reg.completion_queue.get())
    return out


RL = ("ERROR: [youtube] hhWVJJQD8sI: Video unavailable. This content isn't available, try again later. The current "
      "session has been rate-limited by YouTube for up to an hour.\n")
reg, s = Reg(), session()
check("rate limit: 2 lines raise nothing yet", feed(reg, s, RL * 2) == [])
ev = feed(reg, s, RL)
check("rate limit: the 3rd line raises exactly one watch_match", len(ev) == 1 and ev[0]["type"] == "watch_match")
check("alarm says it fails, to tell the person and to let them decide",
      ev and "FAILING" in ev[0]["pattern"] and "Tell the person NOW" in ev[0]["output"] and "let the person decide" in ev[0]["output"])
check("alarm carries a sample and the job identity", ev and "rate-limited by YouTube" in ev[0]["output"] and ev[0]["session_id"] == "proc_1")
check("one alarm per job: more failures raise nothing", feed(reg, s, RL * 50) == [])

reg, s = Reg(), session()
check("error flood: 24 ERROR lines raise nothing", feed(reg, s, "ERROR: video 1 broke\n" * 24) == [])
ev = feed(reg, s, "ERROR: video 25 broke\n")
check("error flood: the 25th raises one alarm", len(ev) == 1 and "25 lines" in ev[0]["output"])

reg, s = Reg(), session()
check("counts accumulate across chunks", [len(feed(reg, s, RL)) for _ in range(3)] == [0, 0, 1])
check("age-restricted videos alone are not an alarm (per video, not a block)",
      feed(Reg(), session(), "ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate\n" * 10) == [])
check("normal progress output raises nothing",
      feed(Reg(), session(), "[download] 12.3% of 50.00MiB at 2.1MiB/s ETA 00:20\n" * 200 + "Finished 3 of 3\n") == [])
check("a job with no chat route raises nothing (nowhere to send it)", feed(Reg(), session(platform=""), RL * 5) == [])
check("an exited job raises nothing", feed(Reg(), session(exited=True), RL * 5) == [])
check("'not a bot' and 'no space left' count", len(feed(Reg(), session(), "Sign in to confirm you're not a bot\n" * 3)) == 1
      and len(feed(Reg(), session(), "write failed: No space left on device\n" * 3)) == 1)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all background_failure_notice checks passed")
