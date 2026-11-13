#!/usr/bin/env python3
"""Silent key failures are deadly: tell the person (and the operator) WHICH key died, the moment it does.

For every stack in ops/wake/stacks.json it collects every key that stack can use (the operator keys in the Hermes
`.env` plus the ones a person saved from the keys page, `credential_pool` in auth.json), asks each provider a free,
read-only question, and reports the keys a provider REJECTS (401/403). Network errors and 429s are "unknown", never
"dead", so a flaky link does not page anybody.

How people hear about it:
  * Telegram: the stack's own bot tells its allowed users; the operator hears about every stack through the ops
    bot (ops/lib/notify.py), including when it is fixed. A key that answers 429 for more than a day is also reported.
  * Web: a warning banner in that stack's Open WebUI ("key-alert") that names the keys; removed when all are fine.
    Open WebUI sleeps with the stack, so the banner is (re)applied on every check where it is reachable.
    The banner is in the stack's language (es/ru/en, see stack_lang) and lists only the keys CHAT depends on (see
    chat_need) or the web voice uses: a dead backup or optional key stays out of it, so nobody reads a permanent red error,
    in a language they may not read, for something that changes nothing for them. The operator hears about every dead key
    through the ops bot either way.

Modes:
  key_check.py                      all stacks; notifies when a key turns bad, again every 24 h while it stays bad.
  key_check.py --wake --stack NAME  called by ops/wake/on_wake.d/10-key-check right after NAME wakes: notifies on EVERY
                                    wake while any key is bad (--chat = the Telegram chat that woke it).
Never prints or logs a key, only provider + last 4 characters. State: ~/.local/state/key_status.json.
Exit codes: 3 while any key is rejected (already reported by this script; key-check.service has SuccessExitStatus=3),
0 when all is fine, 1 when a stack's check crashed (the other stacks are still checked; the unit fails and ops-alert tells).

Why: the speech-to-text key saved inside Open WebUI died while the .env one was fine (the web call got a
401 and the agent claimed its key was empty). Another time the Groq key expired; voice notes silently stopped being transcribed and the agent claimed "no STT".
"""
import argparse, datetime as dt, fcntl, io, json, os, re, subprocess, sys, tarfile, traceback, urllib.error, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import notify  # noqa: E402
import providers  # noqa: E402

HOME = os.path.expanduser("~/aibridge")
STATE = os.path.expanduser("~/.local/state/key_status.json")
STATE_LOCK = STATE + ".lock"
REPEAT_S = 24 * 3600
EXIT_REJECTED = 3     # a key is rejected and this script already told the operator (SuccessExitStatus in key-check.service)
LIMITED_S = 24 * 3600  # a key answering 429 this long is as useless as a dead one

PROVIDERS = providers.PROVIDERS   # label, base, key env vars, what stops working (ops/lib/providers.py)
ENV_VARS = providers.ENV_VARS
BANNER_ID = "key-alert"

