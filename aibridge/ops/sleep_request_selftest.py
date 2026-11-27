#!/usr/bin/env python3
"""Offline test of the on-demand sleep decision in ops/wake/waker.py (no docker, no server): python3 ops/sleep_request_selftest.py"""
import importlib.util, json, os, sys, tempfile
spec = importlib.util.spec_from_file_location("waker", os.path.join(os.path.dirname(os.path.abspath(__file__)), "wake", "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
ok = True
def chk(got, want, what):
    global ok; ok &= got == want; print(("ok   " if got == want else f"FAIL (got {got!r}, want {want!r}) ") + what)

N = 10_000.0
d = w.sleep_decision
chk(d(None, N, False, False), "none", "no request: nothing to do")
chk(d({"x": 1}, N, False, False), "none", "garbage in the file is not a request")
chk(d({"ts": N - 5, "mode": "ahora"}, N, True, False), "wait", "ahora: the turn that asked is still answering -> wait")
chk(d({"ts": N - 5, "mode": "ahora"}, N, False, False), "sleep", "ahora: turn over, nothing busy -> sleep")
chk(d({"ts": N - 5, "mode": "ahora", "force": True}, N, False, True), "sleep", "ahora forced: busy work does not stop it")
chk(d({"ts": N - 5, "mode": "ahora", "force": False}, N, False, True), "wait", "ahora not forced: work that started after the check -> wait")
chk(d({"ts": N - 300, "mode": "ahora", "force": False}, N, False, True), "drop", "ahora not forced: still busy after the grace -> drop, never cut unasked")
chk(d({"ts": N - 300, "mode": "ahora"}, N, True, False), "sleep", "ahora: a turn stuck for more than the grace does not hold the stop")
chk(d({"ts": N - 5, "mode": "cuando-termine"}, N, False, True), "wait", "cuando-termine: busy -> wait")
chk(d({"ts": N - 5, "mode": "cuando-termine"}, N, True, False), "wait", "cuando-termine: turn running -> wait")
chk(d({"ts": N - 5, "mode": "cuando-termine"}, N, False, False), "sleep", "cuando-termine: idle -> sleep at once (not after 10 minutes)")
chk(d({"ts": N - 2000, "mode": "cuando-termine"}, N, False, False), "drop", "a request older than 15 minutes is stale")
chk(d({"ts": N + 500, "mode": "ahora"}, N, False, False), "drop", "a request dated in the future is not trusted")
chk("subs-fetch" in w.Stack.DETACHED_SCRIPT and "yt-dlp" in w.Stack.DETACHED_SCRIPT, True, "detached-job scan knows subs-fetch and yt-dlp")

# ---- a stuck gateway counter must not keep the stack awake or veto "dormir" ----
P = w.gateway_count_is_phantom
chk(P(0, None, 5000), False, "phantom: counter at 0 is not a phantom")
chk(P(1, 30, 5000), False, "phantom: a turn started 30 s ago is real work")
chk(P(1, 600, 5000), False, "phantom: a turn 10 minutes ago may still be running")
chk(P(1, 1500, 5000), True, "phantom: counter above 0, no turn for 25 minutes, container old -> stuck")
chk(P(1, None, 5000), True, "phantom: no turn line at all in the log -> stuck")
chk(P(1, None, 400), False, "phantom: a container up for 7 minutes is still starting, keep the counter")

def stack(active, turn_age, uptime, **extra):
    s = object.__new__(w.Stack)
    s.name, s.booting, s.stopping, s.cron_hold_until, s.brain_api_port = "t", False, False, 0.0, "8642"
    s.brain_up = lambda: True
    s.container_started = lambda: w.time.time() - uptime
    s.gateway_state = lambda: {"active_agents": active}
    s.newest_turn_age = lambda: turn_age
    s.marker_fresh = lambda: extra.get("marker", False)
    s.background_processes = lambda: extra.get("bg", 0)
    s.detached_jobs = lambda: extra.get("detached", 0)
    s.pending_jobs = lambda: extra.get("jobs", 0)
    return s
chk(stack(1, 1500, 5000).busy_reasons(), [], "busy: a stuck counter alone does not make the stack busy")
chk(stack(1, 1500, 5000).busy(), False, "busy(): same, as a bool (this is what the idle sleep reads)")
chk(stack(1, 600, 5000).busy_reasons(), ["un turno del agente"], "busy: a counter backed by a turn from 10 minutes ago still counts")
chk(stack(1, 600, 5000).busy_reasons(ignore_gateway=True), [], "busy: a person's explicit sleep request ignores the counter (the turn that asked has its grace)")
chk(stack(1, 1500, 5000, detached=3).busy_reasons(), ["descargas o renders en marcha"], "busy: real downloads still keep it awake with the counter stuck")
chk(stack(1, 1500, 5000, detached=3).busy_reasons(ignore_gateway=True), ["descargas o renders en marcha"], "busy: and still veto an UNFORCED request")
chk(stack(0, 40, 5000).busy_reasons(), ["un turno reciente"], "busy: a turn that started 40 s ago counts")
chk(stack(0, 900, 5000, jobs=1, bg=1).busy_reasons(), ["procesos en segundo plano", "trabajos registrados"], "busy: reasons are named, several at once")

# ---- the last message of an on-request sleep is written by the host, after the stop ----
N1 = w.sleep_notice
chk(N1(True, "es"), "💤 Soñando", "notice: stopped, Spanish: one word, no hour and no 'write me' line (the chat list shows the date)")
chk(N1(True, "ru"), "💤 Вижу сны", "notice: stopped, Russian only")
chk(N1(True, ""), N1(True, "es"), "notice: no language -> Spanish only, never two languages in one message")
chk(N1(True, "en"), "💤 Dreaming", "notice: English only")
chk(w.notice_lang("ru", "es"), "ru", "language: the person's own /idioma wins over the stack's")
chk(w.notice_lang("", "ru"), "ru", "language: the stack's lang when the person has none")
chk(w.notice_lang("auto", ""), "es", "language: 'auto' or nothing -> Spanish")
chk("sigue arriba" in N1(False, "es") and "💤" not in N1(False, "es"), True, "notice: a stop that did not happen never says it sleeps")
chk(N1(True, "xx").count("💤"), 1, "notice: an unknown language does not crash and stays in one language")
chk(N1(False, "").count("\n"), 0, "notice: the failure message is one language too")

def sleeper(brain_stays_up):
    """A Stack whose tick() reaches the on-request branch with a request 'ahora'; records what happened and in which order."""
    s = stack(0, 900, 5000)
    s.events, s.said = [], []
    s.refresh_telegram = lambda: None
    s.ticks, s.lang = 0, "es"
    s.web_up = lambda: False
    s.sleep_request = lambda: {"ts": w.time.time() - 5, "mode": "ahora", "force": True}
    s.clear_sleep_request = lambda: s.events.append("clear")
    s.sleep_brain = lambda: s.events.append("stop")
    state = {"up": True}
    s.brain_up = lambda: state["up"] if not brain_stays_up else True
    def stop():
        s.events.append("stop"); state["up"] = False
    s.sleep_brain = stop
    s.tell_person = lambda t: s.events.append("tell:" + t.split()[0])
    s.announce_sleep = lambda lang=None, why=None, cause=None: s.events.append("zzz")
    s.confirm_handled = lambda ts: s.events.append("confirm")
    s.last_activity, s.cron_only, s.idle_web, s.idle_brain = w.time.time(), False, 600, 600
    s.web_started = s.brain_started = 0
    return s
w.NO_SLEEP = "/nonexistent-no-sleep-file"
w.ops = lambda *a, **k: None
a = sleeper(False); a.tick()
chk(a.events, ["clear", "stop", "confirm", "zzz"], "tick: after the stop Telegram is told the command was handled, then the 💤 message; never before the stop")
b = sleeper(True); b.tick()
chk(b.events, ["clear", "stop", "tell:No"], "tick: if the container is still up after the stop, the person is told it did not sleep")
class F:                      # only what say() and tell_person() read
    name, tg_on, tg_allowed = "t", True, {"1", "2"}
    say, tell_person = w.Stack.say, w.Stack.tell_person
f = F()
f.tg = lambda m, p, timeout=0: {"ok": True}
chk(f.tell_person("x"), 2, "tell_person: counts every person Telegram accepted")
f.tg = lambda m, p, timeout=0: {"ok": False, "error_code": 400, "description": "chat not found"}
chk(f.tell_person("x"), 0, "tell_person: a 200 with ok=false is not 'sent'")
def boom(m, p, timeout=0): raise OSError("down")
f.tg = boom
chk(f.tell_person("x"), 0, "tell_person: an exception is not 'sent'")
f.tg, f.tg_on = (lambda m, p, timeout=0: {"ok": True}), False
chk(f.tell_person("x"), 0, "tell_person: Telegram off tells nobody")
# ---- sleep notes: one silent note per chat, with how long a wake takes; frozen on a host suspend; gone on the next wake ----
chk((w.eta_text(24.6), w.eta_text(89), w.eta_text(150)), ("25 s", "89 s", "2 min"), "eta: seconds under 90 s, else minutes")
chk((N1(True, "es", 25), w.frozen_notice("es", 8), w.frozen_notice("ru", 8), w.frozen_notice("en", 8)),
    ("💤 Soñando · 25 s", "🧊 Congelado · 8 s", "🧊 Заморожен · 8 s", "🧊 Frozen · 8 s"), "notes: word + wake time, one language")
class Z:
    name, lang, tg_on, tg_allowed = "t", "", True, {"1", "2"}
    for _m in ("say", "announce_sleep", "clear_sleep_notes", "notes_lock", "tg_retry", "post_notes", "drop_notes", "edit_notes", "person_level", "prefs_unreadable", "quiet",
               "host_freezing", "host_resumed"):
        locals()[_m] = getattr(w.Stack, _m)
    def __init__(self): self.state, self.calls, self.up, self.next_id, self.workdir = {}, [], False, 100, tempfile.mkdtemp()
    def level(self, v): json.dump({"verbosity": v}, open(os.path.join(self.workdir, ".prefs.json"), "w"))
    def load_state(self): return dict(self.state)
    def save_state(self, **kw): self.state.update(kw)
    def brain_up(self): return self.up
    def boot_estimate(self): return 25
    def tg(self, m, p, timeout=0):
        self.calls.append((m, dict(p)))
        if m == "sendMessage":
            self.next_id += 1
            return {"ok": True, "result": {"message_id": self.next_id}}
        return {"ok": True, "result": True}
def ids(z): return w.notes_ids(z.state.get("sleep_notes"))
z = Z()
chk(z.announce_sleep(), 2, "zzz: every allowed person gets it")
sends = [p for m, p in z.calls if m == "sendMessage"]
chk(all(p.get("disable_notification") is True and p["text"] == "💤 Soñando · 25 s" for p in sends), True, "zzz: silent, word + the stack's boot time")
chk((ids(z), z.state["sleep_notes"]["kind"]), ({"1": 101, "2": 102}, "zzz"), "zzz: the message ids are kept for the next wake")
z.calls = []; z.announce_sleep()
chk([m for m, _ in z.calls], ["deleteMessage", "deleteMessage", "sendMessage", "sendMessage"], "zzz: a second sleep without a wake deletes the old note first: one per chat")
z.calls = []; z.host_freezing(8)
chk([(m, p.get("text")) for m, p in z.calls], [("editMessageText", "💤 Soñando · 33 s")] * 2, "freeze: a 💤 is EDITED to boot + resume, no new message")
z.calls = []; z.host_resumed()
chk([(m, p.get("text")) for m, p in z.calls], [("editMessageText", "💤 Soñando · 25 s")] * 2, "resume: the 💤 gets its plain boot time back")
z.calls = []; z.clear_sleep_notes()
chk((sorted((p["chat_id"], p["message_id"]) for m, p in z.calls if m == "deleteMessage"), ids(z)), ([("1", 103), ("2", 104)], {}), "zzz: the wake deletes them and forgets the ids")
z.calls = []; z.clear_sleep_notes()
chk(z.calls, [], "zzz: nothing to delete, no call")
z.up = True; z.calls = []
chk((z.announce_sleep(), z.calls), (0, []), "zzz: never while the brain is still up")
z.host_freezing(8)
sends = [p for m, p in z.calls if m == "sendMessage"]
chk((len(sends), sends[0]["text"], sends[0].get("disable_notification"), z.state["sleep_notes"]["kind"]), (2, "🧊 Congelado · 8 s", True, "ice"),
    "freeze: an awake (always) brain gets 🧊 with the resume time, silently")
z.calls = []; z.host_resumed()
chk(([m for m, _ in z.calls], ids(z)), (["deleteMessage", "deleteMessage"], {}), "resume: the 🧊 is deleted")
# what woke the stack, when it was not the person (2026-11-27)
chk((N1(True, "es", 25, {"reason": "cron", "names": ["Resumen"]}), N1(True, "ru", 25, {"reason": "update"}),
     N1(True, "en", 25, {"reason": "refresh"}), N1(True, "es", 25, {"reason": "telegram"}), N1(True, "es", 25, None)),
    ("💤 Soñando · 25 s · desperté por tarea programada «Resumen»", "💤 Вижу сны · 25 s · просыпался: обновление",
     "💤 Dreaming · 25 s · woke for daily refresh", "💤 Soñando · 25 s", "💤 Soñando · 25 s"), "why: a background reason is named, a person's is not")
chk(w.why_text({"reason": "cron", "names": ["a", "b", "c", "?"]}, "es"), " · desperté por tarea programada «a, b +1»", "why: two names at most")
z.up = False; z.calls = []; z.wake_why = None
z.announce_sleep(); z.calls = []
z.wake_why = {"reason": "cron", "names": ["Resumen"]}       # a scheduled job woke it, nobody came: the 💤 already there stays
chk((z.announce_sleep(), z.calls, len(ids(z)), getattr(z, "wake_why", "x")), (0, [], 2, None), "background wake: the chat does not move")
z.wake_why = {"reason": "task", "names": []}
z.clear_sleep_notes(); z.calls = []
chk((z.announce_sleep(), [p["text"] for m, p in z.calls if m == "sendMessage"]), (2, ["💤 Soñando · 25 s"] * 2),
    "background wake with no 💤 left: a plain one is posted (reasons are the operator's: detailed only)")
z.calls = []; z.announce_sleep(why={"reason": "update"}, cause="update")
chk([p["text"] for m, p in z.calls if m == "sendMessage"], ["💤 Soñando · 25 s"] * 2, "an update is never named at the normal level")
z.calls = []; z.host_freezing(8)
chk([p.get("text") for m, p in z.calls], ["💤 Soñando · 33 s"] * 2, "freeze edit at normal: plain")
chk((w.nap_text("es", 25), w.nap_text("ru", 25), w.nap_text("en", 120), w.nap_text("xx", 25)),
    ("😴 Me eché una siesta. Ya me levanto: vuelvo en unos 25 s. Tu mensaje quedó guardado.",
     "😴 Я немного вздремнул. Уже встаю: вернусь примерно через 25 s. Ваше сообщение сохранено.",
     "😴 I took a nap. Getting up now: back in about 2 min. Your message is saved.",
     "😴 Me eché una siesta. Ya me levanto: vuelvo en unos 25 s. Tu mensaje quedó guardado."), "nap: the answer to a message that found it asleep")
# verbosity (NOTICES.md): critical hears nothing about sleeping, detailed hears every reason
z.level("critical"); z.calls = []
chk((z.announce_sleep(cause="idle"), [m for m, _ in z.calls], ids(z)), (0, ["deleteMessage", "deleteMessage"], {}),
    "critical: no 💤, and the one left from before is removed")
z.calls = []; z.host_freezing(8)
chk(z.calls, [], "critical: no 🧊 either")
z.level("detailed"); z.calls = []; z.last_wake = {"reason": "telegram", "names": []}
z.announce_sleep(cause="idle")
chk([p["text"] for m, p in z.calls if m == "sendMessage"], ["💤 Soñando · 25 s · desperté por tu mensaje · me dormí por inactividad"] * 2,
    "detailed: the person's own wake and the cause are named")
z.calls = []; z.wake_why = z.last_wake = {"reason": "cron", "names": ["subs-nuevos"]}
z.announce_sleep(cause="ram")
chk([p["text"] for m, p in z.calls if m == "sendMessage"], ["💤 Soñando · 25 s · desperté por tarea programada «subs-nuevos» · me dormí por memoria para otro"] * 2,
    "detailed: a background wake still posts its own 💤, with both reasons")
z.level("normal")
z.up, z.tg_on = False, False; z.calls = []
chk((z.announce_sleep(), z.host_freezing(8), z.calls), (0, None, []), "Telegram off sends nothing")
z.tg_on = True
z.tg = lambda m, p, timeout=0: {"ok": True}   # an old Bot API answer without result: sent, but nothing to delete later
chk((z.announce_sleep(), ids(z)), (2, {}), "zzz: sent without a message id counts, nothing kept")
n = {"c": 0}
def flaky(m, p, timeout=0):
    n["c"] += 1
    if n["c"] < 3: raise OSError("network not back yet")
    return {"ok": True}
z.tg = flaky
chk((z.tg_retry("deleteMessage", {}, tries=5, wait=0), n["c"]), (True, 3), "retry: right after a resume the call is retried until the network is back")
def gone(m, p, timeout=0):
    n["c"] += 1
    raise w.urllib.error.HTTPError("u", 400, "Bad Request: message to delete not found", {}, None)
n["c"] = 0; z.tg = gone
chk((z.tg_retry("deleteMessage", {}, tries=5, wait=0), n["c"]), (False, 1), "retry: a 400 (already gone) is final, not retried")
z.state["sleep_notes"] = {"kind": "ice", "ids": {"1": 5}}
z.drop_notes()
chk(ids(z), {}, "drop: the ids are forgotten even when the delete fails")

# ---- suspend_watch_loop: the hook's token is answered after every stack put up its notes; a cancelled suspend puts them back ----
import tempfile, threading as _th
_d = tempfile.mkdtemp()
class FS:
    def __init__(self, slow=0): self.froze, self.resumed, self.slow = [], 0, slow
    def host_freezing(self, r): w.time.sleep(self.slow); self.froze.append(r)
    def host_resumed(self): self.resumed += 1
_saved = (w.STATE_DIR, dict(w.STACKS), w.CFG, w.boot_gap, w.SUSPEND_NOTE_BUDGET_S)
w.STATE_DIR, w.CFG, w.SUSPEND_NOTE_BUDGET_S = _d, {"host_resume_s": 9}, 1
_clock = {"gap": 0.0}
w.boot_gap = lambda: _clock["gap"]
w.STACKS.clear(); w.STACKS.update({"a": FS(), "b": FS(slow=3)})
_th.Thread(target=w.suspend_watch_loop, daemon=True).start()
open(os.path.join(_d, w.SUSPEND_REQ), "w").write("tok1\n")
t0 = w.time.time()
while w.time.time() - t0 < 5 and not os.path.exists(os.path.join(_d, w.SUSPEND_ACK)): w.time.sleep(0.1)
took = w.time.time() - t0
chk((open(os.path.join(_d, w.SUSPEND_ACK)).read(), w.STACKS["a"].froze, took < 2.5), ("tok1", [9.0], True),
    "suspend hook: answered with the same token, notes put up with host_resume_s, a slow stack does not hold the suspend past the budget")
chk(w.FROZEN["ts"] > 0, True, "suspend hook: the waker remembers notes are up")
_clock["gap"] = 600.0     # the host really slept: the watcher steps aside (the sleeper loop calls host_resumed)
w.time.sleep(1.2)
chk(w.STACKS["a"].resumed, 0, "suspend hook: a real suspend is left to the sleeper loop")
w.STATE_DIR, _st, w.CFG, w.boot_gap, w.SUSPEND_NOTE_BUDGET_S = _saved[0], _saved[1], _saved[2], _saved[3], _saved[4]
w.STACKS.clear(); w.STACKS.update(_st); w.FROZEN["ts"] = 0

# ---- compact_before_sleep: ask Hermes for an idle compaction right before the idle stop, once per idle period ----
class C:
    name, brain = "t", "b"
    compact_req_path, compact_done_path = "/workdir/.compactar.json", "/workdir/.compactar.done.json"
    compact_before_sleep = w.Stack.compact_before_sleep
    def __init__(self, tokens):
        self.compact_tokens, self.compact_req_ts, self.compact_done_for, self.lh, self.files, self.calls = tokens, None, None, 100.0, {}, []
    def last_human(self): return self.lh
class _R:
    def __init__(self, rc, out=""): self.returncode, self.stdout = rc, out
def fake_docker(c):
    def d(*a, timeout=90):
        c.calls.append(a)
        if a[:2] == ("exec", c.brain) and a[2] == "cat":
            return _R(0, c.files[a[3]]) if a[3] in c.files else _R(1)
        if a[:2] == ("exec", c.brain) and a[2:4] == ("rm", "-f"):
            c.files.pop(a[4], None); return _R(0)
        if a[:2] == ("exec", c.brain) and a[2] == "sh":
            body = a[4].split("printf '%s' '", 1)[1].rsplit("' > ", 1)
            c.files[body[1]] = body[0]; return _R(0)
        return _R(0)
    return d
_real_docker = w.docker
try:
    c = C(None); w.docker = fake_docker(c)
    chk((c.compact_before_sleep(), c.calls), (True, []), "compact: off for a stack without idle_compact_tokens: stop at once, no docker call")
    c = C(28000); w.docker = fake_docker(c)
    chk(c.compact_before_sleep(now=1000.0), False, "compact: the first idle stop asks and waits")
    chk(json.loads(c.files["/workdir/.compactar.json"]), {"ts": 1000.0, "min_tokens": 28000}, "compact: the request carries the time and the threshold")
    chk(c.compact_before_sleep(now=1060.0), False, "compact: no answer yet: keep waiting")
    c.files["/workdir/.compactar.done.json"] = json.dumps({"ts": 999.0, "status": "compressed"})
    chk(c.compact_before_sleep(now=1070.0), False, "compact: an answer to an older request does not count")
    c.files["/workdir/.compactar.done.json"] = json.dumps({"ts": 1000.0, "status": "compressed", "tokens": 32107, "seconds": 171.2})
    chk((c.compact_before_sleep(now=1200.0), "/workdir/.compactar.done.json" in c.files), (True, False), "compact: its answer: stop now, answer removed")
    c.calls = []
    chk((c.compact_before_sleep(now=1300.0), c.calls), (True, []), "compact: the same idle period is not asked twice")
    c.lh = 2000.0
    chk(c.compact_before_sleep(now=2500.0), False, "compact: after a new turn of the person, the next idle stop asks again")
    chk(c.compact_before_sleep(now=2500.0 + w.COMPACT_WAIT_S + 1), True, "compact: no answer within COMPACT_WAIT_S: the stop goes ahead")
    chk("/workdir/.compactar.json" in c.files, False, "compact: and the stale request is withdrawn")
    import inspect
    src = inspect.getsource(w.Stack.tick)
    chk("not self.busy() and self.compact_before_sleep()" in src, True, "compact: the idle stop asks it (a sleep on request or the RAM guard do not)")
finally:
    w.docker = _real_docker

# ---- update_kind: a live location must never wake a sleeping stack ----
AL = {"7"}
chk(w.update_kind({"update_id": 1, "message": {"from": {"id": 7}, "text": "hola"}}, AL)[0], "real", "kind: a new message from an allowed person is real")
chk(w.update_kind({"update_id": 2, "message": {"from": {"id": 7}, "location": {"latitude": 1, "longitude": 2}}}, AL)[0], "real", "kind: a NEW location pin is real (the person is asking for something)")
chk(w.update_kind({"update_id": 3, "edited_message": {"from": {"id": 7}, "date": 1, "location": {"latitude": 1, "longitude": 2, "live_period": 28800}}}, AL)[0], "live", "kind: a live-location refresh is not worth waking for")
chk(w.update_kind({"update_id": 4, "edited_message": {"from": {"id": 7}, "text": "corrected"}}, AL)[0], "real", "kind: an edited TEXT message is still real")
chk(w.update_kind({"update_id": 5, "message": {"from": {"id": 99}, "text": "hi"}}, AL)[0], "other", "kind: a stranger is other")
chk(w.update_kind({"update_id": 6, "my_chat_member": {}}, AL)[0], "other", "kind: a non-message update is other")
chk(w.update_kind({"update_id": 7, "callback_query": {"from": {"id": 7}, "data": "x"}}, AL)[0], "real", "kind: a button press is real")

# ---- warn_live_location: say it once, how to stop it, never spam ----
class W:
    name, lang = "t", ""
    state = {}
    def load_state(self): return dict(self.state)
    def save_state(self, **kw): self.state.update(kw)
    warn_live_location = w.Stack.warn_live_location
w_ = W(); w_.state = {}; w_.sent = []
w_.say = lambda chat, text: (w_.sent.append((chat, text)), True)[1]
live = {"message_id": 55, "chat": {"id": 7}, "location": {"live_period": 28800}}
chk((w_.warn_live_location(live), len(w_.sent), w_.sent[0][0]), (True, 1, 7), "live warning: sent once to the chat")
chk("Dejar de compartir" in w_.sent[0][1] and "pin" in w_.sent[0][1], True, "live warning: says how to stop it and what to send instead")
chk((w_.warn_live_location(live), len(w_.sent)), (False, 1), "live warning: the same shared location is never warned twice")
live2 = {**live, "message_id": 99}
chk((w_.warn_live_location(live2), len(w_.sent)), (False, 1), "live warning: a second one within 12 h is not warned either")
w_.state["live_warn_ts"] = w.time.time() - 13 * 3600
chk((w_.warn_live_location(live2), len(w_.sent)), (True, 2), "live warning: after 12 h a new shared location is warned")
w_.say = lambda chat, text: False
w_.state = {}
chk((w_.warn_live_location(live), w_.state), (False, {}), "live warning: a send Telegram refused is not recorded, so it is tried again")
chk(w_.warn_live_location({"message_id": 1}), False, "live warning: no chat means nothing to send")
chk(all(k in w.LIVE_WARN_TEXT for k in ("es", "ru", "en")), True, "live warning: texts in es, ru and en")

# ---- confirm_handled: the /dormir command must not come back at the next boot ----
class G:
    name, tg_on, tg_allowed, tg_seen, tg_paused = "t", True, {"7"}, 0, False
    confirm_handled = w.Stack.confirm_handled
    def save_state(self, **kw): self.saved = kw
def upd(i, uid, date, text="x"): return {"update_id": i, "message": {"from": {"id": uid}, "date": date, "text": text}}
def run_confirm(ups, ts, **kw):
    g = G(); g.calls = []
    for k, v in kw.items(): setattr(g, k, v)
    def tg(m, p, timeout=0):
        g.calls.append((m, dict(p)))
        return {"ok": True, "result": ups} if "offset" not in p else {"ok": True, "result": []}
    g.tg = tg
    return g, g.confirm_handled(ts)
g, got = run_confirm([upd(10, 7, 1000), upd(11, 7, 1099, "/dormir ya")], 1100)
chk((got, g.calls[-1][1].get("offset"), g.saved), (11, 12, {"tg_seen": 11}), "confirm: the /dormir command and everything before it is confirmed (offset = id + 1)")
g, got = run_confirm([upd(11, 7, 1099, "/dormir ya"), upd(12, 7, 1105, "hola")], 1100)
chk((got, g.calls[-1][1].get("offset")), (11, 12), "confirm: a message sent AFTER the request stays queued (only a prefix is confirmed)")
g, got = run_confirm([upd(12, 7, 1105, "hola")], 1100)
chk((got, len(g.calls)), (None, 1), "confirm: nothing before the request means nothing is confirmed")
g, got = run_confirm([upd(5, 99, 1000), upd(6, 7, 1050), upd(7, 99, 1200)], 1100)
chk((got, g.calls[-1][1].get("offset")), (6, 7), "confirm: strangers' updates do not decide the prefix")
g, got = run_confirm([upd(11, 7, 1099)], 1100, tg_on=False)
chk((got, g.calls), (None, []), "confirm: Telegram off does nothing")
g, got = run_confirm([{"update_id": 3, "callback_query": {"from": {"id": 7}, "message": {"date": 1000}}}], 1100)
chk(got, 3, "confirm: a button press is confirmed too, dated by the message it belongs to")
g = G(); g.calls = []
def broken(m, p, timeout=0): raise OSError("down")
g.tg = broken
chk((g.confirm_handled(1100), g.tg_paused), (None, False), "confirm: an API error is swallowed and the sentinel is released")
compile(w.Stack.DETACHED_SCRIPT.replace("MAXMIN", "360"), "detached", "exec")
print("sleep_request_selftest: all ok" if ok else "sleep_request_selftest: FAILED")
sys.exit(0 if ok else 1)
