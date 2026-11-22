#!/usr/bin/env python3
"""Turn a stretch of a person's Hermes conversations into something a reviewer can read in one sitting.

  ssh <docker-host> 'docker run --rm -i --entrypoint python3 -v ~/aibridge/hermes-config:/p:ro -v ~/aibridge/user1-workdir:/w:ro \
      aibridge-hermes-agent:latest - --own --hours 12 --mode text' < ops/chat_review.py > review.txt; chmod 600 review.txt

What people lived through with the bot is what it gets better from . The first explore night was 1.3 MB of raw state.db rows; read by hand it showed what no
metric did: a live location that interrupted every turn, a model that ranked first on speed and read worst. This is that
reading made repeatable. It opens state.db read-only (immutable) and:
- drops the copies Hermes makes when it compacts a conversation (the same rows again under the new session) and rows
  stored twice at the same instant, but keeps a notice that really happened again ("Your request was not processed"),
- folds runs of location pins into one line ("[17 location pins from 02:36]"),
- shows each tool round as one line (names and counts, how many results look like errors), never the results,
- cuts long messages (compaction summaries, pasted logs) and masks anything shaped like an API key,
- ends with counts: turns cut by a new message, approvals that expired, pins answered with a template, and tool results that
  failed, by cause (a terminal result counts by its exit code; a log that says "0 errors" is not a failure).

--mode text prints what was said: only on the operator's own stack (--own) or when the person chose `/compartir todo`.
--mode structure (the default) prints the counts and the shape of each turn, no text at all: the careful-inspection rule
for everyone else. The person's choice (/compartir, opinion.py) is read from their /workdir, mounted read-only at /w
(`-v ~/aibridge/stacks/NAME/workdir:/w:ro`; the main stack's is ~/aibridge/user1-workdir); `/compartir nada` refuses even the structure. The output is private either way: keep it outside the repo, mode 600.
"""
import argparse, collections, datetime, json, re, sqlite3, sys, time

KEY = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}|thk_[A-Za-z0-9_-]{16,}"
                 r"|[A-Za-z0-9_-]{40,})")
PIN = "[The user shared a location pin.]"
SEEN_PREFIX = re.compile(r"^\[\w{3} \d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d\d(?::?\d\d)?\] (?:\[reply in \w+\] )?")
CUT = {"Your request was not processed": "no procesado", "This turn did not complete": "no completado",
       "Operation interrupted": "interrumpido"}
ERRISH = re.compile(r"error|failed|timed? ?out|denied|not found|Traceback|BLOCKED", re.I)
# A log line that says there were no errors ("0 errors", "errors: 0") is not an error: subs-fetch prints one at the end of every
# healthy run, and the plain word match counted each as a failure (40-70 % "errors" on every stack).
ZERO_ERRORS = re.compile(r"\b(?:0|no|zero)\s+(?:errors?|failed|failures?)\b|\berrors?:\s*0\b|\bwithout errors?\b", re.I)
# The cause, by words only: the review never shows the text, but "denied" against "timed out" tells what to fix.
CAUSES = (("timeout", re.compile(r"timed? ?out", re.I)),
          ("rate limit", re.compile(r"rate[- ]?limit|\b429\b|too many requests", re.I)),
          ("denied", re.compile(r"denied|BLOCKED|not permitted|forbidden|refused", re.I)),
          ("not found", re.compile(r"not found|no such file|does not exist", re.I)),
          ("traceback", re.compile(r"Traceback")))


def cause_of(text):
    return next((name for name, rx in CAUSES if rx.search(text)), "other")


def error_kind(content):
    """None for a tool result that looks fine, else a short cause. A terminal result is JSON with an exit code and that decides:
    0 or none (a job started in the background) is fine whatever the output says. Anything else falls back to the words."""
    try:
        d = json.loads(content)
    except ValueError:
        d = None
    if isinstance(d, dict) and ("exit_code" in d or "error" in d):
        code, err = d.get("exit_code"), d.get("error")
        if not err and (code is None or code == 0):
            return None
        return cause_of(f"{err or ''} {d.get('output') or ''}"[:600]) if (err or code) else None
    head = ZERO_ERRORS.sub("", content[:600])
    return cause_of(head) if ERRISH.search(head) else None
TEMPLATE = re.compile(r"(find|найти|искать|увидеть|buscar).{0,60}(restaurant|кафе|ресторан|café|cafe)", re.I)


