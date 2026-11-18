#!/bin/bash
# Create/update the "Hermes" model preset in Open WebUI: Hermes's API model plus a system prompt that
# tells it it is talking through the web UI (file paths, links, Mermaid, PDFs). Idempotent; run it on
# The Docker host after the stack is up and whenever the prompt changes. Reads the admin password from .env.
set -euo pipefail
umask 077
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/.."
# Defaults = the main (hernik) stack. A per-person stack (ops/provision_stack.sh) overrides these.
LAN_IP="${LAN_IP:-$(grep -m1 '^LAN_IP=' .env 2>/dev/null | cut -d= -f2)}"
BASE="${OWUI_URL:-http://${LAN_IP:?set OWUI_URL or LAN_IP}:3000}"
ENV_FILE="${ENV_FILE:-.env}"                       # file holding OPENWEBUI_ADMIN_PASSWORD (and optionally GROQ_API_KEY)
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@aibridge.local}"
TTS_URL="${TTS_URL:-http://voice-proxy:8650/v1}"   # OpenAI-compatible TTS reachable from inside Open WebUI (home GPU, local Piper as fallback)
TTS_VOICE="${TTS_VOICE:-auto}"                      # auto = by the text's language; a one-language person gets a fixed voice (ops/stack_voice.sh)
STT_URL="${STT_URL-http://voice-proxy:8650/v1}"      # OpenAI-compatible STT (home hosts); STT_URL="" = no home STT (per-person stacks)
PW="$(grep '^OPENWEBUI_ADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"

