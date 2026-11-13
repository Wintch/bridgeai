#!/usr/bin/env python3
"""Split every human turn into the steps it is made of, from the logs a stack already writes, to see which steps a faster machine speeds up.

  ops/turn_breakdown.py run --db state.db --eval .model-eval.jsonl --gateway .gateway-log.jsonl --journal waker.txt --cpu turn-cpu.jsonl \
        --stack NAME --since -24h --label staging --json staging.json [--restarts restarts.txt]
  ops/turn_breakdown.py compare production.json staging.json

One turn, in the order the person lives it (the segment names are the output fields, seconds):
  detect_s     Telegram message sent -> the waker saw it (stack asleep only: the waker's own poll, host independent)
  admit_s      the waker saw it -> the boot started (queue behind another boot, RAM guard)
  boot_s       container start -> ready ("ready after")
  intake_s     ready -> Hermes stored the message
  per model call, from state.db message times (the chain starts at the person's last message of the burst):
    pre_s      router work before the request left (strip, route, keys)            router eval log `pre`
    model_s    the provider's answer: connect + wait + generation                   eval log `s`   (ttfb_s, gen_s = model_s - ttfb_s; `buf` = ttfb is not a first token)
    retry_s    failed tries before the answer (timeouts count in full)              eval log lines with result != ok
    hermes_s   what is left of the gap: Hermes building the prompt, memory, skills, storing the rows, the stream's way back. Disk-bound in part
  per tool call:
    tool seg   time from the previous message to the tool result's row; split into cpu_s and wait_s from, in order: the gateway log
               (proc_cpu / proc_wall of that command), else the container's CPU counters (--cpu, ops/turn_cpu_sampler.py), else unknown
  deliver_s    final answer stored -> on the person's screen: NOT recorded anywhere today (see "Known limits" in ops/STAGING.md)
and four sums that answer the question: machine_s (hermes_s + pre_s + tool cpu + boot + intake + admit), provider_s (model + retry),
external_s (tool waiting + detect), unknown_s (calls the router did not log, tools with no CPU figure). A faster machine can only move
machine_s: it is the most a faster machine can gain on this turn. human_s = the wait before Hermes stored the message (wake) + chain_s
(from the person's last message of the burst to the final answer), so the four sums always add up to it (up to the journal's 1 s).

Cold starts: a stack with a waker has them in the journal (kind telegram / web). A stack without one (the staging copy) is stopped and
started by hand: write the UTC time of each `docker start` in a file, one per line, `2026-11-13 10:00:00 [boot seconds from a stopwatch]`,
and pass it as --restarts: the first turn within 30 minutes after it counts as a cold turn (group `woken`), the rest as warm (`awake`).

Every figure is a time, a count, a tool name or a model id. Message text is never read (only its presence and the tool names in
`tool_calls`), nothing but the first 8 hex digits of a hashed session id identifies a conversation. Precision: state.db and the eval and
gateway logs are sub-second, the waker journal is one second, so the wake segments are +-1 s.

Reading the join: the router's `session` and `turn` fields are not Hermes's ids, so a model call is matched to its state.db assistant row
by time (the router logs when the call ENDED; Hermes stores the row right after). Calls with `aux` (titles, memory review, vision) are
counted, not charged to the chain. A stack that answers from a local model (route local) writes no eval lines: its model time stays in unknown_s.
"""
import argparse, bisect, collections, datetime as dt, hashlib, json, math, os, re, sqlite3, sys, time

SAFE_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
BURST_S = 900                    # same rule as ops/telemetry.py: messages before any answer are one turn
EVAL_SLACK_BEFORE, EVAL_SLACK_AFTER = 0.5, 1.5
MAX_SAMPLE_GAP_S = 30            # a cgroup counter is not interpolated across a longer hole in the sampler's file (container stopped, sampler down)
MANUAL_COLD_S = 1800             # a hand-made restart (--restarts) makes cold the first turn that starts within this many seconds
CPU_BOUND, WAIT_BOUND = 0.6, 0.15  # cores busy during a tool: at or above = cpu, at or below = wait, between = mixed
JOURNAL = {
    "tg": re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[(\S+)\] telegram wake: update \d+ \(\w+[^)]*\), sent (\d+)s ago"),
    "waking": re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[(\S+)\] waking \((\w+)\)"),
    "ready": re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[(\S+)\] ready after ([\d.]+)s \((\w+)\)"),
    "held": re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[(\S+)\] held \S+ replayed after ([\d.]+)s: (\d{3})"),
}
FRONT = re.compile(r'\[(\d\d/\w{3}/\d{4}:\d\d:\d\d:\d\d [+-]\d{4})\] "POST (/api/chat/completions)\S* HTTP/[\d.]+" (\d{3}) .* rt=([\d.]+)')


