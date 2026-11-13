#!/usr/bin/env python3
"""Offline test of statefeed/common.py: canonical JSON and hashes, label rules, item and manifest validation (and that the
published JSON Schema files agree with the code), topic and local config, private files, http_get redirect and size policy,
the conditional-GET cache, SSH signatures with a throwaway key, and the notify sink. No network: local http.server on 127.0.0.1.
Stdlib only: python3 -I ops/statefeed_common_selftest.py"""
import copy, gzip, http.server, json, os, re, stat, sys, tempfile, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from statefeed import common as c

os.environ["no_proxy"] = "*"
for k in list(os.environ):
    if k.startswith("STATEFEED_"):
        del os.environ[k]
TMP = tempfile.mkdtemp(prefix="sf-common-")
os.environ["STATEFEED_HOME"] = os.path.join(TMP, "home")
os.environ["STATEFEED_CONF"] = os.path.join(TMP, "conf")
fails = []


def check(name, ok, detail=""):
    if ok:
        print(f"ok {name}")
    else:
        fails.append(name)
        print(f"FAIL {name} {detail}")


def raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc:
        return True
    except Exception:
        return False
    return False


# ------------------------------------------------------------------ 1. canonical JSON, hashing
a = {"b": 1, "a": [1, 2, {"z": "é", "y": None}]}
b = {"a": [1, 2, {"y": None, "z": "é"}], "b": 1}
check("canonical JSON is stable and sorted", c.canonical_json(a) == c.canonical_json(b)
      == '{"a":[1,2,{"y":null,"z":"é"}],"b":1}\n'.encode())
check("canonical JSON has no trailing newline on request", not c.canonical_json(a, newline=False).endswith(b"\n"))
check("canonical JSON refuses NaN", raises(ValueError, c.canonical_json, {"x": float("nan")}))
check("strict loader refuses duplicate keys, NaN and bad UTF-8",
      raises(ValueError, c.load_json_strict, '{"a":1,"a":2}') and raises(ValueError, c.load_json_strict, '{"a":NaN}')
      and raises(ValueError, c.load_json_strict, b"\xff\xfe") and c.load_json_strict(b'{"a":[1]}') == {"a": [1]})
