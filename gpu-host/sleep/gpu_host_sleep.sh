#!/bin/bash
# Can this GPU host suspend to RAM now? Run every minute by gpu-host-sleep.timer (see README.md). One JSON line per run goes to
# $STATE_DIR/observation.jsonl; the host suspends only after IDLE_MIN minutes in a row without a reason to stay up.
#   MODE=trial  (default) writes "would sleep" and does nothing
#   MODE=active suspends with `systemctl suspend`
# Reasons to stay up (any one is enough):
#   session      somebody is logged in over SSH (a pts session; the desktop's own session does not count)
#   gpu          the GPU works (utilisation above GPU_BUSY_PCT, a compute process, or a video encoder session such as a stream)
#   load         load average above LOAD_MAX
#   net          more than NET_KBS_MAX KB/s on the main interface during the last minute (a copy, a download, a stream)
#   apt          apt or dpkg is running
#   docker       a container is running that is not in IGNORE_CONTAINERS (services the gate starts show up here too)
#   process      a program that matches BUSY_PROCS runs (a game, an editor, a render)
#   gate         the GPU gate says sleep_ok is false (a service up or starting, a lease, a bench); needs GATE_TOKEN in HOST_ENV
#   maintenance  the operator's mark (gpu-host-sleep-mark): "<until-epoch> <reason>", it expires by itself
# Settings: /etc/default/gpu-host-sleep (or the file named by GPU_SLEEP_CONF). Every command can be replaced by an environment variable
# of the same name in capitals (WHO, NVSMI, DOCKER, PGREP, CURL, SUSPEND) so the selftest runs with fakes.
set -u
CONF=${GPU_SLEEP_CONF:-/etc/default/gpu-host-sleep}
[ -f "$CONF" ] && . "$CONF"
MODE=${MODE:-trial}; IDLE_MIN=${IDLE_MIN:-10}; LOAD_MAX=${LOAD_MAX:-2.0}; NET_KBS_MAX=${NET_KBS_MAX:-200}; GPU_BUSY_PCT=${GPU_BUSY_PCT:-5}
BUSY_PROCS=${BUSY_PROCS:-'(^|/)steam$|steamwebhelper|SteamLaunch|/opt/resolve/bin/resolve|(^|/)blender( |$)|(^|/)ffmpeg( |$)'}
IGNORE_CONTAINERS=${IGNORE_CONTAINERS:-}
GATE_URL=${GATE_URL:-http://127.0.0.1:8700/state}; HOST_ENV=${HOST_ENV:-}
STATE_DIR=${STATE_DIR:-/var/lib/gpu-host-sleep}; MAINT=${MAINT_FILE:-$STATE_DIR/maintenance}
WHO=${WHO:-who}; NVSMI=${NVSMI:-nvidia-smi}; DOCKER=${DOCKER:-docker}; PGREP=${PGREP:-pgrep}; CURL=${CURL:-curl}; SUSPEND=${SUSPEND:-systemctl suspend}
NET_IFACE=${NET_IFACE:-$(ip route show default 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')}
NET_STATS=${NET_STATS:-/sys/class/net/$NET_IFACE/statistics}; LOADAVG=${LOADAVG:-/proc/loadavg}; NOW=${NOW_EPOCH:-$(date +%s)}
mkdir -p "$STATE_DIR"
reasons=()

s=$($WHO 2>/dev/null | awk '$2 ~ /^pts\//' | wc -l); [ "$s" -gt 0 ] && reasons+=("session:$s")

g=$($NVSMI --query-gpu=utilization.gpu,encoder.stats.sessionCount --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
util=${g%%,*}; enc=${g##*,}; apps=$($NVSMI --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c .)
[[ "${util:-0}" =~ ^[0-9]+$ ]] || util=0; [[ "${enc:-0}" =~ ^[0-9]+$ ]] || enc=0
{ [ "$util" -gt "$GPU_BUSY_PCT" ] || [ "$apps" -gt 0 ] || [ "$enc" -gt 0 ]; } && reasons+=("gpu:${util}%/${apps}proc/${enc}enc")

l=$(cut -d' ' -f1 "$LOADAVG" 2>/dev/null); awk -v l="${l:-0}" -v m="$LOAD_MAX" 'BEGIN{exit !(l>m)}' && reasons+=("load:$l")

if [ -r "$NET_STATS/rx_bytes" ]; then
  rx=$(cat "$NET_STATS/rx_bytes"); tx=$(cat "$NET_STATS/tx_bytes")
  if [ -f "$STATE_DIR/net.prev" ]; then
    read -r prx ptx pt < "$STATE_DIR/net.prev"; dt=$((NOW - pt))
    if [ "$dt" -gt 0 ] && [ "$dt" -le 300 ]; then kbs=$(( (rx - prx + tx - ptx) / 1024 / dt )); [ "$kbs" -gt "$NET_KBS_MAX" ] && reasons+=("net:${kbs}KB/s"); fi
  fi
  echo "$rx $tx $NOW" > "$STATE_DIR/net.prev"
fi

$PGREP -x 'apt|apt-get|dpkg|unattended-upgr' >/dev/null 2>&1 && reasons+=("apt")

run=$($DOCKER ps --format '{{.Names}}' 2>/dev/null | grep -vxF -f <(printf '%s\n' $IGNORE_CONTAINERS) | tr '\n' ' ')
[ -n "${run// /}" ] && reasons+=("docker:${run% }")

[ -n "$BUSY_PROCS" ] && $PGREP -f "$BUSY_PROCS" >/dev/null 2>&1 && reasons+=("process")

if [ -n "$HOST_ENV" ] && [ -r "$HOST_ENV" ]; then
  tok=$(sed -n 's/^GATE_TOKEN=//p' "$HOST_ENV" | tail -1 | sed "s/^['\"]//; s/['\"]\$//")
  if [ -n "$tok" ]; then
    gj=$($CURL -s -m 4 -H "Authorization: Bearer $tok" "$GATE_URL" 2>/dev/null)
    gw=$(printf '%s' "$gj" | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print("" if d.get("sleep_ok") is not False else ",".join(str(x) for x in (d.get("sleep_why") or ["busy"])))
except Exception:
    print("")' 2>/dev/null)
    [ -n "$gw" ] && reasons+=("gate:$gw")
  fi
fi

if [ -f "$MAINT" ]; then
  read -r mt_until mt_why < "$MAINT" || true
  if [[ "${mt_until:-}" =~ ^[0-9]+$ ]] && [ "$mt_until" -gt "$NOW" ]; then reasons+=("maintenance:${mt_why:-by-hand}")
  else rm -f "$MAINT"; logger -t gpu-host-sleep "maintenance mark expired or broken: removed" 2>/dev/null || true; fi
fi

lf="$STATE_DIR/idle_minutes"; idle=0
if [ ${#reasons[@]} -eq 0 ]; then
  # a counter that was not touched for more than 150 s means the host was asleep or the timer did not run: start again
  if [ -f "$lf" ] && [ $(( NOW - $(stat -c %Y "$lf") )) -le 150 ]; then idle=$(( $(cat "$lf" 2>/dev/null || echo 0) + 1 )); else idle=1; fi
fi
echo "$idle" > "$lf"
action=""
if [ "$idle" -ge "$IDLE_MIN" ]; then
  if [ "$MODE" = active ]; then action="sleep"; else action="trial: would sleep"; fi
fi
python3 -c 'import json,sys; m=sys.argv[4:]; d={"t":int(sys.argv[1]),"idle":int(sys.argv[2]),"reasons":m,"mode":sys.argv[3]}
print(json.dumps(d))' "$NOW" "$idle" "$MODE" "${reasons[@]}" >> "$STATE_DIR/observation.jsonl"
[ -f "$STATE_DIR/observation.jsonl" ] && [ "$(stat -c %s "$STATE_DIR/observation.jsonl")" -gt 1048576 ] && tail -n 2000 "$STATE_DIR/observation.jsonl" > "$STATE_DIR/observation.jsonl.new" && mv -f "$STATE_DIR/observation.jsonl.new" "$STATE_DIR/observation.jsonl"
if [ "$action" = sleep ]; then
  echo 0 > "$lf"
  logger -t gpu-host-sleep "suspending: idle ${idle} min, no reason to stay up" 2>/dev/null || true
  [ -n "${ON_SLEEP_CMD:-}" ] && $ON_SLEEP_CMD >/dev/null 2>&1 || true
  sync; $SUSPEND
elif [ -n "$action" ]; then
  logger -t gpu-host-sleep "$action (idle ${idle} min)" 2>/dev/null || true
fi
exit 0
