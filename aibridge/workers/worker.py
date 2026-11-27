#!/usr/bin/env python3
"""Always-on worker: run ONE scheduled job type for the people that have it, on a machine that never sleeps, so the Docker host (it
suspends itself when idle) and the people's stacks wake only because a person talks to them. WORKERS.md has the why, the data
ownership table, the events, and how to move a job from a stack to here.

  worker.py run TYPE [--stack S]   for each person with the job: pull (only if the host is awake) -> one-shot container -> push
  worker.py sync [--type T]        push what waits, when the host is awake (a timer every few minutes; never wakes the host)
  worker.py check [--ssh]          validate the config (and try BatchMode ssh to the Docker host)
  worker.py schedule TYPE          the type's systemd OnCalendar line (install.sh uses it)
  worker.py status                 per stack and type: last pull, last run, what waits to be pushed

Types (the method lives here; a job names only its TYPE and the person's paths):
  subs      the old Hermes cron `subs-nuevos`: /root/.hermes/scripts/subs_new.py on a local copy of the person's subtitles folder
            (channels.json + the registered channel folders of /workdir/descargas). What it prints (only when a human must know) is
            NOT sent to Telegram: it becomes a notice file in the person's workdir (.worker-notices/).
  jobnight  the old Hermes cron `jobnight`: /root/.hermes/scripts/jobnight.py (= jobpush.py --night) on a local copy of the
            person's jobfinder and /workdir/.prefs.json. Only the night summary goes back (merged into data/.jobpush-pending.json,
            which the waker's hook 50-job-summary or the web router hands to the person), plus the early-alert lines.
  revista   the Hermes AGENT cron `revista` (local data only, needs the model): the job's current prompt from the person's space,
            `hub revista` in a one-shot container, one chat request to the person's own provider (router.py's cloud order), the answer
            sent through the stack's own bot via the always-on Bot API server and saved as <workdir>/revista/<date>.md
            (revista_job.py has the pieces).

The container: the stacks' own image (`docker run --rm --restart=no`, default bridge network), no .env, no keys, no gateways.json,
memory/CPU/pids caps and a hard timeout from the config (on timeout: `docker kill`). Root inside (the scripts live in /root), with the
stacks' capability profile, and the files it wrote are given back to the worker's user at the end.

Data flow, no broker: files. `pull` = rsync over ssh from aibridge@<docker host>, only when `ssh true` answers (ops/project_publish.py
host_awake: an asleep host is "later", never woken); asleep = the last pulled copy, or a skip when there is none. `push` = rsync of
the outputs into the worker's inbox on the Docker host, then apply.py there puts them in the workdir by the ownership rules; never
--delete, never a person-owned file. Outputs wait (outgoing/) while the host sleeps; `sync` delivers them later.

Local data (people.<stack>.local_workdir): the person's workdir already lives on THIS machine (the operator moved it here and the
Docker host mounts it back over NFS). Then there is no pull, no push, no ssh and no "is the host awake": the container works on the
real folders in place, exactly as the stack's own cron did (jobnight writes the jobfinder's data/ itself: the night summary, its state,
the pipeline), and only what the cron used to print or send elsewhere (subs notices, early-alert lines) goes through apply.py, run here
by the same rules (`apply`: docker = a one-shot container as root with no network; direct = this python3). The files it wrote are NOT
chowned to the worker's user: they stay the stack's, as its own cron left them.

Tracing: every step is one line in <state_dir>/events.jsonl and, when ops/lib/bus.py has its config, the same event on the bus as
ev.worker.<type>.<event> (shadow mode, like ops/wake/waker.py): ids, counts and durations only, never text or paths.

Config: $WORKERS_CONFIG, else ~/.config/aibridge-workers/workers.json, else workers.json next to this file (git-ignored).
See workers.json.example. Standard library only.
"""
import argparse
import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(HERE, "lib"), os.path.join(os.path.dirname(HERE), "ops", "lib")):
    if os.path.isfile(os.path.join(_p, "bus.py")):
        sys.path.append(_p)   # appended, never first: nothing there may shadow a stdlib module
        break
try:
    import bus      # event bus, shadow mode (ops/lib/bus.py): off without its config
except ImportError:
    bus = None


def _load_beside(name):
    """A module that lives next to this file (python3 -I leaves this folder out of sys.path; an already imported one is reused)."""
    if name not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
        sys.modules[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[name])
    return sys.modules[name]


revista_job = _load_beside("revista_job")   # the revista type's space reader, model call and Telegram send
BUS_ON = False      # set by main(): the selftests import this module and must never publish

JOB_TYPES = ("subs", "jobnight", "revista")
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
CAPS = ("CHOWN", "DAC_OVERRIDE", "FOWNER", "KILL", "SETGID", "SETUID", "NET_RAW")   # the stacks' profile (ops/container_hardening.py)
APPLY_CAPS = ("CHOWN", "DAC_OVERRIDE", "FOWNER")
DEFAULTS = {"subs": {"memory": "1g", "cpus": 1, "timeout_s": 3600, "pids": 256},
            "jobnight": {"memory": "2g", "cpus": 2, "timeout_s": 3600, "pids": 512},
            # revista: memory/cpus/pids cap its two small containers (the space reader, `hub revista`); timeout_s is the whole run's
            # hard deadline (reader + hub + every model try + the sends)
            "revista": {"memory": "256m", "cpus": 0.5, "timeout_s": 900, "pids": 64}}
SCRIPTS = {"subs": "/root/.hermes/scripts/subs_new.py", "jobnight": "/root/.hermes/scripts/jobnight.py"}
SUBS_ENV = ("SUBS_BACKLOG_PER_RUN", "SUBS_PACE", "SUBS_SLOTS", "SUBS_STALL_HOURS", "SUBS_CLIENT", "SUBS_COOLDOWN_MIN", "SUBS_SOFT_COOLDOWN_MIN")
# subs: transient files that never travel, the per-channel scan state (shared: the newer copy wins), and the channel names it accepts
SUBS_TRANSIENT = (".subs.lock", ".todo.txt", "*.part", "*.tmp", "*.vtt", "*.ytdl", "*.worker-tmp")
SUBS_STATE = (".nocaps.tsv", ".unavailable.tsv", ".ids.cache", ".subs-progress.json")
SAFE_NAME = re.compile(r"^[A-Za-z0-9_@][A-Za-z0-9._@ -]{0,120}$")   # no wildcard, no slash, no leading dot
# jobnight: files of data/ the worker owns (never pulled over its own), the ones it seeds once from the host, what it does not copy at all
JOB_OWNED = ("data/.jobpush-state.json", "data/.jobpush-carry.json", "data/.jobpush-prescan.json", "data/.jobpush-pending.json",
             "data/.jobpush-running", "data/.jobpush-chain.out", "data/jobpush.log", "data/jobpush-scan.log", "data/scan-history.tsv",
             "data/scan-runs.tsv", "data/run-timings.tsv")
JOB_SEED = ("data/.jobpush-carry.json", "data/jobpush.log", "data/scan-history.tsv", "data/scan-runs.tsv", "data/run-timings.tsv")
JOB_SKIP = ("/.git/", "/output/", "/reports/", "/interview-prep/", "/batch/logs/", "*.lock", "*.part")   # not needed for a scan
TOLD_KEEP = 200
URL_RE = re.compile(r"https?://[^\s|]+")
ADDED_KEEP_DAYS = 14


