#!/bin/bash
# Create/update the "Hermes" model preset in Open WebUI: Hermes's API model plus a system prompt that
# tells it it is talking through the web UI (file paths, links, Mermaid, PDFs). Idempotent; run it on
# VM105 after the stack is up and whenever the prompt changes. Reads the admin password from .env.
set -euo pipefail
cd "$(dirname "$0")/.."
BASE="${OWUI_URL:-http://<docker-host-ip>:3000}"
PW="$(grep '^OPENWEBUI_ADMIN_PASSWORD=' .env | cut -d= -f2-)"

read -r -d '' SYSTEM <<'PROMPT' || true
Estás conversando con el usuario a través de la interfaz web (Open WebUI), NO por Telegram. Antes de manejar archivos, PDFs o diagramas, leé tu skill `web-interface`. Reglas esenciales:
- Los adjuntos no llegan como bytes: están en /openwebui-uploads/<id>_<nombre> (el id y el nombre vienen en el bloque <attached_files>). Andá directo a esa ruta, no busques en todo el disco.
- Para entregar un archivo: copialo a /web-outputs/<uuid>/<nombre> y respondé con un enlace markdown RELATIVO /hermes-files/<uuid>/<nombre>. Imágenes en línea: ![desc](/hermes-files/<uuid>/<nombre>). Nunca uses MEDIA: ni rutas locales como entregable.
- Diagramas: bloque ```mermaid (la interfaz lo dibuja). Entre comillas las etiquetas con paréntesis o símbolos.
- PDFs: leer con pdftotext/skill pdf; crear con pandoc --pdf-engine=weasyprint o reportlab. Verificá el PDF antes de decir que está listo.
- Respondé en el idioma del usuario y sé honesto sobre lo que tardan las tareas pesadas.
PROMPT

TOKEN="$(curl -fsS "$BASE/api/v1/auths/signin" -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"email":"admin@aibridge.local","password":sys.argv[1]}))' "$PW")" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')"

BODY="$(python3 - "$SYSTEM" <<'PY'
import json,sys
print(json.dumps({
  "id": "hermes",
  "base_model_id": "hermes-agent",
  "name": "Hermes",
  "meta": {"description": "Hermes Agent (archivos, PDF, diagramas Mermaid)", "capabilities": {"vision": False}},
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

# Open WebUI keeps the resolved model list in memory and only recomputes it when /api/models is requested;
# until then chat calls can fail with "Model not found" using the state from before this script ran.
curl -fsS -o /dev/null "$BASE/api/models" "${H[@]}" && echo "model list refreshed"
