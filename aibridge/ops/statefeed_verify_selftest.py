#!/usr/bin/env python3
"""Offline test of statefeed/verify.py (the consumer): feed trees are signed with a throwaway ed25519 key (real ssh-keygen -Y) and
served from local http.server instances on 127.0.0.1. Covers the ok path and the v1.1 result (rows as dicts, delta, epss, format,
mirrors), a tampered manifest, a wrong principal or key, tampered or missing files, strict kev.csv parsing, rollback / conflict /
chain checks against the state file, stale and expired feeds, a server that is down, the size cap, redirects, setup errors, key
rotation, several sources (--mirror: highest valid seq, behind, seq_conflict, unreachable, dir: and file: sources, learned mirrors
printed and never fetched), a fresh connection for every file, the offline subcommand, and the CLI exit codes. No network, no LAN.
Stdlib only: python3 -I ops/statefeed_verify_selftest.py"""
import http.server, inspect, json, os, subprocess, sys, tempfile, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from statefeed import common as c
from statefeed import verify as v

os.environ["no_proxy"] = "*"
for k in list(os.environ):
    if k.startswith("STATEFEED_"):
        del os.environ[k]
TMP = tempfile.mkdtemp(prefix="sf-verify-")
T0 = c.parse_iso("2026-11-13T12:00:00Z")
os.environ["STATEFEED_FAKE_NOW"] = str(T0)
fails = []


def check(name, ok, detail=""):
    if ok:
        print(f"ok {name}")
    else:
        fails.append(name)
        print(f"FAIL {name} {detail}")


if not c.have_ssh_sign():
    print("SKIP statefeed verify checks: this ssh-keygen has no -Y sign/verify support, so nothing can be signed here")
    print("all statefeed verify checks passed (signing tests skipped)")
    sys.exit(0)

URLS = []                                   # every URL verify.py asked c.http_get for
_real_get = c.http_get


def _logged_get(url, *a, **k):
    URLS.append(url)
    return _real_get(url, *a, **k)


c.http_get = _logged_get


# ------------------------------------------------------------------ the fake world: servers with their own files
class World:
    def __init__(self):
        self.feed, self.hits, self.redirect, self.log = {}, {}, {}, []
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.srv.world = self
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def reset(self):
        self.feed.clear(), self.hits.clear(), self.redirect.clear(), self.log.clear()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"           # keep-alive is possible: a client that reused a connection would be seen

    def do_GET(self):
        w = self.server.world
        w.hits[self.path] = w.hits.get(self.path, 0) + 1
        w.log.append((self.path, self.client_address[1], self.headers.get("Connection")))
        if self.path in w.redirect:
            self.send_response(302)
            self.send_header("Location", w.redirect[self.path])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = w.feed.get(self.path)
        if body is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass   # the client stopped reading: it hit its size cap

    def log_message(self, *a):
        pass


W = World()
BASE = W.base
FEED, HITS, REDIRECT = W.feed, W.hits, W.redirect

KEYDIR = os.path.join(TMP, "keys")
PUB1 = c.generate_signing_key(os.path.join(KEYDIR, "k1"))
PUB2 = c.generate_signing_key(os.path.join(KEYDIR, "k2"))
K1, K2 = os.path.join(KEYDIR, "k1"), os.path.join(KEYDIR, "k2")
ALLOWED = os.path.join(TMP, "allowed_signers")
with open(ALLOWED, "w") as f:
    f.write(c.allowed_signers_line("statefeed-vulns", PUB1) + "\n" + c.allowed_signers_line("statefeed-other", PUB1) + "\n")
PR = "statefeed-vulns"


def row(cve, flag="", epss="0.5", pct="0.9", date="2026-11-01", sha=None):
    return {"cve": cve, "date_added": date, "kev_sha": sha or c.sha256_bytes(cve.encode())[:16], "epss": epss, "epss_pct": pct,
            "flag": flag}


ROWS = [row("CVE-2024-0002", flag="disputed", epss="", pct=""), row("CVE-2024-0001", epss="0.00043", pct="0.0996"),
        row("CVE-2023-12345", date="2026-01-02", epss="1.0", pct="1")]
SORTED = sorted(ROWS, key=lambda r: c.cve_sort_key(r["cve"]))
EPSS_BLOCK = {"model_version": "v2025.03.14", "score_date": "2026-11-12"}
MIRRORS = [{"id": "chat", "kind": "telegram", "address": "@example_feed", "machine_readable": False},
           {"id": "pages", "kind": "https", "address": "https://mirror.example.test/feed", "machine_readable": True}]
_n = [0]


def csv_bytes(rows):
    return c.rows_to_csv(rows)


def publish(seq=1, rows=None, generated=T0 - 3600, valid_days=3, prev=None, key=K1, mutate=None, csv=None, count=None, topic="vulns",
            delta="auto", mirrors=None, epss="auto", world=None):
    """Build, sign and serve a feed into `world` (default W, cleared first). -> (manifest dict, manifest bytes, signature bytes,
    csv bytes)."""
    world = world or W
    rows = ROWS if rows is None else rows
    cb = csv if csv is not None else csv_bytes(rows)
    n = count if count is not None else len(cb.splitlines()) - 1
    snap = c.snap_id(seq, generated)
    path = f"v1/snapshots/{snap}/kev.csv"
    if delta == "auto":
        delta = {"since_seq": seq - 1 if seq > 1 else None, "full": True, "counts": {"added": 0, "removed": 0, "changed": 0}}
    m = {"topic": topic, "schema_version": 2, "seq": seq, "prev_digest": prev, "generated_at": c.iso(generated),
         "valid_until": c.iso_plus_days(generated, valid_days), "item_count": n, "untrusted_text": False,
         "ai_generated": False, "compiled_by": "statefeed/1 (code, no AI)",
         "licence": {"compilation": "CC-BY-4.0", "records": "see sources[].licence"}, "check_set_version": "abc123def456",
         "sources": [{"id": "kev-cisa", "url": "https://example.test/kev.json", "retrieved_at": c.iso(generated - 600),
                      "content_sha256": "b" * 64, "bytes": 1234, "status": "ok",
                      "ref": {"catalog_version": "2026.11.12", "date_released": "2026-11-12T15:00:00.000Z"}}],
         "files": [{"path": path, "sha256": c.sha256_bytes(cb), "bytes": len(cb)}], "snapshot": snap,
         "publish_record": {"approval": "human"}, "format": c.kev_format(), "delta": delta,
         "epss": dict(EPSS_BLOCK) if epss == "auto" else epss}
    if mirrors is not None:
        m["mirrors"] = mirrors
    if mutate:
        mutate(m)
    mb = c.canonical_json(m)
    _n[0] += 1
    d = os.path.join(TMP, f"sign{_n[0]}")
    os.makedirs(d)
    mp = os.path.join(d, "manifest.json")
    with open(mp, "wb") as f:
        f.write(mb)
    with open(c.ssh_sign(key, mp), "rb") as f:
        sig = f.read()
    world.reset()
    world.feed.update({"/v1/latest/manifest.json": mb, "/v1/latest/manifest.json.sig": sig, "/" + path: cb,
                       f"/v1/snapshots/{snap}/manifest.json": mb})
    return m, mb, sig, cb


