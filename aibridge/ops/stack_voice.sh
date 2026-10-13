#!/bin/bash
# Voice settings of one per-person stack, run on VM105 from ~/aibridge (2026-10-13).
#
#   ops/stack_voice.sh NAME --lang es|ru|en|auto [--home]
#
#   --lang  the language this person uses. A one-language person gets a FIXED speech-to-text language (no auto-detection to
#           get wrong on a short clip) and a FIXED voice for the replies; auto = all three (hernik). Written to the stack's
#           .env (STT_LANG, TTS_VOICE) and to Open WebUI's voice config.
#   --home  also run the stack's voice-proxy: speech-to-text and spoken replies on the home GPU hosts (the master's "voice"
#           list for this stack, ops/gateways_sync.py), the stack's own Piper as the fallback. A guest network cannot reach
#           the LAN: this refuses to switch while the stack cannot reach those hosts (add the GUEST_PINHOLES lines it prints,
#           then run it again). Without --home the stack keeps its local Piper and the browser's recognition.
#
# Open WebUI running: the config goes through its API (ops/openwebui_setup.sh). Asleep: the same keys are written straight
# into its webui.db (it only reads them at start), so the stack is not woken for this. Safe to repeat.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:?usage: ops/stack_voice.sh NAME --lang es|ru|en|auto [--home]}"; shift
LANGV=""; HOME_VOICE=0
while [ $# -gt 0 ]; do case "$1" in
  --lang) LANGV="$2"; shift 2;; --home) HOME_VOICE=1; shift;; *) echo "unknown option $1" >&2; exit 2;; esac; done
case "$LANGV" in es|ru|en|auto) ;; *) echo "--lang es|ru|en|auto is required" >&2; exit 2;; esac
DIR="$PWD/stacks/$NAME"; ENVF="$DIR/.env"; [ -f "$ENVF" ] || { echo "no such stack: $NAME" >&2; exit 1; }
# Voices chosen for the stack's OWN Piper (1 CPU, the fallback and, until the firewall lets a GPU host through, the only
# voice). Measured 2026-10-13 as seconds of synthesis per second of audio: es_MX-claude-high 0.89, es_AR-daniela-high 3.88
# (!), es_ES/es_MX medium 0.65, ru_RU-irina 0.71, dmitri 1.14, denis 1.05, ruslan 1.20. A GPU host that lacks the name
# picks its own voice by the text's language. Override with VOICE_ES / VOICE_RU / VOICE_EN.
declare -A VOICE=([es]="${VOICE_ES:-es_MX-claude-high}" [ru]="${VOICE_RU:-ru_RU-irina-medium}" [en]="${VOICE_EN:-en_US-lessac-medium}")
if [ "$LANGV" = auto ]; then STT_LANG=""; TTS_VOICE=""; else STT_LANG="$LANGV"; TTS_VOICE="${VOICE[$LANGV]}"; fi

setenv() { grep -q "^$1=" "$ENVF" && sed -i "s|^$1=.*|$1=$2|" "$ENVF" || echo "$1=$2" >> "$ENVF"; }
COMPOSE=(docker compose -p "stack-$NAME" -f stacks/docker-compose.stack.yml --env-file "$ENVF")
NET="stack-${NAME}_default"

if [ "$HOME_VOICE" = 1 ]; then
  VG="$DIR/voice/gateways.json"
  [ -s "$VG" ] || { echo "no $VG: put \"voice\": [\"<host>\"] for $NAME in ops/gateways.json and run python3 ops/gateways_sync.py" >&2; exit 1; }
  bad=0
  while read -r kind name url; do
    out="$(docker run --rm --network "$NET" python:3.12-slim python3 -c '
