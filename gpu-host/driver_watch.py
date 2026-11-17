#!/usr/bin/env python3
"""
driver_watch -- is there a newer NVIDIA driver, and what would a kernel or driver update need? On the GPU host, stdlib only.

  driver_watch.py run         look, write driver_watch.json into the gate's state dir (the weekly timer runs this). Exit 0.
  driver_watch.py status      print the last result and the operator steps (reads the file; `run` first if there is none)

It NEVER installs, removes or changes anything: no apt install, no apt update (that needs root; the lists are the operator's to
refresh, and their age is reported), no dkms, no reboot. It reads dpkg, apt-cache and `apt-get -s` (a simulation), dkms status,
/boot and the gpu-unlock packages, and reports:
  * the installed driver against the newest in the configured CUDA repo for the SAME branch and for NEWER branches. The pin
    (nvidia-driver-pinningVERSION) makes apt keep the installed version, so the comparison is explicit: candidates come from the
    pinning packages the repo offers and from `apt-cache madison` of the driver metapackages, which ignore the pin;
  * pending kernel updates (a new kernel needs the nvidia and gpu-unlock modules rebuilt by DKMS, and its headers) and installed
    kernels with no DKMS build of those modules (a reboot into one would come up without the driver or without the unlock);
  * /boot free space against the size of one kernel + initrd (two kernels are all that fits on this host class);
  * the gpu-unlock package versions, a newer one in the repo, and a version constraint that excludes the new driver.
and prints the exact operator steps: refresh the lists, read the simulation, make room, unpin and upgrade, rebuild DKMS, reboot, run
gpu_selfcheck.py, and how to roll back. A driver the gpu-unlock package was not built for may leave the card stock; the selfcheck
after the reboot is what tells.

Why: the unlock speeds FP16/TF32 work by about a third; a driver bump that silently drops it wastes energy on every job. Updating
the driver is how security fixes arrive, so it must stay current, and each update is verified by the selfcheck (GPU_WATCH.md).
The gate shows fixed words from the result in GET /state, and the ops bot tells the operator.
"""
import importlib.util
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RESULT = "driver_watch.json"
DRIVER_META = ("cuda-drivers", "nvidia-open", "nvidia-driver", "nvidia-kernel-open-dkms")   # packages whose madison lists driver versions
PIN_PREFIX = "nvidia-driver-pinning-"
DKMS_MODULES = re.compile(r"^(nvidia|gpu[-_]unlock)", re.I)
MANUAL_PKG = re.compile(r"^(nvidia|libnvidia|cuda-drivers|xserver-xorg-video-nvidia|gpu-unlock)")
# /boot: apt writes the new kernel and a new initramfs while the old ones are still there, so one kernel's worth of space
# is not enough; 1.5x covers the temporary initramfs copy.
BOOT_MARGIN = 1.5
APT_STALE_DAYS = 14                                         # package lists older than this are reported; refreshing them is the operator's
VER = re.compile(r"^(?:\d+:)?(\d+(?:\.\d+){1,2})")


