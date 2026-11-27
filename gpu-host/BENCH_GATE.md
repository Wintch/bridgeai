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

Options: `--tasks` (comma list), `--recheck` (also re-verify the five existing profiles), `--caps`, `--reps`, `--wh gross|net18|net`
(Wh used by the rule, default gross = average W x seconds, as the earlier sweeps; see "Which Wh"), `--stt-secs`, `--img-quality`, `--vid-secs`,
`--effectcraft-gpu-eval`, `--eval-cap`, `--keep-tmp`, `--gate URL`, `--allow-app REGEX`.

Run the long ones under `nohup python3 bench_gate.py ... > ~/bench_gate/run.log 2>&1 &` or in tmux. Ctrl-C, SIGTERM and SIGHUP
all end the bench cleanly (a dropped SSH session sends SIGHUP), but with nohup or tmux the run does not even notice the drop.
Without either, never leave a run on a bare SSH session.

Duration (`--dry-run` prints it for your options): the four default tasks about 45 minutes; with `--recheck` about 95 minutes,
most of it vidgen (its cold start is 6 minutes and one short clip takes minutes at every cap) and tts-hq. Count 2 hours.

The gate token, the bench token and the service tokens come from `host.env` (`GATE_TOKEN`, `GATE_BENCH_TOKEN`, `IMAGE_TOKEN`,
`VIDEO_TOKEN`, `VIDPOST_TOKEN`, `UPSCALE_TOKEN`, `TRANSCODE_TOKEN`), read as KEY=VALUE lines, never sourced, never printed or
stored. The gate is `http://127.0.0.1:8700` (`GATE_PORT` or `--gate` change it). A service whose required token is missing is skipped.

**`GATE_BENCH_TOKEN`** is a value of its own, different from the stacks' `GATE_TOKEN`: the gate takes only it on `/bench/*` (403
`bench_disabled` while it is unset or equal to `GATE_TOKEN`; it never falls back to the stacks' token, so no stack can open a bench
and block the others). bench_gate sends it only to `/bench/*` and the stacks' `GATE_TOKEN` everywhere else; without it the run exits
2 before touching anything. A bench lasts at most `GATE_BENCH_TTL_S` (default 3600 s): `--dry-run` says when the plan is longer (it compares with the `GATE_BENCH_TTL_S` of host.env or the environment, and counts the two canary jobs of imggen and vidgen and about 260 s per H3 job), and
then the value must be raised in `host.env` and the gate restarted (or the tasks run in separate invocations).

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
draw sampled 2 s before the job, Wh by trapezoids, VRAM, utilisation, RAM, CPU core-seconds) plus a once-a-second sampler of
temperature, SM clock, throttle reasons, power limit and encoder sessions. Before each job the card settles for 4 s and is read at
rest (three reads: GPU use, encoder sessions, limit, temperature); a 2.2 s idle power sample is taken with the model loaded.

### Which Wh

`gpu_wh` is **gross** (average W x seconds) and is the headline everywhere. Two nets sit next to it and every "net" says which:
`gpu_net18_wh` = gross - 18 W x seconds (the repo's convention, the card's idle draw in P8), and `gpu_net_wh` = gross - this job's own
measured idle draw x seconds. The table prints `Wh gross`, `net18 Wh` and `net-idle`; `--wh net18` or `--wh net` make the rule use one of them.

### Efficiency per output

Wh per job says little when jobs differ in size, and what a person buys is frames, images, seconds of audio. So every cap row of a task
with a known output also carries `per_output` (printed under the table, stored in `results.jsonl` and on the recommend line): the units
one job makes (`units_per_job`) and what one Wh buys, **gross and net18, each labelled** (`gross` = the Wh as measured; `net18` = gross - 18 W x s,
the repo's convention; the card's own measured idle is not used here). The figures are the median over the valid timed jobs of each job's own ratio;
a job with no output size, or a net18 of zero Wh (a job that drew under 18 W), makes that figure `None`, never a division by zero.

