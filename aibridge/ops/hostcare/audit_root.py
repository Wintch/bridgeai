#!/usr/bin/env python3
"""audit_root.py: the sysadmin pack's read-only audit of this machine, printed as JSON (stdlib only, Python 3.8+).

Installed root-owned at /usr/local/lib/hostcare/audit_root.py by install.sh. hostcare's `audit` tool runs it through one
sudoers line that allows exactly this file with no arguments (`... audit_root.py ""`). It takes no arguments, writes nothing
and changes nothing. It prints one JSON object:

  {"version": 1, "host": "...", "root": true, "time": "...Z",
   "findings": [{"check": "ssh", "rule": "SEC-HARD-1", "status": "ok|warn|fail|unknown", "evidence": "..."}, ...]}

Without root, the checks that need it come back "unknown" with the reason, never "ok".
Evidence is short: counts, names, versions, addresses and ports. Never file contents, never a secret.
The rule IDs are those of the security guide (aibridge/security/ in the bridgeai repository).
"""
import collections, datetime, glob, json, os, re, socket, sqlite3, subprocess, sys, threading, time

VERSION = 1
CAP = 400
TODAY = datetime.date.today()

# End of free security support (standard or LTS). Past it: fail; within 180 days: warn. Ubuntu Pro/ESM and Debian ELTS
# extend it for those who pay or enrol, which this check cannot see, so the evidence says so.
SUPPORT_END = {
    "debian": {"9": "2022-06-30", "10": "2024-06-30", "11": "2026-08-31", "12": "2028-06-30", "13": "2030-06-30"},
    "ubuntu": {"16.04": "2021-04-30", "18.04": "2023-05-31", "20.04": "2025-05-31", "22.04": "2027-04-30",
               "24.04": "2029-04-30", "24.10": "2025-07-10", "25.04": "2026-01-15", "25.10": "2026-07-09",
               "26.04": "2031-04-30"},
}
DB_PORTS = {3306: "MySQL/MariaDB", 5432: "PostgreSQL", 6379: "Redis", 27017: "MongoDB", 9200: "Elasticsearch",
            11211: "memcached", 5984: "CouchDB", 9042: "Cassandra", 2375: "Docker API without TLS"}


def F(check, rule, status, evidence):
    evidence = re.sub(r"[\x00-\x1f\x7f]", " ", str(evidence)).strip()
    return {"check": check, "rule": rule, "status": status,
            "evidence": evidence if len(evidence) <= CAP else evidence[:CAP - 1] + "…"}


# /usr/local/bin and /snap/bin: Docker (and others) installed by hand or as a snap live there
# (after the system directories: a file planted in /usr/local/bin must never shadow a system tool that runs as root)
CHILD_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/sbin:/usr/local/bin:/snap/bin", "LC_ALL": "C", "LANG": "C"}


def run(args, timeout=60):
    """argv only, never a shell. Returns (rc, stdout, stderr); rc 127 when the program is missing.
    Output is decoded with errors="replace": a process name or a firewall comment with odd bytes never raises."""
    try:
        p = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout, env=CHILD_ENV)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"{args[0]}: not installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"{args[0]}: timed out"
    except OSError as exc:
        return 126, "", f"{args[0]}: {exc}"


def read(path):
    with open(path, errors="replace") as f:
        return f.read()


def run_grep(args, needle, timeout=60, cap=4 * 1024 * 1024):
    """Like run(), but for commands with a lot of output (the journal): stdout is streamed, only the lines containing
    `needle` are kept, and of those at most the newest `cap` bytes. Returns (rc, kept text, stderr head)."""
    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=CHILD_ENV)
    except FileNotFoundError:
        return 127, "", f"{args[0]}: not installed"
    except OSError as exc:
        return 126, "", f"{args[0]}: {exc}"
    err, timed_out = [], []

    def drain():   # stderr must be read or a chatty child blocks; only its head is kept
        err.append(p.stderr.read(4096))
        while p.stderr.read(65536):
            pass

    def kill():
        timed_out.append(1)
        p.kill()

    t, timer = threading.Thread(target=drain, daemon=True), threading.Timer(timeout, kill)
    t.start()
    timer.start()
    key, kept, size = needle.encode(), collections.deque(), 0
    run_grep.truncated = False   # True when the oldest matching lines were dropped to stay under `cap`
    try:
        while True:
            line = p.stdout.readline(65536)
            if not line:
                break
            if key in line:
                kept.append(line)
                size += len(line)
                while size > cap and kept:
                    size -= len(kept.popleft())
                    run_grep.truncated = True
        p.wait()
    finally:
        timer.cancel()
        p.stdout.close()
    t.join(2)
    text = b"".join(kept).decode("utf-8", "replace")
    head = (err[0] if err else b"").decode("utf-8", "replace")
    return (124 if timed_out else p.returncode), text, (head if not timed_out else f"{args[0]}: timed out")


def read_tail(path, cap=4 * 1024 * 1024):
    """The last `cap` bytes of a text file, without the cut first line. Returns (text, was_cut)."""
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        cut = size > cap
        f.seek(size - cap if cut else 0)
        data = f.read(cap)
    if cut:
        nl = data.find(b"\n")
        data = data[nl + 1:] if nl >= 0 else b""
    return data.decode("utf-8", "replace"), cut