class ConfigError(Exception):
    pass


# ---------------------------------------------------------------- config
def config_path():
    for p in (os.environ.get("WORKERS_CONFIG"), os.path.expanduser("~/.config/aibridge-workers/workers.json"), os.path.join(HERE, "workers.json")):
        if p and os.path.isfile(p):
            return p
    raise ConfigError("no config: set WORKERS_CONFIG or create ~/.config/aibridge-workers/workers.json (see workers.json.example)")


def _keys(d, allowed, where, errs):
    for k in d:
        if k not in allowed and not k.startswith("_"):
            errs.append(f"{where}: unknown key {k!r}")


def validate(cfg):
    """All the problems of a config, as short lines (an empty list = good). Strict: an unknown key is an error, "_comment" keys are fine."""
    errs = []
    if not isinstance(cfg, dict):
        return ["the config is not a JSON object"]
    _keys(cfg, ("host", "image", "host_image", "apply", "remote_inbox", "state_dir", "sync_every_min", "types", "people"), "config", errs)
    people_ = cfg.get("people") if isinstance(cfg.get("people"), dict) else {}
    all_local = bool(people_) and all(isinstance(pc, dict) and "local_workdir" in pc for pc in people_.values())
    if (not all_local or "host" in cfg) and not re.match(r"^[a-z_][a-z0-9_-]*@[A-Za-z0-9][A-Za-z0-9.-]*$", str(cfg.get("host", ""))):
        errs.append("host: want user@host (the Docker host's aibridge user); optional only when every person has local_workdir")
    for k in ("image", "host_image"):
        if k in cfg and not re.match(r"^[a-z0-9][a-z0-9._/:@-]{0,200}$", str(cfg[k])):
            errs.append(f"{k}: not an image name")
    if cfg.get("apply", "docker") not in ("docker", "direct"):
        errs.append("apply: docker or direct")
    for k in ("remote_inbox",):
        if k in cfg and not safe_remote(cfg[k]):
            errs.append(f"{k}: only letters, digits, . _ - / ~ and no '..'")
    if "sync_every_min" in cfg and not (isinstance(cfg["sync_every_min"], int) and 1 <= cfg["sync_every_min"] <= 60):
        errs.append("sync_every_min: 1..60")
    types = cfg.get("types")
    if not isinstance(types, dict) or not types:
        errs.append("types: at least one job type")
        types = {}
    for t, tc in types.items():
        if t not in JOB_TYPES:
            errs.append(f"types.{t}: unknown type (known: {', '.join(JOB_TYPES)})")
            continue
        if not isinstance(tc, dict):
            errs.append(f"types.{t}: not an object")
            continue
        _keys(tc, ("schedule", "memory", "cpus", "timeout_s", "pids"), f"types.{t}", errs)
        if not re.match(r"^[A-Za-z0-9 *:/,._+~-]{1,120}$", str(tc.get("schedule", ""))):
            errs.append(f"types.{t}.schedule: a systemd OnCalendar expression")
        if "memory" in tc and not re.match(r"^[1-9][0-9]{0,5}[kmg]$", str(tc["memory"])):
            errs.append(f"types.{t}.memory: like 512m or 2g")
        if "cpus" in tc and not (isinstance(tc["cpus"], (int, float)) and 0.1 <= tc["cpus"] <= 64):
            errs.append(f"types.{t}.cpus: 0.1..64")
        if "timeout_s" in tc and not (isinstance(tc["timeout_s"], int) and 1 <= tc["timeout_s"] <= 86400):
            errs.append(f"types.{t}.timeout_s: 1..86400 seconds")
        if "pids" in tc and not (isinstance(tc["pids"], int) and 16 <= tc["pids"] <= 4096):
            errs.append(f"types.{t}.pids: 16..4096")
    people = cfg.get("people")
    if not isinstance(people, dict) or not people:
        errs.append("people: at least one stack")
        people = {}
    for s, pc in people.items():
        if not re.match(r"^[a-z0-9][a-z0-9_-]{0,31}$", s):
            errs.append(f"people.{s}: a stack name ([a-z0-9_-])")
            continue
        if not isinstance(pc, dict):
            errs.append(f"people.{s}: not an object")
            continue
        _keys(pc, ("remote_workdir", "local_workdir", "jobs"), f"people.{s}", errs)
        if "remote_workdir" in pc and not safe_remote(pc["remote_workdir"]):
            errs.append(f"people.{s}.remote_workdir: only letters, digits, . _ - / ~ and no '..'")
        if "local_workdir" in pc:
            lw = str(pc["local_workdir"])
            if "remote_workdir" in pc:
                errs.append(f"people.{s}: remote_workdir or local_workdir, not both")
            if not (lw.startswith("/") and safe_remote(lw) and lw.rstrip("/") not in ("", "/")):
                errs.append(f"people.{s}.local_workdir: an absolute path on this machine (letters, digits, . _ - /, no '..')")
        jobs = pc.get("jobs")
        if not isinstance(jobs, dict) or not jobs:
            errs.append(f"people.{s}.jobs: at least one job")
            continue
        for t, jc in jobs.items():
            where = f"people.{s}.jobs.{t}"
            if t not in types:
                errs.append(f"{where}: no such type in types")
                continue
            if not isinstance(jc, dict):
                errs.append(f"{where}: not an object")
                continue
            if t == "subs":
                _keys(jc, ("subs_dir", "env"), where, errs)
                if not re.match(r"^[A-Za-z0-9._-]{1,64}$", str(jc.get("subs_dir", "descargas"))) or jc.get("subs_dir") in (".", ".."):
                    errs.append(f"{where}.subs_dir: one folder name")
                env = jc.get("env", {})
                if not isinstance(env, dict):
                    errs.append(f"{where}.env: an object")
                    env = {}
                for k, v in env.items():
                    if k not in SUBS_ENV:
                        errs.append(f"{where}.env: {k} is not one of {', '.join(SUBS_ENV)}")
                    elif not re.match(r"^[A-Za-z0-9._-]{1,32}$", str(v)):
                        errs.append(f"{where}.env.{k}: a short plain value")
            if t == "revista":
                validate_revista(jc, pc, where, errs)
            if t == "jobnight":
                _keys(jc, ("timezone", "lang", "jobfinder_dir"), where, errs)
                tz = str(jc.get("timezone", ""))
                if not re.match(r"^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+){0,2}$", tz):
                    errs.append(f"{where}.timezone: required, like America/Argentina/Buenos_Aires (the person's zone: the night key and the 12-21 h refusal use it)")
                else:
                    try:
                        import zoneinfo
                        zoneinfo.ZoneInfo(tz)
                    except Exception:
                        errs.append(f"{where}.timezone: {tz} is not a zone this machine knows")
                if "lang" in jc and jc["lang"] not in ("es", "ru", "en"):
                    errs.append(f"{where}.lang: es, ru or en")
                if not re.match(r"^[A-Za-z0-9._-]{1,64}$", str(jc.get("jobfinder_dir", "jobfinder"))) or jc.get("jobfinder_dir") in (".", ".."):
                    errs.append(f"{where}.jobfinder_dir: one folder name")
    return errs


def _abs_ok(p):
    p = str(p)
    return p.startswith("/") and safe_remote(p) and p.rstrip("/") not in ("", "/")