def utc(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp()


def jsonl(paths):
    out = []
    for p in paths or []:
        try:
            with open(p, errors="replace") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue                      # the cut first line of a rotated log
                    if isinstance(d, dict) and isinstance(d.get("ts"), (int, float)) and not isinstance(d["ts"], bool):
                        out.append(d)
        except OSError as e:
            print(f"cannot read {p}: {e.strerror}", file=sys.stderr)
    out.sort(key=lambda d: d["ts"])
    return out


def safe_name(v):
    return v if isinstance(v, str) and SAFE_NAME.match(v) else None


def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ---------------------------------------------------------------- state.db -> turns
def tool_names(tc):
    try:
        calls = json.loads(tc) if tc else []
    except ValueError:
        return []
    out = []
    for x in calls if isinstance(calls, list) else []:
        n = (x.get("function") or x).get("name") if isinstance(x, dict) else None
        out.append(n if isinstance(n, str) and SAFE_NAME.match(n) else "?")
    return out


def read_rows(db_path, immutable=False):
    uri = f"file:{db_path}?" + ("immutable=1" if immutable else "mode=ro")
    db = sqlite3.connect(uri, uri=True, timeout=10)
    cols = {r[1] for r in db.execute("pragma table_info(messages)")}
    pick = lambda c: c if c in cols else "null"
    rows = db.execute(f"select session_id, role, timestamp, {pick('finish_reason')}, {pick('tool_calls')}, {pick('tool_name')}, "
                      f"coalesce(length(content), 0), id from messages order by timestamp, id").fetchall()
    try:
        source = dict(db.execute("select id, source from sessions"))
    except sqlite3.Error:
        source = {}
    db.close()
    seen, by_session = set(), collections.OrderedDict()
    for sid, role, ts, fin, tc, tname, clen, _ in rows:
        if role not in ("user", "assistant", "tool") or not isinstance(ts, (int, float)):
            continue
        key = (role, round(ts, 3), hashlib.sha1((tc or "").encode()).hexdigest()[:8], clen)
        if key in seen:                                # a row stored twice, or a compaction copy under a new session
            continue
        seen.add(key)
        names = tool_names(tc) if role == "assistant" else []
        by_session.setdefault(sid, []).append({"role": role, "ts": float(ts), "fin": fin, "calls": names,
                                              "tname": tname if isinstance(tname, str) and SAFE_NAME.match(tname) else None})
    return by_session, source


def split_turns(rows):
    turns, cur = [], None
    for r in rows:
        if r["role"] == "user":
            if cur and not cur["rest"] and r["ts"] - cur["users"][-1]["ts"] < BURST_S:
                cur["users"].append(r)
                continue
            cur = {"users": [r], "rest": []}
            turns.append(cur)
        elif cur is not None:
            cur["rest"].append(r)
    return turns


# ---------------------------------------------------------------- side logs
class Cpu:
    """Counters from ops/turn_cpu_sampler.py, read at any time by linear interpolation."""
    def __init__(self, recs):
        self.t = [r["ts"] for r in recs]
        self.r = recs

    def at(self, field, t):
        if not self.t or t < self.t[0] - 5 or t > self.t[-1] + 5:
            return None
        i = bisect.bisect_left(self.t, t)
        if i < len(self.t) and self.t[i] == t:
            return num(self.r[i].get(field))
        if i <= 0:
            return num(self.r[0].get(field))
        if i >= len(self.t):
            return num(self.r[-1].get(field))
        a, b = self.r[i - 1], self.r[i]
        va, vb = num(a.get(field)), num(b.get(field))
        if va is None or vb is None or vb < va or b["ts"] - a["ts"] > MAX_SAMPLE_GAP_S:
            return None                  # a counter that went down is a restarted container (counters start again at 0): no figure, not a negative one
        return va + (vb - va) * (t - a["ts"]) / max(b["ts"] - a["ts"], 1e-9)

    def delta(self, field, t0, t1):
        a, b = self.at(field, t0), self.at(field, t1)
        return None if a is None or b is None or b < a else (b - a) / 1e6     # b < a: the container restarted in between


def parse_journal(text, stack):
    """Wake records of one stack: dicts with kind tg|waking|ready|held and the time (UTC epoch) and numbers. No text is kept."""
    out = []
    for line in text.splitlines():
        for kind, rx in JOURNAL.items():
            m = rx.match(line)
            if m and m.group(2) == stack:
                g = m.groups()
                rec = {"kind": kind, "ts": utc(g[0])}
                if kind == "tg":
                    rec["sent_ago"] = float(g[2])
                elif kind == "waking":
                    rec["reason"] = g[2]
                elif kind == "ready":
                    rec["boot_s"], rec["reason"] = float(g[2]), g[3]
                else:
                    rec["hold_s"], rec["status"] = float(g[2]), int(g[3])
                out.append(rec)
                break
    return out


def parse_front(text):
    out = []
    for line in text.splitlines():
        m = FRONT.search(line)
        if m:
            try:
                out.append({"ts": dt.datetime.strptime(m.group(1), "%d/%b/%Y:%H:%M:%S %z").timestamp(), "status": int(m.group(3)),
                            "rt": float(m.group(4))})
            except ValueError:
                pass
    return out


def wake_for(u0, events, used):
    """The wake that ended just before the first message of this turn was stored, as segments; None for a turn on an awake stack."""
    held = [e for e in events if e["kind"] == "held" and abs(e["ts"] - u0) <= 5 and id(e) not in used]
    ready = [e for e in events if e["kind"] == "ready" and e["ts"] <= u0 + 3 and u0 - e["ts"] <= 90 and id(e) not in used]
    if held:
        used.add(id(held[-1]))
        w = {"kind": "web", "wait_s": held[-1]["hold_s"], "boot_s": ready[-1]["boot_s"] if ready else None}
        if ready:
            used.add(id(ready[-1]))
        return w
    if not ready:
        manual = [e for e in events if e["kind"] == "manual" and 0 <= u0 - e["ts"] <= MANUAL_COLD_S and id(e) not in used]
        if not manual:
            return None
        used.add(id(manual[-1]))
        b = manual[-1]["boot_s"]         # the stopwatch figure, when the operator wrote one; the wait before the message is the person's own typing
        return {"kind": "manual", "boot_s": b, "intake_s": None, "detect_s": None, "admit_s": None, "wait_s": b or 0.0}
    r = ready[-1]
    used.add(id(r))
    w = {"kind": r.get("reason") or "wake", "boot_s": r["boot_s"], "intake_s": max(0.0, u0 - r["ts"]), "detect_s": None, "admit_s": None}
    waking = [e for e in events if e["kind"] == "waking" and r["ts"] - 300 <= e["ts"] <= r["ts"]]
    tg = [e for e in events if e["kind"] == "tg" and r["ts"] - 300 <= e["ts"] <= r["ts"]] if r.get("reason") == "telegram" else []
    if tg:
        w["detect_s"] = tg[-1]["sent_ago"]
        w["admit_s"] = max(0.0, (waking[-1]["ts"] if waking else r["ts"] - r["boot_s"]) - tg[-1]["ts"])
        w["wait_s"] = tg[-1]["sent_ago"] + (r["ts"] - tg[-1]["ts"]) + w["intake_s"]
    else:
        w["wait_s"] = r["boot_s"] + w["intake_s"]
    return w


# ---------------------------------------------------------------- one turn
def classify(cpu_s, seg):
    if cpu_s is None or seg <= 0:
        return "unknown"
    cores = cpu_s / seg
    return "cpu" if cores >= CPU_BOUND else "wait" if cores <= WAIT_BOUND else "mixed"


def decompose(turn, sid, source, evals, gws, events, used_wakes, cpu, used_evals, used_gw):
    users, rest = turn["users"], turn["rest"]
    u0, ul = users[0]["ts"], users[-1]["ts"]
    end = next((i for i in range(len(rest) - 1, -1, -1) if rest[i]["role"] == "assistant" and rest[i]["fin"] == "stop"), None)
    if end is None:
        return None
    final = rest[end]
    t = {"ts": round(u0, 2), "session": hashlib.sha1(str(sid).encode()).hexdigest()[:8], "source": source or "", "users": len(users),
         "burst_s": round(ul - u0, 2), "total_s": round(final["ts"] - u0, 2), "chain_s": round(final["ts"] - ul, 2)}
    calls, tools, prev = [], [], ul
    pending = []                                  # tool names of the last assistant row, in order, for rows with no tool_name
    for r in rest[:end + 1]:
        seg = max(0.0, r["ts"] - prev)
        if r["role"] == "assistant":
            pending = list(r["calls"])
            window = [e for e in evals if prev - EVAL_SLACK_BEFORE <= e["ts"] <= r["ts"] + EVAL_SLACK_AFTER and id(e) not in used_evals
                      and e.get("model") and not e.get("aux") and "feedback" not in e]
            ok = [e for e in window if e.get("result") == "ok"]
            good = ok[-1] if ok else None
            bad = [e for e in window if e is not good and e.get("result") != "ok"]
            for e in ([good] if good else []) + bad:
                used_evals.add(id(e))
            c = {"model": good.get("model") if good else None, "seg_s": round(seg, 2), "matched": bool(good), "final": r is final,
                 "tools_asked": len(r["calls"])}
            if good:
                ms, tt = num(good.get("s")) or 0.0, num(good.get("ttfb"))
                retry = sum(num(e.get("s")) or 0.0 for e in bad)
                first = [e for e in window if e.get("pos") == 0 and num(e.get("pre")) is not None]   # the router's pre-work is logged on the first try only, even when a later one answered
                pre = num(first[0]["pre"]) if first else 0.0
                c.update(model_s=round(ms, 2), ttfb_s=tt, gen_s=round(ms - tt, 2) if tt is not None and not good.get("buf") else None,
                         buf=bool(good.get("buf")), retry_s=round(retry, 2), pre_s=round(pre, 3), tok=good.get("tok"), ptok=good.get("ptok"),
                         in_b=good.get("in_b"), tried=len(bad) + 1, hermes_s=round(max(0.0, seg - ms - retry - pre), 2))
            calls.append(c)
        elif r["role"] == "tool":
            name = r["tname"] or (pending.pop(0) if pending else "?")
            lo, hi = prev - 1.5, r["ts"] + 1.0
            hit = [g for g in gws if lo <= g["ts"] - (num(g.get("proc_wall")) or num(g.get("seconds")) or 0) and g["ts"] <= hi
                   and id(g) not in used_gw]
            d = {"name": name, "seg_s": round(seg, 2), "gw": None}
            cpu_s = None
            if hit:
                g = max(hit, key=lambda x: num(x.get("proc_wall")) or 0)
                used_gw.add(id(g))
                d["gw"] = safe_name(g.get("gateway")) or safe_name(g.get("cmd"))
                d["host"] = safe_name(g.get("host"))
                if num(g.get("proc_cpu")) is not None:
                    cpu_s, d["src"] = num(g["proc_cpu"]), "gateway"
            if cpu_s is None and cpu is not None:
                cpu_s = cpu.delta("cpu_us", prev, r["ts"])
                d["src"] = "cgroup" if cpu_s is not None else None
            d["cpu_s"] = round(min(cpu_s, seg), 2) if cpu_s is not None else None
            d["class"] = classify(cpu_s, seg)
            tools.append(d)
        prev = r["ts"]
    wake = wake_for(u0, events, used_wakes) if events else None
    aux = sum(1 for e in evals if u0 - 1 <= e["ts"] <= final["ts"] + 1 and e.get("aux") and e.get("model"))
    t.update(calls=calls, tools=tools, aux_calls=aux, wake=wake)
    sm = lambda xs: round(sum(x for x in xs if x is not None), 2)
    t["pre_s"], t["model_s"] = sm(c.get("pre_s") for c in calls), sm(c.get("model_s") for c in calls)
    t["retry_s"], t["hermes_s"] = sm(c.get("retry_s") for c in calls), sm(c.get("hermes_s") for c in calls)
    t["ttfb_s"] = sm(c.get("ttfb_s") for c in calls if c.get("matched") and not c.get("buf"))   # a buffered answer's ttfb is its total: not a first token
    t["gen_s"] = sm(c.get("gen_s") for c in calls)
    t["unmatched_s"] = sm(c["seg_s"] for c in calls if not c["matched"])
    t["tools_s"] = sm(d["seg_s"] for d in tools)
    t["tools_cpu_s"] = sm(d["cpu_s"] for d in tools)
    t["tools_wait_s"] = sm(d["seg_s"] - d["cpu_s"] for d in tools if d["cpu_s"] is not None)
    t["tools_unknown_s"] = sm(d["seg_s"] for d in tools if d["cpu_s"] is None)
    if cpu is not None:
        for name, field in (("cpu_s", "cpu_us"), ("throttled_s", "thr_us"), ("io_stall_s", "io_psi_us"), ("mem_stall_s", "mem_psi_us")):
            v = cpu.delta(field, u0, final["ts"])
            t[name] = round(v, 2) if v is not None else None
    w = wake or {}
    # wait_s runs from the message being sent to Hermes storing it (a web hold ends when the request is replayed, which is when the row is stored);
    # chain_s from the person's last message of the burst, so the buckets below (which cover the chain) add up to human_s
    t["human_s"] = round(w.get("wait_s", 0) + t["chain_s"], 2)
    t["machine_s"] = sm([t["hermes_s"], t["pre_s"], t["tools_cpu_s"], w.get("boot_s"), w.get("intake_s"), w.get("admit_s")])
    t["provider_s"] = round(t["model_s"] + t["retry_s"], 2)
    t["external_s"] = sm([t["tools_wait_s"], w.get("detect_s")])
    t["unknown_s"] = round(t["unmatched_s"] + t["tools_unknown_s"], 2)
    t["kind"] = "+".join(sorted({d["gw"] and "gateway:" + str(d["gw"]) or d["name"] for d in tools})) or "plain"
    return t


# ---------------------------------------------------------------- aggregates
FIELDS = ("human_s", "total_s", "chain_s", "machine_s", "provider_s", "external_s", "unknown_s", "hermes_s", "pre_s", "model_s",
          "ttfb_s", "gen_s", "retry_s", "tools_s", "tools_cpu_s", "tools_wait_s", "cpu_s", "throttled_s", "io_stall_s")
KINDS_MAX = 15                   # kinds of turn kept in a summary (the set of tools a turn used; "plain" = none), most frequent first
WAKE_FIELDS = ("wait_s", "detect_s", "admit_s", "boot_s", "intake_s")


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 2)


