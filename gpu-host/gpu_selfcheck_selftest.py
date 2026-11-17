#!/usr/bin/env python3
"""Offline test of gpu-host/gpu_selfcheck.py and gpu_selfcheck_probe.py: a fake host (nvidia-smi, dpkg, docker, /proc and /sys files),
a fake gate, a fake clock and a fake torch whose matmul costs depend on the accumulation flag. Nothing real is touched: no GPU, no
Docker, no sudo, no network. Run: python3 -I gpu-host/gpu_selfcheck_selftest.py"""
import contextlib, io, json, os, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gpu_selfcheck as sc  # noqa: E402
import gpu_selfcheck_probe as probe  # noqa: E402

FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeHost:
    """nvidia-smi, dpkg-query, docker and the files the check reads, all scripted."""

    def __init__(self, clock, probe_json=None, probe_json2=None, name="NVIDIA GeForce RTX 3060 Ti", driver="595.71.05"):
        self.clock = clock
        self.calls = []
        self.files = {"/proc/cmdline": "BOOT_IMAGE=/vmlinuz root=/dev/sda2 ro quiet gpu_unlock.targets=all",
                      "/sys/module/gpu_unlock/parameters/targets": "all\n", "/proc/sys/kernel/osrelease": "6.12.74+deb13-amd64\n",
                      "/proc/sys/kernel/random/boot_id": "boot-aaaa\n"}
        self.paths = {"/sys/module/gpu_unlock", "/sys/module/nvidia"}
        self.pkgs = {"gpu-unlock-dkms": "2.0.0", "gpu-unlock-firmware": "2.0.0"}
        self.name, self.driver, self.limit, self.apps = name, driver, 200, []
        self.has_enc = True
        self.throttle_new_name = True                         # the driver knows clocks_event_reasons
        self.mask = "0x0000000000000004"
        self.probes = [probe_json, probe_json2] if probe_json2 else [probe_json]
        self.probe_i = 0
        self.rc = 0
        self.boom = False
        self.smi_down = False
        self.util = "0"                                       # utilisation the card shows while nothing of ours runs
        self.enc = "0"
        self.pmon = "# gpu         pid  type    sm   mem   enc   dec   jpg   ofa   command\n    0          -     -     -     -     -     -     -     -   -\n"
        self.pmon_rc = 0
        self.apps_rc = 0
        self.after_run = None                                 # callable(host) run when the fake probe finishes
        self.kbd = False                                      # SIGTERM arrives while the probe runs
        self.masks = None                                     # per-probe throttle mask override
        self.abort_with = None                                # a callable(host) run by the fake probe at its first abort poll
        self.killed_in_run = False

    def vals(self, busy=False):
        return {"name": self.name, "driver_version": self.driver, "persistence_mode": "Enabled", "power.limit": f"{self.limit:.2f}",
                "power.draw": "128.50", "clocks.sm": "1815", "clocks.max.sm": "2100", "temperature.gpu": "61",
                "utilization.gpu": "99" if busy else self.util, "utilization.encoder": self.enc, "utilization.decoder": "0",
                "clocks_event_reasons.active": self.mask, "clocks_throttle_reasons.active": self.mask}

    def cmd(self, argv, timeout=20):
        self.calls.append(list(argv))
        if argv[0] == "nvidia-smi":
            if self.smi_down:
                return 1, ""
            if argv[1] == "pmon":
                return self.pmon_rc, self.pmon
            q = [a for a in argv if a.startswith("--query")][0]
            if q.startswith("--query-compute-apps"):
                return self.apps_rc, "\n".join(self.apps) + ("\n" if self.apps else "")
            fields = q.split("=", 1)[1].split(",")
            if "clocks_event_reasons.active" in fields and not self.throttle_new_name:
                return 2, ""
            if "utilization.encoder" in fields and not self.has_enc:
                return 2, ""
            return 0, ", ".join(self.vals()[f] for f in fields) + "\n"
        if argv[0] == "dpkg-query":
            v = self.pkgs.get(argv[-1])
            return (0, f"ii |{v}") if v else (1, "")
        if argv[:3] == ["docker", "rm", "-f"]:
            return 0, ""
        return 127, ""

    def read(self, path):
        return self.files.get(path)

    def exists(self, path):
        return path in self.paths

    def run_sampled(self, argv, timeout, sample_argv, period=0.5, abort=None, abort_every=2.0):
        self.calls.append(list(argv))
        if self.boom:
            raise RuntimeError("docker exploded")
        if self.kbd:
            raise KeyboardInterrupt
        if self.abort_with:
            self.abort_with(self)                             # something happens while the probe runs (the gate ends the bench, ...)
        if abort is not None:
            for _ in range(3):                                # the real Host polls abort() while the probe runs
                self.clock.t += 2
                why = abort()
                if why:
                    self.killed_in_run = True
                    raise sc.Skipped(why)
        p = self.probes[min(self.probe_i, len(self.probes) - 1)]
        self.probe_i += 1
        self.clock.t += 12
        fields = [a for a in sample_argv if a.startswith("--query-gpu=")][0].split("=", 1)[1].split(",")
        v = self.vals(busy=True)
        if self.masks:
            v["clocks_event_reasons.active"] = self.masks[min(self.probe_i - 1, len(self.masks) - 1)]
        line = ", ".join(v[f] for f in fields)
        if self.after_run:
            self.after_run(self)
        return (self.rc, json.dumps(p) + "\n", [line, line])

    sleep = property(lambda self: self.clock.sleep)
    now = property(lambda self: self.clock.now)


class FakeGate:
    def __init__(self, host, state=None, bench_code=200, down=False):
        self.host, self.down, self.bench_code = host, down, bench_code
        self.state = state or {"gpu": {}, "blocked": None, "services": {"imggen": {"running": False, "leases": 0}}, "bench": None}
        self.clamp = None                                     # the gate gives this cap instead of the asked one
        self.calls = []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if self.down:
            raise sc.GateError("URLError")
        if path == "/state":
            return 200, self.state
        if path == "/bench/start":
            if self.bench_code != 200:
                return self.bench_code, {"why": "busy_jobs"}
            self.host.limit = self.clamp or body["watts"]
            self.state["bench"] = {"id": "b1b1b1b1", "watts": self.host.limit, "started": 0}
            return 200, {"bench": "b1b1b1b1"}
        if path == "/bench/end":
            self.host.limit = 200
            self.state["bench"] = None
            return 200, {"ok": True}
        return 404, {}


