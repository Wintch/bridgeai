#!/usr/bin/env python3
"""statefeed consumer: fetch a published feed (from one place or several) and accept it only if everything checks out.

    python3 -I ops/statefeed/verify.py fetch --base https://<site> [--mirror <source> ...] --allowed-signers <file> \
        --principal statefeed-vulns [--state <file>] [--max-age-days 3] [--json-out <file>]
    python3 -I ops/statefeed/verify.py offline --manifest M --sig S --data D --allowed-signers <file> \
        --principal statefeed-vulns [--state <file>] [--max-age-days 3] [--json-out <file>]

Library use (a hub collector, a vuln_watch caller):
    sys.path.insert(0, <.../ops>); from statefeed import verify
    result = verify.verify_feed(base, allowed_signers, principal, state_path=None, max_age_days=3, mirrors=())

Sources. `--base` and every `--mirror` is one place to get the same feed from; at least one is needed. A source is
  https://<site>[/path]     the feed base (v1/latest/manifest.json under it; http only for 127.0.0.1, in tests)
  dir:/path                 a directory laid out like the site (a deploy tree, a git checkout, an unpacked archive)
  file:/path/manifest.json  a manifest received any way: its signature next to it as manifest.json.sig, kev.csv next to it too
                            (or at the snapshot path under the same site root)
Every source is fetched and verified independently, in full. The answer comes from the one with the highest valid seq; the
others are reported ("sources": seq, state, "behind" when lower). Two validly signed manifests with the same seq and a different
digest are a seq_conflict: invalid, nothing is returned and the state file is not touched. Mirrors the signed manifest lists are
printed under "mirrors" and never fetched: adding one is the reader's decision (--mirror).
`offline` runs the same checks on three files received any way (forwarded from Telegram, email, a USB stick).

What is checked for each source, in this order (the first failure decides that source, nothing is accepted in part):
  1  the manifest and its .sig are fetched (16 KiB each; manifest and signature together may not pass 3,500 bytes).
     Unreachable -> "unavailable".
  2  `ssh-keygen -Y verify` (namespace "statefeed", the principal and the allowed_signers file pinned by the consumer, out of
     band). A bad signature, the wrong principal or an unknown key -> "invalid".
  3  the manifest passes the schema; it is for the topic the principal names (statefeed-<topic>); generated_at is not in the
     future (10 minutes of clock skew allowed); seq is not lower than the last seen seq in --state (a rollback), an equal seq
     must be the same manifest, the next seq must chain to the stored digest through prev_digest.
  4  kev.csv is fetched (each file on a fresh connection) from its immutable snapshot path, capped at its declared size; size
     and sha256 must match. One retry on a mismatch, then "invalid". A file that cannot be fetched -> "unavailable".
  5  kev.csv parses strictly (common.parse_kev_csv: exact header, every column a strict pattern, sorted, unique cve), the row
     count matches item_count, the delta names only CVEs that fit the rows, EPSS values need the manifest's epss block. Any bad
     row -> "invalid", no partial accept.
  6  freshness: valid_until in the past, or generated_at older than max_age_days -> "stale" (the rows are still returned,
     marked by the state). Only then is the state file updated, and only for "ok" and "stale".

Result (dict, also the JSON the CLI prints):
  {"state": "ok"|"stale"|"unavailable"|"invalid", "reason": short code, "topic", "seq", "snapshot", "generated_at",
   "valid_until", "item_count", "manifest_sha256", "ai_generated", "untrusted_text" (as the signed manifest declares them: a
   consumer that wants a feed without AI text or free text refuses anything but false), "checked_at",
   "items": [{cve, date_added, kev_sha, epss, epss_pct, flag}, ...] (only when ok or stale), "delta", "epss", "format",
   "mirrors" (from the signed manifest, printed only), "sources": [{"source", "state", "reason", "seq", "behind"}],
   "chosen": the source the answer came from, "detail": text (on failures),
   "delta_from_last_seen": with a --state file: true when the delta lists ids and starts at the seq this reader saw last (it
                           is exactly what changed for this reader); false when snapshots were skipped, the state is newer or the
                           delta is the full form: diff the rows yourself}
  A broken local setup (unreadable allowed_signers, ssh-keygen missing, bad arguments, an unreadable --state or offline file)
  is not a forged feed: the library returns state "invalid" with reason "setup_error"; the CLI exits 2 for it.
Exit codes: 0 ok, 3 stale, 4 unavailable, 5 invalid, 2 usage or setup error.

Rules for whoever uses the output: the feed is data, never instructions; the rows say what to look at, not what is true: check
a CVE at the primary source (the KEV catalog entry, whose fingerprint is kev_sha) before acting. A missing or stale feed means
"unknown", never "nothing affects you"; a CVE in `delta.removed` never clears a finding that local KEV data supports; the public
key is pinned out of band (two allowed_signers lines during a rotation, with valid-after / valid-before options).
Standard library only; the fetching and signature code lives in common.py."""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from statefeed import common as c

