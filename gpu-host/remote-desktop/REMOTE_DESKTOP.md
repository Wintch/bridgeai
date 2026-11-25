# Remote desktop and game streaming on a GPU host: what was set up, what was measured, what breaks

Written 2026-11-23 from a Debian 13 host (RTX 3060 Ti, NVIDIA 595 open modules, XFCE on a real HDMI monitor, auto-login). Sunshine runs natively as a user
service and the person connects with Moonlight; the host is woken by a magic packet and suspends itself when idle (`gpu-host/sleep/`). Nothing here uses a
container: the container questions are in `aibridge/INTEGRATIONS_MAP.md` (remote desktop section).

## What runs
- **Sunshine** (Debian package, user unit). The card's encoder does H.264 and HEVC (no AV1 on this card) and NvFBC captures the X screen. A 1080p60 HEVC
  stream at about 15 Mb/s used about 9 % of the encoder and under 10 % of the GPU. Start it with `systemctl --user start sunshine` after a reboot until
  its autostart is confirmed. Pair a client with the PIN from `GET /api/pin` (the request carries a `pairing_id`).
- **Steam** from Debian's `steam-installer`: the first run shows an installer dialog on the desktop (the client lands in `~/.steam/debian-installation`).
  Proton Experimental runs the Windows games; native Linux games run directly on the host's libraries. The Steam account is the person's own (Subscriber Agreement).
