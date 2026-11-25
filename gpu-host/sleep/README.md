# GPU host sleep

A GPU host that is only needed when there is work should sleep in between: suspend to RAM draws about nothing, and wake-on-LAN brings it back in
about ten seconds (measured on a Ryzen 5 5600X with an RTX 3060 Ti: 11 s from the magic packet to SSH answering, no reboot, the unlock module
and the driver intact). This directory holds the part that decides **when it may sleep**; waking is done by whoever needs the host (the pipeline,
a stack through the machine-power provider, the operator) with a magic packet.

`gpu_host_sleep.sh` runs every minute (`gpu-host-sleep.timer`). It adds up the reasons to stay awake (see the header of the script: SSH sessions,
GPU or encoder activity, load, network traffic, apt, containers, programs such as a game or an editor, the GPU gate's `sleep_ok`, and the operator's
mark). Only after `IDLE_MIN` minutes in a row without any reason, and only with `MODE=active`, it runs `systemctl suspend`. `MODE=trial` (the default)
writes the same decision to `/var/lib/gpu-host-sleep/observation.jsonl` and to the journal (`journalctl -t gpu-host-sleep`) and never suspends: run it a
day, look at what kept the host up, then switch to `active`.

| File | Purpose |
|---|---|
| `gpu_host_sleep.sh` | the decision, one JSON line per run |
| `gpu-host-sleep.default` | settings, copied to `/etc/default/gpu-host-sleep` |
| `gpu-host-sleep.service`, `.timer` | the minute timer |
| `gpu-host-sleep-resume` | `systemd-sleep` hook: restarts the idle count after a resume, logs how long it slept, runs `ON_WAKE_CMD` |
| `gpu-host-sleep-mark` | `gpu-host-sleep-mark 2 why` keeps the host awake for 2 h (24 at most; it expires by itself); `off` removes it |
| `install_sleep.sh` | installs all of it |
| `gpu_host_sleep_selftest.py` | offline checks with fake commands |

Needs for waking: the NIC's wake-on-LAN set to `g` (a udev rule that runs `ethtool -s %k wol g`, **matching the card by MAC, not by interface name**: the name moves when PCI hardware is added, see `../remote-desktop/REMOTE_DESKTOP.md`, template `90-bridgeai-wol.rules.example`), "wake on LAN / PCIe" enabled in the firmware, and the
host's MAC known to whoever sends the packet. After a resume the GPU gate and the unlock module need nothing (`gpu_unlock` re-unlocks on resume from suspend to RAM,
see `../MODELS_TUNING.md`); the power cap returns to the card's default until the gate sets one for the next job.

Stay awake while you work on the host: an open SSH session counts, so does `gpu-host-sleep-mark`. The desktop's own session (an autologin) does not count, but a
stream (an encoder session) does.
