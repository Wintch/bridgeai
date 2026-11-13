# The fact model: how to design a monitoring or security data path

Status: design. The model itself is a method and needs no code. The worked example (the Proxmox version-and-vulnerability pilot) is **not built**: every code change and operator step in it is marked "Not built" or "Planned". Anything not confirmed is marked UNVERIFIED.

## Why

A monitoring or security answer ("are my hosts exposed?") is only as good as the path the data took. Before building a feed, write down for each fact:

- where it comes from (and a second, independent source if there is one)
- how many process boundaries it crosses
- what privilege each step needs
- every place a copy ends up, including backups and chat history
- how old each copy can be
- how it fails, and how that failure gets noticed

This turns three vague worries into countable things: "is it minimal?", "where does it leak?", "would we notice if it broke?". The same table is reused for any new path or any client stack: only the collector and the advisory source change.

## Definitions (used the same way everywhere below)

- **Step**: one process boundary crossed on the way from the source of truth (a file or state on the monitored machine) to the consumer (the process that finally uses the value). Each hand-off between two processes counts once, including a network hop and including a process reading a file written by another. The return path is not counted. Steps are counted per fact and per source path.
- **Copy**: any place the value, or a secret needed to get it, is stored for longer than a single request. This includes caches, databases, dumps, backups, session stores, chat history and credentials. A value printed into a model's context is a copy in the session store.
- **Primary / cross-check**: the primary path answers the question. The cross-check is a second path with different failure modes. Two views are never merged silently (see the verdicts in "Alerting and answers").
- **Unjudged**: the system had data but no rule to judge it. It is reported as unjudged. It is never reported as OK.

## What a fact row records

| Column | What goes in it |
|---|---|
| Fact | One question with one answer, for example "installed version of package X". |
| Source paths | Primary, and a cross-check if one exists. If none exists, say so. |
| Steps | Number of process boundaries, with the boundaries listed once in a legend. |
| Privilege per step | The weakest credential or permission that makes the step work. |
| Copies | Every place the value lands, plus the secrets involved. |
| Freshness per copy | How old the value can be at each copy, worst case, and what sets that limit. |
| Failure mode | What happens when a step breaks, and how a human or alarm learns of it. "Nobody notices" is a valid entry and a finding. |

Rules for filling it in:

- A copy you did not locate by looking is a guess. The test plan includes a "locate every copy" check.
- Freshness is per copy. A cache can be older than its source.
- A failure mode with no detection route is a bug in the design, not a note.

## Worked example: Proxmox versions and vulnerabilities

### What already exists, and what is missing

Exists in the repo (committed; deployment not confirmed here):

- `vuln_watch.py`, the "SW inventory daily" Zabbix template and `vw_inventory.sh` already cover the Debian part of a Proxmox node: dpkg inventory, tracker match, KEV, state-file dedupe, ops-bot message. See `VULN_WATCH.md`.

Missing for Proxmox (all Not built):

- `gateway proxmox` reads no versions, and `apt/versions` is not on its allow-list.
- Proxmox-built packages have no Debian tracker rows. Today they are skipped silently, so a green result means nothing for them.
- CISA KEV had no Proxmox, QEMU, KVM, corosync, LXC or Ceph entries when this was checked. Proxmox's own flaws are visible only through its forum advisories (PSAs), which are human-written text with no machine feed (UNVERIFIED that none exists).
- Nothing alerts the stack's person. `vuln_watch` alerts the ops bot only.

Approach: two independent views and a small hand-kept PSA table.

- API view: live, Proxmox-built packages, minimal read-only token.
- Zabbix view: daily, Debian userland and pending updates, minimal read-only Zabbix user.
- PSA table: the only source for Proxmox-origin advisories. A forum poll only nudges the operator when the table may be stale.

### Step legend

API path (consumer: the model):

1. apt and dpkg state on the node, read by the Proxmox daemon.
2. daemon to the Proxmox web proxy.
3. proxy to the gateway process (HTTPS, pinned certificate).
4. gateway to the model.

One more step when the node asked is not the entry node (the proxy forwards to a peer).

Zabbix path (consumer: `vuln_watch`):

1. dpkg database, read by `vw_inventory.sh`.
2. script to the Zabbix agent.
3. agent to the Zabbix server.
4. server to its database.
5. database to the Zabbix API process (`item.get`, `history.get`).
6. API to `vuln_watch`.