# ---- the person's language (banner and Telegram text). The operator's ops-bot text stays Spanish. ----
LANGS = ("es", "ru", "en")
POOL_WHERE = "teclas guardadas: "       # `where` of a key saved from the keys page / hermes auth (+ its label)
ENV_WHERE = "entorno del contenedor"
WEB_WHERE = "voz de la web (Open WebUI)"
TEXT = {
    "es": {"title": "⚠️ Hay claves que dejaron de funcionar",
           "ask": "Pegá una clave nueva en la página de claves (/keys/) o avisale al operador.",
           "tg_head": "⚠️ Claves caídas:", "tg_tail": "Hasta que se renueven, eso no funciona. Podés pegar una nueva en la página de claves (/keys/).",
           "effect": "Consecuencia", POOL_WHERE: POOL_WHERE, ENV_WHERE: ENV_WHERE, WEB_WHERE: WEB_WHERE},
    "ru": {"title": "⚠️ Часть ключей перестала работать",
           "ask": "Вставьте новый ключ на странице ключей (/keys/) или сообщите оператору.",
           "tg_head": "⚠️ Ключи перестали работать:", "tg_tail": "Пока ключ не заменят, это не работает. Новый ключ можно вставить на странице ключей (/keys/).",
           "effect": "Последствие", POOL_WHERE: "сохранённые ключи: ", ENV_WHERE: "окружение контейнера", WEB_WHERE: "голос в веб-интерфейсе (Open WebUI)"},
    "en": {"title": "⚠️ Some keys stopped working",
           "ask": "Paste a new key on the keys page (/keys/) or tell the operator.",
           "tg_head": "⚠️ Keys that stopped working:", "tg_tail": "Until they are renewed, that does not work. You can paste a new one on the keys page (/keys/).",
           "effect": "Effect", POOL_WHERE: "saved keys: ", ENV_WHERE: "container environment", WEB_WHERE: "web voice (Open WebUI)"},
}
# What stops working, per provider and language (es lives in providers.PROVIDERS, the operator's language).
EFFECT = {
    "ru": {"nvidia": "основная модель не отвечает", "gemini": "не работает резервная модель Gemini",
           "huggingface": "не работает резервная модель Hugging Face", "openrouter": "не работает резервная модель OpenRouter",
           "tokenharbor": "не работает резервная модель Token Harbor", "groq": "не распознаются голосовые сообщения"},
    "en": {"nvidia": "the main model does not answer", "gemini": "the Gemini backup fails",
           "huggingface": "the Hugging Face backup fails", "openrouter": "the OpenRouter backup fails",
           "tokenharbor": "the Token Harbor backup fails", "groq": "voice notes are not understood"},
}


def now():
    return dt.datetime.now(dt.timezone.utc)


def sh(*args, timeout=30):
    return subprocess.run(args, capture_output=True, timeout=timeout)


def parse_env(text):
    env = {}
    for line in text.splitlines():
        k, sep, v = line.partition("=")
        if sep and not k.lstrip().startswith("#"):
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def cp_out(container, path):
    """File from a container (running or not) as bytes, or None. Root-owned 0600 files are fine through docker cp."""
    r = sh("docker", "cp", f"{container}:{path}", "-")
    if r.returncode != 0:
        return None
    try:
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
            m = t.next()
            return t.extractfile(m).read() if m else None
    except (tarfile.TarError, AttributeError):
        return None


def container_ips(name):
    r = sh("docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", name)
    return r.stdout.decode().split() if r.returncode == 0 else []


# Open WebUI keeps its own copy of the speech-to-text key in webui.db, and that copy beats the .env one:
# the copy was dead (401) while the .env key was fine, so the web call failed and nothing here noticed. Prints JSON.
OWUI_STT_READER = """
import json, sqlite3
d = sqlite3.connect("file:/app/backend/data/webui.db?mode=ro", uri=True)
q = lambda k: (lambda r: json.loads(r[0]) if r else "")(d.execute("select value from config where key=?", (k,)).fetchone())
print(json.dumps({"base": q("audio.stt.openai.api_base_url"), "key": q("audio.stt.openai.api_key"), "engine": q("audio.stt.engine")}))
"""


def owui_stt_key(stack):
    """(provider, key) of the speech-to-text key saved inside the stack's running Open WebUI, else None."""
    name = (stack.get("web") or [None])[0]
    if not name:
        return None
    try:
        r = sh("docker", "exec", name, "python3", "-c", OWUI_STT_READER)   # fails fast when the stack sleeps
        cfg = json.loads(r.stdout) if r.returncode == 0 else {}
    except (ValueError, subprocess.TimeoutExpired):
        return None
    if cfg.get("engine") != "openai" or not cfg.get("key"):
        return None
    for prov, d in PROVIDERS.items():
        if str(cfg.get("base", "")).rstrip("/") == d["base"]:
            return prov, cfg["key"]
    return None


