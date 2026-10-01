---
name: network-diagnostics
description: "Diagnose network issues closest-to-home-first: NIC -> gateway -> LAN -> ISP -> remote service. Based on the operator's own published methodology."
version: 1.0.0
author: operator (adapted from Wintch/network_check_guide, MIT)
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [networking, diagnostics, troubleshooting, sysadmin, dns, latency]
    related_skills: [systematic-debugging]
---

# Network Diagnostics

## Overview

Full methodology published at https://github.com/Wintch/network_check_guide
(MIT licensed, written by the operator of this infrastructure). This skill is
a condensed, actionable version for quick use -- read the full repo for the
13-document deep reference, the symptom-triage table, and the bundled
scripts (quick_check.py, setup_encrypted_dns.sh) when a quick check is not
enough.

**Core principle:** always diagnose closest to home first, in this order:

```
your NIC/interface -> first-hop gateway -> local LAN infra -> ISP -> remote API/service
```

Do not blame a remote service (an API, a website, an upstream provider)
before ruling out every step closer to home. Most "the internet is broken"
reports turn out to be local: a flaky NIC, a watchdog script resetting a
link, a saturated queue, a stale DNS cache -- not the ISP and not the remote
side. (Real precedent: a local watchdog script caused repeated 8-9s outages
every ~35s for 25 days, initially misdiagnosed as ISP throttling.)

## When to use

Any time something is reported as "slow", "down", "can't connect", or
"times out" -- before proposing a fix, before blaming an external service,
and before escalating. Also use proactively before starting latency-
sensitive work (a long AI session, a call, a stream) to rule out a bad
starting state.

## Required tools

This skill needs real binaries on PATH. If any are missing, say so plainly
instead of guessing results -- do not fabricate diagnostic output.

- `ping`, `traceroute` -- iputils-ping, traceroute (apt)
- `dig` -- dnsutils (apt)
- `mtr` -- mtr-tiny (apt)
- `nmap` -- nmap (apt)
- `tcpdump` -- tcpdump (apt)
- `ssh` -- openssh-client (apt)
- `curl` -- already present

## Quick check procedure (closest-to-home-first)

1. **Interface/NIC**: link up? correct speed/duplex negotiated? any recent
   driver resets in dmesg/journalctl?
2. **First-hop gateway**: `ping` the default gateway. Expect <1-2ms on a
   healthy LAN. Any loss or spikes here means the problem is local, full
   stop -- do not go further out yet.
3. **Local LAN infra**: switches, other routers/VMs in the path. Check for
   anything periodic (a cron job, a watchdog, a scheduled backup) that could
   explain intermittent drops at a fixed interval.
4. **DNS**: `dig <domain>` against the configured resolver AND against a
   known-good public resolver (e.g. 1.1.1.1) to isolate resolver-specific
   issues (stale cache, negative caching after a fix, local resolver down).
5. **ISP / WAN**: `mtr` or `traceroute` out to a stable, well-known
   destination (not the actual service you care about, to avoid confusing
   its own issues with path issues).
6. **Remote service**: only now test the actual API/site/service directly
   (`curl -v`, check its own status page, check for its own rate limits).

## Symptom triage (condensed -- see full repo for the complete table)

- Periodic short outages at a fixed interval -> suspect a local
  watchdog/cron, not the ISP (see the Real Case Study in the full repo).
- "Works on WiFi, fails on wired" or vice versa -> isolate to a specific
  physical path/NIC before touching anything upstream.
- Sudden latency increase to *everything* at once, including the gateway ->
  local; sudden latency to *one* remote service only -> probably on their
  end, verify with their own status page before assuming so.
- DNS resolves to a stale/wrong IP right after a known change -> check
  negative/positive cache TTLs before assuming the record itself is wrong.

## What this skill does NOT grant

This skill describes a methodology and expects the tools above to be
available on the machine actually running the check. It does **not** imply
SSH/login access to any specific host in the operator's infrastructure --
that is a separate, explicitly-granted permission. If asked to diagnose a
remote host and no credentials/reachability exist for it, say so instead of
attempting a workaround.

## One explicit exception: `iashur`

`ssh iashur` works (SSH config alias, set up by `start_hermes.sh` from a
dedicated read-only-mounted key -- see `docker-compose.yml`). This is a
physical VR-lab machine (`iam@192.168.1.171`, Debian 13), explicitly
granted 2026-10-01 for exactly this skill's use. The key is scoped to that
one host only and carries `no-port-forwarding,no-X11-forwarding,
no-agent-forwarding` on the `iashur`-side `authorized_keys` entry; the
`iam` user itself has no sudo, so this cannot be used to make system-level
changes on that host, only ordinary-user diagnostics (`ping`, `ip`,
`uptime`, `df`, reading logs the `iam` user can read, etc.). No other host
in the infrastructure is reachable this way -- do not assume this pattern
extends anywhere else without the operator saying so explicitly.
