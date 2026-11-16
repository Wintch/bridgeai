#!/usr/bin/env python3
"""Patch Hermes so a restarted container takes over the turn lease its dead predecessor left, at once, not after the TTL.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: lease_stale_after_restart.py <hermes_state_pidns.py> <hermes_state.py>

Why: a turn killed mid-flight (docker kill, OOM, host power loss) leaves its row in `session_turn_leases` (and a mid-compression
kill one in `compression_locks`) with a 300 s TTL. The next request on that session, the one the person sends or the replay
that admission_auto_resume.py queues, finds the row and polls "Still waiting for the other Hermes process" until the TTL runs
out: measured in staging with `docker kill` + `docker start` on v0.23.1, 2 runs of 5 waited 279 s and 281 s for a first request
that takes 1 s once the row is gone. v0.21.6 has the same code and the same stall (production images).
`_compression_lock_holder_process_is_dead(holder)` is the only way a dead holder is reclaimed before its TTL, and in a restarted
container it cannot work, for two reasons found in the runs:
1. The holder is stamped `pidns=<inode of /proc/self/ns/pid>` and `holder_pid_checkable` never probes a holder of another
   PID namespace. `docker start` of the same container builds a NEW PID namespace; its inode is sometimes recycled (then the
   probe runs and, the old PID being gone, reclaims at once) and sometimes not (then the dead predecessor reads as a "foreign
   namespace" and defers to the TTL). Which one happens depends on what else created or freed namespaces on the host in
   between: a lottery that production's eight busy stacks lose more often than an idle staging host.
2. When the namespace does match, the probe is about a PID, and a restarted container starts the same process tree: the
   gateway gets the same PID again after the second restart in a row (pid 100 in every boot after the first one in these
   runs), `pid == os.getpid()` reads as "our own live lease" and the row is kept for the TTL. Any other process that happens
   to be alive under the recorded PID keeps it too.
So "which boot of the container wrote this holder" has to be part of the holder, and the guard has to keep working when it is
not known.

What it does (two files, two anchors, one appended block):
1. `hermes_state_pidns.py` gets `container_boot_token()` and `holder_from_previous_boot(holder)`. Every new holder
   (`holder_namespace_token()` is what upstream appends after `pid=<n>`; turn leases and compression locks both use it) carries
   `:cboot=<hostname hash>.<boot id hash>.<start ticks of this container's PID 1>`: a hash of the container's hostname (stable
   across `docker restart`/`start`, different for any other container), a hash of the kernel's boot id, and the start time of
   PID 1 in clock ticks since the host booted (new at every container start, readable in the container, the same for every
   process in it). Nothing outside Linux's /proc is needed; where /proc/1/stat or the boot id cannot be read no token is
   written and the stock rules apply unchanged.
2. `_compression_lock_holder_process_is_dead` asks `holder_from_previous_boot` first. A holder is the dead predecessor's only
   when it carries a token and
   - its hostname hash is ours (the same container, not a sibling that shares the volume: a sibling keeps being judged by
     upstream's namespace rule, which never probes a foreign namespace), and
   - it was written by an earlier life of that container: another kernel boot id (the host rebooted), or the same boot with
     a PID 1 that started BEFORE ours. A holder that started after us is never reclaimed by this rule (a process in a nested
     sandbox that remounts /proc gets its own, later PID 1, and keeps upstream's treatment).
   A holder of this boot (the live gateway, `hermes` CLI run by `docker exec`) never matches, so two live processes keep the
   guard exactly as upstream wrote it. The same PID with an older token (the second-restart case) is reclaimed too: the
   token is checked before the "same process" rule.
   Holders written before the image carried this patch have no token and keep the stock rule (a one-time TTL wait, once, for a
   lease left by the last unpatched container).
Not covered: a container recreated rather than restarted (docker compose up with a new image) gets a new hostname, so a lease
left by a kill during that recreation still waits its TTL; the graceful stop releases the row, so only a kill in that window
leaves one. Setting `hostname:` per stack in compose would close it.

Write-safe: both new texts are computed before either file is written, and each write goes through a temp file in the same
directory + os.replace. Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes
this code fails the build loudly. Re-running on already-patched files is a no-op.
"""
import os
import sys

MARK = "# aibridge-patch: lease_stale_after_restart"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


