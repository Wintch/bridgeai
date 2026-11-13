#!/usr/bin/env python3
"""Offline test of statefeed/publish.py: the approval binding (--sha), flags, every re-validation, secret-file permissions,
signing, the deploy tree (layout, file-type allowlist, limits, retention, contact rendering), dry-run, a failing or silent
fake deploy, the served-bytes check against a local server, and the published-state chain over several publishes. Candidates are
written directly (build.py is not used). The deploy command is a fake that copies the tree into a served directory; docker is
never run. No network: local http.server on 127.0.0.1, a throwaway ssh-keygen key in a temp dir.
Stdlib only: python3 -I ops/statefeed_publish_selftest.py"""
import calendar, contextlib, fcntl, http.server, io, json, os, shutil, subprocess, sys, tempfile, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from statefeed import common as c
from statefeed import publish as p

os.environ["no_proxy"] = "*"
for k in list(os.environ):
    if k.startswith("STATEFEED_"):
        del os.environ[k]
TMP = tempfile.mkdtemp(prefix="sf-publish-")
HOME, CONF, TOPICS, SERVED, SITESRC = (os.path.join(TMP, n) for n in ("home", "conf", "topics", "served", "sitesrc"))
NOW = calendar.timegm((2026, 11, 13, 10, 0, 0))
TOKEN = "cf-tok-9d41c7aa5e3b2f10-secret"
ACCOUNT = "acct-77aa66bb55cc44dd"
os.environ.update({"STATEFEED_HOME": HOME, "STATEFEED_CONF": CONF, "STATEFEED_TOPICS_DIR": TOPICS, "STATEFEED_FAKE_NOW": str(NOW),
                   "STATEFEED_SITE_SRC": SITESRC, "STATEFEED_SERVED_RETRIES": "3", "STATEFEED_SERVED_DELAY": "0.05",
                   "OPS_ENV": os.path.join(TMP, "no-ops.env"), "OPS_BOT_TOKEN": "", "OPS_CHAT_ID": ""})
fails = []
SENT = []
c.set_notifier(lambda text: SENT.append(text) or True)
ALL_OUT = []


def check(name, ok, detail=""):
    if ok:
        print(f"ok {name}")
    else:
        fails.append(name)
        print(f"FAIL {name} {detail}")


def run(*argv):
    """In-process CLI call -> (exit code, stdout, stderr)."""
    out, er = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(er):
        try:
            rc = p.main(list(argv))
        except SystemExit as e:
            rc = e.code
    ALL_OUT.extend([out.getvalue(), er.getvalue()])
    return rc, out.getvalue(), er.getvalue()


# ------------------------------------------------------------------ setup: topic, static files, secrets, served directory
os.makedirs(TOPICS)
topic = json.load(open(os.path.join(c.TOPICS_DIR, "vulns.json")))
topic["caps"] = {"max_removed": 2, "max_new": 5, "max_items_bytes": 20000}
topic["retention_snapshots"] = 3
open(os.path.join(TOPICS, "vulns.json"), "w").write(json.dumps(topic))
TOPIC = c.load_topic("vulns")
os.makedirs(SITESRC)
for name, text in (("index.html", "<!doctype html><title>t</title><p>Contact: {contact}</p>\n"),
                   ("NOTICE.txt", "Notice\nCorrections: {contact}\n"), ("LICENSE.txt", "licence\n"), ("robots.txt", "User-agent: *\n"),
                   ("_headers", "/*\n  X-Content-Type-Options: nosniff\n")):
    open(os.path.join(SITESRC, name), "w").write(text)

HAVE_SIGN = c.have_ssh_sign()
if not HAVE_SIGN:
    print("SKIP statefeed publish checks: ssh-keygen lacks -Y sign")
    shutil.rmtree(TMP, ignore_errors=True)
    print("all statefeed publish checks passed (skipped)")
    sys.exit(0)

KEY = os.path.join(CONF, "signing_key")
PUB = c.generate_signing_key(KEY, "statefeed-test")
PRINCIPAL = "statefeed-vulns"
ENVF = os.path.join(CONF, "cloudflare.env")
c.write_private(ENVF, f"CLOUDFLARE_ACCOUNT_ID={ACCOUNT}\nCLOUDFLARE_API_TOKEN={TOKEN}\n")


class Served(http.server.SimpleHTTPRequestHandler):
    miss = 0                                   # answer 404 to this many requests first (a CDN that is not up to date yet)
    hits = 0

    def __init__(self, *a, **k):
        super().__init__(*a, directory=SERVED, **k)

    def do_GET(self):
        Served.hits += 1
        if Served.miss > 0:
            Served.miss -= 1
            return self.send_error(404)
        return super().do_GET()

    def log_message(self, *a):
        pass


