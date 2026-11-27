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
check("a pid with no /proc entry is gone, not the host", gtm.container_of(43, {cid: "x"}, proc=os.path.join(tmp, "proc")) == gtm.GONE)
hdir = os.path.join(tmp, "proc", "44"); os.makedirs(hdir)
open(os.path.join(hdir, "cgroup"), "w").write("0::/user.slice/user-1000.slice/session-2.scope\n")
check("a host process (cgroup with no docker id) is the host", gtm.container_of(44, {cid: "x"}, proc=os.path.join(tmp, "proc")) == "")
check("classify ignores a process that is gone", gtm.classify([(gtm.GONE, "python3", 5000)], {"services": {}}, {"imggen"}, "Xorg", 400) == [])
check("buckets ignore a process that is gone", sum(v["vram"] for v in gtm.buckets([(gtm.GONE, "python3", 5000, 9.0, {})], {"imggen"}).values()) == 0)

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
r1b = go.result(f1, r1, 1060)
check("second look is still 'pending'", r1b["status"] == "pending" and r1b["streak"] == 2, r1b)
r2 = go.result(f1, r1b, 1120)
check("third look in a row makes it 'outside'", r2["status"] == "outside" and r2["streak"] == 3 and r2["count"] == 1 and r2["vram_mib"] == 5000, r2)
r3 = go.result([], r2, 1180)
check("a clean look resets to ok", r3["status"] == "ok" and r3["streak"] == 0 and r3["count"] == 0, r3)
check("the file keeps names for the operator", r2["items"][0]["exe"] == "python3")

gate = load("bridgeai_gate", os.path.join(HERE, "gate", "gate.py"))
sd = os.path.join(tmp, "state"); os.makedirs(sd)
check("no file: outside is None", gate.load_outside(sd) is None)
d = dict(r2); d["kinds"] = ["host_process", "evil words here"]; d["items"] = [{"exe": "secret-name"}]
go.write_atomic(os.path.join(sd, "outside.json"), d)
o = gate.load_outside(sd, now=1180)
check("gate: fixed words and numbers only", o == {"status": "outside", "count": 1, "vram_mib": 5000, "kinds": ["host_process"], "age_s": 60}, o)
check("gate: never the names", "secret-name" not in json.dumps(o))
open(os.path.join(sd, "outside.json"), "w").write(json.dumps({"status": "hacked"}))
check("gate: an unknown status is dropped", gate.load_outside(sd) is None)

# ---- gpu_watch no longer pages it (Zabbix does)
gw = load("gpu_watch", os.path.join(HERE, "..", "aibridge", "ops", "gpu_watch.py"))
check("gpu_watch: no gpu-outside alert (Zabbix pages it)", not any("gpu-outside" in a[1] for a in gw.evaluate("aishur", {"up_s": 100, "outside": o})))

# ---- buckets and the Zabbix values
SV = {"imggen", "transcoder"}
bk = gtm.buckets([("imggen", "python3", 4968, 48.0, {"compute": 48.0}), ("transcoder", "ffmpeg", 300, 30.0, {"encode": 55.0, "decode": 10.0}),
                  ("hernikdoc", "game", 2000, 70.0, {"3d": 70.0}), ("", "Xorg", 35, 0.0, {}), ("stack-x-hermes", "python3", 100, 1.0, {}),
                  ("hermicdoc", "game", 1000, 50.0, {"3d": 50.0})], SV)
