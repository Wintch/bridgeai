#!/usr/bin/env python3
"""Nightly check of the software installed on monitored hosts against CISA's Known Exploited Vulnerabilities (KEV) list.

Why: Zabbix knew each host's OS banner and a package count, nothing about what is installed. A KEV entry is a
vulnerability that is being exploited now, so "is any of it on one of my machines" is the one question worth a message.

Every night (vuln-watch.timer) this reads the inventory that the "SW inventory daily" Zabbix template collects
(system.sw.os.get, vw.dpkg[N,4] shards, vw.apt), read-only through the Zabbix API, and matches it against:
  * the KEV catalog (cached, conditional GET);
  * the Debian security tracker, reduced to the CVEs that are in KEV: a source package whose tracker entry for the
    host's release is "resolved" with a fixed_version above the installed source version is VULN_FIX (fix available);
    one that is "open"/"undetermined" is AFFECTED (no fix yet); fixed_version "0" means not affected;
  * vuln_watch_products.json: KEV entries for software the Debian tracker does not cover (vendor repositories).
    A match is only CHECK ("verify by hand"), and only for KEV entries added in the last 30 days.
Debian hosts only in this phase. Ubuntu, an agentless collector and trapper write-back are later phases; NVD/CPE matching is
dropped (see security/SECURITY_WATCH.md: Debian tracker, OSV offline data and the product table instead).
A Debian release that the tracker does not carry at all (an end-of-life one) is listed as unsupported, never as verified. The
kernel is judged through source "linux" (signed wrapper sources are mapped to it) using the newest installed version.

One operator message per run (ops/lib/notify.py send), only for: a new finding, AFFECTED that now has a fix, a finding that
was fixed, a KEV due date within 7 days (once), a host that newly cannot be inventoried. Everything else is in `status`.

Config (never in git): ~/aibridge/ops/ops.env (path overridable with OPS_ENV; environment variables win):
  VULNWATCH_ZBX_URL     Zabbix site root or api_jsonrpc.php address (https; plain http only for a loopback address)
  VULNWATCH_ZBX_TOKEN   API token of a read-only user (role type User): any other type, or an answer without a type, is refused (exit 2)
  VULNWATCH_GROUPS      optional, comma-separated host group names (default: every readable group)
Without URL and token it prints one line and exits 0, so an unconfigured timer stays quiet.
Environment: VULNWATCH_STATE (state dir, default ~/.local/state/vuln_watch), VULNWATCH_KEV_URL, VULNWATCH_TRACKER_URL,
VULNWATCH_CHECK_DAYS (CHECK window, default 30).

  vuln_watch.py run [--dry-run] [--host NAME]   inventory, match, notify, update state (the timer). --dry-run prints the
                                                message and sends nothing and writes no state (the feed cache is refreshed)
  vuln_watch.py status                          per host: OS, packages, inventory age, blind/partial/unsupported/not
                                                inventoried, reboot pending, pending/security updates, open findings
  vuln_watch.py feeds                           feed cache ages, validators and the reduced-tracker cache
Exit codes: 0 ok (findings are not an error), 1 failure (API error, feeds unreachable with no recent cache), 2 refused token.

Zabbix API: only the methods in ALLOWED are ever sent, over https, and a redirect is never followed (the token is not re-sent). Free-text values (package lists) are read with history.get, because
item.get's lastvalue is cut for big text. Item age: a shard whose value did not change is discarded by the template's
heartbeat (7 days), so per-shard freshness is judged against SHARD_MAX_S, and the 48 h "inventory is current" rule uses vw.apt.
"""
import argparse, datetime, fnmatch, gzip, hashlib, json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
PRODUCTS = os.path.join(HERE, "vuln_watch_products.json")
UA = "vuln_watch (bridgeai)"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
TRACKER_URL = "https://security-tracker.debian.org/tracker/data/json"
ALLOWED = ("user.checkAuthentication", "hostgroup.get", "host.get", "item.get", "history.get")
KEY_OS, KEY_APT = "system.sw.os.get", "vw.apt"
KEY_SHARDS = [f"vw.dpkg[{n},4]" for n in range(4)]
ITEM_KEYS = [KEY_OS, *KEY_SHARDS, KEY_APT]
CODENAMES = {"11": "bullseye", "12": "bookworm", "13": "trixie", "14": "forky"}
CODENAME_RE = re.compile(r"\b(bullseye|bookworm|trixie|forky|sid)\b", re.I)
BLIND_S = 48 * 3600          # the inventory (vw.apt) must be newer than this
SHARD_MAX_S = 8 * 86400      # a package shard: template heartbeat 7 days plus a day
HISTORY_S = 9 * 86400
CACHE_MAX_S = 7 * 86400      # a feed cache this young stands in for a failed download
DUE_DAYS, MAX_LINES = 7, 20
MSG_CAP = 3900               # the ops bot cuts a message at 4000 characters
FIELD_CAP = 64               # longest agent-supplied field (host, package, version) shown in a message
LOOPBACK = ("127.0.0.1", "localhost", "::1")
ACTIVE = ("VULN_FIX", "AFFECTED")