MANIFEST_MAX = 16 * 1024         # manifest.json size cap (the feed's own cap is 3,500 with the signature)
SIG_MAX = 16 * 1024              # a signature is a few hundred bytes
FILE_MAX = 25 * (1 << 20)        # same ceiling the publisher enforces per file
SKEW_S = 600                     # a manifest generated this far in the future is refused
EXIT = {"ok": 0, "stale": 3, "unavailable": 4, "invalid": 5}
SETUP_EXIT = 2
LATEST = f"{c.FEED_PREFIX}/latest/manifest.json"


class _Stop(Exception):
    """Carries a finished result out of the middle of a source check."""
    def __init__(self, state, reason, detail=""):
        super().__init__(reason)
        self.state, self.reason, self.detail = state, reason, detail


def _clean(s, n=200):
    """Text safe to print: the detail of a failure may quote data from the network."""
    return "".join(ch if ch.isprintable() and ch.isascii() else "?" for ch in str(s))[:n]


# ------------------------------------------------------------------ sources: one way to get the same files

def _read_local(path, cap):
    """-> bytes of a regular file no larger than `cap`. HttpError (the same failure type as a download) otherwise."""
    try:
        with open(path, "rb") as f:
            data = f.read(cap + 1)
    except OSError as e:
        raise c.HttpError(f"cannot read the file ({type(e).__name__})")
    if len(data) > cap:
        raise c.HttpError("response larger than the cap")
    return data


class _Http:
    """A feed base URL. Every file is a separate request on its own connection (urllib closes it after each response)."""

    def __init__(self, base):
        self.base, self.label = base, _clean(base)

    def get(self, rel, cap):
        return c.http_get(f"{self.base}/{rel}", cap, headers={"Connection": "close"}).body


class _Dir:
    def __init__(self, root, label):
        self.root, self.label = root, label

    def get(self, rel, cap):
        return _read_local(os.path.join(self.root, *rel.split("/")), cap)


class _File:
    """A manifest file given directly: signature beside it, kev.csv beside it or under the same site root (when the manifest
    sits in <root>/v1/latest or <root>/v1/snapshots/<snapshot>)."""

    def __init__(self, path, label):
        self.path, self.label = path, label

    def get(self, rel, cap):
        if rel == LATEST:
            return _read_local(self.path, cap)
        if rel == LATEST + ".sig":
            return _read_local(self.path + ".sig", cap)
        here = os.path.dirname(os.path.abspath(self.path))
        tries = [os.path.join(here, rel.rsplit("/", 1)[1])]
        parts = here.split(os.sep)
        for cut, marker in ((2, ("v1", "latest")), (3, ("v1", "snapshots"))):    # <root>/v1/latest, <root>/v1/snapshots/<snap>
            if len(parts) > cut and tuple(parts[-cut:len(parts) - cut + 2]) == marker:
                tries.append(os.path.join(os.sep.join(parts[:-cut]) or os.sep, *rel.split("/")))
        err = None
        for t in tries:
            try:
                return _read_local(t, cap)
            except c.HttpError as e:
                err = e
        raise err


