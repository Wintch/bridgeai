#!/usr/bin/env python3
"""How bridgeai is actually used, without personal data: what to improve next, and problems nobody reports.

  telemetry.py collect         every 5 min (telemetry.timer): new turns, API errors, wakes, host; instant alerts
  telemetry.py report daily    daily summary to the ops bot (telemetry-report.timer)
  telemetry.py report weekly   "what to improve" ranking (the daily run sends it on Mondays)
  telemetry.py report daily --print   print instead of sending
  telemetry.py report subagents [--days N] [--print]   delegate_task subagents per stack: how many, duration, failed share, children's
                               calls and tokens, CPU-seconds over their intervals (an upper bound)

What is collected (~/.local/state/telemetry.db, on this host only):
  turns   stack, time, channel (telegram/web/cron), seconds to the final answer, tool calls, tool errors, failed
          (Hermes marked it failed_turn, or no answer at all), empty answer, model, a short hash of the session id
  errors  stack, time, provider, model, HTTP code of failed model API calls (agent.log)
  wakes   stack, time, reason, seconds, outcome (waker journal)
  host    available RAM, swap used, disk use
  gw      every gateway call (gateway.py): which gateway, host, seconds, GPU/CPU seconds, MB in/out, fallback, error
  gwhost  each gateway host (ops/gateways.json) up or down, every run
  delegations  one row per delegate_task delegation (2026-11-27: bots hand long tasks to background subagents in their container):
          hashed delegation id and parent session (the same hash as turns.session), started, ended (when it left "running", or
          disappeared: status gone), task count, final status per task as counts (ok/failed/interrupted/timeout/running/other),
          duration, the children's model API calls, tool calls and tokens (from Hermes's result ledger, else the children's own
          session counters), model, provider, build. Captured on every collect while Hermes's manifests and ledger rows exist (Hermes
          prunes them), then reconciled.
  res     every collect, one row per running stack container (brain, webui, voice, web, telegram-bot-api): CPU seconds since its
          previous row and memory now/peak from the host's cgroup v2 files (no docker exec), pids, and on the brain row the
          subagents running now. Attributes CPU/RAM per stack per 5 min and over a subagent's interval.
Turns carry a kind: person, subagent (a delegate_task child's own session, source 'subagent') or cron. Reports and alerts about
people leave the subagent turns out.
What is NOT: message text, tool output, titles, chat or user ids, names. The text never leaves SQLite: the queries
below compute booleans (empty answer, tool error) inside the database and only those come out.

Stack data is read from inside the container (`docker exec`, live db with its WAL) when it runs, else from its
persisted copy through a throwaway read-only container (the files are root 0600). Turns, delegations and the running subagents
come from the same exec. A goal, a transcript or a tool output is never read out: the in-container script prints hashes, counts,
timestamps and fixed words only.

Zabbix (optional, off unless STACKS_ZBX_HOST and STACKS_ZBX_SERVER (or ZBX_SERVER) are set in ops/ops.env or the environment):
each collect pushes per stack awake (0/1), running subagents, CPU % of one core over the last interval and memory MB to the
trapper host made by `ops/zabbix/provision.py stacks-host` (template ops/zabbix/template_bridgeai_stacks.yaml).
"""
import argparse, datetime as dt, io, json, os, re, sqlite3, subprocess, sys, tarfile, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import notify  # noqa: E402

DB = os.path.expanduser("~/.local/state/telemetry.db")
STACKS = os.path.join(HERE, "wake", "stacks.json")
BACKUPS = os.path.expanduser("~/backups")
FIRST_LOOKBACK_S = 7 * 86400
SLOW_PLAIN_TURN_S = 60      # an answer with no tool calls should never take this long
UNANSWERED_S = 15 * 60      # a message with no answer after this long counts as a failed turn
DISK_ALERT_PCT = 85
DISK_RESOLVE_PCT = 80       # hysteresis: the disk alert resolves below this, not at 84 %
RESOLVE_CLEAN = 3           # clean samples (turns / ticks) in a row before a tele:* alert resolves
BLIND_TICKS = 3             # failed reads of a stack's data in a row before "telemetry is blind" alerts
LOOKBACK_S = 3600           # turns are stored when they close (or after 900 s): re-read this far behind the newest one
BACKUP_MAX_AGE_H = 26

