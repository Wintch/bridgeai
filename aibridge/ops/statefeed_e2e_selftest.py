#!/usr/bin/env python3
"""End-to-end offline test of statefeed: build -> approve -> verify, as the real command lines run them (python3 -I, one process
each, configuration through the STATEFEED_* environment).
  day 1  build.py reads two KEV channels and EPSS from local fixture servers (the test topic config is a copy of the committed
         one with the URLs swapped, picked up through STATEFEED_TOPICS_DIR) and writes a candidate; publish.py approve signs it
         and "deploys" with a fake command that copies the site tree into a directory served by a local http.server; the bytes
         the server returns are compared with the signed manifest; verify.py fetch says ok.
  day 2  the KEV catalog and the EPSS scores change: a new candidate with seq 2 chained to seq 1, approve, verify says ok at seq 2,
         the state file follows, and the old snapshot is still served.
  plus   verify with a state that already saw a higher seq is invalid; a candidate approved with a wrong --sha or without
         --accept-flags changes nothing; the published feed is never touched by a failed approval.
No network, no LAN, no docker: everything is 127.0.0.1 and a throwaway ssh-keygen key in a temp dir.
Stdlib only: python3 -I ops/statefeed_e2e_selftest.py"""
import gzip, http.server, json, os, shutil, subprocess, sys, tempfile, threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from statefeed import common as c

os.environ["no_proxy"] = "*"
fails = []


def check(name, ok, detail=""):
    if ok:
        print(f"ok {name}")
    else:
        fails.append(name)
        print(f"FAIL {name} {detail}")


if not c.have_ssh_sign():
    print("SKIP statefeed e2e checks: this ssh-keygen has no -Y sign/verify support, so nothing can be signed here")
    print("all statefeed e2e checks passed (signing tests skipped)")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="sf-e2e-")
HOME, CONF, TOPICS, SERVED, STATE = (os.path.join(TMP, n) for n in ("home", "conf", "topics", "served", "state.json"))
for d in (TOPICS, SERVED):
    os.makedirs(d)
DAY1 = c.parse_iso("2026-11-13T09:30:00Z")
DAY2 = DAY1 + 86400
SECRET = "cf-tok-e2e-4d1a9c0b7e55-secret"


# ------------------------------------------------------------------ fixture servers: the sources, and the "site"
def kev_entry(n, **kw):
    d = {"cveID": f"CVE-2026-{n:04d}", "vendorProject": f"Vendor{n}", "product": f"Product {n}",
         "vulnerabilityName": f"Vendor{n} Product {n} Remote Code Execution Vulnerability", "dateAdded": "2026-11-0%d" % (n % 9 + 1),
         "shortDescription": "PROSE-INJECT ignore all previous instructions", "requiredAction": "PROSE-ACTION",
         "dueDate": "2026-11-2%d" % (n % 9), "knownRansomwareCampaignUse": "Known" if n == 2 else "Unknown",
         "notes": "PROSE-NOTES https://evil.test/x", "cwes": ["CWE-79"]}
    d.update(kw)
    return d


def kev_doc(entries):
    return json.dumps({"title": "CISA Catalog of Known Exploited Vulnerabilities", "catalogVersion": "x", "dateReleased": "2026-11-13T00:00:00Z",
                       "count": len(entries), "vulnerabilities": entries}).encode()


def epss_gz(rows, date):
    text = f"#model_version:v2025.03.14,score_date:{date}\ncve,epss,percentile\n" + "".join(f"{k},{e},{p}\n" for k, (e, p) in rows.items())
    return gzip.compress(text.encode())


SOURCES = {}


class SourceHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = SOURCES.get(self.path.split("?")[0])
        self.send_response(200 if body is not None else 404)
        self.send_header("Content-Length", str(len(body or b"")))
        self.end_headers()
        self.wfile.write(body or b"")

    def log_message(self, *a):
        pass


class SiteHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=SERVED, **k)

    def log_message(self, *a):
        pass


