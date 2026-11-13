#!/usr/bin/env python3
"""Offline test of statefeed/verify.py (the consumer): a feed tree is signed with a throwaway ed25519 key (real ssh-keygen -Y)
and served from a local http.server on 127.0.0.1. Covers the ok path, a tampered manifest, a wrong principal or key, tampered
or missing files, rollback / conflict / chain checks against the state file, stale and expired feeds, a server that is down,
bad items, redirects, setup errors, key rotation, and the CLI exit codes. No network, no LAN.
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

# ------------------------------------------------------------------ the fake world
FEED, HITS, REDIRECT = {}, {}, {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        HITS[self.path] = HITS.get(self.path, 0) + 1
        if self.path in REDIRECT:
            self.send_response(302)
            self.send_header("Location", REDIRECT[self.path])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = FEED.get(self.path)
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


def serve():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


SRV = serve()
BASE = f"http://127.0.0.1:{SRV.server_address[1]}"

KEYDIR = os.path.join(TMP, "keys")
PUB1 = c.generate_signing_key(os.path.join(KEYDIR, "k1"))
PUB2 = c.generate_signing_key(os.path.join(KEYDIR, "k2"))
K1, K2 = os.path.join(KEYDIR, "k1"), os.path.join(KEYDIR, "k2")
ALLOWED = os.path.join(TMP, "allowed_signers")
with open(ALLOWED, "w") as f:
    f.write(c.allowed_signers_line("statefeed-vulns", PUB1) + "\n" + c.allowed_signers_line("statefeed-other", PUB1) + "\n")
PR = "statefeed-vulns"


def item(cve, **kw):
    d = {"id": cve, "schema_version": 1, "type": "kev", "vendor": "Example Vendor", "product": "Example Product",
         "name": "Example Product remote code execution", "date_added": "2026-11-01", "due_date": "2026-11-22",
         "ransomware": "unknown", "cwes": ["CWE-79"], "epss": 0.5, "epss_percentile": 0.9, "epss_date": "2026-11-12",
         "agreement": {"state": "authoritative", "channels": 2, "independent": 1},
         "sources": [{"id": "kev-cisa", "licence": "CC0-1.0", "content_sha256": "a" * 64}], "first_seen": "2026-11-01"}
    d.update(kw)
    return d


ITEMS = [item("CVE-2024-0002"), item("CVE-2024-0001", vendor="Other Vendor"), item("CVE-2023-12345", ransomware="known")]
_n = [0]


def publish(seq=1, items=None, generated=T0 - 3600, valid_days=3, prev=None, key=K1, mutate=None, items_bytes=None, topic="vulns"):
    """Build, sign and serve a feed. -> (manifest dict, manifest bytes)."""
    items = ITEMS if items is None else items
    ib = items_bytes if items_bytes is not None else c.items_to_ndjson(items)
    snap = c.snap_id(seq, generated)
    path = f"v1/snapshots/{snap}/items.ndjson"
    m = {"topic": topic, "schema_version": 1, "seq": seq, "prev_digest": prev, "generated_at": c.iso(generated),
         "valid_until": c.iso_plus_days(generated, valid_days), "item_count": len(items), "untrusted_text": False,
         "ai_generated": False, "compiled_by": "statefeed/1 (code, no AI)",
         "licence": {"compilation": "CC-BY-4.0", "records": "see sources[].licence"}, "check_set_version": "abc123def456",
         "sources": [{"id": "kev-cisa", "url": "https://example.org/kev.json", "retrieved_at": c.iso(generated - 600),
                      "content_sha256": "b" * 64, "bytes": 1234, "status": "ok"}],
         "files": [{"path": path, "sha256": c.sha256_bytes(ib), "bytes": len(ib)}], "snapshot": snap,
         "publish_record": {"approval": "human"}}
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
    FEED.clear()
    HITS.clear()
    REDIRECT.clear()
    FEED.update({"/v1/latest/manifest.json": mb, "/v1/latest/manifest.json.sig": sig, "/" + path: ib,
                 f"/v1/snapshots/{snap}/manifest.json": mb})
    return m, mb


def state_file():
    _n[0] += 1
    return os.path.join(TMP, f"state{_n[0]}.json")


def run(state=None, **kw):
    return v.verify_feed(kw.pop("base", BASE), kw.pop("allowed", ALLOWED), kw.pop("principal", PR), state, **kw)


def read_state(p):
    return c.read_json(p)


# ------------------------------------------------------------------ 1. the ok path
m, mb = publish(1)
st = state_file()
r = run(st)
check("a good feed verifies: state ok, items returned in order", r["state"] == "ok" and r["reason"] == "ok" and r["seq"] == 1
      and [i["id"] for i in r["items"]] == ["CVE-2023-12345", "CVE-2024-0001", "CVE-2024-0002"] and r["item_count"] == 3, str(r)[:300])
check("the result carries snapshot, times, topic and the manifest digest",
      r["snapshot"] == "2026-11-13-1" and r["topic"] == "vulns" and r["manifest_sha256"] == c.sha256_bytes(mb)
      and r["generated_at"] == c.iso(T0 - 3600) and r["valid_until"] == c.iso_plus_days(T0 - 3600, 3))
s = read_state(st)
check("an accepted feed writes the state file (seq, digest, snapshot), mode 0600",
      s and s["seq"] == 1 and s["digest"] == c.sha256_bytes(mb) and s["snapshot"] == "2026-11-13-1"
      and (os.stat(st).st_mode & 0o777) == 0o600)
r2 = run(st)
check("the same publish verified again is fine (equal seq, same manifest)", r2["state"] == "ok" and r2["seq"] == 1)
check("verify_feed works without a state file", run()["state"] == "ok")
check("verify_feed has the documented signature",
      list(inspect.signature(v.verify_feed).parameters) == ["base", "allowed_signers", "principal", "state_path", "max_age_days"]
      and inspect.signature(v.verify_feed).parameters["max_age_days"].default == 3)
check("a trailing slash on the base URL is fine", run(base=BASE + "/")["state"] == "ok")

# ------------------------------------------------------------------ 2. signature and identity
m, mb = publish(1)
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
m, mb = publish(1, mutate=lambda m: m.update(item_count=-1))
r = run()
check("a signed manifest that fails the schema is invalid (manifest_schema)", r["state"] == "invalid" and r["reason"] == "manifest_schema")
publish(1, mutate=lambda m: m.pop("files"))
check("a signed manifest with a missing field is invalid", run()["reason"] == "manifest_schema")
m, mb = publish(1)
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

# ------------------------------------------------------------------ 3. files and items
m, mb = publish(1)
path = "/" + m["files"][0]["path"]
bad = FEED[path].replace(b"Example Vendor", b"Examp1e Vendor")
FEED[path] = bad
r = run()
check("tampered items of the same size are invalid (file_hash_mismatch), no items", r["state"] == "invalid"
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
good = c.items_to_ndjson(ITEMS)
publish(1)
calls = {"n": 0}
orig = Handler.do_GET


def flaky(self):
    if self.path.endswith("/items.ndjson"):
        calls["n"] += 1
        if calls["n"] == 1:
            FEED[self.path], keep = b"garbage", FEED[self.path]
            try:
                return orig(self)
            finally:
                FEED[self.path] = keep
    return orig(self)


Handler.do_GET = flaky
r = run()
Handler.do_GET = orig
check("one bad download followed by a good one is accepted", r["state"] == "ok" and calls["n"] == 2, str(r)[:200])

bad_items = [item("CVE-2024-0001"), item("CVE-2024-0002", vendor="<script>alert(1)</script>")]
publish(1, items=bad_items)
r = run()
check("an item that fails validation makes the whole feed invalid (item_invalid), no partial accept",
      r["state"] == "invalid" and r["reason"] == "item_invalid" and "items" not in r and "vendor" in r["detail"], str(r)[:300])
unsorted = b"".join(c.canonical_json(i) for i in [item("CVE-2024-0002"), item("CVE-2024-0001")])
publish(1, items=ITEMS[:2], items_bytes=unsorted)
check("items that are not sorted by id are invalid", run()["reason"] == "item_invalid")
publish(1, items_bytes=c.items_to_ndjson(ITEMS) + b'{"id":"CVE-2024-9999"}\n')
check("an extra line in a hash-correct file with a stale count is invalid", run()["state"] == "invalid")
publish(1, mutate=lambda m: m.update(item_count=2))
r = run()
check("item_count that disagrees with the file is invalid (item_count_mismatch)", r["reason"] == "item_count_mismatch", str(r)[:200])
publish(1, mutate=lambda m: m["files"][0].update(bytes=30 * 1024 * 1024))
r = run()
check("a file declared larger than the 25 MiB ceiling is invalid before any download",
      r["reason"] == "file_too_large" and not [p for p in HITS if p.endswith("items.ndjson")], str(r)[:200])
publish(1, items=[], items_bytes=b"")
r = run()
check("an empty feed (0 items) that is signed and consistent verifies", r["state"] == "ok" and r["items"] == [], str(r)[:200])

# ------------------------------------------------------------------ 4. seq, chain, clock
m1, mb1 = publish(1)
st = state_file()
check("seed state with seq 1", run(st)["state"] == "ok")
m2, mb2 = publish(2, prev=c.sha256_bytes(mb1))
r = run(st)
check("seq 2 chained to seq 1 is accepted and the state moves", r["state"] == "ok" and r["seq"] == 2 and read_state(st)["seq"] == 2)
publish(1)
r = run(st)
check("a lower seq than the state is invalid (seq_rollback)", r["state"] == "invalid" and r["reason"] == "seq_rollback"
      and read_state(st)["seq"] == 2, str(r)[:200])
publish(2, prev=c.sha256_bytes(mb1), generated=T0 - 1800)
r = run(st)
check("the same seq with different content is invalid (seq_conflict)", r["state"] == "invalid" and r["reason"] == "seq_conflict")
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
check("valid_until in the past is stale (valid_until_passed), items still returned, state updated",
      r["state"] == "stale" and r["reason"] == "valid_until_passed" and len(r["items"]) == 3 and read_state(st)["seq"] == 1, str(r)[:200])
publish(1, generated=T0 - 4 * 86400, valid_days=10)
r = run()
check("older than max_age_days is stale even before valid_until (max_age_exceeded)", r["state"] == "stale" and r["reason"] == "max_age_exceeded")
check("max_age_days is a parameter", run(max_age_days=5)["state"] == "ok" and run(max_age_days=None)["state"] == "ok"
      and run(max_age_days=2)["state"] == "stale")
check("a bad max_age_days is a setup error", run(max_age_days=0)["reason"] == "setup_error" and run(max_age_days="3")["reason"] == "setup_error")
publish(1, generated=T0 - 86400, valid_days=3)
check("a fresh manifest is ok", run()["state"] == "ok")
publish(1, generated=T0 - 5 * 86400, valid_days=3, items_bytes=c.items_to_ndjson(ITEMS)[:-5] + b"zzzzz")
check("stale never hides a broken file: invalid wins over stale", run()["state"] == "invalid")

# ------------------------------------------------------------------ 6. availability, redirects, size
publish(1)
dead = serve()
dead_base = f"http://127.0.0.1:{dead.server_address[1]}"
dead.shutdown()
dead.server_close()
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
check("a manifest over the 1 MiB cap is not read", run()["state"] == "unavailable")
publish(1)
REDIRECT["/v1/latest/manifest.json"] = f"http://localhost:{SRV.server_address[1]}/v1/latest/manifest.json"
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
r = run()
check("the result reports what the signed manifest declares about AI text and free text",
      r["state"] == "ok" and r["ai_generated"] is False and r["untrusted_text"] is False)
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

# ------------------------------------------------------------------ 9. the CLI
cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statefeed", "verify.py")
env = dict(os.environ)


def cli_run(*args, base=None):
    p = subprocess.run([sys.executable, "-I", cli, "fetch", "--base", base or BASE, "--allowed-signers", ALLOWED, "--principal", PR, *args],
                       capture_output=True, text=True, env=env, timeout=120)
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
publish(1)
code, out, err = cli_run("--max-age-days", "2.5")
check("CLI: --max-age-days takes a fraction", code == 0)
check("CLI output is plain ASCII JSON (nothing from the feed can reach a terminal raw)",
      out.isascii() and "\x1b" not in out)

# ------------------------------------------------------------------ 10. hygiene
src = open(os.path.join(os.path.dirname(cli), "verify.py")).read()
check("verify.py uses only the standard library and shells out to nothing itself",
      "subprocess" not in src and "shell=True" not in src and "import requests" not in src)
check("no secret or hostname leaks into the module", "http://192." not in src and "token" not in src.lower().replace("hostname", ""))

SRV.shutdown()
print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("all statefeed verify checks passed")
