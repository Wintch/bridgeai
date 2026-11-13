# kev.csv: column specification (statefeed schema version 2)

`kev.csv` is the data file of a snapshot (`v1/snapshots/<snapshot>/kev.csv`). It lists which CISA KEV entries exist, when they were
added, a fingerprint of each entry, and the EPSS score. It copies no text from the source: to learn what a vulnerability is, read
the KEV catalog (the primary source) and the vendor advisory.

## File format

- UTF-8, `\n` line ends, a final newline, no byte order mark.
- First line, exactly: `cve,date_added,kev_sha,epss,epss_pct,flag`
- One row per KEV entry, sorted by `cve` (year first, then the number as a number), no duplicates.
- No quoting, ever. No column can hold a comma, quote or newline, because every column is a strict pattern:

| column | pattern | meaning |
|---|---|---|
| `cve` | `^CVE-[0-9]{4}-(0[0-9]{3}\|[1-9][0-9]{3,6})$` (ASCII digits; a number of 5 or more digits never starts with 0, so every number has one spelling) | CVE id of the KEV entry |
| `date_added` | `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`, a real calendar date | KEV `dateAdded` |
| `kev_sha` | `^[0-9a-f]{16}$` | fingerprint of the entry, see below |
| `epss` | `^(0(\.[0-9]{1,6})?\|1(\.0{1,6})?)$` or empty | EPSS probability, the text of the EPSS file, verbatim |
| `epss_pct` | same pattern, or empty | EPSS percentile, verbatim |
| `flag` | empty, `disputed` or `single_channel` | `disputed`: the two KEV channels carry this CVE with different `kev_sha`. `single_channel`: only one channel carried it |

`epss` and `epss_pct` are both set or both empty (empty: the CVE has no EPSS row).

## kev_sha (rule `kev-entry-sha256-16/v1`)

The first 16 hex characters of the SHA-256 of the KEV entry object (all its fields, exactly as the primary channel published it),
written as `json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`. In words, for a
reader who does not use Python:

- the entry is the JSON object of one element of the catalog's `vulnerabilities` array, every field, none added or dropped;
- keys sorted by Unicode code point (all keys must be ASCII, so UTF-16 order agrees), no spaces after `,` or `:`, no trailing newline;
- strings are written raw as UTF-8 and escaped only as JSON requires (`\"`, `\\`, and `\n`, `\r`, `\t`, `\b`, `\f` or `\u00xx` in lower case
  for control characters). Non-ASCII characters stay as they are. No Unicode normalisation is applied;
- numbers: integers only, written in plain decimal, within plus or minus 9007199254740991. The catalog has no numbers today;
- an entry that holds a float, a larger integer, a non-ASCII key or a string that is not valid Unicode gets no fingerprint:
  the feed leaves it out and flags it (`invalid_items`) instead of publishing a value nobody else could recompute;
- duplicate keys inside an object are refused when the catalog is read.

The manifest repeats the rule in `format`. A reader who fetches the KEV catalog itself can recompute it for any entry; a different value means the
entry changed or this feed is wrong. Compare against the primary source before acting on anything.

## What the manifest adds

`delta` (KEV changes since the previous snapshot: `added`, `removed`, `changed` = `kev_sha` differs; at most 50 ids per list, else
`full: true` and the counts), `epss` (model version and score date), `sources[].ref` (KEV `catalogVersion` and `dateReleased` of
each channel, EPSS model version and score date), and an optional `mirrors` list. See `manifest.2.json`.
