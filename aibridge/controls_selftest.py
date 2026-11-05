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
    return {"subs-fetch": "chan_subs   10 files  en-orig  RUNNING  last 10 min 5  last hour 20\ntotal 10 files", "dormir": "nada corriendo", "archivo": "EXISTE  /x\n-> nota para el agente"}[argv[0]]
c._run = fake
reg = {}
c.register(types.SimpleNamespace(register_command=lambda name, fn, description="", args_hint="": reg.__setitem__(name, fn)))
check("six commands registered, all Spanish names", sorted(reg) == ["archivos", "controles", "dormir", "parar", "retomar", "trabajos"])
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
check("/controles lists the commands in both languages", "/parar" in reg["controles"]() and "Управление" in reg["controles"]())
c.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("no such program"))
real = types.ModuleType("x")
exec(compile(open(spec.origin).read(), spec.origin, "exec"), real.__dict__)
check("a missing program is a line of text, not an exception", "No pude ejecutar" in real._run(["nope"]))
print("\n".join(fails) or "controls_selftest: all ok")
sys.exit(1 if fails else 0)