def stats(xs):
    xs = [x for x in xs if x is not None]
    return {"n": len(xs), "sum": round(sum(xs), 1), "mean": round(sum(xs) / len(xs), 2) if xs else None, "p50": pct(xs, 0.5), "p90": pct(xs, 0.9), "p95": pct(xs, 0.95)}


def group(turns):
    g = {f: stats(t.get(f) for t in turns) for f in FIELDS}
    g.update({"wake_" + f: stats((t["wake"] or {}).get(f) for t in turns if t["wake"]) for f in WAKE_FIELDS})
    total = sum(t["human_s"] for t in turns) or 1
    g["share_of_human"] = {f: round(sum(t.get(f) or 0 for t in turns) / total, 3) for f in ("machine_s", "provider_s", "external_s", "unknown_s")}
    g["turns"] = len(turns)
    return g


def brief(turns):
    """The few figures that tell kinds of turns apart."""
    g = group(turns)
    return {"turns": len(turns), "human_s": g["human_s"], "machine_s": g["machine_s"], "provider_s": g["provider_s"],
            "tools_s": g["tools_s"], "share_of_human": g["share_of_human"]}


def slowest(turns, n=10):
    """The n longest single steps of the period: only a kind of step, a tool name or model id, seconds and the time."""
    steps = []
    for t in turns:
        w = t["wake"] or {}
        if w.get("boot_s") is not None:
            steps.append(("wake boot", w["boot_s"], t["ts"]))
        for c in t["calls"]:
            steps.append(("model call " + str(c.get("model") or "unmatched"), c["seg_s"], t["ts"]))
        for d in t["tools"]:
            steps.append(("tool " + (d["gw"] and "gateway:" + str(d["gw"]) or d["name"]), d["seg_s"], t["ts"]))
    steps.sort(key=lambda x: -x[1])
    return [{"step": a, "s": b, "ts": c} for a, b, c in steps[:n]]


