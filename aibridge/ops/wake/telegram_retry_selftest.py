#!/usr/bin/env python3
"""Offline test of two waker fixes from the 2026-11-07 review (no docker, no Telegram):

  4.2  read_env_file never follows a symlink and reads only a small regular file (the workdir .telegram.env is agent-writable)
  1.0  a failed Telegram wake puts tg_seen back and schedules a retry (60 s, 120 s, then 300 s) instead of consuming the message

Run from anywhere:  python3 ops/wake/telegram_retry_selftest.py
"""
import importlib.util, json, os, sys, tempfile, threading, time

spec = importlib.util.spec_from_file_location("waker", os.path.join(os.path.dirname(os.path.abspath(__file__)), "waker.py"))
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
w.log = lambda *a, **k: None
tmp = tempfile.mkdtemp()
ok = True


def chk(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what)


# 4.2 ---------------------------------------------------------------------------------------------------------------
mine = os.path.join(tmp, "mine.env"); open(mine, "w").write("TELEGRAM_BOT_TOKEN=111:mine\nTELEGRAM_ALLOWED_USERS=1,2\n")
other = os.path.join(tmp, "other.env"); open(other, "w").write("TELEGRAM_BOT_TOKEN=222:other\n")
link = os.path.join(tmp, "link.env"); os.symlink("other.env", link)
big = os.path.join(tmp, "big.env"); open(big, "w").write("TELEGRAM_BOT_TOKEN=333:big\n" + "#" * (70 * 1024))
fifo = os.path.join(tmp, "fifo.env"); os.mkfifo(fifo)
chk(w.read_env_file(mine).get("TELEGRAM_BOT_TOKEN") == "111:mine", "a regular env file is read")
chk(w.read_env_file(link) == {}, "a symlink (to another stack's .env) is not followed")
chk(w.read_env_file(big) == {}, "a file over 64 KB is ignored")
t0 = time.time()
chk(w.read_env_file(fifo) == {} and time.time() - t0 < 2, "a FIFO is ignored without blocking")
chk(w.read_env_file(os.path.join(tmp, "missing.env")) == {}, "a missing file gives nothing")


# 1.0 ---------------------------------------------------------------------------------------------------------------
class S:
    name = "x"
    state_file = os.path.join(tmp, "x.state.json")
    state_lock = threading.Lock()
    tg_seen, wake_failed, tg_retry_at, tg_retry_n = 0, False, 0.0, 0


for m in ("wake_for_telegram", "load_state", "save_state"):
    setattr(S, m, getattr(w.Stack, m))
s = S()
outcome = {"fail": True}


def fake_wake(reason, want_web=False, chat_id=None):
    s.wake_failed = outcome["fail"]


s.wake = fake_wake
s.tg_seen = 105                                   # the sentinel already moved it to the message that triggered the wake
s.wake_for_telegram(chat=7, update_id=105, prev_seen=100)
chk(s.tg_seen == 100 and s.load_state().get("tg_seen") == 100, "failed wake: tg_seen goes back (the same message wakes it again)")
chk(55 < s.tg_retry_at - time.time() <= 60 and s.tg_retry_n == 1, "first retry in 60 s")
s.tg_seen = 105
s.wake_for_telegram(chat=7, update_id=105, prev_seen=100)
chk(115 < s.tg_retry_at - time.time() <= 120, "second retry in 120 s")
for _ in range(3):
    s.tg_seen = 105
    s.wake_for_telegram(chat=7, update_id=105, prev_seen=100)
chk(295 < s.tg_retry_at - time.time() <= 300 and s.tg_retry_n == 3, "later retries every 300 s")
s.tg_seen = 110                                   # a newer message arrived meanwhile: it owns the retry
s.wake_for_telegram(chat=7, update_id=105, prev_seen=100)
chk(s.tg_seen == 110, "a newer message is never rolled back")
outcome["fail"] = False
s.tg_seen = 110
s.wake_for_telegram(chat=7, update_id=110, prev_seen=105)
chk(s.tg_seen == 110 and s.tg_retry_n == 0, "a good wake keeps tg_seen and resets the back-off")

print("all ok" if ok else "FAILED")
sys.exit(0 if ok else 1)
