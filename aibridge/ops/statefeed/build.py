#!/usr/bin/env python3
"""statefeed build: fetch the sources of one topic, compare them, validate, and write a CANDIDATE for a human to approve.

    python3 -I ~/aibridge/ops/statefeed/build.py --topic vulns [--dry-run]

Needs no secret and never publishes anything: it writes <STATEFEED_HOME>/<topic>/candidates/<cand_id>/ with
  items.ndjson   one canonical JSON item per line, sorted by id (the compiled data; no third-party prose at all)
  manifest.json  the unsigned manifest (publish.py signs it after approval; an approval is bound to its exact bytes)
  diff.json      what changed against the last published snapshot, plus the flags that need --accept-flags
  report.txt     the same as text, and how to approve
and sends ONE ops-bot message (ids and counts only). The source list comes only from topics/<topic>.json (committed), never
from data. For the vulns topic the compiled data is the CISA KEV catalog read through two channels (CISA and the cisagov
GitHub mirror; one `group`, so they count as ONE independent source: their agreement detects a tampered or broken download,
not an error of the authority itself) plus EPSS scores from FIRST. Revisitable v1 choices: see STATEFEED.md.

How a candidate is decided
  * KEV primary unavailable (download failed, no cache younger than 2 days): exit 1, no candidate. Another source that is
    unavailable becomes the flag source_unavailable:<id>; an unavailable EPSS keeps the last published EPSS values (their
    epss_date shows how old they are).
  * Nothing changed against the published snapshot (same items and fields; only hashes of the downloads and generated_at
    differ): no candidate, unless the published manifest runs out within 1 day: then a refresh candidate (flag refresh_only).
  * An entry whose text fails the label rules is never repaired: it is left out, listed in diff.json under `invalid`, and the
    candidate gets the flag invalid_items.
Flags (publish.py approve then needs --accept-flags): first_publish, refresh_only, removed_over_cap, new_over_cap,
items_over_size, invalid_items, disputed_items, source_unavailable:<id>.
Exit codes: 0 candidate written or nothing to do, 1 failure (config, primary source, published state), 2 usage.
"""
import argparse, ipaddress, json, os, re, shutil, sys, urllib.parse, zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from statefeed import common as c

KEEP_CANDIDATES = 7
REFRESH_WITHIN_S = 86400          # a published manifest that runs out within this long gets a refresh candidate
LIST_CAP = 30                     # ids per list in report.txt
COMPARED = ("vendor", "product", "name", "date_added", "due_date", "ransomware", "cwes")
EPSS_FIELDS = ("epss", "epss_percentile", "epss_date")
FLOAT_RE = re.compile(r"[0-9.eE+-]{1,24}")
SCORE_DATE_RE = re.compile(r"score_date:([0-9]{4}-[0-9]{2}-[0-9]{2})")
GZIP_MAGIC = b"\x1f\x8b"
COMPILED_BY = "statefeed/1 (code, no AI)"
LICENCE = {"compilation": "CC-BY-4.0", "records": "see sources[].licence"}


class BuildError(Exception):
    pass


# ------------------------------------------------------------------ source parsing

def parse_kev(body):
    """KEV catalog bytes -> parsed dict. ValueError when it is not a catalog (an error page or an empty list must never
    count as "every entry was removed")."""
    d = c.load_json_strict(body)
    v = d.get("vulnerabilities") if isinstance(d, dict) else None
    if not (isinstance(v, list) and any(isinstance(e, dict) and isinstance(e.get("cveID"), str) for e in v)):
        raise ValueError("not a KEV catalog")
    return d


def _text(x):
    return x.strip() if isinstance(x, str) else x


