#!/usr/bin/env python3
"""
upkeep -- update a host with a procedure, a rollback and an audit log. On the GPU host, stdlib only. See UPKEEP.md.

  upkeep.py plan driver --to VERSION  preflight and the exact ordered steps to move the NVIDIA driver to VERSION (two apt transactions)
  upkeep.py check-sim [FILE|-] [--to V] [--pin | --rollback-from SNAPSHOT]
                                      read a saved `apt install -s` (a file, or the owner's pipe) and say ok / not ok, with reasons
  upkeep.py verify --to V [--installed]  after the install (--installed: packages, pin, dkms) or after the reboot (also driver, gate, selfcheck)
  upkeep.py rollback [SNAPSHOT]       the exact commands to go back to a snapshot (two apt transactions again)
  upkeep.py snapshot [--list]         record the installed versions (nvidia*, gpu-unlock*, pin, kernels, dkms, /boot) to a JSON
  upkeep.py busy on|off|status        the operator's busy switch of the gate: it refuses new wakes while it is on
  upkeep.py idle                      is the gate idle (no service running, no lease, no bench, nobody using the card)?
  upkeep.py log [-n N] [--json] [--history] [--add STEP --result R [--note T] [--ref REF]]   the append-only audit log (--history: the changes, before/after)

The NVIDIA card as a whole (UPKEEP.md, "GPU card management"):
  upkeep.py plan profile [RESULTS] [--run ID]   a bench_gate result -> power caps (power_profiles.conf) and VRAM needs (gate.py SERVICES): diff first,
                                      then --apply --confirm ID: backup of both files, write, gate restart by the rules, check, log before/after
  upkeep.py plan deploy --from-ref REF | --from-dir DIR   a new gpu-host tree over the deployed copy, full backup, host data left alone, md5, gate restart rules
  upkeep.py plan kernel [--to RELEASE]  print-only kernel update: nvidia and gpu-unlock built by DKMS for the new kernel BEFORE the restart
  upkeep.py unlock [--run] [--kernel R]   ok / degraded / unknown: packages, DKMS per kernel, the selfcheck result, upstream versions, re-bench due?
  upkeep.py undo [CHANGE_ID] [--apply]  list the changes that have a backup, or restore one exactly (md5 checked), same gate rules
  upkeep.py check-sim --kernel [--to RELEASE]   judge the simulation of a kernel update (image with its headers, nothing removed)

Default is print-only. `--apply` exists only for what needs no root: busy on/off, snapshot, verify's selfcheck and busy handling, the
log lines, and the card changes above (files of the gpu-host copy the gate runs from, with a backup, and the restart of the gate's USER unit). A step that needs root (apt, reboot) is PRINTED for the owner, never executed: the only programs this tool runs are the
read-only ones below (dpkg-query, apt-cache pkgnames|madison|policy, apt-mark showmanual, dkms status, uname, nvidia-smi: the whole
argument list is checked, not only the first two words; plus read-only `git rev-parse` and `git archive` of gpu-host/ in this checkout) and, for
the card changes, the ONE command that changes anything: `systemctl --user restart bridgeai-gate.service` (Sys.act; not root). For `verify --apply`, gpu_selfcheck.py (a script of this repository that starts
its own throwaway docker probe through the gate's bench: not apt, dpkg or dkms, but not "no program at all" either). Anything else is
refused by Sys.cmd before it starts.

Safety nets (UPKEEP.md has the detail): the tool never replaces or deletes a symlink, writes through O_EXCL temp files, has no default destination inside this checkout
(`--dest` must be spelled out there), stops a selfcheck at 240 s and leaves a marker (verify-in-progress.json) that the NEXT call of any kind uses to close the gate
again after a SIGKILL, takes one apply at a time (apply.lock) and keeps the newest UPKEEP_KEEP_BACKUPS (20) backups.

Why two transactions: apt reads /etc/apt/preferences.d (the pin of the installed driver) at the START of a transaction. Installing the
new pin and the driver packages in one `apt install` keeps the old driver ("is already the newest version"). So the pin is swapped alone
first, then the driver packages are installed. check-sim recognises the failed one-transaction output (pin not swapped).

State (mode 700, files 600): $UPKEEP_STATE_DIR or ~/.local/state/bridgeai-upkeep/: snapshots/ID.json and audit.jsonl. The gate's token is
read from host.env like the other host tools (bench_gate.load_host_env) and is never printed. Set UPKEEP_STATE_DIR to the same directory for
every account that uses this tool (the owner, the bot's account): a snapshot or a log kept in another account's home cannot be found.
Exit codes: 0 ok, 1 not ok / failed / degraded, 2 usage, a file that cannot be read, or could not tell.
"""
import argparse
import ast
import configparser
import contextlib
import difflib
import errno
import fcntl
import fnmatch
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import secrets
import stat
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GPU = os.path.dirname(HERE)
UP = "python3 gpu-host/upkeep/upkeep.py"                    # how the steps spell this tool (from the repository root: every plan says so first)
CHECKOUT = os.path.dirname(GPU)                             # the repository root, printed in the "run from the checkout" header


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DW = _load(os.path.join(GPU, "driver_watch.py"), "upkeep_driver_watch")      # parsers of dpkg, apt-cache, dkms status (one place)
SC = _load(os.path.join(GPU, "gpu_selfcheck.py"), "upkeep_selfcheck")        # host.env, gate client, state dir
BG = SC.BG

PIN_RE = re.compile(r"^nvidia-driver-pinning-")
UNLOCK_RE = re.compile(r"^gpu-unlock")
CONTAINER_RE = re.compile(r"^(nvidia-container|libnvidia-container)")
FAMILY_RE = re.compile(r"^(nvidia|libnvidia|firmware-nvidia|xserver-xorg-video-nvidia|cuda-drivers|libcuda1|libnvcuvid1|libgles-nvidia|libegl-nvidia|libglx-nvidia)")
# The snapshot covers the whole driver family (so a rollback can put every package back), gpu-unlock and the container packages.
SNAPSHOT_RE = re.compile("(?:" + FAMILY_RE.pattern + "|^gpu-unlock|" + CONTAINER_RE.pattern + ")")
TOOLKIT = "nvidia-container-toolkit"
# What a driver update must never remove (the old pin is replaced on purpose and is not here). The running kernel's image and headers are
# added at run time; UPKEEP_PROTECT adds regular expressions (comma separated).
PROTECTED = [r"^gpu-unlock", r"^dkms$", r"^linux-image-amd64$", r"^linux-headers-amd64$", r"^nvidia-container-toolkit", r"^libnvidia-container",
             r"^docker-ce", r"^containerd", r"^openssh-server$", r"^systemd$", r"^sudo$"]
# What a driver update may remove: only the pin it replaces. Exceptions are the owner's call: UPKEEP_ALLOW_REMOVE (regular expressions, comma
# separated, matched on the whole package name).
SAFE_VERSION = re.compile(r"[0-9][A-Za-z0-9.+~:-]{0,63}")                    # a dpkg version that is safe inside a command line
SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9+.-]{0,99}(?::[a-z0-9-]{1,20})?")   # a dpkg package name, with an optional :arch
SAFE_PIN = re.compile(r"nvidia-driver-pinning-\d+(?:\.\d+){1,3}")
TARGET_RE = re.compile(r"\d+(?:\.\d+){1,3}")                                # a driver version typed by a person: 595.112.07
SAFE_REF = re.compile(r"[A-Za-z0-9_.+-]{1,64}")
SAFE_TEXT = re.compile(r"[A-Za-z0-9_.:/+@=-]{1,100}")                       # a measurement reference typed by a person (a bench run id, a file name)
SAFE_GITREF = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./+-]{0,99}")             # a branch, tag or commit: never a leading dash
SAFE_CHANGE = re.compile(r"[0-9]{8}T[0-9]{6}Z[x]*-(?:profile|deploy)")      # the id of a change with a backup
CONFIRM_RE = re.compile(r"[0-9a-f]{12}")
KERNEL_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.+~_-]{0,50}")      # a kernel release: 6.12.115+deb13.1-amd64
GATE_UNIT = "bridgeai-gate.service"
MAX_REASONS = 8                                                # reasons and notes are capped; the count is always printed
BOOT_MARGIN = 1.5                                            # the initramfs of every kernel is rebuilt by DKMS: room for one more copy and a half
BOOT_MIN_MB = 200


class Refused(Exception):
    pass


class Sys:
    """The only way this tool runs a program: a short allowlist. `cmd` runs read-only programs; `act` runs the ONE command that changes
    anything (the restart of the gate's user unit: not root). A root command cannot be started from here."""
    NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9+.:@-]{0,99}")
    EXACT = {("dpkg-query", "-W", "-f=${db:Status-Abbrev}|${binary:Package}|${Version}\n"), ("apt-mark", "showmanual"), ("dkms", "status"), ("uname", "-r"),
             ("nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader")}
    WITH_NAME = {("apt-cache", "pkgnames"), ("apt-cache", "madison"), ("apt-cache", "policy")}    # plus exactly one package name or prefix
    ACT = {("systemctl", "--user", "restart", "bridgeai-gate.service")}
    COMMIT = re.compile(r"[0-9a-f]{40,64}")

    def __init__(self, checkout=None):
        self.checkout = checkout or CHECKOUT

    FSMONITOR_OFF = ("-c", "core.fsmonitor=false")   # `git status` runs the program a repository's core.fsmonitor names: every git call here switches that off

    def git_prefix(self):
        return ("git",) + self.FSMONITOR_OFF + ("-C", self.checkout)

    def git_allowed(self, t):
        """git, read-only, in this repository only: resolve a ref to a commit, and archive gpu-host/ of that commit to stdout."""
        pre = self.git_prefix()
        if t[:len(pre)] != pre:
            return False
        rest = t[len(pre):]
        if len(rest) == 4 and rest[:3] == ("rev-parse", "--verify", "--quiet") and rest[3].endswith("^{commit}"):
            ref = rest[3][:-len("^{commit}")]
            return bool(SAFE_GITREF.fullmatch(ref)) and ".." not in ref
        if rest == ("status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "gpu-host"):          # which files of gpu-host/ have uncommitted changes
            return True
        return len(rest) == 4 and rest[:2] == ("archive", "--format=tar") and bool(self.COMMIT.fullmatch(rest[2])) and rest[3] == "gpu-host"

    def allowed(self, argv):
        """The WHOLE argument list is judged: `nvidia-smi --query-gpu=driver_version -pl 100` is not on the list."""
        t = tuple(argv)
        return (t in self.EXACT or (len(t) == 3 and t[:2] in self.WITH_NAME and bool(self.NAME.fullmatch(t[2])))
                or (len(t) > 5 and t[0] == "git" and self.git_allowed(t)))

    def _run(self, argv, timeout, raw=False):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}              # a hook's GIT_DIR must not redirect git
        env["GIT_OPTIONAL_LOCKS"] = "0"                                                      # `git status` must not even refresh the index
        try:
            r = subprocess.run(argv, capture_output=True, text=not raw, timeout=timeout, env=env)
            return r.returncode, r.stdout
        except FileNotFoundError:
            return 127, (b"" if raw else "")
        except subprocess.TimeoutExpired:
            return 124, (b"" if raw else "")

    def cmd(self, argv, timeout=30, raw=False):
        if not argv or not self.allowed(argv):
            raise Refused("upkeep never runs: " + " ".join(argv[:2]))
        return self._run(argv, timeout, raw)

    def act(self, argv, timeout=60):
        """Only the exact restart of the gate's user unit. Everything else is refused."""
        if tuple(argv) not in self.ACT:
            raise Refused("upkeep never runs: " + " ".join(argv[:2]))
        return self._run(argv, timeout)


def strip_arch(name):
    return name.split(":")[0]


def is_family(name):
    n = strip_arch(name)
    return bool(FAMILY_RE.match(n)) and not (PIN_RE.match(n) or UNLOCK_RE.match(n) or CONTAINER_RE.match(n))


def ver(v):
    return DW.clean_version(v)


def pkg_ver(installed, name):
    """The installed version of a package by any of its spellings: dpkg-query prints `libcuda1:amd64` where apt-mark prints `libcuda1`."""
    for k in (name, strip_arch(name), strip_arch(name) + ":amd64"):
        if k in installed:
            return installed[k]
    return None


def kernel_key(release):
    return [int(x) for x in re.findall(r"\d+", release)]


