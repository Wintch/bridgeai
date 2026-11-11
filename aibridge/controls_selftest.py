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
    return {"subs-fetch": "chan_subs   10 files  en-orig  RUNNING  last 10 min 5  last hour 20\ntotal 10 files", "dormir": "nada corriendo", "archivo": "EXISTE  /x\n-> nota para el agente", "opinion": "Anotado.", "manual": "📖 guía", "gateway": "Idioma: auto\nsegunda línea", "paquetes": "paquetes ok"}[argv[0]]
c._run = fake
reg = {}
c.register(types.SimpleNamespace(register_command=lambda name, fn, description="", args_hint="": reg.__setitem__(name, fn)))
check("eighteen commands registered: the English names, the older ones and the owner's /publicar (/publish)", sorted(reg) == ["archivos", "compartir", "controles", "dormir", "feedback", "files", "jobs", "manual", "opinion", "paquete", "paquetes", "parar", "publicar", "publish", "retomar", "settings", "sleep", "trabajos"])
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
check("/archivos with nothing asks what to look for", "Escribí qué buscás" in reg["archivos"](""))
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
for arg, flag in (("", None), ("now", "--igual"), ("ya", "--igual"), ("сейчас", "--igual"), ("later", "--cuando-termine"), ("потом", "--cuando-termine"), ("cancel", "--cancelar")):
    calls.clear(); reg["sleep"](arg)
    check(f"/sleep {arg!r} -> dormir {flag or '(plain)'}", calls[-1] == (["dormir", "--usuario"] + ([flag] if flag else [])))
calls.clear()
check("/sleep with a word it does not know does nothing and explains", "/sleep now" in reg["sleep"]("mañana") and not calls)
calls.clear(); reg["jobs"]("stop teoria")
check("/jobs stop teoria -> the same as /parar teoria", calls[-1] == ["dormir", "--parar", "--usuario", "teoria"])
calls.clear(); reg["jobs"]("")
check("/jobs alone lists the work", any(c[0] == "subs-fetch" for c in calls) and any(c[0] == "dormir" for c in calls))
check("/jobs resume refuses to stack a round, like /retomar", "Ya hay canales descargando" in reg["jobs"]("resume"))
calls.clear(); out = reg["files"]("johnny mnemonic")
check("/files searches like /archivos", calls[-1] == ["archivo", "buscar", "johnny", "mnemonic"] and "EXISTE" in out)
check("/files with nothing asks what to look for", "Escribí qué buscás" in reg["files"](""))
calls.clear(); reg["feedback"]("data none")
check("/feedback passes everything to `opinion`", calls[-1] == ["opinion", "data", "none"])
calls.clear(); reg["feedback"]("private algo mío")
check("/feedback private passes through", calls[-1] == ["opinion", "private", "algo", "mío"])
for words, want in (("language ru", ["gateway", "pref", "lang", "ru"]), ("idioma en", ["gateway", "pref", "lang", "en"]), ("voice", ["gateway", "pref", "voice"]),
                    ("alerts daily", ["gateway", "pref", "avisos", "daily"]), ("avisos nuevo", ["gateway", "pref", "avisos", "nuevo"]),
                    ("feedback all", ["opinion", "compartir", "all"]), ("data none", ["opinion", "compartir", "none"]), ("отзыв всё", ["opinion", "compartir", "всё"])):
    calls.clear(); reg["settings"](words)
    check(f"/settings {words} -> {' '.join(want)}", calls[-1] == want)
calls.clear(); reg["settings"]("packs")
check("/settings packs lists the packs", calls[-1] == ["paquetes", "list"])
for words, want in (("packs on empleo", ["paquetes", "on", "empleo"]), ("packs off empleo", ["paquetes", "off", "empleo"]), ("packs empleo yes", ["paquetes", "on", "empleo"]),
                    ("packs да empleo", ["paquetes", "on", "empleo"]), ("packs empleo нет", ["paquetes", "off", "empleo"])):
    calls.clear(); reg["settings"](words)
    check(f"/settings {words} -> {' '.join(want)}", calls[-1] == want)
out = reg["settings"]("")
check("/settings alone shows language, voice, alerts and the feedback level, then the usage", "/settings language" in out and any(c[:2] == ["opinion", "compartir"] for c in calls[-4:]) and out.count("Idioma: auto") >= 3)
for w, flag in (("позже", "--cuando-termine"), ("PORQUE", None)):
    calls.clear(); res = reg["sleep"](w)
    check(f"/sleep {w!r}", (calls and calls[-1] == ["dormir", "--usuario", flag]) if flag else ("/sleep now" in res and not calls))
calls.clear(); reg["settings"]("packs включить empleo")
check("Russian 'включить' switches a pack on", calls[-1] == ["paquetes", "on", "empleo"])
calls.clear(); reg["manual"]("полный")
check("/manual полный asks for the whole text", calls[-1] == ["manual", "--full"])
c2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(c2)      # a fresh copy: c._run is the stub above
c2.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(ValueError("embedded null byte"))
check("a NUL byte in what the person typed is answered, not raised", "No pude leer ese texto" in c2._run(["opinion", "a\x00b"]))

check("/settings with an unknown verb says so and shows the usage", "No entendí" in reg["settings"]("colors") and "/settings voice" in reg["settings"]("colors"))
check("/controles lists the commands in both languages", "/parar" in reg["controles"]() and "Управление" in reg["controles"]())
c.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("no such program"))
real = types.ModuleType("x")
exec(compile(open(spec.origin).read(), spec.origin, "exec"), real.__dict__)
check("a missing program is a line of text, not an exception", "No pude ejecutar" in real._run(["nope"]))
# skill packs: /paquetes lists, /paquete NOMBRE si|no switches, bad input is a usage line
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
