#!/usr/bin/env python3
"""Offline checks for `gateway transcode` against a fake GPU host and the local ffmpeg. Run: python3 -I gateway_transcode_selftest.py

Covers: the codec list (h264|hevc|av1, anything else refused before any work), the host token is sent,
a 401 is reported instead of silently burning the VM CPU, and the CPU path never leaves a truncated OUT or destroys an
older one (it writes NAME.part.EXT and renames only on success). host choice by /status (the free host first,
429 moves on, older hosts without /status), the local estimate and its limit, the 1080 cap and thread cap, and ffmpeg_shim.py.
"""
import contextlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
FAIL = []
state = {"mode": "ok", "auth": [], "queries": []}


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
        n = int(self.headers["Content-Length"]); self.rfile.read(n)
        state["auth"].append(self.headers.get("Authorization")); state["queries"].append(self.path)
        if state["mode"] == "ok":
            data, code = b"FAKEMP4" * 10, 200
        else:
            data, code = b"nope", int(state["mode"])
        self.send_response(code); self.send_header("Content-Length", str(len(data)))
        if code == 200:
            self.send_header("X-Encode-Seconds", "0.5")
        self.end_headers(); self.wfile.write(data)


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}"
cfgp, logp = os.path.join(tmp, "gateways.json"), os.path.join(tmp, "log.jsonl")


def load(hosts):
    json.dump({"transcode": hosts}, open(cfgp, "w"))
    os.environ.update(GATEWAYS_CONFIG=cfgp, GATEWAY_LOG=logp)
    spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def run(m, argv):
    out = io.StringIO()
    code = None
    with contextlib.redirect_stdout(out):
        try:
            code = m.cmd_transcode(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


src = os.path.join(tmp, "in.mp4")
HAVE_FFMPEG = shutil.which("ffmpeg") is not None
if HAVE_FFMPEG:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10", "-t", "1",
                    "-pix_fmt", "yuv420p", src], check=True)
else:
    open(src, "wb").write(b"not a video")

# 1. codec list
m = load([])
code, txt = run(m, [src, os.path.join(tmp, "x.mp4"), "codec=vp9"])
check("codec=vp9 refused before any work", isinstance(code, str) and "h264, hevc or av1" in code, True)
check("codec=vp9 wrote nothing", os.path.exists(os.path.join(tmp, "x.mp4")), False)
pre, args = m.local_ffmpeg_args({"codec": "av1"})
check("av1 local path uses SVT-AV1", "libsvtav1" in args, True)
pre, args = m.local_ffmpeg_args({"codec": "hevc"})
check("hevc local path is tagged hvc1 (plays on Apple and in Telegram)", "hvc1" in args, True)

# 2. GPU host: token sent, output written
m = load([{"name": "gpu", "url": url, "token": "tok-1234567890abcdef"}])
out = os.path.join(tmp, "gpu.mp4")
state["mode"] = "ok"
code, txt = run(m, [src, out, "codec=av1", "height=720"])
check("GPU host used", code, 0)
check("token sent as Bearer", state["auth"][-1], "Bearer tok-1234567890abcdef")
check("options reach the host", "codec=av1" in state["queries"][-1], True)
check("GPU output written", open(out, "rb").read().startswith(b"FAKEMP4"), True)

# 3. 401: said plainly, then the CPU path
if HAVE_FFMPEG:
    state["mode"] = "401"
    out = os.path.join(tmp, "after401.mp4")
    code, txt = run(m, [src, out, "height=96"])
    check("401 is reported to the agent", "refused this stack's token" in txt, True)
    check("CPU fallback still delivers", code == 0 and os.path.getsize(out) > 0, True)
    check("no .part left after a CPU success", [f for f in os.listdir(tmp) if ".part" in f], [])

# 4. CPU failure never truncates or replaces an older OUT
m = load([])
bad = os.path.join(tmp, "bad.mp4"); open(bad, "wb").write(b"definitely not a video")
old = os.path.join(tmp, "old.mp4"); open(old, "wb").write(b"OLD CONTENT")
code, txt = run(m, [bad, old])
check("a failed CPU encode returns non-zero", code != 0, True)
check("the older OUT is kept intact", open(old, "rb").read(), b"OLD CONTENT")
check("no .part left after a CPU failure", [f for f in os.listdir(tmp) if ".part" in f], [])

