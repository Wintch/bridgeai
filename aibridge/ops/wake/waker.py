#!/usr/bin/env python3
"""aibridge waker: one service that sleeps and wakes EVERY stack on demand, inside a RAM budget.

Per stack, two tiers, started together and stopped in reverse:
  web    Open WebUI + TTS          sleeps after idle_web seconds without a real UI request
  brain  Hermes itself             sleeps after idle_brain seconds with the web asleep and nothing running
Always up: each stack's nginx (2 MB), the Telegram Bot API server, and this service.
Data lives in bind mounts and `docker start/stop` never recreates anything; start_hermes.sh flushes Hermes's
state on SIGTERM.

Ways to wake a stack
  * a browser *navigation*: nginx gets a 502 (Open WebUI stopped), error_page sends it here, the person sees a
    "loading" page that reloads itself. Background traffic of an old tab only gets 503: never wakes, never counts.
  * Telegram (stacks with a bot): while the brain is stopped this service peeks at getUpdates WITHOUT confirming
    them (the message stays queued), starts Hermes for an allowed user, answers "encendiendo, ~N s" and, once
    connected, "listo para trabajar". Hermes must run with drop_pending_on_cold_boot=false (start_hermes.sh sets
    it). Only one consumer may poll, so peeking stops the moment the brain starts.
  * a scheduled cron of a sleeping stack (see "crons").
Hooks: after the brain is ready every executable in on_wake.d/ runs (env WAKE_NAME, WAKE_REASON, WAKE_CHAT_ID).

RAM budget (the host has no spare): boots are serialised (one stack booting at a time, so two wakes never both
count the same free memory), and before starting anything the guard checks MemAvailable minus the stack's expected
footprint stays above reserve_mb and that no more than max_awake brains run; if not, it stops the least recently
used IDLE stack(s) first, and if that is not enough the wake WAITS (never starts anyway). A watchdog checks every
10 s: below critical_mb it stops idle stacks, least recently used first. Busy stacks (a turn running, a UI request
in the last 2 minutes, registered long jobs, a cron running) are never stopped by the guard. Every container also has
its own cgroup limit in compose, so a runaway is killed alone, not the host.

Crons: a sleeping stack's Hermes cannot tick. This service reads each stack's cron/jobs.json (docker cp, works on a
stopped container) and wakes the brain when a job is due, never two stacks at once (cron slots), each shifted by a
per-stack offset plus a slot so they do not pile up, and never more often than cron.min_interval_min. After the run
the brain gets only cron.hold_seconds before it goes back to sleep. A registered long job (/workdir/jobs/*.json, see
jobwatch.py) keeps its stack awake until it is reported.

Maintenance switch: `touch ops/wake/NO_SLEEP` and nothing is ever stopped (wakes still work).
Config: ops/wake/stacks.json (see stacks.json.example). Runs on the host (no docker.sock inside any container).
"""
import calendar
import datetime
import errno
import http.server
import json
import math
import os
import re
import socketserver
import statistics
import subprocess
import tempfile
import threading
import time
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
try:
    import notify   # operator alerts (ops bot); tests and hosts without ops/lib just log
except ImportError:
    notify = None
SLOW_BOOT_S = 90
# The first wake on a new image runs every `hermes config set` once (start_hermes.sh boot-config stamp): measured 138.8 s
# on hernik, 2026-10-20, plus ~10 s of warm-up now waited for below (a usual wake is ~20 s). Told to the person as the wait,
# and not alarming until SLOW_FIRST_BOOT_S.
# A boot longer than FULL_BOOT_S ran those sets; they are kept apart so they do not skew the usual estimate.
FIRST_BOOT_S = 150
SLOW_FIRST_BOOT_S = 200
FULL_BOOT_S = 40
# "Listo para trabajar" (2026-10-20): Telegram says "connected" ~1 s after Hermes starts, but the message queued during the wake is only
# taken after "Turn machinery warmed in N s" (10.5 s on hernik), so the person was told "ready" ~9 s before anything started. A wake
# that ends in a Telegram message now also waits for that log line, at most WARM_WAIT_MAX_S after the boot began (a Hermes that
# stops logging it costs that much, not a dead wait). 0 turns it off (selftest.py: its fake containers never log it).
WARM_WAIT_MAX_S = float(os.environ.get("WAKE_WARM_MAX_S", "40"))
CONFIG = os.environ.get("WAKE_CONFIG", os.path.join(HERE, "stacks.json"))
# The three paths below can be redirected (tests only: selftest.py must never touch the real maintenance switch, the
# production state files or the real hooks).
NO_SLEEP = os.environ.get("WAKE_NO_SLEEP", os.path.join(HERE, "NO_SLEEP"))
HOOKS_DIR = os.environ.get("WAKE_HOOKS_DIR", os.path.join(HERE, "on_wake.d"))
STATE_DIR = os.environ.get("WAKE_STATE_DIR", HERE)
# Background traffic that is NOT a person using the UI. Open WebUI polls /_app/version.json about once a minute from
# every open tab (seen 2026-10-07 in herand's nginx log): counting it would keep a stack awake behind a forgotten tab.
# User-Agents that ask for HTML without a person behind them: crawlers and the link previews of chat apps.
NOT_A_PERSON = re.compile(r"bot|crawl|spider|slurp|preview|facebookexternalhit|embedly|whatsapp|curl|wget|python|httpclient|headless", re.I)
IGNORED = ("/ws/", "/__wake", "/_auth", "/health", "/favicon", "/static/", "/manifest", "/_app/version.json", "/api/version")
# The front's log_format (nginx-main.conf) ends with ` auth=0|1`: 1 when the request carried a `token` cookie or an
# Authorization header. Anonymous hits (bots, scanners, link previews) are not a person using the UI. A line without
# the field (an nginx still on the old log_format) counts as before.
LOG_RE = re.compile(r'"(?:GET|POST|PUT|PATCH|DELETE) (\S+) HTTP/[\d.]+" (\d{3})(?:.* auth=([01]))?')
TICK = int(os.environ.get("WAKE_TICK", "30"))
MEMINFO = os.environ.get("WAKE_TEST_MEMINFO", "")   # tests only: a file holding the MemAvailable MB to pretend

