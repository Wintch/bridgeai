#!/usr/bin/env python3
"""overview.py: the operator's one page on the LAN: every machine, every desktop place, every game server. Stdlib only, read-only.

Runs on the always-on machine (the wake service's VM), bound to its LAN address only (never forwarded by the router). Each request asks:
  - the wake service's /estado: which machines are awake or asleep, when each last woke (why, how long it took) and the next alarm a
    machine set for itself (it never wakes anything);
  - the GPU gate's /host/overview with the host token (file OVERVIEW_GATE_TOKEN_FILE, 0600): the machine's load and every place (state, watchers,
    game, countdown, CPU, memory, VRAM), from the gate's last tick; skipped when that machine is asleep;
  - the bots' waker (aibridge/ops/wake/waker.py, "overview" in its stacks.json) at OVERVIEW_STACKS_URL (http://<bots host>:<port>/__wake/all):
    every Hermes stack's state (asleep, awake, starting...), idle time, a turn running, the person's last turn, the next cron wake and the
    short image id, from the waker's last tick; skipped while OVERVIEW_STACKS_MACHINE sleeps (never woken to look). Only the client address
    the waker allows gets an answer;
  - each game server in OVERVIEW_GAME_SERVERS ("name=host:port,..."), Quake III protocol (getstatus): map, players, score, ping (ping 0 is
    one of the server's own bots: counted apart, never as a person).
A machine named in OVERVIEW_STACKS_MACHINE or OVERVIEW_GATE_MACHINE that the wake service does not list (or a wake service that does not
answer) is in an unknown state: its service is not asked either. The wake service and the game servers are asked at the same time, then the
waker and the gate at the same time, each with a short timeout, so a page never takes more than about 4 s even with everything down.
The page refreshes itself every 15 s; /overview.json gives the same data. Place and stack names and numbers only: never chat content, names of
people's chats, files, windows or URLs.
"""
import html, json, os, re, socket, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN = os.environ.get("OVERVIEW_LISTEN", "127.0.0.1:8097")
WAKE = os.environ.get("OVERVIEW_WAKE_URL", "http://127.0.0.1:8090/estado")
GATE = os.environ.get("OVERVIEW_GATE_URL", "")                     # e.g. http://<gpu host>:8700
GATE_MACHINE = os.environ.get("OVERVIEW_GATE_MACHINE", "")         # its name in the wake service, to skip it while asleep
TOKEN_FILE = os.environ.get("OVERVIEW_GATE_TOKEN_FILE", "")
STACKS = os.environ.get("OVERVIEW_STACKS_URL", "")                 # e.g. http://<bots host>:8662/__wake/all
STACKS_MACHINE = os.environ.get("OVERVIEW_STACKS_MACHINE", "")     # the bots host's name in the wake service, to skip it while asleep
SERVERS = [s.split("=", 1) for s in os.environ.get("OVERVIEW_GAME_SERVERS", "").split(",") if "=" in s]
WAKE_S, ASK_S, GAME_S = 1.5, 2.0, 1.5   # seconds: the wake service, then the waker and the gate (together), the game servers (all along)


def get_json(url, token=None, timeout=ASK_S):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return None


def q3_status(addr, timeout=GAME_S):
    """{map, name, max, players: [{name, score, ping, bot}], humans, bots} from a Quake III server's getstatus, or None when it does not
    answer. A player with ping 0 is one of the server's own bots (bot True): listed, but counted apart from the people (humans).
    The socket is connected to the server: only its answer is read (the kernel drops a datagram from any other address) and a closed port
    fails at once (the ICMP error comes back on recv) instead of waiting the whole timeout."""
    host, _, port = addr.rpartition(":")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        s.send(b"\xff\xff\xff\xffgetstatus\n")
        lines = s.recv(65535).decode("latin-1").split("\n")
    except (OSError, ValueError):
        return None
    finally:
        s.close()
    if len(lines) < 2 or "statusResponse" not in lines[0]:
        return None
    kv = lines[1].split("\\")[1:]
    v = dict(zip(kv[::2], kv[1::2]))
    players = []
    for ln in lines[2:]:
        p = ln.split(" ", 2)
        if len(p) == 3 and p[0].lstrip("-").isdigit():
            name = re.sub(r"\^.", "", p[2].strip().strip('"'))          # Quake colour codes (^1, ^7 ...)
            ping = int(p[1]) if p[1].isdigit() else None
            players.append({"name": name[:32], "score": int(p[0]), "ping": ping, "bot": ping == 0})
    bots = sum(1 for p in players if p["bot"])
    return {"map": v.get("mapname"), "name": v.get("sv_hostname"), "max": v.get("sv_maxclients"), "players": players,
            "humans": len(players) - bots, "bots": bots}


