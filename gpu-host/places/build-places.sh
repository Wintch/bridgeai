#!/bin/bash
# build-places.sh [STEP...]: builds the place images on the GPU host, in this folder, one build at a time, and leaves a status file that a
# watcher can trust. Steps, in order: place sunshine steam quake resolve (default: all). Run with nohup; follow the status, not the processes.
#
#   nohup ./build-places.sh > ~/build-places.log 2>&1 &
#   cat ~/.cache/bridgeai/build-places.status      # "running STEP", then "done SECONDS" or "failed STEP RC"
#
# Lessons of the 2026-11-28 batch, built in:
# - One build at a time (flock): two runs over the same Resolve folder unpacked over each other and the image was never made.
# - Watch the status file, never `pgrep -f NAME` over ssh: the ssh command line holds NAME, so pgrep finds itself and "it still runs" forever.
# - Never grep the log for "ERROR": makeresolvedeb prints "[ERROR: MISSING]" lines as normal output. Docker's own failures end the step's rc.
# - The .dockerignore is an allow-list: a new file the images COPY must be added there.
# - A multi-stage Dockerfile needs its build ARGs before the first FROM.
# - The Quake demo's data comes from the data-only image (bridgeai-quake3-demo-data:N, PLACES.md), never from the vendor's mirrors.
# - Keep the host awake for the build: a maintenance mark (gpu-host-sleep-mark HOURS) is set here and removed at the end.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
STATE=${XDG_CACHE_HOME:-$HOME/.cache}/bridgeai; mkdir -p "$STATE"
STATUS=$STATE/build-places.status
RESOLVE_DIR=${RESOLVE_DIR:-$HOME/resolve-free-build}
exec 9>"$STATE/build-places.lock"
flock -n 9 || { echo "another build-places run holds the lock"; exit 1; }
STEPS=("$@"); [ ${#STEPS[@]} -gt 0 ] || STEPS=(place sunshine steam quake resolve)
command -v gpu-host-sleep-mark >/dev/null && sudo -n gpu-host-sleep-mark 3 build-places >/dev/null 2>&1 || true
cd "$HERE"
t0=$(date +%s)
for s in "${STEPS[@]}"; do
  echo "running $s $(date +%H:%M:%S)" > "$STATUS"; echo "== $(date +%H:%M:%S) $s"
  case "$s" in
    place)    docker build -q -f Dockerfile.place -t bridgeai-place:latest . ;;
    sunshine) sh build-sunshine.sh ;;
    steam)    sh build-steam.sh ;;
    quake)    docker build -q -f Dockerfile.quake -t bridgeai-place-quake:latest . ;;
    resolve)  rm -rf "$RESOLVE_DIR"/unpack-* "$RESOLVE_DIR"/davinci-resolve*_amd64; bash build-resolve.sh "$RESOLVE_DIR" ;;
    *)        echo "unknown step $s"; false ;;
  esac
  rc=$?
  if [ $rc -ne 0 ]; then echo "failed $s $rc" > "$STATUS"; echo "== FAILED $s (rc $rc)"; break; fi
done
[ "${rc:-0}" -eq 0 ] && echo "done $(( $(date +%s) - t0 ))" > "$STATUS" && echo "== done in $(( $(date +%s) - t0 )) s"
command -v gpu-host-sleep-mark >/dev/null && sudo -n gpu-host-sleep-mark off >/dev/null 2>&1 || true
docker images --format '{{.Repository}}:{{.Tag}} {{.CreatedSince}} {{.Size}}' | grep -E 'bridgeai-(place|quake3)'
exit "${rc:-0}"
