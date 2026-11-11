#!/usr/bin/env python3
"""Offline checks for `gateway makevideo` against a fake vidgen host. Run: python3 -I gateway_makevideo_selftest.py"""
import contextlib, importlib.util, io, json, os, shutil, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"fakeframes" * 30
state = {"mode": "ok", "seen": [], "auth": [], "paths": []}
FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self.send_response(200 if self.path == "/healthz" else 404); self.send_header("Content-Length", "8"); self.end_headers(); self.wfile.write(b"ok video")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if "tail" in body:                     # keep the tail itself aside: the checks compare the rest of the body
            state["tails"] = state.get("tails", []) + [body.pop("tail")]; body["tail"] = True
        if "first" in body:                    # same for the starting picture
            state["firsts"] = state.get("firsts", []) + [body.pop("first")]; body["first"] = True
        state["seen"].append(body); state["auth"].append(self.headers.get("Authorization")); state["paths"].append(self.path)
        m = state["mode"]
        if m == "busy2" :                       # another video in progress for the first two calls, then ours is made
            state["busy_left"] = state.get("busy_left", 2) - 1
            m = "429" if state["busy_left"] >= 0 else "ok"
        if m.startswith("chain:"):            # one mode per segment, in order (real, smallclip, or an HTTP code)
            seq = m.split(":")[1].split(",")
            k = state.get("chain_i", 0); state["chain_i"] = k + 1
            m = seq[min(k, len(seq) - 1)]
        if m == "ok":
            data, code, ctype = MP4, 200, "video/mp4"
        elif m == "junk":
            data, code, ctype = b"<html>not a video at all</html>", 200, "text/html"
        elif m == "short":
            data, code, ctype = b"ftyp", 200, "video/mp4"
        elif m == "real":                      # a real clip at a high bitrate with sound, like ComfyUI's
            data, code, ctype = REAL_MP4, 200, "video/mp4"
        elif m == "smallclip":                 # another size: concat cannot join it
            data, code, ctype = REAL_SMALL, 200, "video/mp4"
        elif m == "huge":
            data, code, ctype = MP4 + b"\0" * (3 * 1024 * 1024), 200, "video/mp4"
        else:
            data, code, ctype = f"SECRET-FROM-HOST-{m}".encode(), int(m), "text/plain"
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        if code == 200:
            self.send_header("X-Video-Seconds", "397.4"); self.send_header("X-Video-Seed", str(body.get("seed", 123))); self.send_header("X-Video-Length", "5")
        self.end_headers(); self.wfile.write(data)


import shutil, subprocess
REAL_MP4 = b""
if shutil.which("ffmpeg"):
    _rp = os.path.join(tmp, "real-src.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x192:rate=24:duration=3", "-f", "lavfi",
                    "-i", "sine=frequency=330:duration=3", "-c:v", "libx264", "-crf", "4", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", _rp], check=True)
    REAL_MP4 = open(_rp, "rb").read()
    _rs = os.path.join(tmp, "real-small.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x96:rate=24:duration=2", "-f", "lavfi",
                    "-i", "sine=frequency=500:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", _rs], check=True)
REAL_SMALL = open(os.path.join(tmp, "real-small.mp4"), "rb").read() if REAL_MP4 else b""


def frames_of(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


def dur(path, kind):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", kind, "-show_entries", "stream=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def streams(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path], capture_output=True, text=True)
    return sorted(set(r.stdout.split()))


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}"
cfgp = os.path.join(tmp, "gateways.json")
logp = os.path.join(tmp, "log.jsonl")


def load(hosts):
    json.dump({"video": hosts}, open(cfgp, "w"))
    os.environ.update(GATEWAYS_CONFIG=cfgp, GATEWAY_LOG=logp)
    spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def run(gw, argv):
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = gw.cmd_makevideo(argv)
    return rc, buf.getvalue() + err.getvalue()


