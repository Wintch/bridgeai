---
title: Hardening SSH, fail2ban and WAF
scope: Debian/Ubuntu servers with SSH or web exposure, nginx behind a CDN/reverse proxy, NAT/DNAT routers
when_to_use: setting up or auditing sshd and fail2ban; a fail2ban jail "is active" but attacks continue; banning scanners behind Cloudflare or another proxy; a service behind NAT sees only the router IP; adding a tarpit; a WAF alert
related: [README.md, policies.md, patching.md, firewall-and-ports.md]
---
# Hardening SSH, fail2ban and WAF

A ban is only real when the packet or request is actually refused. Most failures in this area are silent: a jail that
matches nothing, a ban that lives only in fail2ban's memory, a ban on an address the attacker does not use (a proxy),
or a log that shows the router instead of the client. Build the baseline, then prove each layer with a test from the
outside instead of trusting "active (running)".

## Quick decision table
| Situation | Do | Rule |
|---|---|---|
| New host with SSH reachable from the internet | Keys, no root, no passwords by default | SEC-HARD-1 |
| Installing fail2ban on Debian 13 | Use the known-good `jail.local` (systemd backend, iptables action) | SEC-HARD-2 |
| fail2ban says "banned" but the attacker keeps connecting | Check the kernel set, not fail2ban's list | SEC-HARD-3 |
| Auditing SSH logins or failures on a recent distro | Query the unit, not the process name `sshd` | SEC-HARD-4 |
| Scanner traffic is blocked by ModSecurity but never banned | Jail on the ModSecurity 403 lines | SEC-HARD-5 |
| Site is behind Cloudflare / any reverse proxy and bans do nothing | Ban inside nginx on the real client IP | SEC-HARD-6 |
| Adding an action or jail to a running fail2ban | Test config, restart only that jail, self-test | SEC-HARD-7 |
| Backend behind MASQUERADE/SNAT sees the router as the client | Restore the real client IP with connmark | SEC-HARD-8 |
| Want to waste scanners' time and ban them globally | Tarpit plus ipset in `raw PREROUTING` | SEC-HARD-9 |
| WordPress/PHP site needs a WAF | Mini-WAF for unambiguous patterns; CRS in detection first | SEC-HARD-10 |
| Login brute force keeps going but the jail never bans | Match path variants; add a slow jail on the same filter | SEC-HARD-11 |
| Giving a third party temporary shell access | Personal account, `Match User`, expiry | SEC-HARD-1, SEC-POL-2, SEC-POL-9 |

## Rules

### SEC-HARD-1: sshd baseline: keys, no root, passwords only per temporary user
- **Rule:** on any host whose SSH is reachable from the internet: public-key authentication, `PermitRootLogin no`, `PasswordAuthentication no` globally, and passwords enabled only for a named temporary user through a `Match User` block. Policy source: SEC-POL-1 (root) and SEC-POL-2 (keys, temporary passwords, expiry).
- **Why:** internet-facing SSH receives continuous generic guessing (thousands of attempts per day against `root`, `ubuntu`, `admin`). Keys make that noise harmless; a password account is the only door left, so it must be rare, dated and fail2ban-covered.
- **How:**
  ```bash
  # global baseline in its own drop-in (first value wins; the numeric prefix sets the order)
  sudo tee /etc/ssh/sshd_config.d/10-baseline.conf >/dev/null <<'EOF'
  PermitRootLogin no
  PasswordAuthentication no
  KbdInteractiveAuthentication no
  PubkeyAuthentication yes
  MaxAuthTries 3
  LoginGraceTime 30
  X11Forwarding no
  EOF
  # temporary password user: separate file, loaded last (see SEC-POL-2 for the account and chage steps)
  printf 'Match User <user>\n  PasswordAuthentication yes\n' | sudo tee /etc/ssh/sshd_config.d/90-<user>-password.conf
  sudo sshd -t && sudo systemctl reload ssh
  ```
  Optional: `AllowUsers <user1> <user2>` shrinks the target further; rejected users then show up as noise in the log, which is expected.
