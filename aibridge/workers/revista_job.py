"""The pieces of the `revista` worker type (worker.py RevistaJob; WORKERS.md "The revista type"): the morning magazine of a person's
followed sources, written on the always-on machine so the Docker host that runs their bot stays asleep.

What the Hermes cron `revista` did in the stack (an agent turn: run `hub revista`, write the magazine from its output, deliver to
Telegram), done here in four steps without a Hermes:
  1. read_space(): the job's CURRENT prompt and schedule (persist/cron/jobs.json), the person's provider keys and the bot's token and
     allowed users (persist/.env, persist/auth.json's credential pool), read-only, by a small script (READER) run as root in a one-shot
     container with no network (`apply: docker`) or by this python3 (`apply: direct`);
  2. `hub revista` in a one-shot container of the stacks' image (worker.py: no keys, no network, /hub read-only);
  3. call_model(): one OpenAI-compatible chat request, the providers in the router's CLOUD order (router.py), the first with a key,
     the next on an error or a timeout, under a hard deadline;
  4. send_telegram(): sendMessage through the stack's own bot, via the Bot API server named in workers.json, to each allowed user,
     plain text in pieces of at most 4096 characters, link previews off.
Nothing here prints or logs a key, a token, a URL that carries one, the prompt or the answer: callers get counts and short codes.
Standard library only.
"""
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# The router's cloud chain, best first (router.py CLOUD: name, base URL, model, key variable). A copy, because the worker runs on a
# machine with only workers/ installed; worker_revista_selftest.py fails when the two drift apart.
CLOUD = [("NVIDIA nemotron-3.5-super", "https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3.5-super-vl-120b-a12b", "NVIDIA_API_KEY"),
         ("Token Harbor deepseek-v4.1-flash", "https://tokenharbor.ai/v1", "deepseek-v4.1-flash:free", "TOKENHARBOR_API_KEY"),
         ("NVIDIA gpt-oss-20b", "https://integrate.api.nvidia.com/v1", "openai/gpt-oss-20b", "NVIDIA_API_KEY"),
         ("Gemini flash-lite", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite", "GEMINI_API_KEY"),
         ("OpenRouter ling-3.2-flash", "https://openrouter.ai/api/v1", "inclusionai/ling-3.2-flash:free", "OPENROUTER_API_KEY")]
# router.py OPENROUTER_PROVIDER: sent on every OpenRouter request (zero-data-retention endpoints only, never a less private one)
OPENROUTER_PROVIDER = {"data_collection": "deny", "zdr": True, "require_parameters": True}
# Where a key may be written, by the variable the router asks for: the first name is the router's, the others are the same key under
# another name (ops/lib/providers.py PROVIDERS env lists; start_hermes.sh writes the Gemini key to .env as GOOGLE_API_KEY).
KEY_NAMES = {"NVIDIA_API_KEY": ["NVIDIA_API_KEY"], "TOKENHARBOR_API_KEY": ["TOKENHARBOR_API_KEY"],
             "GEMINI_API_KEY": ["GEMINI_API_KEY", "GOOGLE_API_KEY"], "OPENROUTER_API_KEY": ["OPENROUTER_API_KEY"], "HF_TOKEN": ["HF_TOKEN"]}
# router.py POOL_IDS / POOL_HOSTS: a key the person saved with `hermes auth add` (the keys page, ops/stack_keys.py) lives in auth.json's
# credential pool under the provider's id or "custom:<id>"; the pool wins over .env, as in the router
POOL_IDS = {"NVIDIA_API_KEY": "nvidia", "GEMINI_API_KEY": "gemini", "OPENROUTER_API_KEY": "openrouter", "HF_TOKEN": "huggingface"}
POOL_HOSTS = {"nvidia": "integrate.api.nvidia.com", "gemini": "generativelanguage.googleapis.com", "openrouter": "openrouter.ai",
              "huggingface": "router.huggingface.co"}
TG_VARS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS")   # start_hermes.sh writes both into ~/.hermes/.env (= persist/.env)
TG_LIMIT = 4096
SYSTEM = ("This is the scheduled run of the person's morning magazine (the cron job '{job}'), made on a machine without tools: the "
          "command `hub revista` was already run for you and its output is included in the message below. You cannot run commands. "
          "Follow the job's instructions with that output. Write only the final message: it is sent as it is, as plain text, to the "
          "person on Telegram.")
RUN_RE = re.compile(r"[^.\n]*`?hub revista`?(?: --[a-z]+)*[^.\n]*\.?")

# ---------------------------------------------------------------- 1. the person's space, read-only
# Runs as `python3 - PERSIST WORKDIR JOB [GATEWAYS] [STACK_ENV]` (inside a one-shot container: /p /w /g /s). Prints ONE JSON line. Only
# the job's fields, the known key variables and the bot's two variables leave it: nothing else of .env or auth.json is read out.
READER = r'''
import json, os, sys, urllib.parse
persist, workdir, job = sys.argv[1], sys.argv[2], sys.argv[3]
gw = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "-" else ""
senv = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != "-" else ""
KEY_NAMES, POOL_IDS, POOL_HOSTS, TG = json.loads(TABLES)
out = {"job": None, "jobs": 0, "moved": False, "keys": {}, "tg": {}, "gw": {}, "errors": []}
def env_file(path):
    d = {}
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.rstrip("\n")
            if line and not line.lstrip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return d
try:
    data = json.load(open(os.path.join(persist, "cron", "jobs.json"), encoding="utf-8"))
    jobs = data.get("jobs") if isinstance(data, dict) else data
    jobs = [j for j in jobs if isinstance(j, dict)] if isinstance(jobs, list) else []
    out["jobs"] = len(jobs)
    for j in jobs:
        if str(j.get("name") or "").strip().lower() == job.lower():
            sched = j.get("schedule") if isinstance(j.get("schedule"), dict) else {}
            paused = str(j.get("state") or "") == "paused" or bool(j.get("paused_at")) or not j.get("enabled", True)
            out["job"] = {"prompt": j.get("prompt") if isinstance(j.get("prompt"), str) else "", "expr": str(sched.get("expr") or ""),
                          "kind": str(sched.get("kind") or ""), "paused": paused}
            break
except (OSError, ValueError):
    out["errors"].append("jobs")
try:
    out["moved"] = job in open(os.path.join(workdir, ".worker-jobs"), encoding="utf-8").read().split()
except OSError:
    pass
env = env_file(os.path.join(persist, ".env"))
extra = env_file(senv) if senv else {}
pools = {}
try:
    pools = json.load(open(os.path.join(persist, "auth.json"))).get("credential_pool") or {}
except (OSError, ValueError, AttributeError):
    pass
def pool_key(pid):
    entries = []
    for pool_id in (pid, "custom:" + pid):
        pool = pools.get(pool_id, []) if isinstance(pools, dict) else []
        for e in pool if isinstance(pool, list) else []:
            if not isinstance(e, dict):
                continue
            host = urllib.parse.urlparse(str(e.get("base_url") or e.get("inference_base_url") or "")).hostname
            if pool_id != pid and host and host != POOL_HOSTS.get(pid):
                continue
            entries.append(e)
    for e in sorted(entries, key=lambda e: e.get("priority", 99) if isinstance(e.get("priority", 99), (int, float)) else 99):
        k = e.get("api_key") or e.get("access_token") or e.get("key")
        if k and e.get("auth_type", "api_key") in ("api_key", "api-key"):
            return str(k)
    return ""
for var, names in KEY_NAMES.items():
    k = pool_key(POOL_IDS[var]) if var in POOL_IDS else ""
    for src in (env, extra):
        for n in names:
            k = k or src.get(n, "")
    if k:
        out["keys"][var] = k
for v in TG:
    out["tg"][v] = env.get(v) or extra.get(v) or ""
if gw:
    try:
        g = json.load(open(gw))
        out["gw"] = {"cloud_order": [x for x in g.get("cloud_order") or [] if isinstance(x, str)][:20], "local_only": g.get("local_only") is True}
    except (OSError, ValueError, AttributeError):
        out["errors"].append("gateways")
print(json.dumps(out))
'''


def reader_script():
    """READER with its tables (the same ones this module uses) in front: fed on stdin to `python3 -`."""
    return (f"TABLES = {json.dumps([KEY_NAMES, POOL_IDS, POOL_HOSTS, list(TG_VARS)])!r}\n" + READER).encode()


def parse_reader(stdout):
    try:
        d = json.loads(stdout.strip().splitlines()[-1])
        return d if isinstance(d, dict) else None
    except (ValueError, IndexError, AttributeError):
        return None


# ---------------------------------------------------------------- 3. the model
def user_message(prompt, digest, rc=0):
    """The job's prompt with its "run `hub revista`" instruction replaced by a pointer to the output, which follows in full."""
    note = "(`hub revista` was already run for you: its output is below.)"
    body, n = RUN_RE.subn(note, prompt or "", count=1)
    if not n:
        body = note + "\n\n" + (prompt or "")
    tail = "\n\nHere is the output of `hub revista`" + (f" (it ended with exit code {rc})" if rc else "") + ":\n" + digest.rstrip() + "\n"
    return body.strip() + tail


def order(cloud_order=None):
    """Best first: the stack's cloud_order names (router.py cloud_order), then the rest of CLOUD."""
    by = {c[0]: c for c in CLOUD}
    first = [by[n] for n in dict.fromkeys(cloud_order or []) if n in by]
    return first + [c for c in CLOUD if c not in first]


def provider_id(base):
    host = re.sub(r"^https?://", "", base).split("/")[0].split(":")[0]
    for pid, h in (("nvidia", "nvidia.com"), ("tokenharbor", "tokenharbor.ai"), ("gemini", "googleapis.com"), ("openrouter", "openrouter.ai")):
        if host.endswith(h):
            return pid
    return "other"


THINK = re.compile(r"<think>.*?</think>", re.S)


def call_model(keys, system, user, deadline, per_call_s=180, cloud_order=None):
    """-> (text or None, info). Tries each provider of the order that has a key, until one answers with text or the deadline passes.
    info: provider (an id), tries, codes (one short code per try: 200, http_500, timeout, empty, ...), secs. Never raises."""
    info = {"provider": "", "tries": 0, "codes": [], "secs": 0.0}
    t0 = time.time()
    for name, base, model, var in order(cloud_order):
        key = keys.get(var)
        if not key:
            continue
        left = deadline - time.time()
        if left < 5:
            info["codes"].append("deadline")
            break
        body = {"model": model, "stream": False, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if "openrouter.ai" in base:
            body["provider"] = OPENROUTER_PROVIDER
        req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                                              "User-Agent": "bridgeai-worker"})
        info["tries"] += 1
        code = "error"
        try:
            with urllib.request.urlopen(req, timeout=max(1, min(per_call_s, left))) as r:
                d = json.load(r)
            msg = ((d.get("choices") or [{}])[0].get("message") or {}) if isinstance(d, dict) else {}
            text = msg.get("content") if isinstance(msg.get("content"), str) else ""
            text = THINK.sub("", text).strip()
            if text:
                info.update(provider=provider_id(base), secs=round(time.time() - t0, 1))
                info["codes"].append("200")
                return text, info
            code = "empty"
        except urllib.error.HTTPError as e:
            code = f"http_{e.code}"
        except (TimeoutError, OSError) as e:   # URLError is an OSError; a read timeout is a TimeoutError or socket.timeout
            code = "timeout" if "timed out" in str(getattr(e, "reason", e)) or isinstance(e, TimeoutError) else "net"
        except (ValueError, AttributeError, IndexError, TypeError):
            code = "bad_answer"
        info["codes"].append(code)
    info["secs"] = round(time.time() - t0, 1)
    return None, info


