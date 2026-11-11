---
title: Security guide (index)
scope: servers, sites, repos, credentials and AI assistants run by one person or a small team; the knowledge behind bridgeai's `sysadmin` pack
when_to_use: start here for any security task; find the doc for the situation at hand
related: [policies.md, patching.md, hardening-ssh-fail2ban-waf.md, firewall-and-ports.md, containers-and-images.md, detection-and-audit.md, publishing-without-leaks.md, static-sites-deploy-keys.md, web-exposure.md]
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
| Creating, storing or rotating a password, token or key | [policies.md](policies.md) (SEC-POL-3 to 6) |
| Giving or removing access for someone outside the team | [policies.md](policies.md) (SEC-POL-1, 2, 9) |
| A secret was pasted in a chat, log or commit | [policies.md](policies.md) (SEC-POL-10) |
| A bot or AI agent must edit a site, or reports "done" | [policies.md](policies.md) (SEC-POL-7, 11) |
| Hardening SSH, fail2ban does not ban, slow login brute force, banning behind Cloudflare, tarpit, mini-WAF | [hardening-ssh-fail2ban-waf.md](hardening-ssh-fail2ban-waf.md) |
| Changing firewall/routing rules, reviewing exposed ports, Docker ports vs ufw | [firewall-and-ports.md](firewall-and-ports.md) |
| Hardening a container, tenant networks, databases in Docker, agent containers | [containers-and-images.md](containers-and-images.md) |
| Auditing who logged in, intrusion checks, alert design, whether to add a SIEM | [detection-and-audit.md](detection-and-audit.md) |
| Making a repo public, a scan blocked a commit, a secret reached git | [publishing-without-leaks.md](publishing-without-leaks.md) |
| A bot or contractor edits a website; a publish "finished" but nothing changed | [static-sites-deploy-keys.md](static-sites-deploy-keys.md) |
| A certificate expires, a site still answers on HTTP, headers or versions a visitor sees, `/.git` exposed | [web-exposure.md](web-exposure.md) |

## Documents
| File | Status | Covers |
|---|---|---|
| [policies.md](policies.md) | ready | Access, credentials, secrets storage, rotation, third parties, AI agents, publishing |
| [patching.md](patching.md) | ready | KEV-first priorities, patching without reboot, canaries, apt/dpkg pitfalls, Vuls, Trivy, patch windows |
| [hardening-ssh-fail2ban-waf.md](hardening-ssh-fail2ban-waf.md) | ready | fail2ban on Debian 13, ModSecurity-based jails, banning behind Cloudflare, tarpits, slow login brute force |
| [firewall-and-ports.md](firewall-and-ports.md) | ready | Dead-man switch for firewall changes, atomic rule loads, external port reviews, Docker `-p` vs ufw |
| [containers-and-images.md](containers-and-images.md) | ready | Verifying real container hardening, image rebuilds, guest networks without LAN |
| [detection-and-audit.md](detection-and-audit.md) | ready | SSH access audits, intrusion checks, alert design, when to add a SIEM |
| [publishing-without-leaks.md](publishing-without-leaks.md) | ready | Secret scanning hooks, public vs internal repos, history rewrites |
| [static-sites-deploy-keys.md](static-sites-deploy-keys.md) | ready | Sites edited by bots through one-repo deploy keys and a separate publisher |
| [web-exposure.md](web-exposure.md) | ready | TLS and certificates, HTTPS only, security headers, version banners, private files under the web root, CDN origins |

## What goes here and what does not
- **Here (shared):** what to do and why, commands with placeholders (`<host>`, `<vmid>`, `<domain>`), lessons, checklists, tools and how to use them, policies.
- **Not here (private ops notes):** which host has which port open, per-host patch status, pending items and deadlines, who has access, where each credential lives, per-client findings, scanner results. Those stay in the operator's private repository; a lesson here may say "Real case:" in one anonymized line.
- **Never anywhere in git:** secret values (see SEC-POL-5 and SEC-POL-12).

## Conventions (for people and AI assistants)
- Every doc starts with YAML front matter: `title`, `scope`, `when_to_use`, `related`.
- Rules have stable IDs (`SEC-POL-n`, `SEC-PATCH-n`, ...). Never renumber; retire a rule by marking it **Retired** with the date and the replacement.
- Each rule uses the same fields: **Rule**, **Why**, **How**, **Verify**, **Don't**.
- Commands are copy-pasteable with placeholders in `<angle brackets>`; destructive steps say so.
- When a rule changes, say what changed in the commit message.
- AI assistants: cite the rule ID you are applying; if the docs and the situation disagree, stop and ask rather than improvise.
