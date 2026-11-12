# vuln_watch: installed software against CISA's known-exploited list

Zabbix knew each host's OS banner and a package count, and nothing about what is installed. `vuln_watch.py` closes that gap for one question: **is any software that is being exploited right now installed on one of my machines?** Every night the ops host reads a software inventory out of Zabbix, matches it against CISA's Known Exploited Vulnerabilities catalog (KEV) and the Debian security tracker, and sends the operator one message per run, only when something is new.

Scope of this phase: Debian hosts, KEV only. Everything else is listed under "Later phases". Like the rest of the Zabbix integration it only watches: nothing here installs, updates or restarts anything, and the agent side is read-only.

## Pieces

| Piece | Where | Job |
|---|---|---|
| `zabbix/vw_inventory.sh` | each monitored host, `/etc/zabbix/vw_inventory.sh` | prints the installed packages (`dpkg` subcommand) and the update state (`apt` subcommand); no root, no network |
| `zabbix/vuln_watch_userparams.conf` | each monitored host, agent `.d` directory | exposes the script as the items `vw.dpkg[N,M]` and `vw.apt` |
| `zabbix/template_sw_inventory.yaml` | imported in Zabbix 7.0 | template `SW inventory daily`: collects the items once a day, plus dependent items and three informational triggers |
| `vuln_watch.py` | the ops host | reads the inventory through the Zabbix API, matches, notifies |
| `vuln_watch_products.json` | next to `vuln_watch.py` | KEV entries for software that Debian does not track (vendor repositories) |
| `vuln-watch.service`, `vuln-watch.timer` | user units on the ops host | the nightly run (about 05:40, with up to ten minutes of random delay) |
| `vuln_watch_selftest.py`, `vw_inventory_selftest.py` | repo | offline tests, picked up by `run_selftests.sh` |

### Data contract

All items are type "Zabbix agent (active)", collected once a day.

