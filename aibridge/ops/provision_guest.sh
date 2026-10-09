#!/bin/bash
# Create (or print the credentials of) a standalone Hermes instance for one person. Run on VM105 from ~/aibridge.
#   ./ops/provision_guest.sh <name> [--nim-key KEY] [--model provider/model-id]
#                                   [--telegram-token T --telegram-user ID]
# Default = URL + key only: an OpenAI-compatible endpoint with its own API key, plus a dashboard login where
# the user chooses the model and enters their own keys. Telegram is optional. No operator keys are put inside.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:-}"; shift || true
[[ "$NAME" =~ ^[a-z][a-z0-9-]{1,19}$ ]] || { echo "usage: $0 <name: a-z 0-9 -, 2-20 chars> [options]" >&2; exit 2; }
NIM_KEY=""; PROVIDER="nvidia"; MODEL="nvidia/nemotron-3-super-120b-a12b"; TG_TOKEN=""; TG_USER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --nim-key) NIM_KEY="$2"; shift 2;;
    --model) PROVIDER="${2%%/*}"; MODEL="$2"; shift 2;;
    --telegram-token) TG_TOKEN="$2"; shift 2;;
    --telegram-user) TG_USER="$2"; shift 2;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac
done
LAN_IP="${LAN_IP:-$(grep -m1 '^LAN_IP=' .env 2>/dev/null | cut -d= -f2)}"; : "${LAN_IP:?set LAN_IP (the host LAN address) in ~/aibridge/.env}"
DIR="$PWD/guests/$NAME"
ENVF="$DIR/.env"
COMPOSE=(docker compose -p "guest-$NAME" -f guests/docker-compose.guest.yml --env-file "$ENVF")

if [ ! -f "$ENVF" ]; then
  mkdir -p "$DIR/persist" "$DIR/workdir" "$DIR/videos"
  used() { grep -h "^$1=" guests/*/.env 2>/dev/null | cut -d= -f2 | sort -n; }
  next() { local p="$2"; while used "$1" | grep -qx "$p"; do p=$((p+1)); done; echo "$p"; }
  next_subnet() { local n=1; while grep -hq "^GUEST_SUBNET=172.28.$n.0/24" guests/*/.env 2>/dev/null; do n=$((n+1)); done; echo $n; }
  umask 077
  cat > "$ENVF" <<ENV
GUEST_NAME=$NAME
GUEST_DIR=$DIR
LAN_IP=$LAN_IP
GUEST_SUBNET=172.28.$(next_subnet).0/24
API_PORT=$(next API_PORT 8650)
DASH_PORT=$(next DASH_PORT 9120)
HERMES_API_KEY=hk-$(openssl rand -hex 24)
DASH_USER=$NAME
DASH_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
DASH_SECRET=$(openssl rand -hex 32)
HERMES_MODEL_PROVIDER=$PROVIDER
HERMES_MODEL_DEFAULT=$MODEL
NVIDIA_API_KEY=$NIM_KEY
TELEGRAM_BOT_TOKEN=$TG_TOKEN
TELEGRAM_ALLOWED_USERS=$TG_USER
ENV
  echo "created $ENVF"
else
  echo "guest '$NAME' already exists, (re)starting with its saved settings"
  if ! grep -q '^GUEST_SUBNET=' "$ENVF"; then  # created before guests had their own subnet: move it onto one
    n=1; while grep -hq "^GUEST_SUBNET=172.28.$n.0/24" guests/*/.env 2>/dev/null; do n=$((n+1)); done
    echo "GUEST_SUBNET=172.28.$n.0/24" >> "$ENVF"
    "${COMPOSE[@]}" down 2>&1 | tail -1   # the network has to be recreated on the new subnet
  fi
fi

"${COMPOSE[@]}" config -q
"${COMPOSE[@]}" up -d 2>&1 | tail -2
set -a; . "$ENVF"; set +a
echo -n "waiting for the API"; for i in $(seq 1 60); do
  [ "$(curl -s -m2 -o /dev/null -w %{http_code} "http://$LAN_IP:$API_PORT/health")" = 200 ] && { echo " up after ~$((i*3))s"; break; }; echo -n .; sleep 3; done

cat > "$DIR/credentials.txt" <<CRED
Hermes instance for: $NAME
API (OpenAI-compatible):  http://$LAN_IP:$API_PORT/v1     model name: hermes-agent
API key:                  $HERMES_API_KEY
Dashboard (model + keys): http://$LAN_IP:$DASH_PORT      user: $DASH_USER   password: $DASH_PASSWORD
Starting model:           $HERMES_MODEL_DEFAULT   (provider $HERMES_MODEL_PROVIDER)
Own keys:                 $([ -n "$NVIDIA_API_KEY" ] && echo "NVIDIA key provided" || echo "none yet: the user enters them in the dashboard")
Telegram:                 $([ -n "$TELEGRAM_BOT_TOKEN" ] && echo "enabled" || echo "not enabled (optional)")
CRED
chmod 600 "$DIR/credentials.txt"
cat "$DIR/credentials.txt"
