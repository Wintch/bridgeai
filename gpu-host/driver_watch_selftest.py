#!/usr/bin/env python3
"""Offline test of gpu-host/driver_watch.py: apt-cache, dpkg, dkms, /boot and nvidia-smi are scripted text, no apt, no root, no GPU.
Checks that the script only ever reads. Run: python3 -I gpu-host/driver_watch_selftest.py"""
import contextlib, io, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import driver_watch as dw  # noqa: E402

FAIL = []
MB = 2**20


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


PINS = "nvidia-driver-pinning-595.71.05\nnvidia-driver-pinning-595.80.01\nnvidia-driver-pinning-580.126.09\n"
MAD_OPEN = """nvidia-open | 595.80.01-1 | https://example.invalid/cuda/repos/debian13/x86_64  Packages
nvidia-open | 595.71.05-1 | https://example.invalid/cuda/repos/debian13/x86_64  Packages
nvidia-open | 1:600.12.01-1 | https://example.invalid/cuda/repos/debian13/x86_64  Packages
"""
DPKG = """ii |nvidia-open|595.71.05-1
ii |nvidia-driver-pinning-595.71.05|595.71.05-1
ii |libnvidia-compute|595.71.05-1
ii |gpu-unlock-dkms|2.0.0
ii |gpu-unlock-firmware|2.0.0
ii |linux-image-6.12.73+deb13-amd64|6.12.73-1
ii |linux-image-6.12.74+deb13-amd64|6.12.74-1
ii |linux-image-amd64|6.12.74-1
ii |linux-headers-6.12.73+deb13-amd64|6.12.73-1
ii |linux-headers-6.12.74+deb13-amd64|6.12.74-1
rc |linux-image-6.1.0-old|6.1.0-1
"""
DKMS_OK = """nvidia/595.71.05, 6.12.73+deb13-amd64, x86_64: installed
nvidia/595.71.05, 6.12.74+deb13-amd64, x86_64: installed
gpu-unlock/2.0.0, 6.12.73+deb13-amd64, x86_64: installed
gpu-unlock/2.0.0, 6.12.74+deb13-amd64, x86_64: installed
"""
SIM_NONE = "Reading package lists...\n0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n"
SIM_KERNEL = ("Inst linux-image-6.12.80+deb13-amd64 (6.12.80-1 Debian-Security:13/stable-security [amd64])\n"
              "Inst linux-headers-6.12.80+deb13-amd64 (6.12.80-1 Debian-Security:13/stable-security [amd64])\n"
              "Inst libfoo (1.2 Debian:13/stable [amd64])\n")


class FakeHost:
    def __init__(self, **o):
        self.o = {"smi": "595.71.05\n", "pins": PINS, "madison": MAD_OPEN, "dpkg": DPKG, "sim": SIM_NONE, "dkms": DKMS_OK,
                  "manual": "nvidia-open\nvim\nlibnvidia-compute\ngpu-unlock-dkms\ngpu-unlock-firmware\nnvidia-driver-pinning-595.71.05\n",
                  "policy": "gpu-unlock-dkms:\n  Installed: 2.0.0\n  Candidate: 2.0.0\n", "depends": "dkms, nvidia-open (>= 580)",
                  "disk": (400 * MB, 250 * MB), "boot": 70 * MB, "apt_age": 2.0, "osrelease": "6.12.74+deb13-amd64\n"}
        self.o.update(o)
        self.calls = []

    def cmd(self, argv, timeout=20):
        self.calls.append(list(argv))
        o = self.o
        if argv[0] == "nvidia-smi":
            return (0, o["smi"]) if o["smi"] is not None else (127, "")
        if argv[:2] == ["apt-cache", "pkgnames"]:
            return 0, o["pins"]
        if argv[:2] == ["apt-cache", "madison"]:
            return 0, o["madison"] if argv[2] == "nvidia-open" else ""
        if argv[:2] == ["apt-cache", "policy"]:
            return 0, o["policy"]
        if argv[0] == "dpkg-query" and argv[-1].startswith("-f=${Depends}") or (argv[0] == "dpkg-query" and "${Depends}" in argv[2]):
            return 0, o["depends"]
        if argv[0] == "dpkg-query":
            return 0, o["dpkg"]
        if argv[:2] == ["apt-get", "-s"]:
            return 0, o["sim"]
        if argv[:2] == ["dkms", "status"]:
            return 0, o["dkms"]
        if argv[:2] == ["apt-mark", "showmanual"]:
            return 0, o["manual"]
        return 127, ""

    def read(self, path):
        return self.o["osrelease"] if path == "/proc/sys/kernel/osrelease" else None

    def disk(self, path):
        return self.o["disk"]

    def boot_sizes(self, release):
        return {"vmlinuz-" + release: 12 * MB, "initrd.img-" + release: self.o["boot"] - 12 * MB}

    def mtime(self, path):
        return self.now() - self.o["apt_age"] * 86400 if self.o["apt_age"] is not None else None

    def now(self):
        return 2_000_000_000.0


