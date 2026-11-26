#!/usr/bin/env python3
"""Offline checks for place_control.py and the gate's /place/* with a fake docker (a script on PATH that keeps each container's state in a file).
Run: python3 -I place_control_selftest.py"""
import hashlib, importlib.util, json, os, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
import atexit as _a, shutil as _s
tmp = tempfile.mkdtemp(prefix="selftest-"); _a.register(_s.rmtree, tmp, True)
HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        fails.append(name)


root = os.path.join(tmp, "places"); fakes = os.path.join(tmp, "fake"); bindir = os.path.join(tmp, "bin")
for d in (root, fakes, bindir):
    os.makedirs(d)
open(os.path.join(bindir, "docker"), "w").write(f'''#!{sys.executable}
import os, sys, json
F = {fakes!r}
a = sys.argv[1:]
def rd(n, d=""):
    try: return open(os.path.join(F, n)).read().strip()
    except OSError: return d
def cname(x): return x[:-3] if x.endswith("doc") else x
open(os.path.join(F, "calls.txt"), "a").write(" ".join(a) + "\\n")
if a[0] == "inspect":
    n = cname(a[-1]); st = rd(n + ".state")
    if not st: sys.exit(1)
    if "PortBindings" in a[2]:
        print(json.dumps({{"3000/tcp": [{{"HostIp": "10.9.8.7", "HostPort": rd(n + ".p0", "3010")}}], "3001/tcp": [{{"HostIp": "10.9.8.7", "HostPort": rd(n + ".p1", "3011")}}]}}))
    else: print(st)
elif a[0] in ("start", "stop"):
    n = cname(a[-1])
    if not rd(n + ".state"): sys.exit(1)
    open(os.path.join(F, n + ".state"), "w").write("running" if a[0] == "start" else "exited")
elif a[0] == "exec" and "sh" in a and any(x.startswith("/api/") for x in a):
    n = cname([x for x in a if x.endswith("doc")][0]); i = len(a) - 1 - a[::-1].index("sh")
    m, pth = a[i + 1], a[i + 2]
    v = rd(n + ".api." + m + pth.replace("/", "_"))
    if not v: sys.exit(1)
    print(v)
elif a[0] == "exec" and "pgrep" in a:
    n = cname([x for x in a if x.endswith("doc")][0])
    if rd(n + ".game"): print("42 CoDWaW.exe")
    else: sys.exit(1)
elif a[0] == "exec":
    n = cname([x for x in a if x.endswith("doc")][0]); v = rd(n + ".idle")
    if v == "fail": sys.exit(1)
    print(v)
elif a[0] == "stats":
    if any("{{.Name}}" in x for x in a):
        for x in a:
            if x.endswith("doc"):
                n = cname(x); print(f"{{x}}|{{rd(n + '.cpu', '1.0')}}%|{{rd(n + '.mem', '500MiB')}} / 9GiB|{{rd(n + '.net', '1MB / 1MB')}}")
    else:
        print(rd(cname(a[-1]) + ".cpu", "1.0") + "%")
''')
os.chmod(os.path.join(bindir, "docker"), 0o755)
open(os.path.join(bindir, "nvidia-smi"), "w").write(f'''#!/bin/sh
cat <<XML
<nvidia_smi_log><gpu><utilization><gpu_util>14 %</gpu_util><encoder_util>12 %</encoder_util><decoder_util>0 %</decoder_util></utilization>
<fb_memory_usage><total>8192 MiB</total><used>1500 MiB</used></fb_memory_usage><gpu_power_readings><instant_power_draw>61.50 W</instant_power_draw></gpu_power_readings>
<temperature><gpu_temp>49 C</gpu_temp></temperature>
<processes><process_info><pid>111</pid><used_memory>400 MiB</used_memory></process_info><process_info><pid>222</pid><used_memory>300 MiB</used_memory></process_info>
<process_info><pid>999</pid><used_memory>100 MiB</used_memory></process_info></processes></gpu></nvidia_smi_log>
XML
''')
os.chmod(os.path.join(bindir, "nvidia-smi"), 0o755)


def fake(name, state="exited", idle="5000", cpu="1.0"):
    for k, v in (("state", state), ("idle", idle), ("cpu", cpu)):
        open(os.path.join(fakes, f"{name}.{k}"), "w").write(v)


