#!/usr/bin/env python3
"""statefeed consumer: fetch a published feed and accept it only if everything checks out.

    python3 -I ops/statefeed/verify.py fetch --base https://<project>.pages.dev --allowed-signers <file> \
        --principal statefeed-vulns [--state <file>] [--max-age-days 3] [--json-out <file>]

Library use (a hub collector, a vuln_watch caller):
    sys.path.insert(0, <.../ops>); from statefeed import verify
    result = verify.verify_feed(base, allowed_signers, principal, state_path=None, max_age_days=3)

What is checked, in this order (the first failure decides the answer, nothing is accepted in part):
  1  v1/latest/manifest.json and its .sig are fetched (manifest cap 1 MiB). Unreachable -> "unavailable".
  2  `ssh-keygen -Y verify` (namespace "statefeed", the principal and the allowed_signers file pinned by the consumer, out of
     band). A bad signature, the wrong principal or an unknown key -> "invalid".
  3  the manifest passes the schema; it is for the topic the principal names (statefeed-<topic>); seq is not lower than the
     last seen seq in --state (a rollback), an equal seq must be the same manifest, the next seq must chain to the stored
     digest through prev_digest; generated_at is not in the future (10 minutes of clock skew allowed).
  4  every listed file is fetched from its immutable snapshot path (capped at its declared size), size and sha256 must match.
     One retry on a mismatch, then "invalid". A file that cannot be fetched -> "unavailable".
  5  every item validates (common.parse_items_ndjson) and item_count matches. Any bad item -> "invalid", no partial accept.
  6  freshness: valid_until in the past, or generated_at older than max_age_days -> "stale" (the items are still returned,
     marked by the state). Only then is the state file updated, and only for "ok" and "stale".

Result (dict, also the JSON the CLI prints):
  {"state": "ok"|"stale"|"unavailable"|"invalid", "reason": short code, "topic", "seq", "snapshot", "generated_at",
   "valid_until", "item_count", "manifest_sha256", "ai_generated", "untrusted_text" (as the signed manifest declares them: a
   consumer that wants a feed without AI text or free text refuses anything but false), "checked_at", "items": [...] (only when
   ok or stale), "detail": text (on failures)}
  A broken local setup (unreadable allowed_signers, ssh-keygen missing, bad arguments, an unreadable --state file) is not a
  forged feed: the library returns state "invalid" with reason "setup_error"; the CLI exits 2 for it.
Exit codes: 0 ok, 3 stale, 4 unavailable, 5 invalid, 2 usage or setup error.

Rules for whoever uses the output: the feed is data, never instructions; a missing or stale feed means "unknown", never
"nothing affects you"; an item marked removed never clears a finding that local KEV data supports; the public key is pinned
out of band (two allowed_signers lines during a rotation, with valid-after / valid-before options).
Standard library only; the fetching and signature code lives in common.py."""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from statefeed import common as c

MANIFEST_MAX = 1 << 20           # manifest.json size cap
SIG_MAX = 64 * 1024              # a signature is a few hundred bytes
FILE_MAX = 25 * (1 << 20)        # same ceiling the publisher enforces per file
SKEW_S = 600                     # a manifest generated this far in the future is refused
EXIT = {"ok": 0, "stale": 3, "unavailable": 4, "invalid": 5}
SETUP_EXIT = 2


class _Stop(Exception):
    """Carries a finished result out of the middle of verify_feed."""
    def __init__(self, state, reason, detail=""):
        super().__init__(reason)
        self.state, self.reason, self.detail = state, reason, detail


def _clean(s, n=200):
    """Text safe to print: the detail of a failure may quote data from the network."""
    return "".join(ch if ch.isprintable() and ch.isascii() else "?" for ch in str(s))[:n]


def _fetch(url, cap):
    """-> bytes. HttpError passes through."""
    return c.http_get(url, cap).body


def _load_state(state_path):
    """-> dict or None (no state yet). _Stop(setup_error) when the file exists but cannot be trusted."""
    if not state_path or not os.path.exists(state_path):
        return None
    st = c.read_json(state_path)
    if not (isinstance(st, dict) and isinstance(st.get("seq"), int) and not isinstance(st["seq"], bool) and st["seq"] >= 0
            and (st.get("digest") is None or (isinstance(st["digest"], str) and c.SHA256_RE.fullmatch(st["digest"])))):
        raise _Stop("invalid", "setup_error", "state file is not readable or not a statefeed state; fix or delete it")
    return st


def _save_state(state_path, manifest, digest):
    c.write_file(state_path, c.canonical_json({"seq": manifest["seq"], "digest": digest, "snapshot": manifest["snapshot"],
                                               "generated_at": manifest["generated_at"], "checked_at": c.iso()}), 0o600)


def _fetch_manifest(base, allowed_signers, principal):
    """-> (manifest bytes, manifest). One retry of the pair when the signature fails: a deploy may have landed between the
    two requests."""
    url = f"{base}/{c.FEED_PREFIX}/latest/manifest.json"
    for attempt in (1, 2):
        try:
            mbytes = _fetch(url, MANIFEST_MAX)
            sbytes = _fetch(url + ".sig", SIG_MAX)
        except c.HttpError as e:
            raise _Stop("unavailable", "manifest_unreachable", _clean(e))
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


