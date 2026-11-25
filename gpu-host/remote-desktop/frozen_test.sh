#!/bin/bash
# Suspend a GPU host with a game open, wake it by Wake-on-LAN and time every stage, in the order a rental panel's staged boot validation shows them:
# network (ping) -> agent (ssh) -> stream (Sunshine HTTP port) -> display mode -> the game process still alive. Run it from ANOTHER machine on the LAN.
#   frozen_test.sh user@host MAC [FROZEN_SECONDS=60] [GAME_REGEX=GTAIV.exe]
# Pause the game in a menu first, and leave the Moonlight session closed. Afterwards open Moonlight: the game should continue where it was.
set -u
SSH_TARGET="${1:?usage: frozen_test.sh user@host MAC [frozen seconds] [game regex]}"; MAC="${2:?MAC}"; FROZEN="${3:-60}"; GAME="${4:-GTAIV.exe}"
IP="${SSH_TARGET#*@}"
ts() { date +%s.%N; }
since() { python3 -c "print(round($(ts)-$1,1))"; }
remote() { ssh -o ConnectTimeout=4 -o BatchMode=yes "$SSH_TARGET" "$@" 2>/dev/null; }
echo "== before"; remote "echo uptime: \$(uptime -p); echo game_pids: \$(pgrep -fc '$GAME'); nvidia-smi --query-gpu=memory.used,power.limit,clocks.sm --format=csv,noheader; DISPLAY=:0 xrandr --query | grep '\*'; cat /sys/class/net/*/device/power/wakeup 2>/dev/null | head -1"
echo "== suspend"; T0=$(ts); remote "sudo systemctl suspend" >/dev/null
until ! ping -c1 -W1 "$IP" >/dev/null 2>&1; do sleep 0.5; [ "$(python3 -c "print($(ts)-$T0>30)")" = True ] && { echo "host did not go down in 30 s"; exit 1; }; done
echo "frozen after $(since $T0) s; staying frozen $FROZEN s"; sleep "$FROZEN"
echo "== wake: magic packet"; python3 - "$MAC" <<'P'
import socket, sys
mac = bytes.fromhex(sys.argv[1].replace(":", "")); pkt = b"\xff" * 6 + mac * 16
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
for port in (9, 7): s.sendto(pkt, ("255.255.255.255", port))
P
W0=$(ts)
stage() { local name="$1"; shift; until "$@" >/dev/null 2>&1; do sleep 0.3; [ "$(python3 -c "print($(ts)-$W0>300)")" = True ] && { echo "$name: not reached in 300 s"; return 1; }; done; echo "$name: $(since $W0) s"; }
stage "1 network (ping)" ping -c1 -W1 "$IP"
stage "2 agent (ssh)" ssh -o ConnectTimeout=3 -o BatchMode=yes "$SSH_TARGET" true
stage "3 stream (Sunshine ${SUNSHINE_PORT:-47989})" bash -c "</dev/tcp/$IP/${SUNSHINE_PORT:-47989}"
sleep 2; echo "== after"; remote "echo game_pids: \$(pgrep -fc '$GAME'); nvidia-smi --query-gpu=memory.used,power.limit,clocks.sm --format=csv,noheader; DISPLAY=:0 xrandr --query | grep '\*'; echo 'resume errors (nvidia/kernel, last 5 min):'; journalctl -k --since '-5min' --no-pager 2>/dev/null | grep -iE 'nvidia|NVRM|Xid|failed|error' | tail -5 | cut -c1-170"
echo "== now open Moonlight: does the game continue where you left it?"
