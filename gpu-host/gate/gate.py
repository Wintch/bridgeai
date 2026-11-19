#!/usr/bin/env python3
"""
gate -- on-demand GPU services with per-GPU power presets, on the GPU host (stdlib only, no container).

Every service container of this host (run_services.sh create) stays stopped. A stack asks the gate before a job; the gate
starts the container when the machine is free, keeps it while it is used, stops it when it is not, and moves the GPU power
limit to the measured value for the services that run. The gate only runs `docker start` / `docker stop` on EXISTING
containers of the table below and one fixed `sudo -n /usr/bin/nvidia-smi -pl W`; nothing else, nothing from a request.

  GET  /healthz     "ok gate" (no token)
  GET  /state       {"gpu": {name, limit_w, default_w, min_w, max_w, free_mb}, "blocked": null|"vr"|"busy",
                     "services": {name: {port, running, leases, mode, idle_left_s}}, "bench": null|{id, watts, started},
                     "up_s": seconds the host has been up (the gate's own age when /proc/uptime is unreadable),
                     "selfcheck": null|{verdict, reasons, age_s, driver, extra_cost_pct},
                     "driver_watch": null|{age_s, updates, newest, security, update_class, security_fix, unlock_upstream, kernel_pending,
                                           dkms_gap, boot_low, unlock_mismatch, apt_stale}}
                    an external service (resolve) also has "close": null|"idle"|"evicted"|"off"|"released"
                    security: current|fix_available|fix_not_in_repo|unknown (the installed driver against NVIDIA's security bulletins),
                    update_class: none|security|performance|unknown (an available update: urgent, or measure before adopting),
                    unlock_upstream: none|stable_newer|beta_only|unknown, security_fix: the version a bulletin fixes (or null)
                    selfcheck / driver_watch are the last results of gpu_selfcheck.py and driver_watch.py (gpu-host/GPU_WATCH.md), read
                    from the state dir and cut down to fixed words and numbers; null when never run or not readable
  POST /wake        {"port", "stack", "mode": "interactive"|"batch", "batch": str|null, "jobs": int|null, "bench": str|null}
                    200 {lease, running: true, eta_s: 0} | 202 {lease, running: false, eta_s} (started, wait for /healthz)
                    202 {lease, running: false, eta_s, go: true}: an EXTERNAL service was granted, the client starts it now
                    404 unknown | 503 not_installed / start_failed | 409 {"why": "vr"|"busy"|"vram"|"exclusive"|"bench"}
  POST /done        {"lease", "wakes"?}   one job finished (activity); a batch lease with jobs N closes itself after N dones.
                    "wakes" (1-1000, default 1): how many /wake calls this one job made (a chained video asks once per segment);
                    all of them leave the in-flight count, the job counts once
  POST /beat        {"lease"}   the client is alive: every beat resets the idle clock, a call in flight stays in flight; 200 {"close": null|"idle"|"evicted"|"off"|"released"}
  POST /down        {"lease"}   the client closed its external service (the gate also notices by /proc); 200 {"ok": true}
  POST /release     {"lease", "close": bool}   close=true stops the service now when no other lease holds it
  POST /off         {"stack", "port": int|null}   the person turns the GPU off: ends that stack's interactive leases
  POST /bench/start {"stack", "watts"}  200 {"bench": id} | 409 {"why": "busy_jobs"|"bench"|"vr"|"busy"} | 503 power_failed
  POST /bench/watts {"bench", "watts"}  change the cap of the running bench; /bench/end {"bench"} restores the old limit
  Bearer GATE_TOKEN on everything but /healthz and /bench/*. /bench/* takes ONLY Bearer GATE_BENCH_TOKEN (a different value; never the
  stacks' token): 403 {"why": "bench_disabled"} while GATE_BENCH_TOKEN is unset or equals GATE_TOKEN. 400 bad body, 401 bad token, 413 body over 4 KB. Answers carry fixed
  words only: no process names, no paths.

A wake on a service that was started a moment ago answers 202 with the time left of its ready budget until its own /healthz
answers. Slow docker calls never run under the state lock, so one slow start or stop does not stall other requests. When a
wake would be refused for "exclusive" or "vram" only because other services sit idle under interactive leases, the gate stops
those first (stop_reason "evicted"); a service with a job in flight, a batch lease or an unleased start is never evicted.

EXTERNAL services (resolve: pseudo-port 8695, nothing listens there) are not containers: the client starts and closes them. The
gate grants the start (202 with go: true, power profile already applied) and tells the truth from /proc: a process
^/opt/resolve/bin/resolve$ whose environ has DISPLAY=:99 (the private Xvfb of the MCP session) is "running"; a Resolve on any
other display is a person's session and blocks with "vr". The gate never kills: idle, evict, off and release only set a close
request (GET /state services.resolve.close, and the answer of /beat) and the client closes. An eviction waits up to
GATE_EXT_CLOSE_WAIT_S for the process to leave and refuses the waker when it does not.

Bench mode measures power profiles safely: /bench/start refuses while another stack holds a running service or a job is in
flight, then every /wake without the bench id gets 409 "bench", the cap is the bench's watts and the profiles are not applied.
/bench/end (or GATE_BENCH_TTL_S, default 3600 s, or a person's session starting) restores the limit found before.

Config: gpu-host/host.env (KEY=VALUE lines, never sourced here) and the environment (wins). Keys: GATE_TOKEN (required), GATE_BENCH_TOKEN (for /bench/*; unset = bench mode off),
GATE_PORT 8700, GATE_BIND (default GPU_BIND_ADDR or 0.0.0.0), GATE_IDLE_S 600, GATE_IDLE_<SERVICE> (e.g. GATE_IDLE_VIDGEN),
GATE_BATCH_TTL_S 7200, GATE_EXT_CLOSE_WAIT_S 60, GATE_BENCH_TTL_S 3600, GATE_IDLE_RESOLVE 300, GATE_BLOCK_PROCS (comma-separated regexes; each is matched against the program path, argv[0], and
a "cmd:" prefix matches the whole command line instead), GATE_SOCKET_TIMEOUT_S 10, GATE_MAX_CONNS 64, GATE_STOP_WAIT_S 3, GATE_STATE_DIR
(~/.local/state/bridgeai-gate), GATE_POWER_PROFILES (default gpu-host/power_profiles.conf). Tests also use GATE_TICK_S,
GATE_PORT_<SERVICE> (port of a service), GATE_SERVICE_HOST, GATE_PROC_DIR and GATE_GPU_INDEX.
Operator busy switch: the file $GATE_STATE_DIR/busy (run_services.sh busy on|off) refuses every new wake.
State (the power limit found before the first start) survives a restart in $GATE_STATE_DIR/power.json; the usage ledger is
$GATE_STATE_DIR/usage.jsonl, one line per service run, with no person data.
"""
import configparser
import hmac
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_GPU = os.path.dirname(HERE)                            # gpu-host/
MAX_BODY = 4096
NAME_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

