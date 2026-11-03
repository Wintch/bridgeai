#!/bin/bash
# A THROWAWAY per-person Hermes container, built from the real person-stack template plus the hardening profile, to find out
# what the profile breaks before it touches anybody's stack (run on VM105 from ~/aibridge; nothing here needs sudo):
#
#   ops/hardening_trial_stack.sh up     [name]   create it and start ONLY its hermes service (1-3 minutes)
#   ops/hardening_trial_stack.sh check  [name]   profile check, 16-point smoke test, keys page, a restart, permission errors
#   ops/hardening_trial_stack.sh down   [name]   stop it and delete everything it made
#
# name: must start with "hardtest" (default hardtest), so this can never touch a real person's stack.
# What it is: the same compose file the people use (stacks/docker-compose.stack.yml: the keys page, the dashboard, the
# gateways and persist mounts, the 2.5 GB limit) + stacks/hardening.override.yml. What it is NOT: it starts no web UI, voice,
# nginx or waker, and it is never added to ops/wake/stacks.json, so nothing else on the VM changes (provision_stack.sh
# restarts the waker, which serves the four people). It has NO model key (an empty NVIDIA_API_KEY): nothing of the
# operator's or a person's goes into it. The extra port it publishes is the dashboard's, on the LAN IP, behind a random password.
set -euo pipefail
cd "$(dirname "$0")/.."
ACTION="${1:-}"; NAME="${2:-hardtest}"
[[ "$ACTION" =~ ^(up|check|down)$ ]] || { sed -n 2,16p "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
[[ "$NAME" =~ ^hardtest[a-z0-9]{0,8}$ ]] || { echo "the trial's name must start with 'hardtest' (and be at most 16 characters)" >&2; exit 2; }
DIR="$PWD/stacks/$NAME"; ENVF="$DIR/.env"; C="stack-$NAME-hermes"
COMPOSE=(docker compose -p "stack-$NAME" -f stacks/docker-compose.stack.yml -f stacks/hardening.override.yml --env-file "$ENVF")

case "$ACTION" in
up)
  if [ ! -f "$ENVF" ]; then
    LAN_IP="${LAN_IP:-$(grep -m1 '^LAN_IP=' .env 2>/dev/null | cut -d= -f2)}"; : "${LAN_IP:?set LAN_IP (the host LAN address) in ~/aibridge/.env}"
    mkdir -p "$DIR/persist" "$DIR/workdir" "$DIR/videos" "$DIR/owui-data/uploads" "$DIR/web-outputs" "$DIR/gateways" "$DIR/voice"
    # shellcheck source=/dev/null
    . ops/lib/alloc.sh
    n=$(alloc_subnet)
    umask 077
    cat > "$ENVF" <<ENV
STACK_NAME=$NAME
STACK_DIR=$DIR
REPO_DIR=$PWD
LAN_IP=$LAN_IP
PUBLIC_HOST=$NAME.invalid
STACK_SUBNET=172.28.$n.0/24
WEB_PORT=$(alloc_port 3001)
DASH_PORT=$(alloc_port 9130)
HERMES_API_KEY=hk-$(openssl rand -hex 24)
DASH_USER=$NAME
DASH_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
DASH_SECRET=$(openssl rand -hex 32)
ADMIN_EMAIL=$NAME@aibridge.local
OPENWEBUI_SECRET_KEY=$(openssl rand -hex 32)
OPENWEBUI_ADMIN_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
NVIDIA_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USERS=
ENV
    echo "created $ENVF (subnet 172.28.$n.0/24; no model key, no Telegram)"
  else
    echo "trial '$NAME' already exists: starting it with its saved settings"
  fi
  "${COMPOSE[@]}" config -q
  echo "starting ONLY the hermes service of $NAME (the first boot takes 1-3 minutes; next: ops/hardening_trial_stack.sh check $NAME)"
  "${COMPOSE[@]}" up -d hermes 2>&1 | tail -5
  ;;
check)
  docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null | grep -q true || { echo "$C is not running: ops/hardening_trial_stack.sh up $NAME first" >&2; exit 2; }
  rc=0
  echo "== 1. what the container really has (waits for the gateway first)"
  python3 ops/container_hardening.py "$C" || rc=1
  echo "== 2. the 16-point smoke test"
  ops/hardening_smoke.sh "$C" || rc=1
  echo "== 3. what only a person's stack runs: the keys page and what listens"
  if docker exec "$C" curl -sf -m 5 http://127.0.0.1:8700/keys/api/status >/dev/null 2>&1; then echo "PASS  keys page API answers (:8700)"; else echo "FAIL  keys page API does not answer (:8700)"; rc=1; fi
  docker exec "$C" python3 -c '
ports = set()
for f in ("/proc/net/tcp", "/proc/net/tcp6"):
    for l in open(f).read().splitlines()[1:]:
        p = l.split()
        if p[3] == "0A":
            ports.add(int(p[1].split(":")[1], 16))
print("INFO  listening:", sorted(ports))' || true
  echo "== 4. stop and start again (the SIGTERM path flushes state to /hermes-persist with the reduced capabilities)"
  echo "restarting $C: it stops the gateway (up to 25 s), flushes, boots again (1-3 minutes); do not cancel..."
  docker restart "$C" >/dev/null
  up=
  for i in $(seq 1 100); do
    docker exec "$C" curl -sf -m 3 http://localhost:8642/health >/dev/null 2>&1 && { up=1; break; }
    [ $((i % 10)) -eq 0 ] && echo "  still booting ($((i * 3)) s)..."
    sleep 3
  done
  if [ -n "$up" ]; then echo "PASS  gateway answers again after the restart"; else echo "FAIL  the gateway did not come back in 5 minutes"; rc=1; fi
  if [ -n "$(docker exec "$C" sh -c 'ls -A /hermes-persist 2>/dev/null | head -1')" ]; then echo "PASS  /hermes-persist has files"; else echo "FAIL  /hermes-persist is empty after a stop"; rc=1; fi
  echo "== 5. permission errors anywhere in the container's log (the sign of a capability that was needed)"
  n=$(docker logs "$C" 2>&1 | grep -c -i -E "operation not permitted|permission denied|EPERM" || true)
  if [ "$n" -eq 0 ]; then echo "PASS  none"; else echo "FAIL  $n line(s); first ones:"; docker logs "$C" 2>&1 | grep -i -E "operation not permitted|permission denied|EPERM" | head -8 | cut -c1-200; rc=1; fi
  [ $rc -eq 0 ] && echo "ALL GOOD: the profile did not break the person-stack container" || echo "SOMETHING FAILED: do not fold the profile into the template until each line above is understood"
  exit $rc
  ;;
down)
  [ -d "$DIR" ] || { echo "no trial named $NAME"; exit 0; }
  [ -f "$ENVF" ] && "${COMPOSE[@]}" down 2>&1 | tail -3
  # the container ran as root, so its files in the bind mounts are root's: delete them from a container, not with rm
  docker run --rm --entrypoint sh -v "$DIR:/d" aibridge-hermes-agent:latest -c 'rm -rf /d/* /d/.[!.]* 2>/dev/null; true'
  rmdir "$DIR" && echo "removed $DIR"
  ;;
esac