def normalize_entry(e):
    """The fields of one KEV entry that statefeed compares and publishes (no prose). Text is stripped, nothing else is fixed;
    the label rules judge it later. Ransomware: "Known" is "known", anything else "unknown". CWEs: well-formed ids only,
    sorted by number, at most 10."""
    cw = e.get("cwes")
    cwes = sorted({x.strip() for x in cw if isinstance(x, str) and c.CWE_RE.fullmatch(x.strip())}, key=lambda x: int(x[4:])) if isinstance(cw, list) else []
    due = _text(e.get("dueDate"))
    return {"id": _text(e.get("cveID")), "vendor": _text(e.get("vendorProject")), "product": _text(e.get("product")),
            "name": _text(e.get("vulnerabilityName")), "date_added": _text(e.get("dateAdded")), "due_date": due if due else None,
            "ransomware": "known" if str(_text(e.get("knownRansomwareCampaignUse"))).lower() == "known" else "unknown",
            "cwes": cwes[:10]}


def read_channel(sid, catalog):
    """-> (records {cve id: fields}, invalid [(label, "id")]). An entry without a CVE id, or an id listed twice with different
    content, is invalid (and, for the duplicate, dropped from this channel)."""
    records, invalid, conflict = {}, [], set()
    for n, e in enumerate(catalog["vulnerabilities"], 1):
        if not isinstance(e, dict):
            invalid.append((f"{sid}#{n}", "id"))
            continue
        f = normalize_entry(e)
        cid = f["id"]
        if not (isinstance(cid, str) and c.CVE_RE.fullmatch(cid)):
            invalid.append((f"{sid}#{n}", "id"))
        elif cid in records and records[cid] != f:
            conflict.add(cid)
        else:
            records[cid] = f
    for cid in sorted(conflict):
        records.pop(cid, None)
        invalid.append((cid, "id"))
    return records, invalid


def _gz_lines(body, cap):
    """Lines (bytes) of a gzip (or already plain) body, decompressed in a stream. ValueError: bad or truncated gzip, or more
    than `cap` bytes decompressed."""
    buf, total = b"", 0
    if body[:2] == GZIP_MAGIC:
        d, pos = zlib.decompressobj(16 + zlib.MAX_WBITS), 0
        try:
            while pos < len(body) and not d.eof:
                out = d.decompress(body[pos:pos + 16384])
                pos += 16384
                total += len(out)
                if total > cap:
                    raise ValueError("decompressed file larger than the cap")
                buf += out
                *lines, buf = buf.split(b"\n")
                yield from lines
        except zlib.error:
            raise ValueError("bad gzip data")
        if not d.eof:
            raise ValueError("truncated gzip data")
    else:
        if len(body) > cap:
            raise ValueError("file larger than the cap")
        *lines, buf = body.split(b"\n")
        yield from lines
    if buf:
        yield buf


def parse_epss(body, cap, wanted=None):
    """EPSS csv.gz bytes -> {"date": "YYYY-MM-DD", "rows": n, "bad": n, "scores": {cve: (epss, percentile)}}. The first line is
    a comment `#model_version:...,score_date:<ISO time>`, then the header `cve,epss,percentile`. Only the CVEs in `wanted` are
    kept (all when None). ValueError when the structure is wrong (no score_date, no header, no valid row, truncated)."""
    date, header, rows, bad, scores = None, False, 0, 0, {}
    for raw in _gz_lines(body, cap):
        line = raw.decode("utf-8").strip()
        if not line:
            continue
        if line.startswith("#"):
            m = SCORE_DATE_RE.search(line) if date is None else None
            if m and c.parse_date(m[1]):
                date = m[1]
            continue
        parts = [x.strip() for x in line.split(",")]
        if not header:
            if [x.lower() for x in parts[:3]] != ["cve", "epss", "percentile"]:
                raise ValueError("unexpected EPSS header")
            header = True
            continue
        try:
            cve, e, p = parts[0].upper(), parts[1], parts[2]
            if not (c.CVE_RE.fullmatch(cve) and FLOAT_RE.fullmatch(e) and FLOAT_RE.fullmatch(p)):
                raise ValueError
            e, p = float(e), float(p)
            if not (0 <= e <= 1 and 0 <= p <= 1):
                raise ValueError
        except (ValueError, IndexError):
            bad += 1
            continue
        rows += 1
        if wanted is None or cve in wanted:
            scores[cve] = (e, p)
    if date is None:
        raise ValueError("EPSS file without score_date")
    if not header or rows == 0:
        raise ValueError("EPSS file without rows")
    return {"date": date, "rows": rows, "bad": bad, "scores": scores}