def summarize(turns, label, skipped):
    calls = [c for t in turns for c in t["calls"]]
    tools = [d for t in turns for d in t["tools"]]
    by_model, by_tool = collections.defaultdict(list), collections.defaultdict(list)
    by_kind, by_day = collections.defaultdict(list), collections.defaultdict(list)
    for t in turns:
        by_kind[t["kind"]].append(t)
        by_day[dt.datetime.fromtimestamp(t["ts"], dt.timezone.utc).strftime("%Y-%m-%d")].append(t)
    for c in calls:
        if c["matched"]:
            by_model[c["model"]].append(c)
    for d in tools:
        by_tool[d["gw"] and "gateway:" + str(d["gw"]) or d["name"]].append(d)
    return {
        "label": label, "turns": len(turns), "turns_skipped_unanswered": skipped,
        "all": group(turns), "awake": group([t for t in turns if not t["wake"]]), "woken": group([t for t in turns if t["wake"]]),
        "plain": group([t for t in turns if not t["tools"]]), "with_tools": group([t for t in turns if t["tools"]]),
        "kinds": {k: brief(ts) for k, ts in sorted(by_kind.items(), key=lambda x: -len(x[1]))[:KINDS_MAX]},
        "days": {day: brief(ts) for day, ts in sorted(by_day.items())},
        "slowest": slowest(turns),
        "calls": {"n": len(calls), "matched": sum(1 for c in calls if c["matched"]), "aux_in_windows": sum(t["aux_calls"] for t in turns)},
        "models": {m: {"n": len(cs), "ttfb_p50": pct([c["ttfb_s"] for c in cs if c.get("ttfb_s") is not None and not c["buf"]], 0.5),
                       "model_p50": pct([c["model_s"] for c in cs], 0.5), "hermes_p50": pct([c["hermes_s"] for c in cs], 0.5),
                       "tok_per_s_p50": pct([c["tok"] / c["gen_s"] for c in cs if c.get("tok") and c.get("gen_s") and c["gen_s"] > 0.2], 0.5),
                       "ptok_p50": pct([c["ptok"] for c in cs if c.get("ptok")], 0.5)} for m, cs in sorted(by_model.items())},
        "tools": {n: {"n": len(ds), "seg_p50": pct([d["seg_s"] for d in ds], 0.5), "seg_p95": pct([d["seg_s"] for d in ds], 0.95),
                      "seg_sum": round(sum(d["seg_s"] for d in ds), 1),
                      "classes": dict(collections.Counter(d["class"] for d in ds))} for n, ds in sorted(by_tool.items())},
    }


