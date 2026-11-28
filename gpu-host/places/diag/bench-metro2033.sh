#!/bin/sh
# Automatic Metro 2033 Redux benchmark in a place (native Linux build, as the person's user, inside the desktop session). Launched through
# the running Steam with the game's own benchmark arguments (benchmark.sh in the game folder lists them); results to RAM.
set -u
RUNS=${1:-3}
OUT=/dev/shm/metro-bench-$(date +%H%M%S).txt
LOG=/dev/shm/bridgeai-bench.log
log() { echo "$(date +%T) $*" | tee -a "$LOG"; }
pgrep -u "$(id -u)" -x metro >/dev/null && { log "Metro already running: not started"; exit 1; }
log "metro benchmark: $RUNS runs -> $OUT"
steam -applaunch 286690 -benchmark 'benchmarks\benchmark33' -bench_runs "$RUNS" -output_file "$OUT" -close_on_finish >/dev/null 2>&1 &
i=0; while ! pgrep -u "$(id -u)" -x metro >/dev/null && [ $i -lt 180 ]; do sleep 2; i=$((i+2)); done
log "metro process after ${i}s"
j=0; while pgrep -u "$(id -u)" -x metro >/dev/null && [ $j -lt 900 ]; do sleep 2; j=$((j+2)); done
log "metro gone after ${j}s"
[ -s "$OUT" ] && { log "result:"; cat "$OUT"; } || log "no result file"
