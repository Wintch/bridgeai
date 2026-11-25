#!/bin/bash
# Build the Resolve (free edition) layer for a person's place.
#   build-resolve.sh DIR [--image NAME]
# DIR holds what the operator downloaded: the vendor's `DaVinci_Resolve_<version>_Linux.zip` (the FREE one; the vendor's page asks for a registration) and
# `makeresolvedeb_*_multi.sh` (the Debian package maker used on the host install). The script unpacks the zip, makes the .deb files in DIR and builds the
# image `bridgeai-place-resolve:latest` (or --image) on top of bridgeai-place. A Studio file is refused: its licence is a USB key tied to one host.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DIR=${1:-}; shift || true
IMAGE=bridgeai-place-resolve:latest
[ "${1:-}" = "--image" ] && IMAGE=${2:?--image needs a name}
[ -d "$DIR" ] || { echo "usage: build-resolve.sh DIR (a folder with the free DaVinci_Resolve_*_Linux.zip and makeresolvedeb_*_multi.sh)" >&2; exit 2; }
shopt -s nullglob
zips=("$DIR"/DaVinci_Resolve_*_Linux.zip "$DIR"/DaVinci_Resolve_*_Linux.run)
[ ${#zips[@]} -ge 1 ] || { echo "no DaVinci_Resolve_*_Linux.zip (or .run) in $DIR" >&2; exit 2; }
for z in "${zips[@]}"; do
  case "$(basename "$z")" in *Studio*) echo "refused: $(basename "$z") is Resolve Studio; its licence is a USB key tied to one host and must not go in a person's image. Use the free download." >&2; exit 3;; esac
done
mk=("$DIR"/makeresolvedeb_*_multi.sh); [ ${#mk[@]} -ge 1 ] || { echo "no makeresolvedeb_*_multi.sh in $DIR" >&2; exit 2; }
RUNFILE=""
for z in "${zips[@]}"; do case "$z" in *.run) RUNFILE=$z;; esac; done
if [ -z "$RUNFILE" ]; then
  ( cd "$DIR" && unzip -o -q "$(basename "${zips[0]}")" )
  RUNFILE=$(ls "$DIR"/DaVinci_Resolve_*_Linux.run 2>/dev/null | grep -v Studio | head -1 || true)
fi
[ -n "$RUNFILE" ] || { echo "the zip did not hold a DaVinci_Resolve_*_Linux.run" >&2; exit 2; }
rm -rf "$DIR/ctx"; rm -f "$DIR"/*.deb; mkdir -p "$DIR/ctx/debs"
# makeresolvedeb only accepts an installer that sits in its working directory, and writes the .deb files there
( cd "$DIR" && bash "$(basename "${mk[0]}")" "$(basename "$RUNFILE")" )
cp "$DIR"/*.deb "$DIR/ctx/debs/"
cp "$HERE/Dockerfile.resolve" "$DIR/ctx/Dockerfile"
docker build -t "$IMAGE" "$DIR/ctx"
echo "built $IMAGE; create a place on it with: place.py create NAME --image $IMAGE --gpu"