def write_tree(root, m, mb, sig, cb):
    """The same files as a site tree on disk (dir: and file: sources)."""
    snap = m["snapshot"]
    for rel, data in (("v1/latest/manifest.json", mb), ("v1/latest/manifest.json.sig", sig), (m["files"][0]["path"], cb),
                      (f"v1/snapshots/{snap}/manifest.json", mb), (f"v1/snapshots/{snap}/manifest.json.sig", sig)):
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)


def state_file():
    _n[0] += 1
    return os.path.join(TMP, f"state{_n[0]}.json")


def run(state=None, **kw):
    return v.verify_feed(kw.pop("base", BASE), kw.pop("allowed", ALLOWED), kw.pop("principal", PR), state, **kw)


def read_state(p):
    return c.read_json(p)


# ------------------------------------------------------------------ 1. the ok path
m, mb, sig, cb = publish(1, mirrors=MIRRORS)
st = state_file()
r = run(st)
check("a good feed verifies: state ok, rows returned as dicts in CVE order", r["state"] == "ok" and r["reason"] == "ok" and r["seq"] == 1
      and r["items"] == SORTED and r["item_count"] == 3, str(r)[:300])
check("the result carries snapshot, times, topic and the manifest digest",
      r["snapshot"] == "2026-11-13-1" and r["topic"] == "vulns" and r["manifest_sha256"] == c.sha256_bytes(mb)
      and r["generated_at"] == c.iso(T0 - 3600) and r["valid_until"] == c.iso_plus_days(T0 - 3600, 3))
check("the result carries delta, epss, format and the learned mirrors from the signed manifest",
      r["delta"] == m["delta"] and r["epss"] == EPSS_BLOCK and r["format"] == c.kev_format() and r["mirrors"] == MIRRORS, str(r)[:400])
check("the result lists the source it used", r["chosen"] == BASE and r["sources"] == [
    {"source": BASE, "state": "ok", "reason": "ok", "seq": 1, "behind": False}], str(r["sources"]))
s = read_state(st)
check("an accepted feed writes the state file (seq, digest, snapshot), mode 0600",
      s and s["seq"] == 1 and s["digest"] == c.sha256_bytes(mb) and s["snapshot"] == "2026-11-13-1"
      and (os.stat(st).st_mode & 0o777) == 0o600)
r2 = run(st)
check("the same publish verified again is fine (equal seq, same manifest)", r2["state"] == "ok" and r2["seq"] == 1)
check("verify_feed works without a state file", run()["state"] == "ok")
check("verify_feed has the documented signature",
      list(inspect.signature(v.verify_feed).parameters) == ["base", "allowed_signers", "principal", "state_path", "max_age_days", "mirrors"]
      and inspect.signature(v.verify_feed).parameters["max_age_days"].default == 3)
check("a trailing slash on the base URL is fine", run(base=BASE + "/")["state"] == "ok")
publish(1, rows=[], csv=csv_bytes([]), epss=None, mirrors=None)
r = run()
check("an empty feed (0 rows) that is signed and consistent verifies", r["state"] == "ok" and r["items"] == [] and r["mirrors"] == []
      and r["epss"] is None, str(r)[:200])

# ------------------------------------------------------------------ 2. signature and identity
m, mb, sig, cb = publish(1)
FEED["/v1/latest/manifest.json"] = mb.replace(b'"seq":1', b'"seq":9')
st = state_file()
r = run(st)
check("a tampered manifest is invalid (bad_signature), no items, no state written",
      r["state"] == "invalid" and r["reason"] == "bad_signature" and "items" not in r and not os.path.exists(st), str(r)[:200])
check("a failed signature retries the manifest pair once", HITS.get("/v1/latest/manifest.json") == 2, str(HITS))

publish(1)
r = run(principal="statefeed-nobody")
check("a principal that is not in allowed_signers is invalid", r["state"] == "invalid" and r["reason"] == "bad_signature")
publish(1, key=K2)
r = run()
check("a manifest signed by a key that is not pinned is invalid", r["state"] == "invalid" and r["reason"] == "bad_signature")
publish(1)
FEED["/v1/latest/manifest.json.sig"] = FEED["/v1/latest/manifest.json.sig"][:-20]
check("a damaged signature is invalid", run()["reason"] == "bad_signature")
FEED["/v1/latest/manifest.json.sig"] = b""
check("an empty signature is invalid", run()["reason"] == "bad_signature")

publish(1, topic="other")
r = run(principal="statefeed-vulns")
check("a manifest signed for another topic is refused even with the same key (topic_mismatch)",
      r["state"] == "invalid" and r["reason"] == "topic_mismatch", str(r)[:200])
check("the same manifest is fine for the principal of its own topic", run(principal="statefeed-other")["state"] == "ok")

