---
title: Firewall changes and exposed-port reviews
scope: Linux hosts, edge/NAT boxes and Docker hosts; reviewing what is reachable from the internet
when_to_use: before changing any firewall or routing rule on a remote machine; publishing a container port; reviewing exposed ports; a scan result looks wrong; a network outage needs recovery
related: [README.md, policies.md, patching.md, hardening-ssh-fail2ban-waf.md]
---
# Firewall changes and exposed-port reviews

Firewall mistakes on a remote router cut the service you need to fix them, and port reviews are easy to get wrong
because your own network lies to you. Arm a rollback before every change, load rules atomically, test with new
connections from outside, and review exposure from a genuinely external vantage point.

## Quick decision table
| Situation | Do | Rule |
|---|---|---|
| About to change firewall/routing on a remote machine | Save rules, arm an auto-rollback timer, then change | SEC-FW-1 |
| Change applied, need to decide it works | Real canaries, new connections, from each direction | SEC-FW-2 |
| Rewriting a chain with many rules | One `iptables-restore --noflush` of the whole chain, validated first | SEC-FW-3 |
| Container publishes a port with `-p` | Filter in `DOCKER-USER`; bind to a specific address | SEC-FW-4 |
| "Which ports are open to the internet?" | Scan from another network or host, never from inside | SEC-FW-7 |
| Scan shows refused, timeout or filtered | Read it correctly; a web fetcher is not a probe | SEC-FW-8 |
| Finished a port review | Write the inventory in the private notes | SEC-FW-12 |

## Rules

### SEC-FW-1: Arm a dead-man switch before any firewall or routing change
- **Rule:** before changing firewall, NAT, routes or interface settings on a machine you reach remotely, save the current state and start a timer that restores it unless you cancel. If you lose the connection, the machine heals itself.
- **Why:** diagnosing a broken router under pressure is the worst moment to do it, and the router often is the path you need. A timer that restores the rules by itself turns an outage into one log line. Use it on anything that carries live service: routers, edge boxes, hypervisors, hosts that forward traffic. Single low-impact hosts do not need it.
- **How:**
  ```bash
  install -d -m 700 /root/fw-backups
  iptables-save  > /root/fw-backups/pre-<change>.v4
  ip6tables-save > /root/fw-backups/pre-<change>.v6
  rm -f /root/fw-backups/CANCEL-<change>
  systemd-run --unit=fw-rollback --on-active=180s bash -c '
    if [ -f /root/fw-backups/CANCEL-<change> ]; then echo cancelled
    else iptables-restore < /root/fw-backups/pre-<change>.v4; ip6tables-restore < /root/fw-backups/pre-<change>.v6; fi'
  # ... apply the change, run the canaries (SEC-FW-2) ...
  touch /root/fw-backups/CANCEL-<change> && systemctl stop fw-rollback.timer     # only when it is verified
  ```
  The same pattern works for routing: the timer restores the previous default route (`ip route replace default via <old-gateway> dev <if>`). Pick the delay longer than your slowest check and shorter than a human could tolerate the outage; re-arm if you need more time. A persistent change (boot script, config file) is made only after you cancel.
- **Verify:** `systemctl list-timers fw-rollback.timer` shows the timer before you start; after cancelling, the timer is gone and the change survives a re-read of the rules.
- **Don't:** apply first and "arm later". Do not cancel on a ping: use canaries (SEC-FW-2). Do not forget that a timer restores everything including unrelated changes made meanwhile (stop other work during the window).

