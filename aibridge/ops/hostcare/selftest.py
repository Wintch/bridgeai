#!/usr/bin/env python3
"""Offline test of hostcare_mcp.py: speaks MCP to it on stdio with fake docker/systemctl/journalctl/nvidia-smi on PATH
(nothing real is read or restarted). Exit code 0 = all checks passed.  python3 ops/hostcare/selftest.py
"""
import json, os, subprocess, sys, tempfile
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))

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

    # ---- audit mode (sysadmin pack): the helper's JSON through `sudo -n`, falling back to running it unprivileged
    helper = os.path.join(tmp, "audit_root.py")
    open(helper, "w").write("#!/bin/sh\n[ $# -eq 0 ] || exit 2\necho '{\"version\":1,\"host\":\"h\",\"root\":false,\"time\":\"t\",\"findings\":["
                            "{\"check\":\"ssh\",\"rule\":\"SEC-POL-1\",\"status\":\"fail\",\"evidence\":\"PermitRootLogin yes\"},"
                            "{\"check\":\"os\",\"rule\":\"SEC-PATCH-21\",\"status\":\"ok\",\"evidence\":\"Debian 13\"}]}'\n")
    os.chmod(helper, 0o755)
    nosudo = os.path.join(bindir, "sudo")
    open(nosudo, "w").write("#!/bin/sh\necho \"$*\" >> \"$CALLS\"\necho 'sudo: a password is required' >&2\nexit 1\n"); os.chmod(nosudo, 0o755)
    acfg = os.path.join(tmp, "audit.json")
    json.dump({"host": "testhost", "audit_helper": helper}, open(acfg, "w"))
    p = subprocess.run([sys.executable, SERVER, "--config", acfg, "--mode", "audit"], text=True, env=env, timeout=60, capture_output=True,
                       input="\n".join(json.dumps(m) for m in [init, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, call(2, "audit"),
                                                                 call(3, "audit", {"check": "ssh"}), call(4, "audit", {"check": "nope"}),
                                                                 call(5, "audit", {"check": "ssh; rm -rf /"}), call(6, "run", {"command": "id", "reason": "x"}),
                                                                 call(7, "restart_unit", {"name": "x"})]) + "\n")
    by = {r["id"]: r for r in (json.loads(l) for l in p.stdout.splitlines() if l.strip())}
    names = [t["name"] for t in by[1]["result"]["tools"]]
    check("audit mode: only overview and audit, both read-only", names == ["overview", "audit"]
          and all(t["annotations"]["readOnlyHint"] for t in by[1]["result"]["tools"]), names)
    full = json.loads(text(by[2]))
    check("audit mode: the helper's JSON comes back whole", len(full["findings"]) == 2 and not by[2]["result"]["isError"])
    check("audit mode: it tried sudo -n with the helper and no arguments first", f"-n {helper}\n" in open(env["CALLS"]).read())
    check("audit mode: one check filters the findings", [f["check"] for f in json.loads(text(by[3]))["findings"]] == ["ssh"])
    check("audit mode: an unknown check is an error", by[4]["result"]["isError"] and "no check" in text(by[4]))
    check("audit mode: a check that is not one word is refused", by[5]["result"]["isError"])
    check("audit mode: no run, no fixes", by[6]["error"]["code"] == -32601 and by[7]["error"]["code"] == -32601)
    json.dump({"host": "testhost", "audit_helper": os.path.join(tmp, "missing.py")}, open(acfg, "w"))
    p = subprocess.run([sys.executable, SERVER, "--config", acfg, "--mode", "audit"], text=True, env=env, timeout=60, capture_output=True,
                       input=json.dumps(call(1, "audit")) + "\n")
    r = json.loads(p.stdout)["result"]
    check("audit mode: a missing helper is an error that says so, never empty findings", r["isError"] and "did not answer" in r["content"][0]["text"])
    root_py = os.path.join(HERE, "audit_root.py")
    p = subprocess.run([sys.executable, "-I", root_py, "unexpected"], capture_output=True, text=True, timeout=30)
    check("audit_root.py: refuses any argument", p.returncode == 2)

    # ---- audit_root.py parsers, on canned text (nothing of this machine is read)
    import datetime, importlib.util
    spec = importlib.util.spec_from_file_location("audit_root", root_py)
    ar = importlib.util.module_from_spec(spec); spec.loader.exec_module(ar)
    day = datetime.date(2026, 11, 9)
    check("os: Debian 11 past its LTS end is a fail", ar.os_support("debian", "11", day)[0] == "fail")
    check("os: Ubuntu 22.04 inside 180 days of its end is a warn", ar.os_support("ubuntu", "22.04", day)[0] == "warn")
    check("os: Debian 13 is ok; an unknown release is unknown", ar.os_support("debian", "13", day)[0] == "ok" and ar.os_support("arch", "", day)[0] == "unknown")
    check("os: os-release parsed with quotes", ar.parse_os_release('ID=ubuntu\nVERSION_ID="22.04"\n# c\n') == {"ID": "ubuntu", "VERSION_ID": "22.04"})
    sim = ("Inst libssl3 [3.0.2-0ubuntu1.15] (3.0.2-0ubuntu1.18 Ubuntu:22.04/jammy-security [amd64])\n"
           "Inst tzdata (2024a-0ubuntu0.22.04.1 Ubuntu:22.04/jammy-updates [all])\nConf libssl3 (3.0.2 x)\n")
    check("updates: apt simulation split into all and security", ar.parse_apt_sim(sim) == (["libssl3", "tzdata"], ["libssl3"]))
    def st(fs, rule=None):
        return [f["status"] for f in fs if rule is None or f["rule"] == rule]
    good = ar.parse_sshd_T("permitrootlogin no\npasswordauthentication no\npubkeyauthentication yes\nport 22\nmaxauthtries 3\n")
    check("ssh: a clean sshd -T is all ok", set(st(ar.ssh_findings(good))) == {"ok"})
    check("ssh: PermitRootLogin yes is a fail", st(ar.ssh_findings(ar.parse_sshd_T("permitrootlogin yes")), "SEC-POL-1") == ["fail"])
    check("ssh: root by key is a warn", st(ar.ssh_findings(ar.parse_sshd_T("permitrootlogin prohibit-password")), "SEC-POL-1") == ["warn"])
    check("ssh: passwords for everyone is a warn", st(ar.ssh_findings(ar.parse_sshd_T("passwordauthentication yes")), "SEC-POL-2") == ["warn"])
    pw = "root:x:0:0::/root:/bin/bash\ntoor:x:0:0::/root:/bin/sh\nana:x:1000:1000::/home/ana:/bin/bash\nbob:x:1001:1001::/home/bob:/bin/bash\nwww-data:x:33:33::/var/www:/usr/sbin/nologin\n"
    sh_ = "root:*:1::::::\ntoor:!:1::::::\nana:$y$j9T$abc:1:0:99999:7:::\nbob::1:0:99999:7:::\n"
    acc = ar.account_findings(pw, sh_, "sudo:x:27:ana\n")
    check("accounts: a second uid 0 and an empty password are fails", sum(1 for f in acc if f["status"] == "fail") == 2)
    check("accounts: a password with no expiry is a warn, names only", any(f["status"] == "warn" and "ana" in f["evidence"] for f in acc)
          and not any("$y$" in f["evidence"] for f in acc))
    check("accounts: without /etc/shadow it is unknown, not ok", st(ar.account_findings(pw, None, "")) == ["fail", "unknown"])
    su = ar.parse_sudoers(["root ALL=(ALL:ALL) ALL\n%sudo ALL=(ALL:ALL) ALL\n#includedir /etc/sudoers.d\nDefaults env_reset\n",
                           "ubuntu ALL=(ALL) NOPASSWD:ALL # cloud-init\nhostcare ALL=(root) NOPASSWD: /usr/local/lib/hostcare/audit_root.py \"\"\n"])
    check("sudoers: users and groups with their kind, comments and Defaults skipped", su == {"root": "password", "%sudo": "password",
          "ubuntu": "NOPASSWD", "hostcare": "NOPASSWD"}, su)
    ev = ar.account_findings(pw, sh_, "", su)[-1]["evidence"]
    check("accounts: sudo rules listed, root and hostcare left out", "%sudo, ubuntu without password" in ev and "hostcare: only this audit" in ev, ev)
    ss = ('tcp LISTEN 0 4096 0.0.0.0:5432 0.0.0.0:* users:(("postgres",pid=9,fd=5))\n'
          'tcp LISTEN 0 4096 127.0.0.1:6379 0.0.0.0:* users:(("redis-server",pid=8,fd=6))\n'
          'tcp LISTEN 0 128 [::]:22 [::]:* users:(("sshd",pid=7,fd=4))\nudp UNCONN 0 0 0.0.0.0:41234 0.0.0.0:*\n')
    lf = ar.listening_findings(ar.parse_ss(ss), True)
    check("listening: Postgres on every interface is a fail; Redis on localhost is not", lf[0]["status"] == "fail" and "PostgreSQL" in lf[0]["evidence"] and "Redis" not in lf[0]["evidence"])
    check("listening: public ports listed with process, high UDP only counted", "22/tcp sshd" in lf[1]["evidence"] and "1 high UDP" in lf[1]["evidence"])
    lg = ar.login_findings(ar.parse_logins("Accepted publickey for root from 203.0.113.5 port 5 ssh2: ED25519 SHA256:x\n"
                                            "Accepted password for ana from 198.51.100.7 port 6 ssh2\n"))
    check("logins: root over SSH is a warn", lg[0]["status"] == "warn" and "root from 203.0.113.5" in lg[0]["evidence"])
    check("logins: no accepted line at all is unknown (the audit itself logged in, so the log is blind)", ar.login_findings({})[0]["status"] == "unknown")
    pn = os.path.join(tmp, "pnet"); os.makedirs(pn)
    hdr = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
    open(os.path.join(pn, "tcp"), "w").write(hdr + "   0: 00000000:1538 00000000:0000 0A 0:0 00:0 0 0 0 1\n   1: 0100007F:18EB 00000000:0000 0A 0:0 00:0 0 0 0 2\n"
                                              "   2: 0100007F:A1B2 0100007F:0016 01 0:0 00:0 0 0 0 3\n")
    open(os.path.join(pn, "tcp6"), "w").write(hdr + "   0: 00000000000000000000000000000000:0016 00000000000000000000000000000000:0000 0A 0:0 00:0 0 0 0 4\n")
    check("listening without ss: /proc/net read (5432 on all, 6379 local, [::]:22; established skipped)",
          sorted(ar.proc_net_rows(pn)) == [("tcp", "0.0.0.0", 5432, ""), ("tcp", "127.0.0.1", 6379, ""), ("tcp", "::", 22, "")], ar.proc_net_rows(pn))
    cf = ar.container_findings([{"Name": "/a", "HostConfig": {"Privileged": True}, "Mounts": []},
                                {"Name": "/b", "HostConfig": {"SecurityOpt": ["no-new-privileges:true"]}, "Mounts": [{"Source": "/var/run/docker.sock"}]},
                                {"Name": "/c", "HostConfig": {"SecurityOpt": ["no-new-privileges"]}, "Mounts": []}])
    check("containers: privileged and docker.sock are fails", cf[0]["status"] == "fail" and "a privileged" in cf[0]["evidence"] and "docker.sock" in cf[0]["evidence"])
    check("containers: missing no-new-privileges counted", any("1 of 3 without no-new-privileges" in f["evidence"] for f in cf))
    fake = os.path.join(tmp, "proc"); os.makedirs(os.path.join(fake, "41")); os.makedirs(os.path.join(fake, "42"))
    open(os.path.join(fake, "41", "maps"), "w").write("7f r-xp 0 08:01 5 /usr/lib/x86_64-linux-gnu/libssl.so.3 (deleted)\n")
    open(os.path.join(fake, "41", "cgroup"), "w").write("0::/system.slice/nginx.service\n")
    open(os.path.join(fake, "42", "maps"), "w").write("7f r-xp 0 08:01 5 /usr/lib/x86_64-linux-gnu/libc.so.6\n")
    check("stale_libs: a process mapping a deleted library is named by its unit", ar.stale_mappings(fake)[0] == {"nginx.service": 1})
    long_ev = ar.F("x", "R", "ok", "a\nb" + "z" * 900)
    check("evidence: control characters removed and length capped", "\n" not in long_ev["evidence"] and len(long_ev["evidence"]) <= ar.CAP)

    # ---- review fixes: auth.log fallback, strict login parsing, rule ids, IPv6 ss, containers, apt, fail2ban
    import re, time, types
    real_run, real_glob, real_grep = ar.run, ar.glob, ar.run_grep

    def with_fakes(run=None, files=None, grep=None):
        if run is not None:
            ar.run = run
        if grep is not None:
            ar.run_grep = grep
        if files is not None:
            ar.glob = types.SimpleNamespace(glob=lambda pattern: files)

    def undo_fakes():
        ar.run, ar.glob, ar.run_grep = real_run, real_glob, real_grep

    authlog = os.path.join(tmp, "auth.log")
    t_now = time.time()

    def iso_ts(t):
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)) + ".123456" + time.strftime("%z", time.localtime(t))[:3] + ":" + time.strftime("%z", time.localtime(t))[3:]

    def old_ts(t):
        lt = time.localtime(t)
        return f"{time.strftime('%b', lt)} {lt.tm_mday:2d} {time.strftime('%H:%M:%S', lt)}"
    open(authlog, "w").write(f"{iso_ts(t_now - 2 * 86400)} srv sshd[123]: Accepted publickey for ana from 203.0.113.5 port 5 ssh2: ED25519 SHA256:x\n"
                             f"{old_ts(t_now - 86400)} srv sshd[124]: Accepted password for bob from 198.51.100.7 port 6 ssh2\n"
                             f"{iso_ts(t_now - 30 * 86400)} srv sshd[125]: Accepted publickey for oldroot from 192.0.2.99 port 5 ssh2\n"
                             f"{old_ts(t_now - 12 * 86400)} srv sshd[126]: Accepted password for oldbob from 192.0.2.98 port 6 ssh2\n")
    try:
        with_fakes(grep=lambda args, needle, timeout=60, cap=0: (1, "", "journalctl: not installed"), files=[authlog])
        fb = ar.check_logins()
        check("logins: the auth.log fallback works (no TypeError) when the journal fails", len(fb) == 1 and fb[0]["status"] == "warn"
              and "bob from 198.51.100.7 by password" in fb[0]["evidence"] and "ana from 203.0.113.5" in fb[0]["evidence"], fb)
        check("logins: auth.log lines older than 7 days are left out, and the label says what was read",
              "oldroot" not in fb[0]["evidence"] and "oldbob" not in fb[0]["evidence"] and "last 7 days (from auth.log)" in fb[0]["evidence"], fb)
        with_fakes(grep=lambda args, needle, timeout=60, cap=0: (0, "", ""), files=[authlog])
        ar_root = ar.is_root
        ar.is_root = lambda: True
        fb = ar.check_logins()
        ar.is_root = ar_root
        check("logins: the auth.log fallback also runs when the journal has no accepted login", "bob" in fb[0]["evidence"], fb)
        with_fakes(grep=lambda args, needle, timeout=60, cap=0: (0, "Accepted publickey for jo from 192.0.2.7 port 1 ssh2\n", ""), files=[authlog])
        fb = ar.check_logins()
        check("logins: the journal result is labelled as the journal and auth.log is not mixed in",
              "last 7 days (journal)" in fb[0]["evidence"] and "jo from 192.0.2.7" in fb[0]["evidence"] and "bob" not in fb[0]["evidence"], fb)
    finally:
        undo_fakes()

    forged = ["Invalid user x Accepted password for root from 1.2.3.4 port 22 ssh2",
              "Failed password for invalid user a Accepted password for root from 1.2.3.4 port 22 ssh2",
              "Nov  5 10:00:00 srv sshd[9]: Invalid user x Accepted password for root from 1.2.3.4 port 22 ssh2",
              "xx Accepted password for root from 1.2.3.4 port 22 ssh2",
              "Nov  5 10:00:00 srv notsshd[9]: Accepted password for root from 1.2.3.4 port 22 ssh2",
              "Accepted password for root from 1.2.3.4 port 22 ssh2; Accepted password for root from 5.6.7.8 port 1 ssh2",
              "Accepted password for ro ot from 1.2.3.4 port 22 ssh2",
              "Accepted password for root from 1.2.3.4$(id) port 22 ssh2",
              "Accepted password for root from 1.2.3.4 port 22 ssh2 Accepted password for root from 5.6.7.8 port 1 ssh2"]
    check("logins: forged lines (text from the middle of a line) give no login",
          ar.parse_logins("\n".join(forged) + "\n") == {}, ar.parse_logins("\n".join(forged) + "\n"))
    stats = {}
    odd = ar.parse_logins("Accepted publickey for we ird from 1.2.3.4 port 22 ssh2\nAccepted publickey for ana from 2001:db8::1 port 22 ssh2\n", stats)
    check("logins: a real line is kept, an odd one is counted as skipped", odd == {("ana", "2001:db8::1", "publickey"): 1} and stats == {"skipped": 1}, (odd, stats))
    flood = "\n".join(f"Invalid user q Accepted password for root from 10.0.{i // 250}.{i % 250} port 1 ssh2" for i in range(500))
    real = "Accepted publickey for ana from 203.0.113.9 port 7 ssh2\n"
    lg2 = ar.login_findings(ar.parse_logins(flood + "\n" + real))
    check("logins: a forged flood cannot push out or fake a login", lg2[0]["status"] == "ok" and "ana from 203.0.113.9" in lg2[0]["evidence"]
          and "root" not in lg2[0]["evidence"], lg2)
    many = "".join(f"Accepted publickey for u{i} from 192.0.2.{i} port 1 ssh2\n" for i in range(1, 16))
    check("logins: sources beyond the 8 shown are counted in the evidence", "15 sources, the 8 busiest shown" in ar.login_findings(ar.parse_logins(many))[0]["evidence"])

    sec_dir = os.path.join(HERE, "..", "..", "security")
    defined, retired = set(), set()
    for fn in sorted(os.listdir(sec_dir)) if os.path.isdir(sec_dir) else []:
        if fn.endswith(".md"):
            body = open(os.path.join(sec_dir, fn)).read()
            for m in re.finditer(r"^### (SEC-[A-Z]+-\d+): (.*)$", body, re.M):
                defined.add(m.group(1))
                if m.group(2).strip().startswith("Retired"):
                    retired.add(m.group(1))
    cited = set(re.findall(r"SEC-[A-Z]+-\d+", open(root_py).read()))
    bad_ids = sorted(c for c in cited if c not in defined or c in retired)
    check("rule ids: every SEC-* id audit_root.py cites exists in aibridge/security and is not retired",
          bool(defined) and bool(cited) and not bad_ids, f"unknown or retired: {bad_ids}; guide ids found: {len(defined)}")
    check("rule ids: the firewall findings cite SEC-FW-7 (never retired SEC-FW-5)", "SEC-FW-5" in retired and "SEC-FW-5" not in cited)

    p6 = ar.parse_ss('tcp LISTEN 0 128 [::1]%lo:631 [::]:*\ntcp LISTEN 0 128 [fe80::1]%eth0:22 [::]:*\n'
                     'tcp LISTEN 0 128 127.0.0.53%lo:53 0.0.0.0:*\ntcp LISTEN 0 128 [::]:80 [::]:*\ntcp LISTEN 0 128 [2001:db8::5]:443 [::]:*\n')
    check("listening: bracketed IPv6 with a zone parses to a clean address",
          [(a, pt) for _, a, pt, _ in p6] == [("::1", 631), ("fe80::1", 22), ("127.0.0.53", 53), ("::", 80), ("2001:db8::5", 443)], p6)
    lf6 = ar.listening_findings(p6, True)[-1]["evidence"]
    check("listening: [::1]%lo and link-local are local only, not listed as public", "631" not in lf6.split("; ")[0] and "443/tcp on 2001:db8::5" in lf6, lf6)

    one = {"Name": "/a", "HostConfig": {"SecurityOpt": ["no-new-privileges"]}, "Mounts": []}
    try:
        def run_docker(args, timeout=60, ids=("a", "b"), inspect_rc=0, js=json.dumps([one])):
            if args[:2] == ["docker", "ps"]:
                return 0, "\n".join(ids), ""
            return inspect_rc, js if inspect_rc == 0 else "", "Error: No such container: b" if inspect_rc else ""
        with_fakes(run=lambda a, timeout=60: run_docker(a, inspect_rc=1))
        r = ar.check_containers()
        check("containers: a failed docker inspect is unknown and says how many were not inspected, never ok",
              len(r) == 1 and r[0]["status"] == "unknown" and "2 running containers not inspected" in r[0]["evidence"], r)
        many_ids = tuple(f"id{i}" for i in range(100))
        with_fakes(run=lambda a, timeout=60: run_docker(a, ids=many_ids, js=json.dumps([one] * 60)))
        r = ar.check_containers()
        check("containers: 100 running, 60 inspected: no ok, unknown with the 40 not inspected",
              all(f["status"] != "ok" for f in r) and any("could not inspect 40 of 100" in f["evidence"] for f in r), r)
        with_fakes(run=lambda a, timeout=60: run_docker(a, ids=("a",)))
        r = ar.check_containers()
        check("containers: all inspected and clean is still ok", [f["status"] for f in r] == ["ok"], r)
    finally:
        undo_fakes()

    import time
    lists_dir = os.path.join(tmp, "apt-lists"); os.makedirs(lists_dir)
    rel = os.path.join(lists_dir, "deb.debian.org_dists_trixie_InRelease"); open(rel, "w").write("x")
    stamp = os.path.join(tmp, "update-success-stamp"); open(stamp, "w").write("")
    now = time.time()
    os.utime(rel, (now - 20 * 86400,) * 2)
    os.utime(stamp, (now - 86400 * 1.2,) * 2)
    g = os.path.join(lists_dir, "*Release")
    check("apt: an old Release file does not make the lists stale when the update stamp is fresh",
          ar.lists_age_days(g, [stamp], now) == 1, ar.lists_age_days(g, [stamp], now))
    check("apt: with no stamp the Release file date is used", ar.lists_age_days(g, [os.path.join(tmp, "nope")], now) == 20)
    check("apt: no list file and no stamp is None", ar.lists_age_days(os.path.join(tmp, "none*"), [os.path.join(tmp, "nope")], now) is None)
    try:
        with_fakes(run=lambda a, timeout=60: (0, "", ""), files=[])
        ar.lists_age_days = (lambda orig: (lambda **kw: orig(g, [stamp], now, **kw)))(ar.lists_age_days)
        up = ar.check_updates()[0]
        check("apt: evidence says 'newest sign of an apt update', not 'lists N days old'", up["status"] == "ok"
              and "newest sign of an apt update" in up["evidence"] and "1 day old" in up["evidence"], up)
    finally:
        undo_fakes()
        del ar.lists_age_days   # drops the wrapper; reload the real one
        spec.loader.exec_module(ar)

    f2b = "Status for the jail: sshd\n|- Filter\n|  `- File list:\t{}\n`- Actions\n   `- Currently banned:\t0\n"
    check("fail2ban: a jail reading a missing log file is detected", ar.jail_reads_missing_file(f2b.format("/no/such/auth.log"), lambda f: False))
    check("fail2ban: a jail reading an existing file, or the journal, is not flagged",
          not ar.jail_reads_missing_file(f2b.format("/var/log/auth.log"), lambda f: True)
          and not ar.jail_reads_missing_file("|- Filter\n|  `- Journal matches:\t_SYSTEMD_UNIT=sshd.service\n", lambda f: False))
    try:
        ar.is_root = lambda: True
        ar.sqlite3 = types.SimpleNamespace(Error=Exception, connect=lambda *a, **k: types.SimpleNamespace(execute=lambda q: [], close=lambda: None))
        ar.run = lambda args, timeout=60: ((0, "Status\n`- Jail list:\tsshd\n", "") if args[1:] == ["status"]
                                           else (0, "Filter\n File list:\t/dev/null\n", ""))
        qf = ar.check_fail2ban()
        check("fail2ban: a quiet working jail is ok, wording says none in the retention window, never 'never'",
              [f["status"] for f in qf] == ["ok"] and "never" not in qf[0]["evidence"].lower() and "keeps about a day" in qf[0]["evidence"], qf)
    finally:
        undo_fakes()
        spec.loader.exec_module(ar)

    # ---- round-two fixes in audit_root.py
    check("apt: the package cache is not a freshness signal (apt rebuilds it as root)",
          not any("pkgcache" in x for x in ar.APT_STAMPS))
    order = []
    try:
        real_age = ar.lists_age_days
        ar.lists_age_days = lambda **kw: (order.append("age"), real_age(g, [stamp], now, **kw))[1]
        with_fakes(run=lambda a, timeout=60: (order.append(("run", list(a))), (0, "", ""))[1], files=[])
        ar.check_updates()
        runs = [o for o in order if isinstance(o, tuple)]
        check("apt: the lists age is computed BEFORE apt-get runs, and apt-get is given no cache file to write",
              order[0] == "age" and runs and "Dir::Cache::pkgcache=" in runs[0][1] and "Dir::Cache::srcpkgcache=" in runs[0][1], order)
    finally:
        undo_fakes()
        ar.lists_age_days = real_age
    fut = os.path.join(tmp, "future-stamp"); open(fut, "w").write("")
    os.utime(fut, (now + 400 * 86400,) * 2)
    finfo = {}
    check("apt: a stamp dated far in the future is ignored (the Release file date wins) and counted",
          ar.lists_age_days(g, [fut], now, finfo) == 20 and finfo == {"future": 1}, (ar.lists_age_days(g, [fut], now), finfo))
    finfo = {}
    check("apt: only future dates means no sign at all, not 'fresh'",
          ar.lists_age_days(os.path.join(tmp, "none*"), [fut], now, finfo) is None and finfo == {"future": 1})
    os.utime(fut, (now + 3600,) * 2)
    check("apt: a date a few hours ahead (small clock drift) still counts as fresh", ar.lists_age_days(os.path.join(tmp, "none*"), [fut], now) == 0)
    os.utime(fut, (now + 400 * 86400,) * 2)
    try:
        real_age = ar.lists_age_days
        ar.lists_age_days = lambda **kw: real_age(os.path.join(tmp, "none*"), [fut], now, **kw)
        with_fakes(run=lambda a, timeout=60: (0, "", ""), files=[])
        up = ar.check_updates()[0]
        check("apt: zero updates with only a future-dated sign is unknown and the evidence says it was ignored",
              up["status"] == "unknown" and "in the future ignored" in up["evidence"], up)
    finally:
        undo_fakes()
        ar.lists_age_days = real_age

    rcx, outx, _ = ar.run(["/bin/sh", "-c", "printf 'a\\377b\\n'"])
    check("run: non-UTF-8 output is replaced, never an exception", rcx == 0 and outx.startswith("a") and outx.rstrip().endswith("b") and "\ufffd" in outx, outx)
    check("run: the PATH covers /usr/local/bin and /snap/bin", "/usr/local/bin" in ar.CHILD_ENV["PATH"].split(":") and "/snap/bin" in ar.CHILD_ENV["PATH"].split(":"))
    big = ("noise line\n" * 3 + "Accepted publickey for u from 192.0.2.1 port 1 ssh2\n") * 4000
    bigf = os.path.join(tmp, "bigout"); open(bigf, "wb").write(big.encode() + b"Accepted \xff odd\n" + b"Accepted publickey for LAST from 192.0.2.2 port 1 ssh2\n")
    rcg, outg, _ = ar.run_grep(["/bin/cat", bigf], "Accepted ", cap=2000)
    check("run_grep: only matching lines kept, at most the newest cap bytes, newest last, odd bytes tolerated",
          rcg == 0 and len(outg.encode()) <= 2000 and "noise" not in outg and outg.rstrip().endswith("LAST from 192.0.2.2 port 1 ssh2")
          and outg.count("\n") > 10, (rcg, len(outg)))
    t0 = time.time()
    rct, _, errt = ar.run_grep(["/bin/sh", "-c", "exec sleep 20"], "x", timeout=1)
    check("run_grep: a command that hangs is killed at the timeout (rc 124)", rct == 124 and time.time() - t0 < 10, (rct, errt))
    check("run_grep: a missing program is rc 127", ar.run_grep(["/no/such/prog"], "x")[0] == 127)

    tailf = os.path.join(tmp, "tail.log"); open(tailf, "w").write("".join(f"line {i:04d}\n" for i in range(100)))
    tt, cut = ar.read_tail(tailf, cap=45)
    check("read_tail: reads only the end, drops the cut first line, says it was cut",
          cut and tt == "line 0096\nline 0097\nline 0098\nline 0099\n", tt)
    tt, cut = ar.read_tail(tailf, cap=10 ** 6)
    check("read_tail: a small file is read whole", not cut and tt.count("\n") == 100)
    jan = time.mktime((2026, 1, 2, 12, 0, 0, 0, 0, -1))
    lines = ("Dec 30 10:00:00 srv sshd[1]: Accepted publickey for lastyear from 192.0.2.1 port 1 ssh2\n"
             "Dec 20 10:00:00 srv sshd[1]: Accepted publickey for toooldlastyear from 192.0.2.2 port 1 ssh2\n"
             "Jan  1 09:00:00 srv sshd[1]: Accepted publickey for thisyear from 192.0.2.3 port 1 ssh2\n"
             "Jan 20 10:00:00 srv sshd[1]: Accepted publickey for farfuture from 192.0.2.4 port 1 ssh2\n"
             "2025-12-31T23:00:00Z srv sshd[1]: Accepted publickey for isoz from 192.0.2.5 port 1 ssh2\n"
             "2025-12-01T23:00:00+01:00 srv sshd[1]: Accepted publickey for isooff from 192.0.2.6 port 1 ssh2\n"
             "Accepted publickey for nodate from 192.0.2.7 port 1 ssh2\n"
             "Feb 30 10:00:00 srv sshd[1]: Accepted publickey for badday from 192.0.2.8 port 1 ssh2\n")
    kept, undated = ar.recent_lines(lines, jan)
    names = sorted(re.findall(r"for (\w+) from", kept))
    check("auth.log dates: old form uses this year, or last year when that would be in the future; ISO with offsets; 7 days window",
          names == ["isoz", "lastyear", "thisyear"], names)
    check("auth.log dates: accepted-looking lines with no readable date are counted, not trusted", undated == 2, undated)
    ar.glob = types.SimpleNamespace(glob=lambda pattern: [authlog])
    try:
        with_fakes(grep=lambda args, needle, timeout=60, cap=0: (1, "", "x"))
        open(authlog, "w").write(lines)
        fb = ar.check_logins(now=jan)
        check("logins: year logic and the window work end to end; the undated lines are mentioned",
              "lastyear" in fb[0]["evidence"] and "thisyear" in fb[0]["evidence"] and "farfuture" not in fb[0]["evidence"]
              and "2 lines without a readable date left out" in fb[0]["evidence"], fb)
    finally:
        undo_fakes()
    check("logins: an IPv6 source with a zone id is accepted, the zone is not part of the address",
          ar.parse_logins("Accepted publickey for ana from fe80::1%eth0 port 22 ssh2\n"
                          "Nov  5 10:00:00 srv sshd[9]: Accepted publickey for bob from fe80::2%br-lan.1 port 22 ssh2: ED25519 SHA256:x\n")
          == {("ana", "fe80::1", "publickey"): 1, ("bob", "fe80::2", "publickey"): 1})
    zst = {}
    check("logins: a forged zone (too long, spaces, shell characters, or text after the address) is still refused",
          ar.parse_logins("Accepted publickey for a from fe80::1%" + "z" * 17 + " port 22 ssh2\n"
                          "Accepted publickey for a from fe80::1%eth 0 port 22 ssh2\n"
                          "Accepted publickey for a from fe80::1%e$(id) port 22 ssh2\n"
                          "Accepted publickey for a from fe80::1% port 22 ssh2\n", zst) == {} and zst == {"skipped": 4}, zst)
    sockf = os.path.join(tmp, "docker.sock"); open(sockf, "w").write("")
    try:
        with_fakes(run=lambda a, timeout=60: (127, "", "docker: not installed"))
        ar.DOCKER_SOCKS = (sockf,)
        r = ar.check_containers()
        check("containers: no docker CLI but a docker socket is unknown, never silence",
              len(r) == 1 and r[0]["status"] == "unknown" and "docker is running but its CLI was not found" in r[0]["evidence"], r)
        ar.DOCKER_SOCKS = (os.path.join(tmp, "no-socket"),)
        check("containers: no docker CLI and no socket gives no finding, as before", ar.check_containers() == [])
    finally:
        undo_fakes()
        spec.loader.exec_module(ar)

    # ---- audit_root.py: more hardening
    forged_u = "Invalid user x\x0bAccepted publickey for root from 6.6.6.6 port 22 ssh2\nInvalid user y\u2028Accepted publickey for root from 6.6.6.6 port 22 ssh2\n"
    check("logins: a user name with a line-splitting character cannot start a forged login line", ar.parse_logins(forged_u) == {}, ar.parse_logins(forged_u))
    ar.run_grep(["printf", "Accepted a\\nAccepted b\\nAccepted c\\nnothing\\n"], "Accepted ", cap=12)
    check("run_grep: dropping old matches to stay under the cap sets truncated", ar.run_grep.truncated is True)
    ar.run_grep(["printf", "Accepted a\\n"], "Accepted ", cap=1000)
    check("run_grep: nothing dropped, truncated is False", ar.run_grep.truncated is False)
    pth = ar.CHILD_ENV["PATH"].split(":")
    check("child PATH: system directories come before /usr/local and /snap", pth.index("/usr/bin") < pth.index("/usr/local/bin") < pth.index("/snap/bin"))
    # ---- install.sh against a fake root (paths rewritten into a temp dir, fake useradd/install/sshd; nothing real is touched)
    inst = open(os.path.join(HERE, "install.sh")).read()
    root = os.path.join(tmp, "fakeroot"); fb = os.path.join(root, "bin"); os.makedirs(fb)
    for var, sub in (("LIB", "lib"), ("ETC", "etc"), ("HC_HOME", "home"), ("SUDOERS", "sudoers")):
        inst, n = re.subn(rf"(?m)^{var}=.*$", f"{var}={root}/{sub}", inst)
        assert n == 1, var
    for name in ("hostcare_mcp.py", "audit_root.py"):
        _st_shutil.copy(os.path.join(HERE, name), root)
    open(os.path.join(root, "install.sh"), "w").write(inst)
    fakes = {
        "id": 'if [ "$1" = -u ]; then echo 0; elif [ "$1" = -Gn ]; then echo "${IDGROUPS:-hostcare}"; else [ -e "$ROOT/user-exists" ]; fi',
        "getent": '[ -z "$FAKE_HOME" ] || echo "hostcare:x:900:900::$FAKE_HOME:/bin/sh"',
        "useradd": 'mkdir -p "$ROOT/home"; touch "$ROOT/user-exists"',
        "userdel": '[ -z "$USERDEL_FAIL" ] && rm -f "$ROOT/user-exists"; [ -z "$USERDEL_FAIL" ]',
        "usermod": "exit 0", "chown": 'echo "chown $*" >> "$ROOT/cmds.log"', "pkill": "exit 0", "loginctl": "exit 0", "sleep": "exit 0", "visudo": "exit 0",
        "sshd": 'echo "port 22"; [ -z "$SSHD_EXTRA" ] || printf "%s\\n" "$SSHD_EXTRA"',
        "install": 'echo "install $*" >> "$ROOT/cmds.log"\n'
                   'd=0; m=""; while [ $# -gt 0 ]; do case "$1" in -d) d=1; shift;; -m) m=$2; shift 2;; -o|-g) shift 2;; *) break;; esac; done\n'
                   'if [ $d = 1 ]; then mkdir -p "$@"; [ -z "$m" ] || chmod "$m" "$@"; else cp "$1" "$2"; fi',
    }
    for name, body in fakes.items():
        fp = os.path.join(fb, name); open(fp, "w").write("#!/bin/sh\n" + body + "\n"); os.chmod(fp, 0o755)
    ienv = {**os.environ, "PATH": fb + ":" + os.environ["PATH"], "ROOT": root, "TMPDIR": tmp}

    def inst_run(*args, **extra):
        return subprocess.run(["sh", os.path.join(root, "install.sh")] + list(args), capture_output=True, text=True,
                              env={**ienv, **extra}, timeout=60, cwd=root)

    keyA = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI" + "A" * 43 + " bridgeai-sysadmin-a"
    keyB = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI" + "B" * 43 + " bridgeai-sysadmin-b"
    ak = os.path.join(root, "home", ".ssh", "authorized_keys")
    r = inst_run("--key", keyA, "--from", "192.0.2.1", "--name", "srv")
    akt = open(ak).read() if os.path.exists(ak) else ""
    check("install.sh: first install writes exactly one restricted key line", r.returncode == 0 and akt.count("\n") == 1
          and akt.startswith('restrict,from="192.0.2.1",command="') and akt.rstrip().endswith(keyA), r.stderr + r.stdout + akt)
    home = os.path.join(root, "home")
    cmds = open(os.path.join(root, "cmds.log")).read()
    mode = lambda path: oct(os.stat(path).st_mode & 0o7777)
    check("install.sh: the home is root-owned, group hostcare, mode 0750 (never chowned to hostcare)",
          f"chown root:hostcare {home}\n" in cmds and f"chown hostcare" not in cmds and mode(home) == "0o750", (cmds, mode(home)))
    check("install.sh: .ssh and .local are root-owned directories, only ~/.local/state belongs to hostcare (0700)",
          f"install -d -o root -g root -m 0755 {home}/.ssh\n" in cmds and f"install -d -o root -g hostcare -m 0750 {home}/.local\n" in cmds
          and f"install -d -o hostcare -g hostcare -m 0700 {home}/.local/state\n" in cmds and mode(home + "/.local/state") == "0o700"
          and mode(home + "/.ssh") == "0o755" and cmds.count("-o hostcare") == 1, cmds)
    check("install.sh: the key file is built root-owned in the root-only .ssh and moved in, no authorized_keys.new left",
          f"chown root:root {home}/.ssh/.authorized_keys." in cmds and not [n for n in os.listdir(home + "/.ssh") if n != "authorized_keys"], os.listdir(home + "/.ssh"))
    check("install.sh: a fresh install does not claim a repair", "repaired" not in r.stdout, r.stdout)
    # an earlier version left the home owned by hostcare and writable: running the installer again repairs it
    os.chmod(home, 0o775); os.chmod(home + "/.ssh", 0o777); _st_shutil.rmtree(home + "/.local")
    n_before = open(os.path.join(root, "cmds.log")).read().count(f"chown root:hostcare {home}\n")
    r = inst_run("--key", keyA, "--from", "192.0.2.1", "--name", "srv")
    check("install.sh: re-running repairs an old install (home chowned to root again, modes reset, state dir recreated) and says so",
          r.returncode == 0 and mode(home) == "0o750" and mode(home + "/.ssh") == "0o755" and mode(home + "/.local/state") == "0o700"
          and open(os.path.join(root, "cmds.log")).read().count(f"chown root:hostcare {home}\n") == n_before + 1
          and "repaired" in r.stdout, (r.stdout, r.stderr))
    open(ak, "a").write("ssh-ed25519 AAAAFOREIGN someone-else\n")
    r = inst_run("--key", keyB, "--from", "192.0.2.1", "--name", "srv")
    akt = open(ak).read()
    check("install.sh: rotation replaces the old hostcare key and keeps other people's keys",
          r.returncode == 0 and "A" * 43 not in akt and akt.count("B" * 43) == 1 and "AAAAFOREIGN someone-else" in akt
          and akt.count("\n") == 2 and "replaced 1 earlier hostcare key" in r.stdout and "that old key no longer works" in r.stdout, r.stderr + r.stdout + akt)
    r = inst_run("--key", keyB, "--from", "192.0.2.1", "--name", "srv")
    check("install.sh: running the same key again is idempotent", r.returncode == 0 and open(ak).read().count("B" * 43) == 1
          and open(ak).read().count("\n") == 2)
    before = open(ak).read()
    for what, args in (("--key", ["--key", keyB + "\nssh-rsa ATTACKER"]), ("--key (valid line second)", ["--key", "junk\n" + keyB]),
                       ("--key CR", ["--key", keyB + "\rx"]), ("--from", ["--key", keyB, "--from", "1.1.1.1\n" + keyB]),
                       ("--name", ["--key", keyB, "--name", "a\nb"]), ("--name ok line first", ["--key", keyB, "--name", "ok\n"]),
                       ("--key trailing text", ["--key", keyB + " extra words"])):
        r = inst_run(*args)
        check(f"install.sh: {what} with an embedded newline or invalid value is refused, nothing written",
              r.returncode != 0 and open(ak).read() == before, r.stderr + r.stdout)
    # sshd allow lists: never advise a new AllowUsers line; judge groups by the user's real groups; patterns and several names per line
    def warn_for(extra, groups="hostcare"):
        rr = inst_run("--key", keyB, SSHD_EXTRA=extra, IDGROUPS=groups)
        return rr.returncode, rr.stderr
    rc_, e_ = warn_for("allowgroups sshusers admins", "hostcare sshusers")
    check("install.sh: AllowGroups that covers the user's group gives no warning", rc_ == 0 and "AllowGroups" not in e_, e_)
    rc_, e_ = warn_for("allowgroups sshusers admins", "hostcare")
    check("install.sh: AllowGroups without the user's group warns and advises a group, never a new AllowUsers line",
          "AllowGroups does not cover" in e_ and "usermod -aG" in e_ and "rather than adding any AllowUsers line" in e_ and "AllowUsers does not list" not in e_, e_)
    rc_, e_ = warn_for("allowusers alice host*")
    check("install.sh: an AllowUsers pattern that matches the user (host*) gives no warning", "AllowUsers" not in e_, e_)
    rc_, e_ = warn_for("allowusers alice bob")
    check("install.sh: AllowUsers with several names and not the user warns, and says to extend the existing line", "AllowUsers does not list" in e_ and "do not start a second line" in e_, e_)
    r = inst_run("--key", keyB)
    check("install.sh: the same key again says the line was refreshed, not that an old key stopped working",
          "refreshed" in r.stdout and "no longer works" not in r.stdout, r.stdout)
    open(os.path.join(root, "user-exists"), "w").close()
    r = inst_run("--key", keyB, FAKE_HOME="/home/hostcare")
    check("install.sh: an existing account with that name and another home is refused", r.returncode != 0 and "not ours" in r.stderr and "nothing was changed" in r.stderr, r.stderr)
    # the python path lands inside the forced command of the key: a path with a space or a quote is refused
    pydir = os.path.join(tmp, 'py dir'); os.makedirs(pydir)
    open(os.path.join(pydir, "python3"), "w").write('#!/bin/sh\nexec %s "$@"\n' % sys.executable); os.chmod(os.path.join(pydir, "python3"), 0o755)
    ak_now = open(ak).read()
    r = inst_run("--key", keyB, PATH=pydir + ":" + ienv["PATH"])
    check("install.sh: a python3 path with a space is refused, nothing written", r.returncode != 0 and "absolute path" in r.stderr and open(ak).read() == ak_now, r.stderr)
    # planted symlinks: refused, the target is never touched (the old script wrote through them as root)
    victim = os.path.join(tmp, "victim"); open(victim, "w").write("precious\n")
    ak_state = open(ak).read()
    ssh_dir = os.path.join(home, ".ssh")
    os.symlink(victim, ak + ".new")
    r = inst_run("--key", keyA, "--from", "192.0.2.1", "--name", "srv")
    check("install.sh: a planted authorized_keys.new symlink is refused and its target is untouched",
          r.returncode != 0 and open(victim).read() == "precious\n" and open(ak).read() == ak_state and "symbolic link" in r.stderr, r.stderr + r.stdout)
    os.unlink(ak + ".new")
    os.rename(ak, ak + ".real"); os.symlink(victim, ak)
    r = inst_run("--key", keyA, "--from", "192.0.2.1", "--name", "srv")
    check("install.sh: authorized_keys that is a symlink is refused and its target is untouched",
          r.returncode != 0 and open(victim).read() == "precious\n" and os.path.islink(ak), r.stderr + r.stdout)
    os.unlink(ak); os.rename(ak + ".real", ak)
    elsewhere = os.path.join(tmp, "elsewhere-ssh"); os.makedirs(elsewhere)
    open(os.path.join(elsewhere, "authorized_keys"), "w").write("ssh-ed25519 AAAAOTHER root-key\n")
    os.rename(ssh_dir, ssh_dir + ".real"); os.symlink(elsewhere, ssh_dir)
    r = inst_run("--key", keyA, "--from", "192.0.2.1", "--name", "srv")
    check("install.sh: a .ssh that is a symlink is refused and the directory it points to is untouched",
          r.returncode != 0 and os.listdir(elsewhere) == ["authorized_keys"] and "root-key" in open(os.path.join(elsewhere, "authorized_keys")).read()
          and "symbolic link" in r.stderr, r.stderr + r.stdout)
    r = inst_run("--uninstall", USERDEL_FAIL="1")
    check("install.sh: uninstall does not follow a symlinked .ssh to delete the key it points to",
          os.path.isfile(os.path.join(elsewhere, "authorized_keys")) and "symlink" in r.stderr, r.stderr + r.stdout)
    r = inst_run("--key", keyA, "--name", "srv", USERDEL_FAIL="1")   # put a normal install back for the uninstall tests below
    r = inst_run("--uninstall", USERDEL_FAIL="1")
    check("install.sh: uninstall that cannot remove the user keeps the copy for the retry and says so",
          r.returncode == 1 and os.path.isfile(os.path.join(root, "lib", "install.sh")) and not os.path.exists(ak)
          and f"sh {root}/lib/install.sh --uninstall" in r.stderr, r.stderr + r.stdout)
    r = inst_run("--uninstall")
    check("install.sh: the retry removes everything, including the copy", r.returncode == 0
          and not os.path.exists(os.path.join(root, "lib")) and not os.path.exists(os.path.join(root, "home")), r.stderr + r.stdout)
    print("ALL OK" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
