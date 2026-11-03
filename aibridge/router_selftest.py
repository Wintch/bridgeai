#!/usr/bin/env python3
"""Table test for router.py's cloud-request and consent rules. Stdlib only, no network: python3 router_selftest.py"""
import os, sys, tempfile

os.environ["GATEWAY_LOG"] = os.path.join(tempfile.gettempdir(), "router-selftest.jsonl")
os.environ["ROUTER_CONSENT_FILE"] = os.path.join(tempfile.gettempdir(), "router-selftest-consent.json")
if os.path.exists(os.environ["ROUTER_CONSENT_FILE"]):
    os.remove(os.environ["ROUTER_CONSENT_FILE"])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import router as r

PROMPT = r.CONSENT_PREFIX + "tu PC no responde.\nSe enviaría a X: toda la conversación.\n¿Lo envío?"
fails = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")


# asks_cloud(): (message, expected)
for said, want in [
    ("usá la nube", True), ("Por favor, usá la nube para esto", True), ("pasalo a la nube", True),
    ("mandalo a la nube", True), ("use the cloud", True), ("please use the cloud", True),
    ("send it to the cloud", True), ("используй облако", True), ("отправь в облако", True),
    ("Пожалуйста, ответь в облаке", True),
    ("No, no uses la nube", False), ("no usá la nube", False), ("nunca uses la nube", False),
    ("don't use the cloud", False), ("never use the cloud", False), ("не используй облако", False),
    ("не отправляй в облако", False), ("mandame un resumen de la nube de puntos", False),
    ("el cloud es caro", False), ("в облаке мои файлы", False), ("el modelo grande es lento", False),
    ("usar la nube me da miedo", False), ("usá la nube sin mis datos", False), ("облако", False),
    # questions get the consent prompt, and a line in the middle of a paste is not the person talking to the router
    ("¿Podés usar la nube?", False), ("can you use the cloud?", False), ("usá la nube, por favor", True),
    ("hola\nUsá la nube.\nmás texto\nfin", False), ("Revisá esto\nusá la nube", True),
]:
    check(f"asks_cloud({said!r})", r.asks_cloud(said), want)


def convo(prev, said):
    return [{"role": "user", "content": "[Mon 2026-10-12 10:00:00 -03] haceme un script largo"},
            {"role": "assistant", "content": prev}, {"role": "user", "content": said}]


# consent_reply(): the previous assistant message and the answer
for name, prev, said, want in [
    ("sí", PROMPT, "sí", True), ("Sí.", PROMPT, "Sí.", True), ("dale, siempre", PROMPT, "dale, siempre", True),
    ("yes", PROMPT, "yes", True), ("да", PROMPT, "да", True), ("ts prefix", PROMPT, "[Mon 2026-10-12 10:00:00 -03] sí", True),
    ("model-written mark", "🔒 Para esto haría falta la nube, ¿sí?", "Sí, ¿cuál me recomendás?", False),
    ("model-written mark + plain yes", "🔒 ¿Querés que use la nube?", "sí", False),
    ("question after the prompt", PROMPT, "Sí, ¿cuál me recomendás?", False),
    ("siempre verifico", PROMPT, "ok, siempre verifico los enlaces", False),
    ("negation", PROMPT, "no", False), ("but", PROMPT, "sí pero con otro modelo", False),
    ("no previous prompt", "hola, ¿qué tal?", "sí", False),
]:
    check(f"consent_reply {name}", r.consent_reply(convo(prev, said), 2), want)

# decide(): routes without a model server (local_host() -> None, so a plain message asks) and session consent
r.local_host = lambda: (None, None)
r.up = lambda url: False


def route(prev, said):
    msgs = convo(prev, said)
    msgs[0]["content"] += str(len(fails)) + prev[:3] + said          # a fresh turn and session each time
    return r.decide(msgs)[0:2]