def load_selfcheck():
    spec = importlib.util.spec_from_file_location("driver_watch_selfcheck", os.path.join(HERE, "gpu_selfcheck.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Host:
    def __init__(self, base):
        self.cmd, self.read = base.cmd, base.read

    def disk(self, path):
        try:
            st = os.statvfs(path)
        except OSError:
            return None
        return st.f_frsize * st.f_blocks, st.f_frsize * st.f_bavail

    def boot_sizes(self, release):
        """{file: bytes} of the /boot files of one kernel release (vmlinuz, initrd.img, System.map, config)."""
        out = {}
        try:
            for n in os.listdir("/boot"):
                if n.endswith("-" + release):
                    out[n] = os.path.getsize(os.path.join("/boot", n))
        except OSError:
            pass
        return out

    def mtime(self, path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    now = staticmethod(time.time)


def vtuple(v):
    m = VER.match(v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def clean_version(v):
    """'1:595.71.05-1' -> '595.71.05' (epoch and Debian revision dropped); None when it does not look like a driver version."""
    m = VER.match(v or "")
    return m.group(1) if m else None


# ------------------------------------------------------------------------------------------------------------------ parsing
def parse_madison(text):
    """Versions from `apt-cache madison PKG` lines: 'PKG | 595.71.05-1 | http://... suite/main amd64 Packages'."""
    out = set()
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            v = clean_version(parts[1])
            if v:
                out.add(v)
    return out


def parse_pin_names(text):
    """Versions from the names of the pinning packages the repo offers (nvidia-driver-pinning-595.71.05)."""
    out = set()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(PIN_PREFIX):
            v = clean_version(line[len(PIN_PREFIX):])
            if v:
                out.add(v)
    return out


def parse_dpkg_installed(text):
    """{package: version} for the lines 'ii |package|version' of dpkg-query -W -f='${db:Status-Abbrev}|${Package}|${Version}\\n'."""
    out = {}
    for line in text.splitlines():
        st, _, rest = line.partition("|")
        pkg, _, ver = rest.partition("|")
        if st.strip().startswith("ii") and pkg:
            out[pkg.strip()] = ver.strip()
    return out


def kernels_from_packages(installed):
    """Kernel releases from linux-image-RELEASE packages (the linux-image-amd64 metapackage and -dbg are not kernels)."""
    rel = []
    for p in installed:
        m = re.match(r"^linux-image-(\d\S*)$", p)
        if m and not p.endswith("-dbg"):
            rel.append(m.group(1))
    return sorted(rel, key=lambda r: [int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", r)])


def parse_sim_installs(text):
    """Package names of the 'Inst NAME ...' lines of `apt-get -s dist-upgrade`."""
    return [m.group(1) for m in (re.match(r"^Inst (\S+)", l) for l in text.splitlines()) if m]


def parse_dkms_status(text):
    """[(module, version, kernel, status)] of `dkms status`, old ('mod, ver, kernel, arch: installed') and new ('mod/ver, kernel, arch: installed')."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*([\w.-]+)[/,]\s*([\w.+~:-]+),\s*([\w.+~-]+)(?:,\s*[\w-]+)?\s*:\s*([A-Za-z][\w -]*)", line)
        if m:
            out.append((m.group(1), m.group(2), m.group(3), m.group(4).strip().split(" ")[0].lower()))
    return out


def dkms_gaps(kernels, rows):
    """[(kernel, module)] for each installed kernel where a watched DKMS module (nvidia*, gpu-unlock*) is seen for another kernel but
    has no 'installed' build for this one."""
    mods = sorted({r[0] for r in rows if DKMS_MODULES.match(r[0])})
    built = {(r[0], r[2]) for r in rows if r[3] == "installed"}
    return [(k, m) for k in kernels for m in mods if (m, k) not in built]


def parse_policy_candidate(text):
    m = re.search(r"^\s*Candidate:\s*(\S+)", text, re.M)
    return None if not m or m.group(1) == "(none)" else m.group(1)


def depends_constraints(depends):
    """[(package, operator, version)] for the nvidia packages named with a version in a Depends line."""
    return [(m.group(1), m.group(2), m.group(3)) for m in re.finditer(r"(nvidia[\w.+-]*)\s*\(\s*([<>=]+)\s*([\w.:+~-]+)\s*\)", depends or "")]


def constraint_excludes(constraints, target):
    """True when one of the constraints is an exact or bounded version that the target driver does not satisfy."""
    t = vtuple(target)
    for _pkg, op, ver in constraints:
        v = vtuple(ver)
        if t is None or v is None:
            continue
        if (op in ("=", "==") and t != v) or (op == "<<" and not t < v) or (op == "<=" and not t <= v) or (op == ">>" and not t > v) or (op == ">=" and not t >= v):
            return True
    return False


# --------------------------------------------------------------------------------------------------------------- the picture
def newest_by_branch(versions):
    out = {}
    for v in versions:
        t = vtuple(v)
        if t and (t[0] not in out or t > vtuple(out[t[0]])):
            out[t[0]] = v
    return out


def boot_picture(disk, kernels, sizes_by_kernel, pending_kernel):
    """(free MB, one kernel MB, kernels that fit, low?) from /boot's free space and the biggest installed kernel's files."""
    if not disk:
        return {"free_mb": None, "one_kernel_mb": None, "fits": None, "low": False}
    total, free = disk
    one = max((sum(s.values()) for s in sizes_by_kernel.values()), default=0)
    fits = int(total // one) if one else None
    low = bool(one) and (free < BOOT_MARGIN * one or (pending_kernel and fits is not None and len(kernels) >= fits))
    return {"free_mb": int(free // 2**20), "one_kernel_mb": int(one // 2**20) if one else None, "fits": fits, "low": low}


def gather(host):
    smi = host.cmd(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], 15)
    installed = clean_version((smi[1].strip().splitlines() or [""])[0]) if smi[0] == 0 else None
    if not installed:
        m = re.search(r"\s(\d+\.\d+(?:\.\d+)?)\s", host.read("/proc/driver/nvidia/version") or "")
        installed = m.group(1) if m else None
    versions = parse_pin_names(host.cmd(["apt-cache", "pkgnames", PIN_PREFIX], 30)[1])
    for pkg in DRIVER_META:
        versions |= parse_madison(host.cmd(["apt-cache", "madison", pkg], 30)[1])
    dpkg_all = parse_dpkg_installed(host.cmd(["dpkg-query", "-W", "-f=${db:Status-Abbrev}|${Package}|${Version}\n"], 30)[1])
    running = (host.read("/proc/sys/kernel/osrelease") or "").strip()
    kernels = kernels_from_packages(dpkg_all)
    sim = parse_sim_installs(host.cmd(["apt-get", "-s", "dist-upgrade"], 120)[1])
    pend_img = [p[len("linux-image-"):] for p in sim if re.match(r"^linux-image-\d", p) and not p.endswith("-dbg")]
    pend_hdr = {p[len("linux-headers-"):] for p in sim if re.match(r"^linux-headers-\d", p)}
    headers_have = {p[len("linux-headers-"):] for p in dpkg_all if re.match(r"^linux-headers-\d", p)}
    rows = parse_dkms_status(host.cmd(["dkms", "status"], 30)[1])
    sizes = {k: host.boot_sizes(k) for k in kernels}
    # the driver packages to upgrade together: not the pin itself (it is swapped for the new one) and not gpu-unlock (its own version)
    manual = [p for p in host.cmd(["apt-mark", "showmanual"], 20)[1].split() if MANUAL_PKG.match(p) and not p.startswith((PIN_PREFIX, "gpu-unlock"))]
    unlock_dkms, unlock_fw = dpkg_all.get("gpu-unlock-dkms"), dpkg_all.get("gpu-unlock-firmware")
    cand = parse_policy_candidate(host.cmd(["apt-cache", "policy", "gpu-unlock-dkms"], 20)[1]) if unlock_dkms else None
    deps = host.cmd(["dpkg-query", "-W", "-f=${Depends}", "gpu-unlock-dkms"], 10)[1] if unlock_dkms else ""
    stamp = host.mtime("/var/lib/apt/periodic/update-success-stamp") or host.mtime("/var/lib/apt/lists")
    return {"installed": installed, "versions": versions, "running": running, "kernels": kernels, "pending": pend_img,
            "pending_headers": pend_hdr, "headers_have": headers_have, "dkms": rows, "sizes": sizes, "manual": manual,
            "manual_versions": {p: dpkg_all[p] for p in manual if p in dpkg_all}, "unlock_dkms": unlock_dkms,
            "unlock_fw": unlock_fw, "unlock_candidate": cand, "unlock_depends": deps, "disk": host.disk("/boot"),
            "apt_age_days": round((host.now() - stamp) / 86400, 1) if stamp else None, "now": host.now()}


def build(g):
    """The result dict (and the operator steps) from the gathered facts. Pure."""
    inst = g["installed"]
    it = vtuple(inst)
    newer = sorted((v for v in g["versions"] if it and vtuple(v) > it), key=vtuple)
    same = [v for v in newer if vtuple(v)[0] == it[0]]
    other = newest_by_branch([v for v in newer if vtuple(v)[0] > it[0]])
    updates = "same_branch" if same else "newer_branch" if other else "none"
    target = same[-1] if same else (other[max(other)] if other else None)
    gaps = dkms_gaps(g["kernels"], g["dkms"])
    pending = list(g["pending"])
    headers_missing = [k for k in pending if k not in g["pending_headers"] and k not in g["headers_have"]]
    boot = boot_picture(g["disk"], g["kernels"], g["sizes"], bool(pending))
    constraints = depends_constraints(g["unlock_depends"])
    mismatch = bool(target) and constraint_excludes(constraints, target)
    unlock_newer = bool(g["unlock_candidate"] and g["unlock_dkms"] and g["unlock_candidate"] != g["unlock_dkms"])
    apt_stale = g["apt_age_days"] is not None and g["apt_age_days"] > APT_STALE_DAYS
    res = {"schema": 1, "at": int(g["now"]), "installed": inst, "running_kernel": g["running"],
           "newest": target or inst,
           "updates": updates, "target": target, "same_branch_newer": same, "newer_branches": {str(k): v for k, v in sorted(other.items())},
           "kernel_pending": bool(pending), "pending_kernels": pending, "headers_missing": headers_missing,
           "dkms_gap": bool(gaps), "dkms_gaps": [f"{m} for {k}" for k, m in gaps],
           "boot_low": boot["low"], "boot": boot, "unlock_mismatch": mismatch, "unlock_pkg": g["unlock_dkms"], "unlock_fw": g["unlock_fw"],
           "unlock_candidate": g["unlock_candidate"] if unlock_newer else None, "apt_stale": apt_stale, "apt_age_days": g["apt_age_days"]}
    res["advice"] = advice(res, g)
    return res


def advice(res, g):
    """Operator steps, as plain strings. Package names and versions come from this host's dpkg; nothing here is run."""
    lines = []
    inst, target = res["installed"], res["target"]
    if target:
        where = "same branch" if res["updates"] == "same_branch" else "a NEWER branch (check NVIDIA's notes that it is a production branch, not a new-feature one)"
        lines.append(f"A newer driver is in the repo: {inst} -> {target} ({where}).")
    if res["kernel_pending"]:
        lines.append("Kernel update pending (" + ", ".join(res["pending_kernels"]) + "): DKMS must rebuild the nvidia and gpu-unlock modules for it.")
    if res["headers_missing"]:
        lines.append("Headers for " + ", ".join(res["headers_missing"]) + " are not installed or pending: DKMS cannot build without them.")
    if res["dkms_gap"]:
        lines.append("DKMS has no build for: " + "; ".join(res["dkms_gaps"]) + ". A reboot into that kernel would come up without the driver or the unlock.")
    if res["boot_low"]:
        b = res["boot"]
        lines.append(f"/boot is tight: {b['free_mb']} MB free, one kernel+initrd is {b['one_kernel_mb']} MB, {b['fits']} kernels fit. "
                     "Remove the oldest kernel first (its linux-image-RELEASE package, then `sudo apt autoremove --purge`).")
    if res["unlock_mismatch"]:
        lines.append(f"gpu-unlock-dkms {res['unlock_pkg']} declares a version requirement that excludes {target}: do not upgrade the driver until a matching gpu-unlock exists.")
    elif target:
        lines.append(f"gpu-unlock-dkms {res['unlock_pkg']} and gpu-unlock-firmware {res['unlock_fw']} were checked only with driver {inst}: they may not support {target}. "
                     "The selfcheck after the reboot says whether the unlock is still active; keep the rollback below ready.")
    if res["unlock_candidate"]:
        lines.append(f"A newer gpu-unlock-dkms is in the repo ({res['unlock_candidate']}).")
    if res["apt_stale"]:
        lines.append(f"The package lists are {res['apt_age_days']:.0f} days old: this report may be missing newer versions.")
    if not (target or res["kernel_pending"] or res["dkms_gap"] or res["boot_low"]):
        return lines or ["Nothing to do: the installed driver is the newest the repo offers and no kernel update is pending."]
    pkgs = " ".join(g["manual"]) or "<the nvidia packages installed here>"
    old_pkgs = " ".join(f"{p}={v}" for p, v in sorted(g["manual_versions"].items())) or "<package=version of each nvidia package now>"
    steps = ["Steps for the operator (nothing is done for you; stop work on the card first: `gateway gpu off`, then check the gate's GET /state shows no service running):"]
    steps.append("  1. sudo apt update")
    if target:
        steps.append(f"  2. Simulate: sudo apt install -s {PIN_PREFIX}{target} {pkgs}   (read it: it must not remove gpu-unlock-dkms, gpu-unlock-firmware or the running kernel; replacing the old pin is expected)")
        steps.append(f"  3. Apply:    sudo apt install {PIN_PREFIX}{target} {pkgs}   (the old pin {PIN_PREFIX}{inst} is replaced; DKMS rebuilds for every installed kernel that has headers)")
    else:
        steps.append("  2. Simulate: sudo apt-get -s dist-upgrade   (read the kernel and headers lines)")
        steps.append("  3. Apply:    sudo apt-get dist-upgrade   (DKMS rebuilds nvidia and gpu-unlock for the new kernel)")
    steps.append("  4. Check:    dkms status   (nvidia and gpu-unlock must say `installed` for every kernel in /boot) and df -h /boot")
    steps.append("  5. Reboot in a quiet window.")
    steps.append("  6. Verify:   python3 gpu-host/gpu_selfcheck.py run --force   (ok = the unlock is active; degraded = it is not)")
    steps.append(f"  7. Roll back if degraded: sudo apt install {PIN_PREFIX}{inst} {old_pkgs}, reboot, selfcheck again.")
    return lines + steps


# ------------------------------------------------------------------------------------------------------------------- driver
def write_result(state_dir, res):
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    path = os.path.join(state_dir, RESULT)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def render(res):
    out = [f"driver {res['installed']} (kernel {res['running_kernel']}): " + {"none": "up to date", "same_branch": "newer version in the same branch",
                                                                          "newer_branch": "newer branch available"}[res["updates"]]]
    out += res["advice"]
    return "\n".join(out)


def main(argv=None, deps=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("run", "status"):
        print(__doc__)
        return 2
    deps = deps or {}
    sc = deps.get("selfcheck") or load_selfcheck()
    env = deps.get("env") if deps.get("env") is not None else sc.load_env()
    sd = deps.get("state_dir") or sc.state_dir_of(env)
    if argv[0] == "status":
        res = sc.read_json(os.path.join(sd, RESULT))
        if not res:
            print("no driver_watch result yet: run `driver_watch.py run`")
            return 0
        print(render(res))
        return 0
    host = deps.get("host") or Host(sc.Host())
    g = gather(host)
    if not g["installed"]:
        print("driver_watch: cannot read the installed driver (no nvidia-smi, no /proc/driver/nvidia/version)", file=sys.stderr)
        return 2
    res = build(g)
    write_result(sd, res)
    print(render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
