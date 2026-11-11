#!/usr/bin/env python3
"""Set up the Gitea side of `gateway tareas` (aibridge/tareas.py, MULTI_BOT_TASKS.md) for one person: the private organisation, the private
repo "tareas" with issues on, the estado/* labels, one bot user per stack, a token for each bot, one team that reaches that repo
only, and the token written into each stack's Hermes .env. Run it on the Docker host from ~/aibridge (or anywhere that can reach Gitea and,
for the .env step, the stack folders), by the operator:

  printf '%s' "$GITEA_ADMIN_TOKEN" | ops/tareas_setup.py --url https://<gitea-host>[:port] --org <owner-org> \\
      --stack <stack> [--stack <other-stack> ...] [--human <owner's-gitea-user> ...] [--dry-run] [--rotate]

The Gitea admin token (an administrator's token with write:admin, write:organization, write:repository, write:issue and read:user:
Gitea's scope docs put /user and /users/* in the "user" category, which the checks of the admin and of the bot accounts read)
travels on STDIN only: never in argv, never printed, never stored. Without stdin (a terminal) it is asked for without echo.
--dry-run only reads (GET): it prints what it would create and writes nothing, in Gitea or in a .env.

What it does, in order (each step first checks whether it is already done, so a second run changes nothing):
  0. before anything is changed in Gitea: every --stack must have its persist folder here (--aibridge-dir, default the current
     directory) and, when ops/wake/stacks.json is there, be listed in it; otherwise it stops (a typo or the wrong directory would
     leave a token and a bot in Gitea and nothing in the stack);
  1. checks the token belongs to an administrator (GET /user);
  2. the organisation (POST /orgs, visibility private) and the repo (POST /orgs/{org}/repos, private, auto_init, issues on);
  3. the labels estado/pendiente, en-curso, hecho, bloqueado (POST /repos/{o}/{r}/labels, exclusive = scoped);
  4. the team "bots-tareas" (POST /orgs/{org}/teams): includes_all_repositories false, units_map repo.code read and repo.issues
     write, and ONLY the tareas repo added (PUT /teams/{id}/repos/{org}/{repo}). The bots are assignable because of this membership:
     Gitea tokens are scoped by category, not by repo, so the team is what limits a bot to this one repo. A team of that name that
     already exists is used only if it is exactly that narrow (not all repositories, no other repository, repo.code read,
     repo.issues write, every other unit none, no repo creation); otherwise the script stops and nothing is added to it;
  5. per stack: the user bot-<stack> (POST /admin/users, random password that is never shown or kept, not an administrator,
     private; an existing user of that name is touched only if it is not an administrator and its e-mail is the bots' placeholder
     one, and an empty --bot-prefix is refused), its membership of the team, and a token named "tareas" with scopes write:issue and read:repository made with
     the bot's own basic-auth login (POST /users/{bot}/tokens: Gitea documents token creation for the user itself, with
     basic auth, and shows the token once). An existing token named "tareas" is revoked first;
  6. writes GITEA_TAREAS_TOKEN into the stack's persisted Hermes .env (hernik: hermes-config/.env; any other stack:
     stacks/<stack>/persist/.env; mode 600, one backup copy next to it, other lines kept) and, when the stack's container runs, into
     its live /root/.hermes/.env too (start_hermes.sh flushes the live file over the persisted one at the next stop, so writing only
     the persisted one would be undone). The persisted file is root-owned on some hosts: then the write goes through
     `docker run` with the stack's own image, like ops/proxmox_add.sh does;
  7. prints usernames and the last 4 characters of each token, the gateways.json "tareas" entry for the private master
     (no token in it), and the firewall note.

--vigia: also make the account <prefix>vigia, member of the same team, with ONE token named "tareas-vigia" whose scopes are
read:issue and read:repository only, and write it as "poll_token" into ops/wake/tareas_hook.json (the receiver's config, mode 600, which
must exist already). The receiver then polls the board with it when Gitea cannot reach the VM (ops/wake/tareas_hook.py, "Polling"); restart
it afterwards: systemctl --user restart aibridge-tareas-hook. With --vigia, --stack may be left out: then no bot account and no .env is touched.

Only a 404 means "does not exist": any other answer to an existence check (403 for a missing scope, 5xx) stops the script.
A stack that already has GITEA_TAREAS_TOKEN keeps it unless --rotate. A stack whose .env cannot be read here is treated as having none.
Test: aibridge/gateway_tareas_selftest.py runs this script against a fake Gitea (python3 -I gateway_tareas_selftest.py).
"""
import argparse, base64, getpass, json, os, re, secrets, subprocess, sys, urllib.error, urllib.parse, urllib.request

