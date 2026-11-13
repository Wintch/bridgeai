---
title: Security watch pack (design)
scope: following the advisories that matter for what a stack actually runs, and checking hosts and images against them
when_to_use: choosing which security feeds to follow, matching hosts or images against advisories, designing the upkeep skill or the all-in-one vs split bot comparison
related: [../ops/VULN_WATCH.md, ../ops/FACT_MODEL.md, patching.md, DEBIAN13_MIGRATION.md, ../hub/HUB.md]
---
# Security watch pack: stack-aware vulnerability and advisory watch

Status: design. Nothing in this document is built except what already exists: `ops/vuln_watch.py` (KEV plus Debian tracker matching, documented in `ops/VULN_WATCH.md`) and the hub's security collectors (`hub/HUB.md`). Everything else is marked "Not built" or "Planned". Anything not confirmed is marked UNVERIFIED. Effort figures are rough focused working days.

The hub reads RSS/Atom in streaming (first 40 entries, 40 MB cap), so large agency feeds work. This removes the old 2 MB limit as a reason to drop a feed.

## 1. Purpose

Answer two questions for each scope, without anyone keeping a list by hand:

- **Which advisories concern software we actually run?** Feeds are chosen from what is installed, not from a hand-picked list.
- **Is host or image X patched for CVE Y?** The answer comes from a version compare, not from a model.

A scope is a set of machines: `ours`, or `client-<name>`. The pack only watches. It never patches, restarts or writes on a host.

## 2. Principles