# Runs INSIDE the container (python3 -I -, argv: since, state.db path, quiet seconds, delegation live root). Prints one JSON line per
# closed turn whose user message is newer than `since` (with its kind: person, subagent or cron), one {"rec": "deleg"} line per
# delegate_task delegation it can see (live manifests and Hermes's async_delegations ledger) and one {"rec": "live"} line with the
# subagents running right now. Only hashes, counts, timestamps, fixed status words and model/provider names leave: never a goal,
# a transcript line, a summary or a tool output (the transcripts are not even opened, only their mtime is read).
TURNS_SCRIPT = r'''
import glob, hashlib, json, os, re, sqlite3, sys, time
since, path = float(sys.argv[1]), sys.argv[2]
quiet = float(sys.argv[3]) if len(sys.argv) > 3 else 900
live_root = sys.argv[4] if len(sys.argv) > 4 else "/root/.hermes/cache/delegation/live"
uri = "file:%s?mode=ro" % path + ("&immutable=1" if path.startswith("/p/") else "")
db = sqlite3.connect(uri, uri=True, timeout=10)
def h8(x):
    return hashlib.sha1(x.encode()).hexdigest()[:8] if x else None
try:   # a delegate_task child: source 'subagent', or a compression continuation that kept its _delegate_from marker
    sess = db.execute("select id, source, billing_provider, model, case when source='subagent' or "
                      "instr(coalesce(model_config,''),'_delegate_from')>0 then 1 else 0 end from sessions").fetchall()
except sqlite3.OperationalError:
    sess = [r + (int(r[1] == "subagent"),) for r in db.execute("select id, source, billing_provider, model from sessions")]
meta = {sid: (src or "", (prov or "") + "/" + (model or ""), "subagent" if sub else "cron" if src == "cron" else "person")
        for sid, src, prov, model, sub in sess}
rows = db.execute("""
  select session_id, role, timestamp, finish_reason, display_kind,
         case when role='assistant' and tool_calls is null and (content is null or length(trim(content))=0) then 1 else 0 end,
         case when role='tool' and (content like '{"error"%' or content like 'Error%' or content like '%"success": false%')
              then 1 else 0 end
  from messages
  where session_id in (select distinct session_id from messages where role='user' and timestamp > ?)
  order by session_id, timestamp, id""", (since,)).fetchall()
now = time.time()
def emit(sid, turn, closed):
    u = turn[0]
    if u[2] <= since or not (closed or now - u[2] > 900):
        return
    final = [m for m in turn[1:] if m[1] == "assistant" and m[3] == "stop"]
    failed = any(m[4] == "failed_turn" for m in turn) or not final
    src, model, kind = meta.get(sid, ("", "/", "person"))
    print(json.dumps({"ts": u[2], "session": h8(sid), "source": src, "kind": kind,
                      "model": model, "seconds": round(final[-1][2] - u[2], 1) if final else None,
                      "tools": sum(1 for m in turn if m[1] == "tool"), "tool_errors": sum(m[6] for m in turn),
                      "failed": int(failed), "empty": int(bool(final) and final[-1][5] == 1)}))
cur, turn = None, []
for r in rows:
    if r[0] != cur:
        if turn: emit(cur, turn, any(m[1] == "assistant" and m[3] == "stop" for m in turn[1:]))
        cur, turn = r[0], []
    if r[1] == "user":
        # A burst (several messages before any answer) is ONE turn: Hermes answers them together. Measured
        # 35 of hernik's 58 "unanswered" Telegram messages were followed within 30 s by another one.
        if turn and turn[0][1] == "user" and len(turn) == 1 and r[2] - turn[0][2] < 900:
            continue
        if turn and turn[0][1] == "user": emit(cur, turn, True)
        turn = [r]
    elif turn:
        turn.append(r)
if turn: emit(cur, turn, any(m[1] == "assistant" and m[3] == "stop" for m in turn[1:]))
# ---- delegate_task subagents: counts only
WORD, NAME, LIVE_ID = re.compile(r"[a-z_]{1,24}"), re.compile(r"[\w.:/@+-]{1,80}"), re.compile(r"/live/([^/]+)/task-\d+\.log$")
def word(s):
    s = str(s or "").lower()
    return s if WORD.fullmatch(s) else "other"
def name(s):
    return s if isinstance(s, str) and NAME.fullmatch(s) else None
def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else 0
def local_ts(s):   # the manifest's times are the container's local time, second resolution
    try:
        return time.mktime(time.strptime(str(s), "%Y-%m-%d %H:%M:%S"))
    except (ValueError, OverflowError):
        return None
def js(x):
    try:
        v = json.loads(x) if x else {}
    except ValueError:
        v = {}
    return v if isinstance(v, dict) else {}
D, live = {}, 0
def rec(key):
    return D.setdefault(key, {"parent": None, "started": None, "ended": None, "aend": None, "tasks": 0, "mst": {}, "rst": {}, "api": 0,
                              "tools": 0, "tin": 0, "tout": 0, "model": None, "provider": None, "live": 0, "units": 0, "done": 0,
                              "utasks": 0})
for m in glob.glob(os.path.join(live_root, "*", "manifest.json")):
    try:
        d = json.load(open(m, encoding="utf-8-sig"))
    except (OSError, ValueError):
        continue
    if not isinstance(d, dict):
        continue
    r = rec(os.path.basename(os.path.dirname(m)))
    r["started"], r["ended"] = local_ts(d.get("started")), local_ts(d.get("completed")) if d.get("completed") else None
    tasks = [t for t in d.get("tasks") or [] if isinstance(t, dict)]
    r["tasks"] = max(int(num(d.get("task_count"))), len(tasks))
    r["model"], r["provider"] = name(d.get("model")), name(d.get("provider"))
    for t in tasks:
        s = word(t.get("status"))
        r["mst"][s] = r["mst"].get(s, 0) + 1
        r["model"] = r["model"] or name(t.get("model"))
        if s == "running":   # the waker's rule: running AND its live transcript moved in the last `quiet` seconds
            try:
                if now - os.path.getmtime(str(t.get("log") or "")) < quiet:
                    r["live"] += 1
            except OSError:
                pass
    live += r["live"]
try:
    arows = db.execute("select delegation_id, parent_session_id, dispatched_at, completed_at, state, result_json, task_json "
                       "from async_delegations where dispatched_at > ? or state='running'", (now - 8 * 86400,)).fetchall()
except sqlite3.Error:
    arows = []
for did, parent, disp, comp, state, rj, tj in arows:
    res, task = js(rj), js(tj)
    paths = [p for p in list(res.get("live_transcripts") or []) + list(task.get("task_transcripts") or []) if isinstance(p, str)]
    # one unit of a batch keeps the live directory's id; the others are grouped under it through their transcript paths
    r = rec(next((x.group(1) for x in map(LIVE_ID.search, paths) if x), did))
    r["units"] += 1
    r["parent"] = r["parent"] or parent
    if isinstance(disp, (int, float)):
        r["started"] = disp if r["started"] is None else min(r["started"], disp)
    if state != "running" and isinstance(comp, (int, float)):
        r["done"] += 1
        r["aend"] = max(r["aend"] or 0, comp)
    goals = task.get("goals")
    r["utasks"] += len(goals) if isinstance(goals, list) and goals else 1   # a batch's units split its tasks between them
    r["model"] = r["model"] or name(task.get("model"))
    for x in res.get("results") or []:
        if not isinstance(x, dict):
            continue
        s = word(x.get("status"))
        r["rst"][s] = r["rst"].get(s, 0) + 1
        r["api"] += int(num(x.get("api_calls")))
        r["tools"] += len(x["tool_trace"]) if isinstance(x.get("tool_trace"), list) else 0
        tok = x.get("tokens") if isinstance(x.get("tokens"), dict) else {}
        r["tin"] += int(num(tok.get("input")))
        r["tout"] += int(num(tok.get("output")))
        r["model"] = r["model"] or name(x.get("model"))
for key, r in D.items():
    r["tasks"] = max(r["tasks"], r["utasks"])
    if r["units"] and r["done"] == r["units"]:
        r["ended"] = max(r["ended"] or 0, r["aend"] or 0) or None
    elif r["units"]:
        r["ended"] = None   # the ledger says a unit still runs
    if r["started"] and not r["parent"]:
        # a manifest alone names no parent: its children are subagent sessions created at dispatch, all with one parent
        try:
            ps = {p for p, in db.execute("select parent_session_id from sessions where source='subagent' and started_at between ? and ?",
                                          (r["started"] - 5, r["started"] + 30))}
            if len(ps) == 1:
                r["parent"] = ps.pop()
        except sqlite3.Error:
            pass
    if r["started"] and r["parent"] and not r["rst"]:
        # no result yet (still running, or the ledger row is gone): the children's own counters in state.db
        try:
            k = db.execute("select count(*), sum(api_call_count), sum(tool_call_count), sum(input_tokens), sum(output_tokens) from sessions "
                           "where source='subagent' and parent_session_id=? and started_at between ? and ?",
                           (r["parent"], r["started"] - 5, (r["ended"] or now) + 5)).fetchone()
            if k and k[0]:
                r["api"], r["tools"], r["tin"], r["tout"] = (int(num(v)) for v in k[1:])
        except sqlite3.Error:
            pass
    st = r["rst"] or r["mst"] or {"running" if r["ended"] is None else "other": r["tasks"]}
    print(json.dumps({"rec": "deleg", "id": h8(key), "parent": h8(r["parent"]), "started": r["started"], "ended": r["ended"],
                      "tasks": r["tasks"], "st": st, "api": r["api"], "tools": r["tools"], "tin": r["tin"], "tout": r["tout"],
                      "model": r["model"], "provider": r["provider"], "live": r["live"]}))
print(json.dumps({"rec": "live", "running": live}))
'''

BG_MODEL = "local-only"     # model name Hermes's background tasks send to the router (start_hermes.sh)
FAIL_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d).*API call failed.*?provider=(\S+) .*?model=(\S+)(?: .*?summary=HTTP (\d{3}))?")
WAKE_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[(\S+)\] (ready after ([\d.]+)s \((\w+)\)|boot did not finish|"
                     r"wake \((\w+)\) gave up: no memory|evicted by the RAM guard)")


def sh(*args, inp=None, timeout=120):
    return subprocess.run(args, input=inp, capture_output=True, text=True, timeout=timeout)


def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript("""
      create table if not exists turns(stack, ts real, session, source, model, seconds real, tools int, tool_errors int,
                                       failed int, empty int, unique(stack, ts, session));
      create table if not exists errors(stack, ts real, provider, model, code, unique(stack, ts, provider, model, code));
      create table if not exists wakes(stack, ts real, reason, seconds real, outcome, unique(stack, ts, outcome));
      create table if not exists host(ts real, mem_avail_mb int, swap_used_mb int, disk_pct int);
      create table if not exists meta(k primary key, v);
      create table if not exists gw(stack, ts real, gateway, host, ok int, fallback int, seconds real, gpu_seconds real,
                                    cpu_seconds real, mb_in real, mb_out real, error, down, unique(stack, ts, gateway));
      create table if not exists gwhost(ts real, host, up int);
      create table if not exists awake(ts real, brains int, webs int);
      create table if not exists delegations(stack, deleg, parent, started real, ended real, last_seen real, status, tasks int,
                                             ok int, failed int, interrupted int, timeout int, running int, other int, duration real,
                                             api_calls int, tool_calls int, tokens_in int, tokens_out int, model, provider, image,
                                             unique(stack, deleg));
      create table if not exists res(ts real, stack, role, cid, secs real, cpu_usec int, cpu_s real, mem_mb real, peak_mb real,
                                     pids int, subagents int);
      create index if not exists res_stack_ts on res(stack, ts);""")
    ensure_turns_unique(c)
    cols = [r[1] for r in c.execute("pragma table_info(turns)")]
    if "image" not in cols:
        c.execute("alter table turns add column image")   # the build each turn ran on (2026-11-27: rollout by build), NULL before
        c.commit()
    if "kind" not in cols:
        # person | subagent | cron (2026-11-27: delegate_task children are sessions of their own in state.db, source 'subagent', and
        # their kickoff opened "turns" that counted as the person's). Older rows are classified by their source.
        c.execute("alter table turns add column kind")
        c.execute("update turns set kind = case source when 'subagent' then 'subagent' when 'cron' then 'cron' else 'person' end")
        c.commit()
    return c


PERSON = "coalesce(kind, 'person') != 'subagent'"   # turns that count as people's (and cron's): never a subagent's own turns


def booted_image(name):
    """The image id the stack last booted (ops/wake/<name>.booted_image, written by ops/recreate_hermes.sh), shortened; None if unknown.
    A turn is tagged with the image of the stack at collection time: collection runs every 5 min while the stack is awake, and an
    update recreates a stack only when it is idle, so a turn and its image agree."""
    try:
        with open(os.path.join(HERE, "wake", f"{name}.booted_image"), encoding="ascii", errors="replace") as f:
            v = f.read(200).strip()
    except OSError:
        return None
    v = v.split(":", 1)[-1]
    return v[:12] if re.fullmatch(r"[0-9a-f]{12,64}", v) else None


def ensure_turns_unique(c):
    """The turns watermark re-reads an hour of turns and relies on unique(stack, ts, session) to ignore the repeats."""
    for _, name, unique, *_ in c.execute("pragma index_list(turns)").fetchall():
        cols = [r[2] for r in c.execute(f"pragma index_info({name})")]
        if unique and cols == ["stack", "ts", "session"]:
            return
    c.execute("delete from turns where rowid not in (select min(rowid) from turns group by stack, ts, session)")
    c.execute("create unique index if not exists turns_uniq on turns(stack, ts, session)")
    c.commit()


def meta_get(c, k, default=None):
    r = c.execute("select v from meta where k=?", (k,)).fetchone()
    return r[0] if r else default


