#!/usr/bin/env python3
"""Recreate the stacks of a deploy in parallel, as many at once as the Docker host can take (called by ops/redeploy_router.sh).

  ops/deploy_sched.py --host user@host --results FILE [--phases FILE] [--logdir DIR] stack ...

Each stack is `ops/recreate_hermes.sh <stack>` on the host over ssh, as before; the script itself still refuses an awake stack (exit 3) and
verifies the one it recreates. What is new is how many run at once: the next one starts whenever ALL of these hold, re-checked every
DEPLOY_POLL_S (5) seconds from a read of the host (load, /proc/meminfo, `docker ps`, the in-flight brains' cgroup memory):
  * the 1-minute load average per CPU is below DEPLOY_LOAD_PER_CPU (0.75);
  * MemAvailable, minus what the recreates in flight have still to take, minus this stack's need, stays above the waker's reserve_mb;
    a stack's need is its biggest brain peak_mb in the host's telemetry (~/.local/state/telemetry.db, last 14 days), never below its
    est_brain_mb in stacks.json, DEPLOY_DEFAULT_NEED_MB (1000) when telemetry has no row;
  * the awake on-demand brains (people's awake stacks + recreates in flight, always-on brains excluded as the waker counts them) stay
    within the waker's max_awake (both read from the host's ops/wake/stacks.json, the waker's own config);
  * at least DEPLOY_LAUNCH_GAP_S (3) since the previous boot started, so the host read shows it first (measured: with load at 0.25/CPU
    of 16 and 9 GB spare, the old 10 s gap, not the host, set the pace: 11 stacks took ~170 s, one boot alone 33 s, 3-4 at once 44 s);
  * fewer than DEPLOY_MAX_INFLIGHT in flight, when set (1 = the old one-by-one order; default 0 = no cap besides the above).
With nothing in flight one is started anyway (never fewer than one: the deploy always moves on, as the serial loop did). A stack whose brain
is already running costs nothing (the script refuses it at once): it is started at once, without the checks or the gap, and takes no gap. A failed recreate never stops the others.

After a recreate passes, the waker puts the stack back to sleep (waker.py sleep_after_recreate: nobody used it, the script released its
lock); this script only watches for that, to time it, while other recreates still run: a stack it is watching takes no max_awake slot (it is idle and
about to stop; its memory is still counted through MemAvailable), and the deploy ends when the last recreate ends, leaving the stops it did not see as
"pending" (DEPLOY_WAIT_STOPS=1 waits for them, up to DEPLOY_STOP_WAIT_S, 150 s, each). An always-on stack stays up by design.

Output: each stack's lines as it ends (prefixed with its name), a summary table, FILE with one `<stack> <rc>` line per stack for
redeploy_router.sh (the update_pending notes stay there), and with --phases the per-stack phase lines for the deploy log
(ops/deploy_log.py): recreate (with result ok / awake / failed), health (from recreate_hermes.sh's `timing :` line), stop.
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deploy_log  # noqa: E402

ENV = os.environ.get
CFG_DEFAULTS = {"load_per_cpu": float(ENV("DEPLOY_LOAD_PER_CPU", "0.75")), "reserve_mb": 1500, "max_awake": 6,
                "default_need_mb": int(ENV("DEPLOY_DEFAULT_NEED_MB", "1000")), "launch_gap_s": float(ENV("DEPLOY_LAUNCH_GAP_S", "3")),
                "poll_s": float(ENV("DEPLOY_POLL_S", "5")), "stop_wait_s": float(ENV("DEPLOY_STOP_WAIT_S", "150")),
                "wait_stops": ENV("DEPLOY_WAIT_STOPS", "0") == "1",
                "max_inflight": int(ENV("DEPLOY_MAX_INFLIGHT", "0"))}

# One read of the host's config: the waker's budget and stacks (stacks.json), CPU count, and the brains' memory peaks from telemetry.
PROBE_CONFIG = r'''
import json, os, sqlite3, time
c = json.load(open(os.path.expanduser("~/aibridge/ops/wake/stacks.json")))
out = {"ncpu": os.cpu_count() or 1, "reserve_mb": c.get("reserve_mb", 1500), "max_awake": c.get("max_awake", 4), "stacks": {}, "peaks": {}}
for s in c.get("stacks", []):
    out["stacks"][s["name"]] = {"brain": s.get("brain"), "always": bool(s.get("always")), "est_brain_mb": s.get("est_brain_mb")}
try:
    db = sqlite3.connect("file:" + os.path.expanduser("~/.local/state/telemetry.db") + "?mode=ro", uri=True, timeout=5)
    for name, peak in db.execute("SELECT stack, MAX(peak_mb) FROM res WHERE role = 'brain' AND ts > ? GROUP BY stack", (time.time() - 14 * 86400,)):
        out["peaks"][name] = peak
except Exception as exc:
    out["telemetry_error"] = type(exc).__name__
print(json.dumps(out))
'''
# One read of the host's state, every poll: load, free memory, running containers, the memory of the named containers (cgroup v2).
PROBE_STATE = r'''
import json, subprocess, sys
la = open("/proc/loadavg").read().split()
mem = next(int(l.split()[1]) // 1024 for l in open("/proc/meminfo") if l.startswith("MemAvailable:"))
ps = subprocess.run(["docker", "ps", "--format", "{{.ID}} {{.Names}}", "--no-trunc"], capture_output=True, text=True)
running, used = {}, {}
for line in ps.stdout.splitlines():
    cid, _, name = line.partition(" ")
    running[name] = cid
for name in sys.argv[1:]:
    cid = running.get(name)
    if cid:
        try:
            used[name] = int(open(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope/memory.current").read()) // (1024 * 1024)
        except (OSError, ValueError):
            used[name] = 0
print(json.dumps({"load1": float(la[0]), "mem_avail_mb": mem, "running": sorted(running), "used": used, "ok": ps.returncode == 0}))
'''


def brain_of(name, info):
    """The brain container of a stack: stacks.json's "brain", else the usual name (hernik is the main compose's container)."""
    b = (info or {}).get("brain")
    return b or ("aibridge-hermes-agent" if name == "hernik" else f"stack-{name}-hermes")


def need_mb(name, peaks, info, default):
    """Memory a recreate of this stack may take: its telemetry peak, never below its est_brain_mb; `default` with no telemetry row."""
    est = int((info or {}).get("est_brain_mb") or 0)
    peak = peaks.get(name)
    base = int(round(peak)) if isinstance(peak, (int, float)) and peak > 0 else default
    return max(base, est)


def admit(cand, cand_need, cand_always, st, inflight, cfg):
    """(start now?, why). st: {"load1", "ncpu", "mem_avail_mb", "awake": set of on-demand stacks whose brain runs}. inflight: {stack: {"need",
    "used", "always"}} for the recreates still running. cfg: load_per_cpu, reserve_mb, max_awake. Pure: tested offline."""
    if not inflight:
        return True, "first in flight (never fewer than one)"
    if cfg.get("max_inflight") and len(inflight) >= cfg["max_inflight"]:
        return False, f"{len(inflight)} in flight = DEPLOY_MAX_INFLIGHT"
    per_cpu = st["load1"] / max(1, st["ncpu"])
    if per_cpu >= cfg["load_per_cpu"]:
        return False, f"load {per_cpu:.2f}/CPU >= {cfg['load_per_cpu']}"
    still = sum(max(0, f["need"] - f.get("used", 0)) for f in inflight.values())
    left = st["mem_avail_mb"] - still - cand_need
    if left < cfg["reserve_mb"]:
        return False, f"memory: {st['mem_avail_mb']} MB available - {still} still to take by the recreates in flight - {cand_need} for {cand} = {left} < reserve {cfg['reserve_mb']}"
    awake = set(st["awake"]) | {n for n, f in inflight.items() if not f.get("always")}
    if not cand_always:
        awake.add(cand)
    if len(awake) > cfg["max_awake"]:
        return False, f"awake brains would be {len(awake)} > max_awake {cfg['max_awake']}"
    return True, f"load {per_cpu:.2f}/CPU, {left} MB left above the reserve, {len(awake)} awake"


def parse_timing(text):
    """{"up", "health", "warm", "verify", "total"} seconds from recreate_hermes.sh's last `timing :` line ({} when there is none)."""
    lines = [l for l in text.splitlines() if l.startswith("timing :")]
    return {k: float(v) for k, v in deploy_log.parse_kv(lines[-1]).items() if v.replace(".", "", 1).isdigit()} if lines else {}


