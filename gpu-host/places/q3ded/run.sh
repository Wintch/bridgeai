#!/bin/sh
# run.sh [ADDRESS] [NAME]: builds (if needed) and starts the headless Quake III demo LAN server on this machine, published on ADDRESS:27960/udp only.
# The container: read-only root, its home a 64 MB tmpfs (nothing kept between restarts), no capabilities, no-new-privileges, 512 MB, 1 CPU, 64 processes,
# its own network (interface NAMEdoc on the host). The places reach it only if the GPU host's /etc/default/bridgeai-places lists ADDRESS:27960 in
# PLACE_GAME_SERVERS (places-net.sh opens exactly that), and lan-discovery.py then shows it in the games' LAN list.
set -eu
ADDR=${1:?usage: run.sh LAN_ADDRESS [NAME]}; NAME=${2:-q3lan}
HERE=$(cd "$(dirname "$0")" && pwd)
docker image inspect bridgeai-q3ded:latest >/dev/null 2>&1 || docker build -t bridgeai-q3ded:latest "$HERE"
docker network inspect "$NAME-net" >/dev/null 2>&1 || docker network create --driver bridge --opt com.docker.network.bridge.enable_icc=false \
  --opt "com.docker.network.bridge.name=${NAME}doc" "$NAME-net" >/dev/null
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --hostname "$NAME" --network "$NAME-net" --restart unless-stopped -p "$ADDR:27960:27960/udp" \
  --read-only --tmpfs /home/q3:size=64m,uid=27960,gid=27960 --cap-drop ALL --security-opt no-new-privileges \
  --memory 512m --memory-swap 512m --cpus 1 --pids-limit 64 bridgeai-q3ded:latest
