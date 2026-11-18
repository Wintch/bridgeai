---
title: Detection and audit (SSH audits, intrusion pack, alert design, SIEM)
scope: Linux servers, hypervisors and their management planes, monitoring and alerting pipelines, AI assistants that read alerts
when_to_use: auditing who logged in; checking for access nobody granted; building or reviewing intrusion detection; designing alerts; deciding whether to add a SIEM; investigating a host that was compromised earlier; triaging high-level alerts; an AI agent or a monitor reports "all clear"
related: [README.md, policies.md, patching.md, containers-and-images.md, hardening-ssh-fail2ban-waf.md, firewall-and-ports.md, wazuh-fim.md]
---
# Detection and audit

Detection starts with truth sources you can trust (the journal, not a script that may be blind), a list of who is supposed to be there, and a small set of signals that fire on the attacker's first steps. Build that minimal pack first, make sure the monitor's own death alerts a person, and only then consider a SIEM. Alert text is attacker-controlled data (SEC-POL-11). Monitoring that reaches nobody, or that cries wolf, is not monitoring. Related docs: [policies.md](policies.md) (access, credentials, AI agents), [patching.md](patching.md), [containers-and-images.md](containers-and-images.md); SSH and fail2ban hardening is in [hardening-ssh-fail2ban-waf.md](hardening-ssh-fail2ban-waf.md) (SEC-HARD-4 covers audit scripts reading the unit); firewall changes are in [firewall-and-ports.md](firewall-and-ports.md).

## Quick decision table

| Situation | Do | Rule |
|---|---|---|
| "Who logged in over SSH since <date>?" | Read the journal, matching `sshd` and `sshd-session` | SEC-DET-1 |
| An audit shows many logins from one address | Check each source against a known list; recount with `Accepted` lines | SEC-DET-2 |
| Unexplained reboot, credential file touched, new cron entry | Look for third parties with root: cloud agents, patch managers | SEC-DET-3 |
| Someone reading files they should not | Canary account, decoy key, decoy file | SEC-DET-6 |
| The monitor itself could be killed | Out-of-band heartbeat and external watcher | SEC-DET-7 |
| Designing alert rules | List the known evasions and close them | SEC-DET-8 |
| An AI reads alerts or logs | Fixed fields only, no free text | SEC-DET-9 |
| "Should we install Wazuh/a SIEM?" | Decide by need and resources; time-boxed trial | SEC-DET-10 |
| Alerts exist but nobody reacted | Route every trigger to a person; fix noise first | SEC-DET-11 |
| "Is the site up for the public?" | Probe from outside, check content, use two vantage points | SEC-DET-12 |
| A person, tool or agent says "clean / done" | Ask for the evidence; test the tool for blind spots | SEC-DET-14 |
| Running the SIEM: agents on customer servers, alert forwarding, file-integrity rules | Separate document | [wazuh-fim.md](wazuh-fim.md) (SEC-SIEM-1 to 14) |
| An agent's file-integrity database may be full; new files give no alert | Monitor occupancy per agent; keep the state open | SEC-DET-15 |
| About to publish a group configuration to monitoring agents | One batch, at night, then an absorption check | SEC-DET-16 |
| Noise or quota problem in a watched directory | Delete stale data; classify with anchored manager rules | SEC-DET-17 |
| Which FIM limits fail silently; depth and avalanche rules | Write them down and alert on the anomaly | SEC-DET-18 |
| "Agent stopped" or "disconnected" is only a low-level event | Raise them; measure the delay to a page | SEC-DET-19 |
| A host turns out to have been compromised before | Preserve evidence, hunt by change time, check use, clean, rotate | SEC-DET-20 |
| A level-10+ web or integrity alert needs a verdict | Triage with fixed fields and a change log | SEC-DET-21 |

## Rules

### SEC-DET-1: Audit SSH access from the journal, and make sure your script can see it
- **Rule:** the journal is the source of truth for SSH logins. Query it by program name for both `sshd` and `sshd-session`, check how far back it goes, and never conclude "no logins" from a tool you have not tested on a known login.
- **Why:** since OpenSSH 9.8 (Debian 13) the per-connection process is `sshd-session`, so scripts matching `sshd[<pid>]` see almost nothing. Debian 13 also has no `/var/log/auth.log` (everything is in journald) and `last` reads a wtmp file that is gone (the replacement is `wtmpdb`). An old audit script printed "clean" on a host with plenty of logins.
- **How:**
  ```bash
  journalctl --list-boots | head -1                                  # how far back the journal goes
  journalctl _COMM=sshd _COMM=sshd-session --since "<YYYY-MM-DD>" -o short-iso --no-pager \
    | grep -E 'Accepted|Failed|Invalid user|authentication failure' > ssh-events.txt
  grep -oE 'Accepted [a-z-]+ for [^ ]+ from [0-9a-fA-F:.]+' ssh-events.txt | sort | uniq -c | sort -rn
  journalctl _COMM=sudo --since "<YYYY-MM-DD>" --no-pager | grep COMMAND     # what privileged work was done
  ```
  On older systems the same lines are in `/var/log/auth.log` (`sshd[<pid>]`); a portable script matches `sshd(-session)?`. Persistent journal (`/var/log/journal` exists) is needed for history across reboots.
