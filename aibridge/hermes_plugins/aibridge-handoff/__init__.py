"""Notes for the next conversation, written when the person types /new (2026-11-04).

Why: after /new a conversation starts from nothing. On 2026-11-04 hernik's new session did not know about the long
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
  - up to 3 conversations, newest first, none older than 7 days.
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
TOTAL_CAP = 7000
SKIP_PLATFORMS = {"", "api_server", "cron", "webhook"}

STAMP = re.compile(r"^\s*\[(?:[A-Za-z]{3} )?\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?: [+-]\d\d(?::?\d\d)?)?\]\s*")
REPLY_TAG = re.compile(r"^\s*\[reply in [^\]\n]{1,40}\]\s*")
NOT_A_REQUEST = re.compile(r"^\[(?:SYSTEM|System|IMPORTANT|Background|Note|CONTEXT|Your request was not|This turn did not|"
                           r"Operation interrupted|The user shared a location)", re.I)
KEY = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}|thk_[A-Za-z0-9_-]{16,}"
                 r"|hf_[A-Za-z0-9]{20,}|[A-Za-z0-9_-]{40,})")
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
def clean(text, limit):
    """One line of text for the notes: key-shaped strings masked, whitespace folded, cut to `limit`."""
    text = KEY.sub("[hidden]", text or "")
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
    """The session and its ancestors (a compaction or a /branch starts a child session)."""
    out = []
    while sid and sid not in out and len(out) < hops:
        out.append(sid)
        row = db.execute("SELECT parent_session_id FROM sessions WHERE id=?", (sid,)).fetchone()
        sid = row[0] if row else None
    return out


def read_session(db_path, sid):
    """{'requests': [...], 'last_reply': str, 'summary': str, 'count': n} for the session `sid` (and its ancestors)."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
    try:
        ids = lineage(db, sid)
        marks = ",".join("?" * len(ids))
        rows = db.execute(f"SELECT role, content, timestamp FROM messages WHERE session_id IN ({marks}) "
                          "ORDER BY timestamp, id", ids).fetchall()
    finally:
        db.close()
    requests, seen, summary, last_reply = [], set(), "", ""
    for role, content, ts in rows:
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
            last_reply = content
    return {"requests": requests, "last_reply": last_reply, "summary": summary, "count": len(requests)}


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
            "reply": clean(info["last_reply"], 500), "summary": info["summary"]}


def render(entries, jobs, now, scan=None):
    """The text of .hermes.md. `scan(text, kind)` returns True when Hermes's injection scanner would block `text`;
    kind is "person" (the person's own words) or "other" (anything that came from the model, the web or a tool)."""
    def safe(text, kind="other"):
        return "" if (text and scan and scan(text, kind)) else text

    lines = [HEADER]
    if jobs:
        lines.append("## Background jobs the stack held when the person typed /new (check with the `process` tool)")
        for j in jobs:
            state = (f"RUNNING since {utc(j['started'])}" if j["running"]
                     else f"ended {utc(j['ended'])} (exit code {j['exit_code']})")
            keep = " – set to survive /new" if j["persist"] else ""
            command, tail = safe(j["command"]), safe(j["tail"])
            lines.append(f"- {'`' + command + '`' if command else '(command left out)'} – process id {j['id']} – {state}{keep}" +
                         (f"\n  last output: {tail}" if tail else ""))
        lines.append("")
    for n, e in enumerate(entries):
        lines.append(f"## Conversation that ended {utc(e['ended'])} ({e['requests']} requests)" +
                     ("" if n else " – the latest"))
        # a piece the scanner refuses leaves nothing behind, not even its label
        for label, text in ([("It started with", safe(e["first"], "person"))] if e["first"] else []) + \
                [("Later the person asked", safe(r, "person")) for r in (e["last"][-3:] if n else e["last"])] + \
                ([("Your last reply was", safe(e["reply"]))] if e["reply"] and not n else []) + \
                ([("Summary kept by Hermes", safe(e["summary"]))] if e["summary"] and not n else []):
            if text:
                lines.append(f"- {label}: {text}")
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
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


def update(workdir, db_path, sid, registry, now=None, scan=None):
    """Read the session that ended, fold it into the store, rewrite the notes. Returns what it did, for the log."""
    now = int(now or time.time())
    store_path, out_path = os.path.join(workdir, STORE_NAME), os.path.join(workdir, OUT_NAME)
    try:
        store = json.load(open(store_path, encoding="utf-8"))
        entries = [e for e in store.get("entries", []) if now - e.get("ended", 0) < MAX_AGE_S]
    except (OSError, ValueError, AttributeError):
        entries = []
    info = read_session(db_path, sid)
    if info["count"] >= 2:
        entries = ([make_entry(info, sid, now)] + [e for e in entries if e.get("sid") != sid])[:MAX_ENTRIES]
        did = f"saved a conversation of {info['count']} requests"
    else:
        did = f"conversation of {info['count']} request(s) too short to replace the notes"
    jobs = jobs_from(registry, now) if registry is not None else []
    atomic_write(store_path, json.dumps({"entries": entries}, ensure_ascii=False))
    if not entries and not jobs:
        if os.path.exists(out_path):
            os.unlink(out_path)
        return did + "; nothing to carry over"
    text = render(entries, jobs, now, scan)
    if scan and scan(text, "person"):              # a piece slipped through the piece-by-piece check
        text = render(entries, jobs, now, lambda t, kind="other": kind != "person")      # the person's own words only
        if scan(text, "person"):
            if os.path.exists(out_path):           # never leave the notes of an older conversation as if they were current
                os.unlink(out_path)
            logger.warning("aibridge-handoff: the notes trip Hermes's injection scanner even with the person's words only; removed")
            return did + "; blocked by the scanner, old notes removed"
        did += "; the model's own text left out (scanner)"
    atomic_write(out_path, text)
    return f"{did}; {len(entries)} conversation(s), {len(jobs)} job(s), {len(text)} chars"


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
