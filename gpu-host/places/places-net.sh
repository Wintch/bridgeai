#!/bin/bash
# What a desktop place may reach, and the LAN addresses it is published on (run as root on the GPU host).
#   places-net.sh up|down|print|status
# Site values live in /etc/default/bridgeai-places (root-owned, not in git):
#   PLACE_IPS=(192.168.x.172 192.168.x.173)   extra addresses of THIS host's LAN interface, one per place (place.py create/recreate --bind ADDRESS)
#   PLACE_GAME_UDP=(27960)                    UDP ports one place may reach on another place, so two people can play a LAN game against each other (the one that hosts
#                                             publishes the port on its address with place.py --udp 27960; the other connects to THAT address). Nothing else between places.
#   PLACE_NEW_PER_MIN=30                      new TCP connections per minute one PUBLIC address may open to a place's web ports (a place the router forwards to the
#                                             internet): more are dropped, so a password cannot be guessed at speed. Addresses of the LAN are not limited.
#   PLACE_GAME_SERVERS=(192.168.x.64:27960)   game servers OUTSIDE the places (a dedicated server on another LAN machine): every place may send UDP to exactly that
#                                             address and port (answers come back as part of the same flow) and nothing else of that machine. Private addresses only.
#   PLACE_WAN_IPS=(203.0.113.7)               the home's PUBLIC addresses (every internet line): a place must not reach the router through them either (a packet to the
#                                             router's own public address is answered by the router like LAN traffic, and its port forwards hairpin back
#                                             to the LAN). Dropped like the LAN. A line with a changing address needs this kept current.
#   PLACE_SUNSHINE_BASES=(49989)              the base port of each place's Moonlight stream (place.py --sunshine BASE): its TCP ports (BASE-5, BASE, BASE+21) get the
#                                             same limit on new connections from public addresses as the web ports
#   PLACE_IFACE=                              the LAN interface; by default the one that carries the default route (a NIC can be renumbered by the kernel)
#   PLACES_ROOT=/srv/bridgeai/places          where place.py keeps the places: each one found there gets its own rules, named after it (below)
# `up` adds those addresses (idempotent, announced on the LAN) and loads the nft table `bridgeai_places`; `down` removes both; `print` shows the ruleset.
#
# The rule: a place reaches the INTERNET and nothing else. Its traffic towards any private, link-local or carrier-grade range is dropped in the forward path
# (so not the router, not the other place, not the host's other containers, not another PC), except answers to connections the LAN opened to its published
# port (conntrack: established, related). The host's own input chain already drops what a container sends to the host itself.
# Why: a place runs a browser and whatever its person installs; it must not see the media host, the GPU gate, the router or another person's place.
#
# Per place: place.py names a place's container, hostname AND its network interface on the host NAMEdoc, so every place found in PLACES_ROOT gets its own
# rules on that interface, each with a counter and a comment "NAMEdoc: ...": traffic in and out, connections from the internet dropped by the rate limit, and
# attempts to reach the LAN. `nft list table inet bridgeai_places` then tells each place apart. The rules for the whole pool stay after them as the net for
# a place on an older network (an interface named br-...), so nothing depends on the names being right.
set -euo pipefail
CONF=${PLACES_NET_CONF:-/etc/default/bridgeai-places}
IP=${IP:-ip}; NFT=${NFT:-nft}
POOL=172.30.0.0/16                               # place.py: one /24 per place
PLACE_IPS=(); PLACE_IFACE=""; PLACE_GAME_UDP=(); PLACE_GAME_SERVERS=(); PLACE_WAN_IPS=(); PLACE_NEW_PER_MIN=30; PLACE_SUNSHINE_BASES=(); PLACES_ROOT=${PLACES_ROOT:-/srv/bridgeai/places}
[ -f "$CONF" ] && . "$CONF"
PRIV='^(10\.[0-9]+|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]+\.[0-9]+$'

iface() {
  if [ -n "$PLACE_IFACE" ]; then echo "$PLACE_IFACE"; return; fi
  $IP -4 route show default | awk '{for(i=1;i<NF;i++) if($i=="dev"){print $(i+1); exit}}'
}
prefix() { $IP -4 -o addr show dev "$1" scope global | awk '{split($4,a,"/"); print a[2]; exit}'; }

