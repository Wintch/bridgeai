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
main{{background:#1d1d1d;padding:2em;border-radius:12px;min-width:300px;max-width:560px}}h1{{font-size:1.3em;margin-top:0}}h2{{font-size:1.05em;margin:1.2em 0 .3em}}
ul{{margin:0;padding-left:1.2em}}li{{margin:.3em 0}}a{{color:#8ab4ff}}nav{{margin:.8em 0}}nav a{{margin-right:1em}}code{{background:#333;padding:0 .3em;border-radius:4px}}
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
    "en": {"title": "Desktop", "user": "User", "pass": "Password", "login": "Log in", "bad": "Wrong user or password.", "slow": "Too many attempts. Wait a few minutes.",
           "asleep": "The machine is resting.", "off": "Your desktop is off.", "starting": "Switching on… (can take up to a minute)", "open": "Your desktop is open.",
           "error": "Could not read the state.", "on": "Switch on", "enter": "Enter the desktop", "close": "Switch the desktop off", "keep": "Keep it open",
           "closes": "It switches off by itself after {m} min without use.", "logout": "Log out"},
}
for _l, _g in (("es", "Guía"), ("ru", "Инструкция"), ("en", "Guide")):
    T[_l]["guide"] = _g

# The how-to on the door, per person: only the parts that person has. A person's entry in door.json may carry "games": true and
# "moonlight": "ADDRESS:PORT" (the address they type in Moonlight); "games": "quake" for a Quake-only place. Each item is one line; {ml} is that
# address; "full|quake-only" picks the second form for a Quake-only place.
GUIDE = {
    "es": {
        "enter": ("Entrar", ["<b>Encender</b>, esperá a que diga que está abierto (hasta un minuto) y <b>Entrar al escritorio</b>.",
                             "Al terminar, <b>Apagar el escritorio</b>. Si te olvidás, se apaga solo a los 30 minutos sin uso (no con un juego abierto).",
                             "Usá Chrome, Edge o Brave. En Firefox el mouse anda peor en los juegos."]),
        "keys": ("En el navegador", ["<b>Ctrl+Shift+X</b>: modo juego (mouse atrapado, todas las teclas van al juego). Se sale con Esc tres veces o Ctrl+Shift+X.",
                                     "<b>Ctrl+Shift+F</b>: pantalla completa. <b>Ctrl+Shift+G</b>: joystick en pantalla."]),
        "games": ("Juegos", ["Menú → Juegos: Steam, Heroic (Epic) y Quake III demo.|Menú → Juegos: Quake III demo.",
                             "Partida entre nosotros: Multiplayer → Local → Refresh; el servidor siempre prendido es <b>BRIDGEAI-LAN</b>.",
                             "Juego colgado: Menú → Juegos → <b>Force-close game</b>."]),
        "moonlight": ("Moonlight (mejor para jugar)", ["Primero encendé el escritorio acá.",
                                                       "En Moonlight: agregar equipo <b>{ml}</b> (con el puerto). La primera vez muestra un PIN: mandalo al admin o a tu bot (<code>escritorio pin NNNN</code>).",
                                                       "Entrá a <b>Desktop</b>. Para juegos, apagá «Optimize mouse for remote desktop» en las opciones de Moonlight.",
                                                       "Los joysticks todavía no pasan por Moonlight."]),
        "trouble": ("Si algo falla", ["«Demasiados intentos»: esperá unos minutos.", "No enciende o no entra: recargá la página en un minuto; si sigue, avisale al admin."]),
    },
    "ru": {
        "enter": ("Вход", ["<b>Включить</b>, подожди, пока не напишет, что открыт (до минуты), и <b>Войти на рабочий стол</b>.",
                           "В конце — <b>Выключить рабочий стол</b>. Если забудешь, он выключится сам через 30 минут без дела (но не с открытой игрой).",
                           "Используй Chrome, Edge или Brave. В Firefox мышь в играх работает хуже."]),
        "keys": ("В браузере", ["<b>Ctrl+Shift+X</b>: игровой режим (мышь захвачена, все клавиши идут в игру). Выход: три раза Esc или Ctrl+Shift+X.",
                                "<b>Ctrl+Shift+F</b>: полный экран. <b>Ctrl+Shift+G</b>: джойстик на экране."]),
        "games": ("Игры", ["Меню → Игры: Steam, Heroic (Epic) и Quake III demo.|Меню → Игры: Quake III demo.",
                           "Игра между нами: Multiplayer → Local → Refresh; постоянный сервер — <b>BRIDGEAI-LAN</b>.",
                           "Игра зависла: Меню → Игры → <b>Force-close game</b>."]),
        "moonlight": ("Moonlight (лучше для игр)", ["Сначала включи рабочий стол здесь.",
                                                    "В Moonlight: добавить компьютер <b>{ml}</b> (с портом). В первый раз он покажет PIN: отправь его админу или своему боту (<code>escritorio pin NNNN</code>).",
                                                    "Открой <b>Desktop</b>. Для игр выключи «Optimize mouse for remote desktop» в настройках Moonlight.",
                                                    "Джойстики через Moonlight пока не работают."]),
        "trouble": ("Если не получается", ["«Слишком много попыток»: подожди несколько минут.", "Не включается или не входит: обнови страницу через минуту; если не помогло — напиши админу."]),
    },
    "en": {
        "enter": ("Getting in", ["<b>Switch on</b>, wait until it says it is open (up to a minute), then <b>Enter the desktop</b>.",
                                 "When done, <b>Switch the desktop off</b>. If you forget, it switches off after 30 minutes without use (not with a game open).",
                                 "Use Chrome, Edge or Brave. In Firefox the mouse works worse in games."]),
        "keys": ("In the browser", ["<b>Ctrl+Shift+X</b>: game mode (mouse captured, every key goes to the game). Leave with Esc three times or Ctrl+Shift+X.",
                                    "<b>Ctrl+Shift+F</b>: fullscreen. <b>Ctrl+Shift+G</b>: on-screen gamepad."]),
        "games": ("Games", ["Menu → Games: Steam, Heroic (Epic) and the Quake III demo.|Menu → Games: the Quake III demo.",
                            "Playing together: Multiplayer → Local → Refresh; the always-on server is <b>BRIDGEAI-LAN</b>.",
                            "A game hung: Menu → Games → <b>Force-close game</b>."]),
        "moonlight": ("Moonlight (better for games)", ["Switch the desktop on here first.",
                                                       "In Moonlight: add host <b>{ml}</b> (with the port). The first time it shows a PIN: send it to the admin or your bot (<code>escritorio pin NNNN</code>).",
                                                       "Open <b>Desktop</b>. For games, turn off “Optimize mouse for remote desktop” in Moonlight's settings.",
                                                       "Gamepads do not pass through Moonlight yet."]),
        "trouble": ("If something fails", ["“Too many attempts”: wait a few minutes.", "It does not switch on or let you in: reload the page in a minute; if it persists, tell the admin."]),
    },
}


def guide_html(lang, person):
    g, p = GUIDE[lang], person or {}
    ml = html.escape(str(p.get("moonlight") or ""))
    keys = ["enter", "keys"] + (["games"] if p.get("games") else []) + (["moonlight"] if ml else []) + ["trouble"]
    out = ""
    for k in keys:
        title, lines = g[k]
        pick = lambda ln: ln.split("|")[1 if p.get("games") == "quake" else 0] if "|" in ln else ln
        out += f"<h2>{title}</h2><ul>" + "".join(f"<li>{pick(ln).format(ml=ml)}</li>" for ln in lines) + "</ul>"
    return out


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
            if (p or {}).get("lang") in T:
                return p["lang"]
            al = self.headers.get("Accept-Language", "")[:5]
            return "ru" if "ru" in al else "en" if al.startswith("en") else "es"

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
            body += f"<p><a href=/_door/guide>{t['guide']}</a></p>" + btn("logout", t["logout"], "sec")
            self.page(lang, body)

        def guide_page(self, s, want):
            who = s["person"]
            lang = want if want in GUIDE else self.lang(who)
            nav = "".join(f"<a href='/_door/guide?l={l}'>{n}</a>" for l, n in (("es", "Español"), ("ru", "Русский"), ("en", "English")) if l != lang)
            self.page(lang, f"<h1>{T[lang]['guide']}: {html.escape(who)}</h1><nav>{nav}<a href=/_door/>←</a></nav>" + guide_html(lang, door.person(who)))

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
            if path == "/_door/guide":
                if not s:
                    return self.redirect("/_door/login")
                m = re.search(r"(?:^|&)l=([a-z]{2})(?:&|$)", self.path.split("?", 1)[1] if "?" in self.path else "")
                return self.guide_page(s, m.group(1) if m else "")
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