### Fact table (pilot)

P1 means the minimal permission tier, see "Minimal permissions".

| # | Fact | Primary / cross-check | Steps | Privilege |
|---|---|---|---|---|
| F1 | pve-manager installed and running version | API `/nodes/<n>/version` and `apt/versions` ManagerVersion. Cross-check: Zabbix dpkg shard (installed only). A vendor "PVE version" item may exist (UNVERIFIED). | API 4. Zabbix 6. | API: valid token only (`/version` needs no ACL). Zabbix: agent user, no root; Zabbix User role with read on one host group. |
| F2 | Running kernel and installed kernels (reboot pending) | API `/nodes/<n>/status` (current kernel) and `apt/versions` RunningKernel plus every `(pve\|proxmox)-kernel-*` entry. Cross-check: `vw.apt` `kernel_running`. | API 4. Zabbix 6. | API: Sys.Audit on `/nodes/<n>`. Zabbix as F1. |
| F3 | Proxmox-built package versions, installed vs repo candidate | API `apt/versions` (see field semantics below). Cross-check: dpkg shards (installed only, no candidate). | API 4. Zabbix 6. | API: Sys.Audit on `/nodes/<n>`. |
| F4 | Debian base packages (openssl, openssh, sudo, glibc, curl, systemd, perl) | Zabbix dpkg shards only. `apt/versions` does not list them. No cross-check inside the pilot; read-only SSH is out of scope as too heavy. | Zabbix 6. | Zabbix as F1. |
| F5 | Pending updates, security count, reboot-required, apt age | Zabbix `vw.apt`. API derived: installed differs from candidate, installed kernel newer than running. `apt/update` is excluded (needs Sys.Modify). | Zabbix 6. API 4. | Zabbix as F1. API: Sys.Audit. |
| F6 | Running QEMU per VM (tier P2, not in the pilot) | API `qemu/<id>/status/current` against installed pve-qemu-kvm. | 4 per guest, plus one call to list guests. | VM.Audit on `/vms`. |
| F7 | Debian vulnerability data | Debian tracker JSON (reduced to KEV CVEs) and CISA KEV JSON. | `vuln_watch` fetch, disk cache, reduce: 3 within the process chain. | None (public). Egress to two hosts. |
| F8 | Proxmox advisories (PSA): package, branch, minimum fixed version | Forum thread, hand-kept table in git (`ops/pve_advisories.json`, Not built). A forum RSS poll as a nudge only, if a usable feed exists (a tested address returned an XML error, so UNVERIFIED). | Latency is however long a human takes to enter a row. | Public read. Table edits are repo commits. |
| F9 | Match result (finding) | `vuln_watch` matcher: Debian origin vs tracker, Proxmox origin vs PSA table, kernel by PSA and installed-vs-running. | Local to one process. | Local only. |
| F10 | Alert and on-demand answer | `vuln_watch` to ops bot. On demand: `gateway proxmox versions` plus an exported summary. | Alert: `vuln_watch` to notifier to chat service. On demand: API 4, plus a summary file read. | Ops-bot token on the ops host. |
| F11 | Credentials | Proxmox token secret and certificate fingerprint, Zabbix tokens. | Operator creates them, persisted in the stack. | Operator only. |

#### Copies, freshness and failure per fact