def good(ratio=0.97, r32=0.5, t=30.0):
    return {"torch": "2.9.1", "cuda": "12.8", "device": "NVIDIA GeForce RTX 3060 Ti", "capability": [8, 6], "fp16acc_supported": True,
            "sizes": [4096, 6144], "tflops": {"fp16_fp32acc": t, "fp16_fp16acc": round(t / ratio, 2), "tf32": round(t / ratio * r32, 2)},
            "ratio": ratio, "ratio_tf32": r32, "rounds": 5, "seconds": 4.2}


def world(probe_json=None, probe_json2=None, **kw):
    clock = Clock()
    host = FakeHost(clock, probe_json or good(), probe_json2, **{k: v for k, v in kw.items() if k in ("name", "driver")})
    sd = tempfile.mkdtemp(prefix="selfcheck-test-")
    gate = FakeGate(host)
    env = {"GATE_TOKEN": "tok"}
    ctx = sc.make_ctx({"host": host, "state_dir": sd, "gate": gate, "sleep": clock.sleep, "now": clock.now, "probe": "/x/probe.py"}, env)
    return ctx, host, gate, clock, sd


def run_exec(ctx, idle=0, no_gate=False):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = sc.execute(ctx, idle, no_gate)
    return code, out.getvalue()


def result(sd):
    return json.load(open(os.path.join(sd, "selfcheck.json")))


# ----------------------------------------------------------------------------------------------------------------- verdicts
j = sc.judge([good(0.97)], None, 130, "NVIDIA GeForce RTX 3060 Ti", [])
check("unlocked card (ratio 0.97): ok", (j["verdict"], j["reasons"], j["method"], j["borderline"]), ("ok", [], "ratio", False))
j = sc.judge([good(0.5, 0.25)], None, 130, "x", [])
check("stock card (ratio 0.5): degraded, ratio_low", (j["verdict"], j["reasons"]), ("degraded", ["ratio_low"]))
check("a good first run is kept as the baseline for a torch without the flag", j["baseline_update"], None)
j = sc.judge([good(0.97)], None, 130, "NVIDIA GeForce RTX 3060 Ti", [])
check("...a ratio-validated ok run proposes it, with the note that this card was seen unlocked",
      j["baseline_update"], {"gpu": "NVIDIA GeForce RTX 3060 Ti", "cap_w": 130, "tflops_fp16_fp32acc": 30.0, "unlock_seen_gpu": "NVIDIA GeForce RTX 3060 Ti"})
j = sc.judge([good(0.97)], None, 130, "x", [], {"throttle_mask": 0x40})
check("a good ratio on a hot card does not become the reference", (j["verdict"], j["baseline_update"]), ("ok", None))
j = sc.judge([good(0.97)], None, 125, "x", [], requested_w=130)
check("cap_mismatch: asked 130 W, the card ran at 125: recorded, the ratio still judges (ok), no baseline taken", (j["verdict"], j["reasons"], j["baseline_update"]), ("ok", ["cap_mismatch"], None))
j = sc.judge([good(0.5, 0.25)], None, 125, "x", [], requested_w=130)
check("cap_mismatch does not hide a low ratio", (j["verdict"], j["reasons"]), ("degraded", ["cap_mismatch", "ratio_low"]))
j = sc.judge([good(0.97, t=30.0)], {"gpu": "x", "cap_w": 130, "tflops_fp16_fp32acc": 40.0}, 130, "x", [])
check("ratio fine but the TFLOPS are 75 % of the baseline (clocks locked low): degraded, tflops_low", (j["verdict"], j["reasons"], j["tflops_vs_baseline"]), ("degraded", ["tflops_low"], 0.75))
j = sc.judge([good(0.97, t=30.0)], {"gpu": "x", "cap_w": 130, "tflops_fp16_fp32acc": 31.0}, 130, "x", [])
check("ratio fine and TFLOPS at 97 % of the baseline: ok", (j["verdict"], j["reasons"]), ("ok", []))
j = sc.judge([good(0.97, t=30.0)], {"gpu": "x", "cap_w": 100, "tflops_fp16_fp32acc": 40.0}, 130, "x", [])
check("a baseline of another cap is not compared in ratio mode either", (j["verdict"], j["tflops_vs_baseline"]), ("ok", None))
j = sc.judge([good(0.97, t=20.0)], {"gpu": "x", "cap_w": 130, "tflops_fp16_fp32acc": 40.0}, 130, "x", [], {"throttle_mask": 0x40})
check("low TFLOPS on a hot card: cannot judge (throttled_hw), not degraded", (j["verdict"], j["reasons"]), ("error", ["throttled_hw"]))
j = sc.judge([good(0.78)], None, 130, "x", [])
check("ratio 0.78: ok but in the grey band (measured again by the run)", (j["verdict"], j["borderline"]), ("ok", True))
j = sc.judge([good(0.74), good(0.70)], None, 130, "x", [])
check("two grey-band runs: the median decides (0.72 < 0.75)", (j["ratio"], j["verdict"]), (0.72, "degraded"))
j = sc.judge([good(0.80), good(0.90)], None, 130, "x", [])
check("two runs 0.80 and 0.90: median 0.85 is ok", (j["ratio"], j["verdict"]), (0.85, "ok"))
j = sc.judge([good(0.5, 0.25)], None, 130, "x", [], {"throttle_mask": 0x4 | 0x40})
check("low ratio on a card in hardware thermal throttle: cannot judge (error, throttled_hw)", (j["verdict"], j["reasons"]), ("error", ["throttled_hw"]))
j = sc.judge([good(0.5)], None, 130, "x", [], {"throttle_mask": 0x4})
check("a software power cap is expected at 130 W: it does not excuse a low ratio", (j["verdict"], j["reasons"]), ("degraded", ["ratio_low"]))
j = sc.judge([good(0.97)], None, 130, "x", [], {"throttle_mask": 0x40})
check("a good ratio stays ok even when throttled", j["verdict"], "ok")
j = sc.judge([good(0.97)], None, 130, "x", ["param_missing"])
check("param missing is degraded even when the ratio looks fine", (j["verdict"], j["reasons"]), ("degraded", ["param_missing"]))
j = sc.judge([{"error": "probe_failed"}], None, 130, "x", [])
check("probe failed, nothing else known: error", (j["verdict"], j["reasons"]), ("error", ["probe_failed"]))
j = sc.judge([{"error": "timeout"}], None, 130, "x", ["module_not_loaded"])
check("probe failed with the module missing: degraded", (j["verdict"], j["reasons"]), ("degraded", ["module_not_loaded", "probe_failed"]))
j = sc.judge([good(0.5, 0.25)], None, 130, "x", [], tf32_judges=True)
check("tf32 ratio judges when switched on", j["reasons"], ["ratio_low", "tf32_ratio_low"])
j = sc.judge([good(0.97, 0.25)], None, 130, "x", [])
check("tf32 ratio is only recorded by default", (j["verdict"], j["ratio_tf32"]), ("ok", 0.25))
# absolute fallback: a torch without FP16 accumulation
nof = {"tflops": {"fp16_fp32acc": 30.0, "fp16_fp16acc": None, "tf32": None}, "ratio": None, "ratio_tf32": None, "fp16acc_supported": False}
j = sc.judge([nof], None, 130, "G", [])
check("absolute, no baseline yet: error no_reference (never ok: the card may already be stock), no baseline taken", (j["verdict"], j["method"], j["reasons"], j["baseline_update"]), ("error", "absolute", ["no_reference"], None))
j = sc.judge([nof], None, 130, "G", [], accept_baseline=True)
check("absolute, the operator accepts this run as the reference: ok and the baseline is proposed", (j["verdict"], j["baseline_update"]), ("ok", {"gpu": "G", "cap_w": 130, "tflops_fp16_fp32acc": 30.0, "accepted": True}))
j = sc.judge([nof], None, 125, "G", [], requested_w=130, accept_baseline=True)
check("absolute at another cap than asked: not accepted as a reference, error", (j["verdict"], j["reasons"], j["baseline_update"]), ("error", ["cap_mismatch", "no_reference"], None))
j = sc.judge([nof], None, 130, "G", ["param_missing"])
check("absolute, no baseline, unlock not active: not taken as the reference", (j["verdict"], j["baseline_update"]), ("degraded", None))
base = {"gpu": "G", "cap_w": 130, "tflops_fp16_fp32acc": 36.0}
j = sc.judge([nof], base, 130, "G", [])
check("absolute: 30 of 36 TFLOPS (83 %) is below 85 %: degraded, tflops_low", (j["verdict"], j["reasons"], j["tflops_vs_baseline"]), ("degraded", ["tflops_low"], 0.833))
base["tflops_fp16_fp32acc"] = 31.0
j = sc.judge([nof], base, 130, "G", [])
check("absolute: 97 % of baseline is ok", (j["verdict"], j["tflops_vs_baseline"]), ("ok", 0.968))
j = sc.judge([nof], dict(base, cap_w=100), 130, "G", [])
check("absolute with a baseline of another cap: cannot compare, said (error no_reference), not silently ok", (j["tflops_vs_baseline"], j["verdict"], j["reasons"]), (None, "error", ["no_reference"]))

