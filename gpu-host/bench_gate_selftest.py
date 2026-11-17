#!/usr/bin/env python3
"""Offline test of gpu-host/bench_gate.py: a fake gate (real HTTP on loopback) that keeps a bench, leases and the power limit,
fake service servers, a fake recorder (it answers by the cap the fake gate holds), a fake Resolve MCP session, a fake effectcraft-cli
and a fake clock. Nothing real is touched: no GPU, no nvidia-smi, no Docker, no Resolve, no sleep, no network beyond loopback."""
import contextlib, hashlib, io, json, os, shutil, signal, subprocess, sys, tempfile, threading, time, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench_gate as bg  # noqa: E402

FAIL = []
TOKEN = "t0ken-for-tests"
BENCH_TOKEN = "b3nch-token-for-tests"
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
                want = BENCH_TOKEN if self.path.startswith("/bench/") else TOKEN     # /bench/* takes only the bench token
                if self.headers.get("Authorization") != "Bearer " + want:
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
        self.bodies = []

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
                if self.path in ("/image", "/video"):      # the output depends on the request (prompt and seed), like a real render
                    outer.bodies.append(json.loads(data))
                    return self._send(200, hashlib.sha256(data).digest(), "application/octet-stream")
                self._send(200, b"x" * 10, "application/octet-stream")
        self.ports = {}
        for n in names:
            srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
            self.ports[n] = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()


TOP = {}
WALL = {100: 20.0, 130: 15.0, 160: 14.0, 200: 13.5, 240: 13.4, 250: 13.4}


class FakeNv:
    """nvidia-smi as the bench sees it. `snap` is what snapshot() answers (override per test)."""

    def __init__(self, gate, apps=None):
        self.gate, self.apps = gate, apps or ["777, /usr/bin/sunshine, 136", "778, /opt/google/chrome/chrome --type=gpu-process, 64"]
        self.snap = {"temp_c": 47.0, "sm_mhz": 210.0, "util": 0.0, "throttle": 0x1, "enc_sessions": 0.0}

    def limit_w(self):
        return self.gate.limit

    def mem_used_mib(self):
        return 600.0

    def compute_apps(self):
        return self.apps

    def driver(self):
        return "595.71.05"

    def snapshot(self):
        return dict(self.snap, limit_w=self.gate.limit)


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
               "gpu_net18_wh": round(max(0.0, avg - 18) * wall / 3600, 4),
               "vram_peak_mib": 600 if tag.startswith("effectcraft") else 1900, "gpu_util_avg": 50.0, "cpu_busy_core_s": 4.0, "samples": int(wall * 2)}
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
    if args[:1] == ["docker"]:                      # the environment snapshot: image id, model file sizes, ComfyUI version
        if args[1] == "inspect":
            return subprocess.CompletedProcess(cmd, 0, "sha256:0123456789abcdef0123\n", "")
        if "find" in args:
            names = [a for i, a in enumerate(args) if i and args[i - 1] == "-name" or a.endswith(".safetensors")]
            return subprocess.CompletedProcess(cmd, 0, "".join(f"{n} {1000 + i}\n" for i, n in enumerate(dict.fromkeys(names))), "")
        if "cat" in args:
            return subprocess.CompletedProcess(cmd, 0, '__version__ = "0.9.9"\n', "")
        if args[1] == "top":                            # the service container's host PIDs (TOP[name]); docker fails when a test has none
            if args[2] in TOP:
                return subprocess.CompletedProcess(cmd, 0, "PID\n" + "".join(f"{p}\n" for p in TOP[args[2]]), "")
            return subprocess.CompletedProcess(cmd, 1, "", "")
        return subprocess.CompletedProcess(cmd, 1, "", "")
    if "--save-as" in args:
        open(args[args.index("--save-as") + 1], "wb").write(b"proj")
    elif "render" in args and "--out" in args:
        open(args[args.index("--out") + 1], "wb").write(b"mp4")
    return subprocess.CompletedProcess(cmd, 0, "{}", "")