class _Mem:
    """Three files already in memory (the `offline` command): manifest, signature, the data file."""
    label = "offline"

    def __init__(self, manifest, sig, data):
        self.manifest, self.sig, self.data = manifest, sig, data

    def get(self, rel, cap):
        body = self.manifest if rel == LATEST else self.sig if rel == LATEST + ".sig" else self.data
        if len(body) > cap:
            raise c.HttpError("response larger than the cap")
        return body


def parse_source(text):
    """A --base / --mirror value -> source object. ValueError (a short reason) for a source that cannot be used."""
    if not isinstance(text, str) or not text:
        raise ValueError("empty source")
    if text.startswith("dir:"):
        if not os.path.isdir(text[4:]):
            raise ValueError("dir: source is not a directory")
        return _Dir(os.path.abspath(text[4:]), _clean(text))
    if text.startswith("file:"):
        if not os.path.isfile(text[5:]):
            raise ValueError("file: source is not a file")
        return _File(text[5:], _clean(text))
    if not c._url_ok(text):
        raise ValueError("a source must be an https URL, dir:/path or file:/path/manifest.json")
    base = text.rstrip("/")
    if "?" in base or "#" in base:
        raise ValueError("a source URL must not carry a query or a fragment")
    return _Http(base)


# ------------------------------------------------------------------ state

def _load_state(state_path):
    """-> dict or None (no state yet). _Stop(setup_error) when the file exists but cannot be trusted."""
    if not state_path or not os.path.exists(state_path):
        return None
    try:
        st = c.read_json(state_path)
    except (OSError, ValueError):
        st = None
    if not (isinstance(st, dict) and isinstance(st.get("seq"), int) and not isinstance(st["seq"], bool) and st["seq"] >= 0
            and (st.get("digest") is None or (isinstance(st["digest"], str) and c.SHA256_RE.fullmatch(st["digest"])))):
        raise _Stop("invalid", "setup_error", "state file is not readable or not a statefeed state; fix or delete it")
    return st


def _save_state(state_path, manifest, digest):
    c.write_file(state_path, c.canonical_json({"seq": manifest["seq"], "digest": digest, "snapshot": manifest["snapshot"],
                                               "generated_at": manifest["generated_at"], "checked_at": c.iso()}), 0o600)


# ------------------------------------------------------------------ one source

def _fetch_manifest(src, allowed_signers, principal):
    """-> (manifest bytes, manifest). One retry of the pair when the signature fails: a deploy may have landed between the
    two requests."""
    for attempt in (1, 2):
        try:
            mbytes = src.get(LATEST, MANIFEST_MAX)
            sbytes = src.get(LATEST + ".sig", SIG_MAX)
        except c.HttpError as e:
            if "larger than the cap" in str(e):
                raise _Stop("invalid", "manifest_too_large", "manifest or signature is larger than any feed's can be")
            raise _Stop("unavailable", "manifest_unreachable", _clean(e))
        why = c.feed_size_problem(mbytes, sbytes)
        if why:
            raise _Stop("invalid", "manifest_too_large", _clean(why))
        try:
            good = c.ssh_verify(allowed_signers, principal, c.SIGN_NAMESPACE, mbytes, sbytes)
        except c.SignError as e:
            raise _Stop("invalid", "setup_error", _clean(e))
        if good:
            break
        if attempt == 2:
            raise _Stop("invalid", "bad_signature", "the manifest signature does not verify for the pinned key and principal")
    try:
        manifest = c.load_json_strict(mbytes)
    except ValueError as e:
        raise _Stop("invalid", "manifest_unparsable", _clean(e))
    errs = c.validate_manifest(manifest)
    if errs:
        raise _Stop("invalid", "manifest_schema", _clean("; ".join(errs[:3])))
    return mbytes, manifest


def principal_topic(principal):
    """The topic a principal "statefeed-<topic>" names, else None (a custom principal is not checked)."""
    return principal[len("statefeed-"):] if principal.startswith("statefeed-") else None


def _check_basic(manifest, principal):
    topic = manifest["topic"]
    if principal_topic(principal) not in (None, topic):
        raise _Stop("invalid", "topic_mismatch", f"manifest is for topic {topic}")
    if c.parse_iso(manifest["generated_at"]) > c.now() + SKEW_S:
        raise _Stop("invalid", "generated_in_future", "generated_at is more than 10 minutes ahead of the local clock")


