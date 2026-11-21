#!/usr/bin/env python3
"""One person's file access over SFTP (for a backup of their website, images and what the bot keeps for them). Run on the Docker host, from ~/aibridge.

  python3 ops/stack_sftp.py passwd STACK            make a new long random password, store only its hash, print the password ONCE
  python3 ops/stack_sftp.py up STACK [--port N] [--deny a,b]   write stacks/STACK/sftp/docker-compose.yml from what the workdir holds now and start it
  python3 ops/stack_sftp.py down STACK              stop and remove the container (the password and the host key stay)
  python3 ops/stack_sftp.py status STACK            running or not, the folders it shows, and their sizes

Design (decided with the operator, 21/11):
- SFTP only: a chrooted internal-sftp in its own container (sftp/Dockerfile). No shell, no forwarding. ONE account, `persona`, password login: no keys for the
  person to manage. The password is 24 random characters in groups (about 110 bits), only a salted SHA-512 hash is kept (stacks/STACK/sftp/passhash, 0600), and
  OpenSSH slows and blocks a source that fails (3 tries per connection, per-source penalties).
- Read and write on EVERYTHING the person has, except system directories. The chroot shows only the folders this tool mounts: every top-level directory of the
  stack's workdir that does not start with a dot and is not in the deny list (default: jobs, venvs, hub). Dot entries (.gateway-log, key status, preferences,
  packs) are never there: they are the bot's own state, and writing to them is controlling the bot. A directory made later appears after the next `up`.
- The account is uid 0 inside the container (the bot is root in its container, so most files are root's); that is why the chroot and the dropped capabilities
  matter: the container has no other capability than the ones sshd needs, no privileged mode, a read-only image.
- Where it listens: the stack's LAN address (LAN_IP in stacks/STACK/.env) and the port. Reaching it from outside is a port forward only the operator makes.
  The Docker host sleeps by itself: a transfer needs it awake (opening the person's web or Telegram wakes it), and the host must not suspend during one.
- Nothing the person uploads is trusted by the bot: files that arrive this way get the same checks as any other (the file-check skill).
"""
import argparse, json, os, re, secrets, subprocess, sys

ROOT = os.environ.get("AIBRIDGE_ROOT", os.path.expanduser("~/aibridge"))
IMAGE = os.environ.get("SFTP_IMAGE", "aibridge-sftp:latest")
DEFAULT_DENY = ("jobs", "venvs", "hub")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"           # no 0/O/1/I: it is typed by hand
NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


def stack_dir(name):
    return os.path.join(ROOT, "stacks", name)


def exposed(workdir, deny=DEFAULT_DENY):
    """The folders the person sees: top-level directories of the workdir that are not dot entries, not links and not denied."""
    try:
        names = sorted(os.listdir(workdir))
    except OSError:
        return []
    return [n for n in names if not n.startswith(".") and n not in deny and os.path.isdir(os.path.join(workdir, n)) and not os.path.islink(os.path.join(workdir, n))
            and re.fullmatch(r"[A-Za-z0-9._ -]{1,60}", n) and "'" not in n and '"' not in n]


def new_password():
    chars = "".join(secrets.choice(ALPHABET) for _ in range(20))
    return "-".join(chars[i:i + 4] for i in range(0, 20, 4))


def hash_password(pw):
    r = subprocess.run(["openssl", "passwd", "-6", "-stdin"], input=pw + "\n", capture_output=True, text=True, check=True)
    return r.stdout.strip()


def lan_ip(env_path):
    try:
        for line in open(env_path):
            k, _, v = line.strip().partition("=")
            if k == "LAN_IP" and v:
                return v.strip().strip('"')
    except OSError:
        pass
    return "127.0.0.1"


