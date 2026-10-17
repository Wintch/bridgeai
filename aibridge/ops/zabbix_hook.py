#!/usr/bin/env python3
"""Zabbix -> ops bot: the receiver of the webhook media type in ops/zabbix/webhook_media_type.js (design: ops/ZABBIX.md).

  python3 ops/zabbix_hook.py serve                  listen (systemd user unit ops/zabbix-hook.service)
  python3 ops/zabbix_hook.py scope show             what is muted / the only thing let through
  python3 ops/zabbix_hook.py scope only TAG...      only events carrying one of these tags are sent (TAG = key:value, e.g. project:bridgeai)
  python3 ops/zabbix_hook.py scope mute TAG...      add tags to the muted list (mute wins over only)
  python3 ops/zabbix_hook.py scope unmute TAG...    remove tags from the muted list
  python3 ops/zabbix_hook.py scope clear            no restriction

Config (never in git), ~/aibridge/ops/ops.env, next to the ops bot's own keys:
  ZBX_HOOK_TOKEN=...          required; Zabbix sends it in the X-Zabbix-Token header. No token, no start.
  ZBX_HOOK_BIND=host:port     default 127.0.0.1:8660; set the LAN address of this VM when Zabbix runs on another machine
                              (and open that one port to Zabbix's address only).

One POST /event per Zabbix notification: {"event_id", "status": "PROBLEM"|"OK", "name", "severity", "host", "tags": [{"tag", "value"}]}.
A problem becomes notify.alert(key "zbx:<event_id>"), its recovery notify.resolve(same key): the ops bot's outbox, dedupe and
"lasted N min" apply. Zabbix owns the repeats (quiet is effectively infinite here). The event name and host come from Zabbix
and may carry text from a monitored system: they are treated as data (control characters out, length capped, plain text
message, never interpreted). Only the tags project, unit, service and tier are read, with a strict value format; an event
with no `unit` is still sent and says so, so a host missing its tags is visible, not silent.
The scope switch is the cheap, instant one: a muted problem is not sent (journal only) but its recovery always is, if its
problem had been sent. A real maintenance window belongs in Zabbix (tags on the maintenance suppress only those problems).
"""
import hmac, json, os, re, sys, time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import notify  # noqa: E402

SCOPE = os.environ.get("ZBX_SCOPE_FILE", os.path.join(notify.STATE_DIR, "zabbix_scope.json"))
KEYS = ("project", "unit", "service", "tier")
VALUE_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,39}")
TAG_RE = re.compile(r"(%s):([a-z0-9][a-z0-9._-]{0,39})" % "|".join(KEYS))
SEVERITIES = {"not classified": "", "information": "info", "warning": "aviso", "average": "media", "high": "ALTA", "disaster": "CRÍTICA"}
MAX_BODY = 16 * 1024
MAX_PER_MIN = 60
_recent = deque()