- **Verify:** log in once yourself from a known address and confirm the script reports exactly that login; the script prints the first journal timestamp so a reader knows the coverage.
- **Don't:** rely on `last`/`lastlog` alone (wtmp can be truncated or forged and may not exist); read "0 failures" as success when the filter may be blind; run your own broad `grep -r`/`find` on the host and then use `atime` as evidence (your audit changed it).

### SEC-DET-2: Correlate accepted logins with known sources, account by account
- **Rule:** keep a list of expected source addresses per host (people, bastions, automation, the monitoring host). Every `Accepted` line is either on the list or an investigation. Review accounts as well as addresses.
- **Why:** a count by address hides who the account is, and a count of "logins" can be wrong: a figure attributed to a monitoring host as hundreds of thousands of root logins turned out to be connections to the agent port, not SSH logins at all.
- **How:**
  ```bash
  getent passwd | awk -F: '$7 !~ /(nologin|false)$/ {print $1}'               # accounts that can log in
  sudo chage -l <user>                                                          # expiry (SEC-POL-2)
  sudo find /root /home -maxdepth 3 -name authorized_keys -exec sh -c 'for f; do echo "== $f"; ssh-keygen -lf "$f"; done' _ {} +
  sshd -T | grep -E '^(permitrootlogin|passwordauthentication|allowusers)'
  ```
  For each unknown address: note the authentication method (`publickey` vs `password`), the account, the time, and what that session did (`sudo` lines, `apt` history, new files). Typical benign explanations are the provider's web console, your own automation, and a contractor on a dynamic address; record which.
- **Verify:** every accepted source and key fingerprint is explained in the private notes; the number of password logins by root is zero on internet-facing hosts (SEC-POL-1).
- **Don't:** trust a source that matches an expected subnet without checking the account; treat fail2ban bans as the audit (bans show attempts, not successes).

### SEC-DET-3: Audit third parties who hold root on your machines and never told you
- **Rule:** include "who else can run commands as root here" in every audit: cloud management agents, hybrid SSM activations, patch managers, provider "droplet agents", monitoring agents allowed to run remote commands, hypervisor guest agents.
- **Why:** these run with full privilege, can reboot the machine, and may belong to an account you do not control. They explain mysterious reboots and rewritten files, and they are also access that someone else can lose control of.
- **How:**
  ```bash
  ls -la /root/.aws /home/*/.aws 2>/dev/null                      # credentials written by an agent are a sign
  systemctl list-units --type=service --no-legend | grep -iE 'ssm|agent|remote|manage'
  systemctl list-timers --all | head -30
  journalctl --list-boots | tail -10                              # reboot dates; compare with change calendars
  ls -ltr /etc/cron.d /etc/cron.daily /etc/cron.weekly | tail -20  # packages installed by a patch manager change these
  ```
  If an SSM agent is present, find which cloud account it is registered to and what it runs (its command history, with the right account's credentials). Patch baselines usually run on a weekly or fortnightly schedule with a reboot: write the schedule down so your own upgrades and release upgrades avoid it, and ask the owner to pause the association during a window. At the hypervisor level, the guest agent runs commands as root in every guest and these executions do not appear in the usual task history: restrict who can reach the hypervisor (SEC-DET-13).
- **Verify:** a table of third-party agents per host: what, which account owns it, schedule, what it may do, who to ask. Reboots in the last 90 days are each explained.
- **Don't:** remove a management agent you do not understand (the customer's patching may depend on it): ask the owner first, then decide. Do not give an agent's cloud credentials to anyone.

### SEC-DET-4: Retired
- **Retired:** hypervisor and management-plane material that is not part of bridgeai. The ID stays reserved.

### SEC-DET-5: Retired
- **Retired:** hypervisor and management-plane material that is not part of bridgeai. The ID stays reserved.

