#!/usr/bin/env python3
"""Offline checks for door.py: a real HTTP server on localhost, a fake gate. Run: python3 -I door_selftest.py"""
import re, http.client, importlib.util, json, os, socket, sys, tempfile, threading, time
import atexit as _a, shutil as _s
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("door", os.path.join(HERE, "door.py")); door = importlib.util.module_from_spec(spec); spec.loader.exec_module(door)
tmp = tempfile.mkdtemp(prefix="selftest-"); _a.register(_s.rmtree, tmp, True)
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def w(name, text, mode=0o600):
    p = os.path.join(tmp, name); open(p, "w").write(text); os.chmod(p, mode); return p


class FakeQuake:
    """A Quake III server on 127.0.0.1 that answers getstatus (or stays silent): counts the queries it gets."""

    def __init__(self, players=(), silent=False, bots=(), other_source=False):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.s.bind(("127.0.0.1", 0))
        self.addr, self.players, self.silent, self.asked = "127.0.0.1:%d" % self.s.getsockname()[1], list(players), silent, 0
        self.bots, self.other = list(bots), other_source      # bots answer with ping 0; other_source: the answer comes from another port
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            data, peer = self.s.recvfrom(2048)
            if data != b"\xff\xff\xff\xffgetstatus\n":
                continue
            self.asked += 1
            if not self.silent:
                lines = "".join('%d %d "%s"\n' % (i, 40 + i, n) for i, n in enumerate(self.players)) + "".join('5 0 "%s"\n' % n for n in self.bots)
                out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if self.other else self.s
                out.sendto(b"\xff\xff\xff\xffstatusResponse\n\\sv_hostname\\^3LAN\\mapname\\q3dm17\\sv_maxclients\\8\n" + lines.encode("latin-1"), peer)


def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


Q = FakeQuake(['^1Gr^7unt<b>', "^4Ana^7"])
DOWN = "127.0.0.1:%d" % free_udp_port()
conf = {"listen": "127.0.0.1:0", "game_servers": [{"label": "Quake III LAN", "addr": Q.addr, "kind": "quake3"}, {"label": "Otro <x>", "addr": DOWN, "kind": "quake3"}], "gate": "http://gate", "wake_url": "http://wake/despertar?maquina=host", "secrets_dir": tmp,
        "desktops_dir": os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktops"), "people": {"herjav": {"lan": "10.9.8.177", "port": 3041, "lang": "es"}, "herkos": {"lan": "10.9.8.174", "port": 3021, "lang": "ru", "games": True, "moonlight": "203.0.113.5:49989"}}}
w("herjav.pass", door.hash_password("correct horse battery")); w("herjav.token", "TOKJAV"); w("herjav.basic", "Basic aGVyamF2OnNlY3JldA==")
w("herkos.pass", door.hash_password("другой пароль 123")); w("herkos.token", "TOKKOS"); w("herkos.basic", "Basic eA==")
G = {"up": True, "running": {"herjav": False, "herkos": False}, "calls": []}


def fake_gate(method, url, token=None, timeout=8, body=None):
    G["calls"].append((method, url, token))
    G.setdefault("bodies", []).append((url, body))
    if url.startswith("http://wake"):
        G["up"] = True
        return 200, {"estado": "despertando"}
    if not G["up"]:
        return 0, {}
    who = {"TOKJAV": "herjav", "TOKKOS": "herkos"}.get(token)
    if not who:
        return 401, {"why": "token"}
    if url.endswith("/place/state"):
        return 200, {"running": G["running"][who], "closes_in_min": 30, "host": {"ts": 1, "cpu_pct": 91, "cores": 12, "mem_used_gb": 9.5, "mem_total_gb": 31.2,
                     "gpu_pct": 14.0, "vram_used_mb": 1500.0, "vram_total_mb": 8192.0, "places_running": 2}}
    if url.endswith("/place/start"):
        G["running"][who] = True; return 200, {"running": True}
    if url.endswith("/place/stop"):
        G["running"][who] = False; return 200, {"running": False}
    if url.endswith("/place/keep"):
        return 200, {}
    return 404, {}


D = door.Door(conf, gate=fake_gate)
srv = door.Server(("127.0.0.1", 0), door.make_handler(D)); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def req(method, path, body=None, cookie=None, ip="203.0.113.5"):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"X-Real-IP": ip}
    if cookie:
        h["Cookie"] = "door_s=" + cookie
    if body is not None:
        h["Content-Type"] = "application/x-www-form-urlencoded"
    c.request(method, path, body=body, headers=h)
    r = c.getresponse(); data = r.read().decode("utf-8", "replace")
    if os.environ.get("DOOR_PREVIEW_DIR") and method == "GET" and data.startswith("<!doctype"):   # copies of each page, to look at the design
        name = re.sub(r"[^a-z0-9]+", "-", f"{path}-{(cookie or 'anon')[:4]}-{len(data)}".lower()).strip("-")
        open(os.path.join(os.environ["DOOR_PREVIEW_DIR"], name + ".html"), "w").write(data)
    return r.status, dict(r.getheaders()), data


