#!/usr/bin/env python3
"""Offline checks for `gateway pref`/`gateway speak` voice choice, `gateway estado`/`gateway ayuda`, and the Hermes patches
patches/quick_command_args.py, patches/reply_language.py (2026-10-17) and patches/help_menu.py (2026-10-22). Run: python3 -I gateway_pref_selftest.py
The patches are checked on tiny stand-ins that contain the exact lines they replace; a build against the real Hermes commit
is what proves they still match (they abort loudly when they do not)."""
import importlib.util, json, os, subprocess, sys, tempfile, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
os.environ.update(GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log")
json.dump({"tts_voice": "alice-{lang}", "tts_voices": ["alice-ru", "alice-es", "../evil", "bad name"]}, open(f"{tmp}/gw.json", "w"))
spec = importlib.util.spec_from_file_location("gw", f"{HERE}/gateway.py")
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)

fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")

check("choices skip unsafe names", gw.voice_choices(), ["auto", "default", "alice-ru", "alice-es"])
check("auto by language es", gw.voice_for("hola como estas amigo"), "alice-es")
check("auto by language ru", gw.voice_for("привет, как дела"), "alice-ru")
gw.save_prefs({"voice": "alice-ru"}); check("pick", gw.voice_for("hello how are you"), "alice-ru")
gw.save_prefs({"voice": "default"}); check("default voice", gw.voice_for("hola"), "default")
gw.save_prefs({"voice": "gone"});    check("stale pick falls back to the template", gw.voice_for("hello how are you"), "alice-en")
gw.save_prefs({"voice": "../etc"});  check("path-like pick ignored", gw.voice_for("hello how are you"), "alice-en")
gw.CONF = f"{tmp}/none.json"
gw.save_prefs({"voice": "alice-ru"}); check("no config: never another person's clip", gw.voice_for("hola"), "default")
gw.CONF = f"{tmp}/gw.json"