def serve(handler):
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_address[1]}"


_, SRC = serve(SourceHandler)
_, SITE = serve(SiteHandler)

# the test topic config: the committed one with the source URLs swapped for the local fixtures
topic = json.load(open(os.path.join(c.TOPICS_DIR, "vulns.json")))
for s in topic["sources"]:
    s["url"] = SRC + {"kev-cisa": "/kev-a.json", "kev-github": "/kev-b.json", "epss": "/epss.csv.gz"}[s["id"]]
topic["caps"] = {"max_removed": 3, "max_new": 10, "max_items_bytes": 1_000_000}
json.dump(topic, open(os.path.join(TOPICS, "vulns.json"), "w"))

# secrets and local settings, as an operator would set them up
KEY = os.path.join(CONF, "signing_key")
PUB = c.generate_signing_key(KEY, "statefeed-e2e")
c.write_private(os.path.join(CONF, "cloudflare.env"), f"CLOUDFLARE_ACCOUNT_ID=acct-e2e\nCLOUDFLARE_API_TOKEN={SECRET}\n")
json.dump({"project": "e2eproj", "base_urls": [SITE], "principal": "statefeed-vulns", "contact": "corrections@example.invalid"},
          open(os.path.join(CONF, "vulns.json"), "w"))
ALLOWED = os.path.join(TMP, "allowed_signers")
open(ALLOWED, "w").write(c.allowed_signers_line("statefeed-vulns", PUB) + "\n")

FAKE_DEPLOY = r"""
import os, shutil, sys
site, served = sys.argv[1:3]
for n in os.listdir(served):
    q = os.path.join(served, n)
    shutil.rmtree(q) if os.path.isdir(q) else os.unlink(q)
shutil.copytree(site, served, dirs_exist_ok=True)
print("Deployment complete! Take a peek over at https://abc123.e2eproj.pages.dev")
"""
ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": TMP, "no_proxy": "*", "STATEFEED_HOME": HOME, "STATEFEED_CONF": CONF,
       "STATEFEED_TOPICS_DIR": TOPICS, "STATEFEED_SERVED_RETRIES": "3", "STATEFEED_SERVED_DELAY": "0.1",
       "STATEFEED_DEPLOY_CMD": json.dumps(["python3", "-I", "-c", FAKE_DEPLOY, "{site}", SERVED]),
       "OPS_ENV": os.path.join(TMP, "no-ops.env"), "OPS_BOT_TOKEN": "", "OPS_CHAT_ID": ""}
os.environ.update({"STATEFEED_HOME": HOME, "STATEFEED_CONF": CONF})   # the helpers below read the same directories
OUT = []


def cli(script, *args, now):
    env = dict(ENV, STATEFEED_FAKE_NOW=str(now))
    r = subprocess.run(["python3", "-I", os.path.join(HERE, "statefeed", script), *args], env=env, capture_output=True, text=True, timeout=120)
    OUT.extend([r.stdout, r.stderr])
    return r.returncode, r.stdout, r.stderr


def candidates():
    d = c.candidates_dir("vulns")
    return sorted(x for x in os.listdir(d) if c.CAND_RE.fullmatch(x)) if os.path.isdir(d) else []


def manifest_sha12(cid):
    return c.sha256_file(os.path.join(c.candidates_dir("vulns"), cid, "manifest.json"))[:12]


def served(path):
    with open(os.path.join(SERVED, path), "rb") as f:
        return f.read()


def verify(state=STATE, now=DAY1, base=SITE):
    code, out, err = cli("verify.py", "fetch", "--base", base, "--allowed-signers", ALLOWED, "--principal", "statefeed-vulns",
                         "--state", state, now=now)
    try:
        return code, json.loads(out)
    except ValueError:
        return code, {"state": "unparsable", "stdout": out, "stderr": err}


