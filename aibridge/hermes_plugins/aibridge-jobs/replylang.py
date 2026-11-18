"""Reply-language guard, the deterministic half: which language a model reply is in (script plus a stopword count, never a model call),
which language the person expects, and the one-line instruction put in front of a turn.

Used by the aibridge-jobs plugin (__init__.py loads this file by path; nothing here imports Hermes):
  expected()    "es", "ru" or "en": the person's /settings language, else the stack's "lang" in gateways.json; None while they chose
                "auto" or nothing is set (same order as router.person_lang and patches/reply_language.py).
  detect(text)  the language of a reply: "es" "ru" "en" "fr" "pt" "it" "de" "uk", a script code ("zh" CJK and kana, "ko", "ar", "he",
                "th", "hi", "el") or None when the text is too short, mixed or not clearly one language. Code blocks, URLs, paths,
                MEDIA lines, identifiers, numbers and mentions are not read, so a reply that is prose in one language around a lot of code,
                names or links is judged by the prose only.
  slip()        the wrong language the reply is in, or None. With a chosen language: any other language. With none (auto): only a
                language outside Spanish/Russian/English (French, Portuguese, a CJK reply...), because the plugin cannot see the person's
                message in that hook and a person who writes Russian but asked for Spanish answers is not wrong.
  guard_line()  the instruction appended to the turn (pre_llm_call context), after the ledger block, so it is the last thing the model
                reads before it writes.
  signal()      one early-alert line (category wrong_lang, k = the detected code): a counter, never text. Same format as router.signal.
"""
import json
import os
import re
import time

NAMES = {"es": "Spanish", "ru": "Russian", "en": "English", "fr": "French", "pt": "Portuguese", "it": "Italian", "de": "German",
         "uk": "Ukrainian", "zh": "Chinese or Japanese", "ko": "Korean", "ar": "Arabic", "he": "Hebrew", "th": "Thai", "hi": "Hindi",
         "el": "Greek"}
OWN = ("es", "ru", "en")                  # the languages the stack's people use; auto mode flags anything else
MIN_LETTERS = 40                          # a shorter reply (after code, links and numbers are taken out) is never judged
MIN_HITS = 4                              # stopwords of the winning language
MIN_RATIO = 0.08                          # ... as a share of the words: names, identifiers and jargon alone never decide

_RAW = {
    "es": "el los las una unos unas es está están son fue eran ser por para con pero como muy más también esto esta este eso ese esos "
          "cuando donde porque sin sobre entre hasta desde ya sí su sus del mi tu te nos les hay tiene tienen puede pueden quiero tenés "
          "querés puedo acá ahora todo todos toda bien así aquí lo se al y qué cómo está estás tengo hace hacer voy vamos otro otra "
          "cada mejor nada algo muchas muchos pasó queda ahí además después antes mismo ha han he hemos",
    "en": "the and you your for that with this is are was were be been have has had will would can could not but what when where which "
          "they them their from there here about just also into then than very more some any all one only now our out its it's i'm "
          "don't of to in on at by an as or if we he she his her how why who being do does did so yes ok i it me my up get got make "
          "made should must may might still even after before because while those these other each over",
    "fr": "le les des une est sont pour dans avec pas vous nous sur au aux du et en je tu il elle ils elles ce cet cette ces qui que mais "
          "ou où donc car très plus aussi comme être avoir fait faire peut bien tout tous ça c'est n'est j'ai qu'il qu'on l'on d'un "
          "d'une ne y moi toi lui leur leurs mon ma mes ton ta tes son sa ses notre votre vos été avez avons ont suis es sommes "
          "êtes sera seront voici voilà alors encore déjà pourquoi quand comment sans sous entre après avant chez cela ceci",
    "pt": "o os um uma uns de do da dos das em no na nos nas com para por que não é são foi ser está estão muito mais também isso esta "
          "este essa esse quando onde porque sem sobre entre até desde já sim se seu sua seus suas ao aos mas ou você vocês tem têm "
          "pode podem eu ele ela nós obrigado obrigada ainda agora aqui ali tudo todos todas bem assim fazer foram será estou "
          "estamos temos tenho",
    "it": "il lo la gli le un uno una di del della dei delle degli in con per che non è sono ma anche come più molto questo questa "
          "questi quando dove perché senza sopra tra fra già sì se suo sua suoi loro al alla ai agli ho hai ha abbiamo hanno posso può "
          "ciao grazie ancora adesso qui tutto tutti tutte bene così fare stato stata siamo sei essere ci vi mi ti",
    "de": "der die das den dem des ein eine einen einem einer ist sind war waren nicht und oder aber mit für auf bei von zu zum zur "
          "auch wie noch nur sehr kann können ich du wir ihr sie es dass wenn weil über nach aus hier jetzt alle alles schon dann "
          "dies diese dieser haben hat hatte wird werden wurde habe bin bist sein mein dein unser euer",
}