class ApiError(Exception):
    pass


class TokenRefused(Exception):
    pass


class FeedError(Exception):
    pass


def now():
    return time.time()


def today():
    return datetime.date.fromtimestamp(now())


# ------------------------------------------------------------------ config and state files

def load_conf():
    path = os.environ.get("OPS_ENV", os.path.expanduser("~/aibridge/ops/ops.env"))
    conf = {}
    try:
        for line in open(path):
            k, sep, v = line.partition("=")
            if sep and not k.lstrip().startswith("#"):
                conf[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return {k: os.environ.get(k, conf.get(k, "")) for k in ("VULNWATCH_ZBX_URL", "VULNWATCH_ZBX_TOKEN", "VULNWATCH_GROUPS")}


def state_dir(create=True):
    d = os.path.expanduser(os.environ.get("VULNWATCH_STATE", "~/.local/state/vuln_watch"))
    if create:
        os.makedirs(d, mode=0o700, exist_ok=True)
        os.chmod(d, 0o700)
    return d


def write_private(path, data):
    tmp = path + ".part"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode())
    os.replace(tmp, path)


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load_state():
    s = read_json(os.path.join(state_dir(), "state.json"), {})
    return {"findings": s.get("findings") or {}, "blind": s.get("blind") or []}


def save_state(s):
    write_private(os.path.join(state_dir(), "state.json"), json.dumps(s, indent=1, sort_keys=True))


def notify_send(text):
    import notify
    return notify.send(text)


# ------------------------------------------------------------------ Debian version order (dpkg's algorithm)

def _digit(c):
    return "0" <= c <= "9"


def _order(c):
    if _digit(c):
        return 0
    if ("a" <= c <= "z") or ("A" <= c <= "Z"):
        return ord(c)
    if c == "~":
        return -1
    return ord(c) + 256 if c else 0


def _verrev(a, b):
    i = j = 0
    while i < len(a) or j < len(b):
        while (i < len(a) and not _digit(a[i])) or (j < len(b) and not _digit(b[j])):
            ac = _order(a[i]) if i < len(a) else 0
            bc = _order(b[j]) if j < len(b) else 0
            if ac != bc:
                return ac - bc
            i, j = i + 1, j + 1
        while i < len(a) and a[i] == "0":
            i += 1
        while j < len(b) and b[j] == "0":
            j += 1
        first = 0
        while i < len(a) and _digit(a[i]) and j < len(b) and _digit(b[j]):
            first = first or ord(a[i]) - ord(b[j])
            i, j = i + 1, j + 1
        if i < len(a) and _digit(a[i]):
            return 1
        if j < len(b) and _digit(b[j]):
            return -1
        if first:
            return first
    return 0


def _split_version(v):
    v = v.strip()
    epoch = 0
    head, sep, rest = v.partition(":")
    if sep and head.isascii() and head.isdigit() and len(head) <= 9:      # a hostile epoch must not crash a run
        epoch, v = int(head), rest
    up, sep, rev = v.rpartition("-")
    return (epoch, up, rev) if sep else (epoch, v, "")


def debcmp(a, b):
    """-1, 0 or 1: how Debian orders version a against b (epoch, upstream, revision; ~ sorts before everything)."""
    (ea, ua, ra), (eb, ub, rb) = _split_version(a), _split_version(b)
    if ea != eb:
        return -1 if ea < eb else 1
    for x, y in ((ua, ub), (ra, rb)):
        c = _verrev(x, y)
        if c:
            return -1 if c < 0 else 1
    return 0


# ------------------------------------------------------------------ Zabbix API (read-only)

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None   # a 3xx surfaces as HTTPError: the bearer token is never re-sent to another address


_OPENER = urllib.request.build_opener(_NoRedirect)


