#!/usr/bin/env python3
"""aibridge scan: the HOST side of the on-demand ClamAV scan (tier 2 of CAPABILITIES.md "Security tiers").

An agent that wants a file scanned writes a small request into its own /workdir/.scan/; this service (a systemd --user unit, stdlib only,
runs on the host next to the waker) copies the file out of the stack's container, scans it in ONE shared throw-away ClamAV container
(no network, read-only root, file mounted read-only, all capabilities dropped, 2 GB RAM) and writes back a few validated fields. The
agent never gets scanner text, the file never leaves the machine, and nothing runs on the VM's CPU unless the RAM budget allows it.

  scanner.py                   the service (aibridge-scan.service): heartbeat, request intake, one worker
  scanner.py --update          one signature refresh (aibridge-scan-update.service, daily): freshclam in the pinned image
  scanner.py --update --init   the same, but allowed to create the signature volume and pull the image: the operator's first run
  scanner.py --check           print, without scanning anything, what the service would use and serve (the operator's first run)

FIRST RUN (operator, by hand; deploy_ops.sh installs the units but never enables or starts the service):
  1. python3 ~/aibridge/ops/scan/scanner.py --update --init     pulls the pinned image if missing, creates the volume, downloads the
                                                                 signatures (about 108 MB; needs about 460 MB of free disk)
  2. python3 ~/aibridge/ops/scan/scanner.py --check             everything should say "ok"
  3. systemctl --user enable --now aibridge-scan.service
Until step 1 the heartbeat says enabled:false and every request is refused with reason "off". The daily timer never creates the volume
by itself: before the first install it logs one line and exits 0 (so it neither downloads unannounced nor raises a false alarm); after a
successful `--update --init` (it leaves <state dir>/initialized) a missing image or volume makes it exit 1, so the alert fires.

THE CONTRACT with the agent side (gateway.py), directory <host workdir>/.scan/ per stack of ops/wake/stacks.json:
  scanner.json   heartbeat {"v":1,"ts":epoch,"enabled":bool,"max_mb":300,"sigdb":"YYYY-MM-DD","engine":"1.5.4"}, rewritten every ~6 s
                 (tmp + os.replace). enabled is false when the signature volume or image is missing or the volume holds no database.
  req-<id>.json  from the agent, <= 4 KB, {"v":1,"id":<16 lowercase hex = the file name's id>,"ts":epoch,"path":<absolute path INSIDE the
                 container>,"lang":"es|ru|en"}. Read directly; if the host cannot read it, `docker cp <brain>:/workdir/.scan/<name> -`.
  st-<id>.json   {"phase":"queued"|"scanning","ts":epoch} while the request waits or runs ("waiting_ram" is in the contract but never
                 written: the host never waits for RAM, it answers busy/memory at once).
  res-<id>.json  {"v":1,"state":"done"|"busy"|"refused"|"error","verdict":"clean"|"found"|"not_scanned","sigs":[<=5 names],"more":N,
                 "partial":bool,"secs":N,"sigdb":"YYYY-MM-DD","engine":"1.5.4","reason":<enum>,"rts":N,"sha":"<16 hex>"}; reason is ""
                 for state done and one of memory queue_full too_big not_found bad_path not_regular scan_error timeout disk expired
                 off otherwise. "rts" is the request's ts echoed back as an int (0 when the request could not be parsed). "sha" is the
                 first 16 hex of the SHA-256 the host computed while extracting the file, so a verdict is bound to the bytes that were
                 scanned ("" until the extraction has finished: refusals before it, and busy/memory at the first check, carry "").
                 Mode 0644, tmp + os.replace. A signature name is copied only if it matches ^[A-Za-z0-9._\\-/:+]{1,64}$.
The host removes results older than 1 h, the request once it answered it, and leaves nothing that looks like a pending request.

DECISIONS (where the brief left room):
  * verdict: state "done" carries "clean" or "found"; every other state carries "not_scanned". A scan that completed and fired only
    limit alerts (Heuristics.Limits.Exceeded.*, or Heuristics.Encrypted.*: the scan runs with --alert-encrypted-archive/doc so a password-protected zip is "parts not reviewed", not silently clean) is verdict
    "clean" with partial:true: "nothing found, but parts were not reviewed". Those names are never listed as signatures.
  * A FOUND line whose name fails the validation is still a detection: verdict "found", the name is just not listed (and counted in no
    field), so a hostile name can hide itself but never turn a detection into "clean".
  * Never clean when anything looked wrong: an exit code other than 0 or 1, a line with "LibClamAV Error" or "ERROR" (stdout or stderr),
    exit 0 with a FOUND line or exit 1 without one, all give state error/scan_error. The one exception is a real detection with exit 1:
    that is still reported as found, with partial:true if an error line was printed (found is the cautious answer). Stdout alone is
    searched for FOUND lines.
  * "expired": a request whose ts is older than 600 s or more than 60 s ahead is answered refused/expired and removed (cheaper for the
    agent than a silent drop); a request that waited so long in the queue that it became that old is answered the same way.
  * A malformed request (bad JSON, wrong "v", id different from the file name, more than 4 KB, a path that is not a string) with a valid
    file name is answered error/scan_error; one with an invalid "req-..." name is just removed. A request younger than 3 s that does not
    parse yet is left for the next tick (the agent may still be writing it).
  * Duplicate signature names are listed once; "more" counts the distinct valid names beyond the fifth.
  * Memory is checked by the worker twice: after it took the lock and before extracting, and again right before `docker run` (the extraction
    can take minutes): mem_available_mb() - 1800 >= reserve_mb (reserve from the waker's stacks.json), never evicting or waiting; busy/memory
    either way, the temp dir is removed. While a scan container runs the file <state dir>/scan.running holds {"est_mb":1800,"ts":epoch}
    (removed afterwards and at startup) for a later waker patch to read.
  * Fairness: ONE queued-or-running job per stack; a second request from a stack that already has one is answered busy/queue_full at once,
    and the stacks are visited in a rotating order each tick, so a stack that floods its .scan/ cannot starve the others.
  * busy/queue_full is also the answer when the lock stays held longer than LOCK_WAIT_S (a signature update running).
  * The update is `scanner.py --update` rather than `flock ... docker run`: it takes the same lock with a timeout, removes a container left by
    a killed earlier run, kills a hung freshclam container (also on SIGTERM), and can refuse to run before the first manual install.
  * `--update --init` writes <state dir>/initialized after a successful install. From then on a plain `--update` that finds the image or the
    volume gone exits 1 (the OnFailure alert fires: somebody pruned docker); without the marker it still skips silently.
  * The service and the version probe run with `--pull never`: nothing is ever downloaded except by `--update --init` (and the update itself).

THE FILE NEVER LEAVES, THE AGENT IS NOT TRUSTED. Its requests and its /workdir are attacker-controlled: every access to .scan goes through
a directory file descriptor opened with O_NOFOLLOW (the container's root could replace .scan by a symlink to a host directory), request
files are opened O_NOFOLLOW|O_NONBLOCK and must be regular (a FIFO there would hang the loop), and the path to extract is only checked
lexically (absolute, no "..", no empty or "." component, no control character, under /root/.hermes/cache/, /workdir/, /openwebui-uploads/
or /hub/inbox/, no component below the root starting with "." so never /workdir/.scan or a dotfile). Symlinks INSIDE the container are
resolved by `docker cp` within the container's own view: the agent can already read anything the container can, only the verdict leaves.
The sample is extracted from `docker cp ... -` as a tar stream whose FIRST member must be a regular file (symlink, directory, device,
hardlink: refused not_regular) of at most max_mb, copied while counting bytes and hashing, into a 0700 directory under the state dir that
is always removed (and swept at startup). It is named sample.bin so ClamAV's output never echoes a person's file name. Logs (journald)
carry stack name, request id, size, sha256[:12], verdict, seconds, reason and the validated names, never a path or a file name.
Hostile inputs are bounded: a ts that is not a finite number in [0, 1e11) makes the request malformed (never an exception), a file time more
than 5 s in the future is not "still being written" (it is judged at once, and cleanup expires files by abs(now - mtime)), files that are
still settling do not use up the per-tick budget of 8 decisions, at most 2000 directory entries per stack are looked at per tick, and the
docker cp fallback that reads a request gives up after 10 s.

TIMING, measured: about 12 s for a small file and about 36 s for 125 MB of random data, each plus about 10 s of signature loading. So a
scan is usually under a minute and longer for big archives; the hard limits are 300 s for clamscan and 330 s for the container.

THE SCANNER IMAGE is pinned by digest (IMAGE below). To bump it: pick the new tag, `docker pull clamav/clamav:<tag>`, read the digest with
`docker image inspect --format '{{index .RepoDigests 0}}' clamav/clamav:<tag>`, change ENGINE, IMAGE_DIGEST here AND the literals in
scanner_selftest.py, rerun the selftest, then `scanner.py --update --init` (pulls it) and `--check` on the host. The signatures live in the
named volume aibridge-clamav-db (nothing here wipes it, only somebody who prunes docker, e.g. `docker volume prune`; it holds mirrors.dat and
freshclam.dat, which keep the client from being blocked; more than the daily limits gets HTTP 429, so the update runs exactly once a day).

Tests: python3 -I ops/scan/scanner_selftest.py (offline, a fake docker first on PATH). Env overrides: AIBRIDGE_SCAN_STACKS (stacks.json, default
ops/wake/stacks.json beside this repo copy), AIBRIDGE_SCAN_STATE (state dir, default ~/.local/state/aibridge-scan), WAKE_TEST_MEMINFO
(a file holding the MemAvailable MB to pretend, same as the waker), and `docker` is looked up on PATH.
"""
import argparse
import collections
import contextlib
import datetime
import errno
import fcntl
import hashlib
import json
import os
import queue
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- the pinned scanner image and its signature volume ----
ENGINE = "1.5.4"
IMAGE_REPO = "clamav/clamav"
IMAGE_TAG = ENGINE + "_base"
# Bump: see the docstring ("THE SCANNER IMAGE is pinned by digest"). The base image ships no signatures: freshclam fills the volume.
IMAGE_DIGEST = "sha256:58168cd4f48a118c7d20b76da8ffce97e579b84ed7e6d1e977c6e22b1e989c5a"
IMAGE = f"{IMAGE_REPO}:{IMAGE_TAG}@{IMAGE_DIGEST}"
VOLUME = "aibridge-clamav-db"
UPDATE_NAME = "aibridge-scan-update"
SAMPLE_NAME = "sample.bin"
SAMPLE = "/scan/" + SAMPLE_NAME