def _check_state(manifest, digest, state):
    if state is None:
        return
    last, seq = state["seq"], manifest["seq"]
    if seq < last:
        raise _Stop("invalid", "seq_rollback", f"seq {seq} is lower than the last seen seq {last}")
    if seq == last and state.get("digest") is not None and state["digest"] != digest:
        raise _Stop("invalid", "seq_conflict", "same seq as the last seen manifest but different content")
    if seq == last + 1 and state.get("digest") is not None and manifest["prev_digest"] != state["digest"]:
        raise _Stop("invalid", "chain_broken", "prev_digest does not match the last seen manifest")


def _fetch_files(src, manifest):
    """-> {path: bytes}, every file hash- and size-checked."""
    out = {}
    for f in manifest["files"]:
        if f["bytes"] > FILE_MAX:
            raise _Stop("invalid", "file_too_large", _clean(f["path"]))
        why = ""
        for attempt in (1, 2):
            try:
                body = src.get(f["path"], f["bytes"] + 1)
            except c.HttpError as e:
                if "larger than the cap" in str(e):
                    why = "file_size_mismatch"
                    continue
                raise _Stop("unavailable", "file_unreachable", _clean(f"{f['path']}: {e}"))
            if len(body) != f["bytes"]:
                why = "file_size_mismatch"
            elif c.sha256_bytes(body) != f["sha256"]:
                why = "file_hash_mismatch"
            else:
                out[f["path"]] = body
                break
        else:
            raise _Stop("invalid", why, _clean(f["path"]))
    return out


def _check_rows(manifest, data):
    """-> rows. The kev.csv content against the signed manifest."""
    rows, errors = c.parse_kev_csv(data)
    if errors:
        raise _Stop("invalid", "csv_invalid", _clean("; ".join(errors[:3])))
    if len(rows) != manifest["item_count"]:
        raise _Stop("invalid", "item_count_mismatch", f"manifest says {manifest['item_count']}, file has {len(rows)}")
    if manifest["epss"] is None and any(r["epss"] for r in rows):
        raise _Stop("invalid", "epss_inconsistent", "rows carry EPSS scores but the manifest has no epss block")
    ids = {r["cve"] for r in rows}
    d = manifest["delta"]
    if "added" in d and not (set(d["added"]) <= ids and set(d["changed"]) <= ids and not set(d["removed"]) & ids):
        raise _Stop("invalid", "delta_inconsistent", "the delta names CVEs that do not fit kev.csv")
    return rows


def _check_source(src, allowed_signers, principal, state, max_age_days):
    """Everything about one source. -> dict: label, state, reason, detail, seq, digest, signed (the manifest passed the signature,
    schema, topic and clock checks: its seq and digest count as evidence), manifest, rows."""
    r = {"label": src.label, "state": "invalid", "reason": "", "detail": "", "seq": None, "digest": None, "signed": False,
         "manifest": None, "rows": None}
    try:
        mbytes, manifest = _fetch_manifest(src, allowed_signers, principal)
        digest = c.sha256_bytes(mbytes)
        r.update(manifest=manifest, seq=manifest["seq"], digest=digest)
        _check_basic(manifest, principal)
        r["signed"] = True
        _check_state(manifest, digest, state)
        files = _fetch_files(src, manifest)
        r["rows"] = _check_rows(manifest, files[manifest["files"][0]["path"]])
        now = c.now()
        if now > c.parse_iso(manifest["valid_until"]):
            r.update(state="stale", reason="valid_until_passed")
        elif max_age_days is not None and now - c.parse_iso(manifest["generated_at"]) > max_age_days * 86400:
            r.update(state="stale", reason="max_age_exceeded")
        else:
            r.update(state="ok", reason="ok")
    except _Stop as s:
        r.update(state=s.state, reason=s.reason, detail=s.detail, rows=None)
    return r


# ------------------------------------------------------------------ several sources

