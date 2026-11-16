#!/usr/bin/env python3
"""Offline test of gpu-host/bench_gate.py: a fake gate (real HTTP on loopback) that keeps a bench, leases and the power limit,
fake service servers, a fake recorder (it answers by the cap the fake gate holds), a fake Resolve MCP session, a fake effectcraft-cli
and a fake clock. Nothing real is touched: no GPU, no nvidia-smi, no Docker, no Resolve, no sleep, no network beyond loopback."""
import contextlib, io, json, os, shutil, signal, subprocess, sys, tempfile, threading, time, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench_gate as bg  # noqa: E402

FAIL = []
TOKEN = "t0ken-for-tests"
SVC_NAMES = ["upscaler", "transcoder", "stt", "llm", "tts", "tts-hq", "imggen", "vidgen", "vidpost", "mosher", "resolve"]


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def silence_wav(seconds, rate=4000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


class Clock:
    def __init__(self):
        self.t = 1000.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeGate:
    """The contract's bench mode in a few lines: state, /bench/*, /wake, /done, /release, /off."""

    def __init__(self, ports, running=None, apps=None, blocked=None, bench_active=False, restore_ok=True):
        self.calls, self.limit, self.found, self.bench, self.lease_n = [], 240.0, None, None, 0
        self.started = 1      # the "started" time the state reports for the bench
        self.svc = {n: {"port": ports.get(n, 8695), "running": False, "leases": 0} for n in SVC_NAMES}
        self.by_port = {s["port"]: n for n, s in self.svc.items()}
        for n in running or []:
            self.svc[n]["running"] = True
        self.blocked, self.bench_other, self.restore_ok = blocked, bench_active, restore_ok
        self.leases = {}
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _handler(self):
        gate = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

            def _do(self, method):
                if self.headers.get("Authorization") != "Bearer " + TOKEN:
                    return self._send(401, {"why": "token"})
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}") if method == "POST" else None
                with gate.lock:
                    gate.calls.append((method, self.path, body))
                    code, obj = gate.handle(method, self.path, body)
                self._send(code, obj)

            def do_GET(self):
                self._do("GET")

            def do_POST(self):
                self._do("POST")
        return H

    def handle(self, method, path, b):
        if (method, path) == ("GET", "/state"):
            return 200, {"gpu": {"name": "NVIDIA GeForce RTX 3060 Ti", "limit_w": self.limit, "default_w": 240, "min_w": 100, "max_w": 250,
                                 "free_mb": 7000}, "blocked": self.blocked, "services": self.svc,
                         "bench": {"id": "other", "watts": 100, "started": 1} if self.bench_other else (
                             {"id": self.bench, "watts": self.limit, "started": self.started} if self.bench else None)}
        if path == "/bench/start":
            if any(s["running"] for s in self.svc.values()):
                return 409, {"why": "busy_jobs"}
            self.bench, self.found, self.limit = "b1", self.limit, min(max(b["watts"], 100), 250)
            return 200, {"bench": "b1"}
        if path == "/bench/watts":
            if b.get("bench") != self.bench:
                return 404, {"why": "unknown_bench"}
            self.limit = min(max(b["watts"], 100), 250)
            return 200, {"ok": True}
        if path == "/bench/end":
            if b.get("bench") != self.bench:
                return 404, {"why": "unknown_bench"}
            self.bench = None
            if self.restore_ok:
                self.limit = self.found
            return 200, {"ok": True}
        if path == "/wake":
            if self.bench and b.get("bench") != self.bench:
                return 409, {"why": "bench"}
            return self._wake(self.by_port[b["port"]], b)
        if path in ("/done",):
            return 200, {"done": 1, "closed": False}
        if path == "/release":
            name = self.leases.pop(b["lease"], None)
            if name:
                self.svc[name].update(running=False, leases=0)
            return 200, {"stopped": [name] if name else []}
        if path == "/off":
            self.svc["resolve"].update(running=False, leases=0)
            return 200, {"stopped": []}
        return 404, {"why": "not_found"}

    def _wake(self, name, b):
        self.lease_n += 1
        lease = f"L{self.lease_n}"
        self.leases[lease] = name
        self.svc[name].update(running=True, leases=1)
        return 202, {"lease": lease, "running": False, "eta_s": 1, **({"go": True} if name == "resolve" else {})}

    def ops(self):
        return [(m, p) for m, p, _ in self.calls]


