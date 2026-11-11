#!/usr/bin/env python3
"""Offline test of gpu-host/vidpost/server.py with a fake ComfyUI (no GPU, no model, no network beyond loopback; needs ffmpeg)."""
import json, os, shutil, signal, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []
if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
    print("vidpost server_selftest: skipped (ffmpeg/ffprobe not installed)")
    sys.exit(0)
TMP = tempfile.mkdtemp(prefix="vidpost-inputs-")


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def clip(name, size="320x240", secs=2, fps=24, audio=True, tag=None):
    path = os.path.join(TMP, name)
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}:duration={secs}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest"] + (["-metadata", f"title={tag}"] if tag else []) + [path]
    subprocess.run(cmd, check=True)
    return open(path, "rb").read()


class Svc:
    def __init__(self, mode="ok", vram=20000, ram_mb=30000, idle=2.0, job_timeout=6.0, token="tok", extra=None, work=None):
        self.work = work or tempfile.mkdtemp(prefix="vidpost-work-")
        aux = tempfile.mkdtemp(prefix="vidpost-aux-")
        self.log = os.path.join(aux, "graphs.jsonl")
        self.port, self.cport, self.token = free_port(), free_port(), token
        nv = os.path.join(aux, "nvsmi.sh"); open(nv, "w").write(f"#!/bin/sh\necho {vram}\n"); os.chmod(nv, 0o755)
        mi = os.path.join(aux, "meminfo"); open(mi, "w").write(f"MemTotal: 32000000 kB\nMemAvailable: {ram_mb * 1024} kB\n")
        env = dict(os.environ, GPU_PROBE=os.environ.get('GPU_PROBE_TEST', 'true'), GPU_CHECK_S='1', PORT=str(self.port), VIDPOST_TOKEN=token, WORK=self.work, COMFY_PORT=str(self.cport),
                   COMFY_CMD=f"{sys.executable} {HERE}/fake_comfy.py", COMFY_DIR="", IDLE_S=str(idle), JOB_TIMEOUT=str(job_timeout),
                   READY_TIMEOUT="20", NVSMI=nv, MEMINFO=mi, FAKE_MODE=mode, COMFY_FAKE_LOG=self.log, MEM_WAIT_S="0", **(extra or {}))
        self.out = tempfile.NamedTemporaryFile("w+", delete=False)
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")], env=env, stdout=self.out, stderr=subprocess.STDOUT)
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/healthz", timeout=1); break
            except Exception:
                time.sleep(0.1)

    def req(self, data, query="", auth=True, path="/enhance", token=None):
        h = {"Content-Type": "video/mp4"}
        if auth:
            h["Authorization"] = f"Bearer {token or self.token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}{path}{query}", data=data, headers=h, method="POST"), timeout=60) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as r:
            return r.status, r.read().decode()

    def comfy_alive(self):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.cport}/system_stats", timeout=1); return True
        except Exception:
            return False

    def graphs(self):
        return [json.loads(l) for l in open(self.log)] if os.path.exists(self.log) else []

    def leftovers(self):
        return sorted(os.path.relpath(os.path.join(d, f), self.work) for sub in ("up", "in", "out/stg", "job")
                      for d, _, fs in os.walk(os.path.join(self.work, sub)) for f in fs)

    def logtext(self):
        self.out.flush(); return open(self.out.name).read()

    def close(self):
        self.p.send_signal(signal.SIGTERM)
        try:
            self.p.wait(20)
        except subprocess.TimeoutExpired:
            self.p.kill()


def frames_of(b):
    f = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False); f.write(b); f.close()
    r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries", "stream=nb_read_packets",
                        "-of", "csv=p=0", f.name], capture_output=True, text=True)
    os.unlink(f.name); return int(r.stdout.strip() or 0)


def tags_of(b):
    f = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False); f.write(b); f.close()
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format_tags", "-of", "json", f.name], capture_output=True, text=True)
    os.unlink(f.name); j = json.loads(r.stdout or "{}")
    return sorted(s["codec_type"] for s in j.get("streams", [])), j.get("format", {}).get("tags", {})


