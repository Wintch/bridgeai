"""Notes for the next conversation, written when the person types /new.

Why: after /new a conversation starts from nothing. A new session once did not know about the long
download that was in progress and never called `session_search` to find out (the model has to think of it, and nothing
tells it to). The industry answer for work that outlives a context window is a progress file the next session reads on
its own (Anthropic's long-running-agents harness, "handoff" skills); the model must not have to remember to look.

What: on `on_session_finalize` with reason "new_session" (Telegram and the other chat platforms; never the per-request
API sessions or cron) this plugin reads the session that just ended from state.db, and writes /workdir/.hermes.md. Hermes
loads `.hermes.md` from the gateway's working directory (/workdir, which is no git repo, so only that exact file) into
the system prompt of every new session. No LLM call, no tokens: it is a copy of what the person said and what Hermes
itself already summarised.
  - the first request of the conversation and the last few, as the person wrote them (stamps and reply-language tags
    stripped; commands, location pins and system-injected notices left out);
  - the last reply of the assistant (where it stood);
  - Hermes's own compaction summary, only the sections about goal, active state, blockers, files and key context;
  - the background jobs the process registry holds at that moment (running, or finished in the last 6 hours): command,
    process id, when it started, the tail of its output, so the next conversation can `process poll` it;
  - first of all, "Work state when the person typed /new": the work ledger (trabajos.py) in full detail, one item each: id, label,
    state, start and end, the files it made, the reason it failed, and for a queued one the exact command; plus "Announced but not
    confirmed": sentences of the last replies that promise an action ("lanzo", "launching", "запускаю") with no tool call and no
    ledger entry after them (kept until a longer conversation replaces them, so a second /new does not lose them);
  - the last reply of the assistant for EVERY kept conversation, and for the latest also the two replies before it;
  - up to 3 conversations, newest first, none older than 7 days. A conversation is the chain of sessions a compaction (or /branch)
    made: a parent that ended with /new (session_reset, new_session, idle, daily...) is another conversation and is not folded in,
    so each one counts and starts with its own requests.
It follows Hermes's own rule for compaction handoffs (learned from stale-task resumption bugs): background reference ONLY,
the person's latest message wins, nothing is resumed on its own, and it must be verified against files and processes
before anything is called done or still running.

Safety: text that came from the web or from tools (the summary, the last reply, job output) goes through Hermes's own
context-file injection scanner piece by piece, and a flagged piece is dropped instead of letting the scanner block the
whole file; anything shaped like a key is masked. The file is private to the stack (its /workdir), like the chat itself.
A conversation with fewer than 2 real requests does not replace an earlier note. Any failure is logged and swallowed:
/new must never break because of this.
"""
import json
import logging
import os
import re
import sqlite3
import tempfile
import time

logger = logging.getLogger(__name__)

OUT_NAME = ".hermes.md"
STORE_NAME = ".hermes-handoff.json"
MAX_ENTRIES = 3
MAX_AGE_S = 7 * 86400
JOB_KEEP_S = 6 * 3600
MAX_JOBS = 6
TOTAL_CAP = 10000
WORK_CAP = 3200                 # per-section caps; the total above drops the oldest conversation first
CONV_CAP = 1900
WORK_ITEMS = 14
ANNOUNCE_KEEP = 6
REPLIES_BEFORE = 2              # replies kept before the last one, for the latest conversation
# Hermes's deliberate conversation boundaries (hermes_state_common._BOUNDARY_END_REASONS): a session that ended with one of these
# was left by the person (/new) or by a reset; its child is a new conversation. Compaction ("compression") and /branch continue one.
BOUNDARY_END = ("session_reset", "session_switch", "idle", "daily", "suspended", "resume_pending_expired", "new_session")
ANNOUNCE = re.compile(r"\b(?:lanzo|relanzo|empiezo|arranco|sigo con|voy a)\b|\b(?:launching|relaunching|starting|next i(?:'ll| will))\b"
                      r"|(?:запускаю|перезапускаю|начинаю)", re.I)
SKIP_PLATFORMS = {"", "api_server", "cron", "webhook"}

