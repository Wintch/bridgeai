#!/bin/bash
# Create (or re-print) a full per-person web stack on VM105: own Hermes + Open WebUI + nginx + TTS, own data and network.
#   ./ops/provision_stack.sh <name> [--public-host host] [--lang es|ru|en|auto] [--nim-key KEY] [--model provider/model-id]
#                                   [--telegram-token T --telegram-user ID] [--jobfinder bundle.tgz]
# --jobfinder: also install the clean job-search system (see make_jobfinder_bundle.sh / install_jobfinder.sh).
# The person gets: a web URL + admin login, a Hermes dashboard login (to pick the model and enter THEIR OWN keys).
# --nim-key: the person's key, or the operator's shared trial key (it writes workdir/.starter-key, so the welcome and the
# bot's first reply say it is shared and how to get their own). Telegram is optional; a bot can be added later with
# ops/stack_telegram.py, which reads the token from stdin (keeps it out of ps and shell history).
# Options are read only when the stack is new: on a re-run (its .env exists) they are ignored and the summary is re-printed
# (except --lang, --nim-key's .starter-key mark and --jobfinder, which act on every run). A re-run starts the stack and applies the Open
# WebUI preset again, so run it while nobody uses the stack; the script pauses the waker meanwhile so it does not stop it mid-run.
# The port to give to the edge VM is printed at the end (WEB_PORT).
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:-}"; shift || true
[[ "$NAME" =~ ^[a-z][a-z0-9]{1,19}$ ]] || { echo "usage: $0 <name: a-z0-9, 2-20 chars> [options]" >&2; exit 2; }
NIM_KEY=""; PROVIDER="nvidia"; MODEL="nvidia/nemotron-3.5-super-vl-120b-a12b"; TG_TOKEN=""; TG_USER=""; JOBFINDER=""; PUBLIC_HOST="$NAME.${PUBLIC_DOMAIN:-example.com}"  # export PUBLIC_DOMAIN (real domains are not kept in the repo)
while [ $# -gt 0 ]; do
  case "$1" in
    --public-host) PUBLIC_HOST="$2"; shift 2;;
    --nim-key) NIM_KEY="$2"; shift 2;;
    --model) PROVIDER="${2%%/*}"; MODEL="$2"; shift 2;;
    --telegram-token) TG_TOKEN="$2"; shift 2;;
    --telegram-user) TG_USER="$2"; shift 2;;
    --jobfinder) JOBFINDER="$2"; shift 2;;
    --lang) LANGV="$2"; shift 2;;       # es|ru|en|auto: the language the person speaks (fixed STT language and voice)
    *) echo "unknown option $1" >&2; exit 2;;
  esac
done
LAN_IP="${LAN_IP:-$(grep -m1 '^LAN_IP=' .env 2>/dev/null | cut -d= -f2)}"; : "${LAN_IP:?set LAN_IP (the host LAN address) in ~/aibridge/.env}"
DIR="$PWD/stacks/$NAME"; ENVF="$DIR/.env"
COMPOSE=(docker compose -p "stack-$NAME" -f stacks/docker-compose.stack.yml -f stacks/hardening.override.yml --env-file "$ENVF")

if [ ! -f "$ENVF" ]; then
  case "$PUBLIC_HOST" in *.example.com) echo "WARNING: PUBLIC_HOST is the placeholder $PUBLIC_HOST (no PUBLIC_DOMAIN exported, no --public-host). Open WebUI's CORS_ALLOW_ORIGIN and the name for the edge VM will be wrong: stop and re-run with one of them, or fix PUBLIC_HOST in $ENVF and recreate open-webui." >&2;; esac
  mkdir -p "$DIR/persist" "$DIR/workdir" "$DIR/videos" "$DIR/owui-data/uploads" "$DIR/web-outputs"
  chmod 755 "$DIR/web-outputs"
  # Wake-on-demand: nginx of this stack hands visits to the waker bound to the stack's network gateway (port 3099).
  mkdir -p "$DIR/wake"
  . ops/lib/alloc.sh   # subnet and ports shared with guests, never colliding
  n=$(alloc_subnet)
  # umask 077 ONLY for the .env (secrets). It used to stay on for the rest of the script, so everything made after it (gateways/,
  # voice/, what the child scripts create) came out 0700/0600 by accident; a reader without DAC_OVERRIDE (nginx with cap_drop ALL) then
  # got "Permission denied" on a file it was meant to read (wake/upstream.conf, 2026-11-05).
  ( umask 077; cat > "$ENVF" ) <<ENV
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
  chmod 644 "$DIR/wake/upstream.conf"   # explicit: nginx (cap_drop ALL, no DAC_OVERRIDE) must be able to read it
  echo "created $ENVF"
  NEW_STACK=1
