#!/usr/bin/env python3
"""Offline checks for host_caps.py (REQUIREMENTS.md): the CPU level from flags and missing() against made-up hosts. Run: python3 -I host_caps_selftest.py"""
import importlib.util, os, sys

spec = importlib.util.spec_from_file_location("host_caps", os.path.join(os.path.dirname(os.path.abspath(__file__)), "host_caps.py"))
hc = importlib.util.module_from_spec(spec); spec.loader.exec_module(hc)
FAIL = []


def chk(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


V1 = ["fpu", "sse", "sse2", "cx8"]
V2 = V1 + sorted(hc.LEVELS["x86-64-v2"])
V3 = V2 + sorted(hc.LEVELS["x86-64-v3"])
chk("level: an old CPU without SSE4.2 is v1", hc.cpu_level(V1), "x86-64-v1")
chk("level: SSE4.2 and POPCNT make v2", hc.cpu_level(V2), "x86-64-v2")
chk("level: AVX2, BMI2, FMA make v3", hc.cpu_level(V3), "x86-64-v3")
chk("level: AVX2 without the v2 flags is still v1 (levels build on each other)", hc.cpu_level(V1 + sorted(hc.LEVELS["x86-64-v3"])), "x86-64-v1")
gpu_host = {"arch": "amd64", "cpu": "x86-64-v3", "cpu_flags": ["avx2"], "ram_gb": 31.3, "userns": True,
            "gpus": [{"vendor": "nvidia", "vram_gb": 8.0, "driver": "595.112.07", "encoder": "nvenc"}]}
old_vm = {"arch": "amd64", "cpu": "x86-64-v1", "cpu_flags": [], "ram_gb": 0.9, "userns": True, "gpus": []}
steam = {"arch": "amd64", "cpu": "x86-64-v3", "gpu": "nvidia", "vram_gb": 4, "encoder": "nvenc", "userns": True, "ram_gb": 8}
chk("missing: the games image fits the GPU host", hc.missing(steam, gpu_host), [])
chk("missing: on the old VM every gap is named", hc.missing(steam, old_vm),
    ["cpu x86-64-v3 (host x86-64-v1)", "an NVIDIA GPU", "4 GB of VRAM", "a nvenc video encoder", "8 GB of RAM (host 0.9)"])
chk("missing: a v1 service fits the old VM", hc.missing({"cpu": "x86-64-v1", "gpu": "none"}, old_vm), [])
chk("missing: gpu 'any' never blocks (a CPU fallback exists)", hc.missing({"gpu": "any"}, old_vm), [])
chk("missing: an older driver than needed", hc.missing({"driver_min": "600"}, gpu_host), ["NVIDIA driver 600 or newer"])
chk("missing: a flag by name", hc.missing({"cpu_flags": ["avx512f"]}, gpu_host), ["cpu flags avx512f"])
chk("missing: an unknown key or level is reported, never ignored", hc.missing({"tpu": 1, "cpu": "v9"}, gpu_host), ["unknown requirement 'tpu'", "cpu level 'v9' unknown"])
chk("missing: no requirement fits anywhere", hc.missing(None, old_vm), [])
print("host_caps_selftest: " + ("all ok" if not FAIL else "FAILED: " + "; ".join(FAIL)))
sys.exit(1 if FAIL else 0)
