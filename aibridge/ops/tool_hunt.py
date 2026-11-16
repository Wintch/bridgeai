#!/usr/bin/env python3
"""Tool-use review of a Hermes state.db copy: where a bot hunted for tools, looped, or went quiet. Tables only, no chat text.

  ops/tool_hunt.py PATH/state.db [--since HOURS] [--session ID] [--json] [--tz H] [--silent-calls N] [--silent-secs T]

Works on a COPY of state.db (never the live file). It is the second half of what ops/chat_review.py shows: chat_review tells
what was said and the shape of each turn; this one reads the tool rounds in order and flags the patterns that cost a person
time: a long run of "which / ls / --help / pip show" before the first real action, the same failing call repeated, pip/npm/apt
loops, long stretches of tool calls with no word to the person, mid-turn messages that waited for an answer, and the prompt
growing from call to call.

Privacy by construction: the SELECT names its columns (id, session_id, role, content, tool_name, tool_calls, timestamp,
finish_reason, token_count); reasoning, reasoning_content, reasoning_details and codex_reasoning_items are never selected, and
an SQLite authorizer refuses to read them even if a later edit tried. The output holds tool names, the first word of a terminal
command (plus the sub-command for pip/npm/apt/git/docker/gateway), an 80-character masked command preview only in the findings,
failure categories, counts and seconds. No message text, no tool result text. A person's own words are used only to tell which
row starts a turn and are never printed. Even so, keep the output outside the repo (it names tools and commands of a real
session), mode 600; it is meant to be pasted into a review.

--since is counted back from the newest row in the copy (a copy is usually older than now). Times are UTC unless --tz is given.
A turn runs from a message of the person to the next one (mid-turn messages, which Hermes wraps in an out-of-band marker, and
compaction notes do not start a turn). Rows that a compaction stored again under a new session at the same instant are
dropped, as chat_review does. Results are paired to calls by order and tool name (tool_call_id is not selected).
"""
import argparse, collections, datetime, json, os, re, sqlite3, sys, urllib.parse

COLUMNS = ("id", "session_id", "role", "content", "tool_name", "tool_calls", "timestamp", "finish_reason", "token_count")
NEVER = ("reasoning", "reasoning_content", "reasoning_details", "codex_reasoning_items")

OOB_MARK = "[OUT-OF-BAND USER MESSAGE"      # Hermes's wrapper for a message the person sent while a turn ran
COMPACTION = "[CONTEXT COMPACTION"
SEEN_PREFIX = re.compile(r"^\[\w{3} \d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d\d(?::?\d\d)?\] (?:\[reply in \w+\] )?")
KEY = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}|thk_[A-Za-z0-9_-]{16,}"
                 r"|[A-Za-z0-9_-]{40,})")

TERMINAL_TOOLS = {"terminal", "bash", "shell", "execute_command", "run_command", "exec", "run_shell"}
VERB_FIRST = {"pip", "pip3", "npm", "pnpm", "yarn", "apt", "apt-get", "git", "docker", "gateway", "uv", "cargo"}
INSTALL = re.compile(r"^(?:sudo\s+)?(?:(?:python3?|\S*python3?)\s+-m\s+)?(pip3?|uv\s+pip|npm|pnpm|yarn|apt-get|apt|cargo|gem)\s+"
                     r"(install|add|i)\b(.*)$")
CAPABILITY_Q = re.compile(r"\b(api|apis|librar\w+|package|tool|tools|how to|install|alternatives?|open.?source|github|pypi|"
                          r"cli|sdk|free|model|models|identify|recognition)\b", re.I)
HELPISH = re.compile(r"(^|\s)(--help|-h|help|--version|-V)(\s|$)")
BIN_DIRS = re.compile(r"(/s?bin\b|/usr/(local/)?(s?bin|lib|share)\b|/opt\b|\.local/(bin|lib)\b|/root/\.hermes)")
PKG_QUERY = re.compile(r"^(?:python3?\s+-m\s+)?(?:pip3?|uv\s+pip)\s+(show|list|freeze|index|check)\b|^(?:npm|pnpm|yarn)\s+(ls|list|view|info)\b"
                       r"|^dpkg\s+-[ls]\b|^apt(?:-get|-cache)?\s+(list|search|show|policy|madison)\b|^pip3?\s+download\b.*--dry")
