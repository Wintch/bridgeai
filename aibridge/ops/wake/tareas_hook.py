#!/usr/bin/env python3
"""Gitea webhook -> wake request: the receiver that lets a task on the board wake a sleeping bot (design: MULTI_BOT_TASKS.md section 4,
operator steps: ops/wake/TAREAS_HOOK.md).

  python3 ops/wake/tareas_hook.py serve        listen (systemd user unit ops/wake/aibridge-tareas-hook.service)

What it does with one delivery, in this order (the first failing check ends it, and the answer says only that):
  1. POST /gitea (or /gitea/<org>, which only picks the secret) with a body of at most 64 KB;
  2. X-Gitea-Signature must be the hex HMAC-SHA256 of the RAW body with the secret, compared in constant time, BEFORE anything is parsed.
     No signature, an empty one or a wrong one is 401 and nothing else happens; a receiver with no secret does not start;
  3. only X-Gitea-Event "issues" (action opened, assigned, reopened) and "issue_comment" (action created), only for an open issue (not a
     pull request) of a repo some stack has in its gateways.json "tareas" block;
  4. each assignee is mapped to a stack by that block's "me" (ops/gateways.json, the private master, read fresh). Humans and unknown
     accounts are ignored; so is an action done by the bot itself (a bot's own comment or assignment never wakes it);
  5. the chain rule (MULTI_BOT_TASKS.md section 10.3, the same one `gateway tareas` applies): a task wakes its assignee only when that bot may
     act on it. The actor (who assigned or commented) and the issue's author must each be the bot itself, a human or an account of the
     assignee's `accept_from` (the "tareas" block of that stack, default `peers`); the header's depth must be readable and not above the
     owner's `max_cadena` (default 3, 1..5); and the assignee must not already be EARLIER in the header's `cadena` (no cycles). Anything
     else is not woken for (outcomes `not-accepted`, `chain-ignored`) and stays on the board, where the bot finds it with its next
     `gateway tareas listar` (the gateway hides what is outside `accept_from` as well). A header that cannot be read does not wake: the
     gateway would count it as the maximum depth, here a bot that cannot start anything further is not woken either (fail closed). The
     header is parsed by a COPY of tareas.py's parse_body / chain_info (this host does not get tareas.py); the selftest compares the
     source text and the results of both on the same fixtures. The receiver cannot tell a task a bot filed on its own from one a person
     asked for: depth is whatever the header says, and the header is the gateway's discipline, not a wall (the token can edit an issue);
  6. replay protection, two keys, both kept 24 h (and across restarts): the delivery id (X-Gitea-Delivery) and the SHA-256 of the raw body.
     The delivery id is NOT covered by the HMAC, so the body hash is the real guard: a captured signed body re-sent with another or no id
     is still a duplicate. A payload whose own timestamp (comment.created_at, else issue.updated_at) is older than 24 h is refused as
     stale, so a replay cannot outlive the memory either;
  6b. the result goes back: "issues" action "closed", and a label change ("issue_label" or "issues", action
     "label_updated") that leaves the task with estado/bloqueado, wake the bot that FILED the task, so it reads the result and goes on with
     its part. Only when the one who closed or blocked it is an assignee of the task and someone the author filed for or reads from (its
     peers, accept_from or humans), and never the author's own action. A comment or another state wakes nobody that way, so two bots cannot
     wake each other back and forth; and one issue tells its author at most once per kind (closed, bloqueado) per 24 h. The request file
     carries it under "done" ({"n", "by", "kind"}: the number, the closer's login, the kind; never a text): tareas_run.py gives that run its
     own fixed prompt, and the waker sends the person one fixed line through the author's bot;
  7. rate limit and coalescing: a stack gets at most one kick per 2 minutes. The kick is the file <stack>.task.json in the waker's state
     directory (repo, issue numbers, counts and times, never a title or a text); tasks arriving while it is still there only join it,
     and tasks arriving within 2 minutes of the previous kick make the next one wait until then (not_before).
The waker (ops/wake/waker.py task_tick) takes it from there: wake with reason "task" under the RAM guard, then the on_wake.d hook
40-task-run starts ONE run with a fixed prompt (ops/wake/tareas_run.py). Nothing from the issue goes into that prompt.

Polling: when Gitea cannot reach this VM (another subnet, a router or firewall between them, [webhook] ALLOWED_HOST_LIST), the
same receiver can ASK Gitea instead. With "poll_token" in the config (a read-only token: read:issue and read:repository, made by
ops/tareas_setup.py --vigia for the account <prefix>vigia), a thread reads every "poll_seconds" (default 60) the issues of each board repo
that changed since the last look, then their timeline, and turns each new item into the event a webhook would have sent: an assignment
("assignees"), a comment, a close, a reopen, a label change. Each goes through process(), so every rule above applies unchanged (the chain
rule, accept_from, own actions, the result-back rule and its once-a-day key, the rate limit and coalescing). The dedupe key of a polled
item is its timeline id, so a webhook and the poller can both run; a webhook delivery of the same event is kept apart by its own hash, and
the request file coalesces both into one run. The first look goes back LOOKBACK_S (6 h, the waker's request lifetime) so tasks filed
while nothing was listening are not lost. The poller writes only its cursor (tareas_poll.state.json, no text). Its errors are logged as
one line (status code only) and it tries again at the next tick.

Config (never in git): ops/wake/tareas_hook.json, mode 600 (the service refuses to start if group or others can read it, or if a secret is
shorter than 32 characters or still starts with "<", the placeholder of the example file):
  {"bind": "127.0.0.1:8661", "secret": "<same secret as the Gitea webhook>", "secrets": {"<org>": "<secret for /gitea/<org>>"}}
bind defaults to 127.0.0.1; the operator sets this VM's LAN address when Gitea runs on another machine (and opens that one port to
Gitea's address only). Logs: one JSON line per event with stack, issue number, action and outcome. Never a title, a body, a comment,
a signature or a secret.
Env (tests): TAREAS_HOOK_CONFIG, TAREAS_GATEWAYS (the master gateways.json), WAKE_STATE_DIR (the waker's state directory).
"""
import datetime
import errno
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
try:
    import notify   # operator alerts (ops bot); hosts without ops/lib just log
