#!/bin/sh
# Prototype of the per-game fixer (GTA IV), run in the person's desktop session as the person's user. While GTAIV.exe runs: minimize the
# Rockstar Games Launcher windows once each (its Chromium stops using the GPU when hidden: round 3), and give the launcher, Social Club and
# the Rockstar service the lowest CPU and disk priority. The game itself is never touched. Log in RAM: /dev/shm/bridgeai-fixer.log
LOG=/dev/shm/bridgeai-fixer.log
SEEN_WIN=" "; SEEN_PID=" "; RUNNING=0
log() { echo "$(date +%T) $*" >> "$LOG"; }
log "fixer start"
while :; do
  if pgrep -u "$(id -u)" -f "[G]TAIV\.exe" >/dev/null 2>&1; then
    [ "$RUNNING" = 0 ] && { log "GTAIV.exe running"; RUNNING=1; }
    for w in $(xdotool search --onlyvisible --name "Rockstar Games Launcher" 2>/dev/null); do
      case "$SEEN_WIN" in *" $w "*) continue;; esac
      xdotool windowminimize "$w" 2>/dev/null && log "minimized launcher window $w ($(xdotool getwindowname "$w" 2>/dev/null))"
      SEEN_WIN="$SEEN_WIN$w "
    done
    for p in $(pgrep -u "$(id -u)" -f "Rockstar Games.Launcher|Social Club|SocialClubHelper|RockstarService|RockstarErrorHandler"); do
      case "$SEEN_PID" in *" $p "*) continue;; esac
      tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q -i "GTAIV\.exe" && continue
      renice -n 19 -p "$p" >/dev/null 2>&1; ionice -c 3 -p "$p" 2>/dev/null
      log "low priority: pid $p $(cat /proc/$p/comm 2>/dev/null)"
      SEEN_PID="$SEEN_PID$p "
    done
  elif [ "$RUNNING" = 1 ]; then
    log "GTAIV.exe ended"; RUNNING=0; SEEN_WIN=" "; SEEN_PID=" "
  fi
  sleep 2
done
