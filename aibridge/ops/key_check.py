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

Modes:
  key_check.py                      all stacks; notifies when a key turns bad, again every 24 h while it stays bad.
  key_check.py --wake --stack NAME  called by ops/wake/on_wake.d/10-key-check right after NAME wakes: notifies on EVERY
                                    wake while any key is bad (--chat = the Telegram chat that woke it).
Never prints or logs a key, only provider + last 4 characters. State: ~/.local/state/key_status.json.
Exit code 1 while any key is rejected, so `systemctl --user status key-check` turns red.

Why: 2026-10-09 the Groq key expired; voice notes silently stopped being transcribed and the agent claimed "no STT".
"""
import argparse, datetime as dt, io, json, os, re, subprocess, sys, tarfile, urllib.error, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import notify  # noqa: E402

HOME = os.path.expanduser("~/aibridge")
STATE = os.path.expanduser("~/.local/state/key_status.json")
REPEAT_S = 24 * 3600
LIMITED_S = 24 * 3600  # a key answering 429 this long is as useless as a dead one

# provider -> (label, free read-only GET that needs the key, what stops working)
PROVIDERS = {
    "groq": ("Groq (voz a texto)", "https://api.groq.com/openai/v1/models", "no se entienden las notas de voz"),
    "nvidia": ("NVIDIA NIM", "https://integrate.api.nvidia.com/v1/models", "el modelo principal no responde"),
    "gemini": ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/models", "falla el respaldo Gemini"),
    "huggingface": ("Hugging Face", "https://huggingface.co/api/whoami-v2", "falla el respaldo Hugging Face"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1/auth/key", "falla el respaldo OpenRouter"),
}
ENV_VARS = {"GROQ_API_KEY": "groq", "NVIDIA_API_KEY": "nvidia", "GEMINI_API_KEY": "gemini", "GOOGLE_API_KEY": "gemini",
            "HF_TOKEN": "huggingface", "OPENROUTER_API_KEY": "openrouter"}
BANNER_ID = "key-alert"


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
            add(ENV_VARS[var], val, "entorno del contenedor")
    raw = cp_out(stack["brain"], "/root/.hermes/auth.json")
    if raw:
        try:
            pool = json.loads(raw).get("credential_pool", {})
        except ValueError:
            pool = {}
        for prov, entries in pool.items():
            for e in entries if isinstance(entries, list) else []:
                add(prov, e.get("api_key") or e.get("access_token") or e.get("key"), "teclas guardadas: " + str(e.get("label") or e.get("id") or "?"))
    return [(p, k, w) for (p, k), w in found.items()]


def probe(prov, key):
    req = urllib.request.Request(PROVIDERS[prov][1], headers={"Authorization": f"Bearer {key}", "User-Agent": "bridgeai-key-check"})
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
    ips = container_ips(name) if name else []
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


def sync_banner(stack, bad_lines):
    """Add/refresh the key-alert banner when keys are bad, remove it when they are fine. Other banners are kept."""
    login = owui_login(stack, None)
    if not login:
        return False
    base, token = login
    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        cur = json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/v1/configs/banners", headers=hdr), timeout=15))
        keep = [b for b in cur if b.get("id") != BANNER_ID]
        if bad_lines:
            keep.append({"id": BANNER_ID, "type": "warning", "title": "⚠️ Hay claves que dejaron de funcionar",
                         "content": "\n".join(f"- {l}" for l in bad_lines) + "\n\nPegá una clave nueva en la página de claves (/keys/) o avisale al operador.",
                         "dismissible": False, "timestamp": int(now().timestamp())})
        if keep == [b for b in cur] and not bad_lines:
            return True
        urllib.request.urlopen(urllib.request.Request(base + "/api/v1/configs/banners", data=json.dumps({"banners": keep}).encode(),
                                                      headers=hdr, method="POST"), timeout=15).read()
        return True
    except Exception as e:
        print(f"[{stack['name']}] banner sync failed ({type(e).__name__})", flush=True)
        return False


# ---------------- main ----------------
def describe(prov, where, last4, detail):
    label, _, effect = PROVIDERS[prov]
    return f"{label} …{last4} ({'; '.join(sorted(set(where)))}): {detail}. Consecuencia: {effect}."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", help="only this stack")
    ap.add_argument("--wake", action="store_true", help="hook mode: notify on every wake while any key is bad")
    ap.add_argument("--chat", default="", help="telegram chat that woke the stack")
    ap.add_argument("--dry-run", action="store_true", help="probe and print, send nothing, keep no state")
    a = ap.parse_args()

    cfg = json.load(open(os.path.join(HOME, "ops", "wake", "stacks.json")))
    stacks = cfg["stacks"]
    try:
        state = json.load(open(STATE))
        if "stacks" not in state:
            state = {"stacks": {}}
    except (OSError, ValueError):
        state = {"stacks": {}}

    any_bad = False
    for stack in stacks:
        name = stack["name"]
        if a.stack and a.stack != name:
            continue
        old = state["stacks"].get(name, {})
        new, bad_lines, limited, tell = {}, [], [], False
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
                bad_lines.append(describe(prov, where, key[-4:], detail))
                last = dt.datetime.fromisoformat(ent["notified"]) if ent["notified"] else None
                if a.wake or last is None or prev.get("status") != "rejected" or (now() - last).total_seconds() > REPEAT_S:
                    tell = True
                    ent["notified"] = now().isoformat(timespec="seconds")
            if prev.get("status") != status:
                print(f"[{name}] {prov} …{key[-4:]}: {prev.get('status', '-')} -> {status} ({detail})", flush=True)
            new[kid] = ent
        if a.dry_run:
            print(f"[{name}] " + (" | ".join(bad_lines) if bad_lines else f"{len(new)} key(s) ok"))
            continue
        state["stacks"][name] = new
        sync_banner(stack, bad_lines)
        if bad_lines:
            notify.alert(f"keys:{name}", f"Claves caídas en {name}:\n" + "\n".join("• " + l for l in bad_lines))
        else:
            notify.resolve(f"keys:{name}", f"{name}: las claves volvieron a funcionar")
        if limited:
            notify.alert(f"keys-limited:{name}", f"Claves sin cupo hace más de un día en {name}:\n" + "\n".join("• " + l for l in limited))
        else:
            notify.resolve(f"keys-limited:{name}", f"{name}: las claves recuperaron cupo")
        if tell:
            text = f"⚠️ Claves caídas:\n" + "\n".join("• " + l for l in bad_lines) + "\nHasta que se renueven, eso no funciona. Podés pegar una nueva en la página de claves (/keys/)."
            own = telegram_target(stack)
            if own:
                tg_send(own, [a.chat] if (a.wake and a.chat) else own[2], text)
            else:
                print(f"[{name}] no telegram bot of its own; the web banner tells the person", flush=True)
    if not a.dry_run:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        tmp = STATE + ".tmp"
        json.dump(state, open(tmp, "w"), indent=1)
        os.replace(tmp, STATE)
    return 1 if any_bad else 0


if __name__ == "__main__":
    sys.exit(main())