import sys,urllib.request
try: urllib.request.urlopen(sys.argv[1].rstrip("/")+"/healthz",timeout=4); print("ok")
except Exception as e: print(type(e).__name__)' "$url" 2>&1 | tail -1)"
    if [ "$out" = ok ]; then echo "reachable from $NET: $kind $name"
    else
      hp="${url#http://}"; hp="${hp%/}"
      echo "NOT reachable from $NET: $kind $name ($out). Needs a GUEST_PINHOLES line in /etc/default/aibridge-fw: \"$(docker network inspect "$NET" -f '{{(index .IPAM.Config 0).Subnet}}') ${hp%%:*} ${hp##*:}\"" >&2; bad=1
    fi
  done < <(python3 -c '
import json,sys
for k,v in json.load(open(sys.argv[1])).items():
    for h in v: print(k,h["name"],h["url"])' "$VG")
  [ "$bad" = 0 ] || { echo "not switching $NAME to the home voice-proxy: the firewall still blocks it (language settings below are applied anyway)" >&2; HOME_VOICE=0; }
fi

setenv STT_LANG "$STT_LANG"; setenv TTS_VOICE "$TTS_VOICE"
if [ "$HOME_VOICE" = 1 ]; then
  setenv COMPOSE_PROFILES voice
  "${COMPOSE[@]}" create voice 2>&1 | grep -v "variable is not set" | tail -2     # the waker starts it with the stack
  python3 - "$NAME" <<'PY'
import json,sys,os
p="ops/wake/stacks.json"; c=json.load(open(p)); n=sys.argv[1]
for s in c["stacks"]:
    if s["name"]==n and f"stack-{n}-voice" not in s["web"]:
        s["web"].append(f"stack-{n}-voice"); print("stacks.json: waker will start/stop stack-%s-voice with the web" % n)
json.dump(c,open(p+".tmp","w"),indent=2); os.replace(p+".tmp",p)
PY
  systemctl --user restart aibridge-waker
  STT_URL="http://voice:8650/v1"; TTS_URL="http://voice:8650/v1"
else
  sed -i '/^COMPOSE_PROFILES=/d' "$ENVF"
  STT_URL=""; TTS_URL="http://tts:5002/v1"
fi

WEB="stack-$NAME-open-webui"
if [ "$(docker inspect -f '{{.State.Running}}' "$WEB" 2>/dev/null)" = true ]; then
  set -a; . "$ENVF"; set +a
  ENV_FILE="$ENVF" ADMIN_EMAIL="$ADMIN_EMAIL" OWUI_URL="http://$LAN_IP:$WEB_PORT" TTS_URL="$TTS_URL" STT_URL="$STT_URL" \
    TTS_VOICE="${TTS_VOICE:-auto}" ./ops/openwebui_setup.sh | grep -i "voice config"
else
  docker run --rm -i -v "$DIR/owui-data:/d" python:3.12-slim python3 - "$STT_URL" "$TTS_URL" "${TTS_VOICE:-auto}" <<'PY'
import sqlite3,json,shutil,sys,time
stt,tts,voice=sys.argv[1:4]
shutil.copy2("/d/webui.db",f"/d/webui.db.bak-{time.strftime('%Y%m%d')}")
d=sqlite3.connect("/d/webui.db")
def put(k,v):
    d.execute("insert into config(key,value,updated_at) values(?,?,?) on conflict(key) do update set value=excluded.value,updated_at=excluded.updated_at",(k,json.dumps(v),int(time.time())))
put("audio.tts.engine","openai"); put("audio.tts.openai.api_base_url",tts); put("audio.tts.openai.api_key","local")
put("audio.tts.model","tts-1"); put("audio.tts.voice",voice); put("audio.tts.split_on","punctuation")
if stt:
    put("audio.stt.engine","openai"); put("audio.stt.openai.api_base_url",stt); put("audio.stt.openai.api_key","local"); put("audio.stt.model","whisper-1")
else:
    put("audio.stt.engine",""); put("audio.stt.openai.api_key","")
d.commit(); print("voice config written to the stopped Open WebUI database: stt=%s tts=%s voice=%s" % (stt or "browser",tts,voice))
PY
fi
echo "$NAME: language ${LANGV}, voice ${TTS_VOICE:-auto}, $([ "$HOME_VOICE" = 1 ] && echo "home voice-proxy" || echo "local Piper + browser recognition")"
