#!/usr/bin/env python3
"""statefeed publisher: the only part that holds the signing key and the hosting token.

  publish.py status [topic]
      Candidates written by build.py: seq, counts, flags, the sha12 that approve needs.
  publish.py approve <topic> <cand_id> --sha <sha12> [--accept-flags] [--dry-run]
      1. the approval binds to the exact bytes of the candidate's manifest.json (--sha is the start of its SHA-256);
      2. everything is re-validated here (build is not trusted): manifest schema, seq, prev_digest, listed files, hashes,
         every kev.csv row, the delta against the published rows, the mirror list against the local config, caps, file types,
         flags (a flag that build did not raise but this code derives counts too);
      3. the manifest is signed (ssh-keygen -Y sign, namespace statefeed), the signature is checked at once, and manifest.json
         plus the signature must stay within the 3,500 byte cap;
      4. the deploy tree is assembled in a temp dir: previous snapshots + the new one, schema, allowed_signers, static files;
         index.html gets a footer with the mirrors of the signed manifest and the signing key from the LOCAL config;
      5. deploy (STATEFEED_DEPLOY_CMD, a JSON argv list with {site} and {project}, or the pinned wrangler in a container);
         the exit code is checked and the output must report a finished deployment;
      6. served-bytes check: every base URL must serve exactly the signed manifest, the signature and kev.csv;
      7. only then the tree and the published state replace the old ones, and the operator gets one message.
      --dry-run stops after step 4 and keeps the tree in <home>/<topic>/dry-run-tree to inspect; nothing is deployed,
      published or sent.

Config (never in git): STATEFEED_CONF (default ~/.config/statefeed): cloudflare.env (CLOUDFLARE_ACCOUNT_ID,
CLOUDFLARE_API_TOKEN), signing_key (+ .pub, unencrypted ed25519), <topic>.json (project, base_urls, principal, contact, mirrors).
Both secret files must be mode 0600. State: STATEFEED_HOME (default ~/.local/state/statefeed).
Test hooks: STATEFEED_DEPLOY_CMD, STATEFEED_SERVED_RETRIES (default 6), STATEFEED_SERVED_DELAY (seconds, default 20),
STATEFEED_DEPLOY_TIMEOUT (seconds, default 900), STATEFEED_SITE_SRC (static files directory).
The token is never printed: deploy output is scrubbed of the secret values before it is shown.

Exit codes: 0 done, 1 refused or failed (published state unchanged), 2 usage or missing/unsafe local config.
Run as `python3 -I ops/statefeed/publish.py ...` (standard library only; ssh-keygen and docker are the external tools).
"""
import argparse, base64, fcntl, hashlib, html, json, os, re, shutil, subprocess, sys, tempfile, time, unicodedata, uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from statefeed import common as c

HERE = os.path.dirname(os.path.abspath(__file__))
MiB = 1 << 20
DEPLOY_IMAGE = "aibridge-hermes-agent:latest"
WRANGLER = "wrangler@4.156.0"
MAX_TREE_FILES = 20000           # Cloudflare Pages limit per deployment
MAX_FILE_BYTES = 25 * MiB        # Cloudflare Pages limit per file: a file of this size or more is refused
MAX_MANIFEST_BYTES = 1 * MiB
MAX_DIFF_BYTES = 4 * MiB
CAND_KEEP_NAMES = ("manifest.json", "diff.json", "report.txt")
CAND_SUFFIXES = (".json", ".csv", ".txt")
TREE_NAMES = ("index.html", "_headers", "allowed_signers")
TREE_SUFFIXES = (".txt", ".json", ".csv", ".md", ".sig")
FLAG_RE = re.compile(r"[a-z][a-z_]{0,40}(:[a-z0-9-]{1,40})?")
NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,63}")
DEPLOY_OK_RE = re.compile(r"deployment complete|deployment (is )?live|take a peek|\.pages\.dev", re.I)
PLACEHOLDERS = ("{contact}", "<contact>")
FOOTER_PLACEHOLDER = "{footer}"
NO_CONTACT = "see the project repository"
SHA_ARG_RE = re.compile(r"[0-9a-f]{12,64}")
SCHEMA_FILES = ("manifest.2.json", "kev.csv.md")


class Refuse(Exception):
    """The candidate or the setup is not acceptable; nothing was changed."""


class ConfigProblem(Exception):
    """Local config (key, token, settings) missing or unsafe."""


def say(msg):
    print(msg, flush=True)


def err(msg):
    print(msg, file=sys.stderr, flush=True)


def clean(s, n=300):
    """Printable, bounded text (labels from the network or a deploy tool never reach a terminal raw)."""
    return "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in str(s))[:n]


# ------------------------------------------------------------------ candidates

def list_candidates(topic):
    d = c.candidates_dir(topic)
    try:
        names = sorted(n for n in os.listdir(d) if c.CAND_RE.fullmatch(n))
    except OSError:
        return []
    return [n for n in names if os.path.isdir(os.path.join(d, n)) and not os.path.islink(os.path.join(d, n))]