STAMP = re.compile(r"^\s*\[(?:[A-Za-z]{3} )?\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?: [+-]\d\d(?::?\d\d)?)?\]\s*")
REPLY_TAG = re.compile(r"^\s*\[reply in [^\]\n]{1,40}\]\s*")
NOT_A_REQUEST = re.compile(r"^\[(?:SYSTEM|System|IMPORTANT|Background|Note|CONTEXT|Your request was not|This turn did not|"
                           r"Operation interrupted|The user shared a location)", re.I)
KEY_PREFIXED = (r"sk-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}|thk_[A-Za-z0-9_-]{16,}"
                r"|hf_[A-Za-z0-9]{20,}")
KEY = re.compile(r"(" + KEY_PREFIXED + r"|[A-Za-z0-9_-]{40,})")
KEY_NAMED = re.compile(r"(" + KEY_PREFIXED + r")")              # for file names, paths and labels: a long name is not a key
SUMMARY_MARK = "[CONTEXT COMPACTION"
SUMMARY_END = "avoid repeating it:"
KEEP_SECTIONS = ("goal", "active task", "active state", "in progress", "pending user asks", "remaining work", "blocked",
                 "relevant files", "critical context", "key decisions")

HEADER = (
    "# Notes carried over from the previous conversation(s)\n\n"
    "Written automatically when the person typed /new. BACKGROUND REFERENCE ONLY: answer the person's latest message; "
    "do not start, resume or finish anything from these notes on your own. If the person refers to earlier work "
    "(\"seguí\", \"lo de antes\", \"la descarga\"), use them to know where things stood, and CHECK before you say "
    "anything is done or still running: the files, the `process` list and the logs are the truth, and this text may be "
    "hours old. For anything older or not listed here, use `session_search`.\n"
)


