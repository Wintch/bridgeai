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
NIM_KEY=""; PROVIDER="nvidia"; MODEL="nvidia/nemotron-3-super-120b-a12b"; TG_TOKEN=""; TG_USER=""; JOBFINDER=""; PUBLIC_HOST="$NAME.${PUBLIC_DOMAIN:-example.com}"  # export PUBLIC_DOMAIN (real domains are not kept in the repo)
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
LAN_IP="${LAN_IP:-$(grep -m1 '^LAN_IP=' .env 2>/dev/null | cut -d= -f2)}"; : "${LAN_IP:?set LAN_IP (the host LAN address) in ~/aibridge/.env}"
DIR="$PWD/stacks/$NAME"; ENVF="$DIR/.env"
COMPOSE=(docker compose -p "stack-$NAME" -f stacks/docker-compose.stack.yml --env-file "$ENVF")

if [ ! -f "$ENVF" ]; then
  mkdir -p "$DIR/persist" "$DIR/workdir" "$DIR/videos" "$DIR/owui-data/uploads" "$DIR/web-outputs"
  chmod 755 "$DIR/web-outputs"
  # Wake-on-demand: nginx of this stack hands visits to the waker bound to the stack's network gateway (port 3099).
  mkdir -p "$DIR/wake"
  . ops/lib/alloc.sh   # subnet and ports shared with guests, never colliding
  n=$(alloc_subnet)
  umask 077
  cat > "$ENVF" <<ENV
STACK_NAME=$NAME
STACK_DIR=$DIR
REPO_DIR=$PWD
LAN_IP=$LAN_IP
PUBLIC_HOST=$PUBLIC_HOST
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
HERMES_MODEL_PROVIDER=$PROVIDER
HERMES_MODEL_DEFAULT=$MODEL
NVIDIA_API_KEY=$NIM_KEY
TELEGRAM_BOT_TOKEN=$TG_TOKEN
TELEGRAM_ALLOWED_USERS=$TG_USER
ENV
  printf 'set $waker http://172.28.%s.1:3099;\n' "$n" > "$DIR/wake/upstream.conf"
  echo "created $ENVF"
  NEW_STACK=1
else
  echo "stack '$NAME' already exists, (re)starting with its saved settings"
fi

NEW_STACK="${NEW_STACK:-0}"
[ -n "$JOBFINDER" ] && ./ops/install_jobfinder.sh "$NAME" "$JOBFINDER"
"${COMPOSE[@]}" config -q
"${COMPOSE[@]}" up -d 2>&1 | tail -5
set -a; . "$ENVF"; set +a
echo -n "waiting for the web UI"; for i in $(seq 1 60); do
  [ "$(curl -s -m2 -o /dev/null -w %{http_code} "http://$LAN_IP:$WEB_PORT/health")" = 200 ] && { echo " up after ~$((i*3))s"; break; }; echo -n .; sleep 3; done

# Same preset as the main stack (system prompt for files/PDF/Mermaid, vision, private model, voice).
JOBS=$([ -n "$JOBFINDER" ] && echo 1 || echo 0) WELCOME=1 OWUI_URL="http://$LAN_IP:$WEB_PORT" ENV_FILE="$ENVF" ADMIN_EMAIL="$ADMIN_EMAIL" TTS_URL="http://tts:5002/v1" DOC_EXTRACTOR_URL="http://hermes:9998" ./ops/openwebui_setup.sh

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

# Wake-on-demand: list it for the waker (from its .env) and reload the waker so it starts watching it.
python3 ops/wake/stacks_add.py "$NAME"
systemctl --user restart aibridge-waker && echo "waker reloaded: $NAME sleeps after 10 idle minutes and wakes on use"
if [ "$NEW_STACK" = 1 ]; then
  cat <<NEXT

STILL TO DO BY HAND (needs root or another machine):
  1. sudo /usr/local/sbin/docker-user-fw.sh   (opens this stack's gateway:3099 to its own nginx only)
  2. edge VM: proxy https://$PUBLIC_HOST -> http://$LAN_IP:$WEB_PORT  (+ DNS and certificate)
NEXT
fi
