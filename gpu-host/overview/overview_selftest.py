#!/usr/bin/env python3
"""Offline checks for overview.py: a fake wake service, a fake bots' waker (/__wake/all), a fake gate and a fake Quake III server, all on
127.0.0.1. Checks that the bots' machine is never asked while it sleeps, that the waker's answer is reduced to the fields the page shows,
that every name is escaped, and the page's Spanish texts.
Run: python3 -I overview_selftest.py"""
import importlib.util, json, os, socket, sys, tempfile, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, got, want=True):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        fails.append(name)


NOW = int(time.time())
WAKE = {"bots": {"despierta": True, "visto": NOW, "proxima": None, "motivos": [],
                 "ultimo_despertar": {"t": NOW - 600, "motivo": "telegram:demo-a", "pedidos": 1, "tardo_s": 6}},
        "gpu": {"despierta": False, "visto": NOW - 3600, "proxima": NOW + 7200, "motivos": []}}
BOTS = {"ts": NOW, "mem_available_mb": 6144, "max_awake": 6, "awake": 2, "stacks": [
    {"name": "demo-a", "state": "awake", "web": False, "brain": True, "seen_s": 4, "idle_s": 30, "last_human_s": 40, "turn": True,
     "web_in_use": False, "busy": ["un turno del agente", "procesos en segundo plano"], "always": True, "always_suspended": False,
     "warm": True, "image": "c8bb2d3e348a", "update_pending": True, "next_cron_s": None, "chat": "SECRET CHAT TEXT"},
    {"name": "demo-b", "state": "asleep", "web": False, "brain": False, "seen_s": 400, "idle_s": None, "last_human_s": 7200,
     "turn": False, "web_in_use": False, "busy": [], "always": False, "always_suspended": False, "warm": False,
     "image": "<script>x</script>", "update_pending": False, "next_cron_s": 1800},
    {"name": "<b>demo-c</b>", "state": "hacked", "idle_s": "12", "turn": "yes", "busy": "x"},
    "not a row"]}
HITS = {"wake": 0, "bots": 0, "gate": 0}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/estado":
            HITS["wake"] += 1; data = WAKE
        elif p == "/__wake/all":
            HITS["bots"] += 1; data = BOTS
        elif p == "/host/overview":
            HITS["gate"] += 1; data = {"places": [], "host": {}}
        elif p.startswith("/slow"):   # a service that hangs (everything-down timing check)
            HITS["slow"] = HITS.get("slow", 0) + 1; time.sleep(6); data = {}
        else:
            self.send_response(404); self.end_headers(); return
        b = json.dumps(data).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake); srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
P = srv.server_address[1]

# a fake Quake III server: one statusResponse with two players (colour codes in one name)
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); udp.bind(("127.0.0.1", 0))
def q3():
    while True:
        try:
            data, addr = udp.recvfrom(2048)
        except OSError:
            return
        if data.startswith(b"\xff\xff\xff\xffgetstatus"):
            udp.sendto(b"\xff\xff\xff\xffstatusResponse\n\\mapname\\q3dm17\\sv_hostname\\LAN\\sv_maxclients\\8\n"
                       b"12 35 \"^1Ra^7ven\"\n-1 0 \"bot\"\n", addr)
threading.Thread(target=q3, daemon=True).start()

os.environ.update({"OVERVIEW_WAKE_URL": f"http://127.0.0.1:{P}/estado", "OVERVIEW_STACKS_URL": f"http://127.0.0.1:{P}/__wake/all",
                   "OVERVIEW_STACKS_MACHINE": "bots", "OVERVIEW_GATE_URL": "", "OVERVIEW_GAME_SERVERS": f"quake=127.0.0.1:{udp.getsockname()[1]},muerto=127.0.0.1:9"})
spec = importlib.util.spec_from_file_location("overview", os.path.join(HERE, "overview.py"))
ov = importlib.util.module_from_spec(spec); spec.loader.exec_module(ov)

# ---- machine awake: the waker is asked, its answer cleaned
d = ov.collect()
check("the waker is asked while its machine is awake", HITS["bots"], 1)
b = d["bots"]
check("rows that are not stacks are dropped", [s["name"] for s in b["stacks"]], ["demo-a", "demo-b", "<b>demo-c</b>"])
a = b["stacks"][0]
check("a turn, always, warm, a pending update and the short image come through", (a["turn"], a["always"], a["warm"], a["update_pending"], a["image"]),
      (True, True, True, True, "c8bb2d3e348a"))
check("fields the page does not show are dropped (never chat content)", "chat" in a or "SECRET" in json.dumps(d), False)
check("host numbers", (b["mem_available_mb"], b["max_awake"]), (6144, 6))
check("an image id that is not hex is dropped", b["stacks"][1]["image"], None)
c = b["stacks"][2]
check("an unknown state, a string number, a string flag and a string busy list are neutralised",
      (c["state"], c["idle_s"], c["turn"], c["busy"]), ("unknown", None, False, []))