# ------------------------------------------------------------------ fetching

def registrable_domain(host):
    """The last two labels of a host name (no public-suffix list; an IP address or a short name stays as it is). Redirects of
    the EPSS download may stay inside this domain."""
    host = host.lower().rstrip(".")
    try:
        ipaddress.ip_address(host.strip("[]"))
        return host
    except ValueError:
        pass
    parts = host.split(".")
    return host if len(parts) <= 2 else ".".join(parts[-2:])


def fetch_source(topic, src):
    """-> c.FetchResult for one source. KEV sources: redirects stay on the same host. EPSS: the dated file may be served from
    another host of the same registrable domain. A download that does not parse is rejected before it can replace the cache."""
    is_kev = src["kind"] == "kev_json"
    cap = src["max_bytes"]
    allowed = None if is_kev else [registrable_domain(urllib.parse.urlsplit(src["url"]).hostname)]
    validate = parse_kev if is_kev else (lambda b: parse_epss(b, 4 * cap, set()))
    return c.cached_fetch(src["id"], src["url"], cap, c.cache_dir(topic["topic"]), allowed_redirect_domains=allowed, validate=validate)


# ------------------------------------------------------------------ published state

def load_published(name):
    """The last published snapshot kept by publish.py in <home>/<topic>/published/, or None when there is none.
    -> {"manifest", "digest" (sha256 of the manifest bytes), "items" {id: item}}. BuildError when it is damaged: a build must not
    restart the sequence by accident."""
    d = c.published_dir(name)
    mpath = os.path.join(d, "manifest.json")
    if not os.path.exists(mpath):
        return None
    try:
        with open(mpath, "rb") as f:
            mb = f.read()
        m = c.load_json_strict(mb)
        errs = c.validate_manifest(m)
        if errs:
            raise BuildError("published manifest is invalid: " + "; ".join(errs[:3]))
        with open(os.path.join(d, "items.ndjson"), "rb") as f:
            ib = f.read()
    except (OSError, ValueError) as e:
        raise BuildError(f"published state is unreadable ({type(e).__name__})")
    want = [f["sha256"] for f in m["files"] if f["path"].endswith("/items.ndjson")]
    if want != [c.sha256_bytes(ib)]:
        raise BuildError("published items.ndjson does not match its manifest")
    items, errs = c.parse_items_ndjson(ib)
    if errs:
        raise BuildError("published items.ndjson is invalid: " + errs[0])
    return {"manifest": m, "digest": c.sha256_bytes(mb), "items": {i["id"]: i for i in items}}


# ------------------------------------------------------------------ compiling items

def compile_items(topic, channels, epss, prev, today):
    """channels: [(source, FetchResult, records)] primary first; epss: None or (source, FetchResult, parsed) or
    ("carry", source); prev: {id: published item}.
    -> (items [valid items], invalid [(id, field)])."""
    enrich_ids = {s["id"] for s in topic["sources"] if s["role"] == "enrich"}
    ids = sorted({cid for _, _, recs in channels for cid in recs})
    items, invalid = [], set()
    for cid in ids:
        present = [(s, fr, recs[cid]) for s, fr, recs in channels if cid in recs]
        base = present[0][2]
        same = all(f[k] == base[k] for _, _, f in present[1:] for k in COMPARED)
        state = "single_channel" if len(present) == 1 else ("authoritative" if same else "disputed")
        sources = [{"id": s["id"], "licence": s["licence"], "content_sha256": fr.sha256} for s, fr, _ in present]
        old = prev.get(cid)
        item = {"id": cid, "schema_version": c.SCHEMA_VERSION, "type": "kev", **{k: base[k] for k in COMPARED},
                "epss": None, "epss_percentile": None, "epss_date": None,
                "agreement": {"state": state, "channels": len(present), "independent": len({s["group"] for s, _, _ in present})},
                "sources": sources, "first_seen": old["first_seen"] if old else today}
        if epss and epss[0] != "carry":
            src, fr, parsed = epss
            row = parsed["scores"].get(cid)
            if row:
                item.update(epss=row[0], epss_percentile=row[1], epss_date=parsed["date"])
                sources.append({"id": src["id"], "licence": src["licence"], "content_sha256": fr.sha256})
        elif old and old["epss"] is not None:            # EPSS unavailable: keep what was published (epss_date shows its age)
            item.update({k: old[k] for k in EPSS_FIELDS})
            sources.extend(s for s in old["sources"] if s["id"] in enrich_ids)
        sources.sort(key=lambda s: s["id"])
        problems = c.item_problems(item)
        if problems:
            invalid.update((cid, f) for f, _ in problems)
        else:
            items.append(item)
    return items, sorted(invalid)


