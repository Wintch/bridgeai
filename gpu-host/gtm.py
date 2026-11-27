#!/usr/bin/env python3
"""What runs on the GPU, per process, from gputaskman (https://github.com/shanselman/gputaskman, MIT, read-only: NVML per-process VRAM and
engine load). Shared by bench_gate.py (a per-service profile next to each timed job) and gpu_outside.py (GPU use that did not go through
the gate). Stdlib only. The pure parts (fold_record, classify, container_id_of) take their inputs as arguments, so gtm_selftest.py
tests them offline.

gputaskman is installed by hand on the host, never in a container: `python3 -m venv ~/.local/share/gputaskman`, then
`~/.local/share/gputaskman/bin/pip install gputaskman==<pinned>`, then a link at ~/.local/bin/gputaskman (GPU_WATCH.md "gputaskman").
It runs as the host user: NVML gives every process's VRAM and engine load without root. What needs root is the runtime and model-file
detail of other users' processes, and nothing here uses that.
A process is put in a container by /proc/<pid>/cgroup (readable by anyone), and the container id is turned into its name with `docker ps`.
"""
import json, os, re, subprocess

GTM_PATH_ENV = "GPUTASKMAN"
HEX64 = re.compile(r"(?:docker-|/docker/)([0-9a-f]{64})")


def find_tool(environ=None, home=None):
    """The gputaskman binary: $GPUTASKMAN, else ~/.local/bin/gputaskman. None when absent (callers then run without it and say so)."""
    environ = os.environ if environ is None else environ
    p = environ.get(GTM_PATH_ENV) or os.path.join(home or os.path.expanduser("~"), ".local", "bin", "gputaskman")
    return p if os.path.isfile(p) and os.access(p, os.X_OK) else None


def container_id_of(cgroup_text):
    """The docker container id in a /proc/<pid>/cgroup text (cgroup v2 `docker-<id>.scope`, or v1 `/docker/<id>`), else None."""
    m = HEX64.search(cgroup_text or "")
    return m.group(1) if m else None


def read_cgroup(pid, proc="/proc"):
    try:
        with open(os.path.join(proc, str(int(pid)), "cgroup"), encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, ValueError):
        return ""


def docker_names(timeout=20):
    """{full container id: name} of every container (running or not). {} when docker cannot be asked."""
    try:
        r = subprocess.run(["docker", "ps", "-a", "--no-trunc", "--format", "{{.ID}} {{.Names}}"], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return {}
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            out[parts[0]] = parts[1]
    return out


def container_of(pid, names, proc="/proc"):
    """The container name a pid runs in, "" when it runs on the host, "?" when it is in a container docker does not name."""
    cid = container_id_of(read_cgroup(pid, proc))
    if not cid:
        return ""
    return names.get(cid, "?")


def mib(b):
    return int(b) // (1024 * 1024) if isinstance(b, (int, float)) and not isinstance(b, bool) and b > 0 else 0


def procs_of(snapshot):
    """The GPU processes of one gputaskman --json snapshot (or one `record` line): [(pid, exe name, vram MiB, gpu %, {engine: %})].
    Processes with no VRAM and no load are left out."""
    out = []
    for p in (snapshot or {}).get("processes") or []:
        if not isinstance(p, dict) or not isinstance(p.get("pid"), int):
            continue
        v = mib(p.get("vram_bytes"))
        g = p.get("gpu_pct") if isinstance(p.get("gpu_pct"), (int, float)) and not isinstance(p.get("gpu_pct"), bool) else 0
        eng = {k: float(x) for k, x in (p.get("engines") or {}).items() if isinstance(k, str) and isinstance(x, (int, float)) and not isinstance(x, bool)}
        if v or g or any(eng.values()):
            out.append((p["pid"], str(p.get("name") or "?")[:40], v, float(g), eng))
    return out


def fold_record(samples, where):
    """Per process over a recording (a list of snapshots): the peak VRAM, the peak load and the peak of each engine. `where(pid)` gives the
    container name ("" = host). Processes are grouped by (container, exe name); the biggest VRAM first, at most 6."""
    acc = {}
    for s in samples:
        for pid, name, v, g, eng in procs_of(s):
            k = (where(pid), name)
            a = acc.setdefault(k, {"container": k[0], "name": name, "vram_peak_mib": 0, "gpu_peak_pct": 0.0, "engines_peak": {}, "seen": 0})
            a["vram_peak_mib"] = max(a["vram_peak_mib"], v)
            a["gpu_peak_pct"] = max(a["gpu_peak_pct"], g)
            for e, x in eng.items():
                a["engines_peak"][e] = max(a["engines_peak"].get(e, 0.0), x)
            a["seen"] += 1
    rows = sorted(acc.values(), key=lambda a: (-a["vram_peak_mib"], -a["gpu_peak_pct"], a["name"]))
    for a in rows:
        a["gpu_peak_pct"] = round(a["gpu_peak_pct"], 1)
        a["engines_peak"] = {e: round(x, 1) for e, x in sorted(a["engines_peak"].items())}
    return rows[:6]


def read_record(path):
    """The snapshots of a `gputaskman record` file; a broken line (the recorder was stopped mid-write) is skipped."""
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    out.append(d)
    except OSError:
        pass
    return out


# ------------------------------------------------------------------------------------------------ GPU use outside the gate
PLACE_CONTAINER = re.compile(r"^(?:[a-z][a-z0-9]{1,11}doc|place-[a-z][a-z0-9]{1,11}-desktop)$")   # places/place.py container(), lan-discovery.py
KINDS = ("host_process", "unknown_container", "service_not_leased")                           # the only words /state and the alert carry


def classify(procs, state, services, allow_re, allow_max_mib, external_procs=None):
    """Which GPU processes did not go through the gate. procs: [(container, exe, vram MiB)]. state: the gate's GET /state (services with
    running/leases, bench). services: the gate's service names (each is also its container's name). allow_re: small desktop programs on the
    host (Xorg, sunshine, a browser) that may hold up to allow_max_mib. external_procs: {service: compiled regex of the exe} for services that
    are host processes, not containers (resolve). Returns [(kind, container, exe, vram MiB)] for the ones outside, kind from KINDS.
      a container of a gate service              -> fine while the gate shows it running or starting or leased, else service_not_leased
      a place's container (<name>doc)            -> fine (places start and stop through the gate)
      any other container                        -> unknown_container
      a host process during a gate bench         -> fine (the bench owns the whole card)
      a host process of an external service      -> fine while the gate shows that service leased or running
      a small desktop program (allow_re, <= max) -> fine
      any other host process                     -> host_process"""
    svcs = (state or {}).get("services") or {}
    bench = bool((state or {}).get("bench"))
    allow = re.compile(allow_re) if isinstance(allow_re, str) else allow_re
    out = []

    starting = {w.split(":", 1)[1] for w in (state or {}).get("sleep_why") or [] if isinstance(w, str) and w.startswith("starting:")}

    def active(n):
        v = svcs.get(n) or {}
        return bool(v.get("running") or v.get("leases")) or n in starting

    for container, exe, v in procs:
        if container:
            if container in services:
                if not active(container) and not bench:
                    out.append(("service_not_leased", container, exe, v))
            elif container == "?" or not PLACE_CONTAINER.match(container):
                out.append(("unknown_container", container, exe, v))
            continue
        if bench:
            continue
        ext = [n for n, rx in (external_procs or {}).items() if rx.search(exe)]
        if ext and any(active(n) for n in ext):
            continue
        if allow.search(exe) and v <= allow_max_mib:
            continue
        out.append(("host_process", "", exe, v))
    return out
