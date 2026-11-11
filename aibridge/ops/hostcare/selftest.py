#!/usr/bin/env python3
"""Offline test of hostcare_mcp.py: speaks MCP to it on stdio with fake docker/systemctl/journalctl/nvidia-smi on PATH
(nothing real is read or restarted). Exit code 0 = all checks passed.  python3 ops/hostcare/selftest.py
"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "hostcare_mcp.py")
FAKES = {
    "docker": """case "$1" in
  fail) exit 1;;
  ps) printf 'aibridge-web\\trunning\\tUp 2 days\\nstack-x-hermes\\texited\\tExited (0) 3 hours ago\\nbroken\\texited\\tExited (1) 5 min ago\\nsick\\trunning\\tUp 1 h (unhealthy)\\n';;
  system) echo 'Images: 17GB (4GB reclaimable)';;
  logs) echo "log line of $4";;
  restart|builder|inspect) echo "$*" >> "$CALLS"; [ "$1" = builder ] && echo 'Total reclaimed space: 1.2GB'; [ "$1" = inspect ] && echo 'running <nil>'; exit 0;;
esac""",
    "systemctl": """echo "$*" >> "$CALLS"
case "$*" in *--failed*) [ "$1" = --user ] && echo 'telemetry.service loaded failed failed x' ;; *is-active*) echo active;; esac""",
    "journalctl": 'echo "journal of $3"',
    "nvidia-smi": "echo 'GeForce GTX 1070 Ti, 45, 3 %, 900 MiB, 8192 MiB, 30.1 W'",
}


def main():
    tmp = tempfile.mkdtemp()
    bindir = os.path.join(tmp, "bin"); os.makedirs(bindir)
    for name, body in FAKES.items():
        p = os.path.join(bindir, name)
        open(p, "w").write("#!/bin/sh\n" + body + "\n"); os.chmod(p, 0o755)
    cfg = os.path.join(tmp, "hostcare.json")
    json.dump({"host": "testhost", "watch_units": ["zabbix-hook.service"], "restart_units": ["zabbix-hook.service"],
               "restart_containers": ["aibridge-web"], "log_units": ["zabbix-hook.service"], "log_containers": ["aibridge-web"],
               "never": [r"forbidden-extra"]}, open(cfg, "w"))
    env = {**os.environ, "PATH": bindir + ":" + os.environ["PATH"], "CALLS": os.path.join(tmp, "calls"),
           "HOSTCARE_STATE": os.path.join(tmp, "state")}
    ok = True

    def session(mode, msgs):
        lines = "\n".join(m if isinstance(m, str) else json.dumps(m) for m in msgs) + "\n"
        p = subprocess.run([sys.executable, SERVER, "--config", cfg, "--mode", mode], input=lines, capture_output=True,
                           text=True, env=env, timeout=60)
        return [json.loads(l) for l in p.stdout.splitlines() if l.strip()], p.returncode

    def call(i, name, args=None):
        return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}

    def check(name, cond, info=""):
        nonlocal ok
        ok &= bool(cond)
        print(("ok   " if cond else "FAIL ") + name + (f"  [{info}]" if info and not cond else ""))

    def text(r):
        return r["result"]["content"][0]["text"]

    init = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}}}
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    care, rc = session("care", [init, notif, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                call(2, "overview"), call(3, "logs", {"target": "aibridge-web"}),
                                call(4, "logs", {"target": "stack-x-hermes"}), call(5, "restart_unit", {"name": "zabbix-hook.service"}),
                                call(6, "restart_unit", {"name": "aibridge-waker.service"}), call(7, "restart_container", {"name": "aibridge-web"}),
                                call(8, "prune_build_cache"), call(9, "run", {"command": "id", "reason": "x"}),
                                "not json", {"jsonrpc": "2.0", "id": 10, "method": "nope"}, {"jsonrpc": "2.0", "id": 11, "method": "ping"}])
    by = {r.get("id"): r for r in care}
    check("care: exits cleanly at end of input", rc == 0, rc)
    check("care: initialize echoes the client's protocol version", by[0]["result"]["protocolVersion"] == "2025-03-26")
    check("care: notification gets no reply", len([r for r in care if r.get("id") is None]) == 1)  # only the parse error
    tools = {t["name"]: t for t in by[1]["result"]["tools"]}
    check("care: 7 tools, no run", len(tools) == 7 and "run" not in tools, sorted(tools))
    check("care: read tools say readOnlyHint, fixes do not",
          all(tools[n]["annotations"]["readOnlyHint"] for n in ("overview", "containers", "units", "logs"))
          and not any(tools[n]["annotations"]["readOnlyHint"] for n in ("restart_unit", "restart_container", "prune_build_cache")))
    ov = text(by[2])
    check("overview: memory, containers, attention list", "memory:" in ov and "containers: 2 running of 4" in ov
          and "broken (Exited (1)" in ov and "sick (Up 1 h (unhealthy))" in ov and "stack-x-hermes" not in ov.split("attention:")[-1], ov)
    check("overview: failed user unit, watched unit, gpu", "failed user units: telemetry.service" in ov
          and "unit zabbix-hook.service: active" in ov and "gpu: GeForce" in ov, ov)
    check("logs: allowlisted container is read", text(by[3]) == "log line of aibridge-web")
    check("logs: a person's brain is refused", text(by[4]).startswith("ERROR") and by[4]["result"]["isError"])
    check("restart_unit: allowlisted unit restarted", "rc 0" in text(by[5]) and "now active" in text(by[5]))
    check("restart_unit: other unit refused, points to exec", text(by[6]).startswith("ERROR") and "exec" in text(by[6]))
    check("restart_container + prune ran", "rc 0" in text(by[7]) and "reclaimed" in text(by[8]).lower())
    check("care: run is not available", "error" in by[9] and by[9]["error"]["code"] == -32601)
    check("bad JSON line -> parse error, session goes on", any(r.get("error", {}).get("code") == -32700 for r in care) and 11 in by)
    check("unknown method -> -32601", by[10]["error"]["code"] == -32601)
    calls = open(env["CALLS"]).read()
    check("only allowlisted targets reached docker/systemctl", "restart zabbix-hook.service" in calls
          and "aibridge-waker.service" not in calls.replace("is-active", "") and "restart -t 30 aibridge-web" in calls, calls)

    ex, _ = session("exec", [init, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                             call(2, "run", {"command": "echo hello from $USER", "reason": "test"}),
                             call(3, "run", {"command": "cat ~/aibridge/.env", "reason": "x"}),
                             call(4, "run", {"command": "rm -rf /tmp/whatever", "reason": "x"}),
                             call(5, "run", {"command": "sudo iptables -L", "reason": "x"}),
                             call(6, "run", {"command": "echo forbidden-extra", "reason": "x"}),
                             call(7, "run", {"command": "echo no reason"}),
                             call(8, "run", {"command": "python3 -c 'print(\"x\"*50000)'", "reason": "cap"}),
                             call(9, "run", {"command": "sleep 10", "reason": "t", "timeout": 5}),
                             call(10, "overview")])
    by = {r.get("id"): r for r in ex}
    tools = by[1]["result"]["tools"]
    check("exec: only run, destructive, not read-only", [t["name"] for t in tools] == ["run"]
          and tools[0]["annotations"]["destructiveHint"] and not tools[0]["annotations"]["readOnlyHint"])
    check("exec: a plain command runs", text(by[2]).startswith("rc 0") and "hello from" in text(by[2]))
    for i, what in ((3, ".env"), (4, "rm -rf"), (5, "iptables"), (6, "config never list")):
        check(f"exec: never list refuses {what}", text(by[i]).startswith("REFUSED") and by[i]["result"]["isError"])
    check("exec: reason is required", text(by[7]).startswith("ERROR"))
    check("exec: output capped", len(text(by[8])) < 13_000 and "cut," in text(by[8]))
    check("exec: timeout enforced", text(by[9]).startswith("rc 124"))
    check("exec: care tools not available", by[10]["error"]["code"] == -32601)
    log = [json.loads(l) for l in open(os.path.join(env["HOSTCARE_STATE"], "hostcare.log"))]
    check("audit: fixes, runs and refusals logged, no output stored",
          {"restart_unit", "restart_container", "prune_build_cache", "run", "run-refused"} <= {e["tool"] for e in log}
          and all(set(e) == {"t", "mode", "tool", "what", "rc"} for e in log))
    broken = os.path.join(tmp, "broken"); os.makedirs(broken)
    for name, msg in (("docker", "Cannot connect to the Docker daemon"), ("systemctl", "Failed to connect to bus")):
        p = os.path.join(broken, name); open(p, "w").write(f"#!/bin/sh\necho '{msg}' >&2\nexit 1\n"); os.chmod(p, 0o755)
    nodock = {**env, "PATH": broken + ":" + bindir + ":" + os.environ["PATH"]}
    p = subprocess.run([sys.executable, SERVER, "--config", cfg], input=json.dumps(call(1, "overview")) + "\n",
                       capture_output=True, text=True, env=nodock, timeout=60)
    ov = json.loads(p.stdout)["result"]["content"][0]["text"]
    check("overview without docker/systemctl says UNREADABLE, never none", "containers: UNREADABLE" in ov
          and "failed user units: UNREADABLE" in ov and "units: none" not in ov, ov)
    print("ALL OK" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
