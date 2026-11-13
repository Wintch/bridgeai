#!/usr/bin/env python3
"""statefeed build: fetch the sources of one topic, compare them, validate, and write a CANDIDATE for a human to approve.

    python3 -I ~/aibridge/ops/statefeed/build.py --topic vulns [--dry-run]

Needs no secret and never publishes anything: it writes <STATEFEED_HOME>/<topic>/candidates/<cand_id>/ with
  kev.csv        one row per KEV entry: cve, date_added, kev_sha, epss, epss_pct, flag (no text copied from any source)
  manifest.json  the unsigned manifest (publish.py signs it after approval; an approval is bound to its exact bytes)
  diff.json      what changed against the last published snapshot, plus the flags that need --accept-flags
  report.txt     the same as text, and how to approve
and sends ONE ops-bot message (ids and counts only). The source list comes only from topics/<topic>.json (committed), never
from data; the mirror list the manifest advertises comes only from the local, non-secret <conf>/<topic>.json. For the vulns topic
the compiled data is the CISA KEV catalog read through two channels (CISA and the cisagov GitHub mirror; one `group`, so they
count as ONE independent source: their agreement, a kev_sha comparison per CVE, detects a tampered or broken download, not an
error of the authority itself) plus EPSS scores from FIRST. Revisitable choices: see STATEFEED.md.

How a candidate is decided
  * KEV primary unavailable (download failed, no cache younger than 2 days): exit 1, no candidate. Another source that is
    unavailable becomes the flag source_unavailable:<id>; an unavailable EPSS keeps the last published EPSS values (the manifest's
    epss.score_date shows how old they are).
  * A candidate is made when the KEV delta against the published snapshot is not empty (an entry added, removed, or with a
    different kev_sha), when the published manifest runs out within 1 day (a refresh, flag refresh_only; it carries the latest
    EPSS), or on the first publish. An EPSS-only change never makes a candidate by itself. Otherwise: nothing to do, exit 0.
  * A KEV entry whose cve or date_added fails its column pattern (or that cannot be fingerprinted) is never repaired: it is left
    out, listed in diff.json under `invalid`, and the candidate gets the flag invalid_items.
  * The manifest's `delta` lists at most 50 ids per list; beyond that (first publish, catalog re-issue) it says full=true with
    counts. It also falls back to that form when the explicit lists would push manifest.json + signature over 3,500 bytes.
Flags (publish.py approve then needs --accept-flags): first_publish, refresh_only, removed_over_cap, new_over_cap,
items_over_size, invalid_items, disputed_items, source_unavailable:<id>.
Exit codes: 0 candidate written or nothing to do, 1 failure (config, primary source, published state, manifest over the size
cap), 2 usage.
"""
import argparse, ipaddress, json, os, re, shutil, sys, urllib.parse, zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from statefeed import common as c

KEEP_CANDIDATES = 7
REFRESH_WITHIN_S = 86400          # a published manifest that runs out within this long gets a refresh candidate
LIST_CAP = 30                     # ids per list in report.txt
SCORE_DATE_RE = re.compile(r"score_date:([0-9]{4}-[0-9]{2}-[0-9]{2})")
MODEL_VERSION_RE = re.compile(r"model_version:([0-9A-Za-z._:+-]{1,40})(?=,|$)")
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


def kev_ref(catalog):
    """The manifest `ref` of a KEV channel: {"catalog_version", "date_released"}, or None when the catalog gives no usable version
    (plain strings from a restricted alphabet only: a hostile value is dropped, never copied)."""
    cv, dr = catalog.get("catalogVersion"), catalog.get("dateReleased")
    if not (isinstance(cv, str) and c.REF_VALUE_RE.fullmatch(cv)):
        return None
    return {"catalog_version": cv, "date_released": dr if isinstance(dr, str) and c.REF_VALUE_RE.fullmatch(dr) else None}