def meta_set(c, k, v):
    c.execute("insert into meta(k, v) values(?, ?) on conflict(k) do update set v=excluded.v", (k, v))


def epoch(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp()


def inspect(name, fmt):
    r = sh("docker", "inspect", "-f", fmt, name)
    return r.stdout.strip() if r.returncode == 0 else ""


def ran_since(brain, t):
    """True if the brain is running, or stopped after t (it ran since our last look)."""
    if inspect(brain, "{{.State.Running}}") == "true":
        return True
    fin = inspect(brain, "{{.State.FinishedAt}}")[:19]
    if fin.startswith("0001"):   # recreated and never started since: its data is still the persisted copy
        return True
    try:
        return epoch(fin.replace("T", " ")) > t
    except ValueError:
        return True


SUBAGENT_QUIET_S = 900   # a subagent counts as running while its live transcript moved this recently (waker.SUBAGENT_QUIET_S)
LIVE_ROOT = "/root/.hermes/cache/delegation/live"   # Hermes's delegation manifests, in the container's cache (pruned, lost on recreate)


def parse_stack_read(text):
    """The in-container script's output as {"turns": [...], "delegs": [...], "running": n or None}."""
    out = {"turns": [], "delegs": [], "running": None}
    for line in text.splitlines():
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("rec") == "deleg":
            out["delegs"].append(d)
        elif d.get("rec") == "live":
            out["running"] = d.get("running") if isinstance(d.get("running"), int) else None
        elif "ts" in d:
            out["turns"].append(d)
    return out


def stack_read(stack, since):
    """Closed turns newer than `since`, the delegations and the running subagents, in ONE docker exec; None when the data could not
    be read (the caller counts those). A stopped stack is read from its persisted state.db (no live manifests there: running = 0)."""
    brain = stack["brain"]
    if inspect(brain, "{{.State.Running}}") == "true":
        # -w / and -I: /workdir is writable by the person, a json.py or sqlite3.py there must not shadow the stdlib
        r = sh("docker", "exec", "-i", "-w", "/", brain, "python3", "-I", "-", str(since), "/root/.hermes/state.db",
               str(SUBAGENT_QUIET_S), LIVE_ROOT, inp=TURNS_SCRIPT)
    else:
        src = inspect(brain, '{{range .Mounts}}{{if eq .Destination "/hermes-persist"}}{{.Source}}{{end}}{{end}}')
        image = inspect(brain, "{{.Config.Image}}")
        if not (src and image):
            return None
        r = sh("docker", "run", "--rm", "-i", "--network", "none", "-v", f"{src}:/p:ro", "--entrypoint", "python3",
               image, "-I", "-", str(since), "/p/state.db", str(SUBAGENT_QUIET_S), "/nonexistent", inp=TURNS_SCRIPT, timeout=180)
    if r.returncode != 0:
        err = r.stderr.strip().splitlines()[-1][:120] if r.stderr.strip() else str(r.returncode)
        if "unable to open database" in err:   # a brand-new stack has no state.db yet: nothing to read, not a failure
            return {"turns": [], "delegs": [], "running": 0}
        print(f"[{stack['name']}] turns: read failed ({err})")
        return None
    return parse_stack_read(r.stdout)


def stack_turns(stack, since):
    """Closed turns newer than `since`, or None when the data could not be read."""
    d = stack_read(stack, since)
    return None if d is None else d["turns"]


STATUS_COLS = ("ok", "failed", "interrupted", "timeout", "running", "other")
STATUS_OF = {"completed": "ok", "failed": "failed", "error": "failed", "interrupted": "interrupted", "timeout": "timeout",
             "running": "running"}


def _int(x):
    return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 else 0


def _ts(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else None


def _hash8(x):
    return x if isinstance(x, str) and re.fullmatch(r"[0-9a-f]{8}", x) else None


def _model(x):
    return x[:80] if isinstance(x, str) and re.fullmatch(r"[\w.:/@+-]{1,80}", x) else None


def store_delegations(c, name, delegs, now, img):
    """Upsert the delegations the container reported (counts, fixed words, hashes; the container's values are re-checked here), then
    reconcile: one still "running" here that the container no longer shows (Hermes pruned it, or the stack was recreated) ends as
    "gone" at the last time it was seen. Returns the hashes seen."""
    seen = set()
    for d in delegs:
        deleg = _hash8(d.get("id"))
        started = _ts(d.get("started"))
        if not deleg or started is None:
            continue
        seen.add(deleg)
        cnt = dict.fromkeys(STATUS_COLS, 0)
        for word, n in (d.get("st") or {}).items() if isinstance(d.get("st"), dict) else ():
            cnt[STATUS_OF.get(str(word), "other")] += _int(n)
        ended = _ts(d.get("ended"))
        status = "done" if ended else "running"
        c.execute("""insert into delegations(stack, deleg, parent, started, ended, last_seen, status, tasks, ok, failed, interrupted, timeout,
                                              running, other, duration, api_calls, tool_calls, tokens_in, tokens_out, model, provider, image)
                     values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                     on conflict(stack, deleg) do update set
                       parent=coalesce(excluded.parent, parent), started=min(started, excluded.started),
                       ended=excluded.ended,
                       last_seen=excluded.last_seen, status=excluded.status, tasks=max(tasks, excluded.tasks),
                       ok=excluded.ok, failed=excluded.failed, interrupted=excluded.interrupted, timeout=excluded.timeout,
                       running=excluded.running, other=excluded.other, duration=excluded.duration,
                       api_calls=max(api_calls, excluded.api_calls), tool_calls=max(tool_calls, excluded.tool_calls),
                       tokens_in=max(tokens_in, excluded.tokens_in), tokens_out=max(tokens_out, excluded.tokens_out),
                       model=coalesce(excluded.model, model), provider=coalesce(excluded.provider, provider),
                       image=coalesce(image, excluded.image)""",
                  (name, deleg, _hash8(d.get("parent")), started, ended, now, status, _int(d.get("tasks")), *cnt.values(),
                   round((ended or now) - started, 1), _int(d.get("api")), _int(d.get("tools")), _int(d.get("tin")), _int(d.get("tout")),
                   _model(d.get("model")), _model(d.get("provider")), img))
    gone = [r[0] for r in c.execute("select deleg from delegations where stack=? and status='running'", (name,)) if r[0] not in seen]
    for deleg in gone:
        end_gone(c, name, deleg)
    return seen


def end_gone(c, name, deleg=None):
    """A running delegation that vanished, or whose stack stopped (a sleep or an update halts the whole subagent tree): it ends at the
    last time it was seen, its running tasks counted as lost."""
    q = "update delegations set status='gone', ended=last_seen, duration=round(last_seen-started, 1) where stack=? and status='running'"
    c.execute(q + (" and deleg=?" if deleg else ""), (name, deleg) if deleg else (name,))


def stack_errors(stack):
    r = subprocess.run(["docker", "cp", f"{stack['brain']}:/root/.hermes/logs/agent.log", "-"], capture_output=True, timeout=60)
    if r.returncode != 0:
        return []
    try:
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
            text = t.extractfile(t.next()).read().decode("utf-8", "replace")
    except (tarfile.TarError, AttributeError):
        return []
    out = []
    for line in text.splitlines():
        m = FAIL_RE.search(line)
        if m:
            out.append((epoch(m.group(1)), m.group(2), m.group(3), m.group(4) or "err"))
    return out


def tts_probe(stack):
    """None if the stack's TTS is asleep, else (ok, seconds, detail). One short Spanish phrase, the web UI's voice."""
    tts = next((w for w in stack.get("web", []) if "tts" in w), None)
    if not tts or inspect(tts, "{{.State.Running}}") != "true":
        return None
    ip = inspect(tts, "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}").split()
    if not ip:
        return None
    req = urllib.request.Request(f"http://{ip[0]}:5002/v1/audio/speech",
                                 data=json.dumps({"input": "Hola, prueba de voz.", "voice": "es_MX-claude-high",
                                                  "response_format": "mp3"}).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            n = len(r.read())
        return n > 1000, time.time() - t0, f"{n} bytes"
    except Exception as e:
        return False, time.time() - t0, type(e).__name__


GW_MASTER = os.path.join(HERE, "gateways.json")
# The router (router.py) logs one decision per turn, not a call with ok/host/error. Its routes, and how the report
# names them; only "none" (no model answered at all) is a failure. Crossweft set `router-routes` keeps this in step.
ROUTER_ROUTES = {"local": "at home", "nube": "cloud", "ask": "asked permission", "idle": "asked whether to continue", "control": "a typed control carried out by the router", "none": "no answer",
                 "colgado": "cloud model hung", "rechazo": "a model refused the request (4xx)",
                 "cupo-agotado": "free allowance used up", "gate": "the GPU gate did not give the home model",
                 "cold": "home model cold, long read estimated", "prewarm": "home model read the conversation in the background",
                 "submarino": "submarine mode: the home model could not answer"}
# "colgado" (a timeout), "rechazo" (a 4xx with its reason, item 89), "cupo-agotado" (a weekly allowance used up, item
# 88) and "gate" (the home model's GPU gate refused or did not answer) are notes about one backend logged next to the turn's own decision.


# Router rows stored before gw_normalize (commit eef57d6) have host NULL and ok=0: they are not failures.
GW_OK_ROW = "not (gateway='router' and host is null)"


def gw_clean(d):
    """A log record as a dict with a numeric ts and scalar fields, else None (the container's file is not trusted)."""
    if not isinstance(d, dict) or isinstance(d.get("ts"), bool) or not isinstance(d.get("ts"), (int, float)):
        return None
    d = {k: (v if isinstance(v, (str, int, float, type(None))) else None) for k, v in d.items() if k != "down"} | {
        "down": [str(x) for x in d["down"]] if isinstance(d.get("down"), list) else []}
    return d


def gw_normalize(d):
    """A router decision as a gw row: the route goes in `host`, ok unless no model answered."""
    if d.get("gateway") != "router":
        return d
    route = d.get("route")
    if route in ("cupo-agotado", "rechazo"):         # notes about one backend: which one and why go in `error`
        return dict(d, host=route, ok=False,
                    error=f"{d.get('host')}: " + (f"HTTP {d.get('code')} {d.get('why') or ''}".strip() if route == "rechazo"
                                                  else f"until {d.get('until')}"))
    if route == "submarino":                        # submarine mode (local_only): home only, and home did not answer
        return dict(d, host=route, ok=False, error=f"submarine mode, home model unavailable: {d.get('reason') or '?'}")
    return dict(d, host=route, ok=route != "none",
                error=None if route != "none" else f"no model answered ({d.get('tried', 0)} clouds tried)")


# The tail of the older generation and of the live log (gateway.py/router.py rotate it past 5 MB to .gateway-log.1.jsonl):
# a bounded read every 5 minutes instead of the whole history; a cut first line is skipped as bad JSON.
READ_GWLOG = "{{ tail -c 1000000 {d}/.gateway-log.1.jsonl; tail -c 3000000 {d}/.gateway-log.jsonl; }} 2>/dev/null"


def stack_gateway_log(stack, since):
    """New lines of the stack's /workdir/.gateway-log.jsonl (root 0600 inside the container's workdir)."""
    brain = stack["brain"]
    if inspect(brain, "{{.State.Running}}") == "true":
        r = sh("docker", "exec", brain, "sh", "-c", READ_GWLOG.format(d="/workdir"))
    else:
        src = inspect(brain, '{{range .Mounts}}{{if eq .Destination "/workdir"}}{{.Source}}{{end}}{{end}}')
        if not src:
            return []
        r = sh("docker", "run", "--rm", "--network", "none", "-v", f"{src}:/w:ro", "busybox:latest",
               "sh", "-c", READ_GWLOG.format(d="/w"))
    out = []
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        d = gw_clean(d)
        if d and d["ts"] > since:
            out.append(gw_normalize(d))
    return out


def stack_learning(stack, since):
    """Self-improvement of one stack: {action: n} from the skills ledger (actions only, never content) since `since`,
    plus how many learned skill copies a newer image replaced (persist/skills-replaced, kept to merge by hand)."""
    brain = stack["brain"]
    cmd = ("cat /root/.hermes/skills/.curator_ledger.jsonl 2>/dev/null; echo ===; "
           "find /hermes-persist/skills-replaced -type f 2>/dev/null | wc -l")
    if inspect(brain, "{{.State.Running}}") == "true":
        r = sh("docker", "exec", brain, "sh", "-c", cmd)
    else:
        src = inspect(brain, '{{range .Mounts}}{{if eq .Destination "/hermes-persist"}}{{.Source}}{{end}}{{end}}')
        if not src:
            return {}, 0
        r = sh("docker", "run", "--rm", "--network", "none", "-v", f"{src}:/hermes-persist:ro", "busybox:latest", "sh", "-c",
               cmd.replace("/root/.hermes/skills", "/hermes-persist/skills"))
    ledger, _, rest = r.stdout.partition("===")
    actions = {}
    for line in ledger.splitlines():
        try:
            d = json.loads(line)
            if dt.datetime.fromisoformat(d.get("ts", "")).timestamp() > since:
                actions[d.get("action", "?")] = actions.get(d.get("action", "?"), 0) + 1
        except (ValueError, TypeError, AttributeError):
            continue
    try:
        replaced = int(rest.strip() or 0)
    except ValueError:
        replaced = 0
    return actions, replaced


def learning_report(stacks, t0):
    """One line: what each Hermes learned (skills created / patched, memory writes) and learned copies waiting to merge."""
    parts, waiting = [], []
    for st in stacks:
        actions, replaced = stack_learning(st, t0)
        created = actions.get("create", 0)
        changed = sum(v for k, v in actions.items() if k != "create")
        parts.append(f"{st['name']} {created} new/{changed} changes")
        if replaced:
            waiting.append(f"{st['name']} {replaced}")
    lines = ["• learned skills: " + ", ".join(parts)]
    if waiting:
        lines.append("   ⚠️ learned copies that a new image replaced (merge by hand, persist/skills-replaced; "
                     "once merged, move them to persist/skills-merged): "
                     + ", ".join(waiting))
    return lines


def probe_gateway_hosts(c, now):
    """{host: up?} for every host in the master list; recorded for availability; always_on hosts alert when down."""
    try:
        hosts = json.load(open(GW_MASTER)).get("hosts", {})
    except (OSError, ValueError):
        return {}
    state = {}
    for name, h in hosts.items():
        port = h.get("transcode") or h.get("upscale") or h.get("stt")
        if not h.get("addr"):     # reached by container name from the stacks' network, not from this host
            continue
        up = False
        if port:
            try:
                with urllib.request.urlopen(f"http://{h['addr']}:{port}/healthz", timeout=3) as r:
                    up = r.status == 200
            except Exception:
                up = False
        state[name] = up
        c.execute("insert into gwhost values(?,?,?)", (now, name, int(up)))
        if h.get("always_on"):
            if up:
                notify.resolve(f"gwhost:{name}", f"{name} ({h.get('gpu', 'GPU')}) answers again")
            else:
                notify.alert(f"gwhost:{name}", f"{name} ({h.get('gpu', 'GPU')}) does not answer and is marked as always on.")
    c.execute("delete from gwhost where ts < ?", (now - 90 * 86400,))
    return state


CLAUDE_FIX = {"auth": "the Claude session expired on that machine: run `claude auth login` there",
              "key": "the SSH key is no longer authorized on that machine",
              "unreachable": "the machine is off or not reachable over the network",
              "timeout": "Claude took longer than the limit (15 min by default)"}


def gateway_alerts(name, calls):
    for d in calls:
        g = d.get("gateway")
        if g == "transcode" and d.get("fallback"):
            down = ", ".join(d.get("down") or []) or "none configured"
            notify.alert(f"gw:{name}:transcode", f"{name}: a video was processed on the server CPU ({d.get('seconds')} s, "
                                                 f"{d.get('mb_in')} MB) because no GPU host answered ({down}).")
        elif g == "transcode" and d.get("ok"):
            notify.resolve(f"gw:{name}:transcode", f"{name}: videos go to the GPU again")
        elif g == "upscale" and not d.get("ok"):
            notify.alert(f"gw:{name}:upscale", f"{name}: an image could not be enlarged: no GPU host answered.")
        elif g == "upscale":
            notify.resolve(f"gw:{name}:upscale")
        elif g == "claude" and not d.get("ok"):
            err = d.get("error") or "other"
            notify.alert(f"gw:{name}:claude", f"{name}: Claude on {d.get('host')} failed ({err}): "
                                              f"{CLAUDE_FIX.get(err, 'see the stack log')}.")
        elif g == "claude":
            notify.resolve(f"gw:{name}:claude", f"{name}: Claude vuelve a responder")


def host_sample():
    mem = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":", 1)
        mem[k] = int(v.split()[0]) // 1024
    st = os.statvfs("/")
    disk = round(100 * (1 - st.f_bavail / st.f_blocks))
    return mem.get("MemAvailable", 0), mem.get("SwapTotal", 0) - mem.get("SwapFree", 0), disk


# ---------------- per-container resources (host cgroup files, no docker exec) ----------------
CGROUP_ROOT = "/sys/fs/cgroup"


def running_containers():
    """{container name: full id} of every running container (one `docker ps` per collect), None when docker did not answer."""
    r = sh("docker", "ps", "--no-trunc", "--format", "{{.ID}} {{.Names}}", timeout=30)
    if r.returncode != 0:
        return None
    out = {}
    for line in r.stdout.splitlines():
        cid, _, name = line.partition(" ")
        if re.fullmatch(r"[0-9a-f]{64}", cid) and name:
            out[name.strip()] = cid
    return out


def stack_containers(s):
    """[(role, container name)] of one stack: brain, webui (Open WebUI), voice, web (the front), telegram-bot-api."""
    out = [("brain", s["brain"])]
    for w in s.get("web") or []:
        out.append(("voice" if "voice" in w else "webui", w))
    if s.get("front"):
        out.append(("web", s["front"]))
    if s.get("telegram_api"):
        out.append(("telegram-bot-api", s["telegram_api"]))
    return out


def cgroup_read(cid):
    """{cpu_usec, mem, peak, pids} of a container from its cgroup v2 directory (systemd driver: system.slice/docker-<id>.scope;
    cgroupfs driver: docker/<id>), or None. Readable by any user: no docker exec, nothing inside the container is touched."""
    for d in (os.path.join(CGROUP_ROOT, "system.slice", f"docker-{cid}.scope"), os.path.join(CGROUP_ROOT, "docker", cid)):
        if not os.path.isdir(d):
            continue

        def val(f):
            try:
                with open(os.path.join(d, f)) as fh:
                    return fh.read()
            except OSError:
                return ""
        cpu = re.search(r"^usage_usec (\d+)", val("cpu.stat"), re.M)
        num = lambda f: int(val(f).strip()) if val(f).strip().isdigit() else None
        if not cpu:
            return None
        return {"cpu_usec": int(cpu.group(1)), "mem": num("memory.current"), "peak": num("memory.peak"), "pids": num("pids.current")}
    return None


def sample_res(c, stacks, now, running, containers=None):
    """One `res` row per running stack container: CPU seconds used since its previous row (cgroup usage_usec delta; NULL on the very
    first sample, the whole usage when the container is new or restarted since), memory now and peak (since the container started),
    pids, and on the brain row the subagents running now. Returns {stack: totals} for the Zabbix push."""
    containers = running_containers() if containers is None else containers
    fresh = meta_get(c, "res_last") is None        # the first sample ever has nothing to compare with
    agg = {}
    for s in stacks:
        a = agg.setdefault(s["name"], {"awake": int(s["brain"] in containers), "cpu_s": 0.0, "secs": None, "mem_mb": 0.0,
                                        "subagents": running.get(s["name"]) if s["brain"] in containers else 0})
        for role, cname in stack_containers(s):
            cid = containers.get(cname)
            g = cgroup_read(cid) if cid else None
            if not g:
                continue
            prev = c.execute("select ts, cpu_usec from res where stack=? and role=? and cid=? order by ts desc limit 1",
                             (s["name"], role, cid[:12])).fetchone()
            if prev:
                secs = now - prev[0]
                cpu_s = (g["cpu_usec"] - prev[1] if g["cpu_usec"] >= prev[1] else g["cpu_usec"]) / 1e6   # lower: restarted since
            elif fresh:
                secs = cpu_s = None
            else:
                last = float(meta_get(c, "res_last"))
                secs, cpu_s = now - last, g["cpu_usec"] / 1e6     # started since the last sample
            mb = lambda v: round(v / 1048576, 1) if v is not None else None
            c.execute("insert into res values(?,?,?,?,?,?,?,?,?,?,?)",
                      (now, s["name"], role, cid[:12], round(secs, 1) if secs is not None else None, g["cpu_usec"],
                       round(cpu_s, 3) if cpu_s is not None else None, mb(g["mem"]), mb(g["peak"]), g["pids"],
                       a["subagents"] if role == "brain" else None))
            if cpu_s is not None and secs:
                a["cpu_s"] += cpu_s
                a["secs"] = max(a["secs"] or 0, secs)
            a["mem_mb"] += mb(g["mem"]) or 0
    meta_set(c, "res_last", now)
    c.execute("delete from res where ts < ?", (now - 90 * 86400,))
    return agg


# ---------------- Zabbix push (optional, off unless STACKS_ZBX_HOST and a server are set) ----------------
OPS_ENV = os.environ.get("OPS_ENV", os.path.expanduser("~/aibridge/ops/ops.env"))


def zbx_conf(env=None):
    """STACKS_ZBX_SERVER (else ZBX_SERVER), STACKS_ZBX_PORT (else ZBX_PORT, 10051) and STACKS_ZBX_HOST from ops.env and the environment."""
    conf = {}
    try:
        for line in open(OPS_ENV):
            k, sep, v = line.partition("=")
            if sep and not k.lstrip().startswith("#") and k.strip() in ("STACKS_ZBX_SERVER", "STACKS_ZBX_PORT", "STACKS_ZBX_HOST",
                                                                        "ZBX_SERVER", "ZBX_PORT"):
                conf[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    for k, v in (os.environ if env is None else env).items():
        if k.startswith(("STACKS_ZBX_", "ZBX_")):
            conf[k] = v
    return {"server": conf.get("STACKS_ZBX_SERVER") or conf.get("ZBX_SERVER", ""), "host": conf.get("STACKS_ZBX_HOST", ""),
            "port": conf.get("STACKS_ZBX_PORT") or conf.get("ZBX_PORT") or "10051"}


def zbx_values(host, agg):
    """(host, key, value) for one push: the stack discovery, then per stack awake (0/1), running subagents, CPU % of one core over the
    last interval (all its containers) and memory MB now; plus the totals. A value not known this time is left out, never sent as 0."""
    vals = [(host, "stack.discovery", json.dumps([{"{#STACK}": n} for n in sorted(agg)]))]
    for n, a in sorted(agg.items()):
        vals += [(host, f"stack.awake[{n}]", a["awake"]), (host, f"stack.mem_mb[{n}]", round(a["mem_mb"], 1))]
        if isinstance(a.get("subagents"), int):
            vals.append((host, f"stack.subagents[{n}]", a["subagents"]))
        if a.get("secs"):
            vals.append((host, f"stack.cpu_pct[{n}]", round(100 * a["cpu_s"] / a["secs"], 1)))
    vals += [(host, "stack.awake.total", sum(a["awake"] for a in agg.values())),
             (host, "stack.subagents.total", sum(a["subagents"] for a in agg.values() if isinstance(a.get("subagents"), int)))]
    return vals


def zbx_send(items, server, port=10051, timeout=5):
    """Zabbix trapper protocol over TCP, no zabbix_sender needed (the same packet as gpu-host/gate/host_control.zbx_send).
    Returns (processed, failed); raises OSError / ValueError."""
    import socket, struct
    body = json.dumps({"request": "sender data", "data": [{"host": h, "key": k, "value": str(v)} for h, k, v in items]}).encode()
    with socket.create_connection((server, int(port)), timeout=timeout) as s:
        s.sendall(b"ZBXD\x01" + struct.pack("<Q", len(body)) + body)
        buf = b""
        while len(buf) < 13:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
        if len(buf) < 13 or buf[:4] != b"ZBXD":
            raise ValueError("no Zabbix header in the answer")
        size = struct.unpack("<Q", buf[5:13])[0]
        if size > 65536:
            raise ValueError("answer too large")
        while len(buf) < 13 + size:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    info = json.loads(buf[13:13 + size].decode())
    m = re.search(r"processed: (\d+); failed: (\d+)", info.get("info", ""))
    if info.get("response") != "success" or not m:
        raise ValueError("Zabbix refused the values")
    return int(m.group(1)), int(m.group(2))


def push_stacks(agg, conf=None, send=None):
    """None when the push is off (no STACKS_ZBX_HOST or no server), else (processed, failed), or (0, -1) when Zabbix could not be
    reached. Never raises: a Zabbix that is down must not stop the collection."""
    conf = conf or zbx_conf()
    if not conf["server"] or not conf["host"]:
        return None
    try:
        return (send or zbx_send)(zbx_values(conf["host"], agg), conf["server"], conf["port"])
    except (OSError, ValueError):
        return 0, -1


def collect_stack(c, s, now, last_run, first, new_turns, running=None):
    """Read one stack's turns, delegations, API errors and gateway log into the db. Raises when its data cannot be read.
    `running` (a dict) gets {stack: subagents running now}."""
    name = s["name"]
    # Watermark: a turn is stored when it closes (or after 900 s), so a later turn of another session can close
    # first. Re-read LOOKBACK_S behind the newest stored one; unique(stack, ts, session) + rowcount drop the repeats.
    mx = c.execute("select max(ts) from turns where stack=?", (name,)).fetchone()[0]
    since = mx - LOOKBACK_S if mx else now - FIRST_LOOKBACK_S
    data = stack_read(s, since)
    if data is None:
        raise RuntimeError("turns read failed")
    img = booted_image(name)
    for t in data["turns"]:
        kind = t.get("kind") if t.get("kind") in ("person", "subagent", "cron") else ("cron" if t.get("source") == "cron" else "person")
        cur = c.execute("insert or ignore into turns(stack, ts, session, source, model, seconds, tools, tool_errors, failed, empty, image, kind) "
                        "values(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (name, t["ts"], t["session"], t["source"], t["model"], t["seconds"], t["tools"],
                         t["tool_errors"], t["failed"], t["empty"], img, kind))
        if cur.rowcount and kind != "subagent":   # a subagent's own turns never raise the person's alerts
            new_turns.append((name, t))
    store_delegations(c, name, data["delegs"], now, img)
    if running is not None:
        running[name] = data["running"]
    for ts, prov, model, code in stack_errors(s):
        c.execute("insert or ignore into errors values(?,?,?,?,?)", (name, ts, prov, model, code))
    gw_since = c.execute("select max(ts) from gw where stack=?", (name,)).fetchone()[0] or now - FIRST_LOOKBACK_S
    calls = stack_gateway_log(s, gw_since)
    for d in calls:
        c.execute("insert or ignore into gw values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (name, d.get("ts"), d.get("gateway"), d.get("host"), int(bool(d.get("ok"))), int(bool(d.get("fallback"))),
                   d.get("seconds"), d.get("gpu_seconds"), d.get("cpu_seconds"), d.get("mb_in"), d.get("mb_out"),
                   d.get("error"), ",".join(d.get("down") or [])))
    if not first:
        gateway_alerts(name, calls)


def blind_update(c, name, ok):
    """Count consecutive failed reads of a stack; alert after BLIND_TICKS, resolve on the first good read."""
    key = f"blind:{name}"
    if ok:
        if int(meta_get(c, key, 0) or 0):
            meta_set(c, key, 0)
        notify.resolve(f"tele:{name}:blind", f"{name}: telemetry reads the stack data again")
        return
    n = int(meta_get(c, key, 0) or 0) + 1
    meta_set(c, key, n)
    if n >= BLIND_TICKS:
        notify.alert(f"tele:{name}:blind", f"{name}: telemetry cannot read the stack data for {n} readings in a row "
                                           f"(failed or slow turns of this stack are not visible).", quiet=3600)


def collect(c, stacks):
    now = time.time()
    try:
        notify.flush()   # the outbox only retries inside a real send: do it every tick
    except Exception as e:
        print(f"collect: outbox flush failed ({type(e).__name__})")
    first = meta_get(c, "last_collect") is None   # first run loads a week of history: no alerts for old things
    last_run = float(meta_get(c, "last_collect", now - FIRST_LOOKBACK_S))
    new_turns, running = [], {}
    for s in stacks:
        name = s["name"]
        try:
            if not ran_since(s["brain"], last_run - 60):
                end_gone(c, name)   # asleep the whole interval: nothing of it still runs
                continue
            collect_stack(c, s, now, last_run, first, new_turns, running)
            good = True
        except Exception as e:   # one stack (hung docker exec, odd log record) must not stop the others
            print(f"[{name}] collect failed ({type(e).__name__}: {str(e)[:120]})")
            good = False
        c.commit()
        try:
            blind_update(c, name, good)
            c.commit()
        except Exception as e:
            print(f"[{name}] blind counter failed ({type(e).__name__})")
    since_j = dt.datetime.fromtimestamp(last_run - 60, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    r = sh("journalctl", "--user", "-u", "aibridge-waker", "--since", since_j + " UTC", "--no-pager", "-o", "cat")
    for line in r.stdout.splitlines():
        m = WAKE_RE.match(line)
        if not m:
            continue
        ts, name, what = epoch(m.group(1)), m.group(2), m.group(3)
        if what.startswith("ready"):
            row = (name, ts, m.group(5), float(m.group(4)), "ok")
        elif what.startswith("boot"):
            row = (name, ts, "", None, "timeout")
        elif what.startswith("wake"):
            row = (name, ts, m.group(6), None, "no_memory")
        else:
            row = (name, ts, "", None, "evicted")
        c.execute("insert or ignore into wakes values(?,?,?,?,?)", row)
    for s in stacks:
        p = tts_probe(s)
        if p is None:
            continue
        ok, secs, detail = p
        if ok:
            notify.resolve(f"tts:{s['name']}", f"{s['name']}: the voice (TTS) works again")
        elif not first:
            notify.alert(f"tts:{s['name']}", f"{s['name']}: the voice (TTS) does not answer ({detail}, {secs:.0f} s). "
                                             f"The web call mode stays mute.")
    probe_gateway_hosts(c, now)
    containers = running_containers()
    if containers is None:   # docker did not answer: no reconciliation and no resource sample this time
        print("collect: docker ps failed, no resource sample")
        containers = {s["brain"]: "" for s in stacks if inspect(s["brain"], "{{.State.Running}}") == "true"}
        containers.update({s["web"][0]: "" for s in stacks if s.get("web") and inspect(s["web"][0], "{{.State.Running}}") == "true"})
        sampled = False
    else:
        sampled = True
        for s in stacks:
            if s["brain"] not in containers:
                end_gone(c, s["name"])   # read from its persisted copy after it stopped: a stop halts every subagent it had
    brains = sum(1 for s in stacks if s["brain"] in containers)
    webs = sum(1 for s in stacks if s.get("web") and s["web"][0] in containers)
    c.execute("insert into awake values(?,?,?)", (now, brains, webs))
    try:
        if sampled:
            agg = sample_res(c, stacks, now, running, containers)
            z = push_stacks(agg)
            if z and z[1]:
                print("collect: Zabbix push " + ("failed (server not reachable or refused)" if z[1] < 0 else f"{z[1]} value(s) refused"))
    except Exception as e:   # the resource sample must never stop the collection
        print(f"collect: resource sample failed ({type(e).__name__}: {str(e)[:120]})")
    c.execute("delete from awake where ts < ?", (now - 90 * 86400,))
    c.execute("delete from delegations where started < ?", (now - 365 * 86400,))
    mem, swap, disk = host_sample()
    c.execute("insert into host values(?,?,?,?)", (now, mem, swap, disk))
    c.execute("delete from host where ts < ?", (now - 90 * 86400,))
    meta_set(c, "last_collect", now)
    c.commit()
    if not first:
        alerts(c, stacks, new_turns, disk)
        c.commit()
    print(f"collect: {len(new_turns)} new turn(s), host avail={mem}MB swap={swap}MB disk={disk}%")


SRC_LABEL = {"telegram": "Telegram", "api_server": "web", "cron": "cron", "oneshot": "CLI"}


def clean_streak(c, name, kind, bad, good):
    """Consecutive clean samples for tele:<name>:<kind>: a bad one resets it, `good` more extend it. Meta counter."""
    key = f"clean:{name}:{kind}"
    n = 0 if bad else int(meta_get(c, key, 0) or 0) + good
    if bad or good:
        meta_set(c, key, n)
    return n


def alerts(c, stacks, new_turns, disk):
    by_stack = {}
    for name, t in new_turns:
        by_stack.setdefault(name, []).append(t)
    for name, turns in by_stack.items():
        failed = [t for t in turns if t["failed"]]
        empty = [t for t in turns if t["empty"]]
        slow = [t for t in turns if not t["failed"] and t["tools"] == 0 and (t["seconds"] or 0) > SLOW_PLAIN_TURN_S]
        if failed:
            where = ", ".join(sorted({SRC_LABEL.get(t["source"], t["source"]) for t in failed}))
            notify.alert(f"tele:{name}:failed", f"{name}: {len(failed)} turn(s) failed or got no answer ({where}). "
                                                f"The person received no reply.", quiet=3600)
        if empty:
            notify.alert(f"tele:{name}:empty", f"{name}: {len(empty)} empty reply(ies) (the model returned blank text).",
                         quiet=3600)
        if slow:
            worst = max(t["seconds"] for t in slow)
            notify.alert(f"tele:{name}:slow", f"{name}: {len(slow)} reply(ies) without tools took longer than "
                                              f"{SLOW_PLAIN_TURN_S} s (the worst {worst:.0f} s). Check the model/provider.")
        # Resolve only after RESOLVE_CLEAN clean turns in a row (one lucky cron turn is not "fixed")
        ok = [t for t in turns if not t["failed"] and not t["empty"]]
        if clean_streak(c, name, "failed", failed, len(ok)) >= RESOLVE_CLEAN:
            notify.resolve(f"tele:{name}:failed", f"{name}: answers well again")
        if clean_streak(c, name, "empty", empty, len(ok)) >= RESOLVE_CLEAN:
            notify.resolve(f"tele:{name}:empty")
        fast = [t for t in turns if not t["failed"] and t["tools"] == 0 and (t["seconds"] or 0) <= SLOW_PLAIN_TURN_S]
        if clean_streak(c, name, "slow", slow, len(fast)) >= RESOLVE_CLEAN:
            notify.resolve(f"tele:{name}:slow", f"{name}: simple replies are fast again")
    if disk >= DISK_ALERT_PCT:
        notify.alert("host:disk", f"Disk at {disk}% on the stacks host.")
    elif disk < DISK_RESOLVE_PCT:
        notify.resolve("host:disk", f"Disk back to {disk}%")
    for name, age in backup_ages(stacks).items():
        if age is not None and age > BACKUP_MAX_AGE_H:
            notify.alert(f"backup:{name}", f"{name}: the last backup is {age:.0f} h old.")
        elif age is not None:
            notify.resolve(f"backup:{name}", f"{name}: there is a new backup")


def backup_ages(stacks):
    """{stack: hours since its newest backup archive, or None if it is not backed up at all}."""
    ages = {}
    for s in stacks:
        newest = 0
        try:
            for f in os.listdir(BACKUPS):
                if re.fullmatch(re.escape(s["name"]) + r"-\d{8}-\d{4}\.tar\.gz", f):
                    newest = max(newest, os.path.getmtime(os.path.join(BACKUPS, f)))
        except OSError:
            pass
        ages[s["name"]] = (time.time() - newest) / 3600 if newest else None
    return ages


# ---------------- reports ----------------
def pct(values, p):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))]