| Fact | Copies (everywhere it ends up) | Freshness per copy | Failure mode and how it is noticed |
|---|---|---|---|
| F1 to F3, F5 via API | Node state (authoritative). Nothing stored by the API itself. Printed output sits in the model context, so it lands in the stack's session store, memory files, chat database, daily archives and the provider's retention (see "Where copies hide"). Gateway log keeps counters only. | Live. Candidate versions depend on the node's last apt update, which the API does not report: age unknown via API. | Token refused or timeout: the subcommand prints the error and the `/version` fallback, never a blank. A broken repo gives stale candidates with no alarm on the Proxmox side (only the Zabbix `lists_age_s` shows it). |
| F1 to F5 via Zabbix | Node dpkg. Zabbix history, latest-value cache, server value cache, the Zabbix database and any dump of it (UNVERIFIED whether dumps exist), housekeeping and audit tables. `vuln_watch` memory. | Collected daily. An unchanged shard can look up to 8 days old (heartbeat 7 days). `vw.apt` has no heartbeat and is the daily clock. Worst case for pending updates is about two days. | Shard missing or too old: host marked blind in the message. Inventory cut by the size cap: host "partial", and no "fixed" lines for it. |
| F2 (kernel) | As above. | As above. | `vw_inventory.sh` looks only for `linux-image-N`, so `kernel_installed` is empty on a Proxmox node until it is extended. Until then the answer is "unknown", not OK. |
| F7 | Upstream feed. Gzip and reduced caches in the tool's state directory (mode 0700). | Tracker regenerated about hourly, KEV several times a week, cache accepted up to 7 days. | Download fails and cache is older than 7 days: the run exits non-zero and the failure alert fires. An empty feed is rejected. |
| F8 | Forum. Git repo and its mirror. `vuln_watch` memory. Last-seen PSA marker in the state file. | A PSA appears after the fix reaches the enterprise repo. Whether the free repo leads or lags is UNVERIFIED. | Weakest link: a stale table looks like "no advisories". The table carries `reviewed_on` and every message footer prints it. A forum change with no table change is a hard "table needs review". If the poll itself fails for N days, that is flagged. |
| F9 | State file (host, CVE or PSA, package, installed, fixed, first and last seen). Message text. Never the full package list. | Per nightly run. | Unmatchable packages are counted as "unjudged", never skipped. |
| F10 | Chat service server-side history (the ops-bot chat), the notifier outbox, the ops host log. On demand: the stack's session store. | Nightly, or at query time. | Notifier failure: exit code and the failure alert unit. Stack asleep: the waker handles it and the next wake reads the summary. |
| F11 | **Proxmox secret:** persisted stack `.env` and live `.env` of the awake container, plus every daily archive that contains them. The cluster stores the token hash in its config and its token store is replicated to all cluster nodes (public Proxmox behaviour, UNVERIFIED here). **Zabbix token:** hash in the Zabbix database, master gateway config, per-stack copy by the sync script, archives. **`vuln_watch` token:** the ops host env file, separate from the stack. A vendor Zabbix template would add a third Proxmox token held by Zabbix, which is why the pilot avoids it. | Proxmox token expiry about 90 days. `vuln_watch` Zabbix token about 30 days. | Expired token: 401 or 403. `vuln_watch` refuses a Zabbix user whose role is not type User (exit 2). |

If option (a) of C1 is chosen (a separate version credential, see "Minimal permissions"), it adds one more at-rest secret copy per stack and must be added to the F11 row.

### Where copies hide (check this list for every new path)

- **Daily stack archives.** The stack backup archives each stack's state (memory, skills, sessions), workdir and chat database daily, 7 generations by default, in a private directory. They contain the stack `.env` (so every token in it) and any printed output. Small text files and fingerprints are kept longer (about 30 days).
- **Session and memory stores.** The agent may save versions into its memory files.
- **Chat history.** The chat database, the chat service's server-side history, and the ops-bot chat that receives alerts.
- **Model provider retention.** Depends on the data class of the stack.
- **Exported summaries.** `vuln_summary.json` in the stack workdir lands in the archives too.
- **Ops host.** The tool's state directory and the env file holding the Zabbix token, if the ops host is backed up (UNVERIFIED).
- **Zabbix.** Database, any dump, audit and housekeeping tables.
- **Proxmox.** Token hash in cluster config, the replicated token store, the `pkgupdates` cache.

Totals for the pilot, once located: the Zabbix path touches the node, Zabbix history and caches, the Zabbix database (and dumps), `vuln_watch` memory and state file, the chat message and the notifier outbox. The API path touches the node plus the stack's session store and everything that archives it. Fill in real counts only in private notes.

## Proxmox API field semantics (`/nodes/<n>/apt/versions`)

Settled from the Proxmox source (master branch; PVE 8.x behaviour not read, so confirm in step 0):

- Installed package: `OldVersion` is the installed version. `Version` is the candidate, or the installed version if there is no candidate.
- Not installed package with a candidate: `Version` is the candidate and `OldVersion` is absent. Not-installed entries are dropped from the optional package list but are returned for the mandatory list.
- `ManagerVersion` is the running pve-manager API server version.

Parser rules (Planned, Not built):

