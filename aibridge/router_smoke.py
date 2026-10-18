#!/usr/bin/env python3
"""Integration smoke test of the router as shipped in the image: idle question, release notice, subagent, streaming.

Runs in a throwaway container, so it touches no person's data and needs no model or key (the home model is a fake):

  ssh <vm> "docker run --rm -i --entrypoint python3 aibridge-hermes-agent:latest -" < router_smoke.py

Exit 0 and "router_smoke: all ok" when every check passes. Stdlib only.
"""
import json, os, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

tmp = tempfile.mkdtemp()
LLM, ROUTER = 18700, 18650
os.environ.update(
    ROUTER_PORT=str(ROUTER), GATEWAYS_CONFIG=f"{tmp}/gateways.json", GATEWAY_LOG=f"{tmp}/log.jsonl",
    ROUTER_CONSENT_FILE=f"{tmp}/consent.json", ROUTER_RELEASE_FILE=f"{tmp}/release.txt",
    ROUTER_RELEASE_SEEN=f"{tmp}/seen", HERMES_HOME=tmp, ROUTER_IDLE_ASK_HOURS="5")
json.dump({"llm": [{"name": "fake", "url": f"http://127.0.0.1:{LLM}"}]}, open(f"{tmp}/gateways.json", "w"))
open(f"{tmp}/release.txt", "w", encoding="utf-8").write("id: t1\nes: AVISO-ACTUALIZACION\nru: ОБНОВЛЕНИЕ\n")

seen = []                                                  # the messages the fake home model received (not the classifier)


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = "LOCAL" if body.get("max_tokens") == 4 else "RESPUESTA-LOCAL"
        if text != "LOCAL":
            seen.append(body["messages"])
        if body.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for delta, fin in (({"role": "assistant", "content": text}, None), ({}, "stop")):
                self.wfile.write(b"data: " + json.dumps({"id": "f", "object": "chat.completion.chunk", "model": "fake",
                                 "choices": [{"index": 0, "delta": delta, "finish_reason": fin}]}).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            data = json.dumps({"id": "f", "object": "chat.completion", "model": "fake", "choices": [
                {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


sys.path.insert(0, os.environ.get("ROUTER_DIR", "/app"))
import router  # noqa: E402

for srv in (ThreadingHTTPServer(("127.0.0.1", LLM), Fake), ThreadingHTTPServer(("127.0.0.1", ROUTER), router.Handler)):
    threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.5)

TOOLS = [{"type": "function", "function": {"name": "x", "parameters": {"type": "object", "properties": {}}}}]
fails = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")


def stamp(hours_ago):
    return time.strftime("[%a %Y-%m-%d %H:%M:%S +00]", time.gmtime(time.time() - hours_ago * 3600))


def user(hours_ago, text):
    return {"role": "user", "content": f"{stamp(hours_ago)} {text}"}


def ask(msgs, stream=False, system="Platform: telegram"):
    body = {"model": "local-first", "messages": [{"role": "system", "content": system}] + msgs, "tools": TOOLS, "stream": stream}
    req = urllib.request.Request(f"http://127.0.0.1:{ROUTER}/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode()
    if not stream:
        return json.loads(raw)["choices"][0]["message"]["content"]
    return "".join(json.loads(ln[6:])["choices"][0]["delta"].get("content") or ""
                   for ln in raw.splitlines() if ln.startswith("data: {"))


# 1. release notice: once, in front of the first final answer (plain, then not again)
a = ask([user(1, "hola")])
check("release notice shown first", a.startswith("AVISO-ACTUALIZACION") and a.endswith("RESPUESTA-LOCAL"), True)
check("release notice remembered", open(f"{tmp}/seen").read(), "t1")
check("release notice not repeated", ask([user(1, "hola"), {"role": "assistant", "content": a}, user(0.9, "de nuevo")]), "RESPUESTA-LOCAL")

# 2. streaming carries a new release notice too
open(f"{tmp}/release.txt", "w", encoding="utf-8").write("id: t2\nes: AVISO-DOS\n")
a = ask([user(1, "otra")], stream=True)
check("release notice in a stream", a, "AVISO-DOS\n\nRESPUESTA-LOCAL")

# 3. nine idle hours: the router asks, the model is not called
n = len(seen)
old = [user(9, "pregunta vieja"), {"role": "assistant", "content": "respuesta vieja"}]
q = ask(old + [user(0, "buenas!")])
check("idle question", q.startswith("🕓 Pasaron 9 h"), True)
check("idle question did not reach the model", len(seen), n)
check("idle question in Russian", ask(old + [user(0, "привет")]).startswith("🕓 Прошло 9 ч"), True)

# 4. "seguir": the model answers the pending message and never sees the question or the "seguir"
a = ask(old + [user(0, "buenas!"), {"role": "assistant", "content": q}, user(0, "seguir")])
check("seguir gets an answer", a, "RESPUESTA-LOCAL")
sent = [m.get("content") if isinstance(m.get("content"), str) else "" for m in seen[-1]]
check("model never saw the question", any(c.startswith("🕓") for c in sent), False)
check("model never saw the seguir", any(c.endswith("seguir") for c in sent), False)
check("model saw the pending message", any(c.endswith("buenas!") for c in sent), True)

# 5. the same through a stream, and a real new message after the question
a = ask(old + [user(0, "buenas!"), {"role": "assistant", "content": q}, user(0, "seguir")], stream=True)
check("seguir in a stream", a, "RESPUESTA-LOCAL")
a = ask(old + [user(0, "buenas!"), {"role": "assistant", "content": q}, user(0, "otra cosa: qué hora es")])
sent = [m.get("content") if isinstance(m.get("content"), str) else "" for m in seen[-1]]
check("a real answer after the question goes through", (a, any(c.endswith("qué hora es") for c in sent)), ("RESPUESTA-LOCAL", True))

# 6. a delegated subagent is never held, and a recent message is not asked about
sub = ask([user(9, "tarea")] + [user(0, "sigue")], system="Platform: subagent")
check("subagent not held", sub, "RESPUESTA-LOCAL")
check("no gap, no question", ask([user(1, "a"), {"role": "assistant", "content": "b"}, user(0.5, "c")]), "RESPUESTA-LOCAL")

print("\n".join(fails) or "router_smoke: all ok")
sys.exit(1 if fails else 0)