def make_place(name, token):
    d = os.path.join(root, name); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, ".gate.hash"), "w").write(hashlib.sha256(token.encode()).hexdigest() + "\n")
    open(os.path.join(d, ".ports"), "w").write("3010 3011\n")


TOK_A, TOK_B = "a" * 30, "b" * 30
make_place("alpha", TOK_A); make_place("beta", TOK_B)
os.makedirs(os.path.join(root, "nohash"))                     # a folder without a gate token is not drivable
fake("alpha"); fake("beta")
os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]

spec = importlib.util.spec_from_file_location("place_control", os.path.join(HERE, "place_control.py"))
pc = importlib.util.module_from_spec(spec); sys.modules["place_control"] = pc; spec.loader.exec_module(pc)
clock = [1_000_000.0]
P = pc.Places(root=root, state_path=os.path.join(tmp, "st", "places.json"), now=lambda: clock[0], idle_s=1800, warn_s=600, busy_cpu=80, active_s=90)
calls = lambda: open(os.path.join(fakes, "calls.txt")).read().splitlines() if os.path.exists(os.path.join(fakes, "calls.txt")) else []

check("a token finds its own place and no other", (P.find_by_token(TOK_A), P.find_by_token(TOK_B)), ("alpha", "beta"))
check("a wrong, empty, short or non-string token finds nothing", [P.find_by_token(t) for t in ("c" * 30, "", "short", None, 5, "a" * 500)], [None] * 6)
check("only folders with a gate hash are listed", P.names(), ["alpha", "beta"])

# --- start / stop / keep
code, out = P.start("alpha")
check("start: runs docker start on that container only, answers the web addresses and the clock", (code, out["running"], out["urls"]["http"], out["urls"]["https"], out["idle_limit_min"]),
      (200, True, "http://10.9.8.7:3010", "https://10.9.8.7:3011", 30))
check("start touched nothing else", [c for c in calls() if c.startswith("start")], ["start alphadoc"])
check("an unknown place is 404", P.start("ghost"), (404, {"why": "no_such_place"}))
code, out = P.start("alpha")
check("start on a running place only keeps it (no second docker start)", (code, len([c for c in calls() if c.startswith("start")])), (200, 1))
fake("beta", "running")
check("start reports only how many OTHER places run, never whose", P.info("alpha").get("others_running"), 1)
check("info of a stopped place has no clock", "closes_in_min" in P.info("alpha"), True)

# --- the clock: in use resets; idle warns at 20 min, closes at 30 min; render or touch keeps it
P.start("alpha"); P.stop("beta")
fake("alpha", "running", idle="3000", cpu="1.0")
clock[0] += 1300                                              # 21 min idle: past idle_s - warn_s
ev = P.tick()
check("21 min idle: one warning, still running", (ev, P.container_state("alpha"), "warned_at" in P.info("alpha")), ([("alpha", "warned")], "running", True))
check("the warning is given once", P.tick(), [])
check("closes_in counts down", P.info("alpha")["closes_in_min"], 8)
code, out = P.keep("alpha")
check("keep resets the clock and clears the warning", (code, out["closes_in_min"], "warned_at" in out), (200, 30, False))
clock[0] += 1300; P.tick()
fake("alpha", "running", idle="3", cpu="1.0")                 # somebody touched the screen
check("touched the screen: back to full time, event 'back'", (P.tick(), P.info("alpha")["closes_in_min"]), ([("alpha", "back")], 30))
fake("alpha", "running", idle="3000", cpu="150.0")            # a render with nobody there
clock[0] += 2000
check("a render at high CPU keeps it open however long", (P.tick(), P.container_state("alpha")), ([], "running"))
fake("alpha", "running", idle="3000", cpu="2.0")              # a game open but paused in a menu: no input, little CPU
open(os.path.join(fakes, "alpha.game"), "w").write("1")
clock[0] += 4000
check("a place with a game open is never closed for being idle", (P.tick(), P.container_state("alpha")), ([], "running"))
os.remove(os.path.join(fakes, "alpha.game"))
open(os.path.join(root, "alpha", ".hold"), "w").write("held")
clock[0] += 4000
check("a place the operator holds is never closed for being idle", (P.tick(), P.container_state("alpha")), ([], "running"))
os.remove(os.path.join(root, "alpha", ".hold"))
fake("alpha", "running", idle="fail", cpu="2.0")              # the probe fails (no X yet) and nothing is busy: counts as idle
clock[0] += 1900
check("30 min idle closes it, with the reason", (P.tick(), P.container_state("alpha"), P.info("alpha").get("closed_reason")), ([("alpha", "closed")], "exited", "idle"))
check("a closed place is not touched by the clock again", P.tick(), [])
code, out = P.stop("alpha")
check("stop on a stopped place is fine and starts nothing", (code, out["running"]), (200, False))
check("keep on a stopped place is refused", P.keep("alpha"), (409, {"why": "not_running"}))
fake("beta", "running")                                       # started by hand with place.py: the clock starts when the gate first sees it
clock[0] += 100000
check("a place started by hand gets a fresh clock, not an instant close", (P.tick(), P.container_state("beta")), ([], "running"))
P.start("alpha"); P.stop("alpha", "person")
check("a person's own close is recorded as such", P.info("alpha")["closed_reason"], "person")


