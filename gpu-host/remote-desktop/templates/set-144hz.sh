#!/bin/sh
# bridgeai: put the dummy HDMI output on 1080p 144 Hz at every login (the Modeline in xorg.conf.d is not offered by the driver; the runtime mode is).
# Needs the 20-bridgeai-144hz.conf ModeValidation (AllowNonEdidModes). Idempotent.
export DISPLAY=:0
for i in $(seq 1 30); do xrandr --query >/dev/null 2>&1 && break; sleep 1; done
xrandr --newmode "1920x1080_144" 332.77 1920 1968 2000 2080 1080 1083 1088 1111 +hsync -vsync 2>/dev/null
xrandr --addmode HDMI-0 1920x1080_144 2>/dev/null
xrandr --output HDMI-0 --mode 1920x1080_144
