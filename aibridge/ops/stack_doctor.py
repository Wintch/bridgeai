#!/usr/bin/env python3
"""One screen about one stack when the early alert fired: is it awake, what its last turns looked like, are its keys fine, which
failure signals fired, did the job search go quiet, is the SOUL being cut. READ-ONLY, and never prints chat.

  stack_doctor.py STACK [--n 15] [--json]      exit 0 (a missing source prints n/d), 2 for a stack that is not in stacks.json

Privacy: only whitelisted fields are copied out of the files it reads. The turns come from the router's evaluation log
(/workdir/.model-eval.jsonl, through `docker cp`: it also works while the stack sleeps), whose lines carry a session hash and a message id:
those fields are dropped, as is everything that is not in the whitelists below, and every value is checked against a strict pattern
before it is printed. Keys appear as provider + last 4 characters only. Run it by hand, or let the ops brain run it (--json).
"""
import argparse, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, HERE)
import early_alert as ea  # noqa: E402

KEY_STATUS = os.environ.get("STACK_DOCTOR_KEY_STATUS", os.path.expanduser("~/.local/state/key_status.json"))
EVAL_LOG = "/workdir/.model-eval.jsonl"
KEYS_STATUS = "/workdir/.keys-status.json"
JOBPUSH_LOG = "/workdir/jobfinder/data/jobpush.log"
SOUL = "/root/.hermes/SOUL.md"
HERMES_CONFIG = "/root/.hermes/config.yaml"
DEFAULT_CAP = 20000                      # Hermes's own default when config.yaml has no context_file_max_chars
JOB_KEYS = ("mode", "result", "exit", "new", "kept", "carried", "unverified", "secs", "sent", "chain_new", "chain_closing", "chain_expired", "diff", "store")
SAFE_WORD = re.compile(r"^[A-Za-z0-9._:-]{1,24}$")
SAFE_MODEL = re.compile(r"^[A-Za-z0-9 ._:/+()-]{1,60}$")
FINISHES = ("stop", "length", "tool_calls", "content_filter", "error")
ND = "n/d"


CP_LIMIT = 6 * 1024 * 1024               # the evaluation log rotates at 5 MB; a bigger file is not ours and counts as unreadable


def cp(brain, path):
    """File from the brain container (running or not) as bytes, or None. Bounded copy (never buffers more than CP_LIMIT). Never raises."""
    try:
        return ea.cp_read(brain, path, CP_LIMIT)
    except Exception:
        return None


def num(x, lo=0, hi=10 ** 12):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and lo <= x <= hi else None


def age_text(sec):
    if sec is None:
        return ND
    sec = int(max(sec, 0))
    return f"{sec}s" if sec < 120 else f"{sec // 60}m" if sec < 7200 else f"{sec // 3600}h{sec % 3600 // 60:02d}"


def lines_of(raw, tail):
    return raw.decode("utf-8", "replace").splitlines()[-tail:] if raw else []


# ---------------------------------------------------------------- sections

def estado(s, now):
    running, started = ea.docker_state(s.get("brain") or "")
    wd, brain = ea.stack_paths(s), s.get("brain") or ""
    ep = {n: ea.read_epoch(wd, "." + n, brain, now) for n in ("last_human", "last_reply", "last_model_call")}
    midnight = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
    return {"awake": running, "uptime_s": int(now - started) if running and started else None,
            "age_s": {n: (int(now - v) if v is not None else None) for n, v in ep.items()},
            "wakes_today": ea.telemetry_wakes_today(s["name"], midnight)}


def turnos(s, n):
    """The last n non-aux turns of the evaluation log: one row per turn with whitelisted, pattern-checked fields only."""
    raw = cp(s.get("brain") or "", EVAL_LOG)
    if raw is None:
        return None
    groups, order = {}, []
    for ln in lines_of(raw, 300):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(r, dict) or r.get("aux") or "feedback" in r or num(r.get("ts")) is None:
            continue
        key = r.get("turn") if isinstance(r.get("turn"), str) and r.get("turn") else f"#{len(order)}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    rows = []
    for key in order[-n:]:
        calls = groups[key]
        last = calls[-1]
        model = last.get("model") if isinstance(last.get("model"), str) and SAFE_MODEL.match(last["model"]) else "?"
        fin = last.get("finish") if last.get("finish") in FINISHES else "?"
        total = lambda f: sum(v for v in (num(c.get(f)) for c in calls) if v is not None)
        rows.append({"ts": int(calls[0]["ts"]), "model": model, "finish": fin, "calls": len(calls), "tools": int(total("tools")),
                     "s": round(total("s"), 1), "not_ok": sum(1 for c in calls if c.get("result") != "ok"),
                     "odd": int(total("odd")), "leak": int(total("leak")), "bad_args": int(total("bad_args"))})
    return rows