def fmt_s(x):
    return "-" if x is None else (f"{x:.0f} s" if x < 120 else f"{x / 60:.1f} min")


def stack_lines(c, name, t0):
    rows = c.execute("select source, seconds, tools, tool_errors, failed, empty, session from turns where stack=? and ts>=? and " + PERSON,
                     (name, t0)).fetchall()
    wk = c.execute("select seconds, outcome from wakes where stack=? and ts>=?", (name, t0)).fetchall()
    # Hermes's background review/curator call the router as model "local-only" and retry 3 times when every home host is
    # off (a 503 "local model unavailable" each time, nobody waiting). Counted apart so they do not read as outages.
    er = c.execute("select provider, code, count(*) from errors where stack=? and ts>=? and model!=? group by 1,2 order by 3 desc",
                   (name, t0, BG_MODEL)).fetchall()
    bg = c.execute("select count(*) from errors where stack=? and ts>=? and model=?", (name, t0, BG_MODEL)).fetchone()[0]
    sub = c.execute("select count(*), sum(tasks), sum(failed + timeout + interrupted), sum(status='gone'), max(duration) "
                    "from delegations where stack=? and started>=?", (name, t0)).fetchone()
    if not rows and not wk and not er and not bg and not sub[0]:
        return None, {}
    secs = [r[1] for r in rows if not r[4]]
    src = {}
    for r in rows:
        src[SRC_LABEL.get(r[0], r[0] or "?")] = src.get(SRC_LABEL.get(r[0], r[0] or "?"), 0) + 1
    stats = {"turns": len(rows), "sessions": len({r[6] for r in rows}), "failed": sum(r[4] for r in rows),
             "empty": sum(r[5] for r in rows), "tool_errors": sum(r[3] for r in rows), "tools": sum(r[2] for r in rows),
             "p50": pct(secs, 50), "p95": pct(secs, 95),
             "wake_p50": pct([w[0] for w in wk if w[1] == "ok"], 50), "wakes": len(wk),
             "wake_bad": sum(1 for w in wk if w[1] in ("timeout", "no_memory")), "errors": er}
    lines = [f"• {name}: {stats['turns']} turns in {stats['sessions']} conversations ("
             + ", ".join(f"{k} {v}" for k, v in sorted(src.items())) + ")" if rows else f"• {name}: no turns"]
    if rows:
        lines.append(f"   reply p50 {fmt_s(stats['p50'])}, p95 {fmt_s(stats['p95'])}; tools {stats['tools']} "
                     f"({stats['tool_errors']} with error)")
    if stats["failed"] or stats["empty"]:
        lines.append(f"   ⚠️ {stats['failed']} failed, {stats['empty']} empty")
    if wk:
        lines.append(f"   wakes {stats['wakes']} (median {fmt_s(stats['wake_p50'])})"
                     + (f", ⚠️ {stats['wake_bad']} with a problem" if stats["wake_bad"] else ""))
    if er:
        lines.append("   API errors: " + ", ".join(f"{p} {code}×{n}" for p, code, n in er[:4]))
    if bg:
        lines.append(f"   background tasks without a home model: {bg} attempts (nobody was waiting; they retry by themselves)")
    if sub[0]:
        lines.append(f"   subagents: {sub[0]} delegations, {sub[1] or 0} tasks, longest {fmt_s(sub[4])}"
                     + (f", ⚠️ {sub[2]} failed/timed out" if sub[2] else "") + (f", {sub[3]} cut by a stop" if sub[3] else ""))
    return "\n".join(lines), stats


