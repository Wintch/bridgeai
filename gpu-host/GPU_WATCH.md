# GPU watch: is the card still fast, and is there a newer driver?

Principle: use the hardware to the maximum while caring for nature. Wasted energy is a defect, so a GPU host that silently falls back to
its slow stock speed is a bug to catch the same day, not a detail.

## Why

The GeForce RTX 3060 Ti host runs the NVIDIA driver pinned (`nvidia-driver-pinning-<version>`) with the open kernel module built by DKMS,
plus `gpu-unlock-dkms` and `gpu-unlock-firmware`. The unlock is active only with `gpu_unlock.targets=all` on the kernel command line. It lifts
the card's half-rate limit on FP16 matmul with FP32 accumulation (and TF32): SDXL-Lightning, 4 steps, took 2.96 s stock and 2.20 s unlocked
(about 35 % more time per image when it is lost, and about as much more energy at the same draw), and the efficient power point moves from
100 W to 130 W. Blender and NVENC are unaffected. A driver or kernel update, a DKMS build that did not happen, or a boot line lost in a
bootloader update puts the card back to stock without any error.

## Pieces

| piece | what | where it runs |
|---|---|---|
| `gpu_selfcheck.py` + `gpu_selfcheck_probe.py` | a few-second measurement: is the unlock active? Measures inside the gate's bench mode with `GATE_BENCH_TOKEN`, with `bench_gate.py`'s helpers | GPU host: `auto` by a user timer, `run` on demand |
| `driver_watch.py` | newer driver classified as SECURITY (urgent) or PERFORMANCE/FEATURE (measure first) from NVIDIA's public bulletins; pending kernel, DKMS gaps, /boot space, gpu-unlock versions and upstream releases; prints the operator steps; installs nothing | GPU host, weekly user timer |
| gate `GET /state` | `selfcheck` and `driver_watch` fields (fixed words and numbers only) | `gate/gate.py` |
| `bench_gate.py` | the helpers the selfcheck loads (env parse, gate client, compute-app test, cap tolerance, throttle mask) and the per-output efficiency of every task (`BENCH_GATE.md`) | GPU host |
| `gateway gpu status` | a line for a degraded card and for a pending update | `aibridge/gateway.py` |
| `aibridge/ops/gpu_watch.py` + `gpu-watch.timer` | reads each host's gate state every 30 min and alerts the operator through the ops bot | Docker host (the VM) |
| `gpu_outside.py` + `gtm.py` | what holds the card WITHOUT the gate: gputaskman's per-process VRAM, each process put in its container, compared with the gate's `/state` (section "GPU use outside the gate") | GPU host, user timer every minute |
| `install_gpu_watch.sh` | writes and enables the three host timers | GPU host |
| `upkeep/upkeep.py` | the update procedure as a tool: snapshot, plan (two apt transactions), check of the pasted simulation, verify, rollback, audit log; root steps are printed for the owner, never run (`upkeep/UPKEEP.md`) | GPU host |

The host needs, in `host.env`: `GATE_TOKEN` (reads `/state`) and `GATE_BENCH_TOKEN` (opens `/bench/*`; a value of its own, equal to the gate's and different from
`GATE_TOKEN`). Without `GATE_BENCH_TOKEN` the selfcheck refuses to run (below).

The VM unit is installed by `aibridge/ops/deploy_ops.sh --apply` (it ships every tracked unit and enables its timer). The host timers by
`gpu-host/install_gpu_watch.sh` (no sudo). The gate must be installed first.

## The selfcheck

### Method

`gpu_selfcheck_probe.py` runs inside a throwaway container of an image that already has torch (default `imggen:latest`, built on
`comfy-bench` with torch 2.9.1 / CUDA 12.8; `GPU_SELFCHECK_IMAGE` changes it): `--gpus all --network none --read-only --rm`, no capabilities,
the probe mounted read-only. It times three matmuls on the same square sizes (4096 and 6144, compute-bound), interleaved round by round, the
median of five rounds:

