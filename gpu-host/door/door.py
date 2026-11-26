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
    c.setdefault("desktops_dir", "/usr/local/share/bridgeai-door/desktops")     # the showroom's previews (desktops/*.webp of the repo)
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


def http_json(method, url, token=None, timeout=8, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body or {}).encode() if method == "POST" else None,
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
        self.choice = {}                                  # person -> the desktop look they last chose here
        self.woke, self.timings = {}, []                  # person -> the host was asleep at Encender; [(kind, seconds)] of the last starts

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
        host = st.get("host") if isinstance(st.get("host"), dict) else None
        if st.get("running"):
            t0 = self.waking.pop(who, None)
            if t0:                                        # how long this start took: the next estimate learns from it
                self.timings.append(("wake" if self.woke.pop(who, False) else "warm", round(self.now() - t0)))
                del self.timings[:-20]
            return {"state": "open", "closes_in_min": st.get("closes_in_min"), "label": p.get("label", who), "host": host, "prep": st.get("prep")}
        return {"state": "starting" if self.now() - self.waking.get(who, 0) < 180 else "off", "host": host}

    def eta(self, who):
        """(seconds left, estimate) while a start is under way: the median of the last starts of the same kind (host asleep or awake)."""
        t0 = self.waking.get(who)
        if not t0:
            return None
        kind = "wake" if self.woke.get(who) else "warm"
        past = sorted(sec for k, sec in self.timings if k == kind)[-5:]
        est = past[len(past) // 2] if past else (60 if kind == "wake" else 20)
        return max(0, round(est - (self.now() - t0))), est

    def desktop(self, who):
        """The look this person last chose (kept while the door runs), else their door.json default, else the first ready one."""
        d = self.choice.get(who) or (self.person(who) or {}).get("desktop")
        return d if d in READY else READY[0]

    def start(self, who, desktop=None):
        tok, base = read_secret(self.conf, who, "token"), self.conf["gate"].rstrip("/")
        if desktop in READY:
            self.choice[who] = desktop
        desktop = self.desktop(who)
        self.waking[who] = self.now()
        code, out = self.gate("POST", base + "/place/start", tok, 120, body={"desktop": desktop})
        self.woke[who] = code == 0
        if code == 0 and self.conf.get("wake_url"):         # the host does not answer: it sleeps; wake it and let the page poll
            self.gate("GET", self.conf["wake_url"], None, 10)
            threading.Thread(target=self._start_when_up, args=(who, desktop), daemon=True).start()
            return {"state": "starting"}
        return {"state": "open" if code == 200 else "error", "why": out.get("why")}

    def _start_when_up(self, who, desktop=None, tries=40, every=5):
        tok, base = read_secret(self.conf, who, "token"), self.conf["gate"].rstrip("/")
        for _ in range(tries):
            time.sleep(every)
            code, _ = self.gate("POST", base + "/place/start", tok, 120, body={"desktop": desktop} if desktop else None)
            if code == 200:
                return
            if code not in (0, 502, 503):
                return

    def act(self, who, what, desktop=None):
        self.cache.pop(who, None)
        if what == "start":
            return self.start(who, desktop)
        tok, base = read_secret(self.conf, who, "token"), self.conf["gate"].rstrip("/")
        code, out = self.gate("POST", base + {"stop": "/place/stop", "keep": "/place/keep"}[what], tok, 60)
        return {"ok": code == 200, "why": out.get("why")}

    def upstream(self, who):
        p = self.person(who)
        return f"{p['lan']}:{int(p['port'])}" if p and p.get("lan") and p.get("port") else ""


PAGE = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{--bg:#1c2233;--surface:#262d42;--line:#3a4360;--text:#ece8de;--muted:#9aa4b8;--amber:#f0b44c;--stop:#e06a5c;
font:16px/1.5 Ubuntu,Cantarell,"Segoe UI Variable","Segoe UI",system-ui,sans-serif;color:var(--text);background:var(--bg)}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center}}
main{{background:var(--surface);padding:2rem;border-radius:14px;width:min(100% - 2rem,420px);box-sizing:border-box;margin:1rem}}
main:has(.show),main:has(.guide){{width:min(100% - 2rem,920px)}}
h1{{font-size:1.875rem;line-height:1.2;margin:0 0 .25rem;font-weight:500}}h2{{font-size:1.3rem;font-weight:500;margin:1.6rem 0 .5rem}}
p{{margin:.4rem 0}}.st{{color:var(--muted);margin-bottom:1.2rem}}.err{{color:var(--stop)}}a{{color:var(--amber)}}
ul{{margin:0;padding-left:1.2em}}li{{margin:.35em 0;line-height:1.5}}nav{{margin:.8em 0}}nav a{{margin-right:1em}}
code{{background:var(--bg);padding:0 .3em;border-radius:4px}}
kbd{{background:var(--bg);border:1px solid var(--line);border-bottom-width:2px;border-radius:5px;padding:0 .35em;font-size:.85em;white-space:nowrap}}
input,button{{font:inherit;padding:.65em .9em;border-radius:9px;border:1px solid var(--line);background:var(--bg);color:var(--text);width:100%;box-sizing:border-box;margin:.3em 0}}
button{{background:var(--amber);color:var(--bg);border:0;cursor:pointer;font-weight:500}}button.sec{{background:#343c55;color:var(--text)}}button.stop{{background:transparent;color:var(--stop);border:1px solid var(--stop)}}
button:disabled{{background:transparent;color:var(--muted);border:1px dashed var(--line);cursor:default}}
:focus-visible{{outline:2px solid var(--amber);outline-offset:2px}}
.row{{display:flex;gap:.6rem;flex-wrap:wrap}}.row form{{flex:1 1 10rem}}.foot{{margin-top:1.6rem;display:flex;gap:1rem;align-items:center;color:var(--muted)}}.foot form button{{width:auto;padding:.4em .9em}}
.screen{{position:relative;aspect-ratio:16/9;background:#000;border-radius:10px;border:10px solid #0d1019;border-bottom-width:16px;overflow:hidden}}
.screen img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;transition:opacity .18s}}
.picks{{display:grid;grid-template-columns:repeat(auto-fit,minmax(9.5rem,1fr));gap:.7rem;margin:1rem 0 .6rem;border:0;padding:0}}
.picks input{{position:absolute;opacity:0;width:1px;height:1px}}
.pick{{display:block;cursor:pointer;border:2px solid transparent;border-radius:10px;padding:.35rem;background:var(--bg)}}
.pick img{{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:6px}}.pick b{{display:block;font-weight:500;margin:.35rem .2rem 0}}
.pick small{{display:block;color:var(--muted);margin:0 .2rem .15rem}}.pick.soon{{border:2px dashed var(--line)}}
.picks input:focus-visible+.pick{{outline:2px solid var(--amber);outline-offset:2px}}.picks input:checked+.pick{{border:2px solid var(--amber)}}
.say,.go{{display:none}}
.load{{margin-top:1.6rem;padding-top:1rem;border-top:1px solid var(--line)}}.load h2{{margin-top:0}}
.load dl{{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.4rem 1.2rem;margin:.6rem 0}}.load dt{{color:var(--muted);font-size:.9rem}}
.load dd{{margin:0;font-variant-numeric:tabular-nums}}.bar{{display:block;height:6px;border-radius:3px;background:var(--bg);margin:.25rem 0;position:relative;overflow:hidden}}
.bar::after{{content:"";position:absolute;inset:0 auto 0 0;width:var(--v);background:var(--muted)}}.bar.hot::after{{background:var(--stop)}}
@media (prefers-reduced-motion:reduce){{.screen img{{transition:none}}}}
{extra}</style></head>
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
# The showroom: the desktops a person can pick at the door. "ready" ones can be chosen (the gate passes the word to the place, which applies it
# live); the others are shown so people see what is coming. Names and descriptions per language; img is a preview in desktops_dir.
DESKTOPS = [
    {"id": "moderno", "img": "xfce-moderno.webp", "ready": True,
     "es": ("XFCE moderno", "Oscuro, con íconos nuevos y un fondo suave."),
     "ru": ("XFCE современный", "Тёмная тема, новые иконки и мягкий фон."),
     "en": ("XFCE modern", "Dark, with new icons and a soft background.")},
    {"id": "clasico", "img": "xfce-clasico.webp", "ready": True,
     "es": ("XFCE clásico", "El escritorio de siempre: liviano y sin vueltas."),
     "ru": ("XFCE классический", "Привычный рабочий стол: лёгкий и простой."),
     "en": ("XFCE classic", "The usual desktop: light and simple.")},
    {"id": "kde", "img": "kde.webp", "ready": False,
     "es": ("KDE Plasma", "Completo y vistoso, con una barra como la de Windows. Lo estamos preparando."),
     "ru": ("KDE Plasma", "Полный и красивый, с панелью как в Windows. Готовим."),
     "en": ("KDE Plasma", "Complete and polished, with a Windows-like bar. Being prepared.")},
]
READY = [d["id"] for d in DESKTOPS if d["ready"]]
# Which preview, description and button show: pure CSS on the checked radio (no script on the page).
SHOW_CSS = "".join(f".show:has(#d-{d['id']}:checked) [data-d={d['id']}]{{display:block;opacity:1}}" for d in DESKTOPS)
LOAD_T = {"es": {"title": "La máquina ahora", "cpu": "Procesador", "mem": "Memoria", "gpu": "Placa de video", "vram": "Memoria de video",
                 "light": "Liviana: hay lugar para algo pesado.", "mid": "Con carga: algo pesado puede ir más lento.", "full": "A tope: mejor esperar para algo pesado.",
                 "open": "Escritorios abiertos: {n}", "asleep": "La máquina descansa: Encender la despierta.",
                 "eta": "Listo en unos {s} s.", "late": "Tarda más de lo normal; sigue encendiendo.",
                 "prep": "Diagnóstico: Steam prepara los shaders de {g} ({p}%).", "took": "Diagnóstico: últimos encendidos {t}."},
          "ru": {"title": "Машина сейчас", "cpu": "Процессор", "mem": "Память", "gpu": "Видеокарта", "vram": "Видеопамять",
                 "light": "Свободна: можно запускать что-то тяжёлое.", "mid": "Под нагрузкой: тяжёлое может идти медленнее.", "full": "На пределе: тяжёлое лучше отложить.",
                 "open": "Открытых рабочих столов: {n}", "asleep": "Машина отдыхает: «Включить» её разбудит.",
                 "eta": "Будет готово примерно через {s} с.", "late": "Дольше обычного; всё ещё включается.",
                 "prep": "Диагностика: Steam готовит шейдеры {g} ({p}%).", "took": "Диагностика: последние включения {t}."},
          "en": {"title": "The machine now", "cpu": "Processor", "mem": "Memory", "gpu": "Graphics card", "vram": "Video memory",
                 "light": "Light: there is room for something heavy.", "mid": "Busy: something heavy may run slower.", "full": "Full: better wait for anything heavy.",
                 "open": "Desktops open: {n}", "asleep": "The machine is resting: Switch on wakes it.",
                 "eta": "Ready in about {s} s.", "late": "Taking longer than usual; still switching on.",
                 "prep": "Diagnostic: Steam is preparing {g}'s shaders ({p}%).", "took": "Diagnostic: last starts {t}."}}


def load_html(lang, host, state):
    """The machine's load as four meters and one plain verdict; the same for everybody, numbers only."""
    t = LOAD_T[lang]
    if state == "asleep" or not host:
        return f"<section class=load><p class=st>{t['asleep'] if state == 'asleep' else ''}</p></section>" if state == "asleep" else ""
    pct = lambda a, b: round(100 * float(a) / float(b)) if a not in (None, "") and b not in (None, "", 0, "0") else None
    rows = [("cpu", host.get("cpu_pct"), f"{host.get('cpu_pct', '?')}% · {host.get('cores', '?')}"),
            ("mem", pct(host.get("mem_used_gb"), host.get("mem_total_gb")), f"{host.get('mem_used_gb', '?')} / {host.get('mem_total_gb', '?')} GB"),
            ("gpu", None if host.get("gpu_pct") in (None, "") else round(float(host["gpu_pct"])), f"{host.get('gpu_pct', '?')}%".replace(".0%", "%")),
            ("vram", pct(host.get("vram_used_mb"), host.get("vram_total_mb")),
             f"{round(float(host.get('vram_used_mb') or 0) / 1024, 1)} / {round(float(host.get('vram_total_mb') or 0) / 1024, 1)} GB")]
    vals = [v for _, v, _ in rows if isinstance(v, (int, float))]
    top = max(vals) if vals else 0
    verdict = t["light"] if top < 50 else t["mid"] if top < 85 else t["full"]
    out = f"<section class=load aria-label='{t['title']}'><h2>{t['title']}</h2><p>{verdict}</p><dl>"
    for k, v, txt in rows:
        if v is None:
            continue
        v = max(0, min(100, int(v)))
        out += f"<div><dt>{t[k]}</dt><dd><span class='bar{' hot' if v >= 85 else ''}' style='--v:{v}%'></span>{html.escape(txt)}</dd></div>"
    return out + f"</dl><p class=st>{t['open'].format(n=int(host.get('places_running') or 0))}</p></section>"


SHOW_T = {"es": {"pick": "Elegí tu escritorio", "on": "Encender con {n}", "change": "Cambiar a {n}", "soon": "Pronto", "now": "Ahora: {n}"},
          "ru": {"pick": "Выбери рабочий стол", "on": "Включить: {n}", "change": "Сменить на {n}", "soon": "Скоро", "now": "Сейчас: {n}"},
          "en": {"pick": "Pick your desktop", "on": "Switch on with {n}", "change": "Switch to {n}", "soon": "Soon", "now": "Now: {n}"}}

for _l, _g in (("es", "Guía"), ("ru", "Инструкция"), ("en", "Guide")):
    T[_l]["guide"] = _g

# The how-to on the door: one guide per way in (the browser, Moonlight), each a flow drawn in plain HTML (nothing loaded from outside) and short
# lists. Per person, only what they have: door.json may carry "games": true (or "quake" for a Quake-only place) and "moonlight": "ADDRESS:PORT"
# (what they type in Moonlight; no Moonlight guide without it). "full|quake-only" lines pick the second form for a Quake-only place; {ml} is the address.
K = lambda *keys: "+".join(f"<kbd>{k}</kbd>" for k in keys)
GUIDE = {'es': {'tabs': {'web': 'Navegador', 'moonlight': 'Moonlight'},
        'web': {'flow': ['Encender', 'Entrar al escritorio', 'Jugar con <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd>', 'Apagar el escritorio'],
                'sections': [['Paso a paso',
                              ['<b>Encender con …</b> (debajo de «Elegí tu escritorio»): abre tu escritorio con el aspecto elegido y, si la máquina duerme, '
                               'primero la despierta.',
                               'Si la máquina dormía, mientras despierta verás «Listo en unos N s», calculado con los últimos encendidos; la página se '
                               'actualiza sola.',
                               '<b>Entrar al escritorio</b>: lo abre a través de esta página, sin otra contraseña.',
                               'Al terminar, volvé acá y <b>Apagar el escritorio</b>: libera la máquina para los demás. Tus archivos quedan.',
                               'Ojo: <b>Apagar el escritorio</b> cierra también un juego abierto, sin guardar. Guardá la partida antes.']],
                             ['Si te olvidás de apagarlo',
                              ['Se apaga solo tras 30 minutos sin uso: tocar el escritorio, un juego abierto o un trabajo pesado cuentan como uso.',
                               'Una pestaña abierta que nadie toca no cuenta. Un juego abierto sí, aunque esté en pausa en un menú.',
                               'El escritorio avisa 10, 5 y 1 minuto antes; si tenés bot, el primer aviso también te llega por ahí.',
                               'Para seguir: mové el mouse, tocá <b>Mantener abierto</b> acá o decile a tu bot <code>escritorio seguir</code>.']],
                             ['La máquina ahora',
                              ['Abajo, en esta página, ves la carga de la máquina compartida: procesador, memoria, placa de video y su memoria.',
                               '<b>Liviana</b>: hay lugar para algo pesado. <b>Con carga</b>: puede ir más lento. <b>A tope</b>: mejor esperar.',
                               'Una barra en rojo pasa el 85%. «Escritorios abiertos» dice cuántos hay, sin nombres.',
                               'Si la máquina descansa, solo <b>Encender</b> desde esta página la despierta; el bot no puede.']],
                             ['Atajos',
                              ['<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd> modo juego: pantalla completa, mouse atrapado y todas las teclas al juego. '
                               'Arregla el mouse en juegos en primera persona.',
                               '<kbd>Esc</kbd> tres veces seguidas, o <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd> de nuevo: salir del modo juego.',
                               '<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F</kbd> solo pantalla completa · <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> joystick '
                               'en pantalla.']],
                             ['Navegador y joystick',
                              ['Chrome, Edge o Brave. En Firefox el mouse anda peor en los juegos.',
                               'Joystick: uno conectado por ahora no anda en el navegador. <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> muestra uno en '
                               'pantalla, todavía en prueba.']],
                             ['Tu escritorio',
                              ['Es tuyo: red propia y salida solo a internet; no ve tu red ni otros escritorios, salvo el puerto de juego para jugar juntos.',
                               'Tu carpeta no se revisa ni se copia sin tu permiso.',
                               'No hay sudo: instalá en tu carpeta con AppImage, proot-apps o <code>pip --user</code>.']]]},
        'moonlight': {'flow': ['Encender acá',
                               'Moonlight → Desktop',
                               'Jugar',
                               'Salir con <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>Q</kbd>',
                               'Apagar acá'],
                      'sections': [['La primera vez',
                                    ['Instalá Moonlight (moonlight-stream.org) y agregá el equipo <b>{ml}</b>, con el puerto.',
                                     'Con el escritorio encendido, Moonlight muestra un PIN de 4 cifras que dura menos de un minuto.',
                                     'Mandalo enseguida al admin o a tu bot: <code>escritorio pin NNNN</code>.',
                                     'En Ajustes: resolución 1080p y apagá «Optimize mouse for remote desktop».']],
                                   ['Cada vez',
                                    ['Primero <b>Encender</b> en esta página.',
                                     'En Moonlight: el equipo → <b>Desktop</b>. La pantalla se ajusta al tamaño de tu equipo.',
                                     'Donde hay Steam también aparecen <b>Steam Big Picture</b> y cada juego instalado (los de Steam, con su portada).',
                                     'Al terminar, salí de Moonlight y <b>Apagar el escritorio</b> acá: cerrar Moonlight no lo apaga.']],
                                   ['Atajos',
                                    ['<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>Q</kbd> salir de Moonlight.',
                                     '<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> soltar o atrapar el mouse.',
                                     '<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd> pantalla completa o ventana · '
                                     '<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd> estadísticas.']],
                                   ['Tus equipos',
                                    ['<code>escritorio dispositivos</code> le pide a tu bot la lista de equipos emparejados.',
                                     '<code>escritorio revocar NOMBRE</code> quita uno, que tendrá que emparejarse de nuevo. Las dos, con el escritorio '
                                     'abierto.']],
                                   ['Todavía no', ['Los joysticks no pasan por Moonlight.']]]},
        'games': ['Juegos y escritorio',
                  ['Menú → Games: Steam, Heroic (Epic) y Quake III demo.|Menú → Games: Quake III demo.',
                   'La primera vez Steam se instala en tu carpeta (unos minutos). Entrás con tu propia cuenta de Steam o Epic.|Quake III demo arranca llenando '
                   'la ventana, o en una ventana de 1280×720.',
                   'Cada juego instalado tiene su ícono en el escritorio en menos de un minuto; si lo desinstalás, el ícono se va.|Quake y Force-close game '
                   'tienen su ícono en el escritorio.',
                   'Elegí el aspecto en esta página: <b>XFCE moderno</b> (oscuro, íconos nuevos, fondo suave) o <b>XFCE clásico</b> (el de siempre, liviano).',
                   'Con el escritorio abierto, el cambio se aplica en segundos, sin reiniciar. KDE Plasma llega pronto.',
                   'En la barra de arriba: <b>Máquina</b> (toda la máquina), <b>Mío</b> (tu escritorio contra su tope de CPU) y <b>GPU</b>.',
                   'Si varios usan la máquina, un escritorio con un juego abierto tiene prioridad de CPU.',
                   'Jugar juntos en Quake: Multiplayer → Local → Refresh y elegí el servidor compartido o la partida de otro.',
                   'Pronto: el <b>coop de la semana</b>, un juego para jugar todos juntos; cada uno con su cuenta y su copia comprada.',
                   'Juego colgado: Menú → Games → <b>Force-close game</b>. Cierra juegos de Windows (Proton) y Quake; Steam queda abierto.|Juego colgado: Menú '
                   '→ Games → <b>Force-close game</b> cierra Quake; el escritorio sigue.',
                   'Force-close game no cierra juegos nativos de Linux: ahí, cerralo desde su ventana o avisale al admin.|Si Quake no responde ni así, avisale '
                   'al admin.']],
        'trouble': ['Si algo falla',
                    ['«Demasiados intentos»: esperá unos minutos y probá de nuevo.',
                     '«Tarda más de lo normal»: sigue encendiendo; dale un rato más.',
                     'No entra: recargá en un minuto. <b>Entrar al escritorio</b> solo anda con el escritorio abierto.',
                     'El mouse se escapa en un juego: <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd>, y usá Chrome, Edge o Brave.',
                     'La sesión de esta página dura 12 horas; después volvé a entrar con tu usuario.',
                     'Si sigue fallando, avisale al admin y contale qué decía la página.']]},
 'ru': {'tabs': {'web': 'Браузер', 'moonlight': 'Moonlight'},
        'web': {'flow': ['Включить', 'Войти на рабочий стол', 'Играть с <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd>', 'Выключить рабочий стол'],
                'sections': [['По шагам',
                              ['<b>Включить: …</b> (под «Выбери рабочий стол»): открывает стол в выбранном виде, а если машина спит, сначала будит её.',
                               'Если машина спала, пока она просыпается, видно «Будет готово примерно через N с» — по прошлым включениям; страница обновляется сама.',
                               '<b>Войти на рабочий стол</b>: открывает его через эту страницу, без другого пароля.',
                               'В конце вернись сюда и нажми <b>Выключить рабочий стол</b>: машина освободится для других. Файлы останутся.',
                               'Внимание: <b>Выключить рабочий стол</b> закрывает и открытую игру, без сохранения. Сохранись заранее.']],
                             ['Если забудешь выключить',
                              ['Он выключится сам через 30 минут без дела. Дело — это работа за столом, открытая игра или тяжёлая задача (рендер).',
                               'Открытая вкладка, которую никто не трогает, не считается. Открытая игра считается, даже на паузе в меню.',
                               'Рабочий стол предупредит за 10, 5 и 1 минуту; если у тебя есть бот, первое предупреждение придёт и туда.',
                               'Чтобы продолжить: подвигай мышью, нажми здесь <b>Оставить открытым</b> или напиши боту <code>escritorio seguir</code>.']],
                             ['Машина сейчас',
                              ['Внизу этой страницы видна нагрузка общей машины: процессор, память, видеокарта и её память.',
                               '<b>Свободна</b>: можно запускать тяжёлое. <b>Под нагрузкой</b>: тяжёлое может идти медленнее. <b>На пределе</b>: тяжёлое лучше '
                               'отложить.',
                               'Красная полоса — больше 85%. «Открытых рабочих столов» — сколько их, без имён.',
                               'Если машина отдыхает, разбудить её может только <b>Включить</b> на этой странице; бот не может.']],
                             ['Клавиши',
                              ['<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd> игровой режим: полный экран, мышь захвачена, все клавиши идут в игру. Чинит мышь '
                               'в играх от первого лица.',
                               '<kbd>Esc</kbd> три раза подряд или снова <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd>: выйти из игрового режима.',
                               '<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F</kbd> только полный экран · <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> джойстик на '
                               'экране.']],
                             ['Браузер и джойстик',
                              ['Chrome, Edge или Brave. В Firefox мышь в играх работает хуже.',
                               'Джойстик: подключённый в браузере пока не работает. <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> показывает джойстик на '
                               'экране, пока в проверке.']],
                             ['Твой рабочий стол',
                              ['Он твой: своя сеть, выход только в интернет; твоя сеть и другие столы ему не видны, кроме игрового порта для совместной игры.',
                               'Твою папку не смотрят и не копируют без твоего согласия.',
                               'Sudo нет: ставь программы в свою папку через AppImage, proot-apps или <code>pip --user</code>.']]]},
        'moonlight': {'flow': ['Включить здесь',
                               'Moonlight → Desktop',
                               'Играть',
                               'Выйти: <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>Q</kbd>',
                               'Выключить здесь'],
                      'sections': [['В первый раз',
                                    ['Установи Moonlight (moonlight-stream.org) и добавь компьютер <b>{ml}</b>, с портом.',
                                     'Когда стол включён, Moonlight покажет PIN из 4 цифр; он живёт меньше минуты.',
                                     'Сразу отправь его админу или своему боту: <code>escritorio pin NNNN</code>.',
                                     'В настройках: разрешение 1080p и выключи «Optimize mouse for remote desktop».']],
                                   ['Каждый раз',
                                    ['Сначала <b>Включить</b> на этой странице.',
                                     'В Moonlight: компьютер → <b>Desktop</b>. Экран подстроится под размер твоего устройства.',
                                     'Где есть Steam, там же <b>Steam Big Picture</b> и каждая установленная игра, с обложкой.',
                                     'В конце выйди из Moonlight и нажми здесь <b>Выключить рабочий стол</b>: закрытие Moonlight его не выключает.']],
                                   ['Клавиши',
                                    ['<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>Q</kbd> выйти из Moonlight.',
                                     '<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> отпустить или захватить мышь.',
                                     '<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd> полный экран или окно · '
                                     '<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd> статистика.']],
                                   ['Твои устройства',
                                    ['<code>escritorio dispositivos</code> — бот покажет список сопряжённых устройств.',
                                     '<code>escritorio revocar ИМЯ</code> убирает одно, ему придётся сопрягаться заново. Обе — при открытом столе.']],
                                   ['Пока нет', ['Джойстики через Moonlight пока не работают.']]]},
        'games': ['Игры и рабочий стол',
                  ['Меню → Games: Steam, Heroic (Epic) и Quake III demo.|Меню → Games: Quake III demo.',
                   'В первый раз Steam ставится в твою папку (несколько минут). Входишь со своим аккаунтом Steam или Epic.|Quake III demo запускается на всё '
                   'окно или в окне 1280×720.',
                   'У каждой установленной игры меньше чем за минуту появляется значок на столе; удалишь игру — значок уйдёт.|У Quake и Force-close game есть '
                   'значки на столе.',
                   'Вид выбирается на этой странице: <b>XFCE современный</b> (тёмный, новые иконки, мягкий фон) или <b>XFCE классический</b> (привычный, '
                   'лёгкий).',
                   'При открытом столе смена вида применяется за секунды, без перезапуска. KDE Plasma скоро.',
                   'На верхней панели: <b>Машина</b> (вся машина), <b>Мой</b> (твой стол от его лимита CPU) и <b>GPU</b>.',
                   'Когда машиной пользуются несколько человек, стол с открытой игрой получает бо́льшую долю CPU.',
                   'Играть вместе в Quake: Multiplayer → Local → Refresh и выбери общий сервер или чужую игру.',
                   'Скоро: <b>кооп недели</b> — одна игра, чтобы играть всем вместе; каждый со своим аккаунтом и своей купленной копией.',
                   'Игра зависла: Меню → Games → <b>Force-close game</b>. Закрывает Windows-игры (Proton) и Quake; Steam остаётся.|Игра зависла: Меню → Games '
                   '→ <b>Force-close game</b> закроет Quake; стол останется.',
                   'Нативные Linux-игры Force-close game не закрывает: закрой из её окна или напиши админу.|Если Quake и так не отвечает, напиши админу.']],
        'trouble': ['Если не получается',
                    ['«Слишком много попыток»: подожди несколько минут и попробуй снова.',
                     '«Дольше обычного»: он всё ещё включается, подожди ещё немного.',
                     'Не входит: обнови страницу через минуту. <b>Войти на рабочий стол</b> работает только при открытом столе.',
                     'Мышь убегает в игре: <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd>, и пользуйся Chrome, Edge или Brave.',
                     'Вход на эту страницу действует 12 часов; потом войди снова со своим логином.',
                     'Если не помогло, напиши админу и расскажи, что было на странице.']]},
 'en': {'tabs': {'web': 'Browser', 'moonlight': 'Moonlight'},
        'web': {'flow': ['Switch on', 'Enter the desktop', 'Play with <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd>', 'Switch the desktop off'],
                'sections': [['Step by step',
                              ['<b>Switch on with …</b> (under “Pick your desktop”): opens your desktop with the chosen look, and wakes the machine first if '
                               'it is asleep.',
                               'If the machine was asleep, while it wakes you see “Ready in about N s”, learned from the last starts; the page refreshes by itself.',
                               '<b>Enter the desktop</b>: opens it through this page, with no other password.',
                               'When done, come back and <b>Switch the desktop off</b>: it frees the machine for others. Your files stay.',
                               'Careful: <b>Switch the desktop off</b> also closes an open game without saving. Save first.']],
                             ['If you forget to switch it off',
                              ['It switches off after 30 minutes without use. Touching the desktop, an open game or a heavy job count as use.',
                               'An open tab nobody touches does not count. An open game does, even paused in a menu.',
                               'The desktop warns 10, 5 and 1 minute before (that notice is in Spanish or Russian, not English); with a bot, the first warning '
                               'goes there too.',
                               'To keep going: move the mouse, press <b>Keep it open</b> here, or tell your bot <code>escritorio seguir</code>.']],
                             ['The machine now',
                              ["At the bottom of this page you see the shared machine's load: processor, memory, graphics card and its memory.",
                               '<b>Light</b>: room for something heavy. <b>Busy</b>: something heavy may run slower. <b>Full</b>: better wait.',
                               'A red bar is over 85%. “Desktops open” counts them, with no names.',
                               'When the machine is resting, only <b>Switch on</b> on this page wakes it; the bot cannot.']],
                             ['Shortcuts',
                              ['<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd> game mode: fullscreen, mouse captured, every key goes to the game. It fixes the '
                               'mouse in first-person games.',
                               '<kbd>Esc</kbd> three times in a row, or <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd> again: leave game mode.',
                               '<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F</kbd> fullscreen only · <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> on-screen '
                               'gamepad.']],
                             ['Browser and gamepad',
                              ['Chrome, Edge or Brave. In Firefox the mouse works worse in games.',
                               'Gamepad: a plugged-in pad does not work in the browser yet. <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> shows one on screen, '
                               'still being tested.']],
                             ['Your desktop',
                              ['It is yours: its own network, internet only; it cannot see your home network or other desktops, except the game port for '
                               'playing together.',
                               'Your folder is not looked at or copied without your word.',
                               'No sudo: install into your folder with AppImage, proot-apps or <code>pip --user</code>.']]]},
        'moonlight': {'flow': ['Switch on here',
                               'Moonlight → Desktop',
                               'Play',
                               'Quit with <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>Q</kbd>',
                               'Switch off here'],
                      'sections': [['The first time',
                                    ['Install Moonlight (moonlight-stream.org) and add the host <b>{ml}</b>, with the port.',
                                     'With the desktop on, Moonlight shows a 4-digit PIN that lasts under a minute.',
                                     'Send it right away to the admin or your bot: <code>escritorio pin NNNN</code>.',
                                     'In Settings: resolution 1080p, and turn off “Optimize mouse for remote desktop”.']],
                                   ['Every time',
                                    ['First <b>Switch on</b> on this page.',
                                     "In Moonlight: the host → <b>Desktop</b>. The screen adjusts to your device's size.",
                                     'Where Steam is installed you also get <b>Steam Big Picture</b> and each installed game, with its cover.',
                                     'When done, quit Moonlight and <b>Switch the desktop off</b> here: closing Moonlight does not switch it off.']],
                                   ['Shortcuts',
                                    ['<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>Q</kbd> quit Moonlight.',
                                     '<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> release or capture the mouse.',
                                     '<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd> fullscreen or window · '
                                     '<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd> statistics.']],
                                   ['Your devices',
                                    ['<code>escritorio dispositivos</code> asks your bot for the list of paired devices.',
                                     '<code>escritorio revocar NAME</code> removes one; it must pair again. Both need the desktop open.']],
                                   ['Not yet', ['Gamepads do not pass through Moonlight.']]]},
        'games': ['Games and desktop',
                  ['Menu → Games: Steam, Heroic (Epic) and the Quake III demo.|Menu → Games: the Quake III demo.',
                   'The first time, Steam installs into your folder (a few minutes). You sign in with your own Steam or Epic account.|The Quake III demo fills '
                   'the window, or runs in a 1280×720 window.',
                   'Each installed game gets a desktop icon within a minute; uninstall it and the icon goes.|Quake and Force-close game have desktop icons.',
                   'Pick the look on this page: <b>XFCE modern</b> (dark, new icons, soft background) or <b>XFCE classic</b> (the usual, light).',
                   'With the desktop open, the change applies in seconds, no restart. KDE Plasma is coming soon.',
                   'On the top bar: <b>Machine</b> (the whole machine), <b>Mine</b> (your desktop against its CPU cap) and <b>GPU</b>.',
                   'When several people share the machine, a desktop with an open game gets a bigger share of the CPU.',
                   "Playing together in Quake: Multiplayer → Local → Refresh, then pick the shared server or someone's game.",
                   'Coming soon: the <b>co-op of the week</b>, one game for everybody; each plays with their own account and bought copy.',
                   'A game hung: Menu → Games → <b>Force-close game</b>. It closes Windows games (Proton) and Quake; Steam stays open.|A game hung: Menu → '
                   'Games → <b>Force-close game</b> closes Quake; the desktop stays.',
                   'Force-close game does not close native Linux games: quit from its window or tell the admin.|If Quake still does not respond, tell the '
                   'admin.']],
        'trouble': ['If something fails',
                    ['“Too many attempts”: wait a few minutes and try again.',
                     '“Taking longer than usual”: it is still switching on; give it a bit more.',
                     'It does not let you in: reload in a minute. <b>Enter the desktop</b> only works while the desktop is open.',
                     'The mouse escapes in a game: <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>X</kbd>, and use Chrome, Edge or Brave.',
                     'Your login here lasts 12 hours; after that, log in again.',
                     'If it still fails, tell the admin what the page said.']]}}


def guide_ways(person):
    return ["web"] + (["moonlight"] if (person or {}).get("moonlight") else [])


def guide_html(lang, person, way="web"):
    g, p = GUIDE[lang], person or {}
    way = way if way in guide_ways(p) else "web"
    ml = html.escape(str(p.get("moonlight") or ""))
    pick = lambda ln: ln.split("|")[1 if p.get("games") == "quake" else 0] if "|" in ln else ln
    out = "<div class=flow>" + "<i>→</i>".join(f"<span>{s}</span>" for s in g[way]["flow"]) + "</div>"
    for title, lines in g[way]["sections"] + ([g["games"]] if p.get("games") else []) + [g["trouble"]]:
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
            self.send_header("Cache-Control", "no-store" if not ctype.startswith("image/") else "private, max-age=86400")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in headers:
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def page(self, lang, body, code=200, headers=()):
            self.send(code, PAGE.format(lang=lang, title=T[lang]["title"], body=body, extra=SHOW_CSS).encode(), headers=headers)

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

        def showroom(self, who, lang, csrf, act):
            """The desktops as a picker: a big screen with the chosen one, small previews to pick from, one button for the chosen one.
            act: "start" (Encender with it) or "change" (the place is open: the look changes live)."""
            st, cur = SHOW_T[lang], door.desktop(who)
            src = lambda d: f"/_door/desktops/{d['img']}"
            out = f"<div class=show><div class=screen>" + "".join(f"<img data-d={d['id']} src='{src(d)}' alt=''>" for d in DESKTOPS) + "</div>"
            out += f"<form method=post action=/_door/start><input type=hidden name=c value='{csrf}'><fieldset class=picks><legend class=st>{st['pick']}</legend>"
            for d in DESKTOPS:
                name, desc = d[lang]
                out += (f"<input type=radio name=d id=d-{d['id']} value={d['id']}{' checked' if d['id'] == cur else ''}>"
                        f"<label for=d-{d['id']} class='pick{'' if d['ready'] else ' soon'}'><img src='{src(d)}' alt=''><b>{name}</b>"
                        f"<small>{'' if d['ready'] else st['soon']}</small></label>")
            out += "</fieldset>"
            for d in DESKTOPS:
                name, desc = d[lang]
                label = (st["on"] if act == "start" else st["change"]).format(n=name)
                out += f"<p class=say data-d={d['id']}>{desc}</p>"
                out += (f"<button class=go data-d={d['id']}>{label}</button>" if d["ready"] else f"<button class=go data-d={d['id']} disabled>{st['soon']}</button>")
            return out + "</form></div>"

        def state_page(self, s):
            who, lang = s["person"], self.lang(s["person"])
            t, st = T[lang], door.state(who)
            c = html.escape(s["csrf"])
            btn = lambda act, label, cls="": f"<form method=post action=/_door/{act}><input type=hidden name=c value='{c}'><button class='{cls}'>{label}</button></form>"
            body = f"<h1>{html.escape(who)}</h1><p class=st>{t.get(st['state'], t['error'])}</p>"
            if st["state"] == "open":
                body += f"<p>{t['closes'].format(m=st.get('closes_in_min', '?'))}</p><div class=row><form method=get action=/><button>{t['enter']}</button></form>"
                body += btn("keep", t["keep"], "sec") + btn("stop", t["close"], "stop") + "</div>"
                body += self.showroom(who, lang, c, "change")
            elif st["state"] in ("off", "asleep", "error"):
                body += self.showroom(who, lang, c, "start")
            else:
                e, lt = door.eta(who), LOAD_T[lang]
                if e:
                    body += f"<p>{lt['eta'].format(s=e[0]) if e[0] > 0 else lt['late']}</p>"
                body += "<script>setTimeout(()=>location.reload(),5000)</script>"
            diag = bool((door.person(who) or {}).get("diag"))
            if diag and st.get("prep"):
                pr = st["prep"]
                body += f"<p class=st>{html.escape(LOAD_T[lang]['prep'].format(g=pr.get('name') or pr.get('appid'), p=pr.get('pct') if pr.get('pct') is not None else '?'))}</p>"
            if diag and door.timings:
                body += f"<p class=st>{html.escape(LOAD_T[lang]['took'].format(t=', '.join(f'{k} {v} s' for k, v in door.timings[-5:])))}</p>"
            body += load_html(lang, st.get("host"), st["state"])
            body += f"<div class=foot><a href=/_door/guide>{t['guide']}</a>" + btn("logout", t["logout"], "sec") + "</div>"
            self.page(lang, body)

        def guide_page(self, s, want, way):
            who = s["person"]
            p, lang = door.person(who), want if want in GUIDE else self.lang(who)
            ways = guide_ways(p)
            way = way if way in ways else "web"
            tabs = "".join(f"<a class='{'on' if w == way else ''}' href='/_door/guide?s={w}&l={lang}'>{GUIDE[lang]['tabs'][w]}</a>" for w in ways)
            langs = "".join(f"<a href='/_door/guide?s={way}&l={l}'>{n}</a>" for l, n in (("es", "Español"), ("ru", "Русский"), ("en", "English")) if l != lang)
            self.page(lang, f"<h1>{T[lang]['guide']}: {html.escape(who)}</h1><nav class=tabs>{tabs}</nav>" + guide_html(lang, p, way)
                      + f"<nav class=foot>{langs}<a href=/_door/>← {T[lang]['title']}</a></nav>")

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
            if path.startswith("/_door/desktops/"):          # the showroom's previews: a fixed list of names, never a path from the request
                name = path.rsplit("/", 1)[1]
                if not s or name not in {d["img"] for d in DESKTOPS}:
                    return self.send(404, b"not found", "text/plain")
                try:
                    with open(os.path.join(door.conf.get("desktops_dir", "/usr/local/share/bridgeai-door/desktops"), name), "rb") as fh:
                        return self.send(200, fh.read(), "image/webp")
                except OSError:
                    return self.send(404, b"not found", "text/plain")
            if path == "/_door/guide":
                if not s:
                    return self.redirect("/_door/login")
                q = self.path.split("?", 1)[1] if "?" in self.path else ""
                m, w = re.search(r"(?:^|&)l=([a-z]{2})(?:&|$)", q), re.search(r"(?:^|&)s=([a-z]{3,9})(?:&|$)", q)
                return self.guide_page(s, m.group(1) if m else "", w.group(1) if w else "web")
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
                door.act(s["person"], path.rsplit("/", 1)[1], f.get("d") if f.get("d") in READY else None)
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