m = d["machines"]["bots"]
check("the wake service's last wake: reason, when, how long", (m["last_wake"], m["last_wake_t"], m["last_wake_took_s"]), ("telegram:demo-a", NOW - 600, 6))
check("the next alarm of a sleeping machine", d["machines"]["gpu"]["next_alarm"], NOW + 7200)

# ---- Quake: players and colour codes
q = d["servers"][0]
check("the game server answers with map, max and players", (q["up"], q["map"], q["max"], len(q["players"])), (True, "q3dm17", "8", 2))
check("Quake colour codes stripped, score and ping read", q["players"][0], {"name": "Raven", "score": 12, "ping": 35, "bot": False})
check("ping 0 is a bot: counted apart from the people", (q["players"][1]["bot"], q["humans"], q["bots"]), (True, 1, 1))
check("the GPU host's name is in the data (empty when unset)", d["gpu_machine"], "")
check("a server that does not answer is down", d["servers"][1]["up"], False)

# ---- the page
h = ov.page(d)
check("bots heading with counts, machine and cap", "Bots · bots · 1 de 3 despiertos (máximo 6), 1 con un turno en curso" in h)
check("free memory line", "Memoria libre en la máquina: 6.0 GB" in h)
check("a turn shows as running, with the other busy reasons", "turno en curso" in h and "ocupado: procesos en segundo plano" in h)
check("always-on, warm, image and pending update", "despierto · siempre prendido · tibio" in h and "imagen c8bb2d3e348a" in h and "actualización pendiente" in h)
check("asleep stack: last chat, next cron and a stale snapshot", "dormido" in h and "última charla hace 2 h" in h and "próximo cron en 30 min" in h
      and "dato de hace 7 min" in h)
check("every stack name is escaped", "<b>demo-c</b>" not in h and "&lt;b&gt;demo-c&lt;/b&gt;" in h)
check("no raw script from another service", "<script>" in h, False)
check("machine card: last wake with time and duration", "último despertar hace 10 min: telegram:demo-a, tardó 6 s" in h)
check("machine card: a sleeping machine's own alarm", "se despierta sola a las " + time.strftime("%H:%M", time.localtime(NOW + 7200)) in h)
check("players listed", "Raven" in h and "q3dm17" in h)
check("people counted apart from bots, bots marked in the table", "q3dm17 · 1/8 jugadores · +1 bot ·" in h and "<td>bot (bot)</td>" in h)
check("a server with a person is highlighted", "<div class='card watched'><b>quake</b>" in h)
only_bots = ov.page({**d, "servers": [{"label": "solo", "addr": "a:1", "up": True, "map": "m", "max": "8", "humans": 0, "bots": 3,
                                        "players": [{"name": "Sarge", "score": 0, "ping": 0, "bot": True}] * 3}]})
check("only bots: 0 people, +3 bots, never highlighted as played", "m · 0/8 jugadores · +3 bots" in only_bots and "class='card watched'><b>solo" not in only_bots
      and "class='card on'><b>solo" in only_bots)

# ---- machine asleep: the waker is NOT asked, the page says why
WAKE["bots"]["despierta"] = False
before = HITS["bots"]
d = ov.collect()
check("the bots' machine asleep: the waker is never asked", HITS["bots"], before)
check("no bots data then", d["bots"], None)
check("the page says it is asleep and not woken", "La máquina de los bots está dormida (no se la despierta para mirar)" in ov.page(d))

# ---- machine awake but the waker does not answer
WAKE["bots"]["despierta"] = True
ov.STACKS = f"http://127.0.0.1:{P}/nothing"
d = ov.collect()
check("an awake machine whose waker does not answer", "El servicio que despierta los bots no responde." in ov.page(d))

# ---- without OVERVIEW_STACKS_URL nothing about bots, nothing asked
ov.STACKS = ""
before = HITS["bots"]
d = ov.collect()
check("no URL: no bots section, nothing asked", (d["bots_machine"], "<h2>Bots" in ov.page(d), HITS["bots"]), (None, False, before))

# ---- a named machine the wake service does not list: unknown, never asked
ov.STACKS = f"http://127.0.0.1:{P}/__wake/all"
ov.STACKS_MACHINE = "ghost"
ov.GATE, ov.GATE_MACHINE = f"http://127.0.0.1:{P}", "phantom"
tok = os.path.join(tempfile.mkdtemp(prefix="overview-selftest-"), "token")
try:
    open(tok, "w").write("x"); ov.TOKEN_FILE = tok
    before = dict(HITS)
    d = ov.collect()
finally:
    os.remove(tok)
check("a machine missing from the wake data: unknown, the waker and the gate are not asked",
      (d["bots_machine"], d["gpu_machine"], d["gpu_machine_awake"], d["bots"], d["gpu"], HITS["bots"] - before["bots"], HITS["gate"] - before["gate"]),
      ({"name": "ghost", "awake": None}, "phantom", None, None, None, 0, 0))
