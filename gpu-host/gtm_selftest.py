#!/usr/bin/env python3
"""gtm.py, gpu_outside.py, the gate's "outside" field, gpu_watch's gpu-outside alert and bench_gate's per-job recording, offline.
python3 gtm_selftest.py"""
import atexit, importlib.util, json, os, re, shutil, stat, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gtm  # noqa: E402
fails = []
tmp = tempfile.mkdtemp(prefix="gtm-selftest-"); atexit.register(shutil.rmtree, tmp, True)


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


GiB = 1024 ** 3
def proc(pid, name, vram, gpu=0.0, eng=None):
    return {"pid": pid, "name": name, "vram_bytes": vram, "gpu_pct": gpu, "engines": eng or {}}

# ---- container ids
cid = "a" * 64
check("cgroup v2 docker scope gives the container id", gtm.container_id_of(f"0::/system.slice/docker-{cid}.scope\n") == cid)
check("cgroup v1 /docker/<id> gives the container id", gtm.container_id_of(f"12:memory:/docker/{cid}\n") == cid)
check("a host process has no container", gtm.container_id_of("0::/user.slice/user-1000.slice/session-2.scope\n") is None)
pdir = os.path.join(tmp, "proc", "42"); os.makedirs(pdir)
open(os.path.join(pdir, "cgroup"), "w").write(f"0::/system.slice/docker-{cid}.scope\n")
check("container_of names it from docker's list", gtm.container_of(42, {cid: "imggen"}, proc=os.path.join(tmp, "proc")) == "imggen")
check("a container docker does not name is '?'", gtm.container_of(42, {}, proc=os.path.join(tmp, "proc")) == "?")
check("a pid with no /proc entry is the host", gtm.container_of(43, {cid: "x"}, proc=os.path.join(tmp, "proc")) == "")

# ---- fold_record
samples = [{"processes": [proc(1, "python3", 3 * GiB, 20, {"compute": 20}), proc(2, "Xorg", 36 * 2 ** 20)]},
           {"processes": [proc(1, "python3", 7 * GiB, 100, {"compute": 100}), proc(3, "ffmpeg", 300 * 2 ** 20, 30, {"encoder": 55, "decoder": 10}),
                          proc(4, "idle", 0, 0)]},
           {"processes": "broken"}, {}]
where = {1: "imggen", 2: "", 3: "transcoder"}.get
rows = gtm.fold_record(samples, lambda p: where(p, ""))
check("fold: biggest VRAM first, peak per process", rows[0]["name"] == "python3" and rows[0]["vram_peak_mib"] == 7168 and rows[0]["container"] == "imggen", rows)
check("fold: peak engines kept per engine", any(r["name"] == "ffmpeg" and r["engines_peak"] == {"decoder": 10.0, "encoder": 55.0} for r in rows), rows)
check("fold: a process with no VRAM and no load is left out", all(r["name"] != "idle" for r in rows))
check("fold: broken snapshots are skipped", len(rows) == 3, rows)
rec = os.path.join(tmp, "r.jsonl")
open(rec, "w").write(json.dumps(samples[0]) + "\n{half a line\n" + json.dumps(samples[1]) + "\n")
check("read_record skips a half-written line", len(gtm.read_record(rec)) == 2)

# ---- classify
SVCS = {"imggen", "transcoder", "llm", "resolve"}
ALLOW = r"Xorg|sunshine|chrom"
idle = {"services": {"imggen": {"running": False, "leases": 0}, "transcoder": {"running": False, "leases": 0}}, "bench": None, "sleep_why": []}
busy = {"services": {"imggen": {"running": True, "leases": 1}}, "bench": None, "sleep_why": ["running:imggen"]}
ext = {"resolve": re.compile(r"^resolve$")}
c = lambda procs, st=idle: gtm.classify(procs, st, SVCS, ALLOW, 400, ext)
check("a running, leased gate service is fine", c([("imggen", "python3", 7000)], busy) == [])
check("a gate service's container with no lease and not running is service_not_leased", c([("imggen", "python3", 7000)]) == [("service_not_leased", "imggen", "python3", 7000)])
check("a service the gate is starting is fine", c([("transcoder", "ffmpeg", 300)], dict(idle, sleep_why=["starting:transcoder"])) == [])
check("a place container is fine", c([("hernikdoc", "game", 3000), ("place-hermic-desktop", "x", 100)]) == [])
check("another container is unknown_container", c([("stack-foo-hermes", "python3", 500)]) == [("unknown_container", "stack-foo-hermes", "python3", 500)])
check("a container docker does not name is unknown_container", c([("?", "python3", 500)])[0][0] == "unknown_container")
check("a small desktop program on the host is fine", c([("", "Xorg", 36), ("", "sunshine", 137)]) == [])
check("a desktop program over the limit is host_process", c([("", "chrome", 900)]) == [("host_process", "", "chrome", 900)])
check("any other host program is host_process", c([("", "python3", 5000)]) == [("host_process", "", "python3", 5000)])
check("host programs during a gate bench are fine", c([("", "python3", 5000)], dict(idle, bench={"id": "b"})) == [])
check("a gate service container during a bench is fine", c([("imggen", "python3", 7000)], dict(idle, bench={"id": "b"})) == [])
check("resolve on the host is fine while the gate shows it leased", c([("", "resolve", 3000)], {"services": {"resolve": {"running": True, "leases": 1}}}) == [])
check("resolve on the host with no lease is host_process", c([("", "resolve", 3000)]) == [("host_process", "", "resolve", 3000)])

