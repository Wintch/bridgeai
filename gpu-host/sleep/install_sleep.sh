#!/bin/bash
# Install the GPU host sleep observer (run as root on the GPU host): the script, the mark tool, the systemd timer and the resume hook.
#   sudo gpu-host/sleep/install_sleep.sh [--user NAME]     NAME owns ~NAME/bridgeai/gpu-host/host.env (the gate's token), default: the user that ran sudo
# It starts in MODE=trial: it only writes what it would do (journalctl -t gpu-host-sleep, /var/lib/gpu-host-sleep/observation.jsonl).
# After a day of looking at the reasons, switch it on: sed -i 's/^MODE=.*/MODE=active/' /etc/default/gpu-host-sleep
# Undo: systemctl disable --now gpu-host-sleep.timer; remove the files listed below.
set -eu
[ "$(id -u)" = 0 ] || { echo "run as root: sudo $0" >&2; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
U=${SUDO_USER:-root}; [ "${1:-}" = --user ] && U=${2:?--user NAME}
install -m 0755 "$HERE/gpu_host_sleep.sh" /usr/local/sbin/gpu_host_sleep.sh
install -m 0755 "$HERE/gpu-host-sleep-mark" /usr/local/sbin/gpu-host-sleep-mark
install -d -m 0755 /usr/lib/systemd/system-sleep /var/lib/gpu-host-sleep
install -m 0755 "$HERE/gpu-host-sleep-resume" /usr/lib/systemd/system-sleep/gpu-host-sleep-resume
install -m 0755 "$HERE/gpu-host-wake-sources" /usr/local/sbin/gpu-host-wake-sources
install -m 0644 "$HERE/gpu-host-sleep.service" "$HERE/gpu-host-sleep.timer" "$HERE/gpu-host-wake-sources.service" /usr/lib/systemd/system/
install -d -m 0755 /etc/gpu-host-sleep/before.d     # "before sleep" tasks (gpu_host_sleep.sh): root 0755 executables, run only when the host is about to suspend
if [ ! -f /etc/default/gpu-host-sleep ]; then
  sed "s#/home/USER/#$(getent passwd "$U" | cut -d: -f6)/#" "$HERE/gpu-host-sleep.default" > /etc/default/gpu-host-sleep
  chmod 0644 /etc/default/gpu-host-sleep; echo "wrote /etc/default/gpu-host-sleep (MODE=trial)"
else echo "kept the existing /etc/default/gpu-host-sleep"; fi
systemctl daemon-reload
systemctl enable --now gpu-host-sleep.timer
systemctl enable --now gpu-host-wake-sources.service
echo "installed. Watch: journalctl -t gpu-host-sleep -f ; tail /var/lib/gpu-host-sleep/observation.jsonl ; stay awake by hand: gpu-host-sleep-mark 2 why"
