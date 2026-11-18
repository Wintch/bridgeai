#!/usr/bin/env python3
"""
bench_gate -- measure the GPU power profile of every task that goes through the gate, on the GPU host (stdlib only).

  python3 bench_gate.py [--tasks stt,tts-hq,resolve,effectcraft] [--recheck] [--dry-run] [--caps 100,130,...] [--reps N]

Why: a power limit in power_profiles.conf and a VRAM need in gate.py are only worth something when they are measured (the rule
of this repo: never guess). This script takes the card for one exclusive window through the gate's bench mode, runs each task
for each watt cap in turn (never two things at once), and prints the cap to use and the VRAM to reserve. It never edits
power_profiles.conf or gate.py: it prints the lines to paste.

Order, always sequential:
  1. Pre-flight (read only): GET /state shows no bench, nothing blocked, no service running and no lease; nvidia-smi shows only
     the small desktop processes (chrome, sunshine, ...) on the card. Anything else: exit with the reason, change nothing.
  2. POST /bench/start. From here the gate refuses every other wake with "bench" and leaves the power limit to this script.
  3. Per task: wake the service through the gate with the bench id (batch lease), wait for its /healthz, one measured warm-up
     job, then for each cap POST /bench/watts and N timed jobs. Every job runs under the same recorder as the video benchmarks
     (videobench/measure.py): wall s, GPU power draw, Wh, VRAM, utilisation. Then /done and /release (the service stops).
  4. POST /bench/end in a finally block (also on Ctrl-C, SIGTERM or SIGHUP: a dropped SSH session still ends the bench), then
     check that power.limit is what it was before. Run it under nohup or tmux anyway.
  Before every cap and every job it reads GET /state: if the gate is "blocked" (a person's session appeared) or the bench is gone,
  it stops cleanly, ends the bench if it is still ours and says which task and cap were interrupted.

Tasks (default first four; the five after them only with --recheck, they re-verify profiles that already exist):
  stt         ~3 min Spanish clip made here with the local Piper tts (public text, never a person's audio), POST /transcribe
  tts-hq      three public-domain paragraphs (es, en, ru), POST /v1/audio/speech
  resolve     the real MCP path: gpu-host/mcp_dispatch.sh as a stdio child (RESOLVE_GATE_STACK=bench, RESOLVE_GATE_BENCH=<id> so
              the session's /wake carries the bench id), a throwaway project, a synthetic 60 s 1080p24 clip, H.264 Master render.
              One fresh Resolve session per job (cold start, idle VRAM and render peak are recorded each time)
  effectcraft effectcraft-cli renders a 5 s 720p text comp on the CPU: expect ~0 VRAM. CPU core-s recorded. No sweep, no lease.
              --effectcraft-gpu-eval also runs `effectcraft-cli bench --gpu --json` once: "evaluation, EffectCraft stays CPU-only
              in production". It runs only inside this run's active bench (which reserves the whole card) and records VRAM and W
  upscaler, transcoder, vidpost, imggen, vidgen (--recheck)

Every timed job also reads the power limit back (start and end) and records temperature, SM clock, throttle reasons, encoder sessions,
CPU governor and EPP, driver, kernel and the gpu-unlock value; a job is marked invalid (never pooled) when the card is not idle
before it (GPU use > 5 %, encoder sessions), a foreign compute app is on the card, the limit is not the one asked, or it throttled
on hardware or heat. gpu_wh is gross and the headline; gpu_net18_wh = gross - 18 W x s; gpu_net_wh = gross - the job's own idle W x s.
imggen and vidgen (ComfyUI with --cache-classic): a new (prompt, seed) from fixed tables for every job, 8 hex of the output's sha256
stored, and a canary (an identical repeat more than 3x faster than the first warm job aborts the task as cache-tainted). Their
"need + 15 %" VRAM figure is informative only (dynamic VRAM), as is vidpost's.
/bench/* takes only GATE_BENCH_TOKEN (host.env), never GATE_TOKEN.

Results: one JSON line per cap (and per task and recommendation) appended to ~/bench_gate/results.jsonl (BENCH_GATE_HOME
moves it). Recommendation per task: the cap with the lowest Wh per job; a higher cap wins only when it costs at most +10 % Wh
and is at least 15 % faster. Differences under 2 % in Wh count as equal (the lower cap is taken). VRAM need = measured peak
above the card's use before the task + 15 %.

The gate token is read from gpu-host/host.env (GATE_TOKEN; KEY=VALUE lines, never sourced), the token of /bench/* from the same
file (GATE_BENCH_TOKEN, a different value: the gate refuses /bench/* without it and never accepts GATE_TOKEN there), the service tokens from the same
file (IMAGE_TOKEN, VIDEO_TOKEN, VIDPOST_TOKEN, UPSCALE_TOKEN, TRANSCODE_TOKEN). Nothing is printed or stored from them.
Own files live in ~/bench_gate/tmp and ~/Videos/zz_bench and are removed at the end (--keep-tmp keeps them).
gpu-unlock (/sys/module/gpu_unlock/parameters/targets, absent = "off") is printed in the pre-flight and stored on every result
line; the imggen and vidgen profiles assume it is on, so the summary warns when it is off.
Exit: 0 ok, 1 a task failed or the run was interrupted, 2 pre-flight refused, 3 bench start failed, 4 power limit not back.
"""
import argparse
import glob
import hashlib
import importlib.util
import io
import json
import math
import os
import queue
import re
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SHORT_CAPS = [100, 130, 160, 200, 240]
LONG_CAPS = [100, 130, 170, 240]
WH_SLACK = 0.10          # a faster cap may cost up to +10 % Wh ...
SPEED_GAIN = 0.15        # ... when it is at least 15 % faster
WH_TIE = 0.02            # Wh within 2 % of the best count as equal: the lower cap wins
VRAM_MARGIN = 1.15
EFFECTCRAFT_VRAM_ZERO_MIB = 100
ALLOWED_APPS = r"chrom|sunshine|Xorg|Xwayland|gnome-shell|kwin|plasmashell|firefox|steamwebhelper"
ALLOWED_APP_MAX_MIB = 400
DEFAULT_ENV_FILES = ["/mnt/resolve_test/bridgeai/gpu-host/host.env"]
EFFECTCRAFT_CLI = "/mnt/resolve_test/tools/artcraft/effectcraft/current/bin/effectcraft-cli"
GPU_UNLOCK_TARGETS = "/sys/module/gpu_unlock/parameters/targets"
BENCH_START_TIMEOUT = 60  # s: /bench/start sets the power limit and may be slow
START_RECOVER_S = 120     # a bench this young, seen after a failed /bench/start, is ours
EVAL_LABEL = "evaluation, EffectCraft stays CPU-only in production"
THROTTLE_FIELDS = ("clocks_event_reasons.active", "clocks_throttle_reasons.active")
SETTLE_S = 4.0            # s: the card settles after a cap change or the previous job before the idle sample (3-5 s)
IDLE_UTIL_MAX = 5.0       # % GPU use at idle above which a job is invalid (the runbook allows 5-8 %)
NET_IDLE_W = 18.0         # the repo's convention for "net" energy: gross - 18 W x s (the card's own idle draw in P8 is ~20 W)
CAP_TOLERANCE_W = 1.0     # the limit read back may differ from the one asked by this much
THROTTLE_BAD = 0x8 | 0x20 | 0x40 | 0x80   # hw slowdown, sw thermal, hw thermal, power brake; 0x1 (idle) and 0x4 (the cap itself) are fine
NO_ENCODER_TASKS = {"stt", "tts-hq", "upscaler", "imggen"}   # an encoder session during one of these jobs is somebody else's (Sunshine)
CPU_FREQ_DIR = "/sys/devices/system/cpu/cpu0/cpufreq"
COMFY_TASKS = {"imggen", "vidgen"}   # the tasks with (prompt, seed) variants and so with the cache canary (2 extra jobs)
# services without a fixed model file list: the directory inside the container whose listing the environment snapshot digests
# (transcoder has no model: ffmpeg/NVENC only, so its image id is its whole environment)
MODEL_DIRS = {"stt": "/models", "tts-hq": "/models", "vidpost": "/models", "upscaler": "/app/weights"}
DYNAMIC_VRAM = {"imggen", "vidgen", "vidpost"}   # ComfyUI offloads dynamically: the measured peak is an upper bound, not a need
SAMPLE_PERIOD_S = 0.5     # the power sampler (nvidia-smi -lms 500)
SAMPLE_MIN_FRAC = 0.8     # a job with fewer power samples than this share of wall_s / SAMPLE_PERIOD_S has no trustworthy Wh
SAMPLE_MIN_WALL_S = 2.0   # below this wall time the share rule is not applied (only "no sample at all" is invalid)
# the services' IDLE_S as the runbook sets it for the bench: a ComfyUI worker that waits longer than this between two jobs exits, and the
# next job starts it again (cold)
SERVICE_IDLE_S = {"imggen": 60.0, "vidgen": 120.0, "vidpost": 15.0}
IDLE_GAP_WARN = 0.8       # warn when the gap between two jobs of one service is this share of its IDLE_S
CANARY_RATIO = 3.0        # a repeated identical ComfyUI job this many times faster than the first warm one: cache-tainted
# ComfyUI caches node outputs (imggen and vidgen run it with --cache-classic): a repeated (prompt, seed) re-runs only the save node.
# Every timed ComfyUI job therefore takes the next (prompt, seed) of these fixed tables (the same in every session). 5 prompts
# and 8 seeds are coprime, so no job repeats its predecessor and the whole table repeats only every 40 jobs. Prompts of one
# word count: the text encoder sees the same number of words each time.
SEEDS = [7, 1337, 4242, 90210, 31415, 271828, 161803, 8675309]
IMG_PROMPTS = ["a red bicycle leaning on a white wall, soft morning light",
               "a blue teapot resting on a wooden table, warm evening light",
               "a green kayak lying on a sandy beach, bright midday light",
               "a yellow lantern hanging by a stone door, dim night light",
               "a grey cat sitting on a mossy step, cold winter light"]
VID_PROMPTS = ["waves rolling onto an empty beach at sunrise", "rain falling on a quiet forest at dusk",
               "smoke rising from a small cabin at dawn", "leaves swirling across an empty street at noon",
               "boats rocking in a calm harbor at sunset"]
# the model files each ComfyUI task loads (names as in imggen/server.py and vidgen/server.py): the environment snapshot records their size
MODEL_FILES = {
    "imggen": {"fast": ["sdxl_lightning_4step.safetensors"],
               "better": ["flux-2-klein-4b.safetensors", "qwen_3_4b_fp4_flux2.safetensors", "flux2-vae.safetensors"],
               "photo": ["z_image_turbo_bf16.safetensors", "qwen_3_4b_fp8_mixed.safetensors", "ae.safetensors"]},
    "vidgen": ["minimax_h3_fl2va_pruned_int8_convrot.safetensors", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
               "minimax_h3_video_vae_fp16.safetensors", "minimax_h3_audio_vae_fp32.safetensors",
               "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"],
}

DEFAULT_TASKS = ["stt", "tts-hq", "resolve", "effectcraft"]
RECHECK_TASKS = ["upscaler", "transcoder", "vidpost", "imggen", "vidgen"]
ORDER = DEFAULT_TASKS + RECHECK_TASKS
LONG_TASKS = {"resolve", "vidgen"}
DEFAULT_REPS = {"stt": 5, "tts-hq": 3, "resolve": 3, "effectcraft": 3, "upscaler": 5, "transcoder": 5, "vidpost": 3,
                "imggen": 5, "vidgen": 1}
# Rough time per task for --dry-run: (prepare s, ready s, s per job). Resolve: s per session (cold start + project + render + quit).
ESTIMATE = {"stt": (60, 15, 15), "tts-hq": (0, 40, 60), "resolve": (30, 0, 45), "effectcraft": (10, 0, 8),
            "upscaler": (10, 10, 3), "transcoder": (30, 5, 3), "vidpost": (15, 40, 40), "imggen": (0, 30, 6),
            "vidgen": (0, 360, 260)}      # vidgen s per job: the runbook measured 213-300 s for a 2 s H3 clip
SERVICE_TOKEN = {"imggen": "IMAGE_TOKEN", "vidgen": "VIDEO_TOKEN", "vidpost": "VIDPOST_TOKEN", "upscaler": "UPSCALE_TOKEN",
                 "transcoder": "TRANSCODE_TOKEN"}
TOKEN_REQUIRED = {"imggen", "vidgen", "vidpost"}

# Fixed public-domain texts (Cervantes, Austen, Tolstoy); never a person's words.
TEXT_ES = ("En un lugar de la Mancha, de cuyo nombre no quiero acordarme, no ha mucho tiempo que vivía un hidalgo de los de "
           "lanza en astillero, adarga antigua, rocín flaco y galgo corredor. Una olla de algo más vaca que carnero, "
           "salpicón las más noches, duelos y quebrantos los sábados, lentejas los viernes, algún palomino de añadidura "
           "los domingos, consumían las tres partes de su hacienda.")
TEXT_EN = ("It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a "
           "wife. However little known the feelings or views of such a man may be on his first entering a neighbourhood, "
           "this truth is so well fixed in the minds of the surrounding families, that he is considered the rightful "
           "property of some one or other of their daughters.")
TEXT_RU = ("Все счастливые семьи похожи друг на друга, каждая несчастливая семья несчастлива по-своему. Все смешалось в "
           "доме Облонских. Жена узнала, что муж был в связи с бывшею в их доме француженкою-гувернанткой, и объявила "
           "мужу, что не может жить с ним в одном доме.")
