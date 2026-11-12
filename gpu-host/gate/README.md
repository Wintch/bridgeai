# GPU gate

A small stdlib-Python service on each GPU host (a systemd user unit, not a container). Every service container of the host stays
stopped (`restart=no`). A stack asks the gate before a job; the gate starts the container if the machine is free, keeps it while
it is used, stops it when it is not, and sets the GPU power limit to the measured value for what runs.

It only runs `docker start` / `docker stop` on existing containers of a fixed list (ports 8600-8690, see `gate.py`) and one fixed
`sudo -n /usr/bin/nvidia-smi -pl W`. It never creates containers and never runs anything taken from a request.

## Install

1. Add `GATE_TOKEN` (a long random value) to `gpu-host/host.env`.
2. `gpu-host/run_services.sh create` makes the containers, stopped.
3. `gpu-host/gate/install_gate.sh` writes `~/.config/systemd/user/bridgeai-gate.service`, enables and (re)starts it, and removes the `gpu_power.sh` cron line.
   Run it again after a `git pull` or a `host.env` change: it restarts the gate. A restart drops the leases; the new gate adopts services that are
   already running and they follow the idle rule.
4. Open the gate port (default 8700) in the firewall for each stack subnet that may use this host.
5. Register the host's gate for the stacks: `ops/gateways_host_service.py <host> gate 8700 --token-stdin`, then `ops/gateways_sync.py`.

The sudoers rule for `nvidia-smi -pl *` that `gpu_power.sh` needed is the one the gate uses. With the gate installed `gpu_power.sh`
exits at once, and `run_services.sh` no longer starts services blindly (`create` by default; `start` runs them by hand).

## Settings (`gpu-host/host.env`, or the environment)

| key | default | meaning |
|---|---|---|
| `GATE_TOKEN` | required | Bearer token for every call except `/healthz` |
| `GATE_PORT`, `GATE_BIND` | 8700, `GPU_BIND_ADDR` or 0.0.0.0 | listen address |
| `GATE_IDLE_S` | 600 | seconds without activity before an interactive service stops |
| `GATE_IDLE_<SERVICE>` | `GATE_IDLE_S` | per service, e.g. `GATE_IDLE_VIDGEN=900` |
| `GATE_BATCH_TTL_S` | 7200 | a batch lease with no activity for this long is dropped |
| `GATE_BLOCK_PROCS` | VR, games, Resolve | comma-separated regexes that mean "the machine is in use" (quote the value in host.env). Each is matched against the program path (argv[0]), so `tail -f vrserver.txt` does not count; a `cmd:` prefix matches the whole command line |
| `GATE_SOCKET_TIMEOUT_S` | 10 | an idle or half-sent connection is closed after this long |
| `GATE_MAX_CONNS` | 64 | connections served at once; more are closed at once |
| `GATE_STOP_WAIT_S` | 3 | how long a wake waits for a stop of the same service that is already running |
| `GATE_STATE_DIR` | `~/.local/state/bridgeai-gate` | busy switch, saved power limit, usage ledger |
| `GATE_POWER_PROFILES` | `gpu-host/power_profiles.conf` | per-GPU limits |

## Rules

- Refused with `vr` (VR, a game or DaVinci Resolve runs), `busy` (the operator's switch: `run_services.sh busy on|off`), `vram`
  (free VRAM below the service's need) or `exclusive` (vidgen runs alone). A service that already runs is never refused.
  `vram` and `exclusive` do not count services that sit idle under interactive leases: the gate stops those first (ledger reason
  `evicted`). A service with a job in flight, one that works according to its own `/status`, one under a batch lease and one
  started by hand (no lease) are never evicted.
- A wake on a service that was started a moment ago answers 202 with the time left of its ready budget until the service's own
  `/healthz` answers, so a second caller never posts to a service that is still loading.
- Interactive work (a person's one-off request) stays up until `gateway gpu off` or until `GATE_IDLE_S` without activity. A job in
  flight (more wakes than `done`s on a lease, or the service's own `/status` saying it works) keeps it up. The immediate stops (batch
  end, release, off) also leave a service alone while its own `/status` says it works; the idle loop stops it later.
- Batch work (an agent's planned run) names its jobs or ends explicitly. When the batch ends the service stops at once, unless
  another lease holds it.
- Power: when the first service starts the gate remembers the current limit; the target is the highest profile value among the
  running services (clamped to the card's range); when the last one stops the gate restores the remembered limit, unless somebody
  else changed it meanwhile (then it leaves it and logs that). If the limit cannot be read or the restore fails, the remembered limit
  is kept and the restore is retried every tick (logged once).
- Docker start and stop, nvidia-smi and the HTTP probes never run under the state lock, so a slow `docker stop` does not stall
  other requests. Connections that stay idle are closed after `GATE_SOCKET_TIMEOUT_S`.

## API

JSON in and out, `Authorization: Bearer <token>`. `GET /healthz`, `GET /state`, `POST /wake`, `/done`, `/release`, `/off`; the
exact fields and status codes are in the docstring of `gate.py`.

## Usage ledger

`$GATE_STATE_DIR/usage.jsonl`: one line per service run (`service`, `start`, `end`, `seconds`, `wh`, `limit_w`, per-stack job
counts and batch ids, `stop_reason`). Energy comes from `power.draw` sampled every 10 s, split evenly among the services running
at that moment. No file names and no person data.

## Test

`python3 -I gpu-host/gate/gate_selftest.py` (about a minute): fake `docker`, `nvidia-smi`, `sudo`, `systemctl` and `crontab` first in
PATH, fake service servers and a fake `/proc`. Nothing real is touched.
