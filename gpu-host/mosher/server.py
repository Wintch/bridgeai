#!/usr/bin/env python3
"""
mosher -- datamosh over HTTP for Hermes: the motion of one clip drags the pixels of another picture, the
a well-known phone-app effect, made with FFglitch (an FFmpeg fork that edits the MPEG-4 motion vectors in the bitstream).
CPU only: any machine with Docker can run it (a GPU host, or the VM itself by container name).

  GET  /healthz     "ok mosher" once ffgac and ffedit answered at start, else 503 + why
  POST /mosh?hold=S&gain=G&height=H&audio=0|1     Authorization: Bearer <MOSH_TOKEN>
        body = [picture bytes][motion bytes], header X-Picture-Length = the picture's size (0 or absent: one video only)
        -> 200 video/mp4 (H.264 + AAC), headers X-Mosh-Seconds, X-Mosh-Size ("WxH")
        -> 400 bad request (fixed text) | 401 | 413 too big | 429 busy | 500 failed | 504 timeout | 507 no room in WORK

How: both clips are scaled to the same size and frame rate and encoded with
ffgac as MPEG-4 part 2 with one I-frame (-g max, no scene-cut I-frames, no B-frames, forced motion vectors on every
macroblock). The carrier is the picture (a video plays for `hold` seconds, a still image shows for `hold` seconds) and then
its last frame held still, so those held P-frames have zero motion and no residual. ffedit exports the motion vectors of
both; the motion clip's vectors (times `gain`) replace the held frames' vectors, frame by frame; ffedit writes them back.
Decoded, the held picture is dragged by the other clip's motion, with nothing of the other clip's own pixels.

  two files (picture + motion): the picture plays (a video: up to PIC_MAX_S, or `hold` s of it; a photo: `hold` s,
                                default 0.5), then the motion clip's movement takes over
  one video:                    it plays clean for `hold` s (default 1), then freezes and its own later movement drags
                                that frame ("film a clip, then film something else", in one take)

Options (a closed list): hold 0-10 s, gain 0.25-4 (the motion's strength), height 240-720 (even; default 480: the work grows
with the pixels), audio 1|0 (default 1: the motion clip's sound, lined up with its movement). The output size follows the
motion clip's aspect ratio; the picture is scaled to cover it and cropped. At most MOTION_MAX_S seconds of motion are used.

Disk: everything happens in WORK (a tmpfs in the container, RAM only), one job at a time by default; each intermediate file is
deleted once used and the job folder at the end. A 480p 20 s job peaks at about 60 MB there (two MPEG-4 AVIs at q 1 and two
motion-vector JSON files). The image adds only ffgac and ffedit (~56 MB) to the same Debian + ffmpeg layer as transcoder/.
Stdlib only, like transcoder/.
"""
import hmac
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "8690"))
TOKEN = os.environ.get("MOSH_TOKEN", "")
WORK = os.environ.get("WORK", "/work")
FFGLITCH = os.environ.get("FFGLITCH", "/opt/ffglitch")
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
JOBS = int(os.environ.get("JOBS", "1"))
MAX_BYTES = int(os.environ.get("MAX_MB", "200")) * 1024 * 1024
MOTION_MAX_S = float(os.environ.get("MOTION_MAX_S", "20"))
PIC_MAX_S = float(os.environ.get("PIC_MAX_S", "10"))
TIMEOUT_S = float(os.environ.get("TIMEOUT_S", "600"))
FREE_NEED_MB = int(os.environ.get("FREE_NEED_MB", "300"))   # WORK must have this much free before a job starts
# One video loops like a typical datamosh edit: clean, then the picture freezes and its own motion smears it,
# then it fades back to the real video and the next cycle starts on a fresh I-frame. CYCLE_DEFAULT=0 brings back the
# old single break that never heals. A picture plus a video (two files) keeps the single break.
CYCLE_DEFAULT = float(os.environ.get("CYCLE_DEFAULT", "4"))
HEAL_DEFAULT = 0.8
SMEAR_MIN_S, SMEAR_RAMP_S = 0.5, 0.3
FPS = 30
FCODE = 6                                                    # MPEG-4 f_code: vectors up to +-1024 half-pels
MV_LIMIT = (16 << FCODE) - 1
SLOTS = threading.BoundedSemaphore(JOBS)
HEALTH = {"ok": False, "why": "not checked yet"}
GAC = ["-v", "error", "-y", "-c:v", "mpeg4", "-qscale:v", "1", "-bf", "0", "-g", "max", "-sc_threshold", "max",
       "-mpv_flags", "+nopimb+forcemv", "-fcode", str(FCODE), "-an"]


