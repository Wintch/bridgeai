#!/usr/bin/env python3
"""Patch Hermes so a parked MCP server is probed again every 5 minutes at most, as on v0.21.6, instead of backing off up to an hour.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: mcp_parked_probe_cap.py <path to tools/mcp_tool.py>

Why: an MCP server that fails its first connection is parked (its tools are taken away) and probes itself on a timer; nothing else
revives it. v0.23 doubles that wait after every failed probe, up to _PARKED_PROBE_BACKOFF_MAX (3600 s), meant for a server whose failure
is permanent. Ours are not: the media MCP servers (DaVinci Resolve, EffectCraft) run on a GPU host over ssh, and that host sleeps
whenever it is idle. A stack that boots while it sleeps parks them, the probes keep failing while it sleeps, and after the host wakes
for the person the tools could stay missing for up to an hour. The cap comes from AIBRIDGE_MCP_PARKED_PROBE_MAX_S (default 300, the
first interval, so no backoff); a value that is not a number or below 60 falls back to the default. A probe of a sleeping host is one
ssh attempt with ConnectTimeout=3, and it never wakes the host.

The replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
The new text is compiled before the file is written, and the write goes through a temp file in the same folder (never a half-written
target). Re-running on an already-patched file is a no-op.
"""
import os
import re
import sys
import tempfile

MARK = "# aibridge-patch: mcp_parked_probe_cap"

OLD = "_PARKED_PROBE_BACKOFF_MAX = 3600\n"

NEW = MARK + '''
def _aibridge_parked_probe_max():
    try:
        s = float(os.environ.get("AIBRIDGE_MCP_PARKED_PROBE_MAX_S", "300"))
    except ValueError:
        s = 300.0
    return s if s >= 60 else 300.0


_PARKED_PROBE_BACKOFF_MAX = _aibridge_parked_probe_max()
'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    n = src.count(OLD)
    if n != 1:
        sys.exit(f"patch failed: _PARKED_PROBE_BACKOFF_MAX line: expected 1 match, found {n}")
    if not re.search(r"^import (?:[\w.]+, *)*os\b", src, re.M):
        sys.exit("patch failed: tools/mcp_tool.py no longer imports os at module level")
    new = src.replace(OLD, NEW, 1)
    compile(new, path, "exec")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".mcp_tool.", suffix=".tmp")
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