def env_conf():
    conf = {}
    try:
        for line in open(notify.ENV_FILE):
            k, sep, v = line.partition("=")
            if sep and not k.lstrip().startswith("#"):
                conf[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return conf


def clean(text, limit):
    """Data from Zabbix into a one-line plain string: no control characters, no newlines, capped."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(text)).strip()[:limit]


def event_tags(raw):
    """{key: value} for the four known keys; anything else, or a value in a bad format, is dropped."""
    out = {}
    for t in raw if isinstance(raw, list) else []:
        if isinstance(t, dict) and t.get("tag") in KEYS and isinstance(t.get("value"), str) and VALUE_RE.fullmatch(t["value"]):
            out.setdefault(t["tag"], t["value"])   # the first one wins: a trigger tag cannot override the host's
    return out


def load_scope():
    try:
        d = json.load(open(SCOPE))
    except (OSError, ValueError):
        d = {}
    return {"only": [t for t in d.get("only", []) if TAG_RE.fullmatch(str(t))],
            "mute": [t for t in d.get("mute", []) if TAG_RE.fullmatch(str(t))]}


def save_scope(d):
    os.makedirs(os.path.dirname(SCOPE), exist_ok=True)
    tmp = SCOPE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, SCOPE)


def in_scope(tags, scope):
    pairs = {f"{k}:{v}" for k, v in tags.items()}
    if pairs & set(scope["mute"]):
        return False
    return not scope["only"] or bool(pairs & set(scope["only"]))


def message(ev, tags):
    sev = SEVERITIES.get(clean(ev.get("severity", ""), 20).lower(), clean(ev.get("severity", ""), 20))
    where = f"{tags.get('project', '?')}/{tags['unit']}" if "unit" in tags else f"{tags.get('project', '?')}/SIN UNIDAD"
    svc = f" {tags['service']}:" if "service" in tags else ""
    return f"[{where}]{svc} {clean(ev.get('name', ''), 200)} (host {clean(ev.get('host', ''), 60)}{', ' + sev if sev else ''})"


def handle(ev, scope=None):
    """-> (http status, result dict). `ev` is the parsed JSON body."""
    if not isinstance(ev, dict) or not re.fullmatch(r"\d{1,20}", str(ev.get("event_id", ""))):
        return 400, {"error": "need event_id (digits)"}
    status = str(ev.get("status", "")).upper()
    if status not in ("PROBLEM", "OK"):
        return 400, {"error": "status must be PROBLEM or OK"}
    tags = event_tags(ev.get("tags"))
    key, text = f"zbx:{ev['event_id']}", message(ev, tags)
    if status == "OK":   # always, whatever the scope: a problem that was sent must be closed
        done = notify.resolve(key, "Resuelto: " + text)
        return 200, {"ok": True, "resolved": bool(done)}
    if not in_scope(tags, scope if scope is not None else load_scope()):
        print(f"zabbix hook: muted {key} {sorted(f'{k}:{v}' for k, v in tags.items())}", flush=True)
        return 200, {"ok": True, "muted": True}
    sent = notify.alert(key, text, quiet=10 ** 9)
    return 200, {"ok": True, "sent": bool(sent)}


class Handler(BaseHTTPRequestHandler):
    token = ""

    def log_message(self, *a):   # no access log: the token is in a header and the names are not for the journal
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/event":
            return self._send(404, {"error": "not found"})
        if not hmac.compare_digest(self.headers.get("X-Zabbix-Token", ""), self.token):
            return self._send(401, {"error": "bad token"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if not 0 < n <= MAX_BODY:
            return self._send(413, {"error": "body size"})
        now = time.time()
        while _recent and now - _recent[0] > 60:
            _recent.popleft()
        if len(_recent) >= MAX_PER_MIN:
            print("zabbix hook: more than 60 events a minute, refusing (Zabbix retries)", flush=True)
            return self._send(429, {"error": "too many"})
        _recent.append(now)
        try:
            ev = json.loads(self.rfile.read(n))
        except ValueError:
            return self._send(400, {"error": "json"})
        try:
            code, body = handle(ev)
        except Exception as e:   # never leak internals to the caller; the journal has the class
            print(f"zabbix hook: failed ({type(e).__name__})", flush=True)
            code, body = 500, {"error": "internal"}
        self._send(code, body)


def serve():
    conf = env_conf()
    if not conf.get("ZBX_HOOK_TOKEN"):
        sys.exit("ZBX_HOOK_TOKEN is not set in " + notify.ENV_FILE + ": refusing to listen without a token")
    host, _, port = conf.get("ZBX_HOOK_BIND", "127.0.0.1:8660").rpartition(":")
    Handler.token = conf["ZBX_HOOK_TOKEN"]
    print(f"zabbix hook: listening on {host}:{port}", flush=True)
    ThreadingHTTPServer((host or "127.0.0.1", int(port)), Handler).serve_forever()


def cmd_scope(args):
    d, what, tags = load_scope(), (args[0] if args else "show"), args[1:]
    bad = [t for t in tags if not TAG_RE.fullmatch(t)]
    if bad:
        sys.exit(f"not a valid tag: {bad} (key:value with key in {', '.join(KEYS)}, value a-z 0-9 . _ -)")
    if what == "only":
        d["only"] = sorted(set(tags))
    elif what == "mute":
        d["mute"] = sorted(set(d["mute"]) | set(tags))
    elif what == "unmute":
        d["mute"] = [t for t in d["mute"] if t not in tags]
    elif what == "clear":
        d = {"only": [], "mute": []}
    elif what != "show":
        sys.exit(__doc__)
    if what != "show":
        save_scope(d)
    print(json.dumps(d))


if __name__ == "__main__":
    if sys.argv[1:2] == ["serve"]:
        serve()
    elif sys.argv[1:2] == ["scope"]:
        cmd_scope(sys.argv[2:])
    else:
        sys.exit(__doc__)
