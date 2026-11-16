# bench_gate: measuring the power profile of every gate task

`bench_gate.py` fills in `power_profiles.conf` and the VRAM needs in `gate/gate.py` with measured numbers, through the
gate's own bench mode, so nothing competes for the card while it measures. It runs on the GPU host, sequentially,
and never edits a config file: it prints the lines to paste. Stdlib only, no root (the gate sets the limit, not the script).

## When and how to run it

Run it in an idle window: it takes the card exclusively, and while it runs every other wake gets 409 `bench`. A person's job
on the card stops it before it starts (pre-flight), it never queues behind one.

```
cd <repo>/gpu-host   # on the GPU host
python3 bench_gate.py --dry-run --recheck          # the plan and the minutes, touches nothing
python3 bench_gate.py                              # stt, tts-hq, resolve, effectcraft
python3 bench_gate.py --recheck                    # the four above + upscaler, transcoder, vidpost, imggen, vidgen
python3 bench_gate.py --tasks tts-hq --caps 100,130 --reps 3
```

Options: `--tasks` (comma list), `--recheck` (also re-verify the five existing profiles), `--caps`, `--reps`, `--wh gross|net`
(Wh used by the rule, default gross = average W x seconds, as the earlier sweeps), `--stt-secs`, `--img-quality`, `--vid-secs`,
`--effectcraft-gpu-eval`, `--eval-cap`, `--keep-tmp`, `--gate URL`, `--allow-app REGEX`.

Run the long ones under `nohup python3 bench_gate.py ... > ~/bench_gate/run.log 2>&1 &` or in tmux. Ctrl-C, SIGTERM and SIGHUP
all end the bench cleanly (a dropped SSH session sends SIGHUP), but with nohup or tmux the run does not even notice the drop.
Without either, never leave a run on a bare SSH session.

Duration (`--dry-run` prints it for your options): the four default tasks about 45 minutes; with `--recheck` about 95 minutes,
most of it vidgen (its cold start is 6 minutes and one short clip takes minutes at every cap) and tts-hq. Count 2 hours.

The gate token and the service tokens come from `host.env` (`GATE_TOKEN`, `IMAGE_TOKEN`, `VIDEO_TOKEN`, `VIDPOST_TOKEN`,
`UPSCALE_TOKEN`, `TRANSCODE_TOKEN`), read as KEY=VALUE lines, never sourced, never printed or stored. The gate is
`http://127.0.0.1:8700` (`GATE_PORT` or `--gate` change it). A service whose required token is missing is skipped.

## What it does, in order

1. **Pre-flight**, read only: `GET /state` must show no bench, `blocked` null, no service running or leased; `nvidia-smi` must
   show only small desktop processes on the card (chrome, sunshine, Xorg, ...; each under 400 MiB). Otherwise it exits 2 and
   says why. Nothing was changed.
2. `POST /bench/start` (60 s timeout). The gate sets the cap and stops applying profiles until `/bench/end`. If the call gets
   no answer in time, the script reads `GET /state`: a bench started in the last 2 minutes is ours (the pre-flight saw none),
   so it ends it with `POST /bench/end`, says so and exits 3. An older bench is left alone.
3. **Per task**: wake the service through the gate with the bench id (batch lease), wait for `/healthz`, one measured warm-up
   job, then for each cap `POST /bench/watts` (confirmed by reading `power.limit` back) and N timed jobs. Then `/done`,
   `/release` with close, and it waits until the service has stopped before the next task.
   **Before every cap and every job** it reads `GET /state`. If `blocked` is set (a person's session appeared: VR, a game, a
   Resolve on another display) or the bench is gone (also `404 unknown_bench` on `/bench/watts`), it stops at once: the current
   service is released, no further task starts, the bench is ended if it is still there, and the output names the task and the
   cap or job that was interrupted (`interrupted in task stt at cap 130 W: ...`). Exit 1. A person's session is never capped
   or disturbed; the partial rows already recorded stay in `results.jsonl`.
4. `POST /bench/end` in a `finally` (also on Ctrl-C or an error), then it checks that `power.limit` is what it was before.
   If it is not and nothing is running, it prints the command to set it by hand; it does not write the limit itself (a
   service woken right after the bench legitimately gets its own profile).
5. Clean-up of `~/bench_gate/tmp` and `~/Videos/zz_bench`, then the summary.

Every timed job runs under the same recorder as the video benchmarks (`videobench/measure.py`: `nvidia-smi -lms 500`, idle
draw sampled 2 s before the job, Wh by trapezoids, VRAM, utilisation, RAM, CPU core-seconds). One 2.2 s idle sample is taken
before each job, with the model loaded, so "net Wh" subtracts the real loaded-idle draw.

## Tasks

