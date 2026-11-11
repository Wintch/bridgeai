#!/usr/bin/env python3
"""Offline checks for ops/daily_ad.py against a fake Telegram Bot API (no network, no docker). Run: python3 -I ops/daily_ad_selftest.py"""
import contextlib, importlib.util, io, json, os, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []
SENT = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SENT.append({"path": self.path, **body})
        out = json.dumps({"ok": True, "result": {"message_id": len(SENT)}}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = tempfile.mkdtemp()
os.makedirs(os.path.join(base, "ops", "wake"))
envf = os.path.join(base, "tg.env")
open(envf, "w").write("TELEGRAM_BOT_TOKEN=123:SECRET-TOKEN\nTELEGRAM_ALLOWED_USERS=777\n")
json.dump({"stacks": [{"name": "ana", "telegram_env": envf, "lang": "es"}, {"name": "ivan", "telegram_env": envf, "lang": "ru"},
                      {"name": "mike", "telegram_env": envf, "lang": "en"}]}, open(os.path.join(base, "ops", "wake", "stacks.json"), "w"))
os.environ.update(DAILY_AD_DIR=base, DAILY_AD_API_BASE=f"http://127.0.0.1:{srv.server_address[1]}")
spec = importlib.util.spec_from_file_location("da", os.path.join(HERE, "daily_ad.py"))
da = importlib.util.module_from_spec(spec); spec.loader.exec_module(da)
CONF = os.path.join(base, "ops", "ads.json")
AD1 = {"id": "fate", "url": "https://michaelfate.example.com/", "title": {"es": "Arte oscuro hecho a mano", "en": "Handmade dark art", "ru": "Тёмное искусство"},
       "owner_stacks": ["mike"], "consent": "2026-11-08"}
AD2 = {"id": "fletes", "url": "https://fletes.example.com/", "title": "Fletes y mudanzas", "consent": "2026-11-01"}


def conf(**kw):
    c = {"enabled": True, "stacks": ["ana", "ivan", "mike"], "delay_s": 0, "ads": [AD1, AD2]}
    c.update(kw); json.dump(c, open(CONF, "w"))


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = da.main(list(argv))
    return rc, buf.getvalue()


conf()
rc, out = run("wake", "--stack", "ana", "--chat", "777", "--delay", "0")
check("a Telegram wake sends one ad to the stack's own chat", (rc, len(SENT), SENT[-1]["chat_id"]), (0, 1, "777"))
m = SENT[-1]
check("the text says what it is (label + ad) and carries the URL", ("Persona del día" in m["text"], "(anuncio)" in m["text"], AD1["url"] in m["text"]), (True, True, True))
check("the link preview is asked for that URL, large", (m["link_preview_options"]["url"], m["link_preview_options"]["prefer_large_media"]), (AD1["url"], True))
check("the bot token never appears in the output", "SECRET-TOKEN" in out, False)
rc, out = run("wake", "--stack", "ana", "--chat", "777", "--delay", "0")
check("a second wake the same day sends nothing", (rc, len(SENT)), (0, 1))
st = json.load(open(os.path.join(base, "ops", "ads_state.json")))
st["ana"]["last_day"] = "2000-01-01"; json.dump(st, open(os.path.join(base, "ops", "ads_state.json"), "w"))
rc, out = run("wake", "--stack", "ana", "--chat", "777", "--delay", "0")
check("the next day the next ad in turn is shown (round-robin)", (len(SENT), AD2["url"] in SENT[-1]["text"]), (2, True))
n = len(SENT)
for reason in ("cron", "web"):
    run("wake", "--stack", "ivan", "--chat", "777", "--reason", reason, "--delay", "0")
check("a cron or web wake never sends", len(SENT), n)
run("wake", "--stack", "ivan", "--chat", "", "--delay", "0")
check("no chat id, nothing sent", len(SENT), n)
run("wake", "--stack", "ivan", "--chat", "999", "--delay", "0")
check("a chat that is not the stack's allowed user gets nothing", len(SENT), n)
rc, out = run("wake", "--stack", "ivan", "--chat", "777", "--delay", "0")
check("the person's language is used (ru)", ("Человек дня" in SENT[-1]["text"], "(реклама)" in SENT[-1]["text"]), (True, True))
rc, out = run("wake", "--stack", "mike", "--chat", "777", "--delay", "0")
check("never the person's own ad: mike gets the other one", AD2["url"] in SENT[-1]["text"] and AD1["url"] not in SENT[-1]["text"], True)
n = len(SENT)
conf(stacks=["ana"])
json.dump({}, open(os.path.join(base, "ops", "ads_state.json"), "w"))
run("wake", "--stack", "ivan", "--chat", "777", "--delay", "0")
check("a stack not listed in \"stacks\" gets no ads (opt-in)", len(SENT), n)
conf(enabled=False)
run("wake", "--stack", "ana", "--chat", "777", "--delay", "0")
check("enabled false: nothing", len(SENT), n)
conf(ads=[dict(AD2, consent="")])
rc, out = run("wake", "--stack", "ana", "--chat", "777", "--delay", "0")
check("an ad without its owner's consent date never runs (config refused)", (rc, len(SENT)), (1, n))
conf(ads=[dict(AD2, until="2001-01-01")])
run("wake", "--stack", "ana", "--chat", "777", "--delay", "0")
check("an ad past its until date is skipped", len(SENT), n)
conf(ads=[dict(AD2, url="http://plain.example.com/")])
rc, out = run("check")
check("check refuses a non-https URL", ("plain https" in out, rc), (True, 1))
conf()
rc, out = run("test", "--stack", "ana", "--id", "fate")
st = json.load(open(os.path.join(base, "ops", "ads_state.json")))
check("test sends now and does not use up the day", (rc, AD1["url"] in SENT[-1]["text"], "ana" in st), (0, True, False))
rc, out = run("status")
check("status lists the stacks and the next ad", ("ana:" in out and "next fate" in out), True)

srv.shutdown()
print("daily_ad_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