def validate_revista(jc, pc, where, errs):
    _keys(jc, ("job", "local_persist", "local_hub", "local_gateways", "local_stack_env", "bot_api", "timezone", "cloud_order",
               "model_timeout_s"), where, errs)
    if "local_workdir" not in pc:
        errs.append(f"{where}: the revista runs in local data mode only (local_workdir, WORKERS.md 2b)")
    if not re.match(r"^[A-Za-z0-9._-]{1,64}$", str(jc.get("job", "revista"))):
        errs.append(f"{where}.job: the Hermes cron job's name")
    if not _abs_ok(jc.get("local_hub", "")):
        errs.append(f"{where}.local_hub: required, the absolute path of the person's hub folder on this machine (<hubdata>/people/<stack>)")
    for k in ("local_persist", "local_gateways", "local_stack_env"):
        if k in jc and not _abs_ok(jc[k]):
            errs.append(f"{where}.{k}: an absolute path on this machine (letters, digits, . _ - /, no '..')")
    if "bot_api" in jc and not re.match(r"^https?://[A-Za-z0-9.-]{1,253}(:[0-9]{1,5})?/?$", str(jc["bot_api"])):
        errs.append(f"{where}.bot_api: the Bot API server's base URL, like http://<host>:<port> (no path, no token)")
    if "timezone" in jc:
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(str(jc["timezone"]))
        except Exception:
            errs.append(f"{where}.timezone: not a zone this machine knows")
    co = jc.get("cloud_order", [])
    if not (isinstance(co, list) and all(isinstance(x, str) and len(x) <= 80 for x in co)):
        errs.append(f"{where}.cloud_order: a list of router.py CLOUD names")
    if "model_timeout_s" in jc and not (isinstance(jc["model_timeout_s"], int) and 10 <= jc["model_timeout_s"] <= 900):
        errs.append(f"{where}.model_timeout_s: 10..900 seconds")


def safe_remote(p):
    p = str(p)
    return bool(re.match(r"^[A-Za-z0-9._/~-]{1,300}$", p)) and ".." not in p.split("/") and not p.startswith("-")


def load_config(path=None):
    path = path or config_path()
    try:
        cfg = json.load(open(path))
    except (OSError, ValueError) as e:
        raise ConfigError(f"cannot read {path}: {type(e).__name__}")
    errs = validate(cfg)
    if errs:
        raise ConfigError("bad config " + path + ":\n  " + "\n  ".join(errs))
    cfg.setdefault("image", "aibridge-hermes-agent:latest")
    cfg.setdefault("host_image", cfg["image"])
    cfg.setdefault("apply", "docker")
    cfg.setdefault("remote_inbox", "aibridge/worker-inbox")
    cfg.setdefault("sync_every_min", 2)
    cfg["state_dir"] = os.path.expanduser(cfg.get("state_dir") or "~/.local/share/aibridge-workers")
    for t, tc in cfg["types"].items():
        for k, v in DEFAULTS[t].items():
            tc.setdefault(k, v)
    for s, pc in cfg["people"].items():
        if "local_workdir" not in pc:
            pc.setdefault("remote_workdir", f"aibridge/stacks/{s}/workdir")
    return cfg


# ---------------------------------------------------------------- tracing
def token(x):
    return re.sub(r"[^a-z0-9_-]", "_", str(x).lower())[:64] or "_"


