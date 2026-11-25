#!/bin/sh
# build-steam.sh [BASE_IMAGE] [TAG]: builds bridgeai-place-steam on top of the Sunshine image (see Dockerfile.steam). Run it on the GPU host, in this folder.
set -eu
BASE=${1:-bridgeai-place-sunshine:latest}; TAG=${2:-bridgeai-place-steam:latest}
HERE=$(cd "$(dirname "$0")" && pwd)
docker build -f "$HERE/Dockerfile.steam" --build-arg "BASE=$BASE" -t "$TAG" "$HERE"
