# Status, portal list and setup review (job-search)

## "Is the search working? Where does it look?" (status, portals, last runs)

Plan first, then run these in order; they answer where it searches, when it last ran, how many it found and what failed,
in a few calls:
1. `cd /workdir/jobfinder && node stats.mjs --summary`: runs, scanner, portals, tracker in one table
   (`--prune` adds read-only advice on portals that never yield anything).
2. `tail -n 5 data/scan-runs.tsv`: the last scans (columns: timestamp, status, companies, boards, found, filtered_*,
   dupes, new_added, errors).
3. `tail -n 40 data/portal-health.tsv`: each portal's last outcome (`timestamp company status`); `slug_gone` and
   `empty` are blind spots worth telling the person about.
4. Only if the person wants the list checked: `node validate-portals.mjs` (shape, offline), `node audit-portals.mjs
   --summary` (one line per enabled company; asks each site, takes minutes: say so first), `node verify-portals.mjs`
   (which ATS slugs still resolve).

**Never write your own parser for `portals.yml`.** The scripts above already read it, and there is no `yq` and no
`pip install`. On 2026-11-13 an agent spent ten calls writing parsers one after the other.
**Changing the list**: `node select-portals.mjs --regions ... --sectors ... --summary` to preview, then add `--into
portals.yml --write` (it keeps a `.bak`). Never rewrite the file by hand: an agent once collapsed 151 companies to 11.

## Setup review (when it helps, never on a calendar)

A tool for you, not a routine for the person. Use it when they ask to improve their search, CV or pipeline, or when you notice
them doing the same work by hand again and again (the same sites every day, stale rows they keep skipping): then offer it in one
line, as a way to save them that time. Never offer it on a schedule.

- Read-only checks (they change nothing): `node cv-sync-check.mjs`, `node evidence-freshness.mjs`,
  `node check-table-freshness.mjs --summary`, `node close-stale.mjs --summary`, `node dedup-tracker.mjs --dry-run`,
  `node validate-portals.mjs`, `node discover-new-companies.mjs`, plus their own trackers in `data/`.
- Propose at most 3 concrete improvements, the most time-saving first (a CV line to update and why, stale rows to close,
  duplicates, a filter, a company to track). Sites they check by hand: add them to `portals.yml` when it is a supported board;
  otherwise list them, one per line with the address, in `data/manual-sources.md`, so a night check can cover them later.
- Change nothing without their yes, one change at a time, a dated copy first (as for `portals.yml`).