os.makedirs(SERVED)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Served)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"


def settings(contact="Fix <me> & co: ops@example.invalid"):
    d = {"project": "testproj", "base_urls": [BASE], "principal": PRINCIPAL}
    if contact is not None:
        d["contact"] = contact
    open(os.path.join(CONF, "vulns.json"), "w").write(json.dumps(d))


settings()
FAKE = r"""
import os, shutil, sys
site, served, mode, token = sys.argv[1:5]
if mode == "fail":
    print("wrangler said no, token " + token + " rejected"); sys.exit(3)
if mode != "nocopy":
    for n in os.listdir(served):
        q = os.path.join(served, n); shutil.rmtree(q) if os.path.isdir(q) else os.unlink(q)
    shutil.copytree(site, served, dirs_exist_ok=True)
if mode == "noitems":
    for dp, _, fns in os.walk(os.path.join(served, "v1", "snapshots")):
        for fn in fns:
            if fn == "items.ndjson":
                os.unlink(os.path.join(dp, fn))
if mode == "mismatch":
    open(os.path.join(served, "v1", "latest", "manifest.json"), "ab").write(b" ")
if mode != "silent":
    print("Deployment complete! Take a peek over at https://abc123.testproj.pages.dev")
"""


def deploy_mode(mode):
    os.environ["STATEFEED_DEPLOY_CMD"] = json.dumps(["python3", "-I", "-c", FAKE, "{site}", SERVED, mode, TOKEN])


# ------------------------------------------------------------------ candidate factory (no build.py)
_n = [0]
SRC = {s["id"]: c.sha256_bytes(s["id"].encode()) for s in TOPIC["sources"]}


def item(cve, vendor="Acme", state="authoritative", **over):
    ch = 2 if state != "single_channel" else 1
    it = {"id": cve, "schema_version": 1, "type": "kev", "vendor": vendor, "product": "Widget Server", "name": "Widget RCE",
          "date_added": "2026-11-01", "due_date": "2026-11-22", "ransomware": "unknown", "cwes": ["CWE-78"], "epss": 0.5,
          "epss_percentile": 0.9, "epss_date": "2026-11-12", "agreement": {"state": state, "channels": ch, "independent": 1},
          "sources": [{"id": "kev-cisa", "licence": "CC0-1.0", "content_sha256": SRC["kev-cisa"]}], "first_seen": "2026-11-13"}
    it.update(over)
    return it


def items_n(n, vendor="Acme"):
    return [item(f"CVE-2026-{1000 + i}", vendor) for i in range(n)]


def published_manifest_bytes():
    f = os.path.join(c.published_dir("vulns"), "manifest.json")
    return open(f, "rb").read() if os.path.exists(f) else None


def make_cand(seq, items, prev="auto", flags=(), unavailable=(), ts=NOW, raw_items=None, mutate=None, diff=None):
    _n[0] += 1
    cid = f"20261113T{100000 + _n[0]:06d}Z"
    d = os.path.join(c.candidates_dir("vulns"), cid)
    os.makedirs(d)
    ib = raw_items if raw_items is not None else c.items_to_ndjson(items)
    pm = published_manifest_bytes() if prev == "auto" else prev
    snap = c.snap_id(seq, ts)
    srcs = []
    for s in TOPIC["sources"]:
        if s["id"] in unavailable:
            srcs.append({"id": s["id"], "url": s["url"], "retrieved_at": None, "content_sha256": None, "bytes": 0, "status": "unavailable"})
        else:
            srcs.append({"id": s["id"], "url": s["url"], "retrieved_at": c.iso(ts), "content_sha256": SRC[s["id"]], "bytes": 1234, "status": "ok"})
    m = {"topic": "vulns", "schema_version": 1, "seq": seq, "prev_digest": c.sha256_bytes(pm) if pm else None,
         "generated_at": c.iso(ts), "valid_until": c.iso_plus_days(ts, 3), "item_count": len(items), "untrusted_text": False,
         "ai_generated": False, "compiled_by": "statefeed/1 (code, no AI)",
         "licence": {"compilation": "CC-BY-4.0", "records": "see sources[].licence"}, "check_set_version": "abc123def456",
         "sources": srcs, "files": [{"path": f"v1/snapshots/{snap}/items.ndjson", "sha256": c.sha256_bytes(ib), "bytes": len(ib)}],
         "snapshot": snap, "publish_record": {"approval": "human"}}
    if mutate:
        mutate(m)
    mb = c.canonical_json(m)
    open(os.path.join(d, "items.ndjson"), "wb").write(ib)
    open(os.path.join(d, "manifest.json"), "wb").write(mb)
    open(os.path.join(d, "diff.json"), "wb").write(c.canonical_json(
        diff or {"new": [], "removed": [], "updated": [], "disputed": [], "single_channel": [], "invalid": [], "counts": {},
                 "flags": list(flags)}))
    open(os.path.join(d, "report.txt"), "w").write("report\n")
    return {"cid": cid, "dir": d, "sha": c.sha256_bytes(mb)[:12], "mbytes": mb}