def read_capped(path, cap):
    """Bytes of a regular, non-symlink file no larger than `cap`, else Refuse."""
    try:
        st = os.lstat(path)
    except OSError:
        raise Refuse(f"{os.path.basename(path)}: missing or unreadable")
    if not os.path.isfile(path) or os.path.islink(path):
        raise Refuse(f"{os.path.basename(path)}: not a regular file")
    if st.st_size > cap:
        raise Refuse(f"{os.path.basename(path)}: {st.st_size} bytes is over the {cap} byte cap")
    with open(path, "rb") as f:
        data = f.read(cap + 1)
    if len(data) > cap:
        raise Refuse(f"{os.path.basename(path)}: grew past the cap while reading")
    return data


def parse_diff(data):
    """-> diff dict; Refuse when it is not the shape build writes."""
    try:
        d = c.load_json_strict(data)
    except ValueError as e:
        raise Refuse(f"diff.json: not valid JSON ({e})")
    if not isinstance(d, dict):
        raise Refuse("diff.json: not an object")
    flags = d.get("flags")
    if not (isinstance(flags, list) and len(flags) <= 100 and all(isinstance(f, str) and FLAG_RE.fullmatch(f) for f in flags)):
        raise Refuse("diff.json: flags must be a list of short flag names")
    for k in ("new", "removed", "updated", "disputed", "single_channel"):
        v = d.get(k, [])
        if not (isinstance(v, list) and all(isinstance(i, str) and c.CVE_RE.fullmatch(i) for i in v)):
            raise Refuse(f"diff.json: {k} must be a list of CVE ids")
    return d


def load_candidate(topic, cid, tconf, sha):
    """Read a candidate fully into memory and validate its files. -> dict(manifest, mbytes, diff, rows, cbytes, files, dir).
    Everything later is taken from these bytes, never from the directory again. The approval (`sha`, step 1) is checked on the
    manifest bytes first, before anything else about the candidate is trusted or reported."""
    if not c.CAND_RE.fullmatch(cid or ""):
        raise Refuse("candidate id must look like YYYYMMDDTHHMMSSZ")
    d = os.path.join(c.candidates_dir(topic), cid)
    if not os.path.lexists(d):
        raise Refuse(f"no candidate {cid} for topic {topic}")
    if os.path.islink(d) or not os.path.isdir(d):
        raise Refuse("candidate path is not a plain directory")
    names = sorted(os.listdir(d))
    for n in names:
        p = os.path.join(d, n)
        if os.path.islink(p) or not os.path.isfile(p):
            raise Refuse(f"{n}: candidate holds only plain files (no links, no directories)")
        if not NAME_RE.fullmatch(n) or not n.endswith(CAND_SUFFIXES):
            raise Refuse(f"{n}: file type not allowed in a candidate (.json, .csv, .txt only)")
    if "manifest.json" not in names or "diff.json" not in names:
        raise Refuse("candidate needs manifest.json and diff.json")
    mbytes = read_capped(os.path.join(d, "manifest.json"), MAX_MANIFEST_BYTES)
    digest = c.sha256_bytes(mbytes)                                           # step 1
    if not digest.startswith(sha):
        raise Refuse(f"--sha does not match this candidate's manifest (it is {digest[:12]}); the approval binds to exact bytes")
    try:
        manifest = c.load_json_strict(mbytes)
    except ValueError as e:
        raise Refuse(f"manifest.json: not valid JSON ({e})")
    errs = c.validate_manifest(manifest)
    if errs:
        raise Refuse("manifest.json is invalid: " + "; ".join(errs[:5]) + (f" (+{len(errs) - 5} more)" if len(errs) > 5 else ""))
    if mbytes != c.canonical_json(manifest):
        raise Refuse("manifest.json is not in canonical form (statefeed.common.canonical_json)")
    diff = parse_diff(read_capped(os.path.join(d, "diff.json"), MAX_DIFF_BYTES))
    cap_bytes = tconf["caps"]["max_items_bytes"]
    listed, files = set(), {}
    for e in manifest["files"]:
        name = e["path"].rsplit("/", 1)[1]
        if name not in names or not NAME_RE.fullmatch(name) or not name.endswith(CAND_SUFFIXES):
            raise Refuse(f"{e['path']}: listed in the manifest but missing or not an allowed file type in the candidate")
        data = read_capped(os.path.join(d, name), max(cap_bytes, 1) if name == c.KEV_DATA_FILE else MAX_FILE_BYTES - 1)
        if len(data) != e["bytes"]:
            raise Refuse(f"{name}: size {len(data)} does not match the manifest ({e['bytes']})")
        if c.sha256_bytes(data) != e["sha256"]:
            raise Refuse(f"{name}: SHA-256 does not match the manifest (the file was changed after the build)")
        listed.add(name)
        files[name] = data
    for n in names:
        if n not in listed and n not in CAND_KEEP_NAMES:
            raise Refuse(f"{n}: not listed in the manifest")
    rows, rerrs = c.parse_kev_csv(files[c.KEV_DATA_FILE])
    if rerrs:
        raise Refuse(f"{c.KEV_DATA_FILE} is invalid: " + "; ".join(rerrs[:3]))
    if len(rows) != manifest["item_count"]:
        raise Refuse(f"item_count {manifest['item_count']} does not match the {len(rows)} rows of {c.KEV_DATA_FILE}")
    if any(r["epss"] for r in rows) and manifest["epss"] is None:
        raise Refuse("rows carry EPSS scores but the manifest has no epss block")
    return {"manifest": manifest, "mbytes": mbytes, "diff": diff, "rows": rows, "cbytes": files[c.KEV_DATA_FILE],
            "files": files, "dir": d}


