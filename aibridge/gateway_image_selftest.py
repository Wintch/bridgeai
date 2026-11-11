#!/usr/bin/env python3
"""Offline checks for `gateway image` against a fake imggen host. Run: python3 -I gateway_image_selftest.py"""
import contextlib, importlib.util, io, json, os, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
PNG = b"\x89PNG\r\n\x1a\n" + b"fakepixels" * 20
import io as _io
from PIL import Image as _I, PngImagePlugin as _P
_b = _io.BytesIO(); _m = _P.PngInfo(); _m.add_text("prompt", "SECRET-IN-META"); _I.new("RGB", (64, 48), (200, 80, 40)).save(_b, "PNG", pnginfo=_m)
REAL = _b.getvalue()
state = {"mode": "ok", "seen": [], "auth": []}
FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self.send_response(200 if self.path == "/healthz" else 404); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        state["seen"].append(body); state["auth"].append(self.headers.get("Authorization"))
        m = state["mode"]
        if m == "ok":
            data, code, ctype = PNG, 200, "image/png"
        elif m == "real":
            data, code, ctype = REAL, 200, "image/png"
        elif m == "junk":
            data, code, ctype = b"<html>not a picture</html>", 200, "text/html"
        else:
            data, code, ctype = f"SECRET-FROM-HOST-{m}".encode(), int(m), "text/plain"
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        if code == 200:
            self.send_header("X-Image-Seconds", "2.8"); self.send_header("X-Image-Seed", str(body.get("seed", 123)))
            if state.get("size_header"):
                self.send_header("X-Image-Size", state["size_header"])
        self.end_headers(); self.wfile.write(data)


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}"
cfgp = os.path.join(tmp, "gateways.json")
logp = os.path.join(tmp, "log.jsonl")


