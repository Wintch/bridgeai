#!/usr/bin/env python3
"""Keys page for a per-person Hermes stack: paste an LLM API key, have it VALIDATED against the provider, stored the
official way (`hermes auth add`), and pick the model Hermes will use from then on. Hermes re-reads its credential pool on
every request (verified 2026-10-05: a bad key at priority 0 was tried, got 403, and Hermes rotated to the next one), so a
KEY needs no restart. A MODEL change does: `hermes config set model.*` rewrites config.yaml but the running gateway keeps
the old model until it restarts (found 2026-10-09; see HERMES_ARCHITECTURE.md). An earlier version bounced the gateway
after every change and cut in-flight chats ("Response payload is not completed"), so now the gateway is restarted only
when the model really changed AND gateway_state.json shows no active turn (SIGTERM to /tmp/hermes-gateway.pid; the loop in
start_hermes.sh relaunches it, ~18 s). If a turn is running the answer says so and the change applies at the next restart.
Needs no LLM, which is the point: a new person has no key yet, so Hermes itself cannot help them enter one.

Runs inside the Hermes container (HERMES_KEYS_UI=1, see start_hermes.sh), port 8700, stdlib only. The `web` nginx
container proxies /keys/ here behind the Open WebUI login (auth_request); on top of that this server asks Open WebUI
who the caller is (forwarding the session cookie) and only lets ADMINS through, so a second Open WebUI account can't
touch the keys. State-changing calls also need an `X-Keys: 1` header (a cross-site form post can't set it).

Nothing here ever logs or returns a key: only the last 4 characters. A key is stored only after BOTH the key check and
a one-token test call to the chosen model succeed.
"""
import hashlib
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
    "openrouter": {
        "label": "OpenRouter", "note": "Tiene modelos gratuitos (terminan en :free) con límite diario. La más simple para empezar.",
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
    "nvidia": {
        "label": "NVIDIA NIM", "note": "Gratis, sin tarjeta (≈40 pedidos por minuto), la más generosa; pide validar un celular por SMS.",
        "link": "https://build.nvidia.com/settings/api-keys", "base": "https://integrate.api.nvidia.com/v1",
        "default": "nvidia/nemotron-3.5-super-vl-120b-a12b", "hint": "empieza con nvapi-"},
}

# OpenRouter :free models share ONE small daily cap per key (50 requests/day), each probe call spends it: probe only these
# (ops/lib/providers.py is not in the image, so the short list lives here; keep it in step with providers.MENU).
OR_PROBE = ["google/gemma-4-31b-it:free", "nvidia/nemotron-3.5-super-vl:free"]
PROBE_CAP = {"openrouter": 3, "gemini": 6}   # requests one probe may spend; other providers: PROBE_CAP_DEFAULT
PROBE_CAP_DEFAULT = 16
PROBE_TTL_OK, PROBE_TTL_EMPTY = 4 * 3600, 15 * 60
_probe_cache = {}   # (provider, sha256(key)) -> (expires, result); in memory only, the key itself is never kept

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
    if isinstance(d, list):   # Gemini wraps some errors in a list
        d = {"error": d[0] if d else ""}
    if not isinstance(d, dict):
        d = {"error": d}
    if st == 200 and d.get("choices"):
        return True, st, ""
    err = d.get("error") or d.get("detail") or ""
    if isinstance(err, list):
        err = err[0] if err else ""
    if isinstance(err, dict):
        err = err.get("message") or err
    return False, st, str(err or "")[:160]


def hermes(*args, timeout=60, stdin_text=None):
    p = subprocess.run(["hermes", *args], capture_output=True, text=True, timeout=timeout,
                       **({"input": stdin_text} if stdin_text is not None else {"stdin": subprocess.DEVNULL}))
    return p.returncode, (p.stdout + p.stderr)


def load_status():
    try:
        return json.load(open(STATUS_FILE))
    except Exception:
        return {}


def save_status(s):
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    tmp = STATUS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATUS_FILE)


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
def web_date(label):
    """'2026-10-12' from a 'web-YYYYMMDD-HHMMSS' label ('' if it does not parse)."""
    m = re.match(r"^web-(\d{4})(\d{2})(\d{2})-", label or "")
    return "-".join(m.groups()) if m else ""


def do_status():
    st, auth = load_status(), parse_auth_list()
    provs = []
    for pid, p in PROVIDERS.items():
        creds = auth.get(pid, [])
        provs.append({"id": pid, "label": p["label"], "note": p["note"], "link": p["link"], "hint": p["hint"],
                      "credentials": [{"id": c["id"], "from_web": c["label"].startswith("web-"), "date": web_date(c["label"]),
                                       "source": "cargada acá" if c["label"].startswith("web-") else "del entorno"} for c in creds],
                      "validated": st.get(pid)})
    return {"providers": provs, "active": active_model()}