- **Verify:** test the effective config for a given user, not just the file: `sudo sshd -T -C user=<user>,host=<host>,addr=<client-ip> | grep -E '^(permitrootlogin|passwordauthentication|pubkeyauthentication)'`. Open a second session before closing the first after any change.
- **Don't:** leave `PermitRootLogin without-password` or `prohibit-password` on an internet-facing host (SEC-POL-1). Do not keep the `Match User` file after the access ends (SEC-POL-9). Do not put a `Match` block in the middle of a file that has global settings after it.

### SEC-HARD-2: fail2ban on Debian 13 needs two fixes, or it is decorative
- **Rule:** after `apt install fail2ban python3-systemd`, deploy a `jail.local` with `backend = systemd`, a journal match anchored on the unit (not the process name), and `banaction = iptables-multiport` (or install `nftables` on purpose, see Don't).
- **Why:** two independent defaults break it on Debian 13 with OpenSSH 9.8 and later:
  1. **Blind detection.** sshd splits into `sshd` and `sshd-session`; failures are logged with process name `sshd-session`. The stock filter's journal match (`_COMM=sshd`) matches almost nothing.
  2. **Virtual bans.** Debian sets `banaction = nftables`, but the `nft` binary is often not installed. fail2ban lists IPs as "banned" while no rule reaches the kernel and each ban logs `nft: not found`.
  The service still reports `active`. Hosts journal-only (no `/var/log/auth.log`) also need `backend = systemd`, which requires `python3-systemd`.
- **How:**
  ```ini
  # /etc/fail2ban/jail.local
  [DEFAULT]
  backend   = systemd
  ignoreip  = 127.0.0.1/8 ::1 <lan-cidr> <own-egress-ip>
  bantime   = 1h
  findtime  = 10m
  maxretry  = 5
  banaction = iptables-multiport

  [sshd]
  enabled      = true
  port         = ssh
  journalmatch = _SYSTEMD_UNIT=ssh.service
  ```
  Then `sudo fail2ban-client -t && sudo systemctl restart fail2ban`. Over a remote exec channel, install with `systemd-run --wait --collect` so a timeout does not kill the job (see SEC-PATCH-4).
- **Verify:** SEC-HARD-3, in full. "Active" proves nothing.
- **Don't:** rely on the packaged jail without checking both bugs. Do not `apt install nftables` on a host that manages rules with ufw or iptables-nft without reading its service unit first: the stock `nftables.service` can flush the whole ruleset at boot or reload and erase the other rules. Do not drop your own LAN and egress addresses from `ignoreip`: one typo while testing bans you from your own server.

### SEC-HARD-3: Validate a jail in three layers: filter, firewall set, outside
- **Rule:** a jail is accepted only after (1) the filter matches real log lines, (2) a manual ban creates a real rule or set entry in the kernel/proxy, and (3) a test from a genuinely outside address is refused.
- **Why:** each layer fails independently and silently (SEC-HARD-2). fail2ban only reads from its start cursor and does not reprocess history, so "Total failed: 0" right after install proves nothing either way.
- **How:**
  ```bash
  # 1. Detection against the real journal / log
  sudo fail2ban-regex --journalmatch "_SYSTEMD_UNIT=ssh.service" systemd-journal /etc/fail2ban/filter.d/sshd.conf
  sudo fail2ban-regex /var/log/nginx/<site>_error.log /etc/fail2ban/filter.d/<filter>.conf    # for file-based jails
  # 2. Action: ban a documentation address and look where the block actually lives
  sudo fail2ban-client set <jail> banip 203.0.113.66
  sudo iptables -S | grep -i f2b                  # expect a chain with a real REJECT/DROP for that address
  sudo ipset list 2>/dev/null | grep -i -A3 <set> # if the action uses an ipset
  sudo fail2ban-client set <jail> unbanip 203.0.113.66
  # 3. Outside: from another network (a VPS, a phone hotspot, a second WAN), fail on purpose and confirm the block
  ```
  A matching count of zero is a failure of layer 1; a ban visible only in `fail2ban-client status` is a failure of layer 2.
- **Verify:** `sudo fail2ban-client status <jail>` shows currently banned; the matching kernel rule has a non-zero packet counter after the outside test (`iptables -L f2b-<jail> -n -v`).
- **Don't:** use the documentation address above against a jail with the nginx action (SEC-HARD-6): its guard refuses non-global addresses, so nothing is written; use the loopback self-test there. Do not test from an address in `ignoreip` (the log says `Ignore`, nothing is banned). Do not test a proxy-fronted web jail with iptables only (SEC-HARD-6).

### SEC-HARD-4: Audit and alert scripts must read the unit, not `sshd`
- **Rule:** any script, alert or audit that reads SSH logs queries the unit (`journalctl -u ssh`) or accepts both process names (`sshd` and `sshd-session`).
- **Why:** on current Debian/Ubuntu releases `journalctl _COMM=sshd` and a regex such as `sshd\[[0-9]+\]` miss every login and failure and report "0 brute force". On Debian 13 `last` is also gone (use `wtmpdb last`), so an audit that depends on it silently shows no sessions.
- **How:**
  ```bash
  sudo journalctl -u ssh --since "7 days ago" | grep -E 'Accepted|Failed|Invalid user'
  sudo journalctl -u ssh --since "7 days ago" | grep -c 'Failed password'
  # in regexes:  sshd(-session)?\[[0-9]+\]
  ```
- **Verify:** run the script against a day with a known login (your own) and confirm it appears; a result of zero on an internet-facing host is suspicious, not reassuring.
- **Don't:** conclude "no attacks" or "no unknown logins" from a tool you have not tested against a known event.

### SEC-HARD-5: Jail on ModSecurity 403s, because `nginx-botsearch` only counts 404s
- **Rule:** when ModSecurity (anomaly-score blocking) returns 403 to scanners, add a jail on those error-log lines. The stock `nginx-botsearch` jail counts 404s for known paths and `nginx-forbidden` looks at a different message; the ModSecurity 403s fall between them and nobody gets banned.
- **How:**
  ```ini
  # /etc/fail2ban/filter.d/nginx-modsec-403.conf
  [Definition]
  failregex = \[client <HOST>\] ModSecurity: Access denied with code 403
  ignoreregex =
  datepattern = {^LN-BEG}

  # /etc/fail2ban/jail.d/nginx-modsec.conf
  [nginx-modsec]
  enabled  = true
  port     = http,https
  filter   = nginx-modsec-403
  logpath  = /var/log/nginx/<site>_error.log
  maxretry = 10
  findtime = 10m
  bantime  = 12h
  ```
  Before enabling, dry-run on the real logs (current and rotated): `sudo fail2ban-regex /var/log/nginx/<site>_error.log /etc/fail2ban/filter.d/nginx-modsec-403.conf`. Check the distinct source IPs it would ban: a few scanners and zero of your own monitoring/office addresses is the target. Then `sudo fail2ban-client -t && sudo fail2ban-client reload`.
- **Verify:** SEC-HARD-3. Remember that on a proxy-fronted site the iptables action will not cut traffic: add the nginx action (SEC-HARD-6).
- **Don't:** count 403s from your own rules (legitimate clients blocked by a rule you wrote) without the dry run. Do not set `maxretry` so low that one noisy page load by a real user bans them.

### SEC-HARD-6: Behind Cloudflare or any reverse proxy, ban in nginx, not in iptables
- **Rule:** if the server only sees the proxy's addresses at the network layer, an iptables/ipset ban of the client IP never matches. Ban at the HTTP layer, on the real client address that nginx restores, using a `geo` map and an `if` at `server` level.
- **Why:**
  - iptables sees the proxy IP; the rule exists, the counters stay at zero and the attacker keeps getting served. This also applies to `nginx-botsearch` and `nginx-limit-req` jails.
  - SSH usually reaches the host directly, so the SSH jail still works. Only the proxied ports are affected.
  - `allow`/`deny` is the obvious tool and it fails: any `location` that has its own `allow`/`deny` ignores the inherited server-level rules. A `geo` + `if ($var) { return 403; }` in the `server` block runs before location selection and cannot be bypassed that way.
- **How:**
  1. Restore the real client address first (needed for both the log and `geo`): `set_real_ip_from <proxy-range>;` for each published proxy range plus `real_ip_header CF-Connecting-IP;` (Cloudflare) or `X-Forwarded-For` (generic). Pull the ranges from the provider, never retype them:
     ```bash
     { curl -fsS https://www.cloudflare.com/ips-v4; echo; curl -fsS https://www.cloudflare.com/ips-v6; } \
       | grep -E '^[0-9a-fA-F:.]+/[0-9]+$' | sudo tee /etc/fail2ban/proxy-ranges.txt
     ```
  2. An empty map, loaded in `http` context, and the check at the top of every `server` block that serves the site (both the TLS block and the plain-HTTP redirect block):
     ```nginx
     # /etc/nginx/conf.d/f2b-banned.conf
     geo $f2b_banned { default 0; }
     # in each server { } block:
     if ($f2b_banned) { return 403; }  # f2b-nginx-deny
     ```
  3. A root helper that edits the map, validates it and reloads. It must refuse bad addresses (guards), serialize with a lock, and revert on `nginx -t` failure:
     ```bash
     #!/usr/bin/env bash
     # /usr/local/sbin/f2b-nginx-deny ban|unban|flush|list <jail> [ip]   (run as root by the fail2ban action)
     set -u
     FILE=/etc/nginx/conf.d/f2b-banned.conf
     RANGES=/etc/fail2ban/proxy-ranges.txt
     cmd=${1:-}; jail=${2:-}; ip=${3:-}
     exec 9>/run/f2b-nginx-deny.lock; flock -w 20 9 || { echo "lock timeout" >&2; exit 1; }
     [ -f "$FILE" ] || printf 'geo $f2b_banned {\n    default 0;\n}\n' >"$FILE"
     body() { grep -E '^    [0-9a-fA-F:.]+(/[0-9]+)? 1; # ' "$FILE" || true; }
     apply() {   # stdin = the new list of entries
       local new; new=$(mktemp); cat >"$new"; cp -p "$FILE" "$FILE.prev"
       { echo 'geo $f2b_banned {'; echo '    default 0;'; cat "$new"; echo '}'; } >"$FILE.tmp" && mv "$FILE.tmp" "$FILE"; rm -f "$new"
       if ! nginx -t >/dev/null 2>&1; then cp -p "$FILE.prev" "$FILE"; echo "nginx -t failed, reverted" >&2; exit 1; fi
       systemctl reload nginx; sleep 1
     }
     guard() {   # exit 0 = this address may be banned
       python3 - "$ip" "$RANGES" "${F2B_TEST:-0}" <<'PY'
     import ipaddress, sys
     ip, ranges, test = sys.argv[1:4]
     try: a = ipaddress.ip_address(ip)
     except ValueError: print("invalid IP"); sys.exit(1)
     if a.is_multicast or a.is_unspecified or a.is_link_local: print("not bannable"); sys.exit(1)
     if not a.is_global and not (test == "1" and a.is_loopback):
         print("loopback/private/CGNAT: never banned"); sys.exit(1)
     for l in open(ranges):
         l = l.strip()
         if l and a in ipaddress.ip_network(l, strict=False): print("proxy range: never banned"); sys.exit(1)
     PY
     }
     case "$cmd" in
       ban)   [ -n "$ip" ] || exit 2
              if ! msg=$(guard); then logger -t f2b-nginx-deny "ban refused $ip: $msg"; exit 0; fi
              body | grep -q -F "    $ip 1; # " && exit 0
              { body; echo "    $ip 1; # $jail $(date +%s)"; } | apply ;;
       unban) [ -n "$ip" ] || exit 2
              body | grep -v -F -- "    $ip 1; # $jail " | apply ;;
       flush) body | grep -v -F -- " 1; # $jail " | apply ;;
       list)  body ;;
       *) echo "usage: $0 ban|unban|flush|list <jail> [ip]" >&2; exit 2 ;;
     esac
     ```
     `chmod 755`, owner root. `ip_address().is_global` is false for loopback, private, CGNAT and link-local, so one test covers all of them.
  4. The fail2ban action, and wiring it next to the iptables action (keep both: iptables still serves direct, non-proxied hits):
     ```ini
     # /etc/fail2ban/action.d/nginx-deny.conf
     [Definition]
     actionstart = /usr/local/sbin/f2b-nginx-deny flush <name>
     actionstop  = /usr/local/sbin/f2b-nginx-deny flush <name>
     actioncheck =
     actionban   = /usr/local/sbin/f2b-nginx-deny ban <name> <ip>
     actionunban = /usr/local/sbin/f2b-nginx-deny unban <name> <ip>
     [Init]
     name = default

     # in the jail (SEC-HARD-5):
     action = iptables-multiport[name=nginx-modsec, port="http,https"]
              nginx-deny[name=nginx-modsec]
     ```
  5. Load it with SEC-HARD-7. Self-test from the host: ban loopback with `F2B_TEST=1`, `curl -4sk -o /dev/null -w '%{http_code}' --resolve <domain>:443:127.0.0.1 https://<domain>/` must go 200, then 403 while banned, then 200 after `unban`. Use `-4` and `--resolve`: `localhost` resolves to `::1` first and the test ban is for the IPv4 address.
- **Verify:** `sudo /usr/local/sbin/f2b-nginx-deny list x` lists the banned addresses; a banned real scanner receives 403 on its next request in the access log (`$status`), and `nginx -t` passes.
- **Don't:**
  - Never ban loopback (wp-cron and local health checks call the site from `127.0.0.1`), private or CGNAT ranges, or the proxy's own ranges: banning a proxy address bans every visitor behind it.
  - Do not use `deny <ip>;` at server level and call it done, nor `iptables` for a proxied port.
  - Do not apply to a jail that fires at volume without watching it: every ban reloads nginx. Keep `maxretry`/`findtime` conservative; a real ban storm needs a design that does not reload nginx per ban (batched map updates, or banning at the proxy through its API). This action was verified by mechanism and self-test, not under scanner volume.
- **Also decide (not a rule):** the origin may still answer directly, without the proxy, if its 80/443 are open to everyone; then the proxy's protections and your nginx deny are both bypassable by anyone who knows the origin address. Options: restrict 80/443 to the proxy's ranges, or push bans to the proxy via its API (needs a scoped token, SEC-POL-6, and a wrapper that checks the response says success: fail2ban's built-in action does not).

### SEC-HARD-7: Change a running jail safely: test, restart only that jail, self-test, keep a revert
- **Rule:** write every fail2ban/nginx change as a script with three modes: no arguments (read-only dry run), `--apply`, `--revert`. Apply validates before it reloads and reverts itself on any failure.
- **Why:** a bad jail file can take fail2ban down (SSH protection with it); and `fail2ban-client reload` alone does not add new actions to a jail that is already running, so the change looks applied and is not.
- **How:**
  ```bash
  sudo fail2ban-client -t                                  # config syntax; abort and revert if this fails
  sudo fail2ban-client reload --restart <jail>             # restarts ONLY this jail, so sshd's jail is untouched
  sudo fail2ban-client get <jail> actions                  # the new action must be listed
  sudo fail2ban-client status <jail>; sudo fail2ban-client status sshd   # both still up
  ```
  On revert, restart the jail while the helper still exists (its `actionstop` empties the map), only then delete files.
- **Verify:** the actions list contains the new action; the self-test in SEC-HARD-6 passes; `sshd` jail is still running.
- **Don't:** edit `jail.local` or the SSH jail to add a web jail; keep each jail in its own `jail.d/` file. Do not apply on a host you cannot recover without console access before arming a rollback timer (see SEC-FW-1).

### SEC-HARD-8: fail2ban is blind behind MASQUERADE/SNAT: give the backend the real client IP
- **Rule:** when a router DNATs a public port to a backend and also masquerades the connection, the backend logs the router's address for every client. Fix the path so the backend sees the real source, or ban on the router; never leave a jail running on the masked address.
- **Why:** every attacker is one address, and that address is usually inside `ignoreip` (a private-range allowance), so the jail ignores all of it; a successful login also appears to come from the router, so access audits lose the client.
- **How (preferred: real source IP, symmetric return):**
  1. Remove the `MASQUERADE` rule for that flow on the router.
  2. On the backend, mark new connections that arrive from the router and send their replies back through the router even though the backend's default gateway is different:
     ```bash
     # backend; <router-mac> is the router's MAC on the backend's interface
     iptables -t mangle -A PREROUTING -i <if> -m mac --mac-source <router-mac> -m conntrack --ctstate NEW -j CONNMARK --set-mark <mark>
     iptables -t mangle -A OUTPUT -j CONNMARK --restore-mark
     ip rule add fwmark <mark> table <table>
     ip route add default via <router-ip> dev <if> table <table>
     ```
     If the reverse-path filter drops the arriving packets (different interface), set `rp_filter` to loose on that interface. Persist all four lines (netplan routing policy, an ifupdown `post-up`, or a oneshot systemd unit) and test after a reboot; a numeric mark and `0.0.0.0/0` as the route destination are required in netplan.
  3. Arm a dead-man timer first (SEC-FW-1) and test with a real outside client.
  Alternatives: for HTTP, pass the client in `X-Forwarded-For`/PROXY protocol and restore it in nginx; for any protocol, ban on the router in `raw PREROUTING` (SEC-HARD-9).
- **Verify:** from an outside address, connect and read the backend log: the entry shows that outside address; `sudo fail2ban-client set <jail> banip <ip>` then `unbanip` shows the rule in the kernel (SEC-HARD-3).
- **Don't:** keep `ignoreip` covering the whole private space on a backend whose traffic arrives masqueraded: it silently turns the jail off. Do not mark by interface alone if other hosts (the LAN) also reach the service through the same interface.

### SEC-HARD-9: Tarpit plus a global ban list, in `raw PREROUTING`
- **Rule:** to waste scanners' time and shut them out of everything, serve a fake SSH on the public SSH port with `endlessh`, add the sources to an ipset, and drop that set in `raw PREROUTING`. Keep the real SSH reachable only by another path.
- **Why:** `raw PREROUTING` runs before DNAT and before connection tracking, so one rule covers the router itself and every forwarded service; INPUT would only see traffic for the host, and FORWARD only forwarded traffic.
- **How:**
  ```bash
  sudo apt install endlessh fail2ban ipset
  # /etc/endlessh/config: Port 2222 / Delay 10000 / MaxLineLength 32 / MaxClients 1000 / LogLevel 1 / BindFamily 4
  # BindFamily 4 is required: dual-stack logs ::ffff:<ip>, which does not fit an IPv4 hash:ip set.
  # Run it unprivileged: systemd drop-in with DynamicUser=yes, MemoryMax=128M, TasksMax=8, no capabilities.

  iptables -t nat -I PREROUTING 1 -i <wan-if> -p tcp --dport 22 -j REDIRECT --to-ports 2222
  iptables -I INPUT 1 -i <wan-if> -p tcp --dport 2222 -j ACCEPT
  iptables -t raw -I PREROUTING 1 -i <wan-if> -p tcp --dport 22 -j RETURN      # banned sources still reach the tarpit
  iptables -t raw -A PREROUTING -i <wan-if> -m set --match-set honeypot src -j DROP
  ```
  ```ini
  # /etc/fail2ban/filter.d/endlessh.conf  (no ^ anchor: fail2ban prepends host and unit to the line)
  [Definition]
  failregex = ACCEPT host=<HOST> port=\d+ fd=\d+ n=\d+/\d+$
  # /etc/fail2ban/jail.d/endlessh.local
  [endlessh]
  enabled  = true
  backend  = systemd
  journalmatch = _SYSTEMD_UNIT=endlessh.service
  filter   = endlessh
  maxretry = 1
  findtime = 1h
  bantime  = 7d
  action   = honeypot-ipset
  # /etc/fail2ban/action.d/honeypot-ipset.conf
  [Definition]
  actionstart = ipset create honeypot hash:ip timeout 604800 maxelem 262144 -exist
  actionstop  =
  actioncheck =
  actionban   = ipset add honeypot <ip> timeout <bantime> -exist
  actionunban = ipset del honeypot <ip> -exist
  ```
  Create the set at boot in the firewall script with the same `ipset create honeypot hash:ip timeout 604800 maxelem 262144 -exist` (whoever starts first creates it; both use `-exist`; the default timeout matches `bantime`). Set endlessh to `BindFamily 4`: dual-stack logs `::ffff:<ip>`, which the filter does not match; fail2ban restores bans from its database. Test the filter first: `fail2ban-regex` must match the real `ACCEPT` lines (SEC-HARD-3).
- **Verify:** `sudo fail2ban-client status endlessh`; `sudo ipset list honeypot | head`; from an outside host, `timeout 25 bash -c 'exec 3<>/dev/tcp/<public-ip>/22; cat <&3'` prints junk lines every 10 s, and later connections to other ports of the banned test address are dropped. Run this from an address that is not in `ignoreip` (otherwise the log says `Ignore` and nothing is banned), and unban it afterwards: `sudo fail2ban-client set endlessh unbanip <ip>` plus `sudo ipset del honeypot <ip>`.
- **Don't:**
  - Do not scan or probe your own tarpit port from an address you need: it is banned for the full duration (use `--exclude-ports 22` in scans, SEC-FW-7).
  - Do not leave real SSH on the tarpitted port; and keep your own egress addresses and monitoring in `ignoreip`.
  - Accepted risk, document it: a CGNAT/mobile address shared by a bot and a legitimate peer or user locks that user out for the whole ban period. Prefer a shorter ban if your service has mobile users.

### SEC-HARD-10: WAF basics: unambiguous patterns first, CRS in detection mode
- **Rule:** start with a small `map $request_uri` block that returns `444` for patterns that are never legitimate (dotfiles `.env`/`.git`/`.aws`/`.ssh`, known webshell names, path traversal) and include it in every vhost. For a full ruleset (ModSecurity + OWASP CRS) run `DetectionOnly`, measure, then switch to `On`. For PHP hosts, also set `disable_functions` and `open_basedir`. Do not repeat them here.
- **Why:** the mini-WAF has almost no false positives and removes most of the commodity scanning noise from logs; blocking CRS without measuring breaks logins, REST calls and plugins.
- **How:**
  ```nginx
  # conf.d/00-mini-waf.conf (http context)
  map $request_uri $waf_block {
      default 0;
      # dotfiles and secrets (/.env /.git/ /.aws /.ssh .env.prod .env.bak ...)
      "~*/\.(env|git|svn|aws|ssh|bak|htpasswd|htaccess)"   1;
      "~*\.env(\.|/|\?|$)"                                  1;
      # webshell names seen in real logs + well-known ones
      "~*(wp_filemanager|hellopress)"                      1;
      "~*/(wso|alfa|c99|r57|xleet|filemanager)\.php"       1;
      # path traversal (plain and encoded)
      "~*(\.\./|\.\.%2f|%2e%2e/)"                           1;
  }
  # snippets/mini-waf.conf, included in every server { }
  if ($waf_block) { return 444; }
  ```
  Back up each vhost before editing, run `nginx -t`, then verify by forcing requests through the real front door: attacks must return no response (444), legitimate pages 200.
- **Verify:** `curl -sk -o /dev/null -w '%{http_code}\n' https://<domain>/.env` shows `000` (connection closed), the homepage 200; access log counts of 444 per week are in line with background noise.
- **Don't:** block generic `.php` URLs, API paths or admin URLs in the mini-WAF; that needs context and belongs to the CRS or the application. Do not edit auto-generated vhosts by hand (the next regeneration drops the `include`): put it in the generator template.

### SEC-HARD-11: Login brute force that never trips the jail: path variants and slow rate
- **Rule:** a login jail (`wp-login.php`, `xmlrpc.php`, any login endpoint) needs two things: a filter that matches every path that reaches the endpoint, and a second **slow** jail on the same filter with a long window. The fast jail stops bursts; the slow jail stops attackers that pace themselves under its threshold.
- **Why:** both evasions are cheap and common, and neither shows up as an error:
  1. **Path variants.** A filter anchored on `"POST /wp-login\.php` misses `POST //wp-login.php` (the web server normalizes the double slash and serves the login anyway) and installs in a subdirectory (`/blog/wp-login.php`). The attacker gets unlimited attempts while the jail reports a normal, low count.
  2. **Slow rate.** One attempt every few minutes never reaches `maxretry = 8` in `findtime = 10m`, yet adds up to hundreds of guesses a day per address.
- **How:**
  ```ini
  # /etc/fail2ban/filter.d/wp-login.conf  (same idea for xmlrpc.php)
  [Definition]
  failregex = ^<HOST> \S+ \S+ \[\] "POST /+(?:\S*/)?wp-login\.php\S*(?:\s+HTTP/\d\.\S+)?" \d+
  ignoreregex =

  # /etc/fail2ban/jail.d/wordpress-slow.conf  (keep the existing fast [wp-login] jail as is)
  [wp-login-slow]
  enabled  = true
  filter   = wp-login
  port     = http,https
  logpath  = /var/log/apache2/*access*.log
  backend  = polling
  findtime = 12h
  maxretry = 20
  bantime  = 24h
  ```
  Before enabling, compare old and new filters on the real logs (`fail2ban-regex <log> <filter>`: the new one must match at least as many lines), and dry-run the slow threshold: count, per source address, the most POSTs in any 12-hour window over the current and rotated logs. The addresses at or above 20 should all be scanners; none of your own, your developers' or your monitoring's. Then `sudo fail2ban-client -t` and reload (SEC-HARD-7).
- **Verify:** `sudo fail2ban-client status wp-login-slow` lists the slow attacker; its address shows in `iptables -S f2b-wp-login-slow` (SEC-HARD-3); the login page still answers 200 from a normal address.
- **Don't:** lower the fast jail's `maxretry` to catch slow attackers: that bans real users who mistype twice in a row. Do not count only failed logins if the log cannot tell them apart from successful ones; with a plain access log every POST counts, so pick a slow threshold well above what a real user does in half a day (20 in 12 hours left every human user out in the dry run). Keep your own egress addresses in `ignoreip`. Behind a proxy, ban in the proxy (SEC-HARD-6).

## Checklist
- [ ] `sshd -T -C user=<user>,host=<host>,addr=<ip>` shows no root login and no passwords, except documented `Match User` accounts with an expiry (SEC-HARD-1).
- [ ] fail2ban uses `backend = systemd`, the unit-anchored journal match, and a ban action whose binary exists (SEC-HARD-2).
- [ ] `fail2ban-regex` matches real log lines; a manual ban shows in the kernel set; an outside test address is refused (SEC-HARD-3).
- [ ] Audit scripts handle `sshd-session` and were tested against a known login (SEC-HARD-4).
- [ ] ModSecurity 403s feed a jail; dry run showed only scanners (SEC-HARD-5).
- [ ] Proxy-fronted sites ban in nginx with guards for loopback, private and proxy ranges; real IP restored (SEC-HARD-6).
- [ ] Jail changes were applied with `-t`, `reload --restart <jail>`, a self-test and a revert (SEC-HARD-7).
- [ ] No backend logs only the router address; `ignoreip` does not blind a masqueraded service (SEC-HARD-8).
- [ ] Tarpit and ipset ban documented with the CGNAT risk and your own addresses exempt (SEC-HARD-9).
- [ ] WAF in detection mode before blocking; mini-WAF included in every vhost (SEC-HARD-10).
- [ ] Login filters match `//` and subdirectory paths; a slow jail (long `findtime`) backs up the fast one, dry-run first (SEC-HARD-11).
- [ ] Credentials and temporary access follow SEC-POL-1, SEC-POL-2, SEC-POL-9; firewall changes follow SEC-FW-1.