STRICT_ERR = [
    ("traceback", re.compile(r"Traceback \(most recent call last\)")),
    ("not-found", re.compile(r"command not found|No such file or directory|ModuleNotFoundError|No module named|not recognized")),
    ("denied", re.compile(r"Permission denied|Operation not permitted|BLOCKED")),
    ("timeout", re.compile(r"timed? ?out|Timeout", re.I)),
    ("usage", re.compile(r"^usage: |error: (unrecognized|the following|argument|invalid|unknown)", re.I | re.M)),
    ("error", re.compile(r"^(?:Error|ERROR|Fatal|FATAL|E:)\b|^error:", re.M)),
]


# ---------------------------------------------------------------------------------------------------------------- reading

def _deny_reasoning(action, arg1, arg2, dbname, source):
    if action == sqlite3.SQLITE_READ and arg2 in NEVER:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def open_db(path):
    """Read-only handle on a COPY of state.db. The authorizer makes reading a reasoning column an error, not a choice."""
    uri = "file:" + urllib.parse.quote(os.path.abspath(path)) + "?mode=ro"
    try:
        db = sqlite3.connect(uri, uri=True, timeout=5)
        db.execute("select 1 from sqlite_master limit 1")
    except sqlite3.OperationalError:
        db = sqlite3.connect(uri + "&immutable=1", uri=True, timeout=5)      # a copy with an unreadable -wal/-shm side
    db.set_authorizer(_deny_reasoning)
    return db


def load_rows(db, since_hours=None, session=None):
    have = [r[1] for r in db.execute("pragma table_info(messages)")]
    cols = [c for c in COLUMNS if c in have]
    missing = [c for c in ("session_id", "role", "timestamp") if c not in cols]
    if missing:
        raise SystemExit(f"messages table lacks {', '.join(missing)}: not a Hermes state.db?")
    sql = "select " + ", ".join(cols) + " from messages order by timestamp, id"
    rows = [dict(zip(cols, r)) for r in db.execute(sql)]
    for r in rows:
        for c in COLUMNS:
            r.setdefault(c, None)
    if since_hours is not None and rows:
        cut = max(r["timestamp"] or 0 for r in rows) - since_hours * 3600
        rows = [r for r in rows if (r["timestamp"] or 0) >= cut]
    if session:
        rows = [r for r in rows if session in (r["session_id"] or "")]
    return rows


# --------------------------------------------------------------------------------------------------------------- parsing

def parse_calls(tc):
    """[{name, args(dict), raw}] from an assistant row's tool_calls JSON. Unreadable input gives one '?' call."""
    if not tc:
        return []
    try:
        data = json.loads(tc) if isinstance(tc, str) else tc
    except ValueError:
        return [{"name": "?", "args": {}, "raw": ""}]
    out = []
    for x in data if isinstance(data, list) else [data]:
        fn = (x.get("function") if isinstance(x, dict) else None) or x or {}
        name = fn.get("name") or "?"
        raw = fn.get("arguments", fn.get("args", ""))
        args = raw
        if isinstance(raw, str):
            try:
                args = json.loads(raw) if raw.strip() else {}
            except ValueError:
                args = {"_raw": raw}
        out.append({"name": name, "args": args if isinstance(args, dict) else {"_raw": args},
                    "raw": raw if isinstance(raw, str) else json.dumps(raw, sort_keys=True)})
    return out


def command_of(call):
    a = call["args"]
    c = a.get("command") or a.get("cmd") or a.get("script")
    if isinstance(c, list):
        c = " ".join(map(str, c))
    if isinstance(c, str) and (call["name"] in TERMINAL_TOOLS or "command" in a or "cmd" in a):
        return c
    return None


