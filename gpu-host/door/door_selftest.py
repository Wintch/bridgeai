#!/usr/bin/env python3
"""Offline checks for door.py: a real HTTP server on localhost, a fake gate. Run: python3 -I door_selftest.py"""
import http.client, importlib.util, json, os, sys, tempfile, threading, time
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


conf = {"listen": "127.0.0.1:0", "gate": "http://gate", "wake_url": "http://wake/despertar?maquina=host", "secrets_dir": tmp,
        "people": {"herjav": {"lan": "10.9.8.177", "port": 3041, "lang": "es"}, "herkos": {"lan": "10.9.8.174", "port": 3021, "lang": "ru"}}}
w("herjav.pass", door.hash_password("correct horse battery")); w("herjav.token", "TOKJAV"); w("herjav.basic", "Basic aGVyamF2OnNlY3JldA==")
w("herkos.pass", door.hash_password("другой пароль 123")); w("herkos.token", "TOKKOS"); w("herkos.basic", "Basic eA==")
G = {"up": True, "running": {"herjav": False, "herkos": False}, "calls": []}


def fake_gate(method, url, token=None, timeout=8):
    G["calls"].append((method, url, token))
    if url.startswith("http://wake"):
        G["up"] = True
        return 200, {"estado": "despertando"}
    if not G["up"]:
        return 0, {}
    who = {"TOKJAV": "herjav", "TOKKOS": "herkos"}.get(token)
    if not who:
        return 401, {"why": "token"}
    if url.endswith("/place/state"):
        return 200, {"running": G["running"][who], "closes_in_min": 30}
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
check("open: the page offers Entrar, Mantener abierto and Cerrar", "Entrar al escritorio" in body and "Mantener" in body and "Cerrar el escritorio" in body)
st2, ck2, _ = login("herkos", "другой пароль 123", ip="203.0.113.9")
st, h, body = req("GET", "/_door/auth", cookie=ck2)
check("one person's session never reaches another person's place", st == 403 and not G["running"]["herkos"])
st, h, body = req("GET", "/_door/", cookie=ck2)
check("the page speaks the person's language (Russian here)", "выключен" in body and "Включить" in body, body[:300])
st, h, body = req("POST", "/_door/stop", "c=" + csrf(ck), cookie=ck)
check("Cerrar closes the place", st == 303 and not G["running"]["herjav"])
G["up"] = False; G["calls"].clear()
st, h, body = req("POST", "/_door/start", "c=" + csrf(ck), cookie=ck)
check("Encender with the host asleep asks the wake service", any(u.startswith("http://wake") for _, u, _ in G["calls"]), G["calls"])
for _ in range(60):
    if G["running"]["herjav"]: break
    time.sleep(0.1)
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
os.chmod(os.path.join(tmp, "herkos.basic"), 0o644)
check("check() finds a secret file readable by others", any("readable by others" in p for p in door.check(conf)))
srv.shutdown()
print("door_selftest: " + ("all ok" if not fails else f"FAILED: {', '.join(fails)}"))
sys.exit(1 if fails else 0)