# --- the metrics log
mfile = os.path.join(tmp, "metrics", "places-metrics.csv")
os.environ["PLACE_METRICS_FILE"] = mfile
clock2 = [2_000_000.0]
P2 = pc.Places(root=root, state_path=os.path.join(tmp, "st2", "places.json"), now=lambda: clock2[0], idle_s=1800, warn_s=600, busy_cpu=80, active_s=90)
P2.cgroup_place = lambda pid, ids: {111: "alpha", 222: "beta"}.get(pid)
fake("alpha", "running", idle="5", cpu="30.0"); fake("beta", "running", idle="4000", cpu="10.0")
open(os.path.join(fakes, "alpha.mem"), "w").write("600MiB"); open(os.path.join(fakes, "alpha.net"), "w").write("1MB / 10MB"); open(os.path.join(fakes, "beta.net"), "w").write("1MB / 2MB")
P2.tick()                                                     # first sight of each place: clocks start, nothing logged yet
clock2[0] += 60
P2.tick()
open(os.path.join(fakes, "alpha.net"), "w").write("1MB / 17.5MB")
clock2[0] += 60
P2.tick()
import csv as _csv
rows = list(_csv.DictReader(open(mfile)))
check("the log has a header and one row per running place per tick (2 places, 2 ticks)", [len(rows), list(rows[0].keys()) == pc.METRICS_COLUMNS], [4, True])
a1 = [r for r in rows if r["place"] == "alpha"][-1]; b1 = [r for r in rows if r["place"] == "beta"][-1]
check("a place in use is marked, an idle one is not, with its idle seconds", (a1["in_use"], b1["in_use"], b1["idle_s"]), ("1", "0", "4000"))
check("container CPU and memory are read", (a1["cpu_pct"], a1["mem_mb"], b1["cpu_pct"]), ("30.0", "629", "10.0"))
check("the network rate is the change in what leaves the place over the time between ticks (7.5 MB in 60 s = 1000 kbit/s)", a1["net_tx_kbps"], "1000.0")
check("each place's own VRAM comes from the processes in its cgroup, never the host's", (a1["place_vram_mb"], b1["place_vram_mb"]), ("400", "300"))
check("the card's totals are on every row", (a1["gpu_sm_pct"], a1["gpu_enc_pct"], a1["gpu_vram_used_mb"], a1["gpu_vram_total_mb"], a1["gpu_power_w"], a1["gpu_temp_c"], a1["places_running"]), ("14.0", "12.0", "1500.0", "8192.0", "61.5", "49.0", "2"))
os.environ["PLACE_METRICS"] = "0"
n0 = len(rows); clock2[0] += 60; P2.tick()
check("PLACE_METRICS=0 turns the log off", len(list(_csv.DictReader(open(mfile)))), n0)
os.environ["PLACE_METRICS"] = "1"
pc.METRICS_MAX = 300
clock2[0] += 60; P2.tick(); clock2[0] += 60; P2.tick()
check("past the size limit the log moves to .1 and starts again with a header", (os.path.exists(mfile + ".1"), open(mfile).readline().startswith("ts,place")), (True, True))
pc.METRICS_MAX = 5_000_000
check("an unreadable nvidia-smi answer gives no card figures but never breaks the clock", pc.gpu_snapshot("not xml"), {})