def set_model(pid, model):
    """`hermes config set` both keys; True only if both succeeded (their rc used to be ignored)."""
    ok = True
    for k, v in (("model.provider", pid), ("model.default", model)):
        rc, _ = hermes("config", "set", k, v)
        if rc != 0:
            print(f"keys_server: hermes config set {k} failed rc={rc}", flush=True)
            ok = False
    return ok


def gateway_busy():
    """True / False from gateway_state.json's active_agents; None if the file is unreadable (then do not touch the gateway)."""
    try:
        return bool(json.load(open(os.path.join(HERMES_HOME, "gateway_state.json"))).get("active_agents"))
    except Exception:
        return None


def apply_model(pid, model):
    """Set the model, then make the running gateway pick it up (it keeps the old model until restarted). Returns
    (ok, sentence for the person). The gateway is restarted only if the model changed and no turn is running."""
    before = active_model()
    if not set_model(pid, model):
        return False, "No pude cambiar el modelo en Hermes. Avisale al operador."
    if (before.get("provider"), before.get("default")) == (pid, model):
        return True, f"Hermes ya usaba {model}."
    busy = gateway_busy()
    if busy is False:
        try:
            with open("/tmp/hermes-gateway.pid") as f:
                os.kill(int(f.read().strip()), signal.SIGTERM)  # start_hermes.sh relaunches it
            return True, f"Hermes se reinicia para usar {model}: vuelve en unos 20 segundos."
        except Exception as e:
            print(f"keys_server: gateway restart failed: {type(e).__name__}", flush=True)
    if busy:
        return True, f"El modelo {model} queda configurado, pero Hermes está respondiendo ahora: se aplica en el próximo reinicio (por inactividad se duerme solo a los 10 minutos)."
    return True, f"El modelo {model} queda configurado: se aplica cuando Hermes se reinicie (por inactividad se duerme solo a los 10 minutos)."