def num(v):
    """An int, or None: the numbers of another service are shown, never trusted to be numbers."""
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


BOT_STATES = ("awake", "asleep", "starting", "queued", "updating", "stopping", "unknown")


def clean_bots(d):
    """The waker's /__wake/all reduced to the fields this page shows, each of the expected type (anything else is dropped)."""
    if not isinstance(d, dict) or not isinstance(d.get("stacks"), list):
        return None
    rows = []
    for s in d["stacks"]:
        if not isinstance(s, dict) or not isinstance(s.get("name"), str):
            continue
        rows.append({"name": s["name"][:40], "state": s.get("state") if s.get("state") in BOT_STATES else "unknown",
                     **{k: num(s.get(k)) for k in ("seen_s", "idle_s", "last_human_s", "next_cron_s")},
                     **{k: s.get(k) is True for k in ("turn", "web_in_use", "always", "always_suspended", "warm", "update_pending")},
                     "busy": [b[:60] for b in s.get("busy") or [] if isinstance(b, str)][:6] if isinstance(s.get("busy"), list) else [],
                     "image": s["image"][:12] if isinstance(s.get("image"), str) and re.fullmatch(r"[0-9a-f]{1,64}", s["image"]) else None})
    return {"mem_available_mb": num(d.get("mem_available_mb")), "max_awake": num(d.get("max_awake")), "awake": num(d.get("awake")), "stacks": rows}


def machine_awake(machines, name):
    """True or False from the wake service; None (unknown) for a named machine it does not list. No name: True (nothing to check)."""
    if not name:
        return True
    st = machines.get(name)
    return st.get("awake") if isinstance(st, dict) else None


def installed_counts(g):
    """This page has no login: which games each person has is not shown here (the gate gives titles to the host token only). Per place, only
    how many games and how many GB."""
    if isinstance(g, dict) and isinstance(g.get("installed"), dict):
        c = {}
        for n, gs in g["installed"].items():
            gs = [x for x in gs if isinstance(x, dict)] if isinstance(gs, list) else []
            c[str(n)] = {"games": len(gs), "gb": round(sum(x["gb"] for x in gs if isinstance(x.get("gb"), (int, float)) and not isinstance(x.get("gb"), bool)), 1)}
        g = {**g, "installed": c}
    return g


def gate_overview():
    try:
        token = open(TOKEN_FILE).read().strip() if TOKEN_FILE else ""
    except OSError:
        token = ""
    return get_json(GATE.rstrip("/") + "/host/overview", token) if token else None


def collect():
    out = {"ts": int(time.time()), "machines": {}, "gpu": None, "gpu_machine": GATE_MACHINE, "bots": None, "servers": []}
    with ThreadPoolExecutor(max_workers=min(16, 3 + len(SERVERS))) as pool:
        games = [(name, addr, pool.submit(q3_status, addr)) for name, addr in SERVERS]   # all along, they never depend on a machine's state
        wake = pool.submit(get_json, WAKE, None, WAKE_S).result() or {}
        for m, st in (wake.items() if isinstance(wake, dict) else ()):
            if isinstance(st, dict):
                last = st.get("ultimo_despertar") if isinstance(st.get("ultimo_despertar"), dict) else {}
                out["machines"][m] = {"awake": bool(st.get("despierta")), "seen": st.get("visto"), "last_wake": last.get("motivo"),
                                      "last_wake_t": num(last.get("t")), "last_wake_took_s": num(last.get("tardo_s")), "next_alarm": num(st.get("proxima"))}
        # a machine asleep, or in an unknown state, is never asked: a request must not be what keeps it, or makes it, awake
        bots_awake, gpu_awake = machine_awake(out["machines"], STACKS_MACHINE), machine_awake(out["machines"], GATE_MACHINE)
        bots = pool.submit(get_json, STACKS) if STACKS and bots_awake else None
        gate = pool.submit(gate_overview) if GATE and gpu_awake else None
        out["bots"] = clean_bots(bots.result()) if bots else None
        out["bots_machine"] = {"name": STACKS_MACHINE, "awake": bots_awake} if STACKS else None
        out["gpu_machine_awake"] = gpu_awake if GATE else None
        out["gpu"] = installed_counts(gate.result()) if gate else None
        for name, addr, f in games:
            st = f.result()
            out["servers"].append({"label": name, "addr": addr, "up": st is not None, **(st or {})})
    return out