# --- the report
spec2 = importlib.util.spec_from_file_location("places_report", os.path.join(HERE, "places_report.py"))
pr = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(pr)
synth = os.path.join(tmp, "synth.csv")
with open(synth, "w", newline="") as f:
    w = _csv.writer(f); w.writerow(pc.METRICS_COLUMNS)
    for i in range(4):                                         # 1 place in use, 400 MB, 0.3 core, enc 6 %, sm 7 %; host holds 300 MB of 8192
        w.writerow([1000 + i * 60, "alpha", 1, 3, 30, 500, 600, 400, 7, 6, 0, 700, 8192, 40, 45, 1, 0.2])
    for i in range(4, 8):                                      # 2 places, the second idle
        w.writerow([1000 + i * 60, "alpha", 1, 3, 30, 500, 600, 400, 14, 12, 0, 1100, 8192, 60, 49, 2, 0.4])
        w.writerow([1000 + i * 60, "beta", 0, 4000, 10, 400, 100, 300, 14, 12, 0, 1100, 8192, 60, 49, 2, 0.4])
res = pr.analyse(pr.load(synth), threads=12, reserve=2, ram_gb=31, target=80)
check("report: the cost of a session is the mean of the in-use rows", (round(res["cost"]["cpu_cores"], 2), res["cost"]["vram_mb"], round(res["cost"]["mem_mb"])), (0.3, 400.0, 500))
check("report: the curve groups the card by places open", (sorted(res["curve"]), res["curve"][1]["enc"], res["curve"][2]["enc"], res["curve"][2]["ticks"]), ([1, 2], 6.0, 12.0, 4))
check("report: the host's own VRAM is the card's use minus the places' (700-400 and 1100-700: 350 MB on average)", round(res["host_vram"]), 350)
# VRAM (8192-350-1024)//400 = 17; NVENC 80//6 = 13; GPU 80//7 = 11; CPU (12-2)//0.3 = 33; RAM (31000-6000)//500 = 50
check("report: capacity per resource and the one that runs out first", (res["caps"], min(res["caps"], key=res["caps"].get)), ({"VRAM": 17, "NVENC": 13, "GPU use": 11, "CPU": 33, "RAM": 50}, "GPU use"))
txt = pr.render(res)
check("report text names the limiting resource and shows the scaling table", ("GPU use runs out first" in txt, "places  ticks" in txt), (True, True))
check("report with no rows says so; a missing file is rc 1", (pr.render(None).startswith("no rows"), pr.main([os.path.join(tmp, "nope.csv")])), (True, 1))
check("report --since keeps only the last minutes (3 ticks of 2 rows)", len(pr.load(synth, since_min=2)), 6)

# --- files in and out (input / output only; symbolic links are never followed)
import io
pc.MIN_FREE = 1
for pl_name in ("alpha", "beta"):
    for sub in ("input", "output", "desktop"):
        os.makedirs(os.path.join(root, pl_name, sub), exist_ok=True)
secret = os.path.join(tmp, "host.env"); open(secret, "w").write("GATE_TOKEN=very-secret\n")
adir, bdir = os.path.join(root, "alpha"), os.path.join(root, "beta")
open(os.path.join(adir, "desktop", "private.txt"), "w").write("the person's own file")
os.makedirs(os.path.join(adir, "output", "sub")); open(os.path.join(adir, "output", "sub", "cut.mp4"), "wb").write(b"x" * 2000)
open(os.path.join(adir, "output", "final.mov"), "wb").write(b"y" * 5000)
open(os.path.join(adir, "output", "half.part.mov"), "wb").write(b"z")            # an export still being written
os.symlink(secret, os.path.join(adir, "output", "link.txt"))                       # a planted link to a host file
os.symlink(tmp, os.path.join(adir, "output", "linkdir"))                           # a planted link to a folder
os.symlink(os.path.join(adir, "desktop"), os.path.join(adir, "input", "home"))     # a link to the person's home
code, fl = P.files("alpha")
check("files: regular files only, nested ones with their path, links and the unfinished export not listed",
      (code, sorted(x["name"] for x in fl["output"]), fl["input"], fl["working"]), (200, ["final.mov", "sub/cut.mp4"], [], 1))
