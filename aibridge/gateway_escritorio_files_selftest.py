#!/usr/bin/env python3
"""Offline checks for `gateway escritorio archivos|subir|convertir|bajar|borrar` against a fake gate /place/* (loopback only).
Run: python3 -I gateway_escritorio_files_selftest.py"""
import contextlib, importlib.util, io, json, os, sys, tempfile, threading, urllib.parse
import atexit as _a, shutil as _s
tmp = tempfile.mkdtemp(prefix="selftest-"); _a.register(_s.rmtree, tmp, True)
os.environ["TMPDIR"] = tempfile.tempdir = tmp
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []
TOKEN = "place-token-for-tests"
CALLS, UPLOADS = [], {}
FILES = {"input": [], "output": [], "working": 0}
BODIES = {"final.mov": b"m" * 5000, "cut.mp4": b"c" * 3000, "telegram/final.mp4": b"t" * 700, "notes.txt": b"hello"}
SW = {"convert": 200, "shrink": 200, "put": 200}
ML = {"list_code": 200, "list": {"devices": [{"name": "phone", "id": "aaaabbbb"}], "waiting": 0}, "pin_code": 200, "pin": {"accepted": True, "device": "phone"},
      "unpair_code": 200, "unpair": {"revoked": 1, "device": "phone"}}


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj=None, raw=None):
        b = raw if raw is not None else json.dumps(obj or {}).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _go(self, method):
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n) if n else b""
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._send(401, {"why": "token"})
        path, _, qs = self.path.partition("?")
        q = {k: urllib.parse.unquote_plus(v) for k, v in (x.split("=", 1) for x in qs.split("&") if "=" in x)}
        CALLS.append((method, path, q, body if path != "/place/input" else len(body)))
        if path == "/place/files":
            return self._send(200, FILES)
        if path == "/place/input":
            if SW["put"] != 200:
                return self._send(SW["put"], {"why": "no_space"})
            UPLOADS[q["name"]] = body
            return self._send(200, {"name": q["name"], "size": len(body)})
        if path == "/place/file":
            return self._send(200, raw=BODIES[q["name"]]) if q.get("name") in BODIES else self._send(404, {"why": "no_such_file"})
        if path == "/place/convert":
            return self._send(SW["convert"], {"started": True, "result": "resolve/x.mov"})
        if path == "/place/shrink":
            return self._send(SW["shrink"], {"started": True, "result": "telegram/x.mp4"})
        if path == "/place/moonlight":
            return self._send(ML["list_code"], ML["list"])
        if path == "/place/moonlight/pin":
            return self._send(ML["pin_code"], ML["pin"])
        if path == "/place/moonlight/unpair":
            return self._send(ML["unpair_code"], ML["unpair"])
        if path == "/place/delete":
            j = json.loads(body)
            return self._send(200, {"name": j["name"], "freed_bytes": 5000}) if j["name"] in BODIES else self._send(404, {"why": "no_such_file"})
        self._send(404, {"why": "not_found"})

    do_GET = lambda self: self._go("GET")
    do_POST = lambda self: self._go("POST")


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
work = os.path.join(tmp, "work"); os.makedirs(os.path.join(work, "descargas")); os.makedirs(os.path.join(work, ".ssh"))
os.environ.update(AIBRIDGE_LUGAR_SHOTS=f"{tmp}/shots", GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log",
                  AIBRIDGE_JOBS_DIR=f"{tmp}/jobs", GATEWAY_WORKDIR=work)
json.dump({"escritorio": {"url": f"http://127.0.0.1:{srv.server_port}", "token": TOKEN}}, open(f"{tmp}/gw.json", "w"))
spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
gw = importlib.util.module_from_spec(spec); spec.loader.exec_module(gw)


def run(*argv):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        rc = gw.cmd_escritorio(list(argv))
    return rc, b.getvalue()


def mk(rel, data):
    p = os.path.join(work, rel); open(p, "wb").write(data); return p


