#!/bin/sh
# certbot deploy hook (/etc/letsencrypt/renewal-hooks/deploy/bridgeai-door): copies the renewed certificate where nginx reads it and reloads nginx.
set -eu
L=/etc/letsencrypt/live/${DOOR_NAME:-$(sed -n 's/^DOOR_NAME=//p' /etc/bridgeai-door/ddns.env)}
install -m 0644 "$L/fullchain.pem" /etc/bridgeai-door/tls/fullchain.pem
install -m 0600 "$L/privkey.pem" /etc/bridgeai-door/tls/privkey.pem
systemctl reload nginx