# Extra Spanish paragraphs (written for this script) so the stt clip is varied.
STT_PARAGRAPHS = [
    TEXT_ES,
    "La mañana empezó con una lluvia fina que mojaba las calles del barrio. Los vecinos abrían los paraguas, los comercios "
    "levantaban las persianas y el autobús llegaba con unos minutos de retraso, como casi todos los lunes del invierno.",
    "Para preparar la receta hace falta medio kilo de harina, dos huevos, una pizca de sal y un vaso de leche tibia. Se "
    "mezcla todo hasta que no queden grumos, se deja reposar media hora y después se cocina en una sartén bien caliente.",
    "El informe de la reunión resume tres puntos. Primero, el calendario de trabajo se mantiene sin cambios. Segundo, la "
    "compra de materiales se hará la semana próxima. Tercero, cada equipo enviará su avance por escrito el viernes.",
    "Cuando llegamos a la montaña el aire era frío y limpio. Caminamos por un sendero de piedras hasta un mirador desde "
    "donde se veía todo el valle, el río y las casas pequeñas entre los árboles.",
    "La biblioteca del pueblo abre de martes a sábado. Quien quiera sacar un libro solo necesita su documento y unos "
    "minutos para completar la ficha. Los niños tienen una sala propia con cuentos, juegos de mesa y un rincón de dibujo.",
]


def log(msg):
    try:
        print(time.strftime("%H:%M:%S ") + msg, flush=True)
    except (OSError, ValueError):   # the terminal is gone (SIGHUP): the clean-up must go on
        pass


def read_gpu_unlock(path=GPU_UNLOCK_TARGETS):
    """The gpu-unlock module's targets, or "off" when the module is not loaded (file absent) or the value is empty."""
    try:
        val = open(path, encoding="utf-8", errors="replace").read().strip()
    except OSError:
        return "off"
    return val[:60] or "off"


class TaskError(Exception):
    """One task cannot go on (service refused, job failed): the bench records it and moves to the next task."""


class GateError(Exception):
    pass


class Interrupted(Exception):
    """The run must stop now (a person's session appeared, the bench is gone): not a task failure, no further task starts."""

    def __init__(self, task, what, reason):
        self.task, self.what, self.reason = task, what, reason
        super().__init__(f"interrupted in task {task} at {what}: {reason}")


def parse_env_file(path):
    """KEY=VALUE lines, never sourced: the same parse as gate/gate.py."""
    out = {}
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        k, sep, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
            continue
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k] = v
    return out


def load_host_env(environ=None):
    env = os.environ if environ is None else environ
    paths = [env["GATE_ENV_FILE"]] if env.get("GATE_ENV_FILE") else [os.path.join(HERE, "host.env")] + DEFAULT_ENV_FILES
    vals = {}
    for p in reversed(paths):                    # the first file that has a key wins
        vals.update(parse_env_file(p))
    vals.update({k: v for k, v in env.items() if k.startswith("GATE_") or k in SERVICE_TOKEN.values()})
    return vals


# ---------------------------------------------------------------------------------------------------------------- gate client
class Gate:
    """The gate client. /bench/* takes only GATE_BENCH_TOKEN (the stacks' GATE_TOKEN is refused there, and this client never sends it
    there); everything else takes GATE_TOKEN."""

    def __init__(self, base, token, timeout=20, bench_token=None):
        self.base, self.token, self.timeout, self.bench_token = base.rstrip("/"), token, timeout, bench_token

    def call(self, method, path, body=None, timeout=None):
        data = json.dumps(body).encode() if body is not None else None
        tok = self.token
        if path.startswith("/bench/"):
            if not self.bench_token:
                raise GateError("no GATE_BENCH_TOKEN: /bench/* is never called with the stacks' token")
            tok = self.bench_token
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                code, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
        except (OSError, ValueError) as e:
            raise GateError(f"gate unreachable ({type(e).__name__})")
        try:
            obj = json.loads(raw) if raw else {}
        except ValueError:
            obj = {}
        return code, obj if isinstance(obj, dict) else {}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _hex(x):
    try:
        return int(str(x).strip(), 16)
    except (TypeError, ValueError):
        return None


