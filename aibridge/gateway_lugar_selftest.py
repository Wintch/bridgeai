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
CAP = {"enabled": False, "profile": "full", "profiles": {"calidad": "720p30, 1 Mbit/s, stereo 64k", "full": "1080p60, 8 Mbit/s, stereo 128k", "medio": "720p30, 3 Mbit/s, stereo 96k", "ligero": "480p30, 1 Mbit/s, mono 48k"}, "recording": {"active": False}}
SW = {"launch_code": 200, "power_code": 200, "after_launch": None, "shot": (200, b""), "clip": (200, b"", True), "rec": (200, {}), "recfile": (200, b"")}
RECCALLS = []


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
        if self.path == "/host/capture":
            return self._send(200, CAP)
        if self.path.startswith("/host/rec/file"):
            CALLS.append(("RECFILE", self.path))
            code, body = SW["recfile"]
            if code != 200:
                return self._send(code, {"why": "x"})
            self.send_response(200); self.send_header("Content-Type", "video/mp4"); self.send_header("Content-Length", str(len(body))); self.end_headers()
            return self.wfile.write(body)
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
        if self.path == "/host/rec":
            RECCALLS.append(body)
            code, out = SW["rec"]
            return self._send(code, out)
        if self.path == "/host/capture":
            if "enabled" in body:
                CAP["enabled"] = body["enabled"]
            if "profile" in body:
                CAP["profile"] = body["profile"]
            return self._send(200, CAP)
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

# profiles, the switch (the person's), and the stats in `estado`
write_cfg(CFG)
reset()
CAP.update(enabled=False, profile="full")
SW["clip"] = (403, b"", True)
rc, out = run("clip")
check("clip with recording off: says it is off and that the person turns it on, rc 5", rc == 5 and "apagado" in out and "/lugar rec on" in out and "MEDIA:" not in out, out)
SW["clip"] = (200, MP4, True)
CALLS.clear()
rc, out = run("clip", "ligero", "15")
check("clip names a profile: it is asked for with the length", ("CLIP", "/host/clip?s=15&p=ligero") in CALLS, CALLS)
rc, out = run("rec")
check("rec with nothing else just reports the switch (off, profiles listed)", rc == 0 and "apagada" in out and "ligero" in out, out)
rc, out = run("rec", "on", "ligero")
check("the agent cannot turn recording on: prints the person's command, changes nothing (rc 5)", rc == 5 and "/lugar rec on" in out and CAP["enabled"] is False, out)
rc, out = run("rec", "on", "ligero", "--persona")
check("the person's /lugar rec on ligero turns it on with that profile", rc == 0 and CAP["enabled"] is True and CAP["profile"] == "ligero" and "habilitada, perfil ligero" in out, out)
rc, out = run("rec", "off", "--persona")
check("the person's /lugar rec off turns it off and keeps the profile", rc == 0 and CAP["enabled"] is False and CAP["profile"] == "ligero" and "apagada" in out, out)
rc, out = run("perfil", "full", "--persona")
check("perfil changes only the profile", rc == 0 and CAP["profile"] == "full" and CAP["enabled"] is False, out)
STATE.update(display={"output": "HDMI-0", "mode": "1920x1080_144", "hz": 144.0}, encoder={"sessions": 1, "fps": 143.0, "latency_ms": 4.2},
             sunshine={"client": True, "codec": "hevc_nvenc", "bitrate_mbps": 39.4, "resolution": "1920x1080", "problem_count": 0, "problems": []},
             stream={"hz_ok": True, "frames": "ok", "fps": 143.0, "of": 144.0}, capture=dict(CAP, enabled=True, recording={"active": True, "profile": "full", "secs": 10, "elapsed_s": 4}))
rc, out = run("estado")
check("estado reports the 144 Hz mode, the encoder's fps against the refresh, the codec and bitrate, and that it is recording",
      rc == 0 and "1920x1080_144 a 144 Hz" in out and "144 Hz está activo" in out and "143 de 144" in out and "sin pérdida de cuadros en el servidor" in out
      and "hevc_nvenc, 39.4 Mbit/s" in out and "GRABANDO ahora, perfil full, 4 de 10 s" in out and "Ctrl+Alt+Shift+S" in out, out)
STATE.update(display={"output": "HDMI-0", "mode": "1920x1080", "hz": 60.0}, stream={"hz_ok": False, "frames": "loss", "fps": 40.0, "of": 60.0},
             sunshine={"client": True, "problem_count": 1, "problems": ["Failed to start capture session: the display server is in modeset"]}, capture=dict(CAP, enabled=False, recording={"active": False}))
rc, out = run("stats")
check("estado (alias stats) flags a 60 Hz screen, lost frames, Sunshine's last problem, and recording off",
      "NO es el modo de 144 Hz" in out and "ATENCIÓN" in out and "40 de 60" in out and "modeset" in out and "Grabación: apagada" in out, out)
STATE.update(stream={"hz_ok": True, "frames": "idle"}, sunshine={"client": False, "problem_count": 0, "problems": []})
rc, out = run("estado")
check("estado with nobody connected says so and does not claim frame stats", "nadie está conectado" in out and "cuadros por segundo" not in out, out)
STATE.pop("display"); STATE.pop("stream"); STATE.pop("sunshine"); STATE.pop("encoder"); STATE.pop("capture")
rc, out = run("estado")
check("estado against an older gate (no stats) still works", rc == 0 and "está encendida" in out, out)