def login(user, pw, ip="203.0.113.5"):
    from urllib.parse import urlencode
    st, h, body = req("POST", "/_door/login", urlencode({"u": user, "p": pw}), ip=ip)
    m = __import__("re").search(r"door_s=([^;]+)", h.get("Set-Cookie", ""))
    return st, (m.group(1) if m else None), body


def csrf(cookie):
    return D.sessions.get(cookie)["csrf"]


st, h, body = req("GET", "/_door/auth")
check("without a session, auth is 401 (nginx sends the browser to the login)", st == 401)
st, ck, body = login("herjav", "wrong")
check("a wrong password is refused and gives no session", st == 401 and ck is None and "incorrectos" in body)
st, ck, body = login("nobody", "whatever")
check("an unknown name gives the same answer as a wrong password", st == 401 and ck is None)
st, ck, body = login("herjav", "correct horse battery")
check("the right password gives a session cookie (HttpOnly, Secure, SameSite)", st == 303 and ck)
st_l, _, body_l = req("GET", "/_door/login")
check("the login has visible labels (not placeholders only) and the design mark", "<label>Usuario<input" in body_l and "<label>Clave<input" in body_l
      and 'name="design-guide"' in body_l, body_l[:400])
st, h, body = req("POST", "/_door/login", "u=herjav&p=correct+horse+battery")
check("the session cookie carries HttpOnly, Secure and SameSite=Lax", all(x in h.get("Set-Cookie", "") for x in ("HttpOnly", "Secure", "SameSite=Lax")), h.get("Set-Cookie"))
st, h, body = req("GET", "/_door/", cookie=ck)
check("the state page shows the place off with an Encender button, never the token or the basic auth", st == 200 and "apagado" in body and "Encender" in body and "TOKJAV" not in body and "aGVyamF2" not in body, body[:300])
st, h, body = req("GET", "/_door/auth", cookie=ck)
check("auth is 403 while the place is off (nothing to proxy to)", st == 403)
st, h, body = req("POST", "/_door/start", "c=wrong", cookie=ck)
check("a form without the session's CSRF token is refused and starts nothing", st == 403 and not G["running"]["herjav"])
st, h, body = req("POST", "/_door/start", "c=" + csrf(ck), cookie=ck)
check("Encender opens the place through the gate with the person's own token", st == 303 and G["running"]["herjav"] and ("POST", "http://gate/place/start", "TOKJAV") in G["calls"])
st, h, body = req("GET", "/_door/auth", cookie=ck)
check("auth then answers 200 with the place's address and its basic auth for nginx only", st == 200 and h.get("X-Door-Upstream") == "10.9.8.177:3041" and h.get("X-Door-Auth") == "Basic aGVyamF2OnNlY3JldA==", (st, h))
st, h, body = req("GET", "/_door/", cookie=ck)
check("open: the page offers Entrar, Mantener abierto and Cerrar", "Entrar al escritorio" in body and "Mantener" in body and "Apagar el escritorio" in body)
check("open: the guide and logout sit at the top, the state is the amber node, the page has back-to-top and the design mark",
      body.index("/_door/guide") < body.index("Entrar al escritorio") and body.index("/_door/logout") < body.index("Entrar al escritorio")
      and "state s-open" in body and "class=totop" in body and 'name="design-guide"' in body and "noindex" in body, body[:600])
