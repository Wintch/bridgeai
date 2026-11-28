#!/usr/bin/env python3
"""Offline test of ops/deploy_sched.py (no ssh, no docker): the admission decisions, the memory need per stack, the `timing :` line, and a whole
run against a simulated Docker host (stacks booting, taking memory, failing, found awake, put back to sleep by the waker).

  python3 -I ops/deploy_sched_selftest.py
"""
import atexit, os, shutil, sys, tempfile
tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-"); atexit.register(shutil.rmtree, tempfile.tempdir, True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deploy_sched as ds  # noqa: E402

ok = True
def chk(cond, what, extra=""):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what + ("" if cond else f"\n     {extra}"), flush=True)

CFG = {"load_per_cpu": 0.75, "reserve_mb": 1500, "max_awake": 6}
def st(load=2.0, mem=10000, awake=()):
    return {"load1": load, "ncpu": 16, "mem_avail_mb": mem, "awake": set(awake)}
A = ds.admit

# ---- admission
chk(A("a", 1000, False, st(load=15.9, mem=100), {}, CFG)[0], "admit: nothing in flight -> start even when the gates say no (never fewer than one)")
chk(A("b", 1000, False, st(), {"a": {"need": 1000, "used": 900}}, CFG)[0], "admit: light load, plenty of memory, few awake -> start")
r = A("b", 1000, False, st(load=12.0), {"a": {"need": 1000, "used": 900}}, CFG)
chk(not r[0] and "load" in r[1], "admit: load 12 on 16 CPUs = 0.75/CPU -> wait (the limit itself is not allowed)", r)
chk(A("b", 1000, False, st(load=11.9), {"a": {"need": 1000, "used": 900}}, CFG)[0], "admit: load 11.9/16 is under 0.75/CPU -> start")
chk(A("b", 1000, False, st(mem=3400), {"a": {"need": 1000, "used": 100}}, CFG)[0], "admit: 3400 - 900 still to come - 1000 = 1500 = reserve -> start (stays at the reserve)")
r = A("b", 1000, False, st(mem=3399), {"a": {"need": 1000, "used": 100}}, CFG)
chk(not r[0] and "memory" in r[1] and "900 still to take" in r[1], "admit: one MB less -> wait, and the reason names what the boot in flight still takes", r)
chk(A("b", 1000, False, st(mem=2400), {"a": {"need": 1000, "used": 1000}}, CFG)[0] is False and
    A("b", 1000, False, st(mem=2400), {"a": {"need": 1000, "used": 1200}}, CFG)[0] is False,
    "admit: a recreate in flight that already took its need adds nothing; above its need it is not counted negative")
chk(A("b", 1000, False, st(mem=2500), {"a": {"need": 1000, "used": 1200}}, CFG)[0], "admit: 2500 - 0 - 1000 = 1500 -> start")
r = A("f", 500, False, st(awake={"p1", "p2", "p3", "p4"}), {"a": {"need": 500, "used": 500}}, CFG)
chk(r[0], "admit: 4 people awake + 1 in flight + this one = 6 = max_awake -> start", r)
r = A("g", 500, False, st(awake={"p1", "p2", "p3", "p4", "p5"}), {"a": {"need": 500, "used": 500}}, CFG)
chk(not r[0] and "max_awake" in r[1], "admit: 5 awake + 1 in flight + this one = 7 -> wait", r)
r = A("a", 500, False, st(awake={"p1", "p2", "p3", "p4", "a"}), {"x": {"need": 500, "used": 500}}, CFG)
chk(r[0], "admit: a stack already counted awake (its own container up) is not counted twice", r)
r = A("h", 500, True, st(awake={"p1", "p2", "p3", "p4", "p5"}), {"a": {"need": 500, "used": 500}}, CFG)
chk(r[0], "admit: an always-on stack takes no max_awake slot (the waker counts them the same way)", r)
r = A("g", 500, False, st(awake={"p1", "p2", "p3", "p4"}), {"a": {"need": 500, "used": 500, "always": True}}, CFG)
chk(r[0], "admit: an always-on recreate in flight takes no slot either", r)
r = A("b", 500, False, st(), {"a": {"need": 500, "used": 500}}, {**CFG, "max_inflight": 1})
chk(not r[0] and "DEPLOY_MAX_INFLIGHT" in r[1], "admit: DEPLOY_MAX_INFLIGHT=1 gives the old one-by-one order", r)

