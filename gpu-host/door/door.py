#!/usr/bin/env python3
"""The door: one web front for every place (see ../places/DOOR.md). Runs on an always-on machine behind nginx, which terminates TLS and proxies.

  door.py serve                         the service (listens on 127.0.0.1 only; nginx is the only client)
  door.py passwd PERSON                 sets PERSON's door password (run as root; asked twice on the terminal, stored as a scrypt hash owned by
                                        the door's user; never printed)
  door.py check                         validates the configuration and the secret files, prints what is missing

What it does, per person: a login (password, rate-limited), a page with the person's place (asleep / off / starting / open, the time left) and three
actions: Encender (wakes the GPU host through the wake service when it does not answer, then opens the place through the GPU gate), Entrar (the
desktop, proxied by nginx through this door) and Cerrar. Everything the gate decides stays in the gate: idle clock, open game, hold. The door holds,
per person, only the place's gate token and its basic-auth line (files 0600 owned by the door's user), and never sends either to the browser.

nginx asks GET /_door/auth for every request outside /_door/ (auth_request): 200 with X-Door-Upstream (the place's LAN address:port) and
X-Door-Auth (the place's Authorization header) when the session is valid and the place is open, 401 otherwise (nginx then sends the browser to
the login or the state page). Stdlib only.
"""
import base64, getpass, hashlib, hmac, html, http.server, json, os, re, secrets, socketserver, sys, threading, time, urllib.error, urllib.request

CONF = os.environ.get("DOOR_CONF", "/etc/bridgeai-door/door.json")
NAME_OK = re.compile(r"[a-z][a-z0-9]{1,11}")
SESSION_S = 12 * 3600
FAILS_PER_IP, FAILS_WINDOW = 10, 900          # failed logins one address may make in the window
FAILS_PER_USER = 20                           # failed logins on one name in the window (then that name waits)
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def load_conf(path=None):
    with open(path or CONF) as f:
        c = json.load(f)
    c.setdefault("listen", "127.0.0.1:8095")
    c.setdefault("people", {})
    c.setdefault("secrets_dir", os.path.dirname(path or CONF))
    return c


