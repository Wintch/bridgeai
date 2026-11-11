#!/usr/bin/env python3
"""Synthetic business day harness, v1 (design: SYNTHETIC_DAY.md). Standard library only.

  python3 ops/synth_day.py --profile burger --load normal --mode a --speed 60 [--repeats 5] [--targets ops/synth_targets.json]
  python3 ops/synth_day.py --profile design --load busy --mode b --approve-spend --max-tokens 2000000 --price cheap=0.1/0.4
  python3 ops/synth_day.py --profile shop --load normal --mode a --dry-run          # the plan only, nothing is sent
  python3 ops/synth_day.py --calibrate ops/synth_results/<mode-a-run>.json ops/synth_results/<mode-b-run>.json   # offline, joins two reports

What it does: loads a scenario (ops/synth/<profile>.json, all names and numbers invented), lays the day's events on a clock from the load's
volumes (a seeded draw: the same seed gives the same day), and replays them against TEST stacks through each stack's own Hermes API
(--endpoint chat = POST /v1/chat/completions, the default; --endpoint runs = POST /v1/runs and poll GET /v1/runs/<id>). Every message carries
the tag [SYN:<run-id>:<event-id>] so ops/synth_fake_llm.py (mode A: scripted model, no tokens spent) can pick a scripted answer and so every log
line can be matched back to its event. --speed N compresses the clock (N simulated seconds per wall second; a day is 86400/N s); --speed 0
replays event by event, one after the other, without waiting. Task events (kind "task": a bot files a task for the next rung) are driven only
against a target that says it has "gateway tareas" ("tareas": true); otherwise they are recorded as skipped with the reason, and the estimate
fills them from the first-order table of SYNTHETIC_DAY.md section 5.1 and says so.

Safety (SYNTHETIC_DAY.md section 4), enforced here. Be plain about what this CAN and CANNOT know: the harness sees only the private config
the operator wrote. It cannot see a stack's Telegram bot token, nor whether a stack is really a guest, nor what provider key a stack uses. Those
are the operator's statements, so each one is REQUIRED (a missing one refuses), not assumed:
  * Targets come from a PRIVATE config (default ops/synth_targets.json, git-ignored; ops/synth_targets.example.json is the shape). A target is
    accepted only if it is listed there AND its name starts with "syn-" or it is marked "guest": true (a guest made by provision_guest.sh),
    AND it says either "no_telegram": true (the operator states that it has no bot) or "test_bot": true (its bot belongs to nobody). A target
    that says neither is refused, and so is one marked "telegram": true without "test_bot": true. Anything else is refused with exit 2, before a
    single request. SYNTHETIC_DAY.md section 10 has an operator-run preflight that reads the stack's own env for a bot token; the harness cannot.
  * Mode a (a fake model, no tokens spent) needs "fake_llm" in the config and PROVES that every target talks to it: before the day it sends one
    tagged probe turn to each target and reads the fake's /counters; a target whose probe the fake did not see is refused (exit 2) and nothing
    else is sent. (The probe turn itself goes wherever the stack's model points: one small turn on a stack that is still on a real provider.)
  * Mode b (real keys, real tokens) needs "keys" in the config (labels only: provider, label, the roles that use it), --approve-spend, and a
    budget: --max-tokens and/or --max-usd (the latter with --price), summed from the state.db difference or the API usage and checked before every
    turn (a turn already running is not interrupted: the overshoot is at most the turns in flight, --workers). A turn that reports no token figure
    stops the run, since the budget cannot be enforced. The runaway load (E8) needs --allow-runaway and a "cap_check_cmd", which then runs before
    that turn. A turn cannot be capped from outside: the stack's agent keeps running after --turn-timeout abandons the client, so a timed-out E8
    turn runs "on_kill_cmd" at once.
  * Caps: --max-turns and --max-turns-per-bot are hard caps. Their defaults come from the planned turn count (plus 20 percent and 3); the plan and
    the caps are printed before a run, and a cap below the plan warns (mode b: refuses unless --allow-truncate). A file named KILL in --out (or
    --kill-file) is polled every half second, also while waiting for the next event: it stops the replay, runs the optional config "on_kill_cmd"
    (an argv list the operator chooses, e.g. to put the test stacks to sleep) at once and ends the run. Ctrl-C does the same and still writes a
    partial report. "cap_check_cmd" (an argv list, e.g. a wrapper around ops/keys_usage.py) runs before the first turn and then every
    --cap-check-every turns; a non-zero exit stops the run. Neither can stop a turn that is already running.
  * The report holds COUNTS AND SIZES ONLY: no message text, no answer text, no task text, no key, no stack name (roles and target labels).

What a run does NOT show, said once: (1) mode a tokens are the fake model's estimate (request characters / ratio) and its scripted answer sizes,
labelled fake_estimate: dollars from a mode a run are for scale only; the characters-per-token ratio is computed offline from a mode a and a mode
b report (--calibrate), never inside one run. (2) One session per EVENT (steps of an event share a session id, if the stack honours the header),
so a unit cost is a fresh-session cost, not the cost of a long owner conversation; --continue-e3 puts all E3 turns of a role in one session.
(3) state.db figures are Hermes's own (an estimate when the provider returned no usage), include any other traffic on that file during the
turn (crons, aux calls, woken hops), and cache reads are carried separately (cache_read_tokens): whether input_tokens includes them is not
known, see --cache-in-input.

What it reads when it can: the fake model's /counters (calls, tool calls, estimated prompt and completion tokens per event, from the request
size), a stack's Hermes state.db (config "state_db": the table session_model_usage, differenced around each turn: serialised per target),
the stubs' /_counters (config "stubs", before and after), the router's .model-eval.jsonl and .gateway-log.jsonl and the waker's journal
(config "logs": eval, gateway, waker; the journal as plain text, e.g. `journalctl -u aibridge-waker -o cat`). What it cannot read from here (VM only,
docker or SSH): ops/telemetry.py, ops/stack_usage.sh, ops/keys_usage.py, ops/chat_review.py: the operator runs them after the day (the steps are in
SYNTHETIC_DAY.md section 10).

Output (--out, default ops/synth_results/, git-ignored): <run-id>.json per run and <profile>-<load>-<mode>-summary.md for the set.
"""
import argparse
import calendar
import collections
import hashlib
import json
import math
import os
import random
import re
import socket
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
SCEN_DIR = os.path.join(HERE, "synth")
DEFAULT_TARGETS = os.path.join(HERE, "synth_targets.json")
DEFAULT_OUT = os.path.join(HERE, "synth_results")
SCRIPT_VERSION = 1
IDLE_S = 600                  # the waker's idle timer for web and brain (ops/wake/waker.py)
ASSUMED_ACTIVE_S = 60.0       # assumed seconds a bot is busy for a step or hop that was not measured (a scenario step may say "active_s")
CAP_MARGIN = 1.2              # default caps = planned turns x 1.2 + 3

BOOT_ASSUMED_S = 25.0         # assumption until the waker journal gives the median `ready after`
GB_PER_AWAKE_BOT = 1.0        # assumption: about 600-700 MB brain + 300 MB web tier (MULTI_BOT_TASKS.md)
HOST_RESERVE_GB = 4.0         # assumption
MIX = {"quiet": 4, "normal": 22, "busy": 4}      # a month of thirty days (SYNTHETIC_DAY.md 5.6)
NAME_OK = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
RUN_OK = re.compile(r"^[A-Za-z0-9_-]{1,60}$")
FINISHED = {"completed", "complete", "finished", "done", "succeeded", "success", "failed", "error", "cancelled", "canceled", "stopped", "timeout"}
FAILED = {"failed", "error", "cancelled", "canceled", "stopped", "timeout"}
# First-order unit costs when a run has no measurement for an event type: (model calls, input tokens, output tokens). SYNTHETIC_DAY.md 5.1: ASSUMPTIONS.
FIRST_ORDER = {"E1": (4, 26000, 1400), "E2": (8, 52000, 2800), "E3": (4, 26000, 1400), "E4": (5, 33000, 1800), "E5": (6, 39000, 2100),
               "E6": (4, 16000, 1400), "E7": (20, 130000, 7000), "E9": (4, 26000, 1400), "E8": (0, 0, 0), "E10": (0, 0, 0)}
RECEIVER_SIDE = FIRST_ORDER["E4"]    # the rung that wakes for a hop runs with a fixed prompt, untagged: added as an assumption
RECEIVER_ADDON = ("E2", "E4")        # only these first-order rows leave the receiver out; E5 and E7 rows already span every bot of the event
SENDER_FIRST_ORDER = {"E4": FIRST_ORDER["E3"]}   # E4's own row above is the RECEIVER side; the sender is an owner turn, priced like E3
TAG_RE = re.compile(r"\[SYN:[A-Za-z0-9_.-]+:E\d+-\d+(?:\.\d+)?\]")


class Refuse(Exception):
    """A safety rule said no: exit 2 before anything is sent."""