st2, ck2, _ = login("herkos", "другой пароль 123", ip="203.0.113.9")
st, h, body = req("GET", "/_door/auth", cookie=ck2)
check("one person's session never reaches another person's place", st == 403 and not G["running"]["herkos"])
st, h, body = req("GET", "/_door/", cookie=ck2)
check("the page speaks the person's language (Russian here)", "выключен" in body and "Включить" in body, body[:300])
check("the state page links the guide", "/_door/guide" in body)
check("a person with games sees 'Playing now' on the state page while the place is off (Russian here)", "Сейчас играют" in body and "class='load games'" in body, body[-1500:])
check("each server shows its label, map and players/max", "Quake III LAN" in body and "q3dm17 · 2/8" in body, body[-1500:])
check("players' in-game names lose the colour codes and are escaped", "Grunt&lt;b&gt;" in body and "Ana" in body and "^1" not in body and "^7" not in body and "<b>Grunt" not in body)
check("a server that does not answer shows as not answering, its label escaped", "Otro &lt;x&gt;" in body and "не отвечает" in body and "<x>" not in body)
check("one page load asked each server once", Q.asked == 1, Q.asked)
for _ in range(5):
    req("GET", "/_door/", cookie=ck2)
check("the answer is cached: five more page loads ask the server no more", Q.asked == 1, Q.asked)
st, h, body = req("GET", "/_door/", cookie=ck)
check("a person without games sees no game servers", "Jugando ahora" not in body and "class='load games'" not in body and "q3dm17" not in body, body[-600:])
st, h, body = req("GET", "/_door/desktops/kde.webp", cookie=ck2)
check("a showroom preview is served to a session (from the fixed list only)", st == 200 and h.get("Content-Type") == "image/webp" and body)
check("a preview outside the list, or a path, is 404", req("GET", "/_door/desktops/..%2Fdoor.json", cookie=ck2)[0] == 404 and req("GET", "/_door/desktops/x.webp", cookie=ck2)[0] == 404)
check("previews need a session", req("GET", "/_door/desktops/kde.webp")[0] == 404)
st, h, body = req("GET", "/_door/guide", cookie=ck2)
check("the browser guide is in the person's language, with a flow, games, and a tab to Moonlight for a person who has it", st == 200 and "<kbd>X</kbd>" in body and "class=flow" in body and "Force-close game" in body and "s=moonlight" in body and "По шагам" in body, body[:300])
check("the guide has a back-to-top button, the way back to the door at the top, the game lookup before the flow, and the design mark",
      "class=totop href=#top" in body and body.index("href=/_door/>") < body.index("class=flow") and body.index("protondb") < body.index("class=flow")
      and 'name="design-guide" content="guia-sitios@' in body and "noindex" in body, body[:300])
st, h, body = req("GET", "/_door/guide?s=moonlight", cookie=ck2)
check("the Moonlight guide has the person's Moonlight address and Ctrl+Alt+Shift+Q to quit", st == 200 and "203.0.113.5:49989" in body and "<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>Q</kbd>" in body, body[:300])
st, h, body = req("GET", "/_door/guide?s=moonlight&l=en", cookie=ck2)
check("the guide switches language (English) and keeps the guide chosen", st == 200 and "The first time" in body and "<html lang=\"en\"" in body, body[:200])
st, h, body = req("GET", "/_door/guide?s=moonlight&l=es", cookie=ck)
check("a person without Moonlight gets the browser guide only, without games they do not have", st == 200 and "Paso a paso" in body and "s=moonlight" not in body and "Force-close" not in body and "{ml}" not in body, body[:300])
_g = door.guide_html("es", {"games": "quake"})
check("a Quake-only place's guide names only Quake", "Quake III demo" in _g and "Steam" not in _g, _g[:300])
check("the guide escapes the Moonlight address from the config", "<x>" not in door.guide_html("en", {"moonlight": "<x>"}, "moonlight"))
_m = door.guide_html("es", {"moonlight": "1.2.3.4:5"}, "moonlight")
check("both guides tell how to copy and paste: both ways in the browser, Ctrl+Alt+Shift+V one way in Moonlight", "Copiar y pegar" in door.guide_html("es", {}, "web") and "<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>V</kbd>" in _m)
check("a games place's guide has a ProtonDB search that opens ProtonDB's own search in a new tab; a Quake-only place's does not",
      "action='https://www.protondb.com/search'" in door.guide_html("es", {"games": True}, "web") and "target=_blank" in door.guide_html("es", {"games": True}, "web")
      and "protondb" not in door.guide_html("es", {"games": "quake"}, "web"))
