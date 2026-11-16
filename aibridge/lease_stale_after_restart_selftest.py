#!/usr/bin/env python3
"""Self-test for patches/lease_stale_after_restart.py on stand-ins of the two Hermes files it patches (each anchor verbatim, the
rest of upstream's PID-namespace rules reduced to what they decide). The real files are checked at image build time (the patch
aborts unless each anchor matches once) and against the v0.23.1 archive in staging. With HERMES_SRC pointing at an extracted
Hermes tree the patch is also run on copies of its real hermes_state_pidns.py / hermes_state.py.
Run: python3 -I lease_stale_after_restart_selftest.py
"""
import importlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.path.join(HERE, "patches", "lease_stale_after_restart.py")
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


PIDNS = '''"""stand-in"""
from __future__ import annotations

import os
import re
import sys
from typing import NamedTuple, Optional

_PIDNS_TOKEN_RE = re.compile(r"(?:^|:)pidns=(\\d+)(?::|$)")

LOCAL_NS = "4026500001"   # the selftest's "this container's PID namespace inode"


def pid_namespace_id() -> Optional[str]:
    return LOCAL_NS


def holder_namespace_token() -> str:
    """The ``:pidns=<id>`` fragment to append to a new holder string, or ``""``."""
    ns = pid_namespace_id()
    return f":pidns={ns}" if ns else ""


def _recorded_namespace(holder: str) -> Optional[str]:
    match = _PIDNS_TOKEN_RE.search(holder or "")
    return match.group(1) if match else None


def holder_pid_checkable(holder: str) -> bool:
    recorded = _recorded_namespace(holder)
    return recorded is not None and recorded == LOCAL_NS
'''

STATE = '''"""stand-in"""
import os
import re

from hermes_state_pidns import holder_pid_checkable

ALIVE_PIDS = set()   # the selftest decides which PIDs "exist" in this container
psutil = None


def _compression_lock_holder_process_is_dead(holder: str) -> bool:
    """True only when a ``pid=<n>`` lock holder's local PID is provably gone."""
    match = re.search(r"(?:^|:)pid=(\\d+)(?::|$)", holder or "")
    pid = int(match.group(1)) if match else 0
    if pid <= 0 or pid == os.getpid():
        return False
    if not holder_pid_checkable(holder):
        return False  # foreign / unknown namespace: defer to TTL
    return pid not in ALIVE_PIDS
'''


def run_patch(pidns, state):
    return subprocess.run([sys.executable, "-I", PATCH, pidns, state], capture_output=True, text=True)


def load(directory):
    for name in ("hermes_state_pidns", "hermes_state"):
        sys.modules.pop(name, None)
    sys.path.insert(0, directory)
    try:
        return importlib.import_module("hermes_state_pidns"), importlib.import_module("hermes_state")
    finally:
        sys.path.remove(directory)


def holder(pidns_mod, pid, boot, ns="4026500001", tail=":turn=t1:platform=api_server"):
    """A holder as the patched upstream builds it, but for an arbitrary PID / boot identity."""
    token = f":cboot={boot[0]}.{boot[1]}.{boot[2]}" if boot else ""
    return f"pid={pid}:pidns={ns}{token}{tail}"


