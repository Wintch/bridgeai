#!/usr/bin/env python3
"""Offline test of gpu-host/driver_watch.py: apt-cache, dpkg, dkms, /boot and nvidia-smi are scripted text, no apt, no root, no GPU.
Checks that the script only ever reads. Run: python3 -I gpu-host/driver_watch_selftest.py"""
import calendar, contextlib, io, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import driver_watch as dw  # noqa: E402

FAIL = []
MB = 2**20
FIX = os.path.join(HERE, "fixtures", "driver_watch")        # recorded answers of the public feeds (trimmed), see fixtures/driver_watch/README
NOW = calendar.timegm((2026, 11, 17, 12, 0, 0))


def fx(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read().encode()


SEC_API = dw.API + "/repos/NVIDIA/product-security/contents/"
SEC_RAW = dw.RAW + "/NVIDIA/product-security/main/"
UNLOCK_REL = dw.API + "/repos/Zagitta/gpu-unlock/releases?per_page=30"
UNLOCK_TAGS = dw.API + "/repos/Zagitta/gpu-unlock/tags?per_page=30"


class FakeNet:
    """The public feeds as recorded files. `urls` maps a URL to (status, headers, body); a URL not in it is a connection error.
    Every request is kept in `.log`; nothing here touches the network."""
    def __init__(self, **over):
        self.urls = {SEC_API: (200, {}, fx("contents_root.json")),
                     SEC_RAW + "2026/README.md": (200, {}, fx("readme_2026.md")), SEC_RAW + "2025/README.md": (200, {}, fx("readme_2025.md")),
                     UNLOCK_REL: (200, {}, fx("gpu_unlock_releases.json")), UNLOCK_TAGS: (200, {}, fx("gpu_unlock_tags.json"))}
        for y, i in (("2026", "5861"), ("2026", "5821"), ("2026", "5747"), ("2025", "5703")):
            self.urls[f"{SEC_RAW}{y}/{i}/{i}.md"] = (200, {}, fx(f"bulletin_{i}.md"))
        self.urls.update(over)
        self.log = []

    def get(self, url, accept="*/*", timeout=20):
        self.log.append(url)
        if url not in self.urls:
            raise dw.NetError("unreachable")
        return self.urls[url]


def feeds_of(net=None, cache=None, now=NOW):
    src = dw.Source(net or FakeNet(), cache if cache is not None else {}, lambda: now)
    return dw.security_feed(src, now), src


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

# ------------------------------------------------------------------------------------------- the security feed (recorded answers)
check("year dirs: the directories named like a year, newest first", dw.parse_year_dirs(json.loads(fx("contents_root.json"))), ["2026", "2025", "2024", "2023", "2022"])
check("year dirs: not a list -> none", dw.parse_year_dirs({"message": "rate limit"}), [])
idx = dw.parse_index(fx("readme_2026.md").decode(), "2026")
check("index: only the GPU Display Driver rows (the en dash and the hyphen titles), newest information kept as ids and dates",
      [(e["id"], e["initial"], e["updated"]) for e in idx], [("5861", "2026-09-30", "2026-10-13"), ("5821", "2026-05-19", "2026-05-21"), ("5747", "2026-01-28", "2026-01-28")])
check("index: no title text is kept", any("Bulletin" in json.dumps(e) for e in idx), False)
b = dw.parse_bulletin(fx("bulletin_5861.md").decode())
check("bulletin 5861: the Linux(R<branch>) fixed versions; the vGPU, Windows and guest rows are not used", b["fixed"], {"580": "580.178.04", "595": "595.91.07", "610": "610.57.04", "615": "615.71.09"})
check("bulletin: CVE count of the kept rows and the highest base score", (b["cves"], b["max_cvss"]), (2, 7.8))
b = dw.parse_bulletin("| CVE-2026-1111 | GeForce | Linux(R595) | prior | 580.1.1 |\n| CVE-2026-1111 | GeForce | Linux(R595) | prior | 595.2.3 |\n| CVE-2026-1112 | GeForce | Linux(R595) | prior | 595.4.0 |\n| CVE-2026-1113 | Tesla | Windows(R595) | prior | 596.1 |\n")
check("bulletin: a version of another branch is ignored, the highest of a branch is kept, other platforms are not used", b["fixed"], {"595": "595.4.0"})
check("bulletin: no table -> nothing", dw.parse_bulletin("# nothing here\n| a | b |\n")["fixed"], {})

net = FakeNet()
feed, src = feeds_of(net)
check("feed: the newest four driver bulletins, newest first", [x["id"] for x in feed["bulletins"]], ["5861", "5821", "5747", "5703"])
check("feed: one listing, two yearly indexes and four bulletins; the fifth driver bulletin of the index is not asked for", (len(net.log), "2025/5670/5670.md" in " ".join(net.log)), (7, False))
check("feed: no problem, not stale", (feed["problems"], feed["stale"]), ([], False))
check("feed: only the two allowed hosts are asked", sorted({u.split("/")[2] for u in net.log}), ["api.github.com", "raw.githubusercontent.com"])
cache = {}
feeds_of(FakeNet(), cache)
net2 = FakeNet()
feed2, _ = feeds_of(net2, cache)
check("cache: a second run asks for the listing and the indexes only (no bulletin changed)", (len(net2.log), [x["id"] for x in feed2["bulletins"]]), (3, ["5861", "5821", "5747", "5703"]))
upd = fx("readme_2026.md").decode().replace("2026-09-30 | 2026-10-13", "2026-09-30 | 2026-11-02")
net3 = FakeNet(**{SEC_RAW + "2026/README.md": (200, {}, upd.encode())})
feed3, _ = feeds_of(net3, cache)
check("cache: a bulletin whose index row changed is fetched again, the others are not", [u.rsplit("/", 1)[1] for u in net3.log if u.endswith(".md") and "README" not in u], ["5861.md"])
check("cache: the bulletin that dropped out of the newest four is forgotten", sorted(cache["security"]["bulletins"]), ["5703", "5747", "5821", "5861"])

# ---------------------------------------------------------------------------------------------------------- the verdict, by version
fd = feed
cands = lambda *v: list(v)
p = dw.security_picture("595.71.05", fd, cands("595.80.01"))
check("595.71.05, the repo has 595.80.01: vulnerable, the fix 595.91.07 (bulletin 5861) is not in the repo", (p["state"], p["fixed_in"], p["bulletin"], p["fix_target"], p["installed_branch"]),
      ("vulnerable_fix_not_in_repo", "595.91.07", "5861", None, "595"))
p = dw.security_picture("595.71.05", fd, cands("595.91.07"))
check("...the repo has 595.91.07: vulnerable, fix in the repo", (p["state"], p["fix_target"]), ("vulnerable_fix_in_repo", "595.91.07"))
p = dw.security_picture("595.71.05", fd, cands("595.80.01", "610.57.04"))
check("...only a newer branch has it (610.57.04 is the fix of 610): that is the fix target", (p["state"], p["fix_target"]), ("vulnerable_fix_in_repo", "610.57.04"))
p = dw.security_picture("595.71.05", fd, cands("595.80.01", "600.12.01"))
check("...a newer branch the bulletins do not list is not a proven fix", (p["state"], p["fix_target"]), ("vulnerable_fix_not_in_repo", None))
p = dw.security_picture("595.91.07", fd, [])
check("595.91.07 is the fixed version itself: current", p["state"], "current")
p = dw.security_picture("595.99.01", fd, [])
check("above the fix: current", p["state"], "current")
p = dw.security_picture("580.126.09", fd, cands("580.159.03"))
check("580.126.09 is below two bulletins: the highest fix 580.178.04 counts, 580.159.03 does not fix the newest", (p["state"], p["fixed_in"], p["bulletin"]), ("vulnerable_fix_not_in_repo", "580.178.04", "5861"))
p = dw.security_picture("580.126.09", fd, cands("580.159.03", "580.178.04"))
check("...and 580.178.04 fixes both", p["fix_target"], "580.178.04")
p = dw.security_picture("570.133.07", fd, [])
check("570: the newest bulletin does not list the branch but 5747 does (570.211.01 > installed): vulnerable, proven by the older bulletin", (p["state"], p["fixed_in"]), ("vulnerable_fix_not_in_repo", "570.211.01"))
p = dw.security_picture("570.211.01", fd, [])
check("570.211.01 meets the last fix but the newest bulletin no longer lists branch 570 (unaffected or out of support): unknown, not current", (p["state"], p["why"]), ("unknown", "branch_unlisted_newest"))
p = dw.security_picture("555.42.02", fd, [])
check("a branch no bulletin lists: unknown", (p["state"], p["why"]), ("unknown", "branch_unlisted"))
check("no feed: unknown, not_checked; an empty feed: unknown with the first problem word", (dw.security_picture("595.71.05", None, [])["why"], dw.security_picture("595.71.05", {"bulletins": [], "problems": ["rate_limited"]}, [])["why"]),
      ("not_checked", "rate_limited"))

# ---------------------------------------------------------------------------------------------------------------- failing feeds
feed, src = feeds_of(FakeNet(**{SEC_API: (500, {}, b"x")}))
check("listing fails: the clock's years (2026, 2025) are used and the bulletins are still read; the problem is named", ([x["id"] for x in feed["bulletins"]], feed["problems"]), (["5861", "5821", "5747", "5703"], ["http_error"]))
net = FakeNet()
net.urls = {}
feed, src = feeds_of(net)
check("offline: no bulletin, the problem word is unreachable, no crash", (feed["bulletins"], feed["problems"]), ([], ["unreachable"]))
check("offline: the verdict is unknown with that word, never a guess", dw.security_picture("595.71.05", feed, [])["why"], "unreachable")
limited = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(NOW + 1800)}
cache = {}
net = FakeNet(**{SEC_API: (403, limited, b'{"message": "API rate limit exceeded"}')})
feed, src = feeds_of(net, cache)
check("rate limited (403, remaining 0): the backoff runs to GitHub's reset time and the raw files are not asked either", (cache["backoff_until"], feed["bulletins"], feed["problems"], len(net.log)), (NOW + 1800, [], ["rate_limited"], 1))
net = FakeNet()
feed, src = feeds_of(net, cache, now=NOW + 600)
check("inside the backoff nothing goes out", (net.log, feed["problems"]), ([], ["rate_limited"]))
net = FakeNet()
feed, src = feeds_of(net, cache, now=NOW + 1900)
check("after the reset time it asks again and reads everything", (len(net.log) > 3, [x["id"] for x in feed["bulletins"]]), (True, ["5861", "5821", "5747", "5703"]))
cache = {}
feeds_of(FakeNet(), cache)
cache["backoff_until"] = NOW + 600
net = FakeNet()
feed, src = feeds_of(net, cache)
check("inside a backoff the cached bulletins still give a verdict, marked stale", (net.log, [x["id"] for x in feed["bulletins"]], feed["stale"], dw.security_picture("595.71.05", feed, [])["stale"]), ([], ["5861", "5821", "5747", "5703"], True, True))
cache = {}
net = FakeNet(**{SEC_API: (429, {"retry-after": "120"}, b"")})
feeds_of(net, cache)
check("429 with Retry-After: that many seconds", cache["backoff_until"], NOW + 120)
cache = {}
net = FakeNet(**{SEC_API: (403, {}, b"")})
feeds_of(net, cache)
check("403 with no times given: an hour", cache["backoff_until"], NOW + 3600)
cache = {}
net = FakeNet(**{SEC_API: (403, {"retry-after": "999999"}, b"")})
feeds_of(net, cache)
check("the backoff is capped (6 h)", cache["backoff_until"], NOW + 6 * 3600)
cache = {}
net = FakeNet(**{SEC_API: (200, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(NOW + 900)}, fx("contents_root.json"))})
feed, _ = feeds_of(net, cache)
check("the last call of a window succeeds and sets the backoff for the next run (courtesy), this run goes on without further API calls", (cache["backoff_until"], len(net.log)), (NOW + 900, 1))
net = FakeNet(**{SEC_RAW + "2025/README.md": (404, {}, b"")})
feed, _ = feeds_of(net)
check("one yearly index missing (404): the other year is used, the problem is not_found", ([x["id"] for x in feed["bulletins"]], feed["problems"]), (["5861", "5821", "5747"], ["not_found"]))
net = FakeNet(**{SEC_RAW + "2026/README.md": (200, {}, b"<html>moved</html>")})
feed, _ = feeds_of(net)
check("an index with no table (the layout changed): bad_response named, nothing invented (only what the other year and the cache hold)", ([x["id"] for x in feed["bulletins"]], "bad_response" in feed["problems"]), (["5703"], True))
net = FakeNet(**{SEC_RAW + "2026/5861/5861.md": (200, {}, b"# a bulletin with a new layout\n| a | b |\n")})
feed, _ = feeds_of(net)
check("a bulletin with no Linux table is left out and reported, the others stay", ([x["id"] for x in feed["bulletins"]], feed["problems"]), (["5821", "5747", "5703"], ["bad_response"]))
net = FakeNet(**{SEC_RAW + "2026/5861/5861.md": (404, {}, b"")})
feed, _ = feeds_of(net)
p = dw.security_picture("595.71.05", feed, ["595.91.07"])
check("newest bulletin 5861 unreachable, nothing cached: the feed is incomplete and 595.71.05 is unknown (incomplete_feed), never current", (feed["incomplete"], p["state"], p.get("why")), (True, "unknown", "incomplete_feed"))
net = FakeNet(**{SEC_RAW + "2026/README.md": (404, {}, b"")})
feed, _ = feeds_of(net)
p = dw.security_picture("580.100.00", feed, [])
check("the 2026 index unreachable, nothing cached: incomplete, 580.100.00 unknown (incomplete_feed), never current", (feed["incomplete"], p["state"], p.get("why")), (True, "unknown", "incomplete_feed"))
feed, _ = feeds_of(FakeNet())
check("all feeds up: not incomplete, and 595.71.05 is vulnerable with the fix in the repo", (feed["incomplete"], dw.security_picture("595.71.05", feed, ["595.91.07"])["state"]), (False, "vulnerable_fix_in_repo"))
partial = dict(feed, incomplete=True)
check("an incomplete feed still reports a vulnerability that the bulletins read prove", dw.security_picture("595.71.05", partial, ["595.91.07"])["state"], "vulnerable_fix_in_repo")
check("an incomplete feed never proves current, even above every fix read", dw.security_picture("595.99.01", partial, [])["why"], "incomplete_feed")
cache = {}
feeds_of(FakeNet(), cache)
feed, _ = feeds_of(FakeNet(**{SEC_RAW + "2026/5861/5861.md": (404, {}, b""), SEC_RAW + "2026/README.md": (200, {}, fx("readme_2026.md").decode().replace("2026-09-30 | 2026-10-13", "2026-09-30 | 2026-11-02").encode())}), cache)
check("a cached copy of the missing thing exists (changed index row, bulletin unreachable): the old copy is used, stale, not incomplete", (feed["stale"], feed["incomplete"], [x["id"] for x in feed["bulletins"]][:1]), (True, False, ["5861"]))
big = FakeNet()
class BigNet:
    def get(self, url, accept="*/*", timeout=20):
        raise dw.NetError("too_big")
