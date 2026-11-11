#!/usr/bin/env python3
"""Test of gpu-host/mosher/server.py with the real FFglitch tools (no network beyond loopback). Needs ffmpeg, ffprobe and
ffgac/ffedit in $FFGLITCH (default /opt/ffglitch); skipped without them, so the repo's pre-push run passes on a machine
that has no FFglitch. Inside the image: docker run --rm -v $PWD/gpu-host/mosher:/t:ro mosher:latest python3 -I /t/server_selftest.py"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FFG = os.environ.get("FFGLITCH", "/opt/ffglitch")
FAIL = []
if not (shutil.which("ffmpeg") and shutil.which("ffprobe") and os.access(os.path.join(FFG, "ffgac"), os.X_OK)
        and os.access(os.path.join(FFG, "ffedit"), os.X_OK)):
    print("mosher server_selftest: skipped (ffmpeg/ffprobe or FFglitch's ffgac/ffedit not installed)")
    sys.exit(0)
TMP = tempfile.mkdtemp(prefix="mosher-inputs-")


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True)


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries", "stream=codec_type,codec_name,width,height,nb_read_frames",
                        "-of", "json", path], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)["streams"]


def psnr(path, t1, t2):
    """PSNR between the frames at t1 and t2 of one video: low = the picture moved."""
    a, b = os.path.join(TMP, "a.png"), os.path.join(TMP, "b.png")
    ff("-ss", str(t1), "-i", path, "-frames:v", "1", a)
    ff("-ss", str(t2), "-i", path, "-frames:v", "1", b)
    r = subprocess.run(["ffmpeg", "-nostdin", "-i", a, "-i", b, "-lavfi", "psnr", "-f", "null", "-"], capture_output=True, text=True)
    line = [l for l in r.stderr.splitlines() if "average:" in l][-1]
    v = line.split("average:")[1].split()[0]
    return 99.0 if v == "inf" else float(v)


def psnr_vs(path, ref, t, w, h):
    """PSNR between the frame at t of `path` and the frame at t of `ref` scaled to w x h: high = it shows the real picture."""
    a, b = os.path.join(TMP, "a.png"), os.path.join(TMP, "b.png")
    ff("-ss", str(t), "-i", path, "-frames:v", "1", a)
    ff("-ss", str(t), "-i", ref, "-frames:v", "1", "-vf", f"fps=30,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}", b)
    r = subprocess.run(["ffmpeg", "-nostdin", "-i", a, "-i", b, "-lavfi", "psnr", "-f", "null", "-"], capture_output=True, text=True)
    v = [l for l in r.stderr.splitlines() if "average:" in l][-1].split("average:")[1].split()[0]
    return 99.0 if v == "inf" else float(v)


class Svc:
    def __init__(self, **env):
        self.work = tempfile.mkdtemp(prefix="mosher-work-")
        self.port = free_port()
        e = dict(os.environ, PORT=str(self.port), MOSH_TOKEN="tok", WORK=self.work, FFGLITCH=FFG, MOTION_MAX_S="3")
        e.update({k: str(v) for k, v in env.items()})
        self.p = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "server.py")], env=e,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(100):
            try:
                urllib.request.urlopen(self.url("/healthz"), timeout=1)
                break
            except urllib.error.HTTPError:
                break
            except OSError:
                time.sleep(0.1)

    def url(self, p):
        return f"http://127.0.0.1:{self.port}{p}"

    def get(self, p):
        try:
            with urllib.request.urlopen(self.url(p), timeout=10) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def mosh(self, query="", picture=None, motion=b"", token="tok", out=None):
        pic = picture or b""
        h = {"Content-Type": "application/octet-stream", "X-Picture-Length": str(len(pic))}
        if token:
            h["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.url("/mosh" + (f"?{query}" if query else "")), data=pic + motion, method="POST", headers=h)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                body = r.read()
                if out:
                    open(out, "wb").write(body)
                return r.status, dict(r.headers), body
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def stop(self):
        self.p.terminate()
        try:
            self.p.wait(10)
        except subprocess.TimeoutExpired:
            self.p.kill()


motion_path, still_path = os.path.join(TMP, "motion.mp4"), os.path.join(TMP, "still.png")
ff("-f", "lavfi", "-i", "mandelbrot=size=320x180:rate=30", "-f", "lavfi", "-i", "sine=frequency=330:duration=3",
   "-vf", "rotate=t*0.8", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", motion_path)
ff("-f", "lavfi", "-i", "testsrc2=size=400x300", "-frames:v", "1", still_path)
motion, still = open(motion_path, "rb").read(), open(still_path, "rb").read()

s = Svc()
try:
    check("healthz answers ok mosher", s.get("/healthz"), (200, "ok mosher"))
    check("no token: 401", s.mosh(motion=motion, token=None)[0], 401)
    check("wrong token: 401", s.mosh(motion=motion, token="nope")[0], 401)
    for q, why in (("gain=9", "gain"), ("height=241", "height"), ("height=1080", "height"), ("hold=11", "hold"),
                   ("color=1", "unknown option"), ("audio=2", "audio"), ("gain=x", "numbers"),
                   ("cycle=1", "cycle"), ("cycle=21", "cycle"), ("heal=4", "heal")):
        code, _, body = s.mosh(q, motion=motion)
        check(f"{q}: 400 naming {why}", (code, why in body.decode()), (400, True))
    code, _, body = s.mosh(motion=b"definitely not a video")
    check("garbage upload: 400", (code, b"not a video" in body), (400, True))
    code, _, body = s.mosh("hold=5", motion=motion)
    check("one video, hold past its end: 400", (code, b"nothing is left" in body), (400, True))
    code, _, body = s.mosh("cycle=2&hold=1.5&heal=1", motion=motion)
    check("a cycle too short for hold + heal + some smear: 400", (code, b"too short" in body), (400, True))
    code, _, body = s.mosh("cycle=2", picture=still, motion=motion)
    check("cycle with a picture (two files): 400", (code, b"cycle works on one video" in body), (400, True))
    code, _, body = s.mosh(picture=motion, motion=still)
    check("a still as the motion: 400", (code, b"must be a video" in body), (400, True))

    # one video, cycles: 1.5 s cycles of 0.5 s clean, smear, and a 0.5 s fade back to the real video
    cyc = os.path.join(TMP, "cycle.mp4")
    t0 = time.time()
    code, hdr, _ = s.mosh("cycle=1.5&hold=0.5&heal=0.5&height=240", motion=motion, out=cyc)
    check("cycle: 200", code, 200)
    print(f"     cycle took {time.time() - t0:.1f}s")
    if code == 200:
        st = probe(cyc)
        v = [x for x in st if x["codec_type"] == "video"][0]
        check("cycle: two whole cycles of 45 frames", int(v["nb_read_frames"]), 90)
        check("cycle: keeps the sound", any(x["codec_type"] == "audio" for x in st), True)
        clean, smear, healed, again = (psnr_vs(cyc, motion_path, t, 432, 240) for t in (0.3, 0.95, 1.47, 2.45))
        print(f"     cycle PSNR vs the real video: clean {clean:.1f}, smear {smear:.1f}, healed {healed:.1f}, smear again {again:.1f}")
        check("cycle: clean at the start, smeared in the middle, healed at the end, smeared again in the next cycle",
              (clean > 30, smear < clean - 6, healed > smear + 6, again < healed - 6), (True, True, True, True))

    # one video, once (cycle=0, the old behaviour): 1 s clean, then its own motion drags the frame at 1 s, never healing
    one = os.path.join(TMP, "one.mp4")
    t0 = time.time()
    code, hdr, _ = s.mosh("hold=1&height=240&cycle=0", motion=motion, out=one)
    check("one video: 200 video/mp4", (code, hdr.get("Content-Type")), (200, "video/mp4"))
    print(f"     one video took {time.time() - t0:.1f}s")
    if code == 200:
        st = probe(one)
        v = [x for x in st if x["codec_type"] == "video"][0]
        check("one video: h264 at 432x240 (aspect of the motion clip, width a multiple of 16)", (v["codec_name"], v["width"], v["height"]), ("h264", 432, 240))
        check("one video: X-Mosh-Size matches", hdr.get("X-Mosh-Size"), "432x240")
        check("one video: 30 + 59 frames (hold + the motion after it, minus its I-frame)", abs(int(v["nb_read_frames"]) - 89) <= 2, True)
        check("one video: keeps the sound", any(x["codec_type"] == "audio" for x in st), True)
        check("one video: the held frame moves (PSNR 1.1 s vs 2.9 s < 30)", psnr(one, 1.1, 2.9) < 30, True)

    # two files: a still for 0.5 s, then the motion clip's movement drags it; no sound asked
    two = os.path.join(TMP, "two.mp4")
    code, hdr, _ = s.mosh("audio=0&gain=2", picture=still, motion=motion, out=two)
    check("two files: 200", code, 200)
    if code == 200:
        st = probe(two)
        v = [x for x in st if x["codec_type"] == "video"][0]
        check("two files: default height 480, aspect of the motion clip", (v["width"], v["height"]), (848, 480))
        check("two files: 15 + 89 frames", abs(int(v["nb_read_frames"]) - 104) <= 2, True)
        check("two files: audio=0 leaves no sound", any(x["codec_type"] == "audio" for x in st), False)
        check("two files: the still moves (PSNR 0.6 s vs 3.3 s < 30)", psnr(two, 0.6, 3.3) < 30, True)
        check("two files: the first half second is the still, untouched (PSNR 0.1 s vs 0.4 s > 40)", psnr(two, 0.1, 0.4) > 40, True)
    check("WORK is empty after the jobs", os.listdir(s.work), [])
finally:
    s.stop()

s = Svc(FREE_NEED_MB=10 ** 9)
try:
    check("no room in WORK: 507 before reading anything", s.mosh(motion=motion)[0], 507)
finally:
    s.stop()

s = Svc(MOSH_TOKEN="")
try:
    check("no MOSH_TOKEN on the host: every job 401", s.mosh(motion=motion, token="")[0], 401)
finally:
    s.stop()

shutil.rmtree(TMP, ignore_errors=True)
print("mosher server_selftest:", "FAILED " + ", ".join(FAIL) if FAIL else "all passed")
sys.exit(1 if FAIL else 0)