| Task | Job | Notes |
|---|---|---|
| `stt` | one `POST /transcribe?lang=es` of a ~3 min Spanish clip | the clip is made at the start with the local Piper tts (`tts`, port 8640, woken through the gate with the bench id) from public text; never a person's audio. Output unit: audio minutes |
| `tts-hq` | three `POST /v1/audio/speech` calls: public-domain paragraphs in es (Cervantes), en (Austen), ru (Tolstoy) | llm must not be up (the gate answers 409 `vram` otherwise). Output unit: audio seconds, so Wh per audio second is recorded |
| `resolve` | one H.264 Master render of a synthetic 60 s 1080p24 clip (ffmpeg testsrc2, in `~/Videos/zz_bench`) | through the real MCP path: `mcp_dispatch.sh` as a stdio child (`SSH_ORIGINAL_COMMAND=davinci`, `RESOLVE_GATE_STACK=bench`, `RESOLVE_GATE_BENCH=<id>`, so the session's own `/wake` carries the bench id). One fresh Resolve session per job: cold start to the first tool answer, idle VRAM with Resolve open, render peak VRAM. Throwaway project deleted. After each session it calls `/off` for the stack and waits until Resolve (display :99) is gone |
| `effectcraft` | `effectcraft-cli render` of a 5 s 720p text comp | CPU only, no gate lease, no sweep: runs at the card's default cap. Verdict "CPU only" when the VRAM peak is within 100 MiB of the card's use before. CPU core-seconds are system-wide busy time (CPU energy is not measured: RAPL needs root). The CLI syntax is tried in order (comp then project argument, project flag, then the README's demo render); the line used is stored as `comp` (`text-comp` or `demo`). `--effectcraft-gpu-eval` also runs `effectcraft-cli bench --gpu --json` once at `--eval-cap`, labelled **"evaluation, EffectCraft stays CPU-only in production"**: no profile is proposed from it and EffectCraft gets no gate lease. It runs only inside this run's active bench (the bench reserves the whole card through the gate) and is refused when no bench of this run is active; it is recorded like the other jobs (peak VRAM, average and peak W, Wh, plus its own JSON) as a line of kind `evaluation` |
| `upscaler`, `transcoder`, `vidpost`, `imggen`, `vidgen` | `--recheck` only: a 640x360 PNG x4; a 60 s 1080p clip to 720p h264; a 5 s 832x480 clip at x2 and 48 fps; one 1024x1024 image (`--img-quality`); one short clip (`--vid-secs`, default 2) | re-verify the profiles that already exist (vidgen: one timed job per cap by default) |

Caps: 100, 130, 160, 200, 240 for short jobs; 100, 130, 170, 240 for resolve and vidgen. They are clamped to the card's range
and de-duplicated. Reps: 5 (3 for tts-hq, resolve, vidpost, effectcraft; 1 for vidgen).

## What it records and prints

One JSON line per cap (aggregate and the raw runs), per task and per recommendation is appended to
`~/bench_gate/results.jsonl` (`BENCH_GATE_HOME` moves it). Per cap: median s per job, average and peak W, Wh per job (gross)
and net Wh, the card's VRAM peak, utilisation, successes out of runs, and for resolve cold start s and idle VRAM.

**Recommended cap** per task, the repo's rule: the lowest Wh per job; a higher cap wins only when it costs at most +10 % Wh and
is at least 15 % faster. Wh within 2 % of the best count as equal and the lower cap is taken (a flat curve, like NVENC, picks
100 W instead of noise). Where the output length varies (speech) the comparison is per unit of output. A cap whose limit the
card did not confirm, or with no successful job, takes no part.

**VRAM need**: the task's peak minus the card's use before it was woken, plus 15 %, rounded up to 10 MB. For resolve the
peak includes the idle use with Resolve open.

**gpu-unlock**: the state of `/sys/module/gpu_unlock/parameters/targets` (file absent or empty = `off`) is printed in the
pre-flight and stored as `gpu_unlock` on every result line. The `imggen` and `vidgen` profiles assume it is on: when it is
off, the summary warns not to take their numbers from that run.

## Applying the results

The script prints two blocks and edits nothing:

```
gpu-host/power_profiles.conf, section [RTX 3060 Ti]:
    stt = 100
gate/gate.py SERVICES, VRAM need in MB:
    stt: need 1380 MB (was 1200)
```

1. Check the table first: a cap with failed jobs, a limit that was not confirmed, or a slow drift between caps (thermal) means
   run that task again with `--tasks X`.
2. Put the `name = W` lines under the matching GPU section of `power_profiles.conf`. Values are only worth it when measured:
   leave a service out when the curve is flat and the card's default is fine. Remember the gate applies the highest value among
   the running services.
3. Put the needs into `SERVICES` in `gate/gate.py` (the middle number). `resolve` currently carries a provisional 2500 MB:
   replace it with the measured figure, and check the cold start against the 120 s ready budget (about 2.5x headroom is
   comfortable).
4. `effectcraft` with verdict "CPU only" needs no lease and no profile. A "uses VRAM" verdict means look at it before treating it
   as CPU-only.
5. Run `gate/gate_selftest.py` and deploy as usual; commit the numbers with the date of the bench and the results file name,
   not the file itself (it holds host measurements).

## Safety notes

- It only uses the gate's HTTP API and read-only `nvidia-smi`; the cap is set by the gate (`sudo -n /usr/bin/nvidia-smi -pl W`
  with a fixed argv). The bench expires by itself after `GATE_BENCH_TTL_S` (default 14400 s) and the gate restores the limit.
- It never stops or kills a process it did not start. A Resolve MCP child that does not exit is asked to stop once; Resolve
  itself is closed by the wrapper when its last client leaves.
- Inputs are synthetic or public text; outputs are deleted at the end.
- A JSON-RPC `error` answer from the Resolve MCP proxy (for example the gate refusing the wake because a person is using the
  card) is a failure of that job, never a success.
- Offline test: `python3 bench_gate_selftest.py` (fake gate, services, recorder, Resolve session and clock; no GPU needed).