src = dw.Source(BigNet(), {}, lambda: NOW)
check("an answer over the size limit is a problem word, not a crash", (src.get(SEC_API), src.problems), (None, ["too_big"]))
try:
    dw.Net().get("http://example.invalid/x")
    got = "fetched"
except dw.NetError as e:
    got = e.word
check("Net only fetches the two https hosts it knows", got, "bad_url")

import http.client, urllib.request
class Truncated:
    status, headers = 200, {}
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n): raise http.client.IncompleteRead(b"par", 10)
orig_open = urllib.request.urlopen
try:
    for exc in (http.client.IncompleteRead(b"x"), http.client.BadStatusLine("x"), http.client.LineTooLong("status line")):
        def boom(*a, _e=exc, **k): raise _e
        urllib.request.urlopen = boom
        try:
            dw.Net().get(dw.API + "/x")
            got = "fetched"
        except dw.NetError as e:
            got = e.word
        check(f"Net: {type(exc).__name__} is 'unreachable', not a traceback", got, "unreachable")
    urllib.request.urlopen = lambda *a, **k: Truncated()
    try:
        dw.Net().get(dw.API + "/x")
        got = "fetched"
    except dw.NetError as e:
        got = e.word
    check("Net: a truncated chunked body (IncompleteRead while reading) is 'unreachable'", got, "unreachable")
