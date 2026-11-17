#!/usr/bin/env python3
"""Patch Hermes so a reply that announces (or claims) an action without any tool call is re-prompted instead of ending the turn.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit, AFTER text_tool_call_retry.
Usage: announced_action_retry.py <path to agent/turn_final_response.py>

Why (web and Telegram chats): models of the nemotron class end a turn with prose like "Now I'll check X. First let me look
at what is there:", "Checking the link now..." or "I'll send you the working link in a minute" (the same in Spanish and
Russian) with finish_reason=stop and no tool call in that turn. Nothing happens and the person waits for work that was
never started. The twin failure is a claim of finished work ("Updated the list", "saved", "verified all links") in a turn
where no tool ran at all. Hermes's own stall guard only knows a few English "let me now ..." shapes and is off for most
providers, so this widens the net on the same re-prompt path.

It reuses the dropped-tool-call re-prompt that text_tool_call_retry already routes text answers into: the announcing reply
and the nudge are both flagged `_dropped_toolcall_nudge`, so the pair is never persisted and the finalization pop strips an
unanswered tail pair. Both rows also carry `_announced_action_nudge`, which is how "one nudge per turn" is told apart from
Hermes's own retry counter (it is read back from the turn's own messages, so nothing has to be reset between turns).

A reply is flagged when it is plain text (no tool calls), the agent has tools, and either
  1. "announce": its last non-empty line, outside code blocks, ends on a self-action the model is about to take: a trailing
     ':' after an action verb, a future/progressive self-action phrase ("let me check", "I'll look", "checking now",
     "voy a revisar", "reviso ahora", "сейчас проверю", "проверяю"), or a short wait filler ("one moment", "dame un
     minuto", "секунду"). Only the LAST sentence counts, a reply that merely mentions a plan earlier is left alone;
     offers and conditionals ("if you want, I'll ...", "let me know ...") are ignored; so are list items, table rows and
     replies that end with a code block (the colon there introduces the block);
  2. "claim": it says in the first person that work was done (updated/saved/added/verified/checked/wrote, in en/es/ru)
     and no tool ran since the turn's own user message. Replies that carry a code block are left alone (the "work" is the
     block itself).
A reply whose last line ends with '?' is a question to the person and is never flagged. Rule 2 never fires when a tool ran
in the turn. At most one such nudge per turn, never in a background review / curator / cron run (told apart by the agent's
write origin, turn origin and platform), and `agent.stall_guards: false` switches it off with Hermes's own guards.

Early alert (ops/early_alert.py): each re-prompt appends {"cat":"nudge","k":"announce"|"claim"} and a reply that would have been
re-prompted but whose turn already carried its nudge appends {"cat":"nudge_ignored"} to /workdir/.early-signals.jsonl. Categories
and counts only, never the reply or the person's text; the write can never fail the turn.

All word lists live in one place (the _ANN_* tables in HELPER below). Matching is done on lowercase text with curly quotes
and yo normalized; Spanish and Russian verbs are listed in the exact first-person forms so a plain statement ("la empresa
revisó tu CV") does not match.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: announced_action_retry"
PREREQ = "# aibridge-patch: text_tool_call_retry"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


HELPER = r'''_ANN_FLAG = "_announced_action_nudge"  # aibridge-patch: announced_action_retry
_ANN_SIGNALS = "/workdir/.early-signals.jsonl"   # early alert sink (ops/early_alert.py): categories and counts, never text
_ANN_SIG_RECENT = []

# --- word tables: the ONLY place to add a verb or a phrase (all lowercase, alternations for re) ------------------------
# English: base verbs after "let me" / "I'll" / "I'm going to".
_ANN_EN_VERBS = ("check|look|see|verify|try|find|fetch|open|search|run|pull|read|review|go|dig|test|get|grab|send|add|update"
                 "|save|start|set|fix|confirm|make|put|write|create|build|do|figure|investigate|examine|inspect|double-check"
                 "|recheck|re-check|take a look|share|give|provide|prepare|compile|gather|load|download|upload|install|scan"
                 "|list|show|come back|follow up|fill|apply|edit|change|remove|delete|generate|compare|analy[sz]e|calculate")
# "let's" invites the person along ("let's go", "let's start"), so only verbs the assistant itself performs count after it.
_ANN_EN_LETS = ("check|look|see|verify|try|find|open|search|run|review|test|fetch|read|take a look|dig|examine|inspect"
                "|double-check|compare|analy[sz]e|calculate")
# A verb followed by "to be brief" / "to keep it short" is a remark about the reply, not an action ("I'll try to be brief:").
_ANN_EN_V = (rf"(?:{_ANN_EN_VERBS})\b(?!\s+to\s+(?:be|keep|stay|make it|explain|answer|help|say|put it|walk you|summari[sz]e)\b)")
# Progressive forms: list A is an announcement by itself; list B ("writing", "sending", ...) is too common in drafted
# letters and ordinary prose ("I am writing to apply"), so it needs "now" / "currently" next to it.
_ANN_EN_GERUNDS = ("checking(?!\\s+in\\b)(?!\\s+out\\b(?!\\s+(?:the|your|this|that|these|those|it|them)\\b))"  # not "checking in/out"
                   "|verifying|searching|fetching|opening|reviewing|testing|updating|saving|preparing|pulling"
                   "|gathering|generating|installing|downloading|uploading|running|looking(?! forward| for)")
_ANN_EN_GERUNDS_WEAK = "sending|writing|reading|trying|working|going|building|creating"
# Spanish: infinitives (clitics like -lo/-me/-te are allowed after them), exact first-person presents, gerunds.
_ANN_ES_VERBS = ("revisar|buscar|ver|verificar|comprobar|abrir|probar|leer|consultar|preparar|enviar|mandar|pasar|armar|crear"
                 "|generar|agregar|añadir|actualizar|guardar|escribir|hacer|investigar|analizar|chequear|mirar|intentar"
                 "|descargar|cargar|ejecutar|correr|iniciar|empezar|comenzar|confirmar|comparar|calcular|instalar|corregir"
                 "|editar|cambiar|aplicar|eliminar|borrar|poner|dar|compilar|juntar|recopilar|terminar|continuar|seguir"
                 "|responder|mostrar|compartir|fijar")
_ANN_ES_PRESENT = ("reviso|verifico|chequeo|compruebo|consulto|preparo|genero|agrego|actualizo|guardo|investigo|analizo"
                   "|descargo|ejecuto|empiezo|confirmo|corrijo|aplico|te paso|te envío|te envio|te mando|te aviso"
                   "|te muestro|te comparto")
_ANN_ES_PRESENT_AMBIGUOUS = ("busco|miro|abro|pruebo|cambio|edito|añado|escribo|armo")  # only right after ahora/ya
_ANN_ES_GERUNDS = ("revisando|verificando|buscando|chequeando|comprobando|consultando|abriendo|probando|leyendo|preparando"
                   "|generando|actualizando|guardando|enviando|analizando|investigando|descargando|ejecutando|armando")
_ANN_ES_WAIT = ("un (?:momento|momentito|segundo|segundito|minuto|minutito|ratito)|dame (?:un|una) (?:momento|momentito"
                "|segundo|minuto|minutito|ratito)|espera(?:me)? un (?:momento|segundo|minuto)|ya vuelvo|ya regreso|enseguida"
                "|ahorita|en un momento|en unos minutos|en un minuto|en breve|ahora mismo")
# Russian: exact first-person future / present forms (yo written as e), imperfective forms only count at a sentence start
# or right after a time word.
_ANN_RU_FUTURE = ("проверю|посмотрю|найду|открою|загружу|отправлю|пришлю|дам|сделаю|добавлю|обновлю|сохраню|запущу|прочитаю"
                  "|изучу|гляну|уточню|подготовлю|соберу|выполню|попробую|запишу|покажу|скину|кину|вышлю|напишу|свяжусь"
                  "|разберусь|исправлю|создам|переведу|подберу|поищу|скачаю|установлю|протестирую|подтвержу|сравню"
                  "|посчитаю|составлю|верну|вернусь|отвечу|дополню")
_ANN_RU_PRESENT = ("проверяю|смотрю|ищу|открываю|загружаю|отправляю|читаю|изучаю|добавляю|обновляю|сохраняю|запускаю"
                   "|уточняю|готовлю|собираю|выполняю|пробую|записываю|показываю|разбираюсь|исправляю|создаю|подбираю"
                   "|скачиваю|устанавливаю|тестирую|подтверждаю|сравниваю|составляю|делаю|пишу|работаю над")
_ANN_RU_LETS = ("посмотрим|проверим|глянем|попробуем|найдем|откроем|начнем|разберем|посмотреть|проверить|найти|открыть"
                "|взглянуть|глянуть|поискать|уточнить|разобраться|попробовать|сделать|прочитать|изучить|подготовить"
                "|минуту|минутку|секунду|секундочку|время")
_ANN_RU_WAIT = ("одну минуту|одну секунду|минутку|минуточку|секунду|секундочку|подождите|через (?:минуту|минутку|секунду"
                "|пару минут|несколько минут|\\d+ (?:минут|секунд|мин))|сейчас|скоро")
# Wait fillers count only as a SHORT sentence (a long one such as "the file will be ready in 3 minutes" is a fact).
_ANN_FILLER_MAX = 40
_ANN_EN_WAIT = ("one (?:moment|sec(?:ond)?|minute)|just a (?:moment|sec(?:ond)?|minute)|give me (?:a |one )?(?:moment|minute"
                "|second|sec)|hold on|hang on|hang tight|stand by|bear with me|be right back|back in a (?:moment|minute"
                "|sec(?:ond)?)|in a (?:minute|moment|sec(?:ond)?)|in a few (?:minutes|moments|seconds)|shortly|right away"
                "|momentarily")

# First-person claims of finished work. A claim must OPEN its sentence (after a few filler words) and, for a finite verb, be
# followed by a definite object that points at the assistant's own work ("updated the list", "verified all links"). That keeps
# drafted first-person text (a cover letter, CV advice: "In my previous role I created a dashboard") from reading as a claim.
# English needs the pronoun (or a sentence-initial participle: "Updated the list"); Spanish and Russian carry the person in the verb.
_ANN_EN_DONE = ("updated|saved|added|verified|checked|wrote|written|created|fixed|sent|removed|deleted|installed|ran|run"
                "|tested|confirmed|reviewed|edited|changed|generated|downloaded|uploaded|configured|applied|scheduled|fetched")
_ANN_EN_DONE_PARTICIPLE = "updated|saved|added|verified|checked|created|fixed|sent|removed|deleted|installed|tested|confirmed"
_ANN_ES_DONE = ("actualicé|guardé|agregué|añadí|verifiqué|revisé|escribí|creé|corregí|envié|eliminé|instalé|probé|confirmé"
                "|edité|cambié|generé|descargué|configuré|apliqué|comprobé|chequeé|he (?:actualizado|guardado|agregado"
                "|añadido|verificado|revisado|escrito|creado|corregido|enviado|eliminado|instalado|probado|confirmado"
                "|editado|cambiado|generado|descargado|configurado|aplicado|comprobado)")
_ANN_ES_DONE_PARTICIPLE = "actualizad[oa]s?|guardad[oa]s?|agregad[oa]s?|añadid[oa]s?|verificad[oa]s?|revisad[oa]s?"
_ANN_RU_DONE = ("обновил[аи]?|сохранил[аи]?|добавил[аи]?|проверил[аи]?|записал[аи]?|создал[аи]?|исправил[аи]?|отправил[аи]?"
                "|удалил[аи]?|установил[аи]?|протестировал[аи]?|подтвердил[аи]?|изменил[аи]?|сгенерировал[аи]?|скачал[аи]?"
                "|настроил[аи]?|применил[аи]?|загрузил[аи]?|внес(?:ла)?")
_ANN_RU_DONE_PARTICIPLE = "обновлен[аоы]?|сохранен[аоы]?|добавлен[аоы]?|проверен[аоы]?|записан[аоы]?"
_ANN_OPEN_FILLER = (r"(?:(?:готово|да|уже|также|теперь|только что|вот|ок|окей|хорошо|listo|hecho|ya|también|ahora"
                    r"|además|done|ok|okay|and|also|then|great news|good news|great|perfect|all set|so)[,:!.\s-]+){0,3}")
# Definite objects after a finite claim verb: the list, your file, all links, it.
_ANN_EN_OBJ = r"\s+(?:the|your|this|that|these|those|all|it|them|everything|both|each|every|its)\b"
_ANN_ES_OBJ = (r"\s+(?:el|la|los|las|lo|tu|tus|todo|todos|todas|este|esta|estos|estas|ese|esa|esos|esas|ambos|ambas|cada)\b")
_ANN_RU_OBJ = (r"\s+(?:все|всё|ваш\w*|твой|твою|твои|твое|этот|эту|эти|тот|ту|те|его|ее|их|файл\w*|список\w*|ссылк\w*"
               r"|заметк\w*|профил\w*|таблиц\w*|документ\w*|резюме|данные|настройк\w*|изменени\w*|код|скрипт\w*|вакансии)\b")
# Drafted text and career narrative: a reply that carries a letter frame (salutation / formal sign-off line) or tells a work
# history ("in my previous role I ...") is content for the person, not a report on this turn's work. Matched per line.
_ANN_DRAFT = (r"^\s*(?:dear\b|to whom it may concern|estimad[oa]s?\b|a quien corresponda|уважаем\w*)"
              r"|^\s*(?:sincerely|yours (?:sincerely|faithfully)|(?:best|kind|warm) regards|regards|atentamente|cordialmente"
              r"|saludos cordiales|un saludo|с уважением|с наилучшими пожеланиями)\s*[,.!]?\s*$")
_ANN_NARRATIVE = (r"\b(?:in|at|during) my (?:previous|last|former|prior|current|first|earlier) (?:role|job|position|company|post"
                  r"|employer|internship|time)\b|\bmy (?:previous|last|former) (?:role|job|position|employer)\b"
                  r"|\byears of experience\b|\bwhen i worked\b|\bduring my (?:time|tenure|career|studies)\b"
                  r"|\ben mi (?:puesto|trabajo|rol|empleo|cargo|experiencia) (?:anterior|previo)\b|\ben mi (?:último|ultimo|anterior)\b"
                  r"|\bdurante mi (?:tiempo|carrera|trayectoria)\b|\ba[nñ]os de experiencia\b|\bcuando trabaj[ée]\b"
                  r"|\b(?:на|в) (?:моей |моем )?(?:предыдущей|прошлой|последней|прежней) (?:работе|должности|роли|компании)\b"
                  r"|\bв (?:моем )?предыдущем (?:месте|опыте)\b|\bлет опыта\b|\bкогда я работал\w*\b|\bза время работы\b")
# Quoted spans are examples or drafts ("mention what you built, e.g. 'I created X'"), never a report.
_ANN_QUOTED = r'"[^"\n]{0,300}"|“[^”\n]{0,300}”|«[^»\n]{0,300}»'
# A bullet is judged only when a non-bullet line says the bullets are what was done ("Here is what I did:").
_ANN_LIST_CONTEXT = (r"\bwhat i(?:'ve)? (?:did|done)\b|\bhere(?:'s| is| are) (?:what|the changes|a summary)|\bchanges made\b"
                     r"|\bsummary of (?:the )?changes\b|\bi(?:'ve| have) done\b|\blo que hice\b|\bcambios realizados\b"
                     r"|\bhe hecho\b|\bчто (?:я )?сделал\w*|\bсделано\b|\bготово\b|\bвот что\b")
# Rule 2 reads only short replies: a long reply is content (a draft, advice, a report), not a bare claim.
_ANN_CLAIM_MAX = 700

# Offers and conditionals are never announcements.
_ANN_NOT_ANNOUNCEMENT = (r"^(?:if|when|once|unless|should|in case|whenever|si|cuando|una vez|en caso de|если|когда|как только)\b"
                         r"|\bif you(?:'d| would)? (?:want|like|need|prefer|wish)\b|\blet me know\b|\bwould you like\b"
                         r"|\bdo you want\b|\bfeel free\b|\bsi (?:quieres|querés|necesitas|gustas|prefieres|deseas)\b"
                         r"|\bavísame\b|\bavisame\b|\bdime\b|\bhazme saber\b|\bquieres que\b|\bquerés que\b|\bte gustaría\b"
                         r"|\bесли (?:хотите|хочешь|нужно|надо|нужен|нужна|понадобится|желаете|угодно)\b|\bдайте знать\b"
                         r"|\bдай знать\b|\bскажите\b|\bхотите\b|\bмогу\b"
                         r"|\b(?:когда вы|как только вы|после того как вы|when you|once you|after you|cuando me|cuando nos"
                         r"|cuando tú|una vez que me|una vez que nos)\b")

# A promise that waits on the PERSON is not a promise to act now ("I'll send it as soon as you confirm"). The conditional word may
# sit anywhere in the sentence; it only excludes the sentence when the clause after it names the person (second person, or a
# Spanish/Russian second-person form). A clause about the assistant's own work ("I'll send the link once I find it") stays an
# announcement. Spanish subjunctives are ambiguous between persons, so only explicit markers and common second-person forms count.
_ANN_COND_EN = r"\b(?:as soon as|after|until|once|when|whenever|if|unless)\b"
_ANN_COND_ES = r"\b(?:cuando|en cuanto|apenas|después de que|despues de que|una vez que|mientras no|si)\b"
_ANN_COND_RU = r"\b(?:когда|как только|после того как|пока не|если)\b"
_ANN_PERSON_EN = r"\b(?:you|your|you're|you'll|you've|yours|they|them|the (?:person|user))\b"
_ANN_PERSON_ES = (r"\b(?:tú|usted|ustedes|vos|me|te|nos|tu|tus|su|sus|tengas|puedas|quieras|estés|estes|digas|pases|confirmes"
                  r"|envíes|envies|mandes|respondas|indiques|elijas|decidas|avises|apruebes|autorices|subas|compartas|adjuntes"
                  r"|sepas|vuelvas|termines|tengan|puedan|quieran|digan|pasen|confirmen)\b")
_ANN_PERSON_RU = r"\b(?:вы|ты|вам|тебе|вас|тебя|ваш\w*|твой|твою|твои|твое)\b|\b\w{2,}(?:ешь|ете|ишь|ите)\b"

_ANN_TIME = r"(?:сейчас|уже|теперь|прямо сейчас|пока|еще|сразу|также|тоже)"
_ANN_LEAD = r"(?:(?:хорошо|ок|окей|так|итак|ага|да|ладно|отлично|понял|поняла|ok|okay|alright|now|bien|vale|listo)[,!.]?\s+)*"
_ANN_ES_CLITIC = r"(?:me|te|se|lo|la|los|las|le|les|melo|telo|selo)?"


def _ann_compile(*pats):
    import re as _re
    return tuple(_re.compile(p) for p in pats)


_ANN_ANNOUNCE = _ann_compile(
    # let me / I'll / I'm going to + verb
    rf"\b(?:let me|let us)\s+(?:now |just |first |also |quickly |go ahead and |double[- ])*{_ANN_EN_V}",
    rf"\blet's\s+(?:now |just |first |also |quickly |double[- ])*(?:{_ANN_EN_LETS})\b",
    rf"\b(?:i(?:'ll| will|'m going to| am going to|'m about to| am about to)|we(?:'ll| will))\s+(?:now |just |first |then "
    rf"|also |quickly |go ahead and |shortly |promptly )*{_ANN_EN_V}",
    rf"\b(?:i am|i'm|we are|we're)\s+(?:now |just |currently |still |busy )*(?:{_ANN_EN_GERUNDS})\b",
    rf"\b(?:i am|i'm|we are|we're)\s+(?:right now |now |just |currently )(?:{_ANN_EN_GERUNDS_WEAK})\b",
    rf"\b(?:i am|i'm|we are|we're)\s+(?:{_ANN_EN_GERUNDS_WEAK})\b[^.!?]{{0,60}}\b(?:now|right now|shortly)\b",
    rf"^{_ANN_LEAD}(?:{_ANN_EN_GERUNDS})\b",
    rf"^{_ANN_LEAD}(?:{_ANN_EN_GERUNDS_WEAK})\b[^.!?]{{0,60}}\b(?:now|right now|shortly)\b",
    # Spanish
    rf"\b(?:voy a|vamos a|me pongo a|procedo a)\s+(?:ahora |ya |primero |también |a )*(?:{_ANN_ES_VERBS}){_ANN_ES_CLITIC}\b",
    rf"\b(?:déjame|dejame|permíteme|permiteme)\s+(?:ahora |primero |ya )*(?:{_ANN_ES_VERBS}){_ANN_ES_CLITIC}\b",
    rf"\b(?:ya|ahora|enseguida|ahorita|ahora mismo|en un momento|en breve|ya mismo)\b[^.!?]{{0,40}}\b(?:{_ANN_ES_PRESENT}"
    rf"|{_ANN_ES_PRESENT_AMBIGUOUS})\b",
    rf"\b(?:{_ANN_ES_PRESENT})\b[^.!?]{{0,40}}\b(?:ya|ahora|ahora mismo|enseguida|ahorita|en un momento|en un rato"
    rf"|en unos minutos|en un minuto|en breve|más tarde|luego)\b",
    rf"\b(?:estoy|estamos)\s+(?:ahora |ya |todavía )*(?:{_ANN_ES_GERUNDS})\b",
    rf"^{_ANN_LEAD}(?:{_ANN_ES_GERUNDS})\b",
    # Russian (text is yo-normalized)
    rf"(?:^|[\s,;:—–-])(?:{_ANN_RU_FUTURE})(?=[\s.,!…:;—–-]|$)",
    rf"(?:^{_ANN_LEAD}|\b{_ANN_TIME}\s+)(?:{_ANN_RU_PRESENT})\b",
    rf"\b(?:давай(?:те)?|позвольте|разрешите|дай(?:те)? мне)\s+(?:мне |я |еще |сейчас |сначала |теперь |пока )*"
    rf"(?:{_ANN_RU_LETS})\b",
)
_ANN_COND_PAIRS = tuple((_ann_compile(c)[0], _ann_compile(p)[0]) for c, p in (
    (_ANN_COND_EN, _ANN_PERSON_EN), (_ANN_COND_ES, _ANN_PERSON_ES), (_ANN_COND_RU, _ANN_PERSON_RU)))


def _ann_waits_on_person(sentence):
    """True when a conditional clause anywhere in the (normalized) sentence depends on the person."""
    for cond, person in _ANN_COND_PAIRS:
        for m in cond.finditer(sentence):
            if person.search(sentence, m.end()):
                return True
    return False


_ANN_FILLER = _ann_compile(rf"\b(?:{_ANN_EN_WAIT})\b", rf"\b(?:{_ANN_ES_WAIT})\b", rf"\b(?:{_ANN_RU_WAIT})\b")
_ANN_COLON_VERB = _ann_compile(
    rf"\b{_ANN_EN_V}", rf"\b(?:{_ANN_ES_VERBS}){_ANN_ES_CLITIC}\b",
    rf"\b(?:{_ANN_ES_PRESENT}|{_ANN_ES_PRESENT_AMBIGUOUS})\b", rf"\b(?:{_ANN_RU_FUTURE}|{_ANN_RU_PRESENT}|{_ANN_RU_LETS})\b")
_ANN_CLAIM = _ann_compile(
    rf"^{_ANN_OPEN_FILLER}(?:i|we)(?:'ve|'d| have| had)?(?: (?:just|also|now|already|successfully|then|all))*\s+(?:{_ANN_EN_DONE})\b{_ANN_EN_OBJ}",
    rf"^{_ANN_OPEN_FILLER}(?:{_ANN_EN_DONE_PARTICIPLE})\b",
    rf"^{_ANN_OPEN_FILLER}(?:yo )?(?:ya |también )?(?:{_ANN_ES_DONE})\b{_ANN_ES_OBJ}",
    rf"^{_ANN_OPEN_FILLER}(?:\w+ )?(?:{_ANN_ES_DONE_PARTICIPLE})\b",
    rf"^{_ANN_OPEN_FILLER}(?:я )?(?:уже |также )?(?:{_ANN_RU_DONE})\b{_ANN_RU_OBJ}",
    rf"^{_ANN_OPEN_FILLER}(?:все |всё )(?:я )?(?:уже )?(?:{_ANN_RU_DONE})\b",
    rf"^{_ANN_OPEN_FILLER}(?:\w+ )?(?:{_ANN_RU_DONE_PARTICIPLE})\b",
)


def _ann_norm(s):
    return s.lower().replace("’", "'").replace("‘", "'").replace("ё", "е")


def _ann_signal(cat, n=1, **small):  # aibridge-patch: announced_action_retry
    """One early-alert line {"ts","cat","n"[,"k"],"src"} (a copy of router.signal(): early_signals_selftest.py keeps them in step).
    Only a known category and a short [a-z0-9_] enum are written, O_NOFOLLOW + O_APPEND, 40 lines a minute at most. Never raises."""
    import json as _json, os as _os, re as _re, time as _time
    try:
        now = _time.time()
        _ANN_SIG_RECENT[:] = [t for t in _ANN_SIG_RECENT if now - t < 60]
        if cat not in ("nudge", "nudge_ignored") or len(_ANN_SIG_RECENT) >= 40:
            return False
        rec = {"ts": int(now), "cat": cat, "n": max(1, min(int(n), 20))}
        if isinstance(small.get("k"), str) and _re.match(r"^[a-z0-9_]{1,16}$", small["k"]):
            rec["k"] = small["k"]
        rec["src"] = "patch"
        try:
            if _os.lstat(_ANN_SIGNALS).st_size > 200000:
                _os.replace(_ANN_SIGNALS, _ANN_SIGNALS[:-6] + ".1.jsonl")
        except OSError:
            pass
        fd = _os.open(_ANN_SIGNALS, _os.O_WRONLY | _os.O_APPEND | _os.O_CREAT | _os.O_NOFOLLOW, 0o644)
        try:
            _os.fchmod(fd, 0o644)
            _os.write(fd, (_json.dumps(rec, separators=(",", ":")) + "\n").encode())
        finally:
            _os.close(fd)
        _ANN_SIG_RECENT.append(now)
        return True
    except Exception:
        return False


def _ann_verdict(kind, nudged):  # aibridge-patch: announced_action_retry
    """The verdict of _announced_action. A turn that already carried its one nudge is not nudged again: the reply ends with the
    promise, and that is an early-alert signal of its own (the model ignored the re-prompt)."""
    if nudged:
        _ann_signal("nudge_ignored")
        return None
    return kind


def _announced_background(agent):  # aibridge-patch: announced_action_retry
    """True for a background review / curator / cron fork: nobody waits on its reply, so it is never re-prompted."""
    return (getattr(agent, "_memory_write_origin", "assistant_tool") != "assistant_tool"
            or bool(getattr(agent, "_turn_origin", None))
            or getattr(agent, "platform", None) in ("cron", "curator"))


def _announced_action(text, agent, messages, nudge_texts=()):  # aibridge-patch: announced_action_retry
    """"announce" / "claim" when a plain-text final answer should be re-prompted (see the patch docstring), else None."""
    import re as _re
    if not isinstance(text, str) or not text.strip() or not getattr(agent, "valid_tool_names", None):
        return None
    if not getattr(agent, "_stall_guards", True) or _announced_background(agent):
        return None
    tail_text = text[-20000:]
    prose = _re.sub(r"```.*?(?:```|$)", "", tail_text, flags=_re.S)
    lines = [ln for ln in prose.splitlines() if ln.strip()]
    if not lines:
        return None
    last = lines[-1].strip()
    # Tail without markdown marks, trailing emoji and closing quotes: the shape of the last sentence is judged on this.
    core = _re.sub(r"[\s☀-➿\U0001f300-\U0001faff️*_`~)\]\"'»”]+$", "", last)
    if core.endswith(("?", "？")):
        return None
    nudged, tools = False, 0
    for m in reversed(messages or ()):
        if not isinstance(m, dict):
            continue
        if m.get(_ANN_FLAG):
            nudged = True
        # The turn starts at the last user row that is not retry scaffolding.
        if m.get("role") == "user" and not m.get("_dropped_toolcall_nudge") and m.get("content") not in nudge_texts:
            break
        if m.get("role") == "tool" or (m.get("role") == "assistant" and m.get("tool_calls")):
            tools += 1
    has_code = "```" in tail_text
    ends_in_code = tail_text.rstrip().endswith("```") or tail_text.count("```") % 2 == 1
    if not ends_in_code and not _re.match(r"^\s*(?:[-*•]\s|[#|]|\d+[.)]\s)", last):
        sentences = [s for s in _re.split(r"(?<=[.!?…:])\s+", _re.sub(r"^[\s>*_`~#-]+", "", core)) if s.strip()]
        sent = _ann_norm(sentences[-1]) if sentences else ""
        sent_plain = _re.sub(r"[^\w\s]+$", "", sent).strip()
        if (sent_plain and len(sent_plain) <= 300 and not _re.search(_ANN_NOT_ANNOUNCEMENT, sent_plain)
                and not _ann_waits_on_person(sent_plain)):
            if any(p.search(sent_plain) for p in _ANN_ANNOUNCE):
                return _ann_verdict("announce", nudged)
            if len(sent_plain) <= _ANN_FILLER_MAX and any(p.search(sent_plain) for p in _ANN_FILLER):
                return _ann_verdict("announce", nudged)
            if sent.endswith(":") and any(p.search(sent_plain) for p in _ANN_COLON_VERB):
                return _ann_verdict("announce", nudged)
    if tools == 0 and not has_code and len(prose.strip()) <= _ANN_CLAIM_MAX:
        body = _ann_norm(prose)
        if _re.search(_ANN_DRAFT, body, _re.M) or _re.search(_ANN_NARRATIVE, body):
            return None
        body = _re.sub(_ANN_QUOTED, " ", body)
        body_lines = [ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith(">")]
        bullet = _re.compile(r"^\s*(?:[-*•]\s|\d+[.)]\s)")
        bullets_count = _re.search(_ANN_LIST_CONTEXT, " ".join(ln for ln in body_lines if not bullet.match(ln))) is not None
        for line in body_lines:
            if bullet.match(line) and not bullets_count:
                continue
            for raw in _re.split(r"(?<=[.!?…])\s+", line):
                s = _re.sub(r"^[\s>*_`~#•-]+|^\d+[.)]\s+", "", raw)
                s = _re.sub(r"^[☀-➿\U0001f300-\U0001faff️\s]+", "", s)
                if s and not _re.search(_ANN_NOT_ANNOUNCEMENT, s) and any(p.search(s) for p in _ANN_CLAIM):
                    return _ann_verdict("claim", nudged)
    return None


def _announced_action_nudge(kind):  # aibridge-patch: announced_action_retry
    said = "announced an action" if kind == "announce" else "said that work was done"
    return (f"Your previous reply {said}, but no tool ran in this turn, so nothing was actually done and the turn would end "
            "with the person waiting. Do it now with the tool and answer from its result, or tell the person plainly what "
            "could not be done. Do not promise later work unless a background job is actually started.")


'''

CALL_SITE = '''    # An announced action (or a claimed one) with no tool call in the turn: one re-prompt per turn, same path as above.
    _announced = None if assistant_message.tool_calls or finish_reason in ("length", "tool_calls") else _announced_action(final_response, agent, messages, (_CODEX_ACK_CONTINUATION_NUDGE, _DEGENERATE_FINAL_NUDGE))  # aibridge-patch: announced_action_retry
    if _announced and getattr(agent, "_dropped_toolcall_retries", 0) < 3:
        agent._dropped_toolcall_retries = getattr(agent, "_dropped_toolcall_retries", 0) + 1
        logger.warning(
            "reply %s with no tool call in the turn — re-prompting (model=%s provider=%s)",
            "announced an action" if _announced == "announce" else "claimed finished work", agent.model, agent.provider,
        )
        _ann_signal("nudge", k=_announced)
        final_msg["_dropped_toolcall_nudge"] = True
        final_msg[_ANN_FLAG] = True
        append_message(messages, final_msg)
        append_message(messages, {
            "role": "user",
            "content": _announced_action_nudge(_announced),
            "_dropped_toolcall_nudge": True,
            _ANN_FLAG: True,
        })
        agent._session_messages = messages
        final_response = None
        return _verdict("continue")

'''

ANCHOR = '''    # Genuine turn end (no dropped-tool-call mismatch): clear stall budget.
    agent._dropped_toolcall_retries = 0
'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    if PREREQ not in src:
        sys.exit("patch failed: text_tool_call_retry must be applied first")
    src = replace_once(src, "@dataclass\nclass FinalResponseVerdict:", HELPER + "@dataclass\nclass FinalResponseVerdict:",
                       "helper insertion point")
    src = replace_once(src, ANCHOR, CALL_SITE + ANCHOR, "genuine turn end anchor")
    open(path, "w", encoding="utf-8").write(src)
    print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