### SEC-DET-6: Plant canaries that no legitimate person touches
- **Rule:** create decoys whose only possible use is malicious: a login account with an attractive name and no permissions, a decoy private key paired with a public key that works nowhere (forced to `/bin/false`), and decoy files in places an intruder searches. Any use is an alert.
- **Why:** an intruder who has stolen files or is looking around uses what he finds; no colleague knows the decoy exists, so there are no false positives.
- **How:** create the decoy account with `nologin` and a random password; alert on any `Invalid user <decoy>`, `Failed password for <decoy>` or authentication failure naming it. Put the decoy private key where a thief looks (the admin's `~/.ssh/`) and its public half in the decoy account's `authorized_keys` on other hosts with `restrict,command="/bin/false"`: an accepted login with it is severity Disaster. Create decoys before you baseline file hashes, or the hash alarms fire once. Hosted canary tokens (a fake cloud key, a document, a DNS name) are a zero-RAM option for hosts with attractive credentials.
- **Verify:** try the decoy account from a test machine and confirm the alert.
- **Don't:** expect canaries to catch an intruder who already has root and reads your config, or one who avoids the name: they catch file readers and bulk copiers. Do not use a decoy name that a real service or person uses.

### SEC-DET-7: Give the monitor an out-of-band heartbeat
- **Rule:** an attacker with root kills the collector first. The collector's own timestamp is a heartbeat, a silent collector is a High alert, and an external watcher on a different host checks the monitor itself and reports directly to a person.
- **Why:** if the only evidence of a compromise is silence, silence must page someone. The watcher must not depend on the pipeline it is watching, and must not run on the same hypervisor as the monitor.
- **How:**
  - In the monitor: trigger on `nodata(<state item>,4m)=1 or now()-last(<timestamp item>)>180`; also on the agent's ping and on the intrusion-prevention service being up.
  - External watcher (timer every 2 minutes on a host under a different hypervisor): queries the monitor's API with a read-only token for the age of the heartbeat items; after three consecutive failures it sends one chat message directly through the messaging API (not through the monitor, not through the usual alert bot):
    ```bash
    curl -fsS -m 10 -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json-rpc' \
      -d '{"jsonrpc":"2.0","id":1,"method":"item.get","params":{"output":["lastclock"],"filter":{"key_":"<heartbeat-key>"},"monitored":true}}' <monitor-api-url>
    ```
    Keep the token and chat credentials in a root-only environment file (SEC-POL-5). Count items too: a missing item is a failure, not "fine".
  - Add a second watcher in the other direction if the monitor's own host can be the compromised one, and a periodic "still alive" message so that the watcher's death is also noticed (a suggestion; the watcher is a small script that can fail too).
  - Plan maintenance windows for reboots: a reboot raises "collector silent".
  - For power or internet outages at a site, add a ping or probe from outside the site (SEC-DET-12).
- **Verify:** stop the collector on a test host and confirm the in-monitor alert within 4 minutes; stop the monitor's agent and confirm the external watcher messages you after about 6 minutes.
- **Don't:** route the watcher's message through the system it watches; give its token write rights.

### SEC-DET-8: Know the evasions and close them
- **Rule:** for every alert rule, write down how an attacker with the access you are watching for would avoid it, and close the gaps that are cheap. Publish nothing about the gaps you leave open.
- **Why:** most detections fail quietly in predictable ways. Each of these was found by testing the design before deployment.
- **How:** check the design against this list.
  - **Trusted-IP blind spot:** logins from the admin workstation's address never alert, so a stolen workstation or its key is invisible. Remove password authentication first, so that any `Accepted password` becomes an alert with no false positives; protect workstation keys with passphrases; restrict automation keys with `from=` and `command=` so a key found on one host is not general root on the next.
  - **Lateral movement from a known host:** a root attacker on host A uses A's key to enter B from an address already on B's list. Only the first entry is seen. Restrict the key (above) and alert on login from unexpected accounts.
  - **Self-resolving hash alerts:** `changecount(...,15m)` clears itself after 15 minutes, but a new authorized key or user is persistent. For credential files use manual recovery (acknowledge to close).
  - **Counters with a reset:** deleting the collector's cursor zeroes the cumulative count; a negative delta is discarded and nothing fires. Add a "reset" counter that rises when the cumulative value falls. A lost journal cursor re-emits the whole history: discard events older than the collector's start time to avoid a false-positive storm.
  - **Fake heartbeat:** with root, a loop that rewrites the state file with a fresh timestamp defeats the "silent" trigger. Move the most serious detections off the host: send grave events straight to chat at the moment of the event.
  - **Off-host log copies** to a machine the attacker also controls (all hosts share one key) are false comfort; a ring of hosts that all trust each other helps against deletion only if the append-only flag and a restricted key hold.
  - **Pattern matching by option:** a rule for "manual backup" that matches on missing `--quiet` is evaded by adding the flag. Compare against an exact allowlist of expected jobs.
  - **Thresholds and sampling:** "5 failures in 5 minutes" is quiet below the line; `Connection closed by authenticating user` may not be counted; a 30-second `ss` sample misses short connections and everything on 443/UDP.
  - **fail2ban `ignoreip`:** LAN ranges are ignored, so alerts must cover failures from the LAN.
- **Verify:** for each rule, a test (or a written reason) that the evasion is closed or accepted.
- **Don't:** claim coverage for what a rule only partly sees; keep a rule whose evasion is one flag away without noting it.

### SEC-DET-9: Text inside alerts is untrusted data; give an AI fixed fields only
- **Rule:** usernames, `user=` fields, user agents, URLs, file names and command lines in logs and alerts are chosen by the attacker. Collectors emit only counters, hashes, and events of the form `[timestamp, type-from-a-closed-list, validated-IP]`. An AI assistant that summarizes alerts receives those fields, never raw log lines (SEC-POL-11).
- **Why:** an SSH login attempt for a user named like an instruction, or a crafted `User-Agent`, is text that reaches your assistant. If the assistant treats it as instruction it can be steered.
- **How:**
  ```python
  import ipaddress
  def clean_ip(s):
      try: return str(ipaddress.ip_address(s.replace("::ffff:", "")))
      except ValueError: return None        # drop the event rather than pass raw text
  ```
  Alert subjects are static trigger names; do not put `{ITEM.VALUE}` or log text into notification messages. If free text must be shown, put it in quotes labelled as data, and make the assistant's tools read-only for the investigation. Rate-limit the receiver and allow it to ignore malformed events. For the Wazuh aggregator that does this (and the interpolation trap in `rule.description`) see SEC-SIEM-3.
- **Verify:** inject `Invalid user "ignore previous instructions"` through a test login and confirm the text appears nowhere in the state file, alert or the assistant's input.
- **Don't:** forward `full_log`, `data.*` or any free-text field of a SIEM alert to an assistant; give the assistant a token that can run actions (SEC-DET-10).

### SEC-DET-10: Add a SIEM when the need is real, and trial it time-boxed
- **Rule:** adopt a SIEM (for example Wazuh) when you need what the pack cannot give: file-integrity monitoring on large trees with "who changed it", configuration assessment (CIS), ready-made rules across many hosts, or audit-log correlation. Before that, run it as a time-boxed trial on a throwaway machine with success criteria written first.
- **Why:** a full SIEM is memory-hungry (around 2.7 GB of RAM for the whole stack with a few dozen agents, 4 vCPU and 50 GB recommended), noisy until tuned, and its manager is a high-value target (several critical remote-code-execution flaws in 18 months, one in the CISA KEV catalog). Putting it on an already saturated hypervisor makes things worse.
- **How:** a one-week plan:
  1. Pick a machine with free RAM and a calm I/O profile (check pressure: `cat /proc/pressure/io`); never a hypervisor that is already I/O-saturated. Single node, no cluster, latest stable release; check the kernel setting the indexer needs (`vm.max_map_count`).
  2. Change every default credential before first login; expose manager ports (agents' ports and API) to the LAN or agent addresses only; never to the internet. Agents on third-party hosts are allowed only with the owner's written permission and through a source allowlist for the agent port (SEC-SIEM-1, SEC-FW-13); the enrollment port and the API are never opened to the internet.
  3. Install agents on one or two hosts; limit file-integrity paths to `/etc`, root's `.ssh` and `/usr/sbin`, not real-time at first (later, real-time only on narrow high-signal paths such as CMS upload folders, SEC-SIEM-4), and turn the package's default first-start scan off before the first start (SEC-SIEM-2).
  4. Run `logtest` with real log lines from your OS (the journal format of `sshd-session`, the hypervisor auth daemon) to confirm decoders match; test file-integrity monitoring on special filesystems (such as the hypervisor's cluster config, a FUSE mount) before relying on it.
  5. Forward only minimal JSON (rule, level, host, validated IP) to the alert path you already have, so there is one route with dedupe and mute (SEC-SIEM-3); test with the indexer and dashboard stopped to learn whether a manager-only variant is enough (an unsupported topology: measure).
  6. Give any AI assistant a read-only role; it must never reach the active-response or agent-upgrade endpoints.
  7. Write the removal steps up front (`docker compose down -v`, remove the agent package and its directory on every host, undo sysctl and firewall changes, delete the API user).
- **Verify:** success criteria met on day 7: at least one true detection the pack lacks, at most five level>=10 alerts a day after tuning, agent memory and I/O impact acceptable, the assistant answers "what happened in the last 24 hours" with one command. If not met, do the removal.
- **After the trial:** SIEM operation is in [wazuh-fim.md](wazuh-fim.md): agents on other people's servers, alert forwarding, file-integrity rule design and its silent failure modes.
- **Don't:** install it because it is fashionable; let the trial become permanent without re-checking resources and patch ownership; skip updating the manager.

### SEC-DET-11: Monitoring that alerts nobody is not monitoring
- **Rule:** every trigger has a route to a person or team, verified end to end, and noise is reduced before the alert goes live. Stale and noisy problems are cleaned so that a new real alert stands out.
- **Why:** an alert nobody sees is a log. An alert that fires 48 times from one flapping trigger teaches everyone to mute the channel, and the real one is lost.
- **How:**
  - Check the routing rules, not only the triggers: in one pipeline the notifier ignored events whose host lacked the tags its action required (project and unit tags), so a new set of intrusion triggers would have notified nobody until the hosts were tagged. List the actions, their severity filters and required tags before creating triggers.
  - Test end to end with a synthetic problem (a trigger on a test item, or a manual event) and confirm the person receives it, then close it.
  - Simulate noise: replay 30 days of past events through the routing rules and count what would page. One trigger often produces most events; require several consecutive failures (`count(...,#3,"ne",200)=3 or nodata(15m)`), filter flapping interfaces with a regex macro, and send planned reboots through maintenance windows (`pause_suppressed` actions hold the alert).
  - Match severity to channel: immediate for High, delayed for Average (a short Average never pages), dashboard only for Info.
  - Mind the receiver's rate limit: a node reboot with no maintenance window can exceed it.
  - Close or fix stale problems monthly; an alert list with hundreds of old items hides the new one. Distrust "0 problems" from a monitor that lacks data for months.
  - Have an external check that the routing still works (SEC-DET-7).
- **Verify:** a table of triggers with route, severity, who is on the hook; the last end-to-end test date; the 30-day replay count.
- **Don't:** enable new High triggers on hosts that are not yet tagged for routing; page for conditions that clear themselves in under the notification delay.

### SEC-DET-12: Check services from outside the network, with content checks and two vantage points
- **Rule:** an availability check that runs inside the network measures the inside. Probe from outside the way the public reaches the service, validate content, and confirm any "down" from a second vantage point before reacting.
- **Why:** inside a site you often cannot reach your own public address (no hairpin NAT), a resolver inside may differ from the public one, a service behind a CDN is served by the CDN, and a path problem between one network and one provider looks like an outage from that network only.
- **How:**
  - Run a probe in a separate network namespace or machine that leaves and re-enters through a different uplink, with a public resolver and a fixed MAC (a random MAC per run left stale ARP entries in the router and broke the probe for 30+ seconds). Validate the probe against a public address, not the gateway, which may not answer ping but still forwards.
  - Check what the user needs, not a 200: for a file type, parse it (a missing download returned `200` with an HTML page, so check the first bytes and required keys); read in binary.
  - Keep "could not resolve" distinct from "resolves to a different address", and compare DNS records with the live address if it is dynamic (a changed address leaves public players dead while CDN-served pages stay up).
  - When a site-down alert fires, test the same URL from a second network and from the server itself; if only one source fails, it is a path problem, not an outage.
  - Skip, rather than fail, checks whose own probe infrastructure failed.
- **Verify:** break something deliberately (stop a service, point DNS wrong) and confirm the verdict changes; confirm that a probe failure does not raise a false "everything is down".
- **Don't:** treat a status code as proof of function; sample an origin that the public does not actually use.

### SEC-DET-13: Retired
- **Retired:** hypervisor and management-plane material that is not part of bridgeai. The ID stays reserved.

### SEC-DET-14: Verify claims with evidence, including your own tools and analyses
- **Rule:** "patched", "deployed", "clean", "0 logins" and "all hardened" are claims until backed by a command output you can read: a version string, a package-log date, a file hash, an `Accepted` line. This applies to AI agents (SEC-POL-11), to monitoring scripts, and to your own audit.
- **Why:** an agent confirmed a security patch that never ran (no package transaction after the image build; and an in-container change would have been lost anyway, SEC-CONT-5). An audit script printed "clean" because its pattern was blind (SEC-DET-1). A draft analysis attributed a large count to the wrong activity until each figure was re-checked.
- **How:** ask for the evidence command and run it yourself: `tail /var/log/apt/history.log`, `dpkg -l <package>`, `stat -c %y <binary>`, `docker exec <container> <tool> --version` after a recreate. Test a detector on a known positive. When two analyses disagree, mark each statement as verified live, taken from notes, or inferred, and prefer the one that was verified live.
- **Verify:** the report names the command and its output, plus the date; unverified items are labeled.
- **Don't:** accept "done" from an agent that has no execution log for the change; copy conclusions between analyses without re-measuring.

### SEC-DET-15: A full file-integrity database silently stops reporting new files
- **Rule:** monitor the occupancy of the file-integrity (FIM) database of every agent from the server side (files tracked divided by the configured file limit), with escalating steps (80 % Warning, 95 % High, and a "full" state for the vendor's 100 % event), and keep those alerts open as long as the condition lasts.
- **Why:** checked in the Wazuh 4.14 source: once an agent's database reaches `file_limit` (default 100,000), a new file produces no event at all, not even in real time; only a local agent log line remains. There is no "evict the oldest": the new thing is rejected. The built-in "limit reached" alert (rule 233, level 12) fires once per transition and again after each agent restart, with earlier warnings at 80 % (rule 231) and 90 % (rule 232). If the alert pipeline closes it after a minute, nobody sees that the host has been blind since. Quota is eaten by whatever is large and boring: a certificate tool's leftovers can be most of the 100,000 entries (SEC-PATCH-21), and the web tree that matters is then no longer guaranteed to be tracked.
- **How:**
  1. From the manager's per-agent database (table `fim_entry`) count entries per agent, and for the tree that matters (for example `select count(*) from fim_entry where full_path like '/var/www/%'`). Divide by the agent's `file_limit` and send the percentage to the monitoring system every ~10 minutes.
  2. Triggers: Warning at 80 %, High at 95 %, "full" (the vendor's 100 % event, rule 233, passed on as a state) and "last scan did not finish in 26 hours" (from the scan table). They are states: the problem stays open while the condition holds; the integration must not auto-close it.
  3. Set `file_limit` explicitly to about twice the real usage instead of the default, per group, in the same publication as other changes (SEC-DET-16).
  4. When the quota is full, free it by deleting data (SEC-DET-17), not by excluding directories.
- **Verify:** on a test agent set a tiny `file_limit`, create a file after the scan, and confirm that (a) no FIM event arrives for it and (b) your occupancy alert is open. Then restore the limit.
- **Don't:** rely on the vendor's one-shot "limit reached" event as the only signal; assume "no alerts from this host" means "nothing changed there".
- **See also:** SEC-SIEM-8 (the same silent limit in the Wazuh operations doc, with the database-socket query and rule IDs 231 to 233)

### SEC-DET-16: Every config publication restarts the FIM and silently re-baselines it
- **Rule:** treat each publication of a group configuration as a restart of file-integrity monitoring on every agent of the group: whatever is planted at that moment becomes the new baseline with no event. Batch all changes into one scheduled, off-hours publication, and run an absorption check right after.
- **Why:** checked in the 4.14 source: the agent's FIM database is volatile, so after a restart it is rebuilt as a baseline without generating events, and `scan_on_start=no` does not change that. Each publication also rescans every agent of the group, which costs the hosts performance if done in daytime. A restart may also fire the "agent stopped" alert on each host (SEC-DET-19), but a configuration-driven restart can happen without it, so verify by configuration hash (SEC-SIEM-10).
- **How:**
  - Collect all pending config changes, publish once, at night, with the publisher script of SEC-POL-14; announce it to whoever watches alerts.
  - Absorption check (server side, hourly and right after every publication): keep the manager's inventory of paths under the sensitive trees (executable-type files, web-server override files), and after any agent restart compare it with the previous snapshot. A new executable-type file that has no matching "added" event is an alert.
  - Limits to state honestly: the inventory is fed by the agent itself, so against an attacker with root on the host it is not independent truth; it works against attackers without root and it lets you notice absorption caused by your own restarts.
  - After deleting a very large number of files to free quota, do not restart the agent or publish until the next scheduled scan: by the code, that second pass registers the files rejected while the database was full, and those do generate events. Restarting earlier would absorb them. (Expected from the source; confirm the first time.)
- **Verify:** after a publication, the absorption check ran and reported zero unexplained new files; the number of publications per week is known.
- **Don't:** publish "just one small change" during the day; assume a quiet restart is harmless on a host that may already hold something planted.
- **See also:** SEC-SIEM-10 (verification with the agent's configuration hash; a configuration-driven restart may emit no "agent stopped" alert), SEC-POL-14 (the publisher script)

### SEC-DET-17: Delete stale data instead of excluding directories, and classify on the server
- **Rule:** when a directory floods the FIM with noise or quota, delete the stale data. If something must be tolerated, do it with an anchored rule on the manager; the agent collects broadly and decides nothing (SEC-POL-13).
- **Why:** two agent-side filters hide more than they seem (checked in the 4.14 source):
  - `<ignore type="sregex">` is an unanchored, case-insensitive substring match and also applies in real time. Excluding `node_modules` makes `<web-root>/<site>/uploads/node_modules/shell.php` invisible, and anyone who reads the config knows it.
  - `restrict` is already case-insensitive (uppercase extension variants are redundant), but it only lets through the listed names: `.htaccess`, `.user.ini`, `.inc`, `php.ini` and extensionless files never reach the rules, and a one-line `.htaccess` that maps another extension to the PHP handler turns an image upload into code.
- **How:**
  - Replace "allow-list of PHP extensions" with "everything except media extensions" (a negated `restrict`), after measuring the volume, so the manager sees everything and rules classify it.
  - Move noise reduction to manager rules anchored to the real path, for example `^/var/www/[^/]+/(web/)?wp-content/cache/`, never to a bare substring. Measure how much the cache really changes before silencing it.
  - Add a high-level rule for `.htaccess` and `.user.ini` created or changed in upload directories.
  - For quota problems, find the biggest directories in the database and clean the cause (SEC-PATCH-21), then re-measure occupancy (SEC-DET-15).
  - Roll the whole change as one publication (SEC-DET-16), then run the absorption check.
- **Verify:** from the agent's received config, none of the exclusions can be read; a test file named like an excluded substring inside an uploads directory still produces an alert.
- **Don't:** add `<ignore>` lines "temporarily"; copy the vendor's example exclusions into the agent without anchoring them.
- **See also:** SEC-SIEM-12 (the same principle for the agent configuration), SEC-SIEM-9 (clear clutter by deleting it)

### SEC-DET-18: Assume every FIM limit fails silently and alert on the anomaly itself
- **Rule:** write down the silent limits of the tool, and add manager rules where the anomaly is the signal: path depth, avalanches of new or deleted files, files that do not belong in a tool-owned directory.
- **Why:** checked in the 4.14 source, each of these gives no alert, only a local log or a debug line:
  - paths deeper than `recursion_level` (default 256) are skipped, debug log only;
  - names that are not valid UTF-8 are skipped, with a warning only on the agent;
  - inotify watches exhausted (`ENOSPC`) leave real-time monitoring partial, only in the local log;
  - upload directories created after the last scan are watched in real time only after the next daily scan.
  Anyone who knows these limits can plant something exactly there.
- **How:**
  - Depth rule: new or modified executable-type file whose path is deeper than N levels under the web root (high level). Pick N from your inventory: count the existing files that would match at each candidate threshold, and clean those first (a shallow threshold can match hundreds of legitimate vendor files, a deeper one none).
  - Avalanche rules: 300+ new files from one agent in 10 minutes; 1,000+ deletions from one agent in 10 minutes (a planned cleanup will trigger it: expect one alert and say so beforehand).
  - Trap rule: any file in a directory that only a tool writes (for example certificate keys and requests) whose name does not follow the tool's pattern.
  - Raise `fs.inotify.max_user_watches` on hosts with large trees, and look at the agent's local log after the first scan of a new tree.
  - Before enabling real-time monitoring on upload directories of a new site, run `find <docroot>/<uploads> -name '*.php'` to see which plugins store PHP there.
- **Verify:** plant a test file deeper than N, a burst of empty files, and a stray file in the tool-owned directory on a test agent; each raises its alert.
- **Don't:** publish the thresholds to the agent or in comments (SEC-POL-13).
- **See also:** SEC-SIEM-7 (depth rule as a child of "new script"), SEC-SIEM-9 (avalanche and trap rules)

### SEC-DET-19: A stopped or disconnected agent is a detection event
- **Rule:** raise the level of "agent stopped" and "agent disconnected" so they reach a person, and know how long each takes to surface.
- **Why:** the defaults are low (level 3 in the vendor ruleset), and stopping the agent is the first move of a careful intruder. A disconnected agent takes about 25 minutes to page (about 10 minutes of vendor timeout plus the trigger's 15). Agents that never connected do not alert at all.
- **How:** "stopped" at a mid level that does not page (restarts and package upgrades cause one, and config publications often do, although a configuration-driven restart can also happen without it: SEC-DET-16, SEC-SIEM-10); "disconnected for 15 minutes" at a paging level, sent to the monitoring system as a state. If the rules match agent names by prefix, a new customer with another prefix is not covered until the prefix is added to the rule and to the integration: keep that list next to the onboarding checklist. Optionally lower the disconnection timeout to shorten the delay.
- **Verify:** stop the agent on a test host and time how long until a person is notified; do the same with a firewall block.
- **Don't:** count "no events from host X for a day" as health; page on every restart.
- **See also:** SEC-SIEM-13 (stopped, disconnected and database-full as states)

### SEC-DET-20: A host that was compromised before: preserve evidence, hunt by change time, check use, clean, rotate, fix the cause
- **Rule:** when a past compromise is discovered by accident (a disk alert, an odd process), run it as a forensic task in this order: preserve evidence, hunt by change time rather than modification time and beyond PHP, establish with real evidence whether the access was used, clean to a verified state, rotate every credential that lived on the host, and remove the root cause.
- **Why:**
  - An attacker can set a file's modification time to match its neighbours but not its change time (`ctime`); a hunt by `mtime` misses what was disguised.
  - Injected content in a CMS is often not PHP: obfuscated JavaScript appended to theme files, a hijacked `ads.txt`, a few lines inside an otherwise official plugin file.
  - Freeing space by vacuuming the journal destroys the history you need; an old compromise may also hide behind a newer one.
- **How:**
  - **Preserve:** copy the journal (`/var/log/journal`), rotated web and database logs and `atop`-type history to a root-only evidence directory before cleaning or vacuuming; move removed malware there rather than deleting it.
  - **Hunt:** by change time within the window you suspect (first timestamp = start, second = end), all file types in the web root:
    ```bash
    sudo find <docroot> -type f -newerct '<YYYY-MM-DD HH:MM>' ! -newerct '<YYYY-MM-DD HH:MM>' -printf '%C+ %T+ %u %p\n' | sort | head -200
    sudo find <docroot> -type f -printf '%C@ %T@ %p\n' | awk '$1 - $2 > 86400 {print}' | head   # ctime far newer than mtime: mtime may be forged (also true after restores; judge by the paths)
    wp core verify-checksums; wp plugin verify-checksums --all                                 # official files against upstream hashes (adapt: needs WP-CLI as the site user)
    sudo dpkg -V | awk 'NF==2'                                                                  # modified package files; config files (marked c) are excluded
    ```
    Also check for foreign cron entries, systemd units, `authorized_keys`, kernel modules, accounts with sudo and hidden names (a directory name ending in spaces), and the accounts and keys list of SEC-DET-2.
  - **Was it used:** answer only from evidence windows you really have: process accounting or `atop` history (what the web user spawned), the database's query history for queries not from your own tools, web logs for requests to the backdoor's file names and for abnormal response sizes. State plainly which periods have no logs.
  - **Clean:** restore official files and verify hashes; cut an injected block at its exact start; analyse obfuscated scripts in an isolated interpreter with no network (for example Node's `vm` module) to learn what they do, never in a browser.
  - **Rotate:** every credential that lived on or passed through the host, as one batch (SEC-POL-4, SEC-POL-10): database users and application configuration, CMS salts and keys, system passwords, SSH keys. Lock accounts the web server runs as (no password, `nologin`), tighten home directories, and fix the cause (a web user that owns every docroot lets one flaw rewrite all sites).
  - **Decide notification** with the owner from the evidence of access to data, and write the decision down.
- **Verify:** the evidence directory exists and is root-only; every hit from the hunt is explained; checksums verify; the rotation list is complete; the web user no longer owns the code.
- **Don't:** hunt only by `mtime` or only for `.php`; vacuum logs first; declare "not used" without naming the windows that have no logs; delete the malware sample before analysing it.

### SEC-DET-21: Triage a level-10+ alert with fixed fields, then ask three questions
- **Rule:** classify each high-level web or integrity alert from fixed fields only (rule, level, agent, validated source address, HTTP status, a sanitized path; SEC-DET-9), and answer three questions: could the request reach code that acts on the payload; is there a matching change on the host in the same minute; is it explained by something we did.
- **Why:** most high-level alerts are noise from scanners or consequences of your own maintenance, and a few are real. A verdict made from raw payload text is both slow and unsafe.
- **How:**
  ```bash
  # one line per (rule, level, agent): what fired most in the window (adapt: needs jq; the file is the SIEM's alert log)
  sudo jq -r 'select(.rule.level>=7) | [.rule.id,.rule.level,.agent.name]|@tsv' /var/ossec/logs/alerts/alerts.json | sort | uniq -c | sort -rn | head -30
  ```
  - A shell-injection probe against a site with no shell-script handler gets `200` because the page was served; that is not evidence it worked. A `403` from the WAF means the defence worked.
  - A new-file or deleted-file flood right after your clean-up, a package upgrade, or a group configuration publish is its expected consequence (SEC-SIEM-9, SEC-SIEM-10): match each flood to your change record.
  - A `su` from root to a service user is local, not a remote login; an agent restart pair (stopped/started) is a publish or an upgrade.
  - The same network range hitting several hosts within hours is one scanner moving through the fleet: record the range once and ban it.
  - A rule that fires on your own tool's output needs an exception, not a mute (SEC-SIEM-5).
  - Anything that survives these questions (a script in an upload folder you did not put there, a deep new path, a login you cannot explain) is an incident: SEC-DET-20.
- **Verify:** each alert group in the report has a verdict (noise, explained by our change, investigate) and the evidence field that justified it.
- **Don't:** treat a status code as proof either way; hand raw log lines to an assistant to "summarize"; leave a group without a verdict.

## Checklist: intrusion pack and audit

1) SSH audit from the journal with `sshd` and `sshd-session`, tested on a known login (SEC-DET-1).
2) Known-source list per host; every accepted login explained; accounts and keys reviewed (SEC-DET-2).
3) Third-party root agents and patch schedules listed (SEC-DET-3).
6) Canary account and decoy key in place before baselining hashes (SEC-DET-6).
7) Heartbeat trigger and an external watcher on another machine (SEC-DET-7).
8) Evasion list reviewed; password logins removed so any one is an alert (SEC-DET-8).
9) Only fixed fields reach any AI assistant (SEC-DET-9).
10) Every trigger has a verified route; 30-day noise replay done (SEC-DET-11).
11) External probe with content checks and a second vantage point (SEC-DET-12).
13) SIEM only after the pack, as a time-boxed trial with removal steps (SEC-DET-10).
14) A past compromise is handled as evidence first, then hunt by `ctime`, then rotation (SEC-DET-20).
15) High-level alerts get a verdict from fixed fields and the change record (SEC-DET-21).
16) FIM occupancy per agent monitored from the server, with open states at 80 %, 95 % and full (SEC-DET-15).
17) Group configs published once, at night, followed by the absorption check (SEC-DET-16).
18) Noise handled by anchored manager rules and by deleting stale data, not by agent-side exclusions; depth, avalanche and trap-file rules in place (SEC-DET-17, SEC-DET-18).
19) Stopped and disconnected agents reach a person; the delay is measured (SEC-DET-19).
