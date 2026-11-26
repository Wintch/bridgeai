#!/usr/bin/env python3
"""A person's own desktop place on a GPU host: one container (the webtop in Dockerfile.place), one volume folder, one pair of LAN ports, a secret nobody prints.

  place.py create NAME [--image IMG] [--bind IP] [--gpu] [--ports A B]   makes the folders, a password (kept 0600, never printed), the container (NOT started)
  place.py start|stop|status NAME [--force]                the container only; a place starts stopped and is started on request. stop refuses while a
                                                           game is open in the place (GAME_PROCS) unless --force: updates wait for the game to close
  place.py creds NAME                                      the path of the credentials file (never the password)
  place.py rm NAME                                         removes the container; the person's files stay (delete the folder by hand)
  place.py recreate NAME [--image IMG] [--bind IP] [--gpu|--no-gpu] [--udp PORT]... [--no-udp]   removes the container and makes it again from the saved settings (same folders, ports, login)
  place.py create|recreate NAME ... --sunshine BASE | --no-sunshine   a Moonlight stream of the place's own desktop (image Dockerfile.sunshine): Sunshine on its own
                                                           ports BASE-5, BASE, BASE+21 (TCP) and BASE+9, +10, +11, +13 (UDP), published on the place's LAN address; BASE+1 (its admin
                                                           page) is never published. Keyboard and mouse go through X (XTEST) inside the container: it never gets /dev/uinput, which is the host's
  place.py create|recreate NAME ... --games | --no-games    a place for Steam games (image Dockerfile.steam): the narrow profile Steam's runtime and Proton need (user namespaces,
                                                           see install-games-profile.sh and PLACES.md "Games"). Still no capabilities, no sudo, no /dev/uinput
  place.py create|recreate NAME ... --library HOSTDIR | --no-library   one extra folder of the host for games (another disk), mounted read-write at
                                                           /config/SteamLibraryExtra; only a real folder under PLACE_LIBRARY_ROOTS (default /mnt/nvme-data/places),
                                                           owned by the person's uid: never a whole disk, never a link
  place.py kill-game NAME                                  force-closes a hung game in the place (its kill-game: Windows programs under Proton/Wine,
                                                           their Wine servers, the Quake engine); Steam and the desktop stay
  place.py hold NAME on|off                                the gate's idle clock never closes a held place (for a person who cannot reopen it yet,
                                                           e.g. without a bot): on until the operator says off
  place.py notify NAME TITLE BODY [--seconds N] [--normal]   a desktop notification in the person's running session (XFCE's own, top right): stays until
                                                           closed unless --seconds; urgent unless --normal. Write it in the person's language
  place.py pair NAME PIN                                   gives Sunshine the PIN Moonlight shows when pairing (asked inside the container, from localhost)
  place.py gate-token NAME [--rotate]                      makes the token the person's stack uses to open and close THIS place through the gate
                                                           (/place/*): kept 0600 in .gate.token, only its hash in .gate.hash (the gate reads that); never printed
  place.py snapshot NAME [--reason WORD]                   a read-only btrfs snapshot of the place's subvolume NAME into .snapshots/NAME/<UTC time>-<reason>
                                                           (reason: a-z, 0-9 and -, up to 24; default manual). Refused when NAME is not a btrfs subvolume
                                                           (the old ext4 layout) or not a place (no .desktop.env): nothing is copied there. Whether the place
                                                           was running is recorded beside it (<snapshot>.state): a snapshot of a running place is
                                                           crash-consistent, like a power cut; one of a stopped place is clean
  place.py snapshots NAME                                  lists the place's snapshots, newest first, with their reason, whether the place ran, and age
  place.py restore NAME SNAPSHOT [--force]                 puts the place back as it was in SNAPSHOT (a name as `snapshots` lists it), and says which kind of
                                                           snapshot it was. Refused while the place runs, is paused or restarts; --force unpauses and stops it
                                                           first, like stop --force. Holds PLACES_ROOT/.NAME.restore-lock meanwhile (the gate does not open
                                                           the place while it is there; a restore that fails half-way leaves it, and says so). Takes a
                                                           "before-restore" snapshot first, so a restore can itself be undone. The place's own settings, login,
                                                           ports and gate token (the dot files at the top of NAME/) stay as they are now: only the person's
                                                           files go back
  place.py hostcache NAME [--clear]                        the size of the place's GPU caches on this host (PLACES_ROOT/hostcache/NAME); --clear empties them
                                                           (refused while it runs). A --gpu place gets them at create, recreate and restore: hostcache/NAME is mounted
                                                           at /hostcache, and in the home the NVIDIA and Mesa caches, steamapps/shadercache of every Steam library
                                                           (Proton's DXVK and VKD3D caches too) and of every Heroic prefix are links to their folders there, so the
                                                           paths stay the same. Not in snapshots, never backed up or sent to another host; emptied when the GPU or
                                                           the driver changes. Never delete the folders by hand (the place would not start). PLACE_HOSTCACHE=0: off
                                                           (links already in a home then point nowhere until the next recreate with it on)
  place.py set-uid NAME                                    moves a place made before 2026-11-26 off uid 1000 (the operator's own account on the host) to its own
                                                           uid (3001 + its port slot, host account place-NAME without login): its home, input, output, extra library
                                                           and shader caches change owner (only what 1000 owned; never through a link), then it is recreated. The
                                                           place stopped; it holds the lock the gate honours. A new place gets its own uid at create
  place.py dedupe [--dry-run] [--if-needed] [--max-seconds N]   stores identical game files once on disk (duperemove, reflinks: each place keeps its own
                                                           file, a write copies it for that place only): files of 1 MB and up in every place's Steam libraries
                                                           (steamapps/common) and Heroic installs, never saves, prefixes or caches; read-only opens, idle priority. Only
                                                           with every place stopped, the whole run (a place that starts stops it within 2 s). Disk only, not memory.
                                                           It runs in the host's "before sleep" window (gpu-host-sleep before.d, with --if-needed: nothing when no game
                                                           changed since the last complete run; --max-seconds: cut, and no new try for 12 h). It never wakes the host
  place.py prune [--days N]                                deletes snapshots older than N days (PLACE_SNAPSHOT_DAYS, default 7) of every place, never the
                                                           newest one of a place that still exists (a removed place's go after N days too). A place whose
                                                           restore lock is there is left alone. bridgeai-places-snapshot.timer runs a daily snapshot of every place and this

Layout (PLACES_ROOT, default /srv/bridgeai/places): NAME/desktop (the webtop's /config: the person's home), NAME/input and NAME/output (files in and out),
NAME/.desktop.env (CUSTOM_USER and PASSWORD, 0600), NAME/.ports ("3010 3011"). Ports are bound to one LAN address only (PLACE_BIND or --bind), never to
0.0.0.0: the way in from the internet is a separate, on-demand door (PLACES.md). The container runs with no-new-privileges, a 1 GB /dev/shm (browsers need
it) and restart=no, like the operator's own. The container, its hostname and its network interface on the host are all NAMEdoc. Each place has its OWN docker network (NAMEdoc-net, a /24 of 172.30.0.0/16) and memory/CPU/process limits (PLACE_MEM 9g, PLACE_CPUS 5, PLACE_PIDS 4096); what a place may reach is decided by places-net.sh. `--gpu` adds the NVIDIA runtime for Resolve; GPU use still goes through the GPU gate's rules.
Snapshots (on the btrfs disk mounted at PLACES_ROOT, one subvolume per place): PLACES_ROOT/.snapshots/NAME/, 0700, read-only snapshots. They cost no
writes when taken; only what changes afterwards takes new space. On that disk `create` makes the place's folder a subvolume of its own. The name
"library" and "hostcache" are reserved: PLACES_ROOT/library is the subvolume of the extra games libraries, PLACES_ROOT/hostcache the GPU caches.
Stdlib only. DOCKER overrides the docker binary (the selftest uses a fake one); btrfs is found on PATH (BTRFS overrides it)."""
import argparse, hashlib, json, os, re, secrets, stat, string, subprocess, sys, time
from datetime import datetime, timedelta, timezone

ROOT = os.environ.get("PLACES_ROOT", "/srv/bridgeai/places")
DOCKER = os.environ.get("DOCKER", "docker")
NAME_OK = re.compile(r"[a-z][a-z0-9]{1,11}")     # NAME + "doc" is the container, the hostname and the network interface (15 characters at most)
LIBRARY_ROOTS = os.environ.get("PLACE_LIBRARY_ROOTS", "/mnt/nvme-data/places")
LIBRARY_MOUNT = "/config/SteamLibraryExtra"
GAMES_SECCOMP = os.environ.get("PLACE_GAMES_SECCOMP", "/etc/bridgeai/places/seccomp-games.json")
GAMES_APPARMOR = "bridgeai-place-games"
GAMES_CDI_DEVICE = "bridgeai.local/games=all"   # /etc/cdi/bridgeai-games.json, written by gen-games-cdi.sh
BASE_PORT, STEP = 3010, 10                      # 3000/3001 belong to the first place; each new one takes the next pair of tens
LEGACY_UID = 1000                               # the uid every place used before 2026-11-26: on the host it is the operator's own account
UID_BASE, UID_MAX = 3001, 3999                  # a place's own uid: 3001 for the first port pair, then one per pair; never a host login
GATE_GID = int(os.environ.get("PLACE_GATE_GID", "1000"))   # the gate's group: it fills NAME/input and reads NAME/output on the host
HOSTCACHE = "hostcache"                         # PLACES_ROOT/hostcache/NAME: the place's GPU caches on this host (no snapshots, never sent, see "GPU caches")
RESERVED = ("library", HOSTCACHE)               # PLACES_ROOT/library holds the extra games libraries on the btrfs disk (BTRFS_MIGRATION.md)


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def is_place_name(n):
    return bool(NAME_OK.fullmatch(n or "")) and n not in RESERVED


def pdir(name):
    if not NAME_OK.fullmatch(name or ""):
        die("a place name is 2 to 12 lowercase letters and digits, starting with a letter")
    if name in RESERVED:
        die(f'"{name}" is reserved (the subvolume of the extra games libraries), not a place')
    return os.path.join(ROOT, name)


def container(name):
    """NAMEdoc: the container, its hostname and its network interface on the host all carry it, so `docker ps`, a shell prompt and the firewall's counters
    name the same thing."""
    return f"{name}doc"


def legacy_container(name):
    return f"place-{name}-desktop"               # the name before 2026-11-25; recreate removes it


def used_ports():
    used = set()
    try:
        for n in os.listdir(ROOT):
            try:
                used.update(int(x) for x in open(os.path.join(ROOT, n, ".ports")).read().split())
            except (OSError, ValueError):
                pass
    except OSError:
        pass
    return used


def next_ports():
    used = used_ports()
    p = BASE_PORT
    while p in used or p + 1 in used:
        p += STEP
    return p, p + 1


