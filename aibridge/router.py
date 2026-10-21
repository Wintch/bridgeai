#!/usr/bin/env python3
"""router -- "local first" in front of Hermes: the home model answers, the cloud only when needed, always announced.

Hermes's primary model is this router (`model.provider custom`, `model.default local-first`,
`model.base_url http://127.0.0.1:8650/v1`). It runs inside each Hermes container (started by start_hermes.sh), so
every person's keys stay in their own container.

Per turn (the person's message plus the tool calls that follow it), decided once and kept for the whole turn:
  1. The person asks for the cloud ("usá la nube", "в облаке", "use the cloud")       -> cloud, "lo pediste".
  2. Home model down (every "llm" gateway of the stack, /etc/aibridge/gateways.json) -> needs the cloud.
  3. Otherwise the home model classifies the message itself (LOCAL / NUBE, thinking off, ~0.3 s): a small model
     with tools handles chat, lookups, media; long code, multi-step reasoning, long documents, high-stakes advice
     or "your last answer was wrong" need the cloud.
  4. A local answer that fails (error, context full)                                   -> needs the cloud.
**Consent (operator decision 2026-10-09):** "needs the cloud" never sends anything by itself. The router answers
with a 🔒 message: why, which cloud model, what would travel, and how to accept ("sí"/"dale"; "siempre" = for the
rest of this conversation, until /new) or pick another model with /model. The next "sí" sends the turn.
Hermes's own small calls (titles, memory review: no tools) only ever run at home; when home is down they fail.
So does model "local-only" (with or without tools): Hermes's auxiliary tasks (vision, approval guard, background
review, curator) point here with it, so they get the host failover and never the consent message or the cloud.
A delegated subagent (delegate_task: "Platform: subagent" in its system prompt) cannot answer a 🔒, so it uses the cloud
on the person's last cloud consent if it was less than ROUTER_SUBAGENT_GRACE (900 s) ago; otherwise it gets a 503, never the
consent question (the parent model would relay it as a result and answer "sí" to itself).
A picture is the exception that needs no question of its own: Hermes's vision call (model "local-only" with an image) and
`gateway video` cannot show a 🔒, so with the home model out they use a cloud vision model (VISION_CLOUD) on the person's earlier
consent, a live "siempre" or a consented cloud turn less than ROUTER_SUBAGENT_GRACE ago (operator, 2026-10-18: "una sola vez está
bien"); without it they get a 503 that tells the person to say "usá la nube" and send the picture again.
Hermes's own fallback chain must be empty for a router stack (model_guard does it), or it would bypass consent.

What travels to the cloud (ROUTER_CLOUD_CONTEXT): "full" (default, the operator's choice) = the whole conversation;
"recent:N" = the last N exchanges plus the question; "turn" = the current question only. Always the system prompt Hermes needs to
use its tools, but with the person's memory and profile blocks removed (ROUTER_STRIP_MEMORY=1, default), and
images replaced by a placeholder. Every cloud answer the person sees starts with one line saying it was the cloud,
why, and what travelled.

Each decision appends one metadata line to /workdir/.gateway-log.jsonl (route, reason, provider, seconds, how many
messages travelled out of how many). Never the text.
"""
import calendar, hashlib, http.client, json, os, re, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("ROUTER_PORT", "8650"))
GATEWAYS = os.environ.get("GATEWAYS_CONFIG", "/etc/aibridge/gateways.json")
LOG = os.environ.get("GATEWAY_LOG", "/workdir/.gateway-log.jsonl")
HERMES_ENV = os.path.join(os.environ.get("HERMES_HOME", "/root/.hermes"), ".env")
CONTEXT = os.environ.get("ROUTER_CLOUD_CONTEXT", "full")       # operator: "que sea todo", with consent
STRIP_MEMORY = os.environ.get("ROUTER_STRIP_MEMORY", "1") == "1"
# (name shown to the person, base url, model, key variable). Same preference as ops/lib/providers.py.
CLOUD = [("NVIDIA nemotron-3.5-super", "https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3.5-super-vl-120b-a12b", "NVIDIA_API_KEY"),
         ("NVIDIA gpt-oss-20b", "https://integrate.api.nvidia.com/v1", "openai/gpt-oss-20b", "NVIDIA_API_KEY"),
         ("Gemini flash-lite", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite", "GEMINI_API_KEY")]
# Models that read an image, for Hermes's vision call and `gateway video` when the home model is out (all three answered 200 with
# an image in ops/model_menu.py's probe on 2026-10-18). The person's one cloud consent covers the image too (operator, 2026-10-18).
VISION_CLOUD = [("NVIDIA nemotron-3-nano-omni", "https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "NVIDIA_API_KEY"),
                ("NVIDIA gemma-4-31b", "https://integrate.api.nvidia.com/v1", "google/gemma-4-31b-it", "NVIDIA_API_KEY"),
                ("Gemini flash-lite", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite", "GEMINI_API_KEY")]
PASS_KEYS = {"messages", "tools", "tool_choice", "temperature", "top_p", "max_tokens", "max_completion_tokens",
             "stream", "stream_options", "stop", "response_format", "parallel_tool_calls", "seed", "n"}
# A real request to use the cloud: one clause that starts with a verb ("usá la nube", "send it to the cloud",
# "отправь в облако"), not a mention ("un resumen de la nube de puntos") and not a negation. Anything unsure -> the
# normal path, which asks for consent.
_FILLER = (r"(?:(?:por favor|please|pls|che|hola|hey|dale|ok|bueno|ahora|ya|entonces|mejor|now|then|so|let'?s|"
           r"пожалуйста|давай|ну|тогда|теперь)\b[\s,]*)*")
_ASK_CLOUD_END = (r"(?=\W*$|\s+(?:para|por favor|ahora|ya|esta|este|esto|eso|for|to|please|now|this|that|and|y|"
                  r"для|пожалуйста|сейчас|и)\b)")
ASK_CLOUD = re.compile(
    r"^\W*" + _FILLER + r"(?:"
    r"(?:us[aá]r?|utiliz[aá]r?|pas[aá](?:lo|me)?|mand[aá]lo|envi[aá]lo|respond[eé]|contest[aá])\s+"
    r"(?:(?:esto|eso|lo)\s+)?(?:(?:con|en|por|a|desde)\s+)?(?:la\s+)?(?:nube|cloud)\b"
    r"|(?:use|try|switch to|go to|send (?:it|this|that) to|answer (?:with|in)|ask)\s+(?:the\s+)?cloud\b"
    r"|(?:используй(?:те)?|воспользуйся|отправь(?:те)?|пошли|ответь(?:те)?|переключись|спроси)\s+"
    r"(?:(?:это|его|мне)\s+)?(?:(?:в|через|на)\s+)?облак\w*"
    r")" + _ASK_CLOUD_END, re.I)
NEGATION = re.compile(r"\b(no|nunca|jam[aá]s|sin|ni|not|never|without|do not|don.?t|dont|не|без|никогда|нельзя)\b|n't\b", re.I)
MEMORY_HEAD = re.compile(r"═{20,}\n(?:MEMORY \(your personal notes\)|USER PROFILE \(who the user is\))[^\n]*\n═{20,}\n")
MEMORY_END = re.compile(r"\n\n(?=═{20,}\n|Active Hermes profile:|Conversation started:|Timezone:)")
# A consent answer is only these words ("sí", "dale, siempre", "ok por favor"): anything else is a new message.
YES_WORDS = {"si", "sí", "dale", "ok", "okay", "yes", "sure", "да", "давай", "ладно", "acepto", "mandalo", "mandá", "manda",
             "enviá", "envialo", "enviá", "claro", "bueno", "por", "favor", "please", "gracias", "thanks", "спасибо",
             "пожалуйста", "siempre", "always", "всегда", "y", "and", "и", "lo", "envíalo", "mándalo"}
ALWAYS = re.compile(r"\b(siempre|always|всегда)\b", re.I)
TS_PREFIX = re.compile(r"^(\s*\[[^\]]{8,40}\])+\s*")
CONSENT_MARK = "🔒"
CONSENT_PREFIX = CONSENT_MARK + " Para esto haría falta la nube: "     # how ask() starts its question
CLASSIFY = ("Decidí quién responde el último mensaje de la persona.\n"
            "LOCAL: un modelo chico con herramientas (búsqueda web, terminal, fotos, audio, video) alcanza: charla, "
            "preguntas simples, buscar clima, noticias, precios o lugares, traducir, resumir algo corto, recordatorios, "
            "describir fotos o videos, pedir un audio.\n"
            "NUBE: hace falta un modelo grande: escribir o corregir código de más de unas líneas, razonamiento o "
            "cálculo de varios pasos, analizar un documento largo, planificar algo complejo, consejos de salud, "
            "legales o de dinero con consecuencias, o la persona dice que la respuesta anterior estaba mal.\n"
            "Respondé solo LOCAL o NUBE.")


def consent_reply(msgs, u):
    """Is msgs[u] (a user message) a short "yes" to the router's own consent question? The previous assistant message
    must start with the router's prompt (a 🔒 written by the model does not count) and the answer must be nothing
    but affirmative words: no negation, no "pero/but/но", no new question."""
    prev = next((text_of(m) for m in reversed(msgs[:u]) if m.get("role") == "assistant" and text_of(m)), "")
    if not prev.lstrip().startswith(CONSENT_PREFIX):
        return False
    words = re.findall(r"\w+", TS_PREFIX.sub("", text_of(msgs[u])).lower())
    return 0 < len(words) <= 6 and all(w in YES_WORDS for w in words)


CONSENT_FILE = os.environ.get("ROUTER_CONSENT_FILE", "/workdir/.router-consent.json")
CONSENT_TTL = int(os.environ.get("ROUTER_CONSENT_TTL", str(24 * 3600)))


class Sessions:
    """Conversations where the person said "siempre". Kept on disk so a stack that sleeps (the waker stops the container
    after a few idle minutes) does not forget the consent and ask again; entries expire after CONSENT_TTL."""
    def __init__(self, path):
        self.path, self.seen = path, {}
        try:
            with open(path) as f:
                self.seen = {k: float(t) for k, t in json.load(f).items()}
        except (OSError, ValueError, AttributeError):
            pass

    def _live(self):
        now = time.time()
        self.seen = {k: t for k, t in self.seen.items() if now - t < CONSENT_TTL}

    def add(self, key):
        self.seen[key] = time.time()
        self._live()
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.seen, f)
            os.replace(tmp, self.path)
        except OSError:
            pass                                     # still armed in memory for this boot

    def __contains__(self, key):
        self._live()
        return key in self.seen

    def __len__(self):
        self._live()
        return len(self.seen)


_turns, _sessions, _lock = {}, Sessions(CONSENT_FILE), threading.Lock()

# Hermes's delegated subagents (delegate_task) are separate conversations: their own messages, their own first user message
# (the goal), "Platform: subagent" in the system prompt. They cannot answer a 🔒 question. A subagent therefore rides on
# the person's consent: it may use the cloud while the last conversation turn of this container went to the cloud, with
# consent ("sí", "siempre" or the person asked for it), at most SUBAGENT_GRACE seconds ago.
SUBAGENT_GRACE = int(os.environ.get("ROUTER_SUBAGENT_GRACE", "900"))
_SUBAGENT = re.compile(r"^Platform: subagent\s*$", re.M)
_last_cloud = [0.0]


def is_subagent(msgs):
    return any(m.get("role") == "system" and _SUBAGENT.search(text_of(m)) for m in msgs)


def inherits(msgs):
    """May this request, if it comes from a delegated subagent, use the cloud on the person's earlier consent?"""
    return is_subagent(msgs) and time.time() - _last_cloud[0] < SUBAGENT_GRACE


def has_image(msgs):
    return any(isinstance(m.get("content"), list) and any(isinstance(p, dict) and p.get("type") == "image_url" for p in m["content"])
               for m in msgs)


def vision_allowed():
    """May an image go to a cloud vision model? Only on the person's earlier consent, because Hermes's vision call cannot ask:
    a "siempre" still live (CONSENT_TTL), or a turn that went to the cloud with consent less than SUBAGENT_GRACE ago."""
    with _lock:
        return len(_sessions) > 0 or time.time() - _last_cloud[0] < SUBAGENT_GRACE


def log(**kw):
    kw.update(gateway="router", ts=round(time.time(), 1))
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(kw) + "\n")
    except OSError:
        pass


_picked = [None]


HOME_THINKING = os.environ.get("ROUTER_THINKING", "0") == "1"


def local_body(body, model):
    """The request for the home model with its hidden reasoning OFF unless the caller set it. Measured 2026-10-13 on the
    home Gemma: a two-line chat answer took 9.2-9.4 s with reasoning on (400 tokens, 1.3 KB of it reasoning nobody sees) and
    0.9-2.0 s with it off, same visible answer; the classifier call already ran with it off. Hard work goes to the cloud
    anyway (decide()). ROUTER_THINKING=1 restores the model's default."""
    kw = dict(body.get("chat_template_kwargs") or {})
    if not HOME_THINKING:
        kw.setdefault("enable_thinking", False)
    return dict(body, model=model, chat_template_kwargs=kw) if kw else dict(body, model=model)


def local_host():
    """(url, model) of the home model: the first "llm" host that answers, in the gateways order (gateways_sync puts
    the stack's GPU hosts there). Sticky while it stays up, since a switch costs the prompt cache. None up -> the
    first one, so callers see it down."""
    try:
        hosts = [(h["url"].rstrip("/"), h.get("model", "local")) for h in json.load(open(GATEWAYS)).get("llm") or []]
    except (OSError, ValueError, KeyError, TypeError):
        return None, None
    if not hosts:
        return None, None
    cur = _picked[0]
    for h in ([cur] if cur in hosts else []) + [h for h in hosts if h != cur]:
        if up(h[0]):
            _picked[0] = h
            return h
    return hosts[0]


def up(url):
    try:
        with urllib.request.urlopen(url + "/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def key(var):
    if os.environ.get(var):
        return os.environ[var]
    try:
        for line in open(HERMES_ENV):
            if line.startswith(var + "="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def text_of(msg):
    c = msg.get("content")
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c or ""


CONNECT_TIMEOUT = 10        # a backend that does not even accept the connection
IDLE_LOCAL = 240            # silence while reading: big prompts take ~2 min to evaluate before the first byte
IDLE_CLOUD = 90
IDLE_LOCAL_WHOLE = 600       # a non-streamed local answer sends nothing until it is complete (long ones at ~15 tok/s)
BROKEN = "stream-broken"    # forward(): the stream died after bytes went out; the error is already sent and logged


def post(url, body, headers, idle):
    """POST JSON; the response object (HTTPError for status >= 400). `idle` is the longest silence tolerated while
    waiting for the answer or between its chunks, after a short connect timeout."""
    u = urllib.parse.urlsplit(url)
    conn = (http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection)(
        u.hostname, u.port, timeout=CONNECT_TIMEOUT)
    try:
        conn.connect()
        conn.sock.settimeout(idle)
        conn.request("POST", u.path + ("?" + u.query if u.query else ""), json.dumps(body).encode(),
                     {"Content-Type": "application/json", "User-Agent": "bridgeai-router/1.0", "Connection": "close", **headers})
        r = conn.getresponse()
    except BaseException:
        conn.close()
        raise
    if r.status >= 400:
        raise urllib.error.HTTPError(url, r.status, r.reason, r.headers, r)
    return r


def classify(url, model, msgs, u):
    prev = next((text_of(m)[:600] for m in reversed(msgs[:u]) if m.get("role") == "assistant" and text_of(m)), "")
    content = (f"Respuesta anterior del asistente: {prev}\n\n" if prev else "") + f"Último mensaje: {text_of(msgs[u])[:3000]}"
    body = {"model": model, "messages": [{"role": "system", "content": CLASSIFY}, {"role": "user", "content": content}],
            "max_tokens": 4, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    try:
        with post(url + "/v1/chat/completions", body, {}, 20) as r:
            out = json.load(r)["choices"][0]["message"].get("content") or ""
        return "nube" if "NUBE" in out.upper() else "local"
    except Exception:
        return "local"          # the answer call itself will fail over if home is really broken


def asks_cloud(said):
    """The person asks for the cloud in this message: a clause of a statement (not a question: "¿podés usar la nube?"
    gets the consent prompt instead) that is a request and is not negated, in the first or last line of the message
    (a line in the middle of a pasted text is not the person talking to the router)."""
    lines = [ln for ln in TS_PREFIX.sub("", said).splitlines() if ln.strip()]
    for line in {0: [], 1: lines}.get(len(lines), [lines[0], lines[-1]] if lines else []):
        for sentence, end in re.findall(r"([^.!?]+)([.!?]*)", line):
            if "?" in end or "¿" in sentence:
                continue
            for c in re.split(r"[,;:¡]+", sentence):
                if ASK_CLOUD.match(c.strip()) and not NEGATION.search(c):
                    return True
    return False


# Hermes retired timed session resets (conversations end only on /new), so a chat from yesterday keeps all its context and
# its old system prompt. After IDLE_HOURS without a message the router asks once whether to continue or start fresh with
# /new (which also picks up new skills and prompt). The hour comes from the "[Sat 2026-10-17 22:29:48 -03]" stamp Hermes puts on
# each message; a message without a stamp (web chat, system-injected) is never held. 0 turns it off.
IDLE_HOURS = float(os.environ.get("ROUTER_IDLE_ASK_HOURS", "5"))
IDLE_MARK = "🕓"
_STAMP = re.compile(r"^\s*\[(?:[A-Za-z]{3} )?(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)(?: ([+-])(\d\d)(?::?(\d\d))?)?\s*\]")
CONTINUE_WORDS = YES_WORDS | {"seguir", "seguimos", "sigamos", "sigue", "continuar", "continuá", "continuemos", "retomar", "retomamos",
                              "continue", "go", "on", "продолжай", "продолжим", "дальше", "продолжаем"}


def stamp(msg):
    """Epoch seconds of a message's leading Hermes timestamp, or None."""
    m = _STAMP.match(text_of(msg))
    if not m:
        return None
    y, mo, d, h, mi, se, sign, oh, om = m.groups()
    offset = (int(oh) * 3600 + int(om or 0) * 60) * (1 if sign == "+" else -1) if sign else 0
    return calendar.timegm((int(y), int(mo), int(d), int(h), int(mi), int(se))) - offset


def idle_gap_hours(msgs):
    """Hours since the person's previous message, when the last message is theirs, new, and the router has not asked yet."""
    if IDLE_HOURS <= 0 or not msgs or msgs[-1].get("role") != "user" or is_subagent(msgs):
        return None
    if len(msgs) > 1 and msgs[-2].get("role") == "assistant" and text_of(msgs[-2]).startswith(IDLE_MARK):
        return None                                    # already asked about this gap: the answer is this message
    now = stamp(msgs[-1])
    before = next((t for t in (stamp(m) for m in reversed(msgs[:-1]) if m.get("role") == "user") if t), None)
    if now is None or before is None:
        return None
    gap = (now - before) / 3600
    return gap if gap >= IDLE_HOURS else None


def idle_text(hours, said):
    h = f"{hours:.0f}"
    if re.search(r"[а-яё]", said, re.I):
        return (f"{IDLE_MARK} Прошло {h} ч с вашего прошлого сообщения. Если это другая тема, напишите /new: начнём с чистого листа, "
                "это дешевле, и подхватятся последние улучшения (память и навыки сохраняются). Если продолжаем то же самое, "
                "ответьте «продолжай». Ваше сообщение ждёт.")
    return (f"{IDLE_MARK} Pasaron {h} h desde tu último mensaje. Si lo de ahora es otro tema, escribí /new: arranca limpio, "
            "gasta menos y toma las últimas mejoras (tu memoria y tus skills se mantienen). Si seguimos con lo mismo, "
            "contestá \"seguir\". Tu mensaje queda esperando.")


def strip_idle(msgs):
    """Without the router's own idle question (and the plain "seguir" that answered it): the model never sees them."""
    out, drop_next = [], False
    for m in msgs:
        role, t = m.get("role"), text_of(m)
        if role == "assistant" and t.startswith(IDLE_MARK):
            drop_next = True
            continue
        if drop_next and role == "user":
            drop_next = False
            words = re.findall(r"\w+", TS_PREFIX.sub("", t).lower())
            if words and all(w in CONTINUE_WORDS for w in words):
                continue
        out.append(m)
    return out


# The "☁️ Respondió la nube (...)" line the router puts in front of a cloud answer lands in Hermes's history as part of the
# reply. 2026-10-21 on hernik: with those replies in its context the cloud model began its own answers with the same line,
# and the router added its own: 6 of 9 replies in one session showed it twice (one API call per turn, so not a retry).
NOTICE_LINE = re.compile(r"^☁️ Respondió la nube \([^)\n]*\)[^\n]*\n*", re.M)


def strip_notices(msgs):
    """Without the router's own cloud lines in earlier replies: no model ever sees them, so none copies them."""
    out = []
    for m in msgs:
        c = m.get("content")
        if m.get("role") == "assistant" and isinstance(c, str) and "☁️ Respondió la nube" in c:
            m = dict(m, content=NOTICE_LINE.sub("", c))
        elif m.get("role") == "assistant" and isinstance(c, list):
            m = dict(m, content=[dict(p, text=NOTICE_LINE.sub("", p["text"])) if p.get("type") == "text" and isinstance(p.get("text"), str)
                                 else p for p in c])
        out.append(m)
    return out


# "There was an update": the operator edits RELEASE_NOTICE.txt (baked into the image) when a release is worth telling people
# about, and each person sees it once, in front of their next answer, whatever the channel (Telegram, web). No push: nothing
# is sent while nobody is talking, and stacks without Telegram get it too. Format, one item per line:
#   id: 2026-10-18        (change it to show the notice again)
#   es: texto             ru: текст         (the language of the person's message picks one; es is the fallback)
RELEASE_FILE = os.environ.get("ROUTER_RELEASE_FILE", "/app/RELEASE_NOTICE.txt")
RELEASE_SEEN = os.environ.get("ROUTER_RELEASE_SEEN", "/workdir/.router-release-seen")


def release_pending(said):
    """(id, text) of the release notice this container's person has not seen yet, else None."""
    try:
        with open(RELEASE_FILE, encoding="utf-8") as f:
            items = dict(ln.split(":", 1) for ln in f.read().splitlines() if re.match(r"^(id|es|ru):", ln))
        rid = items["id"].strip()
        seen = ""
        try:
            with open(RELEASE_SEEN) as f:
                seen = f.read().strip()
        except OSError:
            pass
        text = items.get("ru") if re.search(r"[а-яё]", said, re.I) and items.get("ru") else items.get("es")
        return (rid, text.strip()) if rid and text and rid != seen else None
    except (OSError, KeyError, ValueError):
        return None


def turn_notice(k, cloud_line=None):
    """What goes in front of this turn's final answer: the release notice (once per person) and the cloud line."""
    with _lock:
        rel = (_turns.get(k) or {}).get("release")
    parts = [x for x in ((rel[1] + "\n\n") if rel else None, cloud_line) if x]
    return "".join(parts) or None


def decide(msgs):
    """(route, reason, turn key, first call of the turn?). route: local | nube (consented) | ask (needs consent)."""
    users = [i for i, m in enumerate(msgs) if m.get("role") == "user"]
    if not users:
        return "local", "sin mensaje", None, False
    u = users[-1]
    k = hashlib.sha1(json.dumps([m.get("content") for m in msgs[:u + 1] if m.get("role") != "system"],
                                sort_keys=True, default=str).encode()).hexdigest()
    sub = is_subagent(msgs)
    with _lock:
        if k in _turns:
            if _turns[k]["route"] == "nube" and not sub:
                _last_cloud[0] = time.time()       # a long tool loop keeps the grace window open
            return _turns[k]["route"], _turns[k]["reason"], k, False
    session = hashlib.sha1(str(msgs[users[0]].get("content")).encode()).hexdigest()
    said = TS_PREFIX.sub("", text_of(msgs[u])).strip()
    url, model = local_host()
    if consent_reply(msgs, u):
        route, reason = "nube", "lo autorizaste"
        if ALWAYS.search(said):
            with _lock:
                _sessions.add(session)
    elif asks_cloud(said):
        route, reason = "nube", "lo pediste"
    else:
        if not url or not up(url):
            route, reason = "ask", "tu PC (el modelo local) no responde"
        else:
            route = classify(url, model, msgs, u)
            route, reason = ("ask", "el modelo local cree que la pregunta necesita un modelo más grande") if route == "nube" else ("local", "local")
        with _lock:
            if route == "ask" and session in _sessions:
                route, reason = "nube", reason + " (autorizaste la nube para esta conversación)"
            elif route == "ask" and inherits(msgs):
                route, reason = "nube", reason + " (tarea delegada de una respuesta que autorizaste)"
    if route == "nube" and not sub:
        _last_cloud[0] = time.time()
    with _lock:
        if len(_turns) > 500:
            _turns.clear()
        _turns[k] = {"route": route, "reason": reason, "noticed": False, "session": session,
                     "release": None if sub else release_pending(said)}
    return route, reason, k, True


def strip_memory(text):
    if not STRIP_MEMORY:
        return text
    out, pos = "", 0
    for m in MEMORY_HEAD.finditer(text):
        if m.start() < pos:
            continue
        end = MEMORY_END.search(text, m.end())
        out += text[pos:m.start()] + "[memoria personal omitida por el router antes de salir a la nube]"
        pos = end.start() if end else len(text)
    return out + text[pos:]


def cloud_messages(msgs):
    """The messages the cloud gets under ROUTER_CLOUD_CONTEXT, and a phrase for the notice."""
    system = [dict(m, content=strip_memory(text_of(m))) for m in msgs if m.get("role") == "system"]
    rest = [m for m in msgs if m.get("role") != "system"]
    users = [i for i, m in enumerate(rest) if m.get("role") == "user"]
    last = len(users) - 1
    if last > 0 and consent_reply(rest, users[last]):
        last -= 1                          # the window starts at the question the 🔒 prompt asked about, not at "sí"
    if CONTEXT == "full" or not users:
        keep, what = rest, "toda la conversación"
    elif CONTEXT == "turn":
        keep, what = rest[users[last]:], "solo tu pregunta actual"
    else:
        n = int(CONTEXT.split(":")[1]) if ":" in CONTEXT else 3
        keep = rest[users[max(0, last - n)]:]
        what = f"tu pregunta y los últimos {n} intercambios"
    if STRIP_MEMORY:
        what += ", sin tus memorias"
    clean = []
    for m in keep:
        if isinstance(m.get("content"), list):
            m = dict(m, content=[p if p.get("type") != "image_url" else {"type": "text", "text": "[imagen omitida]"}
                                 for p in m["content"]])
        clean.append(m)
    return system + clean, what, len(system) + len(clean)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def reply(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url, _ = local_host()
        if self.path.rstrip("/") in ("/health", "/v1/health"):
            return self.reply(200, {"status": "ok"})
        if self.path.startswith("/props") and url:      # llama.cpp context size, which Hermes reads
            try:
                with urllib.request.urlopen(url + "/props", timeout=3) as r:
                    return self.reply(200, r.read())
            except Exception:
                pass
        if self.path.startswith("/v1/models") or self.path.startswith("/models"):
            return self.reply(200, {"object": "list", "data": [{"id": "local-first", "object": "model",
                                                                 "owned_by": "bridgeai", "context_length": 81920}]})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self.reply(404, {"error": "not found"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        msgs = body.get("messages", [])
        aux = not body.get("tools") or body.get("model") == "local-only"
        gap = None if aux else idle_gap_hours(msgs)
        if gap is not None:                            # a long pause: ask once whether to continue or start fresh
            log(route="idle", hours=round(gap, 1))
            return self.assistant(idle_text(gap, TS_PREFIX.sub("", text_of(msgs[-1]))), bool(body.get("stream")))
        msgs = body["messages"] = strip_notices(strip_idle(msgs))
        t0 = time.time()
        route, reason, k, first = ("local", "auxiliar", None, False) if aux else decide(msgs)
        url, model = local_host()
        if route == "local":
            if not url:
                ok = "sin modelo local"
            else:
                ok = self.forward(url + "/v1/chat/completions", local_body(body, model), {}, turn_notice(k), k,
                                  idle=IDLE_LOCAL if body.get("stream") else IDLE_LOCAL_WHOLE)
            if ok is True:
                if first:
                    log(route="local", reason=reason, seconds=round(time.time() - t0, 1))
                return
            if ok is BROKEN:
                return log(route="none", reason="se cortó la respuesta del modelo local", tried=0, aux=aux)
            if aux:                                    # Hermes's own small calls never leave home...
                if has_image(msgs):                    # ...except a picture, on the cloud consent the person already gave
                    return self.vision(body, ok, t0)
                return self.reply(503, {"error": {"message": f"router: local model unavailable ({ok})", "type": "router"}})
            route, reason, first = "ask", f"el modelo local falló ({ok})", True
            with _lock:
                if k in _turns:
                    sess = _turns[k]["session"]
                    route = "nube" if sess in _sessions or inherits(msgs) else "ask"
                    _turns[k].update(route=route, reason=reason)
        if route == "ask":
            return self.ask(body, msgs, reason, k)
        self.cloud(body, msgs, reason, k, aux, t0, first)

    def ask(self, body, msgs, reason, k):
        """No data leaves: answer with the consent question instead."""
        _, what, sent = cloud_messages(msgs)
        names = [n for n, _, _, var in CLOUD if key(var)]
        if names:
            chain = names[0] + (f" (si no responde, {' o '.join(names[1:])})" if names[1:] else "")
            text = (f"{CONSENT_PREFIX}{reason}.\n"
                    f"Se enviaría a {chain}: {what}.\n"
                    "Si hay fotos o video, un modelo de visión de la nube también los mira (el sí vale para eso).\n"
                    "¿Lo envío? Respondé \"sí\" (o \"sí, siempre\" para el resto de esta conversación). "
                    "También podés elegir otro modelo con /model.")
        else:
            text = (f"{CONSENT_MARK} Para esto haría falta la nube ({reason}), pero no hay ninguna key de nube "
                    "configurada. Podés agregar una en la página de keys o elegir otro modelo con /model.")
        with _lock:
            sess = _turns.get(k, {}).get("session", "")[:8]
        log(route="ask", reason=reason.split(" (")[0], would_send=sent, total=len(msgs), context=CONTEXT,
            subagent=is_subagent(msgs), session=sess, armed=[x[:8] for x in _sessions.seen])   # hash prefixes, never text
        if k:
            with _lock:
                _turns.pop(k, None)                    # the person's answer is a new turn
        if is_subagent(msgs):                          # nobody can answer a 🔒 here, and the parent would relay it as a result
            return self.reply(503, {"error": {"message": f"router: the cloud is not authorized for this delegated task "
                                                         f"({reason}); the person has to agree in the main conversation",
                                              "type": "router"}})
        self.assistant(text, bool(body.get("stream")))

    def assistant(self, text, stream):
        now = int(time.time())
        if not stream:
            return self.reply(200, {"id": "router", "object": "chat.completion", "created": now, "model": "local-first",
                                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                                 "finish_reason": "stop"}],
                                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        for delta, fin in (({"role": "assistant", "content": text}, None), ({}, "stop")):
            chunk = {"id": "router", "object": "chat.completion.chunk", "created": now, "model": "local-first",
                     "choices": [{"index": 0, "delta": delta, "finish_reason": fin}]}
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def cloud(self, body, msgs, reason, k, aux, t0, first=True):
        out, what, sent = cloud_messages(msgs)
        base = {kk: v for kk, v in body.items() if kk in PASS_KEYS}
        tried = []
        for name, url, model, var in CLOUD:
            kv = key(var)
            if not kv:
                continue
            with _lock:
                notice_due = bool(k) and not _turns.get(k, {}).get("noticed")
            notice = turn_notice(k, f"☁️ Respondió la nube ({name}), {reason}. Viajó: {what}.\n\n" if notice_due else None)
            ok = self.forward(url + "/chat/completions", dict(base, model=model, messages=out),
                              {"Authorization": f"Bearer {kv}"}, notice, k, idle=IDLE_CLOUD)
            if ok is True:
                if first:                              # one decision per turn, not one per tool call
                    log(route="nube", reason=reason.split(" (")[0], provider=name, seconds=round(time.time() - t0, 1),
                        sent=sent, total=len(msgs), aux=aux, context=CONTEXT)
                return
            if ok is BROKEN:
                return log(route="none", reason="se cortó la respuesta de la nube", provider=name, tried=len(tried) + 1, aux=aux)
            tried.append(f"{name}: {ok}")
        log(route="none", reason=reason.split(" (")[0], tried=len(tried), aux=aux)
        self.assistant("⚠️ No respondió ningún modelo: ni el local ni la nube (" + "; ".join(tried or ["sin keys"]) +
                       "). Probá de nuevo en un rato o elegí otro modelo con /model.", bool(body.get("stream")))

    def vision(self, body, why, t0):
        """An image with no home model to read it (Hermes's vision call, `gateway video`): a cloud vision model if the person
        already consented to the cloud, else an error that says how to. Nothing is asked here: nobody reads this reply."""
        if not vision_allowed():
            log(route="vision-sin-permiso", reason=str(why), aux=True)
            return self.reply(503, {"error": {"message": "router: la imagen necesita la nube (el modelo local no responde) y la persona todavía "
                                                         "no la autorizó; decile que escriba \"usá la nube\" y vuelva a mandar la imagen",
                                              "type": "router"}})
        base = {kk: v for kk, v in body.items() if kk in PASS_KEYS and kk not in ("tools", "tool_choice")}
        tried = []
        for name, url, model, var in VISION_CLOUD:
            kv = key(var)
            if not kv:
                continue
            ok = self.forward(url + "/chat/completions", dict(base, model=model), {"Authorization": f"Bearer {kv}"}, None, None, idle=IDLE_CLOUD)
            if ok is True:
                return log(route="nube", reason="imagen, autorizaste la nube", provider=name, seconds=round(time.time() - t0, 1), aux=True)
            if ok is BROKEN:
                return log(route="none", reason="se cortó la respuesta de la nube (imagen)", provider=name, aux=True)
            tried.append(f"{name}: {ok}")
        log(route="none", reason="imagen", tried=len(tried), aux=True)
        self.reply(503, {"error": {"message": "router: ningún modelo de visión respondió (" + "; ".join(tried or ["sin keys"]) + ")", "type": "router"}})

    def forward(self, url, body, headers, notice, turn=None, idle=IDLE_CLOUD):
        """Send the request; stream (or return) the answer to Hermes. True, or a short error when nothing was sent
        yet (so the caller can try the next backend). BROKEN when the stream died after bytes went out: the person
        got an error chunk and the caller only logs it. A notice goes in front of the turn's final answer."""
        stream = bool(body.get("stream"))
        try:
            r = post(url, body, headers, idle)
        except urllib.error.HTTPError as e:
            return f"HTTP {e.code}"
        except Exception as e:
            return type(e).__name__
        broken = (OSError, http.client.HTTPException)
        with r:
            if not stream:
                try:
                    d = json.load(r)
                except broken + (ValueError,) as e:
                    return type(e).__name__
                msg = (d.get("choices") or [{}])[0].get("message", {})
                if notice and not msg.get("tool_calls"):
                    msg["content"] = notice + (msg.get("content") or "")
                    self.noticed(turn)
                return self.reply(200, d) or True
            if notice is None:                        # pass the stream straight through
                lines = iter(r)
                try:
                    line = next(lines, None)          # nothing is sent before the first byte, so a failure can fall back
                except broken as e:
                    return type(e).__name__
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                last = b""
                while line is not None:
                    self.wfile.write(line)
                    self.wfile.flush()
                    last = line.strip() or last
                    try:
                        line = next(lines, None)
                    except broken:
                        last = b""
                        break
                if last != b"data: [DONE]":           # http.client ends a cut chunked stream quietly: no [DONE] = cut
                    self.stream_error()
                    return BROKEN
                return True
            try:
                lines = r.read().splitlines(keepends=True)   # cloud is fast: buffer, to know if this is the final answer
            except broken as e:
                return type(e).__name__
        def has_tool_call(ln):                       # NVIDIA sends "tool_calls": null in every chunk
            try:
                return any((c.get("delta") or {}).get("tool_calls") for c in json.loads(ln[6:]).get("choices", []))
            except ValueError:
                return False
        tool_call = any(has_tool_call(ln) for ln in lines if ln.startswith(b"data: {"))
        first = next((json.loads(ln[5:]) for ln in lines if ln.startswith(b"data: {")), None)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if not tool_call and first:
            chunk = {"id": first.get("id", "router"), "object": "chat.completion.chunk", "created": first.get("created", int(time.time())),
                     "model": first.get("model", ""), "choices": [{"index": 0, "delta": {"role": "assistant", "content": notice},
                                                                    "finish_reason": None}]}
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.noticed(turn)
        self.wfile.writelines(lines)
        self.wfile.flush()
        return True

    def stream_error(self):
        """The backend went silent or dropped mid-stream: end the stream with a visible error instead of hanging."""
        chunk = {"id": "router", "object": "chat.completion.chunk", "created": int(time.time()), "model": "local-first",
                 "choices": [{"index": 0, "delta": {"content": "\n\n⚠️ Se cortó la respuesta del modelo. Probá de nuevo."},
                              "finish_reason": "stop"}]}
        try:
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\ndata: [DONE]\n\n")
            self.wfile.flush()
        except OSError:
            pass

    @staticmethod
    def noticed(turn):
        if turn:
            with _lock:
                if turn in _turns:
                    _turns[turn]["noticed"] = True
                    rel, _turns[turn]["release"] = _turns[turn].get("release"), None
                    if rel:                                  # shown: this person has seen this release
                        try:
                            with open(RELEASE_SEEN, "w") as f:
                                f.write(rel[0])
                        except OSError:
                            pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