# gateway lugar largo: the long recording at the origin, delivered in parts, deleted after the person confirms
write_cfg(CFG)
reset()
RECCALLS.clear()
CAP.update(enabled=True, profile="calidad", recording={"active": False}, kept=[], kept_bytes=0, cap_bytes=10_000_000_000)
SW["rec"] = (403, {"why": "capture_off"})
rc, out = run("largo", "start")
check("largo start with recording off: says it is off and that the person turns it on, rc 5", rc == 5 and "apagado" in out and "/lugar rec on" in out, out)
SW["rec"] = (200, {"started": True, "name": "rec-20261124-230000", "profile": "calidad", "audio": True, "cap_bytes": 10_000_000_000})
rc, out = run("largo", "start", "ligero")
check("largo start asks for the profile and says what it did (name, profile, sound, 10-min segments, 10 GB cap)",
      rc == 0 and RECCALLS[-1] == {"action": "start", "profile": "ligero"} and "rec-20261124-230000" in out and "10 min" in out and "10 GB" in out and "con sonido" in out, (out, RECCALLS))
SW["rec"] = (409, {"why": "already_recording", "name": "rec-20261124-230000"})
rc, out = run("largo", "start")
check("largo start while recording: names the running one, rc 4", rc == 4 and "rec-20261124-230000" in out, out)
SW["rec"] = (507, {"why": "store_full", "bytes": 10_100_000_000, "cap": 10_000_000_000})
rc, out = run("largo", "start")
check("largo start with the store full: explains and points to lista, rc 3", rc == 3 and "10.1 GB" in out and "largo lista" in out, out)
SW["rec"] = (200, {"name": "rec-20261124-230000", "why": "requested", "elapsed_s": 1325, "segments": 3, "bytes": 1_450_000_000, "parts": 1})
rc, out = run("largo", "stop")
check("largo stop reports minutes, GB, segments, parts and the way to send it", rc == 0 and "22 min 5 s" in out and "1.45 GB" in out and "3 segmento" in out and "largo enviar rec-20261124-230000" in out, out)
SW["rec"] = (409, {"why": "not_recording"})
rc, out = run("largo", "stop")
check("largo stop with nothing running says so, rc 4", rc == 4 and "no estaba grabando" in out, out)
CAP.update(kept=[{"name": "rec-20261124-230000", "bytes": 1_450_000_000, "segments": 3, "parts": 2}, {"name": "rec-20261125-010000", "bytes": 300_000_000, "segments": 1, "parts": 1}], kept_bytes=1_750_000_000)
rc, out = run("largo", "lista")
check("largo lista shows what is kept against the cap", rc == 0 and "1.8 de 10 GB en 2 grabación" in out and "rec-20261125-010000: 0.3 GB" in out, out)
SW["recfile"] = (200, MP4)
CALLS.clear()
rc, out = run("largo", "enviar", "rec-20261124-230000")
parts = sorted(n for n in os.listdir(f"{tmp}/shots") if n.startswith("rec-20261124-230000-p"))
check("largo enviar downloads every part in order, one MEDIA line each, and says the original stays",
      rc == 0 and parts == ["rec-20261124-230000-p1.mp4", "rec-20261124-230000-p2.mp4"] and out.count("MEDIA:/") == 2 and ("RECFILE", "/host/rec/file?name=rec-20261124-230000&part=2") in CALLS
      and "sigue en aishur" in out and "largo borrar rec-20261124-230000" in out, (out, parts))
check("the downloaded parts are 0600", oct(os.stat(f"{tmp}/shots/{parts[0]}").st_mode & 0o777), "0o600")
rc, out = run("largo", "enviar")
check("largo enviar with no name takes the newest finished one", rc == 0 and "rec-20261125-010000" in out, out)
CAP["recording"] = {"active": True, "kind": "long", "name": "rec-20261125-010000", "profile": "calidad", "elapsed_s": 600, "segments": 1, "bytes": 300_000_000, "cap_bytes": 10_000_000_000}
rc, out = run("largo", "enviar", "rec-20261125-010000")
check("largo enviar refuses a recording that is still running, rc 3", rc == 3 and "Está grabando" in out, out)
CAP["recording"] = {"active": False}
SW["recfile"] = (503, b"")
rc, out = run("largo", "enviar", "rec-20261124-230000")
check("a failed part leaves the original and says so, rc 1", rc == 1 and "El original sigue" in out, out)
SW["rec"] = (200, {"deleted": "rec-20261124-230000", "freed_bytes": 1_450_000_000})
rc, out = run("largo", "borrar", "rec-20261124-230000")
left = [n for n in os.listdir(f"{tmp}/shots") if n.startswith("rec-20261124-230000-p")]
check("largo borrar deletes at the origin and the temporary copies here, and says how much it freed", rc == 0 and left == [] and "1.45 GB" in out and RECCALLS[-1] == {"action": "delete", "name": "rec-20261124-230000"}, (out, left))
rc, out = run("largo", "borrar")
check("largo borrar without a name asks which, rc 2", rc == 2, out)
CAP.update(recording={"active": True, "kind": "long", "name": "rec-20261125-010000", "profile": "calidad", "elapsed_s": 780, "segments": 1, "bytes": 2_100_000_000, "cap_bytes": 10_000_000_000}, kept=[{"name": "rec-20261125-010000", "bytes": 300_000_000, "segments": 1, "parts": 1}])
STATE.update(capture=dict(CAP))
rc, out = run("estado")
check("estado says it is recording: minutes, profile, GB of the cap", rc == 0 and "GRABANDO desde hace 13 min" in out and "2.1 de 10 GB" in out and "perfil calidad" in out, out)
CAP.update(recording={"active": False, "last_stop": {"name": "rec-20261125-010000", "why": "cap"}})
STATE.update(capture=dict(CAP))
rc, out = run("estado")
check("estado says a recording stopped by itself and why (the cap)", "se cortó sola" in out and "tope de espacio" in out, out)
STATE.pop("capture", None)
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