finally:
    urllib.request.urlopen = orig_open

# the request itself: a generic User-Agent, no token, no other header
sent = []
class Resp:
    status = 200
    headers = {"X-RateLimit-Remaining": "50"}
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n=-1): return b"[]"
orig = dw.urllib.request.urlopen
dw.urllib.request.urlopen = lambda req, timeout=None: (sent.append(dict(req.header_items())), Resp())[1]
try:
    dw.Net().get(SEC_API, "application/vnd.github+json")
finally:
    dw.urllib.request.urlopen = orig
check("request headers: a generic User-Agent and Accept, no Authorization, nothing from the host", sent, [{"User-agent": "bridgeai-driver-watch", "Accept": "application/vnd.github+json"}])

# ------------------------------------------------------------------------------------------------------------- gpu-unlock upstream
def unlock_state(releases, tags, installed="2.0.0"):
    net = FakeNet(**{UNLOCK_REL: (200, {}, json.dumps(releases).encode()), UNLOCK_TAGS: (200, {}, json.dumps(tags).encode())})
    return dw.unlock_picture(installed, dw.unlock_feed(dw.Source(net, {}, lambda: NOW)))

u = dw.unlock_picture("2.0.0", dw.unlock_feed(dw.Source(FakeNet(), {}, lambda: NOW)))
check("recorded answer (only the pre-release channel 'unraid'): nothing newer, no versioned release, the channel is not a version", (u["state"], u["versioned_releases"], u["channels"], u["stable_latest"]), ("none", 0, ["unraid"], None))
u = unlock_state([{"tag_name": "v2.1.0", "prerelease": False}, {"tag_name": "v2.2.0-beta.1", "prerelease": True}, {"tag_name": "v3.0.0", "prerelease": True}], [])
check("a newer stable (2.1.0) is reported; the betas are listed but never the recommendation", (u["state"], u["stable_newer"], u["stable_latest"], u["beta_latest"]), ("stable_newer", "2.1.0", "2.1.0", "3.0.0"))
u = unlock_state([{"tag_name": "v2.2.0-beta.1", "prerelease": True}, {"tag_name": "v2.1.0-rc1", "prerelease": False}], [])
check("only betas newer (the GitHub flag, or an rc suffix on an unflagged release): beta_only", (u["state"], u["stable_latest"], u["beta_latest"]), ("beta_only", None, "2.2.0"))
u = unlock_state([{"tag_name": "v2.1.0", "prerelease": True}], [{"name": "v2.1.0"}])
check("a release flagged pre-release is a beta even when the tag has no suffix and the tags list shows it", u["state"], "beta_only")
u = unlock_state([], [{"name": "v2.1.0"}, {"name": "v2.3.0-alpha"}, {"name": "weird"}])
check("tags without releases: a plain version tag is stable, a suffixed one is not, other names are channels", (u["state"], u["stable_newer"], u["beta_latest"], u["channels"]), ("stable_newer", "2.1.0", "2.3.0", ["weird"]))
u = unlock_state([{"tag_name": "v2.1.0", "prerelease": False, "draft": True}], [])
check("a draft is not a release", u["state"], "none")
u = unlock_state([{"tag_name": "v2.0.0", "prerelease": False}], [])
check("the installed version itself is not newer", u["state"], "none")
check("no installed gpu-unlock-dkms: unknown, not_installed", unlock_state([{"tag_name": "v2.1.0", "prerelease": False}], [], None)["why"], "not_installed")
net = FakeNet(**{UNLOCK_REL: (404, {}, b""), UNLOCK_TAGS: (404, {}, b"")})
u = dw.unlock_picture("2.0.0", dw.unlock_feed(dw.Source(net, {}, lambda: NOW)))
check("both endpoints failing: unknown with the word, not 'none'", (u["state"], u["why"]), ("unknown", "not_found"))
net = FakeNet(**{UNLOCK_REL: (200, {}, b"<html>"), UNLOCK_TAGS: (200, {}, b"{}")})
u = dw.unlock_picture("2.0.0", dw.unlock_feed(dw.Source(net, {}, lambda: NOW)))
check("garbage answers: unknown", u["state"], "unknown")
check("semver: versions, pre-release suffixes, channels", (dw.semver("v1.2.3"), dw.semver("2.0.0-beta.1"), dw.semver("1.0.0rc1"), dw.semver("unraid")), (((1, 2, 3), False), ((2, 0, 0), True), ((1, 0, 0), True), None))

