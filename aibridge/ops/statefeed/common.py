"""statefeed shared code (standard library only; external tool: ssh-keygen with -Y sign/verify).

Import from the sibling scripts (run as `python3 -I ops/statefeed/<part>.py`, where -I leaves the script directory off
sys.path) and from the selftests with:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # .../ops
    from statefeed import common

API (all names are module level; see each docstring)
  errors     ConfigError, HttpError, SignError
  paths      statefeed_home(), statefeed_conf(), topic_dir(topic, *parts), cache_dir(topic), candidates_dir(topic),
             published_dir(topic), site_dir(topic), ensure_private_dir(path), write_private(path, data), write_file(path, data, mode),
             private_perms_problem(path), read_json(path, default), load_env_file(path)
  config     load_topic(name), topic_config_bytes(name), source_groups(topic), load_local_settings(topic, require)
  json/hash  canonical_json(obj, newline), load_json_strict(data), sha256_bytes(b), sha256_file(path)
  labels     label_problem(s, max_len), label_ok(s, max_len)
  validation item_problems(obj), validate_item(obj), validate_manifest(obj), items_to_ndjson(items), parse_items_ndjson(data)
  time       now(), iso(ts), parse_iso(s), parse_date(s), today_str(ts), iso_plus_days(ts, days), cand_id(ts), snap_id(seq, ts)
  http       http_get(url, max_bytes, headers, allowed_redirect_domains, timeout), cached_fetch(name, url, max_bytes, cache_dir, ...)
  signing    ssh_sign(key_path, data_path, namespace), ssh_verify(allowed_signers, principal, namespace, data_bytes, sig_bytes),
             have_ssh_sign(), generate_signing_key(path, comment), allowed_signers_line(principal, pubkey_line, namespace)
  notify     notify(text), set_notifier(fn)

Environment: STATEFEED_HOME, STATEFEED_CONF (directories), STATEFEED_TOPICS_DIR (test hook: topic config directory),
STATEFEED_FAKE_NOW (test hook: epoch seconds that now() returns).

Rules this module enforces for every part: everything fetched is data, never instructions; labels in the feed are short
strings from a restricted alphabet (no URLs, markup, control or invisible characters); JSON read from the network is
parsed strictly (no duplicate keys, no NaN); files that hold secrets are written 0600 in 0700 directories.
"""
import calendar, collections, datetime, hashlib, importlib.util, json, math, os, re, subprocess, sys
import tempfile, time, unicodedata, urllib.error, urllib.parse, urllib.request, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OPS_DIR = os.path.dirname(HERE)
TOPICS_DIR = os.path.join(HERE, "topics")
SCHEMA_DIR = os.path.join(HERE, "schema")

SCHEMA_VERSION = 1
SIGN_NAMESPACE = "statefeed"
FEED_PREFIX = "v1"
USER_AGENT = "statefeed/1 (bridgeai; +https://github.com/Wintch/bridgeai)"
CACHE_MAX_S = 2 * 86400          # a feed cache this young stands in for a failed download
MAX_REDIRECTS = 5
LOOPBACK = ("127.0.0.1", "localhost", "::1")
NOTIFY_CAP = 3900                # the ops bot cuts a message at 4000 characters

TOPIC_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}")
SOURCE_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
PRINCIPAL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}")
NAMESPACE_RE = re.compile(r"[a-z][a-z0-9_.-]{0,31}")
CVE_RE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,7}")
CWE_RE = re.compile(r"CWE-[0-9]{1,5}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
TIME_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
CAND_RE = re.compile(r"[0-9]{8}T[0-9]{6}Z")
SNAP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{1,9}")
FILE_PATH_RE = re.compile(r"v1/snapshots/([0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{1,9})/([a-z0-9][a-z0-9._-]{0,63})")
CHECK_SET_RE = re.compile(r"[0-9A-Za-z._-]{1,64}")
PROJECT_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,57}")
# one place for the label alphabet; `\w` is Unicode word characters (letters, digits, underscore)
LABEL_CLASS = r"[\w .,:;()/+&'#@-]"
_LABEL_RES = {}
LABEL_BANNED = "<>`[]{}"
BAD_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")   # control, format (bidi, zero width), surrogate, private, unassigned, separators


class ConfigError(Exception):
    pass


