#!/usr/bin/env python3
"""Offline checks for `gateway canal` (canal.py), its cron script and the owner's /publicar in the controls plugin, against a FAKE Telegram Bot API
(an in-memory HTTP server that checks the bot token in the path, parses JSON and multipart bodies and can fail on demand).

Covered: a draft goes to the OWNER's chat as the exact post plus an instruction whose `code` entity holds the one-time command, and nothing reaches the
channel; the model has no subcommand that publishes; forged approvals (wrong user, wrong code, unknown id, replay, expired, too many tries, a record
edited after the preview) do nothing; the owner's approval posts to the channel, records the message id and answers with the link; edit and delete work
only on posts this bot published and only after the owner's approval; a schedule posts at its time and not before, not stale, not after a change; media
is checked by its bytes, copied and hashed; text, caption and media limits; secrets, local paths and private links refused; the token is never printed,
logged or stored; the plugin command; the config pass-through, the pack and the files that ship. Run: python3 -I gateway_canal_selftest.py"""
import contextlib, datetime, importlib.util, io, json, logging, os, re, shutil, struct, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
fails = []


def check(name, cond):
    if not cond:
        fails.append(name)
        print("FAIL " + name)
    else:
        print("ok   " + name)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


TOKEN = "123456789:" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456"
OWNER, OTHER = "111222333", "999888777"
CHANNEL = "@TestChannel"

# ------------------------------------------------------------------------------------------------ the fake Bot API
ST = {"calls": [], "next": 500, "fail": None, "desc": None}


def parse_multipart(ctype, body):
    boundary = ctype.split("boundary=", 1)[1].encode()
    out = {}
    for part in body.split(b"--" + boundary):
        if b"\r\n\r\n" not in part:
            continue
        head, _, data = part.partition(b"\r\n\r\n")
        m = re.search(rb'name="([^"]+)"', head)
        if m:
            out[m.group(1).decode()] = ("<file %d bytes>" % len(data.rstrip(b"\r\n"))) if b"filename=" in head else data.rstrip(b"\r\n").decode()
            if b"filename=" in head:
                out["_bytes"] = len(data.rstrip(b"\r\n"))
    return out


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        ctype = self.headers.get("Content-Type", "")
        m = re.fullmatch(r"/bot([^/]+)/(\w+)", self.path)
        if not m or m.group(1) != TOKEN:
            return self.reply(401, {"ok": False, "description": "Unauthorized"})
        method = m.group(2)
        fields = parse_multipart(ctype, raw) if ctype.startswith("multipart/") else json.loads(raw or b"{}")
        ST["calls"].append((method, fields))
        f = ST["fail"]
        if f and f["method"] == method and (f.get("chat") is None or str(fields.get("chat_id")) == f["chat"]):
            if f.get("once"):
                ST["fail"] = None
            if f["kind"] == "drop":
                self.close_connection = True
                self.connection.close()
                return
            if f["kind"] == "502":                      # a proxy's gateway error: the post may have been made
                body = b"<html>502 Bad Gateway</html>"
                self.send_response(502)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if f["kind"] == "503json":                  # even with a JSON body, a 5xx is not a refusal
                return self.reply(503, {"ok": False, "description": "Service Unavailable"})
            if f["kind"] == "429":
                return self.reply(429, {"ok": False, "description": "Too Many Requests: retry after 5", "parameters": {"retry_after": 5}})
            return self.reply(400, {"ok": False, "description": ST["desc"] or "Bad Request: chat not found"})
        if method == "deleteMessage" or method.startswith("edit"):
            return self.reply(200, {"ok": True, "result": True})
        ST["next"] += 1
        chat = str(fields.get("chat_id"))
        res = {"message_id": ST["next"], "chat": {"id": chat, "username": chat[1:]} if chat.startswith("@") else {"id": chat}}
        return self.reply(200, {"ok": True, "result": res})


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]