# ---------------------------------------------------------------------------------------------------- the whole picture, with feeds
def full(feeds_net=None, **o):
    net = feeds_net or FakeNet()
    src = dw.Source(net, {}, lambda: NOW)
    f = (dw.security_feed(src, NOW), dw.unlock_feed(dw.Source(net, {}, lambda: NOW)))
    return dw.build(dw.gather(FakeHost(**o)), f)

r = full()
txt = "\n".join(r["advice"])
check("host as recorded (595.71.05, repo 595.80.01 and a 600 branch): the fix 595.91.07 is not in the repo; the update is PERFORMANCE class, not security",
      (r["security"], r["update_class"], r["target"], r["security_detail"]["fixed_in"], r["unlock_upstream"]), ("fix_not_in_repo", "performance", "595.80.01", "595.91.07", "none"))
check("advice: says SECURITY with the bulletin, that the repo has no fix, and that the update is measure-before-adopting",
      ("SECURITY: NVIDIA's bulletin 5861" in txt and "no version at or above it yet" in txt, "PERFORMANCE / FEATURE" in txt and "measure before adopting" in txt, "SECURITY (urgent)" in txt), (True, True, False))
check("advice: the measure step is in the steps", "8. Adopt only if the selfcheck says ok and a bench" in txt, True)
r = full(madison="nvidia-open | 595.91.07-1 | u  Packages\nnvidia-open | 595.80.01-1 | u  Packages\n", pins="nvidia-driver-pinning-595.91.07\nnvidia-driver-pinning-595.80.01\n")
txt = "\n".join(r["advice"])
check("the repo offers 595.91.07: SECURITY urgent, class security, that version is the target of the steps", (r["security"], r["update_class"], r["target"], r["updates"], "SECURITY (urgent)" in txt,
      "apt install nvidia-driver-pinning-595.91.07 " in txt, "PERFORMANCE" in txt), ("fix_available", "security", "595.91.07", "same_branch", True, True, False))
