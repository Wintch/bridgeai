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
# turns carry the build they ran on, and `builds` compares them (counts only)
check("turns has an image column", "image" in [r[1] for r in c.execute("pragma table_info(turns)")])
for i, (img, failed) in enumerate([("aaaaaaaaaaaa", 0), ("aaaaaaaaaaaa", 1), ("bbbbbbbbbbbb", 0)]):
    c.execute("insert into turns(stack, ts, session, source, model, seconds, tools, tool_errors, failed, empty, image) values(?,?,?,?,?,?,?,?,?,?,?)",
              ("a", now - 60 - i, f"s{i}", "telegram", "m", 10.0 + i, 0, 0, failed, 0, img))
out = tel.builds(c)
check("builds: one line per build, most turns first, failed share", out.splitlines()[1].split()[:3] == ["aaaaaaaaaaaa", "2", "50.0%"]
      and "bbbbbbbbbbbb" in out.splitlines()[2])
wake = os.path.join(os.path.dirname(tel.DB), "wake"); os.makedirs(wake, exist_ok=True)
tel.HERE = os.path.dirname(wake)
open(os.path.join(wake, "x.booted_image"), "w").write("sha256:96baa74c22ae0123456789")
check("booted_image: the short id from ops/wake/<stack>.booted_image", (tel.booted_image("x"), tel.booted_image("none")) == ("96baa74c22ae", None))
print("\n".join(fails) or "telemetry_report_selftest: all ok")
sys.exit(1 if fails else 0)
