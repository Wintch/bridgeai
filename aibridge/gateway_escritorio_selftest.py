#!/usr/bin/env python3
"""Offline checks for `gateway escritorio` and its jobwatch notice against a fake gate /place/* (loopback only). Run: python3 -I gateway_escritorio_selftest.py"""
import contextlib, importlib.machinery, importlib.util, io, json, os, subprocess, sys, tempfile, threading, time
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []
TOKEN = "place-token-for-tests"
ST = {"place": "alpha", "state": "exited", "running": False, "urls": {"http": "http://10.9.8.7:3010", "https": "https://10.9.8.7:3011"}, "idle_limit_min": 30, "warn_min": 10}
CALLS = []
SW = {"code": 200}


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _go(self, method):
        n = int(self.headers.get("Content-Length", "0"))
        if n:
            self.rfile.read(n)
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            code, out = 401, {"why": "token"}
        elif SW["code"] != 200:
            code, out = SW["code"], {"why": "x"}
        else:
            CALLS.append((method, self.path))
            if self.path == "/place/start":
                ST.update(state="running", running=True, idle_min=0, closes_in_min=30, others_running=SW.get("others", 0))
            elif self.path == "/place/stop":
                ST.update(state="exited", running=False, closed_reason="person")
            elif self.path == "/place/screen":
                if SW.get("assistant") is False:
                    code, out = 403, {"why": "assistant_off"}
                else:
                    img = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 4
                    self.send_response(200); self.send_header("Content-Type", "image/jpeg"); self.send_header("Content-Length", str(len(img))); self.end_headers()
                    return self.wfile.write(img)
                b = json.dumps(out).encode()
                self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); return self.wfile.write(b)
            elif self.path == "/place/games":
                b = json.dumps({"games": [{"store": "steam", "id": "12210", "name": "Grand Theft Auto IV"}, {"store": "epic", "id": "Calluna", "name": "Control"}]}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); return self.wfile.write(b)
            code, out = 200, dict(ST)
        b = json.dumps(out).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    do_GET = lambda self: self._go("GET")
    do_POST = lambda self: self._go("POST")


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
tmp = tempfile.mkdtemp()
URL = f"http://127.0.0.1:{srv.server_port}"
os.environ.update(AIBRIDGE_LUGAR_SHOTS=f"{tmp}/shots", GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log", AIBRIDGE_JOBS_DIR=f"{tmp}/jobs")


def write_cfg(c):
    json.dump(c, open(f"{tmp}/gw.json", "w"))


write_cfg({"escritorio": {"url": URL, "token": TOKEN}})
spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)


def run(*argv):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        rc = gw.cmd_escritorio(list(argv))
    return rc, b.getvalue()


job = f"{tmp}/jobs/escritorio.json"

write_cfg({})
rc, out = run("estado")
check("without an escritorio block it says so and calls nothing", rc == 1 and "no tiene un escritorio" in out and not CALLS, out)
check("the watch (aviso) is silent and done without a block", run("aviso") == (3, "\n") or run("aviso") == (3, ""), run("aviso"))
write_cfg({"escritorio": {"url": URL, "token": TOKEN}})

rc, out = run("estado")
check("estado of a closed place: closed, files safe, how to open", rc == 0 and "está cerrado" in out and "abrir" in out and "archivos" in out, out)
CALLS.clear()
rc, out = run("abrir")
check("abrir opens it and gives both addresses, the 30 min rule and the warning promise", rc == 0 and "http://10.9.8.7:3010" in out and "https://10.9.8.7:3011" in out and "30 min" in out and "10 min antes" in out, out)
check("abrir called only /place/start with the person's token", CALLS == [("POST", "/place/start")], CALLS)
check("abrir registers the jobwatch entry that carries the warnings", os.path.exists(job) and json.load(open(job))["watch"] == "escritorio", os.path.exists(job))
SW["others"] = 1
rc, out = run("abrir")
check("another place open on the machine: told that the card is shared, without saying whose", "otro escritorio" in out and "placa de video se comparte" in out, out)
SW["others"] = 0
rc, out = run("seguir")
check("seguir keeps it and says a full turn of time", rc == 0 and "otra vuelta completa" in out and CALLS[-1] == ("POST", "/place/keep"), out)

# the notice (what jobwatch asks)
ST.update(warned_at=2000, closes_in_min=9)
rc, out = run("aviso")
check("aviso: the warning once, with the minutes left and the save-your-work hint", rc == 0 and "se cierra en unos 9 min" in out and "escritorio seguir" in out and "guardalo" in out, out)
rc, out = run("aviso")
check("aviso: the same warning is not repeated", rc == 0 and out.strip() == "", out)
ST.update(warned_at=2600)
rc, out = run("aviso")
check("aviso: a new warning (after being kept and idle again) is given again", "se cierra en unos" in out, out)
ST.update(state="exited", running=False, closed_reason="idle", closed_at=3000)
rc, out = run("aviso")
check("aviso: the idle close is told once, files safe, and the watch ends (rc 3, entry removed)", rc == 3 and "Cerré tu escritorio por inactividad" in out and "archivos están guardados" in out and not os.path.exists(job), (rc, out))
rc, out = run("aviso")
check("aviso: nothing more after that", rc == 3 and out.strip() == "", out)
ST.update(closed_reason="person", closed_at=3500, warned_at=None)
run("abrir"); run("cerrar")
check("cerrar: stops it, says files stay, removes the watch", not os.path.exists(job), os.path.exists(job))
rc, out = run("cerrar")
check("cerrar text", rc == 0 and "Cerré tu escritorio" in out and "archivos quedan guardados" in out, out)
ST.update(closed_reason="person", closed_at=3600)
rc, out = run("aviso")
check("a close the person asked for is never announced as an idle close", rc == 3 and out.strip() == "", out)