check("...the urgent line carries the CVE count, the highest CVSS and the date", ("2 CVEs" in txt, "highest CVSS 7.8" in txt, "updated 2026-10-13" in txt, "branch 595" in txt), (True,) * 4)
r = full(madison="nvidia-open | 610.57.04-1 | u  Packages\nnvidia-open | 595.80.01-1 | u  Packages\n", pins="nvidia-driver-pinning-595.80.01\nnvidia-driver-pinning-610.57.04\n")
check("only a newer branch fixes it: that is the target and the update is newer_branch, class security", (r["target"], r["updates"], r["update_class"], r["security"]), ("610.57.04", "newer_branch", "security", "fix_available"))
r = full(madison="", pins="nvidia-driver-pinning-595.71.05\n")
check("vulnerable and nothing newer in the repo: no update, class none, the security line stays", (r["updates"], r["update_class"], r["security"], r["advice"][0].startswith("SECURITY: NVIDIA's bulletin 5861")), ("none", "none", "fix_not_in_repo", True))
r = full(madison="", pins="nvidia-driver-pinning-595.71.05\n", apt_age=30.0)
check("...with old package lists it says to refresh them first", "`sudo apt update` first" in "\n".join(r["advice"]), True)
r = full(smi="595.91.07\n", dpkg=DPKG.replace("595.71.05-1", "595.91.07-1"), madison="nvidia-open | 595.91.07-1 | u  Packages\n", pins="")
check("a driver at the fixed version: current, no update, nothing to do", (r["security"], r["update_class"], r["updates"], r["advice"][0].startswith("Nothing to do")), ("current", "none", "none", True))
r = full(smi="595.91.07\n", dpkg=DPKG.replace("595.71.05-1", "595.91.07-1"), madison="nvidia-open | 595.99.01-1 | u  Packages\n", pins="nvidia-driver-pinning-595.99.01\n")
check("current + a newer same-branch version: PERFORMANCE class", (r["security"], r["update_class"]), ("current", "performance"))
down = FakeNet()
down.urls = {}
r = full(down)
txt = "\n".join(r["advice"])
check("feeds unreachable: security unknown with the reason, the update is 'unknown' class, advice says could not check and where to read it; nothing guessed",
      (r["security"], r["update_class"], r["security_detail"]["why"], "could not check NVIDIA's security bulletins (unreachable)" in txt, "github.com/NVIDIA/product-security" in txt, "SECURITY" in txt.replace("security bulletins", "")),
      ("unknown", "unknown", "unreachable", True, True, False))
