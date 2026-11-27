#!/usr/bin/env python3
"""Measure the cloud model providers' uptime ourselves, alert on it (Zabbix, else the ops bot), and say what to do about it.

provider_status.py reads the providers' status pages. A status page is what the provider says; this is what we see: the real
calls of every stack, plus a cheap probe of our own. Every 5 minutes (provider-uptime.timer):

  1. PASSIVE. Reads each stack's router evaluation log (router.py EVAL_LOG, /workdir/.model-eval.jsonl: one metadata line per
     cloud call). Used fields: time, model name, result, seconds, time to first byte. Never a session, a turn, text or a key.
     Per provider: success rate, error classes (timeout, 5xx, 429, auth, net), p50/p95 time to first byte, last success, over
     5 min, 10 min, 60 min and 24 h. Availability = ok / (ok + timeout + 5xx + net): a 429 (the person's own allowance) or a
     401 (their own key) is not the provider being down, so it is counted apart and never held against it.
  2. ACTIVE, rate limited, jittered. Per provider a "reach" probe every PROBE_INTERVAL_S (default 300 s): GET <base>/models. With
     no probe key it is unauthenticated and spends nothing (any HTTP answer below 500 means the front end is alive). If
     ops.env holds PROBE_KEY_<PROVIDER> (a key made for probing, the OPERATOR's, never a person's) the same request is
     authenticated. Opt-in per provider: PROBE_CHAT_<PROVIDER>=<model id> adds a 1-token chat probe (at most every
     PROBE_CHAT_MIN_S, default 900 s), the only way to see "models list answers, inference is down". Keys named
     *_API_KEY, the ones people use, are never read here.
  3. EVALUATE each provider: up, degraded or down (thresholds below, env overridable), keep the outage intervals.
  4. ZABBIX. One host per provider (provider-<name>), trapper items (ops/zabbix/template_provider_uptime.yaml), pushed with
     the built-in trapper protocol (no zabbix_sender needed; ZBX_SENDER=<path> uses the binary instead, for PSK). With Zabbix
     reachable and accepting the values, Zabbix owns the paging (down: High; degraded: Average; collector silent: Average)
     and this script only adds the fallback plan (below) once per outage. Without ZBX_SERVER, or when Zabbix refuses the
     values, this script alerts through ops/lib/notify.py itself, so nothing goes quiet.
  5. FALLBACK READINESS. When a provider is down, the alert names the stacks that would fail and the exact way to put them on
     the local LLM set. Nothing is switched automatically: `provider_uptime.py fallback --provider P` prints the same steps and
     changes nothing.

  provider_uptime.py run [--dry-run] [--jitter S] [--no-probe] [--no-passive]   what the timer runs
  provider_uptime.py status [--json]                        table per provider; changes nothing
  provider_uptime.py report [--month YYYY-MM] [--send] [--json]   uptime % per provider for a month (default: last month)
  provider_uptime.py fallback --provider P [--json]         affected stacks and operator steps; changes nothing
  provider_uptime.py template | hosts                       the Zabbix template YAML | the Zabbix hosts to create

Thresholds (env, ops.env): UPTIME_PROBE_FAILS=3 probes in a row, UPTIME_CHAT_FAILS=2, UPTIME_AVAIL_MIN=50 (% over 10 min),
UPTIME_MIN_CALLS=5, UPTIME_TTFB_P95_MAX=15 (s), UPTIME_PROBE_MS_MAX=5000, UPTIME_429_PCT=50, UPTIME_MIN_CALLS_429=10. The
Zabbix template carries the same numbers as macros ({$PROV.*}); change both together.
ZBX_SERVER (+ ZBX_PORT 10051, ZBX_SENDER, ZBX_SENDER_ARGS, ZBX_PROVIDERS: the providers that have a Zabbix host).
Environment (tests): PROVIDER_UPTIME_STATE, PROVIDER_UPTIME_STACKS, PROVIDER_UPTIME_MASTER, OPS_ENV.
Exit: 0; a crash is what the unit's OnFailure reports.
"""
import argparse, calendar, collections, concurrent.futures as cf, datetime as dt, fcntl, hashlib, json, math, os, random, re
import shlex, shutil, socket, struct, subprocess, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, HERE)
import providers  # noqa: E402  (ops/lib/providers.py: base URLs of the providers)

AIBRIDGE = os.path.dirname(HERE)
STATE = os.path.expanduser(os.environ.get("PROVIDER_UPTIME_STATE", "~/.local/state/provider_uptime.json"))
STACKS = os.environ.get("PROVIDER_UPTIME_STACKS", os.path.join(HERE, "wake", "stacks.json"))
MASTER = os.environ.get("PROVIDER_UPTIME_MASTER", os.path.join(HERE, "gateways.json"))
ENV_FILE = os.environ.get("OPS_ENV", os.path.expanduser("~/aibridge/ops/ops.env"))

EVAL_FILES = (".model-eval.1.jsonl", ".model-eval.jsonl")
READ_LIMIT = 6 * 1024 * 1024          # router.py rotates a log past 5 MB, so one generation always fits
RECENT_S = 48 * 3600                  # raw call records kept (windows up to 24 h, with slack)
RECENT_MAX = 150_000
HOURS_KEEP_S = 120 * 86400            # hourly buckets kept for the monthly report
INTERVALS_MAX = 1000
WINDOWS = (("5m", 300), ("10m", 600), ("60m", 3600), ("24h", 86400))
BOUNDS = (0.5, 1, 2, 4, 8, 16, 32, 64)  # time-to-first-byte histogram of the hourly buckets (seconds)
FAIL = ("timeout", "5xx", "net")      # error classes that count against a provider's availability
CLASSES = ("ok", "timeout", "5xx", "net", "429", "auth", "client", "other")
ERR_ITEMS = ("timeout", "5xx", "429", "auth", "net")   # the error counters pushed to Zabbix
PROBE_TIMEOUT_S = 10
CONTROL_URLS = ("https://www.gstatic.com/generate_204", "https://www.cloudflare.com/cdn-cgi/trace")   # neutral, always-up endpoints (PROBE_CONTROL overrides)
CHAT_TIMEOUT_S = 30
DUE_SLACK = 0.8                       # a probe is due after 80 % of its interval: the timer's cadence is the interval itself
HOLD_RUNS = 2                         # evaluations in a row that must say "better" before an outage is closed (no flapping)

# router display name (first words) -> provider key of ops/lib/providers.py
NAME_PREFIX = (("NVIDIA", "nvidia"), ("Token Harbor", "tokenharbor"), ("Gemini", "gemini"), ("OpenRouter", "openrouter"),
               ("Cloudflare", "cloudflare"), ("Hugging Face", "huggingface"), ("HuggingFace", "huggingface"), ("Groq", "groq"))
PROBE_PROVIDERS = ("nvidia", "gemini", "huggingface", "openrouter", "tokenharbor", "groq")   # cloudflare's URL carries a private account id
HOSTED = PROBE_PROVIDERS + ("cloudflare",)    # one Zabbix host each (cloudflare has traffic, no probe)
LABEL = {p: d["label"] for p, d in providers.PROVIDERS.items()}
LABEL["cloudflare"] = "Cloudflare Workers AI"
STATE_NUM = {"up": 0, "degraded": 1, "down": 2}
TEMPLATE_NAME = "Cloud provider uptime"
HOST_PREFIX = "provider-"
OUTBOX_KEY = "provider-uptime:sender"
NET_KEY = "provider-uptime:collector-net"


# ---------------------------------------------------------------- configuration