def approve(cand, *extra, sha=None):
    return run("approve", "vulns", cand["cid"], "--sha", sha or cand["sha"], *extra)


def state_snapshot():
    """What must not change when something is refused: published copy, site tree, served dir listing."""
    out = {}
    for root in (c.published_dir("vulns"), c.site_dir("vulns")):
        for dp, _, fns in os.walk(root):
            for fn in fns:
                f = os.path.join(dp, fn)
                out[f] = c.sha256_file(f)
    return out


def leftovers():
    return [n for n in os.listdir(c.topic_dir("vulns")) if n.startswith(".assemble-") or n.endswith(".new") or n.endswith(".old")]


def refused(name, cand, *extra, why="", sha=None, rc_want=1):
    before, n_sent = state_snapshot(), len(SENT)
    rc, out, er = approve(cand, *extra, sha=sha)
    check(name, rc == rc_want and why in er and state_snapshot() == before and len(SENT) == n_sent and not leftovers(),
          f"rc={rc} err={er!r}")


# ------------------------------------------------------------------ 1. refusals before anything is signed or deployed
deploy_mode("ok")
c1 = make_cand(1, items_n(3), flags=("first_publish",))
refused("a wrong --sha is refused", c1, "--accept-flags", why="--sha does not match", sha="0" * 12)
refused("a too-short --sha is refused", c1, "--accept-flags", why="--sha must be", sha="abc")
refused("the first publish needs --accept-flags (first_publish)", c1, why="first_publish")
c1b = make_cand(1, items_n(3))                     # build forgot every flag: this code derives first_publish itself
refused("a flag build did not raise is still derived (first_publish)", c1b, why="first_publish")

ct = make_cand(1, items_n(3), flags=("first_publish",))
open(os.path.join(ct["dir"], "items.ndjson"), "ab").write(b"\n")
refused("items changed after the build (hash mismatch) are refused", ct, "--accept-flags", why="does not match the manifest")
ct = make_cand(1, items_n(3))
mb = open(os.path.join(ct["dir"], "manifest.json"), "rb").read()
open(os.path.join(ct["dir"], "manifest.json"), "wb").write(mb.replace(b'"item_count":3', b'"item_count":2'))
refused("a manifest changed after the sha was read is refused (the approval binds to bytes)", ct, "--accept-flags", why="--sha does not match")
ct = make_cand(1, items_n(3), mutate=lambda m: m.update(item_count=2))
refused("item_count that disagrees with the items is refused", ct, "--accept-flags", why="item_count")
ct = make_cand(2, items_n(3), flags=("first_publish",))
refused("a seq gap is refused", ct, "--accept-flags", why="does not follow the published seq")
ct = make_cand(1, items_n(3), prev=b"some other manifest")
refused("a wrong prev_digest is refused", ct, "--accept-flags", why="prev_digest")
ct = make_cand(1, [], raw_items=c.canonical_json(item("CVE-2026-1001", vendor="Bad http://x.invalid")), mutate=lambda m: m.update(item_count=1))
refused("an item with a URL in a label is refused although the hashes are fine", ct, "--accept-flags", why="items.ndjson is invalid")
def extra_file(m):
    m["files"].append({"path": f"v1/snapshots/{m['snapshot']}/report.txt", "sha256": c.sha256_bytes(b"report\n"), "bytes": 7})


ct = make_cand(1, items_n(3), mutate=extra_file)
refused("a manifest that lists any file besides items.ndjson is refused", ct, "--accept-flags", why="exactly one file")
ct = make_cand(1, items_n(3), mutate=lambda m: m.update(topic="other"))
refused("a manifest for another topic is refused", ct, "--accept-flags", why="not vulns")
ct = make_cand(1, items_n(3), ts=NOW - 5 * 86400)
refused("an expired candidate is refused", ct, "--accept-flags", why="valid_until")
ct = make_cand(1, items_n(3), ts=NOW + 3600)
refused("a manifest generated in the future is refused", ct, "--accept-flags", why="future")
ct = make_cand(1, items_n(80))
refused("items over max_items_bytes are refused", ct, "--accept-flags", why="cap")


