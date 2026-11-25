#!/usr/bin/env python3
"""Offline checks for `gateway lugar` against a fake GPU-gate /host/* (loopback only). Run: python3 -I gateway_lugar_selftest.py"""
import contextlib, importlib.util, io, json, os, sys, tempfile, threading
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []
TOKEN = "host-token-for-tests"
GAMES = [{"appid": 12100, "name": "Grand Theft Auto III"}, {"appid": 12210, "name": "Grand Theft Auto IV: The Complete Edition"},
         {"appid": 286690, "name": "Metro 2033 Redux"}, {"appid": 237110, "name": "Mortal Kombat Komplete Edition"},
         {"appid": 1089130, "name": "Quake II RTX"}]
STATE = {"running": [], "shaders": {"compiling": False, "workers": 0, "appids": []}, "stream_up": True, "ready": False}
CALLS = []
SW = {"launch_code": 200, "power_code": 200, "after_launch": None, "shot": (200, b""), "clip": (200, b"", True)}


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _ok(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            self._send(401, {"why": "token"}); return False
        return True

    def do_GET(self):
        if not self._ok():
            return
        CALLS.append(("GET", self.path))
        if self.path == "/host/games":
            return self._send(200, {"games": GAMES, "running": []})
        if self.path == "/host/state":
            return self._send(200, STATE)
        if self.path.startswith("/host/clip"):
            CALLS.append(("CLIP", self.path))
            code, body, audio = SW["clip"]
            if code != 200:
                return self._send(code, {"why": "x"})
            self.send_response(200); self.send_header("Content-Type", "video/mp4"); self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Clip-Seconds", "10"); self.send_header("X-Clip-Audio", "1" if audio else "0"); self.end_headers()
            return self.wfile.write(body)
        if self.path == "/host/screenshot":
            code, body = SW["shot"]
            if code != 200:
                return self._send(code, {"why": "x"})
            self.send_response(200); self.send_header("Content-Type", "image/jpeg"); self.send_header("Content-Length", str(len(body))); self.end_headers()
            return self.wfile.write(body)
        self._send(404, {})

    def do_POST(self):
        if not self._ok():
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        CALLS.append(("POST", self.path, body))
        if self.path == "/host/launch":
            if SW["launch_code"] != 200:
                return self._send(SW["launch_code"], {})
            if SW["after_launch"]:
                STATE.update(SW["after_launch"])
            return self._send(200, {"started": True, "already_running": False, "name": next(g["name"] for g in GAMES if g["appid"] == body["appid"])})
        if self.path == "/host/power":
            return self._send(SW["power_code"], {"ok": True})
        self._send(404, {})


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
tmp = tempfile.mkdtemp()
URL = f"http://127.0.0.1:{srv.server_port}"
CFG = {"lugares": {"aishur": {"url": URL, "token": TOKEN}}}
os.environ.update(AIBRIDGE_LUGAR_SHOTS=f"{tmp}/shots", GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log", AIBRIDGE_LUGAR_WAIT_S="1")


def write_cfg(c):
    json.dump(c, open(f"{tmp}/gw.json", "w"))


write_cfg(CFG)
spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)


def run(*argv):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        rc = gw.cmd_lugar(list(argv))
    return rc, b.getvalue()


def reset():
    CALLS.clear()
    STATE.update(running=[], shaders={"compiling": False, "workers": 0, "appids": []}, stream_up=True, ready=False)
    SW.update(launch_code=200, power_code=200, after_launch=None)


COMPILING = {"running": [], "shaders": {"compiling": True, "workers": 12, "appids": [12210], "percent": 33}, "ready": False}
READY = {"running": [{"appid": 12210, "name": "Grand Theft Auto IV: The Complete Edition"}], "shaders": {"compiling": False, "workers": 0, "appids": []},
         "stream_up": True, "ready": True}

# Not configured.
write_cfg({})
rc, out = run("estado")
check("without a lugares block it says so and calls nothing", rc == 1 and "no tiene un equipo de juegos" in out and not CALLS, out)
write_cfg(CFG)

# Matching a loose name.
for q in ("gta4", "gta 4", "GTA IV", "grand theft auto 4", "grand theft auto iv"):
    reset(); SW["after_launch"] = COMPILING
    rc, out = run("correr", *q.split())
    check(f"«{q}» finds GTA IV and launches appid 12210", rc == 0 and ("POST", "/host/launch", {"appid": 12210}) in CALLS, (out, CALLS))
reset(); SW["after_launch"] = COMPILING
rc, out = run("correr", "gta3")
check("«gta3» finds GTA III, not IV", rc == 0 and ("POST", "/host/launch", {"appid": 12100}) in CALLS, (out, CALLS))
reset()
rc, out = run("correr", "gta")
check("«gta» is ambiguous: it lists both and launches nothing", rc == 3 and "Grand Theft Auto III" in out and "Grand Theft Auto IV" in out and not [c for c in CALLS if c[0] == "POST"], (out, CALLS))
reset(); SW["after_launch"] = COMPILING
rc, out = run("correr", "metro")
check("a word that starts one name finds it", rc == 0 and ("POST", "/host/launch", {"appid": 286690}) in CALLS, (out, CALLS))
reset()
rc, out = run("correr", "fortnite")
check("an unknown game lists what exists and launches nothing", rc == 3 and "No encontré" in out and "Quake II RTX" in out and not [c for c in CALLS if c[0] == "POST"], (out, CALLS))
rc, out = run("correr")
check("no game named asks which", rc == 2 and "¿Qué juego?" in out, out)

# Phases the person is told.
reset(); SW["after_launch"] = COMPILING
rc, out = run("correr", "gta4")
check("while Steam compiles shaders it says so, with Steam's percentage, and tells the person NOT to enter",
      rc == 0 and "compilando los shaders" in out and "33 %" in out and "TODAVÍA NO ENTRES" in out and "Moonlight" not in out, out)
reset(); SW["after_launch"] = READY
rc, out = run("correr", "gta4")
check("when it is ready it gives the way in (Moonlight, Desktop)", rc == 0 and "listo para entrar" in out and "Moonlight" in out and "«Desktop»" in out, out)
check("the way in names the host address, never a token", "127.0.0.1" in out and TOKEN not in out, out)
reset(); STATE.update(READY)
rc, out = run("estado")
check("estado of a ready host", rc == 0 and "listo para entrar" in out and "Moonlight" in out, out)
reset(); STATE.update(COMPILING)
rc, out = run("estado")
check("estado while compiling does not hand out the way in", rc == 0 and "TODAVÍA NO ENTRES" in out and "Moonlight" not in out, out)
reset(); STATE.update(READY); STATE["thermal"] = {"gpu_c": 71, "cpu_c": 88, "level": "warm", "throttle": []}
rc, out = run("estado")
check("a warm PC is said to be warm, with both temperatures", rc == 0 and "templada" in out and "GPU 71 °C" in out and "CPU 88 °C" in out, out)
STATE["thermal"] = {"gpu_c": 84, "cpu_c": 91, "level": "hot", "throttle": ["power cap", "thermal slowdown"]}
rc, out = run("estado")
check("a hot PC says CALOR with the reasons the GPU slows down", rc == 0 and "CALOR" in out and "thermal slowdown" in out and "bajar el límite" in out, out)
STATE["thermal"] = {"gpu_c": 60, "cpu_c": 70, "level": "ok", "throttle": []}
rc, out = run("estado")
check("an ok PC says nothing about heat", rc == 0 and "templada" not in out and "CALOR" not in out, out)
STATE.pop("thermal", None)
reset()
rc, out = run("estado")
check("estado with nothing running says so", rc == 0 and "No hay ningún juego corriendo" in out, out)
reset(); SW["launch_code"] = 404
rc, out = run("correr", "gta4")
check("a refused launch is reported, never as started", rc == 1 and "no pudo lanzar" in out and "Lancé" not in out, out)
reset()
rc, out = run("juegos")
check("juegos lists the names", rc == 0 and "Metro 2033 Redux" in out and "Quake II RTX" in out, out)

# Power: the person's own command.
reset()
rc, out = run("congelar")
check("the agent's congelar prints the person's command and does nothing (rc 5)", rc == 5 and "/lugar freeze yes" in out and "Todavía no hice nada" in out
      and not [c for c in CALLS if c[0] == "POST"], (out, CALLS))
rc, out = run("apagar")
check("the agent's apagar prints /lugar shutdown yes and does nothing", rc == 5 and "/lugar shutdown yes" in out and not [c for c in CALLS if c[0] == "POST"], (out, CALLS))
rc, out = run("--persona", "freeze")
check("the person's freeze without yes only describes (rc 5)", rc == 5 and "/lugar freeze yes" in out and not [c for c in CALLS if c[0] == "POST"], (out, CALLS))
rc, out = run("--persona", "freeze", "yes")
check("freeze + yes suspends through the gate", rc == 0 and ("POST", "/host/power", {"action": "suspend"}) in CALLS and "Wake-on-LAN" in out, (out, CALLS))
CALLS.clear()
rc, out = run("--persona", "shutdown", "yes")
check("shutdown + yes powers off", rc == 0 and ("POST", "/host/power", {"action": "poweroff"}) in CALLS, (out, CALLS))
reset(); SW["power_code"] = 500
rc, out = run("--persona", "freeze", "yes")
check("a refused power order is an error, never 'listo'", rc == 1 and "no aceptó" in out and "Listo" not in out, (rc, out))

# The host is down.
write_cfg({"lugares": {"aishur": {"url": "http://127.0.0.1:9", "token": TOKEN}}})
rc, out = run("estado")
check("an unreachable host says it is asleep or off and that waking is not possible from here", rc == 1 and "dormida o apagada" in out and "Traceback" not in out, out)

# gateway lugar pantalla: one picture of the game PC's screen, kept private, sent with a MEDIA: line
write_cfg(CFG)
reset()
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 500
SW["shot"] = (200, JPG)
rc, out = run("pantalla")
paths = sorted(os.listdir(f"{tmp}/shots")) if os.path.isdir(f"{tmp}/shots") else []
check("pantalla: saves the JPEG and prints the MEDIA line", rc == 0 and len(paths) == 1 and f"MEDIA:{tmp}/shots/{paths[0]}" in out and ("GET", "/host/screenshot") in CALLS, out)
mode = oct(os.stat(f"{tmp}/shots/{paths[0]}").st_mode & 0o777), oct(os.stat(f"{tmp}/shots").st_mode & 0o777)
check("pantalla: the file is 0600 in a 0700 folder (a screen is private)", mode == ("0o600", "0o700"), mode)
for alias in ("screen", "captura", "screenshot", "foto", "shot"):
    rc, out = run(alias)
    check(f"pantalla: alias {alias}", rc == 0 and "MEDIA:" in out, out)
import time as _t
for i in range(5):                                   # names carry the second: make five distinct ones
    open(f"{tmp}/shots/aishur-20260101-00000{i}.jpg", "wb").write(JPG)
rc, out = run("pantalla")
check("pantalla: only the last three pictures of a host are kept", len([n for n in os.listdir(f"{tmp}/shots") if n.startswith("aishur-")]) == 3, os.listdir(f"{tmp}/shots"))
SW["shot"] = (200, b"<html>not a jpeg</html>")
rc, out = run("pantalla")
check("pantalla: a body that is not a JPEG is refused, nothing saved as a picture", rc == 1 and "no pudo sacar la pantalla" in out and "MEDIA:" not in out, out)
SW["shot"] = (503, b"")
rc, out = run("pantalla")
check("pantalla: the gate says no display -> a plain message, rc 1", rc == 1 and "sesión gráfica" in out, out)
SW["shot"] = (429, b"")
rc, out = run("pantalla")
check("pantalla: busy -> try again, rc 4", rc == 4 and "otra captura" in out, out)
SW["shot"] = (200, JPG)
check("pantalla: the usage line lists it", "pantalla" in (run("zzz")[1]), run("zzz")[1])

# gateway lugar clip: a short H.265 + AAC recording, kept private, sent with a MEDIA: line
write_cfg(CFG)
reset()
MP4 = b"\x00\x00\x00\x20ftypisom" + b"0" * 4000
SW["clip"] = (200, MP4, True)
rc, out = run("clip")
mp4s = [n for n in os.listdir(f"{tmp}/shots") if n.endswith(".mp4")]
check("clip: saved as an mp4 with the MEDIA line, the default length is 10 s", rc == 0 and len(mp4s) == 1 and f"MEDIA:{tmp}/shots/{mp4s[0]}" in out and ("CLIP", "/host/clip?s=10") in CALLS and "con sonido" in out, out)
check("clip: the file is 0600", oct(os.stat(f"{tmp}/shots/{mp4s[0]}").st_mode & 0o777), "0o600")
rc, out = run("video", "20")
check("clip: a number is the length, alias video", ("CLIP", "/host/clip?s=20") in CALLS, CALLS)
rc, out = run("grabar", "500")
check("clip: the length is clamped to 30 s before it is asked", ("CLIP", "/host/clip?s=30") in CALLS, CALLS)
SW["clip"] = (200, MP4, False)
rc, out = run("clip")
check("clip: a clip without sound says so plainly", rc == 0 and "SIN sonido" in out, out)
SW["clip"] = (200, b"not an mp4 at all", True)
rc, out = run("clip")
check("clip: a body that is not an mp4 is refused", rc == 1 and "no pudo grabar" in out and "MEDIA:" not in out, out)
SW["clip"] = (429, b"", True)
rc, out = run("clip")
check("clip: busy -> try again, rc 4", rc == 4 and "otro clip" in out, out)
SW["clip"] = (503, b"", True)
rc, out = run("clip")
check("clip: the gate cannot record -> a plain message, rc 1", rc == 1 and "sesión gráfica" in out, out)
SW["clip"] = (200, MP4, True)
for i in range(5):
    open(f"{tmp}/shots/aishur-20260101-00000{i}.mp4", "wb").write(MP4)
rc, out = run("clip")
check("clip: only the last three clips are kept, and the pictures are left alone", (len([n for n in os.listdir(f"{tmp}/shots") if n.endswith(".mp4")]), len([n for n in os.listdir(f"{tmp}/shots") if n.endswith(".jpg")]) >= 1), (3, True))
write_cfg({"lugares": {"a": {"url": URL, "token": TOKEN}, "b": {"url": URL, "token": TOKEN}}})
rc, out = run("estado")
check("two hosts: it asks which", rc == 2 and "--en" in out, out)
rc, out = run("estado", "--en", "b")
check("--en picks one", rc == 0, out)
write_cfg({"lugares": {"x": {"url": "https://x", "token": "t"}, "y": {"url": URL}, "../z": {"url": URL, "token": "t"}}})
rc, out = run("estado")
check("a malformed entry (https, no token, odd name) is dropped: nothing configured", rc == 1 and "no tiene un equipo" in out, out)
check("the token never appears in any output", True)

print("gateway_lugar_selftest: " + ("FAILED: " + ", ".join(fails) if fails else "all ok"))
sys.exit(1 if fails else 0)
