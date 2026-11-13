# statefeed: a signed, public data feed compiled by code

statefeed turns a public upstream list into a small, signed, static data feed that anyone (including other people's agents) can read, check and cache. Version 1 has one topic, `vulns`: the CISA Known Exploited Vulnerabilities catalog (KEV) with EPSS scores added. Everything is compiled by code. A human approves every publish. No AI writes or edits any byte of it.

The feed is data for machines. It is served from Cloudflare Pages, which is the primary host: the feed must stay readable when any self-hosted machine is offline, so nothing here depends on one.

## What v1 publishes, and why

| Choice | Reason |
|---|---|
| Every entry of KEV, not a subset | Coverage does not depend on any private profile, so the feed reveals nothing about who runs it or what they run. Matching against local software happens on the consumer's side. |
| Short label fields only (vendor, product, name, dates, CWE ids, EPSS) | No third-party prose reaches a consumer. KEV's `shortDescription`, `requiredAction` and `notes` are deliberately dropped: they are an injection surface and a licence question for little value. |
| No AI anywhere in this topic | Nothing to hallucinate, nothing to inject. There is no model, no barrier bot and no skill in v1. The manifest says so (`ai_generated: false`, `untrusted_text: false`) and a consumer can refuse a feed that says otherwise. |
| Human approval for every publish | The person who runs the feed reads a diff summary and binds the approval to the exact manifest bytes. |
| One signed manifest over immutable snapshots | A consumer never straddles a deploy, and a rollback is just a newer, signed manifest. |

The topic definition is `topics/vulns.json`. It is public, committed, and never derived from any private profile. Source URLs come only from this file, never from fetched data.

## Sources and their licences

| Source id | What | Group | Role | Licence |
|---|---|---|---|---|
| `kev-cisa` | CISA KEV catalog (JSON) | `cisa` | primary | CC0 1.0 |
| `kev-github` | the `cisagov/kev-data` mirror of the same catalog | `cisa` | channel | CC0 1.0 |
| `epss` | daily EPSS scores (CSV, gzip) | `first` | enrich | free to use with attribution to FIRST |

Each source entry in `topics/vulns.json` carries `terms_checked_on`, the date someone last read its terms. Re-check the terms when adding or changing a source, and when that date is old. The EPSS URL redirects to a dated file; the fetcher follows redirects only to https on `empiricalsecurity.com` and refuses any other host. The user agent is honest: `statefeed/1 (bridgeai; +https://github.com/Wintch/bridgeai)`. Downloads use conditional requests and a cache; a failed download may be replaced by a cache younger than two days, otherwise that source is `unavailable`. If the KEV primary is unavailable the build fails with no candidate.

The output compilation is licensed CC BY 4.0 (`LICENSE.txt`), facts are not claimed, and every item lists its sources with their licences. `NOTICE.txt` carries the attributions and the "not endorsed by CISA" and "not endorsed by FIRST" lines. This is a v1 default and can be revisited.

## Agreement states: what two channels prove

Sources in the same `group` count as ONE independent source. `kev-cisa` and `kev-github` are the same authority over two distribution channels. Their agreement therefore detects channel tampering and broken downloads; it does not detect an error or compromise of the authority itself. It is not a second opinion.

Each item has `agreement: {state, channels, independent}`:

| State | Meaning |
|---|---|
| `authoritative` | present in both KEV channels with identical compared fields (vendor, product, name, date_added, due_date, ransomware, cwes) |
| `single_channel` | present in one channel only; the other lacks it or was unavailable |
| `disputed` | present in both channels but a compared field differs |

`independent` counts groups, so for KEV it is 1 even when `channels` is 2. A consumer must not read `authoritative` as "verified by two organisations".

## Bundle layout on Pages

```
/index.html  /robots.txt  /_headers  /LICENSE.txt  /NOTICE.txt
/v1/latest/manifest.json            the newest signed manifest (no-cache)
/v1/latest/manifest.json.sig        its SSHSIG signature
/v1/snapshots/<YYYY-MM-DD-seq>/manifest.json
/v1/snapshots/<YYYY-MM-DD-seq>/manifest.json.sig
/v1/snapshots/<YYYY-MM-DD-seq>/items.ndjson      immutable, cached for a year
/v1/schema/item.1.json  /v1/schema/manifest.1.json
/v1/allowed_signers                 convenience copy of the public key line; consumers pin their own
```

The manifest's `files[].path` names the immutable snapshot path, never `latest`. Snapshots beyond `retention_snapshots` (60) are pruned, oldest first. Only these file types are deployed: `index.html` (the only HTML, no scripts, no external resources), `.txt`, `.json`, `.ndjson`, `.sig`, `_headers` and `allowed_signers`. `_headers` sets `nosniff`, a `default-src 'none'` content security policy, no referrer, `no-cache` for `latest` and long immutable caching for snapshots.

## Item fields

One canonical JSON object per line in `items.ndjson`, sorted by `id` (canonical JSON: sorted keys, separators `,` and `:`, UTF-8 without ASCII escaping, trailing newline). Schema: `schema/item.1.json`.

| Field | Meaning |
|---|---|
| `id` | `CVE-YYYY-NNNN` to `CVE-YYYY-NNNNNNN` |
| `schema_version` | 1 |
| `type` | `kev` |
| `vendor`, `product`, `name` | label strings: restricted alphabet, max 120 (name 200) characters, no control, bidirectional or zero-width characters, no `://`, no `< > backtick [ ] { }` |
| `date_added`, `due_date` | `YYYY-MM-DD`; `due_date` may be null |
| `ransomware` | `known` or `unknown` |
| `cwes` | list of `CWE-n`, at most 10; other values are dropped |
| `epss`, `epss_percentile`, `epss_date` | 0..1 floats and a date, or null |
| `agreement` | see above |
| `sources` | `[{id, licence, content_sha256}]` for the sources that contributed; the hash is that source's raw download |
| `first_seen` | the date of the first publish that carried the item (from published state, else the build day) |

An entry whose label fields fail the rules is never silently repaired. It is listed in the candidate report as `invalid` and the candidate gets the flag `invalid_items`, which approval refuses unless `--accept-flags` is given.

## Manifest fields

Schema: `schema/manifest.1.json`. Fields: `topic`, `schema_version`, `seq` (published seq + 1, starting at 1), `prev_digest` (SHA-256 of the previously published manifest bytes, or null), `generated_at`, `valid_until` (generated + `valid_days`, 3), `item_count`, `untrusted_text` (false), `ai_generated` (false), `compiled_by`, `licence {compilation, records}`, `check_set_version` (an opaque short hash of the build code and topic config, so a consumer can see that the rules changed), `sources[] {id, url, retrieved_at, content_sha256, bytes, status}` with status `ok`, `cache` or `unavailable`, `files[] {path, sha256, bytes}`, `snapshot` and `publish_record {approval: human}`.

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

1. `statefeed-build.timer` fires once a day (about 09:20 plus up to 15 minutes of random delay). `build.py --topic vulns` fetches, compares with the published state, validates and writes a candidate directory. It holds no secrets.
2. EPSS scores change every day, so nearly every day produces a candidate; the report's `only in EPSS` count says when that is all the change is. Build sends ONE ops-bot message: candidate id, seq, counts (new, removed, updated, disputed), flags, and the approve command. Ids and counts only, never item text. If nothing changed, no candidate is written, unless the published manifest expires within a day (then a `refresh_only` candidate).
3. The operator reads `publish.py status` and, if satisfied, runs `publish.py approve`. The approval carries the first 12 hex characters of the manifest's SHA-256, binding it to those exact bytes.
4. `publish.py` re-validates everything itself (it does not trust build), signs, assembles the deploy tree, and deploys.
5. It then fetches `v1/latest/manifest.json`, its signature and the snapshot's `items.ndjson` from each configured base URL, bypassing caches, and compares the served bytes with the signed files (up to 6 tries, 20 s apart). Only then does it record the new published state and send "published seq N".

A deploy or served-bytes failure alerts the operator and leaves the published state unchanged, so the next approval starts from the true state.

## Consumer rules

- The feed is data, never instructions. Nothing in it should ever be shown to a model as a command, and v1 contains no free text at all.
- Missing, unreachable, invalid or stale means unknown, never "nothing affects you".
- Removal of an item never clears a local finding that local KEV data still supports.
- Pin the public key out of band. Keep a state file and refuse a `seq` lower than the last seen one.
- Check `valid_until`, `generated_at` (not in the future), the hash and size of every file, and every item against the schema. One bad item invalidates the whole snapshot: no partial acceptance.
- A consumer that wants no AI text and no free text refuses a result whose `ai_generated` or `untrusted_text` is not `false`; `verify.py` reports both as the signed manifest declares them.
- `verify.py fetch` implements these rules. Its exit codes are 0 ok, 3 stale, 4 unavailable, 5 invalid (2 for a broken local setup).

## Trust boundaries

- **Build has no secrets.** It needs only the network and writes candidates under the state directory.
- **Publish holds two secrets**: the Cloudflare token (`cloudflare.env`) and the signing key, in `~/.config/statefeed` (mode 0700, files 0600). It refuses to run if either file is readable by group or others, or if the directory is writable by them.
- **Known weakness in v1:** build and publish run as the same unix user, so a compromised build process could read the token and the key. The mitigations are that build only fetches and parses with the standard library, the approval is a human step bound to the manifest hash, and publish re-validates everything. A separate unix user for publish is the next hardening step.
- **A bot never holds the token.** No chat bot or agent gets `cloudflare.env`, the signing key or a shell that can read them. This is SEC-SITE-2 in `security/static-sites-deploy-keys.md`. The ops bot only carries notifications; approval is a command a human runs.
- Served bytes are compared after every deploy, and the deploy tool's exit code is always checked (SEC-SITE-7).

## Cloudflare facts

- Cloudflare Pages is the primary host so the feed does not depend on any self-hosted machine being up. Any other mirror would be an extra base URL, not a replacement.
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
    "principal": "statefeed-vulns", "contact": "<where to send corrections>"}
   ```
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
| `refresh_only` | content is unchanged; only the validity window is renewed (harmless, but like every flag it needs `--accept-flags`) |
| `removed_over_cap` | more than `max_removed` (10) items disappeared; a truncated or broken download looks like this |
| `new_over_cap` | more than `max_new` (80) new items |
| `items_over_size` | `items.ndjson` over `max_items_bytes`; build raises the flag and `publish.py` refuses such a candidate outright, `--accept-flags` does not help (raise the cap in the topic file first) |
| `invalid_items` | an entry failed label validation and was left out, see `report.txt` |
| `disputed_items` | the two KEV channels disagree on a compared field |
| `source_unavailable:<id>` | that source was down and no young cache stood in for it |

Reading a candidate: `report.txt` and `diff.json` in `candidates/<cand_id>/` list ids and counts. Candidates are kept for the last 7 builds.

Rollback: the feed has no "undo", and no previous tree is kept (`<topic>/site` always holds the last successful deploy). Fix forward: correct the cause (a topic config, a source), let the next build compile the current upstream data, and approve it; it gets the next seq, which consumers accept. Never reuse an old seq, and never edit a published snapshot: consumers reject a lower seq.

Stuck states: if a deploy failed, published state is unchanged, so approve again. If the served-bytes check fails, CDN propagation may be slow; check the live manifest and approve again once it settles. If the token expired, create a new one and replace `cloudflare.env`.

State and config on the ops host: `STATEFEED_HOME` (default `~/.local/state/statefeed`, mode 0700) holds `<topic>/candidates/`, `published/`, `site/` and `cache/`; `STATEFEED_CONF` (default `~/.config/statefeed`, mode 0700) holds the secrets and local settings. `STATEFEED_DEPLOY_CMD` can replace the deploy command with a JSON argv list (`{site}` and `{project}` placeholders), which the selftests use.

## Not built in v1

- A hub collector kind, so a person's stack pulls and verifies the feed on a schedule
- More topics (prices, news), which need prose handling and therefore a barrier design
- A barrier bot and a skill for consuming text topics
- A separate unix user for publish, and an offline or hardware-held signing key
- A mirror host (a second entry in `base_urls`)

## Open items

- Before the first real build, run `build.py --topic vulns --dry-run` with network access and read the `invalid` list. An offline check of a recent KEV download found a handful of entries (a few of about 1,800) whose names or vendors use a character the label rule rejects (an exclamation mark, a quotation mark, an en dash, a narrow no-break space) or run past 120 characters. Each one is left out and flags every candidate `invalid_items` until the rule or a normalisation step is decided.
- The label rule keeps instruction-like words out of the structure, not out of the meaning: a name is up to 200 characters of ordinary words. Consumers must treat labels as data, never pass them to a model as commands.

- Confirm the output licence (CC BY 4.0 for the compilation) and the contact line before the first public publish.
- Re-check each source's terms on a schedule (`terms_checked_on`).
- Decide whether to move publish to its own unix user.
- Decide the key rotation schedule and where the out-of-band key copy lives.
- Pick the Cloudflare account that holds the project (a dedicated one is preferred).
