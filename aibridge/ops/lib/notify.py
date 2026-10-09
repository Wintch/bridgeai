#!/usr/bin/env python3
"""Operator alerts: one Telegram bot of its own, sent straight from the host, so no stack has to be awake.

Config (never in git): ~/aibridge/ops/ops.env with OPS_BOT_TOKEN=... and OPS_CHAT_ID=... (the operator's chat).
Without it every alert is still printed (journal), and kept in the outbox until the bot is configured.

  alert(key, text)    a problem. Sent the first time, then at most once per `quiet` seconds while it lasts.
  resolve(key, text)  the problem is gone: "✅ ..." once, only if it had been alerted.
  send(text)          one-off message (daily summary). A failed send waits in the outbox and is retried by the
                      next call (any script), so an outage of Telegram or of the link never loses an alert.

CLI (systemd units, shell scripts):
  notify.py alert KEY TEXT [--quiet S]   notify.py resolve KEY [TEXT]   notify.py send TEXT
  notify.py unit-failed UNIT             (OnFailure= of every unit: unit name + its last log lines)
  notify.py flush                        retry the outbox

Privacy: callers pass stack names, providers, last 4 of a key, counts. Never message text, chat ids or keys.
"""
import fcntl, json, os, socket, subprocess, sys, time, urllib.request

ENV_FILE = os.environ.get("OPS_ENV", os.path.expanduser("~/aibridge/ops/ops.env"))
STATE_DIR = os.path.expanduser("~/.local/state")
STATE = os.path.join(STATE_DIR, "ops_alerts.json")
OUTBOX = os.path.join(STATE_DIR, "ops_outbox.jsonl")
LOCK = os.path.join(STATE_DIR, "ops_alerts.lock")
QUIET_S = 6 * 3600
OUTBOX_MAX = 30
HOST = socket.gethostname()


def _conf():
    conf = {}
    try:
        for line in open(ENV_FILE):
            k, sep, v = line.partition("=")
            if sep and not k.lstrip().startswith("#"):
                conf[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    for k in ("OPS_BOT_TOKEN", "OPS_CHAT_ID"):
        conf[k] = os.environ.get(k, conf.get(k, ""))
    return conf


class _locked:
    def __enter__(self):
        os.makedirs(STATE_DIR, exist_ok=True)
        self.f = open(LOCK, "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def _tg(text):
    conf = _conf()
    if not (conf["OPS_BOT_TOKEN"] and conf["OPS_CHAT_ID"]):
        return False
    req = urllib.request.Request(f"https://api.telegram.org/bot{conf['OPS_BOT_TOKEN']}/sendMessage",
                                 data=json.dumps({"chat_id": conf["OPS_CHAT_ID"], "text": text[:4000],
                                                  "disable_web_page_preview": True}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
        return True
    except Exception as e:  # never print the URL: it carries the token
        print(f"ops notify: telegram send failed ({type(e).__name__})", file=sys.stderr, flush=True)
        return False


def _flush_locked():
    try:
        pending = [json.loads(l) for l in open(OUTBOX) if l.strip()]
    except (OSError, ValueError):
        return
    if not pending:
        return
    dropped = max(0, len(pending) - OUTBOX_MAX)
    pending = pending[-OUTBOX_MAX:]
    if dropped and not _tg(f"[{HOST}] ({dropped} avisos viejos descartados: ver journalctl)"):
        return
    left = []
    for m in pending:
        if left or not _tg(f"(demorado {time.strftime('%d/%m %H:%M', time.localtime(m['ts']))}) " + m["text"]):
            left.append(m)   # keep the order: once one fails, the rest wait too
    tmp = OUTBOX + ".tmp"
    with open(tmp, "w") as f:
        f.writelines(json.dumps(m) + "\n" for m in left)
    os.replace(tmp, OUTBOX)


def _send_locked(text):
    text = f"[{HOST}] {text}"
    print("ops notify:", text, flush=True)
    _flush_locked()
    if _tg(text):
        return True
    with open(OUTBOX, "a") as f:
        f.write(json.dumps({"ts": time.time(), "text": text}) + "\n")
    return False


def _load():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {}


def _save(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, STATE)


def send(text):
    with _locked():
        return _send_locked(text)


def alert(key, text, quiet=QUIET_S):
    """True when it was sent now (new problem, or still there after `quiet` seconds)."""
    with _locked():
        state = _load()
        cur = state.get(key)
        now = time.time()
        if cur and now - cur["last_sent"] < quiet:
            cur["last_seen"] = now
            _save(state)
            return False
        again = f" (sigue desde {time.strftime('%d/%m %H:%M', time.localtime(cur['since']))})" if cur else ""
        _send_locked(f"⚠️ {text}{again}")
        state[key] = {"since": cur["since"] if cur else now, "last_sent": now, "last_seen": now, "text": text[:300]}
        _save(state)
        return True


def resolve(key, text=None):
    with _locked():
        state = _load()
        cur = state.pop(key, None)
        if not cur:
            return False
        mins = int((time.time() - cur["since"]) / 60)
        _send_locked(f"✅ {text or 'Resuelto: ' + cur['text']} (duró {mins} min)")
        _save(state)
        return True


def active(prefix=""):
    """{key: entry} of the alerts that are still open (daily summary, tests)."""
    return {k: v for k, v in _load().items() if k.startswith(prefix)}


def flush():
    with _locked():
        _flush_locked()


def unit_failed(unit):
    r = subprocess.run(["journalctl", "--user", "-u", unit, "-n", "8", "--no-pager", "-o", "cat"],
                       capture_output=True, text=True, timeout=30)
    tail = "\n".join(l[:200] for l in r.stdout.strip().splitlines()[-8:])
    return alert(f"unit:{unit}", f"Falló el servicio {unit}.\n{tail}", quiet=QUIET_S)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, args = argv[1], argv[2:]
    quiet = QUIET_S
    if "--quiet" in args:
        i = args.index("--quiet")
        quiet = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    if cmd == "alert" and len(args) == 2:
        alert(args[0], args[1], quiet)
    elif cmd == "resolve" and args:
        resolve(args[0], args[1] if len(args) > 1 else None)
    elif cmd == "send" and len(args) == 1:
        send(args[0])
    elif cmd == "unit-failed" and len(args) == 1:
        unit_failed(args[0])
    elif cmd == "flush":
        flush()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
