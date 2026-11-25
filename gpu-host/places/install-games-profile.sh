#!/bin/sh
# install-games-profile.sh: run as root on the GPU host, once (and again after a Docker upgrade). Installs what `place.py create|recreate --games` needs:
#   /etc/bridgeai/places/seccomp-games.json   Docker's default seccomp profile + the few calls an unprivileged user namespace needs (make-seccomp-userns.py)
#   /etc/apparmor.d/bridgeai-place-games      docker-default with mount, pivot_root and userns allowed (apparmor-place-games), loaded now and at every boot
#   /etc/cdi/bridgeai-games.json              the GPU as CDI device bridgeai.local/games=all (gen-games-cdi.sh), remade at boot and on driver changes by bridgeai-games-cdi.service
# DEFAULT_JSON is Docker's own default profile (moby/profiles seccomp/default.json); a copy from the Docker version you run is best. Without it the script downloads the current one.
set -eu
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
DEFAULT_JSON=${1:-}
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
if [ -z "$DEFAULT_JSON" ]; then
  curl -fsSL -m60 -o "$TMP/default.json" https://raw.githubusercontent.com/moby/profiles/main/seccomp/default.json
  DEFAULT_JSON=$TMP/default.json
fi
python3 "$HERE/make-seccomp-userns.py" "$DEFAULT_JSON" "$TMP/seccomp-games.json"
install -d -m 0755 /etc/bridgeai/places
install -m 0644 "$TMP/seccomp-games.json" /etc/bridgeai/places/seccomp-games.json
install -m 0644 "$HERE/apparmor-place-games" /etc/apparmor.d/bridgeai-place-games
apparmor_parser -r /etc/apparmor.d/bridgeai-place-games
install -m 0755 "$HERE/gen-games-cdi.sh" /usr/local/sbin/bridgeai-gen-games-cdi
install -m 0644 "$HERE/bridgeai-games-cdi.service" /etc/systemd/system/bridgeai-games-cdi.service
install -d -m 0755 /etc/cdi
systemctl daemon-reload
systemctl enable bridgeai-games-cdi.service >/dev/null
systemctl start bridgeai-games-cdi.service
echo "installed: /etc/bridgeai/places/seccomp-games.json, AppArmor profile bridgeai-place-games, /etc/cdi/bridgeai-games.json (bridgeai-games-cdi.service)"
