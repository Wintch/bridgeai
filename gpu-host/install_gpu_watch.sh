#!/usr/bin/env bash
# Install the GPU watch on this host as systemd USER units (run as the host user, who is in group docker; Linger keeps the
# timers running without a login). Nothing here needs sudo and nothing here changes the driver, the kernel or the power limit.
#   gpu-host/install_gpu_watch.sh          write the units, enable the timers
# Units:
#   bridgeai-gpu-selfcheck.timer   2 min after boot, then every 10 min: `gpu_selfcheck.py auto` checks only when it is due (new boot,
#                                  driver/kernel/gpu-unlock change, weekly, or a skipped run to retry) and only on an idle card
#   bridgeai-gpu-driver-watch.timer  weekly: `driver_watch.py run` (reads apt/dpkg/dkms, writes the report, installs nothing)
#   bridgeai-gpu-outside.timer     every 5 min while the host is up: `gpu_outside.py run` (what holds the card without the gate; needs
#                                  gputaskman, GPU_WATCH.md "gputaskman"; without it the result says no_tool). Never wakes the host
# Needs the gate installed first (gpu-host/gate/install_gate.sh): the selfcheck measures inside the gate's bench mode, so host.env needs
# GATE_TOKEN and GATE_BENCH_TOKEN (the gate's own value, different from GATE_TOKEN); without them the selfcheck refuses to run and says so.
# See gpu-host/GPU_WATCH.md.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
UNIT_DIR=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/bridgeai-gpu-selfcheck.service" <<UNIT
[Unit]
Description=bridgeai GPU selfcheck (does the card still perform as unlocked?)
After=docker.service bridgeai-gate.service

[Service]
Type=oneshot
ExecStart=/usr/bin/env python3 -I $HERE/gpu_selfcheck.py auto
WorkingDirectory=$HERE
Nice=10
TimeoutStartSec=600
UNIT
cat > "$UNIT_DIR/bridgeai-gpu-selfcheck.timer" <<UNIT
[Unit]
Description=bridgeai GPU selfcheck: at boot and whenever it is due

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min

[Install]
WantedBy=timers.target
UNIT
cat > "$UNIT_DIR/bridgeai-gpu-driver-watch.service" <<UNIT
[Unit]
Description=bridgeai driver watch (newer NVIDIA driver, kernel and DKMS state; reads only)

[Service]
Type=oneshot
ExecStart=/usr/bin/env python3 -I $HERE/driver_watch.py run
WorkingDirectory=$HERE
Nice=10
TimeoutStartSec=600
UNIT
cat > "$UNIT_DIR/bridgeai-gpu-driver-watch.timer" <<UNIT
[Unit]
Description=bridgeai driver watch, weekly

[Timer]
OnCalendar=weekly
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
UNIT
cat > "$UNIT_DIR/bridgeai-gpu-outside.service" <<UNIT
[Unit]
Description=bridgeai: GPU use that did not go through the gate (reads only)
After=docker.service bridgeai-gate.service

[Service]
Type=oneshot
ExecStart=/usr/bin/env python3 -I $HERE/gpu_outside.py run
WorkingDirectory=$HERE
Nice=10
TimeoutStartSec=120
UNIT
cat > "$UNIT_DIR/bridgeai-gpu-outside.timer" <<UNIT
[Unit]
Description=bridgeai: look for GPU use outside the gate every 5 minutes

[Timer]
OnBootSec=3min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now bridgeai-gpu-selfcheck.timer bridgeai-gpu-driver-watch.timer bridgeai-gpu-outside.timer
[ -x "$HOME/.local/bin/gputaskman" ] || echo "NOTE: no ~/.local/bin/gputaskman: gpu_outside.py reports no_tool until it is installed (GPU_WATCH.md \"gputaskman\")." >&2
if ! grep -qs '^[[:space:]]*\(export[[:space:]]\+\)\?GATE_BENCH_TOKEN=.' "$HERE/host.env"; then
  echo "WARNING: no GATE_BENCH_TOKEN in $HERE/host.env: the selfcheck will refuse to run (and the ops bot will say so) until it is set to the gate's value." >&2
fi
echo "installed. Look: python3 $HERE/gpu_selfcheck.py status ; python3 $HERE/driver_watch.py status ; python3 $HERE/gpu_outside.py status"
echo "First report now: python3 $HERE/driver_watch.py run"