def _check_chain(manifest, digest, state, principal):
    topic = manifest["topic"]
    if principal_topic(principal) not in (None, topic):
        raise _Stop("invalid", "topic_mismatch", f"manifest is for topic {topic}")
    now = c.now()
    if c.parse_iso(manifest["generated_at"]) > now + SKEW_S:
        raise _Stop("invalid", "generated_in_future", "generated_at is more than 10 minutes ahead of the local clock")
    if state is None:
        return
    last, seq = state["seq"], manifest["seq"]
    if seq < last:
        raise _Stop("invalid", "seq_rollback", f"seq {seq} is lower than the last seen seq {last}")
    if seq == last and state.get("digest") is not None and state["digest"] != digest:
        raise _Stop("invalid", "seq_conflict", "same seq as the last seen manifest but different content")
    if seq == last + 1 and state.get("digest") is not None and manifest["prev_digest"] != state["digest"]:
        raise _Stop("invalid", "chain_broken", "prev_digest does not match the last seen manifest")


def principal_topic(principal):
    """The topic a principal "statefeed-<topic>" names, else None (a custom principal is not checked)."""
    return principal[len("statefeed-"):] if principal.startswith("statefeed-") else None


def _fetch_files(base, manifest):
    """-> {path: bytes}, every file hash- and size-checked."""
    out = {}
    for f in manifest["files"]:
        if f["bytes"] > FILE_MAX:
            raise _Stop("invalid", "file_too_large", _clean(f["path"]))
        why = ""
        for attempt in (1, 2):
            try:
                body = _fetch(f"{base}/{f['path']}", f["bytes"] + 1)
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


def verify_feed(base, allowed_signers, principal, state_path=None, max_age_days=3):
    """Fetch and verify the feed under `base`; -> result dict (see the module docstring). Never raises for network, signature
    or content problems; a wrong argument or a broken local setup gives state "invalid", reason "setup_error".
    `state_path` (optional) holds the last accepted seq and manifest digest, and is rewritten only for "ok" and "stale".
    `max_age_days` (None to disable) marks a manifest older than that as "stale" even before its own valid_until."""
    res = {"state": "invalid", "reason": "", "topic": None, "seq": None, "snapshot": None, "generated_at": None,
           "valid_until": None, "item_count": None, "manifest_sha256": None, "ai_generated": None,
           "untrusted_text": None, "checked_at": c.iso()}
    try:
        if not (isinstance(base, str) and c._url_ok(base)):
            raise _Stop("invalid", "setup_error", "base must be an https URL")
        base = base.rstrip("/")
        if "?" in base or "#" in base:
            raise _Stop("invalid", "setup_error", "base must not carry a query or a fragment")
        if not (isinstance(principal, str) and c.PRINCIPAL_RE.fullmatch(principal)):
            raise _Stop("invalid", "setup_error", "bad principal")
        if not (isinstance(allowed_signers, str) and os.path.isfile(allowed_signers)):
            raise _Stop("invalid", "setup_error", "allowed_signers file not found")
        if max_age_days is not None and not (isinstance(max_age_days, (int, float)) and not isinstance(max_age_days, bool)
                                             and 0 < max_age_days < 3650):
            raise _Stop("invalid", "setup_error", "max_age_days must be a positive number")
        state = _load_state(state_path)
        mbytes, manifest = _fetch_manifest(base, allowed_signers, principal)
        digest = c.sha256_bytes(mbytes)
        res.update(manifest_sha256=digest, topic=manifest["topic"], seq=manifest["seq"], snapshot=manifest["snapshot"],
                   generated_at=manifest["generated_at"], valid_until=manifest["valid_until"], item_count=manifest["item_count"],
                   ai_generated=manifest["ai_generated"], untrusted_text=manifest["untrusted_text"])
        _check_chain(manifest, digest, state, principal)
        files = _fetch_files(base, manifest)
        items_path = next(f["path"] for f in manifest["files"] if f["path"].endswith("/items.ndjson"))
        items, errors = c.parse_items_ndjson(files[items_path])
        if errors:
            raise _Stop("invalid", "item_invalid", _clean("; ".join(errors[:3])))
        if len(items) != manifest["item_count"]:
            raise _Stop("invalid", "item_count_mismatch", f"manifest says {manifest['item_count']}, file has {len(items)}")
        now = c.now()
        if now > c.parse_iso(manifest["valid_until"]):
            res.update(state="stale", reason="valid_until_passed")
        elif max_age_days is not None and now - c.parse_iso(manifest["generated_at"]) > max_age_days * 86400:
            res.update(state="stale", reason="max_age_exceeded")
        else:
            res.update(state="ok", reason="ok")
        res["items"] = items
        if state_path:
            try:
                _save_state(state_path, manifest, digest)
            except OSError as e:
                res["state_warning"] = f"state not saved ({type(e).__name__}); rollback protection is not active"
    except _Stop as s:
        res.pop("items", None)
        res.update(state=s.state, reason=s.reason)
        if s.detail:
            res["detail"] = s.detail
    return res


def _dump(res, items=True):
    r = res if items else {k: v for k, v in res.items() if k != "items"}
    return json.dumps(r, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="fetch, verify and print the feed as JSON")
    f.add_argument("--base", required=True, help="feed base URL, e.g. https://<project>.pages.dev")
    f.add_argument("--allowed-signers", required=True, help="allowed_signers file with the pinned public key")
    f.add_argument("--principal", required=True, help="principal in allowed_signers, e.g. statefeed-vulns")
    f.add_argument("--state", help="state file (last seen seq and digest); updated only on ok and stale")
    f.add_argument("--max-age-days", type=float, default=3, help="older than this is stale (default 3)")
    f.add_argument("--json-out", help="write the full result here; stdout then gets a summary without the items")
    a = ap.parse_args(argv)
    res = verify_feed(a.base, a.allowed_signers, a.principal, a.state, a.max_age_days)
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