else
  echo "stack '$NAME' already exists, (re)starting with its saved settings"
fi

NEW_STACK="${NEW_STACK:-0}"
# gateways/ is bind-mounted into Hermes (read-only): create it here so compose does not create it as root.
mkdir -p "$DIR/gateways" "$DIR/voice"
chmod 755 "$DIR/gateways" "$DIR/voice"   # explicit; they hold URLs and model names, no secrets (checked 2026-11-05)
# voice/gateways.json (the GPU audio hosts of this person) comes from the master: put "voice": [...] for $NAME in ops/gateways.json and run ops/gateways_sync.py
# `deliver <file>` (web-interface skill) is part of every stack, not only job-search ones; refreshed on every run.
install -m 755 ops/deliver "$DIR/workdir/deliver" || echo "warning: could not install ops/deliver into $DIR/workdir" >&2
# --nim-key = the operator'"'"'s shared key: mark the stack so the welcome banner (ops/welcome_starter.<lang>.md) and the job-search skill
# (first reply on Telegram) tell the person it is a shared trial key and how to get their own. Removing the file stops both.
[ -n "$NIM_KEY" ] && date +%F > "$DIR/workdir/.starter-key"
[ -n "$JOBFINDER" ] && ./ops/install_jobfinder.sh "$NAME" "$JOBFINDER"
"${COMPOSE[@]}" config -q
# Re-running this on a stack the waker already knows races with it: it saw the stack idle and stopped Open WebUI and Hermes in the
# middle of openwebui_setup.sh/stack_voice.sh (2026-11-05, "curl: (22) ... 503"). Pause the waker for the run; the EXIT trap starts it
# again however the script ends (the normal path also restarts it at the end, below, to pick up stacks.json).
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ "$NEW_STACK" = 0 ] && systemctl --user is-active --quiet aibridge-waker; then
  trap 'systemctl --user start aibridge-waker >/dev/null 2>&1 || true' EXIT
  systemctl --user stop aibridge-waker && echo "waker paused for this run (it comes back when the script ends)"