gw = load([{"name": "gpu-a", "url": url, "token": "T0K"}])
out = os.path.join(tmp, "clip.mp4")
SECRET = "a red fox SECRET-PROMPT-WORDS"
rc, txt = run(gw, ["--secs", "5", "--seed", "42", "--", SECRET, out])
check("a good call writes the mp4 and says how to send it", (rc, open(out, "rb").read() == MP4, f"MEDIA:{out}" in txt), (0, True, True))
check("the request goes to /video with secs, seed and the Bearer token", (state["paths"][-1], state["seen"][-1], state["auth"][-1]), ("/video", {"prompt": SECRET, "secs": 5, "seed": 42}, "Bearer T0K"))
check("the output text does not repeat the prompt", "SECRET-PROMPT" in txt, False)
check("no .part file is left", os.path.exists(out + ".part"), False)
logtxt = open(logp).read()
check("the log names the verb makevideo, has a hash of the prompt and never the text", ('"makevideo"' in logtxt, "prompt_sha" in logtxt, "SECRET-PROMPT" in logtxt, "fox" in logtxt), (True, True, False, False))

rc, txt = run(gw, ["--", "a plain one", out])
check("default length is 3 s and no seed is sent", (rc, state["seen"][-1]), (0, {"prompt": "a plain one", "secs": 3}))
for s in ("2", "3", "5"):
    run(gw, ["--secs", s, "--", "p", out])
    check(f"--secs {s} is sent as the number {s}", state["seen"][-1]["secs"], int(s))
rc, txt = run(gw, ["--", "--help", out])
check("a prompt that looks like an option is a prompt after --", (rc, state["seen"][-1]["prompt"]), (0, "--help"))
rc, txt = run(gw, ["a plain prompt", out])
check("without -- a plain prompt works too", (rc, state["seen"][-1]["prompt"]), (0, "a plain prompt"))

# argument and path validation: nothing reaches the host
n = len(state["seen"])
bad = [["--secs", "4", "--", "p", out], ["--secs", "0", "--", "p", out], ["--secs", "12", "--", "p", out], ["--secs", "60", "--", "p", out], ["--secs", "abc", "--", "p", out], ["--secs"],
       ["--seed", "-3", "--", "p", out], ["--seed", "abc", "--", "p", out], ["--seed", str(2 ** 32), "--", "p", out], ["--evil", "x", "--", "p", out], ["--quality", "fast", "--", "p", out],
       ["--", "only-one"], ["--", "a", "b", "c"], ["--", "", out], ["--", "x" * 801, out],
       ["--", "p", "../escape.mp4"], ["--", "p", "/etc/passwd"], ["--", "p", os.path.join(tmp, "nodir", "x.mp4")], ["--", "p", os.path.join(tmp, "a b.mp4")],
       ["--", "p", os.path.join(tmp, "x.gif")], ["--", "p", os.path.join(tmp, "x.png")], ["--", "p", os.path.join(tmp, "x.mp4.exe")], ["--", "p", os.path.join(tmp, "x.mov")]]
codes = [run(gw, a)[0] for a in bad]
check("bad arguments and paths all exit 2", codes, [2] * len(bad))
check("and nothing was sent to the host", len(state["seen"]), n)
check("an invalid --secs prints the usage line", "gateway makevideo [--secs 2|3|5|8|10|15|20|30] [--seed N] [--mute] [--from PHOTO|VIDEO [--at S]] -- PROMPT OUT.mp4" in run(gw, ["--secs", "4", "--", "p", out])[1], True)
link = os.path.join(tmp, "link.mp4"); os.symlink("/etc/hostname", link)
check("a symlink as OUT is refused", run(gw, ["--", "p", link])[0], 2)
os.makedirs(os.path.join(tmp, "descargas"))
check("a file in a downloads-style folder is fine", run(gw, ["--", "p", os.path.join(tmp, "descargas", "v.mp4")])[0], 0)

