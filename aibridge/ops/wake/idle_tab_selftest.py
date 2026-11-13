#!/usr/bin/env python3
"""Offline test of a message sent from a tab left open while its stack sleeps (waker.py: is_person_send, replay_allowed, read_body,
Stack.wake_and_hold and the front handler's do_POST). A fake stack and a fake Open WebUI on 127.0.0.1, the real handler.

Checks: which POSTs count as "a person sending" and which stay background (plain 503, no wake); the hold-then-replay path (the wake
starts once, the request waits, then reaches Open WebUI unchanged and its streamed answer streams back); the clear error when the wake
fails or takes too long, when the body never arrived, or when Open WebUI cannot be reached; no replay when Open WebUI already saw the request.

Run from anywhere:  python3 -I ops/wake/idle_tab_selftest.py
"""
import http.client, importlib.util, io, json, os, socket, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("waker", os.path.join(HERE, "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

# ---- classification
H = lambda **k: {key.replace("_", "-"): v for key, v in k.items()}
tok = H(Cookie="a=1; token=abc")
send = w.is_person_send
chk(send("POST", "/api/chat/completions", tok), "POST /api/chat/completions with the token cookie is a send")
chk(send("POST", "/api/chat/completions?x=1", tok), "a query string does not change that")
chk(send("POST", "/api/chat/completions", H(Authorization="Bearer k")), "an Authorization header counts like the cookie")
chk(send("POST", "/api/v1/chats/05833245-69ad-4dd4-a443-cf006ee655a4", tok), "the chat save (typed message) is a send")
chk(send("POST", "/api/v1/chats/new", tok), "a new chat is a send")
chk(not send("POST", "/api/chat/completions", H()), "anonymous: not a person")
chk(not send("POST", "/api/chat/completions", H(Cookie="mytoken=1; other=token=2")), "a cookie merely containing 'token=' is not the token cookie")
chk(not send("GET", "/api/chat/completions", tok), "only POST")
chk(not send("POST", "/api/v1/users/user/settings/update", tok), "settings update from an idle tab stays background")
chk(not send("POST", "/api/v1/auths/update/timezone", tok), "timezone update stays background")
chk(not send("POST", "/api/v1/tasks/tags/completions", tok), "title/tag tasks stay background")
chk(not send("POST", "/api/v1/chats/abc/tags", tok), "deeper chat paths are not the save")
chk(not send("POST", "/api/v1/files/?process=false", tok), "uploads are not held")
chk(not send("POST", "/ws/socket.io/", tok), "websocket traffic is not a send")

# ---- replay guard (never send the same message twice)
ra = w.replay_allowed
chk(ra("502", "asleep") and ra("-", "starting") and ra("", "asleep") and ra("502, 502", "asleep"), "front says Open WebUI was unreachable (502/-): replay")
chk(not ra("503", "ready") and not ra("504", "starting") and not ra("502, 503", "asleep"), "Open WebUI answered 503/504: no replay, it saw the request")
chk(ra(None, "asleep") and ra(None, "starting") and not ra(None, "ready"), "no header (old front): replay only while the stack is not running")

# ---- body reading
rb = w.read_body
chk(rb(io.BytesIO(b"hello world"), {"Content-Length": "5"}) == b"hello", "Content-Length body read exactly")
chk(rb(io.BytesIO(b"hel"), {"Content-Length": "5"}) is None, "body shorter than announced: None")
chk(rb(io.BytesIO(b"x" * 20), {"Content-Length": "20"}, limit=10) is None, "body over the limit: None")
chk(rb(io.BytesIO(b"4\r\nwiki\r\n5\r\npedia\r\n0\r\n\r\n"), {"Transfer-Encoding": "chunked"}) == b"wikipedia", "chunked body decoded")
chk(rb(io.BytesIO(b""), {}) == b"", "no body: empty")

# ---- fake Open WebUI: records what it gets, streams two chunks and waits for the test between them
GOT = []
GATE = threading.Event()
class WebUI(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        GOT.append({"path": self.path, "body": self.rfile.read(n), "cookie": self.headers.get("Cookie"), "host": self.headers.get("Host"),
                    "hint": self.headers.get("X-Wake-Upstream-Status"), "ct": self.headers.get("Content-Type")})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream"); self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
        def chunk(b): self.wfile.write(b"%x\r\n%s\r\n" % (len(b), b)); self.wfile.flush()
        chunk(b"data: one\n\n")
        GATE.wait(10)
        chunk(b"data: two\n\n")
        self.wfile.write(b"0\r\n\r\n")
webui = ThreadingHTTPServer(("127.0.0.1", 0), WebUI); webui.daemon_threads = True
threading.Thread(target=webui.serve_forever, daemon=True).start()
WEB_PORT = webui.server_address[1]

# ---- fake stack: the real wake_and_hold / hold_seconds on top of a scripted wake()
class FakeStack:
    name, lang, web = "t", "ru", ["fake-web"]
    wake_failed = booting = False
    last_activity = 0.0
    hold_seconds = w.Stack.hold_seconds
    wake_and_hold = w.Stack.wake_and_hold
    def __init__(self): self.state, self.wakes, self.script = "asleep", [], "ready"; self.web_health_port = str(WEB_PORT)
    def boot_estimate(self): return 20
    def public_state(self): return self.state
    def wake(self, reason, want_web=False, chat_id=None):
        self.wakes.append((reason, want_web)); self.wake_failed = False
        if self.script == "ready":
            self.booting, self.state = True, "starting"; time.sleep(1.2); self.booting, self.state = False, "ready"
        elif self.script == "fail":
            self.booting = True; time.sleep(0.3); self.booting, self.wake_failed = False, True
        # "never": returns at once and the stack never becomes ready (another boot in flight)
w.ips = lambda name: ["127.0.0.1"]
stack = FakeStack()
front = w.Server(("127.0.0.1", 0), w.make_handler(stack)); threading.Thread(target=front.serve_forever, daemon=True).start()
FRONT = front.server_address[1]

def post(path, body=b'{"messages":[{"role":"user","content":"hi"}]}', headers=None, stream_cb=None):
    c = http.client.HTTPConnection("127.0.0.1", FRONT, timeout=30)
    h = {"Content-Type": "application/json", "Cookie": "token=abc", "X-Wake-Upstream-Status": "502", "Host": "chat.example"}; h.update(headers or {})
    c.request("POST", path, body=body, headers=h)
    r = c.getresponse()
    first = r.read1(100) if stream_cb else None
    if stream_cb: stream_cb()
    data = (first or b"") + r.read()
    c.close()
    return r.status, data, dict(r.getheaders())

def reset(script="ready", state="asleep"):
    stack.state, stack.script, stack.wakes, stack.wake_failed = state, script, [], False
    del GOT[:]; GATE.clear()

# ---- hold then replay, streaming preserved
reset()
t0 = time.time(); seen = {}
def release():
    seen["first_before_second"] = not GATE.is_set(); GATE.set()
code, data, hdr = post("/api/chat/completions?x=1", stream_cb=release)
dt = time.time() - t0
chk(code == 200 and data == b"data: one\n\ndata: two\n\n", f"asleep stack: message held, replayed, answer returned ({code}, {data!r})")
chk(dt >= 1.2, f"the request waited for the wake ({dt:.1f}s)")
chk(stack.wakes == [("web", True)], f"exactly one web wake started: {stack.wakes}")
chk(len(GOT) == 1 and GOT[0]["body"] == b'{"messages":[{"role":"user","content":"hi"}]}' and GOT[0]["path"] == "/api/chat/completions?x=1",
    "Open WebUI got the same path and body, once")
chk(GOT and GOT[0]["cookie"] == "token=abc" and GOT[0]["host"] == "chat.example" and GOT[0]["hint"] is None and GOT[0]["ct"] == "application/json",
    "cookie, Host and content type pass through; the internal hint header does not")
chk(seen.get("first_before_second") and hdr.get("Content-Type") == "text/event-stream", "the first chunk reached the client before the second was produced (streams)")
chk(stack.last_activity > 0, "the stack counts it as activity")

# ---- background / anonymous / already-seen requests: plain 503, no wake
reset()
for what, path, h in (("settings update", "/api/v1/users/user/settings/update", {}), ("anonymous send", "/api/chat/completions", {"Cookie": ""}),
                      ("Open WebUI answered 503", "/api/chat/completions", {"X-Wake-Upstream-Status": "503"})):
    code, data, _ = post(path, headers=h)
    chk(code == 503 and json.loads(data) == {"error": "asleep"} and not stack.wakes and not GOT, f"{what}: plain 503 asleep, nothing woken, nothing sent")

# ---- the wake gives up: a clear error the UI shows, nothing delivered
reset("fail")
code, data, hdr = post("/api/chat/completions")
j = json.loads(data)
chk(code == 503 and j["error"] == "wake_failed" and "Hermes" in j["detail"] and "сообщение" in j["detail"] and not GOT, f"wake failed: 503 with a Russian detail ({j})")
chk(hdr.get("Retry-After"), "and a Retry-After")

# ---- still booting when the hold ends
reset("never")
saved = (w.HOLD_MIN_S, w.HOLD_MAX_S, w.HOLD_EXTRA_S); w.HOLD_MIN_S = w.HOLD_MAX_S = 1
t0 = time.time(); code, data, _ = post("/api/chat/completions"); dt = time.time() - t0
chk(code == 503 and json.loads(data)["error"] == "wake_timeout" and not GOT and 0.9 < dt < 4, f"hold ran out: 503 wake_timeout after {dt:.1f}s, nothing sent")
stack.lang = "en"; code, data, _ = post("/api/chat/completions")
chk("not sent" in json.loads(data)["detail"], "the detail follows the stack's language (en)")
stack.lang = "ru"

# ---- already awake (another boot just finished): replayed with no wait
reset("never", state="ready"); GATE.set()
code, data, _ = post("/api/v1/chats/abc123", headers={"X-Wake-Upstream-Status": "502"})
chk(code == 200 and len(GOT) == 1 and GOT[0]["path"] == "/api/v1/chats/abc123", "stack ready by the time the waker looks (race): replayed at once")

# ---- Open WebUI unreachable right after "ready"
w.HOLD_MIN_S = w.HOLD_MAX_S = 5
reset(); GATE.set(); w.REPLAY_GRACE_S = 1
stack.web_health_port = "1"
code, data, _ = post("/api/chat/completions")
chk(code == 503 and json.loads(data)["error"] == "web_unreachable", "Open WebUI refusing connections after ready: clear error, no hang")
stack.web_health_port = str(WEB_PORT); w.REPLAY_GRACE_S = 15
w.HOLD_MIN_S, w.HOLD_MAX_S, w.HOLD_EXTRA_S = saved

# ---- the body never arrived (the front did not pass it on): error, not a hang
reset(); s = socket.create_connection(("127.0.0.1", FRONT), timeout=10)
s.sendall(b"POST /api/chat/completions HTTP/1.1\r\nHost: x\r\nCookie: token=a\r\nX-Wake-Upstream-Status: 502\r\nContent-Length: 100\r\n\r\nshort")
s.shutdown(socket.SHUT_WR); raw = b""
while True:
    d = s.recv(4096)
    if not d: break
    raw += d
chk(raw.startswith(b"HTTP/1.0 400") and b"body_unavailable" in raw and not stack.wakes, "body shorter than announced: 400, no wake started")

# ---- too big
reset(); code, data, _ = post("/api/chat/completions", headers={"Content-Length": str(w.MAX_HOLD_BODY + 1)}, body=b"")
chk(code in (400, 413) and not stack.wakes, f"oversized body is refused clearly ({code}), not held")

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