def segments(cmd):
    """Pipeline heads of a command line: 'a && b | c; d' gives ['a', 'b', 'd'] (what each stage starts with)."""
    out = []
    for seg in re.split(r"&&|\|\||;|\n", cmd):
        seg = seg.split("|")[0].strip()
        seg = re.sub(r"^(?:(?:\w+=\S+|sudo|env|time|nohup)\s+)+", "", seg)
        if seg and not seg.startswith("#"):
            out.append(seg)
    return out


def preview(call):
    """What the call is, in few words: tool name, or tool:first-word[ verb] for a terminal command."""
    cmd = command_of(call)
    if cmd is None:
        return call["name"]
    segs = segments(cmd)
    if not segs:
        return call["name"] + ":"
    words = segs[0].split()
    w = os.path.basename(words[0]) if words else ""
    if w in VERB_FIRST and len(words) > 1 and not words[1].startswith("-"):
        w += " " + words[1]
    return f"{call['name']}:{KEY.sub('[x]', w)[:40]}"


def cmd_preview(call):
    cmd = command_of(call)
    if cmd is None:
        return call["name"]
    one = " ".join(cmd.split())
    return KEY.sub("[x]", one)[:80]


def result_failure(content):
    """None when the result looks fine, else a short category: 'exit N', 'traceback', 'not-found', ..."""
    text = content if isinstance(content, str) else ""
    head = text
    try:
        d = json.loads(text)
    except ValueError:
        d = None
    if isinstance(d, dict):
        for k in ("exit_code", "returncode", "exitCode", "exit_status"):
            v = d.get(k)
            if isinstance(v, (int, float)) and v != 0:
                return f"exit {int(v)}"
        if d.get("success") is False or d.get("ok") is False:
            return "error"
        if d.get("error"):
            return "error"
        if any(isinstance(d.get(k), (int, float)) for k in ("exit_code", "returncode", "exitCode")):
            return None                                   # a clean exit code outranks words in the output
        head = " ".join(str(d.get(k) or "") for k in ("output", "stderr", "message", "result"))
    head = head[:600]
    for label, rx in STRICT_ERR:
        if rx.search(head):
            return label
    return None


def discovery_kind(call):
    """A label when the call only looks for a tool or a fact about the environment, else None."""
    n = call["name"]
    if n in ("skills_list", "skill_view", "skills_search"):
        return "skills"
    if n in ("web_search", "search_web", "websearch"):
        q = str(call["args"].get("query") or call["args"].get("q") or "")
        return "web-capability" if CAPABILITY_Q.search(q) else None
    cmd = command_of(call)
    if cmd is None:
        return None
    segs = segments(cmd)
    if not segs:
        return None
    kinds = []
    for s in segs:
        words = s.split()
        w0 = os.path.basename(words[0]) if words else ""
        if w0 in ("which", "whereis", "hash") or s.startswith("command -v") or (w0 == "type" and len(words) > 1):
            kinds.append("which")
        elif w0 == "ls" and BIN_DIRS.search(s):
            kinds.append("ls-bin")
        elif w0 == "find" and re.search(r"\s(/usr|/opt|/|~)(\s|/|$)", s):
            kinds.append("find-usr")
        elif PKG_QUERY.search(s):
            kinds.append("pkg-query")
        elif HELPISH.search(s) and w0 not in ("echo", "cat", "grep"):
            kinds.append("help")
        else:
            return None
    return kinds[0]


def installs_in(call):
    cmd = command_of(call)
    out = []
    for s in segments(cmd) if cmd else []:
        m = INSTALL.match(s)
        if m:
            mgr = re.sub(r"\s+", " ", m.group(1)).replace("pip3", "pip")
            pk = sorted(t for t in m.group(3).split() if not t.startswith("-"))
            out.append((mgr, " ".join(pk)))
    return out


# --------------------------------------------------------------------------------------------------------------- analysis

