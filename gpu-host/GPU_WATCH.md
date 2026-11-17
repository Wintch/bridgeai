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
| `gpu_selfcheck.py` + `gpu_selfcheck_probe.py` | a few-second measurement: is the unlock active? | GPU host: `auto` by a user timer, `run` on demand |
| `driver_watch.py` | newer driver, pending kernel, DKMS gaps, /boot space, gpu-unlock versions; prints the operator steps; installs nothing | GPU host, weekly user timer |
| gate `GET /state` | `selfcheck` and `driver_watch` fields (fixed words and numbers only) | `gate/gate.py` |
| `gateway gpu status` | a line for a degraded card and for a pending update | `aibridge/gateway.py` |
| `aibridge/ops/gpu_watch.py` + `gpu-watch.timer` | reads each host's gate state every 30 min and alerts the operator through the ops bot | Docker host (the VM) |
| `install_gpu_watch.sh` | writes and enables the two host timers | GPU host |

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
`selfcheck_baseline.json`, written by the first good run (only when the unlock looked active by every other sign).

Recorded with every result: driver version, whether the boot line has the parameter, the `gpu_unlock` parameter value, whether the
`gpu_unlock` and `nvidia` modules are loaded, the gpu-unlock package versions, persistence mode, and sampled during the probe (every 0.5 s):
power limit and draw, SM clock under load, temperature, throttle reasons.

### Thresholds (constants at the top of `gpu_selfcheck.py`, each with its reasoning)

| constant | value | meaning |
|---|---|---|
| `OK_RATIO` | 0.75 | below it: `degraded` (`ratio_low`). Between stock (0.5) and unlocked (1.0) |
| `BORDER` | 0.68 to 0.82 | a ratio in this band is measured once more, the median of the two decides |
| `TF32_RATIO_MIN` | 0.375 | between 0.25 and 0.5; judges only when `TF32_JUDGES` is true |
| `BASELINE_FRACTION` | 0.85 | absolute fallback: below 85 % of the baseline TFLOPS is `degraded` (`tflops_low`) |
| `SELFCHECK_WATTS` | 130 | fixed power cap during the check (the unlocked efficient point; the gate sets and restores it) |
| `STALE_S` | 7 days | a check is due again after a week |

Throttle reasons that make a low ratio unreliable (hardware slowdown, thermal, power brake): the verdict becomes `error` (`throttled_hw`)
instead of `degraded`. A software power cap is expected at 130 W and does not excuse a low ratio.

### Verdict

`ok`, `degraded` or `error` (could not judge), plus reasons as fixed words: `ratio_low`, `tf32_ratio_low`, `tflops_low`, `param_missing`
(the boot line or the module parameter is off), `module_not_loaded`, `throttled_hw`, `probe_failed`, `no_gpu`. The unlock being absent from
the host (no package, no parameter, no module, or `GPU_SELFCHECK_EXPECT_UNLOCK=0`) and a card that is not a GeForce RTX 30 are `ok` with
nothing measured: there is nothing to judge. `param_missing` and `module_not_loaded` make the verdict `degraded` even when the ratio looks fine.

### When it runs, and never over a person

`gpu_selfcheck.py auto` is run by `bridgeai-gpu-selfcheck.timer` (2 minutes after boot, then every 10 minutes) and does nothing unless a check is due:
no result yet, a new boot, a different kernel, driver or gpu-unlock package version, a week since the last, or an `error` result older than 6 hours.
A due check starts only when the card has been idle for `GPU_SELFCHECK_IDLE_S` (60 s): the gate's `/state` shows no running service, no lease,
no bench, `blocked` null (no VR, game or Resolve, no operator switch), and `nvidia-smi` lists no compute process. Then it uses the gate's bench
mode: `POST /bench/start` (stack `selfcheck`, 130 W), probe, `POST /bench/end` in a `finally` (SIGTERM and SIGHUP also end it). The gate refuses a bench
while any of those is true, so a job or a person that appears first wins: the check is skipped (exit 75, nothing changed, no result written) and the timer
retries in 10 minutes. It never interrupts and never queues behind anything. On demand: `gpu_selfcheck.py run [--force] [--no-gate]` (`--no-gate`
runs at the current power limit; the card must still be free).

The whole check is seconds of GPU time; the container start and the torch import add some more. A wake that arrives during those seconds gets
`409 bench`, which the gateway reports as "busy, try later".

### Reading it

```
python3 gpu-host/gpu_selfcheck.py status      # last verdict, ratio, when, whether a check is due
cat ~/.local/state/bridgeai-gate/selfcheck.json   # the full record (driver, clocks, throttle, unlock facts)
```

Cost wording: for a degraded RTX 3060 Ti the result says about 35 % more time per job and about as much more energy (SDXL-Lightning figure);
other cards say "slower and more energy per job" without a number until one is measured (`KNOWN_COST`).

## The driver watch

`driver_watch.py run` (weekly; `status` prints the last report) compares the installed driver with the newest in the configured CUDA repo, for the
same branch and for newer ones. The pin makes apt keep the installed version, so the candidates are listed explicitly: the pinning packages the
repo offers (`apt-cache pkgnames nvidia-driver-pinning-`) and `apt-cache madison` of `cuda-drivers`, `nvidia-open`, `nvidia-driver`,
`nvidia-kernel-open-dkms`. It also reports:

- pending kernel updates (`apt-get -s dist-upgrade`, a simulation) and whether their headers come along: a new kernel needs the modules rebuilt by DKMS;
- installed kernels with no `installed` DKMS build of an nvidia or gpu-unlock module (`dkms status`): a reboot into one would come up without the driver or the unlock;
- `/boot` free space against one kernel plus initrd (margin 1.5x; this host class fits two kernels, so a pending kernel with two installed is flagged);
- the gpu-unlock package versions, a newer one in the repo, and a version requirement in its Depends that excludes the new driver;
- the age of the package lists (refreshing them needs root and is the operator's).

It never installs, removes, updates or reboots. The report ends with the exact steps; a newer branch comes with a reminder to check that it is a
production branch. The report is in `driver_watch.json` and `driver_watch.py status`.

### Operator steps for a driver update

The script prints these with this host's package names and versions; nothing runs by itself. Stop work on the card first (`gateway gpu off`, then the
gate's state shows no service running).

1. `sudo apt update`
2. Simulate: `sudo apt install -s nvidia-driver-pinning-<new> <the host's nvidia packages>`. It must not remove `gpu-unlock-dkms`, `gpu-unlock-firmware` or the running kernel. Replacing the old pin is expected.
3. If `/boot` is tight, remove the oldest kernel first (its `linux-image-<release>` package, then `sudo apt autoremove --purge`).
4. Apply the same command without `-s`. DKMS rebuilds nvidia and gpu-unlock for every installed kernel that has headers.
5. `dkms status`: nvidia and gpu-unlock must say `installed` for every kernel in `/boot`; `df -h /boot`.
6. Reboot in a quiet window.
7. `python3 gpu-host/gpu_selfcheck.py run --force`. `ok`: the unlock survived, done. `degraded`: it did not.
8. Roll back if degraded: `sudo apt install nvidia-driver-pinning-<old> <package>=<old version> ...` (the script prints the versions found at the time), reboot, selfcheck again. Then wait for a gpu-unlock release that supports the new driver.

A kernel update alone follows the same steps with `apt-get -s dist-upgrade` and `apt-get dist-upgrade`.

## Alerts

| where | what |
|---|---|
| gate `GET /state` | `selfcheck`: `verdict`, `reasons`, `age_s`, `driver`, `extra_cost_pct`; `driver_watch`: `age_s`, `updates` (`none`, `same_branch`, `newer_branch`), `newest`, `kernel_pending`, `dkms_gap`, `boot_low`, `unlock_mismatch`, `apt_stale`. Fixed words and numbers; no paths, no advice text. Null when never run |
| `gateway gpu status` | per host: a warning line when degraded (with the extra time when known), a note for a pending driver, a note for maintenance before the next reboot |
| ops bot (`ops/gpu_watch.py`, 30 min) | `gpu-degraded:<host>` (daily until fixed), `gpu-selfcheck:<host>` (error, or no completed check in 14 days), `gpu-reboot-risk:<host>` (every 3 days), `gpu-driver:<host>:<version>` (weekly reminder). Each is resolved when it clears. A host that does not answer is not an alert (GPU hosts are off on purpose) |

## Settings (`gpu-host/host.env` or the environment)

`GATE_TOKEN`, `GATE_PORT`, `GATE_STATE_DIR` (as the gate), `GPU_SELFCHECK_IMAGE` (default `imggen:latest`), `GPU_SELFCHECK_WATTS` (130),
`GPU_SELFCHECK_IDLE_S` (60), `GPU_SELFCHECK_EXPECT_UNLOCK` (`0` or `1`; default: expected when the package, the boot parameter or the module is present).

## Only verifiable on the real card

- That `allow_fp16_accumulation` exists and takes effect in the image's torch and cuBLAS (the probe feature-detects and falls back to the baseline method).
- That the ratio really is near 0.5 stock and near 1.0 unlocked on this card, and the margin of 0.75 (run once with the unlock off, `gpu_unlock.targets` removed for one boot, and once on). Adjust `OK_RATIO` from those two numbers.
- The TF32 ratio (0.25 / 0.5 are whitepaper figures): once confirmed, set `TF32_JUDGES = True`.
- The `nvidia-smi` throttle field spelling of this driver (`clocks_event_reasons.active` or the older name; both are tried).
- The exact package names in the CUDA repo for this driver branch (pinning package, metapackages) and the `dkms status` format of this DKMS version.
- The total time of a check (container start, torch import) against the "few seconds" of the measurement itself.

## Tests

`python3 -I gpu-host/gpu_selfcheck_selftest.py`, `python3 -I gpu-host/driver_watch_selftest.py`, `python3 -I aibridge/ops/gpu_watch_selftest.py`,
`python3 -I gpu-host/gate/gate_selftest.py` (the `/state` fields), `python3 -I aibridge/gateway_gpu_selftest.py` (the status lines). All offline: fake
`nvidia-smi`, dpkg, apt, docker, torch and gate.
