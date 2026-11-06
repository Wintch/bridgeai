#!/usr/bin/env python3
"""Offline checks for `gateway virus` and the abusech service against fake CIRCL and MalwareBazaar servers. Run: python3 -I gateway_virus_selftest.py"""
import contextlib, hashlib, importlib.util, io, json, os, sys, tempfile, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
calls = {"circl": [], "bazaar": []}
mode = {"bazaar": "ok"}                # ok | 429 | badkey
KNOWN_CIRCL, BAD = set(), set()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        h = self.path.rsplit("/", 1)[-1]
        calls["circl"].append(h)
        if h in KNOWN_CIRCL:
            self.reply(200, {"FileName": "setup.exe", "SHA-256": h.upper(), "hashlookup:trust": 50})
        else:
            self.reply(404, {"message": "Non existing SHA-256"})

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        form = urllib.parse.parse_qs(raw.decode())
        calls["bazaar"].append({"key": self.headers.get("Auth-Key"), "form": form, "len": len(raw)})
        if mode["bazaar"] == "429":
            return self.reply(429, {"query_status": "too_many_requests"})
        if mode["bazaar"] == "badkey":
            return self.reply(200, {"query_status": "unknown_auth_key"})
        h = form.get("hash", [""])[0]
        if h in BAD:
            return self.reply(200, {"query_status": "ok", "data": [{"signature": "AgentTesla", "tags": ["exe", "stealer"], "file_type": "exe", "first_seen": "2026-10-30 10:00:00"}]})
        self.reply(200, {"query_status": "hash_not_found"})


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
os.makedirs(f"{tmp}/home", exist_ok=True)
os.environ.update(GATEWAY_LOG=f"{tmp}/log", AIBRIDGE_PREFS=f"{tmp}/prefs.json", AIBRIDGE_VIRUS_STATE=f"{tmp}/virus.json", HERMES_HOME=f"{tmp}/home",
                  AIBRIDGE_CIRCL_URL=base, AIBRIDGE_MALWAREBAZAAR_URL=base + "/api/v1/")
os.environ.pop("ABUSECH_AUTH_KEY", None)
spec = importlib.util.spec_from_file_location("gw", f"{HERE}/gateway.py")
gw = importlib.util.module_from_spec(spec); spec.loader.exec_module(gw)

fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)
def run(*argv):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        rc = gw.cmd_virus(list(argv))
    return rc, b.getvalue()
def make(name, data):
    p = os.path.join(tmp, name); open(p, "wb").write(data); return p
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def reset():
    calls["circl"].clear(); calls["bazaar"].clear()
    if os.path.exists(f"{tmp}/virus.json"): os.unlink(f"{tmp}/virus.json")

KEY = "k" * 40
exe = make("trainer.exe", b"MZ" + b"\x90" * 200 + b"first")
exe2 = make("other.exe", b"MZ" + b"\x90" * 200 + b"second")
exe3 = make("third.exe", b"MZ" + b"\x90" * 200 + b"third")
bad = make("evil.exe", b"MZ" + b"\x90" * 200 + b"evil"); BAD.add(sha(bad))
photo = make("holiday.jpg", b"\xff\xd8\xff\xe0" + b"0" * 100)
doc = make("cv.docx", b"PK\x03\x04" + b"0" * 100)
pdf = make("cv.pdf", b"%PDF-1.7 " + b"0" * 100)
zipf = make("mod.zip", b"PK\x03\x04" + b"0" * 100)
text = make("notes.txt", b"hello")

# 1. what is never asked about
for p in (photo, doc, pdf, text):
    rc, out = run(p)
    check(f"{os.path.basename(p)}: not consulted, and no hash left the machine", rc == 3 and "no lo consulto" in out and not calls["circl"] and not calls["bazaar"])
rc, out = run(os.path.join(tmp, "missing.exe"))
check("a missing file is said so", rc == 1 and "no encuentro" in out)
rc, out = run()
check("no argument prints usage", rc == 2 and "Uso:" in out)

# 2. no key: CIRCL only, says what is missing, never calls it safe
reset()
rc, out = run(exe)
check("no key: CIRCL asked with the hash only, MalwareBazaar not asked", rc == 0 and calls["circl"] == [sha(exe)] and not calls["bazaar"])
check("no key: says the key is missing and the verdict is not 'checked'", "falta la clave propia de abuse.ch" in out and "NO VERIFICADO" in out and "VEREDICTO" in out)
check("no key: the 💡 line explains how to get it", "💡" in out and "abusech" in out and "auth.abuse.ch" in out)
check("no key: never says safe or clean", "seguro" not in out.replace("no prueba que sea seguro", "").replace("sin llamarlo «seguro»", "") and "limpio" not in out.replace("«limpio»", ""))
check("the agent is told not to save the result", "no guardes este resultado" in out)
rc, out2 = run(exe)
check("the 💡 hint appears once a week at most", "💡" not in out2)