# ------------------------------------------------------------------------------------------------------------------ state and log
def state_dir(env=None):
    return (env or os.environ).get("UPKEEP_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".local", "state", "bridgeai-upkeep")


def private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def open_regular(path, mode="r", **kw):
    """open() for a file this tool reads from a place others can write to (state directory, a destination, a results file): a regular file only. A fifo, a
    device or a socket there would hang the tool (or block it forever on a read), so the file is opened O_NONBLOCK and its type checked on the descriptor.
    A symlink to a regular file is followed (the callers that must not follow one look at the link first); anything else is OSError(EINVAL)."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", path)
        return os.fdopen(fd, mode, **kw)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def special_file(path):
    """True when `path` exists (not through a symlink) and is not a regular file: a fifo, a device, a socket or a directory."""
    try:
        return not stat.S_ISREG(os.lstat(path).st_mode) and not stat.S_ISLNK(os.lstat(path).st_mode)
    except OSError:
        return False


TEST_MARKER_NAME = "upkeep-selftest.marker"
TEST_MARKER_MAGIC = "upkeep-selftest-marker v1"


def test_mode(env):
    """True only inside upkeep_selftest.py. UPKEEP_TEST must name a marker file that only the selftest creates: a regular file called upkeep-selftest.marker,
    owned by this user, mode 600, in a directory made under the temp directory, holding the magic line. `UPKEEP_TEST=1` is NOT enough, so an environment
    variable alone (typed in front of a command) never turns the test overrides on (another script for the selfcheck, another checkout for git)."""
    v = (env or {}).get("UPKEEP_TEST")
    if not v or not os.path.isabs(v) or os.path.basename(v) != TEST_MARKER_NAME:
        return False
    try:
        st = os.lstat(v)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077 or abs(time.time() - st.st_mtime) > 6 * 3600:
            return False                                       # (not a file the selftest made a moment ago)
        parent = os.path.realpath(os.path.dirname(v))
        if os.path.commonpath([parent, os.path.realpath(tempfile.gettempdir())]) != os.path.realpath(tempfile.gettempdir()):
            return False
        with open_regular(v, encoding="utf-8") as f:
            return f.read(200).strip() == TEST_MARKER_MAGIC
    except (OSError, ValueError):
        return False


def write_private(path, text):
    private_dir(os.path.dirname(path))
    atomic_write(path, text.encode("utf-8"), 0o600)


EXTRA_KEYS = ("what", "before", "after", "ref", "rollback")


def append_log(sd, step, result, versions=None, note=None, **extra):
    """One JSON line, append-only: step, result, versions, time. The file is created 600. A change adds what it did (`what`), the state
    before and after (`before`, `after`: versions or file md5s), the measurement it rests on (`ref`) and the command that undoes it (`rollback`)."""
    private_dir(sd)
    path = os.path.join(sd, "audit.jsonl")
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ts": int(time.time()), "step": step, "result": result}
    if versions:
        entry["versions"] = versions
    if note:
        entry["note"] = note
    entry.update({k: x for k, x in extra.items() if k in EXTRA_KEYS and x})
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)      # a fifo as audit.jsonl: ENXIO, not a hang
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise OSError(errno.EINVAL, "the audit log is not a regular file", path)
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    os.chmod(path, 0o600)
    return entry


def read_log(sd):
    out = []
    try:
        with open_regular(os.path.join(sd, "audit.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict):                                   # a line that is a list, a number or a string is not an entry
                    out.append(d)
    except OSError:
        pass
    return out


def list_snapshots(sd):
    d = os.path.join(sd, "snapshots")
    try:
        return sorted(n[:-5] for n in os.listdir(d) if n.endswith(".json"))
    except OSError:
        return []


def load_snapshot(sd, ref=None):
    ids = list_snapshots(sd)
    if ref and os.path.isfile(ref):
        path = ref
    else:
        if ref and ref not in ids:
            return None
        if not ids:
            return None
        path = os.path.join(sd, "snapshots", (ref or ids[-1]) + ".json")
    try:
        with open_regular(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def pick_snapshot(sd, avoid=None, fallback_newest=False):
    """(id, snapshot) of the newest snapshot whose driver is NOT `avoid` (the version the host runs now or just went to): the state before the
    update. None when there is none (or, with fallback_newest, the newest one whatever it holds)."""
    ids = list_snapshots(sd)
    for i in reversed(ids):
        d = load_snapshot(sd, i)
        if d and (not avoid or ver(str(d.get("driver") or "")) != ver(avoid)):
            return i, d
    if fallback_newest and ids:
        d = load_snapshot(sd, ids[-1])
        return (ids[-1], d) if d else None
    return None


# ------------------------------------------------------------------------------------------------------------------ facts
def facts(S):
    """What the host has now, read-only. Everything the plan, the snapshot and verify need."""
    rc, out = S.cmd(["dpkg-query", "-W", "-f=${db:Status-Abbrev}|${binary:Package}|${Version}\n"])
    allpk = DW.parse_dpkg_installed(out)
    rc, smi = S.cmd(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], 15)
    driver = ver((smi.strip().splitlines() or [""])[0]) if rc == 0 else None
    kernels = DW.kernels_from_packages(allpk)
    headers = {p[len("linux-headers-"):] for p in allpk if re.match(r"^linux-headers-\d", p)}
    rc, un = S.cmd(["uname", "-r"])
    manual = S.cmd(["apt-mark", "showmanual"])[1].split()
    rows = DW.parse_dkms_status(S.cmd(["dkms", "status"])[1])
    return {"driver": driver, "installed": allpk, "kernels": kernels, "headers": headers, "running": un.strip() if rc == 0 else None,
            "manual": manual, "dkms": rows}


def driver_set(f):
    """The driver packages to install together: the manually installed ones of the driver family, as driver_watch does (not the pin, not
    gpu-unlock, not the container toolkit, which has its own version). Names keep their :arch qualifier."""
    return sorted(p for p in f["manual"] if is_family(p))


def pins(f):
    return sorted(p for p in f["installed"] if PIN_RE.match(p))


def snapshot_of(f, boot_free_mb):
    pk = {p: v for p, v in sorted(f["installed"].items()) if SNAPSHOT_RE.match(strip_arch(p))}      # the whole driver family, gpu-unlock, container packages, pin
    return {"schema": 1, "at": int(time.time()), "driver": f["driver"], "pins": pins(f), "packages": pk,
            "driver_set": driver_set(f), "toolkit": pkg_ver(f["installed"], TOOLKIT),
            "running_kernel": f["running"], "kernels": f["kernels"],
            "kernel_packages": {p: v for p, v in sorted(f["installed"].items()) if re.match(r"^linux-(image|headers)-\d", p)},
            "dkms": [{"module": m, "version": v, "kernel": k, "status": s} for m, v, k, s in f["dkms"]], "boot_free_mb": boot_free_mb}


def boot_info(env):
    """(free MB, MB needed). Needed: the biggest initrd in /boot times BOOT_MARGIN, at least BOOT_MIN_MB (UPKEEP_BOOT_MIN_MB overrides)."""
    d = env.get("UPKEEP_BOOT_DIR") or "/boot"
    try:
        st = os.statvfs(d)
        free = int(st.f_frsize * st.f_bavail // 2**20)
    except OSError:
        return None, None
    big = 0
    try:
        for n in os.listdir(d):
            if n.startswith("initrd.img"):
                big = max(big, os.path.getsize(os.path.join(d, n)))
    except OSError:
        pass
    floor = int(env.get("UPKEEP_BOOT_MIN_MB") or BOOT_MIN_MB)
    return free, max(floor, int(big * BOOT_MARGIN // 2**20))


# ------------------------------------------------------------------------------------------------------------------ the gate
class GateView:
    def __init__(self, env):
        self.env, self.err, self.state = env, None, None
        token = env.get("GATE_TOKEN")
        if not token:
            self.err = "no_gate_token: GATE_TOKEN is not in host.env or the environment (the token is never printed)"
            return
        gate = BG.Gate(f"http://127.0.0.1:{env.get('GATE_PORT', '8700')}", token, timeout=10)
        try:
            code, obj = gate.call("GET", "/state")
        except BG.GateError as e:
            self.err = str(e)
            return
        if code != 200:
            self.err = f"gate answered {code} to GET /state (wrong GATE_TOKEN?)"
            return
        self.state = obj

    def busy_services(self):
        s = (self.state or {}).get("services") or {}
        return sorted(n for n, v in s.items() if isinstance(v, dict) and (v.get("running") or v.get("leases")))

    def idle(self, busy_file_on=False):
        """(idle?, reason). Idle: no service running or leased, no bench, nobody blocking the card (a VR session, a game, Resolve)."""
        if self.state is None:
            return False, self.err
        why = []
        run = self.busy_services()
        if run:
            why.append("running or leased: " + ", ".join(run) + " (they stop by themselves after their idle time; nothing is cut)")
        if self.state.get("bench"):
            why.append("a bench or selfcheck is running")
        blocked = self.state.get("blocked")
        if blocked == "vr":
            why.append("a person is using the card (VR, a game or Resolve): wait, or tell them first")
        if busy_file_on and blocked != "busy" and blocked != "vr":
            why.append("the busy switch file exists but the gate does not report blocked=busy: GATE_STATE_DIR differs from the gate's")
        return not why, "; ".join(why) or "no service running, no lease, no bench, nobody on the card"


def busy_path(env):
    return os.path.join(SC.state_dir_of(env), "busy")


def set_busy(env, on):
    p = busy_path(env)
    if on:
        os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
        os.close(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_NONBLOCK, 0o666 & ~0o022))
    else:
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass


# The "verify in progress" marker. A verify (or `unlock --run --apply`) lifts the busy switch for the length of the selfcheck. A crash, Ctrl-C or
# SIGTERM puts it back (a finally); a SIGKILL (hostcare's `run` kills at its timeout) cannot. So the marker is written BEFORE the switch is lifted and
# removed only after it is back: any later upkeep call that finds a marker whose process is gone (or too old) closes the gate again.
VERIFY_MARKER = "verify-in-progress.json"
SELFCHECK_TIMEOUT_S = 240                                    # a hard stop of the selfcheck, below hostcare's `run` maximum of 300 s
SELFCHECK_TIMEOUT_MAX = 280                                  # UPKEEP_SELFCHECK_TIMEOUT_S can only lower it (down to 5 s), never go past this


def selfcheck_timeout(env):
    try:
        t = float(env.get("UPKEEP_SELFCHECK_TIMEOUT_S") or SELFCHECK_TIMEOUT_S)
    except ValueError:
        t = SELFCHECK_TIMEOUT_S
    return min(max(t, 5.0), float(SELFCHECK_TIMEOUT_MAX)) if math.isfinite(t) else float(SELFCHECK_TIMEOUT_S)


def marker_path(sd):
    return os.path.join(sd, VERIFY_MARKER)


def write_marker(sd, step, child=None, script=None):
    write_private(marker_path(sd), json.dumps({"at": int(time.time()), "pid": os.getpid(), "step": step, "child": child, "script": script}) + "\n")


def clear_marker(sd):
    """Remove the marker. 'removed' (or it was already gone), 'stale' when it could not be removed (a directory, a read-only state directory) and was renamed
    to verify-in-progress.json.stale so it is not recovered again at every call, or None when neither worked."""
    path = marker_path(sd)
    try:
        os.unlink(path)
        return "removed"
    except FileNotFoundError:
        return "removed"
    except OSError:
        pass
    side = path + ".stale"
    try:
        if os.path.isdir(side) and not os.path.islink(side):
            shutil.rmtree(side)
        elif os.path.lexists(side):
            os.unlink(side)
        os.rename(path, side)
        return "stale"
    except OSError:
        return None


def _cmdline(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read(4096).replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return None


def marker_is_stale(m):
    """True when the process that wrote the marker is gone (or the marker is older than any selfcheck can last, or unreadable)."""
    pid, at = m.get("pid"), m.get("at")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or not isinstance(at, (int, float)):
        return True
    if time.time() - at > SELFCHECK_TIMEOUT_MAX + 120:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        pass
    cl = _cmdline(pid)
    return cl is not None and "upkeep" not in cl             # the pid was reused by another program


def selfcheck_script(env):
    """The selfcheck this tool starts, computed here and never read from the marker (a marker is a file in a shared state directory): the repository's own
    gpu_selfcheck.py, or inside the selftest (test_mode) the one UPKEEP_SELFCHECK names."""
    if test_mode(env) and env.get("UPKEEP_SELFCHECK"):
        return env["UPKEEP_SELFCHECK"]
    return os.path.join(GPU, "gpu_selfcheck.py")


def own_selfcheck_group(child, env):
    """True only when `child` is the selfcheck this tool started: a process of this user, leader of its own process group (start_new_session), whose command
    line has the selfcheck path as one of its arguments. Nothing the marker says about the script is trusted."""
    if not isinstance(child, int) or isinstance(child, bool) or child <= 1 or child in (os.getpid(), os.getpgrp()):
        return False
    try:
        if os.stat(f"/proc/{child}").st_uid != os.getuid() or os.getpgid(child) != child:
            return False
        with open(f"/proc/{child}/cmdline", "rb") as f:
            argv = f.read(8192).split(b"\0")
    except OSError:
        return False
    return os.fsencode(selfcheck_script(env)) in argv


def recover_verify(env, sd):
    """[lines]: when a marker is left behind by a verify that did not finish, close the gate again (busy on), stop its orphaned selfcheck, log it and
    remove the marker. Every upkeep call does this first, so a killed verify never leaves the gate open on an unverified driver."""
    path = marker_path(sd)
    if not os.path.lexists(path):
        return []
    try:
        with open_regular(path, encoding="utf-8") as f:     # a fifo or a directory here is "unreadable", never a hang
            m = json.load(f)
        m = m if isinstance(m, dict) else None
    except (OSError, ValueError):
        m = None
    if m is None:
        m = {}                                               # present but unreadable: stale
    elif not marker_is_stale(m):
        return []                                            # another upkeep process is verifying right now
    child = m.get("child")
    stopped = ""
    if own_selfcheck_group(child, env):                      # the selfcheck this tool started is still running: stop it (the marker's `script` is ignored)
        try:
            os.killpg(child, signal.SIGTERM)
            stopped = " and its orphaned selfcheck was stopped"
        except OSError:
            pass
    set_busy(env, True)
    cleared = clear_marker(sd)
    extra = ""
    if cleared == "stale":
        extra = f" The marker could not be removed; it was renamed to {VERIFY_MARKER}.stale (look at it, then delete it by hand)."
    elif cleared is None:
        extra = f" The marker {marker_path(sd)} could not be removed or renamed: delete it by hand, or every call will say this again."
    step = m.get("step") if isinstance(m.get("step"), str) and SAFE_REF.fullmatch(m.get("step")) else "verify"
    try:
        append_log(sd, "verify-recovered", "closed", what=f"a {step} run ended without a verdict (killed or crashed): the gate was closed again (busy on)" + stopped
                   + (" (marker not removable)" if cleared is None else " (marker renamed to .stale)" if cleared == "stale" else ""),
                   rollback=f"{UP} verify --to VERSION --apply (when the card is free)")
    except OSError as e:
        extra += f" The audit log could not be written ({e.strerror or type(e).__name__}); the gate is closed all the same."
    return [f"upkeep: RECOVERED: a {step} run ended without a verdict (it was killed or crashed, so the busy switch could not be put back). The gate is CLOSED again (busy on){stopped}. "
            f"Run the verify again when the card is free; open the gate only with a verdict ok.{extra}"]


# ------------------------------------------------------------------------------------------------------------------ check-sim
INST = re.compile(r"^Inst (\S+)(?: \[([^\]]+)\])? \((\S+)")
REMV = re.compile(r"^Remv (\S+)")
ALREADY = re.compile(r"^(\S+) is already the newest version \(([^)]+)\)")
BLOCK = re.compile(r"^(The following packages will be REMOVED:|Removing:|The following packages have been kept back:|Not upgrading:|Not Upgrading:)\s*$", re.I)
APT_ERROR = re.compile(r"^(E: .*|The following packages have unmet dependencies:.*)$")


def parse_sim(text):
    """{inst: [(name, old, new)], remv, already: [(name, version)], kept, errors} of an `apt install -s` output (apt 2 and 3 formats).
    A pasted or quoted copy still reads: a leading `> ` quote mark and any indentation of the whole paste are ignored."""
    inst, remv, already, kept, errors = [], [], [], [], []
    lines = [re.sub(r"^(?:\s*>)+ ?", "", l) for l in text.splitlines()]
    for i, raw in enumerate(lines):
        line = raw.lstrip()
        indent = len(raw) - len(line)
        m = INST.match(line)
        if m:
            inst.append((m.group(1), m.group(2), m.group(3)))
            continue
        m = REMV.match(line)
        if m:
            remv.append(m.group(1))
            continue
        m = ALREADY.match(line)
        if m:
            already.append((m.group(1), m.group(2)))
            continue
        m = APT_ERROR.match(line)
        if m:
            errors.append(m.group(1)[:120])
            continue
        m = BLOCK.match(line)
        if m:
            into = remv if re.search(r"remov", m.group(1), re.I) else kept
            for nxt in lines[i + 1:]:
                if not nxt.strip() or len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                into.extend(t.rstrip("*") for t in nxt.split() if not t.startswith("("))
    return {"inst": inst, "remv": sorted(set(remv)), "already": already, "kept": sorted(set(kept)), "errors": errors}


def _cap(items, what):
    """At most MAX_REASONS lines, then one line with the count of the rest."""
    if len(items) <= MAX_REASONS:
        return items
    return items[:MAX_REASONS] + [f"... and {len(items) - MAX_REASONS} more {what} (not listed)"]


def _finish(target, reasons, notes, upgraded):
    return {"ok": not reasons, "target": target, "reasons": _cap(reasons, "reasons"), "notes": _cap(notes, "notes"), "upgraded": upgraded}


def allow_patterns(env_value):
    """Compiled UPKEEP_ALLOW_REMOVE (comma separated regular expressions); a bad one is dropped, never a crash."""
    out = []
    for x in (env_value or "").split(","):
        if x.strip():
            try:
                out.append(re.compile(x.strip()))
            except re.error:
                pass
    return out


def check_pin_sim(text, target):
    """Judge the simulation of TRANSACTION 1 (the pin alone, plus the container toolkit). Pure. Allowed: the new pin installed, an older pin
    removed, container packages upgraded. Anything else (a driver package, any other removal, an apt error) is not ok."""
    s = parse_sim(text)
    reasons, notes = [], []
    if not target:
        reasons.append("cannot judge the pin step without --to VERSION")
    pins_in = [n for n, _o, _v in s["inst"] if PIN_RE.match(n)]
    if target and f"nvidia-driver-pinning-{target}" not in pins_in:
        reasons.append(f"this simulation does not install nvidia-driver-pinning-{target}")
    for n, _o, _v in s["inst"]:
        if PIN_RE.match(n) or CONTAINER_RE.match(strip_arch(n)):
            continue
        reasons.append(f"{n} is installed or upgraded in the pin transaction: only the pin and the container toolkit may be in it")
    for n in s["remv"]:
        if PIN_RE.match(strip_arch(n)) and ver(strip_arch(n)[len("nvidia-driver-pinning-"):]) != target:
            notes.append(f"the old pin {n} is replaced (expected)")
        else:
            reasons.append(f"removes {n}: the pin transaction removes only the old pin")
    reasons += [f"apt reports: {e}" for e in s["errors"]]
    if not reasons:
        notes.append("pin step is clean: next, simulate the driver packages")
    return _finish(target, reasons, notes, 0)


def check_sim(text, target=None, installed=None, running=None, extra_protect=(), expect=None, allow_remove=(), rollback_allow=None):
    """Judge an `apt install -s` output for the driver step. Returns {ok, target, reasons, notes, upgraded}. Pure.
    target: the driver version it must reach (inferred from the new pin or the driver packages when not given).
    installed: the driver version now (inferred from the old pin that is removed, or the most common old version, when not given).
    expect: the driver packages the plan installs; every one must appear (installed or already at the target), else not ok.
    allow_remove: compiled regexes of removals the owner accepts. rollback_allow: for a rollback, the package names of the snapshot; a
    driver package that is NOT in it (it came with the update) may be removed.
    A driver update removes nothing but the old pin: any other removal is not ok."""
    s = parse_sim(text)
    reasons, notes = [], []
    pin_inst = [n for n, _o, _v in s["inst"] if PIN_RE.match(n)]
    if not target:
        pv = [ver(n[len("nvidia-driver-pinning-"):]) for n in pin_inst]
        if pv:
            target = pv[-1]
        else:
            news = sorted((ver(v) for n, _o, v in s["inst"] if is_family(n) and ver(v)), key=DW.vtuple)
            target = news[-1] if news else None
    pin_removed = [ver(strip_arch(n)[len("nvidia-driver-pinning-"):]) for n in s["remv"] if PIN_RE.match(strip_arch(n))]
    old = installed or (pin_removed[0] if pin_removed else None)
    if not old:
        olds = [ver(o) for n, o, _v in s["inst"] if is_family(n) and o and ver(o)] + [ver(v) for n, v in s["already"] if is_family(n) and ver(v)]
        old = max(set(olds), key=olds.count) if olds else None

    olds_known = {x for x in (installed, old, pin_removed[0] if pin_removed else None) if x}

    def tied(oldv):
        """A driver-family package with its own version (a toolkit, a cudnn) is not judged: only the ones that carry the driver version."""
        return not olds_known or ver(oldv) in olds_known or ver(oldv) == target

    if not target:
        reasons.append("cannot tell which driver version this should reach: pass --to VERSION")
    reasons += [f"apt reports: {e}" for e in s["errors"]]
    goes = [(n, ver(v)) for n, o, v in s["inst"] if is_family(n) and (o is None or tied(o))]
    stuck = [(n, ver(v)) for n, v in s["already"] if is_family(n) and ver(v) != target and tied(v)]
    if target and stuck:
        names = ", ".join(f"{n} ({v})" for n, v in stuck[:4]) + (" ..." if len(stuck) > 4 else "")
        if any(ver(n[len("nvidia-driver-pinning-"):]) == target for n in pin_inst):
            reasons.append(f"pin not swapped: the new pin and the driver packages are in ONE transaction, and apt read the OLD pin at its start, so "
                           f"{names} stay at the old version (\"already the newest version\"). Install nvidia-driver-pinning-{target} ALONE first, then simulate the driver packages")
        else:
            reasons.append(f"pin not swapped yet: {names} \"already the newest version\" at the old driver, so the installed pin still holds them. "
                           f"Install nvidia-driver-pinning-{target} alone first, then simulate again")
    wrong = [f"{n} goes to {v}" for n, v in goes if target and v != target]
    if wrong:
        reasons.append(f"{len(wrong)} driver package(s) do not go to the target " + target + ": " + "; ".join(wrong[:6]) + (" ..." if len(wrong) > 6 else ""))
    for n in s["kept"]:
        if is_family(n):
            reasons.append(f"{n} is kept back at the old version")
    if expect and (goes or stuck):                                 # a pin-only or empty simulation gets its own, clearer reason below
        have = {n for n, _o, _v in s["inst"]} | {n for n, v in s["already"] if ver(v) == target}
        bare = {strip_arch(n) for n in have}
        missing = [p for p in expect if p not in have and (":" in p or p not in bare)]
        if missing:
            reasons.append(f"the simulation does not cover {len(missing)} of the {len(expect)} driver package(s) the plan installs: "
                           + " ".join(missing[:6]) + (" ..." if len(missing) > 6 else "") + " (is the whole list in the simulated command?)")
    prot = [re.compile(p) for p in PROTECTED + list(extra_protect)]
    if running:
        prot += [re.compile("^linux-image-" + re.escape(running) + "$"), re.compile("^linux-headers-" + re.escape(running) + "$")]
    for n in s["remv"]:
        b = strip_arch(n)
        if any(p.match(b) for p in prot):
            reasons.append(f"removes a protected package: {n}")
        elif PIN_RE.match(b):
            if ver(b[len("nvidia-driver-pinning-"):]) == target:
                reasons.append(f"removes the pin of the target itself: {n}")
            else:
                notes.append(f"the old pin {n} is replaced (expected)")
        elif rollback_allow is not None and is_family(n) and b not in rollback_allow:
            notes.append(f"{n} came with the update (it is not in the snapshot): removed by the rollback")
        elif any(p.fullmatch(b) for p in allow_remove):
            notes.append(f"removes {n}: allowed by UPKEEP_ALLOW_REMOVE")
        elif is_family(n):
            reasons.append(f"removes a driver package: {n}")
        else:
            reasons.append(f"removes {n}: a driver update removes nothing but the old pin (UPKEEP_ALLOW_REMOVE lists exceptions)")
    oth = other_installs(s)
    kern = sorted(n for n, _v in oth if KERNEL_PKG_RE.match(strip_arch(n)) or re.match(r"^linux-(image|headers)-amd64$", strip_arch(n)))
    if kern:
        reasons.append(f"this driver update also installs or upgrades {len(kern)} kernel package(s) ({_list_pkgs(kern, 4)}): a new kernel makes DKMS rebuild and fills /boot. "
                       f"Do the kernel update separately (`plan kernel`), then the driver")
    rest = sorted(n for n, _v in oth if n not in kern)
    if rest:
        notes.append(f"also installs or upgrades {len(rest)} other package(s) that are not the driver: {_list_pkgs(rest)}")
    if target and not goes and not stuck and not reasons:
        if pin_inst:
            reasons.append("this installs only the pin: it is the pin step, not the driver step. Install the pin alone, then simulate the driver packages")
        else:
            reasons.append("no driver package is installed or upgraded by this simulation")
    if not reasons:
        notes.append(f"{len(goes)} driver package(s) go to {target}")
        if any(n.startswith("firmware-nvidia") for n, _v in goes):
            notes.append("firmware-nvidia-gsp is upgraded too: gpu-unlock-firmware was only checked with the old driver; the selfcheck after the reboot decides")
    return _finish(target, reasons, notes, len(goes))


def other_installs(s):
    """[(name, new version)] of the Inst lines that are not the driver family, the pin or the container packages."""
    return [(n, v) for n, _o, v in s["inst"] if not is_family(n) and not PIN_RE.match(strip_arch(n)) and not CONTAINER_RE.match(strip_arch(n))]


KERNEL_PKG_RE = re.compile(r"^linux-(image|headers|kbuild|compiler)-")


def _list_pkgs(names, n=6):
    return ", ".join(names[:n]) + (f" ... (+{len(names) - n})" if len(names) > n else "")


def render_sim(r):
    """The first line is the one-line verdict the owner may paste to the bot: `check-sim: ok (target V)` or `check-sim: not ok (target V)`."""
    out = ["check-sim: " + ("ok" if r["ok"] else "not ok") + (f" (target {r['target']})" if r["target"] else "")]
    out += [("  reason: " if not r["ok"] else "  ") + x for x in r["reasons"]]
    out += ["  note: " + x for x in r["notes"]]
    if r["ok"]:
        out.append("  next: apply it for real (the same command without -s), then verify --installed")
    else:
        out.append("  do NOT apply this: fix the cause above and simulate again")
    return out


# ------------------------------------------------------------------------------------------------------------------ steps
def policy_versions(S, pkg):
    t = S.cmd(["apt-cache", "policy", pkg])[1]
    m = re.search(r"^\s*Installed:\s*(\S+)", t, re.M)
    inst = None if not m or m.group(1) == "(none)" else m.group(1)
    return inst, DW.parse_policy_candidate(t)


TAGS = {"owner": "[owner, root]", "owner-nr": "[owner, no root]", "bot": "[bot, no root]"}


def fmt_steps(steps):
    out = []
    for i, (who, what, cmd, look) in enumerate(steps, 1):
        out.append(f"{i:2}. {TAGS[who]} {what}")
        for line in cmd if isinstance(cmd, list) else [cmd]:
            out.append(("      " if line.startswith("#") else "      $ ") + line)
        out.append("      look for: " + look)
    return out


def pre_lines(items):
    return [f"  {st:6} {name}: {detail}" for st, name, detail in items]


def checkout_header():
    return f"run from the bridgeai checkout: cd {shlex.quote(CHECKOUT)}   (every command below is written relative to it)"


def sim_file(sd, name):
    """Where the owner may write a simulation so that the bot can read it as a FILE (the bot never takes pasted text into a command)."""
    return os.path.join(sd, name)


def plan_driver(S, env, a, sd=None):
    """(lines, ok) of `plan driver --to TARGET`: preflight and the ordered steps. Reads only. With a NOT OK in the preflight no steps are printed:
    the one exception is a stale package list, where the next action is `sudo apt update` and then this plan again."""
    sd = sd or state_dir()
    target = a.to
    f = facts(S)
    pre = []
    cur = f["driver"]
    # versions
    if not TARGET_RE.fullmatch(target or ""):
        pre.append(("NOT OK", "target", "the target is not a driver version like 595.112.07"))
    elif not cur:
        pre.append(("NOT OK", "driver", "nvidia-smi does not answer: the installed driver is unknown"))
    elif DW.vtuple(target) == DW.vtuple(cur):
        pre.append(("NOT OK", "target", f"the host already runs {cur}: nothing to update"))
    elif DW.vtuple(target) < DW.vtuple(cur):
        pre.append(("NOT OK", "target", f"{target} is older than the installed {cur}: that is a rollback, use `{UP} rollback`"))
    else:
        pre.append(("ok", "target", f"{cur} -> {target}"))
    # the repository
    offered = DW.parse_pin_names(S.cmd(["apt-cache", "pkgnames", DW.PIN_PREFIX])[1])
    for pkg in DW.DRIVER_META:
        offered |= DW.parse_madison(S.cmd(["apt-cache", "madison", pkg])[1])
    if target in offered:
        pre.append(("ok", "repo", f"{target} is offered by the configured repository"))
    else:
        pre.append(("NOT OK", "repo", f"{target} is not in the package lists (offered: {', '.join(sorted(offered, key=DW.vtuple)[-4:]) or 'nothing'}); "
                                       "the lists may be stale: the owner runs `sudo apt update`, then this plan again"))
    # the driver packages
    dset = driver_set(f)
    unsafe = [p for p in dset if not SAFE_NAME.fullmatch(p)]
    if unsafe:
        pre.append(("NOT OK", "packages", "a package name is not dpkg-safe, not put into a command line: " + " ".join(unsafe[:3])))
    elif dset:
        pre.append(("ok", "packages", f"{len(dset)} driver package(s) installed here: {' '.join(dset)}"))
    else:
        pre.append(("NOT OK", "packages", "apt-mark showmanual lists no nvidia driver package: cannot build the install line"))
    pin_now = pins(f)
    pre.append(("ok" if len(pin_now) == 1 else "NOT OK", "pin", (pin_now[0] + " is the installed pin") if len(pin_now) == 1
                else f"expected exactly one nvidia-driver-pinning package, found {len(pin_now)}: {' '.join(pin_now) or 'none'}"))
    unlock = f["installed"].get("gpu-unlock-dkms")
    pre.append(("ok" if unlock else "note", "gpu-unlock", f"gpu-unlock-dkms {unlock} installed" if unlock else "gpu-unlock-dkms is not installed here"))
    # dkms today
    gaps = DW.dkms_gaps([k for k in f["kernels"] if k in f["headers"]], f["dkms"])
    pre.append(("ok" if not gaps else "note", "dkms now", "nvidia and gpu-unlock are built for every kernel with headers" if not gaps
                else "already missing: " + "; ".join(f"{m} for {k}" for k, m in gaps)))
    nohead = kernels_without_headers(f, boot_kernels(env))
    if nohead:
        pre.append(("note", "kernels", "installed without headers (DKMS cannot build for them; the newest one is what grub boots): " + " ".join(nohead[:4])))
    # /boot
    free, need = boot_info(env)
    if free is None:
        pre.append(("note", "/boot", "cannot read the free space"))
    else:
        pre.append(("ok" if free >= need else "NOT OK", "/boot", f"{free} MB free, {need} MB needed (DKMS rebuilds the initramfs of every kernel)"))
    # the gate
    gv = GateView(env)
    idle, why = gv.idle(os.path.exists(busy_path(env)))
    pre.append(("ok" if idle else "wait" if gv.state is not None else "NOT OK", "gate idle",
                why if idle else why + (" -- steps 1 and 2 close the gate and wait" if gv.state is not None else "")))
    pre.append(("ok" if gv.state is not None else "NOT OK", "gate", "answers GET /state" if gv.state is not None else gv.err))
    pre.append(("ok", "busy switch", "on" if os.path.exists(busy_path(env)) else "off (step 1 turns it on)"))
    # what driver_watch knows about this update
    dwr = SC.read_json(os.path.join(SC.state_dir_of(env), DW.RESULT)) or {}
    cls = dwr.get("update_class") if dwr.get("target") == target else None
    if cls == "security":
        pre.append(("note", "class", "SECURITY (driver_watch): apply fast, the selfcheck after the reboot still decides whether the unlock survived"))
    elif cls in ("performance", "unknown"):
        pre.append(("note", "class", f"{cls.upper()} (driver_watch): measure before adopting; the last step is the bench, roll back if slower or costlier"))
    else:
        pre.append(("note", "class", "no driver_watch result for this target: run `python3 gpu-host/driver_watch.py run`; treat as measure-before-adopting if unsure"))
    if dwr.get("unlock_mismatch") and dwr.get("target") == target:
        pre.append(("note", "gpu-unlock", "driver_watch says gpu-unlock-dkms declares a version requirement that excludes this driver: the owner decides"))
    ok_all = all(st != "NOT OK" for st, _n, _d in pre)
    head = [f"upkeep plan driver: {cur or '?'} -> {target}", checkout_header(), "",
            "PREFLIGHT" + ("" if ok_all else "  (NOT OK: no steps are printed until it is fixed)")]
    if not ok_all:
        bad = [n for st, n, _d in pre if st == "NOT OK"]
        if bad == ["repo"]:
            tail = ["", "NEXT (stale package lists?): [owner, root] `sudo apt update`, then run this plan again. Any other NOT OK stops the plan."]
        else:
            tail = ["", "NO STEPS: fix what is NOT OK above and run this plan again. Nothing is built from a target or a package list that failed its check."]
        return head + pre_lines(pre) + tail, False
    # the toolkit
    tk = policy_versions(S, TOOLKIT) if f["installed"].get(TOOLKIT) else (None, None)
    tk_up = bool(tk[0] and tk[1] and tk[0] != tk[1])
    pin_pkgs = f"nvidia-driver-pinning-{target}" + (f" {TOOLKIT}" if tk_up else "")
    pkgs = " ".join(dset)
    t2_flags = "--no-remove "                                   # apt itself refuses to remove anything: a driver update removes nothing but the old pin
    sim1 = f"apt install -s {pin_pkgs} 2>&1 | {UP} check-sim - --pin --to {target}"
    sim2 = f"apt install -s {t2_flags}{pkgs} 2>&1 | {UP} check-sim - --to {target}"
    sim2_file = shlex.quote(sim_file(sd, "sim-transaction-2.txt"))
    steps = [
        ("bot", "close the gate to new wakes (running services finish; nothing is lost, jobs wait or go to the next host)", f"{UP} busy on --apply", "busy: on"),
        ("bot", "wait until nothing runs on the card (repeat until it says idle)", f"{UP} idle", "idle: yes; if not, it names what still runs"),
        ("bot", "record the installed versions: the rollback source", f"{UP} snapshot --apply", "snapshot saved: <id> (nvidia*, gpu-unlock*, pin, container packages, kernels, dkms); a REFUSED snapshot means the host is not in a clean state: read why"),
        ("owner", "refresh the package lists", "sudo apt update", "no errors; the NVIDIA repo lines are fetched"),
        ("owner-nr", "simulate TRANSACTION 1 (the pin alone) and let the tool read it", sim1, "check-sim: ok. Anything but the pin and the container toolkit is not ok"),
        ("owner", f"TRANSACTION 1: install the new pin ALONE" + (f" (plus {TOOLKIT} {tk[0]} -> {tk[1]})" if tk_up else ""), f"sudo apt install {pin_pkgs}",
         f"Remv nvidia-driver-pinning-{cur or '<old>'} and Inst nvidia-driver-pinning-{target}; NO driver package in this transaction (apt reads the old pin at the start of "
         "a transaction, which is why the pin cannot share one with the driver)"),
        ("owner-nr", "simulate TRANSACTION 2 (the driver packages). Either run the pipe, or write the simulation to the file and the bot reads the FILE "
                     "(the bot never takes pasted text into a command; you may tell it the one-line verdict)",
         [sim2, f"# or: apt install -s {t2_flags}{pkgs} > {sim2_file} 2>&1   (then the bot runs: {UP} check-sim {sim2_file} --to {target})"],
         "check-sim: ok. Not ok means: do not apply (pin not swapped, a package left at the old version, a package removed, a package of the plan missing)"),
        ("owner", "TRANSACTION 2: install the driver packages (DKMS builds nvidia and gpu-unlock for every kernel that has headers; takes minutes)",
         f"sudo apt install {t2_flags}{pkgs}", "no errors; DKMS 'Installing to /lib/modules/<kernel>/updates/dkms' per kernel; gpu-unlock-dkms and gpu-unlock-firmware stay installed"),
        ("bot", "check the result before rebooting", [f"{UP} verify --to {target} --installed", "dkms status"],
         f"verify: ok; dkms status: nvidia/{target} and gpu-unlock installed for every kernel with headers (the running kernel included)"),
        ("owner", "reboot in a quiet window (the gate stays closed; the stacks use the next host meanwhile)", "sudo reboot", "the host comes back; the gate answers GET /healthz"),
        ("bot", "verify after the reboot: driver, dkms, gate, then the selfcheck of the FP32-accumulate unlock (opens the gate again only on ok; pass timeout=300 to hostcare; the selfcheck itself stops at 240 s)",
         f"{UP} verify --to {target} --apply", f"RESULT: ok -> busy off and a log line. RESULT: degraded -> it prints the rollback and keeps the gate closed"),
    ]
    if cls != "security":
        steps.append(("bot", "measure before adopting: bench the real jobs against the earlier numbers (idle window); keep the update only if nothing is slower or costlier",
                      "python3 gpu-host/bench_gate.py --recheck", "no slowdown, no extra Wh; otherwise: " + f"{UP} rollback"))
    steps.append(("bot", "if anything goes wrong at any step", f"{UP} rollback", "the commands to go back to the snapshot of step 3"))
    return head + pre_lines(pre) + ["", "STEPS (copy-paste; [owner, root] you run as root, the bot never does; [owner, no root] you run as yourself; [bot, no root] the bot runs them with --apply, or you can)"] \
        + fmt_steps(steps) + ["", "The tool never runs apt, dpkg, dkms install, a reboot or sudo. Log: " + f"{UP} log"], True


def validate_snapshot(snap):
    """[problems] of a snapshot file: its text ends up in `sudo apt install` lines, so every name and version must be dpkg-safe."""
    bad = []
    if not TARGET_RE.fullmatch(str(snap.get("driver") or "")):
        bad.append("the driver version is missing or not a version")
    pn = snap.get("pins")
    if pn is not None and not (isinstance(pn, list) and all(isinstance(x, str) and SAFE_PIN.fullmatch(x) for x in pn)):
        bad.append("the pin names are not nvidia-driver-pinning-VERSION")
    pk = snap.get("packages")
    if not isinstance(pk, dict) or not pk:
        bad.append("it has no `packages` table: the versions to go back to are unknown")
    else:
        for n, v in pk.items():
            if not (isinstance(n, str) and isinstance(v, str) and SAFE_NAME.fullmatch(n) and SAFE_VERSION.fullmatch(v)):
                bad.append(f"package {str(n)[:40]!r} or its version is not dpkg-safe")
                break
    return bad


def rollback_want(f, snap):
    """[(package, version)] to put back: the snapshot's packages (not the pins: transaction 1 does those) that differ from what is installed."""
    out = []
    for p, v in sorted((snap.get("packages") or {}).items()):
        if PIN_RE.match(strip_arch(p)):
            continue
        if pkg_ver(f["installed"], p) != v:
            out.append((p, v))
    return out


def offered_versions(S, name):
    """The exact versions `apt-cache madison NAME` lists."""
    out = set()
    for line in S.cmd(["apt-cache", "madison", strip_arch(name)])[1].splitlines():
        parts = [x.strip() for x in line.split("|")]
        if len(parts) >= 3:
            out.add(parts[1])
    return out


def rollback_lines(S, env, snap, ref_name, sd=None, all_ids=()):
    """The commands to go back to a snapshot, as two apt transactions. Reads only. No steps when the snapshot or the preflight fails."""
    sd = sd or state_dir()
    f = facts(S)
    old = snap.get("driver")
    out = [f"upkeep rollback to snapshot {str(ref_name)[:80]}: driver {str(old)[:20] if old else '?'}; now {f['driver'] or '?'}", checkout_header()]
    if len(all_ids) > 1:
        out.append("snapshots here (newest last): " + ", ".join(all_ids[-6:]) + f"   -- pick another with `{UP} rollback ID`")
    bad = validate_snapshot(snap)
    if bad:
        return out + ["  NOT OK: this snapshot cannot be used (" + "; ".join(bad) + "). No steps are printed from it. Older snapshots: " + f"{UP} snapshot --list"], False
    old_pins = snap.get("pins") or []
    pin_name = old_pins[0] if old_pins else f"nvidia-driver-pinning-{old}"
    if f["driver"] == old and pins(f) == old_pins:
        return out + [f"  nothing to roll back: the installed driver and pin already equal the snapshot's. Older snapshots: {UP} snapshot --list"], False
    want = rollback_want(f, snap)
    missing = [f"{p}={v}" for p, v in want if v not in offered_versions(S, p)]
    pre = []
    pin_offered = pin_name in {l.strip() for l in S.cmd(["apt-cache", "pkgnames", pin_name])[1].splitlines()}
    pre.append(("ok" if pin_offered else "NOT OK", "old pin in the repo", f"{pin_name} is still offered" if pin_offered
                else f"{pin_name} is not offered (stale lists? the owner runs `sudo apt update` and this is run again; transaction 1 would fail after the gate is closed)"))
    pre.append(("ok" if not missing else "NOT OK", "old versions in the repo", "every package is still offered at its old version" if not missing
                else "not offered any more: " + " ".join(missing) + " (without them the downgrade cannot download; the owner decides)"))
    sp = snap.get("packages") or {}
    new_pkgs = sorted(p for p in f["installed"] if is_family(p) and pkg_ver(sp, p) is None)
    if new_pkgs:
        pre.append(("note", "new packages", "installed since the snapshot (check-sim lets the rollback remove them): " + " ".join(new_pkgs[:8]) + (" ..." if len(new_pkgs) > 8 else "")))
    if not want:
        pre.append(("NOT OK", "packages", "no package differs from the snapshot: the line of transaction 2 would be empty"))
    free, need = boot_info(env)
    if free is not None:
        pre.append(("ok" if free >= need else "NOT OK", "/boot", f"{free} MB free, {need} MB needed"))
    gv = GateView(env)
    idle, why = gv.idle(os.path.exists(busy_path(env)))
    pre.append(("ok" if idle else "wait" if gv.state is not None else "NOT OK", "gate idle", why + ("" if idle or gv.state is None else " -- step 1 and 2 close the gate and wait")))
    ok = all(st != "NOT OK" for st, _n, _d in pre)
    out += ["", "PREFLIGHT" + ("" if ok else "  (NOT OK: no steps are printed until it is fixed)")] + pre_lines(pre)
    if not ok:
        return out + ["", "NO STEPS: fix what is NOT OK above and run this again."], False
    line2 = " ".join(f"{p}={v}" for p, v in want)
    flags = "--allow-downgrades " + ("" if new_pkgs else "--no-remove ")       # packages that came with the update may have to go: then check-sim judges, not apt
    ref_arg = shlex.quote(ref_name) if SAFE_REF.fullmatch(str(ref_name)) is None else ref_name
    steps = [
        ("bot", "close the gate to new wakes (skip if it is already on)", f"{UP} busy on --apply", "busy: on"),
        ("bot", "wait until nothing runs on the card", f"{UP} idle", "idle: yes"),
        ("owner-nr", "simulate TRANSACTION 1 (the old pin alone)", f"apt install -s {pin_name} 2>&1 | {UP} check-sim - --pin --to {old}", "check-sim: ok"),
        ("owner", "TRANSACTION 1: put the OLD pin back ALONE", f"sudo apt install {pin_name}", f"Remv {f['driver'] and 'nvidia-driver-pinning-' + f['driver'] or 'the new pin'}, Inst {pin_name}; no driver package yet"),
        ("owner-nr", "simulate TRANSACTION 2: the driver packages at their exact old versions (the pipe, or a file the bot reads, as in the update plan)",
         [f"apt install -s {flags}{line2} 2>&1 | {UP} check-sim - --to {old} --rollback-from {ref_arg}"],
         f"check-sim: ok (every driver package goes to {old}; nothing protected is removed)"),
        ("owner", "TRANSACTION 2: downgrade the driver packages" + (f" and the container packages ({TOOLKIT} and friends: drop them from the line if only the driver is the problem; "
                                                                      "the toolkit's own fixes stay then)" if any(strip_arch(p).startswith("nvidia-container") or strip_arch(p).startswith("libnvidia-container") for p, _v in want) else ""),
         f"sudo apt install {flags}{line2}", f"no errors; DKMS builds nvidia/{old} and gpu-unlock for every kernel with headers"),
        ("bot", "check before rebooting", [f"{UP} verify --to {old} --installed", "dkms status"], f"verify: ok; nvidia/{old} and gpu-unlock installed for every kernel with headers"),
        ("owner", "reboot", "sudo reboot", "the host comes back"),
        ("bot", "verify after the reboot (opens the gate again only on ok; pass timeout=300 to hostcare; the selfcheck itself stops at 240 s)", f"{UP} verify --to {old} --apply", "RESULT: ok"),
    ]
    out += ["", "STEPS"] + fmt_steps(steps)
    out += ["", "A rollback of a security update leaves the host exposed again: tell the owner, write the reason in the log (" + f"{UP} log --add rollback --result done --note ... --apply" + "),",
            "and stay on the old driver only until a gpu-unlock that supports the new one exists. driver_watch will report the update again: expected."]
    return out, True


# The procedures `plan` knows: name -> (function(S, env, args) -> (lines, ok), [(flag, add_argument kwargs)]). A new procedure (kernel,
# container toolkit, gpu-unlock) is one function and one entry here: UPKEEP.md, "Adding a procedure".
MODULES = {"driver": (plan_driver, [("--to", {"required": True, "metavar": "VERSION", "type": "target"})])}


# ------------------------------------------------------------------------------------------------------------------ verify
def run_selfcheck(env, on_start=None):
    """gpu_selfcheck.py run --force as a subprocess (its own session, stopped for good after selfcheck_timeout(env) seconds, which is below hostcare's 300 s);
    (exit code, last output line). The script is gpu_selfcheck.py of this repository. UPKEEP_SELFCHECK can name another one ONLY inside the selftest: it needs
    UPKEEP_TEST to name the selftest's marker file (test_mode), which an environment variable typed in front of a command cannot produce; whoever can create that
    marker (a file only upkeep_selftest.py makes, owned by this user, mode 600, under the temp directory) can already run any script as this user. Every such
    override in effect is printed and logged as OVERRIDE. `on_start(pid, script)` is called once the child runs (the verify marker records it)."""
    path = selfcheck_script(env)
    limit = selfcheck_timeout(env)
    try:
        p = subprocess.Popen([sys.executable, "-I", path, "run", "--force"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    except OSError as e:
        return 2, f"could not run the selfcheck ({type(e).__name__})"
    try:
        if on_start:
            on_start(p.pid, path)
        out, _ = p.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        _kill_group(p)
        return 2, f"the selfcheck did not finish within {limit:.0f} s and was stopped (no verdict)"
    except BaseException:                                    # Ctrl-C, SIGTERM (SystemExit) or an error in on_start: never leave the child running
        _kill_group(p)
        raise
    lines = [l for l in (out or "").splitlines() if l.strip()]
    return p.returncode, lines[-1] if lines else ""


def _kill_group(p):
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        p.communicate(timeout=10)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass


def selfcheck_guarded(env, sd, step, always_close=False):
    """Run the selfcheck for `verify` and `unlock --run --apply`: the busy switch is lifted for the measurement only when it was on (the selfcheck runs in the
    gate's bench mode, which refuses while it is on) and put back unless the verdict is ok, also after a crash, Ctrl-C or SIGTERM; after a SIGKILL the
    marker written first lets the next upkeep call do it. always_close: a failed verdict closes the gate even when it was open before (verify).
    Returns (exit code, last line, was_busy)."""
    was = os.path.exists(busy_path(env))
    code = None

    def term(signum, _frame):
        raise SystemExit(128 + signum)
    old = None
    try:
        old = signal.signal(signal.SIGTERM, term)
    except ValueError:                                       # not the main thread
        pass
    try:
        if was:
            write_marker(sd, step)                           # BEFORE the switch is lifted
            set_busy(env, False)
        code, line = run_selfcheck(env, (lambda pid, script: write_marker(sd, step, pid, script)) if was else None)
    finally:
        if (was or always_close) and code != 0:
            set_busy(env, True)
        if was:
            clear_marker(sd)                                 # only after the switch is back
        if old is not None:
            signal.signal(signal.SIGTERM, old)
    return code, line, was


def boot_kernels(env):
    """Kernel releases that have a vmlinuz in /boot (UPKEEP_BOOT_DIR in tests)."""
    d = env.get("UPKEEP_BOOT_DIR") or "/boot"
    try:
        return sorted((n[len("vmlinuz-"):] for n in os.listdir(d) if n.startswith("vmlinuz-")), key=kernel_key)
    except OSError:
        return []


def kernels_without_headers(f, boot=()):
    """Installed (or present in /boot) kernels that have no headers package: DKMS cannot build for them. Debian's grub boots the newest one."""
    every = sorted(set(f["kernels"]) | set(boot), key=kernel_key)
    return [k for k in every if k not in f["headers"]]


def nohead_item(f, boot=()):
    """(status, 'kernels', detail) when an installed kernel (or one in /boot) has no headers, else None. FAIL when it is the newest: grub boots it and DKMS
    could not build nvidia and gpu-unlock for it. Shared by `verify` and `unlock`."""
    nohead = kernels_without_headers(f, boot)
    if not nohead:
        return None
    every = sorted(set(f["kernels"]) | set(boot), key=kernel_key)
    if every and nohead[-1] == every[-1]:
        return ("FAIL", "kernels", f"the newest kernel {every[-1]} has no headers, so no DKMS build: grub boots it and the host comes up without the driver. "
                                   "Install its headers (or remove the kernel) first")
    return ("note", "kernels", "older kernel(s) without headers, no DKMS build for them (grub does not boot them by default): " + " ".join(nohead[:4]))


def tied_version(v, refs):
    """True when a driver-family package version carries the driver's version (same major as a reference driver): a toolkit or a cudnn has its own."""
    t = DW.vtuple(ver(v) or "")
    return bool(t) and any((DW.vtuple(r) or (None,))[0] == t[0] for r in refs if r)


def snapshot_problems(f):
    """[why] this host is not in a clean state to take THE rollback snapshot: the driver unknown, the pin or a driver package at another version
    than the driver (a half-updated host). A snapshot of such a state would shadow the good one."""
    d = f["driver"]
    if not d:
        return ["nvidia-smi does not answer: the installed driver is unknown"]
    out = []
    p = pins(f)
    if len(p) != 1 or ver(p[0][len("nvidia-driver-pinning-"):]) != d:
        out.append(f"the installed pin ({', '.join(p) or 'none'}) is not the one of the running driver {d}")
    odd = [f"{n} {pkg_ver(f['installed'], n)}" for n in driver_set(f)
           if tied_version(pkg_ver(f["installed"], n) or "", [d]) and ver(pkg_ver(f["installed"], n) or "") != d]
    if odd:
        out.append(f"{len(odd)} driver package(s) are not at {d}: " + "; ".join(odd[:4]) + (" ..." if len(odd) > 4 else ""))
    return out


def verify_state(S, f, target, post, boot=(), refs=()):
    """[(status, name, detail)] of the checks that need no gate: pin, packages, dkms and, after the reboot, the loaded driver."""
    items = []
    p = pins(f)
    want = f"nvidia-driver-pinning-{target}"
    items.append(("ok" if p == [want] else "FAIL", "pin", f"{', '.join(p) or 'none'} installed" + ("" if p == [want] else f" (want only {want})")))
    dset = driver_set(f)
    judged = [n for n in dset if tied_version(pkg_ver(f["installed"], n) or "", [target, *refs])]
    own = [n for n in dset if n not in judged]
    bad = [f"{n} {pkg_ver(f['installed'], n)}" for n in judged if ver(pkg_ver(f["installed"], n) or "") != target]
    items.append(("ok" if judged and not bad else "FAIL", "packages", f"{len(judged)} driver package(s) at {target}" + (f" ({len(own)} with their own version scheme, not judged: {' '.join(own[:3])})" if own else "") if judged and not bad else
                  ("no driver package found" if not judged else "not at the target: " + "; ".join(bad[:5]))))
    kern = [k for k in f["kernels"] if k in f["headers"]]
    miss = []
    for k in kern:
        nv = [r for r in f["dkms"] if r[0] == "nvidia" and r[2] == k and r[3] == "installed"]
        if not any(r[1] == target for r in nv):
            miss.append(f"nvidia/{target} for {k}")
        if f["installed"].get("gpu-unlock-dkms") and not any(re.match(r"^gpu[-_]unlock", r[0]) and r[2] == k and r[3] == "installed" for r in f["dkms"]):
            miss.append(f"gpu-unlock for {k}")
    items.append(("ok" if kern and not miss else "FAIL", "dkms", f"nvidia/{target} and gpu-unlock installed for {len(kern)} kernel(s) with headers" if kern and not miss
                  else ("no kernel with headers" if not kern else "missing: " + "; ".join(miss))))
    nh = nohead_item(f, boot)
    if nh:
        items.append(nh)
    if post:
        d = f["driver"]
        items.append(("ok" if d == target else "FAIL", "driver", f"nvidia-smi reports {d}" if d == target else f"nvidia-smi reports {d or 'nothing (driver not loaded)'}, want {target}"))
        run = f["running"]
        items.append(("ok" if run in kern else "FAIL", "kernel", f"running {run}, built for it" if run in kern else f"running {run}: no headers/dkms build for it"))
    return items


def cmd_verify(S, env, sd, target, installed_only, apply):
    f = facts(S)
    snap_ref = pick_snapshot(sd, avoid=target)
    refs = [snap_ref[1].get("driver")] if snap_ref else []
    items = verify_state(S, f, target, not installed_only, boot_kernels(env), refs)
    out = [f"upkeep verify {'(before the reboot) ' if installed_only else ''}--to {target}"]
    failed = any(st == "FAIL" for st, _n, _d in items)
    gv = GateView(env)
    if not installed_only:
        items.append(("ok" if gv.state is not None else "FAIL", "gate", "answers GET /state" if gv.state is not None else gv.err))
        failed = failed or gv.state is None
    out += [f"  {st:5} {n}: {d}" for st, n, d in items]
    vers = {"driver": f["driver"], "target": target}
    if failed and apply:
        set_busy(env, True)                                       # a failed check leaves the gate CLOSED, whatever it was before
    if installed_only:
        res = "fail" if failed else "ok"
        out.append("RESULT: " + ("ok: nothing blocks the reboot" if not failed else "FAIL: do not reboot; fix it or roll back" + ("; the gate is closed" if apply else "")))
        if apply:
            append_log(sd, "verify-installed", res, vers)
        return out, 0 if not failed else 1
    verdict = "fail" if failed else "pending"
    sc_line = ""
    if not failed:
        if not apply:
            out.append("  --    selfcheck: not run without --apply (it measures the card for a few seconds and lifts the busy switch for that)")
            out.append("RESULT: incomplete: driver, dkms and gate are fine; run with --apply for the selfcheck and to open the gate")
            return out, 2
        # the selfcheck runs inside the gate's bench mode, which refuses while the switch is on: the gate is open to new wakes for the whole
        # selfcheck window (inherent, documented). Not ok, no verdict, a crash, Ctrl-C or SIGTERM: back to CLOSED; after a SIGKILL the marker does it.
        code, sc_line, was_busy = selfcheck_guarded(env, sd, "verify", always_close=True)
        verdict = "ok" if code == 0 else "degraded" if code == 1 else "incomplete"
        out.append(f"  {'ok' if code == 0 else 'FAIL' if code == 1 else '--':5} selfcheck: exit {code}: {sc_line}")
        if code == 0 and was_busy:
            out.append("  ok    busy: off (the gate takes new wakes again)")
    if verdict == "ok":
        out.append("RESULT: ok")
        append_log(sd, "verify", "ok", vers, sc_line or None, what=f"driver update to {target}: verified after the restart",
                   before={"driver": (snap_ref[1].get("driver") if snap_ref else None) or "?", "snapshot": snap_ref[0] if snap_ref else "none"},
                   after={"driver": f["driver"], "selfcheck": "ok"}, rollback=f"{UP} rollback {snap_ref[0]}" if snap_ref else None)
        return out, 0
    if verdict == "incomplete":
        out.append("RESULT: incomplete: the selfcheck gave no verdict (card in use, setup error or error): the gate stays CLOSED; run verify --apply again when the card is free")
        if apply:
            append_log(sd, "verify", "incomplete", vers, sc_line or None)
        return out, 2
    label = "degraded: the unlock did not survive the update" if verdict == "degraded" else "fail: a check above failed"
    out.append("RESULT: " + label + ". The gate stays CLOSED. Rollback:")
    if apply:
        append_log(sd, "verify", verdict, vers, sc_line or None)
    if snap_ref:
        lines, _ok = rollback_lines(S, env, snap_ref[1], snap_ref[0], sd, list_snapshots(sd))
        out += [""] + lines
    else:
        out.append(f"  no snapshot found in {sd}: take the versions from driver_watch.py status, or `{UP} snapshot --apply` is too late now")
    return out, 1


# ------------------------------------------------------------------------------------------------------------------ GPU card management
# Everything below is for the NVIDIA card as a whole, not only the driver: power caps and VRAM needs from the bench, a new gpu-host tree for the
# gate, the unlock's health, a kernel update. The same rules as the driver procedure: print by default, `--apply` only for what needs no root,
# a backup (or a snapshot) before and an exact rollback, and before/after lines in the audit log. The only program started that changes anything is
# the restart of the gate's USER unit (Sys.act): the gate is not a root service.
EXCLUDE_DIRS = ("state", "out", "models", "__pycache__", ".git")      # never copied, never backed up, never restored: the host's own data
EXCLUDE_FILES = ("host.env", "*.log", "*.pyc", "*.upkeep-tmp-*")                          # (the same set a careful rsync of gpu-host/ leaves alone)
MAX_TREE_MB = 200
NEED_MB_RANGE = (64, 98304)                                         # a VRAM need outside this is a measurement error, not a proposal
MAX_NEED_RISE = 2.0                                                   # a VRAM need that grows by more than this factor gets a warning (the gate then refuses wakes it could serve)
MAX_NEED_DROP = 0.25                                                  # a VRAM need that falls by more than this needs --allow-lower-need: it over-commits the card
PROFILE_W_RANGE = (30, 600)                                           # sanity range of a power cap when the gate does not report the card's own


def excluded(rel):
    parts = rel.split("/")
    return any(p in EXCLUDE_DIRS for p in parts[:-1]) or parts[-1] in EXCLUDE_DIRS or any(fnmatch.fnmatch(parts[-1], g) for g in EXCLUDE_FILES)


def walk_tree(root):
    """({rel: (abs path, size)} of the regular files minus the excluded ones, skipped): symlinks and special files are never followed."""
    out, skipped = {}, 0
    for dp, dns, fns in os.walk(root, followlinks=False):
        rd = os.path.relpath(dp, root).replace(os.sep, "/")
        pre = "" if rd == "." else rd + "/"
        dns[:] = sorted(d for d in dns if not excluded(pre + d))
        for fn in sorted(fns):
            p, rel = os.path.join(dp, fn), pre + fn
            if excluded(rel):
                continue
            if os.path.islink(p) or not os.path.isfile(p):
                skipped += 1
                continue
            out[rel] = (p, os.path.getsize(p))
    return out, skipped


def md5_bytes(b):
    return hashlib.md5(b, usedforsecurity=False).hexdigest()          # the identity of a copy, not a security measure


def md5_path(path):
    try:
        with open_regular(path, "rb") as f:                           # a fifo or a device at the path is "no file", never a hang
            return md5_bytes(f.read())
    except OSError:
        return None


def read_text(path, keep_newlines=False):
    """The text of a regular file (utf-8); OSError for a fifo, a device or anything that is not one. keep_newlines: no newline translation
    (a file this tool rewrites keeps its CRLF line ends)."""
    with open_regular(path, encoding="utf-8", **({"newline": ""} if keep_newlines else {})) as f:
        return f.read()


def tree_digest(md5s):
    return md5_bytes("\n".join(f"{m}  {r}" for r, m in sorted(md5s.items())).encode())


def short(m):
    return (m or "none")[:12]


def safe_rel(rel):
    parts = rel.split("/")
    return bool(rel) and not rel.startswith("/") and all(p not in ("", ".", "..") for p in parts) and not re.search(r"[\x00-\x1f]", rel)


def read_dir_tree(root):
    """({rel: (bytes, mode)}, problems) of a gpu-host directory, minus the excluded files."""
    if not os.path.isdir(root):
        return {}, [f"{root} is not a directory"]
    files, _sk = walk_tree(root)
    tree, total = {}, 0
    for rel, (p, size) in files.items():
        total += size
        if total > MAX_TREE_MB * 2**20:
            return {}, [f"the tree is bigger than {MAX_TREE_MB} MB: not a gpu-host tree?"]
        try:
            with open_regular(p, "rb") as f:
                tree[rel] = (f.read(), os.fstat(f.fileno()).st_mode & 0o777)
        except OSError as e:
            return {}, [f"cannot read {rel}: {e.strerror}"]
    return tree, []


def tree_from_archive(data):
    """({rel: (bytes, mode)}, problems) of the regular files under gpu-host/ of a `git archive`, minus the excluded ones."""
    tree, problems, total = {}, [], 0
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
    except tarfile.TarError:
        return {}, ["the archive cannot be read"]
    with tf:
        for m in tf.getmembers():
            if not m.name.startswith("gpu-host/") or not m.isfile():
                continue                                              # directories, symlinks and special files are not deployed
            rel = m.name[len("gpu-host/"):]
            if not safe_rel(rel):
                problems.append("an unsafe path in the archive: " + repr(rel[:40]))
                continue
            if excluded(rel):
                continue
            total += m.size
            if total > MAX_TREE_MB * 2**20:
                return {}, [f"the tree is bigger than {MAX_TREE_MB} MB: not a gpu-host tree?"]
            tree[rel] = (tf.extractfile(m).read(), m.mode & 0o777)
    return tree, problems


def ref_tree(S, ref):
    """(tree, id, problems) of gpu-host/ at a git ref of this checkout: git runs read-only through Sys."""
    rc, out = S.cmd([*S.git_prefix(), "rev-parse", "--verify", "--quiet", ref + "^{commit}"])
    commit = out.strip()
    if rc != 0 or not Sys.COMMIT.fullmatch(commit):
        return {}, None, [f"the ref {ref!r} is not a commit of this checkout"]
    rc, data = S.cmd([*S.git_prefix(), "archive", "--format=tar", commit, "gpu-host"], 120, raw=True)
    if rc != 0 or not data:
        return {}, commit, [f"git archive of gpu-host at {commit[:12]} failed"]
    tree, problems = tree_from_archive(data)
    return tree, commit, problems


def link_in_path(path, root=None):
    """The first symlink on the way to `path` (the final component, and with `root` every component below it), else None. A symlink is never
    replaced or deleted by this tool: the file it points at is not ours to change, and an undo would delete the link."""
    if not root:
        return path if os.path.islink(path) else None
    cur = root
    for p in (x for x in os.path.relpath(path, root).split(os.sep) if x):
        cur = os.path.join(cur, p)
        if os.path.islink(cur):
            return cur
    return None


def atomic_write(path, data, mode, root=None):
    """Write `data` to `path` through a temp file made with O_EXCL and O_NOFOLLOW (a planted file or link under the temp name is never written
    through), then rename it over the target. Refuses (OSError) when the target is a symlink or, with `root`, sits behind one."""
    bad = link_in_path(path, root)
    if bad:
        raise OSError(errno.ELOOP, "is or sits behind a symlink", bad)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.upkeep-tmp-{os.getpid()}-{secrets.token_hex(4)}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fchmod(f.fileno(), mode)
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def dest_dir(a, env):
    """The deployed gpu-host copy the gate runs from: --dest, else UPKEEP_GPU_DIR, else the tree this tool itself sits in. Inside this checkout only
    with an explicit --dest (see dest_checks)."""
    return os.path.abspath(a.dest or env.get("UPKEEP_GPU_DIR") or GPU)


def inside(path, root):
    r = os.path.realpath(root)
    try:
        return os.path.commonpath([os.path.realpath(path), r]) == r
    except ValueError:
        return False


OVERRIDE_WHAT = {
    "UPKEEP_ALLOW_REMOVE": "removals it accepts", "UPKEEP_PROTECT": "extra protected packages", "UPKEEP_GPU_DIR": "the default destination",
    "UPKEEP_STATE_DIR": "where snapshots, backups, the audit log and the verify marker live", "UPKEEP_BOOT_DIR": "the /boot it measures", "UPKEEP_BOOT_MIN_MB": "the /boot space it demands",
    "UPKEEP_CHECKOUT": "the git checkout it reads", "UPKEEP_SELFCHECK": "the script verify runs", "UPKEEP_TEST": "test mode (the selftest's marker)",
    "UPKEEP_SELFCHECK_TIMEOUT_S": "the selfcheck's time limit (clamped)", "UPKEEP_KEEP_BACKUPS": "how many backups are kept (at least 3)", "UPKEEP_HEALTH_WAIT_S": "how long the gate gets to come back",
}
TEST_ONLY = ("UPKEEP_SELFCHECK", "UPKEEP_CHECKOUT")        # honoured only when test_mode() is true


def overrides(env):
    """[text] of EVERY UPKEEP_* environment override in effect (they change what the tool allows, reads, runs or where it writes): each one is printed to stderr
    and logged as OVERRIDE (dispatch), and shown in a plan, so the owner who approves a command sees it. A test-only one outside the selftest says it is ignored."""
    out, tm = [], test_mode(env)
    for k in sorted(k for k, v in env.items() if k.startswith("UPKEEP_") and v):
        shown = re.sub(r"[^ -~]", "?", str(env[k]))[:80]
        note = " -- IGNORED: honoured only inside the selftest" if k in TEST_ONLY and not tm else \
            " -- NOT a valid test marker, test mode is OFF" if k == "UPKEEP_TEST" and not tm else ""
        out.append(f"{k} is set ({OVERRIDE_WHAT.get(k, 'an unknown override')}): {shown}{note}")
    return out


def announce_overrides(env, sd, apply):
    """stderr: one `upkeep: OVERRIDE: ...` line per override in effect. With --apply also one audit line `override`, when the set differs from the last one logged
    (said once, not at every call). A log that cannot be written changes nothing here."""
    lines = overrides(env)
    for line in lines:
        print("upkeep: OVERRIDE: " + line, file=sys.stderr)
    if lines and apply:
        key = md5_bytes("\n".join(lines).encode())[:12]
        try:
            last = [e for e in read_log(sd) if e.get("step") == "override"]
            if not last or last[-1].get("ref") != key:
                append_log(sd, "override", "noted", note="OVERRIDE: " + "; ".join(lines)[:700], ref=key)
        except OSError:
            pass


def dirty_files(S, dest):
    """(set of paths relative to gpu-host/ with uncommitted changes (modified, staged, untracked), why-not): only when `dest` is the gpu-host/ of this
    checkout; (None, why) when it cannot be told. Read-only git through Sys."""
    if os.path.realpath(dest) != os.path.realpath(os.path.join(S.checkout, "gpu-host")):
        return None, "the destination is not the gpu-host/ of the source checkout"
    rc, out = S.cmd([*S.git_prefix(), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "gpu-host"], 30)
    if rc != 0:
        return None, "git status did not answer (not a git checkout?)"
    ent, i, dirty = out.split("\0"), 0, set()
    while i < len(ent):
        e = ent[i]
        i += 1
        if len(e) < 4:
            continue
        if e[0] in "RC":
            i += 1                                           # a rename or copy lists the old name as the next entry
        if e[3:].startswith("gpu-host/"):
            dirty.add(e[3 + len("gpu-host/"):])
    return dirty, None


def other_worktree(path, known):
    """The root of the git work tree `path` is in (a `.git` directory or file on the way up) when it is none of `known` (the source checkout), else None."""
    cur = os.path.realpath(path)
    known = [os.path.realpath(k) for k in known]
    while True:
        if os.path.lexists(os.path.join(cur, ".git")):
            return None if cur in known else cur
        nxt = os.path.dirname(cur)
        if nxt == cur:
            return None
        cur = nxt


def dest_checks(S, env, a, dest, what):
    """[(status, name, detail)] about WHERE a change goes. The default destination is never inside the checkout this tool and its source come from:
    on a standard install the gate runs from the checkout's gpu-host/, so a change there edits git-tracked files, and `--dest` must be spelled out so
    the owner reads the target in the command. Anything else (a dirty tree, a profile change that would revert) is judged by the caller."""
    pre = []
    roots = [r for r in dict.fromkeys([S.checkout, CHECKOUT]) if inside(dest, r)]
    if roots and not a.dest:
        pre.append(("NOT OK", "destination", f"{dest} is inside the source checkout ({roots[0]}) and no --dest was given. On a standard install the gate runs from the checkout's "
                                              f"gpu-host/, so the checkout and the deployed copy are the SAME files and {what} edits git-tracked files there. Name the target "
                                              f"yourself: --dest {shlex.quote(dest)}"))
    elif roots:
        pre.append(("note", "checkout", f"{dest} is inside the source checkout: the checkout and the deployed copy are the same files (standard install), so {what} changes the working tree of the checkout"))
    if os.path.islink(dest):
        pre.append(("note", "destination", f"--dest is itself a symlink (to {os.path.realpath(dest)}): the files are read, written and backed up in the real directory, and undo puts them back there. "
                                           "(Only links INSIDE the tree are refused.)"))
    other = other_worktree(dest, [S.checkout, CHECKOUT])
    if other:
        pre.append(("note", "git", f"{dest} is inside another git work tree ({other}): files there that git tracks change, and the dirty-tree check (and the 'would REVERT' list) is made only "
                                    "for the source checkout, so none is made for this destination: look at `git status` there yourself"))
    pre += [("note", "override", "OVERRIDE: " + x) for x in overrides(env)]
    return pre, bool(roots)


def read_gate_unit():
    """What the gate's user unit says (the unit file is only READ): {path, gate_py, env} or None when this account has none."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, "systemd", "user", GATE_UNIT)
    try:
        with open_regular(path, encoding="utf-8", errors="replace") as f:
            text = f.read(65536)
    except OSError:
        return None
    info = {"path": path, "gate_py": None, "env": {}}
    for line in text.splitlines():
        k, sep, v = line.strip().partition("=")
        if not sep:
            continue
        try:
            toks = shlex.split(v)
        except ValueError:
            toks = []
        if k == "ExecStart":
            g = [t for t in toks if t.endswith("gate.py") and os.path.isabs(t)]
            if g:
                info["gate_py"] = g[-1]
        elif k == "EnvironmentFile" and v.strip().lstrip("-").startswith("/"):
            info["env"].update(BG.parse_env_file(v.strip().lstrip("-")))
        elif k == "Environment":
            for t in toks:
                kk, eq, vv = t.partition("=")
                if eq and kk:
                    info["env"][kk] = vv
    return info


def gate_reads(env, dest):
    """What the gate really reads, as the gate computes it (gate.py Config): its tree (the unit's gate.py), its env file (GATE_ENV_FILE, else host.env
    of the tree) and its power profiles file (GATE_POWER_PROFILES from that env or the unit, else power_profiles.conf of the tree).
    {unit, tree, env_file, profiles}; without a unit the answer comes from this tool's own view (host.env and the environment) and the destination."""
    unit = read_gate_unit()
    if unit:
        tree = os.path.dirname(os.path.dirname(unit["gate_py"])) if unit["gate_py"] else dest
        genv = unit["env"]
        ef = genv.get("GATE_ENV_FILE") or os.path.join(tree, "host.env")
        vals = dict(BG.parse_env_file(ef))
        vals.update({k: v for k, v in genv.items() if k.startswith(("GATE_", "GPU_BIND_ADDR"))})
    else:
        tree, ef, vals = None, env.get("GATE_ENV_FILE") or os.path.join(dest, "host.env"), env
    prof = vals.get("GATE_POWER_PROFILES") or os.path.join(tree or dest, "power_profiles.conf")
    return {"unit": unit, "tree": tree, "env_file": ef, "profiles": prof, "profiles_relative": not os.path.isabs(os.path.expanduser(prof))}


@contextlib.contextmanager
def change_lock(sd):
    """One apply at a time per state directory (flock on apply.lock): yields True when held, False when another upkeep change is running."""
    private_dir(sd)
    fd = os.open(os.path.join(sd, "apply.lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            got = True
        except OSError:
            got = False
        yield got
    finally:
        os.close(fd)


KEEP_BACKUPS = 20


def prune_backups(sd, env):
    """Remove the oldest backups beyond UPKEEP_KEEP_BACKUPS (default 20, at least 3); [ids removed]. Only inside sd/backups, only well-formed ids."""
    try:
        keep = max(3, int(env.get("UPKEEP_KEEP_BACKUPS") or KEEP_BACKUPS))
    except ValueError:
        keep = KEEP_BACKUPS
    ids = [i for i, _m in list_changes(sd)]
    gone = []
    for i in ids[:-keep] if len(ids) > keep else []:
        d = os.path.join(sd, "backups", i)
        if os.path.isdir(d) and not os.path.islink(d):
            shutil.rmtree(d, ignore_errors=True)
            gone.append(i)
    if gone:
        append_log(sd, "backups-pruned", "ok", note=f"{len(gone)} oldest backup(s) removed, the newest {keep} are kept: {gone[0]} .. {gone[-1]}")
    return gone


def private_path(root, *parts):
    """Create root/parts level by level, every level mode 700 (os.makedirs would only set the last one)."""
    cur = private_dir(root)
    for p in parts:
        cur = private_dir(os.path.join(cur, p))
    return cur


def confirm_id(*parts):
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:12]


def capped(items, n=MAX_REASONS * 3):
    return list(items[:n]) + ([f"... and {len(items) - n} more"] if len(items) > n else [])


# ------------------------------------------------------------------------------------------------------------------ the gate: restart rules
def healthz(env, timeout=5):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{env.get('GATE_PORT', '8700')}/healthz", timeout=timeout) as r:
            return r.status == 200 and r.read(64).startswith(b"ok")
    except (OSError, ValueError):
        return False


def restart_decision(env, gv, needed, no_restart, while_running):
    """(action, why): 'none' | 'restart' | 'refuse'. A restart drops the gate's leases and the gate adopts the services that already run, so it is
    safe with services running ONLY because of that: it needs the explicit flag. A bench or selfcheck is never cut by a restart."""
    if not needed:
        return "none", "not needed: nothing the gate loads at its start changed"
    if no_restart:
        return "none", "skipped (--no-restart): the running gate keeps its old values until its next restart"
    if not healthz(env):
        return "restart", "the gate does not answer /healthz (down): starting it loads the new files; services that run are adopted"
    if gv.state is None:
        return "refuse", f"the gate answers /healthz but not GET /state ({gv.err}): cannot tell whether a service runs"
    if gv.state.get("bench"):
        return "refuse", "a bench or selfcheck is running: a restart would end it; wait"
    run = gv.busy_services()
    if run and not while_running:
        return "refuse", ("running or leased: " + ", ".join(run) + ". Wait until they stop (idle), or add --restart-while-running "
                          "(the gate adopts running services after the restart; their leases are dropped, nothing is cut), or --no-restart (files only)")
    if run:
        return "restart", "services run (" + ", ".join(run) + "): restarting on --restart-while-running; the gate adopts them and they follow the idle rule"
    return "restart", "no service is running: the gate is restarted now"


def do_restart(S, env, before_running):
    """(status, lines) of a restart of the gate's user unit, then /healthz and GET /state. status: ok | degraded (a service that ran is not listed
    as running again) | failed (no /healthz or no /state)."""
    rc, _ = S.act(["systemctl", "--user", "restart", GATE_UNIT])
    if rc != 0:
        return "failed", [f"restart of {GATE_UNIT} failed (exit {rc})"]
    try:
        wait = float(env.get("UPKEEP_HEALTH_WAIT_S") or 60)
    except ValueError:
        wait = 60.0
    t0, up = time.time(), False
    while not up:
        up = healthz(env)
        if not up:
            if time.time() - t0 >= wait:
                return "failed", [f"restart sent, but /healthz does not answer after {wait:.0f} s"]
            time.sleep(1)
    gv, missing = None, list(before_running)
    while True:
        gv = GateView(env)
        if gv.state is not None:
            missing = [x for x in before_running if x not in gv.busy_services()]
            if not missing:
                break
        if time.time() - t0 >= wait:
            break
        time.sleep(1)
    lines = ["healthz: ok"]
    if gv.state is None:
        return "failed", lines + [f"GET /state: {gv.err}"]
    lines.append("state: ok" + (f", adopted running: {', '.join(before_running)}" if before_running else ", nothing was running"))
    if missing:
        return "degraded", lines + ["not listed as running after the restart: " + ", ".join(missing) + " (adoption pending? look at `gateway gpu status`)"]
    return "ok", lines


# ------------------------------------------------------------------------------------------------------------------ changes with a backup
def new_change_id(sd, kind):
    base = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    try:
        taken = set(n.rsplit("-", 1)[0] for n in os.listdir(os.path.join(sd, "backups")))
    except OSError:
        taken = set()
    while base in taken:                                         # one id per second whatever the kind: the ids sort in the order they were made
        base += "x"
    return base + "-" + kind


def read_manifest(sd, cid):
    if not SAFE_CHANGE.fullmatch(cid or ""):
        return None
    try:
        with open_regular(os.path.join(sd, "backups", cid, "manifest.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def list_changes(sd):
    try:
        ids = sorted(n for n in os.listdir(os.path.join(sd, "backups")) if SAFE_CHANGE.fullmatch(n))
    except OSError:
        return []
    return [(i, read_manifest(sd, i)) for i in sorted(ids, key=lambda n: n.rsplit("-", 1)[0])]


def make_backup(sd, cid, copies):
    """Copy {store: source file} into backups/ID/<store>; {store: md5 of the copy}. Directories 700, files 600."""
    root = private_path(sd, "backups", cid)
    out = {}
    for store, src in copies.items():
        parts = store.split("/")
        dst_dir = private_path(root, *parts[:-1]) if len(parts) > 1 else root
        dst = os.path.join(dst_dir, parts[-1])
        shutil.copyfile(src, dst)
        os.chmod(dst, 0o600)
        out[store] = md5_path(dst)
    return out


def write_manifest(sd, cid, man):
    write_private(os.path.join(sd, "backups", cid, "manifest.json"), json.dumps(man, indent=1, sort_keys=True) + "\n")


def manifest_problems(man):
    """[problem] of a manifest read from the state dir: its paths decide what gets written, so they are checked against the recorded destination."""
    bad = []
    if man.get("schema") != 1 or man.get("kind") not in ("profile", "deploy") or not isinstance(man.get("files"), list):
        return ["not a manifest of this tool"]
    dest = man.get("dest")
    if not isinstance(dest, str) or not os.path.isabs(dest):
        return ["no destination"]
    for e in man["files"]:
        if not isinstance(e, dict) or not isinstance(e.get("store"), str) or not isinstance(e.get("path"), str):
            bad.append("a file entry is malformed")
            continue
        st = e["store"]
        if st.startswith("tree/") and safe_rel(st[5:]):
            ok = e["path"] == os.path.join(dest, st[5:])
        else:
            ok = st == "mcp/mcp_dispatch.sh" and e["path"] == man.get("mcp") and os.path.basename(e["path"]) == "mcp_dispatch.sh"
        if not ok:
            bad.append("a path does not belong to this change: " + st[:40])
    return bad[:3]


def undo_lines(S, env, sd, cid, man, apply, force, no_restart, while_running):
    """(lines, ok) of the exact rollback of a change: every file back from the backup (an added file removed), then the gate restart rules."""
    bad = manifest_problems(man)
    if bad:
        return [f"undo {cid}: NOT OK: " + "; ".join(bad)], False
    root = os.path.join(sd, "backups", cid)
    out = [f"undo {cid}: {man.get('what', '?')}" + (" (already undone)" if man.get("undone_at") else "")]
    if man.get("undone_at") and not force:
        return out + ["  nothing to do: this change was undone; --force repeats it"], False
    plan, problems, fatal, linked = [], [], [], []   # problems: a later change or a hand edit (--force accepts it); fatal: --force never helps; linked: a symlink (--force skips those files)
    for e in man["files"]:
        cur = md5_path(e["path"])
        name = e["store"][5:] if e["store"].startswith("tree/") else e["store"]
        if special_file(e["path"]):                  # a fifo, a device or a directory where a file was: never read, replaced or removed (and --force does not help)
            fatal.append(f"{name[:60]} is not a regular file now (a fifo, a device, a socket or a directory): move it aside by hand")
        link = link_in_path(e["path"], man["dest"] if e["store"].startswith("tree/") else None)
        if link:
            linked.append((e["path"], f"{name[:60]} is or sits behind a symlink ({os.path.basename(link)[:40]}): this tool never replaces or deletes a symlink; move it aside by hand"))
        if cur != e.get("md5_after") and not force:
            problems.append(f"{e['store'][:60]} was changed after this change (md5 {short(cur)}, expected {short(e.get('md5_after'))}): a later change or a hand edit")
        if e.get("existed"):
            b = md5_path(os.path.join(root, e["store"]))
            if b is None or b != e.get("md5_before"):
                fatal.append(f"the backup of {e['store'][:60]} is missing or altered: --force cannot restore it")
        plan.append((e, cur))
    skip = {pth for pth, _m in linked}
    if force:                                        # restore what can be restored; the symlinked files stay as they are and the result says so
        plan = [(e, c) for e, c in plan if e["path"] not in skip]
    for e, cur in plan[:MAX_REASONS * 3]:
        name = e["store"][5:] if e["store"].startswith("tree/") else e["store"]
        out.append(f"  restore {name}: md5 {short(cur)} -> {short(e.get('md5_before'))}" if e.get("existed") else f"  remove {name} (added by this change)")
    if len(plan) > MAX_REASONS * 3:
        out.append(f"  ... and {len(plan) - MAX_REASONS * 3} more files")
    out += ["  " + ("skipped: " if force else "NOT OK: ") + m for _p, m in linked[:MAX_REASONS]]
    out += ["  NOT OK: " + p for p in (fatal + problems)[:MAX_REASONS]]
    if not force:
        problems = problems + [m for _p, m in linked]
    gv = GateView(env)
    needed = bool(man.get("restart_needed"))
    action, why = restart_decision(env, gv, needed, no_restart, while_running)
    out.append("  gate restart: " + action + " -- " + why)
    if not apply:
        return out + ["  print-only: add --apply to restore" + (" (it would be refused now: see the gate restart line)" if action == "refuse" else "")], not (problems or fatal)
    if problems or fatal or action == "refuse":
        return out + ["  NOT UNDONE: nothing was changed" + ("; --force does not help here (see the NOT OK lines)" if fatal else "; add --force only if the later change may be lost (symlinked files are skipped, never replaced)" if problems else "")], False
    before_running = gv.busy_services() if gv.state is not None else []
    append_log(sd, "undo", "before", what=f"undo {cid}: {man.get('what', '?')}",
               before={e["store"][:60]: short(md5_path(e["path"])) for e in man["files"][:12]}, rollback=f"{UP} undo {cid} --apply --force")
    try:
        for e, cur in plan:
            if e.get("existed") and cur == e.get("md5_before") and not special_file(e["path"]):
                continue                                     # already as before (a copy that stopped earlier never reached it): nothing to write
            if not e.get("existed") and not os.path.lexists(e["path"]):
                continue                                     # an added file that was never written
            if e.get("existed"):
                with open_regular(os.path.join(root, e["store"]), "rb") as f:
                    atomic_write(e["path"], f.read(), int(e.get("mode_before") or 0o644), man["dest"] if e["store"].startswith("tree/") else None)
            elif not os.path.islink(e["path"]):
                try:
                    os.unlink(e["path"])
                except FileNotFoundError:
                    pass
    except OSError as err:
        append_log(sd, "undo", "failed", what=f"undo {cid}: the restore stopped ({err.strerror or type(err).__name__})")
        return out + [f"  FAILED: the restore stopped midway ({err.strerror or type(err).__name__}); the backup is intact: fix the cause, then `{UP} undo {cid} --apply --force`"], False
    wrong = [e["store"] for e in man["files"] if md5_path(e["path"]) != e.get("md5_before")]
    status, lines = "ok", []
    if wrong:
        status, lines = "failed", ["after the restore these files still differ from the backup: " + ", ".join(wrong[:3])
                                   + (" (symlinked: left alone)" if skip else "")]
    elif action == "restart":
        status, lines = do_restart(S, env, before_running)
    if not wrong:
        man["undone_at"] = int(time.time())           # only when every file is back: an undo that left files wrong is not "already undone", a plain `undo` tries again
        write_manifest(sd, cid, man)
    append_log(sd, "undo", status, what=f"undo {cid}", after={e["store"][:60]: short(md5_path(e["path"])) for e in man["files"][:12]}, ref=man.get("ref"))
    return out + ["  restored: " + ("every file is back (md5 equals the backup)" if not wrong else "FAILED")] + ["  " + x for x in lines] \
        + [f"RESULT: {status}"], status == "ok"


def files_back(man):
    """True when every file of the change reads as it did before it (md5 of the backup; an added file is gone)."""
    return all(md5_path(e["path"]) == e.get("md5_before") for e in man["files"])


def cmd_undo(S, env, sd, a):
    if not a.change:
        rows = list_changes(sd)
        if not rows:
            print("no changes with a backup yet")
            return 0
        for i, m in rows[-20:]:
            m = m or {}
            print(f"{i}  {m.get('kind', '?'):8} {'undone ' if m.get('undone_at') else ''}{str(m.get('what', '?'))[:90]}")
        print(f"undo one with: {UP} undo ID --apply")
        return 0
    man = read_manifest(sd, a.change)
    if not man:
        print(f"undo: no change {a.change[:40]!r} in {sd}: `{UP} undo` lists them", file=sys.stderr)
        return 2
    if a.apply:
        with change_lock(sd) as got:
            if not got:
                print(f"undo: another upkeep change is running (lock {os.path.join(sd, 'apply.lock')}): wait for it to end", file=sys.stderr)
                return 1
            lines, ok = undo_lines(S, env, sd, a.change, man, a.apply, a.force, a.no_restart, a.restart_while_running)
    else:
        lines, ok = undo_lines(S, env, sd, a.change, man, False, a.force, a.no_restart, a.restart_while_running)
    print("\n".join(lines))
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------------------------------ profile apply
SEC_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(?:[#;].*)?$")
KEYLIKE_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*[=:]")                      # a line that sets a key, whatever its value looks like
KEYV_RE = re.compile(r"^(\s*)([A-Za-z0-9_.-]+)(\s*[=:]\s*)(\d+(?:\.\d+)?)(\s*(?:#.*)?)$")


def services_of(text):
    """{name: (port, need_mb, ready_s)} from the SERVICES literal of a gate.py, WITHOUT running it; None when it cannot be read."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SERVICES" for t in node.targets):
            try:
                d = ast.literal_eval(node.value)
            except ValueError:
                return None
            ok = isinstance(d, dict) and all(isinstance(k, str) and isinstance(v, tuple) and len(v) == 3 and all(isinstance(x, int) for x in v) for k, v in d.items())
            return d if ok else None
    return None


def card_section(text, gpu_name):
    """The section the gate itself would use for this card (the longest section name that is a case-insensitive part of the GPU's name)."""
    best = None
    for line in text.splitlines():
        m = SEC_RE.match(line)
        if m and gpu_name and m.group(1).strip().lower() in gpu_name.lower():
            if best is None or len(m.group(1).strip()) > len(best):
                best = m.group(1).strip()
    return best


def edit_conf(text, section, caps):
    """(new text, [(task, old, new)], problems): the values of ONE section of power_profiles.conf, comments and the other sections untouched."""
    lines = text.splitlines(keepends=True)
    heads = [i for i, l in enumerate(lines) if SEC_RE.match(l.rstrip("\r\n")) and SEC_RE.match(l.rstrip("\r\n")).group(1).strip().lower() == section.lower()]
    if len(heads) != 1:
        return None, [], [f"section [{section}] occurs {len(heads)} times, expected once"]
    start = heads[0] + 1
    end = next((i for i in range(start, len(lines)) if SEC_RE.match(lines[i].rstrip("\r\n"))), len(lines))
    seen, last, problems, changes, odd = {}, heads[0], [], [], {}
    for i in range(start, end):
        m = KEYV_RE.match(lines[i].rstrip("\r\n"))
        if m:
            k = m.group(2).lower()
            if k in seen:
                problems.append(f"{k} is set twice in [{section}]")
            seen[k] = i
            last = i
        else:
            km = KEYLIKE_RE.match(lines[i])
            if km:
                odd[km.group(1).lower()] = lines[i].strip()
    for task in caps:
        if task in odd:
            problems.append(f"{task} is already set in [{section}] but not as a plain number ({odd[task][:40]!r}): fix that line by hand first (this tool edits only `key = number` lines)")
    new = list(lines)
    adds = []

    def eol_of(line):
        return "\r\n" if line.endswith("\r\n") else "\n"
    for task, w in caps.items():
        if task in seen:
            m = KEYV_RE.match(lines[seen[task]].rstrip("\r\n"))
            if float(m.group(4)) != float(w):
                new[seen[task]] = m.group(1) + m.group(2) + m.group(3) + str(w) + m.group(5) + eol_of(lines[seen[task]])      # the line keeps its own line ending
                changes.append((task, m.group(4), str(w)))
        else:
            adds.append(f"{task} = {w}" + eol_of(lines[last]))
            changes.append((task, None, str(w)))
    if adds:
        if not new[last].endswith("\n"):
            new[last] += "\n"
        new[last + 1:last + 1] = adds
    return "".join(new), changes, problems


def edit_services(text, needs):
    """(new text, [(task, old, new)], problems): the VRAM need (MB) of services in the SERVICES block of gate.py; port and ready budget untouched."""
    m = re.search(r"^SERVICES = \{.*?^\}", text, re.S | re.M)
    if not m:
        return None, [], ["no SERVICES block in gate.py"]
    block, changes, problems = m.group(0), [], []
    for task, need in needs.items():
        pat = re.compile(r'("%s"\s*:\s*\(\s*\d+\s*,\s*)(\d+)(\s*,\s*\d+\s*\))' % re.escape(task))
        hits = pat.findall(block)
        if len(hits) != 1:
            problems.append(f'"{task}" is not in the SERVICES block exactly once')
            continue
        if int(hits[0][1]) != need:
            block = pat.sub(lambda mm: mm.group(1) + str(need) + mm.group(3), block, count=1)
            changes.append((task, hits[0][1], str(need)))
    return text[:m.start()] + block + text[m.end():], changes, problems


def default_results():
    return os.path.join(os.environ.get("BENCH_GATE_HOME") or os.path.join(os.path.expanduser("~"), "bench_gate"), "results.jsonl")


def read_results(path):
    """(rows, problem): the JSON objects of bench_gate's results.jsonl (a bad line is skipped)."""
    rows = []
    try:
        if os.path.getsize(path) > 64 * 2**20:
            return None, "the results file is bigger than 64 MB"
        with open_regular(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    rows.append(d)
    except OSError as e:
        return None, f"cannot read {path}: {e.strerror or type(e).__name__}"
    return rows, None


def int_in(v, lo, hi):
    """v as an int when it is a finite whole number inside [lo, hi] (a bool, NaN, Infinity, a string or a fraction is None: json.loads accepts NaN)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if isinstance(v, float) and (not math.isfinite(v) or v != int(v)):
        return None
    return int(v) if lo <= v <= hi else None


def proposal_from(rows, services, run=None, w_range=PROFILE_W_RANGE):
    """The bench's proposal from one run: {run, gpu, caps: {task: W}, needs: {task: MB}, notes, problems}. Only tasks the gate knows, caps inside
    the card's range, VRAM needs that are not informative-only (dynamic VRAM)."""
    recs = [r for r in rows if r.get("kind") == "recommend" and isinstance(r.get("run"), str) and SAFE_REF.fullmatch(r["run"])]
    runs = sorted({r["run"] for r in recs if r.get("cap_w") is not None or r.get("need_mb") is not None})
    out = {"run": None, "gpu": None, "caps": {}, "needs": {}, "notes": [], "problems": [], "ref_rows": 0}
    chosen = run or (runs[-1] if runs else None)
    if not chosen or chosen not in runs:
        out["problems"].append(f"run {run!r} has no recommendation in the results" if run else "the results hold no recommendation (kind=recommend with a cap or a need)")
        return out
    out["run"] = chosen
    sess = [r for r in rows if r.get("kind") == "session" and r.get("run") == chosen]
    g = sess[-1].get("gpu") if sess else None
    out["gpu"] = g.get("name") if isinstance(g, dict) and isinstance(g.get("name"), str) else None
    for r in [x for x in recs if x["run"] == chosen]:
        t = r.get("task")
        if not isinstance(t, str) or t not in services:
            out["notes"].append(f"{str(t)[:30]}: not a service of the gate, skipped")
            continue
        out["ref_rows"] += 1
        if r.get("gpu_unlock") == "off" and t in ("imggen", "vidgen"):
            out["notes"].append(f"{t}: measured with gpu-unlock off (the profile assumes it is on), skipped")
            continue
        cap = int_in(r.get("cap_w"), *w_range) if r.get("cap_w") is not None else None
        if r.get("cap_w") is not None and cap is None:
            out["notes"].append(f"{t}: cap {str(r.get('cap_w'))[:12]} W is outside the card's range {w_range[0]}-{w_range[1]} W (or not a whole number), skipped")
        elif cap is not None:
            out["caps"][t] = cap
        need = int_in(r.get("need_mb"), NEED_MB_RANGE[0], NEED_MB_RANGE[1]) if r.get("need_mb") is not None and not r.get("need_informative") else None
        if need is not None:
            out["needs"][t] = need
        elif r.get("need_mb") is not None and not r.get("need_informative"):
            out["notes"].append(f"{t}: VRAM need {str(r.get('need_mb'))[:12]} MB is not a whole number between {NEED_MB_RANGE[0]} and {NEED_MB_RANGE[1]}, skipped")
        elif r.get("need_informative") and r.get("need_mb") is not None:
            out["notes"].append(f"{t}: VRAM is informative only (dynamic VRAM), not written to gate.py")
    return out


def unified(label, old, new):
    return list(difflib.unified_diff(old.splitlines(), new.splitlines(), f"{label} (now)", f"{label} (proposed)", lineterm="", n=1))


def plan_profile(S, env, a, sd=None):
    """(lines, ok) of `plan profile`; with --apply one change at a time (flock), and the oldest backups beyond the keep limit are removed after a change."""
    sd = sd or state_dir()
    if not a.apply:
        return _plan_profile(S, env, a, sd)
    with change_lock(sd) as got:
        if not got:
            return ["upkeep plan profile: NOT APPLIED: another upkeep change is running (lock apply.lock in the state directory): wait for it to end"], False
        lines, ok = _plan_profile(S, env, a, sd)
        gone = prune_backups(sd, env) if "APPLIED" in lines else []
    return lines + ([f"pruned {len(gone)} old backup(s) (UPKEEP_KEEP_BACKUPS)"] if gone else []), ok


def _plan_profile(S, env, a, sd):
    """The body of `plan profile`: read the bench's proposal, show the diff of the deployed power_profiles.conf and gate/gate.py, and with --apply
    --confirm ID back both up, write them, restart the gate by the rules and log before and after. Non-root (the gate is a user unit)."""
    dest = dest_dir(a, env)
    conf_p, gate_p = os.path.join(dest, "power_profiles.conf"), os.path.join(dest, "gate", "gate.py")
    results = a.results or default_results()
    pre, inside_ck = dest_checks(S, env, a, dest, "a profile change")
    diff, body, prop = [], None, None
    cfg = gate_reads(env, dest)
    if cfg["tree"] and os.path.realpath(cfg["tree"]) != os.path.realpath(dest):
        pre.append(("NOT OK", "gate", f"the gate's unit runs gate.py from {cfg['tree']}, not from {dest}: editing {dest} would change files the gate never reads (--dest {shlex.quote(cfg['tree'])})"))
    if cfg.get("profiles_relative"):
        pre.append(("NOT OK", "gate", f"GATE_POWER_PROFILES is a relative path ({cfg['profiles'][:60]!r}): the gate resolves it against ITS working directory, which this tool cannot know. "
                                      "Make it absolute in the gate's env file or unit, then plan again"))
    elif os.path.realpath(cfg["profiles"]) != os.path.realpath(conf_p):
        pre.append(("NOT OK", "gate", f"the gate reads its power profiles from {cfg['profiles']} (GATE_POWER_PROFILES), not from {conf_p}: this tool will not edit a file the gate does not read"))
    elif cfg["unit"]:
        pre.append(("ok", "gate", f"the gate (unit {os.path.basename(cfg['unit']['path'])}) reads {conf_p}, runs gate.py from {dest} and takes its settings from {cfg['env_file']}"))
    else:
        pre.append(("note", "gate", "this account has no gate unit file (~/.config/systemd/user): the files the gate reads were taken from host.env and the environment, and the restart "
                                    "only works as the gate's own user: run this as that user"))
    for pth in (conf_p, gate_p):
        if special_file(pth):
            pre.append(("NOT OK", "destination", f"{os.path.relpath(pth, dest)} is not a regular file (a fifo, a device or a directory): nothing is read from it or written to it"))
        bad = link_in_path(pth, dest)
        if bad:
            pre.append(("NOT OK", "destination", f"{os.path.relpath(pth, dest)} is or sits behind a symlink ({os.path.basename(bad)[:40]}): this tool never replaces a symlink; point --dest at the real directory"))
    rows, prob = read_results(results)
    if rows is None:
        pre.append(("NOT OK", "results", prob))
    else:
        try:
            conf_t, gate_t = read_text(conf_p, keep_newlines=True), read_text(gate_p, keep_newlines=True)
        except OSError as e:
            conf_t = gate_t = None
            pre.append(("NOT OK", "deployed files", f"cannot read {conf_p} or {gate_p}: {e.strerror or type(e).__name__} (--dest DIR is the gpu-host copy the gate runs from)"))
        svc = services_of(gate_t) if gate_t else None
        if gate_t and svc is None:
            pre.append(("NOT OK", "gate.py", "cannot read the SERVICES table of the deployed gate.py"))
        gv0 = GateView(env)
        gst = (gv0.state or {}).get("gpu") or {}
        lo_w, hi_w = int_in(gst.get("min_w"), 1, 5000), int_in(gst.get("max_w"), 1, 5000)
        w_range = (lo_w, hi_w) if lo_w is not None and hi_w is not None and lo_w <= hi_w else PROFILE_W_RANGE
        if svc is not None:
            prop = proposal_from(rows, svc, a.run, w_range)
            for p in prop["problems"]:
                pre.append(("NOT OK", "results", p))
            for t, n in sorted(prop["needs"].items()):
                cur_n = svc[t][1]
                if cur_n > 0 and n < cur_n * (1 - MAX_NEED_DROP):
                    pre.append(("note" if a.allow_lower_need else "NOT OK", "need",
                                f"{t}: the VRAM need would fall from {cur_n} to {n} MB (more than {MAX_NEED_DROP:.0%}): a lower need lets the gate over-commit the card. "
                                + ("Accepted with --allow-lower-need." if a.allow_lower_need else "Measure again, or add --allow-lower-need if the owner agrees.")))
            for t, n in sorted(prop["needs"].items()):
                cur_n = svc[t][1]
                if cur_n > 0 and n > cur_n * MAX_NEED_RISE:
                    pre.append(("warn", "need", f"{t}: the VRAM need would grow from {cur_n} to {n} MB (more than {MAX_NEED_RISE:g}x): the gate may then refuse wakes the card could serve. Check the measurement"))
            if not prop["problems"]:
                pre.append(("ok", "results", f"run {prop['run']}: {len(prop['caps'])} power cap(s), {len(prop['needs'])} VRAM need(s) for {prop['gpu'] or 'an unknown card'} "
                                              f"({results})"))
                if not prop["gpu"]:
                    pre.append(("NOT OK", "card", "the run has no session row naming the card: cannot tell where the numbers were measured"))
                if not prop["caps"] and not prop["needs"]:
                    pre.append(("NOT OK", "proposal", "the run proposes nothing the gate can take"))
                pre += [("note", "skipped", n) for n in prop["notes"][:MAX_REASONS]]
        if prop and prop["gpu"] and conf_t is not None and not any(st == "NOT OK" for st, _n, _d in pre):
            sec = card_section(conf_t, prop["gpu"])
            live = gst.get("name")
            if not sec:
                pre.append(("NOT OK", "section", f"no section of power_profiles.conf matches the card {prop['gpu']!r}: add its [section] by hand (this tool never creates one)"))
            else:
                pre.append(("ok", "section", f"[{sec}] exists and is the one the gate uses for {prop['gpu']}"))
                if live and sec.lower() not in live.lower():
                    pre.append(("NOT OK", "card", f"the numbers were measured on {prop['gpu']!r} but this host's gate reports {live!r}"))
                elif not live:
                    pre.append(("note", "card", "the gate does not report the card name: the measured card was not compared with this host's"))
                new_conf, c_changes, c_prob = edit_conf(conf_t, sec, prop["caps"])
                new_gate, g_changes, g_prob = edit_services(gate_t, prop["needs"])
                for p in c_prob + g_prob:
                    pre.append(("NOT OK", "edit", p))
                if new_gate is not None and not g_prob:
                    now_s, new_s = services_of(gate_t), services_of(new_gate)
                    same_rest = new_s is not None and set(new_s) == set(now_s) and all(new_s[k][0] == now_s[k][0] and new_s[k][2] == now_s[k][2] for k in now_s)
                    if not same_rest:
                        pre.append(("NOT OK", "edit", "the edited SERVICES table changes more than the VRAM needs: not applied"))
                if not any(st == "NOT OK" for st, _n, _d in pre):
                    diff = unified("power_profiles.conf", conf_t, new_conf) + unified("gate/gate.py", gate_t, new_gate)
                    body = {"conf": new_conf, "gate": new_gate, "changes": [("cap",) + c for c in c_changes] + [("need",) + c for c in g_changes], "section": sec}
    if inside_ck and not any(st == "NOT OK" for st, _n, _d in pre):
        dirty, why_not = dirty_files(S, dest)
        mine = sorted(r for r in ("power_profiles.conf", "gate/gate.py") if dirty and r in dirty)
        if mine:
            pre.append(("warn", "git", "uncommitted changes in " + ", ".join(mine) + ": the profile edit goes on top of them (`git diff` shows them)"))
        elif dirty is None:
            pre.append(("note", "git", "cannot tell whether the tree is dirty: " + why_not))
        pre.append(("note", "git", "power_profiles.conf and gate/gate.py are tracked by git: after the change the checkout is dirty and a later `git pull` may conflict. Keep the "
                                   "measured values in a local commit, or expect `plan deploy` to revert them"))
    ok_pre = all(st != "NOT OK" for st, _n, _d in pre)
    out = [f"upkeep plan profile: run {prop['run'] if prop and prop['run'] else '?'}", checkout_header(), "",
           "PREFLIGHT" + ("" if ok_pre else "  (NOT OK: nothing is proposed until it is fixed)")] + pre_lines(pre)
    if not ok_pre:
        return out + ["", "NOT PROPOSED: fix what is NOT OK above and run this again."], False
    if not diff:
        return out + ["", "nothing to change: the deployed files already hold the proposal."], True
    cid = confirm_id(dest, "\n".join(diff))
    out += ["", "DIFF (nothing is written until --apply --confirm " + cid + ")"] + ["  " + d for d in diff]
    out += ["", f"{len(body['changes'])} change(s): " + "; ".join(f"{k} {t} {o if o is not None else '(new)'} -> {n}" for k, t, o, n in body["changes"][:12])]
    gv = GateView(env)
    action, why = restart_decision(env, gv, True, a.no_restart, a.restart_while_running)     # the gate reads both files only at its start
    out.append("gate restart: " + action + " -- " + why)
    inv = [UP, "plan profile"] + ([shlex.quote(a.results)] if a.results else []) + (["--run", a.run] if a.run else []) + (["--dest", shlex.quote(a.dest)] if a.dest else []) \
        + (["--ref", a.ref] if a.ref else []) + (["--allow-lower-need"] if a.allow_lower_need else []) + (["--no-restart"] if a.no_restart else []) \
        + (["--restart-while-running"] if a.restart_while_running else [])
    if not a.apply:
        steps = [("bot", "show the owner the DIFF above and say where the numbers come from (the bench run); ask before applying", "# nothing to run: read it to the owner in their language", "the owner says yes"),
                 ("bot", "apply: both files backed up with their md5, the proposal written, the gate restarted by the rule above, healthz and GET /state checked, before and after logged",
                  " ".join(inv + ["--apply", "--confirm", cid]), "RESULT: ok; the printed rollback line"),
                 ("bot", "if anything is worse (slower, costlier, a service that no longer starts): list the changes, then undo this one", [f"{UP} undo", f"{UP} undo ID --apply"], "RESULT: ok; the md5 equal the backup")]
        return out + ["", "STEPS"] + fmt_steps(steps), True
    if a.confirm != cid:
        return out + ["", f"NOT APPLIED: --confirm must be {cid} (the id of the diff above; it changes when the results or the files change)"], False
    if action == "refuse":
        return out + ["", "NOT APPLIED: " + why], False
    before_running = gv.busy_services() if gv.state is not None else []
    ch = new_change_id(sd, "profile")
    ref = f"bench_gate {prop['run']}" + (f"; {a.ref}" if a.ref else "") + f"; {prop['ref_rows']} recommendation row(s) of {os.path.basename(results)}"
    what = f"profile apply: {len(body['changes'])} change(s) for [{body['section']}] from {ref}"
    try:
        stored = make_backup(sd, ch, {"tree/power_profiles.conf": conf_p, "tree/gate/gate.py": gate_p})
    except OSError as err:
        append_log(sd, "profile-apply", "failed", what=what + f" (the backup could not be made: {err.strerror or type(err).__name__})", ref=ref)
        return out + ["", f"NOT APPLIED: the backup could not be made ({err.strerror or type(err).__name__}): nothing was changed."], False
    man = {"schema": 1, "id": ch, "kind": "profile", "at": int(time.time()), "dest": dest, "mcp": None, "what": what, "ref": ref, "restart_needed": True,
           "files": [{"store": "tree/power_profiles.conf", "path": conf_p, "existed": True, "md5_before": stored["tree/power_profiles.conf"], "md5_after": md5_bytes(body["conf"].encode()),
                      "mode_before": os.stat(conf_p).st_mode & 0o777},
                     {"store": "tree/gate/gate.py", "path": gate_p, "existed": True, "md5_before": stored["tree/gate/gate.py"], "md5_after": md5_bytes(body["gate"].encode()),
                      "mode_before": os.stat(gate_p).st_mode & 0o777}]}
    write_manifest(sd, ch, man)
    undo = f"{UP} undo {ch} --apply"
    append_log(sd, "profile-apply", "before", what=what, before={"power_profiles.conf": short(man["files"][0]["md5_before"]), "gate.py": short(man["files"][1]["md5_before"])},
               ref=ref, rollback=undo, note=("OVERRIDE: " + "; ".join(overrides(env)))[:900] if overrides(env) else None)
    res = [f"backup: {os.path.join(sd, 'backups', ch)} (both files, md5 {short(man['files'][0]['md5_before'])} and {short(man['files'][1]['md5_before'])})"]

    def restore_both():
        for e in man["files"]:
            if md5_path(e["path"]) == e["md5_before"]:
                continue                                      # never reached by the failed write: already as before
            with open_regular(os.path.join(sd, "backups", ch, e["store"]), "rb") as f:
                atomic_write(e["path"], f.read(), e["mode_before"], dest)
    try:
        for e, new in ((man["files"][0], body["conf"]), (man["files"][1], body["gate"])):
            atomic_write(e["path"], new.encode(), e["mode_before"], dest)
    except Exception as err:                                  # a full disk, a read-only file, a link that appeared: both files go back, the gate was not touched
        why_err = getattr(err, "strerror", None) or type(err).__name__
        try:
            restore_both()
            restored = all(md5_path(e["path"]) == e["md5_before"] for e in man["files"])
            back = "both files were restored from the backup; nothing changed." if restored else f"the restore left a file different from the backup: `{undo} --force`"
        except Exception as err2:
            restored, back = False, f"the restore ALSO failed ({getattr(err2, 'strerror', None) or type(err2).__name__}): `{undo} --force`"
        append_log(sd, "profile-apply", "failed" if restored else "failed-restore-failed", what=what + f" (the write failed: {why_err}" + ("" if restored else "; the restore FAILED") + ")",
                   ref=ref, rollback=None if restored else f"{undo} --force")
        return out + ["", f"FAILED: the write stopped ({why_err}); {back}"], False
    # the check of what was written: the same parse the gate does, and the table read back without running the file
    cp = configparser.ConfigParser(inline_comment_prefixes=("#",), interpolation=None)
    try:
        cp.read_string(read_text(conf_p))
        got = {k.lower(): float(v) for k, v in cp.items(body["section"])}
        svc2 = services_of(read_text(gate_p))
        good = all(got.get(t) == float(w) for t, w in prop["caps"].items()) and svc2 is not None and all(svc2[t][1] == n for t, n in prop["needs"].items())
    except (configparser.Error, OSError, ValueError, KeyError):
        good = False
    if not good:
        try:
            restore_both()
            restored = all(md5_path(e["path"]) == e["md5_before"] for e in man["files"])
        except Exception:
            restored = False
        append_log(sd, "profile-apply", "failed" if restored else "failed-restore-failed",
                   what=what + (" (read back wrongly: restored)" if restored else " (read back wrongly and the restore FAILED)"), ref=ref, rollback=None if restored else f"{undo} --force")
        return out + ["", "FAILED: the files read back wrongly; both were restored from the backup. Nothing changed." if restored
                      else f"FAILED: the files read back wrongly AND THE RESTORE FAILED: the files are NOT back as they were. `{undo} --force` once the cause is fixed."], False
    res.append("written: power_profiles.conf and gate/gate.py (read back: the section parses, the SERVICES table reads, only VRAM needs differ)")
    status, lines = "ok", []
    if action == "restart":
        status, lines = do_restart(S, env, before_running)
        if status == "failed":                                   # a gate that does not come back leaves the GPU out of rotation: restore at once, as a deploy does
            try:
                text, _undo_ok = undo_lines(S, env, sd, ch, man, True, True, False, True)
                restored = files_back(man)
            except Exception as err2:
                text, restored = [f"  the restore failed ({getattr(err2, 'strerror', None) or type(err2).__name__}): `{undo} --force`"], False
            append_log(sd, "profile-apply", "rolled-back" if restored else "rollback-failed",
                       what=what + (" (the gate did not come back: restored)" if restored else " (the gate did not come back and the restore FAILED)"), ref=ref, rollback=None if restored else f"{undo} --force")
            head = ("APPLIED, THEN ROLLED BACK: the gate does not answer after the restart." if restored
                    else f"APPLIED, THEN THE ROLLBACK FAILED: the gate does not answer after the restart and the files are NOT all back. `{undo} --force` once the cause is fixed.")
            return out + ["", head] + ["  " + x for x in res + lines] + text, False
    else:
        lines = ["gate restart: " + why]
    for e in man["files"]:
        e["md5_after"] = md5_path(e["path"])
    write_manifest(sd, ch, man)
    append_log(sd, "profile-apply", status, what=what, after={"power_profiles.conf": short(man["files"][0]["md5_after"]), "gate.py": short(man["files"][1]["md5_after"])}, ref=ref, rollback=undo)
    tail = [f"RESULT: {status}", "rollback: " + undo, "A cap or a need only counts once measured on the real jobs: re-bench after a driver, unlock or kernel change (`unlock` says when)."]
    return out + ["", "APPLIED"] + ["  " + x for x in res + lines] + tail, status == "ok"


MODULES["profile"] = (plan_profile, [("results", {"nargs": "?", "type": "path"}), ("--run", {"type": "ref"}), ("--dest", {"type": "path"}), ("--ref", {"type": "text"}),
                                     ("--confirm", {"type": "confirm"}), ("--allow-lower-need", {"action": "store_true"}), ("--no-restart", {"action": "store_true"}),
                                     ("--restart-while-running", {"action": "store_true"})])
ACTING = {"profile", "deploy"}                       # plan modules whose function does its own logging when --apply is given


# ------------------------------------------------------------------------------------------------------------------ gate deploy
def plan_deploy(S, env, a, sd=None):
    """(lines, ok) of `plan deploy`; with --apply one change at a time (flock), and the oldest backups beyond the keep limit are removed after a change."""
    sd = sd or state_dir()
    if not a.apply:
        return _plan_deploy(S, env, a, sd)
    with change_lock(sd) as got:
        if not got:
            return ["upkeep plan deploy: NOT APPLIED: another upkeep change is running (lock apply.lock in the state directory): wait for it to end"], False
        lines, ok = _plan_deploy(S, env, a, sd)
        gone = prune_backups(sd, env) if "APPLIED" in lines else []
    return lines + ([f"pruned {len(gone)} old backup(s) (UPKEEP_KEEP_BACKUPS)"] if gone else []), ok


def profile_reverts(sd, dest, dmd5, changed):
    """[(change id, rel)] of files a profile change (still in effect, from the manifests) wrote and this deploy would overwrite."""
    out = []
    for cid, man in list_changes(sd):
        if not man or man.get("kind") != "profile" or man.get("undone_at") or man.get("dest") != dest or not isinstance(man.get("files"), list):
            continue
        for e in man["files"]:
            st = e.get("store") if isinstance(e, dict) else None
            if isinstance(st, str) and st.startswith("tree/") and st[5:] in changed and dmd5.get(st[5:]) == e.get("md5_after"):
                out.append((cid, st[5:]))
    return out


def mcp_problem(path):
    """Why `path` may not be written as the separate mcp_dispatch.sh copy, or None: the name, a regular file or nothing, an existing directory."""
    if os.path.basename(path) != "mcp_dispatch.sh":
        return "the file name must be mcp_dispatch.sh (this tool writes that one file there, nothing else)"
    if os.path.islink(path):
        return "it is a symlink: this tool never replaces one. Give the real file with --mcp-dispatch, or skip it with --no-mcp-dispatch"
    if os.path.lexists(path) and not os.path.isfile(path):
        return "it exists and is not a regular file"
    if not os.path.isdir(os.path.dirname(path)):
        return "its directory does not exist"
    return None


def _plan_deploy(S, env, a, sd):
    """The body of `plan deploy`: a new gpu-host tree (from a git ref of this checkout, or a directory) over the deployed copy, with a full backup of
    the deployed tree, the host's own data left alone, md5 of gate.py before and after, the gate restarted by the rules, healthz and GET /state after.
    Also the separate mcp_dispatch.sh copy. Non-root."""
    dest = dest_dir(a, env)
    pre, inside_ck = dest_checks(S, env, a, dest, "a deploy")
    src, src_id = {}, None
    if bool(a.from_ref) == bool(a.from_dir):
        pre.append(("NOT OK", "source", "give exactly one of --from-ref REF (a commit of this checkout) or --from-dir DIR"))
    else:
        if a.from_ref:
            src, cid0, probs = ref_tree(S, a.from_ref)
            src_id = (cid0 or "?")[:12] + f" ({a.from_ref})"
        else:
            src, probs = read_dir_tree(os.path.abspath(a.from_dir))
            src_id = "directory " + os.path.abspath(a.from_dir)
            if os.path.realpath(a.from_dir) == os.path.realpath(dest):
                probs.append("the source and the destination are the same directory")
        for p in probs:
            pre.append(("NOT OK", "source", p))
        if not probs:
            if "gate/gate.py" not in src:
                pre.append(("NOT OK", "source", "no gate/gate.py in the source: not a gpu-host tree"))
            else:
                pre.append(("ok", "source", f"{src_id}: {len(src)} files (host data left alone: {', '.join(EXCLUDE_DIRS[:4])}/, host.env, *.log)"))
    dtree = {}
    if not os.path.isfile(os.path.join(dest, "gate", "gate.py")):
        pre.append(("NOT OK", "destination", f"{dest} has no gate/gate.py: not a deployed gpu-host tree, nothing is written into it (--dest DIR)"))
    else:
        dtree, skipped = walk_tree(dest)
        size = sum(sz for _p, sz in dtree.values())
        if size > MAX_TREE_MB * 2**20:
            pre.append(("NOT OK", "destination", f"the deployed tree is bigger than {MAX_TREE_MB} MB: not a gpu-host tree?"))
        else:
            pre.append(("ok", "destination", f"{dest}: {len(dtree)} files, {size // 1024} KB (the full backup copies exactly these)" + (f"; {skipped} symlink(s) left alone" if skipped else "")))
            probe = sd
            while probe and not os.path.isdir(probe) and probe != os.path.dirname(probe):
                probe = os.path.dirname(probe)
            try:
                st = os.statvfs(probe)
                free = st.f_frsize * st.f_bavail
            except OSError:
                free = None
            if free is not None and free < size + 20 * 2**20:
                pre.append(("NOT OK", "backup space", f"{free // 2**20} MB free for the backup, {size // 2**20 + 20} MB needed"))
    dmd5 = {r: md5_path(p) for r, (p, _s) in dtree.items()}
    smd5 = {r: md5_bytes(b) for r, (b, _m) in src.items()}
    changed = sorted(r for r in smd5 if r in dmd5 and smd5[r] != dmd5[r])
    added = sorted(r for r in smd5 if r not in dmd5) if dtree else []
    kept = sorted(r for r in dmd5 if r not in smd5)
    if src and dtree:
        links = []
        for r in changed + added:
            pth = os.path.join(dest, r)
            lk = link_in_path(pth, dest)
            if lk:
                links.append(f"{r} ({os.path.relpath(lk, dest)} is a symlink)")
            elif r in added and os.path.lexists(pth):
                links.append(f"{r} (exists and is not a regular file)")
        if links:
            pre.append(("NOT OK", "destination", f"{len(links)} file(s) would replace a symlink or sit behind one, or replace a special file: " + "; ".join(links[:4]) + (" ..." if len(links) > 4 else "")
                        + ". This tool never replaces or deletes a symlink (an undo would delete it): make the destination plain files, or deploy by hand"))
        cfg = gate_reads(env, dest)
        if cfg["tree"] and os.path.realpath(cfg["tree"]) != os.path.realpath(dest):
            pre.append(("warn", "gate", f"the gate's unit runs gate.py from {cfg['tree']}, not from {dest}: this deploy would not change what the gate runs"))
        elif cfg.get("profiles_relative"):
            pre.append(("warn", "gate", f"GATE_POWER_PROFILES is a relative path ({cfg['profiles'][:60]!r}): the gate resolves it against its own working directory, so this tool cannot tell whether power_profiles.conf of this tree is the file it uses"))
        elif os.path.realpath(cfg["profiles"]) != os.path.realpath(os.path.join(dest, "power_profiles.conf")):
            pre.append(("warn", "gate", f"the gate reads its power profiles from {cfg['profiles']} (GATE_POWER_PROFILES), so power_profiles.conf of this tree is not what it uses"))
        if inside(cfg["env_file"], dest) and os.path.exists(cfg["env_file"]):
            rel_ef = os.path.relpath(os.path.realpath(cfg["env_file"]), os.path.realpath(dest)).replace(os.sep, "/")
            if rel_ef in changed + added and not excluded(rel_ef):
                pre.append(("NOT OK", "gate env", f"the gate's env file ({rel_ef}, GATE_ENV_FILE) is inside the tree and the source has a file of that name: the deploy would overwrite the host's settings "
                                                  "and token. Move the env file out of the tree, or leave that file out of the source"))
        if cfg["unit"] is None:
            pre.append(("note", "gate", "this account has no gate unit file (~/.config/systemd/user): the restart only works as the gate's own user: run this as that user"))
        if inside_ck:
            dirty, why_not = dirty_files(S, dest)
            if dirty is None:
                pre.append(("note", "git", "cannot tell whether the tree is dirty: " + why_not))
            elif dirty:
                rev = sorted(r for r in changed if r in dirty)
                pre.append(("warn", "git", f"dirty git tree: {len(dirty)} file(s) of gpu-host/ have uncommitted changes" + (f"; this deploy would REVERT {len(rev)} of them to the source's copy: "
                            + ", ".join(rev[:6]) + (" ..." if len(rev) > 6 else "") if rev else "; none of them is touched by this deploy")))
        for cid_p, rel in profile_reverts(sd, dest, dmd5, changed)[:4]:
            pre.append(("warn", "profile", f"{rel} holds values written by profile change {cid_p} (measured on this host): this deploy overwrites them with the source's copy. Run `plan profile` again afterwards"))
        bad_py = []
        for r in changed + added:
            if r.endswith(".py"):
                try:
                    ast.parse(src[r][0])
                except (SyntaxError, ValueError):
                    bad_py.append(r)
        pre.append(("NOT OK" if bad_py else "ok", "syntax", ("does not compile: " + ", ".join(bad_py[:3])) if bad_py
                    else f"{sum(1 for r in changed + added if r.endswith('.py'))} changed Python file(s) compile"))
    mcp_path = None
    if not a.no_mcp_dispatch:
        cand = a.mcp_dispatch or os.path.join(os.path.expanduser("~"), "bin", "mcp_dispatch.sh")
        if a.mcp_dispatch or os.path.lexists(cand):
            mcp_path = os.path.abspath(cand)
    mcp_act = None
    mp = mcp_problem(mcp_path) if mcp_path else None
    if mp:
        pre.append(("NOT OK", "mcp_dispatch", f"{mcp_path}: {mp}"))
    elif mcp_path and src:
        if "mcp_dispatch.sh" not in src:
            pre.append(("NOT OK", "mcp_dispatch", "the source has no mcp_dispatch.sh"))
        else:
            cur = md5_path(mcp_path)
            mcp_act = "same" if cur == smd5["mcp_dispatch.sh"] else "added" if cur is None else "changed"
            pre.append(("ok", "mcp_dispatch", f"{mcp_path}: {mcp_act} (a plain copy with its own backup; resolve_mcp/ travels with the tree)"))
    elif a.no_mcp_dispatch:
        pre.append(("note", "mcp_dispatch", "skipped (--no-mcp-dispatch)"))
    gv = GateView(env)
    needed = any(r.startswith("gate/") or r == "power_profiles.conf" for r in changed + added)
    action, why = restart_decision(env, gv, needed, a.no_restart, a.restart_while_running)
    pre.append(("ok" if action != "refuse" else "wait", "gate restart", f"{action} -- {why}"))
    ok_pre = all(st != "NOT OK" for st, _n, _d in pre)
    out = [f"upkeep plan deploy: {src_id or '?'} -> {dest}", checkout_header(), "", "PREFLIGHT" + ("" if ok_pre else "  (NOT OK: nothing is deployed until it is fixed)")] + pre_lines(pre)
    if not ok_pre:
        return out + ["", "NO STEPS: fix what is NOT OK above and run this again."], False
    mcp_change = mcp_act in ("changed", "added")
    if not (changed or added or mcp_change):
        return out + ["", "nothing to deploy: the deployed tree already equals the source (excluding the host's own data)."], True
    gate_before, gate_after = dmd5.get("gate/gate.py"), smd5.get("gate/gate.py")
    out += ["", f"CHANGES: {len(changed)} changed, {len(added)} added, {len(kept)} only in the deployed tree (kept, never removed); gate.py md5 {short(gate_before)} -> {short(gate_after)}"]
    for r in capped(changed):
        if r.startswith("..."):
            out.append("  " + r)
            continue
        try:
            d = list(difflib.unified_diff(read_text(dtree[r][0]).splitlines(), src[r][0].decode("utf-8").splitlines(), lineterm="", n=0))
            out.append(f"  changed {r} (+{sum(1 for x in d if x.startswith('+') and not x.startswith('+++'))} -{sum(1 for x in d if x.startswith('-') and not x.startswith('---'))})")
        except (UnicodeDecodeError, OSError):
            out.append(f"  changed {r} (binary)")
    out += [("  added " + r) if not r.startswith("...") else "  " + r for r in capped(added)]
    if mcp_change:
        out.append(f"  {mcp_act} {mcp_path}")
    cid = confirm_id(dest, mcp_path or "", mcp_act or "", "\n".join(f"{r}={smd5[r]}" for r in changed + added))
    inv = [UP, "plan deploy"] + (["--from-ref", a.from_ref] if a.from_ref else ["--from-dir", shlex.quote(a.from_dir)]) + (["--dest", shlex.quote(a.dest)] if a.dest else []) \
        + (["--mcp-dispatch", shlex.quote(a.mcp_dispatch)] if a.mcp_dispatch else []) + (["--no-mcp-dispatch"] if a.no_mcp_dispatch else []) + (["--ref", a.ref] if a.ref else []) \
        + (["--no-restart"] if a.no_restart else []) + (["--restart-while-running"] if a.restart_while_running else [])
    if not a.apply:
        steps = [("bot", "tell the owner what changes (the counts above, gate.py's md5, whether the gate restarts) and ask before applying", "# nothing to run: read it to the owner in their language", "the owner says yes"),
                 ("bot", "apply: full backup of the deployed tree, the new files copied (the host's own data left alone), md5 checked, the gate restarted by the rule above, healthz and GET /state checked; a gate that does not come back is rolled back at once",
                  " ".join(inv + ["--apply", "--confirm", cid]), "RESULT: ok; gate.py md5 after equals the source's; the printed rollback line"),
                 ("bot", "if a service misbehaves afterwards: list the changes, then undo this one (restores the backup, restarts the gate by the same rule)", [f"{UP} undo", f"{UP} undo ID --apply"], "RESULT: ok")]
        return out + ["", "STEPS"] + fmt_steps(steps), True
    if a.confirm != cid:
        return out + ["", f"NOT APPLIED: --confirm must be {cid} (the id of the changes above; it changes when the source or the deployed tree change)"], False
    if action == "refuse":
        return out + ["", "NOT APPLIED: " + why], False
    before_running = gv.busy_services() if gv.state is not None else []
    ch = new_change_id(sd, "deploy")
    ref = (src_id or "") + (f"; {a.ref}" if a.ref else "")
    what = f"gate deploy: {len(changed)} changed, {len(added)} added from {ref}"
    copies = {"tree/" + r: p for r, (p, _s) in dtree.items()}
    if mcp_act in ("changed", "same") and mcp_path:
        copies["mcp/mcp_dispatch.sh"] = mcp_path
    try:
        stored = make_backup(sd, ch, copies)
    except OSError as err:
        append_log(sd, "gate-deploy", "failed", what=what + f" (the backup could not be made: {err.strerror or type(err).__name__})", ref=ref)
        return out + ["", f"NOT APPLIED: the backup could not be made ({err.strerror or type(err).__name__}): nothing was changed."], False
    files = []
    for r in changed + added:
        files.append({"store": "tree/" + r, "path": os.path.join(dest, r), "existed": r in dmd5, "md5_before": stored.get("tree/" + r), "md5_after": smd5[r],
                      "mode_before": os.stat(dtree[r][0]).st_mode & 0o777 if r in dtree else None, "mode_new": src[r][1]})
    if mcp_change:
        files.append({"store": "mcp/mcp_dispatch.sh", "path": mcp_path, "existed": mcp_act == "changed", "md5_before": stored.get("mcp/mcp_dispatch.sh"),
                      "md5_after": smd5["mcp_dispatch.sh"], "mode_before": os.stat(mcp_path).st_mode & 0o777 if mcp_act == "changed" else None, "mode_new": src["mcp_dispatch.sh"][1]})
    man = {"schema": 1, "id": ch, "kind": "deploy", "at": int(time.time()), "dest": dest, "mcp": mcp_path, "what": what, "ref": ref, "restart_needed": needed, "files": files}
    write_manifest(sd, ch, man)
    undo = f"{UP} undo {ch} --apply"
    append_log(sd, "gate-deploy", "before", what=what, before={"gate.py": short(gate_before), "tree": short(tree_digest(dmd5)), "files": str(len(dmd5))}, ref=ref, rollback=undo,
               note=("OVERRIDE: " + "; ".join(overrides(env)))[:900] if overrides(env) else None)
    res = [f"backup: {os.path.join(sd, 'backups', ch)} ({len(dtree)} files of the deployed tree{', plus mcp_dispatch.sh' if 'mcp/mcp_dispatch.sh' in copies else ''}, md5 per file in the manifest)"]
    try:
        for e in files:
            rel = e["store"][5:] if e["store"].startswith("tree/") else "mcp_dispatch.sh"
            mode = e["mode_new"] if e["mode_before"] is None else e["mode_before"] | (e["mode_new"] & 0o111)
            atomic_write(e["path"], src[rel][0], mode, dest if e["store"].startswith("tree/") else None)
    except Exception as err:                                  # a full disk, a read-only file, a link that appeared: EVERYTHING goes back (the gate was not touched)
        why_err = getattr(err, "strerror", None) or type(err).__name__
        try:
            text, _undo_ok = undo_lines(S, env, sd, ch, man, True, True, True, False)
            restored = files_back(man)
        except Exception as err2:
            text, restored = [f"  the restore ALSO failed ({getattr(err2, 'strerror', None) or type(err2).__name__}): `{undo} --force`"], False
        append_log(sd, "gate-deploy", "failed" if restored else "failed-restore-failed",
                   what=what + f" (the copy stopped: {why_err}; " + ("restored" if restored else "the restore FAILED: the tree is half-deployed") + ")", ref=ref, rollback=None if restored else f"{undo} --force")
        head = (f"FAILED: the copy stopped midway ({why_err}); every file was put back from the backup (the gate was not touched)." if restored
                else f"FAILED: the copy stopped midway ({why_err}) AND THE RESTORE FAILED: the deployed tree is HALF-DEPLOYED (the gate was not restarted). Fix the cause, then `{undo} --force` (the backup is intact).")
        return out + ["", head] + text, False
    wrong = [e["store"] for e in files if md5_path(e["path"]) != e["md5_after"]]
    if wrong:
        try:
            text, _undo_ok = undo_lines(S, env, sd, ch, man, True, True, True, False)
            restored = files_back(man)
        except Exception as err2:
            text, restored = [f"  the restore ALSO failed ({getattr(err2, 'strerror', None) or type(err2).__name__}): `{undo} --force`"], False
        append_log(sd, "gate-deploy", "failed" if restored else "failed-restore-failed",
                   what=what + " (copy did not read back; " + ("restored" if restored else "the restore FAILED: the tree is half-deployed") + ")", ref=ref, rollback=None if restored else f"{undo} --force")
        head = ("FAILED: a file does not read back with the source's md5 (" + ", ".join(wrong[:3]) + "); the backup was restored (the gate was not touched)." if restored
                else "FAILED: a file does not read back with the source's md5 (" + ", ".join(wrong[:3]) + f") AND THE RESTORE FAILED: the tree is HALF-DEPLOYED. `{undo} --force` once the cause is fixed.")
        return out + ["", head] + text, False
    res.append(f"copied {len(files)} file(s); every md5 equals the source's; gate.py md5 {short(gate_before)} -> {short(md5_path(os.path.join(dest, 'gate', 'gate.py')))}")
    status, lines = "ok", []
    if action == "restart":
        status, lines = do_restart(S, env, before_running)
        if status == "failed":                                   # a gate that does not come back leaves the GPU out of rotation: restore at once
            try:
                text, _undo_ok = undo_lines(S, env, sd, ch, man, True, True, False, True)
                restored = files_back(man)
            except Exception as err2:
                text, restored = [f"  the restore failed ({getattr(err2, 'strerror', None) or type(err2).__name__}): `{undo} --force`"], False
            append_log(sd, "gate-deploy", "rolled-back" if restored else "rollback-failed",
                       what=what + (" (the gate did not come back: restored)" if restored else " (the gate did not come back and the restore FAILED)"), ref=ref, rollback=None if restored else f"{undo} --force")
            head = ("APPLIED, THEN ROLLED BACK: the gate does not answer after the restart." if restored
                    else f"APPLIED, THEN THE ROLLBACK FAILED: the gate does not answer after the restart and the files are NOT all back. `{undo} --force` once the cause is fixed.")
            return out + ["", head] + ["  " + x for x in res + lines] + text, False
    else:
        lines = ["gate restart: " + why]
    append_log(sd, "gate-deploy", status, what=what, after={"gate.py": short(md5_path(os.path.join(dest, "gate", "gate.py"))),
                                                           "tree": short(tree_digest({r: md5_path(p) for r, (p, _s) in walk_tree(dest)[0].items()}))}, ref=ref, rollback=undo)
    return out + ["", "APPLIED"] + ["  " + x for x in res + lines] + [f"RESULT: {status}", "rollback: " + undo], status == "ok"


MODULES["deploy"] = (plan_deploy, [("--from-ref", {"type": "gitref"}), ("--from-dir", {"type": "path"}), ("--dest", {"type": "path"}), ("--mcp-dispatch", {"type": "path"}),
                                   ("--no-mcp-dispatch", {"action": "store_true"}), ("--ref", {"type": "text"}), ("--confirm", {"type": "confirm"}),
                                   ("--no-restart", {"action": "store_true"}), ("--restart-while-running", {"action": "store_true"})])


# ------------------------------------------------------------------------------------------------------------------ unlock check
def fingerprint_now(f):
    """What a bench measurement belongs to: driver, running kernel, gpu-unlock package versions."""
    return {"driver": f["driver"], "kernel": f["running"], "gpu-unlock-dkms": f["installed"].get("gpu-unlock-dkms"), "gpu-unlock-firmware": f["installed"].get("gpu-unlock-firmware")}


def rebench_due(sd, f):
    """(due?, why): the last `bench` line of the log carries the fingerprint it was done at (log --add bench ...); a different driver, kernel or
    gpu-unlock since then means the profile numbers are not measured on this setup any more."""
    last = [e for e in read_log(sd) if e.get("step") == "bench"]
    if not last:
        return None, "no bench recorded in this log (after a bench: `log --add bench --result done --ref RUN --apply`)"
    then, now = last[-1].get("versions") or {}, fingerprint_now(f)
    diff = [f"{k} {then.get(k) or '?'} -> {now.get(k) or '?'}" for k in ("driver", "kernel", "gpu-unlock-dkms", "gpu-unlock-firmware") if then.get(k) != now.get(k)]
    return bool(diff), ("; ".join(diff) if diff else f"same driver, kernel and gpu-unlock as the bench of {last[-1].get('at')}")


def unlock_eval(f, env, sd, kernel=None):
    """(verdict, [(status, name, detail)], notes): ok | degraded | unknown. degraded: the selfcheck says so, or a package or a DKMS build of the unlock is
    missing. unknown: nothing installed, no fresh selfcheck result for this driver, kernel and unlock version, or the selfcheck could not judge."""
    items, notes = [], []
    drv, run = f["driver"], f["running"]
    inst = f["installed"]
    dk, fw = inst.get("gpu-unlock-dkms"), inst.get("gpu-unlock-firmware")
    if not dk:
        items.append(("--", "packages", "gpu-unlock-dkms is not installed here: no unlock to judge"))
        return "unknown", items, notes
    items.append(("ok" if fw else "FAIL", "packages", f"gpu-unlock-dkms {dk}, gpu-unlock-firmware {fw or 'MISSING'}"))
    if not drv:
        items.append(("--", "driver", "nvidia-smi does not answer: the loaded driver is unknown"))
    kern = [k for k in f["kernels"] if k in f["headers"]]
    miss = []
    for k in kern + ([kernel] if kernel and kernel not in kern else []):
        if drv and not any(r[0] == "nvidia" and r[2] == k and r[3] == "installed" and r[1] == drv for r in f["dkms"]):
            miss.append(f"nvidia/{drv} for {k}")
        if not any(re.match(r"^gpu[-_]unlock", r[0]) and r[2] == k and r[3] == "installed" for r in f["dkms"]):
            miss.append(f"gpu-unlock for {k}")
    items.append(("ok" if kern and not miss else "FAIL", "dkms", f"nvidia/{drv} and gpu-unlock built for {len(kern)} kernel(s) with headers" if kern and not miss
                  else ("no kernel with headers" if not kern else "missing: " + "; ".join(miss[:4]))))
    nh = nohead_item(f, boot_kernels(env))
    if nh:
        items.append(nh)
    if kernel:
        have = f"linux-image-{kernel}" in inst and kernel in f["headers"]
        built = not any(kernel in m for m in miss)
        items.append(("ok" if have and built else "FAIL", "new kernel", f"{kernel}: image, headers and DKMS builds of nvidia and gpu-unlock are there: it may boot" if have and built
                      else f"{kernel}: " + ("image or headers not installed" if not have else "no DKMS build of nvidia or gpu-unlock") + ". DO NOT RESTART the host into it"))
    sc = SC.read_json(os.path.join(SC.state_dir_of(env), "selfcheck.json")) or {}
    fp = sc.get("fingerprint") or {}
    if not sc:
        items.append(("--", "selfcheck", "no result yet (`unlock --run --apply` measures now; the timer does it at boot and after changes)"))
    else:
        age = (time.time() - (sc.get("at") or 0)) / 3600
        stale = [x for x, p, q in (("driver", sc.get("driver"), drv), ("kernel", fp.get("kernel"), run), ("gpu-unlock", fp.get("unlock_pkg"), dk)) if p and q and p != q]
        words = ",".join(str(x) for x in (sc.get("reasons") or [])[:3])
        if sc.get("verdict") == "degraded":
            items.append(("FAIL", "selfcheck", f"degraded ({words or 'no reason'}), {age:.1f} h ago: the card is slower than unlocked and costs more energy for the same work"))
        elif sc.get("verdict") == "error":
            items.append(("--", "selfcheck", f"could not judge ({words or 'error'}), {age:.1f} h ago"))
        elif stale:
            items.append(("--", "selfcheck", f"ok {age:.1f} h ago, but for another {', '.join(stale)}: run `unlock --run --apply`"))
        elif sc.get("verdict") == "ok":
            items.append(("ok", "selfcheck", f"ok {age:.1f} h ago (driver {sc.get('driver')}, kernel {fp.get('kernel')}" + (f", ratio {sc['ratio']}" if sc.get("ratio") else "") + ")"))
        else:
            items.append(("--", "selfcheck", "no verdict in the last result"))
    dw = SC.read_json(os.path.join(SC.state_dir_of(env), "driver_watch.json")) or {}
    up = dw.get("unlock_upstream")
    det = dw.get("unlock_upstream_detail") or {}
    if up == "stable_newer":
        notes.append(f"a newer stable gpu-unlock exists upstream ({det.get('stable_latest', '?')}, installed {dk}): a performance change, measure first (selfcheck, bench), then update like the driver")
    elif up == "beta_only":
        notes.append("only a pre-release newer than the installed gpu-unlock exists upstream: not recommended")
    elif up == "unknown" or not dw:
        notes.append("upstream gpu-unlock versions are not known (driver_watch has no answer): `python3 gpu-host/driver_watch.py run`")
    if dw.get("unlock_candidate"):
        notes.append(f"the apt repository offers gpu-unlock-dkms {dw['unlock_candidate']} (installed {dk})")
    if dw.get("at") and time.time() - dw["at"] > 3 * 86400:
        notes.append(f"driver_watch's last answer is {(time.time() - dw['at']) / 86400:.0f} days old")
    st = [s for s, _n, _d in items]
    verdict = "degraded" if "FAIL" in st else "unknown" if "--" in st else "ok"
    return verdict, items, notes


def unlock_check(S, env, a, sd):
    """(lines, exit code) of `unlock`: 0 ok, 1 degraded, 2 unknown. With --run --apply the selfcheck measures first."""
    sd = sd or state_dir()
    f = facts(S)
    out, ran = [], None
    if a.run:
        if not a.apply:
            ran = "not run without --apply (it measures the card for a few seconds)"
        else:
            code, line, was = selfcheck_guarded(env, sd, "unlock")
            ran = f"selfcheck exit {code}: {line}" + ("; the gate stays CLOSED (busy switch back on)" if was and code != 0 else "; the gate is open again" if was else "")
    verdict, items, notes = unlock_eval(f, env, sd, a.kernel)
    out.append(f"unlock: {verdict} (driver {f['driver'] or '?'}, gpu-unlock-dkms {f['installed'].get('gpu-unlock-dkms') or 'none'}, kernel {f['running'] or '?'})")
    if ran:
        out.append("  --    run: " + ran)
    out += [f"  {st:5} {n}: {d}" for st, n, d in items]
    due, why = rebench_due(sd, f)
    out.append("  note  rebench: " + (f"DUE ({why}): bench the real jobs, then `plan profile` proposes the numbers" if due else why))
    out += ["  note  " + n for n in notes]
    if verdict == "degraded":
        out.append("  next: do not hide it. The unlock is the speed-up: a driver or kernel update is rolled back (`rollback`), a missing DKMS build is fixed before the next restart")
    if a.apply:
        append_log(sd, "unlock-check", verdict, {"driver": f["driver"], "gpu-unlock-dkms": f["installed"].get("gpu-unlock-dkms"), "kernel": f["running"]},
                   "; ".join(f"{n}: {d}" for st, n, d in items if st in ("FAIL", "--"))[:300] or None,
                   what="unlock check" + (" after a selfcheck run" if a.run else ""), after={"verdict": verdict, "driver": f["driver"], "kernel": f["running"]})
    return out, {"ok": 0, "degraded": 1, "unknown": 2}[verdict]


CHECKS = {"unlock": (unlock_check, [("--run", {"action": "store_true"}), ("--kernel", {"type": "kernel"})])}      # top-level checks (one function, one entry)


# ------------------------------------------------------------------------------------------------------------------ kernel update (print-only)
def check_kernel_sim(text, headers=(), running=None, extra_protect=(), allow_remove=(), target=None):
    """Judge `apt install -s linux-image-amd64 linux-headers-amd64` for a kernel update. Pure. Every new kernel image needs its headers (installed
    now or in the same transaction), or DKMS cannot build nvidia and gpu-unlock for it and grub boots it anyway. Nothing may be removed."""
    s = parse_sim(text)
    reasons, notes = [], []
    new = sorted({n[len("linux-image-"):] for n, _o, _v in s["inst"] if re.match(r"^linux-image-\d", n) and not re.search(r"-(dbg|unsigned)$", n)}, key=kernel_key)
    hdr = {n[len("linux-headers-"):] for n, _o, _v in s["inst"] if re.match(r"^linux-headers-\d", n)} | set(headers)
    reasons += [f"apt reports: {e}" for e in s["errors"]]
    if not new:
        reasons.append("this simulation installs no new kernel image")
    if target and new and target not in new:
        reasons.append(f"the new kernel here is {', '.join(new)}, not {target}")
    for k in new:
        if k not in hdr:
            reasons.append(f"kernel {k} comes without its headers (linux-headers-{k}): DKMS cannot build nvidia and gpu-unlock for it, and grub boots the newest kernel")
    drv = sorted(n for n, _o, _v in s["inst"] if is_family(n) or PIN_RE.match(strip_arch(n)) or UNLOCK_RE.match(strip_arch(n)))
    if drv:
        reasons.append(f"this kernel update also installs or upgrades {len(drv)} driver or gpu-unlock package(s) ({_list_pkgs(drv, 4)}): the driver has its own procedure "
                       f"(`plan driver`) with the pin and a snapshot; do not mix it into the kernel update")
    oth = sorted(n for n, _o, _v in s["inst"] if n not in drv and not re.match(r"^(linux-|dkms$)", strip_arch(n)))
    if oth:
        notes.append(f"also installs or upgrades {len(oth)} other package(s) that are not kernel packages: {_list_pkgs(oth)}")
    prot = [re.compile(p) for p in PROTECTED + list(extra_protect)]
    if running:
        prot += [re.compile("^linux-image-" + re.escape(running) + "$"), re.compile("^linux-headers-" + re.escape(running) + "$")]
    for n in s["remv"]:
        b = strip_arch(n)
        if any(p.match(b) for p in prot):
            reasons.append(f"removes a protected package: {n}")
        elif any(p.fullmatch(b) for p in allow_remove):
            notes.append(f"removes {n}: allowed by UPKEEP_ALLOW_REMOVE")
        else:
            reasons.append(f"removes {n}: a kernel update removes nothing (UPKEEP_ALLOW_REMOVE lists exceptions)")
    if not reasons:
        notes.append(f"new kernel(s): {', '.join(new)}; images and headers together, nothing removed. Next: install, then `unlock --kernel {new[-1]}` BEFORE the restart")
    return _finish(" ".join(new) or None, reasons, notes, len(new))


def plan_kernel(S, env, a, sd=None):
    """(lines, ok) of `plan kernel`: the procedure for a kernel update on the GPU host, PRINT-ONLY. The rule it exists for: nvidia and gpu-unlock must
    be built by DKMS for the new kernel before the host restarts into it."""
    sd = sd or state_dir()
    f = facts(S)
    dw = SC.read_json(os.path.join(SC.state_dir_of(env), "driver_watch.json")) or {}
    pend = [k for k in (dw.get("pending_kernels") or []) if isinstance(k, str) and KERNEL_RE.fullmatch(k)]
    target = a.to or (pend[0] if len(pend) == 1 else None)
    pre = []
    if target:
        pre.append(("ok", "kernel", f"{target}" + (" (the one driver_watch sees pending)" if not a.to else "") + f"; running {f['running'] or '?'}"))
    else:
        pre.append(("NOT OK", "kernel", "no --to RELEASE and driver_watch does not show exactly one pending kernel: `python3 gpu-host/driver_watch.py run`, or pass --to"))
    verdict, items, _notes = unlock_eval(f, env, sd)
    pre.append(("ok" if verdict == "ok" else "note", "unlock now", verdict + ("" if verdict == "ok" else ": " + "; ".join(d for st, _n, d in items if st in ("FAIL", "--"))[:200])))
    if not f["driver"]:
        pre.append(("NOT OK", "driver", "nvidia-smi does not answer: the installed driver is unknown"))
    gaps = DW.dkms_gaps([k for k in f["kernels"] if k in f["headers"]], f["dkms"])
    pre.append(("ok" if not gaps else "note", "dkms now", "built for every kernel with headers" if not gaps else "already missing: " + "; ".join(f"{m} for {k}" for k, m in gaps)))
    nohead = kernels_without_headers(f, boot_kernels(env))
    if nohead:
        pre.append(("note", "kernels", "installed without headers: " + " ".join(nohead[:4])))
    free, need = boot_info(env)
    pre.append(("note", "/boot", "cannot read the free space") if free is None else
               ("ok" if free >= need else "NOT OK", "/boot", f"{free} MB free, {need} MB needed (one more kernel and initramfs, and DKMS rebuilds them)"))
    gv = GateView(env)
    idle, why = gv.idle(os.path.exists(busy_path(env)))
    pre.append(("ok" if idle else "wait" if gv.state is not None else "NOT OK", "gate idle", why))
    ok_all = all(st != "NOT OK" for st, _n, _d in pre)
    out = [f"upkeep plan kernel: {f['running'] or '?'} -> {target or '?'}  (print-only)", checkout_header(), "",
           "PREFLIGHT" + ("" if ok_all else "  (NOT OK: no steps are printed until it is fixed)")] + pre_lines(pre)
    if not ok_all:
        return out + ["", "NO STEPS: fix what is NOT OK above and run this again."], False
    steps = [
        ("bot", "close the gate to new wakes", f"{UP} busy on --apply", "busy: on"),
        ("bot", "wait until nothing runs on the card", f"{UP} idle", "idle: yes"),
        ("bot", "record the installed versions (the rollback source for the packages)", f"{UP} snapshot --apply", "snapshot saved: <id>"),
        ("owner", "refresh the package lists", "sudo apt update", "no errors"),
        ("owner-nr", "simulate the kernel packages (image and headers together) and let the tool read it", f"apt install -s --no-remove linux-image-amd64 linux-headers-amd64 2>&1 | {UP} check-sim - --kernel --to {target}",
         "check-sim: ok. Not ok: a kernel without headers, or anything removed"),
        ("owner", "install the kernel image and headers (DKMS builds nvidia and gpu-unlock for the NEW kernel now; minutes)", "sudo apt install --no-remove linux-image-amd64 linux-headers-amd64",
         f"no errors; DKMS 'Installing to /lib/modules/{target}/updates/dkms' for nvidia and gpu-unlock"),
        ("bot", f"THE GATE before the restart: nvidia and gpu-unlock are built for {target}", [f"{UP} unlock --kernel {target}", "dkms status"],
         "unlock: ok and 'ok new kernel'. A FAIL means do NOT restart the host: fix the DKMS build first (a restart into a kernel without the module comes up without the driver)"),
        ("owner", "restart the host in a quiet window (the gate stays closed; the stacks use the next host)", "sudo reboot", "the host comes back on the new kernel; the gate answers GET /healthz"),
        ("bot", "after the restart: the unlock selfcheck decides (the gate opens again only on ok; pass timeout=300 to hostcare; the selfcheck itself stops at 240 s)", f"{UP} unlock --run --apply",
         "unlock: ok (driver, kernel and gpu-unlock all match the result). degraded or unknown: the gate stays closed"),
        ("bot", "the kernel changed: re-bench the real jobs, then let the bench propose the numbers and apply them with the owner's yes",
         ["python3 gpu-host/bench_gate.py --recheck", f"{UP} plan profile", f"{UP} log --add bench --result done --ref RUN --apply"], "no slowdown, no extra Wh; otherwise go back to the old kernel"),
    ]
    out += ["", "STEPS (print-only: the tool changes nothing here; [owner, root] you run as root, [bot, no root] the bot runs)"] + fmt_steps(steps)
    out += ["", f"ROLLBACK: no package change is needed. At the next restart choose the previous kernel ({f['running'] or 'the old one'}) in the boot menu (it stays installed); once the host is on it, "
                f"`{UP} unlock --run --apply`. Remove the new kernel only after that, by the owner."]
    return out, True


MODULES["kernel"] = (plan_kernel, [("--to", {"type": "kernel"})])


# ------------------------------------------------------------------------------------------------------------------ CLI
def cmd_log(sd, args, S=None, env=None):
    if args.add:
        if not args.apply:
            print("log: --add needs --apply (it appends a line)")
            return 2
        versions = None
        if args.add == "bench" and S is not None:                 # a bench line carries the driver, kernel and unlock it was measured on: `unlock` says when it is due again
            versions = {k: x for k, x in fingerprint_now(facts(S)).items() if x}
        e = append_log(sd, args.add, args.result or "done", versions, args.note, ref=args.ref)
        print("logged: " + e["step"] + " " + e["result"])
        return 0
    rows = read_log(sd)
    if args.history:
        rows = [e for e in rows if any(k in e for k in ("what", "before", "after", "rollback"))]
    rows = rows[-(args.n or 50):]
    if not rows:
        print("no upkeep log yet" if not args.history else "no changes in the log yet")
        return 0
    for e in rows:
        if args.json:
            print(json.dumps(e, sort_keys=True))
        elif args.history:
            print(f"{e.get('at')}  {e.get('step'):<14} {e.get('result'):<10} {e.get('what', '')}")
            for k in ("before", "after"):
                if e.get(k):
                    print(f"    {k}: " + " ".join(f"{a}={b}" for a, b in sorted(e[k].items())))
            for k in ("ref", "rollback", "note"):
                if e.get(k):
                    print(f"    {k}: {e[k]}")
        else:
            v = " ".join(f"{k}={x}" for k, x in sorted((e.get("versions") or {}).items()) if x)
            print(f"{e.get('at')}  {e.get('step'):<18} {e.get('result'):<10} {v}" + (f"  {e['what']}" if e.get("what") else "") + (f"  {e['note']}" if e.get("note") else ""))
    return 0


def target_arg(text):
    """A driver version typed by a person, fullmatch: it ends up inside `sudo apt install` lines."""
    if not TARGET_RE.fullmatch(text or ""):
        raise argparse.ArgumentTypeError(f"{text[:40]!r} is not a driver version like 595.112.07")
    return text


def _rx(pattern, what):
    def conv(text):
        if not pattern.fullmatch(text or ""):
            raise argparse.ArgumentTypeError(f"{(text or '')[:40]!r} is not {what}")
        return text
    return conv


def path_arg(text):
    """A path typed by a person: it is printed into command lines, so no control characters and a sane length."""
    if not text or len(text) > 400 or re.search(r"[\x00-\x1f\x7f]", text):
        raise argparse.ArgumentTypeError("not a usable path")
    return text


ARG_TYPES = {"target": target_arg, "kernel": _rx(KERNEL_RE, "a kernel release like 6.12.115+deb13.1-amd64"), "ref": _rx(SAFE_REF, "a run id"),
             "text": _rx(SAFE_TEXT, "a short reference (letters, digits and . _ : / + @ = -)"), "gitref": None, "confirm": _rx(CONFIRM_RE, "a confirm id (12 hex digits)"), "path": path_arg}


def gitref_arg(text):
    if not SAFE_GITREF.fullmatch(text or "") or ".." in text:
        raise argparse.ArgumentTypeError(f"{(text or '')[:40]!r} is not a branch, tag or commit name")
    return text


ARG_TYPES["gitref"] = gitref_arg


def add_specs(parser, specs):
    for flag, kw in specs:
        kw = dict(kw)
        if kw.get("type") in ARG_TYPES:
            kw["type"] = ARG_TYPES[kw["type"]]
        parser.add_argument(flag, **kw)


def to_or_kernel(text):
    """check-sim's --to: a driver version, or a kernel release (only meaningful with --kernel; dispatch refuses it otherwise). Fullmatch either way."""
    if not (TARGET_RE.fullmatch(text or "") or KERNEL_RE.fullmatch(text or "")):
        raise argparse.ArgumentTypeError(f"{(text or '')[:40]!r} is not a driver version like 595.112.07 or a kernel release")
    return text


def main(argv=None, deps=None):
    deps = deps or {}
    ap = argparse.ArgumentParser(prog="upkeep.py", description="Update a host with a procedure, a rollback and an audit log.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--apply", action="store_true", help="do the no-root steps (busy, snapshot, verify's selfcheck, log lines); default is print-only")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", parents=[common], help="preflight and ordered steps for one procedure")
    ps = p.add_subparsers(dest="module", required=True)
    for name, (_fn, args) in MODULES.items():
        add_specs(ps.add_parser(name, parents=[common]), args)
    for name, (_fn, args) in CHECKS.items():
        add_specs(sub.add_parser(name, parents=[common]), args)
    u = sub.add_parser("undo", parents=[common], help="list the changes that have a backup, or restore one exactly")
    u.add_argument("change", nargs="?", type=_rx(SAFE_CHANGE, "a change id (`undo` lists them)"))
    u.add_argument("--force", action="store_true", help="restore although the files changed after the change (a later change is lost)")
    u.add_argument("--no-restart", action="store_true")
    u.add_argument("--restart-while-running", action="store_true")
    c = sub.add_parser("check-sim", parents=[common])
    c.add_argument("file", nargs="?", default="-")
    c.add_argument("--to", metavar="VERSION", type=to_or_kernel, help="the driver version (or, with --kernel, the kernel release) it must reach")
    cm = c.add_mutually_exclusive_group()
    cm.add_argument("--pin", action="store_true", help="judge TRANSACTION 1: the new pin alone (plus the container toolkit)")
    cm.add_argument("--rollback-from", metavar="SNAPSHOT", help="judge a rollback simulation: packages that are not in this snapshot may be removed")
    cm.add_argument("--kernel", action="store_true", help="judge the simulation of a kernel update: every new kernel image comes with its headers, nothing is removed")
    v = sub.add_parser("verify", parents=[common])
    v.add_argument("--to", required=True, metavar="VERSION", type=target_arg)
    v.add_argument("--installed", dest="installed_only", action="store_true")
    r = sub.add_parser("rollback", parents=[common])
    r.add_argument("snapshot", nargs="?")
    s = sub.add_parser("snapshot", parents=[common])
    s.add_argument("--list", action="store_true")
    s.add_argument("--force", action="store_true", help="save it although the host is not in a clean state (a half-updated state is NOT the rollback)")
    b = sub.add_parser("busy", parents=[common])
    b.add_argument("state", choices=["on", "off", "status"])
    sub.add_parser("idle", parents=[common])
    lg = sub.add_parser("log", parents=[common])
    lg.add_argument("-n", type=int)
    lg.add_argument("--json", action="store_true")
    lg.add_argument("--add", metavar="STEP")
    lg.add_argument("--result")
    lg.add_argument("--note")
    lg.add_argument("--ref", type=ARG_TYPES["text"], help="the measurement a change rests on (a bench run id, a results file)")
    lg.add_argument("--history", action="store_true", help="only the changes, with what, before, after, the measurement and the rollback command")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])
    env = deps.get("env") if deps.get("env") is not None else SC.load_env()
    env.update({k: x for k, x in os.environ.items() if k.startswith("UPKEEP_")})      # UPKEEP_STATE_DIR, _BOOT_DIR, _BOOT_MIN_MB, _PROTECT, _ALLOW_REMOVE, _SELFCHECK+_TEST
    sd = state_dir()
    S = deps.get("sys") or Sys(env.get("UPKEEP_CHECKOUT") if test_mode(env) else None)      # a checkout other than this one: the selftest only
    try:
        return dispatch(a, S, env, sd)
    except Refused as e:
        print("upkeep: refused: " + str(e), file=sys.stderr)
        return 2
    except OSError as e:                                      # a symlinked or unwritable audit log, a full disk: a sentence, not a traceback
        print(f"upkeep: stopped by a file error ({e.strerror or type(e).__name__}"
              + (f": {os.path.basename(str(e.filename))[:60]}" if e.filename else "") + "): fix it and run the command again (read what was printed before it: a change may already have been made)", file=sys.stderr)
        return 2


def dispatch(a, S, env, sd):
    announce_overrides(env, sd, getattr(a, "apply", False))
    try:
        for line in recover_verify(env, sd):                  # first of all: a verify that was killed must not leave the gate open
            print(line, file=sys.stderr)
    except OSError as e:
        print(f"upkeep: could not close the gate after an unfinished verify ({e.strerror or type(e).__name__}): `busy on --apply` by hand", file=sys.stderr)
    if a.cmd == "log":
        return cmd_log(sd, a, S, env)
    if a.cmd == "undo":
        return cmd_undo(S, env, sd, a)
    if a.cmd in CHECKS:
        lines, code = CHECKS[a.cmd][0](S, env, a, sd)
        print("\n".join(lines))
        return code
    if a.cmd == "busy":
        on = os.path.exists(busy_path(env))
        if a.state == "status":
            print("busy: " + ("on" if on else "off"))
            return 0
        if not a.apply:
            print(f"busy: would switch {a.state} (the gate refuses new wakes while it is on); add --apply")
            return 0
        set_busy(env, a.state == "on")
        try:
            append_log(sd, "busy-" + a.state, "ok")
        except OSError as e:
            print(f"upkeep: the switch is {a.state}, but the audit log could not be written ({e.strerror or type(e).__name__}): look at {os.path.join(sd, 'audit.jsonl')}", file=sys.stderr)
        print("busy: " + a.state + (" (the gate refuses new wakes; running services stay until idle)" if a.state == "on" else ""))
        return 0
    if a.cmd == "idle":
        gv = GateView(env)
        ok, why = gv.idle(os.path.exists(busy_path(env)))
        print(("idle: yes -- " if ok else "idle: no -- ") + why)
        return 0 if ok else 1
    if a.cmd == "snapshot":
        if a.list:
            ids = list_snapshots(sd)
            for i in ids:
                d = load_snapshot(sd, i) or {}
                print(f"{i}  driver {d.get('driver')}  pins {' '.join(d.get('pins') or [])}  kernel {d.get('running_kernel')}")
            if not ids:
                print("no snapshots yet")
            return 0
        f = facts(S)
        free, _need = boot_info(env)
        snap = snapshot_of(f, free)
        why = snapshot_problems(f)
        if why and not a.force:
            print("snapshot REFUSED: the host is not in a clean state, so this would not be a state to go back to (and it would shadow the good snapshot):\n  "
                  + "\n  ".join(why) + "\nTake the snapshot BEFORE transaction 1. `snapshot --apply --force` saves it anyway.", file=sys.stderr)
            return 1
        sid = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        while os.path.exists(os.path.join(sd, "snapshots", sid + ".json")):
            sid += "x"
        if why:
            print("snapshot: FORCED although " + "; ".join(why))
        print(f"snapshot: driver {snap['driver']}, pins {' '.join(snap['pins']) or 'none'}, {len(snap['packages'])} packages, kernels {' '.join(snap['kernels'])} "
              f"(running {snap['running_kernel']}), dkms rows {len(snap['dkms'])}, /boot free {free} MB")
        if not a.apply:
            print("not saved (print-only): add --apply to save it")
            return 0
        write_private(os.path.join(sd, "snapshots", sid + ".json"), json.dumps(snap, indent=1, sort_keys=True) + "\n")
        append_log(sd, "snapshot", "forced" if why else "ok", {"driver": snap["driver"], "snapshot": sid}, what="snapshot of the driver family (the rollback source)",
                   after={"snapshot": sid, "driver": snap["driver"], "packages": str(len(snap["packages"]))}, rollback=f"{UP} rollback {sid}")
        print("snapshot saved: " + sid)
        return 0
    if a.cmd == "check-sim":
        if a.to and not a.kernel and not TARGET_RE.fullmatch(a.to):
            print(f"check-sim: {a.to[:40]!r} is a kernel release: add --kernel, or give a driver version", file=sys.stderr)
            return 2
        try:
            text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8", errors="replace").read()
        except OSError as e:
            print(f"check-sim: cannot read {a.file}: {e.strerror or type(e).__name__} (not a verdict: exit 2)", file=sys.stderr)
            return 2
        f = facts(S)
        if a.pin:
            res = check_pin_sim(text, a.to)
        elif a.kernel:
            res = check_kernel_sim(text, f["headers"], f["running"], [x for x in (env.get("UPKEEP_PROTECT") or "").split(",") if x], allow_patterns(env.get("UPKEEP_ALLOW_REMOVE")), a.to)
        else:
            rb = None
            expect = driver_set(f)
            if a.rollback_from:
                snap = load_snapshot(sd, a.rollback_from)
                bad = validate_snapshot(snap) if snap else ["snapshot not found"]
                if bad:
                    print("check-sim: cannot use the snapshot (" + "; ".join(bad) + ")", file=sys.stderr)
                    return 2
                rb = {strip_arch(n) for n in snap["packages"]}
                expect = [p for p, _v in rollback_want(f, snap) if is_family(p)]
            res = check_sim(text, a.to, installed=f["driver"], running=f["running"], extra_protect=[x for x in (env.get("UPKEEP_PROTECT") or "").split(",") if x],
                            expect=expect, allow_remove=allow_patterns(env.get("UPKEEP_ALLOW_REMOVE")), rollback_allow=rb)
        ovr = overrides(env)                                      # an environment override changes what is accepted: it is printed and logged, never silent
        res["notes"] = res["notes"] + ["OVERRIDE in effect: " + x for x in ovr]
        print("\n".join(render_sim(res)))
        if a.apply:
            append_log(sd, "check-sim", "ok" if res["ok"] else "not-ok", {"driver": f["driver"], "target": res["target"]}, "; ".join(res["reasons"] + ["OVERRIDE: " + x for x in ovr])[:1200] or None)
        return 0 if res["ok"] else 1
    if a.cmd == "plan":
        lines, ok = MODULES[a.module][0](S, env, a, sd)
        print("\n".join(lines))
        if a.apply and a.module not in ACTING:                  # profile and deploy write their own before/after lines
            append_log(sd, "plan-" + a.module, "ok" if ok else "not-ok", {"target": getattr(a, "to", None)})
        return 0 if ok else 1
    if a.cmd == "rollback":
        if a.snapshot:
            snap, ref = load_snapshot(sd, a.snapshot), a.snapshot
        else:
            picked = pick_snapshot(sd, avoid=facts(S)["driver"], fallback_newest=True)
            snap, ref = (picked[1], picked[0]) if picked else (None, None)
        if not snap:
            print(f"no snapshot{' ' + a.snapshot if a.snapshot else ''} in {sd}: take one before an update with `{UP} snapshot --apply`", file=sys.stderr)
            return 2
        lines, ok = rollback_lines(S, env, snap, ref, sd, list_snapshots(sd))
        print("\n".join(lines))
        if a.apply:
            append_log(sd, "rollback-plan", "ok" if ok else "not-ok", {"to": snap.get("driver"), "snapshot": ref})
        return 0 if ok else 1
    if a.cmd == "verify":
        lines, code = cmd_verify(S, env, sd, a.to, a.installed_only, a.apply)
        print("\n".join(lines))
        return code
    return 2


if __name__ == "__main__":
    sys.exit(main())
