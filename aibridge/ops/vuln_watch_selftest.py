#!/usr/bin/env python3
"""Offline test of vuln_watch.py: Debian version order (cross-checked with dpkg when present), matching against a fake KEV
catalog and Debian tracker, dedupe, state transitions, due dates, the manual product table, feed caching (304, stale cache),
the read-only API guard and token hygiene, against a fake Zabbix served from a local thread. No network.
Stdlib only: python3 -I ops/vuln_watch_selftest.py"""
import contextlib, datetime, gzip, http.server, io, json, os, shutil, subprocess, sys, tempfile, threading, time, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vuln_watch as vw

os.environ["no_proxy"] = "*"
for k in list(os.environ):
    if k.startswith("VULNWATCH_"):
        del os.environ[k]
TOKEN = "tok-3f9a1c7e5b2d4a60-secret"
TMP = tempfile.mkdtemp(prefix="vw-")
fails, ALL_OUT = [], []
SENT = []
_real_notify = vw.notify_send
vw.notify_send = lambda text: SENT.append(text) or True


def check(name, ok, detail=""):
    if ok:
        print(f"ok {name}")
    else:
        fails.append(name)
        print(f"FAIL {name} {detail}")


# ------------------------------------------------------------------ the fake world

class World:
    def __init__(self):
        self.reset()
        self.hits = {"zbx": 0, "kev": 0, "tracker": 0, "kev304": 0, "tracker304": 0}
        self.calls = []
        self.down = False
        self.user_type = "1"          # None: the answer carries no `type` at all
        self.etag, self.lm = '"kev-1"', "lm-1"

    def reset(self):
        self.hosts, self.items, self.vals, self.kev, self.tracker, self.n = [], {}, {}, [], {}, 0

    def add_host(self, hostid, name, os_json=None, shards=None, apt=None, shard_age=60, apt_age=60, os_inv=""):
        self.hosts.append({"hostid": hostid, "host": name.lower(), "name": name, "inventory": {"os": os_inv}})
        self.items[hostid] = {}
        if os_json is not None:
            self.put(hostid, vw.KEY_OS, json.dumps(os_json), 60)
        for n, text in enumerate(shards or []):
            self.put(hostid, vw.KEY_SHARDS[n], text, shard_age)
        if apt is not None:
            self.put(hostid, vw.KEY_APT, json.dumps(apt), apt_age)

    def put(self, hostid, key, value, age_s):
        self.n += 1
        clock = int(time.time() - age_s)
        self.items[hostid][key] = {"itemid": str(self.n), "hostid": hostid, "key_": key, "value_type": "4",
                                   "lastclock": str(clock), "state": "0", "error": ""}
        self.vals[str(self.n)] = (clock, value)


S = World()
DEB13 = {"os_type": "linux", "product_name": "Debian GNU/Linux", "major": 13, "version_pretty": "Debian GNU/Linux 13 (trixie)"}


def shards(rows, truncated=False):
    """Four shard texts for rows (binary, version, source, source_version), round-robin."""
    out = []
    for n in range(4):
        mine = rows[n::4]
        lines = [f"#vw.dpkg shard={n} of=4 count={len(mine)}"] + ["\t".join(r) for r in mine]
        if truncated and n == 0:
            lines.append("#truncated")
        out.append("\n".join(lines) + "\n")
    return out


def apt(**kw):
    return {"pending": 3, "security": 1, "security_pkgs": ["libfoo"], "reboot_required": False, "lists_age_s": 3600,
            "kernel_running": "6.12.1-amd64", "kernel_installed": "6.12.1-1", "kernel_installed_pkg": "linux-image-6.12.1-amd64", **kw}


def day(delta):
    return str(datetime.date.today() + datetime.timedelta(days=delta))


def kev_entry(cve, vendor, product, added, due):
    return {"cveID": cve, "vendorProject": vendor, "product": product, "vulnerabilityName": "x", "dateAdded": added, "dueDate": due,
            "knownRansomwareCampaignUse": "Unknown"}


def rel(status, fixed=None):
    r = {"status": status, "repositories": {}, "urgency": "medium"}
    if fixed is not None:
        r["fixed_version"] = fixed
    return r


