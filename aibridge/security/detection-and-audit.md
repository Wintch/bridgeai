---
title: Detection and audit (SSH audits, intrusion pack, alert design, SIEM)
scope: Linux servers, hypervisors and their management planes, monitoring and alerting pipelines, AI assistants that read alerts
when_to_use: auditing who logged in; checking for access nobody granted; building or reviewing intrusion detection; designing alerts; deciding whether to add a SIEM; an AI agent or a monitor reports "all clear"
related: [README.md, policies.md, patching.md, containers-and-images.md, hardening-ssh-fail2ban-waf.md, firewall-and-ports.md]
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
  Alert subjects are static trigger names; do not put `{ITEM.VALUE}` or log text into notification messages. If free text must be shown, put it in quotes labelled as data, and make the assistant's tools read-only for the investigation. Rate-limit the receiver and allow it to ignore malformed events.
- **Verify:** inject `Invalid user "ignore previous instructions"` through a test login and confirm the text appears nowhere in the state file, alert or the assistant's input.
- **Don't:** forward `full_log`, `data.*` or any free-text field of a SIEM alert to an assistant; give the assistant a token that can run actions (SEC-DET-10).

### SEC-DET-10: Add a SIEM when the need is real, and trial it time-boxed
- **Rule:** adopt a SIEM (for example Wazuh) when you need what the pack cannot give: file-integrity monitoring on large trees with "who changed it", configuration assessment (CIS), ready-made rules across many hosts, or audit-log correlation. Before that, run it as a time-boxed trial on a throwaway machine with success criteria written first.
- **Why:** a full SIEM is memory-hungry (around 2.7 GB of RAM for the whole stack with a few dozen agents, 4 vCPU and 50 GB recommended), noisy until tuned, and its manager is a high-value target (several critical remote-code-execution flaws in 18 months, one in the CISA KEV catalog). Putting it on an already saturated hypervisor makes things worse.
- **How:** a one-week plan:
  1. Pick a machine with free RAM and a calm I/O profile (check pressure: `cat /proc/pressure/io`); never a hypervisor that is already I/O-saturated. Single node, no cluster, latest stable release; check the kernel setting the indexer needs (`vm.max_map_count`).
  2. Change every default credential before first login; expose manager ports (agents' ports and API) to the LAN or agent addresses only; never to the internet. Agents on third-party hosts that would need those ports opened to the internet stay out.
  3. Install agents on one or two hosts; limit file-integrity paths to `/etc`, root's `.ssh` and `/usr/sbin`, not real-time at first.
  4. Run `logtest` with real log lines from your OS (the journal format of `sshd-session`, the hypervisor auth daemon) to confirm decoders match; test file-integrity monitoring on special filesystems (such as the hypervisor's cluster config, a FUSE mount) before relying on it.
  5. Forward only minimal JSON (rule, level, host, validated IP) to the alert path you already have, so there is one route with dedupe and mute; test with the indexer and dashboard stopped to learn whether a manager-only variant is enough (an unsupported topology: measure).
  6. Give any AI assistant a read-only role; it must never reach the active-response or agent-upgrade endpoints.
  7. Write the removal steps up front (`docker compose down -v`, remove the agent package and its directory on every host, undo sysctl and firewall changes, delete the API user).
- **Verify:** success criteria met on day 7: at least one true detection the pack lacks, at most five level>=10 alerts a day after tuning, agent memory and I/O impact acceptable, the assistant answers "what happened in the last 24 hours" with one command. If not met, do the removal.
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