class FakeServices:
    """One small HTTP server per service name (the fake gate reports each one's port); hits are shared."""

    def __init__(self, names=("stt", "tts", "tts-hq", "upscaler", "transcoder", "vidpost", "imggen", "vidgen")):
        outer = self
        self.hits = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)

            def do_GET(self):
                self._send(200, b"ok", "text/plain")

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                data = self.rfile.read(n)
                outer.hits.append(self.path.split("?")[0])
                if self.path == "/v1/audio/speech":
                    lang = json.loads(data).get("language")
                    return self._send(200, silence_wav(2 if lang else 60), "audio/wav")
                if self.path.startswith("/transcribe"):
                    return self._send(200, json.dumps({"text": "hola", "audio_seconds": 180.0}).encode())
                self._send(200, b"x" * 10, "application/octet-stream")
        self.ports = {}
        for n in names:
            srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
            self.ports[n] = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()


WALL = {100: 20.0, 130: 15.0, 160: 14.0, 200: 13.5, 240: 13.4, 250: 13.4}


class FakeNv:
    def __init__(self, gate, apps=None):
        self.gate, self.apps = gate, apps or ["777, /usr/bin/sunshine, 136", "778, /opt/google/chrome/chrome --type=gpu-process, 64"]

    def limit_w(self):
        return self.gate.limit

    def mem_used_mib(self):
        return 600.0

    def compute_apps(self):
        return self.apps


def fake_measure_for(gate, seen, fail_on=None):
    def measure(tag, fn, unit="job"):
        seen.append((tag, gate.limit))
        if fail_on and fail_on(tag, len(seen)):
            raise fail_on.exc
        try:
            ret = fn()
            ok, err = True, None
        except Exception as e:
            ret, ok, err = None, False, str(e)
        cap = gate.limit
        wall = WALL.get(int(cap), 14.0)
        avg = cap * 0.9
        res = {"tag": tag, "ok": ok, "err": err, "wall_s": wall, "gpu_idle_w": 15.0, "gpu_avg_w": avg, "gpu_peak_w": cap,
               "gpu_wh": round(avg * wall / 3600, 4), "gpu_net_wh": round((avg - 15) * wall / 3600, 4),
               "vram_peak_mib": 600 if tag.startswith("effectcraft") else 1900, "gpu_util_avg": 50.0, "cpu_busy_core_s": 4.0, "samples": 20}
        if isinstance(ret, (int, float)) and ret > 0:
            res["ret"] = float(ret)
        return res
    return measure


class FakeMedia:
    def __init__(self, d):
        self.d = d

    def _f(self, name):
        os.makedirs(self.d, exist_ok=True)
        p = os.path.join(self.d, name)
        open(p, "wb").write(b"fake media")
        return p

    def video(self, kind):
        return self._f(kind + ".mp4")

    def png(self):
        return self._f("up.png")


class FakeMcp:
    """What resolve_session does on its first tool call: /wake with the bench id from the environment."""
    sessions = []

    def __init__(self, gate, argv, env):
        self.gate, self.argv, self.env, self.calls, self.woke = gate, argv, env, [], False
        self.out = {}
        FakeMcp.sessions.append(self)

    def initialize(self, timeout=300):
        self.calls.append("initialize")

    def tool(self, name, action, params=None, timeout=300):
        if not self.woke:
            self.woke = True
            b = {"port": self.gate.svc["resolve"]["port"], "stack": self.env["RESOLVE_GATE_STACK"], "mode": "interactive",
                 "bench": self.env["RESOLVE_GATE_BENCH"]}
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:{self.gate.port}/wake", json.dumps(b).encode(), method="POST",
                                         headers={"Authorization": "Bearer " + TOKEN})
            urllib.request.urlopen(req).read()
        self.calls.append(f"{name}.{action}")
        if (name, action) == ("folder", "get_clips"):
            return {"clips": [{"clip_id": "abcdef12-3456-7890"}]}, False
        if (name, action) == ("render", "set_settings"):
            self.out = params["settings"]
        if (name, action) == ("render", "start"):
            open(os.path.join(self.out["TargetDir"], self.out["CustomName"] + ".mp4"), "wb").write(b"mp4")
        if (name, action) == ("render", "is_rendering"):
            return {"rendering": False}, False
        return {"success": True}, False

    def close(self, wait_s=90):
        self.calls.append("close")
        self.gate.svc["resolve"].update(running=False, leases=0)


def fake_run(cmd, **kw):
    """effectcraft-cli: create the files a real call would."""
    args = list(cmd)
    if "--save-as" in args:
        open(args[args.index("--save-as") + 1], "wb").write(b"proj")
    elif "render" in args and "--out" in args:
        open(args[args.index("--out") + 1], "wb").write(b"mp4")
    return subprocess.CompletedProcess(cmd, 0, "{}", "")


