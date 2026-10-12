#!/bin/bash
# Firewall for ports published by containers + egress rules for GUEST instances.
# Install on VM105 (needs root):
#   sudo install -m 755 ~/aibridge/docker-user-fw.sh /usr/local/sbin/docker-user-fw.sh && sudo /usr/local/sbin/docker-user-fw.sh
# Site addresses live in /etc/default/aibridge-fw (root-owned, never in git), for example:
#   LAN_CIDR=<lan-cidr>          the operator's LAN, allowed to reach published ports
#   EDGE_IP=<edge-ip>            the edge VM (reverse proxy), same
#   GUEST_PINHOLES=(                                one person's stack -> ONE LAN host:port per entry
#     "<stack subnet> <lan host ip> <tcp port>"     # why this exception exists
#   )
# (A "# ..." inside an entry's quotes is also tolerated: it is stripped before validation.)
# Installed as a boot-time system unit by docker-user-fw.service (next to this file); re-run it (systemctl restart
# docker-user-fw.service) after creating a stack, so its gateway:3099 pinhole below is added.
#
# Ports published by containers (docker run -p) do NOT go through ufw (INPUT),
# they go straight through DOCKER-USER in FORWARD. Without this, any -p is
# wide open to the whole internet. The container's response leaves with the
# bridge's own IP (not the LAN one) -> ESTABLISHED,RELATED has to be allowed
# first, otherwise return traffic gets dropped.
#
# Copy of /usr/local/sbin/docker-user-fw.sh on VM105, with ONE line added to let the edge VM101 (EDGE_IP) reach the
# published ports -- the public vhosts proxy_pass here.
#
# 2026-10-04: GUEST instances (ops/provision_guest.sh) each live in their own docker network carved out of
# GUEST_NET below. Until now a new compose project got the next free 172.x/16 (172.22...) which none of the
# rules below allowed, so ALL of its outbound traffic was dropped ("can't reach NVIDIA NIM", found the hard way).
# Guests are allowed to reach the INTERNET but NOT the LAN, other docker networks, or this host: a guest runs
# whatever its user asks Hermes to run (the image even ships nmap/tcpdump), so it must not see resolve-host, the GPU
# box, the router, aibridge/open-webui or the other guests.
set -e
GUEST_NET=172.28.0.0/16
GUEST_PINHOLES=()
CONF=/etc/default/aibridge-fw
[ -f "$CONF" ] || { echo "missing $CONF (LAN_CIDR, EDGE_IP, GUEST_PINHOLES): refusing to rewrite the firewall" >&2; exit 1; }
# shellcheck source=/dev/null
. "$CONF"
: "${LAN_CIDR:?LAN_CIDR missing in $CONF}" "${EDGE_IP:?EDGE_IP missing in $CONF}"