def is_root():
    return os.geteuid() == 0


def denied(err):
    return bool(re.search(r"permission denied|not permitted|must be root|are you root|need to be root|got permission", err or "", re.I))


def first_line(text):
    return (text or "").strip().splitlines()[0][:160] if (text or "").strip() else ""


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------- os
def parse_os_release(text):
    out = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"\'')
    return out


def os_support(os_id, version_id, today=TODAY):
    end = SUPPORT_END.get(os_id, {}).get(version_id)
    if not end:
        return "unknown", "no support date known for this release"
    d = datetime.date.fromisoformat(end)
    days = (d - today).days
    if days < 0:
        return "fail", f"free security support ended {end}"
    if days < 180:
        return "warn", f"free security support ends {end} ({days} days)"
    return "ok", f"supported until {end}"


def check_os():
    try:
        rel = parse_os_release(read("/etc/os-release"))
    except OSError as exc:
        return [F("os", "SEC-PATCH-21", "unknown", f"/etc/os-release unreadable: {exc.strerror}")]
    os_id, ver = rel.get("ID", "?"), rel.get("VERSION_ID", "?")
    status, why = os_support(os_id, ver)
    extra = " (Ubuntu Pro/ESM or Debian ELTS can extend it; not visible here)" if status in ("fail", "warn") else ""
    return [F("os", "SEC-PATCH-21", status, f"{rel.get('PRETTY_NAME', os_id + ' ' + ver)}, kernel {os.uname().release}: {why}{extra}")]


# ---------------------------------------------------------------- updates, reboot, unattended
def parse_apt_sim(text):
    """`apt-get -s dist-upgrade` → (all upgradable names, security names)."""
    names, sec = [], []
    for line in text.splitlines():
        m = re.match(r"Inst (\S+) (?:\[[^\]]*\] )?\((.*)\)", line)
        if m:
            names.append(m.group(1))
            if re.search(r"security", m.group(2), re.I):
                sec.append(m.group(1))
    return names, sec


APT_LISTS = "/var/lib/apt/lists/*Release"
# pkgcache.bin is NOT a signal: apt rebuilds it on any apt command run as root, so it says nothing about `apt update`
APT_STAMPS = ["/var/lib/apt/periodic/update-success-stamp"]
FUTURE_SLACK = 86400   # a signal dated more than a day ahead of now is a wrong clock or a touched file