# a signature over another namespace must not pass
publish(1)
d = os.path.join(TMP, "ns")
os.makedirs(d)
with open(os.path.join(d, "manifest.json"), "wb") as f:
    f.write(FEED["/v1/latest/manifest.json"])
subprocess.run(["ssh-keygen", "-Y", "sign", "-f", K1, "-n", "other-namespace", os.path.join(d, "manifest.json")],
               capture_output=True, check=True)
with open(os.path.join(d, "manifest.json.sig"), "rb") as f:
    FEED["/v1/latest/manifest.json.sig"] = f.read()
check("a signature made in a different namespace is invalid", run()["reason"] == "bad_signature")

# a valid signature over a manifest that breaks the schema
publish(1, mutate=lambda m: m.update(item_count=-1))
r = run()
check("a signed manifest that fails the schema is invalid (manifest_schema)", r["state"] == "invalid" and r["reason"] == "manifest_schema")
publish(1, mutate=lambda m: m.pop("files"))
check("a signed manifest with a missing field is invalid", run()["reason"] == "manifest_schema")
publish(1, mutate=lambda m: m.update(schema_version=1))
check("a signed manifest in the old schema version is invalid", run()["reason"] == "manifest_schema")
publish(1, mutate=lambda m: m.update(key_fingerprint="SHA256:abc"))
check("a signed manifest that carries a key_fingerprint is invalid (a self-asserted key adds no trust)",
      run()["reason"] == "manifest_schema")
publish(1, mirrors=[{"id": "x", "kind": "https", "address": "http://plain.example.test/", "machine_readable": True}])
check("a signed manifest with a non-https mirror is invalid", run()["reason"] == "manifest_schema")
m, mb, sig, cb = publish(1)
dup = mb.replace(b'"seq":1,', b'"seq":1,"seq":2,', 1)
d = os.path.join(TMP, "dup")
os.makedirs(d)
with open(os.path.join(d, "manifest.json"), "wb") as f:
    f.write(dup)
FEED["/v1/latest/manifest.json"] = dup
FEED["/v1/latest/manifest.json.sig"] = open(c.ssh_sign(K1, os.path.join(d, "manifest.json")), "rb").read()
check("a signed manifest with duplicate keys is invalid (manifest_unparsable)", run()["reason"] == "manifest_unparsable")
publish(1)
FEED["/v1/latest/manifest.json"] = b"\xff\xfe not json"
check("a manifest that is not JSON is invalid", run()["state"] == "invalid")

# ------------------------------------------------------------------ 3. files and rows
m, mb, sig, cb = publish(1)
path = "/" + m["files"][0]["path"]
bad = FEED[path].replace(b"2026-11-01", b"2026-11-02", 1)
FEED[path] = bad
r = run()
check("tampered rows of the same size are invalid (file_hash_mismatch), no items", r["state"] == "invalid"
      and r["reason"] == "file_hash_mismatch" and "items" not in r, str(r)[:200])
check("a mismatching file is fetched twice before it is called invalid", HITS.get(path) == 2, str(HITS))
FEED[path] = FEED[path] + b"x"
check("a longer file is invalid (file_size_mismatch)", run()["reason"] == "file_size_mismatch")
FEED[path] = b"x" * (len(bad) + 5000)
check("a much larger file is invalid and not downloaded in full", run()["reason"] == "file_size_mismatch")
FEED[path] = bad[:-30]
check("a shorter file is invalid (file_size_mismatch)", run()["reason"] == "file_size_mismatch")
del FEED[path]
r = run()
check("a snapshot file that is missing is unavailable (file_unreachable), not invalid", r["state"] == "unavailable"
      and r["reason"] == "file_unreachable", str(r)[:200])
st = state_file()
check("an unavailable or invalid answer never touches the state file", not os.path.exists(st) and run(st)["state"] == "unavailable"
      and not os.path.exists(st))

# a flaky file: the first answer is wrong, the retry is right
publish(1)
calls = {"n": 0}
orig = Handler.do_GET


def flaky(self):
    if self.path.endswith("/kev.csv"):
        calls["n"] += 1
        if calls["n"] == 1:
            self.server.world.feed[self.path], keep = b"garbage", self.server.world.feed[self.path]
            try:
                return orig(self)
            finally:
                self.server.world.feed[self.path] = keep
    return orig(self)


Handler.do_GET = flaky
r = run()
Handler.do_GET = orig
check("one bad download followed by a good one is accepted", r["state"] == "ok" and calls["n"] == 2, str(r)[:200])

# strict kev.csv: every case is hash-correct and signed, only the content is wrong
good_csv = csv_bytes(SORTED)
lines = good_csv.split(b"\n")


def csv_case(name, data, why="csv_invalid", detail=None, seq=1, **kw):
    publish(seq, csv=data, **kw)
    r = run()
    check(name, r["state"] == "invalid" and r["reason"] == why and "items" not in r and (detail is None or detail in r.get("detail", "")),
          str(r)[:300])


csv_case("a row with an impossible date makes the whole feed invalid, no partial accept", good_csv.replace(b"2026-11-01", b"2026-13-45", 1),
         detail="date")
csv_case("a header that is not exact is invalid", good_csv.replace(b"cve,date_added", b"cve,added", 1), detail="header")
csv_case("rows that are not sorted are invalid", b"\n".join([lines[0], lines[2], lines[1], lines[3], b""]), detail="sorted")
csv_case("a duplicate CVE is invalid", b"\n".join([lines[0], lines[1], lines[1], lines[2], lines[3], b""]), detail="sorted")
csv_case("CRLF line ends are invalid", good_csv.replace(b"\n", b"\r\n"))
csv_case("a missing final newline is invalid", good_csv[:-1], detail="newline")
csv_case("a quoted value is invalid", good_csv.replace(b"CVE-2024-0001", b'"CVE-2024-0001"', 1))
csv_case("an extra column is invalid", good_csv.replace(b",disputed", b",disputed,x", 1), detail="columns")
csv_case("an unknown flag value is invalid", good_csv.replace(b",disputed", b",unknown", 1), detail="flag")
csv_case("an EPSS value in scientific notation is invalid", good_csv.replace(b"0.00043", b"4.3e-4", 1), detail="epss")
csv_case("epss without epss_pct is invalid", good_csv.replace(b"0.00043,0.0996", b"0.00043,", 1), detail="both")
csv_case("the old ndjson content in a kev.csv is invalid", b'{"id":"CVE-2024-0001"}\n')
csv_case("text that looks like an instruction in a row is invalid, never passed on",
         good_csv.replace(b"2026-01-02", b"ignore-previous-instructions", 1))