# ------------------------------------------------------------------------------------------------------------------ facts
ctx, host, gate, clock, sd = world()
f = sc.gather(host, ctx["smi"], ctx["env"])
check("facts: the unlocked host", (f["unlock"]["expected"], sc.static_reasons(f["unlock"]), f["gpu"]["driver"], f["gpu"]["persistence"],
                                    f["fingerprint"]["unlock_pkg"], f["boot_id"]), (True, [], "595.71.05", "enabled", "2.0.0", "boot-aaaa"))
host.files["/proc/cmdline"] = "ro quiet"
host.files["/sys/module/gpu_unlock/parameters/targets"] = "\n"
f = sc.gather(host, ctx["smi"], ctx["env"])
check("facts: the boot line lost: param_missing", sc.static_reasons(f["unlock"]), ["param_missing"])
host.paths.discard("/sys/module/gpu_unlock")
f = sc.gather(host, ctx["smi"], ctx["env"])
check("facts: module not loaded (package still installed): both reasons", sc.static_reasons(f["unlock"]), ["module_not_loaded", "param_missing"])
host.pkgs.clear(); host.files["/proc/cmdline"] = "ro"; host.files.pop("/sys/module/gpu_unlock/parameters/targets")
f = sc.gather(host, ctx["smi"], ctx["env"])
check("facts: nothing of the unlock there: not expected", f["unlock"]["expected"], False)
sc.write_json(os.path.join(ctx["state_dir"], "selfcheck_baseline.json"), {"gpu": "NVIDIA GeForce RTX 3060 Ti", "cap_w": 130, "tflops_fp16_fp32acc": 30.0, "unlock_seen_gpu": "NVIDIA GeForce RTX 3060 Ti"})
f = sc.gather(host, ctx["smi"], ctx["env"], ctx["state_dir"])
check("facts: nothing there now, but this card was once seen unlocked here: EXPECTED (the upgrade took the patch away), both reasons",
      (f["unlock"]["expected"], sc.static_reasons(f["unlock"])), (True, ["module_not_loaded", "param_missing"]))
