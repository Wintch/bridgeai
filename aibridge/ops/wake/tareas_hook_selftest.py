#!/usr/bin/env python3
"""Offline test of the task receiver (tareas_hook.py) and the run starter (tareas_run.py): no docker, no Gitea, no Hermes.

Run from anywhere:  python3 -I ops/wake/tareas_hook_selftest.py
A fake Gitea (this script, signing with HMAC-SHA256), the real receiver over HTTP on a free port, a fake waker (the same decision as the
real one, waker.task_decision, then the real tareas_run.run_for) and a fake Hermes API server that records what it is asked.
"""
import contextlib
import hashlib
import hmac
import http.client
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = load("tareas_hook", os.path.join(HERE, "tareas_hook.py"))
run = load("tareas_run", os.path.join(HERE, "tareas_run.py"))
waker = load("waker", os.path.join(HERE, "waker.py"))

ok = True


def chk(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what, flush=True)


SECRET = "s3cret-" + "x" * 40
API_KEY = "hk-" + "k" * 30
ORG_SECRET = "org-secret-" + "y" * 36
TITLE = "TITLE-MARKER-7731"
BODYTXT = "BODY-MARKER-9942"
tmp = tempfile.mkdtemp(prefix="tareas-hook-test-")
state = os.path.join(tmp, "state")
os.makedirs(state)
gw = os.path.join(tmp, "gateways.json")
json.dump({"stacks": {
    "news-bot": {"tareas": {"url": "https://g.example", "repo": "Acme/tareas", "me": "bot-news", "peers": ["bot-acct"], "humans": ["owner"]}},
    "acct-bot": {"tareas": {"url": "https://g.example", "repo": "acme/tareas", "me": "bot-acct", "peers": ["bot-news"], "humans": ["owner"]}},
    "other": {"tareas": {"url": "https://g.example", "repo": "zeta/tareas", "me": "bot-other"}},
    # the privilege ladder of MULTI_BOT_TASKS.md section 10: down only (peers), read the neighbours (accept_from)
    "lad-nov": {"tareas": {"url": "https://g.example", "repo": "lad/tareas", "me": "bot-lad-nov", "peers": ["bot-lad-tec"], "accept_from": ["bot-lad-tec"], "humans": ["owner"]}},
    "lad-tec": {"tareas": {"url": "https://g.example", "repo": "lad/tareas", "me": "bot-lad-tec", "peers": ["bot-lad-sys"], "accept_from": ["bot-lad-nov", "bot-lad-sys"], "humans": ["owner"]}},
    "lad-sys": {"tareas": {"url": "https://g.example", "repo": "lad/tareas", "me": "bot-lad-sys", "peers": ["bot-lad-bak"], "accept_from": ["bot-lad-tec", "bot-lad-bak"], "humans": ["owner"]}},
    "lad-bak": {"tareas": {"url": "https://g.example", "repo": "lad/tareas", "me": "bot-lad-bak", "peers": [], "accept_from": ["bot-lad-sys"], "humans": ["owner"]}},
    "lad-m2": {"tareas": {"url": "https://g.example", "repo": "lad/tareas", "me": "bot-lad-m2", "accept_from": ["bot-lad-tec"], "max_cadena": 2, "humans": ["owner"]}},
    "plain": {"gpu": []},
}}, open(gw, "w"))

# ---- fake Hermes API ----
API = {"posts": [], "status": 202}


class FakeAPI(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        API["posts"].append({"path": self.path, "auth": self.headers.get("Authorization"), "body": json.loads(body)})
        code = API["status"] if self.headers.get("Authorization") == "Bearer " + API_KEY else 401
        data = json.dumps({"run_id": "run_1", "status": "started"} if code == 202 else {"error": "no"}).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def fake_get(self):
    API["gets"].append({"path": self.path, "auth": self.headers.get("Authorization")})
    ok_key = self.headers.get("Authorization") == "Bearer " + API_KEY
    code = 200 if ok_key and self.path == "/v1/runs/run_1" and API["run_status"] else 404
    data = json.dumps({"id": "run_1", "status": API["run_status"], "output": API.get("output", "")} if code == 200 else {"error": "no"}).encode()
    self.send_response(code)
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)


FakeAPI.do_GET = fake_get
API.update(gets=[], run_status="running")
api = ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
threading.Thread(target=api.serve_forever, daemon=True).start()
API_URL = f"http://127.0.0.1:{api.server_address[1]}"
run.STATE_DIR = state
RUNLOG = []
run.log = RUNLOG.append   # the real one prints to stdout

# ---- the receiver, over HTTP ----
clock = [1_000_000.0]
cfg = {"secret": SECRET, "secrets": {"acme": ORG_SECRET}}
rcv = hook.Receiver(cfg, state_dir=state, gateways=gw, clock=lambda: clock[0])
hook.STATE_DIR = state
srv = ThreadingHTTPServer(("127.0.0.1", 0), hook.make_handler(rcv))
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]
seq = [0]
LOGS = io.StringIO()


def sign(body, secret=SECRET):
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


PAYLOADS = [0]


def payload(event="issues", action="opened", number=7, assignees=("bot-news",), sender="owner", repo="Acme/tareas", state_="open",
            body=None, comment_user=None, age=0, **extra):
    """A Gitea-like payload stamped `age` seconds before the fake clock. Every call is a different body (a real one differs by its timestamps
    and ids), so tests that send "the same event again" mean it by reusing the raw bytes."""
    PAYLOADS[0] += 1
    issue = {"number": number, "state": state_, "title": TITLE, "body": BODYTXT if body is None else body,
             "assignees": [{"login": a} for a in assignees], "user": {"login": sender}, "updated_at": iso(clock[0] - age), "id": PAYLOADS[0]}
    p = {"action": action, "number": number, "issue": issue, "repository": {"full_name": repo}, "sender": {"login": sender}}
    if event == "issue_comment":
        p["comment"] = {"body": "COMMENT-MARKER-5521", "user": {"login": comment_user or sender}, "created_at": iso(clock[0] - age), "id": PAYLOADS[0]}
        p["is_pull"] = False
    p.update(extra)
    return p


def post(p, event="issues", path="/gitea", sig="auto", delivery=None, raw=None, secret=SECRET):
    body = raw if raw is not None else json.dumps(p).encode()
    seq[0] += 1
    h = {"Content-Type": "application/json", "X-Gitea-Event": event, "X-Gitea-Delivery": delivery or f"d-{seq[0]}"}
    if sig == "auto":
        h["X-Gitea-Signature"] = sign(body, secret)
    elif sig is not None:
        h["X-Gitea-Signature"] = sig
    with contextlib.redirect_stdout(LOGS):
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
        c.request("POST", path, body, h)
        r = c.getresponse()
        code, data = r.status, json.loads(r.read() or b"{}")
        c.close()
    return code, data.get("outcome")


def req_file(stack):
    try:
        return json.load(open(os.path.join(state, f"{stack}.task.json")))
    except OSError:
        return None


def clear():
    for f in os.listdir(state):
        if f.endswith(".task.json") or f.endswith(".task.run.json"):
            os.unlink(os.path.join(state, f))


def fake_waker_tick(stack, brain_up=False, busy=False, now=None):
    """What waker.task_tick does with the request, then (for wake/run) what the 40-task-run hook does. -> (decision, hook exit code or None)."""
    req = req_file(stack)
    d = waker.task_decision(req, now if now is not None else clock[0], 0, False, brain_up, busy, 6 * 3600)
    if d in ("wake", "run"):
        return d, run.run_for(stack, lambda: [API_URL], lambda: API_KEY)
    return d, None


