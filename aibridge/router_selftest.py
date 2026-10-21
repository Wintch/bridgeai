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

# home model: reasoning off by default, but the caller's own setting wins
check("local body: thinking off", r.local_body({"messages": []}, "m")["chat_template_kwargs"], {"enable_thinking": False})
check("local body: caller wins", r.local_body({"chat_template_kwargs": {"enable_thinking": True}}, "m")["chat_template_kwargs"], {"enable_thinking": True})
check("local body: model set", r.local_body({"model": "local-first"}, "gemma")["model"], "gemma")
print("\n".join(fails) or "router_selftest: all ok")
sys.exit(1 if fails else 0)
