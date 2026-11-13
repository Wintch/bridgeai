# statefeed: a signed, public data feed compiled by code

statefeed turns a public upstream list into a small, signed, static data feed that anyone (including other people's agents) can read, check and cache. It has one topic, `vulns`: which entries the CISA Known Exploited Vulnerabilities catalog (KEV) holds, a fingerprint of each entry, and the EPSS score. Everything is compiled by code. A human approves every publish. No AI writes or edits any byte of it.

This is format version 1.1 (manifest `schema_version` 2). It replaced a first design that copied labels from the source into the feed (see "Why the feed does not copy the source").

The feed is data for machines. It is served from Cloudflare Pages, which is the primary host, and the signed manifest lists the other places the same files can be fetched from, so the feed stays readable when any one machine or host is offline.

## Why the feed does not copy the source

Whoever reads this feed, an AI agent or a person, has to check every fact against the primary source before acting on it: the KEV entry and the vendor advisory say what a vulnerability is and whether it matters. A copy of the source inside the feed adds nothing to that check, and it adds risks (third-party text reaching a reader, label rules that reject real catalog entries, a licence question). So the feed says only three things: what to look at, what changed, and how to check it.

| Choice | Reason |
|---|---|
| Every entry of KEV, not a subset | Coverage does not depend on any private profile, so the feed reveals nothing about who runs it or what they run. Matching against local software happens on the consumer's side. |
| No prose and no labels: only CVE id, date added, a fingerprint, EPSS | Nothing to inject, nothing to reject. The old vendor/product/name labels and their character rules are gone, together with the invalid entries they caused on real catalog text. Every column of `kev.csv` has a strict pattern. |
| A fingerprint per entry (`kev_sha`) instead of the entry | A reader who fetches the catalog recomputes the fingerprint and sees at once whether the entry changed since the feed, or whether the feed is wrong. |
| A delta in the signed manifest | A reader that already holds the previous snapshot sees which CVEs were added, removed or changed without diffing the file. |
| Signed list of other places to fetch from | The same public data must be reachable everywhere. The list is covered by the signature, so a mirror cannot add itself. |
| No AI anywhere in this topic | There is no model, no barrier bot and no skill. The manifest says so (`ai_generated: false`, `untrusted_text: false`) and a consumer can refuse a feed that says otherwise. |
| Human approval for every publish | The person who runs the feed reads a diff summary and binds the approval to the exact manifest bytes. |
| One signed manifest over immutable snapshots | A consumer never straddles a deploy, and a rollback is just a newer, signed manifest. |
| No key fingerprint in the manifest | A signer vouching for its own key adds no trust. The reader's own `allowed_signers` file decides. |

The topic definition is `topics/vulns.json`. It is public, committed, and never derived from any private profile. Source URLs come only from this file, never from fetched data.

## Sources and their licences

| Source id | What | Group | Role | Licence |
|---|---|---|---|---|
| `kev-cisa` | CISA KEV catalog (JSON) | `cisa` | primary | CC0 1.0 |
| `kev-github` | the `cisagov/kev-data` mirror of the same catalog | `cisa` | channel | CC0 1.0 |
| `epss` | daily EPSS scores (CSV, gzip) | `first` | enrich | free to use with attribution to FIRST |

Each source entry in `topics/vulns.json` carries `terms_checked_on`, the date someone last read its terms. Re-check the terms when adding or changing a source, and when that date is old. The EPSS URL redirects to a dated file; the fetcher follows redirects only to https on `empiricalsecurity.com` and refuses any other host. The user agent is honest: `statefeed/1 (bridgeai; +https://github.com/Wintch/bridgeai)`. Downloads use conditional requests and a cache; a failed download may be replaced by a cache younger than two days, otherwise that source is `unavailable`. If the KEV primary is unavailable the build fails with no candidate.

The output compilation is licensed CC BY 4.0 (`LICENSE.txt`), facts are not claimed, and the manifest's `licence` field summarises the licences (`sources` names each source and the version read). `NOTICE.txt` carries the attributions and the "not endorsed by CISA" and "not endorsed by FIRST" lines. This is a default and can be revisited.

## Agreement between channels: what two channels prove

Sources in the same `group` count as ONE independent source. `kev-cisa` and `kev-github` are the same authority over two distribution channels. Their agreement therefore detects channel tampering and broken downloads; it does not detect an error or compromise of the authority itself. It is not a second opinion.

The comparison is one `kev_sha` per CVE and channel, so any difference in the entry counts, including an edit of a description. It shows in the `flag` column of `kev.csv`:

| `flag` | Meaning |
|---|---|
| empty | both KEV channels carry the CVE with the same `kev_sha` (or only one channel is configured) |
| `single_channel` | one channel carries the CVE; the other lacks it or was unavailable |
| `disputed` | both channels carry the CVE but their `kev_sha` differ |

A consumer must not read an empty flag as "verified by two organisations". The row's `kev_sha` and `date_added` come from the primary channel when it carries the CVE.

## Bundle layout on Pages

```
/index.html  /robots.txt  /_headers  /LICENSE.txt  /NOTICE.txt
/v1/latest/manifest.json            the newest signed manifest (no-cache)
/v1/latest/manifest.json.sig        its SSHSIG signature
/v1/snapshots/<YYYY-MM-DD-seq>/manifest.json
/v1/snapshots/<YYYY-MM-DD-seq>/manifest.json.sig
/v1/snapshots/<YYYY-MM-DD-seq>/kev.csv           immutable, cached for a year
/v1/schema/manifest.2.json  /v1/schema/kev.csv.md
/v1/allowed_signers                 convenience copy of the public key line; consumers pin their own
```

The manifest's `files[].path` names the immutable snapshot path, never `latest`. Snapshots beyond `retention_snapshots` (60) are pruned, oldest first. Only these file types are deployed: `index.html` (the only HTML, no scripts, no external resources), `.txt`, `.json`, `.csv`, `.md`, `.sig`, `_headers` and `allowed_signers`. `_headers` sets `nosniff`, a `default-src 'none'` content security policy, no referrer, `no-cache` for `latest`, long immutable caching for snapshots, and a plain-text content type for `.csv` and `.md`.

The `index.html` footer lists the mirrors of the signed manifest and prints the signing key as an `allowed_signers` line with its fingerprint. Both come from the operator's LOCAL configuration (the mirrors from the signed manifest after publish checked it equals the local list), never from fetched data. The page tells readers to compare the fingerprint with the one their own `ssh-keygen -lf` prints for the key they received out of band, and never to take the key from a mirror.

## The data file: kev.csv

UTF-8, `\n` line ends, a final newline. The first line is exactly `cve,date_added,kev_sha,epss,epss_pct,flag`. One row per KEV entry, sorted by `cve` (year first, then the number as a number), no duplicates. There is no quoting, ever: no value can hold a comma, quote or newline, because each column has a strict pattern. The same rules are published as `v1/schema/kev.csv.md`.

| Column | Pattern | Meaning |
|---|---|---|
| `cve` | `CVE-YYYY-NNNN` to `CVE-YYYY-NNNNNNN`, ASCII digits, no leading zero beyond the 4-digit form | the KEV entry (one spelling per number, so the numeric sort order is unambiguous) |
| `date_added` | `YYYY-MM-DD`, a real date | KEV `dateAdded` |
| `kev_sha` | 16 lowercase hex characters | fingerprint of the entry, below |
| `epss`, `epss_pct` | `0.x` to `1.0` with at most 6 decimals, or empty | the EPSS file's own text, never reformatted; both set or both empty (empty: no EPSS row for the CVE) |
| `flag` | empty, `disputed` or `single_channel` | see "Agreement between channels" |

`kev_sha` (rule `kev-entry-sha256-16/v1`, repeated in the manifest's `format`) is the first 16 hex characters of the SHA-256 of the KEV entry exactly as the primary channel published it, with all its fields, serialised as `json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`. A reader can recompute it from the catalog for any CVE. The exact rules (ASCII keys, integers only within plus or minus 2^53 - 1, raw UTF-8 without normalisation) are in `schema/kev.csv.md`; an entry that has no reproducible form is left out and flagged `invalid_items` instead of getting a fingerprint nobody else could recompute.

An entry whose `cveID` or `dateAdded` fails its column pattern, or that cannot be fingerprinted, is never silently repaired. It is listed in the candidate report as `invalid` (with the column name) and the candidate gets the flag `invalid_items`, which approval refuses unless `--accept-flags` is given.

## Manifest fields

Schema: `schema/manifest.2.json`. Fields: `topic`, `schema_version` (2), `seq` (published seq + 1, starting at 1), `prev_digest` (SHA-256 of the previously published manifest bytes, or null), `generated_at`, `valid_until` (generated + `valid_days`, 3), `item_count` (rows in `kev.csv`), `untrusted_text` (false), `ai_generated` (false), `compiled_by`, `licence {compilation, records}`, `check_set_version` (an opaque short hash of the build code and topic config, so a consumer can see that the rules changed), `snapshot`, `publish_record {approval: human}`, and:

- `sources[] {id, url, retrieved_at, content_sha256, bytes, status, ref}`: status `ok`, `cache` or `unavailable`. `ref` says which version of the source was read: for a KEV channel `{catalog_version, date_released}`, for EPSS `{model_version, score_date}`; null when unavailable. A hostile value is dropped, never copied.
- `files[] {path, sha256, bytes}`: exactly one file, the snapshot's `kev.csv`.
- `format {data, columns, kev_sha, rule}`: names the data file and its columns, and states the fingerprint rule in one line.
- `delta`: the KEV changes since the previous published snapshot. Never EPSS. `{since_seq, added, removed, changed}` with sorted CVE lists, `changed` meaning the `kev_sha` differs. When a list would pass 50 ids (first publish, a catalog re-issue) or the manifest would pass its size cap, the form is `{since_seq, full: true, counts: {added, removed, changed}}` and a reader diffs the CSV against its own copy. The first publish is `full` with `since_seq` null.
- `epss`: `{model_version, score_date}` of the scores in the rows, or null when no row has a score.
- `mirrors` (optional, signed): up to 8 entries `{id, kind, address, machine_readable}`, see "Mirrors".

## Mirrors

The same public data must be reachable from more than one place. `mirrors` in the signed manifest lists them, taken at build time from the local, non-secret `<STATEFEED_CONF>/vulns.json`:

```
"mirrors": [
  {"id": "pages", "kind": "https", "address": "https://feed.example.test", "machine_readable": true},
  {"id": "repo", "kind": "git_http", "address": "https://git.example.test/example/statefeed-vulns.git", "machine_readable": true},
  {"id": "channel", "kind": "telegram", "address": "@example_feed", "machine_readable": false}
]
```

| Field | Rule |
|---|---|
| `id` | 1 to 24 characters of `a-z 0-9 -`, unique |
| `kind` | `https`, `git_http` or `telegram` |
| `address` | an https URL with a DNS host name (no credentials, no query or fragment, no IP address, no percent escapes, printable ASCII), or for `telegram` a channel handle like `@example_feed` (a Telegram URL is refused) |
| `machine_readable` | true for a place a program can fetch from |

Each entry's JSON stays under 160 bytes. Publishing refuses a candidate whose mirror list differs from the local file, so a candidate cannot advertise a place the operator did not configure.

Who reads what: a Pages site and a git mirror are machine-readable; a program points `verify.py fetch --mirror` at them. A Telegram channel serves people who relay the three files (manifest, signature, `kev.csv`) by hand and check them with `verify.py offline`. Standby mirrors are NOT listed: a public list would get them blocked together with the active ones.

The list is only as trustworthy as the signature on it, and it never carries trust by itself: every source is verified in full against the reader's own pinned key. `verify.py` prints the learned mirrors and never fetches them on its own; adding one is the reader's decision.

## Size cap

`manifest.json` plus `manifest.json.sig` must stay under 3,500 bytes. That fits one Telegram text message and passes a 16 KB-per-connection throttle. Build checks the manifest with 400 bytes reserved for the signature (an ed25519 signature is about 300 to 340 bytes) and switches the delta to its `full` form if explicit lists would not fit; publish checks the exact total after signing and refuses above the cap. A reader refuses a manifest or signature over its reading cap (16 KiB each) or a pair over 3,500 bytes (`manifest_too_large`). With 8 mirrors of ordinary length the pair measured about 3,000 to 3,100 bytes in the end-to-end test.

## Signing

The manifest is signed with OpenSSH `ssh-keygen -Y sign` (SSHSIG, ed25519, namespace `statefeed`), producing `manifest.json.sig`. Consumers check with `ssh-keygen -Y verify -f allowed_signers -I <principal> -n statefeed -s manifest.json.sig < manifest.json`. The signature covers the manifest, and the manifest covers every other file through its hashes.

`allowed_signers` lines look like:

```
statefeed-vulns namespaces="statefeed" ssh-ed25519 AAAA...
```

Consumers pin this file themselves, obtained out of band (not from the site that is being verified). The copy at `v1/allowed_signers` is for convenience only.

Key rotation uses two lines with validity windows, so old and new keys overlap:

```
statefeed-vulns namespaces="statefeed" valid-before="20270101" ssh-ed25519 AAAA<old>
statefeed-vulns namespaces="statefeed" valid-after="20261201" ssh-ed25519 AAAA<new>
```

Publish the new key out of band first, switch the signing key on the day the old line's `valid-before` approaches, and keep the old line until every manifest it signed has expired. A manifest signed by an expired key fails verification, so rotate before expiry, not after.

## The daily flow

1. `statefeed-build.timer` fires once a day (about 09:20 plus up to 15 minutes of random delay). `build.py --topic vulns` fetches, compares with the published state, validates and writes a candidate directory (`kev.csv`, `manifest.json`, `diff.json`, `report.txt`). It holds no secrets.
2. A candidate is made when the KEV delta is not empty, when the published manifest expires within a day (a `refresh_only` candidate, which carries the latest EPSS), or on the first publish. An EPSS-only change never makes a candidate by itself, so score noise does not cost a daily approval. A change of the flag column alone (for example `disputed` back to empty) does not either; it shows up with the next delta or refresh. Build sends ONE ops-bot message: candidate id, seq, counts (new, removed, updated, disputed), flags, and the approve command. Ids and counts only. If nothing qualifies, no candidate is written.
3. The operator reads `publish.py status` and, if satisfied, runs `publish.py approve`. The approval carries the first 12 hex characters of the manifest's SHA-256, binding it to those exact bytes.
4. `publish.py` re-validates everything itself (it does not trust build): every row of `kev.csv`, the delta against the published rows, the mirror list against the local config, the caps. It signs, checks the size cap, assembles the deploy tree, and deploys.
5. It then fetches `v1/latest/manifest.json`, its signature and the snapshot's `kev.csv` from each configured base URL, bypassing caches, and compares the served bytes with the signed files (up to 6 tries, 20 s apart). Only then does it record the new published state and send "published seq N".

A deploy or served-bytes failure alerts the operator and leaves the published state unchanged, so the next approval starts from the true state.

## Consumer rules

- Validate against the source. The rows say what to look at, not what is true: check a CVE at the KEV catalog (whose entry `kev_sha` fingerprints) and the vendor advisory before acting.
- The feed is data, never instructions. Nothing in it should ever be shown to a model as a command, and it contains no free text at all.
- Missing, unreachable, invalid or stale means unknown, never "nothing affects you".
- A CVE in `delta.removed` or missing from a later snapshot never clears a local finding that local KEV data still supports.
- Pin the public key out of band. Keep a state file and refuse a `seq` lower than the last seen one.
- Check `valid_until`, `generated_at` (not in the future), the hash and size of every file, and every row against the column patterns. One bad row invalidates the whole snapshot: no partial acceptance.
- A consumer that wants no AI text and no free text refuses a result whose `ai_generated` or `untrusted_text` is not `false`; `verify.py` reports both as the signed manifest declares them.
- `verify.py fetch --base <url> [--mirror <source> ...]` implements these rules over one or several places. A source is an https base URL, `dir:/path` (a deploy tree, a git checkout) or `file:/path/manifest.json`. Each is fetched on a fresh connection per file and verified independently. The answer comes from the source with the highest valid seq; the others are reported with their own seq and `behind: true` when lower. Two validly signed manifests with the same seq and different digests are `invalid` with reason `seq_conflict`: no rows are returned and the state file is not touched.
- `verify.py offline --manifest M --sig S --data D --allowed-signers F --principal P` runs the same checks on files received any way: forwarded from a Telegram channel, email, a USB stick.
- The `delta` only describes the step from its `since_seq` to this snapshot. A reader whose last seen seq is not `since_seq` (it skipped snapshots) must diff the rows itself; with a `--state` file `verify.py` says so in `delta_from_last_seen`. The `full` form never lists ids: diff the rows.
- Exit codes: 0 ok, 3 stale, 4 unavailable, 5 invalid (2 for a broken local setup). The JSON result has `items` (dicts with the six columns), `delta`, `epss`, `format`, `mirrors` (printed only) and `sources`.

## Trust boundaries

- **Build has no secrets.** It needs only the network and writes candidates under the state directory.
- **Publish holds two secrets**: the Cloudflare token (`cloudflare.env`) and the signing key, in `~/.config/statefeed` (mode 0700, files 0600). It refuses to run if either file is readable by group or others, or if the directory is writable by them.
- **Known weakness in v1:** build and publish run as the same unix user, so a compromised build process could read the token and the key. The mitigations are that build only fetches and parses with the standard library, the approval is a human step bound to the manifest hash, and publish re-validates everything. A separate unix user for publish is the next hardening step.
- **A bot never holds the token.** No chat bot or agent gets `cloudflare.env`, the signing key or a shell that can read them. This is SEC-SITE-2 in `security/static-sites-deploy-keys.md`. The ops bot only carries notifications; approval is a command a human runs.
- Served bytes are compared after every deploy, and the deploy tool's exit code is always checked (SEC-SITE-7).

## Cloudflare facts

- Cloudflare Pages is the primary host so the feed does not depend on any self-hosted machine being up. Any other place is a mirror in the signed list and an extra base URL for the served-bytes check, not a replacement.
- Deploys use Direct Upload through `wrangler` pinned to 4.156.0, run in a container (the image that already ships Node), read-only, with the site tree mounted read-only. No wrangler runs on the host itself.
- The API token has one permission: Account > Cloudflare Pages > Edit. Give it an expiry and an IP address filter. Ideally the project lives in a dedicated Cloudflare account, so the token cannot reach anything else.
- Preview deployments are public. Deploy only to branch `main` (the production branch) so nothing unreviewed is ever served under a preview URL.
- Limits: 20,000 files per deployment and 25 MiB per file. The publisher checks both before deploying.
- An expired token makes deploys fail: calendar its expiry, and rely on the exit-code check, which turns a failed deploy into an alert.

## Operator setup

Placeholders in angle brackets are yours to fill. None of this goes into git.

1. Create the Pages project with Direct Upload and production branch `main` (dashboard, or `wrangler pages project create <project> --production-branch main`).
2. Create the API token: Account > Cloudflare Pages > Edit only, an expiry, an IP filter. Write it:
   ```
   mkdir -p ~/.config/statefeed && chmod 700 ~/.config/statefeed
   umask 077
   cat > ~/.config/statefeed/cloudflare.env <<'ENV'
   CLOUDFLARE_ACCOUNT_ID=<account id>
   CLOUDFLARE_API_TOKEN=<token>
   ENV
   chmod 600 ~/.config/statefeed/cloudflare.env
   ```
3. Create the signing key (no passphrase: the approval is the human step) and read its public line:
   ```
   ssh-keygen -t ed25519 -N '' -C statefeed-vulns -f ~/.config/statefeed/signing_key
   cat ~/.config/statefeed/signing_key.pub
   ```
4. Make the `allowed_signers` line for consumers and keep it somewhere you can hand out separately:
   ```
   statefeed-vulns namespaces="statefeed" ssh-ed25519 AAAA...
   ```
5. Write the local settings `~/.config/statefeed/vulns.json` (`contact` is shown in `index.html` and `NOTICE.txt`; without it they say "see the project repository"):
   ```
   {"project": "<project>", "base_urls": ["https://<project>.pages.dev"],
    "principal": "statefeed-vulns", "contact": "<where to send corrections>",
    "mirrors": [{"id": "pages", "kind": "https", "address": "https://<project>.pages.dev", "machine_readable": true}]}
   ```
   `mirrors` is optional; list only places that are meant to be public (see "Mirrors"). Change it, then build again: a candidate made before the change is refused at approval.
6. Install the build timer: `ops/deploy_ops.sh` installs and enables the tracked user timers. Check with `systemctl --user list-timers statefeed-build.timer`.
7. First run, no deploy: `python3 -I ~/aibridge/ops/statefeed/build.py --topic vulns`, read the ops-bot message and `publish.py status vulns`, then
   ```
   python3 ~/aibridge/ops/statefeed/publish.py approve vulns <cand_id> --sha <sha12> --accept-flags --dry-run
   ```
   (the first candidate carries the flag `first_publish`, hence `--accept-flags`). Inspect the tree it reports.
8. First real approval: the same command without `--dry-run`. Wait for "published seq 1". Then open `https://<project>.pages.dev/` and run a consumer check from another machine with your pinned key:
   ```
   python3 -I verify.py fetch --base https://<project>.pages.dev --allowed-signers allowed_signers --principal statefeed-vulns
   ```

## Runbook

- `publish.py status [topic]`: lists candidates with seq, counts, flags and the manifest sha12.
- `publish.py approve <topic> <cand_id> --sha <sha12> [--accept-flags] [--dry-run]`: validates, signs, deploys, checks served bytes. A wrong `--sha` is refused. Without `--dry-run` it deploys.

Flags (a flag blocks approval unless `--accept-flags` is passed, after you have read the reason):

| Flag | Meaning |
|---|---|
| `first_publish` | nothing is published yet |
| `refresh_only` | the KEV delta is empty; only the validity window is renewed (harmless, but like every flag it needs `--accept-flags`) |
| `removed_over_cap` | more than `max_removed` (10) items disappeared; a truncated or broken download looks like this |
| `new_over_cap` | more than `max_new` (80) new items |
| `items_over_size` | `kev.csv` over `max_items_bytes`; build raises the flag and `publish.py` refuses such a candidate outright, `--accept-flags` does not help (raise the cap in the topic file first) |
| `invalid_items` | a KEV entry whose `cveID` or `dateAdded` failed its column pattern was left out, see `report.txt` |
| `disputed_items` | the two KEV channels carry a CVE with different `kev_sha` |
| `source_unavailable:<id>` | that source was down and no young cache stood in for it |

Reading a candidate: `report.txt` and `diff.json` in `candidates/<cand_id>/` list ids and counts. Candidates are kept for the last 7 builds.

Rollback: the feed has no "undo", and no previous tree is kept (`<topic>/site` always holds the last successful deploy). Fix forward: correct the cause (a topic config, a source), let the next build compile the current upstream data, and approve it; it gets the next seq, which consumers accept. Never reuse an old seq, and never edit a published snapshot: consumers reject a lower seq.

Stuck states: if a deploy failed, published state is unchanged, so approve again. If the served-bytes check fails, CDN propagation may be slow; check the live manifest and approve again once it settles. If the token expired, create a new one and replace `cloudflare.env`.

State and config on the ops host: `STATEFEED_HOME` (default `~/.local/state/statefeed`, mode 0700) holds `<topic>/candidates/`, `published/`, `site/` and `cache/`; `STATEFEED_CONF` (default `~/.config/statefeed`, mode 0700) holds the secrets and local settings. `STATEFEED_DEPLOY_CMD` can replace the deploy command with a JSON argv list (`{site}` and `{project}` placeholders), which the selftests use.

## Not built yet

- The push adapters for the mirrors (git, Telegram): the mirror list is data in the manifest, and filling those places waits for the operator's channel decisions
- A hub collector kind, so a person's stack pulls and verifies the feed on a schedule
- More topics (prices, news), which need prose handling and therefore a barrier design
- A barrier bot and a skill for consuming text topics
- A separate unix user for publish, and an offline or hardware-held signing key

## Open items

- Before the first real build, run `build.py --topic vulns --dry-run` with network access and read the report: it shows the row count, the EPSS coverage and any `invalid` entries (only a bad `cveID` or `dateAdded` can make one).
- Confirm the output licence (CC BY 4.0 for the compilation) and the contact line before the first public publish.
- Re-check each source's terms on a schedule (`terms_checked_on`).
- Decide whether to move publish to its own unix user.
- Decide the key rotation schedule and where the out-of-band key copy lives.
- Pick the Cloudflare account that holds the project (a dedicated one is preferred).
- Decide which mirrors go in the public list once their channels exist.