def read_env_file(path):
    conf = {}
    try:
        for line in open(path):
            k, sep, v = line.partition("=")
            if sep and not k.lstrip().startswith("#"):
                conf[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return conf


def load_conf(env=None):
    """ops.env plus the environment. Only the names this script documents are ever looked up; never a key used by a person."""
    conf = read_env_file(ENV_FILE)
    for k, v in (os.environ if env is None else env).items():
        if k.startswith(("UPTIME_", "PROBE_", "ZBX_")):
            conf[k] = v
    return conf


def num(conf, name, default):
    try:
        return float(conf.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def thresholds(conf):
    return {"probe_fails": int(num(conf, "UPTIME_PROBE_FAILS", 3)), "chat_fails": int(num(conf, "UPTIME_CHAT_FAILS", 2)),
            "avail_min": num(conf, "UPTIME_AVAIL_MIN", 50), "min_calls": int(num(conf, "UPTIME_MIN_CALLS", 5)),
            "ttfb_p95_max": num(conf, "UPTIME_TTFB_P95_MAX", 15), "probe_ms_max": num(conf, "UPTIME_PROBE_MS_MAX", 5000),
            "pct429": num(conf, "UPTIME_429_PCT", 50), "min_calls_429": int(num(conf, "UPTIME_MIN_CALLS_429", 10))}


# ---------------------------------------------------------------- classification and statistics

def provider_of(name):
    for prefix, p in NAME_PREFIX:
        if isinstance(name, str) and name.startswith(prefix):
            return p
    return None


def classify(result):
    """Error class of an eval-log result: "ok", "HTTP 503", "TimeoutError", "stream-broken", "empty answer (stop)", an exception name."""
    if result == "ok":
        return "ok"
    m = re.fullmatch(r"HTTP (\d{3})", str(result))
    if m:
        code = int(m.group(1))
        if code == 429:
            return "429"
        if code in (401, 403):
            return "auth"
        if code == 408:
            return "timeout"
        if code >= 500:
            return "5xx"
        return "client"                     # 400, 404, 410...: a request or model problem, not the provider being down
    r = str(result)
    if "imeout" in r:
        return "timeout"
    if r == "stream-broken":
        return "net"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", r):
        return "net"                        # an exception class name: refused, reset, TLS, DNS, truncated body
    return "other"


def pct(sorted_vals, p):
    if not sorted_vals:
        return None
    return sorted_vals[max(0, math.ceil(p / 100 * len(sorted_vals)) - 1)]


def window_stats(events, provider, now, secs, stack=None):
    """events: [ts, provider, stack, cls, seconds, ttfb, model]. Counters, availability and success %, time to first byte p50/p95 (ok calls).
    "wide": the failures look like the provider's and not one model's: they span 2 or more models, or the window saw a single model
    in all and it failed on 2 or more stacks. One flaky model among healthy ones (explore mode tries such models) is not an outage."""
    lo = now - secs
    c = collections.Counter()
    ttfb, last_ok = [], None
    models, fail_models, fail_stacks = set(), set(), set()
    for ts, p, st, cls, s, tf, *rest in events:
        if p != provider or ts < lo or ts > now + 60 or (stack is not None and st != stack):
            continue
        c[cls] += 1
        model = rest[0] if rest else "?"
        models.add(model)
        if cls in FAIL:
            fail_models.add(model)
            fail_stacks.add(st)
        if cls == "ok":
            last_ok = max(last_ok or 0, ts)
            if tf is not None:
                ttfb.append(tf)
    ttfb.sort()
    calls = sum(c.values())
    denom = c["ok"] + sum(c[k] for k in FAIL)
    wide = bool(fail_models) and (len(fail_models) >= 2 or (len(models) == 1 and len(fail_stacks) >= 2))
    out = {"calls": calls, "ok": c["ok"], **{k: c[k] for k in CLASSES if k != "ok"}, "wide": wide,
           "avail": round(100 * c["ok"] / denom, 1) if denom else None,
           "success": round(100 * c["ok"] / calls, 1) if calls else None,
           "ttfb_p50": pct(ttfb, 50), "ttfb_p95": pct(ttfb, 95), "last_ok": last_ok}
    return out


def hist_percentile(hist, p):
    """Upper bound (s) of the histogram bucket holding percentile p; None when empty, inf for the open top bucket."""
    n = sum(hist)
    if not n:
        return None
    need, acc = max(1, math.ceil(p / 100 * n)), 0
    for i, v in enumerate(hist):
        acc += v
        if acc >= need:
            return BOUNDS[i] if i < len(BOUNDS) else math.inf
    return math.inf


def hour_key(ts):
    return time.strftime("%Y-%m-%dT%H", time.gmtime(ts))


# ---------------------------------------------------------------- state

def new_state():
    return {"v": 1, "hwm": {}, "recent": [], "hours": {}, "probes": {}, "prov": {}, "intervals": [], "first": {}, "last_ok": {},
            "unmapped": {}, "runs": 0, "net": {}}


def load_state(path=None):
    try:
        s = json.load(open(path or STATE))
        if isinstance(s, dict) and s.get("v") == 1:
            return {**new_state(), **s}
    except (OSError, ValueError):
        pass
    return new_state()


def save_state(state, path=None):
    path = path or STATE
    os.makedirs(os.path.dirname(path) or ".", mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, separators=(",", ":"))
    os.replace(tmp, path)


class locked:
    """One run at a time (the timer and a hand-run `run` must not interleave their writes)."""
    def __init__(self, path=None):
        self.path = (path or STATE) + ".lock"

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path) or ".", mode=0o700, exist_ok=True)
        self.f = open(self.path, "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def bucket(state, provider, ts):
    h = state["hours"].setdefault(hour_key(ts), {})
    return h.setdefault(provider, {"calls": {}, "ttfb": [0] * (len(BOUNDS) + 1), "probe": [0, 0], "chat": [0, 0]})


def note_seen(state, provider, ts):
    state["first"].setdefault(provider, int(ts))


# ---------------------------------------------------------------- passive: the stacks' router logs

def default_reader(stack, name):
    """Bytes of the stack's /workdir/<name>: host side first, `docker cp` (bounded, also while the stack sleeps) when the file is root 0600."""
    import early_alert as ea
    path = os.path.join(ea.stack_paths(stack), name)
    try:
        return ea.read_small(path, READ_LIMIT)
    except PermissionError:
        brain = stack.get("brain") or ""
        return ea.cp_read(brain, "/workdir/" + name, READ_LIMIT) if brain else None


def load_stacks(path=None):
    try:
        d = json.load(open(path or STACKS))
    except (OSError, ValueError):
        return []
    return [s for s in d.get("stacks", []) if isinstance(s, dict) and s.get("name")]


def read_rows(stack, reader):
    """[(ts, model, result, seconds, ttfb)] of one stack, metadata only. Lines that do not parse (a torn first line of a tail) are skipped."""
    rows = []
    for name in EVAL_FILES:
        try:
            raw = reader(stack, name)
        except Exception:
            raw = None
        for line in (raw or b"").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if not isinstance(e, dict) or "feedback" in e:
                continue
            ts, model, result = e.get("ts"), e.get("model"), e.get("result")
            if isinstance(ts, (int, float)) and isinstance(model, str) and isinstance(result, str):
                s, tf = e.get("s"), e.get("ttfb")
                rows.append((float(ts), model, result, s if isinstance(s, (int, float)) else None,
                             tf if isinstance(tf, (int, float)) else None))
    rows.sort(key=lambda r: r[0])
    return rows


HWM_SLACK_S = 2     # two writers (a gateway and the router) can append a line a moment out of order


def ingest(state, stack_name, rows, now):
    """Add the new rows of one stack once: a high-water mark with a 2 s slack and the fingerprints of the lines inside it, so a line
    written slightly out of order is still taken and a line read twice is not. Returns how many calls were kept."""
    hts, fps = state["hwm"].get(stack_name, [0, []])
    fps = set(fps)
    newest = hts
    kept = 0
    for ts, model, result, s, tf in rows:
        fp = f"{ts}|{model}|{result}|{s}"
        if ts < hts - HWM_SLACK_S or fp in fps or ts < now - RECENT_S or ts > now + 60:
            continue
        fps.add(fp)
        newest = max(newest, ts)
        p = provider_of(model)
        if p is None:
            key = " ".join(model.split()[:1])[:24]
            state["unmapped"][key] = state["unmapped"].get(key, 0) + 1
            continue
        cls = classify(result)
        state["recent"].append([round(ts, 1), p, stack_name, cls, s, tf, model[:60]])
        b = bucket(state, p, ts)
        b["calls"][cls] = b["calls"].get(cls, 0) + 1
        if cls == "ok" and tf is not None:
            b["ttfb"][next((i for i, ub in enumerate(BOUNDS) if tf <= ub), len(BOUNDS))] += 1
        note_seen(state, p, ts)
        if cls == "ok":
            state["last_ok"][p] = max(state["last_ok"].get(p, 0), int(ts))
        kept += 1
    state["hwm"][stack_name] = [newest, sorted(f for f in fps if float(f.split("|", 1)[0]) >= newest - HWM_SLACK_S)]
    return kept


def prune(state, now):
    state["recent"] = [r for r in state["recent"] if r[0] >= now - RECENT_S][-RECENT_MAX:]
    cut = hour_key(now - HOURS_KEEP_S)
    state["hours"] = {k: v for k, v in state["hours"].items() if k >= cut}
    state["intervals"] = state["intervals"][-INTERVALS_MAX:]


# ---------------------------------------------------------------- active probes

def probe_keys(conf, provider):
    up = provider.upper()
    return conf.get(f"PROBE_KEY_{up}") or "", conf.get(f"PROBE_CHAT_{up}") or ""


def probe_request(provider, mode, key, model):
    """The request of one probe. keyless/keyed: GET <base>/models (spends nothing). chat: a 1-token completion with a fixed word."""
    base = providers.base(provider)
    hdr = {"User-Agent": "bridgeai-provider-uptime/1"}
    if key and mode in ("keyed", "chat"):
        hdr["Authorization"] = f"Bearer {key}"
    if mode == "chat":
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}).encode()
        return urllib.request.Request(base + "/chat/completions", data=body, headers={**hdr, "Content-Type": "application/json"})
    return urllib.request.Request(base + "/models", headers=hdr)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A probe never follows a redirect: urllib keeps the Authorization header on a redirect to another host, which would hand the probe key
    to whoever the answer points at. The 3xx answer itself says the front end is alive."""
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def open_probe(req, timeout=None):
    return _OPENER.open(req, timeout=timeout)


def probe_once(provider, mode, key, model, opener=open_probe):
    """{up, ok, cls, code, ms, auth}. up (ok = 1) = the provider answered with something below 500: a 429 or a 401 is a live front end.
    auth is False when our own probe key was refused (keyed and chat probes only)."""
    req = probe_request(provider, mode, key, model)
    t0 = time.time()
    timeout = CHAT_TIMEOUT_S if mode == "chat" else PROBE_TIMEOUT_S
    code, cls, auth, body_ok = 0, "net", None, True
    try:
        with opener(req, timeout=timeout) as r:
            code = r.status
            body = r.read(262144)
        cls = "ok"
        if mode == "chat":
            try:
                body_ok = isinstance(json.loads(body).get("choices"), list)
            except (ValueError, AttributeError):
                body_ok = False
            if not body_ok:
                cls = "net"
    except urllib.error.HTTPError as e:
        code = e.code
        cls = classify(f"HTTP {code}")
        if code in (401, 403) and mode != "keyless":
            auth = False
    except Exception as e:
        cls = "timeout" if ("imeout" in type(e).__name__ or "timed out" in str(e) or isinstance(getattr(e, "reason", None), socket.timeout)) else "net"
    ms = int((time.time() - t0) * 1000)
    up = cls not in FAIL
    return {"up": up, "ok": int(up), "cls": cls, "code": code, "ms": ms, "auth": auth}


def control_urls(conf):
    v = (conf.get("PROBE_CONTROL") or "").replace(" ", "")
    if v.lower() in ("off", "none", "0"):
        return []
    return [u for u in v.split(",") if u.startswith("https://")] or list(CONTROL_URLS)


def probe_control(conf, opener=open_probe):
    """Control probe: can this VM reach the internet at all? Same request as a reach probe but to neutral endpoints that are not a model
    provider (PROBE_CONTROL=url,url or off). Up when any answers below 500. Returns {"ok", "ms"} or None when it is switched off.
    A provider can only be called down when the control answers: a DNS or uplink failure of the VM is not a provider outage."""
    urls = control_urls(conf)
    if not urls:
        return None

    def one(u):
        t0 = time.time()
        try:
            with opener(urllib.request.Request(u, headers={"User-Agent": "bridgeai-provider-uptime/1"}), timeout=PROBE_TIMEOUT_S) as r:
                r.read(1024)
            up = True
        except urllib.error.HTTPError as e:
            up = e.code < 500
        except Exception:
            up = False
        return up, int((time.time() - t0) * 1000)
    with cf.ThreadPoolExecutor(max_workers=len(urls)) as ex:
        res = list(ex.map(one, urls))
    return {"ok": int(any(up for up, _ in res)), "ms": min(ms for _, ms in res)}


def collector_net_down(state):
    """True when the last control probe failed and every provider probed in that same pass failed too: the VM's own network, not a provider."""
    net = state.get("net") or {}
    if not net.get("last") or net.get("ok", 1):
        return False
    reach = [pr["reach"] for pr in state["probes"].values() if pr.get("reach", {}).get("last", 0) >= net["last"] - 60]
    return bool(reach) and not any(r.get("ok") for r in reach)