def lists_age_days(lists=APT_LISTS, stamps=tuple(APT_STAMPS), now=None, info=None):
    """Days since the newest sign that `apt update` ran, or None when there is none. The mtime of a list file is the
    archive's Last-Modified (an unchanged archive keeps an old date), so the periodic success stamp counts too: the newest
    of them is the best evidence available. Dates in the future are ignored (info["future"] counts them)."""
    now = datetime.datetime.now().timestamp() if now is None else now
    times, future = [], 0
    for path in glob.glob(lists) + list(stamps):
        try:
            m = os.path.getmtime(path)
        except OSError:
            continue
        if m > now + FUTURE_SLACK:
            future += 1
            continue
        times.append(m)
    if info is not None:
        info["future"] = future
    if not times:
        return None
    return max(0, int((now - max(times)) // 86400))


def check_updates():
    # the age is read BEFORE apt-get runs, and apt-get gets no cache file to write (`-s` alone still rebuilds pkgcache.bin as root)
    finfo = {}
    age = lists_age_days(info=finfo)
    rc, out, err = run(["apt-get", "-s", "-o", "Debug::NoLocking=1", "-o", "Dir::Cache::pkgcache=",
                        "-o", "Dir::Cache::srcpkgcache=", "dist-upgrade"], timeout=120)
    if rc == 127:
        return [F("updates", "SEC-PATCH-2", "unknown", "apt-get not found: only Debian and Ubuntu are checked today")]
    if rc != 0:
        return [F("updates", "SEC-PATCH-2", "unknown", f"apt-get -s failed: {first_line(err or out)}")]
    names, sec = parse_apt_sim(out)
    age_txt = ("no sign that the package lists were ever downloaded" if age is None
               else f"newest sign of an apt update (list file or update stamp) is {plural(age, 'day')} old")
    if finfo.get("future"):
        age_txt += f" ({plural(finfo['future'], 'file date')} in the future ignored: wrong clock?)"
    stale = age is None or age > 3
    ev = f"{plural(len(sec), 'security update')} pending, {len(names)} upgradable in all; {age_txt}"
    if sec:
        ev += ": " + ", ".join(sorted(sec)[:12]) + (" …" if len(sec) > 12 else "")
    if stale:
        ev += " (old lists hide updates: run apt-get update first, SEC-PATCH-2)"
    status = "fail" if sec else ("warn" if names or stale else "ok")
    if not names and stale:
        status = "unknown"   # zero with old lists proves nothing (SEC-PATCH-2)
    return [F("updates", "SEC-PATCH-2", status, ev)]


def kernel_version_key(v):
    return [int(x) if x.isdigit() else x for x in re.split(r"[.\-+~]", v)]


def check_reboot():
    reasons = []
    if os.path.exists("/run/reboot-required"):
        n = 0
        try:
            n = len([l for l in read("/run/reboot-required.pkgs").splitlines() if l.strip()])
        except OSError:
            pass
        reasons.append("/run/reboot-required is present" + (f" ({plural(n, 'package')})" if n else ""))
    running = os.uname().release
    kernels = [os.path.basename(p)[len("vmlinuz-"):] for p in glob.glob("/boot/vmlinuz-*")]
    flavour = re.sub(r"^[\d.\-]+", "", running)   # e.g. "amd64", "generic", "cloud-amd64"
    same = [k for k in kernels if re.sub(r"^[\d.\-]+", "", k) == flavour]
    if same:
        try:
            newest = max(same, key=kernel_version_key)
        except TypeError:
            newest = sorted(same)[-1]
        if newest != running:
            reasons.append(f"running kernel {running}, newest installed {newest}")
    if reasons:
        return [F("reboot", "SEC-PATCH-3", "warn", "; ".join(reasons) + ": plan a reboot")]
    return [F("reboot", "SEC-PATCH-3", "ok", f"no reboot pending (kernel {running})")]


def check_unattended():
    rc, st, _ = run(["dpkg-query", "-W", "-f=${Status}", "unattended-upgrades"])
    if rc == 127:
        return [F("unattended", "SEC-PATCH-12", "unknown", "dpkg-query not found")]
    if "install ok installed" not in st:
        return [F("unattended", "SEC-PATCH-12", "warn", "unattended-upgrades is not installed: security updates wait for a person")]
    _, dump, _ = run(["apt-config", "dump"])
    on = re.search(r'^APT::Periodic::Unattended-Upgrade "([^"]*)"', dump, re.M)
    lists = re.search(r'^APT::Periodic::Update-Package-Lists "([^"]*)"', dump, re.M)
    if not on or on.group(1) in ("0", ""):
        return [F("unattended", "SEC-PATCH-12", "warn", "unattended-upgrades is installed but not enabled (APT::Periodic::Unattended-Upgrade)")]
    reboot = re.search(r'^Unattended-Upgrade::Automatic-Reboot "([^"]*)"', dump, re.M)
    ev = "enabled" + ("" if lists and lists.group(1) not in ("0", "") else ", but package lists are not refreshed daily")
    if reboot and reboot.group(1).lower() == "true":
        ev += "; automatic reboot is on (the guide keeps it off)"
    return [F("unattended", "SEC-PATCH-12", "ok" if ev == "enabled" else "warn", ev)]


# ---------------------------------------------------------------- stale libraries
def stale_mappings(proc="/proc"):
    """Processes that still map a deleted shared library → {name: count}. Needs root for other users' processes."""
    found, unreadable = {}, 0
    for d in os.listdir(proc):
        if not d.isdigit():
            continue
        try:
            with open(os.path.join(proc, d, "maps")) as f:
                hit = any(".so" in line and line.rstrip().endswith("(deleted)") and "/memfd:" not in line
                          and " /dev/" not in line and "/SYSV" not in line for line in f)
        except (PermissionError, ProcessLookupError, FileNotFoundError):
            unreadable += 1
            continue
        except OSError:
            continue
        if not hit:
            continue
        name = unit_of(proc, d)
        found[name] = found.get(name, 0) + 1
    return found, unreadable


def unit_of(proc, pid):
    try:
        cg = read(os.path.join(proc, pid, "cgroup"))
        m = re.search(r"/([^/\n]+\.(?:service|scope))", cg)
        if m and not m.group(1).startswith(("session-", "user@")):
            return m.group(1)
    except OSError:
        pass
    try:
        return read(os.path.join(proc, pid, "comm")).strip() or pid
    except OSError:
        return pid


def check_stale_libs():
    if not is_root():
        return [F("stale_libs", "SEC-PATCH-13", "unknown", "needs root to read every process (the sudo rule for the helper is missing)")]
    found, _ = stale_mappings()
    if not found:
        return [F("stale_libs", "SEC-PATCH-13", "ok", "no process maps a deleted library")]
    items = sorted(found.items(), key=lambda kv: (-kv[1], kv[0]))
    return [F("stale_libs", "SEC-PATCH-13", "warn", f"{plural(len(items), 'service')} still run replaced libraries, restart them: "
              + ", ".join(n for n, _ in items[:15]) + (" …" if len(items) > 15 else ""))]


# ---------------------------------------------------------------- ssh
def parse_sshd_T(text):
    cfg = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            cfg.setdefault(parts[0].lower(), parts[1].strip())
    return cfg


def ssh_findings(cfg):
    out = []
    root = cfg.get("permitrootlogin", "?")
    if root == "yes":
        out.append(F("ssh", "SEC-POL-1", "fail", "PermitRootLogin yes: root logs in over SSH, even with a password"))
    elif root in ("prohibit-password", "without-password"):
        out.append(F("ssh", "SEC-POL-1", "warn", f"PermitRootLogin {root}: root logs in with a key; the guide says no"))
    elif root == "forced-commands-only":
        out.append(F("ssh", "SEC-POL-1", "ok", "PermitRootLogin forced-commands-only"))
    else:
        out.append(F("ssh", "SEC-POL-1", "ok", f"PermitRootLogin {root}"))
    pw = cfg.get("passwordauthentication", "?")
    kbd = cfg.get("kbdinteractiveauthentication", cfg.get("challengeresponseauthentication", "no"))
    if pw == "yes" or kbd == "yes":
        which = "PasswordAuthentication yes" if pw == "yes" else "KbdInteractiveAuthentication yes"
        out.append(F("ssh", "SEC-POL-2", "warn", f"{which} for every user: passwords only per temporary user (Match User), keys by default"))
    else:
        out.append(F("ssh", "SEC-POL-2", "ok", "passwords off (PasswordAuthentication no)"))
    if cfg.get("pubkeyauthentication", "yes") != "yes":
        out.append(F("ssh", "SEC-HARD-1", "warn", "PubkeyAuthentication no"))
    if cfg.get("permitemptypasswords") == "yes":
        out.append(F("ssh", "SEC-HARD-1", "fail", "PermitEmptyPasswords yes"))
    ports = cfg.get("port", "22")
    allow = [f"{k} {cfg[k]}" for k in ("allowusers", "allowgroups") if k in cfg]
    out.append(F("ssh", "SEC-HARD-1", "ok", f"port {ports}; MaxAuthTries {cfg.get('maxauthtries', '?')}"
                 + (f"; {', '.join(allow)}" if allow else "")))
    return out


def check_ssh():
    rc, out, err = run(["sshd", "-T"])
    if rc == 127:
        if not os.path.exists("/usr/sbin/sshd"):
            return [F("ssh", "SEC-HARD-1", "unknown", "sshd not found")]
    if rc != 0:
        why = "needs root (the sudo rule for the helper is missing)" if (denied(err) or not is_root()) else first_line(err)
        return [F("ssh", "SEC-HARD-1", "unknown", f"sshd -T failed: {why}")]
    return ssh_findings(parse_sshd_T(out))


# ---------------------------------------------------------------- accounts
NOLOGIN = re.compile(r"(nologin|/false|/sync|/shutdown|/halt)$")


def parse_sudoers(texts):
    """sudoers texts → {who: "NOPASSWD" | "password"} for user and %group rules (aliases and Defaults skipped)."""
    who = {}
    for text in texts:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith(("#include", "@include")):
                continue
            line = line.split("#", 1)[0].strip()
            if not line or line.split()[0] in ("Defaults", "Cmnd_Alias", "User_Alias", "Host_Alias", "Runas_Alias") \
                    or line.startswith("Defaults"):
                continue
            m = re.match(r"^(%?[A-Za-z0-9_.-]+)\s+[^=\s]+\s*=\s*(.*)$", line)
            if m:
                kind = "NOPASSWD" if "NOPASSWD" in m.group(2) else "password"
                if who.get(m.group(1)) != "NOPASSWD":
                    who[m.group(1)] = kind
    return who


def read_sudoers():
    texts = []
    for path in ["/etc/sudoers"] + sorted(glob.glob("/etc/sudoers.d/*")):
        base = os.path.basename(path)
        if path != "/etc/sudoers" and ("." in base or base.endswith("~")):
            continue   # sudo itself ignores these names
        try:
            texts.append(read(path))
        except OSError:
            return None
    return texts


def account_findings(passwd, shadow, group, sudo=None):
    users = []
    for line in passwd.splitlines():
        f = line.split(":")
        if len(f) >= 7:
            users.append((f[0], int(f[2]) if f[2].isdigit() else -1, f[6]))
    login = [u for u, uid, sh in users if not NOLOGIN.search(sh or "") and (uid == 0 or uid >= 1000) and uid != 65534]
    uid0 = [u for u, uid, _ in users if uid == 0 and u != "root"]
    admins = set()
    for line in group.splitlines():
        f = line.split(":")
        if len(f) >= 4 and f[0] in ("sudo", "wheel", "admin"):
            admins.update(x for x in f[3].split(",") if x)
    out = []
    if uid0:
        out.append(F("accounts", "SEC-POL-9", "fail", f"accounts with uid 0 besides root: {', '.join(uid0)}"))
    if shadow is None:
        out.append(F("accounts", "SEC-POL-9", "unknown", f"login accounts: {', '.join(login) or 'none'}; admin group: "
                     f"{', '.join(sorted(admins)) or 'nobody'}; passwords and expiry need root"))
        return out
    sh = {}
    for line in shadow.splitlines():
        f = line.split(":")
        if len(f) >= 8:
            sh[f[0]] = f
    empty = [u for u in login if u in sh and sh[u][1] == ""]
    with_pw = [u for u in login if u in sh and sh[u][1] and not sh[u][1].startswith(("!", "*"))]
    no_expiry = [u for u in with_pw if u != "root" and not sh[u][7].strip()]
    if empty:
        out.append(F("accounts", "SEC-POL-9", "fail", f"accounts with an EMPTY password: {', '.join(empty)}"))
    ev = (f"login accounts: {', '.join(login) or 'none'}; admin group (sudo/wheel): {', '.join(sorted(admins)) or 'nobody'}; "
          f"with a password: {', '.join(with_pw) or 'none'}")
    if sudo is not None:
        rules = [f"{w}{' without password' if k == 'NOPASSWD' else ''}" for w, k in sorted(sudo.items()) if w not in ("root", "hostcare")]
        ev += f"; sudo rules for: {', '.join(rules) or 'nobody else'} (hostcare: only this audit)"
    if no_expiry:
        out.append(F("accounts", "SEC-POL-9", "warn", ev + f"; password accounts with no expiry date: {', '.join(no_expiry)} "
                     "(a third party's account is dated: chage -E)"))
    else:
        out.append(F("accounts", "SEC-POL-9", "ok", ev))
    return out


def check_accounts():
    try:
        passwd, group = read("/etc/passwd"), read("/etc/group")
    except OSError as exc:
        return [F("accounts", "SEC-POL-9", "unknown", f"/etc/passwd unreadable: {exc.strerror}")]
    try:
        shadow = read("/etc/shadow")
    except OSError:
        shadow = None
    texts = read_sudoers() if is_root() else None
    return account_findings(passwd, shadow, group, parse_sudoers(texts) if texts is not None else None)


# ---------------------------------------------------------------- listening
def parse_ss(text):
    """`ss -Htlnup` lines → [(proto, addr, port, process)]."""
    rows = []
    for line in text.splitlines():
        f = line.split()
        if len(f) < 5:
            continue
        proto, local = f[0], f[4]
        if ":" not in local:
            continue
        if local.startswith("[") and "]" in local:   # [::1]:631, [fe80::1]%eth0:22
            end = local.index("]")
            addr, rest = local[1:end], local[end + 1:]
            if ":" not in rest:
                continue
            port = rest.rsplit(":", 1)[1]
        else:
            addr, port = local.rsplit(":", 1)
        addr = addr.split("%")[0]
        proc = ""
        m = re.search(r'users:\(\("([^"]+)"', line)
        if m:
            proc = m.group(1)
        if port.isdigit():
            rows.append((proto, addr, int(port), proc))
    return rows


def is_public_bind(addr):
    return addr in ("0.0.0.0", "*", "::", "") or not (addr.startswith("127.") or addr == "::1" or addr.startswith("fe80"))


def listening_findings(rows, have_proc):
    seen, public, local_only, dbs, high_udp = set(), [], 0, [], 0
    for proto, addr, port, proc in rows:
        if proto == "udp" and port >= 32768 and is_public_bind(addr):
            high_udp += 1   # ephemeral client sockets (DNS, DHT, mDNS replies): counted, not listed
            continue
        key = (proto, port, proc, is_public_bind(addr))
        if key in seen:
            continue
        seen.add(key)
        if is_public_bind(addr):
            label = f"{port}/{proto}" + (f" {proc}" if proc else "") + ("" if addr in ("0.0.0.0", "*", "::") else f" on {addr}")
            public.append(label)
            if port in DB_PORTS and addr in ("0.0.0.0", "*", "::"):
                dbs.append(f"{DB_PORTS[port]} ({port})")
        else:
            local_only += 1
    out = []
    if dbs:
        out.append(F("listening", "SEC-CONT-9", "fail", f"listening on every interface: {', '.join(sorted(set(dbs)))}. "
                     "A database or admin API is never on all interfaces"))
    public = sorted(set(public), key=lambda x: (x.split("/")[1][:3], int(x.split("/")[0])))
    ev = (f"listening beyond localhost: {', '.join(public) or 'nothing'}"
          + (f", plus {high_udp} high UDP ports" if high_udp else "") + f"; {local_only} on localhost only"
          + ("" if have_proc else " (process names need root)"))
    out.append(F("listening", "SEC-FW-7", "ok", ev + ". Check from outside what really answers (SEC-FW-7)"))
    return out


def proc_net_rows(base="/proc/net"):
    """Listening TCP and bound UDP sockets from /proc/net when `ss` is missing (no process names)."""
    import struct
    rows = []
    for proto, fname, want in (("tcp", "tcp", "0A"), ("tcp", "tcp6", "0A"), ("udp", "udp", "07"), ("udp", "udp6", "07")):
        try:
            lines = read(os.path.join(base, fname)).splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            f = line.split()
            if len(f) < 4 or f[3] != want:
                continue
            hexaddr, hexport = f[1].split(":")
            raw = bytes.fromhex(hexaddr)
            if len(raw) == 4:
                addr = socket.inet_ntop(socket.AF_INET, raw[::-1])
            else:
                addr = socket.inet_ntop(socket.AF_INET6, b"".join(struct.pack("<I", w) for w in struct.unpack(">4I", raw)))
            rows.append((proto, addr, int(hexport, 16), ""))
    return rows


def check_listening():
    args = ["ss", "-Htlnu"] + (["-p"] if is_root() else [])
    rc, out, err = run(args)
    if rc == 127 and os.path.exists("/proc/net/tcp"):
        return listening_findings(proc_net_rows(), False)
    if rc != 0:
        return [F("listening", "SEC-FW-7", "unknown", f"ss failed: {first_line(err) or rc}")]
    return listening_findings(parse_ss(out), is_root())


# ---------------------------------------------------------------- firewall
def check_firewall():
    if not is_root():
        return [F("firewall", "SEC-FW-7", "unknown", "reading the firewall needs root (the sudo rule for the helper is missing)")]
    out = []
    what = []
    rc, ufw, _ = run(["ufw", "status"])
    if rc == 0 and "Status: active" in ufw:
        what.append("ufw active")
    rc, nft, _ = run(["nft", "list", "ruleset"])
    input_drop = False
    if rc == 0 and nft.strip():
        for m in re.finditer(r"chain \S+ \{[^}]*?hook input[^}]*?policy (\w+)", nft, re.S):
            input_drop = input_drop or m.group(1) == "drop"
        what.append("nftables input policy drop" if input_drop else "nftables rules loaded")
    rc, ipt, _ = run(["iptables", "-S", "INPUT"])
    if rc == 0:
        if re.search(r"^-P INPUT (DROP|REJECT)", ipt, re.M):
            input_drop = True
            what.append("iptables INPUT policy DROP")
        elif len([l for l in ipt.splitlines() if l.startswith("-A INPUT")]) > 0:
            what.append("iptables INPUT rules")
    if "ufw active" in what:
        input_drop = True
    if not what:
        out.append(F("firewall", "SEC-FW-7", "warn", "no firewall loaded (no ufw, no nftables or iptables INPUT rules): every listening port is open; arm a rollback before changing it (SEC-FW-1)"))
    elif input_drop:
        out.append(F("firewall", "SEC-FW-7", "ok", "; ".join(what)))
    else:
        out.append(F("firewall", "SEC-FW-7", "warn", "; ".join(what) + ", but INPUT does not default to deny"))
    rc, ps, _ = run(["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"])
    if rc == 0:
        pub = []
        for line in ps.splitlines():
            name, _, ports = line.partition("\t")
            for m in re.finditer(r"(0\.0\.0\.0|\[::\]|:::?):(\d+)->", ports):
                pub.append(f"{name}:{m.group(2)}")
        if pub:
            rc2, du, _ = run(["iptables", "-S", "DOCKER-USER"])
            filtered = rc2 == 0 and len([l for l in du.splitlines() if l.startswith("-A DOCKER-USER") and "RETURN" not in l]) > 0
            out.append(F("firewall", "SEC-FW-4", "ok" if filtered else "warn",
                         f"Docker publishes on every interface: {', '.join(sorted(set(pub))[:15])}"
                         + (" (DOCKER-USER has rules)" if filtered else ". Those ports skip ufw and INPUT: publish on one IP or filter in DOCKER-USER")))
    return out


# ---------------------------------------------------------------- fail2ban
def check_fail2ban():
    if not is_root():
        return [F("fail2ban", "SEC-HARD-2", "unknown", "needs root (the sudo rule for the helper is missing)")]
    rc, out, err = run(["fail2ban-client", "status"])
    if rc == 127:
        return [F("fail2ban", "SEC-HARD-2", "warn", "fail2ban is not installed")]
    if rc != 0:
        return [F("fail2ban", "SEC-HARD-2", "warn", f"fail2ban is installed but not answering: {first_line(err or out)}")]
    m = re.search(r"Jail list:\s*(.*)", out)
    jails = [j.strip() for j in (m.group(1) if m else "").split(",") if j.strip()]
    if not jails:
        return [F("fail2ban", "SEC-HARD-2", "warn", "fail2ban runs with no jail")]
    banned = {}
    try:
        db = sqlite3.connect("file:/var/lib/fail2ban/fail2ban.sqlite3?mode=ro", uri=True, timeout=5)
        for jail, n in db.execute("SELECT jail, COUNT(*) FROM bans GROUP BY jail"):
            banned[jail] = n
        db.close()
    except sqlite3.Error:
        banned = None
    quiet = [j for j in jails if banned is not None and not banned.get(j)]
    ev = f"jails: {', '.join(jails)}"
    if banned is not None:
        # fail2ban purges old bans (dbpurgeage, one day by default): a zero is "none recorded lately", not "never"
        ev += "; bans still in the database (it keeps about a day by default): " + ", ".join(f"{j} {banned.get(j, 0)}" for j in jails)
    if "sshd" in quiet:
        _, st, _ = run(["fail2ban-client", "status", "sshd"])
        if jail_reads_missing_file(st):
            return [F("fail2ban", "SEC-HARD-2", "warn", ev + ". The sshd jail reads a log file that does not exist: "
                      "on Debian 12/13 it needs backend = systemd or it is decorative")]
    if quiet:
        ev += ". No recent ban on a quiet host proves nothing either way: test that it bans when you set it up (SEC-HARD-3)"
    return [F("fail2ban", "SEC-HARD-3", "ok", ev)]


def jail_reads_missing_file(status_text, exists=os.path.exists):
    """`fail2ban-client status <jail>` text -> True when the jail watches log files and none of them exists."""
    m = re.search(r"File list:[ \t]*(.*)", status_text or "")
    files = m.group(1).split() if m else []
    return bool(files) and not any(exists(f) for f in files)


# ---------------------------------------------------------------- logins
# sshd also logs text an unauthenticated remote party chooses (the user name in "Invalid user ..."), so a login line is
# accepted only when the WHOLE line has the shape of sshd's own record, after the plain journal form (-o cat) or the
# syslog prefix of auth.log (old or ISO time, host, sshd[pid]:), with a restricted user and address. Nothing is ever
# taken from the middle of a line.
_PREFIX = (r"(?:(?:[A-Z][a-z]{2} [ 0-9][0-9] [0-9]{2}:[0-9]{2}:[0-9]{2}"
           r"|[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[+-][0-9]{2}:[0-9]{2}|Z))"
           r" [A-Za-z0-9._-]{1,255} sshd(?:-session)?(?:\[[0-9]{1,8}\])?: )?")
ACCEPT_HEAD = re.compile("^" + _PREFIX + "Accepted ")
ACCEPT = re.compile("^" + _PREFIX + r"Accepted ([A-Za-z0-9/-]{1,40}) for ([A-Za-z0-9._@-]{1,64}) from ([0-9A-Fa-f:.]{2,45})"
                    r"(?:%[A-Za-z0-9._-]{1,16})?"   # an IPv6 zone id (fe80::1%eth0): not part of the address, never kept
                    r" port [0-9]{1,5}(?: ssh[12])?(?::[ -~]{0,200})?$")


def parse_logins(text, stats=None):
    """sshd log text -> {(user, address, method): count}. stats["skipped"] counts lines that start like an accepted
    login but do not have the strict shape (odd characters in the user name, for instance)."""
    seen = {}
    for line in text.split("\n"):   # NOT splitlines(): it also splits on \x0b, \x0c, \x85, U+2028 and a user name may carry them
        m = ACCEPT.match(line.rstrip("\r"))
        if not m:
            if stats is not None and ACCEPT_HEAD.match(line):
                stats["skipped"] = stats.get("skipped", 0) + 1
            continue
        k = (m.group(2), m.group(3), m.group(1))
        seen[k] = seen.get(k, 0) + 1
    return seen


def login_findings(seen, skipped=0, source="journal", undated=0, cut=False):
    if not seen:
        return [F("logins", "SEC-HARD-4", "unknown", "no accepted SSH login in the log, not even this audit's own: the SSH log is "
                  "not readable here (journal not kept, or sshd logs elsewhere)")]
    rows = sorted(seen.items(), key=lambda kv: -kv[1])
    shown = rows[:8]   # the evidence is capped, so the count of the rest goes first, where the cap cannot cut it
    head = plural(len(rows), "source") + (f", the {len(shown)} busiest shown" if len(rows) > len(shown) else "")
    if skipped:
        head += f", {plural(skipped, 'line')} with an unusual shape left out"
    if undated:
        head += f", {plural(undated, 'line')} without a readable date left out"
    if cut:
        head += ", only the newest 4 MiB of each log file read"
    ev = head + ": " + "; ".join(f"{u}{' (this audit)' if u == 'hostcare' else ''} from {ip} by {meth} ×{n}"
                                 for (u, ip, meth), n in shown)
    users = {u for (u, _, _) in seen}
    pw = {u for (u, _, meth) in seen if meth in ("password", "keyboard-interactive/pam")}
    status, note = "ok", ". Check every source is known (SEC-DET-2)"
    if "root" in users:
        status, note = "warn", ". root logged in over SSH (SEC-POL-1)"
    elif pw:
        status, note = "warn", f". Password logins: {', '.join(sorted(pw))} (SEC-POL-2)"
    return [F("logins", "SEC-DET-2" if status == "ok" else "SEC-DET-1", status, f"accepted in the last 7 days ({source}), {ev}{note}")]


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_TS_OLD = re.compile(r"^([A-Z][a-z]{2}) ([ 0-9][0-9]) ([0-9]{2}):([0-9]{2}):([0-9]{2}) ")
_TS_ISO = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2}) ")