fi
"${COMPOSE[@]}" up -d 2>&1 | tail -5
set -a; . "$ENVF"; set +a
WEB_UP=0
echo -n "waiting for the web UI"; for i in $(seq 1 60); do
  [ "$(curl -s -m2 -o /dev/null -w %{http_code} "http://$LAN_IP:$WEB_PORT/health")" = 200 ] && { echo " up after ~$((i*3))s"; WEB_UP=1; break; }; echo -n .; sleep 3; done
# openwebui_setup.sh signs in with curl -fsS and has no wait of its own: going on without the UI only ends in a cryptic curl error.
# Nothing is lost by stopping here: re-running the script re-uses the saved .env.
[ "$WEB_UP" = 1 ] || { echo; echo "ERROR: the web UI at http://$LAN_IP:$WEB_PORT did not answer /health in 180 s: stopping before the Open WebUI preset. Look at: docker compose -p stack-$NAME ps ; docker logs stack-$NAME-open-webui ; then re-run this script." >&2; exit 1; }

# Same preset as the main stack (system prompt for files/PDF/Mermaid, vision, private model, voice).
JOBS=$([ -n "$JOBFINDER" ] && echo 1 || echo 0) WELCOME=1 WELCOME_LANG="$([ "${LANGV:-}" = ru ] && echo ru || echo es)" OWUI_URL="http://$LAN_IP:$WEB_PORT" ENV_FILE="$ENVF" ADMIN_EMAIL="$ADMIN_EMAIL" TTS_URL="http://voice:8650/v1" STT_URL="http://voice:8650/v1" DOC_EXTRACTOR_URL="http://hermes:9998" ./ops/openwebui_setup.sh

[ -n "${LANGV:-}" ] && ./ops/stack_voice.sh "$NAME" --lang "$LANGV"

cat > "$DIR/credentials.txt" <<CRED
Stack for: $NAME
Web UI (give THIS to the edge VM):  http://$LAN_IP:$WEB_PORT      public name: https://$PUBLIC_HOST
  login:   $ADMIN_EMAIL   password: $OPENWEBUI_ADMIN_PASSWORD
Hermes dashboard (model + keys):    http://$LAN_IP:$DASH_PORT   user: $DASH_USER   password: $DASH_PASSWORD
Starting model: $HERMES_MODEL_DEFAULT (provider $HERMES_MODEL_PROVIDER)
LLM key: $([ -n "$NVIDIA_API_KEY" ] && echo "provided (the operator's shared key: .starter-key marks it, the person is told to get their own)" || echo "NONE yet: the person enters their own (NVIDIA NIM free) in the dashboard")
Telegram: $([ -n "$TELEGRAM_BOT_TOKEN" ] && echo enabled || echo "not enabled (optional)")
CRED
chmod 600 "$DIR/credentials.txt"; cat "$DIR/credentials.txt"

# Wake-on-demand: list it for the waker (from its .env) and reload the waker so it starts watching it.
python3 ops/wake/stacks_add.py "$NAME"
python3 -m json.tool ops/wake/stacks.json > /dev/null || { echo "ops/wake/stacks.json is not valid JSON: NOT restarting the waker (it would drop every stack). Fix it, then: systemctl --user restart aibridge-waker" >&2; exit 1; }
# Over a non-login ssh XDG_RUNTIME_DIR may be unset; a failed restart must not hide the "still to do" list below (set -e)
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if systemctl --user restart aibridge-waker; then echo "waker reloaded: $NAME sleeps after 10 idle minutes and wakes on use"
else echo "WARNING: could not restart the waker: run  systemctl --user restart aibridge-waker  yourself" >&2; fi
# A stack created after docker-user-fw.service last loaded has no firewall pinhole to its waker, and nothing says so: hertin's wake
# page timed out (504) for days (2026-11-02..05). Probe the waker from the stack's own nginx. curl exit codes tell the cases apart:
# 0 answered (any HTTP status), 28 timeout = the INPUT DROP for guests = no pinhole, 7 refused = the waker is still binding its port
# (the packet got through: retry), anything else = could not probe. (aibridge has no root: the fix is
# `sudo systemctl restart docker-user-fw.service`, step 1 below.)
WAKER_URL=$(sed -E 's/.*(http[^;]+);.*/\1/' "$DIR/wake/upstream.conf")
for _ in 1 2 3 4 5; do
  sleep 2; WAKER_RC=0
  docker exec "stack-$NAME-web" curl -s -m 4 -o /dev/null "$WAKER_URL/" >/dev/null 2>&1 || WAKER_RC=$?
  [ "$WAKER_RC" = 7 ] || break
done
case "$WAKER_RC" in
  0) ;;
  28) echo "WARNING: $NAME's nginx cannot reach its waker ($WAKER_URL): the firewall has no pinhole for this stack yet, so its wake page times out (504)." >&2
      echo "         Needs root on VM105:  sudo systemctl restart docker-user-fw.service" >&2;;
  7) echo "WARNING: the waker is not listening on $WAKER_URL (connection refused after 5 tries): check  systemctl --user status aibridge-waker" >&2;;
  *) echo "WARNING: could not probe the waker of $NAME (exit $WAKER_RC): is stack-$NAME-web running?" >&2;;
esac
if [ "$NEW_STACK" = 1 ]; then
  cat <<NEXT

STILL TO DO BY HAND (needs root or another machine):
  1. sudo systemctl restart docker-user-fw.service   (opens this stack's gateway:3099 to its own nginx only; the check above says if it is still missing)
  2. edge VM: proxy https://$PUBLIC_HOST -> http://$LAN_IP:$WEB_PORT  (+ DNS and certificate)
NEXT
fi