# service -> (port, VRAM need in MB, ready budget in s). Measured numbers: gpu-host/run_services.sh, aibridge/GPU_MEDIA_TOOLS.md.
SERVICES = {
    "upscaler": (8600, 380, 30), "transcoder": (8610, 300, 30), "stt": (8620, 1540, 40), "llm": (8630, 5200, 60),
    "tts": (8640, 0, 20), "tts-hq": (8650, 5300, 90), "imggen": (8660, 6500, 150), "vidgen": (8670, 7000, 360),
    "vidpost": (8680, 2500, 150), "mosher": (8690, 0, 30),
    # resolve is EXTERNAL (see EXTERNAL): its port is only an id. The 2500 MB need is PROVISIONAL: replace with the bench's measured peak.
    "resolve": (8695, 2500, 120),
}
# Services that are not docker containers: the client starts and closes them, the gate only grants, watches /proc and asks.
# proc matches argv[0]; display is the DISPLAY of /proc/<pid>/environ that makes the process ours (the MCP session's private Xvfb).
EXTERNAL = {"resolve": {"proc": re.compile(r"^/opt/resolve/bin/resolve$"), "display": ":99"}}
DEFAULT_IDLE = {"resolve": 300}                              # idle seconds when GATE_IDLE_<SERVICE> is not set
# Matched against argv[0] (the program path); "cmd:" patterns against the whole command line. A file or an argument that
# merely contains a name (tail -f vrserver.txt, pgrep -f vrserver) does not count as the machine being in use.
DEFAULT_BLOCK = [
    r"(^|/)monado-service$", r"(^|/)vrserver$", r"(^|/)vrcompositor$", r"^/opt/resolve/bin/resolve$",
    r"cmd:(^|/)reaper SteamLaunch( |$)", r"cmd:^(\S*/)?python3?[0-9.]* (\S*/)?proton (run|waitforexitandrun)( |$)",
]
# gpu_selfcheck.py and driver_watch.py write these files into the state dir; /state shows only fixed words from them.
SELFCHECK_FILE, DRIVER_WATCH_FILE = "selfcheck.json", "driver_watch.json"
SELFCHECK_VERDICTS = ("ok", "degraded", "error")
SELFCHECK_REASONS = ("param_missing", "module_not_loaded", "ratio_low", "tf32_ratio_low", "tflops_low", "throttled_hw", "probe_failed",
                     "no_gpu", "cap_mismatch", "no_reference", "no_gate_token", "no_bench_token", "bench_ttl_short")
DRIVER_UPDATES = ("none", "same_branch", "newer_branch")
DRIVER_SECURITY = ("current", "fix_available", "fix_not_in_repo", "unknown")     # driver_watch.py: the installed driver against NVIDIA's bulletins
UPDATE_CLASSES = ("none", "security", "performance", "unknown")                  # of the available update: urgent / measure before adopting
UNLOCK_UPSTREAM = ("none", "stable_newer", "beta_only", "unknown")
VERSION_RE = re.compile(r"^[0-9][0-9.]{0,15}$")
INFLIGHT_MAX_S = 1800                                        # a wake with no done older than this no longer counts as a running job


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)


def parse_env_file(path):
    out = {}
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        k, sep, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
            continue
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k] = v
    return out


class Config:
    def __init__(self, environ=None):
        env = os.environ if environ is None else environ
        file_vals = parse_env_file(env.get("GATE_ENV_FILE") or os.path.join(REPO_GPU, "host.env"))
        self._v = dict(file_vals)
        self._v.update({k: v for k, v in env.items() if k.startswith(("GATE_", "GPU_BIND_ADDR"))})
        self.token = self.get("GATE_TOKEN", "")
        self.bench_token = self.get("GATE_BENCH_TOKEN", "")
        self.bench_token_clash = bool(self.bench_token) and self.bench_token == self.token
        if self.bench_token_clash:
            self.bench_token = ""                            # the stacks' token must never open a bench: bench mode stays off
        self.port = int(self.get("GATE_PORT", "8700"))
        self.bind = self.get("GATE_BIND", "") or self.get("GPU_BIND_ADDR", "") or "0.0.0.0"
        self.idle_s = float(self.get("GATE_IDLE_S", "600"))
        self.batch_ttl_s = float(self.get("GATE_BATCH_TTL_S", "7200"))
        self.tick_s = float(self.get("GATE_TICK_S", "10"))
        raw = self.get("GATE_BLOCK_PROCS", "")
        pats = [p.strip() for p in raw.split(",") if p.strip()] if raw.strip() else DEFAULT_BLOCK
        self.block = [(re.compile(p[4:] if p.startswith("cmd:") else p), p.startswith("cmd:")) for p in pats]
        self.socket_timeout = float(self.get("GATE_SOCKET_TIMEOUT_S", "10"))
        self.max_conns = max(1, int(self.get("GATE_MAX_CONNS", "64")))
        self.stop_wait_s = float(self.get("GATE_STOP_WAIT_S", "3"))
        self.ext_close_wait_s = float(self.get("GATE_EXT_CLOSE_WAIT_S", "60"))
        self.bench_ttl_s = float(self.get("GATE_BENCH_TTL_S", "3600"))
        self.state_dir = self.get("GATE_STATE_DIR", "") or os.path.join(os.path.expanduser("~"), ".local", "state", "bridgeai-gate")
        self.profiles = self.get("GATE_POWER_PROFILES", "") or os.path.join(REPO_GPU, "power_profiles.conf")
        self.proc_dir = self.get("GATE_PROC_DIR", "") or "/proc"
        self.gpu_index = int(self.get("GATE_GPU_INDEX", "0"))
        pub = self.get("GPU_BIND_ADDR", "")                  # a container published on one address is not on loopback
        self.service_host = self.get("GATE_SERVICE_HOST", "") or (pub if pub and pub != "0.0.0.0" else "127.0.0.1")

    def get(self, key, default=""):
        return self._v.get(key, default)

    def service_port(self, name):
        return int(self.get("GATE_PORT_" + name.upper().replace("-", "_"), str(SERVICES[name][0])))

    def service_need(self, name):
        """VRAM need in MB of a service on THIS card: GATE_NEED_<SERVICE> in host.env (a smaller card or model, e.g. a 6 GB card with a
        smaller LLM), else the measured default of SERVICES."""
        return int(self.get("GATE_NEED_" + name.upper().replace("-", "_"), str(SERVICES[name][1])))

    def service_idle(self, name):
        return float(self.get("GATE_IDLE_" + name.upper().replace("-", "_"), str(DEFAULT_IDLE.get(name, self.idle_s))))


