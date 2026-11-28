#!/bin/sh
# freeze-wait.sh CONTAINER [SECONDS] [OUTDIR]: waits until the place's container runs, then starts freeze-detector.py on it (root).
C=${1:?usage: freeze-wait.sh CONTAINER [SECONDS] [OUTDIR]}; SECS=${2:-3600}; OUT=${3:-/tmp/rondas}
HERE=$(cd "$(dirname "$0")" && pwd)
i=0
until [ "$(docker inspect -f '{{.State.Status}}' "$C" 2>/dev/null)" = running ] || [ $i -ge 3600 ]; do sleep 2; i=$((i+2)); done
mkdir -p "$OUT"; echo "$(date +%T) $C running, freeze detector on" >> "$OUT/freezes.log"
exec python3 "$HERE/freeze-detector.py" "$C" "$OUT" "$SECS"
