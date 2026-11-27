#!/usr/bin/env python3
"""Offline check of ops/telemetry.py report(): it covers the span since the last report and moves the mark only once the message was
handed to notify (2026-11-27: the report now runs in the Docker host's awake window, at irregular hours). Run: python3 -I ops/telemetry_report_selftest.py"""
import importlib.util, os, sqlite3, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("tel", os.path.join(HERE, "telemetry.py"))
tel = importlib.util.module_from_spec(spec); spec.loader.exec_module(tel)
fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


tel.DB = os.path.join(tempfile.mkdtemp(), "state", "telemetry.db")   # never the real one
c = tel.db()
sent = []
tel.notify.send = lambda text: (sent.append(text), True)[1]
seen_t0 = []
tel.stack_lines = lambda c_, name, t0: (seen_t0.append(t0), ("", {}))[1]
tel.gateway_report = lambda c_, t0: []
tel.learning_report = lambda stacks, t0: []
tel.backup_ages = lambda stacks: {}
stacks = [{"name": "a"}]

now = time.time()
tel.report(c, stacks, "daily", False)
check("first report: the last 24 h", abs(seen_t0[-1] - (now - 86400)) < 5 and sent and "Summary since" in sent[-1])
mark = float(tel.meta_get(c, "last_report:daily", 0))
check("the mark is set once the message is handed over", abs(mark - now) < 5)
tel.meta_set(c, "last_report:daily", now - 3 * 3600)
tel.report(c, stacks, "daily", False)
check("next report: since the last one (3 h), not a fixed 24 h", abs(seen_t0[-1] - (now - 3 * 3600)) < 5 and "(3 h)" in sent[-1])
tel.meta_set(c, "last_report:daily", now - 40 * 86400)
tel.report(c, stacks, "daily", False)
check("a mark older than the cap falls back to 1 day", abs(seen_t0[-1] - (now - 86400)) < 5)
tel.notify.send = lambda text: False                        # Telegram down: notify keeps it in its outbox and retries
tel.meta_set(c, "last_report:daily", now - 7200)
tel.report(c, stacks, "daily", False)
check("kept in the outbox counts as handed over: the mark moves", float(tel.meta_get(c, "last_report:daily", 0)) > now - 5)
def boom(text): raise KeyboardInterrupt                     # stopped (SIGTERM) before the send went through
tel.notify.send = boom
tel.meta_set(c, "last_report:daily", now - 7200)
try:
    tel.report(c, stacks, "daily", False)
except KeyboardInterrupt:
    pass
check("stopped before the send: the mark stays, the next run covers the same span",
      abs(float(tel.meta_get(c, "last_report:daily", 0)) - (now - 7200)) < 1)
print("\n".join(fails) or "telemetry_report_selftest: all ok")
sys.exit(1 if fails else 0)