REPORT_MAX_DAYS = 14


def report(c, stacks, kind, to_stdout):
    """The summary since the last one sent (2026-11-27: the Docker host now sends it in its awake window before suspending, at an irregular
    hour, so a fixed "last 24 h" would skip or repeat hours). The first report, or one after a long gap, covers 1 day (weekly: 7) up to
    REPORT_MAX_DAYS. The mark moves only after notify.send returned (sent, or kept in its outbox for a retry): a run stopped before that
    (SIGTERM) sends nothing and the next run covers the same span; one stopped between the send and the mark repeats that span once,
    never half of it."""
    days = 7 if kind == "weekly" else 1
    now = time.time()
    last = float(meta_get(c, f"last_report:{kind}", 0) or 0)
    t0 = last if now - REPORT_MAX_DAYS * 86400 < last < now else now - days * 86400
    hours = max(1, round((now - t0) / 3600))
    when = time.strftime("%d/%m %H:%M", time.localtime(t0))
    title = (f"📊 Weekly summary (since {when}, {hours} h)" if kind == "weekly" else f"📊 Summary since {when} ({hours} h)")
    out, all_stats = [title], {}
    for s in stacks:
        text, st = stack_lines(c, s["name"], t0)
        if int(meta_get(c, f"blind:{s['name']}", 0) or 0):
            text = (text + "\n" if text else "") + f"   ⚠️ {s['name']}: no data read (telemetry could not read this stack; the numbers may be incomplete)"
        if text:
            out.append(text)
            all_stats[s["name"]] = st
    h = c.execute("select min(mem_avail_mb), max(swap_used_mb), max(disk_pct) from host where ts>=?", (t0,)).fetchone()
    if h and h[0] is not None:
        out.append(f"• host: minimum free RAM {h[0]} MB, max swap {h[1]} MB, disk {h[2]}%")
    a = c.execute("select max(brains), avg(brains) from awake where ts>=?", (t0,)).fetchone()
    if a and a[0] is not None:
        out.append(f"• stacks awake at once: max {a[0]}, average {a[1]:.1f} (of {len(stacks)}; ~0.9 GB each)")
    out.extend(gateway_report(c, t0))
    out.extend(learning_report(stacks, t0))
    missing = [n for n, a in backup_ages(stacks).items() if a is None]
    if missing:
        out.append("• no backup: " + ", ".join(missing))
    if kind == "weekly":
        out.append("\n🔧 What to improve first (impact = times × people affected):")
        out.extend(ranking(c, stacks, t0) or ["  nothing stands out this week"])
    if len(out) == 1:
        out.append("No activity.")
    text = "\n".join(out)
    if to_stdout:
        print(text)
    else:
        notify.send(text)                          # True = sent; False = kept in notify's outbox, which the next call retries
        meta_set(c, f"last_report:{kind}", now)    # either way this span is delivered: the next report starts here


