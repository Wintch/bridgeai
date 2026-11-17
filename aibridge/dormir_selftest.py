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
check("--parar <channel> stops that family (parent and its children) and says how to resume", proc.poll() is not None and "Detuve 1" in out and "/jobs resume" in out)
check("no stray children left", not any(os.path.basename(c.split()[0] if c.split() else "") == "sleep" and "3071" in c for _, c in d.cmdlines()))
proc2 = subprocess.Popen([fake, "--lang", "en-orig", "https://example/@Other", "/workdir/descargas/other_subs"])
time.sleep(0.5)
code, out = run("--parar")
time.sleep(0.5)
check("--parar with no filter stops every download family", proc2.poll() is not None and "STOPPED" in out)
d.running_work = lambda: ["proceso 1: x"]
code, out = run("--usuario")
check("--usuario speaks to the person, with the three options as commands", code == 3 and "/sleep now" in out and "/sleep later" in out and "/jobs stop" in out and "->" not in out)
# the work ledger is told which pids /jobs stop signalled, so the router does not report them as cut
os.environ["TRABAJOS_DIR"] = os.path.join(tmp, "ledger")
import importlib.util
_s = importlib.util.spec_from_file_location("tj", os.path.join(os.path.dirname(os.path.abspath(__file__)), "trabajos.py"))
tj = importlib.util.module_from_spec(_s); _s.loader.exec_module(tj)
_a = tj.start("render", "video", "gateway makevideo x /workdir/x.mp4", pid=os.getpid())
d.ledger_stopped([os.getpid()])
e = tj.load()["entries"][0]
check("ledger_stopped ends the entry as cortado, already told (the person asked)", e["state"] == "cortado" and e["notified"] is True and tj.aviso_peek(tj.load())["ids"] == [])
# /jobs stop marks the entries BEFORE the signals: the process that wrote its own end afterwards (a gateway that saw its child die)
# finds the flag, so the person is not told "failed" about something they stopped
proc3 = subprocess.Popen([fake, "--lang", "en-orig", "https://example/@Third", "/workdir/descargas/third_subs"])
time.sleep(0.5)
_b = tj.start("render two", "video", "gateway makevideo y /workdir/y.mp4", pid=proc3.pid)
code, out = run("--parar", "third")
time.sleep(0.5)
tj.finish(_b, 143, state="cortado", reason="stopped by a signal", notified=False)          # the gateway's own end record, after the stop
e3 = next(x for x in tj.load()["entries"] if x["id"] == _b)
check("the entry is cortado and told after the stop, and the gateway's later end record does not undo it",
      e3["state"] == "cortado" and e3["notified"] is True and e3["reason"] == "stopped by the person" and e3.get("stopped") is True and _b not in tj.aviso_peek(tj.load())["ids"])
check("the stop time is in the ledger", isinstance(tj.load().get("stopped_at"), int))
d.ledger_stopped(["not-a-pid"])
check("ledger_stopped swallows a bad argument", True)
print("\n".join(fails) or "dormir_selftest: all ok")
sys.exit(1 if fails else 0)
