#!/usr/bin/env python3
"""dormir: put this stack to sleep ON DEMAND, for real (2026-11-05).

  dormir                  nothing running -> asks the waker to stop this stack within a minute; work running -> lists it, changes nothing
  dormir --igual          sleep even though work is running (it is cut; say what gets cut and how to resume it)
  dormir --cuando-termine sleep as soon as the running work is done (no 10-minute idle wait)
  dormir --estado         only list what is running
  dormir --cancelar       withdraw a pending request
  dormir --parar [filtro] stop the running downloads/renders now (subs-fetch, yt-dlp, aria2c, ffmpeg, demucs, whisper); a filter
                          ("subs", a channel name) limits it. Does NOT sleep. This is what /parar runs.
  --usuario               plain text for the person instead of notes for the agent (what the Telegram commands print)

Why. On 2026-11-05 the person typed "dormite", "apagate", "shutdown", "poweroff" and the agent answered "Apagado. Hasta la
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


def write_request(mode, force):
    with open(REQ + ".tmp", "w") as f:
        json.dump({"ts": time.time(), "mode": mode, "force": force}, f)
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
        if not done:
            print("No había nada para detener." if user else "nada que detener")
            return 0
        print(("Detuve " + str(len(done)) + " trabajo(s):\n" + "\n".join("• " + d for d in done) +
               "\nPara seguir con los subtítulos: /retomar") if user else "STOPPED\n" + "\n".join(done))
        return 0
    if "--cancelar" in argv:
        try:
            os.unlink(REQ)
            print("Listo, cancelé el apagado." if user else "OK: pedido de apagado retirado")
        except OSError:
            print("No había ningún apagado pendiente." if user else "no había ningún pedido")
        return 0
    work = running_work()
    if "--estado" in argv:
        req = pending_request()
        extra = f"\nApagado pendiente: {req.get('mode')}" if req else ""
        print(("\n".join(work) if work else "nada corriendo") + extra)
        return 0
    if "--cuando-termine" in argv:
        write_request("cuando-termine", False)
        print(("Listo: me duermo apenas termine lo que corre." if work else "Listo: no hay nada corriendo, me duermo en menos de un minuto.")
              if user else "OK: me duermo apenas termine lo que corre" + ("" if work else " (ahora no hay nada: en menos de un minuto)") + ".")
        return 0
    if work and "--igual" not in argv:
        if user:
            print("Hay trabajo en marcha, no me apago todavía:\n" + "\n".join("• " + w for w in work) +
                  "\n\n/dormir ya — corto todo y me duermo\n/dormir luego — me duermo cuando termine\n/parar — solo detengo las descargas, sigo despierto")
        else:
            print("HAY TRABAJO CORRIENDO, no me apago todavía:")
            print("\n".join("  " + l for l in work))
            print("-> Dile a la persona qué se cortaría y pregunta: ¿corto y me apago (dormir --igual), espero a que termine "
                  "(dormir --cuando-termine) o sigo? Si es subs-fetch se retoma con: subs-fetch --all /workdir/descargas")
        return 3
    write_request("ahora", bool(work))
    if user:
        print("Listo, me duermo en menos de un minuto." + (f" Se cortan {len(work)} trabajo(s) en marcha: los subtítulos se retoman con /retomar." if work else "")
              + " Para despertarme, escríbeme.")
    else:
        print("OK: pedido de apagado enviado. El waker me detiene en menos de un minuto, apenas termine este turno."
              + (f" Se cortan {len(work)} proceso(s) en marcha." if work else ""))
        print("-> Ahora sí puedes decir que te duermes. Para despertarme, que la persona escriba un mensaje.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