with tempfile.TemporaryDirectory() as tmp:
    d = os.path.join(tmp, "ok")
    os.makedirs(d)
    pidns_path, state_path = os.path.join(d, "hermes_state_pidns.py"), os.path.join(d, "hermes_state.py")
    open(pidns_path, "w").write(PIDNS)
    open(state_path, "w").write(STATE)

    # 1. apply, idempotent, compiles
    r = run_patch(pidns_path, state_path)
    check("patch applies", r.returncode == 0 and r.stdout.count("patched:") == 2, r.stdout + r.stderr)
    first = (open(pidns_path).read(), open(state_path).read())
    r = run_patch(pidns_path, state_path)
    check("second run is a no-op", r.returncode == 0 and "patched:" not in r.stdout
          and (open(pidns_path).read(), open(state_path).read()) == first, r.stdout + r.stderr)
    check("patched files compile", subprocess.run([sys.executable, "-m", "py_compile", pidns_path, state_path]).returncode == 0)
    check("no temp file left", not [f for f in os.listdir(d) if f.endswith(".aibridge-tmp")], os.listdir(d))

    # 2. an anchor that does not match once aborts and leaves BOTH files untouched
    for label, mutate in (("missing", lambda s: s.replace("    pid = int(match.group(1)) if match else 0\n", "")),
                          ("doubled", lambda s: s + "\n" + s[s.index("def _compression"):])):
        d2 = os.path.join(tmp, "bad-" + label)
        os.makedirs(d2)
        p2, s2 = os.path.join(d2, "hermes_state_pidns.py"), os.path.join(d2, "hermes_state.py")
        open(p2, "w").write(PIDNS)
        open(s2, "w").write(mutate(STATE))
        before = (open(p2).read(), open(s2).read())
        r = run_patch(p2, s2)
        check(f"{label} anchor aborts", r.returncode != 0 and "patch failed" in (r.stderr + r.stdout), r.stdout + r.stderr)
        check(f"{label} anchor leaves both files untouched", (open(p2).read(), open(s2).read()) == before)
    d3 = os.path.join(tmp, "bad-pidns")
    os.makedirs(d3)
    p3, s3 = os.path.join(d3, "hermes_state_pidns.py"), os.path.join(d3, "hermes_state.py")
    open(p3, "w").write(PIDNS.replace('    return f":pidns={ns}" if ns else ""\n', ""))
    open(s3, "w").write(STATE)
    r = run_patch(p3, s3)
    check("pidns anchor missing aborts, state untouched", r.returncode != 0 and open(s3).read() == STATE, r.stdout + r.stderr)

    # 3. behaviour
    pidns, state = load(d)
    me = os.getpid()
    HOST, BOOT, TICKS = "aaaaaaaa", "bbbbbbbb", 5_000_000
    pidns._LOCAL_CONTAINER_BOOT = (HOST, BOOT, TICKS)   # this process "is" the container started at tick 5,000,000

    tok = pidns.holder_namespace_token()
    check("holder carries the pidns stamp and the boot token", tok == f":pidns=4026500001:cboot={HOST}.{BOOT}.{TICKS}", tok)
    check("a holder built with the token still parses as upstream parses it",
          pidns._recorded_namespace(f"pid=7{tok}:turn=x") == "4026500001"
          and __import__("re").search(r"(?:^|:)pid=(\d+)(?::|$)", f"pid=7{tok}:turn=x").group(1) == "7")

    state.ALIVE_PIDS = {me, 100}
    # the stall: previous life, namespace inode NOT recycled (foreign stamp), PID gone -> stock waits the TTL
    h = holder(pidns, 111, (HOST, BOOT, TICKS - 1000), ns="4026599999")
    check("previous life, other namespace inode: reclaimed at once", state._compression_lock_holder_process_is_dead(h) is True)
    # the same, namespace recycled and the PID gone -> reclaimed (stock did this too)
    h = holder(pidns, 111, (HOST, BOOT, TICKS - 1000))
    check("previous life, same namespace inode, PID gone: reclaimed", state._compression_lock_holder_process_is_dead(h) is True)
    # the second-restart stall: same PID as this process (the gateway gets the same PID every boot)
    h = holder(pidns, me, (HOST, BOOT, TICKS - 1000))
    check("previous life with THIS process's PID (recycled): reclaimed", state._compression_lock_holder_process_is_dead(h) is True)
    # an unrelated live process under the recorded PID
    h = holder(pidns, 100, (HOST, BOOT, TICKS - 1000))
    check("previous life, the PID is alive again as another process: reclaimed", state._compression_lock_holder_process_is_dead(h) is True)
    # the host rebooted
    h = holder(pidns, 111, (HOST, "cccccccc", 10))
    check("same container name, other boot id: reclaimed", state._compression_lock_holder_process_is_dead(h) is True)

    # the guard stays
    h = holder(pidns, me, (HOST, BOOT, TICKS))
    check("this container's own live lease (same process): kept", state._compression_lock_holder_process_is_dead(h) is False)
    h = holder(pidns, 100, (HOST, BOOT, TICKS))
    check("same boot, another live process (docker exec hermes ...): kept", state._compression_lock_holder_process_is_dead(h) is False)
    h = holder(pidns, 999, (HOST, BOOT, TICKS))
    check("same boot, PID not in this namespace view: upstream's rule decides (dead PID, same stamp: reclaimed)",
          state._compression_lock_holder_process_is_dead(h) is True)
    h = holder(pidns, 999, (HOST, BOOT, TICKS), ns="4026599999")
    check("same boot, foreign namespace stamp: upstream defers to TTL (kept)", state._compression_lock_holder_process_is_dead(h) is False)
    h = holder(pidns, 111, ("dddddddd", BOOT, TICKS - 1000), ns="4026599999")
    check("another container's hostname (sibling on the same volume), older ticks: kept", state._compression_lock_holder_process_is_dead(h) is False)
    h = holder(pidns, 111, ("dddddddd", "cccccccc", 1), ns="4026599999")
    check("another container's hostname and boot id: kept", state._compression_lock_holder_process_is_dead(h) is False)
    h = holder(pidns, 111, (HOST, BOOT, TICKS + 500), ns="4026599999")
    check("same hostname but a LATER PID 1 (nested sandbox): kept", state._compression_lock_holder_process_is_dead(h) is False)
    h = holder(pidns, 111, None, ns="4026599999")
    check("holder with no token (written before the patch): upstream's rule (foreign stamp, kept)",
          state._compression_lock_holder_process_is_dead(h) is False)
    h = holder(pidns, 111, None)
    check("holder with no token, same namespace, PID gone: upstream's rule (reclaimed)",
          state._compression_lock_holder_process_is_dead(h) is True)
    check("unstructured holder: kept", state._compression_lock_holder_process_is_dead("fixture-client-turn") is False)
    check("empty holder: kept", state._compression_lock_holder_process_is_dead("") is False)
    check("garbled token: kept", state._compression_lock_holder_process_is_dead("pid=111:pidns=4026599999:cboot=zz.yy.1:turn=x") is False)

    # no boot identity here (no /proc, no boot id): nothing is stamped and the guard is upstream's
    pidns._LOCAL_CONTAINER_BOOT = None
    check("no local identity: no token written", pidns.holder_namespace_token() == ":pidns=4026500001")
    h = holder(pidns, 111, (HOST, BOOT, TICKS - 1000), ns="4026599999")
    check("no local identity: a stamped holder is judged by upstream's rule only (kept)",
          state._compression_lock_holder_process_is_dead(h) is False)

    # the real /proc reader (Linux only), including the cache
    pidns._LOCAL_CONTAINER_BOOT = pidns._UNREAD
    if sys.platform == "linux" and os.path.exists("/proc/1/stat"):
        got = pidns._read_container_boot()
        check("real /proc: identity read", isinstance(got, tuple) and len(got) == 3 and got[2] > 0, got)
        t = pidns.container_boot_token()
        check("real /proc: token round-trips through the holder regex",
              bool(t) and pidns._CBOOT_TOKEN_RE.search(f"pid=1:pidns=2{t}:turn=x") is not None, t)
        check("real /proc: this process's own holder is never from a previous boot",
              pidns.holder_from_previous_boot(f"pid={me}{pidns.holder_namespace_token()}:turn=x") is False)
        check("identity is cached", pidns._local_container_boot() is pidns._local_container_boot())

    # the real files, when an extracted tree is at hand
    src = os.environ.get("HERMES_SRC")
    if src and os.path.exists(os.path.join(src, "hermes_state_pidns.py")):
        d4 = os.path.join(tmp, "real")
        os.makedirs(d4)
        for f in ("hermes_state_pidns.py", "hermes_state.py"):
            shutil.copy(os.path.join(src, f), os.path.join(d4, f))
        r = run_patch(os.path.join(d4, "hermes_state_pidns.py"), os.path.join(d4, "hermes_state.py"))
        check("real files: patch applies", r.returncode == 0 and r.stdout.count("patched:") == 2, r.stdout + r.stderr)
        r = run_patch(os.path.join(d4, "hermes_state_pidns.py"), os.path.join(d4, "hermes_state.py"))
        check("real files: second run is a no-op", r.returncode == 0 and "patched:" not in r.stdout, r.stdout + r.stderr)
        check("real files: compile", subprocess.run([sys.executable, "-m", "py_compile", os.path.join(d4, "hermes_state_pidns.py"),
                                                     os.path.join(d4, "hermes_state.py")]).returncode == 0)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all passed")