def show(s, out=None):
    p = lambda *a: print(*a, file=out or sys.stdout)
    p(f"== {s['label']}: {s['turns']} turns ({s['turns_skipped_unanswered']} with no final answer left out); "
      f"{s['calls']['matched']}/{s['calls']['n']} model calls matched to the router log")
    for name in ("all", "awake", "woken", "plain", "with_tools"):
        g = s[name]
        if not g["turns"]:
            continue
        sh = g["share_of_human"]
        p(f"-- {name}: {g['turns']} turns, human wait p50 {g['human_s']['p50']} s, p90 {g['human_s']['p90']} s; share of the time: machine {sh['machine_s']:.0%}"
          f", provider {sh['provider_s']:.0%}, external {sh['external_s']:.0%}, unknown {sh['unknown_s']:.0%}")
        p("   " + "  ".join(f"{f[:-2]} {g[f]['p50']}" for f in ("hermes_s", "pre_s", "model_s", "ttfb_s", "gen_s", "retry_s", "tools_s", "tools_cpu_s", "tools_wait_s")
                            if g[f]["n"]) + "   (medians, s)")
    if s["woken"]["turns"]:
        w = s["woken"]
        p(f"-- cold turns: {w['turns']} (after a wake or a manual restart); warm = the `awake` group. Never compare a cold group with a warm one")
        p("-- wake steps (median s): " + "  ".join(f"{f[:-2]} {w['wake_' + f]['p50']}" for f in WAKE_FIELDS if w["wake_" + f]["n"]))
    for name in ("days", "kinds"):
        for k, v in s.get(name, {}).items():
            sh = v["share_of_human"]
            p(f"-- {name[:-1]} {k}: {v['turns']} turns, human p50 {v['human_s']['p50']} s p90 {v['human_s']['p90']} s, machine {sh['machine_s']:.0%}, provider {sh['provider_s']:.0%}")
    if s.get("slowest"):
        p("-- slowest steps: " + "; ".join(f"{x['step']} {x['s']} s" for x in s["slowest"][:5]))
    for m, v in s["models"].items():
        p(f"   model {m}: n={v['n']} ttfb p50 {v['ttfb_p50']} s, call p50 {v['model_p50']} s, hermes gap p50 {v['hermes_p50']} s, {v['tok_per_s_p50']} tok/s, prompt {v['ptok_p50']} tok")
    for n, v in s["tools"].items():
        p(f"   tool {n}: n={v['n']} p50 {v['seg_p50']} s p95 {v['seg_p95']} s, {v['classes']}")