except ImportError:
    notify = None

CONFIG = os.environ.get("TAREAS_HOOK_CONFIG", os.path.join(HERE, "tareas_hook.json"))
GATEWAYS = os.environ.get("TAREAS_GATEWAYS", os.path.join(os.path.dirname(HERE), "gateways.json"))
STATE_DIR = os.environ.get("WAKE_STATE_DIR", HERE)
MAX_BODY = 64 * 1024
SEEN_TTL = 24 * 3600
SEEN_MAX = 10000            # two keys per delivery: its id and its body hash
MAX_EVENT_AGE_S = SEEN_TTL  # a signed payload whose own timestamp is older than the replay memory is refused
MIN_SECRET = 32
RATE_S = 120
STALE_S = 6 * 3600          # the waker drops a request older than this (waker.py CFG task.max_age_seconds)
MAX_ISSUES = 20            # issue numbers kept in one request file
MARK = "<!-- tareas:v1 -->"
HEADER_KEYS = ("pedido-por", "para", "salto", "cadena", "desde", "fecha", "reasignada-por")
DEFAULT_MAX_CADENA, MAX_CADENA_CLAMP = 3, 5
USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,38}$")
NUM_RE = re.compile(r"^#?([0-9]{1,9})$")
ISSUE_ACTIONS = {"opened", "assigned", "reopened"}
ISSUE_EVENTS = {"issues", "issue_assign"}
LABEL_EVENTS = {"issue_label", "issues"}
BLOCKED_LABEL = "estado/bloqueado"
DONE_KINDS = ("closed", "bloqueado")
MAX_DONE = 20
STACK_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
ORG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,38}$")
REPO_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,38}/[a-z0-9][a-z0-9_.-]{0,99}$")
LOOKBACK_S = 6 * 3600       # the first poll looks this far back (the waker drops a request older than this anyway)
POLL_OVERLAP_S = 120        # each poll re-reads this much before its cursor: clocks and Gitea's updated_at granularity
LOCK = threading.Lock()


def log(**kw):
    kw = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **kw}
    print(json.dumps(kw, separators=(",", ":")), flush=True)