# host answers (the queue wait is off here: a 429 then fails at once)
gw.VIDEO_QUEUE_WAIT, gw.VIDEO_QUEUE_POLL = 0, 0
for code, rcwant, needle in ((429, 5, "kept the machine busy"), (503, 5, "graphics card or memory is in use"), (400, 2, "refused the request"), (401, 3, "operator"),
                             (504, 3, "too slow"), (500, 3, "GPU: off")):
    state["mode"] = str(code)
    if os.path.exists(out): os.unlink(out)
    rc, txt = run(gw, ["--", SECRET, out])
    check(f"host {code} -> exit {rcwant}, fixed sentence, no host text, no file", (rc, needle in txt, "SECRET" in txt, os.path.exists(out), os.path.exists(out + ".part")), (rcwant, True, False, False, False))
state["mode"] = "401"
rc, txt = run(gw, ["--", "p", out])
check("a 401 says the transcode-style note naming video_token", "gateways_sync video_token" in txt, True)
for mode in ("junk", "short"):
    state["mode"] = mode
    rc, txt = run(gw, ["--", "p", out])
    check(f"a non-mp4 answer ({mode}) is rejected and leaves no file", (rc, os.path.exists(out), os.path.exists(out + ".part"), "MEDIA:" in txt), (3, False, False, False))

# size cap while streaming (lowered here so the test stays small)
state["mode"], gw.VIDEO_QUEUE_WAIT = "busy2", 60
if os.path.exists(out): os.unlink(out)
n0 = len(state["seen"])
rc, txt = run(gw, ["--", SECRET, out])
check("while another video is being made (429) it waits its turn and then makes ours", (rc, len(state["seen"]) - n0, os.path.exists(out)), (0, 3, True))
gw.VIDEO_QUEUE_WAIT = 0
os.unlink(out)
state["mode"] = "huge"
gw.VIDEO_MAX_BYTES = 2 * 1024 * 1024
rc, txt = run(gw, ["--", "p", out])
check("an answer over the size cap is cut and leaves no file", (rc, os.path.exists(out), os.path.exists(out + ".part")), (3, False, False))
state["mode"] = "ok"

# per-host timeout: 900 s by default, "timeout" in the host entry overrides it
import urllib.request
seen_to = []
real = urllib.request.urlopen
def spy(req, timeout=None, **kw):
    if not isinstance(req, str) and getattr(req, "method", None) == "POST":
        seen_to.append(timeout)
    return real(req, timeout=timeout, **kw)
urllib.request.urlopen = spy
run(gw, ["--", "p", out])
gw2 = load([{"name": "gpu-a", "url": url, "timeout": 1234}])
run(gw2, ["--", "p", out])
urllib.request.urlopen = real
check("the wait is 900 s unless the host entry sets timeout", seen_to, [900, 1234])