# errors
SW["code"] = 404
rc, out = run("estado")
check("404: the place does not exist yet", rc == 1 and "todavía no existe" in out, out)
SW["code"] = 502
rc, out = run("abrir")
check("502 on open: asked to retry, nothing registered", rc == 1 and "no respondió bien" in out, out)
SW["code"] = 200
write_cfg({"escritorio": {"url": URL, "token": "wrong"}})
rc, out = run("estado")
check("a token the gate refuses: told to ask the administrator", rc == 1 and "no acepta mi permiso" in out, out)
write_cfg({"escritorio": {"url": "http://127.0.0.1:9", "token": TOKEN}})
rc, out = run("estado")
check("host asleep: says so and that waking it from here is not possible yet", rc == 1 and "dormida o apagada" in out, out)
check("the watch stays silent and retries while the host is unreachable", run("aviso")[0] == 1, "")
write_cfg({"escritorio": {"url": URL, "token": TOKEN}})
check("an unknown verb is usage, rc 2", run("fly")[0] == 2, "")
check("the verbs have Spanish and English aliases", [gw.ES_ALIASES[x] for x in ("abrir", "open", "cerrar", "close", "seguir", "keep", "estado", "status")] == ["abrir", "abrir", "cerrar", "cerrar", "seguir", "seguir", "estado", "estado"], "")
check("the command is registered in the gateway table", '"escritorio": cmd_escritorio' in open(os.path.join(HERE, "gateway.py")).read(), "")

# jobwatch: runs a fixed command, relays its text, drops the entry on rc 3
loader = importlib.machinery.SourceFileLoader("jw", os.path.join(HERE, "jobwatch.py")); sp = importlib.util.spec_from_loader("jw", loader)
jw = importlib.util.module_from_spec(sp); loader.exec_module(jw)
jd = tempfile.mkdtemp(); jw.REGISTRY = jd
fakegw = os.path.join(jd, "fakegw"); calls = os.path.join(jd, "calls")
open(fakegw, "w").write(f'#!/bin/sh\necho "$@" >> {calls}\n[ -f {jd}/done ] && {{ echo "💤 cerrado"; exit 3; }}\n[ -f {jd}/warn ] && echo "⏳ aviso"\nexit 0\n')
os.chmod(fakegw, 0o755); jw.GATEWAY = fakegw
p = os.path.join(jd, "escritorio.json")
json.dump({"watch": "escritorio", "title": "Escritorio", "started": time.time(), "timeout_min": 1440, "check_cmd": "touch /tmp/pwned-by-selftest"}, open(p, "w")); os.utime(p, (time.time() - 10,) * 2)
open(os.path.join(jd, "warn"), "w").close()
b = io.StringIO()
with contextlib.redirect_stdout(b):
    jw.main()
check("jobwatch relays the warning text and keeps the entry", "⏳ aviso" in b.getvalue() and os.path.exists(p), b.getvalue())
check("jobwatch runs exactly `gateway escritorio aviso` and nothing from the file", open(calls).read().strip() == "escritorio aviso" and not os.path.exists("/tmp/pwned-by-selftest"), open(calls).read())
os.utime(p, (time.time() - 10,) * 2); open(os.path.join(jd, "done"), "w").close()
b = io.StringIO()
with contextlib.redirect_stdout(b):
    jw.main()
check("jobwatch relays the closing and removes the entry on rc 3", "💤 cerrado" in b.getvalue() and not os.path.exists(p), b.getvalue())
json.dump({"watch": "escritorio", "started": time.time() - 90000, "timeout_min": 1440}, open(p, "w")); os.utime(p, (time.time() - 10,) * 2)
os.unlink(os.path.join(jd, "done")); os.unlink(os.path.join(jd, "warn"))
with contextlib.redirect_stdout(io.StringIO()):
    jw.main()
check("an entry older than its timeout is dropped even if the gate never answers", not os.path.exists(p), "")

# --- the person's own bot looking at their place (read-only verbs)
write_cfg({"escritorio": {"url": URL, "token": TOKEN}}); SW["code"] = 200
rc, out = run("pantalla")
shot = out.split("MEDIA:")[1].split(".", 1)[0] + ".jpg" if "MEDIA:" in out else ""
check("escritorio pantalla saves the picture privately and says how to send it (MEDIA:)", rc == 0 and shot and os.path.exists(shot) and oct(os.stat(shot).st_mode)[-3:] == "600", out)
rc, out = run("captura")
check("captura is the same verb", rc == 0 and "MEDIA:" in out, out)
SW["assistant"] = False
rc, out = run("pantalla")
check("when the operator has not turned it on, it says so", rc == 1 and "apagado" in out, out)
SW.pop("assistant")
rc, out = run("juegos")
check("escritorio juegos lists the installed games with their store", rc == 0 and "Grand Theft Auto IV (Steam)" in out and "Control (Epic)" in out, out)

print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
