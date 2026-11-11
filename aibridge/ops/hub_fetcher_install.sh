#!/bin/bash
# Install or update the hub's OWN jobfinder checkout, the code the shared job fetch runs (run on the Docker host from ~/aibridge).
#   ./ops/hub_fetcher_install.sh /path/to/jobfinder-bundle.tgz        (make it on the desktop: ops/make_jobfinder_bundle.sh)
# The bundle is the CLEAN system layer of the jobfinder (git-tracked files only: select-portals.mjs, union-portals.mjs, scan.mjs, the catalog in
# templates/ and the role families), the same one people's stacks get. It lands in hubdata/fetcher, which belongs to the hub and holds no
# person's data: re-running updates the code in place and keeps fetcher/data/ (its own scan state). Dependencies are installed with the image's
# own Node (same ABI), skipping Playwright's browser download (the image ships Chromium). Needs the jobfinder at a commit that has
# union-portals.mjs and the cache-only mode (jobfinder docs/SHARED_FETCH.md).
set -euo pipefail
cd "$(dirname "$0")/.."
BUNDLE="${1:?bundle .tgz}"
[ -d hubdata ] || { echo "no hubdata/: run ops/hub_install.sh --apply first" >&2; exit 2; }
tar -tzf "$BUNDLE" | grep -qx 'union-portals.mjs' || { echo "this bundle has no union-portals.mjs: build it from a jobfinder with the shared-fetch commit" >&2; exit 3; }
DEST=hubdata/fetcher
mkdir -p "$DEST"
tar -xzf "$BUNDLE" -C "$DEST"
docker run --rm --network aibridge_default --entrypoint sh -v "$PWD/$DEST:/jf" -w /jf aibridge-hermes-agent:latest \
  -c 'set -e; node --version; test -f package-lock.json; npm ci --ignore-scripts --no-audit --no-fund 2>&1 | tail -4; test -d node_modules/playwright; \
      node select-portals.mjs --list-tags >/dev/null && node union-portals.mjs --help >/dev/null && echo "fetcher tools run"'
echo "fetcher installed in $DEST ($(du -sh "$DEST" | cut -f1)); version $(cat "$DEST/VERSION" 2>/dev/null)"
echo "next: add {\"kind\":\"jobfetch\",\"key\":\"union\"} to hubdata/system.json (optionally \"params\":{\"profiles\":[...]} for a baseline profile of your own)"