# 1. good signature -> request file -> wake -> exactly one run with the fixed prompt
code, out = post(payload())
chk((code, out) == (200, "kick"), f"good signature on an assignment: 200 kick (got {code} {out})")
r = req_file("news-bot")
chk(r and r["issues"] == [7] and r["repo"] == "acme/tareas" and r["count"] == 1, "request file has repo, issue number and count")
chk(TITLE not in json.dumps(r) and BODYTXT not in json.dumps(r), "request file holds no title or text")
chk(oct(os.stat(os.path.join(state, "news-bot.task.json")).st_mode & 0o777) == "0o600", "request file is mode 600")
d, rc = fake_waker_tick("news-bot", brain_up=False)
chk(d == "wake" and rc == 0, f"brain down -> waker decides wake, hook starts the run (got {d}, rc {rc})")
chk(len(API["posts"]) == 1 and API["posts"][0]["path"] == "/v1/runs" and API["posts"][0]["auth"] == "Bearer " + API_KEY, "ONE POST /v1/runs with the Bearer key")
chk(API["posts"][0]["body"] == {"input": run.PROMPT} and "gateway tareas listar --mias" in run.PROMPT, "the prompt is the fixed one")
chk("todas las pendientes" in run.PROMPT and "hasta que no quede ninguna" in run.PROMPT and "bloqueado" in run.PROMPT and "más vieja" in run.PROMPT,
    "the prompt says to work EVERY pending task, oldest first, until the list is empty (a burst is one request)")
rr = json.load(open(os.path.join(state, "news-bot.task.run.json")))
chk(rr.get("run_id") == "run_1" and isinstance(rr.get("started"), float) and API_KEY not in json.dumps(rr) and TITLE not in json.dumps(rr),
    "an accepted run leaves a run record (id and start time, no key, no text)")
chk(oct(os.stat(os.path.join(state, "news-bot.task.run.json")).st_mode & 0o777) == "0o600", "...mode 600")
clear()
chk(TITLE not in json.dumps(API["posts"][0]) and BODYTXT not in json.dumps(API["posts"][0]), "no issue text reaches the prompt")
chk(req_file("news-bot") is None, "request file removed once the run was accepted")
chk(fake_waker_tick("news-bot")[0] == "none", "nothing left to do afterwards")

# 2. signature checks
clear()
n_before = len(os.listdir(state))
chk(post(payload(), sig="0" * 64)[0] == 401, "wrong signature: 401")
chk(post(payload(), sig=None)[0] == 401, "missing signature: 401")
chk(post(payload(), sig="")[0] == 401, "empty signature: 401")
chk(post(payload(), secret="other-secret")[0] == 401, "signature made with another secret: 401")
body = json.dumps(payload()).encode()
chk(post(None, raw=body, sig=sign(body).upper())[0] == 200, "uppercase hex of a good signature is accepted (same digest)")
clear()
chk(post(payload(), sig="sha256=" + sign(json.dumps(payload()).encode()))[0] == 401, "prefixed digest is not the X-Gitea-Signature format: 401")
chk(req_file("news-bot") is None, "nothing written by the rejected ones")
chk(post(payload(), path="/other")[0] == 404, "wrong path: 404")
empty = hook.Receiver({"secret": "", "secrets": {}}, state_dir=state, gateways=gw, clock=lambda: clock[0])
b = json.dumps(payload()).encode()
with contextlib.redirect_stdout(LOGS):
    e1 = empty.handle("/gitea", {"X-Gitea-Signature": hmac.new(b"", b, hashlib.sha256).hexdigest(), "X-Gitea-Event": "issues"}, b)[0]
    e2 = empty.handle("/gitea", {"X-Gitea-Signature": "", "X-Gitea-Event": "issues"}, b)[0]
chk(e1 == 401 and e2 == 401, "empty configured secret never validates (not even the HMAC under an empty key)")
chk(post(payload(), path="/gitea/acme", secret=ORG_SECRET)[1] == "kick", "org path: that org's secret works")
clear()
chk(post(payload(), path="/gitea/acme")[0] == 401 and post(payload(), path="/gitea/nope", secret=ORG_SECRET)[0] == 401,
    "org path: the global secret and an unknown org do not")
cfgfile = os.path.join(tmp, "c.json")
open(cfgfile, "w").write(json.dumps({"secret": SECRET}))
os.chmod(cfgfile, 0o644)
try:
    hook.load_config(cfgfile)
    chk(False, "config readable by others is refused")
except SystemExit as e:
    chk("600" in str(e), "config readable by others is refused")
os.chmod(cfgfile, 0o600)
chk(hook.load_config(cfgfile)["secret"] == SECRET, "mode 600 config loads")
open(cfgfile, "w").write(json.dumps({"secret": ""}))
try:
    hook.load_config(cfgfile)
    chk(False, "config with no secret is refused")
except SystemExit as e:
    chk("no secret" in str(e), "config with no secret is refused")
for bad in ("short", "x" * 31, "<long random string, also pasted in the Gitea webhook form>"):
    open(cfgfile, "w").write(json.dumps({"secret": bad}))
    try:
        hook.load_config(cfgfile)
        chk(False, f"weak secret refused ({bad[:12]!r})")
    except SystemExit as e:
        chk("32 characters" in str(e), f"weak secret refused ({bad[:12]!r}): too short or the placeholder")
open(cfgfile, "w").write(json.dumps({"secret": SECRET, "secrets": {"acme": "short"}}))
try:
    hook.load_config(cfgfile)
    chk(False, "a weak per-org secret is refused")
except SystemExit as e:
    chk("32 characters" in str(e), "a weak per-org secret is refused too")
open(cfgfile, "w").write(json.dumps({"secret": "k" * 32}))
chk(hook.load_config(cfgfile)["secret"] == "k" * 32, "a 32 character secret is accepted")
ex = os.path.join(tmp, "example.json")
open(ex, "w").write(open(os.path.join(HERE, "tareas_hook.json.example")).read())
os.chmod(ex, 0o600)
try:
    hook.load_config(ex)
    chk(False, "an unedited copy of the example config is refused")
except SystemExit as e:
    chk("placeholder" in str(e), "an unedited copy of the example config does not start (the placeholder is not a secret)")

# 3. size cap
clear()
big = b'{"x":"' + b"a" * (hook.MAX_BODY + 10) + b'"}'
chk(post(None, raw=big)[0] == 413, "body over 64 KB: 413")
chk(req_file("news-bot") is None, "oversized body wrote nothing")