def probe_due(slot, now, interval):
    return now - slot.get("last", 0) >= interval * DUE_SLACK


def run_probes(state, conf, now, opener=open_probe):
    """Probe every provider whose slot is due (reach: every PROBE_INTERVAL_S, chat: at most every PROBE_CHAT_MIN_S, opt in). Concurrent,
    each bounded by its timeout, so a hung provider cannot stretch the run. Returns {provider: {"reach": res, "chat": res|None}}."""
    interval = max(60, num(conf, "PROBE_INTERVAL_S", 300))
    chat_min = max(300, num(conf, "PROBE_CHAT_MIN_S", 900))
    wanted = [p for p in (conf.get("PROBE_PROVIDERS", "") or ",".join(PROBE_PROVIDERS)).replace(" ", "").split(",") if p in PROBE_PROVIDERS]
    jobs = []
    for p in wanted:
        key, model = probe_keys(conf, p)
        slots = state["probes"].setdefault(p, {})
        if probe_due(slots.setdefault("reach", {}), now, interval):
            jobs.append((p, "reach", "keyed" if key else "keyless", key, ""))
        if key and model and probe_due(slots.setdefault("chat", {}), now, chat_min):
            jobs.append((p, "chat", "chat", key, model))
    results = {}
    with cf.ThreadPoolExecutor(max_workers=max(1, min(12, len(jobs)))) as ex:
        futs = {ex.submit(probe_once, p, mode, key, model, opener): (p, slot) for p, slot, mode, key, model in jobs}
        for f, (p, slot) in futs.items():
            res = f.result()
            res["mode"] = "chat" if slot == "chat" else ("keyed" if probe_keys(conf, p)[0] else "keyless")
            results.setdefault(p, {})[slot] = res
    for p, by_slot in results.items():
        for slot, res in by_slot.items():
            s = state["probes"][p][slot]
            s["streak"] = 0 if res["up"] else s.get("streak", 0) + 1
            s.update(last=int(now), ok=res["ok"], ms=res["ms"], code=res["code"], cls=res["cls"], mode=res["mode"], auth=res["auth"])
            hist = s.setdefault("hist", [])
            hist.append([int(now), res["ok"], res["ms"]])
            del hist[:-10]
            b = bucket(state, p, now)
            b["probe" if slot == "reach" else "chat"][0] += 1
            b["probe" if slot == "reach" else "chat"][1] += res["ok"]
            note_seen(state, p, now)
    return results