# ----------------------------------------------------------------------------------------------------------- text
def clean(text, limit, names=False):
    """One line of text for the notes: key-shaped strings masked, whitespace folded, cut to `limit`. names=True (file names, paths,
    labels): only the known key prefixes are masked, not any long word."""
    text = (KEY_NAMED if names else KEY).sub("[hidden]", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def request_text(content):
    """What the person wrote, or None when the row is not a request of theirs."""
    if not isinstance(content, str):
        return None
    text = content
    for _ in range(3):                                   # "[stamp] [reply in X] text", in either order
        text = REPLY_TAG.sub("", STAMP.sub("", text, count=1), count=1)
    text = text.strip()
    if len(text) < 12 or text.startswith("/") or NOT_A_REQUEST.match(text) or SUMMARY_MARK in text[:60]:
        return None
    return text


def summary_part(content):
    """The useful sections of Hermes's compaction summary, or ''."""
    i = content.find(SUMMARY_END)
    body = content[i + len(SUMMARY_END):] if i != -1 else content.split("\n\n", 1)[-1]
    parts = re.split(r"(?m)^##\s+", body)
    kept = []
    for p in parts[1:]:
        head, _, rest = p.partition("\n")
        if head.strip().lower().rstrip(":") in KEEP_SECTIONS and rest.strip():
            kept.append(f"{head.strip()}: {clean(rest, 600)}")
    if not kept and not parts[1:]:
        kept = [clean(body, 1500)]
    return " | ".join(kept)[:2400]


def lineage(db, sid, hops=6):
    """The session and its ancestors in the same conversation (a compaction or a /branch starts a child session). A parent that
    ended with /new or a reset belongs to another conversation: the chain stops there. A database without the end_reason column
    (an older schema) follows every parent."""
    out = []
    while sid and sid not in out and len(out) < hops:
        out.append(sid)
        row = db.execute("SELECT parent_session_id FROM sessions WHERE id=?", (sid,)).fetchone()
        parent = row[0] if row else None
        if parent:
            try:
                why = db.execute("SELECT end_reason FROM sessions WHERE id=?", (parent,)).fetchone()
            except sqlite3.OperationalError:
                why = None
            if why and why[0] in BOUNDARY_END:
                break
        sid = parent
    return out


def _has_calls(value):
    return value not in (None, "", "[]", "null", b"", 0)


def announced_in(replies):
    """Sentences of the assistant's replies that promise an action. `replies`: [(text, confirmed)], oldest first; a reply that already
    called a tool in the same turn confirms what it announced. Returns [(sentence, time)] newest last, without repeats."""
    out, seen = [], set()
    for text, ts, confirmed in replies:
        if confirmed:
            continue
        for sent in re.split(r"(?<=[.!?:;])\s+|\n+", text):
            sent = clean(sent, 220)
            if len(sent) >= 8 and ANNOUNCE.search(sent) and sent.lower() not in seen:
                seen.add(sent.lower())
                out.append((sent, ts))
    return out[-ANNOUNCE_KEEP:]


def read_session(db_path, sid):
    """{'requests': [...], 'last_reply': str, 'replies': [last 3 replies, oldest first], 'announced': [(sentence, time)],
    'summary': str, 'count': n} for the session `sid` (and its ancestors in the same conversation)."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
    try:
        ids = lineage(db, sid)
        marks = ",".join("?" * len(ids))
        has_calls = any(c[1] == "tool_calls" for c in db.execute("PRAGMA table_info(messages)"))
        rows = db.execute(f"SELECT role, content, timestamp{', tool_calls' if has_calls else ', NULL'} FROM messages WHERE session_id IN ({marks}) "
                          "ORDER BY timestamp, id", ids).fetchall()
    finally:
        db.close()
    requests, seen, summary, replies = [], set(), "", []
    for i, (role, content, ts, calls) in enumerate(rows):
        if not isinstance(content, str):
            continue
        if SUMMARY_MARK in content[:80]:
            summary = summary_part(content) or summary   # the latest one wins
            continue
        if role == "user":
            t = request_text(content)
            if t and t not in seen:
                seen.add(t)
                requests.append(t)
        elif role == "assistant" and content.strip():
            confirmed = _has_calls(calls)                 # it called a tool in this very message...
            for role2, _c, _t, calls2 in ([] if confirmed else rows[i + 1:]):   # ...or later in the same turn (up to the person's next message)
                if role2 == "user":
                    break
                if role2 == "tool" or _has_calls(calls2):
                    confirmed = True
                    break
            replies.append((content, ts, confirmed))
    return {"requests": requests, "last_reply": replies[-1][0] if replies else "", "replies": [r[0] for r in replies[-(REPLIES_BEFORE + 1):]],
            "announced": announced_in(replies[-4:]), "summary": summary, "count": len(requests)}


def jobs_from(registry, now):
    """Background jobs worth a line: running ones, and ones that ended in the last 6 hours."""
    out = []
    try:
        entries = registry.list_sessions()
    except Exception as exc:
        logger.warning("aibridge-handoff: the process registry could not be listed: %r", exc)
        return out
    for e in entries:
        running = e.get("status") == "running"
        ended = e.get("exited_at") or 0
        if not running and not (ended and now - ended < JOB_KEEP_S):
            continue
        started = now - int(e.get("uptime_seconds") or 0)
        out.append({"id": e.get("session_id"), "command": clean(e.get("command"), 260), "cwd": e.get("cwd") or "",
                    "running": running, "started": started, "ended": None if running else ended,
                    "exit_code": e.get("exit_code"), "tail": clean(e.get("output_preview"), 200),
                    "persist": bool(e.get("persist_on_release"))})
    out.sort(key=lambda j: (not j["running"], -(j["ended"] or j["started"])))
    return out[:MAX_JOBS]


# ---------------------------------------------------------------------------------------------------------- notes
def utc(ts):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts))


def make_entry(info, sid, now):
    reqs = info["requests"]
    return {"sid": sid, "ended": now, "requests": len(reqs),
            "first": clean(reqs[0], 400) if reqs else "", "last": [clean(r, 300) for r in reqs[1:][-4:]],           # the first one is already "first"
            "reply": clean(info["last_reply"], 600),
            "before": [clean(r, 350) for r in info.get("replies", [])[:-1][-REPLIES_BEFORE:]],                     # the replies before the last one
            "summary": info["summary"]}


def ledger_state(registry=None):
    """The work ledger as a dict ({"entries": [...]}), None when there is none or it cannot be read. A job Hermes's registry knows is
    settled first. trabajos.py is /usr/local/bin/trabajos in the image, the repo's copy in a checkout."""
    try:
        import importlib.machinery
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        for path in (os.environ.get("TRABAJOS_MODULE") or "/usr/local/bin/trabajos", os.path.join(here, "..", "..", "trabajos.py")):
            if os.path.isfile(path):
                spec = importlib.util.spec_from_file_location("aibridge_trabajos_h", path,
                                                              loader=importlib.machinery.SourceFileLoader("aibridge_trabajos_h", path))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.reconcile(registry)
                return mod.load()
    except Exception as exc:
        logger.warning("aibridge-handoff: the work ledger could not be read: %r", exc)
    return None


def work_items(ledger, now):
    """The ledger entries worth a line, running first, then the queue in order, then what finished in the last 24 h (newest first)."""
    es = (ledger or {}).get("entries") or []
    run = [e for e in es if e.get("state") == "corriendo"]
    pend = sorted((e for e in es if e.get("state") == "pendiente"), key=lambda e: e.get("order") or 0)
    stopped_at = (ledger or {}).get("stopped_at")
    if isinstance(stopped_at, int):                  # queued before the person's /jobs stop: on hold until they say so
        pend = [dict(e, _held=stopped_at) if (e.get("created") or 0) <= stopped_at else e for e in pend]
    done = sorted((e for e in es if e.get("state") in ("listo", "fallo", "cortado", "cancelado") and now - (e.get("ended") or 0) <= 86400),
                  key=lambda e: -(e.get("ended") or 0))
    return (run + pend + done)[:WORK_ITEMS]


GENERIC = {"clip", "video", "image", "imagen", "audio", "job", "trabajo", "the", "una", "uno", "los", "las", "del", "con", "para"}
CONFIRM_WINDOW_S = 120          # a job started this soon after the sentence is what it promised


def unconfirmed(announced, ledger):
    """Announcements nothing followed: no ledger entry started or queued within two minutes after the sentence, and none made later
    that carries one of its distinctive words (the label "alfa" in "lanzo alfa")."""
    es = (ledger or {}).get("entries") or []
    out = []
    for sent, ts in announced:
        words = set(re.findall(r"[a-z0-9]{2,}", (sent or "").lower())) - GENERIC
        followed = False
        for e in es:
            made = max(e.get("started") or 0, e.get("created") or 0)
            if made < (ts or 0) - 2:
                continue
            labels = set(re.findall(r"[a-z0-9]{2,}", str(e.get("label") or "").lower())) - GENERIC
            if made <= (ts or 0) + CONFIRM_WINDOW_S or (labels & words):
                followed = True
                break
        if not followed:
            out.append(sent)
    return out


def flat(text):
    """Text from outside that is put inside quotes or backticks: neither can end the span early and forge the fields after it."""
    return (text or "").replace('"', "'").replace("`", "'")


def work_lines(items, announced, safe):
    """The text of the work section: every item in full detail (labels, reasons, paths and commands are text from outside: each piece
    goes through the scanner by itself and a flagged one is left out, and a quote or backtick in it cannot close the span it is in),
    then the announcements nobody confirmed."""
    lines = []
    for e in items:
        st = e.get("state")
        label = flat(safe(clean(e.get("label"), 80, names=True))) or "(label left out)"
        bits = [f"{e.get('id')} \"{label}\" – {st}"]
        if e.get("started"):
            bits.append(f"started {utc(e['started'])}")
        if e.get("ended"):
            bits.append(f"ended {utc(e['ended'])}")
        if e.get("hermes_proc"):
            bits.append(f"process id {flat(clean(e['hermes_proc'], 30))}")
        if st in ("listo", "fallo") and e.get("exit_code") is not None:
            bits.append(f"exit code {e['exit_code']}")
        if st == "listo" and e.get("exit_code") is None and e.get("hermes_proc"):
            bits.append("exit status unknown")
        if st == "cortado":
            bits.append("stopped by the person (/jobs stop); do not relaunch unless they ask" if e.get("stopped")
                        else "the process died without finishing")
        if e.get("_held"):
            bits.append(f"ON HOLD: the person stopped work at {utc(e['_held'])}; do not start it without asking them")
        lines.append("- " + "; ".join(bits))
        for o in (e.get("outputs") or [])[:4]:
            o = flat(safe(clean(o, 200, names=True)))
            if o:
                lines.append(f"  output: {o}")
        reason = flat(safe(clean(e.get("reason"), 200))) if e.get("reason") and st in ("fallo", "cortado") else ""
        if reason:
            lines.append(f"  reason: {reason}")
        if st == "pendiente":
            cmd = safe(clean(e.get("full") or e.get("command"), 600, names=True)).replace("`", "'")     # quotes stay: this is the command to run
            lines.append(f"  queued, position {e.get('order')}; the exact command: `{cmd}`" if cmd else f"  queued, position {e.get('order')}")
    ann = [a for a in (safe(a) for a in announced) if a]
    if ann:
        lines.append("Announced but not confirmed (the assistant said it would act, and no tool call or ledger entry followed; "
                     "do not count these as started):")
        lines += [f"- {a}" for a in ann]
    return lines


def cap_lines(lines, cap):
    """The lines that fit in `cap` characters, whole lines only."""
    out, size = [], 0
    for ln in lines:
        if size + len(ln) + 1 > cap:
            break
        out.append(ln)
        size += len(ln) + 1
    return out


def render(entries, jobs, now, scan=None, work=None, announced=None):
    """The text of .hermes.md. `scan(text, kind)` returns True when Hermes's injection scanner would block `text`;
    kind is "person" (the person's own words) or "other" (anything that came from the model, the web or a tool).
    `work`: ledger entries; `announced`: sentences the assistant promised that nothing confirmed."""
    def safe(text, kind="other"):
        return "" if (text and scan and scan(text, kind)) else text

    head = [HEADER]
    sections = []                                   # (lines, cap), newest conversation last to be dropped
    wl = work_lines(work or [], announced or [], safe)
    if wl:
        sections.append(["## Work state when the person typed /new (the ledger: `trabajos lista --todo`; this is the record, not the chat)"]
                        + cap_lines(wl, WORK_CAP) + [""])
    if jobs:
        lines = ["## Background jobs the stack held when the person typed /new (check with the `process` tool)"]
        for j in jobs:
            state = (f"RUNNING since {utc(j['started'])}" if j["running"]
                     else f"ended {utc(j['ended'])} (exit code {j['exit_code']})")
            keep = " – set to survive /new" if j["persist"] else ""
            command, tail = safe(j["command"]), safe(j["tail"])
            lines.append(f"- {'`' + command + '`' if command else '(command left out)'} – process id {j['id']} – {state}{keep}" +
                         (f"\n  last output: {tail}" if tail else ""))
        sections.append(lines + [""])
    convs = []
    for n, e in enumerate(entries):
        lines = [f"## Conversation that ended {utc(e['ended'])} ({e['requests']} requests)" + ("" if n else " – the latest")]
        # a piece the scanner refuses leaves nothing behind, not even its label
        pieces = ([("It started with", safe(e["first"], "person"))] if e["first"] else []) + \
            [("Later the person asked", safe(r, "person")) for r in (e["last"][-3:] if n else e["last"])] + \
            ([("Before that you said", safe(r)) for r in (e.get("before") or [])] if not n else []) + \
            ([("Your last reply was", safe(e["reply"]))] if e["reply"] else []) + \
            ([("Summary kept by Hermes", safe(e["summary"]))] if e["summary"] and not n else [])
        lines += [f"- {label}: {text}" for label, text in pieces if text]
        convs.append(cap_lines(lines, CONV_CAP) + [""])
    sections += convs
    text = "\n".join(head + [ln for sec in sections for ln in sec]).rstrip() + "\n"
    while len(text) > TOTAL_CAP and len(sections) > 1:   # the oldest conversation goes first, then the next oldest
        sections.pop()
        text = "\n".join(head + [ln for sec in sections for ln in sec]).rstrip() + "\n"
    return text if len(text) <= TOTAL_CAP else text[:TOTAL_CAP].rsplit("\n", 1)[0] + "\n"


def atomic_write(path, text):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".hermes-md-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update(workdir, db_path, sid, registry, now=None, scan=None, ledger=False):
    """Read the session that ended, fold it into the store, rewrite the notes. Returns what it did, for the log.
    `ledger`: the work ledger as a dict (None = none); the default reads it from trabajos.py."""
    now = int(now or time.time())
    store_path, out_path = os.path.join(workdir, STORE_NAME), os.path.join(workdir, OUT_NAME)
    try:
        store = json.load(open(store_path, encoding="utf-8"))
        entries = [e for e in store.get("entries", []) if now - e.get("ended", 0) < MAX_AGE_S]
        carried = [(a[0], a[1]) for a in store.get("announced", []) if isinstance(a, list) and len(a) == 2 and now - (a[1] or 0) < 86400]
    except (OSError, ValueError, AttributeError, TypeError, IndexError):
        entries, carried = [], []
    info = read_session(db_path, sid)
    if info["count"] >= 2:
        entries = ([make_entry(info, sid, now)] + [e for e in entries if e.get("sid") != sid])[:MAX_ENTRIES]
        announced = list(info["announced"])
        did = f"saved a conversation of {info['count']} requests"
    else:                                          # a second /new in an empty conversation must not lose what the first one saw
        announced = list(dict.fromkeys(carried + [tuple(a) for a in info["announced"]]))[-ANNOUNCE_KEEP:]
        did = f"conversation of {info['count']} request(s) too short to replace the notes"
    jobs = jobs_from(registry, now) if registry is not None else []
    if ledger is False:
        ledger = ledger_state(registry)
    items = work_items(ledger, now)
    ann = unconfirmed(announced, ledger)
    atomic_write(store_path, json.dumps({"entries": entries, "announced": [list(a) for a in announced]}, ensure_ascii=False))
    if not entries and not jobs and not items and not ann:
        if os.path.exists(out_path):
            os.unlink(out_path)
        return did + "; nothing to carry over"
    text = render(entries, jobs, now, scan, work=items, announced=ann)
    if scan and scan(text, "person"):              # a piece slipped through the piece-by-piece check
        text = render(entries, jobs, now, lambda t, kind="other": kind != "person", work=items, announced=ann)      # the person's own words only
        if scan(text, "person"):
            if os.path.exists(out_path):           # never leave the notes of an older conversation as if they were current
                os.unlink(out_path)
            logger.warning("aibridge-handoff: the notes trip Hermes's injection scanner even with the person's words only; removed")
            return did + "; blocked by the scanner, old notes removed"
        did += "; the model's own text left out (scanner)"
    atomic_write(out_path, text)
    return f"{did}; {len(entries)} conversation(s), {len(jobs)} job(s), {len(items)} ledger item(s), {len(text)} chars"


# ------------------------------------------------------------------------------------------------------------ hook
def _scanner():
    try:
        from agent.prompt_builder import _scan_for_threats
        return lambda text, kind="other": bool(_scan_for_threats(text, scope="context"))
    except Exception as exc:                       # without the scanner the notes carry the person's words only
        logger.warning("aibridge-handoff: Hermes's scanner is not importable (%r); summary, reply and job output left out", exc)
        return lambda text, kind="other": kind != "person"


def on_session_finalize(session_id=None, platform=None, reason=None, **kwargs):
    if reason != "new_session" or not session_id or (platform or "") in SKIP_PLATFORMS:
        return
    try:
        home = os.environ.get("HERMES_HOME") or "/root/.hermes"
        try:
            from tools.process_registry import process_registry as registry
        except Exception:
            registry = None
        done = update(os.environ.get("HANDOFF_DIR", "/workdir"), os.path.join(home, "state.db"), session_id, registry,
                      scan=_scanner())
        logger.info("aibridge-handoff: %s", done)
    except Exception as exc:                       # /new must work whatever happens here
        logger.warning("aibridge-handoff: notes not written: %r", exc)


def register(ctx):
    ctx.register_hook("on_session_finalize", on_session_finalize)
