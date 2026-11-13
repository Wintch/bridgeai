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
  * a person SENDING a message from a tab left open while the stack slept (POST /api/chat/completions, or the chat save
    /api/v1/chats/<id>, with the `token` cookie or an Authorization header): never dropped. The waker wakes the stack,
    HOLDS the request (bounded by the boot estimate), then replays it to Open WebUI and streams the answer back. If the
    wake fails or takes too long the person gets a 503 with a `detail` the UI shows, never a silent 503 {"error":"asleep"}.
  * Telegram (stacks with a bot): while the brain is stopped this service peeks at getUpdates WITHOUT confirming
    them (the message stays queued), starts Hermes for an allowed user, answers "encendiendo, ~N s" and, once
    connected, "listo para trabajar". Hermes must run with drop_pending_on_cold_boot=false (start_hermes.sh sets
    it). Only one consumer may poll, so peeking stops the moment the brain starts.
  * a scheduled cron of a sleeping stack (see "crons").
  * a task handed to the stack's bot on the Gitea board: ops/wake/tareas_hook.py verifies the webhook and writes
    <stack>.task.json; task_tick() wakes the stack like a cron would (reason "task", see "Tasks" below).
Hooks: after the brain is ready every executable in on_wake.d/ runs (env WAKE_NAME, WAKE_REASON = telegram, web, cron or task, WAKE_CHAT_ID).

RAM budget (the host has no spare): boots are serialised (one stack booting at a time, so two wakes never both
count the same free memory), and before starting anything the guard checks MemAvailable minus the stack's expected
footprint stays above reserve_mb and that no more than max_awake brains run; if not, it stops the least recently
used IDLE stack(s) first, and if that is not enough the wake WAITS (never starts anyway). A watchdog checks every
10 s: below critical_mb it stops idle stacks, least recently used first. Busy stacks (a turn running, a UI request
in the last 2 minutes, registered long jobs, a cron script holding its busy marker, a background process the agent started) are never stopped by the guard. Every container also has
its own cgroup limit in compose, so a runaway is killed alone, not the host.