r = dw.build(dw.gather(FakeHost()))
check("not asked for at all (--no-network): unknown/not_checked, and the advice has no 'could not check' noise", (r["security"], r["security_detail"]["why"], "could not check" in "\n".join(r["advice"]), r["update_class"]),
      ("unknown", "not_checked", True, "unknown"))
r = full(depends="dkms, nvidia-open (= 595.71.05)", madison="nvidia-open | 595.91.07-1 | u  Packages\n", pins="nvidia-driver-pinning-595.91.07\n")
txt = "\n".join(r["advice"])
check("a security fix that gpu-unlock excludes: urgent, with the conflict named and left to the operator (not a silent 'do not update')", (r["security"], r["unlock_mismatch"], "the security fix and the unlock conflict" in txt, "do not upgrade the driver" in txt), ("fix_available", True, True, False))
r = full(FakeNet(**{UNLOCK_REL: (200, {}, json.dumps([{"tag_name": "v2.1.0", "prerelease": False}, {"tag_name": "v2.5.0-beta", "prerelease": True}]).encode())}))
txt = "\n".join(r["advice"])
check("a newer stable gpu-unlock upstream: reported as performance/feature, measure first", (r["unlock_upstream"], "newer STABLE release 2.1.0" in txt, "measure before adopting" in txt), ("stable_newer", True, True))
r = full(FakeNet(**{UNLOCK_REL: (200, {}, json.dumps([{"tag_name": "v2.5.0-beta", "prerelease": True}]).encode())}))
txt = "\n".join(r["advice"])
check("only a beta upstream: described as NOT recommended, never offered as an update", (r["unlock_upstream"], "NOT recommended" in txt, "never offered as updates" in txt), ("beta_only", True, True))
check("the result file holds words for the gate and the detail for the operator", (sorted(k for k in r if k in ("security", "update_class", "unlock_upstream", "security_detail", "unlock_upstream_detail"))),
      ["security", "security_detail", "unlock_upstream", "unlock_upstream_detail", "update_class"])