1. **Deterministic first, LLM last.** Order: inventory, package-native matching, prioritisation, then news relevance. `vuln_watch.py` already does an exact dpkg compare with no model in the loop. "Is host X patched" is a query over its output.
2. **The LLM only filters and summarises public news.** It sees one public news item and one candidate product name. It never sees hosts, IPs, versions or the profile. It must return a verbatim quote from the item, and code rejects the answer otherwise.
3. **Unknown is never OK.** A blind host, a stale inventory or software outside the package manager is reported as `unknown`. The pack never says "all clear" when something is unknown.
4. **No package list leaves the network.** No online batch query (for example OSV `querybatch`) with a package list. Use offline datasets or a local database.
5. **No per-CVE lookups either.** The set of CVEs matched against a scope is a fingerprint of its stack. EPSS comes from the bulk daily file (`https://epss.empiricalsecurity.com/epss_scores-current.csv.gz`, a few MB), and lookups happen locally.
6. **One source of truth per fact.** The profile is the only description of what we run. One catalog is the only place a feed URL can come from. Consumers keep no lists of their own.
7. **NVD/CPE is the wrong direction.** Since 2026-04-15 NVD enriches only KEV, federal-use and critical software (https://www.nist.gov/itl/nvd). The "NVD/CPE" later phase in `ops/VULN_WATCH.md` is replaced by the Debian tracker, OSV offline data and the curated product table for KEV.
8. **News is the small lane.** Most coverage is structured data (distro trackers, KEV, OSV). News feeds exist for what structured data misses: vendor-repository software, runtimes and static binaries.

Platform facts that shape the design:

- The stack image is Debian 12 (bookworm). Standard support ended 2026-07-11 and long-term support runs to 2028-06-30 (https://endoflife.date/api/debian.json). Fixes now ship as DLA, not DSA.
- Node.js and Python in the image are upstream binaries or uv-managed builds, not Debian's packages. The Debian tracker and OSV npm do not cover the runtimes themselves.
- `php-cli` has been removed from the shared base image (committed, not yet deployed). No server runs PHP unless the profile says so.

## 3. Deployment profile

**Definition.** A profile is the machine-readable answer to "what do we run, where, and how exposed". One per scope. Feed selection, matching, news filtering and EOL alerts all derive from it.

**File (Planned):** `stack_profile.<scope>.json`. The schema and an example go in the repo. The real files never do.

- `scope`, `generated_at`.
- `hosts[]`: `{id, os, kernel, exposure, owner (ours|third-party), inventory_source, inventory_age}`.
- `products[]`: `{purl, name, version, host_or_image, source, catalog_id, exposure, first_seen, last_seen}`.
- `blind[]`: hosts with no inventory. Blind is a first-class state.

**Exposure tags** (per component):

| Tag | Meaning |
|---|---|
| I | reachable from the internet |
| L | reachable from the local network |
| X | internal only |
| U | parses user-supplied files or pages (Pillow, ffmpeg, ImageMagick, poppler, Chromium) |

`U` counts as exposed even when the component has no listening port: untrusted input reaches it anyway.

**Sources, in order of trust:**

1. **Zabbix inventory.** The `vw.*` items already exist (`ops/zabbix/template_sw_inventory.yaml`, `vw_inventory.sh`). They give each host's dpkg set through a read-only token. They do not see container images.
2. **Image SBOM.** One CycloneDX SBOM per image digest, produced by the same scanner used for matching (section 6). Planned. Whether it identifies every static binary is UNVERIFIED.
3. **Compose and Dockerfile parse.** Image digests and pinned tools (web server, database, antivirus, bot API server). Planned.
4. **Forced-command SSH inventory** for hosts without a Zabbix agent (section 8).
5. **`profile_manual.json`**, operator-written, for things nobody can inventory: self-hosted services with unknown versions, the edge proxy product, hypervisor versions, SaaS use. A product listed there with version `unknown` still activates its feeds. Only the version-behind check waits for a version.

**Normalisation.** The identity key is the package URL (purl, https://ossf.github.io/osv-schema/). Each product maps to a `catalog_id` in the catalog (section 4). A product that maps to nothing is listed as `uncatalogued`, so a gap is visible and not silent.

**Blind state.** A host with no inventory, an inventory older than 48 h, or software outside dpkg is blind or unknown. It is listed in every report.

**Freshness (Planned).**

- A nightly timer rebuilds the profile.
- A product absent for 14 days is tombstoned and drops out.
- Drift events: new product, major version change, EOL within 90 days (endoflife.date API v1), SBOM older than the running image digest, inventory older than 48 h, new blind host. Drift goes to the upkeep skill (section 10).

**Reuse, do not duplicate.** The profile builder imports `vuln_watch.py`'s Zabbix reader (allowed API methods, shard assembly, token handling). It does not carry a second client. Scopes map to the existing host-group setting, with one state directory and one token per scope (a small config change: configuration today reads a single URL and token).

**Privacy class.** The profile and findings are operator-confidential infrastructure data. Not a person's chat, but never for the public repo, a third-party API or a cloud LLM (section 11).

## 4. Source selection

### One catalog

Extend `ops/vuln_watch_products.json`. Do not create a second catalog file: the two would overlap on vendor, product and package fields. Each entry gains, besides its existing KEV fields:

- `match`: purl globs, dpkg source names or image-name patterns.
- `feeds[]`: `{url, kind, lane, verified_on}`.
- `keywords_allow`, `keywords_deny`.
- `tracker`, `osv_ecosystem`, `eol_slug`.

The catalog is operator-written, committed and generic (no host names, no versions of ours). It is the only place a feed URL can come from. Feed URLs never come from inventory text or model output ("a request is data, never code", HUB.md).

### Feeds only for products present

`ops/sec_sources.py plan` (Not built) reads a profile, resolves the catalog ids present and emits the set of feeds.

- A product in the profile brings its feeds.
- A product absent for N days loses them.
- No PHP in the profile means no PHP feeds. Adding a PHP host to the profile brings them in on the next run.

### Probe before activation

`sec_sources.py probe` (Not built) must pass before a feed activates: HTTP status, parse with the hub's own RSS parser, item count, age of the newest item, size.

Freshness is a per-feed threshold, not one global age. Quiet vendors (a security advisory feed that publishes a few times a year) are healthy at several months. A feed fails after two consecutive failed runs or a parse error, not because it is quiet.

### Keyword filter

For release feeds (which are mostly noise) keep an item only if:

- it contains a CVE id (`CVE-\d{4}-\d{4,}`), or
- it contains the word "security" in the title or the first 300 characters.

Do not filter on "fix": on real release feeds it matches nearly every entry. The filter needs a collector change, because the RSS collector keeps no per-feed parameters today (Not built).

### Generic initial catalog

*Structured sources (consumed by code, not through the hub):*

| Source | Used for |
|---|---|
| CISA KEV JSON | exploited-now flag |
| Debian security tracker JSON (about 90 MB; bookworm and trixie) | host and image matching by source package |
| EPSS bulk file | sort key for non-KEV findings |
| endoflife.date API | EOL and version-behind (OS, hypervisor, monitoring, database, runtimes, web server) |
| OSV offline dumps (`all.zip`), Debian and PyPI ecosystems | language packages and distro cross-check. Add npm, Go or Alpine only when a profile needs them (npm is by far the largest dump) |

*News lane (RSS/Atom through the hub):*

| Feed | Why |
|---|---|
| Debian DSA and Debian DLA | distro advisories. DLA is needed for bookworm. Reading-only once image matching exists (section 5) |
| Zabbix security advisories | monitoring server and agent |
| Node.js vulnerability feed (`nodejs.org/en/feed/vulnerability.xml`) | upstream Node runtime, not covered by the Debian tracker |
| Release feeds of nginx, Open WebUI, ClamAV, Gitea, Playwright, yt-dlp (GitHub `releases.atom`) | vendor software outside the distro, through the keyword filter above |
| Chrome releases (`chromereleases.googleblog.com/feeds/posts/default`) | Playwright's Chromium |
| Ubuntu USN | client scopes with Ubuntu hosts only |

The feeds in this table were fetched and parsed with the hub's RSS parser during research on 2026-11-13. Re-probe before activating (feeds change).

Release feeds that carry no security signal (for example an agent framework's own releases) become a pin-review reminder only, not a security item.

Conditional-only items:

- GPU vendor advisories (page only, no feed): only when a GPU host is in the profile.
- llama.cpp releases: only while that service is in the profile.

### Sources with no usable machine-readable feed

- **Proxmox.** There is no machine-readable advisory feed. The forum section for security advisories exists, but a tested RSS address returned an XML error (UNVERIFIED that any usable feed exists). A page watcher conflicts with the hub rule that a request is data, never code, unless it is plain RSS. Decision: keep a hand-kept table of Proxmox security announcements (PSA) as part of the fact model (see `ops/FACT_MODEL.md`, design only), updated by the operator. Debian packages on the nodes are still covered by the tracker through the Zabbix inventory.
- **OpenSSH, ffmpeg, PostgreSQL, Docker CE.** Page-only announcements. Debian-packaged builds are covered by the tracker. Docker CE and containerd come from a third-party apt repository and are not in the tracker: cover them with the OSV Go ecosystem (moby, containerd) if needed.
- **Edge proxy.** No source until the product is named in the manual profile.
- **SaaS (CDN, tunnel).** No CVE feed. Key hygiene only.

### Deliberately not subscribed

- PHP (no PHP in the profile).
- PostgreSQL news. A database exposed to a network is an exposure alert from the profile, not a news item.
- Node and Python vendor pages for libraries (OSV and the Debian tracker cover those).

### Existing generic security firehoses

News aggregators and exploit lists are not stack-aware. Proposal:

- Drop feeds that duplicate another (for example two agency feeds that repeat one alert feed) and the aggregator's KEV filter, since KEV is handled in code.
- Move the remaining firehoses to a `reading` lane: opt-in human reading, never counted as security attention.

The revista caps items per source and total characters, so a firehose in it silently loses items. That is another reason to keep the security lane separate (section 7).

### Clients

The same catalog and `sec_sources.py` run against a client profile. Output goes to a separate per-scope file. Feeds come from the catalog, never from the client. Every add needs operator approval.

## 5. Matching layers

**L1: findings (code).**

- **Today.** `vuln_watch.py` is KEV-only. It reduces the Debian tracker to KEV CVEs, matches Zabbix-inventoried Debian hosts by exact dpkg version compare, and reports states `VULN_FIX`, `AFFECTED`, `CHECK`.
- **Non-KEV ranking is a matcher rewrite, not an enrichment.** Today there are no non-KEV findings to rank. The rewrite must not hold the full tracker (about 70,000 CVE-release rows, 90 MB JSON) in memory. Use streaming or SQLite, and add a `MemoryMax` to `vuln-watch.service` (it has Nice and idle IO but no memory cap today). Not built.
- **Findings file.** `state.json` already keeps one entry per host, CVE and package (first and last seen, installed and fixed versions, KEV due date). The findings file (`findings.<scope>.json`) is an export of that state plus new columns (`urgency`, `epss`, `exposure`, `verified`), not a second store. Not built.
- **Image matching.** Do not extend the hub's `debian-dsa` collector. It matches by package name from the advisory title only: no release, no version. It already matches a newer-release advisory against an older-release image, and adding DLA would double that noise. Instead feed the image's dpkg set (from `dpkg-query` or the SBOM) through the tracker logic once per codename (bookworm). That yields fixed or open status. DSA and DLA feeds then become reading-only. Not built.
- **Language packages.** Matched from the SBOM against OSV offline data (Python wheels, and npm if needed).
- **Raw noise.** OSV Debian data is dominated by old low-urgency rows, so the Debian urgency and the tracker's fixed state filter results before display.

**L2: prioritisation (deterministic).** Proposed rules, to be tuned by the experiment (section 13):

| Level | Rule | Route |
|---|---|---|
| P0 | KEV and product present on a host or image (`AFFECTED` or `VULN_FIX`) | attention, ops bot |
| P1 | KEV with unclear match (`CHECK`), or EPSS at or above a threshold with a fix on an exposed (I, L or U) component | digest |
| P2 | high EPSS with a fix on an X component | digest |
| P3 | everything else | weekly digest |

Debian urgency and the tracker's fixed state apply first.

**L3: news items against the profile.**

1. **Deterministic prefilter** in the hub: catalog keywords and CVE-id regex. A CVE id that already appears in a finding links the item to that finding with no LLM.
2. **LLM step** only for what passes. Input: the item text (delimited and treated as hostile), one candidate product and its public name, no tools. Nothing about hosts, IPs, versions or the profile.
3. **Closed-world check in code.** The model returns `{relevant, catalog_id, quote, cves[]}`. Code rejects the answer unless `catalog_id` is present in the profile and `quote` is a verbatim substring of the item. (A reported 42% false-positive reduction for this approach comes from a paper seen only through search snippets: treat it as weak.)
4. **Wording.** "May concern X (from the item's text)", never "your server is affected". Only an L1 finding can say affected.
5. **Dropped items are counted** ("dropped N") so volume stays visible. A product the catalog does not know is missed by design.

The hub already has an optional `HttpLLM` (off by default). Reusing it for L3 is possible, but where it runs is a privacy-class decision (section 11), not only a code one.

## 6. Scanner for images

- **One scanner, not two.** Pin Trivy by digest (it already runs in `ops/image_audit.sh` with `--trivy`, today as a floating `latest` tag) or use Grype. Do not ship both. Choose after a measurement on a guest. Trivy had a supply-chain incident in March 2026 (v0.69.4 and Docker tags 0.69.5 and 0.69.6), so a digest pin is needed either way (https://www.aquasec.com/blog/trivy-supply-chain-attack-what-you-need-to-know/).
- **Run once per image digest, off the Docker host.** Stacks and the hub share one image digest, so scanning once is enough. Run it on a machine with spare RAM, and ship only the SBOM or findings to the ops host. Do not scan on the small ops host. RAM and database size are UNVERIFIED: measure first.
- **Optional second opinion** on lockfiles: `osv-scanner` in offline mode.
- OpenVEX is the format for our own suppressions (https://github.com/openvex/spec/blob/main/OPENVEX-SPEC.md).

## 7. Hub mechanics

What works today and what does not:

- **`system.json` accepts `rss` entries.** `{"kind":"rss","key":<url>,"attention_for":[...]}` is valid today (the loader calls each collector's `canonical()` generically). Entry fields: `kind`, `key`, `params`, `title`, `interval_min`, `attention_for`.
- **No origin field yet.** There is no way to tag an entry as pack-owned. `system.json` is one file, and an entry missing from it is marked non-system. A pack writer and the operator's hand edits would clobber each other. Options (Planned, choose one): add an `origin` field with a code change and selftest, or let the pack own a separate file that the loader merges.
- **`attention_for` is the only route** from a system source to a person. It puts every item of the source into the attention section of the revista, behind its per-source and character caps. Flagging many release feeds as attention floods the reader. RSS has no quiet baseline (the Security collector has one). Only the "published more than 24 h before the window" rule limits a backlog.
- **A module gates only what a person may subscribe to.** `modules_catalog.json` `hub_kinds` does not apply to system sources, so adding a `security` module would gate nothing. Do not plan one.
- **A separate security digest is new code** in the hub client and in `publish_person` (Planned): a distinct lane, with P0 items opening the digest. It is not a configuration entry.
- **Per-feed keywords** need a collector change (RSS canonical params are empty today).
- **Generalise the existing drift check.** The hub's yt-dlp check ("releases.atom against a pinned installed version") can be parameterised by feed key and an installed-version command for web server, Open WebUI, antivirus and Playwright. No new drift engine.

## 8. Verification states

| State | Definition |
|---|---|
| matched | inventory item and advisory agree by source package or product, with an exact version compare. No keywords |
| verified | matched, and the host's inventory is younger than 48 h, and the match comes from a distro tracker or fixed-version compare. A finding closes as `closed-verified` when a later inventory shows the fixed version |
| unknown | host blind, inventory stale, or software outside dpkg (containers, tarballs, snaps, third-party repositories that reuse Debian source names). Reported as unknown, never as OK |
| cross-checked | an independent scanner run by the operator (for example vuls) disagrees on no CVE for that host. Planned `ops/sec_crosscheck.py` reads a JSON the operator drops in and prints only counts of agreement and difference |

**Prerequisites for the Zabbix path** (operator steps, none assumed done): a read-only Zabbix user with role User and a token, the `SW inventory daily` template imported, UserParameters installed on a pilot host, and the URL and token set in the ops environment file. The allowed API methods stay the five already restricted in `vuln_watch.py`.

### Fallback: forced-command inventory over SSH

For hosts without a Zabbix agent, including client hosts.

- **Use `ops/zabbix/vw_inventory.sh`, not the F1 audit branch.** The script is already read-only, needs no root, and prints exactly `vuln_watch`'s line format (`binary<TAB>version<TAB>source<TAB>source_version`, sharded, truncated marker). The F1 audit script prints only upgradable and security package names, not an inventory. Cherry-picking F1 would also invalidate its pinned install commit hash.
- **Run it host-side.** An ops-host job runs it over SSH with a forced-command key (`command="..."`, `from=`, no pty, no forwarding) and feeds the output to the same parser as the Zabbix path. Matching stays local, so no package list leaves. Not built. About one day.
- **Trust boundary.** This is the ops-brain model (the ops host holds the key and the watch is read-only), not the F1 model (a person's key inside the person's stack). The key lives on the ops host.
- **Key storage design (Planned).** One key pair per scope, never shared across scopes. Private keys in a 0700 directory owned by the ops user, 0600 files, outside git. The public key on the target is restricted by the forced command to the inventory script only. A client revokes access by deleting one line. A key that can only print the package list limits what a leak reveals.
- Containers cannot reach the host's port 22, which is irrelevant here because the job runs on the host.
- **Rejected as fallbacks:** a full XDR/SIEM agent platform and a software-bill-of-materials server with its own database (each needs several GB of RAM on a small host), and an osquery agent (redundant with the Zabbix agent).

## 9. Ubuntu and client scopes

`vuln_watch` is Debian-only and marks Ubuntu as unsupported. Without a path for Ubuntu, a client scope with Ubuntu hosts would be mostly "unsupported" or "blind".

- Add the USN feed to the catalog for client scopes (Planned).
- Add an Ubuntu tracker source (Planned). Ubuntu OSV dumps are large (several hundred MB): do not include them by default.
- Until then, report Ubuntu hosts as `unknown`, not OK.

## 10. Upkeep skill

**Name:** `security-watch-upkeep` (Planned: `SKILL_security_watch.md`, a `vigilancia` pack in `skill_packs.json`; the existing `seguridad` pack is unrelated file checking). Gateway command: `gateway secwatch` (Planned), read-only over the vuln_watch state. It does not duplicate `gateway zabbix`.

The deterministic jobs are ops-side timers. The skill is the conversational front and needs no hub-write capability itself.

**Triggers.**

- Nightly timer: `profile refresh` (code only).
- Weekly timer: `sources probe`, then a short LLM write-up of the diff and probe results.
- On demand: `profile show|diff|refresh`, `sources plan|probe|apply|prune`, `status`, `explain <id>`.
- Events: a deploy or image digest change, a new monitored host, an EOL within 90 days, a dead feed.

**What it does.**

- Refreshes the profile and diffs it against the catalog.
- Proposes feed adds and removals, checks feed health.
- Raises drift alerts (new product, major version change, EOL, stale SBOM, blind host).
- Applies approved changes through the operator-side script.
- Proposes catalog edits (a dead URL, an uncatalogued product) as a board task, because the catalog is in the repo.
- Alerts go to the operator through the ops bot only.

**What it never does.**

- Add a URL that is not in the catalog or given by the operator, or build one from inventory or model text.
- Touch subscriptions that lack the pack's origin tag.
- Remove a source without the 14-day absence window and a notice.
- Auto-apply anything for a client.
- Patch, restart or write on any host.
- Say "you are affected" from a news item.
- Send versions, hosts or IPs to a third party, or query OSV online with a package list.
- Commit a profile or findings to the repo.
- Report "all clear" when a host is blind.

**Policy.**

- For our own scope: auto-add feeds that exist in the catalog, with an ops-bot notice. Auto-apply is limited to catalog entries and is logged. Writes to the hub's system file go through the operator-side script.
- For client scopes: approval is always required.

## 11. Privacy

- **Findings with hosts or versions go only to class A or local models.** Class B and class C routes never carry them. If a prompt must run on another class, give counts and CVE ids only, no hosts or versions. This applies to every reader (assistant or business bot) that reads findings or Zabbix data.
- **The LLM that filters news sees public text only** (section 5), so it may run on any class.
- **Client scopes are separate.** Separate env file, token and state directory (0700) per scope. A client's findings never reach another scope's reader or any person's assistant context. Each scope's token reads only its own host group.
- **Never in git:** profiles, findings, SBOM files, per-scope config. The repo keeps the schema, an example and the generic catalog. Run `privacy_scan.sh` before committing.
- **Experiment data is synthetic** (section 13): no real hostnames or package sets in frozen inputs, no client data.

## 12. Topology: one pack, two configurations

**Shared core, identical for both:** the profile, the findings file, the news-lane feed and the catalog. All are produced by code. Only the LLM reader differs.

**One config file (Planned):** `security_scopes.json`, per scope `{scope, host_selector, reader, mode, lanes}`.

- **All-in-one (personal assistant).** One scope covers all hosts. The assistant reads the security lane and findings, and has the upkeep skill plus the system-administration skills and read-only Zabbix access.
- **Split (business bots).** A news reader reads the news lane of its scope. It holds no SSH key and reads hostile text all day. A technical verifier reads findings through `gateway secwatch` and does the checks. The ops bot sends P0 alerts. The hand-off from reader to verifier goes on the task board at depth 1. This amends the earlier multi-bot design (`MULTI_BOT_TASKS.md`, section 12), which gave the verifier a site-only Zabbix focus and put "crossing inventory with advisories" on the LLM: that crossing is now done by code. Each business bot gets its own Zabbix token per scope.

**Why not split by default.** The evidence says task shape decides:

- Multi-agent research used about 15x the tokens of chat, against about 4x for a single agent, and it fits parallel breadth work, not shared-context work (https://www.anthropic.com/research/multi-agent-research-system). Start with the simplest solution (https://www.anthropic.com/engineering/building-effective-agents).
- A single-threaded agent with shared context is favoured for sequential work (https://cognition.com/blog/dont-build-multi-agents).
- A multi-agent study found gains of up to +80.8% on decomposable tasks and losses of up to -70.0% on sequential ones, over 260 configurations (https://arxiv.org/abs/2512.08296).
- A benchmark shows a single agent degrading with two or more distractor tool domains (https://www.langchain.com/blog/benchmarking-multi-agent-architectures).
- A single-agent-with-skills paper reports selection above 90% up to about 20 skills and declining past 30 (https://arxiv.org/html/2601.04748v2). Caveats: synthetic skills, two models. An assistant with dozens of enabled skills may hit this, so test it.

The strong case for splitting is isolation of keys and actions (client hosts read-only, the news reader sees untrusted text), not efficiency.

## 13. Comparison experiment (Planned, Phase 5)

Question: does the split topology beat the all-in-one one for this task, and does either beat a plain pipeline?

**Arms.**

| Arm | What |
|---|---|
| A | all-in-one clone with the pack and the full skill set |
| A2 | same clone with only the roughly 23-skill security pack and a business-bot prompt |
| B | split: news-reader clone plus verifier clone, real waker, board and polling |
| C | deterministic pipeline plus one LLM call that only writes the message. The cost and correctness floor |

A vs A2 isolates skill dilution and prompt size. A2 vs B isolates the hand-off. Without C you cannot tell whether either topology adds value.

**Fairness.**

- Same model, key and router settings, pinned. Explore mode off, router fallbacks, cooldown switching and local-first off. One retry policy; infra-failed runs are dropped symmetrically across arms.
- Throwaway clones with fresh sessions and no memory. The conclusion applies to a clean assistant, not to a long-running one. State this in the report.
- Synthetic hosts only. Frozen inputs: a synthetic inventory export, a dated KEV snapshot, a dated tracker snapshot, a feed database copy per arm. No real hostnames, no client data.
- Read-only tool permissions. 3 repeats per task per arm, order randomised, paired by task. Half the split runs start asleep.

**Independent answer key.** The key must not come from the pipeline under test (arm C is that pipeline, so a key from it is correct by construction). Build it from independent evidence: an independent scanner's output plus `dpkg --compare-versions` on the frozen inventory, adjudicated by the operator. Use `vuln_watch` only for seeded hosts the scanner cannot see.

**Tasks (about 20).**

- T1: what affects us this week. Seed synthetic hosts and dates; a faithful replay of past weeks is not possible because today's tracker already holds today's fixes. Include decoys such as a PHP-only advisory.
- T2: is host X patched for CVE Y (about 10 synthetic hosts), including a backport, a blind host (correct answer "unknown") and a non-Debian host.
- T3: summarise about 100 hub items labelled relevant or not by the operator, including items beyond the revista cap.
- T4: injection resilience.
- T5: hand-off fidelity (CVE id, host and version survive the hand-off).

Only T1 and T5 exercise the hand-off. Report per task type. Do not roll all tasks into one A-vs-B number.

**Metrics.** Correctness (precision, recall, F1; a confident wrong "patched" is a severe error), missed relevant items, false positives, summary quality (one LLM-judge call plus a 20% human spot-check), tokens summed over session and children at a shadow price (free models cost 0), latency including wake time and board polling, reliability (tool errors, failed turns, variance), operator effort, context tokens per call and tool-description tokens per turn as a dilution proxy.

**Logging.** One SQLite file on the operator's workstation (`runs`, `scores`, `usage`). Answer text stays local, never in git. Board hand-off data (task id, chain, timestamps) is not logged today, so instrumentation is a prerequisite.

**Analysis.** Paired comparison, bootstrap confidence intervals, a sign test. With about 20 tasks, 3 repeats and few hand-off tasks, power is weak: state the minimum detectable effect, or reduce the claim to "no large difference". Stopping rule: if A is within noise of B on correctness and clearly cheaper and faster, keep A as the default; otherwise report B's cost and latency premium per unit of correctness gained.

## 14. Phased plan

Estimates are rough and exclude operator waiting time. They include selftests (the repo has a `*_selftest.py` for nearly every file, picked up by `run_selftests.sh`), English docs and a `privacy_scan.sh` run per phase. Re-estimate after Phase 1.

| Phase | Scope | Effort |
|---|---|---|
| 0 | Unblock and quick fixes: the Zabbix operator steps and a first real dry run on a pilot host; pin the scanner by digest; drop duplicate or failing feeds; add the DLA feed as reading-only; set `attention_for` for system security sources | 0.5 to 1 day, mostly operator |
| 1 | Profile and sources: profile builder (importing the existing Zabbix reader), schema and example, catalog extension (about 25 entries), `sec_sources.py plan\|probe`, per-feed keyword filter and origin field in the hub, nightly timer | 5 to 7 days |
| 2 | Findings and upkeep: non-KEV matching (streaming or SQLite, `MemoryMax`), findings export, EPSS from the bulk file, P0 to P3 rules, per-digest image scan off the Docker host, `gateway secwatch`, upkeep skill, drift and EOL alerts, weekly probe | 6 to 9 days |
| 3 | News relevance and digest: prefilter, closed-world LLM step, security digest lane in the hub client and `publish_person`, the all-in-one configuration | 4 to 6 days |
| 4 | Fallback and clients: forced-command SSH inventory over `vw_inventory.sh` plus the file adapter, client scope paths (separate env and state), Ubuntu source, `sec_crosscheck.py` | 3 to 4 days |
| 5 | Experiment: board hand-off instrumentation, clones, frozen synthetic inputs, 20-task key, 3 arms plus A2 x 3 repeats, analysis | 5 to 8 days of effort, longer calendar |

Build order: Phase 0, then the profile, because every later piece reads it. Do not start Phase 5 before Phases 1 to 3 exist.

## 15. Open decisions

1. Auto-add catalog feeds for our own scope with a notice, or approve each? (Approval is always required for clients.)
2. Which duplicate or failing existing feeds to drop, and whether the other firehoses move to an opt-in `reading` lane or are removed.
3. PHP is out of the shared base image. How does a person who needs it get it (see `DEBIAN13_MIGRATION.md`, open question 1)?
4. Move the image base from Debian 12 to 13, or live with DLA?
5. Scanner: Trivy pinned by digest, or Grype. Decide after the guest measurement.
6. Which machine runs the image scan (desktop or a GPU host, with a memory cap)?
7. Name the missing facts for the manual profile: self-hosted service versions, edge proxy product, hypervisor versions, SaaS use.
8. Proxmox: accept the hand-kept PSA table (no feed exists)?
9. Whether a PHP host is included in the profile (it would bring PHP feeds in).
10. Priority thresholds (EPSS cut-off), to be tuned by the experiment.
11. Per-feed hub origin: add an `origin` field, or a separate pack-owned file?
12. Run the experiment on throwaway clones only, and who adjudicates the T3 labels?
13. Which reader classes may receive findings with hosts and versions (section 11)?

## Unverified or not found

- The Zabbix side in practice (token, template import, UserParameters).
- Scanner coverage of static binaries, scanner RAM and database size.
- Any machine-readable Proxmox advisory feed, and whether Debian, Ubuntu or Proxmox publish CSAF/VEX.
- Whether an independent scanner is available on the operator side for the cross-check in section 8.
- The primary text of one vendor's agent-design guide and the figures of one cited relevance-filter paper.
