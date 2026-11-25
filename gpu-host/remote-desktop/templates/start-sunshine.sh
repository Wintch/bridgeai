#!/bin/sh
# bridgeai: start Sunshine only after the login's display mode change (set-144hz.sh) has finished.
# Sunshine probes NvFBC capture at start; if the X server changes mode at that moment ("Cannot create capture session: the display
# server is in modeset") the probe fails and Moonlight answers error -1 until Sunshine is restarted. The two autostart entries used to
# run 1 s apart. Without set-144hz.sh installed this only waits a moment for the display.
export DISPLAY="${DISPLAY:-:0}"
systemctl --user import-environment DISPLAY XAUTHORITY XDG_RUNTIME_DIR
if [ -x "$HOME/bin/set-144hz.sh" ]; then
    for i in $(seq 1 60); do
        xrandr --query 2>/dev/null | grep -q '_144 .*\*' && break
        sleep 1
    done
fi
sleep 2   # let the driver settle after the mode change
systemctl --user start app-dev.lizardbyte.app.Sunshine.service
