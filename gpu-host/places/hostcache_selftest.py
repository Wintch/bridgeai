#!/usr/bin/env python3
"""Offline checks for the GPU caches of place.py (hostcache): which paths, links refused, the first move out of the home, a stale copy left by a
restore, a new GPU or driver, the mounts handed to docker, --clear and the daily rotation. Fake docker and nvidia-smi; run as the operator
(not root), so nothing changes owner. Run: python3 -I hostcache_selftest.py"""
import importlib.util, io, os, subprocess, sys, tempfile, contextlib
import atexit as _a, shutil as _s
tmp = tempfile.mkdtemp(prefix="hostcache-selftest-"); _a.register(_s.rmtree, tmp, True)
HERE = os.path.dirname(os.path.abspath(__file__))
root = os.path.join(tmp, "places"); os.makedirs(root)
fakebin = os.path.join(tmp, "bin"); os.makedirs(fakebin)
log = os.path.join(tmp, "docker.txt")
open(os.path.join(fakebin, "docker"), "w").write('#!/bin/sh\necho "$@" >> ' + log + '\n'
    '[ "$1" = network ] && [ "$2" = inspect ] && exit 0\n'
    '[ "$1" = inspect ] && { [ -n "$FAKE_RUNNING" ] && echo running || echo exited; exit 0; }\nexit 0\n')
open(os.path.join(fakebin, "nvidia-smi"), "w").write('#!/bin/sh\necho "${FAKE_GPU:-NVIDIA GeForce RTX 3060 Ti, 595.112.07}"\n')
for f in ("docker", "nvidia-smi"):
    os.chmod(os.path.join(fakebin, f), 0o755)
env = dict(os.environ, PLACES_ROOT=root, DOCKER=os.path.join(fakebin, "docker"), PLACE_BIND="10.9.8.7", TZ="UTC",
           PATH=fakebin + ":" + os.environ.get("PATH", "/usr/bin:/bin"), PLACE_LIBRARY_ROOTS=os.path.join(tmp, "libs"), PLACE_LOCK_SETTLE_S="0")
os.environ.update(env)
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def run(*args, e=None):
    return subprocess.run([sys.executable, "-I", os.path.join(HERE, "place.py"), *args], capture_output=True, text=True, env=e or env)


spec = importlib.util.spec_from_file_location("place", os.path.join(HERE, "place.py"))
place = importlib.util.module_from_spec(spec); spec.loader.exec_module(place)


def quiet(fn, *a, **k):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        v = fn(*a, **k)
    return v, out.getvalue()


def write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(text)


# ---- a games place with a Steam main library, a library in the home, one on the extra disk, a Heroic prefix and some traps
r = run("create", "hernew", "--gpu")
nh = os.path.join(root, "hernew", "desktop")
check("a new --gpu place starts with the cache links in its home, owned like the rest",
      r.returncode == 0 and os.readlink(os.path.join(nh, ".cache/nvidia")).startswith("/hostcache/") and os.path.isdir(os.path.join(root, "hostcache", "hernew")), r.stdout + r.stderr)
r = run("create", "hergam", "--gpu", e=dict(env, PLACE_HOSTCACHE="0"))     # a place made before the caches moved out
check("a --gpu place is created", r.returncode == 0, r.stdout + r.stderr)
home = os.path.join(root, "hergam", "desktop")
lib = os.path.join(tmp, "libs", "hergam"); os.makedirs(lib)
outside = os.path.join(tmp, "outside"); os.makedirs(os.path.join(outside, "steamapps", "shadercache"))
write(os.path.join(outside, "secret"), "do not touch")
vdf = '"libraryfolders"\n{\n "0" { "path" "/config/.steam/debian-installation" }\n "1" { "path" "/config/SteamLibrary" }\n' \
      ' "2" { "path" "/config/SteamLibraryExtra/SteamLibrary" }\n "3" { "path" "/etc" }\n "4" { "path" "/config/../../etc" }\n "5" { "path" "/config/Linked" }\n}\n'
write(os.path.join(home, ".steam/debian-installation/steamapps/libraryfolders.vdf"), vdf)
os.symlink(outside, os.path.join(home, "Linked"))
write(os.path.join(home, ".cache/nvidia/GLCache/a.bin"), "nv")
write(os.path.join(home, "SteamLibrary/steamapps/shadercache/12210/fozpipelinesv6/p.foz"), "foz")
write(os.path.join(home, ".steam/debian-installation/steamapps/shadercache/10090/x.foz"), "foz2")
os.makedirs(os.path.join(lib, "SteamLibrary/steamapps/common"))
os.makedirs(os.path.join(home, "Games/Heroic/Prefixes/Control/shadercache"))
write(os.path.join(home, "Games/Heroic/Prefixes/Control/shadercache/c.dxvk-cache"), "dx")