# ---------------------------------------------------------------- 4. Telegram
def u16(s):
    return len(s.encode("utf-16-le")) // 2


def split_text(text, limit=TG_LIMIT):
    """Pieces of at most `limit` UTF-16 units (how Telegram counts), cut at a blank line, else a line end, else a space, in the second
    half of the window; a hard cut only when there is none. "".join(pieces) == text."""
    out = []
    while u16(text) > limit:
        n = 0
        size = 0
        for ch in text:                          # the longest prefix that fits
            w = 2 if ord(ch) > 0xFFFF else 1
            if size + w > limit:
                break
            size += w
            n += 1
        cut = 0
        for sep in ("\n\n", "\n", " "):
            i = text.rfind(sep, 0, n)
            if i >= n // 2:
                cut = i + len(sep)
                break
        cut = cut or n
        out.append(text[:cut])
        text = text[cut:]
    if text:
        out.append(text)
    return out


SCHEDULED = {"es": "🕖 Programado · {label} {hm}", "ru": "🕖 По расписанию · {label} {hm}", "en": "🕖 Scheduled · {label} {hm}"}


def scheduled_header(label, hm, lang="es"):
    """The first line of anything a scheduled run sends (NOTICES.md): it was a schedule, not the bot answering in a chat."""
    return SCHEDULED.get(lang, SCHEDULED["es"]).format(label=label, hm=hm).strip() + "\n\n"