# Common words that more than one language shares ("de", "la", "no", "a"): each list also holds them where they are real words, so
# _build() cancels them and a Spanish text is not scored as Portuguese because "de" was only in the Portuguese list.
_SHARED = {
    "es": "de la que en un no o a ni lo se si me mi tu las una uno dos será con por para del al es le",
    "pt": "de a e um que em o os as no não se com por para do da lhe",
    "fr": "de la le un en ne se si que me a y des du une la les",
    "it": "la lo un una no o a e se si che del al con per me mi ti ci le gli di",
    "en": "no a me do he so i it an as to in on at by of or if we up my",
    "de": "es sie die den die in an",
}
for _k, _v in _SHARED.items():
    _RAW[_k] += " " + _v


def _build():
    """Per language the words it does NOT share with another list: "la", "de" or "que" say nothing about Spanish versus Portuguese."""
    sets = {k: set(v.split()) for k, v in _RAW.items()}
    return {k: s - set().union(*(o for k2, o in sets.items() if k2 != k)) for k, s in sets.items()}


STOP = _build()

_FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)
_INLINE = re.compile(r"`[^`\n]{0,200}`")
_NOT_PROSE = re.compile(r"https?://|www\.|@|MEDIA:|[/\\_\d]")
MAX_CHARS = 30000           # a reply is judged by its first 30k characters: enough for any language, and the time stays bounded
MAX_WORD = 40               # a longer ASCII "word" is a hash, base64 or minified code (Chinese and Japanese have no spaces: kept)
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")
_SCRIPTS = (("zh", "぀-ヿ㐀-䶿一-鿿"), ("ko", "가-힯ᄀ-ᇿ"), ("ar", "؀-ۿ"),
            ("he", "֐-׿"), ("th", "฀-๿"), ("hi", "ऀ-ॿ"), ("el", "Ͱ-Ͽ"))
_SCRIPT_RE = {k: re.compile("[" + r + "]") for k, r in _SCRIPTS}
_CYR = re.compile("[Ѐ-ӿ]")
_UK_ONLY = re.compile("[іїєґІЇЄҐ]")
_RU_ONLY = re.compile("[ыэъёЫЭЪЁ]")
_LATIN = re.compile("[A-Za-zÀ-ɏ]")


def prose(text):
    """The text with code, links, paths, identifiers, numbers and mentions removed. Linear in the length: a token-level filter
    (an earlier per-position regex took seconds to minutes on one long token without spaces, inside the reply hook)."""
    text = _INLINE.sub(" ", _FENCE.sub(" ", (text or "")[:MAX_CHARS]))
    return " ".join(w for w in text.split() if not (len(w) > MAX_WORD and w.isascii()) and w[0] not in "@#" and not _NOT_PROSE.search(w))


def detect(text):
    """The language of `text` (see the module docstring) or None. Pure: no I/O, no model."""
    t = prose(text)
    cyr, lat = len(_CYR.findall(t)), len(_LATIN.findall(t))
    other = {k: len(r.findall(t)) for k, r in _SCRIPT_RE.items()}
    total = cyr + lat + sum(other.values())
    if total < MIN_LETTERS:
        return None
    top_script, top_n = max(other.items(), key=lambda kv: kv[1])
    if top_n / total >= 0.3:
        return top_script
    if cyr / total >= 0.5:
        return "uk" if len(_UK_ONLY.findall(t)) >= 3 and not _RU_ONLY.search(t) else "ru"
    if lat / total < 0.9:
        return None                                      # a real mixture of scripts: not one language
    words = [w.lower().replace("’", "'") for w in _WORD.findall(t)]
    if not words:
        return None
    scores = sorted(((sum(1 for w in words if w in s), k) for k, s in STOP.items()), reverse=True)
    (s1, lang), (s2, _) = scores[0], scores[1]
    if s1 < MIN_HITS or s1 / len(words) < MIN_RATIO or s1 < 2 * s2 + 1:
        return None
    return lang