clip = mk("descargas/mi clip (1).mp4", b"v" * 4000)
mk(".ssh/id", b"secret"); secret = mk("descargas/cfg.txt", b"x"); os.symlink(os.path.join(work, ".ssh", "id"), os.path.join(work, "descargas", "tricky.mp4"))
outside = os.path.join(tmp, "outside.mp4"); open(outside, "wb").write(b"o")
os.symlink(outside, os.path.join(work, "descargas", "out.mp4"))

# --- subir
rc, out = run("subir", clip)
check("subir sends the file (streamed) to /place/input with a clean name and starts the conversion", rc == 0 and UPLOADS.get("mi clip (1).mp4") == b"v" * 4000 and ("POST", "/place/convert") in [(c[0], c[1]) for c in CALLS], (rc, out, list(UPLOADS)))
check("subir says where the converted file will be and that archivos lists it", "input/resolve/mi clip (1).mov" in out and "archivos" in out, out)
conv = [c for c in CALLS if c[1] == "/place/convert"][-1]
check("subir asks for the default tier hq and the uploaded name", json.loads(conv[3]) == {"name": "mi clip (1).mp4", "quality": "hq"}, conv)
CALLS.clear(); rc, out = run("subir", clip, "lb")
check("subir with a tier passes it", json.loads([c for c in CALLS if c[1] == "/place/convert"][-1][3])["quality"] == "lb", CALLS)
CALLS.clear(); rc, out = run("subir", clip, "crudo")
check("subir crudo does not convert", not [c for c in CALLS if c[1] == "/place/convert"] and "carpeta de entrada" in out, out)
CALLS.clear(); rc, out = run("subir", mk("descargas/notas.txt", b"abc"))
check("subir of a non-video file does not convert", not [c for c in CALLS if c[1] == "/place/convert"] and rc == 0, out)
SW["convert"] = 409; rc, out = run("subir", clip)
check("subir with the desktop closed keeps the file and says to open and convert", rc == 0 and "escritorio abrir" in out and "escritorio convertir" in out, out); SW["convert"] = 200
check("subir refuses a file outside the work dir, a hidden folder, a link out and a missing file", [run("subir", p)[0] for p in (outside, os.path.join(work, ".ssh", "id"), os.path.join(work, "descargas", "tricky.mp4"), os.path.join(work, "descargas", "out.mp4"), os.path.join(work, "nope.mp4"))] == [2] * 5, "")
check("nothing of the refused files reached the gate", all(n in ("mi clip (1).mp4", "notas.txt") for n in UPLOADS), list(UPLOADS))
SW["put"] = 507; rc, out = run("subir", clip)
check("subir tells when the machine has no space", rc == 1 and "no hay espacio" in out, out); SW["put"] = 200
check("subir without a file is usage", run("subir")[0] == 2, "")
check("es_clean_name keeps one safe component", [gw.es_clean_name(x) for x in ("a/b/../c d.mp4", ".bashrc", "-rf", "ñandú.mp4", "x" * 300)] == ["c d.mp4", "bashrc", "rf", "and_.mp4", "x" * 150], [gw.es_clean_name(x) for x in ("a/b/../c d.mp4", ".bashrc", "-rf", "ñandú.mp4")])

# --- archivos
FILES.update(input=[{"name": "mi clip.mp4", "size": 4000, "mtime": 5}], output=[{"name": "final.mov", "size": 5000, "mtime": 9}, {"name": "cut.mp4", "size": 3000, "mtime": 8}], working=1)
rc, out = run("archivos")
check("archivos lists both folders with sizes and the work in progress", rc == 0 and "mi clip.mp4" in out and "final.mov" in out and "cut.mp4" in out and "1 archivo(s) en preparación" in out, out)