def load_published(topic):
    """-> (seq, manifest_bytes, rows) of the last published snapshot, or (0, None, []) when nothing was published. A published
    state in the old items.ndjson format is refused, never read."""
    d = c.published_dir(topic)
    if not os.path.isdir(d):
        return 0, None, []
    if os.path.exists(os.path.join(d, "items.ndjson")) and not os.path.exists(os.path.join(d, c.KEV_DATA_FILE)):
        raise Refuse(f"published state is in the old items.ndjson format; remove {d} deliberately to start the new format")
    try:
        seq = int(read_capped(os.path.join(d, "seq"), 32).decode().strip())
        mbytes = read_capped(os.path.join(d, "manifest.json"), MAX_MANIFEST_BYTES)
        manifest = c.load_json_strict(mbytes)
        rows, errs = c.parse_kev_csv(read_capped(os.path.join(d, c.KEV_DATA_FILE), 200 * MiB))
    except (ValueError, UnicodeDecodeError, Refuse) as e:
        raise Refuse(f"published state is damaged ({clean(e, 100)}); fix or remove {d} deliberately")
    if errs or not isinstance(manifest, dict) or manifest.get("seq") != seq:
        raise Refuse(f"published state is inconsistent; fix or remove {d} deliberately")
    return seq, mbytes, rows


def delta_lists(old_rows, new_rows):
    """-> (added, removed, changed) CVE id lists in numeric CVE order: the KEV changes between two lists of rows (changed =
    kev_sha differs; EPSS and flags never count). Worked out here again, build's delta is not trusted."""
    old, new = {r["cve"]: r for r in old_rows}, {r["cve"]: r for r in new_rows}
    key = c.cve_sort_key
    return (sorted(set(new) - set(old), key=key), sorted(set(old) - set(new), key=key),
            sorted((i for i in new if i in old and new[i]["kev_sha"] != old[i]["kev_sha"]), key=key))


def delta_problem(manifest, pub_seq, pub_rows, rows):
    """None, or why the manifest's `delta` is not what the rows say. since_seq is the published seq (null on the first publish);
    explicit lists must equal the real lists; the full form must carry the real counts."""
    d = manifest["delta"]
    want_since = pub_seq or None
    if d["since_seq"] != want_since:
        return f"delta.since_seq is {d['since_seq']}, the published seq is {pub_seq}"
    added, removed, changed = delta_lists(pub_rows, rows)
    if d.get("full") is True:
        got = (d["counts"]["added"], d["counts"]["removed"], d["counts"]["changed"])
        if got != (len(added), len(removed), len(changed)):
            return "delta.counts do not match the real difference to the published rows"
        return None
    if pub_seq == 0:
        return "the first publish must carry the full form of delta"
    if (d["added"], d["removed"], d["changed"]) != (added, removed, changed):
        return "delta lists do not match the real difference to the published rows"
    return None


def derived_flags(cand, tconf, pub_seq, pub_rows):
    """Flags this code works out itself from the data (a build bug or a tampered diff.json cannot hide them)."""
    f, caps, m = set(cand["diff"]["flags"]), tconf["caps"], cand["manifest"]
    ids = {r["cve"] for r in cand["rows"]}
    if pub_seq == 0:
        f.add("first_publish")
    else:
        old = {r["cve"] for r in pub_rows}
        if len(old - ids) > caps["max_removed"]:
            f.add("removed_over_cap")
        if len(ids - old) > caps["max_new"]:
            f.add("new_over_cap")
    if any(r["flag"] == "disputed" for r in cand["rows"]):
        f.add("disputed_items")
    for s in m["sources"]:
        if s["status"] == "unavailable":
            f.add("source_unavailable:" + s["id"])
    return sorted(f)


