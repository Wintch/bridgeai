#!/bin/bash
# B1 (Resolve part): fresh Resolve Studio per run in the desktop session, REF-60 built by b1_resolve.py, then quit.
# measure.py wraps the whole run (cold start + build + renders). Usage: b1_resolve.sh [runs=3]
set -uo pipefail
cd "$(dirname "$0")"
export DISPLAY=:0 XAUTHORITY=$(ls /run/user/1000/.mutter-Xwaylandauth.* | head -1) XDG_RUNTIME_DIR=/run/user/1000 \
       DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
pgrep -f /opt/resolve/bin/resolve >/dev/null && { echo "Resolve already running: not touching it"; exit 1; }
quit() { python3 -c "import sys; sys.path.insert(0, '/opt/resolve/Developer/Scripting/Modules'); import DaVinciResolveScript as d; r=d.scriptapp('Resolve'); r and r.Quit()"
  for _ in $(seq 40); do pgrep -f /opt/resolve/bin/resolve >/dev/null || return; sleep 2; done; pkill -f /opt/resolve/bin/resolve; }
for rep in $(seq 1 ${1:-3}); do
  python3 measure.py b1/resolve/r$rep --out-units 59 --unit s -- bash -c '
    setsid nohup /opt/resolve/bin/resolve >/dev/null 2>&1 < /dev/null &
    python3 b1_resolve.py r'$rep' | tee -a results/b1_resolve.jsonl'
  quit; sleep 5
done
