#!/usr/bin/env python3
"""Offline checks for `gateway mosh` against fake mosh hosts (no FFglitch, no ffmpeg). Run: python3 -I gateway_mosh_selftest.py

Covers: only media is sent (a key file named as MOTION or --picture is refused before any network), the option ranges, the
body framing the mosher expects ([picture][motion] with X-Picture-Length), the token, a busy host (429/507) moves to the next
one, a 400 stops at once, nothing configured or nothing answering says "no local fallback", and OUT is written only whole
(an answer that is not an mp4 leaves no OUT and no .part)."""
import contextlib, importlib.util, io, json, os, shutil, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
FAIL = []
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def fake(mode):
    st = {"mode": mode, "posts": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_GET(self):
            self.send_response(200 if self.path == "/healthz" else 404); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")

        def do_POST(self):
            n = int(self.headers["Content-Length"]); body = self.rfile.read(n)
            st["posts"].append({"path": self.path, "auth": self.headers.get("Authorization"), "plen": self.headers.get("X-Picture-Length"), "body": body})
            m = st["mode"]
            data, code = (MP4, 200) if m in ("ok", "short") else (b"<html>not a video</html>", 200) if m == "notmp4" else (b"nope", int(m))
            self.send_response(code); self.send_header("Content-Length", str(len(data) + (4096 if m == "short" else 0)))
            if code == 200:
                self.send_header("X-Mosh-Seconds", "1.5"); self.send_header("X-Mosh-Size", "848x480")
            self.end_headers(); self.wfile.write(data)
            if m == "short":                       # announces 4 KB more than it sends, then drops the connection
                self.close_connection = True

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, st, f"http://127.0.0.1:{srv.server_address[1]}"


cfgp, logp = os.path.join(tmp, "gateways.json"), os.path.join(tmp, "log.jsonl")


def load(hosts):
    json.dump({"mosh": hosts}, open(cfgp, "w"))
    os.environ.update(GATEWAYS_CONFIG=cfgp, GATEWAY_LOG=logp)
    spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def run(m, argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            code = m.cmd_mosh(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


motion = os.path.join(tmp, "motion.mp4"); open(motion, "wb").write(MP4 + b"MOTION")
photo = os.path.join(tmp, "photo.jpg"); open(photo, "wb").write(b"\xff\xd8\xff\xe0" + b"PHOTO" * 4)
keyfile = os.path.join(tmp, "keys.env"); open(keyfile, "wb").write(b"API_KEY=secret\n")
srv_ok, st_ok, url_ok = fake("ok")
srv_busy, st_busy, url_busy = fake("429")
srv_bad, st_bad, url_bad = fake("400")
srv_odd, st_odd, url_odd = fake("notmp4")

# 1. refused before any network
m = load([{"name": "box", "url": url_ok, "token": "tok-1234567890abcdef"}])
for argv, why in (([keyfile, os.path.join(tmp, "o.mp4")], "MOTION must be a video"),
                  ([photo, os.path.join(tmp, "o.mp4")], "MOTION must be a video"),
                  (["--picture", keyfile, motion, os.path.join(tmp, "o.mp4")], "--picture must be a photo"),
                  ([motion, os.path.join(tmp, "o.avi")], "OUT must be a simple path"),
                  ([motion, motion], "same file"),
                  (["--gain", "9", motion, os.path.join(tmp, "o.mp4")], "--gain 0.25 to 4"),
                  (["--height", "1080", motion, os.path.join(tmp, "o.mp4")], "--height an even number"),
                  (["--hold", "x", motion, os.path.join(tmp, "o.mp4")], "--hold is 0 to 10"),
                  (["--color", "red", motion, os.path.join(tmp, "o.mp4")], "usage: gateway mosh"),
                  ([motion], "usage: gateway mosh")):
    code, txt = run(m, argv)
    check(f"refused: {why} ({' '.join(os.path.basename(a) for a in argv)})", (code, why in txt), (2, True))
check("nothing reached the host while refusing", st_ok["posts"], [])

# 2. two files: framing, options, token, output
out = os.path.join(tmp, "two.mp4")
code, txt = run(m, ["--picture", photo, "--gain", "2", "--hold", "0.5", "--mute", motion, out])
p = st_ok["posts"][-1]
q = parse_qs(urlparse(p["path"]).query)
check("two files: done", code, 0)
check("two files: body is picture then motion", p["body"], open(photo, "rb").read() + open(motion, "rb").read())
check("two files: X-Picture-Length is the picture's size", p["plen"], str(os.path.getsize(photo)))
check("two files: options reach the host", (q.get("gain"), q.get("hold"), q.get("audio")), (["2.0"], ["0.5"], ["0"]))
check("token sent as Bearer", p["auth"], "Bearer tok-1234567890abcdef")
check("OUT written", open(out, "rb").read(), MP4)
check("the done line gives the size and the MEDIA hint", ("848x480" in txt, f"MEDIA:{out}" in txt), (True, True))

# 3. one video: no picture bytes, no options sent when none were given
code, txt = run(m, [motion, os.path.join(tmp, "one.mp4")])
p = st_ok["posts"][-1]
check("one video: X-Picture-Length 0 and the body is the motion", (code, p["plen"], p["body"]), (0, "0", open(motion, "rb").read()))
check("one video: no query", urlparse(p["path"]).query, "")

# 4. a busy host moves to the next one
m = load([{"name": "busy", "url": url_busy}, {"name": "box", "url": url_ok}])
n = len(st_ok["posts"])
code, txt = run(m, [motion, os.path.join(tmp, "next.mp4")])
check("busy host skipped, next one used (the done line never names the machine)", (code, len(st_busy["posts"]), len(st_ok["posts"]) - n, "box" in txt), (0, 1, 1, False))

# 5. all busy: exit 5, no retry advice loop
m = load([{"name": "busy", "url": url_busy}])
code, txt = run(m, [motion, os.path.join(tmp, "b.mp4")])
check("all busy: exit 5 and says busy", (code, "mosh: busy" in txt), (5, True))

# 6. 400 stops at once, the next host is not tried
m = load([{"name": "bad", "url": url_bad}, {"name": "box", "url": url_ok}])
n = len(st_ok["posts"])
code, txt = run(m, [motion, os.path.join(tmp, "r.mp4")])
check("400: exit 2, next host not tried", (code, len(st_ok["posts"]) - n), (2, 0))

# 7. an answer that is not an mp4: no OUT, no .part, and an older OUT is kept
old = os.path.join(tmp, "old.mp4"); open(old, "wb").write(b"OLD CONTENT")
m = load([{"name": "odd", "url": url_odd}])
code, txt = run(m, [motion, old])
check("not an mp4: fails", code, 3)
check("not an mp4: the older OUT is kept intact", open(old, "rb").read(), b"OLD CONTENT")
check("no .part left", [f for f in os.listdir(tmp) if ".part" in f], [])

# 8. nothing configured / nothing answers
m = load([])
code, txt = run(m, [motion, os.path.join(tmp, "n.mp4")])
check("no host configured: exit 3, no local fallback", (code, "no local fallback" in txt), (3, True))
m = load([{"name": "gone", "url": "http://127.0.0.1:9"}])
code, txt = run(m, [motion, os.path.join(tmp, "n.mp4")])
check("host down: exit 3", code, 3)
recs = [json.loads(l) for l in open(logp)]
check("log lines carry no file names", any("motion" in json.dumps(r) or "photo" in json.dumps(r) for r in recs), False)
check("log has a mosh line per run", all(r.get("gateway") == "mosh" for r in recs), True)

# 8b. break-and-heal cycle options
m = load([{"name": "box", "url": url_ok}])
n0 = len(st_ok["posts"])
code, txt = run(m, ["--cycle", "3", "--heal", "1", motion, os.path.join(tmp, "c.mp4")])
check("--cycle and --heal reach the host", (code, parse_qs(urlparse(st_ok["posts"][-1]["path"]).query)), (0, {"cycle": ["3.0"], "heal": ["1.0"]}))
code, txt = run(m, ["--once", motion, os.path.join(tmp, "c1.mp4")])
check("--once sends cycle=0", parse_qs(urlparse(st_ok["posts"][-1]["path"]).query).get("cycle"), ["0.0"])
n1 = len(st_ok["posts"])
bad = [["--cycle", "1", motion, os.path.join(tmp, "x.mp4")], ["--cycle", "25", motion, os.path.join(tmp, "x.mp4")],
       ["--heal", "5", motion, os.path.join(tmp, "x.mp4")], ["--cycle", "3", "--picture", photo, motion, os.path.join(tmp, "x.mp4")]]
check("bad cycle/heal values and a cycle with --picture exit 2 and send nothing", ([run(m, a)[0] for a in bad], len(st_ok["posts"]) - n1), ([2, 2, 2, 2], 0))

# 9. review fixes: a cut answer, a job failure, the .loop name
srv_short, st_short, url_short = fake("short")
srv_500, st_500, url_500 = fake("500")
keep = os.path.join(tmp, "keep.mp4"); open(keep, "wb").write(b"OLD CONTENT")
m = load([{"name": "cut", "url": url_short}])
code, txt = run(m, [motion, keep])
check("an answer shorter than its Content-Length is not taken: the older OUT stays", (code, open(keep, "rb").read(), "MEDIA:" in txt), (3, b"OLD CONTENT", False))
m = load([{"name": "box", "url": url_500}])
code, txt = run(m, [motion, os.path.join(tmp, "f.mp4")])
check("a job failure (500) says failed, not off", (code, "mosh: failed" in txt, "mosh: off" in txt), (3, True, False))
m = load([{"name": "box", "url": url_ok}])
code, txt = run(m, [motion, os.path.join(tmp, "x.loop.mp4")])
check("a .loop.mp4 OUT with sound becomes .mp4 (that name means a silent loop to Telegram)", (code, os.path.exists(os.path.join(tmp, "x.mp4")), os.path.exists(os.path.join(tmp, "x.loop.mp4"))), (0, True, False))
code, txt = run(m, ["--mute", motion, os.path.join(tmp, "y.loop.mp4")])
check("with --mute the .loop.mp4 name stays", (code, os.path.exists(os.path.join(tmp, "y.loop.mp4"))), (0, True))

for s in (srv_ok, srv_busy, srv_bad, srv_odd, srv_short, srv_500):
    s.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("all ok" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}")
sys.exit(1 if FAIL else 0)