def claves(s):
    out = {"host": None, "stack": None}
    try:
        st = json.load(open(KEY_STATUS)).get("stacks", {}).get(s["name"])
    except (OSError, ValueError, AttributeError):
        st = None
    if isinstance(st, dict):
        out["host"] = []
        for kid, ent in st.items():
            prov, _, last4 = str(kid).partition(":")
            status = ent.get("status") if isinstance(ent, dict) else None
            if re.match(r"^[a-z0-9_-]{1,24}$", prov) and re.match(r"^[A-Za-z0-9_-]{1,8}$", last4) and status in ("ok", "rejected", "limited", "unknown"):
                out["host"].append({"provider": prov, "last4": last4, "status": status})
    raw = cp(s.get("brain") or "", KEYS_STATUS)
    if raw is not None:
        try:
            d = json.loads(raw)
        except ValueError:
            d = None
        if isinstance(d, dict):
            out["stack"] = []
            for prov, ent in d.items():
                if isinstance(ent, dict) and re.match(r"^[a-z0-9_-]{1,24}$", str(prov)):
                    at = ent.get("at")
                    out["stack"].append({"provider": prov, "ok": ent.get("ok") if isinstance(ent.get("ok"), bool) else None,
                                         "at": at if isinstance(at, str) and re.match(r"^[0-9T:.+Z-]{8,32}$", at) else None})
    return out


def senales(s, now, info=None):
    info = info or ea.gather(s, now, since=now - 2 * 3600)
    ev2h = [e for e in info["events"] if e.ts >= now - 2 * 3600]
    counts = {}
    for e in ev2h:
        counts[e.cat] = counts.get(e.cat, 0) + (1 if e.cat in ea.STANDING else e.n)
    una = ea.unanswered_minutes(info, now)
    sc, pts, cnt = ea.score(info["events"], now, ea.WINDOW_MIN, una)
    if una is not None:
        counts["unanswered"] = una
    st = ea.load_state().get(s["name"]) or {}
    return {"counts_2h": counts, "score_30m": round(sc, 1), "points": {k: round(v, 1) for k, v in pts.items()},
            "sink": info["sink_found"], "last_alert_age_s": int(now - st["last_sent"]) if st.get("last_sent") else None,
            "alert_open": bool(st.get("open")), "last_score": st.get("last_score")}


def empleo(s, now):
    raw = cp(s.get("brain") or "", JOBPUSH_LOG)
    if raw is None:
        return None
    lines = [l for l in lines_of(raw, 400) if l.strip()]
    if not lines:
        return None
    last = lines[-1]
    out = {"fields": {}, "age_s": None, "zero_streak": 0}
    m = re.match(r"^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)Z", last)
    if m:
        import calendar
        out["age_s"] = int(now - calendar.timegm(tuple(int(x) for x in m.groups())))
    for k, v in re.findall(r"\b([a-z_]+)=(\S+)", last):
        if k in JOB_KEYS and SAFE_WORD.match(v):
            out["fields"][k] = v
    for l in reversed(lines):
        if not re.search(r"\bresult=ok\b", l) or not re.search(r"\bmode=noche\b", l):
            continue                      # same rule as jobpush.zero_streak: only night runs count as days
        new = re.search(r"\bnew=(\d+)", l)
        if not new or int(new.group(1)) != 0:
            break
        out["zero_streak"] += 1
    return out


def soul(s):
    brain = s.get("brain") or ""
    raw = cp(brain, SOUL)
    if raw is None:
        return None
    chars = len(raw.decode("utf-8", "replace"))
    cfg = cp(brain, HERMES_CONFIG)
    m = re.search(r"^context_file_max_chars:\s*(\d{1,7})\s*$", cfg.decode("utf-8", "replace"), re.M) if cfg else None
    cap = int(m.group(1)) if m else None
    eff = cap or DEFAULT_CAP
    return {"chars": chars, "cap": cap, "cap_is_default": cap is None, "pct": round(100 * chars / eff), "over": chars > eff}