def run_cmd(argv, timeout=60):
    """(returncode, stdout). A missing binary or a timeout is (127|124, '')."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""


def num(s):
    try:
        return int(round(float(s)))
    except (TypeError, ValueError):
        return None


class Gpu:
    """nvidia-smi for one card (index 0 for now)."""

    def __init__(self, index):
        self.index = index

    def info(self):
        q = "name,power.limit,power.default_limit,power.min_limit,power.max_limit,memory.free,power.draw"
        rc, out = run_cmd(["nvidia-smi", "-i", str(self.index), f"--query-gpu={q}", "--format=csv,noheader,nounits"], 15)
        f = [x.strip() for x in out.strip().splitlines()[0].split(",")] if rc == 0 and out.strip() else []
        if len(f) < 7:
            return {"name": None, "limit_w": None, "default_w": None, "min_w": None, "max_w": None, "free_mb": None, "draw_w": None}
        return {"name": f[0], "limit_w": num(f[1]), "default_w": num(f[2]), "min_w": num(f[3]), "max_w": num(f[4]),
                "free_mb": num(f[5]), "draw_w": float(f[6]) if re.fullmatch(r"[0-9.]+", f[6]) else None}

    def set_limit(self, watts, info, quiet=False):
        """Clamp to the card's range and apply with a fixed argv. Returns the applied watts when the read-back matches, else None.
        quiet: do not log a failure (a restore that is retried every tick logs once)."""
        w = int(watts)
        if info.get("min_w") is not None:
            w = max(w, info["min_w"])
        if info.get("max_w") is not None:
            w = min(w, info["max_w"])
        argv = ["sudo", "-n", "/usr/bin/nvidia-smi", "-pl", str(w)] + (["-i", str(self.index)] if self.index else [])
        rc, _ = run_cmd(argv, 20)
        now = self.info().get("limit_w")
        ok = rc == 0 and now == w
        if ok or not quiet:
            log(f"power: set {w} W {'ok' if ok else 'FAILED (rc=%s, now %s)' % (rc, now)}")
        return w if ok else None


def load_profiles(path):
    """[(section name lowercased, {service: watts})], only numeric values of known services."""
    cp = configparser.ConfigParser(inline_comment_prefixes=("#",), interpolation=None)
    try:
        cp.read(path, encoding="utf-8")
    except (configparser.Error, OSError) as e:
        log(f"power profiles unreadable: {type(e).__name__}")
        return []
    out = []
    for sec in cp.sections():
        vals = {k.lower(): num(v) for k, v in cp.items(sec) if k.lower() in SERVICES and num(v)}
        out.append((sec.lower(), vals))
    return out


def profile_for(profiles, gpu_name):
    best = None
    for sec, vals in profiles:
        if gpu_name and sec in gpu_name.lower() and (best is None or len(sec) > len(best[0])):
            best = (sec, vals)
    return best[1] if best else {}


def read_json_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def load_watch(state_dir, now=None):
    """(selfcheck, driver_watch) for GET /state: the last results of gpu_selfcheck.py and driver_watch.py, each cut down to
    values of a known shape (a file in the state dir is not trusted to be well formed). None when absent or unreadable."""
    now = time.time() if now is None else now

    def age(d):
        t = d.get("at")
        return max(0, int(now - t)) if isinstance(t, (int, float)) and not isinstance(t, bool) else None

    sc = read_json_file(os.path.join(state_dir, SELFCHECK_FILE))
    if sc is not None and sc.get("verdict") in SELFCHECK_VERDICTS:
        why = sc.get("reasons") if isinstance(sc.get("reasons"), list) else []
        drv = sc.get("driver")
        cost = sc.get("extra_cost_pct")
        sc = {"verdict": sc["verdict"], "reasons": [r for r in why if r in SELFCHECK_REASONS], "age_s": age(sc),
              "driver": drv if isinstance(drv, str) and VERSION_RE.match(drv) else None,
              "extra_cost_pct": int(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) and 0 <= cost <= 300 else None}
    else:
        sc = None
    dw = read_json_file(os.path.join(state_dir, DRIVER_WATCH_FILE))
    if dw is not None and dw.get("updates") in DRIVER_UPDATES:
        newest = dw.get("newest")
        det = dw.get("security_detail") if isinstance(dw.get("security_detail"), dict) else {}
        fix = det.get("fixed_in")
        dw = {"age_s": age(dw), "updates": dw["updates"], "newest": newest if isinstance(newest, str) and VERSION_RE.match(newest) else None,
              "security": dw.get("security") if dw.get("security") in DRIVER_SECURITY else None,
              "update_class": dw.get("update_class") if dw.get("update_class") in UPDATE_CLASSES else None,
              "unlock_upstream": dw.get("unlock_upstream") if dw.get("unlock_upstream") in UNLOCK_UPSTREAM else None,
              "security_fix": fix if isinstance(fix, str) and VERSION_RE.match(fix) else None,
              **{k: dw.get(k) is True for k in ("kernel_pending", "dkms_gap", "boot_low", "unlock_mismatch", "apt_stale")}}
    else:
        dw = None
    return sc, dw


class Lease:
    def __init__(self, stack, mode, batch, jobs):
        self.id = secrets.token_hex(8)
        self.stack, self.mode, self.batch, self.jobs = stack, mode, batch, jobs
        self.done = 0
        self.inflight = 0                                    # wakes minus dones, floor 0: overlapping jobs of one stack
        self.svcs = set()
        self.last_svc = None
        self.last_wake = 0.0
        self.last_act = time.time()


class Gate:
    """Locking: `lock` guards the state below and is never held across a subprocess or an HTTP call. `power_lock` serializes
    the power limit changes (lock order: power_lock, then lock). A service in `starting` or `stopping` is mid docker call."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.gpu = Gpu(cfg.gpu_index)
        self.lock = threading.RLock()
        self.power_lock = threading.Lock()
        self.leases = {}                                     # id -> Lease
        self.runs = {}                                       # service -> run record (for the ledger)
        self.first_seen = {}
        self.running = set()                                 # last docker view (updated by docker_ps and by our own starts/stops)
        self.starting = {}                                   # service -> time its docker start began
        self.stopping = {}                                   # service -> Event set when its docker stop (or external close) is done
        self.close_req = {}                                  # external service -> reason the client was asked to close it
        self.bench = None                                    # {"id", "watts", "t0", "stack"} while a power bench runs
        self.t_start = time.monotonic()
        self.waking = 0                                      # /wake requests past the bench check and not answered yet
        self.gen = 0                                         # bumped whenever a start or stop finishes, so a stale docker_ps is dropped
        self.profiles = load_profiles(cfg.profiles)
        self.last_sample = time.time()
        self.power_file = os.path.join(cfg.state_dir, "power.json")
        self.ledger = os.path.join(cfg.state_dir, "usage.jsonl")
        os.makedirs(cfg.state_dir, exist_ok=True)
        self.pw = self._load_power()                         # {"found": W|None, "set": W|None}
        self.block_logged = None
        self.failed = None                                   # a target the last set_limit could not apply
        self.restore_failed = False                          # the last restore could not be done; retried every tick

    # ---- docker ----
    def docker_ps(self):
        """{container name: state} for the table's names, or None when docker fails. Call without the lock."""
        with self.lock:
            gen = self.gen
        rc, out = run_cmd(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}"], 30)
        if rc != 0:
            return None
        ps = {}
        for line in out.splitlines():
            n, _, s = line.partition("\t")
            if n in SERVICES and n not in EXTERNAL:
                ps[n] = s.strip()
        ps.update(self.ext_ps())
        with self.lock:
            if gen == self.gen:                              # a start or stop finished meanwhile: this view may be older than ours
                for n in EXTERNAL:
                    if n in self.starting and ps[n] == "running":
                        self._ext_up(n)
                self.running = {n for n, s in ps.items() if s == "running"}
        return ps

    def _ext_up(self, svc):
        """/proc shows the external service the client was granted: it is running now. Lock held."""
        self.starting.pop(svc, None)
        self.gen += 1
        self.start_run(svc)
        self.runs[svc]["ready"] = True                       # the process exists; the client waits for the tool itself
        for l in self.holders(svc):
            self.note_stack(svc, l)
        log(f"{svc} is up (client started it)")

    def _proc_argv0(self, pid):
        try:
            raw = open(os.path.join(self.cfg.proc_dir, pid, "cmdline"), "rb").read(4096)
        except OSError:
            return None
        return raw, raw.split(b"\0", 1)[0].decode("utf-8", "replace")

    def _proc_display(self, pid):
        try:
            raw = open(os.path.join(self.cfg.proc_dir, pid, "environ"), "rb").read(1 << 20)
        except OSError:
            return None                                      # unreadable: not ours, so it keeps blocking
        for kv in raw.split(b"\0"):
            if kv.startswith(b"DISPLAY="):
                return kv[8:].decode("utf-8", "replace")
        return None

    def _ext_match(self, pid, argv0):
        """The external service this process is (right program on the gate-managed display), else None."""
        for n, spec in EXTERNAL.items():
            if spec["proc"].search(argv0) and self._proc_display(pid) == spec["display"]:
                return n
        return None

    def ext_ps(self):
        """{external service: "running"|"exited"} from /proc. Call without the lock."""
        out = {n: "exited" for n in EXTERNAL}
        me = str(os.getpid())
        try:
            pids = [p for p in os.listdir(self.cfg.proc_dir) if p.isdigit() and p != me]
        except OSError:
            return out
        for p in pids:
            got = self._proc_argv0(p)
            if got:
                n = self._ext_match(p, got[1])
                if n:
                    out[n] = "running"
        return out

    # ---- power ----
    def _load_power(self):
        try:
            d = json.load(open(self.power_file))
            return {"found": num(d.get("found")), "set": num(d.get("set"))}
        except (OSError, ValueError, AttributeError):
            return {"found": None, "set": None}

    def _save_power(self):
        try:
            if self.pw["found"] is None and self.pw["set"] is None:
                os.unlink(self.power_file)
            else:
                json.dump(self.pw, open(self.power_file, "w"))
        except OSError:
            pass

    def _power_rest(self, info):
        """No service runs: give the limit back. The saved state is dropped only when the limit was restored or someone else
        changed it; an unreadable limit or a failed restore keeps it and the next tick tries again."""
        if self.pw["set"] is not None and self.pw["found"] is not None:
            limit = info["limit_w"]
            if limit is None:
                if not self.restore_failed:
                    log("power: limit unreadable, will retry the restore")
                self.restore_failed = True
                return
            if limit == self.pw["set"]:
                if not self.restore_failed:
                    log(f"power: all stopped, restoring {self.pw['found']} W")
                if self.gpu.set_limit(self.pw["found"], info, quiet=self.restore_failed) is None:
                    if not self.restore_failed:
                        log("power: restore failed, will retry")
                    self.restore_failed = True
                    return
            else:
                log("power: limit changed by someone else, left as is")
        self.pw = {"found": None, "set": None}
        self.failed = None
        self.restore_failed = False
        self._save_power()

    def power_sync(self):
        """Bring the limit in line with the services that run or are starting. Call without the state lock."""
        with self.power_lock:
            with self.lock:
                running = set(self.running) | set(self.starting)
                if self.bench:
                    return                                   # a bench owns the limit
            info = self.gpu.info()
            if not running:
                return self._power_rest(info)
            self.restore_failed = False
            if self.pw["found"] is None and info["limit_w"] is not None:
                self.pw["found"] = info["limit_w"]
            prof = profile_for(self.profiles, info["name"])
            vals = [prof[s] for s in running if s in prof]
            if vals and info["limit_w"] is not None:
                target = max(vals)
                if info["min_w"] is not None:
                    target = max(target, info["min_w"])
                if info["max_w"] is not None:
                    target = min(target, info["max_w"])
                if target != self.pw["set"] and (self.pw["set"] is not None or target != info["limit_w"]):
                    if target != self.failed:                # a failing sudo rule is logged once, not every tick
                        done = self.gpu.set_limit(target, info)
                        self.failed = None if done is not None else target
                        if done is not None:
                            self.pw["set"] = done
                elif self.pw["set"] is None and target == info["limit_w"]:
                    self.pw["set"] = target
            self._save_power()

    # ---- blocking ----
    def blocked(self):
        """None, "busy" or "vr" (VR, a game or Resolve is running). Call without the lock."""
        if os.path.exists(os.path.join(self.cfg.state_dir, "busy")):
            return "busy"
        me = str(os.getpid())
        try:
            pids = [p for p in os.listdir(self.cfg.proc_dir) if p.isdigit() and p != me]
        except OSError:
            return None
        for p in pids:
            got = self._proc_argv0(p)
            if not got:
                continue
            raw, argv0 = got
            cmd = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
            if any(spec["proc"].search(argv0) for spec in EXTERNAL.values()) and self._ext_match(p, argv0):
                continue                                     # the MCP session's own Resolve (private display) is a gate task, not a person
            for rx, whole in self.cfg.block:
                if rx.search(cmd if whole else argv0):
                    if self.block_logged != rx.pattern:
                        log(f"blocked: process matches {rx.pattern!r}")      # the name stays in this log only
                        self.block_logged = rx.pattern
                    return "vr"
        self.block_logged = None
        return None

    # ---- leases ----
    def find_lease(self, stack, mode, batch, svc):
        for l in self.leases.values():
            if l.stack != stack or l.mode != mode:
                continue
            if mode == "batch" and l.batch == batch:
                return l
            if mode == "interactive" and svc in l.svcs:
                return l
        return None

    def holders(self, svc, exclude=None):
        return [l for l in self.leases.values() if svc in l.svcs and l is not exclude]

    def batch_holds(self, svc):
        return any(l.mode == "batch" for l in self.holders(svc))

    def lease_of(self, lid):
        return self.leases.get(lid) if isinstance(lid, str) else None

    def inflight(self, svc, now):
        """A job is in flight when some lease of the service has more wakes than dones (up to INFLIGHT_MAX_S)."""
        return any(svc in l.svcs and l.inflight > 0 and now - l.last_wake < INFLIGHT_MAX_S for l in self.leases.values())

    def lease_for(self, body):
        """The lease of this request (reused or new). Lock held."""
        lease = self.find_lease(body["stack"], body["mode"], body["batch"], self._svc_of(body["port"]))
        if lease is None:
            lease = Lease(body["stack"], body["mode"], body["batch"], body["jobs"])
            self.leases[lease.id] = lease
        lease.jobs = body["jobs"] if body["jobs"] is not None else lease.jobs
        return lease

    def attach(self, lease, svc, now):
        if lease.inflight > 0 and now - lease.last_wake >= INFLIGHT_MAX_S:
            lease.inflight = 0                               # wakes that never got a done expired: they must not count again with this one
        lease.svcs.add(svc)
        lease.last_wake = lease.last_act = now
        lease.last_svc = svc
        lease.inflight += 1

    def _svc_of(self, port):
        return next((n for n in SERVICES if self.cfg.service_port(n) == port), None)

    def detach(self, svc):
        """Drop svc from every lease; an interactive lease with nothing left goes away. Lock held."""
        for l in list(self.leases.values()):
            l.svcs.discard(svc)
            if not l.svcs and l.mode == "interactive":
                del self.leases[l.id]

    # ---- runs and ledger ----
    def start_run(self, svc, info=None, adopted=False):
        info = info or {}
        now = time.time()
        self.runs[svc] = {"service": svc, "start": now, "act": now, "wh": 0.0, "limit_w": info.get("limit_w"), "stacks": {},
                          "adopted": adopted, "ready": adopted,      # ready: its /healthz answered (or it was already up)
                          "bench": self.bench["id"] if self.bench else None}

    def note_stack(self, svc, lease):
        run = self.runs.get(svc)
        if not run:
            return
        st = run["stacks"].setdefault(lease.stack, {"jobs": 0, "mode": lease.mode, "batches": []})
        st["mode"] = lease.mode
        if lease.mode == "batch" and lease.batch not in st["batches"]:
            st["batches"].append(lease.batch)

    def end_run(self, svc, reason):
        run = self.runs.pop(svc, None)
        self.detach(svc)
        if not run:
            return
        end = time.time()
        rec = {"service": svc, "start": int(run["start"]), "end": int(end), "seconds": int(round(end - run["start"])),
               "wh": round(run["wh"], 3), "limit_w": run["limit_w"], "stacks": run["stacks"], "stop_reason": reason}
        bench = run.get("bench") or (self.bench["id"] if self.bench else None)
        if bench:
            rec["bench"] = bench
        try:
            with open(self.ledger, "a") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError as e:
            log(f"ledger write failed: {type(e).__name__}")

    def stop_service(self, svc, reason, guard=None, wait=False):
        """docker stop outside the lock. `guard(svc)` is checked under the lock first; False (or a service that is not up, or
        is mid start/stop) means nothing is stopped. Returns True when it stopped.
        An external service is never stopped: the close is only requested (True) and the client does it. wait=True (eviction)
        then waits for the process to leave and returns False if it did not."""
        with self.lock:
            if svc not in self.running or svc in self.stopping or svc in self.starting or (guard and not guard(svc)):
                return False
            ev = self.stopping[svc] = threading.Event()
            if svc in EXTERNAL:
                self.close_req[svc] = reason
        if svc in EXTERNAL:
            log(f"close requested for {svc} ({reason})")
            return self._ext_wait(svc, ev, self.cfg.ext_close_wait_s) if wait else True
        rc, _ = run_cmd(["docker", "stop", svc], 90)
        log(f"stop {svc} ({reason}){'' if rc == 0 else ' docker rc=%s' % rc}")
        with self.lock:
            self.running.discard(svc)
            self.gen += 1
            self.end_run(svc, reason)
            self.stopping.pop(svc, None)
        ev.set()
        self.power_sync()
        return True

    def _ext_finish(self, svc):
        """The external process is gone: end its run with the reason of the close request. Lock held."""
        reason = self.close_req.pop(svc, None) or "gate_stop"
        self.running.discard(svc)
        self.gen += 1
        self.end_run(svc, reason)
        ev = self.stopping.pop(svc, None)
        if ev:
            ev.set()

    def _ext_wait(self, svc, ev, timeout):
        """Wait for a requested close: True when the process left. On timeout the request is withdrawn (the gate never kills),
        False. Polls /proc, so it does not depend on the tick."""
        end = time.time() + timeout
        while True:
            if ev.is_set():
                return True
            if self.ext_ps()[svc] != "running":
                with self.lock:
                    if self.stopping.get(svc) is ev:
                        self._ext_finish(svc)
                self.power_sync()
                return True
            left = end - time.time()
            if left <= 0:
                break
            ev.wait(min(0.25, left))
        with self.lock:
            if self.stopping.get(svc) is ev:
                self.stopping.pop(svc, None)
                self.close_req.pop(svc, None)
                ev.set()
        log(f"{svc}: the client did not close it in time, close request withdrawn")
        return False

    def stop_unheld(self, svcs, reason):
        """Stop every service in svcs that no lease holds and that is not working right now. A service that works (its own
        /status) is left to the idle loop: something without a lease may be using it. Returns the stopped names."""
        with self.lock:
            cand = [s for s in sorted(svcs) if s in self.running and not self.holders(s)]
        stopped = []
        for s in cand:
            if self.service_busy(s):                         # HTTP outside the lock
                continue
            if self.stop_service(s, reason, lambda x: not self.holders(x)):
                stopped.append(s)
        return stopped

    # ---- API operations (each takes the lock itself, in short steps) ----
    def wake(self, body):
        port = body["port"]
        svc = self._svc_of(port)
        if svc is None:
            return 404, {"why": "unknown"}
        with self.lock:
            bench = self.bench["id"] if self.bench else None
            if body.get("bench") != bench:                   # a bench runs and this wake is not its own (or the bench is over)
                return 409, {"why": "bench"}
            self.waking += 1                                 # bench_start refuses while a wake is in progress
        try:
            return self._wake_run(svc, body)
        finally:
            with self.lock:
                self.waking -= 1

    def _wake_run(self, svc, body):
        ps = self.docker_ps()
        if ps is None or svc not in ps:
            return 503, {"why": "not_installed"}
        ctx = {}
        for _ in range(6):
            with self.lock:
                step = self._wake_step(svc, body, ctx)
            kind = step[0]
            if kind == "reply":
                return step[1], step[2]
            if kind == "env":                                # nvidia-smi and /proc outside the lock
                ctx["blocked"], ctx["info"] = self.blocked(), self.gpu.info()
            elif kind == "wait":                             # the service is being stopped right now
                if svc in EXTERNAL:
                    self._ext_wait(svc, step[1], self.cfg.ext_close_wait_s)      # not closed in time: the request is withdrawn
                else:
                    step[1].wait(self.cfg.stop_wait_s)
                ctx = {"evicted": ctx.get("evicted")}
            elif kind == "probe":
                return self._wake_probe(svc, step[1])
            elif kind == "evict":
                _, cands, why = step
                if any(self.service_busy(s) for s in cands):
                    return 409, {"why": why}
                for s in cands:
                    log(f"evict idle {s} to make room for {svc}")
                    if not self.stop_service(s, "evicted", self._evictable, wait=True):
                        return 409, {"why": why}
                ctx = {"evicted": True}
            else:
                return self._wake_grant(svc, body) if svc in EXTERNAL else self._wake_start(svc, body)
        log(f"refuse {svc} for a stack: exclusive (transition did not settle)")
        return 409, {"why": "exclusive"}

    def _eta_left(self, t0, svc):
        return max(1, int(SERVICES[svc][2] - (time.time() - t0) + 0.999))

    def _wake_step(self, svc, body, ctx):
        """One decision under the lock: ("reply", code, obj) | ("env",) | ("wait", event) | ("probe", lease id) |
        ("evict", [svc], why) | ("start",)."""
        now = time.time()
        if body.get("bench") != (self.bench["id"] if self.bench else None):
            return "reply", 409, {"why": "bench"}            # a bench began (or ended) since the check in wake(): decide under this lock
        if svc in EXTERNAL and svc in self.running and svc in self.stopping and self.close_req.get(svc) == "idle":
            self.close_req.pop(svc, None)                    # a call came while the idle close was pending: it is in use, keep it
            ev = self.stopping.pop(svc, None)
            if ev:
                ev.set()
            log(f"{svc}: idle close withdrawn, a client wants it")
        if svc in self.starting:                             # another request started it a moment ago
            lease = self.lease_for(body)
            self.attach(lease, svc, now)
            return "reply", 202, {"lease": lease.id, "running": False, "eta_s": self._eta_left(self.starting[svc], svc)}
        if svc in self.stopping:
            return "wait", self.stopping[svc]
        if svc in self.running:
            lease = self.lease_for(body)
            self.attach(lease, svc, now)
            if svc not in self.runs:
                self.start_run(svc, adopted=True)
            run = self.runs[svc]
            run["act"] = now
            self.note_stack(svc, lease)
            if not run["ready"] and now - run["start"] < SERVICES[svc][2]:
                return "probe", lease.id                     # started a moment ago: ready only when its /healthz answers
            run["ready"] = True
            return "reply", 200, {"lease": lease.id, "running": True, "eta_s": 0}
        if "blocked" not in ctx:
            return ("env",)
        why, cands = self._refuse_reason(svc, ctx, now)
        if cands:
            return "evict", cands, why
        if why:
            log(f"refuse {svc} for a stack: {why}")
            return "reply", 409, {"why": why}
        self.starting[svc] = now
        return ("start",)

    def _evictable(self, svc, now=None):
        """Idle under interactive leases only: no batch, no job in flight, and a lease exists (an unleased service is left to the
        idle rule, we cannot tell who uses it). The service's own /status is checked by the caller, outside the lock."""
        now = now or time.time()
        hs = self.holders(svc)
        return svc in self.running and svc not in self.stopping and svc not in self.starting and bool(hs) \
            and not self.batch_holds(svc) and not self.inflight(svc, now)

    def _refuse_reason(self, svc, ctx, now):
        """(why, evict list): why None = go. With a non-empty list the caller stops those idle services first and refuses with
        `why` only if that fails. Lock held."""
        if ctx["blocked"]:
            return ctx["blocked"], []
        need = self.cfg.service_need(svc)
        active = set(self.running) | set(self.starting)
        if svc == "vidgen":
            conflict = [s for s in sorted(active) if s != "vidgen" and self.cfg.service_need(s) > 0]
        else:
            conflict = ["vidgen"] if need > 0 and "vidgen" in active else []
        if conflict:
            ok = not ctx.get("evicted") and all(self._evictable(s, now) for s in conflict)
            return "exclusive", conflict if ok else []
        free = ctx["info"]["free_mb"]
        if need > 0 and free is not None and free < need:
            pool = sorted((s for s in self.running if self.cfg.service_need(s) > 0 and self._evictable(s, now)), key=lambda s: -self.cfg.service_need(s))
            pick, got = [], free
            for s in pool:
                if got >= need:
                    break
                pick.append(s)
                got += self.cfg.service_need(s)
            return "vram", pick if (got >= need and not ctx.get("evicted")) else []
        return None, []

    def _wake_probe(self, svc, lid):
        ok = self.service_healthy(svc)                       # HTTP outside the lock
        with self.lock:
            run = self.runs.get(svc)
            if run is None or ok:
                if run is not None:
                    run["ready"] = True
                return 200, {"lease": lid, "running": True, "eta_s": 0}
            if time.time() - run["start"] >= SERVICES[svc][2]:
                run["ready"] = True                          # budget over: the caller sees the truth itself
                return 200, {"lease": lid, "running": True, "eta_s": 0}
            return 202, {"lease": lid, "running": False, "eta_s": self._eta_left(run["start"], svc)}

    def _wake_start(self, svc, body):
        self.power_sync()                                    # counts svc: it is in `starting`
        rc, _ = run_cmd(["docker", "start", svc], 120)
        info = self.gpu.info() if rc == 0 else None
        with self.lock:
            self.starting.pop(svc, None)
            if rc != 0:
                self.detach(svc)                             # leases that joined while it was starting
            else:
                self.running.add(svc)
                self.gen += 1
                self.start_run(svc, info)
                lease = self.lease_for(body)
                self.attach(lease, svc, time.time())
                for l in self.holders(svc):
                    self.note_stack(svc, l)
        if rc != 0:
            log(f"docker start {svc} failed rc={rc}")
            self.power_sync()
            return 503, {"why": "start_failed"}
        log(f"start {svc} ({body['mode']})")
        return 202, {"lease": lease.id, "running": False, "eta_s": SERVICES[svc][2]}

    def _wake_grant(self, svc, body):
        """An external service: the start is granted, the client does it. The power profile is applied first (svc is in
        `starting`), so the measured limit is set before the program boots."""
        self.power_sync()
        with self.lock:
            self.close_req.pop(svc, None)
            lease = self.lease_for(body)
            self.attach(lease, svc, time.time())
            if svc in self.runs:
                self.note_stack(svc, lease)
        log(f"grant {svc} ({body['mode']}): the client starts it")
        return 202, {"lease": lease.id, "running": False, "eta_s": SERVICES[svc][2], "go": True}

    def beat(self, lid):
        """The client is alive and using the service (a call or a render runs): every beat resets the idle clock of the run and
        the lease. A beat extends the in-flight window (last_wake) only while a call is in flight."""
        with self.lock:
            lease = self.lease_of(lid)
            if lease is None:
                return 404, {"why": "unknown_lease"}
            now = time.time()
            lease.last_act = now                             # every beat is activity: the proxy beats only while a call or a render runs
            if lease.inflight > 0:
                lease.last_wake = now                        # only a call in flight extends the in-flight window
            for s in lease.svcs:
                if s in self.runs:
                    self.runs[s]["act"] = now
            close = next((self.close_req[s] for s in sorted(lease.svcs) if s in self.close_req), None)
        return 200, {"close": close}

    def down(self, lid):
        """The client closed its external service. /proc is the truth: the run ends when the process is gone (the tick sees it
        too); a start that never came up is dropped."""
        with self.lock:
            lease = self.lease_of(lid)
            if lease is None:
                return 404, {"why": "unknown_lease"}
            svcs = [s for s in sorted(lease.svcs) if s in EXTERNAL]
        ps = self.ext_ps()
        with self.lock:
            for s in svcs:
                if ps[s] == "running":
                    log(f"{s}: client reports it closed but its process is still there")
                elif s in self.starting:
                    self.starting.pop(s, None)
                    self.detach(s)
                    log(f"{s}: start abandoned by the client")
                elif s in self.running:
                    if s not in self.stopping:
                        self.close_req[s] = "released"       # the client closed it on its own
                    self._ext_finish(s)
        self.power_sync()
        return 200, {"ok": True}

    def done(self, lid, wakes=1):
        """One job finished. `wakes`: how many /wake calls that job made (a chained video asks once per segment and says done once):
        all of them leave the in-flight count, while the job counts once for a batch."""
        svcs = None
        with self.lock:
            lease = self.lease_of(lid)
            if lease is None:
                return 404, {"why": "unknown_lease"}
            now = time.time()
            lease.done += 1
            lease.inflight = max(0, lease.inflight - max(1, wakes))
            lease.last_act = now
            svc = lease.last_svc
            if svc in self.runs:
                self.runs[svc]["act"] = now
                st = self.runs[svc]["stacks"].setdefault(lease.stack, {"jobs": 0, "mode": lease.mode, "batches": []})
                st["jobs"] += 1
            count = lease.done
            if lease.mode == "batch" and lease.jobs and lease.done >= lease.jobs:
                svcs = set(lease.svcs)
                self.leases.pop(lease.id, None)
        if svcs is not None:
            self.stop_unheld(svcs, "batch_done")
        return 200, {"done": count, "closed": svcs is not None}

    def release(self, lid, close):
        with self.lock:
            lease = self.lease_of(lid)
            if lease is None:
                return 404, {"why": "unknown_lease"}
            svcs = set(lease.svcs)
            self.leases.pop(lease.id, None)
        return 200, {"stopped": self.stop_unheld(svcs, "released") if close else []}

    def off(self, stack, port):
        svc = None
        if port is not None:
            svc = self._svc_of(port)
            if svc is None:
                return 404, {"why": "unknown"}
        touched = set()
        with self.lock:
            for l in list(self.leases.values()):
                if l.stack == stack and l.mode == "interactive" and (svc is None or svc in l.svcs):
                    touched |= set(l.svcs)
                    self.leases.pop(l.id, None)
        return 200, {"stopped": self.stop_unheld(touched, "off")}

    def uptime_s(self):
        """Seconds the host has been up: /proc/uptime, else how long this gate has run. GPU hosts are off on purpose, so the ops bot judges
        "no selfcheck result yet" and "no check since boot" by this and not by wall-clock age alone."""
        try:
            with open(os.path.join(self.cfg.proc_dir, "uptime")) as f:
                return int(float(f.read().split()[0]))
        except (OSError, ValueError, IndexError):
            return int(time.monotonic() - self.t_start)

    def state(self):
        self.docker_ps()
        info = self.gpu.info()
        blocked = self.blocked()
        with self.lock:
            now = time.time()
            svcs = {}
            for n in SERVICES:
                hs = self.holders(n)
                running = n in self.running
                mode = "batch" if any(l.mode == "batch" for l in hs) else "interactive" if hs else None
                left = None
                if running and not self.batch_holds(n):
                    act = self.runs.get(n, {}).get("act", now)
                    left = max(0, int(self.cfg.service_idle(n) - (now - act)))
                svcs[n] = {"port": self.cfg.service_port(n), "running": running, "leases": len(hs), "mode": mode, "idle_left_s": left}
                if n in EXTERNAL:
                    svcs[n]["close"] = self.close_req.get(n)
            b = self.bench
        sc, dw = load_watch(self.cfg.state_dir)              # two small files: outside the lock like every other read
        why = sorted({f"running:{n}" for n in self.running} | {f"starting:{n}" for n in self.starting}
                     | {f"lease:{n}" for n, v in svcs.items() if v["leases"]} | ({"bench"} if b else set()))
        return {"gpu": {k: info[k] for k in ("name", "limit_w", "default_w", "min_w", "max_w", "free_mb")},
                "blocked": blocked, "services": svcs,
                # sleep_ok: nothing of the gate's would be cut by a host suspend (no service up or starting, no lease, no bench). A host
                # that suspends itself (pve4-dormir) asks this before sleeping; a service starting (loading its model) counts as busy.
                "sleep_ok": not why, "sleep_why": why,
                "bench": {"id": b["id"], "watts": b["watts"], "started": int(b["t0"])} if b else None,
                "up_s": self.uptime_s(), "selfcheck": sc, "driver_watch": dw}

    # ---- idle loop ----
    def _service_get(self, svc, path):
        url = f"http://{self.cfg.service_host}:{self.cfg.service_port(svc)}{path}"
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status, r.read(65536)

    def service_healthy(self, svc):
        """True when the service's own /healthz answers 200."""
        if svc in EXTERNAL:
            return True
        try:
            return self._service_get(svc, "/healthz")[0] == 200
        except OSError:
            return False

    def service_busy(self, svc):
        """True when the service's own /status says it works (the services expose it without a token)."""
        if svc in EXTERNAL:
            return False                                     # nothing listens: in-flight calls and /beat tell the gate
        try:
            d = json.loads(self._service_get(svc, "/status")[1])
        except (OSError, ValueError):
            return False
        if not isinstance(d, dict):
            return False
        lanes = d.get("lanes") if isinstance(d.get("lanes"), dict) else {}
        return d.get("state") == "running" or (num(d.get("queued")) or 0) > 0 or any(
            isinstance(v, dict) and (num(v.get("busy")) or 0) > 0 for v in lanes.values())

    def idle_expired(self, svc, now):
        """Lock held: no batch lease, no job in flight, and no activity for the service's idle time."""
        run = self.runs.get(svc)
        return bool(run) and not self.batch_holds(svc) and not self.inflight(svc, now) and now - run["act"] > self.cfg.service_idle(svc)

    def tick(self):
        with self.lock:
            b = self.bench
        if b:                                                # before any docker view: a bench must end even when docker is down
            if time.time() - b["t0"] > self.cfg.bench_ttl_s:
                log("bench expired (GATE_BENCH_TTL_S)")
                self.bench_end(b["id"])
            elif self.blocked():
                log("bench ended: a person's session or the operator's switch is active")
                self.bench_end(b["id"])
        if self.docker_ps() is None:
            return
        with self.lock:
            cand = sorted(set(self.running) - set(self.starting))
        busy = {s for s in cand if self.service_busy(s)}     # HTTP polls happen outside the lock
        if self.docker_ps() is None:
            return
        info = self.gpu.info()
        to_stop = []
        with self.lock:
            now = time.time()
            running = set(self.running) - set(self.starting)
            for s in sorted(running):
                if s not in self.runs:
                    log(f"found {s} running without a lease")
                    self.start_run(s, adopted=True)
            for s in list(self.starting):
                if s in EXTERNAL and now - self.starting[s] > 2 * SERVICES[s][2]:
                    log(f"{s}: granted but never showed up, grant dropped")
                    self.starting.pop(s)
                    self.detach(s)
            for s in list(self.stopping):
                if s in EXTERNAL and s not in self.running:  # its process left after the close request
                    self._ext_finish(s)
            for s in list(self.runs):
                if s not in running and s not in self.stopping and s not in self.starting:
                    log(f"{s} stopped outside the gate")
                    self.end_run(s, "gate_stop")             # stopped by hand or exited on its own
            running = {s for s in running if s in self.runs}
            dt = now - self.last_sample
            self.last_sample = now
            if running and info["draw_w"] is not None and dt < 600:
                for s in running:
                    self.runs[s]["wh"] += info["draw_w"] * dt / 3600.0 / len(running)
            for s in running:
                self.runs[s]["limit_w"] = info["limit_w"]
            for l in self.leases.values():
                if l.inflight > 0 and now - l.last_wake >= INFLIGHT_MAX_S:
                    log("lease in-flight count expired (wakes without a done)")
                    l.inflight = 0                           # the count cannot outlive its jobs
            for lid, l in list(self.leases.items()):
                if l.mode == "batch" and now - l.last_act > self.cfg.batch_ttl_s:
                    log("batch lease dropped (no activity for GATE_BATCH_TTL_S)")
                    self.leases.pop(lid)
            for s in sorted(running):
                if s in self.stopping:
                    continue
                if self.inflight(s, now) or s in busy:
                    self.runs[s]["act"] = now
                if self.idle_expired(s, now):
                    to_stop.append(s)
        for s in to_stop:
            self.stop_service(s, "idle", lambda x: self.idle_expired(x, time.time()))
        self.power_sync()

    # ---- bench: measure a power profile with nothing else on the card ----
    def bench_start(self, stack, watts):
        blocked = self.blocked()
        if blocked:
            return 409, {"why": blocked}                     # a person's VR session or the operator's switch: never cap the card
        ps = self.docker_ps()
        if ps is None:
            return 503, {"why": "unavailable"}
        with self.lock:
            cand = sorted(set(self.running))
        busy_by_status = any(self.service_busy(s) for s in cand)   # HTTP outside the lock
        with self.lock:
            now = time.time()
            if self.bench:
                return 409, {"why": "bench"}
            active = set(self.running) | set(self.starting)
            other = any(l.stack != stack for s in active for l in self.holders(s))
            unleased = any(not self.holders(s) for s in active)      # adopted, or left by a gate restart: whose is it?
            if busy_by_status or other or unleased or self.starting or self.waking or any(self.inflight(s, now) for s in SERVICES):
                return 409, {"why": "busy_jobs"}
            b = self.bench = {"id": secrets.token_hex(4), "watts": watts, "t0": now, "stack": stack}
        with self.power_lock:
            info = self.gpu.info()
            fresh = self.pw["found"] is None
            applied = None
            if info["limit_w"] is not None:
                if fresh:
                    self.pw["found"] = info["limit_w"]
                applied = self.gpu.set_limit(watts, info)
            if applied is None:
                if fresh:
                    self.pw["found"] = None
                with self.lock:
                    self.bench = None
                return 503, {"why": "power_failed"}
            self.pw["set"] = applied
            b["watts"] = applied
            self._save_power()
        log(f"bench {b['id']} started at {applied} W")
        return 200, {"bench": b["id"]}

    def bench_watts(self, bid, watts):
        with self.power_lock:
            with self.lock:
                b = self.bench
                if not b or b["id"] != bid:
                    return 404, {"why": "unknown_bench"}
            info = self.gpu.info()
            applied = self.gpu.set_limit(watts, info)
            if applied is None:
                return 503, {"why": "power_failed"}
            self.pw["set"] = applied
            b["watts"] = applied
            self._save_power()
        return 200, {"bench": bid, "watts": applied}

    def bench_end(self, bid):
        with self.power_lock:
            with self.lock:
                b = self.bench
                if not b or b["id"] != bid:
                    return 404, {"why": "unknown_bench"}
            info = self.gpu.info()
            if self.pw["set"] is not None and self.pw["found"] is not None:
                if info["limit_w"] is None:
                    # the limit cannot be read, but the write may still work: try it before the saved value is given up
                    if self.gpu.set_limit(self.pw["found"], info) is None:
                        log("bench: restore failed, the tick retries it")
                        self.restore_failed = True
                elif info["limit_w"] == self.pw["set"]:
                    if self.gpu.set_limit(self.pw["found"], info) is None:
                        log("bench: restore failed, the tick retries it")
                        self.restore_failed = True
                else:
                    log("power: limit changed by someone else, left as is")
            if not self.restore_failed:
                self.pw = {"found": None, "set": None}
                self.failed = None
                self._save_power()
            with self.lock:
                self.bench = None
        log(f"bench {bid} ended")
        self.power_sync()                                    # normal power logic resumes
        return 200, {"ok": True}

    def shutdown(self):
        with self.lock:
            for s in list(self.runs):
                self.end_run(s, "gate_stop")                 # services keep running; the next gate adopts them