# 4. event / action / repo / state / assignee filters
clear()
chk(post(payload(), event="push")[1] == "ignored-event", "event push ignored")
chk(post(payload(action="closed", state_="closed"))[1] == "ignored-author", "issues/closed of a task a PERSON filed: nobody to wake (ignored-author)")
chk(post(payload(action="closed"))[1] == "ignored-state", "issues/closed whose payload still says open: ignored")
chk(post(payload(action="edited"))[1] == "ignored-event", "issues/edited ignored")
chk(post(payload(action="unassigned"))[1] == "ignored-event", "issues/unassigned ignored")
chk(post(payload(event="issue_comment", action="edited"), event="issue_comment")[1] == "ignored-event", "issue_comment/edited ignored")
chk(post(payload(repo="evil/tareas"))[1] == "ignored-repo", "repo that no stack configured ignored")
chk(post(payload(repo="Acme/other"))[1] == "ignored-repo", "another repo of the same org ignored")
chk(post(payload(repo="zeta/tareas"))[1] == "ignored-assignee", "configured repo but the assignee is not its bot: ignored")
chk(post(payload(state_="closed"))[1] == "ignored-state", "closed issue ignored")
pr = payload()
pr["issue"]["pull_request"] = {"merged": False}
chk(post(pr)[1] == "ignored-state", "pull request ignored")
chk(post(payload(assignees=("owner",)))[1] == "ignored-assignee", "human assignee ignored")
chk(post(payload(assignees=("somebody-else",)))[1] == "ignored-assignee", "unknown assignee ignored")
chk(post(payload(assignees=()))[1] == "ignored-assignee", "no assignee ignored")
chk(post(payload(event="issue_comment", action="created", is_pull=True), event="issue_comment")[1] == "ignored-event", "comment on a pull request ignored")
chk(post(None, raw=b"[1,2]")[0] == 400 and post(None, raw=b"not json")[0] == 400, "signed but not a JSON object: 400, nothing written")
chk(all(req_file(s) is None for s in ("news-bot", "acct-bot", "other")), "none of those wrote a request")
a = payload(assignees=("owner", "bot-acct"))
chk(post(a)[1] == "kick" and req_file("acct-bot") and req_file("news-bot") is None, "human + bot assignees: only the bot's stack is kicked")
clear()
one = payload(assignees=("BOT-News",))
chk(post(one)[1] == "kick" and req_file("news-bot"), "assignee login is matched case-insensitively")
clear()
fb = payload()
fb["issue"].pop("assignees")
fb["issue"]["assignee"] = {"login": "bot-news"}
chk(post(fb)[1] == "kick", "single `assignee` field is read when `assignees` is missing")
clear()

# 5. comments
chk(post(payload(event="issue_comment", action="created", sender="bot-news", comment_user="bot-news"), event="issue_comment")[1] == "ignored-self",
    "a comment by the assignee bot itself is ignored")
chk(req_file("news-bot") is None, "...and wrote nothing")
chk(post(payload(event="issue_comment", action="created", sender="owner", comment_user="owner"), event="issue_comment")[1] == "kick",
    "a comment by the person on an open task assigned to the bot wakes it")
clear()
chk(post(payload(event="issue_comment", action="created", sender="bot-news", comment_user="bot-acct",
                 body="<!-- tareas:v1 -->\npedido-por: bot-news\npara: bot-news\nsalto: 0\ncadena: bot-news\n\n---\n\nnote"), event="issue_comment")[1] == "kick",
    "a comment by another bot (author from comment.user, not sender) wakes the assignee")
clear()
chk(post(payload(action="assigned", sender="bot-news"))[1] == "ignored-self", "the bot assigning a task to itself does not wake it")
chk(post(payload(action="assigned", sender="owner"))[1] == "kick", "assigned by the person: kick")
clear()
chk(post(payload(action="reopened"))[1] == "kick", "reopened: kick")
clear()

# 6. duplicate delivery, burst coalescing, rate limit
chk(post(payload(number=1), delivery="same-id")[1] == "kick", "first delivery of an id: kick")
chk(post(payload(number=1), delivery="same-id")[1] == "duplicate", "same delivery id again: duplicate, nothing done")
chk(req_file("news-bot")["count"] == 1, "...and the count did not move")
clock[0] += 3600
chk(post(payload(number=1), delivery="same-id")[1] == "duplicate", "still a duplicate an hour later (24 h memory)")
clear()
rcv2 = hook.Receiver(cfg, state_dir=state, gateways=gw, clock=lambda: clock[0])
chk("same-id" in rcv2.seen, "delivery ids survive a restart (state file)")
chk(oct(os.stat(rcv.state_file).st_mode & 0o777) == "0o600", "receiver state file is mode 600")
clock[0] += 25 * 3600
chk(post(payload(number=1), delivery="same-id")[1] == "kick", "after 24 h the id is forgotten")
clear()
API["posts"].clear()
rcv.kicks.clear()
clock[0] += 3 * 3600
for n in (11, 12, 13):
    post(payload(number=n))
r = req_file("news-bot")
chk(r and r["issues"] == [11, 12, 13] and r["count"] == 3, f"burst of 3 tasks -> ONE request listing the 3 issues (got {r and r['issues']})")
fake_waker_tick("news-bot")
chk(len(API["posts"]) == 1, "...and ONE run")
t0 = clock[0]
clock[0] += 30
post(payload(number=14))
r = req_file("news-bot")
chk(r and r["not_before"] >= t0 + hook.RATE_S - 1, "a task 30 s after the kick: new request, not before the 2 minute mark")
chk(fake_waker_tick("news-bot", now=clock[0])[0] == "wait", "...and the waker waits for it")
chk(fake_waker_tick("news-bot", now=t0 + hook.RATE_S + 1)[0] == "wake" and len(API["posts"]) == 2, "...then wakes and runs once more")
clear()

# 6c. replay protection: the delivery id is not under the HMAC, the body is
clear()
rcv.kicks.clear()
clock[0] += 3 * 3600
raw = json.dumps(payload(number=71)).encode()
chk(post(None, raw=raw, delivery="rp-1")[1] == "kick", "a signed body: kick")
chk(post(None, raw=raw, delivery="rp-2")[1] == "duplicate", "the same signed body under ANOTHER delivery id: duplicate (the id is not covered by the signature)")
chk(post(None, raw=raw, delivery="-")[1] == "duplicate", "the same signed body with no usable delivery id: duplicate")
chk(req_file("news-bot")["count"] == 1, "...none of them woke the bot again")
clear()
chk(post(None, raw=raw, delivery="rp-3")[1] == "duplicate" and req_file("news-bot") is None, "even after the request was consumed, a replay writes nothing")
rcv3 = hook.Receiver(cfg, state_dir=state, gateways=gw, clock=lambda: clock[0])
chk("b:" + hashlib.sha256(raw).hexdigest() in rcv3.seen, "body hashes survive a restart (state file)")
with contextlib.redirect_stdout(LOGS):
    again = rcv3.handle("/gitea", {"X-Gitea-Signature": sign(raw), "X-Gitea-Event": "issues", "X-Gitea-Delivery": "rp-5"}, raw)[1]
chk(again == "duplicate", "...and a restarted receiver still refuses the replay")
clock[0] += 25 * 3600
chk(post(None, raw=raw, delivery="rp-4")[1] == "stale-payload" and req_file("news-bot") is None,
    "after the 24 h memory the body hash is forgotten, but its own timestamp is older than 24 h: refused as stale")
old_comment = json.dumps(payload(event="issue_comment", action="created", number=72, age=26 * 3600)).encode()
chk(post(None, raw=old_comment, event="issue_comment")[1] == "stale-payload", "a comment payload is judged by comment.created_at")
chk(post(payload(number=73, age=23 * 3600))[1] == "kick", "a payload 23 h old is still accepted (once)")
clear()
nostamp = payload(number=74)
del nostamp["issue"]["updated_at"]
chk(post(nostamp)[1] == "kick", "a payload without a timestamp is judged by the body hash alone")
clear()