sc.write_json(os.path.join(ctx["state_dir"], "selfcheck_baseline.json"), {"gpu": "x", "unlock_seen_gpu": "NVIDIA GeForce RTX 2070"})
f = sc.gather(host, ctx["smi"], ctx["env"], ctx["state_dir"])
check("facts: the marker belongs to another card (swapped): not expected", f["unlock"]["expected"], False)
f = sc.gather(host, ctx["smi"], {"GPU_SELFCHECK_EXPECT_UNLOCK": "0"}, ctx["state_dir"])
check("facts: the operator's EXPECT_UNLOCK=0 wins over the marker", f["unlock"]["expected"], False)
host.files["/proc/cmdline"] = "ro gpu_unlock.targets=all"; host.paths.add("/sys/module/gpu_unlock"); host.pkgs.update({"gpu-unlock-dkms": "2.0.0", "gpu-unlock-firmware": "2.0.0"})
f = sc.gather(host, ctx["smi"], ctx["env"])
check("facts: boot line has the parameter, module loaded, the sysfs file cannot be read: no param_missing (the ratio decides)", (f["unlock"]["param_readable"], sc.static_reasons(f["unlock"])), (False, []))
host.files["/sys/module/gpu_unlock/parameters/targets"] = "\n"
f = sc.gather(host, ctx["smi"], ctx["env"])
check("facts: ...but a readable empty parameter is still param_missing", sc.static_reasons(f["unlock"]), ["param_missing"])
host.pkgs.clear(); host.files["/proc/cmdline"] = "ro"; host.files.pop("/sys/module/gpu_unlock/parameters/targets"); host.paths.discard("/sys/module/gpu_unlock")
f = sc.gather(host, ctx["smi"], {"GPU_SELFCHECK_EXPECT_UNLOCK": "1"})
check("facts: GPU_SELFCHECK_EXPECT_UNLOCK=1 expects it anyway", (f["unlock"]["expected"], sc.static_reasons(f["unlock"])), (True, ["module_not_loaded", "param_missing"]))
ctx, host, gate, clock, sd = world()
host.throttle_new_name = False
check("throttle field: the old spelling is found when the new one is refused", ctx["smi"].live_fields()[-1], "clocks_throttle_reasons.active")
ctx, host, gate, clock, sd = world()
check("throttle field: the new spelling first", ctx["smi"].live_fields()[-1], "clocks_event_reasons.active")
s = sc.summarize_samples(["1800, 2100, 60, 120.0, 130.00, 99, 0x0000000000000004", "1700, 2100, 64, 129.0, 130.00, 99, 0x0000000000000044", "210, 2100, 40, 20.0, 130.00, 0, 0x1"],
                         ["clocks.sm", "clocks.max.sm", "temperature.gpu", "power.draw", "power.limit", "utilization.gpu", "clocks_event_reasons.active"])
check("samples: max temp and draw, median busy clock, union of throttle bits", (s["temp_max_c"], s["power_draw_max_w"], s["clocks_sm_busy_mhz"], s["throttle_mask"], s["throttle_names"]),
      (64.0, 129.0, 1750, 0x45, ["idle", "sw_power_cap", "hw_thermal"]))

# ------------------------------------------------------------------------------------------------------------- the full run
ctx, host, gate, clock, sd = world()
code, out = run_exec(ctx)
r = result(sd)
check("run: unlocked card -> exit 0, verdict ok", (code, r["verdict"], r["method"], r["ratio"]), (0, "ok", "ratio", 0.97))
check("run: the gate sequence is state, bench start at 130 W, (state polls while it runs), bench end",
      ([(m, p) for m, p, _ in gate.calls][:2], [(m, p) for m, p, _ in gate.calls if m == "POST"], gate.calls[-1][1]), ([("GET", "/state"), ("POST", "/bench/start")], [("POST", "/bench/start"), ("POST", "/bench/end")], "/bench/end"))
check("run: the gate is polled while the probe runs (so that a session that starts ends it)", [p for _, p, _ in gate.calls].count("/state") > 2, True)
check("run: the bench asked for the fixed cap", gate.calls[1][2], {"stack": "selfcheck", "watts": 130})
check("run: the cap was applied while measuring and is back after", (r["cap_w"], host.limit), (130, 200))
docker = [c for c in host.calls if c[:2] == ["docker", "run"]][0]
check("run: the container is throwaway, read-only, offline, no capabilities, probe mounted read-only",
      all(x in docker for x in ("--rm", "--read-only", "--cap-drop", "--gpus", "--network", "none", "no-new-privileges")) and "/x/probe.py:/probe.py:ro" in docker, True)
check("run: image default is imggen:latest", "imggen:latest" in docker, True)
check("run: a stale container of the same name is removed first", host.calls.index(["docker", "rm", "-f", sc.CONTAINER]) < host.calls.index(docker), True)
check("result: gpu facts and the run telemetry are recorded", (r["gpu"]["persistence"], r["gpu"]["driver"], r["run"]["temp_max_c"], r["run"]["throttle_names"], r["driver"], r["fingerprint"]["kernel"]),
      ("enabled", "595.71.05", 61.0, ["sw_power_cap"], "595.71.05", "6.12.74+deb13-amd64"))
check("result: no baseline key leaks into the file, the baseline file is written once", ("_baseline_update" in r, os.path.exists(os.path.join(sd, "selfcheck_baseline.json"))), (False, True))
check("result: the summary line says what it measured", "ratio 0.97" in out and "gpu selfcheck: ok" in out, True)
check("result: a verdict ok costs nothing extra", r["extra_cost_pct"], None)

ctx, host, gate, clock, sd = world(good(0.5, 0.25))
code, out = run_exec(ctx)
r = result(sd)
check("run: stock card -> exit 1, degraded, ratio_low", (code, r["verdict"], r["reasons"]), (1, "degraded", ["ratio_low"]))
check("run: the cost of a degraded 3060 Ti is stated (about 35 % per job)", (r["extra_cost_pct"], "35%" in out, "energy" in out), (35, True, True))
ctx, host, gate, clock, sd = world(good(0.5, 0.25), name="NVIDIA GeForce RTX 3090")
code, out = run_exec(ctx)
check("run: a card with no measurement says it is slower and costlier, without a number", (result(sd)["extra_cost_pct"], "cost more energy per job" in out), (None, True))

ctx, host, gate, clock, sd = world(good(0.78), good(0.96))
code, out = run_exec(ctx)
check("run: a grey-band ratio is measured again (two containers), the median decides", (len([c for c in host.calls if c[:2] == ["docker", "run"]]), result(sd)["ratio"], code), (2, 0.87, 0))
ctx, host, gate, clock, sd = world(good(0.55))
run_exec(ctx)
check("run: a clearly low ratio is not repeated", len([c for c in host.calls if c[:2] == ["docker", "run"]]), 1)

ctx, host, gate, clock, sd = world()
host.boom = True
try:
    run_exec(ctx)
except RuntimeError:
    pass
check("run: the bench is ended even when the probe blows up", [p for _, p, _ in gate.calls][-1], "/bench/end")
check("run: and the container is removed too", host.calls[-1], ["docker", "rm", "-f", sc.CONTAINER])
ctx, host, gate, clock, sd = world()
host.rc = 3
host.probes = [{"error": "no_cuda"}]
code, out = run_exec(ctx)
check("run: a probe that cannot run -> error verdict, bench ended", (code, result(sd)["verdict"], result(sd)["reasons"], gate.calls[-1][1]), (2, "error", ["probe_failed"], "/bench/end"))