def _fill(res, r):
    """Copy what a source's signed manifest says into the result."""
    m = r["manifest"]
    if m is None:
        return
    res.update(manifest_sha256=r["digest"], topic=m["topic"], seq=m["seq"], snapshot=m["snapshot"], generated_at=m["generated_at"],
               valid_until=m["valid_until"], item_count=m["item_count"], ai_generated=m["ai_generated"],
               untrusted_text=m["untrusted_text"], delta=m["delta"], epss=m["epss"], format=m["format"],
               mirrors=m.get("mirrors", []))


def _conflict(rs, state):
    """The seq at which validly signed manifests disagree (checked at the newest signed seq and at the newest valid seq), or
    None. A manifest that has the stored seq but another digest than the state counts as disagreeing too."""
    last = state["seq"] if state else 0
    signed = [r for r in rs if r["signed"] and r["seq"] >= last]
    seqs = {max((r["seq"] for r in signed), default=None), max((r["seq"] for r in rs if r["state"] in ("ok", "stale")), default=None)}
    for seq in sorted(s for s in seqs if s is not None):
        digests = {r["digest"] for r in signed if r["seq"] == seq}
        if state and seq == last and state.get("digest") is not None:
            digests.add(state["digest"])
        if len(digests) > 1:
            return seq
    return None


def _verify_sources(sources, allowed_signers, principal, state_path, max_age_days):
    res = {"state": "invalid", "reason": "", "topic": None, "seq": None, "snapshot": None, "generated_at": None,
           "valid_until": None, "item_count": None, "manifest_sha256": None, "ai_generated": None,
           "untrusted_text": None, "delta": None, "epss": None, "format": None, "mirrors": [], "sources": [], "chosen": None,
           "checked_at": c.iso()}
    rs = []
    try:
        if not sources:
            raise _Stop("invalid", "setup_error", "no source: give --base or --mirror")
        if not (isinstance(principal, str) and c.PRINCIPAL_RE.fullmatch(principal)):
            raise _Stop("invalid", "setup_error", "bad principal")
        if not (isinstance(allowed_signers, str) and os.path.isfile(allowed_signers)):
            raise _Stop("invalid", "setup_error", "allowed_signers file not found")
        if max_age_days is not None and not (isinstance(max_age_days, (int, float)) and not isinstance(max_age_days, bool)
                                             and 0 < max_age_days < 3650):
            raise _Stop("invalid", "setup_error", "max_age_days must be a positive number")
        state = _load_state(state_path)
        rs = [_check_source(s, allowed_signers, principal, state, max_age_days) for s in sources]
        seq = _conflict(rs, state)
        if seq is not None:
            _fill(res, next(r for r in rs if r["signed"] and r["seq"] == seq))
            raise _Stop("invalid", "seq_conflict", f"validly signed manifests with seq {seq} differ; nothing is accepted")
        valid = [r for r in rs if r["state"] in ("ok", "stale")]
        if not valid:
            bad = next((r for r in rs if r["state"] == "invalid"), rs[0])       # an invalid source says more than a missing one
            _fill(res, bad)
            raise _Stop(bad["state"], bad["reason"], bad["detail"])
        chosen = max(valid, key=lambda r: r["seq"])           # max() keeps the first of equals: the order given
        _fill(res, chosen)
        res.update(state=chosen["state"], reason=chosen["reason"], items=chosen["rows"], chosen=chosen["label"])
        if state is not None:       # the delta only describes the step from its since_seq: a reader who skipped snapshots must diff the csv
            d = chosen["manifest"]["delta"]
            res["delta_from_last_seen"] = "added" in d and d["since_seq"] == state["seq"]
        if state_path:
            try:
                _save_state(state_path, chosen["manifest"], chosen["digest"])
            except OSError as e:
                res["state_warning"] = f"state not saved ({type(e).__name__}); rollback protection is not active"
    except _Stop as s:
        res.pop("items", None)
        res.update(state=s.state, reason=s.reason, chosen=None)
        if s.detail:
            res["detail"] = s.detail
    top = res["seq"] if res["chosen"] else None
    for r in rs:
        res["sources"].append({"source": r["label"], "state": r["state"], "reason": r["reason"], "seq": r["seq"],
                               "behind": top is not None and r["seq"] is not None and r["seq"] < top})
    return res


