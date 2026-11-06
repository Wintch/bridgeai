"""Controls the person can always use, with no model in between (2026-11-05).

Why: on 2026-11-05 the person typed "stop", "dormite", "apagate", "shutdown" and "poweroff" at hernik. Hermes's own /stop only
interrupts the agent's current turn: the seven downloads the agent had started in the background kept running, and the agent
answered "Apagado. Hasta la próxima." to the others without stopping anything. A person must not depend on the model understanding
them to be able to stop work on their own machine.

How: Hermes runs plugin slash commands in the gateway BEFORE the model sees the message (gateway/run_inbound.py,
_hm_dispatch_quick_and_plugin_commands); the returned text is the reply. Each command here only calls one of the small programs
installed in the image (dormir, subs-fetch, archivo), so the agent and the person use the same code:

  /trabajos          what is running and how far the subtitles are (counts the files on disk)
  /parar [filtro]    stop the downloads/renders now (all, or "subs", or part of a channel name). Does not sleep.
  /dormir [ya|luego|cancelar]   go to sleep for real: asks the waker on the host to stop the container
  /retomar           start the subtitle round again (every channel already started)
  /archivos TEXTO    find a file that was sent or downloaded, even if it is gone
  /paquetes          the skill packs (base always on) and which ones are switched on
  /paquete NOMBRE si|no   switch a pack on or off (applies from the next conversation)
  /controles         this list

The names are Spanish and none clashes with a built-in command. Failure of any program is reported to the person in a line, never raised.
"""
import logging
import os
import subprocess

logger = logging.getLogger(__name__)
DESCARGAS = os.environ.get("CONTROLS_DOWNLOADS", "/workdir/descargas")

HELP = (
    "Controles (los entiende el bot sin pasar por el modelo):\n"
    "/trabajos — qué está corriendo y cómo van los subtítulos\n"
    "/parar — detengo las descargas ahora (/parar subs solo subtítulos, /parar nombre-de-canal uno)\n"
    "/dormir — me apago de verdad (si hay trabajo te pregunto: /dormir ya, /dormir luego, /dormir cancelar)\n"
    "/retomar — sigo con los subtítulos de todos los canales\n"
    "/archivos texto — busco un archivo que te mandé, aunque ya no esté\n"
    "/paquetes — qué grupos de habilidades tengo activos; /paquete nombre si (o no) los activa o desactiva\n"
    "\n"
    "Управление: /trabajos — что идёт, /parar — остановить загрузки, /dormir — выключиться, /retomar — продолжить, /archivos — найти файл"
)


def _run(argv, timeout=30):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip() or (r.stderr or "").strip() or "(sin salida)"
    except subprocess.TimeoutExpired:
        return f"{argv[0]} tardó más de {timeout} s: no sé el resultado, prueba /trabajos."
    except OSError as exc:
        return f"No pude ejecutar {argv[0]}: {exc}"


def cmd_trabajos(args=""):
    status = _run(["subs-fetch", "--status", DESCARGAS], 20)
    work = _run(["dormir", "--estado"], 20)
    return f"Subtítulos (archivos en disco):\n{status}\n\nProcesos en marcha:\n{work}"


def cmd_parar(args=""):
    argv = ["dormir", "--parar", "--usuario"] + ([args.strip().split()[0]] if args.strip() else [])
    return _run(argv, 40)


def cmd_dormir(args=""):
    a = (args or "").strip().lower()
    flag = {"ya": ["--igual"], "ahora": ["--igual"], "luego": ["--cuando-termine"], "despues": ["--cuando-termine"],
            "después": ["--cuando-termine"], "cancelar": ["--cancelar"], "": []}.get(a)
    if flag is None:
        return "No entendí. /dormir (me apago si no hay trabajo), /dormir ya (corto todo), /dormir luego (cuando termine) o /dormir cancelar."
    return _run(["dormir", "--usuario"] + flag, 30)


def cmd_paquetes(args=""):
    return _run(["paquetes", "list"], 30)


def cmd_paquete(args=""):
    parts = (args or "").strip().lower().split()
    if len(parts) != 2 or parts[1] not in ("si", "sí", "no", "on", "off"):
        return "Uso: /paquete NOMBRE si  (o no). Mira los nombres con /paquetes."
    return _run(["paquetes", "on" if parts[1] in ("si", "sí", "on") else "off", parts[0]], 90)


def cmd_retomar(args=""):
    status = _run(["subs-fetch", "--status", DESCARGAS], 20)
    if "RUNNING" in status or "subs-fetch" in _run(["dormir", "--estado"], 20):   # jobs started before the folder locks existed show only in the process list
        return "Ya hay canales descargando; no arranco otra ronda encima.\n" + status
    if "PAUSED" in status:
        return "Hay una pausa por límite del sitio (YouTube frenó las peticiones); no la salto.\n" + status
    try:
        log = open(os.path.join(DESCARGAS, ".subs-fetch.log"), "a")
        subprocess.Popen(["subs-fetch", "--all", DESCARGAS], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as exc:
        return f"No pude arrancar subs-fetch: {exc}"
    return "Retomo los subtítulos de todos los canales ya empezados (uno tras otro, máximo 3 a la vez). Mira cómo van con /trabajos; /parar los detiene."


def cmd_archivos(args=""):
    if not args.strip():
        return "Escribe qué buscas: /archivos johnny mnemonic"
    out = _run(["archivo", "buscar"] + args.split(), 30)
    return "\n".join(l for l in out.splitlines() if not l.startswith("->"))


def cmd_controles(args=""):
    return HELP


def _traced(name, fn):
    def run(args=""):
        logger.warning("aibridge-controls: /%s %s", name, (args or "")[:60])   # WARNING so it shows in the default log: slash commands leave no trace in the chat history
        return fn(args)
    return run


def register(ctx):
    for name, fn, desc in (("trabajos", cmd_trabajos, "Qué está corriendo y cómo van los subtítulos"),
                           ("parar", cmd_parar, "Detener las descargas ahora"),
                           ("dormir", cmd_dormir, "Apagarme de verdad (ya | luego | cancelar)"),
                           ("retomar", cmd_retomar, "Seguir con los subtítulos de todos los canales"),
                           ("archivos", cmd_archivos, "Buscar un archivo enviado o descargado"),
                           ("paquetes", cmd_paquetes, "Grupos de habilidades activos"),
                           ("paquete", cmd_paquete, "Activar o desactivar un grupo (nombre si|no)"),
                           ("controles", cmd_controles, "Lista de controles")):
        ctx.register_command(name, _traced(name, fn), description=desc, args_hint="<texto>" if name in ("archivos", "parar", "dormir", "paquete") else "")
