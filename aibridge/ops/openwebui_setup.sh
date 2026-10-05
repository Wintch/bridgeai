#!/bin/bash
# Create/update the "Hermes" model preset in Open WebUI: Hermes's API model plus a system prompt that
# tells it it is talking through the web UI (file paths, links, Mermaid, PDFs). Idempotent; run it on
# VM105 after the stack is up and whenever the prompt changes. Reads the admin password from .env.
set -euo pipefail
cd "$(dirname "$0")/.."
# Defaults = the main (hernik) stack. A per-person stack (ops/provision_stack.sh) overrides these.
BASE="${OWUI_URL:-http://<docker-host-ip>:3000}"
ENV_FILE="${ENV_FILE:-.env}"                       # file holding OPENWEBUI_ADMIN_PASSWORD (and optionally GROQ_API_KEY)
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@aibridge.local}"
TTS_URL="${TTS_URL:-http://tts-piper:5002/v1}"     # OpenAI-compatible TTS reachable from inside Open WebUI
PW="$(grep '^OPENWEBUI_ADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"

read -r -d '' SYSTEM <<'PROMPT' || true
Estás conversando con el usuario a través de la interfaz web (Open WebUI), NO por Telegram. Antes de manejar archivos, PDFs o diagramas, leé tu skill `web-interface`. Reglas esenciales:
- Los adjuntos no llegan como bytes: están en /openwebui-uploads/<id>_<nombre> (el id y el nombre vienen en el bloque <attached_files>). Andá directo a esa ruta, no busques en todo el disco.
- Para entregar un archivo: copialo a /web-outputs/<uuid>/<nombre> y respondé con un enlace markdown RELATIVO /hermes-files/<uuid>/<nombre>. Imágenes en línea: ![desc](/hermes-files/<uuid>/<nombre>). Nunca uses MEDIA: ni rutas locales como entregable.
- Diagramas: bloque ```mermaid (la interfaz lo dibuja). Entre comillas las etiquetas con paréntesis o símbolos.
- PDFs: leer con pdftotext/skill pdf; crear con pandoc --pdf-engine=weasyprint o reportlab. Verificá el PDF antes de decir que está listo.
- Respondé en el idioma del usuario y sé honesto sobre lo que tardan las tareas pesadas.
PROMPT

# Job-search stacks (JOBS=1, set by provision_stack.sh --jobfinder): steer Hermes to the right tools right away. Without this
# it loaded no skill, tried blocked tools first (Cloudflare on ZonaJobs) and took 237s for a 3-result request.
if [ "${JOBS:-0}" = 1 ]; then
  read -r -d '' JOBS_TXT <<'JOBSPROMPT' || true
- Si el pedido es sobre buscar trabajo, ofertas, CV, postulaciones o entrevistas: cargá primero tu skill `job-search` y seguila.
- Para BUSCAR ofertas ejecutá SIEMPRE en la terminal: `buscar-empleos "<palabras>" [--zona "<texto>"]` (ZonaJobs, Bumeran, Computrabajo y LinkedIn en ~25 s). Para leer una oferta completa: `browse-page <url> --max 6000`. No uses web_extract ni browser_* con portales de empleo (Cloudflare los bloquea y tardás minutos). Nunca digas que falta una clave de API para leer un sitio sin haber probado estos comandos.
JOBSPROMPT
  SYSTEM="$SYSTEM"$'\n'"$JOBS_TXT"
fi

TOKEN="$(curl -fsS "$BASE/api/v1/auths/signin" -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"email":sys.argv[1],"password":sys.argv[2]}))' "$ADMIN_EMAIL" "$PW")" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')"

BODY="$(python3 - "$SYSTEM" <<'PY'
import json,sys
print(json.dumps({
  "id": "hermes",
  "base_model_id": "hermes-agent",
  "name": "Hermes",
  "meta": {"description": "Hermes Agent (archivos, PDF, imágenes, diagramas Mermaid)",
           # vision must be True or the UI hides image attachments. Hermes's API takes image_url parts and
           # describes them (tested 2026-10-04: read text + shapes from a PNG in 8s).
           "capabilities": {"vision": True, "file_upload": True, "usage": False}},
  "params": {"system": sys.argv[1]},
  "is_active": True,
  # PRIVATE: admins only until a user/group is granted access in Open WebUI. The web UI is reachable from
  # the internet and Hermes can run commands and holds the API keys, so a new account must NOT get it by default.
  "access_control": {"read": {"group_ids": [], "user_ids": []}, "write": {"group_ids": [], "user_ids": []}},
}))
PY
)"

H=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
code="$(curl -sS -o /tmp/owui_model.json -w '%{http_code}' "$BASE/api/v1/models/create" "${H[@]}" -d "$BODY")"
if [ "$code" != 200 ]; then
  # already exists -> update
  code="$(curl -sS -o /tmp/owui_model.json -w '%{http_code}' "$BASE/api/v1/models/model/update?id=hermes" "${H[@]}" -d "$BODY")"
fi
echo "model preset 'hermes': HTTP $code"
[ "$code" = 200 ]

# Hide the raw base model from the selector: without the preset's system prompt Hermes doesn't know it
# is on the web UI. It must stay ACTIVE (meta.hidden only hides it): an inactive base model is dropped
# from the model list entirely and the "hermes" preset that points at it stops resolving
# ("Model not found"), as found the hard way on 2026-10-04.
HIDE='{"id":"hermes-agent","base_model_id":null,"name":"hermes-agent","meta":{"hidden":true},"params":{},"is_active":true,"access_control":{"read":{"group_ids":[],"user_ids":[]},"write":{"group_ids":[],"user_ids":[]}}}'
code="$(curl -sS -o /tmp/owui_model.json -w '%{http_code}' "$BASE/api/v1/models/create" "${H[@]}" -d "$HIDE")"
if [ "$code" != 200 ]; then
  code="$(curl -sS -o /tmp/owui_model.json -w '%{http_code}' "$BASE/api/v1/models/model/update?id=hermes-agent" "${H[@]}" -d "$HIDE")"
fi
echo "base model hidden: HTTP $code"
[ "$code" = 200 ]

# These settings live in Open WebUI's database after first boot, so the DEFAULT_MODELS /
# ENABLE_EVALUATION_ARENA_MODELS env vars are ignored once it has started once: set them via the API.
code="$(curl -sS -o /tmp/owui_model.json -w '%{http_code}' "$BASE/api/v1/configs/models" "${H[@]}" \
  -d '{"DEFAULT_MODELS":"hermes","DEFAULT_PINNED_MODELS":"hermes","MODEL_ORDER_LIST":["hermes"]}')"
echo "default model = hermes: HTTP $code"; [ "$code" = 200 ]
code="$(curl -sS -o /tmp/owui_model.json -w '%{http_code}' "$BASE/api/v1/evaluations/config" "${H[@]}" \
  -d '{"ENABLE_EVALUATION_ARENA_MODELS":false,"EVALUATION_ARENA_MODELS":[]}')"
echo "arena models off: HTTP $code"; [ "$code" = 200 ]

# PDF/DOCX uploads: Open WebUI "slim" has no extractor and answers 503 ("requires an external document extractor").
# DOC_EXTRACTOR_URL points at doc_extractor.py (tika protocol, runs inside the Hermes container of the stack).
# Indexing/embedding stays off: Hermes opens the real file itself (see the web-interface skill).
if [ -n "${DOC_EXTRACTOR_URL:-}" ]; then
  code="$(curl -sS -o /tmp/owui_model.json -w '%{http_code}' "$BASE/api/v1/retrieval/config/update" "${H[@]}" \
    -d "{\"CONTENT_EXTRACTION_ENGINE\":\"tika\",\"TIKA_SERVER_URL\":\"$DOC_EXTRACTOR_URL\",\"BYPASS_EMBEDDING_AND_RETRIEVAL\":true}")"
  echo "document extractor ($DOC_EXTRACTOR_URL): HTTP $code"; [ "$code" = 200 ]
fi

# Open WebUI keeps the resolved model list in memory and only recomputes it when /api/models is requested;
# until then chat calls can fail with "Model not found" using the state from before this script ran.
curl -fsS -o /dev/null "$BASE/api/models" "${H[@]}" && echo "model list refreshed"

# Voice mode ("Call" button): needs HTTPS in the browser (mic), which the edge provides.
#   TTS: local Piper container (internal network). STT: Groq's OpenAI-compatible Whisper when GROQ_API_KEY is in
#   ENV_FILE (audio of web users goes to Groq); otherwise the browser's own speech recognition (no key, nothing leaves
#   the stack). A per-person stack must NOT carry the operator's Groq key: its admin could read it from Open WebUI.
GROQ_KEY="$(grep '^GROQ_API_KEY=' "$ENV_FILE" | cut -d= -f2- || true)"
CUR="$(curl -fsS "$BASE/api/v1/audio/config" "${H[@]}")"
NEW="$(GROQ_KEY="$GROQ_KEY" TTS_URL="$TTS_URL" python3 -c '
import json,os,sys
c=json.loads(sys.stdin.read())
c["tts"].update({"ENGINE":"openai","OPENAI_API_BASE_URL":os.environ["TTS_URL"],"OPENAI_API_KEY":"local",
                 "MODEL":"tts-1","VOICE":"es_MX-claude-high","SPLIT_ON":"punctuation"})
if os.environ["GROQ_KEY"]:
    c["stt"].update({"ENGINE":"openai","OPENAI_API_BASE_URL":"https://api.groq.com/openai/v1",
                     "OPENAI_API_KEY":os.environ["GROQ_KEY"],"MODEL":"whisper-large-v3-turbo"})
else:
    c["stt"].update({"ENGINE":"","OPENAI_API_KEY":""})
print(json.dumps({"tts":c["tts"],"stt":c["stt"]}))' <<<"$CUR")"
code="$(curl -sS -o /tmp/owui_model.json -w '%{http_code}' "$BASE/api/v1/audio/config/update" "${H[@]}" -d "$NEW")"
echo "voice config ($([ -n "$GROQ_KEY" ] && echo Groq || echo browser) STT + Piper TTS): HTTP $code"; [ "$code" = 200 ]

# Open WebUI keeps the resolved model list in memory and only recomputes it when /api/models is requested;
# until then chat calls can fail with "Model not found" using the state from before this script ran.
curl -fsS -o /dev/null "$BASE/api/models" "${H[@]}" && echo "model list refreshed"

# Welcome banner (only for per-person stacks: WELCOME=1): where to get a key, where to paste it, what happens next.
# Text lives in ops/welcome.es.md. Dismissible, so it greets without nagging.
if [ "${WELCOME:-0}" = 1 ]; then
  BANNERS="$(python3 - "$(dirname "$0")/welcome.es.md" <<'PY'
import json,sys,time
print(json.dumps({"banners":[{"id":"bienvenida","type":"info","title":"👋 Bienvenido/a a tu Hermes","content":open(sys.argv[1],encoding="utf-8").read(),"dismissible":True,"timestamp":int(time.time())}]}))
PY
)"
  code="$(curl -sS -o /tmp/owui_model.json -w '%{http_code}' "$BASE/api/v1/configs/banners" "${H[@]}" -d "$BANNERS")"
  echo "welcome banner: HTTP $code"; [ "$code" = 200 ]
fi
