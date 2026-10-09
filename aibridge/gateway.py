#!/usr/bin/env python3
"""gateway -- one door from Hermes to the machines outside this container (GPU boxes, Claude Code machines).

  gateway status                              which gateways this stack has, and which hosts answer right now
  gateway transcode IN OUT [opt=value ...]    video job on the first GPU host that answers; local ffmpeg if none
  gateway upscale IN OUT                      4x image upscale on a GPU host (no local fallback: says so)
  gateway claude [--host NAME] [TASK]         a task for Claude Code on a machine where it runs (TASK or stdin)
  gateway transcribe FILE [es|ru|en] [--voice] [--out PATH]
                                              speech to text on the first STT host that answers (GPU first);
                                              --voice: GPU, then Groq, then CPU (Hermes voice notes use this)
  gateway bench FILE                          the same audio/video on EVERY host: GPU vs CPU vs Groq, as a table

Transcode options (same closed list as transcoder/server.py): codec=h264|hevc height=N hflip=1 vflip=1 start=S
duration=S cq=15..40 audio=aac|copy|none.

Config: /etc/aibridge/gateways.json, mounted read-only per stack by the operator (never in git: it holds addresses).
  {"transcode": [{"name": "gpu-desktop", "url": "http://<addr>:8610"}, ...],      tried in this order
   "upscale":   [{"name": "gpu-desktop", "url": "http://<addr>:8600"}],
   "stt":       [{"name": "gpu-desktop", "url": "http://<addr>:8620"}, {"name": "stt-cpu", "url": "http://stt-cpu:8620"}],
   "llm":       [{"name": "gpu-desktop", "url": "http://<addr>:8630", "model": "gemma-4-e4b"}],   Hermes's last fallback
   "claude":    [{"name": "claude-box", "ssh_config": "/workdir/.ssh/config"}]}

Every call appends ONE metadata line to /workdir/.gateway-log.jsonl (what ran where, seconds, MB in/out, fallback,
error class), which the operator's telemetry reads to decide which hardware matters. Never the task text or the file
names.
"""
import json, os, subprocess, sys, time, urllib.error, urllib.request

CONF = os.environ.get("GATEWAYS_CONFIG", "/etc/aibridge/gateways.json")
LOG = os.environ.get("GATEWAY_LOG", "/workdir/.gateway-log.jsonl")
TC_KEYS = {"codec", "height", "hflip", "vflip", "start", "duration", "cq", "audio"}


def conf():
    try:
        return json.load(open(CONF))
    except (OSError, ValueError):
        return {}


def log(**kw):
    kw["ts"] = round(time.time(), 1)
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(kw) + "\n")
    except OSError:
        pass


def mb(path):
    try:
        return round(os.path.getsize(path) / 1048576, 1)
    except OSError:
        return None