def load_config(path=CONFIG, need_secret=True):
    """The config dict. Exits when the file is readable by group or others, or when no secret is set."""
    try:
        st = os.stat(path)
        raw = open(path).read()
    except OSError:
        sys.exit(f"no config at {path}: see ops/wake/TAREAS_HOOK.md")
    if st.st_mode & 0o077:
        sys.exit(f"{path} must be mode 600 (it holds the webhook secret): chmod 600 {path}")
    try:
        cfg = json.loads(raw)
    except ValueError:
        sys.exit(f"{path} is not valid JSON")
    if not isinstance(cfg, dict):
        sys.exit(f"{path} must hold a JSON object")
    secrets = {k: v for k, v in (cfg.get("secrets") or {}).items() if isinstance(v, str) and v and ORG_RE.match(str(k))}
    cfg["secrets"] = secrets
    if not isinstance(cfg.get("secret"), str):
        cfg["secret"] = ""
    if need_secret and not cfg["secret"] and not secrets:
        sys.exit(f"{path} has no secret: refusing to listen without one")
    if any(weak_secret(v) for v in [cfg["secret"], *secrets.values()] if v):
        sys.exit(f"{path}: a webhook secret is shorter than {MIN_SECRET} characters or still the placeholder of the example file: "
                 f"use `openssl rand -hex 32` (and the same value in the Gitea webhook form)")
    return cfg


def weak_secret(secret):
    return len(secret) < MIN_SECRET or secret.startswith("<")


def load_repos(path=GATEWAYS):
    """{repo (lower case): Gitea base url} of every board in the private master (for the poller). {} when unreadable."""
    try:
        master = json.load(open(path))
    except (OSError, ValueError):
        return {}
    out = {}
    for stack, conf in (master.get("stacks") or {}).items():
        t = conf.get("tareas") if isinstance(conf, dict) else None
        if isinstance(t, dict) and STACK_RE.match(str(stack)):
            repo, url = str(t.get("repo") or "").lower(), str(t.get("url") or "").rstrip("/")
            if REPO_RE.match(repo) and re.match(r"^https?://[^/\s@]+$", url):
                out.setdefault(repo, url)
    return out


def load_index(path=GATEWAYS):
    """{repo (lower case): {bot login (lower case): stack}} from the "tareas" block of each stack in the private master. {} when unreadable."""
    try:
        master = json.load(open(path))
    except (OSError, ValueError):
        return {}
    index = {}
    for stack, conf in (master.get("stacks") or {}).items():
        t = conf.get("tareas") if isinstance(conf, dict) else None
        if not (isinstance(t, dict) and STACK_RE.match(str(stack))):
            continue
        repo, me = str(t.get("repo") or "").lower(), str(t.get("me") or "").lower()
        if repo and me:
            index.setdefault(repo, {})[me] = stack
    return index


# names, clamp_cadena, parse_body and chain_info are COPIES of the functions of the same name in aibridge/tareas.py (see the docstring, rule 5).
# ops/wake/tareas_hook_selftest.py compares their source text with tareas.py's. Change both together.
def names(v):
    return [x for x in v if isinstance(x, str) and USER_RE.match(x)] if isinstance(v, list) else []


def clamp_cadena(v):
    """The operator's max_cadena: an integer 1..5 (above 5 is 5); anything else (0, negative, a string, a float, a bool, missing) is the default."""
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        return DEFAULT_MAX_CADENA
    return min(v, MAX_CADENA_CLAMP)


def parse_body(body):
    """(header fields, free text). A body with no sign of our header (an issue a person typed in the web page) has no fields.
    A header that was ATTEMPTED but cannot be read (the marker with no separator, leading blanks or a BOM before it, the marker later on its
    first line, a block with no known key such as wrong-case or misspelled keys) returns {"_bad": "1"}, which chain_info reads as unreadable,
    never as "no header". Only the FIRST block counts, so text further down cannot forge a header. A field written twice has the value None."""
    body = (body or "").replace("\r\n", "\n")
    if not body.startswith(MARK):
        probe = re.sub(r"^[\s\ufeff\u200b]+", "", body)
        if probe.startswith(MARK) or MARK in probe.split("\n", 1)[0]:
            return {"_bad": "1"}, body.strip()
        return {}, body.strip()
    head, sep, rest = body[len(MARK):].partition("\n---\n")
    if not sep:
        return {"_bad": "1"}, body.strip()
    f = {}
    for line in head.strip().split("\n"):
        k, _, v = line.partition(":")
        k = k.strip()
        if k in HEADER_KEYS:
            f[k] = None if k in f else v.strip()
    return (f or {"_bad": "1"}), rest.strip()


