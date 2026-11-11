#!/usr/bin/env python3
"""Selftest for ops/container_hardening.py (offline: no Docker needed). Run: python3 ops/container_hardening_selftest.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import container_hardening as ch  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


# Docker's default set, measured on hernik's container (CapEff a80425fb): 14 capabilities.
default = ch.decode_caps("00000000a80425fb")
check("decodes Docker's default 14 capabilities", default == {"CHOWN", "DAC_OVERRIDE", "FSETID", "FOWNER", "MKNOD", "NET_RAW", "SETGID",
                                                              "SETUID", "SETFCAP", "SETPCAP", "NET_BIND_SERVICE", "SYS_CHROOT", "KILL", "AUDIT_WRITE"})
mask = sum(1 << ch.CAPS[c] for c in ch.WANT_CAPS)
check("the profile's mask is 0x20eb", mask == 0x20EB)
check("round trip of the profile", ch.decode_caps(format(mask, "016x")) == ch.WANT_CAPS)
check("an unknown bit is shown, not hidden", "CAP_50" in ch.decode_caps(format(1 << 50, "016x")))


def status(eff, nnp):
    return f"Name:\tbash\nNoNewPrivs:\t{nnp}\nCapEff:\t{eff}\n"


good_inspect = {"HostConfig": {"PidsLimit": 1024, "SecurityOpt": ["no-new-privileges:true"], "Privileged": False}}
problems, _ = ch.judge(good_inspect, status(format(mask, "016x"), 1))
check("a container with the profile passes", problems == [])

problems, _ = ch.judge({"HostConfig": {"PidsLimit": None, "SecurityOpt": None}}, status("00000000a80425fb", 0))
text = " | ".join(problems)
check("the unhardened default is flagged on every count",
      "NoNewPrivs=0" in text and "pids limit is None" in text and "extra capabilities: AUDIT_WRITE" in text)

problems, _ = ch.judge(good_inspect, status(format(mask & ~(1 << ch.CAPS["KILL"]), "016x"), 1))
check("a missing capability is reported (something may break)", len(problems) == 1 and "missing capabilities" in problems[0] and "KILL" in problems[0])

problems, _ = ch.judge({"HostConfig": {"PidsLimit": 5000, "SecurityOpt": ["no-new-privileges:true"]}}, status(format(mask, "016x"), 1))
check("a pids limit above 1024 is flagged", len(problems) == 1 and "pids limit is 5000" in problems[0])

problems, _ = ch.judge({"HostConfig": {"PidsLimit": 1024, "Privileged": True, "SecurityOpt": ["seccomp=unconfined"]}}, status(format(mask, "016x"), 1))
check("privileged and unconfined are flagged", any("PRIVILEGED" in p for p in problems) and any("switched off" in p for p in problems))
check("-1 (unlimited) is flagged", ch.judge({"HostConfig": {"PidsLimit": -1}}, status(format(mask, "016x"), 1))[0] != [])
check("no arguments is a usage error", ch.main([]) == 2 and ch.main(["--x"]) == 2)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("all container_hardening checks passed")
