#!/usr/bin/env python3
"""hostcare: one machine's caretaker tools for the ops Hermes, as an MCP server on stdio (stdlib only, no LLM, no daemon).

sshd starts it as the forced command of a dedicated key (see HOSTCARE.md): the ops Hermes lists it under `mcp_servers` with
`command: ssh`, exactly like the Resolve MCP and claude-gate. One process per connection; nothing runs between calls.

  hostcare_mcp.py [--config FILE] [--mode care|exec]

  care (default)  level 0, read (readOnlyHint): overview, containers, units, logs of allowlisted targets.
                  level 1, known fixes from the config allowlists: restart_unit, restart_container, prune_build_cache.
                  Its mcp_servers entry is `trust: full`: Hermes runs these without asking.
  exec            level 2, one tool: run(command, reason). Any shell command as this user. Its mcp_servers entry is
                  `trust: untrusted`, so Hermes asks the operator first (Telegram buttons). The NEVER list below is still
                  refused here, whatever was approved: secrets, keys and access, firewall, deleting data, power.

Config (JSON, default ~/aibridge/ops/hostcare/hostcare.json, example in hostcare.example.json): "host", "watch_units",
"restart_units", "restart_containers", "log_units", "log_containers", "never" (extra regexes). Allowlists are exact names.
Person stacks' brains are never in log_*: their logs can carry what people wrote.
Every fix and every run is appended to ~/.local/state/hostcare.log (time, mode, tool, target or command, exit code).
Output is plain text, control characters removed, capped; nothing from a tool is ever executed.
"""
import json, os, re, subprocess, sys, time

PROTOCOL = "2025-06-18"
MAX_OUT = 12_000
STATE = os.path.expanduser(os.environ.get("HOSTCARE_STATE", "~/.local/state"))
AUDIT = os.path.join(STATE, "hostcare.log")
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9@._:-]{0,99}")
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# Refused in exec mode whatever the operator approved (2026-10-21 design: "never" level). Matched on the whole command.
NEVER = [
    r"\.env\b", r"auth\.json", r"ops\.env", r"credentials", r"id_(rsa|ed25519|ecdsa)", r"\.ssh/", r"authorized_keys",
    r"\bsudoers\b", r"\bvisudo\b", r"\bpasswd\b", r"\busermod\b", r"\bchpasswd\b",
    r"\biptables\b", r"\bnft\b", r"\bufw\b", r"aibridge-fw", r"docker-user-fw",
    r"\brm\s+(-[a-zA-Z]*[rf]|--recursive|--force)", r"\bshred\b", r"\bmkfs", r"\bdd\b.*\bof=", r"\btruncate\b",
    r"docker\s+(volume\s+rm|system\s+prune|rm\b|rmi\b|compose\s+down)", r"\bpodman\s+rm",
    r"\b(shutdown|reboot|poweroff|halt)\b", r"systemctl\s+(--user\s+)?(stop|disable|mask|poweroff|reboot)",
    r"\bcrontab\s+-r", r">\s*/(etc|boot|usr)/", r"\bchmod\s+[0-7]*7[0-7]*\s+/", r"\bcurl\b.*\s(-d|--data|-F|--upload-file|-T)\b",
]


def load_config(path):
    try:
        cfg = json.load(open(path))
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"hostcare: cannot read config {path}: {exc}\n")
        cfg = {}
    for k in ("watch_units", "restart_units", "restart_containers", "log_units", "log_containers", "never"):
        cfg[k] = [x for x in cfg.get(k, []) if isinstance(x, str)]
    cfg.setdefault("host", os.uname().nodename)
    return cfg


def clean(text, cap=MAX_OUT):
    text = CTRL.sub("", text or "")
    return text if len(text) <= cap else text[:cap] + f"\n… (cut, {len(text)} chars)"


def sh(args, timeout=60):
    """Run argv (never a shell string); returns (rc, combined output)."""
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")   # systemctl --user over a forced-command ssh session
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout + (("\n" + p.stderr) if p.stderr.strip() else "")).strip()
    except FileNotFoundError:
        return 127, f"{args[0]}: not installed"
    except subprocess.TimeoutExpired:
        return 124, f"{args[0]}: timed out after {timeout}s"


def audit(mode, tool, what, rc):
    try:
        os.makedirs(STATE, exist_ok=True)
        with open(AUDIT, "a") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "mode": mode, "tool": tool,
                                "what": what[:300], "rc": rc}) + "\n")
    except OSError:
        pass


