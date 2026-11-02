#!/usr/bin/env python3
"""Offline test of ops/stack_telegram.py: no network, no Docker, a temporary ~/aibridge. Run: python3 ops/stack_telegram_selftest.py"""
import contextlib
import io
import json
import os
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stack_telegram as st  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


TOKEN = "123456789:" + "A" * 35
ENV0 = "STACK_NAME=hx\nSTACK_SUBNET=172.28.9.0/24\nHERMES_API_KEY=hk-abc\nTELEGRAM_BOT_TOKEN=\nTELEGRAM_ALLOWED_USERS=\nSTT_LANG=es\n"


class R:
    def __init__(self, rc=0):
        self.returncode = rc


def setup():
    d = tempfile.mkdtemp()
    os.makedirs(f"{d}/stacks/hx")
    open(f"{d}/stacks/hx/.env", "w").write(ENV0)
    conf = f"{d}/stacks.json"
    json.dump({"stacks": [{"name": "hx", "bind": "172.28.9.1", "port": 3099}]}, open(conf, "w"))
    st.stacks_add.CONF = conf
    os.chdir(d)
    return d, conf


def run(args, token=TOKEN, check_fn=lambda t: ("mybot", None), awake=False):
    calls = []
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = st.main(args, stdin=io.StringIO(token + "\n"), token_check=check_fn,
                     run=lambda cmd, **k: calls.append(cmd) or R(0), running=lambda n: awake)
    return rc, out.getvalue() + err.getvalue(), calls


d, conf = setup()
envf = f"{d}/stacks/hx/.env"

rc, out, calls = run(["hx", "+12025550100"])
check("a phone number instead of the id is refused", rc == 2 and not calls, out)
rc, out, calls = run(["hx", "@someone"])
check("an @name instead of the id is refused", rc == 2, out)
rc, out, calls = run(["hx", "123456789"], token="not-a-token")
check("a badly shaped token is refused", rc == 2, out)
rc, out, calls = run(["hx", "123456789"], check_fn=lambda t: (None, "bad_token"))
check("a token Telegram rejects is refused", rc == 1 and "does not recognise" in out, out)
rc, out, calls = run(["nope", "123456789"])
check("an unknown stack is refused", rc == 2, out)
check("nothing was written after the refusals", open(envf).read() == ENV0 and not os.path.exists(envf + ".bak-x"))

rc, out, calls = run(["hx", "987654321"])
env = open(envf).read()
check("a good pair is accepted", rc == 0 and "bot @mybot" in out, out)
check("token and id are in .env, once, in place", env.count("TELEGRAM_BOT_TOKEN=" + TOKEN) == 1 and "TELEGRAM_ALLOWED_USERS=987654321" in env, env)
check("the other variables and their order are kept", env.splitlines()[:3] == ENV0.splitlines()[:3] and "STT_LANG=es" in env, env)
check("the token is never printed", TOKEN not in out and "AAAAAAAA" not in out, out)
check(".env is mode 600", stat.S_IMODE(os.stat(envf).st_mode) == 0o600)
baks = [f for f in os.listdir(f"{d}/stacks/hx") if f.startswith(".env.bak-")]
check("the previous .env is kept as a 600 backup", len(baks) == 1 and stat.S_IMODE(os.stat(f"{d}/stacks/hx/{baks[0]}").st_mode) == 0o600, baks)
check("telegram_env was added to the stack in stacks.json",
      json.load(open(conf))["stacks"][0].get("telegram_env") == envf and len(json.load(open(conf))["stacks"]) == 1)
check("the waker is restarted and the sleeping stack is recreated",
      ["systemctl", "--user", "restart", "aibridge-waker"] in calls and any(c[-2:] == [os.path.join(HERE, "recreate_hermes.sh"), "hx"][-2:] for c in calls), calls)

rc, out, calls = run(["hx", "987654321"])
check("running it again keeps a single token line", open(envf).read().count("TELEGRAM_BOT_TOKEN=") == 1)
rc, out, calls = run(["hx", "987654321"], token="987654321:" + "B" * 35)
check("a different token replaces the old one and says so", "replacing" in out and ("B" * 35) in open(envf).read() and TOKEN not in open(envf).read(), out)

rc, out, calls = run(["hx", "987654321"], awake=True)
check("an awake stack is not recreated", not any("recreate_hermes" in c[0] for c in calls) and "awake" in out, (out, calls))
rc, out, calls = run(["hx", "987654321", "--no-recreate"])
check("--no-recreate does not recreate", not any("recreate_hermes" in c[0] for c in calls), calls)
rc, out, calls = run(["hx", "987654321", "--no-waker", "--no-recreate"])
check("--no-waker does not touch the waker", calls == [], calls)

# stacks_add on a stack not listed yet still adds a full block, with telegram
json.dump({"stacks": []}, open(conf, "w"))
run(["hx", "987654321", "--no-waker", "--no-recreate"])
blk = json.load(open(conf))["stacks"][0]
check("a stack not yet in stacks.json is added with its bot", blk["name"] == "hx" and blk.get("telegram_env") == envf and blk["bind"] == "172.28.9.1", blk)

print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