def comparable(item, enrich_ids, drop_epss=False):
    """An item without the hashes of the downloads (they change whenever any entry of a feed changes), and, on request, without
    the EPSS part."""
    o = dict(item)
    o["sources"] = [(s["id"], s["licence"]) for s in item["sources"] if not (drop_epss and s["id"] in enrich_ids)]
    if drop_epss:
        for f in EPSS_FIELDS:
            o.pop(f)
    return o


def make_diff(topic, items, invalid, prev, extra_flags, first, refresh):
    """-> diff dict (see the module docstring). `prev` is {id: item} (empty on the first publish)."""
    enrich_ids = {s["id"] for s in topic["sources"] if s["role"] == "enrich"}
    cur = {i["id"]: i for i in items}
    new, removed = sorted(set(cur) - set(prev)), sorted(set(prev) - set(cur))
    updated = sorted(i for i in cur if i in prev and comparable(cur[i], enrich_ids) != comparable(prev[i], enrich_ids))
    epss_only = [i for i in updated if comparable(cur[i], enrich_ids, True) == comparable(prev[i], enrich_ids, True)]
    disputed = sorted(i for i, it in cur.items() if it["agreement"]["state"] == "disputed")
    single = sorted(i for i, it in cur.items() if it["agreement"]["state"] == "single_channel")
    caps = topic["caps"]
    flags = []
    if first:
        flags.append("first_publish")
    if refresh:
        flags.append("refresh_only")
    if len(removed) > caps["max_removed"]:
        flags.append("removed_over_cap")
    if not first and len(new) > caps["max_new"]:
        flags.append("new_over_cap")
    if len(c.items_to_ndjson(items)) > caps["max_items_bytes"]:
        flags.append("items_over_size")
    if invalid:
        flags.append("invalid_items")
    if disputed:
        flags.append("disputed_items")
    flags.extend(extra_flags)
    return {"new": new, "removed": removed, "updated": updated, "disputed": disputed, "single_channel": single,
            "invalid": [{"id": i, "field": f} for i, f in invalid],
            "counts": {"items": len(items), "published_items": len(prev), "new": len(new), "removed": len(removed),
                       "updated": len(updated), "updated_epss_only": len(epss_only), "disputed": len(disputed),
                       "single_channel": len(single), "invalid": len(invalid)},
            "flags": flags}


def report_text(topic_name, cid, manifest, diff, sha12):
    """Deterministic human-readable summary: ids and counts only."""
    n = diff["counts"]
    out = [f"statefeed {topic_name}: candidate {cid} (seq {manifest['seq']}, snapshot {manifest['snapshot']})",
           f"generated {manifest['generated_at']}, valid until {manifest['valid_until']}",
           f"items {n['items']} (published {n['published_items']}): +{n['new']} new, -{n['removed']} removed, ~{n['updated']} updated "
           f"({n['updated_epss_only']} only in EPSS), {n['disputed']} disputed, {n['single_channel']} single channel, {n['invalid']} invalid",
           "flags: " + (", ".join(diff["flags"]) or "none"), "", "sources:"]
    for s in manifest["sources"]:
        out.append(f"  {s['id']}: {s['status']}, {s['bytes']} bytes, sha256 {(s['content_sha256'] or '-')[:12]}")
    for key, title in (("new", "new"), ("removed", "removed"), ("updated", "updated"), ("disputed", "disputed"), ("single_channel", "single channel")):
        ids = diff[key]
        if ids:
            more = f" (+{len(ids) - LIST_CAP} more)" if len(ids) > LIST_CAP else ""
            out += ["", f"{title} ({len(ids)}){more}:"] + [f"  {i}" for i in ids[:LIST_CAP]]
    if diff["invalid"]:
        out += ["", f"invalid ({len(diff['invalid'])}), left out:"] + [f"  {e['id']} field {e['field']}" for e in diff["invalid"][:LIST_CAP]]
    out += ["", f"approve with: python3 ~/aibridge/ops/statefeed/publish.py approve {topic_name} {cid} --sha {sha12}"
                + (" --accept-flags" if diff["flags"] else "")]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ the build