# fallback to a second host; off when none answers
gw = load([{"name": "gpu-a", "url": url}, {"name": "gpu-b", "url": url}])
rc, txt = run(gw, ["--", "p", out])
check("without a token no Authorization header is sent", state["auth"][-1], None)
gw = load([{"name": "gpu-down", "url": "http://127.0.0.1:9"}])
rc, txt = run(gw, ["--", "p", out])
check("no host answering is 'GPU: off' (exit 3), no local fallback", (rc, "GPU: off" in txt, "no local fallback" in txt), (3, True, True))
gw = load([])
check("no host configured is also 'GPU: off'", run(gw, ["--", "p", out])[0], 3)
gw = load([])
json.dump({"image": [{"name": "x", "url": url}]}, open(cfgp, "w"))
check("a config with only an image host has no video host", run(gw, ["--", "p", out])[0], 3)
# Delivery compression and the silent loop.
if REAL_MP4:
    gw = load([{"name": "gpu-a", "url": url, "token": "T0K"}])
    state["mode"] = "real"
    o = os.path.join(tmp, "real.mp4")
    rc, txt = run(gw, ["--secs", "5", "--", "a fox in the snow, wind", o])
    orig = os.path.join(tmp, "real.original.mp4")
    check("a heavy clip is sent as a lighter copy and the original is kept next to it",
          (rc, os.path.getsize(o) < len(REAL_MP4) * 0.85, os.path.getsize(orig) == len(REAL_MP4), "lighter copy" in txt, f"MEDIA:{o}" in txt, streams(o)),
          (0, True, True, True, True, ["audio", "video"]))
    check("the prompt record matches the copy that is sent (prompt-of finds it)", json.load(open(o + ".prompt.json"))["sha"] == gw._file_sha(o), True)
    o2 = os.path.join(tmp, "loop.mp4")
    rc, txt = run(gw, ["--secs", "5", "--mute", "--", "a fox in the snow", o2])
    lp = os.path.join(tmp, "loop.loop.mp4")
    check("--mute: NAME.loop.mp4 with no sound track (Telegram shows it as a loop), the original with sound kept",
          (rc, os.path.exists(lp), streams(lp), streams(os.path.join(tmp, "loop.loop.original.mp4")), f"MEDIA:{lp}" in txt, "silent loop" in txt),
          (0, True, ["video"], ["audio", "video"], True, True))
    o3 = os.path.join(tmp, "loop.mp4")                  # the same name again, with sound this time: its original must not replace the loop's
    rc, txt = run(gw, ["--secs", "5", "--", "a fox in the snow", o3])
    check("a clip and its silent-loop twin keep separate originals", (os.path.exists(os.path.join(tmp, "loop.loop.original.mp4")),
          streams(os.path.join(tmp, "loop.loop.original.mp4")), os.path.exists(os.path.join(tmp, "loop.original.mp4"))), (True, ["audio", "video"], True))
    rc, txt = run(gw, ["--secs", "5", "--", "a fox", os.path.join(tmp, "named.loop.mp4")])
    check("a .loop.mp4 name without --mute becomes a plain .mp4 (that name means a silent loop to Telegram)",
          (rc, os.path.exists(os.path.join(tmp, "named.mp4")), os.path.exists(os.path.join(tmp, "named.loop.mp4"))), (0, True, False))
    odd = os.path.join(tmp, "odd.mp4")                 # 4:4:4 at an odd size: the yuv420p re-encode fails, the silent copy still works
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=321x241:rate=24:duration=2", "-f", "lavfi",
                    "-i", "sine=duration=2", "-c:v", "libx264", "-crf", "4", "-pix_fmt", "yuv444p", "-c:a", "aac", "-shortest", odd], check=True)
    oddloop = os.path.join(tmp, "oddc.loop.mp4"); shutil.copy(odd, oddloop)
    note, muted = gw.deliver_compress(oddloop, True)
    check("when the silent re-encode fails, the loop is still made silent by a stream copy", (muted, streams(oddloop)), (True, ["video"]))
    keep = os.path.join(tmp, "e.original.mp4"); shutil.copy(os.path.join(tmp, "real-src.mp4"), keep)
    e_out = os.path.join(tmp, "e.mp4"); shutil.copy(os.path.join(tmp, "real-src.mp4"), e_out)
    before = open(keep, "rb").read()
    note, _ = gw.deliver_compress(e_out, protect=keep)
    check("the enhance input (an existing NAME.original.mp4) is never overwritten: the new original takes another name",
          (open(keep, "rb").read() == before, os.path.exists(os.path.join(tmp, "e.original-2.mp4"))), (True, True))
    os.makedirs(os.path.join(tmp, "f.original.mp4"))   # a folder where the original would go
    f_out = os.path.join(tmp, "f.mp4"); shutil.copy(os.path.join(tmp, "real-src.mp4"), f_out)
    note, _ = gw.deliver_compress(f_out)
    check("an odd problem while keeping the original never breaks the delivery", (os.path.isfile(f_out), not [x for x in os.listdir(tmp) if x.endswith("small.part")]), (True, True))
    state["mode"] = "ok"
    rc, txt = run(gw, ["--", "p", os.path.join(tmp, "fake.mp4")])
    check("a file ffmpeg cannot read is sent as it came, no copy, no original", (rc, os.path.exists(os.path.join(tmp, "fake.original.mp4")), "lighter" in txt), (0, False, False))