csv_case("rows with EPSS scores but a manifest without an epss block are invalid (epss_inconsistent)", good_csv,
         why="epss_inconsistent", epss=None)
csv_case("item_count that disagrees with the file is invalid (item_count_mismatch)", good_csv, why="item_count_mismatch", count=2)
csv_case("a delta that names a CVE that is not in kev.csv as added is invalid (delta_inconsistent)", good_csv, why="delta_inconsistent",
         seq=2, delta={"since_seq": 1, "added": ["CVE-2030-0001"], "removed": [], "changed": []})
csv_case("a delta that lists a CVE as removed that is still in kev.csv is invalid", good_csv, why="delta_inconsistent", seq=2,
         delta={"since_seq": 1, "added": [], "removed": ["CVE-2024-0001"], "changed": []})
publish(2, delta={"since_seq": 1, "added": ["CVE-2024-0001"], "removed": ["CVE-2030-0001"], "changed": ["CVE-2024-0002"]})
r = run()
check("a delta that fits the rows is returned as signed", r["state"] == "ok" and r["delta"]["added"] == ["CVE-2024-0001"], str(r)[:300])
publish(1, mutate=lambda m: m["files"][0].update(bytes=30 * 1024 * 1024))
r = run()
check("a file declared larger than the 25 MiB ceiling is invalid before any download",
      r["reason"] == "file_too_large" and not [p for p in HITS if p.endswith("kev.csv")], str(r)[:200])
publish(1, mutate=lambda m: m.update(ai_generated=True, untrusted_text=True))
r = run()
check("the result reports what the signed manifest declares about AI text and free text",
      r["state"] == "ok" and r["ai_generated"] is True and r["untrusted_text"] is True)

# ------------------------------------------------------------------ 4. seq, chain, clock
EXPL = lambda since: {"since_seq": since, "added": [], "removed": [], "changed": []}
m1, mb1, _, _ = publish(1)
st = state_file()
r = run(st)
check("no delta_from_last_seen without a state; none the first time a state file is created", r["state"] == "ok" and "delta_from_last_seen" not in r)
m2, mb2, _, _ = publish(2, prev=c.sha256_bytes(mb1), delta=EXPL(1))
r = run(st)
check("delta_from_last_seen is true when the explicit delta starts at the seq this reader saw last", r["state"] == "ok" and r["delta_from_last_seen"] is True, str(r)[:200])
m4, mb4, _, _ = publish(4, prev="e" * 64, delta=EXPL(3))
r = run(st)
check("delta_from_last_seen is false when snapshots were skipped: the reader must diff the rows", r["state"] == "ok" and r["delta_from_last_seen"] is False)
m1, mb1, _, _ = publish(1)
st = state_file()
run(st)
publish(2, prev=c.sha256_bytes(mb1))
r = run(st)
check("delta_from_last_seen is false for the full form, which lists no ids", r["state"] == "ok" and r["delta_from_last_seen"] is False)
m1, mb1, _, _ = publish(1)
st = state_file()
check("seed state with seq 1", run(st)["state"] == "ok")
m2, mb2, _, _ = publish(2, prev=c.sha256_bytes(mb1))
r = run(st)
check("seq 2 chained to seq 1 is accepted and the state moves", r["state"] == "ok" and r["seq"] == 2 and read_state(st)["seq"] == 2)
publish(1)
r = run(st)
check("a lower seq than the state is invalid (seq_rollback)", r["state"] == "invalid" and r["reason"] == "seq_rollback"
      and read_state(st)["seq"] == 2, str(r)[:200])
publish(2, prev=c.sha256_bytes(mb1), generated=T0 - 1800)
r = run(st)
check("the same seq with different content is invalid (seq_conflict)", r["state"] == "invalid" and r["reason"] == "seq_conflict"
      and read_state(st)["seq"] == 2)
publish(3, prev="c" * 64)
r = run(st)
check("seq+1 whose prev_digest does not match the stored digest is invalid (chain_broken)", r["reason"] == "chain_broken", str(r)[:200])
publish(5, prev="d" * 64)
r = run(st)
check("a gap in seq (missed publishes) is fine, the chain cannot be checked across it", r["state"] == "ok" and r["seq"] == 5)
publish(7, prev=None, generated=T0 + 3600)
r = run(st)
check("a manifest generated in the future is invalid", r["reason"] == "generated_in_future", str(r)[:200])
publish(7, prev=None, generated=T0 + 300)
check("a few minutes of clock skew are tolerated", run(st)["state"] == "ok")
with open(st, "w") as f:
    f.write("not json")
r = run(st)
check("a corrupt state file is a setup error, not a pass", r["state"] == "invalid" and r["reason"] == "setup_error")
with open(st, "w") as f:
    f.write('{"seq":"two"}')
check("a state file with a wrong shape is a setup error", run(st)["reason"] == "setup_error")
st2 = os.path.join(TMP, "nodir", "state.json")
publish(1)
r = run(st2)
check("an unwritable state path still returns the verified feed, with a warning", r["state"] == "ok" and "state_warning" in r, str(r)[:200])

# ------------------------------------------------------------------ 5. freshness
publish(1, generated=T0 - 5 * 86400, valid_days=3)
st = state_file()
r = run(st)
check("valid_until in the past is stale (valid_until_passed), rows still returned, state updated",
      r["state"] == "stale" and r["reason"] == "valid_until_passed" and len(r["items"]) == 3 and read_state(st)["seq"] == 1, str(r)[:200])
