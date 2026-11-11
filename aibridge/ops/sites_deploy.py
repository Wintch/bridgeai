#!/usr/bin/env python3
"""Self-hosted static websites: each site is a git repo; this publishes its branch on the VM, served by the
`sites-web` nginx container by Host name. Whoever may push to the repo (a person's Hermes with a deploy key for that ONE
repo, `gateway web`) can change that site and nothing else: no Cloudflare token, no shell, no other site.

  sites_deploy.py watch [--every S]   loop: publish every site whose branch moved (sites-deploy.service)
  sites_deploy.py run [SITE]          one pass (the same as one loop turn)
  sites_deploy.py status              what each site serves and what its branch has
  sites_deploy.py key SITE            create the site's READ-ONLY key on the VM and print its public key (add it to the
                                      repo as a deploy key WITHOUT write access)
  sites_deploy.py nginx               write the nginx server blocks again and reload sites-web

A publish: fetch the branch into a bare mirror, unpack the commit (`git archive`) into releases/<sha>, check it, then
switch the `current` symlink in one rename (a visitor never sees half a site). The last KEEP releases stay on disk.
A release is REFUSED (the site keeps serving the previous one, the operator gets one alert, it is not retried until the
branch moves) when it has: a symlink or any non-regular file, a path that leaves the folder, no index.html at the root,
a file over MAX_FILE, more than MAX_FILES files or MAX_TOTAL bytes, or text that matches a "deny" pattern (by default
private IPv4 addresses and private keys: the sites are public). Dot files are never unpacked (nor served).
Undo = a git revert pushed to the branch (`gateway web deshacer`); the history is the backup.

Config (private, never in git): ops/sites.json, see ops/sites.json.example. Live tree: ~/sites/<site>/{current,releases}
and ~/sites/_nginx/sites.conf (generated). State: ~/.local/state/bridgeai/sites.json.
"""
import io, json, os, re, shutil, subprocess, sys, tarfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.environ.get("SITES_CONFIG", os.path.join(HERE, "sites.json"))
ROOT = os.environ.get("SITES_ROOT", os.path.expanduser("~/sites"))
STATE = os.environ.get("SITES_STATE", os.path.expanduser("~/.local/state/bridgeai/sites.json"))
KEYS = os.environ.get("SITES_KEYS", os.path.expanduser("~/.ssh/sites"))
CONTAINER = os.environ.get("SITES_CONTAINER", "sites-web")
NOTIFY = os.path.join(HERE, "lib", "notify.py")

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
HOST = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
MAX_FILE = 25 * 1048576          # same ceiling as gateway web (WEB_BIG), so Hermes refuses before we do
MAX_FILES = 20000
MAX_TOTAL = 500 * 1048576
KEEP = 5
TEXT = re.compile(r"\.(html?|css|js|mjs|json|txt|md|xml|svg|webmanifest|csv|ya?ml)$", re.I)
DENY_DEFAULT = [
    r"(?<![\d.])10\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])",
    r"(?<![\d.])192\.168\.\d{1,3}\.\d{1,3}(?![\d.])",
    r"(?<![\d.])172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}(?![\d.])",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
]
FETCH_ALERT_S = 1800              # the git server unreachable this long -> one alert


class Refused(Exception):
    """The commit must not go live; the text says why (paths and counts only)."""


def log(*a):
    print(*a, flush=True)