- **A browser** from Debian (`firefox-esr`, security updates from Debian's own repository).
- **Signed third-party packages:** a vendor `.deb` is accepted only after its checksum file is verified against a pinned signing-key fingerprint
  (see `gpu-host/effectcraft/Dockerfile`) and its maintainer scripts are read; install it with `apt install ./file.deb` so the dependencies come from Debian.

## Audio: there is no sound card, make one
A fresh host has no sound server: Sunshine logs `Couldn't connect to pulseaudio: Access denied` and `There will be no audio`, and games fall back to a null output.
Install `pipewire pipewire-pulse wireplumber pulseaudio-utils`, enable `pipewire.socket pipewire-pulse.socket wireplumber.service` for the user, and add a virtual
sink in `~/.config/pipewire/pipewire-pulse.conf.d/10-sunshine-sink.conf`:

    pulse.cmd = [
      { cmd = "load-module" args = "module-null-sink sink_name=sunshine-stereo sink_properties=device.description=Sunshine-Stereo" flags = [ ] }
    ]

`pactl set-default-sink sunshine-stereo` and `audio_sink = sunshine-stereo` in `sunshine.conf`. Check: play a test tone to the sink and read
`sunshine-stereo.monitor` with `parec`; the peak must match the tone. A game opened before the sink existed keeps its null output: restart it.

**WirePlumber spins on an idle host.** With WirePlumber 0.5.8 / PipeWire 1.4.2 (Debian 13) the main thread sat at about 48 % of a core
with no audio playing, and `strace` showed it re-reading `/dev/snd` (`getdents64`, `access` on every `pcmC*`) about 5,000 times a second.
Disabling the two ALSA cards by name did not stop it; switching the whole ALSA monitor off did (0 % CPU) and the Sunshine sink kept working
(a 440 Hz tone played into the sink read back on its monitor). The host has no audio device that matters, so
`~/.config/wireplumber/wireplumber.conf.d/51-no-alsa-monitor.conf` holds:

    wireplumber.profiles = {
      main = { monitor.alsa = disabled }
    }

then `systemctl --user restart wireplumber`. Cost: no local HDMI or analog audio on that host (the remote desktop does not use it). Root cause
inside WirePlumber not found; not reproduced on another machine, so it may depend on the NVIDIA HDMI codec or the dummy plug.

## Input: the absolute pointer is also a joystick
Sunshine creates virtual devices through `/dev/uinput` (the user needs the `input` group; the node was `root:input 0660` with an ACL). Its absolute pointer
(`libvirtualhid Mouse (Absolute)`) is also exposed by the kernel as `/dev/input/js0`, with the cursor position as two axes. Games that read joysticks (SDL,
Unity, several native titles) see a stick held to one side: the camera turns and looks down by itself while the menus, which use the pointer, work.
- **The fix that worked:** in Moonlight turn OFF "Optimize mouse for remote desktop (absolute mouse mode)" for games (relative mode feeds the relative device).
- **Belt and braces** (`/etc/udev/rules.d/61-*-sunshine-nojs.rules`), so no client can trigger it: make that one joystick node unreadable. Real and virtual
  gamepads are other devices and keep working.

      SUBSYSTEM=="input", KERNEL=="js[0-9]*", ATTRS{name}=="libvirtualhid Mouse*", OWNER="root", GROUP="root", MODE="0000", TAG-="uaccess"

  Apply with `udevadm control --reload && udevadm trigger --subsystem-match=input --action=change`; restart the game.
- Moonlight forwards gamepads connected to the client PC; Sunshine turns them into virtual gamepads. Not tested with a real pad yet.

## Old native games: `libudev.so.0`
An old Unity 5.x native build (2018) hung right after its assemblies loaded: it looks for `libudev.so.0` and Debian 13 ships only `.so.1`. The log
(`~/.config/unity3d/<company>/<product>/Player.log`) shows hundreds of `Fallback handler could not load library ...libudev.so.0`. Fix:
`sudo ln -s libudev.so.1 /usr/lib/x86_64-linux-gnu/libudev.so.0`, then start the game again through Steam. The same title can hang on exit (black window, all
threads in a futex): `pkill -x <binary>` ends it. Whether that is a slow exit or a deadlock was not measured yet.

## Frame limiter without vsync, and post-process anti-aliasing
- **MangoHud** (Debian, install `mangohud` and `mangohud:i386` because many Windows games are 32-bit). Config `~/.config/MangoHud/MangoHud.conf`:
  `fps_limit=60`, `fps_limit_method=late`, `no_display`, `toggle_hud=Shift_R+F12`, `toggle_fps_limit=Shift_L+F1`. Steam launch option `mangohud %command%`,
  per game `MANGOHUD_CONFIG=fps_limit=90 mangohud %command%`. Measured with `glxgears`, vsync off: unlimited about 24 000 fps, limit 60 gives 59.7,
  limit 120 gives 120.3. Limiting to what the stream carries lowers heat and latency compared with vsync. Proton games on DXVK also take `DXVK_FRAME_RATE`.
- **vkBasalt** (Debian, amd64 and i386): SMAA, FXAA and CAS for Vulkan and DXVK games, `~/.config/vkBasalt/vkBasalt.conf`
  (`effects = smaa:cas`, `toggleKey = Home`), start with `ENABLE_VKBASALT=1`. Check the layer with `VK_LOADER_DEBUG=layer vulkaninfo`. A game that has its own
  AA or limiter (or a community fix that adds them) should use those, not two layers at once.

## Display refresh: the stream cannot be faster than the screen
Sunshine captures the X screen at the mode it runs. The monitor on this host offers 1920x1080 at 60 Hz as its best mode (`xrandr`: no 120 Hz mode, a 256-byte
EDID), so 120 fps needs a display that really runs 120 Hz: a high-refresh monitor, a dummy HDMI plug whose EDID advertises 1080p120, or a virtual display
(a custom EDID forced on a disconnected output in the Xorg configuration, which touches the live desktop: keep a backup and an SSH session). Also raise
the bitrate in Moonlight for 120 fps (about 30-40 Mb/s at 1080p HEVC).

**144 Hz on a plug that advertises only 1080p60 (done, tested after two display-manager restarts).** The output is an HDMI receiver that reports one 256-byte
EDID. Two pieces are needed: `/etc/X11/xorg.conf.d/20-bridgeai-144hz.conf` with `ModeValidation "HDMI-0: AllowNonEdidModes, NoEdidMaxPClkCheck, NoMaxPClkCheck,
NoVertRefreshCheck, NoHorizSyncCheck"` (without it `xrandr --addmode` fails with BadMatch), and the mode itself added at runtime. A `Modeline` in the same
file was read but not offered by the driver, so a login script does it: `xrandr --newmode "1920x1080_144" 332.77 1920 1968 2000 2080 1080 1083 1088 1111 +hsync
-vsync`, `--addmode HDMI-0 ...`, `--output HDMI-0 --mode ...` (XFCE autostart, idempotent). The timings are reduced blanking by hand because `cvt -r` only takes
multiples of 60: 2080 x 1111 x 144 = 332.77 MHz, under the 340 MHz HDMI 1.4 limit (the GPU's HDMI reports 600 MHz). Applying the config restarts the display
manager (autologin brings the session and Sunshine back, about 40 s): do it when nobody streams (`nvidia-smi` encoder session count 0). Undo: remove the file and the
autostart entry, restart the display manager. Whether Moonlight sustains 144 fps depends on the client and the bitrate; the host side is only the mode.

## Frozen state: suspend with a game open, wake by Wake-on-LAN, continue
`frozen_test.sh user@host MAC [frozen seconds] [game regex]` (run from another LAN machine) suspends the host, waits, sends a magic packet and times the stages in the order a rental panel's staged boot validation shows them: network, agent (SSH), stream port. Measured on the GPU host with a Proton game running (GTA IV, 2.4 GB of VRAM) and the 144 Hz mode: down after 7.9 s, 60 s frozen, then ping answered 11.4 s after the packet, SSH 11.5 s, Sunshine's port 11.6 s. Afterwards: no reboot (uptime unchanged), the game processes alive (same count), VRAM in use 2367 -> 2357 MiB, power limit still 240 W, 1995 MHz, display mode still 1920x1080 at 144 Hz, Sunshine and the firewall table intact, the gate answering. What makes it work: `NVreg_PreserveVideoMemoryAllocations=1`, the nvidia-suspend/resume/hibernate services enabled, `mem_sleep` deep (S3), WoL `g` on the NIC. The sleep observer never suspends a machine with a game open (Steam, GPU load, a stream or traffic all count as work), so this is an explicit order, as a rental panel's suspend button does, never the idle timer. The last check is a person's: connect with Moonlight and see that the game continues where it was.

## First launch of a game: shader compilation (tell the person to wait)
The first time Steam starts a Windows game under Proton it pre-compiles the Vulkan shaders (`fossilize_replay` workers, 12 at first, in batches) before the game window exists. Measured with GTA IV on this host (a 6 GB shader cache): more than 12 minutes of 12 CPU-bound workers, the GPU nearly idle, and the stream showing a desktop with nothing to play. Entering earlier means a half-loaded game. The gate's `GET /host/state` reports it: `shaders: {compiling, workers, appids}` and `ready` (the game runs, the stream is up and nothing compiles); a short grace covers the gaps between batches. A bot should say "compiling shaders, wait" while `compiling` is true and only hand out the way in when `ready` is true. Later launches of the same game reuse the cache.

A game started from the gate's own service dies when the gate restarts (systemd stops the whole control group): that happened once. The launcher therefore starts Steam in its own transient user unit (`systemd-run --user`, `KillMode=process`); restarting the gate with a game running was tested and the game survives.

## Cold boot: what has to come back by itself
Found by a reboot test: **Sunshine did not start after a cold boot.** Its packaged user unit is `WantedBy=graphical-session.target`, and XFCE never reaches that target, so with autologin the desktop came up and nothing listened on 47989 (it looked fine after a display-manager restart only because the user manager and the unit were already running). Fix: an XFCE autostart entry that runs `systemctl --user import-environment DISPLAY XAUTHORITY XDG_RUNTIME_DIR; systemctl --user start app-dev.lizardbyte.app.Sunshine.service`. The 144 Hz mode comes back the same way (autostart script). Measured after the fix, from the moment the host went down: ping 37.0 s, SSH 37.2 s, Sunshine's port 38.7 s, display already at 1920x1080 144 Hz 38.9 s. Also checked after the boot: no failed units, the firewall table loaded, the gate answering, the idle-sleep timer active, the 240 W power limit back (the default; the gate lowers it per job), `gpu_unlock` still on the kernel command line and `PreserveVideoMemoryAllocations=1`. Containers with `restart: no` (the by-design rule for GPU services, and the browser desktop too) stay stopped.

## A real monitor on the output: no 144 Hz

The 144 Hz mode exists for the dummy plug. With a real 60 Hz monitor on the same output the login script still forced 144 Hz: the screen stayed dark, and Sunshine's capture failed with `the display server is in modeset` on every connection (Moonlight error -1, the same symptom as the boot race below, with a different cause). `touch ~/.config/bridgeai/no-144hz` makes `set-144hz.sh` do nothing and `start-sunshine.sh` stop waiting for it; remove the file when the dummy plug is back. To go back at once: `xrandr --output HDMI-0 --mode 1920x1080 --rate 60` and restart Sunshine. A different EDID on `HDMI-0` (`xrandr --prop`) is how to tell which one is plugged in.

## Moonlight "error -1" after a boot: Sunshine started during the mode change

Sunshine probes NvFBC capture when it starts. The login's own autostart (`set-144hz.sh`) changes the display mode a second later; a probe that overlaps the mode change fails with `Cannot create capture session: the display server is in modeset` (Sunshine's log), the capture stays broken, and Moonlight shows **error -1** on connect although the ports answer. Restarting Sunshine (`systemctl --user restart app-dev.lizardbyte.app.Sunshine`) fixes a running host; `templates/start-sunshine.sh` fixes the cause: the Sunshine autostart waits until the 144 Hz mode is current (up to 60 s), then starts. The other known `Error:` lines at startup (`Couldn't release NvFBC context`, `av1_nvenc` unsupported on this card, `Failed to create client: Daemon not running`) appear on healthy starts too.

## The network card's name moves when hardware is added

Found on the reference host: after an extra NVMe went into a free M.2 slot, the host booted and **did not come up on the network**, and Wake-on-LAN
could not be tested either. Debian's predictable names (`enp3s0`) are built from the PCI bus number, and a new device on the chipset's bus
renumbers the ones after it: the Realtek card went from `enp3s0` to `enp4s0` (`lspci` showed it at `04:00.0`). Everything that named the
old interface was then wrong at once:

- `/etc/network/interfaces` had `iface enp3s0 inet dhcp`: no address, so no ping, no SSH, no Sunshine, and the rental panel's agent never
  reported (the panel showed the machine offline, which looks exactly like "did not boot"). With only a dummy plug there is no
  screen to show it.
- The Wake-on-LAN udev rule matched `KERNEL=="enp3s0"`: it silently stopped arming `wol g`, so the next sleep could not be woken. It does not
  fail loudly; `ethtool IFACE | grep Wake-on` printing `d` is the only sign.

What to do, in order of cost:
1. **After any change of PCI hardware** (NVMe, a card, even a BIOS update that changes the slot layout), check `ip -br link` against the name in
   the network config and in every rule before leaving the machine; read it with a real screen once, not through the dummy plug.
2. **Match by MAC, never by name, in udev rules**: `templates/90-bridgeai-wol.rules.example`.
3. **Optionally pin a name** with a systemd `.link` file (`templates/10-bridgeai-lan.link.example`) and use that name everywhere. Do this
   with a screen and keyboard at hand.
4. If the machine is dark after a hardware change: the panel (`status.json`) says the agent has not reported, a LAN sweep finds nothing, and the
   first suspect is the interface name, before the cable, the BIOS boot order or the power. Boot order is the second suspect: a new drive can take the first place.

## Files in this folder, and where each one goes
| file | goes to | what for |
|---|---|---|
| `templates/20-bridgeai-144hz.conf` | `/etc/X11/xorg.conf.d/` | mode validation so the driver accepts a 1080p144 mode the plug's EDID does not list; restart the display manager |
| `templates/set-144hz.sh` + `templates/bridgeai-144hz.desktop` | `~/bin/` and `~/.config/autostart/` | adds the 144 Hz mode and selects it at every login |
| `templates/bridgeai-sunshine.desktop` + `templates/start-sunshine.sh` | `~/.config/autostart/` and `~/bin/` | starts Sunshine's user unit after the display mode change (XFCE never reaches `graphical-session.target`, see "Cold boot"; the wait is the cure for "error -1") |
| `templates/bridgeai-fw.nft.example` + `templates/bridgeai-fw.service` | `/etc/bridgeai-fw.nft` (fill in the addresses) and `/etc/systemd/system/` | the inbound firewall, loaded at boot |
| `templates/90-bridgeai-wol.rules.example` | `/etc/udev/rules.d/90-bridgeai-wol.rules` (fill in the MAC) | arms Wake-on-LAN by MAC, so it survives a change of the interface name |
| `templates/10-bridgeai-lan.link.example` | `/etc/systemd/network/10-bridgeai-lan.link` (optional) | a fixed name for the LAN card, independent of the PCI slot |
| `templates/bridgeai-gpu-power.service` | `/etc/systemd/system/` (enable it) | the GPU power limit at boot and after every resume (200 W by default; `/etc/default/bridgeai-gpu-power` with `GPU_POWER_LIMIT_W=` changes it) |
| `templates/51-no-alsa-monitor.conf` | `~/.config/wireplumber/wireplumber.conf.d/` | stops WirePlumber from spinning on an idle host |
| `stream_probe.py` | `~/bin/` (run with `python3 -I`, stdlib only) | one CSV line every 2 s during a session (GPU, NVENC share, watts, clocks, throttle reasons, CPU, RAM, NIC, the display mode, Sunshine's warnings); stops itself 20 min after the last stream or with `touch /tmp/stop_probe`; output in `~/pipeline-measure/<start>/`. The driver reports 0 fps and 0 latency for Sunshine's encoder session, so the fps the CLIENT receives only comes from Moonlight's overlay (Ctrl+Alt+Shift+S) |
| `frozen_test.sh` | run from another LAN machine | suspend with a game open, wake by Wake-on-LAN, time the stages |
| `cold_boot_test.sh` | run from another LAN machine | reboot and time what comes back by itself, then the checks list |

## Inbound firewall on the GPU host
A fresh GPU host accepts everything (INPUT policy ACCEPT) and listens for the whole LAN on SSH, Sunshine (including its web UI on 47990), the gate (8700), the Docker-published desktops and, while it runs, Resolve's scripting port (15000, no authentication). `templates/bridgeai-fw.nft.example` is a template for its own table (`inet bridgeai_in`, policy drop, Docker's tables untouched): the LAN reaches SSH and Sunshine (TCP 47984, 47989, 47990, 48010; UDP 47998-48002, 48010, 5353), the gate only from the Docker host and the operator's machine, everything else is dropped; Resolve's port stays closed because the MCP runs on the host itself. Fill in `LAN_CIDR` and the two `GATE_CLIENT` addresses, install it as `/etc/bridgeai-fw.nft` and load it from a oneshot unit (`ExecStart=nft -f`, `ExecStop=nft delete table inet bridgeai_in`, `WantedBy=multi-user.target`).

Apply it the first time with a rollback timer in case the rules lock you out: `systemd-run --on-active=150 --unit=bridgeai-fw-rollback nft delete table inet bridgeai_in`, then `nft -f`, then test from another machine, then stop the timer. A closed-by-policy port **hangs** a TCP connect (dropped) while an unused port without a firewall answers "refused" at once, which is a quick read-only check that the rules are live. Not covered: ports Docker publishes (they go through FORWARD, so they need DOCKER-USER rules) and IPv6 beyond link-local.

## Power, sleep and the gate
- The gate lowers the GPU power limit for AI jobs (130 W) and did not put the default (240 W) back afterwards; check `nvidia-smi -q -d POWER` before judging
  game performance, and restore with `nvidia-smi -pl 240`. A job that restores it by itself is still to be built.
- A running stream counts as an encoder session, so the sleep observer keeps the host awake while someone plays.
- With the compositor of the desktop on, GL applications can stutter under capture: `xfconf-query -c xfwm4 -p /general/use_compositing -s false`.

## Known limits
- No HDR or VRR over this path. One person at a time on one card (8 GB). Kernel-level anti-cheat does not run on Linux, with or without a container.
- A browser in a container (a webtop image) works but runs without a sandbox when the container has `no-new-privileges`, and without the GPU until the
  NVIDIA runtime is given to it.

## DaVinci Resolve Studio on the host (what it needed)
Installed from the vendor's Linux zip with `makeresolvedeb` (the packages are built on the host from the file the person downloaded; nothing is redistributed). Measured on Debian 13, Resolve Studio 21.2.0.6, RTX 3060 Ti:
- `libxcb-xinerama0` is missing on a fresh Debian: without it Qt aborts at window creation. Start it from `/opt/resolve` (its log paths are relative).
- **ALSA configuration must exist** (`libasound2-data` and `pipewire-alsa`). Without it Resolve's audio engine loops on `ALSA lib pcm_dmix.c ... unable to open slave` at 300 % CPU, a render sits at 0 % and the scripting API stops answering. With both installed a 6 s 1080p timeline rendered with H.264 NVIDIA in 1.2 s (144 frames, 63 FLAC audio frames).
- Resolve on Linux does not decode AAC audio (log: `Failed to decode the audio samples`): use PCM or another codec in test clips.
- Media and render folders must sit inside Resolve's Media Storage (default `~/Videos` here, see `config.dat`); otherwise a modal "Render Path Inaccessible" blocks everything, also on a headless display.
- External scripting works with no preference change here, and `GetProductName()` returns "DaVinci Resolve Studio" (that is how the licence is confirmed). In a private Xvfb the CUDA/OpenGL interop logs errors (software GL) but the render still completes.
- After a hard kill, Resolve opens a "quit unexpectedly" dialog on that display: press **Ignore** (Send uploads a report). Quit it through the API (`Quit()`) instead.
- Resolve opens a listener on TCP 15000 on all interfaces; keep it behind the host firewall.
