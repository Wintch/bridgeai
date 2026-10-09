#!/usr/bin/env python3
"""router -- "local first" in front of Hermes: the home model answers, the cloud only when needed, always announced.

Hermes's primary model is this router (`model.provider custom`, `model.default local-first`,
`model.base_url http://127.0.0.1:8650/v1`). It runs inside each Hermes container (started by start_hermes.sh), so
every person's keys stay in their own container.

Per turn (the person's message plus the tool calls that follow it), decided once and kept for the whole turn:
  1. The person asks for the cloud ("usá la nube", "в облаке", "use the cloud")       -> cloud, "lo pediste".
  2. Home model down (the stack's "llm" gateway, /etc/aibridge/gateways.json)          -> needs the cloud.
  3. Otherwise the home model classifies the message itself (LOCAL / NUBE, thinking off, ~0.3 s): a small model
     with tools handles chat, lookups, media; long code, multi-step reasoning, long documents, high-stakes advice
     or "your last answer was wrong" need the cloud.
  4. A local answer that fails (error, context full)                                   -> needs the cloud.
**Consent (operator decision 2026-10-09):** "needs the cloud" never sends anything by itself. The router answers
with a 🔒 message: why, which cloud model, what would travel, and how to accept ("sí"/"dale"; "siempre" = for the
rest of this conversation, until /new) or pick another model with /model. The next "sí" sends the turn.
Hermes's own small calls (titles, memory review: no tools) only ever run at home; when home is down they fail.
Hermes's own fallback chain must be empty for a router stack (model_guard does it), or it would bypass consent.

What travels to the cloud (ROUTER_CLOUD_CONTEXT): "full" (default, the operator's choice) = the whole conversation;
"recent:N" = the last N exchanges plus the question; "turn" = the current question only. Always the system prompt Hermes needs to
use its tools, but with the person's memory and profile blocks removed (ROUTER_STRIP_MEMORY=1, default), and
images replaced by a placeholder. Every cloud answer the person sees starts with one line saying it was the cloud,
why, and what travelled.

Each decision appends one metadata line to /workdir/.gateway-log.jsonl (route, reason, provider, seconds, how many
messages travelled out of how many). Never the text.
"""
import hashlib, json, os, re, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("ROUTER_PORT", "8650"))
GATEWAYS = os.environ.get("GATEWAYS_CONFIG", "/etc/aibridge/gateways.json")
LOG = os.environ.get("GATEWAY_LOG", "/workdir/.gateway-log.jsonl")
HERMES_ENV = os.path.join(os.environ.get("HERMES_HOME", "/root/.hermes"), ".env")
CONTEXT = os.environ.get("ROUTER_CLOUD_CONTEXT", "full")       # operator: "que sea todo", with consent
STRIP_MEMORY = os.environ.get("ROUTER_STRIP_MEMORY", "1") == "1"
# (name shown to the person, base url, model, key variable). Same preference as ops/lib/providers.py.
CLOUD = [("NVIDIA nemotron-3-super", "https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3-super-120b-a12b", "NVIDIA_API_KEY"),
         ("NVIDIA gpt-oss-20b", "https://integrate.api.nvidia.com/v1", "openai/gpt-oss-20b", "NVIDIA_API_KEY"),
         ("Gemini flash-lite", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite", "GEMINI_API_KEY")]
PASS_KEYS = {"messages", "tools", "tool_choice", "temperature", "top_p", "max_tokens", "max_completion_tokens",
             "stream", "stream_options", "stop", "response_format", "parallel_tool_calls", "seed", "n"}
ASK_CLOUD = re.compile(r"(us[aá]|use|pas[aá]|mand[aá]).{0,20}\b(nube|cloud)\b|\bв облак|облако|\bmodelo grande\b", re.I)
MEMORY_HEAD = re.compile(r"═{20,}\n(?:MEMORY \(your personal notes\)|USER PROFILE \(who the user is\))[^\n]*\n═{20,}\n")
MEMORY_END = re.compile(r"\n\n(?=═{20,}\n|Active Hermes profile:|Conversation started:|Timezone:)")
YES = re.compile(r"^\W*(s[ií]|dale|ok(ay)?|yes|sure|да|давай|ладно|acepto|mand[aá]lo|envi[aá]lo|siempre|always|всегда)\b", re.I)
ALWAYS = re.compile(r"\b(siempre|always|всегда)\b", re.I)
TS_PREFIX = re.compile(r"^(\s*\[[^\]]{8,40}\])+\s*")
CONSENT_MARK = "🔒"
CLASSIFY = ("Decidí quién responde el último mensaje de la persona.\n"
            "LOCAL: un modelo chico con herramientas (búsqueda web, terminal, fotos, audio, video) alcanza: charla, "
            "preguntas simples, buscar clima, noticias, precios o lugares, traducir, resumir algo corto, recordatorios, "
            "describir fotos o videos, pedir un audio.\n"
            "NUBE: hace falta un modelo grande: escribir o corregir código de más de unas líneas, razonamiento o "
            "cálculo de varios pasos, analizar un documento largo, planificar algo complejo, consejos de salud, "
            "legales o de dinero con consecuencias, o la persona dice que la respuesta anterior estaba mal.\n"
            "Respondé solo LOCAL o NUBE.")

_turns, _sessions, _lock = {}, set(), threading.Lock()


def log(**kw):
    kw.update(gateway="router", ts=round(time.time(), 1))
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(kw) + "\n")
    except OSError:
        pass


def local_host():
    try:
        h = (json.load(open(GATEWAYS)).get("llm") or [None])[0]
        return (h["url"].rstrip("/"), h.get("model", "local")) if h else (None, None)
    except (OSError, ValueError, KeyError, TypeError):
        return None, None


def up(url):
    try:
        with urllib.request.urlopen(url + "/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def key(var):
    if os.environ.get(var):
        return os.environ[var]
    try:
        for line in open(HERMES_ENV):
            if line.startswith(var + "="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def text_of(msg):
    c = msg.get("content")
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c or ""


def post(url, body, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "bridgeai-router/1.0", **headers})
    return urllib.request.urlopen(req, timeout=timeout)


def classify(url, model, msgs, u):
    prev = next((text_of(m)[:600] for m in reversed(msgs[:u]) if m.get("role") == "assistant" and text_of(m)), "")
    content = (f"Respuesta anterior del asistente: {prev}\n\n" if prev else "") + f"Último mensaje: {text_of(msgs[u])[:3000]}"
    body = {"model": model, "messages": [{"role": "system", "content": CLASSIFY}, {"role": "user", "content": content}],
            "max_tokens": 4, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    try:
        with post(url + "/v1/chat/completions", body, {}, 20) as r:
            out = json.load(r)["choices"][0]["message"].get("content") or ""
        return "nube" if "NUBE" in out.upper() else "local"
    except Exception:
        return "local"          # the answer call itself will fail over if home is really broken


def decide(msgs):
    """(route, reason, turn key, first call of the turn?). route: local | nube (consented) | ask (needs consent)."""
    users = [i for i, m in enumerate(msgs) if m.get("role") == "user"]
    if not users:
        return "local", "sin mensaje", None, False
    u = users[-1]
    k = hashlib.sha1(json.dumps([m.get("content") for m in msgs[:u + 1] if m.get("role") != "system"],
                                sort_keys=True, default=str).encode()).hexdigest()
    with _lock:
        if k in _turns:
            return _turns[k]["route"], _turns[k]["reason"], k, False
    session = hashlib.sha1(str(msgs[users[0]].get("content")).encode()).hexdigest()
    said = TS_PREFIX.sub("", text_of(msgs[u])).strip()
    prev = next((text_of(m) for m in reversed(msgs[:u]) if m.get("role") == "assistant" and text_of(m)), "")
    url, model = local_host()
    if CONSENT_MARK in prev and YES.match(said):
        route, reason = "nube", "lo autorizaste"
        if ALWAYS.search(said):
            with _lock:
                _sessions.add(session)
    elif ASK_CLOUD.search(said):
        route, reason = "nube", "lo pediste"
    else:
        if not url or not up(url):
            route, reason = "ask", "tu PC (el modelo local) no responde"
        else:
            route = classify(url, model, msgs, u)
            route, reason = ("ask", "el modelo local cree que la pregunta necesita un modelo más grande") if route == "nube" else ("local", "local")
        with _lock:
            if route == "ask" and session in _sessions:
                route, reason = "nube", reason + " (autorizaste la nube para esta conversación)"
    with _lock:
        if len(_turns) > 500:
            _turns.clear()
        _turns[k] = {"route": route, "reason": reason, "noticed": False, "session": session}
    return route, reason, k, True


def strip_memory(text):
    if not STRIP_MEMORY:
        return text
    out, pos = "", 0
    for m in MEMORY_HEAD.finditer(text):
        if m.start() < pos:
            continue
        end = MEMORY_END.search(text, m.end())
        out += text[pos:m.start()] + "[memoria personal omitida por el router antes de salir a la nube]"
        pos = end.start() if end else len(text)
    return out + text[pos:]


def cloud_messages(msgs):
    """The messages the cloud gets under ROUTER_CLOUD_CONTEXT, and a phrase for the notice."""
    system = [dict(m, content=strip_memory(text_of(m))) for m in msgs if m.get("role") == "system"]
    rest = [m for m in msgs if m.get("role") != "system"]
    users = [i for i, m in enumerate(rest) if m.get("role") == "user"]
    if CONTEXT == "full" or not users:
        keep, what = rest, "toda la conversación"
    elif CONTEXT == "turn":
        keep, what = rest[users[-1]:], "solo tu pregunta actual"
    else:
        n = int(CONTEXT.split(":")[1]) if ":" in CONTEXT else 3
        keep = rest[users[max(0, len(users) - 1 - n)]:]
        what = f"tu pregunta y los últimos {n} intercambios"
    if STRIP_MEMORY:
        what += ", sin tus memorias"
    clean = []
    for m in keep:
        if isinstance(m.get("content"), list):
            m = dict(m, content=[p if p.get("type") != "image_url" else {"type": "text", "text": "[imagen omitida]"}
                                 for p in m["content"]])
        clean.append(m)
    return system + clean, what, len(system) + len(clean)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def reply(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url, _ = local_host()
        if self.path.rstrip("/") in ("/health", "/v1/health"):
            return self.reply(200, {"status": "ok"})
        if self.path.startswith("/props") and url:      # llama.cpp context size, which Hermes reads
            try:
                with urllib.request.urlopen(url + "/props", timeout=3) as r:
                    return self.reply(200, r.read())
            except Exception:
                pass
        if self.path.startswith("/v1/models") or self.path.startswith("/models"):
            return self.reply(200, {"object": "list", "data": [{"id": "local-first", "object": "model",
                                                                 "owned_by": "bridgeai", "context_length": 81920}]})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self.reply(404, {"error": "not found"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        msgs = body.get("messages", [])
        aux = not body.get("tools")
        t0 = time.time()
        route, reason, k, first = ("local", "auxiliar", None, False) if aux else decide(msgs)
        url, model = local_host()
        if route == "local":
            if not url:
                ok = "sin modelo local"
            else:
                ok = self.forward(url + "/v1/chat/completions", dict(body, model=model), {}, None)
            if ok is True:
                if first:
                    log(route="local", reason=reason, seconds=round(time.time() - t0, 1))
                return
            if aux:                                    # Hermes's own small calls never leave home
                return self.reply(503, {"error": {"message": f"router: local model unavailable ({ok})", "type": "router"}})
            route, reason = "ask", f"el modelo local falló ({ok})"
            with _lock:
                if k in _turns:
                    sess = _turns[k]["session"]
                    route = "nube" if sess in _sessions else "ask"
                    _turns[k].update(route=route, reason=reason)
        if route == "ask":
            return self.ask(body, msgs, reason, k)
        self.cloud(body, msgs, reason, k, aux, t0)

    def ask(self, body, msgs, reason, k):
        """No data leaves: answer with the consent question instead."""
        _, what, sent = cloud_messages(msgs)
        name = next((n for n, _, _, var in CLOUD if key(var)), None)
        if name:
            text = (f"{CONSENT_MARK} Para esto haría falta la nube: {reason}.\n"
                    f"Se enviaría a {name}: {what}.\n"
                    "¿Lo envío? Respondé \"sí\" (o \"sí, siempre\" para el resto de esta conversación). "
                    "También podés elegir otro modelo con /model.")
        else:
            text = (f"{CONSENT_MARK} Para esto haría falta la nube ({reason}), pero no hay ninguna key de nube "
                    "configurada. Podés agregar una en la página de keys o elegir otro modelo con /model.")
        log(route="ask", reason=reason.split(" (")[0], would_send=sent, total=len(msgs), context=CONTEXT)
        if k:
            with _lock:
                _turns.pop(k, None)                    # the person's answer is a new turn
        self.assistant(text, bool(body.get("stream")))

    def assistant(self, text, stream):
        now = int(time.time())
        if not stream:
            return self.reply(200, {"id": "router", "object": "chat.completion", "created": now, "model": "local-first",
                                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                                 "finish_reason": "stop"}],
                                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        for delta, fin in (({"role": "assistant", "content": text}, None), ({}, "stop")):
            chunk = {"id": "router", "object": "chat.completion.chunk", "created": now, "model": "local-first",
                     "choices": [{"index": 0, "delta": delta, "finish_reason": fin}]}
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def cloud(self, body, msgs, reason, k, aux, t0):
        out, what, sent = cloud_messages(msgs)
        base = {kk: v for kk, v in body.items() if kk in PASS_KEYS}
        tried = []
        for name, url, model, var in CLOUD:
            kv = key(var)
            if not kv:
                continue
            with _lock:
                notice_due = bool(k) and not _turns.get(k, {}).get("noticed")
            notice = f"☁️ Respondió la nube ({name}), {reason}. Viajó: {what}.\n\n" if notice_due else None
            ok = self.forward(url + "/chat/completions", dict(base, model=model, messages=out),
                              {"Authorization": f"Bearer {kv}"}, notice, k)
            if ok is True:
                log(route="nube", reason=reason.split(" (")[0], provider=name, seconds=round(time.time() - t0, 1),
                    sent=sent, total=len(msgs), aux=aux, context=CONTEXT)
                return
            tried.append(f"{name}: {ok}")
        log(route="none", reason=reason.split(" (")[0], tried=len(tried), aux=aux)
        self.assistant("⚠️ No respondió ningún modelo: ni el local ni la nube (" + "; ".join(tried or ["sin keys"]) +
                       "). Probá de nuevo en un rato o elegí otro modelo con /model.", bool(body.get("stream")))

    def forward(self, url, body, headers, notice, turn=None):
        """Send the request; stream (or return) the answer to Hermes. True, or a short error when nothing was sent
        yet (so the caller can try the next backend). A notice goes in front of the turn's final answer."""
        stream = bool(body.get("stream"))
        try:
            r = post(url, body, headers, 600)
        except urllib.error.HTTPError as e:
            return f"HTTP {e.code}"
        except Exception as e:
            return type(e).__name__
        with r:
            if not stream:
                d = json.load(r)
                msg = (d.get("choices") or [{}])[0].get("message", {})
                if notice and not msg.get("tool_calls"):
                    msg["content"] = notice + (msg.get("content") or "")
                    self.noticed(turn)
                return self.reply(200, d) or True
            if notice is None:                        # pass the stream straight through
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                for line in r:
                    self.wfile.write(line)
                    self.wfile.flush()
                return True
            lines = r.read().splitlines(keepends=True)   # cloud is fast: buffer, to know if this is the final answer
        def has_tool_call(ln):                       # NVIDIA sends "tool_calls": null in every chunk
            try:
                return any((c.get("delta") or {}).get("tool_calls") for c in json.loads(ln[6:]).get("choices", []))
            except ValueError:
                return False
        tool_call = any(has_tool_call(ln) for ln in lines if ln.startswith(b"data: {"))
        first = next((json.loads(ln[5:]) for ln in lines if ln.startswith(b"data: {")), None)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if not tool_call and first:
            chunk = {"id": first.get("id", "router"), "object": "chat.completion.chunk", "created": first.get("created", int(time.time())),
                     "model": first.get("model", ""), "choices": [{"index": 0, "delta": {"role": "assistant", "content": notice},
                                                                    "finish_reason": None}]}
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.noticed(turn)
        self.wfile.writelines(lines)
        self.wfile.flush()
        return True

    @staticmethod
    def noticed(turn):
        if turn:
            with _lock:
                if turn in _turns:
                    _turns[turn]["noticed"] = True


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
