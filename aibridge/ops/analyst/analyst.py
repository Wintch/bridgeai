#!/usr/bin/env python3
"""analyst: a background reviewer of what happened in a stack's sessions, run when the stack goes to sleep (stage 1: no LLM).

  ops/analyst/analyst.py --stack NAME [--dry-run] [--root ~/aibridge] [--config ops/analyst/analyst.json]
  ops/analyst/analyst.py --stack NAME --seed       start from NOW: mark everything already there as seen (a stack with weeks of history)
  ops/analyst/analyst.py --report [--stack NAME] [--status new|done|ignored|all]

Why: a stack's conversations are full of small, repeatable problems (a tool that fails every time, a prompt of 18,000 tokens on every
call, a reply in the wrong language, a message nobody answered). Reading them by hand finds them, but only once. This reads what is
NEW since the last run, so nothing is analysed twice, and writes what it found to a log the operator reads and decides on by hand.
It never changes anything: no stack, no setting, no file of the person's.

When: the waker runs ops/wake/on_sleep.d/60-analyst after it stopped a stack. The stack is down, its files are quiet, nobody is
waiting (a run is never inside a person's turn).

What it reads: the stack's state.db (persisted folder, read-only, through a throwaway container that holds the same Python as the stack).
The container computes METADATA only and prints that: message ids, role, tool name, timestamps, token counts, lengths, a language
class (ru / latin / none) and, for a tool result, a short error class. The text of a conversation never leaves the container and
never reaches the log. Stage 2 (an LLM that proposes fixes from the text itself) is not here: it needs an answer to whose key and
whose consent (see HERMES_ARCHITECTURE.md, "Analyst").

Where it writes: <log_dir>/<stack>.jsonl (one finding per line: ts, stack, detector, severity, signature, count, evidence, proposal,
status), mode 600 in a 700 folder, outside the repo. <log_dir>/.mark-<stack> holds the last message id analysed (moved only after
the findings are written, and only when at least `min_new_messages` are new, so a short chat is not cut in pieces).
<log_dir>/.seen-<stack>.json holds the signature of each finding with its time: the same signature is not logged again within
`dedupe_days`. A finding that belongs to one session carries that session in its signature, so a new session is a new finding.

Test: python3 ops/analyst/analyst_selftest.py
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULTS = {
    "stacks": [],                      # which stacks are reviewed (empty = none: it is opt-in per stack)
    "log_dir": "~/aibridge/analyst",
    "image": "aibridge-hermes-agent:latest",
    "lang": "es",                      # language of the proposals in the log: es | en
    "min_new_messages": 4,
    "dedupe_days": 7,
    "slow_turn_s": 30,
    "long_tool_s": 150,
    "heavy_prompt_tokens": 15000,      # input tokens (new + cached) per model call
    "unanswered_after_s": 300,
    "stack_lang": {},                  # {"hermic": "ru"}: the language the stack is anchored to, for the language detector
}

# ---- what runs INSIDE the throwaway container: metadata only, never text -------------------------------------------------------
READER = r'''
import json, os, re, shutil, sqlite3, sys, tempfile
db = os.environ.get("ANALYST_DB", "/p/state.db"); after = int(os.environ.get("ANALYST_AFTER", "0"))
# the persisted folder is mounted read-only and SQLite wants to write its own side files: read a copy (the stack is stopped, so the file is whole)
work = tempfile.mkdtemp(); copy = os.path.join(work, "state.db"); shutil.copyfile(db, copy)
c = sqlite3.connect(copy)
def script(t):
    t = t if isinstance(t, str) else ""
    cyr = len(re.findall(r"[Ѐ-ӿ]", t)); lat = len(re.findall(r"[A-Za-z]", t))
    return "none" if cyr + lat < 3 else ("ru" if cyr > lat else "latin")
def err_class(t):
    t = t if isinstance(t, str) else ""
    low = t.lower()
    if "is disabled" in low:
        return "skill_disabled"
    if "timed out" in low or '"exit_code": 124' in t:
        return "timeout"
    if "forbidden" in low or "unauthorized" in low or "authentication" in low:
        return "auth"
    if "not found" in low or "no such file" in low:
        return "not_found"
    m = re.search(r'"exit_code":\s*(-?\d+)', t)
    if m and m.group(1) != "0":
        return "exit_nonzero"
    if re.search(r'"success":\s*false', t) or re.search(r'"error":\s*"[^"]', t):
        return "other_error"
    return ""
msgs = []
for i, sid, role, tn, tc, content, ts, tok, fin in c.execute(
        "select id, session_id, role, tool_name, tool_calls, content, timestamp, token_count, finish_reason from messages where id > ? order by id", (after,)):
    d = {"id": i, "sid": sid, "role": role, "tool": tn or "", "ts": ts, "tok": tok, "fin": fin or "",
         "len": len(content) if isinstance(content, str) else 0, "calls": bool(tc and tc not in ("[]", "null"))}
    if role in ("user", "assistant"):
        d["script"] = script(content)
    if role == "tool":
        d["err"] = err_class(content)
    msgs.append(d)
sids = sorted({m["sid"] for m in msgs})
usage = []
try:
    for sid, model, task, calls, inp, out, cache, reason in c.execute(
            "select session_id, model, task, api_call_count, input_tokens, output_tokens, cache_read_tokens, reasoning_tokens from session_model_usage"):
        if sid in sids:
            usage.append({"sid": sid, "model": model, "task": task or "", "calls": calls or 0, "inp": inp or 0, "out": out or 0,
                          "cache": cache or 0, "reason": reason or 0})
except sqlite3.Error:
    pass
print(json.dumps({"max_id": max([m["id"] for m in msgs], default=after), "messages": msgs, "usage": usage}))
'''

PROPOSALS = {
    "es": {
        "unanswered": "Un mensaje de la persona quedó sin respuesta cuando la stack se durmió. Revisar si se cortó un turno (parada, actualización) y si el mensaje sigue en la cola de Telegram; nunca debería perderse.",
        "slow_turn": "Hubo turnos de {max} s o más hasta la respuesta. Mirar qué herramienta los alarga (esperas del publicador, búsquedas) y si el bot puede avisar antes de esperar; un aviso de 'esto tarda' evita que parezca colgado.",
        "tool_errors": "La herramienta '{tool}' falló {count} vez/veces por '{cls}'. {hint}",
        "heavy_prompt": "Cada llamada al modelo manda unos {avg} tokens (nuevos + del caché). Recortar el prompt base (SOUL, índice de capacidades, skills activas) baja el costo y la latencia; el caché ya absorbe gran parte.",
        "title_reasoning": "El título de cada conversación se genera con un modelo que razona: {reason} de {out} tokens de salida fueron razonamiento. Mandar esa tarea auxiliar a un modelo sin razonamiento, o apagar los títulos.",
        "lang_anchor": "{n} respuestas salieron en el idioma de la stack ({lang}) aunque el mensaje venía en otro. Si la persona escribe en varios idiomas, conviene responder en el idioma del mensaje (ver la rama feat/reply-lang).",
        "interrupted": "Un turno se cortó porque entró otro mensaje durante la llamada al modelo. Es normal; solo preocupa si se repite mucho.",
        "long_tool": "{count} esperas de herramienta de {max} s o más. Suele ser el bot repitiendo una verificación que no puede cumplirse; darle una señal de estado en vez de dejarlo esperar.",
    },
    "en": {
        "unanswered": "A message from the person was left unanswered when the stack went to sleep. Check whether a turn was cut (stop, update) and whether the message is still queued in Telegram; it must never be lost.",
        "slow_turn": "Some turns took {max} s or more to answer. See which tool stretches them (publisher waits, searches) and whether the bot can say 'this takes a while' before waiting.",
        "tool_errors": "The tool '{tool}' failed {count} time(s) with '{cls}'. {hint}",
        "heavy_prompt": "Every model call sends about {avg} tokens (new + cached). Trimming the base prompt (SOUL, capabilities index, active skills) lowers cost and latency; the cache already absorbs much of it.",
        "title_reasoning": "Each conversation title is made by a reasoning model: {reason} of {out} output tokens were reasoning. Send that auxiliary task to a non-reasoning model, or turn titles off.",
        "lang_anchor": "{n} replies came in the stack's language ({lang}) although the message was in another. If the person writes in several languages, answering in the message's language is better (see branch feat/reply-lang).",
        "interrupted": "A turn was cut because another message arrived during the model call. Normal; only a worry if it repeats a lot.",
        "long_tool": "{count} tool waits of {max} s or more. Usually the bot repeating a check that cannot be met; give it a status signal instead of letting it wait.",
    },
}
TOOL_HINTS = {
    "es": {"skill_disabled": "La skill está desactivada en esta stack (pack apagado): activar el pack si corresponde, o que el bot no la intente.",
           "timeout": "Pasó el tiempo límite del comando: subir el límite, correrlo en segundo plano o acortar lo que hace.",
           "auth": "Credencial rechazada: revisar la clave o el permiso del servicio.",
           "not_found": "No encontró un archivo o recurso: revisar la ruta que usa.",
           "exit_nonzero": "El comando terminó con error: mirar qué comando es y si le faltan argumentos o herramientas.",
           "other_error": "Devolvió un error sin clase conocida: mirarlo en el log de la stack."},
    "en": {"skill_disabled": "The skill is off in this stack (pack disabled): turn the pack on if it should be, or stop the bot from trying it.",
           "timeout": "The command hit its time limit: raise it, run it in the background or shorten what it does.",
           "auth": "Credential refused: check the key or the service permission.",
           "not_found": "A file or resource was not found: check the path it uses.",
           "exit_nonzero": "The command ended with an error: see which command it is and whether it lacks arguments or tools.",
           "other_error": "It returned an error of no known class: see it in the stack's log."},
}


def sig(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def analyze(stack, msgs, usage, cfg, now=None):
    """Findings (dicts) from the metadata of the new messages. Pure: no files, no docker, no clock but `now`."""
    now = now or time.time()
    L = cfg["lang"] if cfg["lang"] in PROPOSALS else "es"
    P, H = PROPOSALS[L], TOOL_HINTS[L]
    out = []

    def add(detector, severity, key, count, evidence, text):
        out.append({"detector": detector, "severity": severity, "signature": sig(stack, detector, key), "count": count,
                    "evidence": evidence, "proposal": text})

    by_sid = {}
    for m in msgs:
        by_sid.setdefault(m["sid"], []).append(m)
    for sid, rows in by_sid.items():
        rows.sort(key=lambda m: m["id"])
        short = sid[-8:]
        # unanswered: the last thing in the session is the person's message, and it is old
        last = rows[-1]
        if last["role"] == "user" and now - (last["ts"] or now) >= cfg["unanswered_after_s"]:
            add("unanswered", "high", sid + ":" + str(last["id"]), 1, {"session": short, "message_id": last["id"]}, P["unanswered"])
        # slow turns: a person's message to the final answer (an assistant message with no tool calls)
        slow, pend = [], None
        for m in rows:
            if m["role"] == "user":
                pend = m
            elif m["role"] == "assistant" and not m["calls"] and pend is not None:
                dt = (m["ts"] or 0) - (pend["ts"] or 0)
                if dt >= cfg["slow_turn_s"]:
                    slow.append((round(dt), pend["id"]))
                pend = None
        if slow:
            add("slow_turn", "medium" if max(s for s, _ in slow) >= 120 else "low", sid, len(slow),
                {"session": short, "seconds": [s for s, _ in slow][:8], "message_ids": [i for _, i in slow][:8]},
                P["slow_turn"].format(max=max(s for s, _ in slow)))
        # long tool waits: a tool result that came long after the call that asked for it
        waits, prev_call = [], None
        for m in rows:
            if m["role"] == "assistant" and m["calls"]:
                prev_call = m
            elif m["role"] == "tool" and prev_call is not None:
                dt = (m["ts"] or 0) - (prev_call["ts"] or 0)
                if dt >= cfg["long_tool_s"]:
                    waits.append((round(dt), m["tool"]))
                prev_call = None
        if len(waits) >= 2:
            add("long_tool", "medium", sid, len(waits), {"session": short, "seconds": [w for w, _ in waits][:8], "tools": sorted({t for _, t in waits})},
                P["long_tool"].format(count=len(waits), max=max(w for w, _ in waits)))
        # interrupted turns
        n_int = sum(1 for m in rows if m["fin"].startswith("interrupt"))
        if n_int:
            add("interrupted", "info", sid, n_int, {"session": short}, P["interrupted"])
        # language: replies in the stack's language to messages in another script
        lang = cfg["stack_lang"].get(stack)
        if lang == "ru":
            n, last_user = 0, None
            for m in rows:
                if m["role"] == "user":
                    last_user = m.get("script")
                elif m["role"] == "assistant" and not m["calls"] and last_user is not None:
                    if last_user == "latin" and m.get("script") == "ru":
                        n += 1
                    last_user = None
            if n >= 3:
                add("lang_anchor", "low", sid, n, {"session": short}, P["lang_anchor"].format(n=n, lang=lang))
    # tool errors, grouped by tool and class over the whole batch (not by session: the same failure in two chats is one finding)
    errs = {}
    for m in msgs:
        if m["role"] == "tool" and m.get("err"):
            errs.setdefault((m["tool"] or "?", m["err"]), []).append(m)
    for (tool, cls), ms in sorted(errs.items()):
        sev = "medium" if (cls in ("skill_disabled", "auth", "timeout") or len(ms) >= 3) else "low"
        add("tool_errors", sev, f"{tool}:{cls}", len(ms),
            {"tool": tool, "class": cls, "sessions": sorted({m["sid"][-8:] for m in ms})[:6], "message_ids": [m["id"] for m in ms][:8]},
            P["tool_errors"].format(tool=tool, count=len(ms), cls=cls, hint=H.get(cls, "")).strip())
    # usage: the weight of the prompt and the reasoning spent on titles
    main = [u for u in usage if not u["task"] and u["calls"] > 0]
    if main:
        tot_calls = sum(u["calls"] for u in main)
        avg = round(sum(u["inp"] + u["cache"] for u in main) / tot_calls)
        if avg >= cfg["heavy_prompt_tokens"]:
            add("heavy_prompt", "low", "weekly", tot_calls, {"avg_tokens_per_call": avg, "calls": tot_calls, "sessions": len({u["sid"] for u in main})},
                P["heavy_prompt"].format(avg=avg))
    titles = [u for u in usage if u["task"] == "title_generation" and u["reason"] >= 100]
    if titles:
        add("title_reasoning", "low", "weekly", len(titles),
            {"reasoning_tokens": sum(u["reason"] for u in titles), "output_tokens": sum(u["out"] for u in titles), "models": sorted({u["model"] for u in titles})},
            P["title_reasoning"].format(reason=sum(u["reason"] for u in titles), out=sum(u["out"] for u in titles)))
    return out


# ---- state on disk ----------------------------------------------------------------------------------------------------------------
def load_config(path):
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.load(open(path)))
    except (OSError, ValueError):
        pass
    return cfg


def private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def write_private(path, text, mode="w"):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | (os.O_APPEND if mode == "a" else os.O_TRUNC), 0o600)
    with os.fdopen(fd, mode) as f:
        f.write(text)
    os.chmod(path, 0o600)


def read_mark(d, stack):
    try:
        return int(open(os.path.join(d, f".mark-{stack}")).read().strip())
    except (OSError, ValueError):
        return 0


def dedupe(findings, d, stack, days, now):
    """The findings not logged within `days`, and the updated seen map. Findings of one batch never hide each other."""
    p = os.path.join(d, f".seen-{stack}.json")
    try:
        seen = json.load(open(p))
    except (OSError, ValueError):
        seen = {}
    keep = {k: t for k, t in seen.items() if now - t < days * 86400}
    fresh = []
    for f in findings:
        if f["signature"] in keep:
            continue
        fresh.append(f)
    for f in fresh:
        keep[f["signature"]] = now
    return fresh, keep


def persist_dir(root, stack):
    return os.path.join(root, "hermes-config") if stack == "hernik" else os.path.join(root, "stacks", stack, "persist")


def read_metadata(root, stack, after, image, run=subprocess.run):
    p = persist_dir(root, stack)
    if not os.path.isdir(p):
        raise RuntimeError(f"no persisted folder for {stack}")
    r = run(["docker", "run", "--rm", "-i", "-v", f"{p}:/p:ro", "-e", f"ANALYST_AFTER={after}", "--entrypoint", "python3", image, "-c", READER],
            input="", capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("reader failed: " + (r.stderr or "").strip().splitlines()[-1][:160] if (r.stderr or "").strip() else "reader failed")
    return json.loads(r.stdout.strip().splitlines()[-1])


def run_stack(stack, cfg, root, dry=False, now=None, reader=read_metadata):
    now = now or time.time()
    d = os.path.expanduser(cfg["log_dir"])
    if stack not in cfg["stacks"]:
        return "not reviewed (not in the config)"
    private_dir(d)
    lock = open(os.path.join(d, f".lock-{stack}"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return "another run is going"
    after = read_mark(d, stack)
    meta = reader(root, stack, after, cfg["image"])
    msgs = meta.get("messages", [])
    if len(msgs) < cfg["min_new_messages"]:
        return f"{len(msgs)} new message(s), waiting for {cfg['min_new_messages']}"
    found = analyze(stack, msgs, meta.get("usage", []), cfg, now)
    fresh, seen = dedupe(found, d, stack, cfg["dedupe_days"], now)
    lines = "".join(json.dumps({"ts": round(now), "stack": stack, **f, "status": "new"}, ensure_ascii=False) + "\n" for f in fresh)
    if dry:
        return f"dry run: {len(msgs)} new messages, {len(found)} findings, {len(fresh)} would be logged\n" + lines
    if lines:
        write_private(os.path.join(d, f"{stack}.jsonl"), lines, "a")
    write_private(os.path.join(d, f".seen-{stack}.json"), json.dumps(seen))
    write_private(os.path.join(d, f".mark-{stack}"), str(meta["max_id"]))   # last, so a failed write is analysed again
    return f"{len(msgs)} new messages, {len(fresh)} finding(s) logged ({len(found) - len(fresh)} already known)"


def seed(stack, cfg, root, reader=read_metadata):
    """Mark every message that exists now as analysed, without analysing or logging anything."""
    d = os.path.expanduser(cfg["log_dir"])
    if stack not in cfg["stacks"]:
        return "not reviewed (not in the config)"
    private_dir(d)
    meta = reader(root, stack, 0, cfg["image"])
    write_private(os.path.join(d, f".mark-{stack}"), str(meta["max_id"]))
    return f"seeded at message {meta['max_id']} ({len(meta.get('messages', []))} existing messages will not be analysed)"


def report(cfg, stack, status):
    d = os.path.expanduser(cfg["log_dir"])
    names = [stack] if stack else sorted(f[:-6] for f in os.listdir(d) if f.endswith(".jsonl")) if os.path.isdir(d) else []
    rows = []
    for n in names:
        try:
            for line in open(os.path.join(d, f"{n}.jsonl")):
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
        except OSError:
            pass
    rows = [r for r in rows if status == "all" or r.get("status") == status]
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    rows.sort(key=lambda r: (order.get(r.get("severity"), 9), -r.get("ts", 0)))
    for r in rows:
        when = time.strftime("%m-%d %H:%M", time.localtime(r.get("ts", 0)))
        print(f"[{r['severity']:<6}] {when} {r['stack']:<9} {r['detector']:<15} x{r['count']}  id={r['signature']}")
        print(f"          {r['proposal']}")
        print(f"          evidence: {json.dumps(r['evidence'], ensure_ascii=False)}")
    print(f"{len(rows)} finding(s)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stack")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--status", default="new", choices=["new", "done", "ignored", "all"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--root", default=os.path.expanduser("~/aibridge"))
    ap.add_argument("--config", default=os.path.join(HERE, "analyst.json"))
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    if a.report:
        return report(cfg, a.stack, a.status)
    if not a.stack or not re.fullmatch(r"[a-z][a-z0-9]{1,19}", a.stack):
        print("usage: analyst.py --stack NAME | --report", file=sys.stderr)
        return 2
    try:
        print(f"analyst {a.stack}: " + (seed(a.stack, cfg, a.root) if a.seed else run_stack(a.stack, cfg, a.root, a.dry_run)))
    except Exception as exc:   # a reviewer must never be what breaks a sleep
        print(f"analyst {a.stack}: could not run ({type(exc).__name__}: {str(exc)[:160]})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
