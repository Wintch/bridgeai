#!/bin/bash
# Create (or re-print) a full per-person web stack on VM105: own Hermes + Open WebUI + nginx + TTS, own data and network.
#   ./ops/provision_stack.sh <name> [--public-host host] [--nim-key KEY] [--model provider/model-id]
#                                   [--telegram-token T --telegram-user ID] [--jobfinder bundle.tgz]
# --jobfinder: also install the clean job-search system (see make_jobfinder_bundle.sh / install_jobfinder.sh).
# The person gets: a web URL + admin login, a Hermes dashboard login (to pick the model and enter THEIR OWN keys).
# No operator keys go inside. --nim-key only if the person handed you theirs. Telegram is optional.
# The port to give to the edge VM is printed at the end (WEB_PORT).
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:-}"; shift || true
[[ "$NAME" =~ ^[a-z][a-z0-9]{1,19}$ ]] || { echo "usage: $0 <name: a-z0-9, 2-20 chars> [options]" >&2; exit 2; }
NIM_KEY=""; PROVIDER="nvidia"; MODEL="nvidia/nemotron-3-super-120b-a12b"; TG_TOKEN=""; TG_USER=""; JOBFINDER=""; PUBLIC_HOST="$NAME.example.com"
while [ $# -gt 0 ]; do
  case "$1" in
    --public-host) PUBLIC_HOST="$2"; shift 2;;
    --nim-key) NIM_KEY="$2"; shift 2;;
    --model) PROVIDER="${2%%/*}"; MODEL="$2"; shift 2;;
    --telegram-token) TG_TOKEN="$2"; shift 2;;
    --telegram-user) TG_USER="$2"; shift 2;;
    --jobfinder) JOBFINDER="$2"; shift 2;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac
done
LAN_IP="${LAN_IP:-<docker-host-ip>}"
DIR="$PWD/stacks/$NAME"; ENVF="$DIR/.env"
COMPOSE=(docker compose -p "stack-$NAME" -f stacks/docker-compose.stack.yml --env-file "$ENVF")

if [ ! -f "$ENVF" ]; then
  mkdir -p "$DIR/persist" "$DIR/workdir" "$DIR/videos" "$DIR/owui-data/uploads" "$DIR/web-outputs"
  chmod 755 "$DIR/web-outputs"
  # next free value of KEY (>= START) across all stacks and guests
  next() { local p="$2"; while grep -hqx "$1=$p" stacks/*/.env guests/*/.env 2>/dev/null; do p=$((p+1)); done; echo "$p"; }
  n=1; while grep -hqx "STACK_SUBNET=172.28.$n.0/24" stacks/*/.env guests/*/.env 2>/dev/null; do n=$((n+1)); done
  umask 077
  cat > "$ENVF" <<ENV
STACK_NAME=$NAME
STACK_DIR=$DIR
REPO_DIR=$PWD
LAN_IP=$LAN_IP
PUBLIC_HOST=$PUBLIC_HOST
STACK_SUBNET=172.28.$n.0/24
WEB_PORT=$(next WEB_PORT 3001)
DASH_PORT=$(next DASH_PORT 9130)
HERMES_API_KEY=hk-$(openssl rand -hex 24)
DASH_USER=$NAME
DASH_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
DASH_SECRET=$(openssl rand -hex 32)
ADMIN_EMAIL=$NAME@aibridge.local
OPENWEBUI_SECRET_KEY=$(openssl rand -hex 32)
OPENWEBUI_ADMIN_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
HERMES_MODEL_PROVIDER=$PROVIDER
HERMES_MODEL_DEFAULT=$MODEL
NVIDIA_API_KEY=$NIM_KEY
TELEGRAM_BOT_TOKEN=$TG_TOKEN
TELEGRAM_ALLOWED_USERS=$TG_USER
ENV
  echo "created $ENVF"
else
  echo "stack '$NAME' already exists, (re)starting with its saved settings"
fi

[ -n "$JOBFINDER" ] && ./ops/install_jobfinder.sh "$NAME" "$JOBFINDER"
"${COMPOSE[@]}" config -q
"${COMPOSE[@]}" up -d 2>&1 | tail -5
set -a; . "$ENVF"; set +a
echo -n "waiting for the web UI"; for i in $(seq 1 60); do
  [ "$(curl -s -m2 -o /dev/null -w %{http_code} "http://$LAN_IP:$WEB_PORT/health")" = 200 ] && { echo " up after ~$((i*3))s"; break; }; echo -n .; sleep 3; done

# Same preset as the main stack (system prompt for files/PDF/Mermaid, vision, private model, voice).
OWUI_URL="http://$LAN_IP:$WEB_PORT" ENV_FILE="$ENVF" ADMIN_EMAIL="$ADMIN_EMAIL" TTS_URL="http://tts:5002/v1" ./ops/openwebui_setup.sh

cat > "$DIR/credentials.txt" <<CRED
Stack for: $NAME
Web UI (give THIS to the edge VM):  http://$LAN_IP:$WEB_PORT      public name: https://$PUBLIC_HOST
  login:   $ADMIN_EMAIL   password: $OPENWEBUI_ADMIN_PASSWORD
Hermes dashboard (model + keys):    http://$LAN_IP:$DASH_PORT   user: $DASH_USER   password: $DASH_PASSWORD
Starting model: $HERMES_MODEL_DEFAULT (provider $HERMES_MODEL_PROVIDER)
LLM key: $([ -n "$NVIDIA_API_KEY" ] && echo "provided" || echo "NONE yet: the person enters their own (NVIDIA NIM free) in the dashboard")
Telegram: $([ -n "$TELEGRAM_BOT_TOKEN" ] && echo enabled || echo "not enabled (optional)")
CRED
chmod 600 "$DIR/credentials.txt"; cat "$DIR/credentials.txt"