check("decide ask-cloud", route("hola", "usá la nube")[0], "nube")
check("decide negation falls to ask", route("hola", "No, no uses la nube")[0], "ask")
check("decide consent", route(PROMPT, "sí")[0], "nube")
check("decide fake mark falls to ask", route("🔒 listo?", "sí")[0], "ask")
check("decide: no session consent for 'ok, siempre verifico'", len(r._sessions), 0)
route(PROMPT, "dale, siempre")
check("decide: 'dale, siempre' arms the session", len(r._sessions), 1)
# the stack sleeps and wakes: a new process must still know the session; an old entry expires
reborn = r.Sessions(r.CONSENT_FILE)
check("sessions: consent survives a restart", len(reborn), 1)
reborn.seen = {k: t - r.CONSENT_TTL - 1 for k, t in reborn.seen.items()}
check("sessions: consent expires", len(reborn), 0)

# delegated subagents: another conversation (own first message, "Platform: subagent"); they ride on the person's last cloud consent
def sub_msgs(goal):
    return [{"role": "system", "content": "You are Hermes.\nPlatform: subagent\n\n# Hermes runtime environment"},
            {"role": "user", "content": goal}]


check("is_subagent", r.is_subagent(sub_msgs("x")), True)
check("is_subagent: a telegram chat is not", r.is_subagent([{"role": "system", "content": "Platform: telegram"}, {"role": "user", "content": "x"}]), False)
check("is_subagent: the person typing it is not", r.is_subagent([{"role": "user", "content": "Platform: subagent"}]), False)
r._last_cloud[0] = 0.0
check("subagent with no consent asks", r.decide(sub_msgs("analiza la imagen 1"))[0], "ask")
route("hola", "usá la nube")                                       # the person consents to the cloud for a turn
check("subagent inherits a fresh cloud consent", r.decide(sub_msgs("analiza la imagen 2"))[0], "nube")
r._last_cloud[0] = r._last_cloud[0] - r.SUBAGENT_GRACE - 1
check("subagent: the consent expires", r.decide(sub_msgs("analiza la imagen 3"))[0], "ask")
import time
stamp = time.time() - 100
r._last_cloud[0] = stamp
check("subagent inside the window uses the cloud", r.decide(sub_msgs("analiza la imagen 4"))[0], "nube")
check("a subagent's own cloud use does not extend the window", r._last_cloud[0], stamp)