def check_candidate(cand, topic, tconf, pub_seq, pub_mbytes, pub_rows):
    """Step 2: every check that does not depend on the secrets. Raises Refuse."""
    m = cand["manifest"]
    if m["topic"] != topic:
        raise Refuse(f"manifest is for topic {m['topic']}, not {topic}")
    if m["seq"] != pub_seq + 1:
        raise Refuse(f"seq {m['seq']} does not follow the published seq {pub_seq} (a candidate is built for exactly one successor)")
    want_prev = c.sha256_bytes(pub_mbytes) if pub_mbytes is not None else None
    if m["prev_digest"] != want_prev:
        raise Refuse("prev_digest does not match the published manifest")
    ts = c.now()
    if c.parse_iso(m["valid_until"]) <= ts:
        raise Refuse("valid_until has already passed; build a fresh candidate")
    if c.parse_iso(m["generated_at"]) > ts + 600:
        raise Refuse("generated_at is in the future")
    top = {s["id"]: s for s in tconf["sources"]}
    if {s["id"] for s in m["sources"]} != set(top):
        raise Refuse("manifest sources differ from the topic config")
    for s in m["sources"]:
        if s["url"] != top[s["id"]]["url"]:
            raise Refuse(f"source {s['id']}: url differs from the committed topic config")
        if top[s["id"]]["role"] == "primary" and s["status"] == "unavailable":
            raise Refuse(f"the primary source {s['id']} was unavailable; that candidate cannot be published")
        if top[s["id"]]["role"] == "enrich" and s["ref"] is not None and s["ref"] != m["epss"]:
            raise Refuse(f"source {s['id']}: its ref differs from the manifest's epss block")
    if len(cand["cbytes"]) > tconf["caps"]["max_items_bytes"]:
        raise Refuse(f"{c.KEV_DATA_FILE} is over the topic's max_items_bytes")
    why = delta_problem(m, pub_seq, pub_rows, cand["rows"])
    if why:
        raise Refuse(why)
    return derived_flags(cand, tconf, pub_seq, pub_rows)


# ------------------------------------------------------------------ secrets and signing

def load_secrets(topic, need_deploy_env):
    """-> (settings, key_path, pub_line, env). Missing or loose secret files raise ConfigProblem."""
    conf = c.statefeed_conf()
    try:
        settings = c.load_local_settings(topic, require=True)
    except c.ConfigError as e:
        raise ConfigProblem(str(e))
    key = os.path.join(conf, "signing_key")
    try:
        if os.stat(conf).st_mode & 0o022:
            raise ConfigProblem("the statefeed config directory is writable by group or others (chmod 700): its secret files could be swapped")
    except OSError:
        raise ConfigProblem("the statefeed config directory is missing or unreadable")
    for p in (key, os.path.join(conf, "cloudflare.env")):
        if os.path.exists(p) or p == key or need_deploy_env:
            why = c.private_perms_problem(p)
            if why:
                raise ConfigProblem(why)
    pubp = key + ".pub"
    try:
        with open(pubp) as f:
            pub = f.read().strip()
    except OSError:
        raise ConfigProblem("signing_key.pub is missing next to signing_key")
    env = c.load_env_file(os.path.join(conf, "cloudflare.env"))
    if need_deploy_env and not (env.get("CLOUDFLARE_API_TOKEN") and env.get("CLOUDFLARE_ACCOUNT_ID")):
        raise ConfigProblem("cloudflare.env must hold CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN")
    try:
        c.allowed_signers_line(settings["principal"], pub)
    except c.SignError as e:
        raise ConfigProblem(f"signing_key.pub: {e}")
    return settings, key, pub, env


def sign_manifest(key, mbytes, principal, pub):
    """Step 3. Signs a copy in a private temp dir and verifies the signature. -> signature bytes."""
    if not c.have_ssh_sign():
        raise ConfigProblem("ssh-keygen with -Y sign is not available")
    with tempfile.TemporaryDirectory(prefix="sf-sign-") as t:
        os.chmod(t, 0o700)
        mp = os.path.join(t, "manifest.json")
        c.write_private(mp, mbytes)
        try:
            sig = c.ssh_sign(key, mp)
            sigb = open(sig, "rb").read()
            asf = os.path.join(t, "allowed_signers")
            c.write_private(asf, c.allowed_signers_line(principal, pub) + "\n")
            if not c.ssh_verify(asf, principal, c.SIGN_NAMESPACE, mbytes, sigb):
                raise Refuse("the fresh signature does not verify against signing_key.pub (key and .pub do not match)")
        except c.SignError as e:
            raise Refuse(f"signing failed: {e}")
    why = c.feed_size_problem(mbytes, sigb)
    if why:
        raise Refuse(f"size: {why} (it has to fit one Telegram message)")
    return sigb


def key_fingerprint(pub_line):
    """The OpenSSH SHA256 fingerprint ("SHA256:<base64>") of a public key line, as `ssh-keygen -lf` prints it, worked out from the
    key itself (no subprocess)."""
    parts = (pub_line or "").split()
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (IndexError, ValueError):
        raise Refuse("signing_key.pub is not a public key line")
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")


# ------------------------------------------------------------------ the deploy tree