def run_main(argv, gate, svc, tmp, apps=None, measure=None, services_port=None, env=None, unlock=None, clock=None, nv=None, cpu_dir=None):
    clock = clock or Clock()
    unlock_path = os.path.join(tmp, "no_such_unlock_file")
    if unlock is not None:
        os.makedirs(tmp, exist_ok=True)
        unlock_path = os.path.join(tmp, "unlock_targets")
        open(unlock_path, "w").write(unlock + "\n")
    seen = []
    deps = {"gate": bg.Gate(f"http://127.0.0.1:{gate.port}", TOKEN, bench_token=BENCH_TOKEN), "nv": nv or FakeNv(gate, apps),
            "measure": measure or fake_measure_for(gate, seen), "env": env or {"GATE_TOKEN": TOKEN, "GATE_BENCH_TOKEN": BENCH_TOKEN},
            "home": os.path.join(tmp, "home"), "videos": os.path.join(tmp, "zz_bench"), "sleep": clock.sleep, "now": clock.now,
            "media": FakeMedia(os.path.join(tmp, "media")), "run": fake_run, "resolve_dispatch": "/nonexistent/mcp_dispatch.sh",
            "mcp_factory": lambda argv_, env_: FakeMcp(gate, argv_, env_), "unlock_path": unlock_path,
            "cpu_dir": cpu_dir or os.path.join(tmp, "no_such_cpufreq")}
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
                                  env={"GATE_TOKEN": TOKEN, "GATE_BENCH_TOKEN": BENCH_TOKEN})
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
    gctx = bg.Ctx(bg.parse_args(["--tasks", "stt"], home=os.path.join(root, "w1"), videos=os.path.join(root, "w1v")), bg.Gate(f"http://127.0.0.1:{g.port}", TOKEN, bench_token=BENCH_TOKEN),
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

    # --- D1: the pre-flight reads the program's own name, not a path inside an argument ---------------------------------------------
    chrome = ("2642, /opt/google/chrome/chrome --type=gpu-process --crashpad-handler-pid=2590 --enable-crash-reporter=,Debian "
              "--change-stack-guard-on-fork=enable --gpu-preferences=UAAAAAAAAAAgAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= "
              "--render-node-override=/dev/dri/renderD128 --shared-files=v8_context_snapshot_data:100 --field-trial-handle=3,i,1,2, 64")
    sunshine = "2898, /usr/bin/sunshine /home/someone/.config/sunshine/sunshine.conf --log=/var/log/sun/shine.log, 136"
    check("D1: the real Chrome command line (an argument holds /dev/dri/renderD128) is chrome and passes",
          (bg.exe_basename(chrome.split(", ", 1)[1].rsplit(", ", 1)[0]), bg.check_compute_apps([chrome])), ("chrome", []))
    check("D1: the real Sunshine command line (paths in its arguments) passes", (bg.check_compute_apps([sunshine]), bg.check_compute_apps([chrome, sunshine])), ([], []))
    check("D1: a job that hides behind a desktop name in an argument is still refused",
          len(bg.check_compute_apps(["77, /opt/conda/bin/python3 /home/x/chrome --render-node-override=/dev/dri/renderD128, 5800"])), 1)
    check("D1: a big Chrome is refused, an empty name does not crash",
          (len(bg.check_compute_apps(["2642, /opt/google/chrome/chrome --type=gpu-process, 900"])), bg.exe_basename("  "), bg.exe_basename("")), (1, "", ""))
    g = new_gate(svc)
    rc, out, err, _ = run_main(["--dry-run"], g, svc, os.path.join(root, "d1a"))
    g = new_gate(svc)
    rc, out, err, seen = run_main(["--tasks", "upscaler", "--recheck", "--caps", "100", "--reps", "1"], g, svc, os.path.join(root, "d1"),
                                  apps=[chrome, sunshine], env={"GATE_TOKEN": TOKEN, "GATE_BENCH_TOKEN": BENCH_TOKEN})
    check("D1: a run with the real Chrome and Sunshine on the card passes the pre-flight", (rc, "Pre-flight refused" in err), (0, False))

    # --- N3: the stt clip is cached under its length ---------------------------------------------------------------------------------
    tmp = os.path.join(root, "n3")
    for secs, want_total in (("170", 180.0), ("60", 60.0)):
        g = new_gate(svc)
        rc, out, err, seen = run_main(["--tasks", "stt", "--caps", "100", "--reps", "1", "--stt-secs", secs, "--keep-tmp"], g, svc, tmp)
    files = sorted(f for f in os.listdir(os.path.join(tmp, "home", "tmp")) if f.startswith("stt_es"))
    check("N3: two clip lengths make two files, named by length", files, ["stt_es_170.wav", "stt_es_60.wav"])
    check("N3: each file has its own length (180 s of three paragraphs, 60 s of one)",
          [round(bg.wav_seconds(open(os.path.join(tmp, "home", "tmp", f), "rb").read())) for f in files], [180, 60])
    g = new_gate(svc)
    n_before = svc.hits.count("/v1/audio/speech")
    rc, out, err, seen = run_main(["--tasks", "stt", "--caps", "100", "--reps", "1", "--stt-secs", "60", "--keep-tmp"], g, svc, tmp)
    check("N3: the same length again reuses its file (no new speech call)", svc.hits.count("/v1/audio/speech"), n_before)

    # --- D5: the bench client never sends the stacks' token to /bench/*, and a run without GATE_BENCH_TOKEN changes nothing -------------
    g = new_gate(svc)
    plain = bg.Gate(f"http://127.0.0.1:{g.port}", TOKEN)
    try:
        plain.call("POST", "/bench/start", {"stack": "bench", "watts": 100})
        got = "sent"
    except bg.GateError as e:
        got = "refused" if "GATE_BENCH_TOKEN" in str(e) else str(e)
    check("D5: a client without the bench token refuses to call /bench/*, nothing reaches the gate", (got, g.calls), ("refused", []))
    check("D5: the same client still reads /state with the stacks' token", plain.call("GET", "/state")[0], 200)
    check("D5: the right client starts a bench and ends it", (bg.Gate(f"http://127.0.0.1:{g.port}", TOKEN, bench_token=BENCH_TOKEN).call("POST", "/bench/start", {"stack": "bench", "watts": 100})[0],
                                                          bg.Gate(f"http://127.0.0.1:{g.port}", TOKEN, bench_token=BENCH_TOKEN).call("POST", "/bench/end", {"bench": "b1"})[0]), (200, 200))
    for label, env_ in (("missing", {"GATE_TOKEN": TOKEN}), ("empty", {"GATE_TOKEN": TOKEN, "GATE_BENCH_TOKEN": ""}),
                        ("equal to GATE_TOKEN", {"GATE_TOKEN": TOKEN, "GATE_BENCH_TOKEN": TOKEN})):
        g = new_gate(svc)
        rc, out, err, seen = run_main(["--tasks", "stt"], g, svc, os.path.join(root, "d5"), env=env_)
        check(f"D5: GATE_BENCH_TOKEN {label}: exit 2 before any gate call, nothing measured, tokens never printed",
              (rc, g.calls, seen, "GATE_BENCH_TOKEN" in err, TOKEN in out + err, BENCH_TOKEN in out + err), (2, [], [], True, False, False))
    g = new_gate(svc)
    rc, out, err, seen = run_main(["--tasks", "stt", "--dry-run"], g, svc, os.path.join(root, "d5b"), env={"GATE_TOKEN": TOKEN})
    check("D5: --dry-run needs no token", rc, 0)
    rc, out, err, _ = run_main(["--dry-run", "--tasks", "stt,vidgen", "--vid-secs", "5", "--reps", "5", "--recheck"], g, svc, os.path.join(root, "d5c"))
    check("D5: a plan longer than the gate's default bench TTL says so", "GATE_BENCH_TTL_S" in out, True)

    # --- N1: ComfyUI's node cache must never answer for the timed jobs -----------------------------------------------------------------
    v1, v2 = bg.Variants(bg.IMG_PROMPTS), bg.Variants(bg.IMG_PROMPTS)
    seq1 = [v1.pick() for _ in range(120)]
    check("N1: never the same (prompt, seed) as the previous job, over 120 jobs", [a[:2] == b[:2] for a, b in zip(seq1, seq1[1:])].count(True), 0)
    check("N1: the sequence is fixed (the same in every session) and the seeds come from the table",
          (seq1 == [v2.pick() for _ in range(120)], {x[1] for x in seq1} <= set(bg.SEEDS), {x[1] for x in seq1[:8]} == set(bg.SEEDS)), (True, True, True))
    check("N1: the table repeats only after 40 jobs", (seq1[0][:2] == seq1[40][:2], len({x[:2] for x in seq1[:40]})), (True, 40))
    check("N1: image prompts have one word count, video prompts have one word count",
          ({len(p.split()) for p in bg.IMG_PROMPTS}, {len(p.split()) for p in bg.VID_PROMPTS}, len(set(bg.IMG_PROMPTS)), len(set(bg.VID_PROMPTS))), ({11}, {8}, 5, 5))
    v3 = bg.Variants(bg.VID_PROMPTS)
    a_, b_ = v3.pick(), v3.pick(); v3.repeat_next(); c_, d_ = v3.pick(), v3.pick()
    check("N1: repeat_next repeats the last pick once, then it moves on", (b_ == c_, c_[:2] == d_[:2]), (True, False))

    def cache_measure(gate, svcs, seen_, speedup):
        base = fake_measure_for(gate, seen_)
        done = set()

        def measure(tag, fn, unit="job"):
            n0 = len(svcs.bodies)
            res = base(tag, fn, unit)
            if len(svcs.bodies) > n0:               # a job that sends (prompt, seed) again is answered by the node cache
                key = (svcs.bodies[-1].get("prompt"), svcs.bodies[-1].get("seed"))
                if key in done:
                    res["wall_s"] = round(res["wall_s"] / speedup, 2)
                done.add(key)
            return res
        return measure
    envk = {"GATE_TOKEN": TOKEN, "GATE_BENCH_TOKEN": BENCH_TOKEN, "IMAGE_TOKEN": "i", "VIDEO_TOKEN": "v"}
    g = new_gate(svc)
    seen = []
    svc.bodies.clear()
    tmp = os.path.join(root, "n1")
    rc, out, err, _ = run_main(["--tasks", "imggen", "--recheck", "--caps", "100,130", "--reps", "3", "--img-quality", "photo"], g, svc, tmp, env=envk,
                               measure=cache_measure(g, svc, seen, 1.0))
    bodies = [(b["prompt"], b["seed"]) for b in svc.bodies]
    same_next = [i for i in range(1, len(bodies)) if bodies[i] == bodies[i - 1]]
    check("N1 imggen: 1 warm-up + 2 canary + 2 caps x 3 jobs, exit 0", (rc, len(bodies)), (0, 9))
    check("N1 imggen: the only identical consecutive pair is the canary's, and the job after it moves on",
          (same_next, bodies[3] != bodies[2]), ([2], True))
    check("N1 imggen: seeds from the fixed table, every prompt of one word count",
          ({b[1] for b in bodies} <= set(bg.SEEDS), {len(b[0].split()) for b in bodies}), (True, {11}))
    ilines = [json.loads(l) for l in open(os.path.join(tmp, "home", "results.jsonl"))]
    icap = [l for l in ilines if l["kind"] == "cap"]
    check("N1 imggen: every timed job stores 8 hex of its output's sha256, its seed and its prompt index",
          all(len(r["out_sha8"]) == 8 and int(r["out_sha8"], 16) >= 0 and r["seed"] in bg.SEEDS and r["prompt_i"] in range(5) for l in icap for r in l["runs"]), True)
    check("N1 imggen: the output hash is the hash of what the service sent",
          icap[0]["runs"][0]["out_sha8"], hashlib.sha256(hashlib.sha256(json.dumps(
              {"prompt": bodies[3][0], "size": "1024x1024", "quality": "photo", "seed": bodies[3][1]}).encode()).digest()).hexdigest()[:8])
    can = [l for l in ilines if l["kind"] == "canary"]
    check("N1 canary: recorded, passed, not tainted, ratio 1", (len(can), can[0]["tainted"], can[0]["ratio"]), (1, False, 1.0))
    check("N1 canary: its two jobs are not pooled into a row", [l["row"]["n"] for l in icap], [3, 3])
    check("N1 canary: the pass is noted in the summary", "cache canary passed" in out, True)
    imggen_out = out
    # a cache hit that passes for production: 5x faster identical repeat
    g = new_gate(svc)
    seen = []
    svc.bodies.clear()
    tmp = os.path.join(root, "n1t")
    rc, out, err, _ = run_main(["--tasks", "imggen", "--recheck", "--caps", "100,130", "--reps", "3"], g, svc, tmp, env=envk, measure=cache_measure(g, svc, seen, 5.0))
    tl = [json.loads(l) for l in open(os.path.join(tmp, "home", "results.jsonl"))]
    check("N1 tainted: the task is aborted (exit 1) after the canary, no row recorded, bench ended, service released",
          (rc, len(svc.bodies), [l["kind"] for l in tl].count("cap"), ("POST", "/bench/end") in g.ops(), [n for n, x in g.svc.items() if x["running"]]), (1, 3, 0, True, []))
    check("N1 tainted: the output says cache-tainted and why", ("cache-tainted" in out, "5.0x faster" in out, "no row of this task is valid" in out), (True, True, True))
    check("N1 tainted: the canary line is kept as evidence", [(l["tainted"], l["ratio"]) for l in tl if l["kind"] == "canary"], [(True, 5.0)])
    check("N1 tainted: no cap proposed for it", ("recommended cap: none" in out, "imggen = " in out), (True, False))
    # vidgen: same machinery, video prompts
    g = new_gate(svc)
    seen = []
    svc.bodies.clear()
    rc, out, err, _ = run_main(["--tasks", "vidgen", "--recheck", "--caps", "130", "--reps", "2", "--vid-secs", "2"], g, svc, os.path.join(root, "n1v"), env=envk,
                               measure=cache_measure(g, svc, seen, 1.0))
    vb = [(b["prompt"], b["seed"], b["secs"]) for b in svc.bodies]
    check("N1 vidgen: 1 warm-up + 2 canary + 2 jobs, video prompts of 8 words, table seeds, secs kept",
          (rc, len(vb), {len(b[0].split()) for b in vb}, {b[0] in bg.VID_PROMPTS for b in vb}, {b[1] in bg.SEEDS for b in vb}, {b[2] for b in vb}), (0, 5, {8}, {True}, {True}, {2}))
    # a repeated identical job that is NOT faster passes; one that fails the canary jobs aborts clearly
    g = new_gate(svc)
    seen = []
    base_m = cache_measure(g, svc, seen, 1.0)
    calls_ = []

    def failing_canary(tag, fn, unit="job"):
        calls_.append(tag)
        res = base_m(tag, fn, unit)
        if tag.endswith("canary-same"):
            res.update(ok=False, err="boom")
        return res
    rc, out, err, _ = run_main(["--tasks", "imggen", "--recheck", "--caps", "100", "--reps", "1"], g, svc, os.path.join(root, "n1f"), env=envk, measure=failing_canary)
    check("N1: a canary job that fails aborts the task, no rows", (rc, "canary job failed" in out, any(t.endswith("-100W") for t in calls_)), (1, True, False))

    # --- D3: gross is the headline, net18 next to it, the settle before the idle sample ------------------------------------------------
    import types
    fake_m = types.SimpleNamespace(gpu_sampler=lambda stop, rows: rows.append((time.time(), 100.0, 3000.0, 80.0)) or time.sleep(0.05),
                                   ram_used_gb=lambda: 5.0, cpu_busy=lambda: 1.0)
    real_load, real_js = bg.load_measure, bg.job_sampler
    bg.load_measure = lambda: fake_m
    t_ = time.time()
    bg.job_sampler = lambda stop, rows: rows.extend([(t_ + 2.3, 61.0, 1695.0, 0x4, 130.0, 0.0), (t_ + 2.4, 71.0, 1710.0, 0x4, 130.0, 0.0)])
    try:
        rm = bg.real_measure("t", lambda: time.sleep(0.4) or 1)
    finally:
        bg.load_measure, bg.job_sampler = real_load, real_js
    exp = max(0.0, rm["gpu_wh"] - 18 * rm["wall_s"] / 3600)
    check("D3: gpu_net18_wh = gross - 18 W x s, next to gpu_wh (gross) and gpu_net_wh (minus the job's own idle)",
          (abs(rm["gpu_net18_wh"] - exp) < 2e-4, rm["gpu_net18_wh"] < rm["gpu_wh"], "gpu_net_wh" in rm), (True, True, True))
    check("D3: the job sampler's fields are folded in (peak temperature, SM clock, throttle OR, encoder, limits)",
          (rm.get("temp_peak_c"), rm.get("sm_mhz_med"), rm.get("throttle_or"), rm.get("enc_sessions_max"), rm.get("limit_w_min"), rm.get("limit_w_max")),
          (71.0, 1702.5, "0x4", 0, 130.0, 130.0))
    check("D3: fold of nothing is nothing", bg.fold_samples([]), {})
    clk = Clock()
    gx = new_gate(svc)
    ctx_ = bg.Ctx(bg.parse_args(["--tasks", "stt"], home=os.path.join(root, "d3"), videos=os.path.join(root, "d3v")),
                  bg.Gate(f"http://127.0.0.1:{gx.port}", TOKEN, bench_token=BENCH_TOKEN), FakeNv(gx), None, {}, os.path.join(root, "d3"), os.path.join(root, "d3v"),
                  sleep=clk.sleep, now=clk.now)
    t0_ = clk.now()
    pr = ctx_.idle_probe()
    check("D3: the card settles 3-5 s before the idle sample (and 1 s of reads)", (3.0 <= bg.SETTLE_S <= 5.0, clk.now() - t0_ >= bg.SETTLE_S), (True, True))
    check("D3: the idle probe carries the readings", (pr["temp_c"], pr["util"], pr["enc_sessions"], pr["limit_w"]), (47.0, 0.0, 0.0, 240.0))
    g = new_gate(svc)
    tmp = os.path.join(root, "d3full")
    rc, out, err, _ = run_main(["--tasks", "stt", "--caps", "100,130", "--reps", "2", "--stt-secs", "170"], g, svc, tmp)
    dl = [json.loads(l) for l in open(os.path.join(tmp, "home", "results.jsonl"))]
    check("D3: every run line carries gross, net-idle and net18; the session line says which is which",
          (all("gpu_net18_wh" in r and "gpu_wh" in r and "gpu_net_wh" in r for l in dl if l["kind"] == "cap" for r in l["runs"]),
           "net18" in dl[0]["wh_note"] and "gross" in dl[0]["wh_note"]), (True, True))
    check("D3: the table has gross, net18 and net-idle columns", ("Wh gross" in out, "net18 Wh" in out, "net-idle" in out), (True, True, True))
    s18 = bg.summarise(100, [{"ok": True, "wall_s": 10, "gpu_wh": 1.0, "gpu_net_wh": 0.8, "gpu_net18_wh": 0.95, "gpu_avg_w": 90, "gpu_peak_w": 100, "vram_peak_mib": 9}], "gpu_net18_wh")
    check("D3: --wh net18 recommends on the net18 figure", (s18["wh"], s18["net18_wh"], s18["rec_wh"]), (1.0, 0.95, 0.95))

    # --- D4: what each job carries, and when it is invalid -------------------------------------------------------------------------------
    cpu = os.path.join(root, "cpufreq"); os.makedirs(cpu)
    open(os.path.join(cpu, "scaling_governor"), "w").write("powersave\n")
    open(os.path.join(cpu, "energy_performance_preference"), "w").write("balance_performance\n")
    check("D4: cpu governor and EPP are read; a missing file is '?'", (bg.cpu_policy(cpu), bg.cpu_policy(os.path.join(root, "nope"))),
          ({"governor": "powersave", "epp": "balance_performance"}, {"governor": "?", "epp": "?"}))
    g = new_gate(svc)
    tmp = os.path.join(root, "d4")
    rc, out, err, _ = run_main(["--tasks", "stt", "--caps", "100,130", "--reps", "2", "--stt-secs", "170"], g, svc, tmp, unlock="all", cpu_dir=cpu)
    dl = [json.loads(l) for l in open(os.path.join(tmp, "home", "results.jsonl"))]
    runs = [r for l in dl if l["kind"] == "cap" for r in l["runs"]]
    check("D4: each job stores the limit read back at start and end, equal to the cap asked",
          [(r["cap_w_req"], r["limit_w_start"], r["limit_w_end"]) for r in runs], [(100, 100.0, 100.0)] * 2 + [(130, 130.0, 130.0)] * 2)
    check("D4: each job stores temperature, idle use, encoder sessions at idle, foreign apps",
          {(r["temp_c_start"], r["temp_c_end"], r["idle_util_pct"], r["enc_sessions_idle"], tuple(r["foreign_apps"])) for r in runs}, {(47.0, 47.0, 0.0, 0.0, ())})
    check("D4: each job stores governor, EPP, driver, kernel and the gpu_unlock value",
          {(r["governor"], r["epp"], r["driver"], r["kernel"] == os.uname().release, r["gpu_unlock"]) for r in runs}, {("powersave", "balance_performance", "595.71.05", True, "all")})
    check("D4: the session line carries the environment too", (dl[0]["env"]["driver"], dl[0]["env"]["governor"], dl[0]["env"]["gpu_unlock"]), ("595.71.05", "powersave", "all"))
    check("D4: no job of that run is invalid", [r.get("invalid_why") for r in runs], [None] * 4)
    check("D4: every cap line has the environment snapshot with the limit read back",
          [(l["env"]["cap_w_req"], l["env"]["limit_w_read"], l["env"]["driver"], l["env"]["gpu_unlock"], l["env"]["governor"]) for l in dl if l["kind"] == "cap"],
          [(100, 100.0, "595.71.05", "all", "powersave"), (130, 130.0, "595.71.05", "all", "powersave")])
    # the three invalid cases, end to end: nothing pooled, no recommendation from them
    for label, mutate, why_has in [
            ("GPU use 12 % at idle", lambda nv: nv.snap.update(util=12.0), "GPU use at idle 12 %"),
            ("an encoder session at idle (Sunshine)", lambda nv: nv.snap.update(enc_sessions=1.0), "encoder session(s) at idle"),
            ("a foreign compute app", None, "foreign compute app python3(4242)")]:
        g = new_gate(svc)
        nv = FakeNv(g)
        seen = []
        base_m = fake_measure_for(g, seen)
        if mutate:
            mutate(nv)

        def meas(tag, fn, unit="job", nv=nv, base_m=base_m, mutate=mutate):
            if not mutate and tag.endswith("-100W"):
                nv.apps = nv.apps + ["4242, /usr/bin/python3, 800"]      # appears after the warm-up, while the timed jobs run
            return base_m(tag, fn, unit)
        tmp = os.path.join(root, "d4i")
        shutil.rmtree(tmp, ignore_errors=True)
        rc, out, err, _ = run_main(["--tasks", "stt", "--caps", "100", "--reps", "2", "--stt-secs", "170"], g, svc, tmp, nv=nv, measure=meas)
        dl = [json.loads(l) for l in open(os.path.join(tmp, "home", "results.jsonl"))]
        crow = [l for l in dl if l["kind"] == "cap"][0]
        runs_ = crow["runs"]
        check(f"D4 invalid ({label}): every job is marked with its reason",
              all(r["invalid_why"] and why_has in r["invalid_why"][0] for r in runs_) and len(runs_) == 2, True)
        check(f"D4 invalid ({label}): nothing is pooled (no valid job, no medians), the row says why",
              (crow["row"]["n_ok"], crow["row"]["n_invalid"], "wall_s" in crow["row"], any("invalid" in e for e in crow["row"]["errors"])), (0, 2, False, True))
        check(f"D4 invalid ({label}): no cap is recommended from it, the table says no valid job", ("recommended cap: none" in out, "no valid job" in out), (True, True))
    # pure rules
    ok_m = {"ok": True, "limit_w_min": 130.0, "limit_w_max": 130.0, "throttle_or": "0x5", "enc_sessions_max": 0}
    idle_ok = {"util": 1.0, "enc_sessions": 0.0, "limit_w": 130.0}
    check("D4: a clean job is valid (idle + software cap throttle only)", bg.judge_job(ok_m, "imggen", 130, idle_ok, idle_ok, []), [])
    check("D4: use at idle over the limit, at the limit, under it",
          [bool(bg.judge_job(ok_m, "imggen", 130, dict(idle_ok, util=u), idle_ok, [])) for u in (5.1, 5.0, 4.0)], [True, False, False])
    check("D4: encoder sessions at idle make it invalid for every task", [bool(bg.judge_job(ok_m, t, 130, dict(idle_ok, enc_sessions=1.0), idle_ok, [])) for t in ("transcoder", "imggen")], [True, True])
    check("D4: encoder sessions during the job: invalid for a task that does not encode, fine for the transcoder",
          [bool(bg.judge_job(dict(ok_m, enc_sessions_max=1), t, 130, idle_ok, idle_ok, [])) for t in ("imggen", "transcoder")], [True, False])
    check("D4: a foreign compute app makes it invalid", bg.judge_job(ok_m, "stt", 130, idle_ok, idle_ok, ["python3(9)"]), ["foreign compute app python3(9)"])
    check("D4: a limit that is not the one asked (start or end), or that moved, makes it invalid",
          (bool(bg.judge_job(ok_m, "stt", 130, dict(idle_ok, limit_w=100.0), idle_ok, [])), bool(bg.judge_job(ok_m, "stt", 130, idle_ok, dict(idle_ok, limit_w=131.5), [])),
           bool(bg.judge_job(dict(ok_m, limit_w_min=130.0, limit_w_max=131.0), "stt", 130, idle_ok, idle_ok, [])), bool(bg.judge_job(ok_m, "stt", 130, idle_ok, dict(idle_ok, limit_w=130.5), []))),
          (True, True, True, False))
    check("D4: a thermal or hardware throttle makes it invalid, idle and the cap itself do not",
          [bool(bg.judge_job(dict(ok_m, throttle_or=t), "stt", 130, idle_ok, idle_ok, [])) for t in ("0x1", "0x4", "0x5", "0x20", "0x40", "0x8", "0x80")], [False, False, False, True, True, True, True])
    check("D4: a value that could not be read never invalidates, a failed job is failed and not invalid",
          (bg.judge_job({"ok": True}, "stt", None, {}, {}, []), bg.judge_job({"ok": False}, "stt", 130, dict(idle_ok, util=90.0), idle_ok, [])), ([], []))
    mix = [{"ok": True, "wall_s": 10, "gpu_wh": 1.0, "gpu_net_wh": 0.8, "gpu_net18_wh": 0.9, "gpu_avg_w": 90, "gpu_peak_w": 100, "vram_peak_mib": 9},
           {"ok": True, "wall_s": 10, "gpu_wh": 1.2, "gpu_net_wh": 1.0, "gpu_net18_wh": 1.1, "gpu_avg_w": 90, "gpu_peak_w": 100, "vram_peak_mib": 9},
           {"ok": True, "wall_s": 2, "gpu_wh": 0.1, "gpu_net_wh": 0.1, "gpu_net18_wh": 0.1, "gpu_avg_w": 90, "gpu_peak_w": 100, "vram_peak_mib": 9, "invalid_why": ["GPU use at idle 30 %"]}]
    sm = bg.summarise(100, mix, "gpu_wh")
    check("D4: an invalid job is never pooled: medians come from the valid ones only", (sm["n"], sm["n_ok"], sm["n_invalid"], sm["wall_s"], sm["wh"], sm["invalid_why"]),
          (3, 2, 1, 10.0, 1.1, ["GPU use at idle 30 %"]))
    # the real Nvidia reader against a stub nvidia-smi: a driver that renamed the throttle field, and one without encoder stats
    stubdir = os.path.join(root, "smi"); os.makedirs(stubdir, exist_ok=True)
    open(os.path.join(stubdir, "nvidia-smi"), "w").write(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  *clocks_event_reasons.active*) echo 'Invalid field' >&2; exit 2;;\n"
        "  *clocks_throttle_reasons.active*) echo '0x0000000000000004';;\n"
        "  *encoder.stats.sessionCount*) echo '[N/A]';;\n"
        "  *driver_version*) echo '595.71.05';;\n"
        "  *temperature.gpu*) echo '52, 1695, 130.00, 7';;\n"
        "  *) exit 3;;\n"
        "esac\n")
    os.chmod(os.path.join(stubdir, "nvidia-smi"), 0o755)
    old_path, old_field = os.environ["PATH"], bg.Nvidia.throttle_field
    os.environ["PATH"] = stubdir + os.pathsep + old_path
    bg.Nvidia.throttle_field = None
    try:
        snap_ = bg.Nvidia().snapshot()
        drv = bg.Nvidia().driver()
        field_found = bg.Nvidia.throttle_field
    finally:
        os.environ["PATH"], bg.Nvidia.throttle_field = old_path, old_field
    check("D4 real reader: temperature, clock, limit, use; the renamed throttle field is found; no encoder stats is None, not a failure",
          (snap_, field_found, drv), ({"temp_c": 52.0, "sm_mhz": 1695.0, "limit_w": 130.0, "util": 7.0, "throttle": 4, "enc_sessions": None},
                                       "clocks_throttle_reasons.active", "595.71.05"))
    # D2: the VRAM block of the dynamic-VRAM tasks is informative
    tail = imggen_out.split("gate/gate.py SERVICES")[1]
    check("D2: imggen's VRAM line says informative (dynamic VRAM, upper bound), is kept out of the SERVICES block and listed apart",
          ("INFORMATIVE ONLY" in imggen_out, "dynamic VRAM" in imggen_out, tail.split("\n")[1].strip(), "informative only (dynamic VRAM" in tail, "imggen: peak-based" in tail),
          (True, True, "(none)", True, True))
    check("D2: a fixed-memory service (stt) keeps its need line in the SERVICES block, not marked informative",
          ("stt: need " in full_out.split("gate/gate.py SERVICES")[1], "INFORMATIVE" in full_out.split("== stt ==")[1].split("==")[0]), (True, False))
    check("D2: the recommend line of imggen says its need is informative", [l.get("need_informative") for l in ilines if l["kind"] == "recommend"], [True])

    # --- review round: thin rows, plan estimate, cold jobs, sampler, unconfirmed cap, environment snapshot ------------------------------
    def jobs(n_ok, n, wh):
        return [{"ok": True, "wall_s": 10.0, "gpu_wh": wh, "gpu_net_wh": wh, "gpu_net18_wh": wh, "gpu_avg_w": 100.0, "gpu_peak_w": 120.0,
                 "vram_peak_mib": 900} for _ in range(n_ok)] + \
               [{"ok": True, "wall_s": 12.0, "gpu_wh": 9.0, "invalid_why": ["throttle 0x20"]} for _ in range(n - n_ok)]
    thin_row, full_row = bg.summarise(240, jobs(1, 5, 0.20)), bg.summarise(130, jobs(5, 5, 0.30))
    check("thin: 1 valid job of 5 is thin, 5 of 5 and 3 of 5 are not", (thin_row.get("thin"), full_row.get("thin"), bg.summarise(200, jobs(3, 5, 0.3)).get("thin")),
          (True, None, None))
    check("thin: the needed count is half the jobs, never under 2, and the single job of a one-job set",
          [bg.min_valid_jobs(n) for n in (1, 2, 3, 4, 5, 6)], [1, 2, 2, 2, 3, 3])
    pick, _ = bg.recommend([thin_row, full_row])
    check("thin: a cooler single survivor at 240 W does not beat the clean 5/5 row at 130 W", pick["cap_w"], 130)
    pick, why = bg.recommend([thin_row])
    check("thin: only thin rows give no recommendation and the reason says so", (pick, "thin" in why), (None, True))
    check("thin: the row line and the table mark it", ("THIN" in bg.row_line(thin_row), any("THIN" in l for l in bg.table_lines({"rows": [thin_row]}))), (True, True))

    pargs = bg.parse_args(["--tasks", "vidgen", "--recheck", "--caps", "130,100,159,250", "--reps", "2", "--vid-secs", "2"], os.path.join(root, "ph"), os.path.join(root, "pv"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bg.print_plan(["vidgen"], pargs, ttl_s=3600)
    est = bg.estimate_min("vidgen", [130, 100, 159, 250], 2, pargs)
    check("plan: the H3 plan counts the canary jobs and the measured per-job time, so the TTL note fires at 3600 s",
          (est > 50, "GATE_BENCH_TTL_S (now 3600 s" in buf.getvalue()), (True, True))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bg.print_plan(["vidgen"], pargs, ttl_s=7200)
    check("plan: no note when the TTL set on the host covers the plan", "GATE_BENCH_TTL_S" in buf.getvalue(), False)
    check("plan: the TTL comes from the host env", (bg.bench_ttl_s({"GATE_BENCH_TTL_S": "7200"}), bg.bench_ttl_s({}), bg.bench_ttl_s({"GATE_BENCH_TTL_S": "x"})),
          (7200.0, 3600.0, 3600.0))
    check("plan: two canary jobs more for a ComfyUI task only",
          (bg.estimate_min("imggen", [100], 2, pargs) > 0, bg.COMFY_TASKS), (True, {"imggen", "vidgen"}))

    ok_m2 = {"ok": True, "wall_s": 20.0, "samples": 40, "limit_w_min": 100.0, "limit_w_max": 100.0}
    idle_ok2 = {"util": 0.0, "enc_sessions": 0.0, "limit_w": 100.0}
    check("sampler: a job with no power samples, or under 80 % of the expected count, is invalid; a full count and an unknown count are fine",
          (bool(bg.judge_job(dict(ok_m2, samples=0), "stt", 100, idle_ok2, idle_ok2, [])), bool(bg.judge_job(dict(ok_m2, samples=31), "stt", 100, idle_ok2, idle_ok2, [])),
           bg.judge_job(dict(ok_m2, samples=32), "stt", 100, idle_ok2, idle_ok2, []), bg.judge_job({k: v for k, v in ok_m2.items() if k != "samples"}, "stt", 100, idle_ok2, idle_ok2, []),
           bool(bg.judge_job(dict(ok_m2, wall_s=0.4, samples=0), "stt", 100, idle_ok2, idle_ok2, [])), bg.judge_job(dict(ok_m2, wall_s=1.0, samples=1), "stt", 100, idle_ok2, idle_ok2, [])),
          (True, True, [], [], True, []))
    check("sampler: samples, the idle draw, use and CPU time are kept in the stored job line",
          all(k in bg.SLIM_KEYS for k in ("samples", "gpu_idle_w", "gpu_util_avg", "cpu_busy_core_s", "cap_w_asked", "cold")), True)

    # cold jobs: the service's worker is respawned (new PID inside its container); a foreign PID stays foreign
    for label, respawn in [("a respawned worker", True), ("a foreign app", False)]:
        g = new_gate(svc)
        nv = FakeNv(g)
        TOP.clear()
        TOP["stt"] = ["800"]
        seen = []
        base_m = fake_measure_for(g, seen)
        count = {"n": 0}

        def meas(tag, fn, unit="job", nv=nv, base_m=base_m, respawn=respawn, count=count):
            if tag.endswith("-warmup"):                   # the service's worker starts with the first request
                nv.apps = nv.apps + ["800, /usr/bin/python3, 800"]
            if tag.endswith("-100W"):
                count["n"] += 1
                if count["n"] == 2:                       # the second timed job of the cap
                    if respawn:
                        TOP["stt"] = ["801"]
                        nv.apps = [a for a in nv.apps if not a.startswith("800,")] + ["801, /usr/bin/python3, 800"]
                    else:
                        nv.apps = nv.apps + ["4242, /usr/bin/python3, 800"]
            return base_m(tag, fn, unit)
        tmp = os.path.join(root, "cold" + str(respawn))
        rc, out, err, _ = run_main(["--tasks", "stt", "--caps", "100", "--reps", "3", "--stt-secs", "170"], g, svc, tmp, nv=nv, measure=meas)
        dl = [json.loads(l) for l in open(os.path.join(tmp, "home", "results.jsonl"))]
        crow = [l for l in dl if l["kind"] == "cap"][0]
        whys = [r["invalid_why"] for r in crow["runs"]]
        if respawn:
            check(f"cold ({label}): only that job is invalid, flagged cold with its reason; the next jobs are valid (the new PID is known)",
                  (whys[0], bool(whys[1]) and "cold start" in whys[1][0], whys[2], [r["cold"] for r in crow["runs"]]), (None, True, None, [False, True, False]))
        else:
            check(f"cold ({label}): the foreign PID is not blessed as the service's own: it flags the job and the ones after it",
                  (whys[0], all(w and "foreign compute app python3(4242)" in w[0] for w in whys[1:]), [r["cold"] for r in crow["runs"]]), (None, True, [False, False, False]))
    TOP.clear()

    # a cap the card did not take: the jobs carry the limit the card reports, are marked invalid, and nothing is recommended from the row
    class StuckNv(FakeNv):
        def limit_w(self):
            return 240.0
    g = new_gate(svc)
    tmp = os.path.join(root, "stuckcap")
    rc, out, err, _ = run_main(["--tasks", "stt", "--caps", "100", "--reps", "2", "--stt-secs", "170"], g, svc, tmp, nv=StuckNv(g))
    dl = [json.loads(l) for l in open(os.path.join(tmp, "home", "results.jsonl"))]
    crow = [l for l in dl if l["kind"] == "cap"][0]
    check("cap not confirmed: jobs say asked 100 W and the real 240 W, are invalid with that reason, the row is cap_ok False with no valid job",
          ([(r["cap_w_req"], r["cap_w_asked"]) for r in crow["runs"]], all(any("cap not confirmed" in w for w in r.get("invalid_why") or []) for r in crow["runs"]),
           crow["row"]["cap_ok"], crow["row"]["n_ok"], "recommended cap: none" in out), ([(240.0, 100)] * 2, True, False, 0, True))

    # the environment snapshot: model listings of the services without a fixed list, re-read for every row
    ctx_env = bg.Ctx(bg.parse_args(["--tasks", "stt"], os.path.join(root, "eh"), os.path.join(root, "ev")), None, None, None, {}, os.path.join(root, "eh"),
                     os.path.join(root, "ev"), run=fake_run)
    env_stt = bg.service_env(ctx_env, "stt")
    check("env: stt has a model listing digest (dir, files, bytes, hash)", sorted((env_stt["model_files"] or {}).keys()), ["bytes", "dir", "files", "sha8"])
    check("env: transcoder has no model dir (image id only); a change in a model listing or the image is reported, an unknown value is not",
          (bg.service_env(ctx_env, "transcoder")["model_files"], bg.env_changes({"image_id": "a", "model_files": {"x": 1}}, {"image_id": "a", "model_files": {"x": 2}}),
           bg.env_changes({"image_id": "a"}, {"image_id": None}), bg.env_changes({"image_id": "a"}, {"image_id": "a"})), (None, ["model_files"], [], []))
    g = new_gate(svc)
    tmp = os.path.join(root, "envchg")
    flip = {"n": 0}
    base_run = fake_run

    def changing_run(cmd, **kw):
        if list(cmd)[:2] == ["docker", "inspect"]:
            flip["n"] += 1
            if flip["n"] >= 2:
                return subprocess.CompletedProcess(cmd, 0, "sha256:fedcba9876543210ffff\n", "")
        return base_run(cmd, **kw)
    globals()["fake_run"] = changing_run
    try:
        rc, out, err, _ = run_main(["--tasks", "stt", "--caps", "100,130", "--reps", "2", "--stt-secs", "170"], g, svc, tmp)
    finally:
        globals()["fake_run"] = base_run
    dl = [json.loads(l) for l in open(os.path.join(tmp, "home", "results.jsonl"))]
    crows = [l for l in dl if l["kind"] == "cap"]
    check("env: an image that changes mid-task is flagged on the rows and in the table, and each row carries the environment read for it",
          ([l["row"].get("env_changed") for l in crows], "environment changed" in out, crows[0]["env"]["image_id"]), ([["image_id"], ["image_id"]], True, "fedcba987654"))

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