- Gate on `CurrentState == "Installed"` before reading anything as installed.
- Installed version = `OldVersion`. Never read `Version` as installed: a not-installed mandatory package would otherwise report an available version as installed.
- Candidate newer than installed means a pending update. The answer states "candidate as of the node's last apt update, age unknown via API".
- Test fixtures must include a NotInstalled-with-candidate entry.

Debian base packages are not in this endpoint. `openssl` and `openssh` versions come only from the Zabbix dpkg inventory.

## Minimal permissions

### Proxmox (operator runs, once per cluster or standalone node)

Tier P1 needs Sys.Audit on `/nodes`. This is narrower than the usual read-only auditor role. Both the user and the token need the ACL, because the token has privilege separation.

```
pveum role add VersionAudit --privs "Sys.Audit"
pveum user add <audit-user>@pve --comment "version read-only"     # no password, cannot log in
pveum acl modify /nodes --roles VersionAudit --users <audit-user>@pve
pveum user token add <audit-user>@pve <token-id> --privsep 1 --expire <epoch about 90 days out>
pveum acl modify /nodes --roles VersionAudit --tokens '<audit-user>@pve!<token-id>'
```

Header: `Authorization: PVEAPIToken=<audit-user>@pve!<token-id>=<secret>`. The secret is shown once.

- **Can read:** `/version`, `/nodes/<n>/version`, `/nodes/<n>/status`, `/nodes/<n>/apt/versions`, `/nodes/<n>/apt/repositories`.
- **Cannot do:**
  - Read `apt/update` or `apt/changelog` (both need Sys.Modify, so they are excluded). The node `report` file is not allow-listed because it dumps config.
  - Read `/cluster/status` (needs Sys.Audit on `/`).
  - Read VM, storage or Ceph data, or change anything. Sys.Audit does expose node status and cluster and HA config (topology, no secrets).
- **Not granted on purpose:** Sys.Modify (network, firewall, certificates, services, repositories, time).
- **Later tiers:** P2 adds VM.Audit on `/vms` (running QEMU). P3 adds audit on `/` (Ceph running versions, cluster status).

UNVERIFIED: that Sys.Audit at `/nodes` alone is enough in practice (propagation and the node listing permission were not tested), the exact contents of the built-in auditor role on PVE 8.x, and the exact `pveum` flag spelling on the installed release. Step 0 and step 1 settle these.

#### C1: the minimal token must not break existing commands

The existing `gateway proxmox` commands `estado`, `vms` and `backups` use `/cluster/resources`, `/cluster/tasks` and `/cluster/backup*`. With more than one configured host the command also calls `/cluster/status` for cluster-name dedupe. A token that only has Sys.Audit on `/nodes` gets a 403 there, and the per-host loop prints a permission error.

Decide explicitly, as an operator decision:

- **(a)** `versions` gets its own credential (for example a separate version-token variable per entry). Cost: one more at-rest secret copy per stack, counted in F11.
- **(b)** Keep the existing read-only auditor token for the pilot. Test the minimal token as its own step with the expected failures listed.

Either way (Planned, Not built):

- The `versions` path skips the cluster dedupe, or catches its 403 explicitly.
- A selftest covers "minimal token plus `estado`": degradation is graceful, not an error for the whole entry.

### Zabbix (operator runs; needs a Super admin token used only by the operator)

- **Host group** holding only the pilot node(s) (for example `<group>/pve-pilot`). A user-group tag filter applies to problems only, so host-group read is the only hard boundary for items and history.
- **Role** (for example `vulnwatch-ro`):
  - type User, because `vuln_watch` refuses any other type
  - API access on, mode allow-list
  - explicit list: `user.checkAuthentication`, `hostgroup.get`, `host.get`, `item.get`, `history.get`
  - UI default access off, modules default off, actions default off
- **User group:** frontend disabled, read permission on the pilot host group only.
- **User:** the role above, in that group.
- **Token:** one, expiry about 30 days, mode 600 in the ops host env file.
- **Cannot do:** any write (`host.update`, `item.create`, `template.*`), see other groups, or call `problem.get` / `event.get`. This token is not given to a stack. A stack's own gateway user is separate.

**Not built, and new work:** `provision.py` today creates users with the built-in role id 1 only. A custom User-type role with an API allow-list does not exist yet. It needs a new `vulnwatch-user` subcommand (see "Code changes").

