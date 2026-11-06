#!/usr/bin/env python3
"""Offline test of the on-demand sleep decision in ops/wake/waker.py (no docker, no server): python3 ops/sleep_request_selftest.py"""
import importlib.util, os, sys
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

# ---- a stuck gateway counter must not keep the stack awake or veto "dormir" (2026-11-05) ----
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

# ---- the last message of an on-request sleep is written by the host, after the stop (2026-11-06) ----
N1 = w.sleep_notice
chk(N1(True, "ahora", "es", "02:17"), "💤 Dormido (02:17 UTC). Escríbeme cuando quieras y me despierto (tarda unos minutos).", "notice: stopped, Spanish")
chk("Сплю (02:17 UTC)" in N1(True, "ahora", "ru", "02:17") and "Dormido" not in N1(True, "ahora", "ru", "02:17"), True, "notice: stopped, Russian only")
chk(N1(True, "ahora", "", "02:17").count("💤"), 2, "notice: no language configured -> both, es then ru")
chk("Terminó lo que corría" in N1(True, "cuando-termine", "es", "02:17") and "Terminó" not in N1(True, "ahora", "es", "02:17"), True, "notice: 'cuando-termine' says the work ended, 'ahora' does not")
chk("sigue arriba" in N1(False, "ahora", "es", "02:17") and "Dormido" not in N1(False, "ahora", "es", "02:17"), True, "notice: a stop that did not happen never says Dormido")
chk(N1(True, "otra-cosa", "xx", "02:17").count("💤"), 2, "notice: unknown mode and language do not crash")

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
    s.last_activity, s.cron_only, s.idle_web, s.idle_brain = w.time.time(), False, 600, 600
    s.web_started = s.brain_started = 0
    return s
w.NO_SLEEP = "/nonexistent-no-sleep-file"
w.ops = lambda *a, **k: None
a = sleeper(False); a.tick()
chk(a.events, ["clear", "stop", "tell:💤"], "tick: the 'Dormido' message comes after the stop, never before it")
b = sleeper(True); b.tick()
chk(b.events, ["clear", "stop", "tell:No"], "tick: if the container is still up after the stop, the person is told it did not sleep")
compile(w.Stack.DETACHED_SCRIPT.replace("MAXMIN", "360"), "detached", "exec")
print("sleep_request_selftest: all ok" if ok else "sleep_request_selftest: FAILED")
sys.exit(0 if ok else 1)
