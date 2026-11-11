#!/usr/bin/env python3
"""Self-test for connecting Telegram on the keys page (keys_server.py) and the waker noticing it (ops/wake/waker.py).
No network, no Docker:  python3 ops/telegram_connect_selftest.py
"""
import importlib.util, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
fails = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        fails.append(what)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


TOKEN = "123456789:" + "A" * 35
tmp = tempfile.mkdtemp()
ks = load("keys_server", os.path.join(ROOT, "keys_server.py"))
ks.TG_ENV = os.path.join(tmp, "hermes.env")
ks.TG_HANDOFF = os.path.join(tmp, "telegram.env")
ks.STATUS_FILE = os.path.join(tmp, "status.json")
ks.os.environ.pop("TELEGRAM_BOT_TOKEN", None)
restarts = []
ks.restart_gateway_if_idle = lambda: restarts.append(1) or True
ks.tg_get_me = lambda t: ("mybot", None) if t == TOKEN else (None, "bad_token")
open(ks.TG_ENV, "w").write("GROQ_API_KEY=keepme\n")

code, r = ks.do_telegram_save("nonsense", "42")
check(not r["ok"] and "BotFather" in r["error"], "a token with the wrong shape is refused before any call")
code, r = ks.do_telegram_save(TOKEN, "@someone")
check(not r["ok"] and "número" in r["error"], "a user @name instead of the numeric id is refused")
code, r = ks.do_telegram_save("987654321:" + "B" * 35, "123456")
check(not r["ok"] and "no reconoce" in r["error"], "a well-shaped token Telegram rejects is refused")
check(not os.path.exists(ks.TG_HANDOFF), "nothing is written after a refusal")

code, r = ks.do_telegram_save(" " + TOKEN + " ", "123456789")
check(r["ok"] and "@mybot" in r["message"] and TOKEN not in r["message"], "a good pair is saved, names the bot, never echoes the token")
env = ks._dotenv_read(ks.TG_ENV)
check(env.get("TELEGRAM_BOT_TOKEN") == TOKEN and env.get("TELEGRAM_ALLOWED_USERS") == "123456789" and env.get("GROQ_API_KEY") == "keepme",
      "token and id go to Hermes's .env and the other keys stay")
check(ks._dotenv_read(ks.TG_HANDOFF).get("TELEGRAM_BOT_TOKEN") == TOKEN and oct(os.stat(ks.TG_HANDOFF).st_mode & 0o777) == "0o600",
      "the host copy exists with mode 600")
check(restarts == [1], "an idle gateway is restarted once")
code, r = ks.do_telegram("ru")
t = r["telegram"]
check(t["connected"] and t["bot"] == "mybot" and t["uid_last"] == "789" and TOKEN not in str(r), "status shows the bot and the last 3 of the id, never the token")
check(t["label"] == "Telegram" and "Токен" in t["token"], "texts come in the person's language")

# waker: reads the host copy, notices changes without a restart
src = open(os.path.join(HERE, "wake", "waker.py"), encoding="utf-8").read()
src = src.split("\nif __name__")[0]
w = {"__name__": "waker_t", "__file__": os.path.join(HERE, "wake", "waker.py")}
exec(compile(src, "waker.py", "exec"), w)
S = w["Stack"].__new__(w["Stack"])
S.name, S.tg_files, S.tg_token, S.tg_allowed, S.tg_on, S.sentinel_started = "t", [ks.TG_HANDOFF], "", set(), False, False
w["log"] = lambda *a, **k: None
started = []
S.start_sentinel = lambda: started.append(1)
S.refresh_telegram()
check(S.tg_on and S.tg_token == TOKEN and S.tg_allowed == {"123456789"} and started == [1], "the waker picks the token up on its next tick and starts the sentinel")
S.refresh_telegram()
check(started == [1], "an unchanged file does nothing")

code, r = ks.do_telegram_remove()
check(r["ok"] and not os.path.exists(ks.TG_HANDOFF) and "TELEGRAM_BOT_TOKEN" not in ks._dotenv_read(ks.TG_ENV)
      and ks._dotenv_read(ks.TG_ENV).get("GROQ_API_KEY") == "keepme", "disconnecting removes both copies and leaves other keys")
S.refresh_telegram()
check(not S.tg_on and S.tg_token == "", "the waker stops treating the stack as having a bot")

ks.os.environ["TELEGRAM_BOT_TOKEN"] = TOKEN
code, r = ks.do_telegram_save(TOKEN, "123456789")
check(not r["ok"] and "administrador" in r["error"], "a bot the administrator connected cannot be overwritten from the page")
code, r = ks.do_telegram_remove()
check(not r["ok"], "nor removed from the page")
code, r = ks.do_telegram("es")
t = r["telegram"]
check(t["is_managed"] is True and t["managed"] == "Telegram lo conectó el administrador.",
      "an administrator's bot: the flag is separate and the card shows the sentence, not 'true'")
html = open(os.path.join(ROOT, "keys_page.html"), encoding="utf-8").read()
check("if (t.is_managed)" in html and "textContent:t.managed" in html, "the page decides on is_managed and prints the sentence")
ks.os.environ.pop("TELEGRAM_BOT_TOKEN", None)
code, r = ks.do_telegram("es")
check(r["telegram"]["is_managed"] is False and isinstance(r["telegram"]["managed"], str), "a person's own bot keeps the sentence as text and the flag false")

print("\n%d failed" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