publish(1, generated=T0 - 4 * 86400, valid_days=10)
r = run()
check("older than max_age_days is stale even before valid_until (max_age_exceeded)", r["state"] == "stale" and r["reason"] == "max_age_exceeded")
check("max_age_days is a parameter", run(max_age_days=5)["state"] == "ok" and run(max_age_days=None)["state"] == "ok"
      and run(max_age_days=2)["state"] == "stale")
check("a bad max_age_days is a setup error", run(max_age_days=0)["reason"] == "setup_error" and run(max_age_days="3")["reason"] == "setup_error")
publish(1, generated=T0 - 86400, valid_days=3)
check("a fresh manifest is ok", run()["state"] == "ok")
publish(1, generated=T0 - 5 * 86400, valid_days=3, csv=good_csv[:-5] + b"zzzzz")
check("stale never hides a broken file: invalid wins over stale", run()["state"] == "invalid")

# ------------------------------------------------------------------ 6. availability, redirects, size
publish(1)
dead = World()
dead_base = dead.base
dead.stop()
r = run(base=dead_base)
check("a server that is down is unavailable (manifest_unreachable)", r["state"] == "unavailable" and r["reason"] == "manifest_unreachable"
      and "items" not in r, str(r)[:200])
del FEED["/v1/latest/manifest.json"]
r = run()
check("a 404 on the manifest is unavailable", r["state"] == "unavailable" and "HTTP 404" in r["detail"])
publish(1)
del FEED["/v1/latest/manifest.json.sig"]
check("a missing signature file is unavailable", run()["state"] == "unavailable")
publish(1)
FEED["/v1/latest/manifest.json"] = b"{" + b" " * (v.MANIFEST_MAX + 10)
r = run()
check("a manifest over the 16 KiB reading cap is invalid (manifest_too_large), not read further",
      r["state"] == "invalid" and r["reason"] == "manifest_too_large", str(r)[:200])
publish(1, mutate=lambda m: m.update(pad="x" * 4000))
r = run()
check("a signed manifest and signature over 3,500 bytes together are invalid (manifest_too_large)",
      r["state"] == "invalid" and r["reason"] == "manifest_too_large" and "3500" in r["detail"], str(r)[:300])
m, mb, sig, cb = publish(1, mirrors=[{"id": f"m{i}", "kind": "https", "address": f"https://mirror{i}.example.test/feed", "machine_readable": True}
                                     for i in range(7)] + [MIRRORS[0]])
r = run()
check("a feed with eight mirrors is well under 3,500 bytes with its signature and verifies",
      r["state"] == "ok" and len(mb) + len(sig) <= 3500 and len(r["mirrors"]) == 8, (len(mb), len(sig)))
publish(1)
REDIRECT["/v1/latest/manifest.json"] = f"http://localhost:{W.srv.server_address[1]}/v1/latest/manifest.json"
r = run()
check("a redirect to another host is refused (unavailable)", r["state"] == "unavailable", str(r)[:200])
publish(1)
REDIRECT["/v1/latest/manifest.json"] = "/v1/latest/manifest.json"
check("a redirect loop ends in unavailable, not a hang", run()["state"] == "unavailable")
publish(1)
FEED["/other/manifest.json"] = FEED["/v1/latest/manifest.json"]
REDIRECT["/v1/latest/manifest.json"] = "/other/manifest.json"
check("a same-host redirect is followed", run()["state"] == "ok")

# ------------------------------------------------------------------ 7. setup errors never look like a forgery
publish(1)
r = run(allowed=os.path.join(TMP, "missing"))
check("a missing allowed_signers file is a setup error", r["state"] == "invalid" and r["reason"] == "setup_error")
check("a plain-http base that is not loopback is a setup error", run(base="http://example.org")["reason"] == "setup_error")
check("a non-string base is a setup error", run(base=None)["reason"] == "setup_error")
check("a base with a query or a fragment is a setup error",
      run(base=BASE + "?x=1")["reason"] == "setup_error" and run(base=BASE + "/#top")["reason"] == "setup_error")
n_urls = len(URLS)
check("a mirror that cannot be used is a setup error, nothing is fetched",
      run(mirrors=["ftp://x.example.test"])["reason"] == "setup_error" and run(mirrors=["dir:" + os.path.join(TMP, "nodir")])["reason"] == "setup_error"
      and run(mirrors=["file:" + os.path.join(TMP, "nofile.json")])["reason"] == "setup_error" and len(URLS) == n_urls)
check("a principal with shell or option characters is a setup error",
      run(principal="-Ox")["reason"] == "setup_error" and run(principal="a b")["reason"] == "setup_error")
check("verify_feed never raises on junk arguments", all(isinstance(run(base=b, allowed=a, principal=p)["state"], str)
      for b, a, p in ((1, 2, 3), ("", "", ""), (BASE, ALLOWED, ""), ([], {}, None))))

# ------------------------------------------------------------------ 8. key rotation
rot = os.path.join(TMP, "allowed_rot")
with open(rot, "w") as f:
    f.write(c.allowed_signers_line(PR, PUB1, valid_before="20260101") + "\n" + c.allowed_signers_line(PR, PUB2, valid_after="20260101") + "\n")
publish(1, key=K2)
check("rotation: the new key in a two-line allowed_signers verifies", run(allowed=rot)["state"] == "ok")
publish(1, key=K1)
r = run(allowed=rot)
check("rotation: the retired key (valid-before in the past) no longer verifies", r["state"] == "invalid" and r["reason"] == "bad_signature", str(r)[:200])
publish(1, key=K1)
check("rotation: the old key still verifies while only it is listed", run()["state"] == "ok")

# ------------------------------------------------------------------ 9. a fresh connection for every file
publish(1)
r = run()
ports = [(p, port, hdr) for p, port, hdr in W.log if p.endswith(("manifest.json", "manifest.json.sig", "kev.csv"))]
check("every file is fetched on its own connection (manifest, signature and kev.csv use three different client ports)",
      r["state"] == "ok" and len(ports) == 3 and len({port for _, port, _ in ports}) == 3, str(ports))
