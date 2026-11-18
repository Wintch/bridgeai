---
title: SIEM agents, alert routing and file-integrity monitoring (Wazuh)
scope: a Wazuh manager with agents on your own servers and on servers you run for others; web servers with PHP CMS sites; the alert path from the SIEM to the people (and AI assistants) who must react
when_to_use: installing an agent on a server you do not own; forwarding SIEM alerts to the monitor; a file-integrity alert fires too often or not at all; writing or changing manager rules; changing a group configuration; the FIM database is full; a certbot directory fills it; reporting results to a non-technical owner
related: [README.md, detection-and-audit.md, policies.md, patching.md, firewall-and-ports.md, hardening-ssh-fail2ban-waf.md, web-exposure.md]
---
# SIEM agents, alert routing and file-integrity monitoring (Wazuh)

[detection-and-audit.md](detection-and-audit.md) (SEC-DET-10) decides whether to run a SIEM and how to trial it. This document is what to do once it runs: how to put agents on servers safely, how alerts reach people without carrying attacker text, how to design the file-integrity (FIM) rules so they page on webshells and not on plugins, and the silent failure modes of FIM. Commands are for Wazuh 4.14; version-specific commands are marked **adapt**. Two facts shape everything below:

- **Integrity monitoring fails silently.** A full FIM database drops new files without an event, a group-configuration publish re-baselines every agent without an event, and some limits are logged only in the agent's local log. Every silent mode needs its own detector (SEC-SIEM-8, SEC-SIEM-10).
- **What you watch is information.** Whatever reaches the agent, root on that machine can read. Keep criteria, exceptions and thresholds on the manager (SEC-SIEM-12).

## Quick decision table

| Situation | Do | Rule |
|---|---|---|
| Installing an agent on a server someone else owns | Written permission, data list, removal path first | SEC-SIEM-1 |
| The site slowed down after the agent started | Default first-start scan, schedule in host time, rate cap | SEC-SIEM-2 |
| SIEM alerts must reach a person or an assistant | Fixed fields, one route, send text before level | SEC-SIEM-3 |
| Webshell detection for a CMS | Real-time on upload folders, written coverage limits | SEC-SIEM-4 |
| A legitimate plugin fires a high alert | Child rule: exact signature, undo one step only | SEC-SIEM-5 |
| About to lower an alert for a folder that holds `.php` | First prove the web server does not execute PHP there | SEC-SIEM-6 |
| Alert on abnormally deep paths | Measure, escalate as a child of "new PHP", narrow exceptions | SEC-SIEM-7 |
| New files produce no alert on a busy agent | Check FIM database occupancy | SEC-SIEM-8 |
| The FIM database is full of generated files | Delete by exact name, do not exclude; second pass floods | SEC-SIEM-9 |
| About to publish a group configuration | It re-baselines everyone silently; do it rarely and check | SEC-SIEM-10 |
| Changing manager rules | Back up, `analysisd -t`, restart, confirm no agent restarts | SEC-SIEM-11 |
| Writing agent configuration or comments | The agent can read it all; criteria stay on the manager | SEC-SIEM-12 |
| Agent stopped, disconnected, limit reached | These are states; make them stay open | SEC-SIEM-13 |
| Telling the owner what the monitoring found | After about a week, in their terms | SEC-SIEM-14 |

## Rules

### SEC-SIEM-1: An agent on a server you do not own: permission, data list, quiet install, written removal
- **Rule:** install a security agent on a server that belongs to someone else only with the owner's written permission and a written list of the data that leaves the server. Write the removal path before the install, and make the install re-runnable and quiet.
- **Why:** the agent reports file hashes, security events, web logs and an inventory to a machine the owner does not control; web logs contain visitor addresses and URLs (personal data). Without a removal path, "install it, we will see" becomes permanent.
- **How:**
  - **Data list:** security events, file hashes of watched paths, web access and error logs, the package inventory. The inventory module also collects running processes, open ports, network interfaces and hardware unless you turn those off in the group configuration: turn off what you do not need and disclose the rest.
  - **Package:** pin the repository signing key by fingerprint, install an exact version, remove the repository afterwards and hold the package (`apt-mark hold`). An agent must never be newer than its manager: upgrade the manager first, then re-run the installer with the new pinned version. A held package has dpkg status `hold ok installed`; test installation with `dpkg-query -W -f='${db:Status-Abbrev}' wazuh-agent` equal to `ii` or `hi`, not with a text match on `installed`.
  - **Enrollment without the enrollment port:** register the agent on the manager (`manage_agents`), keep the key in a root-only file (SEC-POL-5), render the installer from that file so the key never appears in a command line (SEC-POL-16), and never open the enrollment port to the internet. Delete the rendered installer with `shred` after use; it contains the key. If the only way in is a cloud run-command service, the installer and key stay in the owner's command history: rotate by removing the agent on the manager (`manage_agents -r <id>`) and registering again.
  - **Network:** open only the agent-to-manager port, to the owner's egress addresses, on every firewall in the path (SEC-FW-13), with a timed rollback (SEC-FW-1). Before installing, test from the host that the port answers. Look up the host's egress address with an external echo service: a local address behind NAT is private and useless in an allowlist.
  - **Removal:** the installer writes an ownership marker; the revert step refuses to touch the package or `/var/ossec` when the marker is missing unless forced, so it cannot delete a different installation. Also delete the agent on the manager.
  - **Shell gotcha in installers:** with `set -o pipefail`, `producer | grep -q <text>` can report failure because `grep` exits at the first match and the producer dies of SIGPIPE. Capture the output in a variable first.