small = clip("small.mp4", tag="SECRET-UPLOAD-TITLE")
s = Svc()
try:
    check("healthz answers", s.get("/healthz"), (200, "ok vidpost"))
    # the GPU watch: a container that lost the card answers 503 on /healthz (the gateway skips it, Zabbix alerts)
    os.environ["GPU_PROBE_TEST"] = "false"; nogpu = Svc(); os.environ.pop("GPU_PROBE_TEST")
    try:
        time.sleep(1.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{nogpu.port}/healthz", timeout=5); got = 200
        except urllib.error.HTTPError as e:
            got = (e.code, e.read().decode()[:6])
        check("healthz is 503 'no gpu' when CUDA cannot see the card", got, (503, "no gpu"))
    finally:
        nogpu.close()
    st, body, hdr = s.req(small)
    check("defaults (scale 2, fps x2) return an mp4 with size and fps headers", (st, body[4:8], hdr.get("X-Enhance-Size"), hdr.get("X-Enhance-Fps")),
          (200, b"ftyp", "640x480", "48.0"))
    g = s.graphs()[-1]
    check("the graph chains upscale then RIFE, with the fixed models and the computed size and fps, and no sound (put back at the end)",
          (g["ml"]["inputs"]["model_name"], g["rs"]["inputs"]["width"], g["rs"]["inputs"]["height"], g["fi"]["inputs"]["images"], g["fi"]["inputs"]["multiplier"],
           g["fl"]["inputs"]["model_name"], g["cv"]["inputs"]["fps"], "audio" in g["cv"]["inputs"], "fb" in g),
          ("realesr-general-x4v3.safetensors", 640, 480, ["rs", 0], 2, "rife_v4.26.safetensors", 48.0, False, False))
    check("the piece's file name is the wrapper's random name, never the client's", g["lv"]["inputs"]["file"].startswith("p_") and len(g["lv"]["inputs"]["file"]) == 42, True)
    check("a short clip is one piece and the answer has every frame (48 in, RIFE 2n-1 = 95 out)", (len(s.graphs()), frames_of(body)), (1, 95))
    streams, tags = tags_of(body)
    check("the answer keeps video and audio and carries no metadata", (streams, "SECRET" in json.dumps(tags)), (["audio", "video"], False))
    check("nothing of the job is left (upload, input copy, staging)", s.leftovers(), [])
    s.req(small, "?scale=1&fps=2"); g = s.graphs()[-1]
    check("fps only: RIFE on the original frames, no upscaler nodes", ("ml" in g, g["fi"]["inputs"]["images"], g["cv"]["inputs"]["fps"]), (False, ["gc", 0], 48.0))
    s.req(small, "?scale=2&fps=0"); g = s.graphs()[-1]
    check("scale only: no RIFE nodes, original fps", ("fi" in g, g["cv"]["inputs"]["images"], g["cv"]["inputs"]["fps"]), (False, ["rs", 0], 24.0))
    st, body, hdr = s.req(small, "?scale=1&fps=2&slow=1"); g = s.graphs()[-1]
    check("slow motion: RIFE frames kept at the original fps (twice as long), no audio in the graph, the source sound added back",
          (st, hdr.get("X-Enhance-Fps"), g["cv"]["inputs"]["fps"], "audio" in g["cv"]["inputs"], tags_of(body)[0]), (200, "24.0", 24.0, False, ["audio", "video"]))
    check("slow without fps=2, or a bad slow value, is 400", (s.req(small, "?scale=2&fps=0&slow=1")[0], s.req(small, "?slow=2")[0]), (400, 400))
    bad = [("?scale=1&fps=0", small), ("?scale=3", small), ("?fps=4", small), ("?scale=2&x=1", small), ("", b"not an mp4 at all, just text......"),
           ("", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 100)]
    check("nothing asked, bad values, unknown params, non-mp4 and broken mp4 are 400", [s.req(d, q)[0] for q, d in bad], [400] * len(bad))
    check("an audio-only file is 400", s.req(open(os.path.join(TMP, "a.m4a"), "rb").read() if subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", "-c:a", "aac", "-f", "mp4", os.path.join(TMP, "a.m4a")]).returncode == 0 else b"")[0], 400)
    long_clip = clip("long.mp4", secs=31, audio=False)
    check("a clip over MAX_SECS is 400", s.req(long_clip)[0], 400)
    big = clip("big.mp4", size="1280x720", secs=10, audio=False)
    check("too much work for MAX_WORK (720p, 10 s, scale 2 + 48 fps = 479 frames x 3.7 Mpx) is 400, the same clip at fps only is fine",
          (s.req(big)[0], s.req(big, "?scale=1&fps=2")[0]), (400, 200))
    check("the refusal text never echoes the upload", b"SECRET" in s.req(b"SECRET-UPLOAD " * 10)[1], False)
    check("no token / wrong token is 401, unknown path 404", (s.req(small, auth=False)[0], s.req(small, token="nope")[0], s.req(small, path="/video")[0]), (401, 401, 404))
    check("an empty body is 400", s.req(b"")[0], 400)
    check("nothing is left after the refusals", s.leftovers(), [])
    check("the service log never holds the upload's title", "SECRET" in s.logtext(), False)
finally:
    s.close()

# Pieces: 48 frames of 320x240; scale 2 + RIFE makes 640x480 x 2 per input frame, so CHUNK_WORK 6e6 gives pieces of 9 frames.
s = Svc(extra={"CHUNK_WORK": "6e6"})
try:
    st, body, hdr = s.req(small); gs = s.graphs()
    starts = [g["lv"]["inputs"]["file"] for g in gs]
    check("with RIFE the clip goes in 6 pieces of 9 frames sharing one frame (0-8, 8-16, ... 40-47)", (st, len(gs)), (200, 6))
    check("the first piece keeps its first frame, every later one drops it (ImageFromBatch from 1)",
          [("fb" in g, g.get("fb", {}).get("inputs", {}).get("batch_index"), g.get("fb", {}).get("inputs", {}).get("image")) for g in gs],
          [(False, None, None)] + [(True, 1, ["fi", 0])] * 5)
    check("the joined answer has exactly the frames of one pass (2 x 48 - 1 = 95) and the source's sound", (frames_of(body), tags_of(body)[0]), (95, ["audio", "video"]))
    check("every piece had its own random name and nothing of the job is left", (len(set(starts)), s.leftovers()), (6, []))
    st, body, _ = s.req(small, "?scale=2&fps=0"); gs = s.graphs()[6:]
    check("scale only: disjoint pieces (19 frames each: 0-18, 19-37, 38-47), no frame dropped, all 48 frames",
          (st, len(gs), any("fb" in g for g in gs), frames_of(body)), (200, 3, False, 48))
    st, body, hdr = s.req(small, "?scale=1&fps=2&slow=1")
    check("slow motion in pieces: 95 frames at 24 fps with the sound stretched", (st, frames_of(body), hdr.get("X-Enhance-Fps"), tags_of(body)[0]),
          (200, 95, "24.0", ["audio", "video"]))
    # Odd uploads found by the review.
    rot = os.path.join(TMP, "rot.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-display_rotation", "90", "-i", os.path.join(TMP, "small.mp4"), "-c", "copy", rot], check=True)
    st, body, hdr = s.req(open(rot, "rb").read()); g = s.graphs()[-1]
    check("a portrait phone video (stored 320x240, rotated 90) is planned upright: 480x640, never squashed to 640x480",
          (st, hdr.get("X-Enhance-Size"), g["rs"]["inputs"]["width"], g["rs"]["inputs"]["height"]), (200, "480x640", 480, 640))
    odd = os.path.join(TMP, "odd.mp4")              # 4:4:4, the only way x264 takes an odd size
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=321x241:rate=24:duration=2", "-c:v", "libx264",
                    "-pix_fmt", "yuv444p", odd], check=True)
    st, body, hdr = s.req(open(odd, "rb").read())
    check("an odd-sized video is cropped to even (x264 4:2:0) instead of failing", (st, hdr.get("X-Enhance-Size")), (200, "640x480"))
    bsrc = os.path.join(TMP, "bsrc.mp4"); trim = os.path.join(TMP, "trim.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=4", "-c:v", "libx264", "-bf", "2",
                    "-g", "300", "-pix_fmt", "yuv420p", bsrc], check=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", "1.5", "-i", bsrc, "-c", "copy", trim], check=True)
    st, body, hdr = s.req(open(trim, "rb").read(), "?scale=1&fps=2")
    check("a trimmed mp4 (hidden pre-roll packets behind an edit list) counts its real 75 frames: 149 out, no empty last piece",
          (st, frames_of(body)), (200, 149))
    check("and nothing of those jobs is left", s.leftovers(), [])
