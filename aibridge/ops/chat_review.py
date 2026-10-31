#!/usr/bin/env python3
"""Turn a stretch of a person's Hermes conversations into something a reviewer can read in one sitting (2026-10-31).

  ssh <VM105> 'docker run --rm -i --entrypoint python3 -v ~/aibridge/hermes-config:/p:ro aibridge-hermes-agent:latest - \
      --hours 12 --mode text' < ops/chat_review.py > review.txt; chmod 600 review.txt

What people lived through with the bot is what it gets better from (operator, 2026-10-31: "la experiencia humana es lo que
vale"). The first explore night (hernik, 2026-10-30/31) was 1.3 MB of raw state.db rows; read by hand it showed what no
metric did: a live location that interrupted every turn, a model that ranked first on speed and read worst. This is that
reading made repeatable. It opens state.db read-only (immutable) and:
- drops the copies Hermes makes when it compacts a conversation (the same rows again under the new session) and rows
  stored twice at the same instant, but keeps a notice that really happened again ("Your request was not processed"),
- folds runs of location pins into one line ("[17 location pins from 02:36]"),
- shows each tool round as one line (names and counts, how many results look like errors), never the results,
- cuts long messages (compaction summaries, pasted logs) and masks anything shaped like an API key,
- ends with counts: turns cut by a new message, approvals that expired, pins answered with a template.

--mode text prints what was said: only for a stack whose person asked for the review (the operator's own, or with
consent). --mode structure (the default) prints the counts and the shape of each turn, no text at all: the careful-
inspection rule for everyone else. The output is private either way: keep it outside the repo, mode 600.
"""
import argparse, collections, datetime, json, re, sqlite3, sys, time

KEY = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}|thk_[A-Za-z0-9_-]{16,}"
                 r"|[A-Za-z0-9_-]{40,})")
PIN = "[The user shared a location pin.]"
CUT = {"Your request was not processed": "no procesado", "This turn did not complete": "no completado",
       "Operation interrupted": "interrumpido"}
ERRISH = re.compile(r"error|failed|timed? ?out|denied|not found|Traceback|BLOCKED", re.I)
TEMPLATE = re.compile(r"(find|найти|искать|увидеть|buscar).{0,60}(restaurant|кафе|ресторан|café|cafe)", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--db", default="/p/state.db")
    ap.add_argument("--mode", choices=("structure", "text"), default="structure")
    ap.add_argument("--cut", type=int, default=1500, help="longest message shown in text mode")
    ap.add_argument("--tz", type=float, default=-3, help="hours from UTC for the times shown")
    a = ap.parse_args()
    tz = datetime.timezone(datetime.timedelta(hours=a.tz))
    hm = lambda t: datetime.datetime.fromtimestamp(t, tz).strftime("%H:%M:%S")
    db = sqlite3.connect(f"file:{a.db}?immutable=1", uri=True)
    since = time.time() - a.hours * 3600
    rows = db.execute("select session_id, role, content, tool_calls, timestamp from messages where timestamp > ? "
                      "order by timestamp, id", (since,)).fetchall()
    seen, out, stats = {}, [], collections.Counter()
    tools, errs, pins, pin_t, sess = collections.Counter(), 0, 0, None, None
    first_user, prev_ts = {}, None

    def flush_tools():
        nonlocal tools, errs
        if tools:
            out.append("   [herramientas: " + ", ".join(f"{k}×{v}" for k, v in tools.most_common())
                       + (f"; {errs} resultados con pinta de error" if errs else "") + "]")
        tools, errs = collections.Counter(), 0

    def flush_pins():
        nonlocal pins, pin_t
        if pins:
            out.append(f"[{pins} pines de ubicación desde {pin_t}]")
        pins, pin_t = 0, None

    for sid, role, content, tc, ts in rows:
        content = content or ""
        sig = (role, content, tc)
        burst, prev_ts = ts == prev_ts, ts
        if sig in seen and (seen[sig][1] == ts or (seen[sig][0] != sid and burst)):
            continue                                   # a duplicated row, or a compaction copy: the new session gets the
        seen[sig] = (sid, ts)                          # old rows in one burst with one timestamp; a notice that really
                                                       # happened again has its own time
        if role == "tool":
            stats["resultados de herramientas"] += 1
            if ERRISH.search(content[:600]):
                errs += 1
            if "timed out without user response" in content:
                stats["aprobaciones vencidas"] += 1
            continue
        if role == "system" or role == "session_meta":
            continue
        if role == "user" and content.startswith(PIN) and len(content) < 400:
            flush_tools()
            pins += 1
            pin_t = pin_t or hm(ts)
            stats["pines"] += 1
            continue
        flush_pins()
        if sid != sess:
            flush_tools()
            out.append(f"\n######## sesión …{sid[-8:]}")
            sess = sid
        if role == "assistant" and tc:
            for x in json.loads(tc):
                tools[(x.get("function") or x).get("name") or "?"] += 1
            if not content.strip():
                continue
        flush_tools()
        if role == "user":
            stats["mensajes de la persona"] += 1
            first_user.setdefault(sid, ts)
        cut = next((v for k, v in CUT.items() if role == "assistant" and content.startswith(k)), None)
        if cut:
            stats[f"turnos cortados: {cut}"] += 1
        if role == "assistant" and TEMPLATE.search(content[:300]) and len(content) < 400:
            stats["respuestas de plantilla a un pin"] += 1
        if a.mode == "structure":
            kind = "compactación" if "[CONTEXT COMPACTION" in content else cut or ("adjunto" if content.startswith("[The user sent") else "")
            out.append(f"{hm(ts)} {role:9s} {len(content):6d} car. {kind}")
        else:
            text = KEY.sub("[oculto]", content)
            if len(text) > a.cut:
                text = text[:a.cut] + f" [...+{len(text) - a.cut}]"
            out.append(f"==== {hm(ts)} {role}\n{text}")
    flush_tools()
    flush_pins()
    print("\n".join(out))
    print("\n== resumen", f"(últimas {a.hours:g} h, {len(first_user)} sesiones con mensajes)")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    sys.exit(main())
