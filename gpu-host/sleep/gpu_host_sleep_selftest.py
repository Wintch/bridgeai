#!/usr/bin/env python3
"""Offline checks for gpu_host_sleep.sh: fake commands in a temp dir, one reason at a time, the idle count, trial and active mode,
the gate's sleep_ok, the maintenance mark and the resume hook. Run: python3 -I gpu_host_sleep_selftest.py"""
import json, os, stat, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "gpu_host_sleep.sh")
FAIL = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        FAIL.append(name)


tmp = tempfile.mkdtemp(prefix="gpusleep-")
fake, state = os.path.join(tmp, "bin"), os.path.join(tmp, "state")
os.makedirs(fake)
net = os.path.join(tmp, "net"); os.makedirs(net)
open(os.path.join(net, "rx_bytes"), "w").write("0"); open(os.path.join(net, "tx_bytes"), "w").write("0")
load = os.path.join(tmp, "loadavg"); open(load, "w").write("0.10 0.10 0.10 1/100 1\n")
suspend_log = os.path.join(tmp, "suspended")


def script(name, body):
    p = os.path.join(fake, name)
    open(p, "w").write("#!/bin/sh\n" + body + "\n")
    os.chmod(p, 0o755)
    return p


# knobs the fakes read from files, so each case changes one thing
def knob(name, value):
    open(os.path.join(tmp, name), "w").write(value)


for k, v in (("who", ""), ("gpu", "0, 0"), ("apps", ""), ("pgrep", "none"), ("docker", ""), ("gate", '{"sleep_ok": true, "sleep_why": []}')):
    knob(k, v)
script("who", f'cat {tmp}/who')
script("nvidia-smi", f'case "$*" in *compute-apps*) cat {tmp}/apps;; *) cat {tmp}/gpu;; esac')
script("pgrep", f'a="$*"; case "$a" in *apt*) [ "$(cat {tmp}/pgrep)" = apt ] && exit 0;; *) [ "$(cat {tmp}/pgrep)" = proc ] && exit 0;; esac; exit 1')
script("docker", f'cat {tmp}/docker')
script("curl", f'cat {tmp}/gate')
script("suspend", f'echo suspended >> {suspend_log}')
script("logger", "exit 0")
host_env = os.path.join(tmp, "host.env"); open(host_env, "w").write("GATE_TOKEN=tok\n")
conf = os.path.join(tmp, "conf")
now = [1_000_000]


def write_conf(mode="active", idle=3, extra=""):
    open(conf, "w").write(f"MODE={mode}\nIDLE_MIN={idle}\nHOST_ENV={host_env}\nGATE_URL=http://x/state\nNET_KBS_MAX=200\n{extra}\n")


def run():
    env = {"PATH": fake + ":/usr/bin:/bin", "GPU_SLEEP_CONF": conf, "STATE_DIR": state, "NET_STATS": net, "NET_IFACE": "x", "LOADAVG": load,
           "SUSPEND": os.path.join(fake, "suspend"), "NOW_EPOCH": str(now[0]), "WHO": "who", "NVSMI": "nvidia-smi", "DOCKER": "docker",
           "PGREP": "pgrep", "CURL": "curl"}
    now[0] += 60
    r = subprocess.run(["bash", SCRIPT], capture_output=True, text=True, env=env, timeout=30)
    last = {}
    try:
        last = json.loads(open(os.path.join(state, "observation.jsonl")).read().strip().splitlines()[-1])
    except Exception:
        pass
    if r.returncode != 0:
        print("   script stderr:", r.stderr[:300])
    return last


def suspended():
    return os.path.exists(suspend_log)


def reset():
    for f in (suspend_log,):
        if os.path.exists(f):
            os.remove(f)
    for f in os.listdir(state) if os.path.isdir(state) else []:
        os.remove(os.path.join(state, f))
    for k, v in (("who", ""), ("gpu", "0, 0"), ("apps", ""), ("pgrep", "none"), ("docker", ""), ("gate", '{"sleep_ok": true, "sleep_why": []}')):
        knob(k, v)
    open(load, "w").write("0.10 0.10 0.10 1/100 1\n")


write_conf()
reset()
# an idle host counts minutes and sleeps on the third
a, b, c = run(), run(), run()
check("idle: the count goes 1, 2, 3 and the host suspends on the third minute", (a["idle"], b["idle"], c["idle"]) == (1, 2, 3) and suspended() and c["reasons"] == [], (a, b, c))
check("after suspending the count restarts from zero", open(os.path.join(state, "idle_minutes")).read().strip() == "0")