check("the guide needs a session", req("GET", "/_door/guide")[0] == 303)
# the gift card and its one-time way in
check("without one_time, the card and the one-time links do not exist", req("GET", "/_door/card", cookie=ck)[0] == 404 and req("GET", "/_door/t/" + "a" * 22)[0] == 404)
D.conf["one_time"] = True
st, h, body = req("GET", "/_door/card", cookie=ck)
check("the card: white, a QR drawn here (SVG, no outside service), mountains, not cached, the design mark",
      st == 200 and "<svg class=qr" in body and "class=peaks" in body and "http" not in body.split("<svg class=qr")[1].split("</svg>")[0]
      and h.get("Cache-Control") == "no-store" and 'name="design-guide"' in body, (st, body[:300]))
check("the card needs a session", req("GET", "/_door/card")[0] == 303)
_was = dict(G["running"]); G["running"]["herjav"] = False
tok = D.tickets.mint("herjav", D.now())
st, h, body = req("GET", "/_door/t/" + tok)
check("opening the link only shows a page with a button (a link preview burns nothing)", st == 200 and "<form method=post" in body and D.tickets.peek(tok, D.now()) == "herjav")
st, h, body = req("POST", "/_door/t/" + tok, "")
check("its button uses the token once: a session, and the desktop switches on", st == 303 and "door_s=" in h.get("Set-Cookie", "") and G["running"]["herjav"], (st, h))
st, h, body = req("POST", "/_door/t/" + tok, "")
check("the same link a second time: gone (410), no session", st == 410 and "door_s=" not in h.get("Set-Cookie", ""), st)
old_tok = D.tickets.mint("herjav", D.now() - door.TICKET_S - 1)
check("an expired link is gone", req("POST", "/_door/t/" + old_tok, "")[0] == 410)
toks = [D.tickets.mint("herkos", D.now()) for _ in range(door.TICKETS_PER_PERSON + 2)]
check("at most TICKETS_PER_PERSON links alive per person: the oldest go first", [D.tickets.peek(t, D.now()) for t in toks] == [None, None] + ["herkos"] * door.TICKETS_PER_PERSON)
for _ in range(door.FAILS_PER_IP):
    req("POST", "/_door/t/" + "b" * 22, "", ip="198.51.100.7")
check("guessing links from one address is throttled (429), another address is not", req("POST", "/_door/t/" + "b" * 22, "", ip="198.51.100.7")[0] == 429
      and req("POST", "/_door/t/" + "b" * 22, "", ip="198.51.100.8")[0] == 410)
