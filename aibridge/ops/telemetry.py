#!/usr/bin/env python3
"""How bridgeai is actually used, without personal data: what to improve next, and problems nobody reports.

  telemetry.py collect         every 5 min (telemetry.timer): new turns, API errors, wakes, host; instant alerts
  telemetry.py report daily    daily summary to the ops bot (telemetry-report.timer)
  telemetry.py report weekly   "what to improve" ranking (the daily run sends it on Mondays)
  telemetry.py report daily --print   print instead of sending

What is collected (~/.local/state/telemetry.db, on this host only):
  turns   stack, time, channel (telegram/web/cron), seconds to the final answer, tool calls, tool errors, failed
          (Hermes marked it failed_turn, or no answer at all), empty answer, model, a short hash of the session id
  errors  stack, time, provider, model, HTTP code of failed model API calls (agent.log)
  wakes   stack, time, reason, seconds, outcome (waker journal)
  host    available RAM, swap used, disk use
  gw      every gateway call (gateway.py): which gateway, host, seconds, GPU/CPU seconds, MB in/out, fallback, error
  gwhost  each gateway host (ops/gateways.json) up or down, every run
What is NOT: message text, tool output, titles, chat or user ids, names. The text never leaves SQLite: the queries
below compute booleans (empty answer, tool error) inside the database and only those come out.

Stack data is read from inside the container (`docker exec`, live db with its WAL) when it runs, else from its
persisted copy through a throwaway read-only container (the files are root 0600).
"""
import argparse, datetime as dt, io, json, os, re, sqlite3, statistics, subprocess, sys, tarfile, time, urllib.request

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
BACKUP_MAX_AGE_H = 26