class Nvidia:
    """nvidia-smi reads. Writing the power limit is the gate's job, never this script's."""

    throttle_field = None      # "clocks_event_reasons.active" (driver 595) or "clocks_throttle_reasons.active": found on the first read

    def _query(self, args):
        r = subprocess.run(["nvidia-smi"] + args + ["--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=30)
        return r.stdout.strip().splitlines() if r.returncode == 0 else []

    def limit_w(self):
        rows = self._query(["--query-gpu=power.limit"])
        return float(rows[0]) if rows else None

    def mem_used_mib(self):
        rows = self._query(["--query-gpu=memory.used"])
        return float(rows[0]) if rows else 0.0

    def compute_apps(self):
        return self._query(["--query-compute-apps=pid,process_name,used_memory"])

    def driver(self):
        rows = self._query(["--query-gpu=driver_version"])
        return rows[0].strip() if rows else None

    def snapshot(self):
        """One instantaneous read of what a job's validity depends on: temperature, SM clock, power limit, GPU use, throttle reasons
        (int bitmask), encoder sessions. A value the driver does not give is None."""
        out = dict.fromkeys(("temp_c", "sm_mhz", "limit_w", "util", "throttle", "enc_sessions"))
        rows = self._query(["--query-gpu=temperature.gpu,clocks.sm,power.limit,utilization.gpu"])
        if rows:
            f = [x.strip() for x in rows[0].split(",")] + [None] * 4
            out.update(temp_c=_f(f[0]), sm_mhz=_f(f[1]), limit_w=_f(f[2]), util=_f(f[3]))
        for fld in ([Nvidia.throttle_field] if Nvidia.throttle_field else THROTTLE_FIELDS):   # the field was renamed in newer drivers
            rows = self._query([f"--query-gpu={fld}"])
            if rows:
                Nvidia.throttle_field = fld
                out["throttle"] = _hex(rows[0].strip())
                break
        rows = self._query(["--query-gpu=encoder.stats.sessionCount"])    # asked alone: a driver without it must not cost the rest
        if rows:
            out["enc_sessions"] = _f(rows[0].strip())
        return out


# ------------------------------------------------------------------------------------------------------------------ recorder
def load_measure():
    spec = importlib.util.spec_from_file_location("vb_measure", os.path.join(HERE, "videobench", "measure.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def job_sampler(stop, rows):
    """Every second while a job runs: (time, temperature, SM clock, throttle bitmask, power limit, encoder sessions). Best effort:
    a driver that rejects a field gives no rows and the job simply carries no such fields."""
    fld = Nvidia.throttle_field or THROTTLE_FIELDS[0]
    try:
        p = subprocess.Popen(["nvidia-smi", f"--query-gpu=temperature.gpu,clocks.sm,{fld},power.limit,encoder.stats.sessionCount",
                              "--format=csv,noheader,nounits", "-lms", "1000"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return
    for line in p.stdout:
        f = [x.strip() for x in line.split(",")] + [None] * 5
        rows.append((time.time(), _f(f[0]), _f(f[1]), _hex(f[2]), _f(f[3]), _f(f[4])))
        if stop.is_set():
            break
    p.terminate()


def fold_samples(rows):
    """The per-job fields from job_sampler's rows: peak temperature, median SM clock, the throttle reasons seen (OR of the
    bitmasks), the most encoder sessions, and the lowest and highest power limit during the job."""
    out = {}
    col = lambda i: [r[i] for r in rows if r[i] is not None]
    if col(1):
        out["temp_peak_c"] = max(col(1))
    if col(2):
        out["sm_mhz_med"] = statistics.median(col(2))
    if col(3):
        thr = 0
        for v in col(3):
            thr |= v
        out["throttle_or"] = f"0x{thr:x}"
    if col(5):
        out["enc_sessions_max"] = int(max(col(5)))
    if col(4):
        out["limit_w_min"], out["limit_w_max"] = min(col(4)), max(col(4))
    return out


def cpu_policy(cpu_dir=CPU_FREQ_DIR):
    """CPU frequency governor and energy-performance preference of cpu0, "?" when the file is not there."""
    def rd(name):
        try:
            return open(os.path.join(cpu_dir, name), encoding="utf-8", errors="replace").read().strip()[:40] or "?"
        except OSError:
            return "?"
    return {"governor": rd("scaling_governor"), "epp": rd("energy_performance_preference")}


def pids_of(lines):
    """{pid: process_name} from nvidia-smi --query-compute-apps lines; unreadable lines are left out."""
    out = {}
    for ln in lines:
        try:
            pid, rest = ln.split(",", 1)
            name, _mem = rest.rsplit(",", 1)
            out[pid.strip()] = name.strip()
        except ValueError:
            continue
    return out


def foreign_apps(lines, known, allow=ALLOWED_APPS):
    """Compute apps on the card that are neither known (the desktop ones seen before the bench, the bench's own service seen after
    its start) nor a small desktop app by name: somebody else's job. Names are the program's own, never a command line."""
    return sorted(f"{exe_basename(name) or '?'}({pid})" for pid, name in pids_of(lines).items()
                  if pid not in known and not re.search(allow, exe_basename(name), re.I))


def judge_job(m, task, cap_w, pre, post, foreign):
    """Reasons a job is invalid (an empty list = valid): GPU use at idle, encoder sessions (Sunshine) at idle or, for a task that does
    not encode, during the job, a foreign compute app, too few power samples for the job's length, a power limit that is not the one asked for or moved during the job, a hardware or
    thermal throttle. A value that could not be read never makes a job invalid. A failed job is reported as failed, not as invalid."""
    why = []
    if not m.get("ok", True):
        return why
    if (pre.get("util") or 0) > IDLE_UTIL_MAX:
        why.append(f"GPU use at idle {pre['util']:.0f} %")
    if (pre.get("enc_sessions") or 0) > 0:
        why.append(f"{pre['enc_sessions']:.0f} encoder session(s) at idle")
    elif task in NO_ENCODER_TASKS and (m.get("enc_sessions_max") or 0) > 0:
        why.append(f"{m['enc_sessions_max']} encoder session(s) during the job")
    if foreign:
        why.append("foreign compute app " + ",".join(foreign[:3]))
    n_samples = m.get("samples")
    if n_samples is not None:
        wall = m.get("wall_s") or 0.0
        if n_samples == 0 or (wall >= SAMPLE_MIN_WALL_S and n_samples < SAMPLE_MIN_FRAC * wall / SAMPLE_PERIOD_S):
            why.append(f"power sampler gave {n_samples} sample(s) in {wall:.1f} s: the Wh cannot be trusted")
    if cap_w is not None:
        for label, v in (("start", pre.get("limit_w")), ("end", post.get("limit_w"))):
            if v is not None and abs(v - cap_w) > CAP_TOLERANCE_W:
                why.append(f"power limit {v:.0f} W at {label}, asked {cap_w:.0f} W")
    lo, hi = m.get("limit_w_min"), m.get("limit_w_max")
    if lo is not None and hi is not None and hi - lo > 0.5:
        why.append(f"power limit moved during the job ({lo:.0f}-{hi:.0f} W)")
    thr = _hex(m.get("throttle_or")) if m.get("throttle_or") else None
    if thr is not None and thr & THROTTLE_BAD:
        why.append(f"throttle 0x{thr & THROTTLE_BAD:x}")
    return why


def real_measure(tag, fn, unit="job"):
    """Run fn() under the video benchmarks' recorder (videobench/measure.py sampling helpers, same fields and same Wh sum).
    A failing fn gives ok=False and err; Ctrl-C stops the sampler and goes up. A number returned by fn is the output size
    of that job (audio minutes, seconds, images) and is kept as "ret"."""
    m = load_measure()
    idle_rows, stop0 = [], threading.Event()
    th = threading.Thread(target=m.gpu_sampler, args=(stop0, idle_rows), daemon=True)
    th.start()
    time.sleep(2.2)
    stop0.set()
    th.join(3)
    idle_w = statistics.median(r[1] for r in idle_rows) if idle_rows else 0.0
    base_ram = m.ram_used_gb()
    rows, stop = [], threading.Event()
    th = threading.Thread(target=m.gpu_sampler, args=(stop, rows), daemon=True)
    th.start()
    xrows = []
    xth = threading.Thread(target=job_sampler, args=(stop, xrows), daemon=True)
    xth.start()
    ram = {"peak": base_ram}

    def ram_watch():
        while not stop.is_set():
            ram["peak"] = max(ram["peak"], m.ram_used_gb())
            time.sleep(0.5)

    rw = threading.Thread(target=ram_watch, daemon=True)
    rw.start()
    c0, t0 = m.cpu_busy(), time.time()
    ok, err, ret = True, None, None
    try:
        ret = fn()
    except Exception as e:
        ok, err = False, f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        t1, c1 = time.time(), m.cpu_busy()
        stop.set()
        th.join(3)
        xth.join(3)
        rw.join(2)
    dur = t1 - t0
    run = [r for r in rows if t0 <= r[0] <= t1] or rows
    wh = 0.0
    pts = [(t0, run[0][1])] + [r[:2] for r in run] + [(t1, run[-1][1])] if run else []
    for (ta, wa), (tb, wb) in zip(pts, pts[1:]):
        wh += (wa + wb) / 2 * (tb - ta) / 3600
    res = {
        "tag": tag, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "ok": ok, "err": err, "wall_s": round(dur, 2),
        "gpu_idle_w": round(idle_w, 1),
        "gpu_avg_w": round(statistics.mean(r[1] for r in run), 1) if run else None,
        "gpu_peak_w": round(max(r[1] for r in run), 1) if run else None,
        # gpu_wh is gross (the headline). gpu_net_wh: gross minus THIS job's measured idle draw x s. gpu_net18_wh: gross minus the
        # repo's convention of 18 W x s. Whoever says "net" says which one.
        "gpu_wh": round(wh, 4), "gpu_net_wh": round(max(0.0, wh - idle_w * dur / 3600), 4),
        "gpu_net18_wh": round(max(0.0, wh - NET_IDLE_W * dur / 3600), 4),
        "vram_peak_mib": int(max(r[2] for r in run)) if run else None,
        "gpu_util_avg": round(statistics.mean(r[3] for r in run), 1) if run else None,
        "ram_delta_gb": round(ram["peak"] - base_ram, 2), "cpu_busy_core_s": round(c1 - c0, 1), "samples": len(run),
    }
    if isinstance(ret, (int, float)) and not isinstance(ret, bool) and ret > 0:
        res["ret"] = float(ret)
    res.update(fold_samples([r for r in xrows if t0 - 1 <= r[0] <= t1 + 1]))
    return res


# ----------------------------------------------------------------------------------------------------------- pure arithmetic
def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 4) if xs else None


WH_KEYS = {"gpu_wh": "wh", "gpu_net_wh": "net_wh", "gpu_net18_wh": "net18_wh"}

# Output efficiency: what one Wh buys in the units a person asks for (frames, images, megapixels, audio seconds, tokens), per task.
# (output unit, "<units> per Wh" name, "Wh per <unit>" name or None). A job's output size is its `ret` (the number the job function
# returns) times the task's per-ret factor in JobSpec.outputs. Gross = the Wh as measured; net18 = gross - 18 W x s (the repo's
# convention). Every field name ends in _gross or _net18 in a row: whoever quotes one says which.
EFFICIENCY = {
    "vidgen": [("frames", "frames_per_wh", "wh_per_frame")],
    "imggen": [("images", "images_per_wh", None), ("megapixels", None, "wh_per_megapixel")],
    "stt": [("audio_seconds", "audio_seconds_per_wh", None)],
    "tts-hq": [("audio_seconds_out", "audio_seconds_out_per_wh", None)],
    "upscaler": [("megapixels_out", "megapixels_out_per_wh", None)],
    "transcoder": [("frames", "frames_per_wh", None)],
    "vidpost": [("frames_out", "frames_out_per_wh", None)],
    "llm": [("tokens", "tokens_per_wh", None)],        # no llm task yet: a job that returns its token count gets the same rows
}
VIDGEN_FPS = 24.0          # vidgen/server.py FPS
SRC_FPS = 24               # the synthetic sources of Media.video()
TRANSCODER_SECS = 60       # Media.video("hd60"): 60 s 1080p24, same frame count out (720p h264)
VIDPOST_SECS = 5           # Media.video("sd5"): 5 s 24 fps in; scale=2&fps=2: RIFE makes 2n-1 frames from n (vidpost/server.py plan())
UPSCALE_FACTOR = 4         # upscaler/server.py outscale=4
UPSCALE_IN = (640, 360)    # Media.png()


def vidgen_frames(secs):
    """Frames vidgen makes for a clip of `secs` seconds: vidgen/server.py frames() (24 fps snapped up to the model's 17k+5 grid:
    2 s -> 56, 5 s -> 124, 10 s -> 243), not the nominal secs x fps."""
    n = max(5, round(secs * VIDGEN_FPS))
    return n + (5 - n % 17) % 17


def size_mpx(size):
    """Megapixels of a "WxH" string; None when it does not parse."""
    m = re.fullmatch(r"(\d{2,5})x(\d{2,5})", str(size))
    return int(m.group(1)) * int(m.group(2)) / 1e6 if m else None


def efficiency(task, runs, outputs):
    """The per-output efficiency of the valid jobs of one cap row: {"units_per_job": {unit: median}, "gross": {name: median of the per-job
    ratios}, "net18": {...}}, or None when the task has no output units, `outputs` (unit -> units per `ret`) is missing, or a job has no
    `ret`. A ratio whose Wh is zero (net18 can be, when a job drew less than 18 W) is None for the row, never a division by zero."""
    spec = EFFICIENCY.get(task)
    if not spec or not outputs or not runs or not all(r.get("ret") for r in runs):
        return None
    out = {"units_per_job": {}, "gross": {}, "net18": {}}
    for unit, per_wh, wh_per in spec:
        k = outputs.get(unit)
        if not k:
            continue
        units = [r["ret"] * k for r in runs]
        out["units_per_job"][unit] = round(statistics.median(units), 6)
        for key, label in (("gpu_wh", "gross"), ("gpu_net18_wh", "net18")):
            wh = [r.get(key) for r in runs]
            ok = all(isinstance(w, (int, float)) and w > 0 for w in wh)
            if per_wh:
                out[label][per_wh] = round(statistics.median(u / w for u, w in zip(units, wh)), 4) if ok else None
            if wh_per:
                out[label][wh_per] = round(statistics.median(w / u for u, w in zip(units, wh)), 6) if ok else None
    return out


def efficiency_text(po):
    """One line for a row's per_output: units per job, then the gross and net18 figures, each labelled."""
    if not po or not po.get("units_per_job"):
        return ""
    units = ", ".join(f"{v:g} {u}" for u, v in po["units_per_job"].items())
    parts = []
    for label in ("gross", "net18"):
        figs = ", ".join(f"{n} {'-' if v is None else format(v, 'g')}" for n, v in po.get(label, {}).items())
        if figs:
            parts.append(f"{label}: {figs}")
    return f"{units} per job; " + "; ".join(parts)


def min_valid_jobs(n):
    """Valid jobs a row needs to take part in the recommendation: at least half of the jobs, never fewer than 2 (a single job when
    the set has only one). Invalid jobs are the hot or disturbed ones, so one survivor is the coolest sample, not a median."""
    return min(n, max(2, math.ceil(n / 2)))


def summarise(cap, runs, wh_key="gpu_wh", unit=None, task=None, outputs=None):
    """One row per cap from the timed runs. rec_wh / rec_s are what the recommendation compares: per unit of output when every
    run reports one (the output length of a speech job varies), else per job. A job marked invalid (see judge_job) never takes part:
    it is counted in n_invalid and its reasons are listed, nothing is pooled with it. Wh: wh is gross (the headline), net_wh is gross minus
    the job's own measured idle draw, net18_wh is gross minus 18 W x s."""
    oks = [r for r in runs if r.get("ok", True)]
    good = [r for r in oks if not r.get("invalid_why")]
    bad = [r for r in oks if r.get("invalid_why")]
    row = {"cap_w": cap, "n": len(runs), "n_ok": len(good), "n_invalid": len(bad)}
    if good and len(good) < min_valid_jobs(len(runs)):
        row["thin"] = True
    if bad:
        row["invalid_why"] = sorted({w for r in bad for w in r["invalid_why"]})[:4]
    if not good:
        row["errors"] = sorted({r.get("err") or "failed" for r in runs if not r.get("ok", True)} | {"invalid: " + w for w in row.get("invalid_why", [])})[:3]
        return row
    oks = good
    peaks = [r["gpu_peak_w"] for r in oks if r.get("gpu_peak_w") is not None]
    avgs = [r["gpu_avg_w"] for r in oks if r.get("gpu_avg_w") is not None]
    vr = [r["vram_peak_mib"] for r in oks if r.get("vram_peak_mib") is not None]
    row.update({
        "wall_s": _med(r["wall_s"] for r in oks), "avg_w": round(statistics.mean(avgs), 1) if avgs else None,
        "peak_w": max(peaks) if peaks else None, "wh": _med(r["gpu_wh"] for r in oks),
        "net_wh": _med(r["gpu_net_wh"] for r in oks), "net18_wh": _med(r.get("gpu_net18_wh") for r in oks),
        "idle_w": _med(r.get("gpu_idle_w") for r in oks),
        "util": _med(r.get("gpu_util_avg") for r in oks), "vram_peak_mib": max(vr) if vr else None,
        "cpu_core_s": _med(r.get("cpu_busy_core_s") for r in oks),
    })
    rec_wh, rec_s = row[WH_KEYS.get(wh_key, "wh")], row["wall_s"]
    if unit and all(r.get("ret") for r in oks):
        row["unit"] = unit
        row["s_per_unit"] = round(statistics.median(r["wall_s"] / r["ret"] for r in oks), 5)
        for key, name in WH_KEYS.items():
            vals = [r[key] / r["ret"] for r in oks if r.get(key) is not None]
            row[name + "_per_unit"] = round(statistics.median(vals), 5) if len(vals) == len(oks) else None
        rec_wh, rec_s = row[WH_KEYS.get(wh_key, "wh") + "_per_unit"], row["s_per_unit"]
    row["rec_wh"], row["rec_s"] = rec_wh, rec_s
    po = efficiency(task, oks, outputs)
    if po:
        row["per_output"] = po
    return row


def recommend(rows):
    """(row, why) by the repo's rule: lowest Wh per job; a faster cap wins when it costs at most +10 % Wh and is at least 15 %
    faster. Rows without a successful run, thin rows (too few valid jobs, see min_valid_jobs) and rows whose limit was not confirmed
    do not take part."""
    ok = [r for r in rows if r.get("n_ok") and r.get("rec_wh") is not None and r.get("cap_ok", True) and not r.get("thin")]
    if not ok:
        if any(r.get("thin") for r in rows):
            return None, "no usable measurement (the rows with valid jobs are thin: too few valid jobs per cap)"
        return None, "no usable measurement"
    low = min(r["rec_wh"] for r in ok)
    best = min((r for r in ok if r["rec_wh"] <= low * (1 + WH_TIE)), key=lambda r: r["cap_w"])
    faster = [r for r in ok if r["rec_wh"] <= best["rec_wh"] * (1 + WH_SLACK) and r["rec_s"] <= best["rec_s"] * (1 - SPEED_GAIN)]
    if faster:
        pick = min(faster, key=lambda r: (r["rec_s"], r["cap_w"]))
        gain = 100 * (1 - pick["rec_s"] / best["rec_s"])
        extra = 100 * (pick["rec_wh"] / best["rec_wh"] - 1)
        return pick, f"{gain:.0f} % faster than {best['cap_w']} W (lowest Wh) for {extra:+.0f} % Wh"
    return best, "lowest Wh per job"


def vram_need_mb(peak_mib, baseline_mib):
    return int(math.ceil(max(0.0, peak_mib - baseline_mib) * VRAM_MARGIN / 10.0) * 10)


def exe_basename(name):
    """The program's own name from nvidia-smi's process_name, which is a whole command line: only its first word counts, so a path
    inside an argument (Chrome's --render-node-override=/dev/dri/renderD128) cannot become the name."""
    words = name.strip().split()
    return os.path.basename(words[0]) if words else ""


def check_compute_apps(lines, allow=ALLOWED_APPS, max_mib=ALLOWED_APP_MAX_MIB):
    """Reasons to refuse: compute apps on the card other than the small desktop ones."""
    bad = []
    for ln in lines:
        try:
            pid, rest = ln.split(",", 1)
            name, mem = rest.rsplit(",", 1)
            mem = float(mem)
        except ValueError:
            bad.append(f"unreadable nvidia-smi line: {ln[:60]}")
            continue
        base = exe_basename(name)
        if not re.search(allow, base, re.I) or mem > max_mib:
            bad.append(f"GPU process {base or '?'} (pid {pid.strip()}) uses {mem:.0f} MiB")
    return bad


def preflight(state, apps_lines, allow=ALLOWED_APPS):
    """Reasons the bench must not start; an empty list means go."""
    why = []
    if state.get("bench"):
        why.append("another bench is active on the gate")
    if state.get("blocked"):
        why.append(f"the gate is blocked ({state['blocked']}): a person is using the machine")
    for name, s in sorted((state.get("services") or {}).items()):
        if s.get("running") or s.get("leases"):
            why.append(f"service {name} is {'running' if s.get('running') else 'leased'} (leases {s.get('leases', 0)})")
    why += check_compute_apps(apps_lines, allow)
    return why


def fmt_cap_list(caps):
    return ",".join(str(c) for c in caps)


def clamp_caps(caps, lo, hi):
    out = []
    for c in caps:
        c = int(min(max(c, lo), hi)) if lo is not None and hi is not None else int(c)
        if c not in out:
            out.append(c)
    return out


def known_needs():
    """Current VRAM needs from gate.py's SERVICES, for the printout only; {} when gate.py cannot be loaded."""
    try:
        spec = importlib.util.spec_from_file_location("bench_gate_gate_mod", os.path.join(HERE, "gate", "gate.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return {k: v[1] for k, v in mod.SERVICES.items()}
    except Exception:
        return {}


# --------------------------------------------------------------------------------------------------------------- HTTP helper
def http(method, url, data=None, headers=None, timeout=600):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except OSError as e:
        raise RuntimeError(f"{type(e).__name__} on {method} {url.split('?')[0].rsplit('/', 1)[-1] or '/'}")


def need_ok(code, body, what):
    if code != 200:
        raise RuntimeError(f"{what}: HTTP {code}")
    return body


def wav_seconds(body):
    with wave.open(io.BytesIO(body)) as w:
        return w.getnframes() / float(w.getframerate())


# ------------------------------------------------------------------------------------------------------------------- context
class Ctx:
    def __init__(self, args, gate, nv, measure, env, home, videos, sleep=time.sleep, now=time.time, media=None,
                 mcp_factory=None, resolve_dispatch=None, run=subprocess.run, unlock_path=GPU_UNLOCK_TARGETS, cpu_dir=CPU_FREQ_DIR):
        self.args, self.gate, self.nv, self.measure, self.env = args, gate, nv, measure, env
        self.home, self.videos = home, videos
        self.tmp = os.path.join(home, "tmp")
        self.sleep, self.now, self.run = sleep, now, run
        self.unlock_path, self.gpu_unlock, self.task, self.cpu_dir = unlock_path, None, None, cpu_dir
        self.known_pids = set()          # compute apps that belong here: the desktop ones before the bench, the service once it is up
        self.static_env = None           # driver and kernel, read once
        self.task_env = {}               # per task: service image id, model files, ComfyUI version
        self.media = media or Media(self)
        self.mcp_factory = mcp_factory or McpSession
        self.resolve_dispatch = resolve_dispatch or os.path.join(HERE, "mcp_dispatch.sh")
        self.bench_id = None
        self.run_id = time.strftime("%Y%m%dT%H%M%S")
        self.found_w = None
        self.state = {}
        self.results = os.path.join(home, "results.jsonl")
        self.results_all = []
        self.cap_min = self.cap_max = None
        self.current_cap = None          # the limit the card actually reported after the last set_cap (None when it could not be read)
        self.cap_asked, self.cap_ok = None, True   # the last cap asked of the gate, and whether the card confirmed it
        self.service = None              # the docker service of the running task: its worker's PIDs are the only ones blessed as "ours"
        self.cold_armed = False          # set once the warm-up is over: a new worker process of the service after that is a cold job
        self.last_job_end = None

    def record(self, obj):
        obj = dict(obj, run=self.run_id, bench=self.bench_id, gpu_unlock=read_gpu_unlock(self.unlock_path))
        self.results_all.append(obj)
        os.makedirs(self.home, exist_ok=True)
        with open(self.results, "a") as f:
            f.write(json.dumps(obj) + "\n")

    def refresh_state(self):
        code, st = self.gate.call("GET", "/state")
        if code != 200:
            raise TaskError(f"GET /state: HTTP {code}")
        self.state = st
        return st

    def service_pids(self, name):
        """Host PIDs of the processes inside the service's container (docker top), None when docker cannot say."""
        out = docker_out(self, ["top", name, "-eo", "pid"])
        if out is None:
            return None
        return {ln.strip() for ln in out.splitlines()[1:] if ln.strip().isdigit()}

    def note_service_apps(self, name=None, lenient=True):
        """Remember compute apps on the card as belonging to this run. With a service NAME only the apps that run inside that
        container count (a foreign app that appears meanwhile stays foreign, and a worker the service respawned is recognised); returns
        the set of newly known PIDs. Without a name (Resolve, a host process), or when docker cannot list the container, every app on the
        card now is taken as this run's own and the return is an empty set; with LENIENT False nothing is blessed in that case (the
        jobs' own re-check must never bless a foreign app just because docker could not answer)."""
        try:
            apps = set(pids_of(self.nv.compute_apps()))
        except (OSError, subprocess.SubprocessError):
            return set()
        own = self.service_pids(name) if name else None
        if own is None:
            if lenient:
                self.known_pids |= apps
            return set()
        new = {p for p in apps if p in own} - self.known_pids
        self.known_pids |= new
        return new

    def idle_probe(self):
        """The card at rest just before a job: it settles for SETTLE_S, then three reads half a second apart (the highest GPU use and
        encoder session count count). A read the driver cannot give is None."""
        self.sleep(SETTLE_S)
        reads = []
        for i in range(3):
            if i:
                self.sleep(0.5)
            reads.append(self.nv.snapshot())
        first = dict(reads[0])
        for k in ("util", "enc_sessions"):
            vals = [r.get(k) for r in reads if r.get(k) is not None]
            first[k] = max(vals) if vals else None
        return first

    def timed(self, tag, fn, unit="job", meta=None):
        """One measured job, after a check that no person's session appeared and the bench is still ours. Before it the card settles
        and is read at rest; after it the power limit is read again. The job carries the real limit, temperature, SM clock, throttle
        reasons, encoder sessions, CPU governor and EPP, driver, kernel and gpu-unlock, and `invalid_why` (reasons, empty list = valid)
        when it must not be pooled. META is what the job function noted about itself (seed, prompt index, output hash)."""
        guard(self, f"job {tag}")
        pre = self.idle_probe()
        apps_pre = foreign_apps(self.nv.compute_apps(), self.known_pids, self.args.allow_app)
        began = {}

        def job():
            began["t"] = self.now()
            return fn()

        res = self.measure(tag, job, unit)
        end = self.now()
        gap = began["t"] - self.last_job_end if began.get("t") is not None and self.last_job_end is not None else None
        self.last_job_end = end
        post = self.nv.snapshot()
        # a new worker process of the service after the warm-up: ComfyUI exited at its IDLE_S and this job started it again (cold)
        cold = bool(self.service and self.cold_armed and self.note_service_apps(self.service, lenient=False))
        apps_post = foreign_apps(self.nv.compute_apps(), self.known_pids, self.args.allow_app)
        if meta:
            res.update(meta)
            meta.clear()
        if self.static_env is None:
            self.static_env = {"driver": self.nv.driver(), "kernel": os.uname().release}
        res.update({
            "cap_w_req": self.current_cap, "cap_w_asked": self.cap_asked, "cold": cold, "idle_gap_s": round(gap, 1) if gap is not None else None,
            "limit_w_start": pre.get("limit_w"), "limit_w_end": post.get("limit_w"),
            "temp_c_start": pre.get("temp_c"), "temp_c_end": post.get("temp_c"), "idle_util_pct": pre.get("util"),
            "enc_sessions_idle": pre.get("enc_sessions"), "throttle_idle": pre.get("throttle"),
            "foreign_apps": sorted(set(apps_pre) | set(apps_post)), "gpu_unlock": read_gpu_unlock(self.unlock_path),
            **cpu_policy(self.cpu_dir), **self.static_env,
        })
        why = judge_job(res, self.task, self.current_cap, pre, post, res["foreign_apps"]) if res.get("ok", True) else []
        if res.get("ok", True) and cold:
            why.append("cold start: the service's worker process was respawned during the job (it had exited at its idle timeout)")
        if res.get("ok", True) and not self.cap_ok and self.cap_asked is not None:
            why.append(f"cap not confirmed: asked {self.cap_asked:.0f} W, the card reports "
                       + (f"{self.current_cap:.0f} W" if self.current_cap is not None else "nothing readable"))
        idle_s = SERVICE_IDLE_S.get(self.service or "")
        if gap is not None and idle_s and gap > IDLE_GAP_WARN * idle_s:
            log(f"warning: job {tag} started {gap:.0f} s after the previous one; {self.service} stops its worker after {idle_s:.0f} s idle")
        if why:
            res["invalid_why"] = why
            log(f"warning: job {tag} is invalid, not pooled: " + "; ".join(why))
        return res

    def port_of(self, name):
        svc = (self.refresh_state().get("services") or {}).get(name)
        if not svc:
            raise TaskError(f"the gate does not know service {name}")
        return int(svc["port"])

    def token_of(self, name):
        key = SERVICE_TOKEN.get(name)
        val = self.env.get(key, "") if key else ""
        if name in TOKEN_REQUIRED and not val:
            raise TaskError(f"{key} is not set in host.env")
        return val

    def bearer(self, name):
        tok = self.token_of(name)
        return {"Authorization": "Bearer " + tok} if tok else {}


class Media:
    """Synthetic inputs made with ffmpeg: no person's files, nothing downloaded."""

    def __init__(self, ctx):
        self.ctx = ctx

    def _make(self, path, cmd):
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not shutil.which("ffmpeg"):
            raise TaskError("ffmpeg is not installed")
        r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y"] + cmd + [path], capture_output=True, text=True)
        if r.returncode:
            raise TaskError("ffmpeg failed: " + r.stderr[-120:])
        return path

    def video(self, kind):
        c = self.ctx
        enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p"]
        if kind == "hd60":      # synthetic 60 s 1080p24: the Resolve render and the NVENC job
            return self._make(os.path.join(c.videos, "src_hd60.mp4"),
                              ["-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=24", "-t", "60"] + enc)
        if kind == "sd5":       # 5 s 832x480: what vidgen makes, the vidpost input
            return self._make(os.path.join(c.tmp, "sd5.mp4"),
                              ["-f", "lavfi", "-i", "testsrc2=size=832x480:rate=24", "-t", "5"] + enc)
        raise ValueError(kind)

    def png(self):
        return self._make(os.path.join(self.ctx.tmp, "up.png"),
                          ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=1", "-frames:v", "1"])


# --------------------------------------------------------------------------------------------------------- gate-side helpers
def guard(ctx, what):
    """Read GET /state before a cap or a job. Raises Interrupted when a person's session appeared ("blocked"), when the bench
    is gone, or when the gate cannot be read: the run stops cleanly, a person's session is never capped or disturbed."""
    try:
        st = ctx.refresh_state()
    except (TaskError, GateError) as e:
        raise Interrupted(ctx.task, what, f"cannot read the gate state ({e})")
    if st.get("blocked"):
        raise Interrupted(ctx.task, what, f"a person's session appeared (gate blocked: {st['blocked']})")
    b = st.get("bench")
    if not b or b.get("id") != ctx.bench_id:
        raise Interrupted(ctx.task, what, "the bench is gone (ended or expired)")


def set_cap(ctx, watts):
    """Move the bench's cap and confirm it by reading the limit back. Returns True when the card reports it. When it does not,
    ctx.current_cap is the limit the card does report (None when unreadable) and ctx.cap_ok is False: Ctx.timed marks every job of
    that cap invalid ("cap not confirmed"), so nothing is judged or pooled under a cap that was not applied."""
    guard(ctx, f"cap {int(watts)} W")
    ctx.cap_asked = watts
    code, r = ctx.gate.call("POST", "/bench/watts", {"bench": ctx.bench_id, "watts": int(watts)})
    if code == 404 and r.get("why") == "unknown_bench":
        raise Interrupted(ctx.task, f"cap {int(watts)} W", "the bench is gone (unknown_bench)")
    if code != 200:
        raise TaskError(f"/bench/watts {watts}: HTTP {code} {r.get('why', '')}")
    end = ctx.now() + 8
    got = None
    while True:
        got = ctx.nv.limit_w()
        if got is not None and abs(got - watts) <= CAP_TOLERANCE_W:
            ctx.current_cap, ctx.cap_ok = watts, True
            ctx.sleep(2)
            return True
        if ctx.now() > end:
            break
        ctx.sleep(1)
    ctx.current_cap, ctx.cap_ok = got, False
    log(f"warning: asked {watts} W, the card reports {got} W: the jobs at this cap are marked invalid")
    return False


def wake(ctx, name, port):
    body = {"port": port, "stack": "bench", "mode": "batch", "batch": re.sub(r"[^A-Za-z0-9._:-]", "-", f"bench-{ctx.bench_id}")[:64],
            "bench": ctx.bench_id}
    for attempt in range(7):
        code, r = ctx.gate.call("POST", "/wake", body)
        if code in (200, 202):
            return r
        if code == 409 and r.get("why") in ("vram", "exclusive") and attempt < 6:
            ctx.sleep(5)             # a previous service may still be stopping
            continue
        raise TaskError(f"wake {name}: HTTP {code} {r.get('why', '')}".strip())


def wait_health(ctx, name, port, budget_s):
    end = ctx.now() + budget_s
    while ctx.now() < end:
        try:
            if http("GET", f"http://127.0.0.1:{port}/healthz", timeout=5)[0] == 200:
                return
        except RuntimeError:
            pass
        ctx.sleep(1)
    raise TaskError(f"{name} did not answer /healthz in {budget_s:.0f} s")


def release(ctx, name, lease):
    ctx.gate.call("POST", "/done", {"lease": lease})
    ctx.gate.call("POST", "/release", {"lease": lease, "close": True})
    wait_stopped(ctx, name)


def wait_stopped(ctx, name, budget_s=120):
    end = ctx.now() + budget_s
    while ctx.now() < end:
        try:
            svc = (ctx.refresh_state().get("services") or {}).get(name) or {}
        except TaskError:
            svc = {}
        if not svc.get("running"):
            return True
        ctx.sleep(2)
    log(f"warning: {name} still running {budget_s} s after the release")
    return False


class JobSpec:
    """One task's job. `meta`: what the job function notes about the last run (seed, prompt index, output hash), merged into that job's
    row by Ctx.timed. `variants`: for a ComfyUI task, the (prompt, seed) source (see Variants); its presence turns the cache canary on."""

    def __init__(self, fn, unit=None, extra=None, variants=None, meta=None, outputs=None):
        self.fn, self.unit, self.extra, self.variants = fn, unit, extra or {}, variants
        self.outputs = outputs or {}                      # unit -> units per `ret` (see EFFICIENCY): the output size of a job
        self.meta = meta if meta is not None else {}


class Variants:
    """The next (prompt, seed) of the fixed tables for each timed ComfyUI job: never the one of the previous job, the same sequence in
    every session. pick() advances; repeat_next() makes the next pick the same as the last (only the cache canary does that)."""

    def __init__(self, prompts, seeds=SEEDS):
        self.prompts, self.seeds, self.i, self.again = list(prompts), list(seeds), -1, False

    def pick(self):
        if not self.again or self.i < 0:
            self.i += 1
        self.again = False
        return self.prompts[self.i % len(self.prompts)], self.seeds[self.i % len(self.seeds)], self.i

    def repeat_next(self):
        self.again = True


def sha8(data):
    return hashlib.sha256(data).hexdigest()[:8]


def result_shell(name, kind="service"):
    return {"kind": "task", "task": name, "task_kind": kind, "rows": [], "notes": [], "error": None, "baseline_mib": None,
            "vram_peak_mib": None}


def docker_out(ctx, args):
    """stdout of a read-only docker call, None when it fails: the environment snapshot is best effort and never stops a run."""
    try:
        r = ctx.run(["docker"] + args, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout or "").strip() if r.returncode == 0 else None


def service_env(ctx, name):
    """What the service ran with, read once it is up: its image id, the size of the model files it loads, the ComfyUI version."""
    out = {"image_id": None, "model_files": None, "comfyui_version": None}
    img = docker_out(ctx, ["inspect", "--format", "{{.Image}}", name])
    if img:
        out["image_id"] = img.replace("sha256:", "")[:12]
    files = MODEL_FILES.get(name)
    if files is None and name in MODEL_DIRS:
        # no fixed file list: a digest of the model directory's listing (relative names and sizes), so a swapped or re-downloaded model shows
        txt = docker_out(ctx, ["exec", name, "find", "-L", MODEL_DIRS[name], "-type", "f", "-printf", "%P %s\n"])
        if txt is not None:
            lines = sorted(txt.splitlines())
            out["model_files"] = {"dir": MODEL_DIRS[name], "files": len(lines),
                                  "bytes": sum(int(ln.rpartition(" ")[2]) for ln in lines if ln.rpartition(" ")[2].isdigit()),
                                  "sha8": sha8("\n".join(lines).encode())}
    if isinstance(files, dict):
        files = files.get(ctx.args.img_quality)
    if files:
        expr = []
        for f in files:
            expr += ["-o", "-name", f] if expr else ["-name", f]
        txt = docker_out(ctx, ["exec", name, "find", "-L", "/models", "-type", "f", "("] + expr + [")", "-printf", "%f %s\n"])
        if txt is not None:
            got = {}
            for ln in txt.splitlines():
                n, _, sz = ln.rpartition(" ")
                if n and sz.isdigit():
                    got[n] = int(sz)
            out["model_files"] = {f: got.get(f) for f in files}
    if name in DYNAMIC_VRAM:
        txt = docker_out(ctx, ["exec", name, "cat", "/w/ComfyUI/comfyui_version.py"])
        m = re.search(r"__version__\s*=\s*[\"']([^\"']{1,30})", txt or "")
        out["comfyui_version"] = m.group(1) if m else None
    return out


def env_changes(before, after):
    """Keys of the service environment (image id, model files, ComfyUI version) that differ between two reads. A value one of the
    reads could not give (None) is not a change."""
    return [k for k in ("image_id", "model_files", "comfyui_version")
            if (before or {}).get(k) is not None and (after or {}).get(k) is not None and before[k] != after[k]]


def env_row(ctx, name, cap, runs, env=None):
    """The environment of one result row: driver, kernel, gpu-unlock, CPU governor and EPP, the cap asked and the limit the card read
    back, and (docker services) image id, model files and ComfyUI version, as read for this row when ENV is given."""
    last = next((r for r in reversed(runs) if r.get("limit_w_end") is not None), {})
    return {**(ctx.static_env or {}), "gpu_unlock": read_gpu_unlock(ctx.unlock_path), **cpu_policy(ctx.cpu_dir), "cap_w_req": cap,
            "limit_w_read": last.get("limit_w_end"), **(env if env is not None else ctx.task_env.get(name, {}))}


def run_canary(ctx, name, spec, res):
    """Before any ComfyUI row: one job on a new (prompt, seed) (the first warm one), then the same job again. ComfyUI keeps node outputs
    (--cache-classic): a repeat that skips the sampler is far faster than a real one. When the identical repeat is more than CANARY_RATIO
    times faster, every number of this task would be a cache hit passing for production: the task is aborted and nothing is recorded as a row."""
    first = ctx.timed(f"{name}-canary-new", spec.fn, spec.unit or "job", spec.meta)
    spec.variants.repeat_next()
    again = ctx.timed(f"{name}-canary-same", spec.fn, spec.unit or "job", spec.meta)
    if not (first.get("ok") and again.get("ok")):
        raise TaskError(f"canary job failed: {first.get('err') or again.get('err')}")
    ratio = first["wall_s"] / again["wall_s"] if again["wall_s"] else float("inf")
    tainted = ratio > CANARY_RATIO
    res["canary"] = {"first_s": first["wall_s"], "repeat_s": again["wall_s"], "ratio": round(ratio, 2), "tainted": tainted,
                     "same_output": first.get("out_sha8") == again.get("out_sha8")}
    ctx.record({"kind": "canary", "task": name, **res["canary"], "runs": [slim(first), slim(again)]})
    if tainted:
        res["cache_tainted"] = True
        raise TaskError(f"cache-tainted: an identical repeated job took {again['wall_s']} s against {first['wall_s']} s for the first warm one "
                        f"({ratio:.1f}x faster, limit {CANARY_RATIO:.0f}x): ComfyUI served it from its node cache, so no row of this task is "
                        "valid. Restart the service without --cache-classic or do not trust imggen/vidgen numbers from this run")
    res["notes"].append(f"cache canary passed: identical repeat {ratio:.1f}x the speed of the first warm job (limit {CANARY_RATIO:.0f}x)")


def run_service(ctx, name, prepare, caps, reps):
    """The common path of a docker service task: prepare inputs, wake with the bench id, healthz, warm-up, (canary), sweep, release."""
    res = result_shell(name)
    lease = None
    ctx.service, ctx.cold_armed, ctx.last_job_end = None, False, None
    try:
        spec_for = prepare(ctx)                       # inputs first: a missing token or ffmpeg skips the task before any wake
        port = ctx.port_of(name)
        res["baseline_mib"] = ctx.nv.mem_used_mib()
        r = wake(ctx, name, port)
        lease = r.get("lease")
        t0 = ctx.now()
        wait_health(ctx, name, port, max(60.0, 2.0 * float(r.get("eta_s") or 0) + 60))
        res["ready_s"] = round(ctx.now() - t0, 1)
        ctx.service = name
        ctx.note_service_apps(name)
        ctx.task_env[name] = service_env(ctx, name)
        spec = spec_for(port)
        if not set_cap(ctx, caps[0]):
            res["notes"].append(f"the warm-up cap {caps[0]} W was not confirmed by the card (the warm-up is never pooled)")
        warm = ctx.timed(f"{name}-warmup", spec.fn, spec.unit or "job", spec.meta)
        res["warmup"] = {k: warm.get(k) for k in ("ok", "err", "wall_s", "vram_peak_mib", "gpu_wh")}
        if not warm.get("ok"):
            raise TaskError(f"warm-up job failed: {warm.get('err')}")
        ctx.note_service_apps(name)
        ctx.cold_armed = True                         # from here a new worker process of the service means a cold job
        if spec.variants is not None:
            run_canary(ctx, name, spec, res)
        peaks = [warm.get("vram_peak_mib") or 0]
        for cap in caps:
            cap_ok = set_cap(ctx, cap)
            runs = [ctx.timed(f"{name}-{cap}W", spec.fn, spec.unit or "job", spec.meta) for _ in range(reps)]
            row = summarise(cap, runs, ctx.args.wh_key, spec.unit, name, spec.outputs)
            row["cap_ok"] = cap_ok
            env_now = service_env(ctx, name)          # read again for every row: a swapped model or image mid-task is flagged, not copied
            changed = env_changes(ctx.task_env.get(name), env_now)
            if changed:
                row["env_changed"] = changed
                res["notes"].append(f"{cap} W: the service environment changed since the task started ({', '.join(changed)}); "
                                    "rows before and after are not comparable")
                log(f"warning: {name} environment changed during the task: {', '.join(changed)}")
            res["rows"].append(row)
            peaks.append(row.get("vram_peak_mib") or 0)
            ctx.record({"kind": "cap", "task": name, "row": row, "runs": [slim(x) for x in runs], "extra": spec.extra,
                        "env": env_row(ctx, name, cap, runs, env_now)})
            log(f"{name} {cap} W: " + row_line(row))
        res["vram_peak_mib"] = max(peaks)
    except Interrupted as e:
        res["error"], res["interrupted"] = str(e), str(e)
    except TaskError as e:
        res["error"] = str(e)
    finally:
        ctx.service, ctx.cold_armed = None, False
        if lease:
            try:
                release(ctx, name, lease)
            except GateError as e:
                res["notes"].append(f"release failed: {e}")
    return res


SLIM_KEYS = ("ok", "err", "wall_s", "gpu_avg_w", "gpu_peak_w", "gpu_wh", "gpu_net_wh", "gpu_net18_wh", "vram_peak_mib", "ret", "ts",
             "cap_w_req", "limit_w_start", "limit_w_end", "limit_w_min", "limit_w_max", "temp_c_start", "temp_peak_c", "sm_mhz_med",
             "throttle_or", "throttle_idle", "enc_sessions_idle", "enc_sessions_max", "idle_util_pct", "foreign_apps", "invalid_why",
             "temp_c_end", "governor", "epp", "driver", "kernel", "gpu_unlock", "seed", "prompt_i", "out_sha8",
             "samples", "gpu_idle_w", "gpu_util_avg", "cpu_busy_core_s", "cap_w_asked", "cold", "idle_gap_s")


def slim(m):
    return {k: m.get(k) for k in SLIM_KEYS}


def row_line(row):
    if not row.get("n_ok"):
        return f"no valid job ({', '.join(row.get('errors', []))})"
    bad = f", {row['n_invalid']} invalid job(s) left out ({'; '.join(row.get('invalid_why', []))})" if row.get("n_invalid") else ""
    thin = f"; THIN: under {min_valid_jobs(row['n'])} valid jobs, left out of the recommendation" if row.get("thin") else ""
    po = efficiency_text(row.get("per_output"))
    return (f"{row['wall_s']} s/job, {row['avg_w']} W avg, {row['wh']} Wh/job gross, {row['net18_wh']} net18, "
            f"VRAM peak {row['vram_peak_mib']} MiB ({row['n_ok']}/{row['n']} ok{bad}{thin})" + (f"; {po}" if po else ""))


# ----------------------------------------------------------------------------------------------------------------- stt, tts-hq
def make_stt_clip(ctx):
    """~stt_secs of Spanish speech from the local Piper tts (a CPU service the gate also manages), cached in tmp."""
    path = os.path.join(ctx.tmp, f"stt_es_{int(ctx.args.stt_secs)}.wav")     # the length is in the name: another --stt-secs is another clip
    if os.path.isfile(path):
        return path, wav_seconds(open(path, "rb").read())
    os.makedirs(ctx.tmp, exist_ok=True)
    target = float(ctx.args.stt_secs)
    lease = None
    port = ctx.port_of("tts")
    try:
        lease = wake(ctx, "tts", port).get("lease")
        wait_health(ctx, "tts", port, 90)
        frames, params, total, i = [], None, 0.0, 0
        while total < target and i < 40:
            text = STT_PARAGRAPHS[i % len(STT_PARAGRAPHS)]
            body = need_ok(*http("POST", f"http://127.0.0.1:{port}/v1/audio/speech",
                                 json.dumps({"input": text, "voice": "auto", "response_format": "wav"}).encode(),
                                 {"Content-Type": "application/json"}, timeout=120), "tts speech")
            with wave.open(io.BytesIO(body)) as w:
                p = (w.getnchannels(), w.getsampwidth(), w.getframerate())
                params = params or p
                if p != params:
                    raise TaskError("tts returned audio with changing parameters")
                frames.append(w.readframes(w.getnframes()))
                total += w.getnframes() / float(w.getframerate())
            i += 1
        out = wave.open(path, "wb")
        out.setnchannels(params[0]); out.setsampwidth(params[1]); out.setframerate(params[2])
        out.writeframes(b"".join(frames))
        out.close()
        return path, total
    except (RuntimeError, wave.Error) as e:
        if os.path.exists(path):
            os.remove(path)
        raise TaskError(f"could not make the Spanish clip: {e}")
    finally:
        if lease:
            release(ctx, "tts", lease)


def prepare_stt(ctx):
    path, secs = make_stt_clip(ctx)
    data = open(path, "rb").read()

    def spec_for(port):
        def job():
            body = need_ok(*http("POST", f"http://127.0.0.1:{port}/transcribe?lang=es", data, {"Content-Type": "audio/wav"},
                                 timeout=1200), "transcribe")
            j = json.loads(body)
            if not j.get("text"):
                raise RuntimeError("empty transcript")
            return float(j.get("audio_seconds") or secs) / 60.0
        return JobSpec(job, "audio_min", {"clip_s": round(secs, 1)}, outputs={"audio_seconds": 60.0})       # ret is minutes of audio in
    return spec_for


def prepare_tts_hq(ctx):
    texts = [("es", TEXT_ES), ("en", TEXT_EN), ("ru", TEXT_RU)]

    def spec_for(port):
        def job():
            total = 0.0
            for lang, text in texts:
                body = need_ok(*http("POST", f"http://127.0.0.1:{port}/v1/audio/speech",
                                     json.dumps({"input": text, "voice": "auto", "response_format": "wav", "language": lang}).encode(),
                                     {"Content-Type": "application/json"}, timeout=900), f"speech {lang}")
                total += wav_seconds(body)
            return total
        return JobSpec(job, "audio_s", {"job": "es+en+ru paragraphs"}, outputs={"audio_seconds_out": 1.0})  # ret is seconds of audio out
    return spec_for


# ------------------------------------------------------------------------------------------------ recheck services (tokens)
def prepare_upscaler(ctx):
    png = open(ctx.media.png(), "rb").read()

    def spec_for(port):
        def job():
            need_ok(*http("POST", f"http://127.0.0.1:{port}/upscale", png, dict(ctx.bearer("upscaler"), **{"Content-Type": "image/png"}),
                          timeout=300), "upscale")
            return 1
        return JobSpec(job, "image", {"input": "640x360 png"},
                       outputs={"megapixels_out": UPSCALE_IN[0] * UPSCALE_IN[1] * UPSCALE_FACTOR ** 2 / 1e6})
    return spec_for


def prepare_transcoder(ctx):
    src = open(ctx.media.video("hd60"), "rb").read()

    def spec_for(port):
        def job():
            need_ok(*http("POST", f"http://127.0.0.1:{port}/transcode?height=720&codec=h264", src,
                          dict(ctx.bearer("transcoder"), **{"Content-Type": "video/mp4"}), timeout=900), "transcode")
            return 1
        return JobSpec(job, "clip", {"input": "60 s 1080p24 testsrc2 -> 720p h264"}, outputs={"frames": float(TRANSCODER_SECS * SRC_FPS)})
    return spec_for


def prepare_vidpost(ctx):
    ctx.token_of("vidpost")
    src = open(ctx.media.video("sd5"), "rb").read()

    def spec_for(port):
        def job():
            need_ok(*http("POST", f"http://127.0.0.1:{port}/enhance?scale=2&fps=2", src,
                          dict(ctx.bearer("vidpost"), **{"Content-Type": "video/mp4"}), timeout=1200), "enhance")
            return 1
        return JobSpec(job, "clip", {"input": "5 s 832x480 -> x2, 48 fps"}, outputs={"frames_out": 2.0 * VIDPOST_SECS * SRC_FPS - 1.0})
    return spec_for


def prepare_imggen(ctx):
    ctx.token_of("imggen")
    quality = ctx.args.img_quality

    def spec_for(port):
        variants, meta = Variants(IMG_PROMPTS), {}

        def job():
            prompt, seed, i = variants.pick()           # a new (prompt, seed) every job: ComfyUI's node cache must not answer for us
            body = json.dumps({"prompt": prompt, "size": "1024x1024", "quality": quality, "seed": seed}).encode()
            out = need_ok(*http("POST", f"http://127.0.0.1:{port}/image", body,
                                dict(ctx.bearer("imggen"), **{"Content-Type": "application/json"}), timeout=900), "image")
            meta.update(seed=seed, prompt_i=i % len(IMG_PROMPTS), out_sha8=sha8(out))
            return 1
        return JobSpec(job, "image", {"quality": quality, "size": "1024x1024", "cache": "classic: new prompt and seed per job"}, variants, meta,
                       outputs={"images": 1.0, "megapixels": size_mpx("1024x1024")})
    return spec_for


def prepare_vidgen(ctx):
    ctx.token_of("vidgen")
    secs = int(ctx.args.vid_secs)

    def spec_for(port):
        variants, meta = Variants(VID_PROMPTS), {}

        def job():
            prompt, seed, i = variants.pick()
            body = json.dumps({"prompt": prompt, "secs": secs, "seed": seed}).encode()
            out = need_ok(*http("POST", f"http://127.0.0.1:{port}/video", body,
                                dict(ctx.bearer("vidgen"), **{"Content-Type": "application/json"}), timeout=1500), "video")
            meta.update(seed=seed, prompt_i=i % len(VID_PROMPTS), out_sha8=sha8(out))
            return secs
        return JobSpec(job, "clip_s", {"secs": secs, "cache": "classic: new prompt and seed per job"}, variants, meta,
                       outputs={"frames": vidgen_frames(secs) / secs})     # ret is the clip's seconds; its frames are the model's grid, not secs x 24
    return spec_for


SERVICE_PREPARE = {"stt": prepare_stt, "tts-hq": prepare_tts_hq, "upscaler": prepare_upscaler, "transcoder": prepare_transcoder,
                   "vidpost": prepare_vidpost, "imggen": prepare_imggen, "vidgen": prepare_vidgen}


# ------------------------------------------------------------------------------------------------------------------ resolve
class McpSession:
    """A stdio MCP client over a child process, with timeouts (the reader runs in a thread)."""

    def __init__(self, argv, env):
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
        self.q, self.n = queue.Queue(), 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            self.q.put(line)
        self.q.put(None)

    def rpc(self, method, params=None, notify=False, timeout=300):
        m = {"jsonrpc": "2.0", "method": method}
        if not notify:
            self.n += 1
            m["id"] = self.n
        if params is not None:
            m["params"] = params
        self.p.stdin.write(json.dumps(m) + "\n")
        self.p.stdin.flush()
        end = time.time() + timeout
        while not notify:
            try:
                line = self.q.get(timeout=max(0.1, end - time.time()))
            except queue.Empty:
                raise RuntimeError(f"MCP {method}: no answer in {timeout} s")
            if line is None:
                raise RuntimeError(f"MCP {method}: the server exited")
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("id") == self.n:
                return r

    def initialize(self, timeout=300):
        self.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "bench_gate", "version": "1"}},
                 timeout=timeout)
        self.rpc("notifications/initialized", notify=True)

    def tool(self, name, action, params=None, timeout=300):
        r = self.rpc("tools/call", {"name": name, "arguments": {"action": action, **({"params": params} if params is not None else {})}},
                     timeout=timeout)
        if "error" in r:                       # JSON-RPC error (gate refusal, unknown tool): a failure, never a success
            err = r["error"]
            raise RuntimeError(f"MCP {name}.{action}: " + str(err.get("message", err) if isinstance(err, dict) else err)[:200])
        res = r.get("result", {})
        txt = "".join(c.get("text", "") for c in res.get("content", []))
        try:
            data = json.loads(txt)
        except ValueError:
            data = {"raw": txt}
        bad = bool(res.get("isError")) or (isinstance(data, dict) and (data.get("success") is False or "error" in data))
        return data, bad

    def close(self, wait_s=90):
        """End the session: the wrapper quits Resolve when its last client leaves. A stuck child is asked to stop, never killed."""
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.wait(timeout=wait_s)
        except subprocess.TimeoutExpired:
            self.p.terminate()
            try:
                self.p.wait(timeout=wait_s)
            except subprocess.TimeoutExpired:
                raise RuntimeError("the Resolve MCP child did not exit")


def resolve_rep(ctx, cap, tag, out_dir, src):
    """One fresh Resolve session: cold start, idle VRAM, then the render under the recorder. Returns (run, extras)."""
    name = "zz_bench_proj"
    custom = f"zz_{tag}"
    guard(ctx, f"resolve session {tag}")
    base = ctx.nv.mem_used_mib()
    env = dict(os.environ, SSH_ORIGINAL_COMMAND="davinci", RESOLVE_GATE_STACK="bench", RESOLVE_GATE_BENCH=str(ctx.bench_id))
    t0 = ctx.now()
    s = ctx.mcp_factory([ctx.resolve_dispatch], env)
    extras = {}
    try:
        s.initialize()
        s.tool("project_manager", "delete", {"name": name, "close_current": True}, timeout=300)   # first tool call: the gate wake + Resolve start
        extras["cold_s"] = round(ctx.now() - t0, 1)
        _, bad = s.tool("project_manager", "create", {"name": name})
        if bad:
            raise RuntimeError("create project failed")
        ctx.sleep(3)
        extras["idle_vram_mib"] = round(ctx.nv.mem_used_mib() - base, 0)
        steps = [("media_pool", "safe_import_media", {"paths": [src]})]
        for tool, action, params in steps:
            if s.tool(tool, action, params)[1]:
                raise RuntimeError(f"{tool}.{action} failed")
        clips, bad = s.tool("folder", "get_clips", {})
        ids = re.findall(r'"(?:clip_id|id|unique_id)"\s*:\s*"([0-9a-fA-F-]{8,})"', json.dumps(clips))
        if bad or not ids:
            raise RuntimeError("no clip id after the import")
        for tool, action, params in [("media_pool", "create_timeline_from_clips", {"name": "tl", "clip_ids": ids[:1]}),
                                     ("render", "load_preset", {"name": "H.264 Master"}),
                                     ("render", "set_settings", {"settings": {"TargetDir": out_dir, "CustomName": custom, "SelectAllFrames": True}}),
                                     ("render", "add_job", None)]:
            if s.tool(tool, action, params)[1]:
                raise RuntimeError(f"{tool}.{action} failed")

        def render():
            if s.tool("render", "start")[1]:
                raise RuntimeError("render.start failed")
            end = ctx.now() + 900
            while ctx.now() < end:
                d, _ = s.tool("render", "is_rendering")
                if "true" not in json.dumps(d).lower():
                    break
                ctx.sleep(1)
            else:
                raise RuntimeError("render did not finish in 900 s")
            files = [f for f in glob.glob(os.path.join(out_dir, custom + "*")) if os.path.getsize(f) > 0]
            if not files:
                raise RuntimeError("no output file")
            return 1

        ctx.note_service_apps()                       # Resolve is up now: its processes are this run's
        run = ctx.timed(f"resolve-{cap}W", render, "render")
        try:
            s.tool("project_manager", "delete", {"name": name, "close_current": True})
        except RuntimeError as e:             # the measured render is done: a clean-up error does not void it
            log(f"warning: could not delete the throwaway project ({e})")
        return run, extras
    finally:
        try:
            s.close()
        finally:
            ctx.gate.call("POST", "/off", {"stack": "bench", "port": ctx.port_of("resolve")})   # drop the session's interactive lease
            if not wait_stopped(ctx, "resolve", 150):
                raise TaskError("Resolve is still running after the session closed")


def run_resolve(ctx, caps, reps):
    res = result_shell("resolve", "mcp")
    res["baseline_mib"] = ctx.nv.mem_used_mib()
    out_dir = os.path.join(ctx.videos, "out")
    try:
        os.makedirs(out_dir, exist_ok=True)
        src = ctx.media.video("hd60")
        peaks, idles, colds = [], [], []
        set_cap(ctx, caps[0])
        warm, wx = resolve_rep(ctx, caps[0], "warm", out_dir, src)
        res["warmup"] = {"ok": warm.get("ok"), "err": warm.get("err"), "wall_s": warm.get("wall_s"), **wx}
        if not warm.get("ok"):
            raise TaskError(f"warm-up render failed: {warm.get('err')}")
        peaks.append(warm.get("vram_peak_mib") or 0)
        for cap in caps:
            cap_ok = set_cap(ctx, cap)
            runs, ex = [], []
            for i in range(reps):
                try:
                    run, x = resolve_rep(ctx, cap, f"{cap}_{i}", out_dir, src)
                except RuntimeError as e:             # a failed session counts as a failed job; a TaskError ends the task
                    run, x = {"ok": False, "err": str(e)[:200]}, {}
                runs.append(run)
                ex.append(x)
            row = summarise(cap, runs, ctx.args.wh_key, "render")
            row["cap_ok"] = cap_ok
            row["cold_s"] = _med(x.get("cold_s") for x in ex)
            row["idle_vram_mib"] = _med(x.get("idle_vram_mib") for x in ex)
            res["rows"].append(row)
            peaks.append(row.get("vram_peak_mib") or 0)
            idles += [x["idle_vram_mib"] for x in ex if x.get("idle_vram_mib") is not None]
            colds += [x["cold_s"] for x in ex if x.get("cold_s") is not None]
            ctx.record({"kind": "cap", "task": "resolve", "row": row, "runs": [slim(x) for x in runs], "extra": {"sessions": ex},
                        "env": env_row(ctx, "resolve", cap, runs)})
            log(f"resolve {cap} W: " + row_line(row) + f", cold start {row['cold_s']} s, idle +{row['idle_vram_mib']} MiB")
        res["vram_peak_mib"] = max(peaks + [res["baseline_mib"] + max(idles, default=0)])
        res["cold_s"] = _med(colds)
        res["idle_vram_mib"] = _med(idles)
    except Interrupted as e:
        res["error"], res["interrupted"] = str(e), str(e)
    except (TaskError, RuntimeError) as e:
        res["error"] = str(e)
    return res


# ------------------------------------------------------------------------------------------------------------------ effectcraft
def effectcraft_variants(cli, proj, out):
    """Render command lines tried in order on the first run: the text comp (project file as last argument, then as --project),
    then the demo project (README: `effectcraft-cli render --out intro.mp4`)."""
    return [("text-comp", [cli, "render", "--comp", "Main", "--out", out, proj]),
            ("text-comp", [cli, "render", "--comp", "Main", "--out", out, "--project", proj]),
            ("demo", [cli, "render", "--out", out])]


def require_active_bench(ctx):
    """The GPU evaluation takes the whole card, which only this run's bench reserves through the gate: refuse outside it."""
    if not ctx.bench_id:
        raise TaskError("refused: the EffectCraft GPU evaluation runs only inside this run's bench, and none is active")
    try:
        b = ctx.refresh_state().get("bench")
    except (TaskError, GateError) as e:
        raise TaskError(f"refused: cannot confirm that this run's bench is active ({e})")
    if not b or b.get("id") != ctx.bench_id:
        raise TaskError("refused: this run's bench is not active on the gate, the GPU evaluation needs the reserved card")
    guard(ctx, "EffectCraft GPU evaluation")     # still stops when a person's session appeared


def effectcraft_gpu_eval(ctx, res, cli, wrap):
    """`effectcraft-cli bench --gpu --json` once, as an evaluation only: EffectCraft stays CPU-only in production, so no profile
    and no gate need come out of it. Same recorder as the other jobs: peak VRAM, avg and peak W, Wh."""
    require_active_bench(ctx)
    if not set_cap(ctx, int(ctx.args.eval_cap)):
        res["notes"].append(f"the evaluation cap {ctx.args.eval_cap} W was not confirmed: the evaluation job is marked invalid")
    holder = {}

    def bench_gpu():
        env = dict(os.environ, WGPU_ADAPTER_NAME=os.environ.get("WGPU_ADAPTER_NAME", "NVIDIA"))
        r = ctx.run(wrap + [cli, "bench", "--gpu", "--json"], capture_output=True, text=True, env=env)
        holder["out"] = r.stdout[-20000:]
        if r.returncode:
            raise RuntimeError(f"bench rc={r.returncode}")
        return 1

    m = ctx.timed("effectcraft-gpu-eval", bench_gpu, "bench")
    try:
        parsed = json.loads(holder.get("out", ""))
    except ValueError:
        parsed = None
    ctx.record({"kind": "evaluation", "task": "effectcraft", "label": EVAL_LABEL, "what": "bench --gpu --json",
                "cap_w": int(ctx.args.eval_cap), "vram_peak_mib": m.get("vram_peak_mib"), "gpu_avg_w": m.get("gpu_avg_w"),
                "gpu_peak_w": m.get("gpu_peak_w"), "gpu_wh": m.get("gpu_wh"), "result": slim(m), "bench_json": parsed})
    res["notes"].append(f"GPU compositor {EVAL_LABEL}: at {ctx.args.eval_cap} W ok={m.get('ok')}, VRAM peak {m.get('vram_peak_mib')} MiB, "
                        f"{m.get('gpu_avg_w')} W avg / {m.get('gpu_peak_w')} W peak, {m.get('gpu_wh')} Wh, {m.get('wall_s')} s "
                        "(nothing is proposed from it)")


def run_effectcraft(ctx, reps):
    res = result_shell("effectcraft", "cpu")
    cli = ctx.env.get("EFFECTCRAFT_CLI") or os.environ.get("EFFECTCRAFT_CLI") or EFFECTCRAFT_CLI
    d = os.path.join(ctx.tmp, "effectcraft")
    proj, out = os.path.join(d, "bench.ecproj"), os.path.join(d, "out.mp4")
    wrap = ["nice", "-n", "10", "timeout", "900"]
    try:
        os.makedirs(d, exist_ok=True)
        res["baseline_mib"] = ctx.nv.mem_used_mib()
        if ctx.state.get("gpu", {}).get("default_w"):
            if not set_cap(ctx, ctx.state["gpu"]["default_w"]):       # a CPU task: run at the card's default, whatever the last cap was
                res["notes"].append("the card's default cap was not confirmed: the jobs are marked invalid")
        build = [cli, "run", "comp.new", json.dumps({"name": "Main", "width": 1280, "height": 720, "frameRate": 30, "duration": 5}),
                 "layer.newText", json.dumps({"text": "GPU bench", "size": 96, "fill": "#ffffff", "name": "Title"}), "--save-as", proj]
        built = ctx.run(wrap + build, capture_output=True, text=True).returncode == 0 and os.path.isfile(proj)
        chosen = None
        for label, cmd in effectcraft_variants(cli, proj, out):
            if label == "text-comp" and not built:
                continue
            r = ctx.run(wrap + cmd, capture_output=True, text=True)
            if r.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
                chosen = (label, cmd)
                break
        if not chosen:
            raise TaskError("effectcraft-cli could not render: check the CLI syntax in effectcraft_variants()")
        label, cmd = chosen

        def job():
            r = ctx.run(wrap + cmd, capture_output=True, text=True)
            if r.returncode or not os.path.isfile(out):
                raise RuntimeError(f"render rc={r.returncode}")
            return 1

        runs = [ctx.timed("effectcraft-cpu", job, "render") for _ in range(reps)]
        row = summarise(ctx.current_cap or 0, runs, ctx.args.wh_key, "render")
        row["comp"] = label
        res["rows"].append(row)
        res["vram_peak_mib"] = row.get("vram_peak_mib")
        delta = (row.get("vram_peak_mib") or 0) - res["baseline_mib"]
        res["verdict"] = "cpu_only" if row.get("n_ok") and delta <= EFFECTCRAFT_VRAM_ZERO_MIB else "uses_vram"
        res["notes"].append(f"{label} render: VRAM peak {delta:+.0f} MiB over the card's use before; CPU {row.get('cpu_core_s')} core-s per render "
                            "(system-wide busy time; CPU energy is not measured)")
        ctx.record({"kind": "cap", "task": "effectcraft", "row": row, "runs": [slim(x) for x in runs], "extra": {"comp": label},
                    "env": env_row(ctx, "effectcraft", ctx.current_cap, runs)})
        if ctx.args.effectcraft_gpu_eval:
            effectcraft_gpu_eval(ctx, res, cli, wrap)
    except Interrupted as e:
        res["error"], res["interrupted"] = str(e), str(e)
    except (TaskError, RuntimeError, OSError) as e:
        res["error"] = str(e)
    return res


# ----------------------------------------------------------------------------------------------------------------------- plan
def select_tasks(tasks_arg, recheck):
    if tasks_arg:
        names = [t.strip() for t in tasks_arg.split(",") if t.strip()]
        bad = [t for t in names if t not in ORDER]
        if bad:
            raise SystemExit(f"unknown task {', '.join(bad)} (choose from {', '.join(ORDER)})")
        if any(t in RECHECK_TASKS for t in names) and not recheck:
            raise SystemExit("imggen, vidgen, vidpost, transcoder and upscaler re-verify existing profiles: add --recheck")
    else:
        names = DEFAULT_TASKS + (RECHECK_TASKS if recheck else [])
    return [t for t in ORDER if t in names]


def caps_for(task, args):
    if args.caps:
        return [int(c) for c in args.caps.split(",") if c.strip()]
    return list(LONG_CAPS if task in LONG_TASKS else SHORT_CAPS)


def reps_for(task, args):
    return int(args.reps) if args.reps else DEFAULT_REPS[task]


def estimate_min(task, caps, reps, args):
    prep, ready, job = ESTIMATE[task]
    if task == "effectcraft":
        jobs = reps + (1 if args.effectcraft_gpu_eval else 0)
        return (prep + jobs * (job + 3) + (120 if args.effectcraft_gpu_eval else 0)) / 60.0
    n = 1 + len(caps) * reps + (2 if task in COMFY_TASKS else 0)   # warm-up + sweep (+ the two canary jobs of a ComfyUI task)
    per = job if task == "resolve" else job + 7 + SETTLE_S + 1.5   # 7 s: idle sample before each job and the settle after a cap change; then the settle and the idle probe before each job
    return (prep + ready + n * per + len(caps) * 4 + 30) / 60.0


def bench_ttl_s(env=None):
    """The gate's bench lifetime as this host sets it (GATE_BENCH_TTL_S in the environment or host.env), else the gate's default."""
    try:
        return float((env if env is not None else load_host_env()).get("GATE_BENCH_TTL_S") or 3600)
    except ValueError:
        return 3600.0


def print_plan(names, args, ttl_s=None):
    ttl_s = bench_ttl_s() if ttl_s is None else ttl_s
    total = 0.0
    print("Plan (nothing is touched by --dry-run):")
    print(f"  {'task':12} {'caps (W)':22} {'reps':>4} {'est. min':>9}")
    for t in names:
        caps = caps_for(t, args) if t != "effectcraft" else [int(args.eval_cap)] if args.effectcraft_gpu_eval else []
        reps = reps_for(t, args)
        m = estimate_min(t, caps_for(t, args), reps, args)
        total += m
        print(f"  {t:12} {fmt_cap_list(caps) if caps else 'none (CPU only)':22} {reps:>4} {m:>9.1f}")
    print(f"  {'total':12} {'':22} {'':>4} {total:>9.1f}   (+ a few minutes of pre-flight and clean-up)")
    print("Order: pre-flight, /bench/start, tasks one after another (wake with the bench id, healthz, warm-up, sweep, release), /bench/end.")
    if total > ttl_s / 60.0 - 5:
        print(f"Note: the gate ends a bench by itself after GATE_BENCH_TTL_S (now {ttl_s:.0f} s = {ttl_s / 60:.0f} min; default 3600 s): this plan is "
              f"{total:.0f} min plus pre-flight, so raise it in host.env (and restart the gate) or run the tasks in separate invocations.")
    print(f"Writes: {os.path.join(args.home, 'results.jsonl')} (append); temporary files in {os.path.join(args.home, 'tmp')} and "
          f"{args.videos} (removed at the end).")


# ------------------------------------------------------------------------------------------------------------------- summary
def table_lines(res):
    """Wh/job is GROSS (the headline: avg W x s). net18 is gross - 18 W x s (the repo's convention); net-idle is gross - this job's own
    measured idle draw x s. A column that says "net" says which one."""
    lines = []
    if not res["rows"]:
        return lines
    lines.append(f"  {'cap':>5} {'s/job':>8} {'avg W':>7} {'peak W':>7} {'Wh gross':>9} {'net18 Wh':>9} {'net-idle':>9} {'VRAM MiB':>9} {'ok':>5}")
    for r in res["rows"]:
        if not r.get("n_ok"):
            lines.append(f"  {r['cap_w']:>5}  no valid job: {', '.join(r.get('errors', []))}")
            continue
        flag = "" if r.get("cap_ok", True) else "  (limit not confirmed)"
        if r.get("n_invalid"):
            flag += f"  ({r['n_invalid']} invalid left out)"
        if r.get("thin"):
            flag += f"  (THIN: under {min_valid_jobs(r['n'])} valid jobs, not in the recommendation)"
        if r.get("env_changed"):
            flag += "  (environment changed during the task)"
        n18 = f"{r['net18_wh']:>9.4f}" if r.get("net18_wh") is not None else f"{'-':>9}"
        lines.append(f"  {r['cap_w']:>5} {r['wall_s']:>8.1f} {r['avg_w']:>7.1f} {r['peak_w']:>7.1f} {r['wh']:>9.4f} {n18} {r['net_wh']:>9.4f} "
                     f"{r['vram_peak_mib']:>9} {r['n_ok']:>3}/{r['n']}{flag}")
    per = [(r["cap_w"], efficiency_text(r.get("per_output"))) for r in res["rows"] if r.get("n_ok") and r.get("per_output")]
    if per:
        lines.append("  per output, median of the valid jobs (gross = Wh as measured; net18 = gross - 18 W x s):")
        lines += [f"  {cap:>5} W  {txt}" for cap, txt in per if txt]
    return lines


def summarize(ctx, results):
    """Print the table and the proposed lines; record the recommendations. Returns the printed lines (for tests)."""
    out = []
    needs = known_needs()
    gpu = ctx.state.get("gpu", {}).get("name", "?")
    section = re.sub(r"^NVIDIA (GeForce )?", "", gpu)
    prof, gate_lines, inform = [], [], []
    for res in results:
        t, need = res["task"], None
        out.append(f"\n== {t} ==")
        if res.get("error"):
            out.append(f"  not measured: {res['error']}")
        out += table_lines(res)
        for n in res["notes"]:
            out.append("  " + n)
        if res.get("ready_s") is not None:
            out.append(f"  ready after wake: {res['ready_s']} s; card use before the task {res['baseline_mib']:.0f} MiB")
        if t == "resolve" and res.get("cold_s") is not None:
            out.append(f"  cold start to the first tool answer {res['cold_s']} s (gate ready budget 120 s); idle VRAM with Resolve open +{res['idle_vram_mib']} MiB")
        if t == "effectcraft":
            if res.get("verdict") == "cpu_only":
                out.append("  verdict: CPU only, VRAM ~0: no gate lease and no profile needed")
            elif res.get("verdict"):
                out.append("  verdict: it used VRAM; do not treat it as CPU-only until looked at")
            ctx.record({"kind": "recommend", "task": t, "verdict": res.get("verdict")})
            continue
        pick, why = recommend(res["rows"])
        if pick:
            out.append(f"  recommended cap: {pick['cap_w']} W ({why})")
            if pick.get("per_output"):
                out.append(f"  per output at {pick['cap_w']} W: {efficiency_text(pick['per_output'])}")
            prof.append(f"{t} = {pick['cap_w']}")
        else:
            out.append(f"  recommended cap: none ({why})")
        if res.get("vram_peak_mib") is not None and res.get("baseline_mib") is not None:
            need = vram_need_mb(res["vram_peak_mib"], res["baseline_mib"])
            was = needs.get(t)
            dyn = t in DYNAMIC_VRAM
            out.append(f"  VRAM peak {res['vram_peak_mib']:.0f} MiB - {res['baseline_mib']:.0f} MiB before = {res['vram_peak_mib'] - res['baseline_mib']:.0f} MiB; need + 15 % = {need} MB"
                       + (f" (gate.py now {was})" if was is not None else "")
                       + (" -- INFORMATIVE ONLY: ComfyUI offloads dynamically (dynamic VRAM), so the peak is an upper bound and not the "
                          "need. Do not paste it into SERVICES; the gate's start thresholds are not peaks" if dyn else ""))
            if dyn:
                inform.append(f'{t}: peak-based {need} MB' + (f" (gate.py threshold {was})" if was is not None else ""))
            else:
                gate_lines.append(f'{t}: need {need} MB' + (f" (was {was})" if was is not None else ""))
        ctx.record({"kind": "recommend", "task": t, "cap_w": pick["cap_w"] if pick else None, "why": why,
                    "per_output": pick.get("per_output") if pick else None, "need_mb": need, "need_informative": t in DYNAMIC_VRAM})
    if ctx.gpu_unlock == "off":
        out.append("\nWARNING: gpu-unlock was off during this run; the imggen and vidgen profiles assume it is on, so do not "
                   "take their numbers (cap, Wh, speed) from this run.")
    elif ctx.gpu_unlock is not None and read_gpu_unlock(ctx.unlock_path) != ctx.gpu_unlock:
        out.append("\nWARNING: gpu-unlock changed during this run: compare the gpu_unlock field of the result lines.")
    out.append("\nProposed (nothing is edited):")
    out.append(f"  gpu-host/power_profiles.conf, section [{section}]:")
    out += [f"    {p}" for p in prof] or ["    (none)"]
    out.append("  gate/gate.py SERVICES, VRAM need in MB (fixed-memory services only):")
    out += [f"    {g}" for g in gate_lines] or ["    (none)"]
    if inform:
        out.append("  VRAM, informative only (dynamic VRAM: an upper bound, never for SERVICES):")
        out += [f"    {g}" for g in inform]
    try:
        print("\n".join(out), flush=True)
    except (OSError, ValueError):
        pass
    return out


# ------------------------------------------------------------------------------------------------------------------------ main
def build_parser():
    ap = argparse.ArgumentParser(description="Measure the power profile and VRAM of every gate task (run on the GPU host).")
    ap.add_argument("--tasks", help="comma list from: " + ",".join(ORDER) + " (default: " + ",".join(DEFAULT_TASKS) + ")")
    ap.add_argument("--recheck", action="store_true", help="also re-verify upscaler, transcoder, vidpost, imggen, vidgen")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the time estimate; touch nothing")
    ap.add_argument("--caps", help="watt caps for every task, e.g. 100,130,200 (default: 100,130,160,200,240; resolve and vidgen 100,130,170,240)")
    ap.add_argument("--reps", type=int, help="timed jobs per cap (default per task)")
    ap.add_argument("--wh", dest="wh_key", choices=["gross", "net18", "net"], default="gross",
                    help="Wh used by the recommendation: gross (avg W x s, the headline), net18 (gross - 18 W x s) or net (gross - the job's own "
                         "measured idle draw x s)")
    ap.add_argument("--gate", help="gate URL (default http://127.0.0.1:$GATE_PORT or 8700)")
    ap.add_argument("--allow-app", default=ALLOWED_APPS, help="regex of GPU processes allowed during the bench (small desktop ones)")
    ap.add_argument("--stt-secs", type=int, default=180, help="length of the Spanish clip for stt (default 180)")
    ap.add_argument("--img-quality", default="fast", help="imggen tier for --recheck (fast|better|photo)")
    ap.add_argument("--vid-secs", type=int, default=2, help="vidgen clip length for --recheck (2|3|5|8|10)")
    ap.add_argument("--effectcraft-gpu-eval", action="store_true", help="also run `effectcraft-cli bench --gpu --json` once, inside the bench only (" + EVAL_LABEL + ")")
    ap.add_argument("--eval-cap", type=int, default=130, help="cap for that evaluation")
    ap.add_argument("--keep-tmp", action="store_true", help="keep ~/bench_gate/tmp and ~/Videos/zz_bench")
    return ap


def parse_args(argv, home=None, videos=None):
    args = build_parser().parse_args(argv)
    args.wh_key = {"net": "gpu_net_wh", "net18": "gpu_net18_wh"}.get(args.wh_key, "gpu_wh")
    args.home = home or os.environ.get("BENCH_GATE_HOME") or os.path.join(os.path.expanduser("~"), "bench_gate")
    args.videos = videos or os.path.join(os.path.expanduser("~"), "Videos", "zz_bench")
    return args


def cleanup(ctx):
    if ctx.args.keep_tmp:
        return
    for d in (ctx.tmp, ctx.videos):
        if os.path.basename(d) in ("tmp", "zz_bench"):
            shutil.rmtree(d, ignore_errors=True)


def limit_back(ctx):
    """True when power.limit equals the value found before the bench (a service woken after /bench/end may legitimately set its own)."""
    end = ctx.now() + 20
    got = None
    while True:
        got = ctx.nv.limit_w()
        if got is not None and abs(got - ctx.found_w) <= 0.5:
            return True, got
        if ctx.now() > end:
            return False, got
        ctx.sleep(2)


def quiet_signals(sigs):
    """Ignore the given signals while the bench is being ended (only those this run handles)."""
    for sig in sigs:
        signal.signal(sig, signal.SIG_IGN)


def recover_bench_start(ctx, err):
    """/bench/start got no answer in time: the gate may have created the bench anyway. Read GET /state and end a bench that was
    started in the last START_RECOVER_S seconds, so the card is not held (and capped) until the TTL. Returns the exit code 3.
    The gate's state shows id, watts and start time of a bench but not its stack: a bench that young is ours, since the
    pre-flight saw none."""
    msg = f"bench start failed ({err})"
    try:
        code, st = ctx.gate.call("GET", "/state")
    except GateError:
        print(f"{msg}; the gate does not answer, so it is unknown whether a bench was created. Check GET /state and, if one "
              "exists, POST /bench/end (it expires by itself after GATE_BENCH_TTL_S).", file=sys.stderr)
        return 3
    b = st.get("bench") if code == 200 else None
    if b and b.get("stack", "bench") == "bench" and ctx.now() - float(b.get("started") or 0) <= START_RECOVER_S:
        try:
            endc, _ = ctx.gate.call("POST", "/bench/end", {"bench": b.get("id")})
        except GateError:
            endc = None
        print(f"{msg}; a bench ({b.get('id')}) had been created in the last {START_RECOVER_S} s, " +
              (f"ended it (HTTP {endc})." if endc is not None else "and ending it failed: POST /bench/end by hand."), file=sys.stderr)
    else:
        print(f"{msg}; no bench of this run exists on the gate.", file=sys.stderr)
    return 3


def main(argv=None, deps=None):
    deps = deps or {}
    args = parse_args(argv if argv is not None else sys.argv[1:], deps.get("home"), deps.get("videos"))
    names = select_tasks(args.tasks, args.recheck)
    if args.effectcraft_gpu_eval and "effectcraft" not in names:
        raise SystemExit("--effectcraft-gpu-eval belongs to the effectcraft task: add it to --tasks")
    if args.dry_run:
        print_plan(names, args)
        return 0
    env = deps.get("env") or load_host_env()
    token = env.get("GATE_TOKEN", "")
    if not token:
        print("no GATE_TOKEN in host.env or the environment", file=sys.stderr)
        return 2
    bench_token = env.get("GATE_BENCH_TOKEN", "")
    if not bench_token or bench_token == token:
        print("no GATE_BENCH_TOKEN (a value of its own, different from GATE_TOKEN) in host.env or the environment: the gate refuses "
              "/bench/* without it. Nothing was changed.", file=sys.stderr)
        return 2
    base = args.gate or f"http://127.0.0.1:{env.get('GATE_PORT', '8700')}"
    ctx = Ctx(args, deps.get("gate") or Gate(base, token, bench_token=bench_token), deps.get("nv") or Nvidia(), deps.get("measure") or real_measure, env,
              args.home, args.videos, sleep=deps.get("sleep", time.sleep), now=deps.get("now", time.time), media=deps.get("media"),
              mcp_factory=deps.get("mcp_factory"), resolve_dispatch=deps.get("resolve_dispatch"), run=deps.get("run", subprocess.run),
              unlock_path=deps.get("unlock_path", GPU_UNLOCK_TARGETS), cpu_dir=deps.get("cpu_dir", CPU_FREQ_DIR))

    # 1. pre-flight, read only
    try:
        code, state = ctx.gate.call("GET", "/state")
    except GateError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    if code != 200:
        print(f"refused: GET /state answered HTTP {code}", file=sys.stderr)
        return 2
    ctx.state = state
    apps = ctx.nv.compute_apps()
    why = preflight(state, apps, args.allow_app)
    if why:
        print("Pre-flight refused, nothing was changed:", file=sys.stderr)
        for w in why:
            print("  - " + w, file=sys.stderr)
        print("Run it in an idle window (see BENCH_GATE.md).", file=sys.stderr)
        return 2
    gpu = state.get("gpu", {})
    ctx.known_pids = set(pids_of(apps))                 # the desktop apps that passed the pre-flight: not foreign during the jobs
    ctx.static_env = {"driver": ctx.nv.driver(), "kernel": os.uname().release}
    ctx.gpu_unlock = read_gpu_unlock(ctx.unlock_path)
    ctx.found_w = float(gpu.get("limit_w") or ctx.nv.limit_w() or 0)
    ctx.cap_min, ctx.cap_max = gpu.get("min_w"), gpu.get("max_w")
    plan = {t: clamp_caps(caps_for(t, args), ctx.cap_min, ctx.cap_max) for t in names}
    log(f"card {gpu.get('name')}, limit {ctx.found_w:.0f} W (range {ctx.cap_min}-{ctx.cap_max}); tasks: {', '.join(names)}")
    log(f"gpu-unlock: {ctx.gpu_unlock}" + ("  (the imggen and vidgen profiles assume it is on)" if ctx.gpu_unlock == "off" else ""))

    # 2. bench start, then everything inside try/finally
    first_cap = next((plan[t][0] for t in names if t != "effectcraft" and plan[t]), int(ctx.found_w))

    def on_term(signum, frame):
        raise KeyboardInterrupt

    # SIGTERM, and SIGHUP like SIGTERM: a dropped SSH session must still end the bench (the gate would otherwise keep the cap
    # until its TTL). Installed before /bench/start, so a signal during the start is covered too. Under nohup SIGHUP is already
    # ignored: keep it ignored, the run goes on after the session drops (BENCH_GATE.md).
    old = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGHUP):
            if sig == signal.SIGHUP and signal.getsignal(sig) == signal.SIG_IGN:
                continue
            old[sig] = signal.signal(sig, on_term)

    def restore_signals():
        for sig, handler in old.items():
            signal.signal(sig, handler)

    try:
        code, r = ctx.gate.call("POST", "/bench/start", {"stack": "bench", "watts": first_cap}, timeout=BENCH_START_TIMEOUT)
    except (GateError, KeyboardInterrupt) as e:
        quiet_signals(old)
        try:
            return recover_bench_start(ctx, e if isinstance(e, GateError) else "interrupted")
        finally:
            restore_signals()
    if code != 200 or "bench" not in r:
        restore_signals()
        print(f"bench start refused: HTTP {code} {r.get('why', '')}", file=sys.stderr)
        return 3
    ctx.bench_id = r["bench"]
    results, rc = [], 0
    ctx.record({"kind": "session", "gpu": gpu, "found_w": ctx.found_w, "tasks": names, "plan": plan, "wh_rule": args.wh_key,
                "env": {**ctx.static_env, **cpu_policy(ctx.cpu_dir), "gpu_unlock": ctx.gpu_unlock},
                "wh_note": "gpu_wh is gross; gpu_net18_wh = gross - 18 W x s; gpu_net_wh = gross - the job's own measured idle W x s"})
    try:
        for t in names:
            ctx.task = t
            log(f"== task {t}: caps {fmt_cap_list(plan[t]) if t != 'effectcraft' and plan[t] else 'none (CPU only)'}")
            try:
                if t == "resolve":
                    res = run_resolve(ctx, plan[t], reps_for(t, args))
                elif t == "effectcraft":
                    res = run_effectcraft(ctx, reps_for(t, args))
                else:
                    res = run_service(ctx, t, SERVICE_PREPARE[t], plan[t], reps_for(t, args))
            except GateError as e:
                res = dict(result_shell(t), error=str(e))
            results.append(res)
            ctx.record({k: v for k, v in res.items() if k != "rows"})
            if res.get("error"):
                rc = 1
                log(f"task {t} stopped: {res['error']}")
            if res.get("interrupted"):
                log("run stopped, ending the bench; the remaining tasks were not started")
                break
    except KeyboardInterrupt:
        log("interrupted: ending the bench")
        rc = 1
    finally:
        quiet_signals(old)   # a second signal (terminal close then TERM) must not cut /bench/end short
        try:
            code, _ = ctx.gate.call("POST", "/bench/end", {"bench": ctx.bench_id})
            if code == 404:
                log("the bench was already gone on the gate (/bench/end: unknown_bench)")
            elif code != 200:
                log(f"warning: /bench/end answered HTTP {code}; the bench expires by itself (GATE_BENCH_TTL_S)")
        except GateError as e:
            log(f"warning: /bench/end failed: {e}")
        restore_signals()
        cleanup(ctx)
    back, got = limit_back(ctx)
    if back:
        log(f"power limit back at {got:.0f} W (before the bench: {ctx.found_w:.0f} W)")
    else:
        try:
            busy = [n for n, s in (ctx.refresh_state().get("services") or {}).items() if s.get("running")]
        except (TaskError, GateError):
            busy = []
        if busy:
            log(f"power limit is {got} W, not {ctx.found_w:.0f} W: {', '.join(busy)} started after the bench and the gate applies its profile (normal)")
        else:
            log(f"WARNING: power limit is {got} W, was {ctx.found_w:.0f} W before the bench, and nothing is running. "
                f"Check the gate (journalctl --user -u bridgeai-gate) and set it with: sudo -n /usr/bin/nvidia-smi -pl {ctx.found_w:.0f}")
            rc = rc or 4
    if results:
        summarize(ctx, results)
    return rc


if __name__ == "__main__":
    sys.exit(main())