- **Verify:** the permission and data list are in the private notes; `dpkg-query` shows the exact pinned version; a revert was run on one host and left nothing behind; the agent shows `Active` on the manager.
- **Don't:** install without permission or without a removal path; enable `report_changes` (content diffs) on directories that hold credentials; open the enrollment port; leave the rendered installer on disk.

### SEC-SIEM-2: Keep the agent's load invisible: no first-start scan, host-time schedule, measured rate
- **Rule:** before the first start, turn off the package's default scan and rootcheck in the local configuration, cap the service's CPU and memory, and measure the first scheduled scan from outside.
- **Why:** the package's default configuration scans system directories at start. On a small server with a slow disk this raised the load to more than twice the core count and pushed time to first byte from about 1.2 s to 2.5-4 s within minutes; stopping the agent for a minute restored it, which is how the cause was proven. Later, a full scan on a busy disk took over two hours. Once limits and schedule were set, agents ran at about 1 % CPU and 30-90 MB of RAM in steady state.
- **How:**
  - Local configuration, before the first start: `<scan_on_start>no</scan_on_start>` and `<rootcheck><disabled>yes</disabled></rootcheck>`. The default local directories (`/etc`, `/usr/bin`, `/boot`, ...) are still scanned daily; measure that scan (see SEC-SIEM-9 for what `/etc` can contain).
  - systemd drop-in for the agent: `Nice=10`, `CPUQuota=50%`, and a memory cap of about three times the measured resident size. Set both `MemoryMax=` (cgroup v2) and `MemoryLimit=` (cgroup v1): on older distributions `MemoryMax=` is accepted and does nothing. `IOSchedulingPriority=` is a priority, not a cap, and acts only with BFQ or CFQ; virtio disks usually use `none`, so do not rely on it for disk protection.
  - `scan_time` is in the **host's local time zone**. Check `timedatectl` on every host and write down the UTC time of each scan; hosts in different zones scan hours apart.
  - `max_files_per_second` caps bursts, not duration: when the disk is the bottleneck the scan runs at the disk's pace (an average of about 12 files per second against a cap of 50 in one measurement), so lowering the cap trims the I/O spikes but does not shorten the scan. Give a slow host its own lower value through a neutral per-agent group (SEC-SIEM-12).
  - Read the limits back: `systemctl show wazuh-agent -p CPUQuotaPerSecUSec,MemoryMax,MemoryLimit`.
- **Verify:** from outside, response time of the site and the host's load and I/O pressure (`/proc/pressure/io`) before the install, during the first start, and during the first scheduled scan. Compare with the same window on previous days; a median is not enough, count slow requests.
- **Don't:** let the first start run on a production host unmeasured; trust a memory limit you did not read back; assume the cap shortens the scan.