def dedupe(rows):
    """Drop rows a compaction copied into a new session at the same instant (as chat_review does). Returns rows, oob replays."""
    seen, out, replays = {}, [], 0
    for r in rows:
        c = r["content"] if isinstance(r["content"], str) else ""
        sig = (r["role"], SEEN_PREFIX.sub("", c, count=1), r["tool_calls"], r["tool_name"])
        ts = int(r["timestamp"] or 0)
        if sig in seen and seen[sig] == ts:
            if r["role"] == "user" and OOB_MARK in c[:200]:
                replays += 1
            continue
        seen[sig] = ts
        out.append(r)
    return out, replays


def is_oob(r):
    return r["role"] == "user" and isinstance(r["content"], str) and OOB_MARK in r["content"][:200]


def is_compaction(r):
    return isinstance(r["content"], str) and COMPACTION in r["content"][:300]


def split_turns(rows):
    """Rows of one session into turns: a turn starts at a user row that is neither a mid-turn marker nor a compaction note."""
    turns, cur = [], None
    for r in rows:
        if r["role"] == "user" and not is_oob(r) and not is_compaction(r):
            cur = {"rows": [r]}
            turns.append(cur)
        elif cur is None:
            cur = {"rows": [r], "lead": True}              # rows before any person message (a continued session)
            turns.append(cur)
        else:
            cur["rows"].append(r)
    return turns


