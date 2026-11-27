#!/usr/bin/env python3
"""Offline checks of ops/worker_notices.py: the stack, the bot and docker are stubbed. Run: python3 -I ops/worker_notices_selftest.py"""
import importlib.util, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["WORKER_NOTICES_LOG"] = os.path.join(tempfile.mkdtemp(), "wn.log")
spec = importlib.util.spec_from_file_location("wn", os.path.join(HERE, "worker_notices.py"))
wn = importlib.util.module_from_spec(spec); spec.loader.exec_module(wn)
fails = []


def check(name, got, want):
    print(("ok   " if got == want else "FAIL ") + name)
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")


class World:
    def __init__(self, level="normal", notices=("a", "b"), send_ok=True, allowed=("42",)):
        self.files = {f"subs-{i}.txt": f"notice {n}" for i, n in enumerate(notices)}
        self.level, self.moved, self.sent, self.send_ok = level, [], [], send_ok
        wn.daily_ad.stack_of = lambda s: {"brain": "stack-x-hermes"} if s == "x" else None
        wn.daily_ad.target = lambda st: ("TOKEN", "http://bot", set(allowed))
        wn.job_summary.send = self.send
        wn.in_stack = self.in_stack
        wn.time.sleep = lambda s: None

    def send(self, tgt, chat, text):
        if self.send_ok:
            self.sent.append((chat, text))
        return self.send_ok

    def in_stack(self, brain, script, *args, timeout=60):
        if script is wn.LIST:
            names = sorted(self.files)[: int(args[1])]
            return 0, json.dumps({"level": self.level, "waiting": len(self.files),
                                  "notices": [{"name": n, "text": self.files[n]} for n in names]})
        d, sub, name = args
        self.moved.append((sub, name)); self.files.pop(name, None)
        return 0, ""


def wake(stack="x", chat="42", reason="telegram"):
    return wn.main(["wake", "--stack", stack, "--chat", chat, "--reason", reason, "--delay", "0"])


w = World()
check("telegram wake: every notice is sent, oldest first", (wake(), [t for _, t in w.sent]), (0, ["notice a", "notice b"]))
check("each sent notice is moved to sent/, nothing left", (w.moved, w.files), ([("sent", "subs-0.txt"), ("sent", "subs-1.txt")], {}))
w = World(); check("a wake that is not the person's message sends nothing", (wake(reason="cron"), w.sent, w.moved), (0, [], []))
w = World(allowed=("7",)); check("another chat id is refused", (wake(), w.sent), (2, []))
w = World(level="critical")
check("critical: nothing sent, the files go to skipped/", (wake(), w.sent, sorted(s for s, _ in w.moved)), (0, [], ["skipped", "skipped"]))
w = World(send_ok=False); check("a failed send keeps the notice for the next wake", (wake(), w.moved, len(w.files)), (1, [], 2))
w = World(notices=()); check("nothing waiting: nothing sent", (wake(), w.sent), (0, []))
w = World(); check("an unknown stack is skipped", (wake(stack="nope"), w.sent), (0, []))
print("\n".join(fails) or "worker_notices_selftest: all ok")
sys.exit(1 if fails else 0)
