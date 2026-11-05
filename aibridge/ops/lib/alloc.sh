# Shared by ops/provision_stack.sh and ops/provision_guest.sh (run from ~/aibridge). Before 2026-10-09 each script only
# looked at its own kind, so a stack and a guest could get the same 172.28.N.0/24 or the same port.
# alloc_subnet          -> N of the first 172.28.N.0/24 no stack, guest or hub uses. The hub's /24 is reserved in hub.env (HUB_SUBNET) because
#                          its network exists only while the collector runs: Docker alone would not show it, and a stack created in
#                          between would get the same /24 and make the hub fail with "Pool overlaps". So THIS FILE MUST BE CURRENT
#                          ON THE VM before any stack or guest is created after the hub is installed (ops/hub_install.sh copies it).
# alloc_port START      -> first port >= START that no stack/guest .env names (any *_PORT) and nothing listens on
alloc_subnet() {
  local used n=1
  used=$( { grep -hoE "^(STACK|GUEST|HUB)_SUBNET=172\.28\.[0-9]+\.0/24" stacks/*/.env guests/*/.env hub.env 2>/dev/null | cut -d= -f2
            docker network inspect $(docker network ls -q) -f '{{range .IPAM.Config}}{{.Subnet}} {{end}}' 2>/dev/null \
              | tr ' ' '\n'; } | sort -u)
  while printf '%s\n' "$used" | grep -qx "172\.28\.$n\.0/24"; do n=$((n + 1)); done
  echo "$n"
}
alloc_port() {
  local p="$1"
  while grep -hqE "^[A-Z_]*PORT=$p$" stacks/*/.env guests/*/.env 2>/dev/null || ss -Hltn "sport = :$p" | grep -q .; do
    p=$((p + 1))
  done
  echo "$p"
}
