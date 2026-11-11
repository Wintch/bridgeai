#!/usr/bin/env python3
"""Offline checks for `gateway enhance` against a fake vidpost host. Run: python3 -I gateway_enhance_selftest.py"""
import contextlib, importlib.util, io, json, os, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"fakeframes" * 30
state = {"mode": "ok", "paths": [], "auth": [], "bodies": [], "ctypes": []}
FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self.send_response(200 if self.path == "/healthz" else 404); self.send_header("Content-Length", "11"); self.end_headers(); self.wfile.write(b"ok vidpost\n")

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        state["bodies"].append(body); state["auth"].append(self.headers.get("Authorization")); state["paths"].append(self.path)
        state["ctypes"].append(self.headers.get("Content-Type"))
        m = state["mode"]
        if m == "ok":
            data, code, ctype = MP4, 200, "video/mp4"
        elif m == "junk":
            data, code, ctype = b"<html>not a video at all</html>", 200, "text/html"
        elif m == "short":
            data, code, ctype = b"ftyp", 200, "video/mp4"
        elif m == "huge":
            data, code, ctype = MP4 + b"\0" * (3 * 1024 * 1024), 200, "video/mp4"
        else:
            data, code, ctype = f"SECRET-FROM-HOST-{m}".encode(), int(m), "text/plain"
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        if code == 200:
            self.send_header("X-Enhance-Seconds", "31.4"); self.send_header("X-Enhance-Size", "1664x960"); self.send_header("X-Enhance-Fps", "48")
        self.end_headers(); self.wfile.write(data)


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}"
cfgp = os.path.join(tmp, "gateways.json")
logp = os.path.join(tmp, "log.jsonl")


def load(hosts):
    json.dump({"vidpost": hosts}, open(cfgp, "w"))
    os.environ.update(GATEWAYS_CONFIG=cfgp, GATEWAY_LOG=logp)
    spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def run(gw, argv):
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = gw.cmd_enhance(argv)
    return rc, buf.getvalue() + err.getvalue()


SRC_BYTES = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"input-clip-bytes-SECRETBODY" * 50
src = os.path.join(tmp, "in.mp4")
open(src, "wb").write(SRC_BYTES)
out = os.path.join(tmp, "in-hd.mp4")
gw = load([{"name": "gpu-a", "url": url, "token": "T0K"}])

rc, txt = run(gw, [src, out])
check("a default call writes the mp4 and says how to send it", (rc, open(out, "rb").read() == MP4, f"MEDIA:{out} on its own line" in txt), (0, True, True))
check("default is both options: scale=2 and fps=2, to /enhance with the Bearer token", (state["paths"][-1], state["auth"][-1]), ("/enhance?scale=2&fps=2", "Bearer T0K"))
check("the body is the input file byte for byte, sent as video/mp4", (state["bodies"][-1] == SRC_BYTES, state["ctypes"][-1]), (True, "video/mp4"))
check("the done line has size, fps, time and KB from numeric headers only", "(1664x960, 48 fps, made in 31.4 s, " in txt, True)
check("the output text does not show the host's words", "SECRET" in txt, False)
check("no .part file is left", os.path.exists(out + ".part"), False)
logtxt = open(logp).read()
check("the log names the verb enhance with bytes and seconds and never a path or the body", ('"enhance"' in logtxt, '"bytes"' in logtxt, '"seconds"' in logtxt, tmp in logtxt, "SECRETBODY" in logtxt, "in.mp4" in logtxt), (True, True, True, False, False, False))

for args, want in ((["--scale", "2", "--fps", "48"], "scale=2&fps=2"), (["--scale", "1", "--fps", "48"], "scale=1&fps=2"), (["--scale", "2", "--fps", "24"], "scale=2&fps=0"),
                   (["--fps", "48"], "scale=2&fps=2"), (["--scale", "1"], "scale=1&fps=2"), (["--scale", "2"], "scale=2&fps=2"), (["--fps", "24"], "scale=2&fps=0")):
    rc, txt = run(gw, args + [src, out])
    check(f"{' '.join(args)} is sent as {want}", (rc, state["paths"][-1]), (0, "/enhance?" + want))