def collect(stack):
    """[(provider, key, where)] for one stack, deduplicated by (provider, key)."""
    found = {}

    def add(prov, key, where):
        if key and prov in PROVIDERS:
            found.setdefault((prov, key), []).append(where)

    raw = cp_out(stack["brain"], "/root/.hermes/.env")
    for var, val in parse_env(raw.decode("utf-8", "replace")).items() if raw else []:
        if var in ENV_VARS:
            add(ENV_VARS[var], val, var)
    # keys that only live in the container environment (compose) are used by Hermes too
    r = sh("docker", "inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", stack["brain"])
    for var, val in parse_env(r.stdout.decode("utf-8", "replace")).items() if r.returncode == 0 else []:
        if var in ENV_VARS:
            add(ENV_VARS[var], val, ENV_WHERE)
    raw = cp_out(stack["brain"], "/root/.hermes/auth.json")
    if raw:
        try:
            pool = json.loads(raw).get("credential_pool", {})
        except ValueError:
            pool = {}
        for prov, entries in pool.items():
            for e in entries if isinstance(entries, list) else []:
                add(prov, e.get("api_key") or e.get("access_token") or e.get("key"), POOL_WHERE + str(e.get("label") or e.get("id") or "?"))
    stt = owui_stt_key(stack)
    if stt:
        add(stt[0], stt[1], WEB_WHERE)
    return [(p, k, w) for (p, k), w in found.items()]


def probe(prov, key):
    req = providers.key_check_request(prov, key)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return "ok", str(r.status)
    except urllib.error.HTTPError as e:
        code, body = "", e.read(600).decode("utf-8", "replace")
        try:
            code = json.loads(body).get("error", {}).get("code", "") or ""
        except (ValueError, AttributeError):
            pass
        # Gemini answers a bad key with 400 API_KEY_INVALID, not 401
        if e.code in (401, 403) or (e.code == 400 and "API_KEY_INVALID" in body):
            return "rejected", f"HTTP {e.code}" + (f" {code}" if isinstance(code, str) and code else "")
        if e.code == 429:
            return "limited", "HTTP 429"
        return "unknown", f"HTTP {e.code}"
    except Exception as e:  # link down, DNS, timeout: not the key's fault
        return "unknown", type(e).__name__


def stack_lang(stack):
    """es, ru or en: the language of the person who uses the stack, found the way the other scripts do. In order: their own
    /idioma pick (/workdir/.prefs.json, "auto" does not count), the stack's gateways.json "lang", STT_LANG of its .env (the
    one-language voice setting of ops/stack_voice.sh), "lang" in wake/stacks.json; else es."""
    name = stack["name"]
    cands = []
    raw = cp_out(stack["brain"], "/workdir/.prefs.json")
    try:
        cands.append(json.loads(raw).get("lang") if raw else None)
    except (ValueError, AttributeError):
        pass
    gw = os.path.join(HOME, "gateways-hernik" if name == "hernik" else os.path.join("stacks", name, "gateways"), "gateways.json")
    try:
        cands.append(json.load(open(gw)).get("lang"))
    except (OSError, ValueError, AttributeError):
        pass
    try:
        envf = os.path.join(HOME, ".env") if name == "hernik" else os.path.join(HOME, "stacks", name, ".env")
        cands.append(parse_env(open(envf).read()).get("STT_LANG"))
    except OSError:
        pass
    cands.append(stack.get("lang"))
    return next((c for c in cands if c in LANGS), "es")


# Providers the router's cloud chain calls for chat (router.py CLOUD / CANDIDATES); any of them can carry a turn.
ROUTER_CHAT = frozenset({"nvidia", "tokenharbor", "gemini"})


def chat_need(config_text):
    """What chat depends on, from the stack's Hermes config.yaml: ("primary", {provider}) when Hermes calls that provider itself
    (a person's own key activated with ops/stack_keys.py), ("router", ROUTER_CHAT) when it goes through the router
    (`model.provider custom`: every router stack, local-first or cloud_direct), None when it cannot be told."""
    m = re.search(r"^model:[ \t]*\n((?:[ \t]+.*\n|[ \t]*\n)+)", (config_text or "") + "\n", re.M)
    prov = re.search(r'^[ \t]+provider:\s*"?([^"\n#\s]+)', m.group(1), re.M) if m else None
    if not prov:
        return None
    if prov.group(1) in PROVIDERS and prov.group(1) != "groq":
        return "primary", {prov.group(1)}
    return "router", ROUTER_CHAT


