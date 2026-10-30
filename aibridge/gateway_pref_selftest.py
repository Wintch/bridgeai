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

print("\n".join(fails) or "gateway_pref_selftest: all checks passed")
sys.exit(1 if fails else 0)