def line_time(line, now):
    """Epoch seconds of the syslog timestamp that starts an auth.log line, or None. The old form ('Nov  9 06:05:40')
    has no year: this year, or the previous one when that would put the line more than a day in the future."""
    m = _TS_ISO.match(line)
    try:
        if m:
            y, mo, d, h, mi, sec = (int(x) for x in m.groups()[:6])
            z = m.group(7)
            off = 0 if z == "Z" else (1 if z[0] == "+" else -1) * (int(z[1:3]) * 3600 + int(z[4:6]) * 60)
            tz = datetime.timezone(datetime.timedelta(seconds=off))
            return datetime.datetime(y, mo, d, h, mi, sec, tzinfo=tz).timestamp()
        m = _TS_OLD.match(line)
        if m and m.group(1) in _MONTHS:
            mo, d, h, mi, sec = _MONTHS.index(m.group(1)) + 1, int(m.group(2)), *(int(x) for x in m.groups()[2:])
            year = datetime.datetime.fromtimestamp(now).year
            for y in (year, year - 1):
                try:
                    t = time.mktime((y, mo, d, h, mi, sec, 0, 0, -1))
                except (ValueError, OverflowError):
                    continue
                if t <= now + 86400 and datetime.datetime.fromtimestamp(t).day == d:
                    return t
            return None
    except (ValueError, OverflowError, OSError):
        return None
    return None


