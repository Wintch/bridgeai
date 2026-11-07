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
  /manual [completo]  the welcome manual: a short guide plus the PDF (`manual`)
  /opinion TEXTO      a note for the administrator, who reads it to improve the assistant; /opinion privado TEXTO keeps it only in the person's space
  /compartir [nada|uso|todo]   what the administrator may look at (`opinion compartir`); ops/chat_review.py and stack_usage.sh obey it
  /controles         this list

Names (2026-11-07): English is canonical and the older Spanish names keep working, hidden from the menu:
  /sleep [now|later|cancel]  = /dormir        /health = /estado (quick command)       /jobs [stop|resume] = /trabajos /parar /retomar
  /files TEXT                = /archivos      /feedback [TEXT|private TEXT|data none|usage|all] = /opinion /compartir
  /settings [language|voice|alerts|packs|feedback ...]  one place for the preferences (/idioma /voz /avisos /paquetes /paquete still work)
Any word in es, en or ru is accepted as an argument. These commands also run while the agent is answering (patches/busy_own_commands.py).

The names are Spanish and none clashes with a built-in command. Failure of any program is reported to the person in a line, never raised.
"""
import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)
DESCARGAS = os.environ.get("CONTROLS_DOWNLOADS", "/workdir/descargas")

HELP = (
    "Controles (los entiende el bot sin pasar por el modelo, también mientras contesta):\n"
    "/sleep — me apago de verdad (si hay trabajo te pregunto: /sleep now, /sleep later, /sleep cancel)\n"
    "/jobs — qué está corriendo y cómo van los subtítulos (/jobs stop corta las descargas, /jobs resume las retoma)\n"
    "/files texto — busco un archivo que te mandé, aunque ya no esté\n"
    "/settings — idioma, voz, avisos, grupos de habilidades y feedback\n"
    "/feedback — una nota para el administrador, o qué puede revisar (/feedback data none|usage|all)\n"
    "/manual — la guía de bienvenida, con el PDF\n"
    "Los nombres anteriores (/dormir, /trabajos, /parar, /retomar, /archivos, /paquetes, /opinion, /compartir) siguen funcionando.\n"
    "\n"
    "Управление: /sleep — выключиться, /jobs — что идёт (stop — остановить загрузки, resume — продолжить), /files — найти файл, "
    "/settings — настройки, /feedback — отзыв администратору и что он может смотреть, /manual — руководство (PDF). Старые названия работают."
)


def _run(argv, timeout=30):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip() or (r.stderr or "").strip() or "(sin salida)"
    except subprocess.TimeoutExpired:
        return f"{argv[0]} tardó más de {timeout} s: no sé el resultado, prueba /jobs."
    except OSError as exc:
        return f"No pude ejecutar {argv[0]}: {exc}"
    except (ValueError, UnicodeError):      # a NUL byte or a lone surrogate in what the person typed cannot become an argument
        return "No pude leer ese texto: tiene caracteres que no puedo pasar. Probá escribirlo de nuevo."


PREFS = os.environ.get("AIBRIDGE_PREFS", "/workdir/.prefs.json")
SLEEP_WORDS = {"ya": "ya", "ahora": "ya", "now": "ya", "сейчас": "ya", "luego": "luego", "despues": "luego", "después": "luego", "later": "luego",
               "потом": "luego", "позже": "luego", "cancelar": "cancelar", "cancel": "cancelar", "отмена": "cancelar", "": ""}
YES = ("si", "sí", "yes", "on", "да", "activar", "enable", "включить", "вкл")
NO = ("no", "off", "нет", "desactivar", "disable", "выключить", "выкл")
TXT = {
    "es": {"settings": "Ajustes (/settings):\n/settings language es|ru|en|auto — idioma\n/settings voice [nombre] — voz de los audios\n/settings alerts daily|new|off — avisos de ofertas de trabajo\n/settings packs [on|off NOMBRE] — grupos de habilidades\n/settings feedback none|usage|all — cuánto puede revisar el administrador",
           "bad_settings": "No entendí ese ajuste.", "sleep_bad": "No entendí. /sleep (me apago si no hay trabajo), /sleep now (corto todo), /sleep later (cuando termine) o /sleep cancel.",
           "packs_bad": "Uso: /settings packs (lista), /settings packs on NOMBRE o /settings packs off NOMBRE.", "files_empty": "Escribí qué buscás: /files johnny mnemonic"},
    "ru": {"settings": "Настройки (/settings):\n/settings language es|ru|en|auto — язык\n/settings voice [имя] — голос аудио\n/settings alerts daily|new|off — уведомления о вакансиях\n/settings packs [on|off ИМЯ] — группы навыков\n/settings feedback none|usage|all — что может смотреть администратор",
           "bad_settings": "Не понял эту настройку.", "sleep_bad": "Не понял. /sleep (выключусь, если нет работы), /sleep now (прервать всё), /sleep later (когда закончу) или /sleep cancel.",
           "packs_bad": "Использование: /settings packs (список), /settings packs on ИМЯ или /settings packs off ИМЯ.", "files_empty": "Напишите, что искать: /files johnny mnemonic"},
    "en": {"settings": "Settings (/settings):\n/settings language es|ru|en|auto — language\n/settings voice [name] — voice of the audio replies\n/settings alerts daily|new|off — job notices\n/settings packs [on|off NAME] — skill groups\n/settings feedback none|usage|all — how much the administrator may review",
           "bad_settings": "I did not understand that setting.", "sleep_bad": "I did not understand. /sleep (I stop if there is no work), /sleep now (cut everything), /sleep later (when it ends) or /sleep cancel.",
           "packs_bad": "Usage: /settings packs (list), /settings packs on NAME or /settings packs off NAME.", "files_empty": "Write what to look for: /files johnny mnemonic"},
}


def _lang():
    try:
        v = json.load(open(PREFS)).get("lang")
    except (OSError, ValueError, AttributeError):
        return "es"
    return v if v in TXT else "es"


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
        return "No entendí. /sleep (me apago si no hay trabajo), /sleep now (corto todo), /sleep later (cuando termine) o /sleep cancel."
    return _run(["dormir", "--usuario"] + flag, 30)


def cmd_paquetes(args=""):
    return _run(["paquetes", "list"], 30)


def cmd_paquete(args=""):
    parts = (args or "").strip().lower().split()
    if len(parts) != 2 or parts[1] not in ("si", "sí", "no", "on", "off"):
        return "Uso: /settings packs on NOMBRE (o off). Mira los nombres con /settings packs."
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
    return "Retomo los subtítulos de todos los canales ya empezados (uno tras otro, máximo 3 a la vez). Mira cómo van con /jobs; /jobs stop los detiene."


def cmd_archivos(args=""):
    if not args.strip():
        return "Escribí qué buscás: /files johnny mnemonic"
    out = _run(["archivo", "buscar"] + args.split(), 30)
    return "\n".join(l for l in out.splitlines() if not l.startswith("->"))


def cmd_manual(args=""):
    a = (args or "").strip().lower()
    return _run(["manual"] + (["--full"] if a in ("completo", "full", "todo", "полный", "всё", "все") else []), 120)


def cmd_opinion(args=""):
    return _run(["opinion"] + (args or "").split(), 20)


def cmd_compartir(args=""):
    return _run(["opinion", "compartir"] + (args or "").split()[:2], 20)


def cmd_sleep(args=""):
    w = (args or "").strip().lower()
    if w not in SLEEP_WORDS:
        return TXT[_lang()]["sleep_bad"]
    return cmd_dormir(SLEEP_WORDS[w])


def cmd_jobs(args=""):
    parts = (args or "").strip().split(None, 1)
    verb, rest = (parts[0].lower() if parts else ""), (parts[1] if len(parts) > 1 else "")
    if verb in ("", "list", "lista", "status", "estado"):
        return cmd_trabajos()
    if verb in ("stop", "parar", "cancel", "cancelar", "стоп", "остановить"):
        return cmd_parar(rest)
    if verb in ("resume", "retomar", "continue", "continuar", "продолжить"):
        return cmd_retomar()
    return "/jobs, /jobs stop [filtro], /jobs resume"


def cmd_files(args=""):
    if not args.strip():
        return TXT[_lang()]["files_empty"]
    return cmd_archivos(args)


def cmd_packs(args=""):
    parts = (args or "").strip().split()
    if not parts or parts[0].lower() in ("list", "lista", "ls"):
        return cmd_paquetes()
    verb = parts[0].lower()
    if len(parts) == 2 and verb in YES + NO:
        return cmd_paquete(f"{parts[1]} {'si' if verb in YES else 'no'}")
    if len(parts) == 2 and parts[1].lower() in YES + NO:      # the older order: /paquete NAME yes|no
        return cmd_paquete(f"{parts[0]} {'si' if parts[1].lower() in YES else 'no'}")
    return TXT[_lang()]["packs_bad"]


def cmd_feedback(args=""):
    return _run(["opinion"] + (args or "").split(), 20)


def cmd_settings(args=""):
    parts = (args or "").strip().split(None, 1)
    verb, rest = (parts[0].lower() if parts else ""), (parts[1] if len(parts) > 1 else "")
    if not verb:
        shown = [_run(["gateway", "pref", w], 20).splitlines()[0] for w in ("lang", "voice", "avisos")]
        shown.append(_run(["opinion", "compartir"], 20).splitlines()[0])
        return "\n".join(shown) + "\n\n" + TXT[_lang()]["settings"]
    if verb in ("language", "lang", "idioma", "язык"):
        return _run(["gateway", "pref", "lang"] + rest.split()[:1], 20)
    if verb in ("voice", "voz", "speaker", "голос"):
        return _run(["gateway", "pref", "voice"] + rest.split()[:1], 20)
    if verb in ("alerts", "avisos", "alertas", "уведомления"):
        return _run(["gateway", "pref", "avisos"] + rest.split()[:3], 20)
    if verb in ("packs", "pack", "paquetes", "paquete", "пакеты"):
        return cmd_packs(rest)
    if verb in ("feedback", "data", "share", "compartir", "datos", "отзыв", "отзывы", "данные"):
        # `compartir` is the strict form of opinion.py: a word that is not a level is refused, never filed as a note to the administrator
        return _run(["opinion", "compartir"] + rest.split()[:2], 20)
    return TXT[_lang()]["bad_settings"] + "\n\n" + TXT[_lang()]["settings"]


def cmd_controles(args=""):
    return HELP


def _traced(name, fn):
    def run(args=""):
        # WARNING so it shows in the default log: slash commands leave no trace in the chat history. /opinion is the person's own words
        # (private ones too): only the command name is logged, never the text.
        logger.warning("aibridge-controls: /%s %s", name, "" if name in ("opinion", "feedback") else (args or "")[:60])
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
                           ("manual", cmd_manual, "La guía de bienvenida (con PDF)"),
                           ("opinion", cmd_opinion, "Dejar una opinión para el administrador (o privada)"),
                           ("compartir", cmd_compartir, "Qué puede mirar el administrador: nada, uso o todo"),
                           ("sleep", cmd_sleep, "Sleep for real (now | later | cancel)"),
                           ("jobs", cmd_jobs, "What is running; stop or resume"),
                           ("files", cmd_files, "Find a file that was sent or downloaded"),
                           ("feedback", cmd_feedback, "Notes for the administrator and what he may review"),
                           ("settings", cmd_settings, "Language, voice, alerts, packs and feedback level"),
                           ("controles", cmd_controles, "Lista de controles")):
        ctx.register_command(name, _traced(name, fn), description=desc, args_hint="<texto>" if name in ("archivos", "parar", "dormir", "paquete", "opinion", "manual", "compartir", "sleep", "jobs", "files", "feedback", "settings") else "")
