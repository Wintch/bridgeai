#!/usr/bin/env python3
"""A person's own desktop place on a GPU host: one container (the webtop in Dockerfile.place), one volume folder, one pair of LAN ports, a secret nobody prints.

  place.py create NAME [--image IMG] [--bind IP] [--gpu] [--ports A B]   makes the folders, a password (kept 0600, never printed), the container (NOT started)
  place.py start|stop|status NAME                          the container only; a place starts stopped and is started on request
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
  place.py notify NAME TITLE BODY [--seconds N] [--normal]   a desktop notification in the person's running session (XFCE's own, top right): stays until
                                                           closed unless --seconds; urgent unless --normal. Write it in the person's language
  place.py pair NAME PIN                                   gives Sunshine the PIN Moonlight shows when pairing (asked inside the container, from localhost)
  place.py gate-token NAME [--rotate]                      makes the token the person's stack uses to open and close THIS place through the gate
                                                           (/place/*): kept 0600 in .gate.token, only its hash in .gate.hash (the gate reads that); never printed

Layout (PLACES_ROOT, default /srv/bridgeai/places): NAME/desktop (the webtop's /config: the person's home), NAME/input and NAME/output (files in and out),
NAME/.desktop.env (CUSTOM_USER and PASSWORD, 0600), NAME/.ports ("3010 3011"). Ports are bound to one LAN address only (PLACE_BIND or --bind), never to
0.0.0.0: the way in from the internet is a separate, on-demand door (PLACES.md). The container runs with no-new-privileges, a 1 GB /dev/shm (browsers need
it) and restart=no, like the operator's own. The container, its hostname and its network interface on the host are all NAMEdoc. Each place has its OWN docker network (NAMEdoc-net, a /24 of 172.30.0.0/16) and memory/CPU/process limits (PLACE_MEM 9g, PLACE_CPUS 5, PLACE_PIDS 4096); what a place may reach is decided by places-net.sh. `--gpu` adds the NVIDIA runtime for Resolve; GPU use still goes through the GPU gate's rules.
Stdlib only. DOCKER overrides the docker binary (the selftest uses a fake one)."""
import argparse, hashlib, json, os, re, secrets, string, subprocess, sys

ROOT = os.environ.get("PLACES_ROOT", "/srv/bridgeai/places")
DOCKER = os.environ.get("DOCKER", "docker")
NAME_OK = re.compile(r"[a-z][a-z0-9]{1,11}")     # NAME + "doc" is the container, the hostname and the network interface (15 characters at most)
LIBRARY_ROOTS = os.environ.get("PLACE_LIBRARY_ROOTS", "/mnt/nvme-data/places")
LIBRARY_MOUNT = "/config/SteamLibraryExtra"
GAMES_SECCOMP = os.environ.get("PLACE_GAMES_SECCOMP", "/etc/bridgeai/places/seccomp-games.json")
GAMES_APPARMOR = "bridgeai-place-games"
GAMES_CDI_DEVICE = "bridgeai.local/games=all"   # /etc/cdi/bridgeai-games.json, written by gen-games-cdi.sh
BASE_PORT, STEP = 3010, 10                      # 3000/3001 belong to the first place; each new one takes the next pair of tens


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def pdir(name):
    if not NAME_OK.fullmatch(name or ""):
        die("a place name is 2 to 12 lowercase letters and digits, starting with a letter")
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


def check_library(path, env=None):
    """A host folder a place may get as an extra game library: an absolute, real (no link anywhere in it) directory strictly inside one of
    PLACE_LIBRARY_ROOTS, owned by uid 1000 (the person's). Returns the path; refuses anything else."""
    if not path:
        return None
    roots = [r for r in (env or os.environ).get("PLACE_LIBRARY_ROOTS", LIBRARY_ROOTS).split(":") if r]
    if not os.path.isabs(path) or path != os.path.normpath(path) or os.path.realpath(path) != path or not os.path.isdir(path):
        die(f"--library takes an existing folder given by its real absolute path (no links): {path}")
    if not any(os.path.commonpath([path, r]) == os.path.normpath(r) and os.path.normpath(path) != os.path.normpath(r) for r in roots):
        die(f"--library must be a folder inside {':'.join(roots)} (PLACE_LIBRARY_ROOTS), never a whole disk")
    if os.stat(path).st_uid != 1000:
        die(f"{path} must belong to uid 1000 (the person inside the place)")
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