for args, want in ((["--slow"], "scale=2&fps=2&slow=1"), (["--slow", "--scale", "1"], "scale=1&fps=2&slow=1")):
    rc, txt = run(gw, args + [src, out])
    check(f"{' '.join(args)} is sent as {want}", (rc, state["paths"][-1]), (0, "/enhance?" + want))
rc, txt = run(gw, ["--slow", "--fps", "24", src, out])
check("--slow with --fps 24 is refused locally", (rc, "--slow needs" in txt), (2, True))
rc, txt = run(gw, [src, out, "--fps", "24"])
check("options may come after the files too", (rc, state["paths"][-1]), (0, "/enhance?scale=2&fps=0"))

# local refusals: nothing reaches the host
n = len(state["paths"])
rc, txt = run(gw, ["--scale", "1", "--fps", "24", src, out])
check("--scale 1 --fps 24 is refused locally as nothing to do", (rc, "nothing to do" in txt), (2, True))
link = os.path.join(tmp, "link.mp4"); os.symlink(src, link)
dlink = os.path.join(tmp, "dlink.mp4"); os.symlink("/etc/hostname", dlink)
os.makedirs(os.path.join(tmp, "descargas"))
empty = os.path.join(tmp, "empty.mp4"); open(empty, "wb").close()
txtfile = os.path.join(tmp, "secret.txt"); open(txtfile, "w").write("api_key=SHOULD-NEVER-LEAVE" * 10)
partin = os.path.join(tmp, "p.mp4.part"); open(partin, "wb").write(SRC_BYTES)
dirout = os.path.join(tmp, "isdir.mp4"); os.makedirs(dirout)
bad = [["--scale", "3", src, out], ["--scale", "0", src, out], ["--scale", "abc", src, out], ["--scale"], ["--fps", "30", src, out], ["--fps", "60", src, out], ["--fps"],
       ["--evil", "x", src, out], ["--secs", "3", src, out], [src], [src, out, "extra"], [],
       [os.path.join(tmp, "missing.mp4"), out], [tmp, out], [link, out], [empty, out],
       [src, src], [src, os.path.join(tmp, ".", "in.mp4")], [src, dlink],
       [src, "../escape.mp4"], [src, "/etc/passwd"], [src, os.path.join(tmp, "nodir", "x.mp4")], [src, os.path.join(tmp, "a b.mp4")],
       [src, os.path.join(tmp, "x.gif")], [src, os.path.join(tmp, "x.mov")], [src, os.path.join(tmp, "x.mp4.exe")],
       [txtfile, out], [partin, os.path.join(tmp, "p.mp4")], [src, dirout]]
codes = [run(gw, a)[0] for a in bad]
check("bad arguments, input and output paths all exit 2", codes, [2] * len(bad))
check("and nothing was sent to the host", len(state["paths"]), n)
check("a bad argument prints the usage line", "gateway enhance [--scale 1|2] [--fps 24|48] [--slow] IN.mp4 OUT.mp4" in run(gw, ["--scale", "3", src, out])[1], True)
check("the input is untouched after refusing IN == OUT", open(src, "rb").read(), SRC_BYTES)
check("a file in a downloads-style folder is fine", run(gw, [src, os.path.join(tmp, "descargas", "v-hd.mp4")])[0], 0)
big_in = os.path.join(tmp, "big.mp4"); open(big_in, "wb").write(SRC_BYTES)
gw.VIDEO_MAX_BYTES = 1000
check("an input over the 200 MB cap (lowered here) is refused locally", (run(gw, [big_in, out])[0], len(state["paths"])), (2, n + 1))
gw.VIDEO_MAX_BYTES = 200 * 1024 * 1024
n = len(state["paths"])