def analyze_turn(rows, silent_calls, silent_secs, est_base):
    t0 = rows[0]["timestamp"] or 0
    calls, pending = [], []                                 # calls: dicts in order; pending: not yet answered
    anchor, anchor_calls = t0, 0                            # last word to the person (or the turn start)
    last_ts = t0
    stretches, oobs = [], []
    ctx_tokens, chars, compactions, odd_finish = [], est_base, 0, collections.Counter()
    texts = 0

    def close_stretch(end_ts):
        secs = max(0.0, end_ts - anchor)
        if anchor_calls >= silent_calls or (anchor_calls >= 1 and secs >= silent_secs):
            stretches.append({"calls": anchor_calls, "secs": round(secs), "from": round(anchor - t0)})

    def settle_oobs(ts):
        for o in oobs:
            if o["gap_secs"] is None:
                o["gap_secs"] = round(ts - o["ts"])
                o["gap_calls"] = len(calls) - o["calls_at"]

    for r in rows:
        ts = r["timestamp"] or last_ts
        chars += len(r["content"] or "") + len(r["tool_calls"] or "")
        if r["token_count"]:
            ctx_tokens.append(int(r["token_count"]))
        if is_compaction(r):
            compactions += 1
            last_ts = ts
            continue
        if r["finish_reason"] and r["finish_reason"] not in ("stop", "tool_calls", "tool_use", "end_turn"):
            odd_finish[str(r["finish_reason"])[:20]] += 1
        if is_oob(r):
            oobs.append({"ts": ts, "calls_at": len(calls), "gap_secs": None, "gap_calls": None, "chars": len(r["content"])})
        elif r["role"] == "assistant":
            said = bool((r["content"] or "").strip())
            if said:
                texts += 1
                close_stretch(ts)
                settle_oobs(ts)
                anchor, anchor_calls = ts, 0
            for c in parse_calls(r["tool_calls"]):
                c.update(ts=ts, result_ts=None, fail=None, idx=len(calls) + 1)
                calls.append(c)
                pending.append(c)
                anchor_calls += 1
        elif r["role"] == "tool":
            hit = next((p for p in pending if p["name"] == r["tool_name"]), None) or (pending[0] if pending else None)
            if hit:
                pending.remove(hit)
                hit["result_ts"] = ts
                hit["fail"] = result_failure(r["content"])
        last_ts = ts
    close_stretch(last_ts)
    for o in oobs:
        if o["gap_secs"] is None:                           # never followed by assistant text in this turn
            o["gap_calls"] = len(calls) - o["calls_at"]
            o["gap_secs"] = round(last_ts - o["ts"])
            o["answered"] = False
        else:
            o["answered"] = True

    # failures and identical retries (same tool + same arguments as an earlier call that failed)
    sig_fail, retries, sig_n = collections.Counter(), [], collections.Counter()
    failed_sigs = set()
    for c in calls:
        sig = (c["name"], json.dumps(c["args"], sort_keys=True, default=str))
        c["sig"] = sig
        sig_n[sig] += 1
        if sig in failed_sigs:
            retries.append(c)
        if c["fail"]:
            failed_sigs.add(sig)
            sig_fail[sig] += 1
    worst = []
    for sig, n in sig_fail.items():
        if sig_n[sig] >= 2:
            first = next(c for c in calls if c["sig"] == sig)
            worst.append({"calls": sig_n[sig], "failed": n, "what": cmd_preview(first)})
    worst.sort(key=lambda w: -w["calls"])

    # discovery before the first action
    kinds = [discovery_kind(c) for c in calls]
    lead = 0
    for k in kinds:
        if k is None:
            break
        lead += 1
    disc = collections.Counter(k for k in kinds if k)

    # installs
    inst = collections.Counter()
    inst_sets = collections.defaultdict(set)
    inst_failed = 0
    for c in calls:
        for mgr, pk in installs_in(c):
            inst[mgr] += 1
            inst_sets[mgr].add(pk)
            inst_failed += 1 if c["fail"] else 0

    dur = [c["result_ts"] - c["ts"] for c in calls if c["result_ts"] is not None and c["result_ts"] >= c["ts"]]
    return {
        "start": t0, "secs": round(last_ts - t0), "texts": texts, "calls": len(calls),
        "failed": sum(1 for c in calls if c["fail"]),
        "fail_kinds": dict(collections.Counter(c["fail"] for c in calls if c["fail"])),
        "unanswered_calls": len(pending),
        "retries": len(retries), "worst_repeats": worst[:5],
        "discovery_lead": lead, "discovery_total": sum(disc.values()), "discovery_kinds": dict(disc),
        "installs": dict(inst), "install_sets": {k: len(v) for k, v in inst_sets.items()}, "install_failed": inst_failed,
        "silent": stretches, "silent_max_calls": max([s["calls"] for s in stretches], default=0),
        "silent_max_secs": max([s["secs"] for s in stretches], default=0),
        "oob": [{k: v for k, v in o.items() if k not in ("ts", "calls_at")} for o in oobs],
        "slowest_call_secs": round(max(dur, default=0)),
        "ctx_tokens": ctx_tokens[-1] if ctx_tokens else None, "ctx_tokens_max": max(ctx_tokens) if ctx_tokens else None,
        "ctx_est": None if ctx_tokens else round(chars / 4),
        "compactions": compactions, "odd_finish": dict(odd_finish),
        "sequence": [(c["idx"], preview(c), bool(c["fail"])) for c in calls],
        "install_loop": any(n >= 3 for n in inst.values()),
        "flagged_calls": [cmd_preview(c) for c in retries[:3]],
    }