check("each request asks the server to close the connection", all(hdr == "close" for _, _, hdr in ports), str(ports))

# ------------------------------------------------------------------ 10. several sources
WA, WB, WC = World(), World(), World()
m1, mb1, _, _ = publish(1, world=WB)
mA, mbA, sigA, cbA = publish(2, prev=c.sha256_bytes(mb1), world=WA)
st = state_file()
r = v.verify_feed(WA.base, ALLOWED, PR, st, mirrors=[WB.base])
check("two sources: the highest valid seq is used, the other is reported behind",
      r["state"] == "ok" and r["seq"] == 2 and r["chosen"] == WA.base and [(x["source"], x["seq"], x["behind"], x["state"]) for x in r["sources"]]
      == [(WA.base, 2, False, "ok"), (WB.base, 1, True, "ok")] and read_state(st)["seq"] == 2, str(r)[:400])
r = v.verify_feed(WB.base, ALLOWED, PR, None, mirrors=[WA.base])
check("the order of the sources does not matter: the higher seq wins", r["seq"] == 2 and r["chosen"] == WA.base
      and r["sources"][0]["behind"] is True and r["sources"][1]["behind"] is False)
r = v.verify_sources([WA.base, WB.base, WA.base + "/"], ALLOWED, PR)
check("the same source listed twice is harmless", r["state"] == "ok" and r["seq"] == 2 and len(r["sources"]) == 3)

publish(2, prev=c.sha256_bytes(mb1), world=WC, generated=T0 - 1000)
r = v.verify_feed(WA.base, ALLOWED, PR, st, mirrors=[WC.base])
check("two valid sources with the same seq and different content are a seq_conflict: invalid, no rows, state untouched",
      r["state"] == "invalid" and r["reason"] == "seq_conflict" and "items" not in r and read_state(st)["seq"] == 2
      and read_state(st)["digest"] == c.sha256_bytes(mbA), str(r)[:300])
fresh = state_file()
r = v.verify_feed(WA.base, ALLOWED, PR, fresh, mirrors=[WC.base, WB.base])
check("a conflict at the newest seq is found even when other sources are fine, and no state is written",
      r["reason"] == "seq_conflict" and not os.path.exists(fresh) and {x["seq"] for x in r["sources"]} == {2, 1}, str(r)[:300])
publish(2, prev=c.sha256_bytes(mb1), world=WC)
r = v.verify_feed(WA.base, ALLOWED, PR, None, mirrors=[WC.base])
check("two sources with the same seq and the same content agree", r["state"] == "ok" and all(not x["behind"] for x in r["sources"]))

# a source that serves the newest seq with a broken file does not hide an older valid one
publish(1, world=WB)
mA3, mbA3, _, _ = publish(2, prev=c.sha256_bytes(mb1), world=WA)
pa = "/" + mA3["files"][0]["path"]
WA.feed[pa] = WA.feed[pa].replace(b"2026-11-01", b"2026-11-02", 1)
r = v.verify_feed(WA.base, ALLOWED, PR, None, mirrors=[WB.base])
check("the highest VALID seq wins: a newer manifest with tampered rows is reported invalid, the older valid source is used",
      r["state"] == "ok" and r["seq"] == 1 and r["chosen"] == WB.base
      and [(x["state"], x["reason"], x["seq"]) for x in r["sources"]] == [("invalid", "file_hash_mismatch", 2), ("ok", "ok", 1)], str(r)[:400])
publish(2, prev=c.sha256_bytes(mb1), world=WA)
WA.feed.pop("/v1/latest/manifest.json")
r = v.verify_feed(WA.base, ALLOWED, PR, None, mirrors=[WB.base])
check("an unreachable source does not matter while another one is valid", r["state"] == "ok" and r["chosen"] == WB.base
      and r["sources"][0]["state"] == "unavailable" and r["sources"][0]["seq"] is None and r["sources"][0]["behind"] is False)
r = v.verify_feed(WA.base, ALLOWED, PR, None, mirrors=[dead_base])
check("all sources unreachable: unavailable", r["state"] == "unavailable" and r["reason"] == "manifest_unreachable" and "items" not in r)
publish(1, world=WB, key=K2)
r = v.verify_feed(WA.base, ALLOWED, PR, None, mirrors=[WB.base])
check("one unreachable and one forged source: invalid says more than unavailable, nothing is accepted",
      r["state"] == "invalid" and r["reason"] == "bad_signature" and "items" not in r)
publish(1, world=WB)
publish(2, prev=c.sha256_bytes(mb1), world=WA)
st3 = state_file()
check("seed state seq 2", v.verify_feed(WA.base, ALLOWED, PR, st3)["state"] == "ok")
r = v.verify_feed(WB.base, ALLOWED, PR, st3, mirrors=[WA.base])
check("with a state at seq 2 a mirror at seq 1 is a rollback for that mirror only: the answer comes from the other one",
      r["state"] == "ok" and r["seq"] == 2 and r["sources"][0]["reason"] == "seq_rollback" and r["sources"][0]["behind"] is True)
r = v.verify_feed(WB.base, ALLOWED, PR, st3)
check("a rollback source alone is invalid (seq_rollback)", r["state"] == "invalid" and r["reason"] == "seq_rollback")

# learned mirrors are printed, never fetched
m, mb, sig, cb = publish(1, world=WA, mirrors=MIRRORS)
URLS.clear()
r = v.verify_feed(WA.base, ALLOWED, PR)
check("mirrors in the signed manifest are printed", r["mirrors"] == MIRRORS)
check("learned mirrors are never fetched automatically (only the given source was asked)",
      URLS and all(u.startswith(WA.base) for u in URLS) and not any("example.test" in u for u in URLS), str(URLS))

# dir: and file: sources
tree = os.path.join(TMP, "tree")
m, mb, sig, cb = publish(3, prev="e" * 64, world=WA)
write_tree(tree, m, mb, sig, cb)
r = v.verify_sources(["dir:" + tree], ALLOWED, PR)
check("a dir: source (a site tree on disk) verifies like a download", r["state"] == "ok" and r["seq"] == 3 and r["items"] == SORTED
      and r["chosen"] == "dir:" + tree, str(r)[:300])