- `fp16_fp32acc`: fp16 inputs, FP32 accumulation (what models use)
- `fp16_fp16acc`: fp16 inputs, FP16 accumulation (`torch.backends.cuda.matmul.allow_fp16_accumulation`)
- `tf32`: fp32 inputs on the TF32 tensor path

**Why the ratio is a valid test.** On GeForce Ampere the tensor cores run FP16 with FP32 accumulation at half the rate of FP16 with FP16
accumulation (an NVIDIA limit of the consumer line); the unlock removes it. So `fp16_fp32acc / fp16_fp16acc` is about 0.5 on a stock card and
about 1.0 on an unlocked one, measured on the same card in the same seconds at the same power cap. The card is its own reference: no stored
baseline, and clock, temperature or power-limit drift hits numerator and denominator alike. The second witness, `tf32 / fp16_fp16acc`, is about
0.25 stock and 0.5 unlocked (the same whitepaper figures); it is recorded always and judges the verdict only once `TF32_JUDGES` is switched on
(see "Only verifiable on the real card").

If the image's torch cannot do FP16 accumulation, the probe reports only absolute TFLOPS and the host side compares `fp16_fp32acc` with
`selfcheck_baseline.json`. There is nothing on this path that tells a stock card from an unlocked one, so the baseline is NOT taken
from the first run: without it the verdict is `error` (`no_reference`), never `ok`. The operator seeds it once, on a card known to be
unlocked (`gpu_selfcheck.py run --force --accept-baseline`).

With a ratio, the ratio decides, and the TFLOPS are also compared with the baseline written by the first ratio-validated good run (ratio
above the threshold, no hardware throttle, the requested power cap really applied): a card whose clocks are locked low keeps a ratio near
1.0 but loses TFLOPS, and that is `degraded` (`tflops_low`). A baseline is compared only for the same card and the same applied cap.
That baseline also carries `unlock_seen_gpu`: once this card has been measured unlocked, the unlock is EXPECTED on it even if an upgrade
removes the package and the boot line together (the verdict is then `degraded`, not "unlock not expected on this host").

The cap actually applied (read back from `nvidia-smi` after the bench started) is the result's `cap_w`. If it is not the one asked for
(the gate clamped it), the reason `cap_mismatch` is recorded; the ratio still judges, no baseline is taken from that run and absolute
TFLOPS are not compared with it.

Recorded with every result: driver version, whether the boot line has the parameter, the `gpu_unlock` parameter value, whether the
`gpu_unlock` and `nvidia` modules are loaded, the gpu-unlock package versions, persistence mode, and sampled during the probe (every 0.5 s):
power limit and draw, SM clock under load, temperature, throttle reasons.

### Thresholds (constants at the top of `gpu_selfcheck.py`, each with its reasoning)

| constant | value | meaning |
|---|---|---|
| `OK_RATIO` | 0.75 | below it: `degraded` (`ratio_low`). Between stock (0.5) and unlocked (1.0) |
| `BORDER` | 0.68 to 0.82 | a ratio in this band is measured once more, the median of the two decides |
| `TF32_RATIO_MIN` | 0.375 | between 0.25 and 0.5; judges only when `TF32_JUDGES` is true |
| `BASELINE_FRACTION` | 0.85 | below 85 % of the baseline TFLOPS (same card, same applied cap) is `degraded` (`tflops_low`), in ratio mode and in the absolute fallback |
| `IDLE_UTIL_MAX` | 15 % | the card counts as in use above this GPU, encoder or decoder utilisation, even with no compute process |
| `SELFCHECK_WATTS` | 130 | fixed power cap during the check (the unlocked efficient point; the gate sets and restores it) |
| `STALE_S` | 7 days | a check is due again after a week |
| `PROBE_TIMEOUT_S` + `TTL_MARGIN_S` | 150 + 30 s | the bench lifetime (`GATE_BENCH_TTL_S`) one probe needs; shorter is a setup error (`bench_ttl_short`) |