def api(cfg, method, params, auth=True):
    if method not in ALLOWED:
        raise ApiError(f"method {method} is not allowed (vuln_watch is read-only)")
    url = cfg["VULNWATCH_ZBX_URL"].rstrip("/")
    if not url.endswith(".php"):
        url += "/api_jsonrpc.php"
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" and not (u.scheme == "http" and u.hostname in LOOPBACK) and os.environ.get("VULNWATCH_ALLOW_HTTP") != "1":
        raise ApiError("VULNWATCH_ZBX_URL must be https:// (the token would travel in cleartext)")
    headers = {"Content-Type": "application/json-rpc", "User-Agent": UA}
    if auth:
        headers["Authorization"] = "Bearer " + cfg["VULNWATCH_ZBX_TOKEN"]
    req = urllib.request.Request(url, data=json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode(),
                                 headers=headers)
    try:
        raw = _OPENER.open(req, timeout=30).read()
    except urllib.error.HTTPError as e:
        hint = "; it redirected, set VULNWATCH_ZBX_URL to the final https address" if 300 <= e.code < 400 else ""
        raise ApiError(f"{method}: Zabbix answered HTTP {e.code}{hint}")
    except (urllib.error.URLError, OSError) as e:
        raise ApiError(f"{method}: cannot reach the Zabbix API ({type(e).__name__})")
    try:
        d = json.loads(raw)
    except ValueError:
        raise ApiError(f"{method}: the address did not answer JSON; check VULNWATCH_ZBX_URL")
    if "error" in d:
        raise ApiError(f"{method}: {d['error'].get('message')} {d['error'].get('data', '')}".strip())
    return d["result"]


def check_token(cfg):
    """The token must belong to a plain User: a token that can change Zabbix is not stored here."""
    me = api(cfg, "user.checkAuthentication", {"token": cfg["VULNWATCH_ZBX_TOKEN"]}, auth=False)
    if str(me.get("type", "")) != "1":
        raise TokenRefused("the token's user is not a plain read-only User (role type User is required; Admin, Super admin "
                           "or an unreadable answer is refused): create a read-only user for vuln_watch")


def latest_value(cfg, item, now_s):
    r = api(cfg, "history.get", {"output": "extend", "history": int(item.get("value_type", 4)), "itemids": [item["itemid"]],
                                 "sortfield": "clock", "sortorder": "DESC", "limit": 1, "time_from": int(now_s - HISTORY_S)})
    return (int(r[0]["clock"]), r[0]["value"]) if r else (None, None)


def parse_os(text):
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else {}
    except (ValueError, TypeError, RecursionError):
        return {}


def debian_codename(osd, inv_os=""):
    """(is_debian, codename or ""): Debian by product_name; codename from version_pretty, else from the major number."""
    product = str(osd.get("product_name") or "")
    pretty = str(osd.get("version_pretty") or inv_os or "")
    if "debian" not in (product or pretty).lower():
        return False, ""
    m = CODENAME_RE.search(pretty)
    if m:
        return True, m[1].lower()
    return True, CODENAMES.get(str(osd.get("major", "")), "")


def parse_shard(text):
    """-> (packages {binary: (version, source, source_version)}, truncated, nodpkg, declared package count or None)."""
    pkgs, truncated, nodpkg, declared = {}, False, False, None
    for line in text.splitlines():
        if line.startswith("#"):
            truncated = truncated or line.strip() == "#truncated"
            nodpkg = nodpkg or line.strip() == "#nodpkg"
            m = re.fullmatch(r"#vw\.dpkg shard=\d+ of=\d+ count=(\d+)", line.strip())
            if m:
                declared = int(m[1])
            continue
        f = line.rstrip("\r\n").split("\t")
        if len(f) < 2 or not f[0] or not f[1]:
            continue
        src = f[2] if len(f) > 2 and f[2] else f[0]
        srcv = f[3] if len(f) > 3 and f[3] else f[1]
        if src.startswith("linux-signed-"):
            # the tracker files kernel CVEs under source "linux"; a signed wrapper's binary version equals the linux source version
            src, srcv = "linux", f[1]
        pkgs[f[0]] = (f[1], src, srcv)
    return pkgs, truncated, nodpkg, declared


def signal(item, clock):
    return max(int(item.get("lastclock") or 0), clock or 0)


def blank_rec(h):
    return {"hostid": h["hostid"], "name": h.get("name") or h.get("host"), "kind": "ok", "reason": "", "pretty": "",
            "codename": "", "pkgs": {}, "count": 0, "partial": False, "age_s": None, "apt": None, "reboot": False}