# ---------------------------------------------------------------- evaluate

def evaluate(provider, state, now, th):
    """(state, reasons) of one provider: "down" / "degraded" / "up", from the probes and the real calls. Same rules as the Zabbix template."""
    ev = state["recent"]
    w10 = window_stats(ev, provider, now, 600)
    pr = state["probes"].get(provider, {})
    reach, chat = pr.get("reach", {}), pr.get("chat", {})
    down, deg = [], []
    if reach.get("streak", 0) >= th["probe_fails"]:
        down.append(f"{reach['streak']} probes in a row without an answer ({reach.get('cls')})")
    if chat and chat.get("streak", 0) >= th["chat_fails"]:
        down.append(f"the chat probe failed {chat['streak']} times in a row ({chat.get('cls')})")
    if w10["calls"] >= th["min_calls"] and w10["avail"] is not None and w10["avail"] < th["avail_min"] and w10["wide"]:
        down.append(f"only {w10['avail']:.0f}% of {w10['calls']} real calls were answered in 10 min")
    if down:
        return "down", down
    hist = reach.get("hist", [])[-3:]
    if len(hist) == 3 and all(h[1] and h[2] > th["probe_ms_max"] for h in hist):
        deg.append(f"the last 3 probes took more than {th['probe_ms_max'] / 1000:.0f} s")
    if w10["calls"] >= th["min_calls"] and w10["ttfb_p95"] is not None and w10["ttfb_p95"] > th["ttfb_p95_max"]:
        deg.append(f"p95 time to first byte {w10['ttfb_p95']:.0f} s in 10 min")
    if w10["calls"] >= th["min_calls_429"] and 100 * w10["429"] >= th["pct429"] * w10["calls"]:
        deg.append(f"{w10['429']} of {w10['calls']} calls with 429 in 10 min")
    return ("degraded", deg) if deg else ("up", [])


def advance(state, provider, new, reasons, now):
    """Move the provider's state machine. Returns the transition (old, new) or None. Going back to "up" needs HOLD_RUNS good
    evaluations in a row, so a flapping provider is one outage, not ten. Outage intervals are kept for the monthly report."""
    cur = state["prov"].setdefault(provider, {"state": "up", "since": int(now), "clear": 0, "reasons": []})
    old = cur["state"]
    if STATE_NUM[new] < STATE_NUM[old]:
        cur["clear"] = cur.get("clear", 0) + 1
        if cur["clear"] < HOLD_RUNS:
            return None
    else:
        cur["clear"] = 0
    cur["reasons"] = reasons
    if new == old:
        return None
    if old != "up":
        for iv in reversed(state["intervals"]):
            if iv["p"] == provider and iv["e"] is None:
                iv["e"] = int(now)
                break
    if new != "up":
        state["intervals"].append({"p": provider, "k": new, "s": int(now), "e": None, "why": (reasons[0] if reasons else "")[:120]})
    cur.update(state=new, since=int(now), clear=0, plan_sent=False if new == "down" else cur.get("plan_sent", False))
    return old, new


# ---------------------------------------------------------------- Zabbix push

def zbx_host(provider):
    return HOST_PREFIX + provider


def metrics(provider, state, now, probes, quiet=False):
    """[(key, value)] of one provider. Numbers only (the template's item types); -1 means "no data in that window".
    Probe values go out only when the probe ran in this pass (a stale value pushed again would count as a new failure in Zabbix's
    count(...,#3)). quiet: the collector's own network is down, so only the heartbeat and the state are pushed."""
    ev = state["recent"]
    out = [("provider.heartbeat", int(now)), ("provider.state", STATE_NUM[state["prov"].get(provider, {}).get("state", "up")])]
    if quiet:
        return out
    reach_now = (probes.get(provider) or {}).get("reach")
    if reach_now:
        out += [("provider.probe.ok", reach_now["ok"]), ("provider.probe.ms", reach_now["ms"]), ("provider.probe.code", reach_now["code"])]
    chat_now = (probes.get(provider) or {}).get("chat")
    if chat_now:
        out += [("provider.chat.ok", chat_now["ok"]), ("provider.chat.ms", chat_now["ms"])]
    for w, secs in WINDOWS:
        s = window_stats(ev, provider, now, secs)
        none = lambda v: -1 if v is None else v
        out += [(f"provider.traffic.calls[{w}]", s["calls"]), (f"provider.traffic.avail[{w}]", none(s["avail"])),
                (f"provider.traffic.success[{w}]", none(s["success"])), (f"provider.traffic.ttfb_p50[{w}]", none(s["ttfb_p50"])),
                (f"provider.traffic.ttfb_p95[{w}]", none(s["ttfb_p95"]))]
        out += [(f"provider.traffic.errors[{w},{c}]", s[c]) for c in ERR_ITEMS]
        if w == "10m":
            out.append(("provider.traffic.wide[10m]", int(s["wide"])))
    return out


def trapper_packet(items):
    body = json.dumps({"request": "sender data", "data": [{"host": h, "key": k, "value": str(v)} for h, k, v in items]}).encode()
    return b"ZBXD\x01" + struct.pack("<Q", len(body)) + body


def trapper_send(items, server, port, timeout=10):
    """Zabbix trapper protocol over TCP (no zabbix_sender needed). Returns (processed, failed); raises OSError / ValueError."""
    with socket.create_connection((server, port), timeout=timeout) as s:
        s.sendall(trapper_packet(items))
        head = b""
        while len(head) < 13:
            chunk = s.recv(13 - len(head))
            if not chunk:
                raise OSError("the server closed the connection")
            head += chunk
        if head[:5] != b"ZBXD\x01":
            raise ValueError("not a Zabbix answer")
        n = struct.unpack("<Q", head[5:13])[0]
        if n > 65536:
            raise ValueError("answer too large")
        data = b""
        while len(data) < n:
            chunk = s.recv(n - len(data))
            if not chunk:
                break
            data += chunk
    info = json.loads(data).get("info", "")
    m = re.search(r"processed: (\d+); failed: (\d+)", info)
    if not m:
        raise ValueError("no processed/failed count in the answer")
    return int(m.group(1)), int(m.group(2))


def binary_send(items, sender, server, port, extra, runner=subprocess.run):
    """The same push through the zabbix_sender binary (for PSK/TLS via ZBX_SENDER_ARGS). Returns (processed, failed)."""
    lines = "".join('"%s" "%s" "%s"\n' % (h, k, str(v).replace('"', "'")) for h, k, v in items)
    r = runner([sender, "-z", server, "-p", str(port), "-i", "-", *shlex.split(extra or "")], input=lines, capture_output=True, text=True, timeout=60)
    m = re.search(r"processed: (\d+); failed: (\d+)", (r.stdout or "") + (r.stderr or ""))
    if not m:
        raise OSError(f"zabbix_sender gave no count (exit {r.returncode})")
    return int(m.group(1)), int(m.group(2))


def push(items, conf, sender=None, binary=None):
    """None when Zabbix is not configured, else (True, text) when it took every value, (False, why) otherwise."""
    server = conf.get("ZBX_SERVER", "").strip()
    if not server:
        return None
    port = int(num(conf, "ZBX_PORT", 10051))
    try:
        if conf.get("ZBX_SENDER", "").strip():
            path = conf["ZBX_SENDER"].strip()
            if not shutil.which(path):
                return False, "ZBX_SENDER is not an executable"
            processed, failed = (binary or binary_send)(items, path, server, port, conf.get("ZBX_SENDER_ARGS", ""))
        else:
            processed, failed = (sender or trapper_send)(items, server, port)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return False, f"{type(e).__name__}: {str(e)[:100]}"
    if failed or processed < len(items):
        return False, f"Zabbix took {processed} of {len(items)} values ({failed} refused: host or item missing, or the allowed-hosts macro)"
    return True, f"{processed} values"