# 6b. a request the waker would drop as stale is not extended: a new one starts afresh
clear()
json.dump({"stack": "news-bot", "repo": "acme/tareas", "issues": [1], "count": 1, "first_ts": clock[0] - 7 * 3600, "not_before": 0},
          open(os.path.join(state, "news-bot.task.json"), "w"))
post(payload(number=61))
r = req_file("news-bot")
chk(r and r["issues"] == [61] and r["first_ts"] == clock[0], "a stale pending request is replaced, not merged")
clear()

# 7. the chain rule (MULTI_BOT_TASKS.md section 10.3): who may wake a bot, depth, cycles, malformed headers
rcv.kicks.clear()
clock[0] += 3600


def hdr(salto, cadena=None, by="bot-news", para="bot-acct", extra=""):
    lines = [f"pedido-por: {by}", f"para: {para}", f"salto: {salto}"] + ([f"cadena: {cadena}"] if cadena is not None else []) + ([extra] if extra else []) + ["fecha: 2026-11-09"]
    return "<!-- tareas:v1 -->\n" + "\n".join(lines) + "\n\n---\n\nsome text"


def wakes(n, body, sender="bot-news", assignee="bot-acct", repo="Acme/tareas", user=None, event="issues", **kw):
    """The outcome of one delivery for issue n; the request file is cleared afterwards so the next one is judged alone."""
    pl = payload(event=event, number=n, assignees=(assignee,), sender=sender, body=body, repo=repo, **kw)
    if user is not None:
        pl["issue"]["user"] = {"login": user}
    out = post(pl, event=event)[1]
    clear()
    return out


chk(wakes(22, hdr(1, "bot-news > bot-acct")) == "kick", "a task a peer bot filed (salto 1, chain ends with the assignee): wakes")
chk(wakes(23, hdr(1, "bot-news > bot-acct"), sender="owner", user="bot-news") == "kick", "...also when the person (a human) reassigns it")
chk(wakes(24, hdr(0, "bot-acct"), sender="owner") == "kick", "a person's own task (salto 0): wakes")
chk(wakes(25, "plain text typed in the web page", sender="owner") == "kick", "a task with no header (typed in the web page): depth 0, wakes")
chk(wakes(26, hdr(1, "bot-news > bot-acct"), sender="some-admin") == "not-accepted", "an actor outside the assignee's accept_from and humans: not woken")
chk(wakes(27, hdr(1, "bot-news > bot-acct"), sender="owner", user="some-admin") == "not-accepted", "an issue AUTHORED outside accept_from (the gateway would hide it): not woken, whoever acts on it")
chk(wakes(28, hdr(1, "bot-news > bot-acct"), sender="owner", user="") == "not-accepted", "an issue with no author in the payload: fail closed")
chk(wakes(29, hdr(1, "bot-news > bot-acct"), sender="bot-other") == "not-accepted", "a bot that is not in accept_from (here a bot of another repo's list): not woken")
chk(req_file("acct-bot") is None, "...and no request was written for any refused task")

# depth: at the maximum wakes (it may act, it cannot start anything further); above it does not
chk(wakes(30, hdr(3, "a1 > a2 > bot-news > bot-acct")) == "kick", "salto 3 (the default maximum): wakes")
chk(wakes(31, hdr(4, "a1 > a2 > a3 > bot-news > bot-acct")) == "chain-ignored", "salto 4, above the default maximum 3: not woken")
chk(wakes(32, hdr(4)) == "chain-ignored", "salto 4 with no chain (old format): not woken")
chk(wakes(33, hdr(1)) == "kick", "old format (salto 1, no cadena): depth enforced, wakes")
chk(wakes(34, hdr(0)) == "kick", "old format salto 0: wakes")

# cycles: the assignee already EARLIER in the chain
chk(wakes(35, hdr(1, "bot-acct > bot-news")) == "chain-ignored", "the assignee earlier in the chain (not the last): not woken")
chk(wakes(36, hdr(2, "BOT-ACCT > a2 > bot-news")) == "chain-ignored", "...with any capitalisation")

# malformed or forged headers fail closed, and only the first block counts
for label, b in (("salto that is not a number", hdr("dos", "bot-news > bot-acct")), ("negative salto", hdr(-1, "bot-acct")),
                 ("salto and chain disagree", hdr(0, "bot-news > bot-acct")), ("salto missing", hdr("", None).replace("salto: \n", "")),
                 ("empty link", hdr(1, "bot-news >  > bot-acct")), ("salto written twice", hdr(0, "bot-acct", extra="salto: 0")),
                 ("a cycle inside the chain", hdr(2, "bot-acct > bot-news > Bot-Acct")), ("unreadable desde", hdr(1, "bot-news > bot-acct", extra="desde: lo anterior"))):
    chk(wakes(40, b) == "chain-ignored", f"malformed header ({label}): not woken (fail closed)")
chk(wakes(41, "text\n" + hdr(4, "a1 > a2 > a3 > bot-news > bot-acct"), sender="owner") == "kick", "a header that is not the first block does not count (a person's task: depth 0, wakes)")
chk(wakes(43, "text\n" + hdr(0, "bot-acct")) == "chain-ignored", "a bot's task with no header at the start (a forged one further down does not count): not woken")
chk(wakes(44, "no header at all") == "chain-ignored", "a bot's task with no header at all: not woken (the honest tool always writes one)")
chk(wakes(45, "no header at all", sender="owner") == "kick", "...but a person's task with no header wakes (depth 0)")
chk(wakes(46, "no header at all", sender="owner", user="bot-news") == "chain-ignored", "...and a bot-authored task a person reassigned does not get depth 0 either")
for label, b in (("marker with no separator", "<!-- tareas:v1 -->\nsalto: 0\ncadena: bot-acct\n\ntext"), ("leading space", " " + hdr(0, "bot-acct")),
                 ("leading newline", "\n" + hdr(0, "bot-acct")), ("BOM", "\ufeff" + hdr(0, "bot-acct")), ("wrong-case keys", "<!-- tareas:v1 -->\nSalto: 0\nCadena: bot-acct\n\n---\n\nx"),
                 ("misspelled keys", "<!-- tareas:v1 -->\nsaltos: 0\ncadenas: bot-acct\n\n---\n\nx"), ("empty block", "<!-- tareas:v1 -->\n\n---\n\nx"),
                 ("marker later on the first line", "see <!-- tareas:v1 -->\nsalto: 0\n\n---\n\nx")):
    for who in ("bot-news", "owner"):
        chk(wakes(47, b, sender=who) == "chain-ignored", f"attempted but unreadable header ({label}), filed by {who}: not woken (fail closed, not depth 0)")
chk(wakes(42, hdr("dos", "bot-acct") + "\n<!-- tareas:v1 -->\nsalto: 0\ncadena: bot-acct\n\n---\n\nx") == "chain-ignored", "a good-looking second block after a bad first one does not rescue it")