def chain_info(f, maxc):
    """What a header says about depth, read fail-closed. `f` is parse_body's fields, `maxc` the owner's max_cadena.
    {"present": a header exists, "bad": it is unreadable or inconsistent, "over": depth above the maximum, "salto": depth to use (an unreadable
    or too-deep header counts as maxc), "cadena": list of bot names or None when the chain is unknown, "desde": parent number or None}."""
    info = {"present": bool(f), "bad": False, "over": False, "salto": 0, "cadena": None, "desde": None}
    if not f:
        return info
    salto = f.get("salto")
    salto = int(salto) if isinstance(salto, str) and re.fullmatch(r"[0-9]{1,3}", salto) else None
    chain = None
    if "cadena" in f:
        raw = f["cadena"]
        parts = [x.strip() for x in raw.split(">")] if isinstance(raw, str) else []
        if parts and all(USER_RE.match(x) for x in parts) and len({x.lower() for x in parts}) == len(parts):
            chain = parts
        else:
            info["bad"] = True
    if "desde" in f:
        m = NUM_RE.match(f["desde"] or "")
        if m:
            info["desde"] = int(m.group(1))
        else:
            info["bad"] = True
    if salto is None or (chain is not None and salto != len(chain) - 1):
        info["bad"] = True
    elif salto > maxc or (chain is not None and len(chain) - 1 > maxc):
        info["over"] = True
    info["cadena"] = None if info["bad"] else chain
    info["salto"] = maxc if info["bad"] or info["over"] else salto
    return info


def load_rules(path=GATEWAYS):
    """{repo (lower case): {bot login (lower case): {"accept": {lower-case names the bot acts on: its accept_from (default peers) and its humans},
    "max": max_cadena}}} from the "tareas" block of each stack, read the way tareas.load_conf reads it. {} when unreadable."""
    try:
        master = json.load(open(path))
    except (OSError, ValueError):
        return {}
    out = {}
    for stack, conf in (master.get("stacks") or {}).items():
        t = conf.get("tareas") if isinstance(conf, dict) else None
        if not (isinstance(t, dict) and STACK_RE.match(str(stack))):
            continue
        repo, me = str(t.get("repo") or "").lower(), str(t.get("me") or "").lower()
        if not (repo and me):
            continue
        peers = [p for p in names(t.get("peers")) if p.lower() != me]
        accept = [a for a in names(t.get("accept_from")) if a.lower() != me] if "accept_from" in t else peers
        out.setdefault(repo, {})[me] = {"accept": {x.lower() for x in accept + names(t.get("humans"))}, "max": clamp_cadena(t.get("max_cadena")),
                                    "humans": {x.lower() for x in names(t.get("humans"))}, "peers": {x.lower() for x in peers}}
    return out


def may_act(rule, assignee, actor, author, body):
    """-> (True, "") or (False, outcome): may the bot `assignee` (lower case) act on this task? `actor` and `author` are lower-case logins."""
    if actor not in rule["accept"] or (author != assignee and author not in rule["accept"]):
        return False, "not-accepted"
    f = parse_body(body)[0]
    if not f and author not in rule.get("humans", ()):       # a bot's task with no header: the honest tool always writes one (as tareas.header_of)
        return False, "chain-ignored"
    info = chain_info(f, rule["max"])
    if info["bad"] or info["over"]:
        return False, "chain-ignored"
    if info["cadena"] and assignee in [c.lower() for c in info["cadena"][:-1]]:
        return False, "chain-ignored"
    return True, ""


def event_time(p, event):
    """Epoch seconds of what the payload says happened (comment.created_at for a comment, else issue.updated_at), None when absent or unreadable."""
    obj = p.get("comment") if event == "issue_comment" and isinstance(p.get("comment"), dict) else p.get("issue")
    obj = obj if isinstance(obj, dict) else {}
    for key in (("created_at", "updated_at") if event == "issue_comment" else ("updated_at", "created_at")):
        v = obj.get(key)
        if isinstance(v, str):
            try:
                t = datetime.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
            except ValueError:
                continue
            if t.tzinfo is None:
                t = t.replace(tzinfo=datetime.timezone.utc)
            return t.timestamp()
    return None


def login(obj):
    v = obj.get("login") if isinstance(obj, dict) else None
    return v.lower() if isinstance(v, str) else ""