def pref(*a):
    r = subprocess.run([sys.executable, "-I", f"{HERE}/gateway.py", "pref", *a], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()
os.unlink(f"{tmp}/prefs.json")
check("bad lang", pref("lang", "xx")[0], 1)
check("set lang", pref("lang", "ru")[0], 0)
check("lang stored", json.load(open(f"{tmp}/prefs.json"))["lang"], "ru")
check("bad voice", pref("voice", "nope")[0], 1)
check("voice case-insensitive", pref("voice", "ALICE-ES")[0], 0)
check("voice stored", json.load(open(f"{tmp}/prefs.json"))["voice"], "alice-es")
check("lang back to auto", pref("lang", "auto")[0], 0)

# patches on stand-ins
inbound = f"{tmp}/run_inbound.py"
open(inbound, "w").write(textwrap.dedent('''\
    class G:
        async def f(self, event, command, qcmd):
            if qcmd is not None:
                if qcmd.get("type") == "exec":
                    exec_cmd = qcmd.get("command", "")
                    if not exec_cmd:
                        return True, "no", command
                    return True, await self._hm_run_exec_quick_command(command, exec_cmd), command
    '''))
for _ in range(2):   # the second run must be a no-op
    subprocess.run([sys.executable, f"{HERE}/patches/quick_command_args.py", inbound], check=True, capture_output=True)
ns = {}
exec(open(inbound).read(), ns)
class E:
    def __init__(s, a): s.a = a
    def get_command_args(s): return s.a
class H(ns["G"]):
    async def _hm_run_exec_quick_command(self, c, cmd): return cmd
import asyncio
run = lambda a: asyncio.run(H().f(E(a), "idioma", {"type": "exec", "command": "gateway pref lang"}))[1]
check("args appended", run("ru"), "gateway pref lang ru")
check("shell metacharacters quoted", run("ru; rm -rf /"), "gateway pref lang 'ru;' rm -rf /")
check("no args", run(""), "gateway pref lang")
check("at most 4 words", run("a b c d e f"), "gateway pref lang a b c d")

mt = f"{tmp}/message_timestamps.py"
open(mt, "w").write("import re\n" + textwrap.dedent('''\
    def strip_leading_message_timestamps(content, tz=None):
        text, embedded_epoch = content, None
        while (match := re.match(r"\\[ts\\] ", text)) is not None:
            text = text[match.end():]
        return text, embedded_epoch


    def render_user_content_with_timestamp(content, ts_value=None):
        clean_content, _ = strip_leading_message_timestamps(content)
        prefix = "[ts]"
        return f"{prefix} {clean_content}" if prefix and clean_content else (prefix or clean_content)
    '''))
for _ in range(2):
    subprocess.run([sys.executable, f"{HERE}/patches/reply_language.py", mt], check=True, capture_output=True)
ns = {}
exec(open(mt).read(), ns)
json.dump({"lang": "ru"}, open(f"{tmp}/prefs.json", "w"))
check("hint added", ns["render_user_content_with_timestamp"]("hola"), "[ts] [reply in Russian] hola")
r = ns["render_user_content_with_timestamp"]
check("rendering a rendered message adds no second hint", r(r(r("hola"))), "[ts] [reply in Russian] hola")
check("a stored stack of hints is stripped", r("[ts] [reply in Russian] [reply in Russian] [reply in Russian] hola"), "[ts] [reply in Russian] hola")
json.dump({"lang": "auto"}, open(f"{tmp}/prefs.json", "w")); os.utime(f"{tmp}/prefs.json", (1e9, 1e9 + 7))
check("auto adds nothing", ns["render_user_content_with_timestamp"]("hola"), "[ts] hola")
# never chose (no prefs file): the stack's own language in gateways.json; none there, nothing
_prefs, _gw = os.environ.get("AIBRIDGE_PREFS"), os.environ.get("GATEWAYS_CONFIG")
os.environ["AIBRIDGE_PREFS"], os.environ["GATEWAYS_CONFIG"] = f"{tmp}/no-prefs.json", f"{tmp}/gw-lang.json"
json.dump({"lang": "ru", "llm": []}, open(f"{tmp}/gw-lang.json", "w"))
check("no /idioma choice: the stack's configured language", r("hola"), "[ts] [reply in Russian] hola")
json.dump({"llm": []}, open(f"{tmp}/gw-lang.json", "w")); os.utime(f"{tmp}/gw-lang.json", (1e9, 1e9 + 9))
check("no choice and no stack language: nothing", r("hola"), "[ts] hola")
for _k, _v in (("AIBRIDGE_PREFS", _prefs), ("GATEWAYS_CONFIG", _gw)):
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v

# `gateway estado` (/estado): one line per thing the person can do, from the same health checks the tools use
import contextlib, io, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Ok(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")


srv = ThreadingHTTPServer(("127.0.0.1", 0), Ok)
threading.Thread(target=srv.serve_forever, daemon=True).start()
UP, DOWN = f"http://127.0.0.1:{srv.server_port}", "http://127.0.0.1:9"


def estado(cfg, model="local-first", keys=(), lang=None, prefs_lang=None):
    json.dump(cfg, open(f"{tmp}/gw.json", "w"))
    json.dump({"lang": prefs_lang} if prefs_lang else {}, open(f"{tmp}/prefs.json", "w"))
    gw.hermes_get = lambda k: {"model.default": model, "timezone": "America/Argentina/Buenos_Aires"}[k]
    gw.env_key = lambda var: "k" if var in keys else ""
    gw.groq_key = lambda: "k" if "GROQ_API_KEY" in keys else ""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        gw.cmd_estado([lang] if lang else [])
    return out.getvalue()


ALL = lambda url: {"llm": [{"name": "gpu-desktop", "url": url, "model": "gemma-4-e4b"}], "stt": [{"name": "gpu-desktop", "url": url}],
                   "tts": [{"name": "gpu-hq", "url": url}], "transcode": [{"name": "gpu-desktop", "url": url}],
                   "upscale": [{"name": "gpu-desktop", "url": url}]}
E = gw.ESTADO["es"]
o = estado(ALL(UP))
check("estado home up: chat at home", E["chat_home"].format(m="gemma-4-e4b", h="gpu-desktop") in o, True)
check("estado home up: every line ✅", [ln[0] for ln in o.splitlines()[1:7]], ["✅"] * 6)
o = estado(ALL(DOWN), keys=("NVIDIA_API_KEY", "GROQ_API_KEY"))
check("estado home down: chat asks for the cloud", E["chat_down"] in o, True)
check("estado home down: voice notes on Groq", E["stt_groq"] in o, True)
check("estado home down: video on the server CPU", E["tc_cpu"] in o, True)
check("estado home down: no upscale", E["up_none"] in o, True)
check("estado home down, no keys", (E["chat_nokey"] in o, E["stt_none"] in estado(ALL(DOWN))), (False, True))
check("estado home down, no cloud key", E["chat_nokey"] in estado(ALL(DOWN)), True)
o = estado(ALL(UP), model="nvidia/nemotron-3.5-super-vl-120b-a12b")
check("estado cloud model: chat in the cloud", E["chat_cloud"].format(m="nvidia/nemotron-3.5-super-vl-120b-a12b") in o, True)
check("estado unknown model: no chat line", "Chat" in estado(ALL(UP), model=""), False)
check("estado only what the stack has", "Mejorar" in estado({"llm": ALL(UP)["llm"]}), False)
# cloud_direct (2026-10-30): no home model, so no "PC de casa" or 🔒 line; the router says the mode and the models
gw.router_state = lambda: {"mode": "best", "order": ["NVIDIA nemotron-3.5-super", "Token Harbor deepseek-v4.1-flash", "NVIDIA gpt-oss-20b"]}
o = estado({"cloud_direct": True}, keys=("NVIDIA_API_KEY",))
check("estado direct: first model and fallbacks", E["chat_direct"].format(m="NVIDIA nemotron-3.5-super",
      rest="Token Harbor deepseek-v4.1-flash, NVIDIA gpt-oss-20b") in o and "🔒" not in o and "PC de casa" not in o, True)
gw.router_state = lambda: {"mode": "explore", "order": ["A", "B"], "current": "B"}
check("estado explore: the model this conversation uses", E["chat_explore"].format(m="B") in estado({"cloud_direct": True}), True)
gw.router_state = lambda: {}
check("estado direct, router down: says it cannot answer", E["chat_nokey"] in estado({"cloud_direct": True}), True)
check("estado language from /idioma", estado(ALL(UP), prefs_lang="ru").splitlines()[0].startswith("Состояние"), True)
check("estado language argument wins", estado(ALL(UP), prefs_lang="ru", lang="en").splitlines()[0].startswith("Status now"), True)
t0 = time.time(); estado(ALL("http://10.255.255.1:9"))
check("estado: hosts that never answer are checked at once (~2 s)", time.time() - t0 < 4, True)
check("estado: same keys in every language", {k: sorted(v) for k, v in gw.ESTADO.items()},
      {k: sorted(gw.ESTADO["es"]) for k in gw.ESTADO})

# `gateway ayuda` (/help and the Telegram menu, 2026-10-22) and patches/help_menu.py on stand-ins
import re
def ayuda(argv, cfg, prefs_lang=None):
    json.dump(cfg, open(f"{tmp}/gw.json", "w"))
    json.dump({"lang": prefs_lang} if prefs_lang else {}, open(f"{tmp}/prefs.json", "w"))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        gw.cmd_ayuda(argv)
    return out.getvalue()


o = ayuda([], {})
check("ayuda: our commands", all(f"/{c}" in o for c in ("estado", "idioma", "voz", "btw", "new")), True)
check("ayuda: no Zabbix without a token", "/mon" in o, False)
check("ayuda: Zabbix on a stack that has it", "/mon" in ayuda([], {"zabbix": {"url": "u", "token": "t"}}), True)
check("ayuda: points to the full list", o.rstrip().endswith("/commands"), True)
menu = [ln.split("\t") for ln in ayuda(["--menu"], {"zabbix": {"url": "u", "token": "t"}}).splitlines()]
check("ayuda menu: name<TAB>description, Telegram-valid names",
      all(len(x) == 2 and re.fullmatch(r"[a-z0-9_]{1,32}", x[0]) and 0 < len(x[1]) <= 256 for x in menu), True)
check("ayuda menu: /help last", menu[-1][0], "help")
check("ayuda language: /idioma first", ayuda(["--lang"], {"lang": "en"}, prefs_lang="ru").strip(), "ru")
check("ayuda language: the stack's lang when /idioma is auto", ayuda(["--lang"], {"lang": "ru"}, prefs_lang="auto").strip(), "ru")
check("ayuda language: Spanish by default", ayuda(["--lang"], {}).strip(), "es")
check("ayuda: same keys in every language", {k: sorted(v) for k, v in gw.AYUDA.items()}, {k: sorted(gw.AYUDA["es"]) for k in gw.AYUDA})
check("ayuda: every listed command has a text", all(c in gw.AYUDA["es"] for c in gw.AYUDA_ORDER + gw.AYUDA_ZBX + ("help",)), True)

bindir = f"{tmp}/bin"; os.makedirs(bindir)
open(f"{bindir}/gateway", "w").write("#!/bin/sh\n[ \"$2\" = --menu ] && printf 'estado\\tqué anda\\nhelp\\testa ayuda\\n' || echo AYUDA-BRIDGEAI\n")
os.chmod(f"{bindir}/gateway", 0o755)
sc, cp = f"{tmp}/slash_commands.py", f"{tmp}/commands_platforms.py"
open(sc, "w").write(textwrap.dedent('''\
    import asyncio
    def _execute(c, options=None):
        class R: text = "HERMES-HELP"
        return R()
    def _preview(text: str, limit: int = 60) -> str:
        return text
    class S:
        def _catalog_options(self, event): return {}
        def _telegramized_command_reply(self, event, text): return text
        async def _handle_help_command(self, event: MessageEvent) -> str:
            """Handle /help command - list available commands."""
            return self._telegramized_command_reply(
                event, _execute("help", options=self._catalog_options(event)).text)
    ''').replace("event: MessageEvent", "event"))
open(cp, "w").write(textwrap.dedent('''\
    def telegram_bot_commands(include_plugins=True): return [("help", "h"), ("kanban", "k")]
    def _collect_gateway_skill_entries(platform, **k): return [], 0
    def _normalize_telegram_desc(d): return d
    def telegram_menu_commands(max_commands: int = 100) -> tuple:
        core_commands = list(telegram_bot_commands(include_plugins=False))
        entries, hidden_count = _collect_gateway_skill_entries(
            platform="telegram", max_slots=None)
        return core_commands, hidden_count
    '''))
for _ in range(2):
    subprocess.run([sys.executable, f"{HERE}/patches/help_menu.py", sc, cp], check=True, capture_output=True)
class Ev:
    def __init__(s, a=""): s.a = a
    def get_command_args(s): return s.a
for with_gateway in (True, False):
    os.environ["PATH"] = (bindir + os.pathsep if with_gateway else "") + "/usr/bin:/bin"
    ns = {}; exec(open(sc).read(), ns); nm = {}; exec(open(cp).read(), nm)
    want = ("AYUDA-BRIDGEAI", [("estado", "qué anda"), ("help", "esta ayuda")]) if with_gateway else ("HERMES-HELP", [("help", "h"), ("kanban", "k")])
    check(f"help_menu patch, gateway {'present' if with_gateway else 'missing'}",
          (asyncio.run(ns["S"]()._handle_help_command(Ev())), nm["telegram_menu_commands"]()[0]), want)
os.environ["PATH"] = bindir + os.pathsep + "/usr/bin:/bin"
check("help_menu patch: /help <filter> keeps Hermes's catalog", asyncio.run(ns["S"]()._handle_help_command(Ev("model"))), "HERMES-HELP")

# gateway bajar (2026-10-31): every item at once, a summary, a status file, and no download while the disk is short
import io, contextlib, tempfile
dl = tempfile.mkdtemp()
fake = tempfile.mkdtemp()
open(f"{fake}/yt-dlp", "w").write('#!/bin/sh\nsleep 1\nfor a; do last="$a"; done\nf="%s/$(echo "$last" | tr -c "a-z0-9\\n" _).mp4"\n'
                                 'head -c 2048 /dev/zero > "$f"; echo "$f"\n' % dl)
open(f"{fake}/aria2c", "w").write('#!/bin/sh\nsleep 1\nfor a; do case "$a" in --dir=*) d="${a#--dir=}";; esac; done\n'
                                 'mkdir -p "$d/Peli"; head -c 2097152 /dev/zero > "$d/Peli/peli.mkv"\n')
os.chmod(f"{fake}/yt-dlp", 0o755); os.chmod(f"{fake}/aria2c", 0o755)
os.environ["PATH"] = fake + os.pathsep + os.environ["PATH"]
gw.DL_DIR, gw.DL_MIN_FREE = dl, 0
t0, buf = time.time(), io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = gw.cmd_bajar(["https://youtu.be/a", "buscar:trailer b", "magnet:?xt=urn:btih:00", "https://youtu.be/c"])
check("bajar: four downloads in parallel take about one, not four", (rc, time.time() - t0 < 3.5), (0, True))
check("bajar: the summary lists every file", buf.getvalue().count("    " + dl), 4)
st = [json.loads(l) for l in open(f"{dl}/.bajar.jsonl")]
check("bajar: status file, one start and one end per item", sorted(r["state"] for r in st), ["bajando"] * 4 + ["lista"] * 4)
check("bajar: a torrent is measured by its folder", [r["mb"] for r in st if r["kind"] == "torrent" and r["state"] == "lista"], [2.0])
gw.DL_MIN_FREE = 1e18
with contextlib.redirect_stdout(io.StringIO()):
    check("bajar: a disk under the minimum refuses to start", gw.cmd_bajar(["https://youtu.be/d"]), 1)
check("bajar: and says why", json.loads(open(f"{dl}/.bajar.jsonl").readlines()[-1])["state"], "sin espacio")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    gw.cmd_bajar(["estado"])
check("bajar estado: one line per download and the free space", (buf.getvalue().count("lista"), "libre en disco" in buf.getvalue()), (4, True))

# gateway mapa (2026-10-31): checked places, a keyless fallback for every part (Photon then Nominatim, FOSSGIS OSRM, a
# picture drawn here from OSM tiles), transit only as a link, no coordinates or place names in the log
import http.server, threading, urllib.parse
from PIL import Image
tile_png = io.BytesIO(); Image.new("RGB", (256, 256), "#cde").save(tile_png, "PNG"); tile_png = tile_png.getvalue()
seen, fail = [], set()
class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def reply(self, code, body, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = dict(urllib.parse.parse_qsl(u.query)); seen.append((u.path, q))
        text = q.get("text") or q.get("q") or ""
        if u.path == "/v1/geocode/search" and "Mardel" in text:
            return self.reply(200, {"results": [{"name": "Mardel", "formatted": "calle", "result_type": "street", "lat": -34.62, "lon": -58.49},
                                                {"name": "Mardel", "formatted": "ciudad", "result_type": "city", "lat": -38.0, "lon": -57.55}]})
        if u.path == "/api/" and "Mardel" in text:
            city = q.get("osm_tag") == "!highway" and "Calle" not in text
            return self.reply(200, {"features": [{"properties": {"name": "Mardel", "osm_key": "place" if city else "highway"},
                                                  "geometry": {"coordinates": [-57.55, -38.0] if city else [-58.49, -34.62]}}]})
        if u.path == "/v1/geocode/search":
            if "roto" in text or "caido" in text:
                return self.reply(500, {"error": "x"})
            if "nada" in text:
                return self.reply(200, {"results": []})
            return self.reply(200, {"results": [{"name": text, "formatted": text + ", Ciudad", "lat": -34.6, "lon": -58.43, "rank": {"confidence": 1}}]})
        if u.path == "/api/":
            if "roto" in text or "nada" in text:
                return self.reply(503 if "roto" in text else 200, {"features": []})
            far = "lejano" in text
            return self.reply(200, {"features": [{"properties": {"name": text, "street": "Calle", "housenumber": "1", "city": "Ciudad Photon"},
                                                  "geometry": {"coordinates": [-58.44, -31.4 if far else -34.62]}}]})
        if u.path == "/v1/geocode/reverse":
            return self.reply(500 if "reverse" in fail else 200, {"results": [{"formatted": "Calle Uno 100, Barrio Dos", "street": "Calle Uno", "housenumber": "100"}]})
        if u.path == "/reverse" and "lat" in q and "format" not in q:
            if "photon_reverse" in fail:
                return self.reply(503, {})
            return self.reply(200, {"features": [{"properties": {"street": "Calle Uno", "housenumber": "100", "district": "Barrio Dos",
                                                                 "city": "Partido Tres", "country": "Argentina"}}]})
        if u.path == "/reverse":
            return self.reply(200, {"display_name": "Calle Uno, Barrio Dos, OSM", "address": {"road": "Calle Uno", "suburb": "Barrio Dos"}})
        if u.path == "/search":
            return self.reply(200, [] if "nada" in text else [{"name": text, "display_name": text + ", OSM", "lat": "-34.61", "lon": "-58.44", "importance": .5}])
        if u.path == "/v1/routing":
            if "routing" in fail:
                return self.reply(500, {})
            line = [[-58.37 - i / 1000, -34.59 - i / 2000] for i in range(600)]
            return self.reply(200, {"features": [{"geometry": {"type": "MultiLineString", "coordinates": [line]},
                                                  "properties": {"distance": 7100, "time": 6780, "legs": [{"steps": [
                                                      {"instruction": {"text": "Camine hacia el oeste"}, "distance": 300}] * 20}]}}]})
        if u.path.startswith("/routed-foot/route/v1/driving/"):
            steps = [{"maneuver": {"type": "depart"}, "name": "", "distance": 100},
                     {"maneuver": {"type": "turn", "modifier": "right"}, "name": "Av. Córdoba", "distance": 400},
                     {"maneuver": {"type": "turn", "modifier": "left"}, "name": "", "distance": 2},
                     {"maneuver": {"type": "roundabout", "exit": 2}, "name": "", "distance": 50},
                     {"maneuver": {"type": "arrive"}, "name": "", "distance": 0}]
            return self.reply(200, {"routes": [{"distance": 2052, "duration": 1654, "legs": [{"steps": steps}],
                                                "geometry": {"coordinates": [[-58.44, -34.62], [-58.43, -34.61], [-58.42, -34.60]]}}]})
        if u.path.startswith("/t/"):
            return self.reply(200, tile_png, "image/png")
        self.reply(404, {})
    def do_POST(self):
        seen.append((urllib.parse.urlparse(self.path).path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
        if "staticmap" in fail:
            return self.reply(502, {"error": "x"})
        self.reply(200, b"\xff\xd8fakejpeg", "image/jpeg")
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
gw.GEOAPIFY = gw.GEOAPIFY_MAPS = gw.NOMINATIM = gw.PHOTON = gw.OSRM = base
gw.TILES = base + "/t/{z}/{x}/{y}.png"
gw.MAP_DIR, gw.TRACK, gw.LOG = f"{tmp}/mapas", f"{tmp}/track.jsonl", f"{tmp}/maplog"
os.environ["HERMES_HOME"] = tmp
fresh = importlib.util.module_from_spec(spec); spec.loader.exec_module(fresh)
gw.env_key = fresh.env_key                             # the estado checks above stubbed it
open(f"{tmp}/.env", "w").write("GEOAPIFY_API_KEY=k123\n")
open(gw.TRACK, "w").write(json.dumps({"lat": -34.53, "lon": -58.48, "time": "14:30"}) + "\n")
def mapa(*a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gw.cmd_mapa(list(a))
    return rc, buf.getvalue()
def picture(out):
    return open(out.split("MEDIA:")[1].split()[0], "rb").read()[:2] if "MEDIA:" in out else None
rc, out = mapa("buscar", "Reserva Ecologica")
check("mapa buscar: Geoapify, biased to the person's last pin", (rc, seen[-1][0], seen[-1][1].get("bias")), (0, "/v1/geocode/search", "proximity:-58.48,-34.53"))
check("mapa buscar: address, coordinates, distance and link", all(x in out for x in ("Ciudad", "-34.600000", "km de tu ubicación", "maps/search")), True)
rc, out = mapa("buscar", "caido")
check("mapa buscar: Geoapify down -> Photon, biased too", (rc, seen[-1][0], seen[-1][1].get("lat"), "Calle 1" in out), (0, "/api/", "-34.53", True))
rc, out = mapa("buscar", "roto")
check("mapa buscar: Photon down too -> Nominatim", (rc, seen[-1][0], "OSM" in out), (0, "/search", True))
rc, out = mapa("buscar", "nada")
check("mapa buscar: nothing found anywhere says so, exit 1", (rc, "No encontré" in out), (1, True))
rc, out = mapa("buscar", "caido lejano")
check("mapa buscar: a match far from the person is flagged", "lejos de la persona" in out, True)
check("mapa buscar: when every match is far, it says the name may be misheard", "mal oído" in out, True)
check("mapa buscar: a near match gets no misheard note", "mal oído" in mapa("buscar", "caido")[1], False)
rc, out = mapa("donde")
check("mapa donde: the last pin's address from Geoapify", (rc, "tu ubicación (14:30): Calle Uno 100, Barrio Dos (geoapify)" in out, seen[-1][1].get("lat")), (0, True, "-34.53"))
fail.add("reverse")
rc, out = mapa("donde", "-34.52,-58.48")
check("mapa donde: Geoapify down -> Photon, for a lat,lon", (rc, "Calle Uno 100, Barrio Dos, Partido Tres, Argentina (photon)" in out), (0, True))
fail.add("photon_reverse")
rc, out = mapa("donde", "-34.52,-58.48")
check("mapa donde: Photon down too -> Nominatim", (rc, "(osm)" in out), (0, True))
fail.difference_update({"reverse", "photon_reverse"})
del seen[:]
rc, out = mapa("ruta", "aquí", "Parque Centenario", "--modo", "transporte")
check("mapa ruta transporte: no routing call, the transit link, a picture", (rc, [p for p, _ in seen if "rout" in p], "travelmode=transit" in out,
      picture(out)), (0, [], True, b"\xff\xd8"))
del seen[:]
rc, out = mapa("ruta", "-34.59,-58.37", "Plaza", "--modo", "pie")
body = [b for p, b in seen if p == "/v1/staticmap"][0]
check("mapa ruta pie: distance, time, 15 steps and a note for the rest", ("7.1 km, unos 113 min" in out, out.count("Camine hacia"), "5 pasos más" in out), (True, 15, True))
check("mapa ruta pie: the line is thinned for the picture, two numbered markers",
      (len(body["geometries"][0]["value"]) <= 260, [m["text"] for m in body["markers"]]), (True, ["1", "2"]))
fail.update({"routing", "staticmap"})
rc, out = mapa("ruta", "-34.59,-58.37", "-34.60,-58.42")
check("mapa: Geoapify routing and picture down -> OSRM steps in words and a picture drawn here",
      (rc, "2.1 km, unos 28 min" in out, "girá a la derecha → Av. Córdoba (400 m)" in out, "salida 2" in out,
       "girá a la izquierda (2 m)" in out, picture(out)), (0, True, True, True, False, b"\xff\xd8"))
fail.clear()
open(f"{tmp}/.env", "w").write("")
del seen[:]
rc, out = mapa("puntos", "Obelisco", "Planetario")
paths = [p for p, _ in seen]
check("mapa without any key: Photon finds, the picture is drawn here from tiles, Geoapify never called",
      (rc, all(p == "/api/" or p.startswith("/t/") for p in paths), any(p.startswith("/t/") for p in paths), picture(out)), (0, True, True, b"\xff\xd8"))
del seen[:]
rc, out = mapa("puntos", "Obelisco", "Planetario")
check("mapa: tiles are kept and reused", [p for p, _ in seen if p.startswith("/t/")], [])
gw.TILES = base + "/missing/{z}/{x}/{y}.png"
import shutil; shutil.rmtree(f"{gw.MAP_DIR}/.tiles")
rc, out = mapa("puntos", "Obelisco")
check("mapa: no picture possible -> says so, links still there, exit 0", (rc, "no se pudo dibujar" in out, "maps/search" in out), (0, True, True))
open(f"{tmp}/.env", "w").write("GEOAPIFY_API_KEY=k123\n")
check("mapa: a place name prefers the city over a nearer street (Geoapify)", gw.map_place("Mardel", gw.last_pin())["lat"], -38.0)
open(f"{tmp}/.env", "w").write("")
check("mapa: a place name asks Photon for places first", gw.map_place("Mardel", gw.last_pin())["lat"], -38.0)
del seen[:]
gw.geocode("Mardel 1234")
check("mapa: an address (digits) keeps streets: no place filter", [q.get("osm_tag") for p, q in seen if p == "/api/"], [None])
os.unlink(gw.TRACK)
rc, out = mapa("ruta", "aquí", "Obelisco")
check("mapa: 'aquí' with no pin saved says so", (rc, "ninguna ubicación tuya" in out), (1, True))
check("mapa: bad usage", mapa("ruta", "solo-uno")[0], 2)
logtxt = open(gw.LOG).read()
check("mapa: the log holds no place names or coordinates", any(x in logtxt for x in ("Reserva", "Centenario", "Obelisco", "Córdoba", "Calle Uno", "-34.5", "-58.4")), False)
check("mapa: the log says which source served", ('"route": "osrm"' in logtxt, '"image": "osm"' in logtxt, '"src": "photon"' in logtxt), (True, True, True))
srv.shutdown()

# gateway dato (2026-10-31): one structured keyless source per question, named in the output, fallbacks, nothing in the log
RSS = b'<?xml version="1.0"?><rss><channel><item><title>Titular uno</title><link>https://x/1</link></item><item><title>Dos</title><link>https://x/2</link></item></channel></rss>'
RDF = b'<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"><item><title>Novost</title><link>https://y/1</link></item></rdf:RDF>'
down = set()
class FakeDato(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def reply(self, code, body, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = dict(urllib.parse.parse_qsl(u.query))
        if any(u.path.startswith(d) for d in down):
            return self.reply(503, {})
        m = "_ecmwf_ifs025", "_gfs_seamless"
        if u.path == "/v1/forecast":
            daily = {"time": ["2026-11-01", "2026-11-02"]}
            for sfx, prob in zip(m, ([10, 88], [60, 93])):
                daily.update({f"weather_code{sfx}": [3, 63], f"temperature_2m_max{sfx}": [21, 24], f"temperature_2m_min{sfx}": [14, 16],
                              f"precipitation_probability_max{sfx}": prob, f"precipitation_sum{sfx}": [0, 5.1],
                              f"wind_speed_10m_max{sfx}": [18, 16], f"uv_index_max{sfx}": [8, 7],
                              f"sunrise{sfx}": ["2026-11-01T05:52", "2026-11-02T05:51"], f"sunset{sfx}": ["2026-11-01T19:23", "2026-11-02T19:24"]})
            return self.reply(200, {"daily": daily, "current": {"temperature_2m_ecmwf_ifs025": 20.3, "weather_code_ecmwf_ifs025": 0}, "q": q})
        if u.path == "/v1/air-quality":
            return self.reply(200, {"current": {"us_aqi": 51, "pm2_5": 9.3, "uv_index": 3.3}})
        if u.path == "/v1/dolares":
            return self.reply(200, [{"nombre": "Blue", "compra": 1545, "venta": 1565, "fechaActualizacion": "2026-10-31T17:57:00.000Z"}])
        if u.path == "/v1/cotizaciones":
            return self.reply(200, [{"moneda": "USD", "venta": 1560}, {"moneda": "EUR", "venta": 1714.4}])
        if u.path == "/v2/latest":
            return self.reply(200, {"blue": {"value_buy": 1532, "value_sell": 1565}})
        if u.path.startswith("/v1/feriados/"):
            return self.reply(200, [{"fecha": "2020-01-01", "nombre": "Viejo", "tipo": "x"}, {"fecha": "2099-11-09", "nombre": "Futuro", "tipo": "inamovible"}])
        if u.path == "/v1/finanzas/indices/inflacion":
            return self.reply(200, [{"fecha": f"2026-0{i}-30", "valor": v} for i, v in zip(range(4, 10), (2.6, 2.1, 1.9, 2.1, 1.7, 1.9))])
        if u.path == "/v1/finanzas/indices/riesgo-pais/ultimo":
            return self.reply(200, {"valor": 787, "fecha": "2026-10-30"})
        if u.path == "/v1/finanzas/indices/uva":
            return self.reply(200, [{"fecha": "2026-11-01", "valor": 2177.53}])
        if u.path.startswith("/api/v3/NextPublicHolidays/"):
            return self.reply(200, [{"date": "2026-11-04", "localName": "День народного единства", "name": "Unity Day"}])
        if u.path == "/w/rest.php/v1/search/title":
            return self.reply(200, {"pages": [{"key": "Obelisco_de_Buenos_Aires", "title": "Obelisco de Buenos Aires"}, {"key": "O2", "title": "Obelisco (otro)"}]})
        if u.path.startswith("/api/rest_v1/page/summary/"):
            return self.reply(200, {"title": "Obelisco de Buenos Aires", "description": "monumento", "extract": "Es un monumento.",
                                    "content_urls": {"desktop": {"page": "https://es.wikipedia.org/wiki/Obelisco_de_Buenos_Aires"}}})
        if u.path.startswith("/adsb2/"):
            return self.reply(200, {"ac": [{"flight": "ARG1665 ", "r": "LV-GVD", "t": "B38M", "alt_baro": 3000, "gs": 140, "track": 124, "lat": -34.552, "lon": -58.429},
                                           {"flight": "", "r": "LV-X", "t": "C172", "alt_baro": "ground", "gs": 0, "lat": -34.558, "lon": -58.414},
                                           {"flight": "NOPOS"}]})
        if u.path.startswith("/3/"):
            good = q.get("api_key") == "goodkey1234567890abcd" or self.headers.get("Authorization") == "Bearer eyJgoodtoken1234567890"
            if not good:
                return self.reply(401, {"status_message": "Invalid API key"})
            if u.path == "/3/configuration":
                return self.reply(200, {"images": {}})
            if u.path == "/3/movie/now_playing":
                return self.reply(200, {"results": [{"title": "Peli Uno", "release_date": "2026-10-20", "vote_average": 7.4}]})
            if u.path == "/3/search/multi":
                return self.reply(200, {"results": [{"media_type": "person", "name": "X"}, {"media_type": "tv", "id": 9, "name": "Serie Buena",
                                                     "first_air_date": "2024-01-01", "vote_average": 8.1, "overview": "Trata de algo."}]})
            if u.path == "/3/tv/9/watch/providers":
                return self.reply(200, {"results": {"AR": {"flatrate": [{"provider_name": "Netflix"}]}, "US": {"buy": [{"provider_name": "Apple"}]}}})
        if u.path == "/rss":
            return self.reply(200, RSS, "application/xml")
        if u.path == "/rdf":
            return self.reply(200, RDF, "application/xml")
        self.reply(404, {})
dsrv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeDato)
threading.Thread(target=dsrv.serve_forever, daemon=True).start()
dbase = f"http://127.0.0.1:{dsrv.server_port}"
gw.OPEN_METEO = gw.OPEN_METEO_AIR = gw.DOLARAPI = gw.BLUELYTICS = gw.ARGDATOS = gw.NAGER = gw.WIKI = gw.TMDB = dbase
gw.ADSB = [dbase + "/adsb1/{lat}/{lon}/{nm}", dbase + "/adsb2/{lat}/{lon}/{nm}"]
gw.NEWS = {"ar": [("Diario A", dbase + "/rss"), ("Caído", dbase + "/nada")], "ru": [("DW", dbase + "/rdf")]}
down.add("/adsb1")
gw.LOG = f"{tmp}/datolog"
def dato(*a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gw.cmd_dato(list(a))
    return rc, buf.getvalue()
rc, out = dato("clima", "-34.6,-58.38")
check("dato clima: both models' rain chance side by side, the source named, air quality, sunrise and sunset",
      (rc, "lluvia 10 % / 60 % (ECMWF / GFS)" in out, "Open-Meteo" in out, "índice 51" in out, "2026-11-01: nublado" in out, "Ahora: 20 °C" in out,
       "sol 05:52–19:23" in out), (0, True, True, True, True, True, True))
rc, out = dato("dolar")
check("dato dolar: rates, the Bluelytics check, other currencies", (rc, "Blue: 1545 / 1565" in out, "Bluelytics: blue 1532 / 1565" in out, "EUR 1714.40" in out), (0, True, True, True))
rc, out = dato("feriados")
check("dato feriados: only upcoming ones", (rc, "Futuro" in out, "Viejo" in out), (0, True, False))
rc, out = dato("feriados", "ru")
check("dato feriados RU: Nager.Date", (rc, "День народного единства" in out, "Nager" in out), (0, True, True))
rc, out = dato("economia")
check("dato economia: last inflation, country risk, UVA", (rc, "1.9 % en 2026-09" in out, "787 puntos" in out, "2177.53" in out), (0, True, True, True))
rc, out = dato("wiki", "Obelisco")
check("dato wiki: summary, link, other matches", (rc, "Es un monumento." in out, "wiki/Obelisco_de_Buenos_Aires" in out, "Obelisco (otro)" in out), (0, True, True, True))
rc, out = dato("aviones", "-34.5592,-58.4156")
check("dato aviones: first source down -> second, nearest first, on the ground said so, no-position entries skipped",
      (rc, "adsb.fi" in out or "adsb" in out, out.index("LV-X") < out.index("ARG1665"), "en tierra" in out, "NOPOS" in out, "914 m" in out),
      (0, True, True, True, False, True))
rc, out = dato("noticias")
check("dato noticias: headlines and links, a dead feed says so", (rc, "Titular uno  https://x/1" in out, "Caído: no responde" in out), (0, True, True))
rc, out = dato("noticias", "ru")
check("dato noticias: RDF feeds too", "Novost  https://y/1" in out, True)
down.add("/v1/dolares")
rc, out = dato("dolar")
check("dato: a source down says so, exit 1, never invents", (rc, "no respondió" in out), (1, True))
check("dato: bad usage", dato("nada")[0], 2)
logtxt = open(gw.LOG).read()
check("dato: the log has kind, source and result, never places or numbers asked", ('"kind": "clima"' in logtxt, "-34.6" in logtxt, "Obelisco" in logtxt), (True, False, False))
# optional services (2026-10-31, plan B step 3): a 💡 line once a week at most, never after "no"; keys checked before
# they are stored; the .env keeps everything else
open(f"{tmp}/.env", "w").write("OTHER_KEY=keepme\n")
rc, out = dato("pelis", "Obelisco")
check("pelis without a key: the Wikipedia summary and one 💡 line with the link", (rc, "Es un monumento." in out, out.count("💡"), "themoviedb.org" in out), (0, True, 1, True))
rc, out = dato("pelis", "Obelisco")
check("pelis without a key: the 💡 line does not repeat within a week", out.count("💡"), 0)
p_ = json.load(open(os.environ["AIBRIDGE_PREFS"])); p_["hints"]["tmdb"] -= 8 * 86400; json.dump(p_, open(os.environ["AIBRIDGE_PREFS"], "w"))
check("pelis without a key: after a week it may say it again", dato("pelis")[1].count("💡"), 1)
with contextlib.redirect_stdout(io.StringIO()):
    gw.cmd_servicios(["no", "tmdb"])
p_ = json.load(open(os.environ["AIBRIDGE_PREFS"])); p_["hints"]["tmdb"] = 0; json.dump(p_, open(os.environ["AIBRIDGE_PREFS"], "w"))
check("servicios no tmdb: never again", dato("pelis")[1].count("💡"), 0)
def guardar(svc, key):
    sys.stdin, buf = io.StringIO(key + "\n"), io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gw.cmd_servicios(["guardar", svc])
    sys.stdin = sys.__stdin__
    return rc, buf.getvalue()
check("servicios guardar: not key-shaped is refused", guardar("tmdb", "hola que tal")[0], 1)
rc, out = guardar("tmdb", "badkey1234567890abcdef")
check("servicios guardar: a key the service rejects is not stored", (rc, "HTTP 401" in out, "TMDB_API_KEY" in open(f"{tmp}/.env").read()), (1, True, False))
rc, out = guardar("tmdb", "goodkey1234567890abcd")
env_txt = open(f"{tmp}/.env").read()
check("servicios guardar: checked, stored, the rest of the .env kept, mode 600, only the last 4 shown",
      (rc, "TMDB_API_KEY=goodkey1234567890abcd" in env_txt, "OTHER_KEY=keepme" in env_txt, oct(os.stat(f"{tmp}/.env").st_mode)[-3:], "…abcd" in out, "goodkey" in out),
      (0, True, True, "600", True, False))
rc, out = dato("pelis")
check("pelis with a key: cinemas in Argentina from TMDB", (rc, "Peli Uno (2026), 7.4/10" in out, "💡" in out), (0, True, False))
rc, out = dato("pelis", "serie buena")
check("pelis with a key: the title, where it streams in AR only", (rc, "Serie Buena (2024, serie)" in out, "Incluida en: Netflix" in out, "Apple" in out), (0, True, True, False))
check("servicios guardar: the long read token works too", guardar("tmdb", "eyJgoodtoken1234567890")[0], 0)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    gw.cmd_servicios(["--json"])
rows = {r["id"]: r for r in json.loads(buf.getvalue())}
check("servicios --json: last 4 only, never the key", (rows["tmdb"]["last4"], "eyJgood" in buf.getvalue(), rows["geoapify"]["last4"]), ("7890", False, None))
with contextlib.redirect_stdout(io.StringIO()):
    gw.cmd_servicios(["quitar", "tmdb"])
check("servicios quitar: the line goes, the rest stays", ("TMDB_API_KEY" in open(f"{tmp}/.env").read(), "OTHER_KEY=keepme" in open(f"{tmp}/.env").read()), (False, True))
check("estado: every language has the services line", all("{s}" in gw.ESTADO[l]["svc"] for l in ("es", "ru", "en")), True)
check("servicios: the log never holds a key", any(k in open(gw.LOG).read() for k in ("goodkey", "eyJgood", "badkey")), False)
dsrv.shutdown()

# gateway proxmox (2026-10-31, plan B step 4): GET only on a short path list, TLS pinned to the host's fingerprint,
# the token in the header, nothing about the host in the log
import shutil as _sh, ssl, hashlib
if _sh.which("openssl"):
    pdir = tempfile.mkdtemp()
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=pve-test",
                    "-keyout", f"{pdir}/k.pem", "-out", f"{pdir}/c.pem"], capture_output=True, check=True)
    der = ssl.PEM_cert_to_DER_cert(open(f"{pdir}/c.pem").read())
    fp = ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())
    pseen, clustered = [], False
    class FakePve(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass
        def reply(self, code, data):
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"data": data}).encode())
        def do_POST(self):
            pseen.append(("POST", self.path)); self.reply(500, None)
        def do_GET(self):
            u = urllib.parse.urlparse(self.path); pseen.append(("GET", u.path, self.headers.get("Authorization")))
            path = u.path[len("/api2/json"):]
            now = time.time()
            if path == "/cluster/resources":
                res = [{"type": "node", "node": "pve1", "status": "online", "cpu": .12, "mem": 30e9, "maxmem": 64e9, "uptime": 90000},
                       {"type": "qemu", "vmid": 105, "name": "docker", "node": "pve1", "status": "running", "cpu": .4, "maxcpu": 4,
                        "mem": 6e9, "maxmem": 8e9, "uptime": 3600, "maxdisk": 80e9},
                       {"type": "lxc", "vmid": 110, "name": "dns", "node": "pve1", "status": "stopped", "maxmem": 1e9},
                       {"type": "qemu", "vmid": 106, "name": "ballooned", "node": "pve1", "status": "running", "mem": 6e9, "maxmem": 8e9},
                       {"type": "storage", "storage": "local-lvm", "node": "pve1", "status": "available", "disk": 90e9, "maxdisk": 100e9}]
                t = urllib.parse.parse_qs(u.query).get("type")
                return self.reply(200, [r for r in res if not t or r["type"] == t[0]])
            if path == "/cluster/status":
                return self.reply(200, ([{"type": "cluster", "name": "casa"}] if clustered else []) + [{"type": "node", "name": "pve1", "local": 1}])
            if path == "/cluster/tasks":
                return self.reply(200, [{"type": "vzdump", "id": "110", "node": "pve1", "status": "job errors", "starttime": now - 600},
                                        {"type": "qmstart", "node": "pve1", "status": "OK", "starttime": now - 60}])
            if path == "/nodes/pve1/qemu/105/status/current":
                return self.reply(200, {"name": "docker", "status": "running", "cpus": 4, "cpu": .4, "mem": 6e9, "maxmem": 8e9, "uptime": 3600,
                                        "netin": 1e9, "netout": 2e9, "diskread": 3e9, "diskwrite": 4e9})
            if path == "/nodes/pve1/qemu/106/status/current":
                return self.reply(200, {"name": "ballooned", "status": "running", "cpus": 2, "cpu": .1, "mem": 6e9, "maxmem": 8e9, "uptime": 60,
                                        "ballooninfo": {"total_mem": 8 * 2 ** 30, "free_mem": 1 * 2 ** 30, "avail_mem": 6 * 2 ** 30}})
            if path == "/cluster/backup":
                return self.reply(200, [{"id": "backup-1", "enabled": 1, "schedule": "sun 01:00", "storage": "pbs", "all": 1}])
            if path == "/nodes/pve1/tasks":
                return self.reply(200, [{"id": "105", "status": "OK", "starttime": now - 7200, "endtime": now - 6600}])
            if path == "/cluster/backup-info/not-backed-up":
                return self.reply(200, [{"vmid": 110, "name": "dns"}])
            self.reply(404, None)
    psrv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakePve)
    psrv.handle_error = lambda *a: None                 # the pin test drops the connection on purpose
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); sctx.load_cert_chain(f"{pdir}/c.pem", f"{pdir}/k.pem")
    psrv.socket = sctx.wrap_socket(psrv.socket, server_side=True)
    threading.Thread(target=psrv.serve_forever, daemon=True).start()
    gw.LOG = f"{tmp}/pvelog"
    def pve(*a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = gw.cmd_proxmox(list(a))
        return rc, buf.getvalue()
    open(f"{tmp}/.env", "w").write("")
    check("proxmox not configured: says so, exit 1, no call", (pve()[0], "no está configurado" in pve()[1], pseen), (1, True, []))
    open(f"{tmp}/.env", "w").write(f"PROXMOX_URL=https://127.0.0.1:{psrv.server_port}\nPROXMOX_TOKEN=hermes@pve!ro=uuid-secret\nPROXMOX_FINGERPRINT={fp}\n")
    rc, out = pve("estado")
    check("proxmox estado: node, machines on/off, top RAM, a nearly full disk, a failed task",
          (rc, "Nodo pve1: online" in out, "2 encendidas de 3" in out, "105 docker 5.6 GB/7.5 GB" in out, "casi lleno" in out, "vzdump 110" in out),
          (0, True, True, True, True, True))
    check("proxmox: the token goes in the PVEAPIToken header", {h for _, _, h in [x for x in pseen if x[0] == "GET"]}, {"PVEAPIToken=hermes@pve!ro=uuid-secret"})
    rc, out = pve("vm", "105")
    check("proxmox vm: status, CPU, RAM, network and disk", (rc, "105 docker (VM en pve1): running" in out, "4 núcleos" in out, "salió 1.9 GB" in out), (0, True, True, True))
    check("proxmox vm without balloon: says the number is host memory with the guest's cache, and how to get the real one",
          ("RAM ocupada en el host: 5.6 GB" in out, "incluye la caché" in out, "free -m" in out), (True, True, True))
    rc, out = pve("vm", "106")
    check("proxmox vm with balloon stats: the guest's own used memory, available-based", "usada 2.0 GB de 8.0 GB" in out, True)
    check("proxmox vm: an unknown id says so", pve("vm", "999")[0], 1)
    rc, out = pve("backups")
    check("proxmox backups: jobs, last runs, machines without backup", (rc, "backup-1: activo, sun 01:00, a pbs, máquinas: todas" in out, ": OK, 10 min" in out,
          "sin ningún backup programado: 110 dns" in out), (0, True, True, True))
    check("proxmox vms: every guest", pve("vms")[1].count("\n- "), 3)
    check("proxmox: never anything but GET", [x for x in pseen if x[0] != "GET"], [])
    one = open(f"{tmp}/.env").read()
    open(f"{tmp}/.env", "a").write(f"PROXMOX_NAME=pve3\nPROXMOX_HOSTS=pve-b, caido,a medias\nPROXMOX_PVE_B_URL=https://127.0.0.1:{psrv.server_port}\n"
                                   f"PROXMOX_PVE_B_TOKEN=zabbix@pve!b=uuid-b\nPROXMOX_PVE_B_FINGERPRINT={fp}\nPROXMOX_CAIDO_URL=https://127.0.0.1:1\n"
                                   f"PROXMOX_CAIDO_TOKEN=x@pve!c=uuid-c\nPROXMOX_CAIDO_FINGERPRINT={fp}\nPROXMOX_A_MEDIAS_URL=https://127.0.0.1:2\n")
    rc, out = pve("estado")
    check("proxmox, several standalone hosts sharing a node name: each shown in full, a dead one and an incomplete one reported, exit 1",
          (rc, "== pve3 (en Zabbix: grupo bridgeai/pve3)" in out, out.count("Nodo pve1: online"), "Mismo cluster" in out,
           "caido: no pude leer Proxmox: ConnectionRefusedError" in out,
           "a medias: configuración incompleta (falta PROXMOX_A_MEDIAS_TOKEN, PROXMOX_A_MEDIAS_FINGERPRINT)" in out),
          (1, True, 2, False, True, True))
    clustered = True
    rc, out = pve("estado")
    check("proxmox, two ways into one cluster: the second only says it answers", (out.count("Nodo pve1: online"), "Mismo cluster (casa) que pve3" in out), (1, True))
    clustered = False
    check("proxmox, several hosts: each host's own token", {h for _, _, h in [x for x in pseen[-6:] if x[0] == "GET"]} >= {"PVEAPIToken=zabbix@pve!b=uuid-b"}, True)
    rc, out = pve("--host", "pve-b", "estado")
    check("proxmox --host: only that one, with its Zabbix group", (rc, out.count("== "), "grupo bridgeai/pve-b" in out, "Nodo pve1" in out), (0, 1, True, True))
    rc, out = pve("--host", "pve3", "vm", "999")
    check("proxmox --host + unknown vm: says so once", (rc, out.count("No hay ninguna máquina 999")), (1, 1))
    rc, out = pve("--host", "nadie")
    check("proxmox --host unknown: lists the names", (rc, "pve3, pve-b, caido, a medias" in out), (1, True))
    open(f"{tmp}/.env", "w").write(one)
    try:
        gw.pve_get("/nodes/pve1/qemu/105/config")
        allowed = True
    except ValueError:
        allowed = False
    check("proxmox: a path off the read-only list is refused before any call (VM config holds secrets)", allowed, False)
    check("proxmox: an exec-like path is refused", gw.PVE_PATHS.match("/nodes/pve1/qemu/105/agent/exec") is None, True)
    open(f"{tmp}/.env", "a").write("PROXMOX_FINGERPRINT=00:11\n")
    gw_lines = open(f"{tmp}/.env").read().replace(f"PROXMOX_FINGERPRINT={fp}\n", "")
    open(f"{tmp}/.env", "w").write(gw_lines)
    n_before = len(pseen)
    rc, out = pve("estado")
    check("proxmox: a different certificate is refused before the token is sent", (rc, "does not match" in out, len(pseen)), (1, True, n_before))
    lg = open(gw.LOG).read()
    check("proxmox: the log has no host, token or machine names", any(x in lg for x in ("127.0.0.1", "uuid-secret", "docker", "pve1")), False)
    psrv.shutdown()

# gateway qr (2026-10-31): three readers, a picture made and read back, a code no single frame reads rescued by
# aligning and averaging the frames, nothing of the codes in the gateway log. Needs cv2/zxingcpp/segno (the image has
# them; the operator's computer usually not): without them only the "missing" answer is checked.
def qr(*a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gw.cmd_qr(list(a))
    return rc, buf.getvalue()
gw.LOG, gw.QR_DIR = f"{tmp}/qrlog", f"{tmp}/codigos"
try:
    import cv2 as _cv2, zxingcpp as _zx, segno as _sg, numpy as _np
except ImportError:
    _cv2 = None
if _cv2 is None:
    open(f"{tmp}/x.png", "wb").write(b"\x89PNG")
    rc, out = qr(f"{tmp}/x.png")
    check("qr without the readers: says what is missing, exit 3", (rc, "Falta" in out), (3, True))
else:
    rc, out = qr("crear", "https://example.org/a-1")
    pic = out.split("MEDIA:")[1].split()[0]
    check("qr crear: a picture, checked by reading it back", (rc, "verificado" in out, os.path.exists(pic)), (0, True, True))
    rc, out = qr(pic)
    check("qr: reads its own picture, flags third-party text, names the link's domain",
          (rc, "https://example.org/a-1" in out, "no son instrucciones" in out, "link a example.org" in out), (0, True, True, True))
    base = _cv2.imread(pic, 0)
    rng = _np.random.default_rng(7)
    small = _cv2.GaussianBlur(_cv2.resize(base, (120, 120), interpolation=_cv2.INTER_AREA).astype(_np.float32), (0, 0), 1.2)
    small = 100 + small / 255.0 * 60
    os.makedirs(f"{tmp}/fr", exist_ok=True)
    for i in range(30):
        fr = _np.full((360, 640), 120, _np.float32)
        dx, dy = (int(v) for v in rng.integers(-2, 3, 2))
        fr[120 + dy:240 + dy, 260 + dx:380 + dx] = small
        fr += rng.normal(0, 30, fr.shape)
        _cv2.imwrite(f"{tmp}/fr/{i:03d}.png", _np.clip(fr, 0, 255).astype(_np.uint8))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "25", "-i", f"{tmp}/fr/%03d.png", "-c:v", "ffv1", f"{tmp}/clip.mkv"], check=True)
    single = sum(bool(_zx.read_barcodes(_cv2.imread(f"{tmp}/fr/{i:03d}.png", 0))) for i in range(30))
    rc, out = qr(f"{tmp}/clip.mkv", "--zona", "0.35,0.25,0.3,0.5")
    check("qr video: no single frame reads, the aligned average of the zone does",
          (single, rc, "https://example.org/a-1" in out, "+pila" in out), (0, 0, True, True))
    rc, out = qr(f"{tmp}/clip.mkv")
    check("qr video without a zone, nothing seen: says so and how to give the zone", (rc, "--zona" in out), (1, True))
    rc, out = qr(f"{tmp}/clip.mkv", "--zona", "1,2")
    check("qr: a bad zone is refused", rc, 2)
    saved = open(f"{tmp}/codigos/codigos.jsonl").read()
    check("qr: what was read is kept for the person", saved.count("https://example.org/a-1"), 2)
    rc, out = qr("lista")
    check("qr lista: the last codes read", (rc, out.count("https://example.org/a-1")), (0, 2))
    # the grid reader: a curved, unevenly inked, blurred code on skin colour (the 2026-10-31 tattoo, in miniature):
    # zxing and WeChat read nothing, the grid with its bent mesh and soft decoding does
    m = _np.array(_sg.make("https://example.org/tattoo", version=3, error="m", boost_error=False).matrix, dtype=_np.float32)
    S, N = 16, m.shape[0]
    img = _np.ones(((N + 8) * S, (N + 8) * S), _np.float32)
    img[4 * S:(4 + N) * S, 4 * S:(4 + N) * S] = 1 - _np.kron(m, _np.ones((S, S)))
    h, w = img.shape
    img = 1 - (1 - img) * (1 - 0.55 * _np.clip((_np.arange(w) - w * 0.5) / (w * 0.3), 0, 1)[None, :])
    yy, xx = _np.mgrid[0:h, 0:w].astype(_np.float32)
    img = _cv2.remap(img, xx - 0.04 * w * _np.sin(_np.pi * yy / h), yy, _cv2.INTER_LINEAR, borderValue=1)
    img = _cv2.GaussianBlur(img, (0, 0), 0.45 * S)
    rng = _np.random.default_rng(0)
    col = _np.clip(_np.stack([img * 120 + 40, img * 150 + 50, img * 190 + 60], axis=2) + rng.normal(0, 9, (h, w, 3)), 0, 255).astype(_np.uint8)
    _cv2.imwrite(f"{tmp}/tattoo.png", col)
    plain = [r.text for r in _zx.read_barcodes(_cv2.cvtColor(col, _cv2.COLOR_BGR2GRAY)) if r.valid]
    rc, out = qr(f"{tmp}/tattoo.png")
    check("qr grid reader: a curved faded code no plain reader takes", (plain, rc, "https://example.org/tattoo" in out, "cuadrícula" in out),
          ([], 0, True, True))
    # 2026-11-01: a code at under 3 px a module on a white sticker in a dark 720x1280 night photo. No reader takes the
    # whole picture; the automatic zone (what --zona did by hand) does. The sticker itself must not pass for a finder.
    m = _np.array(_sg.make("https://example.org/lejos", version=3, error="m", boost_error=False).matrix, _np.float32)
    side = int(round((m.shape[0] + 8) * 2.7))
    c = _cv2.resize(_np.pad(1 - m, 4, constant_values=1), (side, side), interpolation=_cv2.INTER_AREA)
    rng = _np.random.default_rng(1)
    fr = _np.full((1280, 720), 45, _np.float32) + rng.normal(0, 4, (1280, 720))
    fr[680:760 + side, 360:400 + side] = 225
    fr[700:700 + side, 380:380 + side] = 30 + c * 190
    fr = _cv2.GaussianBlur(fr, (0, 0), 1.3) + rng.normal(0, 6, fr.shape)
    _cv2.imwrite(f"{tmp}/lejos.jpg", _np.clip(_np.stack([fr] * 3, 2), 0, 255).astype(_np.uint8), [_cv2.IMWRITE_JPEG_QUALITY, 75])
    far = _cv2.imread(f"{tmp}/lejos.jpg")
    fs = gw.qr_finders(far[..., 2], _cv2, _np, up=True)
    check("qr finders: the white sticker around a code is not taken for a finder (one hid the real ones)",
          [round(f[2]) for f in fs if f[2] > side / 3], [])
    rc, out = qr(f"{tmp}/lejos.jpg")
    check("qr photo: a small far code no reader takes whole is found and read by the automatic zone",
          (bool(gw.QrReader().read(_cv2.cvtColor(far, _cv2.COLOR_BGR2GRAY))[0]), rc, "https://example.org/lejos" in out,
           "zona automática" in out), (False, 0, True, True))
    # several photos of one code, each with a reflection somewhere else, noise and its own angle: none reads alone,
    # their grids averaged module by module do
    rng = _np.random.default_rng(1)
    m = _np.array(_sg.make("https://example.org/varias-1", version=4, error="l", boost_error=False).matrix, _np.float32)
    S, N = 10, m.shape[0]
    shots = []
    for k in range(4):
        img = _np.ones(((N + 8) * S, (N + 8) * S), _np.float32) * 0.85
        img[4 * S:(4 + N) * S, 4 * S:(4 + N) * S] = 0.85 - 0.7 * _np.kron(m, _np.ones((S, S)))
        h, w = img.shape
        yy, xx = _np.mgrid[0:h, 0:w]
        cx, cy = w * rng.uniform(.3, .7), h * rng.uniform(.3, .7)
        img = _np.minimum(1, img + 1.4 * _np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (0.16 * w) ** 2)))
        sq = _np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        img = _cv2.warpPerspective(img, _cv2.getPerspectiveTransform(sq, sq + rng.uniform(-0.06, 0.06, (4, 2)).astype(_np.float32) * w),
                                   (w, h), borderValue=0.85)
        img = _cv2.GaussianBlur(img, (0, 0), 0.35 * S) * 255 + rng.normal(0, 22, img.shape)
        shots.append(f"{tmp}/varias{k}.jpg")
        _cv2.imwrite(shots[-1], _np.clip(_np.stack([img] * 3, 2), 0, 255).astype(_np.uint8), [_cv2.IMWRITE_JPEG_QUALITY, 80])
    alone = [qr(p)[0] for p in shots[:2]]
    rc, out = qr(*shots)
    check("qr several photos: none reads alone, together they do", (alone, rc, "example.org/varias-1" in out, "fotos juntos" in out),
          ([1, 1], 0, True, True))
    rc, out = qr(shots[0], f"{tmp}/clip.mkv")
    check("qr: a video goes alone, not with photos", rc, 2)
    _cv2.imwrite(f"{tmp}/nada.jpg",_np.clip(rng.normal(60, 20, (640, 480, 3)), 0, 255).astype(_np.uint8))
    rc, out = qr(f"{tmp}/nada.jpg")
    check("qr photo that does not read: how to take one that does", (rc, "Para otra foto que se lea" in out, "cerca" in out),
          (1, True, True))
    m2 = _np.array(_sg.make("https://example.org/x", version=3, error="h", boost_error=False).matrix, dtype=float) * 2 - 1
    junk = _np.random.default_rng(3).normal(0, 1, m2.shape)
    check("qr soft decoding never prints a miscorrection: random modules give nothing", gw.qr_soft_decode(junk, 29, _np)[0], None)
    lg = open(gw.LOG).read()
    check("qr: the gateway log has no code text", "example.org" in lg, False)