def footer_html(manifest, signers_line, fingerprint):
    """The index.html footer, built from two trusted places and nothing else: the mirrors of the SIGNED manifest, and the signing
    key from the operator's LOCAL config (never read from the manifest or from a mirror). Every value is escaped."""
    esc = html.escape
    out = ["<h2>Other places to get this feed</h2>"]
    mirrors = manifest.get("mirrors") or []
    if mirrors:
        out.append("<p>The signed manifest lists these places. The list is only as good as the signature on it: verify the "
                   "manifest first, then use whichever place you can reach. The files are identical everywhere.</p>\n<ul>")
        for m in mirrors:
            how = "machine readable" if m["machine_readable"] else "for people, who relay the files"
            addr = esc(m["address"])
            shown = f'<a href="{addr}">{addr}</a>' if m["kind"] != "telegram" else f"<code>{addr}</code> (Telegram)"
            out.append(f"<li><code>{esc(m['id'])}</code>: {shown}, {esc(m['kind'])}, {how}</li>")
        out.append("</ul>")
    else:
        out.append("<p>The signed manifest lists no other place.</p>")
    out.append("<h2>The signing key</h2>")
    out.append("<p>The line below is the public key this site's manifests are signed with, in the format of an "
               "<code>allowed_signers</code> file. Do not trust it because you read it here: a site you do not trust can "
               "show a different key. Compare the fingerprint with the one your own "
               "<code>ssh-keygen -lf</code> prints for the key you received out of band. If they differ, do not use this feed. "
               "Never take the key from a mirror.</p>")
    out.append(f"<pre>{esc(signers_line)}</pre>")
    out.append(f"<p>Fingerprint: <code>{esc(fingerprint)}</code></p>")
    return "\n".join(out) + "\n"


def render_static(name, data, contact, footer=""):
    """index.html and NOTICE.txt carry the correction contact; without one the line points at the repository. index.html also
    gets `footer` (at {footer}, else before </main>, </body> or at the end)."""
    if name not in ("index.html", "NOTICE.txt"):
        return data
    text = data.decode("utf-8")
    value = contact or NO_CONTACT
    value = html.escape(value) if name == "index.html" else value
    for ph in PLACEHOLDERS:
        text = text.replace(ph, value)
    if name == "index.html":
        if FOOTER_PLACEHOLDER in text:
            text = text.replace(FOOTER_PLACEHOLDER, footer)
        else:
            for tag in ("</main>", "</body>"):
                if tag in text:
                    text = text.replace(tag, footer + tag, 1)
                    break
            else:
                text += footer
    return text.encode("utf-8")


def static_dir():
    return os.environ.get("STATEFEED_SITE_SRC") or os.path.join(HERE, "site")


def tree_name_ok(rel):
    base = rel.rsplit("/", 1)[-1]
    if base.endswith(".html"):
        return rel == "index.html"
    return base in TREE_NAMES or base.endswith(TREE_SUFFIXES)


def check_tree(root):
    """The file-type allowlist and the limits for the whole tree. Raises Refuse. -> (files, bytes)."""
    n = total = 0
    for dp, dns, fns in os.walk(root, followlinks=False):
        for name in dns + fns:
            if os.path.islink(os.path.join(dp, name)):
                raise Refuse(f"deploy tree holds a symbolic link ({clean(name, 60)})")
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            if not tree_name_ok(rel):
                raise Refuse(f"file type not allowed in the deploy tree: {clean(rel, 120)}")
            size = os.path.getsize(p)
            if size >= MAX_FILE_BYTES:
                raise Refuse(f"{clean(rel, 120)}: {size} bytes, the hosting limit is {MAX_FILE_BYTES} per file")
            n += 1
            total += size
    if n >= MAX_TREE_FILES:
        raise Refuse(f"{n} files; the hosting limit is {MAX_TREE_FILES} per deployment")
    return n, total


def snap_seq(name):
    return int(name.rsplit("-", 1)[1])