# --- validate every pinhole BEFORE touching iptables: a typo must not leave DOCKER-USER half built (open) ---
is_ip() {  # a.b.c.d or a.b.c.d/len
  local ip="${1%%/*}" len="" o
  [[ "$1" == */* ]] && len="${1#*/}"
  [[ "$ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 1
  for o in ${ip//./ }; do [ "$((10#$o))" -le 255 ] || return 1; done
  [ -z "$len" ] || { [[ "$len" =~ ^[0-9]{1,2}$ ]] && [ "$((10#$len))" -le 32 ]; }
}
PINHOLE_RULES=()
for h in "${GUEST_PINHOLES[@]}"; do
  h="${h%%#*}"
  read -r PH_SRC PH_DST PH_PORT PH_EXTRA <<< "$h"
  [ -n "$PH_SRC$PH_DST$PH_PORT" ] || continue   # empty or comment-only entry
  if [ -n "$PH_EXTRA" ] || ! is_ip "$PH_SRC" || ! is_ip "$PH_DST" || ! [[ "$PH_PORT" =~ ^[0-9]{1,5}$ ]] \
     || [ "$((10#$PH_PORT))" -lt 1 ] || [ "$((10#$PH_PORT))" -gt 65535 ]; then
    echo "invalid GUEST_PINHOLES entry in $CONF (want '<subnet> <ip> <port>'): '$h'; firewall left untouched" >&2; exit 1
  fi
  PINHOLE_RULES+=("-A DOCKER-USER -s $PH_SRC -d $PH_DST -p tcp --dport $((10#$PH_PORT)) -j RETURN")
done

# --- build the whole DOCKER-USER chain, then load it in ONE atomic iptables-restore ---
# `:DOCKER-USER - [0:0]` under --noflush empties only that chain, and the new rules replace the old ones in a single
# commit, so there is no moment with an empty (= wide open) chain and a failure leaves the previous rules in place.
RULES=(
  "*filter"
  ":DOCKER-USER - [0:0]"
  "-A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN"
  "-A DOCKER-USER -i lo -j RETURN"
)

# --- guests: explicit pinholes (ONE person's stack -> ONE host:port on the LAN) ---
# GUEST_PINHOLES (from $CONF), format "<guest subnet> <destination ip> <tcp port>". Keep it short and each line commented:
# every entry is an exception to "guests do not see the LAN". Must come BEFORE the guest DROP rules below (first match
# wins). Example: one stack -> its Claude Code machine on port 22 with a restricted key (ops/install_claude_gate.sh).
RULES+=("${PINHOLE_RULES[@]}")

# --- guests: internet only ---
for dst in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 169.254.0.0/16; do
  RULES+=("-A DOCKER-USER -s $GUEST_NET -d $dst -j DROP")
done
RULES+=("-A DOCKER-USER -s $GUEST_NET -j RETURN")

# --- LAN, edge VM, and the operator's own docker networks (unchanged) ---
RULES+=("-A DOCKER-USER -s $LAN_CIDR -j RETURN")
RULES+=("-A DOCKER-USER -s $EDGE_IP -j RETURN")
for n in 17 18 19 20 21; do RULES+=("-A DOCKER-USER -s 172.$n.0.0/16 -j RETURN"); done
RULES+=("-A DOCKER-USER -j DROP" "COMMIT")
printf '%s\n' "${RULES[@]}" | iptables-restore --noflush

# Guests must not reach services on the host itself either (ssh, etc.): that path is INPUT, not FORWARD.
# BUT replies to connections the HOST starts toward a guest's published port (health checks, ops scripts run on VM105)
# also arrive through INPUT with a guest source address, so ESTABLISHED/RELATED must be accepted first, otherwise the
# host can't talk to its own guests' ports (found 2026-10-05: curl from VM105 to a stack's web port timed out while
# the same port answered fine from the LAN). Idempotent: remove then re-add in the right order.
while iptables -D INPUT -s "$GUEST_NET" -j DROP 2>/dev/null; do :; done
while iptables -D INPUT -s "$GUEST_NET" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; do :; done
iptables -I INPUT 1 -s "$GUEST_NET" -j DROP
iptables -I INPUT 1 -s "$GUEST_NET" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Wake-on-demand (2026-10-07): each guest's nginx must reach ITS OWN waker, nothing else on the host. The waker binds to
# that stack's network gateway (ops/wake/waker.py, port 3099), so the pinhole is: that stack's subnet -> that gateway:3099.
# Inserted last at position 1 so it sits ABOVE the DROP (a ufw rule never gets a say: INPUT 1 is evaluated before ufw).
for net in $(docker network ls --format '{{.Name}}' | grep -E '^stack-.*_default$'); do
  read -r subnet gw < <(docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}} {{.Gateway}}{{end}}' "$net")
  [ -n "$subnet" ] && [ -n "$gw" ] || continue
  while iptables -D INPUT -s "$subnet" -d "$gw" -p tcp --dport 3099 -j ACCEPT 2>/dev/null; do :; done
  iptables -I INPUT 1 -s "$subnet" -d "$gw" -p tcp --dport 3099 -j ACCEPT
done
