# A person's own game PC (`gateway lugar`, `/lugar`)

A desktop host that streams games with Sunshine (Moonlight on the person's side) can be driven from the person's chat: run a game by name, see whether it is ready to enter, freeze the machine with the game still open. It sits next to `MACHINES.md` (rented remote machines with credit through a provider) and uses the GPU gate of `gpu-host/gate` as its door.

```
person ──"corre gta4"──▶ agent ──gateway lugar correr gta4──┐
person ──/lugar freeze|shutdown yes──▶ quick command ───────┤  (runs before the model, passes --persona)
                                                            ▼
                         gateway lugar ── http://<host>:8700/host/* (its own token) ── host_control.py on the PC
                                                                  games · state · launch · suspend/poweroff
```

## Who can do what
| | the agent (`gateway lugar ...`) | the person |
|---|---|---|
| list the games, state, phase | yes | |
| run a game (`correr NAME`, a loose name: `gta4`, `gta iv`, `metro`) | yes | |
| see the screen: one picture (`pantalla`) or a short clip (`clip [profile] [seconds]`, H.265 + AAC, 30 s at most) | picture always; clip only while recording is on (the files arrive as `MEDIA:`, the last three of each kept under `/workdir/lugar`, private) | `/lugar screen`, `/lugar clip` |
| turn recording on or off, choose its profile (`rec on|off [full|medio|ligero]`) | no: prints the command (it takes from the game) | `/lugar rec on ligero`, `/lugar rec off` |
| stats: screen refresh, encoder fps against it, who is connected, Sunshine's problems, recording | yes (`estado` or `stats`) | `/lugar` |
| freeze (suspend, the game stays open) | no: prints the command | `/lugar freeze yes` |
| switch off (loses what is open and unsaved) | no: prints the command | `/lugar shutdown yes` |
| wake a frozen or off PC | no (not possible from the container) | Wake-on-LAN by the operator or the despertador; `/machine on` once the machine is registered in the rental panel |

## Seeing the screen (`pantalla`, `clip`)
The gate takes the picture and records the clip on the PC itself, so nothing depends on the rental panel: `GET /host/screenshot` is one `ffmpeg x11grab` frame of the whole X screen (1280 px wide at most, about 0.1 s) and `GET /host/clip?s=N` is `x11grab` at 30 fps encoded by `hevc_nvenc` (H.265, tagged `hvc1` so Telegram and phones play it) with the sound of the default sink's monitor as AAC (never a microphone), in an mp4 that fits Telegram's 50 MB. Both are under the host token; one grab or recording at a time (a second is a 429); a clip is 30 s at most (`HOST_CLIP_BITRATE`, `HOST_CLIP_AUDIO=none|auto|SOURCE`, `HOST_SHOT_MAX_W` change it). Recording is **off by default** and a person turns it on (`/lugar rec on [profile]`, kept in `capture.json` in the gate's state folder) because the grab (`x11grab` goes through the CPU) and the encoder both take from the game. Profiles: `full` 1080p at 60 fps and 8 Mbit/s with stereo AAC 128k (the target), `calidad` 720p30 1 Mbit/s with stereo AAC 64k at 32 kHz (the profile for long recordings), `medio` 720p30 3 Mbit/s, `ligero` 480p30 1 Mbit/s with mono AAC 48k at 22 kHz. Measured on the reference host with an idle desktop: `full` took about 73 % of one CPU core and 20 % of the encoder (8 s, 4.4 MB), `ligero` about 44 % of a core and 1 % of the encoder (8 s, 0.6 MB); with a game the numbers are the game's to lose, so the stats say whether the encoder keeps up. The picture is the X screen: a game that owns the screen exclusively can come out black (the command says so). Saved files are 0600 in a 0700 folder.

## Long recording (`largo`)
`POST /host/rec {"action": "start"|"stop"|"delete"}` runs one background ffmpeg that writes ten-minute Matroska segments (keyframes forced at each cut, H.265 on NVENC, AAC) into `~/recordings/rec-YYYYMMDD-HHMMSS/` on the host. Same switch as clips (`/lugar rec on`). **At most 10 GB of recordings are kept in total** (`HOST_REC_CAP_GB`; `HOST_REC_MIN_FREE_GB`, 5, is the free space it will not go under): reaching either stops ffmpeg cleanly (`q` on its stdin closes the file) and the status says why; a new start with the store at the cap is a 507. `GET /host/rec/file?name=&part=N` joins the segments of delivery part N without re-encoding (`-c copy`, `hvc1`, `faststart`) and streams it; parts are groups of segments under 1.8 GB so each fits Telegram's 2000 MB on the local Bot API. The bot downloads the parts to `/workdir/lugar/` (private) and sends them; **the original is deleted only by `largo borrar`, after the person confirms it arrived** (the file also lives in Telegram, which is the storage for now). Status (`estado`, `largo lista`) shows the running recording (minutes, profile, GB of the cap) and what is kept. A crash of the gate or the host leaves the finished segments readable (Matroska), and the running one up to its last cluster.

## Stats the bot can report (`estado`, `/host/state`)
`display` (the mode and refresh `xrandr` marks current: is it 144 Hz?), `encoder` (the driver's NVENC session count, average fps and latency: a stream that cannot keep the screen's refresh shows there), `sunshine` (from its log: is a player connected, codec, bitrate, resolution, and the warnings and errors of the last 10 minutes minus the startup noise a healthy start always prints; a `Failed to start capture session` is the one that explains a Moonlight error -1), `stream` (the verdict: `hz_ok`, and `frames` ok / loss / idle: loss when the encoder's fps is under 90 % of the refresh), `capture` (switch, profile, whether a recording is running now, with its elapsed seconds). What the network loses on the way to the player is not visible on the PC; only the player's statistics overlay has it.

## The phases the person is told
1. **Starting**: Steam cold start, 15 to 25 s until the launcher process exists.
2. **Compiling shaders**: the first time a game runs on that PC Steam pre-compiles its Vulkan shaders: GTA IV took more than 12 minutes on a 12-thread-busy CPU with the GPU idle (a 6 GB cache), and the stream shows a desktop with nothing to play. The state reports it (`shaders.compiling`, `workers`, Steam's own percentage from its shader log). The agent says **wait, do not enter yet**. Later runs of the same game reuse the cache.
3. **Ready** (`ready`): the game runs, Sunshine answers and nothing compiles. Only now the way in is given: Moonlight, the host address, the app `Desktop` (the game is already on that screen). The Sunshine app list also has `Steam Big Picture`.

## Setting it up for a person
1. On the PC: `GATE_HOST_TOKEN` (long random) in `gpu-host/host.env`, the gate restarted; `/usr/games/steam`, `systemd-run --user` and an X session logged in (autologin); for freeze and switch-off a sudoers rule (see the gate README). Firewall: the gate port reachable from the Docker host.
2. On the Docker host: `ops/gateways_host_service.py HOST host 8700 --token-stdin` (the token on stdin, never printed), add the host to the person's stack list `"lugar": ["HOST"]` in `ops/gateways.json` (a different list and token from `"gpu"` and `gate_token`: GPU jobs on a host never mean starting its games or switching it off), then `ops/gateways_sync.py`. The stack gets `lugares` in its `gateways.json`; recreate it once so `start_hermes.sh` registers `/lugar` and the `lugar` skill pack appears.
3. Check: `gateway lugar estado` from the agent, a run of a small game, then the person's `/lugar freeze yes` and a wake.

## Heat and the power cap
A summer on a game PC: the GPU is capped at boot and after every resume by a small system unit (`gpu-host/remote-desktop/templates/bridgeai-gpu-power.service`, 200 W by default, the stock board power of an RTX 3060 Ti; the driver's default on an unlocked card is 240 W and a game peaked at 183 W), and the gate keeps a minute-by-minute heat log and reports `warm` or `hot` in its state, which `gateway lugar estado` repeats with the temperatures and the reasons the GPU slows down. Measured on the reference host: GPU target 83 C, slowdown 95 C; the CPU reached 86 C on a one-core-bound game.

## Limits and what is not built
- **Parsec cannot be a host on Linux**: Moonlight with Sunshine is the stream; Moonlight has no link that opens a session, so the answer carries the address and the app name.
- **One person at a time** for now. Two at once (two Steam accounts, each with its own session, Sunshine and display on one GPU) is wanted and not tried: it needs two logged-in sessions or two containers, with the VRAM (8 GB) shared and each person's own Steam account (Steam's terms: a personal account, not shared).
- **Waking and freezing through the rental panel work** (tested 2026-11-24 on the reference host with its Linux agent reinstalled and given power orders): a suspend order through the panel's API took 7.2 s to take effect; the panel's own Wake-on-LAN brought the host back with the game process alive, answering ping after 8.2 s, SSH 8.3 s, Sunshine's port 8.3 s and online in the panel 8.4 s, no reboot. The agent polls for orders every 5 s (the panel advertises one heartbeat, about a minute). What a person's bot still needs for that path is an account and key on the panel in its `maquinas` block (`/machine on|freeze|enter`), and a panel change so a frozen machine's reservation is not released after an hour without heartbeats. The gate's `/host/*` stays as the stand-in that needs the host awake: `gateway lugar` should call the panel's `/v1/sessions` and `/power` once the account exists.
- Steam only (no Epic or GOG inventory yet). The appid must be in the inventory; nothing else is launched.
- Measured on the reference host: down in 8 s, back 11 s after the magic packet with the game still running; cold boot to the stream port in 39 s (see `gpu-host/remote-desktop/REMOTE_DESKTOP.md`).