def _file_lang(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        v = d.get("lang") if isinstance(d, dict) else None
        return v if isinstance(v, str) else None
    except (OSError, ValueError):
        return None


def expected(prefs=None, gateways=None):
    """"es", "ru" or "en" when the person chose one (/settings language) or the stack sets one; None for "auto" or nothing."""
    chosen = _file_lang(prefs or os.environ.get("AIBRIDGE_PREFS", "/workdir/.prefs.json"))
    if chosen == "auto":
        return None
    if chosen in OWN:
        return chosen
    stack = _file_lang(gateways or os.environ.get("GATEWAYS_CONFIG", "/etc/aibridge/gateways.json"))
    return stack if stack in OWN else None


def slip(text, exp):
    """The wrong language `text` is in, or None (right language, not sure, too short). See the module docstring for auto mode."""
    got = detect(text)
    if got is None:
        return None
    if exp:
        return None if got == exp else got
    return None if got in OWN else got


TAG = re.compile(r"\[reply in (?:Spanish|Russian|English)\]")


def guard_line(exp, user_message="", slipped=None):
    """The instruction for this turn. With a chosen language and the message already carrying its `[reply in X]` tag (Hermes's messaging
    gateway and the router add it) the standing line is skipped; after a reply in a wrong language one correction is added. '' = nothing."""
    parts = []
    if exp:
        if not TAG.search(user_message or ""):
            n = NAMES[exp]
            parts.append(f"Reply language: {n}. Write this whole reply in {n}, whatever language the message, the tool output or your "
                         "notes are in, unless the person asks for another language.")
    else:
        parts.append("Reply language: only Spanish, Russian or English, the language the person writes in (an automatic notice such as "
                     "\"[IMPORTANT: Background process ...\" is not the person), unless they asked for one. Do not drift into French, Portuguese or any other language on your own.")
    if slipped:
        want = NAMES[exp] if exp else "the person's language (Spanish, Russian or English)"
        parts.append(f"Your last reply was in {NAMES.get(slipped, slipped)}: write this one in {want}, unless the person asked for "
                     "another language.")
    return " ".join(parts)


# ---- the counter: one early-alert line, the same shape router.signal writes (categories and small enums, never text)
SIGNALS = os.environ.get("ROUTER_EARLY_SIGNALS", "/workdir/.early-signals.jsonl")
_SIG_SRC = "plugin"
_SIG_CATS = frozenset(("wrong_lang",))
_SIG_K = re.compile(r"^[a-z0-9_]{1,16}$")
_SIG_MAX_BYTES = 200_000
_SIG_PER_MIN = 40
_SIG_RECENT = []


def early_signal(cat, n=1, **small):
    """Append {"ts","cat","n"[,"k"][,"v"],"src"} to SIGNALS (O_NOFOLLOW + O_APPEND, one small write). True when a line was written;
    never raises. A copy of router.signal; early_signals_selftest.py checks that it behaves alike."""
    try:
        now = time.time()
        _SIG_RECENT[:] = [t for t in _SIG_RECENT if now - t < 60]
        if cat not in _SIG_CATS or len(_SIG_RECENT) >= _SIG_PER_MIN:
            return False
        rec = {"ts": int(now), "cat": cat, "n": max(1, min(int(n), 20))}
        if isinstance(small.get("k"), str) and _SIG_K.match(small["k"]):
            rec["k"] = small["k"]
        if isinstance(small.get("v"), int) and not isinstance(small["v"], bool) and 0 <= small["v"] <= 1_000_000:
            rec["v"] = small["v"]
        rec["src"] = _SIG_SRC
        try:
            if os.lstat(SIGNALS).st_size > _SIG_MAX_BYTES:
                os.replace(SIGNALS, SIGNALS[:-6] + ".1.jsonl")
        except OSError:
            pass
        fd = os.open(SIGNALS, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o644)
        try:
            os.fchmod(fd, 0o644)
            os.write(fd, (json.dumps(rec, separators=(",", ":")) + "\n").encode())
        finally:
            os.close(fd)
        _SIG_RECENT.append(now)
        return True
    except Exception:
        return False