def result_of(rc):
    return "ok" if rc == 0 else "awake" if rc == 3 else "failed"


class Host:
    def __init__(self, host):
        self.host = host

    def py(self, code, *args, timeout=60):
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", self.host, "python3", "-", *args], input=code, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[-300:] or f"ssh exit {r.returncode}")
        return json.loads(r.stdout)

    def recreate(self, stack, log_path):
        log = open(log_path, "w")
        return subprocess.Popen(["ssh", "-n", "-o", "BatchMode=yes", self.host, f"cd ~/aibridge && ops/recreate_hermes.sh {stack}"],
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True), log


def run(stacks, host, cfg, results_path, phases_path=None, logdir=None, out=print, clock=time.time, sleep=time.sleep):
    t_all = clock()
    try:
        conf = host.py(PROBE_CONFIG)
    except Exception as exc:
        out(f"could not read the host's waker config and telemetry ({exc}): using reserve {cfg['reserve_mb']} MB, max_awake {cfg['max_awake']}")
        conf = {"ncpu": 1, "stacks": {}, "peaks": {}}
    cfg = {**cfg, **{k: conf[k] for k in ("reserve_mb", "max_awake") if k in conf}}
    info, peaks = conf.get("stacks", {}), conf.get("peaks", {})
    if conf.get("telemetry_error"):
        out(f"telemetry not readable on the host ({conf['telemetry_error']}): needs from stacks.json / {cfg['default_need_mb']} MB")
    needs = {s: need_mb(s, peaks, info.get(s), cfg["default_need_mb"]) for s in stacks}
    out(f"parallel recreates: load < {cfg['load_per_cpu']}/CPU of {conf.get('ncpu')}, reserve {cfg['reserve_mb']} MB, max_awake {cfg['max_awake']}; "
        f"needs " + ", ".join(f"{s} {needs[s]} MB" for s in stacks))
    logdir = logdir or os.path.dirname(os.path.abspath(results_path))
    queue, inflight, watching, done = list(stacks), {}, {}, {}
    last_launch, last_why = -1e9, None
    phases = []

    def phase(name, secs, **kv):
        phases.append(deploy_log.phase_line(name, secs, **kv))

    while queue or inflight or (watching and cfg.get("wait_stops")):
        now = clock()
        for s, f in list(inflight.items()):   # recreates that ended
            rc = f["proc"].poll()
            if rc is None:
                continue
            f["log"].close()
            text = open(f["path"], errors="replace").read()
            secs = now - f["t0"]
            res = result_of(rc)
            out(f"== {s}: {res} (exit {rc}, {secs:.0f} s)")
            for line in text.splitlines():
                out(f"  [{s}] {line}")
            tm = parse_timing(text)
            phase("recreate", secs, stack=s, result=res, rc=rc)
            if "health" in tm:
                phase("health", tm["health"], stack=s)
            done[s] = {"rc": rc, "secs": secs, "result": res, "stop": None}
            del inflight[s]
            if rc == 0:
                if info.get(s, {}).get("always"):
                    done[s]["stop"] = "always-on"
                else:
                    watching[s] = now
        try:
            st = host.py(PROBE_STATE, *[brain_of(s, info.get(s)) for s in inflight], timeout=30)
        except Exception as exc:
            out(f"could not read the host's state ({exc}); retrying")
            sleep(cfg["poll_s"]); continue
        running = set(st.get("running", []))
        for s, t_end in list(watching.items()):   # the waker's stop after a passed recreate
            if brain_of(s, info.get(s)) not in running:
                phase("stop", now - t_end, stack=s, result="stopped"); done[s]["stop"] = f"stopped after {now - t_end:.0f} s"
                del watching[s]
            elif now - t_end > cfg["stop_wait_s"]:
                phase("stop", now - t_end, stack=s, result="left-up"); done[s]["stop"] = "still up (the waker's idle rule stops it)"
                out(f"{s}: still up {cfg['stop_wait_s']:.0f} s after its recreate (an older waker keeps it a whole idle period)")
                del watching[s]
        for s, f in inflight.items():
            f["used"] = st.get("used", {}).get(brain_of(s, info.get(s)), 0)
        # a recreated stack the waker is about to stop (watching) is idle: it takes no max_awake slot (its real memory is in MemAvailable)
        awake = {n for n in set(info) | set(stacks) if not info.get(n, {}).get("always") and brain_of(n, info.get(n)) in running and n not in watching}
        state = {"load1": st["load1"], "ncpu": conf.get("ncpu", 1), "mem_avail_mb": st["mem_avail_mb"], "awake": awake}
        # An awake stack is started at once, without the gap: its recreate only refuses it (exit 3) and takes no CPU or memory.
        pick = next((s for s in queue if brain_of(s, info.get(s)) in running), None)
        why, boots = "awake: its recreate refuses it at once", False
        if not pick and queue and now - last_launch >= cfg["launch_gap_s"]:
            for s in queue:
                ok, why = admit(s, needs[s], bool(info.get(s, {}).get("always")), state, inflight, cfg)
                if ok:
                    pick, boots = s, True
                    break
            if not pick and why != last_why:
                out(f"waiting ({len(queue)} left, {len(inflight)} in flight): {why}")
                last_why = why
        if pick:
            queue.remove(pick)
            path = os.path.join(logdir, f"recreate-{pick}.log")
            proc, log = host.recreate(pick, path)
            inflight[pick] = {"proc": proc, "log": log, "path": path, "t0": clock(), "need": needs[pick], "used": 0,
                              "always": bool(info.get(pick, {}).get("always"))}
            if boots:
                last_launch, last_why = clock(), None
            out(f"-> {pick} started ({why}); in flight: {', '.join(inflight)}")
            continue
        if queue or inflight or watching:
            sleep(cfg["poll_s"])
    wall = clock() - t_all
    for s, t_end in watching.items():   # not waited for (DEPLOY_WAIT_STOPS=1 waits): the waker stops it and logs when
        phase("stop", clock() - t_end, stack=s, result="pending"); done[s]["stop"] = "the waker stops it (not waited for)"
    phase("recreates", wall, stacks=len(stacks))
    with open(results_path, "w") as f:
        for s in stacks:
            f.write(f"{s} {done[s]['rc']}\n")
    if phases_path:
        with open(phases_path, "a") as f:
            f.write("\n".join(phases) + "\n")
    out("")
    out(f"recreates: {len(stacks)} stacks in {wall:.0f} s")
    for s in stacks:
        d = done[s]
        out(f"  {s:<12} {d['result']:<7} {d['secs']:6.0f} s" + (f"  {d['stop']}" if d["stop"] else ""))
    return 0 if all(d["rc"] == 0 for d in done.values()) else 3 if all(d["rc"] in (0, 3) for d in done.values()) else 1


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", required=True); ap.add_argument("--results", required=True)
    ap.add_argument("--phases"); ap.add_argument("--logdir"); ap.add_argument("stacks", nargs="+")
    a = ap.parse_args(argv)
    for s in a.stacks:
        if not s.replace("-", "").replace("_", "").replace(".", "").isalnum():
            print(f"bad stack name {s!r}", file=sys.stderr); return 2
    return run(a.stacks, Host(a.host), dict(CFG_DEFAULTS), a.results, a.phases, a.logdir, out=lambda m: print(m, flush=True))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