# ------------------------------------------------------------------------------------------ never interrupts, skips instead
def skipped(ctx, host, gate, why, idle=0):
    code, out = run_exec(ctx, idle)
    return (code, why in out, not any(p == "/bench/start" for _, p, _ in gate.calls), not os.path.exists(os.path.join(ctx["state_dir"], "selfcheck.json")),
            not any(c[:2] == ["docker", "run"] for c in host.calls))

for label, mut, why in [("a service is running", lambda h, g: g.state["services"]["imggen"].update(running=True), "service"),
                        ("a lease is open", lambda h, g: g.state["services"]["imggen"].update(leases=1), "service"),
                        ("a person's session (vr)", lambda h, g: g.state.update(blocked="vr"), "vr"),
                        ("the operator's switch", lambda h, g: g.state.update(blocked="busy"), "busy"),
                        ("another bench runs", lambda h, g: g.state.update(bench={"id": "x"}), "bench"),
                        ("a compute process is on the card", lambda h, g: h.apps.append("123, blender, 900"), "card_in_use")]:
    ctx, host, gate, clock, sd = world()
    mut(host, gate)
    check(f"skip: {label} -> exit 75, no bench, no container, no result file", skipped(ctx, host, gate, why), (75, True, True, True, True))
ctx, host, gate, clock, sd = world()
gate.bench_code = 409
code, out = run_exec(ctx)
check("skip: the gate refuses the bench (409) -> exit 75, nothing to end, nothing run", (code, "busy_jobs" in out, [p for _, p, _ in gate.calls], any(c[:2] == ["docker", "run"] for c in host.calls)),
      (75, True, ["/state", "/bench/start"], False))
ctx, host, gate, clock, sd = world()
gate.down = True
check("skip: the gate does not answer -> exit 75", skipped(ctx, host, gate, "gate_down")[:2], (75, True))
ctx, host, gate, clock, sd = world()
code, out = run_exec(ctx, no_gate=True)
check("--no-gate: runs at the current limit without the gate, still checks the card is free", (code, gate.calls, result(sd)["cap_w"]), (0, [], 200))
ctx, host, gate, clock, sd = world()
host.apps.append("1, x, 5")
check("--no-gate: a compute process still skips", run_exec(ctx, no_gate=True)[0], 75)
ctx, host, gate, clock, sd = world()
ctx["gate"] = None
ctx["env"] = {}
code = run_exec(ctx)[0]
check("no token and no --no-gate: exit 78 and an error result is written (a host that never checks must not be silent)", (code, result(sd)["verdict"], result(sd)["reasons"]), (78, "error", ["no_gate_token"]))

# idle for N seconds: polls 5 s apart, any busy poll ends it
ctx, host, gate, clock, sd = world()
t0 = clock.t
code, out = run_exec(ctx, idle=15)
ps = [p for _, p, _ in gate.calls]
check("idle wait: 15 s = 4 polls over 15 s, then the bench", (code, ps[:ps.index("/bench/start")].count("/state"), clock.t - t0 >= 15 + 12), (0, 4, True))
ctx, host, gate, clock, sd = world()
polls = []
orig = gate.call
def going_busy(m, p, b=None):
    if p == "/state":
        polls.append(1)
        if len(polls) == 3:
            gate.state["blocked"] = "vr"
    return orig(m, p, b)
gate.call = going_busy
code, out = run_exec(ctx, idle=30)
check("idle wait: a session that starts during the wait ends it at once (3 polls, no bench)", (code, len(polls), "vr" in out), (75, 3, True))

# applicable cards and expectation
ctx, host, gate, clock, sd = world(name="NVIDIA GeForce GTX 1070 Ti")
code, out = run_exec(ctx)
check("a card that is not GeForce RTX 30: nothing to judge, ok, no gate call, no container", (code, result(sd)["verdict"], gate.calls, any(c[:2] == ["docker", "run"] for c in host.calls)), (0, "ok", [], False))
ctx, host, gate, clock, sd = world()
host.pkgs.clear(); host.files["/proc/cmdline"] = "ro"; host.files.pop("/sys/module/gpu_unlock/parameters/targets"); host.paths.discard("/sys/module/gpu_unlock")
code, out = run_exec(ctx)
check("unlock not expected on this host: ok without measuring", (code, result(sd)["verdict"], result(sd)["unlock_expected"], gate.calls), (0, "ok", False, []))
ctx, host, gate, clock, sd = world()
host.smi_down = True
check("no nvidia-smi: error no_gpu", (run_exec(ctx)[0], result(sd)["reasons"]), (2, ["no_gpu"]))
ctx, host, gate, clock, sd = world()
host.files["/proc/cmdline"] = "ro quiet"
host.files["/sys/module/gpu_unlock/parameters/targets"] = ""
code, out = run_exec(ctx)
check("boot line lost: degraded param_missing even though the ratio is good", (code, result(sd)["verdict"], result(sd)["reasons"]), (1, "degraded", ["param_missing"]))
ctx, host, gate, clock, sd = world(nof)
host.probes = [nof]
code, out = run_exec(ctx)
r = result(sd)
check("a torch without FP16 accumulation: method absolute, no reference yet -> error no_reference and NO baseline is taken on its own",
      (code, r["method"], r["reasons"], os.path.exists(os.path.join(sd, "selfcheck_baseline.json"))), (2, "absolute", ["no_reference"], False))
ctx["accept_baseline"] = True
code, out = run_exec(ctx)
r = result(sd)
check("...the operator's --accept-baseline run is ok and writes it", (code, r["verdict"], json.load(open(os.path.join(sd, "selfcheck_baseline.json")))["tflops_fp16_fp32acc"],
                                                                    "accepted" in json.load(open(os.path.join(sd, "selfcheck_baseline.json")))), (0, "ok", 30.0, False))
ctx["accept_baseline"] = False
host.probes = [dict(nof, tflops={"fp16_fp32acc": 15.0, "fp16_fp16acc": None, "tf32": None})]
host.probe_i = 0
code, out = run_exec(ctx)
check("...and the next run at half the speed is degraded (tflops_low)", (code, result(sd)["reasons"], result(sd)["tflops_vs_baseline"]), (1, ["tflops_low"], 0.5))