# ---- level 0: read ----
def t_overview(cfg, _):
    out = [f"host: {cfg['host']}"]
    try:
        up = float(open("/proc/uptime").read().split()[0])
        load = open("/proc/loadavg").read().split()[:3]
        out.append(f"uptime: {up / 86400:.1f} days, load: {' '.join(load)}, cpus: {os.cpu_count()}")
        mem = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo") if l.split(":")[0] in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")}
        out.append(f"memory: {mem.get('MemAvailable', 0) // 1024} MB free of {mem.get('MemTotal', 0) // 1024} MB, "
                   f"swap used {(mem.get('SwapTotal', 0) - mem.get('SwapFree', 0)) // 1024} MB")
    except (OSError, ValueError, IndexError):
        out.append("uptime/memory: unreadable")
    rc, df = sh(["df", "-P", "-x", "tmpfs", "-x", "devtmpfs", "-x", "overlay", "-x", "squashfs"])
    if rc == 0:
        for line in df.splitlines()[1:]:
            f = line.split()
            if len(f) >= 6:
                out.append(f"disk {f[5]}: {f[4]} used, {int(f[3]) // 1048576} GB free")
    rc, ps = sh(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Status}}"])
    if rc == 0:
        rows = [l.split("\t") for l in ps.splitlines() if l.count("\t") == 2]
        running = sum(1 for r in rows if r[1] == "running")
        bad = [f"{r[0]} ({r[2]})" for r in rows if "unhealthy" in r[2] or r[1] == "restarting" or (r[1] == "exited" and not r[2].startswith("Exited (0)") and not r[2].startswith("Exited (143)"))]
        out.append(f"containers: {running} running of {len(rows)}" + (f"; attention: {', '.join(bad)}" if bad else ""))
    else:
        out.append(f"containers: UNREADABLE ({ps.splitlines()[0] if ps else 'docker unavailable'})")
    rc, df2 = sh(["docker", "system", "df", "--format", "{{.Type}}: {{.Size}} ({{.Reclaimable}} reclaimable)"])
    if rc == 0 and df2:
        out.append("docker space: " + "; ".join(df2.splitlines()))
    for scope, args in (("user", ["systemctl", "--user"]), ("system", ["systemctl"])):
        rc, failed = sh(args + ["list-units", "--failed", "--no-legend", "--plain", "--no-pager"])
        if rc != 0:   # never "none" when it could not be read (a small model reports that as "no problems")
            out.append(f"failed {scope} units: UNREADABLE ({failed.splitlines()[0] if failed else f'rc {rc}'})")
            continue
        names = [l.split()[0] for l in failed.splitlines() if l.strip() and not l.startswith("0 ")]
        out.append(f"failed {scope} units: {', '.join(names) if names else 'none'}")
    for u in cfg["watch_units"]:
        rc, st = sh(["systemctl", "--user", "is-active", u])
        out.append(f"unit {u}: {st.splitlines()[0] if st else 'unknown'}")
    rc, gpu = sh(["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
                  "--format=csv,noheader"], timeout=20)
    if rc == 0 and gpu:
        out += [f"gpu: {g}" for g in gpu.splitlines()]
    return "\n".join(out)


def t_containers(cfg, _):
    rc, ps = sh(["docker", "ps", "-a", "--format", "{{.Names}}  {{.State}}  {{.Status}}  {{.Image}}"])
    return ps if rc == 0 else f"ERROR: {ps}"


def t_units(cfg, _):
    rc, lu = sh(["systemctl", "--user", "list-units", "--type=service,timer", "--all", "--no-legend", "--plain", "--no-pager"])
    return lu if rc == 0 else f"ERROR: {lu}"


def t_logs(cfg, a):
    target, lines = str(a.get("target", "")), max(1, min(int(a.get("lines", 80) or 80), 300))
    if target in cfg["log_containers"]:
        rc, out = sh(["docker", "logs", "--tail", str(lines), target])
    elif target in cfg["log_units"]:
        rc, out = sh(["journalctl", "--user", "-u", target, "-n", str(lines), "--no-pager", "-o", "short-iso"])
    else:
        return (f"ERROR: '{target}' is not readable here. Readable: "
                f"{', '.join(cfg['log_containers'] + cfg['log_units']) or 'nothing configured'}")
    return out if rc == 0 else f"ERROR (rc {rc}): {out}"


# ---- level 1: known fixes ----
def t_restart_unit(cfg, a):
    name = str(a.get("name", ""))
    if name not in cfg["restart_units"]:
        return f"ERROR: '{name}' is not in restart_units: {', '.join(cfg['restart_units']) or 'none'}. Use the exec server and ask."
    rc, out = sh(["systemctl", "--user", "restart", name], timeout=90)
    audit("care", "restart_unit", name, rc)
    _, st = sh(["systemctl", "--user", "is-active", name])
    return f"{'' if rc == 0 else 'ERROR: '}restart {name}: rc {rc}{(' ' + out) if out else ''}; now {st or 'unknown'}"


def t_restart_container(cfg, a):
    name = str(a.get("name", ""))
    if name not in cfg["restart_containers"]:
        return f"ERROR: '{name}' is not in restart_containers: {', '.join(cfg['restart_containers']) or 'none'}. Use the exec server and ask."
    rc, out = sh(["docker", "restart", "-t", "30", name], timeout=120)
    audit("care", "restart_container", name, rc)
    _, st = sh(["docker", "inspect", "-f", "{{.State.Status}} {{.State.Health}}", name])
    return f"{'' if rc == 0 else 'ERROR: '}restart {name}: rc {rc}{(' ' + out[-300:]) if rc and out else ''}; now {st or 'unknown'}"