# 3. with a key
reset()
os.environ["ABUSECH_AUTH_KEY"] = KEY
rc, out = run(exe)
check("key: one POST with the Auth-Key header and the hash, no file bytes", rc == 0 and len(calls["bazaar"]) == 1 and calls["bazaar"][0]["key"] == KEY
      and calls["bazaar"][0]["form"] == {"query": ["get_info"], "hash": [sha(exe)]} and calls["bazaar"][0]["len"] < 200)
check("key: unknown everywhere is 'no concluyente', with the warning that it proves nothing", "NO CONCLUYENTE" in out and "NO prueba que sea seguro" in out)
check("the key never appears in the output or the log", KEY not in out and KEY not in open(f"{tmp}/log").read() and KEY not in open(f"{tmp}/virus.json").read())
check("the log keeps a hash prefix and states, not the file name", "trainer" not in open(f"{tmp}/log").read() and sha(exe)[:12] in open(f"{tmp}/log").read())
n = (len(calls["circl"]), len(calls["bazaar"]))
rc, out = run(exe)
check("cache: the same file again asks nobody", (len(calls["circl"]), len(calls["bazaar"])) == n)
rc, out = run(bad)
check("detected: names the signature and refuses to send it on", "DETECTADO" in out and "AgentTesla" in out and "No lo envíes" in out)
KNOWN_CIRCL.add(sha(exe2))
rc, out = run(exe2)
check("known to CIRCL only: says that list includes legitimate software and proves nothing", "archivo conocido" in out and "no prueba que sea seguro" in out and "NO CONCLUYENTE" in out)
rc, out = run(zipf)
check("a zip is an archive worth asking about", rc == 0 and "archivo comprimido" in out)
rc, out = run(exe3, bad)
check("several files: one report each", out.count("SHA-256:") == 2)

# 4. limits and back-off
reset(); mode["bazaar"] = "429"
rc, out = run(exe)
check("429: says it was not consulted and sets a pause", "límite de consultas" in out and "NO VERIFICADO" in out and json.load(open(f"{tmp}/virus.json"))["cooldown"] > 0)
mode["bazaar"] = "ok"; before = len(calls["bazaar"])
rc, out = run(exe2)
check("during the pause nothing is sent to abuse.ch", len(calls["bazaar"]) == before and "pidió esperar" in out)
reset(); gw.VIRUS_DAILY_MAX = 1
run(exe); before = len(calls["bazaar"])
rc, out = run(exe2)
check("the daily cap stops further queries and says why", len(calls["bazaar"]) == before and "consultas hoy" in out)
gw.VIRUS_DAILY_MAX = 150
reset(); mode["bazaar"] = "badkey"
rc, out = run(exe)
check("a rejected key is reported, not hidden", "no fue aceptada" in out and "NO VERIFICADO" in out)
mode["bazaar"] = "ok"

# 5. the service: key check, texts in three languages
ok, why = gw.service_check("abusech", KEY)
check("service_check accepts a key that gets hash_not_found", ok and why == "")
mode["bazaar"] = "badkey"
ok, why = gw.service_check("abusech", KEY)
check("service_check refuses an unknown key and shows the status it got", not ok and "unknown_auth_key" in why)
mode["bazaar"] = "429"
ok, why = gw.service_check("abusech", KEY)
check("service_check turns an HTTP error into a message", not ok and "429" in why)
sv = gw.SERVICES["abusech"]
check("abusech texts exist in es, ru and en, with the personal-use note and the 72 h limit",
      all(sv[f][l] for f in ("label", "gives", "without", "how", "note") for l in ("es", "ru", "en")) and "72" in sv["note"]["en"] and "Hide Profile" in sv["how"]["en"])
check("abusech is listed with the other services", "abusech" in gw.SERVICES and sv["env"] == "ABUSECH_AUTH_KEY" and sv["link"] == "https://auth.abuse.ch/")

print("\n".join(fails) or "gateway_virus_selftest: all ok")
sys.exit(1 if fails else 0)