def watch(**o):
    return dw.build(dw.gather(FakeHost(**o)))


# ------------------------------------------------------------------------------------------------------------------- parsers
check("madison: versions without epoch and revision", dw.parse_madison(MAD_OPEN), {"595.80.01", "595.71.05", "600.12.01"})
check("pin names: the versions the repo offers", dw.parse_pin_names(PINS), {"595.71.05", "595.80.01", "580.126.09"})
check("pin names: other lines ignored", dw.parse_pin_names("nvidia-open\nfoo\n"), set())
check("dpkg: only installed (ii) packages", sorted(dw.parse_dpkg_installed(DPKG))[:3], ["gpu-unlock-dkms", "gpu-unlock-firmware", "libnvidia-compute"])
check("kernels: releases from linux-image-N packages; the metapackage and removed ones are not kernels",
      dw.kernels_from_packages(dw.parse_dpkg_installed(DPKG)), ["6.12.73+deb13-amd64", "6.12.74+deb13-amd64"])
check("sim: Inst lines", dw.parse_sim_installs(SIM_KERNEL), ["linux-image-6.12.80+deb13-amd64", "linux-headers-6.12.80+deb13-amd64", "libfoo"])
check("dkms: new format", dw.parse_dkms_status("nvidia/595.71.05, 6.12.74+deb13-amd64, x86_64: installed")[0], ("nvidia", "595.71.05", "6.12.74+deb13-amd64", "installed"))
check("dkms: old format and a warning suffix", [r[3] for r in dw.parse_dkms_status("nvidia, 595.71.05, 6.12.74+deb13-amd64, x86_64: installed (WARNING! Diff between built and installed module!)\nnvidia, 595.71.05, 6.12.73+deb13-amd64, x86_64: built")], ["installed", "built"])
check("dkms: lines without a kernel (added only) are not builds", dw.parse_dkms_status("nvidia/595.71.05: added"), [])
check("policy candidate", (dw.parse_policy_candidate("  Candidate: 2.0.1\n"), dw.parse_policy_candidate("  Candidate: (none)\n")), ("2.0.1", None))
check("depends: nvidia constraints only", dw.depends_constraints("dkms, nvidia-kernel-open-dkms (= 595.71.05), libc6 (>= 2.3)"), [("nvidia-kernel-open-dkms", "=", "595.71.05")])
check("constraint: exact pin excludes another version, accepts its own", (dw.constraint_excludes([("nvidia-x", "=", "595.71.05")], "595.80.01"), dw.constraint_excludes([("nvidia-x", "=", "595.71.05")], "595.71.05")), (True, False))
check("constraint: a lower bound is satisfied by a newer driver", dw.constraint_excludes([("nvidia-x", ">=", "580")], "600.12.01"), False)

# ---------------------------------------------------------------------------------------------------------------- the picture
r = watch()
check("same branch has a newer version (595.80.01); the newer branch 600 is listed too", (r["updates"], r["target"], r["same_branch_newer"], r["newer_branches"]),
      ("same_branch", "595.80.01", ["595.80.01"], {"600": "600.12.01"}))