### SEC-SIEM-3: Forward SIEM alerts into the existing route as fixed, sanitized fields
- **Rule:** the SIEM pages nobody directly. A small aggregator reads the alert file once a minute and sends the monitor a few fixed fields per host; the monitor routes, deduplicates and mutes them like every other alert. The aggregator's and the SIEM's own health travel the same way. Complements SEC-DET-9 and SEC-DET-11.
- **Why:** one route gives one place to mute and one end-to-end test. Wazuh's `rule.description` interpolates event fields (`$(field)`), and those come from the attacker (a URL, a user name, a user agent). Forwarding descriptions puts attacker text in front of people and AI assistants.
- **How:**
  - **Reading the alert file** (`alerts.json`): keep inode and offset in a state file and cap bytes per run; the live file is rotated and compressed at midnight, so finish the old inode (or its `.gz`) before the new one. A corrupt state means reprocessing, which can repeat pages. Verify the first midnight: counts before and after the boundary add up, no gap, no duplicate.
  - **Fields per host per minute:** highest level, rule id, count, agent name, a description from a fixed allowlist (or `rule <id> (<group>)`), and at most three source addresses per agent and rule. Validate an address by rejecting anything longer than 45 characters or containing `%` (IPv6 scope text) and then full-matching an address pattern. Cap the total text at about 1000 characters. Never forward `rule.description`, `full_log` or `data.*`.
  - **Threshold:** forward level 10 and above. Drop pure noise rules (for example "many 400 responses from one source") and send configuration-assessment and vulnerability results to reports, not pages. Every own rule at level 10 or above needs its fixed text; a level below the threshold never travels.
  - **Routing:** map each agent to the monitor host that owns the server so its tags apply; unmapped agents go to the manager's own host with the agent name in the text. The notifier's user needs read permission on that host's group, or nothing is sent even though the action matches: grant read on the security group only.
  - **Race between text and level:** the monitor evaluates a trigger the moment the level arrives. Send the text values in a request before the one that carries the levels, three requests per run (text; levels plus heartbeat; health). Putting the text item first in the expression is not enough, and without the ordering an event shows the previous alert's text.
  - **Triggers:** a High trigger that is multiple-event (one event per minute at level 12 or above) so a second attack is not absorbed by an open problem; an Average trigger that stays open long enough to pass the notifier's delayed step and is suppressed if a High fired recently. Trapper items accept values only from the aggregator's address.
  - **Health items on the manager's host:** aggregator heartbeat (`nodata` 10 minutes, High); daemons and services down; agents disconnected (with names); the agent-listing command failing; unread backlog; and values the monitor rejected on any send (High: a rejected value is a lost alert, usually a host or item missing from the map).
  - Provision with a script that is idempotent on creation and records every id it creates, so a revert works after a partial run.
- **Verify:** plant a script file in a real-time test folder on the manager and confirm the person gets the High within about a minute, then remove it. Stop the aggregator and confirm the heartbeat alert. Map an agent to an unknown host and confirm the rejected-values alert. Open a High and check that its text is the current alert's, not the previous one.
- **Don't:** forward descriptions or raw logs; build a second alert channel; give an assistant anything but these fields.

### SEC-SIEM-4: Watch CMS upload folders in real time for script files
- **Rule:** a new or modified script file in a CMS upload folder is treated as a probable webshell and pages at once. New scripts elsewhere in the web tree raise a softer alert. Write down what this does not cover, and make the web server refuse to execute scripts in uploads as the defence behind the alert.
- **Why:** core never stores scripts in uploads and few plugins do, so a script there is the cheapest high-signal evidence that an upload flaw was used; an automated attacker needs minutes, not a day, so a daily scan is too slow for this one path.
- **How:**
  - Enable real-time monitoring only on the upload folders (`/var/www/*/wp-content/uploads` and one level deeper), not on whole web trees, and collect script extensions there (`php`, `php3`-`php8`, `phtml`, `phar`, `pht`; match case-insensitively in the rule, `(?i)`).
  - Local rules as children of the integrity events "modified" (550) and "added" (554), matching the `file` field with PCRE2: a script in uploads is level 13; a new script elsewhere under the web root is level 10 with uploads excluded by a lookahead so the two never compete. Do not use the parent ids 551 and 552: they do not exist in 4.14 and analysisd warns at every start.
  - **Before enabling on a site**, list what already lives there: `find <docroot>/wp-content/uploads -name '*.php'`. Plugins that store data as `.php` there would otherwise page every few minutes (dozens of false High alerts in the first night from one security plugin). Handle each with SEC-SIEM-5 and SEC-SIEM-6.
  - **Handler files** (`.htaccess`, `.user.ini`) can make an image executable. If your agent configuration collects them, give them a level-12 rule in uploads; if it does not, record that as a coverage limit. Measure the volume before collecting them: several plugins write a harmless `.htaccess` in their own folders.
  - **Coverage limits to write down:** new or modified PHP outside uploads (a plugin or theme uploaded after an admin takeover, an edited theme file) is seen only by the scheduled scan and a modification there is level 7, which does not page; names that are not in the collected extensions are not seen; the real-time watch needs one inotify watch per folder, so compare `fs.inotify.max_user_watches` with the number of folders and look for "Unable to add inotify watch" in the agent log; a new site's upload folder is watched in real time only after the next scheduled scan.
  - **Defence behind the alert:** deny PHP in uploads at the web server: `location ~* ^/wp-content/uploads/.*\.php$ { return 403; }` in nginx (adapt the prefix to your layout; regex locations are tried in order, so it must come before the generic PHP location). Prove it with SEC-SIEM-6.
- **Verify:** on a real agent, not only the manager: create `uploads/<x>.php`, a level 13 alert arrives within seconds and pages; create one in another path, the softer rule fires; remove both.
- **Don't:** rely on the scheduled scan for uploads; watch large trees in real time; promise coverage you did not test.