def sharing(workdir):
    """What the person lets the administrator look at (/compartir, opinion.py): "nada", "uso" (the default) or "todo"."""
    try:
        v = json.load(open(f"{workdir}/.compartir.json")).get("level")
    except (OSError, ValueError, AttributeError):
        return "uso"
    return v if v in ("nada", "uso", "todo") else "uso"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--db", default="/p/state.db")
    ap.add_argument("--mode", choices=("structure", "text"), default="structure")
    ap.add_argument("--cut", type=int, default=1500, help="longest message shown in text mode")
    ap.add_argument("--tz", type=float, default=-3, help="hours from UTC for the times shown")
    ap.add_argument("--workdir", default="/w", help="the person's /workdir, mounted read-only: where their sharing choice lives")
    ap.add_argument("--own", action="store_true", help="the operator's own stack: text mode without the person's consent file")
    a = ap.parse_args()
    level = sharing(a.workdir)
    if level == "nada":
        print("The person chose /compartir nada: their use is not reviewed (neither structure nor text).")
        return 0
    if a.mode == "text" and level != "todo" and not a.own:
        print(f"The person shares «{level}»: structure only. To read the text they must choose /compartir todo (or --own on your own stack).")
        return 0
    tz = datetime.timezone(datetime.timedelta(hours=a.tz))
    hm = lambda t: datetime.datetime.fromtimestamp(t, tz).strftime("%H:%M:%S")
    db = sqlite3.connect(f"file:{a.db}?immutable=1", uri=True)
    since = time.time() - a.hours * 3600
    rows = db.execute("select session_id, role, content, tool_calls, timestamp from messages where timestamp > ? "
                      "order by timestamp, id", (since,)).fetchall()
    seen, out, stats = {}, [], collections.Counter()
    causes = collections.Counter()
    tools, errs, pins, pin_t, sess = collections.Counter(), 0, 0, None, None
    first_user = {}

    def flush_tools():
        nonlocal tools, errs
        if tools:
            out.append("   [tools: " + ", ".join(f"{k}×{v}" for k, v in tools.most_common())
                       + (f"; {errs} results that look like errors" if errs else "") + "]")
        tools, errs = collections.Counter(), 0

    def flush_pins():
        nonlocal pins, pin_t
        if pins:
            out.append(f"[{pins} location pins since {pin_t}]")
        pins, pin_t = 0, None

    burst = {t for t, n in collections.Counter(int(r[4]) for r in rows).items() if n >= 3}   # same second; floats differ
    for sid, role, content, tc, ts in rows:
        content = content or ""
        # each compaction stores the conversation's tail again under the same message time, as the model saw it: with
        # the "[Sun 2026-01-01 19:28:22 -03] [reply in Russian] " prefix the original row lacks (the "every message
        # stored twice" seen; three compactions made four copies)
        sig = (role, SEEN_PREFIX.sub("", content, count=1), tc)
        if sig in seen and (int(seen[sig]) == int(ts) or int(ts) in burst):
            continue                                   # a duplicated row, or a compaction copy: the old rows come back in
        seen[sig] = ts                                 # one burst with one timestamp (in a new session, or since
                                                       # in the same one); a notice that really happened again
                                                       # has its own time
        if role == "tool":
            stats["tool results"] += 1
            kind = error_kind(content)
            if kind:
                errs += 1
                stats["tool results that look like errors"] += 1
                causes[kind] += 1
            if "timed out without user response" in content:
                stats["expired approvals"] += 1
            continue
        if role == "system" or role == "session_meta":
            continue
        if role == "user" and content.startswith(PIN) and len(content) < 400:
            flush_tools()
            pins += 1
            pin_t = pin_t or hm(ts)
            stats["pins"] += 1
            continue
        flush_pins()
        if sid != sess:
            flush_tools()
            out.append(f"\n######## session …{sid[-8:]}")
            sess = sid
        if role == "assistant" and tc:
            for x in json.loads(tc):
                tools[(x.get("function") or x).get("name") or "?"] += 1
            if not content.strip():
                continue
        flush_tools()
        if role == "user":
            stats["messages from the person"] += 1
            first_user.setdefault(sid, ts)
        cut = next((v for k, v in CUT.items() if role == "assistant" and content.startswith(k)), None)
        if cut:
            stats[f"cut turns: {cut}"] += 1
        if role == "assistant" and TEMPLATE.search(content[:300]) and len(content) < 400:
            stats["template replies to a pin"] += 1
        if a.mode == "structure":
            kind = "compaction" if "[CONTEXT COMPACTION" in content else cut or ("attachment" if content.startswith("[The user sent") else "")
            out.append(f"{hm(ts)} {role:9s} {len(content):6d} chars {kind}")
        else:
            text = KEY.sub("[hidden]", content)
            if len(text) > a.cut:
                text = text[:a.cut] + f" [...+{len(text) - a.cut}]"
            out.append(f"==== {hm(ts)} {role}\n{text}")
    flush_tools()
    flush_pins()
    print("\n".join(out))
    print("\n== summary", f"(last {a.hours:g} h, {len(first_user)} sessions with messages)")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    if causes:
        print("  tool errors by cause: " + ", ".join(f"{k} {v}" for k, v in causes.most_common()))


if __name__ == "__main__":
    sys.exit(main())