check("the older branch 580 is not an update", "580.126.09" in json.dumps(r["same_branch_newer"]) + json.dumps(r["newer_branches"]), False)
check("nothing else wrong: no kernel pending, no dkms gap, /boot fine, lists fresh", (r["kernel_pending"], r["dkms_gap"], r["boot_low"], r["apt_stale"], r["unlock_mismatch"]), (False,) * 5)
check("the gpu-unlock packages are reported", (r["unlock_pkg"], r["unlock_fw"], r["unlock_candidate"]), ("2.0.0", "2.0.0", None))
txt = "\n".join(r["advice"])
check("advice: the exact simulate / apply / verify / rollback steps with this host's names",
      all(x in txt for x in ("sudo apt update", "apt install -s nvidia-driver-pinning-595.80.01 nvidia-open libnvidia-compute", "apt install nvidia-driver-pinning-595.80.01 ",
                             "dkms status", "gpu_selfcheck.py run --force", "nvidia-driver-pinning-595.71.05 libnvidia-compute=595.71.05-1 nvidia-open=595.71.05-1")), True)
check("advice: it warns that gpu-unlock was only checked with the installed driver", "were checked only with driver 595.71.05" in txt and "may not support 595.80.01" in txt, True)
check("advice: vim is not a driver package; the old pin and gpu-unlock are not in the upgrade line (the pin is swapped, gpu-unlock has its own version)",
      ("vim" in txt, "apt install nvidia-driver-pinning-595.80.01 nvidia-open libnvidia-compute   (" in txt), (False, True))

r = watch(madison="", pins="")
check("repo has nothing newer: updates none, nothing to do", (r["updates"], r["target"], r["newest"], r["advice"][0].startswith("Nothing to do")), ("none", None, "595.71.05", True))
r = watch(madison="nvidia-open | 600.12.01-1 | u  Packages\n", pins="nvidia-driver-pinning-600.12.01\n")
check("only a newer branch: updates newer_branch, advice says to check it is a production branch", (r["updates"], r["target"], "production branch" in "\n".join(r["advice"])), ("newer_branch", "600.12.01", True))
r = watch(madison="", pins="nvidia-driver-pinning-595.71.05\n")
check("the installed version itself is not an update", r["updates"], "none")

r = watch(sim=SIM_KERNEL, madison="", pins="")
check("pending kernel with its headers pending too: reported, headers not missing", (r["kernel_pending"], r["pending_kernels"], r["headers_missing"]), (True, ["6.12.80+deb13-amd64"], []))
check("pending kernel advice names the DKMS rebuild and gives the dist-upgrade steps", ("DKMS must rebuild" in "\n".join(r["advice"]), "apt-get -s dist-upgrade" in "\n".join(r["advice"])), (True, True))
r = watch(sim="Inst linux-image-6.12.80+deb13-amd64 (6.12.80-1 x [amd64])\n", madison="", pins="")
check("pending kernel without headers: DKMS cannot build, said", r["headers_missing"], ["6.12.80+deb13-amd64"])

bad = DKMS_OK.replace("nvidia/595.71.05, 6.12.74+deb13-amd64, x86_64: installed", "nvidia/595.71.05, 6.12.74+deb13-amd64, x86_64: built")
r = watch(dkms=bad, madison="", pins="")
check("an installed kernel with no installed nvidia build: dkms_gap", (r["dkms_gap"], r["dkms_gaps"]), (True, ["nvidia for 6.12.74+deb13-amd64"]))
r = watch(dkms=DKMS_OK.replace("gpu-unlock/2.0.0, 6.12.74+deb13-amd64, x86_64: installed\n", ""), madison="", pins="")
check("...also for the gpu-unlock module", r["dkms_gaps"], ["gpu-unlock for 6.12.74+deb13-amd64"])