# the ladder, rung by rung (repo lad/tareas), and what is two rungs away
L = "Lad/tareas"
chk(wakes(50, hdr(1, "bot-lad-nov > bot-lad-tec", by="bot-lad-nov", para="bot-lad-tec"), sender="bot-lad-nov", assignee="bot-lad-tec", repo=L) == "kick", "ladder: novedades -> tecnico (salto 1): wakes tecnico")
chk(wakes(51, hdr(2, "bot-lad-nov > bot-lad-tec > bot-lad-sys", by="bot-lad-tec", para="bot-lad-sys"), sender="bot-lad-tec", assignee="bot-lad-sys", repo=L) == "kick", "ladder: tecnico -> sysadmin (salto 2): wakes sysadmin")
chk(wakes(52, hdr(3, "bot-lad-nov > bot-lad-tec > bot-lad-sys > bot-lad-bak", by="bot-lad-sys", para="bot-lad-bak"), sender="bot-lad-sys", assignee="bot-lad-bak", repo=L) == "kick", "ladder: sysadmin -> backupbot (salto 3, the maximum): wakes backupbot")
chk(wakes(53, hdr(1, "bot-lad-nov > bot-lad-bak", by="bot-lad-nov", para="bot-lad-bak"), sender="bot-lad-nov", assignee="bot-lad-bak", repo=L) == "not-accepted", "ladder: a task from novedades straight to backupbot (two rungs away): not woken")
chk(wakes(54, hdr(2, "bot-lad-nov > bot-lad-tec > bot-lad-sys", by="bot-lad-tec", para="bot-lad-sys"), sender="bot-lad-nov", assignee="bot-lad-sys", repo=L, user="bot-lad-tec",
          event="issue_comment", action="created", comment_user="bot-lad-nov") == "not-accepted", "ladder: a comment by a bot two rungs away on a task held by sysadmin: not woken")
chk(wakes(59, hdr(2, "bot-lad-nov > bot-lad-tec > bot-lad-sys", by="bot-lad-tec", para="bot-lad-sys"), sender="bot-lad-nov", assignee="bot-lad-sys", repo=L, user="bot-lad-tec",
          event="issue_comment", action="created", comment_user="bot-lad-bak") == "kick", "ladder: ...and a comment by a neighbour on the same task wakes it")
chk(wakes(55, hdr(2, "bot-lad-nov > bot-lad-tec > bot-lad-sys", by="bot-lad-tec", para="bot-lad-sys"), sender="bot-lad-bak", assignee="bot-lad-sys", repo=L, user="bot-lad-tec") == "kick", "ladder: the result coming back from backupbot (a neighbour) wakes sysadmin")
chk(wakes(56, hdr(2, "bot-lad-nov > bot-lad-tec > bot-lad-sys", by="bot-lad-tec", para="bot-lad-nov"), sender="bot-lad-tec", assignee="bot-lad-nov", repo=L, user="bot-lad-tec") == "chain-ignored", "ladder: a task sent back UP to a bot already in the chain: not woken")
chk(wakes(57, hdr(3, "bot-lad-nov > bot-lad-tec > bot-lad-sys > bot-lad-m2", by="bot-lad-sys", para="bot-lad-m2"), sender="bot-lad-tec", assignee="bot-lad-m2", repo=L, user="bot-lad-tec") == "chain-ignored", "a stack with max_cadena 2: salto 3 is above its maximum")
chk(wakes(58, hdr(2, "bot-lad-nov > bot-lad-tec > bot-lad-m2", by="bot-lad-tec", para="bot-lad-m2"), sender="bot-lad-tec", assignee="bot-lad-m2", repo=L, user="bot-lad-tec") == "kick", "...and salto 2 is at it: wakes")

# the receiver and tareas.py read the same: source text, fixtures and the config of a stack
import inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import tareas
chk(all(inspect.getsource(getattr(hook, n)) == inspect.getsource(getattr(tareas, n)) for n in ("names", "clamp_cadena", "parse_body", "chain_info")),
    "the receiver's names, clamp_cadena, parse_body and chain_info are the same source text as tareas.py's")
chk(hook.HEADER_KEYS == tareas.HEADER_KEYS and hook.USER_RE.pattern == tareas.USER_RE.pattern and hook.NUM_RE.pattern == tareas.NUM_RE.pattern
    and (hook.DEFAULT_MAX_CADENA, hook.MAX_CADENA_CLAMP) == (tareas.DEFAULT_MAX_CADENA, tareas.MAX_CADENA_CLAMP) and hook.MARK == tareas.MARK, "...and so are their constants")
FIX = [hdr(1, "bot-news > bot-acct"), hdr(0, "bot-acct"), hdr(0), hdr(1), hdr(3), hdr(4), hdr(9), hdr(2, "a > b > c"), hdr(3, "a > b > c > d"), hdr(4, "a > b > c > d > e"), hdr(5, "a>b>c>d>e>f"),
       hdr("dos"), hdr(-1), hdr("", None).replace("salto: \n", ""), hdr(1, "bot-news >  > bot-acct"), hdr(0, "x", extra="salto: 0"), hdr(2, "a > b > A"), hdr(1, "a > b", extra="desde: #12"),
       hdr(1, "a > b", extra="desde: 12"), hdr(1, "a > b", extra="desde: x"), hdr(1, "a > b", extra="cadena: a > b"), hdr(1, "a > b", extra="desde: #1\ndesde: #2"),
       "text\n" + hdr(1, "a > b"), hdr(1, "a > b").replace("\n---\n", "\n"), hdr(1, "a > b").replace("\n", "\r\n"), hdr(1, "a > b") + "\n" + hdr(0, "x"),
       "<!-- tareas:v1 -->\nsalto: 1\n", "<!-- tareas:v1 -->\nsalto: x\n\n---\n\nt", " " + hdr(1, "a > b"), "\n" + hdr(1, "a > b"), "\ufeff" + hdr(1, "a > b"),
       "<!-- tareas:v1 -->\nSalto: 1\nCadena: a > b\n\n---\n\nt", "<!-- tareas:v1 -->\nsaltos: 1\n\n---\n\nt", "<!-- tareas:v1 -->\n\n---\n\nt", "see <!-- tareas:v1 -->\nsalto: 0\n\n---\n\nt", "plain", "", None, hdr(1, "bot ok > bad name"), hdr(1, "a > " + "b" * 50), hdr("١", "a"), hdr(1000, "a")]
chk(all(hook.parse_body(b) == tareas.parse_body(b) and all(hook.chain_info(hook.parse_body(b)[0], m) == tareas.chain_info(tareas.parse_body(b)[0], m) for m in range(1, 6)) for b in FIX),
    f"parse_body and chain_info give the same answer on {len(FIX)} header fixtures at every maximum")
ATTEMPTED = [" " + hdr(1, "a > b"), "\n" + hdr(1, "a > b"), "\ufeff" + hdr(1, "a > b"), "<!-- tareas:v1 -->\nSalto: 1\nCadena: a > b\n\n---\n\nt", "<!-- tareas:v1 -->\nsaltos: 1\n\n---\n\nt",
             "<!-- tareas:v1 -->\n\n---\n\nt", "see <!-- tareas:v1 -->\nsalto: 0\n\n---\n\nt", "<!-- tareas:v1 -->\nsalto: 1\ncadena: a > b\n\ntext"]
chk(all(tareas.chain_info(tareas.parse_body(b)[0], 3)["present"] and tareas.chain_info(tareas.parse_body(b)[0], 3)["bad"] for b in ATTEMPTED),
    "attempted-but-unreadable headers (blanks or BOM before the marker, wrong-case or misspelled keys, an empty block, no separator) are present and bad, never 'no header'")