def run_main(argv, gate, svc, tmp, apps=None, measure=None, services_port=None, env=None, unlock=None, clock=None):
    clock = clock or Clock()
    unlock_path = os.path.join(tmp, "no_such_unlock_file")
    if unlock is not None:
        os.makedirs(tmp, exist_ok=True)
        unlock_path = os.path.join(tmp, "unlock_targets")
        open(unlock_path, "w").write(unlock + "\n")
    seen = []
    deps = {"gate": bg.Gate(f"http://127.0.0.1:{gate.port}", TOKEN), "nv": FakeNv(gate, apps),
            "measure": measure or fake_measure_for(gate, seen), "env": env or {"GATE_TOKEN": TOKEN},
            "home": os.path.join(tmp, "home"), "videos": os.path.join(tmp, "zz_bench"), "sleep": clock.sleep, "now": clock.now,
            "media": FakeMedia(os.path.join(tmp, "media")), "run": fake_run, "resolve_dispatch": "/nonexistent/mcp_dispatch.sh",
            "mcp_factory": lambda argv_, env_: FakeMcp(gate, argv_, env_), "unlock_path": unlock_path}
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = bg.main(argv, deps)
        except BaseException as e:      # a bug inside the run: the caller checks the finally block anyway
            rc = e
    return rc, out.getvalue(), err.getvalue(), seen


def new_gate(svc, **kw):
    g = FakeGate(svc.ports, **kw)
    return g


