#!/bin/sh
# run.sh [ADDRESS] [NAME]: builds (if needed) and starts the headless Quake III demo LAN server on this machine, published on ADDRESS:27960/udp only.
# Environment: NET_SUBNET (the server network's subnet: on the GPU host of the places use one inside 172.30.0.0/16, e.g. 172.30.250.0/24, so the
# places' firewall treats it as a game between places), SV_HOSTNAME, SV_MAP, SV_FRAGLIMIT, SV_TIMELIMIT, SV_MAXCLIENTS (passed to the server).
# The container: read-only root, its home a 64 MB tmpfs (nothing kept between restarts), no capabilities, no-new-privileges, 512 MB, 1 CPU, 64 processes,
# its own network (interface NAMEdoc on the host). The places reach it only if the GPU host's /etc/default/bridgeai-places lists ADDRESS:27960 in
# PLACE_GAME_SERVERS (places-net.sh opens exactly that), and lan-discovery.py then shows it in the games' LAN list.
# MEM (default 512m) and CPUS (default 1) size the container; ioq3ded itself needs about 50 MB, so a small always-on VM can run it with MEM=192m.
set -eu
ADDR=${1:?usage: run.sh LAN_ADDRESS [NAME]}; NAME=${2:-q3lan}
HERE=$(cd "$(dirname "$0")" && pwd)
docker image inspect bridgeai-q3ded:latest >/dev/null 2>&1 || docker build -t bridgeai-q3ded:latest "$HERE"
docker network inspect "$NAME-net" >/dev/null 2>&1 || docker network create --driver bridge ${NET_SUBNET:+--subnet "$NET_SUBNET"} --opt com.docker.network.bridge.enable_icc=false \
  --opt "com.docker.network.bridge.name=${NAME}doc" "$NAME-net" >/dev/null
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --hostname "$NAME" --network "$NAME-net" --restart unless-stopped -p "$ADDR:27960:27960/udp" \
  --read-only --tmpfs /home/q3:size=64m,uid=27960,gid=27960 --cap-drop ALL --security-opt no-new-privileges \
  --memory "${MEM:-512m}" --memory-swap "${MEM:-512m}" --cpus "${CPUS:-1}" --pids-limit 64 \
  ${SV_HOSTNAME:+-e SV_HOSTNAME="$SV_HOSTNAME"} ${SV_MAP:+-e SV_MAP="$SV_MAP"} ${SV_FRAGLIMIT:+-e SV_FRAGLIMIT="$SV_FRAGLIMIT"} \
  ${SV_TIMELIMIT:+-e SV_TIMELIMIT="$SV_TIMELIMIT"} ${SV_MAXCLIENTS:+-e SV_MAXCLIENTS="$SV_MAXCLIENTS"} bridgeai-q3ded:latest