def emit(cfg, jtype, event, **data):
    """One event: a line in <state_dir>/events.jsonl and, when the bus is on, ev.worker.<type>.<event> on the bus. data: ids, counts,
    durations, short enums; anything else is dropped here (a value is never free text)."""
    clean = {}
    for k, v in data.items():
        if isinstance(v, bool) or isinstance(v, int) or (isinstance(v, float) and v == v):
            clean[k] = round(v, 1) if isinstance(v, float) else v
        elif isinstance(v, str) and re.match(r"^[a-z0-9_.:-]{1,64}$", v):
            clean[k] = v
    subject = f"ev.worker.{token(jtype)}.{token(event)}"
    rec = {"ts": round(time.time(), 3), "subject": subject, "data": clean}
    try:
        os.makedirs(cfg["state_dir"], mode=0o700, exist_ok=True)
        fd = os.open(os.path.join(cfg["state_dir"], "events.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    except OSError:
        pass
    if BUS_ON:
        try:
            # synchronous: this is a short-lived command, a queued event would die with it
            bus.send(subject, dict(clean, pub_ts=rec["ts"]), f"{clean.get('run') or clean.get('stack', '-')}-{token(event)}-{int(rec['ts'] * 1000)}")
        except Exception:
            pass
    return rec


# ---------------------------------------------------------------- ssh / rsync
def ssh(cfg, command, input=None, timeout=120):
    return subprocess.run(["ssh", *SSH_OPTS, cfg["host"], command], input=input, capture_output=True, timeout=timeout)


def host_awake(cfg):
    """Can the Docker host be reached now (ops/project_publish.py host_awake)? It suspends itself when nobody uses it: asleep is
    "later", never a failure, and this never wakes it."""
    try:
        return ssh(cfg, "true", timeout=30).returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def rsync(*args, timeout=3600):
    """rsync -a over the same BatchMode ssh; returns (exit code, files transferred, stderr tail). Never --delete towards the host."""
    cmd = ["rsync", "-a", "--stats", "-e", "ssh " + " ".join(SSH_OPTS), *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, 0, "timeout"
    m = re.search(r"Number of regular files transferred: ([\d,.]+)", r.stdout)
    return r.returncode, int(re.sub(r"[,.]", "", m.group(1))) if m else 0, r.stderr.strip()[-1000:]


def remote_abs(p):
    """A remote path as the remote shell should see it: relative paths are under the aibridge user's home."""
    return shlex.quote(p) if p.startswith("/") else '"$HOME"/' + shlex.quote(p)


# ---------------------------------------------------------------- one job of one person
class Job:
    kind = None

    def __init__(self, cfg, stack):
        self.cfg, self.stack = cfg, stack
        self.tc = cfg["types"][self.kind]
        self.pc = cfg["people"][stack]
        self.jc = self.pc["jobs"][self.kind]
        self.base = os.path.join(cfg["state_dir"], stack, self.kind)
        self.copy = os.path.join(self.base, "copy")
        self.outgoing = os.path.join(self.base, "outgoing")
        self.lwd = self.pc["local_workdir"].rstrip("/") if "local_workdir" in self.pc else None   # local data mode
        self.wd = self.lwd or self.pc["remote_workdir"].rstrip("/")
        self.inbox = f"{cfg['remote_inbox'].rstrip('/')}/{stack}/{self.kind}"
        self.run_id = f"{self.kind}-{stack}-{int(time.time())}"
        for d in (self.base, self.copy, self.outgoing):
            os.makedirs(d, mode=0o700, exist_ok=True)

    # --- meta and lock
    def meta(self):
        try:
            return json.load(open(os.path.join(self.base, "meta.json")))
        except (OSError, ValueError):
            return {}

    def save_meta(self, **kw):
        m = self.meta()
        m.update(kw)
        tmp = os.path.join(self.base, "meta.json.tmp")
        with open(tmp, "w") as f:
            json.dump(m, f)
        os.replace(tmp, os.path.join(self.base, "meta.json"))

    def lock(self):
        f = open(os.path.join(self.base, ".lock"), "a")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except OSError:
            f.close()
            return None

    def ev(self, event, **data):
        return emit(self.cfg, self.kind, event, stack=self.stack, run=token(self.run_id), **data)

    def has_copy(self):
        return bool(self.meta().get("last_pull"))

    # --- the parts each type fills in
    def pull(self):
        """Refresh the local copy. True = fresh, False = failed (a run may use the last copy), None = do not run at all."""
        raise NotImplementedError

    def container(self):
        """(mounts [(host, container, ro)], env {k: v})."""
        raise NotImplementedError

    def before_run(self):
        pass

    def after_run(self, stdout):
        pass

    def apply_args(self):
        raise NotImplementedError

    def waiting(self):
        """Files waiting in outgoing/ (or in the host inbox, not applied yet)."""
        n = sum(len(f) for _, _, f in os.walk(self.outgoing))
        return n + (1 if self.meta().get("inbox_dirty") else 0)

    # --- the container
    def docker_cmd(self, name):
        mounts, env = self.container()
        cmd = ["docker", "run", "--rm", "--name", name, "--restart=no", "--network", "bridge",
               "--memory", self.tc["memory"], "--memory-swap", self.tc["memory"], "--cpus", str(self.tc["cpus"]),
               "--pids-limit", str(self.tc["pids"]), "--security-opt", "no-new-privileges", "--cap-drop", "ALL"]
        for c in CAPS:
            cmd += ["--cap-add", c]
        cmd += ["--label", f"aibridge.worker={self.kind}"]
        for src, dst, ro in mounts:
            cmd += ["-v", f"{src}:{dst}" + (":ro" if ro else "")]
        for k, v in sorted(env.items()):
            cmd += ["-e", f"{k}={v}"]
        # the files the job wrote go back to this user (the scripts need root: they live in /root/.hermes/scripts)
        # local data: the real folders, left to the stack's owner (no chown); a copy: given to this user
        owner = "" if self.lwd else f"{os.getuid()}:{os.getgid()}"
        cmd += ["--entrypoint", "/bin/sh", self.cfg["image"], "-c",
                'python3 "$1"; rc=$?; [ -z "$2" ] || chown -R "$2" /workdir 2>/dev/null; exit $rc', "worker", SCRIPTS[self.kind], owner]
        return cmd

    def run_container(self):
        """Returns (result, rc, stdout). result: ok | exit | timeout | docker."""
        name = f"aibridge-worker-{self.kind}-{self.stack}"
        log_path = os.path.join(self.base, "last-run.log")
        try:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60)   # a leftover of a crashed run of ours
            p = subprocess.Popen(self.docker_cmd(name), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
        except (OSError, subprocess.SubprocessError):
            return "docker", -1, ""
        try:
            out, err = p.communicate(timeout=self.tc["timeout_s"])
            result = "ok" if p.returncode == 0 else "docker" if p.returncode in (125, 126, 127) else "exit"
        except subprocess.TimeoutExpired:
            try:
                subprocess.run(["docker", "kill", name], capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError):
                pass
            try:
                out, err = p.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                p.kill()
                out, err = p.communicate()
            result = "timeout"
        try:   # the operator's local log of the last run (this machine only, mode 600): never an event, never pushed
            fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {self.run_id} result={result} rc={p.returncode}\n--- stdout\n{out[-20000:]}\n--- stderr\n{err[-20000:]}\n")
        except OSError:
            pass
        return result, p.returncode, out or ""

    # --- the whole run
    def run(self):
        lk = self.lock()
        if lk is None:
            self.ev("skipped", reason="busy")
            return 0
        with lk:
            t0 = time.time()
            if self.lwd:
                if not os.path.isdir(self.lwd):
                    self.ev("failed", reason="local_missing", rc=0)
                    return 1
                self.save_meta(last_pull=int(t0))   # the data is here: always "fresh"
            elif host_awake(self.cfg):
                ok = self.pull()
                if ok is None:
                    return 1
                if not ok and not self.has_copy():
                    self.ev("skipped", reason="nothing_to_run")
                    return 0
            else:
                self.ev("skipped_host_asleep", has_copy=self.has_copy(), waiting=self.waiting(), step="pull")
                if not self.has_copy():
                    return 0
            m = self.meta()
            self.ev("started", copy_age_s=int(t0 - m.get("last_pull", t0)))
            self.before_run()
            t1 = time.time()
            result, rc, out = self.run_container()
            produced = self.after_run(out)
            secs = round(time.time() - t1, 1)
            self.save_meta(last_run={"ts": int(t1), "result": result, "rc": rc, "secs": secs})
            if result == "ok":
                self.ev("done", secs=secs, rc=rc, **produced)
            else:
                self.ev("failed", reason=result, rc=rc if isinstance(rc, int) else -1, secs=secs, **produced)
            if self.waiting():
                if self.lwd or host_awake(self.cfg):
                    self.push()
                else:
                    self.ev("skipped_host_asleep", has_copy=True, waiting=self.waiting(), step="push")
            return 0 if result == "ok" else 1

    def sync(self):
        """Push what waits, if anything and if the host is awake. Quiet: an asleep host is not an event here (every few minutes)."""
        if not self.waiting():
            return 0
        lk = self.lock()
        if lk is None:
            return 0
        with lk:
            if not self.lwd and not host_awake(self.cfg):
                return 0
            return self.push()

    def push(self):
        """outgoing/ -> the worker's inbox on the host (rsync, sent files leave outgoing/), then apply.py there."""
        t0 = time.time()
        sent = 0
        if self.lwd:
            return self.apply_local(t0)
        if any(f for _, _, f in os.walk(self.outgoing)):
            r = ssh(self.cfg, "mkdir -p " + remote_abs(self.inbox))
            if r.returncode != 0:
                self.ev("failed", reason="push_inbox", rc=r.returncode)
                return 1
            self.save_meta(inbox_dirty=True)
            rc, sent, _ = rsync("--remove-source-files", self.outgoing + "/", f"{self.cfg['host']}:{self.inbox}/")
            prune_empty(self.outgoing)
            if rc != 0:
                self.ev("failed", reason="push_rsync", rc=rc)
                return 1
        try:
            r = ssh(self.cfg, self.apply_command(), input=open(os.path.join(HERE, "apply.py"), "rb").read(), timeout=600)
        except (subprocess.SubprocessError, OSError):
            self.ev("failed", reason="push_apply", rc=-1)
            return 1
        try:
            counts = json.loads(r.stdout.decode().strip().splitlines()[-1])
        except (ValueError, IndexError):
            counts = {}
        counts = {k: v for k, v in counts.items() if isinstance(v, int)}
        if r.returncode != 0:
            self.ev("failed", reason="push_apply", rc=r.returncode, **counts)
            return 1
        self.save_meta(inbox_dirty=False, last_push=int(time.time()))
        self.ev("pushed", files=sent, secs=round(time.time() - t0, 1), **counts)
        return 0

    def apply_local(self, t0):
        """Local data: apply.py here, outgoing/ as its inbox, the real workdir as the target (same rules as on the Docker host)."""
        args = ["--type", self.kind] + self.apply_args()
        if self.cfg["apply"] == "direct":
            cmd = [sys.executable, os.path.join(HERE, "apply.py"), *args, "--inbox", self.outgoing, "--workdir", self.lwd]
            stdin = None
        else:
            cmd = ["docker", "run", "--rm", "-i", "--restart=no", "--network", "none", "--memory", "256m", "--pids-limit", "64",
                   "--security-opt", "no-new-privileges", "--cap-drop", "ALL"]
            for c in APPLY_CAPS:
                cmd += ["--cap-add", c]
            cmd += ["-v", f"{self.lwd}:/workdir", "-v", f"{self.outgoing}:/inbox", "--entrypoint", "python3", self.cfg["host_image"],
                    "-", *args, "--inbox", "/inbox", "--workdir", "/workdir"]
            stdin = open(os.path.join(HERE, "apply.py"), "rb").read()
        try:
            r = subprocess.run(cmd, input=stdin, capture_output=True, timeout=600)
        except (subprocess.SubprocessError, OSError):
            self.ev("failed", reason="push_apply", rc=-1)
            return 1
        try:
            counts = json.loads(r.stdout.decode().strip().splitlines()[-1])
        except (ValueError, IndexError):
            counts = {}
        counts = {k: v for k, v in counts.items() if isinstance(v, int)}
        prune_empty(self.outgoing)
        if r.returncode != 0:
            self.ev("failed", reason="push_apply", rc=r.returncode, **counts)
            return 1
        self.save_meta(inbox_dirty=False, last_push=int(time.time()))
        self.ev("pushed", files=0, secs=round(time.time() - t0, 1), **counts)
        return 0

    def apply_command(self):
        args = ["--type", self.kind] + self.apply_args()
        if self.cfg["apply"] == "direct":
            return " ".join(["python3", "-", *args, "--inbox", remote_abs(self.inbox), "--workdir", remote_abs(self.wd)])
        cmd = ["docker", "run", "--rm", "-i", "--restart=no", "--network", "none", "--memory", "256m", "--pids-limit", "64",
               "--security-opt", "no-new-privileges", "--cap-drop", "ALL"]
        for c in APPLY_CAPS:
            cmd += ["--cap-add", c]
        cmd += ["-v", f"{remote_abs(self.wd)}:/workdir", "-v", f"{remote_abs(self.inbox)}:/inbox",
                "--entrypoint", "python3", shlex.quote(self.cfg["host_image"]), "-", *args, "--inbox", "/inbox", "--workdir", "/workdir"]
        return " ".join(cmd)


def prune_empty(root):
    for d, _, _ in os.walk(root, topdown=False):
        if d != root:
            try:
                os.rmdir(d)
            except OSError:
                pass


def stamp():
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + f".{int(time.time() * 1000) % 1000:03d}Z"


# ---------------------------------------------------------------- subs
class SubsJob(Job):
    """The subtitles of the person's registered channels. Local copy: copy/ = their /workdir/descargas, but only channels.json, the
    registered channel folders and the shared pause file; nothing else of their downloads."""
    kind = "subs"

    def __init__(self, cfg, stack):
        super().__init__(cfg, stack)
        self.rdir = f"{self.wd}/{self.jc.get('subs_dir', 'descargas')}"

    def channels(self):
        try:
            reg = json.load(open(os.path.join(self.copy, "channels.json")))
        except (OSError, ValueError):
            return []
        return sorted(n for n in reg if isinstance(n, str) and SAFE_NAME.match(n)) if isinstance(reg, dict) else []

    def state_filters(self, names):
        f = ["--include=/.subs-cooldown"]
        for n in names:
            f += [f"--include=/{n}/"] + [f"--include=/{n}/{s}" for s in SUBS_STATE]
        return f + ["--exclude=*"]

    def pull(self):
        t0 = time.time()
        host = self.cfg["host"]
        # 1. the registry is the person's: the host's copy wins
        rc, n1, err = rsync(f"{host}:{self.rdir}/channels.json", os.path.join(self.copy, "channels.json"))
        if rc != 0:
            self.ev("failed", reason="pull_no_channels" if "No such file" in err else "pull", rc=rc)
            return False
        names = self.channels()
        # 2. what the host has and the worker does not (new channels, subtitles fetched there by hand): never over the worker's files
        filt = [f"--exclude={x}" for x in SUBS_TRANSIENT] + [f"--include=/{n}/***" for n in names] + ["--exclude=*"]
        rc2, n2, _ = rsync("--ignore-existing", *filt, f"{host}:{self.rdir}/", self.copy + "/")
        # 3. the shared scan state and the pause: the newer copy wins
        rc3, n3, _ = rsync("--update", *self.state_filters(names), f"{host}:{self.rdir}/", self.copy + "/")
        if rc2 not in (0, 24) or rc3 not in (0, 24):
            self.ev("failed", reason="pull", rc=rc2 or rc3)
            return self.has_copy()
        self.save_meta(last_pull=int(time.time()))
        self.ev("pulled", files=n1 + n2 + n3, channels=len(names), secs=round(time.time() - t0, 1))
        return True

    def container(self):
        env = {"SUBS_PARENT": "/workdir/descargas"}
        env.update({k: str(v) for k, v in self.jc.get("env", {}).items()})
        src = os.path.join(self.lwd, self.jc.get("subs_dir", "descargas")) if self.lwd else self.copy
        return [(src, "/workdir/descargas", False)], env

    def snapshot(self):
        out = {}
        for n in self.channels():
            d = os.path.join(self.copy, n)
            try:
                for e in os.scandir(d):
                    if e.is_file(follow_symlinks=False):
                        out[f"{n}/{e.name}"] = e.stat().st_mtime
            except OSError:
                pass
        try:
            out[".subs-cooldown"] = os.stat(os.path.join(self.copy, ".subs-cooldown")).st_mtime
        except OSError:
            pass
        return out

    def before_run(self):
        self._before = {} if self.lwd else self.snapshot()

    def after_run(self, stdout):
        """New subtitle files and changed scan state go to outgoing/; what the script printed becomes a notice file. Local data: the
        subtitles and the state are already in place, only the notice goes through apply.py."""
        after = {} if self.lwd else self.snapshot()
        new_srt = changed = 0
        for rel, mt in after.items():
            name = rel.rsplit("/", 1)[-1]
            src = os.path.join(self.copy, rel)
            if name.endswith(".srt") and rel not in self._before:
                dst = os.path.join(self.outgoing, "srt", rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
                new_srt += 1
            elif (name in SUBS_STATE or rel == ".subs-cooldown") and mt != self._before.get(rel):
                dst = os.path.join(self.outgoing, "state", rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)   # a snapshot: the next run may change the local one again
                changed += 1
        notices = 0
        if stdout.strip():
            d = os.path.join(self.outgoing, "notices")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"subs-{stamp()}.txt"), "w", encoding="utf-8") as f:
                f.write(stdout.strip() + "\n")
            notices = 1
            self.ev("notice", count=1)
        return {"new_files": new_srt, "state_files": changed, "notices": notices}

    def apply_args(self):
        return ["--subs-dir", self.jc.get("subs_dir", "descargas")]


# ---------------------------------------------------------------- jobnight
class JobnightJob(Job):
    """The night job scan. Local copy: copy/jobfinder (the person's jobfinder without its outputs), copy/prefs.json (/workdir/.prefs.json),
    copy/hermes-config.yaml (only `timezone:`, from the config), copy/out/ (the early-alert lines)."""
    kind = "jobnight"

    def __init__(self, cfg, stack):
        super().__init__(cfg, stack)
        self.jdir = self.jc.get("jobfinder_dir", "jobfinder")
        self.rjob = f"{self.wd}/{self.jdir}"
        self.local = os.path.join(self.copy, "jobfinder")
        self.data = os.path.join(self.local, "data")
        self.added = os.path.join(self.base, "pipeline-added.jsonl")

    def pull(self):
        t0 = time.time()
        host = self.cfg["host"]
        os.makedirs(self.local, exist_ok=True)
        prefs = os.path.join(self.copy, "prefs.json")
        rc0, n0, err0 = rsync(f"{host}:{self.wd}/.prefs.json", prefs)
        if rc0 != 0 and "No such file" not in err0:
            self.ev("failed", reason="pull", rc=rc0)
            return self.has_copy()
        if not os.path.exists(prefs):
            with open(prefs, "w") as f:
                f.write("{}")
        # 1. the person's jobfinder, the host's copy wins (code, portals, profile, tracker, pipeline); the worker's own files of data/
        #    are excluded, which also keeps --delete (local copy only) away from them
        excl = [f"--exclude=/{p}" for p in JOB_OWNED] + [f"--exclude={p}" for p in JOB_SKIP]
        rc1, n1, err1 = rsync("--delete", *excl, f"{host}:{self.rjob}/", self.local + "/")
        if rc1 != 0:
            self.ev("failed", reason="pull_no_jobfinder" if "No such file" in err1 else "pull", rc=rc1)
            return self.has_copy()
        # 2. the worker's own history, seeded once from the host
        seed = ["--include=/data/"] + [f"--include=/{p}" for p in JOB_SEED] + ["--exclude=*"]
        rc2, n2, _ = rsync("--ignore-existing", *seed, f"{host}:{self.rjob}/", self.local + "/")
        # 3. what the person's side marked as told (the summary is acknowledged on the host) and the night already scanned there
        inc = os.path.join(self.base, "incoming-state.json")
        rc3, _, err3 = rsync(f"{host}:{self.rjob}/data/.jobpush-state.json", inc)
        if rc3 == 0:
            self.merge_state(inc)
        self.readd_pipeline()
        if not self.data_root_ok():
            self.ev("failed", reason="data_root_elsewhere", rc=0)
            return None
        self.save_meta(last_pull=int(time.time()))
        self.ev("pulled", files=n0 + n1 + n2, secs=round(time.time() - t0, 1))
        return rc2 in (0, 24)

    def data_root_ok(self):
        """A .career-ops-data marker that sends the data somewhere outside the jobfinder folder is not supported (only that folder is copied)."""
        try:
            v = open(os.path.join(self.local, ".career-ops-data")).read().strip()
        except OSError:
            return True
        return not v or (not v.startswith("/") and ".." not in v.split("/")) or v.rstrip("/") == "/workdir/" + self.jdir

    def merge_state(self, incoming):
        """From the host's data/.jobpush-state.json take only what the person's side writes (told lists, last message, the night it
        already scanned): the worker's counters and carry stay the worker's."""
        try:
            host = json.load(open(incoming))
        except (OSError, ValueError):
            return
        path = os.path.join(self.data, ".jobpush-state.json")
        try:
            mine = json.load(open(path))
        except (OSError, ValueError):
            mine = None
        if not isinstance(host, dict):
            return
        if not isinstance(mine, dict):
            mine = dict(host)
        else:
            for k in ("closing_told", "expired_told"):
                seen = list(dict.fromkeys(list(mine.get(k) or []) + list(host.get(k) or [])))
                mine[k] = seen[-TOLD_KEEP:]
            mine["last_message"] = max(mine.get("last_message") or 0, host.get("last_message") or 0)
            if str(host.get("night_done") or "") > str(mine.get("night_done") or ""):
                mine["night_done"] = host["night_done"]
        os.makedirs(self.data, exist_ok=True)
        with open(path + ".tmp", "w") as f:
            json.dump(mine, f)
        os.replace(path + ".tmp", path)

    def pipeline_lines(self):
        try:
            return open(os.path.join(self.data, "pipeline.md"), encoding="utf-8").read().splitlines()
        except OSError:
            return []

    def readd_pipeline(self):
        """The host's pipeline.md just replaced the local one. Offers the worker's scans added and the host never got (it is the
        person's file: nothing goes back) are added again to the LOCAL copy, so a carried offer is still "in the pipeline" for jobpush."""
        now = time.time()
        rows = []
        try:
            for line in open(self.added, encoding="utf-8"):
                r = json.loads(line)
                if now - r["ts"] < ADDED_KEEP_DAYS * 86400:
                    rows.append(r)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        have = set()
        for line in self.pipeline_lines():
            have.update(URL_RE.findall(line))
        extra = [r["line"] for r in rows if not set(URL_RE.findall(r["line"])) & have]
        if extra:
            with open(os.path.join(self.data, "pipeline.md"), "a", encoding="utf-8") as f:
                f.write("\n".join(extra) + "\n")
        self._write_added(rows)

    def _write_added(self, rows):
        fd = os.open(self.added, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    def container(self):
        tz = os.path.join(self.copy, "hermes-config.yaml")
        with open(tz, "w") as f:
            f.write(f"timezone: {self.jc['timezone']}\n")
        out = os.path.join(self.copy, "out")
        os.makedirs(out, exist_ok=True)
        env = {"JOBPUSH_HERMES_CONFIG": "/worker/hermes-config.yaml",
               "GATEWAYS_CONFIG": "/worker/no-gateways.json",            # job_decide needs the person's key: off here
               "JOBPUSH_SHARED_STORE": "/worker/no-shared-store",
               "JOBPUSH_EARLY_SIGNALS": "/workdir/.worker-out/early-signals.jsonl"}
        if self.jc.get("lang"):
            env["JOBPUSH_LANG"] = self.jc["lang"]
        if self.lwd:   # the real jobfinder and prefs, in place
            prefs = os.path.join(self.lwd, ".prefs.json")
            if not os.path.isfile(prefs):
                prefs = os.path.join(self.copy, "prefs.json")
                with open(prefs, "w") as f:
                    f.write("{}")
            mounts = [(os.path.join(self.lwd, self.jdir), f"/workdir/{self.jdir}", False), (prefs, "/workdir/.prefs.json", True),
                      (tz, "/worker/hermes-config.yaml", True), (out, "/workdir/.worker-out", False)]
        else:
            mounts = [(self.local, f"/workdir/{self.jdir}", False), (os.path.join(self.copy, "prefs.json"), "/workdir/.prefs.json", True),
                      (tz, "/worker/hermes-config.yaml", True), (out, "/workdir/.worker-out", False)]
        if self.jdir != "jobfinder":
            env["JOBPUSH_ROOT"] = f"/workdir/{self.jdir}"
        return mounts, env

    def before_run(self):
        self._before = set() if self.lwd else set(self.pipeline_lines())

    def after_run(self, stdout):
        """The night summary and the early-alert lines go to outgoing/ (each run its own file: apply.py merges them in order). Local
        data: jobpush already wrote the summary (merged under its own lock), its state and the pipeline in place; only the early-alert
        lines go through apply.py (known keys, appended)."""
        if self.lwd:
            sig = os.path.join(self.copy, "out", "early-signals.jsonl")
            signals = 0
            if os.path.isfile(sig) and os.path.getsize(sig):
                signals = sum(1 for _ in open(sig))
                os.replace(sig, os.path.join(self.outgoing, f"signals-{stamp()}.jsonl"))
            pending = 1 if os.path.isfile(os.path.join(self.lwd, self.jdir, "data", ".jobpush-pending.json")) else 0
            return {"pipeline_new": 0, "pending": pending, "signals": signals}
        new = [ln for ln in self.pipeline_lines() if ln not in self._before and URL_RE.search(ln)]
        if new:
            rows = []
            try:
                rows = [json.loads(x) for x in open(self.added, encoding="utf-8")]
            except (OSError, ValueError):
                pass
            self._write_added(rows + [{"ts": int(time.time()), "line": ln} for ln in new])
        pending = 0
        src = os.path.join(self.data, ".jobpush-pending.json")
        if os.path.isfile(src):
            os.replace(src, os.path.join(self.outgoing, f"pending-{stamp()}.json"))
            pending = 1
        sig = os.path.join(self.copy, "out", "early-signals.jsonl")
        signals = 0
        if os.path.isfile(sig) and os.path.getsize(sig):
            signals = sum(1 for _ in open(sig))
            os.replace(sig, os.path.join(self.outgoing, f"signals-{stamp()}.jsonl"))
        return {"pipeline_new": len(new), "pending": pending, "signals": signals}

    def apply_args(self):
        return ["--jobfinder-dir", self.jdir]


# ---------------------------------------------------------------- revista
def oncalendar_hm(cal):
    """(hour, minute) of a daily OnCalendar like "*-*-* 07:30:00 Zone", else None."""
    m = re.match(r"^\*-\*-\* (\d{1,2}):(\d{2})(?::\d{2})?(?: \S+)?$", str(cal).strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def cron_hm(expr):
    """(hour, minute) of a daily cron expression like "30 7 * * *", else None."""
    m = re.match(r"^(\d{1,2}) (\d{1,2}) \* \* \*$", str(expr).strip())
    return (int(m.group(2)), int(m.group(1))) if m else None


class RevistaJob(Job):
    """The morning magazine (WORKERS.md "The revista type"), local data only. It reads the person's space read-only (the job's prompt
    in persist/cron/jobs.json, the keys and the bot in persist/.env and auth.json), runs `hub revista` in a one-shot container without
    keys or network, writes the magazine with one model call, sends it through the stack's own bot, and CREATES
    <workdir>/revista/<date>.md (through apply.py, never over an existing file). Nothing else of the person's is written by this code;
    `hub revista` itself updates /workdir/.revista.json and .hub-read.json as it does in the stack."""
    kind = "revista"

    def __init__(self, cfg, stack):
        super().__init__(cfg, stack)
        self.job_name = self.jc.get("job", "revista")
        self.persist = (self.jc.get("local_persist") or os.path.join(os.path.dirname(self.lwd), "persist")).rstrip("/")
        self.hub = self.jc["local_hub"].rstrip("/")

    def apply_args(self):
        return []

    def today(self):
        import datetime
        tz = None
        if self.jc.get("timezone"):
            import zoneinfo
            tz = zoneinfo.ZoneInfo(self.jc["timezone"])
        return datetime.datetime.now(tz).strftime("%Y-%m-%d")

    def small_docker(self, name, mounts, caps, entry, args, stdin=False):
        mem = self.tc["memory"]
        cmd = ["docker", "run", "--rm"] + (["-i"] if stdin else []) + [
            "--name", name, "--restart=no", "--network", "none", "--memory", mem, "--memory-swap", mem, "--cpus", str(self.tc["cpus"]),
            "--pids-limit", str(self.tc["pids"]), "--security-opt", "no-new-privileges", "--cap-drop", "ALL"]
        for c in caps:
            cmd += ["--cap-add", c]
        cmd += ["--label", f"aibridge.worker={self.kind}"]
        for src, dst, ro in mounts:
            cmd += ["-v", f"{src}:{dst}" + (":ro" if ro else "")]
        return cmd + ["--entrypoint", entry, self.cfg["image"], *args]

    def read_space(self, left):
        """The job, the keys and the bot, read-only (revista_job.READER). -> (dict or None, code)."""
        gw, senv = self.jc.get("local_gateways"), self.jc.get("local_stack_env")
        gw = gw if gw and os.path.isfile(gw) else None
        senv = senv if senv and os.path.isfile(senv) else None
        if self.cfg["apply"] == "direct":
            cmd = [sys.executable, "-", self.persist, self.lwd, self.job_name, gw or "-", senv or "-"]
        else:
            mounts = [(self.persist, "/p", True), (self.lwd, "/w", True)]
            mounts += [(gw, "/g/gateways.json", True)] if gw else []
            mounts += [(senv, "/s/env", True)] if senv else []
            name = f"aibridge-worker-revista-read-{self.stack}"
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60)
            cmd = self.small_docker(name, mounts, ("DAC_OVERRIDE",), "python3",
                                    ["-", "/p", "/w", self.job_name, "/g/gateways.json" if gw else "-", "/s/env" if senv else "-"], stdin=True)
        return revista_job.run_reader(cmd, timeout=max(10, min(120, left)))

    def run_hub(self, left):
        """`hub revista` in the stacks' image: no keys, no network, the person's hub folder read-only at /hub and their workdir at
        /workdir (the hub client keeps its window there, .revista.json). -> (result, rc, text)."""
        name = f"aibridge-worker-revista-{self.stack}"
        cmd = self.small_docker(name, [(self.hub, "/hub", True), (self.lwd, "/workdir", False)], APPLY_CAPS, "python3",
                                ["/usr/local/bin/hub", "revista"])
        try:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60)
            r = subprocess.run(cmd, capture_output=True, timeout=max(10, min(300, left)))
        except subprocess.TimeoutExpired:
            try:
                subprocess.run(["docker", "kill", name], capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError):
                pass
            return "hub_timeout", -1, ""
        except (OSError, subprocess.SubprocessError):
            return "hub_docker", -1, ""
        if r.returncode in (125, 126, 127):
            return "hub_docker", r.returncode, ""
        out = r.stdout.decode("utf-8", "replace")
        if r.returncode != 0:   # its own plain messages ("not attached", "no feed yet") go to stderr: the model tells the person
            out = (out + "\n" + r.stderr.decode("utf-8", "replace")).strip()
        if not out.strip():
            return "hub_empty", r.returncode, ""
        return "ok", r.returncode, out[:60000]

    def save(self, day, text):
        """outgoing/revista/<day>.md -> <workdir>/revista/ through apply.py (a new name when that day's file exists)."""
        d = os.path.join(self.outgoing, "revista")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{day}.md"), "w", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
        return self.apply_local(time.time())

    def run(self):
        lk = self.lock()
        if lk is None:
            self.ev("skipped", reason="busy")
            return 0
        with lk:
            t0 = time.time()
            deadline = t0 + self.tc["timeout_s"]
            for path, why in ((self.lwd, "local_missing"), (self.persist, "persist_missing"), (self.hub, "hub_missing")):
                if not os.path.isdir(path):
                    self.ev("failed", reason=why, rc=0)
                    return 1
            day = self.today()
            if self.meta().get("last_sent_day") == day:
                self.ev("skipped", reason="already_sent")
                return 0
            space, code = self.read_space(deadline - time.time())
            if space is None:
                self.ev("failed", reason="read_" + code, rc=0)
                return 1
            job = space.get("job")
            if not job:
                self.ev("skipped", reason="no_job", jobs=int(space.get("jobs") or 0))
                return 0
            if not space.get("moved"):      # the stack still owns it (/workdir/.worker-jobs does not name it): no second magazine
                self.ev("skipped", reason="not_moved")
                return 0
            if not job.get("paused"):      # listed as moved but still on in the stack: its own cron would send one too
                self.ev("skipped", reason="job_active")
                return 0
            if not str(job.get("prompt") or "").strip():
                self.ev("failed", reason="no_prompt", rc=0)
                return 1
            if (space.get("gw") or {}).get("local_only"):
                self.ev("skipped", reason="local_only")   # submarine mode: nothing may go to a cloud model
                return 0
            tg = space.get("tg") or {}
            chats = revista_job.chats_of(tg.get("TELEGRAM_ALLOWED_USERS"))
            base = self.jc.get("bot_api", "")
            if not (tg.get("TELEGRAM_BOT_TOKEN") and base and chats):
                self.ev("failed", reason="no_bot", rc=0, token=bool(tg.get("TELEGRAM_BOT_TOKEN")), bot_api=bool(base), users=len(chats))
                return 1
            keys = space.get("keys") or {}
            if not any(keys.get(c[3]) for c in revista_job.CLOUD):
                self.ev("failed", reason="no_key", rc=0)
                return 1
            want, have = oncalendar_hm(self.tc["schedule"]), cron_hm(job.get("expr"))
            self.ev("started", copy_age_s=0, prompt_chars=len(job["prompt"]), keys=sum(1 for v in keys.values() if v),
                    schedule_differs=bool(want != have or not want))
            result, hub_rc, digest = self.run_hub(deadline - time.time())
            if result != "ok":
                self.ev("failed", reason=result, rc=hub_rc, secs=round(time.time() - t0, 1))
                self.save_meta(last_run={"ts": int(t0), "result": result, "rc": hub_rc, "secs": round(time.time() - t0, 1)})
                return 1
            order = self.jc.get("cloud_order") or (space.get("gw") or {}).get("cloud_order") or []
            text, info = revista_job.call_model(keys, revista_job.SYSTEM.format(job=self.job_name),
                                                revista_job.user_message(job["prompt"], digest, hub_rc), deadline,
                                                per_call_s=self.jc.get("model_timeout_s", 180), cloud_order=order)
            stats = dict(hub_rc=hub_rc, digest_chars=len(digest), tries=info["tries"], model_secs=info["secs"],
                         last_code=(info["codes"] or ["none"])[-1])
            if not text:
                self.ev("failed", reason="model", rc=0, secs=round(time.time() - t0, 1), **stats)
                self.save_meta(last_run={"ts": int(t0), "result": "model", "rc": 0, "secs": round(time.time() - t0, 1)})
                return 1
            sent, sfail, pieces = revista_job.send_telegram(base, tg["TELEGRAM_BOT_TOKEN"], chats, text)
            self.save(day, text)
            secs = round(time.time() - t0, 1)
            stats.update(provider=info["provider"], answer_chars=len(text), pieces=pieces, users=len(chats), sent=sent, send_failed=sfail)
            if sent:
                self.save_meta(last_sent_day=day)
            self.save_meta(last_run={"ts": int(t0), "result": "ok" if sent and not sfail else "send", "rc": 0, "secs": secs})
            if not sent or sfail:
                self.ev("failed", reason="send", rc=0, secs=secs, **stats)
                return 1
            self.ev("done", secs=secs, rc=0, **stats)
            return 0


JOBS = {"subs": SubsJob, "jobnight": JobnightJob, "revista": RevistaJob}


def people_with(cfg, jtype, only=None):
    return [s for s, pc in sorted(cfg["people"].items()) if jtype in pc["jobs"] and (only is None or s == only)]


# ---------------------------------------------------------------- commands
def cmd_run(cfg, jtype, only):
    if jtype not in cfg["types"]:
        print(f"worker: no type {jtype} in the config", file=sys.stderr)
        return 2
    rc = 0
    for s in people_with(cfg, jtype, only):
        rc |= JOBS[jtype](cfg, s).run()
    return rc


def cmd_sync(cfg, only_type):
    rc = 0
    for t in cfg["types"]:
        if only_type and t != only_type:
            continue
        for s in people_with(cfg, t):
            rc |= JOBS[t](cfg, s).sync()
    return rc


def cmd_check(cfg, try_ssh):
    print(f"config ok: {len(cfg['people'])} stack(s), types {', '.join(cfg['types'])}, state in {cfg['state_dir']}")
    for t, tc in cfg["types"].items():
        print(f"  {t}: OnCalendar={tc['schedule']} memory={tc['memory']} cpus={tc['cpus']} pids={tc['pids']} timeout={tc['timeout_s']}s "
              f"people: {', '.join(people_with(cfg, t)) or '-'}")
    if try_ssh and "host" not in cfg:
        print("ssh: not needed (every person has local_workdir)")
    elif try_ssh:
        r = subprocess.run(["ssh", *SSH_OPTS, cfg["host"], "true"], capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            print(f"ssh: ok (BatchMode) to {cfg['host'].split('@')[0]}@<docker host>")
        else:
            print(f"ssh: no answer ({r.returncode}): the Docker host may be asleep (fine: the worker waits) or the key is not "
                  f"in aibridge's authorized_keys. {r.stderr.strip()[-200:]}")
            return 3
    return 0


def cmd_status(cfg):
    for t in cfg["types"]:
        for s in people_with(cfg, t):
            j = JOBS[t](cfg, s)
            m = j.meta()
            lr = m.get("last_run") or {}
            ago = lambda ts: f"{int((time.time() - ts) / 60)} min ago" if ts else "never"
            print(f"{t:9} {s:12} pull {ago(m.get('last_pull'))}; run {ago(lr.get('ts'))} {lr.get('result', '')}; "
                  f"push {ago(m.get('last_push'))}; waiting {j.waiting()}")
    return 0


def main(argv):
    global BUS_ON
    ap = argparse.ArgumentParser(description="Always-on worker: one scheduled job type, away from the sleeping Docker host.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("type", choices=JOB_TYPES); r.add_argument("--stack")
    y = sub.add_parser("sync"); y.add_argument("--type", choices=JOB_TYPES)
    c = sub.add_parser("check"); c.add_argument("--ssh", action="store_true")
    sc = sub.add_parser("schedule"); sc.add_argument("type", choices=JOB_TYPES + ("sync",))
    sub.add_parser("status")
    a = ap.parse_args(argv)
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"worker: {e}", file=sys.stderr)
        return 2
    if a.cmd == "schedule":
        if a.type == "sync":
            print(f"*:0/{cfg['sync_every_min']}")
            return 0
        if a.type not in cfg["types"]:
            return 1
        print(cfg["types"][a.type]["schedule"])
        return 0
    if a.cmd in ("check", "status"):
        return cmd_check(cfg, a.ssh) if a.cmd == "check" else cmd_status(cfg)
    if bus is not None and bus.enabled():
        BUS_ON = True
    os.makedirs(cfg["state_dir"], mode=0o700, exist_ok=True)
    if a.cmd == "run":
        return cmd_run(cfg, a.type, a.stack)
    return cmd_sync(cfg, a.type)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
