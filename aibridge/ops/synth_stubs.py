#!/usr/bin/env python3
"""Tiny stub servers for the synthetic business days (SYNTHETIC_DAY.md section 3.1). Standard library only, local runs only.

  python3 ops/synth_stubs.py --zabbix 8701 --postiz 8702 --pbs 8703 --audd 8704 --gpu 8705 [--bind 127.0.0.1] [--gpu-seconds 0.3]

Each stub answers canned, INVENTED data and COUNTS its calls: GET /_counters returns {"calls": {"<key>": n}, "gpu_seconds": s}, POST /_reset clears.
They exist so a scenario that calls Zabbix, Postiz, a backup store, a song-recognition API or a GPU gateway never reaches a real service.
Point a test stack's gateway entry at them (gateways.json of the TEST side only); never reuse a real service's address or token.

The shapes are what the repo's own code expects where it has a client (Zabbix: JSON-RPC at /api_jsonrpc.php, the same methods gateway_zabbix_selftest.py
fakes; PBS: /api2/json/... like gateway.py), and what the services' public documentation says elsewhere (Postiz public API, AudD): recalled,
not tried live, so a gateway that expects a different path needs the stub's route adjusted here, never the gateway.
Stub behaviour worth testing: Postiz refuses type "now" (the real narrow gateway cannot send it either) and enforces 90 requests an hour with a 429;
PBS can answer a fresh, a stale or a failed verification per --pbs-verify (fresh|stale|failed|alternate) and bigger sizes with --pbs-large.
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Stub(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, kind, opts):
        super().__init__(addr, Handler)
        self.kind, self.opts = kind, opts
        self.lock = threading.Lock()
        self.calls = {}
        self.gpu_seconds = 0.0
        self.post_times = []        # postiz: request times inside the hour

    def bump(self, key):
        with self.lock:
            self.calls[key] = self.calls.get(key, 0) + 1

    def snapshot(self):
        with self.lock:
            return {"kind": self.kind, "calls": dict(self.calls), "gpu_seconds": round(self.gpu_seconds, 2)}

    def reset(self):
        with self.lock:
            self.calls.clear()
            self.gpu_seconds = 0.0
            self.post_times.clear()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def out(self, code, obj, ctype="application/json", extra=None):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw) if raw else {}
        except ValueError:
            return {}

    def do_GET(self):
        s = self.server
        path = self.path.split("?")[0]
        if path == "/_counters":
            return self.out(200, s.snapshot())
        getattr(self, "get_" + s.kind)(path)

    def do_POST(self):
        s = self.server
        path = self.path.split("?")[0]
        if path == "/_reset":
            s.reset()
            return self.out(200, {"ok": True})
        getattr(self, "post_" + s.kind)(path, self.body())

    do_PUT = do_DELETE = do_POST

    # --- zabbix: JSON-RPC, invented hosts and items -------------------------------------------------------------------------
    def get_zabbix(self, path):
        self.out(404, {"error": "POST /api_jsonrpc.php"})

    def post_zabbix(self, path, req):
        m = req.get("method", "") if isinstance(req, dict) else ""
        self.server.bump(m or "unknown")
        if m == "user.checkAuthentication" or m == "apiinfo.version":
            res = {"userid": "1"} if m != "apiinfo.version" else "7.0.0"
        elif m == "hostgroup.get":
            res = [{"groupid": "1", "name": "synthetic-shop", "hosts": "2"}]
        elif m == "host.get":
            res = [{"hostid": "10", "host": "web-syn-1", "name": "web-syn-1", "status": "0", "tags": [], "interfaces": [{"available": "1"}]},
                   {"hostid": "20", "host": "db-syn-1", "name": "db-syn-1", "status": "0", "tags": [], "interfaces": [{"available": "1"}]}]
        elif m == "item.get":
            res = [{"itemid": "1", "name": "PHP version", "key_": "php.version", "lastvalue": "8.1.2", "hostid": "10"},
                   {"itemid": "2", "name": "Last backup stamp", "key_": "backup.stamp", "lastvalue": "2026-01-01T03:00:00Z", "hostid": "20"}]
        elif m in ("problem.get", "event.get"):
            res = [{"eventid": "1", "name": "Synthetic problem: disk 91 percent", "severity": "3", "clock": "0", "hosts": [{"hostid": "20", "host": "db-syn-1"}]}]
        else:
            res = []
        self.out(200, {"jsonrpc": "2.0", "result": res, "id": req.get("id", 1) if isinstance(req, dict) else 1})

    # --- postiz: drafts and scheduled posts, "now" refused, 90 requests an hour -------------------------------------------------
    def get_postiz(self, path):
        s = self.server
        s.bump("GET " + ("integrations" if "integrations" in path else "other"))
        if "integrations" in path:
            return self.out(200, [{"id": "ch1", "name": "Synthetic page", "identifier": "facebook", "disabled": False}])
        self.out(200, {"posts": []})

    def post_postiz(self, path, body):
        s = self.server
        now = time.time()
        with s.lock:
            s.post_times = [t for t in s.post_times if now - t < 3600] + [now]
            over = len(s.post_times) > s.opts.get("postiz_hourly", 90)
        if over:
            s.bump("429")
            return self.out(429, {"error": "rate limit"}, extra={"Retry-After": "60"})
        kind = body.get("type", "draft") if isinstance(body, dict) else "draft"
        if kind == "now":
            s.bump("POST now refused")
            return self.out(400, {"error": "type now is not allowed"})
        s.bump("POST " + kind)
        self.out(200, {"id": "p-%d" % s.calls.get("POST " + kind, 0), "status": kind})

    # --- pbs: snapshots, verify, restore test ---------------------------------------------------------------------------------
    def get_pbs(self, path):
        s = self.server
        size = 400 if s.opts.get("pbs_large") else 4      # GiB, invented
        if "snapshots" in path:
            s.bump("snapshots")
            return self.out(200, {"data": [{"backup-type": "vm", "backup-id": "100", "backup-time": 1767225600, "size": size * 2**30,
                                            "verification": {"state": "ok"}}]})
        s.bump("other")
        self.out(200, {"data": []})

    def post_pbs(self, path, body):
        s = self.server
        mode = s.opts.get("pbs_verify", "fresh")
        if "verify" in path:
            s.bump("verify")
            n = s.calls["verify"]
            state = {"fresh": "ok", "stale": "ok", "failed": "failed"}.get(mode, "ok" if n % 2 else "failed")
            return self.out(200, {"data": {"state": state, "stale": mode == "stale"}})
        s.bump("restore-test" if "restore" in path else "other")
        self.out(200, {"data": {"ok": True}})

    # --- audd: one canned song ---------------------------------------------------------------------------------------------------
    def get_audd(self, path):
        self.post_audd(path, {})

    def post_audd(self, path, body):
        self.server.bump("recognize")
        self.out(200, {"status": "success", "result": {"artist": "Synthetic Artist", "title": "Synthetic Song", "album": "Invented"}})

    # --- gpu: image, makevideo; sleeps a configured time and returns a tiny file ----------------------------------------------------
    def get_gpu(self, path):
        self.out(200, {"ok": True}) if path in ("/healthz", "/health") else self.out(404, {"error": "no"})

    def post_gpu(self, path, body):
        s = self.server
        secs = float(s.opts.get("gpu_seconds", 0.3))
        key = "makevideo" if "video" in path else ("image" if "image" in path else "other")
        s.bump(key)
        time.sleep(secs)
        with s.lock:
            s.gpu_seconds += secs
        self.out(200, b"\x89PNG\r\n\x1a\n" + b"0" * 32, ctype="application/octet-stream", extra={"X-Synthetic-Gpu-Seconds": str(secs)})


def start(kind, port, bind="127.0.0.1", **opts):
    """Start one stub in a thread -> the Stub (call .shutdown() to stop it). port 0 picks a free one (read .server_port)."""
    s = Stub((bind, port), kind, opts)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--bind", default="127.0.0.1")
    for k in ("zabbix", "postiz", "pbs", "audd", "gpu"):
        p.add_argument("--" + k, type=int, default=0, help="port; 0 = not started")
    p.add_argument("--gpu-seconds", type=float, default=0.3)
    p.add_argument("--pbs-verify", choices=("fresh", "stale", "failed", "alternate"), default="fresh")
    p.add_argument("--pbs-large", action="store_true")
    p.add_argument("--postiz-hourly", type=int, default=90)
    a = p.parse_args(argv)
    started = []
    for k in ("zabbix", "postiz", "pbs", "audd", "gpu"):
        port = getattr(a, k)
        if port:
            started.append(start(k, port, a.bind, gpu_seconds=a.gpu_seconds, pbs_verify=a.pbs_verify, pbs_large=a.pbs_large, postiz_hourly=a.postiz_hourly))
            print(f"{k} stub on http://{a.bind}:{port} (counts only)", flush=True)
    if not started:
        p.error("give at least one of --zabbix --postiz --pbs --audd --gpu")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