def assemble_tree(topic, tconf, cand, sig, settings, pub, dest):
    """Step 4: build the tree in `dest` (a new directory). Only the previous snapshots are carried over; everything else is
    regenerated, so no stale static file survives. -> sorted list of snapshot names kept."""
    m = cand["manifest"]
    snap = m["snapshot"]
    v1 = os.path.join(dest, "v1")
    snaps = os.path.join(v1, "snapshots")
    os.makedirs(snaps)
    prev = os.path.join(c.site_dir(topic), "v1", "snapshots")
    if os.path.isdir(prev):
        for name in sorted(os.listdir(prev)):
            src = os.path.join(prev, name)
            if not c.SNAP_RE.fullmatch(name) or os.path.islink(src) or not os.path.isdir(src):
                raise Refuse(f"previous deploy tree: unexpected entry {clean(name, 60)} in v1/snapshots")
            if name != snap:
                shutil.copytree(src, os.path.join(snaps, name), symlinks=True)
    sd = os.path.join(snaps, snap)
    os.makedirs(sd)
    for name, data in cand["files"].items():
        c.write_file(os.path.join(sd, name), data)
    c.write_file(os.path.join(sd, "manifest.json"), cand["mbytes"])
    c.write_file(os.path.join(sd, "manifest.json.sig"), sig)
    latest = os.path.join(v1, "latest")
    os.makedirs(latest)
    c.write_file(os.path.join(latest, "manifest.json"), cand["mbytes"])
    c.write_file(os.path.join(latest, "manifest.json.sig"), sig)
    schema = os.path.join(v1, "schema")
    os.makedirs(schema)
    for name in SCHEMA_FILES:
        try:
            with open(os.path.join(c.SCHEMA_DIR, name), "rb") as f:
                c.write_file(os.path.join(schema, name), f.read())
        except OSError:
            raise Refuse(f"schema file {name} is missing from the installation")
    signers_line = c.allowed_signers_line(settings["principal"], pub)
    c.write_file(os.path.join(v1, "allowed_signers"), (signers_line + "\n").encode())
    footer = footer_html(m, signers_line, key_fingerprint(pub))
    src = static_dir()
    if not os.path.isdir(src):
        raise Refuse("the static site files directory is missing from the installation")
    count = 0
    for dp, dns, fns in os.walk(src, followlinks=False):
        dns[:] = [d for d in dns if not os.path.islink(os.path.join(dp, d))]
        for fn in fns:
            p = os.path.join(dp, fn)
            if os.path.islink(p):
                raise Refuse(f"static files: {clean(fn, 60)} is a symbolic link")
            rel = os.path.relpath(p, src).replace(os.sep, "/")
            if not tree_name_ok(rel) or rel.startswith("v1/"):
                raise Refuse(f"static files: {clean(rel, 80)} is not an allowed file")
            data = render_static(rel, read_capped(p, 1 * MiB), settings["contact"], footer)
            out = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            c.write_file(out, data)
            count += 1
    if not count:
        raise Refuse("static files: the directory is empty")
    idx = os.path.join(dest, "index.html")
    if os.path.exists(idx):
        low = open(idx, encoding="utf-8", errors="replace").read().lower()
        if re.search(r"<script|<iframe|javascript:|\son[a-z]+\s*=", low):
            raise Refuse("index.html must not carry scripts, frames or event handlers")
    # retention: the newest N snapshots stay (the new one is the newest by construction)
    names = sorted((n for n in os.listdir(snaps)), key=snap_seq)
    for old in names[:-tconf["retention_snapshots"]] if len(names) > tconf["retention_snapshots"] else []:
        shutil.rmtree(os.path.join(snaps, old))
    kept = sorted(os.listdir(snaps), key=snap_seq)
    for dp, dns, fns in os.walk(dest):
        os.chmod(dp, 0o755)
        for fn in fns:
            os.chmod(os.path.join(dp, fn), 0o644)
    check_tree(dest)
    return kept


# ------------------------------------------------------------------ deploy and served-bytes check

def default_deploy_argv(env_file, tree, project):
    for p in (tree, env_file):
        if ":" in p or "," in p or " " in p:
            raise ConfigProblem(f"path {p!r} cannot be used in a docker mount (no colon, comma or space)")
    return ["docker", "run", "--rm", "--env-file", env_file, "-v", f"{tree}:/site:ro", "--read-only", "--tmpfs", "/tmp",
            "--tmpfs", "/root", "-e", "HOME=/root", "-e", "WRANGLER_SEND_METRICS=false", "--entrypoint", "npx", DEPLOY_IMAGE,
            "--yes", WRANGLER, "pages", "deploy", "/site", "--project-name", project, "--branch", "main",
            "--commit-dirty=true"]


def deploy_argv(env_file, tree, project):
    raw = os.environ.get("STATEFEED_DEPLOY_CMD")
    if not raw:
        return default_deploy_argv(env_file, tree, project)
    try:
        argv = json.loads(raw)
    except ValueError:
        raise ConfigProblem("STATEFEED_DEPLOY_CMD must be a JSON list of strings")
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
        raise ConfigProblem("STATEFEED_DEPLOY_CMD must be a JSON list of strings")
    return [a.replace("{site}", tree).replace("{project}", project) for a in argv]


def scrub(text, secrets):
    for s in secrets:
        if s and len(s) >= 4:
            text = text.replace(s, "***")
    return text


def run_deploy(argv, secrets):
    """Step 5. -> (ok, short scrubbed output tail). The output must report a finished deployment, not only exit 0."""
    try:
        timeout = float(os.environ.get("STATEFEED_DEPLOY_TIMEOUT", "900"))
    except ValueError:
        timeout = 900.0
    try:
        r = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
                           start_new_session=True)
    except FileNotFoundError:
        return False, f"cannot run {clean(argv[0], 40)}: not found"
    except subprocess.TimeoutExpired:
        return False, "deploy timed out"
    except OSError as e:
        return False, f"cannot run the deploy command ({type(e).__name__})"
    out = scrub(r.stdout.decode("utf-8", "replace"), secrets)
    tail = clean(" | ".join(out.strip().splitlines()[-6:]), 600)
    if r.returncode != 0:
        return False, f"exit code {r.returncode}: {tail}"
    if not DEPLOY_OK_RE.search(out):
        return False, f"exit 0 but the output does not report a finished deployment: {tail}"
    return True, tail