D.conf["one_time"] = False; G["running"].update(_was); D.waking.pop("herjav", None); D.woke.pop("herjav", None); D.cache.pop("herjav", None)
st, h, body = req("POST", "/_door/stop", "c=" + csrf(ck), cookie=ck)
check("Cerrar closes the place", st == 303 and not G["running"]["herjav"])
st, h, body = req("GET", "/_door/", cookie=ck)
check("the page shows the machine's load with a plain verdict and a count of open desktops, never whose", "La máquina ahora" in body and "A tope" in body and "Escritorios abiertos: 2" in body and "herkos" not in body, body[-900:])
check("a meter at 85% or more is marked", "class='bar hot' style='--v:91%'" in body)
st, h, body = req("GET", "/_door/", cookie=ck)
check("the off page is the showroom: every desktop, the ready ones to pick, the others marked", "name=d id=d-moderno" in body and "name=d id=d-clasico" in body and "class='pick soon'" in body and "Encender con XFCE moderno" in body, body[:400])
G["bodies"].clear()
st, h, body = req("POST", "/_door/start", "c=" + csrf(ck) + "&d=clasico", cookie=ck)
check("Encender sends the chosen desktop to the gate", st == 303 and ("http://gate/place/start", {"desktop": "clasico"}) in G["bodies"], G["bodies"])
st, h, body = req("GET", "/_door/", cookie=ck)
check("the page remembers the choice", "id=d-clasico value=clasico checked" in body, body[:300])
G["bodies"].clear()
req("POST", "/_door/start", "c=" + csrf(ck) + "&d=kde", cookie=ck)
check("a desktop that is not ready is never sent (the last choice is kept)", all(b == {"desktop": "clasico"} for u, b in G["bodies"] if u.endswith("/place/start")), G["bodies"])
req("POST", "/_door/stop", "c=" + csrf(ck), cookie=ck)
G["up"] = False; G["calls"].clear()
st, h, body = req("POST", "/_door/start", "c=" + csrf(ck), cookie=ck)
check("Encender with the host asleep asks the wake service", any(u.startswith("http://wake") for _, u, _ in G["calls"]), G["calls"])
for _ in range(60):
    if G["running"]["herjav"]: break
    time.sleep(0.1)
check("while starting, the page tells how long it should take", "Listo en unos" in req("GET", "/_door/", cookie=ck)[2] or G["running"]["herjav"])
check("the page says starting meanwhile", "Encendiendo" in req("GET", "/_door/", cookie=ck)[2] or G["running"]["herjav"])
st, h, body = req("POST", "/_door/logout", "c=" + csrf(ck), cookie=ck)
check("logout ends the session", st == 303 and req("GET", "/_door/auth", cookie=ck)[0] == 401)
for i in range(door.FAILS_PER_IP):
    login("herjav", "bad%d" % i, ip="198.51.100.7")
st, ck3, body = login("herjav", "correct horse battery", ip="198.51.100.7")
check("after too many failures from one address, even the right password waits", ck3 is None and "Demasiados" in body)
st, ck4, _ = login("herjav", "correct horse battery", ip="198.51.100.8")
check("another address is not blocked by that", ck4 is not None)
check("passwords are stored as scrypt and checked in constant time", door.check_password("x", door.hash_password("x")) and not door.check_password("y", door.hash_password("x")) and door.hash_password("x").startswith("scrypt$"))
st2, ck5, _ = login("herkos", "другой пароль 123", ip="203.0.113.10")
req("POST", "/_door/start", "c=" + csrf(ck5), cookie=ck5)
st, h, body = req("GET", "/_door/", cookie=ck5)
check("the open page shows the game servers too", "Войти на рабочий стол" in body and "Сейчас играют" in body and "q3dm17" in body, body[-1500:])
clock = [1000.0]
Q2 = FakeQuake(["p%d" % i for i in range(20)])
gs = door.GameServers([{"label": "LAN", "addr": Q2.addr, "kind": "quake3"}], now=lambda: clock[0])
r1 = gs.status(); clock[0] += 14; gs.status()
check("within 15 s the server is not asked again", Q2.asked == 1, Q2.asked)
clock[0] += 1; r2 = gs.status()
check("after 15 s it is asked again", Q2.asked == 2, Q2.asked)
_h = door.games_html("es", r2)
check("at most 16 names show, then how many more", "p15" in _h and "p16" not in _h and "y 4 más" in _h and "20/8" in _h, _h)
clock[0] += 15
slow = {"n": 0}
def slow_query(addr):
    slow["n"] += 1; time.sleep(0.3); return {"map": "x", "max": 4, "players": []}
