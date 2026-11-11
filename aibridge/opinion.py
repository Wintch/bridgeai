#!/usr/bin/env python3
"""opinion: what the person tells the system to improve it, and what they let the administrator look at.

  opinion TEXT...                 a note for the administrator, who reads it to improve the assistant
  opinion private TEXT...         a note only kept in the person's own space; nothing here reads it   (privado, приватно: same)
  opinion data                    show what the person shares                                         (compartir, datos: same)
  opinion data none|usage|all     change it                                                           (nada|uso|todo, ничего|использование|всё: same)

Installed in the image as /usr/local/bin/opinion; the /feedback and /settings slash commands (aibridge-controls plugin), the older /opinion and /compartir,
and the agent call the same code. Words in es, en and ru are accepted everywhere. State lives in /workdir (the person's folder, outside the image):
  .opiniones.jsonl            notes for the administrator (ops/opiniones.py lists them)
  .opiniones-privadas.jsonl   private notes (no tool of ours reads this file)
  .compartir.json             {"level": "nada"|"uso"|"todo", "ts": ...}; no file means "uso". The stored values never change: ops tools read them.

Levels, the same wording in the manual (manual/MANUAL.*.md):
  nada (none)    the administrator does not review how the person uses it, not even counts (the technical records the server needs stay, no conversation text)
  uso (usage)    (default) which tools were used, how many times, errors, timings, which model answered; never message text or file contents
  todo (all)     the administrator may read the conversation, only to improve the assistant; keys and long secret-like strings are masked
ops/chat_review.py and ops/stack_usage.sh read .compartir.json and refuse what the level does not allow.
A key pasted into a note is masked before it is written, and the person is told.
"""
import json
import os
import re
import sys
import time

DIR = os.environ.get("AIBRIDGE_OPINION_DIR", "/workdir")
PREFS = os.environ.get("AIBRIDGE_PREFS", "/workdir/.prefs.json")
LEVELS = ("nada", "uso", "todo")
LEVEL_WORDS = {"nada": "nada", "none": "nada", "no": "nada", "off": "nada", "nothing": "nada", "ninguno": "nada", "ninguna": "nada", "nunca": "nada",
               "ничего": "nada", "нет": "nada", "ничто": "nada", "никогда": "nada",
               "uso": "uso", "usage": "uso", "use": "uso", "использование": "uso", "использования": "uso",
               "todo": "todo", "todos": "todo", "all": "todo", "everything": "todo", "всё": "todo", "все": "todo"}
SHOWN = {"es": {"nada": "nada", "uso": "uso", "todo": "todo"}, "en": {"nada": "none", "uso": "usage", "todo": "all"},
         "ru": {"nada": "ничего", "uso": "использование", "todo": "всё"}}
PRIVATE_WORDS = ("privado", "privada", "private", "приватно", "личное", "личная")
DATA_WORDS = ("compartir", "data", "datos", "данные")
NOTE_WORDS = ("note", "nota", "заметка")   # /feedback note data loss was terrible: an explicit note, for text that starts with a command word
DEFAULT_LEVEL = "uso"
MAX_CHARS = 2000
KEY = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}|thk_[A-Za-z0-9_-]{16,}|[A-Za-z0-9_-]{40,})")