def other_url(m):
    m["sources"][0]["url"] = "https://evil.example.invalid/kev.json"


ct = make_cand(1, items_n(3), mutate=other_url)
refused("a source url that differs from the committed topic config is refused", ct, "--accept-flags", why="url differs")
gh = [{"id": "kev-github", "licence": "CC0-1.0", "content_sha256": SRC["kev-github"]}]
ct = make_cand(1, [item(f"CVE-2026-{1000 + i}", sources=gh) for i in range(3)], unavailable=("kev-cisa",))
refused("the primary source unavailable is never publishable", ct, "--accept-flags", why="primary source")
ct = make_cand(1, items_n(3), unavailable=("kev-github",))
refused("an unavailable secondary source is a derived flag", ct, why="source_unavailable:kev-github")
it = item("CVE-2026-5000", state="disputed")
ct = make_cand(1, [it])
refused("disputed items are a derived flag", ct, why="disputed_items")
it = item("CVE-2026-6000", sources=[{"id": "kev-cisa", "licence": "CC0-1.0", "content_sha256": "1" * 64}])
ct = make_cand(1, [it])
refused("an item whose source hash differs from the manifest is refused", ct, "--accept-flags", why="does not match the manifest's sources")

ct = make_cand(1, items_n(2))
open(os.path.join(ct["dir"], "run.sh"), "w").write("#!/bin/sh\n")
refused("a script file in the candidate is refused", ct, "--accept-flags", why="file type not allowed")
ct = make_cand(1, items_n(2))
open(os.path.join(ct["dir"], "extra.txt"), "w").write("x")
refused("an unlisted file in the candidate is refused", ct, "--accept-flags", why="not listed in the manifest")
ct = make_cand(1, items_n(2))
os.symlink("/etc/hostname", os.path.join(ct["dir"], "link.txt"))
refused("a symbolic link in the candidate is refused", ct, "--accept-flags", why="plain files")
ct = make_cand(1, items_n(2))
os.unlink(os.path.join(ct["dir"], "diff.json"))
refused("a candidate without diff.json is refused", ct, "--accept-flags", why="needs manifest.json and diff.json")
rc, out, er = run("approve", "vulns", "20250101T000000Z", "--sha", "0" * 12)
check("an unknown candidate is refused", rc == 1 and "no candidate" in er)
rc, out, er = run("approve", "../x", "20250101T000000Z", "--sha", "0" * 12)
check("a topic name that climbs out is refused", rc == 1 and "invalid topic" in er)

# ------------------------------------------------------------------ 2. secret files
good = make_cand(1, items_n(3), flags=("first_publish",))
os.chmod(KEY, 0o640)
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("a group-readable signing key is refused", rc == 2 and "signing_key" in er and "group" in er, er)
os.chmod(KEY, 0o600)
os.chmod(CONF, 0o777)
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("a config directory that others can write to is refused", rc == 2 and "config directory" in er, er)
os.chmod(CONF, 0o700)
os.chmod(ENVF, 0o644)
rc, out, er = approve(good, "--accept-flags")
check("a world-readable cloudflare.env is refused", rc == 2 and "cloudflare.env" in er and not os.path.exists(c.published_dir("vulns")), er)
os.chmod(ENVF, 0o600)
os.rename(KEY + ".pub", KEY + ".pub.bak")
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("a missing signing_key.pub is refused", rc == 2 and "signing_key.pub" in er)
os.rename(KEY + ".pub.bak", KEY + ".pub")
os.rename(os.path.join(CONF, "vulns.json"), os.path.join(CONF, "vulns.json.bak"))
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("missing local settings are refused with a clear message", rc == 2 and "vulns.json" in er, er)
os.rename(os.path.join(CONF, "vulns.json.bak"), os.path.join(CONF, "vulns.json"))
saved_cmd = os.environ.pop("STATEFEED_DEPLOY_CMD")
os.rename(ENVF, ENVF + ".bak")
rc, out, er = approve(good, "--accept-flags")
check("the real deploy path needs cloudflare.env (refused before anything runs)", rc == 2 and "cloudflare.env" in er, er)
os.rename(ENVF + ".bak", ENVF)
os.environ["STATEFEED_DEPLOY_CMD"] = saved_cmd
argv = p.default_deploy_argv(ENVF, "/tmp/tree-x/site", "testproj")
check("the default deploy command is the pinned wrangler in a read-only container, token only via --env-file",
      argv[:3] == ["docker", "run", "--rm"] and "--read-only" in argv and "/tmp/tree-x/site:/site:ro" in argv and "npx" in argv
      and p.WRANGLER in argv and "wrangler@4.156.0" in argv and argv[argv.index("--project-name") + 1] == "testproj"
      and "--env-file" in argv and ENVF in argv and TOKEN not in " ".join(argv))