def prune_candidates(name):
    base = c.candidates_dir(name)
    for d in os.listdir(base):
        if d.startswith(".tmp-"):
            shutil.rmtree(os.path.join(base, d), ignore_errors=True)
    done = sorted(d for d in os.listdir(base) if c.CAND_RE.fullmatch(d) and os.path.isdir(os.path.join(base, d)))
    for d in done[:-KEEP_CANDIDATES]:
        shutil.rmtree(os.path.join(base, d), ignore_errors=True)


def run(name, dry_run=False):
    """-> exit code. Prints the report; raises ConfigError or BuildError for failures."""
    topic = c.load_topic(name)
    tbytes = c.topic_config_bytes(name)
    srcs = topic["sources"]
    for s in srcs:
        if (s["role"] == "enrich") != (s["kind"] == "epss_csv_gz"):
            raise BuildError(f"source {s['id']}: role {s['role']} does not fit kind {s['kind']}")
    primary = next(s for s in srcs if s["role"] == "primary")
    if primary["kind"] != "kev_json":
        raise BuildError("the primary source must be a KEV catalog")
    enrich = [s for s in srcs if s["role"] == "enrich"]
    if len(enrich) > 1:
        raise BuildError("at most one enrichment source is supported")
    for p in (c.statefeed_home(), c.topic_dir(name), c.candidates_dir(name), c.cache_dir(name)):
        c.ensure_private_dir(p)

    published = load_published(name)
    prev = published["items"] if published else {}
    fetched = {s["id"]: fetch_source(topic, s) for s in srcs}
    flags = []
    if fetched[primary["id"]].status == "unavailable":
        raise BuildError(f"primary source {primary['id']} is unavailable ({fetched[primary['id']].error}) and has no recent cache")

    channels = []
    for s in [primary] + [x for x in srcs if x["role"] == "channel"]:
        fr = fetched[s["id"]]
        try:
            if fr.status == "unavailable":
                raise ValueError("unavailable")
            records, bad = read_channel(s["id"], parse_kev(fr.body))
        except ValueError:
            if s is primary:
                raise BuildError(f"primary source {s['id']} does not parse")
            flags.append(f"source_unavailable:{s['id']}")
            continue
        channels.append((s, fr, records, bad))
    invalid = {x for *_, bad in channels for x in bad}
    channels = [(s, fr, recs) for s, fr, recs, _ in channels]

    epss = None
    for s in enrich:
        fr = fetched[s["id"]]
        try:
            if fr.status == "unavailable":
                raise ValueError("unavailable")
            wanted = {cid for _, _, recs in channels for cid in recs}
            epss = (s, fr, parse_epss(fr.body, 4 * s["max_bytes"], wanted))
        except ValueError:
            epss = ("carry", s)
            flags.append(f"source_unavailable:{s['id']}")
    flags += [f"source_unavailable:{s['id']}" for s in srcs if fetched[s["id"]].status == "unavailable" and f"source_unavailable:{s['id']}" not in flags]

    ts = c.now()
    items, bad_items = compile_items(topic, channels, epss, prev, c.today_str(ts))
    invalid = sorted(invalid | set(bad_items))
    enrich_ids = {s["id"] for s in enrich}
    first = published is None
    unchanged = (not first and set(prev) == {i["id"] for i in items}
                 and all(comparable(i, enrich_ids) == comparable(prev[i["id"]], enrich_ids) for i in items))
    refresh = False
    if unchanged:
        left = c.parse_iso(published["manifest"]["valid_until"]) - int(ts)
        if left > REFRESH_WITHIN_S:
            print(f"statefeed {name}: nothing changed since seq {published['manifest']['seq']}; no candidate"
                  + (f" ({len(invalid)} invalid entries left out)" if invalid else ""))
            return 0
        refresh = True
    diff = make_diff(topic, items, invalid, prev, sorted(set(flags)), first, refresh)

    seq = published["manifest"]["seq"] + 1 if published else 1
    ib = c.items_to_ndjson(items)
    snap = c.snap_id(seq, ts)
    manifest = {
        "topic": name, "schema_version": c.SCHEMA_VERSION, "seq": seq, "prev_digest": published["digest"] if published else None,
        "generated_at": c.iso(ts), "valid_until": c.iso_plus_days(ts, topic["valid_days"]), "item_count": len(items),
        "untrusted_text": False, "ai_generated": False, "compiled_by": COMPILED_BY, "licence": dict(LICENCE),
        "check_set_version": c.sha256_bytes(open(os.path.abspath(__file__), "rb").read() + tbytes)[:12],
        "sources": [{"id": s["id"], "url": s["url"],
                     "retrieved_at": None if fetched[s["id"]].status == "unavailable" else c.iso(fetched[s["id"]].retrieved_at),
                     "content_sha256": fetched[s["id"]].sha256, "bytes": fetched[s["id"]].size, "status": fetched[s["id"]].status}
                    for s in srcs],
        "files": [{"path": f"{c.FEED_PREFIX}/snapshots/{snap}/items.ndjson", "sha256": c.sha256_bytes(ib), "bytes": len(ib)}],
        "snapshot": snap, "publish_record": {"approval": "human"}}
    errs = c.validate_manifest(manifest)
    parsed, ierrs = c.parse_items_ndjson(ib)
    if errs or ierrs:
        raise BuildError("internal error, the candidate does not validate: " + "; ".join((errs + ierrs)[:3]))
    mb = c.canonical_json(manifest)
    sha12 = c.sha256_bytes(mb)[:12]
    cid = c.cand_id(ts)
    report = report_text(name, cid, manifest, diff, sha12)
    print(report, end="")
    if dry_run:
        print("(dry run: nothing written, nothing sent)")
        return 0

    base = c.candidates_dir(name)
    final, tmp = os.path.join(base, cid), os.path.join(base, ".tmp-" + cid)
    if os.path.exists(final):
        raise BuildError(f"candidate {cid} already exists")
    shutil.rmtree(tmp, ignore_errors=True)
    c.ensure_private_dir(tmp)
    c.write_private(os.path.join(tmp, "items.ndjson"), ib)
    c.write_private(os.path.join(tmp, "manifest.json"), mb)
    c.write_private(os.path.join(tmp, "diff.json"), json.dumps(diff, indent=1, sort_keys=True) + "\n")
    c.write_private(os.path.join(tmp, "report.txt"), report)
    os.rename(tmp, final)
    prune_candidates(name)
    n = diff["counts"]
    c.notify(f"statefeed {name}: candidate {cid} ready (seq {seq}): +{n['new']} new, -{n['removed']} removed, "
             f"~{n['updated']} updated, {n['disputed']} disputed; flags: {', '.join(diff['flags']) or 'none'}; "
             f"approve with: python3 ~/aibridge/ops/statefeed/publish.py approve {name} {cid} --sha {sha12}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build a statefeed candidate (no secrets, never publishes).")
    ap.add_argument("--topic", required=True)
    ap.add_argument("--dry-run", action="store_true", help="print the report; write nothing, send nothing")
    a = ap.parse_args(argv)
    try:
        return run(a.topic, a.dry_run)
    except (c.ConfigError, BuildError) as e:
        print(f"statefeed build: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"statefeed build: file error ({type(e).__name__}: {e.strerror or e})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