check("buckets: every gate service and the fixed ones are always there", sorted(bk) == ["host", "imggen", "other", "places", "transcoder"], sorted(bk))
check("buckets: a service's VRAM in bytes", bk["imggen"]["vram"] == 4968 * 2 ** 20 and bk["imggen"]["compute"] == 48.0)
check("buckets: NVENC/NVDEC from gputaskman's encode/decode", bk["transcoder"]["enc"] == 55.0 and bk["transcoder"]["dec"] == 10.0)
check("buckets: places summed, 3d counts as compute, load capped at 100", bk["places"]["vram"] == 3000 * 2 ** 20 and bk["places"]["util"] == 100.0 and bk["places"]["compute"] == 100.0, bk["places"])
check("buckets: a container the gate does not know is 'other', a host program 'host'", bk["other"]["vram"] == 100 * 2 ** 20 and bk["host"]["vram"] == 35 * 2 ** 20)
snapz = {"vram_used": 6 * GiB, "vram_total": 8 * GiB, "device": {"util_gpu": 77, "enc": 12, "dec": 3, "power_w": 129.5, "temp": None}}
vals = gtm.zbx_values("H", snapz, bk, {"status": "outside", "count": 2, "vram_mib": 512})
kv = {k: v for _h, k, v in vals}
check("zabbix: the card's values, a missing temperature left out", kv["gpu.util"] == 77 and kv["gpu.power"] == 129.5 and "gpu.temp" not in kv, kv)
check("zabbix: outside as its code with count and bytes", (kv["gpu.outside.status"], kv["gpu.outside.count"], kv["gpu.outside.vram"]) == (2, 2, 512 * 2 ** 20))
check("zabbix: pending sends status 1 and zero counts", {k: v for _h, k, v in gtm.zbx_values("H", snapz, bk, {"status": "pending", "count": 1, "vram_mib": 9})}["gpu.outside.count"] == 0)
check("zabbix: the discovery lists the buckets", json.loads(kv["gpu.bucket.discovery"]) == [{"{#BUCKET}": b} for b in sorted(bk)])
check("zabbix: never a person's or a process's name", not any(x in json.dumps(vals) for x in ("hernik", "hermic", "python3", "ffmpeg", "Xorg", "stack-x")))
tpl = open(os.path.join(HERE, "..", "aibridge", "ops", "zabbix", "template_gpu_usage.yaml")).read()
tkeys = set(re.findall(r"^\s+key: '([^']+)'", tpl, re.M))
sent = {re.sub(r"\[[^]]+\]$", "[{#BUCKET}]", k) for _h, k, _v in vals} | {"gpu.temp"}
check("zabbix: the code sends exactly the template's keys", sent == tkeys, sorted(sent ^ tkeys))
exprs = re.findall(r"^\s+expression: '([^']+)'", tpl, re.M)
check("zabbix: the one trigger pages on status 2 and needs fresh data", exprs == ["last(/GPU host usage/gpu.outside.status)=2 and nodata(/GPU host usage/gpu.outside.status,{$GPU.NODATA})=0"], exprs)
got = []
z = go.push({"GPU_ZBX_SERVER": "zbx", "GPU_ZBX_HOST": "H"}, snapz, [("imggen", "python3", 10, 1.0, {})], SV, {"status": "ok"}, send=lambda v, s, p: got.append((s, p, len(v))) or (len(v), 0))
check("push: sends to the configured server on 10051", got and got[0][:2] == ("zbx", "10051") and z == (got[0][2], 0), got)
check("push: off without GPU_ZBX_SERVER/HOST", go.push({}, snapz, [], SV, {"status": "ok"}, send=lambda *a: 1 / 0) is None)
check("push: a refused send never raises", go.push({"GPU_ZBX_SERVER": "z", "GPU_ZBX_HOST": "H"}, snapz, [], SV, {"status": "ok"}, send=lambda *a: (_ for _ in ()).throw(OSError())) is None)

# ---- gpu_outside run with no tool writes no_tool
env_home = os.path.join(tmp, "home"); os.makedirs(env_home)
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "gpu_outside.py"), "run"], capture_output=True, text=True,
                   env={"HOME": env_home, "GATE_STATE_DIR": sd, "GPUTASKMAN": os.path.join(tmp, "missing"), "PATH": os.environ.get("PATH", "")})
check("run without gputaskman: exit 78 and status no_tool", r.returncode == 78 and json.load(open(os.path.join(sd, "outside.json")))["status"] == "no_tool", r.stdout + r.stderr)

# ---- a host with no gate (the operator's PC): GPU_NO_GATE=1 -> status no_gate, exit 0
fake_json = os.path.join(tmp, "fake-json")
open(fake_json, "w").write("#!/bin/sh\necho '" + json.dumps({"vram_used": 1, "vram_total": 2, "device": {}, "processes": []}) + "'\n")
os.chmod(fake_json, 0o755)
sd2 = os.path.join(tmp, "state2")
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "gpu_outside.py"), "run"], capture_output=True, text=True,
                   env={"HOME": env_home, "GATE_STATE_DIR": sd2, "GPUTASKMAN": fake_json, "GPU_NO_GATE": "1", "PATH": "/nonexistent"})
check("no gate: exit 0 and status no_gate", r.returncode == 0 and json.load(open(os.path.join(sd2, "outside.json")))["status"] == "no_gate", r.stdout + r.stderr)

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