def hash_password(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, dklen=32, **SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def check_password(pw, stored):
    try:
        kind, salt, h = stored.split("$")
        if kind != "scrypt":
            return False
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), dklen=32, **SCRYPT)
        return hmac.compare_digest(got, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def read_secret(conf, person, kind):
    """kind: 'pass' (scrypt hash), 'token' (the place's gate token), 'basic' (the place's 'Basic ...' header value)."""
    if not NAME_OK.fullmatch(person or ""):
        return ""
    try:
        with open(os.path.join(conf["secrets_dir"], person + "." + kind)) as f:
            return f.read().strip()
    except OSError:
        return ""


class Limits:
    """Failed-login counters by address and by name, in memory (a restart forgets them: acceptable, it is not the only guard)."""

    def __init__(self):
        self.lock, self.by = threading.Lock(), {}

    def _recent(self, key, now):
        v = [t for t in self.by.get(key, []) if now - t < FAILS_WINDOW]
        self.by[key] = v
        return v

    def blocked(self, ip, user, now=None):
        now = time.time() if now is None else now
        with self.lock:
            return len(self._recent("ip:" + ip, now)) >= FAILS_PER_IP or len(self._recent("user:" + user, now)) >= FAILS_PER_USER

    def fail(self, ip, user, now=None):
        now = time.time() if now is None else now
        with self.lock:
            for k in ("ip:" + ip, "user:" + user):
                self._recent(k, now).append(now)
            if len(self.by) > 10000:
                self.by = {k: v for k, v in self.by.items() if v and now - v[-1] < FAILS_WINDOW}


class Sessions:
    def __init__(self):
        self.lock, self.s = threading.Lock(), {}

    def new(self, person, now=None):
        now = time.time() if now is None else now
        sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with self.lock:
            self.s = {k: v for k, v in self.s.items() if v["exp"] > now}
            self.s[sid] = {"person": person, "exp": now + SESSION_S, "csrf": csrf}
        return sid

    def get(self, sid, now=None):
        now = time.time() if now is None else now
        with self.lock:
            v = self.s.get(sid or "")
            return v if v and v["exp"] > now else None

    def drop(self, sid):
        with self.lock:
            self.s.pop(sid or "", None)


def http_json(method, url, token=None, timeout=8):
    req = urllib.request.Request(url, method=method, data=b"{}" if method == "POST" else None,
                                 headers={"Authorization": "Bearer " + token} if token else {})
    if method == "POST":
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (OSError, ValueError):
        return 0, {}


class Door:
    def __init__(self, conf, gate=http_json, now=time.time):
        self.conf, self.gate, self.now = conf, gate, now
        self.sessions, self.limits = Sessions(), Limits()
        self.waking = {}                                  # person -> time Encender was pressed (the page shows "starting")
        self.cache = {}                                   # person -> (time, state): nginx asks /_door/auth on every request

    def state_cached(self, who, ttl=10):
        t, st = self.cache.get(who, (0, None))
        if st is None or self.now() - t > ttl:
            st = self.state(who)
            self.cache[who] = (self.now(), st)
        return st

    def person(self, name):
        return self.conf["people"].get(name) if NAME_OK.fullmatch(name or "") else None

    def state(self, who):
        """{state: asleep|off|starting|open, closes_in_min, ...} of the person's place, from the gate."""
        p = self.person(who)
        code, st = self.gate("GET", self.conf["gate"].rstrip("/") + "/place/state", read_secret(self.conf, who, "token"))
        if code == 0:
            return {"state": "starting" if self.now() - self.waking.get(who, 0) < 180 else "asleep"}
        if code != 200:
            return {"state": "error", "why": st.get("why", code)}
        if st.get("running"):
            self.waking.pop(who, None)
            return {"state": "open", "closes_in_min": st.get("closes_in_min"), "label": p.get("label", who)}
        return {"state": "starting" if self.now() - self.waking.get(who, 0) < 180 else "off"}

    def start(self, who):
        tok, base = read_secret(self.conf, who, "token"), self.conf["gate"].rstrip("/")
        self.waking[who] = self.now()
        code, out = self.gate("POST", base + "/place/start", tok, 120)
        if code == 0 and self.conf.get("wake_url"):         # the host does not answer: it sleeps; wake it and let the page poll
            self.gate("GET", self.conf["wake_url"], None, 10)
            threading.Thread(target=self._start_when_up, args=(who,), daemon=True).start()
            return {"state": "starting"}
        return {"state": "open" if code == 200 else "error", "why": out.get("why")}

    def _start_when_up(self, who, tries=40, every=5):
        tok, base = read_secret(self.conf, who, "token"), self.conf["gate"].rstrip("/")
        for _ in range(tries):
            time.sleep(every)
            code, _ = self.gate("POST", base + "/place/start", tok, 120)
            if code == 200:
                return
            if code not in (0, 502, 503):
                return

    def act(self, who, what):
        self.cache.pop(who, None)
        if what == "start":
            return self.start(who)
        tok, base = read_secret(self.conf, who, "token"), self.conf["gate"].rstrip("/")
        code, out = self.gate("POST", base + {"stop": "/place/stop", "keep": "/place/keep"}[what], tok, 60)
        return {"ok": code == 200, "why": out.get("why")}

    def upstream(self, who):
        p = self.person(who)
        return f"{p['lan']}:{int(p['port'])}" if p and p.get("lan") and p.get("port") else ""


PAGE = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>body{{font:16px system-ui,sans-serif;background:#111;color:#eee;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
main{{background:#1d1d1d;padding:2em;border-radius:12px;min-width:300px;max-width:420px}}h1{{font-size:1.3em;margin-top:0}}
input,button{{font:inherit;padding:.6em .8em;border-radius:8px;border:1px solid #444;background:#222;color:#eee;width:100%;box-sizing:border-box;margin:.3em 0}}
button{{background:#2d6cdf;border:0;cursor:pointer}}button.sec{{background:#444}}.st{{font-size:1.1em;margin:.8em 0}}.err{{color:#f77}}</style></head>
<body><main>{body}</main></body></html>"""

T = {
    "es": {"title": "Escritorio", "user": "Usuario", "pass": "Clave", "login": "Entrar", "bad": "Usuario o clave incorrectos.", "slow": "Demasiados intentos. Esperá unos minutos.",
           "asleep": "La máquina está en reposo.", "off": "Tu escritorio está apagado.", "starting": "Encendiendo… (puede tardar hasta un minuto)", "open": "Tu escritorio está abierto.",
           "error": "No se pudo consultar el estado.", "on": "Encender", "enter": "Entrar al escritorio", "close": "Apagar el escritorio", "keep": "Mantener abierto",
           "closes": "Se apaga solo si nadie lo usa en {m} min.", "logout": "Salir"},
    "ru": {"title": "Рабочий стол", "user": "Логин", "pass": "Пароль", "login": "Войти", "bad": "Неверный логин или пароль.", "slow": "Слишком много попыток. Подожди несколько минут.",
           "asleep": "Машина в режиме ожидания.", "off": "Твой рабочий стол выключен.", "starting": "Включается… (может занять до минуты)", "open": "Твой рабочий стол открыт.",
           "error": "Не удалось узнать состояние.", "on": "Включить", "enter": "Войти на рабочий стол", "close": "Выключить рабочий стол", "keep": "Оставить открытым",
           "closes": "Выключится сам, если им не пользоваться {m} мин.", "logout": "Выйти"},
}


def make_handler(door):
    class H(http.server.BaseHTTPRequestHandler):
        server_version = "door"
        sys_version = ""

        def log_message(self, fmt, *a):
            pass

        def ip(self):
            return (self.headers.get("X-Real-IP") or self.client_address[0])[:64]

        def cookie(self):
            m = re.search(r"(?:^|;\s*)door_s=([A-Za-z0-9_-]{20,64})", self.headers.get("Cookie", ""))
            return m.group(1) if m else ""

        def sess(self):
            return door.sessions.get(self.cookie())

        def lang(self, who=None):
            p = door.person(who) if who else None
            return (p or {}).get("lang") or ("ru" if "ru" in self.headers.get("Accept-Language", "")[:5] else "es")

        def send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=()):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in headers:
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def page(self, lang, body, code=200, headers=()):
            self.send(code, PAGE.format(lang=lang, title=T[lang]["title"], body=body).encode(), headers=headers)

        def redirect(self, to, headers=()):
            self.send(303, b"", headers=(("Location", to),) + tuple(headers))

        def form(self):
            n = min(int(self.headers.get("Content-Length", "0") or 0), 4096)
            raw = self.rfile.read(n).decode("utf-8", "replace")
            return {k: urllib.request.unquote(v.replace("+", " ")) for k, v in (x.split("=", 1) for x in raw.split("&") if "=" in x)}

        def login_page(self, lang, msg=""):
            t = T[lang]
            self.page(lang, f"<h1>{t['title']}</h1>{f'<p class=err>{msg}</p>' if msg else ''}<form method=post action=/_door/login>"
                            f"<input name=u placeholder='{t['user']}' autocomplete=username required maxlength=12>"
                            f"<input name=p type=password placeholder='{t['pass']}' autocomplete=current-password required maxlength=200>"
                            f"<button>{t['login']}</button></form>", 200 if not msg else 401)

        def state_page(self, s):
            who, lang = s["person"], self.lang(s["person"])
            t, st = T[lang], door.state(who)
            c = html.escape(s["csrf"])
            btn = lambda act, label, cls="": f"<form method=post action=/_door/{act}><input type=hidden name=c value='{c}'><button class='{cls}'>{label}</button></form>"
            body = f"<h1>{html.escape(who)}</h1><p class=st>{t.get(st['state'], t['error'])}</p>"
            if st["state"] == "open":
                body += f"<p>{t['closes'].format(m=st.get('closes_in_min', '?'))}</p><form method=get action=/><button>{t['enter']}</button></form>"
                body += btn("keep", t["keep"], "sec") + btn("stop", t["close"], "sec")
            elif st["state"] in ("off", "asleep", "error"):
                body += btn("start", t["on"])
            else:
                body += "<script>setTimeout(()=>location.reload(),5000)</script>"
            body += btn("logout", t["logout"], "sec")
            self.page(lang, body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            s = self.sess()
            if path == "/_door/auth":                      # nginx auth_request: is this session allowed through to its open place?
                if not s:
                    return self.send(401)
                up, basic = door.upstream(s["person"]), read_secret(door.conf, s["person"], "basic")
                if not up or not basic or door.state_cached(s["person"])["state"] != "open":
                    return self.send(403)
                return self.send(200, headers=(("X-Door-Upstream", up), ("X-Door-Auth", basic)))
            if path in ("/_door/", "/_door"):
                return self.state_page(s) if s else self.redirect("/_door/login")
            if path == "/_door/state":
                return self.send(200, json.dumps(door.state(s["person"]) if s else {"state": "login"}).encode(), "application/json") if s else self.send(401)
            if path == "/_door/login":
                return self.redirect("/_door/") if s else self.login_page(self.lang())
            self.send(404, b"not found", "text/plain")

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            f = self.form()
            if path == "/_door/login":
                user, ip = (f.get("u") or "").strip().lower(), self.ip()
                lang = self.lang(user if door.person(user) else None)
                if door.limits.blocked(ip, user, door.now()):
                    return self.login_page(lang, T[lang]["slow"])
                stored = read_secret(door.conf, user, "pass") if door.person(user) else ""
                ok = check_password(f.get("p", ""), stored or hash_password("x", b"0" * 16))     # same work whether the name exists or not
                if not (ok and stored):
                    door.limits.fail(ip, user, door.now())
                    return self.login_page(lang, T[lang]["bad"])
                sid = door.sessions.new(user, door.now())
                return self.redirect("/_door/", headers=(("Set-Cookie", f"door_s={sid}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age={SESSION_S}"),))
            s = self.sess()
            if not s:
                return self.redirect("/_door/login")
            if not hmac.compare_digest(f.get("c", ""), s["csrf"]):
                return self.send(403, b"bad form", "text/plain")
            if path == "/_door/logout":
                door.sessions.drop(self.cookie())
                return self.redirect("/_door/login", headers=(("Set-Cookie", "door_s=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0"),))
            if path in ("/_door/start", "/_door/stop", "/_door/keep"):
                door.act(s["person"], path.rsplit("/", 1)[1])
                return self.redirect("/_door/")
            self.send(404, b"not found", "text/plain")

    return H


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def check(conf):
    problems = []
    if not conf.get("gate"):
        problems.append("no gate URL")
    for who, p in conf["people"].items():
        if not NAME_OK.fullmatch(who):
            problems.append(f"{who}: bad name")
            continue
        for k in ("pass", "token", "basic"):
            fpath = os.path.join(conf["secrets_dir"], f"{who}.{k}")
            if not os.path.isfile(fpath):
                problems.append(f"{who}: missing {fpath}")
            elif os.stat(fpath).st_mode & 0o077:
                problems.append(f"{who}: {fpath} is readable by others (chmod 600)")
        if not p.get("lan") or not p.get("port"):
            problems.append(f"{who}: no lan/port of the place")
    return problems


def main(argv=None):
    a = (argv or sys.argv)[1:]
    if not a or a[0] not in ("serve", "passwd", "check"):
        sys.exit(__doc__)
    conf = load_conf()
    if a[0] == "check":
        p = check(conf)
        print("\n".join(p) if p else "ok")
        sys.exit(1 if p else 0)
    if a[0] == "passwd":
        who = a[1] if len(a) > 1 else ""
        if who not in conf["people"]:
            sys.exit(f"{who!r} is not in {CONF}")
        pw = getpass.getpass("new door password: ")
        if len(pw) < 10 or pw != getpass.getpass("again: "):
            sys.exit("passwords differ or shorter than 10 characters: nothing changed")
        fpath = os.path.join(conf["secrets_dir"], who + ".pass")
        fd = os.open(fpath + ".new", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(hash_password(pw) + "\n")
        if os.geteuid() == 0:                                  # run as root (the folder is root's): the file belongs to the door's user
            import pwd
            u = pwd.getpwnam("door")
            os.chown(fpath + ".new", u.pw_uid, u.pw_gid)
        os.replace(fpath + ".new", fpath)
        print(f"door password for {who} set")
        return
    host, port = conf["listen"].rsplit(":", 1)
    if host not in ("127.0.0.1", "::1"):
        sys.exit("the door listens on localhost only (nginx in front)")
    srv = Server((host, int(port)), make_handler(Door(conf)))
    print(f"door on {host}:{port}, {len(conf['people'])} people", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