def read_channel(sid, catalog):
    """-> (records {cve: {"date_added", "kev_sha"}}, invalid [(label, column)]). An entry with a bad cve or date_added, or one that
    cannot be fingerprinted, is invalid and left out; an id listed twice with different content is invalid too (and dropped from
    this channel). An entry is named in `invalid` by its CVE id when that is well formed, else by source and position."""
    records, invalid, conflict = {}, [], set()
    for n, e in enumerate(catalog["vulnerabilities"], 1):
        cid = e.get("cveID") if isinstance(e, dict) else None
        if not (isinstance(cid, str) and not c.column_problem("cve", cid)):
            invalid.append((f"{sid}#{n}", "cve"))
            continue
        if c.column_problem("date_added", e.get("dateAdded")):
            invalid.append((cid, "date_added"))
            continue
        try:
            rec = {"date_added": e["dateAdded"], "kev_sha": c.kev_sha(e)}
        except ValueError:
            invalid.append((cid, "kev_sha"))
            continue
        if cid in records and records[cid] != rec:
            conflict.add(cid)
        else:
            records[cid] = rec
    for cid in sorted(conflict):
        records.pop(cid, None)
        invalid.append((cid, "cve"))
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
    """EPSS csv.gz bytes -> {"date": "YYYY-MM-DD", "model_version": text, "rows": n, "bad": n, "scores": {cve: (epss, percentile)}}
    with the two scores as the file's own text (checked against c.EPSS_TEXT_RE, never converted). The first line is a comment
    `#model_version:...,score_date:<ISO time>`, then the header `cve,epss,percentile`. Only the CVEs in `wanted` are kept (all when
    None). A row that does not fit (bad id, a score that is not plain 0..1 text, too few columns) is counted in `bad`. ValueError
    when the structure is wrong (no model_version or score_date, no header, no valid row, truncated)."""
    date, model, header, rows, bad, scores = None, None, False, 0, 0, {}
    for raw in _gz_lines(body, cap):
        line = raw.decode("utf-8").strip()
        if not line:
            continue
        if line.startswith("#"):
            m = SCORE_DATE_RE.search(line) if date is None else None
            if m and c.parse_date(m[1]):
                date = m[1]
            m = MODEL_VERSION_RE.search(line) if model is None else None
            if m:
                model = m[1]
            continue
        parts = [x.strip() for x in line.split(",")]
        if not header:
            if [x.lower() for x in parts[:3]] != ["cve", "epss", "percentile"]:
                raise ValueError("unexpected EPSS header")
            header = True
            continue
        try:
            cve, e, p = parts[0].upper(), parts[1], parts[2]
        except IndexError:
            bad += 1
            continue
        if not (c.CVE_RE.fullmatch(cve) and c.EPSS_TEXT_RE.fullmatch(e) and c.EPSS_TEXT_RE.fullmatch(p)):
            bad += 1
            continue
        rows += 1
        if wanted is None or cve in wanted:
            scores[cve] = (e, p)
    if date is None:
        raise ValueError("EPSS file without score_date")
    if model is None:
        raise ValueError("EPSS file without model_version")
    if not header or rows == 0:
        raise ValueError("EPSS file without rows")
    return {"date": date, "model_version": model, "rows": rows, "bad": bad, "scores": scores}


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
    """The last published snapshot kept by publish.py in <home>/<topic>/published/ (manifest.json and kev.csv), or None when there
    is none. -> {"manifest", "digest" (sha256 of the manifest bytes), "rows" {cve: row}}. BuildError when it is damaged: a build
    must not restart the sequence by accident."""
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
        with open(os.path.join(d, c.KEV_DATA_FILE), "rb") as f:
            cb = f.read()
    except (OSError, ValueError) as e:
        raise BuildError(f"published state is unreadable ({type(e).__name__})")
    if [f["sha256"] for f in m["files"]] != [c.sha256_bytes(cb)]:
        raise BuildError(f"published {c.KEV_DATA_FILE} does not match its manifest")
    rows, errs = c.parse_kev_csv(cb)
    if errs:
        raise BuildError(f"published {c.KEV_DATA_FILE} is invalid: " + errs[0])
    return {"manifest": m, "digest": c.sha256_bytes(mb), "rows": {r["cve"]: r for r in rows}}


# ------------------------------------------------------------------ compiling rows

def compile_rows(channels, epss, prev):
    """channels: [(source, FetchResult, records)] primary first; epss: None, (source, FetchResult, parsed) or ("carry", source);
    prev: {cve: published row}. -> (rows [valid rows, sorted], invalid [(cve, column)]).
    The row's kev_sha and date_added come from the first channel that carries the CVE (the primary when it does). flag: a CVE only
    one channel carries is single_channel; one whose kev_sha differs between channels is disputed."""
    ids = sorted({cid for _, _, recs in channels for cid in recs}, key=c.cve_sort_key)
    rows, invalid = [], set()
    for cid in ids:
        present = [recs[cid] for _, _, recs in channels if cid in recs]
        base = present[0]
        flag = "single_channel" if len(present) == 1 else ("disputed" if any(r["kev_sha"] != base["kev_sha"] for r in present[1:]) else "")
        e = p = ""
        if epss and epss[0] == "carry":                  # EPSS unavailable: keep what was published (the manifest keeps its date)
            old = prev.get(cid)
            if old:
                e, p = old["epss"], old["epss_pct"]
        elif epss:
            e, p = epss[2]["scores"].get(cid, ("", ""))
        row = {"cve": cid, "date_added": base["date_added"], "kev_sha": base["kev_sha"], "epss": e, "epss_pct": p, "flag": flag}
        problems = c.row_problems(row)
        if problems:
            invalid.update((cid, col) for col, _ in problems)
        else:
            rows.append(row)
    return rows, sorted(invalid)