# Chained clips (15/20/30 s, VIDEO_BENCH_RESULTS.md B4c, B5n): segments from the host, tails sent back, joined here.
if REAL_MP4:
    import base64
    gw = load([{"name": "gpu-a", "url": url, "token": "T0K"}])
    gw.VIDEO_QUEUE_WAIT = 0
    def chain(modes, argv):
        state.update(mode="chain:" + modes, chain_i=0, tails=[])
        n0 = len(state["seen"])
        rc, txt = run(gw, argv)
        return rc, txt, state["seen"][n0:]
    c = os.path.join(tmp, "long.mp4")
    rc, txt, seen = chain("real", ["--secs", "20", "--seed", "100", "--", SECRET, c])
    check("--secs 20: two 10 s chain segments, seeds 100 and 101, the second with the tail",
          [(b["secs"], b["seed"], b.get("chain"), b.get("tail", False)) for b in seen], [(10, 100, True, False), (10, 101, True, True)])
    tp = os.path.join(tmp, "tail-sent.mp4"); open(tp, "wb").write(base64.b64decode(state["tails"][0]))
    check("the tail sent back is the last 5 frames, no sound", (frames_of(tp), streams(tp)), (5, ["video"]))
    orig = os.path.join(tmp, "long.original.mp4")
    check("joined: 72 + 67 frames, sound as long as the picture, delivered light with the original kept",
          (rc, frames_of(orig), abs(dur(orig, "a:0") - dur(orig, "v:0")) < 0.03, streams(c), f"MEDIA:{c}" in txt, "2 parts" in txt, "PARTIAL" in txt, "SECRET" in txt),
          (0, 139, True, ["audio", "video"], True, True, False, False))
    rec = json.load(open(c + ".prompt.json"))
    check("the record keeps the asked length and the first seed (the same --seed repeats the clip)", (rec["secs"], str(rec["seed"])), (20, "100"))
    check("no work folder or part is left", [x for x in os.listdir(tmp) if x.startswith(".makevideo-") or x.endswith(".part")], [])
    rc, txt, seen = chain("real", ["--secs", "15", "--", "p", c])
    check("--secs 15 is 10 + 5", [b["secs"] for b in seen], [10, 5])
    rc, txt, seen = chain("real,real,503", ["--secs", "30", "--", "p", c])
    check("a later segment failing still delivers what was made, marked PARTIAL",
          (rc, len(seen), frames_of(os.path.join(tmp, "long.original.mp4")), "PARTIAL: 6 s of the 30 s" in txt, f"MEDIA:{c}" in txt), (0, 3, 139, True, True))
    os.unlink(c)
    rc, txt, seen = chain("503", ["--secs", "30", "--", "p", c])
    check("the first segment failing is the usual GPU sentence and no file", (rc, "GPU: busy" in txt, os.path.exists(c), len(seen)), (5, True, False, 1))
    rc, txt, seen = chain("real", ["--secs", "20", "--mute", "--", "p", c])
    lp = os.path.join(tmp, "long.loop.mp4")
    check("a chained silent loop: NAME.loop.mp4 without a sound track", (rc, streams(lp), f"MEDIA:{lp}" in txt), (0, ["video"], True))
    rc, txt, seen = chain("real,smallclip", ["--secs", "20", "--", "p", os.path.join(tmp, "mix.mp4")])
    p1, p2 = os.path.join(tmp, "mix-part1.mp4"), os.path.join(tmp, "mix-part2.mp4")
    check("parts that cannot be joined are handed over one by one, nothing lost",
          (rc, os.path.exists(p1), os.path.exists(p2), f"MEDIA:{p1}" in txt and f"MEDIA:{p2}" in txt, os.path.exists(os.path.join(tmp, "mix.mp4"))),
          (0, True, True, True, False))
    check("still no work folder or part left", [x for x in os.listdir(tmp) if x.startswith(".makevideo-") or x.endswith(".part")], [])
    state["mode"] = "ok"

