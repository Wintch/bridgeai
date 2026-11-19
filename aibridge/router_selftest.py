#!/usr/bin/env python3
"""Table test for router.py's cloud-request and consent rules. Stdlib only, no network: python3 router_selftest.py"""
import os, sys, tempfile
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))

os.environ["GATEWAY_LOG"] = os.path.join(tempfile.gettempdir(), "router-selftest.jsonl")
os.environ["ROUTER_CONSENT_FILE"] = os.path.join(tempfile.gettempdir(), "router-selftest-consent.json")
if os.path.exists(os.environ["ROUTER_CONSENT_FILE"]):
    os.remove(os.environ["ROUTER_CONSENT_FILE"])
_lang_dir = tempfile.mkdtemp()                     # the person's /idioma file and the stack's gateways.json: absent unless a case writes them
os.environ["AIBRIDGE_PREFS"] = os.path.join(_lang_dir, "prefs.json")
os.environ["GATEWAYS_CONFIG"] = os.path.join(_lang_dir, "gateways.json")
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
late = "Sat 2026-10-17 16:00:00 -03"
check("idle: plain text after 6 h still asks", round(r.idle_gap_hours(old + [um(late, "q2")]), 1), 6.0)
check("idle: video notice after 6 h is not held", r.idle_gap_hours(old + [um(late, "[The user sent a video attachment: 'x.mp4'. It is saved at: /tmp/x.mp4]")]), None)
check("idle: document notice after 6 h is not held", r.idle_gap_hours(old + [um(late, "[The user sent a document: 'a.pdf'. It is saved at: /tmp/a.pdf]")]), None)
check("idle: image notice ('an image') after 6 h is not held", r.idle_gap_hours(old + [um(late, "[The user sent an image: 'a.jpg'. It is saved at: /tmp/a.jpg]")]), None)
check("idle: replied-to file after 6 h is not held", r.idle_gap_hours(old + [um(late, "[Replied-to message saved at: /tmp/a.mp4] mirá esto")]), None)
check("idle: image_url part after 6 h is not held", r.idle_gap_hours(old + [{"role": "user", "content": [
    {"type": "text", "text": f"[{late}] mirá"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}]), None)
check("idle: voice message after 6 h still asks", round(r.idle_gap_hours(old + [um(late, "[The user sent a voice message: 'v.ogg'. Transcript: hola]")]), 1), 6.0)
r.IDLE_HOURS = 0
check("idle: 0 turns it off", r.idle_gap_hours(old + [um("Sat 2026-10-17 19:00:00 -03", "q2")]), None)
r.IDLE_HOURS = 5

# the waker's own inactivity note (warm stacks): /workdir/.idle_notice newer than the person's previous message covers the stretch
r.IDLE_NOTICE = os.path.join(tempfile.gettempdir(), "router-selftest-idle-notice")
if os.path.exists(r.IDLE_NOTICE):
    os.remove(r.IDLE_NOTICE)
q2 = old + [um("Sat 2026-10-17 19:00:00 -03", "q2")]
before_q1 = r.stamp(old[0])
check("idle notice: no file, the router still asks", round(r.idle_gap_hours(q2), 1), 9.0)
open(r.IDLE_NOTICE, "w").write(f"{before_q1 + 6 * 3600}\n")
check("idle notice: the waker told the person after their previous message, so no second question", r.idle_gap_hours(q2), None)
open(r.IDLE_NOTICE, "w").write(f"{before_q1 - 60}\n")
check("idle notice: a note from an earlier stretch does not count", round(r.idle_gap_hours(q2), 1), 9.0)
open(r.IDLE_NOTICE, "w").write("garbage")
check("idle notice: an unreadable file is ignored", round(r.idle_gap_hours(q2), 1), 9.0)
open(r.IDLE_NOTICE, "w").write(f"{before_q1 + 6 * 3600}\n")
q3 = q2 + [{"role": "assistant", "content": "a2"}, um("Sun 2026-10-18 20:00:00 -03", "q3")]   # a NEW stretch, 25 h later, no new note
check("idle notice: a later stretch without a note asks again", round(r.idle_gap_hours(q3), 1), 25.0)
os.remove(r.IDLE_NOTICE)

# human_turn(): what the router records for the waker (a real user message, never a subagent, a cron or injected text)
sysm = lambda t: {"role": "system", "content": t}
check("human_turn: a plain user message", r.human_turn([sysm("Platform: telegram"), um("Sat 2026-10-17 19:00:00 -03", "hola")]), True)
check("human_turn: the web chat (no stamp)", r.human_turn([sysm("Platform: api_server"), {"role": "user", "content": "hola"}]), True)
check("human_turn: mid tool loop (last message is a tool result)", r.human_turn([um("Sat 2026-10-17 19:00:00 -03", "q"), {"role": "tool", "content": "t"}]), False)
check("human_turn: a delegated subagent", r.human_turn([sysm("Platform: subagent"), {"role": "user", "content": "tarea"}]), False)
check("human_turn: a cron run", r.human_turn([sysm("Platform: cron"), {"role": "user", "content": "run the job"}]), False)
check("human_turn: a platform that is not a person's (a cron whose prompt differs from the guess)", r.human_turn([sysm("sys\nPlatform: scheduler\nmore"), {"role": "user", "content": "run"}]), False)
check("human_turn: a person's platform line inside a longer prompt", r.human_turn([sysm("sys\nPlatform: telegram\nmore"), {"role": "user", "content": "hola"}]), True)
check("human_turn: injected system text", r.human_turn([sysm("Platform: telegram"), um("Sat 2026-10-17 19:00:00 -03", "[SYSTEM: a background process finished]")]), False)
check("human_turn: empty", r.human_turn([]), False)
check("human_turn: reply-language tag then a person's text", r.human_turn([sysm("Platform: telegram"), um("Sat 2026-10-17 19:00:00 -03", "[reply in Spanish] hola")]), True)
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("tareas_run", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops", "wake", "tareas_run.py"))
_tr = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_tr)
check("human_turn: a board task run on the web API is not the person (with stamp and reply tag)",
      r.human_turn([sysm("Platform: api_server"), um("Sat 2026-10-17 19:00:00 -03", "[reply in Spanish] " + _tr.PROMPT)]), False)
check("human_turn: a board task result run is not the person", r.human_turn([sysm("Platform: api_server"), {"role": "user", "content": _tr.DONE_PROMPT.format(nums="#1")}]), False)
r.LAST_HUMAN = os.path.join(tempfile.gettempdir(), "router-selftest-last-human")
if os.path.exists(r.LAST_HUMAN):
    os.remove(r.LAST_HUMAN)
r._last_human_at[0] = 0.0
check("touch_human: writes the epoch", r.touch_human(1_800_000_000.0) and open(r.LAST_HUMAN).read().strip() == "1800000000", True)
check("touch_human: not rewritten within the throttle", r.touch_human(1_800_000_002.0), False)
check("touch_human: rewritten after it", r.touch_human(1_800_000_010.0) and open(r.LAST_HUMAN).read().strip() == "1800000010", True)
_um = os.umask(0o077)                                   # Hermes's own umask: the waker on the host must still be able to read the file
try:
    check("touch_human: readable by the waker under umask 077", r.touch_human(1_800_000_020.0) and (os.stat(r.LAST_HUMAN).st_mode & 0o777) == 0o644, True)
finally:
    os.umask(_um)
r.LAST_HUMAN = "/nonexistent-dir/.last_human"
r._last_human_at[0] = 0.0
check("touch_human: an unwritable workdir never raises", r.touch_human(1_800_000_100.0), False)

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

# night job summary on the web chat: peeked at the turn's start, shown in front of the answer, acknowledged once shown
nd = tempfile.mkdtemp(prefix="router-selftest-night-")
os.makedirs(os.path.join(nd, "data"))
r.JOB_PENDING = os.path.join(nd, "data", ".jobpush-pending.json")
r.JOBPUSH = os.path.join(nd, "fake_jobpush.py")
acked = os.path.join(nd, "acked")
open(r.JOBPUSH, "w").write("import json, sys\n"
                           "if sys.argv[2] == 'peek': print(json.dumps({'id': 'n1', 'text': 'Resumen de la noche: 2 ofertas'}))\n"
                           f"else: open({acked!r}, 'w').write(sys.argv[3])\n")
web = [{"role": "system", "content": "sys\nPlatform: api_server\n"}, {"role": "user", "content": "hola"}]
tg = [{"role": "system", "content": "sys\nPlatform: telegram\n"}, {"role": "user", "content": "hola"}]
check("night: no file, nothing (no peek)", r.night_pending(web), None)
open(r.JOB_PENDING, "w").write("{}")
check("night: Telegram has the wake hook", r.night_pending(tg), None)
check("night: web chat gets it", r.night_pending(web), ("n1", "Resumen de la noche: 2 ofertas"))
k, first = r.direct_turn(web)
check("night: in front of the answer", (first, r.turn_notice(k)), (True, "Resumen de la noche: 2 ofertas\n\n"))
check("night: a tool call of the same turn does not peek again", r.direct_turn(web + [{"role": "assistant", "content": "x"}])[1], False)
r.Handler.noticed(k)
for _ in range(50):
    if os.path.exists(acked):
        break
    time.sleep(0.1)
check("night: acknowledged with its id once shown", open(acked).read() if os.path.exists(acked) else None, "n1")
check("night: turn has no notice left", r.turn_notice(k), None)
peeks = []
_np, r.night_pending = r.night_pending, (lambda m: peeks.append(1) or None)
r.direct_turn(web + [{"role": "assistant", "content": "x"}])
check("night: same file version, no second peek", len(peeks), 0)
os.utime(r.JOB_PENDING, (time.time() + 5, time.time() + 5))
r.direct_turn(web)
check("night: a new night run is peeked again for the same opening words", len(peeks), 1)
r.decide(web)
check("night: decide() follows the same rule", len(peeks), 1)
r.night_pending = _np
r.JOB_PENDING = os.path.join(nd, "none.json")

# a background job that was cut or failed (the work ledger, trabajos.py): one line in front of the next answer on EVERY platform,
# once, in the person's language, acknowledged when shown; without the program or the ledger the router does nothing
import importlib.util, json
_td = tempfile.mkdtemp(prefix="router-selftest-ledger-")
os.environ["TRABAJOS_DIR"] = os.path.join(_td, "ledger")
_tp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trabajos.py")
_spec = importlib.util.spec_from_file_location("trabajos_for_router", _tp)
tj = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(tj)
r.LEDGER_FILE, r.LEDGER_CMD = os.path.join(tj.ROOT, "ledger.json"), _tp
r.LEDGER_NOTICE = True                                   # off by default (the jobs plugin gives the notice); the code path is still checked
tg2 = [{"role": "system", "content": "sys\nPlatform: telegram\n"}, {"role": "user", "content": "[Mon 2026-11-03 10:00:00 -03] qué pasó con el clip?"}]
web2 = [{"role": "system", "content": "sys\nPlatform: api_server\n"}, {"role": "user", "content": "hola, sigamos"}]
check("ledger: no ledger file, nothing (no subprocess)", r.ledger_pending("es"), None)
_lid = tj.start("clip v7", "video", "gateway makevideo v7 /workdir/descargas/v7.mp4", pid=None)
tj.finish(_lid, None, state="cortado", reason="x", notified=False)
check("ledger: a cut job is pending, in Spanish", r.ledger_pending("es"), (_lid, f"⚠️ Se cortó: clip v7 ({_lid}). /jobs para ver, o pedime que lo relance."))
check("ledger: in English and Russian", (r.ledger_pending("en")[1].startswith("⚠️ Cut off: clip v7"), r.ledger_pending("ru")[1].startswith("⚠️ Оборвалось: clip v7")), (True, True))
check("ledger: peeking does not acknowledge", r.ledger_pending("es") is not None, True)
for _name, _msgs in (("Telegram", tg2), ("web chat", web2)):
    _k, _first = r.direct_turn(_msgs)
    check(f"ledger: {_name} gets the line in front of the answer", (_first, r.turn_notice(_k)),
          (True, f"⚠️ Se cortó: clip v7 ({_lid}). /jobs para ver, o pedime que lo relance.\n\n"))
    check(f"ledger: {_name}: it rides with the cloud line", r.turn_notice(_k, "CLOUD\n\n").endswith("relance.\n\nCLOUD\n\n"), True)
_peeks = []
_lp, r.ledger_pending = r.ledger_pending, (lambda lang: _peeks.append(lang) or None)
r.direct_turn(web2 + [{"role": "assistant", "content": "x"}])
r.decide(web2)
check("ledger: a tool call of the same turn does not peek again", len(_peeks), 0)
r.ledger_pending = _lp
_k, _ = r.direct_turn(web2)
r.Handler.noticed(_k)
for _ in range(80):
    if tj.load()["entries"][0]["notified"]:
        break
    time.sleep(0.1)
check("ledger: acknowledged with its ids once shown", tj.load()["entries"][0]["notified"], True)
check("ledger: the turn has no line left", r.turn_notice(_k), None)
check("ledger: shown once: nothing pending now", r.ledger_pending("es"), None)
_k2, _ = r.direct_turn(tg2 + [{"role": "assistant", "content": "a"}, {"role": "user", "content": "otra cosa"}])
check("ledger: a later turn has none", r.turn_notice(_k2), None)
_lid2 = tj.start("clip v8", "video", "gateway makevideo v8 /workdir/descargas/v8.mp4", pid=None)
tj.finish(_lid2, 5, reason="GPU: busy", notified=False)
check("ledger: the same opening words come back after the line was shown: peeked again (the ledger changed)",
      r.direct_turn(web2)[0] == _k and (r.turn_notice(_k) or "").startswith("⚠️ Falló: clip v8"), True)
check("ledger: a failed one says why", "GPU: busy" in (r.turn_notice(_k) or ""), True)
r.Handler.noticed(_k)
time.sleep(1.0)
tj.finish(tj.start("clip v10", "video", "gateway makevideo v10 /workdir/v10.mp4", pid=None), None, state="cortado", notified=False)
_sk, _ = r.direct_turn([{"role": "system", "content": "sys\nPlatform: subagent\n"}, {"role": "user", "content": "tarea para el subagente"}])
check("ledger: a subagent turn gets no line even with one pending", (r.ledger_pending("es") is not None, r.turn_notice(_sk)), (True, None))
r.LEDGER_CMD = os.path.join(_td, "no-such-program")
tj.finish(tj.start("clip v9", "video", "gateway makevideo v9 /workdir/v9.mp4", pid=None), None, state="cortado", notified=False)
check("ledger: without the program the router does nothing", r.ledger_pending("es"), None)
r.LEDGER_CMD = _tp
open(os.path.join(_td, "broken.py"), "w").write("print('not json')\n")
r.LEDGER_CMD = os.path.join(_td, "broken.py")
check("ledger: a program that answers garbage is ignored", r.ledger_pending("es"), None)
r.LEDGER_CMD = _tp
r.LEDGER_FILE = os.path.join(_td, "nothing.json")

# strip_notices(): the router's own cloud line never reaches a model
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

# cloud_direct keeps the memory and profile blocks (they were stripped on every call and the model forgot every saved
# note); consented cloud turns still strip them
BAR = "═" * 46
SYS = ("You are Hermes.\n\n" + BAR + "\nMEMORY (your personal notes) [90% — 1,980/2,200 chars]\n" + BAR + "\nnota uno\n§\nnota dos"
       "\n\n" + BAR + "\nUSER PROFILE (who the user is) [80%]\n" + BAR + "\nperfil\n\nConversation started: hoy")
mm = [{"role": "system", "content": SYS}, {"role": "user", "content": "hola"}]
r.CONTEXT = "full"
out, what, _ = r.cloud_messages(mm)
check("cloud_messages strips memory by default", ("nota uno" in out[0]["content"], "perfil" in out[0]["content"],
                                                  "Conversation started" in out[0]["content"], what.endswith("sin tus memorias")),
      (False, False, True, True))
out, what, _ = r.cloud_messages(mm, keep_memory=True)
check("cloud_messages keep_memory (cloud_direct)", (out[0]["content"], what), (SYS, "toda la conversación"))

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
for said in ("da", "Da!", "davai", "ок", "хорошо, давай"):      # Russian in Latin letters
    check(f"consent_reply {said!r} after the Russian prompt", r.consent_reply(convo(r.CONSENT_PREFIX_RU + "x", said), 2), True)
check("consent_decline 'net'", r.consent_decline(convo(r.CONSENT_PREFIX_RU + "x", "net"), 2), True)
check("'da igual' is not a yes", r.consent_reply(convo(PROMPT, "da igual"), 2), False)
for said, want in [("sí, de una", True), ("sí, de una genio", True), ("dale, mandalo nomás", True), ("sí pero contame antes qué es", False),
                   ("sí? qué se manda", False), ("si no hay otra", False), ("hola, qué tal", False)]:  # a clear yes first
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


class Sent(Fake):
    """cloud() up to the provider call: keeps the messages that would leave."""
    def forward(self, url, body, headers, notice, turn=None, **kw):
        self.out = body["messages"]
        self.meter = None
        return True


for reason, want in [(r.DIRECT, True), ("pediste la nube", False)]:
    h = Sent()
    h.scrub = type("S", (), {"runs": 0})()
    h.cloud({}, mm, reason, None, True, 0)
    check(f"cloud() memory travels: {reason}", "nota uno" in h.out[0]["content"], want)

# an image with no home model: the vision chain order, thinking off for the NVIDIA reasoning models, a short idle window,
# and a hung first model falling through to the next one inside Hermes's 120 s
class Pic(Fake):
    """vision() up to the provider call: records each (model, request field, idle) and answers from a script."""
    def __init__(self, script):
        super().__init__()
        self.script, self.calls, self.bodies = list(script), [], []

    def forward(self, url, body, headers, notice, turn=None, idle=None, need_text=False):
        self.calls.append((body["model"], body.get("chat_template_kwargs"), idle))
        self.bodies.append((url, body))
        self.meter = None
        return self.script.pop(0)

    def reply(self, code, obj):
        pass


def see(script):
    r._hung.clear(); r._limited.clear()
    h = Pic(script)
    h.vision({"messages": pic, "stream": False}, r.DIRECT, time.time())
    return h.calls


SUPER, OMNI, ORL, GEM = [c[2] for c in r.VISION_CLOUD]
check("vision chain: both NVIDIA first, then the free OpenRouter model, Gemini last",
      (SUPER, OMNI, ORL, GEM), ("nvidia/nemotron-3.5-super-vl-120b-a12b", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
                                "inclusionai/ling-3.2-flash:free", "gemini-3.5-flash-lite"))
check("vision idle window: every model fits inside Hermes's 120 s", len(r.VISION_CLOUD) * r.IDLE_VISION < 120, True)
check("vision idle window: below the old 45 s, above the slowest answer seen (18.8 s)", 18.8 < r.IDLE_VISION < 45, True)
calls = see([True])
check("vision: first model answers, one call, thinking off, short idle", calls, [(SUPER, {"enable_thinking": False}, r.IDLE_VISION)])
calls = see(["TimeoutError", True])
check("vision: a hung first model falls through to the omni model, thinking off", calls,
      [(SUPER, {"enable_thinking": False}, r.IDLE_VISION), (OMNI, {"enable_thinking": False}, r.IDLE_VISION)])
calls = see(["TimeoutError", "empty answer (length)", "HTTP 404", True])
check("vision: Gemini is the fourth try and gets no chat_template_kwargs", calls[3], (GEM, None, r.IDLE_VISION))
# OpenRouter vision: only ":free" ids, only with the person's OpenRouter key, with the same privacy preferences as chat, thinking off
_orv = [c for c in r.VISION_CLOUD if "openrouter.ai" in c[1] or c[3] == "OPENROUTER_API_KEY"]
check("vision openrouter guard: every OpenRouter vision model id ends with :free", [c[2] for c in _orv if not c[2].endswith(":free")], [])
check("vision openrouter: one entry, on openrouter.ai, keyed by OPENROUTER_API_KEY, after the NVIDIA entries",
      ([c[3] for c in _orv], {c[1] for c in _orv}, [c[3] for c in r.VISION_CLOUD].index("OPENROUTER_API_KEY") > 1),
      (["OPENROUTER_API_KEY"], {r.OPENROUTER_BASE}, True))
r._hung.clear(); r._limited.clear()
_see_h = Pic(["HTTP 404", "HTTP 404", True])
_see_h.vision({"messages": pic, "stream": False, "max_completion_tokens": 300}, r.DIRECT, time.time())
_u, _b = _see_h.bodies[2]
check("vision openrouter: the request goes to openrouter.ai with data_collection deny + zdr and reasoning off",
      (_u.startswith(r.OPENROUTER_BASE), _b.get("provider"), _b.get("reasoning"), "chat_template_kwargs" in _b),
      (True, r.OPENROUTER_PROVIDER, {"enabled": False}, False))
check("vision openrouter: the NVIDIA calls carry no OpenRouter provider field", [("provider" in b) for _, b in _see_h.bodies[:2]], [False, False])
check("vision openrouter: max_completion_tokens becomes max_tokens, like every OpenRouter call",
      (_b.get("max_tokens"), "max_completion_tokens" in _b), (300, False))
_real_key_v = r.key
r.key = lambda var: "" if var == "OPENROUTER_API_KEY" else "k"
check("vision openrouter: without an OpenRouter key the model is never called", [c[0] for c in see(["HTTP 404", "HTTP 404", True]) if c[0] == ORL], [])
r.key = lambda var: "k" if var == "OPENROUTER_API_KEY" else ""
check("vision openrouter: with only an OpenRouter key it is the whole chain", [c[0] for c in see([True])], [ORL])
r.key = _real_key_v
r.note_health("NVIDIA nemotron-3.5-super-vl", "TimeoutError")
h = Pic([True])
h.vision({"messages": pic, "stream": False}, r.DIRECT, time.time())
check("vision: after a hang the next image goes to the other model first", h.calls[0][0], OMNI)
r._hung.clear(); r._limited.clear()

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
# aside for an hour so the provider keeps working on the stack's key
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
check("an own key the provider refused: set aside, and NOT replaced by the stack's key (no cross-person fallback)", r.key("NVIDIA_API_KEY"), "")
check("...the person is told it was refused", (r.key_refused("NVIDIA_API_KEY"), r.key_problem(["NVIDIA_API_KEY"])), (True, "refused"))
r._own_failed[("NVIDIA_API_KEY", "nvapi-own")] = _time.time() - r.KEY_RETRY - 5
check("...and the own key is tried again after the wait", r.key("NVIDIA_API_KEY"), "nvapi-own")
r._own_failed[("NVIDIA_API_KEY", "nvapi-own")] = _time.time()
_json.dump({"credential_pool": {"nvidia": [{"api_key": "nvapi-new"}]}}, open(r.AUTH_JSON, "w"))
check("a newly pasted key is a different value: it works at once", r.key("NVIDIA_API_KEY"), "nvapi-new")
_json.dump({"credential_pool": {"nvidia": [{"api_key": "nvapi-own"}]}}, open(r.AUTH_JSON, "w"))
os.environ["NVIDIA_API_KEY"] = ""
check("a refused own key with nothing else: no key, never the refused one again", r.key("NVIDIA_API_KEY"), "")
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
# A 429 from Token Harbor is the account's allowance: every model there goes last, NVIDIA's do not
r._limited.clear()
r.note_health("Token Harbor mimo-v2.6-flash", "HTTP 429")
by = {c[0]: c for c in r.CANDIDATES}
check("a Token Harbor 429 cools every Token Harbor model, no NVIDIA one",
      (r.cooling(by["Token Harbor deepseek-v4-flash"]), r.cooling(by["Token Harbor deepseek-v4.1-flash"]),
       r.cooling(by["NVIDIA nemotron-3.5-super"])), (True, True, False))
r.note_health("NVIDIA gpt-oss-20b", "HTTP 429")
check("an NVIDIA 429 cools that model only", (r.cooling(by["NVIDIA gpt-oss-20b"]), r.cooling(by["NVIDIA nemotron-3-ultra"])), (True, False))
r._limited.clear()

# A 429 that announces when the free allowance returns is remembered: those models are not tried until
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

# Request threads learn, read and clear the record at once (ThreadingHTTPServer): no exception, the file stays valid JSON,
# and no temporary file is left behind (unlocked clear()+update() and one shared .tmp name).
import threading as _th
_errs = []
def _hammer(i):
    try:
        for _ in range(60):
            r.learn_limit(URL, AUTH, FakeErr(announced(future)))
            r.exhausted(th[i % 3])
            r.exhausted_until("tokenharbor.ai")
            r.note_health("Token Harbor deepseek-v4-flash", True)
    except Exception as e:  # noqa: BLE001 - any exception is the failure we test for
        _errs.append(repr(e))
_ts = [_th.Thread(target=_hammer, args=(i,)) for i in range(8)]
[t.start() for t in _ts]; [t.join() for t in _ts]
_left = [f for f in os.listdir(os.path.dirname(_state)) if f.startswith(os.path.basename(_state) + ".") and f.endswith(".tmp")]
_valid = True
try:
    _json.load(open(_state))
except ValueError:
    _valid = False
check("8 threads learning, reading and clearing at once: no error, valid file, no temp files", (_errs[:1], _valid, _left), ([], True, []))
r.key = _real_key
r._limited.clear(); r._exhausted.clear(); r._exh_mtime[0] = None
os.environ.pop("TOKENHARBOR_API_KEY", None); os.environ.pop("NVIDIA_API_KEY", None)
if _envk is not None:
    os.environ["NVIDIA_API_KEY"] = _envk
# The release notice in the person's language: /idioma's tag wins, then Cyrillic, else Spanish; a missing line falls back to es
_rel = os.path.join(tempfile.gettempdir(), "router-selftest-release.txt")
open(_rel, "w", encoding="utf-8").write("id: r9\nes: AVISO\nru: ОБНОВЛЕНИЕ\nen: UPDATE\n")
r.RELEASE_FILE, r.RELEASE_SEEN = _rel, _rel + ".seen"
if os.path.exists(r.RELEASE_SEEN):
    os.remove(r.RELEASE_SEEN)
check("release: Spanish by default", r.release_pending("hola, cómo va"), ("r9", "AVISO"))
check("release: Cyrillic gets ru", r.release_pending("привет"), ("r9", "ОБНОВЛЕНИЕ"))
check("release: [reply in English] gets en", r.release_pending("[Mon 2026-11-03 10:00:00 -03] [reply in English] hola"), ("r9", "UPDATE"))
check("release: [reply in Russian] wins over Spanish text", r.release_pending("[reply in Russian] hola"), ("r9", "ОБНОВЛЕНИЕ"))
open(_rel, "w", encoding="utf-8").write("id: r10\nes: AVISO\n")
check("release: no en line falls back to es", r.release_pending("[reply in English] hi"), ("r10", "AVISO"))
open(r.RELEASE_SEEN, "w").write("r10")
check("release: an id already seen is not shown", r.release_pending("hola"), None)
# A 4xx other than 429 keeps the provider's reason, with any quoted value that is not a field name hidden
check("error_reason keeps field names", r.error_reason('Invalid JSON payload received. Unknown name "strict" at \'tools[0].function\': Cannot find field.'),
      'Invalid JSON payload received. Unknown name "strict" at \'tools[0].function\': Cannot find field.')
check("error_reason hides quoted text and long numbers", r.error_reason('Bad message 12345678901 "hola mi nombre es Juan" sk-x'),
      "Bad message # … sk-x")
class _E400:
    code = 400
    def read(self, n=-1):
        return b'[{"error": {"code": 400, "message": "Unknown name \\"strict\\": Cannot find field.", "status": "INVALID_ARGUMENT"}}]'
_logged = []
_real_log = r.log
r.log = lambda **kw: _logged.append(kw)
r.note_rejection("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", _E400())
r.log = _real_log
check("note_rejection logs host, code and reason (Gemini's list shape)",
      (_logged[-1]["host"], _logged[-1]["code"], _logged[-1]["why"]) if _logged else None,
      ("generativelanguage.googleapis.com", 400, 'Unknown name "strict": Cannot find field.'))

# --- people use only their own keys (DATA_LAW_AND_KEYS.md B.0) ---
_spec = _ilu.spec_from_file_location("router_keys", os.path.join(os.path.dirname(os.path.abspath(__file__)), "router.py"))
r = _ilu.module_from_spec(_spec); _spec.loader.exec_module(r)
_dir = tempfile.mkdtemp()
r.AUTH_JSON, r.HERMES_ENV = os.path.join(_dir, "auth.json"), os.path.join(_dir, ".env")
_saved_env = {v: os.environ.pop(v, None) for v in ("NVIDIA_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "HF_TOKEN")}
def pool(**p):
    _json.dump({"credential_pool": {k.replace("__", ":"): v for k, v in p.items()}}, open(r.AUTH_JSON, "w"))
# 1. "custom:<provider>" in the pool is the same provider's key
pool(custom__nvidia=[{"api_key": "nvapi-custom"}])
check("pool alias: custom:nvidia counts for NVIDIA", r.key("NVIDIA_API_KEY"), "nvapi-custom")
pool(nvidia=[{"api_key": "nvapi-plain", "priority": 1}], custom__nvidia=[{"api_key": "nvapi-custom", "priority": 0}])
check("pool alias: the best priority wins across nvidia and custom:nvidia", r.key("NVIDIA_API_KEY"), "nvapi-custom")
pool(nvidia=[{"api_key": "nvapi-plain"}], custom__nvidia=[{"api_key": "nvapi-custom"}])
check("pool alias: on a tie the plain id comes first", r.key("NVIDIA_API_KEY"), "nvapi-plain")
pool(custom__gemini=[{"api_key": "AIza-c"}], custom__openrouter=[{"api_key": "sk-or-c"}], custom__huggingface=[{"api_key": "hf_c"}])
check("pool alias: gemini, openrouter and huggingface too", [r.key(v) for v in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "HF_TOKEN")], ["AIza-c", "sk-or-c", "hf_c"])
pool(custom__nvidia=[{"api_key": "elsewhere", "base_url": "https://api.example.com/v1"}])
check("pool alias: a custom entry for another host is not the provider's key", r.key("NVIDIA_API_KEY"), "")
pool(custom__nvidia=[{"api_key": "nvapi-host", "base_url": "https://integrate.api.nvidia.com/v1"}])
check("pool alias: a custom entry for the provider's own host counts", r.key("NVIDIA_API_KEY"), "nvapi-host")
pool(custom__nvidia=[{"api_key": "oauth", "auth_type": "oauth"}])
check("pool alias: an oauth entry is not an API key", r.key("NVIDIA_API_KEY"), "")
pool(custom__openrouter=[{"api_key": "sk-or-mine"}])
check("pool alias: another provider's alias is not used (nvidia has no key)", r.key("NVIDIA_API_KEY"), "")
# 2. OpenRouter candidates exist only where the stack has an OpenRouter key; every request to OpenRouter denies data collection
_or = [c for c in r.CLOUD if c[3] == "OPENROUTER_API_KEY"]
check("openrouter: 1 free candidate in the cloud chain, on openrouter.ai", (len(_or), {c[1] for c in _or}), (1, {"https://openrouter.ai/api/v1"}))
# guard: nothing the router sends may bill a person, so every OpenRouter model id (cloud chain, explore list, skip list) ends with ":free"
_or_all = [c for c in r.CANDIDATES if c[3] == "OPENROUTER_API_KEY" or "openrouter.ai" in c[1]]
check("openrouter guard: every candidate model id ends with :free", [c[2] for c in _or_all if not c[2].endswith(":free")], [])
check("openrouter guard: no paid OpenRouter name is left in the skip list", [n for n in r.EXPLORE_SKIP if n.startswith("OpenRouter")], [])
check("openrouter: every candidate is also an explore candidate", all(c in r.CANDIDATES for c in _or), True)
check("openrouter: the free one can be explored", [c[0] for c in _or if c[2].endswith(":free") and c[0] in r.EXPLORE_SKIP], [])
pool()
check("openrouter: no key, the chain has no usable OpenRouter model", [c[0] for c in r.CLOUD if r.key(c[3])], [])
pool(openrouter=[{"api_key": "sk-or-mine"}])
check("openrouter: with the person's key it is the whole chain", [c[0] for c in r.CLOUD if r.key(c[3])], [c[0] for c in _or])
pool(); open(r.HERMES_ENV, "w").write("OPENROUTER_API_KEY=sk-or-env\n")
check("openrouter: a key in the person's .env counts", r.key("OPENROUTER_API_KEY"), "sk-or-env")
os.remove(r.HERMES_ENV)
_body = {"model": "m", "messages": [], "stream": True, "tools": [{"type": "function"}]}
_pref = r.with_provider_prefs("https://openrouter.ai/api/v1/chat/completions", dict(_body))
check("openrouter: data collection denied, zero retention, tools required", _pref["provider"],
      {"data_collection": "deny", "zdr": True, "require_parameters": True})
check("openrouter: the rest of the request (stream, tools) is untouched", {k: v for k, v in _pref.items() if k != "provider"}, _body)
check("openrouter: the router's setting wins over a provider field Hermes sent", r.with_provider_prefs("https://openrouter.ai/api/v1/chat/completions", dict(_body, provider={"data_collection": "allow"}))["provider"]["data_collection"], "deny")
_hq = r.with_provider_prefs("https://openrouter.ai/api/v1/chat/completions", dict(_body, parallel_tool_calls=True, n=1, seed=3, max_completion_tokens=500, temperature=0.2))
check("openrouter: parameters few private endpoints take are dropped, max_completion_tokens becomes max_tokens",
      {k: v for k, v in _hq.items() if k not in _body and k != "provider"}, {"temperature": 0.2, "max_tokens": 500})
check("other providers keep parallel_tool_calls and max_completion_tokens", r.with_provider_prefs("https://integrate.api.nvidia.com/v1/chat/completions",
      dict(_body, parallel_tool_calls=True, max_completion_tokens=5))["max_completion_tokens"], 5)
check("other providers get no provider field", "provider" in r.with_provider_prefs("https://integrate.api.nvidia.com/v1/chat/completions", dict(_body)), False)
check("the default request set drops a provider field Hermes sent", "provider" in {k: v for k, v in dict(_body, provider={"x": 1}).items() if k in r.PASS_KEYS}, False)
# 3. a refused key is never replaced by another key; OpenRouter's per-model errors do not set the key aside
os.environ["NVIDIA_API_KEY"] = "nvapi-operator-leftover"
pool(nvidia=[{"api_key": "nvapi-person"}])
r._own_failed.clear()
check("refusal: the person's key first", r.key("NVIDIA_API_KEY"), "nvapi-person")
r._own_failed[("NVIDIA_API_KEY", "nvapi-person")] = _time.time()
check("refusal: the operator's leftover in the environment is NOT used instead", r.key("NVIDIA_API_KEY"), "")
check("refusal: not even on the next request", [c[0] for c in r.CLOUD if r.key(c[3])], [])
os.environ.pop("NVIDIA_API_KEY")
r._own_failed.clear()
check("refuses_key: 401, 402 and 403 on a normal provider", [r.refuses_key("NVIDIA_API_KEY", f"HTTP {c}") for c in (401, 402, 403, 404, 429)], [True, True, True, False, False])
check("refuses_key: OpenRouter's 402/403 are about one model or request, only 401 is the key",
      [r.refuses_key("OPENROUTER_API_KEY", f"HTTP {c}") for c in (401, 402, 403)], [True, False, False])
check("refuses_key: a timeout is not a refusal", r.refuses_key("NVIDIA_API_KEY", "TimeoutError"), False)
# keys come only from this stack: the pool, its .env, its environment (nothing else is read)
check("sources: only the pool, the .env and the environment", sorted(set(__import__("re").findall(r"open\(([A-Z_]+)", open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "router.py")).read().split("def own_key")[0].split("# Where a key may come from")[1]))), ["AUTH_JSON", "HERMES_ENV"])
# 4. no key at all: one clear line, in the person's language, pointing at the keys page
def um_(t):
    return [{"role": "user", "content": t}]
for t_, lang_ in [("hola, ¿cómo estás?", "es"), ("привет, как дела", "ru"), ("hello, can you help me with this", "en"),
                  ("[Mon 2026-11-03 10:00:00 -03] [reply in English] hola", "en"), ("[reply in Russian] hola", "ru"), ("ok", "es"),
                  ("a quien le interesa", "es")]:
    check(f"key_lang({t_!r})", r.key_lang(um_(t_)), lang_)
for lang_, t_ in (("es", "hola, ¿cómo estás?"), ("ru", "привет, как дела"), ("en", "hello, can you help me with this")):
    none_ = r.key_line(um_(t_), "none")
    check(f"no key ({lang_}): one line", none_.count("\n"), 0)
    check(f"no key ({lang_}): points at the keys page", "/keys/" in none_, True)
    ref_ = r.key_line(um_(t_), "refused", ["NVIDIA_API_KEY"])
    check(f"refused key ({lang_}): names the provider, one line, keys page", ("NVIDIA" in ref_, ref_.count("\n"), "/keys/" in ref_), (True, 0, True))
check("no key: the line is not a raw error", r.key_line(um_("hola, ¿cómo estás?"), "none").startswith("🔑 Todavía no hay una key tuya"), True)
check("no key is Spanish, Russian and English only in the table", sorted(r.KEY_NOTICE["none"]), ["en", "es", "ru"])
for v_ in ("NVIDIA_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "HF_TOKEN"):
    os.environ.pop(v_, None)
pool()
r._own_failed.clear()
check("key_problem: nothing saved, nothing in the environment", r.key_problem([v for _, _, _, v in r.CLOUD]), "none")
pool(gemini=[{"api_key": "AIza-own"}])
check("key_problem: one usable key is enough", r.key_problem([v for _, _, _, v in r.CLOUD]), None)
r._own_failed[("GEMINI_API_KEY", "AIza-own")] = _time.time()
check("key_problem: the only key was refused", r.key_problem([v for _, _, _, v in r.CLOUD]), "refused")
r._own_failed.clear()
for v_, k_ in _saved_env.items():
    if k_ is not None:
        os.environ[v_] = k_

# 5. reply language on the web chat path (Open WebUI -> Hermes api_server), where Hermes adds no "[reply in X]" note itself
import json as _json


_tick = [0]


def lang_files(prefs=None, stack=None):
    for path_, d_ in ((r.PREFS, prefs), (r.GATEWAYS, stack)):
        if d_ is None:
            if os.path.exists(path_):
                os.remove(path_)
        else:
            with open(path_, "w") as f_:
                _json.dump(d_, f_)
            _tick[0] += 1                              # a distinct mtime per write: same-size rewrites inside one clock tick are not told apart
            os.utime(path_, ns=(10**18 + _tick[0], 10**18 + _tick[0]))


def web(*users, platform="api_server", tools=True):
    """A request as Hermes sends it from the web chat: system prompt, then user/assistant turns."""
    out_ = [{"role": "system", "content": f"You are an assistant.\nPlatform: {platform}"}]
    for i_, u_ in enumerate(users):
        if i_:
            out_.append({"role": "assistant", "content": "ok"})
        out_.append({"role": "user", "content": u_})
    return out_


def users_of(msgs_):
    return [r.text_of(m_) for m_ in msgs_ if m_["role"] == "user"]


lang_files()
check("lang: nothing set -> none", r.person_lang(), None)
lang_files(stack={"lang": "ru"})
check("lang: stack ru, no prefs file", r.person_lang(), "ru")
check("key notice: '/keys/' alone on a ru stack is Russian", r.key_line(um_("/keys/"), "none").startswith("🔑 Вашего ключа"), True)
check("key_lang: Cyrillic on an es stack follows the stack (same as Telegram)", (lang_files(stack={"lang": "es"}), r.key_lang(um_("привет, как дела")))[1], "es")
lang_files(stack={"lang": "ru"})
check("key_lang: the person's explicit tag wins over the stack", r.key_lang(um_("[reply in English] /keys/")), "en")
check("key_lang: the tag wins over a chosen language", (lang_files(prefs={"lang": "es"}, stack={"lang": "ru"}), r.key_lang(um_("hola [reply in Russian]")))[1], "ru")
lang_files(prefs={"lang": "en"}, stack={"lang": "ru"})
check("key_lang: /idioma choice wins over the stack", r.key_lang(um_("/keys/")), "en")
lang_files(prefs={"lang": "auto"}, stack={"lang": "ru"})
check("lang: auto means no choice (not the stack's)", r.person_lang(), None)
check("key_lang: auto -> Cyrillic detection", r.key_lang(um_("привет, как дела")), "ru")
check("key_lang: auto -> English detection", r.key_lang(um_("hello, can you help me with this")), "en")
check("key_lang: auto -> Spanish fallback", r.key_lang(um_("/keys/")), "es")
lang_files(prefs={"voice": "auto"}, stack={"lang": "ru"})
check("lang: a prefs file without lang does not hide the stack's", r.person_lang(), "ru")
lang_files(prefs={"lang": "xx"}, stack={"lang": "ru"})
check("lang: an unknown choice falls back to the stack", r.person_lang(), "ru")
lang_files(stack={"lang": "fr"})
check("lang: an unknown stack language is none", r.person_lang(), None)
lang_files(stack={"lang": "ru"})
check("lang: a change of the file is seen at once (cache by mtime)", (lang_files(stack={"lang": "es"}), r.person_lang())[1], "es")

lang_files(stack={"lang": "ru"})
sent_ = r.with_reply_note(web("hola"))
check("note: appended to the last user message", users_of(sent_), ["hola [reply in Russian]"])
check("note: the system prompt is untouched", sent_[0], web("hola")[0])
orig_ = web("uno", "dos")
sent_ = r.with_reply_note(orig_)
check("note: every person message, same way each time (cache prefix)", users_of(sent_), ["uno [reply in Russian]", "dos [reply in Russian]"])
check("note: the input is not modified", users_of(orig_), ["uno", "dos"])
check("note: never twice", users_of(r.with_reply_note(sent_)), ["uno [reply in Russian]", "dos [reply in Russian]"])
check("note: an explicit tag of the person stays alone", users_of(r.with_reply_note(web("hi [reply in English]"))), ["hi [reply in English]"])
check("note: Telegram's tag after the timestamp counts as present",
      users_of(r.with_reply_note(web("[Mon 2026-11-03 10:00:00 -03] [reply in Russian] hola", platform="telegram"))),
      ["[Mon 2026-11-03 10:00:00 -03] [reply in Russian] hola"])
check("note: stable across a tool loop (last message a tool result)",
      users_of(r.with_reply_note(web("hola") + [{"role": "assistant", "content": None, "tool_calls": []}, {"role": "tool", "content": "x", "tool_call_id": "1"}])),
      ["hola [reply in Russian]"])
check("note: the router's own consent answer still matches the person's words (applied to the outgoing copy only)",
      r.consent_reply([{"role": "assistant", "content": PROMPT}, {"role": "user", "content": "sí"}], 1), True)
parts_ = [{"type": "text", "text": "mirá esto"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
sent_ = r.with_reply_note(web("x")[:1] + [{"role": "user", "content": parts_}])
check("note: list-of-parts content: appended to the last text part, image kept",
      sent_[1]["content"], [{"type": "text", "text": "mirá esto [reply in Russian]"}, parts_[1]])
check("note: the input parts are not modified", parts_[0]["text"], "mirá esto")
sent_ = r.with_reply_note(web("x")[:1] + [{"role": "user", "content": [parts_[1]]}])
check("note: image-only message gets a text part", sent_[1]["content"], [parts_[1], {"type": "text", "text": "[reply in Russian]"}])
check("note: empty message gets nothing", users_of(r.with_reply_note(web(""))), [""])
lang_files(prefs={"lang": "en"}, stack={"lang": "ru"})
check("note: /idioma choice, English", users_of(r.with_reply_note(web("hola"))), ["hola [reply in English]"])
lang_files(prefs={"lang": "auto"}, stack={"lang": "ru"})
check("note: auto adds nothing", users_of(r.with_reply_note(web("hola"))), ["hola"])
lang_files()
check("note: no language set adds nothing", users_of(r.with_reply_note(web("hola"))), ["hola"])
lang_files(stack={"lang": "ru"})
# Hermes's own calls
review_ = web("hola", "gracias") + [{"role": "assistant", "content": "de nada"},
                                    {"role": "user", "content": "Review the conversation above and consider saving to memory if appropriate.\n\nMemory has TWO distinct stores"}]
check("note: memory/skill review prompt is not tagged, the person's earlier messages are (same prefix as the main calls)",
      users_of(r.with_reply_note(review_)), ["hola [reply in Russian]", "gracias [reply in Russian]", users_of(review_)[-1]])
check("note: combined review prompt is not tagged",
      users_of(r.with_reply_note(web("a") + [{"role": "user", "content": "Review the conversation above and update two things:\n\n**Memory**"}]))[-1].endswith("**Memory**"), True)
check("note: compaction summarizer prompt is not tagged",
      users_of(r.with_reply_note(web("You are a summarization agent creating a context checkpoint. Treat the conversation turns below as source")))[0].endswith("as source"), True)
check("note: a compaction summary replayed in the user role is not tagged",
      users_of(r.with_reply_note(web("[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted")))[0].endswith("compacted"), True)
for _frame in ("[Your active task list was preserved across context compression] - a", "[Planning state preserved] b",
               "[ASYNC DELEGATION COMPLETE - d1] c", "Cronjob Response: nightly\nbody"):
    check("note: Hermes control frame is not tagged: " + _frame[:24], users_of(r.with_reply_note(web(_frame)))[0], _frame)
check("note: injected [SYSTEM ...] notes are not tagged", users_of(r.with_reply_note(web("[SYSTEM: a board task] run it")))[0].endswith("run it"), True)
check("note: aux calls (titles, summaries: no tools) get nothing", users_of(r.with_reply_note(web("hola"), aux=True)), ["hola"])
check("note: a delegated subagent gets nothing", users_of(r.with_reply_note(web("do the task", platform="subagent"))), ["do the task"])
check("note: a cron run gets nothing", users_of(r.with_reply_note(web("run the job", platform="cron"))), ["run the job"])
title_ = [{"role": "system", "content": "You name chat sessions. Given the user's opening message, write a title"}, {"role": "user", "content": "hola"}]
check("note: a title call (aux in the handler: no tools) is left alone", r.with_reply_note(title_, aux=True), title_)
lang_files()

# ---- early alert: the router writes categories and counts to a host-readable sink, never the person's words ----
import json as _json, stat as _stat
_sigdir = tempfile.mkdtemp()
r.EARLY_SIGNALS = os.path.join(_sigdir, ".early-signals.jsonl")
r.LAST_REPLY, r.LAST_MODEL_CALL = os.path.join(_sigdir, ".last_reply"), os.path.join(_sigdir, ".last_model_call")


def sig_reset():
    for f in (r.EARLY_SIGNALS, r.EARLY_SIGNALS[:-6] + ".1.jsonl"):
        if os.path.lexists(f):
            os.remove(f)
    r._sig_recent[:] = []
    r._repeats[:] = []


def sig_lines():
    try:
        return [_json.loads(x) for x in open(r.EARLY_SIGNALS).read().splitlines()]
    except OSError:
        return []


def said(t):
    return [{"role": "user", "content": t}]


def cats(t, turn=None, now=None):
    return [(c, k) for c, n, k in r.person_signals(said(t), turn, now)]


sig_reset()
for t, want in [
    ("did you check the link", "check"), ("Did you actually test it?", "check"), ("you never checked it", "check"), ("you didn't verify anything", "check"),
    ("¿chequeaste el link?", "check"), ("lo revisaste?", "check"), ("¿Verificaste que abre?", "check"), ("ты проверил?", "check"), ("Ты это пробовал?", "check"),
    ("вы проверили ссылку", "check"),
    ("we agreed on the other one", "agreed"), ("I already told you", "agreed"), ("habíamos quedado en que lo probabas", "agreed"),
    ("quedamos en eso ayer", "agreed"), ("ya te dije que no", "agreed"), ("мы договорились", "agreed"), ("Я же просил по-другому", "agreed"),
    ("the link doesn't open", "broken"), ("it won't load", "broken"), ("not working", "broken"), ("dead link", "broken"), ("no abre", "broken"),
    ("no funciona el enlace", "broken"), ("sigue sin andar", "broken"), ("link roto", "broken"), ("не открывается", "broken"),
    ("не работает", "broken"), ("ссылка не та", "broken"),
    ("you forgot the attachment", "didnt"), ("no lo hiciste", "didnt"), ("te olvidaste del adjunto", "didnt"), ("ты не сделал", "didnt"), ("ты забыл", "didnt"),
    ("otra vez el mismo error", "again"), ("the same error again", "again"), ("de nuevo mal", "again"), ("опять ошибка", "again"), ("снова не работает?", "broken"),
    # negatives
    ("can you check again tomorrow", None), ("abre el archivo", None), ("проверь ещё раз", None), ("try again tomorrow", None),
    ("please check the link", None), ("otra vez gracias", None), ("de nuevo, buen día", None), ("снова привет", None),
    ("hola, ¿cómo estás?", None), ("did it work?", None), ("we said hello", "agreed"),
]:
    got = cats(t)
    check(f"complaint {t!r}", [k for c, k in got if c == "complaint"] or [None], [want])
check("complaint: a message is at most one complaint line", len([1 for c, k in cats("did you check, we agreed, no abre, otra vez error") if c == "complaint"]), 1)
check("complaint: the first k in table order wins", cats("did you check, we agreed, no abre")[0], ("complaint", "check"))
check("complaint: the Hermes stamp and the reply tag are not part of the text", cats("[Mon 2030-03-04 10:00:00 -03] did you check the link [reply in English]"), [("complaint", "check")])
check("complaint: a pasted document (over 600 chars) is skipped", cats("did you check the link " + "x" * 700), [])
for t, want in [("This site can’t be reached", True), ("ERR_NAME_NOT_RESOLVED", True), ("DNS_PROBE_FINISHED_NXDOMAIN", True),
                ("No se puede acceder a este sitio", True), ("Не удается получить доступ к сайту", True), ("Сайт недоступен", True),
                ("404 Not Found", True), ("Page not found", True), ("Página no encontrada", True), ("Страница не найдена", True),
                ("the page loads fine", False), ("error de sintaxis", False), ("route 404 in my notes", False)]:
    check(f"deadpage {t!r}", any(c == "deadpage" for c, k in cats(t)), want)
check("deadpage: a long developer question that mentions a 404 is not a pasted error page",
      any(c == "deadpage" for c, k in cats("how do I handle a 404 not found in express when the route exists in the router file but the middleware order "
                                          "makes it fall through, and should the handler live before or after the static files, " + "context " * 30)), False)
check("signals: a pasted document (over 2000 chars) is skipped before any normalization", cats("did you check the link " + "x" * 2100), [])

# repeat: the same text (25+ chars) in a second distinct turn within 10 minutes; hashes stay in memory
sig_reset()
T = 1_800_000_000.0
check("repeat: the first time nothing fires", r.person_signals(said("mandame el link del video otra vez"), "t1", T), [])
check("repeat: a retry of the same turn key does not count", r.person_signals(said("mandame el link del video otra vez"), "t1", T + 5), [])
check("repeat: the second distinct turn within 600 s fires with n=1", [x for x in r.person_signals(said("Mandame  el link del VIDEO otra vez"), "t2", T + 60) if x[0] == "repeat"],
      [("repeat", 1, None)])
check("repeat: a third one is again one line with n=1 (the collector's cap limits it, not a running count)",
      [x for x in r.person_signals(said("mandame el link del video otra vez"), "t3", T + 120) if x[0] == "repeat"], [("repeat", 1, None)])
check("repeat: after 600 s it does not", [x for x in r.person_signals(said("mandame el link del video otra vez"), "t4", T + 1000) if x[0] == "repeat"], [])
sig_reset()
r.person_signals(said("hola"), "a1", T)
check("repeat: text under 25 chars never repeats", r.person_signals(said("hola"), "a2", T + 10), [])
sig_reset()
for i, t in enumerate(("hola buen dia", "ok gracias, dale", "sí, dale, hacelo", "sí, dale, hacelo", "sí, dale, hacelo")):
    got = r.person_signals(said(t), f"g{i}", T + i)
check("repeat: three identical short confirmations or greetings never fire", got, [])
check("repeat: what is kept in memory is a hash, not the text", all(len(e[2]) == 40 for e in r._repeats), True)

# the sink: exactly the writers' shape, never words
sig_reset()
SECRET = "mi secreto es el pastel de manzana, did you check el link?"
msgs = [{"role": "user", "content": "[Mon 2030-03-04 10:00:00 -03] " + SECRET}]
r.early_turn(msgs, "k1")
r.early_turn(msgs + [{"role": "assistant", "content": "x"}, {"role": "user", "content": SECRET}], "k2")
raw = open(r.EARLY_SIGNALS, "rb").read()
check("sink: a complaint and a repeat were written", [(x["cat"], x.get("k")) for x in sig_lines()], [("complaint", "check"), ("complaint", "check"), ("repeat", None)])
check("sink: the person's words are nowhere in the bytes", (b"pastel" in raw, b"manzana" in raw, b"secreto" in raw), (False, False, False))
OK_K = __import__("re").compile(r"^[a-z0-9_]{1,16}$")
check("sink: every line passes the schema",
      all(set(x) <= {"ts", "cat", "n", "k", "v", "src"} and x["cat"] in r._SIG_CATS and isinstance(x["ts"], int) and isinstance(x["n"], int) and x["n"] >= 1
          and x["src"] == "router" and ("k" not in x or OK_K.match(x["k"])) and ("v" not in x or isinstance(x["v"], int)) for x in sig_lines()), True)
check("sink: the file is 0644", _stat.S_IMODE(os.stat(r.EARLY_SIGNALS).st_mode), 0o644)
sig_reset()
_um = os.umask(0o077)
try:
    r.signal("deadpage")
    check("sink: 0644 under umask 077 (the host's collector must read it)", _stat.S_IMODE(os.stat(r.EARLY_SIGNALS).st_mode), 0o644)
finally:
    os.umask(_um)
sig_reset()
os.symlink(os.path.join(_sigdir, "victim"), r.EARLY_SIGNALS)
check("sink: a symlink planted at the path is not followed", (r.signal("deadpage"), os.path.exists(os.path.join(_sigdir, "victim"))), (False, False))
sig_reset()
check("sink: only known categories, a short [a-z0-9_] k and int v are written",
      (r.signal("nope"), r.signal("complaint", k="Bad K!"), r.signal("complaint", k="check", v="x", extra="text"), r.signal("scan_zero")), (False, True, True, False))
check("sink: the dropped fields are not in the line", [(x["cat"], x.get("k"), x.get("v"), set(x)) for x in sig_lines()][1],
      ("complaint", "check", None, {"ts", "cat", "n", "k", "src"}))
check("sink: n is clamped to 1..20", (r.signal("repeat", n=99), r.signal("repeat", n=0), [x["n"] for x in sig_lines()][-2:]), (True, True, [20, 1]))
sig_reset()
r._sig_recent[:] = []
wrote = sum(1 for _ in range(100) if r.signal("complaint", k="check"))
check("sink: a looping bug is capped at 40 lines a minute", (wrote, len(sig_lines())), (40, 40))
sig_reset()
open(r.EARLY_SIGNALS, "w").write("x" * 200_001)
r.signal("deadpage")
check("sink: past 200 KB it rotates to .early-signals.1.jsonl", (os.path.getsize(r.EARLY_SIGNALS[:-6] + ".1.jsonl"), len(sig_lines())), (200_001, 1))
r.EARLY_SIGNALS = "/nonexistent-dir/.early-signals.jsonl"
check("sink: an unwritable workdir never raises", r.signal("deadpage"), False)
r.EARLY_SIGNALS = os.path.join(_sigdir, ".early-signals.jsonl")

# touch_epoch: per-path throttle, 0644, no symlink written through
r._epoch_at.clear()
check("touch_epoch: writes the epoch", r.touch_epoch(r.LAST_MODEL_CALL, now=1_800_000_000.0) and open(r.LAST_MODEL_CALL).read().strip() == "1800000000", True)
check("touch_epoch: throttled per path (5 s)", (r.touch_epoch(r.LAST_MODEL_CALL, now=1_800_000_002.0), r.touch_epoch(r.LAST_REPLY, now=1_800_000_002.0)), (False, True))
check("touch_epoch: rewritten after the throttle", r.touch_epoch(r.LAST_MODEL_CALL, now=1_800_000_010.0) and open(r.LAST_MODEL_CALL).read().strip() == "1800000010", True)
check("touch_epoch: every=0 is never throttled", (r.touch_epoch(r.LAST_REPLY, every=0, now=1_800_000_002.0), r.touch_epoch(r.LAST_REPLY, every=0, now=1_800_000_002.0)), (True, True))
os.umask(0o077)
try:
    r._epoch_at.clear()
    r.touch_epoch(r.LAST_REPLY, now=1_800_000_030.0)
    check("touch_epoch: 0644 under umask 077", _stat.S_IMODE(os.stat(r.LAST_REPLY).st_mode), 0o644)
finally:
    os.umask(_um)
r._epoch_at.clear()
_tmp = f"{r.LAST_REPLY}.{os.getpid()}.tmp"
os.symlink(os.path.join(_sigdir, "victim2"), _tmp)
check("touch_epoch: a symlink planted at the temp name is replaced, never written through",
      (r.touch_epoch(r.LAST_REPLY, now=1_800_000_040.0), os.path.exists(os.path.join(_sigdir, "victim2"))), (True, False))
check("touch_epoch: an unwritable workdir never raises", r.touch_epoch("/nonexistent-dir/.x", now=1_800_000_100.0), False)

# evaluate(): .last_reply, bad_end and wrong_lang from one answered call; the reply text is only counted in memory
def meter_with(text, finish="stop", tools=0):
    m = r.Meter()
    m.choice({"message": {"content": text, **({"tool_calls": [{"function": {"name": "f", "arguments": "{}"}}]} if tools else {})}, "finish_reason": finish}, False)
    return m


def ev(text, finish="stop", tools=0, msgs=None, aux=False, ok=True):
    sig_reset()
    r._epoch_at.clear()
    if os.path.exists(r.LAST_REPLY):
        os.remove(r.LAST_REPLY)
    r.evaluate(meter_with(text, finish, tools), "m", ok, 0, "mode", "sess", "turn", aux, msgs)
    return [(x["cat"], x.get("k")) for x in sig_lines()], os.path.exists(r.LAST_REPLY)


lang_files()
RU = "Привет! Я проверил все ссылки и обновил список, всё работает, как договорились. " * 4
EN = "Here is the summary of what we did together and the things that you can do with this: the link is the one that you asked for. " * 3
ES = "Acá tenés el resumen de lo que hicimos con los links para que puedas usar la lista que me pediste y el archivo de la semana. " * 3
check("evaluate: a plain answer writes .last_reply and no signal", ev(ES, msgs=web("hola")), ([], True))
check("evaluate: a tool-call turn is not a reply", ev("", "tool_calls", 1, msgs=web("hola")), ([], False))
check("evaluate: cut by the length limit is bad_end length (and a reply)", ev("texto cortado", "length", msgs=web("hola")), ([("bad_end", "length")], True))
check("evaluate: stop with nothing at all is bad_end empty", ev("", "stop", msgs=web("hola")), ([("bad_end", "empty")], True))
check("evaluate: aux calls leave no trace", ev("", "length", aux=True), ([], False))
check("evaluate: a failed call leaves no trace", ev("x", ok="HTTP 500"), ([], False))
check("evaluate: a Russian reply to a Spanish speaker is wrong_lang", ev(RU, msgs=web("hola, ¿me ayudás?"))[0], [("wrong_lang", None)])
check("evaluate: a Spanish reply to a Russian speaker is wrong_lang", ev(ES, msgs=web("привет, помоги мне"))[0], [("wrong_lang", None)])
check("evaluate: an English reply to a Spanish speaker is wrong_lang", ev(EN, msgs=web("hola, ¿me ayudás con esto?"))[0], [("wrong_lang", None)])
check("evaluate: a Spanish reply to an English speaker is wrong_lang", ev(ES, msgs=web("hello, can you help me with this? thanks the list"))[0], [("wrong_lang", None)])
check("evaluate: the right language is quiet", (ev(RU, msgs=web("привет, помоги мне"))[0], ev(ES, msgs=web("hola, ¿me ayudás?"))[0], ev(EN, msgs=web("hello, can you help me with this? thanks"))[0]), ([], [], []))
check("evaluate: a short reply (under 120 letters) is never judged", ev("Привет, готово.", msgs=web("hola"))[0], [])
check("evaluate: a Russian reply to a Spanish speaker who chose Russian with /idioma is fine", (lang_files(prefs={"lang": "ru"}), ev(RU, msgs=web("hola"))[0])[1], [])
lang_files()
ev(RU, msgs=web("hola, ¿me ayudás?"))
check("evaluate: the reply's words never reach the sink", "ссылки".encode() in open(r.EARLY_SIGNALS, "rb").read(), False)

# the local route: do_POST -> forward() never reaches evaluate(), so it must write .last_reply itself or every locally answered message
# would read as "unanswered" to the collector
import io as _io


class LocalPost(r.Handler):
    """do_POST on a stack with a home model: forward() is replaced by a fake that fills the meter like a finished local call."""
    def __init__(self, finish, tools=0):
        self.finish, self.tools, self.path = finish, tools, "/v1/chat/completions"
        self.headers = {"Content-Length": "0"}
        self.rfile = None

    def forward(self, url, body, headers, notice, turn=None, idle=0, need_text=False):
        self.meter = meter_with("ok", self.finish, self.tools)
        return True

    def reply(self, *a, **kw):
        return True


def local_turn(finish="stop", tools=0, aux=False):
    sig_reset()
    r._epoch_at.clear()
    if os.path.exists(r.LAST_REPLY):
        os.remove(r.LAST_REPLY)
    body = {"messages": [{"role": "user", "content": "hola, ¿me ayudás con esto?"}],
            **({} if aux else {"tools": [{"type": "function", "function": {"name": "f"}}]})}
    h = LocalPost(finish, tools)
    h.rfile = _io.BytesIO(_json.dumps(body).encode())
    h.headers = {"Content-Length": str(len(h.rfile.getvalue()))}
    h.do_POST()
    return os.path.exists(r.LAST_REPLY)


_saved = (r.cloud_direct, r.decide, r.local_host, r.idle_gap_hours)
r.cloud_direct, r.local_host = (lambda: False), (lambda: ("http://127.0.0.1:1", "m"))
r.decide, r.idle_gap_hours = (lambda msgs: ("local", "local", "kk", True)), (lambda msgs: None)
try:
    check("local route: a locally answered turn writes .last_reply", local_turn("stop"), True)
    check("local route: a call that ended with a tool call is not a reply (the loop is still working)", local_turn("tool_calls", 1), False)
    check("local route: Hermes's own auxiliary calls are not a reply", local_turn("stop", aux=True), False)
finally:
    r.cloud_direct, r.decide, r.local_host, r.idle_gap_hours = _saved

_bench = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops", "bench_models.py")
if os.path.exists(_bench):                                  # not in the image
    check("bench_models.py --or-private sends the same provider preferences as the router",
          'EXTRA["provider"] = ' + repr(r.OPENROUTER_PROVIDER).replace("'", '"') in open(_bench).read(), True)
# ---- the home model behind a GPU gate: leases around each call, a stopped model is started through the gate ----
import importlib.util as _ilu, json as _json, threading as _th
from http.server import BaseHTTPRequestHandler as _BH, ThreadingHTTPServer as _TS
_spec = _ilu.spec_from_file_location("router_gate", os.path.join(os.path.dirname(os.path.abspath(__file__)), "router.py"))
rg = _ilu.module_from_spec(_spec); _spec.loader.exec_module(rg)     # a fresh copy: the cases above replaced local_host and up
_gstate = {"llm_up": False, "calls": [], "mode": "ok"}
class _Gate(_BH):
    def log_message(self, *a): pass
    def do_POST(self):
        body = _json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        _gstate["calls"].append((self.path, self.headers.get("Authorization"), body))
        if _gstate["mode"] == "refuse" or (_gstate["mode"] == "refuse_then_ok" and self.path == "/wake" and _gstate.get("refused", 0) == 0):
            if _gstate["mode"] == "refuse_then_ok":
                _gstate["refused"] = 1
            out, code = {"why": "bench"}, 409
        elif self.path == "/wake":
            code = 200 if _gstate["llm_up"] else 202
            out = {"lease": "L1", "running": _gstate["llm_up"]}
            _gstate["llm_up"] = True              # the gate starts it
        else:
            out, code = {"done": 1}, 200
        data = _json.dumps(out).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
class _Llm(_BH):
    def log_message(self, *a): pass
    def do_GET(self):
        code = 200 if _gstate["llm_up"] and self.path == "/health" else 503
        self.send_response(code); self.send_header("Content-Length", "0"); self.end_headers()
_gs, _ls = _TS(("127.0.0.1", 0), _Gate), _TS(("127.0.0.1", 0), _Llm)
for _srv in (_gs, _ls):
    _th.Thread(target=_srv.serve_forever, daemon=True).start()
_llm_url = f"http://127.0.0.1:{_ls.server_address[1]}"
_gw = os.path.join(_lang_dir, "gateways-gate.json")
_json.dump({"stack": "novedades", "llm": [{"name": "pve4", "url": _llm_url, "model": "qwen3.5-4b"}],
            "gates": {"pve4": {"url": f"http://127.0.0.1:{_gs.server_address[1]}", "token": "tok"}}}, open(_gw, "w"))
rg.GATEWAYS = _gw
check("gate_for: the llm host's gate and the stack's name", rg.gate_for(_llm_url), ({"url": f"http://127.0.0.1:{_gs.server_address[1]}", "token": "tok"}, "novedades"))
check("gate_for: a URL that is not an llm host has no gate", rg.gate_for("http://127.0.0.1:1"), (None, None))
check("local_host: the model is stopped behind its gate: started through the gate, then used",
      rg.local_host(), (_llm_url, "qwen3.5-4b"))
check("local_host: it asked /wake with the port and the stack, then gave the lease back with /done",
      [(c[0], c[1], c[2]) for c in _gstate["calls"]],
      [("/wake", "Bearer tok", {"port": _ls.server_address[1], "stack": "novedades"}), ("/done", "Bearer tok", {"lease": "L1", "wakes": 1})])
_gstate["calls"].clear()
_h = rg.gate_hold(_llm_url)
check("gate_hold on a running model: one /wake, a lease kept for the call", (_h[1] if _h else None, [c[0] for c in _gstate["calls"]]), ("L1", ["/wake"]))
rg.gate_release(_h)
check("gate_release: one /done for that lease", [c[0] for c in _gstate["calls"]], ["/wake", "/done"])
rg.GATE_BUSY_WAIT_S = 0.1; _real_sleep = rg.time.sleep; rg.time.sleep = lambda s: None
_gstate.update(mode="refuse", calls=[])
check("gate refused (409) past GATE_BUSY_WAIT_S: no lease, the call goes on as before", rg.gate_hold(_llm_url), None)
_n = len(_gstate["calls"])
check("a refusal is asked again while GATE_BUSY_WAIT_S lasts", _n >= 2, True)
check("after the wait the gate is not asked again for GATE_RETRY_S", (rg.gate_hold(_llm_url), len(_gstate["calls"])), (None, _n))
rg._gate_failed.clear(); _gstate.update(mode="refuse_then_ok", calls=[], refused=0)
rg.GATE_BUSY_WAIT_S = 30
_h2 = rg.gate_hold(_llm_url)
check("a refusal that clears within the wait (a bench ends): the lease is taken", (_h2[1] if _h2 else None, [c[0] for c in _gstate["calls"]]), ("L1", ["/wake", "/wake"]))
rg.gate_release(_h2); rg.time.sleep = _real_sleep
rg.GATEWAYS = os.path.join(_lang_dir, "missing.json")
check("no gateways file: no gate, nothing asked", rg.gate_hold(_llm_url), None)
_gs.shutdown(); _ls.shutdown()

print("\n".join(fails) or "router_selftest: all ok")
sys.exit(1 if fails else 0)