# gateway zabbix (2026-11-01, two fixes hernik's agent wrote live that day): a text item shows its last value instead of
# "no es numérico", and a timed-out API call is retried while a refusal is not
import http.server as _hs, threading as _th
_zcalls = []
class FakeZabbix(_hs.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _zcalls.append(req["method"])
        if self.server.mode == "slow" and len(_zcalls) <= 2:
            _th.Event().wait(0.6)                        # longer than the test's timeout (not time.sleep: patched below)
        if self.server.mode == "403":
            self.send_response(403); self.end_headers(); return
        if self.server.mode == "zerr":                  # Zabbix answers, with an error: an answer, not a network failure
            body = json.dumps({"jsonrpc": "2.0", "error": {"message": "Invalid params.", "data": "x"}, "id": 1}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        res = {"host.get": [{"hostid": "1", "host": "pve-a", "name": "pve-a", "tags": []}],
               "item.get": [{"itemid": "9", "name": "PVE version", "key_": "pve.version", "value_type": "4", "units": "",
                             "lastvalue": "pve-manager/9.2.24/abc", "state": "0"},
                            {"itemid": "8", "name": "PVE version old", "key_": "pve.version.old", "value_type": "1", "units": "",
                             "lastvalue": "", "state": "1"}]}.get(req["method"], [])
        body = json.dumps({"jsonrpc": "2.0", "result": res, "id": 1}).encode()
        try:
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        except OSError:
            pass
zsrv = _hs.ThreadingHTTPServer(("127.0.0.1", 0), FakeZabbix)
zsrv.mode, zsrv.handle_error = "ok", (lambda *a: None)
_th.Thread(target=zsrv.serve_forever, daemon=True).start()
json.dump({"zabbix": {"url": f"http://127.0.0.1:{zsrv.server_port}", "token": "t"}}, open(f"{tmp}/gw-zbx.json", "w"))
_conf_was, gw.CONF, _zto, gw.ZBX_TIMEOUT = gw.CONF, f"{tmp}/gw-zbx.json", gw.ZBX_TIMEOUT, 0.3
_sleep, gw.time.sleep = gw.time.sleep, (lambda s: None)
def zbx(*a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gw.cmd_zabbix(list(a))
    return rc, buf.getvalue()
rc, out = zbx("item", "pve-a", "version")
check("zabbix item: a text item prints its last value", "PVE version: pve-manager/9.2.24/abc" in out, True)
check("zabbix item: an unsupported text item says so", "(vacío)  (item no soportado)" in out, True)
_zcalls.clear(); zsrv.mode = "slow"
rc, out = zbx("item", "pve-a", "version")
check("zabbix: two timeouts then an answer: retried, answered", ("pve-manager/9.2.24" in out, len(_zcalls) >= 4, _zcalls[0] == _zcalls[2]),
      (True, True, True))
_zcalls.clear(); zsrv.mode = "403"
rc, out = zbx("item", "pve-a", "version")
check("zabbix: a refusal (403) is not retried, and is reported", (len(_zcalls), "403" in out, "pve-manager" in out), (1, True, False))
_zcalls.clear(); zsrv.mode = "zerr"
rc, out = zbx("item", "pve-a", "version")
check("zabbix: an error answer from Zabbix is not retried, and is reported", (len(_zcalls), "Invalid params" in out), (1, True))
gw.CONF, gw.ZBX_TIMEOUT, gw.time.sleep = _conf_was, _zto, _sleep
zsrv.shutdown()

print("\n".join(fails) or "gateway_pref_selftest: all checks passed")
sys.exit(1 if fails else 0)
