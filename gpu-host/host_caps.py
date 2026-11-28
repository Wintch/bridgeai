#!/usr/bin/env python3
"""What this host provides to containers, and what an image needs that it lacks (REQUIREMENTS.md). Standard library only: runs on the oldest host.

  host_caps.py                      this host's capabilities as JSON
  host_caps.py check IMAGE...       for each local image: its org.bridgeai.requires label against this host (exit 1 when one does not fit)
  host_caps.py check-json '{"cpu": "x86-64-v3", "gpu": "nvidia"}'   the same for a requirement given by hand

`missing(requires, provides)` is pure: the list of what is missing, empty when the host fits.
"""
import json, os, re, subprocess, sys

LEVELS = {  # the flags each x86-64 micro-architecture level adds (psABI), as /proc/cpuinfo names them
    "x86-64-v2": {"cx16", "lahf_lm", "popcnt", "sse4_1", "sse4_2", "ssse3"},
    "x86-64-v3": {"avx", "avx2", "bmi1", "bmi2", "f16c", "fma", "abm", "movbe", "xsave"},
    "x86-64-v4": {"avx512f", "avx512bw", "avx512cd", "avx512dq", "avx512vl"},
}
ORDER = ["x86-64-v1", "x86-64-v2", "x86-64-v3", "x86-64-v4"]
LABEL = "org.bridgeai.requires"


def cpu_level(flags):
    """The highest level whose flags (and every lower level's) are all present. Pure."""
    level = "x86-64-v1"
    have = set(flags)
    for lv in ORDER[1:]:
        if LEVELS[lv] <= have:
            level = lv
        else:
            break
    return level


def run(argv, timeout=10):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def provides():
    flags, model = [], ""
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("flags") and not flags:
                flags = line.split(":", 1)[1].split()
            elif line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
    except OSError:
        pass
    mem = 0
    try:
        mem = int(re.search(r"MemTotal:\s+(\d+)", open("/proc/meminfo").read()).group(1)) / 1048576
    except (OSError, AttributeError):
        pass
    gpus = []
    for line in run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version,encoder.stats.sessionCount", "--format=csv,noheader,nounits"]).splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 3:
            gpus.append({"vendor": "nvidia", "model": p[0], "vram_gb": round(float(p[1]) / 1024, 1) if p[1].replace(".", "").isdigit() else None,
                         "driver": p[2], "encoder": "nvenc"})
    try:
        userns = open("/proc/sys/kernel/unprivileged_userns_clone").read().strip() != "0"
    except OSError:
        userns = os.path.exists("/proc/self/ns/user")
    return {"arch": {"x86_64": "amd64", "aarch64": "arm64"}.get(os.uname().machine, os.uname().machine), "cpu": cpu_level(flags),
            "cpu_model": model, "cpu_flags": sorted(set(flags) & {"avx", "avx2", "avx512f", "sse4_2", "fma", "aes", "sha_ni"}),
            "cores": os.cpu_count(), "ram_gb": round(mem, 1), "gpus": gpus, "userns": userns,
            "virt": run(["systemd-detect-virt"]).strip() or "none"}


def missing(req, prov):
    """What `prov` (provides()) lacks for `req` (an image's requires), as short reasons. Pure. An unknown key is reported, never ignored."""
    out = []
    req = req or {}
    for k, v in req.items():
        if k == "arch":
            if v != prov.get("arch"):
                out.append(f"arch {v} (host {prov.get('arch')})")
        elif k == "cpu":
            if v not in ORDER:
                out.append(f"cpu level {v!r} unknown")
            elif ORDER.index(v) > ORDER.index(prov.get("cpu", "x86-64-v1")):
                out.append(f"cpu {v} (host {prov.get('cpu')})")
        elif k == "cpu_flags":
            lack = [f for f in v if f not in prov.get("cpu_flags", [])]
            if lack:
                out.append("cpu flags " + ",".join(lack))
        elif k == "gpu":
            g = prov.get("gpus") or []
            if v == "nvidia" and not any(x.get("vendor") == "nvidia" for x in g):
                out.append("an NVIDIA GPU")
        elif k == "vram_gb":
            if not any((x.get("vram_gb") or 0) >= v for x in prov.get("gpus") or []):
                out.append(f"{v} GB of VRAM")
        elif k == "driver_min":
            if not any(int(str(x.get("driver", "0")).split(".")[0] or 0) >= int(v) for x in prov.get("gpus") or []):
                out.append(f"NVIDIA driver {v} or newer")
        elif k == "encoder":
            if not any(x.get("encoder") == v for x in prov.get("gpus") or []):
                out.append(f"a {v} video encoder")
        elif k == "ram_gb":
            if (prov.get("ram_gb") or 0) < v:
                out.append(f"{v} GB of RAM (host {prov.get('ram_gb')})")
        elif k == "userns":
            if v and not prov.get("userns"):
                out.append("unprivileged user namespaces")
        else:
            out.append(f"unknown requirement {k!r}")
    return out


def image_requires(image):
    out = run(["docker", "image", "inspect", "-f", "{{json .Config.Labels}}", image])
    try:
        return json.loads((json.loads(out) or {}).get(LABEL) or "null")
    except ValueError:
        return None


def main(argv):
    prov = provides()
    if not argv:
        print(json.dumps(prov, indent=1))
        return 0
    if argv[0] == "check-json":
        lack = missing(json.loads(argv[1]), prov)
        print("fits" if not lack else "missing: " + "; ".join(lack))
        return 1 if lack else 0
    if argv[0] == "check":
        bad = 0
        for img in argv[1:]:
            req = image_requires(img)
            if req is None:
                print(f"{img}: no {LABEL} label (requirements not declared)")
                continue
            lack = missing(req, prov)
            print(f"{img}: " + ("fits" if not lack else "MISSING " + "; ".join(lack)))
            bad += bool(lack)
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
