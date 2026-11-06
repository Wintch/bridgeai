#!/usr/bin/env python3
"""dormir.py: the request file it writes and when it refuses. No docker: python3 dormir_selftest.py"""
import contextlib, io, json, os, sys, tempfile
tmp = tempfile.mkdtemp()
os.environ["DORMIR_REQUEST"] = os.path.join(tmp, "dormir.json")
os.environ["DORMIR_JOBS_DIR"] = os.path.join(tmp, "jobs")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dormir as d

fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = d.main(list(argv))
    return code, buf.getvalue()

d.running_work = lambda: ["proceso 1: python3 /usr/local/bin/subs-fetch --lang ru-orig URL DIR"]
code, out = run()
check("work running: refuses (exit 3), lists it and writes NOTHING", code == 3 and "HAY TRABAJO" in out and not os.path.exists(d.REQ))
check("it tells the agent to ask and how to resume subtitles", "dormir --igual" in out and "subs-fetch --all" in out)
code, out = run("--igual")
req = json.load(open(d.REQ))
check("--igual writes a forced 'ahora' request and says what gets cut", code == 0 and req["mode"] == "ahora" and req["force"] is True and "OK" in out and "1 proceso" in out)
check("the request carries no language when the person has no /idioma", req.get("lang") == "")
prefs = os.path.join(tmp, "prefs.json")
os.environ["AIBRIDGE_PREFS"] = prefs
for chosen, want in (("ru", "ru"), ("en", "en"), ("es", "es"), ("auto", ""), ("xx", "")):
    json.dump({"lang": chosen}, open(prefs, "w"))
    run("--igual")
    check(f"the request carries the person's /idioma ({chosen} -> {want!r})", json.load(open(d.REQ)).get("lang") == want)
open(prefs, "w").write("not json")
run("--igual")
check("a broken prefs file means no language, not a crash", json.load(open(d.REQ)).get("lang") == "")
os.unlink(prefs)
code, out = run("--cancelar")
check("--cancelar removes it", code == 0 and not os.path.exists(d.REQ))
code, out = run("--cuando-termine")
req = json.load(open(d.REQ))
check("--cuando-termine writes that mode, not forced", code == 0 and req["mode"] == "cuando-termine" and req["force"] is False)
run("--cancelar")
d.running_work = lambda: []
code, out = run()
req = json.load(open(d.REQ))
check("nothing running: plain 'ahora' request, not forced, OK printed", code == 0 and req["mode"] == "ahora" and req["force"] is False and out.startswith("OK"))
run("--cancelar")
code, out = run("--igual")
req = json.load(open(d.REQ))
check("--igual with nothing visible running is STILL forced (a stuck gateway counter once dropped it twice)", code == 0 and req["force"] is True)
run("--cancelar")
code, out = run()
check("the OK line tells the agent the request is sent, not that it sleeps: the host writes the last message",
      "pedido de apagado enviado" in out and "no estás dormido todavía" in out and "«Dormido»" in out)
code, out = run("--usuario")
check("the person is told it is a request and that «Dormido» will be the last message", "Pedido recibido" in out and "«Dormido»" in out and "último mensaje" in out)
code, out = run("--estado")
check("--estado with nothing running also shows the pending sleep request", out.startswith("nada corriendo") and "Apagado pendiente: ahora" in out and code == 0)
check("a request is a timestamp the waker can age", isinstance(req["ts"], float))
# --parar against a real process family named like a download tool
import subprocess, time
os.makedirs(os.path.join(tmp, "bin"))
fake = os.path.join(tmp, "bin", "subs-fetch")
# 3071: a duration nothing else on the machine uses (another `sleep 300`, from a systemd timer here, made this test fail)
open(fake, "w").write("#!/bin/sh\nsleep 3071 &\nsleep 3071\n"); os.chmod(fake, 0o755)
_real_tops = d.family_tops
d.family_tops = lambda: [(p, c) for p, c in _real_tops() if tmp in c]   # NEVER touch a real download of whoever runs the test
proc = subprocess.Popen([fake, "--lang", "ru-orig", "https://example/@TeoriaX", "/workdir/descargas/teoria_x_subs"])
time.sleep(0.8)
d.running_work = d.__dict__["running_work"]
code, out = run("--parar", "nadaquecoincida")
check("--parar with a filter that matches nothing stops nothing", proc.poll() is None and "nada que detener" in out)
code, out = run("--parar", "teoria", "--usuario")
time.sleep(0.5)
check("--parar <channel> stops that family (parent and its children) and says how to resume", proc.poll() is not None and "Detuve 1" in out and "/retomar" in out)
check("no stray children left", not any(os.path.basename(c.split()[0] if c.split() else "") == "sleep" and "3071" in c for _, c in d.cmdlines()))
proc2 = subprocess.Popen([fake, "--lang", "en-orig", "https://example/@Other", "/workdir/descargas/other_subs"])
time.sleep(0.5)
code, out = run("--parar")
time.sleep(0.5)
check("--parar with no filter stops every download family", proc2.poll() is not None and "STOPPED" in out)
d.running_work = lambda: ["proceso 1: x"]
code, out = run("--usuario")
check("--usuario speaks to the person, with the three options as commands", code == 3 and "/dormir ya" in out and "/dormir luego" in out and "/parar" in out and "->" not in out)
print("\n".join(fails) or "dormir_selftest: all ok")
sys.exit(1 if fails else 0)