finally:
    s.close()

w = tempfile.mkdtemp(prefix="vidpost-work-")
for d in ("up", "job/abc"):
    os.makedirs(os.path.join(w, d)); open(os.path.join(w, d, "left.mp4"), "w").write("x")
s = Svc(work=w)
try:
    check("an upload and pieces left by a job cut short are removed when the service starts", s.leftovers(), [])
finally:
    s.close()

s = Svc(mode="slow", job_timeout=5.0)
try:
    res = []
    t = threading.Thread(target=lambda: res.append(s.req(small)[0])); t.start(); time.sleep(1.5)
    st, _, hdr = s.req(small)
    check("a second job during one gets 429 with Retry-After", (st, hdr.get("Retry-After")), (429, "30"))
    big_body = b"\x00" * 3_000_000
    check("a 3 MB upload during a job still gets a clean 429, and a bad token a clean 401 (the body is read first, no reset)",
          (s.req(big_body)[0], s.req(big_body, token="nope")[0]), (429, 401))
    t.join(40)
    check("a job that never completes is 504 and ComfyUI is killed", (res, s.comfy_alive()), ([504], False))
    check("and nothing of it is left", s.leftovers(), [])
finally:
    s.close()

s = Svc(mode="error")
try:
    check("ComfyUI reporting an error is a fixed 500", s.req(small)[0], 500)
finally:
    s.close()
s = Svc(vram=1000)
try:
    check("without free VRAM it is 503 and ComfyUI never starts", (s.req(small)[0], s.comfy_alive(), s.graphs()), (503, False, []))
finally:
    s.close()

env = dict(os.environ, VIDPOST_TOKEN="", PORT=str(free_port()), WORK=tempfile.mkdtemp())
r = subprocess.run([sys.executable, os.path.join(HERE, "server.py")], env=env, capture_output=True, text=True, timeout=20)
check("the service refuses to start without a token", (r.returncode != 0, "VIDPOST_TOKEN" in r.stderr), (True, True))

s = Svc(idle=60)
st = s.req(small)[0]; alive = s.comfy_alive(); s.close(); time.sleep(0.5)
check("SIGTERM to the service stops its ComfyUI too (no orphan holding RAM, VRAM and the port)", (st, alive, s.comfy_alive()), (200, True, False))

print("vidpost server_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