def delta_lists(prev, cur):
    """-> (added, removed, changed): sorted CVE id lists of the KEV changes between two {cve: row} maps. changed = kev_sha differs.
    EPSS and flag never count."""
    key = c.cve_sort_key
    return (sorted(set(cur) - set(prev), key=key), sorted(set(prev) - set(cur), key=key),
            sorted((i for i in cur if i in prev and cur[i]["kev_sha"] != prev[i]["kev_sha"]), key=key))


def make_delta(since_seq, lists, full=False):
    """The manifest `delta`. The three lists when since_seq is known and none is longer than c.DELTA_MAX_IDS and full is not
    forced; otherwise {"since_seq", "full": true, "counts"}."""
    added, removed, changed = lists
    if full or since_seq is None or max(len(added), len(removed), len(changed)) > c.DELTA_MAX_IDS:
        return {"since_seq": since_seq, "full": True, "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)}}
    return {"since_seq": since_seq, "added": added, "removed": removed, "changed": changed}


def make_diff(topic, rows, invalid, prev, lists, epss_changed, csv_len, extra_flags, first, refresh):
    """-> diff dict (see the module docstring). `prev` is {cve: row} (empty on the first publish). Keys: new, removed, updated (KEV
    entry changed), disputed, single_channel (CVE lists, uncapped), invalid ([{id, field}]), counts, flags."""
    new, removed, updated = lists
    disputed = [r["cve"] for r in rows if r["flag"] == "disputed"]
    single = [r["cve"] for r in rows if r["flag"] == "single_channel"]
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
    if csv_len > caps["max_items_bytes"]:
        flags.append("items_over_size")
    if invalid:
        flags.append("invalid_items")
    if disputed:
        flags.append("disputed_items")
    flags.extend(extra_flags)
    return {"new": new, "removed": removed, "updated": updated, "disputed": disputed, "single_channel": single,
            "invalid": [{"id": i, "field": f} for i, f in invalid],
            "counts": {"items": len(rows), "published_items": len(prev), "new": len(new), "removed": len(removed),
                       "updated": len(updated), "epss_changed": epss_changed, "disputed": len(disputed),
                       "single_channel": len(single), "invalid": len(invalid)},
            "flags": flags}


def report_text(topic_name, cid, manifest, diff, sha12):
    """Deterministic human-readable summary: ids and counts only."""
    n = diff["counts"]
    out = [f"statefeed {topic_name}: candidate {cid} (seq {manifest['seq']}, snapshot {manifest['snapshot']})",
           f"generated {manifest['generated_at']}, valid until {manifest['valid_until']}",
           f"rows {n['items']} (published {n['published_items']}): +{n['new']} new, -{n['removed']} removed, ~{n['updated']} updated "
           f"(kev_sha changed), {n['disputed']} disputed, {n['single_channel']} single channel, {n['invalid']} invalid; "
           f"EPSS differs on {n['epss_changed']} rows",
           "delta in the manifest: " + ("full (readers diff the csv)" if manifest["delta"].get("full") else "explicit lists"),
           "flags: " + (", ".join(diff["flags"]) or "none"), "", "sources:"]
    for s in manifest["sources"]:
        out.append(f"  {s['id']}: {s['status']}, {s['bytes']} bytes, sha256 {(s['content_sha256'] or '-')[:12]}")
    if manifest.get("mirrors"):
        out += ["", "mirrors listed: " + ", ".join(m["id"] for m in manifest["mirrors"])]
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
    mirrors = c.load_local_settings(name)["mirrors"]
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
    prev = published["rows"] if published else {}
    fetched = {s["id"]: fetch_source(topic, s) for s in srcs}
    flags, refs = [], {}
    if fetched[primary["id"]].status == "unavailable":
        raise BuildError(f"primary source {primary['id']} is unavailable ({fetched[primary['id']].error}) and has no recent cache")

    channels = []
    for s in [primary] + [x for x in srcs if x["role"] == "channel"]:
        fr = fetched[s["id"]]
        try:
            if fr.status == "unavailable":
                raise ValueError("unavailable")
            catalog = parse_kev(fr.body)
            records, bad = read_channel(s["id"], catalog)
        except ValueError:
            if s is primary:
                raise BuildError(f"primary source {s['id']} does not parse")
            flags.append(f"source_unavailable:{s['id']}")
            continue
        refs[s["id"]] = kev_ref(catalog)
        channels.append((s, fr, records, bad))
    invalid = {x for *_, bad in channels for x in bad}
    channels = [(s, fr, recs) for s, fr, recs, _ in channels]

    epss, epss_block = None, None
    for s in enrich:
        fr = fetched[s["id"]]
        try:
            if fr.status == "unavailable":
                raise ValueError("unavailable")
            wanted = {cid for _, _, recs in channels for cid in recs}
            epss = (s, fr, parse_epss(fr.body, 4 * s["max_bytes"], wanted))
            epss_block = {"model_version": epss[2]["model_version"], "score_date": epss[2]["date"]}
            refs[s["id"]] = dict(epss_block)
        except ValueError:
            epss = ("carry", s)
            epss_block = published["manifest"]["epss"] if published else None
            flags.append(f"source_unavailable:{s['id']}")
    flags += [f"source_unavailable:{s['id']}" for s in srcs if fetched[s["id"]].status == "unavailable" and f"source_unavailable:{s['id']}" not in flags]

    ts = c.now()
    rows, bad_rows = compile_rows(channels, epss, prev)
    invalid = sorted(invalid | set(bad_rows))
    cur = {r["cve"]: r for r in rows}
    first = published is None
    lists = delta_lists(prev, cur)
    refresh = False
    if not first and not any(lists):
        left = c.parse_iso(published["manifest"]["valid_until"]) - int(ts)
        if left > REFRESH_WITHIN_S:
            print(f"statefeed {name}: nothing changed in KEV since seq {published['manifest']['seq']}; no candidate"
                  + (f" ({len(invalid)} invalid entries left out)" if invalid else ""))
            return 0
        refresh = True
    epss_changed = sum(1 for i, r in cur.items() if i in prev and (r["epss"], r["epss_pct"]) != (prev[i]["epss"], prev[i]["epss_pct"]))
    csv = c.rows_to_csv(rows)
    diff = make_diff(topic, rows, invalid, prev, lists, epss_changed, len(csv), sorted(set(flags)), first, refresh)

    seq = published["manifest"]["seq"] + 1 if published else 1
    since = published["manifest"]["seq"] if published else None
    snap = c.snap_id(seq, ts)

    def assemble(delta):
        m = {"topic": name, "schema_version": c.SCHEMA_VERSION, "seq": seq, "prev_digest": published["digest"] if published else None,
             "generated_at": c.iso(ts), "valid_until": c.iso_plus_days(ts, topic["valid_days"]), "item_count": len(rows),
             "untrusted_text": False, "ai_generated": False, "compiled_by": COMPILED_BY, "licence": dict(LICENCE),
             "check_set_version": c.sha256_bytes(open(os.path.abspath(__file__), "rb").read() + tbytes)[:12],
             "sources": [{"id": s["id"], "url": s["url"],
                          "retrieved_at": None if fetched[s["id"]].status == "unavailable" else c.iso(fetched[s["id"]].retrieved_at),
                          "content_sha256": fetched[s["id"]].sha256, "bytes": fetched[s["id"]].size, "status": fetched[s["id"]].status,
                          "ref": refs.get(s["id"])}
                         for s in srcs],
             "files": [{"path": f"{c.FEED_PREFIX}/snapshots/{snap}/{c.KEV_DATA_FILE}", "sha256": c.sha256_bytes(csv), "bytes": len(csv)}],
             "snapshot": snap, "publish_record": {"approval": "human"},
             "format": c.kev_format(), "delta": delta, "epss": epss_block}
        if mirrors:
            m["mirrors"] = [dict(x) for x in mirrors]
        return m

    manifest = assemble(make_delta(since, lists))
    if "added" in manifest["delta"] and c.manifest_size_problem(manifest):
        manifest = assemble(make_delta(since, lists, full=True))          # too many ids for the size cap: readers diff the csv
    errs = c.validate_manifest(manifest)
    cparsed, cerrs = c.parse_kev_csv(csv)
    if errs or cerrs:
        raise BuildError("internal error, the candidate does not validate: " + "; ".join((errs + cerrs)[:3]))
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
    c.write_private(os.path.join(tmp, c.KEV_DATA_FILE), csv)
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