check("files: an unknown place is 404", P.files("ghost"), (404, {"why": "no_such_place"}))
fd, size = P.open_file("alpha", "output", "sub/cut.mp4")
check("open_file reads a nested file", (os.read(fd, 10), size), (b"xxxxxxxxxx", 2000)); os.close(fd)
check("open_file refuses a link to a host file", P.open_file("alpha", "output", "link.txt"), (404, {"why": "no_such_file"}))
check("open_file refuses to walk through a linked folder", P.open_file("alpha", "output", "linkdir/host.env"), (404, {"why": "no_such_file"}))
check("open_file refuses the person's home through a link and never reads `desktop`", (P.open_file("alpha", "input", "home/private.txt"), P.open_file("alpha", "desktop", "private.txt")),
      ((404, {"why": "no_such_file"}), (404, {"why": "no_such_place"})))
check("open_file refuses odd names", [P.open_file("alpha", "output", n)[1] for n in ("../beta/output/x", "/etc/passwd", "a//b", ".hidden", "-rf", "x\nzz", "a/b/c/d.mov", "x.part.mov")], [{"why": "bad_name"}] * 8)
check("open_file refuses a directory and a missing file", (P.open_file("alpha", "output", "sub"), P.open_file("alpha", "output", "nope.mov")), ((404, {"why": "no_such_file"}),) * 2)
code, out = P.put_input("alpha", "clip one.mp4", io.BytesIO(b"v" * 3000), 3000)
check("put_input writes the file and says its name", (code, out, open(os.path.join(adir, "input", "clip one.mp4"), "rb").read() == b"v" * 3000), (200, {"name": "clip one.mp4", "size": 3000}, True))
check("put_input never overwrites: the same name gets -2", P.put_input("alpha", "clip one.mp4", io.BytesIO(b"w" * 10), 10)[1]["name"], "clip one-2.mp4")
check("put_input leaves no .part file behind", [n for n in os.listdir(os.path.join(adir, "input")) if n.endswith(".part")], [])
check("put_input with a short body leaves nothing and says so", (P.put_input("alpha", "short.mp4", io.BytesIO(b"abc"), 100), os.path.exists(os.path.join(adir, "input", "short.mp4")),
      [n for n in os.listdir(os.path.join(adir, "input")) if "short" in n]), ((400, {"why": "short_body"}), False, []))
check("put_input refuses a path, a dot name, an unfinished-looking name", [P.put_input("alpha", n, io.BytesIO(b"a"), 1)[1]["why"] for n in ("../x.mp4", "a/b.mp4", ".bashrc", "x.part", "x.part.mp4")], ["bad_name"] * 5)
check("put_input refuses an empty body and a file over the limit", (P.put_input("alpha", "e.mp4", io.BytesIO(b""), 0)[0], P.put_input("alpha", "big.mp4", io.BytesIO(b""), pc.MAX_FILE + 1)[0]), (413, 413))
pc.MIN_FREE = 1 << 60
check("put_input refuses when the disk would be left too full", P.put_input("alpha", "full.mp4", io.BytesIO(b"a"), 1), (507, {"why": "no_space"})); pc.MIN_FREE = 1
os.symlink(secret, os.path.join(adir, "input", "planted.mp4"))
check("put_input never writes through a link already there (takes a new name)", (P.put_input("alpha", "planted.mp4", io.BytesIO(b"a"), 1)[1]["name"], open(secret).read()), ("planted-2.mp4", "GATE_TOKEN=very-secret\n"))
check("one place's files are not another's", (P.files("beta")[1]["input"], P.files("beta")[1]["output"]), ([], []))
check("delete_output removes a file and says how much", (P.delete_output("alpha", "final.mov"), os.path.exists(os.path.join(adir, "output", "final.mov"))), ((200, {"name": "final.mov", "freed_bytes": 5000}), False))
check("delete_output refuses a link (the link target stays) and odd names", (P.delete_output("alpha", "link.txt")[0], os.path.exists(secret), P.delete_output("alpha", "../x")[0]), (404, True, 400))
fake("alpha", "exited")
check("convert and shrink need the place open", (P.convert("alpha", "clip one.mp4")[0], P.shrink("alpha", "sub/cut.mp4")[0]), (409, 409))
fake("alpha", "running")
execs = lambda: [c for c in calls() if c.startswith("exec -d")]
code, out = P.convert("alpha", "clip one.mp4", "sq")
check("convert starts to-resolve inside the place, in the background, as the person's uid", (code, out["result"], execs()[-1].split(" sh -c ")[0]), (200, "resolve/clip one.mov", "exec -d -u 1000:1000 alphadoc"))
check("convert passes the quality and both paths as arguments, not inside the shell template", execs()[-1].endswith(" sh sq /input/clip one.mp4 /input/resolve/clip one.mov"), True)
check("convert refuses a bad tier, a link and a missing file", (P.convert("alpha", "clip one.mp4", "x; rm -rf /")[0], P.convert("alpha", "home")[0], P.convert("alpha", "nope.mp4")[0]), (400, 404, 404))
code, out = P.shrink("alpha", "sub/cut.mp4", 1500)
check("shrink starts from-resolve inside the place with the size limit", (code, out["result"], execs()[-1].endswith(" sh 1500 /output/sub/cut.mp4 /output/telegram/cut.mp4")), (200, "telegram/cut.mp4", True))
check("shrink refuses a size over what Telegram takes", (P.shrink("alpha", "sub/cut.mp4", 5000)[0], P.shrink("alpha", "sub/cut.mp4", "9; ls")[0]), (400, 400))