def compare(a, b, out=None):
    p = lambda *x: print(*x, file=out or sys.stdout)
    p(f"{'':28s}{a['label']:>14s}{b['label']:>14s}   B/A")
    for grp in ("all", "awake", "woken", "plain", "with_tools"):
        ga, gb = a[grp], b[grp]
        if not ga["turns"] or not gb["turns"]:
            continue
        p(f"[{grp}] turns {ga['turns']} vs {gb['turns']}")
        for f in ("human_s", "machine_s", "provider_s", "external_s", "unknown_s", "hermes_s", "model_s", "ttfb_s", "gen_s", "tools_s", "tools_cpu_s",
                  "tools_wait_s", "io_stall_s", "throttled_s"):
            x, y = ga[f]["p50"], gb[f]["p50"]
            if x is None or y is None:
                continue
            p(f"  {f + ' p50':26s}{x:14.2f}{y:14.2f}   {('%.2f' % (y / x)) if x else '-'}")
        for f in WAKE_FIELDS:
            x, y = ga["wake_" + f]["p50"], gb["wake_" + f]["p50"]
            if x is not None and y is not None:
                p(f"  {'wake ' + f[:-2] + ' p50':26s}{x:14.2f}{y:14.2f}   {('%.2f' % (y / x)) if x else '-'}")
    ma, mb = set(a.get("models", {})), set(b.get("models", {}))
    if ma != mb:
        p(f"NOTE: not the same models on both sides (only in {a['label']}: {sorted(ma - mb) or '-'}; only in {b['label']}: {sorted(mb - ma) or '-'}): "
          f"the comparison is not fair for the turns that used them")
    for m in sorted(ma & mb):
        va, vb = a["models"][m], b["models"][m]
        p(f"[model {m}] calls {va['n']} vs {vb['n']}")
        for f in ("ttfb_p50", "model_p50", "hermes_p50", "ptok_p50"):
            x, y = va.get(f), vb.get(f)
            if x is not None and y is not None:
                p(f"  {f:26s}{x:14.2f}{y:14.2f}   {('%.2f' % (y / x)) if x else '-'}")
    for k in [k for k in a.get("kinds", {}) if k in b.get("kinds", {})]:
        ka, kb = a["kinds"][k], b["kinds"][k]
        p(f"[kind {k}] turns {ka['turns']} vs {kb['turns']}")
        for f in ("human_s", "machine_s", "provider_s", "tools_s"):
            x, y = ka[f]["p50"], kb[f]["p50"]
            if x is not None and y is not None:
                p(f"  {f + ' p50':26s}{x:14.2f}{y:14.2f}   {('%.2f' % (y / x)) if x else '-'}")
    for n in sorted(set(a["tools"]) & set(b["tools"])):
        x, y = a["tools"][n]["seg_p50"], b["tools"][n]["seg_p50"]
        p(f"  tool {n:21s}{x:14.2f}{y:14.2f}   {('%.2f' % (y / x)) if x else '-'}   (n {a['tools'][n]['n']} vs {b['tools'][n]['n']})")