def main_world():
    S.reset()
    S.kev = [kev_entry("CVE-2099-0001", "Libfoo", "Libfoo", day(-5), day(20)),
             kev_entry("CVE-2099-0002", "Barapp", "Barapp", day(-5), day(3)),
             kev_entry("CVE-2099-0003", "Notaff", "Notaff", day(-5), day(20)),
             kev_entry("CVE-2099-0004", "Cnsrc", "Cnsrc", day(-5), day(20)),
             kev_entry("CVE-2099-0005", "Google", "Chromium V8", day(-2), day(20)),
             kev_entry("CVE-2099-0006", "Google", "Chromium Skia", day(-100), day(-80))]
    S.tracker = {
        "libfoo": {"CVE-2099-0001": {"releases": {"trixie": rel("resolved", "1.2-1+deb13u1"), "bookworm": rel("resolved", "1.1-1")}},
                   "CVE-2000-0001": {"releases": {"trixie": rel("open")}}},          # not in KEV: ignored
        "barapp": {"CVE-2099-0002": {"releases": {"trixie": rel("open")}}},
        "notaff": {"CVE-2099-0003": {"releases": {"trixie": rel("resolved", "0")}}},
        "cnsrc": {"CVE-2099-0004": {"releases": {"bookworm": rel("open")}}},          # no trixie entry
    }
    foo, bar = ("libfoo", "1.2-1", "libfoo", "1.2-1"), ("barapp", "2.0-1", "barapp", "2.0-1")
    notaff, cns = ("notaff", "3.0-1", "notaff", "3.0-1"), ("cnsrc", "1.0-1", "cnsrc", "1.0-1")
    chrome = ("google-chrome-stable", "120.0.1", "", "")
    S.add_host("1", "deb13-a", DEB13, shards([foo, bar, notaff, cns, chrome, ("bash", "5.2-1", "bash", "5.2-1")]), apt())
    S.add_host("2", "deb13-b", DEB13, shards([("libfoo", "1.2-1+deb13u1", "libfoo", "1.2-1+deb13u1"), notaff]), apt())
    S.add_host("3", "ubu-c", {"product_name": "Ubuntu", "version_pretty": "Ubuntu 24.04 LTS"}, shards([foo]), apt())
    S.add_host("4", "blind-d", DEB13, shards([foo, bar]), apt(), shard_age=10 * 86400, apt_age=10 * 86400)
    S.add_host("5", "partial-e", {"product_name": "Debian GNU/Linux", "major": 13}, shards([foo, notaff], truncated=True), apt())
    S.add_host("6", "bare-f")


def set_a_packages(rows):
    for n, text in enumerate(shards(rows)):
        S.put("1", vw.KEY_SHARDS[n], text, 60)


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body=b"", headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        which = "kev" if self.path.startswith("/kev") else "tracker"
        S.hits[which] += 1
        if S.down:
            return self._send(500)
        if which == "kev":
            body, validators = json.dumps({"title": "t", "vulnerabilities": S.kev}).encode(), (("ETag", S.etag),)
            if self.headers.get("If-None-Match") == S.etag:
                S.hits["kev304"] += 1
                return self._send(304)
        else:
            body, validators = json.dumps(S.tracker).encode(), (("Last-Modified", S.lm),)
            if self.headers.get("If-Modified-Since") == S.lm:
                S.hits["tracker304"] += 1
                return self._send(304)
        self._send(200, gzip.compress(body), (("Content-Type", "application/json"), ("Content-Encoding", "gzip"), *validators))

    def do_POST(self):
        if self.path == "/redir.php":                       # a frontend that moved: answers with a redirect
            S.hits["redir"] = S.hits.get("redir", 0) + 1
            self.rfile.read(int(self.headers["Content-Length"]))
            return self._send(302, b"", (("Location", BASE + "/api_jsonrpc.php"),))
        S.hits["zbx"] += 1
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        m, p = req["method"], req["params"]
        S.calls.append(m)
        ok = self.headers.get("Authorization") == "Bearer " + TOKEN

        def reply(result=None, error=None):
            d = {"jsonrpc": "2.0", "id": 1}
            d.update({"error": {"code": -32500, "message": error, "data": ""}} if error else {"result": result})
            self._send(200, json.dumps(d).encode(), (("Content-Type", "application/json"),))

        if m == "user.checkAuthentication":
            if p.get("token") != TOKEN:
                return reply(error="Session terminated")
            # roleid deliberately differs from type: role ids are a different scale (4 is the default Super admin role)
            return reply({"type": S.user_type, "roleid": "4"} if S.user_type is not None else {"roleid": "1"})
        if not ok:
            return reply(error="Not authorised")
        if m == "hostgroup.get":
            return reply([{"groupid": "9", "name": n} for n in p["filter"]["name"] if n == "Servers"])
        if m == "host.get":
            return reply(S.hosts)
        if m == "item.get":
            return reply([it for h in p["hostids"] for k, it in S.items.get(h, {}).items() if k in p["filter"]["key_"]])
        if m == "history.get":
            clock, val = S.vals[p["itemids"][0]]
            return reply([{"itemid": p["itemids"][0], "clock": str(clock), "value": val}] if clock >= p["time_from"] else [])
        reply(error=f"unexpected method {m}")


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"
os.environ["VULNWATCH_KEV_URL"], os.environ["VULNWATCH_TRACKER_URL"] = BASE + "/kev.json", BASE + "/tracker.json"
ENVF = os.path.join(TMP, "ops.env")
open(ENVF, "w").write(f'# test\nVULNWATCH_ZBX_URL="{BASE}"\nVULNWATCH_ZBX_TOKEN={TOKEN}\nVULNWATCH_GROUPS=Servers\n')
os.environ["OPS_ENV"] = ENVF
STATES = []


def new_state():
    d = tempfile.mkdtemp(prefix="st-", dir=TMP)
    shutil.rmtree(d)                       # let vuln_watch create it, with its own mode
    STATES.append(d)
    os.environ["VULNWATCH_STATE"] = d
    return d


def run(*args):
    """-> (exit code, stdout, stderr, message sent or None)"""
    out, err, n = io.StringIO(), io.StringIO(), len(SENT)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = vw.main(list(args))
    ALL_OUT.extend([out.getvalue(), err.getvalue()])
    return code, out.getvalue(), err.getvalue(), (SENT[-1] if len(SENT) > n else None)


def finding_lines(msg):
    return [l for l in (msg or "").splitlines() if "CVE-" in l]