def _setup_error(allowed_signers, principal, state_path, max_age_days, why):
    res = _verify_sources([], allowed_signers, principal, state_path, max_age_days)
    res.update(state="invalid", reason="setup_error", detail=_clean(why))
    return res


def verify_sources(sources, allowed_signers, principal, state_path=None, max_age_days=3):
    """`sources`: strings as --base / --mirror take them. -> result dict (see the module docstring). Never raises for network,
    signature or content problems; a source that cannot be used gives state "invalid", reason "setup_error"."""
    objs = []
    for s in sources:
        try:
            objs.append(parse_source(s))
        except ValueError as e:
            return _setup_error(allowed_signers, principal, state_path, max_age_days, e)
    return _verify_sources(objs, allowed_signers, principal, state_path, max_age_days)


def verify_feed(base, allowed_signers, principal, state_path=None, max_age_days=3, mirrors=()):
    """Fetch and verify the feed under `base` (and under every `mirrors` source); -> result dict (see the module docstring).
    `state_path` (optional) holds the last accepted seq and manifest digest, and is rewritten only for "ok" and "stale".
    `max_age_days` (None to disable) marks a manifest older than that as "stale" even before its own valid_until."""
    return verify_sources(([base] if base is not None else []) + list(mirrors), allowed_signers, principal, state_path, max_age_days)


def verify_offline(manifest_path, sig_path, data_path, allowed_signers, principal, state_path=None, max_age_days=3):
    """The same checks on three files received any way: the manifest, its signature and kev.csv. -> result dict."""
    try:
        mem = _Mem(_read_local(manifest_path, MANIFEST_MAX), _read_local(sig_path, SIG_MAX), _read_local(data_path, FILE_MAX))
    except c.HttpError as e:
        return _setup_error(allowed_signers, principal, state_path, max_age_days, f"cannot read an offline file: {e}")
    return _verify_sources([mem], allowed_signers, principal, state_path, max_age_days)


# ------------------------------------------------------------------ command line

def _dump(res, items=True):
    r = res if items else {k: v for k, v in res.items() if k != "items"}
    return json.dumps(r, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _common_args(p):
    p.add_argument("--allowed-signers", required=True, help="allowed_signers file with the pinned public key")
    p.add_argument("--principal", required=True, help="principal in allowed_signers, e.g. statefeed-vulns")
    p.add_argument("--state", help="state file (last seen seq and digest); updated only on ok and stale")
    p.add_argument("--max-age-days", type=float, default=3, help="older than this is stale (default 3)")
    p.add_argument("--json-out", help="write the full result here; stdout then gets a summary without the items")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="fetch, verify and print the feed as JSON")
    f.add_argument("--base", help="feed base URL, e.g. https://<site>")
    f.add_argument("--mirror", action="append", default=[], metavar="SOURCE",
                   help="another place for the same feed (https base URL, dir:/path or file:/path/manifest.json); repeatable")
    _common_args(f)
    o = sub.add_parser("offline", help="verify a manifest, its signature and kev.csv received any way")
    o.add_argument("--manifest", required=True)
    o.add_argument("--sig", required=True)
    o.add_argument("--data", required=True, help="the kev.csv file")
    _common_args(o)
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        if not a.base and not a.mirror:
            ap.error("fetch needs --base or at least one --mirror")
        res = verify_sources(([a.base] if a.base else []) + a.mirror, a.allowed_signers, a.principal, a.state, a.max_age_days)
    else:
        res = verify_offline(a.manifest, a.sig, a.data, a.allowed_signers, a.principal, a.state, a.max_age_days)
    try:
        if a.json_out:
            c.write_file(a.json_out, _dump(res) + "\n")
            print(_dump(res, items=False))
        else:
            print(_dump(res))
    except OSError as e:
        print(f"verify.py: cannot write the result ({type(e).__name__})", file=sys.stderr)
        return SETUP_EXIT
    if res["reason"] == "setup_error":
        return SETUP_EXIT
    return EXIT[res["state"]]


if __name__ == "__main__":
    sys.exit(main())