def served_check(base_urls, mbytes, sigb, extra=()):
    """Step 6. Every base URL must serve the signed manifest and signature, byte for byte, and every (path, bytes) in `extra`
    (the snapshot's kev.csv), so a consumer never finds a manifest whose files are missing. -> (ok, reason)."""
    try:
        tries = max(1, int(os.environ.get("STATEFEED_SERVED_RETRIES", "6")))
        delay = max(0.0, float(os.environ.get("STATEFEED_SERVED_DELAY", "20")))
    except ValueError:
        tries, delay = 6, 20.0
    hdrs = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
    reason = "no base URL configured"
    for base in base_urls:
        for attempt in range(tries):
            if attempt:
                time.sleep(delay)
            bust = "?cb=" + uuid.uuid4().hex[:12]
            try:
                got, shown = [], ""
                for name, want in (("v1/latest/manifest.json", mbytes), ("v1/latest/manifest.json.sig", sigb), *extra):
                    shown = name.rsplit("/", 1)[-1]
                    r = c.http_get(f"{base}/{name}{bust}", max(len(want) + 1, 4096) * 2, headers=hdrs, timeout=30)
                    got.append((name.rsplit("/", 1)[-1], r.status == 200 and r.body == want))
                bad = [n for n, ok in got if not ok]
                if not bad:
                    reason = ""
                    break
                reason = f"{base}: served {', '.join(bad)} differs from the signed file"
            except c.HttpError as e:
                reason = f"{base}: {shown}: {clean(e, 100)}"
        if reason:
            return False, reason
    return True, ""


# ------------------------------------------------------------------ approve

def replace_dir(new, final):
    """Swap a directory in: the old one is renamed aside first, so a crash leaves one complete copy at `final` or beside it."""
    old = final + ".old"
    shutil.rmtree(old, ignore_errors=True)
    if os.path.exists(final):
        os.rename(final, old)
    os.rename(new, final)
    shutil.rmtree(old, ignore_errors=True)


def write_published(topic, cand, sig):
    d = c.published_dir(topic)
    tmp = d + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    c.write_file(os.path.join(tmp, c.KEV_DATA_FILE), cand["cbytes"])
    c.write_file(os.path.join(tmp, "manifest.json.sig"), sig)
    c.write_file(os.path.join(tmp, "manifest.json"), cand["mbytes"])
    c.write_file(os.path.join(tmp, "seq"), f"{cand['manifest']['seq']}\n")
    replace_dir(tmp, d)


def approve(topic, cid, sha, accept_flags=False, dry_run=False):
    """-> exit code."""
    if not SHA_ARG_RE.fullmatch(sha or ""):
        raise Refuse("--sha must be at least the first 12 hex characters of the manifest's SHA-256")
    try:
        tconf = c.load_topic(topic)
    except c.ConfigError as e:
        raise ConfigProblem(str(e))
    c.ensure_private_dir(c.topic_dir(topic))
    lockf = open(c.topic_dir(topic, ".publish.lock"), "a")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise Refuse("another publish for this topic is running")
    try:
        return _approve_locked(topic, tconf, cid, sha, accept_flags, dry_run)
    finally:
        lockf.close()