# ---- gpu_outside.result (the two-looks rule) and the file the gate reads
go = load("gpu_outside", os.path.join(HERE, "gpu_outside.py"))
f1 = [("host_process", "", "python3", 5000)]
r1 = go.result(f1, {}, 1000)
check("first look with a finding is only 'pending'", r1["status"] == "pending" and r1["streak"] == 1, r1)
r2 = go.result(f1, r1, 1300)
check("second look in a row makes it 'outside'", r2["status"] == "outside" and r2["streak"] == 2 and r2["count"] == 1 and r2["vram_mib"] == 5000, r2)
r3 = go.result([], r2, 1600)
check("a clean look resets to ok", r3["status"] == "ok" and r3["streak"] == 0 and r3["count"] == 0, r3)
check("the file keeps names for the operator", r2["items"][0]["exe"] == "python3")

gate = load("bridgeai_gate", os.path.join(HERE, "gate", "gate.py"))
sd = os.path.join(tmp, "state"); os.makedirs(sd)
check("no file: outside is None", gate.load_outside(sd) is None)
d = dict(r2); d["kinds"] = ["host_process", "evil words here"]; d["items"] = [{"exe": "secret-name"}]
go.write_atomic(os.path.join(sd, "outside.json"), d)
o = gate.load_outside(sd, now=1360)
check("gate: fixed words and numbers only", o == {"status": "outside", "count": 1, "vram_mib": 5000, "kinds": ["host_process"], "age_s": 60}, o)
check("gate: never the names", "secret-name" not in json.dumps(o))
open(os.path.join(sd, "outside.json"), "w").write(json.dumps({"status": "hacked"}))
check("gate: an unknown status is dropped", gate.load_outside(sd) is None)

# ---- gpu_watch alert
gw = load("gpu_watch", os.path.join(HERE, "..", "aibridge", "ops", "gpu_watch.py"))
acts = gw.evaluate("aishur", {"up_s": 100, "outside": o})
al = [a for a in acts if a[1] == "gpu-outside:aishur"]
check("gpu_watch: 'outside' opens gpu-outside:HOST", al and al[0][0] == "alert" and "5000 MiB" in al[0][2] and "a program on the host" in al[0][2], al)
acts = gw.evaluate("aishur", {"up_s": 100, "outside": dict(o, status="pending")})
check("gpu_watch: 'pending' clears instead", [a[0] for a in acts if a[1] == "gpu-outside:aishur"] == ["clear"])
acts = gw.evaluate("aishur", {"up_s": 100})
check("gpu_watch: a gate without the field clears", [a[0] for a in acts if a[1] == "gpu-outside:aishur"] == ["clear"])

# ---- gpu_outside run with no tool writes no_tool
env_home = os.path.join(tmp, "home"); os.makedirs(env_home)
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "gpu_outside.py"), "run"], capture_output=True, text=True,
                   env={"HOME": env_home, "GATE_STATE_DIR": sd, "GPUTASKMAN": os.path.join(tmp, "missing"), "PATH": os.environ.get("PATH", "")})
check("run without gputaskman: exit 78 and status no_tool", r.returncode == 78 and json.load(open(os.path.join(sd, "outside.json")))["status"] == "no_tool", r.stdout + r.stderr)

# ---- bench_gate: a fake gputaskman records during the job and the result carries gpu_procs
fake = os.path.join(tmp, "fake-gtm")
snap = json.dumps({"processes": [proc(os.getpid(), "python3", 2 * GiB, 80, {"compute": 80})]})
open(fake, "w").write(f"""#!/bin/sh
# fake: record -o FILE -i S
[ "$1" = record ] || exit 2
f="$3"
trap 'exit 0' TERM
while :; do echo '{snap}' >> "$f"; sleep 0.1; done
""")
os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
bg = load("bench_gate", os.path.join(HERE, "bench_gate.py"))


class A:
    no_gputaskman = False


ctx = bg.Ctx.__new__(bg.Ctx)
ctx.gtm_tool, ctx.home, ctx.run_id = fake, os.path.join(tmp, "bench"), "20261127T000000"
rec = ctx.gtm_start("imggen 130_1")
time.sleep(0.6)
rows = ctx.gtm_stop(rec)
check("bench: the recorder ran and its file is folded", rows and rows[0]["name"] == "python3" and rows[0]["vram_peak_mib"] == 2048 and rows[0]["container"] == "", rows)
check("bench: the file is named after the run and the tag", os.path.exists(os.path.join(tmp, "bench", "gputaskman", "20261127T000000-imggen_130_1.jsonl")))
ctx.gtm_tool = None
check("bench: no tool, no recording", ctx.gtm_start("x") is None and ctx.gtm_stop(None) is None)
src = open(os.path.join(HERE, "bench_gate.py")).read()
check("bench: --no-gputaskman exists", "--no-gputaskman" in src)
check("bench: the job result gets gpu_procs", 'res["gpu_procs"] = procs' in src)

print("\n".join(fails) or "gtm_selftest: all ok")
sys.exit(1 if fails else 0)