class Bad(ValueError):
    """A request we refuse with 400 and this fixed text."""


def tool(name):
    return os.path.join(FFGLITCH, name)


def self_test():
    try:
        for t in ("ffgac", "ffedit"):
            r = subprocess.run([tool(t), "-version"], capture_output=True, text=True, timeout=30)
            if r.returncode != 0 or "ffglitch" not in r.stdout:
                return HEALTH.update(ok=False, why=f"{t} did not answer")
        for t in (FFMPEG, FFPROBE):
            if subprocess.run([t, "-version"], capture_output=True, timeout=30).returncode != 0:
                return HEALTH.update(ok=False, why=f"{t} did not answer")
        HEALTH.update(ok=True, why="")
    except (OSError, subprocess.SubprocessError) as e:
        HEALTH.update(ok=False, why=type(e).__name__)


def options(query):
    q = {k: v[-1] for k, v in parse_qs(query).items()}
    unknown = set(q) - {"hold", "gain", "height", "audio", "cycle", "heal"}
    if unknown:
        raise Bad("unknown option: " + ", ".join(sorted(unknown)))
    try:
        o = {"hold": float(q["hold"]) if "hold" in q else None, "gain": float(q.get("gain", "1")),
             "height": int(q.get("height", "480")), "audio": q.get("audio", "1"),
             "cycle": float(q["cycle"]) if "cycle" in q else None, "heal": float(q.get("heal", HEAL_DEFAULT))}
    except ValueError:
        raise Bad("hold, gain, height, cycle and heal must be numbers")
    if o["cycle"] is not None and not (o["cycle"] == 0 or 1.5 <= o["cycle"] <= 20):
        raise Bad("cycle must be 0 (break once) or 1.5 to 20 seconds")
    if not 0 <= o["heal"] <= 3:
        raise Bad("heal must be 0 (a hard cut back) to 3 seconds")
    if o["hold"] is not None and not 0 <= o["hold"] <= 10:
        raise Bad("hold must be 0 to 10 seconds")
    if not 0.25 <= o["gain"] <= 4:
        raise Bad("gain must be 0.25 to 4")
    if not 240 <= o["height"] <= 720 or o["height"] % 2:
        raise Bad("height must be an even number from 240 to 720")
    if o["audio"] not in ("0", "1"):
        raise Bad("audio must be 0 or 1")
    return o


def probe(path):
    """(kind, width, height, seconds, has_audio) of an upload; kind is "video" or "image". Bad if it is neither."""
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration,format_name",
                        "-of", "json", path], capture_output=True, text=True, timeout=60)
    try:
        info = json.loads(r.stdout or "{}")
    except ValueError:
        info = {}
    vs = [s for s in info.get("streams", []) if s.get("codec_type") == "video" and s.get("width")]
    if r.returncode != 0 or not vs:
        raise Bad("an upload is not a video or a picture")
    fmt = info.get("format", {})
    name = fmt.get("format_name", "")
    image = name == "image2" or (name.endswith("_pipe") and vs[0].get("codec_name") != "gif")   # jpeg_pipe, png_pipe, webp_pipe...
    try:
        secs = float(fmt.get("duration") or 0)
    except ValueError:
        secs = 0.0
    has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    return ("image" if image else "video"), int(vs[0]["width"]), int(vs[0]["height"]), secs, has_audio


def run(cmd, deadline, what):
    left = deadline - time.time()
    if left <= 0:
        raise TimeoutError(what)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=left)
    if r.returncode != 0:
        raise RuntimeError(f"{what}: " + ((r.stderr.strip().splitlines() or ["?"])[-1])[:200])


