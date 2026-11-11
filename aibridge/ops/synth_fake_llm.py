#!/usr/bin/env python3
"""An OpenAI-compatible FAKE model for the synthetic business days (mode A of SYNTHETIC_DAY.md). Standard library only.

  python3 ops/synth_fake_llm.py [--bind 127.0.0.1] [--port 8700] [--scenarios ops/synth] [--log FILE]
        [--chars-per-token 4.0] [--usage always|stream_opt|never] [--shell-tool terminal] [--peer ROLE=BOT ...]
        [--max-calls N] [--max-calls-per-event N] [--fail-mode 429|hang|bad_args|no_usage --fail-every N] [--hang-seconds 120]

It answers POST /v1/chat/completions (and /chat/completions), streaming or not, with SCRIPTED text and SCRIPTED tool calls, so that the
real Hermes, router, gateway, waker and RAM guard run end to end without spending a token. What it measures is infrastructure.

How the script is chosen: the latest user message of the request carries a tag `[SYN:<run-id>:<event-id>]` (the harness, ops/synth_day.py,
puts it there; run-id starts with the profile name, event-id is `E3-04` or `E7-01.2` for step 2). The profile and event type select a plan in
the scenario files (ops/synth/<profile>.json: `plan` of the event, or of the step): `rounds` tool rounds (each one a call of the shell tool
with the next command of `calls`), then a final text whose length is drawn from `out_tokens` [lo, hi]. A request without a tag (titles,
memory review, anything the agent sends on its own) gets a short canned answer and is counted as `untagged`.

A command in `calls` is a COMPLETE command line with the arguments the real command needs, with placeholders filled here: {n} is the event's
number (E2-03 gives 3), {event} its id (E2-03), {next} the role of the first hop of the event (the bot a task is filed for). --peer ROLE=BOT
(repeatable) maps a role to the name that bot has on the test stacks' task board; without it the role name is the bot name. The tool RESULT is
read too: a result that looks like a usage error or a failed command (a line starting with "Uso:" or "usage:", a non-zero exit_code, command not
found) is counted per event as `tool_errors`, so a scripted command that does nothing shows in the counters instead of passing as a real task.
The event number 0 (tag E0-01) is the harness's probe (a one-line reply, no tool call): ops/synth_day.py sends it before a mode a day to see that
the stack really talks to this fake.

What it records, COUNTS AND SIZES ONLY: per request the characters of the request body, the number of messages and of tools, a hash of the tag,
the estimated prompt tokens (characters divided by --chars-per-token, default 4.0: an assumption that mode B calibrates), the completion tokens,
the finish reason and the HTTP status. No message text, no arguments. GET /counters returns them aggregated per tag (add ?run=<run-id> to filter),
GET /health answers ok, POST /reset clears the counters.

Failure is scriptable: --fail-every N makes every Nth request fail the chosen way (429 with Retry-After, a hang past the router's timeout,
tool-call arguments that are not valid JSON, or an answer without `usage`), to exercise the router's fallback chain and cooldowns.
--max-calls and --max-calls-per-event are hard caps: past them every request gets 429 (counted as `cap_refused`).
Every name and number in the scenario files is invented.
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
TAG_RE = re.compile(r"\[SYN:([A-Za-z0-9_.-]{1,80}):(E\d+)-(\d+)(?:\.(\d+))?\]")
WORDS = "alpha bravo carta delta eco foxtrot golf hotel indigo julio kilo lima mono nube oscar prisma quebec romeo sierra tango".split()
UNTAGGED_TOKENS = 12
TOOL_FAIL_RE = re.compile(r'(?:^|\n)\s*(?:uso|usage):|"exit_code"\s*:\s*(?!0\b)-?\d+|command not found', re.I)
PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")


def fill(cmd, etype, num, nxt):
    """The placeholders of a scripted command: {n}, {event}, {next}."""
    return cmd.replace("{event}", f"{etype}-{num:02d}").replace("{n}", str(num)).replace("{next}", nxt)


def tool_failures(messages, ui):
    """How many of the NEWEST tool results (the ones after the last assistant tool call, so a replayed history is not counted twice) look like failures."""
    last = -1
    for i in range(len(messages) - 1, ui, -1):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls"):
            last = i
            break
    if last < 0:
        return 0
    return sum(1 for m in messages[last + 1:] if isinstance(m, dict) and m.get("role") == "tool" and TOOL_FAIL_RE.search(flat_text(m.get("content"))))


def load_plans(directory):
    """{profile: {(etype, step): plan}} (and "__hops__": {profile: {etype: [roles]}}) from the scenario files. Step 0 is the event's own plan (or its first step's); steps 2 and up are keyed by their number."""
    plans = {}
    hops = {}
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith(".json"):
            continue
        try:
            doc = json.load(open(os.path.join(directory, fn)))
        except (OSError, ValueError):
            continue
        prof = doc.get("profile")
        if not isinstance(prof, str):
            continue
        for et, spec in (doc.get("events") or {}).items():
            hops.setdefault(prof, {})[et] = [h.get("role") for h in (spec.get("hops") or []) if isinstance(h, dict) and h.get("role")]
            steps = spec.get("steps") or []
            plans.setdefault(prof, {})[(et, 0)] = (steps[0].get("plan") if steps else None) or spec.get("plan") or {}
            for i, st in enumerate(steps, 1):      # step 1 carries no suffix in its tag, so it is key (et, 0)
                if i > 1:
                    plans[prof][(et, i)] = st.get("plan") or spec.get("plan") or {}
    plans["__hops__"] = hops          # {profile: {event type: [hop roles]}}: only for {next}
    return plans


def flat_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and isinstance(p.get("text"), str))
    return ""


def find_tag(messages):
    """(tag match, index of that user message) for the latest user message that carries a tag, else (None, -1)."""
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "user":
            hit = TAG_RE.search(flat_text(m.get("content")))
            if hit:
                return hit, i
            return None, -1     # the latest user message has no tag: not ours
    return None, -1


class Fake:
    def __init__(self, args):
        self.a = args
        self.plans = load_plans(args.scenarios)
        self.peers = {}
        for item in args.peer or []:
            role, _, bot = item.partition("=")
            if role and bot:
                self.peers[role] = bot
        self.lock = threading.Lock()
        self.n_calls = 0
        self.per_event = {}      # tag text -> counters
        self.untagged = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        self.totals = {"calls": 0, "cap_refused": 0, "failed_scripted": 0, "tool_missing": 0}

    def reset(self):
        with self.lock:
            self.n_calls = 0
            self.per_event.clear()
            self.untagged = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
            self.totals = {k: 0 for k in self.totals}

    def count(self, tag, **inc):
        with self.lock:
            row = self.per_event.setdefault(tag, {"calls": 0, "tool_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "chars": 0,
                                                  "steps_max": 0, "tool_missing": 0, "no_usage": 0, "tool_errors": 0})
            for k, v in inc.items():
                if k == "steps_max":
                    row[k] = max(row[k], v)
                else:
                    row[k] = row.get(k, 0) + v

    def snapshot(self, run=None):
        with self.lock:
            rows = {t: dict(r) for t, r in self.per_event.items() if not run or t.split(":")[1] == run}
            return {"events": rows, "untagged": dict(self.untagged), "totals": dict(self.totals), "chars_per_token": self.a.chars_per_token}


def est_tokens(chars, ratio):
    return max(1, int(chars / ratio + 0.999))


def make_text(tokens, seed, ratio):
    rnd = random.Random(seed)
    out, n = [], 0
    target = int(tokens * ratio)
    while n < target:
        w = rnd.choice(WORDS)
        out.append(w)
        n += len(w) + 1
    return " ".join(out)


class Handler(BaseHTTPRequestHandler):
    server_version = "synth-fake-llm"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send_json(self, code, obj, headers=None):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        f = self.server.fake
        if u.path in ("/health", "/healthz", "/"):
            return self.send_json(200, {"ok": True})
        if u.path.rstrip("/") in ("/v1/models", "/models"):
            return self.send_json(200, {"object": "list", "data": [{"id": "synth-fake", "object": "model", "owned_by": "synthetic"}]})
        if u.path == "/counters":
            run = (parse_qs(u.query).get("run") or [None])[0]
            return self.send_json(200, f.snapshot(run))
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        f = self.server.fake
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if u.path == "/reset":
            f.reset()
            return self.send_json(200, {"ok": True})
        if u.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            return self.send_json(404, {"error": "not found"})
        try:
            body = json.loads(raw or b"{}")
            msgs = body.get("messages") or []
        except ValueError:
            return self.send_json(400, {"error": "bad json"})
        a = f.a
        hit, ui = find_tag(msgs)
        tag = hit.group(0) if hit else None
        with f.lock:
            f.n_calls += 1
            nth = f.n_calls
            f.totals["calls"] += 1
            ev_calls = f.per_event.get(tag, {}).get("calls", 0) if tag else 0
        if (a.max_calls and nth > a.max_calls) or (tag and a.max_calls_per_event and ev_calls >= a.max_calls_per_event):
            with f.lock:
                f.totals["cap_refused"] += 1
            return self.send_json(429, {"error": {"message": "synthetic call cap reached", "type": "rate_limit"}}, {"Retry-After": "60"})
        fail = a.fail_mode if (a.fail_mode and a.fail_every and nth % a.fail_every == 0) else None
        if fail:
            with f.lock:
                f.totals["failed_scripted"] += 1
        if fail == "429":
            return self.send_json(429, {"error": {"message": "synthetic rate limit", "type": "rate_limit"}}, {"Retry-After": "5"})
        if fail == "hang":
            time.sleep(a.hang_seconds)
            return self.send_json(504, {"error": {"message": "synthetic hang"}})

        ratio = a.chars_per_token
        prompt_tokens = est_tokens(len(raw), ratio)
        tools = body.get("tools") or []
        tool_names = [((t or {}).get("function") or {}).get("name") for t in tools if isinstance(t, dict)]
        seed = hashlib.sha256((tag or "-").encode() + str(len(msgs)).encode()).hexdigest()
        tool_call = None
        steps_done = 0
        plan = {}
        tool_errors = 0
        if hit:
            profile = hit.group(1).split("-")[0]
            step = int(hit.group(4) or 0)
            plan = f.plans.get(profile, {}).get((hit.group(2), step)) or f.plans.get(profile, {}).get((hit.group(2), 0)) or {}
            steps_done = sum(1 for m in msgs[ui + 1:] if isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls"))
            tool_errors = tool_failures(msgs, ui)
            rounds = int(plan.get("rounds") or 0)
            calls = plan.get("calls") or ["true"]
            if steps_done < rounds:
                if a.shell_tool in tool_names:
                    nhops = f.plans.get("__hops__", {}).get(profile, {}).get(hit.group(2)) or []
                    role = nhops[0] if nhops else "owner"
                    cmd = fill(calls[steps_done % len(calls)], hit.group(2), int(hit.group(3)), f.peers.get(role, role))
                    args = json.dumps({"command": cmd})
                    if fail == "bad_args":
                        args = args[:-1]            # not valid JSON
                    tool_call = {"id": "call_" + seed[:8] + str(steps_done), "type": "function", "function": {"name": a.shell_tool, "arguments": args}}
                else:
                    with f.lock:
                        f.totals["tool_missing"] += 1
                    f.count(tag, tool_missing=1)
        if tool_call:
            completion_tokens = est_tokens(len(tool_call["function"]["arguments"]) + len(a.shell_tool), ratio)
            message = {"role": "assistant", "content": None, "tool_calls": [tool_call]}
            finish = "tool_calls"
        else:
            lo, hi = (plan.get("out_tokens") or [UNTAGGED_TOKENS, UNTAGGED_TOKENS])[:2] if hit else (UNTAGGED_TOKENS, UNTAGGED_TOKENS)
            completion_tokens = random.Random(seed).randint(int(lo), max(int(lo), int(hi)))
            message = {"role": "assistant", "content": make_text(completion_tokens, seed, ratio)}
            finish = "stop"
        if tag:
            self.server.fake.count(tag, calls=1, tool_calls=1 if tool_call else 0, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                                   chars=len(raw), steps_max=steps_done + 1, no_usage=1 if (a.usage == "never" or fail == "no_usage") else 0,
                                   tool_errors=tool_errors)
        else:
            with f.lock:
                f.untagged["calls"] += 1
                f.untagged["prompt_tokens"] += prompt_tokens
                f.untagged["completion_tokens"] += completion_tokens
        if a.log:
            rec = {"ts": round(time.time(), 1), "tag": hashlib.sha256(tag.encode()).hexdigest()[:10] if tag else None,
                   "event": hit.group(2) if hit else None, "chars": len(raw), "messages": len(msgs), "tools": len(tools), "stream": bool(body.get("stream")),
                   "prompt_tokens_est": prompt_tokens, "completion_tokens": completion_tokens, "finish": finish, "status": 200}
            try:
                with f.lock, open(a.log, "a") as fh:
                    fh.write(json.dumps(rec) + "\n")
            except OSError:
                pass
        want_stream_usage = bool((body.get("stream_options") or {}).get("include_usage"))
        usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens}
        send_usage = not (a.usage == "never" or fail == "no_usage")
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            cid = "chatcmpl-" + seed[:12]

            def chunk(delta, fin=None, use=None):
                d = {"id": cid, "object": "chat.completion.chunk", "model": "synth-fake", "choices": [{"index": 0, "delta": delta, "finish_reason": fin}]}
                if use is not None:
                    d["usage"] = use
                self.wfile.write(b"data: " + json.dumps(d).encode() + b"\n\n")

            if tool_call:
                tc = tool_call["function"]
                chunk({"role": "assistant", "tool_calls": [{"index": 0, "id": tool_call["id"], "type": "function", "function": {"name": tc["name"], "arguments": ""}}]})
                arg = tc["arguments"]
                chunk({"tool_calls": [{"index": 0, "function": {"arguments": arg[:6]}}]})
                chunk({"tool_calls": [{"index": 0, "function": {"arguments": arg[6:]}}]})
            else:
                text = message["content"]
                chunk({"role": "assistant", "content": ""})
                for i in range(0, len(text), 64):
                    chunk({"content": text[i:i + 64]})
            final_usage = usage if (send_usage and (a.usage == "always" or want_stream_usage)) else None
            chunk({}, finish, use=final_usage if a.usage == "always" else None)
            if final_usage is not None and a.usage == "stream_opt":
                self.wfile.write(b"data: " + json.dumps({"id": cid, "object": "chat.completion.chunk", "model": "synth-fake", "choices": [], "usage": final_usage}).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True
            return
        out = {"id": "chatcmpl-" + seed[:12], "object": "chat.completion", "model": "synth-fake",
               "choices": [{"index": 0, "message": message, "finish_reason": finish}]}
        if send_usage:
            out["usage"] = usage
        self.send_json(200, out)


def make_server(args, host="127.0.0.1", port=0):
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    srv.fake = Fake(args)
    return srv


def parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8700)
    p.add_argument("--scenarios", default=os.path.join(HERE, "synth"))
    p.add_argument("--log", default="")
    p.add_argument("--chars-per-token", type=float, default=4.0)
    p.add_argument("--usage", choices=("always", "stream_opt", "never"), default="always")
    p.add_argument("--shell-tool", default="terminal")
    p.add_argument("--peer", action="append", default=[], help="ROLE=BOT: the name a role's bot has on the task board (default: the role name)")
    p.add_argument("--max-calls", type=int, default=0)
    p.add_argument("--max-calls-per-event", type=int, default=0)
    p.add_argument("--fail-mode", choices=("429", "hang", "bad_args", "no_usage"), default="")
    p.add_argument("--fail-every", type=int, default=0)
    p.add_argument("--hang-seconds", type=float, default=120)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    srv = make_server(args, args.bind, args.port)
    print(f"synth fake LLM on http://{args.bind}:{srv.server_port}/v1 (scenarios {args.scenarios}, counts only)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