# ---------------------------------------------------------------- fallback readiness

def load_master(path=None):
    try:
        return json.load(open(path or MASTER))
    except (OSError, ValueError):
        return {}


def master_stack(master, name):
    return (master.get("stacks") or {}).get(name) or {}


def local_set(master, name):
    """[(host, model)] of the "llm" services this stack may use (its gpu list, narrowed by gpu_only), from the master gateways list."""
    s = master_stack(master, name)
    only = s.get("gpu_only") if isinstance(s.get("gpu_only"), dict) else {}
    out = []
    for h in s.get("gpu") or []:
        host = (master.get("hosts") or {}).get(h) or {}
        if host.get("llm") and ("llm" in only.get(h, ["llm"])):
            out.append((h, host.get("llm_model", "local")))
    return out


def config_provider(text):
    """model.provider of a Hermes config.yaml (only that line is looked at), or None."""
    m = re.search(r"^model:[ \t]*\n((?:[ \t]+.*\n?|\n)*)", text or "", re.M)
    if not m:
        return None
    p = re.search(r"^[ \t]+provider:[ \t]*[\"']?([A-Za-z0-9_.-]+)", m.group(1), re.M)
    return p.group(1) if p else None


def default_config_reader(stack):
    """The stack's config.yaml (host side, else `docker cp`); only its model.provider line is ever looked at."""
    import early_alert as ea
    persist = stack.get("persist_dir") or os.path.join(AIBRIDGE, "stacks", stack["name"], "persist")
    try:
        raw = ea.read_small(os.path.join(persist, "config.yaml"), 262144)
    except PermissionError:
        brain = stack.get("brain") or ""
        raw = ea.cp_read(brain, "/root/.hermes/config.yaml", 262144) if brain else None
    except Exception:
        raw = None
    return raw.decode("utf-8", "replace") if raw else None


def fallback_plan(provider, state, now, stacks, master, config_reader=None):
    """What the outage of `provider` does to each stack and how to move it to the local LLM set. Reads only; nothing is switched."""
    label = LABEL.get(provider, provider)
    config_reader = config_reader or default_config_reader
    names = [s["name"] for s in stacks] or sorted({r[2] for r in state["recent"]})
    by_name = {s["name"]: s for s in stacks}
    rows = []
    for name in names:
        w = {p: window_stats(state["recent"], p, now, 86400, stack=name) for p in {r[1] for r in state["recent"] if r[2] == name}}
        mine = w.get(provider, {"calls": 0})
        others_ok = sorted(p for p, s in w.items() if p != provider and s["ok"])
        pin = None
        if name in by_name:
            try:
                pin = config_provider(config_reader(by_name[name]))
            except Exception:
                pin = None
        ms = master_stack(master, name)
        direct = ms.get("cloud_direct") is True
        local = local_set(master, name)
        if pin == provider:
            verdict, why = "FAILS", "pinned to this provider: it bypasses the router, no failover"
        elif mine["calls"] == 0:
            verdict, why = "no effect", "did not use it in 24 h"
        elif others_ok:
            verdict, why = "degraded", "the router falls to the next one (" + ", ".join(LABEL.get(o, o) for o in others_ok) + "), each call losing time until the cooldown"
        else:
            verdict, why = "FAILS", "this was the only provider that answered in 24 h"
        mode = "pinned" if pin == provider else ("cloud_direct" if direct else ("local-first" if local else "cloud-only"))
        rows.append({"stack": name, "verdict": verdict, "why": why, "mode": mode, "pin": pin, "calls24h": mine["calls"],
                     "ok24h": mine.get("ok", 0), "alternatives": others_ok, "local": [f"{h}:{m}" for h, m in local]})
    hosts = sorted({x.split(":")[0] for r in rows for x in r["local"]})
    return {"provider": provider, "label": label, "stacks": rows, "local_hosts": hosts,
            "steps": steps_for(provider, rows, hosts)}


def steps_for(provider, rows, hosts):
    """Operator steps as {title, where, commands}. Only for stacks that are hit and have a local set; the rest get a note."""
    hit = [r for r in rows if r["verdict"] == "FAILS"]       # a "degraded" stack still gets answers from another provider
    out = []
    movable = [r for r in hit if r["local"] and r["mode"] in ("cloud_direct", "pinned")]
    if movable or any(r["mode"] == "local-first" for r in hit):
        out.append({"title": "Start the local LLM on each GPU host (check it is not in use: VR, a game, Resolve)",
                    "where": "on each GPU host, from its copy of the repo",
                    "commands": [f"{h}: gpu-host/run_services.sh start llm   # then: curl -s http://<host>:<llm port>/health" for h in hosts]
                    or ["no host with an LLM in the master file: ops/gateways_host_service.py HOST llm PORT"]})
    direct = [r["stack"] for r in movable if r["mode"] == "cloud_direct"]
    if direct:
        out.append({"title": "Remove cloud_direct from the stacks that used only the cloud (the router tries the local model first again)",
                    "where": "on the Docker host, from ~/aibridge",
                    "commands": [f'edit ops/gateways.json: delete "cloud_direct": true from {s}' for s in direct]
                    + ["python3 ops/gateways_sync.py --check   # dry run: shows what changes, writes nothing",
                       "python3 ops/gateways_sync.py           # applies; restarts nothing"]})
    pinned = [r["stack"] for r in movable if r["mode"] == "pinned"]
    if pinned:
        out.append({"title": "Move the stacks pinned to the provider to the local-first router (with the stack asleep)",
                    "where": "on the Docker host, from ~/aibridge",
                    "commands": [c for s in pinned for c in (f"ops/switch_to_local_first.sh {s}", f"ops/recreate_hermes.sh {s}")]})
    stuck = [r["stack"] for r in hit if not r["local"]]
    if stuck:
        out.append({"title": "No local LLM assigned (nothing to do here until there is one): " + ", ".join(stuck),
                    "where": "on the Docker host, from ~/aibridge",
                    "commands": ['add the host with an LLM to the stack\'s "gpu" list in ops/gateways.json, and run: python3 ops/gateways_sync.py']})
    if out:
        out.append({"title": "When the provider is back: undo in reverse order (put cloud_direct back where it was; the local LLM stops by itself)",
                    "where": "", "commands": []})
    return out