# --- bajar
CALLS.clear(); rc, out = run("bajar", "cut.mp4")
dest = os.path.join(tmp, "shots", "es-cut.mp4")
check("bajar of an mp4 downloads it and gives a MEDIA line", rc == 0 and f"MEDIA:{dest}" in out and open(dest, "rb").read() == b"c" * 3000, out)
check("bajar says the original stays and how to delete after the person confirms", "borrar cut.mp4" in out and "confirme" in out, out)
CALLS.clear(); rc, out = run("bajar", "final.mov")
check("bajar of a .mov export starts the Telegram version and sends nothing", rc == 3 and [c[1] for c in CALLS if c[1] != "/place/files"] == ["/place/shrink"] and "MEDIA:" not in out and "mp4" in out, (rc, out, CALLS))
check("the shrink request carries the 1900 MB ceiling", json.loads([c for c in CALLS if c[1] == "/place/shrink"][0][3]) == {"name": "final.mov", "max_mb": 1900}, CALLS)
FILES["output"].append({"name": "telegram/final.mp4", "size": 700, "mtime": 10})
CALLS.clear(); rc, out = run("bajar", "final.mov")
check("once the Telegram version exists bajar sends that one", rc == 0 and "telegram_final.mp4" in out and not [c for c in CALLS if c[1] == "/place/shrink"], (out, CALLS))
CALLS.clear(); rc, out = run("bajar")
check("bajar without a name takes the newest export that is not already a Telegram copy", "final.mov" in out or "final.mp4" in out, out)
CALLS.clear(); rc, out = run("bajar", "final.mov", "crudo")
check("bajar crudo sends the .mov as it is when it fits", rc == 0 and "MEDIA:" in out and not [c for c in CALLS if c[1] == "/place/shrink"], (out, CALLS))
SW["shrink"] = 409; FILES["output"].pop(); CALLS.clear(); rc, out = run("bajar", "final.mov")
check("bajar with the desktop closed says to open it", rc == 1 and "escritorio abrir" in out, out); SW["shrink"] = 200
FILES["output"] = [{"name": "huge.mov", "size": 3_000_000_000, "mtime": 1}, {"name": "huge.zip", "size": 3_000_000_000, "mtime": 0}]
CALLS.clear(); rc, out = run("bajar", "huge.mov", "crudo")
check("a video over the limit is shrunk even with crudo", rc == 3 and [c[1] for c in CALLS if c[1] == "/place/shrink"] == ["/place/shrink"], (rc, out))
CALLS.clear(); rc, out = run("bajar", "huge.zip")
check("a non-video over the limit is refused and left in the folder", rc == 1 and "no es un video" in out and not [c for c in CALLS if c[1] in ("/place/file", "/place/shrink")], out)
FILES["output"] = []
rc, out = run("bajar")
check("bajar with nothing exported says so (rc 3)", rc == 3 and "nada exportado" in out, out)
check("bajar of an unknown name says so", run("bajar", "nope.mov")[0] == 3, "")

# --- borrar
FILES["output"] = [{"name": "cut.mp4", "size": 3000, "mtime": 8}]
rc, out = run("borrar", "cut.mp4")
check("borrar deletes the gate's file and the temporary copy here", rc == 0 and "liberé 5 KB" in out and not os.path.exists(dest), (out, os.path.exists(dest)))
check("borrar of an unknown name is rc 1, without a name is usage", (run("borrar", "nope")[0], run("borrar")[0]) == (1, 2), "")

