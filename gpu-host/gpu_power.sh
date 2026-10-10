#!/usr/bin/env bash
# Keep the GPU power cap at the measured optimum while the home model (container `llm`) runs, and put back the
# previous cap when it stops. Run every minute from cron (gpu_power.sh --install adds the line) and right after
# run_services.sh starts or stops services.
#
# Per host, in gpu-host/host.env (not in git):
#   LLM_POWER_W=130           the cap while llm runs; unset = do nothing on this host
#   LLM_POWER_RAISE_ONLY=1    only raise a lower cap, never lower a higher one: on a host whose GPU something else
#                             also manages (a VR power watchdog), a session that asked for more keeps it
# Needs `sudo -n nvidia-smi -pl <W>` (a NOPASSWD sudoers line for nvidia-smi -pl).
#
# Measured 2026-10-09/10 with a Hermes-sized Gemma turn (HERMES_ARCHITECTURE.md, "Runbook: the GPU hosts"):
#   3060 Ti: 100 W 7.3 s, 130 W 5.7 s, both 0.20 Wh per turn; above 159 W almost nothing  -> 130
#   1070 Ti: 100 W 16.7 s 0.46 Wh, 180 W 14.5 s 0.66 Wh                                    -> 100
set -u
cd "$(dirname "$0")/.."
if [ "${1:-}" = --install ]; then
  line="* * * * * $PWD/gpu-host/gpu_power.sh"
  ( crontab -l 2>/dev/null | grep -v "gpu-host/gpu_power.sh"; echo "$line" ) | crontab -
  echo "cron: $line"
  exec "$0"
fi
[ -f gpu-host/host.env ] && . gpu-host/host.env
W=${LLM_POWER_W:-}
[ -n "$W" ] || exit 0
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/bridgeai-gpu-power.prev
mkdir -p "$(dirname "$STATE")"
cur=$(nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits 2>/dev/null | head -1 | cut -d. -f1)
[ -n "$cur" ] || exit 0
say() { logger -t bridgeai-gpu-power "$*" 2>/dev/null; [ -t 1 ] && echo "$*"; }

if [ "$(docker inspect -f '{{.State.Running}}' llm 2>/dev/null)" = true ]; then
  [ "$cur" = "$W" ] && exit 0
  [ "${LLM_POWER_RAISE_ONLY:-0}" = 1 ] && [ "$cur" -gt "$W" ] && exit 0
  [ -f "$STATE" ] || echo "$cur" > "$STATE"
  sudo -n nvidia-smi -pl "$W" >/dev/null 2>&1 && say "llm running: cap $cur -> $W W"
elif [ -f "$STATE" ]; then
  prev=$(cat "$STATE")
  rm -f "$STATE"
  # Only undo our own setting: if something else changed the cap meanwhile, leave it.
  [ "$cur" = "$W" ] && sudo -n nvidia-smi -pl "$prev" >/dev/null 2>&1 && say "llm stopped: cap $cur -> $prev W"
fi
exit 0
