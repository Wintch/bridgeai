# GPU gate

A small stdlib-Python service on each GPU host (a systemd user unit, not a container). Every service container of the host stays
stopped (`restart=no`). A stack asks the gate before a job; the gate starts the container if the machine is free, keeps it while
it is used, stops it when it is not, and sets the GPU power limit to the measured value for what runs.

It only runs `docker start` / `docker stop` on existing containers of a fixed list (ports 8600-8690, see `gate.py`) and one fixed
`sudo -n /usr/bin/nvidia-smi -pl W`. It never creates containers and never runs anything taken from a request.

One service of the list is not a container: `resolve` (pseudo-port 8695, only an id) is EXTERNAL. The client that wants it (the MCP
session on the GPU host) starts and closes it; the gate grants the start, watches `/proc` and asks for the close. It never kills.

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
| `GATE_NEED_<SERVICE>` | the measured need in `SERVICES` | VRAM in MB a service needs on THIS card, e.g. `GATE_NEED_LLM=5000` on a 6 GB card that runs a smaller model (`LLM_MODEL` in `run_services.sh`) |
| `GATE_BATCH_TTL_S` | 7200 | a batch lease with no activity for this long is dropped |
| `GATE_BLOCK_PROCS` | VR, games, Resolve (not the one on :99) | comma-separated regexes that mean "the machine is in use" (quote the value in host.env). Each is matched against the program path (argv[0]), so `tail -f vrserver.txt` does not count; a `cmd:` prefix matches the whole command line |
| `GATE_SOCKET_TIMEOUT_S` | 10 | an idle or half-sent connection is closed after this long |
| `GATE_MAX_CONNS` | 64 | connections served at once; more are closed at once |
| `GATE_STOP_WAIT_S` | 3 | how long a wake waits for a stop of the same service that is already running |
| `GATE_EXT_CLOSE_WAIT_S` | 60 | an eviction waits this long for an external service (resolve) to leave after its close request; then the waker is refused and the request withdrawn |
| `GATE_IDLE_RESOLVE` | 300 | idle seconds before resolve gets a close request |
| `GATE_BENCH_TOKEN` | unset | Bearer token for `/bench/*` only (a value different from `GATE_TOKEN`). Unset, or equal to `GATE_TOKEN`: `/bench/*` answers 403 `bench_disabled`; the stacks' token is never accepted there |
| `GATE_BENCH_TTL_S` | 3600 | a bench that is not ended restores the old limit after this long |
| `GATE_STATE_DIR` | `~/.local/state/bridgeai-gate` | busy switch, saved power limit, usage ledger |
| `GATE_POWER_PROFILES` | `gpu-host/power_profiles.conf` | per-GPU limits |

## Rules