# ---- paths (env overrides are for the selftest) ----
STATE_DIR = os.environ.get("AIBRIDGE_SCAN_STATE") or os.path.expanduser("~/.local/state/aibridge-scan")
TMP_DIR = os.path.join(STATE_DIR, "tmp")
LOCK_PATH = os.path.join(STATE_DIR, "lock")
MARKER = os.path.join(STATE_DIR, "scan.running")        # {"est_mb":N,"ts":epoch} while a scan container runs
INIT_MARKER = os.path.join(STATE_DIR, "initialized")    # written by a successful `--update --init`
STACKS_FILE = os.environ.get("AIBRIDGE_SCAN_STACKS") or os.path.join(os.path.dirname(HERE), "wake", "stacks.json")
DOCKER = "docker"          # looked up on PATH

# ---- limits ----
MAX_MB = 300               # largest file accepted (also the clamscan --max-filesize)
EST_SCAN_MB = 1800         # RAM a scan is expected to need (ClamAV with its database, in a 2 GB cgroup)
DEFAULT_RESERVE_MB = 1500  # like the waker's reserve_mb
DISK_MARGIN = 2 << 30      # free disk needed beyond the largest file
SCAN_TIMEOUT_S = 330       # hard limit for the scan container (clamscan itself stops at 300 s)
EXTRACT_TIMEOUT_S = 180    # docker cp of the largest file
LOCK_WAIT_S = 300          # a worker waits this long for a signature update before answering busy
UPDATE_LOCK_WAIT_S = 900
UPDATE_TIMEOUT_S = 900
REQ_MAX_BYTES = 4096
REQ_MAX_AGE_S = 600
REQ_MAX_FUTURE_S = 60
REQ_SETTLE_S = 3           # a request that does not parse yet and is younger than this may still be being written
REQ_FUTURE_MTIME_S = 5     # a file time further ahead than this is not "written just now": it is judged at once
REQ_CP_TIMEOUT_S = 10      # the docker cp fallback that reads one request
TS_MAX = 1e11              # a request ts outside [0, TS_MAX) is malformed
MAX_ENTRIES = 2000         # directory entries looked at per stack per tick
RESULT_KEEP_S = 3600
ORPHAN_KEEP_S = 600        # st-*.json with no live request
TICK_S = 3
HEARTBEAT_S = 5            # with a 3 s tick the heartbeat is rewritten about every 6 s
WORKDIR_TTL_S = 300
WORKDIR_RETRY_S = 30
MAX_REQS_PER_TICK = 8
QUEUE_MAX = 2
SIGDB_TTL_OK_S = 600
SIGDB_TTL_OFF_S = 60
SIGDB_RETRY_S = 10         # after a probe in which docker did not answer