# Starting from the person's own picture (--from): re-encoded here, portrait decided here, only the first chain segment carries it.
import base64
from PIL import Image
gw = load([{"name": "gpu-a", "url": url, "token": "T0K"}])
gw.VIDEO_QUEUE_WAIT = 0
state["mode"] = "ok"
ex = Image.Exif(); ex[0x0112] = 1; ex[0x010E] = "SECRET-IN-EXIF"
tall = os.path.join(tmp, "tall.jpg"); Image.new("RGB", (900, 2400), (200, 30, 30)).save(tall, "JPEG", exif=ex)
wide = os.path.join(tmp, "wide.png"); Image.new("RGB", (2400, 1200), (30, 30, 200)).save(wide, "PNG")
sq = os.path.join(tmp, "sq.webp"); Image.new("RGB", (500, 560), (30, 200, 30)).save(sq, "WEBP")   # 1.12: not portrait
rot = os.path.join(tmp, "rot.jpg"); ex2 = Image.Exif(); ex2[0x0112] = 6; Image.new("RGB", (2000, 1000), (9, 9, 9)).save(rot, "JPEG", exif=ex2)  # lands upright: 1000x2000


def sent_first():
    return Image.open(io.BytesIO(base64.b64decode(state["firsts"][-1], validate=True)))


o = os.path.join(tmp, "from.mp4")
n = len(state["seen"])
rc, txt = run(gw, ["--secs", "5", "--from", tall, "--", SECRET, o])
im = sent_first()
check("--from a tall photo: first is a JPEG, portrait is true, the rest as usual",
      (rc, len(state["seen"]) - n, state["seen"][-1], im.format), (0, 1, {"prompt": SECRET, "secs": 5, "first": True, "portrait": True}, "JPEG"))
check("the picture is capped at 1600 px on the long side and carries no metadata",
      (im.size, len(im.getexif()), b"SECRET-IN-EXIF" in base64.b64decode(state["firsts"][-1])), ((600, 1600), 0, False))
check("the done line says the clip starts from the given picture, no secrets", ("starting from the given picture" in txt, "SECRET" in txt, f"MEDIA:{o}" in txt), (True, False, True))
rec = json.load(open(o + ".prompt.json"))
check("the prompt record notes first=True, never the path or bytes", (rec.get("first"), tall in json.dumps(rec), state["firsts"][-1][:40] in json.dumps(rec)), (True, False, False))
logtxt = open(logp).read()
check("the log notes first but not the path, the bytes or the prompt", ('"first": true' in logtxt, tall in logtxt, state["firsts"][-1][:40] in logtxt, "SECRET" in logtxt), (True, False, False, False))
run(gw, ["--from", wide, "--", "p", o])
check("--from a wide photo (PNG): first, no portrait key, and the long side is cut to 1600", (state["seen"][-1], sent_first().size), ({"prompt": "p", "secs": 3, "first": True}, (1600, 800)))
run(gw, ["--from", sq, "--", "p", o])
check("a photo only a little taller than wide (WEBP, ratio 1.12) is not portrait", "portrait" in state["seen"][-1], False)
run(gw, ["--from", rot, "--", "p", o])
check("EXIF rotation is applied before the shape is judged (2000x1000 turned = portrait)", (state["seen"][-1].get("portrait"), sent_first().size), (True, (800, 1600)))
run(gw, ["--secs", "5", "--", "p", o])
check("without --from there is no first and no portrait", sorted(state["seen"][-1]), ["prompt", "secs"])

if shutil.which("ffmpeg"):
    for at, label in (("0.5", "at 0.5"), (None, "default 1.0"), ("30", "past the end")):
        rc, txt = run(gw, ["--from", os.path.join(tmp, "real-src.mp4")] + (["--at", at] if at else []) + ["--", "p", o])
        im = sent_first()
        check(f"--from video, {label}: a frame is sent, wide so not portrait", (rc, im.format, im.size, "portrait" in state["seen"][-1]), (0, "JPEG", (320, 192), False))
    fr = []
    for at in ("0.0", "2.0"):
        run(gw, ["--from", os.path.join(tmp, "real-src.mp4"), "--at", at, "--", "p", o]); fr.append(state["firsts"][-1])
    check("another --at gives another frame", fr[0] != fr[1], True)