r = v.verify_sources(["dir:" + tree, WA.base], ALLOWED, PR)
check("a dir: source and a URL for the same snapshot agree", r["state"] == "ok" and all(not x["behind"] for x in r["sources"]))
snapdir = os.path.join(tree, "v1", "snapshots", m["snapshot"])
r = v.verify_sources(["file:" + os.path.join(snapdir, "manifest.json")], ALLOWED, PR)
check("a file: source (a snapshot's manifest with its signature and kev.csv beside it) verifies", r["state"] == "ok" and r["seq"] == 3, str(r)[:300])
r = v.verify_sources(["file:" + os.path.join(tree, "v1", "latest", "manifest.json")], ALLOWED, PR)
check("a file: source for the latest manifest finds kev.csv at the snapshot path under the same root", r["state"] == "ok" and r["seq"] == 3,
      str(r)[:300])
loose = os.path.join(TMP, "loose")
os.makedirs(loose)
for name, data in (("manifest.json", mb), ("manifest.json.sig", sig), ("kev.csv", cb)):
    open(os.path.join(loose, name), "wb").write(data)
r = v.verify_sources(["file:" + os.path.join(loose, "manifest.json")], ALLOWED, PR)
check("a file: source with three loose files in one directory verifies", r["state"] == "ok" and r["seq"] == 3)
os.unlink(os.path.join(loose, "kev.csv"))
r = v.verify_sources(["file:" + os.path.join(loose, "manifest.json")], ALLOWED, PR)
check("a file: source without kev.csv is unavailable (file_unreachable)", r["state"] == "unavailable" and r["reason"] == "file_unreachable")
open(os.path.join(loose, "kev.csv"), "wb").write(cb.replace(b"2026-11-01", b"2026-11-02", 1))
r = v.verify_sources(["file:" + os.path.join(loose, "manifest.json")], ALLOWED, PR)
check("a file: source with a changed kev.csv is invalid (file_hash_mismatch)", r["state"] == "invalid" and r["reason"] == "file_hash_mismatch")
r = v.verify_sources(["dir:" + tree, "file:" + os.path.join(loose, "manifest.json"), WB.base], ALLOWED, PR)
check("dir, file and URL sources mix: each is reported on its own", r["state"] == "ok" and r["seq"] == 3
      and [x["state"] for x in r["sources"]] == ["ok", "invalid", "ok"] and r["sources"][2]["behind"] is True, str(r)[:400])
os.symlink("/nonexistent-target", os.path.join(tree, "v1", "snapshots", "dangling"))
r = v.verify_sources(["dir:" + tree], ALLOWED, PR)
check("a dangling link elsewhere in the tree does not matter", r["state"] == "ok")

# ------------------------------------------------------------------ 11. offline
off = os.path.join(TMP, "offline")
os.makedirs(off)
m, mb, sig, cb = publish(4, prev="f" * 64, world=WA)
paths = {}
for key_, name, data in (("m", "manifest (1).json", mb), ("s", "manifest (1).json.sig", sig), ("d", "kev (2).csv", cb)):
    paths[key_] = os.path.join(off, name)
    open(paths[key_], "wb").write(data)
st = state_file()
r = v.verify_offline(paths["m"], paths["s"], paths["d"], ALLOWED, PR, st)
check("offline: forwarded files with any names verify like a download (same result shape)", r["state"] == "ok" and r["seq"] == 4
      and r["items"] == SORTED and r["delta"] == m["delta"] and r["chosen"] == "offline" and read_state(st)["seq"] == 4, str(r)[:300])
tampered = os.path.join(off, "kev-tampered.csv")
open(tampered, "wb").write(cb.replace(b"2026-11-01", b"2026-11-02", 1))
r = v.verify_offline(paths["m"], paths["s"], tampered, ALLOWED, PR)
check("offline: a changed kev.csv is invalid (file_hash_mismatch)", r["state"] == "invalid" and r["reason"] == "file_hash_mismatch" and "items" not in r)
open(os.path.join(off, "m-tampered.json"), "wb").write(mb.replace(b'"seq":4', b'"seq":9'))
r = v.verify_offline(os.path.join(off, "m-tampered.json"), paths["s"], paths["d"], ALLOWED, PR)
check("offline: a changed manifest is invalid (bad_signature)", r["state"] == "invalid" and r["reason"] == "bad_signature")
r = v.verify_offline(paths["m"], paths["s"], paths["d"], ALLOWED, "statefeed-nobody")
check("offline: the wrong principal is invalid", r["state"] == "invalid" and r["reason"] == "bad_signature")
r = v.verify_offline(paths["m"], os.path.join(off, "nosuchfile"), paths["d"], ALLOWED, PR)
check("offline: a file that cannot be read is a setup error", r["state"] == "invalid" and r["reason"] == "setup_error")
m5, mb5, sig5, cb5 = publish(3, prev="f" * 64, world=WA)
open(os.path.join(off, "m3.json"), "wb").write(mb5)
open(os.path.join(off, "m3.json.sig"), "wb").write(sig5)
open(os.path.join(off, "k3.csv"), "wb").write(cb5)
r = v.verify_offline(os.path.join(off, "m3.json"), os.path.join(off, "m3.json.sig"), os.path.join(off, "k3.csv"), ALLOWED, PR, st)
check("offline: an older forwarded manifest is refused as a rollback against the state file", r["state"] == "invalid" and r["reason"] == "seq_rollback"
      and read_state(st)["seq"] == 4)
big_m = os.path.join(off, "big.json")
open(big_m, "wb").write(b"x" * (v.MANIFEST_MAX + 5))
r = v.verify_offline(big_m, paths["s"], paths["d"], ALLOWED, PR)
check("offline: a manifest file over the reading cap is a setup error (not read)", r["reason"] == "setup_error")