# ------------------------------------------------------------------------------------------------------------- when it is due
ctx, host, gate, clock, sd = world()
facts = sc.gather(host, ctx["smi"], ctx["env"])
last = {"at": int(clock.t) - 100, "boot_id": "boot-aaaa", "fingerprint": facts["fingerprint"], "verdict": "ok"}
due = lambda l=last, f=facts, t=None: sc.pending_reason(l, f, clock.t if t is None else t)
check("due: never ran", sc.pending_reason(None, facts, clock.t), "first")
check("due: not at all when nothing changed", due(), None)
check("due: a new boot", due(f=dict(facts, boot_id="boot-bbbb")), "boot")
check("due: a new kernel", due(f=dict(facts, fingerprint=dict(facts["fingerprint"], kernel="6.12.75+deb13-amd64"))), "changed")
check("due: a new driver", due(f=dict(facts, fingerprint=dict(facts["fingerprint"], driver="595.80.01"))), "changed")
check("due: a new gpu-unlock package", due(f=dict(facts, fingerprint=dict(facts["fingerprint"], unlock_pkg="2.1.0"))), "changed")
check("due: after a week", due(t=clock.t + 8 * 86400), "stale")
check("due: an error result is retried after 6 h, not before", (due(dict(last, verdict="error"), t=clock.t + 3600), due(dict(last, verdict="error"), t=clock.t + 7 * 3600)), (None, "retry_error"))

ctx, host, gate, clock, sd = world()
out = io.StringIO()
with contextlib.redirect_stdout(out):
    code = sc.main(["auto", "--idle-s", "0"], {"host": host, "state_dir": sd, "gate": gate, "sleep": clock.sleep, "now": clock.now, "no_signals": True, "probe": "/p"})
check("auto, first time: runs and exits 0", (code, result(sd)["verdict"]), (0, "ok"))
gate.calls.clear(); host.calls.clear()
with contextlib.redirect_stdout(out):
    code = sc.main(["auto"], {"host": host, "state_dir": sd, "gate": gate, "sleep": clock.sleep, "now": clock.now, "no_signals": True, "probe": "/p"})
check("auto, nothing changed: exits 0 without touching the gate or docker", (code, gate.calls, any(c[:2] == ["docker", "run"] for c in host.calls)), (0, [], False))
host.files["/proc/sys/kernel/random/boot_id"] = "boot-bbbb\n"
host.apps.append("5, game, 4000")
with contextlib.redirect_stdout(out):
    code = sc.main(["auto", "--idle-s", "0"], {"host": host, "state_dir": sd, "gate": gate, "sleep": clock.sleep, "now": clock.now, "no_signals": True, "probe": "/p"})
check("auto, a new boot but the card in use: skipped, exit 0 (timer stays green), the old result is kept and the run is still due",
      (code, result(sd)["boot_id"], sc.pending_reason(result(sd), sc.gather(host, ctx["smi"], ctx["env"]), clock.t)), (0, "boot-aaaa", "boot"))
host.apps.clear()
with contextlib.redirect_stdout(out):
    code = sc.main(["run"], {"host": host, "state_dir": sd, "gate": gate, "sleep": clock.sleep, "now": clock.now, "no_signals": True, "probe": "/p"})
check("run after the boot change measures and records the new boot", (code, result(sd)["boot_id"]), (0, "boot-bbbb"))
out = io.StringIO()
with contextlib.redirect_stdout(out):
    code = sc.main(["run"], {"host": host, "state_dir": sd, "gate": gate, "sleep": clock.sleep, "now": clock.now, "no_signals": True, "probe": "/p"})
check("run with nothing changed does not repeat (needs --force)", (code, "not repeated" in out.getvalue()), (0, True))
out = io.StringIO()
with contextlib.redirect_stdout(out):
    sc.main(["status"], {"host": host, "state_dir": sd, "gate": gate, "sleep": clock.sleep, "now": clock.now, "no_signals": True})
check("status: last verdict and not due", ("gpu selfcheck: ok" in out.getvalue(), "not due" in out.getvalue()), (True, True))

# -------------------------------------------------------------------------------- the probe, against a fake torch
class FakeTorch:
    """matmul costs by flags: stock fp32-acc fp16 2 ms, fp16-acc 1 ms, tf32 4 ms; unlocked 1, 1 and 2 ms."""

    def __init__(self, unlocked=False, fp16acc=True, cuda=True):
        self.unlocked, self.has_flag, self.cuda_ok = unlocked, fp16acc, cuda
        self.gpu_ms = 0.0
        self.version = type("V", (), {"cuda": "12.8"})
        self.__version__ = "2.9.1"
        outer = self
        self.float16, self.float32 = "f16", "f32"

        class Matmul:
            allow_tf32 = False
            _acc = False

            @property
            def allow_fp16_accumulation(self_):
                if not outer.has_flag:
                    raise AttributeError("allow_fp16_accumulation")
                return self_._acc

            @allow_fp16_accumulation.setter
            def allow_fp16_accumulation(self_, v):
                if not outer.has_flag:
                    raise RuntimeError("not supported")
                self_._acc = v

        self.m = Matmul()
        self.backends = type("B", (), {"cuda": type("C", (), {"matmul": self.m})})

        class Ev:
            def __init__(s, enable_timing=False):
                s.t = None

            def record(s):
                s.t = outer.gpu_ms

            def elapsed_time(s, e):
                return e.t - s.t

        class Cuda:
            Event = Ev
            is_available = staticmethod(lambda: outer.cuda_ok)
            synchronize = staticmethod(lambda: None)
            get_device_properties = staticmethod(lambda i: type("P", (), {"name": "FakeCard"})())
            get_device_capability = staticmethod(lambda i: (8, 6))

        self.cuda = Cuda
        self.device = lambda kind, i=0: (kind, i)

    def randn(self, n, m, device=None, dtype=None):
        return (n, dtype)

    def matmul(self, a, b):
        n, dt = a
        if dt == "f32":
            ms = (2.0 if self.unlocked else 4.0) if self.m.allow_tf32 else 20.0     # plain fp32 (no tensor cores) is far slower
        elif self.m._acc if self.has_flag else False:
            ms = 1.0
        else:
            ms = 1.0 if self.unlocked else 2.0
        self.gpu_ms += ms * (n / 4096) ** 3


class T:
    t = 0.0


def fake_clock():
    T.t += 0.01
    return T.t


