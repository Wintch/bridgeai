#!/bin/bash
# Show the current release notice as a dismissible banner in a web-only person's Open WebUI.
#
#   ops/web_banner.sh <stack> es|ru        (run on the Docker host from ~/aibridge, after ops/redeploy_router.sh; also: ops/web_banner.sh <stack> off)
#   ops/web_banner.sh <stack> es|ru welcome   the welcome banner from ops/welcome.<lang>.md instead (where to get and paste the
#                                             keys); a new id each time, so a person who closed the old one sees the new text
#
# some stacks call their model directly, so the router's one-time notice never reaches them; this is their channel. The
# text is the web_<lang> line of RELEASE_NOTICE.txt, the banner id carries the release id (a new release shows again even to
# someone who dismissed the last one) and older release banners are removed. It reads the stack's admin password from its .env
# (through the environment and stdin, never argv). A sleeping stack is woken the way a visit does.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
NAME="${1:?usage: ops/web_banner.sh <stack> es|ru|off [welcome]}"; LANG_="${2:?usage: ops/web_banner.sh <stack> es|ru|off [welcome]}"
KIND="${3:-release}"
[ "$KIND" = release ] || [ "$KIND" = welcome ] || { echo "third argument: welcome (or nothing)" >&2; exit 2; }
[ "$KIND" = release ] || [ -f "ops/welcome.$LANG_.md" ] || { echo "no ops/welcome.$LANG_.md" >&2; exit 2; }
ENV_FILE="stacks/$NAME/.env"
[ -f "$ENV_FILE" ] || { echo "no $ENV_FILE" >&2; exit 2; }
get() { grep -m1 "^$1=" "$ENV_FILE" | cut -d= -f2-; }
BASE="http://$(get LAN_IP):$(get WEB_PORT)"
EMAIL="$(get ADMIN_EMAIL)"; PW="$(get OPENWEBUI_ADMIN_PASSWORD)"
# A sleeping stack wakes only for a browser navigation (waker.py ignores bots and fetches), so ask the way a visit does, once;
# then wait for Open WebUI (about 15 s). Plain curl would get 503 forever.
if [ "$(curl -s -m5 -o /dev/null -w '%{http_code}' "$BASE/health")" != 200 ]; then
  curl -s -m10 -o /dev/null -H 'Accept: text/html' -H 'Sec-Fetch-Mode: navigate' -H 'Sec-Fetch-Dest: document' "$BASE/" || true
  up=0
  for _ in $(seq 1 40); do
    [ "$(curl -s -m5 -o /dev/null -w '%{http_code}' "$BASE/health")" = 200 ] && { up=1; break; }; sleep 3
  done
  [ "$up" = 1 ] || { echo "$NAME did not wake within 2 minutes (waker or RAM budget?): nothing changed" >&2; exit 3; }
fi
TOKEN="$(EMAIL="$EMAIL" PW="$PW" python3 -c 'import json,os;print(json.dumps({"email":os.environ["EMAIL"],"password":os.environ["PW"]}))' \
  | curl -fsS "$BASE/api/v1/auths/signin" -H 'Content-Type: application/json' --data-binary @- \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')"
H=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
CURB="$(curl -fsS "$BASE/api/v1/configs/banners" "${H[@]}")"
BANNERS="$(CURB="$CURB" STARTER_MARK="stacks/$NAME/workdir/.starter-key" python3 - "$LANG_" RELEASE_NOTICE.txt "$KIND" <<'PY'
import json, os, sys, time
lang, path, kind = sys.argv[1], sys.argv[2], sys.argv[3]
if kind == "welcome":
    try:
        cur = json.loads(os.environ.get("CURB") or "[]")
    except ValueError:
        cur = []
    cur = cur.get("banners", []) if isinstance(cur, dict) else cur
    keep = [b for b in cur if not str(b.get("id", "")).startswith("bienvenida")]
    text = open(f"ops/welcome.{lang}.md", encoding="utf-8").read()
    if os.path.exists(os.environ.get("STARTER_MARK", "")):   # the stack started on the operator's shared key
        text += "\n\n" + open(f"ops/welcome_starter.{lang}.md", encoding="utf-8").read()
    keep.append({"id": "bienvenida-" + time.strftime("%Y%m%d%H%M"), "type": "info",
                 "title": {"ru": "👋 Добро пожаловать в ваш Hermes"}.get(lang, "👋 Bienvenido/a a tu Hermes"),
                 "content": text, "dismissible": True, "timestamp": int(time.time())})
    print(json.dumps({"banners": keep}))
    sys.exit(0)
items = {}
for ln in open(path, encoding="utf-8"):
    if ":" in ln:
        k, v = ln.split(":", 1)
        items[k.strip()] = v.strip()
try:
    cur = json.loads(os.environ.get("CURB") or "[]")
except ValueError:
    cur = []
if isinstance(cur, dict):
    cur = cur.get("banners", [])
keep = [b for b in cur if not str(b.get("id", "")).startswith("actualizacion-")]
if lang != "off":
    text = items.get("web_" + lang)
    if not text or not items.get("id"):
        sys.exit("RELEASE_NOTICE.txt has no web_%s or id line" % lang)
    keep.append({"id": "actualizacion-" + items["id"], "type": "info", "title": "", "content": text,
                 "dismissible": True, "timestamp": int(time.time())})
print(json.dumps({"banners": keep}))
PY
)"
code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/configs/banners" "${H[@]}" -d "$BANNERS")"
echo "$NAME $KIND banner ($LANG_): HTTP $code"; [ "$code" = 200 ]