try:
    p.default_deploy_argv(ENVF, "/tmp/a:b/site", "x")
    check("a docker mount path with a colon is refused", False)
except p.ConfigProblem:
    check("a docker mount path with a colon is refused", True)

# ------------------------------------------------------------------ 3. dry run: layout, allowlist, signature, no side effects
n_sent = len(SENT)
rc, out, er = approve(good, "--accept-flags", "--dry-run")
tree = os.path.join(c.topic_dir("vulns"), "dry-run-tree")
files = sorted(os.path.relpath(os.path.join(dp, f), tree).replace(os.sep, "/") for dp, _, fns in os.walk(tree) for f in fns)
want = sorted(["index.html", "NOTICE.txt", "LICENSE.txt", "robots.txt", "_headers", "v1/allowed_signers", "v1/latest/manifest.json",
               "v1/latest/manifest.json.sig", "v1/schema/item.1.json", "v1/schema/manifest.1.json", "v1/snapshots/2026-11-13-1/items.ndjson",
               "v1/snapshots/2026-11-13-1/manifest.json", "v1/snapshots/2026-11-13-1/manifest.json.sig"])
check("dry-run succeeds and reports the tree", rc == 0 and "nothing was deployed" in out and tree in out, f"{rc} {er}")
check("dry-run tree has exactly the documented layout", files == want, files)
check("dry-run changes no state and sends nothing", not os.path.exists(c.published_dir("vulns")) and not os.path.exists(c.site_dir("vulns"))
      and len(SENT) == n_sent and not [n for n in os.listdir(c.topic_dir("vulns")) if n.startswith(".assemble")])
sig = open(os.path.join(tree, "v1/latest/manifest.json.sig"), "rb").read()
check("the tree's latest manifest is the candidate's bytes and its signature verifies against the tree's allowed_signers",
      open(os.path.join(tree, "v1/latest/manifest.json"), "rb").read() == good["mbytes"]
      and c.ssh_verify(os.path.join(tree, "v1/allowed_signers"), PRINCIPAL, "statefeed", good["mbytes"], sig)
      and not c.ssh_verify(os.path.join(tree, "v1/allowed_signers"), PRINCIPAL, "statefeed", good["mbytes"] + b" ", sig)
      and not c.ssh_verify(os.path.join(tree, "v1/allowed_signers"), "someone-else", "statefeed", good["mbytes"], sig)
      and open(os.path.join(tree, "v1/snapshots/2026-11-13-1/manifest.json.sig"), "rb").read() == sig)
check("the allowed_signers copy holds one line for the principal and namespace",
      open(os.path.join(tree, "v1/allowed_signers")).read() == c.allowed_signers_line(PRINCIPAL, PUB) + "\n"
      and 'namespaces="statefeed"' in open(os.path.join(tree, "v1/allowed_signers")).read())
check("schema files are the installed ones",
      all(open(os.path.join(tree, "v1/schema", n), "rb").read() == open(os.path.join(c.SCHEMA_DIR, n), "rb").read()
          for n in ("item.1.json", "manifest.1.json")))
idx, notice = (open(os.path.join(tree, n), encoding="utf-8").read() for n in ("index.html", "NOTICE.txt"))
check("the contact is rendered into index.html (escaped) and NOTICE.txt (plain)",
      "Fix &lt;me&gt; &amp; co: ops@example.invalid" in idx and "Fix <me> & co: ops@example.invalid" in notice and "{contact}" not in idx + notice)
settings(contact=None)
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("without a contact the lines point at the project repository",
      rc == 0 and "see the project repository" in open(os.path.join(tree, "NOTICE.txt")).read()
      and "see the project repository" in open(os.path.join(tree, "index.html")).read())
settings()
bad_modes = [oct(os.stat(os.path.join(dp, n)).st_mode & 0o777) for dp, dns, fns in os.walk(tree) for n in dns + fns
             if (os.stat(os.path.join(dp, n)).st_mode & 0o022) or not os.access(os.path.join(dp, n), os.R_OK)]
