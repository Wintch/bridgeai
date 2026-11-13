#!/usr/bin/env python3
"""Offline test of statefeed/common.py: canonical JSON and hashes, label rules, kev.csv rows and file, kev_sha, manifest v2 validation (delta,
format, epss, mirrors, size cap) and that the published JSON Schema and column spec agree with the code, topic and local config, private files, http_get redirect and size policy,
the conditional-GET cache, SSH signatures with a throwaway key, and the notify sink. No network: local http.server on 127.0.0.1.
Stdlib only: python3 -I ops/statefeed_common_selftest.py"""
import copy, gzip, hashlib, http.server, json, os, re, stat, sys, tempfile, threading, time

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

# ------------------------------------------------------------------ 3. kev.csv rows
SHA = "a" * 64
ROW = {"cve": "CVE-2024-12345", "date_added": "2024-01-02", "kev_sha": "0123456789abcdef", "epss": "0.97565", "epss_pct": "0.99912", "flag": ""}
check("a valid row passes", c.validate_row(ROW) == [], c.validate_row(ROW))
check("the column list and header are the spec's", c.KEV_COLUMNS == ("cve", "date_added", "kev_sha", "epss", "epss_pct", "flag")
      and c.KEV_HEADER == "cve,date_added,kev_sha,epss,epss_pct,flag")


def row_with(**kw):
    o = dict(ROW)
    o.update(kw)
    return o


ROW_BAD = {
    "cve lower case": row_with(cve="cve-2024-12345"), "cve short number": row_with(cve="CVE-2024-123"), "cve long number": row_with(cve="CVE-2024-12345678"),
    "cve unicode digits": row_with(cve="CVE-2024-١٢٣٤٥"), "cve trailing newline": row_with(cve="CVE-2024-12345\n"), "cve comma": row_with(cve="CVE-2024-1234,"),
    "cve not a string": row_with(cve=5), "date format": row_with(date_added="2024-1-2"), "date not on calendar": row_with(date_added="2024-02-31"),
    "date empty": row_with(date_added=""), "date with time": row_with(date_added="2024-01-02T00:00:00Z"),
    "sha short": row_with(kev_sha="0123456789abcde"), "sha long": row_with(kev_sha="0123456789abcdef0"), "sha upper": row_with(kev_sha="0123456789ABCDEF"),
    "sha not hex": row_with(kev_sha="0123456789abcdeg"), "sha empty": row_with(kev_sha=""),
    "epss above 1": row_with(epss="1.5"), "epss 1.1": row_with(epss="1.1"), "epss exponent": row_with(epss="1e-05"), "epss negative": row_with(epss="-0.1"),
    "epss nan": row_with(epss="nan"), "epss 7 decimals": row_with(epss="0.1234567"), "epss trailing dot": row_with(epss="0."), "epss leading dot": row_with(epss=".5"),
    "epss space": row_with(epss=" 0.5"), "epss comma": row_with(epss="0,5"), "epss pct bad": row_with(epss_pct="2"),
    "epss without pct": row_with(epss_pct=""), "pct without epss": row_with(epss=""), "flag other": row_with(flag="maybe"), "flag upper": row_with(flag="Disputed"),
    "missing column": {k: v for k, v in ROW.items() if k != "flag"}, "extra column": dict(ROW, notes="x"), "not an object": [1, 2],
}
bad_ok = {k: bool(c.validate_row(v)) for k, v in ROW_BAD.items()}
check("validate_row rejects every bad variant", all(bad_ok.values()), [k for k, v in bad_ok.items() if not v])
good_rows = [ROW, row_with(epss="", epss_pct=""), row_with(epss="0", epss_pct="0"), row_with(epss="1", epss_pct="1.0"), row_with(epss="0.000001", epss_pct="1.000000"),
             row_with(flag="disputed"), row_with(flag="single_channel"), row_with(cve="CVE-1999-0001"), row_with(cve="CVE-2024-1234567")]
check("valid variants pass (empty EPSS pair, 0, 1, 6 decimals, both flags)", all(c.validate_row(r) == [] for r in good_rows), [r for r in good_rows if c.validate_row(r)])
check("row_problems names the column", ("cve", "not a CVE id") in c.row_problems(row_with(cve="x")) and c.row_problems(ROW) == [])
check("no column pattern lets a comma, quote, newline or space through", all(c.column_problem(col, v) for col in c.KEV_COLUMNS[:5]
      for v in ("a,b", 'a"b', "a\nb", " ", "‮")) and c.column_problem("flag", "a,b"))