def load_conf():
    with open(CONF) as f:
        c = json.load(f)
    sites = c.get("sites") or {}
    seen = {}
    for name, s in sites.items():
        if not NAME.match(name):
            raise SystemExit(f"{CONF}: bad site name {name!r} (a-z, 0-9, '-')")
        if not isinstance(s.get("repo"), str) or not s["repo"].startswith("ssh://"):
            raise SystemExit(f"{CONF}: site {name}: \"repo\" must be an ssh:// URL")
        s.setdefault("branch", "main")
        if not re.match(r"^[A-Za-z0-9._/-]{1,100}$", s["branch"]) or ".." in s["branch"]:
            raise SystemExit(f"{CONF}: site {name}: bad branch {s['branch']!r}")
        hosts = s.get("hosts") or []
        if not hosts or not all(isinstance(h, str) and HOST.match(h) for h in hosts):
            raise SystemExit(f"{CONF}: site {name}: \"hosts\" must list its domain names")
        for h in hosts:
            if h in seen:
                raise SystemExit(f"{CONF}: {h} is listed for both {seen[h]} and {name}")
            seen[h] = name
        s["deny"] = [re.compile(p.encode()) for p in DENY_DEFAULT + list(c.get("deny") or []) + list(s.get("deny") or [])]
    return sites


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
    os.replace(tmp, STATE)


def notify(*args):
    if os.path.exists(NOTIFY):
        subprocess.run([sys.executable, NOTIFY, *args], capture_output=True, timeout=60)


def key_path(name):
    return os.path.join(KEYS, name)


def git(mirror, *args, raw=False, name=None, timeout=120):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    if name:
        env["GIT_SSH_COMMAND"] = (f"ssh -i {key_path(name)} -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 "
                                  f"-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile={os.path.join(KEYS, 'known_hosts')}")
    r = subprocess.run(["git", *(["--git-dir", mirror] if mirror else []), *args], capture_output=True, env=env, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"git {args[0]}: {(r.stderr or r.stdout).decode(errors='replace').strip()[-300:]}")
    return r.stdout if raw else r.stdout.decode(errors="replace").strip()


def fetch(name, s):
    """Bring the branch into the bare mirror; returns its commit."""
    mirror = os.path.join(ROOT, name, "mirror.git")
    if not os.path.isdir(mirror):
        os.makedirs(os.path.dirname(mirror), exist_ok=True)
        git(None, "init", "-q", "--bare", mirror)
        os.chmod(mirror, 0o700)         # the mirror is not served (nginx roots are <site>/current)
    git(mirror, "fetch", "-q", "--no-tags", "--prune", s["repo"], f"+refs/heads/{s['branch']}:refs/heads/live", name=name)
    return git(mirror, "rev-parse", "refs/heads/live^{commit}"), mirror


def unpack(mirror, sha, dest, deny):
    """git archive of the commit into dest, after checking every entry. Raises Refused."""
    data = git(mirror, "archive", "--format=tar", sha, raw=True, timeout=300)
    files, total, bad, leaks = 0, 0, [], []
    tf = tarfile.open(fileobj=io.BytesIO(data))
    members = []
    for m in tf.getmembers():
        if m.name == "pax_global_header" or m.type == tarfile.XGLTYPE:
            continue
        p = m.name.rstrip("/")
        parts = p.split("/")
        if p.startswith("/") or any(x in ("", "..") for x in parts):
            bad.append(f"ruta inválida: {p}")
            continue
        if any(x.startswith(".") for x in parts):
            continue                                   # .gitignore, .well-known, .git*: never unpacked, never served
        if m.isdir():
            members.append(m)
            continue
        if not m.isreg():
            bad.append(f"no es un archivo común (symlink u otro): {p}")
            continue
        if m.size > MAX_FILE:
            bad.append(f"pesa más de {MAX_FILE // 1048576} MiB: {p}")
            continue
        files += 1
        total += m.size
        if TEXT.search(p):
            body = tf.extractfile(m).read()
            if any(r.search(body) for r in deny):
                leaks.append(p)
        members.append(m)
    if not any(m.name == "index.html" and m.isreg() for m in members):
        bad.append("falta index.html en la raíz")
    if files > MAX_FILES:
        bad.append(f"{files} archivos (máximo {MAX_FILES})")
    if total > MAX_TOTAL:
        bad.append(f"{total // 1048576} MiB en total (máximo {MAX_TOTAL // 1048576})")
    if leaks:
        bad.append("datos privados (IP de red interna o clave) en: " + ", ".join(sorted(leaks)[:10]))
    if bad:
        raise Refused("; ".join(bad[:8]))
    tmp = dest + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for m in members:
        target = os.path.join(tmp, m.name.rstrip("/"))
        if m.isdir():
            os.makedirs(target, mode=0o755, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target), mode=0o755, exist_ok=True)
        with open(target, "wb") as out:
            shutil.copyfileobj(tf.extractfile(m), out)
        os.chmod(target, 0o644)
        os.utime(target, (m.mtime, m.mtime))
    for d, dirs, _ in os.walk(tmp):
        os.chmod(d, 0o755)
    shutil.rmtree(dest, ignore_errors=True)
    os.rename(tmp, dest)
    return files, total