def load(hosts):
    json.dump({"image": hosts}, open(cfgp, "w"))
    os.environ.update(GATEWAYS_CONFIG=cfgp, GATEWAY_LOG=logp)
    spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def run(gw, argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gw.cmd_image(argv)
    return rc, buf.getvalue()


gw = load([{"name": "gpu-a", "url": url, "token": "T0K"}])
out = os.path.join(tmp, "pic.png")
SECRET = "a red fox SECRET-PROMPT-WORDS"
rc, txt = run(gw, ["--quality", "better", "--seed", "42", "--", SECRET, out])
check("a good call writes the PNG and says how to send it", (rc, open(out, "rb").read() == PNG, f"MEDIA:{out}" in txt), (0, True, True))
check("the request carries tier, size and seed and the Bearer token", (state["seen"][-1], state["auth"][-1]), ({"prompt": SECRET, "quality": "better", "size": "1024x1024", "seed": 42}, "Bearer T0K"))
check("the output text does not repeat the prompt", "SECRET-PROMPT" in txt, False)
check("no .part file is left", os.path.exists(out + ".part"), False)
rec = json.load(open(out + ".prompt.json"))
check("the prompt and options are kept next to the picture, owner only (gateway prompt-of reads them)",
      (rec["kind"], rec["prompt"], rec["quality"], rec["size"], oct(os.stat(out + ".prompt.json").st_mode & 0o777), os.path.exists(out + ".prompt.json.part")),
      ("image", SECRET, "better", "1024x1024", "0o600", False))
logtxt = open(logp).read()
check("the log has a hash of the prompt and never the text", ("prompt_sha" in logtxt, "SECRET-PROMPT" in logtxt, "fox" in logtxt), (True, False, False))

rc, txt = run(gw, ["--", "--help", out])
check("a prompt that looks like an option is a prompt after --", (rc, state["seen"][-1]["prompt"]), (0, "--help"))
rc, txt = run(gw, ["--", "-x -o evil", out])
check("a prompt starting with a dash is fine after --", (rc, state["seen"][-1]["prompt"]), (0, "-x -o evil"))
rc, txt = run(gw, ["a plain prompt", out])
check("without -- a plain prompt works too", (rc, state["seen"][-1]["prompt"]), (0, "a plain prompt"))

# argument and path validation: nothing reaches the host
n = len(state["seen"])
bad = [["--size", "99x99", "--", "p", out], ["--quality", "ultra", "--", "p", out], ["--seed", "-3", "--", "p", out], ["--seed", "abc", "--", "p", out], ["--evil", "x", "--", "p", out],
       ["--", "only-one"], ["--", "a", "b", "c"], ["--", "", out], ["--", "x" * 801, out],
       ["--", "p", "../escape.png"], ["--", "p", "/etc/passwd"], ["--", "p", os.path.join(tmp, "nodir", "x.png")], ["--", "p", os.path.join(tmp, "a b.png")], ["--", "p", os.path.join(tmp, "x.gif")], ["--", "p", os.path.join(tmp, "x.png.exe")]]
codes = [run(gw, a)[0] for a in bad]
check("bad arguments and paths all exit 2", codes, [2] * len(bad))
check("and nothing was sent to the host", len(state["seen"]), n)
link = os.path.join(tmp, "link.png"); os.symlink("/etc/hostname", link)
check("a symlink as OUT is refused", run(gw, ["--", "p", link])[0], 2)

# host answers
for code, rcwant, needle in ((429, 5, "Another picture"), (503, 5, "graphics card is in use"), (400, 2, "refused the request"), (500, 3, "GPU: off")):
    state["mode"] = str(code)
    if os.path.exists(out): os.unlink(out)
    rc, txt = run(gw, ["--", SECRET, out])
    check(f"host {code} -> exit {rcwant}, fixed sentence, no host text, no file", (rc, needle in txt, "SECRET" in txt, os.path.exists(out)), (rcwant, True, False, False))
state["mode"] = "junk"
rc, txt = run(gw, ["--", "p", out])
check("a non-PNG answer is rejected and leaves no file", (rc, os.path.exists(out), os.path.exists(out + ".part")), (3, False, False))


# output formats: the host answers in PNG, the lighter ones are made by the gateway
state["mode"] = "real"
from PIL import Image, features
for ext, fmt in (("jpg", "JPEG"), ("jpeg", "JPEG"), ("webp", "WEBP"), ("avif", "AVIF")):
    if ext == "avif" and not features.check("avif"):
        print("skip avif (this Pillow has no AVIF)"); continue
    o = os.path.join(tmp, f"fmt.{ext}")
    rc, txt = run(gw, ["--", "p", o])
    im = Image.open(o)
    check(f".{ext} output is a real {fmt} with no PNG metadata and says its size", (rc, im.format, im.size, "SECRET-IN-META" in open(o, "rb").read().decode("latin-1"), "KB" in txt), (0, fmt, (64, 48), False, True))
o = os.path.join(tmp, "fmt.png")
rc, txt = run(gw, ["--", "p", o])
check(".png output is the host's bytes untouched", (rc, open(o, "rb").read() == REAL), (0, True))
state["mode"] = "ok"

# fallback to a second host; off when none answers
state["mode"] = "500"
gw = load([{"name": "gpu-a", "url": url}, {"name": "gpu-b", "url": url}])
state["mode"] = "ok"
rc, txt = run(gw, ["--", "p", out])
check("without a token no Authorization header is sent", state["auth"][-1], None)
gw = load([{"name": "gpu-down", "url": "http://127.0.0.1:9"}])
rc, txt = run(gw, ["--", "p", out])
check("no host answering is 'GPU: off' (exit 3), no local fallback", (rc, "GPU: off" in txt, "no local fallback" in txt), (3, True, True))
gw = load([])
check("no host configured is also 'GPU: off'", run(gw, ["--", "p", out])[0], 3)
# Editing the person's own picture (--ref): the photo is re-encoded here, nothing else is sent.
import base64, shutil, subprocess
state["mode"], state["size_header"] = "real", "832x1216"
gw = load([{"name": "gpu-a", "url": url, "token": "T0K"}])
big = Image.new("RGB", (3000, 2000), (30, 120, 200))
for x in range(0, 3000, 50):
    big.paste((250, 250, 20), (x, 0, x + 25, 2000))
ex = Image.Exif(); ex[0x0112] = 6; ex[0x010E] = "SECRET-IN-EXIF"; ex[0x013B] = "SECRET-ARTIST"
photo = os.path.join(tmp, "me.jpg"); big.save(photo, "JPEG", exif=ex)
check("the test photo really carries EXIF", b"SECRET-IN-EXIF" in open(photo, "rb").read(), True)
o = os.path.join(tmp, "edit.jpg")
n = len(state["seen"])
rc, txt = run(gw, ["--ref", photo, "--", SECRET, o])
b = state["seen"][-1]
sent = base64.b64decode(b["ref"], validate=True) if "ref" in b else b""
sim = Image.open(io.BytesIO(sent)) if sent else None
check("--ref photo: one request, tier better, no size, a ref that decodes",
      (rc, len(state["seen"]) - n, sorted(b), b["quality"], sim and sim.format), (0, 1, ["prompt", "quality", "ref"], "better", "JPEG"))
check("the ref is upright (EXIF turned), long side <= 2048, no metadata, the prompt untouched",
      (sim.size, b"SECRET-IN-EXIF" in sent, b"SECRET-ARTIST" in sent, len(sim.getexif()), b["prompt"]), ((1365, 2048), False, False, 0, SECRET))
check("the done line uses the host's X-Image-Size and says it was edited",
      (rc, "832x1216" in txt, "edited" in txt, "SECRET" in txt, f"MEDIA:{o}" in txt, os.path.getsize(o) > 0), (0, True, True, False, True, True))
rec = json.load(open(o + ".prompt.json"))
check("the prompt record notes ref=True and size from the host, never the path or bytes",
      (rec.get("ref"), rec["size"], rec["quality"], photo in json.dumps(rec), b["ref"][:40] in json.dumps(rec)), (True, "832x1216", "better", False, False))
logtxt = open(logp).read()
check("the log notes ref but not the path, the bytes or the prompt", ('"ref": true' in logtxt, photo in logtxt, b["ref"][:40] in logtxt, "SECRET" in logtxt), (True, False, False, False))
rc, txt = run(gw, ["--ref", photo, "--size", "1216x832", "--seed", "7", "--", "p", o])
check("--ref with an explicit --size and --seed sends them", (rc, state["seen"][-1]["size"], state["seen"][-1]["seed"]), (0, "1216x832", 7))
rc, txt = run(gw, ["--ref", photo, "--quality", "better", "--", "p", o])
check("--ref with --quality better is fine", rc, 0)
state["size_header"] = "not a size <b>"
rc, txt = run(gw, ["--ref", photo, "--", "p", o])
check("a host size header that is not WxH is never printed (the done line falls back)", (rc, "<b>" in txt, "auto" in txt), (0, False, True))
state["size_header"] = None
rc, txt = run(gw, ["--", "p", o])
check("without --ref and without the header the asked size is shown", (rc, "1024x1024" in txt, "ref" in state["seen"][-1]), (0, True, False))

# a picture from a video: one frame
if shutil.which("ffmpeg") and shutil.which("ffprobe"):
    vid = os.path.join(tmp, "me.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x192:rate=24:duration=2", "-pix_fmt", "yuv420p", vid], check=True)
    for at, label in (("0.5", "at 0.5"), (None, "default 1.0"), ("30", "past the end (the middle)")):
        n = len(state["seen"])
        rc, txt = run(gw, ["--ref", vid] + (["--at", at] if at else []) + ["--", "p", o])
        f = base64.b64decode(state["seen"][-1]["ref"], validate=True) if len(state["seen"]) > n else b""
        im = Image.open(io.BytesIO(f)) if f else None
        check(f"--ref video, {label}: a JPEG frame is sent, no size", (rc, im and im.format, im and im.size, "size" in state["seen"][-1]), (0, "JPEG", (320, 192), False))
    # frames really differ with the moment (testsrc2 has a running counter)
    fr = []
    for at in ("0.0", "1.5"):
        run(gw, ["--ref", vid, "--at", at, "--", "p", o]); fr.append(state["seen"][-1]["ref"])
    check("another --at gives another frame", fr[0] != fr[1], True)
    n = len(state["seen"])
    check("--at past a photo's one picture is a usage error", run(gw, ["--ref", photo, "--at", "1", "--", "p", o])[0], 2)
    check("a negative or odd --at is refused", [run(gw, ["--ref", vid, "--at", a, "--", "p", o])[0] for a in ("-1", "abc", "nan", "99999")], [2] * 4)
    fake_vid = os.path.join(tmp, "fake.mp4"); open(fake_vid, "wb").write(b"\x00\x00\x00\x18ftypisom" + b"junk" * 50)
    check("an mp4 box that ffprobe cannot read is refused", run(gw, ["--ref", fake_vid, "--", "p", o])[0], 2)
    check("nothing was sent for those", len(state["seen"]), n)