def main():
    svc = FakeServices()
    root = tempfile.mkdtemp(prefix="bench_gate_selftest-")

    # --- the recommendation rule -------------------------------------------------------------------------------------------
    def rows(*data):
        return [{"cap_w": c, "n_ok": 3, "n": 3, "rec_wh": wh, "rec_s": s, "wall_s": s, "wh": wh} for c, wh, s in data]

    pick, why = bg.recommend(rows((100, 1.00, 20), (130, 1.05, 15), (160, 1.20, 14)))
    check("rule: +5 % Wh and 25 % faster takes the faster cap", pick["cap_w"], 130)
    pick, _ = bg.recommend(rows((100, 1.00, 20), (130, 1.05, 18), (160, 1.20, 14)))
    check("rule: only 10 % faster stays at the lowest Wh", pick["cap_w"], 100)
    pick, _ = bg.recommend(rows((100, 1.00, 20), (130, 1.12, 15)))
    check("rule: +12 % Wh is too much", pick["cap_w"], 100)
    pick, _ = bg.recommend(rows((100, 1.00, 20), (130, 0.90, 19), (160, 0.98, 12)))
    check("rule: lowest Wh is the base, the fast one wins within +10 % of it", pick["cap_w"], 160)
    pick, _ = bg.recommend(rows((100, 0.0304, 3.0), (130, 0.030, 3.0), (240, 0.0305, 3.0)))
    check("rule: Wh within 2 % is a tie, lower cap", pick["cap_w"], 100)
    pick, why = bg.recommend([{"cap_w": 100, "n_ok": 0, "n": 3}])
    check("rule: nothing measured", (pick, why), (None, "no usable measurement"))
    pick, _ = bg.recommend([dict(r, cap_ok=(r["cap_w"] != 100)) for r in rows((100, 0.5, 20), (130, 1.0, 15))])
    check("rule: a cap the card did not confirm is left out", pick["cap_w"], 130)
    check("vram need = peak above baseline + 15 %, rounded up to 10", bg.vram_need_mb(2000, 600), 1610)
    check("clamp and dedupe caps", bg.clamp_caps([50, 100, 130, 300], 100, 250), [100, 130, 250])
    s = bg.summarise(130, [{"ok": True, "wall_s": 10, "gpu_wh": 1.0, "gpu_net_wh": 0.8, "gpu_avg_w": 90, "gpu_peak_w": 130,
                            "vram_peak_mib": 900, "ret": 2.0}, {"ok": True, "wall_s": 20, "gpu_wh": 3.0, "gpu_net_wh": 2.0, "gpu_avg_w": 95,
                                                                "gpu_peak_w": 130, "vram_peak_mib": 950, "ret": 4.0}, {"ok": False, "err": "x"}],
                     "gpu_wh", "audio_s")
    check("summary: median per job, per unit when every run has one, failed run counted",
          (s["n_ok"], s["n"], s["wall_s"], s["wh"], s["rec_wh"], s["rec_s"], s["vram_peak_mib"]), (2, 3, 15.0, 2.0, 0.625, 5.0, 950))
    check("compute apps: desktop ones pass, a job does not",
          (bg.check_compute_apps(["1, /usr/bin/sunshine, 136"]), len(bg.check_compute_apps(["2, /opt/conda/bin/python3, 5800"])),
           len(bg.check_compute_apps(["3, /opt/chrome/chrome, 900"]))), ([], 1, 1))
    check("env parse: quotes and export, no sourcing", (lambda p: (open(p, "w").write("export A='x y'\nB=2 #c\n#C=3\nbad line\n"),
                                                                   bg.parse_env_file(p))[1])(os.path.join(root, "e.env")), {"A": "x y", "B": "2 #c"})

    # --- task selection and dry-run ---------------------------------------------------------------------------------------
    check("tasks: default four", bg.select_tasks(None, False), ["stt", "tts-hq", "resolve", "effectcraft"])
    check("tasks: --recheck adds the five", bg.select_tasks(None, True)[4:], ["upscaler", "transcoder", "vidpost", "imggen", "vidgen"])
    try:
        bg.select_tasks("imggen", False)
        check("tasks: a re-check task needs --recheck", "accepted", "SystemExit")
    except SystemExit:
        check("tasks: a re-check task needs --recheck", "SystemExit", "SystemExit")
    g0 = new_gate(svc)
    rc, out, err, _ = run_main(["--dry-run", "--recheck"], g0, svc, os.path.join(root, "dry"))
    check("dry-run: exit 0", rc, 0)
    check("dry-run: prints a plan with minutes for every task", ("est. min" in out, all(t in out for t in bg.ORDER), "total" in out), (True, True, True))
    check("dry-run: no call to the gate, no file written", (g0.calls, os.path.exists(os.path.join(root, "dry", "home"))), ([], False))

    # --- pre-flight refusals: nothing may be changed ------------------------------------------------------------------------
    for label, kw, apps in [("a service running", {"running": ["vidgen"]}, None), ("the gate blocked", {"blocked": "vr"}, None),
                            ("another bench", {"bench_active": True}, None),
                            ("a person's job on the card", {}, ["99, /opt/conda/bin/python3, 5800"])]:
        g = new_gate(svc, **kw)
        rc, out, err, seen = run_main(["--tasks", "stt"], g, svc, os.path.join(root, "pf"), apps=apps)
        check(f"pre-flight refuses {label}: exit 2, only GET /state, nothing measured",
              (rc, g.ops(), seen, "Pre-flight refused" in err), (2, [("GET", "/state")], [], True))

    # --- bench start refused by the gate -------------------------------------------------------------------------------------
    g = new_gate(svc)
    g.handle_orig = g.handle
    g.handle = lambda m, p, b: (409, {"why": "busy_jobs"}) if p == "/bench/start" else g.handle_orig(m, p, b)
    rc, out, err, seen = run_main(["--tasks", "stt"], g, svc, os.path.join(root, "bs"))
    check("bench/start refused: exit 3, no bench/end, nothing measured", (rc, ("POST", "/bench/end") in g.ops(), seen), (3, False, []))

    # --- a full run of the four default tasks ----------------------------------------------------------------------------------
    FakeMcp.sessions = []
    g = new_gate(svc)
    tmp = os.path.join(root, "full")
    rc, out, err, seen = run_main(["--caps", "100,130", "--reps", "2", "--stt-secs", "170"], g, svc, tmp)
    ops = g.ops()
    check("full run: exit 0", rc, 0)
    check("full run: pre-flight GET /state, then /bench/start first", ops[:2], [("GET", "/state"), ("POST", "/bench/start")])
    check("full run: /bench/end is the last bench call and the limit is restored",
          ([p for m, p in ops if p.startswith("/bench/")][-1], g.limit, g.bench), ("/bench/end", 240.0, None))
    wakes = [b for m, p, b in g.calls if p == "/wake"]
    check("every wake carries the bench id and stack 'bench' (stt's tts, stt, tts-hq, resolve sessions)",
          (len(wakes), all(w.get("bench") == "b1" and w.get("stack") == "bench" for w in wakes)), (3 + len(FakeMcp.sessions), True))
    check("docker services are woken in batch mode with a batch id", [w["mode"] for w in wakes if w["mode"] != "interactive"],
          ["batch"] * 3)
    check("resolve sessions: env carries stack and bench id, warm-up + 2 caps x 2 reps",
          (len(FakeMcp.sessions), {(s.env["RESOLVE_GATE_STACK"], s.env["RESOLVE_GATE_BENCH"]) for s in FakeMcp.sessions}),
          (5, {("bench", "b1")}))
    check("resolve session order of calls", FakeMcp.sessions[0].calls[:5],
          ["initialize", "project_manager.delete", "project_manager.create", "media_pool.safe_import_media", "folder.get_clips"])
    check("resolve sessions end with project delete and close", FakeMcp.sessions[0].calls[-2:], ["project_manager.delete", "close"])
    watts = [b["watts"] for m, p, b in g.calls if p == "/bench/watts"]
    check("watts per cap: warm-up at the first cap then the sweep, per task (stt, tts-hq, resolve), effectcraft at the default",
          watts, [100, 100, 130, 100, 100, 130, 100, 100, 130, 240])
    check("measured in order, at the cap the gate held",
          [(t, c) for t, c in seen if t.startswith("stt")], [("stt-warmup", 100.0), ("stt-100W", 100.0), ("stt-100W", 100.0),
                                                              ("stt-130W", 130.0), ("stt-130W", 130.0)])
    check("every service is released (stopped) before the next task: nothing left running",
          [n for n, s in g.svc.items() if s["running"]], [])
    check("services were hit: tts for the clip, stt, tts-hq", ("/v1/audio/speech" in svc.hits, "/transcribe" in svc.hits), (True, True))
    lines = [json.loads(l) for l in open(os.path.join(tmp, "home", "results.jsonl"))]
    kinds = [l["kind"] for l in lines]
    check("results.jsonl: session, cap rows, task and recommend lines, all with the bench id",
          (kinds[0], kinds.count("cap"), kinds.count("recommend"), {l["bench"] for l in lines}), ("session", 7, 4, {"b1"}))
    check("temporary files removed", (os.path.exists(os.path.join(tmp, "home", "tmp")), os.path.exists(os.path.join(tmp, "zz_bench"))), (False, False))
    check("summary: recommended cap for stt by the rule (130 W: lowest Wh)", "recommended cap: 130 W" in out, True)
    check("summary: proposed power_profiles lines and the section", ("stt = 130" in out, "[RTX 3060 Ti]" in out, "tts-hq = 130" in out), (True, True, True))
    check("summary: VRAM need printed", "need + 15 % = " in out, True)
    check("summary: effectcraft is judged CPU only (VRAM unchanged)", "CPU only, VRAM ~0" in out, True)
    check("summary: nothing edited", "Proposed (nothing is edited)" in out, True)
    check("power limit confirmed back", "power limit back at 240 W" in out, True)
    full_out = out

    # --- clamp to the card range ----------------------------------------------------------------------------------------------
    g = new_gate(svc)
    rc, out, err, seen = run_main(["--tasks", "upscaler", "--recheck", "--caps", "50,100,300", "--reps", "1"], g, svc, os.path.join(root, "clamp"),
                                  env={"GATE_TOKEN": TOKEN})
    check("clamp: upscaler without UPSCALE_TOKEN still runs (token optional), caps 100 and 250 only",
          (rc, [b["watts"] for m, p, b in g.calls if p == "/bench/watts"]), (0, [100, 100, 250]))
    g = new_gate(svc)
    rc, out, err, seen = run_main(["--tasks", "imggen", "--recheck", "--caps", "100", "--reps", "1"], g, svc, os.path.join(root, "tok"))
    check("a required service token missing: the task is skipped before any wake, bench still ended",
          (rc, [b for m, p, b in g.calls if p == "/wake"], ("POST", "/bench/end") in g.ops(), "IMAGE_TOKEN is not set" in out), (1, [], True, True))

    # --- bench/end even on exceptions ---------------------------------------------------------------------------------------
    def boom(exc, at):
        f = lambda tag, n: n == at
        f.exc = exc
        return f
    g = new_gate(svc)
    seen = []
    rc, out, err, _ = run_main(["--tasks", "stt,tts-hq", "--caps", "100,130", "--reps", "1"], g, svc, os.path.join(root, "ki"),
                               measure=fake_measure_for(g, seen, boom(KeyboardInterrupt(), 4)))
    check("Ctrl-C mid-run: bench/end sent, limit restored, exit 1, service released",
          (rc, ("POST", "/bench/end") in g.ops(), g.limit, g.bench, [n for n, s in g.svc.items() if s["running"]]), (1, True, 240.0, None, []))
    g = new_gate(svc)
    seen = []
    rc, out, err, _ = run_main(["--tasks", "stt", "--caps", "100", "--reps", "1"], g, svc, os.path.join(root, "bug"),
                               measure=fake_measure_for(g, seen, boom(ValueError("bug in a task"), 2)))
    check("unexpected exception: it propagates but bench/end was sent, limit restored, service released",
          (isinstance(rc, ValueError), ("POST", "/bench/end") in g.ops(), g.limit, [n for n, s in g.svc.items() if s["running"]]),
          (True, True, 240.0, []))

    # --- B5: gpu-unlock state on every result line, pre-flight print, summary warning ------------------------------------------
    check("full run: gpu-unlock absent reads \"off\" on every result line", {l["gpu_unlock"] for l in lines}, {"off"})
    check("full run: pre-flight prints gpu-unlock off, summary warns about imggen/vidgen",
          ("gpu-unlock: off" in full_out, "WARNING: gpu-unlock was off" in full_out), (True, True))
    check("gpu-unlock reader: absent, empty, value",
          (bg.read_gpu_unlock(os.path.join(root, "none")), (lambda p: (open(p, "w").write("\n"), bg.read_gpu_unlock(p))[1])(os.path.join(root, "u0")),
           (lambda p: (open(p, "w").write("1\n"), bg.read_gpu_unlock(p))[1])(os.path.join(root, "u1"))), ("off", "off", "1"))
    g = new_gate(svc)
    rc, out, err, _ = run_main(["--tasks", "tts-hq", "--caps", "100", "--reps", "1"], g, svc, os.path.join(root, "unl"), unlock="1")
    ulines = [json.loads(l) for l in open(os.path.join(root, "unl", "home", "results.jsonl"))]
    check("gpu-unlock on: value on every line, no warning", (rc, {l["gpu_unlock"] for l in ulines}, "gpu-unlock: 1" in out, "WARNING: gpu-unlock" in out),
          (0, {"1"}, True, False))

    # --- B4: a JSON-RPC error is a failure, not a success ------------------------------------------------------------------------
    echo = ("import sys, json\n"
            "for line in sys.stdin:\n"
            "    m = json.loads(line)\n"
            "    if 'id' not in m: continue\n"
            "    a = m['params']['arguments']['action']\n"
            "    if a == 'rpc_error': r = {'error': {'code': -32000, 'message': 'gate refused: vr'}}\n"
            "    elif a == 'tool_error': r = {'result': {'isError': True, 'content': [{'type': 'text', 'text': '{\"success\": false}'}]}}\n"
            "    else: r = {'result': {'content': [{'type': 'text', 'text': '{\"success\": true}'}]}}\n"
            "    print(json.dumps(dict(r, jsonrpc='2.0', id=m['id'])), flush=True)\n")
    ms = bg.McpSession([sys.executable, "-c", echo], dict(os.environ))
    try:
        ok_data, ok_bad = ms.tool("project_manager", "create", {"name": "x"})
        _, tool_bad = ms.tool("project_manager", "tool_error")
        try:
            ms.tool("project_manager", "rpc_error")
            raised = None
        except RuntimeError as e:
            raised = str(e)
        check("MCP tool(): success is ok, isError is bad=True, a JSON-RPC error raises with its message",
              (ok_bad, tool_bad, raised and "gate refused: vr" in raised), (False, True, True))
    finally:
        ms.close(wait_s=10)

    # --- B1: SIGHUP ends the bench like SIGTERM, handlers restored ---------------------------------------------------------------
    g = new_gate(svc)
    seen = []
    base_measure = fake_measure_for(g, seen)
    during = {}

    def hup_measure(tag, fn, unit="job"):
        if len(seen) == 2:
            during["hup"] = signal.getsignal(signal.SIGHUP)
            during["term"] = signal.getsignal(signal.SIGTERM)
            os.kill(os.getpid(), signal.SIGHUP)
            time.sleep(0.2)                      # the handler runs in the main thread, here
        return base_measure(tag, fn, unit)
    before = (signal.getsignal(signal.SIGHUP), signal.getsignal(signal.SIGTERM))
    rc, out, err, _ = run_main(["--tasks", "stt,tts-hq", "--caps", "100,130", "--reps", "1"], g, svc, os.path.join(root, "hup"),
                               measure=hup_measure)
    check("SIGHUP mid-run: same handler as SIGTERM, bench/end sent, limit restored, exit 1, nothing running",
          (rc, during.get("hup") is not None and during.get("hup") is during.get("term"), ("POST", "/bench/end") in g.ops(), g.bench, g.limit,
           [n for n, x in g.svc.items() if x["running"]]), (1, True, True, None, 240.0, []))
    check("signal handlers restored after the run", (signal.getsignal(signal.SIGHUP), signal.getsignal(signal.SIGTERM)), before)

    # --- under nohup (SIGHUP ignored) a dropped session does not stop the run ---------------------------------------------------
    g = new_gate(svc)
    seen = []
    base_measure = fake_measure_for(g, seen)
    during = {}

    def nohup_measure(tag, fn, unit="job"):
        if len(seen) == 2:
            during["hup"] = signal.getsignal(signal.SIGHUP)
            os.kill(os.getpid(), signal.SIGHUP)
            time.sleep(0.2)
        return base_measure(tag, fn, unit)
    prev_hup = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        rc, out, err, _ = run_main(["--tasks", "stt,tts-hq", "--caps", "100,130", "--reps", "1"], g, svc, os.path.join(root, "nohup"),
                                   measure=nohup_measure)
        check("under nohup: SIGHUP stays ignored, the run completes, bench ended, limit restored",
              (rc, during.get("hup") == signal.SIG_IGN, ("POST", "/bench/end") in g.ops(), g.bench, g.limit, signal.getsignal(signal.SIGHUP)),
              (0, True, True, None, 240.0, signal.SIG_IGN))
    finally:
        signal.signal(signal.SIGHUP, prev_hup)

    # --- B1: /bench/start with no answer in time: end the bench the gate may have created ----------------------------------------
    old_to = bg.BENCH_START_TIMEOUT
    bg.BENCH_START_TIMEOUT = 0.4
    try:
        for label, started, ended in [("young bench", 990, True), ("old bench", 1, False)]:
            g = new_gate(svc)
            g.started = started
            g.handle_orig = g.handle

            def slow_start(m, p, b, g=g):
                r = g.handle_orig(m, p, b)
                if p == "/bench/start":
                    time.sleep(1.2)              # the answer arrives after the client gave up (the lock is held, so GET /state waits)
                return r
            g.handle = slow_start
            rc, out, err, seen = run_main(["--tasks", "stt"], g, svc, os.path.join(root, "slow_" + label.split()[0]))
            check(f"/bench/start timeout, {label}: exit 3, nothing measured, bench ended only if young, clear message",
                  (rc, seen, ("POST", "/bench/end") in g.ops(), g.bench is None, "bench start failed" in err,
                   ("ended it" in err) if ended else ("no bench of this run" in err)), (3, [], ended, ended, True, True))
            if ended:
                check("/bench/start timeout: the limit is restored by the gate's /bench/end", g.limit, 240.0)
    finally:
        bg.BENCH_START_TIMEOUT = old_to

    # --- B2: a person's session appears, or the bench is gone: stop cleanly, say which task and cap -------------------------------
    for label, at, what in [("before a cap", 3, "cap 130 W"), ("before a job", 2, "job stt-100W")]:
        g = new_gate(svc)
        seen = []
        base_measure = fake_measure_for(g, seen)

        def block_measure(tag, fn, unit="job", at=at, g=g, seen=seen, base_measure=base_measure):
            if len(seen) == at - 1:
                g.blocked = "vr"
            return base_measure(tag, fn, unit)
        rc, out, err, _ = run_main(["--tasks", "stt,tts-hq", "--caps", "100,130", "--reps", "2"], g, svc, os.path.join(root, "blk" + str(at)),
                                   measure=block_measure)
        wk = [b for m, p, b in g.calls if p == "/wake"]
        check(f"blocked appears {label}: exit 1, names the task and {what}, no further measure or wake",
              (rc, f"interrupted in task stt at {what}" in out + err, len(seen), len(wk)), (1, True, at, 2))
        check(f"blocked appears {label}: bench ended, limit restored, services released, no cap set after it",
              (("POST", "/bench/end") in g.ops(), g.bench, g.limit, [n for n, x in g.svc.items() if x["running"]],
               [b["watts"] for m, p, b in g.calls if p == "/bench/watts"][-1:] != [130] or at == 2), (True, None, 240.0, [], True))
    g = new_gate(svc)
    seen = []
    base_measure = fake_measure_for(g, seen)

    def gone_measure(tag, fn, unit="job"):
        if len(seen) == 1:
            g.bench = None                       # expired on the gate
        return base_measure(tag, fn, unit)
    rc, out, err, _ = run_main(["--tasks", "stt,tts-hq", "--caps", "100,130", "--reps", "1"], g, svc, os.path.join(root, "gone"),
                               measure=gone_measure)
    check("bench gone mid-run: exit 1, interrupted message, stt service released, tts-hq never woken, /bench/end tolerated",
          (rc, "the bench is gone" in out, len(seen), [n for n, x in g.svc.items() if x["running"]],
           "already gone" in out), (1, True, 2, [], True))
    # the unknown_bench answer of /bench/watts alone (state still shows the bench) also stops the run
    g = new_gate(svc)
    gctx = bg.Ctx(bg.parse_args(["--tasks", "stt"], home=os.path.join(root, "w1"), videos=os.path.join(root, "w1v")), bg.Gate(f"http://127.0.0.1:{g.port}", TOKEN),
                  FakeNv(g), None, {}, os.path.join(root, "w1"), os.path.join(root, "w1v"), sleep=lambda s_: None)
    gctx.bench_id, gctx.task = "b1", "stt"
    real_guard = bg.guard
    bg.guard = lambda ctx, what: None
    try:
        try:
            bg.set_cap(gctx, 130)
            raised = None
        except bg.Interrupted as e:
            raised = str(e)
    finally:
        bg.guard = real_guard
    check("/bench/watts 404 unknown_bench stops the run, names task and cap", raised, "interrupted in task stt at cap 130 W: the bench is gone (unknown_bench)")

    # --- B3: the EffectCraft GPU evaluation runs only inside this run's active bench ----------------------------------------------
    g = new_gate(svc)
    seen = []
    rc, out, err, _ = run_main(["--tasks", "effectcraft", "--effectcraft-gpu-eval", "--eval-cap", "130", "--reps", "1"], g, svc,
                               os.path.join(root, "ev"), measure=fake_measure_for(g, seen))
    evl = [json.loads(l) for l in open(os.path.join(root, "ev", "home", "results.jsonl"))]
    ev = [l for l in evl if l["kind"] == "evaluation"]
    check("gpu eval inside the bench: recorded once, labelled, with VRAM peak and W, bench id on the line",
          (rc, len(ev), ev and ev[0]["label"], ev and ev[0]["vram_peak_mib"], ev and ev[0]["gpu_peak_w"] is not None, ev and ev[0]["bench"]),
          (0, 1, "evaluation, EffectCraft stays CPU-only in production", 600, True, "b1"))
    check("gpu eval: after /bench/start, at the eval cap set through the gate, /bench/end last",
          (g.ops().index(("POST", "/bench/start")) < [i for i, (m, p) in enumerate(g.ops()) if p == "/bench/watts"][-1],
           [b["watts"] for m, p, b in g.calls if p == "/bench/watts"][-1], g.ops()[-1]), (True, 130, ("POST", "/bench/end")))
    check("gpu eval: summary carries the label and the CPU-only verdict is unchanged",
          ("evaluation, EffectCraft stays CPU-only in production" in out, "CPU only, VRAM ~0" in out), (True, True))
    # refused outside an active bench: no bench id, or the bench is not the gate's current one
    for label, bench_id, gate_bench in [("no bench of this run", None, None), ("bench ended on the gate", "b1", None), ("another bench active", "b1", "zz")]:
        g = new_gate(svc)
        g.bench = gate_bench
        calls = []
        ectx = bg.Ctx(bg.parse_args(["--tasks", "effectcraft", "--effectcraft-gpu-eval"], home=os.path.join(root, "r1"), videos=os.path.join(root, "r1v")),
                      bg.Gate(f"http://127.0.0.1:{g.port}", TOKEN), FakeNv(g), lambda *a: calls.append(("measure", a)) or {}, {},
                      os.path.join(root, "r1"), os.path.join(root, "r1v"), sleep=lambda s_: None,
                      run=lambda *a, **k: calls.append(("run", a)) or subprocess.CompletedProcess(a, 0, "{}", ""))
        ectx.bench_id = bench_id
        res = bg.result_shell("effectcraft", "cpu")
        try:
            bg.effectcraft_gpu_eval(ectx, res, "cli", [])
            got = "ran"
        except bg.TaskError as e:
            got = "refused" if str(e).startswith("refused:") else str(e)
        check(f"gpu eval refused ({label}): nothing run or measured, no cap set",
              (got, calls, [p for m, p in g.ops() if p == "/bench/watts"]), ("refused", [], []))
    try:
        bg.main(["--tasks", "stt", "--effectcraft-gpu-eval", "--dry-run"], {})
        got = "accepted"
    except SystemExit as e:
        got = "SystemExit" if "effectcraft" in str(e) else str(e)
    check("--effectcraft-gpu-eval without the effectcraft task is rejected", got, "SystemExit")

    # --- the limit is not back after bench/end ----------------------------------------------------------------------------------
    g = new_gate(svc, restore_ok=False)
    rc, out, err, _ = run_main(["--tasks", "stt", "--caps", "100", "--reps", "1"], g, svc, os.path.join(root, "lim"))
    check("limit not restored by the gate: warning with the manual command, exit 4, no write by the script",
          (rc, "WARNING: power limit is" in out and "sudo -n /usr/bin/nvidia-smi -pl 240" in out), (4, True))

    # --- the token never appears in any output --------------------------------------------------------------------------------------
    check("the gate token is never printed", TOKEN in (out + err), False)

    shutil.rmtree(root, ignore_errors=True)
    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED: " + ", ".join(FAIL))
        sys.exit(1)
    print("all bench_gate checks passed")


if __name__ == "__main__":
    main()