### SEC-FW-2: Judge a change with real canaries and NEW connections
- **Rule:** before cancelling the timer, test with hosts and ports you have just confirmed are alive, from every direction that matters (outside to inside, inside to outside, inside to inside across the router), and with connections opened after the change.
- **Why:** established connections survive a bad rule through conntrack (`ESTABLISHED,RELATED` accepted early), so an existing SSH session looks fine while every new peer is blocked. A canary that is itself dead (a powered-off machine's port, a retired service) produces a false alarm and tempts you to cancel the safety net.
- **How:**
  ```bash
  # list canaries beforehand, each with a one-line proof it is alive today
  nc -z -w3 <canary-host> <canary-port> && echo up          # from the same side the real clients use
  curl -sS -o /dev/null -w '%{http_code}\n' https://<public-name>/   # from an external vantage (SEC-FW-7)
  ```
  Include at least: one inbound published service tested from outside, one outbound flow from an internal host (internet access), one flow between two internal segments through the router, and the management path you are using right now (opened as a new session).
- **Verify:** every canary answers as before; counters of the new rules increase (`iptables -L <chain> -n -v`).
- **Don't:** keep working over the session you are testing. Do not pick canaries from memory.

### SEC-FW-3: Load rules atomically and validate the input first
- **Rule:** build the complete content of a chain, check every parameter, then load it in one `iptables-restore --noflush` that begins with `:<CHAIN> - [0:0]`. Never flush a chain and then append rule by rule.
- **Why:** with `--noflush`, declaring the chain empties only that chain and the new rules replace the old in a single commit: there is no instant with an empty (wide-open) chain, and a failed load leaves the previous rules untouched. A typo found halfway through an append loop leaves the chain half built.
- **How:**
  ```bash
  # 1. validate parameters from your config BEFORE touching iptables (addresses, ports, ranges); exit non-zero on the first bad entry
  # 2. build all the lines
  RULES=( "*filter" ":<CHAIN> - [0:0]"
          "-A <CHAIN> -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN"
          "-A <CHAIN> -s <trusted-cidr> -j RETURN"
          "-A <CHAIN> -j DROP" "COMMIT" )
  printf '%s\n' "${RULES[@]}" > /tmp/rules.$$
  iptables-restore --test --noflush < /tmp/rules.$$    # parse only; nothing is changed
  iptables-restore --noflush < /tmp/rules.$$           # commit
  ```
  Keep site-specific values (subnets, hosts, ports) in a root-owned file read by the script (`/etc/default/<name>`), refuse to run if it is missing, and run the script from a boot unit ordered after the service that creates the chain.
- **Verify:** `iptables -S <CHAIN>` shows the intended list; re-running the script produces the same result (idempotent).
- **Don't:** use `iptables -F <CHAIN>` followed by `-A` lines in a script. Do not run it without the dead-man switch on a remote machine (SEC-FW-1).

### SEC-FW-4: Docker published ports bypass ufw and INPUT: use DOCKER-USER
- **Rule:** a container started with `-p` (or `ports:` in compose) is reachable from every network that can reach the host, whatever ufw says. Filter in the `DOCKER-USER` chain, and bind published ports to the one address that needs them.
- **Why:** Docker publishes through DNAT, so the traffic takes the `FORWARD` path through `DOCKER-USER` and never touches `INPUT`, where ufw rules live. Without an explicit rule, every `-p` is open to the whole network or internet.
- **How:**
  ```bash
  # bind to a specific address: reachable only there
  docker run -p 127.0.0.1:<host-port>:<container-port> <image>
  # ports <lan-ip>:<host-port>:<container-port> in compose
  ```
  Chain content (loaded as in SEC-FW-3; the first two lines are mandatory):
  ```
  -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  -A DOCKER-USER -i lo -j RETURN
  -A DOCKER-USER -s <docker-bridge-subnet> -j RETURN        # one line per container network: their own egress and inter-network traffic
  -A DOCKER-USER -s <trusted-cidr> -j RETURN
  -A DOCKER-USER -s <proxy-or-edge-ip> -j RETURN
  -A DOCKER-USER -j DROP
  ```
  Replies from a published container leave with the bridge's own address, not the LAN's, so the `ESTABLISHED,RELATED` rule comes first or the return traffic is dropped. If a rule must match the original public port, remember that DNAT has already rewritten the destination: match with `-m conntrack --ctorigdstport <port>`. For containers that must reach the internet but not your network, add `-s <guest-subnet> -d <private-range> -j DROP` for each private range before a final `-s <guest-subnet> -j RETURN`, and allow exceptions as separate, commented pinholes placed above those drops (first match wins). Guests also reach the host through `INPUT`: accept `ESTABLISHED,RELATED` first, then drop the guest subnet.
- **Verify:** `ss -ltnp` shows which address each port binds to; `iptables -S DOCKER-USER`; test from an untrusted address that the published port times out (SEC-FW-7).
- **Don't:** assume `ufw deny <port>` protects a published container. Do not publish a database port `0.0.0.0` "just for a moment". Do not forget the egress rule: a new compose project gets the next free subnet, which no existing rule allows, so its outbound traffic is silently dropped until you add it.

### SEC-FW-5: Retired
- **Retired:** router and hypervisor material that is not part of bridgeai. The ID stays reserved.

### SEC-FW-6: Retired
- **Retired:** router and hypervisor material that is not part of bridgeai. The ID stays reserved.

### SEC-FW-7: Review exposed ports from a genuinely external vantage point
- **Rule:** to learn what the internet can reach, scan your public address from a network that is not yours: a VPS in another provider, a second uplink through a network namespace, or a phone hotspot. Probing your own public address from a machine that owns it, or from inside, tells you nothing.
- **Why:**
  - The kernel recognizes its own addresses and answers them via the local route (round-trip around 0.02 ms): the packet never leaves the host, even if you bind another interface or add policy routing. It is not the same as the hairpin NAT problem, which is about a router reflecting traffic; this is the host short-circuiting.
  - From the LAN, hairpin/reflection rules can mask or invent results.
  - One vantage point cannot tell "blocked by country" from "filtered from some networks".
- **How:** from a VPS: `nmap -Pn -sS -p- --max-rate 300 --exclude-ports 22 <public-ip>`; IPv6 separately: `nmap -6 -Pn -p 22,80,443 <ipv6-address>`; UDP only for known ports (`-sU -p <list>`), it is slow and ambiguous. For a second uplink, a temporary namespace (skeleton, adapt names):
  ```bash
  ip netns add ext
  ip link add veth-ext type veth peer name veth-ext-br
  ip link set veth-ext-br master <other-uplink-bridge> up
  ip link set veth-ext netns ext
  ip netns exec ext ip addr add <free-address>/<prefix> dev veth-ext
  ip netns exec ext ip link set veth-ext up; ip netns exec ext ip link set lo up
  ip netns exec ext ip route add default via <other-uplink-gateway>
  systemd-run --on-active=25min bash -c 'ip netns del ext; ip link del veth-ext-br 2>/dev/null'   # cleanup even if you forget
  ip netns exec ext nmap -Pn -sS -p- --max-rate 600 --exclude-ports 22 <target-public-ip>
  ```
  Remove the namespace manually when done.
- **Verify:** the scan result agrees with the rules (SEC-FW-8); a sanity check that the scan really left the host: the first hop on `traceroute` is not loopback, and the latency is not tenths of a millisecond.
- **Don't:** scan your own tarpit or honeypot port: it bans your scanner for the ban duration (`--exclude-ports`). Do not scan hosts you do not own. Do not run a heavy scan at full rate over a home uplink with a data cap or a fragile NAT table.

### SEC-FW-8: Read probe results correctly
- **Rule:** interpret the result by type before concluding anything.
- **Why:**
  - **Refused (RST, `ECONNREFUSED`)** means something actively answered: a host that is up with no listener, or a service that rejects. **Timeout / filtered** means packets were dropped, which is what a filter does. The two are opposite diagnoses. A "country filter" hypothesis was refuted because refused connections cannot come from a source-address drop; the real cause was a stale DNS record pointing at an address now owned by someone else, whose router replied with RST.
  - A web-fetch tool (an assistant's "fetch URL", a link checker) has its own policies and caches; its success or failure says nothing about ports and nothing about who can reach you.
  - Monitors that probe from one network (one country) will report green even if a real filter exists for others.
  - "Filtered" on a port with a forwarding rule usually means the destination does not answer (host off), not that the rule is absent.
- **How:** compare the scan with the live rules in both directions (open in the scan but no rule; rule present but closed or filtered); check packet counters (`iptables -t nat -L PREROUTING -n -v`); check DNS (`dig +short <name>`) before blaming the network; try a second vantage point before claiming a geographic effect.
- **Verify:** each discrepancy has an explanation written down (stale record, dead host, upstream device, rule missing).
- **Don't:** call it a geo-block from one failed vantage point. Do not use a fetch tool as a port probe.

### SEC-FW-9: Retired
- **Retired:** router and hypervisor material that is not part of bridgeai. The ID stays reserved.

### SEC-FW-10: Retired
- **Retired:** router and hypervisor material that is not part of bridgeai. The ID stays reserved.

### SEC-FW-11: Retired
- **Retired:** router and hypervisor material that is not part of bridgeai. The ID stays reserved.

### SEC-FW-12: Keep a written port inventory, in the private notes
- **Rule:** maintain, per uplink and per router, a table of every published port: port, destination, purpose, authentication, evidence of use (counters), last scan date, verdict (justified / restrict / close). Review it after every change and at least quarterly.
- **Why:** without a baseline you cannot tell a new exposure from an old one, and "drift" (a port that appeared, a documented port that vanished) is the early signal you want. Which port is open on which host is operational detail that does not belong in the shared repository (see the README).
- **How:** generate it from the live rules plus a scan (SEC-FW-7), compare with the previous inventory, and record each difference. Store it in the private operations repository.
- **Verify:** the last comparison shows no unexplained difference.
- **Don't:** put the inventory, addresses or host names in this shared repository; keep only the method here.

## Port review checklist
- [ ] Scan from an external vantage point (VPS or second uplink namespace), not from a host that owns the address (SEC-FW-7).
- [ ] Exclude tarpit/honeypot ports from the scan (SEC-FW-7).
- [ ] Compare scan and rules in both directions; explain each difference (SEC-FW-8).
- [ ] Check every published container port is bound and filtered in `DOCKER-USER` (SEC-FW-4).
- [ ] Any change: dead-man switch armed, atomic load, canaries tested with new connections, timer cancelled, then persisted (SEC-FW-1 to SEC-FW-3).
- [ ] Update the private port inventory; note the date and what changed (SEC-FW-12).
- [ ] Related controls: fail2ban and tarpit validation in the hardening doc (SEC-HARD-3, SEC-HARD-9); secrets on guest disks (SEC-POL-5, SEC-POL-10).