gs2 = door.GameServers([{"label": "LAN", "addr": "10.9.8.5:27960", "kind": "quake3"}], query=slow_query, now=lambda: clock[0])
th = [threading.Thread(target=gs2.status) for _ in range(12)]
[t.start() for t in th]; [t.join() for t in th]
check("many page loads at once ask the server once (a query in flight counts)", slow["n"] == 1, slow["n"])
_h = door.games_html("en", gs2.status())
check("an empty server says nobody yet, with players/max", "nobody yet" in _h and "x · 0/4" in _h and "dot on" not in _h, _h)
check("Russian and Spanish say nobody in their language", "пока никого" in door.games_html("ru", gs2.status()) and "nadie por ahora" in door.games_html("es", gs2.status()))
QS = FakeQuake(silent=True)
gs3 = door.GameServers([{"label": "a", "addr": QS.addr}, {"label": "b", "addr": "127.0.0.1:%d" % free_udp_port()}])
t0 = time.monotonic(); r3 = gs3.status(); took = time.monotonic() - t0
check("a silent server and a closed port: both not answering, and the page waits no more than ~2 s", [x["up"] for x in r3] == [False, False] and took < 2.2, (r3, took))
check("a silent server got exactly one query", QS.asked == 1, QS.asked)
check("games 'quake' shows the servers, no games or no servers shows nothing",
      door.Door({**conf, "people": {"herq": {"games": "quake"}}}, gate=fake_gate).shows_games("herq")
      and not door.Door({**conf, "people": {"herq": {}}}, gate=fake_gate).shows_games("herq")
      and not door.Door({**conf, "game_servers": [], "people": {"herq": {"games": True}}}, gate=fake_gate).shows_games("herq"))
check("a bad game server entry is reported by check and never asked", any("game server" in p for p in door.check({**conf, "game_servers": [{"label": "x", "addr": "nope"}]}))
      and door.GameServers([{"label": "x", "addr": "nope"}, {"label": "y", "addr": "h:1", "kind": "doom"}]).servers == [])
# ---- bots are not people: counted apart, never listed, never light the dot
QB = FakeQuake(bots=["Sarge", "Xaero", "Major"])
r = door.q3_status(QB.addr)
check("only bots (ping 0): no players, three bots", (r or {}).get("players") == [] and (r or {}).get("bots") == 3, r)
_h = door.games_html("es", door.GameServers([{"label": "LAN", "addr": QB.addr}]).status())
check("only bots: 'nadie por ahora', 0/8 and +3 bots, the dot stays off", "nadie por ahora" in _h and "q3dm17 · 0/8 · +3 bots" in _h and "dot on" not in _h
      and "Sarge" not in _h, _h)
QM = FakeQuake(["Ana"], bots=["Sarge"])
_h = door.games_html("ru", door.GameServers([{"label": "LAN", "addr": QM.addr}]).status())
check("a person and a bot: 1/8 and +1 bot apart, only the person named, the dot on", "q3dm17 · 1/8 · +1 бот" in _h and "Ana" in _h and "Sarge" not in _h
      and "dot on" in _h, _h)
check("Russian plural of bots", [door.bots_text("ru", n) for n in (1, 2, 5, 11, 22)] == ["+1 бот", "+2 бота", "+5 ботов", "+11 ботов", "+22 бота"])
# ---- an entry without a label never shows its address on this internet-facing page
gl = door.GameServers([{"addr": Q.addr, "kind": "quake3"}, {"label": "", "addr": DOWN}])
_h = door.games_html("es", gl.status())
check("no label: shown as 'Quake III', never HOST:PORT", [x["label"] for x in gl.servers] == ["Quake III", "Quake III"]
      and Q.addr not in _h and DOWN not in _h and "127.0.0.1" not in _h, _h)
# ---- the UDP socket is connected: a closed port fails at once, an answer from another address is ignored
t0 = time.monotonic(); r = door.q3_status("127.0.0.1:%d" % free_udp_port(), timeout=1.5); took = time.monotonic() - t0
check("a closed port fails at once (connected socket), not after the timeout", r is None and took < 0.5, took)
QO = FakeQuake(["Ana"], other_source=True)
check("an answer from another address is never read", door.q3_status(QO.addr, timeout=0.5) is None and QO.asked == 1)
os.chmod(os.path.join(tmp, "herkos.basic"), 0o644)
check("check() finds a secret file readable by others", any("readable by others" in p for p in door.check(conf)))
srv.shutdown()
print("door_selftest: " + ("all ok" if not fails else f"FAILED: {', '.join(fails)}"))
sys.exit(1 if fails else 0)
