#!/usr/bin/env python3
"""Early alert: a person's bot is failing them, and the operator hears within minutes (not at the next review).

Every 5 minutes (early-alert.timer) this reads, per stack of ops/wake/stacks.json, only CATEGORIES AND COUNTS and scores them:
  * the stack's sink /workdir/.early-signals.jsonl (router, announced-action patch, jobpush, boot: see ops/EARLY_ALERT.md), a small
    host-readable file; when it is root 0600 (an old or odd file) it is read through `docker cp`, which also works while the stack sleeps;
  * the epoch files /workdir/.last_human, .last_reply, .last_model_call (the "unanswered" check);
  * ~/.local/state/telemetry.db (telemetry.py): failed API calls, failed / empty turns, dead links.
No chat text, URL, file name, key or id is ever read: the files do not contain them. The agent can write /workdir as root, so every file is
opened O_NOFOLLOW, must be a regular file, and only its last 256 KB are read; a forged line can at worst cause a false alert.

Score over a sliding window (default 30 min): sum over categories of min(weight * count, CAP=4). Alert at >= 3.0. So a single complaint
(2) does not alert, two nudges and a complaint (4) do, and the weight-3 categories alone do. model_err counts only beside another
category. After an alert the stack is silent for 2 h unless the score escalates (>= last*1.5+2, 30 min apart); when the score has been
0 for 60 min the alert resolves. soul_cut and scan_zero are standing conditions: their own alert, 24 h cooldown, no escalation, resolved
when they age out.

SAFE BY DEFAULT: nothing is sent until EARLY_ALERT_NOTIFY=1 is in ops/ops.env (or the environment). Until then every run only prints the
per-stack table to the journal (the same as --dry-run) and writes no state, so installing the timer can never spam.

  early_alert.py                 live (prints only, unless EARLY_ALERT_NOTIFY=1)
  early_alert.py --dry-run       the per-stack table: events, score, decision, would-be text; no state write, no notify
  early_alert.py --stack NAME --window MIN --json
Environment (tests): EARLY_ALERT_STATE, EARLY_ALERT_STACKS, EARLY_ALERT_TELEMETRY, EARLY_ALERT_NOW, EARLY_ALERT_NOTIFY.
Exit: 0, or 1 only when every stack failed (a flaky stack must not fail the unit).
"""
import argparse, collections, fcntl, json, os, re, sqlite3, stat, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, HERE)
import notify  # noqa: E402

AIBRIDGE = os.path.dirname(HERE)
STACKS = os.environ.get("EARLY_ALERT_STACKS", os.path.join(HERE, "wake", "stacks.json"))
STATE = os.environ.get("EARLY_ALERT_STATE", os.path.expanduser("~/.local/state/early_alert.json"))
TELEMETRY = os.environ.get("EARLY_ALERT_TELEMETRY", os.path.expanduser("~/.local/state/telemetry.db"))

WINDOW_MIN = 30
CAP = 4.0                       # points one category can add inside a window
THRESHOLD = 3.0
COOLDOWN_S = 2 * 3600
ESCALATE_AFTER_S = 30 * 60
QUIET_RESOLVE_S = 60 * 60
STANDING_COOLDOWN_S = 24 * 3600
EVENT_MAX_AGE_S = 24 * 3600
STANDING_MAX_AGE_S = 36 * 3600  # a once-a-night line must stay visible past a run that comes a little later the next day, else the
                                # condition would "resolve" and re-alert a few minutes later while it never cleared
READ_TAIL = 256 * 1024
MAX_LINES = 2000
SINK = ".early-signals.jsonl"
SINK_OLD = ".early-signals.1.jsonl"
UNANSWERED_S = 1800             # no reply and no model call for this long (a long transcode or render makes no model call for many minutes)
BUSY_MARKER = ("jobfinder", "data", ".jobpush-running")   # as the waker reads it: a fresh marker is a run that is working
BUSY_MARKER_MIN = 90
UNANSWERED_MAX_AGE_S = 3 * 3600
BOOT_GRACE_S = 180              # a brain that has been up this short a time has not had the chance to answer yet

