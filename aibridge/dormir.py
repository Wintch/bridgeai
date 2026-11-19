#!/usr/bin/env python3
"""dormir: put this stack to sleep ON DEMAND, for real.

  dormir                  nothing running -> asks the waker to stop this stack within a minute; work running -> lists it, changes nothing
  dormir --igual          sleep even though work is running (it is cut; say what gets cut and how to resume it)
  dormir --cuando-termine sleep as soon as the running work is done (no 10-minute idle wait)
  dormir --estado         only list what is running
  dormir --cancelar       withdraw a pending request
  dormir --parar [filtro] stop the running downloads/renders now (subs-fetch, yt-dlp, aria2c, ffmpeg, demucs, whisper); a filter
                          ("subs", a channel name) limits it. Does NOT sleep. This is what /parar runs.
  --usuario               plain text for the person instead of notes for the agent (what the Telegram commands print)

Why. The person once typed "dormite", "apagate", "shutdown", "poweroff" and the agent answered "Apagado. Hasta la
próxima." three times without running anything: the stack stayed up with seven downloads going. The agent cannot stop its own
container (no docker socket inside); the waker on the host can. This writes the request file the waker reads
(/workdir/.dormir.json, see ops/wake/waker.py). Say "me duermo" only when this printed OK.
"""
import json, os, re, signal, sys, time

REQ = os.environ.get("DORMIR_REQUEST", "/workdir/.dormir.json")
JOBS = os.environ.get("DORMIR_JOBS_DIR", "/workdir/jobs")
PROCS = os.environ.get("DORMIR_PROCESSES", "/root/.hermes/processes.json")
LONG = re.compile(r"(^|/)(subs-fetch|yt-dlp|aria2c|ffmpeg|demucs|whisper)( |$)")
SELF = os.getpid()
STOPPED = []        # pids the last parar() signalled


def cmdlines():
    out = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == SELF:
            continue
        try:
            raw = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace").strip()
            state = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0]
        except OSError:
            continue
        if raw and state not in "ZX":
            out.append((int(pid), raw))
    return out


