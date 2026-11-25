#!/bin/bash
# What a desktop place may reach, and the LAN addresses it is published on (run as root on the GPU host).
#   places-net.sh up|down|print|status
# Site values live in /etc/default/bridgeai-places (root-owned, not in git):
#   PLACE_IPS=(192.168.x.172 192.168.x.173)   extra addresses of THIS host's LAN interface, one per place (place.py create/recreate --bind ADDRESS)
#   PLACE_GAME_UDP=(27960)                    UDP ports one place may reach on another place, so two people can play a LAN game against each other (the one that hosts
#                                             publishes the port on its address with place.py --udp 27960; the other connects to THAT address). Nothing else between places.
#   PLACE_NEW_PER_MIN=30                      new TCP connections per minute one PUBLIC address may open to a place's web ports (a place the router forwards to the
#                                             internet): more are dropped, so a password cannot be guessed at speed. Addresses of the LAN are not limited.
#   PLACE_SUNSHINE_BASES=(49989)              the base port of each place's Moonlight stream (place.py --sunshine BASE): its TCP ports (BASE-5, BASE, BASE+21) get the
#                                             same limit on new connections from public addresses as the web ports
#   PLACE_IFACE=                              the LAN interface; by default the one that carries the default route (a NIC can be renumbered by the kernel)
# `up` adds those addresses (idempotent, announced on the LAN) and loads the nft table `bridgeai_places`; `down` removes both; `print` shows the ruleset.
#
# The rule: a place reaches the INTERNET and nothing else. Its traffic towards any private, link-local or carrier-grade range is dropped in the forward path
# (so not the router, not the other place, not the host's other containers, not another PC), except answers to connections the LAN opened to its published
# port (conntrack: established, related). The host's own input chain already drops what a container sends to the host itself.
# Why: a place runs a browser and whatever its person installs; it must not see the media host, the GPU gate, the router or another person's place.
set -euo pipefail
CONF=${PLACES_NET_CONF:-/etc/default/bridgeai-places}
IP=${IP:-ip}; NFT=${NFT:-nft}
POOL=172.30.0.0/16                               # place.py: one /24 per place
PLACE_IPS=(); PLACE_IFACE=""; PLACE_GAME_UDP=(); PLACE_NEW_PER_MIN=30; PLACE_SUNSHINE_BASES=()
[ -f "$CONF" ] && . "$CONF"
PRIV='^(10\.[0-9]+|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]+\.[0-9]+$'

iface() {
  if [ -n "$PLACE_IFACE" ]; then echo "$PLACE_IFACE"; return; fi
  $IP -4 route show default | awk '{for(i=1;i<NF;i++) if($i=="dev"){print $(i+1); exit}}'
}
prefix() { $IP -4 -o addr show dev "$1" scope global | awk '{split($4,a,"/"); print a[2]; exit}'; }

ruleset() {
local game="" webp="3000, 3001" b
for b in "${PLACE_SUNSHINE_BASES[@]}"; do
  [[ $b =~ ^[0-9]+$ ]] && [ "$b" -ge 20000 ] && [ "$b" -le 60000 ] || { echo "refused: PLACE_SUNSHINE_BASES entry $b is not a port from 20000 to 60000" >&2; exit 2; }
  webp="$webp, $((b - 5)), $b, $((b + 21))"
done
if [ ${#PLACE_GAME_UDP[@]} -gt 0 ]; then
  local ports; ports=$(IFS=,; echo "${PLACE_GAME_UDP[*]}")
  game="ip saddr $POOL ip daddr $POOL udp dport { ${ports//,/, } } accept"
fi
cat <<RULES
table inet bridgeai_places {
	set place_flood {
		type ipv4_addr; size 8192; flags dynamic,timeout; timeout 10m
	}
	chain forward {
		type filter hook forward priority -5; policy accept;
		ip saddr != { 10.0.0.0/8, 127.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 100.64.0.0/10 } ip daddr $POOL tcp dport { $webp } ct state new add @place_flood { ip saddr limit rate over ${PLACE_NEW_PER_MIN}/minute burst $((PLACE_NEW_PER_MIN * 2)) packets } counter drop
		ip saddr $POOL ct state established,related accept
		$game
		ip saddr $POOL ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 100.64.0.0/10 } counter drop
	}
}
RULES
}

check_ips() {
  for p in "${PLACE_GAME_UDP[@]}"; do
    [[ $p =~ ^[0-9]+$ ]] && [ "$p" -ge 1024 ] && [ "$p" -le 65535 ] || { echo "refused: PLACE_GAME_UDP port $p is not a number from 1024 to 65535" >&2; exit 2; }
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
        echo "REFUSED: $a already answers on the LAN (another device uses it): not added; pick a free address for that place" >&2; BAD=1
      else $IP addr add "$a/$P" dev "$IF" && echo "added $a/$P on $IF"; fi
      # announce only an address that is ours: never one another device answers on
      if $IP -4 -o addr show dev "$IF" | grep -qE "inet $a/"; then command -v arping >/dev/null 2>&1 && arping -q -U -c 2 -I "$IF" "$a" >/dev/null 2>&1 || true; fi
    done
    $NFT delete table inet bridgeai_places 2>/dev/null || true
    ruleset | $NFT -f - && echo "nft table bridgeai_places loaded"
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