def _approve_locked(topic, tconf, cid, sha, accept_flags, dry_run):
    cand = load_candidate(topic, cid, tconf, sha)                            # step 1 happens inside, on the manifest bytes
    pub_seq, pub_mbytes, pub_rows = load_published(topic)
    flags = check_candidate(cand, topic, tconf, pub_seq, pub_mbytes, pub_rows)   # step 2
    if flags and not accept_flags:
        raise Refuse("flags present: " + ", ".join(flags) + " (read the report, then add --accept-flags to accept them)")
    settings, key, pub, env = load_secrets(topic, need_deploy_env=not dry_run and not os.environ.get("STATEFEED_DEPLOY_CMD"))
    if not dry_run and not settings["base_urls"]:
        raise ConfigProblem(f"{c.statefeed_conf()}/{topic}.json needs base_urls (the served-bytes check)")
    m = cand["manifest"]
    if m.get("mirrors", []) != settings["mirrors"]:
        raise Refuse(f"the manifest's mirror list differs from the mirrors in {c.statefeed_conf()}/{topic}.json; build again")
    sig = sign_manifest(key, cand["mbytes"], settings["principal"], pub)         # step 3
    home = c.topic_dir(topic)
    if dry_run:
        dest = os.path.join(home, "dry-run-tree")
        shutil.rmtree(dest, ignore_errors=True)
        kept = assemble_tree(topic, tconf, cand, sig, settings, pub, dest)       # step 4, kept for inspection
        n, total = check_tree(dest)
        say(f"dry run: candidate {cid} seq {m['seq']} snapshot {m['snapshot']}, {m['item_count']} items, flags: {', '.join(flags) or 'none'}")
        say(f"tree: {dest} ({n} files, {total} bytes, snapshots kept: {len(kept)})")
        say("nothing was deployed, published or sent.")
        return 0
    tree = tempfile.mkdtemp(prefix=".assemble-", dir=home)
    try:
        dest = os.path.join(tree, "site")
        kept = assemble_tree(topic, tconf, cand, sig, settings, pub, dest)       # step 4
        secrets = [env.get("CLOUDFLARE_API_TOKEN"), env.get("CLOUDFLARE_ACCOUNT_ID")]
        argv = deploy_argv(os.path.join(c.statefeed_conf(), "cloudflare.env"), dest, settings["project"])
        say(f"deploying candidate {cid} (seq {m['seq']}, {len(cand['rows'])} items) ...")
        ok, tail = run_deploy(argv, secrets)                                      # step 5
        if not ok:
            c.notify(f"statefeed {topic}: deploy of candidate {cid} FAILED; published state unchanged. See the operator terminal or logs.")
            raise Refuse(f"deploy failed: {tail}")
        say("deploy finished: " + tail)
        ok, why = served_check(settings["base_urls"], cand["mbytes"], sig,        # step 6
                               [(m["files"][0]["path"], cand["cbytes"])])
        if not ok:
            c.notify(f"statefeed {topic}: candidate {cid} was deployed but the served bytes do not match the signed manifest "
                     f"({clean(why, 200)}); published state unchanged. Check the live site, then run the same approve again.")
            raise Refuse(f"served-bytes check failed: {why}")
        replace_dir(dest, c.site_dir(topic))                                      # step 7
        write_published(topic, cand, sig)
    finally:
        shutil.rmtree(tree, ignore_errors=True)
    c.notify(f"statefeed {topic}: published seq {m['seq']} ({m['snapshot']}), {m['item_count']} items")
    say(f"published seq {m['seq']} ({m['snapshot']}), {m['item_count']} items")
    return 0


# ------------------------------------------------------------------ status

def status_topics(topic):
    if topic:
        return [topic]
    try:
        names = sorted(os.listdir(c.statefeed_home()))
    except OSError:
        return []
    return [n for n in names if c.TOPIC_RE.fullmatch(n) and os.path.isdir(os.path.join(c.statefeed_home(), n))]


def status(topic=None):
    topics = status_topics(topic)
    if not topics:
        say("no topics found")
        return 0
    for t in topics:
        try:
            pub_seq, pub_m, _ = load_published(t)
        except Refuse as e:
            pub_seq, pub_m = 0, None
            say(f"{t}: {e}")
        say(f"{t}: published seq {pub_seq}" + (f", manifest {c.sha256_bytes(pub_m)[:12]}" if pub_m else ", nothing published yet"))
        cands = list_candidates(t)
        if not cands:
            say("  no candidates")
        for cid in cands:
            d = os.path.join(c.candidates_dir(t), cid)
            try:
                mb = read_capped(os.path.join(d, "manifest.json"), MAX_MANIFEST_BYTES)
                m = c.load_json_strict(mb)
                seq, count = m["seq"], m["item_count"]
                note = "" if seq == pub_seq + 1 else "  (not the next seq: cannot be approved)"
            except (Refuse, ValueError, KeyError, TypeError):
                say(f"  {cid}  unreadable manifest")
                continue
            try:
                df = parse_diff(read_capped(os.path.join(d, "diff.json"), MAX_DIFF_BYTES))
                counts = f"+{len(df.get('new', []))} -{len(df.get('removed', []))} ~{len(df.get('updated', []))} " \
                         f"disputed {len(df.get('disputed', []))}"
                flags = ", ".join(df["flags"]) or "none"
            except Refuse as e:
                counts, flags = "diff.json unreadable", f"UNKNOWN ({clean(e, 60)})"
            say(f"  {cid}  seq {clean(seq, 12)}  {clean(count, 12)} items  {counts}  flags: {flags}  sha {c.sha256_bytes(mb)[:12]}{note}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="publish.py", description="statefeed publisher")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", help="list candidates")
    s.add_argument("topic", nargs="?")
    a = sub.add_parser("approve", help="validate, sign, deploy and check one candidate")
    a.add_argument("topic")
    a.add_argument("cand_id")
    a.add_argument("--sha", required=True, help="first 12+ hex characters of sha256(manifest.json)")
    a.add_argument("--accept-flags", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "status":
            if args.topic and not c.TOPIC_RE.fullmatch(args.topic):
                raise Refuse("invalid topic name")
            return status(args.topic)
        if not c.TOPIC_RE.fullmatch(args.topic):
            raise Refuse("invalid topic name")
        return approve(args.topic, args.cand_id, args.sha, args.accept_flags, args.dry_run)
    except Refuse as e:
        err(f"statefeed: refused: {clean(e, 600)}")
        return 1
    except ConfigProblem as e:
        err(f"statefeed: configuration: {clean(e, 600)}")
        return 2
    except c.ConfigError as e:
        err(f"statefeed: configuration: {clean(e, 600)}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