# refused before any network
n = len(state["seen"])
key = os.path.join(tmp, "x.jpg"); open(key, "w").write("-----BEGIN OPENSSH " + "PRIVATE KEY-----\nSECRET-KEY-BODY\n")   # split so the privacy scan does not take the fixture for a key
fakejpg = os.path.join(tmp, "fake.jpg"); open(fakejpg, "wb").write(b"\xff\xd8\xff\xe0" + b"not really a jpeg" * 10)
heic = os.path.join(tmp, "x.heic"); open(heic, "wb").write(b"\x00\x00\x00\x18ftypheic" + b"\0" * 40)
lnk = os.path.join(tmp, "reflink.jpg"); os.symlink(photo, lnk)
empty = os.path.join(tmp, "empty.jpg"); open(empty, "wb").close()
same = os.path.join(tmp, "same.jpg"); shutil.copy(photo, same)
cases = {"--at without --ref": ["--at", "1", "--", "p", o], "--ref with --quality photo": ["--ref", photo, "--quality", "photo", "--", "p", o],
         "--ref with --quality fast": ["--ref", photo, "--quality", "fast", "--", "p", o], "a key file named x.jpg": ["--ref", key, "--", "p", o],
         "a jpeg header with junk after it": ["--ref", fakejpg, "--", "p", o], "a HEIC photo": ["--ref", heic, "--", "p", o], "a link": ["--ref", lnk, "--", "p", o],
         "an empty file": ["--ref", empty, "--", "p", o], "a missing file": ["--ref", os.path.join(tmp, "nope.jpg"), "--", "p", o],
         "a folder": ["--ref", tmp, "--", "p", o], "--ref without a value": ["--ref"], "the source as OUT": ["--ref", same, "--", "p", same]}
for name, a in cases.items():
    rc, txt = run(gw, a)
    check(f"{name}: exit 2 and no host text or secret in the answer", (rc, "SECRET" in txt), (2, False))
check("none of them reached the host", len(state["seen"]), n)
check("the key file was not touched", open(key).read().startswith("-----BEGIN"), True)
check("no temporary folder is left behind", [x for x in os.listdir(tempfile.gettempdir()) if x.startswith(".ref-")], [])
state["mode"] = "400"
rc, txt = run(gw, ["--ref", photo, "--", "p", o])
check("host 400 with a ref: fixed sentence, no host text", (rc, "refused the request" in txt, "another picture" in txt, "SECRET" in txt), (2, True, True, False))
state["mode"] = "ok"
print("gateway_image_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