### SEC-SIEM-5: Exceptions are child rules on an exact signature that undo one step, never silence
- **Rule:** when a legitimate source triggers a high rule repeatedly, add a child rule that matches its exact signature and returns the event to the level the parent's base rule gave it. Never level 0, never "mute the parent", never a name-only match when size, hash or path can also be checked.
- **Why:** every exception is a place where an attacker's file is quiet. An exception for a file name lets a webshell take that name; a loose path pattern lets one nest a file into it. Wazuh's `analysisd` picks the first child that matches, not the highest level, so an over-broad exception also hides the stricter rule behind it.
- **How:**
  - Make the signature as narrow as the source allows: anchored full path (`^...$`), a fixed plugin sub-path, and a character set that matches the source's real names (for example `[a-z0-9-]+`), never `.*` and never a bare file name.
  - Return to the base level, not to a quiet one. If a depth rule escalated a "new script" alert from 10 to 11, the exception goes back to 10, so a new script there still alerts like any other (SEC-SIEM-7). A level below the paging threshold is acceptable only for exact file names of a known plugin after SEC-SIEM-6 proved the folder does not execute PHP; keep the event in the archive for the report.
  - Same pattern for non-file noise: a rule fired by your own tool's output (for example a banner line your monitoring script logs) gets a child on `program_name` plus an anchored pattern of that exact line; web 5xx answers produced on purpose by a sleeping backend to an idle browser tab get a child on the two exact poll URLs.
  - Test each exception with negative cases: the same name in another directory, another file in the same directory, an upper-case variant, a deeper nesting, a different plugin. Every one must still fire at the parent's level (patterns offline, SEC-SIEM-11).
  - Keep the exception list in the manager's rule files with a one-line reason each; apply it with SEC-SIEM-11.
- **Verify:** the positive case drops to the intended level and the negative cases do not.
- **Don't:** silence a rule because it is noisy; write an exception by file name alone; add an exception without checking what the source actually is.

### SEC-SIEM-6: Before lowering the alert for a folder that holds `.php`, prove the web server does not run PHP there
- **Rule:** an alert on `.php` files in a plugin's cache or data folder may be lowered only after a request for an existing harmless file in that folder shows the web server refuses to execute it. If it executes, fix the web server instead.
- **Why:** a plugin's cache file can look like a harmless stub, but the folder is writable by the web user, so a webshell fits in the same name and size. `.htaccess` with `Deny from all` is an Apache mechanism: nginx ignores it, so a plugin that ships one gives no protection under nginx. Under Apache it applies only if `AllowOverride` permits it.
- **How:**
  ```bash
  # use a file that exists and is harmless, for example the folder's own index.php
  ls <docroot>/wp-content/plugins/<plugin>/<cache-dir>/index.php
  curl -ks -o /dev/null -w '%{http_code}\n' --resolve <domain>:443:127.0.0.1 \
    https://<domain>/wp-content/plugins/<plugin>/<cache-dir>/index.php
  ```
  `--resolve` sends the request to the local server without going through a CDN or DNS. `200` means the server executed it (the stub prints nothing): a webshell there would run, so do not lower the alert. `403` means PHP is denied. Fix at the web server (adapt; place it before the generic PHP location so it wins):
  ```nginx
  location ~* ^/wp-content/plugins/<plugin>/<cache-dir>/.*\.php$ { return 403; }
  ```
  Reload (`nginx -t` first) and repeat the request until it returns `403`, then lower the alert for the exact cache file names only.
- **Verify:** the request returns `403` after the fix; an exact-name file still alerts at the lowered level; any other `.php` in the folder still alerts at the base level.
- **Don't:** lower an alert because the file's content "looks benign"; rely on an `.htaccess` under nginx; test only through the CDN (it may answer from cache).

