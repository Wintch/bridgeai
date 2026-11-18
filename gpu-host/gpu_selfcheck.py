#!/usr/bin/env python3
"""
gpu_selfcheck -- does this GPU still perform as unlocked? A check of a few seconds, on the GPU host (stdlib only).

  gpu_selfcheck.py auto                  what the systemd timer runs: check only when it is due (once per boot, after a driver,
                                         kernel or gpu-unlock package change, weekly, or to retry a skipped run) and only when
                                         the card has been idle for GPU_SELFCHECK_IDLE_S seconds. Exit 0 also when it skips.
  gpu_selfcheck.py run [--force]         check now, on demand. Exit 0 ok, 1 degraded, 2 error, 75 skipped (card in use), 78 setup error
                                         (no GATE_TOKEN, no GATE_BENCH_TOKEN, or a bench lifetime too short for one probe)
                                         (--accept-baseline: with a torch that cannot do FP16 accumulation there is no ratio, so the first
                                         absolute TFLOPS must be confirmed by the operator as measured on an unlocked card)
  gpu_selfcheck.py status                print the last result and whether a check is due

Why: the unlock (gpu-unlock-dkms + firmware, active only with gpu_unlock.targets=all on the kernel command line) makes FP16
matmul with FP32 accumulation and TF32 run at full rate on a GeForce Ampere card instead of half. A driver or kernel update, a
DKMS rebuild that did not happen, or a boot line lost in a bootloader update silently puts the card back to stock: every image
and video job then takes longer and costs more energy for the same result, and nothing fails. Wasted energy is a defect, so this
measures it at boot and after every change and tells the operator the same day (gate GET /state, `gateway gpu status`, the ops bot).

How it measures (no stored baseline needed): gpu_selfcheck_probe.py, inside a throwaway container of an image that already has
torch (`--gpus all --network none --read-only --rm`), times fp16 matmul with FP32 accumulation, with FP16 accumulation and TF32 on
the same sizes, interleaved. On GeForce Ampere the FP32-accumulate rate is half of the FP16-accumulate rate on a stock card (about
0.5) and equal when unlocked (about 1.0): the card is its own reference. Threshold 0.75 (between the two; see OK_RATIO). If this
torch cannot do FP16 accumulation, the absolute TFLOPS are compared with a baseline file that the OPERATOR seeds (run --force
--accept-baseline on a card known to be unlocked): without it that verdict is error (no_reference), never ok. With a ratio, the ratio
decides, and the TFLOPS against the baseline of the last ratio-validated good run flag a card that is slow in another way (tflops_low).
Alongside: power limit and draw, clocks, temperature, throttle reasons, driver version, the gpu_unlock parameter, modules loaded,
persistence mode. Verdict: ok / degraded / error (could not judge), reasons as fixed words.

Safety: the probe runs inside the gate's bench mode (start, fixed cap of SELFCHECK_WATTS, run, end in a finally; the gate refuses
every other wake for those seconds and restores the limit). /bench/* takes ONLY GATE_BENCH_TOKEN (the gate refuses the stacks'
GATE_TOKEN there), the same token and the same client bench_gate.py uses, read from host.env the same way; without it the check
refuses to run (no_bench_token, exit 78, one clear line). The bench lasts at most GATE_BENCH_TTL_S (gate default 3600 s): the check
needs one probe's worst case (PROBE_TIMEOUT_S + TTL_MARGIN_S) inside it, runs the second look of a grey-band ratio only when that
much of the lifetime is left, and stops without a verdict (bench_ttl) before the gate would end the bench under it. The host
helpers (env file parse, gate client, compute-app test, power-cap tolerance, hardware-throttle mask) are bench_gate.py's, loaded
from there, so the two scripts cannot drift. The gate refuses a bench while a service runs, a job is in flight, a
person's session (VR, a game, Resolve) is active or the operator's switch is on; nvidia-smi must also list no compute process, show
the card (GPU, encoder, decoder) nearly idle and no process with graphics/encode load, and answer at all. In those cases the check is
SKIPPED (exit 75) and retried by the timer; it never interrupts anything and never queues behind it. While the probe runs the gate's
state and the power limit are polled: if the gate ended the bench (a person's session began), the cap changed or the gate stopped
answering, the probe container is removed at once and the run is skipped without a verdict. SIGTERM does the same.
Results: $GATE_STATE_DIR/selfcheck.json (the gate shows fixed words from it in GET /state), selfcheck_baseline.json.
A host that never produces a result is noticed by the ops bot (ops/gpu_watch.py: the gate answers but has no selfcheck result after
hours of uptime). A missing GATE_TOKEN (GET /state) or GATE_BENCH_TOKEN (/bench/*) is written as an error result (no_gate_token,
no_bench_token) and the unit exits 78 so it shows as failed. `run --no-gate` (manual only, `auto` never uses it) skips the bench token, lease check and
cap control, so it needs `--force` (exit 64 without it) and prints a warning line.
Efficiency of the measurement itself: the result carries tflops_per_w (fp16 FP32-accumulate TFLOPS over the mean draw of the busy
samples of the whole probe, gross and net18 = draw minus 18 W; the three matmul kinds are interleaved, so it is one blended figure).
Settings (host.env or environment): GATE_TOKEN, GATE_BENCH_TOKEN, GATE_BENCH_TTL_S, GATE_PORT, GATE_STATE_DIR (as the gate),
GPU_SELFCHECK_IMAGE (default imggen:latest),
GPU_SELFCHECK_WATTS (default 130), GPU_SELFCHECK_IDLE_S (auto, default 60), GPU_SELFCHECK_EXPECT_UNLOCK (0 or 1; default: expected
when the package, the kernel parameter or the module is there).
"""
import argparse
import importlib.util
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "gpu_selfcheck_probe.py")


