#!/usr/bin/env python3
"""overview.py: the operator's one page on the LAN: every machine, every desktop place, every game server. Stdlib only, read-only.

Runs on the always-on machine (the wake service's VM), bound to its LAN address only (never forwarded by the router). Each request asks:
  - the wake service's /estado: which machines are awake or asleep (it never wakes anything);
  - the GPU gate's /host/overview with the host token (file OVERVIEW_GATE_TOKEN_FILE, 0600): the machine's load and every place (state, watchers,
    game, countdown, CPU, memory, VRAM), from the gate's last tick; skipped when that machine is asleep;
  - each game server in OVERVIEW_GAME_SERVERS ("name=host:port,..."), Quake III protocol (getstatus): map, players, score, ping.
The page refreshes itself every 15 s; /overview.json gives the same data. Place names and numbers only: never files, windows or URLs.
"""
import html, json, os, re, socket, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN = os.environ.get("OVERVIEW_LISTEN", "127.0.0.1:8097")
WAKE = os.environ.get("OVERVIEW_WAKE_URL", "http://127.0.0.1:8090/estado")
GATE = os.environ.get("OVERVIEW_GATE_URL", "")                     # e.g. http://<gpu host>:8700
GATE_MACHINE = os.environ.get("OVERVIEW_GATE_MACHINE", "")         # its name in the wake service, to skip it while asleep
TOKEN_FILE = os.environ.get("OVERVIEW_GATE_TOKEN_FILE", "")
SERVERS = [s.split("=", 1) for s in os.environ.get("OVERVIEW_GAME_SERVERS", "").split(",") if "=" in s]


def get_json(url, token=None, timeout=4):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return None


def q3_status(addr, timeout=2.0):
    """{map, name, max, players: [{name, score, ping}]} from a Quake III server's getstatus, or None when it does not answer."""
    host, _, port = addr.rpartition(":")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(b"\xff\xff\xff\xffgetstatus\n", (host, int(port)))
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
            players.append({"name": name[:32], "score": int(p[0]), "ping": int(p[1]) if p[1].isdigit() else None})
    return {"map": v.get("mapname"), "name": v.get("sv_hostname"), "max": v.get("sv_maxclients"), "players": players}


def collect():
    wake = get_json(WAKE) or {}
    out = {"ts": int(time.time()), "machines": {}, "gpu": None, "servers": []}
    for m, st in wake.items():
        if isinstance(st, dict):
            out["machines"][m] = {"awake": bool(st.get("despierta")), "seen": st.get("visto"), "last_wake": (st.get("ultimo_despertar") or {}).get("motivo") if isinstance(st.get("ultimo_despertar"), dict) else None}
    awake = out["machines"].get(GATE_MACHINE, {}).get("awake", True) if GATE_MACHINE else True
    if GATE and awake:
        try:
            token = open(TOKEN_FILE).read().strip() if TOKEN_FILE else ""
        except OSError:
            token = ""
        out["gpu"] = get_json(GATE.rstrip("/") + "/host/overview", token) if token else None
    for name, addr in SERVERS:
        st = q3_status(addr)
        out["servers"].append({"label": name, "addr": addr, "up": st is not None, **(st or {})})
    return out


CSS = """:root{--bg:#1c2233;--surface:#262d42;--line:#3a4360;--text:#ece8de;--muted:#9aa4b8;--amber:#f0b44c;--stop:#e06a5c;--ok:#7fc29b;
font:15px/1.45 Ubuntu,Cantarell,"Segoe UI",system-ui,sans-serif;color:var(--text);background:var(--bg)}
body{margin:0;padding:1.4rem;max-width:1200px;margin:auto}h1{font-size:1.6rem;font-weight:500;margin:0 0 .2rem}h2{font-size:1.1rem;font-weight:500;margin:1.4rem 0 .5rem;color:var(--muted)}
.st{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:.8rem}
.card{background:var(--surface);border-radius:12px;padding:.8rem 1rem;border-left:4px solid var(--line)}.card.on{border-left-color:var(--amber)}.card.watched{border-left-color:var(--ok)}
.card b{font-weight:500;font-size:1.05rem}.kv{color:var(--muted);font-size:.9rem;font-variant-numeric:tabular-nums}.warn{color:var(--stop)}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{text-align:left;padding:.25rem .6rem .25rem 0;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:400}"""


def page(d):
    e = html.escape
    t = time.strftime("%H:%M:%S", time.localtime(d["ts"]))
    body = f"<h1>Vista general</h1><p class=st>Actualizado {t} · se refresca cada 15 s · <a href=/overview.json style='color:var(--amber)'>JSON</a></p>"
    body += "<h2>Máquinas</h2><div class=grid>"
    for m, st in d["machines"].items():
        body += f"<div class='card{' on' if st['awake'] else ''}'><b>{e(m)}</b><div class=kv>{'despierta' if st['awake'] else 'dormida'}" + (f" · último despertar: {e(str(st['last_wake']))}" if st.get("last_wake") else "") + "</div></div>"
    body += "</div>"
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
    else:
        body += "<h2>Escritorios</h2><p class=st>La máquina de los escritorios está dormida o no responde.</p>"
    body += "<h2>Servidores de juego</h2>"
    for s in d["servers"]:
        if not s["up"]:
            body += f"<div class=card><b>{e(s['label'])}</b><div class=kv>no responde ({e(s['addr'])})</div></div>"
            continue
        body += (f"<div class='card{' watched' if s.get('players') else ' on'}'><b>{e(s['label'])}</b> <span class=kv>{e(str(s.get('name') or ''))}</span>"
                 f"<div class=kv>{e(str(s.get('map')))} · {len(s.get('players') or [])}/{e(str(s.get('max')))} jugadores · {e(s['addr'])}</div>")
        if s.get("players"):
            body += "<table><tr><th>Jugador</th><th>Puntos</th><th>Ping</th></tr>" + "".join(
                f"<tr><td>{e(pl['name'])}</td><td>{pl['score']}</td><td>{pl['ping'] if pl['ping'] is not None else ''}</td></tr>" for pl in s["players"]) + "</table>"
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
