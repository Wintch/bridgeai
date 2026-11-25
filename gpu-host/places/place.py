#!/usr/bin/env python3
"""A person's own desktop place on a GPU host: one container (the webtop in Dockerfile.place), one volume folder, one pair of LAN ports, a secret nobody prints.

  place.py create NAME [--image IMG] [--bind IP] [--gpu]   makes the folders, a password (kept 0600, never printed), the container (NOT started)
  place.py start|stop|status NAME                          the container only; a place starts stopped and is started on request
  place.py creds NAME                                      the path of the credentials file (never the password)
  place.py rm NAME                                         removes the container; the person's files stay (delete the folder by hand)

Layout (PLACES_ROOT, default /srv/bridgeai/places): NAME/desktop (the webtop's /config: the person's home), NAME/input and NAME/output (files in and out),
NAME/.desktop.env (CUSTOM_USER and PASSWORD, 0600), NAME/.ports ("3010 3011"). Ports are bound to one LAN address only (PLACE_BIND or --bind), never to
0.0.0.0: the way in from the internet is a separate, on-demand door (PLACES.md). The container runs with no-new-privileges, a 1 GB /dev/shm (browsers need
it) and restart=no, like the operator's own. `--gpu` adds the NVIDIA runtime for Resolve; GPU use still goes through the GPU gate's rules.
Stdlib only. DOCKER overrides the docker binary (the selftest uses a fake one)."""
import argparse, os, re, secrets, string, subprocess, sys

ROOT = os.environ.get("PLACES_ROOT", "/srv/bridgeai/places")
DOCKER = os.environ.get("DOCKER", "docker")
NAME_OK = re.compile(r"[a-z][a-z0-9]{1,19}")
BASE_PORT, STEP = 3010, 10                      # 3000/3001 belong to the first place; each new one takes the next pair of tens


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def pdir(name):
    if not NAME_OK.fullmatch(name or ""):
        die("a place name is 2 to 20 lowercase letters and digits, starting with a letter")
    return os.path.join(ROOT, name)


def container(name):
    return f"place-{name}-desktop"


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


def run_args(name, image, bind, ports, gpu=False, env=None):
    d = pdir(name)
    args = [DOCKER, "create", "--name", container(name), "--security-opt", "no-new-privileges", "--shm-size", "1gb", "--restart", "no",
            "-p", f"{bind}:{ports[0]}:3000", "-p", f"{bind}:{ports[1]}:3001",
            "--env-file", os.path.join(d, ".desktop.env"),
            "-e", "PUID=1000", "-e", "PGID=1000", "-e", "TZ=" + (env or os.environ).get("TZ", "America/Argentina/Buenos_Aires"),
            "-e", "LANG=en_US.UTF-8", "-e", "LANGUAGE=en_US:en", "-e", "LC_ALL=en_US.UTF-8",
            "-v", f"{d}/desktop:/config", "-v", f"{d}/input:/input", "-v", f"{d}/output:/output"]
    if gpu:
        args += ["--runtime", "nvidia", "-e", "NVIDIA_VISIBLE_DEVICES=all", "-e", "NVIDIA_DRIVER_CAPABILITIES=all"]
    return args + [image]


def create(name, image, bind=None, gpu=False):
    d = pdir(name)
    if os.path.exists(os.path.join(d, ".desktop.env")):
        die(f"{name} already has a place ({d}): remove it first, nothing was changed", 3)
    addr = bind_address(bind)
    ports = next_ports()
    for sub in ("", "desktop", "input", "output"):
        os.makedirs(os.path.join(d, sub), mode=0o755, exist_ok=True)
    os.chown(os.path.join(d, "desktop"), 1000, 1000) if os.geteuid() == 0 else None
    pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(28))
    fd = os.open(os.path.join(d, ".desktop.env"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"CUSTOM_USER={name}\nPASSWORD={pw}\n")
    with open(os.path.join(d, ".ports"), "w") as f:
        f.write(f"{ports[0]} {ports[1]}\n")
    r = subprocess.run(run_args(name, image, addr, ports, gpu), capture_output=True, text=True)
    if r.returncode != 0:
        die(f"docker could not create the container: {r.stderr.strip()[:300]}", 1)
    print(f"{container(name)} created, not started. Web (HTTPS): https://{addr}:{ports[1]}  (LAN only). Credentials: {os.path.join(d, '.desktop.env')} (0600, never printed here).")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["create", "start", "stop", "status", "creds", "rm"])
    ap.add_argument("name")
    ap.add_argument("--image", default="bridgeai-place:latest")
    ap.add_argument("--bind")
    ap.add_argument("--gpu", action="store_true")
    a = ap.parse_args(argv)
    d = pdir(a.name)
    if a.cmd == "create":
        create(a.name, a.image, a.bind, a.gpu)
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