h = ov.page(d)
check("the page says the state is unknown, for the bots and the desktops",
      "La máquina de los bots: estado desconocido" in h and "La máquina de los escritorios: estado desconocido" in h)
ov.STACKS_MACHINE, ov.GATE, ov.GATE_MACHINE, ov.TOKEN_FILE = "bots", "", "", ""

# ---- everything down or hanging: the whole collect stays well under 5 s (queries run at the same time)
silent = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); silent.bind(("127.0.0.1", 0))   # bound, never answers
saved = (ov.WAKE, ov.STACKS, ov.STACKS_MACHINE, ov.GATE, ov.GATE_MACHINE, ov.TOKEN_FILE, ov.SERVERS)
tok = os.path.join(tempfile.mkdtemp(prefix="overview-selftest-"), "token")
try:
    open(tok, "w").write("x")
    ov.WAKE, ov.STACKS, ov.STACKS_MACHINE = f"http://127.0.0.1:{P}/slow/estado", f"http://127.0.0.1:{P}/slow/all", ""
    ov.GATE, ov.GATE_MACHINE, ov.TOKEN_FILE = f"http://127.0.0.1:{P}/slow", "", tok
    ov.SERVERS = [[f"s{i}", f"127.0.0.1:{silent.getsockname()[1]}"] for i in range(6)]
    t0 = time.monotonic(); d = ov.collect(); took = time.monotonic() - t0
finally:
    os.remove(tok)
    ov.WAKE, ov.STACKS, ov.STACKS_MACHINE, ov.GATE, ov.GATE_MACHINE, ov.TOKEN_FILE, ov.SERVERS = saved
check("everything hanging: the wake service, the waker, the gate and six silent game servers in under 4.5 s",
      (took < 4.5, d["machines"], d["bots"], d["gpu"], [s["up"] for s in d["servers"]]), (True, {}, None, None, [False] * 6))
print(f"     (took {took:.1f} s)")
t0 = time.monotonic(); r = ov.q3_status("127.0.0.1:9"); took = time.monotonic() - t0
check("a closed port fails at once (the socket is connected)", (r, took < 0.5), (None, True))

# ---- helpers
check("ago()", [ov.ago(x) for x in (5, 89, 90, 3599, 5400, 172799, 172800)], ["5 s", "89 s", "2 min", "60 min", "2 h", "48 h", "2 d"])
check("clean_bots on junk", (ov.clean_bots(None), ov.clean_bots({"stacks": "x"}), ov.clean_bots([])), (None, None, None))

# ---- the HTTP side: the page and the JSON
ov.STACKS = f"http://127.0.0.1:{P}/__wake/all"
web = ThreadingHTTPServer(("127.0.0.1", 0), ov.H); web.daemon_threads = True
threading.Thread(target=web.serve_forever, daemon=True).start()
with urllib.request.urlopen(f"http://127.0.0.1:{web.server_address[1]}/overview.json", timeout=10) as r:
    j = json.loads(r.read())
check("/overview.json carries the bots", [s["name"] for s in j["bots"]["stacks"]][:2], ["demo-a", "demo-b"])
with urllib.request.urlopen(f"http://127.0.0.1:{web.server_address[1]}/", timeout=10) as r:
    check("/ is the page, no-store", ("Vista general" in r.read().decode(), r.headers.get("Cache-Control")), (True, "no-store"))
try:
    urllib.request.urlopen(f"http://127.0.0.1:{web.server_address[1]}/x", timeout=10); code = 200
except urllib.error.HTTPError as e:
    code = e.code
check("anything else is 404", code, 404)

dp = {**d, "gpu": {"running": 0, "watched": 0, "host": {}, "places": [],
       "profile": {"gpu": "RTX <3060>", "vram_gb": 8.0, "rt": True, "driver": "595", "cpu": "Ryzen", "cores": 12, "ram_gb": 31, "disk_gb": 586, "disk_free_gb": 380},
       "installed": {"herkos": [{"name": "Quake <III>", "gb": 0.5}, {"name": "Control", "gb": 42}]}, "games_fit": [{"name": "Control", "fits": False, "missing": ["ray tracing"]}]}}
dp["gpu"] = ov.installed_counts(dp["gpu"])
hp = ov.page(dp)
check("the page shows the machine's profile, how many games each place has (never which: the page has no login) and which games fit, escaped",
      "con ray tracing" in hp and "RTX &lt;3060&gt;" in hp and "herkos 2 (42.5 GB)" in hp and "Quake" not in hp and "Control ✗ falta ray tracing" in hp and "<3060>" not in hp, True)
check("the JSON of the page carries counts only too", dp["gpu"]["installed"], {"herkos": {"games": 2, "gb": 42.5}})

print("ALL OK" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