# host answers
for code, rcwant, needle in ((429, 5, "one at a time"), (503, 5, "graphics card or memory is in use"), (400, 2, "refused this clip"), (401, 3, "operator"),
                             (504, 3, "too slow"), (500, 3, "GPU: off")):
    state["mode"] = str(code)
    if os.path.exists(out): os.unlink(out)
    rc, txt = run(gw, [src, out])
    check(f"host {code} -> exit {rcwant}, fixed sentence, no host text, no file", (rc, needle in txt, "SECRET" in txt, os.path.exists(out), os.path.exists(out + ".part")), (rcwant, True, False, False, False))
state["mode"] = "401"
rc, txt = run(gw, [src, out])
check("a 401 names gateways_sync vidpost_token", "gateways_sync vidpost_token" in txt, True)
for mode in ("junk", "short"):
    state["mode"] = mode
    rc, txt = run(gw, [src, out])
    check(f"a non-mp4 answer ({mode}) is rejected and leaves no file", (rc, os.path.exists(out), os.path.exists(out + ".part"), "MEDIA:" in txt), (3, False, False, False))

# an old OUT is not destroyed by a failed run
open(out, "wb").write(b"OLD")
state["mode"] = "junk"
run(gw, [src, out])
check("a failed run keeps an existing OUT as it was", open(out, "rb").read(), b"OLD")
# a good run replaces it
state["mode"] = "ok"
check("a good run replaces an existing OUT", (run(gw, [src, out])[0], open(out, "rb").read() == MP4), (0, True))
gw.save_prompt_record(src, "video", "waves on a beach", secs="5", seed="77")
run(gw, [src, out]); rec = json.load(open(out + ".prompt.json"))
check("the finished clip keeps the source's prompt record (gateway prompt-of)", (rec["prompt"], rec["seed"], rec["finished"].startswith("scale")), ("waves on a beach", 77, True))
os.unlink(src + ".prompt.json"); run(gw, [src, out])
check("a source with no record removes OUT's older record (it would describe another clip)", os.path.exists(out + ".prompt.json"), False)

# size cap while streaming (lowered here so the test stays small)
state["mode"] = "huge"
gw.ENHANCE_MAX_OUT = 2 * 1024 * 1024
os.unlink(out)
rc, txt = run(gw, [src, out])
check("an answer over the size cap is cut and leaves no file", (rc, os.path.exists(out), os.path.exists(out + ".part")), (3, False, False))
gw.ENHANCE_MAX_OUT = 400 * 1024 * 1024
state["mode"] = "ok"

# per-host timeout: 600 s by default, "timeout" in the host entry overrides it
import urllib.request
seen_to = []
real = urllib.request.urlopen
def spy(req, timeout=None, **kw):
    if not isinstance(req, str) and getattr(req, "method", None) == "POST":
        seen_to.append(timeout)
    return real(req, timeout=timeout, **kw)
urllib.request.urlopen = spy
run(gw, [src, out])
gw2 = load([{"name": "gpu-a", "url": url, "timeout": 1234}])
run(gw2, [src, out])
urllib.request.urlopen = real
check("the wait is 600 s unless the host entry sets timeout", seen_to, [600, 1234])

# second host, no token, none answering
gw = load([{"name": "gpu-down", "url": "http://127.0.0.1:9"}, {"name": "gpu-b", "url": url}])
rc, txt = run(gw, [src, out])
check("hosts are tried in order: the down one is skipped, the next answers, no token means no Authorization", (rc, state["auth"][-1]), (0, None))
gw = load([{"name": "gpu-down", "url": "http://127.0.0.1:9"}])
rc, txt = run(gw, [src, out])
check("no host answering is 'GPU: off' (exit 3), no local fallback", (rc, "GPU: off" in txt, "no local fallback" in txt), (3, True, True))
gw = load([])
check("no host configured is also 'GPU: off'", run(gw, [src, out])[0], 3)
json.dump({"video": [{"name": "x", "url": url}]}, open(cfgp, "w"))
check("a config with only a video (vidgen) host has no vidpost host", run(gw, [src, out])[0], 3)
check("a non-video IN (a key file), IN named OUT.part and an OUT that is a folder are refused locally; the input survives", (os.path.exists(partin), any(b"SHOULD-NEVER-LEAVE" in b for b in state["bodies"])), (True, False))
print("gateway_enhance_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