# ------------------------------------------------------------------ 1. debcmp
TABLE = [("1.0~rc1", "1.0", -1), ("1:0.1", "2.0", 1), ("1.0-1", "1.0-1+deb12u1", -1), ("2.30-1", "2.30-1+b1", -1),
         ("1.0a", "1.0", 1), ("1.0", "1.0+", -1), ("1.0", "1.0", 0), ("1.10", "1.9", 1), ("1.0~~", "1.0~", -1),
         ("1.0~", "1.0", -1), ("2:1.0", "1:9.9", 1), ("1.0-0", "1.0", 0), ("007", "7", 0), ("0.9.8-1", "0.9.8", 1),
         ("1.0-1~bpo12+1", "1.0-1", -1), ("1.2.3-1ubuntu1", "1.2.3-1", 1), ("1.0-1", "1.0-1.1", -1), ("1.0.1", "1.0", 1),
         ("1.0a-1", "1.0-1", 1), ("3.1.2+dfsg1-1+deb13u1", "3.1.2+dfsg1-1", 1), ("1:1.0-1", "1.0-1", 1), ("1.0-2", "1.0-10", -1)]
bad = [(a, b, w) for a, b, w in TABLE if vw.debcmp(a, b) != w or vw.debcmp(b, a) != -w]
check("debcmp table", not bad, str(bad))
if os.path.exists("/usr/bin/dpkg"):
    bad = []
    for a, b, w in TABLE:
        op = {-1: "lt", 0: "eq", 1: "gt"}[w]
        if subprocess.run(["/usr/bin/dpkg", "--compare-versions", a, op, b]).returncode != 0:
            bad.append((a, op, b))
    check("debcmp agrees with dpkg --compare-versions", not bad, str(bad))
else:
    print("skip debcmp dpkg cross-check (no /usr/bin/dpkg)")

# ------------------------------------------------------------------ 2. not configured, admin token, allowlist
main_world()
new_state()
saved = os.environ["OPS_ENV"]
os.environ["OPS_ENV"] = os.path.join(TMP, "missing.env")
before = dict(S.hits)
code, out, err, msg = run("run")
check("not configured: exit 0, says so, no request", code == 0 and "not configured" in out and S.hits == before and msg is None)
os.environ["OPS_ENV"] = saved
for t in ("3", "2", None):
    S.user_type, S.calls = t, []
    code, out, err, msg = run("run")
    check(f"admin or unreadable token (type {t}) refused with exit 2", code == 2 and "read-only" in err and "host.get" not in S.calls and msg is None)
S.user_type = "1"
before = dict(S.hits)
try:
    vw.api({"VULNWATCH_ZBX_URL": "http://zabbix.invalid/", "VULNWATCH_ZBX_TOKEN": TOKEN}, "host.get", {})
    check("a cleartext non-loopback URL is refused", False)
except vw.ApiError as e:
    check("a cleartext non-loopback URL is refused", "https" in str(e) and TOKEN not in str(e) and S.hits == before)
try:
    vw.api({"VULNWATCH_ZBX_URL": BASE + "/redir.php", "VULNWATCH_ZBX_TOKEN": TOKEN}, "host.get", {})
    check("a redirect is not followed", False)
except vw.ApiError as e:
    check("a redirect is not followed, the token is not re-sent", "302" in str(e) and S.hits.get("redir") == 1 and S.hits["zbx"] == before["zbx"], str(e))
before = dict(S.hits)
try:
    vw.api({"VULNWATCH_ZBX_URL": BASE, "VULNWATCH_ZBX_TOKEN": TOKEN}, "host.update", {"hostid": "1"})
    check("allowlist rejects host.update", False)
except vw.ApiError:
    check("allowlist rejects host.update", S.hits == before)
bad = [m for m in ("host.delete", "item.create", "user.update", "history.push", "configuration.import") if m in vw.ALLOWED]
check("allowlist has only read methods", not bad and set(vw.ALLOWED) == {"user.checkAuthentication", "hostgroup.get", "host.get", "item.get", "history.get"})

# ------------------------------------------------------------------ 3. dry run, first run
st1 = new_state()
code, out, err, msg = run("run", "--dry-run")
check("dry run prints the message, sends nothing, writes no state", code == 0 and "CVE-2099-0001" in out and msg is None
      and not os.path.exists(os.path.join(st1, "state.json")))
code, out, err, msg = run("run")
lines = finding_lines(msg)
check("first run sends exactly one message", code == 0 and len(SENT) == 1 and msg is not None)
check("header counts", msg.startswith("🛡️ vuln_watch: ") and "nuevas, 0 corregidas" in msg.splitlines()[0])
check("VULN_FIX found with fixed version", any("deb13-a: CVE-2099-0001 libfoo 1.2-1 → 1.2-1+deb13u1 (KEV, vence" in l for l in lines), msg)
check("AFFECTED (open) reported as no fix", any("deb13-a: CVE-2099-0002 barapp 2.0-1 → sin parche" in l for l in lines))
check("patched host not reported", not any(l.startswith("deb13-b:") for l in lines))
check("fixed_version 0 skipped", "CVE-2099-0003" not in msg)
check("codename without a tracker entry skipped", "CVE-2099-0004" not in msg)
check("KEV-only reduction: CVE outside KEV ignored", "CVE-2000-0001" not in msg)
check("Ubuntu is unsupported, not alerted", not any(l.startswith("ubu-c:") for l in lines))
check("partial host (truncated shard) still matched", any(l.startswith("partial-e: CVE-2099-0001") for l in lines))
check("major-number fallback gives the codename", any("partial-e" in l for l in lines))
check("CHECK via the product table for a recent KEV entry", any("deb13-a: CVE-2099-0005 google-chrome-stable 120.0.1 → verificar" in l for l in lines))
check("no CHECK for an old KEV entry", "CVE-2099-0006" not in msg)
check("blind host (old shards) mentioned, others not", "sin inventario reciente: blind-d" in msg and "deb13-b" not in msg.splitlines()[-1])
check("blind host is not matched", not any(l.startswith("blind-d:") for l in lines))
check("due soon in the first message is not announced twice", msg.count("CVE-2099-0002") == 1)
sm = json.load(open(os.path.join(st1, "state.json")))
check("state keyed host|cve|source", "deb13-a|CVE-2099-0001|libfoo" in sm["findings"] and sm["findings"]["deb13-a|CVE-2099-0002|barapp"]["notified_due"] is True
      and sm["blind"] == ["blind-d"], str(sorted(sm["findings"])))