# ---- memory need per stack
chk(ds.need_mb("a", {"a": 1868.7}, {"est_brain_mb": 600}, 1000) == 1869, "need: the telemetry peak, rounded")
chk(ds.need_mb("a", {"a": 116.1}, {"est_brain_mb": 600}, 1000) == 600, "need: never below the stack's est_brain_mb (a peak seen only early in a boot)")
chk(ds.need_mb("a", {}, {"est_brain_mb": 600}, 1000) == 1000, "need: no telemetry row -> the default")
chk(ds.need_mb("a", {"a": None}, None, 1000) == 1000, "need: a NULL peak and no stacks.json entry -> the default")

# ---- names and the timing line
chk(ds.brain_of("hernik", None) == "aibridge-hermes-agent" and ds.brain_of("x", None) == "stack-x-hermes" and ds.brain_of("x", {"brain": "b"}) == "b",
    "brain_of: stacks.json's brain, else the usual container names")
t = ds.parse_timing("before : x\nPASS: ok\ntiming : up=3 health=25 warm=2 verify=10 total=45\n")
chk(t == {"up": 3, "health": 25, "warm": 2, "verify": 10, "total": 45}, "timing: the line recreate_hermes.sh prints at its end", t)
chk(ds.parse_timing("timing : total=1\n") == {"total": 1} and ds.parse_timing("no timing here") == {}, "timing: partial or missing line")
chk([ds.result_of(c) for c in (0, 3, 1, 2, -9)] == ["ok", "awake", "failed", "failed", "failed"], "result_of: exit 0 ok, 3 awake, anything else failed")

# ---- a whole run on a simulated host
class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t
    def sleep(self, s): self.t += s

class FakeProc:
    def __init__(self, host, stack):
        self.host, self.stack = host, stack
    def poll(self):
        return self.host.rc.get(self.stack)

class FakeHost:
    """Each recreate boots its brain for `boot` seconds (memory grows to its need), then ends with its exit code; a passed one is stopped by
    the "waker" `stop_after` seconds later. People's stacks in `people` are awake the whole time."""
    def __init__(self, clock, plan, people=(), mem=10000, load=2.0, conf=None, stop_after=40, always=()):
        self.c, self.plan, self.people, self.mem0, self.load = clock, plan, set(people), mem, load
        self.stop_after, self.started, self.ended, self.rc, self.max_parallel, self.logdir = stop_after, {}, {}, {}, 0, None
        self.always = set(always)
        self.conf = conf or {"ncpu": 16, "reserve_mb": 1500, "max_awake": 6,
                             "stacks": {s: {"always": s in self.always} for s in list(plan) + list(people)}, "peaks": {s: plan[s][2] for s in plan}}
    def advance(self):
        for s, t0 in self.started.items():
            boot, rc, need = self.plan[s]
            if s not in self.rc and self.c.t - t0 >= boot:
                self.rc[s] = rc; self.ended[s] = self.c.t
                with open(os.path.join(self.logdir, f"recreate-{s}.log"), "w") as f:
                    f.write(("PASS: fine\n" if rc == 0 else "running (awake)\n" if rc == 3 else "FAIL: boom\n") + f"timing : up=1 health={boot - 5:.0f} total={boot:.0f}\n")
    def up(self, s):
        if s in self.people:
            return True
        if s not in self.started or self.plan[s][1] == 3:
            return False
        if s not in self.rc:
            return True
        return self.plan[s][1] == 0 and (s in self.always or self.c.t - self.ended[s] < self.stop_after)
    def py(self, code, *args, timeout=60):
        self.advance()
        if "telemetry" in code:
            return self.conf
        running = [ds.brain_of(s, None) for s in set(self.plan) | self.people if self.up(s)]
        used = {}
        for s in self.started:
            if self.up(s) and s not in self.rc:
                used[ds.brain_of(s, None)] = int(self.plan[s][2] * min(1.0, (self.c.t - self.started[s]) / max(1, self.plan[s][0])))
        mem = self.mem0 - sum(self.plan[s][2] for s in self.plan if self.up(s) and s in self.rc) - sum(used.values())
        inflight = sum(1 for s in self.started if s not in self.rc)
        self.max_parallel = max(self.max_parallel, inflight)
        return {"load1": self.load + 1.5 * inflight, "mem_avail_mb": mem, "running": running, "used": {a: used.get(a, 0) for a in args}, "ok": True}
    def recreate(self, stack, log_path):
        self.logdir = os.path.dirname(log_path)
        self.started[stack] = self.c.t
        if self.plan[stack][1] == 3:   # refused at once: the brain is up (a person's)
            self.rc[stack] = 3; self.ended[stack] = self.c.t
            open(log_path, "w").write(f"stack-{stack}-hermes is running (awake): not recreating a live container. Wait for it to sleep.\ntiming : total=0\n")
        return FakeProc(self, stack), open(os.devnull, "w")