check("render: one line with the security state, the class and the upstream state", [l for l in dw.render(r).splitlines() if l.startswith("security:")][0].startswith("security: a security fix exists but the repo does not offer it yet; update class:"), True)

# the command line: feeds, the cache, --no-network
sd2 = tempfile.mkdtemp(prefix="dw-test-net-")
class SC2:
    @staticmethod
    def load_env(): return {}
    @staticmethod
    def state_dir_of(env): return sd2
    @staticmethod
    def read_json(p):
        try: return json.load(open(p))
        except (OSError, ValueError): return None
    class Host: pass
net = FakeNet()
out = io.StringIO()
with contextlib.redirect_stdout(out):
    code = dw.main(["run"], {"selfcheck": SC2, "env": {}, "state_dir": sd2, "host": FakeHost(), "net": net, "now": lambda: NOW})
f = json.load(open(os.path.join(sd2, "driver_watch.json")))
check("run: the result carries the security words and the cache file is written beside it", (code, f["security"], f["update_class"], os.path.exists(os.path.join(sd2, "driver_watch_cache.json"))), (0, "fix_not_in_repo", "performance", True))
check("run: the verdict line shows the security state", "security: a security fix exists but the repo does not offer it yet" in out.getvalue(), True)
net = FakeNet()
with contextlib.redirect_stdout(io.StringIO()):
    dw.main(["run"], {"selfcheck": SC2, "env": {}, "state_dir": sd2, "host": FakeHost(), "net": net, "now": lambda: NOW})