Shared with `bench_gate.py` (loaded from it, not copied): the host.env parse and file search, the gate client, `check_compute_apps` (a small desktop app is not a job;
anything else on the card, or over 400 MiB, skips the check), `CAP_TOLERANCE_W` (1 W: the limit read back may differ from the one asked by that much), `THROTTLE_BAD`
(hardware slowdown, thermal, power brake) and `NET_IDLE_W` (18 W). One deliberate difference: `IDLE_UTIL_MAX` is 15 % here against 5 % in `bench_gate.py`, because the selfcheck
compares two rates measured on the same card in the same seconds (a light load does not move a ratio) while the bench measures Wh.

Throttle reasons that make a low ratio unreliable (hardware slowdown, thermal, power brake): the verdict becomes `error` (`throttled_hw`)
instead of `degraded`. A software power cap is expected at 130 W and does not excuse a low ratio.

### Verdict

`ok`, `degraded` or `error` (could not judge), plus reasons as fixed words: `ratio_low`, `tf32_ratio_low`, `tflops_low`, `param_missing`
(the boot line or the module parameter is off; a parameter file that cannot be read does not count when the boot line has it, the ratio
decides), `module_not_loaded`, `throttled_hw`, `probe_failed`, `no_gpu`, `no_reference` (absolute method, no baseline: `error`),
`no_gate_token` (`error`, no GATE_TOKEN), `no_bench_token` (`error`, no GATE_BENCH_TOKEN, equal to GATE_TOKEN, or refused by the gate),
`bench_ttl_short` (`error`, `GATE_BENCH_TTL_S` too short for one probe), `cap_mismatch` (informational: it does not make a verdict worse). The unlock being absent from
the host (no package, no parameter, no module, or `GPU_SELFCHECK_EXPECT_UNLOCK=0`) and a card that is not a GeForce RTX 30 are `ok` with
nothing measured: there is nothing to judge. `param_missing` and `module_not_loaded` make the verdict `degraded` even when the ratio looks fine.

### When it runs, and never over a person

`gpu_selfcheck.py auto` is run by `bridgeai-gpu-selfcheck.timer` (2 minutes after boot, then every 10 minutes) and does nothing unless a check is due:
no result yet, a new boot, a different kernel, driver or gpu-unlock package version, a week since the last, or an `error` result older than 6 hours.
A due check starts only when the card has been idle for `GPU_SELFCHECK_IDLE_S` (60 s): the gate's `/state` shows no running service, no lease,
no bench, `blocked` null (no VR, game or Resolve, no operator switch), and `nvidia-smi` lists no compute process, shows GPU, encoder and decoder
utilisation at or under `IDLE_UTIL_MAX`, and `nvidia-smi pmon` (when this driver has it) shows no process with load (a game, a compositor under load,
Parsec or an NVENC encode have no compute context and would otherwise be invisible). A failing `nvidia-smi` is a skip (`smi_failed`), never an idle card.
Then it uses the gate's bench mode: `POST /bench/start` (stack `selfcheck`, 130 W; Bearer `GATE_BENCH_TOKEN`, the only token `/bench/*` takes), probe, `POST /bench/end` in a `finally`. The gate refuses a bench
while any of those is true, so a job or a person that appears first wins: the check is skipped (exit 75, nothing changed, no result written) and the timer
retries in 10 minutes. It never interrupts and never queues behind anything.

While the probe runs, every 2 s the check reads the gate's `/state` and the power limit. If the gate ended the bench (it does that the moment a person's VR,
game or Resolve session or the operator's switch starts), the cap is no longer the applied one, or the gate stops answering, the probe container is
removed at once and the run is skipped without a verdict (`bench_ended`, `vr`, `busy`, `cap_changed`, `gate_down`, `bench_ttl`); the same checks run once more after
the probe ends and drop the numbers.