# Fixed vocabulary. Every writer (router, patch, jobpush, start_hermes.sh) must stay inside it: early_signals_selftest.py checks.
SINK_CATS = ("nudge", "nudge_ignored", "complaint", "repeat", "deadpage", "key_notice", "bad_end", "wrong_lang", "scan_zero", "soul_cut")
TELEMETRY_CATS = ("model_err", "failed_turn", "empty_turn", "links_dead")
CATS = SINK_CATS + TELEMETRY_CATS + ("unanswered",)
SRCS = ("router", "patch", "jobpush", "boot", "plugin")
STANDING = ("scan_zero", "soul_cut")
# repeat is 1 per repeated turn (a person who sends the same long message four times is stuck; three identical acknowledgements are not),
# deadpage is 2 (a pasted error title or a developer question about a 404 must not alert alone; it counts beside another signal)
WEIGHT = {"nudge": 1, "nudge_ignored": 2, "complaint": 2, "repeat": 1, "deadpage": 2, "key_notice": 1, "bad_end": 1, "wrong_lang": 1,
          "scan_zero": 3, "soul_cut": 3, "unanswered": 3, "model_err": 0.5, "failed_turn": 2, "empty_turn": 2, "links_dead": 1}
KEY_NOTICE_WEIGHT = {"refused": 3, "none": 1}
N_MAX = {"soul_cut": 1_000_000}   # soul_cut's n is the SOUL.md length in characters; every other n is a small count
V_MAX = 1_000_000
K_RE = re.compile(r"^[a-z0-9_]{1,16}$")

Event = collections.namedtuple("Event", "ts cat n k v src", defaults=(None,))
SAME_REPLY_S = 60       # a router line and a plugin line for the same reply are written seconds apart (the stream ends, then Hermes finishes the turn)


# ---------------------------------------------------------------- reading the sink (hostile-file safe)

def parse_line(line, now=None):
    """An Event from one sink line, or None for anything that is not exactly what the writers produce: bad JSON, an unknown category or
    key, a ts outside [now-24h, now+60 s], a count or value out of bounds, a k that is not a short [a-z0-9_] word."""
    now = time.time() if now is None else now
    try:
        d = json.loads(line)
    except ValueError:
        return None
    if not isinstance(d, dict) or not set(d) <= {"ts", "cat", "n", "k", "v", "src"}:
        return None
    ts, cat, n = d.get("ts"), d.get("cat"), d.get("n", 1)
    isint = lambda x: isinstance(x, int) and not isinstance(x, bool)
    if cat not in SINK_CATS or not isint(ts) or not isint(n) or not 1 <= n <= N_MAX.get(cat, 20):
        return None
    if not now - (STANDING_MAX_AGE_S if cat in STANDING else EVENT_MAX_AGE_S) <= ts <= now + 60:
        return None
    k, v = d.get("k"), d.get("v")
    if k is not None and not (isinstance(k, str) and K_RE.match(k)):
        return None
    if v is not None and not (isint(v) and 0 <= v <= V_MAX):
        return None
    if d.get("src") is not None and d["src"] not in SRCS:
        return None
    return Event(ts, cat, n, k, v, d.get("src"))