# ------------------------------------------------------------------ 12. the CLI
cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statefeed", "verify.py")
env = dict(os.environ)


def cli_run(*args, base="default"):
    head = [sys.executable, "-I", cli, "fetch"]
    if base is not None:
        head += ["--base", BASE if base == "default" else base]
    p = subprocess.run(head + ["--allowed-signers", ALLOWED, "--principal", PR, *args], capture_output=True, text=True, env=env, timeout=120)
    return p.returncode, p.stdout, p.stderr


publish(1)
st, out_file = state_file(), os.path.join(TMP, "out.json")
code, out, err = cli_run("--state", st)
j = json.loads(out)
check("CLI: ok prints the JSON result with items and exits 0", code == 0 and j["state"] == "ok" and len(j["items"]) == 3 and read_state(st)["seq"] == 1, err)
code, out, err = cli_run("--json-out", out_file)
j, full = json.loads(out), c.read_json(out_file)
check("CLI: --json-out writes the full result and prints a summary without items", code == 0 and "items" not in j and len(full["items"]) == 3
      and full["state"] == "ok" and (os.stat(out_file).st_mode & 0o777) == 0o644)
publish(1, generated=T0 - 9 * 86400)
check("CLI: stale exits 3", cli_run()[0] == 3)
publish(1)
FEED["/v1/latest/manifest.json"] = FEED["/v1/latest/manifest.json"] + b" "
check("CLI: invalid exits 5", cli_run()[0] == 5)
check("CLI: unavailable exits 4", cli_run(base=dead_base)[0] == 4)
code, out, err = cli_run("--max-age-days", "0")
check("CLI: a setup error exits 2 and is still reported as JSON", code == 2 and json.loads(out)["reason"] == "setup_error")
p = subprocess.run([sys.executable, "-I", cli, "fetch"], capture_output=True, text=True, env=env)
check("CLI: missing arguments exit 2", p.returncode == 2)
p = subprocess.run([sys.executable, "-I", cli, "fetch", "--allowed-signers", ALLOWED, "--principal", PR], capture_output=True, text=True, env=env)
check("CLI: fetch without --base and without --mirror exits 2", p.returncode == 2 and "--mirror" in p.stderr, p.stderr)
publish(1)
code, out, err = cli_run("--max-age-days", "2.5")
check("CLI: --max-age-days takes a fraction", code == 0)
check("CLI output is plain ASCII JSON (nothing from the feed can reach a terminal raw)", out.isascii() and "\x1b" not in out)

publish(2, prev="a" * 64, world=WA)
publish(1, world=WB)
code, out, err = cli_run("--mirror", WB.base, "--mirror", WA.base)
j = json.loads(out)
check("CLI: --base plus repeated --mirror, the highest valid seq wins, every source is listed",
      code == 0 and j["seq"] == 2 and [x["seq"] for x in j["sources"]] == [1, 1, 2], out[:400])
code, out, err = cli_run("--mirror", WB.base, "--mirror", WA.base, base=None)
j = json.loads(out)
check("CLI: --mirror alone is enough (no --base)", code == 0 and j["seq"] == 2 and [x["seq"] for x in j["sources"]] == [1, 2]
      and j["sources"][0]["behind"] is True, out[:400])
code, out, err = cli_run("--mirror", "dir:" + os.path.join(TMP, "nodir"), base=None)
check("CLI: a bad --mirror is a setup error (exit 2)", code == 2 and json.loads(out)["reason"] == "setup_error")
publish(2, prev="a" * 64, world=WC, generated=T0 - 500)
code, out, err = cli_run("--mirror", WA.base, "--mirror", WC.base, base=None)
check("CLI: a seq_conflict exits 5", code == 5 and json.loads(out)["reason"] == "seq_conflict")

m, mb, sig, cb = publish(6, prev="b" * 64, world=WA)
open(paths["m"], "wb").write(mb)
open(paths["s"], "wb").write(sig)
open(paths["d"], "wb").write(cb)
st = state_file()
p = subprocess.run([sys.executable, "-I", cli, "offline", "--manifest", paths["m"], "--sig", paths["s"], "--data", paths["d"],
                    "--allowed-signers", ALLOWED, "--principal", PR, "--state", st], capture_output=True, text=True, env=env, timeout=120)
j = json.loads(p.stdout)
check("CLI: offline prints the same JSON and exits 0", p.returncode == 0 and j["state"] == "ok" and j["seq"] == 6 and len(j["items"]) == 3
      and read_state(st)["seq"] == 6, p.stderr)
open(paths["d"], "ab").write(b"x")
p = subprocess.run([sys.executable, "-I", cli, "offline", "--manifest", paths["m"], "--sig", paths["s"], "--data", paths["d"],
                    "--allowed-signers", ALLOWED, "--principal", PR], capture_output=True, text=True, env=env, timeout=120)
check("CLI: offline with a changed data file exits 5", p.returncode == 5 and json.loads(p.stdout)["reason"] == "file_size_mismatch", p.stdout[:200])
p = subprocess.run([sys.executable, "-I", cli, "offline", "--manifest", paths["m"], "--sig", paths["s"], "--data", paths["d"] + ".nope",
                    "--allowed-signers", ALLOWED, "--principal", PR], capture_output=True, text=True, env=env, timeout=120)
check("CLI: offline with a missing file exits 2", p.returncode == 2)
p = subprocess.run([sys.executable, "-I", cli, "offline", "--manifest", paths["m"]], capture_output=True, text=True, env=env, timeout=120)
check("CLI: offline with missing arguments exits 2", p.returncode == 2)

# ------------------------------------------------------------------ 13. hygiene
src = open(cli).read()
check("verify.py uses only the standard library and shells out to nothing itself",
      "subprocess" not in src and "shell=True" not in src and "import requests" not in src)
check("no secret or hostname leaks into the module", "http://192." not in src and "token" not in src.lower().replace("hostname", ""))
check("the old item API is gone from verify.py", "ndjson" not in src and "parse_items" not in src)

for w in (W, WA, WB, WC):
    w.stop()
print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("all statefeed verify checks passed")