class HttpError(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


class SignError(Exception):
    pass


# ------------------------------------------------------------------ time

def now():
    """Epoch seconds. STATEFEED_FAKE_NOW overrides it (test hook)."""
    v = os.environ.get("STATEFEED_FAKE_NOW", "")
    if v:
        try:
            return float(v)
        except ValueError:
            pass
    return time.time()


def iso(ts=None):
    """UTC "YYYY-MM-DDTHH:MM:SSZ" for epoch seconds (default: now)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now() if ts is None else ts))


def parse_iso(s):
    """Epoch seconds (int) of an ISO UTC timestamp as written by iso(); ValueError otherwise."""
    if not isinstance(s, str) or not TIME_RE.fullmatch(s):
        raise ValueError("not an ISO UTC timestamp")
    return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))


def parse_date(s):
    """datetime.date for "YYYY-MM-DD" (a real calendar date), else None."""
    if not isinstance(s, str) or not DATE_RE.fullmatch(s):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def today_str(ts=None):
    return time.strftime("%Y-%m-%d", time.gmtime(now() if ts is None else ts))


def iso_plus_days(ts, days):
    return iso(int(ts) + int(days) * 86400)


def cand_id(ts=None):
    """Candidate id: UTC "YYYYMMDDTHHMMSSZ"."""
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now() if ts is None else ts))


def snap_id(seq, ts=None):
    """Snapshot id: "YYYY-MM-DD-<seq>"."""
    return f"{today_str(ts)}-{int(seq)}"


# ------------------------------------------------------------------ paths, private files

def statefeed_home():
    """State directory (default ~/.local/state/statefeed). Not created here: see ensure_private_dir."""
    return os.path.abspath(os.path.expanduser(os.environ.get("STATEFEED_HOME") or "~/.local/state/statefeed"))


def statefeed_conf():
    """Config directory (default ~/.config/statefeed): cloudflare.env, signing_key, <topic>.json. Never in git."""
    return os.path.abspath(os.path.expanduser(os.environ.get("STATEFEED_CONF") or "~/.config/statefeed"))


def _topic_name(topic):
    if not isinstance(topic, str) or not TOPIC_RE.fullmatch(topic):
        raise ConfigError(f"invalid topic name {topic!r}")
    return topic


def topic_dir(topic, *parts):
    """<STATEFEED_HOME>/<topic>/<parts...>; the topic name is checked, so it cannot climb out of the home."""
    return os.path.join(statefeed_home(), _topic_name(topic), *parts)


def candidates_dir(topic):
    return topic_dir(topic, "candidates")


def published_dir(topic):
    return topic_dir(topic, "published")


def site_dir(topic):
    return topic_dir(topic, "site")


def cache_dir(topic):
    return topic_dir(topic, "cache")


def ensure_private_dir(path):
    """Create the directory (and parents) and make the leaf mode 0700."""
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _write_atomic(path, data, mode):
    tmp = f"{path}.part{os.getpid()}"
    try:
        os.unlink(tmp)                      # a planted file or link at the temp name is never written through
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_private(path, data):
    """Atomic write, file mode 0600 (str is written as UTF-8)."""
    _write_atomic(path, data, 0o600)


def write_file(path, data, mode=0o644):
    """Atomic write with an explicit mode (deploy trees, published copies)."""
    _write_atomic(path, data, mode)


def private_perms_problem(path):
    """None when `path` exists, is a regular file owned by us and not readable by group or others, else a short reason."""
    try:
        st = os.stat(path)
    except OSError:
        return f"{os.path.basename(path)}: missing or unreadable"
    if not os.path.isfile(path):
        return f"{os.path.basename(path)}: not a regular file"
    if st.st_mode & 0o077:
        return f"{os.path.basename(path)}: mode {st.st_mode & 0o777:03o} is readable by group or others (chmod 600)"
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        return f"{os.path.basename(path)}: not owned by the running user"
    return None


def read_json(path, default=None):
    try:
        with open(path, "rb") as f:
            return load_json_strict(f.read())
    except (OSError, ValueError):
        return default


def load_env_file(path):
    """{KEY: value} of a KEY=VALUE file (comments and blank lines skipped, quotes stripped). Missing file -> {}."""
    out = {}
    try:
        with open(path) as f:
            for line in f:
                k, sep, v = line.partition("=")
                if sep and k.strip() and not k.lstrip().startswith("#"):
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


# ------------------------------------------------------------------ JSON and hashing

def canonical_json(obj, newline=True):
    """Canonical bytes: sort_keys, separators (",",":"), ensure_ascii=False, UTF-8, NaN refused; one trailing "\\n" unless
    newline=False. Items.ndjson lines and manifest.json are written this way."""
    s = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return s.encode("utf-8") + (b"\n" if newline else b"")


def _no_dupes(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"duplicate key {k!r}")
        d[k] = v
    return d


def _no_const(name):
    raise ValueError(f"{name} is not valid JSON")


def load_json_strict(data):
    """json.loads for untrusted input: bytes or str, strict UTF-8, duplicate keys and NaN/Infinity refused. ValueError on any problem."""
    try:
        if isinstance(data, (bytes, bytearray)):
            data = bytes(data).decode("utf-8")
        return json.loads(data, object_pairs_hook=_no_dupes, parse_constant=_no_const)
    except RecursionError:
        raise ValueError("JSON nested too deeply")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ labels

def _label_re(max_len, brackets):
    r = _LABEL_RES.get((max_len, brackets))
    if r is None:
        cls = LABEL_CLASS[:-2] + r"\[\]-]" if brackets else LABEL_CLASS
        r = _LABEL_RES[(max_len, brackets)] = re.compile(f"{cls}{{1,{int(max_len)}}}")
    return r


def label_problem(s, max_len=120, brackets=False):
    """None if `s` is an acceptable label, else a short reason. A label is 1..max_len characters of letters, digits,
    space and . , : ; ( ) / + & ' # @ - _ ; never a URL ("://"), markup or brackets, control, bidi or zero-width characters.
    brackets=True also allows [ ] (licence texts such as "see sources[].licence"); < > ` { } stay forbidden."""
    if not isinstance(s, str):
        return "not a string"
    if not s:
        return "empty"
    if len(s) > max_len:
        return f"longer than {max_len}"
    for c in s:
        if unicodedata.category(c) in BAD_CATEGORIES:
            return "control, format or invisible character"
    if "://" in s:
        return "contains ://"
    if any(c in (LABEL_BANNED[:3] + LABEL_BANNED[5:] if brackets else LABEL_BANNED) for c in s):
        return "contains markup or bracket characters"
    if not _label_re(max_len, brackets).fullmatch(s):
        return "character outside the label alphabet"
    return None


def label_ok(s, max_len=120):
    return label_problem(s, max_len) is None


# ------------------------------------------------------------------ validation (item, manifest)

def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_unit(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v <= 1


def _date_or_none(v, nullable):
    if v is None:
        return nullable
    return parse_date(v) is not None


def _keys(obj, required, problems, prefix=""):
    """Exact key set: report missing and unknown keys. Returns True when the object is a dict."""
    if not isinstance(obj, dict):
        problems.append((prefix.rstrip(".") or "$", "not an object"))
        return False
    for k in required:
        if k not in obj:
            problems.append((prefix + k, "missing"))
    for k in obj:
        if k not in required:
            problems.append((prefix + str(k), "not allowed"))
    return True


ITEM_KEYS = ("id", "schema_version", "type", "vendor", "product", "name", "date_added", "due_date", "ransomware", "cwes",
             "epss", "epss_percentile", "epss_date", "agreement", "sources", "first_seen")


def item_problems(obj):
    """[(field, reason)] for an item (empty list: valid). `field` is the top-level field, usable in a candidate's invalid list."""
    p = []
    if not _keys(obj, ITEM_KEYS, p):
        return p
    v = obj.get
    def bad(field, why):
        p.append((field, why))
    if "id" in obj and not (isinstance(v("id"), str) and CVE_RE.fullmatch(v("id"))):
        bad("id", "not a CVE id")
    if "schema_version" in obj and not (_is_int(v("schema_version")) and v("schema_version") == SCHEMA_VERSION):
        bad("schema_version", f"must be {SCHEMA_VERSION}")
    if "type" in obj and v("type") != "kev":
        bad("type", 'must be "kev"')
    for field, n in (("vendor", 120), ("product", 120), ("name", 200)):
        if field in obj and (why := label_problem(v(field), n)):
            bad(field, why)
    if "date_added" in obj and not _date_or_none(v("date_added"), False):
        bad("date_added", "not a calendar date YYYY-MM-DD")
    if "due_date" in obj and not _date_or_none(v("due_date"), True):
        bad("due_date", "not a calendar date YYYY-MM-DD or null")
    if "first_seen" in obj and not _date_or_none(v("first_seen"), False):
        bad("first_seen", "not a calendar date YYYY-MM-DD")
    if "epss_date" in obj and not _date_or_none(v("epss_date"), True):
        bad("epss_date", "not a calendar date YYYY-MM-DD or null")
    if "ransomware" in obj and v("ransomware") not in ("known", "unknown"):
        bad("ransomware", 'must be "known" or "unknown"')
    if "cwes" in obj:
        c = v("cwes")
        if not (isinstance(c, list) and len(c) <= 10 and all(isinstance(x, str) and CWE_RE.fullmatch(x) for x in c)):
            bad("cwes", "must be a list of at most 10 CWE-n ids")
    for field in ("epss", "epss_percentile"):
        if field in obj and not (v(field) is None or _is_unit(v(field))):
            bad(field, "must be a number from 0 to 1 or null")
    if "agreement" in obj:
        a = v("agreement")
        sub = []
        if _keys(a, ("state", "channels", "independent"), sub, "agreement."):
            p.extend(("agreement", f"{k.split('.')[-1]}: {w}") for k, w in sub)
            st, ch, ind = a.get("state"), a.get("channels"), a.get("independent")
            if st not in ("authoritative", "single_channel", "disputed"):
                bad("agreement", "state is not one of authoritative, single_channel, disputed")
            if not (_is_int(ch) and 1 <= ch <= 10 and _is_int(ind) and 1 <= ind <= 10):
                bad("agreement", "channels and independent must be integers 1..10")
            else:
                if ind > ch:
                    bad("agreement", "independent is larger than channels")
                if st == "single_channel" and ch != 1:
                    bad("agreement", "single_channel needs channels == 1")
                if st in ("authoritative", "disputed") and ch < 2:
                    bad("agreement", f"{st} needs channels >= 2")
    if "sources" in obj:
        s = v("sources")
        if not (isinstance(s, list) and 1 <= len(s) <= 10):
            bad("sources", "must be a list of 1..10 sources")
        else:
            seen = set()
            for e in s:
                sub = []
                if not _keys(e, ("id", "licence", "content_sha256"), sub, ""):
                    p.extend(("sources", w) for _, w in sub)
                    continue
                p.extend(("sources", f"{k}: {w}") for k, w in sub)
                if not (isinstance(e.get("id"), str) and SOURCE_ID_RE.fullmatch(e["id"])):
                    bad("sources", "bad source id")
                elif e["id"] in seen:
                    bad("sources", "duplicate source id")
                else:
                    seen.add(e["id"])
                if label_problem(e.get("licence"), 60):
                    bad("sources", "bad licence label")
                if not (isinstance(e.get("content_sha256"), str) and SHA256_RE.fullmatch(e["content_sha256"])):
                    bad("sources", "bad content_sha256")
    return p


def validate_item(obj):
    """[error strings] for an item; empty list means valid."""
    return [f"{f}: {w}" for f, w in item_problems(obj)]


def _url_ok(u):
    """https, or http to a loopback host (selftests); printable ASCII only, no userinfo."""
    if not (isinstance(u, str) and re.fullmatch(r"[\x21-\x7e]{1,500}", u)):
        return False
    try:
        sp = urllib.parse.urlsplit(u)
        sp.port
    except ValueError:
        return False
    if not sp.hostname or sp.username is not None or sp.password is not None:
        return False
    return sp.scheme == "https" or (sp.scheme == "http" and sp.hostname in LOOPBACK)


MANIFEST_KEYS = ("topic", "schema_version", "seq", "prev_digest", "generated_at", "valid_until", "item_count", "untrusted_text",
                 "ai_generated", "compiled_by", "licence", "check_set_version", "sources", "files", "snapshot", "publish_record")


def validate_manifest(obj):
    """[error strings] for a manifest object (the unsigned content); empty list means valid."""
    p = []
    if not _keys(obj, MANIFEST_KEYS, p):
        return [f"{f}: {w}" for f, w in p]
    v = obj.get
    def bad(field, why):
        p.append((field, why))
    if "topic" in obj and not (isinstance(v("topic"), str) and TOPIC_RE.fullmatch(v("topic"))):
        bad("topic", "invalid topic name")
    if "schema_version" in obj and not (_is_int(v("schema_version")) and v("schema_version") == SCHEMA_VERSION):
        bad("schema_version", f"must be {SCHEMA_VERSION}")
    seq = v("seq")
    if "seq" in obj and not (_is_int(seq) and 1 <= seq <= 10**9):
        bad("seq", "must be an integer >= 1")
    if "prev_digest" in obj and not (v("prev_digest") is None or (isinstance(v("prev_digest"), str) and SHA256_RE.fullmatch(v("prev_digest")))):
        bad("prev_digest", "must be a sha256 hex string or null")
    times = {}
    for field in ("generated_at", "valid_until"):
        if field in obj:
            try:
                times[field] = parse_iso(v(field))
            except ValueError:
                bad(field, "not an ISO UTC timestamp")
    if len(times) == 2 and times["valid_until"] <= times["generated_at"]:
        bad("valid_until", "must be after generated_at")
    if "item_count" in obj and not (_is_int(v("item_count")) and 0 <= v("item_count") <= 10**7):
        bad("item_count", "must be an integer >= 0")
    for field in ("untrusted_text", "ai_generated"):
        if field in obj and not isinstance(v(field), bool):
            bad(field, "must be a boolean")
    if "compiled_by" in obj and (why := label_problem(v("compiled_by"), 120)):
        bad("compiled_by", why)
    if "licence" in obj:
        lic, sub = v("licence"), []
        if _keys(lic, ("compilation", "records"), sub, "licence."):
            p.extend(sub)
            for k in ("compilation", "records"):
                if k in lic and (why := label_problem(lic[k], 120, brackets=True)):
                    bad("licence", f"{k}: {why}")
        else:
            p.extend(sub)
    if "check_set_version" in obj and not (isinstance(v("check_set_version"), str) and CHECK_SET_RE.fullmatch(v("check_set_version"))):
        bad("check_set_version", "must be 1..64 characters of [0-9A-Za-z._-]")
    if "sources" in obj:
        s = v("sources")
        if not (isinstance(s, list) and 1 <= len(s) <= 20):
            bad("sources", "must be a list of 1..20 sources")
        else:
            seen = set()
            for e in s:
                sub = []
                if not _keys(e, ("id", "url", "retrieved_at", "content_sha256", "bytes", "status"), sub, ""):
                    p.extend(("sources", w) for _, w in sub)
                    continue
                p.extend(("sources", f"{k}: {w}") for k, w in sub)
                sid = e.get("id")
                if not (isinstance(sid, str) and SOURCE_ID_RE.fullmatch(sid)):
                    bad("sources", "bad source id")
                elif sid in seen:
                    bad("sources", f"duplicate source id {sid}")
                else:
                    seen.add(sid)
                if not _url_ok(e.get("url")):
                    bad("sources", f"{sid}: url must be https (or http on loopback), printable ASCII")
                if e.get("status") not in ("ok", "cache", "unavailable"):
                    bad("sources", f"{sid}: status must be ok, cache or unavailable")
                    continue
                sha, at = e.get("content_sha256"), e.get("retrieved_at")
                if not _is_int(e.get("bytes")) or not 0 <= e["bytes"] <= 2**31 - 1:
                    bad("sources", f"{sid}: bytes must be an integer >= 0")
                if e["status"] == "unavailable":
                    if sha is not None or at is not None:
                        bad("sources", f"{sid}: an unavailable source has null content_sha256 and retrieved_at")
                else:
                    if not (isinstance(sha, str) and SHA256_RE.fullmatch(sha)):
                        bad("sources", f"{sid}: bad content_sha256")
                    try:
                        parse_iso(at)
                    except ValueError:
                        bad("sources", f"{sid}: bad retrieved_at")
    snap = v("snapshot")
    if "snapshot" in obj:
        if not (isinstance(snap, str) and SNAP_RE.fullmatch(snap) and parse_date(snap[:10])):
            bad("snapshot", "must be YYYY-MM-DD-<seq>")
        elif _is_int(seq) and snap.split("-", 3)[3] != str(seq):
            bad("snapshot", "does not end with -<seq>")
    if "files" in obj:
        fl = v("files")
        if not (isinstance(fl, list) and 1 <= len(fl) <= 20):
            bad("files", "must be a list of 1..20 files")
        else:
            paths, n_items = set(), 0
            for e in fl:
                sub = []
                if not _keys(e, ("path", "sha256", "bytes"), sub, ""):
                    p.extend(("files", w) for _, w in sub)
                    continue
                p.extend(("files", f"{k}: {w}") for k, w in sub)
                path = e.get("path")
                m = FILE_PATH_RE.fullmatch(path) if isinstance(path, str) else None
                if not m:
                    bad("files", "bad path (v1/snapshots/<snapshot>/<name>)")
                else:
                    if path in paths:
                        bad("files", f"duplicate path {path}")
                    paths.add(path)
                    if isinstance(snap, str) and m[1] != snap:
                        bad("files", f"{path} is not under the manifest's snapshot")
                    n_items += m[2] == "items.ndjson"
                if not (isinstance(e.get("sha256"), str) and SHA256_RE.fullmatch(e["sha256"])):
                    bad("files", "bad sha256")
                if not _is_int(e.get("bytes")) or not 0 <= e["bytes"] <= 2**31 - 1:
                    bad("files", "bytes must be an integer >= 0")
            if n_items != 1 or len(fl) != 1:
                bad("files", "v1 lists exactly one file, items.ndjson")
    if "publish_record" in obj:
        pr, sub = v("publish_record"), []
        if _keys(pr, ("approval",), sub, "publish_record."):
            if pr.get("approval") != "human":
                bad("publish_record", 'approval must be "human"')
        p.extend(sub)
    return [f"{f}: {w}" for f, w in p]


def items_to_ndjson(items):
    """Canonical items.ndjson bytes: items sorted by id, one canonical JSON line each."""
    return b"".join(canonical_json(i) for i in sorted(items, key=lambda i: i["id"]))


def parse_items_ndjson(data, max_errors=50):
    """-> (items, errors) for items.ndjson bytes. Checks: UTF-8, strict JSON per line, every item valid, every line is the
    canonical form of its object, ids sorted and unique, final newline. Items are returned only if there are no errors."""
    errors, items, last = [], [], None
    if not isinstance(data, (bytes, bytearray)):
        return [], ["input is not bytes"]
    if data and not data.endswith(b"\n"):
        errors.append("missing final newline")
    lines = bytes(data).split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    for n, line in enumerate(lines, 1):
        if len(errors) >= max_errors:
            errors.append("... more errors not shown")
            break
        try:
            obj = load_json_strict(line)
        except ValueError as e:
            errors.append(f"line {n}: {e}")
            continue
        errs = validate_item(obj)
        if errs:
            errors.append(f"line {n}: {errs[0]}" + (f" (+{len(errs) - 1} more)" if len(errs) > 1 else ""))
            continue
        if canonical_json(obj, newline=False) != line:
            errors.append(f"line {n}: not in canonical form")
        if last is not None and obj["id"] <= last:
            errors.append(f"line {n}: ids must be sorted and unique")
        last = obj["id"]
        items.append(obj)
    return ([] if errors else items), errors


# ------------------------------------------------------------------ topic and local config

TOPIC_KINDS = ("kev_json", "epss_csv_gz")
TOPIC_ROLES = ("primary", "channel", "enrich")


def _topics_dir():
    return os.environ.get("STATEFEED_TOPICS_DIR") or TOPICS_DIR


def topic_config_bytes(name):
    """Raw bytes of the committed topic config (check_set_version hashes them)."""
    path = os.path.join(_topics_dir(), _topic_name(name) + ".json")
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        raise ConfigError(f"unknown topic {name!r}: {os.path.basename(path)} not found")


def _topic_errors(t, name):
    e = []
    if not isinstance(t, dict):
        return ["topic config is not an object"]
    if t.get("topic") != name:
        e.append("topic does not match the file name")
    if t.get("schema_version") != SCHEMA_VERSION or not _is_int(t.get("schema_version")):
        e.append(f"schema_version must be {SCHEMA_VERSION}")
    for k in ("title", "coverage"):
        if not (isinstance(t.get(k), str) and 1 <= len(t[k]) <= 300 and not any(unicodedata.category(c) in BAD_CATEGORIES for c in t[k])):
            e.append(f"{k} must be a short text")
    srcs = t.get("sources")
    if not (isinstance(srcs, list) and srcs):
        e.append("sources must be a non-empty list")
        srcs = []
    seen = set()
    for s in srcs:
        if not isinstance(s, dict):
            e.append("a source is not an object")
            continue
        sid = s.get("id")
        if not (isinstance(sid, str) and SOURCE_ID_RE.fullmatch(sid)) or sid in seen:
            e.append(f"bad or duplicate source id {sid!r}")
        seen.add(sid)
        if s.get("kind") not in TOPIC_KINDS:
            e.append(f"{sid}: kind must be one of {', '.join(TOPIC_KINDS)}")
        if s.get("role") not in TOPIC_ROLES:
            e.append(f"{sid}: role must be one of {', '.join(TOPIC_ROLES)}")
        if not _url_ok(s.get("url")):
            e.append(f"{sid}: url must be https (http only on loopback)")
        if not (isinstance(s.get("group"), str) and SOURCE_ID_RE.fullmatch(s["group"])):
            e.append(f"{sid}: bad group")
        if label_problem(s.get("licence"), 60):
            e.append(f"{sid}: bad licence label")
        if not (isinstance(s.get("attribution"), str) and 1 <= len(s["attribution"]) <= 200):
            e.append(f"{sid}: bad attribution")
        if parse_date(s.get("terms_checked_on")) is None:
            e.append(f"{sid}: terms_checked_on must be a date")
        if not (_is_int(s.get("max_bytes")) and 1 <= s["max_bytes"] <= 200_000_000):
            e.append(f"{sid}: max_bytes must be 1..200000000")
    if srcs and sum(1 for s in srcs if isinstance(s, dict) and s.get("role") == "primary") != 1:
        e.append("exactly one source must have role primary")
    caps = t.get("caps")
    if not (isinstance(caps, dict) and set(caps) == {"max_removed", "max_new", "max_items_bytes"}
            and all(_is_int(x) and x >= 0 for x in caps.values())):
        e.append("caps must hold non-negative integers max_removed, max_new, max_items_bytes")
    if not (_is_int(t.get("valid_days")) and 1 <= t["valid_days"] <= 30):
        e.append("valid_days must be 1..30")
    if not (_is_int(t.get("retention_snapshots")) and 1 <= t["retention_snapshots"] <= 1000):
        e.append("retention_snapshots must be 1..1000")
    return e


def load_topic(name):
    """Parsed and checked topic config (topics/<name>.json). ConfigError when missing or malformed. Source URLs come only
    from this committed file, never from feed data."""
    raw = topic_config_bytes(name)
    try:
        t = load_json_strict(raw)
    except ValueError as e:
        raise ConfigError(f"topic {name}: not valid JSON ({e})")
    errs = _topic_errors(t, name)
    if errs:
        raise ConfigError(f"topic {name}: " + "; ".join(errs))
    return t


def source_groups(topic):
    """{source id: independence group}. Sources in one group count as ONE independent source."""
    return {s["id"]: s["group"] for s in topic["sources"]}


def load_local_settings(topic, require=False):
    """Local, never-committed settings <STATEFEED_CONF>/<topic>.json:
    {"project": "<pages project>", "base_urls": ["https://..."], "principal": "statefeed-<topic>", "contact": "<text>"}.
    Returns a dict with project, base_urls, principal (default statefeed-<topic>), contact (default ""). With require=True a
    missing or incomplete file raises ConfigError; otherwise missing gives the defaults with project None and base_urls []."""
    _topic_name(topic)
    path = os.path.join(statefeed_conf(), topic + ".json")
    out = {"project": None, "base_urls": [], "principal": f"statefeed-{topic}", "contact": ""}
    if not os.path.exists(path):
        if require:
            raise ConfigError(f"{path} is missing (project, base_urls, principal)")
        return out
    try:
        with open(path, "rb") as f:
            d = load_json_strict(f.read())
    except (OSError, ValueError) as e:
        raise ConfigError(f"{path}: cannot read ({e})")
    if not isinstance(d, dict):
        raise ConfigError(f"{path}: not an object")
    if d.get("project") is not None:
        if not (isinstance(d["project"], str) and PROJECT_RE.fullmatch(d["project"])):
            raise ConfigError(f"{path}: project must be a lowercase Pages project name")
        out["project"] = d["project"]
    if "base_urls" in d:
        bu = d["base_urls"]
        if not (isinstance(bu, list) and all(_url_ok(u) and not u.endswith("/") for u in bu)):
            raise ConfigError(f"{path}: base_urls must be a list of https URLs without a trailing slash")
        out["base_urls"] = list(bu)
    if "principal" in d:
        if not (isinstance(d["principal"], str) and PRINCIPAL_RE.fullmatch(d["principal"])):
            raise ConfigError(f"{path}: bad principal")
        out["principal"] = d["principal"]
    if "contact" in d:
        c = d["contact"]
        if not (isinstance(c, str) and len(c) <= 200 and not any(unicodedata.category(ch) in BAD_CATEGORIES for ch in c)):
            raise ConfigError(f"{path}: contact must be a short plain text")
        out["contact"] = c
    if require and not (out["project"] and out["base_urls"]):
        raise ConfigError(f"{path}: project and base_urls are required")
    return out


# ------------------------------------------------------------------ HTTP

Response = collections.namedtuple("Response", "status body headers url")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None   # redirects are followed by http_get itself, under its policy


_OPENER = urllib.request.build_opener(_NoRedirect)


HOST_RE = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?|::1")


def _check_url(url, prev_scheme=None):
    if not re.fullmatch(r"[\x21-\x7e]{1,2000}", url):
        raise HttpError("malformed URL (printable ASCII only)")      # also covers a Location header with spaces or controls
    try:
        sp = urllib.parse.urlsplit(url)
        sp.port
    except ValueError:
        raise HttpError("malformed URL")
    host = sp.hostname
    if not host or sp.username is not None or sp.password is not None:
        raise HttpError("URL without a host, or with credentials")
    if not HOST_RE.fullmatch(host):
        raise HttpError("malformed host name")                     # e.g. "evil.test\\.good.test" must not pass a suffix check
    if sp.scheme == "https":
        pass
    elif sp.scheme == "http" and host in LOOPBACK and prev_scheme != "https":
        pass
    else:
        raise HttpError(f"only https is allowed (got {sp.scheme})")
    return host


def _domain_ok(host, allowed):
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in (x.lower().strip(".") for x in allowed))


def _decode_gzip(body, max_bytes):
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = d.decompress(body, max_bytes + 1)
        if len(out) > max_bytes or d.unconsumed_tail:
            raise HttpError("decompressed response larger than the cap")
        out += d.flush()
    except zlib.error:
        raise HttpError("bad gzip body")
    if len(out) > max_bytes:
        raise HttpError("decompressed response larger than the cap")
    return out


def http_get(url, max_bytes, headers=None, allowed_redirect_domains=None, timeout=30, total_timeout=None):
    """GET with a size cap and a strict redirect policy. -> Response(status, body, headers (lower-case keys), final url).
    Status is 200..299, or 304 with an empty body (conditional requests). Anything else raises HttpError (.status set for
    HTTP errors, None for network problems). The body is never larger than max_bytes (also after a gzip decode).
    Redirects: at most 5, https only (http only between loopback hosts, for tests, never after an https hop), no credentials in
    URLs, and the target host must equal one of `allowed_redirect_domains` or be a subdomain of it; the default is the
    original host only. Request headers are re-sent on a redirect, so never pass secrets here."""
    hdrs = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    hdrs.update(headers or {})
    host = _check_url(url)
    allowed = list(allowed_redirect_domains) if allowed_redirect_domains is not None else [host]
    deadline = time.monotonic() + (total_timeout or max(60, timeout * 10))
    cur, prev_scheme = url, None
    for _ in range(MAX_REDIRECTS + 1):
        h = _check_url(cur, prev_scheme)
        if cur != url and not _domain_ok(h, allowed):
            raise HttpError("redirect to a host outside the allowed domains")
        try:
            r = _OPENER.open(urllib.request.Request(cur, headers=hdrs), timeout=timeout)
        except urllib.error.HTTPError as e:
            code, loc, rh = e.code, e.headers.get("Location"), {k.lower(): v for k, v in e.headers.items()}
            e.close()
            if code == 304:
                return Response(304, b"", rh, cur)
            if code in (301, 302, 303, 307, 308) and loc:
                prev_scheme = urllib.parse.urlsplit(cur).scheme
                cur = urllib.parse.urljoin(cur, loc)
                continue
            raise HttpError(f"HTTP {code}", code)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise HttpError(f"cannot reach the server ({type(e).__name__})")
        with r:
            rh = {k.lower(): v for k, v in r.headers.items()}
            try:
                if int(rh.get("content-length", "0")) > max_bytes and "content-encoding" not in rh:
                    raise HttpError("response larger than the cap")
            except ValueError:
                pass
            chunks, size = [], 0
            try:
                while True:
                    c = r.read(65536)
                    if not c:
                        break
                    size += len(c)
                    if size > max_bytes:
                        raise HttpError("response larger than the cap")
                    if time.monotonic() > deadline:
                        raise HttpError("download took too long")
                    chunks.append(c)
            except (OSError, ValueError) as e:
                raise HttpError(f"download failed ({type(e).__name__})")
            body = b"".join(chunks)
            if "gzip" in rh.get("content-encoding", "").lower():
                body = _decode_gzip(body, max_bytes)
            return Response(r.status, body, rh, cur)
    raise HttpError("too many redirects")


FetchResult = collections.namedtuple("FetchResult", "status how body sha256 size retrieved_at error")


def cached_fetch(name, url, max_bytes, cache_dir, headers=None, allowed_redirect_domains=None, timeout=60,
                 max_cache_age_s=CACHE_MAX_S, validate=None):
    """Conditional download into `cache_dir` (ETag / Last-Modified), modelled on vuln_watch.refresh.
    -> FetchResult(status, how, body, sha256, size, retrieved_at, error)
       status  "ok" (the server delivered or confirmed the bytes now), "cache" (the download failed and a cache younger than
               max_cache_age_s (default 2 days) stands in), "unavailable" (failed, no usable cache: body is None)
       how     "updated" | "not-modified" | "cache" | "unavailable"
       retrieved_at  epoch seconds of the last time the server delivered or confirmed these bytes
    `validate(body)` may raise to reject a download (an error page, an empty catalog); that counts as a failed download, and
    the cache is not overwritten. Never raises for network or content problems; the error text never contains the URL."""
    if not SOURCE_ID_RE.fullmatch(name):
        raise ConfigError(f"bad cache name {name!r}")
    ensure_private_dir(cache_dir)
    body_path, meta_path = os.path.join(cache_dir, name + ".body"), os.path.join(cache_dir, name + ".meta.json")
    meta = read_json(meta_path, {})
    meta = meta if isinstance(meta, dict) else {}
    cached = None
    if isinstance(meta.get("sha"), str):
        try:
            with open(body_path, "rb") as f:
                b = f.read()
            if sha256_bytes(b) == meta["sha"]:
                cached = b
        except OSError:
            pass
    req = {"User-Agent": USER_AGENT}
    req.update(headers or {})
    if cached is not None and meta.get("etag"):
        req["If-None-Match"] = meta["etag"]
    if cached is not None and meta.get("last_modified"):
        req["If-Modified-Since"] = meta["last_modified"]
    err = ""
    try:
        r = http_get(url, max_bytes, req, allowed_redirect_domains, timeout)
        if r.status == 304:
            if cached is None:
                raise HttpError("unexpected 304")
            meta["checked"] = now()
            write_private(meta_path, json.dumps(meta))
            return FetchResult("ok", "not-modified", cached, meta["sha"], len(cached), meta["checked"], "")
        if validate is not None:
            try:
                validate(r.body)
            except Exception as e:
                raise HttpError(f"content rejected ({type(e).__name__})")
        t = now()
        meta = {"etag": r.headers.get("etag"), "last_modified": r.headers.get("last-modified"), "sha": sha256_bytes(r.body),
                "size": len(r.body), "fetched": t, "checked": t}
        write_private(body_path, r.body)
        write_private(meta_path, json.dumps(meta))
        return FetchResult("ok", "updated", r.body, meta["sha"], len(r.body), t, "")
    except HttpError as e:
        err = str(e)
    except OSError as e:
        err = f"cache write failed ({type(e).__name__})"
    checked = meta.get("checked")
    if cached is not None and isinstance(checked, (int, float)) and 0 <= now() - checked < max_cache_age_s:
        return FetchResult("cache", "cache", cached, meta["sha"], len(cached), checked, err)
    return FetchResult("unavailable", "unavailable", None, None, 0, None, err)


# ------------------------------------------------------------------ SSH signatures (ssh-keygen -Y)

def _ssh_env():
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/"), "LC_ALL": "C"}


def _ssh_run(argv, data=None, timeout=30):
    try:
        return subprocess.run(argv, input=data, stdin=None if data is not None else subprocess.DEVNULL, capture_output=True,
                              timeout=timeout, env=_ssh_env(), start_new_session=True)   # no tty: a passphrase prompt cannot hang
    except FileNotFoundError:
        raise SignError("ssh-keygen is not installed")
    except subprocess.TimeoutExpired:
        raise SignError("ssh-keygen timed out")
    except OSError as e:
        raise SignError(f"cannot run ssh-keygen ({type(e).__name__})")


def have_ssh_sign():
    """True when ssh-keygen exists and knows -Y sign."""
    try:
        r = _ssh_run(["ssh-keygen", "-Y", "sign"], timeout=10)
    except SignError:
        return False
    return b"unknown option" not in r.stderr.lower() and b"illegal option" not in r.stderr.lower() and b"namespace" in r.stderr.lower()


def ssh_sign(key_path, data_path, namespace=SIGN_NAMESPACE, timeout=30):
    """Sign the file with `ssh-keygen -Y sign -f key -n namespace data`; returns the signature path (<data_path>.sig).
    SignError on any failure (exit code, missing or empty signature). The key must be unencrypted (no prompt is possible)."""
    if not NAMESPACE_RE.fullmatch(namespace):
        raise SignError("bad namespace")
    key, data = os.path.abspath(key_path), os.path.abspath(data_path)
    if not os.path.isfile(key):
        raise SignError("signing key not found")
    if not os.path.isfile(data):
        raise SignError("file to sign not found")
    sig = data + ".sig"
    try:
        os.unlink(sig)
    except FileNotFoundError:
        pass
    r = _ssh_run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", namespace, data], timeout=timeout)
    if r.returncode != 0:
        why = r.stderr.decode("utf-8", "replace").replace(key, "<signing key>").replace(data, "<manifest>").strip()[:200]
        raise SignError(f"ssh-keygen sign failed (exit {r.returncode}): {why}")
    if not os.path.isfile(sig) or os.path.getsize(sig) == 0:
        raise SignError("ssh-keygen reported success but wrote no signature")
    return sig


def ssh_verify(allowed_signers, principal, namespace, data_bytes, sig_bytes, timeout=30):
    """True only if `ssh-keygen -Y verify` accepts the signature for `principal` in `namespace` over data_bytes
    (allowed_signers is a file path; it decides which keys are trusted and may carry valid-after/valid-before).
    False for any verification failure. SignError when verification could not be attempted (tool missing, unreadable
    allowed_signers, bad arguments), so a broken setup is not mistaken for a forged signature."""
    if not PRINCIPAL_RE.fullmatch(principal or "") or not NAMESPACE_RE.fullmatch(namespace or ""):
        raise SignError("bad principal or namespace")
    if not os.path.isfile(allowed_signers) or not os.access(allowed_signers, os.R_OK):
        raise SignError("allowed_signers file not readable")
    if not isinstance(data_bytes, (bytes, bytearray)) or not isinstance(sig_bytes, (bytes, bytearray)):
        raise SignError("data and signature must be bytes")
    if not sig_bytes or len(sig_bytes) > 16384:
        return False
    with tempfile.TemporaryDirectory(prefix="sf-verify-") as d:
        sigf = os.path.join(d, "s.sig")
        write_private(sigf, bytes(sig_bytes))
        r = _ssh_run(["ssh-keygen", "-Y", "verify", "-f", os.path.abspath(allowed_signers), "-I", principal, "-n", namespace,
                      "-s", sigf], data=bytes(data_bytes), timeout=timeout)
    return r.returncode == 0 and b'Good "' in r.stdout


def generate_signing_key(path, comment="statefeed"):
    """Create an unencrypted ed25519 key pair at `path` (+ .pub), mode 0600; refuses to overwrite. Returns the public key line."""
    path = os.path.abspath(path)
    if os.path.exists(path) or os.path.exists(path + ".pub"):
        raise SignError("key already exists; refusing to overwrite")
    ensure_private_dir(os.path.dirname(path))
    r = _ssh_run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", path], timeout=30)
    if r.returncode != 0:
        raise SignError(f"ssh-keygen failed (exit {r.returncode})")
    os.chmod(path, 0o600)
    with open(path + ".pub") as f:
        return f.read().strip()


def allowed_signers_line(principal, pubkey_line, namespace=SIGN_NAMESPACE, valid_after=None, valid_before=None):
    """One allowed_signers line: `<principal> namespaces="<ns>"[,valid-after=..][,valid-before=..] <keytype> <base64>`.
    valid_after/valid_before are "YYYYMMDD" strings (for key rotation, two lines)."""
    parts = (pubkey_line or "").split()
    if not PRINCIPAL_RE.fullmatch(principal or "") or not NAMESPACE_RE.fullmatch(namespace or ""):
        raise SignError("bad principal or namespace")
    if len(parts) < 2 or not re.fullmatch(r"[a-z0-9@.-]+", parts[0]) or not re.fullmatch(r"[A-Za-z0-9+/=]+", parts[1]):
        raise SignError("not a public key line")
    opts = f'namespaces="{namespace}"'
    for k, val in (("valid-after", valid_after), ("valid-before", valid_before)):
        if val is not None:
            if not re.fullmatch(r"[0-9]{8}([0-9]{4}([0-9]{2})?)?Z?", str(val)):
                raise SignError(f"bad {k}")
            opts += f',{k}="{val}"'
    return f"{principal} {opts} {parts[0]} {parts[1]}"


# ------------------------------------------------------------------ operator messages

_NOTIFIER = None
_NOTIFY_MOD = None


def set_notifier(fn):
    """Replace the message sink (selftests, or None to restore the default). fn(text) -> truthy when delivered."""
    global _NOTIFIER
    _NOTIFIER = fn


def _load_notify_module():
    global _NOTIFY_MOD
    if _NOTIFY_MOD is None:
        path = os.path.join(OPS_DIR, "lib", "notify.py")
        spec = importlib.util.spec_from_file_location("statefeed_ops_notify", path)
        if spec is None or spec.loader is None:
            raise ImportError("ops/lib/notify.py not found")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _NOTIFY_MOD = mod
    return _NOTIFY_MOD


def notify(text):
    """Send one operator message through ops/lib/notify.py send() when that module is importable and the bot is configured
    (OPS_BOT_TOKEN and OPS_CHAT_ID); otherwise print it. -> True when the bot delivered it. Control characters are removed
    and the text is cut at 3900 characters. Pass ids and counts only, never item text."""
    text = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") and c != "\n" else c for c in str(text))[:NOTIFY_CAP]
    if _NOTIFIER is not None:
        return bool(_NOTIFIER(text))
    try:
        mod = _load_notify_module()
        conf = mod._conf()
        configured = bool(conf.get("OPS_BOT_TOKEN") and conf.get("OPS_CHAT_ID"))
    except Exception:
        configured = False
    if configured:
        try:
            return bool(mod.send(text))
        except Exception as e:
            print(f"statefeed: ops notify failed ({type(e).__name__})", file=sys.stderr, flush=True)
    print("statefeed notify:", text, flush=True)
    return False
