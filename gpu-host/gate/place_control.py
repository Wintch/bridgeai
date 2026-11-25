"""place_control: start, stop and watch the desktop places (gpu-host/places/place.py) from the gate.

A place is one container per person (`place-NAME-desktop`) with its own folder. The gate opens one on the person's request and closes it by itself
after PLACE_IDLE_S (30 min) without anybody using it, with a warning PLACE_WARN_S (10 min) before. Isolation is by token: every place has its own
`.gate.token` (the person's stack keeps it) and the gate holds only its sha256 (`.gate.hash`), so a token opens, closes and reads ONE place and nothing
else, never another person's and never the host's games or power (those use the host token). Nothing here reads a person's files: only the hash files, the
`.ports` file and docker's own state.

"In use" means somebody touched the screen in the last minute (the X server's idle time, asked inside the container) OR the container is working hard
(CPU at or above PLACE_BUSY_CPU %, a render with nobody at the keyboard). An open tab nobody touches is not use. Stdlib only; `run` and `now` are
injected so the selftest needs no docker.
"""
import csv
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET

ROOT = os.environ.get("PLACES_ROOT", "/srv/bridgeai/places")
NAME_OK = re.compile(r"[a-z][a-z0-9]{1,19}")
PROBE = (
    "import ctypes, sys\n"
    "class I(ctypes.Structure):\n"
    "    _fields_ = [('w', ctypes.c_ulong), ('s', ctypes.c_int), ('k', ctypes.c_int), ('t', ctypes.c_ulong), ('idle', ctypes.c_ulong), ('m', ctypes.c_ulong)]\n"
    "x = ctypes.CDLL('libX11.so.6'); s = ctypes.CDLL('libXss.so.1')\n"
    "x.XOpenDisplay.restype = ctypes.c_void_p; x.XDefaultRootWindow.restype = ctypes.c_ulong\n"
    "s.XScreenSaverAllocInfo.restype = ctypes.POINTER(I)\n"
    "d = x.XOpenDisplay(None)\n"
    "if not d: sys.exit(3)\n"
    "i = s.XScreenSaverAllocInfo()\n"
    "if not s.XScreenSaverQueryInfo(ctypes.c_void_p(d), ctypes.c_ulong(x.XDefaultRootWindow(ctypes.c_void_p(d))), i): sys.exit(4)\n"
    "print(i.contents.idle // 1000)\n")

# ---- files in and out (only NAME/input and NAME/output, never NAME/desktop)
FILE_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ ()+,@=-]{0,150}")      # one path component a person's file may have; no slash, no leading dot or dash
AREAS = ("input", "output")
MAX_FILE = int(os.environ.get("PLACE_MAX_FILE", str(1_900_000_000)))   # bytes: under the 2000 MB of the local Bot API
MIN_FREE = int(os.environ.get("PLACE_MIN_FREE", str(8_000_000_000)))   # an upload leaves at least this much free (Resolve intermediates are big)
LIST_MAX, LIST_DEPTH = 300, 3
TIERS = ("lb", "sq", "hq", "hqx", "444")


METRICS_COLUMNS = ["ts", "place", "in_use", "idle_s", "cpu_pct", "mem_mb", "net_tx_kbps", "place_vram_mb", "gpu_sm_pct", "gpu_enc_pct", "gpu_dec_pct",
                   "gpu_vram_used_mb", "gpu_vram_total_mb", "gpu_power_w", "gpu_temp_c", "places_running", "load1"]
METRICS_MAX = 5_000_000                       # bytes; past this the file moves to .1 (one older generation is kept)
_SIZES = {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3}


def to_bytes(text):
    m = re.fullmatch(r"\s*([\d.]+)\s*([A-Za-z]+)\s*", text or "")
    return float(m.group(1)) * _SIZES.get(m.group(2).lower(), 0) if m else 0.0


