# Place diagnostics (gpu-host/places/diag)

Tools made while measuring game sessions in a place (2026-11-28). They read only, write to RAM (`/tmp` on the GPU host is tmpfs; inside a
place, `/dev/shm`), and never send a person's files or text anywhere. Run on the GPU host as root unless said otherwise.

| Tool | What it measures | Run |
|---|---|---|
| `place-recorder.py PLACE UID APPID OUTDIR [SECONDS]` | every 5 s: container, Steam, Sunshine instances, shader preparation (with Steam's %), game processes, GPU, the place's RAM/swap/reclaims/OOM, zswap, the size of the game's merged NVIDIA cache; an event line on every change | host, root |
| `freeze-detector.py CONTAINER OUTDIR SECONDS` (`freeze-wait.sh` starts it when the container runs) | every 100 ms the container's PSI "full" stalls (every task waiting at once: a freeze the person feels, audio included), cause io/mem/cpu, reclaims, refaults, MB read; follows a recreated container | host, root |
| `stream-watch.py IFACE UID OUTDIR SECONDS` | every 100 ms the bytes leaving the place (its bridge on the host, NAMEdoc); gaps in the stream and per-second rate with selkies/sunshine CPU | host, root |
| `mangohud-lows.py CSV [SKIP_S]`, `mangohud-bursts.py CSV` | from a per-frame MangoHud log: average, 1 % and 0.1 % lows, worst frame, frames over 33/50/100/250 ms; seconds with bursts of slow frames | anywhere |
| `steam-launch-options.py LOCALCONFIG APPID 'OPTIONS'` | sets a game's launch options in `localconfig.vdf` (Steam must be closed: it overwrites the file on exit); keeps everything else, backup first | in the place, as the person |
| `fixer-gta4.sh` | prototype per-game fixer: while GTAIV.exe runs, minimizes the Rockstar Games Launcher (its Chromium used the GPU) and gives the launcher, Social Club and Rockstar service the lowest CPU/disk priority | in the place's session, as the person |
| `bench-q2rtx.sh [REPS]` | Quake II RTX's own timedemo, unattended (reverb-g2's q2rtx-power-sweep recipe); bare 3060 Ti baseline 74.6 fps at 210 W | in the place's session, as the person |
| `bench-metro2033.sh [RUNS]` | Metro 2033 Redux built-in benchmark. **Do not use the native build**: on 2026-11-28 it grew to 61 GB and left the host with 0.19 GB (the memory guardian now kills that) | in the place's session |
| `selkies-stalls.py CONTAINER [--since 24h]` | the web stream's stalls per session from Selkies' own log: how many, per hour, frames behind (median/p90/max), network ("path holding") vs browser ("path delivered"), and the encoder in use. The before/after number for the web's worst moments | host, root |

Also: `../place_memguard.py` (host memory guardian), `../place_faults.py ram_hog NAME` (provoke a runaway on purpose and check every link),
gputaskman (`gputaskman record -o /tmp/rondas/gtm/x.jsonl -i 0.5`, per-process GPU). Findings and the round-by-round results live in the
operator's local notes, not here.

Lessons that shaped these tools:
- Steam's "% replaying" lies near the end (the total is recalculated); measure elapsed time against the game's history instead.
- `no_display` makes MangoHud 0.7.2 log nothing; a 32-bit game needs the i386 layer.
- Memory the NVIDIA driver pins for a game is not charged to the place's cgroup: watch the host, not only the cgroup.
- The web stream (selkies) goes over TCP: packet loss freezes picture and audio together; Moonlight (UDP + FEC) degrades instead.
- `pgrep -f`/`pkill -f` over ssh match their own command line: use a bracketed pattern (`[n]ame`) or a PID.
- Recreating a place starts a new container and its Selkies log starts empty: count the stalls (`selkies-stalls.py`) BEFORE a recreate.
- The gate's idle clock frees a place with a game open and nobody watching: an unattended benchmark needs `place.py hold NAME on`
  first (and `off` after), or the place is closed mid-run (Metro, 2026-11-28).
- Docker's `OOMKilled` stays true for the container's life after any OOM in it: check the kernel log's time before blaming memory.

## Test conditions (every benchmark number carries them)

A number is compared with another only when these match; otherwise say which differs and call it indicative:
- the exact test: game and build (the appmanifest's buildid), demo/scene, runs, whether the first was cold (shaders prepared);
- the REAL render resolution (not the one asked for: on Xvfb a fullscreen game may take the screen's size), window or fullscreen;
- quality: preset, ray tracing, vsync, frame cap, upscaler;
- GPU: model, driver, power cap (W), max clock, temperature at start, PCIe link under load;
- layer: bare metal / place (image + id) / VM / Windows; Proton version or native; virtual or real display;
- load beside: somebody watching the stream (the encoder shares the GPU), recorders, other places, a build;
- container limits (RAM, CPUs), zswap, kernel;
- result: average per run and spread; with a per-frame log, 1 % and 0.1 % lows, worst frame, frames over 33 ms.