check("a second run: the cache saves the four bulletin requests (5 left: listing, two indexes, releases, tags; 3 of them API calls, the other two raw files)",
      (len(net.log), sum(1 for u in net.log if u.startswith(dw.API))), (5, 3))
net = FakeNet()
with contextlib.redirect_stdout(io.StringIO()):
    code = dw.main(["run", "--no-network"], {"selfcheck": SC2, "env": {}, "state_dir": sd2, "host": FakeHost(), "net": net, "now": lambda: NOW})
f = json.load(open(os.path.join(sd2, "driver_watch.json")))
check("run --no-network: no request at all, security unknown/not_checked", (code, net.log, f["security"], f["security_detail"]["why"]), (0, [], "unknown", "not_checked"))
with contextlib.redirect_stdout(io.StringIO()):
    check("an unknown option prints the usage and exits 2", dw.main(["run", "--bogus"], {"selfcheck": SC2, "env": {}, "state_dir": sd2}), 2)

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
    code = dw.main(["run"], {"selfcheck": SC, "env": {}, "state_dir": sd, "host": FakeHost(), "net": FakeNet(), "now": lambda: NOW})
f = json.load(open(os.path.join(sd, "driver_watch.json")))
check("run: writes the result and prints the verdict", (code, f["updates"], f["target"], out.getvalue().startswith("driver 595.71.05")), (0, "same_branch", "595.80.01", True))
out = io.StringIO()
with contextlib.redirect_stdout(out):
    code = dw.main(["status"], {"selfcheck": SC, "env": {}, "state_dir": sd})
check("status: prints the saved advice", (code, "Steps for the operator" in out.getvalue()), (0, True))
check("run with no driver: exit 2", dw.main(["run"], {"selfcheck": SC, "env": {}, "state_dir": sd, "host": FakeHost(smi=None), "net": FakeNet()}), 2)

print()
print(f"{len(FAIL)} FAILED: {FAIL}" if FAIL else "all ok")
sys.exit(1 if FAIL else 0)