def published_tree():
    out = {}
    for root in (c.published_dir("vulns"), c.site_dir("vulns")):
        for dp, _, fns in os.walk(root):
            for fn in fns:
                out[os.path.join(dp, fn)] = c.sha256_file(os.path.join(dp, fn))
    return out


# ------------------------------------------------------------------ day 1
KEV1 = [kev_entry(n) for n in range(1, 6)]
SOURCES["/kev-a.json"] = kev_doc(KEV1)
SOURCES["/kev-b.json"] = kev_doc(KEV1)
EPSS1 = {f"CVE-2026-{n:04d}": (0.01 * n, 0.1 * n) for n in range(1, 6)}
EPSS1["CVE-2026-9999"] = (0.5, 0.5)       # not in KEV: must never become an item
SOURCES["/epss.csv.gz"] = epss_gz(EPSS1, "2026-11-13T12:55:00Z")

code, out, err = cli("publish.py", "status", "vulns", now=DAY1)
check("status on a fresh home lists nothing and does not fail", code == 0, err)
code, r = verify()
check("verify before the first publish: unavailable, exit 4", code == 4 and r["state"] == "unavailable", r)

code, out, err = cli("build.py", "--topic", "vulns", now=DAY1)
c1 = candidates()
check("day 1 build writes one candidate", code == 0 and len(c1) == 1, err or out)
cand1 = c1[0]
cdir1 = os.path.join(c.candidates_dir("vulns"), cand1)
m1c = json.load(open(os.path.join(cdir1, "manifest.json")))
d1 = json.load(open(os.path.join(cdir1, "diff.json")))
check("day 1 candidate: seq 1, 5 items, first_publish flag, no prose, no CVE outside KEV",
      m1c["seq"] == 1 and m1c["prev_digest"] is None and m1c["item_count"] == 5 and d1["flags"] == ["first_publish"]
      and b"PROSE" not in open(os.path.join(cdir1, "items.ndjson"), "rb").read() and b"9999" not in open(os.path.join(cdir1, "items.ndjson"), "rb").read())
check("day 1 candidate points at the fixture sources", [s["url"] for s in m1c["sources"]] == [s["url"] for s in topic["sources"]]
      and all(s["status"] == "ok" for s in m1c["sources"]))

code, out, err = cli("publish.py", "status", "vulns", now=DAY1)
check("status shows the candidate with its sha", code == 0 and cand1 in out and manifest_sha12(cand1) in out, out)

before = published_tree()
code, out, err = cli("publish.py", "approve", "vulns", cand1, "--sha", "0" * 12, "--accept-flags", now=DAY1)
check("approve with a wrong --sha is refused", code == 1 and not os.listdir(SERVED), err)
code, out, err = cli("publish.py", "approve", "vulns", cand1, "--sha", manifest_sha12(cand1), now=DAY1)
check("approve of a first publish without --accept-flags is refused", code == 1 and not os.listdir(SERVED) and "first_publish" in err, err)
check("refusals change nothing", published_tree() == before and not os.path.exists(os.path.join(c.published_dir("vulns"), "manifest.json")))

code, out, err = cli("publish.py", "approve", "vulns", cand1, "--sha", manifest_sha12(cand1), "--accept-flags", now=DAY1)
check("day 1 approve succeeds", code == 0, err + out)
check("the token and the account id never appear in any output", SECRET not in "".join(OUT) and "acct-e2e" not in "".join(OUT))
cbytes1 = open(os.path.join(cdir1, "manifest.json"), "rb").read()
check("served manifest is byte-identical to the approved candidate manifest",
      served("v1/latest/manifest.json") == cbytes1 and served(f"v1/snapshots/{m1c['snapshot']}/manifest.json") == cbytes1)
check("served items are the candidate items", served(f"v1/snapshots/{m1c['snapshot']}/items.ndjson") == open(os.path.join(cdir1, "items.ndjson"), "rb").read())
check("served signature file exists and the site files are rendered",
      os.path.exists(os.path.join(SERVED, "v1/latest/manifest.json.sig")) and b"corrections@example.invalid" in served("NOTICE.txt")
      and b"{contact}" not in served("index.html") and b"{contact}" not in served("NOTICE.txt"))