UNVERIFIED: whether `user.checkAuthentication` with a token is exempt from the role allow-list (it stays on the list because `vuln_watch` calls it first and exits 2 without it), whether Zabbix 7.0 tokens inherit host-group permissions (the repo relies on it), and the 7.0 wording for an empty allow-list (always set an explicit list).

The vendor "Proxmox VE by HTTP" template is not used. It needs a third Proxmox token, gives only manager and kernel strings, and has no package data. If "PVE version" items already exist on a node, they stay as a free cross-check (UNVERIFIED that they do).

## Matching by package origin

Classify the origin first. Use `apt/versions` Origin when the package is listed. Otherwise use the name set (`pve-*`, `proxmox-*`, `libpve-*`, `qemu-server`, `lxc-pve`, `pve-container`) plus the version suffixes `pve` or `pmx`. The Zabbix dpkg inventory carries no origin, so this heuristic is the only classifier for packages outside the API list. Its completeness is UNVERIFIED.

**Default for a Proxmox host: a package whose source is absent from the tracker and not in the PSA table is "unjudged", never OK.** The unjudged count is printed by name pattern, and a test enforces it.

| Origin | Advisory source | Rule | Cadence |
|---|---|---|---|
| Debian (openssl, openssh, sudo, glibc, curl, systemd, perl) | Debian tracker by **source** package and release codename (the Debian release under the Proxmox major version), plus KEV | Exact dpkg version compare (already built). **The pilot alerts on KEV only**, as built today. Non-KEV findings appear only as a count in the message footer, or in an on-demand `status` section. | Nightly |
| Proxmox-built (pve-manager, qemu-server, pve-qemu-kvm, lxc-pve, libpve-*, pve-container, ...) | Hand-kept PSA table (`ops/pve_advisories.json`, Not built): PSA id, date, branch, package, `fixed_min`, CVEs if any, plus a top-level `reviewed_on` date | dpkg compare against `fixed_min`. Installed below `fixed_min` is AFFECTED. No row for the package means "unjudged by CVE". A newer candidate in the Proxmox repo is a digest-only signal. | Table: hand-kept. Poll: daily nudge. |
| Same-name rebuilds (corosync, frr, grub2, systemd, libtpms, ceph, lxcfs, swtpm, open-iscsi, fwupd, lvm2, apparmor) | PSA table; Debian tracker as information only | **The rebuild trap:** if the installed version carries a `pve` or `pmx` suffix, never emit "fixed" or "ok" from Debian data. A Proxmox rebuild version can compare as newer than the Debian fix even when it lacks the backport (a false negative, measured). Emit "unjudged by Debian, see PSA". | As above |
| Kernel (`proxmox-kernel-*`) | PSA table only. Never the Debian `linux` source: its fixed versions do not apply. | Judged by the PSA table and installed-vs-running only. A newer installed kernel than the running one means reboot needed. A newer candidate is a digest line. The message states "kernel judged by PSA and update state only". | Nightly, plus live via API |
| Debian `linux-image-*` or `linux-signed-*` on a Proxmox node (UNVERIFIED how common) | none | When `kernel_running` ends in `-pve`, label them "installed, not running". Drop them from AFFECTED. Digest only. | Nightly |

Honesty rules, inherited from `vuln_watch`:

- Unknown is never OK.
- The last line of every message and answer carries the counts judged, unjudged, blind and partial, plus the PSA-table review date.

PVE 7 is Debian 11. `vuln_watch` supports Debian 11 to 14, but the tracker may not carry that codename. The existing "unsupported" state covers it; it is on the test list.

## Alerting and answers

### Nightly alert

- **One alerter:** `vuln_watch` to the ops bot. The stack is not a second alerter, so there are no double messages.
- **Dedupe by state key:** `host|CVE|package` for CVE findings. PSA findings are grouped **per host and package**: the key is `host|package` with the highest `fixed_min` and the list of PSA ids, so a node far behind gets one line, and one upgrade closes all its PSAs in one "fixed" line.
- **One message per run**, never one per finding. The first run with no saved state sends a summary only.
- **Events:** new finding; AFFECTED finding that gained a fix; finding now fixed; KEV due within 7 days (once); host newly blind; "table needs review".
- **Quiet hours:** `ops/lib/notify.py` has none. Its `quiet` option is a re-send throttle in seconds, and `send()` has no silent flag. Holding non-urgent items to a morning slot is therefore new code (Not built). Options:
  - drop the urgent/non-urgent split in the first cut
  - set the run time through a local systemd drop-in, not the tracked timer file
  - add a `--silent` option to `ops/lib/notify.py` that sets the chat service's no-notification flag