check("state dir is private", oct(os.stat(st1).st_mode & 0o777) == "0o700" and oct(os.stat(os.path.join(st1, "state.json")).st_mode & 0o777) == "0o600")

# ------------------------------------------------------------------ 4. status
code, out, err, msg = run("status")
check("status lists every kind of host", code == 0 and "deb13-a:" in out and "trixie" in out and "ubu-c: unsupported in this phase" in out
      and "blind-d: BLIND" in out and "bare-f: not inventoried" in out and "partial-e:" in out and "partial (truncated shard)" in out
      and "open findings: 4" in out, out)
code, out, err, msg = run("feeds")
check("feeds reports both caches", code == 0 and "kev: fetched" in out and "tracker: fetched" in out and "reduced tracker: built" in out)

# ------------------------------------------------------------------ 5. dedupe and the 304 path
orig_reduce = vw.reduce_tracker
vw.reduce_tracker = lambda *a: (_ for _ in ()).throw(AssertionError("reduction recomputed"))
h0 = dict(S.hits)
code, out, err, msg = run("run")
vw.reduce_tracker = orig_reduce
check("second run: no message", code == 0 and msg is None and len(SENT) == 1)
check("304 for both feeds, reduced cache reused",
      S.hits["kev304"] == h0["kev304"] + 1 and S.hits["tracker304"] == h0["tracker304"] + 1)

# ------------------------------------------------------------------ 6. AFFECTED becomes VULN_FIX
S.tracker["barapp"]["CVE-2099-0002"]["releases"]["trixie"] = rel("resolved", "2.0-1+deb13u1")
S.lm = "lm-2"
code, out, err, msg = run("run")
check("AFFECTED -> VULN_FIX is announced once", msg is not None and "🩹 deb13-a: CVE-2099-0002 barapp 2.0-1 → 2.0-1+deb13u1" in msg and len(finding_lines(msg)) == 1, str(msg))
code, out, err, msg = run("run")
check("and not repeated", msg is None)

# ------------------------------------------------------------------ 7. due date inside 7 days, once
real_today = vw.today
vw.today = lambda: real_today() + datetime.timedelta(days=15)
code, out, err, msg = run("run")
check("due within 7 days: one extra notice", msg is not None and msg.count("⏰") == 2 and "CVE-2099-0001" in msg
      and "deb13-a: CVE-2099-0001" in msg and "partial-e: CVE-2099-0001" in msg, str(msg))
code, out, err, msg = run("run")
vw.today = real_today
check("due notice is not repeated", msg is None)

# ------------------------------------------------------------------ 8. fix applied
set_a_packages([("libfoo", "1.2-1+deb13u1", "libfoo", "1.2-1+deb13u1"), ("barapp", "2.0-1", "barapp", "2.0-1"),
                ("notaff", "3.0-1", "notaff", "3.0-1"), ("cnsrc", "1.0-1", "cnsrc", "1.0-1"), ("bash", "5.2-1", "bash", "5.2-1")])
code, out, err, msg = run("run")
check("fix applied: one ✅ line", msg is not None and "✅ deb13-a: CVE-2099-0001 libfoo corregido" in msg and "0 nuevas, 1 corregidas" in msg, str(msg))
check("a CHECK that goes away (package removed) is silent", "CVE-2099-0005" not in msg)
code, out, err, msg = run("run")
check("fixed finding does not come back", msg is None)

# ------------------------------------------------------------------ 9. a host that goes blind keeps its findings
S.put("1", vw.KEY_APT, json.dumps(apt()), 3 * 86400)
code, out, err, msg = run("run")
check("newly blind host is mentioned, not reported as fixed", msg is not None and "sin inventario reciente: deb13-a" in msg and "✅" not in msg, str(msg))
code, out, err, msg = run("run")
check("blind again: not repeated", msg is None)
S.put("1", vw.KEY_APT, json.dumps(apt()), 60)
code, out, err, msg = run("run")
check("recovered host: its findings were kept, nothing new", msg is None
      and "deb13-a|CVE-2099-0002|barapp" in json.load(open(os.path.join(st1, "state.json")))["findings"])
S.put("1", vw.KEY_SHARDS[2], "", 60)
code, out, err, msg = run("status")
check("an empty shard makes a host blind", "deb13-a: BLIND (shard 2 has no value" in out, out)