def bind_address(arg=None, env=None):
    """The one LAN address the ports are bound to: --bind, PLACE_BIND, or the host's first private IPv4. Never 0.0.0.0, never a public one."""
    env = os.environ if env is None else env
    addr = arg or env.get("PLACE_BIND")
    if not addr:
        try:
            out = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=5).stdout
            addr = next((m.group(1) for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)/", out) if re.match(r"(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", m.group(1))), None)
        except (OSError, subprocess.SubprocessError):
            addr = None
    if not addr or not re.fullmatch(r"(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)\d+\.\d+(\.\d+)?", addr):
        die("no private LAN address to bind the ports to: pass --bind ADDRESS, a private LAN address (a place is never published on every interface)")
    return addr


NET_POOL = "172.30"                              # one /24 per place inside 172.30.0.0/16: places-net.sh drops what leaves this range towards the LAN and the other places


def net_name(name):
    return f"{name}doc-net"


def legacy_net(name):
    return f"place-{name}-net"


def net_subnet(ports):
    """The place's own /24, from its port pair (3000 -> 172.30.0.0/24, 3010 -> .1.0/24, 3020 -> .2.0/24 ...): the same place always gets the same one."""
    k = (ports[0] - BASE_PORT) // STEP + 1
    if not 0 <= k <= 254:
        die(f"ports {ports[0]}/{ports[1]} do not map to a network of the pool")
    return f"{NET_POOL}.{k}.0/24"


def ensure_net(name, ports):
    """Every place lives alone in its own docker network (never the shared default bridge), so two places cannot see each other and the host firewall can tell them apart."""
    if subprocess.run([DOCKER, "network", "inspect", net_name(name)], capture_output=True, text=True).returncode == 0:
        return
    r = subprocess.run([DOCKER, "network", "create", "--driver", "bridge", "--subnet", net_subnet(ports), "--opt", "com.docker.network.bridge.enable_icc=false",
                        "--opt", f"com.docker.network.bridge.name={container(name)}", net_name(name)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die(f"docker could not create the network {net_name(name)}: {r.stderr.strip()[:300]}", 1)


def limits(env=None):
    """Memory, CPUs and process count a place may use, so a person's session cannot starve the host desktop or the other place (the card cannot be split: see PLACES.md)."""
    env = os.environ if env is None else env
    mem, cpus, pids = env.get("PLACE_MEM", "9g"), env.get("PLACE_CPUS", "5"), env.get("PLACE_PIDS", "4096")
    if not re.fullmatch(r"\d+[mg]", mem) or not re.fullmatch(r"\d+(\.\d+)?", cpus) or not re.fullmatch(r"\d+", pids):
        die("PLACE_MEM is like 9g, PLACE_CPUS like 5 or 2.5, PLACE_PIDS a number")
    return ["--memory", mem, "--memory-swap", mem, "--cpus", cpus, "--pids-limit", pids]


def place_uid(name):
    """The uid the place's person runs as (inside: user abc; on the host: account place-NAME, no login). A place made before 2026-11-26 still
    runs as 1000 until `place.py set-uid NAME`."""
    v = load_settings(name).get("uid")
    return v if isinstance(v, int) and UID_BASE <= v <= UID_MAX else LEGACY_UID


def uid_for_ports(ports):
    k = (ports[0] - BASE_PORT) // STEP + 1         # 3000 -> 0, 3010 -> 1 ... the same slot as the place's network
    if not 0 <= k <= UID_MAX - UID_BASE:
        die(f"ports {ports[0]}/{ports[1]} do not map to a uid of the pool")
    return UID_BASE + k


def own_areas(d, uid):
    """desktop is the person's alone (0750: their uid, their group). input and output are theirs too, with the gate's group and setgid (2770):
    the gate (the host user) streams files into input and reads exports from output on the host, and every file made there keeps that group."""
    if os.geteuid() != 0:
        return
    os.chown(os.path.join(d, "desktop"), uid, uid)
    os.chmod(os.path.join(d, "desktop"), 0o751)  # others may only pass through: the gate checks SteamLibraryExtra with lstat, never reads
    for sub in ("input", "output"):
        p = os.path.join(d, sub)
        os.chown(p, uid, GATE_GID)
        os.chmod(p, 0o2770)
        # everything already inside (exports, converted files, folders made by an older layout): the gate's group, group-writable,
        # folders setgid, so the gate can still read and delete them. find -P never follows a link; only the place is touched (stopped, locked).
        for cmd in (["-mindepth", "1", "(", "-type", "d", "-o", "-type", "f", ")", "-exec", "chgrp", "-h", str(GATE_GID), "{}", "+"],
                    ["-mindepth", "1", "-type", "d", "-exec", "chmod", "g+rwxs", "{}", "+"],
                    ["-mindepth", "1", "-type", "f", "-exec", "chmod", "g+rw", "{}", "+"]):
            subprocess.run(["find", "-P", p, "-xdev", *cmd], capture_output=True, text=True)


def chown_tree(path, old, new, group=True):
    """Gives NEW every file under PATH that belongs to OLD (the owner; the group too when GROUP), never following a link (-h, -P), never
    leaving the disk. Files of anyone else (root's, the gate's group) stay as they are."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return True
    if not stat.S_ISDIR(st.st_mode) or os.geteuid() != 0:
        return not stat.S_ISLNK(st.st_mode)
    ok = subprocess.run(["find", "-P", path, "-xdev", "-user", str(old), "-exec", "chown", "-h", str(new), "{}", "+"],
                        capture_output=True, text=True).returncode == 0
    if group:
        ok &= subprocess.run(["find", "-P", path, "-xdev", "-group", str(old), "-exec", "chgrp", "-h", str(new), "{}", "+"],
                             capture_output=True, text=True).returncode == 0
    return ok


def move_to_uid(name, old, new, library=None):
    """Every folder of the place from uid OLD to NEW: the home, input and output (their files keep the gate's group), the extra library and the
    shader caches. The place stopped and its lock held."""
    d = pdir(name)
    bad = [p for p, g in ((os.path.join(d, "desktop"), True), (os.path.join(d, "input"), False), (os.path.join(d, "output"), False),
                          (library, True), (os.path.join(ROOT, HOSTCACHE, name), True)) if p and not chown_tree(p, old, new, g)]
    own_areas(d, new)
    return bad


def ensure_account(name, uid):
    """Reserves UID on the host with a no-login account place-NAME (and its group), so `ls` and `ps` name it and no other account can take
    it. Refused when UID or the name belongs to something else. Skipped when not root (the selftest)."""
    import grp, pwd
    acct = f"place-{name}"
    try:
        u = pwd.getpwuid(uid)
        if u.pw_name != acct:
            die(f"uid {uid} already belongs to {u.pw_name}: not used for {name}", 3)
        return
    except KeyError:
        pass
    try:
        if pwd.getpwnam(acct).pw_uid != uid:
            die(f"{acct} exists with another uid: look at it first", 3)
    except KeyError:
        pass
    if os.geteuid() != 0:
        return
    try:
        if grp.getgrgid(uid).gr_name != acct:
            die(f"gid {uid} already belongs to the group {grp.getgrgid(uid).gr_name}: not used for {name}", 3)
    except KeyError:
        r = subprocess.run(["groupadd", "--gid", str(uid), acct], capture_output=True, text=True)
        if r.returncode != 0:
            die(f"could not make the group {acct}: {r.stderr.strip()[:200]}", 1)
    r = subprocess.run(["useradd", "--uid", str(uid), "--gid", str(uid), "--no-create-home", "--home-dir", "/nonexistent",
                        "--shell", "/usr/sbin/nologin", "--comment", f"desktop place {name}", acct], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"could not make the account {acct}: {r.stderr.strip()[:200]}", 1)


def check_library(path, env=None, uid=LEGACY_UID):
    """A host folder a place may get as an extra game library: an absolute, real (no link anywhere in it) directory strictly inside one of
    PLACE_LIBRARY_ROOTS, owned by the place's uid. Returns the path; refuses anything else."""
    if not path:
        return None
    roots = [r for r in (env or os.environ).get("PLACE_LIBRARY_ROOTS", LIBRARY_ROOTS).split(":") if r]
    if not os.path.isabs(path) or path != os.path.normpath(path) or os.path.realpath(path) != path or not os.path.isdir(path):
        die(f"--library takes an existing folder given by its real absolute path (no links): {path}")
    if not any(os.path.commonpath([path, r]) == os.path.normpath(r) and os.path.normpath(path) != os.path.normpath(r) for r in roots):
        die(f"--library must be a folder inside {':'.join(roots)} (PLACE_LIBRARY_ROOTS), never a whole disk")
    if os.geteuid() != 0:                        # the selftests run unprivileged: nothing can be given away, the caller's own uid stands in
        uid = os.getuid()
    if os.stat(path).st_uid != uid:
        die(f"{path} must belong to uid {uid} (the person inside the place): sudo chown -R -h {uid}:{uid} {path}")
    return os.path.normpath(path)


def games_options(env=None):
    """The security options of a games place: Docker's default seccomp profile plus user namespaces, an AppArmor profile that allows the mounts bubblewrap makes inside
    its own namespace, and an unmasked /proc (bubblewrap cannot mount a new one over Docker's masks). The profiles are installed on the host by install-games-profile.sh;
    without them the place is NOT created with weaker defaults, it is refused."""
    env = env or os.environ
    path = env.get("PLACE_GAMES_SECCOMP", GAMES_SECCOMP)
    cdi = env.get("PLACE_GAMES_CDI", "/etc/cdi/bridgeai-games.json")
    for need in (path, cdi):
        if not os.path.isfile(need):
            die(f"--games needs the host's profiles ({need} is missing): run install-games-profile.sh as root first", 3)
    return ["--security-opt", f"seccomp={path}", "--security-opt", f"apparmor={GAMES_APPARMOR}", "--security-opt", "systempaths=unconfined"]


# ---------------------------------------------------------------- GPU caches
# Shader caches depend on the GPU model and the driver, are rebuilt by the programs themselves, and are large (one games place: about 4 GB of
# Steam's per-game shader pre-caching). So they do not live in the person's home: they live in PLACES_ROOT/hostcache/NAME (a subvolume of its own
# on the btrfs disk, so the place's snapshots never hold them and a send to another host never carries them), mounted ONCE at /hostcache, a fixed
# path of the container's own filesystem that the person cannot replace. In the home, each cache path is a link to its folder there
# (~/.cache/nvidia -> /hostcache/.cache_nvidia-1a2b3c4d), made as the person: the paths the programs use stay the same. A mount target under
# /config was refused on purpose: the person controls /config and could turn a parent into a link while the place runs, and docker would follow
# it at the next start.
# Not backed up: `place.py hostcache NAME --clear` is always safe (the folders stay; deleting them by hand stops the place from starting).
# When the GPU or the driver changes, the caches of a stopped place are emptied (create/recreate, and prune daily).
CACHE_FIXED = ("/config/.cache",)              # all of ~/.cache (XDG: regenerable by definition): the NVIDIA and Mesa shader caches and the browsers' and Resolve's caches
STEAM_MAIN = "/config/.steam/debian-installation"
HEROIC_PREFIXES = "/config/Games/Heroic/Prefixes"
CACHE_MOUNT = "/hostcache"
CACHE_PATH_OK = re.compile(r"/config(/[A-Za-z0-9 ._+-]{1,120}){1,16}")   # no comma, colon, quote or newline
GPU_LINE_OK = re.compile(r"[^,\n]{2,80}, [0-9][0-9.]{1,20}")


def as_person(cmd, uid):
    """CMD run as the place's own uid, never as root, when it touches the person's files."""
    return ["setpriv", f"--reuid={uid}", f"--regid={uid}", "--clear-groups", *cmd] if os.geteuid() == 0 else list(cmd)


def gpu_key():
    """<gpu model>-<driver version> of this host as a file-name-safe word, or None when nvidia-smi does not answer properly (then nothing is
    emptied: a driver not ready yet after a wake must not look like a new GPU)."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    line = (r.stdout.strip().splitlines() or [""])[0].strip()
    if r.returncode != 0 or not GPU_LINE_OK.fullmatch(line):
        return None
    return re.sub(r"[^A-Za-z0-9.]+", "-", line).strip("-")


def safe_dir(base, rel, last_link_ok=False):
    """BASE/REL when no part of it below BASE is a link or a non-folder (missing parts are fine; the last part may be a link when
    LAST_LINK_OK); else None. The person controls what is under BASE: a link there must never send root anywhere else."""
    parts = [x for x in rel.split("/") if x]
    p = base
    for i, part in enumerate(parts):
        if part in (".", ".."):
            return None
        p = os.path.join(p, part)
        try:
            st = os.lstat(p)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode) and last_link_ok and i == len(parts) - 1:
            continue
        if not stat.S_ISDIR(st.st_mode):
            return None
    return p


def read_small(base, rel, limit=1 << 20):
    """A regular file under BASE (no link on the way, none at the end), or "" when it is not there."""
    p = safe_dir(base, os.path.dirname(rel))
    if not p:
        return ""
    try:
        fd = os.open(os.path.join(p, os.path.basename(rel)), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return ""
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            return ""
        return f.read(limit).decode("utf-8", "replace")


def host_path(name, cpath, library=None):
    """The host path behind a path inside the place: /config/... is the home, /config/SteamLibraryExtra/... the extra library (None without
    one). None for anything else or a path that goes through a link (the last part may be a link: ours)."""
    cpath = os.path.normpath(cpath)
    if cpath == LIBRARY_MOUNT or cpath.startswith(LIBRARY_MOUNT + "/"):
        return safe_dir(library, cpath[len(LIBRARY_MOUNT):], True) if library else None
    if cpath.startswith("/config/"):
        return safe_dir(os.path.join(pdir(name), "desktop"), cpath[len("/config"):], True)
    return None


def cache_paths(name, library=None):
    """Every GPU cache folder of the place, as paths inside it: the NVIDIA and Mesa caches, steamapps/shadercache of every Steam library
    (the main one and those in libraryfolders.vdf; Proton keeps DXVK's and VKD3D's caches there too), and the shadercache of every Heroic prefix
    already there. A path inside another one (or holding another one) is dropped. A library added later is covered at the next recreate."""
    home = os.path.join(pdir(name), "desktop")
    libs = [STEAM_MAIN]
    for vdf in ("steamapps/libraryfolders.vdf", "config/libraryfolders.vdf"):
        for m in re.finditer(r'"path"\s+"([^"\n]+)"', read_small(home, STEAM_MAIN[len("/config/"):] + "/" + vdf)):
            libs.append(os.path.normpath(m.group(1)))
    out = list(CACHE_FIXED) + [lib + "/steamapps/shadercache" for lib in libs]
    pre = safe_dir(home, HEROIC_PREFIXES[len("/config/"):])
    try:
        out += [f"{HEROIC_PREFIXES}/{p}/shadercache" for p in (sorted(os.listdir(pre)) if pre else [])
                if os.path.isdir(os.path.join(pre, p)) and not os.path.islink(os.path.join(pre, p))]
    except OSError:
        pass
    keep = []
    for c in out:
        if not CACHE_PATH_OK.fullmatch(c) or ".." in c.split("/") or c in keep or not host_path(name, c, library):
            continue
        if any(c.startswith(k + "/") or k.startswith(c + "/") for k in keep):
            continue
        keep.append(c)
    return keep


def slot_name(cpath):
    """The folder in hostcache/NAME for a path inside the place: readable, plus a short hash so two paths never share one."""
    tail = re.sub(r"[^A-Za-z0-9._-]+", "_", cpath[len("/config/"):])[-60:].strip("_.")
    return f"{tail}-{hashlib.sha256(cpath.encode()).hexdigest()[:8]}"


def make_parents_as_person(path, base, uid):
    """Creates the missing parents of PATH (under BASE), owned by the person. False when one is a link or not a folder."""
    p = base
    for part in os.path.relpath(os.path.dirname(path), base).split("/"):
        if part in ("", "."):
            continue
        p = os.path.join(p, part)
        if not os.path.lexists(p):
            os.mkdir(p, 0o755)
            if os.geteuid() == 0:
                os.chown(p, uid, uid, follow_symlinks=False)
        elif os.path.islink(p) or not os.path.isdir(p):
            return False
    return True


def empty_as_person(path, uid, also_itself=False):
    """Deletes what is inside PATH (and PATH itself when asked), as the place's uid, never following a link. True when it worked."""
    cmd = ["find", path, "-depth", "-delete"] if also_itself else ["find", path, "-mindepth", "1", "-delete"]
    return subprocess.run(as_person(cmd, uid), capture_output=True, text=True, cwd="/").returncode == 0


def empty_as_root(path):
    """What the person's uid could not delete in an old cache folder of their home: files a program run as root inside the place left there
    (one place had a root-owned ~/.cache/nvidia, unusable by the person too). Only from prepare_hostcache, with the place stopped and its
    lock held, on a path checked to have no link on the way; find -P never follows a link inside it, -xdev never leaves the disk."""
    st = os.lstat(path) if os.path.lexists(path) else None
    if st is None or not stat.S_ISDIR(st.st_mode) or os.geteuid() != 0:
        return st is None
    return subprocess.run(["find", "-P", path, "-xdev", "-depth", "-delete"], capture_output=True, text=True, cwd="/").returncode == 0


def hostcache_root(make=False):
    hc = os.path.join(ROOT, HOSTCACHE)
    if os.path.islink(hc):
        die(f"{hc} is a link: refused", 3)
    if make and not os.path.isdir(hc):
        if is_subvolume(ROOT):
            r = btrfs("subvolume", "create", hc)
            if r.returncode != 0:
                die(f"btrfs could not create the subvolume {hc}: {(r.stderr or r.stdout).strip()[:300]}", 1)
        else:
            os.mkdir(hc)
        os.chmod(hc, 0o711)                      # root's; each place's folder below it is the person's, 0700; the GPU keys stay root's here
    return hc


def library_mount_ok(name):
    """The extra library is mounted at /config/SteamLibraryExtra, inside the person's home: that folder must be a real folder (or absent), never
    a link, or docker would follow the link at start and mount the library somewhere else in the container. The gate checks the same before
    every start (place_control.py)."""
    p = os.path.join(pdir(name), "desktop", os.path.basename(LIBRARY_MOUNT))
    try:
        return stat.S_ISDIR(os.lstat(p).st_mode)
    except FileNotFoundError:
        return True


def library_sharers(name, library):
    """The other places whose saved settings use the same extra library."""
    if not library:
        return []
    out = []
    try:
        names = sorted(n for n in os.listdir(ROOT) if is_place_name(n) and n != name)
    except OSError:
        return []
    for n in names:
        try:
            with open(os.path.join(ROOT, n, ".settings.json")) as f:
                v = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(v, dict) and isinstance(v.get("library"), str) and os.path.normpath(v["library"]) == os.path.normpath(library):
            out.append(n)
    return out


def place_cache_dir(name, make=False):
    hc = hostcache_root(make)
    d = os.path.join(hc, name)
    if os.path.islink(d):
        die(f"{d} is a link: refused", 3)
    if make and not os.path.isdir(d):
        os.mkdir(d, 0o700)
        if os.geteuid() == 0:
            os.chown(d, place_uid(name), place_uid(name))
    return d


def key_file(name):
    """hostcache/NAME.gpu-key: root's, beside the person's folder, never inside it (the person can write in their folder)."""
    return os.path.join(ROOT, HOSTCACHE, name + ".gpu-key")


def real_slots(d):
    """The folders in hostcache/NAME that are real folders (a link the person made there is never entered: it is removed by the caller)."""
    try:
        return [s for s in sorted(os.listdir(d)) if os.path.isdir(os.path.join(d, s)) and not os.path.islink(os.path.join(d, s))]
    except OSError:
        return []


def empty_slots(name, d, only=None):
    uid = place_uid(name)
    bad = [s for s in real_slots(d) if (only is None or s in only) and not empty_as_person(os.path.join(d, s), uid)]
    if bad:
        print(f"warning: {name}: {len(bad)} cache folder(s) could not be emptied fully: {', '.join(bad[:3])}", file=sys.stderr)
    return not bad


def prepare_hostcache(name, library=None, env=None):
    """Called with the place stopped (create, recreate, restore). Makes hostcache/NAME and one folder per cache path, moves a cache already in
    the home there (a reflink copy on the same btrfs disk: no data written; as the person, never as root), and puts in the home a link from each
    cache path to /hostcache/<folder>. Empties every cache when the GPU or driver changed, and the folders of paths that no longer exist.
    Returns the mount for run_args ([] when off: PLACE_HOSTCACHE=0)."""
    if (env or os.environ).get("PLACE_HOSTCACHE", "1") == "0":
        return []
    d = place_cache_dir(name, make=True)
    uid = place_uid(name)
    key, kf = gpu_key(), key_file(name)
    old = read_small(os.path.dirname(kf), os.path.basename(kf)).strip()
    if key is None:
        print(f"warning: {name}: nvidia-smi did not answer: the shader caches are kept as they are", file=sys.stderr)
    elif old != key:
        if old:
            empty_slots(name, d)
            print(f"{name}: the GPU or driver changed ({old} -> {key}): its shader caches start empty")
        write_secret(kf, key + "\n", 0o644, replace=True)
    for s in os.listdir(d):                      # a link or a file the person left in their cache folder: removed, never followed
        p = os.path.join(d, s)
        if os.path.islink(p) or not os.path.isdir(p):
            os.unlink(p) if os.path.islink(p) or os.path.isfile(p) else None
    home = os.path.join(pdir(name), "desktop")
    paths, moved, linked = cache_paths(name, library), 0, 0
    sharers = library_sharers(name, library)
    if sharers:                                  # another place may be running on it: nothing is moved or linked there
        paths = [c for c in paths if not c.startswith(LIBRARY_MOUNT + "/")]
        print(f"{name}: the extra library is shared with {', '.join(sharers)}: its shader caches stay where they are")
    for cpath in paths:
        hp = host_path(name, cpath, library)
        base = library if cpath.startswith(LIBRARY_MOUNT + "/") else home
        s = slot_name(cpath)
        slot, want = os.path.join(d, s), f"{CACHE_MOUNT}/{s}"
        if not os.path.isdir(slot):
            os.mkdir(slot, 0o755)
            if os.geteuid() == 0:
                os.chown(slot, uid, uid)
        st = os.lstat(hp) if os.path.lexists(hp) else None
        if st and stat.S_ISLNK(st.st_mode):
            if os.readlink(hp) == want:
                continue
            os.unlink(hp)                        # a link elsewhere (or to an old folder name): ours replaces it
        elif st and stat.S_ISDIR(st.st_mode):
            if os.listdir(hp) and not os.listdir(slot):
                r = subprocess.run(as_person(["cp", "-a", "-T", "--reflink=auto", hp, slot], uid), capture_output=True, text=True, cwd="/")   # -T, no "/.": a source turned into a link is never followed
                if r.returncode == 0:
                    moved += 1
                    # links an older layout left inside (~/.cache/nvidia -> /hostcache/<old folder>) would point at folders removed below
                    subprocess.run(as_person(["find", slot, "-maxdepth", "1", "-type", "l", "-lname", CACHE_MOUNT + "/*", "-delete"], uid),
                                   capture_output=True, text=True, cwd="/")
                else:
                    print(f"warning: {name}: {cpath} could not be moved to its cache folder ({r.stderr.strip()[:160]}): it starts empty", file=sys.stderr)
                    empty_as_person(slot, uid)
            if not empty_as_person(hp, uid, also_itself=True) and not empty_as_root(hp):
                print(f"warning: {name}: {cpath} could not be cleared in the home: left as it is", file=sys.stderr)
                continue
        elif st:
            print(f"warning: {name}: {cpath} is not a folder in the home: left as it is", file=sys.stderr)
            continue
        if not make_parents_as_person(hp, base, uid):
            print(f"warning: {name}: a folder above {cpath} is a link or a file: no cache link there", file=sys.stderr)
            continue
        os.symlink(want, hp)
        if os.geteuid() == 0:
            os.chown(hp, uid, uid, follow_symlinks=False)
        linked += 1
    used = {slot_name(c) for c in paths}
    stale = [s for s in real_slots(d) if s not in used]
    if stale:
        empty_slots(name, d, stale)
        for s in stale:
            try:
                os.rmdir(os.path.join(d, s))
            except OSError:
                pass
    if moved or linked:
        print(f"{name}: shader caches on this host: {moved} moved out of the home, {linked} link(s) made in the home")
    return [(d, CACHE_MOUNT)]


def hostcache_info(name, clear=False):
    """Sizes of the place's GPU caches; --clear empties them (refused while the place runs or is paused)."""
    d = place_cache_dir(name)
    if not os.path.isdir(d):
        print(f"{name}: no GPU caches on this host (they are made at the next create or recreate)")
        return
    if clear:
        busy = running_containers(name)
        if busy is None or busy:
            die(f"{name} is running (or docker cannot tell): its caches are in use, not cleared", 3)
        ok = empty_slots(name, d)
        print(f"{name}: GPU caches emptied; the games rebuild them" if ok else f"{name}: GPU caches partly emptied (see the warning)")
        sys.exit(0 if ok else 1)
    r = subprocess.run(["du", "-sxP", "--block-size=1M", d], capture_output=True, text=True)
    key = read_small(os.path.join(ROOT, HOSTCACHE), name + ".gpu-key").strip() or "not set"
    print(f"{name}: GPU caches {(r.stdout.split() or ['?'])[0]} MB in {d} (built for {key}); not in snapshots, never backed up")


def rotate_caches():
    """For prune: a stopped place whose caches were built for another GPU or driver gets them emptied; the caches of a place whose folder is
    gone are removed. Nothing is emptied when nvidia-smi does not answer properly."""
    hc = os.path.join(ROOT, HOSTCACHE)
    if os.path.islink(hc) or not os.path.isdir(hc):
        return
    key = gpu_key()
    for name in sorted(n for n in os.listdir(hc) if is_place_name(n)):
        d = os.path.join(hc, name)
        if os.path.islink(d) or not os.path.isdir(d):
            continue
        if os.path.lexists(restore_lock(name)):  # a restore or recreate is moving the place: its folder may look gone for a moment
            continue
        busy = running_containers(name)
        if busy is None or busy:
            continue
        pd = os.path.join(ROOT, name)
        if not os.path.isdir(pd) or os.path.islink(pd):
            if os.lstat(d).st_uid != 0 and empty_as_person(d, os.lstat(d).st_uid) and not os.rmdir(d):
                try:
                    os.unlink(key_file(name))
                except OSError:
                    pass
                print(f"{name}: the place is gone: its GPU caches were removed")
            continue
        old = read_small(hc, name + ".gpu-key").strip()
        if key is None or not old or old == key:
            continue
        empty_slots(name, d)
        write_secret(key_file(name), key + "\n", 0o644, replace=True)
        print(f"{name}: GPU caches emptied (built for {old}, this host is now {key})")


# ---------------------------------------------------------------- shared game files (dedupe)
# Identical game files of the places are stored once on disk: duperemove asks the kernel (FIDEDUPERANGE) to share the blocks of byte-identical
# files, which the kernel checks itself before sharing; each place keeps its own file (a reflink), and a game update or any write makes a new
# copy for that place only (copy-on-write). Disk only: two places running the same game still read it each (hardlinks would share memory too,
# but only inside one subvolume, and a writing game would write into everybody's copy: WEEKLY_COOP.md).
# Only game installs, files of 1 MB and up: every Steam library's steamapps/common (the main one, those in libraryfolders.vdf, the extra one)
# and every Heroic install (installed.json). Never saves, prefixes, settings, caches. Files are opened read-only (-A); block hashes, partial
# matches (the same game laid out differently on disk still shares). Every place stopped the whole run (see dedupe). Space shared with snapshots
# comes free when those snapshots expire. Known side effects: a person can tell with FIEMAP that another place has byte-identical game blocks
# (which games, versions); and a later `btrfs send` of a home whose library was deduped sends those files again (MULTI_HOST.md).
DEDUPE_HASHES = os.environ.get("PLACE_DEDUPE_HASHES", "/var/lib/bridgeai-places/dedupe.hash")
DEDUPE_MIN_BYTES = 1 << 20


def game_dirs(name, library=None):
    """Host folders holding the place's installed games (see above), each checked to have no link on the way."""
    home = os.path.join(pdir(name), "desktop")
    libs = [STEAM_MAIN]
    for vdf in ("steamapps/libraryfolders.vdf", "config/libraryfolders.vdf"):
        for m in re.finditer(r'"path"\s+"([^"\n]+)"', read_small(home, STEAM_MAIN[len("/config/"):] + "/" + vdf)):
            libs.append(os.path.normpath(m.group(1)))
    paths = [lib + "/steamapps/common" for lib in libs]
    try:
        inst = json.loads(read_small(home, ".config/heroic/legendaryConfig/legendary/installed.json") or "{}")
        paths += [v["install_path"] for v in inst.values() if isinstance(v, dict) and isinstance(v.get("install_path"), str)]
    except (ValueError, AttributeError):
        pass
    out = []
    for c in paths:
        c = os.path.normpath(c)
        if ".." in c.split("/") or not c.startswith("/config/"):
            continue
        hp = host_path(name, c, library)
        if hp and os.path.isdir(hp) and not os.path.islink(hp) and hp not in out:
            out.append(hp)
    return out


def games_changed_at(name, library=None):
    """When the place's installed games last changed: the newest Steam app manifest (appmanifest_*.acf, rewritten on every install and
    update) of its libraries and Heroic's installed.json, by ctime. 0 when none."""
    home = os.path.join(pdir(name), "desktop")
    newest = 0
    for d in game_dirs(name, library):
        steamapps = os.path.dirname(d)
        try:
            for f in os.listdir(steamapps):
                if f.startswith("appmanifest_") and f.endswith(".acf"):
                    newest = max(newest, os.lstat(os.path.join(steamapps, f)).st_ctime)   # ctime: a copy cannot set it back
        except OSError:
            pass
    p = safe_dir(home, ".config/heroic/legendaryConfig/legendary")
    try:
        newest = max(newest, os.lstat(os.path.join(p, "installed.json")).st_ctime) if p else newest
    except OSError:
        pass
    return newest


def dedupe(dry_run=False, if_needed=False, max_seconds=0, partial=True):
    """Shares the blocks of identical game files between and within the places (see above). Runs at idle priority; one run at a time.
    Only with every place stopped, the whole time: a person controls their home only through their running place, so with all of them stopped
    no folder can turn into a link between the listing and duperemove's reads. Docker is asked every 2 s; a place that starts (or a docker that
    cannot be asked) stops the run at once (each share is atomic: stopping leaves no file half-done).
    if_needed (the "before sleep" window, gpu-host-sleep's before.d): nothing when no game was installed or updated since the last complete run
    (newest ctime of the Steam app manifests and Heroic's installed.json), and nothing within 12 h of a run cut by its time.
    The hash file is made fresh for every run and deleted after: an old one would list paths a person may have turned into links since."""
    import fcntl
    names = []
    try:
        names = sorted(n for n in os.listdir(ROOT) if is_place_name(n) and os.path.isfile(os.path.join(ROOT, n, ".desktop.env")))
    except OSError:
        pass
    state = os.path.dirname(DEDUPE_HASHES)
    os.umask(0o077)                              # the hash file lists the people's game files: root's only
    os.makedirs(state, mode=0o700, exist_ok=True)
    stamp_file, cut_file = DEDUPE_HASHES + ".done", DEDUPE_HASHES + ".cut"

    def busy():
        out = []
        for n in names:
            r = running_containers(n)
            if r is None or r:
                out.append(n)
        return out

    if busy():
        print(f"dedupe: not now, {len(busy())} place(s) running (or docker cannot tell)")
        return
    if if_needed:
        newest = max([games_changed_at(n, load_settings(n).get("library")) for n in names] or [0])
        try:
            done = float(read_small(state, os.path.basename(stamp_file)).strip() or 0)
            cut = float(read_small(state, os.path.basename(cut_file)).strip() or 0)
        except ValueError:
            done = cut = 0
        if newest <= done:
            print("dedupe: nothing new since the last run")
            return
        if time.time() - cut < 12 * 3600:
            print("dedupe: the last run was cut by its time less than 12 h ago: next window")
            return
    root_real = os.path.realpath(ROOT)
    dirs, skipped = [], 0
    for n in names:
        for d in game_dirs(n, load_settings(n).get("library")):
            if os.path.realpath(d).startswith(root_real + "/"):
                dirs.append(d)
            else:
                skipped += 1                     # an extra library on another disk: blocks can only be shared on the same filesystem
    if not dirs:
        print("dedupe: no game folders in any place")
        return
    lockf = open(DEDUPE_HASHES + ".lock", "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        die("dedupe: another run is going", 3)
    files = []
    for d in dirs:                               # -P: the last part of a path is never followed; regular files of 1 MB and up
        r = subprocess.run(["find", "-P", d, "-xdev", "-type", "f", "-size", f"+{DEDUPE_MIN_BYTES - 1}c", "-print0"], capture_output=True)
        files += [f for f in r.stdout.decode("utf-8", "surrogateescape").split("\0") if f and "\n" not in f]
    size = sum(os.lstat(f).st_size for f in files if os.path.lexists(f))
    print(f"dedupe: {len(files)} game file(s) of 1 MB and up, {size / 1e9:.1f} GB, in {len(dirs)} folder(s) of {len(names)} place(s)"
          + (f"; {skipped} folder(s) on another disk left out" if skipped else ""))
    hashes = os.path.join(state, f"dedupe-{os.getpid()}.hash")
    cmd = ["nice", "-n", "19", "ionice", "-c", "3", os.environ.get("DUPEREMOVE", "duperemove"), "-A", "-h", "-q", "--skip-zeroes",
           f"--hashfile={hashes}"] + (["--dedupe-options=partial"] if partial else []) + ([] if dry_run else ["-d"]) + ["-"]
    started, why = time.time(), None
    errf = open(os.path.join(state, "dedupe.err"), "w+")
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=errf, stderr=subprocess.STDOUT)
    try:
        p.stdin.write("\n".join(files).encode("utf-8", "surrogateescape"))
        p.stdin.close()
        while p.poll() is None:
            try:
                p.wait(timeout=2)
                break
            except subprocess.TimeoutExpired:
                pass
            if busy():
                why = "a place started"
            elif max_seconds and time.time() - started > max_seconds:
                why = "its time is up"
            if why:
                p.send_signal(2)
                try:
                    p.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
                break
    finally:
        for f in (hashes, hashes + "-shm", hashes + "-wal", hashes + "-journal"):
            try:
                os.unlink(f)
            except OSError:
                pass
    errf.seek(0)
    out = errf.read().splitlines()
    errf.close()
    errors = [l for l in out if l.lower().startswith(("error", "failure", "dedupe error")) or "error" in l.lower()[:40]]
    summary = [l for l in out[-8:] if "/" not in l and l.strip()]
    print("\n".join(summary) or "dedupe: done")  # never a person's file names: lines with a path are left out
    if errors:
        print(f"dedupe: {len(errors)} error line(s) (details in {os.path.join(state, 'dedupe.err')}, root only)")
    if why:
        print(f"dedupe: stopped after {int(time.time() - started)} s: {why}; a later window does it again")
        if why == "its time is up":
            write_secret(cut_file, f"{time.time():.6f}\n", 0o600, replace=True)
        return
    if p.returncode != 0:
        die(f"dedupe: duperemove ended with {p.returncode}", 1)
    if not dry_run:
        write_secret(stamp_file, f"{started:.6f}\n", 0o600, replace=True)   # games changed after this start are seen by the next window


def run_args(name, image, bind, ports, gpu=False, env=None, udp=None, sunshine=None, games=False, library=None, caches=()):
    d = pdir(name)
    args = [DOCKER, "create", "--name", container(name), "--hostname", container(name), "--security-opt", "no-new-privileges", *(games_options(env) if games else []), "--shm-size", "1gb", "--restart", "no",
            "--network", net_name(name), *limits(env),
            "-p", f"{bind}:{ports[0]}:3000", "-p", f"{bind}:{ports[1]}:3001",
            *[x for p in check_udp(udp) for x in ("-p", f"{bind}:{p}:{p}/udp")],
            *[x for p in sunshine_ports(sunshine)[0] for x in ("-p", f"{bind}:{p}:{p}/tcp")],
            *[x for p in sunshine_ports(sunshine)[1] for x in ("-p", f"{bind}:{p}:{p}/udp")],
            "--env-file", os.path.join(d, ".desktop.env"),
            "-e", f"PUID={place_uid(name)}", "-e", f"PGID={place_uid(name)}", "-e", "UMASK=002",   # 002: the person's own group is private; in input/output (setgid) the gate can delete "-e", "TZ=" + (env or os.environ).get("TZ", "America/Argentina/Buenos_Aires"),
            "-e", "LANG=en_US.UTF-8", "-e", "LANGUAGE=en_US:en", "-e", "LC_ALL=en_US.UTF-8",
            "-v", f"{d}/desktop:/config", "-v", f"{d}/input:/input", "-v", f"{d}/output:/output"]
    for helper in ("to-resolve", "from-resolve"):    # the helpers come from this folder, read-only: a fix to one reaches every place at its next start, no 20 GB image rebuild
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", helper)
        if os.path.isfile(path):
            args += ["-v", f"{path}:/usr/local/bin/{helper}:ro"]
    if library:
        args += ["-v", f"{check_library(library, env, place_uid(name))}:{LIBRARY_MOUNT}"]
    for src, dst in caches:                      # hostcache/NAME at /hostcache: outside /config, so the person cannot redirect it
        args += ["--mount", f"type=bind,source={src},target={dst}"]
    if sunshine:
        args += ["--env-file", os.path.join(d, ".sunshine.env"), "-e", f"SUNSHINE_PORT={int(sunshine)}", "-e", f"SUNSHINE_NAME={container(name)}"]
    if gpu and games:                            # the games device: same driver, plus its 32-bit libraries and without the /proc file bubblewrap trips on
        args += ["--device", GAMES_CDI_DEVICE, "-e", "NVIDIA_VISIBLE_DEVICES=all", "-e", "NVIDIA_DRIVER_CAPABILITIES=all"]
    elif gpu:
        args += ["--runtime", "nvidia", "-e", "NVIDIA_VISIBLE_DEVICES=all", "-e", "NVIDIA_DRIVER_CAPABILITIES=all"]
    return args + [image]


def write_secret(path, text, mode=0o600, replace=False):
    """A new file with that mode from the first byte (never world-readable for a moment); refuses to overwrite unless asked."""
    if replace:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def make_gate_token(name, rotate=False):
    """The place's own gate token: the person's stack gets it, the gate keeps only the hash, so a stack can only ever drive its own place."""
    d = pdir(name)
    if os.path.exists(os.path.join(d, ".gate.hash")) and not rotate:
        die(f"{name} already has a gate token: use --rotate to replace it (the old one stops working at once)", 3)
    tok = secrets.token_urlsafe(32)
    write_secret(os.path.join(d, ".gate.token"), tok + "\n", 0o600, replace=True)
    write_secret(os.path.join(d, ".gate.hash"), hashlib.sha256(tok.encode()).hexdigest() + "\n", 0o644, replace=True)
    print(f"gate token for {name} written to {os.path.join(d, '.gate.token')} (0600, never printed here); the gate reads only {os.path.join(d, '.gate.hash')}")


def check_udp(ports):
    ports = [int(p) for p in (ports or [])]
    if len(ports) > 4 or any(not 1024 <= p <= 65535 for p in ports) or len(set(ports)) != len(ports):
        die("--udp takes up to 4 different ports from 1024 to 65535 (a game's own port, for example 27960)")
    return ports


def sunshine_ports(base):
    """(tcp, udp) a Sunshine with that base port uses and the place publishes. BASE+1 is its admin page: never published."""
    if base is None:
        return [], []
    base = int(base)
    if not 20000 <= base <= 60000:
        die("--sunshine takes a base port from 20000 to 60000 (the host's own Sunshine keeps 47989; the stream ports are offsets of the base)")
    return [base - 5, base, base + 21], [base + 9, base + 10, base + 11, base + 13]


def sunshine_range(base):
    """Every port of a Sunshine with that base, the admin page's included: two places never share one."""
    return set(sum(sunshine_ports(base), [])) | {int(base) + 1}


def sunshine_taken(name, base):
    """The name of another place whose Sunshine ports overlap this base's, or None."""
    try:
        others = [n for n in os.listdir(ROOT) if n != name and is_place_name(n)]
    except OSError:
        return None
    mine = sunshine_range(base)
    for n in others:
        b = load_settings(n).get("sunshine")
        if b and mine & sunshine_range(b):
            return n
    return None


def ensure_sunshine_env(name):
    """NAME/.sunshine.env (0600): the password of this Sunshine's admin page, which only place.py pair uses (from localhost, inside the container)."""
    path = os.path.join(pdir(name), ".sunshine.env")
    if not os.path.exists(path):
        write_secret(path, "SUNSHINE_ADMIN_PASS=" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(28)) + "\n")
    return path


def save_settings(name, image, bind, gpu, udp=None, sunshine=None, games=False, library=None):
    """Writes the settings place.py manages and keeps every other key already there (e.g. "lang", read by the gate for the person's notices)."""
    old = load_settings(name)
    new = {"image": image, "bind": bind, "gpu": bool(gpu), "udp": check_udp(udp), "sunshine": sunshine, "games": bool(games), "library": library}
    new.update({k: v for k, v in old.items() if k not in new})
    with open(os.path.join(pdir(name), ".settings.json"), "w") as f:
        json.dump(new, f)


def load_settings(name):
    try:
        with open(os.path.join(pdir(name), ".settings.json")) as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def recreate(name, image=None, gpu=None, bind=None, udp=None, sunshine=..., games=None, library=..., held=False):
    d = pdir(name)
    if not os.path.exists(os.path.join(d, ".desktop.env")):
        die(f"{name} has no credentials file ({d}/.desktop.env): create it first", 3)
    old = load_settings(name)
    image = image or old.get("image") or "bridgeai-place:latest"
    gpu = old.get("gpu", False) if gpu is None else gpu
    bind = bind_address(bind) if bind else (old.get("bind") or bind_address(None))
    udp = check_udp(old.get("udp", []) if udp is None else udp)
    sunshine = old.get("sunshine") if sunshine is ... else sunshine
    games = bool(old.get("games", False)) if games is None else games
    library = check_library(old.get("library") if library is ... else library, None, place_uid(name))
    if sunshine:
        sunshine_ports(sunshine)
        if sunshine_taken(name, sunshine):
            die(f"the Sunshine ports of base {sunshine} overlap those of {sunshine_taken(name, sunshine)}: pick another base")
        ensure_sunshine_env(name)
    try:
        ports = tuple(int(x) for x in open(os.path.join(d, ".ports")).read().split())
        assert len(ports) == 2
    except (OSError, ValueError, AssertionError):
        ports = next_ports()
        with open(os.path.join(d, ".ports"), "w") as f:
            f.write(f"{ports[0]} {ports[1]}\n")
    if held:                                     # set-uid already holds the lock
        return _recreate_locked(name, image, gpu, bind, udp, sunshine, games, library, d, ports)
    with place_lock(name, "recreate"):           # the gate does not start a place while it is there: nobody opens it during the moves below
        _recreate_locked(name, image, gpu, bind, udp, sunshine, games, library, d, ports)


class place_lock:
    """PLACES_ROOT/.NAME.restore-lock for the time of a recreate or a uid change (restore takes the same one itself): the gate never starts the
    place while it is there."""
    def __init__(self, name, what):
        self.lock, self.name, self.what = restore_lock(name), name, what

    def __enter__(self):
        try:
            fd = os.open(self.lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            die(f"{self.lock} is there: a restore or recreate of {self.name} is running, or one failed and left it. Look at the place, then delete it", 3)
        with os.fdopen(fd, "w") as f:
            f.write(f"{self.what} of {self.name}, pid {os.getpid()}\n")
        return self

    def __exit__(self, *a):
        try:
            os.unlink(self.lock)
        except FileNotFoundError:
            pass
        return False


def set_uid(name):
    """Moves a place made before 2026-11-26 off uid 1000 (the operator's own account on the host) to its own uid, then recreates it."""
    d = pdir(name)
    if not os.path.exists(os.path.join(d, ".desktop.env")):
        die(f"{name} has no place", 3)
    old = place_uid(name)
    try:
        ports = tuple(int(x) for x in open(os.path.join(d, ".ports")).read().split())
    except (OSError, ValueError):
        die(f"{name} has no .ports: recreate it first", 3)
    new = uid_for_ports(ports)
    if old == new:
        r = subprocess.run([DOCKER, "inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", container(name)], capture_output=True, text=True)
        if f"PUID={new}" in r.stdout.split():
            print(f"{name} already runs as its own uid {new} (place-{name})")
            return
        print(f"{name}: its files are uid {new}'s but its container is not: recreating it")
        return recreate(name)
    library = load_settings(name).get("library")
    if library and library_sharers(name, library):
        die(f"{name}'s extra library is shared with {', '.join(library_sharers(name, library))}: one uid cannot own it for both. Give each its own first", 3)
    if library:
        check_library(library, None, old)        # before anything changes: the recreate at the end must not fail on it
    with place_lock(name, "uid change"):
        time.sleep(float(os.environ.get("PLACE_LOCK_SETTLE_S", "1")))
        busy = running_containers(name)
        if busy is None or busy:
            die(f"{name} is running (or docker cannot tell): stop it first", 3)
        ensure_account(name, new)
        bad = move_to_uid(name, old, new, library)
        if bad:
            die(f"{name}: some folders could not be given to uid {new}: {', '.join(bad)}. Nothing was recreated; run set-uid again", 1)
        v = load_settings(name)
        v["uid"] = new
        with open(os.path.join(d, ".settings.json"), "w") as f:
            json.dump(v, f)
        print(f"{name}: its files now belong to uid {new} (place-{name}), no longer to {old}")
        recreate(name, held=True)                # under the same lock: the gate never starts the old container on the new files


def _recreate_locked(name, image, gpu, bind, udp, sunshine, games, library, d, ports):
    time.sleep(float(os.environ.get("PLACE_LOCK_SETTLE_S", "1")))   # a gate start that checked the lock just before it existed is running by now
    busy = running_containers(name)              # running, paused (frozen) or restarting: never recreated under the person's hands
    if busy is None:
        die("docker could not be asked whether the place runs: not recreated", 3)
    if busy:
        die(f"{busy[0][0]} is {busy[0][1]}: stop it first (a place is never recreated under the person's hands)", 3)
    if library and not library_mount_ok(name):
        die(f"{name}: SteamLibraryExtra in the home is a link or a file: the library cannot be mounted there. Look at it first", 3)
    own_areas(d, place_uid(name))               # the person may have changed the modes of their folders; the gate needs these
    caches = prepare_hostcache(name, library) if gpu else []
    if running_containers(name):                 # started anyway: stop here, the person's session must not lose its container
        die(f"{name} was started during the recreate: not recreated (run it again once the place is stopped)", 3)
    for c in (container(name), legacy_container(name)):
        subprocess.run([DOCKER, "rm", c], capture_output=True, text=True)
    subprocess.run([DOCKER, "network", "rm", legacy_net(name)], capture_output=True, text=True)   # its /24 goes to the new network
    ensure_net(name, ports)
    r = subprocess.run(run_args(name, image, bind, ports, gpu, udp=udp, sunshine=sunshine, games=games, library=library, caches=caches), capture_output=True, text=True)
    if r.returncode != 0:
        die(f"docker could not create the container: {r.stderr.strip()[:300]}", 1)
    save_settings(name, image, bind, gpu, udp, sunshine, games, library)
    print(f"{container(name)} recreated from {image}{' with the GPU' if gpu else ''}{' and the games profile' if games else ''}, not started. Same folder, ports and login as before."
          + (f" Moonlight: {bind}:{sunshine}." if sunshine else "") + (" GPU shader caches on this host, at /hostcache." if caches else ""))


def make_place_dir(d):
    """The place's own folder. When PLACES_ROOT is the btrfs disk (a subvolume itself) the folder is a subvolume of its own, so it can be
    snapshotted alone; elsewhere a plain folder. A folder that is already there is kept as it is (with a warning when it cannot be snapshotted)."""
    if os.path.islink(d):
        die(f"{d} is a link: refused", 3)
    on_btrfs = is_subvolume(ROOT)
    if os.path.isdir(d):
        if on_btrfs and not is_subvolume(d):
            print(f"warning: {d} is already there as a plain folder, not a btrfs subvolume: this place gets no snapshots", file=sys.stderr)
        return
    if not on_btrfs:
        os.makedirs(d, mode=0o755)
        return
    r = btrfs("subvolume", "create", d)
    if r.returncode != 0:
        die(f"btrfs could not create the subvolume {d}: {(r.stderr or r.stdout).strip()[:300]}", 1)
    os.chmod(d, 0o755)


def create(name, image, bind=None, gpu=False, ports=None, udp=None, sunshine=None, games=False, library=None):
    d = pdir(name)
    limits()                                     # a bad PLACE_MEM must stop us before anything is written
    if games:
        games_options()                          # and so must a host without the games profiles
    udp = check_udp(udp)
    if os.path.exists(os.path.join(d, ".desktop.env")):
        die(f"{name} already has a place ({d}): remove it first, nothing was changed", 3)
    addr = bind_address(bind)
    if sunshine:
        sunshine_ports(sunshine)
        if sunshine_taken(name, sunshine):
            die(f"the Sunshine ports of base {sunshine} overlap those of {sunshine_taken(name, sunshine)}: pick another base")
    ports = ports or next_ports()
    uid = uid_for_ports(ports)                   # the place's own uid, never the operator's account
    library = check_library(library, None, uid)
    ensure_account(name, uid)
    make_place_dir(d)
    with open(os.path.join(d, ".settings.json"), "w") as f:
        json.dump({"uid": uid}, f)               # save_settings keeps it
    for sub in ("desktop", "input", "output"):
        os.makedirs(os.path.join(d, sub), mode=0o755, exist_ok=True)
    own_areas(d, uid)
    pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(28))
    fd = os.open(os.path.join(d, ".desktop.env"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"CUSTOM_USER={name}\nPASSWORD={pw}\n")
    with open(os.path.join(d, ".ports"), "w") as f:
        f.write(f"{ports[0]} {ports[1]}\n")
    if sunshine:
        ensure_sunshine_env(name)
    caches = prepare_hostcache(name, library) if gpu else []
    ensure_net(name, ports)
    r = subprocess.run(run_args(name, image, addr, ports, gpu, udp=udp, sunshine=sunshine, games=games, library=library, caches=caches), capture_output=True, text=True)
    if r.returncode != 0:
        die(f"docker could not create the container: {r.stderr.strip()[:300]}", 1)
    save_settings(name, image, addr, gpu, udp, sunshine, games, library)
    make_gate_token(name)
    print(f"{container(name)} created, not started. Web (HTTPS): https://{addr}:{ports[1]}  (LAN only). Credentials: {os.path.join(d, '.desktop.env')} (0600, never printed here).")


def pair(name, pin):
    """Hands Sunshine the PIN Moonlight shows. Sunshine's admin page answers only over localhost inside the container, so both calls are made there; the password
    is read from the container's own environment, never from a command line. The pairing the person just started in Moonlight is the pending one."""
    base = load_settings(name).get("sunshine")
    if not base:
        die(f"{name} has no Moonlight stream (create or recreate it with --sunshine BASE)", 3)
    if not re.fullmatch(r"\d{4}", pin or ""):
        die("the PIN is the 4 digits Moonlight shows")
    url = f"https://127.0.0.1:{int(base) + 1}/api/pin"
    auth = 'curl -sk -m15 -u "admin:$SUNSHINE_ADMIN_PASS" -H "Content-Type: application/json" '
    ex = [DOCKER, "exec", "-u", f"{place_uid(name)}:{place_uid(name)}", container(name), "sh", "-c"]
    r = subprocess.run(ex + [auth + url, "sh"], capture_output=True, text=True)
    try:
        pending = json.loads(r.stdout).get("pairings") or []
    except (ValueError, AttributeError):
        pending = []
    if r.returncode != 0 or not pending:
        die("no pairing is waiting: in Moonlight add the host first (it shows the PIN), then run this within a minute", 3)
    p = pending[-1]
    pid = str(p.get("id", ""))
    if not re.fullmatch(r"[0-9a-fA-F]{32}", pid):
        die("Sunshine answered a pending pairing in a shape this script does not know", 1)
    r = subprocess.run(ex + [auth + '-d "{\\"pin\\":\\"$1\\",\\"name\\":\\"$2\\",\\"pairing_id\\":\\"$3\\"}" ' + url, "sh", pin, name, pid], capture_output=True, text=True)
    ok = r.returncode == 0 and '"status":true' in r.stdout.replace(" ", "")
    who = f"{p.get('name', '?')} from {p.get('address', '?')}"
    if ok:
        print(f"PIN accepted for {who}")
    else:
        print(f"Sunshine did not confirm the PIN for {who} ({(r.stdout.strip() or r.stderr.strip())[:120]}). Moonlight says whether the pairing finished: if it did not, start it again and give the new PIN")
    sys.exit(0 if ok else 1)


NOTIFY_SH = r"""P=$(pgrep -u "$(id -u)" -f xfce4-notifyd | head -1)
[ -n "$P" ] || { echo "no notification service in the session (is the desktop open?)" >&2; exit 3; }
export $(tr '\0' '\n' < /proc/$P/environ | grep -E '^(DISPLAY|DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR)=' | xargs)
exec notify-send -u "$3" -t "$4" -i dialog-warning -a bridgeai "$1" "$2"
"""


def notify(name, title, body, seconds=0, urgent=True):
    """A notification in the session of a running place, sent by the session's own notification service. Title and body are arguments, never part of the
    command text (no quoting or injection through what the operator writes)."""
    pdir(name)
    if not title or len(title) > 120 or len(body) > 1000 or not 0 <= seconds <= 3600:
        die("the title is 1 to 120 characters, the body up to 1000, --seconds 0 (until closed) to 3600")
    st = subprocess.run([DOCKER, "inspect", "-f", "{{.State.Status}}", container(name)], capture_output=True, text=True)
    if st.returncode != 0 or st.stdout.strip() != "running":
        die(f"{container(name)} is not running: nobody would see it", 3)
    r = subprocess.run([DOCKER, "exec", "-u", f"{place_uid(name)}:{place_uid(name)}", container(name), "sh", "-c", NOTIFY_SH, "sh", title, body,
                        "critical" if urgent else "normal", str(int(seconds) * 1000)], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        die(f"the notification was not shown: {(r.stderr or r.stdout).strip()[:200]}", r.returncode if r.returncode in (1, 3) else 1)
    print(f"notification shown in {container(name)}")


GAME_PROCS = os.environ.get("PLACE_GAME_PROCS", r"SteamLaunch|\.exe( |$)|(^|[/ ])ioquake3( |$)|(^|[/ ])ioq3ded( |$)")   # the gate uses the same


def game_open(name):
    r = subprocess.run([DOCKER, "exec", container(name), "pgrep", "-af", GAME_PROCS], capture_output=True, text=True)
    return [l.split(" ", 1)[-1][:80] for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []


def stop(name, force=False):
    st = subprocess.run([DOCKER, "inspect", "-f", "{{.State.Status}}", container(name)], capture_output=True, text=True)
    if st.returncode == 0 and st.stdout.strip() == "running" and not force:
        g = game_open(name)
        if g:
            die(f"{container(name)} has a game open ({g[0]}): not stopped. Wait for it to close, or --force", 3)
    r = subprocess.run([DOCKER, "stop", "-t", "30", container(name)], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"docker could not stop {container(name)}: {r.stderr.strip()[:200]}", 1)
    print(f"{container(name)} stopped")


KILL_GAME_SH = r"""n=0
for p in $(pgrep -u "$(id -u)" -f '\.exe( |$)|(^|[/ ])ioquake3( |$)'); do kill -9 "$p" 2>/dev/null && n=$((n + 1)); done
sleep 1
for w in $(pgrep -u "$(id -u)" -f '/wineserver( |$)'); do kill "$w" 2>/dev/null; done
sleep 2
for w in $(pgrep -u "$(id -u)" -f '/wineserver( |$)|\.exe( |$)'); do kill -9 "$w" 2>/dev/null; done
echo "$n"
"""


def kill_game(name):
    """The same as the place's own kill-game, run from outside (a place on an older image may not have it)."""
    pdir(name)
    r = subprocess.run([DOCKER, "exec", "-u", f"{place_uid(name)}:{place_uid(name)}", container(name), "sh", "-c", KILL_GAME_SH], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        die(f"could not run inside {container(name)}: {r.stderr.strip()[:200]}", 1)
    n = (r.stdout.strip().splitlines() or ["0"])[-1]
    print(f"{container(name)}: {n} game process(es) closed" if n != "0" else f"{container(name)}: no game was running")


def hold(name, how):
    d = pdir(name)
    if not os.path.exists(os.path.join(d, ".desktop.env")):
        die(f"{name} has no place", 3)
    f = os.path.join(d, ".hold")
    if how == "on":
        with open(f, "w") as fh:
            fh.write("held by the operator: the idle clock never closes this place\n")
        print(f"{container(name)} held: it stays open until `place.py hold {name} off`")
    elif how == "off":
        if os.path.exists(f):
            os.remove(f)
        print(f"{container(name)} released: the idle clock closes it after its idle time again")
    else:
        die("hold takes on or off")


BTRFS = os.environ.get("BTRFS", "btrfs")
SNAPSHOTS = ".snapshots"                         # PLACES_ROOT/.snapshots/NAME/...: not a place name, so the gate, places-net.sh and the port scan skip it
SNAP_OK = re.compile(r"(\d{8}T\d{6}Z)-([a-z0-9-]{1,24})")
REASON_OK = re.compile(r"[a-z0-9-]{1,24}")
STAMP = "%Y%m%dT%H%M%SZ"
KEEP_ON_RESTORE = (".settings.json", ".desktop.env", ".gate.token", ".gate.hash", ".ports", ".sunshine.env", ".hold")   # the place's own config, not the person's files
KIND_SUFFIX = ".state"                           # .snapshots/NAME/<snapshot>.state: "running" or "stopped", what the place was when the snapshot was taken
KIND_TEXT = {
    "running": "taken while the place was running: crash-consistent, like after a power cut (a program that was writing may have to repair its files)",
    "stopped": "taken while the place was stopped: a clean state",
    "unknown": "whether the place was running then is not recorded (treat it like a power cut)",
}
BUSY_STATES = ("running", "paused", "restarting", "removing")   # docker states in which the container still holds the place's folder


def btrfs(*args):
    try:
        return subprocess.run([BTRFS, *args], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess([BTRFS, *args], 127, "", str(e))


def is_subvolume(path):
    return not os.path.islink(path) and os.path.isdir(path) and btrfs("subvolume", "show", path).returncode == 0


def snap_dir(name, make=False):
    """PLACES_ROOT/.snapshots/NAME (0700: a snapshot holds the place's secrets and the person's files). Never a link."""
    pdir(name)
    base = os.path.join(ROOT, SNAPSHOTS)
    d = os.path.join(base, name)
    for p in (base, d):
        if os.path.islink(p):
            die(f"{p} is a link: refused", 3)
        if make and not os.path.isdir(p):
            os.mkdir(p, 0o700)
    return d


def snap_list(name):
    """[(snapshot name, UTC time, reason)], newest first. Only entries named like a snapshot, real folders, no links."""
    d = snap_dir(name)
    try:
        entries = os.listdir(d)
    except OSError:
        return []
    out = []
    for e in entries:
        m = SNAP_OK.fullmatch(e)
        p = os.path.join(d, e)
        if not m or os.path.islink(p) or not os.path.isdir(p):
            continue
        try:
            ts = datetime.strptime(m.group(1), STAMP).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        out.append((e, ts, m.group(2)))
    return sorted(out, key=lambda s: (s[1], s[0]), reverse=True)


def need_subvolume(name):
    d = pdir(name)
    if os.path.islink(d) or not os.path.isdir(d):
        die(f"{name} has no place folder ({d})", 3)
    if not os.path.isfile(os.path.join(d, ".desktop.env")):
        die(f"{d} is not a place (it has no .desktop.env): no snapshot", 3)
    if not is_subvolume(d):
        die(f"{d} is not a btrfs subvolume: no snapshot (a place on the old layout has none; move it onto the btrfs disk first)", 3)
    return d


def snap_kind(name, snap):
    """"running", "stopped" or "unknown": what the place was when SNAP was taken (from the file beside it)."""
    try:
        with open(os.path.join(snap_dir(name), snap + KIND_SUFFIX)) as f:
            v = f.read().strip()
    except OSError:
        return "unknown"
    return v if v in KIND_TEXT else "unknown"


def snapshot(name, reason="manual"):
    """A read-only snapshot of the place's subvolume. Instant, and no data is written: only what changes afterwards takes new space. A snapshot
    of a running place is taken as it is: crash-consistent, like a power cut. Which of the two it was is recorded beside it."""
    if not REASON_OK.fullmatch(reason or ""):
        die("the reason is 1 to 24 characters of a-z, 0-9 and -")
    d = need_subvolume(name)
    busy = running_containers(name)
    kind = "unknown" if busy is None else "running" if busy else "stopped"
    sd = snap_dir(name, make=True)
    for _ in range(3):                           # two snapshots with the same reason in the same second: wait for the next one
        dst = os.path.join(sd, datetime.now(timezone.utc).strftime(STAMP) + "-" + reason)
        if not os.path.lexists(dst):
            break
        time.sleep(1)
    else:
        die(f"{dst} already exists", 1)
    r = btrfs("subvolume", "snapshot", "-r", d, dst)
    if r.returncode != 0:
        die(f"btrfs could not snapshot {d}: {(r.stderr or r.stdout).strip()[:300]}", 1)
    try:
        write_secret(dst + KIND_SUFFIX, kind + "\n", 0o600, replace=True)
    except OSError as e:
        print(f"warning: could not record whether {name} was running ({e})", file=sys.stderr)
    print(f"{name}: snapshot {os.path.basename(dst)} taken (read-only), {KIND_TEXT[kind]}")
    return os.path.basename(dst)


def age(seconds):
    s = max(0, int(seconds))
    return f"{s // 86400} d {s % 86400 // 3600} h" if s >= 86400 else f"{s // 3600} h {s % 3600 // 60} min" if s >= 3600 else f"{s // 60} min"


def list_snapshots(name):
    snaps = snap_list(name)
    if not snaps:
        print(f"{name}: no snapshots")
        return
    now = datetime.now(timezone.utc)
    w = max(len(s[0]) for s in snaps)
    for n, ts, reason in snaps:
        print(f"{n:<{w}}  {reason:<24}  {snap_kind(name, n):<8}  {age((now - ts).total_seconds())} ago")


def running_containers(name):
    """[(container, state)] of the place's containers (NAMEdoc and the name before 2026-11-25) that still hold its folder: running, paused
    (frozen), restarting or being removed. None when docker cannot be asked at all."""
    out = []
    for c in (container(name), legacy_container(name)):
        try:
            st = subprocess.run([DOCKER, "inspect", "-f", "{{.State.Status}}", c], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        if st.returncode == 0 and st.stdout.strip() in BUSY_STATES:
            out.append((c, st.stdout.strip()))
    return out


def restore_lock(name):
    """PLACES_ROOT/.NAME.restore-lock: there while a restore runs (and after one that failed half-way). The gate does not start the place while it exists."""
    return os.path.join(ROOT, f".{name}.restore-lock")


def carry_file(src, dst):
    """Copies one regular file from the old state into the restored one with its mode and owner, never through a link; removes dst when src is absent."""
    try:
        st = os.lstat(src)
    except FileNotFoundError:
        st = None
    try:
        os.unlink(dst)
    except FileNotFoundError:
        pass
    if st is None or not stat.S_ISREG(st.st_mode):
        return
    with open(src, "rb") as f:
        data = f.read()
    fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        if os.geteuid() == 0:
            os.fchown(f.fileno(), st.st_uid, st.st_gid)
        os.fchmod(f.fileno(), stat.S_IMODE(st.st_mode))
        f.write(data)


def restore(name, snap, force=False):
    """The place's subvolume becomes a writable snapshot of SNAP. The current state is kept first as a "before-restore" snapshot, and the old subvolume is
    deleted only after the new one is in place."""
    d = pdir(name)
    if not snap or "/" in snap or ".." in snap or not SNAP_OK.fullmatch(snap):
        die("give the snapshot's name exactly as `place.py snapshots NAME` lists it")
    src = os.path.join(snap_dir(name), snap)
    if os.path.islink(src) or not os.path.isdir(src):
        die(f"{name} has no snapshot {snap}", 3)
    need_subvolume(name)
    if not is_subvolume(src):
        die(f"{snap} is not a btrfs snapshot: refused", 3)
    aside = os.path.join(ROOT, f".{name}.restoring")
    if os.path.lexists(aside):
        die(f"{aside} is left from an earlier restore: look at it and delete it (btrfs subvolume delete) first", 3)
    lock = restore_lock(name)
    try:                                         # taken before the running check: from here on the gate does not start the place
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        die(f"{lock} is there: another restore of {name} is running, or one failed half-way and left it. The gate does not open {name} while it is "
            "there: look at the place, then delete it", 3)
    except OSError as e:
        die(f"could not create {lock}: {e}", 1)
    with os.fdopen(fd, "w") as f:
        f.write(f"restore of {name} to {snap}, pid {os.getpid()}\n")
    changing = False                             # True from the moment the folder is moved aside until the place is whole again
    try:
        busy = running_containers(name)
        if busy is None:
            die("docker could not be asked whether the place runs: not restored, nothing changed", 3)
        if busy and not force:
            die(f"{busy[0][0]} is {busy[0][1]}: stop it first, or --force (a place is never restored under the person's hands)", 3)
        for c, cst in busy:
            if cst == "paused":                  # a frozen container cannot be stopped cleanly: thaw it first
                r = subprocess.run([DOCKER, "unpause", c], capture_output=True, text=True)
                if r.returncode != 0:
                    die(f"docker could not unpause {c}: {r.stderr.strip()[:200]}. Not restored, nothing changed", 1)
            if c == container(name):
                stop(name, force=True)
            else:
                r = subprocess.run([DOCKER, "stop", "-t", "30", c], capture_output=True, text=True)
                if r.returncode != 0:
                    die(f"docker could not stop {c}: {r.stderr.strip()[:200]}", 1)
        before = snapshot(name, "before-restore")
        busy = running_containers(name)          # something started it after the check (not the gate: it sees the lock)
        if busy is None or busy:
            die(f"{busy[0][0] if busy else name} started during the restore: not restored, nothing changed (snapshot {before} stays)", 3)
        kind = snap_kind(name, snap)
        st = os.stat(d)
        changing = True
        os.rename(d, aside)
        r = btrfs("subvolume", "snapshot", src, d)
        if r.returncode != 0:
            if not os.path.lexists(d):
                os.rename(aside, d)
                changing = False
                die(f"btrfs could not restore {snap}: {(r.stderr or r.stdout).strip()[:300]}. Nothing changed", 1)
            die(f"btrfs could not restore {snap} and left {d}: the place as it was is in {aside} (and in {before})", 1)
        try:
            if os.geteuid() == 0:
                os.chown(d, st.st_uid, st.st_gid)
            os.chmod(d, stat.S_IMODE(st.st_mode))
            for f in KEEP_ON_RESTORE:
                carry_file(os.path.join(aside, f), os.path.join(d, f))
        except OSError as e:
            die(f"{snap} is back, but the place's own files could not be carried over ({e}): they are still in {aside}", 1)
        changing = False
        uid = place_uid(name)
        if uid != LEGACY_UID:                    # a snapshot from before the place got its own uid: its files come back as 1000's
            bad = move_to_uid(name, LEGACY_UID, uid)
            if bad:
                print(f"warning: {name}: some restored files could not be given to uid {uid}: {', '.join(bad)} (run set-uid NAME)", file=sys.stderr)
        if load_settings(name).get("gpu") and os.path.isdir(place_cache_dir(name)):
            try:                                 # the snapshot may predate the cache links: put them back (the place is still stopped)
                prepare_hostcache(name, load_settings(name).get("library"))
            except (OSError, SystemExit) as e:
                print(f"warning: {name}: the shader cache links could not be put back ({e}): they come back at the next recreate", file=sys.stderr)
        busy = running_containers(name)
        if busy is None or busy:                 # something started the place during the swap: its writes may be in the old state, keep it
            r = None
            left = f" The place was started during the restore, so the old state was kept, not deleted: {aside} (look at it before deleting it)."
        else:
            r = btrfs("subvolume", "delete", aside)
            left = "" if r.returncode == 0 else f" The old state could not be deleted: {aside} (delete it with btrfs subvolume delete)."
        print(f"{name}: restored to {snap}, {KIND_TEXT[kind]}. Settings, login, ports and gate token kept as they were. "
              f"Before this restore: snapshot {before}.{left}")
    finally:
        if changing:
            print(f"{lock} is left on purpose: the gate will not open {name} until you have looked at the place and deleted it", file=sys.stderr)
        else:
            try:
                os.unlink(lock)
            except FileNotFoundError:
                pass


def prune(days=None):
    """Deletes every place's snapshots older than DAYS, always keeping the newest one of each place that still exists. A place whose folder is
    gone keeps none: its snapshots go once they are older than DAYS. A place in the middle of a restore (its lock is there) is left alone."""
    raw = days if days is not None else os.environ.get("PLACE_SNAPSHOT_DAYS", "7")
    try:
        n = int(raw)
        assert 1 <= n <= 3650
    except (ValueError, TypeError, AssertionError):
        die("--days (or PLACE_SNAPSHOT_DAYS) is a whole number of days from 1 to 3650")
    base = os.path.join(ROOT, SNAPSHOTS)
    if os.path.islink(base):
        die(f"{base} is a link: refused", 3)
    try:
        names = sorted(x for x in os.listdir(base) if is_place_name(x))
    except OSError:
        names = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=n)
    gone = failed = 0
    for name in names:
        if os.path.lexists(restore_lock(name)):
            print(f"{name}: a restore is running (or left its lock): its snapshots are not pruned now", file=sys.stderr)
            continue
        pd = os.path.join(ROOT, name)
        exists = os.path.isdir(pd) and not os.path.islink(pd)
        for snap, ts, _ in snap_list(name)[1 if exists else 0:]:
            if ts < cutoff:
                r = btrfs("subvolume", "delete", os.path.join(base, name, snap))
                if r.returncode == 0:
                    gone += 1
                    try:
                        os.unlink(os.path.join(base, name, snap + KIND_SUFFIX))
                    except OSError:
                        pass
                else:
                    failed += 1
                    print(f"{name}: could not delete {snap}: {(r.stderr or r.stdout).strip()[:200]}", file=sys.stderr)
    print(f"prune: {gone} snapshot(s) older than {n} days deleted" + (f", {failed} failed" if failed else "")
          + "; the newest of each existing place is always kept")
    rotate_caches()
    sys.exit(1 if failed else 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["create", "start", "stop", "status", "creds", "rm", "recreate", "gate-token", "pair", "notify", "hold", "kill-game",
                                    "snapshot", "snapshots", "restore", "prune", "hostcache", "set-uid", "dedupe"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("pin", nargs="?", help="pair: the PIN; notify: the title; restore: the snapshot")
    ap.add_argument("body", nargs="?", help="notify: the text")
    ap.add_argument("--seconds", type=int, default=0)
    ap.add_argument("--normal", action="store_true")
    ap.add_argument("--sunshine", type=int, metavar="BASE")
    ap.add_argument("--no-sunshine", action="store_true")
    ap.add_argument("--library", default=None, metavar="HOSTDIR")
    ap.add_argument("--no-library", action="store_true")
    ap.add_argument("--games", action="store_true", default=None)
    ap.add_argument("--no-games", action="store_true")
    ap.add_argument("--image", default=None)
    ap.add_argument("--bind")
    ap.add_argument("--gpu", action="store_true", default=None)
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="dedupe: only report the duplicates, share nothing")
    ap.add_argument("--if-needed", action="store_true", help="dedupe: only when no place runs and a game changed since the last complete run")
    ap.add_argument("--max-seconds", type=int, default=0, help="dedupe: stop after this long (the next run goes on)")
    ap.add_argument("--clear", action="store_true", help="hostcache: empty the place's GPU caches (the place stopped)")
    ap.add_argument("--force", action="store_true", help="stop: even with a game open; restore: unpause and stop the place first, the same way")
    ap.add_argument("--reason", default="manual", help="snapshot: one word (a-z, 0-9, -) kept in the snapshot's name")
    ap.add_argument("--days", default=None, help="prune: keep this many days (default PLACE_SNAPSHOT_DAYS or 7)")
    ap.add_argument("--udp", type=int, action="append", metavar="PORT", help="also publish this UDP port on the place's LAN address (a game's own port); repeat for up to 4; recreate keeps the saved ones, --no-udp clears them")
    ap.add_argument("--no-udp", action="store_true")
    ap.add_argument("--ports", nargs=2, type=int, metavar=("HTTP", "HTTPS"), help="create only: take these two ports (a place that already ran on them)")
    a = ap.parse_args(argv)
    if a.cmd == "prune":
        if a.name:
            die("prune takes no NAME: it goes through every place")
        prune(a.days)
    if a.cmd == "dedupe":
        if a.name:
            die("dedupe takes no NAME: it goes through every place")
        dedupe(a.dry_run, a.if_needed, int(a.max_seconds or 0))
        return
    if not a.name:
        die(f"{a.cmd} needs the place's NAME")
    d = pdir(a.name)
    if a.cmd == "hostcache":
        hostcache_info(a.name, a.clear)
    elif a.cmd == "set-uid":
        set_uid(a.name)
    elif a.cmd == "snapshot":
        snapshot(a.name, a.reason)
    elif a.cmd == "snapshots":
        list_snapshots(a.name)
    elif a.cmd == "restore":
        restore(a.name, a.pin, a.force)
    elif a.cmd == "create":
        create(a.name, a.image or ("bridgeai-place-steam:latest" if a.games else "bridgeai-place:latest"), a.bind, bool(a.gpu), tuple(a.ports) if a.ports else None, a.udp, a.sunshine, bool(a.games), a.library)
    elif a.cmd == "recreate":
        recreate(a.name, a.image, False if a.no_gpu else a.gpu, a.bind, [] if a.no_udp else a.udp, None if a.no_sunshine else (a.sunshine if a.sunshine else ...), False if a.no_games else a.games, None if a.no_library else (a.library if a.library else ...))
    elif a.cmd == "kill-game":
        kill_game(a.name)
    elif a.cmd == "hold":
        hold(a.name, a.pin or "")
    elif a.cmd == "notify":
        notify(a.name, a.pin or "", a.body or "", a.seconds, not a.normal)
    elif a.cmd == "pair":
        pair(a.name, a.pin)
    elif a.cmd == "gate-token":
        make_gate_token(a.name, a.rotate)
    elif a.cmd == "creds":
        print(os.path.join(d, ".desktop.env"))
    elif a.cmd == "stop":
        stop(a.name, a.force)
    elif a.cmd == "start":
        r = subprocess.run([DOCKER, a.cmd, container(a.name)], capture_output=True, text=True)
        print(f"{container(a.name)}: {a.cmd} " + ("ok" if r.returncode == 0 else "failed: " + r.stderr.strip()[:200]))
        sys.exit(r.returncode)
    elif a.cmd == "status":
        r = subprocess.run([DOCKER, "inspect", "-f", "{{.State.Status}}", container(a.name)], capture_output=True, text=True)
        print(r.stdout.strip() or "no such place")
        sys.exit(0 if r.returncode == 0 else 1)
    elif a.cmd == "rm":
        r = subprocess.run([DOCKER, "rm", container(a.name)], capture_output=True, text=True)
        print(f"{container(a.name)} removed; the folder {d} was left (the person's files)." if r.returncode == 0 else "failed: " + r.stderr.strip()[:200])
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
