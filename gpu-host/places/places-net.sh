#!/bin/bash
# What a desktop place may reach, and the LAN addresses it is published on (run as root on the GPU host).
#   places-net.sh up|down|print|status
# Site values live in /etc/default/bridgeai-places (root-owned, not in git):
#   PLACE_IPS=(192.168.x.172 192.168.x.173)   extra addresses of THIS host's LAN interface, one per place (place.py create/recreate --bind ADDRESS)
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
PLACE_IPS=(); PLACE_IFACE=""
[ -f "$CONF" ] && . "$CONF"
PRIV='^(10\.[0-9]+|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]+\.[0-9]+$'

iface() {
  if [ -n "$PLACE_IFACE" ]; then echo "$PLACE_IFACE"; return; fi
  $IP -4 route show default | awk '{for(i=1;i<NF;i++) if($i=="dev"){print $(i+1); exit}}'
}
prefix() { $IP -4 -o addr show dev "$1" scope global | awk '{split($4,a,"/"); print a[2]; exit}'; }

ruleset() {
cat <<RULES
table inet bridgeai_places {
	chain forward {
		type filter hook forward priority -5; policy accept;
		ip saddr $POOL ct state established,related accept
		ip saddr $POOL ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 100.64.0.0/10 } counter drop
	}
}
RULES
}

check_ips() {
  for a in "${PLACE_IPS[@]}"; do
    [[ $a =~ $PRIV ]] || { echo "refused: $a is not a private LAN address (a place is never published on a public one)" >&2; exit 2; }
  done
}

case "${1:-}" in
  print) ruleset ;;
  up)
    check_ips
    IF=$(iface); [ -n "$IF" ] || { echo "no LAN interface found (set PLACE_IFACE)" >&2; exit 1; }
    P=$(prefix "$IF"); [ -n "$P" ] || { echo "no address on $IF" >&2; exit 1; }
    for a in "${PLACE_IPS[@]}"; do
      if $IP -4 -o addr show dev "$IF" | grep -qE "inet $a/"; then echo "$a already on $IF"; else $IP addr add "$a/$P" dev "$IF" && echo "added $a/$P on $IF"; fi
      command -v arping >/dev/null 2>&1 && arping -q -U -c 2 -I "$IF" "$a" >/dev/null 2>&1 || true
    done
    $NFT delete table inet bridgeai_places 2>/dev/null || true
    ruleset | $NFT -f - && echo "nft table bridgeai_places loaded" ;;
  down)
    IF=$(iface)
    for a in "${PLACE_IPS[@]}"; do $IP addr del "$a/$(prefix "$IF")" dev "$IF" 2>/dev/null && echo "removed $a" || true; done
    $NFT delete table inet bridgeai_places 2>/dev/null && echo "nft table removed" || true ;;
  status)
    IF=$(iface); echo "interface: $IF"; for a in "${PLACE_IPS[@]}"; do $IP -4 -o addr show dev "$IF" | grep -qE "inet $a/" && echo "$a: up" || echo "$a: missing"; done
    $NFT list table inet bridgeai_places >/dev/null 2>&1 && echo "firewall: loaded" || echo "firewall: not loaded" ;;
  *) echo "usage: places-net.sh up|down|print|status" >&2; exit 2 ;;
esac