def switch(name, rel):
    """Point <site>/current at releases/<rel> in one rename."""
    site = os.path.join(ROOT, name)
    link = os.path.join(site, "current")
    tmp = link + ".new"
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(os.path.join("releases", rel), tmp)
    os.replace(tmp, link)


def live_release(name):
    link = os.path.join(ROOT, name, "current")
    return os.path.basename(os.readlink(link)) if os.path.islink(link) else None


def prune(name):
    rels = os.path.join(ROOT, name, "releases")
    cur = live_release(name)
    olds = sorted((e for e in os.listdir(rels) if e != cur and not e.endswith(".tmp")),
                  key=lambda e: os.path.getmtime(os.path.join(rels, e)), reverse=True)
    for e in olds[KEEP - 1:]:
        shutil.rmtree(os.path.join(rels, e), ignore_errors=True)


def publish(name, s, st):
    """One site, one pass. Returns True when something went live."""
    rec = st.setdefault(name, {})
    try:
        sha, mirror = fetch(name, s)
    except Exception as e:                              # git server down, key not added yet...
        rec.setdefault("fetch_failing_since", time.time())
        rec["fetch_error"] = str(e)[-300:]
        if time.time() - rec["fetch_failing_since"] > FETCH_ALERT_S and not rec.get("fetch_alerted"):
            notify("alert", f"site-fetch:{name}", f"sitio {name}: no puedo leer su repo hace más de 30 min ({str(e)[-160:]})")
            rec["fetch_alerted"] = True
        return False
    if rec.pop("fetch_alerted", None):
        notify("resolve", f"site-fetch:{name}", f"sitio {name}: el repo vuelve a responder")
    rec.pop("fetch_failing_since", None)
    rec.pop("fetch_error", None)
    rel = sha[:12]
    if rec.get("live") == sha and live_release(name) == rel:
        return False
    if rec.get("refused") == sha:
        return False
    dest = os.path.join(ROOT, name, "releases", rel)
    try:
        files, total = unpack(mirror, sha, dest, s["deny"])
    except Refused as e:
        rec.update(refused=sha, refused_why=str(e), refused_at=int(time.time()))
        log(f"{name}: {rel} RECHAZADO: {e}")
        notify("alert", f"site:{name}", f"sitio {name}: no publiqué {rel}, sigue la versión anterior. Motivo: {e}", "--quiet", "21600")
        return False
    switch(name, rel)
    if rec.pop("refused", None):
        rec.pop("refused_why", None)
        rec.pop("refused_at", None)
        notify("resolve", f"site:{name}", f"sitio {name}: publicado {rel}")
    rec.update(live=sha, live_at=int(time.time()), files=files, bytes=total)
    log(f"{name}: publicado {rel} ({files} archivos, {total // 1024} KiB)")
    prune(name)
    return True


def nginx_conf(sites):
    out = ["# Generated by ops/sites_deploy.py from ops/sites.json: do not edit (rewritten on every change)."]
    for name, s in sorted(sites.items()):
        out += ["server {", "    listen 8080;", f"    server_name {' '.join(s['hosts'])};",
                f"    root /sites/{name}/current;", "    include /etc/nginx/site-common.conf;", "}"]
    return "\n".join(out) + "\n"


