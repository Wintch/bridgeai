#!/usr/bin/env python3
"""GPU use that did not go through the gate. Every GPU job is supposed to ask the gate first (a lease, the mapped VRAM, the power
profile): a container started by hand, a service left running after a test, or a program on the host that grabs the card breaks the
gate's VRAM accounting and its power and sleep decisions without any error. This looks at what really holds the card.

  gpu_outside.py run      one look: gputaskman --json (per-process VRAM and load, gtm.py), each process put in its container, compared
                          with the gate's GET /state; writes outside.json in the gate's state dir, and pushes the card's use to Zabbix
                          when GPU_ZBX_SERVER and GPU_ZBX_HOST are set (bridgeai-gpu-outside.timer, every minute)
  gpu_outside.py status   what the last look found, with the process and container names (on the host only)

The rules are gtm.classify(). A finding has to be seen in STREAK_NEEDED looks in a row before it counts ("pending" before that): a service the
gate is starting or stopping at that very second is not an alarm. The gate shows only fixed words and numbers from outside.json in GET /state
("outside": status, count, MiB, kinds, age). The names of the processes and containers stay in the file on the host. Reads only: it never
stops anything.
Zabbix (template "GPU host usage", aibridge/ops/ZABBIX.md): the whole card, the outside status (its trigger pages the operator) and the use per
bucket: each gate service, "places", "host", "other" (gtm.buckets). No process, container or person name is sent.
A host with no gate (the operator's PC) sets GPU_NO_GATE=1: no comparison (status "no_gate"), only the Zabbix push.
Needs gputaskman (gtm.py says how it is installed); without it the status is "no_tool" and nothing is guessed.
"""
import importlib.util, json, os, re, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gtm  # noqa: E402

OUTSIDE_FILE = "outside.json"
ALLOW_RE = r"chrom|sunshine|Xorg|Xwayland|gnome-shell|kwin|plasmashell|firefox|steamwebhelper|xfwm|xfdesktop"   # bench_gate.ALLOWED_APPS + Xfce
ALLOW_MAX_MIB = 400
STREAK_NEEDED = 3                       # looks a minute apart


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


def snapshot(tool):
    """One gputaskman --json snapshot and its GPU processes with their container: (snap, [(container, exe, MiB, gpu %, engines)])."""
    r = subprocess.run([tool, "--json", "--no-system"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gputaskman rc={r.returncode}")
    snap = json.loads(r.stdout)
    names = gtm.docker_names()
    return snap, [(gtm.container_of(pid, names), exe, v, g, e) for pid, exe, v, g, e in gtm.procs_of(snap)]


def external_names(gate):
    """{service: regex of its program name} for the gate's host-process services (resolve: ^/opt/resolve/bin/resolve$ -> ^resolve$)."""
    out = {}
    for n, x in getattr(gate, "EXTERNAL", {}).items():
        pat = getattr(x.get("proc"), "pattern", None)
        if pat:
            out[n] = re.compile(r"^" + re.escape(os.path.basename(pat.strip("^$").replace("\\", ""))) + r"$")
    return out


def look(procs, env, gate):
    """[(kind, container, exe, MiB)] outside the gate right now. Raises when the gate does not answer."""
    st = gate_state(env)
    return gtm.classify([(c, e, v) for c, e, v, _g, _x in procs], st, set(gate.SERVICES), ALLOW_RE, ALLOW_MAX_MIB, external_names(gate))


def zbx_send(values, server, port):
    """The gate's own trapper sender (gate/host_control.py, stdlib)."""
    spec = importlib.util.spec_from_file_location("host_control", os.path.join(HERE, "gate", "host_control.py"))
    hc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hc)
    return hc.zbx_send(values, server, port)


def push(env, snap, procs, services, d, send=None):
    """The Zabbix push when GPU_ZBX_SERVER and GPU_ZBX_HOST are set (HOST_ZBX_* as a fallback: the same Zabbix host as the heat).
    Returns (processed, failed), or None when off or refused; never raises (a Zabbix that is down must not stop the look)."""
    server = env.get("GPU_ZBX_SERVER") or env.get("HOST_ZBX_SERVER", "")
    host = env.get("GPU_ZBX_HOST") or env.get("HOST_ZBX_HOST", "")
    if not server or not host:
        return None
    try:
        vals = gtm.zbx_values(host, snap, gtm.buckets(procs, services), d)
        return (send or zbx_send)(vals, server, env.get("GPU_ZBX_PORT") or env.get("HOST_ZBX_PORT") or "10051")
    except (OSError, ValueError):
        return None


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
    env.update({k: v for k, v in os.environ.items() if k.startswith(("GATE_", "GPU_", "HOST_ZBX_")) or k == gtm.GTM_PATH_ENV})
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
    blank = {"at": int(now), "count": 0, "vram_mib": 0, "kinds": [], "streak": 0, "items": []}
    if not tool:
        write_atomic(path, dict(blank, status="no_tool"))
        print("gpu_outside: gputaskman is not installed (GPU_WATCH.md)")
        return 78
    no_gate = env.get("GPU_NO_GATE") == "1"
    if not no_gate and not env.get("GATE_TOKEN"):
        write_atomic(path, dict(blank, status="error"))
        print("gpu_outside: no GATE_TOKEN in host.env (a host with no gate sets GPU_NO_GATE=1)")
        return 78
    try:
        snap, procs = snapshot(tool)
    except Exception as e:
        write_atomic(path, dict(blank, status="error", streak=int(prev.get("streak") or 0)))
        print(f"gpu_outside: gputaskman failed ({type(e).__name__})")
        return 2
    services = set()
    if no_gate:
        d = dict(blank, status="no_gate")
    else:
        try:
            gate = gate_module()
            services = set(gate.SERVICES)
            d = result(look(procs, env, gate), prev, now)
        except Exception as e:
            d = dict(blank, status="error", streak=int(prev.get("streak") or 0))
            print(f"gpu_outside: could not ask the gate ({type(e).__name__})")
    write_atomic(path, d)
    z = push(env, snap, procs, services, d)
    print(f"gpu_outside: {d['status']} ({d['count']} process(es), {d['vram_mib']} MiB)" + (f"; zabbix {z[0]} sent, {z[1]} refused" if z else ""))
    return 0 if d["status"] != "error" else 2

if __name__ == "__main__":
    sys.exit(main(sys.argv))