def gone(*paths):
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


def count_frames(mv_json):
    return len(json.load(open(mv_json))["streams"][0]["frames"])


def merge(carrier_json, motion_json, start, gain, out_json, pairs=None):
    """Carrier frames start.. take the motion clip's vectors (its frame 1.., frame 0 is the I-frame), times gain, clamped to
    the f_code range. With `pairs` [(carrier frame, motion frame, gain), ...] exactly those frames are replaced instead.
    Returns the number of motion frames used."""
    c = json.load(open(carrier_json))
    m = json.load(open(motion_json))
    cf, mf = c["streams"][0]["frames"], m["streams"][0]["frames"]
    if pairs is None:
        pairs = ((start + k, k + 1, gain) for k in range(len(mf) - 1))
    used = 0
    for i, mi, g in pairs:
        if i >= len(cf) or mi >= len(mf):
            break
        src, dst = (mf[mi].get("mv") or {}).get("forward"), (cf[i].get("mv") or {}).get("forward")
        used += 1
        if not src or not dst:
            continue
        for r in range(min(len(src), len(dst))):
            sr, dr = src[r], dst[r]
            for col in range(min(len(sr), len(dr))):
                v = sr[col]
                if v is not None and dr[col] is not None:
                    dr[col] = [max(-MV_LIMIT, min(MV_LIMIT, round(v[0] * g))), max(-MV_LIMIT, min(MV_LIMIT, round(v[1] * g)))]
    with open(out_json, "w") as f:
        json.dump(c, f, separators=(",", ":"))
    return used


def cycle_plan(N, C, h, gain):
    """Per output frame, the gain its vectors get (0 = left as it is: the clean part of each cycle). The smear starts gently
    (a ramp over SMEAR_RAMP_S) so the picture goes from fine to blurry instead of jumping."""
    ramp = max(1, round(SMEAR_RAMP_S * FPS))
    return [0.0 if i % C < h else gain * min(1.0, (i % C - h + 1) / ramp) for i in range(N)]