# --- Moonlight: confirm the PIN, list and revoke paired devices through the place's own Sunshine
def api(name, method, path, text):
    open(os.path.join(fakes, f"{name}.api.{method}{path.replace('/', '_')}"), "w").write(text)
json.dump({"sunshine": 49989}, open(os.path.join(root, "alpha", ".settings.json"), "w"))
fake("alpha", "running")
U1, U2 = "aaaabbbb-1111-2222-3333-444455556666", "ccccdddd-1111-2222-3333-444455556666"
api("alpha", "GET", "/api/clients/list", json.dumps({"named_certs": [{"name": "phone", "uuid": U1, "cert": "SECRET-CERT"}, {"name": "pc", "uuid": U2}], "status": True}))
api("alpha", "GET", "/api/pin", json.dumps({"pairings": []}))
api("alpha", "POST", "/api/pin", json.dumps({"status": True}))
api("alpha", "POST", "/api/clients/unpair", json.dumps({"status": True}))
api("alpha", "POST", "/api/clients/unpair-all", json.dumps({"status": True}))
code, out = P.moonlight_list("alpha")
check("moonlight list: devices by name and a short id, never the certificate, and how many pairings wait", (code, out, "SECRET-CERT" in json.dumps(out)), (200, {"devices": [{"name": "phone", "id": "aaaabbbb"}, {"name": "pc", "id": "ccccdddd"}], "waiting": 0}, False))
check("moonlight pin with nothing waiting says so and sends nothing", (P.moonlight_pin("alpha", "1234"), [c for c in calls() if "-d" in c and "/api/pin" in c and "alpha" in c and "pairing_id" in c]), ((409, {"why": "nothing_waiting"}), []))
api("alpha", "GET", "/api/pin", json.dumps({"pairings": [{"address": "1.2.3.4", "id": "0123456789abcdef0123456789abcdef", "name": "phone"}]}))
n0 = len(calls())
code, out = P.moonlight_pin("alpha", "1234")
post = [c for c in calls()[n0:] if "POST /api/pin" in c or c.endswith(" sh POST /api/pin " ) or "POST /api/pin" in c]
check("moonlight pin sends the PIN with the waiting pairing's id and says which device", bool((code, out) == (200, {"accepted": True, "device": "phone"}) and post and "1234" in post[-1] and "0123456789abcdef0123456789abcdef" in post[-1]), True)
check("moonlight pin: the admin password is read inside the container (env), never on the docker command line", bool(all("SUNSHINE_ADMIN_PASS" in c or "admin:" not in c for c in calls()[n0:]) and not any("admin:" in c and "$SUNSHINE_ADMIN_PASS" not in c for c in calls()[n0:])), True)
check("moonlight pin refuses anything but 4 digits", [P.moonlight_pin("alpha", x)[0] for x in ("12", "12345", "12ab", "1234; ls", None, 1234)], [400] * 6)
check("a place without Moonlight is 404 and a stopped one is 409", (P.moonlight_list("beta")[0], (fake("alpha", "exited"), P.moonlight_list("alpha")[0])[1], (fake("alpha", "running"), 0)[1]), (404, 409, 0))
n1 = len(calls())
check("unpair by short id revokes that device only and sends its full uuid", (P.moonlight_unpair("alpha", "aaaabbbb"), any(U1 in c for c in calls()[n1:]), any(U2 in c for c in calls()[n1:])), ((200, {"revoked": 1, "device": "phone"}), True, False))
check("unpair by name works (case-insensitive)", P.moonlight_unpair("alpha", "PC"), (200, {"revoked": 1, "device": "pc"}))
check("unpair of an unknown device is 404 and a too-short id matches nothing", (P.moonlight_unpair("alpha", "zzzz")[0], P.moonlight_unpair("alpha", "aa")[0]), (404, 404))
api("alpha", "GET", "/api/clients/list", json.dumps({"named_certs": [{"name": "a", "uuid": "abcd0001-x"}, {"name": "b", "uuid": "abcd0002-x"}], "status": True}))
check("unpair by an id that fits two devices is refused as ambiguous", P.moonlight_unpair("alpha", "abcd"), (409, {"why": "ambiguous"}))
check("unpair all revokes every device and counts them", P.moonlight_unpair("alpha", "all"), (200, {"revoked": 2}))
api("alpha", "POST", "/api/clients/unpair", json.dumps({"status": False}))
check("a Sunshine that refuses the unpair is reported as a failure, not as revoked", P.moonlight_unpair("alpha", "abcd0001")[0], 502)

