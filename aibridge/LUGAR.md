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
| freeze (suspend, the game stays open) | no: prints the command | `/lugar freeze yes` |
| switch off (loses what is open and unsaved) | no: prints the command | `/lugar shutdown yes` |
| wake a frozen or off PC | no (not possible from the container) | Wake-on-LAN by the operator or the despertador; `/machine on` once the machine is registered in the rental panel |

## The phases the person is told
1. **Starting**: Steam cold start, 15 to 25 s until the launcher process exists.
2. **Compiling shaders**: the first time a game runs on that PC Steam pre-compiles its Vulkan shaders: GTA IV took more than 12 minutes on a 12-thread-busy CPU with the GPU idle (a 6 GB cache), and the stream shows a desktop with nothing to play. The state reports it (`shaders.compiling`, `workers`, Steam's own percentage from its shader log). The agent says **wait, do not enter yet**. Later runs of the same game reuse the cache.
3. **Ready** (`ready`): the game runs, Sunshine answers and nothing compiles. Only now the way in is given: Moonlight, the host address, the app `Desktop` (the game is already on that screen). The Sunshine app list also has `Steam Big Picture`.

## Setting it up for a person
1. On the PC: `GATE_HOST_TOKEN` (long random) in `gpu-host/host.env`, the gate restarted; `/usr/games/steam`, `systemd-run --user` and an X session logged in (autologin); for freeze and switch-off a sudoers rule (see the gate README). Firewall: the gate port reachable from the Docker host.
2. On the Docker host: `ops/gateways_host_service.py HOST host 8700 --token-stdin` (the token on stdin, never printed), add the host to the person's stack list `"lugar": ["HOST"]` in `ops/gateways.json` (a different list and token from `"gpu"` and `gate_token`: GPU jobs on a host never mean starting its games or switching it off), then `ops/gateways_sync.py`. The stack gets `lugares` in its `gateways.json`; recreate it once so `start_hermes.sh` registers `/lugar` and the `lugar` skill pack appears.
3. Check: `gateway lugar estado` from the agent, a run of a small game, then the person's `/lugar freeze yes` and a wake.

## Limits and what is not built
- **Parsec cannot be a host on Linux**: Moonlight with Sunshine is the stream; Moonlight has no link that opens a session, so the answer carries the address and the app name.
- **One person at a time** for now. Two at once (two Steam accounts, each with its own session, Sunshine and display on one GPU) is wanted and not tried: it needs two logged-in sessions or two containers, with the VRAM (8 GB) shared and each person's own Steam account (Steam's terms: a personal account, not shared).
- **Waking** is outside the gate. The rental panel already has a Linux agent (heartbeat, Steam inventory, the queue that launches games, `sunshine` flag) that ran on this very machine before its disk was replaced and has to be reinstalled (it needs the hub's address); what it lacks (suspend and power-off orders, a reservation that survives a frozen machine, a stream block with Sunshine's host and port) is listed in the panel's `reqs-bridgeai-linux-gpu-host-2026-11-24.md`. The gate's `/host/*` is the stand-in until then, and the canonical path afterwards: `gateway lugar` should then call the panel's `/v1/sessions` and `/power` instead.
- Steam only (no Epic or GOG inventory yet). The appid must be in the inventory; nothing else is launched.
- Measured on the reference host: down in 8 s, back 11 s after the magic packet with the game still running; cold boot to the stream port in 39 s (see `gpu-host/remote-desktop/REMOTE_DESKTOP.md`).