check("strict loader survives deep nesting", raises(ValueError, c.load_json_strict, "[" * 100000 + "]" * 100000))
check("sha256 of bytes", c.sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
p = os.path.join(TMP, "f.bin")
open(p, "wb").write(b"abc")
check("sha256 of a file equals the bytes hash", c.sha256_file(p) == c.sha256_bytes(b"abc"))

# ------------------------------------------------------------------ 2. labels
good = ["Microsoft", "Windows Kernel", "Apache Struts 2", "Cisco IOS XE Web UI", "Zoho ManageEngine (ADSelfService)", "D-Link DIR-859",
        "Fortinet FortiOS SSL-VPN: Out-of-Bounds Write", "Oracle Java SE, GlassFish", "Cámara/Año Ünïcode", "Ivanti EPMM & MDM", "ЦБ Россия",
        "Joomla! Joomla!".replace("!", ""), "O'Reilly #1 @home", "a" * 120]
check("labels accept real KEV-like names", all(c.label_ok(x) for x in good), [x for x in good if not c.label_ok(x)])
badl = {"empty": "", "too long": "a" * 121, "newline": "a\nb", "tab": "a\tb", "bidi override": "a\u202eb", "zero width": "a\u200bb",
        "bidi isolate": "\u2066x", "url": "see http://x.test", "scheme only": "a://b", "script": "<script>alert(1)</script>",
        "backtick": "a`b", "brackets": "a [b]", "braces": "a {b}", "angle": "a>b", "nbsp": "a\u00a0b", "pipe": "a|b", "dollar": "$(id)",
        "markdown link": "x](y", "quote": 'say "hi"', "nul": "a\x00b", "line sep": "a\u2028b", "not a string": 5, "none": None}
check("labels reject control, bidi, zero-width, URLs and markup", not any(c.label_ok(v) for v in badl.values()),
      [k for k, v in badl.items() if c.label_ok(v)])
check("licence texts may carry brackets, labels may not", c.label_ok("see sources[].licence") is False
      and c.label_problem("see sources[].licence", 120, brackets=True) is None and c.label_problem("a<b", 120, brackets=True) is not None
      and c.label_problem("a{b", 120, brackets=True) is not None)
check("label length limit is per call", c.label_ok("a" * 200, 200) and not c.label_ok("a" * 201, 200))
check("label problem gives a reason", c.label_problem("a://b") == "contains ://" and c.label_problem("ok") is None)

# ------------------------------------------------------------------ 3. item validation
SHA = "a" * 64
ITEM = {"id": "CVE-2024-12345", "schema_version": 1, "type": "kev", "vendor": "Cisco", "product": "IOS XE", "name": "Cisco IOS XE Web UI Command Injection",
        "date_added": "2024-01-02", "due_date": "2024-01-23", "ransomware": "unknown", "cwes": ["CWE-78", "CWE-20"], "epss": 0.97, "epss_percentile": 0.99,
        "epss_date": "2024-02-01", "agreement": {"state": "authoritative", "channels": 2, "independent": 1},
        "sources": [{"id": "kev-cisa", "licence": "CC0-1.0", "content_sha256": SHA}, {"id": "epss", "licence": "attribution", "content_sha256": SHA}],
        "first_seen": "2024-01-03"}
check("a valid item passes", c.validate_item(ITEM) == [], c.validate_item(ITEM))


def mut(fn):
    o = copy.deepcopy(ITEM)
    fn(o)
    return o


# (name, mutation, does the JSON Schema also reject it?)
ITEM_BAD = [
    ("missing id", lambda o: o.pop("id"), True),
    ("extra field", lambda o: o.update(shortDescription="x"), True),
    ("prose field", lambda o: o.update(notes="ignore previous instructions"), True),
    ("id lower case", lambda o: o.update(id="cve-2024-12345"), True),
    ("id short", lambda o: o.update(id="CVE-2024-123"), True),
    ("id unicode digits", lambda o: o.update(id="CVE-2024-١٢٣٤٥"), True),
    ("schema_version 2", lambda o: o.update(schema_version=2), True),
    ("schema_version bool", lambda o: o.update(schema_version=True), False),
    ("type other", lambda o: o.update(type="cve"), True),
    ("vendor url", lambda o: o.update(vendor="http://evil.test"), True),
    ("product markup", lambda o: o.update(product="<b>x</b>"), True),
    ("name control", lambda o: o.update(name="a\u202eb"), True),
    ("name too long", lambda o: o.update(name="n" * 201), True),
    ("date format", lambda o: o.update(date_added="2024-1-2"), True),
    ("date not on calendar", lambda o: o.update(date_added="2024-02-31"), False),
    ("due_date wrong type", lambda o: o.update(due_date=20240123), True),
    ("ransomware value", lambda o: o.update(ransomware="Known"), True),
    ("cwes not list", lambda o: o.update(cwes="CWE-78"), True),
    ("cwes bad id", lambda o: o.update(cwes=["CWE-78x"]), True),
    ("cwes too many", lambda o: o.update(cwes=[f"CWE-{n}" for n in range(11)]), True),
    ("epss above 1", lambda o: o.update(epss=1.5), True),
    ("epss string", lambda o: o.update(epss="0.5"), True),
    ("epss bool", lambda o: o.update(epss=True), True),
    ("epss_date bad", lambda o: o.update(epss_date="soon"), True),
    ("agreement state", lambda o: o["agreement"].update(state="maybe"), True),
    ("agreement extra", lambda o: o["agreement"].update(x=1), True),
    ("agreement channels 0", lambda o: o["agreement"].update(channels=0), True),
    ("agreement independent > channels", lambda o: o["agreement"].update(independent=3), False),
    ("single_channel with 2 channels", lambda o: o["agreement"].update(state="single_channel"), False),
    ("authoritative with 1 channel", lambda o: o["agreement"].update(channels=1), False),
    ("sources empty", lambda o: o.update(sources=[]), True),
    ("source id bad", lambda o: o["sources"][0].update(id="Bad Id"), True),
    ("source hash bad", lambda o: o["sources"][0].update(content_sha256="zz"), True),
    ("source extra", lambda o: o["sources"][0].update(url="https://x.test"), True),
    ("source duplicate", lambda o: o["sources"].append(copy.deepcopy(o["sources"][0])), False),
    ("source licence markup", lambda o: o["sources"][0].update(licence="[x](y)"), True),
    ("first_seen null", lambda o: o.update(first_seen=None), True),
    ("not an object", None, True),
]
ok = True
for name, fn, _ in ITEM_BAD:
    o = [1, 2] if fn is None else mut(fn)
    if not c.validate_item(o):
        ok = False
        print("   item accepted:", name)
check("validate_item rejects every bad variant", ok)
check("item_problems names the field", ("vendor", "contains ://") in c.item_problems(mut(lambda o: o.update(vendor="http://evil.test"))))
nullable = mut(lambda o: o.update(due_date=None, epss=None, epss_percentile=None, epss_date=None, cwes=[]))
check("nullable fields and empty cwes are valid", c.validate_item(nullable) == [])
check("integer epss 0 and 1 are valid", c.validate_item(mut(lambda o: o.update(epss=0, epss_percentile=1))) == [])

# ------------------------------------------------------------------ 4. manifest validation
MAN = {"topic": "vulns", "schema_version": 1, "seq": 3, "prev_digest": SHA, "generated_at": "2026-11-13T09:30:00Z", "valid_until": "2026-11-16T09:30:00Z",
       "item_count": 2, "untrusted_text": False, "ai_generated": False, "compiled_by": "statefeed/1 (code, no AI)",
       "licence": {"compilation": "CC-BY-4.0", "records": "see sources[].licence"}, "check_set_version": "0123456789ab",
       "sources": [{"id": "kev-cisa", "url": "https://example.test/kev.json", "retrieved_at": "2026-11-13T09:29:00Z", "content_sha256": SHA, "bytes": 100, "status": "ok"},
                   {"id": "epss", "url": "https://example.test/epss.csv.gz", "retrieved_at": "2026-11-12T09:29:00Z", "content_sha256": SHA, "bytes": 50, "status": "cache"},
                   {"id": "kev-github", "url": "http://127.0.0.1:8080/kev.json", "retrieved_at": None, "content_sha256": None, "bytes": 0, "status": "unavailable"}],
       "files": [{"path": "v1/snapshots/2026-11-13-3/items.ndjson", "sha256": SHA, "bytes": 1234}], "snapshot": "2026-11-13-3",
       "publish_record": {"approval": "human"}}
check("a valid manifest passes", c.validate_manifest(MAN) == [], c.validate_manifest(MAN))


def mm(fn):
    o = copy.deepcopy(MAN)
    fn(o)
    return o


MAN_BAD = [
    ("missing key", lambda o: o.pop("seq"), True),
    ("extra key", lambda o: o.update(signature="x"), True),
    ("topic bad", lambda o: o.update(topic="Vulns"), True),
    ("schema_version 2", lambda o: o.update(schema_version=2), True),
    ("seq 0", lambda o: o.update(seq=0), True),
    ("seq string", lambda o: o.update(seq="3"), True),
    ("seq bool", lambda o: o.update(seq=True), False),
    ("prev_digest short", lambda o: o.update(prev_digest="abc"), True),
    ("generated_at format", lambda o: o.update(generated_at="2026-11-13 09:30:00"), True),
    ("generated_at not real", lambda o: o.update(generated_at="2026-02-30T09:30:00Z"), False),
    ("valid_until before generated", lambda o: o.update(valid_until="2026-11-12T09:30:00Z"), False),
    ("item_count negative", lambda o: o.update(item_count=-1), True),
    ("untrusted_text string", lambda o: o.update(untrusted_text="no"), True),
    ("compiled_by url", lambda o: o.update(compiled_by="http://x.test"), True),
    ("licence extra", lambda o: o["licence"].update(x="y"), True),
    ("check_set_version space", lambda o: o.update(check_set_version="a b"), True),
    ("sources empty", lambda o: o.update(sources=[]), True),
    ("source url http non-loopback", lambda o: o["sources"][0].update(url="http://example.test/x"), True),
    ("source url userinfo", lambda o: o["sources"][0].update(url="https://u:p@example.test/x"), False),
    ("source url space", lambda o: o["sources"][0].update(url="https://example.test/a b"), True),
    ("source status", lambda o: o["sources"][0].update(status="fine"), True),
    ("source hash null while ok", lambda o: o["sources"][0].update(content_sha256=None), False),
    ("unavailable with hash", lambda o: o["sources"][2].update(content_sha256=SHA), False),
    ("source duplicate id", lambda o: o["sources"][1].update(id="kev-cisa"), False),
    ("files empty", lambda o: o.update(files=[]), True),
    ("file path escapes", lambda o: o["files"][0].update(path="v1/snapshots/2026-11-13-3/../../x"), True),
    ("file path other snapshot", lambda o: o["files"][0].update(path="v1/snapshots/2026-11-12-3/items.ndjson"), False),
    ("file path not v1", lambda o: o["files"][0].update(path="items.ndjson"), True),
    ("no items file", lambda o: o["files"][0].update(path="v1/snapshots/2026-11-13-3/other.json"), False),
    ("a second file besides items.ndjson", lambda o: o["files"].append({"path": "v1/snapshots/2026-11-13-3/other.json", "sha256": SHA, "bytes": 1}), True),
    ("file duplicate", lambda o: o["files"].append(copy.deepcopy(o["files"][0])), False),
    ("file hash bad", lambda o: o["files"][0].update(sha256="x"), True),
    ("snapshot wrong seq", lambda o: o.update(snapshot="2026-11-13-4"), False),
    ("snapshot format", lambda o: o.update(snapshot="today-3"), True),
    ("publish_record auto", lambda o: o["publish_record"].update(approval="auto"), True),
    ("publish_record extra", lambda o: o["publish_record"].update(by="x"), True),
    ("not an object", None, True),
]
ok = True
for name, fn, _ in MAN_BAD:
    o = "x" if fn is None else mm(fn)
    if not c.validate_manifest(o):
        ok = False
        print("   manifest accepted:", name)
check("validate_manifest rejects every bad variant", ok)

# ------------------------------------------------------------------ 5. the JSON Schema files agree with the code

def _rx(pat):
    return re.compile(pat.replace("\\p{L}\\p{N}", "\\w"))     # ECMA \p{L}\p{N}_ equals Python \w


def schema_errors(schema, inst, root=None, path="$"):
    """A tiny JSON Schema subset checker: just the keywords the two feed schemas use."""
    root = root or schema
    if "$ref" in schema:
        node = root
        for part in schema["$ref"][2:].split("/"):
            node = node[part]
        return schema_errors(node, inst, root, path)
    e = []
    if "anyOf" in schema:
        if not any(not schema_errors(s, inst, root, path) for s in schema["anyOf"]):
            e.append(f"{path}: no anyOf branch matches")
    if "not" in schema and not schema_errors(schema["not"], inst, root, path):
        e.append(f"{path}: matches a forbidden schema")
    if "const" in schema and (inst != schema["const"] or isinstance(inst, bool) != isinstance(schema["const"], bool)):
        e.append(f"{path}: const")
    if "enum" in schema and inst not in schema["enum"]:
        e.append(f"{path}: enum")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        def is_t(t):
            return {"object": isinstance(inst, dict), "array": isinstance(inst, list), "string": isinstance(inst, str), "null": inst is None,
                    "boolean": isinstance(inst, bool), "integer": isinstance(inst, int) and not isinstance(inst, bool),
                    "number": isinstance(inst, (int, float)) and not isinstance(inst, bool)}[t]
        if not any(is_t(t) for t in types):
            return e + [f"{path}: type"]
    if isinstance(inst, str):
        if "pattern" in schema and not _rx(schema["pattern"]).search(inst):
            e.append(f"{path}: pattern")
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            e.append(f"{path}: minimum")
        if "maximum" in schema and inst > schema["maximum"]:
            e.append(f"{path}: maximum")
    if isinstance(inst, list):
        if len(inst) > schema.get("maxItems", 10**9) or len(inst) < schema.get("minItems", 0):
            e.append(f"{path}: item count")
        if "items" in schema:
            for n, x in enumerate(inst):
                e += schema_errors(schema["items"], x, root, f"{path}[{n}]")
    if isinstance(inst, dict):
        for k in schema.get("required", []):
            if k not in inst:
                e.append(f"{path}.{k}: required")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            e += [f"{path}.{k}: additional property" for k in inst if k not in props]
        for k, sub in props.items():
            if k in inst:
                e += schema_errors(sub, inst[k], root, f"{path}.{k}")
    return e


ITEM_SCHEMA = json.load(open(os.path.join(c.SCHEMA_DIR, "item.1.json")))
MAN_SCHEMA = json.load(open(os.path.join(c.SCHEMA_DIR, "manifest.1.json")))
check("schema accepts the valid item and the nullable variant", not schema_errors(ITEM_SCHEMA, ITEM) and not schema_errors(ITEM_SCHEMA, nullable))
check("schema accepts the valid manifest", not schema_errors(MAN_SCHEMA, MAN), schema_errors(MAN_SCHEMA, MAN)[:3])
disagree = []
for name, fn, schema_rejects in ITEM_BAD:
    o = [1, 2] if fn is None else mut(fn)
    if schema_rejects and not schema_errors(ITEM_SCHEMA, o):
        disagree.append("item: " + name)
for name, fn, schema_rejects in MAN_BAD:
    o = "x" if fn is None else mm(fn)
    if schema_rejects and not schema_errors(MAN_SCHEMA, o):
        disagree.append("manifest: " + name)
check("the JSON Schema files reject what the code rejects (where JSON Schema can say so)", not disagree, disagree)
check("label corpus: schema and code agree", all(
    bool(schema_errors(ITEM_SCHEMA["$defs"]["label120"], v)) == (not c.label_ok(v)) for v in list(badl.values()) + good if isinstance(v, str)))
check("schema documents declare their version",
      ITEM_SCHEMA["properties"]["schema_version"]["const"] == 1 and MAN_SCHEMA["properties"]["schema_version"]["const"] == 1
      and all("2020-12" in s["$schema"] for s in (ITEM_SCHEMA, MAN_SCHEMA)))

# ------------------------------------------------------------------ 6. items.ndjson
items = [mut(lambda o: o.update(id="CVE-2024-00002")), mut(lambda o: o.update(id="CVE-2023-99999")), copy.deepcopy(ITEM)]
nd = c.items_to_ndjson(items)
got, errs = c.parse_items_ndjson(nd)
check("ndjson round trip: sorted by id, canonical, valid", errs == [] and [i["id"] for i in got] == ["CVE-2023-99999", "CVE-2024-00002", "CVE-2024-12345"]
      and nd.endswith(b"\n") and nd.count(b"\n") == 3, errs)
check("ndjson refuses a missing final newline", c.parse_items_ndjson(nd[:-1])[1] != [])
check("ndjson refuses unsorted lines", c.parse_items_ndjson(b"".join(reversed(nd.splitlines(True))))[1] != [])
check("ndjson refuses duplicate ids", c.parse_items_ndjson(nd.splitlines(True)[0] * 2)[1] != [])
check("ndjson refuses non-canonical spacing", c.parse_items_ndjson(json.dumps(ITEM, sort_keys=True).encode() + b"\n")[1] != [])
check("ndjson refuses a bad item and a duplicate key line", c.parse_items_ndjson(b'{"id":"x"}\n')[1] != [] and c.parse_items_ndjson(b'{"id":"a","id":"b"}\n')[1] != [])
check("empty ndjson is valid (zero items)", c.parse_items_ndjson(b"") == ([], []))

# ------------------------------------------------------------------ 7. time helpers
check("iso/parse_iso round trip", c.parse_iso(c.iso(1700000000)) == 1700000000 and c.iso(0) == "1970-01-01T00:00:00Z")
check("parse_iso refuses other shapes", raises(ValueError, c.parse_iso, "2026-11-13") and raises(ValueError, c.parse_iso, "2026-13-01T00:00:00Z"))
check("parse_date is strict", c.parse_date("2026-02-28") and c.parse_date("2026-02-30") is None and c.parse_date("2026-2-3") is None and c.parse_date(None) is None)
os.environ["STATEFEED_FAKE_NOW"] = "1794000000"       # 2026-11-06 20:00:00 UTC
check("fake clock drives now, ids and day arithmetic", c.now() == 1794000000 and c.cand_id() == "20261106T212000Z" and c.snap_id(4) == "2026-11-06-4"
      and c.iso_plus_days(c.now(), 3) == "2026-11-09T21:20:00Z" and c.today_str() == "2026-11-06" and c.iso() == "2026-11-06T21:20:00Z")
del os.environ["STATEFEED_FAKE_NOW"]
check("real clock when no override", abs(c.now() - time.time()) < 5)

# ------------------------------------------------------------------ 8. paths and private files
check("paths follow the environment", c.statefeed_home() == os.path.join(TMP, "home") and c.statefeed_conf() == os.path.join(TMP, "conf")
      and c.topic_dir("vulns", "x") == os.path.join(TMP, "home", "vulns", "x") and c.candidates_dir("vulns").endswith("vulns/candidates")
      and c.published_dir("vulns").endswith("vulns/published") and c.site_dir("vulns").endswith("vulns/site") and c.cache_dir("vulns").endswith("vulns/cache"))
check("topic names cannot climb out", all(raises(c.ConfigError, c.topic_dir, t) for t in ("../x", "a/b", "", "A", ".hidden")))
d = c.ensure_private_dir(os.path.join(TMP, "priv", "sub"))
check("private dir is 0700", stat.S_IMODE(os.stat(d).st_mode) == 0o700)
f = os.path.join(d, "secret")
c.write_private(f, "s3cret")
check("private file is 0600 and replaced atomically", stat.S_IMODE(os.stat(f).st_mode) == 0o600 and open(f).read() == "s3cret"
      and not [x for x in os.listdir(d) if ".part" in x])
c.write_private(f, b"again")
check("private overwrite works", open(f, "rb").read() == b"again")
g = os.path.join(d, "pub")
c.write_file(g, b"x")
check("write_file default is 0644", stat.S_IMODE(os.stat(g).st_mode) == 0o644)
check("perms check accepts 0600 and names the problem for 0640, 0644, missing",
      c.private_perms_problem(f) is None and c.private_perms_problem(g) and (os.chmod(f, 0o640) or c.private_perms_problem(f))
      and c.private_perms_problem(os.path.join(d, "nope")))
os.chmod(f, 0o600)
env = os.path.join(TMP, "x.env")
open(env, "w").write('# c\nCLOUDFLARE_ACCOUNT_ID="abc"\nCLOUDFLARE_API_TOKEN=tok=en\n\nbad line\n')
check("env file parser", c.load_env_file(env) == {"CLOUDFLARE_ACCOUNT_ID": "abc", "CLOUDFLARE_API_TOKEN": "tok=en"} and c.load_env_file(env + "x") == {})

# ------------------------------------------------------------------ 9. topic and local settings
t = c.load_topic("vulns")
check("the committed vulns topic loads", t["topic"] == "vulns" and len(t["sources"]) == 3 and t["valid_days"] == 3 and t["caps"]["max_removed"] == 10)
check("independence groups: the two KEV channels are one source",
      c.source_groups(t) == {"kev-cisa": "cisa", "kev-github": "cisa", "epss": "first"})
check("topic config bytes are the file's", c.topic_config_bytes("vulns") == open(os.path.join(c.TOPICS_DIR, "vulns.json"), "rb").read())
check("unknown topic is a ConfigError", raises(c.ConfigError, c.load_topic, "nope"))
td = os.path.join(TMP, "topics")
os.makedirs(td)
os.environ["STATEFEED_TOPICS_DIR"] = td


def topic_with(fn):
    o = copy.deepcopy(t)
    fn(o)
    open(os.path.join(td, "vulns.json"), "w").write(json.dumps(o))
    return o


bads = {"http url": lambda o: o["sources"][0].update(url="http://example.test/x"), "no primary": lambda o: o["sources"][0].update(role="channel"),
        "two primaries": lambda o: o["sources"][1].update(role="primary"), "dup id": lambda o: o["sources"][1].update(id="kev-cisa"),
        "bad kind": lambda o: o["sources"][0].update(kind="html"), "caps negative": lambda o: o["caps"].update(max_new=-1),
        "valid_days 0": lambda o: o.update(valid_days=0), "retention str": lambda o: o.update(retention_snapshots="60"),
        "topic mismatch": lambda o: o.update(topic="other"), "max_bytes huge": lambda o: o["sources"][0].update(max_bytes=10**12)}
res = {}
for name, fn in bads.items():
    topic_with(fn)
    res[name] = raises(c.ConfigError, c.load_topic, "vulns")
check("malformed topic configs are refused", all(res.values()), [k for k, v in res.items() if not v])
topic_with(lambda o: o["sources"][0].update(url="http://127.0.0.1:9/kev"))
check("loopback http is allowed in a topic (selftests)", c.load_topic("vulns")["sources"][0]["url"].startswith("http://127.0.0.1"))
del os.environ["STATEFEED_TOPICS_DIR"]

check("local settings missing -> defaults", c.load_local_settings("vulns") == {"project": None, "base_urls": [], "principal": "statefeed-vulns", "contact": ""})
check("local settings missing with require -> error", raises(c.ConfigError, c.load_local_settings, "vulns", True))
c.ensure_private_dir(c.statefeed_conf())
lp = os.path.join(c.statefeed_conf(), "vulns.json")
open(lp, "w").write(json.dumps({"project": "my-feed", "base_urls": ["https://my-feed.pages.dev"], "contact": "ops at example.test"}))
ls = c.load_local_settings("vulns", True)
check("local settings load", ls["project"] == "my-feed" and ls["base_urls"] == ["https://my-feed.pages.dev"] and ls["principal"] == "statefeed-vulns" and ls["contact"])
res = {}
for name, body in {"project caps": {"project": "My Feed", "base_urls": ["https://x.test"]}, "http url": {"project": "p", "base_urls": ["http://x.test"]},
                   "trailing slash": {"project": "p", "base_urls": ["https://x.test/"]}, "principal flag": {"project": "p", "base_urls": ["https://x.test"], "principal": "-Ox"},
                   "no base": {"project": "p"}, "not object": []}.items():
    open(lp, "w").write(json.dumps(body))
    res[name] = raises(c.ConfigError, c.load_local_settings, "vulns", True)
check("bad local settings are refused", all(res.values()), [k for k, v in res.items() if not v])

# ------------------------------------------------------------------ 10. http_get and cached_fetch against a local server
class H(http.server.BaseHTTPRequestHandler):
    hits = {}
    etag = '"v1"'
    body = b'{"vulnerabilities":[{"cveID":"CVE-2024-0001"}]}'
    fail = False

    def log_message(self, *a):
        pass

    def reply(self, code, body=b"", headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        H.hits[path] = H.hits.get(path, 0) + 1
        port = self.server.server_address[1]
        if path == "/data":
            if H.fail:
                return self.reply(503)
            if self.headers.get("If-None-Match") == H.etag:
                return self.reply(304)
            return self.reply(200, H.body, [("ETag", H.etag), ("Last-Modified", "Fri, 13 Nov 2026 00:00:00 GMT")])
        if path == "/big":
            return self.reply(200, b"x" * 5000)
        if path == "/gz":
            return self.reply(200, gzip.compress(b"hello " * 100), [("Content-Encoding", "gzip")])
        if path == "/bomb":
            return self.reply(200, gzip.compress(b"\0" * 1_000_000), [("Content-Encoding", "gzip")])
        if path == "/csvgz":                              # a .gz file served as a plain download
            return self.reply(200, gzip.compress(b"cve,epss\n"), [("Content-Type", "application/gzip")])
        if path == "/same":
            return self.reply(302, headers=[("Location", "/data")])
        if path == "/other":
            return self.reply(302, headers=[("Location", f"http://localhost:{port}/data")])
        if path == "/loop":
            return self.reply(302, headers=[("Location", "/loop")])
        if path == "/https":
            return self.reply(302, headers=[("Location", "ftp://127.0.0.1/x")])
        if path == "/creds":
            return self.reply(302, headers=[("Location", f"http://u:p@127.0.0.1:{port}/data")])
        if path == "/echo":
            return self.reply(200, self.headers.get("User-Agent", "").encode())
        if path == "/slow":
            time.sleep(3)
            return self.reply(200, b"late")
        self.reply(404)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"

r = c.http_get(BASE + "/data", 10000)
check("http_get returns status, body and lower-case headers", r.status == 200 and r.body == H.body and r.headers["etag"] == '"v1"')
check("http_get sends the honest User-Agent", c.http_get(BASE + "/echo", 1000).body.decode() == c.USER_AGENT)
check("http_get enforces the size cap", raises(c.HttpError, c.http_get, BASE + "/big", 1000) and len(c.http_get(BASE + "/big", 5000).body) == 5000)
check("http_get decodes gzip under the cap", c.http_get(BASE + "/gz", 10000).body == b"hello " * 100)
check("http_get refuses a gzip bomb", raises(c.HttpError, c.http_get, BASE + "/bomb", 10000))
check("a .gz download is returned as is", gzip.decompress(c.http_get(BASE + "/csvgz", 1000).body) == b"cve,epss\n")
check("http_get follows a same-host redirect", c.http_get(BASE + "/same", 10000).body == H.body)
check("http_get refuses a redirect to another host by default", raises(c.HttpError, c.http_get, BASE + "/other", 10000))
check("http_get follows it when that domain is allowed", c.http_get(BASE + "/other", 10000, allowed_redirect_domains=["localhost"]).body == H.body)
check("allowed domains do not match by suffix trick", not c._domain_ok("evil127.0.0.1", ["127.0.0.1"]) and c._domain_ok("a.b.example.test", ["example.test"])
      and not c._domain_ok("example.test.evil.test", ["example.test"]) and c._domain_ok("EXAMPLE.test.", ["example.test"]))
check("a host that tries to pass a domain-suffix check with a backslash, or a non-ASCII or spaced URL, is refused",
      all(raises(c.HttpError, c._check_url, u) for u in ("https://evil.test\\.good.test/x", "https://good.test\\@evil.test/",
                                                         "https://g\u00f6\u00f6d.test/", "https://good.test/a b", "https://-bad.test/",
                                                         "https://good.test\n.evil.test/"))
      and c._check_url("https://epss.example.test/f.csv.gz") == "epss.example.test")
check("http_get refuses redirect loops, other schemes and credentials",
      all(raises(c.HttpError, c.http_get, BASE + p, 10000, allowed_redirect_domains=["127.0.0.1"]) for p in ("/loop", "/https", "/creds")))
check("http_get refuses plain http to a non-loopback host and credentials in the URL",
      raises(c.HttpError, c.http_get, "http://example.test/x", 100) and raises(c.HttpError, c.http_get, "https://u:p@example.test/x", 100)
      and raises(c.HttpError, c.http_get, "file:///etc/passwd", 100) and raises(c.HttpError, c.http_get, "ftp://127.0.0.1/x", 100))
try:
    c.http_get(BASE + "/missing", 100)
    e404 = None
except c.HttpError as e:
    e404 = e
check("http_get reports the HTTP status", e404 is not None and e404.status == 404)
check("http_get reports a closed port as HttpError without a status",
      raises(c.HttpError, c.http_get, "http://127.0.0.1:1/x", 100, timeout=2))
r304 = c.http_get(BASE + "/data", 10000, headers={"If-None-Match": '"v1"'})
check("http_get returns 304 with an empty body", r304.status == 304 and r304.body == b"")
t0 = time.monotonic()
check("http_get honours the timeout", raises(c.HttpError, c.http_get, BASE + "/slow", 100, timeout=1) and time.monotonic() - t0 < 2.8)

cd = os.path.join(TMP, "cache")


def parse_ok(b):
    if b"vulnerabilities" not in b:
        raise ValueError("not a catalog")


H.hits.clear()
f1 = c.cached_fetch("kev-cisa", BASE + "/data", 10000, cd, validate=parse_ok)
check("cached_fetch first download: ok/updated, cache written 0600",
      (f1.status, f1.how) == ("ok", "updated") and f1.body == H.body and f1.sha256 == c.sha256_bytes(H.body) and f1.size == len(H.body)
      and stat.S_IMODE(os.stat(os.path.join(cd, "kev-cisa.body")).st_mode) == 0o600 and stat.S_IMODE(os.stat(cd).st_mode) == 0o700)
f2 = c.cached_fetch("kev-cisa", BASE + "/data", 10000, cd, validate=parse_ok)
check("cached_fetch revalidates with a conditional GET: ok/not-modified, same bytes", (f2.status, f2.how) == ("ok", "not-modified") and f2.body == H.body
      and f2.sha256 == f1.sha256)
H.fail = True
f3 = c.cached_fetch("kev-cisa", BASE + "/data", 10000, cd, validate=parse_ok)
check("a failed download falls back to a young cache: status cache", (f3.status, f3.how) == ("cache", "cache") and f3.body == H.body and "503" in f3.error
      and BASE not in f3.error)
os.environ["STATEFEED_FAKE_NOW"] = str(time.time() + 3 * 86400)
f4 = c.cached_fetch("kev-cisa", BASE + "/data", 10000, cd, validate=parse_ok)
check("a cache older than 2 days does not stand in: unavailable", (f4.status, f4.how) == ("unavailable", "unavailable") and f4.body is None and f4.sha256 is None)
del os.environ["STATEFEED_FAKE_NOW"]
check("no cache at all and a failed download is unavailable", c.cached_fetch("epss", BASE + "/data", 10000, cd).status == "unavailable")
H.fail = False
H.body, H.etag = b"<html>error page</html>", '"v2"'
f5 = c.cached_fetch("kev-cisa", BASE + "/data", 10000, cd, validate=parse_ok)
check("content rejected by validate counts as a failed download and keeps the cache",
      f5.status == "cache" and b"CVE-2024-0001" in f5.body and "rejected" in f5.error
      and b"CVE-2024-0001" in open(os.path.join(cd, "kev-cisa.body"), "rb").read())
H.body = b'{"vulnerabilities":[{"cveID":"CVE-2024-0002"}]}'
f6 = c.cached_fetch("kev-cisa", BASE + "/data", 10000, cd, validate=parse_ok)
check("a good new download replaces the cache", (f6.status, f6.how) == ("ok", "updated") and b"0002" in f6.body)
open(os.path.join(cd, "kev-cisa.body"), "ab").write(b"tamper")
H.fail = True
check("a corrupted cache body is not used", c.cached_fetch("kev-cisa", BASE + "/data", 10000, cd).status == "unavailable")
H.fail = False
check("cached_fetch rejects a bad cache name", raises(c.ConfigError, c.cached_fetch, "../x", BASE + "/data", 10, cd))
check("cached_fetch applies the redirect policy", c.cached_fetch("redir", BASE + "/other", 10000, cd).status == "unavailable"
      and c.cached_fetch("redir2", BASE + "/other", 10000, cd, allowed_redirect_domains=["localhost"]).status == "ok")
srv.shutdown()

# ------------------------------------------------------------------ 11. SSH signatures
if not c.have_ssh_sign():
    print("SKIP ssh signature checks: this ssh-keygen has no -Y sign/verify")
else:
    kd = c.ensure_private_dir(os.path.join(TMP, "keys"))
    key = os.path.join(kd, "signing_key")
    pub = c.generate_signing_key(key, "statefeed-test")
    check("generated key is 0600 and refuses to be overwritten", stat.S_IMODE(os.stat(key).st_mode) == 0o600 and c.private_perms_problem(key) is None
          and raises(c.SignError, c.generate_signing_key, key))
    line = c.allowed_signers_line("statefeed-test", pub)
    check("allowed_signers line has principal, namespaces option and the key", re.fullmatch(r'statefeed-test namespaces="statefeed" ssh-ed25519 [A-Za-z0-9+/=]+', line) is not None, line)
    allowed = os.path.join(kd, "allowed_signers")
    open(allowed, "w").write(line + "\n")
    data = c.canonical_json({"seq": 1, "topic": "vulns"})
    df = os.path.join(kd, "manifest.json")
    open(df, "wb").write(data)
    sig = c.ssh_sign(key, df, "statefeed")
    sigb = open(sig, "rb").read()
    check("ssh_sign writes <file>.sig", sig == df + ".sig" and sigb.startswith(b"-----BEGIN SSH SIGNATURE-----"))
    check("ssh_verify accepts the right data, principal and namespace", c.ssh_verify(allowed, "statefeed-test", "statefeed", data, sigb) is True)
    check("ssh_verify rejects tampered data", c.ssh_verify(allowed, "statefeed-test", "statefeed", data + b" ", sigb) is False)
    check("ssh_verify rejects a wrong principal", c.ssh_verify(allowed, "someone-else", "statefeed", data, sigb) is False)
    check("ssh_verify rejects a wrong namespace", c.ssh_verify(allowed, "statefeed-test", "other", data, sigb) is False)
    check("ssh_verify rejects a damaged or empty signature", c.ssh_verify(allowed, "statefeed-test", "statefeed", data, sigb[:-40]) is False
          and c.ssh_verify(allowed, "statefeed-test", "statefeed", data, b"") is False)
    key2 = os.path.join(kd, "other_key")
    pub2 = c.generate_signing_key(key2, "other")
    open(df + "2", "wb").write(data)
    sig2 = open(c.ssh_sign(key2, df + "2", "statefeed"), "rb").read()
    check("a signature from a key that is not in allowed_signers is rejected", c.ssh_verify(allowed, "statefeed-test", "statefeed", data, sig2) is False)
    open(allowed, "w").write(line + "\n" + c.allowed_signers_line("statefeed-test", pub2) + "\n")
    check("two allowed_signers lines (rotation): both keys verify", c.ssh_verify(allowed, "statefeed-test", "statefeed", data, sig2) is True
          and c.ssh_verify(allowed, "statefeed-test", "statefeed", data, sigb) is True)
    open(allowed, "w").write(c.allowed_signers_line("statefeed-test", pub, valid_before="20200101") + "\n")
    check("valid-before in allowed_signers is honoured (an expired key no longer verifies)",
          c.ssh_verify(allowed, "statefeed-test", "statefeed", data, sigb) is False)
    open(allowed, "w").write(line + "\n")
    check("ssh_sign replaces an old signature", c.ssh_sign(key, df, "statefeed") == sig)
    check("ssh_sign errors are SignError (missing key, missing data, bad namespace, wrong exit)",
          raises(c.SignError, c.ssh_sign, os.path.join(kd, "nope"), df) and raises(c.SignError, c.ssh_sign, key, df + "nope")
          and raises(c.SignError, c.ssh_sign, key, df, "Bad Ns") and raises(c.SignError, c.ssh_sign, df, df))
    check("ssh_verify refuses bad arguments with SignError instead of False",
          raises(c.SignError, c.ssh_verify, allowed, "-Ox", "statefeed", data, sigb) and raises(c.SignError, c.ssh_verify, allowed + "x", "statefeed-test", "statefeed", data, sigb)
          and raises(c.SignError, c.ssh_verify, allowed, "statefeed-test", "statefeed", "text", sigb))
    check("allowed_signers_line refuses junk", all(raises(c.SignError, c.allowed_signers_line, *a) for a in
          (("bad principal", pub), ("p", "nokey"), ("p", pub, "BAD NS"), ("p", pub, "statefeed", "tomorrow"))))

# ------------------------------------------------------------------ 12. notify
SENT = []
c.set_notifier(lambda text: SENT.append(text) or True)
check("notify goes to the installed sink, cleaned and capped", c.notify("a\x00b\u202e\nc" + "z" * 5000) is True and len(SENT[0]) == c.NOTIFY_CAP
      and "\x00" not in SENT[0] and "\u202e" not in SENT[0] and "\n" in SENT[0])
c.set_notifier(None)
import contextlib, io
os.environ["OPS_ENV"] = os.path.join(TMP, "no-such.env")
for k in ("OPS_BOT_TOKEN", "OPS_CHAT_ID"):
    os.environ.pop(k, None)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    sent = c.notify("hello operator")
check("with no bot configured notify prints and reports False", sent is False and "hello operator" in buf.getvalue())
mod = c._load_notify_module()
check("the real ops notify module is found and exposes send()", callable(getattr(mod, "send", None)) and callable(getattr(mod, "_conf", None)))
fake = []
mod_send, mod_conf = mod.send, mod._conf
mod._conf = lambda: {"OPS_BOT_TOKEN": "t", "OPS_CHAT_ID": "1"}
mod.send = lambda text: fake.append(text) or True
check("with a bot configured notify uses ops/lib/notify.py send()", c.notify("ready") is True and fake == ["ready"])
mod.send, mod._conf = mod_send, mod_conf

# ------------------------------------------------------------------ 13. the files that ship
check("the package, schemas and topic are present and the module docstring states the API",
      os.path.isfile(os.path.join(c.HERE, "__init__.py")) and "API" in c.__doc__ and "ssh_verify" in c.__doc__ and "http_get" in c.__doc__)

print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("all statefeed common checks passed")
