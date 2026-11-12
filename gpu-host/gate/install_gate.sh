#!/usr/bin/env bash
# Install the GPU gate on this host as a systemd USER unit (run as the host user, who is in group docker; Linger keeps the
# unit up without a login). It replaces gpu_power.sh: the cron line of that script is removed.
#   gpu-host/gate/install_gate.sh        write the unit, enable it, (re)start it, drop the gpu_power.sh cron line
# Safe to re-run after a git pull or a host.env change: it restarts the gate so the new code and settings apply.
# Needs GATE_TOKEN in gpu-host/host.env (see gpu-host/gate/README.md). The token is read by the gate from that file, never
# written into the unit and never printed.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ENVF=${GATE_ENV_FILE:-$HERE/../host.env}
val() { [ -f "$ENVF" ] && sed -n "s/^\(export \)\{0,1\}$1=//p" "$ENVF" | tail -1 | sed "s/^['\"]//; s/['\"]\$//" || true; }
[ -n "$(val GATE_TOKEN)" ] || { echo "install_gate: GATE_TOKEN is not set in $ENVF; add a long random value first" >&2; exit 1; }
PORT=$(val GATE_PORT); PORT=${PORT:-8700}
UNIT_DIR=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/bridgeai-gate.service" <<UNIT
[Unit]
Description=bridgeai GPU gate (on-demand GPU services)
After=docker.service network-online.target

[Service]
ExecStart=/usr/bin/env python3 -I $HERE/gate.py
WorkingDirectory=$HERE
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable bridgeai-gate.service
# restart, not just start: `enable --now` leaves an already running gate on its old code and old host.env settings
systemctl --user restart bridgeai-gate.service
# The gate sets and restores the power limit itself: the old cron line would fight it.
if cron=$(crontab -l 2>/dev/null) && printf '%s\n' "$cron" | grep -q "gpu-host/gpu_power.sh"; then
  { printf '%s\n' "$cron" | grep -v "gpu-host/gpu_power.sh" || true; } | crontab -
  echo "removed the gpu_power.sh cron line"
fi
echo "gate installed (started or restarted) on port $PORT."
echo "A restart drops the gate's leases; it adopts services that are already running and they follow the idle rule."
echo "Firewall: each stack subnet that may use this host needs a rule to tcp/$PORT (the gate is protected by its token, not by the network)."
echo "Next: gpu-host/run_services.sh create   (containers stay stopped; the gate starts them on demand)"
echo "Register it for the stacks: ops/gateways_host_service.py <host> gate $PORT --token-stdin, then gateways_sync."
