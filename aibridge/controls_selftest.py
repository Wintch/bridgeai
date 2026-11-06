#!/usr/bin/env python3
"""The aibridge-controls plugin: every command answers the person with text and never raises. No Hermes needed: python3 controls_selftest.py"""
import importlib.util, os, sys, types
spec = importlib.util.spec_from_file_location("controls", os.path.join(os.path.dirname(os.path.abspath(__file__)), "hermes_plugins", "aibridge-controls", "__init__.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

calls = []
def fake(argv, timeout=30):
    calls.append(argv)
    return {"subs-fetch": "chan_subs   10 files  en-orig  RUNNING  last 10 min 5  last hour 20\ntotal 10 files", "dormir": "nada corriendo", "archivo": "EXISTE  /x\n-> nota para el agente", "opinion": "Anotado.", "manual": "📖 guía"}[argv[0]]
c._run = fake
reg = {}
c.register(types.SimpleNamespace(register_command=lambda name, fn, description="", args_hint="": reg.__setitem__(name, fn)))
check("eleven commands registered, all Spanish names", sorted(reg) == ["archivos", "compartir", "controles", "dormir", "manual", "opinion", "paquete", "paquetes", "parar", "retomar", "trabajos"])
check("/trabajos shows the files on disk and the processes", "10 files" in reg["trabajos"]() and "nada corriendo" in reg["trabajos"]())
calls.clear(); reg["parar"]("")
check("/parar with no argument stops everything (no filter)", calls[-1] == ["dormir", "--parar", "--usuario"])
calls.clear(); reg["parar"]("teoria extra words")
check("/parar teoria passes only the first word as the filter", calls[-1] == ["dormir", "--parar", "--usuario", "teoria"])
for arg, flag in (("", None), ("ya", "--igual"), ("luego", "--cuando-termine"), ("cancelar", "--cancelar")):
    calls.clear(); reg["dormir"](arg)
    check(f"/dormir {arg!r} -> dormir {flag or '(plain)'}", calls[-1] == (["dormir", "--usuario"] + ([flag] if flag else [])))
calls.clear()
check("/dormir with a word it does not know does nothing and explains", "No entendí" in reg["dormir"]("mañana") and not calls)
check("/retomar refuses to stack a round on a running one", "Ya hay canales descargando" in reg["retomar"]())
c._run = lambda argv, timeout=30: ("proceso 7: python3 /usr/local/bin/subs-fetch --lang en-orig X Y" if argv[0] == "dormir" else "chan_subs   10 files  en-orig  idle  last 10 min 0  last hour 0")
check("/retomar also sees an old-style job that holds no folder lock", "Ya hay canales descargando" in reg["retomar"]())
c._run = lambda argv, timeout=30: "chan_subs 10 files en-orig idle last 10 min 0 last hour 0\ntotal 10 files; PAUSED by a rate limit for 40 more min" if argv[0] == "subs-fetch" else "x"
check("/retomar respects a rate-limit pause", "pausa por límite" in reg["retomar"]())
c._run = fake
out = reg["archivos"]("johnny mnemonic")
check("/archivos hides the notes meant for the agent", "EXISTE" in out and "nota para el agente" not in out)
check("/archivos with nothing asks what to look for", "Escribe qué buscas" in reg["archivos"](""))
calls.clear(); reg["opinion"]("me gustó  mucho")
check("/opinion passes the words to `opinion`", calls[-1] == ["opinion", "me", "gustó", "mucho"])
calls.clear(); reg["opinion"]("privado algo mío")
check("/opinion privado passes through too", calls[-1] == ["opinion", "privado", "algo", "mío"])
calls.clear(); reg["compartir"]("")
check("/compartir alone shows the level", calls[-1] == ["opinion", "compartir"])
calls.clear(); reg["compartir"]("todo y más cosas")
check("/compartir todo passes the level and at most one more word (opinion.py refuses extra words)", calls[-1] == ["opinion", "compartir", "todo", "y"])
calls.clear(); reg["manual"]("")
check("/manual asks for the short guide", calls[-1] == ["manual"])
calls.clear(); reg["manual"]("completo")
check("/manual completo asks for the whole text", calls[-1] == ["manual", "--full"])
import logging, io
buf = io.StringIO(); h = logging.StreamHandler(buf); logging.getLogger().addHandler(h)
reg["opinion"]("MI-TEXTO-PRIVADO"); reg["archivos"]("johnny")
logging.getLogger().removeHandler(h)
check("the log never carries the text of an opinion (it does keep the other commands' arguments)", "MI-TEXTO-PRIVADO" not in buf.getvalue() and "/opinion" in buf.getvalue() and "johnny" in buf.getvalue())
check("/controles lists the commands in both languages", "/parar" in reg["controles"]() and "Управление" in reg["controles"]())
c.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("no such program"))
real = types.ModuleType("x")
exec(compile(open(spec.origin).read(), spec.origin, "exec"), real.__dict__)
check("a missing program is a line of text, not an exception", "No pude ejecutar" in real._run(["nope"]))
# skill packs (2026-11-06): /paquetes lists, /paquete NOMBRE si|no switches, bad input is a usage line
import subprocess as _sp
calls = []
_real_run = c._run if hasattr(c, "_run") else None
c._run = lambda argv, timeout=30: (calls.append(argv), "OK " + " ".join(argv))[1]
check("/paquetes runs `paquetes list`", c.cmd_paquetes("") == "OK paquetes list")
check("/paquete empleo si -> paquetes on empleo", c.cmd_paquete("empleo si") == "OK paquetes on empleo")
check("/paquete Oficina NO -> paquetes off oficina", c.cmd_paquete("Oficina NO") == "OK paquetes off oficina")
check("/paquete with one word or a wrong answer is a usage line, nothing runs", c.cmd_paquete("empleo").startswith("Uso:") and c.cmd_paquete("empleo quizas").startswith("Uso:") and len(calls) == 3)
check("/controles mentions the packs", "/paquetes" in c.cmd_controles(""))

print("\n".join(fails) or "controls_selftest: all ok")
sys.exit(1 if fails else 0)