MSG = {
    "es": {
        "empty": "Escribí tu opinión después del comando. Por ejemplo: /feedback me gustó que me conteste rápido.\nSi querés que quede solo para vos: /feedback private TEXTO.\nPara elegir cuánto puede revisar el administrador: /feedback data none, usage o all.",
        "sent": "Anotado. El administrador la va a leer para mejorar el asistente. Gracias.",
        "private": "Anotado en tu espacio. Nadie la lee: es solo tuya.",
        "masked": "Ojo: había algo parecido a una clave y lo taché antes de guardarlo. Las claves no van en el chat.",
        "level": "Lo que compartís: {lvl}. {what}\nPara cambiarlo: /feedback data none, /feedback data usage o /feedback data all.",
        "set": "Listo, ahora compartís: {lvl}. {what}",
        "bad": "No entendí. Los niveles son: none (nada), usage (uso), all (todo). Probá /feedback data usage.\nSi querías dejar una nota que empieza con «data», escribí /feedback note data ...",
        "what": {
            "nada": "El administrador no revisa cómo me usás, ni siquiera los conteos. El servidor guarda lo técnico para funcionar, sin el texto de tus conversaciones.",
            "uso": "El administrador puede ver qué herramientas usé, cuántas veces, errores, tiempos y qué modelo contestó. Nunca el texto de tus mensajes ni el contenido de tus archivos.",
            "todo": "El administrador puede leer la conversación solo para mejorar el asistente. Las claves y los textos largos que parecen secretos se tachan.",
        },
        "note": "El administrador maneja el servidor: esto es un acuerdo sobre qué mira, no una barrera técnica.",
    },
    "ru": {
        "empty": "Напишите отзыв после команды. Например: /feedback мне понравилось, что вы быстро отвечаете.\nЕсли хотите оставить заметку только себе: /feedback private ТЕКСТ.\nЧтобы выбрать, сколько может смотреть администратор: /feedback data none, usage или all.",
        "sent": "Записано. Администратор прочитает это, чтобы улучшить ассистента. Спасибо.",
        "private": "Записано в вашем личном пространстве. Её никто не читает: она только ваша.",
        "masked": "Внимание: в тексте было что-то похожее на ключ, я зачеркнул это перед сохранением. Ключи не пишут в чат.",
        "level": "Чем вы делитесь: {lvl}. {what}\nЧтобы изменить: /feedback data none, /feedback data usage или /feedback data all.",
        "set": "Готово, теперь вы делитесь так: {lvl}. {what}",
        "bad": "Не понял. Уровни: none (ничего), usage (использование), all (всё). Попробуйте /feedback data usage.\nЕсли вы хотели оставить заметку, которая начинается со слова data, напишите /feedback note data ...",
        "what": {
            "nada": "Администратор не смотрит, как вы мной пользуетесь, даже счётчики. Сервер хранит только технические записи, нужные для работы, без текста ваших разговоров.",
            "uso": "Администратор может видеть, какие инструменты я использовал, сколько раз, ошибки, время и какая модель отвечала. Никогда не текст ваших сообщений и не содержимое файлов.",
            "todo": "Администратор может читать разговор, только чтобы улучшить ассистента. Ключи и длинные строки, похожие на секреты, зачёркиваются.",
        },
        "note": "Администратор управляет сервером: это договорённость о том, на что он смотрит, а не техническая преграда.",
    },
    "en": {
        "empty": "Write your opinion after the command. For example: /feedback I liked how fast it answers.\nIf you want it to stay only with you: /feedback private TEXT.\nTo choose how much the administrator may review: /feedback data none, usage or all.",
        "sent": "Noted. The administrator will read it to improve the assistant. Thank you.",
        "private": "Noted in your own space. Nobody reads it: it is only yours.",
        "masked": "Careful: something looked like a key and I blanked it before saving. Keys do not go in the chat.",
        "level": "What you share: {lvl}. {what}\nTo change it: /feedback data none, /feedback data usage or /feedback data all.",
        "set": "Done, you now share: {lvl}. {what}",
        "bad": "I did not understand. The levels are: none, usage, all. Try /feedback data usage.\nIf you meant a note that starts with \"data\", write /feedback note data ...",
        "what": {
            "nada": "The administrator does not review how you use me, not even counts. The server keeps the technical records it needs to run, with no conversation text.",
            "uso": "The administrator may see which tools I used, how many times, errors, timings and which model answered. Never the text of your messages or the content of your files.",
            "todo": "The administrator may read the conversation, only to improve the assistant. Keys and long secret-like strings are blanked.",
        },
        "note": "The administrator runs the server: this is an agreement about what he looks at, not a technical barrier.",
    },
}


def lang():
    try:
        v = json.load(open(PREFS)).get("lang")
    except (OSError, ValueError, AttributeError):
        return "es"
    return v if v in MSG else "es"


def level():
    """The person's sharing level; "uso" when nothing was chosen or the file is unreadable."""
    try:
        v = json.load(open(os.path.join(DIR, ".compartir.json"))).get("level")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_LEVEL
    return v if v in LEVELS else DEFAULT_LEVEL


def set_level(new):
    path = os.path.join(DIR, ".compartir.json")
    with open(path + ".tmp", "w") as f:
        json.dump({"level": new, "ts": int(time.time())}, f)
    os.replace(path + ".tmp", path)


def clean(text):
    """The note as it will be stored: control characters out, secret-like strings blanked, length capped. Returns (text, masked)."""
    text = "".join(c for c in text if c == "\n" or c >= " ").strip()[:MAX_CHARS]
    out = KEY.sub("[tachado]", text)
    return out, out != text


def write_note(text, private):
    text, masked = clean(text)
    name = ".opiniones-privadas.jsonl" if private else ".opiniones.jsonl"
    rec = {"ts": int(time.time()), "when": time.strftime("%Y-%m-%d %H:%M"), "lang": lang(), "level": level(), "text": text}
    path = os.path.join(DIR, name)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    # The gateway runs with umask 077, so the file would be root-only and ops/opiniones.py (the administrator's own account) could not read the
    # notes meant for him (it listed 0 notes). Those are 0644; the private ones stay 0600.
    try:
        os.chmod(path, 0o600 if private else 0o644)
    except OSError:
        pass
    return masked


def say_level(m, key):
    lvl = level()
    return m[key].format(lvl=SHOWN[lang()][lvl], what=m["what"][lvl]) + "\n" + m["note"]


def main(argv):
    m = MSG[lang()]
    if not argv:
        print(m["empty"] + "\n\n" + say_level(m, "level"))
        return 2
    head = argv[0].lower()
    # The level command. A privacy setting must never turn into a public note by a typo: `compartir` is always strict; `data` and its
    # synonyms are strict with one more word (a level or an error, never a note) and with none (show the level); with three or more words the
    # text is a note unless its first word is a level word (then it is ambiguous, so it is refused and explained).
    if head in DATA_WORDS:
        n = len(argv)
        second = argv[1].lower() if n > 1 else ""
        level_form = head == "compartir" or n <= 2 or second in LEVEL_WORDS
        if level_form:
            if n == 1:
                print(say_level(m, "level"))
                return 0
            new = LEVEL_WORDS.get(second)
            if new is None or n > 2:
                print(m["bad"])
                return 2
            set_level(new)
            print(say_level(m, "set"))
            return 0
    private = head in PRIVATE_WORDS
    words = argv[1:] if (private or head in NOTE_WORDS) else argv
    text = " ".join(words).strip()
    if not text:
        print(m["empty"])
        return 2
    try:
        masked = write_note(text, private)
    except OSError as exc:
        print(f"No pude guardar la nota ({exc}).")
        return 1
    print(m["private" if private else "sent"] + ("\n" + m["masked"] if masked else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