Crons: a sleeping stack's Hermes cannot tick. This service reads each stack's cron/jobs.json (docker cp, works on a
stopped container) and wakes the brain when a job is due, never two stacks at once (cron slots), each shifted by a
per-stack offset plus a slot so they do not pile up, and never more often than cron.min_interval_min. After the run
the brain gets only cron.hold_seconds before it goes back to sleep. A registered long job (/workdir/jobs/*.json, see
jobwatch.py) keeps its stack awake until it is reported.

Night jobs (CFG "night", default after 23:00, idle 60 min, jobs ["jobnight"]): a daily job named there (the job scan in mode "noche")
does not wait for its fixed time. Once the stack's local clock is past `after` on the night before the job's next run and nothing has
happened on the stack for idle_minutes (the person is most likely offline), night_tick() wakes the brain like a cron (one slot, look
once, no eviction) and starts the job with `hermes cron run ID`. The night is then marked done (state file, key = local date 12 h
earlier), so the waker plans no wake for that night's fixed run: due_jobs() moves it to the next night. jobpush.py keeps its own
mark too, so a run Hermes makes anyway (awake at 04:30, or a catch-up at the next wake) skips. If the person never goes quiet, the
fixed time still runs it as before.

Tasks: the request file is only a "look at your board" signal (repo, issue numbers, times), never task text. A task wake is treated like a
cron wake: look once, never evict anybody, never wait (a stack with no RAM is retried after task.retry_seconds), and the brain only gets
task.hold_seconds before it can sleep again. A stack that is already awake gets the run when nothing is busy (a person talking has priority).
The run itself is started by the on_wake.d hook 40-task-run (reason "task"). See ops/wake/TAREAS_HOOK.md.
Two guards against a task that goes wrong. (1) The waker counts the task hooks it runs for one request (task.max_tries, default 5): a hook
that is not executable, or crashes before it can count its own failure, otherwise woke the stack every retry until the 6 h drop with no
alert; at the cap the request is dropped and the operator is told. (2) A run in progress is "busy": tareas_run.py writes <stack>.task.run.json
when the API accepts the run, and until the run is seen finished (GET /v1/runs/<id> through `tareas_run.py --check`, at most task.max_run_seconds,
default 1 h) busy_reasons() says "una tarea en curso", which holds off the idle sleep, the RAM guard's evict_one() and a new task request.

Maintenance switch: `touch ops/wake/NO_SLEEP` and nothing is ever stopped (wakes still work).
On-demand sleep: the agent's `dormir` command writes /workdir/.dormir.json in the container; the next tick stops the stack (see sleep_decision).
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
import stat
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
# on the main stack, plus ~10 s of warm-up now waited for below (a usual wake is ~20 s). Told to the person as the wait,
# and not alarming until SLOW_FIRST_BOOT_S.
# A boot longer than FULL_BOOT_S ran those sets; they are kept apart so they do not skew the usual estimate.
FIRST_BOOT_S = 150
SLOW_FIRST_BOOT_S = 200
FULL_BOOT_S = 40
# "Listo para trabajar": Telegram says "connected" ~1 s after Hermes starts, but the message queued during the wake is only
# taken after "Turn machinery warmed in N s" (10.5 s measured), so the person was told "ready" ~9 s before anything started. A wake
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
# every open tab (seen in an nginx access log): counting it would keep a stack awake behind a forgotten tab.
# User-Agents that ask for HTML without a person behind them: crawlers and the link previews of chat apps.
NOT_A_PERSON = re.compile(r"bot|crawl|spider|slurp|preview|facebookexternalhit|embedly|whatsapp|curl|wget|python|httpclient|headless", re.I)
IGNORED = ("/ws/", "/__wake", "/_auth", "/health", "/favicon", "/static/", "/manifest", "/_app/version.json", "/api/version")
# A person sending a message (see "Ways to wake a stack"): these are held and replayed, every other non-GET stays a plain 503.
# Open WebUI sends a chat turn with POST /api/chat/completions and saves the typed message with POST /api/v1/chats/<id>
# (or /new); the other POSTs an idle tab makes in the front's access log are settings/timezone updates, which are background.
SEND_PATH = re.compile(r"^/api/(?:chat/completions|v1/chats/[\w-]+)$")
HOLD_MIN_S, HOLD_MAX_S, HOLD_EXTRA_S = 90, 150, 40   # hold = boot estimate + 40 s, between 90 and 150 s (a proxy in front of the stack cuts long waits)
MAX_HOLD_BODY = 16 * 1024 * 1024                    # a chat turn is a few KB; a bigger body (an upload) is not held
REPLAY_GRACE_S = 15                                 # after "ready", a refused connection to Open WebUI is retried this long
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding",
              "upgrade", "content-length", "x-wake-upstream-status"}
HOLD_FAIL = {   # shown by Open WebUI as the error of the message (it reads `detail`)
    "es": "Hermes todavía está encendiendo y tu mensaje no se envió. Esperá un minuto y enviálo de nuevo.",
    "ru": "Hermes ещё запускается, и сообщение не отправлено. Подождите минуту и отправьте его снова.",
    "en": "Hermes is still starting and your message was not sent. Wait a minute and send it again.",
}
# The front's log_format (nginx-main.conf) ends with ` auth=0|1`: 1 when the request carried a `token` cookie or an
# Authorization header. Anonymous hits (bots, scanners, link previews) are not a person using the UI. A line without
# the field (an nginx still on the old log_format) counts as before.
LOG_RE = re.compile(r'"(?:GET|POST|PUT|PATCH|DELETE) (\S+) HTTP/[\d.]+" (\d{3})(?:.* auth=([01]))?')
TICK = int(os.environ.get("WAKE_TICK", "30"))
NIGHT_READ_S = 300   # night_tick reads jobs.json (docker cp) at most this often
# Brain log lines that mean a reply went wrong in a way the person may never report (an 806k-character loop
# flooded a stack's Telegram for two hours, and the flood ban swallowed the shutdown notice). Told to the operator through the
# ops bot, which is another bot and so is not caught by a flood ban on the stack's own. Counts only, never message text.
INCIDENTS = (
    ("runaway", "aibridge runaway_text_cap", "un modelo entró en loop y el guardia cortó la respuesta (patches/runaway_text_cap.py)"),
    ("flood", "Telegram flood control", "Telegram frenó al bot por flood: avisos y respuestas de ese chat se pierden mientras dure"),
    ("truncated", "Response still truncated after", "una respuesta quedó truncada después de 4 continuaciones"),
)
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


def iso_offset(ts):
    """UTC offset in seconds of an ISO time with a zone ("...-03:00" -> -10800), None without one."""
    try:
        off = datetime.datetime.fromisoformat(ts).utcoffset()
    except (TypeError, ValueError):
        return None
    return None if off is None else int(off.total_seconds())


ENV_FILE_MAX = 64 * 1024


def read_env_file(path):
    """KEY=value lines of a small regular file. The workdir copy of .telegram.env is writable by the stack's agent (root in its
    container): a symlink there could point the waker at another stack's .env and its bot token (4.2), so
    the last component is opened with O_NOFOLLOW and only a regular file under 64 KB is read, as ops/scan/scanner.py does."""
    out = {}
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return out
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > ENV_FILE_MAX:
            log(f"ignored {path}: not a small regular file")
            return out
        with os.fdopen(fd, encoding="utf-8", errors="replace") as f:
            fd = None
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.rstrip("\n").split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    finally:
        if fd is not None:
            os.close(fd)
    return out


REQUEST_MAX_AGE = 900          # a request older than this is stale (the stack was down, or nobody acted): ignored and removed
REQUEST_TURN_GRACE = 120       # let the turn that asked finish answering ("me duermo") before the stop
PHANTOM_AFTER = 1200           # the gateway's own "active work" counter stuck above 0 this long, with no turn started, is a leak, not work


def gateway_count_is_phantom(active, turn_age, uptime, after=PHANTOM_AFTER):
    """True when Hermes's gateway_state says work is active but nothing backs it up (active_agents stayed at 1 for 15+ minutes
    after one answered message, no turn, no process; the waker took it for work, so neither `dormir` nor the idle sleep ever fired).
    Real work leaves traces elsewhere (background processes, detached downloads, jobs, markers: all checked by busy()); this only decides
    whether the bare counter alone may keep the stack awake. It may not once no turn started for `after` seconds and the container is older."""
    if not active:
        return False
    return (turn_age is None or turn_age > after) and uptime > after


def sleep_decision(req, now, turn_active, busy_now):
    """What to do with the agent's request to sleep: "none", "wait", "drop" or "sleep". Pure, so it is tested offline.

    mode "ahora": stop once the turn that asked has finished (turn_active False, or REQUEST_TURN_GRACE passed). With
      force=False it also waits while other work is busy (it started after the agent looked) and is dropped after the grace.
    mode "cuando-termine": stop as soon as nothing is busy and no turn is running.
    """
    if not isinstance(req, dict) or "ts" not in req:
        return "none"
    age = now - float(req["ts"])
    if age > REQUEST_MAX_AGE or age < -60:
        return "drop"
    if req.get("mode") == "cuando-termine":
        return "wait" if (turn_active or busy_now) else "sleep"
    if turn_active and age < REQUEST_TURN_GRACE:
        return "wait"
    if not req.get("force") and busy_now:
        return "wait" if age < REQUEST_TURN_GRACE else "drop"
    return "sleep"


TASK_REQUEST_MAX_BYTES = 8192
TASK_RUN_REASON = "una tarea en curso"
TASK_RUN_SCRIPT = os.environ.get("WAKE_TASK_RUN", os.path.join(HERE, "tareas_run.py"))


def task_run_decision(rec, now, poll, hold_s, max_run_s):
    """Is a task run recorded in <stack>.task.run.json still going? Pure (poll is called only when needed). -> "busy", "free" (nothing says it is
    going) or "drop" (free, and the record is to be removed).
    poll() -> "running", "finished" or "unknown" (the API did not say: its answer is unverified, so then only the first hold_s count as busy)."""
    try:
        age = now - float(rec["started"])
        rid = str(rec.get("run_id") or "")
    except (KeyError, TypeError, ValueError, AttributeError):
        return "drop"
    if age > max_run_s:
        return "drop"
    if rid:
        state = poll()
        if state == "finished":
            return "drop"
        if state == "running":
            return "busy"
    return "busy" if age < hold_s else "free"


def task_decision(req, now, retry_at, blocked, brain_up, busy_now, max_age):
    """What task_tick does with a request from ops/wake/tareas_hook.py: "none", "drop", "wait", "wake" or "run". Pure, so it is tested offline.

    drop  the request is malformed or older than max_age (the issue stays open on the board: this was only the wake signal)
    wait  not yet (not_before of the receiver's rate limit, a retry after a failed wake, the stack booting/stopping or already starting
          a run, or the stack is awake and busy: a person talking has priority)
    wake  the brain is down: wake it with reason "task" (the hook starts the run once it is ready)
    run   the brain is up and quiet: start the run now (the hooks do not run for an already awake stack)
    """
    if req is None:
        return "none"
    if not isinstance(req, dict):
        return "drop"
    try:
        first, not_before = float(req["first_ts"]), float(req.get("not_before", 0))
    except (KeyError, TypeError, ValueError):
        return "drop"
    if now - first > max_age:
        return "drop"
    if now < not_before or now < retry_at or blocked:
        return "wait"
    if not brain_up:
        return "wake"
    return "wait" if busy_now else "run"


DAILY_CRON_RE = re.compile(r"^\d{1,2} \d{1,2} \* \* \*$")   # "M H * * *": the only schedule a night job may have


def night_key(epoch, offset):
    """The night a moment belongs to: the local date 12 h earlier (23:00 and 04:30 of one night share a key). offset: UTC offset, s."""
    return time.strftime("%Y-%m-%d", time.gmtime(epoch + offset - 12 * 3600))


def night_next(nxt, offset, done):
    """A daily job's next run that is not done yet: the fixed run of a night the early run already took moves one day on."""
    for _ in range(3):
        if night_key(nxt, offset) != done:
            break
        nxt += 86400
    return nxt


def night_window_start(nxt, offset, after):
    """The last local `after` (HH:MM) at or before the run at nxt, as epoch: a 04:30 run opens at 23:00 the evening before."""
    h, m = (int(x) for x in after.split(":"))
    local = nxt + offset
    start = local - local % 86400 + h * 3600 + m * 60
    if start > local:
        start -= 86400
    return start - offset


def night_decision(now, nxt, offset, done, after, idle_for, idle_needed, brain_up, retry_at):
    """What night_tick does for one night job: "none" (outside the window), "wait", "wake" or "run" (brain up: the caller still checks
    busy). Pure, so it is tested offline."""
    nxt = night_next(nxt, offset, done)
    if not night_window_start(nxt, offset, after) <= now < nxt:
        return "none"
    if now < retry_at or idle_for < idle_needed:
        return "wait"
    return "run" if brain_up else "wake"


SLEPT_TEXT = {
    "es": "💤 Dormido ({hm} UTC). {why}Escríbeme cuando quieras y me despierto (tarda unos minutos).",
    "ru": "💤 Сплю ({hm} UTC). {why}Напиши, когда нужно, и я проснусь (это займёт пару минут).",
    "en": "💤 Asleep ({hm} UTC). {why}Message me whenever you like and I'll wake up (it takes a few minutes).",
}
SLEPT_WHY = {
    "es": {"cuando-termine": "Terminó lo que corría. ", "ahora": ""},
    "ru": {"cuando-termine": "То, что шло, закончилось. ", "ahora": ""},
    "en": {"cuando-termine": "What was running has finished. ", "ahora": ""},
}
NOT_SLEPT_TEXT = {
    "es": "No logré apagarme: el contenedor sigue arriba. No cortes nada por tu cuenta, ya avisé al operador.",
    "ru": "Мне не удалось выключиться: контейнер всё ещё работает. Ничего не обрывай, оператор уже предупреждён.",
    "en": "I could not shut down: the container is still up. Don't cut anything yourself, the operator has already been told.",
}


LIVE_WARN_TEXT = {
    "es": "📍 Tenés compartida tu ubicación en vivo. Mientras duermo no la registro y no me despierta; solo gasta batería de tu teléfono. "
          "Para pararla, en este chat tocá «Dejar de compartir». Si necesitás que sepa dónde estás, mandame un pin normal.",
    "ru": "📍 У вас включена трансляция геопозиции. Пока я сплю, я её не записываю и она меня не будит; она только садит батарею телефона. "
          "Чтобы остановить, нажмите в этом чате «Прекратить делиться». Если нужно, чтобы я знал, где вы, пришлите обычную геометку.",
    "en": "📍 You are sharing your live location. While I sleep I do not record it and it does not wake me; it only drains your phone's battery. "
          "To stop it, tap \u201cStop sharing\u201d in this chat. If I need to know where you are, send me a normal pin.",
}
LIVE_WARN_EVERY = 12 * 3600


# A task this stack's bot filed came back (tareas_hook.py 6b): one fixed line per task to the people of THIS bot, before its run starts.
# Only the issue number and the closer's login (both checked here) go in; never a title or a text.
DONE_NOTICE = {
    "es": {"closed": "🔔 {by} cerró la tarea #{n} que pedí en el tablero. Reviso el resultado y sigo con lo mío.",
           "bloqueado": "🔔 {by} dejó bloqueada la tarea #{n} que pedí en el tablero. Miro el motivo y te cuento."},
    "ru": {"closed": "🔔 {by} закрыл задачу #{n}, которую я поставил на доске. Смотрю результат и продолжаю свою часть.",
           "bloqueado": "🔔 {by} заблокировал задачу #{n}, которую я поставил на доске. Смотрю причину и расскажу."},
    "en": {"closed": "🔔 {by} closed task #{n} that I filed on the board. I am reading the result and going on with my part.",
           "bloqueado": "🔔 {by} blocked task #{n} that I filed on the board. I am looking at the reason and will tell you."},
}
DONE_BY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,38}$")


def done_notices(req, lang, already):
    """-> [(key, text)] for the "done" entries of a request not yet in `already` (a set of keys). Bad entries are skipped."""
    out = []
    texts = DONE_NOTICE.get(lang) or DONE_NOTICE["es"]
    for d in (req.get("done") or [])[:20] if isinstance(req, dict) else []:
        if not isinstance(d, dict):
            continue
        n, by, kind = d.get("n"), str(d.get("by") or ""), d.get("kind")
        if not (isinstance(n, int) and not isinstance(n, bool) and 0 < n < 10 ** 9 and kind in texts and DONE_BY_RE.match(by)):
            continue
        key = f"{n}:{kind}:{req.get('first_ts')}"
        if key not in already:
            out.append((key, texts[kind].format(by=by, n=n)))
    return out


def notice_lang(request_lang, stack_lang):
    """One language for the last sleep message (never Spanish and Russian together): the person's own reply language
    (/idioma, carried in the sleep request), else the stack's "lang" in stacks.json, else Spanish."""
    for lang in (request_lang, stack_lang):
        if lang in SLEPT_TEXT:
            return lang
    return "es"


def sleep_notice(stopped, mode, lang, hm):
    """The last message of an on-request sleep, written by the host AFTER the container stopped: the agent's own
    reply to /dormir can only say the request was sent, it cannot know when the stop happened. lang: "es", "ru" or "en"; anything else is Spanish."""
    lang = lang if lang in SLEPT_TEXT else "es"
    if stopped:
        return SLEPT_TEXT[lang].format(hm=hm, why=SLEPT_WHY[lang].get(mode, ""))
    return NOT_SLEPT_TEXT[lang]


def update_kind(u, allowed):
    """Classify one Telegram update for the sentinel: ('real', msg) from an allowed person and worth waking for; ('live', msg) a refresh
    of a shared LIVE LOCATION (an edited_message that carries a location: Telegram sends one every few seconds, dated like the original
    message, for hours; a stack once woke 18 s after every sleep because of them, and `edited_message` age 3.5 h showed it); ('other', msg)
    anyone else's update or one that is not a message."""
    key = next((k for k in ("message", "edited_message", "channel_post", "callback_query") if k in u), None)
    msg = u.get(key) if key else None
    if not (msg and str(msg.get("from", {}).get("id", "")) in allowed):
        return "other", msg
    if key == "edited_message" and "location" in msg:
        return "live", msg
    return "real", msg


class Stack:
    def __init__(self, c, index):
        self.name = c["name"]
        self.index = index
        self.bind, self.port = c["bind"], int(c.get("port", 3099))
        self.front, self.web, self.brain = c["front"], list(c["web"]), c["brain"]
        self.idle_web, self.idle_brain = int(c.get("idle_web", 600)), int(c.get("idle_brain", 600))
        self.brain_api_port = str(c.get("brain_api_port", 8642))
        self.lang = str(c.get("lang", ""))      # "es", "ru", "en" or empty: the fallback language of the last sleep message (the person's /idioma wins; then Spanish)
        self.web_health_port = str(c.get("web_health_port", 8080))
        self.est_brain_mb, self.est_web_mb = int(c.get("est_brain_mb", 700)), int(c.get("est_web_mb", 300))
        self.jobs_dir = c.get("jobs_dir", "/workdir/jobs")
        # jobpush.py (a --no-agent cron script: no agent turn, no registered job) keeps this file while it runs; the file is
        # touched between its phases, so one older than busy_marker_minutes is a run that died, not a busy stack.
        self.busy_marker = c.get("busy_marker", "/workdir/jobfinder/data/.jobpush-running")
        self.busy_marker_minutes = int(c.get("busy_marker_minutes", 90))
        # Background processes the agent started (terminal background=true: yt-dlp, ffmpeg, a build) are listed in
        # /root/.hermes/processes.json. One that is alive keeps the stack awake, for at most this long (a process that
        # is still running after that is stuck or forgotten, and must not keep the stack awake forever).
        self.bg_max_minutes = int(c.get("background_max_minutes", 360))
        # On-demand sleep: the agent's `dormir` command writes this file; the next tick stops the stack.
        self.sleep_request_path = c.get("sleep_request", "/workdir/.dormir.json")
        self.state_file = os.path.join(STATE_DIR, f"{self.name}.state.json")
        self.state_lock = threading.Lock()   # sentinel, wake and tick threads all save state
        # persist dir of the stack: where its cron/jobs.json is read when the brain container was recreated and never started
        self.persist_dir = c.get("persist_dir") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "stacks", self.name, "persist")
        # Where the bot token lives: the stack's compose .env (telegram_env, set by the operator) or, when the person
        # connected Telegram on the keys page, /workdir/.telegram.env (keys_server.py writes it there, readable from the host).
        self.tg_files = ([c["telegram_env"]] if c.get("telegram_env") else []) + [
            c.get("telegram_handoff") or os.path.join(os.path.dirname(self.persist_dir), "workdir", ".telegram.env")]
        self.tg_token, self.tg_allowed = "", set()
        self.load_telegram()
        # telegram_api = the stack's Local Bot API container; without one the public api.telegram.org is used (a person
        # whose stack has a bot but no local Bot API server still wakes it with a message).
        self.tg_api = c.get("telegram_api", "")
        self.tg_api_port = str(c.get("telegram_api_port", 8081))
        self.tg_on = bool(self.tg_token)
        # A wake that fails (no memory, start error, 240 s) used to consume the Telegram trigger: tg_seen was already saved, so the
        # queued message never woke the stack again until the person wrote once more (1.0). Now tg_seen is put
        # back and the sentinel retries the same message after 60 s, 120 s, then every 300 s.
        self.wake_failed, self.tg_retry_at, self.tg_retry_n = False, 0.0, 0
        self.sentinel_started = False
        self.tg_paused = False        # True while confirm_handled() talks to Telegram: the sentinel must not poll at the same time
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
        # Task requests (ops/wake/tareas_hook.py): its own retry clock, because cron_tick replans cron_due from jobs.json every tick and
        # would erase a task retry kept there.
        self.task_file = os.path.join(STATE_DIR, f"{self.name}.task.json")
        self.task_retry_at = 0.0
        self.task_starting = False    # a run hook is in progress for an already awake stack
        self.task_tries = [None, 0]   # [first_ts of the request, task hook runs for it]: the waker's own cap, whatever the hooks do
        self.task_run_file = os.path.join(STATE_DIR, f"{self.name}.task.run.json")
        self.task_poll = (0.0, "unknown")   # (when, answer) of the last run-status check
        self.cron_last_wake = {}      # job id -> last time we woke for it
        self.job_info = {}            # job id -> (name, UTC offset of its next_run_at in seconds or None, daily "M H * * *")
        st = self.load_state().get("night_done")
        self.night_done = st if isinstance(st, dict) else {}   # night job id -> key of the night it already ran (survives a restart)
        self.night_retry_at = 0.0
        self.night_starting = False
        self.night_jobs = (0.0, [])   # (when read, due_jobs()) for night_tick: jobs.json is read at most every NIGHT_READ_S
        self._public = (0.0, "")      # (when, state): /__wake/status is polled by every open "loading" page
        self.incidents_scanned = 0.0  # brain log read up to here for INCIDENTS

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
        waits for one full getUpdates cycle (10 s) before it reports "connected" when nothing is queued."""
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

    BG_SCRIPT = (
        "import json,os\n"
        "try: d=json.load(open('/root/.hermes/processes.json'))\n"
        "except Exception: d=[]\n"
        "up=float(open('/proc/uptime').read().split()[0]); hz=os.sysconf('SC_CLK_TCK'); n=0\n"
        "for e in (d if isinstance(d,list) else []):\n"
        "    try:\n"
        "        st=open('/proc/%d/stat'%int(e['pid'])).read().rsplit(')',1)[1].split()\n"
        "        if st[0] not in 'ZX' and (up-int(st[19])/hz)/60<MAXMIN: n+=1\n"
        "    except Exception: pass\n"
        "print(n)\n")

    def background_processes(self):
        """How many processes the agent started in the background are still alive (a download, a render, a build).
        Without this the waker slept the stack 10 minutes after the last turn and killed them."""
        r = docker("exec", self.brain, "python3", "-c", self.BG_SCRIPT.replace("MAXMIN", str(self.bg_max_minutes)))
        try:
            return int(r.stdout.strip() or 0)
        except ValueError:
            return 0

    DETACHED_SCRIPT = (
        "import os,re\n"
        "pat=re.compile(r'(^|/)(subs-fetch|yt-dlp|aria2c|ffmpeg|demucs|whisper)( |$)')\n"
        "up=float(open('/proc/uptime').read().split()[0]); hz=os.sysconf('SC_CLK_TCK'); n=0\n"
        "for p in os.listdir('/proc'):\n"
        "    if not p.isdigit() or int(p)==os.getpid(): continue\n"
        "    try:\n"
        "        c=open('/proc/%s/cmdline'%p,'rb').read().replace(b'\\0',b' ').decode(errors='replace').strip()\n"
        "        st=open('/proc/%s/stat'%p).read().rsplit(')',1)[1].split()\n"
        "        if pat.search(c) and st[0] not in 'ZX' and (up-int(st[19])/hz)/60<MAXMIN: n+=1\n"
        "    except Exception: pass\n"
        "print(n)\n")

    def detached_jobs(self):
        """Download/render programs alive in the container that are NOT in processes.json (the agent launched them with nohup or &, so
        background_processes() cannot see them). Before this a stack with six detached downloads would have been stopped 10 minutes
        after the last chat message. Same age cap as background_processes."""
        r = docker("exec", self.brain, "python3", "-c", self.DETACHED_SCRIPT.replace("MAXMIN", str(self.bg_max_minutes)))
        try:
            return int(r.stdout.strip() or 0)
        except ValueError:
            return 0

    def sleep_request(self):
        """The agent's pending `dormir` request as a dict, or None."""
        r = docker("exec", self.brain, "cat", self.sleep_request_path)
        if r.returncode != 0:
            return None
        try:
            return json.loads(r.stdout)
        except ValueError:
            return None

    def clear_sleep_request(self):
        docker("exec", self.brain, "rm", "-f", self.sleep_request_path)

    def marker_fresh(self):
        """A cron script that is not an agent (jobpush) is running: its busy marker was touched recently."""
        if not self.busy_marker:
            return False
        r = docker("exec", self.brain, "find", self.busy_marker, "-mmin", f"-{self.busy_marker_minutes}")
        return r.returncode == 0 and bool(r.stdout.strip())

    def busy(self, ignore_gateway=False):
        """Something is happening that a stop would interrupt."""
        return bool(self.busy_reasons(ignore_gateway))

    def busy_reasons(self, ignore_gateway=False):
        """What a stop would interrupt, as short names (empty = nothing). ignore_gateway: leave Hermes's own counter out, for a person who
        explicitly asked to sleep: the turn that asked is covered by REQUEST_TURN_GRACE, and a leaked counter must not veto the request."""
        if self.booting or self.stopping or time.time() < self.cron_hold_until:
            return ["arrancando o con un cron en curso"]
        if not self.brain_up():
            return []
        # Still booting, started outside the waker (ops/recreate_hermes.sh after a new image): start_hermes.sh writes the
        # boot config before Hermes's API answers, and a stop 9 s after start cut it short on every redeploy.
        started = self.container_started()
        uptime = time.time() - started if math.isfinite(started) else 1e9
        if uptime < 300 and not http_ok(self.brain, self.brain_api_port):
            return ["terminando de arrancar"]
        out = []
        if self.task_run_busy():   # an API run (/v1/runs) is not known to raise the gateway's counter: the run record says it is going
            out.append(TASK_RUN_REASON)
        age = self.newest_turn_age()
        if not ignore_gateway:
            active = self.gateway_state().get("active_agents")
            if active and gateway_count_is_phantom(active, age, uptime):
                if not getattr(self, "phantom_logged", False):
                    self.phantom_logged = True
                    log(f"[{self.name}] gateway says {active} active but no turn started for "
                        f"{'over 40' if age is None else int(age // 60)} min: ignored as a stuck counter")
            elif active:
                out.append("un turno del agente")
                self.phantom_logged = False
            else:
                self.phantom_logged = False
        if self.marker_fresh():
            out.append("un cron sin agente (jobpush)")
        if self.background_processes() > 0:
            out.append("procesos en segundo plano")
        if self.detached_jobs() > 0:
            out.append("descargas o renders en marcha")
        if age is not None and age < 120:
            out.append("un turno reciente")
        if self.pending_jobs() > 0:
            out.append("trabajos registrados")
        return out

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
        """True when Telegram accepted the message. a 200 with ok=false used to pass as sent, and a send that worked left no line at all."""
        try:
            r = self.tg("sendMessage", {"chat_id": chat_id, "text": text}, timeout=15)
            if isinstance(r, dict) and r.get("ok") is False:
                log(f"[{self.name}] sendMessage refused: {str(r.get('error_code'))} {str(r.get('description'))[:80]}")
                return False
            return True
        except Exception as exc:  # never log the URL: it carries the bot token
            log(f"[{self.name}] sendMessage failed: {type(exc).__name__}")
            return False

    def tell_person(self, text):
        """A short note to the people allowed on this stack's bot (the waker is the only one who knows a sleep request failed).
        Returns how many accepted it (0 when Telegram is off or nobody is allowed)."""
        if not self.tg_on:
            return 0
        return sum(1 for uid in self.tg_allowed if self.say(uid, text))

    def load_telegram(self):
        """Token and allowed ids from the first of tg_files that has a token. Returns True when they changed."""
        token, allowed = "", set()
        for f in self.tg_files:
            e = read_env_file(f)
            if e.get("TELEGRAM_BOT_TOKEN"):
                token = e["TELEGRAM_BOT_TOKEN"]
                allowed = {x.strip() for x in e.get("TELEGRAM_ALLOWED_USERS", "").split(",") if x.strip()}
                break
        changed = (token, allowed) != (self.tg_token, self.tg_allowed)
        self.tg_token, self.tg_allowed = token, allowed
        return changed

    def refresh_telegram(self):
        """A person who connects (or disconnects) Telegram on the keys page does not need the waker restarted."""
        if not self.load_telegram():
            return
        self.tg_on = bool(self.tg_token)
        log(f"[{self.name}] telegram {'connected' if self.tg_on else 'disconnected'} (token file changed)")
        self.start_sentinel()

    def start_sentinel(self):
        if self.tg_on and not self.sentinel_started:
            self.sentinel_started = True
            threading.Thread(target=self.sentinel_loop, daemon=True).start()

    def warn_live_location(self, msg):
        """Tell the person once (per shared location, and at most every 12 h) that a live location they left on does nothing while the stack
        sleeps. The bot API cannot stop a live location the person shares: only their Telegram can, so the message says how."""
        chat = (msg.get("chat") or {}).get("id")
        mid = str(msg.get("message_id", ""))
        if chat is None or not mid:
            return False
        st = self.load_state()
        if mid == str(st.get("live_warn_mid", "")) or time.time() - float(st.get("live_warn_ts", 0) or 0) < LIVE_WARN_EVERY:
            return False
        if self.say(chat, LIVE_WARN_TEXT[notice_lang(None, self.lang)]):
            self.save_state(live_warn_ts=time.time(), live_warn_mid=mid)
            log(f"[{self.name}] told the person their live location is on (it does not wake the stack)")
            return True
        return False

    def confirm_handled(self, upto_ts):
        """After an on-request stop: tell Telegram that Hermes already took the updates of the allowed people sent up to the request.
        `/dormir ya` stopped the container within a second, before Hermes's next getUpdates confirmed the command, so Telegram
        handed it out again at the next boot (container log: `/dormir ya` run 2 s after Hermes connected, with nobody typing) and the
        stack put itself to sleep again, in a loop. Only a PREFIX is confirmed: the newest allowed update with date <= upto_ts such that
        no allowed update newer than upto_ts comes before it. A message sent after the request stays queued and wakes the stack as usual.
        Returns the update_id confirmed, or None."""
        if not self.tg_on or not self.tg_allowed:
            return None
        self.tg_paused = True
        try:
            res = self.tg("getUpdates", {"limit": 100, "timeout": 0}, timeout=25)
            best = None
            for u in res.get("result", []):
                msg = next((u[k] for k in ("message", "edited_message", "callback_query") if k in u), None)
                if not (msg and str(msg.get("from", {}).get("id", "")) in self.tg_allowed):
                    continue
                date = msg.get("date") if "date" in msg else (msg.get("message") or {}).get("date")
                if not isinstance(date, (int, float)) or date > upto_ts:
                    break
                best = u.get("update_id", 0)
            if best is None:
                return None
            self.tg("getUpdates", {"offset": best + 1, "limit": 1, "timeout": 0}, timeout=25)
            self.tg_seen = max(self.tg_seen, best)
            self.save_state(tg_seen=self.tg_seen)
            log(f"[{self.name}] telegram: confirmed the updates Hermes had already taken, up to id {best}")
            return best
        except Exception as exc:
            log(f"[{self.name}] confirm_handled failed: {type(exc).__name__}")
            return None
        finally:
            self.tg_paused = False

    def sentinel_loop(self):
        while True:
            try:
                if not self.tg_on:      # disconnected on the keys page: idle until a token comes back
                    time.sleep(20)
                    continue
                if self.brain_up() or self.booting:
                    time.sleep(10 if self.brain_up() else 2)
                    continue
                if self.tg_paused:
                    time.sleep(1)
                    continue
                # Short long-poll: a poll still in flight when Hermes starts delays Hermes's own first getUpdates.
                # No offset: peeking must not confirm anything an allowed person sent (Hermes still has to get it).
                res = self.tg("getUpdates", {"timeout": 2 if self.tg_api else 8, "limit": 100}, timeout=25)
                ups = res.get("result", [])
                hit = None
                lead_junk = None    # newest update_id of the junk that precedes every update of an allowed person
                lead = True
                for u in ups:
                    kind, msg = update_kind(u, self.tg_allowed)
                    if kind == "live":
                        self.warn_live_location(msg)
                    if kind == "real":
                        lead = False    # even one already answered (<= tg_seen) may still be unread by Hermes: keep it queued
                        if u.get("update_id", 0) > self.tg_seen:
                            hit = (u, msg)
                            break
                    elif lead:          # junk, or a live-location refresh (never wakes anybody; confirmed with the leading junk so they cannot fill the page)
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
                if hit and time.time() < self.tg_retry_at:
                    hit = None          # a failed wake retries later (back-off), not on every poll
                    time.sleep(2)
                if hit:
                    u, msg = hit
                    prev_seen = self.tg_seen
                    self.tg_seen = u.get("update_id", 0)
                    self.save_state(tg_seen=self.tg_seen)
                    # What woke it, never what was said: a stack once woke 15-23 s after every /dormir and the log could not say whether a
                    # person wrote or an old update came back. An age far above the time since the stop means a redelivery.
                    kind = next((k for k in ("message", "edited_message", "channel_post", "callback_query") if k in u), "update")
                    sent = msg.get("date")
                    log(f"[{self.name}] telegram wake: update {u.get('update_id')} ({kind}{', a command' if str(msg.get('text', ''))[:1] == '/' else ''}), "
                        f"sent {round(time.time() - sent)}s ago" if isinstance(sent, (int, float)) else
                        f"[{self.name}] telegram wake: update {u.get('update_id')} ({kind}), no date")
                    chat = (msg.get("chat") or msg.get("message", {}).get("chat") or {}).get("id")
                    if chat is not None:
                        self.say(chat, f"⏳ Encendiendo Hermes… tarda unos {self.boot_estimate()} s. Tu mensaje quedó guardado, no hace falta repetirlo.")
                    threading.Thread(target=self.wake_for_telegram, args=(chat, u.get("update_id", 0), prev_seen), daemon=True).start()
                    time.sleep(3)
            except Exception as exc:
                log(f"[{self.name}] sentinel error: {type(exc).__name__}")
                time.sleep(5)

    # ---- wake ----
    def run_hooks(self, reason, chat_id):
        if reason != "task":
            return self._run_hooks(reason, chat_id)
        if not self.count_task_try():
            return
        self._run_hooks(reason, chat_id)
        if self.read_task_request() is None:   # the hook took the request: a clean slate for the next one
            self.task_tries = [None, 0]

    def _run_hooks(self, reason, chat_id):
        if not os.path.isdir(HOOKS_DIR):
            return
        for f in sorted(os.listdir(HOOKS_DIR)):
            path = os.path.join(HOOKS_DIR, f)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                try:
                    env = dict(os.environ, WAKE_NAME=self.name, WAKE_REASON=reason, WAKE_CHAT_ID=str(chat_id or ""))
                    r = subprocess.run([path], env=env, capture_output=True, text=True, timeout=120)
                    log(f"[{self.name}] hook {f}: rc={r.returncode}")
                    if reason == "task":   # the run starter's own lines (stack, counts, error class, never text or keys) belong in the journal
                        for line in r.stdout.splitlines()[-3:]:
                            log(f"[{self.name}] hook {f}: {line[:200]}")
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

    def wake_for_telegram(self, chat, update_id, prev_seen):
        """wake() for a Telegram message; on a failed boot the message triggers again later instead of waiting for a new one."""
        self.wake("telegram", False, chat)
        if not self.wake_failed:
            self.tg_retry_n = 0
            return
        with self.state_lock:
            if self.tg_seen != update_id:   # a newer message already moved it: that one carries the retry
                return
            self.tg_retry_n = min(self.tg_retry_n + 1, 3)
            delay = (60, 120, 300)[self.tg_retry_n - 1]
            self.tg_retry_at = time.time() + delay
            self.tg_seen = prev_seen
        self.save_state(tg_seen=prev_seen)
        log(f"[{self.name}] telegram wake failed: update {update_id} will wake it again in {delay}s")

    def wake(self, reason, want_web=False, chat_id=None):
        self.wake_failed = False
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
                if not self.admit(need_brain, need_web, chat_id, patient=reason not in ("cron", "task")):
                    if reason == "cron":
                        self.cron_due = time.time() + CFG["cron"]["retry_seconds"]
                        log(f"[{self.name}] cron wake postponed {CFG['cron']['retry_seconds']}s: not enough free memory (avail={mem_available_mb()}MB)")
                        return
                    if reason == "task":   # the request file stays: the task waits on the board, nobody is told, the next try is later
                        self.task_retry_at = time.time() + CFG["task"]["retry_seconds"]
                        log(f"[{self.name}] task wake postponed {CFG['task']['retry_seconds']}s: not enough free memory (avail={mem_available_mb()}MB)")
                        return
                    log(f"[{self.name}] wake ({reason}) gave up: no memory")
                    ops("alert", f"wake:{self.name}:nomem", f"{self.name}: no pudo despertar ({reason}) por falta de "
                                                            f"memoria (libre {mem_available_mb()} MB). La persona recibió el aviso.")
                    self.wake_failed = True
                    for c in list(self.chats):
                        self.say(c, "⚠️ El servidor no tiene memoria libre ahora mismo. " + (
                            "Tu mensaje sigue guardado: lo vuelvo a intentar solo en unos minutos." if reason == "telegram"
                            else "Probá de nuevo en unos minutos."))
                    self.chats.clear()
                    return
                self.boot_t0 = time.time()
                self.last_activity = time.time()
                self.cron_only = reason in ("cron", "task")
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
                    # Idle time counts from "ready", not from the wake decision: a stack (idle brain 120 s) took
                    # 149 s on its first boot on a new image and was put to sleep 18 s after "ready", before Hermes took the
                    # queued message.
                    self.last_activity = time.time()
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
                self.wake_failed = True
                if reason == "task":
                    self.task_retry_at = time.time() + CFG["task"]["retry_seconds"]
                for c in list(self.chats):
                    self.say(c, "⚠️ Hermes está tardando más de lo normal en encender. " + (
                        "Tu mensaje sigue guardado: lo vuelvo a intentar solo en un minuto." if reason == "telegram"
                        else "Probá de nuevo en un minuto."))
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
            elif reason == "task":   # same for a task run, with its own (longer) hold: an LLM working a task is slower than a cron script
                self.cron_hold_until = time.time() + CFG["task"]["hold_seconds"]
            hook_args = (reason, chat)
        finally:
            self.booting = False
            self.queued = False
        if hook_args:
            self.run_hooks(*hook_args)
            if hook_args[0] == "task":
                self.task_retry_at = time.time() + CFG["task"]["retry_seconds"]

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

    def hold_seconds(self):
        return min(HOLD_MAX_S, max(HOLD_MIN_S, self.boot_estimate() + HOLD_EXTRA_S))

    def wake_and_hold(self, hold_s):
        """A person's message is waiting: wake the web tier (same wake(), so the wake lock, the boot queue and the RAM guard apply) and
        wait up to hold_s for the stack to be ready. "ready", "failed" (the wake gave up: no memory, start error, 240 s) or "timeout"
        (still booting or queued; the wake goes on and the person's next try finds it up)."""
        done = threading.Event()
        def go():
            try:
                self.wake("web", True)
            finally:
                done.set()
        threading.Thread(target=go, daemon=True).start()
        end = time.time() + hold_s
        while time.time() < end:
            if self.public_state() == "ready":
                return "ready"
            if done.is_set() and self.wake_failed and not self.booting:   # wake() clears wake_failed first thing: this one is ours
                return "failed"
            time.sleep(0.5)
        return "timeout"

    # ---- sleep ----
    def sleep_web(self):
        self.stopping = True
        try:
            log(f"[{self.name}] stopping web")
            for c in reversed(self.web):
                docker("stop", "-t", "20", c, timeout=60)
        finally:
            self.stopping = False

    def scan_incidents(self):
        """Alert the operator about INCIDENTS the brain logged since the last scan (one alert per kind, notify's quiet time)."""
        since = self.incidents_scanned or self.brain_started or time.time() - 600
        now = time.time()
        r = docker("logs", "--since", str(int(since)), self.brain)
        self.incidents_scanned = now
        out = r.stdout + r.stderr
        for kind, needle, what in INCIDENTS:
            n = out.count(needle)
            if n:
                log(f"[{self.name}] incident {kind}: {n} log line(s)")
                ops("alert", f"incident:{self.name}:{kind}", f"⚠️ {self.name}: {what} ({n} línea(s) en el log de Hermes).")

    def sleep_brain(self):
        self.scan_incidents()   # the last minutes before the stop, or they are never read
        self.stopping = True
        try:
            log(f"[{self.name}] stopping brain")
            docker("stop", "-t", "45", self.brain, timeout=90)
        finally:
            self.stopping = False

    def tick(self):
        """Idle accounting for this stack (called every TICK seconds)."""
        self.refresh_telegram()
        if self.booting or self.stopping:
            return
        self.ticks = getattr(self, "ticks", 0) + 1
        web_up, brain_up = self.web_up(), self.brain_up()
        if brain_up and self.ticks % 10 == 0:
            self.notify_fast_jobs(self.due_jobs())
            self.scan_incidents()
        # cron_only (short idle limit after a cron wake) ends when a person shows up: a UI request, or something busy
        # once the cron's own hold time is over (busy() is True during the hold because of the cron's own turn).
        if web_up and self.ui_requests():
            self.last_activity = time.time()
            self.cron_only = False
        elif (web_up or brain_up) and (reasons := self.busy_reasons()):
            self.last_activity = time.time()
            # a task run alone keeps the short idle limit: nobody is using the stack, it only must not be cut mid-run
            if time.time() >= self.cron_hold_until and reasons != [TASK_RUN_REASON]:
                self.cron_only = False
        if os.path.exists(NO_SLEEP):
            return
        if brain_up:   # the person said "dormite": the agent asked for a real stop with `dormir`
            req = self.sleep_request()
            if req is not None:
                turn_active = bool(self.gateway_state().get("active_agents"))
                reasons = [] if req.get("force") else self.busy_reasons(ignore_gateway=True)
                what = sleep_decision(req, time.time(), turn_active, bool(reasons))
                if what == "drop":
                    log(f"[{self.name}] sleep request dropped (stale or work started: {', '.join(reasons) or 'stale'})")
                    self.clear_sleep_request()
                    self.tell_person("No me pude dormir: " + (", ".join(reasons) if reasons else "el pedido quedó viejo") +
                                     ". Si querés que me apague igual, /sleep now (corta lo que corre).")
                elif what == "sleep":
                    log(f"[{self.name}] sleep on request ({req.get('mode')}{', forced' if req.get('force') else ''})")
                    self.clear_sleep_request()
                    if web_up:
                        self.sleep_web()
                    self.sleep_brain()
                    # The person's last message is written here, once the stop is a fact, not by the agent before it
                    stopped = not self.brain_up()
                    if not stopped:
                        ops("alert", f"sleep:{self.name}:notstopped", f"{self.name}: pidió dormir y el contenedor sigue arriba tras docker stop")
                    else:
                        self.confirm_handled(float(req.get("ts") or time.time()))   # before the sentinel can see the command again
                    told = self.tell_person(sleep_notice(stopped, req.get("mode"), notice_lang(req.get("lang"), self.lang), time.strftime("%H:%M", time.gmtime())))
                    log(f"[{self.name}] sleep notice: container {'stopped' if stopped else 'STILL UP'}, accepted by {told} of {len(getattr(self, "tg_allowed", ()))} allowed person(s)")
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
            jid, name = j.get("id", "?"), j.get("name", "?")
            offset = iso_offset(j.get("next_run_at"))
            daily = sched.get("kind") == "cron" and bool(DAILY_CRON_RE.match(str(sched.get("expr", "")).strip()))
            self.job_info[jid] = (name, offset, daily)
            if nxt and daily and offset is not None and name in (CFG.get("night") or {}).get("jobs", ()):
                nxt = night_next(nxt, offset, self.night_done.get(jid))   # tonight's fixed run is not woken for once the early run took it
            if nxt:
                out.append((jid, name, nxt, every))
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

    # ---- night jobs (see "Night jobs" at the top) ----
    def night_tick(self):
        nc = CFG.get("night") or {}
        if not nc.get("jobs") or self.booting or self.stopping or self.night_starting:
            return
        now = time.time()
        if now - self.night_jobs[0] >= NIGHT_READ_S:
            self.night_jobs = (now, self.due_jobs())
        for jid, name, nxt, _ in self.night_jobs[1]:
            _, offset, daily = self.job_info.get(jid, (name, None, False))
            if name not in nc["jobs"] or not daily or offset is None:
                continue
            up = self.brain_up()
            what = night_decision(now, nxt, offset, self.night_done.get(jid), nc["after"], now - self.last_activity,
                                  nc["idle_minutes"] * 60, up, self.night_retry_at)
            if what in ("none", "wait") or (what == "run" and self.busy()):
                continue
            with PLAN_LOCK:   # one cron-like wake per slot across all stacks
                if now < LAST_CRON_WAKE[0] + CFG["cron"]["slot_seconds"] or any(s.booting for s in STACKS.values()):
                    continue
                LAST_CRON_WAKE[0] = now
            self.night_starting = True
            key = night_key(night_next(nxt, offset, self.night_done.get(jid)), offset)
            log(f"[{self.name}] night job {name}: idle {int((now - self.last_activity) // 60)} min after {nc['after']}, "
                f"{'waking to start' if what == 'wake' else 'starting'} it early")
            threading.Thread(target=self.night_run, args=(jid, name, key, what == "wake"), daemon=True).start()
            return

    def night_run(self, jid, name, key, wake):
        retry = CFG["cron"]["retry_seconds"]
        try:
            if wake:
                self.cron_pending_ids = [jid]
                self.wake("cron", False, None)
                if not self.brain_up():
                    self.night_retry_at = time.time() + retry
                    log(f"[{self.name}] night job {name}: the wake did not happen, retry in {retry}s")
                    return
            self.cron_hold_until = max(self.cron_hold_until, time.time() + CFG["cron"]["hold_seconds"])   # until Hermes's next tick runs it
            r = docker("exec", self.brain, "hermes", "cron", "run", jid)
            if r.returncode != 0:
                self.night_retry_at = time.time() + retry
                log(f"[{self.name}] night job {name}: hermes cron run failed (rc={r.returncode}), retry in {retry}s")
                return
            self.night_done[jid] = key
            self.night_done = {k: v for k, v in self.night_done.items() if k in self.job_info}   # forget removed jobs
            self.save_state(night_done=self.night_done)
            self.night_jobs = (0.0, [])   # re-read: next_run_at moved
            log(f"[{self.name}] night job {name}: started for the night of {key}")
        finally:
            self.night_starting = False

    # ---- tasks (ops/wake/tareas_hook.py) ----
    def tell_done(self, req):
        """The person hears, from this bot, that a task it filed came back (once per task and kind; a waker restart may repeat it once)."""
        told = self.__dict__.setdefault("done_told", set())
        notes = done_notices(req, notice_lang(None, getattr(self, "lang", "")), told)   # getattr: test shims skip __init__
        if not notes:
            return
        for key, _ in notes:
            told.add(key)
        sent = self.tell_person("\n".join(text for _, text in notes))
        log(f"[{self.name}] told the person {len(notes)} task result(s) came back, accepted by {sent}")

    def read_task_request(self):
        """The receiver's request file as a dict, None when there is none, or False when it is unreadable (dropped by task_decision)."""
        try:
            fd = os.open(self.task_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        except OSError:
            return False
        try:
            with os.fdopen(fd, "rb") as f:
                raw = f.read(TASK_REQUEST_MAX_BYTES + 1)
            return json.loads(raw) if len(raw) <= TASK_REQUEST_MAX_BYTES else False
        except (OSError, ValueError):
            return False

    def drop_task_request(self):
        try:
            os.unlink(self.task_file)
        except OSError:
            pass

    def run_task_hooks(self):
        """The brain is already up (no wake, so wake() runs no hooks): run the "task" hooks, then hold the stack awake for the run."""
        try:
            self.run_hooks("task", None)
        finally:
            now = time.time()
            self.cron_hold_until = max(self.cron_hold_until, now + CFG["task"]["hold_seconds"])
            self.task_retry_at = now + CFG["task"]["retry_seconds"]   # a hook that left the request behind is not rerun on every tick
            self.task_starting = False

    def count_task_try(self):
        """Count one run of the task hooks for the pending request; False (and the request dropped, the operator told) past task.max_tries.
        Kept in memory, not in the request file, so it cannot race with the receiver rewriting that file."""
        req = self.read_task_request()
        if not isinstance(req, dict):
            return True   # nothing pending (or unreadable, which task_decision drops): the hooks have nothing to repeat
        first = req.get("first_ts")
        if self.task_tries[0] != first:
            self.task_tries = [first, 0]
        self.task_tries[1] += 1
        cap = int(CFG["task"].get("max_tries", 5))
        if self.task_tries[1] <= cap:
            return True
        log(f"[{self.name}] task request dropped: the task hooks ran {cap} times and it is still pending (hook not executable or crashing?)")
        ops("alert", f"task:{self.name}:stuck", f"{self.name}: un pedido de tarea no logró arrancar tras {cap} intentos del waker; lo descarté "
                                                f"(la tarea sigue abierta en el tablero). Revisar el hook 40-task-run y los logs de tareas_run.")
        self.drop_task_request()
        self.task_tries = [None, 0]
        return False

    def poll_task_run(self):
        """running | finished | unknown, asked of the run starter (it holds the know-how of the API and reads the key itself, never this process)."""
        if time.time() - self.task_poll[0] < CFG["task"].get("poll_seconds", 30):
            return self.task_poll[1]
        word = "unknown"
        try:
            r = subprocess.run([sys.executable, TASK_RUN_SCRIPT, "--stack", self.name, "--check"], capture_output=True, text=True, timeout=60,
                               env=dict(os.environ, WAKE_STATE_DIR=STATE_DIR, WAKE_CONFIG=CONFIG))
            last = (r.stdout.strip().splitlines() or [""])[-1].strip()
            word = last if last in ("running", "finished") else "unknown"
        except (OSError, subprocess.SubprocessError):
            pass
        self.task_poll = (time.time(), word)
        return word

    def report_task_run(self):
        """The person gets the finished task run's own answer through this bot (a run started by the board has no chat to answer in).
        The run starter fetches it (it holds the API know-how and the key); only its text comes back here."""
        try:
            r = subprocess.run([sys.executable, TASK_RUN_SCRIPT, "--stack", self.name, "--report"], capture_output=True, text=True, timeout=60,
                               env=dict(os.environ, WAKE_STATE_DIR=STATE_DIR, WAKE_CONFIG=CONFIG))
            d = json.loads((r.stdout.strip().splitlines() or ["{}"])[-1])
        except (OSError, subprocess.SubprocessError, ValueError):
            return
        text = d.get("text") if isinstance(d, dict) and isinstance(d.get("text"), str) else ""
        if not text.strip():
            log(f"[{self.name}] task run finished with no answer to pass on")
            return
        sent = self.tell_person("📋 " + text)
        log(f"[{self.name}] task run's answer ({len(text)} chars, status {d.get('status') or '?'}) passed to the person, accepted by {sent}")

    def task_run_busy(self):
        """A task run started by tareas_run.py is still going (see task_run_decision). Removes the record once it is over or too old."""
        try:
            fd = os.open(getattr(self, "task_run_file", ""), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)   # getattr: test shims skip __init__
        except OSError:
            return False
        try:
            with os.fdopen(fd, "rb") as f:
                rec = json.loads(f.read(4096))
        except (OSError, ValueError):
            rec = None
        seen = []

        def poll():
            word = self.poll_task_run()
            seen.append(word)
            return word
        what = task_run_decision(rec, time.time(), poll, CFG["task"]["hold_seconds"], CFG["task"].get("max_run_seconds", 3600))
        if what == "drop":
            if seen and seen[-1] == "finished":
                self.report_task_run()   # before the record (and its run id) goes away
            try:
                os.unlink(self.task_run_file)
            except OSError:
                pass
            self.task_poll = (0.0, "unknown")
        return what == "busy"

    def task_tick(self):
        req = self.read_task_request()
        if req is None:
            return
        brain_up = self.brain_up()
        what = task_decision(req, time.time(), self.task_retry_at,
                             self.booting or self.stopping or self.task_starting, brain_up,
                             brain_up and self.busy(), CFG["task"]["max_age_seconds"])
        if what == "drop":
            log(f"[{self.name}] task request dropped (stale or unreadable): the task stays on the board")
            self.drop_task_request()
        if what in ("wake", "run"):
            self.tell_done(req)
        if what == "wake":
            log(f"[{self.name}] waking for a task request")
            threading.Thread(target=self.wake, args=("task", False, None), daemon=True).start()
        elif what == "run":
            log(f"[{self.name}] task request: stack is awake and quiet, starting the run")
            self.task_starting = True
            threading.Thread(target=self.run_task_hooks, daemon=True).start()


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
                s.task_tick()
                s.night_tick()   # last: a bad "night" config must not stop the task tick
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


def is_person_send(method, path, headers):
    """A logged-in person sending a message: POST to a send endpoint with the `token` cookie or an Authorization header. A bot, a scanner
    or an old tab's background POST (settings, timezone, tags) is not, and stays a plain 503."""
    if method != "POST" or not SEND_PATH.match(path.split("?")[0]):
        return False
    return bool(re.search(r"(?:^|;\s*)token=", headers.get("Cookie", "")) or headers.get("Authorization"))


def replay_allowed(upstream_hint, state):
    """May the held request be replayed to Open WebUI without risking a duplicate? Only if Open WebUI never saw it. The front's @wake
    location passes `$upstream_status` as X-Wake-Upstream-Status: 502 (or "-", the DNS lookup of a stopped container failing) means
    nothing was received there; 503/504 mean Open WebUI itself answered, and a replay would send the message twice. Without the header
    (a front not yet updated) the stack must not be running."""
    if upstream_hint is None:
        return state != "ready"
    return all(t in ("502", "-") for t in re.split(r"[,\s]+", upstream_hint.strip() or "-") if t)


def read_body(rfile, headers, limit=MAX_HOLD_BODY):
    """The request body (Content-Length or chunked) or None when it is longer than limit or ends early."""
    if "chunked" in headers.get("Transfer-Encoding", "").lower():
        out = b""
        while True:
            size = int((rfile.readline(100) or b"x").split(b";")[0].strip() or b"x", 16)
            if size == 0:
                while rfile.readline(1000) not in (b"\r\n", b"\n", b""):
                    pass
                return out
            out += rfile.read(size)
            rfile.readline(10)
            if len(out) > limit:
                return None
    n = int(headers.get("Content-Length") or 0)
    if n > limit:
        return None
    data = rfile.read(n) if n else b""
    return data if len(data) == n else None


def replay_to_web(stack, method, path, headers, body, deadline):
    """Send the held request to the stack's Open WebUI and return (response, connection); a connection
    refused right after "ready" is retried until deadline (the body is whole in memory, so a retry is safe). Raises OSError after that."""
    import http.client
    fwd = {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}
    fwd["Content-Length"] = str(len(body))
    port = int(stack.web_health_port)
    last = OSError("no address for the web container")
    while True:
        for ip in ips(stack.web[0]):
            conn = http.client.HTTPConnection(ip, port, timeout=5)
            try:
                conn.connect()
                conn.sock.settimeout(3600)   # a turn can run for many minutes, as in the front (proxy_read_timeout)
                conn.request(method, path, body=body, headers=fwd)
                resp = conn.getresponse()
                return resp, conn
            except OSError as exc:
                last = exc
                conn.close()
        if time.time() >= deadline:
            raise last
        time.sleep(1)


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

        def _fail_send(self, code, why, text):
            log(f"[{stack.name}] held message NOT delivered ({why}): {self.command} {self.path.split('?')[0]}")
            return self._send(code, json.dumps({"error": why, "detail": text}), "application/json", {"Retry-After": "30"})

        def do_POST(self):
            """A person's message sent while the stack sleeps: wake, hold, replay (see the design comment). Anything else is a plain 503."""
            path = self.path
            if not is_person_send("POST", path, self.headers) or not replay_allowed(
                    self.headers.get("X-Wake-Upstream-Status"), stack.public_state()):
                return self._asleep()
            text = HOLD_FAIL[notice_lang(None, stack.lang)]
            try:
                body = read_body(self.rfile, self.headers)
            except (ValueError, OSError):
                body = None
            if body is None:   # too big, cut short, or the front did not pass the body on
                return self._fail_send(413 if self.headers.get("Content-Length", "0").isdigit()
                                       and int(self.headers["Content-Length"]) > MAX_HOLD_BODY else 400, "body_unavailable", text)
            t0 = time.time()
            hold = stack.hold_seconds()
            log(f"[{stack.name}] holding {self.command} {path.split('?')[0]} ({len(body)} bytes) for a wake, up to {hold}s")
            state = stack.wake_and_hold(hold)
            if state != "ready":
                return self._fail_send(503, f"wake_{state}", text)
            try:
                resp, conn = replay_to_web(stack, "POST", path, self.headers, body, time.time() + REPLAY_GRACE_S)
            except OSError as exc:
                log(f"[{stack.name}] held message: Open WebUI not reachable after the wake: {exc}")
                return self._fail_send(503, "web_unreachable", text)
            stack.last_activity = time.time()
            log(f"[{stack.name}] held {path.split('?')[0]} replayed after {time.time() - t0:.1f}s: {resp.status}")
            try:   # stream the answer as it arrives (an SSE chat turn), HTTP/1.0 style: no length, the connection closes at the end
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in HOP_BY_HOP:
                        self.send_header(k, v)
                if resp.getheader("Content-Length"):
                    self.send_header("Content-Length", resp.getheader("Content-Length"))
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                while True:
                    chunk = resp.read1(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except OSError:   # the person closed the tab: nothing to deliver to
                pass
            finally:
                conn.close()
                stack.last_activity = time.time()

        do_PUT = do_PATCH = do_DELETE = do_HEAD = lambda self: self._asleep()
    return Handler


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def listen(s, wait_s=120):
    """Server on the stack's address, the gateway of its Docker network. Right after a host boot Docker may not have
    brought that network up yet (EADDRNOTAVAIL, seen after a power cut: the unit failed and its alert
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
    CFG["night"] = {"after": "23:00", "idle_minutes": 60, "jobs": ["jobnight"], **CFG.get("night", {})}
    CFG["task"] = {"max_age_seconds": 6 * 3600, "hold_seconds": 600, "retry_seconds": CFG["cron"]["retry_seconds"],
                   "max_tries": 5, "max_run_seconds": 3600, "poll_seconds": 30, **CFG.get("task", {})}
    global BOOT_SEM
    BOOT_SEM = threading.BoundedSemaphore(int(CFG.get("max_parallel_boots", 1)))
    for i, c in enumerate(CFG["stacks"]):
        STACKS[c["name"]] = Stack(c, i)
    for s in STACKS.values():
        threading.Thread(target=serve, args=(s,), daemon=True).start()   # one thread per stack: each retries its own bind
        s.start_sentinel()
        log(f"[{s.name}] on {s.bind}:{s.port} web={s.web} brain={s.brain} telegram={'on' if s.tg_on else 'off'} "
            f"idle web={s.idle_web}s brain={s.idle_brain}s")
    log(f"budget: reserve={CFG['reserve_mb']}MB critical={CFG['critical_mb']}MB max_awake={CFG['max_awake']} "
        f"cron={CFG['cron']} avail={mem_available_mb()}MB")
    threading.Thread(target=watchdog_loop, daemon=True).start()
    sleeper_loop()


if __name__ == "__main__":
    main()