def run_tests(pid, key, models, timeout=40):
    """chat_test every model in parallel; {model: (ok, status, why)} (a model missing from the result timed out)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    res = {}
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(models)))) as ex:
        futs = {ex.submit(chat_test, pid, key, m, 25): m for m in models}
        try:
            for f in as_completed(futs, timeout=timeout):
                try:
                    res[futs[f]] = f.result()
                except Exception:
                    pass
        except Exception:
            pass
    return res


def store_key(pid, key, model, activate):
    """Add the key (stdin, never argv), replace the earlier web- credentials of this provider, record the status, and
    optionally switch the model. Returns (ok, error text or sentence about the model)."""
    with _lock:
        old = [c["id"] for c in parse_auth_list().get(pid, []) if c["label"].startswith("web-")]
        label = "web-" + time.strftime("%Y%m%d-%H%M%S")
        # The key goes in on stdin (`hermes auth add` reads it when --api-key is absent): on argv it was visible in
        # /proc/<pid>/cmdline to every process in the container while the command ran.
        rc, out = hermes("auth", "add", pid, "--type", "api-key", "--label", label, "--priority", "0", stdin_text=key + "\n")
        if rc != 0:
            # never echo provider/CLI output to the browser: it can carry a (masked) key
            print(f"keys_server: hermes auth add failed rc={rc}", flush=True)
            return False, "La clave es válida pero Hermes no pudo guardarla. Avisale al operador."
        for cid in old:   # the new one is in: drop the previous one(s) so a dead key does not pile up
            rc, _ = hermes("auth", "remove", pid, cid)
            if rc != 0:
                print(f"keys_server: hermes auth remove (replaced credential) failed rc={rc}", flush=True)
        st = load_status()
        st[pid] = {"ok": True, "at": int(time.time()), "last4": key[-4:], "model": model if activate else None}
        save_status(st)
        if activate:
            return apply_model(pid, model)
    return True, ""


def do_save(pid, key, model, activate):
    if pid not in PROVIDERS:
        return 400, {"ok": False, "error": "Proveedor desconocido."}
    key = (key or "").strip()
    if not key or len(key) < 12 or any(c.isspace() for c in key):
        return 400, {"ok": False, "error": "La clave está vacía o tiene espacios: copiala de nuevo, entera."}
    label = PROVIDERS[pid]["label"]
    code, models = list_models(pid, key)
    if code in (400, 401, 403):  # Gemini answers 400 (not 401) for a bad key
        return 200, {"ok": False, "error": f"{label} rechazó la clave (HTTP {code}). Revisá que la copiaste completa y que no está vencida."}
    if code != 200:
        return 200, {"ok": False, "error": f"No pude comunicarme con {label} (HTTP {code}). Probá de nuevo en un minuto."}
    chosen = bool(model)
    if chosen:
        tests = [model]
    else:
        default = pick_default(pid, models)
        if not default:
            return 200, {"ok": False, "error": "No encontré modelos disponibles para ese proveedor."}
        # the default may be a model this account cannot run: try a few more in parallel instead of giving up
        tests = [default] + [m for m in candidates(pid, models) if m != default][:3]
    res = run_tests(pid, key, tests)
    good = [m for m in tests if res.get(m, (False,))[0]]
    codes = [res[m][1] for m in tests if m in res]
    if not good and any(c in (401, 403) for c in codes):
        return 200, {"ok": False, "error": f"{label} rechazó la clave (HTTP {[c for c in codes if c in (401, 403)][0]}). Revisá que la copiaste completa, sin espacios, y que no está vencida. No la guardé."}
    if good:
        model, activate = good[0], bool(activate)
    elif 429 in codes:
        # a 429 means the provider recognised the key: it is valid, only rate-limited right now. Keep it, do not switch.
        model, activate = None, False
    else:
        first = res.get(tests[0], (False, 0, "sin respuesta"))
        return 200, {"ok": False, "models": models[:200], "model": tests[0],
                     "error": f"No pude confirmar que la clave funcione con «{tests[0]}» ({first[2] or 'HTTP ' + str(first[1])})"
                              + (f" ni con otros {len(tests) - 1} modelos que probé" if len(tests) > 1 else "")
                              + ". Elegí otro modelo de la lista y tocá «Usar este modelo»: la clave que pegaste se prueba con ese. No la guardé."}
    ok, note = store_key(pid, key, model, activate)
    if not ok:
        return 200, {"ok": False, "error": note}
    if model is None:
        return 200, {"ok": True, "model": None, "models": models[:200], "last4": key[-4:], "activated": False,
                     "message": f"La clave de {label} es válida y la guardé (…{key[-4:]}), pero {label} está limitando el uso ahora mismo (HTTP 429): no cambié el modelo en uso. "
                                "Probá con «Cambiar de modelo» más tarde (los límites gratuitos suelen renovarse al día siguiente)."}
    return 200, {"ok": True, "model": model, "models": models[:200], "last4": key[-4:], "activated": bool(activate),
                 "message": f"Clave de {label} válida y guardada (…{key[-4:]})."
                            + (f" {note}" if activate else " No cambié el modelo en uso.")}


def do_use(pid, model):
    key = stored_key(pid) if pid in PROVIDERS else None
    if not key:
        return 200, {"ok": False, "error": "No tengo una clave guardada de ese proveedor (las del entorno no se pueden leer acá)."}
    ok, status, why = chat_test(pid, key, model)
    if not ok:
        return 200, {"ok": False, "error": f"El modelo «{model}» no respondió ({why or 'HTTP ' + str(status)}). No lo cambié."}
    ok, note = apply_model(pid, model)
    return 200, {"ok": ok, **({"message": note} if ok else {"error": note})}


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
    """Which models can THIS key really run? One-token test each, in parallel, bounded in time. Every test is a real
    request that counts against the provider's quota (OpenRouter :free: 50/day per key), so the list is capped per
    provider and the result is cached per (provider, key hash)."""
    key = stored_key(pid) if pid in PROVIDERS else None
    if not key:
        return 200, {"verified": [], "error": "Sin clave guardada acá."}
    ck = (pid, hashlib.sha256(key.encode()).hexdigest())
    hit = _probe_cache.get(ck)
    if hit and hit[0] > time.time():
        return 200, dict(hit[1], cached=True)
    models = list_models(pid, key)[1]
    if pid == "openrouter":
        cands = [m for m in OR_PROBE if m in models] or candidates(pid, models, 2)
    else:
        cands = candidates(pid, models, PROBE_CAP.get(pid, PROBE_CAP_DEFAULT))
    res = run_tests(pid, key, cands)
    ok = sorted(m for m in cands if res.get(m, (False,))[0])
    out = {"verified": ok, "tested": len(cands)}
    _probe_cache[ck] = (time.time() + (PROBE_TTL_OK if ok else PROBE_TTL_EMPTY), out)
    return 200, out


def do_remove(pid, cid):
    with _lock:
        auth = parse_auth_list().get(pid, [])
        tgt = [c for c in auth if c["id"] == cid and c["label"].startswith("web-")]
        if not tgt:
            return 200, {"ok": False, "error": "Solo se pueden quitar las claves cargadas desde esta página."}
        rc, out = hermes("auth", "remove", pid, cid)
        st = load_status()
        st.pop(pid, None)
        save_status(st)
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
        m = re.match(r"^/keys/api/probe/([a-z]+)$", path)
        if m:
            return self._send(*do_probe(m.group(1)))
        if path == "/keys/api/remove":
            return self._send(*do_remove(body.get("provider"), body.get("id") or ""))
        self._send(404, {"error": "not found"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
