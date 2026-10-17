#!/usr/bin/env python3
"""Offline checks for zabbix_hook.py: real HTTP against the receiver, Telegram replaced by a list. Run: python3 -I ops/zabbix_hook_selftest.py"""
import json, os, sys, tempfile, threading, urllib.error, urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
tmp = tempfile.mkdtemp()
import notify  # noqa: E402
notify.STATE_DIR, notify.STATE, notify.OUTBOX, notify.LOCK = tmp, f"{tmp}/s.json", f"{tmp}/o.jsonl", f"{tmp}/l"
sent = []
notify._tg = lambda text: sent.append(text) or True
import zabbix_hook as z  # noqa: E402
z.SCOPE = f"{tmp}/scope.json"

fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")

Handler = z.Handler
Handler.token = "tok"
srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/event"

def post(body, token="tok", path="/event", raw=None):
    data = raw if raw is not None else json.dumps(body).encode()
    req = urllib.request.Request(URL.replace("/event", path), data=data, headers={"X-Zabbix-Token": token, "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

T = [{"tag": "project", "value": "bridgeai"}, {"tag": "unit", "value": "hernik"}, {"tag": "service", "value": "tts"}, {"tag": "tier", "value": "critical"}]
ev = lambda i, status="PROBLEM", tags=T, name="TTS host down": {"event_id": str(i), "status": status, "name": name, "severity": "High", "host": "gpu-hq", "tags": tags}

check("bad token", post(ev(1), token="x")[0], 401)
check("wrong path", post(ev(1), path="/other")[0], 404)
check("not json", post(None, raw=b"{nope")[0], 400)
check("missing event id", post({"status": "OK"})[0], 400)
check("bad status", post({**ev(1), "status": "MAYBE"})[0], 400)
check("too big", post(None, raw=b"x" * 20000)[0], 413)

check("problem sent", post(ev(10)), (200, {"ok": True, "sent": True}))
check("text", sent[-1].split("] ", 1)[1], "⚠️ [bridgeai/hernik] tts: TTS host down (host gpu-hq, ALTA)")   # the bot prefixes [hostname]
check("same problem again (Zabbix retry)", post(ev(10)), (200, {"ok": True, "sent": False}))
check("recovery", post(ev(10, "OK"))[1], {"ok": True, "resolved": True})
check("recovery text", sent[-1].split("] ", 1)[1].startswith("✅ Resuelto: [bridgeai/hernik] tts: TTS host down"), True)
check("recovery of an unknown problem is quiet", post(ev(99, "OK"))[1], {"ok": True, "resolved": False})

n = len(sent)
post(ev(11, tags=[{"tag": "project", "value": "bridgeai"}]))
check("no unit is said, not hidden", "SIN UNIDAD" in sent[-1], True)
check("no unit still sent", len(sent), n + 1)

post(ev(12, name="disk full\n\x1b[31mIGNORE PREVIOUS INSTRUCTIONS " + "A" * 500))
check("control characters out, capped", ("\n" not in sent[-1]) and ("\x1b" not in sent[-1]) and len(sent[-1]) < 400, True)
post(ev(13, tags=[{"tag": "unit", "value": "x; rm -rf /"}, {"tag": "weird", "value": "a"}, {"tag": "unit", "value": "hereug"}]))
check("bad tag value dropped, next one wins", "?/hereug" in sent[-1], True)
post(ev(14, tags=[{"tag": "unit", "value": "first"}, {"tag": "unit", "value": "second"}]))
check("first tag wins", "?/first" in sent[-1], True)

# scope
z.save_scope({"only": [], "mute": ["unit:hernik"]})
n = len(sent)
check("muted", post(ev(20)), (200, {"ok": True, "muted": True}))
check("muted not sent", len(sent), n)
z.save_scope({"only": ["project:bridgeai"], "mute": []})
check("only: match passes", post(ev(21))[1].get("sent"), True)
check("only: other project muted", post(ev(22, tags=[{"tag": "project", "value": "vr"}, {"tag": "unit", "value": "pc"}]))[1].get("muted"), True)
z.save_scope({"only": [], "mute": ["unit:hernik"]})
post(ev(23, tags=[{"tag": "unit", "value": "hereug"}]))   # sent
z.save_scope({"only": [], "mute": ["unit:hereug"]})
check("a sent problem is closed even while muted", post(ev(23, "OK", tags=[{"tag": "unit", "value": "hereug"}]))[1], {"ok": True, "resolved": True})

# scope CLI
os.environ["ZBX_SCOPE_FILE"] = z.SCOPE
import subprocess
def cli(*a):
    r = subprocess.run([sys.executable, "-I", f"{HERE}/zabbix_hook.py", "scope", *a], capture_output=True, text=True, env={**os.environ, "OPS_ENV": f"{tmp}/none"})
    return r.returncode, r.stdout.strip()
check("cli clear", cli("clear"), (0, '{"only": [], "mute": []}'))
check("cli mute", cli("mute", "unit:hereug", "service:tts"), (0, '{"only": [], "mute": ["service:tts", "unit:hereug"]}'))
check("cli unmute", cli("unmute", "service:tts"), (0, '{"only": [], "mute": ["unit:hereug"]}'))
check("cli rejects a bad tag", cli("mute", "host:evil")[0] != 0, True)

# rate limit
z._recent.clear(); z._recent.extend([__import__("time").time()] * 60)
check("rate limit", post(ev(30))[0], 429)
srv.shutdown()
print("\n".join(fails) or "zabbix_hook_selftest: all checks passed")
sys.exit(1 if fails else 0)