def healthy(url, timeout=2, path="/healthz"):
    try:
        with urllib.request.urlopen(url.rstrip("/") + path, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def post_file(url, path, out, timeout=1900):
    req = urllib.request.Request(url, data=open(path, "rb"), method="POST",
                                 headers={"Content-Length": str(os.path.getsize(path)),
                                          "Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(out, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
        return r.headers.get("X-Encode-Seconds")


def local_ffmpeg_args(o):
    """The CPU equivalent of the GPU options (x264/x265 quality chosen to give a similar size)."""
    pre, args, vf = [], [], []
    if "start" in o:
        pre += ["-ss", str(float(o["start"]))]
    if "duration" in o:
        args += ["-t", str(float(o["duration"]))]
    if "height" in o:
        vf.append(f"scale=-2:{int(o['height'])}")
    if o.get("hflip") == "1":
        vf.append("hflip")
    if o.get("vflip") == "1":
        vf.append("vflip")
    crf = str(int(o.get("cq", "28")) - 5)
    args += (["-c:v", "libx265", "-preset", "fast", "-crf", crf] if o.get("codec") == "hevc"
             else ["-c:v", "libx264", "-preset", "veryfast", "-crf", crf])
    if vf:
        args += ["-vf", ",".join(vf)]
    a = o.get("audio", "aac")
    args += ["-an"] if a == "none" else ["-c:a", "copy"] if a == "copy" else ["-c:a", "aac", "-b:a", "160k"]
    return pre, args + ["-movflags", "+faststart"]


def cmd_transcode(argv):
    if len(argv) < 2:
        sys.exit("usage: gateway transcode IN OUT [opt=value ...]")
    src, out = argv[0], argv[1]
    opts = dict(a.split("=", 1) for a in argv[2:])
    bad = set(opts) - TC_KEYS
    if bad:
        sys.exit(f"unknown option(s): {', '.join(sorted(bad))}; allowed: {', '.join(sorted(TC_KEYS))}")
    query = "&".join(f"{k}={v}" for k, v in opts.items())
    t0 = time.time()
    tried = []
    for h in conf().get("transcode", []):
        if not healthy(h["url"]):
            tried.append(h["name"])
            continue
        try:
            gpu_s = post_file(h["url"].rstrip("/") + "/transcode?" + query, src, out)
            took = time.time() - t0
            log(gateway="transcode", host=h["name"], ok=True, fallback=False, seconds=round(took, 1),
                gpu_seconds=float(gpu_s) if gpu_s else None, mb_in=mb(src), mb_out=mb(out), down=tried)
            print(f"done on {h['name']} (GPU) in {took:.1f}s -> {out}")
            return 0
        except urllib.error.HTTPError as e:
            if e.code == 400:   # our options are wrong: no point trying elsewhere
                log(gateway="transcode", host=h["name"], ok=False, error="bad_options", seconds=round(time.time() - t0, 1))
                sys.exit(f"{h['name']} rejected the options: {e.read(300).decode('utf-8', 'replace')}")
            tried.append(f"{h['name']}:{e.code}")
        except Exception as e:
            tried.append(f"{h['name']}:{type(e).__name__}")
    pre, args = local_ffmpeg_args(opts)
    t1 = time.time()
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *pre, "-i", src, *args, out])
    took = time.time() - t0
    log(gateway="transcode", host="local-cpu", ok=r.returncode == 0, fallback=True, seconds=round(took, 1),
        cpu_seconds=round(time.time() - t1, 1), mb_in=mb(src), mb_out=mb(out), down=tried,
        error=None if r.returncode == 0 else "ffmpeg")
    why = f"no GPU host answered ({', '.join(tried)})" if tried else "no GPU host configured"
    print(f"{'done' if r.returncode == 0 else 'FAILED'} on this container's CPU in {took:.1f}s: {why}")
    return r.returncode


def cmd_upscale(argv):
    if len(argv) != 2:
        sys.exit("usage: gateway upscale IN OUT")
    t0, tried = time.time(), []
    for h in conf().get("upscale", []):
        if not healthy(h["url"]):
            tried.append(h["name"])
            continue
        try:
            post_file(h["url"].rstrip("/") + "/upscale", argv[0], argv[1], timeout=300)
            log(gateway="upscale", host=h["name"], ok=True, seconds=round(time.time() - t0, 1), mb_in=mb(argv[0]),
                mb_out=mb(argv[1]), down=tried)
            print(f"done on {h['name']} -> {argv[1]}")
            return 0
        except Exception as e:
            tried.append(f"{h['name']}:{type(e).__name__}")
    log(gateway="upscale", host=None, ok=False, error="no_host", seconds=round(time.time() - t0, 1), down=tried)
    print(f"no upscale host available ({', '.join(tried) or 'none configured'}): tell the person, no local fallback")
    return 3


CLAUDE_ERRORS = (("auth", ("Not logged in", "Login: Expired", "auth login", "Invalid API key", "OAuth")),
                 ("key", ("Permission denied",)),
                 ("unreachable", ("Connection refused", "timed out", "No route to host", "Could not resolve")))


def cmd_claude(argv):
    hosts = conf().get("claude", [])
    if argv[:1] == ["--host"]:
        hosts = [h for h in hosts if h["name"] == argv[1]]
        argv = argv[2:]
    if not hosts:
        sys.exit("no Claude machine configured for this person")
    task = " ".join(argv) if argv else sys.stdin.read()
    if not task.strip():
        sys.exit("empty task")
    h = hosts[0]
    t0 = time.time()
    try:
        r = subprocess.run(["ssh", "-F", h.get("ssh_config", "/workdir/.ssh/config"), h["name"]], input=task, text=True,
                           capture_output=True, timeout=int(h.get("timeout", 900)))
        err = next((cls for cls, keys in CLAUDE_ERRORS if any(k in (r.stderr + r.stdout) for k in keys)), None) \
            if r.returncode else None
        ok = r.returncode == 0
    except subprocess.TimeoutExpired:
        r, ok, err = None, False, "timeout"
    took = time.time() - t0
    log(gateway="claude", host=h["name"], ok=ok, seconds=round(took, 1), error=err if not ok else None,
        chars_in=len(task), chars_out=len(r.stdout) if r else 0)
    if r is not None:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
    if not ok:
        print(f"\n[gateway] Claude on {h['name']} failed ({err or 'exit ' + str(r.returncode if r else '?')}) after {took:.0f}s",
              file=sys.stderr)
    return 0 if ok else 4


def stt_call(url, path, lang="auto", timeout=1800):
    req = urllib.request.Request(url.rstrip("/") + f"/transcribe?lang={lang}", data=open(path, "rb"), method="POST",
                                 headers={"Content-Length": str(os.path.getsize(path)),
                                          "Content-Type": "application/octet-stream"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    d["wall"] = round(time.time() - t, 1)
    return d


def cmd_transcribe(argv):
    """Plain: every STT host in order. --voice (Hermes voice notes): fast hosts, then Groq, then slow CPU hosts
    (local first for privacy; Groq only when no GPU answers, a CPU host only when Groq fails too: it runs at ~0.5x).
    --out PATH writes the text there (Hermes command provider) instead of stdout."""
    voice = "--voice" in argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--out")]
    if not pos:
        sys.exit("usage: gateway transcribe FILE [es|ru|en] [--voice] [--out PATH]")
    path, lang = pos[0], pos[1] if len(pos) > 1 else "auto"
    hosts = conf().get("stt", [])
    if voice:
        hosts = [h for h in hosts if not h.get("slow")] + [{"name": "groq"}] + [h for h in hosts if h.get("slow")]
    tried = []
    for h in hosts:
        try:
            if h["name"] == "groq":
                key = groq_key()
                if not key:
                    tried.append("groq:no_key")
                    continue
                d = groq_stt(path, key)
            elif not healthy(h["url"]):
                tried.append(h["name"])
                continue
            else:
                d = stt_call(h["url"], path, lang, timeout=120 if voice and not h.get("slow") else 1800)
        except Exception as e:
            tried.append(f"{h['name']}:{type(e).__name__}")
            continue
        log(gateway="stt", host=h["name"], ok=True, seconds=d["wall"], audio_seconds=d.get("audio_seconds"),
            device=d.get("device"), language=d.get("language"), mb_in=mb(path), down=tried,
            mode="voice" if voice else "tool")
        if out:
            with open(out, "w") as f:
                f.write(d["text"])
        else:
            print(d["text"])
        print(f"\n[{h['name']} {d.get('device')}: {d['wall']}s for {d.get('audio_seconds')}s of audio, {d.get('language')}]",
              file=sys.stderr)
        return 0
    log(gateway="stt", host=None, ok=False, error="no_host", down=tried, mode="voice" if voice else "tool")
    print(f"no speech-to-text host answered ({', '.join(tried) or 'none configured'})", file=sys.stderr)
    return 3


def groq_key():
    k = os.environ.get("GROQ_API_KEY", "")
    for env in (os.path.join(os.environ.get("HERMES_HOME", "/root/.hermes"), ".env"), "/root/.hermes/.env"):
        if k:
            break
        try:
            for line in open(env):
                if line.startswith("GROQ_API_KEY="):
                    k = line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    return k


def groq_stt(path, key):
    """Groq whisper-large-v3-turbo (the cloud STT Hermes uses for voice notes), for comparison. Video goes as its audio."""
    src = path
    if has_video(path):
        src = path + ".bench.ogg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vn", "-c:a", "libopus", "-b:a", "48k", src], check=True)
    boundary = "----gw" + str(int(time.time() * 1000))
    body = io_multipart(boundary, {"model": "whisper-large-v3-turbo", "response_format": "verbose_json"},
                        os.path.basename(src), open(src, "rb").read())
    req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "User-Agent": "bridgeai-gateway/1.0",
                                          # Cloudflare in front of Groq answers 403 "error code: 1010" to Python-urllib
                                          "Content-Type": f"multipart/form-data; boundary={boundary}"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
    finally:
        if src != path:
            os.unlink(src)
    return {"text": d.get("text", "").strip(), "language": d.get("language"), "wall": round(time.time() - t, 1),
            "audio_seconds": d.get("duration"), "device": "cloud"}


def io_multipart(boundary, fields, filename, data):
    out = b""
    for k, v in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return out


def has_video(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=codec_name",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return bool(r.stdout.strip()) and "png" not in r.stdout and "mjpeg" not in r.stdout   # cover art is not video


def cmd_bench(argv):
    """Same file through every host. Prints a table; logs only timings. The transcripts are shown, never stored."""
    import difflib
    if not argv:
        sys.exit("usage: gateway bench FILE")
    path = argv[0]
    rows, texts = [], []
    for h in conf().get("stt", []):
        if not healthy(h["url"], timeout=3):
            rows.append((f"STT {h['name']}", "apagado", "", "", ""))
            continue
        try:
            d = stt_call(h["url"], path)
        except Exception as e:
            rows.append((f"STT {h['name']}", f"error {type(e).__name__}", "", "", ""))
            continue
        texts.append(d["text"])
        rt = f"{d['audio_seconds'] / d['wall']:.1f}x" if d.get("audio_seconds") and d["wall"] else ""
        rows.append((f"STT {h['name']} ({d.get('device')})", f"{d['wall']} s", rt, d.get("language", ""), d["text"]))
        log(gateway="bench-stt", host=h["name"], ok=True, seconds=d["wall"], audio_seconds=d.get("audio_seconds"),
            device=d.get("device"), mb_in=mb(path))
    key = groq_key()
    if key:
        try:
            d = groq_stt(path, key)
            texts.append(d["text"])
            rt = f"{d['audio_seconds'] / d['wall']:.1f}x" if d.get("audio_seconds") and d["wall"] else ""
            rows.append(("STT Groq (nube)", f"{d['wall']} s", rt, d.get("language", ""), d["text"]))
            log(gateway="bench-stt", host="groq", ok=True, seconds=d["wall"], audio_seconds=d.get("audio_seconds"),
                device="cloud", mb_in=mb(path))
        except Exception as e:
            rows.append(("STT Groq (nube)", f"error {type(e).__name__}", "", "", ""))
    if has_video(path):
        out_gpu, out_cpu = path + ".bench-gpu.mp4", path + ".bench-cpu.mp4"
        for h in conf().get("transcode", []):
            if healthy(h["url"]):
                t = time.time()
                try:
                    post_file(h["url"].rstrip("/") + "/transcode?height=720", path, out_gpu)
                    took = round(time.time() - t, 1)
                    rows.append((f"Video 720p {h['name']} (GPU)", f"{took} s", "", "", f"{mb(out_gpu)} MB"))
                    log(gateway="bench-transcode", host=h["name"], ok=True, seconds=took, mb_in=mb(path), mb_out=mb(out_gpu))
                except Exception as e:
                    rows.append((f"Video 720p {h['name']} (GPU)", f"error {type(e).__name__}", "", "", ""))
                break
        pre, args = local_ffmpeg_args({"height": "720"})
        t = time.time()
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", *pre, "-i", path, *args, out_cpu])
        took = round(time.time() - t, 1)
        rows.append(("Video 720p este servidor (CPU)", f"{took} s" if r.returncode == 0 else "error", "", "", f"{mb(out_cpu)} MB"))
        log(gateway="bench-transcode", host="local-cpu", ok=r.returncode == 0, seconds=took, mb_in=mb(path), mb_out=mb(out_cpu))
        for f in (out_gpu, out_cpu):
            if os.path.exists(f):
                os.unlink(f)
    print("| prueba | tiempo | velocidad (x tiempo real) | idioma | resultado |")
    print("|---|---|---|---|---|")
    for name, secs, rt, lang, res in rows:
        print(f"| {name} | {secs} | {rt} | {lang} | {res[:120].replace('|', '/')}{'…' if len(res) > 120 else ''} |")
    if len(texts) > 1:
        import re
        words = lambda s: re.findall(r"\w+", s.lower())   # word level, punctuation and case ignored
        ref = words(texts[0])
        sims = [f"{difflib.SequenceMatcher(None, ref, words(x), autojunk=False).ratio() * 100:.0f}%" for x in texts[1:]]
        print("\nParecido de los textos con el primero: " + ", ".join(sims))
    return 0


def cmd_status(_):
    c = conf()
    if not c:
        print("no gateways configured for this stack")
        return 0
    for kind in ("transcode", "upscale"):
        for h in c.get(kind, []):
            print(f"{kind:9} {h['name']:16} {'UP' if healthy(h['url']) else 'down'}")
    for h in c.get("stt", []):
        print(f"{'stt':9} {h['name']:16} {'UP' if healthy(h['url']) else 'down'}")
    for h in c.get("llm", []):       # llama.cpp answers /health, not /healthz; Hermes uses it as its last fallback
        print(f"{'llm':9} {h['name']:16} {'UP' if healthy(h['url'], path='/health') else 'down'}  ({h.get('model')})")
    for h in c.get("claude", []):
        print(f"{'claude':9} {h['name']:16} configured (checked on use)")
    return 0


def main():
    cmds = {"status": cmd_status, "transcode": cmd_transcode, "upscale": cmd_upscale, "claude": cmd_claude,
            "transcribe": cmd_transcribe, "bench": cmd_bench}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        return 2
    return cmds[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