def recent_lines(text, now, days=7):
    """auth.log text -> (the lines dated inside the last `days`, how many accepted-login-looking lines had no readable date)."""
    cutoff, keep, undated = now - days * 86400, [], 0
    for line in text.split("\n"):
        t = line_time(line, now)
        if t is None:
            if ACCEPT_HEAD.match(line):
                undated += 1
        elif t >= cutoff:
            keep.append(line)
    return "\n".join(keep), undated


def check_logins(now=None):
    now = time.time() if now is None else now
    rc, out, err = run_grep(["journalctl", "-u", "ssh", "-u", "sshd", "-u", "ssh@*", "-u", "sshd@*", "--since", "-7d", "-o", "cat",
                             "--no-pager"], "Accepted ", timeout=60)
    jstats = {}
    seen = parse_logins(out, jstats) if rc == 0 else {}
    if seen:
        return login_findings(seen, jstats.get("skipped", 0), "journal", cut=getattr(run_grep, "truncated", False))
    text, cut, read_any = "", False, False
    for path in sorted(glob.glob("/var/log/auth.log*"))[:2]:
        if path.endswith(".gz"):
            continue
        try:
            part, was_cut = read_tail(path)
        except OSError:
            continue
        read_any = True
        text += part + "\n"
        cut = cut or was_cut
    if not read_any:
        if rc != 0:
            return [F("logins", "SEC-DET-1", "unknown", f"no journal and no auth.log readable: {first_line(err)}")]
        if not out.strip() and not is_root():   # an empty journal and no readable auth.log: this account may simply not see the logs
            return [F("logins", "SEC-DET-1", "unknown", "the journal shows nothing to this account and no auth.log is readable: needs root or the adm group")]
        return login_findings({}, jstats.get("skipped", 0))
    astats = {}
    text, undated = recent_lines(text, now)
    seen = parse_logins(text, astats)
    if not seen:
        return login_findings({}, 0)
    return login_findings(seen, astats.get("skipped", 0), "from auth.log", undated, cut)