# Appended to hermes_state_pidns.py. Not an f-string: @@MARK@@ is substituted below. Only stdlib; hashlib / socket are
# imported where used so the module's import list (and every importer) stays as upstream wrote it.
HELPERS = '''

@@MARK@@: which boot of the container wrote a lease holder (see patches/lease_stale_after_restart.py in aibridge)
# ``cboot=<hostname hash>.<boot id hash>.<start ticks of PID 1>`` inside a structured holder string.
_CBOOT_TOKEN_RE = re.compile(r"(?:^|:)cboot=([0-9a-f]{8})\\.([0-9a-f]{8})\\.(\\d+)(?::|$)")
_UNREAD = object()
_LOCAL_CONTAINER_BOOT = _UNREAD  # (host hash, boot id hash, ticks) or None once read; the answer never changes for a process
_PREVIOUS_BOOT_SEEN: set = set()


def _read_container_boot():
    """This container's boot identity ``(host8, boot8, ticks)``, or None when /proc cannot give it."""
    if sys.platform != "linux":
        return None
    try:
        with open("/proc/1/stat", "rb") as fh:
            raw = fh.read().decode("ascii", "replace")
        # ``pid (comm) state ...``: comm may hold spaces/parens, so split after the LAST ``)``; starttime is field 22.
        ticks = int(raw.rsplit(")", 1)[1].split()[19])
        with open("/proc/sys/kernel/random/boot_id", "r", encoding="ascii") as fh:
            boot_id = fh.read().strip()
        import socket
        host = socket.gethostname()
    except (OSError, ValueError, IndexError):
        return None
    if ticks <= 0 or not boot_id or not host:
        return None
    import hashlib
    return (hashlib.sha1(host.encode("utf-8", "replace")).hexdigest()[:8],
            hashlib.sha1(boot_id.encode("ascii", "replace")).hexdigest()[:8], ticks)


def _local_container_boot():
    global _LOCAL_CONTAINER_BOOT
    if _LOCAL_CONTAINER_BOOT is _UNREAD:
        _LOCAL_CONTAINER_BOOT = _read_container_boot()
    return _LOCAL_CONTAINER_BOOT


def container_boot_token() -> str:
    """The ``:cboot=...`` fragment to append to a new holder string, or ``""`` when the boot identity is unknown."""
    local = _local_container_boot()
    return f":cboot={local[0]}.{local[1]}.{local[2]}" if local else ""


def holder_from_previous_boot(holder: str) -> bool:
    """True only for a holder stamped by an EARLIER life of THIS container: its process cannot be alive.

    Same hostname hash and either another kernel boot id (the host rebooted) or the same boot with a PID 1 that started
    before ours. No token on either side, another container's hostname, or a later PID 1: False, so upstream's rules decide."""
    local = _local_container_boot()
    match = _CBOOT_TOKEN_RE.search(holder or "")
    if local is None or match is None or match.group(1) != local[0]:
        return False
    older = match.group(2) != local[1] or int(match.group(3)) < local[2]
    if older and holder not in _PREVIOUS_BOOT_SEEN and len(_PREVIOUS_BOOT_SEEN) < 256:
        _PREVIOUS_BOOT_SEEN.add(holder)
        import logging
        logging.getLogger(__name__).info(
            "Lease holder %s was written before this container (re)started: reclaiming it now, not at its TTL", holder)
    return older
'''.replace("@@MARK@@", MARK)


def patch_pidns(path: str):
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        return None
    src = replace_once(
        src,
        '    ns = pid_namespace_id()\n    return f":pidns={ns}" if ns else ""\n',
        '    ns = pid_namespace_id()\n'
        f'    return (f":pidns={{ns}}" if ns else "") + container_boot_token()  {MARK}: stamp which boot wrote the holder\n',
        "hermes_state_pidns.holder_namespace_token",
    )
    return src.rstrip("\n") + "\n" + HELPERS


def patch_state(path: str):
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        return None
    return replace_once(
        src,
        '    match = re.search(r"(?:^|:)pid=(\\d+)(?::|$)", holder or "")\n    pid = int(match.group(1)) if match else 0\n',
        f'    from hermes_state_pidns import holder_from_previous_boot  {MARK}\n'
        '    if holder_from_previous_boot(holder):  # written by an earlier life of this container: dead, whatever its PID says\n'
        '        return True\n'
        '    match = re.search(r"(?:^|:)pid=(\\d+)(?::|$)", holder or "")\n    pid = int(match.group(1)) if match else 0\n',
        "hermes_state._compression_lock_holder_process_is_dead",
    )


def write_atomic(path: str, text: str) -> None:
    """Write via a temp file in the same directory + os.replace, so a crash never leaves a half-written target."""
    tmp = f"{path}.aibridge-tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(pidns_path: str, state_path: str) -> None:
    # Both new texts are computed before either file is written: a mismatch in one leaves both untouched.
    jobs = ((pidns_path, patch_pidns(pidns_path)), (state_path, patch_state(state_path)))
    for path, text in jobs:
        if text is not None:
            write_atomic(path, text)
            print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
