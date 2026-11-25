#!/bin/sh
# gen-games-cdi.sh: run as root on the GPU host (install-games-profile.sh installs it as a boot service, bridgeai-games-cdi). Writes /etc/cdi/bridgeai-games.json:
# the host's NVIDIA driver as a CDI device `bridgeai.local/games=all` for a games place, differing from the stock nvidia.com/gpu one in two ways Steam needs:
#   1. no /proc/driver/nvidia/params override: that file mount over /proc makes the kernel refuse a fresh procfs, which bubblewrap (Steam runtime, Proton) must mount;
#   2. the 32-bit NVIDIA libraries (the toolkit leaves them out; 32-bit games, and Proton's 32-bit Vulkan/GL, need them).
# The libraries come from the host's own driver install, so the spec must be made again after a driver update (the boot service does; a place must be recreated
# only if Docker refuses to start it because a bind source disappeared).
set -eu
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
OUT=${1:-/etc/cdi/bridgeai-games.json}
TMP=$(mktemp --suffix=.json); trap 'rm -f "$TMP"' EXIT
nvidia-ctk cdi generate --vendor bridgeai.local --class games --format json --disable-hook disable-device-node-modification --output "$TMP" >/dev/null 2>&1
python3 - "$TMP" "$OUT" <<'PY'
import glob, json, os, sys
spec = json.load(open(sys.argv[1]))
libs = sorted(p for pat in ("*nvidia*", "libcuda*", "libGLX_*", "libEGL_*", "libnvcuvid*", "libnvoptix*") for p in glob.glob("/usr/lib/i386-linux-gnu/" + pat)
              if os.path.isfile(p) and "/mesa" not in p)
libs = sorted(set(libs))
edits = spec.setdefault("containerEdits", {})
mounts = edits.setdefault("mounts", [])
for p in libs:
    mounts.append({"hostPath": p, "containerPath": p, "options": ["ro", "nosuid", "nodev", "bind"]})
for h in edits.get("hooks", []):          # the cache must also learn the 32-bit directory
    a = h.get("args", [])
    if "update-ldcache" in a and "--folder" in a:
        a += ["--folder", "/usr/lib/i386-linux-gnu"]
        break
tmp = sys.argv[2] + ".new"
json.dump(spec, open(tmp, "w"), indent=1)
os.chmod(tmp, 0o644)
os.replace(tmp, sys.argv[2])
print(f"{sys.argv[2]}: {len(libs)} 32-bit NVIDIA libraries added")
PY