# ---------------------------------------------------------------- containers
def container_findings(inspected, not_inspected=0):
    bad, warn, nnp, n = [], [], [], 0
    for c in inspected:
        n += 1
        name = (c.get("Name") or "?").lstrip("/")
        hc = c.get("HostConfig") or {}
        mounts = [m.get("Source", "") for m in (c.get("Mounts") or [])]
        if hc.get("Privileged"):
            bad.append(f"{name} privileged")
        if any(s.endswith("docker.sock") for s in mounts):
            bad.append(f"{name} mounts docker.sock (root on the host)")
        if hc.get("NetworkMode") == "host":
            warn.append(f"{name} network host")
        caps = [x for x in (hc.get("CapAdd") or []) if x]
        if caps:
            warn.append(f"{name} adds {','.join(caps)}")
        if not any("no-new-privileges" in s for s in (hc.get("SecurityOpt") or [])):
            nnp.append(name)
    if not n:
        return [F("containers", "SEC-CONT-1", "ok", "no running container")]
    out = []
    if nnp:
        warn.append(f"{len(nnp)} of {n} without no-new-privileges: {', '.join(sorted(nnp)[:10])}" + (" …" if len(nnp) > 10 else ""))
    if bad:
        out.append(F("containers", "SEC-CONT-6", "fail", "; ".join(bad)))
    if warn:
        out.append(F("containers", "SEC-CONT-1", "warn", "; ".join(warn[:15]) + (" …" if len(warn) > 15 else "")))
    if not bad and not warn:
        out.append(F("containers", "SEC-CONT-1", "ok", f"{plural(n, 'container')}: none privileged, all with no-new-privileges"))
    if not_inspected:
        out = [f for f in out if f["status"] != "ok"]
        out.append(F("containers", "SEC-CONT-1", "unknown", f"could not inspect {not_inspected} of {n + not_inspected} running "
                     f"containers (only the first {n} are looked at)" + ("" if any(f["status"] != "ok" for f in out) else
                     f"; those {n} show nothing privileged")))
    return out


