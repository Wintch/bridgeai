#!/usr/bin/env python3
"""Offline checks for place.py with a fake docker. Run: python3 -I place_selftest.py"""
import os, stat, subprocess, sys, tempfile
import atexit as _a, shutil as _s
tmp = tempfile.mkdtemp(prefix="selftest-"); _a.register(_s.rmtree, tmp, True)
HERE = os.path.dirname(os.path.abspath(__file__))
fake = os.path.join(tmp, "docker"); log = os.path.join(tmp, "calls.txt")
open(fake, "w").write('#!/bin/sh\necho "$@" >> ' + log + '\n[ "$1" = "create" ] && [ -n "$FAKE_FAIL" ] && { echo boom >&2; exit 1; }\n[ "$1" = "inspect" ] && { echo exited; }\nexit 0\n')
os.chmod(fake, 0o755)
root = os.path.join(tmp, "places"); os.makedirs(root)
env = dict(os.environ, PLACES_ROOT=root, DOCKER=fake, PLACE_BIND="10.9.8.7", TZ="UTC")
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def run(*args, e=None):
    return subprocess.run([sys.executable, "-I", os.path.join(HERE, "place.py"), *args], capture_output=True, text=True, env=e or env)


r = run("create", "hermic")
calls = open(log).read().splitlines()
check("create makes the container and says it is not started", r.returncode == 0 and "created, not started" in r.stdout and calls[0].startswith("create --name place-hermic-desktop"), r.stdout + r.stderr)
c = calls[0]
check("ports bound to the one LAN address only, 3010 -> 3000 and 3011 -> 3001", "-p 10.9.8.7:3010:3000" in c and "-p 10.9.8.7:3011:3001" in c and "0.0.0.0" not in c, c)
check("no-new-privileges, 1 GB shm, restart no, English locale, the volumes", all(x in c for x in ("no-new-privileges", "--shm-size 1gb", "--restart no", "LC_ALL=en_US.UTF-8", "LANG=en_US.UTF-8", "/hermic/desktop:/config", "/hermic/input:/input", "/hermic/output:/output")), c)
check("no GPU runtime unless asked", "nvidia" not in c, c)
envf = os.path.join(root, "hermic", ".desktop.env")
body = open(envf).read()
check("credentials file is 0600 and holds a long password", stat.S_IMODE(os.stat(envf).st_mode) == 0o600 and len(body.split("PASSWORD=")[1].strip()) >= 24, body[:30])
pw = body.split("PASSWORD=")[1].strip()
check("the password is never printed, nor passed on the command line", pw not in r.stdout + r.stderr + c, "")
check("the env file is handed to docker by path", f"--env-file {envf}" in c, c)
r = run("create", "hermic")
check("creating the same place twice is refused and changes nothing", r.returncode == 3 and "already has a place" in r.stderr, r.stderr)
r = run("create", "herstr", "--gpu")
c2 = open(log).read().splitlines()[-1]
check("the next place takes the next pair of ports, and --gpu adds the NVIDIA runtime", "-p 10.9.8.7:3020:3000" in c2 and "--runtime nvidia" in c2, c2)
for bad in ("Bad", "a", "x" * 25, "../x", "1abc", "a b"):
    check(f"a name like {bad!r} is refused", run("create", bad).returncode == 2)