check("the tree is readable by the deploy tool and not group- or world-writable", not bad_modes, bad_modes)

carried = item("CVE-2026-7000", sources=[{"id": "kev-cisa", "licence": "CC0-1.0", "content_sha256": SRC["kev-cisa"]},
                                         {"id": "epss", "licence": "attribution", "content_sha256": "2" * 64}])
ct = make_cand(1, [carried], unavailable=("epss",))
rc, out, er = approve(ct, "--dry-run")
check("EPSS down with last published scores carried over: a flag, not a refusal", rc == 1 and "source_unavailable:epss" in er, er)
rc, out, er = approve(ct, "--accept-flags", "--dry-run")
check("a carried-over EPSS source (hash of an older download) is publishable once the flag is accepted", rc == 0, er)
carried_bad = item("CVE-2026-7001", sources=[{"id": "kev-cisa", "licence": "CC0-1.0", "content_sha256": "3" * 64}])
ct = make_cand(1, [carried_bad], unavailable=("epss",))
rc, out, er = approve(ct, "--accept-flags", "--dry-run")
check("the carry-over allowance covers only the enrichment source, never KEV", rc == 1 and "does not match the manifest's sources" in er, er)

# ------------------------------------------------------------------ 4. the deploy tree guards
open(os.path.join(SITESRC, "evil.html"), "w").write("<p>x</p>")
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("a second html page in the static files is refused", rc == 1 and "not an allowed file" in er, er)
os.unlink(os.path.join(SITESRC, "evil.html"))
open(os.path.join(SITESRC, "tool.js"), "w").write("x")
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("a .js file in the static files is refused", rc == 1 and "not an allowed file" in er, er)
os.unlink(os.path.join(SITESRC, "tool.js"))
good_index = open(os.path.join(SITESRC, "index.html")).read()
open(os.path.join(SITESRC, "index.html"), "w").write("<p>{contact}</p><script>alert(1)</script>")
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("a script in index.html is refused", rc == 1 and "scripts" in er, er)
open(os.path.join(SITESRC, "index.html"), "w").write(good_index)
os.symlink("/etc/hostname", os.path.join(SITESRC, "link.txt"))
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("a symbolic link in the static files is refused", rc == 1 and "symbolic link" in er, er)
os.unlink(os.path.join(SITESRC, "link.txt"))
save = p.MAX_FILE_BYTES
p.MAX_FILE_BYTES = 100
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("a file at the hosting size limit is refused", rc == 1 and "hosting limit" in er, er)
p.MAX_FILE_BYTES = save
save = p.MAX_TREE_FILES
p.MAX_TREE_FILES = 5
rc, out, er = approve(good, "--accept-flags", "--dry-run")
check("a tree with too many files is refused", rc == 1 and "per deployment" in er, er)
p.MAX_TREE_FILES = save
check("tree_name_ok follows the allowlist",
      all(p.tree_name_ok(x) for x in ("index.html", "_headers", "v1/allowed_signers", "a/b.json", "x.ndjson", "x.sig", "NOTICE.txt"))
      and not any(p.tree_name_ok(x) for x in ("a.html", "v1/x.html", "run.sh", "x.js", "x.php", "x", ".htaccess", "x.json.bak")))

# ------------------------------------------------------------------ 5. real runs: failures leave the state alone, then success
before = state_snapshot()
deploy_mode("fail")
rc, out, er = approve(good, "--accept-flags")
combined = out + er
check("a failing deploy (exit 3) is refused, state unchanged, operator alerted",
      rc == 1 and "deploy failed" in er and "exit code 3" in er and state_snapshot() == before == {}
      and not os.path.exists(c.published_dir("vulns")) and not leftovers() and any("FAILED" in s for s in SENT))
check("the token never reaches the output, even if the tool prints it", TOKEN not in combined and "***" in combined, combined)
deploy_mode("silent")
rc, out, er = approve(good, "--accept-flags")
check("exit 0 without a reported deployment is not success", rc == 1 and "does not report a finished deployment" in er
      and not os.path.exists(c.published_dir("vulns")) and not leftovers(), er)
deploy_mode("mismatch")
n_sent = len(SENT)
rc, out, er = approve(good, "--accept-flags")
check("served bytes that differ from the signed manifest fail the publish, state unchanged",
      rc == 1 and "served-bytes check failed" in er and not os.path.exists(c.published_dir("vulns"))
      and not os.path.exists(c.site_dir("vulns")) and not leftovers() and any("served bytes do not match" in s for s in SENT[n_sent:]))