def compose(name, workdir, folders, ip, port, image=IMAGE):
    """The compose file text. Secrets are never in it: the hash is a mounted file."""
    sd = os.path.join(stack_dir(name), "sftp")
    vols = [f"      - {sd}/passhash:/config/passhash:ro", f"      - {sd}/hostkeys:/config/hostkeys"]
    vols += [f"      - {workdir}/{f}:/srv/view/{f}" for f in folders]
    return "\n".join([
        f"# written by ops/stack_sftp.py: do not edit (it is rewritten by `up`)",
        "services:",
        "  sftp:",
        f"    image: {image}",
        f"    container_name: stack-{name}-sftp",
        "    restart: unless-stopped",
        "    read_only: true",
        "    tmpfs: [\"/run\", \"/tmp\"]",
        "    cap_drop: [ALL]",
        "    cap_add: [SYS_CHROOT, SETUID, SETGID, CHOWN, DAC_OVERRIDE, FOWNER, AUDIT_WRITE]",
        "    security_opt: [\"no-new-privileges:true\"]",
        "    mem_limit: 256m",
        "    pids_limit: 64",
        "    ports:",
        f"      - \"{ip}:{port}:2222\"",
        "    volumes:",
        *vols, ""])


def cmd_passwd(name):
    d = os.path.join(stack_dir(name), "sftp")
    os.makedirs(d, mode=0o700, exist_ok=True)
    pw = new_password()
    tmp = os.path.join(d, "passhash.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(hash_password(pw) + "\n")
    os.replace(tmp, os.path.join(d, "passhash"))
    print("User: persona\nPassword (shown once, only its hash is kept):\n\n    " + pw + "\n\nGive it to the person through a private channel. "
          "Run `up` (or `docker restart stack-%s-sftp`) so a running container takes the new one." % name)
    return 0


def cmd_up(name, port, deny):
    sd = os.path.join(stack_dir(name), "sftp")
    if not os.path.exists(os.path.join(sd, "passhash")):
        print("no password yet: run `passwd` first", file=sys.stderr)
        return 1
    workdir = os.path.join(stack_dir(name), "workdir")
    folders = exposed(workdir, tuple(deny))
    if not folders:
        print("nothing to show: the workdir has no folders", file=sys.stderr)
        return 1
    os.makedirs(os.path.join(sd, "hostkeys"), mode=0o700, exist_ok=True)
    path = os.path.join(sd, "docker-compose.yml")
    with open(path, "w") as f:
        f.write(compose(name, workdir, folders, lan_ip(os.path.join(stack_dir(name), ".env")), port))
    r = subprocess.run(["docker", "compose", "-p", f"stack-{name}-sftp", "-f", path, "up", "-d", "--force-recreate"])
    print("shows: " + ", ".join(folders))
    return r.returncode


def cmd_down(name):
    path = os.path.join(stack_dir(name), "sftp", "docker-compose.yml")
    return subprocess.run(["docker", "compose", "-p", f"stack-{name}-sftp", "-f", path, "down"]).returncode


def cmd_status(name):
    workdir = os.path.join(stack_dir(name), "workdir")
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", f"stack-{name}-sftp"], capture_output=True, text=True)
    print("container:", r.stdout.strip() or "not created")
    for f in exposed(workdir):
        du = subprocess.run(["du", "-sh", os.path.join(workdir, f)], capture_output=True, text=True).stdout.split("\t")[0]
        print(f"  {f}  {du}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["passwd", "up", "down", "status"])
    ap.add_argument("stack")
    ap.add_argument("--port", type=int, default=2230)
    ap.add_argument("--deny", default=",".join(DEFAULT_DENY))
    a = ap.parse_args(argv)
    if not NAME.match(a.stack) or not os.path.isdir(stack_dir(a.stack)):
        print("unknown stack", file=sys.stderr)
        return 2
    if not 1024 <= a.port <= 65535:
        print("bad port", file=sys.stderr)
        return 2
    deny = [x for x in a.deny.split(",") if x]
    return {"passwd": lambda: cmd_passwd(a.stack), "up": lambda: cmd_up(a.stack, a.port, deny), "down": lambda: cmd_down(a.stack), "status": lambda: cmd_status(a.stack)}[a.cmd]()


if __name__ == "__main__":
    sys.exit(main())