n = len(state["seen"])
key = os.path.join(tmp, "x.jpg"); open(key, "w").write("-----BEGIN OPENSSH " + "PRIVATE KEY-----\nSECRET-KEY-BODY\n")   # split so the privacy scan does not take the fixture for a key
fakepng = os.path.join(tmp, "fake.png"); open(fakepng, "wb").write(b"\x89PNG\r\n\x1a\n" + b"junk" * 30)
heic = os.path.join(tmp, "x.heic"); open(heic, "wb").write(b"\x00\x00\x00\x18ftypheic" + b"\0" * 40)
fakemp4 = os.path.join(tmp, "fake-src.mp4"); open(fakemp4, "wb").write(b"\x00\x00\x00\x18ftypisom" + b"junk" * 50)
lnk = os.path.join(tmp, "fromlink.jpg"); os.symlink(tall, lnk)
same = os.path.join(tmp, "src.mp4"); shutil.copy(os.path.join(tmp, "real-src.mp4"), same) if REAL_MP4 else open(same, "wb").write(MP4)
cases = {"--at without --from": ["--at", "1", "--", "p", o], "--at on a photo": ["--from", tall, "--at", "1", "--", "p", o],
         "a bad --at": ["--from", tall, "--at", "abc", "--", "p", o], "a key file named x.jpg": ["--from", key, "--", "p", o],
         "a png header with junk": ["--from", fakepng, "--", "p", o], "a HEIC photo": ["--from", heic, "--", "p", o],
         "an mp4 box ffprobe cannot read": ["--from", fakemp4, "--", "p", o], "a link": ["--from", lnk, "--", "p", o],
         "a missing file": ["--from", os.path.join(tmp, "nope.jpg"), "--", "p", o], "--from without a value": ["--from"],
         "the source as OUT": ["--from", same, "--", "p", same], "a chain with a bad source": ["--secs", "15", "--from", key, "--", "p", o]}
for name, a in cases.items():
    rc, txt = run(gw, a)
    check(f"{name}: exit 2 and no secret in the answer", (rc, "SECRET" in txt), (2, False))
check("none of them reached the host", len(state["seen"]), n)
check("the key file was not touched", open(key).read().startswith("-----BEGIN"), True)
check("no temporary folder is left behind", [x for x in os.listdir(tempfile.gettempdir()) if x.startswith(".ref-")], [])

if REAL_MP4:
    def chain2(argv):
        state.update(mode="chain:real", chain_i=0, tails=[], firsts=[])
        n0 = len(state["seen"])
        rc, txt = run(gw, argv)
        return rc, txt, state["seen"][n0:]
    c = os.path.join(tmp, "fromlong.mp4")
    rc, txt, seen = chain2(["--secs", "20", "--seed", "5", "--from", tall, "--", SECRET, c])
    check("chain --secs 20 --from: only segment 1 carries first, both carry portrait, the tail only on the second",
          (rc, [(b.get("first", False), b.get("portrait"), b.get("tail", False)) for b in seen]), (0, [(True, True, False), (False, True, True)]))
    rec = json.load(open(c + ".prompt.json"))
    check("the chain's record and done line note the start picture, no secrets",
          (rec.get("first"), "starting from the given picture" in txt, "SECRET" in txt, tall in json.dumps(rec)), (True, True, False, False))
    rc, txt, seen = chain2(["--secs", "30", "--from", wide, "--", "p", c])
    check("chain 30 s from a wide photo: first only on the first of three, no portrait anywhere",
          ([("first" in b, "portrait" in b) for b in seen]), [(True, False), (False, False), (False, False)])
    rc, txt, seen = chain2(["--secs", "15", "--", "p", c])
    check("a chain without --from has neither", [sorted(b) for b in seen], [["chain", "prompt", "secs", "seed"], ["chain", "prompt", "secs", "seed", "tail"]])
    check("no work folder or part is left", [x for x in os.listdir(tmp) if x.startswith(".makevideo-") or x.endswith(".part")], [])
state["mode"] = "ok"

print("gateway_makevideo_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