r = probe.run(FakeTorch(unlocked=False), fake_clock)
check("probe, stock card: ratio 0.5 and tf32 ratio 0.25", (r["ratio"], r["ratio_tf32"], r["fp16acc_supported"], r["device"]), (0.5, 0.25, True, "FakeCard"))
r = probe.run(FakeTorch(unlocked=True), fake_clock)
check("probe, unlocked card: ratio 1.0 and tf32 ratio 0.5", (r["ratio"], r["ratio_tf32"]), (1.0, 0.5))
r = probe.run(FakeTorch(fp16acc=False), fake_clock)
check("probe, torch without FP16 accumulation: only absolute TFLOPS, no ratio", (r["ratio"], r["ratio_tf32"], r["fp16acc_supported"], r["tflops"]["fp16_fp16acc"], r["tflops"]["fp16_fp32acc"] > 0), (None, None, False, None, True))
check("probe: no CUDA is reported, not raised", probe.run(FakeTorch(cuda=False), fake_clock), {"error": "no_cuda"})
ticks = iter(range(0, 10000, 30))
r = probe.run(FakeTorch(unlocked=True), lambda: float(next(ticks)))
check("probe: a slow card still finishes (at least one round per size under the time budget)", (r["ratio"], r["rounds"] >= 1), (1.0, True))

# ------------------------------------------------------------- a session without compute, and a failing nvidia-smi, skip too
for label, mut, why in [("the card shows load (a game or a compositor draws, no compute context)", lambda h, g: setattr(h, "util", "60"), "card_busy"),
                        ("an encode runs (encoder utilisation)", lambda h, g: setattr(h, "enc", "40"), "card_busy"),
                        ("pmon shows a graphics process with load", lambda h, g: setattr(h, "pmon", "# gpu pid type sm mem enc dec jpg ofa command\n 0 4242 G 12 3 0 0 - - game\n"), "card_in_use"),
                        ("nvidia-smi fails on the process list (not read as an idle card)", lambda h, g: setattr(h, "apps_rc", 1), "smi_failed")]:
    ctx, host, gate, clock, sd = world()
    mut(host, gate)
    check(f"skip: {label} -> exit 75, no bench, no container, no result file", skipped(ctx, host, gate, why), (75, True, True, True, True))
ctx, host, gate, clock, sd = world()
host.pmon_rc = 1
host.has_enc = False
host.util = "3"
check("an idle compositor (3 %), no pmon on this driver, no encoder field: the check runs", (run_exec(ctx)[0], result(sd)["verdict"]), (0, "ok"))
ctx, host, gate, clock, sd = world()
host.pmon = "# gpu pid type sm mem enc dec jpg ofa command\n 0 900 G - - - - - - Xorg\n"
check("a graphics process with no load (Xorg idle) does not block the check", run_exec(ctx)[0], 0)

# ---------------------------------------------- the gate ends the bench while the probe runs: stop at once, judge nothing
def skip_midrun(label, setup, why):
    ctx, host, gate, clock, sd = world()
    setup(host, gate)
    code, out = run_exec(ctx)
    check(f"midrun: {label} -> exit 75 ({why}), container removed, bench end called, no result file, nothing judged",
          (code, why in out, host.killed_in_run or why == "after", [p for _, p, _ in gate.calls][-1], host.calls[-1] if host.killed_in_run else None, os.path.exists(os.path.join(sd, "selfcheck.json"))),
          (75, True, True, "/bench/end", ["docker", "rm", "-f", sc.CONTAINER] if why != "after" else None, False))

skip_midrun("a person's session starts and the gate ends the bench", lambda h, g: setattr(h, "abort_with", lambda hh: g.state.update(bench=None)), "bench_ended")
skip_midrun("the gate reports a blocked card", lambda h, g: setattr(h, "abort_with", lambda hh: g.state.update(blocked="vr")), "vr")
skip_midrun("the operator's switch is turned on", lambda h, g: setattr(h, "abort_with", lambda hh: g.state.update(blocked="busy")), "busy")
skip_midrun("the power limit was changed under the probe", lambda h, g: setattr(h, "abort_with", lambda hh: setattr(hh, "limit", 100)), "cap_changed")
ctx, host, gate, clock, sd = world()
host.after_run = lambda h: gate.state.update(bench=None)
code, out = run_exec(ctx)
check("midrun: the bench ended in the last seconds of the run: the numbers are dropped (skip, no result file)", (code, "bench_ended" in out, os.path.exists(os.path.join(sd, "selfcheck.json"))), (75, True, False))
ctx, host, gate, clock, sd = world()
host.after_run = lambda h: setattr(h, "limit", 100)
check("midrun: the limit changed during the run: dropped", (run_exec(ctx)[0], os.path.exists(os.path.join(sd, "selfcheck.json"))), (75, False))
ctx, host, gate, clock, sd = world()
host.abort_with = lambda h: setattr(gate, "down", True)
code, out = run_exec(ctx)
check("midrun: the gate stops answering: the probe is stopped, nothing judged", (code, "gate_down" in out, host.killed_in_run), (75, True, True))
ctx, host, gate, clock, sd = world()
host.kbd = True
try:
    run_exec(ctx)
    interrupted = False
except KeyboardInterrupt:
    interrupted = True
dcalls = [c for c in host.calls if c[:2] == ["docker", "run"]]
check("SIGTERM during the probe: the container is removed (after it was started) and the bench is ended, power restored",
      (interrupted, host.calls.index(["docker", "rm", "-f", sc.CONTAINER], host.calls.index(dcalls[0])) > host.calls.index(dcalls[0]), [p for _, p, _ in gate.calls][-1], host.limit), (True, True, "/bench/end", 200))

# --------------------------------------------------------------------------- the cap the gate really gave
ctx, host, gate, clock, sd = world()
gate.clamp = 125
code, out = run_exec(ctx)
r = result(sd)
check("run: the gate clamped the cap to 125 W: recorded (cap_mismatch, cap_w 125), the ratio still judges, no baseline from this run",
      (code, r["verdict"], r["reasons"], r["cap_w"], os.path.exists(os.path.join(sd, "selfcheck_baseline.json"))), (0, "ok", ["cap_mismatch"], 125, False))

