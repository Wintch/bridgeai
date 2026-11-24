#!/bin/bash
# Reboot a GPU host that streams games and time what has to come back by itself, from the moment it goes down:
# network (ping) -> agent (ssh) -> stream (Sunshine HTTP port) -> display mode (the 144 Hz mode set at login), then a list of checks
# (failed units, firewall table, Sunshine, the gate, the idle-sleep timer, the GPU power limit, gpu_unlock, kept video memory, containers).
# Run it from ANOTHER machine on the LAN, with nobody streaming:   cold_boot_test.sh user@host
H="${1:?usage: cold_boot_test.sh user@host}"; IP="${H#*@}"
now() { date +%s.%N; }; el() { python3 -c "print(round($(now)-$1,1))"; }
T0=$(now); ssh -o ConnectTimeout=5 $H 'sudo systemctl reboot' >/dev/null 2>&1
until ! ping -c1 -W1 $IP >/dev/null 2>&1; do sleep 0.5; [ "$(python3 -c "print($(now)-$T0>60)")" = True ] && { echo "did not go down"; exit 1; }; done
echo "down after $(el $T0) s"; R0=$(now)
stage() { local n="$1"; shift; until "$@" >/dev/null 2>&1; do sleep 0.5; [ "$(python3 -c "print($(now)-$R0>420)")" = True ] && { echo "$n: NOT reached in 420 s"; return 1; }; done; echo "$n: $(el $R0) s after going down"; }
stage "1 ping" ping -c1 -W1 $IP
stage "2 ssh" ssh -o ConnectTimeout=3 -o BatchMode=yes $H true
stage "3 Sunshine 47989" bash -c "</dev/tcp/$IP/47989"
disp() { ssh -o ConnectTimeout=3 -o BatchMode=yes $H 'DISPLAY=:0 xrandr --query' 2>/dev/null | grep -qF '1920x1080_144 144.00*'; }
stage "4 display 1920x1080_144 active" disp
echo "== checks"; ssh -o ConnectTimeout=5 $H 'echo "uptime: $(uptime -p)"; echo "failed units: $(systemctl --failed --no-legend | wc -l) system, $(systemctl --user --failed --no-legend | wc -l) user"; systemctl --failed --no-legend | cut -c1-100; echo "firewall unit: $(systemctl is-active bridgeai-fw.service) table: $(sudo nft list tables | grep -c bridgeai_in)"; echo "sunshine: $(systemctl --user is-active app-dev.lizardbyte.app.Sunshine.service)"; echo "gate: $(curl -s --max-time 4 http://127.0.0.1:8700/state | head -c 120)"; echo "sleep observer: $(systemctl is-active gpu-host-sleep.timer) mode $(grep ^MODE= /etc/default/gpu-host-sleep)"; nvidia-smi --query-gpu=driver_version,power.limit,pstate,clocks.max.sm --format=csv,noheader; grep -o "gpu_unlock[^ ]*" /proc/cmdline; cat /proc/driver/nvidia/params | grep -E "PreserveVideoMemoryAllocations"; echo "xrandr: $(DISPLAY=:0 xrandr --query | grep "\*" | tr -s " ")"; echo "docker: $(docker ps --format "{{.Names}}" | tr "\n" " ")"; echo "probe running: $(pgrep -fc stream_probe.py)"; echo "autostart 144 script: $(ls ~/.config/autostart/bridgeai-144hz.desktop >/dev/null 2>&1 && echo yes)"' 2>&1