def inspect_host(cfg, h, items, now_s):
    """One host's inventory record. kind: not_inventoried | unsupported | blind | ok."""
    inv = h.get("inventory")
    rec = blank_rec(h)
    if not any(k in items for k in KEY_SHARDS + [KEY_APT]):
        rec.update(kind="not_inventoried", reason="no vw.dpkg / vw.apt items")
        return rec
    osd = {}
    if KEY_OS in items and str(items[KEY_OS].get("state")) != "1":
        osd = parse_os(latest_value(cfg, items[KEY_OS], now_s)[1])
    inv_os = inv.get("os", "") if isinstance(inv, dict) else ""
    rec["pretty"] = str(osd.get("version_pretty") or osd.get("product_name") or inv_os or "unknown OS")
    if not (osd.get("product_name") or osd.get("version_pretty") or inv_os):
        rec.update(kind="blind", reason="OS unknown (system.sw.os.get missing, in error or empty)")
        return rec
    is_deb, rec["codename"] = debian_codename(osd, inv_os)
    if not is_deb:
        rec.update(kind="unsupported", reason=f"unsupported in this phase ({rec['pretty']})")
        return rec
    if not rec["codename"]:
        rec.update(kind="unsupported", reason=f"Debian release not identified ({rec['pretty']})")
        return rec
    reasons, parsed, signals = [], [], []
    for n, key in enumerate(KEY_SHARDS):
        it = items.get(key)
        if not it:
            reasons.append(f"shard {n} item missing")
            continue
        if str(it.get("state")) == "1":
            reasons.append(f"shard {n} in error")
            continue
        clock, val = latest_value(cfg, it, now_s)
        if not val or not val.strip():
            reasons.append(f"shard {n} has no value in 9 days")
        elif now_s - signal(it, clock) > SHARD_MAX_S:
            reasons.append(f"shard {n} older than {SHARD_MAX_S // 86400} days")
        else:
            pkgs, truncated, nodpkg, declared = parse_shard(val)
            if not nodpkg and declared is None:
                reasons.append(f"shard {n} has no header")
                continue
            if not nodpkg and not truncated and len(pkgs) < declared:
                reasons.append(f"shard {n} incomplete ({len(pkgs)} of {declared} packages)")
                continue
            parsed.append((pkgs, truncated, nodpkg))
            signals.append(signal(it, clock))
    apt_sig = None
    if KEY_APT in items:
        it = items[KEY_APT]
        if str(it.get("state")) == "1":
            reasons.append("vw.apt in error")
        else:
            clock, val = latest_value(cfg, it, now_s)
            if not val:
                reasons.append("vw.apt has no value in 9 days")
            else:
                apt_sig = signal(it, clock)
                try:
                    apt = json.loads(val)
                    rec["apt"] = apt if isinstance(apt, dict) else None
                except (ValueError, RecursionError):
                    pass
    else:
        reasons.append("vw.apt item missing")
    live = apt_sig if apt_sig is not None else (max(signals) if signals else None)
    if live is not None:
        rec["age_s"] = int(now_s - live)
        if apt_sig is not None and now_s - live > BLIND_S:
            reasons.append(f"inventory older than {BLIND_S // 3600} h")
    if reasons:
        rec.update(kind="blind", reason="; ".join(reasons))
        return rec
    for pkgs, truncated, nodpkg in parsed:
        if nodpkg:
            rec.update(kind="unsupported", reason="no dpkg on this host")
            return rec
        rec["pkgs"].update(pkgs)
        rec["partial"] = rec["partial"] or truncated
    rec["count"] = len(rec["pkgs"])
    if not rec["count"]:
        rec.update(kind="blind", reason="the inventory holds no packages")
        return rec
    apt = rec["apt"] or {}
    pkg, run = str(apt.get("kernel_installed_pkg") or ""), str(apt.get("kernel_running") or "")
    rec["reboot"] = bool(apt.get("reboot_required")) or bool(pkg and run and not (pkg == "linux-image-" + run or pkg.endswith(run)))
    return rec