def _load_bench_gate():
    """bench_gate.py, loaded by path: the one place for the host.env parse, the gate client with its bench token, the compute-app test and
    the cap and throttle rules. (Loading runs no benchmark: bench_gate guards its main.)"""
    spec = importlib.util.spec_from_file_location("gpu_selfcheck_bench_gate", os.path.join(HERE, "bench_gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BG = _load_bench_gate()
GateError = BG.GateError

# --- thresholds (the reasoning is the point: change them only with a measurement) -------------------------------------------
# GeForce Ampere tensor cores: FP16 with FP32 accumulate runs at HALF the rate of FP16 with FP16 accumulate; the unlock lifts
# that. So fp16_fp32acc / fp16_fp16acc is about 0.5 stock and about 1.0 unlocked. 0.75 is the middle; a card lost in thermal or
# power limits drops both numerators alike, which is why a ratio (not TFLOPS) is the primary test.
OK_RATIO = 0.75
BORDER = (0.68, 0.82)          # a ratio in this band is measured once more and the median taken
# TF32 / fp16_fp16acc: about 0.25 stock, 0.5 unlocked. It is recorded always; it only decides the verdict once TF32_JUDGES is True,
# which waits for the first good run on the real card to show it near 0.5 (the 0.25/0.5 figures are from the Ampere whitepaper, not measured here).
TF32_RATIO_MIN = 0.375
TF32_JUDGES = False
# Fallback when the ratio cannot be measured: absolute fp16_fp32acc TFLOPS against the baseline file of the first good run.
# 15 % covers run-to-run noise at a fixed cap (a few %) and a slightly warmer card; stock is -50 %.
BASELINE_FRACTION = 0.85
# Power cap while measuring: the unlocked efficient point of the RTX 3060 Ti (100 W stock -> 130 W unlocked). Fixed, so numbers
# from different days compare, and so a check never runs the card at its 200 W default.
SELFCHECK_WATTS = 130
STALE_S = 7 * 86400            # a check is due again after a week (no reboot, no change)
RETRY_ERROR_S = 6 * 3600       # an "error" result (could not judge) is retried after this long
IDLE_S_AUTO, POLL_S = 60, 5
PROBE_TIMEOUT_S = 150          # a cold image start can take a while; the measurement itself is seconds
# Throttle bits (NVML clocksThrottleReason*): 0x1 idle, 0x2 application clocks, 0x4 software power cap (expected at a cap),
# 0x8 HW slowdown, 0x20 SW thermal, 0x40 HW thermal, 0x80 HW power brake. The last four make a ratio unreliable.
UNRELIABLE_MASK = BG.THROTTLE_BAD                            # bench_gate's rule for an invalid job: 0x8 | 0x20 | 0x40 | 0x80
THROTTLE_NAMES = {0x1: "idle", 0x2: "app_clocks", 0x4: "sw_power_cap", 0x8: "hw_slowdown", 0x10: "sync_boost", 0x20: "sw_thermal",
                  0x40: "hw_thermal", 0x80: "hw_power_brake", 0x100: "display_clocks"}
# Cards the ratio test is valid for: GeForce RTX 30 series (the half-rate FP32 accumulate of GA10x). Others: nothing to judge.
HALF_RATE_GPU = re.compile(r"GeForce RTX 30\d0", re.I)
# What a degraded card costs per job, where it was measured (SDXL-Lightning 4 steps: 2.96 s stock, 2.20 s unlocked).
KNOWN_COST = [("RTX 3060 Ti", round(100 * (2.96 / 2.20 - 1)), "SDXL-Lightning, 4 steps: 2.96 s stock vs 2.20 s unlocked")]
UNLOCK_OFF = ("", "off", "none", "0")
EXIT_SKIPPED = 75
EXIT_USAGE = 64                                              # --no-gate without --force
EXIT_CONFIG = 78                                             # no GATE_TOKEN / GATE_BENCH_TOKEN, bench too short: a setup error the unit must show as failed
TTL_MARGIN_S = 30                                            # of the gate's bench lifetime kept free: the gate's clock started before ours
NET_IDLE_W = BG.NET_IDLE_W                                   # "net18": gross minus 18 W, the repo's convention (bench_gate.py)
# The card counts as busy for a person above this utilisation (GPU, encoder or decoder, percent): a game, a desktop compositor under
# load, Parsec or an NVENC encode use the card without a compute context, which --query-compute-apps does not list. Looser than
# bench_gate's 5 % (BG.IDLE_UTIL_MAX) on purpose: that one guards Wh, this one a ratio of two rates measured on the same card at the
# same moment, which a light load does not move; a stricter rule here would skip forever on a desktop host.
IDLE_UTIL_MAX = 15
INFO_REASONS = ("cap_mismatch",)                             # recorded, do not make a verdict worse
STACK = "selfcheck"
BASELINE_FILE = "selfcheck_baseline.json"
CONTAINER = "bridgeai-gpu-selfcheck"


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


class Skipped(Exception):
    """The check did not run, or was stopped without a verdict (the card is in use, the gate ended the bench, ...). `why` is a fixed word."""
    def __init__(self, why):
        self.why = why
        super().__init__(why)


# ------------------------------------------------------------------------------------------------------------ system access
class Host:
    """Everything that touches the machine, in one place so a test can replace it."""

    def cmd(self, argv, timeout=20):
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout
        except FileNotFoundError:
            return 127, ""
        except subprocess.TimeoutExpired:
            return 124, ""

    def read(self, path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    def exists(self, path):
        return os.path.exists(path)

    def run_sampled(self, argv, timeout, sample_argv, period=0.5, abort=None, abort_every=2.0):
        """Run argv; while it runs call sample_argv every `period` s and abort() every `abort_every` s. (rc, stdout, [sample stdout lines]).
        When abort() returns a word, argv is killed and Skipped(word) is raised; so it is on any exception (SIGTERM becomes
        KeyboardInterrupt): the docker client is never left running. (The container itself is removed by run_probe.)"""
        samples = []
        try:
            p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except FileNotFoundError:
            return 127, "", samples
        out = []
        t = threading.Thread(target=lambda: out.append(p.communicate()[0]), daemon=True)
        t.start()
        end = time.time() + timeout
        next_abort = time.time() + abort_every
        try:
            while t.is_alive() and time.time() < end:
                rc, o = self.cmd(sample_argv, 10)
                if rc == 0 and o.strip():
                    samples.append(o.strip().splitlines()[0])
                if abort is not None and time.time() >= next_abort:
                    next_abort = time.time() + abort_every
                    why = abort()
                    if why:
                        raise Skipped(why)
                t.join(period)
        except BaseException:
            p.kill()
            t.join(5)
            raise
        if t.is_alive():
            p.kill()
            t.join(5)
            return 124, "", samples
        return p.returncode, out[0] if out else "", samples

    sleep = staticmethod(time.sleep)
    now = staticmethod(time.time)


class SetupError(Exception):
    """The host is not set up for this check (a token missing or refused, a bench lifetime too short): not a card verdict. `reason` is
    a fixed word, `msg` the one line the operator reads."""
    def __init__(self, reason, msg):
        self.reason, self.msg = reason, msg
        super().__init__(reason)


def make_gate(env):
    """The gate client of bench_gate.py: GATE_TOKEN for /state, GATE_BENCH_TOKEN for /bench/* (and only there)."""
    return BG.Gate(f"http://127.0.0.1:{env.get('GATE_PORT', '8700')}", env.get("GATE_TOKEN", ""), timeout=BG.BENCH_START_TIMEOUT,
                   bench_token=env.get("GATE_BENCH_TOKEN") or None)


def load_env(environ=None):
    """host.env (KEY=VALUE lines, never sourced) under the environment: bench_gate.py's parse and file search, plus GPU_SELFCHECK_*."""
    env = os.environ if environ is None else environ
    vals = BG.load_host_env(env)
    vals.update({k: v for k, v in env.items() if k.startswith("GPU_SELFCHECK_")})
    return vals


def state_dir_of(env):
    return env.get("GATE_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".local", "state", "bridgeai-gate")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------------------------------ facts
SMI_STATIC = ["name", "driver_version", "persistence_mode"]
SMI_LIVE = ["power.limit", "power.draw", "clocks.sm", "clocks.max.sm", "temperature.gpu", "utilization.gpu"]
UTIL_FIELDS = ("utilization.gpu", "utilization.encoder", "utilization.decoder")
THROTTLE_FIELDS = ["clocks_event_reasons.active", "clocks_throttle_reasons.active"]    # renamed in newer drivers; the old name may be gone


class Smi:
    def __init__(self, host):
        self.host = host
        self.throttle_field = None                           # the spelling this driver accepts, found once

    def query(self, fields):
        """{field: str|None} of the first card, or None when nvidia-smi fails."""
        rc, out = self.host.cmd(["nvidia-smi", "--query-gpu=" + ",".join(fields), "--format=csv,noheader,nounits"], 15)
        if rc != 0 or not out.strip():
            return None
        vals = [v.strip() for v in out.strip().splitlines()[0].split(",")]
        if len(vals) != len(fields):
            return None
        return {f: (None if v.startswith("[") or v in ("", "N/A") else v) for f, v in zip(fields, vals)}

    def live_fields(self):
        """The sampling query, with the throttle field spelled as this driver wants (probed once)."""
        if self.throttle_field is None:
            for f in THROTTLE_FIELDS:
                if self.query([f]) is not None:
                    self.throttle_field = f
                    break
            else:
                self.throttle_field = ""
        return SMI_LIVE + ([self.throttle_field] if self.throttle_field else [])

    def sample_argv(self):
        return ["nvidia-smi", "--query-gpu=" + ",".join(self.live_fields()), "--format=csv,noheader,nounits"]

    def compute_apps(self):
        """Lines of the compute processes; None when nvidia-smi fails (a failing query is not an idle card)."""
        rc, out = self.host.cmd(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"], 15)
        return [l for l in out.splitlines() if l.strip()] if rc == 0 else None

    def util_max(self):
        """The highest of GPU, encoder and decoder utilisation (percent); the encoder/decoder fields are tried and dropped when this
        driver lacks them. None when nvidia-smi does not answer."""
        for fields in (UTIL_FIELDS, UTIL_FIELDS[:1]):
            q = self.query(list(fields))
            if q is not None:
                vals = [num(v) for v in q.values() if num(v) is not None]
                return max(vals) if vals else None
        return None

    def graphics_busy(self):
        """True when `nvidia-smi pmon` shows a process (graphics or compute) with SM, memory, encoder or decoder load; False when none;
        None when pmon is not available on this driver (the utilisation figure still applies)."""
        rc, out = self.host.cmd(["nvidia-smi", "pmon", "-c", "1", "-s", "u"], 15)
        if rc != 0:
            return None
        for line in out.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if any((num(x) or 0) > 0 for x in line.split()[3:8]):
                return True
        return False

    def activity(self):
        return {"apps": self.compute_apps(), "util": self.util_max(), "graphics": self.graphics_busy()}


def hexnum(s):
    try:
        return int(s, 16) if s and s.lower().startswith("0x") else int(s)
    except (TypeError, ValueError):
        return 0


def throttle_names(mask):
    return [n for bit, n in sorted(THROTTLE_NAMES.items()) if mask & bit]


def summarize_samples(samples, fields):
    """Max temperature and draw, the median SM clock while the card was busy, the union of throttle reasons."""
    rows = []
    for line in samples:
        vals = [v.strip() for v in line.split(",")]
        if len(vals) == len(fields):
            rows.append({f: (None if v.startswith("[") or v in ("", "N/A") else v) for f, v in zip(fields, vals)})
    busy = [num(r["clocks.sm"]) for r in rows if (num(r.get("utilization.gpu")) or 0) >= 50 and num(r.get("clocks.sm")) is not None]
    mask = 0
    for r in rows:
        mask |= hexnum(r.get("clocks_event_reasons.active") or r.get("clocks_throttle_reasons.active"))
    pick = lambda k, fn: fn([num(r[k]) for r in rows if num(r[k]) is not None] or [None])
    draws = [num(r["power.draw"]) for r in rows if (num(r.get("utilization.gpu")) or 0) >= 50 and num(r.get("power.draw")) is not None]
    return {"samples": len(rows), "temp_max_c": pick("temperature.gpu", max), "power_draw_max_w": pick("power.draw", max),
            "power_draw_busy_avg_w": round(statistics.mean(draws), 1) if draws else None,
            "clocks_sm_busy_mhz": round(statistics.median(busy)) if busy else None,
            "throttle_mask": mask, "throttle_names": throttle_names(mask)}


def pkg_version(host, name):
    """(installed?, version) from dpkg; (False, None) when the package is not installed."""
    rc, out = host.cmd(["dpkg-query", "-W", "-f=${db:Status-Abbrev}|${Version}", name], 10)
    st, _, ver = out.partition("|")
    return (rc == 0 and st.strip().startswith("ii"), ver.strip() or None) if rc == 0 else (False, None)


def gather(host, smi, env, state_dir=None):
    """Everything known without running the probe. `state_dir` lets the check remember that this card was seen unlocked."""
    s = smi.query(SMI_STATIC + SMI_LIVE) or {}
    cmdline = host.read("/proc/cmdline") or ""
    m = re.search(r"(?:^|\s)gpu_unlock\.targets=(\S+)", cmdline)
    raw_param = host.read("/sys/module/gpu_unlock/parameters/targets")
    param = (raw_param or "").strip()
    seen = (read_json(os.path.join(state_dir, BASELINE_FILE)) or {}).get("unlock_seen_gpu") if state_dir else None
    seen_before = bool(seen) and seen == s.get("name")
    pkg_dkms, v_dkms = pkg_version(host, "gpu-unlock-dkms")
    pkg_fw, v_fw = pkg_version(host, "gpu-unlock-firmware")
    f = {
        "gpu": {"name": s.get("name"), "driver": s.get("driver_version"), "persistence": (s.get("persistence_mode") or "").lower() or None,
                "power_limit_w": num(s.get("power.limit")), "power_draw_w": num(s.get("power.draw")),
                "clocks_sm_mhz": num(s.get("clocks.sm")), "clocks_max_sm_mhz": num(s.get("clocks.max.sm")),
                "temp_c": num(s.get("temperature.gpu"))},
        "unlock": {"cmdline_param": bool(m) and m.group(1).lower() not in UNLOCK_OFF, "param_value": param, "param_readable": raw_param is not None,
                   "seen_active_before": seen_before, "module_loaded": host.exists("/sys/module/gpu_unlock"), "nvidia_module_loaded": host.exists("/sys/module/nvidia"),
                   "pkg_installed": pkg_dkms, "fw_installed": pkg_fw},
        "fingerprint": {"kernel": (host.read("/proc/sys/kernel/osrelease") or "").strip(), "driver": s.get("driver_version"),
                        "unlock_pkg": v_dkms, "unlock_fw": v_fw},
        "boot_id": (host.read("/proc/sys/kernel/random/boot_id") or "").strip(),
        "smi_ok": bool(s),
    }
    u = f["unlock"]
    forced = env.get("GPU_SELFCHECK_EXPECT_UNLOCK")
    # Expected when anything of the unlock is present, or when this card was once measured unlocked here: a package lost in an upgrade
    # together with the boot line is exactly the regression this exists to catch, and must not read as "not expected on this host".
    u["expected"] = (forced == "1") if forced in ("0", "1") else bool(u["pkg_installed"] or u["cmdline_param"] or u["module_loaded"]
                                                                       or param.lower() not in UNLOCK_OFF or seen_before)
    return f


def static_reasons(unlock):
    """Reasons visible without measuring: the patch cannot be active."""
    out = []
    if not unlock["module_loaded"] or not unlock["nvidia_module_loaded"]:
        out.append("module_not_loaded")
    if not unlock["cmdline_param"] and unlock["param_value"].lower() in UNLOCK_OFF:
        out.append("param_missing")
    elif unlock["module_loaded"] and unlock.get("param_readable", True) and unlock["param_value"].lower() in UNLOCK_OFF:
        out.append("param_missing")                          # on the boot line but the module does not use it
    # (a parameter file that cannot be read says nothing when the boot line has it: the measured ratio decides)
    return out


def cost_for(gpu_name):
    """(extra percent per job, how it was measured) for a card with a measurement; (None, None) otherwise."""
    for key, pct, how in KNOWN_COST:
        if gpu_name and key.lower() in gpu_name.lower():
            return pct, how
    return None, None


# ---------------------------------------------------------------------------------------------------------------- verdict
def judge(probes, baseline, cap_w, gpu_name, static, samples=None, tf32_judges=None, requested_w=None, accept_baseline=False):
    """The verdict from the probe results (a list of dicts: the probe's JSON, or {"error": ...}), pure. `cap_w` is the power limit the
    run really had, `requested_w` the one asked of the gate (None without the gate). Returns {verdict, reasons, method, ratio,
    ratio_tf32, tflops, borderline, tflops_vs_baseline, baseline_update}."""
    tf32_judges = TF32_JUDGES if tf32_judges is None else tf32_judges
    good = [p for p in probes if isinstance(p, dict) and not p.get("error") and (p.get("tflops") or {}).get("fp16_fp32acc")]
    res = {"verdict": "ok", "reasons": list(static), "method": "none", "ratio": None, "ratio_tf32": None, "tflops": None,
           "borderline": False, "tflops_vs_baseline": None, "baseline_update": None}
    if not good:
        res["reasons"].append("probe_failed")
        res["verdict"] = "degraded" if static else "error"
        return res
    med = lambda key, sub=None: (lambda xs: round(statistics.median(xs), 3) if xs else None)(
        [(p[key] if sub is None else (p.get(key) or {}).get(sub)) for p in good if (p[key] if sub is None else (p.get(key) or {}).get(sub)) is not None])
    res["tflops"] = {m: med("tflops", m) for m in ("fp16_fp32acc", "fp16_fp16acc", "tf32")}
    res["ratio"], res["ratio_tf32"] = med("ratio"), med("ratio_tf32")
    t32 = res["tflops"]["fp16_fp32acc"]
    cap_ok = requested_w is None or abs(requested_w - cap_w) <= BG.CAP_TOLERANCE_W      # bench_gate's tolerance for the limit read back
    if not cap_ok:
        res["reasons"].append("cap_mismatch")                # the gate gave another cap than asked: absolute TFLOPS no longer compare with the baseline
    if baseline and baseline.get("gpu") == gpu_name and baseline.get("cap_w") == cap_w and num(baseline.get("tflops_fp16_fp32acc")):
        res["tflops_vs_baseline"] = round(t32 / baseline["tflops_fp16_fp32acc"], 3)
    vs = res["tflops_vs_baseline"]
    if res["ratio"] is not None:
        res["method"] = "ratio"
        res["borderline"] = BORDER[0] <= res["ratio"] <= BORDER[1]
        if res["ratio"] < OK_RATIO:
            res["reasons"].append("ratio_low")
        if tf32_judges and res["ratio_tf32"] is not None and res["ratio_tf32"] < TF32_RATIO_MIN:
            res["reasons"].append("tf32_ratio_low")
        if vs is not None and vs < BASELINE_FRACTION:
            res["reasons"].append("tflops_low")              # slow in a way the ratio cannot see (clocks locked low, both rates down)
    else:
        res["method"] = "absolute"
        if vs is not None:
            if vs < BASELINE_FRACTION:
                res["reasons"].append("tflops_low")
        elif not static:
            if accept_baseline and cap_ok:
                res["baseline_update"] = {"gpu": gpu_name, "cap_w": cap_w, "tflops_fp16_fp32acc": t32, "accepted": True}   # the operator vouched for it
            else:
                res["reasons"].append("no_reference")        # no ratio and no usable reference: cannot judge, and never "ok"
    measured_bad = [r for r in res["reasons"] if r in ("ratio_low", "tf32_ratio_low", "tflops_low")]
    hot = bool(samples and samples.get("throttle_mask", 0) & UNRELIABLE_MASK)
    if hot and measured_bad:
        res["reasons"] = [r for r in res["reasons"] if r not in measured_bad] + ["throttled_hw"]
        res["verdict"] = "degraded" if static else "error"      # a hot or braked card says nothing about the unlock
        return res
    bad = [r for r in res["reasons"] if r not in INFO_REASONS and r != "no_reference"]
    res["verdict"] = "degraded" if bad else "error" if "no_reference" in res["reasons"] else "ok"
    if res["verdict"] == "ok" and res["method"] == "ratio" and not static and cap_ok and not hot and res["ratio"] >= OK_RATIO:
        # a ratio-validated good run: the card was unlocked now. Keep it as the reference and remember that this card is expected unlocked.
        res["baseline_update"] = {"gpu": gpu_name, "cap_w": cap_w, "tflops_fp16_fp32acc": t32, "unlock_seen_gpu": gpu_name}
    return res


# ----------------------------------------------------------------------------------------------------- the run, with the gate
def idle_reason(state, act):
    """None when nothing uses the card, else a fixed word. `act` is Smi.activity(): compute processes, utilisation, graphics load."""
    if state.get("bench"):
        return "bench"
    if state.get("blocked"):
        return "vr" if state["blocked"] == "vr" else "busy"
    svcs = state.get("services") if isinstance(state.get("services"), dict) else {}
    if any(isinstance(v, dict) and (v.get("running") or v.get("leases")) for v in svcs.values()):
        return "service"
    if act["apps"] is None or act["util"] is None:
        return "smi_failed"                                  # a failing query is not an idle card
    if (act["apps"] and BG.check_compute_apps(act["apps"])) or act["graphics"]:
        return "card_in_use"                                 # bench_gate's test: a small desktop app (browser, compositor) is not a job
    if act["util"] > IDLE_UTIL_MAX:
        return "card_busy"                                   # a game, a compositor, Parsec or an encode: busy without a compute context
    return None


def probe_argv(image, probe_path):
    return ["docker", "run", "--rm", "--name", CONTAINER, "--gpus", "all", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "256", "--memory", "4g", "--user", "1000:1000",
            "--tmpfs", "/tmp:rw,size=256m", "-e", "HOME=/tmp", "-e", "CUDA_CACHE_DISABLE=1", "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "NVIDIA_DRIVER_CAPABILITIES=compute,utility", "-v", f"{probe_path}:/probe.py:ro", "--entrypoint", "python3",
            image, "-I", "/probe.py"]


def run_probe(host, smi, image, probe_path=PROBE, abort=None, timeout=PROBE_TIMEOUT_S):
    """(probe dict, sample summary). The container is removed whatever happens: on a timeout, when `abort` ends the run (Skipped is
    raised) and on SIGTERM (killing the docker client alone would leave the container loading the card)."""
    host.cmd(["docker", "rm", "-f", CONTAINER], 30)          # a leftover of a killed run would block the name
    sample = smi.sample_argv()
    try:
        rc, out, samples = host.run_sampled(probe_argv(image, probe_path), timeout, sample, abort=abort)
    except BaseException:
        host.cmd(["docker", "rm", "-f", CONTAINER], 30)
        raise
    if rc == 124:
        host.cmd(["docker", "rm", "-f", CONTAINER], 30)
    summary = summarize_samples(samples, smi.live_fields())
    probe = None
    for line in reversed(out.strip().splitlines()):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            probe = d
            break
    if probe is None or rc not in (0, 3):
        probe = {"error": "timeout" if rc == 124 else "no_docker" if rc == 127 else "probe_failed"}
    return probe, summary


def power_limit(smi):
    cur = smi.query(["power.limit"]) or {}
    v = num(cur.get("power.limit"))
    return int(round(v)) if v is not None else None


def bench_left_s(ctx):
    """Seconds of the gate's bench lifetime still to run; None when there is no bench."""
    t0 = ctx.get("bench_t0")
    return None if t0 is None else ctx["bench_ttl_s"] - (ctx["now"]() - t0)


def make_abort(ctx, bench, expect_w):
    """The check that runs while the probe does: None while nothing changed, else a fixed word. The gate ends a bench by itself
    when a person's session starts or its lifetime (GATE_BENCH_TTL_S) is over, and the probe must not keep loading the card (or be
    judged at another power limit) after that."""
    gate, smi = ctx.get("gate"), ctx["smi"]

    def abort():
        if bench:
            left = bench_left_s(ctx)
            if left is not None and left < TTL_MARGIN_S / 3:
                return "bench_ttl"
            try:
                code, st = gate.call("GET", "/state")
            except GateError:
                return "gate_down"
            if code != 200:
                return "gate_down"
            b = st.get("bench")
            if not isinstance(b, dict) or b.get("id") != bench:
                return "bench_ended"
            if st.get("blocked"):
                return "vr" if st["blocked"] == "vr" else "busy"
        if expect_w is not None:
            now_w = power_limit(smi)
            if now_w is not None and abs(now_w - expect_w) > BG.CAP_TOLERANCE_W:
                return "cap_changed"
        return None
    return abort


def merge_summaries(items):
    """One sample summary for several probes: the union of throttle bits (a hardware throttle in the first run still counts when a
    second run was needed), the worst temperature and draw."""
    items = [x for x in items if x]
    if len(items) <= 1:
        return items[0] if items else None
    mask = 0
    for x in items:
        mask |= x.get("throttle_mask", 0)
    pick = lambda k: max([x[k] for x in items if x.get(k) is not None] or [None])
    clocks = [x["clocks_sm_busy_mhz"] for x in items if x.get("clocks_sm_busy_mhz") is not None]
    draws = [x["power_draw_busy_avg_w"] for x in items if x.get("power_draw_busy_avg_w") is not None]
    return {"samples": sum(x.get("samples", 0) for x in items), "temp_max_c": pick("temp_max_c"), "power_draw_max_w": pick("power_draw_max_w"),
            "power_draw_busy_avg_w": round(statistics.mean(draws), 1) if draws else None,
            "clocks_sm_busy_mhz": round(statistics.median(clocks)) if clocks else None, "throttle_mask": mask, "throttle_names": throttle_names(mask)}


def check_once(ctx, idle_s=0, use_gate=True):
    """One measurement. Returns the result dict. Raises Skipped when the card is in use (nothing was changed) or when the gate ended the
    bench / the power limit changed while the probe ran (the container is gone, nothing is judged)."""
    host, smi, env = ctx["host"], ctx["smi"], ctx["env"]
    facts = ctx["facts"]
    cap = int(num(env.get("GPU_SELFCHECK_WATTS")) or SELFCHECK_WATTS)
    image = env.get("GPU_SELFCHECK_IMAGE") or "imggen:latest"
    gate = ctx.get("gate")
    sleep = ctx["sleep"]
    ttl = ctx["bench_ttl_s"] = BG.bench_ttl_s(env)           # the gate's bench lifetime as this host sets it
    if use_gate and ttl < PROBE_TIMEOUT_S + TTL_MARGIN_S:
        raise SetupError("bench_ttl_short", f"GATE_BENCH_TTL_S is {ttl:.0f} s: the check needs at least {PROBE_TIMEOUT_S + TTL_MARGIN_S} s of bench "
                         "lifetime for one probe (the gate default is 3600 s); raise it in host.env and restart the gate")
    ctx["bench_t0"] = None
    # 1. idle for idle_s seconds (read only): the gate's view and the card's own compute list, utilisation and graphics load
    polls = int(idle_s // POLL_S) + 1
    for i in range(polls):
        if use_gate:
            try:
                code, state = gate.call("GET", "/state")
            except GateError:
                raise Skipped("gate_down")
            if code != 200:
                raise Skipped("gate_down")
        else:
            state = {}
        why = idle_reason(state, smi.activity())
        if why:
            raise Skipped(why)
        if i < polls - 1:
            sleep(POLL_S)
    # 2. the bench: the gate refuses other wakes, sets the cap, restores it at the end
    bench = None
    if use_gate:
        try:
            code, out = gate.call("POST", "/bench/start", {"stack": STACK, "watts": cap})
        except GateError:
            raise Skipped("gate_down")
        if code == 409:
            raise Skipped(out.get("why") if isinstance(out.get("why"), str) else "busy_jobs")
        if code in (401, 403):                               # 403 bench_disabled (the gate has no bench token, or it equals GATE_TOKEN) / 401 wrong token
            raise SetupError("no_bench_token", f"the gate refused /bench/start ({code} {out.get('why') or 'bad token'}): GATE_BENCH_TOKEN here must equal the "
                             "gate's GATE_BENCH_TOKEN, and differ from GATE_TOKEN")
        if code != 200 or not isinstance(out.get("bench"), str):
            raise Skipped("bench_failed")
        bench = out["bench"]
        ctx["bench_t0"] = ctx["now"]()
    probes, summaries, applied = [], [], cap
    requested = cap if bench else None
    try:
        now_w = power_limit(smi)
        applied = now_w if now_w is not None else (cap if bench else int(facts["gpu"]["power_limit_w"] or 0))
        abort = make_abort(ctx, bench, applied or None)
        for attempt in range(2):
            left = bench_left_s(ctx)
            if attempt and left is not None and left < PROBE_TIMEOUT_S + TTL_MARGIN_S:
                break                                        # the grey-band second look must fit in the bench lifetime that is left
            budget = PROBE_TIMEOUT_S if left is None else min(PROBE_TIMEOUT_S, left - TTL_MARGIN_S / 3)
            probe, summary = run_probe(host, smi, image, ctx.get("probe", PROBE), abort, budget)
            why = abort()                                    # the gate may have ended the bench in the last seconds of the run
            if why:
                raise Skipped(why)
            probes.append(probe)
            summaries.append(summary)
            # a second look only when the first ratio is in the grey band
            r = probe.get("ratio") if isinstance(probe, dict) else None
            if r is None or not (BORDER[0] <= r <= BORDER[1]):
                break
            sleep(5)
            why = abort()
            if why:
                raise Skipped(why)
    finally:
        if bench:
            try:
                gate.call("POST", "/bench/end", {"bench": bench})
            except GateError:
                log("could not end the bench: the gate ends it by itself after GATE_BENCH_TTL_S")
    return judge_and_build(ctx, probes, merge_summaries(summaries), applied, requested)


def judge_and_build(ctx, probes, samples, applied, requested=None):
    facts = ctx["facts"]
    gpu = facts["gpu"]["name"]
    baseline = read_json(os.path.join(ctx["state_dir"], BASELINE_FILE))
    static = static_reasons(facts["unlock"])
    j = judge(probes, baseline, applied, gpu, static, samples, requested_w=requested, accept_baseline=bool(ctx.get("accept_baseline")))
    return build_result(ctx, j, probes, samples, applied)


def tflops_per_w(tflops, samples):
    """Energy efficiency of the probe: fp16 FP32-accumulate TFLOPS over the mean draw of the busy samples (the probe interleaves its three
    matmul kinds, so the draw is one blended figure and this one number is labelled by the rate it divides). gross = over the draw,
    net18 = over the draw minus 18 W (bench_gate's convention). None when either figure is missing."""
    t = (tflops or {}).get("fp16_fp32acc")
    w = (samples or {}).get("power_draw_busy_avg_w")
    if not t or not w:
        return None
    net = w - NET_IDLE_W
    return {"tflops_fp16_fp32acc_per_w_gross": round(t / w, 4), "tflops_fp16_fp32acc_per_w_net18": round(t / net, 4) if net > 1.0 else None,
            "busy_draw_w": w, "basis": "fp16 FP32-accumulate TFLOPS over the mean draw of the busy samples of the whole probe (three matmul kinds interleaved)"}


def build_result(ctx, j, probes, samples, applied):
    facts = ctx["facts"]
    good = [p for p in probes if isinstance(p, dict) and not p.get("error")]
    pct, how = cost_for(facts["gpu"]["name"]) if j["verdict"] == "degraded" else (None, None)
    res = {"schema": 1, "at": int(ctx["now"]()), "boot_id": facts["boot_id"], "verdict": j["verdict"], "reasons": j["reasons"],
           "method": j["method"], "unlock_expected": facts["unlock"]["expected"], "ratio": j["ratio"], "ratio_tf32": j["ratio_tf32"],
           "tflops": j["tflops"], "tflops_vs_baseline": j["tflops_vs_baseline"], "borderline": j["borderline"], "cap_w": applied,
           "driver": facts["gpu"]["driver"], "fingerprint": facts["fingerprint"], "gpu": facts["gpu"], "unlock": facts["unlock"],
           "run": samples, "efficiency": tflops_per_w(j["tflops"], samples), "torch": good[0].get("torch") if good else None, "probe_rounds": good[0].get("rounds") if good else None,
           "probe_seconds": good[0].get("seconds") if good else None, "extra_cost_pct": pct, "extra_cost_basis": how,
           "probe_errors": [p.get("error") for p in probes if isinstance(p, dict) and p.get("error")]}
    res["_baseline_update"] = j.get("baseline_update")       # persisted by finish(), never part of the result file
    return res


def finish(ctx, res):
    """Persist the result (and the first ratio-validated baseline) and print the summary. Returns the exit code."""
    sd = ctx["state_dir"]
    bu = res.pop("_baseline_update", None)
    write_json(os.path.join(sd, "selfcheck.json"), res)
    old = read_json(os.path.join(sd, BASELINE_FILE))
    accepted = bool(bu) and bu.pop("accepted", False)
    if bu and (not old or accepted):
        write_json(os.path.join(sd, BASELINE_FILE), dict(bu, at=res["at"], driver=res["driver"]))     # the first ratio-validated run, or the operator's
        res["baseline_written"] = True
    elif bu and bu.get("unlock_seen_gpu") and old.get("unlock_seen_gpu") != bu["unlock_seen_gpu"]:
        write_json(os.path.join(sd, BASELINE_FILE), dict(old, unlock_seen_gpu=bu["unlock_seen_gpu"]))   # an older baseline learns that the card was unlocked
    print(summary_line(res))
    return {"ok": 0, "degraded": 1}.get(res["verdict"], 2)


def summary_line(res):
    s = f"gpu selfcheck: {res['verdict']}"
    if res["reasons"]:
        s += " (" + ", ".join(res["reasons"]) + ")"
    if res.get("ratio") is not None:
        s += f"; fp32-acc/fp16-acc ratio {res['ratio']:.2f} (stock about 0.5, unlocked about 1.0)"
    elif res.get("tflops"):
        s += f"; {res['tflops']['fp16_fp32acc']} TFLOPS fp16/fp32acc"
    eff = res.get("efficiency")
    if eff:
        net = eff.get("tflops_fp16_fp32acc_per_w_net18")
        s += f"; {eff['tflops_fp16_fp32acc_per_w_gross']} TFLOPS/W gross" + (f", {net} net18" if net is not None else "") + f" at {eff['busy_draw_w']:.0f} W"
    if res["verdict"] == "degraded":
        if res.get("extra_cost_pct"):
            s += f"; jobs take about {res['extra_cost_pct']}% longer and cost about as much more energy ({res['extra_cost_basis']})"
        else:
            s += "; fp16/TF32-heavy jobs (image and video generation) run slower and cost more energy per job"
    return s


# ------------------------------------------------------------------------------------------------------------------ pending
def pending_reason(last, facts, now):
    """Why a check is due now, or None."""
    if last is None:
        return "first"
    if last.get("boot_id") != facts["boot_id"]:
        return "boot"
    if last.get("fingerprint") != facts["fingerprint"]:
        return "changed"
    if now - (last.get("at") or 0) > STALE_S:
        return "stale"
    if last.get("verdict") == "error" and now - (last.get("at") or 0) > RETRY_ERROR_S:
        return "retry_error"
    return None


def make_ctx(deps=None, env=None):
    deps = deps or {}
    env = env if env is not None else load_env()
    host = deps.get("host") or Host()
    ctx = {"host": host, "smi": deps.get("smi") or Smi(host), "env": env, "state_dir": deps.get("state_dir") or state_dir_of(env),
           "sleep": deps.get("sleep") or host.sleep, "now": deps.get("now") or host.now, "gate": deps.get("gate"),
           "probe": deps.get("probe", PROBE)}
    return ctx


def use_gate_for(ctx, no_gate):
    """(use_gate, setup_error): (False, None) with --no-gate; (True, None) when the gate is wanted and both tokens are there; (None, (reason,
    line)) when a token is missing: GATE_TOKEN reads GET /state, GATE_BENCH_TOKEN opens /bench/* (a different value, never the stacks' token)."""
    if no_gate:
        return False, None
    if ctx.get("gate"):
        return True, None
    env = ctx["env"]
    if not env.get("GATE_TOKEN"):
        return None, ("no_gate_token", "no GATE_TOKEN in host.env or the environment: the check cannot read the gate's state (run --no-gate --force measures at the "
                                       "current power limit without the gate)")
    if not env.get("GATE_BENCH_TOKEN"):
        return None, ("no_bench_token", "no GATE_BENCH_TOKEN in host.env or the environment: the check measures inside the gate's bench mode and refuses "
                                        "to run without it (set the same value the gate has, different from GATE_TOKEN; run --no-gate --force measures at the current "
                                        "power limit without the gate)")
    if env["GATE_BENCH_TOKEN"] == env["GATE_TOKEN"]:
        return None, ("no_bench_token", "GATE_BENCH_TOKEN equals GATE_TOKEN: the gate keeps bench mode off then; give it its own value")
    ctx["gate"] = make_gate(env)
    return True, None


def execute(ctx, idle_s, no_gate):
    """Gather, check, persist. Exit code: 0 ok, 1 degraded, 2 error, 75 skipped, 78 setup error."""
    ctx["facts"] = facts = gather(ctx["host"], ctx["smi"], ctx["env"], ctx["state_dir"])
    base = {"at": int(ctx["now"]()), "boot_id": facts["boot_id"], "fingerprint": facts["fingerprint"], "driver": facts["gpu"]["driver"],
            "unlock_expected": facts["unlock"]["expected"], "gpu": facts["gpu"], "unlock": facts["unlock"], "reasons": [], "method": "none",
            "ratio": None, "ratio_tf32": None, "tflops": None, "extra_cost_pct": None, "schema": 1}
    if not facts["smi_ok"]:
        return finish(ctx, dict(base, verdict="error", reasons=["no_gpu"]))
    if not facts["unlock"]["expected"] or not HALF_RATE_GPU.search(facts["gpu"]["name"] or ""):
        why = "unlock not expected on this host" if not facts["unlock"]["expected"] else "not a GeForce RTX 30 card: nothing to judge"
        res = dict(base, verdict="ok", note=why)
        finish(ctx, res)
        print(why)
        return 0
    use_gate, problem = use_gate_for(ctx, no_gate)
    if use_gate is None:
        return setup_failed(ctx, base, *problem)
    try:
        res = check_once(ctx, idle_s, use_gate)
    except Skipped as s:
        print(f"gpu selfcheck skipped: {s.why}")
        return EXIT_SKIPPED
    except SetupError as e:
        return setup_failed(ctx, base, e.reason, e.msg)
    return finish(ctx, res)


def setup_failed(ctx, base, reason, msg):
    """A host that is not set up must not stay silent: one clear line, an error result the gate and the ops bot show, exit 78."""
    print("gpu_selfcheck: " + msg, file=sys.stderr)
    finish(ctx, dict(base, verdict="error", reasons=[reason]))
    return EXIT_CONFIG


def cmd_status(ctx):
    sd = ctx["state_dir"]
    last = read_json(os.path.join(sd, "selfcheck.json"))
    facts = gather(ctx["host"], ctx["smi"], ctx["env"], sd)
    if not last:
        print("no selfcheck result yet; due: first")
        return 0
    print(summary_line(last))
    age_h = (ctx["now"]() - (last.get("at") or 0)) / 3600
    print(f"last run {age_h:.1f} h ago, driver {last.get('driver')}, kernel {last.get('fingerprint', {}).get('kernel')}")
    due = pending_reason(last, facts, ctx["now"]())
    print("due: " + due if due else "not due")
    return 0


def main(argv=None, deps=None):
    ap = argparse.ArgumentParser(description="Does this GPU still perform as unlocked?")
    ap.add_argument("mode", choices=["auto", "run", "status"])
    ap.add_argument("--force", action="store_true", help="run: check even if nothing changed")
    ap.add_argument("--no-gate", action="store_true", help="run at the current power limit without the gate's bench; the card must still be free; "
                    "needs --force: no lease check, no cap control, a wake during the probe is not refused")
    ap.add_argument("--accept-baseline", action="store_true",
                    help="run: with a torch that cannot do FP16 accumulation, take this run's TFLOPS as the reference (the card must be known to be unlocked now)")
    ap.add_argument("--idle-s", type=float, default=None, help="require the card idle this long first (auto: GPU_SELFCHECK_IDLE_S or 60)")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])
    ctx = make_ctx(deps)
    ctx["accept_baseline"] = bool(args.accept_baseline)

    def bye(*_):
        raise KeyboardInterrupt                               # run_probe removes the container, then the finally in check_once ends the bench

    if not (deps or {}).get("no_signals"):
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, bye)
    if args.mode == "status":
        return cmd_status(ctx)
    if args.mode == "auto":
        ctx["facts"] = facts = gather(ctx["host"], ctx["smi"], ctx["env"], ctx["state_dir"])
        last = read_json(os.path.join(ctx["state_dir"], "selfcheck.json"))
        due = pending_reason(last, facts, ctx["now"]())
        if not due:
            return 0
        log(f"gpu selfcheck due ({due})")
        idle = args.idle_s if args.idle_s is not None else float(ctx["env"].get("GPU_SELFCHECK_IDLE_S") or IDLE_S_AUTO)
        code = execute(ctx, idle, False)
        return 0 if code in (0, 1, 2, EXIT_SKIPPED) else code     # the timer unit must not fail on a verdict or a skip; a setup error (78) it shows
    idle = args.idle_s if args.idle_s is not None else 0
    if args.no_gate and not args.force:
        print("gpu_selfcheck: --no-gate needs --force: it skips the bench token, the gate's lease check and the power cap control, so the only guard "
              "is the nvidia-smi read of the card; a gate wake during the probe is not refused", file=sys.stderr)
        return EXIT_USAGE
    if args.no_gate:
        print("gpu_selfcheck: WARNING --no-gate: measuring at the current power limit with no bench lock; the gate is not asked and does not know", file=sys.stderr)
    if not args.force:
        last = read_json(os.path.join(ctx["state_dir"], "selfcheck.json"))
        facts = gather(ctx["host"], ctx["smi"], ctx["env"], ctx["state_dir"])
        if pending_reason(last, facts, ctx["now"]()) is None:
            print("nothing changed since the last check; it is not repeated (--force to run anyway)")
            print(summary_line(last))
            return {"ok": 0, "degraded": 1}.get(last.get("verdict"), 2)
    return execute(ctx, idle, args.no_gate)


if __name__ == "__main__":
    sys.exit(main())
