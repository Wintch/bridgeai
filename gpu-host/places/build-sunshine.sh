#!/bin/sh
# build-sunshine.sh [BASE_IMAGE] [TAG]: downloads the pinned Sunshine .deb (sha256 checked), builds bridgeai-place-sunshine on top of the place image.
# Run it on the GPU host, in this folder. The version and its hash are pinned here: change both together when you move to a newer release.
set -eu
VERSION=2026.914.233613
SHA=a86f858cbae57f60ecebd445402ee0295c1c057b857bd45d44c2ea2d255cbbfb
BASE=${1:-bridgeai-place:latest}; TAG=${2:-bridgeai-place-sunshine:latest}
HERE=$(cd "$(dirname "$0")" && pwd)
CTX=$(mktemp -d); trap 'rm -rf "$CTX"' EXIT
cp "$HERE/Dockerfile.sunshine" "$HERE/place-sunshine" "$HERE/place-sunshine.desktop" "$CTX/"
URL="https://github.com/SunshineStream/Sunshine/releases/download/v$VERSION/sunshine_$VERSION-1%2Bdebiantrixie_amd64.deb"
curl -fsSL -m300 -o "$CTX/sunshine.deb" "$URL"
echo "$SHA  $CTX/sunshine.deb" | sha256sum -c - || { echo "the downloaded .deb does not match the pinned hash: nothing built" >&2; exit 1; }
docker build -f "$CTX/Dockerfile.sunshine" --build-arg "BASE=$BASE" --build-arg "SUNSHINE_SHA256=$SHA" -t "$TAG" "$CTX"
