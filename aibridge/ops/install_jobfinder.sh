#!/bin/bash
# Run on VM105: install the jobfinder bundle into a stack's persistent workdir and install its dependencies with
# Hermes's own Node (same ABI), skipping Playwright's browser download (the image already ships Chromium in /opt/ms-playwright).
#   ./ops/install_jobfinder.sh <stack-name> /path/to/jobfinder-bundle.tgz
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:?stack name}"; BUNDLE="${2:?bundle .tgz}"
DEST="stacks/$NAME/workdir/jobfinder"
[ -d "stacks/$NAME" ] || { echo "no such stack: $NAME" >&2; exit 2; }
if [ -e "$DEST/cv.md" ] || [ -e "$DEST/config/profile.yml" ]; then
  echo "refusing to overwrite: $DEST already holds the person's data (cv.md / profile.yml). Update system files by hand." >&2; exit 3
fi
mkdir -p "$DEST"; tar -xzf "$BUNDLE" -C "$DEST"
# throwaway container on the main network (has internet) using Hermes's image: its node, root, bind-mounted workdir
docker run --rm --network aibridge_default --entrypoint sh -v "$PWD/$DEST:/jf" -w /jf aibridge-hermes-agent:latest \
  -c 'set -e; node --version; test -f package-lock.json; npm ci --ignore-scripts --no-audit --no-fund 2>&1 | tail -4; test -d node_modules/playwright'
# upstream `cops` drives `docker compose`; Hermes's container has no Docker, so swap in the Docker-free version
install -m 755 "$(dirname "$0")/cops-nodocker" "$DEST/cops"
echo "installed in $DEST ($(du -sh "$DEST" | cut -f1)); version $(cat "$DEST/VERSION")"