def gateway_report(c, t0):
    """Per gateway: use, outcome, time, and what it means in practice (GPU vs CPU, share of all turn time)."""
    lines = []
    turn_total = c.execute("select sum(seconds) from turns where ts>=? and seconds is not null and " + PERSON, (t0,)).fetchone()[0] or 0
    for g, n, ok, fb, secs, p50 in c.execute(
            "select gateway, count(*), sum(ok), sum(fallback), sum(seconds), avg(seconds) from gw where ts>=? and %s group by 1" % GW_OK_ROW,
            (t0,)):
        if g == "router":
            routes = dict(c.execute("select host, count(*) from gw where gateway='router' and host is not null and ts>=? group by 1", (t0,)))
            lines.append(f"• router: {n} decisions: " + ", ".join(f"{label} {routes[r]}" for r, label in
                                                                   ROUTER_ROUTES.items() if routes.get(r)))
            if routes.get("none"):
                lines.append(f"   ⚠️ {routes['none']} turns with no model that answered")
            if routes.get("colgado"):
                lines.append(f"   ⚠️ {routes['colgado']} times a cloud model did not answer in 90 s and moved to the end of the list")
            for why, k in c.execute("select error, count(*) from gw where gateway='router' and host='rechazo' and ts>=? "
                                    "group by 1 order by 2 desc limit 3", (t0,)):
                lines.append(f"   ⚠️ refusal x{k}: {why}")
            continue
        if g == "content-guard":   # hits only (text that talked to the AI); the tool is in `host`, the patterns in `error`
            by = ", ".join(f"{h} {k}" for h, k in c.execute(
                "select host, count(*) from gw where gateway='content-guard' and ts>=? group by 1 order by 2 desc", (t0,)))
            lines.append(f"• content-guard: {n} warning(s) of text aimed at the AI ({by}); check whether any was a legitimate job ad")
            continue
        line = f"• gateway {g}: {n} calls, {ok} ok"
        if fb:
            line += f", {fb} on CPU for lack of a GPU"
        line += f", {fmt_s(secs)} in total"
        if turn_total:
            line += f" ({100 * (secs or 0) / turn_total:.0f}% of the time of all turns)"
        lines.append(line)
        if g == "tts":   # which voice engine answered: the HQ host (Chatterbox, host name ends in -hq), Piper hosts, or Edge (cloud)
            by = ", ".join(f"{h or 'edge (cloud)'} {k} (~{fmt_s(a)} each)" for h, k, a in c.execute(
                "select host, count(*), avg(seconds) from gw where gateway='tts' and ok=1 and ts>=? group by 1 order by 2 desc", (t0,)))
            lines.append(f"   answered: {by}")
            fell = c.execute("select count(*) from gw where gateway='tts' and ok=1 and ts>=? and down like '%-hq%'", (t0,)).fetchone()[0]
            if fell:
                lines.append(f"   ⚠️ {fell} reply(ies) fell back to another voice because the HQ host (Chatterbox) did not answer")
            if any(h is None for h, in c.execute("select host from gw where gateway='tts' and ok=1 and ts>=?", (t0,))):
                lines.append("   ⚠️ voice went through Edge (cloud): no home voice host answered")
        if g == "transcode":
            gpu = c.execute("select sum(seconds), sum(mb_in) from gw where gateway='transcode' and fallback=0 and ok=1 and ts>=?",
                            (t0,)).fetchone()
            cpu = c.execute("select sum(seconds), sum(mb_in) from gw where gateway='transcode' and fallback=1 and ok=1",
                            ()).fetchone()
            if gpu[0] and gpu[1] and cpu[0] and cpu[1]:
                saved = gpu[1] * (cpu[0] / cpu[1]) - gpu[0]   # same MB at the CPU's measured s/MB, minus what GPU took
                lines.append(f"   the GPU saved ~{fmt_s(max(saved, 0))} compared with doing it on CPU (measured with the real CPU cases)")
        for host, err, k in c.execute("select host, error, count(*) from gw where gateway=? and ok=0 and ts>=? and " + GW_OK_ROW + " group by 1,2",
                                      (g, t0)):
            lines.append(f"   ⚠️ {k} failures on {host or '?'}: {err}")
    for host, up, total in c.execute("select host, sum(up), count(*) from gwhost where ts>=? group by 1", (t0,)):
        lines.append(f"• host {host}: available {100 * up / total:.0f}% of the time")
    return lines


