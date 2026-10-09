#!/usr/bin/env python3
"""Talk with the operator through the ops bot (the same bot as the alerts), so the operator answers from Telegram.

  opschat.py send TEXT        (or the text on stdin) a message to the operator's chat; long text goes in parts
  opschat.py voice FILE [CAPTION]   an audio file (ogg/opus) as a voice note, e.g. TTS samples to choose by ear
  opschat.py read [--wait S]  the operator's new messages since the last read, waiting up to S seconds for one

Only messages from OPS_CHAT_ID are read; anything else sent to the bot is skipped (and never printed).
Voice notes are transcribed with `gateway transcribe --voice` (GPU host first, Groq if none answers); the audio is
deleted right after.
Nothing else polls this bot (notify.py only sends), so getUpdates here never conflicts.
"""
import json, os, subprocess, sys, tempfile, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from notify import _conf  # noqa: E402

OFFSET = os.path.expanduser("~/.local/state/opschat_offset")
HERE = os.path.dirname(os.path.abspath(__file__))
GATEWAY = os.path.join(HERE, "..", "gateway.py")
GW_CONF = os.path.join(HERE, "..", "gateways-hernik", "gateways.json")   # the operator's own STT hosts


def api(method, net=15, **params):
    url = f"https://api.telegram.org/bot{_conf()['OPS_BOT_TOKEN']}/{method}"
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=data, timeout=net) as r:
        return json.load(r)["result"]


def send(text):
    chat = _conf()["OPS_CHAT_ID"]
    while text:
        part, text = text[:4000], text[4000:]
        api("sendMessage", chat_id=chat, text=part, disable_web_page_preview="true")


def voice(path, caption=""):
    boundary = "----ops" + str(int(time.time() * 1000))
    parts = b""
    for k, v in (("chat_id", str(_conf()["OPS_CHAT_ID"])), ("caption", caption)):
        parts += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    parts += (f'--{boundary}\r\nContent-Disposition: form-data; name="voice"; filename="voice.ogg"\r\n'
              f"Content-Type: audio/ogg\r\n\r\n").encode() + open(path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{_conf()['OPS_BOT_TOKEN']}/sendVoice", data=parts,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    urllib.request.urlopen(req, timeout=60).read()


def transcribe(file_id):
    token = _conf()["OPS_BOT_TOKEN"]
    path = api("getFile", file_id=file_id)["file_path"]
    with tempfile.TemporaryDirectory() as d:
        audio, out = os.path.join(d, "voice.ogg"), os.path.join(d, "voice.txt")
        urllib.request.urlretrieve(f"https://api.telegram.org/file/bot{token}/{path}", audio)
        env = dict(os.environ, GATEWAYS_CONFIG=GW_CONF, HERMES_HOME=os.path.join(HERE, ".."),   # its .env: Groq key
                   GATEWAY_LOG=os.path.expanduser("~/.local/state/opschat-gateway.jsonl"))
        r = subprocess.run([sys.executable, GATEWAY, "transcribe", audio, "--voice", "--out", out],
                           env=env, capture_output=True, text=True, timeout=200)
        if r.returncode:
            return f"(audio: no se pudo transcribir: {r.stderr.strip()[-200:]})"
        return open(out).read().strip() + f"  {r.stderr.strip()}"


def read(wait):
    chat = str(_conf()["OPS_CHAT_ID"])
    try:
        offset = int(open(OFFSET).read())
    except (OSError, ValueError):
        offset = 0
    deadline = time.time() + wait
    while True:
        left = max(0, int(deadline - time.time()))
        updates = api("getUpdates", net=min(left, 50) + 15, offset=offset, timeout=min(left, 50))
        got = []
        for u in updates:
            offset = u["update_id"] + 1
            m = u.get("message") or u.get("edited_message") or {}
            if str(m.get("chat", {}).get("id")) != chat:
                continue
            t = time.strftime("%H:%M", time.localtime(m.get("date", 0)))
            if m.get("text"):
                got.append(f"[{t}] {m['text']}")
            elif m.get("voice") or m.get("audio"):
                got.append(f"[{t}] (audio) {transcribe((m.get('voice') or m.get('audio'))['file_id'])}")
            else:
                got.append(f"[{t}] (non-text message)")
        os.makedirs(os.path.dirname(OFFSET), exist_ok=True)
        open(OFFSET, "w").write(str(offset))
        if got or time.time() >= deadline:
            print("\n".join(got) if got else "(no new messages)")
            return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("send", "read", "voice"):
        sys.exit(__doc__)
    if sys.argv[1] == "voice":
        voice(sys.argv[2], " ".join(sys.argv[3:]))
        return 0
    if sys.argv[1] == "send":
        send(" ".join(sys.argv[2:]) if len(sys.argv) > 2 else sys.stdin.read())
        return 0
    wait = int(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 0
    return read(wait)


if __name__ == "__main__":
    sys.exit(main())