def validate(path, d):
    """Return a cleaned body or None."""
    if not isinstance(d, dict):
        return None
    def s(k, null=False):
        v = d.get(k)
        return v if (isinstance(v, str) and NAME_RE.match(v)) or (null and v is None) else False
    def i(k, null=False, lo=1, hi=100000):
        v = d.get(k)
        return v if (type(v) is int and lo <= v <= hi) or (null and v is None) else False
    if path == "/wake":
        mode = d.get("mode", "interactive")
        stack, batch, jobs, port = s("stack"), s("batch", True) if "batch" in d else None, i("jobs", True) if "jobs" in d else None, i("port", lo=1, hi=65535)
        bench = s("bench", True) if "bench" in d else None
        if mode not in ("interactive", "batch") or False in (stack, batch, jobs, port, bench) or (mode == "batch" and not batch):
            return None
        return {"port": port, "stack": stack, "mode": mode, "batch": batch if mode == "batch" else None, "jobs": jobs if mode == "batch" else None,
                "bench": bench}
    if path == "/bench/start":
        stack, watts = s("stack"), i("watts", hi=1000)
        return None if False in (stack, watts) else {"stack": stack, "watts": watts}
    if path == "/bench/watts":
        bench, watts = s("bench"), i("watts", hi=1000)
        return None if False in (bench, watts) else {"bench": bench, "watts": watts}
    if path == "/bench/end":
        bench = s("bench")
        return {"bench": bench} if bench else None
    if path == "/done":
        lid, wakes = d.get("lease"), i("wakes", lo=1, hi=1000) if "wakes" in d else 1
        return {"lease": lid, "wakes": wakes} if isinstance(lid, str) and NAME_RE.match(lid) and wakes is not False else None
    if path in ("/beat", "/down"):
        lid = d.get("lease")
        return {"lease": lid} if isinstance(lid, str) and NAME_RE.match(lid) else None
    if path == "/release":
        lid, close = d.get("lease"), d.get("close", False)
        return {"lease": lid, "close": close} if isinstance(lid, str) and NAME_RE.match(lid) and isinstance(close, bool) else None
    if path == "/off":
        stack, port = s("stack"), i("port", True, 1, 65535) if "port" in d else None
        return None if False in (stack, port) else {"stack": stack, "port": port}
    return None


