#!/bin/sh
# bench-q2rtx.sh [REPS]: Quake II RTX's own timedemo (q2demo1, 631 frames, full path tracer, appid 1089130) in a place, unattended.
# Run inside the place's desktop session as the person's user (the session's DISPLAY/DBUS exported). Same recipe as reverb-g2's
# local-notes/scripts/q2rtx-power-sweep.sh (launch through the running Steam, read "N frames, S seconds: F fps" from the game's console
# log, stop the game), 3 repetitions by default (that project's discipline). Baseline on a bare 3060 Ti (reverb-g2 docs/96): 74.6 fps at 210 W,
# 74.5 at 190 W. Results to RAM: /dev/shm/bench-q2rtx-<time>.csv (rep,frames,seconds,fps).
set -u
REPS=${1:-3}
APPID=1089130
LOG="$HOME/.local/share/quake2rtx/baseq2/logs/console.log"
OUT=/dev/shm/bench-q2rtx-$(date +%H%M%S).csv
TIMEOUT_S=${BENCH_TIMEOUT_S:-240}
echo "rep,frames,seconds,fps" > "$OUT"
stop_game() {
  for p in $(pgrep -u "$(id -u)" -f "[q]2rtx|quake2rtx"); do kill "$p" 2>/dev/null; done
  i=0; while pgrep -u "$(id -u)" -f "[q]2rtx" >/dev/null && [ $i -lt 20 ]; do sleep 1; i=$((i+1)); done
}
for rep in $(seq 1 "$REPS"); do
  before=0; [ -f "$LOG" ] && before=$(wc -l < "$LOG")
  echo "$(date +%T) rep $rep: launch"
  steam -applaunch "$APPID" +set logfile 2 +timedemo 1 +demo q2demo1 >/dev/null 2>&1 &
  waited=0; line=""
  while [ "$waited" -lt "$TIMEOUT_S" ]; do
    sleep 2; waited=$((waited + 2))
    [ -f "$LOG" ] || continue
    line=$(tail -n "+$((before + 1))" "$LOG" | grep -E 'frames,.*seconds:.*fps' | tail -1)
    [ -n "$line" ] && break
  done
  stop_game
  if [ -z "$line" ]; then echo "$(date +%T) rep $rep: no result after ${waited}s"; continue; fi
  frames=$(echo "$line" | grep -oE '[0-9]+ frames' | grep -oE '[0-9]+')
  secs=$(echo "$line" | grep -oE '[0-9.]+ seconds' | grep -oE '[0-9.]+')
  fps=$(echo "$line" | grep -oE '[0-9.]+ fps' | grep -oE '[0-9.]+')
  echo "$(date +%T) rep $rep: $frames frames, ${secs}s, $fps fps (after ${waited}s)"
  echo "$rep,$frames,$secs,$fps" >> "$OUT"
  sleep 3
done
echo "results: $OUT"; cat "$OUT"