def run_args(name, image, bind, ports, gpu=False, env=None, udp=None, sunshine=None, games=False, library=None):
    d = pdir(name)
    args = [DOCKER, "create", "--name", container(name), "--hostname", container(name), "--security-opt", "no-new-privileges", *(games_options(env) if games else []), "--shm-size", "1gb", "--restart", "no",
            "--network", net_name(name), *limits(env),
            "-p", f"{bind}:{ports[0]}:3000", "-p", f"{bind}:{ports[1]}:3001",
            *[x for p in check_udp(udp) for x in ("-p", f"{bind}:{p}:{p}/udp")],
            *[x for p in sunshine_ports(sunshine)[0] for x in ("-p", f"{bind}:{p}:{p}/tcp")],
            *[x for p in sunshine_ports(sunshine)[1] for x in ("-p", f"{bind}:{p}:{p}/udp")],
            "--env-file", os.path.join(d, ".desktop.env"),
            "-e", "PUID=1000", "-e", "PGID=1000", "-e", "TZ=" + (env or os.environ).get("TZ", "America/Argentina/Buenos_Aires"),
            "-e", "LANG=en_US.UTF-8", "-e", "LANGUAGE=en_US:en", "-e", "LC_ALL=en_US.UTF-8",
            "-v", f"{d}/desktop:/config", "-v", f"{d}/input:/input", "-v", f"{d}/output:/output"]
    for helper in ("to-resolve", "from-resolve"):    # the helpers come from this folder, read-only: a fix to one reaches every place at its next start, no 20 GB image rebuild
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", helper)
        if os.path.isfile(path):
            args += ["-v", f"{path}:/usr/local/bin/{helper}:ro"]
    if library:
        args += ["-v", f"{check_library(library, env)}:{LIBRARY_MOUNT}"]
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
        others = [n for n in os.listdir(ROOT) if n != name and NAME_OK.fullmatch(n)]
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
    with open(os.path.join(pdir(name), ".settings.json"), "w") as f:
        json.dump({"image": image, "bind": bind, "gpu": bool(gpu), "udp": check_udp(udp), "sunshine": sunshine, "games": bool(games), "library": library}, f)


def load_settings(name):
    try:
        with open(os.path.join(pdir(name), ".settings.json")) as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def recreate(name, image=None, gpu=None, bind=None, udp=None, sunshine=..., games=None, library=...):
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
    library = check_library(old.get("library") if library is ... else library)
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
    for c in (container(name), legacy_container(name)):
        st = subprocess.run([DOCKER, "inspect", "-f", "{{.State.Status}}", c], capture_output=True, text=True)
        if st.returncode == 0 and st.stdout.strip() == "running":
            die(f"{c} is running: stop it first (a place is never recreated under the person's hands)", 3)
    for c in (container(name), legacy_container(name)):
        subprocess.run([DOCKER, "rm", c], capture_output=True, text=True)
    subprocess.run([DOCKER, "network", "rm", legacy_net(name)], capture_output=True, text=True)   # its /24 goes to the new network
    ensure_net(name, ports)
    r = subprocess.run(run_args(name, image, bind, ports, gpu, udp=udp, sunshine=sunshine, games=games, library=library), capture_output=True, text=True)
    if r.returncode != 0:
        die(f"docker could not create the container: {r.stderr.strip()[:300]}", 1)
    save_settings(name, image, bind, gpu, udp, sunshine, games, library)
    print(f"{container(name)} recreated from {image}{' with the GPU' if gpu else ''}{' and the games profile' if games else ''}, not started. Same folder, ports and login as before."
          + (f" Moonlight: {bind}:{sunshine}." if sunshine else ""))


