---
title: Security guide (index)
scope: servers, sites, repos, credentials and AI assistants run by one person or a small team; the knowledge behind bridgeai's `sysadmin` pack
when_to_use: start here for any security task; find the doc for the situation at hand
related: [SECURITY_WATCH.md, DEBIAN13_MIGRATION.md, policies.md, patching.md, hardening-ssh-fail2ban-waf.md, firewall-and-ports.md, containers-and-images.md, detection-and-audit.md, publishing-without-leaks.md, static-sites-deploy-keys.md, web-exposure.md, software-and-data-access.md, wazuh-fim.md, backups-and-storage.md, storage-performance.md]
---
# Security guide

Reusable security knowledge: procedures, rules, lessons and tools. The `sysadmin` pack (`../SYSADMIN_PLAN.md`, `../SKILL_sysadmin.md`)
reads it: each of its checks names the rule it verifies, and the agent cites that rule ID when it reports or proposes a change.
It is written in a fixed shape so a person or an AI assistant can find the right rule quickly and cite it by ID.

## Find the doc for your situation
| Situation | Read |
|---|---|
| A CVE is announced, or it is in CISA KEV | [patching.md](patching.md) |
| A scanner (Vuls, Trivy, WPScan) reported findings | [patching.md](patching.md) |
| Planning a patch window or a reboot of a host/hypervisor | [patching.md](patching.md) |
| `/etc/letsencrypt/keys` or `csr` holds thousands of files; certbot retries a certificate another system serves | [patching.md](patching.md) (SEC-PATCH-21, 22) |
| Rebooting a guest with dozens of PHP-FPM pools; services failed with `timeout` after boot | [patching.md](patching.md) (SEC-PATCH-23) |
| Creating, storing or rotating a password, token or key | [policies.md](policies.md) (SEC-POL-3 to 6) |
| Writing a monitoring agent's configuration, or publishing a shared one to many agents | [policies.md](policies.md) (SEC-POL-13, 14) |
| Giving or removing access for someone outside the team | [policies.md](policies.md) (SEC-POL-1, 2, 9) |
| A secret was pasted in a chat, log or commit | [policies.md](policies.md) (SEC-POL-10) |
| A password or token is about to go into a command line, or an assistant read a credentials file | [policies.md](policies.md) (SEC-POL-16) |
| About to run a test, scan or one-off command on a customer's server | [policies.md](policies.md) (SEC-POL-15) |
| A security or pentest tool (offensive, AI-driven, or a fork) is proposed | [policies.md](policies.md) (SEC-POL-17) |
| A bot or AI agent must edit a site, or reports "done" | [policies.md](policies.md) (SEC-POL-7, 11) |
| Hardening SSH, fail2ban does not ban, slow login brute force, banning behind Cloudflare, tarpit, mini-WAF | [hardening-ssh-fail2ban-waf.md](hardening-ssh-fail2ban-waf.md) |
| Password SSH only from one country; a WAF jail locked out real users; an admin/API URL restricted by source behind proxies | [hardening-ssh-fail2ban-waf.md](hardening-ssh-fail2ban-waf.md) (SEC-HARD-12 to 14) |
| Changing firewall/routing rules, reviewing exposed ports, Docker ports vs ufw | [firewall-and-ports.md](firewall-and-ports.md) |
| A monitoring or SIEM agent port must be reachable from the internet | [firewall-and-ports.md](firewall-and-ports.md) (SEC-FW-13) |
| Hardening a container, tenant networks, databases in Docker, agent containers | [containers-and-images.md](containers-and-images.md) |
| Auditing who logged in, intrusion checks, alert design, whether to add a SIEM | [detection-and-audit.md](detection-and-audit.md) |
| A file-integrity database may be full; a config publish; silent FIM limits; an agent stopped or disconnected | [detection-and-audit.md](detection-and-audit.md) (SEC-DET-15 to 19) |
| A host turns out to have been compromised earlier; a high-level alert needs a verdict | [detection-and-audit.md](detection-and-audit.md) (SEC-DET-20, 21) |
| Installing a SIEM agent on a customer's server; forwarding SIEM alerts; file-integrity (FIM) rules, exceptions, full FIM database, group config publish | [wazuh-fim.md](wazuh-fim.md) |
| Telling a non-technical owner what the monitoring found | [wazuh-fim.md](wazuh-fim.md) (SEC-SIEM-14) |
| Making a repo public, a scan blocked a commit, a secret reached git | [publishing-without-leaks.md](publishing-without-leaks.md) |
| A bot or contractor edits a website; a publish "finished" but nothing changed | [static-sites-deploy-keys.md](static-sites-deploy-keys.md) |
| Which advisories to follow for what we run, or checking a host against them | [SECURITY_WATCH.md](SECURITY_WATCH.md), [../ops/FACT_MODEL.md](../ops/FACT_MODEL.md) |
| Moving the base image to a new Debian release, or a browser CVE in Playwright | [DEBIAN13_MIGRATION.md](DEBIAN13_MIGRATION.md) |
| A certificate expires, a site still answers on HTTP, headers or versions a visitor sees, `/.git` exposed | [web-exposure.md](web-exposure.md) |
| An agent installs software or can send files out; protecting a private project or confidential code | [software-and-data-access.md](software-and-data-access.md) |
| Copying a VM or a large dataset to a backup disk; a backup disk is slow or reports errors; offline backups; VM disk cache modes and readahead | [backups-and-storage.md](backups-and-storage.md) |
| Disks run hot; a host with many seeding VMs has high iowait; an SSD or RAM read cache is proposed; btrfs vs xfs for VM images | [storage-performance.md](storage-performance.md) |

