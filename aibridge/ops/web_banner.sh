#!/bin/bash
# Show the current release notice as a dismissible banner in a web-only person's Open WebUI. 2026-10-18.
#
#   ops/web_banner.sh <stack> es|ru        (run on VM105 from ~/aibridge, after ops/redeploy_router.sh; also: ops/web_banner.sh <stack> off)
#
# herand and hereug call their model directly, so the router's one-time notice never reaches them; this is their channel. The
# text is the web_<lang> line of RELEASE_NOTICE.txt, the banner id carries the release id (a new release shows again even to
# someone who dismissed the last one) and older release banners are removed. It reads the stack's admin password from its .env
# (through the environment and stdin, never argv). The request goes through the stack's web port, which wakes a sleeping stack.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
NAME="${1:?usage: ops/web_banner.sh <stack> es|ru|off}"; LANG_="${2:?usage: ops/web_banner.sh <stack> es|ru|off}"
ENV_FILE="stacks/$NAME/.env"
[ -f "$ENV_FILE" ] || { echo "no $ENV_FILE" >&2; exit 2; }
get() { grep -m1 "^$1=" "$ENV_FILE" | cut -d= -f2-; }
BASE="http://$(get LAN_IP):$(get WEB_PORT)"
EMAIL="$(get ADMIN_EMAIL)"; PW="$(get OPENWEBUI_ADMIN_PASSWORD)"
for _ in $(seq 1 40); do   # a sleeping stack answers 503 while it boots (about 15 s)
  [ "$(curl -s -m5 -o /dev/null -w '%{http_code}' "$BASE/health")" = 200 ] && break; sleep 3
done
TOKEN="$(EMAIL="$EMAIL" PW="$PW" python3 -c 'import json,os;print(json.dumps({"email":os.environ["EMAIL"],"password":os.environ["PW"]}))' \
  | curl -fsS "$BASE/api/v1/auths/signin" -H 'Content-Type: application/json' --data-binary @- \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')"
H=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
CURB="$(curl -fsS "$BASE/api/v1/configs/banners" "${H[@]}")"
BANNERS="$(CURB="$CURB" python3 - "$LANG_" RELEASE_NOTICE.txt <<'PY'
import json, os, sys, time
lang, path = sys.argv[1], sys.argv[2]
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
echo "$NAME banner ($LANG_): HTTP $code"; [ "$code" = 200 ]
