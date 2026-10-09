#!/usr/bin/env python3
"""gateway -- one door from Hermes to the machines outside this container (GPU boxes, Claude Code machines).

  gateway status                              which gateways this stack has, and which hosts answer right now
  gateway transcode IN OUT [opt=value ...]    video job on the first GPU host that answers; local ffmpeg if none
  gateway upscale IN OUT                      4x image upscale on a GPU host (no local fallback: says so)
  gateway claude [--host NAME] [TASK]         a task for Claude Code on a machine where it runs (TASK or stdin)

Transcode options (same closed list as transcoder/server.py): codec=h264|hevc height=N hflip=1 vflip=1 start=S
duration=S cq=15..40 audio=aac|copy|none.

Config: /etc/aibridge/gateways.json, mounted read-only per stack by the operator (never in git: it holds addresses).
  {"transcode": [{"name": "gpu-desktop", "url": "http://<addr>:8610"}, ...],      tried in this order
   "upscale":   [{"name": "gpu-desktop", "url": "http://<addr>:8600"}],
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


def healthy(url, timeout=2):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/healthz", timeout=timeout) as r:
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


def cmd_status(_):
    c = conf()
    if not c:
        print("no gateways configured for this stack")
        return 0
    for kind in ("transcode", "upscale"):
        for h in c.get(kind, []):
            print(f"{kind:9} {h['name']:16} {'UP' if healthy(h['url']) else 'down'}")
    for h in c.get("claude", []):
        print(f"{'claude':9} {h['name']:16} configured (checked on use)")
    return 0


def main():
    cmds = {"status": cmd_status, "transcode": cmd_transcode, "upscale": cmd_upscale, "claude": cmd_claude}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        return 2
    return cmds[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