# Runs INSIDE the container. Prints one JSON line per closed turn whose user message is newer than argv[1].
TURNS_SCRIPT = r'''
import hashlib, json, sqlite3, sys, time
since, path = float(sys.argv[1]), sys.argv[2]
uri = "file:%s?mode=ro" % path + ("&immutable=1" if path.startswith("/p/") else "")
db = sqlite3.connect(uri, uri=True, timeout=10)
meta = {sid: (src or "", (prov or "") + "/" + (model or "")) for sid, src, prov, model in
        db.execute("select id, source, billing_provider, model from sessions")}
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
    src, model = meta.get(sid, ("", "/"))
    print(json.dumps({"ts": u[2], "session": hashlib.sha1(sid.encode()).hexdigest()[:8], "source": src,
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
        # 2026-10-09: 35 of hernik's 58 "unanswered" Telegram messages were followed within 30 s by another one.
        if turn and turn[0][1] == "user" and len(turn) == 1 and r[2] - turn[0][2] < 900:
            continue
        if turn and turn[0][1] == "user": emit(cur, turn, True)
        turn = [r]
    elif turn:
        turn.append(r)
if turn: emit(cur, turn, any(m[1] == "assistant" and m[3] == "stop" for m in turn[1:]))
'''

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
      create table if not exists awake(ts real, brains int, webs int);""")
    return c


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


def stack_turns(stack, since):
    brain = stack["brain"]
    if inspect(brain, "{{.State.Running}}") == "true":
        r = sh("docker", "exec", "-i", brain, "python3", "-", str(since), "/root/.hermes/state.db", inp=TURNS_SCRIPT)
    else:
        src = inspect(brain, '{{range .Mounts}}{{if eq .Destination "/hermes-persist"}}{{.Source}}{{end}}{{end}}')
        image = inspect(brain, "{{.Config.Image}}")
        if not (src and image):
            return []
        r = sh("docker", "run", "--rm", "-i", "--network", "none", "-v", f"{src}:/p:ro", "--entrypoint", "python3",
               image, "-", str(since), "/p/state.db", inp=TURNS_SCRIPT, timeout=180)
    if r.returncode != 0:
        print(f"[{stack['name']}] turns: read failed ({r.stderr.strip().splitlines()[-1][:120] if r.stderr.strip() else r.returncode})")
        return []
    return [json.loads(l) for l in r.stdout.splitlines() if l.startswith("{")]


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


def stack_gateway_log(stack, since):
    """New lines of the stack's /workdir/.gateway-log.jsonl (root 0600 inside the container's workdir)."""
    brain = stack["brain"]
    if inspect(brain, "{{.State.Running}}") == "true":
        r = sh("docker", "exec", brain, "sh", "-c", "cat /workdir/.gateway-log.jsonl 2>/dev/null")
    else:
        src = inspect(brain, '{{range .Mounts}}{{if eq .Destination "/workdir"}}{{.Source}}{{end}}{{end}}')
        if not src:
            return []
        r = sh("docker", "run", "--rm", "--network", "none", "-v", f"{src}:/w:ro", "busybox:latest",
               "sh", "-c", "cat /w/.gateway-log.jsonl 2>/dev/null")
    out = []
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("ts", 0) > since:
            out.append(d)
    return out


def probe_gateway_hosts(c, now):
    """{host: up?} for every host in the master list; recorded for availability; always_on hosts alert when down."""
    try:
        hosts = json.load(open(GW_MASTER)).get("hosts", {})
    except (OSError, ValueError):
        return {}
    state = {}
    for name, h in hosts.items():
        port = h.get("transcode") or h.get("upscale")
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
                notify.resolve(f"gwhost:{name}", f"{name} ({h.get('gpu', 'GPU')}) volvió a responder")
            else:
                notify.alert(f"gwhost:{name}", f"{name} ({h.get('gpu', 'GPU')}) no responde y está marcado como siempre prendido.")
    c.execute("delete from gwhost where ts < ?", (now - 90 * 86400,))
    return state


CLAUDE_FIX = {"auth": "la sesión de Claude venció en esa máquina: hay que correr `claude auth login` ahí",
              "key": "la clave SSH ya no está autorizada en esa máquina",
              "unreachable": "la máquina está apagada o no se llega por la red",
              "timeout": "Claude tardó más que el límite (15 min por defecto)"}


def gateway_alerts(name, calls):
    for d in calls:
        g = d.get("gateway")
        if g == "transcode" and d.get("fallback"):
            down = ", ".join(d.get("down") or []) or "ninguno configurado"
            notify.alert(f"gw:{name}:transcode", f"{name}: un video se procesó en la CPU del servidor ({d.get('seconds')} s, "
                                                 f"{d.get('mb_in')} MB) porque ningún host GPU respondía ({down}).")
        elif g == "transcode" and d.get("ok"):
            notify.resolve(f"gw:{name}:transcode", f"{name}: los videos vuelven a ir a la GPU")
        elif g == "upscale" and not d.get("ok"):
            notify.alert(f"gw:{name}:upscale", f"{name}: no se pudo agrandar una imagen: ningún host GPU respondía.")
        elif g == "upscale":
            notify.resolve(f"gw:{name}:upscale")
        elif g == "claude" and not d.get("ok"):
            err = d.get("error") or "otro"
            notify.alert(f"gw:{name}:claude", f"{name}: Claude en {d.get('host')} falló ({err}): "
                                              f"{CLAUDE_FIX.get(err, 'ver el log del stack')}.")
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


def collect(c, stacks):
    now = time.time()
    first = meta_get(c, "last_collect") is None   # first run loads a week of history: no alerts for old things
    last_run = float(meta_get(c, "last_collect", now - FIRST_LOOKBACK_S))
    new_turns = []
    for s in stacks:
        name = s["name"]
        if not ran_since(s["brain"], last_run - 60):
            continue
        since = c.execute("select max(ts) from turns where stack=?", (name,)).fetchone()[0] or now - FIRST_LOOKBACK_S
        for t in stack_turns(s, since):
            cur = c.execute("insert or ignore into turns values(?,?,?,?,?,?,?,?,?,?)",
                            (name, t["ts"], t["session"], t["source"], t["model"], t["seconds"], t["tools"],
                             t["tool_errors"], t["failed"], t["empty"]))
            if cur.rowcount:
                new_turns.append((name, t))
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
            notify.resolve(f"tts:{s['name']}", f"{s['name']}: la voz (TTS) volvió a funcionar")
        elif not first:
            notify.alert(f"tts:{s['name']}", f"{s['name']}: la voz (TTS) no responde ({detail}, {secs:.0f} s). "
                                             f"El modo llamada de la web queda mudo.")
    probe_gateway_hosts(c, now)
    brains = sum(1 for s in stacks if inspect(s["brain"], "{{.State.Running}}") == "true")
    webs = sum(1 for s in stacks if s.get("web") and inspect(s["web"][0], "{{.State.Running}}") == "true")
    c.execute("insert into awake values(?,?,?)", (now, brains, webs))
    c.execute("delete from awake where ts < ?", (now - 90 * 86400,))
    mem, swap, disk = host_sample()
    c.execute("insert into host values(?,?,?,?)", (now, mem, swap, disk))
    c.execute("delete from host where ts < ?", (now - 90 * 86400,))
    meta_set(c, "last_collect", now)
    c.commit()
    if not first:
        alerts(c, stacks, new_turns, disk)
    print(f"collect: {len(new_turns)} new turn(s), host avail={mem}MB swap={swap}MB disk={disk}%")


SRC_LABEL = {"telegram": "Telegram", "api_server": "web", "cron": "cron", "oneshot": "CLI"}


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
            notify.alert(f"tele:{name}:failed", f"{name}: {len(failed)} turno(s) fallaron o quedaron sin respuesta ({where}). "
                                                f"La persona no recibió contestación.", quiet=3600)
        if empty:
            notify.alert(f"tele:{name}:empty", f"{name}: {len(empty)} respuesta(s) vacía(s) (el modelo devolvió texto en blanco).",
                         quiet=3600)
        if slow:
            worst = max(t["seconds"] for t in slow)
            notify.alert(f"tele:{name}:slow", f"{name}: {len(slow)} respuesta(s) sin herramientas tardaron más de "
                                              f"{SLOW_PLAIN_TURN_S} s (la peor {worst:.0f} s). Revisar modelo/proveedor.")
        ok = [t for t in turns if not t["failed"] and not t["empty"]]
        if ok and not failed:
            notify.resolve(f"tele:{name}:failed", f"{name}: vuelve a contestar bien")
        if ok and not empty:
            notify.resolve(f"tele:{name}:empty")
    if disk >= DISK_ALERT_PCT:
        notify.alert("host:disk", f"Disco al {disk}% en el host de los stacks.")
    else:
        notify.resolve("host:disk", f"Disco de nuevo en {disk}%")
    for name, age in backup_ages(stacks).items():
        if age is not None and age > BACKUP_MAX_AGE_H:
            notify.alert(f"backup:{name}", f"{name}: el último backup tiene {age:.0f} h.")
        elif age is not None:
            notify.resolve(f"backup:{name}", f"{name}: hay backup nuevo")


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
    rows = c.execute("select source, seconds, tools, tool_errors, failed, empty, session from turns where stack=? and ts>=?",
                     (name, t0)).fetchall()
    wk = c.execute("select seconds, outcome from wakes where stack=? and ts>=?", (name, t0)).fetchall()
    er = c.execute("select provider, code, count(*) from errors where stack=? and ts>=? group by 1,2 order by 3 desc",
                   (name, t0)).fetchall()
    if not rows and not wk and not er:
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
    lines = [f"• {name}: {stats['turns']} turnos en {stats['sessions']} conversaciones ("
             + ", ".join(f"{k} {v}" for k, v in sorted(src.items())) + ")" if rows else f"• {name}: sin turnos"]
    if rows:
        lines.append(f"   respuesta p50 {fmt_s(stats['p50'])}, p95 {fmt_s(stats['p95'])}; herramientas {stats['tools']} "
                     f"({stats['tool_errors']} con error)")
    if stats["failed"] or stats["empty"]:
        lines.append(f"   ⚠️ {stats['failed']} fallidos, {stats['empty']} vacíos")
    if wk:
        lines.append(f"   encendidos {stats['wakes']} (mediana {fmt_s(stats['wake_p50'])})"
                     + (f", ⚠️ {stats['wake_bad']} con problema" if stats["wake_bad"] else ""))
    if er:
        lines.append("   errores de API: " + ", ".join(f"{p} {code}×{n}" for p, code, n in er[:4]))
    return "\n".join(lines), stats


def report(c, stacks, kind, to_stdout):
    days = 7 if kind == "weekly" else 1
    t0 = time.time() - days * 86400
    title = "📊 Resumen semanal" if kind == "weekly" else "📊 Resumen de ayer (24 h)"
    out, all_stats = [title], {}
    for s in stacks:
        text, st = stack_lines(c, s["name"], t0)
        if text:
            out.append(text)
            all_stats[s["name"]] = st
    h = c.execute("select min(mem_avail_mb), max(swap_used_mb), max(disk_pct) from host where ts>=?", (t0,)).fetchone()
    if h and h[0] is not None:
        out.append(f"• host: RAM libre mínima {h[0]} MB, swap máx {h[1]} MB, disco {h[2]}%")
    a = c.execute("select max(brains), avg(brains) from awake where ts>=?", (t0,)).fetchone()
    if a and a[0] is not None:
        out.append(f"• stacks despiertos a la vez: máximo {a[0]}, promedio {a[1]:.1f} (de {len(stacks)}; ~0,9 GB cada uno)")
    out.extend(gateway_report(c, t0))
    missing = [n for n, a in backup_ages(stacks).items() if a is None]
    if missing:
        out.append("• sin backup: " + ", ".join(missing))
    if kind == "weekly":
        out.append("\n🔧 Qué mejorar primero (impacto = veces × personas afectadas):")
        out.extend(ranking(c, stacks, t0) or ["  nada que se destaque esta semana"])
    if len(out) == 1:
        out.append("Sin actividad.")
    text = "\n".join(out)
    if to_stdout:
        print(text)
    else:
        notify.send(text)


def gateway_report(c, t0):
    """Per gateway: use, outcome, time, and what it means in practice (GPU vs CPU, share of all turn time)."""
    lines = []
    turn_total = c.execute("select sum(seconds) from turns where ts>=? and seconds is not null", (t0,)).fetchone()[0] or 0
    for g, n, ok, fb, secs, p50 in c.execute(
            "select gateway, count(*), sum(ok), sum(fallback), sum(seconds), avg(seconds) from gw where ts>=? group by 1",
            (t0,)):
        line = f"• gateway {g}: {n} llamadas, {ok} ok"
        if fb:
            line += f", {fb} en CPU por falta de GPU"
        line += f", {fmt_s(secs)} en total"
        if turn_total:
            line += f" ({100 * (secs or 0) / turn_total:.0f}% del tiempo de todos los turnos)"
        lines.append(line)
        if g == "transcode":
            gpu = c.execute("select sum(seconds), sum(mb_in) from gw where gateway='transcode' and fallback=0 and ok=1 and ts>=?",
                            (t0,)).fetchone()
            cpu = c.execute("select sum(seconds), sum(mb_in) from gw where gateway='transcode' and fallback=1 and ok=1",
                            ()).fetchone()
            if gpu[0] and gpu[1] and cpu[0] and cpu[1]:
                saved = gpu[1] * (cpu[0] / cpu[1]) - gpu[0]   # same MB at the CPU's measured s/MB, minus what GPU took
                lines.append(f"   la GPU ahorró ~{fmt_s(max(saved, 0))} frente a hacerlo en CPU (medido con los casos reales en CPU)")
        for host, err, k in c.execute("select host, error, count(*) from gw where gateway=? and ok=0 and ts>=? group by 1,2",
                                      (g, t0)):
            lines.append(f"   ⚠️ {k} fallas en {host or '?'}: {err}")
    for host, up, total in c.execute("select host, sum(up), count(*) from gwhost where ts>=? group by 1", (t0,)):
        lines.append(f"• host {host}: disponible {100 * up / total:.0f}% del tiempo")
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
                      "sum(case when failed=0 and tools=0 and seconds>? then 1 else 0 end) from turns where stack=? and ts>=?",
                      (SLOW_PLAIN_TURN_S, name, t0)).fetchone()
        add("failed", "turnos fallidos o sin respuesta", r[0] or 0, name)
        add("empty", "respuestas vacías", r[1] or 0, name)
        add("tool_errors", "herramientas que devolvieron error", r[2] or 0, name)
        add("slow", f"respuestas simples de más de {SLOW_PLAIN_TURN_S} s", r[3] or 0, name)
        for prov, code, n in c.execute("select provider, code, count(*) from errors where stack=? and ts>=? group by 1,2",
                                       (name, t0)):
            add(f"api:{prov}:{code}", f"errores {code} de {prov}", n, name)
        for g, k in c.execute("select gateway, count(*) from gw where stack=? and ts>=? and (ok=0 or fallback=1) group by 1",
                              (name, t0)):
            add(f"gw:{g}", f"gateway {g} sin su máquina (falló o cayó a CPU)", k, name)
        w = c.execute("select sum(case when outcome in ('timeout','no_memory') then 1 else 0 end), "
                      "sum(case when outcome='ok' and seconds>30 then 1 else 0 end) from wakes where stack=? and ts>=?",
                      (name, t0)).fetchone()
        add("wake_bad", "encendidos que fallaron (timeout o sin memoria)", w[0] or 0, name)
        add("wake_slow", "encendidos de más de 30 s", w[1] or 0, name)
    ranked = sorted(issues.values(), key=lambda e: e["n"] * len(e["who"]), reverse=True)
    return [f"  {i}. {e['label']}: {e['n']} ({', '.join(sorted(e['who']))})" for i, e in enumerate(ranked[:6], 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["collect", "report"])
    ap.add_argument("kind", nargs="?", default="daily", choices=["daily", "weekly"])
    ap.add_argument("--print", action="store_true", help="report: print instead of sending")
    a = ap.parse_args()
    stacks = json.load(open(STACKS))["stacks"]
    c = db()
    if a.cmd == "collect":
        collect(c, stacks)
    else:
        report(c, stacks, a.kind, a.print)
        if a.kind == "daily" and dt.datetime.now().weekday() == 0 and not a.print:
            report(c, stacks, "weekly", False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