def t_prune_build_cache(cfg, _):
    rc, out = sh(["docker", "builder", "prune", "-f", "--filter", "until=72h"], timeout=600)
    audit("care", "prune_build_cache", "until=72h", rc)
    last = [l for l in out.splitlines() if "reclaimed" in l.lower()]
    return f"{'' if rc == 0 else 'ERROR: '}build cache older than 72 h pruned: rc {rc}; {last[-1] if last else out[-300:]}"


# ---- level 2: anything else, after the operator's OK ----
def t_run(cfg, a):
    cmd, reason = str(a.get("command", "")).strip(), str(a.get("reason", "")).strip()
    timeout = max(5, min(int(a.get("timeout", 120) or 120), 300))
    if not cmd or not reason:
        return "ERROR: both command and reason are required."
    for pat in NEVER + cfg["never"]:
        if re.search(pat, cmd, re.I):
            audit("exec", "run-refused", cmd, -1)
            return (f"REFUSED on this host (never list, pattern {pat!r}): even with approval, secrets, keys, access, firewall, "
                    "deleting data and power stay with the operator. Tell the operator the exact command and why.")
    try:
        p = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")})
        rc, out = p.returncode, (p.stdout + ("\n" + p.stderr if p.stderr.strip() else "")).strip()
    except subprocess.TimeoutExpired:
        rc, out = 124, f"timed out after {timeout}s"
    audit("exec", "run", cmd, rc)
    return f"rc {rc}\n{out}"


S = {"type": "object", "properties": {}, "additionalProperties": False}
TOOLS = {
    "care": [
        ("overview", "Health of this machine in one call: uptime, load, memory, disks, containers needing attention, docker "
                     "space, failed systemd units, watched units, GPU. Start here.", S, t_overview, True),
        ("containers", "Every docker container with state, status and image.", S, t_containers, True),
        ("units", "Every systemd user service and timer of this account with its state.", S, t_units, True),
        ("logs", "Last lines of an allowlisted container or user unit (target = exact name; lines 1-300, default 80).",
         {"type": "object", "properties": {"target": {"type": "string"}, "lines": {"type": "integer"}},
          "required": ["target"], "additionalProperties": False}, t_logs, True),
        ("restart_unit", "Known fix: restart a systemd user unit from restart_units. Others are refused.",
         {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
         t_restart_unit, False),
        ("restart_container", "Known fix: restart a container from restart_containers. Others are refused.",
         {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
         t_restart_container, False),
        ("prune_build_cache", "Known fix: delete docker build cache older than 72 h (images and volumes untouched).",
         S, t_prune_build_cache, False),
    ],
    "exec": [
        ("run", "Run one shell command on this machine as its account, after the operator approved it. Give the exact command "
                "and a one-line reason. Secrets, keys, access, firewall, deleting data and power are refused here anyway.",
         {"type": "object", "properties": {"command": {"type": "string"}, "reason": {"type": "string"},
                                           "timeout": {"type": "integer"}},
          "required": ["command", "reason"], "additionalProperties": False}, t_run, False),
    ],
}


def handle(msg, cfg, mode):
    mid, method = msg.get("id"), msg.get("method")
    if method == "initialize":
        return {"protocolVersion": (msg.get("params") or {}).get("protocolVersion") or PROTOCOL,
                "capabilities": {"tools": {}}, "serverInfo": {"name": f"hostcare-{cfg['host']}-{mode}", "version": "1"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": s,
                           "annotations": {"readOnlyHint": ro, "destructiveHint": (mode == "exec"), "openWorldHint": False}}
                          for n, d, s, _, ro in TOOLS[mode]]}
    if method == "tools/call":
        p = msg.get("params") or {}
        fn = next((f for n, _, _, f, _ in TOOLS[mode] if n == p.get("name")), None)
        if fn is None:
            raise LookupError(f"unknown tool {p.get('name')!r}")
        try:
            text, err = fn(cfg, p.get("arguments") or {}), False
        except Exception as exc:  # a tool bug must come back as an error result, never kill the session
            text, err = f"ERROR: {type(exc).__name__}: {exc}", True
        return {"content": [{"type": "text", "text": clean(text)}], "isError": err or text.startswith(("ERROR", "REFUSED"))}
    raise LookupError(f"method not found: {method}")


def main(argv):
    cfg_path, mode = os.path.expanduser("~/aibridge/ops/hostcare/hostcare.json"), "care"
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--config" and args:
            cfg_path = os.path.expanduser(args.pop(0))
        elif a == "--mode" and args and args[0] in TOOLS:
            mode = args.pop(0)
        else:
            sys.stderr.write(__doc__)
            return 2
    # A forced command gets the client's requested command in SSH_ORIGINAL_COMMAND: it is ignored on purpose.
    cfg = load_config(cfg_path)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            if not isinstance(msg, dict) or "id" not in msg:
                continue   # notifications (initialized, cancelled): nothing to answer
            try:
                reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg, cfg, mode)}
            except LookupError as exc:
                reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": str(exc)}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