VAR = "GITEA_TAREAS_TOKEN"
TOKEN_NAME = "tareas"
SCOPES = ["write:issue", "read:repository"]
ESTADOS = {"pendiente": "#fbca04", "en-curso": "#1d76db", "hecho": "#0e8a16", "bloqueado": "#d93f0b"}
USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,38}$")
STACK_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
IMAGE = "aibridge-hermes-agent:latest"
TIMEOUT = 20

# Runs wherever the .env lives (here, or inside a container): variable name and value come on stdin, the path in the environment P.
SNIPPET = r"""
import os, shutil, sys
var = sys.stdin.readline().rstrip("\n")
val = sys.stdin.readline().rstrip("\n")
p = os.environ["P"]
lines = open(p).read().splitlines() if os.path.exists(p) else []
if os.path.exists(p):
    shutil.copyfile(p, p + ".tareas-backup")
    os.chmod(p + ".tareas-backup", 0o600)
out = [l for l in lines if l.split("=", 1)[0] != var] + [var + "=" + val]
fd = os.open(p + ".n", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("\n".join(out) + "\n")
os.replace(p + ".n", p)
os.chmod(p, 0o600)
print("ok")
"""


class Abort(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


class Gitea:
    def __init__(self, url, admin_token):
        self.url, self.admin = url.rstrip("/"), admin_token

    def call(self, method, path, body=None, query=None, basic=None):
        url = f"{self.url}/api/v1{path}" + ("?" + urllib.parse.urlencode(query) if query else "")
        if basic:
            auth = "Basic " + base64.b64encode(f"{basic[0]}:{basic[1]}".encode()).decode()
        else:
            auth = "token " + self.admin
        headers = {"Authorization": auth, "Accept": "application/json", "User-Agent": "bridgeai-tareas-setup/1"}
        data = None
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        try:
            with OPENER.open(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=TIMEOUT) as r:
                status, raw = r.status, r.read(4_000_000)
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read(4_000_000)
        except (urllib.error.URLError, OSError):
            raise Abort(f"cannot reach Gitea at {self.url} ({method} {path.split('?')[0]})")
        try:
            parsed = json.loads(raw.decode("utf-8", "replace")) if raw.strip() else None
        except ValueError:
            parsed = None
        return status, parsed

    def need(self, method, path, ok, body=None, query=None, basic=None):
        st, d = self.call(method, path, body, query, basic)
        if st not in ok:
            msg = d.get("message", "") if isinstance(d, dict) else ""
            raise Abort(f"{method} {path.split('?')[0]} answered {st}" + (f": {re.sub(r'[^ -~]', '', str(msg))[:160]}" if msg else ""))
        return d

    def pages(self, path, query=None):
        out, page = [], 1
        while page <= 20:
            d = self.need("GET", path, (200,), query=dict(query or {}, limit=50, page=page))
            if not isinstance(d, list):
                break
            out += d
            if len(d) < 50:
                break
            page += 1
        return out


def stack_paths(aibridge_dir, stack):
    if stack == "hernik":
        return os.path.join(aibridge_dir, "hermes-config"), "aibridge-hermes-agent"
    return os.path.join(aibridge_dir, "stacks", stack, "persist"), f"stack-{stack}-hermes"


def docker(*args, input=None):
    try:
        return subprocess.run(["docker", *args], input=input, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None


def container_running(ct):
    r = docker("inspect", "-f", "{{.State.Running}}", ct)
    return bool(r and r.returncode == 0 and r.stdout.strip() == "true")


def persisted_has_token(aibridge_dir, stack):
    """True / False when the persisted .env could be read, None when it could not (root-owned: then the caller treats it as none)."""
    d, _ = stack_paths(aibridge_dir, stack)
    try:
        return any(l.startswith(VAR + "=") and l.split("=", 1)[1].strip() for l in open(os.path.join(d, ".env")))
    except FileNotFoundError:
        return False
    except OSError:
        return None


def write_env(aibridge_dir, stack, token):
    """The token into the persisted .env (directly, or through docker when the folder is not writable) and the live one when awake."""
    d, ct = stack_paths(aibridge_dir, stack)
    path = os.path.join(d, ".env")
    payload = f"{VAR}\n{token}\n"
    writable = os.access(d, os.W_OK) and (not os.path.exists(path) or os.access(path, os.W_OK))
    if writable:
        r = subprocess.run([sys.executable, "-c", SNIPPET], input=payload, capture_output=True, text=True, env=dict(os.environ, P=path))
        where = "persisted .env"
    else:
        r = docker("run", "--rm", "-i", "--network", "none", "-e", "P=/p/.env", "-v", f"{d}:/p", "--entrypoint", "python3", IMAGE, "-c", SNIPPET, input=payload)
        where = "persisted .env (through docker)"
    if r is None or r.returncode != 0 or "ok" not in r.stdout:
        raise Abort(f"could not write {VAR} into {path} (is the folder there, and may this user write it or run docker?)")
    msg = where
    if container_running(ct):
        r = docker("exec", "-i", "-e", "P=/root/.hermes/.env", ct, "python3", "-c", SNIPPET, input=payload)
        if r is None or r.returncode != 0 or "ok" not in r.stdout:
            raise Abort(f"wrote the persisted .env of {stack} but not its live copy: the next stop of the container would undo it. Run this again once it sleeps")
        msg += " + live copy"
    return msg


def exists(g, path, what):
    """True on 200, False on 404; anything else (403: a token scope is missing or no access; 5xx) stops the script instead of being read as 'absent'."""
    st, d = g.call("GET", path)
    if st == 200:
        return True
    if st == 404:
        return False
    raise Abort(f"cannot tell whether {what} exists: GET {path} answered {st} (a missing token scope such as read:user / read:organization, or no access)")


def known_stacks(aibridge_dir):
    """The stack names of ops/wake/stacks.json, or None when that file is not here (it is private to the host)."""
    try:
        return {x.get("name") for x in json.load(open(os.path.join(aibridge_dir, "ops", "wake", "stacks.json"))).get("stacks", []) if isinstance(x, dict)}
    except (OSError, ValueError, AttributeError):
        return None


def check_stacks(aibridge_dir, stacks):
    """Before Gitea is touched: the folder each token will be written into must exist, and the stack must be one the waker knows."""
    known = known_stacks(aibridge_dir)
    for s in stacks:
        d, _ = stack_paths(aibridge_dir, s)
        if not os.path.isdir(d):
            raise Abort(f"stack {s}: the folder {d} is not there (wrong --aibridge-dir, or a typo in --stack). Nothing was changed in Gitea")
        if known is not None and s not in known:
            raise Abort(f"stack {s} is not listed in ops/wake/stacks.json. Nothing was changed in Gitea")
    if known is None:
        print("note: ops/wake/stacks.json not found here, so the stack names were checked only against their folders")


def team_problem(team, listed_repos, full):
    """Why an existing team is wider than this script's promise (repo.code read + repo.issues write on this one repo), or None."""
    um = team.get("units_map") or {}
    if team.get("includes_all_repositories"):
        return "it includes all repositories"
    if team.get("can_create_org_repo"):
        return "it may create repositories"
    if um.get("repo.code") != "read" or um.get("repo.issues") != "write":
        return "its units are not exactly repo.code read and repo.issues write"
    extra = sorted(k for k, v in um.items() if k not in ("repo.code", "repo.issues") and v not in ("none", "", None))
    if extra:
        return "it has more units: " + ", ".join(extra)
    other = sorted(r.get("full_name", "?") for r in listed_repos if isinstance(r, dict) and str(r.get("full_name", "")).lower() != full.lower())
    if other:
        return "it already reaches other repositories: " + ", ".join(other[:5])
    return None


def bot_problem(user, email_domain):
    """Why an existing account must not be treated as one of our bots, or None."""
    if not isinstance(user, dict) or user.get("is_admin"):
        return "it is an administrator (or its type could not be read)"
    if not str(user.get("email", "")).lower().endswith("@" + email_domain.lower()):
        return f"its e-mail does not end in @{email_domain}, so it is not an account this script made"
    return None


def rand_password():
    return secrets.token_urlsafe(24)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gitea side of gateway tareas (see the docstring of this file)")
    ap.add_argument("--url", required=True)
    ap.add_argument("--org", required=True)
    ap.add_argument("--repo", default="tareas")
    ap.add_argument("--stack", action="append", default=[])
    ap.add_argument("--vigia", action="store_true", help="also make the read-only poller account and write its token into ops/wake/tareas_hook.json")
    ap.add_argument("--human", action="append", default=[])
    ap.add_argument("--team", default="bots-tareas")
    ap.add_argument("--bot-prefix", default="bot-")
    ap.add_argument("--email-domain", default="bots.invalid", help="domain of the bots' placeholder e-mail (never used to send anything)")
    ap.add_argument("--aibridge-dir", default=os.getcwd())
    ap.add_argument("--rotate", action="store_true", help="make a new token even when the stack already has one")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    dry = a.dry_run
    if not re.match(r"^https?://[^/\s@]+$", a.url.rstrip("/")):
        sys.exit("--url must look like https://host[:port] (no path, no credentials)")
    if not a.bot_prefix:
        sys.exit("--bot-prefix must not be empty: a bot name equal to a stack name could be an existing person's account")
    for n in [a.org, a.repo, *a.human]:
        if not USER_RE.match(n):
            sys.exit(f"not a valid Gitea name: {n}")
    stacks = list(dict.fromkeys(a.stack))
    if not stacks and not a.vigia:
        sys.exit("at least one --stack (or --vigia alone)")
    for s in stacks:
        if not STACK_RE.match(s) or not USER_RE.match(a.bot_prefix + s):
            sys.exit(f"not a valid stack name: {s}")
    if sys.stdin.isatty():
        admin = getpass.getpass("Gitea admin token (hidden): ").strip()
    else:
        admin = sys.stdin.readline().strip()
    if not admin or re.search(r"\s", admin):
        sys.exit("no admin token on stdin")
    g = Gitea(a.url, admin)
    tag = "[dry-run] would: " if dry else ""
    full = f"{a.org}/{a.repo}"

    try:
        check_stacks(a.aibridge_dir, stacks)
        me = g.need("GET", "/user", (200,))
        if not isinstance(me, dict) or not me.get("is_admin"):
            raise Abort("that token does not belong to a Gitea administrator (GET /user says is_admin false)")
        print(f"admin token ok (user {me.get('login')})")

        # 2. organisation and repo
        org_ok = exists(g, f"/orgs/{a.org}", f"organisation {a.org}")
        if org_ok:
            print(f"organisation {a.org}: exists")
        else:
            print(f"{tag}create organisation {a.org} (private)")
            if not dry:
                g.need("POST", "/orgs", (201,), {"username": a.org, "visibility": "private", "repo_admin_change_team_access": False, "description": "task board between one person's bots"})
        st, repo = g.call("GET", f"/repos/{full}")
        if st not in (200, 404):
            raise Abort(f"cannot tell whether repo {full} exists: GET answered {st} (a missing token scope such as read:repository, or no access)")
        if st == 200 and isinstance(repo, dict):
            print(f"repo {full}: exists" + ("" if repo.get("private") else "  WARNING: it is PUBLIC, make it private in Gitea"))
            if not repo.get("has_issues"):
                print(f"{tag}switch issues on for {full}")
                if not dry:
                    g.need("PATCH", f"/repos/{full}", (200,), {"has_issues": True})
        else:
            print(f"{tag}create repo {full} (private, issues on, auto_init)")
            if not dry:
                g.need("POST", f"/orgs/{a.org}/repos", (201,), {"name": a.repo, "private": True, "auto_init": True, "default_branch": "main", "description": "tasks between one person's bots"})
        repo_exists = st == 200 or not dry

        # 3. labels
        have = {l["name"] for l in g.pages(f"/repos/{full}/labels")} if repo_exists else set()
        for e, color in ESTADOS.items():
            name = "estado/" + e
            if name in have:
                continue
            print(f"{tag}create label {name}")
            if not dry:
                g.need("POST", f"/repos/{full}/labels", (200, 201), {"name": name, "color": color, "exclusive": True, "description": "tareas entre bots"})

        # 4. team with access to this repo only
        team = None
        if org_ok:
            team = next((t for t in g.pages(f"/orgs/{a.org}/teams") if t.get("name") == a.team), None)
        if team:
            why = team_problem(team, g.pages(f"/teams/{team['id']}/repos"), full)
            if why:
                raise Abort(f"team {a.team} already exists and is wider than this script gives to bots: {why}. Fix it in Gitea or use --team with another name; nothing was added to it")
            print(f"team {a.team}: exists, exactly repo.code read + repo.issues write, no other repository")
        else:
            print(f"{tag}create team {a.team} (not all repositories; repo.code read, repo.issues write)")
            if not dry:
                team = g.need("POST", f"/orgs/{a.org}/teams", (201,), {"name": a.team, "description": "bots that use the task board", "includes_all_repositories": False,
                                                                       "can_create_org_repo": False, "permission": "read",
                                                                       "units_map": {"repo.code": "read", "repo.issues": "write"}})
        if team:
            if not dry:
                g.need("PUT", f"/teams/{team['id']}/repos/{a.org}/{a.repo}", (204,))
            print(f"{tag}team {a.team} -> repo {full} only")

        # 5-6. one bot per stack
        report, bots = [], {s: a.bot_prefix + s for s in stacks}
        for s, bot in bots.items():
            st, user = g.call("GET", f"/users/{bot}")
            if st not in (200, 404):
                raise Abort(f"cannot tell whether user {bot} exists: GET answered {st} (a missing token scope such as read:user, or no access)")
            present = st == 200
            if present:
                why = bot_problem(user, a.email_domain)
                if why:
                    raise Abort(f"user {bot} already exists and {why}: it is not touched (no password reset, no team, no token). Pick another --bot-prefix")
            has = persisted_has_token(a.aibridge_dir, s)
            need_token = a.rotate or not has
            if has and not a.rotate:
                print(f"{bot}: {VAR} already in the .env of {s}: token kept (use --rotate to replace it)")
            elif has is None and not a.rotate:
                print(f"{bot}: cannot read the .env of {s} from here, so it is treated as having no token")
            if dry:
                if not present:
                    print(f"{tag}create user {bot} (not an administrator, private)")
                print(f"{tag}add {bot} to team {a.team}" + (f"; make a token '{TOKEN_NAME}' ({', '.join(SCOPES)}) and write {VAR} into the .env of {s}" if need_token else ""))
                report.append((s, bot, None))
                continue
            pw = rand_password() if (need_token or not present) else None
            if not present:
                g.need("POST", "/admin/users", (201,), {"username": bot, "email": f"{bot}@{a.email_domain}", "password": pw, "must_change_password": False,
                                                          "send_notify": False, "visibility": "private"})
                print(f"{bot}: user created")
            elif need_token:
                g.need("PATCH", f"/admin/users/{bot}", (200,), {"login_name": bot, "source_id": 0, "password": pw, "must_change_password": False})
            if team:
                g.need("PUT", f"/teams/{team['id']}/members/{bot}", (204,))
            tok = None
            if need_token:
                basic = (bot, pw)
                for t in g.call("GET", f"/users/{bot}/tokens", basic=basic)[1] or []:
                    if isinstance(t, dict) and t.get("name") == TOKEN_NAME:
                        g.need("DELETE", f"/users/{bot}/tokens/{TOKEN_NAME}", (204,), basic=basic)
                made = g.need("POST", f"/users/{bot}/tokens", (201,), {"name": TOKEN_NAME, "scopes": SCOPES}, basic=basic)
                tok = (made or {}).get("sha1") or (made or {}).get("token")
                if not tok:
                    raise Abort(f"Gitea made a token for {bot} but did not return it")
                where = write_env(a.aibridge_dir, s, tok)
                print(f"{bot}: token ending ...{tok[-4:]} written to {where} of {s}")
            report.append((s, bot, tok))

        # 7. the read-only poller account (--vigia)
        if a.vigia:
            vig = a.bot_prefix + "vigia"
            cfgp = os.path.join(a.aibridge_dir, "ops", "wake", "tareas_hook.json")
            try:
                hook_cfg = json.load(open(cfgp))
            except (OSError, ValueError):
                raise Abort(f"{cfgp} is missing or unreadable: set up the receiver first (ops/wake/TAREAS_HOOK.md step 1)")
            if not isinstance(hook_cfg, dict):
                raise Abort(f"{cfgp} does not hold a JSON object")
            st, user = g.call("GET", f"/users/{vig}")
            if st not in (200, 404):
                raise Abort(f"cannot tell whether user {vig} exists: GET answered {st}")
            present = st == 200
            if present and bot_problem(user, a.email_domain):
                raise Abort(f"user {vig} already exists and {bot_problem(user, a.email_domain)}: it is not touched")
            need = a.rotate or not hook_cfg.get("poll_token")
            if dry:
                print(f"{tag}{'create user ' + vig + ', ' if not present else ''}add {vig} to team {a.team}"
                      + ("; make a read-only token 'tareas-vigia' (read:issue, read:repository) and write it into ops/wake/tareas_hook.json" if need else "; poll_token kept"))
            else:
                pw = rand_password()
                if not present:
                    g.need("POST", "/admin/users", (201,), {"username": vig, "email": f"{vig}@{a.email_domain}", "password": pw, "must_change_password": False,
                                                              "send_notify": False, "visibility": "private"})
                    print(f"{vig}: user created")
                elif need:
                    g.need("PATCH", f"/admin/users/{vig}", (200,), {"login_name": vig, "source_id": 0, "password": pw, "must_change_password": False})
                if team:
                    g.need("PUT", f"/teams/{team['id']}/members/{vig}", (204,))
                if need:
                    basic = (vig, pw)
                    for t in g.call("GET", f"/users/{vig}/tokens", basic=basic)[1] or []:
                        if isinstance(t, dict) and t.get("name") == "tareas-vigia":
                            g.need("DELETE", f"/users/{vig}/tokens/tareas-vigia", (204,), basic=basic)
                    made = g.need("POST", f"/users/{vig}/tokens", (201,), {"name": "tareas-vigia", "scopes": ["read:issue", "read:repository"]}, basic=basic)
                    tok = (made or {}).get("sha1") or (made or {}).get("token")
                    if not tok:
                        raise Abort(f"Gitea made a token for {vig} but did not return it")
                    hook_cfg["poll_token"] = tok
                    tmp = cfgp + ".tmp"
                    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, "w") as f:
                        json.dump(hook_cfg, f)
                    os.replace(tmp, cfgp)
                    print(f"{vig}: read-only token ending ...{tok[-4:]} written to ops/wake/tareas_hook.json (poll_token); "
                          f"now: systemctl --user restart aibridge-tareas-hook")
                else:
                    print(f"{vig}: poll_token already in ops/wake/tareas_hook.json: kept (use --rotate to replace it)")
    except Abort as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        print("Nothing after this point was done. Running the script again is safe: finished steps are skipped.", file=sys.stderr)
        return 1

    if not report:
        return 0
    print()
    print("Add to ops/gateways.json (private master) under each stack, then run: python3 ops/gateways_sync.py")
    for s, bot, _t in report:
        entry = {"url": a.url.rstrip("/"), "repo": full, "me": bot, "peers": [b for t, b in bots.items() if t != s], "humans": a.human}
        print(f'  "{s}": {{ ... "tareas": {json.dumps(entry)} }}')
    print()
    print("Firewall: a guest stack cannot reach the LAN. For each stack that is a guest, add one line to GUEST_PINHOLES in /etc/default/aibridge-fw (sudo, operator):")
    print("  \"<that stack's subnet> <gitea-host-ip> <gitea-port>\"   then: sudo systemctl restart docker-user-fw   (see aibridge/docker-user-fw.sh)")
    print("Then, for the pack to appear: nothing to do, it exists on a stack once its gateways.json has the \"tareas\" block; the person or operator switches it on with /paquete equipo si.")
    print("The humans listed must be members of the organisation (they open the board in the Gitea web page).")
    if dry:
        print("[dry-run] nothing was changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