def chat_critical(prov, need, statuses):
    """Does a rejected key of `prov` break chat? statuses = {(provider, key id): status} of the stack's keys. It does only when no
    other key of what chat needs is left: the primary provider's last good key, or, behind the router, every key of the
    router's providers. None (unknown) = yes, the old behaviour. A provider chat never calls (Groq for voice notes,
    OpenRouter behind the router, an unused backup) never is."""
    if need is None:
        return True
    kind, chat = need
    if prov not in chat:
        return False
    pool = chat if kind == "router" else {prov}
    return not [k for k, st in statuses.items() if k[0] in pool and st != "rejected"]


# ---------------- telegram ----------------
def telegram_target(stack):
    """(token, bot-api url, [chat ids]) of a stack that has its own bot, else None."""
    envf = stack.get("telegram_env")
    api = stack.get("telegram_api")
    if not (envf and api):
        return None
    env = parse_env(open(envf).read())
    ips = container_ips(api)
    if not (env.get("TELEGRAM_BOT_TOKEN") and ips):
        return None
    users = [u.strip() for u in env.get("TELEGRAM_ALLOWED_USERS", "").split(",") if u.strip()]
    return env["TELEGRAM_BOT_TOKEN"], f"http://{ips[0]}:{stack.get('telegram_api_port', 8081)}", users


def tg_send(target, chats, text):
    token, base, _ = target
    ok = False
    for chat in chats:
        req = urllib.request.Request(f"{base}/bot{token}/sendMessage", data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=15).read()
            ok = True
        except Exception as e:  # never log the URL: it carries the bot token
            print(f"telegram send failed: {type(e).__name__}", flush=True)
    return ok


# ---------------- open webui banner ----------------
def owui_login(stack, cfg_dir):
    """(base url, bearer token) of the stack's Open WebUI when it is running, else None."""
    name = (stack.get("web") or [None])[0]
    running = name and sh("docker", "inspect", "-f", "{{.State.Running}}", name).stdout.decode().strip() == "true"
    ips = container_ips(name) if running else []   # a stopped container still reports its old IP
    if not ips:
        return None
    email, pw = "admin@aibridge.local", None
    cred = os.path.join(HOME, "stacks", stack["name"], "credentials.txt")
    if os.path.exists(cred):
        m = re.search(r"login:\s+(\S+)\s+password:\s+(\S+)", open(cred).read())
        if m:
            email, pw = m.group(1), m.group(2)
    elif os.path.exists(os.path.join(HOME, ".env")):
        pw = parse_env(open(os.path.join(HOME, ".env")).read()).get("OPENWEBUI_ADMIN_PASSWORD")
    if not pw:
        return None
    base = f"http://{ips[0]}:8080"
    try:
        req = urllib.request.Request(base + "/api/v1/auths/signin", data=json.dumps({"email": email, "password": pw}).encode(),
                                     headers={"Content-Type": "application/json"})
        return base, json.load(urllib.request.urlopen(req, timeout=15))["token"]
    except Exception as e:
        print(f"[{stack['name']}] banner: login failed ({type(e).__name__})", flush=True)
        return None


def sync_banner(stack, bad_lines, lang="es"):
    """Add/refresh the key-alert banner (in the person's language) when keys chat needs are bad, remove it when they are
    fine. Other banners are kept."""
    login = owui_login(stack, None)
    if not login:
        return False
    base, token = login
    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        cur = json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/v1/configs/banners", headers=hdr), timeout=15))
        keep = [b for b in cur if b.get("id") != BANNER_ID]
        if bad_lines:
            keep.append({"id": BANNER_ID, "type": "warning", "title": TEXT[lang]["title"],
                         "content": "\n".join(f"- {l}" for l in bad_lines) + "\n\n" + TEXT[lang]["ask"],
                         "dismissible": False, "timestamp": int(now().timestamp())})
        if keep == [b for b in cur] and not bad_lines:
            return True
        urllib.request.urlopen(urllib.request.Request(base + "/api/v1/configs/banners", data=json.dumps({"banners": keep}).encode(),
                                                      headers=hdr, method="POST"), timeout=15).read()
        return True
    except Exception as e:
        print(f"[{stack['name']}] banner sync failed ({type(e).__name__})", flush=True)
        return False


def merge_banner(cur, banner_id, banner):
    """The banner list with the one `banner_id` replaced by `banner` (a dict) or removed (None); every other banner is kept."""
    return [b for b in cur if b.get("id") != banner_id] + ([banner] if banner else [])