| task | output units per job | fields (each as `..._gross` / `..._net18` in the table and under `gross` / `net18` in the row) |
|---|---|---|
| `vidgen` | frames: the clip's seconds on vidgen's frame grid (24 fps snapped up to 17k+5: 2 s = 56, 5 s = 124, 10 s = 243), not seconds x 24 | `frames_per_wh`, `wh_per_frame` |
| `imggen` | 1 image and its megapixels (1024x1024 = 1.048576) | `images_per_wh`, `wh_per_megapixel` |
| `stt` | seconds of audio transcribed (the service's `audio_seconds`) | `audio_seconds_per_wh` |
| `tts-hq` | seconds of audio produced | `audio_seconds_out_per_wh` |
| `upscaler` | megapixels out (640x360 x4 = 3.6864) | `megapixels_out_per_wh` |
| `transcoder` | frames (60 s x 24 fps = 1440, the same count out) | `frames_per_wh` |
| `vidpost` | frames out (5 s x 24 fps = 120 in, interpolation makes 2n-1 = 239) | `frames_out_per_wh` |
| `llm` | tokens (no llm task in this script yet; a job that returns its token count and declares `outputs={"tokens": 1.0}` gets it) | `tokens_per_wh` |

`resolve` and `effectcraft` have no per-output block (their unit is a render). The recommended cap is still chosen by Wh per job (or per unit of the
task's own `ret`, as before); the per-output lines are for comparing machines, caps and drivers in the units people ask for. Output sizes of the
synthetic inputs are constants of this script (`UPSCALE_FACTOR`, `TRANSCODER_SECS`, ...): change the input and change the constant with it.

### What each job records, and when it is invalid

Each run line stores: the cap asked (`cap_w_req`) and the **power limit read back** at the start and at the end (`limit_w_start`,
`limit_w_end`, and the lowest and highest during the job), temperature at start, end and peak, median SM clock, the throttle
reasons seen (OR of the bitmasks), encoder sessions (at idle, and the most during the job), GPU use at idle, foreign compute apps, CPU
governor and EPP, driver, kernel and the gpu-unlock value. The environment is also on the session line and, per cap, in `env` (driver,
kernel, gpu-unlock, governor, EPP, cap asked and limit read back; for docker services also the image id, the size of the model files
it loads and, for ComfyUI services, the ComfyUI version; these come from read-only `docker inspect` and `docker exec` calls and are best
effort: a value that cannot be read is null).

A job is **invalid** (`invalid_why` lists the reasons) when: GPU use at idle is above 5 %; the card has encoder sessions at idle (a
Sunshine client), or during a job of a task that does not encode (stt, tts-hq, upscaler, imggen); a foreign compute app is on the
card (one that is neither a desktop app seen before the bench nor a process that appeared before the service's warm-up ended, which
is taken to be the service's own); the limit read back differs from the one asked by more than 1 W or moves by more than 0.5 W during
the job; or a hardware or thermal throttle (0x8, 0x20, 0x40, 0x80) shows up (0x1 idle and 0x4, the cap itself, are normal). A value
the driver cannot give never makes a job invalid. **An invalid job is never pooled**: it is counted (`n_invalid`), its reasons are
listed, the medians and the recommendation come from the valid jobs only, and a cap with no valid job proposes nothing.

More invalid reasons: **a cold job** (the service's worker process was respawned during the job, because it had exited at its idle
timeout: only processes inside the service's own container, read with `docker top`, are taken as the service's, so a foreign app that
starts meanwhile is never blessed and a respawned worker is recognised; the job is tagged `cold`, never mixed with warm ones, and a gap
near the service's idle timeout is warned about); **too few power samples** (none, or under 80 % of the two per second the sampler
should give for jobs of 2 s or more: the Wh cannot be trusted); **a cap the card did not confirm** (the read-back limit differs from the
one asked: the jobs carry the limit the card reports, `cap_w_asked` holds what was asked, and they are invalid with "cap not confirmed").

A cap row with **too few valid jobs** (under half of the jobs, never fewer than 2) is marked THIN, printed as such and left out of the
recommendation: the jobs dropped for heat or throttle are the hot ones, so a lone survivor is the coolest sample, not a median.

The environment snapshot (image id, model files, ComfyUI version) is read again for every cap row; a change during the task is flagged
on the row (`env_changed`) and in the table. Services without a fixed model list (stt, tts-hq, vidpost, upscaler) record a digest of
their model directory's listing (file count, bytes, hash of names and sizes); the transcoder has no model, its image id is its environment.

`--allow-app` note: the card's process name is read by its first word, so a program whose path has a space in it (for example
`/opt/Google Chrome/chrome`) is not recognised as the desktop app and the pre-flight refuses. That fails safe; pass `--allow-app` with a
pattern that matches the word it sees (here `Google`). Matching the name before the first argument instead would let an argument path
ending in an allowed name pass for the program.

### ComfyUI's node cache (imggen, vidgen)

Both services run ComfyUI with `--cache-classic`: after a first run, an identical (prompt, seed) job re-executes only the save node,
and its time and energy would pass for production. So every timed ComfyUI job takes the next (prompt, seed) of fixed tables (8
seeds, 5 prompts of one word count; the same sequence in every session, never the same pair as the job before), and stores 8 hex of
the output's sha256, its seed and its prompt index. **Canary**: after the warm-up, one job on a new pair (the first warm one), the
same pair again, and one more new pair. The identical repeat is expected to be fast (the cache is on, as in production; the line
records `cache_active`). When the second NEW pair is more than 3x faster than the first, the rotation does not defeat the cache and
the task is aborted as **cache-tainted**; the same happens when the two new pairs give the same output hash (the service
is not using its inputs). No row is recorded, the canary line is kept as evidence, exit 1. Do not trust imggen or
vidgen rows from a run that did not pass its canary.

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

**Per process** (when gputaskman is installed, `GPU_WATCH.md` "gputaskman"; `--no-gputaskman` turns it off): every timed job is recorded every
0.5 s into `~/bench_gate/gputaskman/<run>-<tag>.jsonl`, and the job's raw line gets `gpu_procs`: up to 6 rows `{container, name, vram_peak_mib,
gpu_peak_pct, engines_peak, seen}`, grouped by container and program, biggest VRAM first. It separates the service's own VRAM from the desktop's
and shows which engine did the work (compute against NVENC/NVDEC). Look at a file with `gputaskman summary FILE`.

**Recommended cap** per task, the repo's rule: the lowest Wh per job; a higher cap wins only when it costs at most +10 % Wh and
is at least 15 % faster. Wh within 2 % of the best count as equal and the lower cap is taken (a flat curve, like NVENC, picks
100 W instead of noise). Where the output length varies (speech) the comparison is per unit of output. A cap whose limit the
card did not confirm, or with no successful job, takes no part.

**VRAM need**: the task's peak minus the card's use before it was woken, plus 15 %, rounded up to 10 MB. For resolve the
peak includes the idle use with Resolve open. For **imggen, vidgen and vidpost the figure is informative only**: ComfyUI offloads
dynamically (dynamic VRAM), so the measured peak is an upper bound and not what the service needs, and `need + 15 %` can be larger
than the VRAM that is free. The output says so, lists it apart from the SERVICES block, and the result line carries
`need_informative: true`; the gate's 6500/7000 MB for imggen/vidgen are start thresholds, not peaks.

**gpu-unlock**: the state of `/sys/module/gpu_unlock/parameters/targets` (file absent or empty = `off`) is printed in the
pre-flight and stored as `gpu_unlock` on every result line. The `imggen` and `vidgen` profiles assume it is on: when it is
off, the summary warns not to take their numbers from that run.

## Applying the results

The script prints two blocks and edits nothing:

```
gpu-host/power_profiles.conf, section [RTX 3060 Ti]:
    stt = 100
gate/gate.py SERVICES, VRAM need in MB (fixed-memory services only):
    stt: need 1380 MB (was 1200)
  VRAM, informative only (dynamic VRAM: an upper bound, never for SERVICES):
    imggen: peak-based 8480 MB (gate.py threshold 6500)
```

1. Check the table first: a cap with failed jobs, a limit that was not confirmed, or a slow drift between caps (thermal) means
   run that task again with `--tasks X`.
2. Put the `name = W` lines under the matching GPU section of `power_profiles.conf`. Values are only worth it when measured:
   leave a service out when the curve is flat and the card's default is fine. Remember the gate applies the highest value among
   the running services.
3. Put the needs of the fixed-memory services (stt, tts-hq, upscaler, transcoder) into `SERVICES` in `gate/gate.py` (the middle
   number). **Do not paste the imggen, vidgen or vidpost block**: it is informative (dynamic VRAM). `resolve` currently carries a provisional 2500 MB:
   replace it with the measured figure, and check the cold start against the 120 s ready budget (about 2.5x headroom is
   comfortable).
4. `effectcraft` with verdict "CPU only" needs no lease and no profile. A "uses VRAM" verdict means look at it before treating it
   as CPU-only.
5. Run `gate/gate_selftest.py` and deploy as usual; commit the numbers with the date of the bench and the results file name,
   not the file itself (it holds host measurements).

## Safety notes

- It only uses the gate's HTTP API, read-only `nvidia-smi` and read-only `docker inspect` / `docker exec` (image id, model file
  sizes, ComfyUI version); the cap is set by the gate (`sudo -n /usr/bin/nvidia-smi -pl W` with a fixed argv). The bench expires by
  itself after `GATE_BENCH_TTL_S` (default 3600 s) and the gate restores the limit; if the limit cannot be read when the bench ends, the
  gate still tries to write the saved value before giving it up.
- It never stops or kills a process it did not start. A Resolve MCP child that does not exit is asked to stop once; Resolve
  itself is closed by the wrapper when its last client leaves.
- Inputs are synthetic or public text; outputs are deleted at the end.
- A JSON-RPC `error` answer from the Resolve MCP proxy (for example the gate refusing the wake because a person is using the
  card) is a failure of that job, never a success.
- Offline test: `python3 bench_gate_selftest.py` (fake gate, services, recorder, Resolve session and clock; no GPU needed).
- `gpu_selfcheck.py` (see `GPU_WATCH.md`) uses this script's host.env parse, gate client (with `GATE_BENCH_TOKEN` on `/bench/*` only), compute-app test,
  power-cap tolerance and hardware-throttle mask by loading it, so a change here changes the selfcheck too: run both selftests.