### SEC-SIEM-7: An "anomalous depth" rule: measure first, escalate as a child, keep exceptions narrow
- **Rule:** alert on files whose path is far deeper than any normal site layout, and measure the threshold on your own inventory before choosing it. Attach the depth rule to the "new script" rule so it escalates that alert by one level; exceptions are child rules that undo only that step (SEC-SIEM-5).
- **Why:** an attacker who knows the agent's limits plants files below them (the agent's recursion depth is large but finite, and a path past it is skipped, logged only at debug level). A normal web root is shallow; third-party `vendor/` and `node_modules` trees are deep by design, and some plugins ship deep view templates. Without an exception, those fire forever; with a careless one, the rule is gone.
- **How:**
  - Measure: count inventory paths per depth threshold (14, 15, 16, 17 directory levels) per agent, and choose the lowest level with a tolerable count. Most deep paths are `vendor/` and `node_modules`.
  - Order matters: the "new script under the web root" rule (level 10) always matches a new script first, so a depth rule hung on the same parent never evaluates. Make the depth rule a child of the "new script" rule (level 11), and a separate depth rule for modified scripts and non-script files, excluding by lookahead what higher-level rules already own.
    ```xml
    <!-- file name: local_rules_fim.xml (loaded after local_rules.xml: alphabetical order) -->
    <rule id="100501" level="10">   <!-- new script anywhere under the web root -->
      <if_sid>554</if_sid>
      <field name="file" type="pcre2">(?i)^/var/www/.*\.(?:php\d?|phtml|phar|pht)$</field>
      <description>New script under the web root</description>
    </rule>
    <rule id="100502" level="11">   <!-- escalation: 17 or more path components below /var/www -->
      <if_sid>100501</if_sid>
      <field name="file" type="pcre2">^/var/www(?:/[^/]+){17,}$</field>
      <description>New script with an abnormally deep path</description>
    </rule>
    <rule id="100503" level="10">   <!-- exception: back to the base level, not quiet -->
      <if_sid>100502</if_sid>
      <field name="file" type="pcre2">/wp-content/plugins/example-plugin/src/views/(?:[a-z0-9-]+/)+[a-z0-9-]+\.php$</field>
      <description>New script in a plugin's deep view folder</description>
    </rule>
    ```
    Replace `example-plugin` with the real slug. If your layout adds a fixed prefix (a control panel's per-client folders), skip it with a possessive quantifier (`(?:/prefix/[^/]+)?+`) so the engine does not backtrack and count it twice.
  - When a depth rule is added, expect one burst from your own clean-ups (deleting a deep tree raises one deleted-file event per file); plan a single summarized alert (SEC-SIEM-9).
- **Verify:** a test path at the threshold fires level 11, one level shallower fires level 10, the exception path fires level 10 and a same-looking path with an upper-case or different plugin slug fires 11 (patterns offline, SEC-SIEM-11).
- **Don't:** put the depth rule next to the "new script" rule as a sibling (it never runs); widen an exception to `.*`; pick a threshold without counting.
- **See also:** SEC-DET-18 (silent FIM limits, depth and avalanche rules in the audit doc)

### SEC-SIEM-8: A full FIM database means new files produce no event: monitor the occupancy
- **Rule:** each agent's FIM database has a hard entry limit (`file_limit`, 100000 by default). When it is full, a new file creates no event at all, not even in real time and not for the webshell rule. Watch occupancy per agent, keep the limit-reached state open until it is fixed, and set the limit explicitly to about twice the real usage.
- **Why:** there is no "evict the oldest": the new entry is rejected and only a line in the agent's local log remains. A server can be blind to new files for days. The limit-reached alert (rule 233, level 12) fires once per transition and after each agent restart; the steps before it are 231 (80 %, level 7) and 232 (90 %, level 9). Treated as an event, it closes in the monitor within a minute while the problem stays.
- **How:**
  - Compute occupancy on the manager from its per-agent database and send it to the monitor as items (SEC-SIEM-3): entries, percentage of the limit, hours since the last finished scan, and whether a scan is running. Triggers: 80 % Warning, 95 % High, both open while the condition holds; a scan not finished for more than about 26 hours.
  - Count rows with the manager's database socket (**adapt**: socket path, message format and table names are version specific). The message is a 4-byte little-endian length followed by `agent <NNN> sql select count(*) as c from fim_entry`, answered by `ok <json>`. Group by directory to see what fills it: for a typical host, one or two directories hold most rows.
  - After fixing the cause, check that the rejected files are now covered: count rows under the web root for that agent and compare with the number of scripts on disk.
  - Set `<file_limit><enabled>yes</enabled><entries>N</entries></file_limit>` (inside `<syscheck>`) explicitly through the group configuration (SEC-SIEM-10) with N about twice the measured usage, so growth raises the 80 % warning instead of silently crossing the line.
  - Do not redefine or mask rules 231-233. Check that no local rule uses `if_sid` on 230-233.
- **Verify:** the occupancy items exist for every active agent and the 80 % and 95 % triggers open on a test value; the limit-reached state stays open in the monitor.
- **Don't:** conclude "no new files" from the absence of alerts on an agent whose database may be full; handle the problem by excluding the directory that filled it (SEC-SIEM-9).
- **See also:** SEC-DET-15 (the same rule in the detection doc, as part of the audit checklist)

### SEC-SIEM-9: Clear the clutter that fills the FIM database by deleting it, by exact name
- **Rule:** when generated files (certificate request and key files, caches, backups) fill the FIM database, delete the stale files rather than excluding their directory, delete by exact name pattern only, and stop the source from regenerating them. A bulk deletion and the next scan produce known floods: plan for them.
- **Why:** an exclusion is a permanent blind spot that anyone reading the configuration learns (SEC-SIEM-12). A typical filler is certbot: versions older than 2.3.0 write a private key and a request file into `keys/` and `csr/` on every attempt, even a failing one, so a failing renewal retried twice a day adds thousands of files a year. certbot 2.3 stopped writing them, but upgrading does not remove existing ones.
- **How:**
  1. Find the cause before deleting: `ls /etc/letsencrypt/keys | wc -l`; `certbot certificates`; `grep -E 'error|fail' /var/log/letsencrypt/letsencrypt.log | tail`. Lineages that are served elsewhere (the public certificate comes from an edge proxy) and fail HTTP validation here get `autorenew = False` in their renewal file (back it up); remove lineages nothing references.
  2. Back up first: a root-only compressed archive of what you will delete, plus the list. Schedule its own deletion (the archive holds private keys; `shred` it after a week).
  3. Delete only names matching the generator's pattern (`NNNN_key-certbot.pem`, `NNNN_csr-certbot.pem`), never by age (root can change dates). Never touch `live/`, `archive/`, `renewal/`, `accounts/`. Validate with `certbot certificates` and the web server's config test; nothing needs a restart.
  4. For keys use `shred --remove=unlink`; plain `shred -u` renames and syncs per file and crawls on a slow disk. Run long jobs detached (`nohup setsid <script> > <log> 2>&1 &`) and poll the log: a remote exec call's timeout returns while the process keeps running.
  5. Expect a flood: tens of thousands of deleted-file events (about 20 per second at the agent's event cap, so tens of thousands take close to an hour), and, at the next scheduled scan, the previously rejected files appear as new-file events (second pass). The avalanche rule (below) summarizes them. Do not restart the agent or publish a group configuration between the deletion and that scan: a restart would take the rejected files into the new baseline without events (SEC-SIEM-10).
  6. After the next scan, confirm occupancy dropped and that the second pass reported what it should.
  - **Trap for what remains:** in a directory that should only hold the generator's files, any other name is suspicious. A rule on `^/etc/letsencrypt/(?:keys/(?![0-9]{4,}_key-certbot\.pem$)|csr/(?![0-9]{4,}_csr-certbot\.pem$)).+$` at level 10 catches a file that does not follow the pattern.
  - **Avalanche rules:** `frequency="300" timeframe="600" ignore="600"` over the added-file event and `frequency="1000" timeframe="600" ignore="3600"` over the deleted-file event, level 10: one summary per burst. `frequency` counts per agent; `ignore` is per rule (not per agent), so two agents bursting inside the ignore window alert once.
- **Verify:** cleaned directory counts, config test passes, the monitor shows one avalanche alert and not tens of thousands, and the scheduled scan after the cleanup completes.
- **Don't:** add `<ignore>` to the directory; delete by modification time; restart the agent in between.
- **See also:** SEC-PATCH-21 (the certbot cleanup script), SEC-PATCH-22 (why renewals keep running), SEC-DET-17 and SEC-DET-18 (delete stale data; trap and avalanche rules)

### SEC-SIEM-10: A group-configuration publish re-baselines every agent in the group, silently
- **Rule:** publishing a group's shared configuration restarts the FIM of every agent in that group; the agent's database is volatile, so it rebuilds a baseline without events, and anything planted at that moment is absorbed. Publish rarely, all changes in one night, and run a comparison afterwards.
- **Why:** verified in the 4.14 source: the restart is triggered by the new configuration and `scan_on_start=no` does not prevent the rebuild. Each publish is also a full scan of every client agent at the time of publishing (measure it, SEC-SIEM-2). Do not count on "agent stopped/started" alerts to tell you which agents restarted: a configuration-driven restart can emit neither. The agent's configuration hash and its FIM start time are the reliable trace (see Verify).
- **How:**
  - Batch changes: prepare and validate the files (`/var/ossec/bin/verify-agent-conf -f <file>`, **adapt**), keep a backup of the previous group files, publish once at the quietest hour.
  - Before and after, take the manager's inventory of script and handler files under the web roots (and cron, sudoers, `authorized_keys` directories) from its per-agent database. A new or changed path that appears after the restart without a matching "added" or "modified" alert was absorbed. A small hourly job that keeps a snapshot, compares successive snapshots with the alerts of that window, and holds suspicious paths for a couple of runs (the inventory arrives before the alert on a busy agent) detects absorption caused by restarts you did not make, for example a package upgrade of the agent. Keep unresolved findings open until acknowledged.
  - A manager restart alone does **not** re-baseline agents (SEC-SIEM-11); a group publish does, and a changed configuration hash per agent is the signal (`agent_control -i <id>`, line `Configuration hash`). An agent in several groups gets a merged file from `/var/ossec/var/multigroups/<hash>/merged.mg`, not from `shared/<group>/`.
  - Do not publish between a bulk deletion and the next scheduled scan (SEC-SIEM-9).
- **Verify:** after a publish: for each agent in scope, `sudo /var/ossec/bin/agent_control -i <id> | grep -E 'Configuration hash|Syscheck last started'` shows a new hash and a FIM start at the publish time; agents outside the scope keep their old hash and start time; every agent returns to `Active`; the absorption comparison reports nothing; the scan completes.
  - To limit the blast radius, give a single agent its own neutral group (for example `a<agent-id>`) assigned after the common group: publishing that group restarts only that agent.
- **Don't:** publish "a small tweak" in the middle of the day on production agents; assume that disabling the start-up scan protects the baseline.
- **See also:** SEC-DET-16 (the same rule in the detection doc), SEC-POL-14 (the publisher script)

### SEC-SIEM-11: Change manager rules in a fixed sequence: back up, validate, restart, confirm nothing re-baselined
- **Rule:** before restarting the manager for a rule change, back up the rules file and validate with `wazuh-analysisd -t`; read its exit code and its WARNING lines. After the restart, confirm that all agents are back and that no agent's configuration hash or FIM start time changed: restarting the manager does not touch the agents' FIM.
- **Why:** a rule file with a bad reference can stop `analysisd` and with it all detection. Several mistakes only warn, at every start: a parent `if_sid` that does not exist (551 and 552 in 4.14), an unknown MITRE id (this one can prevent start), and `<same_agent/>` (rejected in 4.14). A piped `... | tail` shows the last lines and loses the exit code.
- **How:**
  ```bash
  sudo cp -p /var/ossec/etc/rules/<file>.xml /root/wazuh-backups/<file>.xml.pre-<change>
  sudo /var/ossec/bin/wazuh-analysisd -t > /tmp/analysisd-test.log 2>&1; echo "rc=$?"   # must be 0
  grep -iE 'warning|error|critical' /tmp/analysisd-test.log                              # must be empty
  for a in <agent-ids>; do sudo /var/ossec/bin/agent_control -i $a | grep -E 'Configuration hash|Syscheck last started'; done > /tmp/agents-before.txt
  sudo systemctl restart wazuh-manager
  sudo /var/ossec/bin/agent_control -l | grep -c Active                                    # all expected agents
  for a in <agent-ids>; do sudo /var/ossec/bin/agent_control -i $a | grep -E 'Configuration hash|Syscheck last started'; done | diff /tmp/agents-before.txt -   # empty = no re-baseline
  ```
  Restore the backup and restart if validation or the restart fails. A manager restart drops agent connections briefly; do it at a quiet hour and expect agents back within a minute or two.
  - **Rule behaviour to remember:** rule files load in alphabetical order, and `analysisd` takes the first child that matches, not the highest level; `frequency` counts events of the same agent; `ignore` is per rule; rules below the forwarding threshold never reach the monitor (SEC-SIEM-3).
  - **Testing:** `wazuh-logtest` decodes sshd, web and system lines and shows the rule that fires. In 4.14 it does not decode file-integrity events (they stay in the generic JSON decoder), so for FIM rules test the patterns offline: extract each `file` pattern from the XML (not a copy), run good and bad sample paths through `grep -P` (PCRE2) and through your language's regex engine, and require the same result. Then test end to end once: a real-time test folder on the manager and a planted file, check the alert and the page, remove both.
- **Verify:** rc 0, no WARNING lines, all agents Active, configuration hashes and FIM start times unchanged. Absence of 503/506 alerts is not proof: a configuration-driven agent restart can emit neither.
- **Don't:** restart on a validation you did not read; test only with the page's pattern copied by hand; leave a test folder in the manager's configuration.

### SEC-SIEM-12: What you watch and tolerate lives on the manager; the agent gets the minimum
- **Rule:** the agent receives only what it needs to collect. Exceptions, thresholds, levels and the reasoning behind them live in manager rules, which agents never receive. Group configuration files travel verbatim to every agent in the group, so they carry no comments, no names of other customers or hosts, and no explanations.
- **Why:** anyone with root on a monitored machine (an attacker, or its owner's administrator) can read the shared configuration and learn exactly where you do not look, then plant files there. An exclusion also tells them other machines may have the same one. Nothing can hide from root **what** the agent collects; what you can hide is the criteria. The manager's inventory is fed by the agent, so against an attacker who has root it is not an independent source: it helps against lower-privileged attackers and for noticing absorption.
- **How:**
  - Keep commented sources in your private repository and publish a stripped copy with a script that removes comments and rejects configuration containing customer or host names.
  - `<agent_config name="...">` blocks in a shared file are visible to every agent in the group. For per-agent values (a lower `max_files_per_second` for a slow disk) use a per-agent group with a neutral name and performance values only. Wazuh shows the agent a `Source file: <group>/agent.conf` line, so group names are visible too: do not name groups after customers or what they contain.
  - Prefer collecting broadly on the agent and classifying with manager rules. In the agent, `<ignore type="sregex">` is an unanchored, case-insensitive substring applied to real-time events too: `<ignore>node_modules</ignore>` makes `uploads/node_modules/shell.php` invisible. If you must keep an agent-side ignore for performance, treat it as a known hole and cover it with a rule on the path elsewhere. Delete stale data rather than excluding directories (SEC-SIEM-9).
  - Do not rely on documentation for what the collector does with case and anchoring: check the source or test with real files. In one case the documentation and the code disagreed and the code was right.
  - Limits that fail silently must alert loudly and stay open (SEC-SIEM-8, SEC-SIEM-13).
- **Verify:** read the shared file as root on a monitored host: it has no comments, no names and no reasoning; every exception exists as a manager rule.
- **Don't:** put reasons in the agent configuration "for the next admin"; publish `<agent_config name=>` blocks; add a new agent-side exclusion as the default response to noise.
- **See also:** SEC-POL-13 (what must not be readable from the monitored machine), SEC-POL-14 (publisher script), SEC-DET-17 (delete stale data, classify on the server)

### SEC-SIEM-13: Limits and agent loss are states; make them stay open and give them the right level
- **Rule:** "agent stopped", "agent disconnected" and "database full" describe a state that persists. Raise each as a state in the monitor, with a level chosen for how often it happens legitimately, and test that a new agent is covered.
- **Why:** an aggregator that sends the highest level seen in the last minute closes the problem the minute after a one-shot alert, although the agent is still blind. And stopping the agent is the first thing an intruder does to a monitored host; if it barely shows, stopping it is free.
- **How:**
  - **Stopped (rule 506):** fires on agent restarts and package upgrades, and often on a group publish (five agents in eight minutes in one measurement), although a configuration-driven restart can also happen without it (SEC-SIEM-10), so give it a middle level (8) that does not page; it stays in the archive as the trace of when the agent stopped.
  - **Disconnected (rule 504):** generated by the manager's monitoring daemon after the disconnection time, with the agent name only in `full_log` and the agent field showing the manager. Extract the name with a strict anchored regex that accepts only valid agent names, never forward the line. Level 10, so it pages. The real delay is the manager's disconnection time plus the trigger window, longer than either alone (measure it); agents that never connected do not alert, on purpose, so list them separately.
  - If the rules filter agents by a name prefix (to exclude your own laptops), a new agent with another prefix gets no alert: stop a test agent after registering it and watch the alert arrive.
  - A database-full state (SEC-SIEM-8) and a real-time queue overflow are fed from periodic items, not from the one-shot alert.
- **Verify:** stop an agent: a note at level 8 and, after the window, a page; start it: the problem closes. Register a test agent with a new name and repeat.
- **Don't:** set "agent stopped" to page (publishes become a storm) and then forget to cover "disconnected"; assume the filter covers agents added later.
- **See also:** SEC-DET-19 (the same rule in the detection doc)

### SEC-SIEM-14: Report what the monitoring found, in the owner's terms
- **Rule:** the permission and data list come before the install (SEC-SIEM-1). The results report comes after about a week of data and uses what an outsider measures, in plain language.
- **Why:** owners are rarely technical and will never open your monitor. "We installed a SIEM" invites "what did it cost me, and what did it tell you?", and the answer must be numbers.
- **How:** five blocks, with no rule ids, levels or tool names:
  - **Availability and speed:** failed checks and median response time from an outside probe (SEC-DET-12), the week before against the week after.
  - **Attacks:** attempts per day, distinct sources, what they wanted in plain words ("guessing passwords", "looking for forgotten configuration files") and that none succeeded, or what happened if one did.
  - **Site integrity:** changes detected and which were legitimate updates.
  - **Pending flaws:** critical and high per server, those actively exploited (KEV), and whether each needs an update or a migration.
  - **Cost:** the agent's CPU and memory next to the response times.
  - Say which servers are left out and why.
- **Verify:** someone non-technical reads it and can say what they have to decide.
- **Don't:** send screenshots of the monitor; present the tool instead of the findings; promise protection against everything.

## Checklist

1) Permission, data list and tested removal for every agent on a server you do not own (SEC-SIEM-1).
2) First-start scan and rootcheck off, limits read back, first scan measured from outside (SEC-SIEM-2).
3) Alerts reach the monitor as fixed fields, text before level, health and rejected values alert (SEC-SIEM-3).
4) Upload folders watched in real time, coverage limits written down, PHP denied at the web server (SEC-SIEM-4, SEC-SIEM-6).
5) Every exception: exact signature, base level, negative cases tested (SEC-SIEM-5, SEC-SIEM-7).
6) FIM occupancy items and triggers for every agent; explicit `file_limit` (SEC-SIEM-8).
7) Clutter deleted by exact name, not excluded; floods planned (SEC-SIEM-9).
8) Group publishes are rare, batched, followed by an absorption comparison (SEC-SIEM-10).
9) Rule changes: backup, `analysisd -t` rc 0, restart, no agent restarts (SEC-SIEM-11).
10) Shared agent configuration is stripped, neutral, minimal (SEC-SIEM-12).
11) Stopped, disconnected and full are tested states, including for new agents (SEC-SIEM-13).
12) First owner report after a week, in their terms (SEC-SIEM-14).