CFG = {}
STACKS = {}
BOOT_SEM = threading.BoundedSemaphore(1)   # boots in flight (max_parallel_boots, default 1: people entering together queue)
GUARD_LOCK = threading.Lock()     # admission + eviction decisions
PLAN_LOCK = threading.Lock()      # cron slots
LAST_CRON_WAKE = [0.0]            # when the last cron wake (any stack) was decided: the next one waits a slot


def log(msg):
    # UTC: telemetry.py epoch() reads these journal timestamps as UTC
    print(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), msg, flush=True)


def ops(kind, key, text=None):
    """alert/resolve through the ops bot in a thread: never block a wake on Telegram."""
    if notify is None or os.environ.get("WAKE_TEST_MEMINFO"):
        return
    fn = notify.alert if kind == "alert" else notify.resolve
    threading.Thread(target=lambda: fn(key, text) if text else fn(key), daemon=True).start()


def docker(*args, timeout=90):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def running(name):
    r = docker("inspect", "-f", "{{.State.Running}}", name)
    return r.returncode == 0 and r.stdout.strip() == "true"


def ips(name):
    r = docker("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", name)
    return r.stdout.split() if r.returncode == 0 else []


def http_ok(name, port, path="/health"):
    for ip in ips(name):
        try:
            with urllib.request.urlopen(f"http://{ip}:{port}{path}", timeout=2) as resp:
                return resp.status == 200
        except Exception:
            continue
    return False


def mem_available_mb():
    if MEMINFO:
        try:
            return int(open(MEMINFO).read().strip())
        except (OSError, ValueError):
            pass
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    return 0


def parse_iso(ts):
    try:
        return datetime.datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError):
        return None


def read_env_file(path):
    out = {}
    try:
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.rstrip("\n").split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