CSS = """:root{--bg:#1c2233;--surface:#262d42;--line:#3a4360;--text:#ece8de;--muted:#9aa4b8;--amber:#f0b44c;--stop:#e06a5c;--ok:#7fc29b;
font:15px/1.45 Ubuntu,Cantarell,"Segoe UI",system-ui,sans-serif;color:var(--text);background:var(--bg)}
body{margin:0;padding:1.4rem;max-width:1200px;margin:auto}h1{font-size:1.6rem;font-weight:500;margin:0 0 .2rem}h2{font-size:1.1rem;font-weight:500;margin:1.4rem 0 .5rem;color:var(--muted)}
.st{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:.8rem}
.card{background:var(--surface);border-radius:12px;padding:.8rem 1rem;border-left:4px solid var(--line)}.card.on{border-left-color:var(--amber)}.card.watched{border-left-color:var(--ok)}
.card b{font-weight:500;font-size:1.05rem}.kv{color:var(--muted);font-size:.9rem;font-variant-numeric:tabular-nums}.warn{color:var(--stop)}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{text-align:left;padding:.25rem .6rem .25rem 0;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:400}"""


def ago(s):
    """Seconds as a short Spanish span: 45 s, 12 min, 5 h, 3 d."""
    s = max(0, int(s))
    return f"{s} s" if s < 90 else f"{round(s / 60)} min" if s < 5400 else f"{round(s / 3600)} h" if s < 172800 else f"{round(s / 86400)} d"


BOT_STATE_ES = {"awake": "despierto", "asleep": "dormido", "starting": "arrancando", "queued": "en cola para arrancar",
                "updating": "actualizando", "stopping": "apagándose", "unknown": "sin datos todavía"}


def bot_card(s):
    e = html.escape
    up = s["state"] in ("awake", "starting", "updating", "stopping")
    cls = "watched" if s["turn"] or s["web_in_use"] else "on" if up else ""
    head = BOT_STATE_ES[s["state"]] + (" · siempre prendido" if s["always"] and not s["always_suspended"] else "") + (" · tibio" if s["warm"] else "")
    lines = [head]
    if s["turn"]:
        lines.append("turno en curso")
    elif s["web_in_use"]:
        lines.append("usando la web")
    elif s["state"] == "awake" and s["idle_s"] is not None:
        lines.append(f"sin actividad hace {ago(s['idle_s'])}")
    other = [b for b in s["busy"] if b not in ("un turno del agente", "un turno reciente")]
    if other:
        lines.append("ocupado: " + e(", ".join(other)))
    if s["last_human_s"] is not None:
        lines.append(f"última charla hace {ago(s['last_human_s'])}")
    if s["next_cron_s"] is not None:
        lines.append(f"próximo cron en {ago(s['next_cron_s'])}")
    if s["image"]:
        lines.append(f"imagen {e(s['image'])}" + (" · <span class=warn>actualización pendiente</span>" if s["update_pending"] else ""))
    if s["seen_s"] is not None and s["seen_s"] > 120:
        lines.append(f"<span class=warn>dato de hace {ago(s['seen_s'])}</span>")
    return f"<div class='card {cls}'><b>{e(s['name'])}</b>" + "".join(f"<div class=kv>{x}</div>" for x in lines) + "</div>"