# ------------------------------------------------------------------ 10. cap of 20 lines
S.reset()
S.kev = [kev_entry(f"CVE-2098-{i:04d}", f"V{i}", f"P{i}", day(-90), day(30)) for i in range(25)]
S.tracker = {f"pkg{i}": {f"CVE-2098-{i:04d}": {"releases": {"trixie": rel("open")}}} for i in range(25)}
S.add_host("1", "big-host", DEB13, shards([(f"pkg{i}", "1.0-1", f"pkg{i}", "1.0-1") for i in range(25)]), apt())
S.lm = "lm-3"
S.etag = '"kev-2"'
new_state()
code, out, err, msg = run("run")
check("message capped at 20 lines with a tail", msg is not None and len(finding_lines(msg)) == 20 and "… y 5 más: vuln_watch.py status" in msg
      and msg.splitlines()[0].startswith("🛡️ vuln_watch: 25 nuevas"), str(msg)[-200:])
check("--host limits the run", run("run", "--host", "nope")[0] == 0)

# ------------------------------------------------------------------ 11. network errors and the cache
main_world()
S.etag, S.lm = '"kev-3"', "lm-4"
st_net = new_state()
code, out, err, msg = run("run")
S.down = True
code, out, err, msg = run("run")
check("feeds down, cache fresh: run ok from the cache", code == 0 and "using the cache" in err and msg is None, err)
for name in ("kev", "tracker"):
    p = os.path.join(st_net, name + ".meta.json")
    m = json.load(open(p))
    m["checked"] = time.time() - 8 * 86400
    json.dump(m, open(p, "w"))
code, out, err, msg = run("run")
check("feeds down, cache older than 7 days: exit 1", code == 1 and "no cache younger than 7 days" in err, err)
new_state()
code, out, err, msg = run("run")
check("feeds down, no cache: exit 1", code == 1)
S.down = False

# ------------------------------------------------------------------ 11b. kernel, coverage, hostile input, promotion
def rec_of(lines, codename="trixie", name="h"):
    r = vw.blank_rec({"hostid": "1", "name": name})
    r["codename"] = codename
    r["pkgs"] = vw.parse_shard("\n".join(lines) + "\n")[0]
    return r


def kev_of(*entries):
    return {e["cveID"]: e for e in entries}


KIMG = "linux-image-6.12.116+deb13-amd64\t6.12.116-1\tlinux-signed-amd64\t6.12.116+1"
KHDR_OLD = "linux-headers-6.12.107-common\t6.12.107-1\tlinux\t6.12.107-1"
KHDR_NEW = "linux-headers-6.12.116-common\t6.12.116-1\tlinux\t6.12.116-1"
kcve = kev_of(kev_entry("CVE-2099-1000", "Linux", "Kernel", day(-5), day(20)))


def kred(fixed):
    return {"linux": {"CVE-2099-1000": {"trixie": {"status": "resolved", "fixed_version": fixed}}}}


f = vw.match_host(rec_of([KIMG]), kcve, kred("6.12.117-1"), [], 30)
check("kernel image alone (signed wrapper source) is judged against source linux",
      [(x["source"], x["installed"], x["status"]) for x in f.values()] == [("linux", "6.12.116-1", "VULN_FIX")], str(f))
check("kernel image at the fixed version is clean", not vw.match_host(rec_of([KIMG]), kcve, kred("6.12.116-1"), [], 30))
check("retained old kernel headers do not hold a finding open",
      not vw.match_host(rec_of([KIMG, KHDR_OLD, KHDR_NEW]), kcve, kred("6.12.110-1"), [], 30))
f = vw.match_host(rec_of([KIMG, KHDR_OLD, KHDR_NEW]), kcve, kred("6.12.117-1"), [], 30)
check("the newest installed kernel version is the one reported", [x["installed"] for x in f.values()] == ["6.12.116-1"], str(f))
f = vw.match_host(rec_of(["libfoo\t1.0-1\tlibfoo\t1.0-1", "libfoo-dev\t1.0-0\tlibfoo\t1.0-0"]), kev_of(kev_entry("CVE-2099-1001", "L", "L", day(-5), day(9))),
                  {"libfoo": {"CVE-2099-1001": {"trixie": {"status": "resolved", "fixed_version": "1.0-1"}}}}, [], 30)
check("for other sources the oldest installed source version still counts", len(f) == 1, str(f))

# real-shaped KEV names against the product table
t0 = day(-2)
kreal = kev_of(kev_entry("CVE-2099-2001", "Plex", "Media Server", t0, day(20)), kev_entry("CVE-2099-2002", "Zabbix", "Frontend", t0, day(20)),
               kev_entry("CVE-2099-2003", "Google", "Chrome Blink", t0, day(20)),
               kev_entry("CVE-2099-2004", "Mozilla", "Firefox and Thunderbird", t0, day(20)),
               kev_entry("CVE-2099-2005", "Mozilla", "Firefox, Firefox ESR, and Thunderbird", t0, day(20)))
rr = rec_of(["plexmediaserver\t1.40\t\t", "zabbix-frontend-php\t7.0.1\t\t", "google-chrome-stable\t125.0\t\t", "thunderbird\t128.0\t\t"])
f = vw.match_host(rr, kreal, {}, vw.load_products(), 30)
check("table rows match the real KEV product names (Plex, Zabbix frontend, Chrome, Thunderbird via the Firefox entries)",
      {(x["cve"], x["source"]) for x in f.values()} == {("CVE-2099-2001", "plexmediaserver"), ("CVE-2099-2002", "zabbix-frontend-php"),
                                                        ("CVE-2099-2003", "google-chrome-stable"), ("CVE-2099-2004", "thunderbird"),
                                                        ("CVE-2099-2005", "thunderbird")}, str(sorted(x["cve"] for x in f.values())))

