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
SW = {"launch_code": 200, "power_code": 200, "after_launch": None}


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
os.environ.update(GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log", AIBRIDGE_LUGAR_WAIT_S="1")


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