- `system.sw.os.get`: the agent's built-in OS record (JSON text). `vuln_watch` reads `product_name`, `version_pretty` and `major`; any field may be missing.
- `vw.dpkg[N,4]` for N = 0..3: shard N of 4 of the installed packages (dpkg's second status character `i`, `U`, `F`, `H`, `W` or `t`: installed or partly installed, so held packages, status `hi`, are included; removed and purged ones are not). One tab-separated line per binary package: `binary`, `version`, `source`, `source_version` (all four always filled; an unknown source falls back to the binary name and version). A package lands in shard `cksum(name) mod 4`, where `cksum` is the POSIX CRC printed by `printf %s NAME | cksum`, so the split is stable and needs no state. Binary names are unique within the host (multi-arch duplicates appear once, without an `:arch` suffix). The first line is a header `#vw.dpkg shard=N of=4 count=K` (K counted before any cut). A shard is capped at 60000 bytes; when cut, the last line is `#truncated`. A host without dpkg answers the single line `#nodpkg`. If `dpkg-query` fails the script prints nothing and exits 1, so the item turns unsupported and the host shows up as blind, rather than reporting an empty shard.
- `vw.apt`: compact JSON, at most 2 KB: `pending`, `security` (suites containing `-security`), `security_pkgs` (up to 20 names), `reboot_required`, `lists_age_s`, `kernel_running`, `kernel_installed`, `kernel_installed_pkg` (the newest installed `linux-image-*` of the running kernel's flavour, for example `-amd64`; other flavours and debug packages are ignored). A host without apt answers `{"error":"no-apt"}`. It reads the apt lists cache, so it says what the host last knew, not what the archive has today.

Why shards: a text item holds a limited amount, and a desktop with 3000+ packages produces about 160 KB in total, roughly 40 KB per shard. Four shards of one script run each keep every value well under the cap and each call under a second. A host with about 4400 packages would reach the cap and be flagged "partial" (see below); raise the shard count in the script, the userparams call and the template together if that happens.

The template also has dependent items (`vw.apt.pending`, `vw.apt.security`, `vw.reboot`, `vw.kernel.running`, `vw.kernel.installed`, `vw.os.pretty`) and three triggers at severity Information with event tag `tier=info`: installed kernel changed, OS version changed, reboot pending. These feed dashboards only (`tier:info` matches no action, see ZABBIX.md); `vuln_watch` does not need them. The template fills no host inventory field, so it links next to the vendor Linux template without a conflict.

## Setup

1. **A read-only Zabbix user.** Create a user (for example `vulnwatch`) with the plain **User** role, read permission on the host groups to cover and nothing else, and an API token with an expiry of about one month. Put it in `ops/ops.env` on the ops host (never in git):

   ```
   VULNWATCH_ZBX_URL=https://zabbix.example/          # site root or the api_jsonrpc.php address
   VULNWATCH_ZBX_TOKEN=...
   VULNWATCH_GROUPS=group one,group two               # optional; default: every readable group
   ```

   `vuln_watch` calls `user.checkAuthentication` first and accepts only a token whose user has role type User; Admin, Super admin or an answer without a type is refused (exit 2): a token that can change Zabbix does not belong in this file. The URL must be `https://` (plain `http://` is accepted only for a loopback address, or with `VULNWATCH_ALLOW_HTTP=1`), and a redirect is never followed, so the token is not re-sent to another address. In code it can only ever send `user.checkAuthentication`, `hostgroup.get`, `host.get`, `item.get` and `history.get`. Rotate the token before it expires; an expired token makes the service fail and alert through the ops bot.
2. **Import the template.** Import `template_sw_inventory.yaml` (Data collection > Templates > Import), then link `SW inventory daily` to the hosts next to the vendor Linux template. The template populates no host inventory field, so the two do not conflict.
3. **Install the script on each host.** Copy `vw_inventory.sh` to `/etc/zabbix/vw_inventory.sh` (root-owned, mode 0755) and `vuln_watch_userparams.conf` to the agent's `.d` directory (`zabbix_agent2.d` or `zabbix_agentd.d`), restart the agent, and test as the agent would run it: `zabbix_agent2 -t 'vw.apt'` and `zabbix_agent2 -t 'vw.dpkg[0,4]'`. The item timeout is set per item in the template (30 s, Zabbix 7.0), so the agent-wide timeout does not need to change. The hosts must use active checks.
4. **Restrict the Zabbix API.** The API is on the same port as the frontend. Allow that port from the ops host and the people who need it, and nobody else.
5. **The timer.** `deploy_ops.sh` installs and enables every tracked user timer, so `vuln-watch.timer` arrives with the next deploy. Until `VULNWATCH_ZBX_URL` and `VULNWATCH_ZBX_TOKEN` exist in `ops.env` the run prints `vuln_watch: not configured` and exits 0: no request, no message.
6. **Pilot on one host.** Link the template to one Debian host, let the items collect (a daily item is first polled shortly after the agent loads it; the first full inventory is in within a day), then run `vuln_watch.py status` and `vuln_watch.py run --dry-run --host NAME` on the ops host and read the output before linking the rest. The first real run with no saved state sends one summary message (counts plus up to 20 lines), not one message per finding.

## How a host is judged

Per host, in this order:

1. **Not inventoried**: none of `vw.dpkg[*]` / `vw.apt` exists on the host. Counted and listed by `status`, never alerted.
2. **Unsupported**: the OS is known and is not Debian (for example Ubuntu), the Debian release cannot be identified (no codename in `version_pretty` and no major version 11 to 14), the release is not covered by the Debian tracker at all (typically an end-of-life release: it was never judged, so it must not look verified), or the host answers `#nodpkg`. Listed, not alerted. The check runs before the freshness check so a non-Debian host is not also reported as blind.
3. **Blind**: the inventory is not trustworthy. Any of these makes a host blind: the OS cannot be read (`system.sw.os.get` missing, in error or empty); `vw.apt` is missing, in error or older than 48 hours; a shard item is missing or in error; a shard has no value in the last 9 days or has not been seen for 8 days; a shard has no header, or fewer package lines than the `count=` in its header (without a `#truncated` marker); the whole inventory holds no packages; or the host's data cannot be parsed or matched (it is then isolated, so the other hosts are still judged). The shards are judged more loosely than `vw.apt` because the template discards an unchanged shard (heartbeat 7 days), so a healthy but unchanged shard legitimately has an old timestamp. A host that newly becomes blind is mentioned in the run's message; a host that stays blind is not repeated.
4. **OK**: Debian, with a codename, and a current inventory. Its packages are parsed and matched. If any shard ends with `#truncated` the host is **partial**: still matched, flagged in `status`, and a partial host never produces a "fixed" line (a cut inventory cannot prove that something was fixed).

The Debian release comes from the codename in `version_pretty` (`... (trixie)`), else from the major version: 11 bullseye, 12 bookworm, 13 trixie, 14 forky.

## Matching rules

The data comes from two cached feeds: the KEV catalog and the Debian security tracker, which is reduced on load to the CVEs that are in KEV. Each feed is fetched with a conditional GET (ETag and Last-Modified where the server sends them, gzip accepted). If a download fails, the cache is used while it is younger than 7 days; beyond that the run fails (exit 1) so the unit's `OnFailure` alerts. A feed that parses but is empty (a KEV catalog with no entries, a tracker without any release data) is rejected like a failed download, so the cache stays and no finding is wrongly marked fixed. The reduced tracker is cached under the hash of both raw feeds, together with the list of releases the whole tracker carries, so a run where nothing changed skips parsing. The tracker's `Last-Modified` changes often, so most nights download and parse it: that is about 90 MB of JSON and needs roughly 0.5 GB of free RAM for a few seconds. The unit runs at idle I/O priority with a 30 minute start timeout.

**Debian packages: the tracker decides.** Matching is by *source* package and *source* version, because that is how the tracker is organised. For a KEV CVE with a tracker entry for the host's release:

| Tracker entry for the host's release | Result |
|---|---|
| `resolved`, fixed version `0` | not affected, skipped |
| `resolved`, installed source version older than the fixed version | **VULN_FIX**: vulnerable, a fix is available (the fixed version is shown) |
| `resolved`, installed version equal or newer | patched, nothing reported |
| `open` or `undetermined` | **AFFECTED**: installed, no fix in that release |
| no entry for the release, or a resolved entry without a usable fixed version | skipped |

Versions are compared with the exact dpkg algorithm (epoch, upstream, revision, `~` before everything, letters before non-letters), implemented in Python and cross-checked in the selftest against `dpkg --compare-versions` when dpkg is present. The installed version is the one dpkg reports, binNMU suffixes included. If several binaries of one source differ in version, the oldest source version counts, except for the kernel (below).

**The kernel.** On Debian the installed kernel image is built from a signed wrapper source (`linux-signed-<arch>`) that the tracker does not know, while the tracker files kernel CVEs under source `linux`. Binaries whose source starts with `linux-signed-` are therefore matched as source `linux` at the binary's own version (which equals the `linux` source version). For source `linux` the newest installed version counts instead of the oldest, because old kernel header and image packages stay installed after an upgrade and are not what runs; a pending reboot into the newest kernel is shown separately by `status`. Other signed wrappers (bootloader and firmware packages) have source versions that differ from their binary versions and are not mapped.

**Third-party repositories: CHECK only.** `vuln_watch_products.json` lists KEV entries for software Debian does not track (vendor browsers, Grafana, GitLab, Jenkins, the Zabbix frontend, Plex and similar). A KEV entry matches a row when its `vendorProject` equals the row's `vendor` (case-insensitive) and its `product` starts with the row's `product`; an installed binary matches when its name fits one of the row's `packages` (case-insensitive, `*` and `?` wildcards). The result is **CHECK**: "installed X version Y, vendor fix status not verifiable automatically". CHECK applies only to KEV entries added in the last 30 days (`VULNWATCH_CHECK_DAYS`), so a new host does not start with years of old entries to read, and it is skipped for any package whose Debian source has a tracker entry for that CVE, so the tracker never gets overruled by a guess. Software that Debian ships and tracks (Apache, Nginx, OpenSSH and so on) needs no row. To cover a new product, add a row with its vendor, product prefix and package names. Rows must use the names KEV really publishes (for example Plex's product is `Media Server`, the Zabbix entry is `Frontend`, Chrome entries start with `Chrome`, and the shared engine entries are named `Firefox and Thunderbird`, which the Firefox row covers); the selftest checks the shipped rows against real-shaped names.

**Limitation: package origin.** The inventory carries no package origin. A package from a third-party repository that reuses a Debian source name (for example NodeSource `nodejs`, or PHP builds from an extra repository) is matched against the Debian tracker like a Debian package. It can be reported AFFECTED while the tracker says `open`, or compared against a Debian fixed version that does not apply to a vendor version scheme, and its CHECK entry is suppressed when the tracker lists the CVE for that source. Treat such findings as advisory and verify them against the vendor. A later improvement is to add the package origin (`apt-cache policy`) to `vw.dpkg` and treat non-Debian origins as CHECK only.

### Limits and false positives

- **KEV only.** It is the "exploited now" list, not every CVE. A host with no KEV match can still have serious unpatched vulnerabilities; the daily `vw.apt` security-update count in Zabbix is the broader signal.
- **Backports are handled by the tracker.** Debian patches in place without bumping the upstream version, so a version number alone would mislead. The tracker's `fixed_version` is the Debian version that carries the fix, which is why matching is source package against tracker, not upstream version against NVD.
- **Only what dpkg knows.** Software installed from a tarball, a container image, a language package manager or a snap is invisible. Plugins (WordPress, Jenkins) are invisible too.
- **The tracker lags.** A fresh KEV entry can appear before the tracker has a row for it; it then shows up on a later night.
- **A package with no tracker entry for a release** is not judged. An `AFFECTED` finding means the tracker says no fix exists yet for that release, not that the host is exploitable: it depends on how the software is used.
- **Cross-check.** An independent scanner run weekly (for example a vuls scan) is a good second opinion; differences point at either a tracker lag or a package source this tool does not see.

## Operation

Run on the ops host as the same user as the timer. All three commands read `ops.env`.

```
vuln_watch.py status                           per host: OS and codename, package count, inventory age,
                                               partial / blind / unsupported / not inventoried, reboot pending,
                                               pending and security updates, open findings; then every open finding
vuln_watch.py feeds                            cache age, size, ETag and Last-Modified of each feed, and the reduced tracker
vuln_watch.py run --dry-run [--host NAME]      the whole run, prints the message, writes no state and sends nothing
vuln_watch.py run [--host NAME]                what the timer does
```

`--dry-run` still refreshes the feed cache in the state directory. `--host` limits a run to one host (name as in Zabbix); findings of the other hosts are left untouched. State and the feed cache live in `~/.local/state/vuln_watch/` (mode 0700; override with `VULNWATCH_STATE`). `state.json` keeps one entry per `host|CVE|package` with first and last seen, installed and fixed versions, the KEV due date and whether the due notice was sent. No token is ever written to state, output or messages.

**What triggers a message.** One message per run, and nothing if none of these happened:

- a finding that was not there before (new);
- an `AFFECTED` finding that now has a fix (prefix 🩹);
- a finding that disappeared because it was fixed (prefix ✅);
- an open `VULN_FIX` or `AFFECTED` finding whose KEV due date is within 7 days, once (prefix ⏰); it is not sent for a finding announced as new in the same run, since that line carries the due date already;
- a host that newly became blind (a closing line `sin inventario reciente: ...`).

The message is in Spanish, the ops bot's language: a header `vuln_watch: N nuevas, M corregidas`, then up to 20 lines `<host>: CVE-... <package> <installed> → <fixed version or "sin parche" or "verificar"> (KEV, vence YYYY-MM-DD)`, then `… y K más: vuln_watch.py status` if there were more. Lines that could not be recovered later (due dates and fixed findings) come first, then fix-available lines, then new findings with VULN_FIX before AFFECTED before CHECK, so the cut at 20 lines (and a total cap just under the ops bot's 4000-character limit) falls on findings that `status` still lists. Host, package and version texts come from the monitored hosts, so control and format characters are replaced by spaces and each field is capped at 64 characters. Version changes, reboots pending and pending-update counts never produce a message; they are in `status` only. A finding of a host that is blind, unsupported or outside the current `--host` filter is carried over untouched, so losing the inventory never looks like a fix. A CHECK entry that disappears (package removed, or the KEV entry aged past the window) is dropped silently, and so are the findings of a host that left Zabbix.

**Exit codes.** 0 for a normal run, including runs with findings; 1 for a failure (API error, feeds unreachable with no recent cache), which fires the unit's `OnFailure` alert; 2 for a refused token.

## Later phases

Not built, in rough order:

1. **Ubuntu** hosts, matched through the OSV `querybatch` API.
2. **NVD / CPE matching** for software outside the distribution, replacing the manual products table.
3. **An agentless collector** over read-only SSH (the hostcare pattern) for hosts without a Zabbix agent.
4. **Trapper write-back**: push the findings into Zabbix as items so problems and history live there too.
5. **Windows**: OS version plus installed hotfix count.