## Documents
| File | Status | Covers |
|---|---|---|
| [policies.md](policies.md) | ready | Access, credentials, secrets storage, rotation, third parties, AI agents, publishing, keeping monitoring criteria off the monitored machine, publishing shared monitoring configuration, customer machines, secrets in assistant-recorded commands, vetting third-party offensive tools |
| [patching.md](patching.md) | ready | KEV-first priorities, patching without reboot, canaries, apt/dpkg pitfalls, Vuls, Trivy, patch windows, reboot checks for service-heavy guests, certbot key and request cleanup |
| [hardening-ssh-fail2ban-waf.md](hardening-ssh-fail2ban-waf.md) | ready | fail2ban on Debian 13, ModSecurity-based jails, banning behind Cloudflare, tarpits, slow login brute force, country-restricted password SSH, WAF false-positive review, source-restricted admin endpoints |
| [firewall-and-ports.md](firewall-and-ports.md) | ready | Dead-man switch for firewall changes, atomic rule loads, external port reviews, Docker `-p` vs ufw, allowlists for public agent-ingest ports |
| [containers-and-images.md](containers-and-images.md) | ready | Verifying real container hardening, image rebuilds, guest networks without LAN |
| [detection-and-audit.md](detection-and-audit.md) | ready | SSH access audits, intrusion checks, alert design, when to add a SIEM, silent file-integrity limits and config publishes, stopped agents, investigating a past compromise, alert triage |
| [wazuh-fim.md](wazuh-fim.md) | ready | Wazuh in operation (rule IDs `SEC-SIEM-n`): agents on customer servers, scan load, alert forwarding, upload-folder watch, exceptions, FIM database limits and silent failure modes, rule-change procedure, reporting to owners |
| [publishing-without-leaks.md](publishing-without-leaks.md) | ready | Secret scanning hooks, public vs internal repos, history rewrites |
| [static-sites-deploy-keys.md](static-sites-deploy-keys.md) | ready | Sites edited by bots through one-repo deploy keys and a separate publisher |
| [SECURITY_WATCH.md](SECURITY_WATCH.md) | design | Stack-aware security watch: profile, catalog-driven feeds, matching, verification, upkeep skill, all-in-one vs split bots |
| [DEBIAN13_MIGRATION.md](DEBIAN13_MIGRATION.md) | done | Base image Debian 12 to 13 (built, smoke-tested, rolled out by ops/PIPELINE.md), and Playwright's bundled Chromium bumps |
| [backups-and-storage.md](backups-and-storage.md) | ready | Verified backup copies (stream and file hashes, full read-back), backup-disk health and error recovery, throttled copies, trim before backup, cold-storage cycle, rotating verification, VM disk cache and readahead (rule IDs `SEC-STOR-n`) |
| [storage-performance.md](storage-performance.md) | ready | Serving much content from HDDs with little wear and heat: temperature vs airflow, IO caps, experiments with a paired control, btrfs vs xfs write amplification, read caches, thermal throttle (rule IDs `SEC-PERF-n`; every effect labelled measured, documented, expected or measure first) |
| A web or service guest writes too much to disk; logs, journal, sessions and temp files to RAM | [storage-performance.md](storage-performance.md) (SEC-PERF-22) |
| [web-exposure.md](web-exposure.md) | ready | TLS and certificates, HTTPS only, security headers, version banners, private files under the web root, CDN origins |
| [software-and-data-access.md](software-and-data-access.md) | design | Agent installs through a package gateway, outbound control, an outside watcher, and data access levels L0 to L4 |

## What goes here and what does not
- **Here (shared):** what to do and why, commands with placeholders (`<host>`, `<vmid>`, `<domain>`), lessons, checklists, tools and how to use them, policies.
- **Not here (private ops notes):** which host has which port open, per-host patch status, pending items and deadlines, who has access, where each credential lives, per-client findings, scanner results. Those stay in the operator's private repository; a lesson here may say "Real case:" in one anonymized line.
- **Never anywhere in git:** secret values (see SEC-POL-5 and SEC-POL-12).

## Conventions (for people and AI assistants)
- Every doc starts with YAML front matter: `title`, `scope`, `when_to_use`, `related`.
- Each doc owns one rule-ID prefix (`SEC-POL`, `SEC-PATCH`, `SEC-HARD`, `SEC-FW`, `SEC-CONT`, `SEC-DET`, `SEC-PUB`, `SEC-SITE`, `SEC-WEB`, `SEC-SIEM`, `SEC-STOR`, `SEC-PERF`); a new rule takes the next free number in its document.
- Rules have stable IDs (`SEC-POL-n`, `SEC-PATCH-n`, ...). Never renumber; retire a rule by marking it **Retired** with the date and the replacement.
- Each rule uses the same fields: **Rule**, **Why**, **How**, **Verify**, **Don't**.
- Commands are copy-pasteable with placeholders in `<angle brackets>`; destructive steps say so.
- When a rule changes, say what changed in the commit message.
- AI assistants: cite the rule ID you are applying; if the docs and the situation disagree, stop and ask rather than improvise.