def make_handler(gate):
    cfg = gate.cfg

    class Handler(BaseHTTPRequestHandler):
        server_version = "gate"
        timeout = cfg.socket_timeout                        # an idle or half-sent connection is dropped, not held for ever

        def log_message(self, *a):
            pass

        def _send(self, code, obj, text=None):
            body = (text if text is not None else json.dumps(obj)).encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain" if text is not None else "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _auth(self, token=None):
            got = self.headers.get("Authorization", "")
            return hmac.compare_digest(got.encode(), ("Bearer " + (cfg.token if token is None else token)).encode())

        def do_GET(self):
            if self.path == "/healthz":
                return self._send(200, None, "ok gate")
            if not self._auth():
                return self._send(401, {"why": "token"})
            if self.path == "/state":
                return self._send(200, gate.state())
            self._send(404, {"why": "not_found"})

        def do_POST(self):
            if self.path.startswith("/bench/"):             # only the bench token; never the stacks' token, never a fallback to it
                if not cfg.bench_token:
                    return self._send(403, {"why": "bench_disabled"})
                if not self._auth(cfg.bench_token):
                    return self._send(401, {"why": "token"})
            elif not self._auth():
                return self._send(401, {"why": "token"})
            if self.path not in ("/wake", "/done", "/beat", "/down", "/release", "/off", "/bench/start", "/bench/watts", "/bench/end"):
                return self._send(404, {"why": "not_found"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = -1
            if n > MAX_BODY:
                self.rfile.read(min(n, 1 << 20))            # drain, so the client sees the answer and not a reset
                return self._send(413, {"why": "too_big"})
            try:
                if n <= 0:
                    raise ValueError
                body = validate(self.path, json.loads(self.rfile.read(n)))
            except (ValueError, UnicodeError):
                body = None
            if body is None:
                return self._send(400, {"why": "bad_request"})
            if self.path == "/wake":
                code, out = gate.wake(body)
            elif self.path == "/done":
                code, out = gate.done(body["lease"], body["wakes"])
            elif self.path == "/beat":
                code, out = gate.beat(body["lease"])
            elif self.path == "/down":
                code, out = gate.down(body["lease"])
            elif self.path == "/bench/start":
                code, out = gate.bench_start(body["stack"], body["watts"])
            elif self.path == "/bench/watts":
                code, out = gate.bench_watts(body["bench"], body["watts"])
            elif self.path == "/bench/end":
                code, out = gate.bench_end(body["bench"])
            elif self.path == "/release":
                code, out = gate.release(body["lease"], body["close"])
            else:
                code, out = gate.off(body["stack"], body["port"])
            self._send(code, out)

    return Handler


class Server(ThreadingHTTPServer):
    """One thread per connection, at most max_conns at a time: more are closed at once, so idle peers cannot starve the gate."""
    daemon_threads = True

    def __init__(self, addr, handler, max_conns):
        super().__init__(addr, handler)
        self.slots = threading.BoundedSemaphore(max_conns)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def main():
    cfg = Config()
    if not cfg.token:
        sys.exit("GATE_TOKEN is required (gpu-host/host.env): the gate never runs without a token")
    if cfg.bench_token_clash:
        log("GATE_BENCH_TOKEN equals GATE_TOKEN: bench mode stays off (it needs its own value)")
    elif not cfg.bench_token:
        log("GATE_BENCH_TOKEN is not set: /bench/* is refused")
    gate = Gate(cfg)
    gate.docker_ps()
    gate.tick()

    def loop():
        while True:
            time.sleep(cfg.tick_s)
            try:
                gate.tick()
            except Exception as e:                           # keep the loop alive; the next tick retries
                log(f"tick error: {type(e).__name__}")

    threading.Thread(target=loop, daemon=True).start()
    srv = Server((cfg.bind, cfg.port), make_handler(gate), cfg.max_conns)

    def bye(*_):
        gate.shutdown()
        os._exit(0)

    signal.signal(signal.SIGTERM, bye)
    log(f"gate listening on {cfg.bind}:{cfg.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        gate.shutdown()


if __name__ == "__main__":
    main()