# ------------------------------------------------------- a throttle in the first of two probes is not lost
check("merge: the union of throttle bits, the worst temperature", (lambda m: (m["throttle_mask"], m["throttle_names"], m["temp_max_c"], m["samples"]))(
    sc.merge_summaries([{"samples": 2, "temp_max_c": 60.0, "power_draw_max_w": 120.0, "clocks_sm_busy_mhz": 1800, "throttle_mask": 0x44},
                        {"samples": 3, "temp_max_c": 66.0, "power_draw_max_w": 110.0, "clocks_sm_busy_mhz": 1700, "throttle_mask": 0x4}])),
      (0x44, ["sw_power_cap", "hw_thermal"], 66.0, 5))
check("merge: one summary or none", (sc.merge_summaries([{"samples": 1}]), sc.merge_summaries([None])), ({"samples": 1}, None))
ctx, host, gate, clock, sd = world(good(0.70), good(0.74))
host.masks = ["0x0000000000000044", "0x0000000000000004"]
code, out = run_exec(ctx)
check("run: hardware thermal throttle in the first run only, median ratio low: cannot judge (error throttled_hw), not degraded",
      (code, result(sd)["reasons"], result(sd)["run"]["throttle_names"]), (2, ["throttled_hw"], ["sw_power_cap", "hw_thermal"]))

# ---------------------------------------------- remembering that the card was unlocked, and what happens when the upgrade removes it
ctx, host, gate, clock, sd = world()
run_exec(ctx)
b = json.load(open(os.path.join(sd, "selfcheck_baseline.json")))
check("a ratio-validated ok run writes the baseline with the unlock_seen_gpu note", (b["unlock_seen_gpu"], b["tflops_fp16_fp32acc"], b["cap_w"]), ("NVIDIA GeForce RTX 3060 Ti", 30.0, 130))
host.pkgs.clear(); host.files["/proc/cmdline"] = "ro"; host.files.pop("/sys/module/gpu_unlock/parameters/targets"); host.paths.discard("/sys/module/gpu_unlock")
host.probes = [good(0.5, 0.25)]
host.probe_i = 0
code, out = run_exec(ctx)
r = result(sd)
check("an upgrade removed the package AND the boot line: still expected, measured, degraded (not 'unlock not expected')",
      (code, r["verdict"], r["unlock_expected"], r["reasons"]), (1, "degraded", True, ["module_not_loaded", "param_missing", "ratio_low"]))
ctx, host, gate, clock, sd = world()
host.pkgs.clear(); host.files["/proc/cmdline"] = "ro"; host.files.pop("/sys/module/gpu_unlock/parameters/targets"); host.paths.discard("/sys/module/gpu_unlock")
code, out = run_exec(ctx)
check("the same host that never had the unlock (no marker): ok, not expected", (code, result(sd)["unlock_expected"]), (0, False))
ctx, host, gate, clock, sd = world()
sc.write_json(os.path.join(sd, "selfcheck_baseline.json"), {"gpu": "NVIDIA GeForce RTX 3060 Ti", "cap_w": 130, "tflops_fp16_fp32acc": 29.0, "at": 5})
run_exec(ctx)
b = json.load(open(os.path.join(sd, "selfcheck_baseline.json")))
check("an older baseline (no note) learns that the card was unlocked and keeps its numbers", (b["unlock_seen_gpu"], b["tflops_fp16_fp32acc"], b["at"]), ("NVIDIA GeForce RTX 3060 Ti", 29.0, 5))
ctx, host, gate, clock, sd = world(good(0.97, t=20.0))
sc.write_json(os.path.join(sd, "selfcheck_baseline.json"), {"gpu": "NVIDIA GeForce RTX 3060 Ti", "cap_w": 130, "tflops_fp16_fp32acc": 30.0, "unlock_seen_gpu": "NVIDIA GeForce RTX 3060 Ti"})
code, out = run_exec(ctx)
check("run: a good ratio but 67 % of the baseline TFLOPS: degraded tflops_low, exit 1", (code, result(sd)["reasons"], result(sd)["tflops_vs_baseline"]), (1, ["tflops_low"], 0.667))

# the real Host class, against harmless local commands
h = sc.Host()
rc, out, samples = h.run_sampled([sys.executable, "-c", "import time; time.sleep(0.8); print('{\"a\": 1}')"], 10, ["echo", "7, 8"], 0.1)
check("Host.run_sampled: output, exit code and samples taken while it ran", (rc, out.strip(), len(samples) >= 3, samples[0]), (0, '{"a": 1}', True, "7, 8"))
rc, out, samples = h.run_sampled([sys.executable, "-c", "import time; time.sleep(30)"], 1, ["echo", "x"], 0.1)
check("Host.run_sampled: a run past its timeout is killed (124)", (rc, out), (124, ""))
# the real Host.run_sampled stops its process when abort() answers, and on an interrupt (SIGTERM becomes KeyboardInterrupt)
pidf = tempfile.mktemp(prefix="pid-")
prog = f"import os,time; open({pidf!r},'w').write(str(os.getpid())); time.sleep(30)"
def alive(pid):
    try:
        os.kill(pid, 0)
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except (OSError, ValueError):
        return False
calls = []
def abort_after_two():
    calls.append(1)
    return "bench_ended" if len(calls) >= 2 else None
try:
    h.run_sampled([sys.executable, "-c", prog], 20, ["echo", "x"], 0.1, abort=abort_after_two, abort_every=0.2)
    got = None
except sc.Skipped as e:
    got = e.why
time.sleep(0.3)
pid = int(open(pidf).read())
check("Host.run_sampled: abort() returns a word -> Skipped(word) and the process is killed", (got, alive(pid)), ("bench_ended", False))
def boom_kbd():
    raise KeyboardInterrupt
try:
    h.run_sampled([sys.executable, "-c", prog], 20, ["echo", "x"], 0.1, abort=boom_kbd, abort_every=0.2)
    got = None
except KeyboardInterrupt:
    got = "kbd"
time.sleep(0.3)
pid = int(open(pidf).read())
check("Host.run_sampled: an interrupt (SIGTERM) kills the process too, never leaves it loading the card", (got, alive(pid)), ("kbd", False))
os.unlink(pidf)
check("Host.cmd: a missing binary is 127, not an exception", h.cmd(["/nonexistent-binary-xyz"]), (127, ""))
check("Host.run_sampled: a missing binary is 127", h.run_sampled(["/nonexistent-binary-xyz"], 5, ["echo"])[0], 127)

print()
print(f"{len(FAIL)} FAILED: {FAIL}" if FAIL else "all ok")
sys.exit(1 if FAIL else 0)