check("an unknown column is refused", c.column_problem("notes", "x") == "unknown column")

# ------------------------------------------------------------------ 3b. kev_sha
E1 = {"cveID": "CVE-2024-12345", "vendorProject": "Example Vendor", "product": "Example Product", "dateAdded": "2024-01-02", "cwes": ["CWE-79"], "notes": "ünï"}
E1_REORDERED = {"notes": "ünï", "cwes": ["CWE-79"], "dateAdded": "2024-01-02", "product": "Example Product", "vendorProject": "Example Vendor", "cveID": "CVE-2024-12345"}
want = hashlib.sha256(json.dumps(E1, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
check("kev_sha is the first 16 hex of sha256 over the sorted compact UTF-8 JSON, as the spec writes it", c.kev_sha(E1) == want
      and re.fullmatch("[0-9a-f]{16}", c.kev_sha(E1)) and c.kev_sha(E1_REORDERED) == c.kev_sha(E1))
check("kev_sha is fixed for a known entry (a regression guard for the rule id)", c.kev_sha({"a": 1}) == hashlib.sha256(b'{"a":1}').hexdigest()[:16]
      and c.kev_sha({"b": "é", "a": [1, None]}) == hashlib.sha256('{"a":[1,null],"b":"é"}'.encode()).hexdigest()[:16])
check("kev_sha sees every field (a prose change changes it) and non-ASCII is not escaped",
      c.kev_sha(dict(E1, notes="other")) != c.kev_sha(E1) and c.kev_sha(dict(E1, extra=1)) != c.kev_sha(E1)
      and c.kev_sha({"x": "é"}) == hashlib.sha256('{"x":"é"}'.encode()).hexdigest()[:16])
check("kev_sha refuses what is not an entry or has no UTF-8 form", raises(ValueError, c.kev_sha, [1]) and raises(ValueError, c.kev_sha, "x")
      and raises(ValueError, c.kev_sha, {"a": "\ud800"}))
check("kev_sha refuses what a third party could not reproduce: floats (also whole ones), NaN, huge integers, non-ASCII keys",
      all(raises(ValueError, c.kev_sha, e) for e in ({"a": 1.5}, {"a": 1.0}, {"a": float("nan")}, {"a": float("inf")}, {"a": [{"b": 2.5}]},
                                                     {"a": 2**53}, {"a": -2**53}, {"\u00e9": 1}, {"a": {"\u00e9": 1}}))
      and c.kev_sha({"a": 2**53 - 1}) == hashlib.sha256(b'{"a":9007199254740991}').hexdigest()[:16]
      and c.kev_sha({"a": True, "b": None, "c": "\u2028\x7f\x01"}) == hashlib.sha256('{"a":true,"b":null,"c":"\u2028\x7f\\u0001"}'.encode()).hexdigest()[:16])
check("a CVE number has one spelling: leading zeros beyond the 4-digit form are refused",
      c.column_problem("cve", "CVE-2024-00001") and c.column_problem("cve", "CVE-2024-01234567") and c.column_problem("cve", "CVE-2024-\u0661\u0662\u0663\u0664")
      and not c.column_problem("cve", "CVE-2024-0001") and not c.column_problem("cve", "CVE-2024-10000") and not c.column_problem("cve", "CVE-2024-1234567"))
check("the manifest names the rule", c.KEV_SHA_RULE_ID == "kev-entry-sha256-16/v1" and "16 hex" in c.KEV_SHA_RULE_TEXT)

# ------------------------------------------------------------------ 3c. kev.csv file
check("cve_sort_key sorts by year, then number as a number", sorted(["CVE-2024-12345", "CVE-2024-1234", "CVE-2023-99999", "CVE-2024-0999", "CVE-2024-99999"],
      key=c.cve_sort_key) == ["CVE-2023-99999", "CVE-2024-0999", "CVE-2024-1234", "CVE-2024-12345", "CVE-2024-99999"]
      and raises(ValueError, c.cve_sort_key, "nope"))
rows3 = [row_with(cve="CVE-2024-12345"), row_with(cve="CVE-2023-99999", flag="disputed"), row_with(cve="CVE-2024-1234", epss="", epss_pct="")]
csv = c.rows_to_csv(rows3)
text = csv.decode()
check("rows_to_csv: header, sorted rows, newline ends, no quoting", text == (
    "cve,date_added,kev_sha,epss,epss_pct,flag\n"
    "CVE-2023-99999,2024-01-02,0123456789abcdef,0.97565,0.99912,disputed\n"
    "CVE-2024-1234,2024-01-02,0123456789abcdef,,,\n"
    "CVE-2024-12345,2024-01-02,0123456789abcdef,0.97565,0.99912,\n"), text)
got, errs = c.parse_kev_csv(csv)
check("kev.csv round trip", errs == [] and [r["cve"] for r in got] == ["CVE-2023-99999", "CVE-2024-1234", "CVE-2024-12345"] and got[1]["epss"] == "" and got[0]["flag"] == "disputed")
check("an empty catalog is a header only, and valid", c.rows_to_csv([]) == b"cve,date_added,kev_sha,epss,epss_pct,flag\n" and c.parse_kev_csv(c.rows_to_csv([])) == ([], []))
check("rows_to_csv refuses an invalid row and a duplicate", raises(ValueError, c.rows_to_csv, [row_with(kev_sha="x")]) and raises(ValueError, c.rows_to_csv, [ROW, ROW]))
hdr = c.KEV_HEADER + "\n"
line = "CVE-2024-0001,2024-01-02,0123456789abcdef,,,\n"
CSV_BAD = {
    "no final newline": (hdr + line).rstrip("\n").encode(), "crlf": (hdr + line).replace("\n", "\r\n").encode(),
    "wrong header": ("cve,date_added,kev_sha,epss,epss_pct\n" + line).encode(), "header with spaces": ("cve, date_added,kev_sha,epss,epss_pct,flag\n" + line).encode(),
    "no header": line.encode(), "empty file": b"", "BOM": b"\xef\xbb\xbf" + (hdr + line).encode(), "not UTF-8": hdr.encode() + b"CVE-2024-0001,\xff\n",
    "too few columns": (hdr + "CVE-2024-0001,2024-01-02,0123456789abcdef,,\n").encode(), "too many columns": (hdr + line.rstrip("\n") + ",\n").encode(),
    "quoted field": (hdr + 'CVE-2024-0001,"2024-01-02",0123456789abcdef,,,\n').encode(), "bad cve": (hdr + line.replace("CVE-2024-0001", "CVE-24-1")).encode(),
    "bad date": (hdr + line.replace("2024-01-02", "2024-02-30")).encode(), "unsorted": (hdr + line.replace("0001", "0002") + line).encode(),
    "year unsorted": (hdr + "CVE-2024-0001,2024-01-02,0123456789abcdef,,,\nCVE-2023-0001,2024-01-02,0123456789abcdef,,,\n").encode(),
    "duplicate": (hdr + line + line).encode(), "blank line": (hdr + line + "\n").encode(), "epss without pct": (hdr + line.replace(",,,", ",0.5,,")).encode(),
    "bad flag": (hdr + line.replace(",,,\n", ",,,x\n")).encode(), "text number sort": (hdr + "CVE-2024-1000,2024-01-02,0123456789abcdef,,,\nCVE-2024-999999,2024-01-02,0123456789abcdef,,,\nCVE-2024-20000,2024-01-02,0123456789abcdef,,,\n").encode(),
}
res = {k: c.parse_kev_csv(v)[1] != [] and c.parse_kev_csv(v)[0] == [] for k, v in CSV_BAD.items()}
check("parse_kev_csv refuses every bad file and returns no rows", all(res.values()), [k for k, v in res.items() if not v])
check("numeric order is the order: 1000 < 20000 < 999999 is accepted", c.parse_kev_csv(
    (hdr + "CVE-2024-1000,2024-01-02,0123456789abcdef,,,\nCVE-2024-20000,2024-01-02,0123456789abcdef,,,\nCVE-2024-999999,2024-01-02,0123456789abcdef,,,\n").encode())[1] == [])
many = (hdr + "".join(f"CVE-2024-{n:04d},bad,x,,,\n" for n in range(1, 200))).encode()
check("parse_kev_csv caps the number of errors it reports", len(c.parse_kev_csv(many)[1]) <= 52 and c.parse_kev_csv(bytes([0xff]))[1] and c.parse_kev_csv("x")[1])

# ------------------------------------------------------------------ 4. manifest validation
FORMAT = {"data": "kev.csv", "columns": ["cve", "date_added", "kev_sha", "epss", "epss_pct", "flag"], "kev_sha": "kev-entry-sha256-16/v1", "rule": c.KEV_SHA_RULE_TEXT}
MAN = {"topic": "vulns", "schema_version": 2, "seq": 3, "prev_digest": SHA, "generated_at": "2026-11-13T09:30:00Z", "valid_until": "2026-11-16T09:30:00Z",
       "item_count": 2, "untrusted_text": False, "ai_generated": False, "compiled_by": "statefeed/1 (code, no AI)",
       "licence": {"compilation": "CC-BY-4.0", "records": "see sources[].licence"}, "check_set_version": "0123456789ab",
       "sources": [{"id": "kev-cisa", "url": "https://example.test/kev.json", "retrieved_at": "2026-11-13T09:29:00Z", "content_sha256": SHA, "bytes": 100, "status": "ok",
                    "ref": {"catalog_version": "2026.11.13", "date_released": "2026-11-13T00:00:00.000Z"}},
                   {"id": "epss", "url": "https://example.test/epss.csv.gz", "retrieved_at": "2026-11-12T09:29:00Z", "content_sha256": SHA, "bytes": 50, "status": "cache",
                    "ref": {"model_version": "v2025.03.14", "score_date": "2026-11-12"}},
                   {"id": "kev-github", "url": "http://127.0.0.1:8080/kev.json", "retrieved_at": None, "content_sha256": None, "bytes": 0, "status": "unavailable", "ref": None}],
       "files": [{"path": "v1/snapshots/2026-11-13-3/kev.csv", "sha256": SHA, "bytes": 1234}], "snapshot": "2026-11-13-3",
       "publish_record": {"approval": "human"}, "format": FORMAT,
       "delta": {"since_seq": 2, "added": ["CVE-2026-0002"], "removed": [], "changed": ["CVE-2025-9999", "CVE-2026-0001"]},
       "epss": {"model_version": "v2025.03.14", "score_date": "2026-11-12"},
       "mirrors": [{"id": "pages", "kind": "https", "address": "https://example.test/feed", "machine_readable": True},
                   {"id": "relay", "kind": "telegram", "address": "@example_feed", "machine_readable": False}]}
check("a valid manifest passes", c.validate_manifest(MAN) == [], c.validate_manifest(MAN))
check("schema_version is 2 and the file name is kev.csv", c.SCHEMA_VERSION == 2 and c.KEV_DATA_FILE == "kev.csv")


def mm(fn):
    o = copy.deepcopy(MAN)
    fn(o)
    return o


FULL = {"since_seq": None, "full": True, "counts": {"added": 5, "removed": 0, "changed": 0}}
# (name, mutation, does the JSON Schema also reject it?)
MAN_BAD = [
    ("missing key", lambda o: o.pop("seq"), True),
    ("missing format", lambda o: o.pop("format"), True),
    ("missing delta", lambda o: o.pop("delta"), True),
    ("missing epss", lambda o: o.pop("epss"), True),
    ("extra key", lambda o: o.update(signature="x"), True),
    ("key_fingerprint is gone", lambda o: o.update(key_fingerprint="SHA256:abc"), True),
    ("topic bad", lambda o: o.update(topic="Vulns"), True),
    ("schema_version 1", lambda o: o.update(schema_version=1), True),
    ("schema_version 3", lambda o: o.update(schema_version=3), True),
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
    ("source without ref", lambda o: o["sources"][0].pop("ref"), True),
    ("source url http non-loopback", lambda o: o["sources"][0].update(url="http://example.test/x"), True),
    ("source url userinfo", lambda o: o["sources"][0].update(url="https://u:p@example.test/x"), False),
    ("source url space", lambda o: o["sources"][0].update(url="https://example.test/a b"), True),
    ("source status", lambda o: o["sources"][0].update(status="fine"), True),
    ("source hash null while ok", lambda o: o["sources"][0].update(content_sha256=None), False),
    ("unavailable with hash", lambda o: o["sources"][2].update(content_sha256=SHA), False),
    ("unavailable with a ref", lambda o: o["sources"][2].update(ref={"catalog_version": "1", "date_released": None}), False),
    ("source duplicate id", lambda o: o["sources"][1].update(id="kev-cisa"), False),
    ("ref extra key", lambda o: o["sources"][0]["ref"].update(note="x"), True),
    ("ref mixed keys", lambda o: o["sources"][0].update(ref={"catalog_version": "1", "score_date": "2026-11-12"}), True),
    ("ref value with a url", lambda o: o["sources"][0]["ref"].update(catalog_version="http://evil.test"), True),
    ("ref value with a space", lambda o: o["sources"][0]["ref"].update(catalog_version="a b"), True),
    ("ref value too long", lambda o: o["sources"][0]["ref"].update(catalog_version="v" * 41), True),
    ("ref value empty", lambda o: o["sources"][0]["ref"].update(catalog_version=""), True),
    ("ref not an object", lambda o: o["sources"][0].update(ref="2026.11.13"), True),
    ("ref score_date not a date", lambda o: o["sources"][1]["ref"].update(score_date="2026-02-30"), False),
    ("files empty", lambda o: o.update(files=[]), True),
    ("file path escapes", lambda o: o["files"][0].update(path="v1/snapshots/2026-11-13-3/../../x"), True),
    ("file path other snapshot", lambda o: o["files"][0].update(path="v1/snapshots/2026-11-12-3/kev.csv"), False),
    ("file path not v1", lambda o: o["files"][0].update(path="kev.csv"), True),
    ("the old data file name", lambda o: o["files"][0].update(path="v1/snapshots/2026-11-13-3/items.ndjson"), True),
    ("a second file besides kev.csv", lambda o: o["files"].append({"path": "v1/snapshots/2026-11-13-3/other.json", "sha256": SHA, "bytes": 1}), True),
    ("file duplicate", lambda o: o["files"].append(copy.deepcopy(o["files"][0])), True),
    ("file hash bad", lambda o: o["files"][0].update(sha256="x"), True),
    ("snapshot wrong seq", lambda o: o.update(snapshot="2026-11-13-4"), False),
    ("snapshot format", lambda o: o.update(snapshot="today-3"), True),
    ("publish_record auto", lambda o: o["publish_record"].update(approval="auto"), True),
    ("publish_record extra", lambda o: o["publish_record"].update(by="x"), True),
    ("format rule changed", lambda o: o["format"].update(rule="trust me"), True),
    ("format columns reordered", lambda o: o["format"].update(columns=["date_added", "cve", "kev_sha", "epss", "epss_pct", "flag"]), True),
    ("format rule id changed", lambda o: o["format"].update(kev_sha="kev-entry-sha256-16/v2"), True),
    ("format data changed", lambda o: o["format"].update(data="items.ndjson"), True),
    ("format extra key", lambda o: o["format"].update(x=1), True),
    ("delta not an object", lambda o: o.update(delta=[]), True),
    ("delta since_seq not below seq", lambda o: o["delta"].update(since_seq=3), False),
    ("delta since_seq 0", lambda o: o["delta"].update(since_seq=0), True),
    ("delta since_seq null without full", lambda o: o["delta"].update(since_seq=None), True),
    ("delta since_seq with the first seq", lambda o: o.update(seq=1, snapshot="2026-11-13-1", files=[{"path": "v1/snapshots/2026-11-13-1/kev.csv", "sha256": SHA, "bytes": 1}]), False),
    ("delta list missing", lambda o: o["delta"].pop("changed"), True),
    ("delta list with a non-CVE", lambda o: o["delta"].update(added=["CVE-2026-0002", "nope"]), True),
    ("delta list unsorted", lambda o: o["delta"].update(changed=["CVE-2026-0001", "CVE-2025-9999"]), False),
    ("delta list text-sorted but not numerically", lambda o: o["delta"].update(changed=["CVE-2026-20000", "CVE-2026-9999"]), False),
    ("delta list with a duplicate", lambda o: o["delta"].update(changed=["CVE-2026-0001", "CVE-2026-0001"]), False),
    ("delta lists overlap", lambda o: o["delta"].update(added=["CVE-2026-0001"]), False),
    ("delta list over 50", lambda o: o["delta"].update(added=[f"CVE-2026-{n:04d}" for n in range(1, 52)]), True),
    ("delta extra key", lambda o: o["delta"].update(note="x"), True),
    ("delta full with lists", lambda o: o.update(delta=dict(FULL, since_seq=2, added=[])), True),
    ("delta full false", lambda o: o.update(delta=dict(FULL, full=False)), True),
    ("delta full without counts", lambda o: o.update(delta={"since_seq": 2, "full": True}), True),
    ("delta full counts negative", lambda o: o.update(delta=dict(FULL, since_seq=2, counts={"added": -1, "removed": 0, "changed": 0})), True),
    ("delta full counts extra", lambda o: o.update(delta=dict(FULL, since_seq=2, counts={"added": 1, "removed": 0, "changed": 0, "x": 1})), True),
    ("epss extra key", lambda o: o["epss"].update(x=1), True),
    ("epss bad date", lambda o: o["epss"].update(score_date="2026-13-01"), False),
    ("epss model with a space", lambda o: o["epss"].update(model_version="v 1"), True),
    ("epss missing model", lambda o: o["epss"].pop("model_version"), True),
    ("epss a string", lambda o: o.update(epss="v2025"), True),
    ("mirrors empty", lambda o: o.update(mirrors=[]), True),
    ("mirrors over 8", lambda o: o.update(mirrors=[{"id": f"m{n}", "kind": "https", "address": f"https://m{n}.example.test", "machine_readable": True} for n in range(9)]), True),
    ("mirror id duplicate", lambda o: o["mirrors"][1].update(id="pages"), False),
    ("mirror id upper case", lambda o: o["mirrors"][0].update(id="Pages"), True),
    ("mirror id too long", lambda o: o["mirrors"][0].update(id="a" * 25), True),
    ("mirror kind other", lambda o: o["mirrors"][0].update(kind="ftp"), True),
    ("mirror https address is http", lambda o: o["mirrors"][0].update(address="http://example.test/feed"), True),
    ("mirror https address on loopback http", lambda o: o["mirrors"][0].update(address="http://127.0.0.1:8080/feed"), True),
    ("mirror address with credentials", lambda o: o["mirrors"][0].update(address="https://u:p@example.test/feed"), False),
    ("mirror telegram address is a url", lambda o: o["mirrors"][1].update(address="https://t.me/example_feed"), True),
    ("mirror telegram handle too short", lambda o: o["mirrors"][1].update(address="@abcd"), True),
    ("mirror telegram handle without @", lambda o: o["mirrors"][1].update(address="example_feed"), True),
    ("mirror telegram handle starts with a digit", lambda o: o["mirrors"][1].update(address="@1example_feed"), True),
    ("mirror https address is a handle", lambda o: o["mirrors"][0].update(address="@example_feed"), True),
    ("mirror machine_readable string", lambda o: o["mirrors"][0].update(machine_readable="yes"), True),
    ("mirror extra key", lambda o: o["mirrors"][0].update(note="x"), True),
    ("not an object", None, True),
]
ok = True
for name, fn, _ in MAN_BAD:
    o = "x" if fn is None else mm(fn)
    if not c.validate_manifest(o):
        ok = False
        print("   manifest accepted:", name)
check("validate_manifest rejects every bad variant", ok)
check("the first snapshot with the full form and since_seq null is valid", c.validate_manifest(mm(lambda o: o.update(
    seq=1, snapshot="2026-11-13-1", prev_digest=None, delta=copy.deepcopy(FULL), files=[{"path": "v1/snapshots/2026-11-13-1/kev.csv", "sha256": SHA, "bytes": 1}]))) == [])
check("a delta list of exactly 50 ids is valid (51 is not, see above)", c.validate_manifest(mm(lambda o: o["delta"].update(
    added=[f"CVE-2027-{n:04d}" for n in range(1, 51)]))) == [])
check("full form with a known since_seq is valid", c.validate_manifest(mm(lambda o: o.update(delta=dict(FULL, since_seq=2)))) == [])
check("a manifest without mirrors is valid (the key is optional)", c.validate_manifest(mm(lambda o: o.pop("mirrors"))) == [])
check("epss null is valid (no scores at all) and ref null is valid for a source that has none", c.validate_manifest(mm(lambda o: (o.update(epss=None), o["sources"][0].update(ref=None)))) == [])
check("a KEV ref may have a null date_released", c.validate_manifest(mm(lambda o: o["sources"][0]["ref"].update(date_released=None))) == [])
def mirror_of_size(n):
    e = dict(MAN["mirrors"][0])
    e["address"] += "a" * (n - len(c.canonical_json(e, newline=False)))
    assert len(c.canonical_json(e, newline=False)) == n
    return e


check("a mirror entry of 159 bytes is valid, one of 160 is not", c.mirror_problems(mirror_of_size(159)) == [] and c.mirror_problems(mirror_of_size(160)))
BAD_MIRROR_ADDRS = ("http://feed.example.test", "https://user@feed.example.test", "https://user:pw@feed.example.test", "https://@feed.example.test",
                    "https://feed.example.test@evil.test", "https://feed.example.test\\@evil.test", "https://feed.example.test?x=1", "https://feed.example.test/#f",
                    "https://127.0.0.1/feed", "https://localhost/feed", "https://feed/feed", "https://feed.example.test:99999", "https://feed.example.test/%41",
                    "https://[::1]/feed", "ftp://feed.example.test", "//feed.example.test", "feed.example.test", "https://feed.example.test/a b",
                    "https://feed.example.test./")
check("a mirror address with userinfo, a non-https scheme, an IP or bare host, a query, a fragment or escapes is refused for https and git_http",
      all(c.mirror_problems(dict(MAN["mirrors"][0], address=a)) and c.mirror_problems(dict(MAN["mirrors"][0], kind="git_http", address=a))
          for a in BAD_MIRROR_ADDRS)
      and not c.mirror_problems(dict(MAN["mirrors"][0], address="https://feed.example.test:8443/feed/x.git", kind="git_http")))
check("mirror_problems and mirrors_problems are usable on their own", c.mirror_problems(MAN["mirrors"][0]) == [] and c.mirror_problems({"id": "x"})
      and c.mirrors_problems(MAN["mirrors"]) == [] and c.mirrors_problems([]) and c.mirrors_problems("x"))

# ---- the size cap: manifest.json + .sig under 3,500 bytes
check("feed_size_problem: exactly 3,500 passes, 3,501 fails, ints and bytes both work", c.feed_size_problem(3000, 500) is None and c.feed_size_problem(3000, 501)
      and c.feed_size_problem(b"x" * 3100, b"y" * 400) is None and c.MANIFEST_CAP_BYTES == 3500)
huge = mm(lambda o: (o.update(mirrors=[dict(mirror_of_size(159), id=f"m{n}") for n in range(8)]),
                     o["delta"].update(added=[f"CVE-2027-{n:04d}" for n in range(1, 21)])))
errs = c.validate_manifest(huge)
check("an oversized manifest fails validation with a size error only", errs and all(e.startswith("size:") for e in errs), errs)
check("the sample manifest with 2 mirrors is well under the cap", len(c.canonical_json(MAN)) + c.SIG_RESERVE_BYTES < c.MANIFEST_CAP_BYTES, len(c.canonical_json(MAN)))

# ------------------------------------------------------------------ 5. the JSON Schema and the column spec agree with the code

def _rx(pat):
    return re.compile(pat.replace("\\p{L}\\p{N}", "\\w"))     # ECMA \p{L}\p{N}_ equals Python \w


def schema_errors(schema, inst, root=None, path="$"):
    """A tiny JSON Schema subset checker: just the keywords the manifest schema uses."""
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


check("the v1 schema files are gone and the v2 ones are present", sorted(os.listdir(c.SCHEMA_DIR)) == ["kev.csv.md", "manifest.2.json"])
MAN_SCHEMA = json.load(open(os.path.join(c.SCHEMA_DIR, "manifest.2.json")))
check("schema accepts the valid manifest and the variants that are valid", not schema_errors(MAN_SCHEMA, MAN), schema_errors(MAN_SCHEMA, MAN)[:3])
variants = [mm(lambda o: o.pop("mirrors")), mm(lambda o: o.update(epss=None)), mm(lambda o: o.update(delta=dict(FULL, since_seq=2))),
            mm(lambda o: o.update(seq=1, snapshot="2026-11-13-1", prev_digest=None, delta=copy.deepcopy(FULL), files=[{"path": "v1/snapshots/2026-11-13-1/kev.csv", "sha256": SHA, "bytes": 1}]))]
check("schema accepts the first-snapshot, full-delta, no-mirrors and no-epss manifests", all(not schema_errors(MAN_SCHEMA, v) for v in variants),
      [schema_errors(MAN_SCHEMA, v)[:2] for v in variants])
disagree = []
for name, fn, schema_rejects in MAN_BAD:
    o = "x" if fn is None else mm(fn)
    if schema_rejects and not schema_errors(MAN_SCHEMA, o):
        disagree.append("manifest: " + name)
check("the JSON Schema rejects what the code rejects (where JSON Schema can say so)", not disagree, disagree)
check("schema repeats the format object and the version, and lists no key_fingerprint property", MAN_SCHEMA["properties"]["schema_version"]["const"] == 2
      and MAN_SCHEMA["properties"]["format"]["properties"]["rule"]["const"] == c.KEV_SHA_RULE_TEXT
      and MAN_SCHEMA["properties"]["format"]["properties"]["columns"]["const"] == list(c.KEV_COLUMNS)
      and "key_fingerprint" not in MAN_SCHEMA["properties"] and "key_fingerprint" not in MAN_SCHEMA["required"])
check("schema documents declare 2020-12", "2020-12" in MAN_SCHEMA["$schema"])
spec = open(os.path.join(c.SCHEMA_DIR, "kev.csv.md")).read()
check("the column spec names every column, the header, the rule id and the kev_sha text", all(col in spec for col in c.KEV_COLUMNS)
      and c.KEV_HEADER in spec and c.KEV_SHA_RULE_ID in spec and "disputed" in spec and "single_channel" in spec
      and 'json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)' in spec)
check("the committed key_fingerprint is nowhere in the code's manifest keys", "key_fingerprint" not in c.MANIFEST_KEYS + c.MANIFEST_OPTIONAL_KEYS)

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

check("local settings missing -> defaults", c.load_local_settings("vulns") == {"project": None, "base_urls": [], "principal": "statefeed-vulns", "contact": "", "mirrors": []})
check("local settings missing with require -> error", raises(c.ConfigError, c.load_local_settings, "vulns", True))
c.ensure_private_dir(c.statefeed_conf())
lp = os.path.join(c.statefeed_conf(), "vulns.json")
open(lp, "w").write(json.dumps({"project": "my-feed", "base_urls": ["https://feed.example.test"], "contact": "ops at example.test"}))
ls = c.load_local_settings("vulns", True)
check("local settings load", ls["project"] == "my-feed" and ls["base_urls"] == ["https://feed.example.test"] and ls["principal"] == "statefeed-vulns" and ls["contact"]
      and ls["mirrors"] == [])
MIRRORS = [{"id": "pages", "kind": "https", "address": "https://feed.example.test", "machine_readable": True},
           {"id": "relay", "kind": "telegram", "address": "@example_feed", "machine_readable": False}]
open(lp, "w").write(json.dumps({"project": "my-feed", "base_urls": ["https://feed.example.test"], "mirrors": MIRRORS}))
check("local settings carry the mirror list (copied, in order)", c.load_local_settings("vulns", True)["mirrors"] == MIRRORS
      and c.load_local_settings("vulns")["mirrors"] is not MIRRORS)
open(lp, "w").write(json.dumps({"mirrors": MIRRORS}))
check("mirrors load without require, even before a project is configured", c.load_local_settings("vulns")["mirrors"] == MIRRORS)
res = {}
for name, body in {"project caps": {"project": "My Feed", "base_urls": ["https://x.test"]}, "http url": {"project": "p", "base_urls": ["http://x.test"]},
                   "trailing slash": {"project": "p", "base_urls": ["https://x.test/"]}, "principal flag": {"project": "p", "base_urls": ["https://x.test"], "principal": "-Ox"},
                   "no base": {"project": "p"}, "not object": [],
                   "mirrors not a list": {"project": "p", "base_urls": ["https://x.test"], "mirrors": "https://m.test"},
                   "mirrors empty": {"project": "p", "base_urls": ["https://x.test"], "mirrors": []},
                   "mirror http": {"project": "p", "base_urls": ["https://x.test"], "mirrors": [dict(MIRRORS[0], address="http://m.test")]},
                   "mirror duplicate id": {"project": "p", "base_urls": ["https://x.test"], "mirrors": [MIRRORS[0], dict(MIRRORS[1], id="pages")]},
                   "mirror 9 entries": {"project": "p", "base_urls": ["https://x.test"], "mirrors": [dict(MIRRORS[0], id=f"m{n}") for n in range(9)]},
                   "mirror bad handle": {"project": "p", "base_urls": ["https://x.test"], "mirrors": [dict(MIRRORS[1], address="@a")]}}.items():
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
    check("a real ed25519 signature fits the room kept for it (SIG_RESERVE_BYTES), with a long key comment too",
          len(sigb) <= c.SIG_RESERVE_BYTES, len(sigb))
    check("signed manifest + signature of the size-cap test fit the cap through feed_size_problem", c.feed_size_problem(data, sigb) is None)
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