def go(plan, **kw):
    clk = Clock(); h = FakeHost(clk, plan, **kw); lines = []
    d = tempfile.mkdtemp(); res, phases = os.path.join(d, "results"), os.path.join(d, "phases")
    cfg = {**ds.CFG_DEFAULTS, "launch_gap_s": 10, "poll_s": 5, "stop_wait_s": 150, "max_inflight": 0}
    rc = ds.run(list(plan), h, cfg, res, phases, d, out=lines.append, clock=clk, sleep=clk.sleep)
    got = dict(l.split() for l in open(res))
    import deploy_log
    ph = deploy_log.read_phases(phases)
    return rc, got, ph, lines, h, clk

# seven sleeping stacks that fit: all at once (spaced by the launch gap), all verified, all stopped by the waker
plan = {f"s{i}": (60, 0, 800) for i in range(7)}
rc, got, ph, lines, h, clk = go(plan, people=("p1",), mem=12000)
chk(rc == 0 and set(got.values()) == {"0"}, "run: every stack recreated (exit 0, results file)", (rc, got))
chk(h.max_parallel >= 5, f"run: several at once when the host can take them (peak {h.max_parallel} in flight)", h.max_parallel)
chk(clk.t - 1000 < 7 * 60, f"run: faster than one by one ({clk.t - 1000:.0f} s for 7 x 60 s boots)", clk.t)
rec = [p for p in ph if p["name"] == "recreate"]; stops = [p for p in ph if p["name"] == "stop"]; heal = [p for p in ph if p["name"] == "health"]
chk(len(rec) == 7 and all(p["result"] == "ok" for p in rec) and len(heal) == 7, "run: a recreate and a health phase per stack, with the result")
chk(len(stops) == 7 and all(p["result"] == "stopped" for p in stops), "run: each passed stack's stop by the waker is timed", stops)
chk(any(p["name"] == "recreates" for p in ph), "run: the wall time of all the recreates is a phase too")
# max_awake: 5 people awake leave one slot: strictly one at a time, never more than max_awake brains
rc, got, ph, lines, h, clk = go({f"s{i}": (60, 0, 800) for i in range(3)}, people=("p1", "p2", "p3", "p4", "p5"), mem=20000)
chk(rc == 0 and h.max_parallel == 1, "run: with 5 people awake (max_awake 6) the recreates go one at a time", h.max_parallel)
chk(any("max_awake" in l for l in lines), "run: the waiting reason is printed once it changes", lines[:12])
# memory: 3000 MB free, needs of 1000 -> only one at a time (1500 reserve), but the deploy still moves on
rc, got, ph, lines, h, clk = go({f"s{i}": (60, 0, 1000) for i in range(3)}, mem=3000)
chk(rc == 0 and h.max_parallel == 1 and len(got) == 3, "run: little memory -> one at a time, never zero", (h.max_parallel, got))
# a failure and an awake stack do not stop the others; exit 1 (a failure wins over awake)
rc, got, ph, lines, h, clk = go({"a": (30, 0, 500), "b": (30, 1, 500), "c": (0, 3, 500), "d": (30, 0, 500)}, mem=12000)
chk(rc == 1 and got == {"a": "0", "b": "1", "c": "3", "d": "0"}, "run: a failed recreate does not stop the others; each stack keeps its own exit code", (rc, got))
chk(any("[b] FAIL: boom" in l for l in lines) and any(l.startswith("== b: failed") for l in lines), "run: a failed stack's own lines are printed, prefixed")
chk({p["stack"]: p["result"] for p in ph if p["name"] == "recreate"} == {"a": "ok", "b": "failed", "c": "awake", "d": "ok"}, "run: the phases carry ok / failed / awake")
chk(not any(p["name"] == "stop" and p["stack"] in ("b", "c") for p in ph), "run: no stop is awaited for a failed or awake stack")
rc, got, *_ = go({"a": (30, 0, 500), "c": (0, 3, 500)}, mem=12000)
chk(rc == 3, "run: awake but no failure -> exit 3")
# an older waker that keeps the stack up: the deploy does not wait forever, it says so
rc, got, ph, lines, h, clk = go({"a": (30, 0, 500)}, stop_after=10_000)
chk(rc == 0 and [p["result"] for p in ph if p["name"] == "stop"] == ["left-up"] and any("still up" in l for l in lines),
    "run: a stack the waker does not stop is reported left up after DEPLOY_STOP_WAIT_S")
# an always-on stack stays up by design: no stop awaited
rc, got, ph, lines, h, clk = go({"hx": (30, 0, 500)}, always=("hx",))
chk(rc == 0 and not any(p["name"] == "stop" for p in ph) and any("always-on" in l for l in lines), "run: an always-on stack is not expected to stop")

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