# ------------------------------------------------------------------------------------------------ the module under test, pointed at the fake
canal = load("canal", os.path.join(HERE, "canal.py"))
hermes_home = os.path.join(tmp, "hermes")
os.makedirs(hermes_home)
open(os.path.join(hermes_home, ".env"), "w").write(f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_ALLOWED_USERS={OWNER},{OTHER}\n")
conf_path = os.path.join(tmp, "gateways.json")
json.dump({"canal": {"chat": CHANNEL, "title": "Test Channel", "tz": "America/Argentina/Buenos_Aires"}}, open(conf_path, "w"))
cron_calls = os.path.join(tmp, "cron.calls")
fake_hermes = os.path.join(tmp, "hermes-bin")
open(fake_hermes, "w").write(f"#!/bin/sh\necho \"$@\" >> {cron_calls}\n")
os.chmod(fake_hermes, 0o755)
canal.CONF, canal.ROOT, canal.LOG, canal.PREFS = conf_path, os.path.join(tmp, "canal"), os.path.join(tmp, "gateway-log.jsonl"), os.path.join(tmp, "prefs.json")
canal.KEY_PATH = os.path.join(tmp, "keys", ".canal-key")      # outside canal.ROOT, as in production (/hermes-persist vs /workdir)
canal.HERMES_HOMES, canal.API_BASE, canal.HERMES_BIN = (hermes_home,), f"http://127.0.0.1:{PORT}/bot", fake_hermes
canal.PREVIEWS_PER_DAY = 10 ** 6                  # the daily cap has its own check below


def run(*argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    old_in = sys.stdin
    if stdin is not None:
        sys.stdin = io.TextIOWrapper(io.BytesIO(stdin.encode()))
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = canal.main(list(argv))
    finally:
        sys.stdin = old_in
    return rc, out.getvalue() + err.getvalue()


def reset_calls():
    ST["calls"].clear()
    ST["fail"] = None
    ST["desc"] = None


def to(chat):
    return [(m, f) for m, f in ST["calls"] if str(f.get("chat_id")) == chat]


def code_of(draft_id):
    """What the owner sees: the command in the last instruction message sent to the owner (the harness plays the owner, the model never gets this)."""
    for m, f in reversed(ST["calls"]):
        if m == "sendMessage" and str(f.get("chat_id")) == OWNER and f"/publicar {draft_id} " in f.get("text", ""):
            mm = re.search(rf"/publicar {draft_id} ([A-Z2-9]{{10}})", f["text"])
            if mm:
                return mm.group(1)
    return None


def rec(i):
    return json.load(open(os.path.join(canal.ROOT, f"{i}.json")))


def rec_text(i):
    return open(os.path.join(canal.ROOT, f"{i}.json")).read()


def jpeg(w=800, h=600, pad=0):
    return (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\xff\xc0\x00\x11\x08" + struct.pack(">HH", h, w)
            + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01" + b"\x00" * pad + b"\xff\xd9")


def png(w=800, h=600):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00" + b"\x00" * 40


def mp4(pad=0):
    return b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * (32 + pad)


def put(name, data):
    p = os.path.join(tmp, name)
    open(p, "wb").write(data)
    return p


# ------------------------------------------------------------------------------------------------ no configuration
canal.CONF = os.path.join(tmp, "missing.json")
rc, out = run("borrador", "hola")
check("no canal block: a fixed sentence, exit 3, nothing sent", rc == 3 and "no tiene un canal configurado" in out and not ST["calls"])
canal.CONF = conf_path
json.dump({"canal": {"chat": "not a chat", "title": "x"}}, open(os.path.join(tmp, "bad.json"), "w"))
canal.CONF = os.path.join(tmp, "bad.json")
rc, out = run("borrador", "hola")
check("a malformed canal block is refused as a configuration error", rc == 3 and "mal escrita" in out and not ST["calls"])
canal.CONF = conf_path

# ------------------------------------------------------------------------------------------------ a text draft: preview to the owner only
reset_calls()
rc, out = run("borrador", "Hola canal: hoy sale la versión 2.\nMás en https://example.org/v2 #novedades")
check("borrador: exit 0 and the model is told it is NOT published", rc == 0 and "NO está publicado" in out and "enviado a tu dueño" in out)
check("the model-facing answer carries no code and no token", not re.search(r"[A-Z2-9]{10}", out.replace("PUBLICADO", "")) and TOKEN not in out and "/publicar 1 " not in out)
m1, f1 = ST["calls"][0]
m2, f2 = ST["calls"][1]
check("two messages went to the owner's chat and none to the channel", len(ST["calls"]) == 2 and all(str(f.get("chat_id")) == OWNER for _, f in ST["calls"]) and not to(CHANNEL))
check("the first is the exact post as plain text: no parse_mode, no entities, no buttons", m1 == "sendMessage" and f1["text"] == "Hola canal: hoy sale la versión 2.\nMás en https://example.org/v2 #novedades"
      and not ({"parse_mode", "entities", "reply_markup"} & set(f1)))
code1 = code_of(1)
check("the second holds the one-time command in a `code` entity", code1 and f2.get("entities") and f2["entities"][0]["type"] == "code")
cmd_text = f"/publicar 1 {code1}"
units = f2["text"].encode("utf-16-le")
off, ln = f2["entities"][0]["offset"], f2["entities"][0]["length"]
check("the entity covers exactly the command (UTF-16 offsets)", units[off * 2:(off + ln) * 2].decode("utf-16-le") == cmd_text)
check("the instruction names the channel and that the code is the owner's alone", "Test Channel" in f2["text"] and "No se lo des al asistente" in f2["text"])
r1 = rec(1)
check("the record is a draft with a pending publish and no plaintext code anywhere on disk", r1["state"] == "draft" and r1["pending"]["op"] == "publish"
      and code1 not in rec_text(1) and code1 not in open(canal.LOG).read() + "".join(open(os.path.join(canal.ROOT, n)).read() for n in os.listdir(canal.ROOT) if not n.endswith(".json") and os.path.isfile(os.path.join(canal.ROOT, n))))
check("the code is 10 characters from an alphabet with no look-alikes", re.fullmatch(r"[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{10}", code1) is not None)
check("the log has metadata only", all(set(json.loads(l)) <= {"ts", "cmd", "sub", "ok", "rc"} for l in open(canal.LOG)))
rc, out = run("lista")
check("lista shows the draft as waiting for the owner, without any code", rc == 0 and "1 | borrador" in out and "esperando la aprobación" in out and code1 not in out)
rc, out = run("ver", "1")
check("ver prints the text as quoted data", "> Hola canal" in out and "dato del borrador" in out)

# ------------------------------------------------------------------------------------------------ the model cannot publish
for sub in ("publicar", "aprobar", "approve", "publish", "due"):
    reset_calls()
    rc, out = run(sub, "1", code1)
    check(f"`canal {sub}` does not exist for the model and sends nothing", rc == 2 and "no existe" in out and not ST["calls"])
check("no model-facing sub-command can publish, approve or run the schedule", not ({"publicar", "aprobar", "approve", "publish", "due", "pub"} & set(canal.COMMANDS)))
reset_calls()
rc, out = run("descartar", "1", "--publicar")
check("an unknown flag is refused", rc == 2)
run("descartar", "1", "extra")
check("descartar with an extra word is refused, the draft stays", rec(1)["state"] == "draft")

# ------------------------------------------------------------------------------------------------ forged approvals do nothing
reset_calls()
bad = canal.approve(1, "AAAAAAAAAA", sender=OWNER)
check("a wrong code: refused with the uniform sentence, nothing sent", "no corresponde" in bad and not to(CHANNEL) and rec(1)["state"] == "draft")
check("a wrong code counts a try", rec(1)["pending"]["tries"] == 1)
check("the right code from another user id: refused, nothing sent", "no corresponde" in canal.approve(1, code1, sender=OTHER) and not to(CHANNEL) and rec(1)["state"] == "draft")
check("an unknown draft id: the same sentence", canal.approve(77, code1, sender=OWNER) == bad)
check("a malformed id or a missing code: the usage sentence, nothing sent", "Uso:" in canal.approve("x", code1) and not to(CHANNEL))
rr = rec(1)
rr["text"] = "Hola canal: texto cambiado por el modelo"
open(os.path.join(canal.ROOT, "1.json"), "w").write(json.dumps(rr))
check("a record edited after the preview no longer matches its approval: nothing sent", "no corresponde" in canal.approve(1, code1, sender=OWNER) and not to(CHANNEL))
rr["text"] = "Hola canal: hoy sale la versión 2.\nMás en https://example.org/v2 #novedades"
rr["pending"]["tries"] = 0
open(os.path.join(canal.ROOT, "1.json"), "w").write(json.dumps(rr))
for _ in range(canal.MAX_TRIES):
    canal.approve(1, "BBBBBBBBBB")
check("five wrong tries cancel the pending approval (the right code then fails too)", rec(1)["pending"] is None and "no corresponde" in canal.approve(1, code1) and not to(CHANNEL))
rc, out = run("reenviar", "1")
code1 = code_of(1)
check("reenviar: a fresh approval message and a new code", rc == 0 and code1 and rec(1)["pending"]["tries"] == 0)
rr = rec(1)
rr["pending"]["expires"] = int(time.time()) - 5
open(os.path.join(canal.ROOT, "1.json"), "w").write(json.dumps(rr))
check("an expired code is refused", "no corresponde" in canal.approve(1, code1) and not to(CHANNEL))
rc, out = run("reenviar", "1")
code1 = code_of(1)

# ------------------------------------------------------------------------------------------------ the owner approves: it posts
reset_calls()
ans = canal.approve(1, code1.lower()[:5] + " " + code1.lower()[5:], sender=OWNER)       # typed in lower case with a space: normalised
sent = to(CHANNEL)
check("the owner's approval posts the exact text to the channel (plain, no formatting)", len(sent) == 1 and sent[0][0] == "sendMessage"
      and sent[0][1]["text"] == "Hola canal: hoy sale la versión 2.\nMás en https://example.org/v2 #novedades" and not ({"parse_mode", "entities"} & set(sent[0][1])))
r1 = rec(1)
check("the record is published with the channel message id and no pending", r1["state"] == "published" and r1["published"]["message_id"] == ST["next"] and r1["pending"] is None)
check("the owner is told with the post link", ans == f"Publicado en Test Channel: https://t.me/TestChannel/{ST['next']}")
reset_calls()
check("replaying the same command does nothing", "no corresponde" in canal.approve(1, code1, sender=OWNER) and not ST["calls"])
rc, out = run("lista")
check("lista now shows it as published with its link", "1 | publicado" in out and "t.me/TestChannel/" in out)
rc, out = run("descartar", "1")
check("a published post cannot be discarded (only deleted with approval)", rc == 2 and "borrar" in out)
rc, out = run("reenviar", "1")
check("a published post cannot be re-sent as a draft", rc == 2)

# ------------------------------------------------------------------------------------------------ edit and delete: own posts, owner's approval
reset_calls()
rc, out = run("editar", "99", "x")
check("editar on an id that is not this bot's post: refused", rc == 2 and not ST["calls"])
rc, out = run("borrador", "Segundo borrador")
check("a second draft", rc == 0 and rec(2)["state"] == "draft")
reset_calls()
rc, out = run("editar", "2", "cambio")
check("editar on a draft (not published by this bot): refused, nothing sent", rc == 2 and "publicó" in out and not ST["calls"])
rc, out = run("borrar", "2")
check("borrar on a draft: refused", rc == 2 and not ST["calls"])
reset_calls()
rc, out = run("editar", "1", "Texto corregido del post 1")
code_e = code_of(1)
check("editar on a published post asks the owner: new text and the old one shown, the channel is not touched", rc == 0 and code_e and not to(CHANNEL) and "no cambia hasta" in out
      and ST["calls"][0][1]["text"] == "Texto corregido del post 1" and "Hola canal" in ST["calls"][-1][1]["text"])
reset_calls()
check("a wrong code does not edit", "no corresponde" in canal.approve(1, "CCCCCCCCCC", sender=OWNER) and not ST["calls"])
check("another user does not edit", "no corresponde" in canal.approve(1, code_e, sender=OTHER) and not ST["calls"])
ST["fail"] = {"method": "editMessageText", "kind": "400", "once": True}
ans = canal.approve(1, code_e, sender=OWNER)
check("Telegram refuses the edit: the owner is told, the code stays valid", "rechazó" in ans and rec(1)["pending"] is not None and rec(1)["text"].startswith("Hola canal"))
reset_calls()
ans = canal.approve(1, code_e, sender=OWNER)
check("the owner repeats it and the edit goes to the right message", ST["calls"][-1][0] == "editMessageText" and ST["calls"][-1][1]["chat_id"] == CHANNEL
      and ST["calls"][-1][1]["message_id"] == rec(1)["published"]["message_id"] and ST["calls"][-1][1]["text"] == "Texto corregido del post 1" and "Cambiado el post 1" in ans)
check("the record keeps the new text and the pending is gone", rec(1)["text"] == "Texto corregido del post 1" and rec(1)["pending"] is None)
reset_calls()
check("the edit code is single-use", "no corresponde" in canal.approve(1, code_e, sender=OWNER) and not ST["calls"])
reset_calls()
rc, out = run("borrar", "1")
code_d = code_of(1)
check("borrar asks the owner and deletes nothing yet", rc == 0 and code_d and not [c for c in ST["calls"] if c[0] == "deleteMessage"])
check("a code of another operation does not delete", "no corresponde" in canal.approve(1, code_e, sender=OWNER) and not [c for c in ST["calls"] if c[0] == "deleteMessage"])
ans = canal.approve(1, code_d, sender=OWNER)
check("the owner's approval deletes exactly that message of the channel", [c for c in ST["calls"] if c[0] == "deleteMessage"][-1][1] == {"chat_id": CHANNEL, "message_id": rec(1)["published"]["message_id"]} and "Borrado el post 1" in ans)
check("a deleted post is out of the list and cannot be touched again", rec(1)["state"] == "deleted" and "1 |" not in run("lista")[1] and run("editar", "1", "x")[0] == 2 and run("borrar", "1")[0] == 2)
reset_calls()
rc, out = run("borrar", "2")
check("borrar of a draft is still refused after all this", rc == 2)

# ------------------------------------------------------------------------------------------------ one `no` cancels
rc, out = run("reenviar", "2")
check("cancel: /publicar N no discards a draft and sends nothing", "Cancelado" in canal.approve(2, "no") and rec(2)["state"] == "discarded" and not to(CHANNEL))
check("a discarded draft cannot be approved any more", "no corresponde" in canal.approve(2, "AAAAAAAAAA"))

# ------------------------------------------------------------------------------------------------ Telegram errors and doubt
reset_calls()
rc, out = run("borrador", "Tercero")
code3 = code_of(3)
ST["fail"] = {"method": "sendMessage", "kind": "400", "chat": CHANNEL, "once": True}
ST["desc"] = f"Forbidden: bot is not a member of the channel chat {TOKEN}"
ans = canal.approve(3, code3, sender=OWNER)
check("a clear refusal from Telegram: the owner reads why (the token is masked), the draft and its code stay", "rechazó" in ans and TOKEN not in ans and "***" in ans and rec(3)["state"] == "draft" and rec(3)["pending"])
ans = canal.approve(3, code3, sender=OWNER)
check("repeating it then publishes", "Publicado en" in ans and rec(3)["state"] == "published")
rc, out = run("borrador", "Cuarto")
code4 = code_of(4)
ST["fail"] = {"method": "sendMessage", "kind": "drop", "chat": CHANNEL, "once": True}
ans = canal.approve(4, code4, sender=OWNER)
n_before = len(to(CHANNEL))
check("a dropped connection: nobody knows if it went out, so it says so and marks it", "No sé si" in ans and rec(4).get("inflight"))
check("with the doubt open the same code does not post a second time", "no corresponde" in canal.approve(4, code4, sender=OWNER) and len(to(CHANNEL)) == n_before)
check("lista warns the model not to repeat it", "no se sabe si salió" in run("lista")[1])
check("the owner closes the doubt with `no`", "Cancelado" in canal.approve(4, "no") and rec(4)["state"] == "discarded" and not rec(4).get("inflight"))
reset_calls()
ST["fail"] = {"method": "sendMessage", "kind": "400", "chat": OWNER, "once": True}
rc, out = run("borrador", "No llega al dueño")
left = [n for n in os.listdir(canal.ROOT) if n.endswith(".json") and "No llega" in open(os.path.join(canal.ROOT, n)).read()]
check("when the preview cannot be sent the draft is not kept and the model is told", rc == 3 and "No pude mandarle" in out and not left)

# ------------------------------------------------------------------------------------------------ media
reset_calls()
p_jpg = put("a.jpg", jpeg())
rc, out = run("borrador", "Foto del día", "--foto", p_jpg)
cid = int(re.search(r"borrador (\d+)", out).group(1))
mm, ff = ST["calls"][0]
check("a photo draft goes to the owner as a photo with the caption (multipart), then the instruction", rc == 0 and mm == "sendPhoto" and ff["caption"] == "Foto del día" and ff.get("_bytes") == len(jpeg())
      and ff["chat_id"] == OWNER and ST["calls"][1][0] == "sendMessage")
check("the file was copied into the draft folder and hashed", os.path.isfile(os.path.join(canal.ROOT, rec(cid)["media"]["file"])) and len(rec(cid)["media"]["sha256"]) == 64)
open(p_jpg, "wb").write(jpeg(100, 100))
rc, out = run("reenviar", str(cid))
codep = code_of(cid)
reset_calls()
ans = canal.approve(cid, codep, sender=OWNER)
sent = to(CHANNEL)
check("approval posts the copy taken at draft time (changing the original later changes nothing)", len(sent) == 1 and sent[0][0] == "sendPhoto" and sent[0][1]["caption"] == "Foto del día" and sent[0][1]["_bytes"] == len(jpeg()))
check("the media copy is removed once published, and the post is recorded", not os.path.exists(os.path.join(canal.ROOT, f"{cid}.media.jpg")) and rec(cid)["state"] == "published")
reset_calls()
rc, out = run("editar", str(cid), "Pie corregido")
code_c = code_of(cid)
canal.approve(cid, code_c, sender=OWNER)
check("a media post is edited through its caption", ST["calls"][-1][0] == "editMessageCaption" and ST["calls"][-1][1]["caption"] == "Pie corregido")
rc, out = run("editar", str(cid), "x" * 1025)
check("the new caption of a media post is held to 1024 characters", rc == 2 and "1024" in out)
# tampering with the stored copy between approval and posting
rc, out = run("borrador", "Con video", "--video", put("v.mp4", mp4()))
vid = int(re.search(r"borrador (\d+)", out).group(1))
codev = code_of(vid)
stored = os.path.join(canal.ROOT, rec(vid)["media"]["file"])
good = open(stored, "rb").read()
open(stored, "wb").write(good + b"tampered")
reset_calls()
ans = canal.approve(vid, codev, sender=OWNER)
check("a stored copy that changed after the preview is not posted", "rechazó" in ans and not to(CHANNEL) and rec(vid)["state"] == "draft")
open(stored, "wb").write(good)
ans = canal.approve(vid, codev, sender=OWNER)
check("the intact copy posts as a streaming video", to(CHANNEL) and to(CHANNEL)[-1][0] == "sendVideo" and to(CHANNEL)[-1][1].get("supports_streaming") == "true" and "Publicado" in ans)
# validation
reset_calls()
cases = [("a text file named .jpg", ["borrador", "x", "--foto", put("t.jpg", b"hello world, not an image" * 10)], "contenido"),
         ("a PNG of 9000x9000 (width plus height over 10000)", ["borrador", "x", "--foto", put("big.png", png(9000, 9000))], "límites"),
         ("a PNG with ratio over 20", ["borrador", "x", "--foto", put("thin.png", png(2100, 100))], "límites"),
         ("a photo over 10 MB", ["borrador", "x", "--foto", put("huge.jpg", jpeg(pad=11 * 1048576))], "MB"),
         ("a video given as --foto", ["borrador", "x", "--foto", put("v2.mp4", mp4())], "contenido"),
         ("a photo given as --video", ["borrador", "x", "--video", put("p2.jpg", jpeg())], "contenido"),
         ("both a photo and a video", ["borrador", "x", "--foto", p_jpg, "--video", put("v3.mp4", mp4())], "no los dos"),
         ("a file that does not exist", ["borrador", "x", "--foto", os.path.join(tmp, "nope.jpg")], "No encuentro"),
         ("a directory", ["borrador", "x", "--foto", tmp], "No encuentro")]
for name, argv, word in cases:
    rc, out = run(*argv)
    check(f"media refused: {name}", rc == 2 and word in out and not ST["calls"])
canal.VIDEO_MAX = 1000
rc, out = run("borrador", "x", "--video", put("v4.mp4", mp4(pad=2000)))
canal.VIDEO_MAX = 50 * 1024 * 1024
check("a video over the cap is refused", rc == 2 and "MB" in out and not ST["calls"])
rc, out = run("borrador", "", "--foto", put("ok.png", png()))
check("a photo may go without caption", rc == 0 and ST["calls"][0][0] == "sendPhoto" and "caption" not in ST["calls"][0][1])

# ------------------------------------------------------------------------------------------------ text rules
reset_calls()
rc, out = run("borrador", "a" * 4097)
check("4097 characters: refused", rc == 2 and "4096" in out and not ST["calls"])
rc, out = run("borrador", "a" * 4096)
check("4096 characters: accepted", rc == 0)
reset_calls()
rc, out = run("borrador", "😀" * 2100)
check("length is counted in UTF-16 units (2100 emoji are 4200)", rc == 2 and not ST["calls"])
rc, out = run("borrador", "a" * 1025, "--foto", p_jpg)
check("with media the text is a caption of at most 1024", rc == 2 and "1024" in out and not ST["calls"])
rc, out = run("borrador", "")
check("an empty text is refused", rc == 2 and "Falta el texto" in out)
for name, text, word in (("a key shape", "mi clave ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8", "clave"),
                         ("a bot token shape", "token " + "123456789:" + "A" * 35, "clave"),
                         ("a local path", "mirá /workdir/descargas/foto.jpg", "ruta"),
                         ("a private address", "entrá a http://10.20.30.40:8080/panel", "privada"),
                         ("localhost", "http://localhost:3000/x", "privada"),
                         ("an internal name", "https://nas.internal/x", "privada")):
    reset_calls()
    rc, out = run("borrador", text)
    check(f"text refused: {name}", rc == 2 and word in out and not ST["calls"] and ("ghp_" not in out))
reset_calls()
rc, out = run("borrador", "Ofertas en https://www.example.com/promo")
check("a public link is fine", rc == 0)
reset_calls()
rc, out = run("borrador", "ocu​lto 👨‍👩‍👧 ‮RTL")
sent_txt = ST["calls"][0][1]["text"] if ST["calls"] else ""
check("hidden characters are stripped from the stored and shown text", "​" not in sent_txt and "‮" not in sent_txt and "👨‍👩‍👧" in sent_txt)
reset_calls()
rc, out = run("borrador", "-", stdin="Texto por stdin con \"comillas\"\ny dos líneas")
check("text can come from stdin (`-`)", rc == 0 and ST["calls"][0][1]["text"] == "Texto por stdin con \"comillas\"\ny dos líneas")

# ------------------------------------------------------------------------------------------------ caps
canal.PREVIEWS_PER_DAY = canal.previews_today() + 1
reset_calls()
rc, out = run("borrador", "uno más")
rc2, out2 = run("borrador", "uno más todavía")
check("a daily cap on approval messages sent to the owner", rc == 0 and rc2 == 2 and "hoy" in out2)
canal.PREVIEWS_PER_DAY = 10 ** 6
canal.OPEN_MAX = canal.open_count()
rc, out = run("borrador", "uno más")
check("a cap on open drafts", rc == 2 and "esperando" in out)
canal.OPEN_MAX = 10 ** 6

# ------------------------------------------------------------------------------------------------ the schedule
tz = canal.load_conf()["tz"]
from zoneinfo import ZoneInfo
def local(ep):
    return datetime.datetime.fromtimestamp(ep, ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M")
now = time.time()
rc, out = run("borrador", "Para programar")
sid = int(re.search(r"borrador (\d+)", out).group(1))
reset_calls()
check("programar less than 60 minutes ahead is refused", run("programar", str(sid), local(now + 600))[0] == 2 and not ST["calls"])
check("programar with a bad date or in the past is refused", run("programar", str(sid), "mañana a las 5")[0] == 2 and run("programar", str(sid), "2020-01-01 10:00")[0] == 2)
check("programar more than 60 days ahead is refused", run("programar", str(sid), local(now + 61 * 86400))[0] == 2)
when_s = local(now + 3 * 3600)
T = int(datetime.datetime.strptime(when_s, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz)).timestamp())
rc, out = run("programar", str(sid), when_s)
code_s = code_of(sid)
check("programar asks the owner to approve 'publish at T' and schedules nothing yet", rc == 0 and code_s and "NO está programado" in out and not rec(sid).get("scheduled") and not to(CHANNEL)
      and when_s in ST["calls"][-1][1]["text"])
check("a wrong code does not schedule", "no corresponde" in canal.approve(sid, "DDDDDDDDDD", sender=OWNER) and not rec(sid).get("scheduled"))
open(cron_calls, "w").close()
ans = canal.approve(sid, code_s, sender=OWNER)
check("the owner's press stores 'publish at T' and posts nothing now", rec(sid)["scheduled"]["when"] == T and rec(sid)["state"] == "draft" and not to(CHANNEL) and "Programado" in ans and when_s in ans)
check("the cron job is resumed while something is scheduled", "cron resume canal" in open(cron_calls).read())
reset_calls()
check("due before T publishes nothing", canal.due(now=T - 60) == [] and not to(CHANNEL))
rc, out = run("lista")
check("lista shows the schedule", "programado " + when_s in out)
lines = canal.due(now=T + 30)
check("due at T publishes the owner-approved draft and reports the link", len(to(CHANNEL)) == 1 and to(CHANNEL)[0][1]["text"] == "Para programar" and len(lines) == 1 and "https://t.me/TestChannel/" in lines[0])
check("the record is published and the schedule is gone; the cron is paused again", rec(sid)["state"] == "published" and not rec(sid).get("scheduled") and open(cron_calls).read().strip().endswith("cron pause canal"))
check("a second due publishes nothing more", canal.due(now=T + 90) == [] and len(to(CHANNEL)) == 1)
# a draft with a pending schedule that nobody approved is not published
rc, out = run("borrador", "Sin aprobar")
uid = int(re.search(r"borrador (\d+)", out).group(1))
run("programar", str(uid), when_s)
reset_calls()
check("a schedule nobody approved is never published", canal.due(now=T + 30) == [] and not to(CHANNEL))
# stale
rc, out = run("borrador", "Se pasó")
stid = int(re.search(r"borrador (\d+)", out).group(1))
run("programar", str(stid), when_s)
canal.approve(stid, code_of(stid), sender=OWNER)
reset_calls()
lines = canal.due(now=T + canal.STALE + 120)
check("a post later than the stale limit is not published and the owner is told", not to(CHANNEL) and len(lines) == 1 and "venció" in lines[0] and rec(stid)["state"] == "draft" and not rec(stid).get("scheduled"))
# changed after approval
rc, out = run("borrador", "Original")
chid = int(re.search(r"borrador (\d+)", out).group(1))
run("programar", str(chid), when_s)
canal.approve(chid, code_of(chid), sender=OWNER)
rr = rec(chid)
rr["text"] = "Cambiado"
open(os.path.join(canal.ROOT, f"{chid}.json"), "w").write(json.dumps(rr))
reset_calls()
lines = canal.due(now=T + 30)
check("a draft that changed after its schedule was approved is not published", not to(CHANNEL) and len(lines) == 1 and "cambió" in lines[0])
# failures
rc, out = run("borrador", "Falla")
fid = int(re.search(r"borrador (\d+)", out).group(1))
run("programar", str(fid), when_s)
canal.approve(fid, code_of(fid), sender=OWNER)
reset_calls()
ST["fail"] = {"method": "sendMessage", "kind": "400", "chat": CHANNEL}
l1 = canal.due(now=T + 30)
check("a clear refusal: the owner hears it and it is tried again next round", "rechazó" in l1[0] and rec(fid).get("scheduled") and rec(fid)["scheduled"]["tries"] == 1)
canal.due(now=T + 60)
l3 = canal.due(now=T + 90)
check("after three refusals it gives up and says so", "Dejé de intentar" in l3[0] and not rec(fid).get("scheduled") and rec(fid)["state"] == "draft" and len(to(CHANNEL)) == 3)
ST["fail"] = None
rc, out = run("borrador", "Duda")
did = int(re.search(r"borrador (\d+)", out).group(1))
run("programar", str(did), when_s)
canal.approve(did, code_of(did), sender=OWNER)
reset_calls()
ST["fail"] = {"method": "sendMessage", "kind": "drop", "chat": CHANNEL, "once": True}
l1 = canal.due(now=T + 30)
n_sent = len(to(CHANNEL))
check("a dropped connection on a scheduled post: doubt is reported, no automatic second try", "No sé si" in l1[0] and canal.due(now=T + 60) == [] and len(to(CHANNEL)) == n_sent and rec(did).get("inflight"))
# cancel a schedule
rc, out = run("borrador", "Para cancelar")
kid = int(re.search(r"borrador (\d+)", out).group(1))
run("programar", str(kid), when_s)
canal.approve(kid, code_of(kid), sender=OWNER)
open(cron_calls, "w").close()
check("the owner cancels a scheduled draft with `no`", "Cancelado" in canal.approve(kid, "no") and rec(kid)["state"] == "discarded" and not rec(kid).get("scheduled"))
reset_calls()
check("a cancelled schedule is never published", [l for l in canal.due(now=T + 30) if f"borrador {kid} " in l] == [] and not [c for c in to(CHANNEL) if c[1].get("text") == "Para cancelar"])
rc, out = run("borrador", "El modelo descarta")
mid = int(re.search(r"borrador (\d+)", out).group(1))
run("programar", str(mid), when_s)
canal.approve(mid, code_of(mid), sender=OWNER)
rc, out = run("descartar", str(mid))
check("the model may discard a scheduled draft (the safe direction)", rc == 0 and rec(mid)["state"] == "discarded" and not rec(mid).get("scheduled"))
sh = open(os.path.join(HERE, "start_hermes.sh")).read()
# a schedule written by hand (a file write is all it takes) is never published
def forge(text, mac):
    rc, out = run("borrador", text)
    fid_ = int(re.search(r"borrador (\d+)", out).group(1))
    rr_ = rec(fid_)
    rr_["pending"] = None
    rr_["scheduled"] = {"when": T - 3600, "approved": T - 7200, "bind": mac(rr_), "tries": 0}
    open(os.path.join(canal.ROOT, f"{fid_}.json"), "w").write(json.dumps(rr_))
    return fid_
assert os.path.isfile(canal.KEY_PATH) and not canal.KEY_PATH.startswith(canal.ROOT)
for label, mac in (("the plain SHA-256 of the record fields", lambda r_: canal.bind_of(r_, "schedule", T - 3600).hex()),
                   ("a MAC made with a guessed key", lambda r_: __import__("hmac").new(b"x" * 32, canal.bind_of(r_, "schedule", T - 3600), "sha256").hexdigest()),
                   ("a non-string bind", lambda r_: 12345)):
    reset_calls()
    gid = forge("Texto forjado " + label, mac)
    rc, out = run("descartar", str(forge("Otro para reanudar", mac)))   # a model-side call that runs after_schedule_change, as the finding did
    lines = canal.due(now=T + 30)
    check(f"a hand-written schedule with {label} is NOT published, the owner is told", not to(CHANNEL) and any(f"borrador {gid} " in l and "cambió" in l for l in lines) and not rec(gid).get("scheduled"))
reset_calls()
gid = forge("Sin clave", lambda r_: "0" * 64)
keep = canal.KEY_PATH + ".away"
os.replace(canal.KEY_PATH, keep)
lines = canal.due(now=T + 30)
check("with no key file nothing scheduled is published (and due never creates a key)", not to(CHANNEL) and not os.path.exists(canal.KEY_PATH) and any("cambió" in l for l in lines))
os.replace(keep, canal.KEY_PATH)
# approving a schedule too late: the 60-minute lead is checked again at approval
rc, out = run("borrador", "Aprobado tarde")
lid = int(re.search(r"borrador (\d+)", out).group(1))
run("programar", str(lid), when_s)
cl = code_of(lid)
reset_calls()
old_lead, canal.MIN_LEAD = canal.MIN_LEAD, 4 * 3600
ans = canal.approve(lid, cl, sender=OWNER)
canal.MIN_LEAD = old_lead
check("approving a schedule that no longer has the 60-minute lead is refused with a clear sentence, nothing scheduled or posted", "60 minutos" in ans and not rec(lid).get("scheduled") and not rec(lid).get("pending") and not to(CHANNEL)
      and rec(lid)["state"] == "draft")
check("... and the same code cannot be used again", "no corresponde" in canal.approve(lid, cl, sender=OWNER))
canal.approve(lid, "no")
# a 5xx on a scheduled post is "unsure": no automatic second try
rc, out = run("borrador", "Programado con 502")
bid = int(re.search(r"borrador (\d+)", out).group(1))
run("programar", str(bid), when_s)
canal.approve(bid, code_of(bid), sender=OWNER)
reset_calls()
ST["fail"] = {"method": "sendMessage", "kind": "502", "chat": CHANNEL, "once": True}
l1 = canal.due(now=T + 30)
n_sent = len(to(CHANNEL))
check("a 502 on a scheduled post: doubt reported, no automatic second try", "No sé si" in l1[0] and canal.due(now=T + 60) == [] and len(to(CHANNEL)) == n_sent and rec(bid).get("inflight"))
canal.approve(bid, "no")
# boot: a recreated stack has the cron job paused while a schedule is waiting
rc, out = run("borrador", "Esperando el reinicio")
wid = int(re.search(r"borrador (\d+)", out).group(1))
run("programar", str(wid), when_s)
canal.approve(wid, code_of(wid), sender=OWNER)
open(cron_calls, "w").close()
canal.after_schedule_change()
check("the boot sync step resumes the cron job when an approved schedule is waiting", "cron resume canal" in open(cron_calls).read())
canal.approve(wid, "no")
canal.after_schedule_change()
check("... and start_hermes.sh runs it after creating or finding the job", "/usr/local/bin/canal --sync-cron" in sh and sh.index("--name canal --no-agent") < sh.index("canal --sync-cron")
      and '--sync-cron' in open(os.path.join(HERE, "canal.py")).read())
canal.CONF = os.path.join(tmp, "missing.json")
check("due without a channel configured is silent", canal.due(now=T + 30) == [])
canal.CONF = conf_path
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "canal_due.py")], capture_output=True, text=True, timeout=60)
check("the cron script runs and, on a stack with no channel, prints nothing", r.returncode == 0 and r.stdout == "")