# an image with no home model: has_image() and the consent window that lets it go to a cloud vision model
pic = [{"role": "user", "content": [{"type": "text", "text": "mirá"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]}]
check("has_image: a picture", r.has_image(pic), True)
check("has_image: text parts only", r.has_image([{"role": "user", "content": [{"type": "text", "text": "hola"}]}]), False)
check("has_image: plain text", r.has_image([{"role": "user", "content": "hola"}]), False)
r._sessions.seen, r._last_cloud[0] = {}, 0.0
check("vision_allowed: no consent", r.vision_allowed(), False)
r._last_cloud[0] = time.time()
check("vision_allowed: a consented cloud turn just now", r.vision_allowed(), True)
r._last_cloud[0] = time.time() - r.SUBAGENT_GRACE - 1
check("vision_allowed: that consent expired", r.vision_allowed(), False)
r._sessions.seen = {"abc": time.time()}
check("vision_allowed: a live 'siempre'", r.vision_allowed(), True)
r._sessions.seen = {}

# idle question: after IDLE_HOURS without a message the router asks once (continue or /new); the answer is stripped before the model
def um(ts, text):
    return {"role": "user", "content": f"[{ts}] {text}"}


check("stamp with offset", r.stamp(um("Sat 2026-10-17 22:29:48 -03", "x")), 1792286988)
check("stamp without weekday or offset", r.stamp(um("2026-10-18 01:29:48", "x")), 1792286988)
check("stamp: none", r.stamp({"role": "user", "content": "hola"}), None)
old = [um("Sat 2026-10-17 10:00:00 -03", "q1"), {"role": "assistant", "content": "a1"}]
check("idle: 9 h later asks", round(r.idle_gap_hours(old + [um("Sat 2026-10-17 19:00:00 -03", "q2")]), 1), 9.0)
check("idle: 2 h later does not", r.idle_gap_hours(old + [um("Sat 2026-10-17 12:00:00 -03", "q2")]), None)
check("idle: unstamped message is never held", r.idle_gap_hours(old + [{"role": "user", "content": "q2"}]), None)
check("idle: mid tool loop is not held", r.idle_gap_hours(old + [um("Sat 2026-10-17 19:00:00 -03", "q2"), {"role": "tool", "content": "t"}]), None)
asked = old + [um("Sat 2026-10-17 19:00:00 -03", "q2"), {"role": "assistant", "content": r.idle_text(9, "hola")}]
check("idle: asked once, the answer goes through", r.idle_gap_hours(asked + [um("Sat 2026-10-17 19:01:00 -03", "seguir")]), None)
check("idle: Russian text", r.idle_text(9, "привет").split()[1], "Прошло")
got = r.strip_idle(asked + [um("Sat 2026-10-17 19:01:00 -03", "seguir")])
check("strip_idle drops the question and a plain 'seguir'", [r.text_of(m) for m in got], [r.text_of(m) for m in old + [asked[2]]])
got = r.strip_idle(asked + [um("Sat 2026-10-17 19:01:00 -03", "otra cosa: qué hora es")])
check("strip_idle keeps a real new message", len(got), 4)
r.IDLE_HOURS = 0
check("idle: 0 turns it off", r.idle_gap_hours(old + [um("Sat 2026-10-17 19:00:00 -03", "q2")]), None)
r.IDLE_HOURS = 5

# release notice: shown once per person, in front of the next final answer, in the language of the message
rel = os.path.join(tempfile.gettempdir(), "router-selftest-release.txt")
seen = rel + ".seen"
open(rel, "w", encoding="utf-8").write("id: r1\nes: hubo una actualización\nru: вышло обновление\n")
if os.path.exists(seen):
    os.remove(seen)
r.RELEASE_FILE, r.RELEASE_SEEN = rel, seen
check("release: pending, Spanish", r.release_pending("hola"), ("r1", "hubo una actualización"))
check("release: pending, Russian", r.release_pending("привет"), ("r1", "вышло обновление"))
r._turns["T"] = {"noticed": False, "release": r.release_pending("hola")}
check("release: notice carries the text and the cloud line", r.turn_notice("T", "CLOUD\n\n"), "hubo una actualización\n\nCLOUD\n\n")
check("release: not delivered yet, still pending", r.release_pending("hola") is not None, True)
r.Handler.noticed("T")
check("release: delivered, never again", r.release_pending("hola"), None)
check("release: turn has no notice left", r.turn_notice("T"), None)
open(rel, "w", encoding="utf-8").write("id: r2\nes: otra\n")
check("release: a new id shows again", r.release_pending("hola"), ("r2", "otra"))
check("release: missing file is quiet", (setattr(r, "RELEASE_FILE", rel + ".none"), r.release_pending("hola"))[1], None)

# strip_notices(): the router's own cloud line never reaches a model (it copied it: two lines per answer, 2026-10-21)
NOTE = "☁️ Respondió la nube (NVIDIA nemotron-3.5-super), tu PC (el modelo local) no responde. Viajó: toda la conversación.\n\n"
hist = [{"role": "user", "content": "q"}, {"role": "assistant", "content": NOTE + NOTE + "respuesta"},
        {"role": "assistant", "content": "texto que cita ☁️ Respondió la nube (x) en el medio"},
        {"role": "assistant", "content": PROMPT}, {"role": "user", "content": NOTE + "lo pegó la persona"},
        {"role": "assistant", "content": [{"type": "text", "text": NOTE + "parte"}]}]
got = r.strip_notices(hist)
check("strip_notices: both copied lines removed", got[1]["content"], "respuesta")
check("strip_notices: a mention mid-line stays", got[2]["content"], hist[2]["content"])
check("strip_notices: the consent prompt stays", got[3]["content"], PROMPT)
check("strip_notices: user text untouched", got[4]["content"], hist[4]["content"])
check("strip_notices: list content", got[5]["content"][0]["text"], "parte")
check("strip_notices: input not mutated", hist[1]["content"].count("☁️"), 2)

# cloud_messages(): with a narrow window the question travels, not just the "sí"
msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"}, {"role": "assistant", "content": PROMPT}, {"role": "user", "content": "sí"}]
for ctx, want in [("turn", ["q2", PROMPT, "sí"]), ("recent:1", ["q1", "a1", "q2", PROMPT, "sí"])]:
    r.CONTEXT = ctx
    out = r.cloud_messages(msgs)[0]
    check(f"cloud_messages {ctx}", [r.text_of(m) for m in out if m["role"] != "system"], want)

# a "no" to the consent question (2026-10-22 on hernik: home PC off, four "no" got the same question nine times)
for name, prev, said, want in [
    ("no", PROMPT, "no", True), ("No.", PROMPT, "No.", True), ("no, gracias", PROMPT, "no, gracias", True),
    ("нет", PROMPT, "нет", True), ("нет, не надо", PROMPT, "нет, не надо", True), ("ts prefix", PROMPT, "[Mon 2026-10-12 10:00:00 -03] no", True),
    ("no sé", PROMPT, "no sé", False), ("a new message", PROMPT, "no, mejor decime qué hora es en Moscú ahora", False),
    ("sí", PROMPT, "sí", False), ("gracias alone", PROMPT, "gracias", False), ("no prompt", "hola", "no", False),
    ("after the note", r.DECLINED_PREFIX + "entendido.", "no", True),
]:
    check(f"consent_decline {name}", r.consent_decline(convo(prev, said), 2), want)
check("consent_reply after the note", r.consent_reply(convo(r.DECLINED_PREFIX + "x", "sí"), 2), True)
check("consent_reply after the Russian prompt", r.consent_reply(convo(r.CONSENT_PREFIX_RU + "x", "да"), 2), True)
for said in ("da", "Da!", "davai", "ок", "хорошо, давай"):      # Russian in Latin letters ("da" on hernik 2026-10-22)
    check(f"consent_reply {said!r} after the Russian prompt", r.consent_reply(convo(r.CONSENT_PREFIX_RU + "x", said), 2), True)
check("consent_decline 'net'", r.consent_decline(convo(r.CONSENT_PREFIX_RU + "x", "net"), 2), True)
check("'da igual' is not a yes", r.consent_reply(convo(PROMPT, "da igual"), 2), False)
for said, want in [("sí, de una", True), ("sí, de una genio", True), ("dale, mandalo nomás", True), ("sí pero contame antes qué es", False),
                   ("sí? qué se manda", False), ("si no hay otra", False), ("hola, qué tal", False)]:  # a clear yes first (2026-10-22)
    check(f"consent_reply {said!r}", r.consent_reply(convo(PROMPT, said), 2), want)
q = [{"role": "user", "content": "q"}]
check("strip_declined: question and 'no' gone", r.strip_declined(q + [{"role": "assistant", "content": PROMPT}, {"role": "user", "content": "no"}]), q)
kept = q + [{"role": "assistant", "content": PROMPT}, {"role": "user", "content": "otra pregunta larga"}]
check("strip_declined: a new message stays", r.strip_declined(kept), kept)
check("lang_of: a Russian chat answered 'no'", r.lang_of([{"role": "user", "content": "привет, как дела"}, {"role": "assistant", "content": "x"},
                                                       {"role": "user", "content": "no"}], 2), "ru")
check("lang_of: Spanish", r.lang_of(convo(PROMPT, "no"), 2), "es")
check("ru: reason and what", r.ru("tu PC (el modelo local) no responde: toda la conversación, sin tus memorias"),
      "ваш ПК (локальная модель) не отвечает: весь разговор, без ваших заметок памяти")


class Fake(r.Handler):
    """The handler's text paths without a socket: assistant() keeps what the person would see."""
    def __init__(self):
        self.said = []

    def assistant(self, text, stream):
        self.said.append(text)


r.key = lambda var: "k"
r.CONTEXT = "full"


def chat(lines):
    """Replay a conversation through decide() and the handler's text paths the way do_POST does; returns what the person saw."""
    h, msgs = Fake(), []
    for said in lines:
        msgs.append({"role": "user", "content": said})
        route, reason, k, _ = r.decide(msgs)
        if route == "ask":
            h.ask({}, msgs, reason, k)
        elif route == "no":
            h.declined_note({}, msgs, reason, k)
        else:
            h.said.append(route)
        msgs.append({"role": "assistant", "content": h.said[-1]})
    return h.said


got = chat(["Привет, расскажи мне что-нибудь интересное", "no", "no", "Ну ладно, а сколько сейчас времени в Москве", "да"])
check("incident: one full question, in Russian", got[0].startswith(r.CONSENT_PREFIX_RU), True)
check("incident: 'no' gets the short note", [t[:len(r.DECLINED_PREFIX_RU)] for t in got[1:4]], [r.DECLINED_PREFIX_RU] * 3)
check("incident: the notes are shorter than the question", max(len(t) for t in got[1:4]) < len(got[0]) * 0.7, True)
check("incident: a new message after 'no' names what 'да' sends", "весь разговор" in got[3], True)
check("incident: 'да' to the note sends it", got[4], "nube")
got = chat(["Necesito ayuda con un tema largo de trabajo", "no", "sí"])
check("es: question, note, cloud", [got[0][:len(r.CONSENT_PREFIX)], got[1][:len(r.DECLINED_PREFIX)], got[2]], [r.CONSENT_PREFIX, r.DECLINED_PREFIX, "nube"])
msgs = [{"role": "user", "content": "Otra charla distinta para probar el plazo"}]
msgs += [{"role": "assistant", "content": PROMPT}, {"role": "user", "content": "no"}]
r.decide(msgs)
for s_ in list(r._declined):
    r._declined[s_] -= r.DECLINE_TTL + 1
msgs += [{"role": "assistant", "content": r.DECLINED_PREFIX + "entendido."}, {"role": "user", "content": "y ahora esto otro, más largo"}]
check("decline expires: the full question again", r.decide(msgs)[0], "ask")
r._declined.clear()
r.local_host, r.up = (lambda: ("http://home", "gemma")), (lambda url: True)
r.classify = lambda url, model, msgs, u: "nube"
got = chat(["Escribime un programa largo en Python por favor", "no", "y otra cosa difícil más"])
check("home up: 'no' sends the question home", got[1:], ["local", "local"])
r.local_host, r.up = (lambda: (None, None)), (lambda url: False)

# home model: reasoning off by default, but the caller's own setting wins
check("local body: thinking off", r.local_body({"messages": []}, "m")["chat_template_kwargs"], {"enable_thinking": False})
check("local body: caller wins", r.local_body({"chat_template_kwargs": {"enable_thinking": True}}, "m")["chat_template_kwargs"], {"enable_thinking": True})
check("local body: model set", r.local_body({"model": "local-first"}, "gemma")["model"], "gemma")
# a provider's status page says its API is down: its backends go last, not away; an expired entry or a broken file is
# ignored
import json as _json, time as _time
r.PROVIDER_STATUS = os.path.join(tempfile.gettempdir(), "router-selftest-provider-status.json")
gem, nv = ("Gemini x", "https://generativelanguage.googleapis.com/v1beta/openai", "m", "K"), ("NVIDIA y", "https://integrate.api.nvidia.com/v1", "m", "K")
def status(entries):
    with open(r.PROVIDER_STATUS, "w") as f:
        _json.dump({"avoid": entries}, f)
    r._status_cache[:] = [None, {}]                    # two writes within one mtime tick
status([{"host": "generativelanguage.googleapis.com", "until": _time.time() + 600}])
check("provider status: a host in an incident is tried last", [b[0] for b in r.by_health([gem, nv])], ["NVIDIA y", "Gemini x"])
status([{"host": "generativelanguage.googleapis.com", "until": _time.time() - 1}, {"host": "x", "until": 0}])
check("provider status: an expired entry no longer counts", [b[0] for b in r.by_health([gem, nv])], ["Gemini x", "NVIDIA y"])
open(r.PROVIDER_STATUS, "w").write("{broken")
r._status_cache[:] = [None, {}]
check("provider status: a broken file is ignored", r.avoided_hosts(), set())
os.remove(r.PROVIDER_STATUS)
check("provider status: no file, nothing avoided", r.avoided_hosts(), set())
# stray foreign-script fragments inside words are dropped from answers; real foreign text is kept
for text, want in [("Это слово한어во в тексте", "Это словово в тексте"), ("Hola mundo日 qué tal", "Hola mundo qué tal"),
                   ("ссылка: 東京 и дальше", "ссылка: 東京 и дальше"), ("日本語のテキストです", "日本語のテキストです"),
                   ("Название (Café) ок", "Название (Café) ок"), ("emoji 🚀 ok", "emoji 🚀 ok")]:
    check(f"scrub {text!r}", r.Scrub().text(text), want)
sc = r.Scrub()
check("scrub across stream chunks", sc.feed("сло") + sc.feed("во한") + sc.feed("ой") + sc.end(), "словоой")
sc = r.Scrub()
check("scrub: a fragment at the very end touching a word is dropped", sc.feed("готово한") + sc.end(), "готово")
check("scrub off: untouched", r.Scrub(on=False).text("слово한во"), "слово한во")
ln = b'data: {"choices": [{"index": 0, "delta": {"content": "\xd1\x82\xd0\xb5\xea\xb0\x80\xd1\x81\xd1\x82"}, "finish_reason": null}]}\n'
check("scrub SSE line: content cleaned", r.json.loads(r.Scrub().line(ln)[6:])["choices"][0]["delta"]["content"], "тест")
tl = b'data: {"choices": [{"index": 0, "delta": {"tool_calls": [{"function": {"arguments": "{\\"q\\": \\"\xe6\x9d\xb1x\\"}"}}]}}]}\n'
check("scrub SSE line: tool calls untouched", r.Scrub().line(tl), tl)
check("scrub SSE line: [DONE] untouched", r.Scrub().line(b"data: [DONE]\n"), b"data: [DONE]\n")
# a key the person pasted on the keys page (credential pool) comes before the stack's .env key; one that fails is set
# aside for an hour so the provider keeps working on the stack's key (2026-11-01)
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("router_fresh", os.path.join(os.path.dirname(os.path.abspath(__file__)), "router.py"))
r = _ilu.module_from_spec(_spec); _spec.loader.exec_module(r)      # earlier checks replaced router.key with a stub
_aj, _envk = r.AUTH_JSON, os.environ.get("NVIDIA_API_KEY")
r.AUTH_JSON = os.path.join(tempfile.mkdtemp(), "auth.json")
_json.dump({"credential_pool": {"nvidia": [{"api_key": "nvapi-own"}]}}, open(r.AUTH_JSON, "w"))
os.environ["NVIDIA_API_KEY"] = "nvapi-stack"
r._own_failed.clear()
check("own key from the keys page first", r.key("NVIDIA_API_KEY"), "nvapi-own")
r._own_failed[("NVIDIA_API_KEY", "nvapi-own")] = _time.time()
check("an own key the provider refused: the stack's key for the next hour", r.key("NVIDIA_API_KEY"), "nvapi-stack")
r._own_failed[("NVIDIA_API_KEY", "nvapi-own")] = _time.time() - 3700
check("...and the own key again after it", r.key("NVIDIA_API_KEY"), "nvapi-own")
os.environ["NVIDIA_API_KEY"] = ""
r._own_failed[("NVIDIA_API_KEY", "nvapi-own")] = _time.time()
check("a refused own key with nothing to fall back on is still used (no key would be worse)", r.key("NVIDIA_API_KEY"), "nvapi-own")
_json.dump({"credential_pool": {"nvidia": [{"api_key": "nvapi-seeded", "priority": 5, "auth_type": "api_key"},
                                           {"api_key": "nvapi-web", "priority": 0, "auth_type": "api_key"}]}}, open(r.AUTH_JSON, "w"))
check("the pool entry with the best priority wins, as on the keys page", r.key("NVIDIA_API_KEY"), "nvapi-web")
_envfile = os.path.join(os.path.dirname(r.AUTH_JSON), ".env")
open(_envfile, "w").write("TOKENHARBOR_API_KEY=th-person\n")
_he, r.HERMES_ENV = r.HERMES_ENV, _envfile
os.environ["TOKENHARBOR_API_KEY"] = "th-operator"
check("a key the person saved in their .env beats the operator's environment", r.key("TOKENHARBOR_API_KEY"), "th-person")
r.HERMES_ENV = _he
os.environ.pop("TOKENHARBOR_API_KEY", None)
r.AUTH_JSON, r._own_failed = _aj, {}
if _envk is None:
    os.environ.pop("NVIDIA_API_KEY", None)
else:
    os.environ["NVIDIA_API_KEY"] = _envk
# A 429 from Token Harbor is the account's allowance: every model there goes last, NVIDIA's do not (2026-11-01)
r._limited.clear()
r.note_health("Token Harbor mimo-v2.6-flash", "HTTP 429")
by = {c[0]: c for c in r.CANDIDATES}
check("a Token Harbor 429 cools every Token Harbor model, no NVIDIA one",
      (r.cooling(by["Token Harbor deepseek-v4-flash"]), r.cooling(by["Token Harbor deepseek-v4.1-flash"]),
       r.cooling(by["NVIDIA nemotron-3.5-super"])), (True, True, False))
r.note_health("NVIDIA gpt-oss-20b", "HTTP 429")
check("an NVIDIA 429 cools that model only", (r.cooling(by["NVIDIA gpt-oss-20b"]), r.cooling(by["NVIDIA nemotron-3-ultra"])), (True, False))
r._limited.clear()

# A 429 that announces when the free allowance returns (Token Harbor, 2026-11-02) is remembered: those models are not tried until
# then, the memory survives a restart of the router, a different key starts clean, and one try in RECHECK still goes out.
import calendar, io, json as _json, stat, time as _time
_state = os.path.join(tempfile.gettempdir(), "router-selftest-limits.json")
if os.path.exists(_state):
    os.remove(_state)
r.LIMITS_STATE = _state
r._exhausted.clear(); r._exh_mtime[0] = None
_real_key = r.key
r.key = lambda var: os.environ.get(var, "")
os.environ["TOKENHARBOR_API_KEY"] = "thk-selftest-key-one"
os.environ["NVIDIA_API_KEY"] = "nvapi-selftest-key"
MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
def announced(epoch):
    t = _time.gmtime(epoch)
    return ("Your free allowance for ':free' models is used up. It comes back on %d %s %d at %02d:%02d UTC. Your account is not "
            "limited: remove ':free' from the model name." % (t.tm_mday, MON[t.tm_mon - 1], t.tm_year, t.tm_hour, t.tm_min))
class FakeErr:
    def __init__(self, msg, code="free_tier_limit_reached"):
        self.b = _json.dumps({"error": {"message": msg, "type": code, "code": code}}).encode()
    def read(self, n=-1):
        return self.b
URL = "https://tokenharbor.ai/v1/chat/completions"
AUTH = {"Authorization": "Bearer thk-selftest-key-one"}
check("parse_reset reads the announced date", r.parse_reset("It comes back on 6 Nov 2026 at 23:05 UTC."),
      calendar.timegm((2026, 11, 6, 23, 5, 0)))
check("parse_reset: no date in the text", (r.parse_reset("rate limit"), r.parse_reset(""), r.parse_reset(None)), (None, None, None))
check("parse_reset: an unknown month", r.parse_reset("It comes back on 6 Xyz 2026 at 23:05 UTC."), None)

by = {c[0]: c for c in r.CANDIDATES}
th = [by[n] for n in ("Token Harbor deepseek-v4-flash", "Token Harbor mimo-v2.6-flash", "Token Harbor deepseek-v4.1-flash")]
nv = by["NVIDIA nemotron-3-ultra"]
future = _time.time() + 3 * 86400
r.learn_limit(URL, AUTH, FakeErr(announced(future)))
check("an announced reset makes every Token Harbor model exhausted", [r.exhausted(c) for c in th], [True, True, True])
check("NVIDIA is not exhausted by it", r.exhausted(nv), False)
check("by_health drops the exhausted models, not just last", [c[0] for c in r.by_health(th + [nv])], ["NVIDIA nemotron-3-ultra"])
check("when everything is exhausted all are still returned", len(r.by_health(th)), 3)
check("the state file holds a fingerprint, never the key",
      "thk-selftest-key-one" not in open(_state).read() and stat.S_IMODE(os.stat(_state).st_mode) == 0o600, True)
r._exhausted.clear(); r._exh_mtime[0] = None
check("the memory survives a router restart (read back from the file)", r.exhausted(th[0]), True)
os.environ["TOKENHARBOR_API_KEY"] = "thk-selftest-key-two"
check("a different key (another account) is not exhausted", r.exhausted(th[0]), False)
os.environ["TOKENHARBOR_API_KEY"] = "thk-selftest-key-one"
r._exhausted["tokenharbor.ai"]["checked"] = _time.time() - r.RECHECK - 5
check("after RECHECK one try goes out again", r.exhausted(th[0]), False)
r.learn_limit(URL, AUTH, FakeErr(announced(future)))
check("a new 429 renews the check", r.exhausted(th[0]), True)
r.note_health("Token Harbor deepseek-v4-flash", True)
check("a success clears the entry, in memory and in the file",
      (r.exhausted(th[0]), "tokenharbor.ai" in _json.load(open(_state))), (False, False))
r.learn_limit(URL, AUTH, FakeErr(announced(_time.time() - 3600)))
check("a reset date already past is ignored", r.exhausted(th[0]), False)
r.learn_limit(URL, AUTH, FakeErr("Too many requests, slow down.", "rate_limit"))
check("a 429 with no announced date leaves the 10-minute cooldown only", r.exhausted(th[0]), False)
r._limited.clear()
r.note_health("Token Harbor mimo-v2.6-flash", "HTTP 429")
check("...and that cooldown still cools the host", r.cooling(th[0]), True)
r.key = _real_key
r._limited.clear(); r._exhausted.clear(); r._exh_mtime[0] = None
os.environ.pop("TOKENHARBOR_API_KEY", None); os.environ.pop("NVIDIA_API_KEY", None)
if _envk is not None:
    os.environ["NVIDIA_API_KEY"] = _envk
print("\n".join(fails) or "router_selftest: all ok")
sys.exit(1 if fails else 0)
