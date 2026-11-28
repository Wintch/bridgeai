#!/bin/bash
# Publishes the door from this checkout to the door machine. Usage: sh publish-door.sh USER@DOOR_HOST (a sudo user there)
# Backs up every file, changes ONLY the welcome line of nginx, tests nginx before reloading and puts everything back if a step fails.
# The public name to verify comes from DOOR_URL (default: none, then the check is skipped).
set -euo pipefail
H="${1:?usage: publish-door.sh USER@DOOR_HOST}"
R=$(cd "$(dirname "$0")" && pwd)
T=$(date +%Y%m%d-%H%M%S)
WELCOME=$(grep "<title>Bienvenido</title>" "$R/nginx-door.conf")
[ -n "$WELCOME" ] || { echo "no welcome line in the repo nginx-door.conf"; exit 1; }
scp -q "$R/door.py" "$R/qrcodegen.py" "$R/maintenance/index.html" "$H:/tmp/"
printf '%s\n' "$WELCOME" | ssh "$H" "cat > /tmp/door-welcome.line"
ssh -t "$H" "T=$T bash -s" <<'REMOTE'
set -euo pipefail
S=""; [ "$(id -u)" = 0 ] || S=sudo
NG=/etc/nginx/sites-available/bridgeai-door
$S cp -a /usr/local/sbin/bridgeai-door /usr/local/sbin/bridgeai-door.bak-$T
$S cp -a $NG $NG.bak-$T
[ -f /var/www/bridgeai-maintenance/index.html ] && $S cp -a /var/www/bridgeai-maintenance/index.html /var/www/bridgeai-maintenance/index.html.bak-$T
undo() { echo "FAILED: putting everything back"; $S cp -a /usr/local/sbin/bridgeai-door.bak-$T /usr/local/sbin/bridgeai-door; $S cp -a $NG.bak-$T $NG
         $S nginx -t && $S systemctl reload nginx; $S systemctl restart bridgeai-door; exit 1; }
trap undo ERR
$S install -m 0755 /tmp/door.py /usr/local/sbin/bridgeai-door
$S install -d -m 0755 /usr/local/share/bridgeai-door
$S install -m 0644 /tmp/qrcodegen.py /usr/local/share/bridgeai-door/qrcodegen.py
$S install -d -m 0755 /var/www/bridgeai-maintenance
$S install -m 0644 /tmp/index.html /var/www/bridgeai-maintenance/index.html
n=$($S grep -c "<title>Bienvenido</title>" $NG)
[ "$n" = 1 ] || { echo "the welcome line appears $n times in $NG: not touching it"; false; }
$S python3 - "$NG" /tmp/door-welcome.line <<'PY'
import sys
ng, new = sys.argv[1], open(sys.argv[2]).read().rstrip("\n")
lines = open(ng).read().split("\n")
lines = [new if "<title>Bienvenido</title>" in l else l for l in lines]
open(ng, "w").write("\n".join(lines))
PY
$S nginx -t
$S systemctl reload nginx
$S systemctl restart bridgeai-door
sleep 1
$S systemctl is-active bridgeai-door
$S /usr/local/sbin/bridgeai-door check || true
trap - ERR
rm -f /tmp/door.py /tmp/qrcodegen.py /tmp/index.html /tmp/door-welcome.line
echo "done; backups: *.bak-$T"
REMOTE
if [ -n "${DOOR_URL:-}" ]; then
  echo "check:"; curl -s -m 10 "$DOOR_URL/_door/login" | grep -o -E 'name="design-guide"[^>]*|min-height:2.75rem' | sort -u
fi