def say(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------------------------------------------- scenario and timeline
def hhmm(s):
    h, m = s.split(":")
    return int(h) * 3600 + int(m) * 60


def load_scenario(profile, directory=SCEN_DIR):
    if not re.fullmatch(r"[a-z][a-z0-9]{1,20}", profile or ""):
        raise Refuse(f"bad profile name {profile!r}")
    path = os.path.join(directory, profile + ".json")
    try:
        doc = json.load(open(path))
    except (OSError, ValueError) as e:
        raise Refuse(f"cannot read scenario {path}: {e}")
    if doc.get("script_version") != SCRIPT_VERSION or doc.get("profile") != profile:
        raise Refuse(f"scenario {path}: script_version {SCRIPT_VERSION} and profile {profile!r} expected")
    return doc


def pad_text(chars, seed):
    """Invented 'document' text of about `chars` characters: it only gives the prompt a document-sized body."""
    rnd = random.Random(seed)
    out, n, i = [], 0, 0
    while n < chars:
        i += 1
        line = f"Line {i}: item {rnd.randint(100, 999)} amount {rnd.randint(10, 9999)} due day {rnd.randint(1, 28)}."
        out.append(line)
        n += len(line) + 1
    return "\n".join(out)


def times_for(spec, n, rnd):
    if spec.get("at"):
        at = spec["at"]
        return sorted(hhmm(at[i % len(at)]) for i in range(n))
    wins = []
    for w in spec.get("windows") or ["09:00-18:00"]:
        a, b = w.split("-")
        wins.append((hhmm(a), hhmm(b)))
    clusters = spec.get("clusters") or []
    out = []
    for _ in range(n):
        r, acc, t = rnd.random(), 0.0, None
        for c in clusters:
            acc += float(c.get("share", 0))
            if r < acc:
                t = hhmm(c["at"]) + rnd.uniform(0, float(c.get("span_min", 10)) * 60)
                break
        if t is None:
            a, b = wins[rnd.randrange(len(wins))]
            t = rnd.uniform(a, b)
        out.append(int(t))
    return sorted(out)


def build_timeline(scen, load, seed, run_id):
    """-> list of events sorted by simulated time; each has `steps` (the turns to send). Pure function of (scenario, load, seed)."""
    vols = (scen.get("loads") or {}).get(load)
    if vols is None:
        raise Refuse(f"scenario {scen['profile']} has no load {load!r} (have {', '.join(scen.get('loads', {}))})")
    rnd = random.Random(f"{scen['profile']}:{load}:{seed}")
    events = []
    for et in sorted(scen["events"], key=lambda k: int(k[1:])):
        spec = scen["events"][et]
        n = int(vols.get(et, 0))
        for i, t in enumerate(times_for(spec, n, rnd) if n else [], 1):
            eid = f"{et}-{i:02d}"
            roles = spec.get("roles") or [spec.get("role", "*")]
            role = rnd.choice(roles)
            steps = []
            defs = spec.get("steps") or [{"after_s": 0}]
            for k, st in enumerate(defs, 1):
                tpl = st.get("template") if st.get("template") is not None else (rnd.choice(spec["templates"]) if spec.get("templates") else "")
                tpl = tpl.replace("{n}", str(i))
                tag_id = eid if k == 1 else f"{eid}.{k}"
                text = f"[SYN:{run_id}:{tag_id}] {tpl}".rstrip()
                if spec.get("doc_chars") and spec.get("kind") == "turn":
                    text += "\n" + pad_text(int(spec["doc_chars"]), f"{run_id}{tag_id}")
                steps.append({"idx": k, "tag_id": tag_id, "after_s": int(st.get("after_s", 0)), "role": st.get("role", role), "text": text,
                              "gpu_seconds": float(st.get("gpu_seconds", 0 if spec.get("steps") else spec.get("gpu_seconds", 0))),
                              "active_s": float(st.get("active_s", spec.get("active_s", ASSUMED_ACTIVE_S)))})
            events.append({"id": eid, "etype": et, "name": spec.get("name", et), "source": spec.get("source", "owner"), "kind": spec.get("kind", "turn"),
                           "sim_s": t, "role": role, "steps": steps, "hops": spec.get("hops") or [], "ext": spec.get("ext") or {},
                           "fresh_session": bool(spec.get("fresh_session", True))})
    events.sort(key=lambda e: (e["sim_s"], e["id"]))
    return events


def clock(sim_s):
    return "%02d:%02d" % (sim_s // 3600 % 24, sim_s // 60 % 60)


# ---------------------------------------------------------------------------------------------------------------- private config and safety
def load_targets(path):
    """Read the private config and apply the safety rules. -> config dict with `targets` as an ordered list of dicts (key material not yet read)."""
    try:
        cfg = json.load(open(path))
    except OSError:
        raise Refuse(f"no private config at {path}: copy ops/synth_targets.example.json there and fill it in (it is git-ignored)")
    except ValueError as e:
        raise Refuse(f"{path} is not valid JSON: {e}")
    raw = cfg.get("targets")
    if not isinstance(raw, dict) or not raw:
        raise Refuse(f"{path}: \"targets\" must list at least one test stack")
    out = []
    for i, (name, t) in enumerate(raw.items()):
        if not isinstance(t, dict) or not NAME_OK.match(name):
            raise Refuse(f"target {name!r}: bad name or entry")
        if not (name.startswith("syn-") or t.get("guest") is True):
            raise Refuse(f"target {name!r} is neither named syn-* nor marked \"guest\": true: the harness only drives test stacks")
        if t.get("telegram") and t.get("test_bot") is not True:
            raise Refuse(f"target {name!r} has a Telegram bot and is not marked \"test_bot\": true: refused (a person's bot is never a target)")
        if t.get("no_telegram") is not True and t.get("test_bot") is not True:
            raise Refuse(f"target {name!r}: the harness cannot see a stack's bot token, so the config must say it: \"no_telegram\": true (this stack has no "
                         f"Telegram bot) or \"test_bot\": true (its bot belongs to nobody). Neither is assumed")
        if t.get("no_telegram") is True and (t.get("telegram") or t.get("test_bot")):
            raise Refuse(f"target {name!r} says \"no_telegram\": true and also names a bot: contradictory, refused")
        api = t.get("api", "")
        if not re.match(r"^https?://[^/\s]+$", api):
            raise Refuse(f"target {name!r}: \"api\" must be http(s)://host:port with no path")
        if not (t.get("key_file") or t.get("key_env")):
            raise Refuse(f"target {name!r}: give \"key_file\" (a path) or \"key_env\" (a variable name); keys are never written in this file's report")
        roles = t.get("roles") or ["*"]
        if not isinstance(roles, list):
            raise Refuse(f"target {name!r}: \"roles\" must be a list")
        out.append(dict(t, name=name, label=t.get("label") or f"target-{i + 1}", roles=roles))
    cfg["targets"] = out
    return cfg


def read_key(t):
    try:
        if t.get("key_env"):
            k = os.environ.get(t["key_env"], "")
        else:
            k = open(t["key_file"]).read().strip()
    except OSError:
        k = ""
    if not k:
        raise Refuse(f"target {t['name']}: its key could not be read (key_file or key_env is empty or missing)")
    return k


def pick_target(targets, role, profile):
    for t in targets:
        if t.get("profile") not in (None, "", profile):
            continue
        if "*" in t["roles"] or role in t["roles"]:
            return t
    return None


# ---------------------------------------------------------------------------------------------------------------- driving a stack's API
def http_call(method, url, key, body=None, timeout=60, headers=None):
    """-> (http status or 0, parsed JSON or None, error code or "")."""
    hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    hdr.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(4 * 1024 * 1024)
            code = r.status
    except urllib.error.HTTPError as e:
        return e.code, None, f"http_{e.code}"
    except (socket.timeout, TimeoutError):
        return 0, None, "timeout"
    except urllib.error.URLError as e:
        return 0, None, "timeout" if isinstance(e.reason, (socket.timeout, TimeoutError)) else "connect"
    except OSError:
        return 0, None, "connect"
    try:
        return code, json.loads(raw), ""
    except ValueError:
        return code, None, "bad_json"


def as_int(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def usage_of(d):
    u = d.get("usage") if isinstance(d, dict) else None
    if not isinstance(u, dict):
        return None
    i = as_int(u.get("prompt_tokens", u.get("input_tokens")))
    o = as_int(u.get("completion_tokens", u.get("output_tokens")))
    return (i, o) if (i or o) else None


def send_turn(t, key, text, session, opts):
    """One turn through the stack's API. -> dict of sizes and timings (never the text)."""
    hdr = {opts["session_header"]: session} if opts.get("session_header") and session else {}
    t0 = time.time()
    res = {"http_status": 0, "error_code": "", "answer_chars": 0, "finish": "", "api_usage": None, "run_status": ""}
    if opts["endpoint"] == "chat":
        body = {"model": t.get("model", "hermes-agent"), "stream": False, "messages": [{"role": "user", "content": text}]}
        code, d, err = http_call("POST", t["api"] + "/v1/chat/completions", key, body, opts["turn_timeout"], hdr)
        res.update(http_status=code, error_code=err)
        if d:
            ch = (d.get("choices") or [{}])[0]
            c = (ch.get("message") or {}).get("content")
            res.update(answer_chars=len(c) if isinstance(c, str) else 0, finish=str(ch.get("finish_reason") or "")[:20], api_usage=usage_of(d))
    else:
        code, d, err = http_call("POST", t["api"] + "/v1/runs", key, {"input": text}, min(30, opts["turn_timeout"]), hdr)
        res.update(http_status=code, error_code=err)
        rid = (d.get("run_id") or d.get("id")) if isinstance(d, dict) else None
        if not err and not rid:
            res["error_code"] = "no_run_id"
        elif not err:
            unknown = 0
            while time.time() - t0 < opts["turn_timeout"]:
                time.sleep(opts["poll_s"])
                if opts.get("stop") and opts["stop"]():
                    res["error_code"] = "stopped"          # the run was killed: stop polling (the stack's run itself is not cancelled)
                    break
                code, g, err = http_call("GET", f"{t['api']}/v1/runs/{rid}", key, None, 30, hdr)
                if err:
                    res["error_code"] = err
                    break
                st = (g.get("status") if isinstance(g.get("status"), str) else g.get("state")) if isinstance(g, dict) else None
                st = st.strip().lower() if isinstance(st, str) else ""
                if not st:
                    unknown += 1
                    if unknown >= 3:
                        res["error_code"] = "run_status_unknown"      # the status field names are a guess (tareas_run.py): this says so
                        break
                    continue
                if st in FINISHED:
                    res.update(run_status=st, api_usage=usage_of(g))
                    out = g.get("output") if isinstance(g.get("output"), str) else g.get("result")
                    res["answer_chars"] = len(out) if isinstance(out, str) else 0
                    if st in FAILED:
                        res["error_code"] = "run_" + st
                    break
            else:
                res["error_code"] = "timeout"
    res["seconds"] = round(time.time() - t0, 2)
    return res


def usage_snapshot(path):
    """Sums over Hermes's state.db: session_model_usage tokens and calls, sessions.tool_call_count. None when it cannot be read."""
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            a = db.execute("select coalesce(sum(api_call_count),0), coalesce(sum(input_tokens),0), coalesce(sum(output_tokens),0), "
                           "coalesce(sum(cache_read_tokens),0) from session_model_usage").fetchone()
            try:
                tc = db.execute("select coalesce(sum(tool_call_count),0) from sessions").fetchone()[0]
            except sqlite3.Error:
                tc = None
        finally:
            db.close()
        return {"calls": a[0], "input": a[1], "output": a[2], "cache_read": a[3], "tool_calls": tc}
    except (sqlite3.Error, OSError):
        return None


def delta(after, before):
    if not after or not before:
        return None
    return {k: (after[k] - before[k]) if after.get(k) is not None and before.get(k) is not None else None for k in after}


# ---------------------------------------------------------------------------------------------------------------- the replay
def usd_of(inp, out, cache, price, cache_in_input=False):
    """Dollars for one token triple at one price (pin, pout, pcache or None). Cache reads are billed at pcache, else at the input price.
    cache_in_input: input already includes the cache reads (OpenAI style); otherwise input excludes them (Anthropic style)."""
    pin, pout, pcache = price
    pcache = pin if pcache is None else pcache
    inp, out, cache = inp or 0, out or 0, cache or 0
    fresh = max(0, inp - cache) if cache_in_input else inp
    return (fresh * pin + cache * pcache + out * pout) / 1e6


class Run:
    def __init__(self, scen, cfg, args, run_id, seed, caps, prices=None):
        self.scen, self.cfg, self.args, self.run_id, self.seed = scen, cfg, args, run_id, seed
        self.targets = cfg["targets"]
        self.keys = {t["name"]: read_key(t) for t in self.targets}
        self.max_turns, self.caps_by_label = caps
        self.prices = prices or {}
        self.lock = threading.Lock()
        self.locks = {}            # per target (state.db difference) and per session: one turn at a time
        self.turns_total = 0
        self.turns_by_label = collections.Counter()
        self.tokens_used = 0
        self.tok_in = self.tok_out = self.tok_cache = 0
        self.unmetered = 0
        self.results = {}          # tag_id -> row
        self.killed = False
        self.stop_reason = ""
        self._kill_ran = False
        self.opts = {"endpoint": args.endpoint, "turn_timeout": args.turn_timeout, "poll_s": args.poll_s, "session_header": args.session_header,
                     "stop": lambda: self.killed or os.path.exists(self.args.kill_file)}

    def lock_for(self, key):
        with self.lock:
            return self.locks.setdefault(key, threading.Lock())

    def kill_requested(self):
        if self.killed:
            return True
        if os.path.exists(self.args.kill_file):
            self.stop("kill file")
            return True
        return False

    def stop(self, why):
        """Mark the run stopped and run the operator's on_kill_cmd once, now (not at the end of the simulated day)."""
        with self.lock:
            if not self.killed:
                self.killed, self.stop_reason = True, why
            run_cmd = not self._kill_ran
            self._kill_ran = True
        cmd = self.cfg.get("on_kill_cmd")
        if run_cmd and cmd and isinstance(cmd, list):
            try:
                subprocess.run(cmd, timeout=60, capture_output=True)
            except (OSError, subprocess.SubprocessError):
                pass

    def cap_check(self, n, force=False):
        """cap_check_cmd: before the first turn, every --cap-check-every turns after it, and always when forced (the runaway turn)."""
        cmd, every = self.cfg.get("cap_check_cmd"), self.args.cap_check_every
        if not cmd or not isinstance(cmd, list):
            return
        if not force and not (n == 1 or (every and n % every == 0)):
            return
        try:
            r = subprocess.run(cmd, timeout=120, capture_output=True)
            if r.returncode != 0:
                self.stop("cap_check_cmd exited %d" % r.returncode)
        except (OSError, subprocess.SubprocessError):
            self.stop("cap_check_cmd could not run")

    def budget_reason(self):
        a = self.args
        if a.max_tokens and self.tokens_used >= a.max_tokens:
            return f"token budget reached ({self.tokens_used} of {a.max_tokens})"
        if a.max_usd and self.prices:
            used = self.usd_used()
            if used >= a.max_usd:
                return f"dollar budget reached ({used:.4f} of {a.max_usd})"
        return ""

    def budget_stop(self):
        why = self.budget_reason()
        if why:
            self.stop(why)
        return bool(why)

    def usd_used(self):
        return max((usd_of(self.tok_in, self.tok_out, self.tok_cache, p, self.args.cache_in_input) for p in self.prices.values()), default=0.0)

    def account(self, out):
        """Add a finished turn to the budget: the state.db difference first, else the API usage. A turn with no figure cannot be budgeted."""
        db, api = out.get("db_delta"), out.get("api_usage")
        if db and (db.get("input") or db.get("output")):
            i, o, c = db["input"] or 0, db["output"] or 0, db.get("cache_read") or 0
        elif api:
            i, o, c = api["input"] or 0, api["output"] or 0, 0
        else:
            i = o = c = None
        with self.lock:
            if i is None:
                if out.get("error_code") != "connect":      # a refused connection spent nothing; any other turn without a figure may have
                    self.unmetered += 1
            else:
                self.tok_in += i
                self.tok_out += o
                self.tok_cache += c
                self.tokens_used += i + o + c
        if i is None and out.get("error_code") != "connect" and (self.args.max_tokens or self.args.max_usd):
            self.stop("a turn reported no token figure (no state.db, no usage): the budget cannot be enforced")

    def session_for(self, ev, st):
        if not self.opts["session_header"]:
            return ""
        if ev["etype"] == "E3" and self.args.continue_e3:
            return f"syn-{self.run_id}-owner-{st['role']}"
        if not ev["fresh_session"]:
            return ""
        return f"syn-{self.run_id}-{ev['id']}"          # one session per EVENT: its steps share it

    def do_step(self, ev, st):
        row = {"tag_id": st["tag_id"], "event": ev["id"], "etype": ev["etype"], "step": st["idx"], "role": st["role"], "kind": ev["kind"],
               "sim_s": ev["sim_s"] + st["after_s"], "gpu_seconds_declared": st["gpu_seconds"], "prompt_chars_sent": len(st["text"])}
        t = pick_target(self.targets, st["role"], self.scen["profile"])
        if ev["kind"] == "marker":
            row.update(status="marker")
        elif t is None:
            row.update(status="skipped", skip_reason="no_target_for_role")
        elif ev["kind"] == "task" and st["idx"] == 1 and not t.get("tareas"):      # later steps (approvals) are plain owner turns
            row.update(status="skipped", skip_reason="target_has_no_tareas", target=t["label"])
        elif self.kill_requested() or self.budget_stop():
            row.update(status="skipped", skip_reason="stopped", target=t["label"])
        else:
            cap = self.caps_by_label.get(t["label"], self.args.max_turns_per_bot or 0)
            with self.lock:
                over = self.turns_total >= self.max_turns or self.turns_by_label[t["label"]] >= cap
                if not over:
                    self.turns_total += 1
                    self.turns_by_label[t["label"]] += 1
                    n = self.turns_total
            if over:
                row.update(status="skipped", skip_reason="turn_cap", target=t["label"])
            else:
                runaway = self.args.mode == "b" and ev["etype"] == "E8"
                self.cap_check(n, force=runaway)
                if self.killed:                                  # the cap check (or a kill) stopped the run before this turn started
                    with self.lock:
                        self.turns_total -= 1
                        self.turns_by_label[t["label"]] -= 1
                    row.update(status="skipped", skip_reason="stopped", target=t["label"])
                else:
                    row.update(self.run_turn(t, ev, st), target=t["label"])
                    self.account(row)
                    if runaway and row.get("error_code") == "timeout":
                        self.stop("the runaway turn timed out (the stack's agent may still be running): on_kill_cmd run")
        with self.lock:
            self.results[st["tag_id"]] = row
        return row

    def run_turn(self, t, ev, st):
        key = self.keys[t["name"]]
        session = self.session_for(ev, st)
        db = t.get("state_db")
        sl = self.lock_for("session:" + session) if session and ev["etype"] == "E3" and self.args.continue_e3 else None
        if sl:
            sl.acquire()                    # a continued conversation is one turn at a time
        try:
            if db:
                with self.lock_for("db:" + t["name"]):          # one turn at a time on this target, so the difference belongs to this turn
                    before = usage_snapshot(db)
                    res = send_turn(t, key, st["text"], session, self.opts)
                    dd = delta(usage_snapshot(db), before)
            else:
                res, dd = send_turn(t, key, st["text"], session, self.opts), None
        finally:
            if sl:
                sl.release()
        out = {"status": "ok" if not res["error_code"] else "error", "error_code": res["error_code"], "http_status": res["http_status"],
               "seconds": res["seconds"], "answer_chars": res["answer_chars"], "finish": res["finish"], "run_status": res["run_status"]}
        if res["api_usage"]:
            out["api_usage"] = {"input": res["api_usage"][0], "output": res["api_usage"][1]}
        if dd:
            out["db_delta"] = dd
        return out

    def execute(self, events):
        """Replay the events. The kill file is polled every half second, also while waiting for the next event; Ctrl-C stops the same way."""
        speed = self.args.speed
        t0 = time.time()
        todo = []
        for ev in events:
            for st in ev["steps"]:
                todo.append((ev["sim_s"] + st["after_s"], ev, st))
        todo.sort(key=lambda x: (x[0], x[2]["tag_id"]))
        pool = ThreadPoolExecutor(max_workers=self.args.workers if speed else 1)
        futs = []
        try:
            for sim, ev, st in todo:
                if speed:
                    while True:                       # the clock starts at the first event
                        wait = t0 + (sim - todo[0][0]) / speed - time.time()
                        if wait <= 0 or self.kill_requested():
                            break
                        time.sleep(min(0.5, wait))
                if speed:
                    futs.append(pool.submit(self.do_step, ev, st))
                else:
                    self.do_step(ev, st)
            for f in futs:
                f.result()
        except KeyboardInterrupt:
            self.stop("interrupted (Ctrl-C)")
            pool.shutdown(wait=False, cancel_futures=True)
            return
        pool.shutdown(wait=True)


# ---------------------------------------------------------------------------------------------------------------- counters from other places
def fetch_json(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read(4 * 1024 * 1024))
    except (OSError, ValueError):
        return None


def stub_snapshots(cfg):
    out = {}
    for name, url in (cfg.get("stubs") or {}).items():
        d = fetch_json(url.rstrip("/") + "/_counters")
        if d:
            out[name] = d
    return out


def stub_delta(after, before):
    out = {}
    for name, a in after.items():
        b = (before.get(name) or {})
        calls = {k: v - (b.get("calls") or {}).get(k, 0) for k, v in (a.get("calls") or {}).items()}
        out[name] = {"calls": {k: v for k, v in calls.items() if v}, "gpu_seconds": round((a.get("gpu_seconds") or 0) - (b.get("gpu_seconds") or 0), 2)}
    return out


def lines_of(path):
    """The log and its older generation (NAME.1.jsonl), oldest first; a missing file is just nothing."""
    cand = [path[:-6] + ".1.jsonl" if path.endswith(".jsonl") else path + ".1", path]
    for p in cand:
        try:
            with open(p, errors="replace") as f:
                for ln in f:
                    yield ln
        except OSError:
            continue


def pct(vals, q):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 2)


def scan_eval_log(path, t0, t1):
    """Counts from the router's .model-eval.jsonl inside [t0, t1]: calls by model and result, tokens when reported, neurons, peak calls per minute and hour."""
    models, stamps, neurons = {}, [], 0.0
    aux = calls = 0
    for ln in lines_of(path):
        try:
            r = json.loads(ln)
            ts = float(r["ts"])
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(r, dict) or not (t0 <= ts <= t1):
            continue
        calls += 1
        aux += 1 if r.get("aux") else 0
        stamps.append(ts)
        m = models.setdefault(str(r.get("model", "?"))[:80], {"calls": 0, "results": collections.Counter(), "tok": 0, "tok_calls": 0, "ttfb": []})
        m["calls"] += 1
        m["results"][str(r.get("result", "?"))[:30]] += 1
        if as_int(r.get("tok")):
            m["tok"] += r["tok"]
            m["tok_calls"] += 1
        if isinstance(r.get("ttfb"), (int, float)):
            m["ttfb"].append(r["ttfb"])
        if isinstance(r.get("neurons"), (int, float)):
            neurons += r["neurons"]

    def peak(window):
        best, j = 0, 0
        for i, s in enumerate(stamps):
            while s - stamps[j] >= window:
                j += 1
            best = max(best, i - j + 1)
        return best
    stamps.sort()
    return {"calls": calls, "aux_calls": aux, "neurons": round(neurons, 1), "neurons_pct_of_10000": round(neurons / 100.0, 2),
            "peak_calls_per_minute": peak(60), "peak_calls_per_hour": peak(3600),
            "models": {k: {"calls": v["calls"], "results": dict(v["results"]), "completion_tokens_reported": v["tok"], "calls_with_tokens": v["tok_calls"],
                           "ttfb_p50": pct(v["ttfb"], .5)} for k, v in models.items()}}


def scan_gateway_log(path, t0, t1):
    gws, routes = {}, collections.Counter()
    for ln in lines_of(path):
        try:
            r = json.loads(ln)
            ts = float(r["ts"])
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(r, dict) or not (t0 <= ts <= t1):
            continue
        g = str(r.get("gateway", "?"))[:30]
        if g == "router":
            routes[f"{r.get('route', '?')}/{r.get('reason', '?')}"[:60]] += 1
            continue
        d = gws.setdefault(g, {"lines": 0, "ok": 0, "errors": 0, "gpu_seconds": 0.0, "cpu_seconds": 0.0})
        d["lines"] += 1
        d["ok" if r.get("ok") else "errors"] += 1
        for k in ("gpu_seconds", "cpu_seconds"):
            if isinstance(r.get(k), (int, float)):
                d[k] += r[k]
    for d in gws.values():
        d["gpu_seconds"], d["cpu_seconds"] = round(d["gpu_seconds"], 1), round(d["cpu_seconds"], 1)
    return {"gateways": gws, "router_routes": dict(routes)}


WAKER_RE = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[([a-z0-9-]+)\] (.*)$")


def scan_waker(path, t0, t1, stacks):
    """Counts from the waker's journal text (UTC stamps) for the given stacks: wakes, `ready after` seconds, boot failures, evictions, postponed wakes, footprint."""
    out = {s: {"wakes": 0, "ready_after_s": [], "boot_failures": 0, "evictions": 0, "postponed": 0, "footprint_mb_max": None, "host_avail_mb_min": None}
           for s in stacks}
    try:
        f = open(path, errors="replace")
    except OSError:
        return {}
    with f:
        for ln in f:
            m = WAKER_RE.search(ln)
            if not m or m.group(2) not in out:
                continue
            try:
                ts = calendar.timegm(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                continue
            if not (t0 - 2 <= ts <= t1 + 2):
                continue
            d, msg = out[m.group(2)], m.group(3)
            if msg.startswith("waking ("):
                d["wakes"] += 1
            elif msg.startswith("ready after "):
                g = re.match(r"ready after ([\d.]+)s", msg)
                if g:
                    d["ready_after_s"].append(float(g.group(1)))
            elif "boot did not finish" in msg:
                d["boot_failures"] += 1
            elif "evicted by the RAM guard" in msg:
                d["evictions"] += 1
            elif "wake postponed" in msg:
                d["postponed"] += 1
            g = re.match(r"footprint (\d+)MB, host avail=(\d+)MB", msg)
            if g:
                d["footprint_mb_max"] = max(d["footprint_mb_max"] or 0, int(g.group(1)))
                d["host_avail_mb_min"] = min(d["host_avail_mb_min"] if d["host_avail_mb_min"] is not None else 1 << 30, int(g.group(2)))
    return out


# ---------------------------------------------------------------------------------------------------------------- merging and estimating
def rel_diff(a, b):
    return abs(a - b) / max(a, b, 1)


def merge_tokens(row, fake_event, mode, tol=0.15):
    """Pick the best token source for a row: state.db difference, then the API's usage, then the fake model's request-size estimate.
    tokens_source says where the figure came from; tokens_method is how far to trust it: in mode a EVERY figure is the fake model's estimate
    (the stack only relays what the fake said), so it is labelled fake_estimate whatever file it was read from."""
    db, api = row.get("db_delta"), row.get("api_usage")
    calls = tools = cache = None
    if db and (db.get("input") or db.get("output")):
        inp, out, src = db["input"], db["output"], "state_db"
        cache = db.get("cache_read")
        calls, tools = db.get("calls"), db.get("tool_calls")
    elif api:
        inp, out, src = api["input"], api["output"], "api"
    elif fake_event and fake_event.get("calls"):
        inp, out, src = fake_event["prompt_tokens"], fake_event["completion_tokens"], "request_estimate"
    else:
        inp = out = None
        src = "none"
    if src == "none":
        method = "none"
    elif mode == "a":
        method = "fake_estimate"
    else:
        method = {"state_db": "reported_state_db", "api": "reported_api", "request_estimate": "estimated_request"}[src]
    if fake_event and fake_event.get("calls"):
        calls = calls if calls is not None else fake_event["calls"]
        tools = tools if tools is not None else fake_event["tool_calls"]
    row.update(input_tokens=inp, output_tokens=out, cache_read_tokens=cache, tokens_method=method, tokens_source=src, model_calls=calls, tool_calls=tools)
    if db and api and src == "state_db" and (rel_diff(db["input"] or 0, api["input"] or 0) > tol or rel_diff(db["output"] or 0, api["output"] or 0) > tol):
        row["usage_mismatch"] = True
    if fake_event and fake_event.get("calls"):
        row["tool_errors"] = fake_event.get("tool_errors", 0)
        row["fake_estimate"] = {"input": fake_event["prompt_tokens"], "output": fake_event["completion_tokens"], "chars": fake_event["chars"],
                                "no_usage_calls": fake_event.get("no_usage", 0), "tool_missing": fake_event.get("tool_missing", 0)}
    return row


def aggregate_events(events, rows):
    out = []
    for ev in events:
        rs = [rows[s["tag_id"]] for s in ev["steps"] if s["tag_id"] in rows]
        done = [r for r in rs if r["status"] in ("ok", "error")]

        def tot(k):
            vals = [r.get(k) for r in done if r.get(k) is not None]
            return sum(vals) if vals else None
        ok = [r for r in done if r["status"] == "ok"]
        out.append({"id": ev["id"], "etype": ev["etype"], "name": ev["name"], "role": ev["role"], "kind": ev["kind"], "sim_clock": clock(ev["sim_s"]),
                    "status": ("marker" if ev["kind"] == "marker" else "skipped" if not done else
                               "partial" if len(done) < len(rs) else "ok" if len(ok) == len(done) else "error"),     # partial: some steps were skipped
                    "skip_reason": next((r["skip_reason"] for r in rs if r.get("skip_reason")), ""),
                    "steps_sent": len(done), "errors": [r["error_code"] for r in done if r.get("error_code")],
                    "calls": tot("model_calls"), "input_tokens": tot("input_tokens"), "output_tokens": tot("output_tokens"),
                    "cache_read_tokens": tot("cache_read_tokens"), "tool_calls": tot("tool_calls"), "tool_errors": tot("tool_errors"),
                    "seconds": round(sum(r.get("seconds", 0) for r in done), 2),
                    "tokens_methods": sorted({r["tokens_method"] for r in done}), "gpu_seconds_declared": sum(r["gpu_seconds_declared"] for r in rs),
                    "ext_declared": ev["ext"], "hops_declared": [h["role"] for h in ev["hops"]], "depth_planned": len(ev["hops"]),
                    "turns": [{**{k: r.get(k) for k in ("tag_id", "step", "role", "target", "status", "error_code", "http_status", "seconds", "answer_chars",
                                                        "prompt_chars_sent", "input_tokens", "output_tokens", "cache_read_tokens", "tokens_method",
                                                        "tokens_source", "model_calls", "tool_calls", "tool_errors")},
                               "request_chars": (r.get("fake_estimate") or {}).get("chars")}
                              for r in rs]})
    return out


def union_minutes(intervals):
    ivs = sorted(intervals)
    total, cur = 0.0, None
    for a, b in ivs:
        if cur and a <= cur[1]:
            cur[1] = max(cur[1], b)
        else:
            if cur:
                total += cur[1] - cur[0]
            cur = [a, b]
    if cur:
        total += cur[1] - cur[0]
    return total / 60.0


def merged(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def awake_model(events, rows, boot_s):
    """SYNTHETIC_DAY.md 5.4: per role, a cluster is a run of activity less than 10 minutes apart; awake = span + boot + 10 minutes idle.
    EVERY step and hop of the script counts, whether or not it was sent: a step that was measured keeps its measured seconds; one that was skipped
    (a target without tareas, a cap, a kill, no target for the role) keeps the script's `active_s` (default 60 s) and is counted as assumed; the
    hops of an event are always the script's `active_s` (assumed). Leaving skipped events out made the capacity table come out too high."""
    acts = collections.defaultdict(list)
    total_steps = assumed_steps = 0
    for ev in events:
        if ev["kind"] == "marker":
            continue
        for st in ev["steps"]:
            total_steps += 1
            s = ev["sim_s"] + st["after_s"]
            r = rows.get(st["tag_id"])
            if r and r["status"] in ("ok", "error"):
                dur = max(1.0, r.get("seconds", 1.0))
            else:
                dur = float(st.get("active_s", ASSUMED_ACTIVE_S))
                assumed_steps += 1
            acts[st["role"]].append((s, s + dur))
        for h in ev["hops"]:
            s = ev["sim_s"] + int(h.get("after_s", 0))
            acts[h["role"]].append((s, s + float(h.get("active_s", ASSUMED_ACTIVE_S))))
    per_role, all_iv = {}, []
    for role, lst in acts.items():
        lst.sort()
        clusters, cur = [], None
        for a, b in lst:
            if cur and a - cur[1] < IDLE_S:
                cur[1] = max(cur[1], b)
            else:
                cur = [a, b]
                clusters.append(cur)
        ivs = [(c[0], c[1] + boot_s + IDLE_S) for c in clusters]       # first start + span + boot + idle
        per_role[role] = {"wakes": len(clusters), "awake_minutes": round(union_minutes(ivs), 1)}
        all_iv += [tuple(x) for x in merged(ivs)]
    edges = sorted([(a, 1) for a, b in all_iv] + [(b, -1) for a, b in all_iv], key=lambda x: (x[0], x[1]))
    cur = peak = 0
    peak_at = 0
    for t, d in edges:
        cur += d
        if cur > peak:
            peak, peak_at = cur, t
    return {"per_role": per_role, "peak_concurrent_awake_bots": peak, "peak_at_sim_clock": clock(int(peak_at)) if peak else "",
            "boot_seconds_used": round(boot_s, 1), "hop_activity_is_assumed": True, "steps_total": total_steps, "steps_assumed": assumed_steps}


def capacity(peak):
    out = {"assumptions": {"gb_per_awake_bot": GB_PER_AWAKE_BOT, "host_reserve_gb": HOST_RESERVE_GB}, "peak_awake_bots": peak, "businesses_by_vm_gb": {}}
    if not peak:
        return out
    for ram in (16, 32, 64):
        use = ram - HOST_RESERVE_GB
        out["businesses_by_vm_gb"][str(ram)] = {"f_1.0": int(use // (peak * GB_PER_AWAKE_BOT)), "f_0.5": int(use // (0.5 * peak * GB_PER_AWAKE_BOT))}
    return out


def unit_costs(events_agg):
    """Per event type: median and p90 of calls, input, output, cache reads, tool calls, active seconds over the instances that were measured; assumed otherwise."""
    out = {}
    for et in sorted({e["etype"] for e in events_agg}, key=lambda k: int(k[1:])):
        es = [e for e in events_agg if e["etype"] == et and e["status"] in ("ok",) and e["input_tokens"] is not None]
        u = {"measured_instances": len(es), "source": "measured" if es else "assumed"}
        if es:
            for k in ("calls", "input_tokens", "output_tokens", "cache_read_tokens", "tool_calls", "seconds"):
                vals = [e[k] for e in es if e[k] is not None]
                u[k] = {"p50": pct(vals, .5), "p90": pct(vals, .9)} if vals else None
            u["gpu_seconds_declared"] = pct([e["gpu_seconds_declared"] for e in es], .5)
        else:
            c, i, o = SENDER_FIRST_ORDER.get(et) or FIRST_ORDER.get(et, (0, 0, 0))
            u.update(calls={"p50": c, "p90": c}, input_tokens={"p50": i, "p90": i}, output_tokens={"p50": o, "p90": o}, cache_read_tokens={"p50": 0, "p90": 0})
        out[et] = u
    return out


def projections(scen, units, prices, gpu_price_hr, cache_in_input=False):
    """Day totals for each load = sum(volume x unit cost p50), plus, for E2 and E4 only, the receiver rung of every hop at the first-order cost
    (assumed: the rung that wakes runs untagged). E5 and E7 first-order rows already span every bot of the event, so they get no add-on; an assumed E4
    is priced as its sender (an owner turn, like E3) plus the receiver add-on. Month = 4 quiet + 22 normal + 4 busy."""
    res = {}
    for load in ("quiet", "normal", "busy"):
        vols = scen["loads"][load]
        tot = {"calls": 0.0, "input_tokens": 0.0, "output_tokens": 0.0, "cache_read_tokens": 0.0, "gpu_seconds": 0.0}
        used_assumed = set()
        for et, n in vols.items():
            if not n or et in ("E8", "E10"):
                continue
            u = units.get(et)
            c, i, o = (u["calls"]["p50"], u["input_tokens"]["p50"], u["output_tokens"]["p50"]) if u else (SENDER_FIRST_ORDER.get(et) or FIRST_ORDER.get(et, (0, 0, 0)))
            cr = ((u.get("cache_read_tokens") or {}).get("p50") if u else 0) or 0
            if not u or u["source"] == "assumed":
                used_assumed.add(et)
            tot["calls"] += n * (c or 0)
            tot["input_tokens"] += n * (i or 0)
            tot["output_tokens"] += n * (o or 0)
            tot["cache_read_tokens"] += n * cr
            tot["gpu_seconds"] += n * ((u or {}).get("gpu_seconds_declared") or scen["events"][et].get("gpu_seconds", 0) or 0)
            hops = len(scen["events"][et].get("hops") or [])
            if hops and et in RECEIVER_ADDON:
                tot["calls"] += n * hops * RECEIVER_SIDE[0]
                tot["input_tokens"] += n * hops * RECEIVER_SIDE[1]
                tot["output_tokens"] += n * hops * RECEIVER_SIDE[2]
        tot = {k: round(v) for k, v in tot.items()}
        tot["assumed_event_types"] = sorted(used_assumed)
        tot["receiver_side_assumed"] = True
        res[load] = tot
    month = {k: sum(MIX[l] * res[l][k] for l in MIX) for k in ("calls", "input_tokens", "output_tokens", "cache_read_tokens", "gpu_seconds")}
    res["month_4q_22n_4b"] = month
    for name, price in prices.items():
        for k, v in list(res.items()):
            usd = usd_of(v["input_tokens"], v["output_tokens"], v["cache_read_tokens"], price, cache_in_input)
            usd += (v["gpu_seconds"] / 3600.0 * gpu_price_hr) if gpu_price_hr else 0
            v.setdefault("usd", {})[name] = round(usd, 3)
    return res


def calibrate(a, b):
    """OFFLINE: the characters-per-token ratio, from a mode a and a mode b report of the same profile, load and seed (so the same tags, roles and
    templates). Per turn: the fake model's request characters per model call in A, divided by the provider's input tokens per model call in B (state.db
    or API figures, both with a call count). Approximate: B's agent makes its own tool rounds, so the requests differ in size; the per-call mean
    and the spread over turns are what this reports. Never computed inside a single run: in mode a the 'reported' tokens are the fake's own estimate."""
    if a.get("mode") != "a" or b.get("mode") != "b":
        raise Refuse("--calibrate takes a mode a report first and a mode b report second")
    for k in ("profile", "load", "seed"):
        if a.get(k) != b.get(k):
            raise Refuse(f"--calibrate: the reports differ in {k} ({a.get(k)!r} and {b.get(k)!r}): same profile, load and seed are needed")
    ta = {t["tag_id"]: t for e in a["events"] for t in e["turns"]}
    ratios, by_et = [], collections.defaultdict(list)
    for e in b["events"]:
        for t in e["turns"]:
            x = ta.get(t["tag_id"])
            if not x or not x.get("request_chars") or not x.get("model_calls"):
                continue
            if t.get("tokens_method") not in ("reported_state_db", "reported_api") or not t.get("input_tokens") or not t.get("model_calls"):
                continue
            r = (x["request_chars"] / x["model_calls"]) / (t["input_tokens"] / t["model_calls"])
            ratios.append(r)
            by_et[e["etype"]].append(r)
    return {"chars_per_token_p50": pct(ratios, .5), "p10": pct(ratios, .1), "p90": pct(ratios, .9), "n_turns": len(ratios),
            "by_event_type": {k: {"p50": pct(v, .5), "n": len(v)} for k, v in sorted(by_et.items())},
            "caveat": "per-call means of two different runs of the same script: B's own tool rounds change the request sizes; use the p50 and the spread, not one turn"}


# ---------------------------------------------------------------------------------------------------------------- planning and caps
def plan_turns(scen, cfg, load, seed):
    """-> (planned turns that will be sent, planned per target label, has an E8 runaway event). A marker, a step with no target and the first step of a
    task event on a target without tareas are not sent, so they are not counted."""
    events = build_timeline(scen, load, seed, f"{scen['profile']}-{load}-plan-r1")
    total, by, e8 = 0, collections.Counter(), False
    for ev in events:
        if ev["kind"] == "marker":
            continue
        e8 = e8 or ev["etype"] == "E8"
        for st in ev["steps"]:
            t = pick_target(cfg["targets"], st["role"], scen["profile"])
            if t is None or (ev["kind"] == "task" and st["idx"] == 1 and not t.get("tareas")):
                continue
            total += 1
            by[t["label"]] += 1
    return total, by, e8


def with_margin(n):
    return int(math.ceil(n * CAP_MARGIN)) + 3


def resolve_caps(scen, cfg, args, seeds):
    """The hard caps of a run and what they are measured against. Defaults come from the plan (the most any repeat plans) plus a margin; an explicit
    --max-turns / --max-turns-per-bot is used as given. -> (max_turns, caps_by_label, planned_total, planned_by_label, truncates, has_e8)."""
    total, by, e8 = 0, collections.Counter(), False
    for sd_ in seeds:
        t, b, e = plan_turns(scen, cfg, args.load, sd_)
        total, e8 = max(total, t), e8 or e
        for k, v in b.items():
            by[k] = max(by[k], v)
    max_turns = args.max_turns if args.max_turns is not None else with_margin(total)
    caps = {k: (args.max_turns_per_bot if args.max_turns_per_bot is not None else with_margin(v)) for k, v in by.items()}
    truncates = total > max_turns or any(by[k] > caps[k] for k in by)
    return max_turns, caps, total, by, truncates, e8


# ---------------------------------------------------------------------------------------------------------------- the probe (mode a)
def probe_fake(cfg, scen):
    """Mode a: prove, before anything else is sent, that each target's model is the fake. One tagged turn per target (event E0-01: a one-line reply, no
    tool call), then the fake's /counters for that probe. A target the fake did not see is refused: nothing but the probes was sent."""
    fake_url = (cfg.get("fake_llm") or "").rstrip("/")
    if not re.match(r"^https?://[^/\s]+$", fake_url):
        raise Refuse("mode a needs \"fake_llm\" in the private config: http(s)://host:port of ops/synth_fake_llm.py (it proves each stack talks to it)")
    if fetch_json(fake_url + "/health") is None:
        raise Refuse("mode a: the fake model at fake_llm is not answering /health: start ops/synth_fake_llm.py first (nothing was sent to any stack)")
    opts = {"endpoint": "chat", "turn_timeout": 120, "poll_s": 1.0, "session_header": ""}
    for t in cfg["targets"]:
        pid = f"{scen['profile']}-probe-{hashlib.sha256(os.urandom(8)).hexdigest()[:8]}"
        res = send_turn(t, read_key(t), f"[SYN:{pid}:E0-01] probe", "", opts)
        seen = fetch_json(f"{fake_url}/counters?run={pid}")
        if not seen or not seen.get("events"):
            raise Refuse(f"mode a: target {t['label']!r} did not reach the fake model (probe answer: http {res['http_status']} {res['error_code'] or 'ok'}): its model is not "
                         f"pointed at fake_llm (SYNTHETIC_DAY.md section 10, step 3). Nothing but the probes was sent. If this stack is still on a real "
                         f"provider the probe was one small real turn; fix that before anything else")


# ---------------------------------------------------------------------------------------------------------------- one run and the report
def run_one(scen, cfg, args, rep, seed, prices):
    run_id = f"{scen['profile']}-{args.load}-{args.mode}-r{rep}-{int(time.time()) % 10**7:x}{os.urandom(2).hex()}"      # random tail: two runs in the same second must not share a fake-model counter
    assert RUN_OK.match(run_id)
    events = build_timeline(scen, args.load, seed, run_id)
    max_turns, caps, planned, planned_by, truncates, _ = resolve_caps(scen, cfg, args, [seed])
    say(f"run {rep}: planned {planned} turns {dict(planned_by)}; caps {max_turns} in total, per target {caps}" + (" (WILL TRUNCATE the day)" if truncates else ""))
    run = Run(scen, cfg, args, run_id, seed, (max_turns, caps), prices)
    stubs_before = stub_snapshots(cfg)
    t0 = time.time()
    run.execute(events)
    t1 = time.time()
    rows = run.results
    fake_url = (cfg.get("fake_llm") or "").rstrip("/")
    fake = fetch_json(f"{fake_url}/counters?run={run_id}") if fake_url else None
    fake_events = {}
    if fake:
        for tag, c in fake["events"].items():
            m = TAG_RE.match(tag)
            if m:
                fake_events[tag.rsplit(":", 1)[1].rstrip("]")] = c
    for tid, r in rows.items():
        if r["status"] in ("ok", "error"):
            merge_tokens(r, fake_events.get(tid), args.mode, args.usage_tolerance)
    agg = aggregate_events(events, rows)
    sent = [r for r in rows.values() if r["status"] in ("ok", "error")]
    warnings = []
    if truncates:
        warnings.append(f"the caps are below the plan (planned {planned} turns, cap {max_turns}; per target {dict(planned_by)} against {caps}): the day was truncated, turn_cap skips")
    if args.mode == "a" and sent and not fake:
        warnings.append("mode a but the fake model's /counters could not be read (config fake_llm): tokens come only from the API's usage")
    if args.mode == "a" and fake and sent and not fake_events:
        warnings.append("the fake model saw none of this run's events: the stack is not pointed at it (see SYNTHETIC_DAY.md section 10)")
    if args.mode == "b" and fake_events:
        warnings.append("mode b but the fake model saw this run's events: the stack is on the fake, not on real providers")
    for tid, r in rows.items():
        if r["status"] == "ok" and r.get("tokens_method") == "none":
            warnings.append("no token figure for some turns (no usage in the API answer, no state_db, no fake counters)")
            break
    nerr = sum(r.get("tool_errors") or 0 for r in sent)
    if nerr:
        warnings.append(f"{nerr} tool result(s) looked like a usage error or a failed command (tool_errors): a scripted command did not do what the script meant "
                        f"(for example `gateway tareas nueva` refused, or a proposed gateway that does not exist yet); the numbers include the failed round trips")
    for ev in events:
        s1 = rows.get(ev["steps"][0]["tag_id"]) if ev["steps"] else None
        if ev["kind"] == "task" and s1 and s1["status"] in ("ok", "error") and (s1.get("tool_errors") or 0):
            warnings.append("a task event's first step had a failing tool result: no task was created for it, so there was no hop (E2, E4 and E7 hand-downs did not happen)")
            break
    mism = sum(1 for r in sent if r.get("usage_mismatch"))
    if mism:
        warnings.append(f"state.db and the API's usage differ by more than {int(args.usage_tolerance * 100)} percent on {mism} turn(s): Hermes's figure may be its own estimate, "
                        f"may include other traffic on that state.db, or the API usage may cover only the last call; do not trust either until checked once by hand")
    cache_tot = sum(r.get("cache_read_tokens") or 0 for r in sent)
    if cache_tot:
        warnings.append(f"cache_read_tokens {cache_tot}: it is not known whether input_tokens includes them; dollars follow --cache-in-input "
                        f"({'included in input' if args.cache_in_input else 'separate from input'}) and bill cache reads at the cached price of --price (else the input price)")
    logs = cfg.get("logs") or {}
    waker_stacks = [t["name"] for t in run.targets]
    waker = scan_waker(logs["waker"], t0, t1, waker_stacks) if logs.get("waker") else {}
    waker_by_label = {t["label"]: waker[t["name"]] for t in run.targets if t["name"] in waker}
    ready = [x for w in waker_by_label.values() for x in w["ready_after_s"]]
    task_sent = [ev for ev in events if ev["kind"] == "task" and ev["hops"] and ev["steps"] and (rows.get(ev["steps"][0]["tag_id"]) or {}).get("status") == "ok"]
    if task_sent:
        if logs.get("waker") and not any(w["wakes"] for w in waker_by_label.values()):
            warnings.append(f"{len(task_sent)} task event(s) were sent but the waker journal shows no wake in the window: no hop happened (no task filed, or the hook did not wake anyone)")
        elif not logs.get("waker"):
            warnings.append(f"{len(task_sent)} task event(s) were sent and hops are not observed (no waker journal in the config): whether the tasks reached the next rung is unverified")
    boot_s = statistics.median(ready) if ready else args.boot_seconds
    awake = awake_model(events, rows, boot_s)
    awake["boot_source"] = "waker journal median" if ready else "assumed"
    if awake["steps_assumed"]:
        warnings.append(f"awake minutes and capacity were computed with {awake['steps_assumed']} of {awake['steps_total']} steps ASSUMED (skipped or not sent: "
                        f"{dict(collections.Counter(r['skip_reason'] for r in rows.values() if r['status'] == 'skipped'))}) at {ASSUMED_ACTIVE_S:g} s each unless the script says otherwise, "
                        f"plus every hop at its script active_s")
    units = unit_costs(agg)
    for w in waker_by_label.values():
        w["ready_after_s_p50"] = pct(w["ready_after_s"], .5)
        w["ready_after_s"] = len(w["ready_after_s"])
    secs = [r["seconds"] for r in sent if r["status"] == "ok"]
    totals = {"events": len(events), "turns_sent": len(sent), "turns_ok": sum(1 for r in sent if r["status"] == "ok"),
              "turns_error": sum(1 for r in sent if r["status"] == "error"), "turns_skipped": sum(1 for r in rows.values() if r["status"] == "skipped"),
              "skipped_by_reason": dict(collections.Counter(r["skip_reason"] for r in rows.values() if r["status"] == "skipped")),
              "errors_by_code": dict(collections.Counter(r["error_code"] for r in sent if r["error_code"])),
              "model_calls": sum(r["model_calls"] or 0 for r in sent), "input_tokens": sum(r["input_tokens"] or 0 for r in sent),
              "output_tokens": sum(r["output_tokens"] or 0 for r in sent), "cache_read_tokens": cache_tot, "tool_calls": sum(r["tool_calls"] or 0 for r in sent),
              "tool_errors": nerr, "tokens_methods": dict(collections.Counter(r["tokens_method"] for r in sent)),
              "seconds_p50": pct(secs, .5), "seconds_p95": pct(secs, .95), "gpu_seconds_declared": sum(r["gpu_seconds_declared"] for r in sent),
              "planned_turns": planned, "cap_turns": max_turns}
    notes = ["Counts and sizes only: no message, answer or task text, no key, no stack name.",
             "Compressed clock: waker idle timers, boot time and RAM do not compress, so a compressed run is MORE crowded than a real day; awake minutes are computed from the script times and measured seconds (assumed for steps that were not sent), not read from the compressed run.",
             "Hop rungs (a bot woken by a task) are not driven or counted here; their cost in the projection is the first-order receiver side of E2 and E4 (assumed).",
             "One session per event: a unit cost is a fresh-session cost, not the cost of a long owner conversation" + (" (E3 turns of a role share one session in this run)." if args.continue_e3 else " (use --continue-e3 for the E3 variant)."),
             "state.db differences are Hermes's own figures and include any other traffic on that file during the turn; the API usage is assumed to cover the whole turn (unverified)."]
    if args.mode == "a":
        notes.append("MODE A: every token figure is the fake model's estimate (request characters / ratio) and its scripted output sizes (tokens_method fake_estimate); dollars are for scale only. The characters-per-token ratio comes from `--calibrate` on a mode a and a mode b report, not from this run.")
    report = {
        "run_id": run_id, "script_version": SCRIPT_VERSION, "mode": args.mode, "profile": scen["profile"], "load": args.load, "seed": seed, "repeat": rep,
        "speed": args.speed, "endpoint": args.endpoint, "session_mode": "owner conversation for E3, event for the rest" if args.continue_e3 else "one session per event",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)), "wall_seconds": round(t1 - t0, 1),
        "stopped": run.stop_reason, "targets_by_label": {t["label"]: {"roles": t["roles"], "guest": bool(t.get("guest")), "tareas": bool(t.get("tareas")),
                                                                       "model_tier": t.get("model_tier", "")} for t in run.targets},
        "key_manifest": [{"label": str(k.get("label", ""))[:60], "provider": str(k.get("provider", ""))[:30], "used_by_roles": k.get("roles", [])}
                         for k in (cfg.get("keys") or []) if isinstance(k, dict)],
        "budget": {"max_tokens": args.max_tokens, "max_usd": args.max_usd, "tokens_used": run.tokens_used, "turns_without_figure": run.unmetered},
        "totals": totals, "events": agg, "unit_costs": units, "awake": awake, "capacity": capacity(awake["peak_concurrent_awake_bots"]),
        "projection_from_unit_costs": projections(scen, units, prices, args.gpu_price_per_hour, args.cache_in_input),
        "calibration": None, "calibration_note": "not computed inside a run: python3 ops/synth_day.py --calibrate A.json B.json",
        "fake_model": ({"untagged": fake["untagged"], "totals": fake["totals"], "chars_per_token_assumed": fake["chars_per_token"]} if fake else None),
        "stubs_delta": stub_delta(stub_snapshots(cfg), stubs_before) if cfg.get("stubs") else {},
        "router_eval_log": scan_eval_log(logs["eval"], t0, t1) if logs.get("eval") else None,
        "gateway_log": scan_gateway_log(logs["gateway"], t0, t1) if logs.get("gateway") else None,
        "waker": waker_by_label, "warnings": sorted(set(warnings)), "notes": notes}
    return report, run


def day_ranges(reports, key):
    vals = [r["totals"][key] for r in reports]
    return {"p50": pct(vals, .5), "p10": pct(vals, .1), "p90": pct(vals, .9), "n": len(vals)}


def spread(vals):
    """`p50 (p10 to p90)` of a list over the repeats."""
    p50, p10, p90 = pct(vals, .5), pct(vals, .1), pct(vals, .9)
    return "-" if p50 is None else (f"{p50:g}" if p10 == p90 else f"{p50:g} ({p10:g} to {p90:g})")


def summary_md(reports, prices):
    r0 = reports[0]
    L = [f"# Synthetic day: {r0['profile']} / {r0['load']} / mode {r0['mode'].upper()}", "",
         f"{len(reports)} run(s) (script v{r0['script_version']}, speed {r0['speed']}, endpoint {r0['endpoint']}, {r0['session_mode']}). Counts only. Figures are `p50 (p10 to p90)` over the runs"
         + (" (one run: no spread yet)." if len(reports) == 1 else "."), ""]
    if r0["mode"] == "a":
        L += ["**Mode A: every token figure below is the fake model's estimate (request characters / ratio) and its scripted output sizes. Dollars are for scale only; "
              "the real ratio and the real output sizes come from mode B (`--calibrate`).**", ""]
    if any(r["warnings"] for r in reports):
        L += ["## Warnings", ""] + [f"- {w}" for w in sorted({w for r in reports for w in r["warnings"]})] + [""]
    L += ["## What the runs measured", "", "| Quantity | p50 | p10 | p90 |", "|---|---|---|---|"]
    for k, label in (("planned_turns", "turns planned"), ("turns_sent", "turns sent"), ("turns_error", "turn errors"), ("turns_skipped", "turns skipped"),
                     ("model_calls", "model calls"), ("input_tokens", "input tokens"), ("output_tokens", "output tokens"), ("cache_read_tokens", "cache read tokens"),
                     ("tool_calls", "tool calls"), ("tool_errors", "tool results that failed"), ("seconds_p50", "turn seconds p50"), ("seconds_p95", "turn seconds p95")):
        d = day_ranges(reports, k)
        L.append(f"| {label} | {d['p50']} | {d['p10']} | {d['p90']} |")
    methods = collections.Counter()
    for r in reports:
        methods.update(r["totals"]["tokens_methods"])
    L += ["", f"Token method per turn: {dict(methods)}. `fake_estimate` (mode a): the fake model's request-size estimate, characters / "
          f"{r0['fake_model']['chars_per_token_assumed'] if r0.get('fake_model') else 4.0} (an assumption); `reported_*` (mode b): the provider's or Hermes's own figures, see the notes of the JSON report.", ""]
    skipped = collections.Counter()
    for r in reports:
        skipped.update(r["totals"]["skipped_by_reason"])
    if skipped:
        L += [f"Skipped: {dict(skipped)}. Skipped event types are filled by the first-order table in the projection, and in the awake model by the script's assumed active seconds.", ""]
    L += ["## Unit costs (last run)", "", "| Event | source | instances | calls p50 | input tokens p50 | output tokens p50 | seconds p50 |", "|---|---|---|---|---|---|---|"]
    for et, u in reports[-1]["unit_costs"].items():
        g = lambda k: (u.get(k) or {}).get("p50")
        L.append(f"| {et} | {u['source']} | {u['measured_instances']} | {g('calls')} | {g('input_tokens')} | {g('output_tokens')} | {g('seconds')} |")
    L += ["", "## Awake time and capacity (computed from script times)", "", "| Role | wakes | awake minutes |", "|---|---|---|"]
    for role, d in sorted(reports[-1]["awake"]["per_role"].items()):
        L.append(f"| {role} | {d['wakes']} | {d['awake_minutes']} |")
    a = reports[-1]["awake"]
    L += ["", f"Peak concurrent awake bots: {a['peak_concurrent_awake_bots']} (at about {a['peak_at_sim_clock']}); boot {a['boot_seconds_used']} s ({a['boot_source']}); hop activity assumed; "
          f"{a['steps_assumed']} of {a['steps_total']} steps assumed" + (" (the figure is an ASSUMPTION for those steps)." if a["steps_assumed"] else "."), "",
          "| VM RAM (GB) | businesses at f=1.0 | at f=0.5 |", "|---|---|---|"]
    for ram, d in reports[-1]["capacity"]["businesses_by_vm_gb"].items():
        L.append(f"| {ram} | {d['f_1.0']} | {d['f_0.5']} |")
    L += ["", "Memory only, assuming 1 GB per awake bot and a 4 GB host reserve (both assumptions); CPU, provider limits and the morning correlation may bind first.", "",
          f"## Projection per day and month (unit costs x volumes; p50 and spread over the {len(reports)} run(s))", "",
          "| Load | model calls | input tokens | output tokens | cache read tokens | GPU seconds (declared) |" + "".join(f" USD {n} |" for n in prices),
          "|---|---|---|---|---|---|" + "---|" * len(prices)]
    for load in reports[-1]["projection_from_unit_costs"]:
        pv = [r["projection_from_unit_costs"][load] for r in reports]
        L.append(f"| {load} | " + " | ".join(spread([v[k] for v in pv]) for k in ("calls", "input_tokens", "output_tokens", "cache_read_tokens", "gpu_seconds")) + " |"
                 + "".join(f" {spread([v.get('usd', {}).get(n) for v in pv])} |" for n in prices))
    last = reports[-1]["projection_from_unit_costs"]["normal"]
    L += ["", f"Assumed (not measured in this run) in the normal day: event types {last['assumed_event_types']}; the receiver rung of every E2 and E4 hop is always the first-order cost.", ""]
    if reports[-1].get("router_eval_log"):
        e = reports[-1]["router_eval_log"]
        L += [f"Router eval log in the window: {e['calls']} calls ({e['aux_calls']} aux), peak {e['peak_calls_per_minute']} a minute and {e['peak_calls_per_hour']} an hour, "
              f"{e['neurons']} Cloudflare neurons ({e['neurons_pct_of_10000']} percent of the daily 10,000).", ""]
    return "\n".join(L) + "\n"


def print_plan(scen, events, cfg, args, caps=None):
    L = [f"plan: profile {scen['profile']}, load {args.load}, seed {args.seed}, mode {args.mode}, speed {args.speed}, endpoint {args.endpoint}", ""]
    turns = 0
    by_role = collections.Counter()
    flat = sorted(((ev["sim_s"] + st["after_s"], ev, st) for ev in events for st in ev["steps"]), key=lambda x: (x[0], x[2]["tag_id"]))
    for sim, ev, st in flat:
        tgt = ""
        if cfg:
            t = pick_target(cfg["targets"], st["role"], scen["profile"])
            tgt = t["label"] if t else "(no target for this role)"
            if ev["kind"] == "task" and st["idx"] == 1 and t and not t.get("tareas"):
                tgt += " (task event: skipped, target has no tareas)"
        if ev["kind"] != "marker":
            turns += 1
            by_role[st["role"]] += 1
        L.append(f"{clock(sim)}  {st['tag_id']:<9} {ev['kind']:<6} -> {st['role']:<10} chars={len(st['text']):<6} {tgt}")
    capline = (f"planned {caps[2]} turns to send, caps {caps[0]} in total, per target {caps[1]}" + (" (the caps would TRUNCATE the day)" if caps[4] else "")) if caps \
        else "caps: derived from the plan once the private config names the targets"
    L += ["", f"{len(events)} events, {turns} turns: {dict(by_role)}", capline, "dry run: nothing was sent"]
    print("\n".join(L))


def parse_price(s):
    m = re.fullmatch(r"([A-Za-z0-9_-]{1,20})=([\d.]+)/([\d.]+)(?:/([\d.]+))?", s)
    if not m:
        raise Refuse(f"--price {s!r}: use NAME=IN/OUT or NAME=IN/OUT/CACHED in dollars per million tokens, e.g. cheap=0.1/0.4")
    return m.group(1), (float(m.group(2)), float(m.group(3)), float(m.group(4)) if m.group(4) else None)


def parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", help="burger | accounting | shop | design (ops/synth/<profile>.json)")
    p.add_argument("--load", default="normal", help="quiet | normal | busy | idle | runaway")
    p.add_argument("--mode", choices=("a", "b"), default="a", help="a: fake model, no tokens spent; b: real providers on the test stacks, tokens spent")
    p.add_argument("--speed", type=float, default=0, help="simulated seconds per wall second; 0 = event by event, no waiting")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--targets", default=DEFAULT_TARGETS)
    p.add_argument("--scenarios", default=SCEN_DIR)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--endpoint", choices=("chat", "runs"), default="chat")
    p.add_argument("--session-header", default="X-Hermes-Session-Id", help="header that names the session of an event (unverified: empty disables)")
    p.add_argument("--continue-e3", action="store_true", help="the E3 variant: all E3 turns of a role share one session (an owner conversation), not one per event")
    p.add_argument("--turn-timeout", type=float, default=600)
    p.add_argument("--poll-s", type=float, default=2.0)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--max-turns", type=int, default=None, help="hard cap on turns per run (default: planned turns x 1.2 + 3)")
    p.add_argument("--max-turns-per-bot", type=int, default=None, help="hard cap per target (default: that target's planned turns x 1.2 + 3)")
    p.add_argument("--allow-truncate", action="store_true", help="mode b: allow an explicit cap that is below the planned day")
    p.add_argument("--max-tokens", type=int, default=0, help="mode b: hard stop when input + output + cache read tokens reach this (needed in mode b unless --max-usd)")
    p.add_argument("--max-usd", type=float, default=0.0, help="mode b: hard stop at this many dollars at the dearest --price (needs --price)")
    p.add_argument("--allow-runaway", action="store_true", help="mode b: run the E8 runaway load (needs cap_check_cmd in the config, run before that turn)")
    p.add_argument("--usage-tolerance", type=float, default=0.15, help="warn when the state.db difference and the API usage differ by more than this share")
    p.add_argument("--cache-in-input", action="store_true", help="input_tokens already includes the cache reads (default: they are separate)")
    p.add_argument("--kill-file", default=None, help="stop the replay when this file exists (default <out>/KILL)")
    p.add_argument("--cap-check-every", type=int, default=10)
    p.add_argument("--approve-spend", action="store_true", help="mode b only: yes, spend real tokens on the listed keys")
    p.add_argument("--price", action="append", default=[], help="NAME=IN/OUT[/CACHED] dollars per million tokens (repeatable)")
    p.add_argument("--gpu-price-per-hour", type=float, default=0.0)
    p.add_argument("--boot-seconds", type=float, default=BOOT_ASSUMED_S)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--calibrate", nargs=2, metavar=("MODE_A_REPORT", "MODE_B_REPORT"), help="offline: chars per token from a mode a and a mode b report of the same profile, load and seed")
    return p


def read_report(path):
    try:
        return json.load(open(path))
    except (OSError, ValueError) as e:
        raise Refuse(f"cannot read report {path}: {e}")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.calibrate:
            print(json.dumps(calibrate(read_report(args.calibrate[0]), read_report(args.calibrate[1])), indent=1))
            return 0
        if not args.profile:
            raise Refuse("--profile is required")
        args.kill_file = args.kill_file or os.path.join(args.out, "KILL")
        prices = dict(parse_price(s) for s in args.price)
        scen = load_scenario(args.profile, args.scenarios)
        if args.repeats < 1 or args.repeats > 50:
            raise Refuse("--repeats must be 1 to 50")
        seeds = [args.seed + i for i in range(args.repeats)]
        cfg = None
        if args.dry_run:
            try:
                cfg = load_targets(args.targets)
            except Refuse as e:
                if os.path.exists(args.targets):
                    raise
                say(f"note: {e} (dry plan only, no targets shown)")
            caps = resolve_caps(scen, cfg, args, [args.seed]) if cfg else None
            print_plan(scen, build_timeline(scen, args.load, args.seed, f"{args.profile}-{args.load}-{args.mode}-r1-plan"), cfg, args, caps)
            return 0
        cfg = load_targets(args.targets)
        max_turns, caps, planned, planned_by, truncates, has_e8 = resolve_caps(scen, cfg, args, seeds)
        say(f"planned {planned} turns {dict(planned_by)}; caps {max_turns} in total, per target {caps}")
        if args.mode == "b":
            if not args.approve_spend:
                raise Refuse("mode b spends real tokens: add --approve-spend after the size of the run was approved (SYNTHETIC_DAY.md section 7)")
            if not [k for k in (cfg.get("keys") or []) if isinstance(k, dict) and k.get("label") and k.get("provider")]:
                raise Refuse("mode b needs \"keys\" in the private config: one entry per test key with provider, label and roles (labels only, never the value)")
            if not (args.max_tokens or args.max_usd):
                raise Refuse("mode b needs a hard budget: --max-tokens N and/or --max-usd X (with --price), fixed in advance from the plan (SYNTHETIC_DAY.md section 7)")
            if args.max_usd and not prices:
                raise Refuse("--max-usd needs at least one --price NAME=IN/OUT to turn tokens into dollars")
            if truncates and not args.allow_truncate:
                raise Refuse(f"the caps ({max_turns} in total, {caps} per target) are below the planned day ({planned} turns, {dict(planned_by)}): raise them, or add --allow-truncate")
            if has_e8 and not args.allow_runaway:
                raise Refuse("this load contains the E8 runaway turn: a real model asked to retry without stopping can spend without limit; add --allow-runaway to run it anyway")
            if has_e8 and not (isinstance(cfg.get("cap_check_cmd"), list) and cfg["cap_check_cmd"]):
                raise Refuse("the E8 runaway turn in mode b needs \"cap_check_cmd\" in the config: it runs right before that turn and a non-zero exit stops the run")
        elif truncates:
            say("warning: the caps are below the planned day: the day will be truncated (turn_cap skips)")
        if args.mode == "a":
            probe_fake(cfg, scen)
        os.makedirs(args.out, exist_ok=True)
        reports = []
        for rep in range(1, args.repeats + 1):
            report, run = run_one(scen, cfg, args, rep, args.seed + rep - 1, prices)
            path = os.path.join(args.out, report["run_id"] + ".json")
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                json.dump(report, f, indent=1)
            say(f"run {rep}/{args.repeats}: {report['totals']['turns_sent']} turns, {report['totals']['turns_error']} errors, {report['wall_seconds']} s -> {path}")
            reports.append(report)
            if run.killed:
                say(f"stopped: {run.stop_reason}")
                break
        md = os.path.join(args.out, f"{args.profile}-{args.load}-{args.mode}-summary.md")
        with open(md, "w") as f:
            f.write(summary_md(reports, prices))
        say(f"summary -> {md}")
        return 0
    except Refuse as e:
        say(f"refused: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