def gpu_snapshot(xml_text):
    """From `nvidia-smi -q -x`: card totals and the memory each process (graphics and compute) holds, by pid. {} when the text is not that XML."""
    try:
        g = ET.fromstring(xml_text).find("gpu")
        num = lambda path: float(re.match(r"[\d.]+", g.findtext(path) or "0").group(0)) if re.match(r"[\d.]+", g.findtext(path) or "") else 0.0
        procs = {}
        for p in g.findall("processes/process_info"):
            try:
                procs[int(p.findtext("pid"))] = procs.get(int(p.findtext("pid")), 0.0) + num_of(p.findtext("used_memory"))
            except (TypeError, ValueError):
                pass
        return {"sm": num("utilization/gpu_util"), "enc": num("utilization/encoder_util"), "dec": num("utilization/decoder_util"),
                "used": num("fb_memory_usage/used"), "total": num("fb_memory_usage/total"), "power": num("gpu_power_readings/instant_power_draw") or num("gpu_power_readings/power_draw"),
                "temp": num("temperature/gpu_temp"), "procs": procs}
    except (ET.ParseError, AttributeError, TypeError):
        return {}


def num_of(text):
    m = re.match(r"[\d.]+", text or "")
    return float(m.group(0)) if m else 0.0


def hash_of(token):
    return hashlib.sha256(token.encode()).hexdigest()


def container(name):
    return f"place-{name}-desktop"