LANS="10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 100.64.0.0/10"
NOT_PUBLIC="10.0.0.0/8, 127.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 100.64.0.0/10"

# place_rules accounting|guard: the rules of each place found in PLACES_ROOT, on its own interface NAMEdoc
place_rules() {
  local d n f ports b
  for d in "$PLACES_ROOT"/*/; do
    n=$(basename "$d"); f="$d.settings.json"
    [[ $n =~ ^[a-z][a-z0-9]{1,11}$ ]] && [ -f "$f" ] || continue
    if [ "$1" = accounting ]; then
      echo "		iifname \"${n}doc\" counter comment \"${n}doc: out\""
      echo "		oifname \"${n}doc\" counter comment \"${n}doc: in\""
      ports="3000, 3001"
      b=$(grep -oE '"sunshine": [0-9]+' "$f" | grep -oE '[0-9]+$' || true)
      if [ -n "$b" ] && [ "$b" -ge 20000 ] && [ "$b" -le 60000 ]; then ports="$ports, $((b - 5)), $b, $((b + 21))"; fi
      echo "		oifname \"${n}doc\" ip saddr != { $NOT_PUBLIC } tcp dport { $ports } ct state new add @place_flood_named { ip saddr limit rate over ${PLACE_NEW_PER_MIN}/minute burst $((PLACE_NEW_PER_MIN * 2)) packets } counter drop comment \"${n}doc: too many new connections from the internet\""
    else
      echo "		iifname \"${n}doc\" ip daddr { $LANS } counter drop comment \"${n}doc: tried to reach the LAN\""
    fi
  done
}

ruleset() {
local game="" webp="3000, 3001" b
for b in "${PLACE_SUNSHINE_BASES[@]}"; do
  [[ $b =~ ^[0-9]+$ ]] && [ "$b" -ge 20000 ] && [ "$b" -le 60000 ] || { echo "refused: PLACE_SUNSHINE_BASES entry $b is not a port from 20000 to 60000" >&2; exit 2; }
  webp="$webp, $((b - 5)), $b, $((b + 21))"
done
local srv="" e a p
for e in "${PLACE_GAME_SERVERS[@]}"; do
  a=${e%:*}; p=${e##*:}
  srv="$srv		ip saddr $POOL ip daddr $a udp dport $p counter accept comment \"game server $a:$p\"
"
done
local wan=""
if [ ${#PLACE_WAN_IPS[@]} -gt 0 ]; then
  wan="ip saddr $POOL ip daddr { $(IFS=,; echo "${PLACE_WAN_IPS[*]}" | sed 's/,/, /g') } counter drop comment \"any place: tried the home's public address (router, hairpin)\""
fi
if [ ${#PLACE_GAME_UDP[@]} -gt 0 ]; then
  local ports; ports=$(IFS=,; echo "${PLACE_GAME_UDP[*]}")
  game="ip saddr $POOL ip daddr $POOL udp dport { ${ports//,/, } } counter accept comment \"game between places\""
fi
cat <<RULES
table inet bridgeai_places {
	set place_flood {
		type ipv4_addr; size 65535; flags dynamic,timeout; timeout 10m
	}
	set place_flood_named {
		type ipv4_addr; size 65535; flags dynamic,timeout; timeout 10m
	}
	chain relay_out {
		type filter hook output priority raw; policy accept;
		meta mark 0x51a7 notrack comment "lan-discovery answers: never tracked (a tracked one would capture the client's next packet to that server)"
	}
	chain forward {
		type filter hook forward priority -5; policy accept;
$(place_rules accounting)
		ip saddr != { $NOT_PUBLIC } ip daddr $POOL tcp dport { $webp } ct state new add @place_flood { ip saddr limit rate over ${PLACE_NEW_PER_MIN}/minute burst $((PLACE_NEW_PER_MIN * 2)) packets } counter drop
		$wan
		ip saddr $POOL ct state established,related accept
		$game
${srv}$(place_rules guard)
		ip saddr $POOL ip daddr { $LANS } counter drop comment "any place: tried to reach the LAN"
	}
}
RULES
}

check_ips() {
  for p in "${PLACE_GAME_UDP[@]}"; do
    [[ $p =~ ^[0-9]+$ ]] && [ "$p" -ge 1024 ] && [ "$p" -le 65535 ] || { echo "refused: PLACE_GAME_UDP port $p is not a number from 1024 to 65535" >&2; exit 2; }
  done
  for a in "${PLACE_WAN_IPS[@]}"; do
    [[ $a =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "refused: PLACE_WAN_IPS entry $a is not an IPv4 address" >&2; exit 2; }
  done
  for e in "${PLACE_GAME_SERVERS[@]}"; do
    local sa="" sp=""
    [[ $e =~ ^([0-9.]+):([0-9]+)$ ]] && sa=${BASH_REMATCH[1]} && sp=${BASH_REMATCH[2]}
    [[ $sa =~ $PRIV ]] && [ "$sp" -ge 1024 ] 2>/dev/null && [ "$sp" -le 65535 ] \
      || { echo "refused: PLACE_GAME_SERVERS entry $e is not PRIVATE_ADDRESS:PORT (port 1024 to 65535)" >&2; exit 2; }
  done
  for a in "${PLACE_IPS[@]}"; do
    [[ $a =~ $PRIV ]] || { echo "refused: $a is not a private LAN address (a place is never published on a public one)" >&2; exit 2; }
  done
}

case "${1:-}" in
  print) check_ips; ruleset ;;
  up)
    check_ips
    # At boot "network-online" can be reached before DHCP has given the default route: wait for the interface and its address (PLACE_NET_WAIT seconds,
    # 90 by default) instead of failing, which left a host without its place addresses AND without the egress rules until somebody noticed (2026-11-25).
    IF=""; P=""
    for _ in $(seq 0 "${PLACE_NET_WAIT:-90}"); do
      IF=$(iface); [ -n "$IF" ] && P=$(prefix "$IF") && [ -n "$P" ] && break
      sleep 1
    done
    [ -n "$IF" ] || { echo "no LAN interface found (set PLACE_IFACE)" >&2; exit 1; }
    [ -n "$P" ] || { echo "no address on $IF" >&2; exit 1; }
    BAD=0
    for a in "${PLACE_IPS[@]}"; do
      if $IP -4 -o addr show dev "$IF" | grep -qE "inet $a/"; then echo "$a already on $IF"
      elif ${PING:-ping} -c1 -W1 -I "$IF" "$a" >/dev/null 2>&1; then
        # another device of the LAN already answers on it: taking it would break that device (an address conflict, 2026-11-25)
        echo "REFUSED: $a already answers on the LAN (another device uses it): not added; pick a free address for that place" >&2; BAD=3
      else $IP addr add "$a/$P" dev "$IF" && echo "added $a/$P on $IF"; fi
      # announce only an address that is ours: never one another device answers on
      if $IP -4 -o addr show dev "$IF" | grep -qE "inet $a/"; then command -v arping >/dev/null 2>&1 && arping -q -U -c 2 -I "$IF" "$a" >/dev/null 2>&1 || true; fi
    done
    # One nft transaction: the old table is replaced only if the new one loads; a ruleset with an error leaves the old one in place (2026-11-25: deleting
    # first and loading after left the places without their egress rules for two minutes when the new ruleset had a syntax error).
    RS=$(ruleset) || exit 2
    if printf 'table inet bridgeai_places\ndelete table inet bridgeai_places\n%s\n' "$RS" | $NFT -f -; then
      echo "nft table bridgeai_places loaded"
    else
      echo "the new ruleset was refused: the table that was loaded before is unchanged" >&2; exit 1
    fi
    exit $BAD ;;
  down)
    IF=$(iface)
    for a in "${PLACE_IPS[@]}"; do $IP addr del "$a/$(prefix "$IF")" dev "$IF" 2>/dev/null && echo "removed $a" || true; done
    $NFT delete table inet bridgeai_places 2>/dev/null && echo "nft table removed" || true ;;
  status)
    IF=$(iface); echo "interface: $IF"; for a in "${PLACE_IPS[@]}"; do $IP -4 -o addr show dev "$IF" | grep -qE "inet $a/" && echo "$a: up" || echo "$a: missing"; done
    $NFT list table inet bridgeai_places >/dev/null 2>&1 && echo "firewall: loaded" || echo "firewall: not loaded" ;;
  *) echo "usage: places-net.sh up|down|print|status" >&2; exit 2 ;;
esac