# hostile values
try:
    ok = vw.debcmp("²:1.0", "1.0") in (-1, 0, 1) and vw.debcmp("9" * 5000 + ":1.0", "1.0") in (-1, 0, 1)
except Exception as e:
    ok = False
check("a non-ASCII digit or a huge epoch cannot crash debcmp", ok)
check("a deeply nested OS value cannot crash the parser", vw.parse_os("[" * 50000) == {})
for label, fn, arg in (("empty KEV catalog", vw.parse_kev, '{"vulnerabilities": []}'), ("empty tracker", vw.parse_tracker, "{}"),
                       ("tracker error body", vw.parse_tracker, '{"message": "rate limited"}')):
    try:
        fn(arg)
        check(f"{label} is rejected", False)
    except ValueError:
        check(f"{label} is rejected", True)

# a degenerate feed keeps the cache and produces no "fixed" flood
main_world()
S.etag, S.lm = '"kev-5"', "lm-5"
st_deg = new_state()
run("run")
n_state = len(json.load(open(os.path.join(st_deg, "state.json")))["findings"])
S.kev_saved, S.tracker_saved = S.kev, S.tracker
S.kev, S.etag = [], '"kev-6"'
code, out, err, msg = run("run")
check("an empty KEV answer keeps the cache: no message, findings kept",
      code == 0 and msg is None and len(json.load(open(os.path.join(st_deg, "state.json")))["findings"]) == n_state, err)
S.kev, S.tracker, S.lm = S.kev_saved, {}, "lm-6"
code, out, err, msg = run("run")
check("an empty tracker answer keeps the cache: no message", code == 0 and msg is None and "✅" not in (msg or ""), err)
S.tracker, S.lm, S.etag = S.tracker_saved, "lm-7", '"kev-7"'
code, out, err, msg = run("run")
check("recovered feeds: nothing re-announced", code == 0 and msg is None, str(msg))

# a release the tracker does not carry is unsupported, not verified
main_world()
S.add_host("7", "deb11-g", {"product_name": "Debian GNU/Linux", "major": 11, "version_pretty": "Debian GNU/Linux 11 (bullseye)"},
           shards([("libfoo", "1.0-1", "libfoo", "1.0-1")]), apt())
S.etag, S.lm = '"kev-8"', "lm-8"
new_state()
code, out, err, msg = run("run")
check("a release absent from the tracker (bullseye) produces no finding and no 'verified' state",
      code == 0 and not any(l.startswith("deb11-g:") for l in finding_lines(msg)))
code, out, err, msg = run("status")
check("status lists it as unsupported with the reason", "deb11-g: release not covered by the Debian tracker" in out and "deb11-g: Debian" not in out, out)

# CHECK promoted to a confirmed finding under the same key
oldk = {"h|CVE-2099-3000|nodejs": {"host": "h", "cve": "CVE-2099-3000", "source": "nodejs", "status": "CHECK", "installed": "20.1-1",
                                    "fixed": "", "due": day(30), "first_seen": 111, "last_seen": 111, "notified_due": False}}
fnew = {"h|CVE-2099-3000|nodejs": {"host": "h", "cve": "CVE-2099-3000", "source": "nodejs", "status": "VULN_FIX", "installed": "20.1-1",
                                    "fixed": "20.2-1", "due": day(30), "ev": 0}}
recs_h = [{"name": "h", "kind": "ok", "partial": False}]
newd, ev = vw.reconcile(oldk, recs_h, fnew, True)
check("a CHECK that becomes VULN_FIX is announced as new and keeps first_seen",
      len(ev["new"]) == 1 and newd["h|CVE-2099-3000|nodejs"]["first_seen"] == 111 and newd["h|CVE-2099-3000|nodejs"]["status"] == "VULN_FIX", str(ev))
newd, ev = vw.reconcile(oldk, recs_h, {k: {**v, "status": "CHECK"} for k, v in fnew.items()}, True)
check("a CHECK that stays a CHECK is silent", not any(ev.values()), str(ev))

# message: order, cap and hostile text
many = {"new": [{"host": "h", "cve": f"CVE-2099-{i:04d}", "source": f"p{i}", "status": "CHECK", "installed": "1", "fixed": "", "due": ""} for i in range(25)]
        + [{"host": "h", "cve": "CVE-2099-9999", "source": "important", "status": "VULN_FIX", "installed": "1", "fixed": "2", "due": day(3)}],
        "fixavail": [], "due": [], "fixed": []}
check("a VULN_FIX line is listed before 25 CHECK lines, so the cap cannot hide it", "CVE-2099-9999" in vw.build_message(many, set()))
evx = {"new": [], "fixavail": [], "due": [{"host": "h", "cve": "CVE-2099-5000", "source": "a", "status": "AFFECTED", "installed": "1", "fixed": "", "due": day(2)}],
       "fixed": [{"host": "h", "cve": "CVE-2099-5001", "source": "b"}]}
