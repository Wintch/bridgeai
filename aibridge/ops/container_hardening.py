#!/usr/bin/env python3
"""Read-only: report what hardening a running Hermes container REALLY has, and whether it matches the profile in
guests/docker-compose.guest.yml (run on the Docker host; reads `docker inspect` and /proc/1/status inside the container):

  ops/container_hardening.py <container> [<container> ...]       e.g. guest-prueba stack-<name>-hermes
  exit 0 = every container matches the profile, 1 = at least one differs or is not running, 2 = usage

Why: the compose file says what we ASKED for; /proc/1/status says what the process got (a typo in a key, or a compose
version that ignores `deploy.resources.limits.pids`, leaves the YAML looking hardened and the container not).
The profile: no-new-privileges, a pids limit of at most 1024, and exactly these capabilities: CHOWN DAC_OVERRIDE FOWNER
KILL SETGID SETUID NET_RAW. Test: python3 ops/container_hardening_selftest.py
"""
import json
import subprocess
import sys

# Linux capability numbers (include/uapi/linux/capability.h) for the ones this stack knows about.
CAPS = {"CHOWN": 0, "DAC_OVERRIDE": 1, "DAC_READ_SEARCH": 2, "FOWNER": 3, "FSETID": 4, "KILL": 5, "SETGID": 6, "SETUID": 7,
        "SETPCAP": 8, "LINUX_IMMUTABLE": 9, "NET_BIND_SERVICE": 10, "NET_BROADCAST": 11, "NET_ADMIN": 12, "NET_RAW": 13,
        "IPC_LOCK": 14, "IPC_OWNER": 15, "SYS_MODULE": 16, "SYS_RAWIO": 17, "SYS_CHROOT": 18, "SYS_PTRACE": 19,
        "SYS_PACCT": 20, "SYS_ADMIN": 21, "SYS_BOOT": 22, "SYS_NICE": 23, "SYS_RESOURCE": 24, "SYS_TIME": 25,
        "SYS_TTY_CONFIG": 26, "MKNOD": 27, "LEASE": 28, "AUDIT_WRITE": 29, "AUDIT_CONTROL": 30, "SETFCAP": 31,
        "MAC_OVERRIDE": 32, "MAC_ADMIN": 33, "SYSLOG": 34, "WAKE_ALARM": 35, "BLOCK_SUSPEND": 36, "AUDIT_READ": 37,
        "PERFMON": 38, "BPF": 39, "CHECKPOINT_RESTORE": 40}
WANT_CAPS = {"CHOWN", "DAC_OVERRIDE", "FOWNER", "KILL", "SETGID", "SETUID", "NET_RAW"}
MAX_PIDS = 1024


def decode_caps(mask_hex):
    """'00000000a80425fb' -> {'CHOWN', ...}; unknown bits show as CAP_<n>."""
    mask = int(mask_hex, 16)
    by_num = {n: name for name, n in CAPS.items()}
    return {by_num.get(n, f"CAP_{n}") for n in range(64) if mask >> n & 1}


def status_field(status_text, key):
    for line in status_text.splitlines():
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip()
    return ""


def judge(inspect, status_text):
    """Compare one container's facts to the profile. Returns (list of problems, dict of what was seen)."""
    host = inspect.get("HostConfig") or {}
    sec = host.get("SecurityOpt") or []
    pids = host.get("PidsLimit")
    eff = decode_caps(status_field(status_text, "CapEff") or "0")
    nnp = status_field(status_text, "NoNewPrivs")
    seen = {"no_new_privileges": nnp == "1", "pids_limit": pids, "caps": sorted(eff)}
    problems = []
    if nnp != "1":
        problems.append("no-new-privileges is NOT in effect (NoNewPrivs=%s)" % (nnp or "?"))
    if not pids or pids < 0 or pids > MAX_PIDS:
        problems.append(f"pids limit is {pids!r}, want 1..{MAX_PIDS}")
    extra, missing = sorted(eff - WANT_CAPS), sorted(WANT_CAPS - eff)
    if extra:
        problems.append("extra capabilities: " + ", ".join(extra))
    if missing:
        problems.append("missing capabilities (something may break): " + ", ".join(missing))
    if host.get("Privileged"):
        problems.append("container is PRIVILEGED")
    if "seccomp=unconfined" in sec or "apparmor=unconfined" in sec:
        problems.append("seccomp/AppArmor confinement is switched off")
    return problems, seen


def docker(*args):
    r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout, r.stderr


def check(name):
    rc, out, err = docker("inspect", name)
    if rc != 0:
        return [f"no such container ({err.strip()[:80]})"], {}
    info = json.loads(out)[0]
    if not info["State"]["Running"]:
        return ["not running (asleep?): start it and run this again"], {}
    rc, status, err = docker("exec", name, "cat", "/proc/1/status")
    if rc != 0:
        return [f"could not read /proc/1/status ({err.strip()[:80]})"], {}
    return judge(info, status)


def main(argv):
    if not argv or any(a.startswith("-") for a in argv):
        print(__doc__, file=sys.stderr)
        return 2
    bad = 0
    for name in argv:
        problems, seen = check(name)
        print(f"{name}: " + ("OK, matches the profile" if not problems else "DIFFERS"))
        if seen:
            print(f"  no-new-privileges={seen['no_new_privileges']} pids_limit={seen['pids_limit']} caps={','.join(seen['caps'])}")
        for p in problems:
            print("  - " + p)
        bad += bool(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