def send_telegram(base, token, chats, text, timeout=30):
    """sendMessage of each piece to each chat (plain text, no link previews). -> (sent, failed, pieces). A chat whose first piece
    fails is not sent the rest (no half magazine). Never prints the URL (it carries the token)."""
    pieces = [p for p in split_text(text) if p.strip()]
    sent = failed = 0
    url = f"{base.rstrip('/')}/bot{token}/sendMessage"
    for chat in chats:
        for p in pieces:
            body = {"chat_id": chat, "text": p.strip(), "link_preview_options": {"is_disabled": True}}
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    ok = json.load(r).get("ok") is True
            except Exception:
                ok = False
            if ok:
                sent += 1
            else:
                failed += 1
                break
    return sent, failed, len(pieces)


def chats_of(allowed):
    return [c.strip() for c in str(allowed or "").split(",") if re.match(r"^-?[0-9]{1,20}$", c.strip())]


def run_reader(cmd, timeout):
    """Run READER (cmd = a docker or python3 command reading the script on stdin). -> (dict or None, short code)."""
    try:
        r = subprocess.run(cmd, input=reader_script(), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except (OSError, subprocess.SubprocessError):
        return None, "docker"
    if r.returncode != 0:
        return None, f"rc_{r.returncode}"
    d = parse_reader(r.stdout.decode("utf-8", "replace"))
    return d, "ok" if d is not None else "bad_output"


if __name__ == "__main__":
    sys.exit("revista_job.py is a module of workers/worker.py (worker.py run revista)")