# no slow fallback: an encode estimated over the local limit is refused when no host takes it; nothing is started locally
m = load([])
m.LOCAL_MAX_S = -1
outp = os.path.join(tmp, "big-av1.mp4")
code, txt = run(m, [src, outp, "codec=av1"])
check("too slow for this CPU with no host: refused (exit 3), clear sentence, nothing written",
      (code, "is not encoded to AV1 on this container" in txt, os.path.exists(outp), [f for f in os.listdir(tmp) if ".part" in f]), (3, True, False, []))
m = load([])
if HAVE_FFMPEG:
    code, txt = run(m, [src, os.path.join(tmp, "small-av1.mp4"), "codec=av1"])
    check("...a small AV1 job (short estimate) is still made here", code, 0)

# local guards: thread cap from the cgroup quota, short side capped at 1080 unless height= is given
check("cpu_quota is at least 1 and at most 4", 1 <= m.cpu_quota() <= 4, True)
pre, args = m.local_ffmpeg_args({"codec": "av1"}, 1)
check("local args cap decoder, filters and encoder threads", (pre[:4], "-threads" in args), (["-threads", "1", "-filter_threads", "1"], True))
check("local SVT-AV1 gets lp", args[args.index("-svtav1-params") + 1], "lp=1")
p4k = {"w": 3648, "h": 2022, "fps": 28.57, "frames": 2061}
check("4K landscape capped to 1080 high", m.out_size(p4k, {}, 1080), (1948, 1080, "scale=-2:1080"))
check("4K portrait capped to 1080 wide", m.out_size({"w": 2160, "h": 3840, "fps": 30, "frames": 30}, {}, 1080), (1080, 1920, "scale=1080:-2"))
check("height= wins over the cap", m.out_size(p4k, {"height": "480"}, 1080), (866, 480, None))
est4k = m.local_estimate(p4k, {"codec": "av1"}, 1, 196)
check("a 72 s 4K clip in AV1 here, capped to 1080p: about 4 min (measured 188 s), under the limit", 150 < est4k < 400, True)
check("...at 480p in h264: a couple of minutes", 30 < m.local_estimate(p4k, {"height": "480"}, 1, 196) < 300, True)
if HAVE_FFMPEG:
    pr = m.vprobe(src)
    check("vprobe reads the test clip", (pr or {}).get("w"), 160)

# host choice: every host is asked for /status; the free one goes first, a 429 moves on, a host without /status still works
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        st = self.server.st
        if self.path == "/healthz":
            body, code = b"ok", 200
        elif self.path == "/status" and st.get("status") is not None:
            body, code = json.dumps(st["status"]).encode(), 200
        else:
            body, code = b"no", 404
        self.send_response(code); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        st = self.server.st
        st["posts"] += 1
        code = st.get("post", 200)
        data = b"FAKEMP4-" + st["name"].encode() if code == 200 else b"busy"
        self.send_response(code); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


def fake(name, status=None, post=200):
    s = HTTPServer(("127.0.0.1", 0), Fake)
    s.st = {"name": name, "status": status, "post": post, "posts": 0}
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_address[1]}"