def analyze(rows, silent_calls=10, silent_secs=90):
    rows, replays = dedupe(rows)
    by = collections.OrderedDict()
    for r in rows:
        by.setdefault(r["session_id"], []).append(r)
    sessions = []
    for sid, srows in by.items():
        srows.sort(key=lambda r: (r["timestamp"] or 0, r["id"] or 0))
        turns, base = [], 0
        for t in split_turns(srows):
            a = analyze_turn(t["rows"], silent_calls, silent_secs, base)
            base += sum(len(r["content"] or "") + len(r["tool_calls"] or "") for r in t["rows"])
            a["lead"] = bool(t.get("lead"))
            a["msg_chars"] = 0 if a["lead"] else len(t["rows"][0]["content"] or "")
            a["n"] = len([x for x in turns if not x["lead"]]) + 1
            turns.append(a)
        tok = [t["ctx_tokens"] for t in turns if t["ctx_tokens"]]
        est = [t["ctx_est"] for t in turns if t["ctx_est"]]
        s = {
            "session": sid, "start": srows[0]["timestamp"], "end": srows[-1]["timestamp"], "rows": len(srows),
            "turns": len(turns), "calls": sum(t["calls"] for t in turns), "failed": sum(t["failed"] for t in turns),
            "retries": sum(t["retries"] for t in turns), "discovery_lead_max": max([t["discovery_lead"] for t in turns], default=0),
            "discovery_total": sum(t["discovery_total"] for t in turns),
            "installs": dict(sum((collections.Counter(t["installs"]) for t in turns), collections.Counter())),
            "silent_max_calls": max([t["silent_max_calls"] for t in turns], default=0),
            "silent_max_secs": max([t["silent_max_secs"] for t in turns], default=0),
            "oob": sum(len(t["oob"]) for t in turns),
            "oob_unanswered": sum(1 for t in turns for o in t["oob"] if not o["answered"]),
            "compactions": sum(t["compactions"] for t in turns),
            "ctx_first": tok[0] if tok else None, "ctx_last": tok[-1] if tok else None,
            "ctx_max": max([t["ctx_tokens_max"] or 0 for t in turns] or [0]) or None,
            "ctx_est_last": est[-1] if not tok and est else None,
            "turn_list": turns,
        }
        sessions.append(s)
    return {"sessions": sessions, "oob_replays_skipped": replays}


# -------------------------------------------------------------------------------------------------------------- printing

def table(headers, rows):
    rows = [[str(c) for c in r] for r in rows]
    w = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    line = lambda r: "  ".join(c.ljust(w[i]) for i, c in enumerate(r)).rstrip()
    return [line(headers), line(["-" * x for x in w])] + [line(r) for r in rows]


def fmt_ctx(t):
    if t.get("ctx_tokens") is not None:
        return f"{t['ctx_tokens'] // 1000}k"
    return f"~{t['ctx_est'] // 1000}k est" if t.get("ctx_est") else "-"