def machine_card(m, st, now):
    e = html.escape
    lines = ["despierta" if st["awake"] else "dormida"]
    if st.get("last_wake"):
        when = f" hace {ago(now - st['last_wake_t'])}" if st.get("last_wake_t") else ""
        took = f", tardó {st['last_wake_took_s']} s" if st.get("last_wake_took_s") is not None else ""
        lines.append(f"último despertar{when}: {e(str(st['last_wake']))}{took}")
    if st.get("next_alarm") and not st["awake"] and st["next_alarm"] > now:
        lines.append("se despierta sola a las " + time.strftime("%H:%M", time.localtime(st["next_alarm"])))
    return f"<div class='card{' on' if st['awake'] else ''}'><b>{e(m)}</b>" + "".join(f"<div class=kv>{x}</div>" for x in lines) + "</div>"


def page(d):
    e = html.escape
    t = time.strftime("%H:%M:%S", time.localtime(d["ts"]))
    body = f"<h1>Vista general</h1><p class=st>Actualizado {t} · se refresca cada 15 s · <a href=/overview.json style='color:var(--amber)'>JSON</a></p>"
    body += "<h2>Máquinas</h2><div class=grid>"
    for m, st in d["machines"].items():
        body += machine_card(m, st, d["ts"])
    body += "</div>"
    bm, b = d.get("bots_machine"), d.get("bots")
    if bm:
        where = f" · {e(bm['name'])}" if bm.get("name") else ""
        if b:
            n = sum(1 for s in b["stacks"] if s["state"] in ("awake", "starting", "updating", "stopping"))
            turns = sum(1 for s in b["stacks"] if s["turn"])
            mem = f"<p class=kv>Memoria libre en la máquina: {round(b['mem_available_mb'] / 1024, 1)} GB</p>" if b.get("mem_available_mb") is not None else ""
            cap = f" (máximo {b['max_awake']})" if b.get("max_awake") is not None else ""
            body += (f"<h2>Bots{where} · {n} de {len(b['stacks'])} despiertos{cap}, {turns} con un turno en curso</h2>"
                     f"{mem}<div class=grid>" + "".join(bot_card(s) for s in b["stacks"]) + "</div>")
        elif bm["awake"] is None:
            body += f"<h2>Bots{where}</h2><p class=st>La máquina de los bots: estado desconocido (el servicio que despierta las máquinas no la conoce o no responde; no se la consulta).</p>"
        elif not bm["awake"]:
            body += f"<h2>Bots{where}</h2><p class=st>La máquina de los bots está dormida (no se la despierta para mirar): cada bot se despierta solo cuando le escriben.</p>"
        else:
            body += f"<h2>Bots{where}</h2><p class=st>El servicio que despierta los bots no responde.</p>"
    g = d.get("gpu")
    if g and g.get("places") is not None:
        h = g.get("host") or {}
        body += (f"<h2>Escritorios · {g.get('running', 0)} prendidos, {g.get('watched', 0)} con alguien mirando</h2>"
                 f"<p class=kv>Máquina: CPU {h.get('cpu_pct', '…')}% · memoria {h.get('mem_used_gb', '?')}/{h.get('mem_total_gb', '?')} GB · placa {h.get('gpu_pct', '?')}% · "
                 f"video {round(float(h.get('vram_used_mb') or 0) / 1024, 1)}/{round(float(h.get('vram_total_mb') or 0) / 1024, 1)} GB</p><div class=grid>")
        for p in g["places"]:
            cls = "watched" if p.get("running") and (p.get("viewers") or 0) > 0 else "on" if p.get("running") else ""
            if p.get("running"):
                who = f"{p.get('viewers') or 0} mirando" + (" · juego abierto" if p.get("game_open") else "") + (" · sonido" if p.get("sound") else "")
                left = f"se apaga en {p.get('closes_in_min')} min" if p.get("closes_in_min") is not None else ""
                res = f"CPU {p.get('cpu_pct', '?')}% · {p.get('mem_mb', '?')} MB · VRAM {p.get('vram_mb', '?')} MB"
                extra = (" · <span class=warn>avisado</span>" if p.get("warned") else "") + (" · retenido" if p.get("held") else "")
                prep = f"<div class=kv>shaders: {e(str((p.get('prep') or {}).get('name') or ''))} {(p.get('prep') or {}).get('pct', '')}%</div>" if p.get("prep") else ""
                body += f"<div class='card {cls}'><b>{e(p['place'])}</b><div class=kv>{who}</div><div class=kv>{left}{extra}</div><div class=kv>{res}</div>{prep}</div>"
            else:
                why = {"idle": "apagado por inactividad", "person": "apagado por la persona"}.get(p.get("closed_reason") or "", "apagado")
                body += f"<div class='card'><b>{e(p['place'])}</b><div class=kv>{why}</div></div>"
        body += "</div>"
        pr = g.get("profile") if isinstance(g.get("profile"), dict) else {}
        if pr:
            rt = {True: "con ray tracing", False: "sin ray tracing"}.get(pr.get("rt"), "ray tracing ?")
            body += (f"<p class=kv>Perfil: {e(str(pr.get('gpu', '?')))} · {e(str(pr.get('vram_gb', '?')))} GB de video · {rt} · driver {e(str(pr.get('driver', '?')))} · "
                     f"{e(str(pr.get('cpu', '?')))} ({e(str(pr.get('cores', '?')))} hilos) · {e(str(pr.get('ram_gb', '?')))} GB · "
                     f"disco de escritorios {e(str(pr.get('disk_free_gb', '?')))}/{e(str(pr.get('disk_gb', '?')))} GB libres</p>")
        inst = g.get("installed") if isinstance(g.get("installed"), dict) else {}
        rows = [(n, c) for n, c in sorted(inst.items()) if isinstance(c, dict) and c.get("games")]
        if rows:
            body += "<p class=kv>Juegos instalados: " + " · ".join(f"{e(str(n))} {e(str(c.get('games')))} ({e(str(c.get('gb')))} GB)" for n, c in rows) + "</p>"
        fits = [x for x in (g.get("games_fit") or []) if isinstance(x, dict)]
        if fits:
            body += "<p class=kv>Perfiles de juego en esta máquina: " + " · ".join(
                e(str(x.get("name", "?"))) + (" ✓" if x.get("fits") else " ✗ falta " + e(", ".join(str(m) for m in (x.get("missing") or []))))
                for x in fits) + "</p>"
    elif d.get("gpu_machine_awake") is None and d.get("gpu_machine"):
        body += "<h2>Escritorios</h2><p class=st>La máquina de los escritorios: estado desconocido (el servicio que despierta las máquinas no la conoce o no responde; no se la consulta).</p>"
    else:
        body += "<h2>Escritorios</h2><p class=st>La máquina de los escritorios está dormida o no responde.</p>"
    body += "<h2>Servidores de juego</h2>"
    for s in d["servers"]:
        if not s["up"]:
            body += f"<div class=card><b>{e(s['label'])}</b><div class=kv>no responde ({e(s['addr'])})</div></div>"
            continue
        humans, bots = s.get("humans") or 0, s.get("bots") or 0   # people only: bots (ping 0) never light the card
        more = f" · +{bots} bot{'' if bots == 1 else 's'}" if bots else ""
        body += (f"<div class='card{' watched' if humans else ' on'}'><b>{e(s['label'])}</b> <span class=kv>{e(str(s.get('name') or ''))}</span>"
                 f"<div class=kv>{e(str(s.get('map')))} · {humans}/{e(str(s.get('max')))} jugadores{more} · {e(s['addr'])}</div>")
        if s.get("players"):
            body += "<table><tr><th>Jugador</th><th>Puntos</th><th>Ping</th></tr>" + "".join(
                f"<tr><td>{e(pl['name'])}{' (bot)' if pl.get('bot') else ''}</td><td>{pl['score']}</td><td>{pl['ping'] if pl['ping'] is not None else ''}</td></tr>"
                for pl in s["players"]) + "</table>"
        body += "</div>"
    return f"<!doctype html><html lang=es><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><meta http-equiv=refresh content=15><title>Vista general</title><style>{CSS}</style></head><body>{body}</body></html>"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/", "/overview.json"):
            return self._send(404, b"not found", "text/plain")
        d = collect()
        if path == "/overview.json":
            return self._send(200, json.dumps(d).encode(), "application/json")
        return self._send(200, page(d).encode(), "text/html; charset=utf-8")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)


def main():
    host, _, port = LISTEN.rpartition(":")
    srv = ThreadingHTTPServer((host, int(port)), H)
    print(f"overview on {LISTEN}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