evx["new"] = [{"host": "h", "cve": f"CVE-2099-6{i:03d}", "source": "p", "status": "AFFECTED", "installed": "1", "fixed": "", "due": day(9)} for i in range(30)]
mx = vw.build_message(evx, set())
check("due and fixed lines come before the new ones, so a cut never drops them", mx.splitlines().index(next(l for l in mx.splitlines() if "CVE-2099-5001" in l)) < 4
      and "CVE-2099-5000" in mx)
evh = {"new": [{"host": "a‮evil\nfake ✅ line", "cve": "CVE-2099-7000", "source": "x", "status": "CHECK", "installed": "9" * 40000, "fixed": "", "due": ""},
               {"host": "second", "cve": "CVE-2099-7001", "source": "y", "status": "AFFECTED", "installed": "1", "fixed": "", "due": ""}],
       "fixavail": [], "due": [], "fixed": []}
mh = vw.build_message(evh, {"z‮" + "n" * 500})
check("agent-supplied text is cleaned and capped, a long field cannot push other lines out",
      len(mh) < 3900 and "‮" not in mh and "CVE-2099-7001" in mh and not any(l.startswith("fake") for l in mh.splitlines())
      and not any(unicodedata.category(c) in ("Cc", "Cf") for c in mh.replace("\n", "")), mh[:300])

# host isolation: a host that cannot be judged is blind, the others are still judged
main_world()
S.etag, S.lm = '"kev-9"', "lm-9"
new_state()
real_match, real_inspect = vw.match_host, vw.inspect_host
vw.match_host = lambda rec, *a, **k: (_ for _ in ()).throw(RuntimeError("garbled")) if rec["name"] == "deb13-b" else real_match(rec, *a, **k)
code, out, err, msg = run("run")
vw.match_host = real_match
check("a host whose matching fails is blind, the others are still judged",
      code == 0 and "sin inventario reciente:" in msg and "deb13-b" in msg and "deb13-a: CVE-2099-0001" in msg, str(msg))
vw.inspect_host = lambda cfg, h, items, now_s: (_ for _ in ()).throw(RuntimeError("garbled")) if h["name"] == "deb13-a" else real_inspect(cfg, h, items, now_s)
code, out, err, msg = run("status")
vw.inspect_host = real_inspect
check("a host whose inventory cannot be parsed is listed as blind and the others still appear",
      code == 0 and "deb13-a: BLIND (unparsable inventory)" in out and "deb13-b:" in out, out)

# inventory sanity: blind reasons
S.reset()
S.kev = [kev_entry("CVE-2099-0001", "Libfoo", "Libfoo", day(-5), day(20))]
S.tracker = {"libfoo": {"CVE-2099-0001": {"releases": {"trixie": rel("open")}}}}
foo = ("libfoo", "1.2-1", "libfoo", "1.2-1")
short = [f"#vw.dpkg shard={n} of=4 count=9\nlibfoo\t1.2-1\tlibfoo\t1.2-1\n" for n in range(4)]
S.add_host("1", "short-a", DEB13, short, apt())
S.add_host("2", "empty-b", DEB13, [f"#vw.dpkg shard={n} of=4 count=0\n" for n in range(4)], apt())
S.add_host("3", "noapt-c", DEB13, shards([foo]), None, shard_age=3 * 86400)
S.add_host("4", "noos-d", None, shards([foo]), apt())
S.add_host("5", "quiet-e", DEB13, shards([foo]), apt(), shard_age=3 * 86400)
S.add_host("6", "nohead-f", DEB13, ["libfoo\t1.2-1\tlibfoo\t1.2-1\n"] * 4, apt())
S.etag, S.lm = '"kev-10"', "lm-10"
new_state()
code, out, err, msg = run("status")
check("a shard with fewer lines than its header count is blind", "short-a: BLIND (shard 0 incomplete (1 of 9 packages)" in out, out)
check("an inventory with no packages is blind", "empty-b: BLIND (the inventory holds no packages)" in out, out)
check("a missing vw.apt item is blind, with fresh-enough shards judged only by the shard rule",
      "noapt-c: BLIND (vw.apt item missing)" in out and "inventory older" not in out.split("noapt-c:")[1].split("\n")[0], out)
check("an unreadable OS is blind, not silently unsupported", "noos-d: BLIND (OS unknown" in out, out)
check("an unchanged shard 3 days old with a fresh vw.apt is not blind", "quiet-e: Debian" in out, out)
check("a shard without a header is blind", "nohead-f: BLIND (shard 0 has no header" in out, out)

# partial host: never a "fixed" line, then a proper one
S.reset()
S.kev = [kev_entry("CVE-2099-0001", "Libfoo", "Libfoo", day(-5), day(20))]
S.tracker = {"libfoo": {"CVE-2099-0001": {"releases": {"trixie": rel("open")}}}}
S.add_host("1", "partial-p", DEB13, shards([foo, ("bash", "5.2-1", "bash", "5.2-1")], truncated=True), apt())
S.add_host("2", "full-q", DEB13, shards([foo, ("bash", "5.2-1", "bash", "5.2-1")]), apt())
S.etag, S.lm = '"kev-11"', "lm-11"
stp = new_state()
run("run")
for hid in ("1", "2"):
    for n, text in enumerate(shards([("bash", "5.2-1", "bash", "5.2-1"), ("zsh", "5.9-1", "zsh", "5.9-1")], truncated=hid == "1")):
        S.put(hid, vw.KEY_SHARDS[n], text, 60)