full = {"state": "running", "lanes": {"gpu": {"slots": 2, "busy": 2, "eta_s": 300, "avg_s": 60}, "cpu": {"slots": 1, "busy": 0}}}
free = {"state": "idle", "lanes": {"gpu": {"slots": 2, "busy": 0, "eta_s": 0}, "cpu": {"slots": 1, "busy": 0}}}
sa, ua = fake("busyhost", full)
sb, ub = fake("freehost", free)
m = load([{"name": "busyhost", "url": ua}, {"name": "freehost", "url": ub}])
m.HOST_NET_MBS = 1e6
order = [h["name"] for h in m.ranked("transcode", lane="gpu")]
check("ranked: the free host before the full one listed first", order, ["freehost", "busyhost"])
outp = os.path.join(tmp, "ranked.mp4")
m.LOCAL_MAX_S = -1         # keep the local CPU out of this check
code, txt = run(m, [src, outp])
check("the job went to the free host", (code, open(outp, "rb").read() if os.path.exists(outp) else None), (0, b"FAKEMP4-freehost"))
check("...and the full host got nothing", sa.st["posts"], 0)
m2 = load([{"name": "gone", "url": "http://127.0.0.1:9"}, {"name": "freehost", "url": ub}])
check("a down host ranks last", [h["name"] for h in m2.ranked("transcode")], ["freehost", "gone"])
check("full lane: wait is the soonest eta (300 s)", m.host_wait(full, "transcode", "gpu"), 300.0)
check("free lane: no wait", m.host_wait(free, "transcode", "gpu"), 0.0)
check("asleep image service: model load counted", m.host_wait({"state": "asleep", "slots": 1, "busy": 0}, "image"), 40.0)
check("host JSON is never trusted as is (a string eta is ignored)", m.host_wait({"slots": 1, "busy": 1, "eta_s": "9e99"}, "video"), 210.0)
sc, uc = fake("first429", free, post=429)
sd, ud = fake("legacy", None)          # an older service: /healthz only
m = load([{"name": "first429", "url": uc}, {"name": "legacy", "url": ud}])
m.LOCAL_MAX_S = -1
outp = os.path.join(tmp, "after429.mp4")
code, txt = run(m, [src, outp])
check("a 429 from the chosen host passes the job to the next (an older one with no /status)",
      (code, open(outp, "rb").read() if os.path.exists(outp) else None), (0, b"FAKEMP4-legacy"))
if HAVE_FFMPEG:
    se, ue = fake("faraway", free)
    m = load([{"name": "faraway", "url": ue, "net_mbs": 0.000001}])
    outp = os.path.join(tmp, "local-first.mp4")
    code, txt = run(m, [src, outp])
    check("a tiny clip stays on the local CPU when the host would take far longer", (code, se.st["posts"], "it is faster here" in txt), (0, 0, True))
    for s_ in (se,):
        s_.shutdown()
for s_ in (sa, sb, sc, sd):
    s_.shutdown()

# the ffmpeg shim of the stack image: thread cap added only where the command set none, no hand-run AV1 encode
spec = importlib.util.spec_from_file_location("shim", os.path.join(HERE, "ffmpeg_shim.py"))
shim = importlib.util.module_from_spec(spec); spec.loader.exec_module(shim)
check("shim: cap before the first input and the last output",
      shim.shape(["-y", "-i", "a.mp4", "-c:v", "libx264", "b.mp4"], 1),
      ["-filter_threads", "1", "-y", "-threads", "1", "-i", "a.mp4", "-c:v", "libx264", "-threads", "1", "b.mp4"])
check("shim: a command with its own -threads keeps it", shim.shape(["-i", "a", "-threads", "3", "b"], 1).count("-threads"), 1)
check("shim: -version untouched", shim.shape(["-version"], 1), ["-version"])
check("shim: libx265 gets its pool size", "pools=2:frame-threads=1" in shim.shape(["-i", "a", "-c:v", "libx265", "b.mp4"], 2), True)
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ffmpeg_shim.py"), "-i", "x.mp4", "-c:v", "libsvtav1", "y.mp4"],
                   capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k != "AIBRIDGE_FFMPEG_GATEWAY"})
check("shim: a hand AV1 encode is refused with the gateway command", (r.returncode, "gateway transcode IN OUT codec=av1" in r.stderr), (2, True))
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ffmpeg_shim.py"), "-c:v", "libdav1d", "-i", "x.mp4", "y.mp4"],
                   capture_output=True, text=True)
check("shim: decoding AV1 (decoder before -i) is not refused", r.returncode != 2 or "gateway transcode" not in r.stderr, True)

shutil.rmtree(tmp, ignore_errors=True)
srv.shutdown()
print("all ok" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}")
sys.exit(1 if FAIL else 0)
