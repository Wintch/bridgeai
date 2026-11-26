#!/usr/bin/env python3
"""Offline test of the waker's wake service handoff (waker.py: wake_service_url, tell_wake_service): once the sentinel writes "⏳ Encendiendo
Hermes…" it tells the wake service, which deletes its own "despertando" notice. A local fake wake service on 127.0.0.1 records the calls.

Run from anywhere:  python3 -I ops/wake/wake_service_selftest.py
"""
import http.server, importlib.util, os, sys, threading
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("waker", os.path.join(HERE, "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
w.log = lambda *a, **k: None
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

SEEN, CODE = [], [200]
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        SEEN.append(self.path); self.send_response(CODE[0]); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a):
        pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"

w.CFG = {}
chk(w.tell_wake_service(123) is False and SEEN == [], "without \"wake_service\" nothing is sent")
w.CFG = {"wake_service": base + "/"}
chk(w.wake_service_url() == base, "the address is taken without its trailing slash")
chk(w.tell_wake_service(123456789) is True and SEEN == ["/posta?chat=123456789"], "the handoff names the chat and nothing else")
chk(w.tell_wake_service(-1001234) is True and SEEN[-1] == "/posta?chat=-1001234", "a group chat id (negative) works too")
n = len(SEEN)
chk(w.tell_wake_service("12&x=1") is False and len(SEEN) == n, "a chat that is not a number is never sent")
for bad in ("https://x:1", "http://x/estado", "ftp://x", "http://a b", 5):
    w.CFG = {"wake_service": bad}
    chk(w.wake_service_url() == "", f"a malformed address is ignored: {bad!r}")
w.CFG = {"wake_service": base}; CODE[0] = 500
chk(w.tell_wake_service(1) is False, "a failing wake service is a False, never an exception")
w.CFG = {"wake_service": "http://127.0.0.1:9"}
chk(w.tell_wake_service(1) is False, "an unreachable wake service is a False, never an exception")
src = open(os.path.join(HERE, "waker.py")).read()
chk("threading.Thread(target=tell_wake_service, args=(chat,), daemon=True).start()" in src, "the sentinel tells it in its own thread, right after \"Encendiendo Hermes\"")
srv.shutdown()
print("wake_service_selftest: " + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