chk(sum(1 for b in FIX if tareas.chain_info(tareas.parse_body(b)[0], 3)["bad"]) >= 10, "...and the fixtures include many malformed ones (they were not all trivially good)")
# may_act (receiver) against what the gateway would let the bot do: a task the receiver wakes for is one the gateway shows and does not count as unreadable
rules = hook.load_rules(gw)
agree = True
for b in FIX:
    for assignee, repo in (("bot-acct", "acme/tareas"), ("bot-lad-m2", "lad/tareas"), ("bot-lad-tec", "lad/tareas")):
        rule = rules[repo][assignee]
        info = tareas.chain_info(tareas.parse_body(b)[0], rule["max"])
        gateway_ok = not (info["bad"] or info["over"]) and not (info["cadena"] and assignee in [c.lower() for c in info["cadena"][:-1]])
        agree &= hook.may_act(rule, assignee, "owner", "owner", b)[0] == gateway_ok
chk(agree, "may_act wakes exactly for the tasks tareas.chain_info reads as usable (readable, within the maximum, assignee not earlier in the chain)")
tareas.CONF = os.path.join(tmp, "tareas-conf.json")
os.environ["GITEA_TAREAS_TOKEN"], os.environ["HERMES_HOME"] = "faketoken", os.path.join(tmp, "nohome")
blocks = [{"peers": ["bot-b"], "humans": ["h1"]}, {"peers": ["bot-b"], "accept_from": ["bot-c", "bad name", 7], "humans": ["h1"]}, {"peers": ["bot-b"], "accept_from": []},
          {"peers": ["bot-b"], "accept_from": "bot-c"}, {"peers": ["bot-b", "ME"], "accept_from": ["me", "bot-c"], "max_cadena": 9}, {"max_cadena": 0}, {"max_cadena": "2"},
          {"max_cadena": 2}, {"max_cadena": True}, {"max_cadena": 2.0}, {"max_cadena": -1}]
same_cfg = True
for blk in blocks:
    full = dict({"url": "https://g.example", "repo": "Z/tareas", "me": "ME", "peers": [], "humans": []}, **blk)
    json.dump({"tareas": full}, open(tareas.CONF, "w"))
    g = tareas.load_conf()
    json.dump({"stacks": {"zed": {"tareas": full}}}, open(os.path.join(tmp, "gw-one.json"), "w"))
    r = hook.load_rules(os.path.join(tmp, "gw-one.json"))["z/tareas"]["me"]
    same_cfg &= r["max"] == g["max_cadena"] and r["accept"] == {x.lower() for x in g["accept_from"] + g["humans"]}
chk(same_cfg, "load_rules reads accept_from (default peers; a non-list means nobody; humans always) and max_cadena (default 3, clamp 1..5) exactly as tareas.load_conf does")

# 8. run starter failures
clear()
post(payload(number=31))
API["status"] = 500
API["posts"].clear()
rc = run.run_for("news-bot", lambda: [API_URL], lambda: API_KEY)
r = req_file("news-bot")
chk(rc == 1 and r and r["attempts"] == 1 and r["not_before"] > time.time() + 200, "API error: exit 1, request kept with a later not_before")
rc = run.run_for("news-bot", lambda: [API_URL], lambda: API_KEY)
rc2 = run.run_for("news-bot", lambda: [API_URL], lambda: API_KEY)
chk(rc == 1 and rc2 == 2 and req_file("news-bot") is None, "third failure: exit 2 and the request is dropped")
API["status"] = 202
post(payload(number=32))
chk(run.run_for("news-bot", lambda: [API_URL], lambda: "wrong-key") in (1,) and req_file("news-bot")["attempts"] == 1, "a rejected key is a failure, not a started run")
chk(run.run_for("news-bot", lambda: [API_URL], lambda: "") == 1, "no key found: failure")
clear()
chk(run.run_for("news-bot", lambda: [API_URL], lambda: API_KEY) == 0, "no request: exit 0, nothing started")
# a task added while the run starts is kept
post(payload(number=41))
real_start = run.start_run


def racing(urls, key, prompt=run.PROMPT):
    post(payload(number=42))   # arrives during the API call
    return real_start(urls, key, prompt)


run.start_run = racing
rc = run.run_for("news-bot", lambda: [API_URL], lambda: API_KEY)
run.start_run = real_start
r = req_file("news-bot")
chk(rc == 0 and r and 42 in r["issues"], "a task that joined while the run was starting is kept for another run")
clear()

# 8b. an uncaught crash of the starter counts as a failed try (the waker's own cap is tested in tareas_waker_selftest.py)
clear()
post(payload(number=95))
real_run_for = run.run_for


def boom(*a, **k):
    raise KeyError("stacks.json has no such stack")


run.run_for = boom
os.environ["TAREAS_RUN_TEST_URL"] = API_URL
codes = [run.main(["--stack", "news-bot"]) for _ in range(3)]
run.run_for = real_run_for
chk(codes == [1, 1, 2] and req_file("news-bot") is None, f"a crashing starter: exit 1, 1, then 2 and the request is dropped (got {codes})")
post(payload(number=96))
run.run_for = boom
run.main(["--stack", "news-bot"])
run.run_for = real_run_for
chk(req_file("news-bot")["attempts"] == 1 and req_file("news-bot")["not_before"] > time.time() + 200, "...the crash was recorded in the request file with a later not_before")
del os.environ["TAREAS_RUN_TEST_URL"]
chk("stacks.json has no such" not in "\n".join(RUNLOG), "...and the exception text is not logged, only its class")
clear()

# 8c. is the recorded run still going? (waker -> `tareas_run.py --check`)
recf = os.path.join(state, "news-bot.task.run.json")
json.dump({"stack": "news-bot", "run_id": "run_1", "started": time.time()}, open(recf, "w"))
getw = lambda: run.check_run("news-bot", lambda: [API_URL], lambda: API_KEY)
res = {}
for st in ("running", "in_progress", "completed", "failed", "cancelled", "weird"):
    API["run_status"] = st
    res[st] = getw()
chk(res == {"running": "running", "in_progress": "running", "completed": "finished", "failed": "finished", "cancelled": "finished", "weird": "unknown"},
    f"run status words: running/finished, anything unknown is 'unknown' (got {res})")
chk(any(g["path"] == "/v1/runs/run_1" and g["auth"] == "Bearer " + API_KEY for g in API["gets"]), "the status call is GET /v1/runs/<id> with the Bearer key")
chk(run.check_run("news-bot", lambda: [API_URL], lambda: "wrong") == "unknown" and run.check_run("news-bot", lambda: [], lambda: API_KEY) == "unknown",
    "a rejected key or no address: unknown")
json.dump({"stack": "news-bot", "run_id": "../x", "started": time.time()}, open(recf, "w"))
chk(getw() == "unknown", "a run id that is not a plain token is never put in a URL")
json.dump({"stack": "news-bot", "run_id": "", "started": time.time()}, open(recf, "w"))
chk(getw() == "unknown", "a record with no run id: unknown")
os.unlink(recf)
chk(getw() == "unknown", "no record: unknown")
json.dump({"stack": "news-bot", "run_id": "run_1", "started": time.time()}, open(recf, "w"))
API["run_status"] = "completed"
env = dict(os.environ, WAKE_STATE_DIR=state, TAREAS_RUN_TEST_URL=API_URL, TAREAS_RUN_TEST_KEY=API_KEY, WAKE_CONFIG=os.path.join(tmp, "none.json"))
p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "tareas_run.py"), "--stack", "news-bot", "--check"], env=env, capture_output=True, text=True)
chk(p.returncode == 0 and p.stdout.strip().splitlines()[-1] == "finished" and API_KEY not in p.stdout + p.stderr, "CLI --check prints the word on its last line, never the key")
env2 = dict(env, TAREAS_RUN_TEST_URL="")
env2.pop("TAREAS_RUN_TEST_KEY")
p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "tareas_run.py"), "--stack", "news-bot", "--check"], env=env2, capture_output=True, text=True)
chk(p.returncode == 0 and p.stdout.strip().splitlines()[-1] == "unknown", "CLI --check with an unusable config (crash inside) still answers 'unknown', exit 0")
API["run_status"] = "running"
clear()

