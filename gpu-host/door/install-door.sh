#!/bin/sh
# install-door.sh: run as root on the always-on machine. Installs nginx, the door service (user `door`), its folder /etc/bridgeai-door
# (door.json + one set of secret files per person, 0600 door), the nginx site, and a self-signed certificate until a real one replaces it
# (tls/fullchain.pem, tls/privkey.pem). Idempotent; never overwrites door.json or the secret files.
set -eu
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
command -v nginx >/dev/null || { apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends nginx ssl-cert >/dev/null; }
id door >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -d /nonexistent door
install -d -m 0750 -o root -g door /etc/bridgeai-door
install -d -m 0750 -o root -g root /etc/bridgeai-door/tls
install -m 0755 "$HERE/door.py" /usr/local/sbin/bridgeai-door
install -d -m 0755 /usr/local/share/bridgeai-door/desktops
install -m 0644 "$HERE"/desktops/*.webp /usr/local/share/bridgeai-door/desktops/
install -m 0644 "$HERE/qrcodegen.py" /usr/local/share/bridgeai-door/qrcodegen.py   # the gift card's QR (MIT, Project Nayuki; drawn here, no outside service)
[ -f /etc/bridgeai-door/door.json ] || { printf '{\n "listen": "127.0.0.1:8095",\n "gate": "http://GPU_HOST:8700",\n "wake_url": "http://WAKE_SERVICE/despertar?maquina=GPU_HOST_NAME&motivo=puerta",\n "people": {}\n}\n' > /etc/bridgeai-door/door.json; chown root:door /etc/bridgeai-door/door.json; chmod 0640 /etc/bridgeai-door/door.json; }
if [ ! -f /etc/bridgeai-door/tls/fullchain.pem ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=door" -keyout /etc/bridgeai-door/tls/privkey.pem -out /etc/bridgeai-door/tls/fullchain.pem 2>/dev/null
  chmod 0600 /etc/bridgeai-door/tls/privkey.pem
fi
install -d -m 0755 /var/www/letsencrypt
install -m 0644 "$HERE/nginx-door.conf" /etc/nginx/sites-available/bridgeai-door
ln -sfn /etc/nginx/sites-available/bridgeai-door /etc/nginx/sites-enabled/bridgeai-door
rm -f /etc/nginx/sites-enabled/default
nginx -t
install -m 0644 "$HERE/bridgeai-door.service" /etc/systemd/system/bridgeai-door.service
systemctl daemon-reload
systemctl enable --now bridgeai-door >/dev/null
systemctl reload nginx || systemctl restart nginx
echo "installed: edit /etc/bridgeai-door/door.json, put each person's PERSON.pass/.token/.basic (0600, owner door), then: bridgeai-door check"