def write_nginx(sites, force=False):
    """Rewrite the server blocks when the site list changed, test them and reload sites-web."""
    d = os.path.join(ROOT, "_nginx")
    os.makedirs(d, exist_ok=True)
    for x in (ROOT, d):
        os.chmod(x, 0o755)              # nginx reads it as another user (uid 101): never depend on the umask
    path = os.path.join(d, "sites.conf")
    new = nginx_conf(sites)
    try:
        old = open(path).read()
    except FileNotFoundError:
        old = None
    if old == new and not force:
        return
    with open(path + ".tmp", "w") as f:
        f.write(new)
    os.chmod(path + ".tmp", 0o644)
    os.replace(path + ".tmp", path)
    if subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER], capture_output=True, text=True).stdout.strip() != "true":
        log(f"nginx: {CONTAINER} no está corriendo; toma la config al arrancar")
        return
    t = subprocess.run(["docker", "exec", CONTAINER, "nginx", "-t", "-q"], capture_output=True, text=True)
    if t.returncode:
        if old is not None:
            with open(path, "w") as f:
                f.write(old)
        notify("alert", "sites-nginx", f"sites-web: la config nueva no pasa nginx -t, dejé la anterior: {t.stderr.strip()[-200:]}")
        raise SystemExit("nginx -t failed: " + t.stderr.strip()[-300:])
    subprocess.run(["docker", "exec", CONTAINER, "nginx", "-s", "reload"], capture_output=True, check=True)
    log(f"nginx: {len(sites)} sitio(s), recargado")


def run_once(only=None):
    sites = load_conf()
    if only and only not in sites:
        raise SystemExit(f"no site {only!r} in {CONF}")
    st = load_state()
    for name, s in sites.items():
        if only and name != only:
            continue
        os.makedirs(os.path.join(ROOT, name, "releases"), exist_ok=True)
        for x in (ROOT, os.path.join(ROOT, name), os.path.join(ROOT, name, "releases")):
            os.chmod(x, 0o755)
        try:
            publish(name, s, st)
        except Exception as e:                         # one broken site never stops the others
            log(f"{name}: error: {e}")
            st.setdefault(name, {})["error"] = str(e)[-300:]
        else:
            st.get(name, {}).pop("error", None)
    save_state(st)
    write_nginx(sites)


def watch(every):
    while True:
        try:
            run_once()
        except SystemExit as e:                        # bad config: say it, keep the sites as they are, try again later
            log(str(e))
        time.sleep(every)


def status():
    sites, st = load_conf(), load_state()
    for name, s in sites.items():
        r = st.get(name, {})
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["live_at"])) if r.get("live_at") else "-"
        print(f"{name}: {' '.join(s['hosts'])}  sirve {live_release(name) or 'nada'} desde {when}"
              f"  ({r.get('files', 0)} archivos)")
        if r.get("refused"):
            print(f"  RECHAZADO {r['refused'][:12]}: {r.get('refused_why')}")
        if r.get("fetch_error"):
            print(f"  no lee el repo: {r['fetch_error']}")
        if r.get("error"):
            print(f"  error: {r['error']}")


def make_key(name):
    if name not in load_conf():
        raise SystemExit(f"add {name!r} to {CONF} first")
    os.makedirs(KEYS, mode=0o700, exist_ok=True)
    k = key_path(name)
    if not os.path.exists(k):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"sites-deploy-{name}", "-f", k], check=True)
    print("Add this key to the site's repo as a deploy key, READ-ONLY (do not tick write access):\n")
    print(open(k + ".pub").read())


def main(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "watch":
        every = int(argv[2]) if len(argv) > 2 and argv[1] == "--every" else 20
        watch(max(every, 5))
    elif cmd == "run":
        run_once(argv[1] if len(argv) > 1 else None)
    elif cmd == "status":
        status()
    elif cmd == "key" and len(argv) == 2:
        make_key(argv[1])
    elif cmd == "nginx":
        write_nginx(load_conf(), force=True)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