def collect(cfg, only=None):
    """Inventory records of every monitored host in the configured groups (read-only Zabbix calls)."""
    params = {"output": ["hostid", "host", "name"], "filter": {"status": 0}, "selectInventory": ["os"]}
    names = [g.strip() for g in cfg["VULNWATCH_GROUPS"].split(",") if g.strip()]
    if names:
        groups = api(cfg, "hostgroup.get", {"output": ["groupid", "name"], "filter": {"name": names}})
        if not groups:
            raise ApiError("no readable host group matches VULNWATCH_GROUPS")
        params["groupids"] = [g["groupid"] for g in groups]
    hosts = api(cfg, "host.get", params)
    if only:
        hosts = [h for h in hosts if only.lower() in (str(h.get("host", "")).lower(), str(h.get("name", "")).lower())]
    items = {h["hostid"]: {} for h in hosts}
    ids = list(items)
    for i in range(0, len(ids), 100):
        for it in api(cfg, "item.get", {"output": ["itemid", "hostid", "key_", "value_type", "lastclock", "state", "error"],
                                        "hostids": ids[i:i + 100], "filter": {"key_": ITEM_KEYS}}):
            items.setdefault(it["hostid"], {})[it["key_"]] = it
    now_s = now()
    recs = []
    for h in hosts:
        try:
            recs.append(inspect_host(cfg, h, items[h["hostid"]], now_s))
        except ApiError:
            raise
        except Exception:               # one garbled host must not blind the others
            rec = blank_rec(h)
            rec.update(kind="blind", reason="unparsable inventory")
            recs.append(rec)
    return recs


# ------------------------------------------------------------------ feeds

def _gz_json(path):
    try:
        with gzip.open(path, "rb") as f:
            return json.loads(f.read())
    except (OSError, EOFError, ValueError, zlib.error):
        raise FeedError(f"the cached feed {os.path.basename(path)} cannot be read; delete it and run again")


def parse_kev(raw):
    d = json.loads(raw)
    if not isinstance(d, dict) or not isinstance(d.get("vulnerabilities"), list) or not d["vulnerabilities"]:
        raise ValueError("not a KEV catalog")      # an empty list would turn every finding into "fixed"
    return d


def parse_tracker(raw):
    d = json.loads(raw)
    if not isinstance(d, dict) or not any(
            isinstance(e, dict) and isinstance(e.get("releases"), dict)
            for entries in d.values() if isinstance(entries, dict) for e in entries.values()):
        raise ValueError("not a tracker document")  # an error body or an empty object would turn every finding into "fixed"
    return d


