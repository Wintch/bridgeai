#!/usr/bin/env python3
"""GPU use that did not go through the gate. Every GPU job is supposed to ask the gate first (a lease, the mapped VRAM, the power
profile): a container started by hand, a service left running after a test, or a program on the host that grabs the card breaks the
gate's VRAM accounting and its power and sleep decisions without any error. This looks at what really holds the card.

  gpu_outside.py run      one look: gputaskman --json (per-process VRAM and load, gtm.py), each process put in its container, compared
                          with the gate's GET /state; writes outside.json in the gate's state dir (bridgeai-gpu-outside.timer, every 5 min)
  gpu_outside.py status   what the last look found, with the process and container names (on the host only)

The rules are gtm.classify(). A finding has to be seen in 2 looks in a row before it counts ("pending" before that): a service the gate is
starting or stopping at that very second is not an alarm. The gate shows only fixed words and numbers from outside.json in GET /state
("outside": status, count, MiB, kinds, age) and gpu_watch.py on the Docker host alerts the operator (gpu-outside:HOST). The names of the
processes and containers stay in the file on the host. Reads only: it never stops anything.
Needs gputaskman (gtm.py says how it is installed); without it the status is "no_tool" and nothing is guessed.
"""
import importlib.util, json, os, re, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gtm  # noqa: E402

OUTSIDE_FILE = "outside.json"
ALLOW_RE = r"chrom|sunshine|Xorg|Xwayland|gnome-shell|kwin|plasmashell|firefox|steamwebhelper|xfwm|xfdesktop"   # bench_gate.ALLOWED_APPS + Xfce
ALLOW_MAX_MIB = 400
STREAK_NEEDED = 2


def parse_env_file(path):
    """KEY=VALUE lines, never sourced (the gate's parse)."""
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
        if sep and re.fullmatch(r"[A-Z_][A-Z0-9_]*", k.strip()):
            out[k.strip()] = v.strip().strip("'\"")
    return out


def gate_module():
    spec = importlib.util.spec_from_file_location("bridgeai_gate", os.path.join(HERE, "gate", "gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def state_dir(env):
    return env.get("GATE_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".local", "state", "bridgeai-gate")


def gate_state(env, timeout=8):
    bind = env.get("GATE_BIND") or env.get("GPU_BIND_ADDR") or "127.0.0.1"
    if bind in ("0.0.0.0", "::"):
        bind = "127.0.0.1"
    r = urllib.request.Request(f"http://{bind}:{env.get('GATE_PORT', '8700')}/state", headers={"Authorization": "Bearer " + env["GATE_TOKEN"]})
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return json.load(f)


def look(tool, env, gate):
    """[(kind, container, exe, MiB)] outside the gate right now. Raises on a tool or gate failure."""
    r = subprocess.run([tool, "--json", "--no-system"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gputaskman rc={r.returncode}")
    snap = json.loads(r.stdout)
    st = gate_state(env)
    names = gtm.docker_names()
    procs = [(gtm.container_of(pid, names), exe, v) for pid, exe, v, _g, _e in gtm.procs_of(snap)]
    ext = {n: re.compile(r"^" + re.escape(os.path.basename(x["proc"].pattern.strip("^$").replace("\\", ""))) + r"$")
           for n, x in getattr(gate, "EXTERNAL", {}).items() if hasattr(x.get("proc"), "pattern")}
    return gtm.classify(procs, st, set(gate.SERVICES), ALLOW_RE, ALLOW_MAX_MIB, ext)


def result(found, prev, now):
    """The new outside.json from this look's findings and the previous file. Pure."""
    streak = (int(prev.get("streak") or 0) + 1) if found and isinstance(prev, dict) else (1 if found else 0)
    status = "ok" if not found else ("outside" if streak >= STREAK_NEEDED else "pending")
    kinds = sorted({k for k, _c, _e, _v in found})
    return {"at": int(now), "status": status, "count": len(found), "vram_mib": sum(v for *_x, v in found), "kinds": kinds, "streak": streak,
            "items": [{"kind": k, "container": c, "exe": e, "vram_mib": v} for k, c, e, v in found]}


def write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    t = f"{path}.tmp.{os.getpid()}"
    with open(t, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(t, path)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    env = parse_env_file(os.path.join(HERE, "host.env"))
    env.update({k: v for k, v in os.environ.items() if k.startswith("GATE_") or k == gtm.GTM_PATH_ENV})
    path = os.path.join(state_dir(env), OUTSIDE_FILE)
    if cmd == "status":
        try:
            d = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            print("no look yet (bridgeai-gpu-outside.timer)")
            return 0
        print(f"{d.get('status')} at {time.strftime('%Y-%m-%d %H:%M', time.localtime(d.get('at', 0)))}: {d.get('count', 0)} process(es), "
              f"{d.get('vram_mib', 0)} MiB, seen {d.get('streak', 0)} time(s) in a row")
        for it in d.get("items") or []:
            print(f"  {it.get('kind'):<19} {it.get('container') or '(host)':<20} {it.get('exe'):<24} {it.get('vram_mib')} MiB")
        return 0
    if cmd != "run":
        print(__doc__)
        return 2
    try:
        prev = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    now = time.time()
    tool = gtm.find_tool(env)
    if not tool:
        write_atomic(path, {"at": int(now), "status": "no_tool", "count": 0, "vram_mib": 0, "kinds": [], "streak": 0, "items": []})
        print("gpu_outside: gputaskman is not installed (GPU_WATCH.md)")
        return 78
    if not env.get("GATE_TOKEN"):
        write_atomic(path, {"at": int(now), "status": "error", "count": 0, "vram_mib": 0, "kinds": [], "streak": 0, "items": []})
        print("gpu_outside: no GATE_TOKEN in host.env")
        return 78
    try:
        found = look(tool, env, gate_module())
    except Exception as e:
        write_atomic(path, {"at": int(now), "status": "error", "count": 0, "vram_mib": 0, "kinds": [], "streak": int(prev.get("streak") or 0), "items": []})
        print(f"gpu_outside: could not look ({type(e).__name__})")
        return 2
    d = result(found, prev, now)
    write_atomic(path, d)
    print(f"gpu_outside: {d['status']} ({d['count']} process(es), {d['vram_mib']} MiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