def mosh_cycle(job, mot, o, W, H, fit, msecs, maudio, deadline):
    """One video in cycles of C frames: h clean frames, then the last clean frame is held and the clip's own motion drags it,
    and over the last hl frames the result fades back to the real video; every cycle starts on a fresh I-frame of the real
    picture, so it breaks and heals again and again (the classic datamosh look). Returns the number of frames."""
    j = lambda n: os.path.join(job, n)
    C = round(o["cycle"] * FPS)
    h = max(1, round((1.0 if o["hold"] is None else o["hold"]) * FPS))
    hl = round(o["heal"] * FPS)
    avail = int(min(MOTION_MAX_S, msecs or MOTION_MAX_S) * FPS)
    C = min(C, avail)
    if C < h + hl + round(SMEAR_MIN_S * FPS):
        raise Bad("the cycle is too short for hold + heal + half a second of smear (or the video is shorter than one cycle)")
    N = avail // C * C
    # 1. the real video at the output size and rate, exactly N frames
    run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", mot, "-vf", f"fps={FPS},{fit},tpad=stop_mode=clone:stop_duration=1",
         "-frames:v", str(N), "-an", "-c:v", "ffv1", j("real.mkv")], deadline, "real")
    # 2. the carrier: the real video with each cycle's smear part frozen on its last clean frame
    n = N // C
    graph = [f"[0:v]split={n + 1}[a]" + "".join(f"[r{c}]" for c in range(n))]
    prev = "a"
    for c in range(n):
        graph.append(f"[{prev}][r{c}]freezeframes=first={c * C + h}:last={c * C + C - 1}:replace={c * C + h - 1}[f{c}]")
        prev = f"f{c}"
    run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", j("real.mkv"), "-filter_complex", ";".join(graph), "-map", f"[{prev}]",
         "-frames:v", str(N), "-an", "-c:v", "ffv1", j("car.mkv")], deadline, "carrier")
    gac = list(GAC)
    gac[gac.index("-g") + 1] = str(C)                       # an I-frame of the real picture at every cycle start
    run([tool("ffgac"), "-i", j("car.mkv"), *gac, j("car.avi")], deadline, "carrier encode")
    gone(j("car.mkv"))
    # 3. the motion: the same real video, its own vectors frame by frame
    run([tool("ffgac"), "-i", j("real.mkv"), *GAC, j("mot.avi")], deadline, "motion encode")
    run([tool("ffedit"), "-v", "error", "-y", "-i", j("car.avi"), "-f", "mv", "-e", j("car.json")], deadline, "carrier vectors")
    run([tool("ffedit"), "-v", "error", "-y", "-i", j("mot.avi"), "-f", "mv", "-e", j("mot.json")], deadline, "motion vectors")
    gone(j("mot.avi"))
    plan = cycle_plan(N, C, h, o["gain"])
    merge(j("car.json"), j("mot.json"), 0, 0, j("new.json"), pairs=[(i, i, g) for i, g in enumerate(plan) if g > 0])
    gone(j("car.json"), j("mot.json"))
    run([tool("ffedit"), "-v", "error", "-y", "-i", j("car.avi"), "-f", "mv", "-a", j("new.json"), "-o", j("moshed.avi")], deadline, "apply")
    gone(j("car.avi"), j("new.json"))
    # 4. the heal: the last hl frames of every cycle fade from the smear back to the real video (frame-exact, by frame number)
    cmd = [FFMPEG, "-nostdin", "-v", "error", "-y", "-i", j("moshed.avi"), "-i", j("real.mkv")]
    if hl:
        # blend counts frames from 1 here (measured: with mod(N) the last frame of each cycle jumped back to the smear);
        # mod(N-1) is exact for that and only 1/hl short of clean if a build counts from 0. Commas need no escaping in quotes.
        a = f"clip((mod(N-1,{C})-{C - hl}+1)/{hl},0,1)"
        vf = f"[0:v]format=yuv420p[m];[1:v]format=yuv420p[r];[m][r]blend=all_expr='A*(1-{a})+B*{a}'[v]"
    else:
        vf = "[0:v]format=yuv420p[v]"
    sound = o["audio"] == "1" and maudio
    if sound:                                               # the clip's own sound, from its start, as long as the picture
        cmd += ["-t", f"{N / FPS:.3f}", "-i", mot]
    cmd += ["-filter_complex", vf, "-map", "[v]"]
    cmd += ["-map", "2:a:0", "-c:a", "aac", "-b:a", "128k", "-shortest"] if sound else ["-an"]
    cmd += ["-frames:v", str(N), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-map_metadata", "-1", "-movflags", "+faststart", j("out.mp4")]
    run(cmd, deadline, "final encode")
    gone(j("moshed.avi"), j("real.mkv"))
    return N


def mosh(job, pic, mot, o, deadline):
    """Write job/out.mp4; return (width, height)."""
    mkind, mw, mh, msecs, maudio = probe(mot)
    if mkind != "video":
        raise Bad("the motion upload must be a video")
    if pic:
        pkind, _, _, psecs, _ = probe(pic)
        if pkind == "image":
            hold = 0.5 if o["hold"] is None else max(o["hold"], 1 / FPS)
        else:
            hold = min(PIC_MAX_S, psecs or PIC_MAX_S) if o["hold"] is None else max(o["hold"], 1 / FPS)
            if psecs:      # a hold past the picture video's end would put the "held" frame after the carrier ends: no motion at all
                hold = min(hold, psecs)
        mstart = 0.0
    else:
        hold = 1.0 if o["hold"] is None else max(o["hold"], 1 / FPS)
        if msecs and hold >= msecs - 0.2:
            raise Bad("hold is as long as the video: nothing is left to move the picture")
        pic, pkind, mstart = mot, "video", hold
    cyc = o["cycle"] if o["cycle"] is not None else (0 if pic is not mot else CYCLE_DEFAULT)
    if cyc and pic is not mot:
        raise Bad("cycle works on one video: leave it out (or 0) with a picture")
    H = o["height"]
    # width from MOTION's aspect, a multiple of 16, kept between 128 and 1280 (a portrait clip stays portrait; an odd strip is cropped)
    W = min(1280, max(128, round(mw * H / mh / 16) * 16)) if mw and mh else round(H * 16 / 9 / 16) * 16
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,format=yuv420p"
    if cyc:
        o = dict(o, cycle=cyc)
        mosh_cycle(job, mot, o, W, H, fit, msecs, maudio, deadline)
        return W, H
    mdur = min(MOTION_MAX_S, max(0.0, (msecs or MOTION_MAX_S) - mstart))
    if mdur < 0.2:
        raise Bad("the motion video is too short")
    j = lambda n: os.path.join(job, n)
    # 1. the carrier: the picture for `hold` s, then its last frame held for the motion's length (+1 s of margin)
    src_in = (["-loop", "1", "-t", f"{hold:.3f}", "-i", pic] if pkind == "image" else ["-t", f"{hold:.3f}", "-i", pic])
    run([FFMPEG, "-nostdin", "-v", "error", "-y", *src_in, "-vf", f"fps={FPS},{fit},tpad=stop_mode=clone:stop_duration={mdur + 1:.3f}",
         "-an", "-c:v", "ffv1", j("car.mkv")], deadline, "carrier")
    run([tool("ffgac"), "-i", j("car.mkv"), *GAC, j("car.avi")], deadline, "carrier encode")
    gone(j("car.mkv"))
    # 2. the motion clip at the same size and rate
    run([FFMPEG, "-nostdin", "-v", "error", "-y", "-ss", f"{mstart:.3f}", "-t", f"{mdur:.3f}", "-i", mot, "-vf", f"fps={FPS},{fit}",
         "-an", "-c:v", "ffv1", j("mot.mkv")], deadline, "motion")
    run([tool("ffgac"), "-i", j("mot.mkv"), *GAC, j("mot.avi")], deadline, "motion encode")
    gone(j("mot.mkv"))
    # 3. vectors out, swapped, back in
    run([tool("ffedit"), "-v", "error", "-y", "-i", j("car.avi"), "-f", "mv", "-e", j("car.json")], deadline, "carrier vectors")
    run([tool("ffedit"), "-v", "error", "-y", "-i", j("mot.avi"), "-f", "mv", "-e", j("mot.json")], deadline, "motion vectors")
    gone(j("mot.avi"))
    # the first held frame (fps=30 over `hold` s gives about hold*30 frames; one frame either way is not visible)
    held_from = max(1, min(round(hold * FPS), count_frames(j("car.json")) - 1))
    used = merge(j("car.json"), j("mot.json"), held_from, o["gain"], j("new.json"))
    gone(j("car.json"), j("mot.json"))
    run([tool("ffedit"), "-v", "error", "-y", "-i", j("car.avi"), "-f", "mv", "-a", j("new.json"), "-o", j("moshed.avi")], deadline, "apply")
    gone(j("car.avi"), j("new.json"))
    # 4. the answer: H.264, exactly the held-in frames plus the motion's, with the motion clip's sound lined up
    frames = held_from + used
    cmd = [FFMPEG, "-nostdin", "-v", "error", "-y", "-i", j("moshed.avi")]
    if o["audio"] == "1" and maudio:
        if pic is mot:   # one video: the output timeline is the original's, so its sound fits as it is
            cmd += ["-t", f"{frames / FPS:.3f}", "-i", mot, "-map", "0:v:0", "-map", "1:a:0"]
        else:            # two files: the motion's sound starts where its movement starts
            ms = int(held_from * 1000 / FPS)
            cmd += ["-t", f"{used / FPS:.3f}", "-i", mot, "-map", "0:v:0", "-map", "1:a:0", "-af", f"adelay={ms}:all=1,apad"]
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += ["-frames:v", str(frames), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-map_metadata", "-1", "-movflags", "+faststart", j("out.mp4")]
    run(cmd, deadline, "final encode")
    gone(j("moshed.avi"))
    return W, H


class Handler(BaseHTTPRequestHandler):
    timeout = 60   # a stalled upload cannot hold the job slot forever

    def _send(self, code, body, ctype="text/plain"):
        body = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

    def _early(self, code, text, n):
        """A refusal before the job reads the upload. The body is read and dropped first (when its length is sane): a reply
        sent while the client is still uploading reaches it as a broken pipe, and the gateway then says "off" instead of
        "busy" or "refused" (vidpost does the same)."""
        if 0 < n <= MAX_BYTES:
            left = n
            while left:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    break
                left -= len(chunk)
        else:
            self.close_connection = True
        return self._send(code, text)

    def do_GET(self):
        if urlparse(self.path).path == "/healthz":
            return self._send(200, "ok mosher") if HEALTH["ok"] else self._send(503, "not ready: " + HEALTH["why"])
        self._send(404, "not found")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/mosh":
            return self._send(404, "not found")
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = -1
        # bytes, not str: a non-ASCII header must be a 401, not a TypeError that drops the connection
        got = self.headers.get("Authorization", "").encode("utf-8", "surrogateescape")
        if not TOKEN or not hmac.compare_digest(got, f"Bearer {TOKEN}".encode()):
            return self._early(401, "bad token", length)
        try:
            plen = int(self.headers.get("X-Picture-Length", 0) or 0)
        except ValueError:
            return self._early(400, "bad lengths", length)
        if not 0 < length <= MAX_BYTES:
            return self._early(413, f"body must be 1 byte to {MAX_BYTES // 1048576} MB", length)
        if not 0 <= plen < length:
            return self._early(400, "X-Picture-Length must be smaller than the body", length)
        try:
            o = options(url.query)
        except Bad as e:
            return self._early(400, str(e), length)
        if not SLOTS.acquire(blocking=False):
            return self._early(429, f"busy: {JOBS} mosh job(s) running, retry in a minute", length)
        job = None
        try:
            if shutil.disk_usage(WORK).free < FREE_NEED_MB * 1048576:
                return self._early(507, "no room for a job right now", length)
            job = tempfile.mkdtemp(prefix="mosh-", dir=WORK)
            pic, mot = (os.path.join(job, "pic.bin") if plen else None), os.path.join(job, "mot.bin")
            left = length
            for path, n in ((pic, plen), (mot, length - plen)):
                if not path:
                    continue
                with open(path, "wb") as f:
                    while n:
                        chunk = self.rfile.read(min(n, 1 << 20))
                        if not chunk:
                            return self._send(400, "body ended early")
                        f.write(chunk)
                        n -= len(chunk)
                        left -= len(chunk)
            t0 = time.time()
            w, h = mosh(job, pic, mot, o, t0 + TIMEOUT_S)
            gone(*(p for p in (pic, mot) if p))
            took = time.time() - t0
            out = os.path.join(job, "out.mp4")
            size = os.path.getsize(out)
            print(f"mosh {length / 1048576:.1f} MB -> {size / 1048576:.1f} MB {w}x{h} in {took:.1f}s "
                  f"({'two files' if plen else 'one video'}, {url.query or 'defaults'})", flush=True)
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(size))
            self.send_header("X-Mosh-Seconds", f"{took:.1f}")
            self.send_header("X-Mosh-Size", f"{w}x{h}")
            self.end_headers()
            with open(out, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 1 << 20)
        except Bad as e:
            self._send(400, str(e))
        except (TimeoutError, subprocess.TimeoutExpired):
            self._send(504, f"the job took more than {TIMEOUT_S:.0f}s")
        except Exception as e:   # the message is ours (step name + ffmpeg's last line), never the file names
            print(f"mosh failed: {type(e).__name__}: {str(e)[:200]}", flush=True)
            self._send(500, "mosh failed: " + str(e)[:300])
        finally:
            SLOTS.release()
            if job:
                shutil.rmtree(job, ignore_errors=True)


if __name__ == "__main__":
    os.makedirs(WORK, exist_ok=True)
    self_test()
    if not TOKEN:
        print("mosher: MOSH_TOKEN is not set: every job is refused (401)", flush=True)
    print(f"mosher on :{PORT}, {'ready' if HEALTH['ok'] else 'NOT ready: ' + HEALTH['why']}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