class Places:
    def __init__(self, root=None, state_path=None, run=None, now=None, idle_s=None, warn_s=None, busy_cpu=None, active_s=None):
        self.root = root or ROOT
        self.state_path = state_path or os.path.join(os.path.expanduser("~"), ".local", "state", "bridgeai-gate", "places.json")
        self.run = run or self._run
        self.now = now or time.time
        self.idle_s = float(os.environ.get("PLACE_IDLE_S", "1800")) if idle_s is None else idle_s
        self.warn_s = float(os.environ.get("PLACE_WARN_S", "600")) if warn_s is None else warn_s
        self.busy_cpu = float(os.environ.get("PLACE_BUSY_CPU", "80")) if busy_cpu is None else busy_cpu
        self.active_s = float(os.environ.get("PLACE_ACTIVE_S", "90")) if active_s is None else active_s    # touched within this many seconds = in use now
        self.lock = threading.Lock()

    # ---- docker, the only thing touched
    @staticmethod
    def _run(argv, stdin=None, timeout=30):
        try:
            r = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout
        except (OSError, subprocess.SubprocessError):
            return 1, ""

    def docker(self, *args, stdin=None, timeout=30):
        return self.run(["docker", *args], stdin=stdin, timeout=timeout)

    # ---- who is who
    def find_by_token(self, token):
        """The place whose hash matches (constant time over all of them), or None. An empty or odd token matches nothing."""
        if not isinstance(token, str) or not 20 <= len(token) <= 200:
            return None
        want, found = hash_of(token), None
        try:
            names = sorted(os.listdir(self.root))
        except OSError:
            return None
        for n in names:
            if not NAME_OK.fullmatch(n):
                continue
            try:
                with open(os.path.join(self.root, n, ".gate.hash")) as f:
                    have = f.read().strip()
            except OSError:
                continue
            if hmac.compare_digest(have.encode(), want.encode()):
                found = n
        return found

    def names(self):
        out = []
        try:
            for n in sorted(os.listdir(self.root)):
                if NAME_OK.fullmatch(n) and os.path.exists(os.path.join(self.root, n, ".gate.hash")):
                    out.append(n)
        except OSError:
            pass
        return out

    # ---- state kept between ticks
    def load(self):
        try:
            with open(self.state_path) as f:
                v = json.load(f)
            return v if isinstance(v, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, st):
        d = os.path.dirname(self.state_path)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".places-")
        with os.fdopen(fd, "w") as f:
            json.dump(st, f)
        os.replace(tmp, self.state_path)

    def container_state(self, name):
        rc, out = self.docker("inspect", "-f", "{{.State.Status}}", container(name))
        return out.strip() if rc == 0 and out.strip() else "missing"

    def urls(self, name):
        rc, out = self.docker("inspect", "-f", "{{json .HostConfig.PortBindings}}", container(name))
        try:
            b = json.loads(out)
            ip = b["3000/tcp"][0]["HostIp"]
            return {"http": f"http://{ip}:{b['3000/tcp'][0]['HostPort']}", "https": f"https://{ip}:{b['3001/tcp'][0]['HostPort']}"}
        except (ValueError, KeyError, IndexError, TypeError):
            return {}

    def running_count(self):
        return sum(1 for n in self.names() if self.container_state(n) == "running")

    def info(self, name):
        st = self.load().get(name, {})
        cs = self.container_state(name)
        now = self.now()
        running = cs == "running"
        out = {"place": name, "state": cs, "running": running, "urls": self.urls(name) if cs != "missing" else {},
               "idle_limit_min": round(self.idle_s / 60), "warn_min": round(self.warn_s / 60)}
        if running:
            idle = max(0, now - float(st.get("last_active", now)))
            out["idle_min"] = int(idle // 60)
            out["closes_in_min"] = max(0, int((self.idle_s - idle) // 60))
            out["others_running"] = max(0, self.running_count() - 1)   # a count only: never who
        for k in ("warned_at", "closed_at", "closed_reason", "opened_at"):
            if st.get(k):
                out[k] = st[k]
        return out

    # ---- the person's requests
    def _mark(self, name, **kv):
        with self.lock:
            st = self.load()
            e = st.setdefault(name, {})
            for k, v in kv.items():
                if v is None:
                    e.pop(k, None)
                else:
                    e[k] = v
            self.save(st)

    def start(self, name):
        cs = self.container_state(name)
        if cs == "missing":
            return 404, {"why": "no_such_place"}
        now = int(self.now())
        if cs != "running":
            rc, _ = self.docker("start", container(name), timeout=120)
            if rc != 0:
                return 502, {"why": "start_failed"}
            self._mark(name, opened_at=now, last_active=now, warned_at=None, closed_at=None, closed_reason=None)
        else:
            self._mark(name, last_active=now, warned_at=None)
        return 200, self.info(name)

    def stop(self, name, reason="person"):
        cs = self.container_state(name)
        if cs == "missing":
            return 404, {"why": "no_such_place"}
        if cs == "running":
            rc, _ = self.docker("stop", "-t", "20", container(name), timeout=60)
            if rc != 0:
                return 502, {"why": "stop_failed"}
            self._mark(name, closed_at=int(self.now()), closed_reason=reason, warned_at=None)
        return 200, self.info(name)

    def keep(self, name):
        if self.container_state(name) != "running":
            return 409, {"why": "not_running"}
        self._mark(name, last_active=int(self.now()), warned_at=None)
        return 200, self.info(name)

    # ---- files in and out. The person's own container writes into `output` and can plant a symbolic link there: the gate runs as the host user and could be
    # made to read the host's own files through it. So every step goes through a directory fd with O_NOFOLLOW; a link, a device, a pipe is never opened.
    @staticmethod
    def rel_ok(rel):
        if not isinstance(rel, str) or not rel or len(rel) > 400:
            return None
        parts = rel.split("/")
        if len(parts) > LIST_DEPTH or any(not FILE_PART.fullmatch(x) or x.endswith(".part") or ".part." in x for x in parts):
            return None
        return parts

    def _area_fd(self, name, area):
        """An fd of NAME/input or NAME/output, opened without following links, or None."""
        if area not in AREAS or not NAME_OK.fullmatch(name or ""):
            return None
        try:
            return os.open(os.path.join(self.root, name, area), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            return None

    def _walk(self, fd, parts):
        """Opens the directories of `parts[:-1]` under fd one at a time without following links; (dir fd, last name) or (None, None). The caller closes the fd."""
        cur = os.dup(fd)
        try:
            for x in parts[:-1]:
                nxt = os.open(x, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=cur)
                os.close(cur)
                cur = nxt
            return cur, parts[-1]
        except OSError:
            os.close(cur)
            return None, None

    def listing(self, name, area):
        """[{name, size, mtime}] of regular files under the area (links, devices and the unfinished `.part` files are not shown), newest first, capped."""
        fd = self._area_fd(name, area)
        if fd is None:
            return None
        out, working = [], 0

        def go(dfd, prefix, depth):
            nonlocal working
            try:
                with os.scandir(dfd) as it:
                    entries = sorted(it, key=lambda e: e.name)
            except OSError:
                return
            for e in entries:
                if len(out) >= LIST_MAX or not FILE_PART.fullmatch(e.name):
                    continue
                try:
                    if e.is_symlink():
                        continue
                    if e.is_dir(follow_symlinks=False):
                        if depth + 1 < LIST_DEPTH:
                            sub = os.open(e.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dfd)
                            try:
                                go(sub, prefix + e.name + "/", depth + 1)
                            finally:
                                os.close(sub)
                    elif e.is_file(follow_symlinks=False):
                        if ".part" in e.name:
                            working += 1
                            continue
                        st = e.stat(follow_symlinks=False)
                        out.append({"name": prefix + e.name, "size": st.st_size, "mtime": int(st.st_mtime)})
                except OSError:
                    continue
        try:
            go(fd, "", 0)
        finally:
            os.close(fd)
        out.sort(key=lambda x: -x["mtime"])
        return out, working

    def files(self, name):
        got = {a: self.listing(name, a) for a in AREAS}
        if any(v is None for v in got.values()):
            return 404, {"why": "no_such_place"}
        return 200, {"input": got["input"][0], "output": got["output"][0], "working": got["input"][1] + got["output"][1], "max_file": MAX_FILE}

    def open_file(self, name, area, rel):
        """(fd, size) of a regular file under the area, or (code, why). The fd is read-only and its path never contained a link."""
        parts = self.rel_ok(rel)
        if not parts:
            return 400, {"why": "bad_name"}
        base = self._area_fd(name, area)
        if base is None:
            return 404, {"why": "no_such_place"}
        try:
            dfd, last = self._walk(base, parts)
            if dfd is None:
                return 404, {"why": "no_such_file"}
            try:
                fd = os.open(last, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
            except OSError:
                return 404, {"why": "no_such_file"}
            finally:
                os.close(dfd)
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                os.close(fd)
                return 404, {"why": "no_such_file"}
            return fd, st.st_size
        finally:
            os.close(base)

    def put_input(self, name, fname, rfile, length):
        """Streams `length` bytes from rfile into NAME/input/<fname> (a free name: `-2`, `-3` ... when taken), through a `.part` file renamed when whole.
        (200, {name, size}) or (code, why). A short body leaves nothing behind."""
        if not isinstance(fname, str) or not FILE_PART.fullmatch(fname) or fname.endswith(".part") or ".part." in fname:
            return 400, {"why": "bad_name"}
        if not 0 < length <= MAX_FILE:
            return 413, {"why": "too_big", "max_bytes": MAX_FILE}
        try:
            fs = os.statvfs(self.root)
            if fs.f_bavail * fs.f_frsize - length < MIN_FREE:
                return 507, {"why": "no_space"}
        except OSError:
            return 507, {"why": "no_space"}
        fd = self._area_fd(name, "input")
        if fd is None:
            return 404, {"why": "no_such_place"}
        tmp = None
        try:
            stem, ext = os.path.splitext(fname)
            final, n = fname, 1
            while True:
                try:
                    os.stat(final, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    break
                except OSError:
                    return 500, {"why": "stat"}
                n += 1
                final = f"{stem}-{n}{ext}"
                if n > 99:
                    return 409, {"why": "too_many_copies"}
            tmp = "." + final + ".part"                      # hidden and ending in .part: never listed, never served
            out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=fd)
            got = 0
            with os.fdopen(out, "wb") as f:
                while got < length:
                    chunk = rfile.read(min(1 << 20, length - got))
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
            if got != length:
                os.unlink(tmp, dir_fd=fd)
                tmp = None
                return 400, {"why": "short_body"}
            os.rename(tmp, final, src_dir_fd=fd, dst_dir_fd=fd)
            tmp = None
            return 200, {"name": final, "size": got}
        except OSError:
            return 500, {"why": "write_failed"}
        finally:
            if tmp:
                try:
                    os.unlink(tmp, dir_fd=fd)
                except OSError:
                    pass
            os.close(fd)

    def delete_output(self, name, rel):
        parts = self.rel_ok(rel)
        if not parts:
            return 400, {"why": "bad_name"}
        base = self._area_fd(name, "output")
        if base is None:
            return 404, {"why": "no_such_place"}
        try:
            dfd, last = self._walk(base, parts)
            if dfd is None:
                return 404, {"why": "no_such_file"}
            try:
                st = os.stat(last, dir_fd=dfd, follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode):
                    return 404, {"why": "no_such_file"}
                os.unlink(last, dir_fd=dfd)
                return 200, {"name": rel, "freed_bytes": st.st_size}
            except OSError:
                return 404, {"why": "no_such_file"}
            finally:
                os.close(dfd)
        finally:
            os.close(base)

    def _exec_bg(self, name, script, *args):
        """Runs a fixed shell template inside the place's container in the background (`docker exec -d`, as the person's own uid). Every value reaches
        it as a positional argument, never inside the template."""
        rc, _ = self.docker("exec", "-d", "-u", "1000:1000", container(name), "sh", "-c", script, "sh", *args)
        return (200, {"started": True}) if rc == 0 else (502, {"why": "exec_failed"})

    def _missing(self, name, area, rel):
        """None when the file exists as a regular file under the area, else the (code, why) to answer."""
        r = self.open_file(name, area, rel)
        if isinstance(r[1], dict):
            return r
        os.close(r[0])
        return None

    def convert(self, name, rel, quality="hq"):
        """Makes the file of NAME/input readable by Resolve free (DNxHR + PCM) into input/resolve/<stem>.mov with `to-resolve`, inside the place."""
        if self.container_state(name) != "running":
            return 409, {"why": "not_running"}
        if quality not in TIERS:
            return 400, {"why": "bad_quality"}
        bad = self._missing(name, "input", rel)
        if bad:
            return bad
        stem = os.path.splitext(rel.rsplit("/", 1)[-1])[0]
        code, out = self._exec_bg(name, 'mkdir -p /input/resolve && exec to-resolve --quality "$1" "$2" "$3"', quality, "/input/" + rel, f"/input/resolve/{stem}.mov")
        return code, dict(out, result=f"resolve/{stem}.mov")

    def shrink(self, name, rel, max_mb=1900):
        """Makes an export of NAME/output fit Telegram (H.264 + AAC, at most max_mb) into output/telegram/<stem>.mp4 with `from-resolve`, inside the place."""
        if self.container_state(name) != "running":
            return 409, {"why": "not_running"}
        if not isinstance(max_mb, int) or not 10 <= max_mb <= 1900:
            return 400, {"why": "bad_size"}
        bad = self._missing(name, "output", rel)
        if bad:
            return bad
        stem = os.path.splitext(rel.rsplit("/", 1)[-1])[0]
        code, out = self._exec_bg(name, 'mkdir -p /output/telegram && from-resolve --max-mb "$1" "$2" "$3.part.mp4" && mv "$3.part.mp4" "$3"', str(max_mb), "/output/" + rel, f"/output/telegram/{stem}.mp4")
        return code, dict(out, result=f"telegram/{stem}.mp4")

    # ---- Moonlight pairing: the person confirms the PIN Moonlight shows and sees or revokes her paired devices, through the place's own Sunshine. Its admin page
    # answers only over localhost inside the container, so every call is a `docker exec` of curl with the admin password read from the container's own
    # environment (never on a command line, never returned).
    def _sunshine_base(self, name):
        try:
            with open(os.path.join(self.root, name, ".settings.json")) as f:
                b = json.load(f).get("sunshine")
            return int(b) if b else None
        except (OSError, ValueError, TypeError):
            return None

    def _sunshine(self, name, method, path, body=None):
        """(http-like code, parsed JSON) of one call to the place's Sunshine admin API, or (code, {"why"})."""
        base = self._sunshine_base(name)
        if not base:
            return 404, {"why": "no_moonlight"}
        if self.container_state(name) != "running":
            return 409, {"why": "not_running"}
        cmd = ('curl -sk -m15 -X "$1" -u "admin:$SUNSHINE_ADMIN_PASS" -H "Content-Type: application/json" '
               f'https://127.0.0.1:{base + 1}"$2" ' + ('-d "$3"' if body is not None else ""))
        args = ["exec", "-u", "1000:1000", container(name), "sh", "-c", cmd, "sh", method, path] + ([json.dumps(body)] if body is not None else [])
        rc, out = self.docker(*args, timeout=30)
        if rc != 0:
            return 502, {"why": "sunshine_unreachable"}
        try:
            v = json.loads(out)
        except ValueError:
            return 502, {"why": "sunshine_bad_answer"}
        return 200, v if isinstance(v, dict) else {"why": "sunshine_bad_answer"}

    def moonlight_list(self, name):
        """Paired devices (name and short id only) and whether a pairing is waiting for its PIN."""
        code, cl = self._sunshine(name, "GET", "/api/clients/list")
        if code != 200:
            return code, cl
        code, pend = self._sunshine(name, "GET", "/api/pin")
        if code != 200:
            return code, pend
        devs = [{"name": str(c.get("name", "?"))[:60], "id": str(c.get("uuid", ""))[:8]} for c in (cl.get("named_certs") or []) if isinstance(c, dict)]
        return 200, {"devices": devs, "waiting": len(pend.get("pairings") or [])}

    def moonlight_pin(self, name, pin):
        """Gives Sunshine the 4 digits Moonlight shows, for the pairing that is waiting (the newest if several)."""
        if not isinstance(pin, str) or not re.fullmatch(r"\d{4}", pin):
            return 400, {"why": "bad_pin"}
        code, pend = self._sunshine(name, "GET", "/api/pin")
        if code != 200:
            return code, pend
        waiting = pend.get("pairings") or []
        if not waiting:
            return 409, {"why": "nothing_waiting"}
        pid = str(waiting[-1].get("id", ""))
        if not re.fullmatch(r"[0-9a-fA-F]{32}", pid):
            return 502, {"why": "sunshine_bad_answer"}
        code, ans = self._sunshine(name, "POST", "/api/pin", {"pin": pin, "name": name, "pairing_id": pid})
        if code != 200:
            return code, ans
        return 200, {"accepted": bool(ans.get("status")), "device": str(waiting[-1].get("name", "?"))[:60]}

    def moonlight_unpair(self, name, which):
        """Revokes one paired device by the name or short id the list gave, or every one ('all'). Returns what was revoked."""
        code, cl = self._sunshine(name, "GET", "/api/clients/list")
        if code != 200:
            return code, cl
        certs = [c for c in (cl.get("named_certs") or []) if isinstance(c, dict)]
        if which == "all":
            code, ans = self._sunshine(name, "POST", "/api/clients/unpair-all", {})
            return (200, {"revoked": len(certs)}) if code == 200 and ans.get("status", True) else (code if code != 200 else 502, ans)
        hit = [c for c in certs if str(c.get("uuid", "")).lower().startswith(str(which).lower()) and len(str(which)) >= 4] \
            or [c for c in certs if str(c.get("name", "")).lower() == str(which).lower()]
        if len(hit) != 1:
            return (404 if not hit else 409), {"why": "no_such_device" if not hit else "ambiguous"}
        code, ans = self._sunshine(name, "POST", "/api/clients/unpair", {"uuid": hit[0].get("uuid")})
        return (200, {"revoked": 1, "device": str(hit[0].get("name", "?"))[:60]}) if code == 200 and ans.get("status", True) else (code if code != 200 else 502, ans)

    # ---- the clock: called every minute by the gate
    def activity(self, name):
        """(seconds since the last touch or None, container CPU % or None)."""
        rc, out = self.docker("exec", "-i", "-u", "abc", "-e", "DISPLAY=:1", container(name), "python3", "-", stdin=PROBE, timeout=20)
        idle = int(out.strip()) if rc == 0 and out.strip().isdigit() else None
        rc, out = self.docker("stats", "--no-stream", "--format", "{{.CPUPerc}}", container(name), timeout=20)
        try:
            cpu = float(out.strip().rstrip("%")) if rc == 0 else None
        except ValueError:
            cpu = None
        return idle, cpu

    # ---- the log: one row per running place per tick (capacity planning)
    def metrics_path(self):
        return os.environ.get("PLACE_METRICS_FILE") or os.path.join(os.path.dirname(self.state_path), "places-metrics.csv")

    def cgroup_place(self, pid, ids):
        """The place whose container (id prefix in `ids`) holds this pid, from /proc/PID/cgroup; None for the host's own processes."""
        try:
            with open(f"/proc/{pid}/cgroup") as f:
                text = f.read()
        except OSError:
            return None
        for name, cid in ids.items():
            if cid and cid[:12] in text:
                return name
        return None

    def write_metrics(self, rows):
        if os.environ.get("PLACE_METRICS", "1") == "0" or not rows:
            return
        path = self.metrics_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            if os.path.getsize(path) > METRICS_MAX:
                os.replace(path, path + ".1")
        except OSError:
            pass
        new = not os.path.exists(path)
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(METRICS_COLUMNS)
            for r in rows:
                w.writerow([r.get(c, "") for c in METRICS_COLUMNS])

    def collect(self, running, activity):
        """Rows for the running places: container CPU, memory and network rate, the card's totals and each place's own VRAM, and whether the person is using it."""
        names = list(running)
        rc, out = self.docker("stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}", *[container(n) for n in names], timeout=30)
        stats = {}
        for line in out.splitlines():
            p = line.split("|")
            if len(p) == 4:
                n = p[0].replace("place-", "", 1).replace("-desktop", "")
                try:
                    cpu = float(p[1].rstrip("%"))
                except ValueError:
                    cpu = 0.0
                stats[n] = (cpu, to_bytes(p[2].split("/")[0]) / 1e6, to_bytes(p[3].split("/")[-1]))      # NetIO is "rx / tx": the second is what leaves the place
        ids = {}
        for n in names:
            rc, out = self.docker("inspect", "-f", "{{.Id}}", container(n))
            ids[n] = out.strip() if rc == 0 else ""
        rc, xml = self.run(["nvidia-smi", "-q", "-x"], stdin=None, timeout=20)
        g = gpu_snapshot(xml) if rc == 0 else {}
        vram = {n: 0.0 for n in names}
        for pid, mb in (g.get("procs") or {}).items():
            n = self.cgroup_place(pid, ids)
            if n in vram:
                vram[n] += mb
        try:
            load1 = os.getloadavg()[0]
        except OSError:
            load1 = ""
        now, rows = int(self.now()), []
        prev = getattr(self, "_net", {})
        self._net = {}
        for n in names:
            cpu, mem, tx = stats.get(n, (0.0, 0.0, 0.0))
            self._net[n] = (now, tx)
            kbps = ""
            if n in prev and now > prev[n][0] and tx >= prev[n][1]:
                kbps = round((tx - prev[n][1]) * 8 / 1000 / (now - prev[n][0]), 1)
            idle = activity.get(n)
            rows.append({"ts": now, "place": n, "in_use": 1 if idle is not None and idle <= self.active_s else 0, "idle_s": "" if idle is None else idle,
                         "cpu_pct": round(cpu, 1), "mem_mb": round(mem), "net_tx_kbps": kbps, "place_vram_mb": round(vram[n]),
                         "gpu_sm_pct": g.get("sm", ""), "gpu_enc_pct": g.get("enc", ""), "gpu_dec_pct": g.get("dec", ""), "gpu_vram_used_mb": g.get("used", ""),
                         "gpu_vram_total_mb": g.get("total", ""), "gpu_power_w": g.get("power", ""), "gpu_temp_c": g.get("temp", ""),
                         "places_running": len(names), "load1": round(load1, 2) if load1 != "" else ""})
        return rows

    def tick(self):
        """For every running place: in use -> reset its clock; idle -> warn at idle_s - warn_s, close at idle_s. Returns the events (for the log)."""
        events = []
        now = int(self.now())
        seen = {}                                   # place -> seconds since its screen was touched, for the metrics log
        for name in self.names():
            if self.container_state(name) != "running":
                continue
            st = self.load().get(name, {})
            last = float(st.get("last_active", 0)) or None
            if last is None:                          # started by hand (place.py start): the clock starts when the gate first sees it
                self._mark(name, last_active=now, opened_at=st.get("opened_at") or now)
                continue
            idle, cpu = self.activity(name)
            seen[name] = idle
            if (idle is not None and idle <= self.active_s) or (cpu is not None and cpu >= self.busy_cpu):
                if st.get("warned_at"):
                    events.append((name, "back"))
                self._mark(name, last_active=now, warned_at=None)
                continue
            gone = now - last
            if gone >= self.idle_s:
                code, _ = self.stop(name, "idle")
                events.append((name, "closed" if code == 200 else "close_failed"))
            elif gone >= self.idle_s - self.warn_s and not st.get("warned_at"):
                self._mark(name, warned_at=now)
                events.append((name, "warned"))
        try:
            running = [n for n in seen if self.container_state(n) == "running"]
            if running:
                self.write_metrics(self.collect(running, seen))
        except Exception:                           # the log must never stop the clock
            pass
        return events


def start_clock(places, every_s=60.0, log=print):
    def loop():
        while True:
            time.sleep(every_s)
            try:
                for name, ev in places.tick():
                    log(f"place {name}: {ev}")
            except Exception as e:                   # the clock must outlive any one bad tick
                log(f"place clock error: {type(e).__name__}")
    threading.Thread(target=loop, daemon=True).start()