# --- Moonlight: confirm the PIN, list and revoke
CALLS.clear(); rc, out = run("pin", "1234")
check("pin sends the 4 digits to the gate and says which device was confirmed", rc == 0 and "confirmé el PIN de «phone»" in out and json.loads(CALLS[-1][3]) == {"pin": "1234"}, (rc, out, CALLS))
check("pin refuses anything but 4 digits without calling the gate", all(run("pin", x)[0] == 2 for x in ("12", "12345", "12ab", "1234; ls", "")) and not [c for c in CALLS if c[1].endswith("/pin")][1:], CALLS)
ML["pin_code"], ML["pin"] = 409, {"why": "nothing_waiting"}; rc, out = run("pin", "1234")
check("pin with no pairing waiting says to start it in Moonlight first", rc == 1 and "agregá el escritorio primero" in out, out)
ML["pin_code"], ML["pin"] = 409, {"why": "not_running"}; check("pin with the desktop closed says to open it", "escritorio abrir" in run("pin", "1234")[1], "")
ML["pin_code"], ML["pin"] = 200, {"accepted": False, "device": "phone"}; rc, out = run("pin", "1234")
check("a PIN Sunshine does not confirm is not reported as done", rc == 1 and "no confirmó" in out, out)
ML["pin_code"], ML["pin"] = 404, {"why": "no_moonlight"}; check("a place without Moonlight says so", "no tiene Moonlight" in run("pin", "1234")[1], "")
ML["pin_code"], ML["pin"] = 200, {"accepted": True, "device": "phone"}
rc, out = run("dispositivos")
check("dispositivos lists the paired devices by name and short id, never more", rc == 0 and "phone  (id aaaabbbb)" in out and "revocar" in out, out)
ML["list"] = {"devices": [], "waiting": 1}; rc, out = run("dispositivos")
check("dispositivos with none paired says so and mentions a waiting PIN", "Ningún dispositivo" in out and "escritorio pin" in out, out)
ML["list_code"], ML["list"] = 409, {"why": "not_running"}; check("dispositivos with the desktop closed says to open it", "escritorio abrir" in run("dispositivos")[1], "")
ML["list_code"], ML["list"] = 200, {"devices": [{"name": "phone", "id": "aaaabbbb"}], "waiting": 0}
CALLS.clear(); rc, out = run("revocar", "phone")
check("revocar sends the name and says the device can no longer enter", rc == 0 and "Saqué «phone»" in out and json.loads(CALLS[-1][3]) == {"device": "phone"}, (out, CALLS))
CALLS.clear(); ML["unpair"] = {"revoked": 3}; rc, out = run("revocar", "todos")
check("revocar todos sends 'all', says how many and that pairing starts over", rc == 0 and json.loads(CALLS[-1][3]) == {"device": "all"} and "(3)" in out and "emparejar de nuevo" in out, (out, CALLS))
ML["unpair_code"], ML["unpair"] = 404, {"why": "no_such_device"}; check("revocar of an unknown device says so", run("revocar", "zzz")[0] == 1, "")
ML["unpair_code"], ML["unpair"] = 409, {"why": "ambiguous"}; check("revocar with an ambiguous id asks for more", "más de un dispositivo" in run("revocar", "abcd")[1], "")
check("revocar without an argument is usage", run("revocar")[0] == 2, "")
check("the verbs have aliases", [gw.ES_ALIASES[x] for x in ("devices", "revoke", "desemparejar", "moonlight")] == ["dispositivos", "revocar", "revocar", "dispositivos"], "")

# --- convertir, aliases, unreachable
CALLS.clear(); rc, out = run("convertir", "mi clip.mp4", "sq")
check("convertir starts it with the tier", rc == 0 and json.loads(CALLS[0][3]) == {"name": "mi clip.mp4", "quality": "sq"}, (out, CALLS))
SW["convert"] = 409; check("convertir with the desktop closed says to open it", "escritorio abrir" in run("convertir", "x.mp4")[1], ""); SW["convert"] = 200
check("verbs have Spanish and English aliases", [gw.ES_ALIASES[x] for x in ("subir", "upload", "bajar", "download", "borrar", "delete", "archivos", "files", "convertir", "convert")] == ["subir", "subir", "bajar", "bajar", "borrar", "borrar", "archivos", "archivos", "convertir", "convertir"], "")
json.dump({"escritorio": {"url": "http://127.0.0.1:9", "token": TOKEN}}, open(f"{tmp}/gw.json", "w"))
rc, out = run("subir", clip)
check("a gate that cannot be reached: says asleep or off, no traceback", rc == 1 and "dormida o apagada" in out, out)
json.dump({}, open(f"{tmp}/gw.json", "w"))
check("without an escritorio block the file verbs say so", run("archivos")[0] == 1, "")

print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