code, out, err, msg = run("run")
fs = json.load(open(os.path.join(stp, "state.json")))["findings"]
check("a truncated host never gets a fixed line and keeps its finding",
      msg is not None and "✅ full-q" in msg and "partial-p" not in msg and "partial-p|CVE-2099-0001|libfoo" in fs and "full-q|CVE-2099-0001|libfoo" not in fs, str(msg))
for n, text in enumerate(shards([("bash", "5.2-1", "bash", "5.2-1"), ("zsh", "5.9-1", "zsh", "5.9-1")])):
    S.put("1", vw.KEY_SHARDS[n], text, 60)
code, out, err, msg = run("run")
check("once the inventory is whole, the fix is announced", msg is not None and "✅ partial-p: CVE-2099-0001 libfoo corregido" in msg, str(msg))

# --host leaves the other hosts' findings alone
S.reset()
S.kev = [kev_entry("CVE-2099-0001", "Libfoo", "Libfoo", day(-5), day(20))]
S.tracker = {"libfoo": {"CVE-2099-0001": {"releases": {"trixie": rel("open")}}}}
S.add_host("1", "host-a", DEB13, shards([foo]), apt())
S.add_host("2", "host-b", DEB13, shards([foo]), apt())
S.etag, S.lm = '"kev-12"', "lm-12"
sth = new_state()
run("run")
for n, text in enumerate(shards([("bash", "5.2-1", "bash", "5.2-1")])):
    S.put("2", vw.KEY_SHARDS[n], text, 60)
code, out, err, msg = run("run", "--host", "host-a")
fs = json.load(open(os.path.join(sth, "state.json")))["findings"]
check("--host: the other host's findings are untouched and no fixed line is sent", code == 0 and msg is None and "host-b|CVE-2099-0001|libfoo" in fs, str(msg))
code, out, err, msg = run("run")
check("a full run afterwards does announce that host's fix", msg is not None and "✅ host-b" in msg, str(msg))

# a host that left Zabbix drops its findings quietly
S.hosts = [h for h in S.hosts if h["name"] != "host-a"]
code, out, err, msg = run("run")
fs = json.load(open(os.path.join(sth, "state.json")))["findings"]
check("a host that left Zabbix drops its findings quietly", code == 0 and msg is None and not any(k.startswith("host-a|") for k in fs), str(msg))

# reboot pending, in status only
S.reset()
S.kev, S.tracker = [kev_entry("CVE-2099-0001", "Libfoo", "Libfoo", day(-5), day(20))], {"libfoo": {"CVE-2099-0001": {"releases": {"trixie": rel("open")}}}}
S.add_host("1", "rb-file", DEB13, shards([("bash", "5.2-1", "bash", "5.2-1")]), apt(reboot_required=True))
S.add_host("2", "rb-kernel", DEB13, shards([("bash", "5.2-1", "bash", "5.2-1")]), apt(kernel_installed_pkg="linux-image-6.12.2-amd64"))
S.add_host("3", "rb-none", DEB13, shards([("bash", "5.2-1", "bash", "5.2-1")]), apt())
S.etag, S.lm = '"kev-13"', "lm-13"
new_state()
code, out, err, msg = run("run")
check("reboot pending never produces a message", msg is None)
code, out, err, msg = run("status")
lines_by = {l.split(":")[0]: l for l in out.splitlines() if ":" in l}
check("status shows reboot pending from the file and from a newer installed kernel, not otherwise",
      "reboot pending" in lines_by["rb-file"] and "reboot pending" in lines_by["rb-kernel"] and "reboot pending" not in lines_by["rb-none"]
      and "updates 3 (security 1)" in lines_by["rb-none"], out)

# the real notify path: import, send(text), outbox
import notify
for k in ("OPS_BOT_TOKEN", "OPS_CHAT_ID"):
    os.environ.pop(k, None)
notify.ENV_FILE = os.path.join(TMP, "no-such.env")
notify.STATE_DIR = os.path.join(TMP, "notify")
notify.STATE, notify.OUTBOX, notify.LOCK = (os.path.join(notify.STATE_DIR, n) for n in ("alerts.json", "outbox.jsonl", "alerts.lock"))
with contextlib.redirect_stdout(io.StringIO()):
    sent_ok = _real_notify("probe text")
check("the real notify path works: with no bot configured the text waits in the outbox",
      sent_ok is False and "probe text" in open(notify.OUTBOX).read())

# ------------------------------------------------------------------ 12. nothing leaks the token
blob = "\n".join(ALL_OUT + SENT)
for d in STATES:
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith(".gz"):
                continue
            blob += open(os.path.join(root, f), errors="replace").read()
check("token never in output, messages or state files", TOKEN not in blob and "Bearer" not in blob)
check("the unit files and the product table are well formed",
      all(isinstance(r, dict) for r in json.load(open(vw.PRODUCTS))) and len(vw.load_products()) >= 10
      and all(x in open(os.path.join(os.path.dirname(vw.__file__), "vuln-watch.service")).read()
              for x in ("OnFailure=ops-alert@%n.service", "IOSchedulingClass=idle", "TimeoutStartSec=30min"))
      and "05:40" in open(os.path.join(os.path.dirname(vw.__file__), "vuln-watch.timer")).read())

shutil.rmtree(TMP, ignore_errors=True)
print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("all vuln_watch checks passed")