cases = (
    ("an SSH session", "who", "aishur pts/0 2026-11-23 05:00 (10.0.0.1)\n", "session"),
    ("the desktop's own session does not count", None, None, None),
    ("GPU utilisation", "gpu", "40, 0", "gpu"),
    ("a video encoder session (a stream)", "gpu", "0, 1", "gpu"),
    ("a compute process", "apps", "/usr/bin/python3\n", "gpu"),
    ("Sunshine's idle GPU context alone is not work", "apps", "/usr/bin/sunshine\n", None),
    ("Sunshine plus another compute process is work", "apps", "/usr/bin/sunshine\n/usr/bin/blender\n", "gpu"),
    ("apt running", "pgrep", "apt", "apt"),
    ("a game or an editor", "pgrep", "proc", "process"),
    ("a container running", "docker", "imggen\n", "docker"),
    ("the gate says it is busy", "gate", '{"sleep_ok": false, "sleep_why": ["lease:imggen", "running:imggen"]}', "gate"),
)
for name, knobname, val, reason in cases:
    reset()
    write_conf(idle=1)
    if knobname:
        knob(knobname, val)
    else:
        knob("who", "aishur :0 2026-11-23 04:00 (:0)\n")
    r = run()
    if reason:
        check(f"reason: {name} keeps it awake", not suspended() and any(x.startswith(reason) for x in r.get("reasons", [])), r)
    else:
        check(f"no reason: {name}", suspended() and r.get("reasons") == [], r)

reset(); write_conf(idle=1); open(load, "w").write("3.50 3.00 2.00 1/100 1\n")
r = run(); check("reason: load above LOAD_MAX", not suspended() and any(x.startswith("load") for x in r["reasons"]), r)

reset(); write_conf(idle=1)
run()                                                                    # first sample: no rate yet, and it suspends: undo that for the next step
if os.path.exists(suspend_log): os.remove(suspend_log)
open(os.path.join(net, "rx_bytes"), "w").write(str(60 * 1024 * 500))      # 500 KB/s for the next minute
r = run(); check("reason: network traffic above NET_KBS_MAX", not suspended() and any(x.startswith("net") for x in r["reasons"]), r)
open(os.path.join(net, "rx_bytes"), "w").write("0")

reset(); write_conf(mode="trial", idle=2)
run(); r = run()
check("trial mode: it decides it would sleep and does not suspend", not suspended() and r["idle"] == 2 and r["mode"] == "trial", r)

reset(); write_conf(idle=1)
os.makedirs(state, exist_ok=True)
open(os.path.join(state, "maintenance"), "w").write(f"{now[0] + 3600} fixing\n")
r = run(); check("maintenance mark keeps it awake and names the reason", not suspended() and "maintenance:fixing" in r["reasons"], r)
open(os.path.join(state, "maintenance"), "w").write(f"{now[0] - 10} old\n")
r = run(); check("an expired maintenance mark is removed and the host may sleep", suspended() and not os.path.exists(os.path.join(state, "maintenance")), r)

reset(); write_conf(idle=1); knob("gate", "not json")
r = run(); check("a gate that answers garbage does not block sleep (the other checks decide)", suspended(), r)

reset(); write_conf(idle=3)
a = run(); st = os.path.join(state, "idle_minutes"); os.utime(st, (now[0] - 1000, now[0] - 1000))   # a stale counter = the host was asleep
b = run(); check("a stale idle counter starts again at 1 (the host slept or the timer stopped)", b["idle"] == 1, (a, b))

# the resume hook and the mark tool, with a temp state dir
hook = os.path.join(HERE, "gpu-host-sleep-resume")
env = {"PATH": fake + ":/usr/bin:/bin", "STATE_DIR": state}
os.makedirs(state, exist_ok=True); open(os.path.join(state, "idle_minutes"), "w").write("7")
subprocess.run(["sh", hook, "pre"], env=env); subprocess.run(["sh", hook, "post"], env=env)
check("the resume hook restarts the idle count", not os.path.exists(os.path.join(state, "idle_minutes")))
mark = os.path.join(HERE, "gpu-host-sleep-mark")
menv = {"PATH": "/usr/bin:/bin", "STATE_DIR": state}
r = subprocess.run(["bash", mark, "99", "testing", "now"], capture_output=True, text=True, env=menv)
f = open(os.path.join(state, "maintenance")).read().split(None, 1)
import time
check("the mark tool caps a mark at 24 hours and keeps the reason", r.returncode == 0 and 23 * 3600 < int(f[0]) - time.time() <= 24 * 3600 + 5 and f[1].strip() == "testing now", (r.stdout, f))
subprocess.run(["bash", mark, "off"], env=menv)
check("the mark tool 'off' removes it", not os.path.exists(os.path.join(state, "maintenance")))
r = subprocess.run(["bash", mark, "abc"], capture_output=True, text=True, env=menv)
check("the mark tool refuses a non-number of hours", r.returncode == 2)

for f in ("gpu_host_sleep.sh", "install_sleep.sh", "gpu-host-sleep-mark"):
    r = subprocess.run(["bash", "-n", os.path.join(HERE, f)], capture_output=True, text=True)
    check(f"{f}: bash syntax", r.returncode == 0, r.stderr)
print("\n".join(FAIL) or "gpu_host_sleep_selftest: all ok")
sys.exit(1 if FAIL else 0)