def assignee_logins(issue):
    out = {login(a) for a in (issue.get("assignees") or []) if isinstance(a, dict)} if isinstance(issue.get("assignees"), list) else set()
    out.add(login(issue.get("assignee")))
    out.discard("")
    return out


def signature_ok(secrets, header, body):
    """True when `header` is the hex HMAC-SHA256 of body under one of the candidate secrets. Empty header or empty secret never match."""
    if not header or not isinstance(header, str):
        return False
    got = header.strip().lower().encode()
    ok = False
    for secret in secrets:
        if not secret:
            continue
        want = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest().encode()
        ok |= hmac.compare_digest(got, want)   # every candidate is compared: the time does not say which one matched
    return ok


class Receiver:
    def __init__(self, cfg, state_dir=STATE_DIR, gateways=GATEWAYS, clock=time.time):
        self.cfg, self.state_dir, self.gateways, self.clock = cfg, state_dir, gateways, clock
        self.state_file = os.path.join(state_dir, "tareas_hook.state.json")
        try:
            st = json.load(open(self.state_file))
        except (OSError, ValueError):
            st = {}
        self.seen = {str(k): float(v) for k, v in (st.get("seen") or {}).items() if isinstance(v, (int, float))}
        self.kicks = {str(k): float(v) for k, v in (st.get("kicks") or {}).items() if isinstance(v, (int, float))}

    # ---- state ----
    def save(self):
        tmp = self.state_file + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"seen": self.seen, "kicks": self.kicks}, f)
        os.replace(tmp, self.state_file)

    def prune(self, now):
        for k in [k for k, t in self.seen.items() if now - t > SEEN_TTL]:
            del self.seen[k]
        if len(self.seen) > SEEN_MAX:   # only reachable by a flood of valid deliveries: drop the oldest
            for k in sorted(self.seen, key=self.seen.get)[:len(self.seen) - SEEN_MAX]:
                del self.seen[k]

    # ---- the request file the waker reads ----
    def request_path(self, stack):
        return os.path.join(self.state_dir, f"{stack}.task.json")

    def kick(self, stack, repo, issue, delivery, now, done=None):
        """Create or extend <stack>.task.json. -> "kick" (a new request), "coalesced" (joined a pending one). `done` ({"n", "by", "kind"}) puts
        the issue under "done" (a task this bot filed came back) instead of "issues" (a task for it to work)."""
        path = self.request_path(stack)
        try:
            req = json.load(open(path))
            if not isinstance(req, dict) or now - float(req.get("first_ts", 0)) > STALE_S:   # the waker would drop a stale one: start afresh
                req = None
        except (OSError, ValueError, TypeError):
            req = None
        if req is not None:
            issues = [n for n in req.get("issues", []) if isinstance(n, int)]
            dones = [d for d in req.get("done", []) if isinstance(d, dict)]
            if done is None and issue not in issues:
                issues.append(issue)
            if done is not None and not any(d.get("n") == done["n"] and d.get("kind") == done["kind"] for d in dones):
                dones.append(done)
            req.update(issues=issues[-MAX_ISSUES:], done=dones[-MAX_DONE:], count=int(req.get("count", 1)) + 1, delivery=delivery)
            how = "coalesced"
        else:
            not_before = max(now, self.kicks.get(stack, 0) + RATE_S)
            req = {"stack": stack, "repo": repo, "issues": [] if done else [issue], "done": [done] if done else [], "count": 1,
                   "delivery": delivery, "first_ts": now, "not_before": not_before}
            self.kicks[stack] = not_before
            how = "kick"
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(req, f)
        os.replace(tmp, path)
        return how

    # ---- one delivery ----
    def handle(self, path, headers, body):
        """-> (http status, outcome). `headers` is any mapping with Gitea's header names; `body` the raw bytes. Never raises for bad input."""
        m = re.fullmatch(r"/gitea(?:/([^/]+))?", path.split("?")[0])
        if not m:
            return 404, "not-found"
        org = m.group(1)
        if org is None:
            candidates = [self.cfg["secret"]]
        elif ORG_RE.match(org):
            candidates = [self.cfg["secrets"].get(org, "")]
        else:
            candidates = []
        if not signature_ok(candidates, headers.get("X-Gitea-Signature", ""), body):
            log(outcome="bad-signature")
            return 401, "bad-signature"
        delivery = str(headers.get("X-Gitea-Delivery", ""))[:64]
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", delivery):
            delivery = "-"
        event = str(headers.get("X-Gitea-Event", "")).lower()
        try:
            p = json.loads(body)
        except ValueError:
            log(outcome="bad-json")
            return 400, "bad-json"
        if not isinstance(p, dict):
            log(outcome="bad-json")
            return 400, "bad-json"
        return self.process(event, p, delivery, "b:" + hashlib.sha256(body).hexdigest())   # the delivery id is not under the HMAC, the body is

    def process(self, event, p, delivery, digest, via="hook"):
        """One event, already authenticated: a signed webhook delivery (digest = hash of the raw body) or one the poller read from Gitea
        with its own token (digest = a key built from the timeline item). -> (http status, outcome)."""
        issue = p.get("issue") if isinstance(p.get("issue"), dict) else {}
        action = p.get("action") if isinstance(p.get("action"), str) else ""
        number = issue.get("number") if isinstance(issue.get("number"), int) else p.get("number")
        number = number if isinstance(number, int) and 0 < number < 10 ** 9 else 0
        shown = action if action in ISSUE_ACTIONS | {"created", "closed", "label_updated"} else "other"

        def done(outcome, stack=None, code=200):
            log(stack=stack, issue=number, action=shown, outcome=outcome, via=via)
            return code, outcome

        if event in ISSUE_EVENTS and action == "closed":
            return self.handle_done(p, issue, number, delivery, digest, event, "closed", done)
        if event in LABEL_EVENTS and action == "label_updated":
            labels = issue.get("labels") if isinstance(issue.get("labels"), list) else []
            if any(isinstance(lb, dict) and str(lb.get("name", "")).lower() == BLOCKED_LABEL for lb in labels):
                return self.handle_done(p, issue, number, delivery, digest, event, "bloqueado", done)
            return done("ignored-event")
        if event in ISSUE_EVENTS and action in ISSUE_ACTIONS:
            actor = login(p.get("sender"))
        elif event == "issue_comment" and action == "created" and not p.get("is_pull"):
            actor = login((p.get("comment") or {}).get("user") if isinstance(p.get("comment"), dict) else None) or login(p.get("sender"))
        else:
            return done("ignored-event")
        repo = str((p.get("repository") or {}).get("full_name") or "").lower() if isinstance(p.get("repository"), dict) else ""
        bots = self.index().get(repo)
        if not bots:
            return done("ignored-repo")
        if issue.get("pull_request") or str(issue.get("state", "")).lower() != "open" or not number:
            return done("ignored-state")
        targets = sorted({bots[a] for a in assignee_logins(issue) if a in bots})
        if not targets:
            return done("ignored-assignee")
        now = self.clock()
        stamp = event_time(p, event)
        if stamp is not None and now - stamp > MAX_EVENT_AGE_S:   # signed, but older than the replay memory: cannot be told from a replay
            return done("stale-payload")
        author = login(issue.get("user"))
        rules = load_rules(self.gateways).get(repo, {})
        outcome = "ignored-self"
        with LOCK:
            self.prune(now)
            if (delivery != "-" and delivery in self.seen) or digest in self.seen:
                return done("duplicate")
            for stack in targets:
                bot = bots_of(bots, stack)
                if bot == actor:   # the bot's own action never wakes it
                    log(stack=stack, issue=number, action=shown, outcome="ignored-self", via=via)
                    continue
                may, why = may_act(rules.get(bot) or {"accept": set(), "max": DEFAULT_MAX_CADENA}, bot, actor, author, issue.get("body"))
                if not may:
                    log(stack=stack, issue=number, action=shown, outcome=why, via=via)
                    outcome = why
                    continue
                how = self.kick(stack, repo, number, delivery, now)
                log(stack=stack, issue=number, action=shown, outcome=how, via=via)
                outcome = how
            if delivery != "-":
                self.seen[delivery] = now
            self.seen[digest] = now
            self.save()
        return 200, outcome

    def handle_done(self, p, issue, number, delivery, digest, event, kind, done):
        """A task came back (closed, or left bloqueado): wake the bot that filed it (section 6b of the docstring)."""
        repo = str((p.get("repository") or {}).get("full_name") or "").lower() if isinstance(p.get("repository"), dict) else ""
        bots = self.index().get(repo)
        if not bots:
            return done("ignored-repo")
        want = "closed" if kind == "closed" else "open"
        if issue.get("pull_request") or str(issue.get("state", "")).lower() != want or not number:
            return done("ignored-state")
        actor, author = login(p.get("sender")), login(issue.get("user"))
        stack = bots.get(author)
        if not stack:
            return done("ignored-author")   # a person's task: they see the result in Gitea, there is no bot to wake
        if actor == author:
            return done("ignored-self", stack)
        rule = load_rules(self.gateways).get(repo, {}).get(author) or {}
        if actor not in assignee_logins(issue) or actor not in (rule.get("peers", set()) | rule.get("accept", set())):
            return done("not-accepted", stack)
        now = self.clock()
        stamp = event_time(p, event)
        if stamp is not None and now - stamp > MAX_EVENT_AGE_S:
            return done("stale-payload", stack)
        once = f"n:{stack}:{number}:{kind}"
        with LOCK:
            self.prune(now)
            if (delivery != "-" and delivery in self.seen) or digest in self.seen:
                return done("duplicate", stack)
            if once in self.seen:
                outcome = "already-told"
            else:
                outcome = self.kick(stack, repo, number, delivery, now, done={"n": number, "by": actor, "kind": kind})
                self.seen[once] = now
            if delivery != "-":
                self.seen[delivery] = now
            self.seen[digest] = now
            self.save()
        return done(outcome, stack)

    def index(self):
        return load_index(self.gateways)


