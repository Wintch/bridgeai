#!/usr/bin/env python3
"""make-seccomp-userns.py DEFAULT.json OUT.json: Docker's own default seccomp profile plus the few calls an UNPRIVILEGED user namespace needs.

Steam's runtime (pressure-vessel) and Proton start every game inside bubblewrap, which makes a user namespace and mounts inside it. Docker's default profile
refuses unshare/clone(NEWUSER)/mount/setns unless the container holds CAP_SYS_ADMIN, which a place must never have. This keeps everything else of the default
profile and lets those calls through WITHOUT the capability: they only act inside a namespace the process creates for itself (the container still has no
capabilities, no sudo, no /dev/uinput). What it costs: the kernel's user-namespace code is reachable from inside the container. See PLACES.md, "Games".
"""
import json, sys

OPEN = {"unshare", "setns", "mount", "umount", "umount2", "pivot_root", "sethostname", "setdomainname", "clone"}


def build(default):
    prof = json.loads(json.dumps(default))
    out = []
    for rule in prof["syscalls"]:
        names = rule.get("names") or ([rule["name"]] if "name" in rule else [])
        gated = rule.get("action") == "SCMP_ACT_ALLOW" and rule.get("includes", {}).get("caps") == ["CAP_SYS_ADMIN"]
        if gated:
            keep = [n for n in names if n not in OPEN]
            if keep:
                out.append({**rule, "names": keep})
            continue
        if names == ["clone"]:      # the masked-flags variants: replaced by one plain allow below
            continue
        out.append(rule)
    out.append({"names": sorted(OPEN), "action": "SCMP_ACT_ALLOW"})
    prof["syscalls"] = out
    return prof


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    json.dump(build(json.load(open(sys.argv[1]))), open(sys.argv[2], "w"), indent=1)