paths = place.cache_paths("hergam", lib)
want = {"/config/.cache/nvidia", "/config/.cache/mesa_shader_cache", "/config/.steam/debian-installation/steamapps/shadercache",
        "/config/SteamLibrary/steamapps/shadercache", "/config/SteamLibraryExtra/SteamLibrary/steamapps/shadercache",
        "/config/Games/Heroic/Prefixes/Control/shadercache"}
check("the cache paths: NVIDIA, Mesa, every Steam library's shadercache (home and extra disk) and the Heroic prefix", set(paths) == want, sorted(set(paths) ^ want))
check("a library path outside /config, with .., or through a link is never a cache path", not any(p.startswith("/etc") or "Linked" in p or ".." in p for p in paths), paths)
check("without the extra library its paths are left out", "/config/SteamLibraryExtra/SteamLibrary/steamapps/shadercache" not in place.cache_paths("hergam", None), "")

# a libraryfolders.vdf that is a link is not read
vdf_path = os.path.join(home, ".steam/debian-installation/steamapps/libraryfolders.vdf")
os.rename(vdf_path, vdf_path + ".real"); os.symlink(vdf_path + ".real", vdf_path)
check("a libraryfolders.vdf that is a link is not read", "/config/SteamLibrary/steamapps/shadercache" not in place.cache_paths("hergam", lib), "")
os.unlink(vdf_path); os.rename(vdf_path + ".real", vdf_path)

# ---- the first recreate moves the caches out of the home and leaves links at the same paths
r = run("recreate", "hergam", "--library", lib)
check("recreate of a --gpu place works and says the caches are on this host", r.returncode == 0 and "GPU shader caches on this host" in r.stdout, r.stdout + r.stderr)
check("it says caches were moved and links made", "moved out of the home" in r.stdout and "link(s) made" in r.stdout, r.stdout)
hc = os.path.join(root, "hostcache", "hergam")
c = [l for l in open(log).read().splitlines() if l.startswith("create --name hergamdoc")][-1]
binds = [x for x in c.split() if x.startswith("type=bind,")]
check("one mount only: hostcache/NAME at /hostcache, outside /config (the person cannot redirect it)",
      binds == [f"type=bind,source={hc},target=/hostcache"], binds)
slot = lambda p: os.path.join(hc, place.slot_name(p))
hp = lambda p: os.path.join(lib, p[len("/config/SteamLibraryExtra/"):]) if p.startswith("/config/SteamLibraryExtra/") else os.path.join(home, p[len("/config/"):])
check("every cache path in the home is now a link to /hostcache/<its folder>",
      all(os.path.islink(hp(p)) and os.readlink(hp(p)) == "/hostcache/" + place.slot_name(p) for p in want), [(p, os.path.islink(hp(p))) for p in want])
check("every link has its folder in hostcache/NAME", all(os.path.isdir(slot(p)) for p in want), os.listdir(hc))
check("the NVIDIA cache moved to its host folder", open(os.path.join(slot("/config/.cache/nvidia"), "GLCache/a.bin")).read() == "nv", "")
check("Steam's shader pre-caching of a home library moved too",
      open(os.path.join(slot("/config/SteamLibrary/steamapps/shadercache"), "12210/fozpipelinesv6/p.foz")).read() == "foz", "")
check("the Heroic prefix's DXVK cache moved too", os.path.isfile(os.path.join(slot("/config/Games/Heroic/Prefixes/Control/shadercache"), "c.dxvk-cache")), "")
check("a missing cache path on the extra disk gets its parents and its link", os.path.islink(os.path.join(lib, "SteamLibrary/steamapps/shadercache")), "")
check("nothing outside the place was touched through the link", open(os.path.join(outside, "secret")).read() == "do not touch" and not os.listdir(os.path.join(outside, "steamapps", "shadercache")), "")
kf = os.path.join(root, "hostcache", "hergam.gpu-key")
check("the GPU key is recorded beside the person's folder, not inside it", open(kf).read().strip() == "NVIDIA-GeForce-RTX-3060-Ti-595.112.07" and not os.path.exists(os.path.join(hc, ".gpu-key")), "")
check("hostcache/NAME is 0700 (the person's caches, nobody else's)", oct(os.stat(hc).st_mode & 0o777) == "0o700", oct(os.stat(hc).st_mode))