- Refused with `vr` (VR, a game or DaVinci Resolve runs), `busy` (the operator's switch: `run_services.sh busy on|off`), `vram`
  (free VRAM below the service's need) or `exclusive` (vidgen runs alone). A service that already runs is never refused.
  `vram` and `exclusive` do not count services that sit idle under interactive leases: the gate stops those first (ledger reason
  `evicted`). A service with a job in flight, one that works according to its own `/status`, one under a batch lease and one
  started by hand (no lease) are never evicted.
- Refused with `bench` while a power bench runs (see Bench), unless the wake carries the bench id.
- A wake on a service that was started a moment ago answers 202 with the time left of its ready budget until the service's own
  `/healthz` answers, so a second caller never posts to a service that is still loading.
- Interactive work (a person's one-off request) stays up until `gateway gpu off` or until `GATE_IDLE_S` without activity. A job in
  flight (more wakes than `done`s on a lease, or the service's own `/status` saying it works) keeps it up; `POST /done {lease, wakes: N}`
  closes N wakes at once for a job that woke the gate N times (a chained video), and counts as one job for a batch. The immediate stops (batch
  end, release, off) also leave a service alone while its own `/status` says it works; the idle loop stops it later.
- Batch work (an agent's planned run) names its jobs or ends explicitly. When the batch ends the service stops at once, unless
  another lease holds it.
- Power: when the first service starts the gate remembers the current limit; the target is the highest profile value among the
  running services (clamped to the card's range); when the last one stops the gate restores the remembered limit, unless somebody
  else changed it meanwhile (then it leaves it and logs that). If the limit cannot be read or the restore fails, the remembered limit
  is kept and the restore is retried every tick (logged once).
- Docker start and stop, nvidia-smi and the HTTP probes never run under the state lock, so a slow `docker stop` does not stall
  other requests. Connections that stay idle are closed after `GATE_SOCKET_TIMEOUT_S`.

## External services (resolve)

| | |
|---|---|
| table | `resolve`: pseudo-port 8695 (`GATE_PORT_RESOLVE` overrides), VRAM need 2500 MB provisional (replace with the bench's measured peak), ready budget 120 s |
| running | a process with argv0 `/opt/resolve/bin/resolve` and `DISPLAY=:99` in its `/proc/<pid>/environ` (the private Xvfb of the MCP session) |
| person's Resolve | any other display (or an unreadable environ) is a person's session and blocks with `vr`; the one on `:99` does not |
| grant | `POST /wake` on a free machine answers `202 {lease, running: false, eta_s, go: true}`: the client starts it now. The power profile is applied before the answer. A second wake while it starts joins (202, no `go`) |
| up | the gate sees the process in `/proc` and moves the run from starting to running; a grant whose process never shows up is dropped after 2x the ready budget |
| in flight | a lease with more wakes than `done`s is in flight (a job that wakes the gate several times, like a chained video with one wake per segment, sends one `/done {lease, wakes: N}` that covers them all; a count whose last wake is older than 30 minutes is expired and reset, and never added to the next job). `POST /beat {lease}` every few seconds during a long call keeps it in flight past 30 minutes. Every beat also resets the idle clock of the run and the lease (the client beats only while a call or a render runs), so a client that beats is never idle-closed; it must stop beating when it is idle to let the idle rule fire |
| close | idle, eviction, `off` and `release` never kill: they set a close request, shown in `GET /state` as `services.resolve.close` (`idle`, `evicted`, `off`, `released`) and returned by `/beat` as `{"close": reason}`. The client closes, then may `POST /down {lease}`; the gate also sees the process leave. The run ends with the reason of the request. A wake that arrives while an `idle` request is pending withdraws it at once and gets `200` (the service is in use); `evicted`, `off` and `released` are waited for |
| eviction | another wake needs the VRAM (or vidgen's exclusivity): the gate waits up to `GATE_EXT_CLOSE_WAIT_S` for the process to leave; if it stays, the waker gets the original `409` and the request is withdrawn |
| exclusivity | resolve needs VRAM, so it is exclusive with vidgen both ways and evicts idle imggen/llm like any other service |

Power: `resolve`, `stt` and `tts-hq` have no measured value yet, so the profile file has no number for them and they do not change the
limit. The bench below is how the numbers are measured.

## Bench

Measures a power profile with nothing else on the card. Every `/bench/*` call takes only `GATE_BENCH_TOKEN` (never the stacks'
`GATE_TOKEN`; 403 `bench_disabled` while it is unset), so a stack cannot open a bench and block the others. `POST /bench/start {"stack","watts"}` answers `200 {"bench": id}` only when
no service runs with a lease of another stack, no job is in flight, no VR session or operator switch is active, and no other bench
runs; else `409` (`busy_jobs`, `vr`, `busy`, `bench`). While it runs:

- every `/wake` without `"bench": id` gets `409 {"why": "bench"}`; with the id it works (batch mode too);
- the cap is the bench's watts (clamped to the card's range; same fixed `sudo` argv, read back) and the profiles are not applied;
- `POST /bench/watts {"bench","watts"}` changes the cap; `GET /state` shows `bench: {id, watts, started}`; ledger lines carry `bench`.

`POST /bench/end {"bench"}` (or `GATE_BENCH_TTL_S`) restores the limit found before the bench and normal power logic resumes. If the
restore fails it is retried every tick. The tick also ends a running bench (and restores the limit) when a person's session or the operator's switch becomes active, even if docker is unreachable. `/bench/start` also answers `busy_jobs` when any running or starting service has no lease (for example a Resolve on `:99` left after a gate restart) or a `/wake` is in progress; each wake re-checks the bench id under the state lock. A gate restart drops the bench; the saved limit is restored when nothing runs.

## Watch fields

`GET /state` carries `sleep_ok` and `sleep_why` for a host that suspends itself: `sleep_ok` is false while any service runs or is
starting (loading its model), any lease is held or a bench is open, and `sleep_why` lists those (`running:llm`, `starting:imggen`,
`lease:llm`, `bench`). The host's sleeper asks it before suspending; when the gate does not answer it keeps its own GPU check.

`GET /state` also carries `selfcheck` and `driver_watch`: the last results of `gpu_selfcheck.py` and `driver_watch.py` (`gpu-host/GPU_WATCH.md`), read from
`selfcheck.json` and `driver_watch.json` in `GATE_STATE_DIR` and cut down to fixed words and numbers (verdict, reason words, ages in seconds, driver
version, booleans for a pending kernel, a DKMS gap, low `/boot` space, and the security words `security`, `update_class`, `security_fix`, `unlock_upstream`: whether the installed
driver is below what NVIDIA's bulletins fix and whether an update is urgent or measure-first). Null when never run or unreadable. The selfcheck measures inside the bench mode above,
with `GATE_BENCH_TOKEN` (it refuses to run without it).

## API

JSON in and out, `Authorization: Bearer <token>`. `GET /healthz`, `GET /state`, `POST /wake`, `/done`, `/beat`, `/down`, `/release`,
`/off`, `/bench/start`, `/bench/watts`, `/bench/end`; the exact fields and status codes are in the docstring of `gate.py`.

## Usage ledger

`$GATE_STATE_DIR/usage.jsonl`: one line per service run (`service`, `start`, `end`, `seconds`, `wh`, `limit_w`, per-stack job
counts and batch ids, `stop_reason`, and `bench` when written during a bench). Energy comes from `power.draw` sampled every 10 s, split evenly among the services running
at that moment. No file names and no person data.

## Test

`python3 -I gpu-host/gate/gate_selftest.py` (about a minute): fake `docker`, `nvidia-smi`, `sudo`, `systemctl` and `crontab` first in
PATH, fake service servers and a fake `/proc`. Nothing real is touched.