def sync_info_banner(stack, banner_id, text):
    """Set (text) or remove (None) one dismissible info banner in ONE stack's Open WebUI, the way key-alert is: used by the waker's
    inactivity note for a web-only stack (ops/wake/waker.py). Other banners are kept. False when Open WebUI is not reachable."""
    login = owui_login(stack, None)
    if not login:
        return False
    base, token = login
    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        cur = json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/v1/configs/banners", headers=hdr), timeout=15))
        banner = None if text is None else {"id": banner_id, "type": "info", "title": "", "content": text, "dismissible": True,
                                            "timestamp": int(now().timestamp())}
        keep = merge_banner(cur, banner_id, banner)
        if banner is None and keep == cur:
            return True
        urllib.request.urlopen(urllib.request.Request(base + "/api/v1/configs/banners", data=json.dumps({"banners": keep}).encode(),
                                                      headers=hdr, method="POST"), timeout=15).read()
        return True
    except Exception as e:
        print(f"[{stack['name']}] banner sync failed ({type(e).__name__})", flush=True)
        return False


# ---------------- main ----------------
def load_state():
    try:
        state = json.load(open(STATE))
        if "stacks" in state:
            return state
    except (OSError, ValueError):
        pass
    return {"stacks": {}}


def save_stack(name, new):
    """Merge one stack's result into key_status.json under a lock: the 30-min timer and the wake hook both do this."""
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE_LOCK, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state()
        state["stacks"][name] = new
        tmp = f"{STATE}.{os.getpid()}.tmp"
        json.dump(state, open(tmp, "w"), indent=1)
        os.replace(tmp, STATE)


def where_text(w, lang):
    t = TEXT[lang]
    return t[POOL_WHERE] + w[len(POOL_WHERE):] if w.startswith(POOL_WHERE) else t.get(w, w)


def describe(prov, where, last4, detail, lang="es"):
    label = PROVIDERS[prov]["label"]
    effect = PROVIDERS[prov]["effect"] if lang == "es" else EFFECT[lang][prov]
    return f"{label} …{last4} ({'; '.join(sorted({where_text(w, lang) for w in where}))}): {detail}. {TEXT[lang]['effect']}: {effect}."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", help="only this stack")
    ap.add_argument("--wake", action="store_true", help="hook mode: notify on every wake while any key is bad")
    ap.add_argument("--chat", default="", help="telegram chat that woke the stack")
    ap.add_argument("--dry-run", action="store_true", help="probe and print, send nothing, keep no state")
    ap.add_argument("--banner", choices=("set", "off"), help="with --stack: set or remove one info banner in that stack's Open WebUI "
                    "(no key is probed); used by the waker's inactivity note")
    ap.add_argument("--banner-id", default="idle-notice", help="id of the --banner banner")
    ap.add_argument("--banner-text", default="", help="text of the --banner set banner")
    a = ap.parse_args()

    cfg = json.load(open(os.path.join(HOME, "ops", "wake", "stacks.json")))
    stacks = cfg["stacks"]
    if a.banner:
        stack = next((st for st in stacks if st["name"] == a.stack), None)
        if not stack or (a.banner == "set" and not a.banner_text.strip()) or a.banner_id == BANNER_ID:
            print("--banner needs --stack NAME of a known stack, --banner-text for set, and an id other than key-alert", file=sys.stderr)
            return 2
        return 0 if sync_info_banner(stack, a.banner_id, a.banner_text if a.banner == "set" else None) else 1
    state = load_state()
    any_bad = crashed = False
    for stack in stacks:
        name = stack["name"]
        if a.stack and a.stack != name:
            continue
        try:
            any_bad |= check_stack(stack, state["stacks"].get(name, {}), a)
        except Exception:   # one broken stack must not hide the keys of the others
            crashed = True
            print(f"[{name}] check crashed:\n" + traceback.format_exc(), file=sys.stderr, flush=True)
    return 1 if crashed else (EXIT_REJECTED if any_bad else 0)