# ---------------------------------------------------------------- cli
def since_of(v):
    if v is None:
        return 0.0
    if v.startswith("-") and v[-1] in "mhd":
        return time.time() - float(v[1:-1]) * {"m": 60, "h": 3600, "d": 86400}[v[-1]]
    return float(v)


def run(a):
    since = since_of(a.since)
    by_session, source = read_rows(a.db, a.immutable)
    evals = [e for e in jsonl(a.eval) if e["ts"] >= since - 60]
    gws = [g for g in jsonl(a.gateway) if g["ts"] >= since - 60]
    cpu = Cpu(jsonl([a.cpu])) if a.cpu else None
    if cpu is not None and not cpu.t:
        cpu = None
    events = []
    if a.journal:
        try:
            text = open(a.journal, errors="replace").read()
        except OSError as e:
            print(f"cannot read {a.journal}: {e.strerror}", file=sys.stderr)
            text = ""
        names = {m.group(2) for rx in JOURNAL.values() for m in (rx.match(l) for l in text.splitlines()) if m}
        stack = a.stack or (next(iter(names)) if len(names) == 1 else None)
        if stack is None and names:
            print("the journal has several stacks: pass --stack NAME", file=sys.stderr)
            return 2
        events = parse_journal(text, stack) if stack else []
    if a.restarts:
        try:
            for line in open(a.restarts, errors="replace"):
                m = re.match(r"\s*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)(?:\s+([\d.]+))?\s*$", line)
                if m:
                    events.append({"kind": "manual", "ts": utc(m.group(1)), "boot_s": float(m.group(2)) if m.group(2) else None})
        except OSError as e:
            print(f"cannot read {a.restarts}: {e.strerror}", file=sys.stderr)
    turns, skipped, used_w, used_e, used_g = [], 0, set(), set(), set()
    allturns = [(sid, tn) for sid, rows in by_session.items() for tn in split_turns(rows)]
    allturns.sort(key=lambda x: x[1]["users"][0]["ts"])
    for sid, tn in allturns:
        if tn["users"][0]["ts"] < since:
            continue
        t = decompose(tn, sid, source.get(sid), evals, gws, events, used_w, cpu, used_e, used_g)
        if t is None:
            skipped += 1
        else:
            turns.append(t)
    if a.front_log:
        try:
            reqs = parse_front(open(a.front_log, errors="replace").read())
        except OSError:
            reqs = []
        for t in turns:
            end = t["ts"] + t["total_s"]
            near = [r for r in reqs if abs(r["ts"] - end) <= 5 and r["rt"] >= t["total_s"] - 2]
            if near:
                t["web_rt_s"] = min(near, key=lambda r: abs(r["ts"] - end))["rt"]
    s = summarize(turns, a.label, skipped)
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"summary": s, "turns": turns}, f)
        os.chmod(a.json, 0o600)
    show(s)
    return 0