def bots_of(bots, stack):
    """The bot login of `stack` in one repo's {login: stack} map."""
    return next((b for b, s in bots.items() if s == stack), "")


def make_handler(receiver):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10   # a client that sends the body slowly must not hold a thread

        def log_message(self, *a):   # no access log: the journal gets the JSON lines of Receiver.handle only
            pass

        def _send(self, code, outcome):
            data = json.dumps({"ok": code == 200, "outcome": outcome}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", ""))
            except ValueError:
                n = -1
            if not 0 < n <= MAX_BODY:
                log(outcome="body-size")
                return self._send(413, "body-size")
            body = self.rfile.read(n)
            try:
                code, outcome = receiver.handle(self.path, self.headers, body)
            except Exception as e:   # never leak internals to the caller; the journal has the class
                log(outcome="error", error=type(e).__name__)
                code, outcome = 500, "error"
            self._send(code, outcome)

        def do_GET(self):
            self._send(404, "not-found")
        do_PUT = do_DELETE = do_PATCH = do_GET
    return Handler


def listen(host, port, receiver, wait_s=120):
    """Like the waker's listen(): right after a host boot the LAN address may not be up yet (EADDRNOTAVAIL), so a failed bind is
    retried forever, one log line per distinct error and an operator alert after wait_s."""
    t0 = time.time()
    last, alerted = None, False
    while True:
        try:
            srv = ThreadingHTTPServer((host, port), make_handler(receiver))
            srv.daemon_threads = True
            if alerted and notify:
                threading.Thread(target=lambda: notify.resolve("tareas-hook:bind", f"tareas_hook ya escucha en {host}:{port}"), daemon=True).start()
            return srv
        except OSError as e:
            if e.errno != last:
                last = e.errno
                log(outcome="bind-retry", error=errno.errorcode.get(e.errno, str(e.errno)))
            if not alerted and time.time() - t0 > wait_s and notify:
                alerted = True
                threading.Thread(target=lambda: notify.alert("tareas-hook:bind", f"tareas_hook no puede escuchar en {host}:{port} desde hace "
                                                              f"{wait_s} s: las tareas no despiertan a los bots."), daemon=True).start()
            time.sleep(2 if e.errno == errno.EADDRNOTAVAIL else 5)


def iso_utc(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def parse_time(v):
    try:
        t = datetime.datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)).timestamp()