def ranking(c, stacks, t0):
    issues = {}

    def add(key, label, n, who):
        if n:
            e = issues.setdefault(key, {"label": label, "n": 0, "who": set()})
            e["n"] += n
            e["who"].add(who)
    for s in stacks:
        name = s["name"]
        r = c.execute("select sum(failed), sum(empty), sum(tool_errors), "
                      "sum(case when failed=0 and tools=0 and seconds>? then 1 else 0 end) from turns where stack=? and ts>=? and " + PERSON,
                      (SLOW_PLAIN_TURN_S, name, t0)).fetchone()
        add("failed", "failed turns or turns without an answer", r[0] or 0, name)
        add("empty", "empty replies", r[1] or 0, name)
        add("tool_errors", "tools that returned an error", r[2] or 0, name)
        add("slow", f"simple replies longer than {SLOW_PLAIN_TURN_S} s", r[3] or 0, name)
        for prov, code, n in c.execute("select provider, code, count(*) from errors where stack=? and ts>=? and model!=? "
                                       "group by 1,2", (name, t0, BG_MODEL)):
            add(f"api:{prov}:{code}", f"{code} errors from {prov}", n, name)
        for g, k in c.execute("select gateway, count(*) from gw where stack=? and ts>=? and (ok=0 or fallback=1) and " + GW_OK_ROW + " group by 1",
                              (name, t0)):
            add(f"gw:{g}", f"gateway {g} without its machine (failed or fell back to CPU)", k, name)
        w = c.execute("select sum(case when outcome in ('timeout','no_memory') then 1 else 0 end), "
                      "sum(case when outcome='ok' and seconds>30 then 1 else 0 end) from wakes where stack=? and ts>=?",
                      (name, t0)).fetchone()
        add("wake_bad", "wakes that failed (timeout or out of memory)", w[0] or 0, name)
        add("wake_slow", "wakes longer than 30 s", w[1] or 0, name)
    ranked = sorted(issues.values(), key=lambda e: e["n"] * len(e["who"]), reverse=True)
    return [f"  {i}. {e['label']}: {e['n']} ({', '.join(sorted(e['who']))})" for i, e in enumerate(ranked[:6], 1)]