r = run("create", "other", e=dict(env, PLACE_BIND="8.8.8.8"))
check("a public address is refused for the ports", r.returncode == 2 and "private LAN address" in r.stderr, r.stderr)
r = run("create", "other", e=dict(env, PLACE_BIND="0.0.0.0"))
check("0.0.0.0 is refused too", r.returncode == 2, r.stderr)
r = run("create", "other", e=dict(env, FAKE_FAIL="1"))
check("a docker failure is reported and nothing is called a success", r.returncode == 1 and "could not create" in r.stderr and "created" not in r.stdout, r.stdout + r.stderr)
r = run("creds", "hermic")
check("creds prints the path, not the password", r.stdout.strip() == envf and pw not in r.stdout, r.stdout)
check("start and stop call docker on that container only", run("start", "hermic").returncode == 0 and run("stop", "hermic").returncode == 0 and "start place-hermic-desktop" in open(log).read() and "stop place-hermic-desktop" in open(log).read())
check("status prints docker's state", run("status", "hermic").stdout.strip() == "exited")
r = run("rm", "hermic")
check("rm removes the container and leaves the person's folder", "left" in r.stdout and os.path.isdir(os.path.join(root, "hermic", "desktop")), r.stdout)
bd = os.path.join(tmp, "rb"); os.makedirs(bd)
rr = lambda d: subprocess.run(["bash", os.path.join(HERE, "build-resolve.sh"), d], capture_output=True, text=True)
check("build-resolve.sh without a folder: usage, rc 2", rr(os.path.join(tmp, "nope")).returncode == 2)
check("build-resolve.sh with an empty folder: asks for the zip, rc 2", (lambda r: r.returncode == 2 and "no DaVinci_Resolve" in r.stderr)(rr(bd)))
open(os.path.join(bd, "DaVinci_Resolve_Studio_21.2_Linux.zip"), "w").write("x")
r = rr(bd)
check("build-resolve.sh refuses a Studio file: its licence is a USB key tied to one host, rc 3", r.returncode == 3 and "Studio" in r.stderr, r.stderr)
os.remove(os.path.join(bd, "DaVinci_Resolve_Studio_21.2_Linux.zip")); open(os.path.join(bd, "DaVinci_Resolve_21.2_Linux.zip"), "w").write("x")
r = rr(bd)
check("build-resolve.sh with the free zip but no makeresolvedeb: asks for it, rc 2", r.returncode == 2 and "makeresolvedeb" in r.stderr, r.stderr)
import shutil as _sh
if _sh.which("ffmpeg") and _sh.which("ffprobe"):
    w = os.path.join(tmp, "media"); os.makedirs(w)
    src = os.path.join(w, "game.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=3", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src], check=True)
    probe = lambda f: subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", f], capture_output=True, text=True).stdout.split()
    sh = lambda *a: subprocess.run(["sh", *a], capture_output=True, text=True)
    r = sh(os.path.join(HERE, "bin", "to-resolve"), src, os.path.join(w, "full.mov"))
    check("to-resolve (default): DNxHR video and PCM audio, nothing AAC left", r.returncode == 0 and probe(os.path.join(w, "full.mov")) == ["dnxhd", "pcm_s16le"], (r.stderr[-200:], probe(os.path.join(w, "full.mov"))))
    r = sh(os.path.join(HERE, "bin", "to-resolve"), "--audio", src, os.path.join(w, "aud.mov"))
    check("to-resolve --audio: the video is copied untouched, only the sound becomes PCM", r.returncode == 0 and probe(os.path.join(w, "aud.mov")) == ["h264", "pcm_s16le"], (r.stderr[-200:], probe(os.path.join(w, "aud.mov"))))
    r = sh(os.path.join(HERE, "bin", "to-resolve"), os.path.join(w, "nope.mp4"))
    check("to-resolve with a missing file: usage, rc 2", r.returncode == 2)
    r = sh(os.path.join(HERE, "bin", "to-resolve"), src, src)
    check("to-resolve refuses to overwrite its input", r.returncode == 2 and "differ" in r.stderr, r.stderr)
    r = sh(os.path.join(HERE, "bin", "from-resolve"), os.path.join(w, "full.mov"), os.path.join(w, "back.mp4"))
    check("from-resolve: H.264 + AAC mp4 back from the intermediate", r.returncode == 0 and probe(os.path.join(w, "back.mp4")) == ["h264", "aac"], (r.stderr[-200:], probe(os.path.join(w, "back.mp4"))))
    r = sh(os.path.join(HERE, "bin", "from-resolve"), "--max-mb", "1", os.path.join(w, "full.mov"), os.path.join(w, "small.mp4"))
    check("from-resolve --max-mb: the result fits the size asked", r.returncode == 0 and os.path.getsize(os.path.join(w, "small.mp4")) < 1_048_576, os.path.getsize(os.path.join(w, "small.mp4")) if os.path.exists(os.path.join(w, "small.mp4")) else r.stderr)
    r = sh(os.path.join(HERE, "bin", "from-resolve"), "--max-mb", "0", os.path.join(w, "full.mov"))
    check("from-resolve: a size that cannot hold a watchable video is refused, rc 3 (or a bad number rc 2)", r.returncode in (2, 3), r.returncode)
    r = sh(os.path.join(HERE, "bin", "from-resolve"), "--max-mb", "abc", os.path.join(w, "full.mov"))
    check("from-resolve: a non-numeric size is rc 2", r.returncode == 2, r.returncode)
else:
    print("skip to-resolve / from-resolve tests: no ffmpeg here")
print("place_selftest: " + ("FAILED: " + ", ".join(fails) if fails else "all ok"))
sys.exit(1 if fails else 0)