class Poller:
    """Reads the boards with a read-only token and feeds Receiver.process (see "Polling" in the docstring)."""

    def __init__(self, receiver, token, state_dir=STATE_DIR, clock=time.time, fetch=None):
        self.receiver, self.token, self.clock = receiver, token, clock
        self.state_file = os.path.join(state_dir, "tareas_poll.state.json")
        self.fetch = fetch or self.http_get
        try:
            st = json.load(open(self.state_file))
        except (OSError, ValueError):
            st = {}
        self.cursor = {str(k): float(v) for k, v in (st.get("cursor") or {}).items() if isinstance(v, (int, float))}

    def http_get(self, url):
        """-> (status, parsed JSON or None). Never raises; the token is only in the header."""
        req = urllib.request.Request(url, headers={"Authorization": "token " + self.token, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.loads(r.read(4 * 1024 * 1024) or b"null")
        except urllib.error.HTTPError as e:
            return e.code, None
        except (OSError, ValueError):
            return 0, None

    def save(self):
        tmp = self.state_file + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"cursor": self.cursor}, f)
        os.replace(tmp, self.state_file)

    @staticmethod
    def event_of(item, issue, repo):
        """A timeline item -> (event header, payload) as a webhook would carry it, or None for kinds that wake nobody."""
        kind, user = item.get("type"), item.get("user") if isinstance(item.get("user"), dict) else {}
        base = {"issue": issue, "repository": {"full_name": repo}, "sender": {"login": user.get("login", "")}, "number": issue.get("number")}
        if kind == "comment":
            return "issue_comment", dict(base, action="created", is_pull=False,
                                         comment={"user": {"login": user.get("login", "")}, "created_at": item.get("created_at")})
        if kind == "assignees" and not item.get("removed_assignee"):
            return "issues", dict(base, action="assigned")
        if kind == "close":
            return "issues", dict(base, action="closed")
        if kind == "reopen":
            return "issues", dict(base, action="reopened")
        if kind == "label":
            return "issue_label", dict(base, action="label_updated")   # the receiver looks at the issue's CURRENT labels
        return None

    def tick(self):
        now = self.clock()
        outcomes = []
        for repo, url in load_repos(self.receiver.gateways).items():
            since = self.cursor.get(repo, now - LOOKBACK_S) - POLL_OVERLAP_S
            api = f"{url}/api/v1/repos/{repo}"
            st, issues = self.fetch(f"{api}/issues?state=all&type=issues&limit=50&since={urllib.parse.quote(iso_utc(since))}")
            if st != 200 or not isinstance(issues, list):
                log(outcome="poll-error", error=f"issues {st}", via="poll")
                continue
            ok = True
            for issue in issues:
                n = issue.get("number") if isinstance(issue, dict) else None
                if not isinstance(n, int) or issue.get("pull_request"):
                    continue
                st, items = self.fetch(f"{api}/issues/{n}/timeline?limit=50&since={urllib.parse.quote(iso_utc(since))}")
                if st != 200 or not isinstance(items, list):
                    log(outcome="poll-error", error=f"timeline {st}", issue=n, via="poll")
                    ok = False
                    continue
                for item in items:
                    if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                        continue
                    t = parse_time(item.get("created_at"))
                    if t is None or t < since:
                        continue
                    ev = self.event_of(item, issue, repo)
                    if ev:
                        outcomes.append(self.receiver.process(ev[0], ev[1], "-", f"p:{repo}:{n}:{item['id']}", via="poll")[1])
            if ok:
                self.cursor[repo] = now
        self.save()
        return outcomes

    def loop(self, every):
        while True:
            try:
                self.tick()
            except Exception as e:   # a bad answer must not kill the thread: one line, next tick
                log(outcome="poll-error", error=type(e).__name__, via="poll")
            time.sleep(every)


def serve():
    cfg = load_config()
    host, _, port = str(cfg.get("bind", "127.0.0.1:8661")).rpartition(":")
    receiver = Receiver(cfg)
    token = cfg.get("poll_token") if isinstance(cfg.get("poll_token"), str) and re.fullmatch(r"[A-Za-z0-9]{20,100}", cfg.get("poll_token", "")) else ""
    every = max(30, int(cfg.get("poll_seconds", 60))) if str(cfg.get("poll_seconds", 60)).isdigit() else 60
    log(outcome="starting", bind=f"{host or '127.0.0.1'}:{port}", repos=len(receiver.index()), polling=every if token else 0)
    if token:
        threading.Thread(target=Poller(receiver, token).loop, args=(every,), daemon=True).start()
    listen(host or "127.0.0.1", int(port), receiver).serve_forever()


if __name__ == "__main__":
    if sys.argv[1:2] == ["serve"]:
        serve()
    else:
        sys.exit(__doc__)