# 9. the CLI as the hook runs it: key never printed
post(payload(number=51))
env = dict(os.environ, WAKE_STATE_DIR=state, TAREAS_RUN_TEST_URL=API_URL, TAREAS_RUN_TEST_KEY=API_KEY, WAKE_CONFIG=os.path.join(tmp, "none.json"))
p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "tareas_run.py"), "--stack", "news-bot"], env=env, capture_output=True, text=True)
chk(p.returncode == 0 and "run started" in p.stdout, f"tareas_run CLI: exit 0 (got {p.returncode} {p.stderr[-200:]})")
chk(API_KEY not in p.stdout + p.stderr, "tareas_run output never contains the key")
post(payload(number=52))
API["status"] = 401
p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "tareas_run.py"), "--stack", "news-bot"], env=env, capture_output=True, text=True)
chk(p.returncode == 1 and API_KEY not in p.stdout + p.stderr, "tareas_run CLI on an API error: exit 1, still no key in the output")
API["status"] = 202
clear()
hookscript = os.path.join(HERE, "on_wake.d", "40-task-run")
p = subprocess.run([hookscript], env=dict(os.environ, WAKE_REASON="telegram", WAKE_NAME="news-bot", HOME=tmp), capture_output=True, text=True)
chk(p.returncode == 0 and os.access(hookscript, os.X_OK), "40-task-run does nothing for other wake reasons (exit 0) and is executable")
p = subprocess.run(["sh", "-c", 'WAKE_REASON=task; WAKE_NAME=x; . "$0" 2>/dev/null; true', os.path.join(HERE, "on_wake.d", "10-key-check")], capture_output=True, text=True)
chk('"task"' in open(os.path.join(HERE, "on_wake.d", "10-key-check")).read(), "10-key-check treats a task wake like a cron wake (no --wake notice)")
ad = open(os.path.join(HERE, "on_wake.d", "30-daily-ad")).read()
chk('"telegram"' in ad and "WAKE_CHAT_ID" in ad, "30-daily-ad only fires for a Telegram wake with a chat (never for a task)")

# 9b. the result goes back to the bot that filed the task (closed, or left bloqueado); a comment or another state never does
clear()
def back(n, kind="closed", closer="bot-acct", author="bot-news", assignees=("bot-acct",), state_=None, event=None, labels=("estado/bloqueado",), raw=None):
    if kind == "closed":
        pl = payload(action="closed", number=n, assignees=assignees, sender=closer, state_=state_ or "closed")
        ev = event or "issues"
    else:
        pl = payload(action="label_updated", number=n, assignees=assignees, sender=closer, state_=state_ or "open")
        pl["issue"]["labels"] = [{"name": x} for x in labels]
        ev = event or "issue_label"
    pl["issue"]["user"] = {"login": author}
    return post(pl, event=ev, raw=raw)[1], pl
out, pl = back(61)
r = req_file("news-bot")
chk(out == "kick" and r and r["issues"] == [] and r["done"] == [{"n": 61, "by": "bot-acct", "kind": "closed"}],
    f"the assignee closes a task bot-news filed: bot-news gets a request with it under done (got {out}, {r})")
chk(TITLE not in json.dumps(r) and BODYTXT not in json.dumps(r), "...and the request holds no title or text")
chk(run.prompt_for(r) == run.DONE_PROMPT.format(nums="#61") and run.PROMPT not in run.prompt_for(r), "a done-only request gets the result prompt, not the work prompt")
d, rc = fake_waker_tick("news-bot", brain_up=False, now=r["not_before"] + 1)   # past the 2-minute rate limit of earlier kicks
chk(d == "wake" and rc == 0 and API["posts"][-1]["body"] == {"input": run.DONE_PROMPT.format(nums="#61")}, f"the run starts with the result prompt (got {d}, {rc})")
clear()
chk(back(62, closer="bot-news")[0] == "ignored-self", "the author closing its own task wakes nobody")
chk(back(63, closer="bot-other", assignees=("bot-other",))[0] == "not-accepted", "a closer outside the author's peers, accept_from and humans: not woken")
chk(back(64, closer="bot-acct", assignees=("bot-news",))[0] == "not-accepted", "a closer who is not an assignee of the task: not woken")
chk(back(65, closer="owner", assignees=("owner",))[0] == "kick", "the person closes a task the bot filed for the person: the bot hears the result")
clear()
chk(back(66, kind="bloqueado")[0] == "kick" and req_file("news-bot")["done"][0]["kind"] == "bloqueado", "the assignee sets estado/bloqueado: the author is woken (kind bloqueado)")
clear()
chk(back(67, kind="bloqueado", labels=("estado/en-curso",))[0] == "ignored-event", "estado/en-curso (or any other label) wakes nobody")
chk(back(68, kind="bloqueado", event="issues")[0] == "kick", "a label change sent as event issues/label_updated works the same")
clear()
chk(back(69, kind="bloqueado", state_="closed")[0] == "ignored-state", "bloqueado on a closed task: ignored")
chk(back(70)[0] == "kick" and back(70)[0] == "already-told", "the same task closed again (reopened, closed) within 24 h: told once (already-told)")
clear()
out1, pl = back(71)
raw = json.dumps(pl).encode()
chk(post(pl, event="issues", raw=raw)[1] == "duplicate", "a replayed close is a duplicate")
clear()
pc = payload(event="issue_comment", action="created", number=72, assignees=("bot-acct",), sender="bot-acct")
pc["issue"]["user"] = {"login": "bot-news"}
chk(post(pc, event="issue_comment")[1] != "kick" and req_file("news-bot") is None, "a comment by the assignee does not wake the author (no back-and-forth)")
clear()
out, _ = back(73)
post(payload(number=74))   # a new task for bot-news while the result is pending: one request, both parts
r = req_file("news-bot")
chk(r["issues"] == [74] and [x["n"] for x in r["done"]] == [73], "a result and a new task coalesce into one request")
pr = run.prompt_for(r)
chk(pr.startswith(run.PROMPT) and run.DONE_PROMPT.format(nums="#73") in pr, "...and that run gets both prompts")
chk(run.prompt_for({"done": [{"n": "1; rm -rf /"}, {"n": True}, {"n": 5}]}) == run.DONE_PROMPT.format(nums="#5"), "only integer issue numbers reach the prompt")
clear()
# the waker's line to the person: fixed text, number and closer only, once per task and kind
notes = waker.done_notices({"first_ts": 1, "done": [{"n": 61, "by": "bot-acct", "kind": "closed"}, {"n": 66, "by": "bot-acct", "kind": "bloqueado"},
                                                    {"n": 9, "by": "<script>", "kind": "closed"}, {"n": 8, "by": "x", "kind": "otro"}]}, "es", set())
chk([t for _, t in notes] == [waker.DONE_NOTICE["es"]["closed"].format(by="bot-acct", n=61), waker.DONE_NOTICE["es"]["bloqueado"].format(by="bot-acct", n=66)],
    "the person gets one fixed line per result (a bad login or kind is skipped)")
