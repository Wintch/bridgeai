#!/usr/bin/env bash
# Keep the GPU power cap at the measured optimum while the home model (container `llm`) or another GPU service runs, and
# put back the previous cap when they all stop. Run every minute from cron (gpu_power.sh --install adds the line) and right after
# run_services.sh starts or stops services.
#
# Per host, in gpu-host/host.env (not in git):
#   LLM_POWER_W=130           the cap while llm runs; unset = do nothing on this host
#   LLM_POWER_CONTAINERS="llm vidgen imggen vidpost"   containers that get the cap while any of them runs (default: llm).
#                             A cap is a ceiling, not a draw: an idle service still idles at ~17 W.
#   LLM_POWER_RAISE_ONLY=1    only raise a lower cap, never lower a higher one: on a host whose GPU something else
#                             also manages (a VR power watchdog), a session that asked for more keeps it
# Needs `sudo -n nvidia-smi -pl <W>` (a NOPASSWD sudoers line for nvidia-smi -pl).
#
# Measured with a Hermes-sized Gemma turn (HERMES_ARCHITECTURE.md, "Runbook: the GPU hosts"):
#   8 GB Ampere: 100 W 7.3 s, 130 W 5.7 s, both 0.20 Wh per turn; above 159 W almost nothing  -> 130
#   8 GB Pascal: 100 W 16.7 s 0.46 Wh, 180 W 14.5 s 0.66 Wh                                    -> 100
# with gpu-unlock on, the Ampere card's best point for generation is 130 W too: SDXL base 25 steps 12.3 s / 0.434 Wh,
# a 5 s MiniMax H3 clip 395 s at 130 W against 562-579 s at 100 W (about 14 Wh against 16 Wh): faster and less energy.
# With the GPU gate installed (gate/README.md) the gate sets and restores the cap itself: this script, and its cron line, step aside.
set -u
if [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/bridgeai-gate.service" ] || systemctl --user is-active --quiet bridgeai-gate 2>/dev/null; then
  [ -t 1 ] && echo "gpu_power.sh: the GPU gate is installed and manages the power cap; nothing to do"
  exit 0
fi
SELF=$(readlink -f "$0")
cd "$(dirname "$SELF")/.."
if [ "${1:-}" = --install ]; then
  line="* * * * * flock -n /tmp/bridgeai-gpu-power.lock '$PWD/gpu-host/gpu_power.sh'"
  ( crontab -l 2>/dev/null | grep -v "gpu-host/gpu_power.sh"; echo "$line" ) | crontab -
  echo "cron: $line"
  exec "$SELF"
fi
[ -f gpu-host/host.env ] && . gpu-host/host.env
W=${LLM_POWER_W:-}
[ -n "$W" ] || exit 0
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/bridgeai-gpu-power.prev
mkdir -p "$(dirname "$STATE")"
cur=$(nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits 2>/dev/null | head -1 | cut -d. -f1)
[ -n "$cur" ] || exit 0
say() { logger -t bridgeai-gpu-power "$*" 2>/dev/null; [ -t 1 ] && echo "$*"; }

running=
for c in ${LLM_POWER_CONTAINERS:-llm}; do
  [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = true ] && running="$running $c"
done
if [ -n "$running" ]; then
  [ "$cur" = "$W" ] && exit 0
  [ "${LLM_POWER_RAISE_ONLY:-0}" = 1 ] && [ "$cur" -gt "$W" ] && exit 0
  [ -f "$STATE" ] || echo "$cur" > "$STATE"
  sudo -n nvidia-smi -pl "$W" >/dev/null 2>&1 && say "running:$running: cap $cur -> $W W"
elif [ -f "$STATE" ]; then
  prev=$(cat "$STATE")
  rm -f "$STATE"
  # Only undo our own setting: if something else changed the cap meanwhile, leave it.
  [ "$cur" = "$W" ] && sudo -n nvidia-smi -pl "$prev" >/dev/null 2>&1 && say "${LLM_POWER_CONTAINERS:-llm} stopped: cap $cur -> $prev W"
fi
exit 0