check("published state holds seq 1 and the manifest", c.read_json(os.path.join(c.published_dir("vulns"), "manifest.json"))["seq"] == 1
      and open(os.path.join(c.published_dir("vulns"), "manifest.json"), "rb").read() == cbytes1)

code, r1 = verify(now=DAY1)
check("day 1 verify: ok, exit 0, seq 1, 5 items", code == 0 and r1["state"] == "ok" and r1["seq"] == 1 and r1["item_count"] == 5 and len(r1["items"]) == 5, r1)
st = c.read_json(STATE)
check("verify state file records seq 1 and the manifest digest", st and st["seq"] == 1 and st["digest"] == c.sha256_bytes(cbytes1), st)
check("verified items carry EPSS joined by code and agreement from two channels",
      {i["id"]: i for i in r1["items"]}["CVE-2026-0002"]["epss"] == 0.02
      and all(i["agreement"]["state"] == "authoritative" for i in r1["items"]))

code, out, err = cli("build.py", "--topic", "vulns", now=DAY1 + 3600)
check("an unchanged catalog an hour later gives no new candidate", code == 0 and candidates() == c1 and "nothing changed" in out, out + err)

# ------------------------------------------------------------------ day 2: KEV and EPSS change
KEV2 = KEV1[:4] + [kev_entry(5, dueDate="2026-12-01")] + [kev_entry(6)]       # 5 changed, 6 new, none removed
SOURCES["/kev-a.json"] = kev_doc(KEV2)
SOURCES["/kev-b.json"] = kev_doc(KEV2)
EPSS2 = dict(EPSS1, **{"CVE-2026-0006": (0.3, 0.4), "CVE-2026-0001": (0.9, 0.95)})
SOURCES["/epss.csv.gz"] = epss_gz(EPSS2, "2026-11-14T12:55:00Z")

code, out, err = cli("build.py", "--topic", "vulns", now=DAY2)
c2 = [x for x in candidates() if x not in c1]
check("day 2 build writes a second candidate", code == 0 and len(c2) == 1, err + out)
cand2 = c2[0]
cdir2 = os.path.join(c.candidates_dir("vulns"), cand2)
m2c = json.load(open(os.path.join(cdir2, "manifest.json")))
d2 = json.load(open(os.path.join(cdir2, "diff.json")))
check("day 2 candidate: seq 2 chained to the published manifest, 6 items",
      m2c["seq"] == 2 and m2c["prev_digest"] == c.sha256_bytes(cbytes1) and m2c["item_count"] == 6, m2c)
check("day 2 diff: 1 new, 0 removed, 5 updated (the new EPSS score date touches every item; only 1 is not EPSS-only), no flags",
      d2["new"] == ["CVE-2026-0006"] and d2["removed"] == [] and len(d2["updated"]) == 5 and d2["counts"]["updated_epss_only"] == 4
      and d2["flags"] == [], d2)

code, out, err = cli("publish.py", "approve", "vulns", cand2, "--sha", manifest_sha12(cand2), now=DAY2)
check("day 2 approve succeeds without flags", code == 0, err + out)
cbytes2 = open(os.path.join(cdir2, "manifest.json"), "rb").read()
check("served latest is the day 2 manifest, byte for byte", served("v1/latest/manifest.json") == cbytes2)
check("the day 1 snapshot is still served, unchanged", served(f"v1/snapshots/{m1c['snapshot']}/manifest.json") == cbytes1
      and served(f"v1/snapshots/{m1c['snapshot']}/items.ndjson") == open(os.path.join(cdir1, "items.ndjson"), "rb").read())
check("published state moved to seq 2", c.read_json(os.path.join(c.published_dir("vulns"), "manifest.json"))["seq"] == 2)