ID_RE = re.compile(r"[0-9a-f]{16}")
REQ_RE = re.compile(r"req-([0-9a-f]{16})\.json")
SIG_RE = re.compile(r"[A-Za-z0-9._\-/:+]{1,64}")
LIMIT_ALERT = re.compile(r"Heuristics\.(?:Limits\.Exceeded|Encrypted)(?:\.[A-Za-z0-9_.\-]{1,40})?")
STACK_NAME_RE = re.compile(r"[A-Za-z0-9_.\-]{1,40}")
ROOTS = ("/root/.hermes/cache/", "/workdir/", "/openwebui-uploads/", "/hub/inbox/")
WORKDIR_FMT = '{{range .Mounts}}{{if eq .Destination "/workdir"}}{{.Source}}{{end}}{{end}}'

STOP = threading.Event()
CURRENT = [""]                           # name of the scan container running now (for a clean stop)
INFLIGHT = set()                         # (stack name, id) queued or running
INFLIGHT_LOCK = threading.Lock()
Q = queue.Queue(maxsize=QUEUE_MAX)
Job = collections.namedtuple("Job", "stack rid ts path")


class Fail(Exception):
    """A request that ends with this state and reason (never any scanner text)."""
    def __init__(self, state, reason):
        super().__init__(f"{state}/{reason}")
        self.state, self.reason = state, reason


class LockTimeout(Exception):
    pass


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), msg, flush=True)


_WARNED = {}


def warn_rate(key, msg, every=60):
    now = time.time()
    if now - _WARNED.get(key, 0.0) >= every:
        _WARNED[key] = now
        log(msg)


def docker(*args, timeout=60):
    return subprocess.run([DOCKER, *args], capture_output=True, text=True, errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)


