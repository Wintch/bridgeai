#!/usr/bin/env python3
"""Keys page for a per-person Hermes stack: paste an LLM API key, have it VALIDATED against the provider, stored the
official way (`hermes auth add`), and pick the model Hermes will use from then on. Needs no LLM, which is the point: a
new person has no key yet, so Hermes itself cannot help them enter one.

Runs inside the Hermes container (HERMES_KEYS_UI=1, see start_hermes.sh), port 8700, stdlib only. The `web` nginx
container proxies /keys/ here behind the Open WebUI login (auth_request); on top of that this server asks Open WebUI
who the caller is (forwarding the session cookie) and only lets ADMINS through, so a second Open WebUI account can't
touch the keys. State-changing calls also need an `X-Keys: 1` header (a cross-site form post can't set it).

Nothing here ever logs or returns a key: only the last 4 characters. A key is stored only after BOTH the key check and
a one-token test call to the chosen model succeed.
"""
import json
import os
import re
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("KEYS_PORT", "8700"))
OWUI = os.environ.get("OWUI_URL", "http://open-webui:8080").rstrip("/")
HERMES_HOME = os.path.expanduser("~/.hermes")
STATUS_FILE = os.path.join("/workdir", ".keys-status.json")  # no secrets: provider -> {ok, at, last4}

PROVIDERS = {
    "nvidia": {
        "label": "NVIDIA NIM", "note": "Gratis, sin tarjeta (≈40 pedidos por minuto). La recomendada para empezar.",
        "link": "https://build.nvidia.com/settings/api-keys", "base": "https://integrate.api.nvidia.com/v1",
        "default": "nvidia/nemotron-3-super-120b-a12b", "hint": "empieza con nvapi-"},
    "openrouter": {
        "label": "OpenRouter", "note": "Tiene modelos gratuitos (terminan en :free) con límite diario.",
        "link": "https://openrouter.ai/settings/keys", "base": "https://openrouter.ai/api/v1",
        "default": None, "hint": "empieza con sk-or-"},
    "gemini": {
        "label": "Google Gemini", "note": "Gratis con cupo diario bajo; alcanza para probar.",
        "link": "https://aistudio.google.com/apikey", "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default": None, "hint": "empieza con AIza"},
    "huggingface": {
        "label": "Hugging Face", "note": "Créditos mensuales gratuitos de inferencia.",
        "link": "https://huggingface.co/settings/tokens", "base": "https://router.huggingface.co/v1",
        "default": None, "hint": "empieza con hf_"},
}

_lock = threading.Lock()