def read_small(path, limit):
    """The last `limit` bytes of a regular file, no symlink followed, never blocking. None when absent / not a regular file / unreadable.
    PermissionError is raised (the caller falls back to docker cp)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except PermissionError:
        raise
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None
        if st.st_size > limit:
            os.lseek(fd, st.st_size - limit, os.SEEK_SET)
        return os.read(fd, limit)
    except OSError:
        return None
    finally:
        os.close(fd)


TAR_SLACK = 4096                # a tar of a file of `limit` bytes is at most limit + 512 (header) + 511 (padding) + 1024 (trailer)
CP_TIMEOUT_S = 30


def cp_read(brain, path, limit=READ_TAIL):
    """The file through `docker cp` (root 0600 files, stopped containers), BOUNDED: at most limit + 4 KB of the tar stream is ever held
    in memory, then the copy is killed and the file counts as unreadable (None). key_check.cp_out would buffer a whole multi-GB file the
    agent made on purpose (it runs as root in the container and writes /workdir) before any size check could apply."""
    import io, subprocess, tarfile, threading
    try:
        p = subprocess.Popen(["docker", "cp", f"{brain}:{path}", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return None
    timer = threading.Timer(CP_TIMEOUT_S, p.kill)
    timer.start()
    try:
        data = p.stdout.read(limit + TAR_SLACK + 1)
        if len(data) > limit + TAR_SLACK:
            p.kill()
            return None
        if p.wait() != 0:
            return None
    except OSError:
        return None
    finally:
        timer.cancel()
        if p.poll() is None:
            p.kill()
        p.stdout.close()
        p.wait()
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            m = t.next()
            if not m or not m.isreg() or m.size > limit:
                return None
            return t.extractfile(m).read()
    except (tarfile.TarError, AttributeError):
        return None


class _Capped:
    """A read-only stream that fails after `cap` bytes: tarfile in streaming mode stops there however large the entries are."""
    def __init__(self, f, cap):
        self.f, self.left = f, cap

    def read(self, n=-1):
        if n is None or n < 0 or n > self.left:
            n = self.left
        if n <= 0:
            raise OSError("cap reached")
        data = self.f.read(n)
        self.left -= len(data)
        return data


def cp_peek(brain, path, cap=64 * 1024, max_members=50):
    """[(name, mtime, is_regular)] of the first entries of `docker cp brain:path -` (a file or a directory), reading at most `cap` bytes
    of the stream: only the tar headers matter here (what exists and how old), never the contents. [] when absent or on any error."""
    import subprocess, tarfile, threading
    try:
        p = subprocess.Popen(["docker", "cp", f"{brain}:{path}", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return []
    timer = threading.Timer(CP_TIMEOUT_S, p.kill)
    timer.start()
    out = []
    try:
        with tarfile.open(fileobj=_Capped(p.stdout, cap), mode="r|") as t:
            for m in t:
                out.append((m.name, m.mtime, m.isreg()))
                if len(out) >= max_members:
                    break
    except (OSError, tarfile.TarError, EOFError):
        pass
    finally:
        timer.cancel()
        if p.poll() is None:
            p.kill()
        p.stdout.close()
        p.wait()
    return out


def busy_now(workdir, brain, now):
    """Is something long-running working in the stack (so a silent model is expected)? A registered job (/workdir/jobs/*.json) or a fresh
    job-scan marker, the same two the waker treats as busy. Read host side when /workdir allows it, else through a bounded docker cp
    (never docker exec). Unknown counts as not busy."""
    jobs = os.path.join(workdir, "jobs")
    try:
        with os.scandir(jobs) as it:
            if any(e.name.endswith(".json") and e.is_file(follow_symlinks=False) for e in it):
                return True
    except FileNotFoundError:
        pass
    except OSError:
        if any(n.startswith("jobs/") and n.endswith(".json") and reg for n, _, reg in cp_peek(brain, "/workdir/jobs")):
            return True
    marker = os.path.join(workdir, *BUSY_MARKER)
    try:
        st = os.lstat(marker)
        return stat.S_ISREG(st.st_mode) and now - st.st_mtime <= BUSY_MARKER_MIN * 60
    except FileNotFoundError:
        return False
    except OSError:
        return any(reg and now - mt <= BUSY_MARKER_MIN * 60 for _, mt, reg in cp_peek(brain, "/workdir/" + "/".join(BUSY_MARKER), cap=8192, max_members=1))


def read_file(workdir, name, brain, limit):
    """Bytes of workdir/name (host side, else docker cp), or None. Never raises."""
    try:
        raw = read_small(os.path.join(workdir, name), limit)
    except PermissionError:
        try:
            raw = cp_read(brain, "/workdir/" + name, limit)
        except Exception:
            return None
        if raw is not None:
            raw = raw[-limit:]
    except Exception:
        return None
    return raw


def sink_events(workdir, brain, now):
    """(events, found): found is False when neither sink file exists (an image without the writers: nothing to say, never an alert)."""
    events, found = [], False
    for name in (SINK_OLD, SINK):
        raw = read_file(workdir, name, brain, READ_TAIL)
        if raw is None:
            continue
        found = True
        lines = raw.decode("utf-8", "replace").splitlines()
        if len(raw) >= READ_TAIL and lines:
            lines = lines[1:]                      # the cut may have split the first line
        for ln in lines[-MAX_LINES:]:
            e = parse_line(ln, now)
            if e:
                events.append(e)
    return events, found


def read_epoch(workdir, name, brain, now):
    """The epoch a small file holds, or None (absent, odd, in the future: a forged future time must not hide a stalled turn)."""
    raw = read_file(workdir, name, brain, 64)
    if raw is None:
        return None
    try:
        v = float(raw.decode("ascii", "replace").strip())
    except ValueError:
        return None
    return v if 0 < v <= now + 60 else None


# ---------------------------------------------------------------- telemetry.db and docker

def telemetry_events(stack, since, db=None):
    """Events from telemetry.db (read-only): failed model API calls (not Hermes's background model), failed / empty turns of people's
    channels, links the bot gave that were dead. [] when the db or a table is missing."""
    db = db or TELEMETRY
    if not os.path.exists(db):
        return []
    out = []
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            out += [Event(int(ts), "model_err", 1, None, None) for (ts,) in
                    c.execute("select ts from errors where stack=? and ts>=? and coalesce(model,'')!='local-only'", (stack, since))]
            for ts, failed, empty in c.execute("select ts, failed, empty from turns where stack=? and ts>=? and (failed=1 or empty=1) "
                                               "and coalesce(source,'')!='cron'", (stack, since)):
                if failed:
                    out.append(Event(int(ts), "failed_turn", 1, None, None))
                if empty:
                    out.append(Event(int(ts), "empty_turn", 1, None, None))
            out += [Event(int(ts), "links_dead", 1, None, None) for (ts,) in
                    c.execute("select ts from gw where stack=? and ts>=? and gateway='enlaces' and ok=0", (stack, since))]
        finally:
            c.close()
    except (sqlite3.Error, TypeError, ValueError):
        return out
    return out


def telemetry_wakes_today(stack, since, db=None):
    db = db or TELEMETRY
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            return c.execute("select count(*) from wakes where stack=? and ts>=?", (stack, since)).fetchone()[0]
        finally:
            c.close()
    except (sqlite3.Error, OSError):
        return None


def docker_state(brain):
    """(running, started epoch or None) of a container; (False, None) when it does not exist or docker fails."""
    import subprocess
    try:
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}} {{.State.StartedAt}}", brain], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False, None
    if r.returncode != 0:
        return False, None
    run, _, started = r.stdout.decode().strip().partition(" ")
    ts = None
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)", started)
    if m:
        import calendar
        ts = calendar.timegm(tuple(int(x) for x in m.groups()))
    return run == "true", ts


# ---------------------------------------------------------------- the stack and its score

def stack_paths(s):
    persist = s.get("persist_dir") or os.path.join(AIBRIDGE, "stacks", s["name"], "persist")
    return s.get("workdir") or os.path.join(os.path.dirname(persist), "workdir")


def gather(s, now, since=None):
    """Everything one stack contributes: {events, awake, uptime, epochs, sink_found}. `since`: how far back telemetry rows are read."""
    workdir, brain = stack_paths(s), s.get("brain") or ""
    since = now - 2 * 3600 if since is None else since       # run_stack passes max(2 h, the window)
    ev, found = sink_events(workdir, brain, now)
    epochs = {n: read_epoch(workdir, "." + n, brain, now) for n in ("last_human", "last_reply", "last_model_call")}
    running, started = docker_state(brain) if brain else (False, None)
    ev += telemetry_events(s["name"], since)
    return {"events": ev, "awake": running, "started": started, "epochs": epochs, "sink_found": found,
            "busy": lambda: busy_now(workdir, brain, now)}      # lazy: only asked when everything else says "unanswered"


def unanswered_minutes(info, now):
    """Minutes of silence when the person's last message has no reply and nothing is working on it, else None.
    Needs an awake brain up for more than 3 min, a message under 3 h old, no registered job or job-scan marker, and a router that writes the epoch files (without
    .last_model_call the image is older than the writers and there is nothing to judge)."""
    ep = info["epochs"]
    human, reply, call = ep.get("last_human"), ep.get("last_reply"), ep.get("last_model_call")
    if not info["awake"] or human is None or call is None:
        return None
    if info["started"] is not None and now - info["started"] <= BOOT_GRACE_S:
        return None
    if reply is not None and reply >= human:
        return None
    if now - human >= UNANSWERED_MAX_AGE_S or now - max(human, call) <= UNANSWERED_S:
        return None
    busy = info.get("busy")
    if (busy() if callable(busy) else busy):     # a long tool (render, transcode, scan) makes no model call for many minutes: not a stall
        return None
    return int((now - max(human, call)) / 60)


def weight(e):
    return KEY_NOTICE_WEIGHT.get(e.k, 1) if e.cat == "key_notice" else WEIGHT[e.cat]


def one_per_reply(events):
    """The events with one wrong_lang per reply: on a routed stack the router and the aibridge-jobs plugin both check the same final reply
    and both write a line, so a router line with a plugin line within SAME_REPLY_S is the same reply and is dropped (the plugin sees every
    path, the router only its own)."""
    plugin = [e.ts for e in events if e.cat == "wrong_lang" and e.src == "plugin"]
    if not plugin:
        return events
    return [e for e in events if not (e.cat == "wrong_lang" and e.src == "router" and any(abs(e.ts - t) <= SAME_REPLY_S for t in plugin))]


def score(events, now, window_min=WINDOW_MIN, unanswered=None):
    """(score, {cat: points}, {cat: raw count}) over the window. Standing categories are not part of it (see standing())."""
    lo = now - window_min * 60
    events = one_per_reply(events)
    pts, cnt = collections.defaultdict(float), collections.defaultdict(int)
    for e in events:
        if e.cat in STANDING or not lo <= e.ts <= now + 60:
            continue
        pts[e.cat] += weight(e) * e.n
        cnt[e.cat] += e.n
    if unanswered is not None:
        pts["unanswered"], cnt["unanswered"] = 3.0, unanswered
    capped = {c: min(p, CAP) for c, p in pts.items()}
    if not any(p > 0 for c, p in capped.items() if c != "model_err"):
        capped.pop("model_err", None)              # six failed calls alone say nothing about what the person experienced
    return sum(capped.values()), dict(capped), dict(cnt)


def standing(events, now):
    """{cat: (latest ts, n, v)} of the standing conditions seen in the last 36 h."""
    out = {}
    for e in events:
        if e.cat in STANDING and now - STANDING_MAX_AGE_S <= e.ts <= now + 60 and (e.cat not in out or e.ts > out[e.cat][0]):
            out[e.cat] = (e.ts, e.n, e.v)
    return out


# ---------------------------------------------------------------- text (only whitelisted labels and integers)

COMPLAINT_LABEL = {"check": "check", "agreed": "we agreed", "broken": "not working", "didnt": "you did not", "again": "again"}
LABEL = {"repeat": "repeated message", "deadpage": "dead page stuck in", "key_notice": "key notice", "bad_end": "cut or empty replies",
         "wrong_lang": "wrong language", "model_err": "model errors", "links_dead": "dead links"}


def describe(cat, count, events, now, window_min):
    """One 'what happened' fragment for a category. Every value comes from a fixed table or an integer."""
    lo = now - window_min * 60
    if cat == "nudge":
        ign = sum(e.n for e in events if e.cat == "nudge_ignored" and lo <= e.ts <= now + 60)
        return f"promises without action x{count}" + (f" ({ign} ignored)" if ign else "")
    if cat == "nudge_ignored":
        return f"promise the model repeated unchanged x{count}"
    if cat == "complaint":
        ks = [COMPLAINT_LABEL[k] for k in dict.fromkeys(e.k for e in events if e.cat == "complaint" and lo <= e.ts <= now + 60) if k in COMPLAINT_LABEL]
        return f"complaints x{count}" + (f" ({', '.join(ks)})" if ks else "")
    if cat in ("failed_turn", "empty_turn"):
        return f"{'failed turns' if cat == 'failed_turn' else 'empty turns'} x{count}"
    if cat == "unanswered":
        return f"no reply for {count} min"
    return f"{LABEL.get(cat, cat)} x{count}"


def signals_text(pts, cnt, events, now, window_min):
    order = [c for c in CATS if c in pts and not (c == "nudge_ignored" and "nudge" in pts)]
    return ", ".join(describe(c, cnt[c], events, now, window_min) for c in order)


def alert_text(name, sc, pts, cnt, events, now, window_min):
    return (f"🚨 {name}: the bot is failing its person (score {sc:.1f}, last {window_min} min).\n"
            f"Signals: {signals_text(pts, cnt, events, now, window_min)}.\n"
            f"Next step: python3 ~/aibridge/ops/stack_doctor.py {name}\n"
            "Only categories and counts; nothing from the chat. Has the bot answered yet? If not, try /parar or restart the stack.")


def standing_text(name, cat, n, v):
    what = {"soul_cut": f"SOUL cut ({n}/{v})" if v is not None else f"SOUL cut ({n} characters)",
            "scan_zero": f"job search with nothing new for {v if v is not None else '?'} days"}[cat]
    return (f"🚨 {name}: {what}. Hermes drops the middle of the SOUL when it passes the cap; a job search with nothing new is usually a "
            "broken scan, not a quiet market.\n"
            f"Next step: python3 ~/aibridge/ops/stack_doctor.py {name}\n"
            "Only categories and counts; nothing from the chat.")


# ---------------------------------------------------------------- state

def load_state():
    try:
        d = json.load(open(STATE))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE + ".tmp"
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, STATE)


def decide(st, sc, now):
    """('send' | 'escalate' | 'cooldown' | 'below', reason) from the stack's state and the current score."""
    if sc < THRESHOLD:
        return "below", "score under 3"
    if not st.get("open") or not st.get("last_sent"):
        return "send", "new"
    age = now - st["last_sent"]
    if age >= COOLDOWN_S:
        return "send", "still failing after the cooldown"
    if sc >= st.get("last_score", 0) * 1.5 + 2 and age >= ESCALATE_AFTER_S:
        return "escalate", "score rose"
    return "cooldown", f"alerted {int(age / 60)} min ago"


def run_stack(s, now, window_min, state, live):
    """Evaluate one stack. Returns its report dict; when `live`, also sends / resolves through notify and updates `state`."""
    name = s["name"]
    silenced = s.get("early_alert") is False
    info = gather(s, now, now - max(2 * 3600, window_min * 60))
    una = unanswered_minutes(info, now)
    sc, pts, cnt = score(info["events"], now, window_min, una)
    st = state.setdefault(name, {})
    action, why = decide(st, sc, now)
    rep = {"stack": name, "awake": info["awake"], "sink": info["sink_found"], "score": round(sc, 1), "points": {k: round(v, 1) for k, v in pts.items()},
           "counts": cnt, "decision": action, "reason": why, "text": None, "standing": []}
    if sc >= THRESHOLD:
        rep["text"] = alert_text(name, sc, pts, cnt, info["events"], now, window_min)
    if silenced:
        rep["decision"], rep["reason"] = "silenced", "early_alert is false for this stack"
    sent = False
    if live and not silenced:
        if action in ("send", "escalate"):
            notify.alert(f"early:{name}", rep["text"], quiet=0)
            st.update(last_sent=now, last_score=sc, open=True, since=st.get("since") if st.get("open") else now, zero_since=None)
            sent = True
        elif sc > 0:
            st["zero_since"] = None
        elif st.get("open"):                       # quiet: resolve once the score has stayed at 0 for 60 min
            if st.get("zero_since") is None:
                st["zero_since"] = now
            if now - st["zero_since"] >= QUIET_RESOLVE_S:
                notify.resolve(f"early:{name}", f"{name}: back to normal")
                st.update(open=False, zero_since=None)
    # standing conditions: their own alert, 24 h cooldown, never escalated, resolved when they age out
    stand = standing(info["events"], now)
    sstate = st.setdefault("standing", {})
    for cat in STANDING:
        ss = sstate.setdefault(cat, {})
        if cat in stand:
            ts, n, v = stand[cat]
            due = ts > ss.get("event", 0) and now - ss.get("sent", 0) >= STANDING_COOLDOWN_S
            rep["standing"].append({"cat": cat, "n": n, "v": v, "decision": "silenced" if silenced else "send" if due else "cooldown",
                                    "text": standing_text(name, cat, n, v) if due else None})
            if live and not silenced and due:
                notify.alert(f"early:{name}:{cat}", standing_text(name, cat, n, v), quiet=0)
                ss.update(sent=now, event=ts, open=True)
        elif live and not silenced and ss.get("open"):
            notify.resolve(f"early:{name}:{cat}", f"{name}: {cat} back to normal")
            ss.update(open=False)
    rep["sent"] = sent
    return rep


def notifications_on():
    v = os.environ.get("EARLY_ALERT_NOTIFY")
    if v is None:
        try:
            for line in open(notify.ENV_FILE):
                k, sep, val = line.partition("=")
                if sep and k.strip() == "EARLY_ALERT_NOTIFY":
                    v = val.strip().strip('"').strip("'")
        except OSError:
            pass
    return (v or "").lower() in ("1", "true", "yes", "on")


def table(rep):
    lines = [f"== {rep['stack']}  {'awake' if rep['awake'] else 'asleep'}  sink {'yes' if rep['sink'] else 'no'}  score {rep['score']:.1f}  -> {rep['decision']} ({rep['reason']})"]
    if rep["counts"]:
        lines.append("   " + ", ".join(f"{c} x{rep['counts'][c]} ({rep['points'].get(c, 0):.1f})" for c in CATS if c in rep["counts"]))
    for sd in rep["standing"]:
        lines.append(f"   standing {sd['cat']} n={sd['n']} v={sd['v']} -> {sd['decision']}")
    if rep["text"]:
        lines.append("   would send:\n" + "\n".join("      " + t for t in rep["text"].splitlines()))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="early alert collector")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stack")
    ap.add_argument("--window", type=int, default=WINDOW_MIN)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    now = float(os.environ["EARLY_ALERT_NOW"]) if os.environ.get("EARLY_ALERT_NOW") else time.time()
    try:
        cfg = json.load(open(STACKS))
        stacks = [s for s in cfg.get("stacks", []) if isinstance(s, dict) and s.get("name")]
    except (OSError, ValueError) as e:
        print(f"early_alert: cannot read {STACKS} ({type(e).__name__})", file=sys.stderr)
        return 1
    if a.stack:
        stacks = [s for s in stacks if s["name"] == a.stack]
        if not stacks:
            print(f"early_alert: no stack named {a.stack}", file=sys.stderr)
            return 2
    live = not a.dry_run and notifications_on()
    reports, failed = [], 0
    lock = None
    if live:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        lock = open(STATE + ".lock", "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        state = load_state()
        for s in stacks:
            try:
                reports.append(run_stack(s, now, a.window, state, live))
            except Exception as e:                  # one flaky stack must not stop the others
                failed += 1
                print(f"early_alert: [{s['name']}] skipped ({type(e).__name__})", file=sys.stderr)
        if live:
            save_state(state)
    finally:
        if lock:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
    if a.json:
        print(json.dumps(reports, indent=1))
    else:
        if not live and not a.dry_run and reports:
            print("early_alert: notifications OFF (set EARLY_ALERT_NOTIFY=1 in ops/ops.env to send); table only")
        for rep in reports:
            if a.dry_run or rep["counts"] or rep["standing"] or rep["decision"] != "below":
                print(table(rep))
    return 1 if stacks and failed == len(stacks) else 0


if __name__ == "__main__":
    sys.exit(main())