def docker_try(*args, timeout=60):
    """The CompletedProcess, or None when docker is missing or hangs."""
    try:
        return docker(*args, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def mem_available_mb():
    meminfo = os.environ.get("WAKE_TEST_MEMINFO", "")     # tests only: a file holding the MemAvailable MB to pretend
    if meminfo:
        try:
            return int(open(meminfo).read().strip())
        except (OSError, ValueError):
            pass
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    return 0


# ---------------------------------------------------------------------------------------------------------------- path validation
def validate_path(path):
    """None when the path may be extracted, else "bad_path". Lexical only (see the docstring)."""
    if not isinstance(path, str) or not path or len(path) > 1024:
        return "bad_path"
    if any(ord(c) < 32 or ord(c) == 127 for c in path):        # includes NUL
        return "bad_path"
    if not path.startswith("/"):
        return "bad_path"
    parts = path.split("/")[1:]
    if any(p in ("", ".", "..") for p in parts):
        return "bad_path"
    root = next((r for r in ROOTS if path.startswith(r) and len(path) > len(r)), None)
    if root is None:
        return "bad_path"
    if any(p.startswith(".") for p in path[len(root):].split("/")):      # basename, .scan, any hidden component
        return "bad_path"
    return None


# ---------------------------------------------------------------------------------------------------------------- stacks
class Stack:
    def __init__(self, name, brain):
        self.name, self.brain = name, brain
        self.workdir, self.workdir_at, self.next_try = "", 0.0, 0.0
        self.last_hb = 0.0

    def resolve(self, now):
        """The host path behind the container's /workdir, cached (no docker call per tick)."""
        if self.workdir and now - self.workdir_at < WORKDIR_TTL_S:
            return self.workdir
        if now < self.next_try:
            return self.workdir
        r = docker_try("inspect", "-f", WORKDIR_FMT, self.brain, timeout=20)
        wd = r.stdout.strip() if r is not None and r.returncode == 0 else ""
        if wd and os.path.isabs(wd) and os.path.isdir(wd):
            self.workdir, self.workdir_at, self.next_try = wd, now, 0.0
        else:
            self.next_try = now + WORKDIR_RETRY_S
        return self.workdir


class Config:
    def __init__(self):
        self.stacks, self.reserve_mb, self.mtime = {}, DEFAULT_RESERVE_MB, None


CFG = Config()


def load_config(force=False):
    """(Re)read stacks.json when it changed; keeps the Stack objects (and their caches) of unchanged stacks."""
    try:
        mtime = os.stat(STACKS_FILE).st_mtime_ns
    except OSError:
        warn_rate("cfg", "stacks file not readable: serving the stacks already known" if CFG.stacks
                  else "stacks file not readable and no stack known yet: nothing to serve")
        return
    if not force and mtime == CFG.mtime:
        return
    try:
        with open(STACKS_FILE) as f:
            raw = json.load(f)
        reserve = int(raw.get("reserve_mb", DEFAULT_RESERVE_MB))
        found = {}
        for c in raw["stacks"]:
            name, brain = str(c["name"]), str(c["brain"])
            if STACK_NAME_RE.fullmatch(name) and brain:
                found[name] = brain
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        warn_rate("cfg", "stacks file does not parse: keeping the previous one")
        return
    CFG.stacks = {n: (CFG.stacks[n] if n in CFG.stacks and CFG.stacks[n].brain == b else Stack(n, b)) for n, b in found.items()}
    CFG.reserve_mb, CFG.mtime = reserve, mtime


# ---------------------------------------------------------------------------------------------------------------- the .scan directory
def open_scan_dir(workdir):
    """A directory fd for <workdir>/.scan, created 0775 when missing. Never follows a symlink: a link planted by the container is replaced."""
    p = os.path.join(workdir, ".scan")
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        st = None
    if st is not None and not stat.S_ISDIR(st.st_mode):
        os.unlink(p)
        st = None
    if st is None:
        os.mkdir(p, 0o775)
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        if s.st_uid == os.geteuid() and stat.S_IMODE(s.st_mode) != 0o775:
            os.fchmod(fd, 0o775)
    except OSError:
        pass
    return fd


@contextlib.contextmanager
def scan_dir(stack):
    wd = stack.workdir
    if not wd:
        raise OSError(errno.ENOENT, "workdir unknown")
    fd = open_scan_dir(wd)
    try:
        yield fd
    finally:
        os.close(fd)


def write_json_atomic(dfd, name, obj):
    """tmp + os.replace inside the directory, mode 0644 whatever the umask."""
    tmp = ".tmp-" + secrets.token_hex(6)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644, dir_fd=dfd)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(json.dumps(obj, separators=(",", ":")).encode("ascii"))
            f.flush()
            os.fchmod(f.fileno(), 0o644)
        os.replace(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
    except BaseException:
        unlink_quiet(dfd, tmp)
        raise


def unlink_quiet(dfd, name):
    try:
        os.unlink(name, dir_fd=dfd)
    except OSError:
        pass


def lstat_quiet(dfd, name):
    try:
        return os.stat(name, dir_fd=dfd, follow_symlinks=False)
    except OSError:
        return None


# ---------------------------------------------------------------------------------------------------------------- signature database state
Snap = collections.namedtuple("Snap", "enabled date engine")


def version_argv():
    return ["run", "--rm", "--pull", "never", "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--user", "100:101", "--memory", "256m", "-v", f"{VOLUME}:/var/lib/clamav:ro",
            "--entrypoint", "clamscan", IMAGE, "--version"]


def parse_version(out):
    """'ClamAV 1.5.4/27812/Fri Nov  7 08:25:16 2026' -> (engine, 'YYYY-MM-DD', True); 'ClamAV 1.5.4' (empty volume) -> (engine, '', False)."""
    for line in out.split("\n"):
        m = re.match(r"ClamAV (\d+\.\d+(?:\.\d+)?)(?:/(\d+)/(.+))?\s*$", line.strip())
        if not m:
            continue
        date = ""
        if m.group(3):
            try:
                date = datetime.datetime.strptime(" ".join(m.group(3).split()), "%a %b %d %H:%M:%S %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        return m.group(1), date, bool(m.group(2)) and int(m.group(2)) > 0
    return None


def docker_answers():
    r = docker_try("version", "--format", "{{.Server.Version}}", timeout=20)
    return bool(r is not None and r.returncode == 0)


def image_present():
    for ref in (IMAGE, f"{IMAGE_REPO}@{IMAGE_DIGEST}"):
        r = docker_try("image", "inspect", "--format", "{{.Id}}", ref, timeout=20)
        if r is not None and r.returncode == 0:
            return True
    return False


def volume_present():
    r = docker_try("volume", "inspect", VOLUME, timeout=20)
    return bool(r is not None and r.returncode == 0)


class SigDb:
    """Engine, signature date and the enabled flag, probed with `clamscan --version` in the pinned image and cached. The service never
    pulls an image: a missing image or volume, or a volume without a database, is a definite "off"; a docker that does not answer
    switches it off only on the second failed probe in a row."""

    def __init__(self):
        self.lock = threading.Lock()
        self.enabled, self.date, self.engine, self.checked, self.soft = False, "", ENGINE, 0.0, 0

    def snapshot(self):
        with self.lock:
            return Snap(self.enabled, self.date, self.engine)

    def due(self):
        with self.lock:
            ttl = SIGDB_RETRY_S if self.soft else (SIGDB_TTL_OK_S if self.enabled else SIGDB_TTL_OFF_S)   # a failed probe is retried soon
            return time.time() - self.checked >= ttl

    def _set(self, enabled, date=None, engine=None):
        with self.lock:
            self.enabled, self.checked, self.soft = enabled, time.time(), 0
            if date is not None:
                self.date = date
            if engine:
                self.engine = engine

    def _soft(self):
        with self.lock:
            self.soft += 1
            self.checked = time.time()
            if self.soft >= 2:
                self.enabled = False

    def refresh(self):
        if not docker_answers():
            return self._soft()
        if not image_present() or not volume_present():
            return self._set(False, "")
        r = docker_try(*version_argv(), timeout=60)
        parsed = parse_version(r.stdout) if r is not None and r.returncode == 0 else None
        if parsed is None:
            return self._soft()
        engine, date, has_db = parsed
        self._set(has_db, date, engine)


SIG = SigDb()


def sigdb_loop():
    while not STOP.is_set():
        if SIG.due():
            SIG.refresh()
        STOP.wait(5)


# ---------------------------------------------------------------------------------------------------------------- lock (scan vs update)
@contextlib.contextmanager
def scan_lock(wait_s):
    """flock on the state dir's lock file, shared by the worker and the daily update; LockTimeout when it stays held."""
    ensure_state()
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    deadline = time.monotonic() + wait_s
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline or STOP.is_set():
                    raise LockTimeout()
                time.sleep(0.25)
        yield
    finally:
        os.close(fd)        # closing drops the flock


def ensure_state():
    os.makedirs(TMP_DIR, mode=0o700, exist_ok=True)
    for d in (STATE_DIR, TMP_DIR):
        with contextlib.suppress(OSError):
            os.chmod(d, 0o700)


# ---------------------------------------------------------------------------------------------------------------- extraction
def stream_file(brain, path, cap_bytes, sink, timeout=None):
    """`docker cp <brain>:<path> -` as a tar stream. The FIRST member must be a regular file of at most cap_bytes; its bytes go to sink(chunk)
    while they are counted. Returns the size. Raises Fail(refused, not_found | not_regular | too_big) or Fail(error, scan_error | timeout).
    timeout: seconds for the whole copy (default EXTRACT_TIMEOUT_S)."""
    errf = tempfile.TemporaryFile()
    try:
        proc = subprocess.Popen([DOCKER, "cp", f"{brain}:{path}", "-"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errf)
    except OSError:
        errf.close()
        raise Fail("error", "scan_error")
    timed_out = []
    timer = threading.Timer(EXTRACT_TIMEOUT_S if timeout is None else timeout, lambda: (timed_out.append(1), proc.kill()))
    timer.start()
    tf = None
    try:
        member = None
        try:
            tf = tarfile.open(fileobj=proc.stdout, mode="r|")
            member = tf.next()
        except (tarfile.TarError, EOFError, OSError):
            member = None
        if member is None:                       # docker cp wrote no tar: the path is missing, or docker failed
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=10)
            errf.seek(0)
            err = errf.read(4096)
            if timed_out:
                raise Fail("error", "timeout")
            if proc.returncode not in (0, None) and (b"Could not find the file" in err or b"No such file" in err):
                raise Fail("refused", "not_found")
            raise Fail("error", "scan_error")
        if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE):
            raise Fail("refused", "not_regular")
        if member.size > cap_bytes:
            raise Fail("refused", "too_big")
        src = tf.extractfile(member)
        total = 0
        try:
            while total < member.size:
                chunk = src.read(min(1 << 20, member.size - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > cap_bytes:
                    raise Fail("refused", "too_big")
                sink(chunk)
        except (tarfile.TarError, EOFError, OSError):
            raise Fail("error", "timeout" if timed_out else "scan_error")
        if total != member.size:
            raise Fail("error", "timeout" if timed_out else "scan_error")
        return total
    finally:
        timer.cancel()
        with contextlib.suppress(OSError):
            proc.kill()
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            proc.wait(timeout=10)
        with contextlib.suppress(OSError):
            proc.stdout.close()
        if tf is not None:
            with contextlib.suppress(Exception):
                tf.close()
        errf.close()


def extract(brain, path, dest, cap_bytes):
    """Copy the file at `path` in the container to `dest` (mode 0644 when done). Returns (size, sha256 hex)."""
    h = hashlib.sha256()
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as out:
        def sink(chunk):
            h.update(chunk)
            out.write(chunk)
        size = stream_file(brain, path, cap_bytes, sink)
        out.flush()
        os.fchmod(out.fileno(), 0o644)
    return size, h.hexdigest()


# ---------------------------------------------------------------------------------------------------------------- the scan
def scan_argv(rid, tmpdir):
    """Arguments of `docker run` for one scan. Every hardening flag is asserted by the selftest."""
    return ["run", "--rm", "--pull", "never", "--name", f"aibridge-scan-{rid}", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "64", "--user", "100:101",
            "--memory", "2g", "--memory-swap", "2g", "--cpus", "2",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",
            "-v", f"{VOLUME}:/var/lib/clamav:ro", "-v", f"{tmpdir}:/scan:ro",
            "--entrypoint", "clamscan", IMAGE,
            "--stdout", "--no-summary", "--alert-exceeds-max=yes", "--alert-encrypted-archive=yes", "--alert-encrypted-doc=yes", f"--max-filesize={MAX_MB}M", f"--max-scansize={2 * MAX_MB}M",
            f"--pcre-max-filesize={MAX_MB}M", "--max-files=10000", "--max-recursion=17", "--max-scantime=300000", SAMPLE]


def parse_clamscan(stdout, stderr, rc):
    """clamscan's output -> {verdict, sigs, more, partial, dropped}; Fail(error, scan_error) when anything looks wrong. Pure."""
    found, bad = [], False
    for line in stdout.split("\n"):
        line = line.rstrip("\r")
        if line.endswith(" FOUND"):
            body = line[:-len(" FOUND")]
            prefix = SAMPLE + ": "
            found.append(body[len(prefix):] if body.startswith(prefix) else body.rpartition(": ")[2])
        elif "LibClamAV Error" in line or "ERROR" in line:
            bad = True
    if any("LibClamAV Error" in l or "ERROR" in l for l in stderr.split("\n")):
        bad = True
    real, partial = [], False
    for name in found:
        if LIMIT_ALERT.fullmatch(name):
            partial = True
        else:
            real.append(name)
    if real and rc == 1:
        partial = partial or bad          # a real detection outweighs an error line: report it, and say that parts may not have been reviewed
    elif bad or rc not in (0, 1) or (rc == 0 and found) or (rc == 1 and not found):
        raise Fail("error", "scan_error")
    valid, dropped = [], 0
    for name in real:
        if SIG_RE.fullmatch(name):
            if name not in valid:
                valid.append(name)
        else:
            dropped += 1
    return {"verdict": "found" if real else "clean", "sigs": valid[:5], "more": max(0, len(valid) - 5), "partial": partial,
            "dropped": dropped}


def run_scan(rid, tmpdir):
    """Run the scan container; returns (parsed output dict, seconds). Fail(error, timeout | scan_error)."""
    name = f"aibridge-scan-{rid}"
    CURRENT[0] = name
    t0 = time.monotonic()
    try:
        p = subprocess.run([DOCKER, *scan_argv(rid, tmpdir)], capture_output=True, timeout=SCAN_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        docker_try("rm", "-f", name, timeout=60)
        raise Fail("error", "timeout")
    except OSError:
        raise Fail("error", "scan_error")
    finally:
        CURRENT[0] = ""
    secs = int(time.monotonic() - t0)
    if p.returncode not in (0, 1):
        docker_try("rm", "-f", name, timeout=60)         # a client that died may have left the container behind
    return parse_clamscan(p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"), p.returncode), secs


def result(state, reason="", verdict="not_scanned", sigs=(), more=0, partial=False, secs=0, rts=0, sha=""):
    """rts: the request's ts as an int (0 when unknown). sha: first 16 hex of the SHA-256 of the extracted file, "" before the extraction ended."""
    s = SIG.snapshot()
    return {"v": 1, "state": state, "verdict": verdict, "sigs": list(sigs), "more": int(more), "partial": bool(partial), "secs": int(secs),
            "sigdb": s.date, "engine": s.engine, "reason": reason, "rts": int(rts), "sha": (sha or "")[:16]}


def memory_ok():
    """The RAM rule, as the waker's guard states it: what a scan needs must still leave reserve_mb. Never evicts, never waits."""
    return mem_available_mb() - EST_SCAN_MB >= CFG.reserve_mb


def marker_write():
    """<state dir>/scan.running while a scan container runs, for a later waker patch: it must not start a stack into the scan's RAM."""
    tmp = MARKER + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"est_mb": EST_SCAN_MB, "ts": int(time.time())}, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, MARKER)


def marker_clear():
    for p in (MARKER, MARKER + ".tmp"):
        with contextlib.suppress(OSError):
            os.unlink(p)


def scan_one(job):
    """Extract and scan under the lock. Returns (result, size, sha12, dropped)."""
    cap = MAX_MB * 1024 * 1024
    try:
        ensure_state()
        free = shutil.disk_usage(TMP_DIR).free
        if free < cap + DISK_MARGIN:
            raise Fail("error", "disk")
        tmpdir = tempfile.mkdtemp(prefix="s-", dir=TMP_DIR)          # mode 0700
    except OSError as e:
        raise Fail("error", "disk" if e.errno in (errno.ENOSPC, errno.EDQUOT) else "scan_error")
    size = sha = None
    try:
        size, sha = extract(job.stack.brain, job.path, os.path.join(tmpdir, SAMPLE_NAME), cap)
        os.chmod(tmpdir, 0o755)                                      # for the ClamAV user (uid 100); the parents stay 0700
        if not memory_ok():                                          # the extraction may have taken minutes: look again before docker run
            raise Fail("busy", "memory")
        marker_write()
        try:
            out, secs = run_scan(job.rid, tmpdir)
        finally:
            marker_clear()
    except Fail as f:
        f.size, f.sha = size, sha
        raise
    except OSError as e:
        raise Fail("error", "disk" if e.errno in (errno.ENOSPC, errno.EDQUOT) else "scan_error")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    res = result("done", "", out["verdict"], out["sigs"], out["more"], out["partial"], secs, rts=int(job.ts), sha=sha)
    return res, size, sha[:12], out["dropped"]


def set_phase(stack, rid, phase):
    with contextlib.suppress(OSError):
        with scan_dir(stack) as dfd:
            write_json_atomic(dfd, f"st-{rid}.json", {"phase": phase, "ts": int(time.time())})


def finish(stack, rid, res):
    """Write the result, then remove the request and the phase file. The answer comes first: a crash in between leaves a request that
    the next tick recognises as answered (its result exists) and just removes."""
    with scan_dir(stack) as dfd:
        write_json_atomic(dfd, f"res-{rid}.json", res)
        unlink_quiet(dfd, f"req-{rid}.json")
        unlink_quiet(dfd, f"st-{rid}.json")


def log_result(stack, rid, res, size, sha12, dropped):
    log(f"[{stack}] id={rid} size={'-' if size is None else size} sha={sha12 or '-'} state={res['state']} verdict={res['verdict']} "
        f"secs={res['secs']} reason={res['reason'] or '-'} partial={int(res['partial'])} sigs={','.join(res['sigs']) or '-'} "
        f"more={res['more']} dropped={dropped}")


def process_job(job):
    """One request from the queue to its result file. Never raises."""
    t0 = time.monotonic()
    size = sha12 = None
    dropped = 0
    try:
        try:
            if time.time() - job.ts > REQ_MAX_AGE_S:
                raise Fail("refused", "expired")
            try:
                with scan_lock(LOCK_WAIT_S):
                    if not memory_ok():                                          # never evict, never wait
                        raise Fail("busy", "memory")
                    set_phase(job.stack, job.rid, "scanning")
                    res, size, sha12, dropped = scan_one(job)
            except LockTimeout:
                raise Fail("busy", "queue_full")
        except Fail as f:
            size, sha = getattr(f, "size", None), getattr(f, "sha", None)
            res = result(f.state, f.reason, secs=time.monotonic() - t0, rts=int(job.ts), sha=sha)
            sha12 = sha[:12] if sha else None
        except Exception as e:                                   # never leave a request unanswered
            log(f"[{job.stack.name}] id={job.rid} worker error {type(e).__name__}")
            res = result("error", "scan_error", secs=time.monotonic() - t0, rts=int(job.ts))
        try:
            finish(job.stack, job.rid, res)
        except OSError as e:
            log(f"[{job.stack.name}] id={job.rid} could not write the result (errno {errno.errorcode.get(e.errno, e.errno)})")
        log_result(job.stack.name, job.rid, res, size, sha12, dropped)
    finally:
        with INFLIGHT_LOCK:
            INFLIGHT.discard((job.stack.name, job.rid))


def worker_loop():
    while not STOP.is_set():
        try:
            job = Q.get(timeout=1)
        except queue.Empty:
            continue
        process_job(job)


# ---------------------------------------------------------------------------------------------------------------- requests
def read_request(stack, dfd, name):
    """(bytes up to REQ_MAX_BYTES+1, mtime) or None when the file vanished. OSError when it is not a regular file."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dfd)
    except FileNotFoundError:
        return None
    except PermissionError:
        return read_via_cp(stack, name)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError(errno.EINVAL, "not a regular file")
        return os.read(fd, REQ_MAX_BYTES + 1), st.st_mtime
    finally:
        os.close(fd)


def read_via_cp(stack, name):
    """The host cannot read the request (root-owned, mode 0600?): ask Docker for it."""
    chunks = []
    try:
        stream_file(stack.brain, f"/workdir/.scan/{name}", REQ_MAX_BYTES, chunks.append, timeout=REQ_CP_TIMEOUT_S)
    except Fail as f:
        if f.reason == "too_big":
            return b"x" * (REQ_MAX_BYTES + 1), 0.0
        raise OSError(errno.EIO, "docker cp failed")
    return b"".join(chunks), 0.0


def parse_request(data, rid):
    """The request dict, or None when it is not a well-formed v1 request for this id."""
    if len(data) > REQ_MAX_BYTES:
        return None
    try:
        req = json.loads(data.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(req, dict) or isinstance(req.get("v"), bool) or req.get("v") != 1 or req.get("id") != rid \
            or not isinstance(req.get("path"), str):
        return None
    ts = req.get("ts")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return None
    try:
        if not (0 <= ts < TS_MAX):             # also False for NaN and the infinities; int-versus-float comparison never overflows
            return None
    except (OverflowError, ValueError):
        return None
    return req


def answer(dfd, rid, res):
    write_json_atomic(dfd, f"res-{rid}.json", res)
    unlink_quiet(dfd, f"req-{rid}.json")
    unlink_quiet(dfd, f"st-{rid}.json")


def answer_now(stack, dfd, rid, state, reason, rts=0):
    res = result(state, reason, rts=rts)
    try:
        answer(dfd, rid, res)
    except OSError as e:
        log(f"[{stack.name}] id={rid} could not write the result (errno {errno.errorcode.get(e.errno, e.errno)})")
    log_result(stack.name, rid, res, None, None, 0)


def recent(now, mtime):
    """True when a file may still be being written: modified within the last REQ_SETTLE_S seconds (or a hair ahead of our clock). A time far
    in the future is the container's doing, not a writer in progress: it is NOT recent, so such a file cannot be kept waiting."""
    return -REQ_FUTURE_MTIME_S <= now - mtime < REQ_SETTLE_S


def intake(stack, dfd, names, now):
    reqs = sorted(n for n in names if n.startswith("req-"))
    decided = 0                                           # answers and enqueues only: files still settling cost nothing
    for name in reqs:
        if decided >= MAX_REQS_PER_TICK:
            break
        m = REQ_RE.fullmatch(name)
        if not m:                                         # "req-" with a bad id: not left forever, but a temp file being written is spared
            st = lstat_quiet(dfd, name)
            if st is not None and abs(now - st.st_mtime) > 30:
                unlink_quiet(dfd, name)
            continue
        rid = m.group(1)
        with INFLIGHT_LOCK:
            if (stack.name, rid) in INFLIGHT:
                continue
        if lstat_quiet(dfd, f"res-{rid}.json") is not None:       # answered before a restart: just tidy up
            unlink_quiet(dfd, name)
            continue
        try:
            got = read_request(stack, dfd, name)
        except OSError:
            answer_now(stack, dfd, rid, "error", "scan_error")
            decided += 1
            continue
        if got is None:
            continue
        data, mtime = got
        req = parse_request(data, rid)
        if req is None:
            if recent(now, mtime):                        # maybe still being written: look again next tick
                continue
            answer_now(stack, dfd, rid, "error", "scan_error")
            decided += 1
            continue
        decided += 1
        rts = int(req["ts"])
        age = now - req["ts"]
        if age > REQ_MAX_AGE_S or age < -REQ_MAX_FUTURE_S:
            answer_now(stack, dfd, rid, "refused", "expired", rts)
            continue
        if validate_path(req["path"]):
            answer_now(stack, dfd, rid, "refused", "bad_path", rts)
            continue
        if not SIG.snapshot().enabled:
            answer_now(stack, dfd, rid, "refused", "off", rts)
            continue
        with INFLIGHT_LOCK:                               # one queued-or-running job per stack
            stack_busy = any(s == stack.name for s, _ in INFLIGHT)
            if not stack_busy:
                INFLIGHT.add((stack.name, rid))
        if stack_busy:
            answer_now(stack, dfd, rid, "busy", "queue_full", rts)
            continue
        try:
            write_json_atomic(dfd, f"st-{rid}.json", {"phase": "queued", "ts": int(now)})
        except OSError:
            pass
        try:
            Q.put_nowait(Job(stack, rid, float(req["ts"]), req["path"]))
        except queue.Full:
            with INFLIGHT_LOCK:
                INFLIGHT.discard((stack.name, rid))
            answer_now(stack, dfd, rid, "busy", "queue_full", rts)


def cleanup(stack, dfd, names, now):
    """Results older than an hour, orphan phase files and leftover temp files. Age is abs(now - mtime): a file the container dated in the
    far future expires as well, it cannot be kept forever."""
    for name in names:
        kind = name.split("-", 1)[0]
        if name.startswith(".tmp-"):
            limit = 300
        elif name.endswith(".json") and kind == "res" and ID_RE.fullmatch(name[4:-5]):
            limit = RESULT_KEEP_S
        elif name.endswith(".json") and kind == "st" and ID_RE.fullmatch(name[3:-5]):
            rid = name[3:-5]
            with INFLIGHT_LOCK:
                live = (stack.name, rid) in INFLIGHT
            if live:
                continue
            limit = 0 if lstat_quiet(dfd, f"res-{rid}.json") is not None else ORPHAN_KEEP_S
        else:
            continue
        st = lstat_quiet(dfd, name)
        if st is not None and (stat.S_ISLNK(st.st_mode) or abs(now - st.st_mtime) >= limit):
            unlink_quiet(dfd, name)


def list_names(dfd, limit=None):
    """(names, truncated): at most `limit` (default MAX_ENTRIES) entries, so a directory stuffed with files costs one tick a bounded amount."""
    limit = MAX_ENTRIES if limit is None else limit
    names = []
    with os.scandir(dfd) as it:
        for e in it:
            names.append(e.name)
            if len(names) >= limit:
                return names, True
    return names, False


def heartbeat(dfd):
    s = SIG.snapshot()
    write_json_atomic(dfd, "scanner.json", {"v": 1, "ts": int(time.time()), "enabled": s.enabled, "max_mb": MAX_MB, "sigdb": s.date,
                                            "engine": s.engine})


def service_stack(stack, now):
    if not stack.resolve(now):
        warn_rate(f"wd-{stack.name}", f"[{stack.name}] container or /workdir mount not found: no scan service for this stack yet")
        return
    try:
        with scan_dir(stack) as dfd:
            if now - stack.last_hb >= HEARTBEAT_S:
                heartbeat(dfd)
                stack.last_hb = now
            names, truncated = list_names(dfd)
            if truncated:
                warn_rate(f"big-{stack.name}", f"[{stack.name}] the scan directory holds more than {MAX_ENTRIES} entries: only the first ones are looked at")
            intake(stack, dfd, names, now)
            cleanup(stack, dfd, names, now)
    except OSError as e:
        warn_rate(f"dir-{stack.name}", f"[{stack.name}] cannot use the scan directory (errno {errno.errorcode.get(e.errno, e.errno)})")


# ---------------------------------------------------------------------------------------------------------------- service
def startup_sweep():
    """Leftovers of a previous run: temp dirs, and scan containers that outlived their client (never the update container)."""
    ensure_state()
    marker_clear()
    for n in os.listdir(TMP_DIR):
        p = os.path.join(TMP_DIR, n)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            with contextlib.suppress(OSError):
                os.unlink(p)
    r = docker_try("ps", "-a", "--filter", "name=aibridge-scan-", "--format", "{{.Names}}", timeout=30)
    for n in (r.stdout.split() if r is not None and r.returncode == 0 else []):
        if re.fullmatch(r"aibridge-scan-[0-9a-f]{16}", n):
            docker_try("rm", "-f", n, timeout=60)


def on_term(signum, frame):
    STOP.set()
    name = CURRENT[0]
    if name:
        threading.Thread(target=lambda: docker_try("rm", "-f", name, timeout=60), daemon=True).start()


def rotated(stacks, n):
    """The stacks starting from a different one on every pass (pass n starts at n mod len), so none is always served first."""
    if not stacks:
        return []
    k = n % len(stacks)
    return stacks[k:] + stacks[:k]


def run_pass(n, now):
    for st in rotated(list(CFG.stacks.values()), n):
        try:
            service_stack(st, now)
        except Exception as e:
            warn_rate(f"svc-{st.name}", f"[{st.name}] tick failed: {type(e).__name__}")


def serve():
    if ":" in TMP_DIR or "," in TMP_DIR:
        log("the state directory path contains ':' or ',': it cannot be bind-mounted; set AIBRIDGE_SCAN_STATE")
        return 1
    startup_sweep()
    load_config(force=True)
    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    SIG.refresh()                                  # so the first heartbeat already tells the truth
    worker = threading.Thread(target=worker_loop, name="worker", daemon=True)
    worker.start()
    threading.Thread(target=sigdb_loop, name="sigdb", daemon=True).start()
    log(f"scan service up: stacks={sorted(CFG.stacks)} reserve={CFG.reserve_mb}MB max={MAX_MB}MB image={IMAGE_TAG} avail={mem_available_mb()}MB")
    n = 0
    while not STOP.is_set():
        load_config()
        run_pass(n, time.time())
        n += 1
        STOP.wait(TICK_S)
    worker.join(timeout=30)
    while True:                                   # requests still waiting get an answer instead of a silence
        try:
            job = Q.get_nowait()
        except queue.Empty:
            break
        with contextlib.suppress(Exception):
            finish(job.stack, job.rid, result("refused", "off", rts=int(job.ts)))
    for st in list(CFG.stacks.values()):          # a missing heartbeat tells the agent faster than a stale one
        with contextlib.suppress(Exception):
            with scan_dir(st) as dfd:
                unlink_quiet(dfd, "scanner.json")
    log("scan service stopped")
    return 0


# ---------------------------------------------------------------------------------------------------------------- --update
def update_argv():
    return ["run", "--rm", "--name", UPDATE_NAME, "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "1g", "--user", "100:101", "--tmpfs", "/tmp", "-v", f"{VOLUME}:/var/lib/clamav",
            "--entrypoint", "freshclam", IMAGE, "--stdout", "--log=/dev/null"]


def _update_term(signum, frame):
    """SIGTERM during an update: remove the freshclam container (it would outlive us), then leave."""
    STOP.set()
    docker_try("rm", "-f", UPDATE_NAME, timeout=30)
    raise SystemExit(1)


def cmd_update(init=False):
    ensure_state()
    if not docker_answers():
        log("update failed: docker does not answer")
        return 1
    present = image_present() and volume_present()
    if not present and not init:
        if os.path.exists(INIT_MARKER):
            log("update failed: the image or the signature volume is gone although they were installed before (docker prune?): "
                "run scanner.py --update --init")
            return 1
        log("update skipped: no signature volume or image yet (the first update is run by hand: scanner.py --update --init)")
        return 0
    if init and not present:                            # the docker output is captured, so say what the wait is
        log("pulling the image and downloading signatures (about 108 MB), this takes a few minutes")
    old = None
    with contextlib.suppress(ValueError):               # signal handlers can only be set from the main thread
        old = signal.signal(signal.SIGTERM, _update_term)
    try:
        return _run_update(init)
    finally:
        if old is not None:
            signal.signal(signal.SIGTERM, old)


def _run_update(init):
    try:
        with scan_lock(UPDATE_LOCK_WAIT_S):
            docker_try("rm", "-f", UPDATE_NAME, timeout=60)      # a container a killed earlier run left behind (errors ignored)
            try:
                p = subprocess.run([DOCKER, *update_argv()], capture_output=True, text=True, errors="replace", timeout=UPDATE_TIMEOUT_S,
                                   stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                docker_try("rm", "-f", UPDATE_NAME, timeout=60)
                log("update failed: freshclam did not finish in time")
                return 1
            except OSError:
                log("update failed: docker is not available")
                return 1
    except LockTimeout:
        log("update failed: a scan held the lock too long")
        return 1
    tail = (p.stdout or "")[-1500:].strip()
    if p.returncode != 0:                               # freshclam's own text: signatures and mirrors, never a person's data
        log(f"update failed: freshclam exit {p.returncode}\n{tail}")
        return 1
    SIG.refresh()
    s = SIG.snapshot()
    log(f"update ok: signatures dated {s.date or 'unknown'}, engine {s.engine}, enabled={s.enabled}")
    if not s.enabled:
        log("freshclam finished but the database is not usable: check the volume")
        return 1
    if init:
        try:
            with open(INIT_MARKER, "w") as f:
                json.dump({"ts": int(time.time()), "sigdb": s.date}, f)
            os.chmod(INIT_MARKER, 0o600)
        except OSError:
            log("could not write the initialized marker: a later pruned volume will not raise an alert")
    return 0


# ---------------------------------------------------------------------------------------------------------------- --check
def cmd_check():
    """What the service would use and serve; never scans, never writes."""
    bad = []

    def say(ok, text):
        print(("ok    " if ok else "FAIL  ") + text)
        if not ok:
            bad.append(text)

    up = docker_answers()
    say(up, "docker answers" if up else "docker does not answer (is the user in the docker group, is the daemon up?)")
    img = up and image_present()
    say(img, f"image {IMAGE_TAG}@{IMAGE_DIGEST[:19]}... present" if img else f"image missing: scanner.py --update --init pulls {IMAGE_TAG}")
    vol = up and volume_present()
    say(vol, f"volume {VOLUME} exists" if vol else f"volume {VOLUME} missing: scanner.py --update --init creates it and downloads the signatures")
    if img and vol:
        r = docker_try(*version_argv(), timeout=60)
        parsed = parse_version(r.stdout) if r is not None and r.returncode == 0 else None
        if parsed is None:
            say(False, "could not read the signature version (clamscan --version in the pinned image failed)")
        else:
            say(parsed[2], f"signatures dated {parsed[1] or 'unknown'}, engine {parsed[0]}" if parsed[2]
                else f"engine {parsed[0]} but the volume holds no database: scanner.py --update --init")
    if not os.path.exists(STACKS_FILE):
        say(False, f"stacks file missing: {STACKS_FILE} (AIBRIDGE_SCAN_STACKS names another one; the default is ops/wake/stacks.json beside this copy)")
        stacks = {}
    else:
        load_config(force=True)
        stacks = CFG.stacks
        say(bool(stacks), f"stacks file lists {len(stacks)} stack(s), reserve {CFG.reserve_mb} MB" if stacks
            else "no stack found in the stacks file (it does not parse, or lists none)")
    now = time.time()
    for st in stacks.values():
        wd = st.resolve(now) if up else ""
        if not wd:                                      # a stack that is not created yet is not a fault of the scan service
            print(f"note  stack {st.name}: container {st.brain} not found or it has no /workdir mount (not created yet?): skipped")
            continue
        scan = os.path.join(wd, ".scan")
        has = os.path.isdir(scan)
        ok = os.access(wd, os.W_OK | os.X_OK)
        say(ok, f"stack {st.name}: the host workdir is writable by this user" if ok
            else f"stack {st.name}: the host workdir is NOT writable by this user ({wd}): the service cannot create .scan there; fix its owner or mode")
        if has and not os.access(scan, os.W_OK | os.X_OK):
            say(False, f"stack {st.name}: .scan exists but this user cannot write in it (owned by root? remove it so the service recreates it)")
        print(f"      stack {st.name}: container {st.brain}, workdir {wd}, .scan {'exists' if has else 'will be created by the service'}")
    avail = mem_available_mb()
    say(avail - EST_SCAN_MB >= CFG.reserve_mb, f"memory now: {avail} MB available, a scan needs {EST_SCAN_MB} MB above the {CFG.reserve_mb} MB reserve")
    try:
        probe = STATE_DIR
        while not os.path.isdir(probe) and os.path.dirname(probe) != probe:
            probe = os.path.dirname(probe)
        free = shutil.disk_usage(probe).free // (1 << 20)
        say(free * (1 << 20) >= MAX_MB * (1 << 20) + DISK_MARGIN, f"disk for samples: {free} MB free (needs {MAX_MB} MB plus {DISK_MARGIN >> 20} MB)")
    except OSError:
        say(False, "could not read the free disk of the state directory")
    print("\nready" if not bad else f"\n{len(bad)} problem(s) above")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="aibridge on-demand ClamAV scan, host side (see the module docstring)")
    ap.add_argument("--check", action="store_true", help="print what would be used and served; scans nothing")
    ap.add_argument("--update", action="store_true", help="refresh the signatures once (aibridge-scan-update.service)")
    ap.add_argument("--init", action="store_true", help="with --update: allowed to create the volume and pull the image (first run)")
    a = ap.parse_args(argv)
    if a.init and not a.update:
        ap.error("--init goes with --update")
    if a.check:
        return cmd_check()
    if a.update:
        return cmd_update(init=a.init)
    return serve()


if __name__ == "__main__":
    sys.exit(main())