class Stack:
    def __init__(self, c, index):
        self.name = c["name"]
        self.index = index
        self.bind, self.port = c["bind"], int(c.get("port", 3099))
        self.front, self.web, self.brain = c["front"], list(c["web"]), c["brain"]
        self.idle_web, self.idle_brain = int(c.get("idle_web", 600)), int(c.get("idle_brain", 600))
        self.brain_api_port = str(c.get("brain_api_port", 8642))
        self.web_health_port = str(c.get("web_health_port", 8080))
        self.est_brain_mb, self.est_web_mb = int(c.get("est_brain_mb", 700)), int(c.get("est_web_mb", 300))
        self.jobs_dir = c.get("jobs_dir", "/workdir/jobs")
        self.state_file = os.path.join(STATE_DIR, f"{self.name}.state.json")
        self.state_lock = threading.Lock()   # sentinel, wake and tick threads all save state
        # persist dir of the stack: where its cron/jobs.json is read when the brain container was recreated and never started
        self.persist_dir = c.get("persist_dir") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "stacks", self.name, "persist")
        tg = read_env_file(c["telegram_env"]) if c.get("telegram_env") else {}
        self.tg_token = tg.get("TELEGRAM_BOT_TOKEN", "")
        self.tg_allowed = {x.strip() for x in tg.get("TELEGRAM_ALLOWED_USERS", "").split(",") if x.strip()}
        # telegram_api = the stack's Local Bot API container; without one the public api.telegram.org is used (a person
        # whose stack has a bot but no local Bot API server still wakes it with a message).
        self.tg_api = c.get("telegram_api", "")
        self.tg_api_port = str(c.get("telegram_api_port", 8081))
        self.tg_on = bool(self.tg_token)
        self.booting = False
        self.queued = False           # waiting for its turn to boot (someone else is booting)
        self.stopping = False
        self.chats = set()
        self.boot_t0 = 0.0
        self.web_started = self.brain_started = 0.0
        self.last_activity = time.time()
        self.cron_hold_until = 0.0
        self.cron_only = False        # woken by a cron and nobody else has used it since
        self.tg_seen = int(self.load_state().get("tg_seen", 0))   # newest update_id answered (survives a restart)
        self.wake_lock = threading.Lock()   # one wake decision at a time (a page load + a Telegram message together)
        self.tg_full_warned = 0.0
        self.cron_due = None          # planned wake for a due cron (epoch), None = nothing planned
        self.cron_last_wake = {}      # job id -> last time we woke for it
        self._public = (0.0, "")      # (when, state): /__wake/status is polled by every open "loading" page

    # ---- state ----
    def web_up(self):
        return running(self.web[0])

    def brain_up(self):
        return running(self.brain)

    def gateway_state(self):
        r = docker("exec", self.brain, "cat", "/root/.hermes/gateway_state.json")
        try:
            return json.loads(r.stdout)
        except ValueError:
            return {}

    def brain_ready(self, need_tg=True):
        """API answering, and (need_tg) Telegram connected. A web visitor only needs the API: Hermes's Telegram adapter
        waits for one full getUpdates cycle (10 s) before it reports "connected" when nothing is queued (2026-10-09)."""
        if not self.brain_up() or not http_ok(self.brain, self.brain_api_port):
            return False
        if self.tg_on and need_tg:  # the file survives a stop: only trust a "connected" written after this boot started
            tgs = self.gateway_state().get("platforms", {}).get("telegram", {})
            if tgs.get("state") != "connected":
                return False
            written = parse_iso(tgs.get("updated_at"))
            return bool(written) and written >= self.container_started() - 2
        return True

    def warm(self):
        """Hermes logged "Turn machinery warmed" (INFO, so only in agent.log, never in `docker logs`) after this container started:
        from then on a message queued during the wake is taken at once. agent.log keeps the lines of earlier boots, hence the time check
        (its timestamps are UTC, like the container's StartedAt)."""
        started = self.container_started()
        if started == math.inf:
            return False
        try:
            r = docker("exec", self.brain, "tail", "-n", "400", "/root/.hermes/logs/agent.log")
        except (OSError, subprocess.SubprocessError):
            return False
        for line in r.stdout.splitlines():
            if "Turn machinery warmed" in line:
                try:
                    when = calendar.timegm(time.strptime(line[:19], "%Y-%m-%d %H:%M:%S"))
                except ValueError:
                    continue
                if when >= started - 2:
                    return True
        return False

    def container_started(self):
        """Epoch when the brain container last started (what a "connected" in gateway_state.json must be newer than).
        inf when it cannot be read, so a stale "connected" is never trusted (the caller just polls again)."""
        try:
            r = docker("inspect", "-f", "{{.State.StartedAt}}", self.brain)
            m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?", r.stdout.strip())
            if not m:
                return math.inf
            t = datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
            return t.timestamp() + float("0." + m.group(2)[:6] if m.group(2) else 0)
        except (OSError, ValueError, OverflowError, subprocess.SubprocessError):
            return math.inf

    def web_ready(self):
        return self.web_up() and http_ok(self.web[0], self.web_health_port)

    def public_state(self):
        """Cached 2.5 s: every request used to cost several docker inspect / http probes."""
        now = time.time()
        when, val = self._public
        if val and now - when < 2.5:
            return val
        val = self._public_state()
        self._public = (now, val)
        return val

    def _public_state(self):
        if self.queued:
            return "queued"
        if self.booting:
            return "starting"
        if not self.web_up():
            return "asleep"
        return "ready" if (self.web_ready() and self.brain_ready(need_tg=False)) else "starting"

    # ---- activity ----
    def ui_requests(self):
        r = docker("logs", "--since", f"{TICK + 5}s", self.front)
        n = 0
        for line in (r.stdout + r.stderr).splitlines():
            m = LOG_RE.search(line)
            if m and m.group(2) not in ("502", "503", "504") and m.group(3) != "0" and not m.group(1).startswith(IGNORED):
                n += 1
        return n

    def newest_turn_age(self):
        r = docker("exec", self.brain, "sh", "-c", "tail -n 80 /root/.hermes/logs/agent.log")
        newest = 0
        for line in r.stdout.splitlines():
            if "conversation turn:" in line or "[api-" in line:
                try:
                    newest = max(newest, calendar.timegm(time.strptime(line[:19], "%Y-%m-%d %H:%M:%S")))
                except ValueError:
                    pass
        return (time.time() - newest) if newest else None

    def pending_jobs(self):
        r = docker("exec", self.brain, "sh", "-c", f"ls {self.jobs_dir}/*.json 2>/dev/null | wc -l")
        try:
            return int(r.stdout.strip() or 0)
        except ValueError:
            return 0

    def busy(self):
        """Something is happening that a stop would interrupt."""
        if self.booting or self.stopping or time.time() < self.cron_hold_until:
            return True
        if not self.brain_up():
            return False
        if self.gateway_state().get("active_agents"):
            return True
        age = self.newest_turn_age()
        return (age is not None and age < 120) or self.pending_jobs() > 0

    def footprint_mb(self):
        names = [c for c in self.web + [self.brain, self.front] if running(c)]
        if not names:
            return 0
        r = docker("stats", "--no-stream", "--format", "{{.MemUsage}}", *names)
        total = 0.0
        for line in r.stdout.splitlines():
            m = re.match(r"([\d.]+)\s*([KMG]i?B)", line)
            if m:
                total += float(m.group(1)) * {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "KB": 1 / 1024, "MB": 1, "GB": 1024}[m.group(2)]
        return int(total)

    # ---- boot history ----
    def load_state(self):
        try:
            return json.load(open(self.state_file))
        except (OSError, ValueError):
            return {}

    def save_state(self, **changes):
        with self.state_lock:
            st = {**self.load_state(), **changes}
            tmp = self.state_file + ".tmp"
            try:
                with open(tmp, "w") as f:
                    json.dump(st, f)
                os.replace(tmp, self.state_file)
            except OSError as exc:
                log(f"[{self.name}] could not save state: {exc}")

    def boots(self):
        return self.load_state().get("boots", [])

    def image_id(self):
        """Image id the brain container was created from (changes when ops/recreate_hermes.sh puts a new image in), or None."""
        try:
            return docker("inspect", "-f", "{{.Image}}", self.brain).stdout.strip() or None
        except Exception:
            return None

    def first_on_image(self):
        """True until a boot has been recorded on the container's current image: that boot runs every config set."""
        img = self.image_id()
        return bool(img) and img != self.load_state().get("image")

    def boot_estimate(self):
        if self.first_on_image():
            full = self.load_state().get("boots_full", [])[-3:]
            return int(statistics.median(full)) if full else FIRST_BOOT_S
        h = self.boots()[-5:]
        return int(statistics.median(h)) if h else 60

    def record_boot(self, seconds):
        st = self.load_state()
        key = "boots_full" if seconds > FULL_BOOT_S else "boots"
        self.save_state(**{key: (st.get(key, []) + [round(seconds, 1)])[-20:]}, image=self.image_id() or st.get("image"))

    # ---- telegram ----
    def tg(self, method, params=None, timeout=20):
        if self.tg_api:
            ip = (ips(self.tg_api) or [None])[0]
            if not ip:
                raise RuntimeError("telegram-bot-api container has no IP")
            base = f"http://{ip}:{self.tg_api_port}"
        else:
            base = "https://api.telegram.org"
        req = urllib.request.Request(f"{base}/bot{self.tg_token}/{method}",
                                     data=json.dumps(params or {}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)

    def say(self, chat_id, text):
        try:
            self.tg("sendMessage", {"chat_id": chat_id, "text": text}, timeout=15)
        except Exception as exc:  # never log the URL: it carries the bot token
            log(f"[{self.name}] sendMessage failed: {type(exc).__name__}")

    def sentinel_loop(self):
        while True:
            try:
                if self.brain_up() or self.booting:
                    time.sleep(10 if self.brain_up() else 2)
                    continue
                # Short long-poll: a poll still in flight when Hermes starts delays Hermes's own first getUpdates.
                # No offset: peeking must not confirm anything an allowed person sent (Hermes still has to get it).
                res = self.tg("getUpdates", {"timeout": 2 if self.tg_api else 8, "limit": 100}, timeout=25)
                ups = res.get("result", [])
                hit = None
                lead_junk = None    # newest update_id of the junk that precedes every update of an allowed person
                lead = True
                for u in ups:
                    msg = next((u[k] for k in ("message", "edited_message", "channel_post", "callback_query") if k in u), None)
                    if msg and str(msg.get("from", {}).get("id", "")) in self.tg_allowed:
                        lead = False    # even one already answered (<= tg_seen) may still be unread by Hermes: keep it queued
                        if u.get("update_id", 0) > self.tg_seen:
                            hit = (u, msg)
                            break
                    elif lead:
                        lead_junk = u.get("update_id", 0)
                if lead_junk is not None:
                    # Strangers' messages and non-message updates at the head of the queue would otherwise fill the page
                    # forever and hide an allowed person's message behind them. offset = newest junk id + 1 confirms
                    # only those (ids are ascending and nothing allowed comes before them).
                    self.tg("getUpdates", {"offset": lead_junk + 1, "limit": 1, "timeout": 0}, timeout=25)
                    log(f"[{self.name}] telegram: confirmed leading junk updates up to id {lead_junk}")
                elif not hit and len(ups) >= 100 and time.time() - self.tg_full_warned > 3600:
                    self.tg_full_warned = time.time()
                    log(f"[{self.name}] telegram: 100 queued updates and none is new from an allowed person: "
                        f"messages behind them cannot be seen until Hermes runs")
                if not hit and ups:
                    time.sleep(2)   # getUpdates returns at once while updates are queued: do not spin
                if hit:
                    u, msg = hit
                    self.tg_seen = u.get("update_id", 0)
                    self.save_state(tg_seen=self.tg_seen)
                    chat = (msg.get("chat") or msg.get("message", {}).get("chat") or {}).get("id")
                    if chat is not None:
                        self.say(chat, f"⏳ Encendiendo Hermes… tarda unos {self.boot_estimate()} s. Tu mensaje quedó guardado, no hace falta repetirlo.")
                    threading.Thread(target=self.wake, args=("telegram", False, chat), daemon=True).start()
                    time.sleep(3)
            except Exception as exc:
                log(f"[{self.name}] sentinel error: {type(exc).__name__}")
                time.sleep(5)

    # ---- wake ----
    def run_hooks(self, reason, chat_id):
        if not os.path.isdir(HOOKS_DIR):
            return
        for f in sorted(os.listdir(HOOKS_DIR)):
            path = os.path.join(HOOKS_DIR, f)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                try:
                    env = dict(os.environ, WAKE_NAME=self.name, WAKE_REASON=reason, WAKE_CHAT_ID=str(chat_id or ""))
                    r = subprocess.run([path], env=env, capture_output=True, text=True, timeout=120)
                    log(f"[{self.name}] hook {f}: rc={r.returncode}")
                    if r.returncode not in (0, 1, 3):   # 1 or 3 = the hook found a problem and reported it itself
                        ops("alert", f"hook:{self.name}:{f}", f"{self.name}: el hook {f} terminó con rc={r.returncode}")
                except Exception as exc:
                    log(f"[{self.name}] hook {f} failed: {exc}")
                    ops("alert", f"hook:{self.name}:{f}", f"{self.name}: el hook {f} falló ({type(exc).__name__})")

    def start_container(self, name):
        """docker start; returns "" or a short reason. A failed start must not wait out the 240 s boot timeout."""
        try:
            r = docker("start", name, timeout=60)
        except subprocess.TimeoutExpired:
            return f"docker start {name} timed out"
        if r.returncode != 0:
            return f"docker start {name} failed: {(r.stderr.strip().splitlines() or ['rc=%d' % r.returncode])[-1][:200]}"
        return ""

    def wake(self, reason, want_web=False, chat_id=None):
        if chat_id is not None:
            self.chats.add(chat_id)
        for _ in range(90):  # a stop in progress finishes first
            if not self.stopping:
                break
            time.sleep(1)
        with self.wake_lock:   # check-and-claim in one step: two callers must not both start a boot
            if self.booting:
                return
            if self.brain_up() and (not want_web or self.web_up()):
                self.last_activity = time.time()
                return
            self.booting = True
        waited = False
        hook_args = None   # hooks run after `booting` is cleared: a slow hook must not make the stack look "starting"
        try:
            while not BOOT_SEM.acquire(timeout=5):  # somebody else is booting: people entering together take turns
                self.queued = True
                if chat_id is not None and not waited:
                    self.say(chat_id, "🕐 Hay otro Hermes encendiéndose; espero mi turno.")
                    waited = True
            self.queued = False
            try:
                need_brain, need_web = not self.brain_up(), want_web and not self.web_up()
                if not (need_brain or need_web):
                    return
                # A cron wake is never worth another stack's RAM: no eviction, no waiting; try again later.
                if not self.admit(need_brain, need_web, chat_id, patient=reason != "cron"):
                    if reason == "cron":
                        self.cron_due = time.time() + CFG["cron"]["retry_seconds"]
                        log(f"[{self.name}] cron wake postponed {CFG['cron']['retry_seconds']}s: not enough free memory (avail={mem_available_mb()}MB)")
                        return
                    log(f"[{self.name}] wake ({reason}) gave up: no memory")
                    ops("alert", f"wake:{self.name}:nomem", f"{self.name}: no pudo despertar ({reason}) por falta de "
                                                            f"memoria (libre {mem_available_mb()} MB). La persona recibió el aviso.")
                    for c in list(self.chats):
                        self.say(c, "⚠️ El servidor no tiene memoria libre ahora mismo. Probá de nuevo en unos minutos.")
                    self.chats.clear()
                    return
                self.boot_t0 = time.time()
                self.last_activity = time.time()
                self.cron_only = reason == "cron"
                if reason == "cron":
                    for jid in getattr(self, "cron_pending_ids", []):
                        self.cron_last_wake[jid] = time.time()
                log(f"[{self.name}] waking ({reason}): brain={need_brain} web={need_web} avail={mem_available_mb()}MB")
                start_err = ""
                if need_brain:
                    self.brain_started = time.time()
                    start_err = self.start_container(self.brain)
                if need_web and not start_err:
                    self.web_started = time.time()
                    for c in self.web:
                        start_err = self.start_container(c)
                        if start_err:
                            break
                deadline = self.boot_t0 + 240
                need_tg = reason != "web"
                def ready_now():
                    return (self.brain_ready(need_tg) and (not want_web or self.web_ready())
                            and (not (need_tg and self.tg_on) or time.time() - self.boot_t0 > WARM_WAIT_MAX_S or self.warm()))
                while not start_err and time.time() < deadline and not ready_now():
                    time.sleep(1)
                ok = not start_err and ready_now()
                if ok:   # logged INSIDE the turn: the next boot cannot log "waking" before this stack is "ready"
                    took = time.time() - self.boot_t0
                    first = need_brain and self.first_on_image()
                    if need_brain:
                        self.record_boot(took)
                    log(f"[{self.name}] ready after {took:.1f}s ({reason})" + (" first on this image" if first else ""))
                    if took > (SLOW_FIRST_BOOT_S if first else SLOW_BOOT_S):
                        ops("alert", f"wake:{self.name}:slow", f"{self.name}: tardó {took:.0f} s en despertar ({reason}); lo normal es "
                                                              f"{self.boot_estimate()} s.")
                    else:
                        ops("resolve", f"wake:{self.name}:slow")
                    ops("resolve", f"wake:{self.name}:timeout", f"{self.name}: vuelve a despertar bien ({took:.0f} s)")
                    ops("resolve", f"wake:{self.name}:nomem")
            finally:
                BOOT_SEM.release()
            if not ok:
                if start_err:
                    log(f"[{self.name}] boot aborted: {start_err}")
                    ops("alert", f"wake:{self.name}:timeout", f"{self.name}: no pudo arrancar ({reason}): {start_err}")
                else:
                    log(f"[{self.name}] boot did not finish in 240s")
                    ops("alert", f"wake:{self.name}:timeout", f"{self.name}: no terminó de despertar en 240 s ({reason}). "
                                                             f"Revisar: docker logs del cerebro.")
                for c in list(self.chats):
                    self.say(c, "⚠️ Hermes está tardando más de lo normal en encender. Probá de nuevo en un minuto.")
                self.chats.clear()
                return
            log(f"[{self.name}] footprint {self.footprint_mb()}MB, host avail={mem_available_mb()}MB")
            chat = None
            for c in list(self.chats):
                chat = c
                self.say(c, "✅ Listo para trabajar.")
            self.chats.clear()
            if reason == "cron":   # give the cron time to run once Hermes is up, then let the idle logic sleep it
                self.cron_hold_until = time.time() + CFG["cron"]["hold_seconds"]
            hook_args = (reason, chat)
        finally:
            self.booting = False
            self.queued = False
        if hook_args:
            self.run_hooks(*hook_args)

    def admit(self, need_brain, need_web, chat_id, patient=True):
        """Wait (up to 5 min) until the host can take this stack inside the RAM budget, evicting idle stacks.
        patient=False (crons): look once, never evict anybody, never wait."""
        need = (self.est_brain_mb if need_brain else 0) + (self.est_web_mb if need_web else 0)
        deadline = time.time() + (300 if patient else 0)
        told = False
        while True:
            with GUARD_LOCK:
                awake = [s for s in STACKS.values() if s is not self and s.brain_up()]
                over_awake = need_brain and len(awake) >= CFG["max_awake"]
                short = mem_available_mb() - need < CFG["reserve_mb"]
                if not over_awake and not short:
                    return True
                if patient and evict_one(exclude=self):
                    continue
            if time.time() >= deadline:
                return False
            if chat_id is not None and not told:
                self.say(chat_id, "🕐 No hay memoria libre: espero a que otro Hermes termine y vuelvo.")
                told = True
            time.sleep(5)

    # ---- sleep ----
    def sleep_web(self):
        self.stopping = True
        try:
            log(f"[{self.name}] stopping web")
            for c in reversed(self.web):
                docker("stop", "-t", "20", c, timeout=60)
        finally:
            self.stopping = False

    def sleep_brain(self):
        self.stopping = True
        try:
            log(f"[{self.name}] stopping brain")
            docker("stop", "-t", "45", self.brain, timeout=90)
        finally:
            self.stopping = False

    def tick(self):
        """Idle accounting for this stack (called every TICK seconds)."""
        if self.booting or self.stopping:
            return
        self.ticks = getattr(self, "ticks", 0) + 1
        web_up, brain_up = self.web_up(), self.brain_up()
        if brain_up and self.ticks % 10 == 0:
            self.notify_fast_jobs(self.due_jobs())
        # cron_only (short idle limit after a cron wake) ends when a person shows up: a UI request, or something busy
        # once the cron's own hold time is over (busy() is True during the hold because of the cron's own turn).
        if web_up and self.ui_requests():
            self.last_activity = time.time()
            self.cron_only = False
        elif (web_up or brain_up) and self.busy():
            self.last_activity = time.time()
            if time.time() >= self.cron_hold_until:
                self.cron_only = False
        if os.path.exists(NO_SLEEP):
            return
        idle = time.time() - self.last_activity
        brain_limit = min(self.idle_brain, CFG["cron"]["hold_seconds"]) if self.cron_only else self.idle_brain
        if web_up and idle > self.idle_web and time.time() - self.web_started > self.idle_web:
            self.sleep_web()   # the brain is judged against the SAME last activity: web, then brain, in this same tick
            web_up = False
        if brain_up and not web_up and idle > brain_limit and time.time() - self.brain_started > brain_limit:
            if not self.busy():
                self.sleep_brain()

    # ---- crons ----
    def due_jobs(self):
        """Enabled jobs of this stack as (id, name, next_run_epoch, interval_minutes or None), read with `docker cp`
        (works on a stopped container). Jobs in cron.ignore_names are left out: e.g. jobwatch."""
        with tempfile.TemporaryDirectory() as d:
            dst = os.path.join(d, "jobs.json")
            if docker("cp", f"{self.brain}:/root/.hermes/cron/jobs.json", dst).returncode != 0:
                # A container recreated with --no-start has no jobs.json yet: use the persisted copy
                # (start_hermes.sh restores it from there on the first start).
                if self.brain_up():
                    return []
                dst = os.path.join(self.persist_dir, "cron", "jobs.json")
            try:
                jobs = json.load(open(dst)).get("jobs", [])
            except (OSError, ValueError, AttributeError):
                return []
        out = []
        for j in jobs:
            if not j.get("enabled", True) or j.get("paused_at") or j.get("name") in CFG["cron"]["ignore_names"]:
                continue
            nxt = parse_iso(j.get("next_run_at"))
            sched = j.get("schedule") or {}
            every = sched.get("minutes") if sched.get("kind") == "interval" else None
            if nxt:
                out.append((j.get("id", "?"), j.get("name", "?"), nxt, every))
        return out

    def notify_fast_jobs(self, jobs):
        """Tell the person (once per job) that a job asking for less than min_interval fires at most that often."""
        floor = CFG["cron"]["min_interval_min"]
        done = set(self.load_state().get("notified", []))
        for jid, name, _nxt, every in jobs:
            if every is None or every >= floor or jid in done:
                continue
            log(f"[{self.name}] cron '{name}' asks every {every} min: it will fire at most every {floor} min")
            if self.tg_on:
                for uid in self.tg_allowed:
                    self.say(uid, f"⏰ El cron «{name}» pide correr cada {every} min. Este servidor duerme cuando no se usa, "
                                  f"así que se dispara como máximo cada {floor} min.")
            done.add(jid)
            self.save_state(notified=sorted(done))

    def plan_cron(self):
        """For a sleeping stack: the next grid point (every grid_minutes, shifted per stack) at which something is due,
        serialised against the other stacks. Nothing due (or only ignored jobs) = no wake planned at all."""
        c = CFG["cron"]
        jobs = self.due_jobs()
        self.notify_fast_jobs(jobs)
        if not jobs:
            self.cron_due = None
            return
        floor = max(self.cron_last_wake.get(j[0], 0) + c["min_interval_min"] * 60 for j in jobs)
        want = max(min(j[2] for j in jobs), floor, time.time())
        grid = c["grid_minutes"] * 60
        phase = (self.index * c["stack_offset_seconds"]) % grid
        t = math.ceil((want - phase) / grid) * grid + phase     # one wake per grid period serves every job due by then
        with PLAN_LOCK:
            t = max(t, LAST_CRON_WAKE[0] + c["slot_seconds"])
            taken = sorted(s.cron_due for s in STACKS.values() if s is not self and s.cron_due)
            for _ in range(len(taken) + 1):  # slide forward until no other stack's slot overlaps
                clash = [o for o in taken if abs(t - o) < c["slot_seconds"]]
                if not clash:
                    break
                t = max(clash) + c["slot_seconds"]
            self.cron_due = t

    def cron_tick(self):
        if self.brain_up() or self.booting or self.stopping:
            self.cron_due = None
            return
        if self.cron_due is None or time.time() > self.cron_due + 3600:
            self.plan_cron()
        if self.cron_due and time.time() >= self.cron_due:
            # Last look before spending RAM: is anything STILL due? (the stack may have run its jobs while awake)
            pending = [j for j in self.due_jobs() if j[2] <= time.time()]
            if not pending:
                self.cron_due = None
                return
            with PLAN_LOCK:
                LAST_CRON_WAKE[0] = time.time()
            log(f"[{self.name}] waking for a scheduled cron ({len(pending)} job(s) due)")
            self.cron_pending_ids = [j[0] for j in pending]   # marked as woken-for only if the wake really happens
            self.cron_due = None
            threading.Thread(target=self.wake, args=("cron", False, None), daemon=True).start()


def evict_one(exclude=None):
    """Stop the least recently used idle stack (web first, then brain). True if something was stopped."""
    if os.path.exists(NO_SLEEP):
        return False
    cands = [s for s in STACKS.values() if s is not exclude and (s.web_up() or s.brain_up()) and not s.busy()
             and time.time() - s.last_activity > CFG["evict_min_idle_seconds"]]
    if not cands:
        return False
    s = min(cands, key=lambda x: x.last_activity)
    log(f"[{s.name}] evicted by the RAM guard (avail={mem_available_mb()}MB)")
    if s.web_up():
        s.sleep_web()
    elif s.brain_up():
        s.sleep_brain()
    return True


def watchdog_loop():
    warned = 0
    while True:
        time.sleep(min(10, TICK))
        try:
            avail = mem_available_mb()
            if warned and avail > CFG["reserve_mb"]:
                warned = 0
                ops("resolve", "ram:critical", f"La RAM se recuperó ({avail} MB libres)")
            if avail < CFG["critical_mb"]:
                with GUARD_LOCK:
                    if not evict_one() and time.time() - warned > 60:
                        warned = time.time()
                        log(f"RAM CRITICAL ({avail}MB) and every stack is busy: nothing to stop, new wakes are held")
                        ops("alert", "ram:critical", f"RAM crítica ({avail} MB libres) y todos los stacks están ocupados: "
                                                     f"no se puede liberar nada, los nuevos wakes esperan.")
        except Exception as exc:
            log(f"watchdog error: {exc}")


def sleeper_loop():
    last = 0
    while True:
        time.sleep(min(5, TICK))
        if time.time() - last < TICK:
            continue
        last = time.time()
        for s in STACKS.values():
            try:
                s.tick()
                s.cron_tick()
            except Exception as exc:  # never die: one bad tick must not stop the sleeper
                log(f"[{s.name}] tick failed: {exc}")


PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Despertando a Hermes</title><style>
:root{color-scheme:light dark;--bg:#fff;--fg:#1c1c1e;--mut:#6b6b70;--ac:#4f46e5}
@media(prefers-color-scheme:dark){:root{--bg:#111114;--fg:#f2f2f4;--mut:#9a9aa2;--ac:#818cf8}}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{text-align:center;padding:0 16px}.s{width:44px;height:44px;margin:0 auto 22px;border:4px solid var(--mut);border-top-color:var(--ac);border-radius:50%;animation:r 1s linear infinite}
@keyframes r{to{transform:rotate(360deg)}}h1{font-size:1.3rem;margin:0 0 6px}p{color:var(--mut);margin:0}
</style></head><body><main><div class="s"></div><h1>Despertando a Hermes…</h1>
<p id="m">Tarda unos __EST__ segundos. Tus chats y archivos están intactos.</p></main>
<script>
let n=0;async function t(){try{const r=await fetch('/__wake/status',{cache:'no-store'});const j=await r.json();
if(j.state==='ready'){location.reload();return}
document.getElementById('m').textContent=j.state==='queued'?'Hay otra persona encendiendo su Hermes y sos la siguiente. Esperá un momento, tus chats están intactos.':'Tarda unos __EST__ segundos. Tus chats y archivos están intactos.';
if(j.state==='asleep'&&n>2){location.reload();return}}catch(e){}
n++;if(n>90)document.getElementById('m').textContent='Está tardando más de lo normal. Recargá la página en un momento.';
setTimeout(t,2000)}setTimeout(t,2000);
</script></body></html>"""


def make_handler(stack):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body, ctype, extra=None):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _asleep(self):
            return self._send(503, json.dumps({"error": "asleep"}), "application/json", {"Retry-After": "30"})

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/__wake/status":
                return self._send(200, json.dumps({"state": stack.public_state()}), "application/json")
            # Only a browser navigation to a document wakes a stack, never a bot or a fetch(). Browsers omit Sec-Fetch-*
            # on plain http to a non-localhost address (the LAN way in), so without them a request still counts when
            # it asks for HTML AND carries Upgrade-Insecure-Requests: 1, which every browser navigation sends and
            # curl, scanners and link previewers normally do not; a webview or older browser that omits it still counts
            # with a browser User-Agent that is not a bot or link previewer.
            mode = self.headers.get("Sec-Fetch-Mode")
            if mode is None:
                ua = self.headers.get("User-Agent", "")
                nav = "text/html" in self.headers.get("Accept", "") and (
                    self.headers.get("Upgrade-Insecure-Requests") == "1"
                    or (ua.startswith("Mozilla/") and not NOT_A_PERSON.search(ua)))
            else:
                nav = mode == "navigate" and self.headers.get("Sec-Fetch-Dest") == "document"
            if nav and not path.startswith(IGNORED):
                threading.Thread(target=stack.wake, args=("web", True), daemon=True).start()
                return self._send(503, PAGE.replace("__EST__", str(stack.boot_estimate())), "text/html; charset=utf-8", {"Retry-After": "5"})
            return self._asleep()

        do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = lambda self: self._asleep()
    return Handler


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def listen(s, wait_s=120):
    """Server on the stack's address, the gateway of its Docker network. Right after a host boot Docker may not have
    brought that network up yet (EADDRNOTAVAIL, seen after the 2026-10-11 power cut: the unit failed and its alert
    went out as a false alarm), so wait for it. Any bind error is retried forever (one log line per distinct error,
    an operator alert after wait_s): a stack whose network is missing or whose port is taken must not take down the
    waker of every other stack."""
    t0 = time.time()
    last, alerted = None, False
    while True:
        try:
            srv = Server((s.bind, s.port), make_handler(s))
            if alerted:
                ops("resolve", f"waker:{s.name}:bind", f"{s.name}: el waker ya escucha en {s.bind}:{s.port}")
            return srv
        except OSError as e:
            if e.errno != last:
                last = e.errno
                log(f"[{s.name}] cannot listen on {s.bind}:{s.port} ({errno.errorcode.get(e.errno, e.errno)}): retrying"
                    + (f", alert after {wait_s}s" if e.errno == errno.EADDRNOTAVAIL else ""))
            if not alerted and time.time() - t0 > wait_s:
                alerted = True
                ops("alert", f"waker:{s.name}:bind", f"{s.name}: el waker no puede escuchar en {s.bind}:{s.port} "
                                                    f"({errno.errorcode.get(e.errno, e.errno)}) desde hace {wait_s} s; "
                                                    f"este stack no despierta solo. Revisar la red Docker del stack.")
            time.sleep(2 if e.errno == errno.EADDRNOTAVAIL else 5)


def serve(s):
    listen(s).serve_forever()


def main():
    global CFG
    CFG = json.load(open(CONFIG))
    CFG.setdefault("reserve_mb", 1500)
    CFG.setdefault("critical_mb", 700)
    CFG.setdefault("max_awake", 4)
    CFG.setdefault("evict_min_idle_seconds", 120)   # a stack must have been idle this long to be stopped by the guard
    CFG["cron"] = {"min_interval_min": 60, "grid_minutes": 60, "slot_seconds": 240, "stack_offset_seconds": 600,
                   "hold_seconds": 180, "retry_seconds": 600, "ignore_names": ["jobwatch"], **CFG.get("cron", {})}
    global BOOT_SEM
    BOOT_SEM = threading.BoundedSemaphore(int(CFG.get("max_parallel_boots", 1)))
    for i, c in enumerate(CFG["stacks"]):
        STACKS[c["name"]] = Stack(c, i)
    for s in STACKS.values():
        threading.Thread(target=serve, args=(s,), daemon=True).start()   # one thread per stack: each retries its own bind
        if s.tg_on:
            threading.Thread(target=s.sentinel_loop, daemon=True).start()
        log(f"[{s.name}] on {s.bind}:{s.port} web={s.web} brain={s.brain} telegram={'on' if s.tg_on else 'off'} "
            f"idle web={s.idle_web}s brain={s.idle_brain}s")
    log(f"budget: reserve={CFG['reserve_mb']}MB critical={CFG['critical_mb']}MB max_awake={CFG['max_awake']} "
        f"cron={CFG['cron']} avail={mem_available_mb()}MB")
    threading.Thread(target=watchdog_loop, daemon=True).start()
    sleeper_loop()


if __name__ == "__main__":
    main()