def render(res, tz, silent_calls, silent_secs, max_seq=60):
    hm = lambda ts: datetime.datetime.fromtimestamp(ts, tz).strftime("%m-%d %H:%M:%S") if ts else "-"
    out = []
    ss = res["sessions"]
    out.append("== sessions (newest last)")
    out += table(["session", "start", "turns", "calls", "fail", "retry", "disc.lead", "disc", "installs", "silent max", "oob", "oob open",
                  "compact", "ctx first>last (max)"],
                 [[s["session"][-8:], hm(s["start"]), s["turns"], s["calls"], s["failed"], s["retries"], s["discovery_lead_max"],
                   s["discovery_total"], "/".join(f"{k}:{v}" for k, v in s["installs"].items()) or "-",
                   f"{s['silent_max_calls']}c/{s['silent_max_secs']}s", s["oob"], s["oob_unanswered"], s["compactions"],
                   (f"{(s['ctx_first'] or 0) // 1000}k>{(s['ctx_last'] or 0) // 1000}k ({(s['ctx_max'] or 0) // 1000}k)"
                    if s["ctx_first"] else (f"~{s['ctx_est_last'] // 1000}k est" if s["ctx_est_last"] else "-"))] for s in ss])
    if res["oob_replays_skipped"]:
        out.append(f"(mid-turn messages replayed after a compaction and skipped: {res['oob_replays_skipped']})")
    for s in ss:
        out.append(f"\n######## session ...{s['session'][-8:]}  {hm(s['start'])}  {s['rows']} rows")
        out += table(["turn", "start", "secs", "msg", "calls", "fail", "retry", "disc.lead/tot", "installs", "silent max", "oob", "ctx"],
                     [[t["n"] if not t["lead"] else "0*", hm(t["start"]), t["secs"], t["msg_chars"], t["calls"], t["failed"], t["retries"],
                       f"{t['discovery_lead']}/{t['discovery_total']}", "/".join(f"{k}:{v}" for k, v in t["installs"].items()) or "-",
                       f"{t['silent_max_calls']}c/{t['silent_max_secs']}s", len(t["oob"]), fmt_ctx(t)] for t in s["turn_list"]])
        for t in s["turn_list"]:
            notes = []
            if t["calls"]:
                seq = " ".join(f"{i}:{p}{'!' if f else ''}" for i, p, f in t["sequence"][:max_seq])
                if len(t["sequence"]) > max_seq:
                    seq += f" ...+{len(t['sequence']) - max_seq}"
                notes.append("calls (! = failed): " + seq)
            if t["fail_kinds"]:
                notes.append("failures: " + ", ".join(f"{k} x{v}" for k, v in sorted(t["fail_kinds"].items())))
            for w in t["worst_repeats"]:
                notes.append(f"identical call x{w['calls']} ({w['failed']} failed): {w['what']}")
            if t["discovery_lead"] >= 3 or t["discovery_total"] >= 5:
                notes.append(f"discovery: {t['discovery_lead']} before the first action, {t['discovery_total']} in all "
                             + ", ".join(f"{k} x{v}" for k, v in sorted(t["discovery_kinds"].items())))
            if t["install_loop"]:
                notes.append("install loop: " + ", ".join(f"{k} x{v} ({t['install_sets'].get(k, 0)} distinct)" for k, v in t["installs"].items())
                             + f", {t['install_failed']} failed")
            for st in t["silent"]:
                notes.append(f"silent: {st['calls']} calls over {st['secs']}s from +{st['from']}s with no text to the person")
            for o in t["oob"]:
                notes.append(f"mid-turn message ({o['chars']} chars): "
                             + (f"next text after {o['gap_secs']}s / {o['gap_calls']} calls" if o["answered"]
                                else f"NO text after it, {o['gap_calls']} calls / {o['gap_secs']}s to the end of the turn"))
            if t["unanswered_calls"]:
                notes.append(f"{t['unanswered_calls']} calls without a result row")
            if t["slowest_call_secs"] >= 60:
                notes.append(f"slowest call {t['slowest_call_secs']}s")
            if t["odd_finish"]:
                notes.append("finish_reason: " + ", ".join(f"{k} x{v}" for k, v in t["odd_finish"].items()))
            if t["compactions"]:
                notes.append(f"compactions in this turn: {t['compactions']}")
            if notes:
                out.append(f"  turn {t['n'] if not t['lead'] else '0*'}:")
                out += ["    " + n for n in notes]
    out.append(f"\n(thresholds: silent = {silent_calls}+ calls or {silent_secs}+ s with calls and no text; 0* = rows before the first message "
               "of the person; no message text is printed)")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tool-use review of a Hermes state.db copy (tables only, no chat text).")
    ap.add_argument("db", help="path to a COPY of state.db")
    ap.add_argument("--since", type=float, metavar="HOURS", help="only rows from the last HOURS before the newest row in the copy")
    ap.add_argument("--session", metavar="ID", help="only sessions whose id contains this text")
    ap.add_argument("--json", action="store_true", help="print the structured result as JSON")
    ap.add_argument("--tz", type=float, default=0, help="hours from UTC for the times shown (default 0)")
    ap.add_argument("--silent-calls", type=int, default=10, help="a stretch of this many tool calls with no text is flagged")
    ap.add_argument("--silent-secs", type=int, default=90, help="so is one this long (with at least one call)")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.db):
        print(f"no such file: {a.db}", file=sys.stderr)
        return 2
    db = open_db(a.db)
    try:
        rows = load_rows(db, a.since, a.session)
    finally:
        db.close()
    res = analyze(rows, a.silent_calls, a.silent_secs)
    if a.json:
        print(json.dumps(res, indent=1, sort_keys=True, default=str))
    else:
        print(render(res, datetime.timezone(datetime.timedelta(hours=a.tz)), a.silent_calls, a.silent_secs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