def refresh(name, url, timeout, parse):
    """Conditional download into the cache. -> (meta, parsed or None, how); how: updated | not-modified | cache.
    None means "read the cache": the server said not modified, or it failed and the cache is under 7 days old."""
    d = state_dir()
    body_path, meta_path = os.path.join(d, name + ".json.gz"), os.path.join(d, name + ".meta.json")
    meta = read_json(meta_path, {})
    have = os.path.exists(body_path) and bool(meta.get("sha"))
    headers = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    if have and meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    if have and meta.get("last_modified"):
        headers["If-Modified-Since"] = meta["last_modified"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            raw, enc = r.read(), r.headers.get("Content-Encoding", "")
            etag, lm = r.headers.get("ETag"), r.headers.get("Last-Modified")
        if "gzip" in enc.lower():
            raw = gzip.decompress(raw)
        obj = parse(raw)
    except urllib.error.HTTPError as e:
        if e.code == 304 and have:
            meta["checked"] = now()
            write_private(meta_path, json.dumps(meta))
            return meta, None, "not-modified"
        err = f"HTTP {e.code}"
    except (urllib.error.URLError, OSError, ValueError, EOFError, zlib.error) as e:
        err = type(e).__name__
    else:
        meta = {"etag": etag, "last_modified": lm, "sha": hashlib.sha256(raw).hexdigest(), "size": len(raw),
                "fetched": now(), "checked": now()}
        write_private(body_path, gzip.compress(raw, 6))
        write_private(meta_path, json.dumps(meta))
        return meta, obj, "updated"
    if have and now() - meta.get("checked", 0) < CACHE_MAX_S:
        print(f"vuln_watch: {name} download failed ({err}); using the cache from {int((now() - meta.get('checked', 0)) / 3600)} h ago",
              file=sys.stderr)
        return meta, None, "cache"
    raise FeedError(f"{name}: download failed ({err}) and there is no cache younger than {CACHE_MAX_S // 86400} days")


def reduce_tracker(tracker, cves):
    """-> ({source: {cve: {codename: {status, fixed_version}}}} for the CVEs in `cves` only, every release codename the
    whole tracker knows). The codenames come from the full tracker so a release is not lost because none of its CVEs are in KEV."""
    out, codenames = {}, set()
    for src, entries in tracker.items():
        if not isinstance(entries, dict):
            continue
        for cve, e in entries.items():
            if not isinstance(e, dict):
                continue
            rels = e.get("releases")
            if not isinstance(rels, dict):
                continue
            codenames.update(str(c) for c in rels)
            if cve not in cves:
                continue
            for cn, r in rels.items():
                if isinstance(r, dict):
                    out.setdefault(src, {}).setdefault(cve, {})[cn] = {"status": r.get("status", ""),
                                                                      "fixed_version": r.get("fixed_version", "")}
    return out, codenames


def load_feeds():
    """-> (kev {cve: entry}, reduced tracker, codenames the tracker covers). The reduction is cached under both feeds' content hashes."""
    kmeta, kobj, _ = refresh("kev", os.environ.get("VULNWATCH_KEV_URL", KEV_URL), 60, parse_kev)
    if kobj is None:
        kobj = _gz_json(os.path.join(state_dir(), "kev.json.gz"))
    kev = {v["cveID"]: v for v in kobj["vulnerabilities"] if isinstance(v, dict) and v.get("cveID")}
    tmeta, tobj, _ = refresh("tracker", os.environ.get("VULNWATCH_TRACKER_URL", TRACKER_URL), 300, parse_tracker)
    key = f"{kmeta['sha']}:{tmeta['sha']}"
    path = os.path.join(state_dir(), "reduced.json")
    cached = read_json(path, {})
    if cached.get("key") == key and isinstance(cached.get("data"), dict) and isinstance(cached.get("codenames"), list):
        return kev, cached["data"], set(cached["codenames"])
    if tobj is None:
        tobj = _gz_json(os.path.join(state_dir(), "tracker.json.gz"))
    red, codenames = reduce_tracker(tobj, set(kev))
    write_private(path, json.dumps({"key": key, "built": now(), "codenames": sorted(codenames), "data": red}))
    return kev, red, codenames


def apply_coverage(recs, codenames):
    """A Debian release the tracker does not carry (an end-of-life one) was never judged: it must not look verified."""
    if not codenames:
        return
    for r in recs:
        if r["kind"] == "ok" and r["codename"] not in codenames:
            r.update(kind="unsupported", reason=f"release not covered by the Debian tracker ({r['pretty']})")


# ------------------------------------------------------------------ matching

def load_products():
    rows = read_json(PRODUCTS, [])
    return [r for r in rows if isinstance(r, dict) and r.get("vendor") and r.get("product") and r.get("packages")]


def parse_date(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def finding(rec, cve, source, status, installed, fixed, entry):
    return {"host": rec["name"], "cve": cve, "source": source, "status": status, "installed": installed, "fixed": fixed,
            "due": str((entry or {}).get("dueDate") or "")[:10]}


def keeps_newest(src):
    """Retained old kernel packages are not what runs, so for the kernel source the newest installed version counts;
    for every other source the oldest does (a library may still be loaded from it)."""
    return src == "linux"


def match_host(rec, kev, red, products, check_days):
    """{state key: finding} for one Debian host."""
    out = {}
    srcs = {}
    for _, (_, src, srcv) in rec["pkgs"].items():
        if src not in srcs:
            srcs[src] = srcv
        else:
            c = debcmp(srcv, srcs[src])
            if (c > 0) if keeps_newest(src) else (c < 0):
                srcs[src] = srcv
    for src, cves in red.items():
        sv = srcs.get(src)
        if sv is None:
            continue
        for cve, rels in cves.items():
            r = rels.get(rec["codename"])
            if not r:
                continue
            status, fixed = r.get("status"), r.get("fixed_version") or ""
            if status == "resolved":
                if fixed not in ("", "0") and debcmp(sv, fixed) < 0:
                    out[f"{rec['name']}|{cve}|{src}"] = finding(rec, cve, src, "VULN_FIX", sv, fixed, kev.get(cve))
            elif status in ("open", "undetermined"):
                out[f"{rec['name']}|{cve}|{src}"] = finding(rec, cve, src, "AFFECTED", sv, "", kev.get(cve))
    t = today()
    for cve, e in kev.items():
        added = parse_date(e.get("dateAdded"))
        if added is None or (t - added).days > check_days:
            continue
        vendor, product = str(e.get("vendorProject", "")).lower(), str(e.get("product", "")).lower()
        for row in products:
            if row["vendor"].lower() != vendor or not product.startswith(row["product"].lower()):
                continue
            for binary, (ver, src, _) in rec["pkgs"].items():
                if any(fnmatch.fnmatchcase(binary.lower(), p.lower()) for p in row["packages"]):
                    if cve in red.get(src, {}):
                        continue          # the Debian tracker decides for its own packages
                    out.setdefault(f"{rec['name']}|{cve}|{binary}", finding(rec, cve, binary, "CHECK", ver, "", e))
    return out


def due_soon(f):
    d = parse_date(f.get("due"))
    return d is not None and (d - today()).days <= DUE_DAYS


def reconcile(old, recs, found, scope_all):
    """-> (new findings dict, events). Hosts that could not be evaluated keep their old findings untouched."""
    ev = {"new": [], "fixavail": [], "due": [], "fixed": []}
    evaluated = {r["name"] for r in recs if r["kind"] == "ok"}
    partial = {r["name"] for r in recs if r["kind"] == "ok" and r["partial"]}
    known = {r["name"] for r in recs}
    t = int(now())
    new = {}
    for key, o in old.items():
        if o.get("host") not in evaluated:
            if scope_all and o.get("host") not in known:
                continue                  # the host left Zabbix (or the groups): drop its findings quietly
            new[key] = o
    for key, f in found.items():
        o = old.get(key)
        rec = {**f, "first_seen": o["first_seen"] if o else t, "last_seen": t, "notified_due": bool(o and o.get("notified_due"))}
        if f["status"] in ACTIVE and not (o and o["status"] in ACTIVE):
            ev["new"].append(rec)             # first sighting, or a CHECK promoted to a confirmed finding
        elif not o:
            ev["new"].append(rec)             # a CHECK seen for the first time
        elif o["status"] == "AFFECTED" and f["status"] == "VULN_FIX":
            ev["fixavail"].append(rec)
        if rec["status"] in ACTIVE and due_soon(rec) and not rec["notified_due"]:
            if o and o["status"] == f["status"]:
                ev["due"].append(rec)
            rec["notified_due"] = True              # a "new" or "fix available" line already says when it is due
        new[key] = rec
    for key, o in old.items():
        if o.get("host") in evaluated and key not in found and o.get("host") not in partial:
            if o["status"] in ACTIVE:
                ev["fixed"].append(o)
        elif o.get("host") in partial and key not in found:
            new[key] = o                          # a truncated inventory cannot prove that something was fixed
    return new, ev


def _s(v, n=FIELD_CAP):
    """An agent-supplied value for a message: control, format and line-separator characters become spaces, length is capped."""
    t = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in str(v))
    return t if len(t) <= n else t[:n - 1] + "…"


def fmt(f, prefix=""):
    fix = _s(f["fixed"]) if f["status"] == "VULN_FIX" else ("sin parche" if f["status"] == "AFFECTED" else "verificar")
    due = f"KEV, vence {f['due']}" if f.get("due") else "KEV"
    return f"{prefix}{_s(f['host'])}: {f['cve']} {_s(f['source'])} {_s(f['installed'])} → {fix} ({due})"


def build_message(ev, newly_blind):
    """Lines that cannot be recovered later (due, fixed) come first, so a cut falls on new findings, which `status` still lists."""
    rank = {"VULN_FIX": 0, "AFFECTED": 1, "CHECK": 2}
    new = sorted(ev["new"], key=lambda f: (rank.get(f["status"], 3), f.get("due") or "9999-99-99"))
    lines = [fmt(f, "⏰ ") for f in ev["due"]] + [f"✅ {_s(f['host'])}: {f['cve']} {_s(f['source'])} corregido" for f in ev["fixed"]] \
        + [fmt(f, "🩹 ") for f in ev["fixavail"]] + [fmt(f) for f in new]
    if not lines and not newly_blind:
        return None
    head = f"🛡️ vuln_watch: {len(ev['new'])} nuevas, {len(ev['fixed'])} corregidas"
    names = sorted(newly_blind)
    blind = ("👁️ sin inventario reciente: " + ", ".join(_s(n) for n in names[:10])
             + (f" y {len(names) - 10} más" if len(names) > 10 else "") + " (vuln_watch.py status)") if names else ""
    n = min(len(lines), MAX_LINES)
    while True:
        out = [head] + lines[:n]
        if len(lines) > n:
            out.append(f"… y {len(lines) - n} más: vuln_watch.py status")
        if blind:
            out.append(blind)
        text = "\n".join(out)
        if len(text) <= MSG_CAP or n == 0:
            return text
        n -= 1


# ------------------------------------------------------------------ commands

def configured():
    cfg = load_conf()
    if not (cfg["VULNWATCH_ZBX_URL"] and cfg["VULNWATCH_ZBX_TOKEN"]):
        print("vuln_watch: not configured (VULNWATCH_ZBX_URL/VULNWATCH_ZBX_TOKEN in ops.env)")
        return None
    return cfg


def cmd_run(args):
    cfg = configured()
    if not cfg:
        return 0
    check_token(cfg)
    recs = collect(cfg, args.host)
    kev, red, codenames = load_feeds()
    apply_coverage(recs, codenames)
    products = load_products()
    check_days = int(os.environ.get("VULNWATCH_CHECK_DAYS", "30"))
    found = {}
    for r in recs:
        if r["kind"] == "ok":
            try:
                found.update(match_host(r, kev, red, products, check_days))
            except Exception:           # one garbled host must not stop the others; it keeps its old findings
                r.update(kind="blind", reason="unparsable inventory")
    state = load_state()
    new, ev = reconcile(state["findings"], recs, found, scope_all=not args.host)
    scope = {r["name"] for r in recs}
    blind = {r["name"] for r in recs if r["kind"] == "blind"}
    newly_blind = blind - set(state["blind"])
    msg = build_message(ev, newly_blind)
    if args.dry_run:
        print(msg or "vuln_watch: nothing to report")
        print(f"vuln_watch: dry run, {len(recs)} hosts, {len(found)} findings, no state written, nothing sent")
        return 0
    if msg:
        notify_send(msg)
    save_state({"version": 1, "findings": new, "blind": sorted((set(state["blind"]) - scope) | blind)})
    print(f"vuln_watch: {len(recs)} hosts, {len(found)} findings, {len(ev['new'])} new, {len(ev['fixed'])} fixed"
          + (", message sent" if msg else ""))
    return 0


def age(s):
    if s is None:
        return "unknown"
    return f"{s // 3600} h" if s < 2 * 86400 else f"{s // 86400} d"


def cmd_status(args):
    cfg = configured()
    if not cfg:
        return 0
    check_token(cfg)
    recs = collect(cfg)
    apply_coverage(recs, read_json(os.path.join(state_dir(create=False), "reduced.json"), {}).get("codenames"))
    state = load_state()
    per_host = {}
    for f in state["findings"].values():
        per_host.setdefault(f.get("host"), []).append(f)
    for r in sorted(recs, key=lambda r: r["name"]):
        if r["kind"] == "not_inventoried":
            print(f"{r['name']}: not inventoried")
        elif r["kind"] == "unsupported":
            print(f"{r['name']}: {r['reason']}")
        elif r["kind"] == "blind":
            print(f"{r['name']}: BLIND ({r['reason']})")
        else:
            apt = r["apt"] or {}
            bits = [f"{r['pretty']} [{r['codename']}]", f"{r['count']} packages", f"inventory {age(r['age_s'])} old"]
            if r["partial"]:
                bits.append("partial (truncated shard)")
            if r["reboot"]:
                bits.append("reboot pending")
            if "pending" in apt:
                bits.append(f"updates {apt.get('pending')} (security {apt.get('security')})")
            bits.append(f"open findings {len([f for f in per_host.get(r['name'], []) if f['status'] != 'CHECK'])}")
            print(f"{r['name']}: " + ", ".join(bits))
    print()
    open_f = sorted(state["findings"].values(), key=lambda f: (f.get("due") or "9999", f.get("host", ""), f.get("cve", "")))
    print(f"open findings: {len(open_f)}")
    for f in open_f:
        print("  " + fmt(f, f"[{f['status']}] "))
    return 0


def cmd_feeds(args):
    d = state_dir(create=False)
    for name in ("kev", "tracker"):
        m = read_json(os.path.join(d, name + ".meta.json"), {})
        if not m:
            print(f"{name}: no cache")
            continue
        print(f"{name}: fetched {age(int(now() - m.get('fetched', 0)))} ago, checked {age(int(now() - m.get('checked', 0)))} ago, "
              f"{m.get('size', 0) // 1024} KiB, etag {m.get('etag') or '-'}, last-modified {m.get('last_modified') or '-'}")
    red = read_json(os.path.join(d, "reduced.json"), {})
    print("reduced tracker: " + (f"built {age(int(now() - red.get('built', 0)))} ago, {len(red.get('data', {}))} source packages"
                                 if red else "no cache"))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="vuln_watch.py", description="KEV watch over the Zabbix software inventory")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="inventory, match, notify (the timer)")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--host", help="only this host (name as in Zabbix)")
    sub.add_parser("status", help="per-host state and open findings")
    sub.add_parser("feeds", help="feed cache ages")
    args = p.parse_args(argv)
    try:
        return {"run": cmd_run, "status": cmd_status, "feeds": cmd_feeds}[args.cmd](args)
    except TokenRefused as e:
        print(f"vuln_watch: {e}", file=sys.stderr)
        return 2
    except (ApiError, FeedError) as e:
        print(f"vuln_watch: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