def check_stack(stack, old, a):
    """Probe every key of one stack, notify, store its state. True while any of its keys is rejected."""
    name = stack["name"]
    any_bad = False
    new, rejected, limited, tell = {}, [], [], False
    for prov, key, where in collect(stack):
        kid = f"{prov}:{key[-4:]}"
        status, detail = probe(prov, key)
        prev = old.get(kid, {})
        if status == "unknown":  # keep what we knew
            status = prev.get("status", "unknown")
        since = prev.get("since") if prev.get("status") == status else now().isoformat(timespec="seconds")
        ent = {"status": status, "since": since, "detail": detail, "notified": prev.get("notified")}
        if status == "limited" and (now() - dt.datetime.fromisoformat(since)).total_seconds() > LIMITED_S:
            limited.append(describe(prov, where, key[-4:], f"responde 429 desde {since[:16]}"))
        if status == "rejected":
            any_bad = True
            rejected.append((kid, prov, where, key[-4:], detail))
            last = dt.datetime.fromisoformat(ent["notified"]) if ent["notified"] else None
            if a.wake or last is None or prev.get("status") != "rejected" or (now() - last).total_seconds() > REPEAT_S:
                tell = True
                ent["notified"] = now().isoformat(timespec="seconds")
        if prev.get("status") != status:
            print(f"[{name}] {prov} …{key[-4:]}: {prev.get('status', '-')} -> {status} ({detail})", flush=True)
        new[kid] = ent
    # Which rejected keys break chat (they go in the person's banner) and which are a backup or an optional one (the ops bot
    # only). The language and the config are read only when something is rejected: both cost a docker cp.
    crit, lang = {}, "es"
    if rejected:
        raw = cp_out(stack["brain"], "/root/.hermes/config.yaml")
        need = chat_need(raw.decode("utf-8", "replace") if raw else None)
        statuses = {(k.split(":")[0], k): e["status"] for k, e in new.items()}
        # A key Open WebUI's own voice setting uses is not a backup: on a web-only stack the mic stops working with it.
        crit = {kid: chat_critical(prov, need, statuses) or WEB_WHERE in where for kid, prov, where, *_ in rejected}
        lang = stack_lang(stack)
    ops_lines = {kid: describe(prov, where, last4, detail) + ("" if crit[kid] else " (no es la del chat: la persona no ve aviso en la web)")
                 for kid, prov, where, last4, detail in rejected}
    if a.dry_run:
        print(f"[{name}] " + (" | ".join(ops_lines.values()) if ops_lines else f"{len(new)} key(s) ok"))
        return any_bad
    save_stack(name, new)
    person_lines = [describe(prov, where, last4, detail, lang) for kid, prov, where, last4, detail in rejected]
    sync_banner(stack, [l for (kid, *_), l in zip(rejected, person_lines) if crit[kid]], lang)
    # One ops alert per (stack, provider, last 4): a second key dying later is announced when it dies, not hours later.
    for kid, line in ops_lines.items():
        notify.alert(f"keys:{name}:{kid}", f"Clave caída en {name}:\n• {line}")
    for ak in notify.active(f"keys:{name}:"):
        if ak.split(":", 2)[2] not in ops_lines:
            notify.resolve(ak, f"{name}: una clave volvió a funcionar o se quitó ({ak.split(':', 2)[2].replace(':', ' …')})")
    notify.resolve(f"keys:{name}", f"{name}: los avisos de claves caídas pasaron a ser uno por clave")   # the old per-class key
    if limited:
        notify.alert(f"keys-limited:{name}", f"Claves sin cupo hace más de un día en {name}:\n" + "\n".join("• " + l for l in limited))
    else:
        notify.resolve(f"keys-limited:{name}", f"{name}: las claves recuperaron cupo")
    if tell:
        text = TEXT[lang]["tg_head"] + "\n" + "\n".join("• " + l for l in person_lines) + "\n" + TEXT[lang]["tg_tail"]
        own = telegram_target(stack)
        if own:
            tg_send(own, [a.chat] if (a.wake and a.chat) else own[2], text)
        else:
            print(f"[{name}] no telegram bot of its own; the web banner tells the person when chat depends on the key", flush=True)
    return any_bad


if __name__ == "__main__":
    sys.exit(main())