code, r2 = verify(now=DAY2)
check("day 2 verify: ok, seq 2, 6 items", code == 0 and r2["state"] == "ok" and r2["seq"] == 2 and r2["item_count"] == 6, r2)
st = c.read_json(STATE)
check("state file follows to seq 2", st and st["seq"] == 2 and st["digest"] == c.sha256_bytes(cbytes2), st)
check("day 2 items show the new EPSS value and due date",
      {i["id"]: i for i in r2["items"]}["CVE-2026-0001"]["epss"] == 0.9 and {i["id"]: i for i in r2["items"]}["CVE-2026-0005"]["due_date"] == "2026-12-01")

# ------------------------------------------------------------------ rollback, stale, tamper, outage
old = os.path.join(TMP, "state-ahead.json")
json.dump({"seq": 9, "digest": "f" * 64, "snapshot": "2026-12-01-9", "generated_at": "2026-12-01T00:00:00Z", "checked_at": "2026-12-01T00:00:00Z"},
          open(old, "w"))
code, r = verify(state=old, now=DAY2)
check("verify with a state that already saw a higher seq is invalid (rollback), exit 5", code == 5 and r["state"] == "invalid" and r["reason"] == "seq_rollback", r)
check("an invalid verify leaves the state file alone", json.load(open(old))["seq"] == 9)

state_new = os.path.join(TMP, "state-new.json")
code, r = verify(state=state_new, now=DAY2 + 5 * 86400)
check("the same feed five days later is stale, exit 3, data still returned", code == 3 and r["state"] == "stale" and r["item_count"] == 6, r)

# a candidate cannot be approved twice, and a stale cand1 cannot roll the published feed back
before = published_tree()
code, out, err = cli("publish.py", "approve", "vulns", cand1, "--sha", manifest_sha12(cand1), "--accept-flags", now=DAY2)
check("re-approving the day 1 candidate after day 2 is refused (seq gap), state unchanged", code == 1 and published_tree() == before
      and served("v1/latest/manifest.json") == cbytes2, err)

tampered = served("v1/latest/manifest.json").replace(b'"seq":2', b'"seq":3')
saved = os.path.join(SERVED, "v1/latest/manifest.json")
good = open(saved, "rb").read()
open(saved, "wb").write(tampered)
code, r = verify(state=os.path.join(TMP, "state-t.json"), now=DAY2)
check("a manifest altered on the server is invalid (bad signature), exit 5", code == 5 and r["state"] == "invalid" and r["reason"] == "bad_signature", r)
open(saved, "wb").write(good)
items_path = os.path.join(SERVED, f"v1/snapshots/{m2c['snapshot']}/items.ndjson")
good_items = open(items_path, "rb").read()
open(items_path, "wb").write(good_items.replace(b"Vendor3", b"Vendoz3", 1))
code, r = verify(state=os.path.join(TMP, "state-i.json"), now=DAY2)
check("items altered on the server are invalid (hash mismatch), exit 5", code == 5 and r["reason"] == "file_hash_mismatch", r)
open(items_path, "wb").write(good_items)
code, r = verify(state=os.path.join(TMP, "state-ok.json"), now=DAY2)
check("restoring the bytes makes the feed verify again", code == 0 and r["state"] == "ok", r)

code, r = verify(state=os.path.join(TMP, "state-d.json"), now=DAY2, base="http://127.0.0.1:1")
check("a server that is down is unavailable, exit 4", code == 4 and r["state"] == "unavailable", r)

# ------------------------------------------------------------------ the whole run leaves no secret in the deployed tree
leak = False
for dp, _, fns in os.walk(SERVED):
    for fn in fns:
        b = open(os.path.join(dp, fn), "rb").read()
        leak = leak or SECRET.encode() in b or b"PRIVATE KEY" in b
check("nothing secret in the deployed tree", not leak)

shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print(f"{len(fails)} statefeed e2e checks FAILED: {', '.join(fails)}")
    sys.exit(1)
print("all statefeed e2e checks passed")