deploy_mode("noitems")
rc, out, er = approve(good, "--accept-flags")
check("a site that serves the manifest but not the snapshot's items fails the publish", rc == 1 and "served-bytes check failed" in er
      and "items.ndjson" in er and not os.path.exists(c.published_dir("vulns")) and not leftovers(), er)
deploy_mode("nocopy")
shutil.rmtree(SERVED)
os.makedirs(SERVED)
rc, out, er = approve(good, "--accept-flags")
check("a site that does not serve the manifest at all fails the publish", rc == 1 and "served-bytes check failed" in er
      and not os.path.exists(c.published_dir("vulns")), er)

deploy_mode("ok")
Served.miss, Served.hits = 2, 0
n_sent = len(SENT)
rc, out, er = approve(good, "--accept-flags")
check("success: exit 0, retries past a CDN that is not up to date yet", rc == 0 and "published seq 1" in out and Served.hits == 5, f"{rc} {er} hits={Served.hits}")
pub = c.published_dir("vulns")
check("success writes the published state (manifest, signature, items, seq)",
      open(os.path.join(pub, "manifest.json"), "rb").read() == good["mbytes"] and open(os.path.join(pub, "seq")).read().strip() == "1"
      and open(os.path.join(pub, "items.ndjson"), "rb").read() == c.items_to_ndjson(items_n(3))
      and open(os.path.join(pub, "manifest.json.sig"), "rb").read().startswith(b"-----BEGIN SSH SIGNATURE-----"))
check("success replaces the kept site tree and leaves no temp dirs",
      os.path.exists(os.path.join(c.site_dir("vulns"), "v1", "latest", "manifest.json")) and not leftovers())
check("one message, ids and counts only: no item text, no token",
      len(SENT) == n_sent + 1 and "published seq 1 (2026-11-13-1), 3 items" in SENT[-1] and "Acme" not in SENT[-1] and "Widget" not in SENT[-1])
check("served directory holds the signed manifest", open(os.path.join(SERVED, "v1/latest/manifest.json"), "rb").read() == good["mbytes"])
rc, out, er = approve(good, "--accept-flags")
check("the same candidate cannot be approved twice (seq moved on)", rc == 1 and "does not follow" in er)

# ------------------------------------------------------------------ 6. the chain: seq 2, derived caps, retention
c2 = make_cand(2, items_n(3) + [item("CVE-2026-2000")])
check("a normal next candidate needs no --accept-flags and chains prev_digest",
      json.loads(c2["mbytes"])["prev_digest"] == c.sha256_bytes(good["mbytes"]))
rc, out, er = approve(c2)
check("seq 2 publishes", rc == 0 and open(os.path.join(pub, "seq")).read().strip() == "2" and "published seq 2" in out, er)
c3 = make_cand(3, items_n(0) + [item("CVE-2026-3000")])
refused("removing more than max_removed is a derived flag even if diff.json shows none", c3, why="removed_over_cap")
c3 = make_cand(3, items_n(3) + [item(f"CVE-2026-{3000 + i}") for i in range(6)])
refused("adding more than max_new is a derived flag", c3, why="new_over_cap")
c3 = make_cand(3, items_n(3) + [item("CVE-2026-2000"), item("CVE-2026-3001")], flags=("refresh_only",))
refused("a flag from build (refresh_only) needs --accept-flags", c3, why="refresh_only")
rc, out, er = approve(c3, "--accept-flags")
check("--accept-flags accepts them", rc == 0 and open(os.path.join(pub, "seq")).read().strip() == "3", er)
c4 = make_cand(4, items_n(3) + [item("CVE-2026-2000"), item("CVE-2026-3001")])
rc, out, er = approve(c4)
snaps = sorted(os.listdir(os.path.join(c.site_dir("vulns"), "v1", "snapshots")))
check("retention keeps the newest 3 snapshots and the manifest list is intact",
      rc == 0 and snaps == ["2026-11-13-2", "2026-11-13-3", "2026-11-13-4"], f"{snaps} {er}")
check("the served directory carries the pruned set and the new manifest",
      sorted(os.listdir(os.path.join(SERVED, "v1", "snapshots"))) == snaps
      and open(os.path.join(SERVED, "v1/latest/manifest.json"), "rb").read() == c4["mbytes"])