- The timer has no timezone in the tracked file, so it runs in the ops host's local zone. Do not write that zone into the repo.

### PSA poller (untrusted input)

- Adds one egress host (the Proxmox forum) to a tool that today talks only to Zabbix, the KEV host and the Debian tracker host. Document it.
- Forum text is untrusted. Reuse the existing control-character and 64-character sanitising before any of it reaches a message.
- If no usable forum feed exists, the nudge becomes a time-based reminder: the table is flagged for review when `reviewed_on` is older than a set age.
- The poller **proposes rows only**. It never writes the table, because the HTML format can drift.
- "Forum activity with no table change" is a hard "table needs review" state.
- If the poll itself fails for N days, flag that. Silence must not read as "no advisories".

### On-demand answer ("are my Proxmox hosts exposed?")

1. `gateway proxmox versions [--host NAME]` (Not built): the live API view. Prints manager version, running kernel vs newest installed, installed vs candidate for Proxmox packages, and a verdict per package from the PSA table shipped in the repo. Every line carries an "as of" time.
2. The Zabbix view. `gateway zabbix` cannot read the dpkg shards (`lastvalue` is cut to 140 characters and only numeric items use `history.get`). It cannot read `vw.apt` either (up to 2 KB of JSON, same 140-character cut). Two options:
   - `vuln_watch --export-summary` writes `vuln_summary.json` (per host: findings, blind or partial state, inventory age, key versions, PSA review date; no package list), and a new `gateway vulns [HOST]` reads it. This adds one copy in the stack, which lands in the archives.
   - Use the dependent items (`vw.apt.pending`, `vw.apt.security`, `vw.reboot`, `vw.kernel.running`, `vw.kernel.installed`), which are short and readable with `gateway zabbix item`. This covers apt age and pending counts but not findings.
3. Optionally `gateway zabbix item <host> "PVE version"` as a third cross-check, if that item exists.

Compare the same packages in both views (pve-manager, kernel packages, pve-qemu-kvm, qemu-server, lxc-pve, corosync). Print both values and one verdict. Never merge silently.

| Verdict | Condition | Meaning and action |
|---|---|---|
| AGREE | Same versions. | Report once. |
| LAG | API newer than Zabbix, inventory under about 26 hours old. | An update happened since collection. Trust the API for "installed". Wait one cycle. |
| STUCK | The lag lasts more than 2 cycles (48 hours). | The Zabbix item or agent is stuck. Say so and name the host. |
| CONFLICT | Zabbix newer than API, or version families do not line up. | Probable host mapping error (node names can repeat across hosts, so map by Zabbix group). Say "mapping problem, trust neither". |
| ONE-SIDE-BLIND | One view failed (API down, Zabbix down, token expired). | Report the other view and say which one is missing. Never "all clear". |

Candidate versions from the API have unknown age. Say so in the answer.

## Code changes, smallest first

All items are **Not built**. Operator-run items are marked [OP]: writes to a host or VM go through the operator, and the agent verifies read-only.

1. **`gateway.py` and its selftest.**
   - Allow-list `/nodes/<n>/version` and `/nodes/<n>/apt/versions` only. Add `versions [--host NAME]`.
   - Skip the cluster dedupe on this path. Degrade on a 403: print what `/version` gave and say which permission is missing.
   - Selftests with a fake API: the two paths accepted; `apt/update`, `apt/changelog` and the node report still rejected; a 403 handled; "minimal token plus `estado`"; installed-vs-candidate parsing with a NotInstalled-with-candidate fixture; a kernel mismatch reported.
2. **`zabbix/provision.py`:** new `vulnwatch-user` subcommand (custom User-type role with API allow-list, host group, user group, user, token) and a `vulnwatch-test` check that a write is refused and other groups are invisible. [OP] runs it with the Super admin token.
3. **`vuln_watch.py`** (extend; no new tool):
   - origin classification with the `pve`/`pmx` rule and the unjudged default
   - PSA table loader and match, reusing the existing dpkg compare; PSA findings grouped per host and package
   - kernel handling by PSA and installed-vs-running; Debian `linux-*` labelled "installed, not running" on `-pve` kernels
   - non-KEV Debian findings as a footer count only. If the filter is ever widened, give the reduced cache a second key, test its size, and cap lines per host per run.
   - unjudged count in the footer; `--export-summary`
   - selftests: fixed, affected, the `pmx` trap, blind, stale, PVE 7