# ---------- helpers ----------
def http_json(url, key=None, body=None, timeout=20):
    headers = {"Content-Type": "application/json", "User-Agent": "hermes-keys/1"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:  # network, DNS, timeout
        return 0, {"error": str(e)[:200]}


def list_models(pid, key):
    st, d = http_json(PROVIDERS[pid]["base"] + "/models", key)
    if st != 200:
        return st, []
    ids = [m.get("id", "") for m in (d.get("data") or [])]
    ids = [i.split("models/", 1)[-1] if pid == "gemini" else i for i in ids if i]
    return st, sorted(set(ids))


def pick_default(pid, models):
    p = PROVIDERS[pid]["default"]
    if p and p in models:
        return p
    if pid == "openrouter":
        free = [m for m in models if m.endswith(":free")]
        if free:
            return free[0]
    if pid == "gemini":
        flash = [m for m in models if "flash" in m and "image" not in m and "tts" not in m]
        if flash:
            return flash[0]
    return models[0] if models else None


def chat_test(pid, key, model, timeout=60):
    """One-token completion: proves this key can actually run this model. Returns (ok, http_status, reason).
    This, not the model listing, is what validates a key: several providers (NVIDIA, OpenRouter...) serve /models
    publicly, so a garbage key still gets a 200 there."""
    st, d = http_json(PROVIDERS[pid]["base"] + "/chat/completions", key,
                      {"model": model, "messages": [{"role": "user", "content": "Responde solo: ok"}], "max_tokens": 8}, timeout=timeout)
    if st == 200 and d.get("choices"):
        return True, st, ""
    msg = (d.get("error") or {}) if isinstance(d.get("error"), dict) else {"message": d.get("error") or d.get("detail") or ""}
    return False, st, str(msg.get("message") or msg)[:160]


def hermes(*args, timeout=60):
    p = subprocess.run(["hermes", *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    return p.returncode, (p.stdout + p.stderr)


def load_status():
    try:
        return json.load(open(STATUS_FILE))
    except Exception:
        return {}


def save_status(s):
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    json.dump(s, open(STATUS_FILE, "w"))
    os.chmod(STATUS_FILE, 0o600)


def parse_auth_list():
    """{provider: [{id, label, source}]} from `hermes auth list` (no secrets in that output)."""
    rc, out = hermes("auth", "list")
    res, cur = {}, None
    for line in out.splitlines():
        m = re.match(r"^(\S+) \((\d+) credentials?\):", line)
        if m:
            cur = m.group(1)
            res[cur] = []
            continue
        m = re.match(r"^\s+#\d+\s+(\S+)\s+(api_key|oauth)\s+id=(\w+)\s+priority=(\d+)\s*(.*)$", line)
        if m and cur:
            res[cur].append({"label": m.group(1), "type": m.group(2), "id": m.group(3), "priority": int(m.group(4)),
                             "source": m.group(5).replace("←", "").strip()})
    return res


def stored_key(pid):
    """Highest-priority API key stored for a provider (read from Hermes's own credential pool)."""
    try:
        pool = json.load(open(os.path.join(HERMES_HOME, "auth.json"))).get("credential_pool", {}).get(pid, [])
    except Exception:
        pool = []
    for e in sorted(pool, key=lambda e: e.get("priority", 99)):
        k = e.get("api_key") or e.get("access_token") or e.get("key")
        if k and e.get("auth_type", "api_key") in ("api_key", "api-key"):
            return k
    return None


def active_model():
    out = {}
    for k in ("model.provider", "model.default"):
        rc, o = hermes("config", "get", k)
        out[k.split(".")[1]] = (o.strip().splitlines() or [""])[-1] if rc == 0 else ""
    return out


def restart_gateway(delay=1.0):
    """Kill `hermes gateway run`; start_hermes.sh's loop relaunches it, now with the new credentials/model."""
    def _go():
        time.sleep(delay)
        for pid in filter(str.isdigit, os.listdir("/proc")):
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()
            except OSError:
                continue
            if "gateway run" in cmd and "hermes" in cmd and int(pid) != os.getpid() and "keys_server" not in cmd:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except OSError:
                    pass
    threading.Thread(target=_go, daemon=True).start()


def caller_role(cookie, auth):
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    if auth:
        headers["Authorization"] = auth
    try:
        req = urllib.request.Request(OWUI + "/api/v1/auths/", headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read()).get("role")
    except Exception:
        return None


# ---------- actions ----------
def do_status():
    st, auth = load_status(), parse_auth_list()
    provs = []
    for pid, p in PROVIDERS.items():
        creds = auth.get(pid, [])
        provs.append({"id": pid, "label": p["label"], "note": p["note"], "link": p["link"], "hint": p["hint"],
                      "credentials": [{"id": c["id"], "from_web": c["label"].startswith("web-"),
                                       "source": "cargada acá" if c["label"].startswith("web-") else "del entorno"} for c in creds],
                      "validated": st.get(pid)})
    return {"providers": provs, "active": active_model()}


def do_save(pid, key, model, activate):
    if pid not in PROVIDERS:
        return 400, {"ok": False, "error": "Proveedor desconocido."}
    key = (key or "").strip()
    if not key or len(key) < 12 or any(c.isspace() for c in key):
        return 400, {"ok": False, "error": "La clave está vacía o tiene espacios: copiala de nuevo, entera."}
    code, models = list_models(pid, key)
    if code in (400, 401, 403):  # Gemini answers 400 (not 401) for a bad key
        return 200, {"ok": False, "error": f"{PROVIDERS[pid]['label']} rechazó la clave (HTTP {code}). Revisá que la copiaste completa y que no está vencida."}
    if code != 200:
        return 200, {"ok": False, "error": f"No pude comunicarme con {PROVIDERS[pid]['label']} (HTTP {code}). Probá de nuevo en un minuto."}
    model = model or pick_default(pid, models)
    if not model:
        return 200, {"ok": False, "error": "No encontré modelos disponibles para ese proveedor."}
    ok, status, why = chat_test(pid, key, model)
    if not ok and status in (401, 403):
        return 200, {"ok": False, "error": f"{PROVIDERS[pid]['label']} rechazó la clave (HTTP {status}). Revisá que la copiaste completa, sin espacios, y que no está vencida. No la guardé."}
    if not ok and status == 429:
        return 200, {"ok": False, "error": f"La clave parece válida pero {PROVIDERS[pid]['label']} está limitando el uso ahora mismo (HTTP 429). Esperá un minuto y probá de nuevo. No la guardé."}
    if not ok:
        return 200, {"ok": False, "models": models[:200], "model": model,
                     "error": f"No pude confirmar que la clave funcione con el modelo «{model}» ({why or 'HTTP ' + str(status)}). Probá con otro modelo de la lista. No la guardé."}
    with _lock:
        label = "web-" + time.strftime("%Y%m%d-%H%M%S")
        rc, out = hermes("auth", "add", pid, "--type", "api-key", "--api-key", key, "--label", label, "--priority", "0")
        if rc != 0:
            return 200, {"ok": False, "error": "La clave es válida pero Hermes no pudo guardarla: " + out.strip()[-160:]}
        st = load_status()
        st[pid] = {"ok": True, "at": int(time.time()), "last4": key[-4:], "model": model}
        save_status(st)
        if activate:
            hermes("config", "set", "model.provider", pid)
            hermes("config", "set", "model.default", model)
    restart_gateway()
    return 200, {"ok": True, "model": model, "models": models[:200], "last4": key[-4:], "activated": bool(activate),
                 "message": f"Clave de {PROVIDERS[pid]['label']} válida y guardada (…{key[-4:]}). Hermes la usará desde ahora"
                            + (f" con el modelo {model}." if activate else ".") + " Se reinicia en unos segundos."}


def do_use(pid, model):
    key = stored_key(pid) if pid in PROVIDERS else None
    if not key:
        return 200, {"ok": False, "error": "No tengo una clave guardada de ese proveedor (las del entorno no se pueden leer acá)."}
    ok, status, why = chat_test(pid, key, model)
    if not ok:
        return 200, {"ok": False, "error": f"El modelo «{model}» no respondió ({why or 'HTTP ' + str(status)}). No lo cambié."}
    hermes("config", "set", "model.provider", pid)
    hermes("config", "set", "model.default", model)
    restart_gateway()
    return 200, {"ok": True, "message": f"Listo: Hermes usará {model} ({PROVIDERS[pid]['label']}). Se reinicia en unos segundos."}


SKIP = re.compile(r"embed|guard|safety|reward|parse|rerank|retriev|clip|vila|fuyu|paligemma|neva|kosmos|riva|tts|asr|whisper|"
                  r"image|diffusion|stable|flux|sdxl|translat|moderation|audio|vision|ocr|bge|nv-|-vl|/vl", re.I)


def candidates(pid, models, cap=16):
    """Chat-looking models worth testing: providers list far more than a free account can actually call."""
    ms = [m for m in models if not SKIP.search(m)]
    if pid == "openrouter":
        ms = [m for m in ms if m.endswith(":free")]
    elif pid == "gemini":
        ms = [m for m in ms if "gemini" in m]
    # house models first (they are the ones that tend to be enabled on free tiers)
    ms.sort(key=lambda m: (not m.startswith("nvidia/"), m))
    return ms[:cap]


def do_probe(pid):
    """Which models can THIS key really run? One-token test each, in parallel, bounded in time."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    key = stored_key(pid) if pid in PROVIDERS else None
    if not key:
        return 200, {"verified": [], "error": "Sin clave guardada acá."}
    cands = candidates(pid, list_models(pid, key)[1])
    ok = []
    deadline = time.time() + 40
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(chat_test, pid, key, m, 20): m for m in cands}  # 20s each: the whole probe must stay under the edge's ~60s
        try:
            for f in as_completed(futs, timeout=max(1, deadline - time.time())):
                try:
                    if f.result()[0]:
                        ok.append(futs[f])
                except Exception:
                    pass
        except Exception:
            pass
    return 200, {"verified": sorted(ok), "tested": len(cands)}


def do_models(pid):
    key = stored_key(pid) if pid in PROVIDERS else None
    if not key:
        return 200, {"models": [], "error": "Sin clave guardada acá."}
    return 200, {"models": list_models(pid, key)[1][:300]}


def do_remove(pid, cid):
    auth = parse_auth_list().get(pid, [])
    tgt = [c for c in auth if c["id"] == cid and c["label"].startswith("web-")]
    if not tgt:
        return 200, {"ok": False, "error": "Solo se pueden quitar las claves cargadas desde esta página."}
    rc, out = hermes("auth", "remove", pid, cid)
    st = load_status()
    st.pop(pid, None)
    save_status(st)
    restart_gateway()
    return 200, {"ok": rc == 0, "message": "Clave quitada." if rc == 0 else out.strip()[-160:]}


# ---------- http ----------
PAGE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys_page.html"), encoding="utf-8").read()


class Handler(BaseHTTPRequestHandler):
    server_version = "keys/1"

    def log_message(self, fmt, *args):  # never log bodies/paths with data
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'self'")
        self.end_headers()
        self.wfile.write(data)

    def _authed(self):
        role = caller_role(self.headers.get("Cookie"), self.headers.get("Authorization"))
        if role != "admin":
            self._send(403, {"error": "Solo el administrador de esta cuenta puede gestionar las claves."})
            return False
        return True

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/keys", "/keys/"):
            return self._send(200, PAGE.encode(), "text/html") if self._authed() else None
        if path == "/keys/api/status":
            return self._send(200, do_status()) if self._authed() else None
        m = re.match(r"^/keys/api/models/([a-z]+)$", path)
        if m:
            return self._send(*do_models(m.group(1))) if self._authed() else None
        m = re.match(r"^/keys/api/probe/([a-z]+)$", path)
        if m:
            return self._send(*do_probe(m.group(1))) if self._authed() else None
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.headers.get("X-Keys") != "1":
            return self._send(400, {"error": "missing X-Keys header"})
        if not self._authed():
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(min(n, 20000)) or b"{}")
        except Exception:
            return self._send(400, {"error": "bad json"})
        path = self.path.split("?", 1)[0]
        if path == "/keys/api/save":
            return self._send(*do_save(body.get("provider"), body.get("key"), body.get("model"), body.get("activate", True)))
        if path == "/keys/api/use":
            return self._send(*do_use(body.get("provider"), body.get("model") or ""))
        if path == "/keys/api/remove":
            return self._send(*do_remove(body.get("provider"), body.get("id") or ""))
        self._send(404, {"error": "not found"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