MAX_INSPECT = 60


DOCKER_SOCKS = ("/var/run/docker.sock", "/run/docker.sock")


def check_containers():
    rc, ids, err = run(["docker", "ps", "-q"])
    if rc == 127:
        if any(os.path.exists(p) for p in DOCKER_SOCKS):   # a daemon is there but this PATH does not find its CLI
            return [F("containers", "SEC-CONT-1", "unknown", "docker is running but its CLI was not found: the containers were not looked at")]
        return []   # no docker: nothing to say
    if rc != 0:
        why = "needs root or the docker group" if denied(err) else first_line(err)
        return [F("containers", "SEC-CONT-1", "unknown", f"docker ps failed: {why}")]
    ids = ids.split()
    if not ids:
        return container_findings([])
    rc, js, err = run(["docker", "inspect"] + ids[:MAX_INSPECT])
    if rc != 0:
        return [F("containers", "SEC-CONT-1", "unknown",
                  f"docker inspect failed, {plural(len(ids), 'running container')} not inspected: {first_line(err) or rc}")]
    try:
        return container_findings(json.loads(js), max(0, len(ids) - MAX_INSPECT))
    except ValueError:
        return [F("containers", "SEC-CONT-1", "unknown",
                  f"docker inspect unreadable, {plural(len(ids), 'running container')} not inspected: {first_line(err)}")]


CHECKS = [("os", check_os), ("updates", check_updates), ("reboot", check_reboot), ("unattended", check_unattended),
          ("stale_libs", check_stale_libs), ("ssh", check_ssh), ("accounts", check_accounts),
          ("listening", check_listening), ("firewall", check_firewall), ("fail2ban", check_fail2ban),
          ("logins", check_logins), ("containers", check_containers)]


def main(argv):
    if argv:
        sys.stderr.write("audit_root.py takes no arguments.\n")
        return 2
    findings = []
    for name, fn in CHECKS:
        try:
            findings += fn()
        except Exception as exc:   # one broken check must not hide the others
            findings.append(F(name, "", "unknown", f"check error: {type(exc).__name__}: {exc}"))
    print(json.dumps({"version": VERSION, "host": socket.gethostname(), "root": is_root(),
                      "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "findings": findings},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