read -r -d '' SYSTEM <<'PROMPT' || true
You are talking to the user through the web interface (Open WebUI), NOT through Telegram. Before handling files, PDFs or diagrams, read your skill `web-interface`. Essential rules:
- Attachments do not arrive as bytes: they are in /openwebui-uploads/<id>_<name> (the id and the name come in the <attached_files> block). Go straight to that path, do not search the whole disk.
- To deliver a file: copy it to /web-outputs/<uuid>/<name> and answer with a RELATIVE markdown link /hermes-files/<uuid>/<name>. Inline images: ![desc](/hermes-files/<uuid>/<name>). Never use MEDIA: or local paths as the deliverable.
- Diagrams: a ```mermaid block (the interface draws it). Quote labels that contain parentheses or symbols.
- PDFs: read with pdftotext/the pdf skill; create with pandoc --pdf-engine=weasyprint or reportlab. Check the PDF before saying it is ready.
- Answer in the user's language and be honest about how long heavy tasks take. If the user writes in Spanish, address them informally in Rioplatense voseo (vos tenés, podés, mirá, dale; never tú or usted), warm and direct, without detours or formalities.
- You are a trusted assistant for this person: do the work instead of explaining why you could not. You can use the terminal, run code, browse the internet and handle files freely.
- The person has NO terminal in this chat: never ask them to run `hermes ...` commands, or to paste keys or passwords into the conversation. Keys are added on the /keys/ page of this same website.
- Those paths are WHERE the files are, NOT a limit on what you can do. You have internet: web_search, web_extract and curl work from your terminal (and `browse-page <url>` if it exists in this container). Never say you cannot access the internet or external domains; if a site blocks you, say which one and what you tried.
- A link /hermes-files/<id>/<file> that the user gives you is only the web URL of that file (the public address asks for login and answers 401: do not open it). On disk it is /web-outputs/<id>/<file>: read it from there. If it is gone (it is deleted after ~24 h), ask them to upload it again.
PROMPT

# Job-search stacks (JOBS=1, set by provision_stack.sh --jobfinder): steer Hermes to the right tools right away. Without this
# it loaded no skill, tried blocked tools first (Cloudflare on ZonaJobs) and took 237s for a 3-result request.
if [ "${JOBS:-0}" = 1 ]; then
  read -r -d '' JOBS_TXT <<'JOBSPROMPT' || true
- If the request is about looking for work, job ads, a CV, applications or interviews: first load your skill `job-search` and follow it.
- To SEARCH for ads ALWAYS run in the terminal: `buscar-empleos "<words>" [--zona "<text>"]` (ZonaJobs, Bumeran, Computrabajo and LinkedIn in ~25 s). To read a full ad: `browse-page <url> --max 6000`. Do not use web_extract or browser_* with job portals (Cloudflare blocks them and you take minutes). Never say that an API key is missing to read a site without having tried these commands.
JOBSPROMPT
  SYSTEM="$SYSTEM"$'\n'"$JOBS_TXT"
  # Each Open WebUI chat is a NEW Hermes session with no memory of the previous one ("where did everything go?").
  # A progress note on the persistent /workdir volume is what carries work across chats.
  read -r -d '' PROGRESS_TXT <<'PROGRESSPROMPT' || true
- Continuity: keep a progress file at /workdir/PROGRESS.md (what was done, what is missing, what is next, dates). Update it when you finish each important step. At the start of ANY conversation, read it first (if it exists) and tell the person in one line where the work stands. Every new chat is a new session: without that file you remember nothing.
PROGRESSPROMPT
  SYSTEM="$SYSTEM"$'\n'"$PROGRESS_TXT"
fi

# Stacks whose person has Claude Code reachable over SSH (ops/install_claude_gate.sh; CLAUDE_REMOTE=1): ask before delegating.
# A rule in memory alone was ignored (the model just built the whole thing); the system prompt is read first.
if [ "${CLAUDE_REMOTE:-0}" = 1 ]; then
  read -r -d '' CLAUDE_TXT <<'CLAUDEPROMPT' || true
- COMPLEX tasks (code in several files, the architecture of a system, a refactor, a hard bug, a long analysis): do NOT start them. Answer ONLY with this question, in the person's language, and wait: «This is complex, do you want me to hand it to Claude?». If they say yes (or already asked you to use Claude), load your skill `claude-remote` and delegate as it says. Do not use the `claude-code` skill: there is no `claude` in this container. Simple things (answers, short scripts, one file, searches, a CV) you solve yourself without asking.
CLAUDEPROMPT
  SYSTEM="$SYSTEM"$'\n'"$CLAUDE_TXT"
fi

# The password goes through the environment and stdin, never argv (visible in ps).
TOKEN="$(EMAIL="$ADMIN_EMAIL" PW="$PW" python3 -c 'import json,os;print(json.dumps({"email":os.environ["EMAIL"],"password":os.environ["PW"]}))' \
  | curl -fsS "$BASE/api/v1/auths/signin" -H 'Content-Type: application/json' --data-binary @- \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')"

BODY="$(python3 - "$SYSTEM" <<'PY'
import json,sys
print(json.dumps({
  "id": "hermes",
  "base_model_id": "hermes-agent",
  "name": "Hermes",
  "meta": {"description": "Hermes Agent (archivos, PDF, imágenes, diagramas Mermaid)",
           # vision must be True or the UI hides image attachments. Hermes's API takes image_url parts and
           # describes them (read text + shapes from a PNG in 8s).
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
code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/models/create" "${H[@]}" -d "$BODY")"
if [ "$code" != 200 ]; then
  # already exists -> update
  code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/models/model/update?id=hermes" "${H[@]}" -d "$BODY")"
fi
echo "model preset 'hermes': HTTP $code"
[ "$code" = 200 ]

# Hide the raw base model from the selector: without the preset's system prompt Hermes doesn't know it
# is on the web UI. It must stay ACTIVE (meta.hidden only hides it): an inactive base model is dropped
# from the model list entirely and the "hermes" preset that points at it stops resolving
# ("Model not found"), as found the hard way.
HIDE='{"id":"hermes-agent","base_model_id":null,"name":"hermes-agent","meta":{"hidden":true},"params":{},"is_active":true,"access_control":{"read":{"group_ids":[],"user_ids":[]},"write":{"group_ids":[],"user_ids":[]}}}'
code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/models/create" "${H[@]}" -d "$HIDE")"
if [ "$code" != 200 ]; then
  code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/models/model/update?id=hermes-agent" "${H[@]}" -d "$HIDE")"
fi
echo "base model hidden: HTTP $code"
[ "$code" = 200 ]

# These settings live in Open WebUI's database after first boot, so the DEFAULT_MODELS /
# ENABLE_EVALUATION_ARENA_MODELS env vars are ignored once it has started once: set them via the API.
code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/configs/models" "${H[@]}" \
  -d '{"DEFAULT_MODELS":"hermes","DEFAULT_PINNED_MODELS":"hermes","MODEL_ORDER_LIST":["hermes"]}')"
echo "default model = hermes: HTTP $code"; [ "$code" = 200 ]
code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/evaluations/config" "${H[@]}" \
  -d '{"ENABLE_EVALUATION_ARENA_MODELS":false,"EVALUATION_ARENA_MODELS":[]}')"
echo "arena models off: HTTP $code"; [ "$code" = 200 ]

# PDF/DOCX uploads: Open WebUI "slim" has no extractor and answers 503 ("requires an external document extractor").
# DOC_EXTRACTOR_URL points at doc_extractor.py (tika protocol, runs inside the Hermes container of the stack).
# Indexing/embedding stays off: Hermes opens the real file itself (see the web-interface skill).
if [ -n "${DOC_EXTRACTOR_URL:-}" ]; then
  code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/retrieval/config/update" "${H[@]}" \
    -d "{\"CONTENT_EXTRACTION_ENGINE\":\"tika\",\"TIKA_SERVER_URL\":\"$DOC_EXTRACTOR_URL\",\"BYPASS_EMBEDDING_AND_RETRIEVAL\":true}")"
  echo "document extractor ($DOC_EXTRACTOR_URL): HTTP $code"; [ "$code" = 200 ]
fi

# Open WebUI keeps the resolved model list in memory and only recomputes it when /api/models is requested;
# until then chat calls can fail with "Model not found" using the state from before this script ran.
curl -fsS -o /dev/null "$BASE/api/models" "${H[@]}" && echo "model list refreshed"

# Voice mode ("Call" button): needs HTTPS in the browser (mic), which the edge provides.
#   TTS: TTS_URL (voice-proxy: Piper on the home GPU, the local Piper as fallback; per-person stacks pass their own `tts`).
#   VOICE "auto" = the voice follows the text's language (a fixed Spanish voice read Russian as "cirílico, cirílico").
#   STT, in this order: STT_URL (voice-proxy: Whisper on the home GPU,
#   then on the CPU container; nothing leaves home) > Groq's Whisper when GROQ_API_KEY is in ENV_FILE (audio goes to
#   Groq) > the browser's own speech recognition. A per-person stack must NOT carry the operator's Groq key: its admin
#   could read it from Open WebUI; those stacks pass STT_URL="" and use the browser.
GROQ_KEY="$(grep '^GROQ_API_KEY=' "$ENV_FILE" | cut -d= -f2- || true)"
CUR="$(curl -fsS "$BASE/api/v1/audio/config" "${H[@]}")"
NEW="$(GROQ_KEY="$GROQ_KEY" TTS_URL="$TTS_URL" TTS_VOICE="$TTS_VOICE" STT_URL="$STT_URL" python3 -c '
import json,os,sys
c=json.loads(sys.stdin.read())
c["tts"].update({"ENGINE":"openai","OPENAI_API_BASE_URL":os.environ["TTS_URL"],"OPENAI_API_KEY":"local",
                 "MODEL":"tts-1","VOICE":os.environ["TTS_VOICE"],"SPLIT_ON":"punctuation"})
if os.environ["STT_URL"]:
    c["stt"].update({"ENGINE":"openai","OPENAI_API_BASE_URL":os.environ["STT_URL"],"OPENAI_API_KEY":"local","MODEL":"whisper-1"})
elif os.environ["GROQ_KEY"]:
    c["stt"].update({"ENGINE":"openai","OPENAI_API_BASE_URL":"https://api.groq.com/openai/v1",
                     "OPENAI_API_KEY":os.environ["GROQ_KEY"],"MODEL":"whisper-large-v3-turbo"})
else:
    c["stt"].update({"ENGINE":"","OPENAI_API_KEY":""})
print(json.dumps({"tts":c["tts"],"stt":c["stt"]}))' <<<"$CUR")"
# $NEW can carry the Groq key: send it on stdin, not argv.
code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/audio/config/update" "${H[@]}" --data-binary @- <<<"$NEW")"
echo "voice config ($([ -n "$STT_URL" ] && echo home || ([ -n "$GROQ_KEY" ] && echo Groq || echo browser)) STT + Piper TTS): HTTP $code"; [ "$code" = 200 ]

# Open WebUI keeps the resolved model list in memory and only recomputes it when /api/models is requested;
# until then chat calls can fail with "Model not found" using the state from before this script ran.
curl -fsS -o /dev/null "$BASE/api/models" "${H[@]}" && echo "model list refreshed"

# Welcome banner (only for per-person stacks: WELCOME=1): where to get a key, where to paste it, what happens next.
# Text lives in ops/welcome.<WELCOME_LANG>.md (es by default; ru for a Russian speaker). Dismissible, so it greets without nagging.
# To refresh it on a running stack without the rest of this script: ops/web_banner.sh <stack> es|ru welcome
if [ "${WELCOME:-0}" = 1 ]; then
  # The banner list is replaced as a whole by the API: read the current list, swap only our "bienvenida" entry, post it back.
  CURB="$(curl -fsS "$BASE/api/v1/configs/banners" "${H[@]}")"
  # A stack of the operator's own account started with the operator's key (marker stacks/<name>/workdir/.starter-key, written by
  # provision_stack.sh --operator-account --nim-key) also gets ops/welcome_starter.<lang>.md: it says how to get their own.
  STARTER_MARK="$(dirname "${ENV_FILE:-/nonexistent}")/workdir/.starter-key"
  BANNERS="$(CURB="$CURB" STARTER_MARK="$STARTER_MARK" python3 - "$HERE/welcome.${WELCOME_LANG:-es}.md" <<'PY'
import json,os,sys,time
try:
    cur = json.loads(os.environ.get("CURB") or "[]")
except ValueError:
    cur = []
if isinstance(cur, dict):
    cur = cur.get("banners", [])
ru = sys.argv[1].endswith(".ru.md")
text = open(sys.argv[1],encoding="utf-8").read()
if os.path.exists(os.environ.get("STARTER_MARK","")):
    text += "\n\n" + open(sys.argv[1].replace("welcome.", "welcome_starter."),encoding="utf-8").read()
mine = {"id":"bienvenida","type":"info","title":"👋 Добро пожаловать в ваш Hermes" if ru else "👋 Bienvenido/a a tu Hermes","content":text,"dismissible":True,"timestamp":int(time.time())}
print(json.dumps({"banners":[b for b in cur if not str(b.get("id","")).startswith("bienvenida")] + [mine]}))
PY
)"
  code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/configs/banners" "${H[@]}" -d "$BANNERS")"
  echo "welcome banner: HTTP $code"; [ "$code" = 200 ]
fi