**The bench lifetime.** The gate ends a bench after `GATE_BENCH_TTL_S` (default 3600 s), read here the way `bench_gate.py` reads it. The check needs one probe's worst case
(`PROBE_TIMEOUT_S` + `TTL_MARGIN_S`) inside it: a shorter lifetime is a setup error (`bench_ttl_short`, exit 78, nothing started). It gives the probe only the lifetime that is
left, runs the grey-band second look only when a whole probe still fits (otherwise the first result stands, recorded as `borderline`), and stops without a verdict (`bench_ttl`)
10 seconds before the gate would end the bench under it. SIGTERM and SIGHUP remove the container too (killing the docker client alone would leave it running), then end
the bench. When a grey-band ratio is measured twice, the throttle bits of both runs are combined.

A host that never produces a result is not silent: with no `GATE_TOKEN` or no `GATE_BENCH_TOKEN` the check refuses to run, prints one line saying which and why
(`gpu_selfcheck: no GATE_BENCH_TOKEN in host.env ...`), writes an `error` result (`no_gate_token` / `no_bench_token`) and exits 78, so the unit
shows as failed (the same when the gate answers 401/403 to `/bench/start`: its token differs or it has bench mode off), and the ops bot alerts when the gate answers, the host has been up for hours and there is still no result (see Alerts). On demand: `gpu_selfcheck.py run [--force] [--no-gate]` (`--no-gate`
runs at the current power limit with no bench lock, no lease check and no cap control; the card must still be free, a gate wake during the probe is not refused, and nothing
re-applies the cap. It is manual only (`auto` never uses it) and needs `--force`: without it the command exits 64 and says why; with it a warning line is printed).

The whole check is seconds of GPU time; the container start and the torch import add some more. A wake that arrives during those seconds gets
`409 bench`, which the gateway reports as "busy, try later".

### Reading it

```
python3 gpu-host/gpu_selfcheck.py status      # last verdict, ratio, when, whether a check is due
cat ~/.local/state/bridgeai-gate/selfcheck.json   # the full record (driver, clocks, throttle, unlock facts)
```

Energy efficiency of the measurement: the result's `efficiency` carries `tflops_fp16_fp32acc_per_w_gross` (fp16 FP32-accumulate TFLOPS over the mean draw of the busy samples of
the probe) and `tflops_fp16_fp32acc_per_w_net18` (over that draw minus 18 W), with `busy_draw_w` and a `basis` sentence. The probe interleaves its three matmul kinds, so the draw is one
blended figure and only the FP32-accumulate rate (the one models use) is divided by it. It is in the result file and the summary line (`TFLOPS/W gross ... net18`); the gate does not
show it. Use it to compare drivers and power caps in TFLOPS per watt next to `bench_gate.py`'s per-output figures (`BENCH_GATE.md`).

Cost wording: for a degraded RTX 3060 Ti the result says about 35 % more time per job and about as much more energy (SDXL-Lightning figure);
other cards say "slower and more energy per job" without a number until one is measured (`KNOWN_COST`).

## The driver watch

`driver_watch.py run` (weekly; `status` prints the last report) compares the installed driver with the newest in the configured CUDA repo, for the
same branch and for newer ones. The pin makes apt keep the installed version, so the candidates are listed explicitly: the pinning packages the
repo offers (`apt-cache pkgnames nvidia-driver-pinning-`) and `apt-cache madison` of `cuda-drivers`, `nvidia-open`, `nvidia-driver`,
`nvidia-kernel-open-dkms`. It also reports:

- pending kernel updates (`apt-get -s dist-upgrade`, a simulation) and whether their headers come along: a new kernel needs the modules rebuilt by DKMS;
- installed kernels with no `installed` DKMS build of an nvidia or gpu-unlock module (`dkms status`): a reboot into one would come up without the driver or the unlock;
- `/boot` free space against one kernel plus initrd (margin 1.5x), only while a kernel update is pending: the new kernel is written while the old ones are still
  there. Two installed kernels filling a small `/boot` with nothing pending is how it is meant to be and is not flagged;
