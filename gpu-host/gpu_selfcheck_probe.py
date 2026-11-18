#!/usr/bin/env python3
"""
gpu_selfcheck_probe -- the CUDA half of gpu_selfcheck.py. It runs INSIDE a throwaway container of an image that already has torch
(`docker run --rm --gpus all --network none --read-only ... python3 /probe.py`); the host side never imports torch.

It times three matrix multiplications on the same sizes, interleaved round by round so a clock or temperature drift hits all of
them alike, and prints one JSON line:

  fp16_fp32acc   fp16 inputs, FP32 accumulation   (what almost every model uses; torch's default for fp16 matmul)
  fp16_fp16acc   fp16 inputs, FP16 accumulation   (torch.backends.cuda.matmul.allow_fp16_accumulation)
  tf32           fp32 inputs on the TF32 tensor path (torch.backends.cuda.matmul.allow_tf32)

Why the ratio fp16_fp32acc / fp16_fp16acc answers "is the unlock active": GeForce Ampere cards run the tensor cores at half rate
when the accumulator is FP32 (NVIDIA's own limit on the consumer line) and at full rate with an FP16 accumulator. So on a stock
card the ratio is about 0.5 and on an unlocked card about 1.0, measured on the same card, in the same seconds, with the same
power cap. No stored baseline is needed. The TF32 ratio (tf32 / fp16_fp16acc) is the second witness: about 0.25 stock, 0.5 unlocked.

When this torch build cannot set allow_fp16_accumulation (an older torch or a cuBLAS without it), "fp16_fp16acc" and "tf32" ratios
are null and only the absolute TFLOPS of fp16_fp32acc are reported; the host side then compares them with a baseline file.
Matrix sizes are large enough to be compute-bound (a 4096 cube is 137 GFLOP, a few ms): the run is a few seconds, the torch
import and the CUDA context dominate.

Exit 0 and a JSON line with "error" absent; exit 3 and {"error": "..."} when it cannot run. Nothing is written to disk.
"""
import json
import statistics
import sys
import time

SIZES = (4096, 6144)       # square matmuls; compute-bound on any card of the families this is for
WARMUP = 5
ITERS = 20                 # timed matmuls per mode per size per round
ROUNDS = 5                 # interleaved rounds; the median of the rounds is taken
BUDGET_S = 25.0            # stop starting new rounds after this long (a cold, power-capped card is slower)
MODES = ("fp16_fp32acc", "fp16_fp16acc", "tf32")


def set_flags(torch, mode):
    """Select the accumulation mode; False when this build cannot (fp16_fp16acc on a torch without the flag)."""
    m = torch.backends.cuda.matmul
    try:
        m.allow_tf32 = mode == "tf32"
        if mode == "fp16_fp16acc":
            m.allow_fp16_accumulation = True
            return bool(m.allow_fp16_accumulation)
        if hasattr(m, "allow_fp16_accumulation"):
            m.allow_fp16_accumulation = False
        return True
    except (AttributeError, RuntimeError):
        return False


def time_matmul(torch, a, b, iters):
    """Milliseconds per matmul, measured with CUDA events around `iters` back-to-back launches."""
    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    torch.cuda.synchronize()
    start.record()
    for _ in range(iters):
        torch.matmul(a, b)
    end.record()
    torch.cuda.synchronize()
    return start.elapsed_time(end) / iters


def run(torch, clock=time.monotonic):
    t0 = clock()
    if not torch.cuda.is_available():
        return {"error": "no_cuda"}
    dev = torch.device("cuda", 0)
    props = torch.cuda.get_device_properties(0)
    supported = {m: set_flags(torch, m) for m in MODES}
    modes = [m for m in MODES if supported[m]]
    out = {"torch": str(torch.__version__), "cuda": str(getattr(torch.version, "cuda", None)), "device": props.name,
           "capability": list(torch.cuda.get_device_capability(0)), "fp16acc_supported": supported["fp16_fp16acc"],
           "sizes": list(SIZES)}
    tflops = {m: [] for m in modes}
    rounds = 0
    for n in SIZES:
        h = torch.randn(n, n, device=dev, dtype=torch.float16)
        f = torch.randn(n, n, device=dev, dtype=torch.float32)
        ops = {m: (f, f) if m == "tf32" else (h, h) for m in modes}
        for m in modes:                                    # warm-up: kernels selected, clocks up
            set_flags(torch, m)
            for _ in range(WARMUP):
                torch.matmul(*ops[m])
        torch.cuda.synchronize()
        per = {m: [] for m in modes}
        for _ in range(ROUNDS):
            if clock() - t0 > BUDGET_S and per[modes[0]]:
                break
            for m in modes:                                # interleaved: a, b, c, a, b, c ...
                set_flags(torch, m)
                per[m].append(time_matmul(torch, *ops[m], ITERS))
        rounds = max(rounds, len(per[modes[0]]))
        for m in modes:
            tflops[m].append(2.0 * n ** 3 / (statistics.median(per[m]) / 1e3) / 1e12)
        del h, f, ops
    t = {m: round(statistics.median(v), 2) for m, v in tflops.items()}
    out["tflops"] = {m: t.get(m) for m in MODES}
    base = t.get("fp16_fp16acc")
    out["ratio"] = round(t["fp16_fp32acc"] / base, 3) if base else None
    out["ratio_tf32"] = round(t["tf32"] / base, 3) if base and "tf32" in t else None
    out["rounds"], out["seconds"] = rounds, round(clock() - t0, 1)
    return out


def main():
    try:
        import torch
    except ImportError:
        print(json.dumps({"error": "no_torch"}))
        return 3
    try:
        res = run(torch)
    except Exception as e:                                 # a CUDA error must come back as data, not a traceback
        res = {"error": type(e).__name__}
    print(json.dumps(res))
    return 3 if "error" in res else 0


if __name__ == "__main__":
    sys.exit(main())