# ---------------------------------------------------------------- output

def render(r):
    L = [f"== {r['stack']} =="]
    e = r["estado"]
    ag = e["age_s"]
    L.append(f"Estado: {'despierto' if e['awake'] else 'dormido'}"
             + (f", prendido hace {age_text(e['uptime_s'])}" if e["uptime_s"] is not None else "")
             + f" | último mensaje {age_text(ag['last_human'])}, última respuesta {age_text(ag['last_reply'])}, "
               f"última llamada al modelo {age_text(ag['last_model_call'])} | despertares hoy {e['wakes_today'] if e['wakes_today'] is not None else ND}")
    L.append(f"Últimos turnos (más nuevo abajo):" + ("" if r["turnos"] is not None else f" {ND}"))
    for t in r["turnos"] or []:
        flags = "".join(f" {k}={t[k]}" for k in ("odd", "leak", "bad_args") if t[k])
        L.append(f"  {time.strftime('%d/%m %H:%M', time.localtime(t['ts']))}  {t['model']}  fin={t['finish']}  llamadas={t['calls']}  tools={t['tools']}"
                 f"  {t['s']}s" + (f"  FALLÓ x{t['not_ok']}" if t["not_ok"] else "") + flags)
    k = r["claves"]
    L.append("Keys (chequeo del host): " + (", ".join(f"{x['provider']} …{x['last4']} {x['status']}" for x in k["host"]) or "ninguna") if k["host"] is not None else f"Keys (chequeo del host): {ND}")
    L.append("Keys (estado en el stack): " + (", ".join(f"{x['provider']} {'ok' if x['ok'] else 'NO' if x['ok'] is False else '?'} {x['at'] or ''}".rstrip() for x in k["stack"]) or "ninguna")
             if k["stack"] is not None else f"Keys (estado en el stack): {ND}")
    g = r["senales"]
    L.append("Señales últimas 2 h: " + (", ".join(f"{c} x{n}" for c, n in sorted(g["counts_2h"].items())) or "ninguna")
             + ("" if g["sink"] else " (este stack no tiene el archivo de señales: imagen vieja)"))
    L.append(f"  puntaje ahora (30 min): {g['score_30m']:.1f} | último aviso: "
             + (f"hace {age_text(g['last_alert_age_s'])}{' (abierto)' if g['alert_open'] else ''}" if g["last_alert_age_s"] is not None else "nunca"))
    j = r["empleo"]
    if j is None:
        L.append(f"Búsqueda de empleo: {ND}")
    else:
        L.append("Búsqueda de empleo: " + " ".join(f"{k}={v}" for k, v in j["fields"].items()) + f" | línea de hace {age_text(j['age_s'])}"
                 + f" | rachas sin novedades: {j['zero_streak']}")
    so = r["soul"]
    L.append(f"SOUL: {ND}" if so is None else
             f"SOUL {so['chars']}/{so['cap'] if so['cap'] else str(DEFAULT_CAP) + ' (por defecto)'} ({so['pct']}%)" + ("  <-- RECORTADO: Hermes descarta el medio" if so["over"] else ""))
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="read-only one-screen look at a stack")
    ap.add_argument("stack")
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        stacks = [x for x in json.load(open(ea.STACKS)).get("stacks", []) if isinstance(x, dict) and x.get("name")]
    except (OSError, ValueError):
        stacks = []
    s = next((x for x in stacks if x["name"] == a.stack), None)
    if s is None:
        print(f"stack_doctor: no stack named {a.stack[:40]!r} in {ea.STACKS}", file=sys.stderr)
        return 2
    now = float(os.environ["EARLY_ALERT_NOW"]) if os.environ.get("EARLY_ALERT_NOW") else time.time()
    r = {"stack": s["name"], "estado": estado(s, now), "turnos": turnos(s, max(1, min(a.n, 100))), "claves": claves(s),
         "senales": senales(s, now), "empleo": empleo(s, now), "soul": soul(s)}
    print(json.dumps(r, indent=1) if a.json else render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
