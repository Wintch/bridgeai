#!/usr/bin/env python3
"""Offline checks for `gateway pref`/`gateway speak` voice choice and the two Hermes patches of 2026-10-17
(patches/quick_command_args.py, patches/reply_language.py). Run: python3 -I gateway_pref_selftest.py
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
open(mt, "w").write("\n" + textwrap.dedent('''\
    def render_user_content_with_timestamp(content, ts_value=None):
        clean_content, prefix = content, "[ts]"
        return f"{prefix} {clean_content}" if prefix and clean_content else (prefix or clean_content)
    '''))
for _ in range(2):
    subprocess.run([sys.executable, f"{HERE}/patches/reply_language.py", mt], check=True, capture_output=True)
ns = {}
exec(open(mt).read(), ns)
json.dump({"lang": "ru"}, open(f"{tmp}/prefs.json", "w"))
check("hint added", ns["render_user_content_with_timestamp"]("hola"), "[ts] [reply in Russian] hola")
json.dump({"lang": "auto"}, open(f"{tmp}/prefs.json", "w")); os.utime(f"{tmp}/prefs.json", (1e9, 1e9 + 7))
check("auto adds nothing", ns["render_user_content_with_timestamp"]("hola"), "[ts] hola")

print("\n".join(fails) or "gateway_pref_selftest: all checks passed")
sys.exit(1 if fails else 0)