chk(waker.done_notices({"first_ts": 1, "done": [{"n": 61, "by": "bot-acct", "kind": "closed"}]}, "es", {k for k, _ in notes}) == [], "...and never twice for the same request")
chk(waker.done_notices({"first_ts": 1, "done": [{"n": 61, "by": "bot-acct", "kind": "closed"}]}, "ru", set())[0][1].startswith("🔔 bot-acct закрыл"), "...in the stack's language")

# 9c. polling: the same rules, fed by reading Gitea with a read-only token (no webhook needed)
clear()
POLL_TOKEN = "polltok" + "Z" * 30
FG = {"issues": [], "timeline": {}, "status": 200, "urls": []}
def fake_fetch(url):
    FG["urls"].append(url)
    if FG["status"] != 200:
        return FG["status"], None
    if "/repos/acme/tareas/" not in url:
        return 200, []   # the other boards of the fixture have nothing new
    if "/timeline" in url:
        n = int(url.split("/issues/")[1].split("/")[0])
        return 200, FG["timeline"].get(n, [])
    return 200, FG["issues"]
def gissue(n, assignee="bot-acct", author="bot-news", state_="open", labels=(), body=None):
    return {"number": n, "state": state_, "title": TITLE, "user": {"login": author},
            "assignees": [{"login": assignee}], "labels": [{"name": x} for x in labels], "updated_at": iso(clock[0] - 5),
            "body": hdr(1, f"{author} > {assignee}", by=author, para=assignee) if body is None else body}
def item(i, kind, user, age=5, **kw):
    return dict({"id": i, "type": kind, "user": {"login": user}, "created_at": iso(clock[0] - age)}, **kw)
poller = hook.Poller(rcv, POLL_TOKEN, state_dir=state, clock=lambda: clock[0], fetch=fake_fetch)
FG["issues"] = [gissue(81)]
FG["timeline"] = {81: [item(9001, "assignees", "bot-news")]}
outs = poller.tick()
chk(outs == ["kick"] and req_file("acct-bot")["issues"] == [81], f"poll: an assignment read from the timeline wakes the assignee (got {outs})")
chk(all(POLL_TOKEN not in u for u in FG["urls"]) and any("/repos/acme/tareas/issues?state=all" in u for u in FG["urls"]), "poll: the token is never in a URL; it reads the board repo")
chk(poller.tick() == ["duplicate"], "poll: the same timeline item read again is a duplicate (no second kick)")
clear()
FG["issues"] = [gissue(82, state_="closed")]
FG["timeline"] = {82: [item(9002, "close", "bot-acct")]}
chk(poller.tick() == ["kick"] and req_file("news-bot")["done"][0]["n"] == 82, "poll: a close by the assignee goes back to the author (done)")
clear()
FG["issues"] = [gissue(83)]
FG["timeline"] = {83: [item(9003, "comment", "bot-acct"), item(9004, "label", "bot-acct"), item(9005, "assignees", "bot-news", age=99999)]}
chk(poller.tick() == ["ignored-self", "ignored-event"] and req_file("acct-bot") is None,
    "poll: the assignee's own comment wakes nobody, a label that is not bloqueado wakes nobody, an item older than the cursor is skipped")
FG["issues"] = [gissue(84, labels=("estado/bloqueado",))]
FG["timeline"] = {84: [item(9006, "label", "bot-acct")]}
chk(poller.tick() == ["kick"] and req_file("news-bot")["done"][0]["kind"] == "bloqueado", "poll: bloqueado set by the assignee goes back to the author")
clear()
before = dict(poller.cursor)
FG["status"] = 500
chk(poller.tick() == [] and poller.cursor == before, "poll: Gitea answering 500 advances nothing (next tick reads the same window)")
FG["status"] = 200
st_text = open(os.path.join(state, "tareas_poll.state.json")).read()
chk(POLL_TOKEN not in st_text and TITLE not in st_text and oct(os.stat(os.path.join(state, "tareas_poll.state.json")).st_mode & 0o777) == "0o600",
    "poll: the cursor file holds no token or text and is mode 600")
fresh = hook.Poller(rcv, POLL_TOKEN, state_dir=state, clock=lambda: clock[0], fetch=fake_fetch)
chk(fresh.cursor.get("acme/tareas") == poller.cursor.get("acme/tareas"), "poll: the cursor survives a restart")
clear()

# 9d. the finished run's own answer goes to the person (a board run has no chat of its own)
API["run_status"], API["output"] = "completed", "Listo: revisé la #2.\nMEDIA:/workdir/descargas/placa-final.png\n¿Avanzo?"
st_, out_ = run.run_report([API_URL], API_KEY, "run_1")
chk(st_ == "completed" and out_.startswith("Listo"), f"run_report reads status and output of a finished run (got {st_!r})")
chk(run.report_text(out_) == "Listo: revisé la #2.\n(adjunto: placa-final.png)\n¿Avanzo?", "report_text: a MEDIA line becomes (adjunto: name), no server path")
chk(len(run.report_text("x" * 9000)) <= 3502 and run.report_text("x" * 9000).endswith("…"), "report_text: a long answer is cut to one Telegram message")
chk(run.run_report([API_URL], "wrong-key", "run_1") == ("", "") and run.run_report([API_URL], API_KEY, "bad id!") == ("", ""), "run_report: a wrong key or a bad id gives nothing")
json.dump({"stack": "news-bot", "run_id": "run_1", "started": time.time()}, open(os.path.join(state, "news-bot.task.run.json"), "w"))
p_ = subprocess.run([sys.executable, "-I", os.path.join(HERE, "tareas_run.py"), "--stack", "news-bot", "--report"],
                    env=dict(os.environ, WAKE_STATE_DIR=state, TAREAS_RUN_TEST_URL=API_URL, TAREAS_RUN_TEST_KEY=API_KEY), capture_output=True, text=True)
rep_ = json.loads(p_.stdout.strip().splitlines()[-1])
chk(p_.returncode == 0 and rep_["status"] == "completed" and "(adjunto: placa-final.png)" in rep_["text"] and API_KEY not in p_.stdout + p_.stderr,
    "tareas_run --report prints {status, text} for the recorded run, never the key")
API["run_status"], API["output"] = "running", ""
os.unlink(os.path.join(state, "news-bot.task.run.json"))

# 10. logs: metadata only
text = LOGS.getvalue()
lines = [json.loads(l) for l in text.splitlines() if l.strip()]
chk(lines and all(set(l) <= {"ts", "stack", "issue", "action", "outcome", "error", "bind", "repos", "via", "polling"} for l in lines), f"every log line is JSON with metadata fields only ({len(lines)} lines)")
text += "\n".join(RUNLOG)
chk(RUNLOG and all(m not in text for m in (TITLE, BODYTXT, "COMMENT-MARKER-5521", SECRET, ORG_SECRET, API_KEY, "wrong-key", POLL_TOKEN)), "logs (receiver and run starter) hold no title, body, comment, secret or key")
chk(any(l.get("stack") == "news-bot" and l.get("issue") == 7 and l.get("outcome") == "kick" for l in lines), "a kick line names stack, issue number, action and outcome")
chk(any(l.get("outcome") == "bad-signature" and "stack" not in l for l in lines), "an unsigned request is logged without any content")

srv.shutdown()
api.shutdown()
print("ALL OK" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