- the gpu-unlock package versions, a newer one in the repo, and a version requirement in its Depends that excludes the new driver;
- the age of the package lists (refreshing them needs root and is the operator's).

It never installs, removes, updates or reboots. The report ends with the exact steps; a newer branch comes with a reminder to check that it is a
production branch. The report is in `driver_watch.json` and `driver_watch.py status`.

### Security or performance: how an update is classified

Every available update gets a class, so the operator knows how much hurry it is (`driver_watch.py run`; `--no-network` skips this part):

| class (`update_class`) | meaning | what to do |
|---|---|---|
| `security` | the installed driver is below the version that a recent NVIDIA "GPU Display Driver" security bulletin fixes for its branch, and this update is at or above the fix (proven, for the target's own branch) | URGENT: update as soon as the card is free; the selfcheck after the reboot still decides whether the unlock survived |
| `performance` | an update that is not a proven security fix (the driver is current, or the update does not reach the fix) | measure before adopting: the selfcheck, then a bench of the real jobs (`bench_gate.py`), roll back if slower or costlier |
| `unknown` | the bulletins could not be read | treated as measure-first and reported as "could not check"; never guessed |
| `none` | nothing newer in the repo | |

`security` (the installed driver itself) is `current`, `fix_available` (a fixing version is in the repo), `fix_not_in_repo` (NVIDIA fixed it, the configured repo does not offer it
yet; refresh the lists or wait) or `unknown`. A fixing version of a NEWER branch counts only when every bulletin that affects the installed driver lists that branch with a fixed
version at or below it; a branch the bulletins do not list is not a proven fix. When the installed branch is not in the newest bulletin read and no older one shows a higher fix, the state is
`unknown` (`branch_unlisted_newest`): the branch is either unaffected or out of support, and the tables cannot say which, so "current" would be a guess.

Source (public, no token, no account): the repo `NVIDIA/product-security` on GitHub. `api.github.com/repos/NVIDIA/product-security/contents/` lists the year folders; the raw yearly
`README.md` index lists each bulletin with its dates (the rows titled "GPU Display Driver"); the raw `YEAR/ID/ID.md` of the newest four is parsed: only the rows of the "Updated Version"
table whose platform is `Linux(R<branch>)` (GeForce, RTX/Quadro/NVS, Tesla; the vGPU and Windows rows are not used) and whose version belongs to that branch; the highest per branch is
kept, plus the CVE count and highest CVSS base score. Nothing from the files is copied into the result except versions, ids, dates and numbers.

Network rules: unauthenticated GETs of `api.github.com` and `raw.githubusercontent.com` only, a generic `User-Agent`, at most four API calls a run (the listing, releases and tags
of gpu-unlock, plus raw files that do not count against the API limit), answers cached in `driver_watch_cache.json` in the gate's state dir (a bulletin is fetched again only when its
index row's update date changes; the index and listing are read every run). The rate limit is respected: a 403 or 429 sets a backoff from `Retry-After` or `X-RateLimit-Reset` (at most 6 h,
an hour when neither is given), the last call of a window sets it too, and while it runs nothing goes out and the cached answers are used (marked `stale`). Every failure is a fixed
word (`unreachable`, `rate_limited`, `not_found`, `http_error`, `bad_response`, `too_big`, `branch_unlisted`, `branch_unlisted_newest`, `incomplete_feed`, `no_bulletins`, `not_checked`) and the verdict is
`unknown`, "could not check", with the address to read by hand. `incomplete_feed`: a yearly index or one of the newest bulletins could not be had and there is no cached
copy, so the newest bulletin may be the one missing; a partial read never proves "current" (it can still prove a vulnerability). If the listing alone fails, the years come from the clock.

gpu-unlock upstream (`api.github.com/repos/Zagitta/gpu-unlock` releases and tags): `unlock_upstream` is `stable_newer` (a version above the installed `gpu-unlock-dkms` that is a
stable release: not flagged pre-release by GitHub, no alpha/beta/rc-like suffix, not a draft), `beta_only` (only pre-releases are newer), `none`, or `unknown`. A pre-release is described
in the report as NOT recommended and is never an alert: nothing in this tool recommends a beta automatically. Tags that are not versions (a packaging channel such as `unraid`, which is
the only release at the time of writing) are ignored and listed as channels.

The gate shows `security`, `update_class`, `security_fix` (the fixed version) and `unlock_upstream` as fixed words in `GET /state`; the ops bot turns them into the alerts below.
Recorded answers of both feeds are in `gpu-host/fixtures/driver_watch/` (trimmed; the selftest never touches the network).

### Operator steps for a driver update

The script prints these with this host's package names and versions; nothing runs by itself. Stop work on the card first (`gateway gpu off`, then the
gate's state shows no service running).

Class first: a `security` update is done now; a `performance` or `unknown` one is adopted only after step 10 below says so.

The prepared, checked version of this list (preflight, snapshot for the rollback, reading of the simulation, verify, audit log) is `python3 gpu-host/upkeep/upkeep.py plan driver --to <new>`; see `upkeep/UPKEEP.md`.

The pin and the driver packages are TWO apt transactions. apt reads the pin of the installed driver (`/etc/apt/preferences.d`) at the start of a transaction, so one
`apt install` with the new pin and the driver packages keeps the old driver ("is already the newest version").

1. `sudo apt update`
2. Transaction 1, the new pin alone: `sudo apt install nvidia-driver-pinning-<new>` (plus `nvidia-container-toolkit` when it is upgradable). The old pin is replaced; no driver package goes in this transaction.
3. Simulate transaction 2: `apt install -s --no-remove <the host's nvidia packages>`, or pipe it into `upkeep.py check-sim - --to <new>`. It must remove nothing (`gpu-unlock-dkms`, `gpu-unlock-firmware` and the running kernel least of all), and every nvidia package must go to `<new>`.
4. If `/boot` is tight, remove the oldest kernel first (its `linux-image-<release>` package, then `sudo apt autoremove --purge`).
5. Transaction 2: `sudo apt install --no-remove <the host's nvidia packages>`. DKMS rebuilds nvidia and gpu-unlock for every installed kernel that has headers.
6. `dkms status`: nvidia and gpu-unlock must say `installed` for every kernel in `/boot`; `df -h /boot`.
7. Reboot in a quiet window.
8. `python3 gpu-host/gpu_selfcheck.py run --force`. `ok`: the unlock survived, done. `degraded`: it did not.
9. Roll back if degraded, also in two transactions: `sudo apt install nvidia-driver-pinning-<old>` alone, then `sudo apt install --allow-downgrades <package>=<old version> ...` (the script prints the versions found at the time; `upkeep.py rollback` prints them from the snapshot), reboot, selfcheck again. Then wait for a gpu-unlock release that supports the new driver.
10. For a `performance` or `unknown` update: also run `python3 gpu-host/bench_gate.py --recheck` (idle window) and compare with the earlier numbers (time, Wh and the per-output figures);
   keep the update only if nothing got slower or costlier, otherwise roll back as in step 9. A `security` update that conflicts with gpu-unlock's version requirement is the operator's call (the fix wins unless the card is isolated).

A kernel update alone follows the same steps with `apt-get -s dist-upgrade` and `apt-get dist-upgrade`.

## gputaskman

[gputaskman](https://github.com/shanselman/gputaskman) (MIT, Python, read-only) shows per process what is on the card: VRAM, load per
engine (compute, encoder, decoder), and with root the runtimes and model files. Installed by hand on each GPU host, never in a container,
pinned to a version that was read before installing (0.4.5 on 2026-11-27: no outbound network, only read-only GETs to local LLM servers
on 127.0.0.1):

    sudo apt install python3-venv            # Debian ships venv without ensurepip
    python3 -m venv ~/.local/share/gputaskman
    ~/.local/share/gputaskman/bin/pip install gputaskman==0.4.5
    ln -sf ~/.local/share/gputaskman/bin/gputaskman ~/.local/bin/gputaskman

`gputaskman` (interactive), `gputaskman --json`, `gputaskman record -o FILE -i 0.5` then `gputaskman summary FILE`. As the host user it sees every
process's VRAM and load; `sudo` adds the runtime and model-file detail, which nothing here uses. Process and container names can name a
person's files or games: they stay on the host, and only counts and fixed words leave it. `gtm.py` holds the shared code: `bench_gate.py` records
every timed job with it (`gpu_procs` in `BENCH_GATE.md`), `gpu_outside.py` uses it below. `GPUTASKMAN` overrides the path.

## GPU use outside the gate

Every GPU job is supposed to ask the gate first. A container started by hand, a service left running after a test, or a program on the host
that grabs the card breaks the gate's VRAM accounting, its power profile and the host's sleep decision, and nothing fails. `gpu_outside.py run`
(every minute) puts each GPU process in its container (`/proc/<pid>/cgroup`, then `docker ps`) and judges it with `gtm.classify()`:

| process | verdict |
|---|---|
| in a gate service's container (the container is named like the service), the gate shows it running, starting or leased | fine |
| in a gate service's container, the gate shows it neither running nor leased | `service_not_leased` |
| in a place's container (`<name>doc`, `place-<name>-desktop`) | fine (places start and stop through the gate) |
| in any other container, or one docker does not name | `unknown_container` |
| on the host while a gate bench runs | fine (the bench owns the card) |
| on the host, the program of an external service (resolve) the gate shows leased or running | fine |
| on the host, a small desktop program (Xorg, sunshine, a browser...) up to 400 MiB | fine |
| any other program on the host | `host_process` |

A finding must be seen in three looks in a row, a minute apart (`pending` before that), so a service starting or stopping at that second is not an alarm.
The result is `outside.json` in the gate's state dir: status `ok`, `pending`, `outside`, `no_tool` (no gputaskman) or `error`, with the
names for the operator (`python3 gpu-host/gpu_outside.py status`). The gate's `/state` carries only `outside: {status, count, vram_mib, kinds, age_s}`.
It reads only and never stops anything.

The same look pushes the card's use to Zabbix (template "GPU host usage", `aibridge/ops/ZABBIX.md`) when `GPU_ZBX_SERVER` and `GPU_ZBX_HOST`
are in `host.env` (`HOST_ZBX_*` are used when those are absent). Zabbix pages "GPU used outside the gate" (Average): `gpu_watch.py` does not
send its own alert for it. A machine with no gate (the operator's PC) sets `GPU_NO_GATE=1`: no comparison (status `no_gate`), only the push.

## Alerts

| where | what |
|---|---|
| gate `GET /state` | `up_s` (host uptime); `selfcheck`: `verdict`, `reasons`, `age_s`, `driver`, `extra_cost_pct`; `driver_watch`: `age_s`, `updates` (`none`, `same_branch`, `newer_branch`), `newest`, `security` (`current`, `fix_available`, `fix_not_in_repo`, `unknown`), `update_class` (`none`, `security`, `performance`, `unknown`), `security_fix`, `unlock_upstream` (`none`, `stable_newer`, `beta_only`, `unknown`), `kernel_pending`, `dkms_gap`, `boot_low`, `unlock_mismatch`, `apt_stale`. Fixed words and numbers; no paths, no advice text. Null when never run |
| `gateway gpu status` | per host: one warning line when degraded (with the extra time when known), the only thing that changes a job's time. Driver, DKMS and `/boot` work are operator items and are not relayed to a person's bot |
| ops bot (`ops/gpu_watch.py`, 30 min) | `gpu-degraded:<host>` (daily until fixed), `gpu-selfcheck:<host>` (error; or never completed after 6 h of uptime; or no check since this boot after 6 h up while the last is over 14 days old; weekly), `gpu-driverwatch:<host>` (no driver report, or over 21 days old and not renewed since boot; weekly), `gpu-reboot-risk:<host>` (DKMS lacks a build for an installed kernel; every 3 days), `gpu-boot-space:<host>` (a kernel update is pending and `/boot` cannot take it; every 3 days), `gpu-security:<host>:<fixed version>` (**URGENT**, daily until updated: the installed driver is below the version a recent NVIDIA bulletin fixes and the repo offers a fixing version; when gpu-unlock excludes that driver it names the conflict and leaves the decision to the operator), `gpu-security-wait:<host>` (NVIDIA published the fix, the configured repo does not offer it yet; every 3 days), `gpu-driver:<host>:<version>` (weekly reminder for an update that is NOT a proven security fix: performance class, "measure before adopting", or unknown class when the bulletins could not be read; says "do not update yet" when gpu-unlock excludes that driver), `gpu-unlock-new:<host>` (a newer STABLE gpu-unlock upstream; weekly; a pre-release is never an alert), GPU use outside the gate is paged by Zabbix (template "GPU host usage"), not by the ops bot's gpu_watch. Each is resolved when it clears. A security state of `unknown` raises nothing by itself (fail soft: the host report says "could not check"). Not alerts: a pending kernel (it is not installed, so a reboot does not boot it, and DKMS builds at install time) and a host that does not answer (GPU hosts are off on purpose) |

Staleness and "never" are judged against the host's uptime (`up_s`: `/proc/uptime`, else the gate's own age), not the wall clock: a host that was off for
weeks answers `/state` the moment it boots, still carrying its old result, and its boot check has not had time to run. A gate that does not report `up_s`
yet (an older one) gets no "never"/"stale" alerts.

## Settings (`gpu-host/host.env` or the environment)

`GATE_TOKEN`, `GATE_BENCH_TOKEN`, `GATE_BENCH_TTL_S` (as the gate), `GATE_PORT`, `GATE_STATE_DIR` (as the gate), `GPU_SELFCHECK_IMAGE` (default `imggen:latest`), `GPU_SELFCHECK_WATTS` (130),
`GPU_SELFCHECK_IDLE_S` (60), `GPU_SELFCHECK_EXPECT_UNLOCK` (`0` or `1`; default: expected when the package, the boot parameter or the module is present).

## Only verifiable on the real card

- That `allow_fp16_accumulation` exists and takes effect in the image's torch and cuBLAS (the probe feature-detects and falls back to the baseline method).
- That the ratio really is near 0.5 stock and near 1.0 unlocked on this card, and the margin of 0.75 (run once with the unlock off, `gpu_unlock.targets` removed for one boot, and once on). Adjust `OK_RATIO` from those two numbers.
- The TF32 ratio (0.25 / 0.5 are whitepaper figures): once confirmed, set `TF32_JUDGES = True`.
- The `nvidia-smi` throttle field spelling of this driver (`clocks_event_reasons.active` or the older name; both are tried).
- The exact package names in the CUDA repo for this driver branch (pinning package, metapackages) and the `dkms status` format of this DKMS version.
- That this driver offers `utilization.encoder`/`utilization.decoder` and `nvidia-smi pmon -s u` (both are optional: the check falls back to GPU utilisation alone), and that an idle desktop stays under `IDLE_UTIL_MAX` so the check is not skipped for ever.
- The total time of a check (container start, torch import) against the "few seconds" of the measurement itself.

## Tests

`python3 -I gpu-host/gpu_selfcheck_selftest.py`, `python3 -I gpu-host/driver_watch_selftest.py` (recorded feed answers from `gpu-host/fixtures/driver_watch/`),
`python3 -I gpu-host/upkeep/upkeep_selftest.py` (the update procedure, fake dpkg/apt/dkms/gate, no root command ever started),
`python3 -I gpu-host/bench_gate_selftest.py` (also the efficiency figures), `python3 -I aibridge/ops/gpu_watch_selftest.py`,
`python3 -I gpu-host/gtm_selftest.py` (gputaskman folding, the outside-the-gate rules, the gate field, the Zabbix buckets and values against the template, the no-gate mode, the per-job recording with a fake recorder),
`python3 -I gpu-host/gate/gate_selftest.py` (the `/state` fields), `python3 -I aibridge/gateway_gpu_selftest.py` (the status lines). All offline: fake
`nvidia-smi`, dpkg, apt, docker, torch and gate.
