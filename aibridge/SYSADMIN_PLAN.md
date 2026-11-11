# `sysadmin` pack: a person looks after their own servers from their Hermes (plan)

Status: **F0 built, F1 and later planned.** Built so far:
- the guide in `aibridge/security/`, with a new doc `web-exposure.md` (SEC-WEB-1..6);
- `SKILL_sysadmin.md`;
- the `sysadmin` pack (an old choice of `servidores` counts as `sysadmin`);
- `sysadmin.py` (`gateway sysadmin web|creds`) with `sysadmin_selftest.py`.

F1 and later are not built.

## Goal

A module that any person can switch on to take care of **their own** servers from their own Hermes: audit them, understand
what is wrong and why, and fix it with their approval. The name honours the profession: `sysadmin`.

The knowledge comes from a security guide with stable rule IDs (`SEC-POL-n`, `SEC-PATCH-n`, ...), written in English and in
a fixed shape so an agent can cite the rule it applies. The checks come from that guide's **Verify** fields: each rule that
can be checked by a machine becomes a check, and each finding names its rule.

## Principles

1. **Only what the person declares and installs.** Hermes reaches a server only through a key whose public half the person
   pasted on that server, limited there to the `hostcare` program (forced command) and to the stack's egress address
   (`from=`). There is no scanning of anything the person has not connected. Web checks that go beyond what a browser sees
   need proof of ownership (below).