def load_summary(path):
    d = json.load(open(path))
    return d.get("summary", d)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="break down the turns of one stack")
    r.add_argument("--db", required=True, help="Hermes state.db (a copy, or the live file read-only)")
    r.add_argument("--immutable", action="store_true", help="open the db immutable (a copy without its -wal file)")
    r.add_argument("--eval", nargs="*", help=".model-eval.1.jsonl .model-eval.jsonl of the router (/workdir)")
    r.add_argument("--gateway", nargs="*", help=".gateway-log.1.jsonl .gateway-log.jsonl (/workdir)")
    r.add_argument("--journal", help="text of `journalctl --user -u aibridge-waker -o cat` (wake steps)")
    r.add_argument("--front-log", help="the web front's nginx access.log (rt= field, ops/../web/nginx-main.conf)")
    r.add_argument("--cpu", help="file written by ops/turn_cpu_sampler.py")
    r.add_argument("--stack", help="stack name in the journal ([name] prefix)")
    r.add_argument("--since", help="epoch seconds or -90m, -6h, -2d")
    r.add_argument("--restarts", help="stack with no waker: UTC time of each manual `docker start`, one per line, optional stopwatch boot seconds after it")
    r.add_argument("--label", default="run")
    r.add_argument("--json", help="write per-turn rows and the summary here (0600)")
    c = sub.add_parser("compare", help="two summaries side by side (A then B)")
    c.add_argument("a")
    c.add_argument("b")
    a = ap.parse_args(argv)
    if a.cmd == "compare":
        compare(load_summary(a.a), load_summary(a.b))
        return 0
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