def create(name, image, bind=None, gpu=False, ports=None, udp=None, sunshine=None, games=False, library=None):
    d = pdir(name)
    limits()                                     # a bad PLACE_MEM must stop us before anything is written
    if games:
        games_options()                          # and so must a host without the games profiles
    library = check_library(library)
    udp = check_udp(udp)
    if os.path.exists(os.path.join(d, ".desktop.env")):
        die(f"{name} already has a place ({d}): remove it first, nothing was changed", 3)
    addr = bind_address(bind)
    if sunshine:
        sunshine_ports(sunshine)
        if sunshine_taken(name, sunshine):
            die(f"the Sunshine ports of base {sunshine} overlap those of {sunshine_taken(name, sunshine)}: pick another base")
    ports = ports or next_ports()
    for sub in ("", "desktop", "input", "output"):
        os.makedirs(os.path.join(d, sub), mode=0o755, exist_ok=True)
    for sub in ("desktop", "input", "output"):   # the container's user (PUID 1000) writes the exports; the gate (the host user, also 1000) reads and fills input/output
        os.chown(os.path.join(d, sub), 1000, 1000) if os.geteuid() == 0 else None
    pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(28))
    fd = os.open(os.path.join(d, ".desktop.env"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"CUSTOM_USER={name}\nPASSWORD={pw}\n")
    with open(os.path.join(d, ".ports"), "w") as f:
        f.write(f"{ports[0]} {ports[1]}\n")
    if sunshine:
        ensure_sunshine_env(name)
    ensure_net(name, ports)
    r = subprocess.run(run_args(name, image, addr, ports, gpu, udp=udp, sunshine=sunshine, games=games, library=library), capture_output=True, text=True)
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
    ex = [DOCKER, "exec", "-u", "1000:1000", container(name), "sh", "-c"]
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
    r = subprocess.run([DOCKER, "exec", "-u", "1000:1000", container(name), "sh", "-c", NOTIFY_SH, "sh", title, body,
                        "critical" if urgent else "normal", str(int(seconds) * 1000)], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        die(f"the notification was not shown: {(r.stderr or r.stdout).strip()[:200]}", r.returncode if r.returncode in (1, 3) else 1)
    print(f"notification shown in {container(name)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["create", "start", "stop", "status", "creds", "rm", "recreate", "gate-token", "pair", "notify"])
    ap.add_argument("name")
    ap.add_argument("pin", nargs="?", help="pair: the PIN; notify: the title")
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
    ap.add_argument("--udp", type=int, action="append", metavar="PORT", help="also publish this UDP port on the place's LAN address (a game's own port); repeat for up to 4; recreate keeps the saved ones, --no-udp clears them")
    ap.add_argument("--no-udp", action="store_true")
    ap.add_argument("--ports", nargs=2, type=int, metavar=("HTTP", "HTTPS"), help="create only: take these two ports (a place that already ran on them)")
    a = ap.parse_args(argv)
    d = pdir(a.name)
    if a.cmd == "create":
        create(a.name, a.image or ("bridgeai-place-steam:latest" if a.games else "bridgeai-place:latest"), a.bind, bool(a.gpu), tuple(a.ports) if a.ports else None, a.udp, a.sunshine, bool(a.games), a.library)
    elif a.cmd == "recreate":
        recreate(a.name, a.image, False if a.no_gpu else a.gpu, a.bind, [] if a.no_udp else a.udp, None if a.no_sunshine else (a.sunshine if a.sunshine else ...), False if a.no_games else a.games, None if a.no_library else (a.library if a.library else ...))
    elif a.cmd == "notify":
        notify(a.name, a.pin or "", a.body or "", a.seconds, not a.normal)
    elif a.cmd == "pair":
        pair(a.name, a.pin)
    elif a.cmd == "gate-token":
        make_gate_token(a.name, a.rotate)
    elif a.cmd == "creds":
        print(os.path.join(d, ".desktop.env"))
    elif a.cmd in ("start", "stop"):
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