# ---- a second recreate changes nothing
before = sorted(os.listdir(hc))
r = run("recreate", "hergam")
check("a second recreate keeps the links and folders as they are", r.returncode == 0 and sorted(os.listdir(hc)) == before and "moved" not in r.stdout, r.stdout + r.stderr)

# ---- the person's own changes: a real folder again (an old snapshot restored), a link elsewhere, a link planted in their cache folder
os.unlink(hp("/config/.cache/nvidia")); write(os.path.join(home, ".cache/nvidia/GLCache/old.bin"), "stale")
os.unlink(hp("/config/.cache/mesa_shader_cache")); os.symlink(outside, hp("/config/.cache/mesa_shader_cache"))
os.symlink(outside, os.path.join(hc, "planted"))
r = run("recreate", "hergam", "--library", lib)
check("a real folder back in the home: dropped (the host copy wins), the link put back",
      r.returncode == 0 and os.path.islink(hp("/config/.cache/nvidia")) and os.path.isfile(os.path.join(slot("/config/.cache/nvidia"), "GLCache/a.bin"))
      and not os.path.exists(os.path.join(slot("/config/.cache/nvidia"), "GLCache/old.bin")), r.stdout + r.stderr)
check("a link to elsewhere is replaced by ours, never followed", os.readlink(hp("/config/.cache/mesa_shader_cache")).startswith("/hostcache/")
      and open(os.path.join(outside, "secret")).read() == "do not touch", "")
check("a link the person planted in their cache folder is removed, not followed", not os.path.lexists(os.path.join(hc, "planted")) and os.path.isdir(outside), "")

# ---- nvidia-smi failing never empties anything
write(os.path.join(slot("/config/.cache/nvidia"), "n.bin"), "n")
r = run("recreate", "hergam", "--library", lib, e=dict(env, FAKE_GPU="NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver"))
check("nvidia-smi not answering: caches kept, key kept, a warning", r.returncode == 0 and os.path.isfile(os.path.join(slot("/config/.cache/nvidia"), "n.bin"))
      and open(kf).read().strip().endswith("595.112.07") and "did not answer" in r.stderr, r.stdout + r.stderr)
r = run("prune", e=dict(env, FAKE_GPU=""))
check("prune with nvidia-smi silent empties nothing", os.path.isfile(os.path.join(slot("/config/.cache/nvidia"), "n.bin")), r.stdout + r.stderr)

# ---- a new driver empties the caches
r = run("recreate", "hergam", "--library", lib, e=dict(env, FAKE_GPU="NVIDIA GeForce RTX 3060 Ti, 600.1"))
check("a new driver: the caches start empty", r.returncode == 0 and "GPU or driver changed" in r.stdout and not os.listdir(slot("/config/.cache/nvidia")), r.stdout + r.stderr)
check("the new key is recorded", open(kf).read().strip().endswith("600.1"), "")

# ---- hostcache command
write(os.path.join(slot("/config/.cache/nvidia"), "n.bin"), "n")
r = run("hostcache", "hergam")
check("hostcache NAME shows the size and the key", r.returncode == 0 and "GPU caches" in r.stdout and "600.1" in r.stdout, r.stdout + r.stderr)
r = run("hostcache", "hergam", "--clear", e=dict(env, FAKE_RUNNING="1"))
check("--clear is refused while the place runs", r.returncode == 3 and os.path.isfile(os.path.join(slot("/config/.cache/nvidia"), "n.bin")), r.stdout + r.stderr)
r = run("hostcache", "hergam", "--clear")
check("--clear empties them when stopped, the folders stay", r.returncode == 0 and os.path.isdir(slot("/config/.cache/nvidia")) and not os.listdir(slot("/config/.cache/nvidia")), r.stdout + r.stderr)
check("hostcache is a reserved name, never a place", run("create", "hostcache").returncode == 2, "")
r = run("recreate", "hergam", e=dict(env, FAKE_RUNNING="1"))
check("recreate is refused while the place runs (nothing moved or emptied)", r.returncode == 3, r.stdout + r.stderr)

# ---- the daily prune rotates a stopped place's caches after a driver change; a running one waits
write(os.path.join(slot("/config/.cache/nvidia"), "n.bin"), "n")
r = run("prune", e=dict(env, FAKE_GPU="NVIDIA GeForce RTX 3090, 610.0", FAKE_RUNNING="1"))
check("prune leaves the caches of a running place alone", os.path.isfile(os.path.join(slot("/config/.cache/nvidia"), "n.bin")), r.stdout + r.stderr)
r = run("prune", e=dict(env, FAKE_GPU="NVIDIA GeForce RTX 3090, 610.0"))
check("prune empties a stopped place's caches built for another GPU", "GPU caches emptied" in r.stdout and not os.listdir(slot("/config/.cache/nvidia"))
      and open(kf).read().strip() == "NVIDIA-GeForce-RTX-3090-610.0", r.stdout + r.stderr)