# ------------------------------------------------------------------------------------------------ language of the owner's messages
open(canal.PREFS, "w").write(json.dumps({"lang": "ru"}))
reset_calls()
rc, out = run("borrador", "Привет, канал")
check("the owner's messages follow their /idioma (ru)", "Черновик" in ST["calls"][-1][1]["text"] and "/publicar" in ST["calls"][-1][1]["text"])
open(canal.PREFS, "w").write(json.dumps({"lang": "en"}))
rc, out = run("borrador", "Hello channel")
check("and en", "Draft" in ST["calls"][-1][1]["text"])
os.unlink(canal.PREFS)
check("all three languages carry the same keys", set(canal.TXT["es"]) == set(canal.TXT["en"]) == set(canal.TXT["ru"]))
check("every instruction names the cancel command and the one-time code", all("/publicar {id} no" in canal.TXT[l]["instr_" + k] and "{cmd}" in canal.TXT[l]["instr_" + k] for l in canal.TXT for k in ("publish", "schedule", "edit", "delete")))
mm = canal.entities_code("😀 título 😀\n/publicar 3 ABC", "/publicar 3 ABC")
check("entity offsets count astral characters as two UTF-16 units", mm[0]["offset"] == len("😀 título 😀\n".encode("utf-16-le")) // 2)

# ------------------------------------------------------------------------------------------------ the owner's command in the plugin
plug = load("controls", os.path.join(HERE, "hermes_plugins", "aibridge-controls", "__init__.py"))
reg = {}
import types
plug.register(types.SimpleNamespace(register_command=lambda name, fn, description="", args_hint="": reg.__setitem__(name, fn)))
check("/publicar and /publish are registered", "publicar" in reg and "publish" in reg)
plug._canal = lambda: canal
rc, out = run("borrador", "Por el plugin")
pid = int(re.search(r"borrador (\d+)", out).group(1))
codepl = code_of(pid)
buf = io.StringIO()
h = logging.StreamHandler(buf)
logging.getLogger().addHandler(h)
reset_calls()
bad = reg["publicar"](f"{pid} AAAAAAAAAA")
check("the plugin answers a wrong code with the uniform sentence and posts nothing", "no corresponde" in bad and not to(CHANNEL))
check("the plugin gives the usage when the arguments are wrong", "Uso:" in reg["publicar"]("") and "Uso:" in reg["publish"](f"{pid}") and not to(CHANNEL))
ans = reg["publicar"](f"{pid} {codepl}")
logging.getLogger().removeHandler(h)
check("the owner's /publicar posts, and the reply carries the link", len(to(CHANNEL)) == 1 and "https://t.me/TestChannel/" in ans)
check("the log never carries the code", codepl not in buf.getvalue() and "/publicar" in buf.getvalue())
plug2 = load("controls2", os.path.join(HERE, "hermes_plugins", "aibridge-controls", "__init__.py"))
mod = plug2._canal()
check("the plugin finds canal.py by itself (installed, or next to the repo)", mod is not None and callable(getattr(mod, "approve", None)))
check("the plugin's reply never raises", "No pude" in (lambda: (setattr(plug, "_canal", lambda: (_ for _ in ()).throw(RuntimeError("boom"))), plug.cmd_publicar("1 AAAAAAAAAA"))[1])())

# ------------------------------------------------------------------------------------------------ the token is never printed, logged or stored
blob = open(canal.LOG).read() + "".join(open(os.path.join(canal.ROOT, n), errors="replace").read() for n in os.listdir(canal.ROOT) if os.path.isfile(os.path.join(canal.ROOT, n)))
check("the token is nowhere in the log or in the drafts folder", TOKEN not in blob and TOKEN.split(":")[1] not in blob)
reset_calls()
canal.API_BASE = "http://127.0.0.1:9/bot"          # nothing listens there: the error text must not carry the URL
rc, out = run("borrador", "sin red")
canal.API_BASE = f"http://127.0.0.1:{PORT}/bot"
check("a network failure prints a fixed sentence without the URL or the token", rc == 3 and TOKEN not in out and "127.0.0.1" not in out)
open(os.path.join(hermes_home, ".env"), "w").write("TELEGRAM_ALLOWED_USERS=%s\n" % OWNER)
rc, out = run("borrador", "sin token")
check("without a bot token: refused with a fixed sentence", rc == 3 and "token del bot" in out)
open(os.path.join(hermes_home, ".env"), "w").write(f"TELEGRAM_BOT_TOKEN={TOKEN}\n")
rc, out = run("borrador", "sin dueño")
check("without an owner id: refused, nothing sent", rc == 3 and "dueño" in out)
open(os.path.join(hermes_home, ".env"), "w").write(f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_ALLOWED_USERS={OWNER},{OTHER}\n")
reset_calls()
rc, out = run("borrador", "para el primero de la lista")
check("the owner is the FIRST id of TELEGRAM_ALLOWED_USERS", all(str(f.get("chat_id")) == OWNER for _, f in ST["calls"]) and ST["calls"])

# ------------------------------------------------------------------------------------------------ configuration pass-through, pack, shipped files
sync = load("gateways_sync", os.path.join(HERE, "ops", "gateways_sync.py"))
master = {"hosts": {}, "stacks": {"ok": {"canal": {"chat": "@MyChannel1", "title": " Mi canal ", "tz": "America/Argentina/Buenos_Aires", "token": "SECRET", "x": 1}},
                                  "id": {"canal": {"chat": "-1001234567890", "title": "Canal"}},
                                  "bad1": {"canal": {"chat": "MyChannel", "title": "x"}}, "bad2": {"canal": {"chat": "@MyChannel1"}},
                                  "bad3": {"canal": "yes"}, "bad4": {"canal": {"chat": "@MyChannel1", "title": "x" * 81}},
                                  "bad5": {"canal": {"chat": "@MyChannel1", "title": "a\nb"}}, "none": {}}}
with contextlib.redirect_stdout(io.StringIO()) as noted:
    built = {k: sync.build(master, k) for k in master["stacks"]}
check("gateways_sync passes a valid canal (chat, title, tz) and nothing else", built["ok"]["canal"] == {"chat": "@MyChannel1", "title": "Mi canal", "tz": "America/Argentina/Buenos_Aires"})
check("a numeric channel id is accepted", built["id"]["canal"] == {"chat": "-1001234567890", "title": "Canal"})
check("invalid entries are dropped and said (no chat shape, no title, not a dict, long title, control characters)", all("canal" not in built[k] for k in ("bad1", "bad2", "bad3", "bad4", "bad5", "none")) and noted.getvalue().count("ignored") == 5)
jm = {"hosts": {}, "stacks": {"on": {"job_decide": {"enabled": True, "drop_below": 0.2, "key_env": "MY_GEMINI_KEY", "key": "SECRET"}},
                              "bad": {"job_decide": {"enabled": True, "drop_below": 7, "key_env": "x; rm"}}, "off": {"job_decide": {"enabled": "yes"}}}}
with contextlib.redirect_stdout(io.StringIO()) as noted2:
    jb = {k: sync.build(jm, k) for k in jm["stacks"]}
check("job_decide: passed validated, never a key", jb["on"].get("job_decide") == {"enabled": True, "drop_below": 0.2, "key_env": "MY_GEMINI_KEY"})
check("job_decide: bad values dropped, enabled kept", jb["bad"].get("job_decide") == {"enabled": True})
check("job_decide: not exactly true -> off and said", "job_decide" not in jb["off"] and "job_decide" in noted2.getvalue())
check("the summary shows the title only", "channel Mi canal" in json.dumps(sync.summary(built["ok"])) and "MyChannel1" not in json.dumps(sync.summary(built["ok"])))
addp = load("gateways_add_person", os.path.join(HERE, "ops", "gateways_add_person.py"))
cp = addp.add_person({"stacks": {"a": {"canal": {"chat": "@MyChannel1", "title": "x"}, "gpu": ["h"]}}}, "b", "a")
check("a new person's stack never inherits another person's channel", "canal" not in cp["stacks"]["b"] and cp["stacks"]["b"].get("gpu") == ["h"])
packs = json.load(open(os.path.join(HERE, "skill_packs.json")))["packs"]
check("the pack difusion: title, skill canal, gated on the canal config", packs["difusion"]["title"] == "Difusión: tu canal" and packs["difusion"]["skills"] == ["canal"] and packs["difusion"]["gateway_config"] == "canal")
skill = open(os.path.join(HERE, "SKILL_canal.md"), encoding="utf-8").read()
check("the skill has the frontmatter name canal", re.match(r'---\nname: canal\ndescription: "', skill) is not None)
check("the skill never asks for the code, never claims publication early, and names the limits", "Never ask the person to type, paste, read out or send you the approval code" in skill
      and "Never claim it is published until it is" in skill and "4096" in skill and "1024" in skill and "Postiz" in skill and "gateway tareas" in skill and "never a permission" in skill)
# a 5xx or a non-Telegram body is "unsure", never a refusal: the post may have been made
for kind in ("502", "503json"):
    reset_calls()
    rc, out = run("borrador", f"Duda {kind}")
    xid = int(re.search(r"borrador (\d+)", out).group(1))
    cx = code_of(xid)
    ST["fail"] = {"method": "sendMessage", "kind": kind, "chat": CHANNEL, "once": True}
    ans = canal.approve(xid, cx, sender=OWNER)
    n_x = len(to(CHANNEL))
    check(f"a {kind} answer on a post: unsure, not 'still pending'; marked in flight, code not reusable", "No sé si" in ans and "Sigue pendiente" not in ans and rec(xid).get("inflight")
          and rec(xid)["state"] == "draft" and "no corresponde" in canal.approve(xid, cx, sender=OWNER) and len(to(CHANNEL)) == n_x)
    canal.approve(xid, "no")
reset_calls()
rc, out = run("borrador", "Limite de Telegram")
xid = int(re.search(r"borrador (\d+)", out).group(1))
cx = code_of(xid)
ST["fail"] = {"method": "sendMessage", "kind": "429", "chat": CHANNEL, "once": True}
ans = canal.approve(xid, cx, sender=OWNER)
check("a 429 with Telegram's JSON is a clear refusal: still pending, the code stays", "rechazó" in ans and not rec(xid).get("inflight") and rec(xid)["pending"])
canal.approve(xid, "no")
dock = open(os.path.join(HERE, "Dockerfile.hermes-agent")).read()
check("the Dockerfile installs canal, its cron script and the skill", "COPY canal.py /usr/local/bin/canal\n" in dock and "COPY canal_due.py /root/.hermes/scripts/canal_due.py\n" in dock
      and "COPY SKILL_canal.md /root/.hermes/skills/productivity/canal/SKILL.md\n" in dock and "chmod 755 /usr/local/bin/canal" in dock)
sh = open(os.path.join(HERE, "start_hermes.sh")).read()
check("start_hermes.sh creates the cron job paused, only where a canal block exists", "--name canal --no-agent --script canal_due.py" in sh and "--paused" in sh.split("--name canal")[1].split("\n")[0] + sh.split("--name canal")[1].split("\n")[1])
gw = load("gateway_mod", os.path.join(HERE, "gateway.py"))
gw.CONF = os.path.join(tmp, "missing.json")
with contextlib.redirect_stdout(io.StringIO()) as o:
    rcg = gw.cmd_canal(["lista"])
check("gateway canal answers at once, starting nothing, where no canal is configured", rcg == 3 and "no tiene un canal configurado" in o.getvalue())
gsrc = open(os.path.join(HERE, "gateway.py")).read()
check("gateway.py dispatches `canal` and documents it", '"canal": cmd_canal' in gsrc and "gateway canal borrador" in gsrc)

print()
if fails:
    print(f"{len(fails)} FAILED:", *fails, sep="\n  ")
    sys.exit(1)
print("all canal checks passed")
shutil.rmtree(tmp, ignore_errors=True)
