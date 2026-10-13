#!/bin/bash
# The language one person speaks, applied to their stack's voice (run on VM105 from ~/aibridge). 2026-10-13.
#
#   ops/stack_voice.sh NAME --lang es|ru|en|auto
#
# A one-language person gets a FIXED speech-to-text language (no auto-detection to get wrong on a short clip) and a FIXED
# voice for the replies; auto = all three (hernik). Written to the stack's .env (STT_LANG, TTS_VOICE, read by its
# `voice` container) and to Open WebUI's voice config. Every stack's voice goes through its own `voice` container (the
# voice-proxy of stt/proxy.py) to the home GPU hosts listed under "voice" for it in ops/gateways.json: that container
# has a second foot in hernik's network, the only way a guest network reaches the LAN. SPEECH NEVER RUNS ON THIS VM'S
# CPU (operator rule, 2026-10-13): no local Piper, no CPU Whisper; with every GPU host down the call fails clearly.
#
# Open WebUI running: the config goes through its API (ops/openwebui_setup.sh). Asleep: the same keys are written straight
# into its webui.db (it only reads them at start), so the stack is not woken for this. Safe to repeat.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:?usage: ops/stack_voice.sh NAME --lang es|ru|en|auto}"; shift
LANGV=""
while [ $# -gt 0 ]; do case "$1" in --lang) LANGV="$2"; shift 2;; *) echo "unknown option $1" >&2; exit 2;; esac; done
case "$LANGV" in es|ru|en|auto) ;; *) echo "--lang es|ru|en|auto is required" >&2; exit 2;; esac
DIR="$PWD/stacks/$NAME"; ENVF="$DIR/.env"; [ -f "$ENVF" ] || { echo "no such stack: $NAME" >&2; exit 1; }
[ -s "$DIR/voice/gateways.json" ] || echo "warning: no $DIR/voice/gateways.json: put \"voice\": [\"gpu-desktop\"] for $NAME in ops/gateways.json and run python3 ops/gateways_sync.py (its voice container has no host until then)" >&2
# Voices the GPU hosts' Piper has (all four Russian and all Spanish ones are in its image). Override with VOICE_ES / VOICE_RU / VOICE_EN.
declare -A VOICE=([es]="${VOICE_ES:-es_AR-daniela-high}" [ru]="${VOICE_RU:-ru_RU-irina-medium}" [en]="${VOICE_EN:-en_US-lessac-medium}")
if [ "$LANGV" = auto ]; then STT_LANG=""; TTS_VOICE=""; else STT_LANG="$LANGV"; TTS_VOICE="${VOICE[$LANGV]}"; fi

setenv() { grep -q "^$1=" "$ENVF" && sed -i "s|^$1=.*|$1=$2|" "$ENVF" || echo "$1=$2" >> "$ENVF"; }
setenv STT_LANG "$STT_LANG"; setenv TTS_VOICE "$TTS_VOICE"
sed -i '/^COMPOSE_PROFILES=/d' "$ENVF"      # the voice container is part of every stack now, no profile
COMPOSE=(docker compose -p "stack-$NAME" -f stacks/docker-compose.stack.yml --env-file "$ENVF")
VURL="http://voice:8650/v1"

WEB="stack-$NAME-open-webui"
if [ "$(docker inspect -f '{{.State.Running}}' "$WEB" 2>/dev/null)" = true ]; then
  "${COMPOSE[@]}" up -d --no-deps voice 2>&1 | grep -v "variable is not set" | tail -2   # picks up the new language
  set -a; . "$ENVF"; set +a
  ENV_FILE="$ENVF" ADMIN_EMAIL="$ADMIN_EMAIL" OWUI_URL="http://$LAN_IP:$WEB_PORT" TTS_URL="$VURL" STT_URL="$VURL" \
    TTS_VOICE="${TTS_VOICE:-auto}" ./ops/openwebui_setup.sh | grep -i "voice config"
else
  "${COMPOSE[@]}" create voice 2>&1 | grep -v "variable is not set" | tail -2            # the waker starts it with the stack
  docker run --rm -i -v "$DIR/owui-data:/d" python:3.12-slim python3 - "$VURL" "${TTS_VOICE:-auto}" <<'PY'
import sqlite3,json,shutil,sys,time
url,voice=sys.argv[1:3]
shutil.copy2("/d/webui.db",f"/d/webui.db.bak-{time.strftime('%Y%m%d')}")
d=sqlite3.connect("/d/webui.db")
def put(k,v):
    d.execute("insert into config(key,value,updated_at) values(?,?,?) on conflict(key) do update set value=excluded.value,updated_at=excluded.updated_at",(k,json.dumps(v),int(time.time())))
put("audio.tts.engine","openai"); put("audio.tts.openai.api_base_url",url); put("audio.tts.openai.api_key","local")
put("audio.tts.model","tts-1"); put("audio.tts.voice",voice); put("audio.tts.split_on","punctuation")
put("audio.stt.engine","openai"); put("audio.stt.openai.api_base_url",url); put("audio.stt.openai.api_key","local"); put("audio.stt.model","whisper-1")
d.commit(); print("voice config written to the stopped Open WebUI database: voice-proxy at %s, voice %s" % (url,voice))
PY
fi
# The waker starts and stops the voice container with the web: make sure it is in the stack's list (idempotent).
python3 - "$NAME" <<'PY'
import json,sys,os
p="ops/wake/stacks.json"; c=json.load(open(p)); n=sys.argv[1]; changed=False
for s in c["stacks"]:
    if s["name"]==n:
        if f"stack-{n}-voice" not in s["web"]: s["web"].append(f"stack-{n}-voice"); changed=True
        if f"stack-{n}-tts" in s["web"]: s["web"].remove(f"stack-{n}-tts"); changed=True
if changed:
    json.dump(c,open(p+".tmp","w"),indent=2); os.replace(p+".tmp",p); print("stacks.json updated for",n)
PY
echo "$NAME: language ${LANGV}, voice ${TTS_VOICE:-auto}"