def builds(c, days=14):
    """Per build (the image a stack booted): turns, failed and empty share, median seconds, stacks. Counts only, never text. The data for
    rolling out by build (2026-11-27): a person keeps their build until their stack is updated, so builds are compared on real use."""
    t0 = time.time() - days * 86400
    rows = c.execute("select coalesce(image, '?'), stack, seconds, failed, empty from turns where ts>=? and " + PERSON, (t0,)).fetchall()
    by = {}
    for img, stack, secs, failed, empty in rows:
        b = by.setdefault(img, {"n": 0, "failed": 0, "empty": 0, "secs": [], "stacks": set()})
        b["n"] += 1; b["failed"] += bool(failed); b["empty"] += bool(empty); b["stacks"].add(stack)
        if isinstance(secs, (int, float)):
            b["secs"].append(secs)
    out = [f"builds, last {days} days (turns, failed, empty, median s, stacks):"]
    for img, b in sorted(by.items(), key=lambda kv: -kv[1]["n"]):
        sc = sorted(b["secs"]); med = sc[len(sc) // 2] if sc else 0
        out.append(f"  {img:12s} {b['n']:5d}  {100 * b['failed'] / b['n']:5.1f}%  {100 * b['empty'] / b['n']:5.1f}%  {med:6.1f}  {len(b['stacks'])}")
    return "\n".join(out if by else out + ["  no turns"])


def merge_intervals(spans):
    out = []
    for lo, hi in sorted(spans):
        if out and lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def subagent_cpu(c, stack, spans):
    """(CPU seconds, max brain MB) of the stack's `res` samples whose interval (ts - secs, ts] overlaps one of `spans` (merged first,
    so overlapping delegations are not counted twice). An UPPER bound: a sample counts whole, with every container of the stack and
    whatever else the stack did in that interval (the person's own turns included)."""
    cpu, peak, used = 0.0, None, set()
    for lo, hi in merge_intervals(spans):
        for rowid, cpu_s, role, mem in c.execute("select rowid, cpu_s, role, mem_mb from res where stack=? and ts>? and ts-coalesce(secs, 300)<?",
                                                 (stack, lo, hi)):
            if rowid in used:
                continue
            used.add(rowid)
            cpu += cpu_s or 0
            if role == "brain" and mem is not None:
                peak = mem if peak is None else max(peak, mem)
    return cpu, peak


def subagents_report(c, days=7, now=None):
    """Per stack: delegate_task delegations and tasks, median/max duration, failed share, children's model API calls, tool calls and
    tokens (when Hermes recorded them), and the CPU seconds of the stack over the subagents' intervals (an upper bound)."""
    now = now or time.time()
    t0 = now - days * 86400
    out = [f"🤖 Subagents (delegate_task), last {days} days"]
    stacks = [r[0] for r in c.execute("select distinct stack from delegations where started>=? order by 1", (t0,))]
    for st in stacks:
        rows = c.execute("select started, coalesce(ended, last_seen), duration, status, tasks, ok, failed, interrupted, timeout, running, "
                         "api_calls, tool_calls, tokens_in, tokens_out from delegations where stack=? and started>=?", (st, t0)).fetchall()
        durs = sorted(r[2] for r in rows if isinstance(r[2], (int, float)))
        tasks = sum(r[4] or 0 for r in rows)
        bad = sum((r[6] or 0) + (r[7] or 0) + (r[8] or 0) for r in rows)
        lost = sum((r[9] or 0) for r in rows if r[3] == "gone")
        now_running = sum((r[9] or 0) for r in rows if r[3] == "running")
        cpu, peak = subagent_cpu(c, st, [(r[0], r[1]) for r in rows if r[0] and r[1]])
        out.append(f"• {st}: {len(rows)} delegations, {tasks} tasks; duration median {fmt_s(durs[len(durs) // 2] if durs else None)}, "
                   f"max {fmt_s(durs[-1] if durs else None)}; failed {100 * bad / tasks if tasks else 0:.0f}%"
                   + (f", {lost} cut by a stop or a prune" if lost else "") + (f", {now_running} running now" if now_running else ""))
        out.append(f"   children: {sum(r[10] or 0 for r in rows)} model calls, {sum(r[11] or 0 for r in rows)} tool calls, "
                   f"{sum(r[12] or 0 for r in rows)} tokens in / {sum(r[13] or 0 for r in rows)} out")
        out.append(f"   CPU over their intervals: at most {cpu:.0f} CPU-s (upper bound: every container of the stack, whole 5-min samples)"
                   + (f"; brain RAM up to {peak:.0f} MB" if peak is not None else ""))
    if not stacks:
        out.append("No subagents.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["collect", "report", "builds"])
    ap.add_argument("kind", nargs="?", default="daily", choices=["daily", "weekly", "subagents"])
    ap.add_argument("--print", action="store_true", help="report: print instead of sending")
    ap.add_argument("--days", type=int, default=7, help="report subagents: how many days back (default 7)")
    a = ap.parse_args()
    stacks = json.load(open(STACKS))["stacks"]
    c = db()
    if a.cmd == "collect":
        collect(c, stacks)
    elif a.cmd == "builds":
        print(builds(c))
    elif a.kind == "subagents":
        text = subagents_report(c, max(1, min(a.days, 365)))
        print(text) if a.print else notify.send(text)
    else:
        report(c, stacks, a.kind, a.print)
        if a.kind == "daily" and dt.datetime.now().weekday() == 0 and not a.print:
            report(c, stacks, "weekly", False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