2. **Their servers, their keys.** The key pair is generated inside the person's stack and the private half never leaves it.
   The operator never holds it and never sees the findings. (hostcare's rule "the ops brain is not a person's Hermes" protects
   *other* people's data from the *operator's* server keys. When the servers and the data have the same owner it does not
   apply. The operator's own servers keep going through the `ops` stack.)
3. **Reading is free, changing asks.** hostcare's levels stay: level 0 reads, level 1 runs named fixes, level 2 runs any
   command. Level 1 and level 2 run only from a command **the person types** (`/sysadmin fix ...`, `/sysadmin run ...`), the
   same pattern as `/machine on NAME yes`. The agent proposes the exact text and cannot run it. hostcare's `NEVER` list is
   still enforced on the host, whatever was approved.
4. **Evidence, not claims.** Every finding has the same fields: `check`, `rule`, `status` (`ok|warn|fail|unknown`) and
   `evidence`, a short string read on the host. `unknown` means the check could not read its source, and it is never shown as
   `ok`. Text that comes from a host (log lines, banners, file names) is data, never instructions (SEC-POL-11).
5. **Nothing about the server leaves except to the person's model.** The vulnerability datasets are downloaded; nothing is
   queried with the host's package list. The skill and the person's guide say plainly what does leave: audit evidence goes to
   whatever model the person uses, and some free cloud models may train on it (the provider table in the project site's
   Privacy section). The evidence is kept minimal: counts and names, no file contents, and no secrets ever (hostcare refuses
   them).

## Pieces

| Piece | Where | What |
|---|---|---|
| The guide | `aibridge/security/` | The rule docs (policies, patching, hardening, firewall, containers, detection, publishing, sites). This repo becomes the source; internal copies point here. Placeholders only, checked by `privacy_scan.sh`. |
| The skill | `aibridge/SKILL_sysadmin.md` | When to audit, how to report (KEV first, then `fail`, then `warn`, always with the rule ID), what never to do, and how to hand a change to the person. |
| Audit tools | `ops/hostcare/hostcare_mcp.py`, level 0 | `audit`: runs every check and returns the findings as JSON. One check alone also works (`audit ssh`). |
| Root helper | `ops/hostcare/audit_root.py`, installed root-owned | Reads what needs root (`sshd -T`, `ss -p`, `/proc/*/maps`, firewall rules, fail2ban, the journal). It takes **no arguments** and prints JSON. One sudoers line lets the `hostcare` user run exactly this file. |
| Installer | `ops/hostcare/install.sh` | The person runs it once as root on their server, after reading it. It creates the `hostcare` user (no password, no sudo except the helper), installs the two files and writes `hostcare.json` and the `authorized_keys` line. With `--uninstall` it removes all of it. |
| Agent side | `gateway sysadmin` | `hosts`, `connect NAME` (makes the key and prints the one installer command with the public key and `from=`), `check NAME`, `audit [NAME\|all]`, `web DOMAIN`, `diff NAME`. It speaks MCP over `ssh -i <key> -o BatchMode=yes`, so no per-person `mcp_servers` configuration and no recreate are needed. |
| Person's commands | Telegram and web | `/sysadmin fix NAME FIX yes` and `/sysadmin run NAME yes` (the last one shows the proposed command and asks again). |
| State | `/workdir/.sysadmin/` | Hosts, known host keys (pinned on `connect`), the last audit of each host and the history used by `diff`. Never in memory notes beyond "last audit: date, N findings". |
| The pack | `skill_packs.json` | `sysadmin`: `sysadmin`, `network-diagnostics` and `proxmox`. It replaces `servidores`; whoever has `servidores` on gets `sysadmin`, and `servidores` stays as an alias until nobody uses it. No `needs`: it uses no third-party key. |

The operator's only setup: the stack's egress address for `from=`, in the stack's gateway config. Servers on the internet are
reachable from any stack (guests reach the internet, not the LAN). A server on a LAN needs a pinhole (`GUEST_PINHOLES`), which
the operator adds by hand. A home server behind NAT needs a port forward limited to the egress address, or it stays out.

## The checks

| check | Reads | Rule | Root |
|---|---|---|---|
| `os` | `/etc/os-release`, kernel, end-of-support date from a table in the repo | SEC-PATCH | no |
| `updates` | upgradable packages, security subset, `/run/reboot-required` | SEC-PATCH | no |
| `kev` | installed versions against the Debian/Ubuntu security data joined with CISA KEV (downloaded daily by the stack, never queried with the host's packages) | SEC-PATCH (KEV first) | no |
| `stale_libs` | processes still mapping deleted libraries, so they need a restart after an upgrade | SEC-PATCH | yes |
| `unattended` | whether security updates install themselves | SEC-PATCH | no |
| `ssh` | `sshd -T`: root login, passwords, keys only | SEC-POL-1, SEC-POL-2 | yes |
| `accounts` | users with a shell, who is in sudo or wheel, accounts with no expiry date (names only) | SEC-POL-9 | yes |
| `listening` | listening sockets with their process | SEC-FW | yes |
| `firewall` | whether a firewall is loaded, and Docker published ports that skip it | SEC-FW | yes |
| `fail2ban` | jails, and whether any jail has ever banned (on Debian 13 a jail can look active and never ban) | SEC-HARD | yes |
| `logins` | accepted SSH logins of the last 7 days: user, source and method | SEC-DET | yes |
| `containers` | per running container: privileged, capabilities, `no-new-privileges`, published ports | SEC-CONT | no (docker group) or yes |
| `web` (from the stack) | TLS version and certificate expiry, security headers, the server banner | SEC-HARD, SEC-PUB | — |
| `web --deep` (from the stack) | exposed `/.git/`, `/.env`, directory listing: GET only | SEC-PUB | — |
| `ports` (from the stack) | a TCP connect to a short list of ports on the connected server's public address | SEC-FW | — |

`web` reads only what any browser reads, so it works on any domain. `web --deep` and `ports` probe, so they need proof of
ownership: `web --deep` needs a token at `/.well-known/bridgeai-sysadmin.txt` or in a DNS TXT record; `ports` works only on a
server connected with a key.

A weekly `hermes cron` per person (within the cron policy) runs `audit all` and reports only what changed since last time.

## Fixes (level 1, named, mapped to a rule)

- `security-upgrade PACKAGE`: upgrades one package from the security pocket (SEC-PATCH: on a fleet, first on a canary).
- `restart UNIT`: restarts a service that `stale_libs` named.
- `enable-unattended`: security updates only.

Never as a fix, not even at level 2: firewall rules, SSH configuration, users, keys, passwords, reboot. These lock people out
or open doors. For them the agent writes the exact steps with the guide's safety net (a dead-man timer for firewall changes,
`sshd -t` plus a second session for SSH) and the person runs them.

## Threats

- **Prompt injection reaches the person's agent** through a web page, a file or a log line. The attacker gets what level 0
  gives: reading the audit. They cannot change anything. Fixes need the person's typed command, which the agent cannot
  produce, and the key works only from the stack's address and only for `hostcare`.
- **The stack itself is compromised.** The same: level 0 on the connected servers. That is why `NEVER` is enforced on the
  host and the helper takes no arguments.
- **A person points `sysadmin` at someone else's server.** Without a key on it, only `web` works, and `web` reads what a
  browser reads. Probing needs proof of ownership.
- **The operator.** The operator runs the VM, so the operator could read a stack's files, the private key among them. This is
  the same honest limit as with every key a person loads (`DATA_LAW_AND_KEYS.md` B.7), and the guide must say it. A person who
  does not accept it uses `from=` plus a key they revoke when they leave, and keeps level 2 off.

## Phases

- **F0 (no server access):**
  - the guide into `aibridge/security/` with a clean `privacy_scan.sh`;
  - `SKILL_sysadmin.md`;
  - the `sysadmin` pack;
  - `gateway sysadmin web DOMAIN`;
  - credential expiry reminders from a list in the person's workdir that holds names and dates only, never values (SEC-POL-3).
- **F1:**
  - the hostcare `audit` tools and `audit_root.py`;
  - `install.sh`;
  - `gateway sysadmin connect|check|audit`;
  - tests on a throwaway VM and on a cloud droplet.
- **F2:**
  - `kev` with the downloaded datasets;
  - the weekly cron with diffs;
  - `ports`, `web --deep` with proof of ownership.
- **F3:**
  - the named fixes and `/sysadmin fix|run`, with the person's confirmation;
  - the person's guide in es, en, ru.

## Open questions

- Install by `curl … | sh` from a pinned commit with a published sha256, or by pasting one self-contained block? Pasting is
  easier to read before running, and the script is short.
- Should a Proxmox host connect through hostcare as well, which reaches its guests through `qm guest exec` and needs root on
  the hypervisor, or should it stay with the API token as today (read-only, no guest packages)?