# --- over HTTP through the real gate
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
fake("alpha"); fake("beta")
env = {k: v for k, v in os.environ.items() if not k.startswith("GATE_")}
env.update(GATE_TOKEN="stack-token-for-tests-xx", GATE_HOST_TOKEN="host-token-for-tests-xx", GATE_PORT=str(port), GATE_BIND="127.0.0.1", GATE_ENV_FILE=os.path.join(tmp, "none.env"),
           GATE_STATE_DIR=os.path.join(tmp, "gstate"), HOME=tmp, PLACES_ROOT=root, PLACE_TICK_S="3600", GATE_TICK_S="5")
log = open(os.path.join(tmp, "gate.log"), "w+")
proc = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "gate.py")], env=env, stdout=log, stderr=subprocess.STDOUT)
for _ in range(80):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1); break
    except Exception:
        time.sleep(0.1)


def rq(path, token=None, method=None, body=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers=h, method=method or ("POST" if body is not None else "GET"))
    try:
        with urllib.request.urlopen(r, timeout=20) as x:
            return x.status, json.loads(x.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


try:
    check("http: no token, a wrong one, the stacks' token and the HOST token are all 401 on /place/state",
          [rq("/place/state", t)[0] for t in (None, "x" * 30, env["GATE_TOKEN"], env["GATE_HOST_TOKEN"])], [401] * 4)
    check("http: alpha's token reads alpha's state", rq("/place/state", TOK_A)[1]["place"], "alpha")
    code, out = rq("/place/start", TOK_A, body=b"{}")
    check("http: start opens alpha and only alpha", (code, out["place"], out["running"], P.container_state("beta")), (200, "alpha", True, "exited"))
    check("http: beta's token sees beta, never alpha's", rq("/place/state", TOK_B)[1]["place"], "beta")
    check("http: keep and stop", (rq("/place/keep", TOK_A, body=b"{}")[0], rq("/place/stop", TOK_A, body=b"{}")[1]["running"]), (200, False))
    check("http: unknown path 404, GET on a POST path 404", (rq("/place/nope", TOK_A)[0], rq("/place/start", TOK_A)[0]), (404, 404))
    check("http: the host token cannot open a place and a place token cannot touch /host/*", (rq("/place/start", env["GATE_HOST_TOKEN"], body=b"{}")[0], rq("/host/state", TOK_A)[0]), (401, 401))
    check("http: the stacks' token cannot use /host/ either (unchanged)", rq("/host/state", env["GATE_TOKEN"])[0], 401)
    # files over HTTP
    def raw(path, token, method=None, body=None):
        r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers={"Authorization": "Bearer " + token}, method=method)
        try:
            with urllib.request.urlopen(r, timeout=20) as x:
                return x.status, x.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
    open(os.path.join(adir, "output", "net.mp4"), "wb").write(os.urandom(300000) * 5)
    code, out = rq("/place/files", TOK_A)
    check("http: files lists alpha's output with sizes", (code, [x["size"] for x in out["output"] if x["name"] == "net.mp4"]), (200, [1500000]))
    code, data = raw("/place/file?name=net.mp4", TOK_A)
    check("http: file streams the whole file", (code, len(data), data == open(os.path.join(adir, "output", "net.mp4"), "rb").read()), (200, 1500000, True))
    check("http: file refuses a planted link and beta's token cannot read alpha's file", (raw("/place/file?name=link.txt", TOK_A)[0], raw("/place/file?name=net.mp4", TOK_B)[0]), (404, 404))
    check("http: file name is URL-decoded (a space)", raw("/place/file?name=" + urllib.parse.quote("a b.mp4"), TOK_A)[0], 404)
    up = os.urandom(200000) * 3
    code, out = rq("/place/input?name=" + urllib.parse.quote("from stack.mp4"), TOK_A, body=up)
    check("http: input stores the streamed body", (code, out, open(os.path.join(adir, "input", "from stack.mp4"), "rb").read() == up), (200, {"name": "from stack.mp4", "size": 600000}, True))
    check("http: input with a bad name is 400 and the host token cannot upload", (rq("/place/input?name=..%2Fx", TOK_A, body=b"abc")[0], rq("/place/input?name=a.mp4", env["GATE_HOST_TOKEN"], body=b"abc")[0]), (400, 401))
    check("http: delete removes the output file; a second delete is 404", (rq("/place/delete", TOK_A, body=json.dumps({"name": "net.mp4"}).encode())[0], rq("/place/delete", TOK_A, body=json.dumps({"name": "net.mp4"}).encode())[0]), (200, 404))
    check("http: convert on a stopped place is 409", rq("/place/convert", TOK_A, body=json.dumps({"name": "from stack.mp4"}).encode())[0], 409)
    check("http: the gate still answers after an upload that was refused", rq("/place/state", TOK_A)[0], 200)
    # moonlight over HTTP
    api("alpha", "GET", "/api/clients/list", json.dumps({"named_certs": [{"name": "phone", "uuid": U1}], "status": True}))
    api("alpha", "POST", "/api/clients/unpair", json.dumps({"status": True}))
    api("alpha", "GET", "/api/pin", json.dumps({"pairings": []}))
    fake("alpha", "running")
    check("http: moonlight list through the place's own token", rq("/place/moonlight", TOK_A)[1].get("devices"), [{"name": "phone", "id": "aaaabbbb"}])
    check("http: another place's token cannot see it (beta has no Moonlight: 404) and the host token is refused", (rq("/place/moonlight", TOK_B)[0], rq("/place/moonlight", env["GATE_HOST_TOKEN"])[0]), (404, 401))
    check("http: pin with nothing waiting is 409; a bad pin is 400", (rq("/place/moonlight/pin", TOK_A, body=json.dumps({"pin": "1234"}).encode())[0], rq("/place/moonlight/pin", TOK_A, body=json.dumps({"pin": "abcd"}).encode())[0]), (409, 400))
    check("http: unpair by id", rq("/place/moonlight/unpair", TOK_A, body=json.dumps({"device": "aaaabbbb"}).encode()), (200, {"revoked": 1, "device": "phone"}))
    check("http: the gate says how many places it watches", "places: 2 with a gate token" in (log.flush() or open(log.name).read()), True)