# ---- a library path inside another cache path is dropped (no nested caches)
s = open(vdf_path).read().replace('"5" { "path" "/config/Linked" }', '"5" { "path" "/config/.cache/nvidia" }'); open(vdf_path, "w").write(s)
check("a library path inside a cache path is never a cache path", not any(p.startswith("/config/.cache/nvidia/") for p in place.cache_paths("hergam", lib)), place.cache_paths("hergam", lib))

# ---- a name that would add options to docker's --mount is never a cache path
os.makedirs(os.path.join(home, "Games/Heroic/Prefixes/x,source=_etc/shadercache"), exist_ok=True)
os.makedirs(os.path.join(home, "Games/Heroic/Prefixes/a:b/shadercache"), exist_ok=True)
check("a prefix name with a comma or a colon is never a cache path", not any("," in p or ":" in p for p in place.cache_paths("hergam", lib)), place.cache_paths("hergam", lib))

# ---- a folder for a path that is gone is emptied and removed at the next recreate
_s.rmtree(os.path.join(home, "Games/Heroic/Prefixes"))
gone = slot("/config/Games/Heroic/Prefixes/Control/shadercache")
r = run("recreate", "hergam", "--library", lib)
check("the folder of a cache path that no longer exists is removed", r.returncode == 0 and not os.path.exists(gone), r.stdout + r.stderr)

# ---- recreate holds the lock the gate honours, and refuses one left behind
lockf = os.path.join(root, ".hergam.restore-lock")
open(lockf, "w").close()
r = run("recreate", "hergam", "--library", lib)
check("recreate is refused while a restore (or another recreate) holds the place's lock", r.returncode == 3 and "is there" in r.stderr, r.stdout + r.stderr)
os.remove(lockf)
r = run("recreate", "hergam", "--library", lib)
check("a recreate leaves no lock behind", r.returncode == 0 and not os.path.exists(lockf), r.stdout + r.stderr)

# ---- the library's mount point in the home must be a real folder
sle = os.path.join(home, "SteamLibraryExtra")
_s.rmtree(sle, ignore_errors=True); os.symlink(outside, sle)
r = run("recreate", "hergam", "--library", lib)
check("recreate with a library is refused when SteamLibraryExtra in the home is a link", r.returncode == 3 and "link or a file" in r.stderr, r.stdout + r.stderr)
os.unlink(sle)

# ---- a library shared with another place: its cache paths are left alone
run("create", "herdos", "--gpu", "--library", lib)
before = os.readlink(os.path.join(lib, "SteamLibrary/steamapps/shadercache"))
os.unlink(os.path.join(lib, "SteamLibrary/steamapps/shadercache")); os.makedirs(os.path.join(lib, "SteamLibrary/steamapps/shadercache/9"))
r = run("recreate", "hergam", "--library", lib)
check("with a shared library, its shader cache is not moved or linked (the other place may be running)", r.returncode == 0 and "shared with herdos" in r.stdout
      and os.path.isdir(os.path.join(lib, "SteamLibrary/steamapps/shadercache/9")) and not os.path.islink(os.path.join(lib, "SteamLibrary/steamapps/shadercache")), r.stdout + r.stderr)
check("the home's own caches still are", os.path.islink(hp("/config/.cache/nvidia")), "")

# ---- off switch, places without a GPU, a removed place
r = run("recreate", "hergam", e=dict(env, PLACE_HOSTCACHE="0"))
c = open(log).read().splitlines()[-1]
check("PLACE_HOSTCACHE=0: no cache mount", r.returncode == 0 and "--mount" not in c, c)
run("create", "herweb")
r = run("recreate", "herweb")
c = open(log).read().splitlines()[-1]
check("a place without --gpu gets no cache mount and no hostcache folder", "--mount" not in c and not os.path.exists(os.path.join(root, "hostcache", "herweb")), c)
os.makedirs(os.path.join(root, "hostcache", "hergone", "x")); open(os.path.join(root, "hostcache", "hergone.gpu-key"), "w").write("k\n")
r = run("prune")
check("prune removes the caches of a place whose folder is gone", not os.path.exists(os.path.join(root, "hostcache", "hergone"))
      and not os.path.exists(os.path.join(root, "hostcache", "hergone.gpu-key")) and os.path.isdir(hc), r.stdout + r.stderr)

print("hostcache_selftest: " + ("all ok" if not fails else f"{len(fails)} FAILED"))
sys.exit(1 if fails else 0)