# /boot: one kernel is 70 MB here; the margin is 1.5x (105 MB). It matters only while a kernel update is pending.
r = watch(disk=(400 * MB, 90 * MB), sim=SIM_KERNEL, madison="", pins="")
check("/boot: kernel pending and 90 MB free < 1.5 x 70 MB -> boot_low", (r["boot_low"], r["boot"]["free_mb"], r["boot"]["one_kernel_mb"], r["boot"]["fits"]), (True, 90, 70, 5))
r = watch(disk=(400 * MB, 150 * MB), sim=SIM_KERNEL, madison="", pins="")
check("/boot: kernel pending and 150 MB free is enough", r["boot_low"], False)
r = watch(disk=(400 * MB, 90 * MB), madison="", pins="")
check("/boot: 90 MB free with nothing pending is not an alarm", r["boot_low"], False)
# a /boot that really fits two kernels, with exactly two installed: free = total - installed (consistent figures)
r = watch(disk=(150 * MB, 10 * MB), sim=SIM_KERNEL, madison="", pins="")
check("/boot: two kernels fill the 150 MB, a third is pending (10 MB free) -> low", (r["boot"]["fits"], r["boot"]["free_mb"], r["boot_low"], "cannot take the pending kernel" in "\n".join(r["advice"])), (2, 10, True, True))
r = watch(disk=(150 * MB, 10 * MB), madison="", pins="")
check("/boot: the same full /boot with no kernel pending is the steady state, not an alarm (and no update, nothing to do)", (r["boot_low"], r["advice"][0].startswith("Nothing to do")), (False, True))
r = watch(disk=None, madison="", pins="")
check("/boot unreadable: no alarm, no numbers", (r["boot_low"], r["boot"]["free_mb"]), (False, None))

r = watch(depends="dkms, nvidia-open (= 595.71.05)")
check("gpu-unlock exact requirement excludes the new driver: unlock_mismatch and a do-not-upgrade line", (r["unlock_mismatch"], "do not upgrade the driver" in "\n".join(r["advice"])), (True, True))
r = watch(policy="  Installed: 2.0.0\n  Candidate: 2.1.0\n", madison="", pins="")
check("a newer gpu-unlock in the repo is reported", (r["unlock_candidate"], "newer gpu-unlock-dkms" in "\n".join(r["advice"])), ("2.1.0", True))
r = watch(apt_age=30.0)
check("stale package lists are reported", (r["apt_stale"], "30 days old" in "\n".join(r["advice"])), (True, True))
r = watch(apt_age=None)
check("no stamp file: not reported as stale", r["apt_stale"], False)
r = watch(smi=None)  # nvidia-smi gone: the proc file is read, absent in the fake
check("no driver readable: gather finds none", dw.gather(FakeHost(smi=None))["installed"], None)

# ------------------------------------------------------------------------------------------------------- only ever reads
host = FakeHost(sim=SIM_KERNEL)
dw.gather(host)
verbs = {tuple(c[:2]) for c in host.calls}
writers = [c for c in host.calls if c[:2] in (["apt-get", "install"], ["apt", "install"], ["apt-get", "update"], ["apt-get", "remove"], ["dkms", "build"], ["dkms", "install"])
           or c[0] in ("sudo", "reboot", "modprobe", "rmmod") or (c[:2] == ["apt-get", "-s"]) is False and c[0] == "apt-get"]
check("gather runs only reads (apt-get only with -s, no sudo, no install, no update, no dkms build)", writers, [])
check("the only apt-get call is the simulation", [c for c in host.calls if c[0] == "apt-get"], [["apt-get", "-s", "dist-upgrade"]])

# the command line, with a state dir
sd = tempfile.mkdtemp(prefix="dw-test-")
class SC:  # the bits of gpu_selfcheck.py the CLI borrows
    @staticmethod
    def load_env(): return {}
    @staticmethod
    def state_dir_of(env): return sd
    @staticmethod
    def read_json(p):
        try: return json.load(open(p))
        except (OSError, ValueError): return None
    class Host: pass
out = io.StringIO()
with contextlib.redirect_stdout(out):
    code = dw.main(["run"], {"selfcheck": SC, "env": {}, "state_dir": sd, "host": FakeHost()})
f = json.load(open(os.path.join(sd, "driver_watch.json")))
check("run: writes the result and prints the verdict", (code, f["updates"], f["target"], out.getvalue().startswith("driver 595.71.05")), (0, "same_branch", "595.80.01", True))
out = io.StringIO()
with contextlib.redirect_stdout(out):
    code = dw.main(["status"], {"selfcheck": SC, "env": {}, "state_dir": sd})
check("status: prints the saved advice", (code, "Steps for the operator" in out.getvalue()), (0, True))
check("run with no driver: exit 2", dw.main(["run"], {"selfcheck": SC, "env": {}, "state_dir": sd, "host": FakeHost(smi=None)}), 2)

print()
print(f"{len(FAIL)} FAILED: {FAIL}" if FAIL else "all ok")
sys.exit(1 if FAIL else 0)