def procs_table():
    procs = cmdlines()
    ppid = {}
    for p, _ in procs:
        try:
            ppid[p] = int(open(f"/proc/{p}/stat").read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            ppid[p] = 0
    return procs, ppid


def family_tops():
    """(pid, cmdline) of each long-running command whose parent is not itself one (a subs-fetch, not its yt-dlp children)."""
    procs, ppid = procs_table()
    long_pids = {p for p, c in procs if LONG.search(c) and "dormir" not in c}
    return [(p, c) for p, c in procs if p in long_pids and ppid.get(p) not in long_pids]


def descendants(root):
    procs, ppid = procs_table()
    out, frontier = [], [root]
    while frontier:
        cur = frontier.pop()
        for p, _ in procs:
            if ppid.get(p) == cur and p not in out:
                out.append(p)
                frontier.append(p)
    return out


def running_work():
    """Human lines about what a stop would cut. Only the top of each family, not every child."""
    lines = [f"proceso {p}: {c[:110]}" for p, c in family_tops()]
    try:
        registered = len([f for f in os.listdir(JOBS) if f.endswith(".json")])
    except OSError:
        registered = 0
    if registered:
        lines.append(f"{registered} trabajo(s) registrados en {JOBS} (avisos de fin pendientes)")
    return lines


def parar(filtro=None):
    """Stop the families (ancestors first, so nothing relaunches its children), wait, then force. Returns the stopped command lines."""
    tops = [(p, c) for p, c in family_tops() if not filtro or filtro in ("todo", "todos") or filtro.lower() in c.lower()
            or (filtro.lower() in ("subs", "subtitulos", "subtítulos") and ("subs-fetch" in c or "yt-dlp" in c))]
    victims = []
    for p, c in tops:
        victims.append((p, c))
    all_pids = []
    for p, _ in victims:
        all_pids += [p] + descendants(p)
    _, ppid = procs_table()
    up = set()
    for p, _ in victims:                      # the shell that started a victim is what the ledger may hold the pid of
        q, n = ppid.get(p), 0
        while q and q > 1 and n < 8 and q != SELF:
            up.add(q)
            q, n = ppid.get(q), n + 1
    STOPPED[:] = list(dict.fromkeys(all_pids + sorted(up)))
    ledger_stopped(STOPPED)                   # BEFORE the signals: the gateway that sees its child die writes its own end, and must find the stop flag
    for p in all_pids:
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(12):
        time.sleep(0.5)
        if not any(os.path.exists(f"/proc/{p}") and not open(f"/proc/{p}/stat").read().rsplit(")", 1)[1].split()[0] in "ZX" for p in all_pids):
            break
    for p in all_pids:
        try:
            if os.path.exists(f"/proc/{p}") and open(f"/proc/{p}/stat").read().rsplit(")", 1)[1].split()[0] not in "ZX":
                os.kill(p, signal.SIGKILL)
        except OSError:
            pass
    return [f"{p}: {c[:100]}" for p, c in victims]


def ledger_stopped(pids):
    """The work ledger (trabajos.py) is told these processes were stopped by the person, so the router does not report them as cut.
    Any failure is ignored: stopping must work without the ledger."""
    try:
        import importlib.machinery, importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        for path in ("/usr/local/bin/trabajos", os.path.join(here, "trabajos.py")):
            if os.path.isfile(path):
                spec = importlib.util.spec_from_file_location("aibridge_trabajos", path, loader=importlib.machinery.SourceFileLoader("aibridge_trabajos", path))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.stopped_by_person(pids)
                return
    except Exception:
        pass


def person_lang():
    """The person's reply language (/idioma: es, ru or en), so the host writes the last message in it; "" when they have none or chose auto."""
    try:
        lang = json.load(open(os.environ.get("AIBRIDGE_PREFS", "/workdir/.prefs.json"))).get("lang")
    except (OSError, ValueError, AttributeError):
        return ""
    return lang if lang in ("es", "ru", "en") else ""


def write_request(mode, force):
    with open(REQ + ".tmp", "w") as f:
        json.dump({"ts": time.time(), "mode": mode, "force": force, "lang": person_lang()}, f)
    os.replace(REQ + ".tmp", REQ)


def pending_request():
    try:
        return json.load(open(REQ))
    except (OSError, ValueError):
        return None


def main(argv):
    user = "--usuario" in argv
    argv = [a for a in argv if a != "--usuario"]
    if "--parar" in argv:
        rest = [a for a in argv if a != "--parar"]
        done = parar(rest[0] if rest else None)
        if done:
            ledger_stopped(STOPPED)
        if not done:
            print("No había nada para detener." if user else "nothing to stop")
            return 0
        print(("Detuve " + str(len(done)) + " trabajo(s):\n" + "\n".join("• " + d for d in done) +
               "\nPara seguir con los subtítulos: /jobs resume") if user else "STOPPED\n" + "\n".join(done))
        return 0
    if "--cancelar" in argv:
        try:
            os.unlink(REQ)
            print("Listo, cancelé el apagado." if user else "OK: shutdown request withdrawn")
        except OSError:
            print("No había ningún apagado pendiente." if user else "there was no request")
        return 0
    work = running_work()
    if "--estado" in argv:
        req = pending_request()
        extra = f"\nApagado pendiente: {req.get('mode')}" if req else ""
        print(("\n".join(work) if work else "nada corriendo") + extra)
        return 0
    if "--cuando-termine" in argv:
        write_request("cuando-termine", False)
        print(("Pedido recibido: sigo con lo que corre y, cuando termine y el contenedor esté apagado, te escribo «💤 Soñando»." if work
               else "Pedido recibido: no hay nada corriendo; te escribo «💤 Soñando» cuando esté apagado (hasta 1 minuto).")
              if user else "OK: request sent, the host stops me as soon as what is running ends" + ("" if work else " (nothing is running now: in under a minute)")
              + ". The «💤 Soñando» message is written by the host at the end; do not say that you are asleep already.")
        return 0
    if work and "--igual" not in argv:
        if user:
            print("Hay trabajo en marcha, no me apago todavía:\n" + "\n".join("• " + w for w in work) +
                  "\n\n/sleep now — corto todo y me duermo\n/sleep later — me duermo cuando termine\n/jobs stop — solo detengo las descargas, sigo despierto")
        else:
            print("WORK IS RUNNING, not shutting down yet:")
            print("\n".join("  " + l for l in work))
            print("-> Tell the person what would be cut and ask: shall I cut it and shut down (dormir --igual), wait until it ends "
                  "(dormir --cuando-termine) or carry on? If it is subs-fetch it resumes with: subs-fetch --all /workdir/descargas")
        return 3
    # --igual is the person's explicit "sleep anyway": forced even when this process list shows nothing, because the waker may still see
    # the gateway's counter above 0 (a leaked counter made "/dormir ya" an unforced request that was dropped twice)
    write_request("ahora", bool(work) or "--igual" in argv)
    if user:
        print("Pedido recibido. Cierro este turno y, cuando el contenedor esté realmente apagado (hasta 1 minuto), te escribo «💤 Soñando»: "
              "ese será mi último mensaje." + (f" Se cortan {len(work)} trabajo(s) en marcha: los subtítulos se retoman con /jobs resume." if work else ""))
    else:
        print("OK: shutdown request sent. The host stops the container in under a minute, as soon as this turn ends."
              + (f" {len(work)} running process(es) are cut." if work else ""))
        print("-> Say in one line that the request is sent, that you are not asleep yet and that the last message («💤 Soñando») "
              "is written by the host when the container has stopped. Write nothing after it and do not say \"shut down\" or \"until next time\".")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
