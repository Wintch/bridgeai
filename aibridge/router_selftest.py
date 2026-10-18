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