c5 = make_cand(5, items_n(3) + [item("CVE-2026-2000"), item("CVE-2026-3001")])
rc, out, er = approve(c5, "--dry-run")
kept = sorted(os.listdir(os.path.join(tree, "v1", "snapshots")))
check("dry-run of seq 5 prunes to the newest 3 without touching the live tree",
      rc == 0 and kept == ["2026-11-13-3", "2026-11-13-4", "2026-11-13-5"]
      and sorted(os.listdir(os.path.join(c.site_dir("vulns"), "v1", "snapshots"))) == snaps, f"{kept} {er}")

# bad previous tree
bad = os.path.join(c.site_dir("vulns"), "v1", "snapshots", "2026-11-13-4", "evil.html")
open(bad, "w").write("x")
rc, out, er = approve(c5, "--dry-run")
check("a stray html file inside a kept snapshot is refused", rc == 1 and "file type not allowed" in er, er)
os.unlink(bad)
os.makedirs(os.path.join(c.site_dir("vulns"), "v1", "snapshots", "not-a-snapshot"))
rc, out, er = approve(c5, "--dry-run")
check("an unexpected entry in the previous snapshots is refused", rc == 1 and "unexpected entry" in er, er)
shutil.rmtree(os.path.join(c.site_dir("vulns"), "v1", "snapshots", "not-a-snapshot"))
rc, out, er = approve(c5, "--dry-run")
check("the previous tree is fine again", rc == 0, er)

# damaged published state is not guessed around
os.rename(os.path.join(pub, "seq"), os.path.join(pub, "seq.bak"))
rc, out, er = approve(c5)
check("a damaged published state is refused", rc == 1 and "published state is damaged" in er, er)
os.rename(os.path.join(pub, "seq.bak"), os.path.join(pub, "seq"))

# one publish at a time
lock = open(c.topic_dir("vulns", ".publish.lock"), "a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
rc, out, er = approve(c5, "--dry-run")
check("a publish that is already running blocks a second one", rc == 1 and "another publish" in er, er)
fcntl.flock(lock, fcntl.LOCK_UN)
lock.close()
rc, out, er = approve(c5, "--dry-run")
check("and it is free again afterwards", rc == 0, er)

# ------------------------------------------------------------------ 7. status
rc, out, er = run("status", "vulns")
lines = out.splitlines()
check("status shows the published seq and every candidate with sha and flags",
      rc == 0 and "vulns: published seq 4" in lines[0] and any(c5["cid"] in l and "seq 5" in l and c5["sha"] in l for l in lines)
      and any(c3["cid"] in l and "refresh_only" in l and "not the next seq" in l for l in lines), out)
rc, out2, er = run("status")
check("status without a topic walks the topics found", rc == 0 and "vulns: published seq 4" in out2)
rc, out3, er = run("status", "nothere")
check("status of an unknown topic is calm", rc == 0 and "no candidates" in out3)
rc, out, er = run("status", "Bad Topic")
check("status refuses a bad topic name", rc == 1)

# ------------------------------------------------------------------ 8. the script as the timer and the operator run it
env = {k: v for k, v in os.environ.items() if not k.startswith("STATEFEED_DEPLOY")}
env["HOME"] = TMP
r = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(p.__file__), "publish.py"), "status", "vulns"], env=env,
                   capture_output=True, text=True, timeout=60)
check("python3 -I publish.py status works as a script", r.returncode == 0 and "published seq 4" in r.stdout, r.stderr)
r = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(p.__file__), "publish.py"), "approve", "vulns", c5["cid"], "--sha",
                    "f" * 12], env=env, capture_output=True, text=True, timeout=60)
check("python3 -I publish.py approve with a wrong sha exits 1", r.returncode == 1 and "--sha does not match" in r.stderr, r.stderr)
r = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(p.__file__), "publish.py")], env=env, capture_output=True, text=True, timeout=60)
check("no subcommand is a usage error (exit 2)", r.returncode == 2)

# ------------------------------------------------------------------ 9. nothing leaks the token
blob = "\n".join(ALL_OUT + SENT)
for root in (c.topic_dir("vulns"), SERVED):
    for dp, _, fns in os.walk(root):
        for fn in fns:
            blob += open(os.path.join(dp, fn), errors="replace").read()
check("neither the token nor the account id appears in output, messages, state or the served tree", TOKEN not in blob and ACCOUNT not in blob)
check("the signing key never reaches the state or the served tree", "BEGIN OPENSSH PRIVATE KEY" not in blob)

shutil.rmtree(TMP, ignore_errors=True)
print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("all statefeed publish checks passed")