4. **`zabbix/vw_inventory.sh`:** report installed `proxmox-kernel-*` and compare with `uname -r`, so `kernel_installed` and reboot-needed work. Check that the "installed kernel changed" trigger and its dependent item do not go unsupported on an empty value (UNVERIFIED). Whether a Proxmox node writes the reboot-required file is UNVERIFIED, so do not rely on it. [OP] reinstalls the script and the `UserParameter` file on the pilot node.
5. **PSA poller** in `vuln_watch.py`: conditional GET of the RSS feed, change detection, the "table needs review" nudge, proposed rows in the message or a log, sanitising, a failure flag after N days.
6. **`ops/pve_advisories.json`** (new, in git, public advisory data) with `reviewed_on`. Rows are operator-reviewed.
7. **`gateway vulns [HOST]`**, the summary sync, and doc updates (`SKILL_proxmox.md`, which today tells the agent to read Zabbix text items; `VULN_WATCH.md`; this file).

### The Zabbix agent on a hypervisor is a host write

Installing the agent, `vw_inventory.sh` and the `UserParameter` file adds a package and a script on the hypervisor, and needs outbound access from the node to the Zabbix server (active mode only).

- Record the firewall change needed.
- Rollback: stop the agent, remove the two files.
- It stays on the operator's decision list. It is the only route to openssl and openssh versions without SSH.

## Operator-run steps

- **Step 0, read-only recon, one node** (nothing is changed):
  - check whether the Zabbix user, role and the SW-inventory template already exist
  - dump one raw `apt/versions` response: confirm the field semantics on the node's real release, that `openssl` and `openssh` are absent, and the package count
  - confirm the Proxmox release, the agent mode, and whether "PVE version" items exist and from which template
- Create the Proxmox role, user and token; load the token secret and certificate fingerprint into the stack with the existing add script. Which token goes in follows decision C1.
- Zabbix: create the host group, link "SW inventory daily" on the pilot node, install the agent, `vw_inventory.sh` and the `UserParameter` file, run the `vulnwatch-user` subcommand.
- Put the `vuln_watch` token in the ops env file and recreate the stack.
- Before any redeploy: check `git status` (a redeploy ships the working tree) and check that the stack can reach the node's API port (a firewall opening may be needed, UNVERIFIED).

## Test plan

Results and the pilot node's raw `apt/versions` dump go to the git-ignored private notes only, never to the repo.

Steps:

1. **Step 0** as above.
2. Create the Proxmox credential. Run `gateway proxmox versions` from the guest stack. If using option (b) of C1, repeat with the minimal token as its own step and record the expected failures.
3. Create the Zabbix group, role, user and token. Link the template on one node. Wait one collection, or trigger one run.
4. Run `vuln_watch` in dry-run for the node. Check that it judges the node and prints counts.
5. Seed a test PSA row with `fixed_min` above the installed pve-manager. Expect exactly one alert, and no repeat on a second run. Lower the row below the installed version and expect one "fixed" message.
6. Ask the stack the on-demand question. Check that both views and the verdict line appear.
7. Leave it running for a week. Check the digest behaviour, the stale-table footer and the forum-poll failure flag.

Success criteria:

| Item | Target |
|---|---|
| Steps per fact | Match the legend: API 4 (one request per node), Zabbix 6. |
| Copies | **Locate every copy, including archives.** Look in the stack session store, memory files, chat database, daily archives, the exported summary, the Zabbix database and any dump, the ops host state directory. Compare with the copies table. |
| Leaks | Fail if the state file contains a package list, if the gateway log contains output text, or if any session store or archive contains output you did not expect. The gateway log is not the only place to look. |
| Answer time | A few seconds for `gateway proxmox versions` (to be measured). |
| Inventory age | At most about 26 hours normally, with the 48-hour and 8-day blind thresholds visible. |
| Alert dedupe | One message per change, zero repeats. |

Negative tests:

- **Permission denied:** a token without the ACL gets a 403 on `apt/versions` while `/version` works, and the command degrades with a message. The minimal token with `estado` degrades gracefully. The Zabbix role refuses `host.update` and `problem.get`, and other groups are invisible.
- **Not-installed entry:** a NotInstalled-with-candidate fixture never reports the candidate as installed.
- **Rebuild trap:** a `pmx`-suffixed version against a Debian fix is "unjudged", never fixed.
- **Unknown origin:** a package with no tracker row and no PSA row is "unjudged", with the count printed.
- **Debian kernel on a Proxmox node:** labelled "installed, not running".
- **Flood control:** a fixture node far behind produces one grouped PSA line per package, and the first run is a summary only.
- **Stale apt cache:** `lists_age_s` is surfaced. Use fixtures; making a node's apt stale is a host write.
- **Zabbix down:** `vuln_watch` exits non-zero and the failure alert fires. The stack answers with the API view only and says the Zabbix view is missing.
- **API down or token expired:** `gateway proxmox` fails with a clear error. `vuln_watch` is unaffected. The answer says the API view is missing.
- **Feed down:** the cache is used up to 7 days, then the run fails loudly.
- **Forum poll down or hostile text:** the failure is flagged after N days; control characters and long text are cleaned.
- **Agent stopped:** after 48 hours the host goes blind. Use a fixture or a time shift.
- **Node-name collision:** two hosts with the same node name map by Zabbix group, with no cross-talk.
- **PVE 7:** the host shows as unsupported, not OK.

## Reuse for a client

The same table columns apply to any stack. For each fact record steps, privilege, copies, freshness and failure mode. Swap only:

- the collector (API token, Zabbix item, or read-only SSH)
- the advisory source per package origin

Keep unchanged: the origin split, the "unjudged" state, the "as of" stamps, the disagreement verdicts, the footer counts, and the "locate every copy" check. Add the client's own backup and history locations to the copies list before building anything.

## Open decisions for the operator

1. **Credential (C1):** separate version credential (a), or keep the existing auditor token and test the minimal one as its own step (b)?
2. Vendor "Proxmox VE by HTTP" template: skip it (recommended, avoids a third token), or keep any existing items as a cross-check?
3. Is a Zabbix agent plus `vw_inventory.sh` on the hypervisor acceptable?
4. Alert timing: drop the urgent/non-urgent split, use a local timer drop-in, or add `--silent` to `ops/lib/notify.py`?
5. Debian filter: KEV only for the pilot (recommended). Widen later, with a second cache key and caps, and maybe add EPSS?
6. PSA table: hand-kept with the forum nudge (recommended), or also scraped proposals?
7. Kernel policy: PSA plus update state only (recommended), with an optional KEV check line.
8. How the stack gets the Zabbix view: exported summary (one extra copy) or dependent items only for the first cut?
9. Data class: version data of the operator's own infrastructure passes through the model context. Confirm the stack's agreed data class covers it, and what the provider retains.
10. Cluster or standalone: one entry per cluster or per node (without `/cluster/status`, duplicate entries are not auto-detected).

## UNVERIFIED, in one list

- `apt/versions` behaviour on PVE 8.x (the semantics above come from the master branch), and the PVE 8.x auditor role contents.
- Whether Sys.Audit alone at `/nodes` is enough in practice.
- Ceph endpoints on a cluster without Ceph.
- Which template feeds any "PVE version" or "Kernel version" item, and whether the SW-inventory template and agent are present on Proxmox nodes.
- Zabbix 7.0: `user.checkAuthentication` vs the role allow-list; whether tokens inherit host-group permissions.
- `item.get` `lastvalue` truncation (the repo claims 140 characters).
- Whether the `apt/update` Sys.Modify restriction was relaxed in released versions.
- Whether PSAs exist in any machine-readable form; whether Proxmox is a CNA.
- Which Proxmox rebuilds reuse Debian source names, and the effect of apt pinning.
- Reboot-required file on a Proxmox node; whether Debian kernel packages sit beside Proxmox kernels.
- Whether the Zabbix database is dumped anywhere; whether the ops host is backed up.
- The ops host timezone and any silent-delivery support in `ops/lib/notify.py` (the code shows none).
- Reachability of the node from the stack.
- Package counts and shard sizes on a real node.