def plan_text(plan, brief=False):
    lines = [f"Plan if {plan['label']} stays down (this changes nothing; nothing is switched automatically):"]
    hit = [r for r in plan["stacks"] if r["verdict"] != "no effect"]
    if not hit:
        lines.append("  No stack used it in the last 24 h: nothing to move.")
    for r in hit:
        loc = ("local LLM on " + ", ".join(r["local"])) if r["local"] else "no local LLM assigned"
        lines.append(f"  {r['stack']}: {r['verdict']}, {r['why']} ({r['calls24h']} calls in 24 h; {loc})")
    quiet = [r["stack"] for r in plan["stacks"] if r["verdict"] == "no effect"]
    if quiet:
        lines.append("  No effect: " + ", ".join(quiet))
    for i, s in enumerate(plan["steps"], 1):
        lines.append(f"{i}. {s['title']}" + (f" [{s['where']}]" if s["where"] and not brief else ""))
        if not brief:
            lines += ["     " + c for c in s["commands"]]
    lines.append(f"Details without changing anything: python3 ops/provider_uptime.py fallback --provider {plan['provider']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- the run

def fmt_dur(s):
    s = int(s)
    return f"{s // 3600} h {s % 3600 // 60} min" if s >= 3600 else f"{s // 60} min"


def alert_text(provider, new, reasons):
    head = {"down": "🔴 down", "degraded": "🟠 degraded"}[new]
    return f"{LABEL.get(provider, provider)} {head}: " + "; ".join(reasons or ["no detail"]) + "."


def run(conf, now, opener=open_probe, reader=default_reader, notify=None, stacks=None, master=None, sender=None, binary=None,
        do_probe=True, do_passive=True, state=None, config_reader=None, do_push=True):
    """One pass. Returns (state, report dict). `state` is mutated; the caller saves it unless it is a dry run."""
    state = state if state is not None else new_state()
    th = thresholds(conf)
    stacks = load_stacks() if stacks is None else stacks
    master = load_master() if master is None else master
    report = {"read": 0, "stacks_read": 0, "probed": 0, "transitions": [], "zabbix": None, "alerts": [], "net": None}
    if do_passive:
        for s in stacks:
            rows = read_rows(s, reader)
            if rows:
                report["stacks_read"] += 1
            report["read"] += ingest(state, s["name"], rows, now)
    probes = run_probes(state, conf, now, opener) if do_probe else {}
    report["probed"] = sum(len(v) for v in probes.values())
    if probes:
        ctl = probe_control(conf, opener)
        if ctl:
            state["net"].update(last=int(now), ok=ctl["ok"], ms=ctl["ms"])
        else:
            state["net"] = {}
    prune(state, now)
    state["runs"] += 1
    netdown = collector_net_down(state)
    if netdown != bool(state["net"].get("down")):
        state["net"].update(down=netdown, since=int(now))
        report["net"] = "down" if netdown else "up"
    seen = sorted({r[1] for r in state["recent"]} | set(state["probes"]) | set(state["prov"]))
    for p in seen:
        new, reasons = evaluate(p, state, now, th)
        if netdown and new == "down" and state["prov"].get(p, {}).get("state", "up") != "down":
            continue                        # the VM lost its network: withhold "down", no provider is judged on it
        t = advance(state, p, new, reasons, now)
        if t:
            report["transitions"].append((p, t[0], t[1], reasons))
    hosted = [p for p in (conf.get("ZBX_PROVIDERS", "").replace(" ", "").split(",") if conf.get("ZBX_PROVIDERS") else HOSTED) if p]
    items = [(zbx_host(p), k, v) for p in sorted(set(hosted) | set(seen)) if p in hosted for k, v in metrics(p, state, now, probes, quiet=netdown)]
    z = push(items, conf, sender, binary) if (items and do_push) else None
    report["zabbix"] = z
    owned = set(hosted) if (z and z[0]) else set()
    if notify is not None:
        route(state, report, notify, owned, z, now, stacks, master, config_reader)
    return state, report


def route(state, report, notify, owned, z, now, stacks, master, config_reader):
    """Messages. Zabbix owns the paging when it took the values (one route per condition); we add the plan once per outage.
    Without Zabbix, or when it refuses the values, the ops bot gets the alert itself, with the plan inside."""
    if z is not None and not z[0]:
        notify.alert(OUTBOX_KEY, f"Zabbix did not accept the provider metrics ({z[1]}). Provider alerts go through the ops bot until this is fixed.",
                     quiet=24 * 3600)
        report["alerts"].append("sender")
    elif z is not None:
        notify.resolve(OUTBOX_KEY, "Zabbix accepts the provider metrics again")
    if report.get("net") == "down":
        notify.alert(NET_KEY, "🌐 The VM has no internet access: the control probe and every probed provider fail at once. This is not a provider "
                     "outage; provider alerts and the pushes to Zabbix are suspended until the network is back.", quiet=0)
        report["alerts"].append("collector-net")
    elif report.get("net") == "up":
        notify.resolve(NET_KEY, "The VM has network again; provider alerts resume")
    for p, old, new, reasons in report["transitions"]:
        key = f"provider-uptime:{p}"
        zabbix_owns = p in owned
        if new == "up":
            # always resolve: it is a no-op unless we opened the alert (Zabbix may have refused the values at the time). notify.resolve
            # adds the duration itself.
            notify.resolve(key, f"{LABEL.get(p, p)} is answering again")
            continue
        plan = fallback_plan(p, state, now, stacks, master, config_reader) if new == "down" else None
        if not zabbix_owns:
            text = alert_text(p, new, reasons)
            if plan:
                text += "\n" + plan_text(plan, brief=True)
            notify.alert(key, text, quiet=0)
            report["alerts"].append(f"{p}:{new}")
            if plan:
                state["prov"][p]["plan_sent"] = True
        elif plan and not state["prov"][p].get("plan_sent"):
            notify.send(f"ℹ️ {alert_text(p, new, reasons)}\n" + plan_text(plan, brief=True))
            state["prov"][p]["plan_sent"] = True
            report["alerts"].append(f"{p}:plan")
    for p, d in state["probes"].items():
        refused = [slot for slot, s in d.items() if s.get("auth") is False]
        keyed = any(s.get("mode") in ("keyed", "chat") for s in d.values())
        if refused:
            notify.alert(f"provider-uptime:probe-key:{p}", f"The probe key of {LABEL.get(p, p)} was rejected ({refused[0]}); check PROBE_KEY in ops.env.",
                         quiet=24 * 3600)
        elif keyed:
            notify.resolve(f"provider-uptime:probe-key:{p}")


# ---------------------------------------------------------------- report, status

def month_bounds(month):
    y, m = (int(x) for x in month.split("-"))
    start = calendar.timegm((y, m, 1, 0, 0, 0))
    end = calendar.timegm((y + (m == 12), m % 12 + 1, 1, 0, 0, 0))
    return start, end


def previous_month(now):
    d = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    y, m = (d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1)
    return f"{y:04d}-{m:02d}"


def month_report(state, month, now):
    """Per provider for one month: uptime % (1 - down time / monitored time), probe success %, traffic availability %, calls, p50/p95 of
    the first byte (histogram bucket bounds), outages. Monitored time = hours that hold at least one probe or call."""
    lo, hi = month_bounds(month)
    prefix = month
    out = {}
    provs = sorted({p for h in state["hours"].values() for p in h} | {iv["p"] for iv in state["intervals"]})
    for p in provs:
        hours = [(k, h[p]) for k, h in state["hours"].items() if k.startswith(prefix) and p in h]
        monitored = len([1 for _, b in hours if b["probe"][0] or sum(b["calls"].values())]) * 3600
        calls = collections.Counter()
        hist = [0] * (len(BOUNDS) + 1)
        pn = po = 0
        for _, b in hours:
            calls.update(b["calls"])
            hist = [a + c for a, c in zip(hist, b["ttfb"])]
            pn += b["probe"][0]
            po += b["probe"][1]
        outs, down_s, deg_s = [], 0, 0
        for iv in state["intervals"]:
            if iv["p"] != p:
                continue
            s, e = max(iv["s"], lo), min(iv["e"] or now, hi)
            if e <= s:
                continue
            (outs if iv["k"] == "down" else []).append({"start": s, "minutes": round((e - s) / 60), "why": iv.get("why", "")})
            if iv["k"] == "down":
                down_s += e - s
            else:
                deg_s += e - s
        denom = calls["ok"] + sum(calls[k] for k in FAIL)
        n = sum(calls.values())
        out[p] = {"label": LABEL.get(p, p), "monitored_h": round(monitored / 3600, 1),
                  "uptime": round(100 * (1 - min(down_s, monitored) / monitored), 3) if monitored else None,
                  "down_min": round(down_s / 60), "degraded_min": round(deg_s / 60), "outages": outs,
                  "probe_success": round(100 * po / pn, 2) if pn else None, "probes": pn,
                  "traffic_avail": round(100 * calls["ok"] / denom, 2) if denom else None, "calls": n,
                  "r429": calls["429"], "timeouts": calls["timeout"], "r5xx": calls["5xx"], "auth": calls["auth"], "net": calls["net"],
                  "ttfb_p50": hist_percentile(hist, 50), "ttfb_p95": hist_percentile(hist, 95)}
    return {"month": month, "providers": out}


def json_safe(o):
    """json.dumps writes math.inf as the bare token Infinity, which is not JSON: the open top histogram bucket becomes ">64"."""
    if isinstance(o, float) and math.isinf(o):
        return f">{BOUNDS[-1]:g}"
    if isinstance(o, dict):
        return {k: json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    return o


def fmt_bound(v):
    return "-" if v is None else (">64 s" if v == math.inf else f"<={v:g} s")


def report_text(rep):
    lines = [f"Cloud provider availability, {rep['month']} (measured by us: real calls and probes)"]
    if not rep["providers"]:
        lines.append("  No data for that month.")
    for p, r in sorted(rep["providers"].items()):
        up = "no data" if r["uptime"] is None else f"{r['uptime']:.3f} %"
        lines.append(f"  {r['label']}: {up} up ({r['down_min']} min down, {r['degraded_min']} min degraded, {r['monitored_h']} h measured)")
        lines.append(f"      probes {r['probe_success'] if r['probe_success'] is not None else '-'} % de {r['probes']}; "
                     f"calls {r['traffic_avail'] if r['traffic_avail'] is not None else '-'} % de {r['calls']} "
                     f"(429: {r['r429']}, timeouts: {r['timeouts']}, 5xx: {r['r5xx']}, auth: {r['auth']}, network: {r['net']}); "
                     f"time to first byte p50 {fmt_bound(r['ttfb_p50'])}, p95 {fmt_bound(r['ttfb_p95'])}")
        for o in r["outages"][:5]:
            lines.append(f"      outage: {time.strftime('%d/%m %H:%M', time.gmtime(o['start']))} UTC, {o['minutes']} min. {o['why']}")
    return "\n".join(lines)


def status_table(state, now):
    rows = []
    for p in sorted(set(state["probes"]) | {r[1] for r in state["recent"]} | set(state["prov"])):
        pr = state["probes"].get(p, {})
        reach = pr.get("reach", {})
        row = {"provider": p, "state": state["prov"].get(p, {}).get("state", "up"), "reasons": state["prov"].get(p, {}).get("reasons", []),
               "probe": {k: reach.get(k) for k in ("ok", "ms", "code", "cls", "mode", "streak")},
               "last_ok": state["last_ok"].get(p)}
        for w, secs in WINDOWS:
            row[w] = window_stats(state["recent"], p, now, secs)
        rows.append(row)
    return rows


def status_text(rows, now):
    lines = []
    for r in rows:
        w = r["10m"]
        probe = r["probe"]
        lines.append(f"{r['provider']:<12} {r['state']:<9} probe {probe['cls'] or '-'} {probe['ms'] if probe['ms'] is not None else '-'} ms ({probe['mode'] or '-'})"
                     f"  10m: {w['calls']} calls, avail {w['avail'] if w['avail'] is not None else '-'} %, ttfb p95 {w['ttfb_p95'] if w['ttfb_p95'] is not None else '-'} s"
                     f"  24h: {r['24h']['calls']} calls, avail {r['24h']['avail'] if r['24h']['avail'] is not None else '-'} %"
                     f"  last ok {fmt_dur(now - r['last_ok']) + ' ago' if r['last_ok'] else '-'}")
        for why in r["reasons"]:
            lines.append(f"    {why}")
    return "\n".join(lines) or "no data yet"


# ---------------------------------------------------------------- the Zabbix template (generated: the file in git must equal this)

def _uuid(name):
    h = list(hashlib.sha256(("bridgeai-provider-uptime/" + name).encode()).hexdigest()[:32])
    h[12], h[16] = "4", "89ab"[int(h[16], 16) % 4]
    return "".join(h)


def _q(s):
    return "'" + str(s).replace("'", "''") + "'"


MACROS = (("{$PROV.PROBE.FAILS}", "3", "Probes in a row that must fail before the provider is down."),
          ("{$PROV.CHAT.FAILS}", "2", "Chat probes in a row that must fail (only providers with PROBE_CHAT_<PROVIDER> set)."),
          ("{$PROV.AVAIL.MIN}", "50", "Percent of real calls that must answer over 10 min, below this the provider is down (needs {$PROV.MIN.CALLS} calls)."),
          ("{$PROV.MIN.CALLS}", "5", "Calls in 10 min below which the real traffic says nothing."),
          ("{$PROV.TTFB.P95.MAX}", "15", "Seconds to the first byte, p95 over 10 min, above which the provider is degraded."),
          ("{$PROV.PROBE.MS.MAX}", "5000", "Milliseconds; the last 3 probes all slower than this make the provider degraded."),
          ("{$PROV.429.PCT}", "50", "Percent of calls answered 429 over 10 min that is a storm (needs {$PROV.MIN.CALLS.429} calls)."),
          ("{$PROV.MIN.CALLS.429}", "10", "Calls in 10 min below which a 429 share says nothing."),
          ("{$PROV.NODATA}", "20m", "How long the collector may stay silent before its own alert."),
          ("{$PROV.TRAPPER.HOSTS}", "127.0.0.1", "Allowed hosts of every trapper item: the Docker host's address (provision.py provider-hosts --sender-addr sets it per host)."))


def template_items():
    """[(name, key, value_type, units, description)]"""
    items = [("Collector heartbeat", "provider.heartbeat", "UNSIGNED", "unixtime", "Time of the last run of ops/provider_uptime.py; silence raises its own problem."),
             ("Provider state (0 up, 1 degraded, 2 down)", "provider.state", "UNSIGNED", "", "The collector's own verdict, same rules as the triggers; kept for graphs and for the monthly report."),
             ("Probe: front end answered (1 yes, 0 no)", "provider.probe.ok", "UNSIGNED", "", "Reach probe: GET <base>/models. Any HTTP answer below 500 is 1 (a 429 or a 401 is a live front end)."),
             ("Probe: milliseconds", "provider.probe.ms", "UNSIGNED", "ms", "Time of the reach probe."),
             ("Probe: HTTP code (0 = no answer)", "provider.probe.code", "UNSIGNED", "", "Status of the reach probe."),
             ("Chat probe: answered (1 yes, 0 no)", "provider.chat.ok", "UNSIGNED", "", "1-token chat, only where PROBE_CHAT_<PROVIDER> is set; sent at most every 15 min."),
             ("Chat probe: milliseconds", "provider.chat.ms", "UNSIGNED", "ms", "Time of the chat probe.")]
    for w, _ in WINDOWS:
        items += [(f"Real calls ({w})", f"provider.traffic.calls[{w}]", "UNSIGNED", "", "Cloud calls of every stack in the window (router evaluation logs, metadata only)."),
                  (f"Availability ({w})", f"provider.traffic.avail[{w}]", "FLOAT", "%", "ok / (ok + timeout + 5xx + net). 429 and auth are not held against the provider. -1 = no calls."),
                  (f"Success rate ({w})", f"provider.traffic.success[{w}]", "FLOAT", "%", "ok / every call, 429 and auth included. -1 = no calls."),
                  (f"Time to first byte p50 ({w})", f"provider.traffic.ttfb_p50[{w}]", "FLOAT", "s", "Of the calls that answered. -1 = none."),
                  (f"Time to first byte p95 ({w})", f"provider.traffic.ttfb_p95[{w}]", "FLOAT", "s", "Of the calls that answered. -1 = none.")]
        items += [(f"Calls with {c} ({w})", f"provider.traffic.errors[{w},{c}]", "UNSIGNED", "", f"Real calls of the window that ended as {c}.") for c in ERR_ITEMS]
        if w == "10m":
            items.append(("Failures look provider-wide (10m)", "provider.traffic.wide[10m]", "UNSIGNED", "",
                          "1 when the failed calls of the window span 2 or more models (or the only model seen failed on 2 or more stacks); 0 when one model fails among healthy ones. Only then does real traffic say the provider is down."))
    return items


def template_triggers():
    """[(name, expression, priority, tier, description, dependency name or None)]"""
    T = TEMPLATE_NAME
    k = lambda key: f"/{T}/{key}"
    down = (f'count({k("provider.probe.ok")},#{{$PROV.PROBE.FAILS}},"eq",0)>={{$PROV.PROBE.FAILS}}'
            f' or count({k("provider.chat.ok")},#{{$PROV.CHAT.FAILS}},"eq",0)>={{$PROV.CHAT.FAILS}}'
            f' or (last({k("provider.traffic.calls[10m]")})>={{$PROV.MIN.CALLS}} and last({k("provider.traffic.avail[10m]")})>=0'
            f' and last({k("provider.traffic.avail[10m]")})<{{$PROV.AVAIL.MIN}} and last({k("provider.traffic.wide[10m]")})=1)')
    # count() answers 0 when there is no data (min() would make the trigger Unknown on a host that is never probed, cloudflare, or before its first probe)
    deg = (f'count({k("provider.probe.ms")},#3,"gt",{{$PROV.PROBE.MS.MAX}})>=3'
           f' or (last({k("provider.traffic.calls[10m]")})>={{$PROV.MIN.CALLS}} and last({k("provider.traffic.ttfb_p95[10m]")})>{{$PROV.TTFB.P95.MAX}})'
           f' or (last({k("provider.traffic.calls[10m]")})>={{$PROV.MIN.CALLS.429}}'
           f' and last({k("provider.traffic.errors[10m,429]")})*100>={{$PROV.429.PCT}}*last({k("provider.traffic.calls[10m]")}))')
    stale = f'nodata({k("provider.heartbeat")},{{$PROV.NODATA}})=1'
    return [("Cloud provider down", down, "HIGH", "critical",
             "Real traffic or our probes say the provider does not answer. Zabbix pages; the ops bot adds which stacks are hit and the steps to move them to the local LLM set (ops/provider_uptime.py fallback).", None),
            ("Cloud provider degraded", deg, "AVERAGE", "normal",
             "Slow probes, slow first byte over 10 min, or a 429 storm. Not an outage: a 429 is also a person's own allowance running out.", ("Cloud provider down", down)),
            ("Provider uptime collector not reporting", stale, "AVERAGE", "normal",
             "Nothing arrived for this provider for {$PROV.NODATA}: the timer, the VM or the push is down. Without it no provider outage can be seen.", None)]


def build_template():
    T = TEMPLATE_NAME
    # a trigger belongs to an item in the 7.0 export format: attach each to the item its expression starts from
    anchors = collections.defaultdict(list)
    for tr in template_triggers():
        anchors[{"Cloud provider down": "provider.probe.ok", "Cloud provider degraded": "provider.probe.ms",
                 "Provider uptime collector not reporting": "provider.heartbeat"}[tr[0]]].append(tr)
    L = ["zabbix_export:", "  version: '7.0'", "  template_groups:", f"    - uuid: {_uuid('group')}", "      name: 'Templates/bridgeai'",
         "  templates:", f"    - uuid: {_uuid('template')}", f"      template: {_q(T)}", f"      name: {_q(T)}",
         "      description: |",
         "        Cloud model provider uptime as seen from our own VM: real calls of the stacks plus our own probes.",
         "        Trapper items, pushed every 5 minutes by ops/provider_uptime.py (built-in trapper protocol or zabbix_sender).",
         "        One host per provider, named provider-<name> (ops/zabbix/provision.py provider-hosts). Generated by",
         "        `python3 ops/provider_uptime.py template`: edit the generator, not this file.",
         "      groups:", "        - name: 'Templates/bridgeai'", "      items:"]
    for name, key, vt, units, desc in template_items():
        L += [f"        - uuid: {_uuid('item/' + key)}", f"          name: {_q(name)}", "          type: TRAP", f"          key: {_q(key)}",
              "          delay: '0'", "          history: 30d", "          trends: 365d", f"          value_type: {vt}"]
        if units:
            L.append(f"          units: {_q(units)}")
        L += [f"          description: {_q(desc)}", "          allowed_hosts: '{$PROV.TRAPPER.HOSTS}'", "          tags:", "            - tag: component",
              "              value: provider-uptime"]
        if anchors.get(key):
            L.append("          triggers:")
            for tname, expr, prio, tier, tdesc, dep in anchors[key]:
                L += [f"            - uuid: {_uuid('trigger/' + tname)}", f"              expression: {_q(expr)}", f"              name: {_q(tname)}",
                      f"              priority: {prio}", f"              description: {_q(tdesc)}", "              manual_close: 'YES'"]
                if dep:
                    L += ["              dependencies:", f"                - name: {_q(dep[0])}", f"                  expression: {_q(dep[1])}"]
                L += ["              tags:", "                - tag: tier", f"                  value: {tier}"]
    L += ["      tags:", "        - tag: service", "          value: llm", "      macros:"]
    for m, v, d in MACROS:
        L += [f"        - macro: {_q(m)}", f"          value: {_q(v)}", f"          description: {_q(d)}"]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- command line

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--jitter", type=float, default=0.0)
    r.add_argument("--no-probe", action="store_true")
    r.add_argument("--no-passive", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--month")
    rp.add_argument("--send", action="store_true")
    rp.add_argument("--json", action="store_true")
    f = sub.add_parser("fallback")
    f.add_argument("--provider", required=True)
    f.add_argument("--json", action="store_true")
    sub.add_parser("template")
    sub.add_parser("hosts")
    a = ap.parse_args(argv)
    now = time.time()
    if a.cmd == "template":
        sys.stdout.write(build_template())
        return 0
    if a.cmd == "hosts":
        for p in HOSTED:
            print(f"host {zbx_host(p)}  group bridgeai/{zbx_host(p)}  tags project:bridgeai unit:{zbx_host(p)}  template {TEMPLATE_NAME}")
        return 0
    if a.cmd == "run":
        conf = load_conf()
        if a.jitter > 0 and not a.dry_run:
            time.sleep(random.uniform(0, a.jitter))
            now = time.time()
        import notify
        with locked():
            state = load_state()
            state, rep = run(conf, now, notify=None if a.dry_run else notify, state=state, do_probe=not a.no_probe, do_passive=not a.no_passive,
                             do_push=not a.dry_run)
            if not a.dry_run:
                save_state(state)
        print(f"read {rep['read']} new calls from {rep['stacks_read']} stacks; {rep['probed']} probes; zabbix: "
              + ("not configured (or dry run)" if rep["zabbix"] is None else rep["zabbix"][1]) + "; alerts: " + (", ".join(rep["alerts"]) or "none"))
        print(status_text(status_table(state, now), now))
        for t in rep["transitions"]:
            print("transition:", t[0], t[1], "->", t[2], "; ".join(t[3]))
        return 0
    state = load_state()
    if a.cmd == "status":
        rows = status_table(state, now)
        print(json.dumps(rows, indent=1) if a.json else status_text(rows, now))
        if state["unmapped"] and not a.json:
            print("model names not mapped to a provider (first words, counts): " + json.dumps(state["unmapped"]))
        return 0
    if a.cmd == "report":
        rep = month_report(state, a.month or previous_month(now), now)
        txt = report_text(rep)
        print(json.dumps(json_safe(rep), indent=1) if a.json else txt)
        if a.send:
            import notify
            notify.send(txt[:3900])
        return 0
    plan = fallback_plan(a.provider, state, now, load_stacks(), load_master())
    print(json.dumps(plan, indent=1, ensure_ascii=False) if a.json else plan_text(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