finally:
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()

# --- the same gate without a places folder: /place/* is simply off
env2 = dict(env, PLACES_ROOT=os.path.join(tmp, "absent"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
env2["GATE_PORT"] = str(port)
proc = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "gate.py")], env=env2, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
for _ in range(80):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1); break
    except Exception:
        time.sleep(0.1)
try:
    check("no places folder on the host: /place/* answers 403 places_disabled", rq("/place/state", TOK_A), (403, {"why": "places_disabled"}))
finally:
    proc.terminate()

# --- notices: the gate tells the wake service (and through it the person's bot) about open / warned / closed / stopped
import http.server as _hs, threading as _th, urllib.parse as _up
got = []
class _N(_hs.BaseHTTPRequestHandler):
    def do_GET(self):
        got.append(dict(_up.parse_qsl(_up.urlparse(self.path).query))); self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a): pass
_srv = _hs.HTTPServer(("127.0.0.1", 0), _N); _th.Thread(target=_srv.serve_forever, daemon=True).start()
pc.NOTIFY_URL = f"http://127.0.0.1:{_srv.server_address[1]}/aviso_lugar"
fake("beta", "exited"); got.clear()
P.start("beta"); P.stop("beta")
for _ in range(50):
    if len(got) >= 2: break
    time.sleep(0.05)
check("opening and closing a place notify the wake service with the place and the event", sorted((g.get("lugar"), g.get("evento")) for g in got), [("beta", "open"), ("beta", "stopped")])
_srv.shutdown(); pc.NOTIFY_URL = ""

print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
