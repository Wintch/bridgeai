#!/usr/bin/env python3
"""Offline test of gpu-host/upkeep/upkeep.py: fake dpkg-query, apt-cache, apt-mark, dkms, uname and nvidia-smi on PATH, a fake gate (a real HTTP
server on 127.0.0.1) and a fake selfcheck. Trap versions of sudo, apt, apt-get, dpkg, reboot, modprobe, update-initramfs and `dkms install`
write a line to a file the test checks at the end: the tool must never start a root command. Nothing real is read or changed.
Run: python3 -I gpu-host/upkeep/upkeep_selftest.py [--show]   (--show prints the sample outputs at the end)"""
import http.server, importlib.util, json, os, re, stat, subprocess, sys, tempfile, threading

HERE = os.path.dirname(os.path.abspath(__file__))
UPKEEP = os.path.join(HERE, "upkeep.py")
FIX = os.path.join(HERE, "fixtures")
TOKEN = "tok-secret-7f3a9c"
FAIL = []
OUTS = []          # everything the tool printed: the token must not be in it
SHOW = {}


def check(name, cond, info=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{info}]"))
    if not cond:
        FAIL.append(name)


spec = importlib.util.spec_from_file_location("upkeep_under_test", UPKEEP)
U = importlib.util.module_from_spec(spec)
spec.loader.exec_module(U)

TMP = tempfile.mkdtemp(prefix="upkeep-selftest-")
TESTMARK = os.path.join(TMP, U.TEST_MARKER_NAME)          # the file only this selftest creates: it is what turns the test overrides on (UPKEEP_TEST names it)
fd_ = os.open(TESTMARK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.write(fd_, (U.TEST_MARKER_MAGIC + "\n").encode())
os.close(fd_)
BIN, FAKE, HOME_ = os.path.join(TMP, "bin"), os.path.join(TMP, "fake"), os.path.join(TMP, "home")
GSTATE, STATE, BOOT = os.path.join(TMP, "gate-state"), os.path.join(TMP, "upkeep-state"), os.path.join(TMP, "boot")
ROOTCALLS = os.path.join(TMP, "rootcalls")
RESTARTS = os.path.join(TMP, "restarts")
for d in (BIN, FAKE, HOME_, GSTATE, BOOT):
    os.makedirs(d)

# ---------------------------------------------------------------------------------------------------------------- fake commands
SH = {
    "dpkg-query": 'cat "$FAKE/dpkg.txt"',
    "apt-mark": '[ "$1" = showmanual ] && cat "$FAKE/manual.txt"',
    "uname": 'cat "$FAKE/kernel"',
    "nvidia-smi": '[ -f "$FAKE/smi" ] && cat "$FAKE/smi" || exit 9',
    "dkms": 'if [ "$1" = status ]; then cat "$FAKE/dkms.txt"; else echo "dkms $*" >> "$ROOTCALLS"; exit 1; fi',
    "apt-cache": 'case "$1" in pkgnames) cat "$FAKE/pkgnames.txt";; madison) cat "$FAKE/madison.txt";; policy) cat "$FAKE/policy_$2.txt" 2>/dev/null;; esac',
}
for trap in ("sudo", "apt", "apt-get", "dpkg", "reboot", "shutdown", "modprobe", "update-initramfs", "docker"):
    SH[trap] = f'echo "{trap} $*" >> "$ROOTCALLS"; exit 1'
# systemctl: the ONE accepted call is the restart of the gate's USER unit (it only writes a line to RESTARTS, nothing is restarted); any other use is a trap
SH["systemctl"] = ('if [ $# -eq 3 ] && [ "$1 $2 $3" = "--user restart bridgeai-gate.service" ]; then echo restart >> "$RESTARTS"; [ -f "$FAKE/restart_fails" ] && exit 1; exit 0; fi; '
                   'echo "systemctl $*" >> "$ROOTCALLS"; exit 1')
for name, body in SH.items():
    p = os.path.join(BIN, name)
    with open(p, "w") as f:
        f.write("#!/bin/sh\n" + body + "\n")
    os.chmod(p, 0o755)
SELFCHECK = os.path.join(TMP, "fake_selfcheck.py")
with open(SELFCHECK, "w") as f:
    f.write('''import os, signal, sys, time
fake = os.environ["FAKE"]
open(fake + "/selfcheck_ran", "a").write("busy_exists=%s\\n" % os.path.exists(os.environ["GATE_STATE_DIR"] + "/busy"))
if os.path.exists(fake + "/selfcheck_kill_parent"):
    open(fake + "/selfcheck_child_pid", "w").write(str(os.getpid()))
    time.sleep(1)                                          # the parent has recorded this process in the marker by now (a kill at the very start is not what hostcare does: it kills at its timeout)
    os.kill(os.getppid(), signal.SIGKILL)
    time.sleep(40)
if os.path.exists(fake + "/selfcheck_sleep"):
    open(fake + "/selfcheck_child_pid", "w").write(str(os.getpid()))
    time.sleep(float(open(fake + "/selfcheck_sleep").read()))
code = int(open(fake + "/selfcheck_exit").read())
print("gpu selfcheck: " + {0: "ok ratio 1.01 tflops 18.2", 1: "degraded ratio 0.52 (fp32acc_slow)", 2: "error (no_reference)", 75: "skipped (card in use)"}[code])
sys.exit(code)
''')

# ---------------------------------------------------------------------------------------------------------------- fake gate
GATE = {"services": {}, "bench": None, "calls": 0}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        GATE["calls"] += 1
        if self.path == "/healthz":
            down = os.path.exists(os.path.join(FAKE, "healthz_down"))
            self.send_response(503 if down else 200); self.end_headers(); self.wfile.write(b"down" if down else b"ok gate"); return
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            self.send_response(401); self.end_headers(); return
        if self.path != "/state":
            self.send_response(404); self.end_headers(); return
        busy = os.path.exists(os.path.join(GSTATE, "busy"))
        services = GATE["services"]
        gf = os.path.join(FAKE, "gate_forgets")                       # a gate that lost a running service when it restarted (the restart count in the file)
        if os.path.exists(gf) and os.path.exists(RESTARTS) and len(open(RESTARTS).read().split()) >= int(open(gf).read()):
            services = {}
        body = json.dumps({"gpu": GATE.get("gpu") or {"name": "fake"}, "blocked": GATE.get("blocked") or ("busy" if busy else None),
                           "services": services, "bench": GATE["bench"], "up_s": 100}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]
ENVF = os.path.join(TMP, "host.env")


def set_env_file(token=TOKEN):
    with open(ENVF, "w") as f:
        f.write(f"GATE_PORT={PORT}\n" + (f"GATE_TOKEN={token}\n" if token else ""))


set_env_file()


# ---------------------------------------------------------------------------------------------------------------- the host's state
OLD, NEW = "595.71.05", "595.112.07"
KERNELS = ["6.12.100+deb13-amd64", "6.12.115+deb13.1-amd64"]


def write(name, text):
    with open(os.path.join(FAKE, name), "w") as f:
        f.write(text)


def host_state(updated=False, dkms_missing=None, smi=True, running=KERNELS[1]):
    v, pin, tk = (NEW + "-1", NEW, "1.21.0-1") if updated else (OLD + "-1", OLD, "1.20.1-1")
    lines = [f"ii |nvidia-open|{v}", f"ii |nvidia-driver|{v}", f"ii |nvidia-driver-libs:i386|{v}", f"ii |nvidia-opencl-icd|{v}", f"ii |libnvidia-compute|{v}",
             f"ii |firmware-nvidia-gsp|{v}", f"ii |libcuda1:amd64|{v}", f"ii |libnvcuvid1|{v}", f"ii |libegl-nvidia0|{v}", f"ii |libglx-nvidia0|{v}",
             f"ii |nvidia-driver-pinning-{pin}|{v}", f"ii |nvidia-container-toolkit|{tk}", f"ii |nvidia-container-toolkit-base|{tk}",
             f"ii |libnvidia-container1|{tk}", "ii |gpu-unlock-dkms|2.0.0", "ii |gpu-unlock-firmware|2.0.0", "ii |vim|9.1", "ii |linux-image-amd64|6.12.115-1",
             "rc |linux-image-6.1.0-old|6.1.0-1"]
    for k in KERNELS:
        lines += [f"ii |linux-image-{k}|{k.split('+')[0]}-1", f"ii |linux-headers-{k}|{k.split('+')[0]}-1"]
    write("dpkg.txt", "\n".join(lines) + "\n")
    write("manual.txt", f"nvidia-open\nnvidia-driver\nnvidia-driver-libs:i386\nnvidia-opencl-icd\nlibcuda1\nnvidia-container-toolkit\nnvidia-driver-pinning-{pin}\ngpu-unlock-dkms\nvim\n")
    drv = NEW if updated else OLD
    rows = []
    for k in KERNELS:
        rows.append(f"gpu-unlock/2.0.0, {k}, x86_64: installed")
        if (dkms_missing or {}).get("nvidia") != k:
            rows.append(f"nvidia/{drv}, {k}, x86_64: installed")
    if dkms_missing and dkms_missing.get("gpu-unlock"):
        rows = [r for r in rows if not (r.startswith("gpu-unlock") and dkms_missing["gpu-unlock"] in r)]
    write("dkms.txt", "\n".join(rows) + "\n")
    write("kernel", running + "\n")
    if smi:
        write("smi", drv + "\n")
    elif os.path.exists(os.path.join(FAKE, "smi")):
        os.unlink(os.path.join(FAKE, "smi"))
    write("pkgnames.txt", f"nvidia-driver-pinning-{OLD}\nnvidia-driver-pinning-{NEW}\nnvidia-driver-pinning-580.126.09\n")
    write("madison.txt", "".join(f"nvidia-open | {x} | https://example.invalid/cuda/x86_64  Packages\n" for x in (NEW + "-1", OLD + "-1", "1.21.0-1", "1.20.1-1", "2.0.0")))
    write("policy_nvidia-container-toolkit.txt", f"nvidia-container-toolkit:\n  Installed: {tk}\n  Candidate: 1.21.0-1\n")


PATCHED = """import importlib.util, sys
spec = importlib.util.spec_from_file_location("upkeep_patched", sys.argv[1]); U = importlib.util.module_from_spec(spec); spec.loader.exec_module(U)
%s
sys.exit(U.main(sys.argv[2:]))
"""


def run(*args, stdin=None, env_extra=None, sel_exit=None, timeout=120, patch=None):
    """patch: Python source run after upkeep.py is loaded and before its main (a fault injected in-process: a full disk, a restart that fails)."""
    if sel_exit is not None:
        write("selfcheck_exit", str(sel_exit))
    env = {**os.environ, "PATH": BIN + os.pathsep + os.environ["PATH"], "HOME": HOME_, "FAKE": FAKE, "ROOTCALLS": ROOTCALLS, "GATE_ENV_FILE": ENVF,
           "GATE_STATE_DIR": GSTATE, "UPKEEP_STATE_DIR": STATE, "UPKEEP_BOOT_DIR": BOOT, "RESTARTS": RESTARTS, "BENCH_GATE_HOME": os.path.join(HOME_, "bench_gate"), "UPKEEP_SELFCHECK": SELFCHECK, "UPKEEP_TEST": TESTMARK, "TMPDIR": TMP,
           "XDG_CONFIG_HOME": os.path.join(HOME_, ".config")}
    env.pop("GATE_TOKEN", None)
    env.update(env_extra or {})
    argv = [sys.executable, "-I", UPKEEP, *args] if patch is None else [sys.executable, "-I", "-c", PATCHED % patch, UPKEEP, *args]
    p = subprocess.run(argv, input=stdin, capture_output=True, text=True, env=env, timeout=timeout)
    OUTS.append(p.stdout + p.stderr)
    return p.returncode, p.stdout, p.stderr


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def pos(text, *needles):
    """True when the needles occur in this order."""
    i = 0
    for n in needles:
        j = text.find(n, i)
        if j < 0:
            return False
        i = j + len(n)
    return True


# ================================================================================================================ plan
host_state()
rc, out, err = run("plan", "driver", "--to", NEW)
SHOW["plan driver --to " + NEW] = out
check("plan: exit 0 with a ready host", rc == 0, out[-600:])
check("plan: the ordered steps (busy on, idle, snapshot, apt update, simulate the pin, pin alone, simulate the drivers, install, dkms, reboot, verify)",
      pos(out, "busy on --apply", "upkeep.py idle", "snapshot --apply", "sudo apt update", f"check-sim - --pin --to {NEW}", f"sudo apt install nvidia-driver-pinning-{NEW}",
          f"check-sim - --to {NEW}", "sudo apt install --no-remove libcuda1", "verify --to " + NEW + " --installed", "dkms status", "sudo reboot", "verify --to " + NEW + " --apply"), out)
check("plan: it starts with the 'run from the checkout: cd ...' header", out.splitlines()[1].startswith("run from the bridgeai checkout: cd /") , out[:300])
pin_line = next(l for l in out.splitlines() if l.strip().startswith(f"$ sudo apt install nvidia-driver-pinning-{NEW}"))
check("plan: TRANSACTION 1 is the new pin alone (plus the upgradable container toolkit), no driver package",
      pin_line.strip() == f"$ sudo apt install nvidia-driver-pinning-{NEW} nvidia-container-toolkit", pin_line)
inst_line = next(l for l in out.splitlines() if l.strip().startswith("$ sudo apt install --no-remove "))
check("plan: TRANSACTION 2 installs the host's own driver packages (from dpkg/apt-mark), with --no-remove (apt itself refuses a removal), without the pin, the container toolkit or gpu-unlock",
      inst_line.strip() == "$ sudo apt install --no-remove libcuda1 nvidia-driver nvidia-driver-libs:i386 nvidia-open nvidia-opencl-icd", inst_line)
sim_line = next(l for l in out.splitlines() if "apt install -s --no-remove " in l and "| " in l)
check("plan: the printed simulation of transaction 2 uses --no-remove too and is piped into check-sim with the target", "check-sim - --to " + NEW in sim_line and "nvidia-open" in sim_line, sim_line)
check("plan: the simulation of transaction 2 can also be written to a FILE the bot reads (never pasted text)", "> " in out and "sim-transaction-2.txt" in out and "check-sim /" in out and "never takes pasted text" in out, out)
check("plan: root, no-root owner and bot steps are labelled; the simulations are [owner, no root]; the tool says it never runs apt",
      all(x in out for x in ("[owner, root]", "[bot, no root]", "[owner, no root] simulate TRANSACTION 1", "[owner, no root] simulate TRANSACTION 2", "never runs apt")), out)
check("plan: preflight lines (repo, packages, pin, /boot, gate, busy switch)", all(x in out for x in ("ok     repo", "ok     packages", "ok     pin", "/boot", "ok     gate idle", "busy switch")), out[:900])
check("plan: the token is not printed", TOKEN not in out + err)

host_state()
rc, out, _ = run("plan", "driver", "--to", "595.200.01")
check("plan: a target the repo does not offer is NOT OK (exit 1): no steps, only 'sudo apt update, then plan again'",
      rc == 1 and "NOT OK repo" in out and "NEXT (stale package lists?)" in out and "$ " not in out, out[:700])
rc, out, _ = run("plan", "driver", "--to", OLD)
check("plan: the installed version is NOT OK (nothing to update)", rc == 1 and "already runs" in out)
rc, out, _ = run("plan", "driver", "--to", "580.126.09")
check("plan: an older target is a rollback, not an update", rc == 1 and "rollback" in out)
rc, out, _ = run("plan", "driver", "--to", NEW, env_extra={"UPKEEP_BOOT_MIN_MB": "999999999"})
check("plan: /boot too small is NOT OK, and no steps are printed", rc == 1 and "NOT OK /boot" in out and "NO STEPS" in out and "$ " not in out, out[:500])
GATE["services"] = {"llm": {"port": 8630, "running": True, "leases": 1, "mode": "interactive"}, "stt": {"port": 8620, "running": False, "leases": 0}}
rc, out, _ = run("plan", "driver", "--to", NEW)
check("plan: a running service is a 'wait' (the steps close the gate and wait), not a failure", rc == 0 and "wait   gate idle" in out and "llm" in out, out[:700])
GATE["services"] = {}
GATE["blocked"] = "vr"
rc, out, _ = run("plan", "driver", "--to", NEW)
check("plan: a person using the card (VR) is reported", "a person is using the card" in out)
GATE["blocked"] = None
set_env_file(token=None)
rc, out, err = run("plan", "driver", "--to", NEW)
check("plan: no GATE_TOKEN is NOT OK with the setup word, never a crash", rc == 1 and "no_gate_token" in out, out[:600])
set_env_file()
rc, out, _ = run("plan", "driver", "--to", NEW, env_extra={"GATE_PORT": "1"})
check("plan: an unreachable gate is NOT OK", rc == 1 and "NOT OK gate" in out, out[:600])
os.makedirs(os.path.join(GSTATE), exist_ok=True)
with open(os.path.join(GSTATE, "driver_watch.json"), "w") as f:
    json.dump({"target": NEW, "update_class": "performance"}, f)
rc, out, _ = run("plan", "driver", "--to", NEW)
check("plan: a performance update ends with the bench step", "PERFORMANCE (driver_watch)" in out and "bench_gate.py --recheck" in out)
with open(os.path.join(GSTATE, "driver_watch.json"), "w") as f:
    json.dump({"target": NEW, "update_class": "security"}, f)
rc, out, _ = run("plan", "driver", "--to", NEW)
check("plan: a security update is applied fast, no bench step", "SECURITY (driver_watch): apply fast" in out and "bench_gate.py" not in out)

# ================================================================================================================ check-sim
one = open(os.path.join(FIX, "sim_one_transaction.txt")).read()
two = open(os.path.join(FIX, "sim_driver_after_pin.txt")).read()
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=one)
SHOW["check-sim (one transaction)"] = out
check("check-sim: the one-transaction output is 'not ok: pin not swapped'", rc == 1 and "not ok" in out and "pin not swapped" in out and "ONE transaction" in out, out)
check("check-sim: it names the packages left at the old version", "nvidia-open (595.71.05)" in out)
rc, out, _ = run("check-sim", os.path.join(FIX, "sim_one_transaction.txt"))
check("check-sim: a FILE argument works and the target is inferred from the new pin", rc == 1 and "target 595.112.07" in out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two)
SHOW["check-sim (after the pin, 58 upgraded)"] = out
check("check-sim: the driver simulation after the pin swap is ok", rc == 0 and out.startswith("check-sim: ok"), out)
check("check-sim: ok mentions the 58 packages and the firmware note", "58 driver package(s) go to 595.112.07" in out and "firmware-nvidia-gsp" in out)
rc, out, _ = run("check-sim", "-", stdin=two)
check("check-sim: ok without --to (target inferred)", rc == 0 and "target 595.112.07" in out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "Remv gpu-unlock-dkms [2.0.0]\n")
check("check-sim: removing gpu-unlock-dkms is not ok", rc == 1 and "protected package: gpu-unlock-dkms" in out, out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "Remv gpu-unlock-firmware [2.0.0]\n")
check("check-sim: removing gpu-unlock-firmware is not ok", rc == 1 and "gpu-unlock-firmware" in out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + f"Remv linux-image-{KERNELS[1]} [6.12.115-1]\n")
check("check-sim: removing the running kernel is not ok", rc == 1 and "protected package: linux-image-" + KERNELS[1] in out, out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "Remv docker-ce [5:27.0]\n")
check("check-sim: removing another protected package (docker) is not ok", rc == 1 and "docker-ce" in out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "The following packages will be REMOVED:\n  gpu-unlock-dkms*\n")
check("check-sim: the apt 2 'will be REMOVED' block is read too", rc == 1 and "gpu-unlock-dkms" in out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "Removing:\n  nvidia-open\n")
check("check-sim: the apt 3 'Removing:' block with a driver package is not ok", rc == 1 and "removes a driver package: nvidia-open" in out)
left = two.replace("Inst nvidia-open [595.71.05-1] (595.112.07-1", "Inst nvidia-open [595.71.05-1] (595.80.01-1", 1)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=left)
check("check-sim: a driver package that goes to another version is not ok", rc == 1 and "nvidia-open goes to 595.80.01" in out, out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "The following packages have been kept back:\n  libnvidia-gl\n")
check("check-sim: a kept-back driver package is not ok", rc == 1 and "kept back" in out)
pin_only = "Reading package lists...\nInst nvidia-driver-pinning-595.112.07 (595.112.07-1 u [amd64])\nRemv nvidia-driver-pinning-595.71.05 [595.71.05-1]\n"
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=pin_only)
check("check-sim: the pin-only simulation is recognised as the pin step, not the driver step", rc == 1 and "only the pin" in out, out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin="Reading package lists...\n0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n")
check("check-sim: an empty simulation is not ok", rc == 1)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "Inst nvidia-cuda-toolkit [12.4.1-1] (12.6.0-1 u [amd64])\n")
check("check-sim: a package with its own version scheme is not judged against the driver", rc == 0, out)

# ================================================================================================================ snapshot
host_state()
rc, out, _ = run("snapshot")
check("snapshot: print-only by default, nothing is written", rc == 0 and "not saved" in out and not os.path.exists(STATE), out)
rc, out, _ = run("snapshot", "--apply")
check("snapshot --apply saves it", rc == 0 and "snapshot saved: " in out, out)
snaps = sorted(os.listdir(os.path.join(STATE, "snapshots")))
snap = json.load(open(os.path.join(STATE, "snapshots", snaps[-1])))
check("snapshot: driver, pin, packages (nvidia*, libnvidia*, firmware-nvidia*, container toolkit, gpu-unlock*), kernels, dkms, /boot",
      snap["driver"] == OLD and snap["pins"] == [f"nvidia-driver-pinning-{OLD}"] and snap["packages"].get("nvidia-open") == OLD + "-1"
      and snap["packages"].get("nvidia-driver-libs:i386") == OLD + "-1" and snap["packages"].get("nvidia-container-toolkit") == "1.20.1-1"
      and snap["packages"].get("gpu-unlock-dkms") == "2.0.0" and snap["packages"].get("firmware-nvidia-gsp") == OLD + "-1" and "vim" not in snap["packages"]
      and snap["running_kernel"] == KERNELS[1] and snap["kernels"] == KERNELS and len(snap["dkms"]) == 4 and snap["boot_free_mb"] is not None, json.dumps(snap)[:400])
check("snapshot: a second one the same second does not overwrite", run("snapshot", "--apply")[0] == 0 and len(os.listdir(os.path.join(STATE, "snapshots"))) == 2)
rc, out, _ = run("snapshot", "--list")
check("snapshot --list", rc == 0 and out.count("driver " + OLD) == 2, out)
check("state dir permissions: dirs 700, files 600", mode(STATE) == 0o700 and mode(os.path.join(STATE, "snapshots")) == 0o700
      and all(mode(os.path.join(STATE, "snapshots", n)) == 0o600 for n in os.listdir(os.path.join(STATE, "snapshots"))) and mode(os.path.join(STATE, "audit.jsonl")) == 0o600,
      oct(mode(STATE)))
os.chmod(STATE, 0o755)
run("snapshot", "--apply")
check("state dir permissions are put back to 700 on use", mode(STATE) == 0o700)

# ================================================================================================================ busy / idle
rc, out, _ = run("busy", "status")
check("busy: off at the start", "busy: off" in out)
rc, out, _ = run("busy", "on")
check("busy on without --apply changes nothing", "would switch" in out and not os.path.exists(os.path.join(GSTATE, "busy")))
rc, out, _ = run("busy", "on", "--apply")
check("busy on --apply creates the gate's switch file", rc == 0 and os.path.exists(os.path.join(GSTATE, "busy")))
rc, out, _ = run("idle")
check("idle: yes with the switch on and nothing running (the gate reports blocked=busy)", rc == 0 and out.startswith("idle: yes"), out)
GATE["services"] = {"imggen": {"port": 8660, "running": True, "leases": 1, "mode": "batch"}}
rc, out, _ = run("idle")
check("idle: no while a service runs, naming it", rc == 1 and "imggen" in out, out)
GATE["services"] = {}
GATE["bench"] = {"id": "x"}
check("idle: no while a bench or selfcheck runs", run("idle")[0] == 1)
GATE["bench"] = None
rc, out, _ = run("busy", "off", "--apply")
check("busy off --apply removes it", rc == 0 and not os.path.exists(os.path.join(GSTATE, "busy")))
os.makedirs(os.path.join(TMP, "other-state"))
open(os.path.join(TMP, "other-state", "busy"), "w").close()
rc, out, _ = run("idle", env_extra={"GATE_STATE_DIR": os.path.join(TMP, "other-state")})
check("idle: a busy switch the gate cannot see (another state dir) is not idle", rc == 1 and "does not report blocked=busy" in out, out)

# ================================================================================================================ rollback
host_state(updated=True)
rc, out, _ = run("rollback")
SHOW["rollback"] = out
check("rollback: exit 0, names the snapshot's driver", rc == 0 and f"driver {OLD}" in out and f"now {NEW}" in out, out[:600])
check("rollback: two transactions: the old pin ALONE first, then the explicit =versions of the driver packages and the container toolkit",
      pos(out, f"$ sudo apt install nvidia-driver-pinning-{OLD}\n", "apt install -s --allow-downgrades", "$ sudo apt install --allow-downgrades "), out)
t2 = next(l for l in out.splitlines() if l.strip().startswith("$ sudo apt install --allow-downgrades"))
check("rollback: transaction 2 has the exact old versions and no pin", all(x in t2 for x in (f"nvidia-open={OLD}-1", f"nvidia-driver-libs:i386={OLD}-1", f"firmware-nvidia-gsp={OLD}-1",
                                                                                           "libnvidia-container1=1.20.1-1", "nvidia-container-toolkit-base=1.20.1-1")) and "pinning" not in t2, t2)
check("rollback: dkms status, reboot and verify against the OLD version follow", pos(out, "dkms status", "sudo reboot", f"verify --to {OLD} --apply"), out)
check("rollback: the simulation is checked against the old target", f"check-sim - --to {OLD}" in out)
check("rollback: a security rollback warning and the log hint", "leaves the host exposed" in out and "log --add rollback" in out)
write("madison.txt", "nvidia-open | 595.112.07-1 | u  Packages\n")
rc, out, _ = run("rollback")
check("rollback: an old version no longer in the repo is NOT OK and named", rc == 1 and "not offered any more" in out and "nvidia-open=595.71.05-1" in out, out[:700])
host_state(updated=True)
sid = sorted(os.listdir(os.path.join(STATE, "snapshots")))[0][:-5]
rc, out, _ = run("rollback", sid)
check("rollback SNAPSHOT_ID picks that snapshot", rc == 0 and sid in out)
rc, out, err = run("rollback", "nope")
check("rollback: an unknown snapshot is a clear error", rc == 2 and "no snapshot nope" in err)
host_state()
rc, out, _ = run("rollback")
check("rollback: nothing to roll back when the host equals the snapshot", rc == 1 and "nothing to roll back" in out)

# ================================================================================================================ verify
host_state(updated=True)
rc, out, _ = run("verify", "--to", NEW, "--installed")
check("verify --installed: ok when the pin, the packages and dkms are at the target for every kernel with headers", rc == 0 and "RESULT: ok" in out, out)
host_state(updated=True, dkms_missing={"gpu-unlock": KERNELS[0]})
rc, out, _ = run("verify", "--to", NEW, "--installed")
check("verify --installed: a kernel without a gpu-unlock build is FAIL (do not reboot)", rc == 1 and "FAIL  dkms" in out and "gpu-unlock for " + KERNELS[0] in out and "do not reboot" in out, out)
host_state(updated=True, dkms_missing={"nvidia": KERNELS[1]})
rc, out, _ = run("verify", "--to", NEW, "--installed")
check("verify --installed: a kernel without nvidia/TARGET is FAIL", rc == 1 and f"nvidia/{NEW} for {KERNELS[1]}" in out)
host_state()
rc, out, _ = run("verify", "--to", NEW, "--installed")
check("verify --installed: packages still at the old version is FAIL", rc == 1 and "FAIL  packages" in out and "FAIL  pin" in out)

# post-reboot: ok
host_state(updated=True)
open(os.path.join(GSTATE, "busy"), "w").close()
if os.path.exists(os.path.join(FAKE, "selfcheck_ran")):
    os.unlink(os.path.join(FAKE, "selfcheck_ran"))
rc, out, _ = run("verify", "--to", NEW, sel_exit=0)
check("verify without --apply: driver/dkms/gate checked, the selfcheck is NOT run, result incomplete (exit 2)", rc == 2 and "incomplete" in out and not os.path.exists(os.path.join(FAKE, "selfcheck_ran")), out)
check("verify without --apply leaves the busy switch alone", os.path.exists(os.path.join(GSTATE, "busy")))
rc, out, _ = run("verify", "--to", NEW, "--apply", sel_exit=0)
SHOW["verify ok"] = out
check("verify --apply: ok -> RESULT ok, selfcheck run, busy switch lifted", rc == 0 and "RESULT: ok" in out and "selfcheck: exit 0" in out and "busy: off" in out
      and not os.path.exists(os.path.join(GSTATE, "busy")), out)
check("verify: the selfcheck ran with the busy switch lifted (the gate's bench refuses while it is on)", "busy_exists=False" in open(os.path.join(FAKE, "selfcheck_ran")).read())
log_rows = [json.loads(l) for l in open(os.path.join(STATE, "audit.jsonl"))]
check("verify ok: one log line with step, result, versions, time", any(r["step"] == "verify" and r["result"] == "ok" and r["versions"]["driver"] == NEW and r["at"].endswith("Z") for r in log_rows))

# post-reboot: degraded
open(os.path.join(GSTATE, "busy"), "w").close()
rc, out, _ = run("verify", "--to", NEW, "--apply", sel_exit=1)
SHOW["verify degraded"] = out
check("verify --apply: degraded -> RESULT degraded, exit 1", rc == 1 and "RESULT: degraded" in out and "fp32acc_slow" in out, out[:800])
check("verify degraded: the gate stays CLOSED (busy switch back on)", os.path.exists(os.path.join(GSTATE, "busy")))
check("verify degraded: prints the rollback commands (old pin alone, then the exact old versions)", pos(out, "upkeep rollback to snapshot", f"$ sudo apt install nvidia-driver-pinning-{OLD}\n", "--allow-downgrades"), out)
log_rows = [json.loads(l) for l in open(os.path.join(STATE, "audit.jsonl"))]
check("verify degraded: logged", any(r["step"] == "verify" and r["result"] == "degraded" for r in log_rows))
rc, out, _ = run("verify", "--to", NEW, "--apply", sel_exit=75)
check("verify: a skipped selfcheck is incomplete (exit 2), the gate stays closed, no rollback advice", rc == 2 and "incomplete" in out and os.path.exists(os.path.join(GSTATE, "busy")) and "$ sudo" not in out, out)
host_state(updated=True, smi=False)
rc, out, _ = run("verify", "--to", NEW, "--apply", sel_exit=0)
check("verify: no driver loaded after the reboot is FAIL with the rollback, selfcheck not even run", rc == 1 and "FAIL  driver" in out and "driver not loaded" in out and "$ sudo apt install nvidia-driver-pinning-" in out, out[:600])
host_state(updated=True, running="6.12.117+deb13-amd64")
rc, out, _ = run("verify", "--to", NEW, "--apply", sel_exit=0)
check("verify: a running kernel with no dkms build is FAIL", rc == 1 and "FAIL  kernel" in out)
host_state(updated=True)
set_env_file(token=None)
rc, out, _ = run("verify", "--to", NEW, "--apply", sel_exit=0)
check("verify: a gate that cannot be read is FAIL (setup word, no token printed)", rc == 1 and "no_gate_token" in out)
set_env_file()

# ================================================================================================================ log
rc, out, _ = run("log")
check("log: shows the audit lines (busy, snapshot, verify)", rc == 0 and all(x in out for x in ("snapshot", "busy-on", "verify")) and "degraded" in out, out)
rc, out, _ = run("log", "--json", "-n", "3")
check("log --json: valid JSON lines, last N", rc == 0 and len(out.strip().splitlines()) == 3 and all(json.loads(l)["step"] for l in out.splitlines()))
before = open(os.path.join(STATE, "audit.jsonl")).read()
rc, out, _ = run("log", "--add", "owner-apt-transaction-1", "--result", "done")
check("log --add needs --apply", rc == 2 and open(os.path.join(STATE, "audit.jsonl")).read() == before)
rc, out, _ = run("log", "--add", "owner-apt-transaction-1", "--result", "done", "--note", "pin swapped", "--apply")
after = open(os.path.join(STATE, "audit.jsonl")).read()
check("log --add --apply appends one line and never rewrites the old ones", rc == 0 and after.startswith(before) and len(after.splitlines()) == len(before.splitlines()) + 1)
check("log: the owner's step is shown with its note", "owner-apt-transaction-1" in run("log")[1] and "pin swapped" in run("log")[1])
check("the audit log is mode 600", mode(os.path.join(STATE, "audit.jsonl")) == 0o600)

# ================================================================================================================ review fixes: check-sim
host_state()
quiet = two  # the driver simulation after the pin swap: ok on its own
EXTRA = [("network-manager", "network-manager [1.52]"), ("xserver-xorg-core", "xserver-xorg-core [2:21.1]"), ("docker-compose-plugin", "docker-compose-plugin [2.29]"),
         ("cuda-toolkit-13-0", "cuda-toolkit-13-0 [13.0.1-1]"), ("the pending kernel", "linux-image-6.12.117+deb13-amd64 [6.12.117-1]")]
for label, rm in EXTRA:
    rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "Remv " + rm + "\n")
    check(f"check-sim: a removal that is not protected is not ok either ({label})", rc == 1 and "not ok" in out and "removes " + rm.split()[0] in out and "nothing but the old pin" in out, out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + f"Remv nvidia-driver-pinning-{OLD} [{OLD}-1]\n")
check("check-sim: the replaced old pin is the one removal that is fine", rc == 0 and "old pin" in out, out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "Remv docker-compose-plugin [2.29]\n", env_extra={"UPKEEP_ALLOW_REMOVE": "^docker-compose-plugin$,[bad("})
check("check-sim: UPKEEP_ALLOW_REMOVE is the explicit exception (a broken regex in it is dropped, no crash)", rc == 0 and "allowed by UPKEEP_ALLOW_REMOVE" in out, out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "".join(f"Remv extra-package-{i} [1.0]\n" for i in range(60)))
check("check-sim: 60 removals print a capped list with the count of the rest, not 60 lines", rc == 1 and len(out.splitlines()) < 25 and "52 more reasons" in out, len(out.splitlines()))
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin="Inst nvidia-open [595.71.05-1] (595.112.07-1 https://example.invalid/x [amd64])\n")
check("check-sim: coverage: a simulation of ONE driver package is not ok when the plan installs more (the host's list is the expectation)",
      rc == 1 and "does not cover 4 of the 5 driver package(s)" in out and "nvidia-driver" in out, out)
indented = "".join("    " + l + "\n" for l in two.splitlines())
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=indented)
check("check-sim: a paste with every line indented still reads (ok)", rc == 0, out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=indented + "    Remv gpu-unlock-dkms [2.0.0]\n")
check("check-sim: an indented Remv is not silently missed", rc == 1 and "protected package: gpu-unlock-dkms" in out, out)
quoted = "".join("> " + l + "\n" for l in two.splitlines())
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=quoted + "> Remv xserver-xorg-core [2:21.1]\n")
check("check-sim: a `> ` quoted paste is read, its removal caught", rc == 1 and "removes xserver-xorg-core" in out, out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=indented + "    Removing:\n      xserver-xorg-core\n    Summary:\n")
check("check-sim: an indented 'Removing:' block ends where its indentation ends", rc == 1 and "removes xserver-xorg-core" in out and "Summary" not in out.replace("check-sim", ""), out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "E: Unable to correct problems, you have held broken packages.\n")
check("check-sim: an `E:` line is not ok", rc == 1 and "apt reports: E: Unable to correct problems" in out, out)
rc, out, _ = run("check-sim", "-", "--to", NEW, stdin=two + "The following packages have unmet dependencies:\n")
check("check-sim: 'unmet dependencies' is not ok", rc == 1 and "apt reports: The following packages have unmet dependencies" in out, out)
rc, out, err = run("check-sim", "/nonexistent/sim.txt", "--to", NEW)
check("check-sim: a file that cannot be read is exit 2 with one message and no traceback", rc == 2 and "Traceback" not in err and "cannot read" in err and out == "", (rc, err))

# --pin
rc, out, _ = run("check-sim", "-", "--pin", "--to", NEW, stdin=one)
check("check-sim --pin: the pin swap plus the container toolkit is ok", rc == 0 and out.startswith("check-sim: ok"), out)
rc, out, _ = run("check-sim", "-", "--pin", "--to", NEW, stdin=one + "Inst nvidia-open [595.71.05-1] (595.112.07-1 https://example.invalid/x [amd64])\n")
check("check-sim --pin: a driver package in the pin transaction is not ok", rc == 1 and "nvidia-open is installed or upgraded in the pin transaction" in out, out)
rc, out, _ = run("check-sim", "-", "--pin", "--to", NEW, stdin=one + "Remv network-manager [1.52]\n")
check("check-sim --pin: any removal but the old pin is not ok", rc == 1 and "removes network-manager" in out, out)
rc, out, _ = run("check-sim", "-", "--pin", "--to", NEW, stdin="Inst nvidia-driver-pinning-595.80.01 (595.80.01-1 u [amd64])\n")
check("check-sim --pin: the wrong pin version is not ok", rc == 1 and f"does not install nvidia-driver-pinning-{NEW}" in out, out)
rc, out, _ = run("check-sim", "-", "--pin", stdin=one)
check("check-sim --pin without --to cannot judge (not ok)", rc == 1 and "without --to" in out, out)

# --rollback-from
host_state(updated=True)
SNAPDIR = os.path.join(TMP, "state-rb")
rc, out, _ = run("snapshot", "--apply", env_extra={"UPKEEP_STATE_DIR": SNAPDIR})        # a clean NEW-state snapshot (id 1)
host_state()
rc, out, _ = run("snapshot", "--apply", env_extra={"UPKEEP_STATE_DIR": SNAPDIR})        # the OLD one (id 2, newest)
host_state(updated=True)
dp = open(os.path.join(FAKE, "dpkg.txt")).read()
write("dpkg.txt", dp + f"ii |nvidia-newonly|{NEW}-1\n")
rb_sim = "Inst nvidia-open [595.112.07-1] (595.71.05-1 u [amd64])\n".replace("nvidia-open", "nvidia-open")
want_old = ["firmware-nvidia-gsp", "libcuda1:amd64", "libegl-nvidia0", "libglx-nvidia0", "libnvcuvid1", "libnvidia-compute", "nvidia-driver", "nvidia-driver-libs:i386", "nvidia-open", "nvidia-opencl-icd"]
rb_full = "".join(f"Inst {n} [{NEW}-1] ({OLD}-1 https://example.invalid/x [amd64])\n" for n in want_old)
rc, out, _ = run("check-sim", "-", "--to", OLD, stdin=rb_full + "Remv nvidia-newonly [595.112.07-1]\n", env_extra={"UPKEEP_STATE_DIR": SNAPDIR})
check("check-sim: without --rollback-from a driver package that is removed is not ok", rc == 1 and "removes a driver package: nvidia-newonly" in out, out)
rc, out, _ = run("check-sim", "-", "--to", OLD, "--rollback-from", sorted(os.listdir(os.path.join(SNAPDIR, "snapshots")))[-1][:-5], stdin=rb_full + "Remv nvidia-newonly [595.112.07-1]\n",
                 env_extra={"UPKEEP_STATE_DIR": SNAPDIR})
check("check-sim --rollback-from: a driver package that came with the update (not in the snapshot) may be removed", rc == 0 and "came with the update" in out, out)
rc, out, _ = run("check-sim", "-", "--to", OLD, "--rollback-from", sorted(os.listdir(os.path.join(SNAPDIR, "snapshots")))[-1][:-5], stdin=rb_full + "Remv gpu-unlock-dkms [2.0.0]\n",
                 env_extra={"UPKEEP_STATE_DIR": SNAPDIR})
check("check-sim --rollback-from: a protected package is still not ok", rc == 1 and "protected package: gpu-unlock-dkms" in out, out)
rc, out, _ = run("check-sim", "-", "--to", OLD, "--rollback-from", "nope", stdin=rb_full, env_extra={"UPKEEP_STATE_DIR": SNAPDIR})
check("check-sim --rollback-from: an unknown snapshot is exit 2", rc == 2, out)
rc, out, _ = run("rollback", env_extra={"UPKEEP_STATE_DIR": SNAPDIR})
t2 = next(l for l in out.splitlines() if l.strip().startswith("$ sudo apt install --allow-downgrades"))
check("rollback: the default snapshot is the newest whose driver differs from the host's (the OLD one, not the NEW state taken first or last)", f"driver {OLD}" in out.splitlines()[0], out.splitlines()[0])
check("rollback: with a package that came with the update the downgrade line has no --no-remove (check-sim judges instead) and says so in the preflight",
      "--no-remove" not in t2 and "nvidia-newonly" in out and "check-sim lets the rollback remove them" in out, out[:900])
check("rollback: the simulation line names the snapshot for check-sim", "--rollback-from 2" in out, out)
check("rollback: lists the snapshots it could use", "snapshots here (newest last):" in out and "pick another with" in out, out)
host_state(updated=True)
rc, out, _ = run("rollback", env_extra={"UPKEEP_STATE_DIR": SNAPDIR})
t2 = next(l for l in out.splitlines() if l.strip().startswith("$ sudo apt install --allow-downgrades"))
check("rollback: with nothing new since the snapshot the downgrade line has --no-remove", "--no-remove" in t2, t2)

# ================================================================================================================ review fixes: snapshot family, half-updated
host_state()
rc, out, _ = run("snapshot", "--apply", env_extra={"UPKEEP_STATE_DIR": os.path.join(TMP, "state-fam")})
fam = json.load(open(os.path.join(TMP, "state-fam", "snapshots", os.listdir(os.path.join(TMP, "state-fam", "snapshots"))[0])))
check("snapshot: the WHOLE driver family is in it (libcuda1, libnvcuvid1, libegl/libglx-nvidia, the arch-qualified key too), not only the shorter list of before",
      all(fam["packages"].get(k) == OLD + "-1" for k in ("libcuda1:amd64", "libnvcuvid1", "libegl-nvidia0", "libglx-nvidia0")) and fam["toolkit"] == "1.20.1-1", sorted(fam["packages"]))
check("snapshot: the snapshot pattern is built from the family pattern plus gpu-unlock and the container packages",
      all(U.SNAPSHOT_RE.match(n) for n in ("libcuda1", "libnvcuvid1", "libgles-nvidia1", "libglx-nvidia0", "gpu-unlock-dkms", "nvidia-container-toolkit", "libnvidia-container1", "nvidia-driver-pinning-1.2")) and not U.SNAPSHOT_RE.match("vim"))
HALF = os.path.join(TMP, "state-half")
host_state()
dp = open(os.path.join(FAKE, "dpkg.txt")).read().replace(f"nvidia-driver-pinning-{OLD}|{OLD}-1", f"nvidia-driver-pinning-{NEW}|{NEW}-1")      # T1 done, T2 not
write("dpkg.txt", dp)
rc, out, err = run("snapshot", "--apply", env_extra={"UPKEEP_STATE_DIR": HALF})
check("snapshot: a half-updated host (the new pin, the old driver) is REFUSED, nothing saved", rc == 1 and "REFUSED" in err and "not the one of the running driver" in err and not os.path.exists(os.path.join(HALF, "snapshots")), (rc, err))
host_state(smi=False)
rc, out, err = run("snapshot", "--apply", env_extra={"UPKEEP_STATE_DIR": HALF})
check("snapshot: an unknown driver (nvidia-smi silent) is REFUSED", rc == 1 and "driver is unknown" in err, err)
host_state()
dp = open(os.path.join(FAKE, "dpkg.txt")).read().replace(f"ii |nvidia-open|{OLD}-1", f"ii |nvidia-open|{NEW}-1")      # one driver package already at the new version
write("dpkg.txt", dp)
rc, out, err = run("snapshot", "--apply", env_extra={"UPKEEP_STATE_DIR": HALF})
check("snapshot: a driver package at another version than the driver is REFUSED", rc == 1 and "nvidia-open" in err, err)
rc, out, err = run("snapshot", "--apply", "--force", env_extra={"UPKEEP_STATE_DIR": HALF})
check("snapshot --force saves it anyway, says FORCED and the log says forced", rc == 0 and "FORCED" in out and len(os.listdir(os.path.join(HALF, "snapshots"))) == 1
      and any(json.loads(l)["result"] == "forced" for l in open(os.path.join(HALF, "audit.jsonl"))), out)
host_state()

# ================================================================================================================ review fixes: hostile text
for flag_cmd in (("plan", "driver", "--to", "595.112.07; touch /tmp/pwn"), ("check-sim", "-", "--to", "595.112.07;x"), ("verify", "--to", "$(id)", "--installed"),
                 ("plan", "driver", "--to", "595.112.07 ")):
    rc, out, err = run(*flag_cmd, stdin="")
    check("--to is a fullmatch version: " + repr(flag_cmd[-1] if flag_cmd[-1] != "--installed" else flag_cmd[-2]) + " is refused before anything is printed",
          rc == 2 and "is not a driver version" in err and "sudo" not in out and out == "", (rc, err, out))
rc, out, _ = run("plan", "driver", "--to", "595.112.07")
check("plan: a good --to still works after the validation", rc == 0 and "$ sudo apt install" in out)
EVIL = os.path.join(TMP, "evil.json")
host_state(updated=True)


def evil(**over):
    d = {"schema": 1, "driver": OLD, "pins": [f"nvidia-driver-pinning-{OLD}"], "packages": {"nvidia-open": OLD + "-1", f"nvidia-driver-pinning-{OLD}": OLD + "-1"}}
    d.update(over)
    json.dump(d, open(EVIL, "w"))
    return run("rollback", EVIL)


for label, over in (("a version with a command in it", {"packages": {"nvidia-open": "1; touch /tmp/pwn #"}}),
                    ("a package name with a command in it", {"packages": {"nvidia-open; touch /tmp/pwn": "1.0"}}),
                    ("a pin name with a command in it", {"pins": ["nvidia-driver-pinning-595.71.05; id"]}),
                    ("a driver version with a command in it", {"driver": "595.71.05; id"}),
                    ("no packages table", {"packages": None}), ("packages as a string", {"packages": "nvidia-open=1"}), ("an empty packages table", {"packages": {}})):
    rc, out, err = evil(**over)
    check(f"rollback: a snapshot with {label} is refused, no steps printed, no crash", rc == 1 and "NOT OK: this snapshot cannot be used" in out and "$ " not in out and "Traceback" not in err and "touch" not in out.replace("touch /tmp/pwn' or", ""), (rc, out[-300:], err[-200:]))
rc, out, _ = evil()
check("rollback: the same file made clean gives steps", rc == 0 and "sudo apt install nvidia-driver-pinning-" in out, out[-300:])

# ================================================================================================================ review fixes: rollback preflight
host_state(updated=True)
write("pkgnames.txt", f"nvidia-driver-pinning-{NEW}\nnvidia-driver-pinning-580.126.09\n")      # the old pin is not offered any more
rc, out, _ = run("rollback", env_extra={"UPKEEP_STATE_DIR": SNAPDIR})
check("rollback preflight: the OLD PIN package itself is checked: not offered is NOT OK, no steps, the stale-list hint", rc == 1 and "NOT OK old pin in the repo" in out and "sudo apt update" in out and "$ " not in out, out[:700])
host_state(updated=True)
write("madison.txt", "".join(f"nvidia-open | {x} | u  Packages\n" for x in (NEW + "-1", OLD + "-10", "1.21.0-1", "1.20.1-1", "2.0.0")))      # 595.71.05-10 is not 595.71.05-1
rc, out, _ = run("rollback", env_extra={"UPKEEP_STATE_DIR": SNAPDIR})
check("rollback preflight: versions are compared whole, not as text (…-10 does not satisfy …-1)", rc == 1 and "not offered any more" in out and "nvidia-open=595.71.05-1" in out and "$ " not in out, out[:700])
host_state(updated=True)
rc, out, _ = run("rollback", env_extra={"UPKEEP_STATE_DIR": SNAPDIR})
check("rollback: a clean preflight prints the steps with check-sim --pin for transaction 1", rc == 0 and f"check-sim - --pin --to {OLD}" in out and "toolkit's own fixes stay" in out, out[:600])

# ================================================================================================================ review fixes: verify
host_state(updated=True)
open(os.path.join(GSTATE, "busy"), "w").close()
os.unlink(os.path.join(GSTATE, "busy"))
host_state(updated=True, dkms_missing={"gpu-unlock": KERNELS[0]})
rc, out, _ = run("verify", "--to", NEW, "--installed", "--apply")
check("verify --installed --apply: a failed check puts the busy switch ON (the gate stays closed)", rc == 1 and os.path.exists(os.path.join(GSTATE, "busy")) and "the gate is closed" in out, out)
os.unlink(os.path.join(GSTATE, "busy"))
host_state(updated=True)
dp = open(os.path.join(FAKE, "dpkg.txt")).read()
write("dpkg.txt", dp + "ii |linux-image-6.12.117+deb13-amd64|6.12.117-1\n")
rc, out, _ = run("verify", "--to", NEW, "--installed")
check("verify: the newest installed kernel without headers is a FAIL (grub boots it, no DKMS build, the host would come up without the driver)", rc == 1 and "FAIL  kernels" in out and "6.12.117+deb13-amd64 has no headers" in out, out)
host_state(updated=True)
dp = open(os.path.join(FAKE, "dpkg.txt")).read()
write("dpkg.txt", dp + "ii |linux-image-5.10.0-old|5.10.0-1\n")
rc, out, _ = run("verify", "--to", NEW, "--installed")
check("verify: an OLDER kernel without headers is only a note", rc == 0 and "note  kernels" in out, out)
host_state(updated=True)
open(os.path.join(BOOT, "vmlinuz-6.12.200+deb13-amd64"), "w").close()
rc, out, _ = run("verify", "--to", NEW, "--installed")
check("verify: a kernel in /boot that has no headers (even without a package row) is judged like an installed one", rc == 1 and "6.12.200+deb13-amd64 has no headers" in out, out)
os.unlink(os.path.join(BOOT, "vmlinuz-6.12.200+deb13-amd64"))
host_state(updated=True)
dp = open(os.path.join(FAKE, "dpkg.txt")).read()
write("dpkg.txt", dp + "ii |nvidia-cuda-toolkit|12.4.1-1\n")
write("manual.txt", open(os.path.join(FAKE, "manual.txt")).read() + "nvidia-cuda-toolkit\n")
rc, out, _ = run("verify", "--to", NEW, "--installed")
check("verify: a family package with its own version scheme (a CUDA toolkit) is named, not judged, and does not fail the update forever",
      rc == 0 and "1 with their own version scheme, not judged: nvidia-cuda-toolkit" in out, out)
host_state(updated=True)
rc, out, _ = run("verify", "--to", NEW, "--installed")
check("verify: the arch-qualified key does not make the packages check fail", rc == 0 and "FAIL  packages" not in out, out)
# the busy switch survives a crash of the selfcheck run (in-process, KeyboardInterrupt in the middle of the selfcheck)
os.environ["PATH"], os.environ["FAKE"] = BIN + os.pathsep + os.environ["PATH"], FAKE
env_ip = {"GATE_PORT": str(PORT), "GATE_TOKEN": TOKEN, "GATE_STATE_DIR": GSTATE, "UPKEEP_BOOT_DIR": BOOT}
host_state(updated=True)
open(os.path.join(GSTATE, "busy"), "w").close()
real_run_selfcheck = U.run_selfcheck


def boom(env, on_start=None):
    assert not os.path.exists(os.path.join(GSTATE, "busy")), "the switch must be lifted for the measurement"
    raise KeyboardInterrupt()


U.run_selfcheck = boom
try:
    U.cmd_verify(U.Sys(), env_ip, os.path.join(TMP, "state-ip"), NEW, False, True)
    interrupted = False
except KeyboardInterrupt:
    interrupted = True
U.run_selfcheck = real_run_selfcheck
check("verify: a crash or Ctrl-C during the selfcheck leaves the busy switch ON (the gate is never open on an unverified driver)", interrupted and os.path.exists(os.path.join(GSTATE, "busy")))
os.unlink(os.path.join(GSTATE, "busy"))

# UPKEEP_SELFCHECK is honoured only with UPKEEP_TEST=1
seen = []


class FakePopen:
    returncode = 0

    def __init__(self, argv, **kw):
        seen.append(argv)
        self.pid = 1

    def communicate(self, timeout=None):
        return "gpu selfcheck: ok\n", None


real_popen = U.subprocess.Popen
U.subprocess.Popen = FakePopen
U.run_selfcheck({"UPKEEP_SELFCHECK": "/tmp/evil.py"})
U.run_selfcheck({"UPKEEP_SELFCHECK": "/tmp/evil.py", "UPKEEP_TEST": TESTMARK})
U.subprocess.Popen = real_popen
check("UPKEEP_SELFCHECK alone cannot make verify run another script; with UPKEEP_TEST=1 (the selftest) it can",
      seen[0][2] == os.path.join(U.GPU, "gpu_selfcheck.py") and seen[1][2] == "/tmp/evil.py", seen)

# ================================================================================================================ review fixes: the allowlist is the whole argv
bad_argv = (["nvidia-smi", "--query-gpu=driver_version", "-pl", "100"], ["nvidia-smi", "--query-gpu=driver_version"], ["apt-cache", "madison", "x; reboot"], ["apt-cache", "policy"],
            ["dpkg-query", "-W"], ["dpkg-query", "-W", "-f=${Package}\n"], ["uname", "-r", "-a"], ["dkms", "status", "--all"], ["apt-mark", "showmanual", "x"])
r2 = 0
for argv in bad_argv:
    try:
        U.Sys().cmd(argv)
    except U.Refused:
        r2 += 1
check("Sys.cmd judges the WHOLE argument list (extra flags, odd package names, a changed format string are refused)", r2 == len(bad_argv), r2)
check("Sys.cmd still allows the exact read-only commands", all(U.Sys().allowed(a) for a in (["apt-mark", "showmanual"], ["dkms", "status"], ["uname", "-r"], ["apt-cache", "madison", "nvidia-open"],
      ["apt-cache", "pkgnames", "nvidia-driver-pinning-"], ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
      ["dpkg-query", "-W", "-f=${db:Status-Abbrev}|${binary:Package}|${Version}\n"])))

# ================================================================================================================ GPU card management: profile apply
import shutil
import hashlib

ST2 = os.path.join(TMP, "state-card")                      # the state dir of the card procedures (backups, log)
LIVE = os.path.join(TMP, "gpuhost-live")                   # the deployed gpu-host copy the gate runs from
SECRET = "SECRET-HOST-ENV-VALUE-31337"


def runc(*args, **kw):
    kw["env_extra"] = {"UPKEEP_STATE_DIR": ST2, "UPKEEP_GPU_DIR": LIVE, "UPKEEP_HEALTH_WAIT_S": "2", **(kw.get("env_extra") or {})}
    return run(*args, **kw)


def md5map(root):
    out = {}
    for dp, _d, fns in os.walk(root):
        for fn in fns:
            q = os.path.join(dp, fn)
            out[os.path.relpath(q, root)] = hashlib.md5(open(q, "rb").read()).hexdigest()
    return out


def restarts():
    return len(open(RESTARTS).read().split()) if os.path.exists(RESTARTS) else 0


def make_live():
    shutil.rmtree(LIVE, ignore_errors=True)
    for rel in ("gate/gate.py", "power_profiles.conf"):
        os.makedirs(os.path.dirname(os.path.join(LIVE, rel)), exist_ok=True)
        shutil.copy(os.path.join(U.GPU, rel), os.path.join(LIVE, rel))
    files = {"mcp_dispatch.sh": "#!/bin/sh\necho old dispatcher\n", "resolve_mcp/wrapper.py": "print('old')\n", "gate/README.md": "old readme\n",
             "host.env": f"GATE_TOKEN={SECRET}\n", "state/usage.jsonl": "{}\n", "gate/gate.log": "old log\n", "out/render.mp4": "x", "models/m.bin": "x", "gate/__pycache__/g.pyc": "x"}
    for rel, txt in files.items():
        os.makedirs(os.path.dirname(os.path.join(LIVE, rel)), exist_ok=True)
        open(os.path.join(LIVE, rel), "w").write(txt)
    os.chmod(os.path.join(LIVE, "mcp_dispatch.sh"), 0o755)


R_OLD, R_NEW = "20261101T100000", "20261118T100000"
CARD = {"name": "NVIDIA GeForce RTX 3060 Ti", "min_w": 70, "max_w": 200, "limit_w": 130}


def write_results(rows):
    d = os.path.join(HOME_, "bench_gate")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "results.jsonl"), "w") as f:
        f.write("not json\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")


def rec(run_id, task, cap=None, need=None, inform=False, unlock="on"):
    return {"kind": "recommend", "run": run_id, "task": task, "cap_w": cap, "need_mb": need, "need_informative": inform, "gpu_unlock": unlock}


RESULT_ROWS = [{"kind": "session", "run": R_OLD, "gpu": {"name": CARD["name"]}}, rec(R_OLD, "stt", 90, 1500),
               {"kind": "session", "run": R_NEW, "gpu": dict(CARD)}, rec(R_NEW, "stt", 110, 1600), rec(R_NEW, "tts-hq", 130, 5400), rec(R_NEW, "llm", 120, None),
               rec(R_NEW, "imggen", 130, 6000, inform=True), rec(R_NEW, "vidgen", 130, None, unlock="off"), rec(R_NEW, "mosher", 100, None), rec(R_NEW, "upscaler", 9999, None),
               {"kind": "recommend", "run": R_NEW, "task": "effectcraft", "verdict": "cpu_only"}]
write_results(RESULT_ROWS)
GATE["gpu"] = dict(CARD)
GATE["services"], GATE["blocked"], GATE["bench"] = {}, None, None
make_live()
host_state()
orig = md5map(LIVE)
for f_ in ("restarts", "healthz_down"):
    for q in (os.path.join(TMP, f_), os.path.join(FAKE, f_)):
        if os.path.exists(q):
            os.unlink(q)

rc, out, err = runc("plan", "profile")
SHOW["plan profile (dry run: the diff first)"] = out
check("profile: the dry run exits 0 and shows the run, the card section check and the DIFF first", rc == 0 and f"run {R_NEW}" in out and "ok     section: [RTX 3060 Ti] exists" in out and "DIFF" in out, out[:900])
check("profile: the diff shows the cap lines of the section (stt 100 -> 110, llm 130 -> 120, mosher added) and the VRAM needs of gate.py (stt 1540 -> 1600, tts-hq 5300 -> 5400)",
      all(x in out for x in ("-stt = 100", "+stt = 110", "-llm = 130", "+llm = 120", "+mosher = 100", "(8620, 1600, 40)", "(8650, 5400, 90)")), out)
check("profile: informative-only VRAM (imggen), a gpu-unlock-off row (vidgen), an out-of-range cap (upscaler) and a non-service (effectcraft) are skipped with a note",
      all(x in out for x in ("imggen: VRAM is informative only", "vidgen: measured with gpu-unlock off", "upscaler: cap 9999 W is outside", "effectcraft: not a service")) and "+upscaler" not in out and "+vidgen" not in out, out)
check("profile: a dry run changes nothing (md5 of every file, no backup, no restart, no log) and prints the confirm id and the steps with the confirm",
      md5map(LIVE) == orig and not os.path.exists(os.path.join(ST2, "backups")) and restarts() == 0 and re.search(r"--apply --confirm [0-9a-f]{12}", out) is not None and "STEPS" in out, out[-500:])
CID = re.search(r"--confirm ([0-9a-f]{12})", out).group(1)
check("profile: the token and host.env content never appear", TOKEN not in out and SECRET not in out)
rc, out, _ = runc("plan", "profile", "--apply")
check("profile: --apply without the confirm id is refused (the owner must have seen THIS diff), nothing changes", rc == 1 and "NOT APPLIED: --confirm must be " + CID in out and md5map(LIVE) == orig and restarts() == 0, out[-300:])
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", "0" * 12)
check("profile: a wrong confirm id is refused", rc == 1 and "NOT APPLIED" in out and md5map(LIVE) == orig)

# the gate answers with a card that is not the one the numbers come from
GATE["gpu"] = {"name": "NVIDIA GeForce GTX 1070 Ti", "min_w": 70, "max_w": 200}
rc, out, _ = runc("plan", "profile")
check("profile: numbers measured on another card than the gate reports are NOT OK, no diff", rc == 1 and "NOT OK card" in out and "DIFF" not in out, out[:600])
GATE["gpu"] = dict(CARD)
write_results([{"kind": "session", "run": R_NEW, "gpu": {"name": "NVIDIA GeForce RTX 9090"}}, rec(R_NEW, "stt", 110, 1600)])
rc, out, _ = runc("plan", "profile")
check("profile: no section for the card in power_profiles.conf is NOT OK (the tool never creates one)", rc == 1 and "NOT OK section" in out and "never creates one" in out and "DIFF" not in out, out[:600])
write_results([rec(R_NEW, "stt", 110, 1600)])
rc, out, _ = runc("plan", "profile")
check("profile: a run without a session row (which card?) is NOT OK", rc == 1 and "NOT OK card" in out, out[:500])
write_results([{"kind": "session", "run": R_NEW, "gpu": dict(CARD)}, rec(R_NEW, "stt", 110, 1600)])
rc, out, _ = runc("plan", "profile", "--run", "20200101T000000")
check("profile: a run id that is not in the results is NOT OK", rc == 1 and "NOT OK results" in out)
rc, out, _ = runc("plan", "profile", os.path.join(TMP, "nope.jsonl"))
check("profile: a results file that cannot be read is NOT OK, one line, no crash", rc == 1 and "NOT OK results" in out and "Traceback" not in out + _)
bad_run = run("plan", "profile", "--run", "x; reboot", env_extra={"UPKEEP_STATE_DIR": ST2})
bad_ref = run("plan", "profile", "--ref", "two words", env_extra={"UPKEEP_STATE_DIR": ST2})
check("profile: hostile --run and --ref values are refused by the parser (exit 2, no stdout)", bad_run[0] == 2 and not bad_run[1] and bad_ref[0] == 2 and not bad_ref[1])
write_results(RESULT_ROWS)
broken = open(os.path.join(LIVE, "gate", "gate.py")).read()
open(os.path.join(LIVE, "gate", "gate.py"), "w").write(broken.replace("SERVICES = {", "SERVICES = dict(", 1))
rc, out, _ = runc("plan", "profile")
check("profile: a deployed gate.py whose SERVICES table cannot be read (without running it) is NOT OK", rc == 1 and "NOT OK gate.py" in out, out[:500])
open(os.path.join(LIVE, "gate", "gate.py"), "w").write(broken)
check("profile: the unit tests of the editors: only the value changes, comments and other sections stay, a duplicate key is a problem",
      U.edit_conf("# c\n[A]\nx = 1  # k\n[B]\nx = 2\n", "A", {"x": 5})[0] == "# c\n[A]\nx = 5  # k\n[B]\nx = 2\n"
      and U.edit_conf("[A]\nx = 1\nx = 2\n", "A", {"x": 5})[2] and U.edit_conf("[A]\nx = 1\n", "Z", {"x": 5})[0] is None
      and U.edit_conf("[A]\nx = 1", "A", {"y": 3})[0] == "[A]\nx = 1\ny = 3\n")

# running services: the apply is refused without the flag
GATE["services"] = {"llm": {"port": 8630, "running": True, "leases": 1}, "stt": {"port": 8620, "running": False, "leases": 0}}
rc, out, _ = runc("plan", "profile")
cid_run = re.search(r"--confirm ([0-9a-f]{12})", out).group(1)
check("profile: with a service running the plan says the gate restart is refused and names the two ways out", "gate restart: refuse" in out and "--restart-while-running" in out and "--no-restart" in out, out)
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_run)
check("profile: --apply while a service runs and no flag: refused BEFORE any write (md5 intact, no backup, no restart, nothing logged as a change)",
      rc == 1 and "NOT APPLIED" in out and md5map(LIVE) == orig and restarts() == 0 and not os.path.exists(os.path.join(ST2, "backups")), out[-400:])
GATE["bench"] = {"id": "b1"}
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_run, "--restart-while-running")
check("profile: a running bench is never cut by a restart, even with the flag", rc == 1 and "a bench or selfcheck is running" in out and md5map(LIVE) == orig and restarts() == 0, out[-300:])
GATE["bench"] = None
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_run, "--restart-while-running")
SHOW["plan profile --apply (services running, flag given)"] = out
check("profile: with --restart-while-running the files are written, the gate restarted once (the gate adopts the running service), healthz and /state checked",
      rc == 0 and "APPLIED" in out and "RESULT: ok" in out and restarts() == 1 and "healthz: ok" in out and "adopted running: llm" in out, out[-900:])
new_md5 = md5map(LIVE)
changed = sorted(k for k in new_md5 if new_md5[k] != orig[k])
check("profile: exactly power_profiles.conf and gate/gate.py changed; host.env, state, logs, models, out and everything else are byte for byte the same", changed == ["gate/gate.py", "power_profiles.conf"], changed)
conf_new = open(os.path.join(LIVE, "power_profiles.conf")).read()
svc_old, svc_new = U.services_of(open(os.path.join(U.GPU, "gate", "gate.py")).read()), U.services_of(open(os.path.join(LIVE, "gate", "gate.py")).read())
check("profile: the written conf and gate.py read back as proposed (caps, needs), and ports and ready budgets of every service are unchanged",
      "stt = 110" in conf_new and "llm = 120" in conf_new and "mosher = 100" in conf_new and svc_new["stt"][1] == 1600 and svc_new["tts-hq"][1] == 5400
      and all(svc_new[k][0] == svc_old[k][0] and svc_new[k][2] == svc_old[k][2] for k in svc_old) and svc_new["imggen"][1] == svc_old["imggen"][1], (svc_new["stt"], svc_new["tts-hq"]))
changes = U.list_changes(ST2)
CH_P = changes[-1][0]
bk = os.path.join(ST2, "backups", CH_P)
check("profile: a timestamped backup of BOTH files exists (md5 equal to the originals), mode 700 for directories and 600 for files",
      len(changes) == 1 and CH_P.endswith("-profile") and md5map(os.path.join(bk, "tree"))["power_profiles.conf"] == orig["power_profiles.conf"]
      and md5map(os.path.join(bk, "tree"))["gate/gate.py"] == orig["gate/gate.py"] and mode(bk) == 0o700 and mode(os.path.join(bk, "tree", "gate")) == 0o700
      and mode(os.path.join(bk, "tree", "gate", "gate.py")) == 0o600 and mode(os.path.join(bk, "manifest.json")) == 0o600 and mode(os.path.join(ST2, "backups")) == 0o700, (changes, mode(bk)))
rc, logout, _ = runc("log", "--history")
SHOW["log --history (after profile apply)"] = logout
rows = [e for e in U.read_log(ST2) if e["step"] == "profile-apply"]
check("log: a profile apply writes a BEFORE line (what, md5 before, measurement reference, rollback command) and an AFTER line (md5 after, result, rollback)",
      [e["result"] for e in rows] == ["before", "ok"] and rows[0]["before"]["gate.py"] == orig["gate/gate.py"][:12] and rows[1]["after"]["gate.py"] == new_md5["gate/gate.py"][:12]
      and rows[1]["after"]["gate.py"] != rows[0]["before"]["gate.py"] and f"bench_gate {R_NEW}" in rows[0]["ref"] and rows[1]["rollback"] == f"python3 gpu-host/upkeep/upkeep.py undo {CH_P} --apply" and rows[0]["what"], rows)
check("log --history prints what, before, after, the measurement and the rollback command; the state events stay on the host (the state dir), not in the repo",
      all(x in logout for x in ("profile-apply", "before:", "after:", "ref: bench_gate", "rollback: python3 gpu-host/upkeep/upkeep.py undo " + CH_P)), logout)

# idempotent: the same proposal again changes nothing
rc, out, _ = runc("plan", "profile")
check("profile: running the same proposal again says there is nothing to change (no new backup, no restart)", rc == 0 and "nothing to change" in out and len(U.list_changes(ST2)) == 1)

# undo: the exact rollback
rc, out, _ = runc("undo")
check("undo: with no id it lists the changes", rc == 0 and CH_P in out and "profile" in out, out)
rc, out, _ = runc("undo", CH_P)
check("undo: print-only by default; it shows the md5 it restores and the gate rule", rc == 0 and "print-only" in out and "restore power_profiles.conf" in out and md5map(LIVE) == new_md5, out)
rc, out, _ = runc("undo", CH_P, "--apply")
check("undo: while a service runs it is refused like the apply (nothing restored)", rc == 1 and "NOT UNDONE" in out and md5map(LIVE) == new_md5 and restarts() == 1, out)
with open(os.path.join(LIVE, "power_profiles.conf"), "a") as f:
    f.write("# a hand edit after the change\n")
rc, out, _ = runc("undo", CH_P, "--apply", "--restart-while-running")
check("undo: files edited after the change are NOT silently overwritten (a later change or a hand edit)", rc == 1 and "was changed after this change" in out and "NOT UNDONE" in out, out)
with open(os.path.join(LIVE, "power_profiles.conf"), "w") as f:
    f.write(conf_new)
rc, out, _ = runc("undo", CH_P, "--apply", "--restart-while-running")
check("undo: --apply --restart-while-running restores BOTH files exactly (md5 equal to the originals) and restarts the gate once more", rc == 0 and md5map(LIVE) == orig and restarts() == 2 and "RESULT: ok" in out, out)
rc, out, _ = runc("undo", CH_P, "--apply", "--restart-while-running")
check("undo: a second undo says it was already undone", rc == 1 and "already undone" in out)
steps_logged = [(e["step"], e["result"]) for e in U.read_log(ST2)]
check("log: the undo is logged too (before and after)", ("undo", "before") in steps_logged and ("undo", "ok") in steps_logged, steps_logged)
bad_undo = run("undo", "../../etc", env_extra={"UPKEEP_STATE_DIR": ST2})
check("undo: a hostile change id is refused by the parser (exit 2)", bad_undo[0] == 2 and not bad_undo[1])
# a manifest whose paths point elsewhere is refused
mpath = os.path.join(ST2, "backups", CH_P, "manifest.json")
man = json.load(open(mpath))
man["files"][0]["path"] = os.path.join(TMP, "elsewhere.conf")
man.pop("undone_at", None)
json.dump(man, open(mpath, "w"))
rc, out, _ = runc("undo", CH_P, "--apply", "--restart-while-running")
check("undo: a manifest whose paths do not belong to its destination is refused (it decides what gets written)", rc == 1 and "does not belong to this change" in out and not os.path.exists(os.path.join(TMP, "elsewhere.conf")), out)

# the idle path: the gate is restarted by itself; --no-restart leaves the files only
GATE["services"] = {}
write_results(RESULT_ROWS)
before_r = restarts()
rc, out, _ = runc("plan", "profile")
cid_idle = re.search(r"--confirm ([0-9a-f]{12})", out).group(1)
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_idle, "--no-restart")
check("profile: --no-restart writes the files and leaves the running gate alone (it keeps the old values until its next restart)", rc == 0 and restarts() == before_r and "skipped (--no-restart)" in out and md5map(LIVE) != orig, out[-500:])
CH_N = U.list_changes(ST2)[-1][0]
rc, out, _ = runc("undo", CH_N, "--apply", "--no-restart")
check("undo: --no-restart restores the files only", rc == 0 and md5map(LIVE) == orig and restarts() == before_r, out)
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_idle)
check("profile: with an idle gate the apply restarts it by itself, once", rc == 0 and restarts() == before_r + 1 and "no service is running" in out and "nothing was running" in out, out[-600:])
CH_I = U.list_changes(ST2)[-1][0]
rc, out, _ = runc("undo", CH_I, "--apply")
check("undo: with an idle gate it restores and restarts by itself", rc == 0 and md5map(LIVE) == orig and restarts() == before_r + 2, out)

# ================================================================================================================ gate deploy
NEWSRC = os.path.join(TMP, "newtree")
shutil.rmtree(NEWSRC, ignore_errors=True)
shutil.copytree(LIVE, NEWSRC)
open(os.path.join(NEWSRC, "gate", "gate.py"), "a").write("\n# a new line in the deployed gate\n")
open(os.path.join(NEWSRC, "resolve_mcp", "wrapper.py"), "w").write("print('new')\n")
open(os.path.join(NEWSRC, "resolve_mcp", "extra.py"), "w").write("print('added')\n")
open(os.path.join(NEWSRC, "mcp_dispatch.sh"), "w").write("#!/bin/sh\necho new dispatcher\n")
open(os.path.join(NEWSRC, "host.env"), "w").write("GATE_TOKEN=fake-from-the-source-must-not-land\n")
open(os.path.join(NEWSRC, "state", "usage.jsonl"), "w").write("source state\n")
open(os.path.join(NEWSRC, "out", "render.mp4"), "w").write("source out\n")
open(os.path.join(NEWSRC, "models", "m.bin"), "w").write("source model\n")
open(os.path.join(NEWSRC, "gate", "gate.log"), "w").write("source log\n")
MCPDIR = os.path.join(HOME_, "bin")
os.makedirs(MCPDIR, exist_ok=True)
MCP = os.path.join(MCPDIR, "mcp_dispatch.sh")
open(MCP, "w").write("#!/bin/sh\necho old dispatcher\n")
os.chmod(MCP, 0o755)
mcp_orig = hashlib.md5(open(MCP, "rb").read()).hexdigest()
orig = md5map(LIVE)
gate_md5_old = orig["gate/gate.py"]
gate_md5_src = hashlib.md5(open(os.path.join(NEWSRC, "gate", "gate.py"), "rb").read()).hexdigest()
GATE["services"] = {}
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC)
SHOW["plan deploy (the plan: nothing is touched)"] = out
check("deploy: the plan shows the source, the destination, the counts, gate.py's md5 before and after, the excluded host data, the mcp copy and the gate rule",
      rc == 0 and "CHANGES: 3 changed, 1 added" in out and f"gate.py md5 {gate_md5_old[:12]} -> {gate_md5_src[:12]}" in out and "host data left alone" in out and "mcp_dispatch" in out
      and "gate restart: restart" in out and "STEPS" in out, out)
check("deploy: the plan changes nothing and prints a confirm id", md5map(LIVE) == orig and restarts() == before_r + 2 and hashlib.md5(open(MCP, "rb").read()).hexdigest() == mcp_orig and "--confirm" in out)
cid_d = re.search(r"--confirm ([0-9a-f]{12})", out).group(1)
check("deploy: host.env, state/, *.log, out/, models/, __pycache__ of the SOURCE are never in the change list, and the secret is not printed", "host.env" not in out.split("CHANGES")[1] and "usage.jsonl" not in out and "render.mp4" not in out
      and "m.bin" not in out and "fake-from-the-source" not in out and SECRET not in out)
check("deploy: the exclusion rule itself (unit)", all(U.excluded(x) for x in ("host.env", "gate/host.env", "state/x", "a/state/b", "x.log", "out/y", "models/z", "gate/__pycache__/q.pyc", ".git/config"))
      and not any(U.excluded(x) for x in ("gate/gate.py", "resolve_mcp/wrapper.py", "statement.py", "outline.md", "models.md")))
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--apply")
check("deploy: --apply without the confirm id is refused, nothing changes", rc == 1 and "NOT APPLIED: --confirm must be " + cid_d in out and md5map(LIVE) == orig)
GATE["services"] = {"llm": {"port": 8630, "running": True, "leases": 1}}
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--apply", "--confirm", cid_d)
check("deploy: with a service running and no flag the gate restart is refused BEFORE any write (nothing copied, no backup, no restart)",
      rc == 1 and "NOT APPLIED" in out and md5map(LIVE) == orig and restarts() == before_r + 2 and len(U.list_changes(ST2)) == 3, out[-300:])
GATE["services"] = {}
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--apply", "--confirm", cid_d)
SHOW["plan deploy --apply (idle gate)"] = out
dep_md5 = md5map(LIVE)
check("deploy: applied; gate.py md5 after equals the source's, the gate was restarted once, healthz and /state were checked",
      rc == 0 and "RESULT: ok" in out and dep_md5["gate/gate.py"] == gate_md5_src and restarts() == before_r + 3 and "healthz: ok" in out and f"gate.py md5 {gate_md5_old[:12]} -> {gate_md5_src[:12]}" in out, out[-700:])
touched = sorted(k for k in dep_md5 if orig.get(k) != dep_md5[k])
check("deploy: only the changed and added files were touched; host.env, state/, the log, out/, models/ and __pycache__ are byte for byte what they were",
      touched == ["gate/gate.py", "mcp_dispatch.sh", "resolve_mcp/extra.py", "resolve_mcp/wrapper.py"] and all(dep_md5[k] == orig[k] for k in orig if U.excluded(k)), touched)
check("deploy: the separate ~/bin/mcp_dispatch.sh copy was replaced by a plain copy (mode kept executable)", open(MCP).read().endswith("new dispatcher\n") and mode(MCP) == 0o755)
CH_D = U.list_changes(ST2)[-1][0]
bkd = os.path.join(ST2, "backups", CH_D)
bk_tree = md5map(os.path.join(bkd, "tree"))
check("deploy: a FULL backup of the deployed tree exists (every non-excluded file, md5 equal to the old ones; host.env and state are not copied), plus the old mcp_dispatch.sh",
      CH_D.endswith("-deploy") and all(bk_tree[k] == orig[k] for k in orig if not U.excluded(k)) and not any(U.excluded(k) for k in bk_tree) and "host.env" not in bk_tree
      and hashlib.md5(open(os.path.join(bkd, "mcp", "mcp_dispatch.sh"), "rb").read()).hexdigest() == mcp_orig and mode(bkd) == 0o700, (sorted(bk_tree)[:5], mode(bkd)))
rows = [e for e in U.read_log(ST2) if e["step"] == "gate-deploy"]
check("log: a deploy writes a before line (gate.py md5, tree digest, file count, source, rollback) and an after line (gate.py md5 = the source's, tree digest)",
      [e["result"] for e in rows] == ["before", "ok"] and rows[0]["before"]["gate.py"] == gate_md5_old[:12] and rows[1]["after"]["gate.py"] == gate_md5_src[:12]
      and rows[0]["before"]["tree"] != rows[1]["after"]["tree"] and "directory" in rows[0]["ref"] and rows[1]["rollback"].endswith(f"undo {CH_D} --apply"), rows)
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC)
check("deploy: the same source again says there is nothing to deploy", rc == 0 and "nothing to deploy" in out)
GATE["services"] = {"stt": {"port": 8620, "running": True, "leases": 0}}
rc, out, _ = runc("undo", CH_D, "--apply")
check("undo of a deploy: refused while a service runs without the flag", rc == 1 and "NOT UNDONE" in out and md5map(LIVE) == dep_md5)
rc, out, _ = runc("undo", CH_D, "--apply", "--restart-while-running")
SHOW["undo of the deploy"] = out
check("undo of a deploy: the backup is restored (every md5 equals the old tree, the added file is removed, the old mcp_dispatch.sh is back) and the gate restarts",
      rc == 0 and md5map(LIVE) == orig and not os.path.exists(os.path.join(LIVE, "resolve_mcp", "extra.py")) and hashlib.md5(open(MCP, "rb").read()).hexdigest() == mcp_orig
      and restarts() == before_r + 4 and "RESULT: ok" in out, out)
GATE["services"] = {}
# a gate that does not come back after the restart: rolled back at once
cid_d = re.search(r"--confirm ([0-9a-f]{12})", runc("plan", "deploy", "--from-dir", NEWSRC)[1]).group(1)
open(os.path.join(FAKE, "healthz_down"), "w").close()
r0 = restarts()
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--apply", "--confirm", cid_d)
os.unlink(os.path.join(FAKE, "healthz_down"))
check("deploy: a gate that does not answer after the restart is rolled back at once (files and mcp copy restored, two restarts tried, logged as rolled-back)",
      rc == 1 and "ROLLED BACK" in out and md5map(LIVE) == orig and hashlib.md5(open(MCP, "rb").read()).hexdigest() == mcp_orig and restarts() == r0 + 2
      and any(e["step"] == "gate-deploy" and e["result"] == "rolled-back" for e in U.read_log(ST2)), out[-600:])
# problems in the source or the destination
rc, out, _ = runc("plan", "deploy")
check("deploy: no source is NOT OK", rc == 1 and "give exactly one of --from-ref" in out)
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--from-ref", "HEAD")
check("deploy: two sources are NOT OK", rc == 1 and "exactly one" in out)
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--dest", os.path.join(TMP, "not-a-gpu-host"))
check("deploy: a destination that is not a deployed gpu-host tree is NOT OK, nothing is written there", rc == 1 and "NOT OK destination" in out and not os.path.exists(os.path.join(TMP, "not-a-gpu-host")))
rc, out, _ = runc("plan", "deploy", "--from-dir", LIVE)
check("deploy: the source and the destination being the same directory is NOT OK", rc == 1 and "same directory" in out)
BADSRC = os.path.join(TMP, "badtree")
shutil.rmtree(BADSRC, ignore_errors=True)
shutil.copytree(NEWSRC, BADSRC)
open(os.path.join(BADSRC, "gate", "gate.py"), "w").write("def broken(:\n")
rc, out, _ = runc("plan", "deploy", "--from-dir", BADSRC)
check("deploy: a changed Python file that does not compile is NOT OK, no steps", rc == 1 and "NOT OK syntax" in out and "gate/gate.py" in out and "\nSTEPS" not in out)
os.makedirs(os.path.join(TMP, "notree"), exist_ok=True)
rc, out, _ = runc("plan", "deploy", "--from-dir", os.path.join(TMP, "notree"))
check("deploy: a source without gate/gate.py is NOT OK", rc == 1 and "not a gpu-host tree" in out)
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")
check("deploy: --no-mcp-dispatch leaves the separate dispatcher alone (and says so)", "skipped (--no-mcp-dispatch)" in out and "CHANGES: 3 changed, 1 added" in out and MCP not in out)
# the git route: a throwaway repository, read-only git through Sys
GITREPO = os.path.join(TMP, "gitrepo")
shutil.rmtree(GITREPO, ignore_errors=True)
shutil.copytree(NEWSRC, os.path.join(GITREPO, "gpu-host"))
genv = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
genv.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "HOME": HOME_})
for g in (["init", "-q", "-b", "main"], ["add", "-A", "-f"], ["commit", "-q", "-m", "tree"]):
    subprocess.run(["git", "-C", GITREPO, *g], check=True, capture_output=True, env=genv)
os.symlink("/etc/passwd", os.path.join(GITREPO, "gpu-host", "evil_link"))
subprocess.run(["git", "-C", GITREPO, "add", "-A", "-f"], check=True, capture_output=True, env=genv)
subprocess.run(["git", "-C", GITREPO, "commit", "-q", "-m", "link"], check=True, capture_output=True, env=genv)
rc, out, _ = runc("plan", "deploy", "--from-ref", "main", env_extra={"UPKEEP_CHECKOUT": GITREPO})
cid_g = re.search(r"--confirm ([0-9a-f]{12})", out).group(1) if "--confirm" in out else ""
check("deploy: --from-ref resolves the ref to a commit and reads gpu-host/ of that commit (the symlink is not deployed; ignored files are not in the tree)",
      rc == 0 and re.search(r"ok     source: [0-9a-f]{12} \(main\)", out) and "CHANGES: 3 changed, 1 added" in out and "evil_link" not in out, out[:900])
rc, out, _ = runc("plan", "deploy", "--from-ref", "no-such-ref", env_extra={"UPKEEP_CHECKOUT": GITREPO})
check("deploy: an unknown ref is NOT OK", rc == 1 and "is not a commit of this checkout" in out)
for hostile in ("--upload-pack=x", "a..b", "x;reboot", "$(id)"):
    rr = run("plan", "deploy", "--from-ref", hostile, env_extra={"UPKEEP_STATE_DIR": ST2})
    if rr[0] != 2 or rr[1]:
        check("deploy: hostile ref " + hostile, False, rr)
        break
else:
    check("deploy: hostile refs (a leading dash, .., shell characters) are refused by the parser: exit 2, no stdout", True)
rc, out, _ = runc("plan", "deploy", "--from-ref", "main", "--apply", "--confirm", cid_g, env_extra={"UPKEEP_CHECKOUT": GITREPO})
check("deploy: --from-ref applies like --from-dir (md5 of gate.py equals the committed one, the log names the commit)", rc == 0 and md5map(LIVE)["gate/gate.py"] == gate_md5_src and "(main)" in out
      and any(e["step"] == "gate-deploy" and e["result"] == "ok" and re.search(r"[0-9a-f]{12} \(main\)", e.get("ref", "")) for e in U.read_log(ST2)), out[-500:])
CH_G = U.list_changes(ST2)[-1][0]
rc, out, _ = runc("undo", CH_G, "--apply")
check("undo of the git deploy restores the tree exactly", rc == 0 and md5map(LIVE) == orig and hashlib.md5(open(MCP, "rb").read()).hexdigest() == mcp_orig, out[-300:])
# a crafted archive: traversal, symlinks and special members never become files
import io, tarfile
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w") as tf:
    def add(name, data=b"x", typ=tarfile.REGTYPE, link=""):
        ti = tarfile.TarInfo(name); ti.size = len(data) if typ == tarfile.REGTYPE else 0; ti.type = typ; ti.linkname = link; ti.mode = 0o644
        tf.addfile(ti, io.BytesIO(data) if typ == tarfile.REGTYPE else None)
    add("gpu-host/ok.py"); add("gpu-host/../escape.py"); add("gpu-host//abs.py"); add("gpu-host/ln", typ=tarfile.SYMTYPE, link="/etc/passwd"); add("gpu-host/host.env"); add("other/x.py")
tree_x, probs_x = U.tree_from_archive(buf.getvalue())
check("deploy: a crafted archive yields only the safe regular files (traversal reported, symlink, host.env and other trees dropped)", sorted(tree_x) == ["ok.py"] and probs_x, (sorted(tree_x), probs_x))
check("Sys: git is read-only and this checkout only; Sys.cmd cannot restart anything; Sys.act accepts exactly the gate's user unit restart",
      not U.Sys().allowed(["git", "-c", "core.fsmonitor=false", "-C", "/tmp", "archive", "--format=tar", "0" * 40, "gpu-host"]) and not U.Sys().allowed([*U.Sys().git_prefix(), "push"])
      and not U.Sys().allowed([*U.Sys().git_prefix(), "archive", "--format=tar", "--remote=x", "gpu-host"]) and not U.Sys().allowed([*U.Sys().git_prefix(), "rev-parse", "--verify", "--quiet", "--x^{commit}"])
      and U.Sys().allowed([*U.Sys().git_prefix(), "archive", "--format=tar", "0" * 40, "gpu-host"]) and U.Sys().allowed([*U.Sys().git_prefix(), "rev-parse", "--verify", "--quiet", "main^{commit}"]))
bad_act = 0
for argv in (["systemctl", "--user", "stop", "bridgeai-gate.service"], ["systemctl", "restart", "bridgeai-gate.service"], ["systemctl", "--user", "restart", "other.service"],
             ["systemctl", "--user", "restart", "bridgeai-gate.service", "x"], ["sudo", "true"], ["apt", "install", "x"]):
    try:
        U.Sys().act(argv)
    except U.Refused:
        bad_act += 1
try:
    U.Sys().cmd(["systemctl", "--user", "restart", "bridgeai-gate.service"])
except U.Refused:
    bad_act += 1
check("Sys.act refuses everything but the restart of bridgeai-gate.service, and Sys.cmd refuses even that", bad_act == 7, bad_act)

# ================================================================================================================ unlock check
host_state()
GATE["services"] = {}
now_ = __import__("time").time()


def selfcheck_json(verdict="ok", driver=OLD, kernel=KERNELS[1], pkg="2.0.0", reasons=(), age=3600):
    json.dump({"verdict": verdict, "driver": driver, "reasons": list(reasons), "at": now_ - age, "ratio": 1.01,
               "fingerprint": {"kernel": kernel, "driver": driver, "unlock_pkg": pkg, "unlock_fw": "2.0.0"}}, open(os.path.join(GSTATE, "selfcheck.json"), "w"))


def dw_json(**kw):
    json.dump({"at": now_, "unlock_upstream": "none", **kw}, open(os.path.join(GSTATE, "driver_watch.json"), "w"))


selfcheck_json()
dw_json(unlock_upstream="stable_newer", unlock_upstream_detail={"stable_latest": "2.1.0"}, unlock_candidate="2.0.1")
rc, out, _ = runc("unlock")
SHOW["unlock (ok)"] = out
check("unlock: ok when the packages, the DKMS builds and a fresh selfcheck all agree; upstream and apt news are notes, never a verdict", rc == 0 and out.startswith("unlock: ok")
      and "ok    packages: gpu-unlock-dkms 2.0.0, gpu-unlock-firmware 2.0.0" in out and "ok    dkms:" in out and "ok    selfcheck: ok" in out and "newer stable gpu-unlock exists upstream (2.1.0" in out
      and "offers gpu-unlock-dkms 2.0.1" in out, out)
selfcheck_json("degraded", reasons=["fp32acc_slow"])
rc, out, _ = runc("unlock")
SHOW["unlock (degraded)"] = out
check("unlock: a degraded selfcheck is degraded (exit 1) and says why, in words", rc == 1 and out.startswith("unlock: degraded") and "FAIL  selfcheck: degraded (fp32acc_slow)" in out and "costs more energy" in out, out)
selfcheck_json("error", reasons=["no_reference"])
rc, out, _ = runc("unlock")
check("unlock: a selfcheck that could not judge is unknown (exit 2), not ok", rc == 2 and out.startswith("unlock: unknown") and "could not judge (no_reference)" in out, out)
selfcheck_json("ok", driver="580.1.1")
rc, out, _ = runc("unlock")
check("unlock: a result for another driver is stale: unknown, with the way to refresh it", rc == 2 and "but for another driver" in out and "unlock --run --apply" in out, out)
os.unlink(os.path.join(GSTATE, "selfcheck.json"))
rc, out, _ = runc("unlock")
check("unlock: no selfcheck result yet is unknown", rc == 2 and "no result yet" in out)
selfcheck_json()
host_state(dkms_missing={"gpu-unlock": KERNELS[0]})
rc, out, _ = runc("unlock")
check("unlock: a missing gpu-unlock DKMS build for a kernel with headers is degraded even when the selfcheck was ok", rc == 1 and "FAIL  dkms: missing: gpu-unlock for " + KERNELS[0] in out, out)
host_state()
write("dpkg.txt", open(os.path.join(FAKE, "dpkg.txt")).read().replace("ii |gpu-unlock-firmware|2.0.0\n", ""))
rc, out, _ = runc("unlock")
check("unlock: gpu-unlock-firmware missing is degraded", rc == 1 and "gpu-unlock-firmware MISSING" in out, out)
host_state()
write("dpkg.txt", "".join(l + "\n" for l in open(os.path.join(FAKE, "dpkg.txt")).read().splitlines() if "gpu-unlock" not in l))
rc, out, _ = runc("unlock")
check("unlock: no gpu-unlock-dkms at all is unknown (nothing to judge), not a crash", rc == 2 and "not installed here" in out)
host_state()
NEWK = "6.12.200+deb13-amd64"
rc, out, _ = runc("unlock", "--kernel", NEWK)
SHOW["unlock --kernel (new kernel not built yet)"] = out
check("unlock --kernel: a new kernel with no image, headers or DKMS builds is a FAIL that says DO NOT RESTART into it", rc == 1 and "FAIL  new kernel" in out and "DO NOT RESTART" in out, out)
write("dpkg.txt", open(os.path.join(FAKE, "dpkg.txt")).read() + f"ii |linux-image-{NEWK}|6.12.200-1\nii |linux-headers-{NEWK}|6.12.200-1\n")
write("dkms.txt", open(os.path.join(FAKE, "dkms.txt")).read() + f"nvidia/{OLD}, {NEWK}, x86_64: installed\n")
rc, out, _ = runc("unlock", "--kernel", NEWK)
check("unlock --kernel: image, headers and the nvidia build but NO gpu-unlock build is still a FAIL", rc == 1 and f"gpu-unlock for {NEWK}" in out and "no DKMS build of nvidia or gpu-unlock" in out, out)
write("dkms.txt", open(os.path.join(FAKE, "dkms.txt")).read() + f"gpu-unlock/2.0.0, {NEWK}, x86_64: installed\n")
rc, out, _ = runc("unlock", "--kernel", NEWK)
check("unlock --kernel: with both builds for the new kernel it says it may boot (ok)", rc == 0 and "ok    new kernel" in out and "it may boot" in out, out)
bad_k = run("unlock", "--kernel", "6.1; reboot", env_extra={"UPKEEP_STATE_DIR": ST2})
check("unlock --kernel: a hostile release is refused by the parser", bad_k[0] == 2 and not bad_k[1])
# --run: the busy switch is handled as in verify
host_state()
selfcheck_json()
open(os.path.join(GSTATE, "busy"), "w").close()
if os.path.exists(os.path.join(FAKE, "selfcheck_ran")):
    os.unlink(os.path.join(FAKE, "selfcheck_ran"))
rc, out, _ = runc("unlock", "--run", "--apply", sel_exit=0)
check("unlock --run --apply: the selfcheck runs with the busy switch lifted, an ok verdict leaves the gate open, and a log line is written",
      "busy_exists=False" in open(os.path.join(FAKE, "selfcheck_ran")).read() and not os.path.exists(os.path.join(GSTATE, "busy")) and "selfcheck exit 0" in out and "the gate is open again" in out
      and any(e["step"] == "unlock-check" for e in U.read_log(ST2)), out)
open(os.path.join(GSTATE, "busy"), "w").close()
rc, out, _ = runc("unlock", "--run", "--apply", sel_exit=1)
check("unlock --run --apply: a degraded selfcheck puts the busy switch back ON (never open on an unlocked-off card)", os.path.exists(os.path.join(GSTATE, "busy")) and "the gate stays CLOSED" in out, out)
os.unlink(os.path.join(GSTATE, "busy"))
rc, out, _ = runc("unlock", "--run")
check("unlock --run without --apply does not measure", "not run without --apply" in out)
# rebench: a bench line carries the setup it was measured on
rc, out, _ = runc("log", "--add", "bench", "--result", "done", "--ref", R_NEW, "--apply")
rc, out, _ = runc("unlock")
check("unlock: right after a recorded bench, a re-bench is not due (same driver, kernel and gpu-unlock)", "same driver, kernel and gpu-unlock as the bench of" in out, out)
host_state(updated=True)
selfcheck_json(driver=NEW)
rc, out, _ = runc("unlock")
check("unlock: after a driver change the log says a re-bench is DUE and names what changed", "rebench: DUE" in out and f"driver {OLD} -> {NEW}" in out, out)
host_state()

# ================================================================================================================ kernel update (print-only)
selfcheck_json()
rc, out, _ = runc("plan", "kernel", "--to", NEWK)
SHOW["plan kernel --to " + NEWK + " (print-only)"] = out
check("kernel: the plan is print-only and puts the gate (unlock --kernel NEW) BEFORE the restart, then unlock --run --apply, the re-bench and plan profile",
      rc == 0 and "(print-only)" in out and pos(out, "check-sim - --kernel --to " + NEWK, "sudo apt install --no-remove linux-image-amd64 linux-headers-amd64", "unlock --kernel " + NEWK, "sudo reboot", "unlock --run --apply", "bench_gate.py --recheck", "plan profile")
      and "ROLLBACK: no package change is needed" in out, out)
rc, out2, _ = runc("plan", "kernel")
check("kernel: with no --to and no single pending kernel it is NOT OK, no steps", rc == 1 and "NOT OK kernel" in out2 and "\nSTEPS" not in out2)
dw_json(pending_kernels=[NEWK])
rc, out2, _ = runc("plan", "kernel")
check("kernel: with exactly one pending kernel from driver_watch it takes that one", rc == 0 and f"{NEWK} (the one driver_watch sees pending)" in out2)
runc("plan", "kernel", "--to", NEWK, "--apply")
check("kernel: --apply only logs the plan (nothing else exists to apply)", any(e["step"] == "plan-kernel" for e in U.read_log(ST2)) and restarts() >= 0)
good_sim = f"Inst linux-image-{NEWK} (6.12.200-1 Debian [amd64])\nInst linux-headers-{NEWK} (6.12.200-1 Debian [amd64])\nInst linux-headers-6.12.200-common (6.12.200-1 Debian [all])\n"
rc, out3, _ = runc("check-sim", "-", "--kernel", "--to", NEWK, stdin=good_sim)
check("check-sim --kernel: image and headers together, nothing removed, is ok", rc == 0 and out3.startswith("check-sim: ok") and NEWK in out3, out3)
rc, out3, _ = runc("check-sim", "-", "--kernel", stdin=f"Inst linux-image-{NEWK} (6.12.200-1 Debian [amd64])\n")
check("check-sim --kernel: a kernel image without its headers is not ok (DKMS cannot build for it, grub boots it)", rc == 1 and "comes without its headers" in out3, out3)
rc, out3, _ = runc("check-sim", "-", "--kernel", stdin=good_sim + f"Remv linux-image-{KERNELS[1]} [6.12.115-1]\n")
check("check-sim --kernel: removing the running kernel is not ok", rc == 1 and "protected package" in out3, out3)
rc, out3, _ = runc("check-sim", "-", "--kernel", stdin=good_sim + "Remv vim [9.1]\n")
check("check-sim --kernel: any removal is not ok", rc == 1 and "a kernel update removes nothing" in out3, out3)
rc, out3, _ = runc("check-sim", "-", "--kernel", stdin="Reading package lists...\n")
check("check-sim --kernel: an empty simulation is not ok", rc == 1 and "no new kernel image" in out3)
rc, out3, _ = runc("check-sim", "-", "--to", NEWK, stdin=good_sim)
check("check-sim: a kernel release as --to without --kernel is refused (exit 2), never judged as a driver", rc == 2 and not out3)
os.unlink(os.path.join(GSTATE, "driver_watch.json"))
rc, hist, _ = runc("log", "--history", "-n", "100")
SHOW["log --history (the whole card history so far)"] = hist
check("log: --history lists every change of this section with before/after and a rollback command; the plain log lists them with their what",
      hist.count("rollback: python3 gpu-host/upkeep/upkeep.py") >= 4 and "gate-deploy" in hist and "profile-apply" in hist and "undo" in hist and "unlock-check" in hist and "before:" in hist and "after:" in hist, hist[-400:])
check("the card procedures never started a root command or a second systemctl form (the trap log is empty)", not os.path.exists(ROOTCALLS) or open(ROOTCALLS).read() == "", open(ROOTCALLS).read() if os.path.exists(ROOTCALLS) else "")

# ================================================================================================================ review round 4: symlinks, destinations, the verify marker, mid-copy failures
import errno, signal, time as _time, fcntl as _fcntl

CK = "review4: "
LINKT = os.path.join(TMP, "link-targets")
shutil.rmtree(LINKT, ignore_errors=True)
os.makedirs(LINKT)


def fresh_live():
    make_live()
    host_state()
    GATE["services"], GATE["blocked"], GATE["bench"], GATE["gpu"] = {}, None, None, dict(CARD)
    for f_ in ("healthz_down", "gate_forgets", "selfcheck_kill_parent", "selfcheck_sleep"):
        if os.path.exists(os.path.join(FAKE, f_)):
            os.unlink(os.path.join(FAKE, f_))
    write_results(RESULT_ROWS)


def cid_of(out):
    m = re.search(r"--confirm ([0-9a-f]{12})", out)
    return m.group(1) if m else ""


def alive(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


# ---- (1) a symlink in the deployed tree is never replaced or deleted
fresh_live()
n_before, r_before = len(U.list_changes(ST2)), restarts()
victim = os.path.join(LINKT, "gate_real.py")
shutil.copy(os.path.join(LIVE, "gate", "gate.py"), victim)
vict_md5 = hashlib.md5(open(victim, "rb").read()).hexdigest()
os.unlink(os.path.join(LIVE, "gate", "gate.py"))
os.symlink(victim, os.path.join(LIVE, "gate", "gate.py"))
rc, out, err = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")
check(CK + "a symlinked file in the destination is NOT OK before anything is written (no steps, no backup, no restart, the link and its target untouched)",
      rc == 1 and "NOT OK destination" in out and "gate/gate.py" in out and "symlink" in out and "\nSTEPS" not in out and os.path.islink(os.path.join(LIVE, "gate", "gate.py"))
      and hashlib.md5(open(victim, "rb").read()).hexdigest() == vict_md5 and len(U.list_changes(ST2)) == n_before and restarts() == r_before, out[:700])
rc, out, err = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--apply", "--confirm", "0" * 12)
check(CK + "--apply cannot get past it either", rc == 1 and os.path.islink(os.path.join(LIVE, "gate", "gate.py")) and len(U.list_changes(ST2)) == n_before)
fresh_live()
real_dir = os.path.join(LINKT, "resolve_dir")
shutil.copytree(os.path.join(LIVE, "resolve_mcp"), real_dir)
shutil.rmtree(os.path.join(LIVE, "resolve_mcp"))
os.symlink(real_dir, os.path.join(LIVE, "resolve_mcp"))
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")
check(CK + "a symlinked DIRECTORY in the destination is NOT OK too (its files would be written through the link)", rc == 1 and "NOT OK destination" in out and "resolve_mcp is a symlink" in out
      and open(os.path.join(real_dir, "wrapper.py")).read() == "print('old')\n", out[:600])
fresh_live()
os.symlink("/nonexistent-target", os.path.join(LIVE, "resolve_mcp", "extra.py"))
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")
check(CK + "a dangling symlink where a new file would go is NOT OK", rc == 1 and "NOT OK destination" in out and "resolve_mcp/extra.py" in out, out[:600])
fresh_live()
os.mkfifo(os.path.join(LIVE, "resolve_mcp", "extra.py"))
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")
check(CK + "a special file where a new file would go is NOT OK (it is not ours to replace)", rc == 1 and "not a regular file" in out, out[:600])
fresh_live()
os.symlink(victim, os.path.join(LIVE, "power_profiles.conf.link"))
os.unlink(os.path.join(LIVE, "power_profiles.conf"))
os.symlink(victim, os.path.join(LIVE, "power_profiles.conf"))
rc, out, _ = runc("plan", "profile")
check(CK + "a profile change refuses a symlinked power_profiles.conf (NOT OK, nothing written)", rc == 1 and "NOT OK destination" in out and "power_profiles.conf" in out and "symlink" in out and "DIFF" not in out, out[:600])
# undo never replaces or deletes a symlink that appeared after the change
fresh_live()
GATE["services"] = {}
cid_d = cid_of(runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")[1])
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--apply", "--confirm", cid_d)
ch_l = U.list_changes(ST2)[-1][0]
check(CK + "(setup) a deploy was applied", rc == 0 and "RESULT: ok" in out, out[-300:])
real_after = os.path.join(LINKT, "wrapper_after.py")
shutil.copy(os.path.join(LIVE, "resolve_mcp", "wrapper.py"), real_after)
os.unlink(os.path.join(LIVE, "resolve_mcp", "wrapper.py"))
os.symlink(real_after, os.path.join(LIVE, "resolve_mcp", "wrapper.py"))
after_md5 = hashlib.md5(open(real_after, "rb").read()).hexdigest()
rc, out, _ = runc("undo", ch_l, "--apply")
check(CK + "undo refuses while a file of the change is now a symlink (NOT UNDONE, the link and its target are still there, nothing was deleted)",
      rc == 1 and "symlink" in out and "NOT UNDONE" in out and os.path.islink(os.path.join(LIVE, "resolve_mcp", "wrapper.py")) and hashlib.md5(open(real_after, "rb").read()).hexdigest() == after_md5
      and os.path.exists(os.path.join(LIVE, "resolve_mcp", "extra.py")), out[-700:])
rc, out, _ = runc("undo", ch_l, "--apply", "--force")
check(CK + "undo --force restores every other file, skips the symlinked one (it stays a symlink, its target intact), and says FAILED rather than ok",
      rc == 1 and "skipped:" in out and os.path.islink(os.path.join(LIVE, "resolve_mcp", "wrapper.py")) and hashlib.md5(open(real_after, "rb").read()).hexdigest() == after_md5
      and not os.path.exists(os.path.join(LIVE, "resolve_mcp", "extra.py")) and "RESULT: failed" in out, out[-700:])
# the writer itself
wd = os.path.join(TMP, "aw")
os.makedirs(os.path.join(wd, "sub"))
real_tok = U.secrets.token_hex
U.secrets.token_hex = lambda n=4: "deadbeef"
planted = os.path.join(wd, f"f.txt.upkeep-tmp-{os.getpid()}-deadbeef")
os.symlink(victim, planted)
try:
    U.atomic_write(os.path.join(wd, "f.txt"), b"data", 0o644)
    planted_ok = False
except FileExistsError:
    planted_ok = True
U.secrets.token_hex = real_tok
check(CK + "atomic_write makes its temp file with O_EXCL (a planted link under the temp name is not written through; the target is untouched)",
      planted_ok and hashlib.md5(open(victim, "rb").read()).hexdigest() == vict_md5 and not os.path.exists(os.path.join(wd, "f.txt")))
os.unlink(planted)
os.symlink(victim, os.path.join(wd, "link.txt"))
os.symlink(wd, os.path.join(TMP, "aw-link"))
errs = []
for target, root in ((os.path.join(wd, "link.txt"), None), (os.path.join(TMP, "aw-link", "sub", "x.txt"), TMP)):
    try:
        U.atomic_write(target, b"x", 0o644, root)
        errs.append("no error")
    except OSError as e:
        errs.append(e.errno)
check(CK + "atomic_write refuses a symlink as the target, or a symlinked directory on the way (ELOOP), and leaves no temp file behind",
      errs == [errno.ELOOP, errno.ELOOP] and hashlib.md5(open(victim, "rb").read()).hexdigest() == vict_md5 and not [n for n in os.listdir(wd) if "upkeep-tmp" in n]
      and not [n for n in os.listdir(os.path.join(wd, "sub")) if "upkeep-tmp" in n], errs)
U.atomic_write(os.path.join(wd, "g.txt"), b"ok", 0o640)
check(CK + "atomic_write still writes a normal file, with the mode asked for", open(os.path.join(wd, "g.txt"), "rb").read() == b"ok" and mode(os.path.join(wd, "g.txt")) == 0o640)

# ---- (2) --mcp-dispatch: the one file name, a regular file or nothing, an existing directory
fresh_live()
other = os.path.join(LINKT, "rc_file")
open(other, "w").write("export X=1\n")
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--mcp-dispatch", other)
check(CK + "--mcp-dispatch with another file name is NOT OK and the file is not touched", rc == 1 and "NOT OK mcp_dispatch" in out and "must be mcp_dispatch.sh" in out and open(other).read() == "export X=1\n", out[:600])
os.makedirs(os.path.join(LINKT, "mcpd"), exist_ok=True)
os.symlink(other, os.path.join(LINKT, "mcpd", "mcp_dispatch.sh"))
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--mcp-dispatch", os.path.join(LINKT, "mcpd", "mcp_dispatch.sh"))
check(CK + "--mcp-dispatch naming a symlink is NOT OK (the real file or --no-mcp-dispatch is the way out)", rc == 1 and "it is a symlink" in out and "--no-mcp-dispatch" in out and open(other).read() == "export X=1\n", out[:600])
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--mcp-dispatch", os.path.join(LINKT, "no-such-dir", "mcp_dispatch.sh"))
check(CK + "--mcp-dispatch in a directory that does not exist is NOT OK", rc == 1 and "its directory does not exist" in out, out[:500])
os.makedirs(os.path.join(LINKT, "mcpdir", "mcp_dispatch.sh"))
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--mcp-dispatch", os.path.join(LINKT, "mcpdir", "mcp_dispatch.sh"))
check(CK + "--mcp-dispatch naming a directory is NOT OK", rc == 1 and "not a regular file" in out, out[:500])
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--mcp-dispatch", os.path.join(LINKT, "mcpd", "fresh", "mcp_dispatch.sh"))
check(CK + "--mcp-dispatch in a missing subdirectory is NOT OK, but an absent file in an existing directory is an 'added' copy",
      rc == 1 and "its directory does not exist" in out and "NOT OK" in out, out[:400])
os.makedirs(os.path.join(LINKT, "mcpe"))
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--mcp-dispatch", os.path.join(LINKT, "mcpe", "mcp_dispatch.sh"))
check(CK + "an absent mcp_dispatch.sh in an existing directory is accepted (added)", rc == 0 and "ok     mcp_dispatch" in out and "added" in out, out[:600])
os.rename(MCP, MCP + ".keep")
os.symlink(other, MCP)
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC)
os.unlink(MCP)
os.rename(MCP + ".keep", MCP)
check(CK + "the DEFAULT ~/bin/mcp_dispatch.sh being a symlink is NOT OK as well (it is common: the message names both ways out)", rc == 1 and "it is a symlink" in out and "--mcp-dispatch" in out and open(other).read() == "export X=1\n", out[:500])
check(CK + "undo only ever accepts the recorded file name for the mcp copy (manifest check)",
      U.manifest_problems({"schema": 1, "kind": "deploy", "dest": "/x", "mcp": "/tmp/rc_file", "files": [{"store": "mcp/mcp_dispatch.sh", "path": "/tmp/rc_file"}]}) != [])

# ---- (3) destinations: never a default inside the source checkout; dirty tree; profile changes a deploy would revert; what the gate really reads
fresh_live()
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", env_extra={"UPKEEP_GPU_DIR": ""})
check(CK + "deploy: with no --dest and no UPKEEP_GPU_DIR the default is this checkout's own gpu-host/: NOT OK, and it says to name --dest (standard install: checkout = deployed copy)",
      rc == 1 and "NOT OK destination" in out and "inside the source checkout" in out and "no --dest was given" in out and "SAME files" in out and "--dest " in out and "\nSTEPS" not in out, out[:900])
rc, out, _ = runc("plan", "profile", env_extra={"UPKEEP_GPU_DIR": ""})
check(CK + "profile: the same rule (it would edit git-tracked files of the checkout)", rc == 1 and "NOT OK destination" in out and "inside the source checkout" in out and "DIFF" not in out, out[:600])
GR = os.path.join(TMP, "gitrepo-dirty")
shutil.rmtree(GR, ignore_errors=True)
shutil.copytree(NEWSRC, os.path.join(GR, "gpu-host"))
for g in (["init", "-q", "-b", "main"], ["add", "-A", "-f"], ["commit", "-q", "-m", "tree"]):
    subprocess.run(["git", "-C", GR, *g], check=True, capture_output=True, env=genv)
SRC3 = os.path.join(TMP, "newtree3")
shutil.rmtree(SRC3, ignore_errors=True)
shutil.copytree(os.path.join(GR, "gpu-host"), SRC3)
open(os.path.join(SRC3, "resolve_mcp", "wrapper.py"), "w").write("print('from source 3')\n")
open(os.path.join(SRC3, "gate", "gate.py"), "a").write("\n# source 3\n")
open(os.path.join(GR, "gpu-host", "resolve_mcp", "wrapper.py"), "w").write("print('a hand edit, not committed')\n")
open(os.path.join(GR, "gpu-host", "untracked_note.py"), "w").write("x = 1\n")
GRD = os.path.join(GR, "gpu-host")
env3 = {"UPKEEP_CHECKOUT": GR, "UPKEEP_GPU_DIR": ""}
rc, out, _ = runc("plan", "deploy", "--from-dir", SRC3, "--no-mcp-dispatch", env_extra={"UPKEEP_CHECKOUT": GR, "UPKEEP_GPU_DIR": GRD})
check(CK + "deploy: UPKEEP_GPU_DIR inside the source checkout is a default too: NOT OK without --dest", rc == 1 and "NOT OK destination" in out and "no --dest was given" in out, out[:500])
rc, out, _ = runc("plan", "deploy", "--from-dir", SRC3, "--no-mcp-dispatch", "--dest", GRD, env_extra={"UPKEEP_CHECKOUT": GR})
SHOW["plan deploy into a dirty checkout (--dest given)"] = out
check(CK + "deploy: an explicit --dest inside the checkout works, notes that checkout and deployed copy are the same files, and WARNS about the dirty tree and the files it would revert",
      rc == 0 and "note   checkout" in out and "same files" in out and "warn   git: dirty git tree: 2 file(s)" in out and "would REVERT 1 of them" in out and "resolve_mcp/wrapper.py" in out, out[:1200])
check(CK + "deploy: the printed apply command carries --dest (the owner reads the target in the command)", f"--dest {GRD}" in out)
NOGIT = os.path.join(TMP, "nogit")
shutil.rmtree(NOGIT, ignore_errors=True)
shutil.copytree(NEWSRC, os.path.join(NOGIT, "gpu-host"))
rc, out, err = runc("plan", "deploy", "--from-dir", SRC3, "--no-mcp-dispatch", "--dest", os.path.join(NOGIT, "gpu-host"), env_extra={"UPKEEP_CHECKOUT": NOGIT})
check(CK + "deploy: when git cannot say whether the tree is dirty the plan says so (a note, no crash)", rc == 0 and "Traceback" not in out + err and "note   git: cannot tell whether the tree is dirty: git status did not answer" in out, out[:900])
check(CK + "Sys: `git status` is allowed in exactly one read-only form for this checkout; other status forms and other git commands are not",
      U.Sys().allowed([*U.Sys().git_prefix(), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "gpu-host"])
      and not U.Sys().allowed([*U.Sys().git_prefix(), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "/etc"])
      and not U.Sys().allowed(["git", "-c", "core.fsmonitor=false", "-C", "/tmp", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "gpu-host"])
      and not U.Sys().allowed([*U.Sys().git_prefix(), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "gpu-host", "--output=/tmp/x"])
      and not U.Sys().allowed([*U.Sys().git_prefix(), "clean", "-fdx"]) and not U.Sys().allowed([*U.Sys().git_prefix(), "checkout", "--", "gpu-host"]))
# a profile change a later deploy would overwrite
fresh_live()
rc, out, _ = runc("plan", "profile")
cid_p = cid_of(out)
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_p)
check(CK + "(setup) a profile change was applied", rc == 0 and "RESULT: ok" in out, out[-300:])
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")
SHOW["plan deploy after a profile change"] = out
check(CK + "deploy: warns that it overwrites values a profile change wrote (named by change id, from the manifests) and says to run plan profile again",
      rc == 0 and "warn   profile: power_profiles.conf holds values written by profile change" in out and "warn   profile: gate/gate.py holds values" in out and "plan profile` again" in out, out[:1500])
ch_pr = [i for i, m in U.list_changes(ST2) if m and m["kind"] == "profile"][-1]
rc, _o, _ = runc("undo", ch_pr, "--apply")
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")
check(CK + "deploy: once the profile change is undone there is no such warning", "holds values written by profile change" not in out)
# what the gate really reads
fresh_live()
UNITDIR = os.path.join(HOME_, ".config", "systemd", "user")
UNIT = os.path.join(UNITDIR, "bridgeai-gate.service")
os.makedirs(UNITDIR, exist_ok=True)
elsewhere = os.path.join(TMP, "other-profiles.conf")
shutil.copy(os.path.join(LIVE, "power_profiles.conf"), elsewhere)
rc, out, _ = runc("plan", "profile", env_extra={"GATE_POWER_PROFILES": elsewhere})
check(CK + "profile: GATE_POWER_PROFILES pointing at another file is NOT OK (this tool will not edit a file the gate does not read), nothing proposed", rc == 1 and "NOT OK gate" in out
      and "does not read" in out and elsewhere in out and "DIFF" not in out, out[:700])
open(UNIT, "w").write(f"[Service]\nExecStart=/usr/bin/env python3 -I {os.path.join(TMP, 'another-tree')}/gate/gate.py\nWorkingDirectory=/x\n")
rc, out, _ = runc("plan", "profile")
check(CK + "profile: a gate unit that runs gate.py from another tree is NOT OK (named), the deploy only warns", rc == 1 and "NOT OK gate" in out and "another-tree" in out and "DIFF" not in out, out[:600])
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")
check(CK + "deploy: the same mismatch is a warning (this deploy would not change what the gate runs)", rc == 0 and "warn   gate" in out and "another-tree" in out, out[:700])
open(UNIT, "w").write(f"[Service]\nExecStart=/usr/bin/env python3 -I {LIVE}/gate/gate.py\nEnvironment=GATE_POWER_PROFILES={elsewhere}\n")
rc, out, _ = runc("plan", "profile")
check(CK + "profile: GATE_POWER_PROFILES in the unit's Environment is honoured (NOT OK, the other file is named)", rc == 1 and "NOT OK gate" in out and elsewhere in out, out[:600])
envf = os.path.join(TMP, "unit.env")
open(envf, "w").write(f"GATE_POWER_PROFILES={elsewhere}\n")
open(UNIT, "w").write(f"[Service]\nExecStart=/usr/bin/env python3 -I {LIVE}/gate/gate.py\nEnvironmentFile=-{envf}\n")
rc, out, _ = runc("plan", "profile")
check(CK + "profile: ... and so is an EnvironmentFile of the unit", rc == 1 and "NOT OK gate" in out and elsewhere in out, out[:600])
SRC5 = os.path.join(TMP, "newtree5")
shutil.rmtree(SRC5, ignore_errors=True)
shutil.copytree(NEWSRC, SRC5)
open(os.path.join(SRC5, "gate.settings"), "w").write("GATE_TOKEN=fake-from-the-source\n")
open(os.path.join(LIVE, "gate.settings"), "w").write("GATE_PORT=1\n")
open(UNIT, "w").write(f"[Service]\nExecStart=/usr/bin/env python3 -I {LIVE}/gate/gate.py\nEnvironment=GATE_ENV_FILE={LIVE}/gate.settings\n")
rc, out, _ = runc("plan", "deploy", "--from-dir", SRC5, "--no-mcp-dispatch")
check(CK + "deploy: a gate env file (GATE_ENV_FILE of the unit) inside the tree that the source also holds is a NOT OK: it would overwrite the host's settings",
      rc == 1 and "NOT OK gate env" in out and "gate.settings" in out and open(os.path.join(LIVE, "gate.settings")).read() == "GATE_PORT=1\n", out[:700])
os.unlink(os.path.join(LIVE, "gate.settings"))
open(UNIT, "w").write(f"[Service]\nExecStart=/usr/bin/env python3 -I {LIVE}/gate/gate.py\n")
rc, out, _ = runc("plan", "profile")
check(CK + "profile: a unit that runs this tree and reads this tree's power_profiles.conf is ok (and the plan says what the gate reads)", rc == 0 and "ok     gate: the gate (unit bridgeai-gate.service) reads" in out and "DIFF" in out, out[:700])
os.unlink(UNIT)
rc, out, _ = runc("plan", "profile")
check(CK + "profile: with no unit file for this account the plan says the restart only works as the gate's own user", rc == 0 and "no gate unit file" in out and "as the gate's own user" in out, out[:600])

# ---- (4) the verify marker: a killed verify never leaves the gate open
fresh_live()
host_state(updated=True)
SNAP4 = os.path.join(TMP, "state-v4")


def v4(*args, **kw):
    kw["env_extra"] = {"UPKEEP_STATE_DIR": SNAP4, **(kw.get("env_extra") or {})}
    return run(*args, **kw)


def busy_on():
    open(os.path.join(GSTATE, "busy"), "w").close()


def busy_is_on():
    return os.path.exists(os.path.join(GSTATE, "busy"))


MK = os.path.join(SNAP4, "verify-in-progress.json")
busy_on()
write("selfcheck_kill_parent", "")
rc, out, err = v4("verify", "--to", NEW, "--apply", sel_exit=0)
os.unlink(os.path.join(FAKE, "selfcheck_kill_parent"))
mk = json.load(open(MK)) if os.path.exists(MK) else {}
child = int(open(os.path.join(FAKE, "selfcheck_child_pid")).read())
check(CK + "SIGKILL of verify during the selfcheck: the process is gone (rc -9), the marker is left behind with the pid, the step and the selfcheck's own pid, and the switch is still lifted (what a kill does)",
      rc == -9 and mk.get("step") == "verify" and mk.get("pid") and mk.get("child") == child and not busy_is_on(), (rc, mk, busy_is_on()))
rc, out, err = v4("busy", "status")
check(CK + "the NEXT upkeep call (busy status) closes the gate again, stops the orphaned selfcheck, removes the marker, says RECOVERED on stderr, and logs it",
      rc == 0 and out.strip() == "busy: on" and busy_is_on() and not os.path.exists(MK) and "RECOVERED" in err and "orphaned selfcheck was stopped" in err and not alive(child)
      and any(e["step"] == "verify-recovered" and e["result"] == "closed" for e in U.read_log(SNAP4)), (rc, out, err, alive(child)))
os.unlink(os.path.join(GSTATE, "busy"))
rc, out, err = v4("busy", "status")
check(CK + "after the recovery there is nothing left to recover (the marker is gone, a later call is quiet)", "RECOVERED" not in err and "busy: off" in out)
for cmd_ in (("idle",), ("plan", "driver", "--to", NEW), ("verify", "--to", NEW, "--installed")):
    busy_on()
    write("selfcheck_kill_parent", "")
    v4("verify", "--to", NEW, "--apply", sel_exit=0)
    os.unlink(os.path.join(FAKE, "selfcheck_kill_parent"))
    os.unlink(os.path.join(GSTATE, "busy")) if busy_is_on() else None
    left = os.path.exists(MK)
    rc, out, err = v4(*cmd_)
    check(CK + f"the marker is also acted on by `{cmd_[0]}` (not only busy status)", left and "RECOVERED" in err and busy_is_on() and not os.path.exists(MK), (left, err))
    os.unlink(os.path.join(GSTATE, "busy"))
# unlock --run --apply the same
busy_on()
write("selfcheck_kill_parent", "")
selfcheck_json()
rc, out, err = v4("unlock", "--run", "--apply", sel_exit=0)
os.unlink(os.path.join(FAKE, "selfcheck_kill_parent"))
mk = json.load(open(MK)) if os.path.exists(MK) else {}
rc2, out2, err2 = v4("busy", "status")
check(CK + "unlock --run --apply writes the marker too (step unlock) and is recovered the same way", rc == -9 and mk.get("step") == "unlock" and "RECOVERED" in err2 and busy_is_on(), (rc, mk, err2))
os.unlink(os.path.join(GSTATE, "busy"))
# a live writer, a dead one, a corrupt marker, an old one
os.makedirs(SNAP4, exist_ok=True)
json.dump({"at": int(_time.time()), "pid": os.getpid(), "step": "verify", "child": None, "script": None}, open(MK, "w"))
rc, out, err = v4("busy", "status")
check(CK + "a marker whose writer is still running is left alone (another verify is in progress)", "RECOVERED" not in err and os.path.exists(MK) and not busy_is_on())
json.dump({"at": int(_time.time()) - 5000, "pid": os.getpid(), "step": "verify"}, open(MK, "w"))
rc, out, err = v4("busy", "status")
check(CK + "a marker older than any selfcheck can last is stale even if its pid exists (pid reuse)", "RECOVERED" in err and busy_is_on() and not os.path.exists(MK), err)
os.unlink(os.path.join(GSTATE, "busy"))
open(MK, "w").write("not json{")
rc, out, err = v4("busy", "status")
check(CK + "a corrupt marker is treated as stale (the gate is closed), never a crash", rc == 0 and "RECOVERED" in err and busy_is_on() and "Traceback" not in err, err)
os.unlink(os.path.join(GSTATE, "busy"))
json.dump({"at": int(_time.time()), "pid": 4194999, "step": "verify; reboot"}, open(MK, "w"))
rc, out, err = v4("busy", "status")
check(CK + "a marker whose pid is gone is stale; a hostile step text in it is not echoed into the log or the output", "RECOVERED" in err and "reboot" not in err and all("reboot" not in json.dumps(e) for e in U.read_log(SNAP4)), err)
os.unlink(os.path.join(GSTATE, "busy"))
# the hard timeout, below hostcare's 300 s
check(CK + "the selfcheck timeout is below hostcare's 300 s, can only be lowered by the environment (never past 280 s), and a bad value falls back",
      U.selfcheck_timeout({}) < 300 and U.selfcheck_timeout({"UPKEEP_SELFCHECK_TIMEOUT_S": "9999"}) == 280 and U.selfcheck_timeout({"UPKEEP_SELFCHECK_TIMEOUT_S": "10"}) == 10
      and U.selfcheck_timeout({"UPKEEP_SELFCHECK_TIMEOUT_S": "nan"}) == U.SELFCHECK_TIMEOUT_S and U.selfcheck_timeout({"UPKEEP_SELFCHECK_TIMEOUT_S": "x"}) == U.SELFCHECK_TIMEOUT_S
      and U.selfcheck_timeout({"UPKEEP_SELFCHECK_TIMEOUT_S": "0.1"}) == 5, None)
busy_on()
write("selfcheck_sleep", "60")
t0 = _time.time()
rc, out, err = v4("verify", "--to", NEW, "--apply", env_extra={"UPKEEP_SELFCHECK_TIMEOUT_S": "5"}, sel_exit=0)
took = _time.time() - t0
child = int(open(os.path.join(FAKE, "selfcheck_child_pid")).read())
os.unlink(os.path.join(FAKE, "selfcheck_sleep"))
check(CK + "a selfcheck that does not finish is stopped for good at the limit: RESULT incomplete (exit 2), the gate is CLOSED again, no marker, the selfcheck process is gone, well inside hostcare's window",
      rc == 2 and "did not finish within 5 s" in out and "RESULT: incomplete" in out and busy_is_on() and not os.path.exists(MK) and not alive(child) and took < 30, (rc, out[-400:], took))
os.unlink(os.path.join(GSTATE, "busy"))
# SIGTERM: the finally runs
busy_on()
write("selfcheck_sleep", "60")
penv = {**os.environ, "PATH": BIN + os.pathsep + os.environ["PATH"], "HOME": HOME_, "FAKE": FAKE, "ROOTCALLS": ROOTCALLS, "GATE_ENV_FILE": ENVF, "GATE_STATE_DIR": GSTATE,
        "UPKEEP_STATE_DIR": SNAP4, "UPKEEP_BOOT_DIR": BOOT, "RESTARTS": RESTARTS, "UPKEEP_SELFCHECK": SELFCHECK, "UPKEEP_TEST": TESTMARK, "TMPDIR": TMP,
        "XDG_CONFIG_HOME": os.path.join(HOME_, ".config")}
penv.pop("GATE_TOKEN", None)
if os.path.exists(os.path.join(FAKE, "selfcheck_child_pid")):
    os.unlink(os.path.join(FAKE, "selfcheck_child_pid"))
pp = subprocess.Popen([sys.executable, "-I", UPKEEP, "verify", "--to", NEW, "--apply"], env=penv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
for _i in range(100):
    if os.path.exists(os.path.join(FAKE, "selfcheck_child_pid")) and os.path.exists(MK):
        break
    _time.sleep(0.1)
child = int(open(os.path.join(FAKE, "selfcheck_child_pid")).read())
lifted = not busy_is_on()
pp.send_signal(signal.SIGTERM)
pp.communicate(timeout=30)
os.unlink(os.path.join(FAKE, "selfcheck_sleep"))
_time.sleep(0.3)
check(CK + "SIGTERM during the selfcheck (hostcare's gentler stop) runs the finally: the gate is CLOSED again, the marker removed and the selfcheck stopped",
      lifted and busy_is_on() and not os.path.exists(MK) and not alive(child), (lifted, busy_is_on(), os.path.exists(MK), alive(child)))
os.unlink(os.path.join(GSTATE, "busy"))

# ---- (5) a failure in the middle of a copy: everything goes back, logged as failed; no traceback
if os.geteuid() != 0:
    fresh_live()
    GATE["services"] = {}
    cid_d = cid_of(runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")[1])
    o0 = md5map(LIVE)
    r0, n0 = restarts(), len(U.list_changes(ST2))
    os.chmod(os.path.join(LIVE, "resolve_mcp"), 0o555)
    try:
        rc, out, err = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--apply", "--confirm", cid_d)
    finally:
        os.chmod(os.path.join(LIVE, "resolve_mcp"), 0o755)
    check(CK + "deploy: a write error in the middle (a read-only directory) restores every file, says FAILED, logs failed, never restarts the gate, and does not crash",
          rc == 1 and "FAILED: the copy stopped midway" in out and "Traceback" not in out + err and md5map(LIVE) == o0 and restarts() == r0
          and any(e["step"] == "gate-deploy" and e["result"] == "failed" for e in U.read_log(ST2)) and len(U.list_changes(ST2)) == n0 + 1, (out[-600:], err[-300:]))
    fresh_live()
    cid_p = cid_of(runc("plan", "profile")[1])
    o0 = md5map(LIVE)
    r0 = restarts()
    os.chmod(os.path.join(LIVE, "gate"), 0o555)
    try:
        rc, out, err = runc("plan", "profile", "--apply", "--confirm", cid_p)
    finally:
        os.chmod(os.path.join(LIVE, "gate"), 0o755)
    check(CK + "profile: a write error on the second file puts the first one back (both files as before), no crash, no restart, logged as failed",
          rc == 1 and "FAILED: the write stopped" in out and "Traceback" not in out + err and md5map(LIVE) == o0 and restarts() == r0
          and any(e["step"] == "profile-apply" and e["result"] == "failed" for e in U.read_log(ST2)), (out[-500:], err[-300:]))
else:
    check(CK + "(skipped as root: a read-only directory does not stop root)", True)

# ---- (5) values: finite whole numbers in range; odd existing lines; a VRAM need that falls a lot
check(CK + "int_in: NaN, Infinity, a bool, a string, a fraction and an out-of-range number are None; a whole float is an int",
      [U.int_in(x, 1, 100) for x in (float("nan"), float("inf"), float("-inf"), True, "5", 5.5, 500, 0)] == [None] * 8 and U.int_in(5.0, 1, 100) == 5 and U.int_in(7, 1, 100) == 7)
fresh_live()
rows_nan = [dict(r) for r in RESULT_ROWS]
rows_nan = [r for r in rows_nan if not (r.get("kind") == "recommend" and r.get("task") in ("stt", "tts-hq"))]
os.makedirs(os.path.join(HOME_, "bench_gate"), exist_ok=True)
with open(os.path.join(HOME_, "bench_gate", "results.jsonl"), "w") as f:
    for r in rows_nan:
        f.write(json.dumps(r) + "\n")
    f.write('{"kind": "recommend", "run": "%s", "task": "stt", "cap_w": NaN, "need_mb": Infinity}\n' % R_NEW)
    f.write('{"kind": "recommend", "run": "%s", "task": "tts-hq", "cap_w": Infinity, "need_mb": -Infinity}\n' % R_NEW)
    f.write('{"kind": "recommend", "run": "%s", "task": "llm", "cap_w": 125.5, "need_mb": 0}\n' % R_NEW)
GATE["gpu"] = {"name": CARD["name"], "min_w": float("nan"), "max_w": float("inf"), "limit_w": 130}
rc, out, err = runc("plan", "profile")
check(CK + "profile: NaN and Infinity in the results (json.loads takes them) and in the gate's card range give notes, never a traceback",
      "Traceback" not in out + err and rc in (0, 1) and "stt: cap nan W is outside" in out and "tts-hq: cap inf W is outside" in out and "VRAM need" in out, (rc, out[:900], err[-300:]))
GATE["gpu"] = dict(CARD)
write_results(RESULT_ROWS)
# an existing key that does not look like `key = number`
for bad_line in ("llm = fast", "llm = 130 W", "llm : fast"):
    fresh_live()
    txt = open(os.path.join(LIVE, "power_profiles.conf")).read()
    open(os.path.join(LIVE, "power_profiles.conf"), "w").write(txt.replace("llm = 130", bad_line, 1))
    rc, out, err = runc("plan", "profile")
    check(CK + f"profile: an existing line `{bad_line}` is a NOT OK at the dry run (not a FAILED after the owner said yes)",
          rc == 1 and "NOT OK edit" in out and "not as a plain number" in out and "DIFF" not in out and "Traceback" not in out + err, out[:700])
nt, ch_, pr_ = U.edit_conf("[A]\nllm = fast\n", "A", {"llm": 100})
check(CK + "edit_conf (unit): the odd line is reported as a problem", pr_ and "not as a plain number" in pr_[0] and nt == "[A]\nllm = fast\n" + "" or bool(pr_), pr_)
# VRAM need: a big fall needs the owner's word; a tiny or zero need is not a proposal
fresh_live()
rows_low = [r for r in RESULT_ROWS if not (r.get("kind") == "recommend" and r.get("task") in ("stt", "tts-hq"))]
rows_low += [rec(R_NEW, "stt", 110, 800), rec(R_NEW, "tts-hq", 130, 10)]
write_results(rows_low)
rc, out, _ = runc("plan", "profile")
check(CK + "profile: a VRAM need that falls by more than 25% (stt 1540 -> 800) is NOT OK, no diff; a need under 64 MB is skipped with a note",
      rc == 1 and "NOT OK need" in out and "stt: the VRAM need would fall from 1540 to 800" in out and "--allow-lower-need" in out and "DIFF" not in out and "tts-hq: VRAM need 10 MB is not a whole number between 64" in out, out[:900])
rc, out, _ = runc("plan", "profile", "--allow-lower-need")
check(CK + "profile: --allow-lower-need turns it into a note and the printed apply command carries the flag", rc == 0 and "note   need" in out and "Accepted with --allow-lower-need" in out and "DIFF" in out
      and "--allow-lower-need --apply --confirm" in out.replace("  ", " ") or ("--allow-lower-need" in out and "--confirm" in out), out[:900])
write_results(RESULT_ROWS)
# undo whose backup is gone: --force does not help and the message says so
fresh_live()
cid_p = cid_of(runc("plan", "profile")[1])
runc("plan", "profile", "--apply", "--confirm", cid_p)
ch_m = [i for i, m in U.list_changes(ST2) if m and m["kind"] == "profile"][-1]
os.unlink(os.path.join(ST2, "backups", ch_m, "tree", "gate", "gate.py"))
rc, out, _ = runc("undo", ch_m, "--apply", "--force")
check(CK + "undo with a missing backup says --force does not help (it used to suggest --force), and changes nothing",
      rc == 1 and "NOT UNDONE" in out and "--force does not help" in out and "add --force only if" not in out, out[-500:])

# ---- (6) other installs in a simulation are judged
extra_k = "Inst linux-image-6.12.117+deb13-amd64 (6.12.117-1 Debian [amd64])\nInst linux-headers-6.12.117+deb13-amd64 (6.12.117-1 Debian [amd64])\n"
host_state()
rc, out, _ = runc("check-sim", "-", "--to", NEW, stdin=two + extra_k)
check(CK + "check-sim: a driver update that also installs a new kernel is not ok (DKMS and /boot risk), and points to `plan kernel`", rc == 1 and "also installs or upgrades 2 kernel package(s)" in out and "plan kernel" in out, out)
rc, out, _ = runc("check-sim", "-", "--to", NEW, stdin=two + "Inst openssh-client (1:9.2p1-2 Debian [amd64])\n")
check(CK + "check-sim: another non-driver install is a note (listed), not a silent ok", rc == 0 and "also installs or upgrades 1 other package(s)" in out and "openssh-client" in out, out)
host_state()
rc, out, _ = runc("check-sim", "-", "--kernel", "--to", NEWK, stdin=good_sim + "Inst nvidia-open [595.71.05-1] (595.112.07-1 Debian [amd64])\n")
check(CK + "check-sim --kernel: a kernel update that also upgrades nvidia-open is not ok (the driver has its own procedure)", rc == 1 and "also installs or upgrades 1 driver or gpu-unlock package(s)" in out and "plan driver" in out, out)
rc, out, _ = runc("check-sim", "-", "--kernel", "--to", NEWK, stdin=good_sim + "Inst gpu-unlock-dkms [2.0.0] (2.0.1 Debian [all])\n")
check(CK + "check-sim --kernel: a gpu-unlock upgrade inside a kernel update is not ok either", rc == 1 and "driver or gpu-unlock package" in out, out)
rc, out, _ = runc("check-sim", "-", "--kernel", "--to", NEWK, stdin=good_sim + "Inst openssh-client (1:9.2p1-2 Debian [amd64])\n")
check(CK + "check-sim --kernel: another non-kernel install is a note", rc == 0 and "also installs or upgrades 1 other package(s) that are not kernel packages" in out, out)
rc, out, _ = runc("plan", "kernel", "--to", NEWK)
check(CK + "plan kernel: both the simulation and the install line carry --no-remove", "apt install -s --no-remove linux-image-amd64" in out and "sudo apt install --no-remove linux-image-amd64" in out, out[-1500:])

# ---- (7) unlock judges a newest kernel without headers like verify does
host_state()
selfcheck_json()
open(os.path.join(BOOT, "vmlinuz-6.12.300+deb13-amd64"), "w").close()
rc, out, _ = runc("unlock")
os.unlink(os.path.join(BOOT, "vmlinuz-6.12.300+deb13-amd64"))
check(CK + "unlock: the newest kernel in /boot with no headers is degraded (FAIL kernels) even with a fresh ok selfcheck", rc == 1 and out.startswith("unlock: degraded") and "FAIL  kernels" in out and "6.12.300+deb13-amd64 has no headers" in out, out[:700])
rc, out, _ = runc("unlock")
check(CK + "unlock: without that kernel it is ok again", rc == 0 and out.startswith("unlock: ok"), out[:300])

# ---- (8) the rest
with open(os.path.join(ST2, "audit.jsonl"), "a") as f:
    f.write('[1, 2]\n5\n"text"\nnull\n{"step": "x", "result": "ok"}\n')
codes = []
for args_ in (("log",), ("log", "--history"), ("log", "--json"), ("unlock",), ("plan", "kernel", "--to", NEWK)):
    rc, out, err = runc(*args_)
    codes.append((args_, rc, "Traceback" in out + err))
check(CK + "an audit.jsonl line that is not a JSON object (a list, a number, a string, null) crashes nothing (log, log --history, unlock, plan)", all(not tb for _a, _rc, tb in codes), codes)
# a degraded restart is not ok
fresh_live()
GATE["services"] = {"stt": {"port": 8620, "running": True, "leases": 0}}
cid_p = cid_of(runc("plan", "profile", "--restart-while-running")[1])
write("gate_forgets", str(restarts() + 1))
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_p, "--restart-while-running")
os.unlink(os.path.join(FAKE, "gate_forgets"))
check(CK + "profile: a restart that ends degraded (a service that ran is not listed again) is exit 1 with RESULT: degraded, as the skill says", rc == 1 and "RESULT: degraded" in out, out[-500:])
fresh_live()
GATE["services"] = {"stt": {"port": 8620, "running": True, "leases": 0}}
cid_d = cid_of(runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--restart-while-running")[1])
write("gate_forgets", str(restarts() + 1))
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--apply", "--confirm", cid_d, "--restart-while-running")
os.unlink(os.path.join(FAKE, "gate_forgets"))
check(CK + "deploy: the same, exit 1 with RESULT: degraded", rc == 1 and "RESULT: degraded" in out, out[-500:])
GATE["services"] = {}
# a profile change whose gate does not come back is rolled back like a deploy
fresh_live()
cid_p = cid_of(runc("plan", "profile")[1])
o0 = md5map(LIVE)
open(os.path.join(FAKE, "healthz_down"), "w").close()
r0 = restarts()
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_p)
os.unlink(os.path.join(FAKE, "healthz_down"))
check(CK + "profile: a gate that does not answer after the restart is rolled back at once (both files as before, a second restart, logged rolled-back)",
      rc == 1 and "ROLLED BACK" in out and md5map(LIVE) == o0 and restarts() == r0 + 2 and any(e["step"] == "profile-apply" and e["result"] == "rolled-back" for e in U.read_log(ST2)), out[-600:])
# one change at a time
fresh_live()
cid_p = cid_of(runc("plan", "profile")[1])
o0 = md5map(LIVE)
os.makedirs(ST2, exist_ok=True)
lk = os.open(os.path.join(ST2, "apply.lock"), os.O_RDWR | os.O_CREAT, 0o600)
_fcntl.flock(lk, _fcntl.LOCK_EX)
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_p)
rc2, out2, err2 = runc("undo", [i for i, m in U.list_changes(ST2) if m][-1], "--apply")
rc3, out3, _ = runc("plan", "profile")
_fcntl.flock(lk, _fcntl.LOCK_UN)
os.close(lk)
check(CK + "two applies at once: while another change holds the lock, profile --apply and undo --apply refuse, nothing changes; the dry run is not blocked",
      rc == 1 and "another upkeep change is running" in out and md5map(LIVE) == o0 and rc2 == 1 and "another upkeep change is running" in err2 and rc3 == 0 and "DIFF" in out3, (out, err2))
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_p)
check(CK + "... and the same apply goes through once the lock is free", rc == 0 and "RESULT: ok" in out, out[-300:])
# old backups are pruned
n_now = len(U.list_changes(ST2))
fresh_live()
cid_p = cid_of(runc("plan", "profile")[1])
rc, out, _ = runc("plan", "profile", "--apply", "--confirm", cid_p, env_extra={"UPKEEP_KEEP_BACKUPS": "3"})
left = U.list_changes(ST2)
newest = [i for i, _m in left]
check(CK + "backups: only the newest UPKEEP_KEEP_BACKUPS (3) remain after a change, the new one among them, the removal is logged and printed",
      n_now > 3 and len(left) == 3 and "pruned" in out and sorted(newest) == newest and any(e["step"] == "backups-pruned" for e in U.read_log(ST2))
      and len(os.listdir(os.path.join(ST2, "backups"))) == 3, (n_now, len(left), out[-300:]))
# environment overrides are visible
rc, out, _ = runc("check-sim", "-", "--to", NEW, stdin=two, env_extra={"UPKEEP_ALLOW_REMOVE": "^vim$"})
check(CK + "check-sim: an UPKEEP_ALLOW_REMOVE in the environment is printed as an OVERRIDE (the bot cannot prefix it unseen)", "OVERRIDE in effect: UPKEEP_ALLOW_REMOVE is set" in out, out)
rc, out, _ = runc("check-sim", "-", "--to", NEW, "--apply", stdin=two, env_extra={"UPKEEP_PROTECT": "^foo$"})
check(CK + "check-sim --apply logs the override in the audit line", any(e["step"] == "check-sim" and "UPKEEP_PROTECT" in (e.get("note") or "") for e in U.read_log(ST2)))
fresh_live()
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", env_extra={"UPKEEP_PROTECT": "^foo$"})
check(CK + "deploy and profile plans print the overrides in their preflight too", "note   override: OVERRIDE: UPKEEP_PROTECT is set" in out, out[:500])
check(CK + "the new docs say what changed: marker and hard timeout, no default destination in the checkout, symlinks, the lock and pruning, standard install = same files",
      all(x in open(os.path.join(HERE, "UPKEEP.md")).read() for x in ("verify-in-progress", "never a default destination inside", "never replaces or deletes a symlink", "apply.lock", "UPKEEP_KEEP_BACKUPS", "the SAME files",
                                                                   "hard stop of 240 s", "RECOVERED")), None)
SK4 = open(os.path.join(HERE, "..", "..", "aibridge", "SKILL_host_upkeep.md")).read()
check(CK + "the skill no longer claims the switch always goes back on a kill: it names the marker, RECOVERED, --dest and the symlink rule",
      "does not hold on a" in SK4 and "SIGKILL" in SK4 and "RECOVERED" in SK4 and "--dest DIR" in SK4 and "never replaces a symlink" in SK4 and "is put back to closed by the tool whenever a verify does not end in ok" not in SK4, None)
shutil.rmtree(GR, ignore_errors=True)


# ================================================================================================================ review round 5: marker trust, rollback truth, special files, overrides, git, the rest
R5 = "review5: "
import tempfile as _tempfile


def spawn_sleeper(new_session, extra_env=None):
    """The fake selfcheck started the way the tool starts it (own session) or not; its pid is written by the script to FAKE/selfcheck_child_pid."""
    write("selfcheck_sleep", "60")
    write("selfcheck_exit", "0")
    env = {**os.environ, "FAKE": FAKE, "GATE_STATE_DIR": GSTATE, **(extra_env or {})}
    pr = subprocess.Popen([sys.executable, "-I", SELFCHECK, "run", "--force"], env=env, start_new_session=new_session, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if os.path.exists(os.path.join(FAKE, "selfcheck_child_pid")) and int(open(os.path.join(FAKE, "selfcheck_child_pid")).read() or 0) == pr.pid:
            break
        _time.sleep(0.05)
    os.unlink(os.path.join(FAKE, "selfcheck_sleep"))
    return pr


def stop(pr):
    try:
        os.killpg(pr.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        pr.kill()
    except OSError:
        pass
    pr.wait()


fresh_live()
SNAP5 = os.path.join(TMP, "state-v5")
MK5 = os.path.join(SNAP5, "verify-in-progress.json")


def v5(*args, **kw):
    kw["env_extra"] = {"UPKEEP_STATE_DIR": SNAP5, **(kw.get("env_extra") or {})}
    return run(*args, **kw)


def forge(child, script, pid=4194999):
    os.makedirs(SNAP5, exist_ok=True)
    json.dump({"at": int(_time.time()), "pid": pid, "step": "verify", "child": child, "script": script}, open(MK5, "w"))


# ---- N1: the marker's `child` and `script` are not trusted
sl = subprocess.Popen(["sleep", "60"], start_new_session=True)
forge(sl.pid, "sleep")
rc, out, err = v5("busy", "status")
check(R5 + "N1 a forged marker naming an unrelated process (its own session) and a script that is a substring of its command line does NOT stop it; the gate is still closed",
      rc == 0 and "RECOVERED" in err and "orphaned selfcheck was stopped" not in err and sl.poll() is None and busy_is_on(), (rc, err, sl.poll()))
sl.kill(); sl.wait()
os.unlink(os.path.join(GSTATE, "busy"))
py = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(60)"], start_new_session=True)
forge(py.pid, "time.sleep")
rc, out, err = v5("busy", "status")
check(R5 + "N1 the same with a python process and script `time.sleep`", "RECOVERED" in err and "orphaned" not in err and py.poll() is None, err)
py.kill(); py.wait()
os.unlink(os.path.join(GSTATE, "busy"))
real_sc = spawn_sleeper(True)
forge(real_sc.pid, "NOT-THE-SCRIPT")
rc, out, err = v5("busy", "status")
_time.sleep(0.3)
check(R5 + "N1 the selfcheck this tool computes itself is stopped even when the marker's script text is wrong (the text is ignored)", "orphaned selfcheck was stopped" in err and real_sc.poll() is not None, (err, real_sc.poll()))
stop(real_sc)
os.unlink(os.path.join(GSTATE, "busy"))
not_leader = spawn_sleeper(False)
forge(not_leader.pid, SELFCHECK)
rc, out, err = v5("busy", "status")
check(R5 + "N1 a process with the selfcheck's command line that is not the leader of its own process group (killpg would hit its neighbours) is left alone",
      "RECOVERED" in err and "orphaned" not in err and not_leader.poll() is None, (err, not_leader.poll()))
stop(not_leader)
os.unlink(os.path.join(GSTATE, "busy"))
forge(os.getpid(), SELFCHECK)
forge(1, SELFCHECK)
rc, out, err = v5("busy", "status")
check(R5 + "N1 pid 1 is never signalled (and the test runner is still alive)", "RECOVERED" in err and "orphaned" not in err)
os.unlink(os.path.join(GSTATE, "busy"))
sleeper = spawn_sleeper(True)
real_stat = U.os.stat


class FakeSt:
    def __init__(self, st):
        self.st_uid = st.st_uid + 1


U.os.stat = lambda pth, *a, **k: FakeSt(real_stat(pth)) if str(pth) == f"/proc/{sleeper.pid}" else real_stat(pth, *a, **k)
try:
    other_uid = U.own_selfcheck_group(sleeper.pid, {"UPKEEP_TEST": TESTMARK, "UPKEEP_SELFCHECK": SELFCHECK})
finally:
    U.os.stat = real_stat
same_uid = U.own_selfcheck_group(sleeper.pid, {"UPKEEP_TEST": TESTMARK, "UPKEEP_SELFCHECK": SELFCHECK})
check(R5 + "N1 own_selfcheck_group: the right process of this user is accepted; the same process owned by another uid is not", same_uid and not other_uid, (same_uid, other_uid))
stop(sleeper)

# ---- N1b: a marker that cannot be removed is renamed to .stale and said once
shutil.rmtree(SNAP5, ignore_errors=True)
os.makedirs(MK5)
open(os.path.join(MK5, "x"), "w").write("a directory where the marker file should be")
rc, out, err = v5("busy", "status")
rc2, out2, err2 = v5("busy", "status")
rc3, out3, err3 = v5("busy", "status")
log5 = [e for e in U.read_log(SNAP5) if e["step"] == "verify-recovered"]
check(R5 + "N1b a marker that is a directory: the first call recovers (gate closed), renames it to .stale and says so; the next calls are quiet and log nothing more",
      "RECOVERED" in err and "renamed to verify-in-progress.json.stale" in err and "RECOVERED" not in err2 + err3 and len(log5) == 1 and os.path.isdir(MK5 + ".stale") and not os.path.lexists(MK5), (err, err2, len(log5)))
os.unlink(os.path.join(GSTATE, "busy"))
shutil.rmtree(MK5 + ".stale")
os.mkfifo(MK5)
rc, out, err = v5("busy", "status", timeout=30)
check(R5 + "N1b a marker that is a fifo does not hang the tool: stale, recovered, set aside", rc == 0 and "RECOVERED" in err, (rc, err))
os.unlink(os.path.join(GSTATE, "busy"))
shutil.rmtree(SNAP5, ignore_errors=True)

# ---- N2: the headline and the audit step follow the real result of the restore
GN = os.path.join(TMP, "n2")
AW = "real_aw = U.atomic_write\nn_ = [0]\ndef aw(*a, **k):\n    n_[0] += 1\n    if n_[0] >= %d:\n        raise OSError(28, 'No space left on device')\n    return real_aw(*a, **k)\nU.atomic_write = aw\n"
fresh_live()
GATE["services"] = {}
cid_d = cid_of(runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")[1])
o0 = md5map(LIVE)
r0, n0 = restarts(), len(U.list_changes(ST2))
rc, out, err = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--apply", "--confirm", cid_d, patch=AW % 3)
ch_n2 = U.list_changes(ST2)[-1][0]
last = [e for e in U.read_log(ST2) if e["step"] == "gate-deploy"][-1]
check(R5 + "N2 a failed copy whose restore ALSO fails: the headline says the restore FAILED and the tree is half-deployed (not 'every file was put back'), the audit result is failed-restore-failed with the undo command, no restart",
      rc == 1 and "AND THE RESTORE FAILED" in out and "HALF-DEPLOYED" in out and "every file was put back" not in out and last["result"] == "failed-restore-failed" and "restore FAILED" in last["what"]
      and "undo " + ch_n2 in last.get("rollback", "") and md5map(LIVE) != o0 and restarts() == r0 and "Traceback" not in out + err, (out[-900:], last))
rc, out, err = runc("undo", ch_n2, "--apply", "--force")
check(R5 + "N2 the printed `undo --force` then restores the tree exactly (md5 equal to before the deploy)", rc == 0 and md5map(LIVE) == o0, (out[-500:],))
fresh_live()
cid_p = cid_of(runc("plan", "profile")[1])
o0 = md5map(LIVE)
rc, out, err = runc("plan", "profile", "--apply", "--confirm", cid_p, patch=AW % 3)
last = [e for e in U.read_log(ST2) if e["step"] == "profile-apply"][-1]
check(R5 + "N2 profile: the second write fails and the restore of the first fails too: FAILED with the restore reported failed, audit failed-restore-failed", rc == 1 and "ALSO failed" in out and last["result"] == "failed-restore-failed", (out[-600:], last))
# the gate does not come back and the rollback itself fails
fresh_live()
GATE["services"] = {}
cid_d = cid_of(runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")[1])
write("healthz_down", "")
PATCH_RB = ("real_aw = U.atomic_write\nflag_ = %r\nreal_restart = U.do_restart\n"
            "def dr(*a, **k):\n    open(flag_, 'w').close()\n    return real_restart(*a, **k)\nU.do_restart = dr\n"
            "def aw(*a, **k):\n    import os\n    if os.path.exists(flag_):\n        raise OSError(28, 'No space left on device')\n    return real_aw(*a, **k)\nU.atomic_write = aw\n") % os.path.join(TMP, "rb_flag")
if os.path.exists(os.path.join(TMP, "rb_flag")):
    os.unlink(os.path.join(TMP, "rb_flag"))
rc, out, err = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--apply", "--confirm", cid_d, patch=PATCH_RB)
last = [e for e in U.read_log(ST2) if e["step"] == "gate-deploy"][-1]
check(R5 + "N2 gate down after the restart and the rollback fails: 'ROLLBACK FAILED' (not 'ROLLED BACK'), audit rollback-failed", rc == 1 and "THE ROLLBACK FAILED" in out and "ROLLED BACK:" not in out
      and last["result"] == "rollback-failed", (out[-700:], last))
os.unlink(os.path.join(FAKE, "healthz_down"))
fresh_live()

# ---- N3: special files are refused, never opened
fifo_conf = os.path.join(LIVE, "power_profiles.conf")
os.unlink(fifo_conf)
os.mkfifo(fifo_conf)
rc, out, err = runc("plan", "profile", timeout=30)
check(R5 + "N3 plan profile with power_profiles.conf as a fifo: NOT OK, 'not a regular file', no hang", rc == 1 and "NOT OK destination" in out and "not a regular file" in out and "DIFF" not in out, (rc, out[:600]))
fresh_live()
fifo_res = os.path.join(TMP, "results.fifo")
if os.path.exists(fifo_res):
    os.unlink(fifo_res)
os.mkfifo(fifo_res)
rc, out, err = runc("plan", "profile", fifo_res, timeout=30)
check(R5 + "N3 a results file that is a fifo: 'cannot read ... not a regular file', no hang", rc == 1 and "cannot read" in out and "not a regular file" in out, (rc, out[:500]))
os.unlink(fifo_res)
fresh_live()
GATE["services"] = {}
cid_d = cid_of(runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")[1])
runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--apply", "--confirm", cid_d)
ch_f = U.list_changes(ST2)[-1][0]
fifo_t = os.path.join(LIVE, "gate", "gate.py")
os.unlink(fifo_t)
os.mkfifo(fifo_t)
rc, out, err = runc("undo", ch_f, "--apply", timeout=30)
rc_f, out_f, _ = runc("undo", ch_f, "--apply", "--force", timeout=30)
rc_l, out_l, _ = runc("undo", ch_f, timeout=30)
check(R5 + "N3 undo with a fifo at a manifest path: NOT UNDONE (with and without --force), the fifo is still there, no hang; the dry run says so too",
      rc == 1 and rc_f == 1 and "NOT UNDONE" in out and "NOT UNDONE" in out_f and "not a regular file" in out and stat.S_ISFIFO(os.lstat(fifo_t).st_mode) and rc_l == 1 and "not a regular file" in out_l, (out[-500:], out_f[-300:]))
os.unlink(fifo_t)
os.mkfifo(fifo_res)
check(R5 + "N3 md5_path and open_regular: a fifo is 'no file' / OSError at once", U.md5_path(os.path.join(TMP, "nothing")) is None
      and U.md5_path(fifo_res) is None and U.special_file(fifo_res) and not U.special_file(os.path.join(TMP, "nothing")), None)
try:
    U.open_regular(fifo_res)
    ore = "no error"
except OSError as e:
    ore = e.errno
os.unlink(fifo_res)
check(R5 + "N3 open_regular(fifo) raises EINVAL", ore == errno.EINVAL, ore)
SNAPF = os.path.join(TMP, "state-fifo")
os.makedirs(SNAPF, mode=0o700, exist_ok=True)
os.mkfifo(os.path.join(SNAPF, "audit.jsonl"))
rc, out, err = run("log", env_extra={"UPKEEP_STATE_DIR": SNAPF}, timeout=30)
rc2, out2, err2 = run("busy", "on", "--apply", env_extra={"UPKEEP_STATE_DIR": SNAPF}, timeout=30)
os.unlink(os.path.join(GSTATE, "busy")) if busy_is_on() else None
check(R5 + "N3 an audit log that is a fifo hangs nothing: `log` reads it as empty, `busy on --apply` still works and says the log could not be written", rc == 0 and rc2 == 0 and "audit log could not be written" in err2, (rc, err, rc2, err2))

# ---- N4: every override is shown; the test overrides need the selftest's marker
rc, out, err = runc("busy", "status")
check(R5 + "N4 every UPKEEP_* override in effect is printed to stderr as OVERRIDE (state dir, boot dir, test mode, selfcheck, gpu dir ...)",
      all(f"upkeep: OVERRIDE: {k} is set" in err for k in ("UPKEEP_STATE_DIR", "UPKEEP_BOOT_DIR", "UPKEEP_TEST", "UPKEEP_SELFCHECK", "UPKEEP_GPU_DIR")), err)
rc, out, err = runc("busy", "status", env_extra={"UPKEEP_BOOT_MIN_MB": "1", "UPKEEP_CHECKOUT": "/x", "UPKEEP_FUTURE_KNOB": "1"})
check(R5 + "N4 UPKEEP_BOOT_MIN_MB, UPKEEP_CHECKOUT and a variable the tool does not know are listed too", all(k in err for k in ("UPKEEP_BOOT_MIN_MB is set", "UPKEEP_CHECKOUT is set", "UPKEEP_FUTURE_KNOB is set (an unknown override)")), err)
rc, out, err = runc("busy", "status", env_extra={"UPKEEP_TEST": "1", "UPKEEP_SELFCHECK": "/tmp/evil.py"})
check(R5 + "N4 UPKEEP_TEST=1 with UPKEEP_SELFCHECK is announced as IGNORED (test mode is off without the selftest's marker)", "UPKEEP_SELFCHECK is set" in err and "IGNORED" in err and "test mode is OFF" in err, err)
env1 = {"UPKEEP_TEST": "1", "UPKEEP_SELFCHECK": "/tmp/evil.py"}
check(R5 + "N4 selfcheck_script: UPKEEP_TEST=1 is not enough; the selftest's marker is", U.selfcheck_script(env1) == os.path.join(U.GPU, "gpu_selfcheck.py")
      and U.selfcheck_script({"UPKEEP_TEST": TESTMARK, "UPKEEP_SELFCHECK": "/tmp/evil.py"}) == "/tmp/evil.py" and not U.test_mode({"UPKEEP_TEST": "1"}))
bad_marks = []
d_ok = _tempfile.mkdtemp(prefix="mark-")
for label, mk in (("wrong name", "other.marker"), ("wrong content", None), ("mode 644", None), ("old", None), ("a symlink", None), ("outside the temp dir", None)):
    pth = os.path.join(d_ok, mk or U.TEST_MARKER_NAME)
    if os.path.lexists(pth):
        os.unlink(pth)
    if label == "a symlink":
        os.symlink(TESTMARK, pth)
    else:
        with open(pth, "w") as f_:
            f_.write("nope\n" if label == "wrong content" else U.TEST_MARKER_MAGIC + "\n")
        os.chmod(pth, 0o644 if label == "mode 644" else 0o600)
        if label == "old":
            os.utime(pth, (_time.time() - 86400, _time.time() - 86400))
    if label == "outside the temp dir":
        pth = os.path.join(os.path.expanduser("~"), ".cache", "bridgeai-selftest-tmp", U.TEST_MARKER_NAME)
        with open(pth, "w") as f_:
            f_.write(U.TEST_MARKER_MAGIC + "\n")
        os.chmod(pth, 0o600)
        U.tempfile_real = U.tempfile.gettempdir
        U.tempfile.gettempdir = lambda: "/nonexistent-tmp"
        try:
            bad_marks.append((label, U.test_mode({"UPKEEP_TEST": pth})))
        finally:
            U.tempfile.gettempdir = U.tempfile_real
        os.unlink(pth)
        continue
    bad_marks.append((label, U.test_mode({"UPKEEP_TEST": pth})))
shutil.rmtree(d_ok, ignore_errors=True)
check(R5 + "N4 test_mode refuses a marker with the wrong name, wrong content, mode 644, an old file, a symlink, or outside the temp directory", all(v is False for _l, v in bad_marks) and len(bad_marks) == 6, bad_marks)
subprocess.run(["git", "-C", GITREPO, "branch", "-f", "only-in-selftest", "HEAD"], check=True, capture_output=True, env=genv)
rc, out, _ = runc("plan", "deploy", "--from-ref", "only-in-selftest", "--no-mcp-dispatch", env_extra={"UPKEEP_CHECKOUT": GITREPO, "UPKEEP_TEST": "1"})
rc2, out2, _ = runc("plan", "deploy", "--from-ref", "only-in-selftest", "--no-mcp-dispatch", env_extra={"UPKEEP_CHECKOUT": GITREPO, "UPKEEP_TEST": ""})
check(R5 + "N4 UPKEEP_CHECKOUT is honoured only with the selftest's marker (a plain UPKEEP_TEST=1 or none: the ref is looked up in the real checkout)",
      "not a commit of this checkout" in out and "not a commit of this checkout" in out2, (out[:300], out2[:300]))
rc3, out3, _ = runc("plan", "deploy", "--from-ref", "only-in-selftest", "--no-mcp-dispatch", env_extra={"UPKEEP_CHECKOUT": GITREPO, "UPKEEP_GPU_DIR": LIVE})
check(R5 + "N4 (with the marker the same lookup in the test checkout works: the setup is not what blocks it)", "not a commit of this checkout" not in out3, out3[:300])
SNAP4b = os.path.join(TMP, "state-ovr")
shutil.rmtree(SNAP4b, ignore_errors=True)
run("busy", "on", "--apply", env_extra={"UPKEEP_STATE_DIR": SNAP4b})
run("busy", "off", "--apply", env_extra={"UPKEEP_STATE_DIR": SNAP4b})
n_one = [e for e in U.read_log(SNAP4b) if e["step"] == "override"]
run("busy", "off", "--apply", env_extra={"UPKEEP_STATE_DIR": SNAP4b, "UPKEEP_PROTECT": "^foo$"})
n_two = [e for e in U.read_log(SNAP4b) if e["step"] == "override"]
check(R5 + "N4 an --apply logs the overrides once (an `override` audit line starting with OVERRIDE:), not again for the same set, and again when the set changes",
      len(n_one) == 1 and n_one[0]["note"].startswith("OVERRIDE: ") and "UPKEEP_STATE_DIR" in n_one[0]["note"] and len(n_two) == 2 and "UPKEEP_PROTECT" in n_two[-1]["note"], (n_one, n_two))
usrc = open(UPKEEP).read()
check(R5 + "N4 the docstring no longer claims the environment alone cannot run another script; it says test_mode and the marker", "the environment alone\n    cannot make this tool run an arbitrary script" not in usrc
      and "the environment alone cannot make" not in usrc and "test_mode" in usrc.split("def run_selfcheck")[1][:1500])
SK5 = open(os.path.join(HERE, "..", "..", "aibridge", "SKILL_host_upkeep.md")).read()
never = SK5.split("## Never")[1]
check(R5 + "N4 the skill's Never list names UPKEEP_TEST, UPKEEP_SELFCHECK, UPKEEP_CHECKOUT, UPKEEP_STATE_DIR, UPKEEP_BOOT_DIR and UPKEEP_BOOT_MIN_MB", all(k in never for k in ("UPKEEP_TEST", "UPKEEP_SELFCHECK", "UPKEEP_CHECKOUT", "UPKEEP_STATE_DIR", "UPKEEP_BOOT_DIR", "UPKEEP_BOOT_MIN_MB")), None)

# ---- N5: git runs with core.fsmonitor off
GRP = os.path.join(TMP, "gitfsm")
shutil.rmtree(GRP, ignore_errors=True)
os.makedirs(os.path.join(GRP, "gpu-host"))
flag_fs = os.path.join(TMP, "fsmonitor_ran")
if os.path.exists(flag_fs):
    os.unlink(flag_fs)
hook = os.path.join(TMP, "fsmon.sh")
open(hook, "w").write(f"#!/bin/sh\necho ran >> {flag_fs}\nprintf '\\0'\n")
os.chmod(hook, 0o755)
for g in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.invalid"], ["config", "user.name", "t"], ["config", "core.fsmonitor", hook]):
    subprocess.run(["git", "-C", GRP, *g], check=True, capture_output=True, env=genv)
open(os.path.join(GRP, "gpu-host", "a.txt"), "w").write("x\n")
subprocess.run(["git", "-C", GRP, "add", "-A"], check=True, capture_output=True, env=genv)
subprocess.run(["git", "-C", GRP, "commit", "-q", "-m", "x"], check=True, capture_output=True, env=genv)
S5 = U.Sys(GRP)
if os.path.exists(flag_fs):
    os.unlink(flag_fs)
subprocess.run(["git", "-C", GRP, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "gpu-host"], capture_output=True, env=genv)
bare_ran = os.path.exists(flag_fs)
if bare_ran:
    os.unlink(flag_fs)
rc5, out5 = S5.cmd([*S5.git_prefix(), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "gpu-host"], 30)
check(R5 + "N5 (sanity) a bare `git status` in a repo with core.fsmonitor set runs that program", bare_ran, None)
check(R5 + "N5 the tool's git status does NOT run the fsmonitor program; the call is allowed only with -c core.fsmonitor=false",
      rc5 == 0 and not os.path.exists(flag_fs) and not S5.allowed(["git", "-C", GRP, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "gpu-host"])
      and S5.allowed([*S5.git_prefix(), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "gpu-host"]) and not S5.allowed(["git", "-c", "core.fsmonitor=true", "-C", GRP, "rev-parse", "--verify", "--quiet", "main^{commit}"]), (rc5, os.path.exists(flag_fs)))

# ---- N6 / N7: destinations in other work trees, a symlinked --dest, a relative GATE_POWER_PROFILES
fresh_live()
OTH = os.path.join(TMP, "othercheckout")
shutil.rmtree(OTH, ignore_errors=True)
shutil.copytree(LIVE, os.path.join(OTH, "gpu-host"))
os.makedirs(os.path.join(OTH, ".git"))
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--dest", os.path.join(OTH, "gpu-host"))
check(R5 + "N6 a --dest inside another git work tree gets a note that the dirty-tree check is not made there", "inside another git work tree" in out and "dirty-tree check" in out, out[:900])
rc, out, _ = runc("plan", "profile", "--dest", os.path.join(OTH, "gpu-host"))
check(R5 + "N6 the same note for a profile change", "inside another git work tree" in out, out[:900])
LNK = os.path.join(TMP, "dest-link")
if os.path.lexists(LNK):
    os.unlink(LNK)
os.symlink(LIVE, LNK)
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--dest", LNK)
check(R5 + "N7 a --dest that is itself a symlink is accepted with a note that says where the files really are", "--dest is itself a symlink" in out and os.path.realpath(LIVE) in out and "NOT OK" not in out, out[:900])
rc, out, _ = runc("plan", "profile", env_extra={"GATE_POWER_PROFILES": "rel/power.conf"})
check(R5 + "N6 a relative GATE_POWER_PROFILES is NOT OK for a profile change (the gate resolves it against its own working directory)", rc == 1 and "relative path" in out and "DIFF" not in out, out[:700])
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", env_extra={"GATE_POWER_PROFILES": "rel/power.conf"})
check(R5 + "N6 and a warning for a deploy", "relative path" in out and "warn   gate" in out, out[:700])

# ---- N8: the rest
fresh_live()
GATE["services"] = {}
cid_d = cid_of(runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")[1])
runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch", "--apply", "--confirm", cid_d)
ch8 = U.list_changes(ST2)[-1][0]
wp = os.path.join(LIVE, "resolve_mcp", "wrapper.py")
shutil.copy(wp, os.path.join(LINKT, "w8.py"))
os.unlink(wp)
os.symlink(os.path.join(LINKT, "w8.py"), wp)
rc, out, _ = runc("undo", ch8, "--apply", "--force")
mf = U.read_manifest(ST2, ch8)
check(R5 + "N8 an undo that left a file wrong (RESULT: failed) does not set undone_at", rc == 1 and "RESULT: failed" in out and mf is not None and not mf.get("undone_at"), (out[-300:], mf and mf.get("undone_at")))
rc, out, _ = runc("undo", ch8)
check(R5 + "N8 ... so a later plain undo is not 'already undone'", "already undone" not in out, out[:300])
os.unlink(wp)
shutil.copy(os.path.join(LINKT, "w8.py"), wp)
rc, out, _ = runc("undo", ch8, "--apply", "--force")
mf = U.read_manifest(ST2, ch8)
check(R5 + "N8 an undo that restored everything sets undone_at", rc == 0 and mf.get("undone_at"), out[-300:])
SYM = os.path.join(TMP, "state-symlog")
shutil.rmtree(SYM, ignore_errors=True)
os.makedirs(SYM, mode=0o700)
os.symlink(os.path.join(TMP, "somewhere.log"), os.path.join(SYM, "audit.jsonl"))
rc, out, err = run("busy", "on", "--apply", env_extra={"UPKEEP_STATE_DIR": SYM})
was_on = busy_is_on()
if was_on:
    os.unlink(os.path.join(GSTATE, "busy"))
rc2, out2, err2 = run("snapshot", "--apply", env_extra={"UPKEEP_STATE_DIR": SYM})
check(R5 + "N8 a symlinked audit.jsonl: no traceback; busy on says the switch changed and the log could not be written; any other write ends with one sentence (exit 2)",
      "Traceback" not in err + err2 and was_on and rc == 0 and "audit log could not be written" in err and "stopped by a file error" in err2 and rc2 == 2, (rc, err, rc2, err2))
check(R5 + "N8 leftover *.upkeep-tmp-* files are never copied, backed up or listed as kept", U.excluded("gate/gate.py.upkeep-tmp-123-deadbeef") and U.excluded("x.upkeep-tmp-1-ab"), None)
fresh_live()
open(os.path.join(LIVE, "gate", "gate.py.upkeep-tmp-123-deadbeef"), "w").write("half written")
rc, out, _ = runc("plan", "deploy", "--from-dir", NEWSRC, "--no-mcp-dispatch")
check(R5 + "N8 a killed copy's temp file in the tree is not counted in the deploy plan", "upkeep-tmp" not in out, out[:500])
check(R5 + "N8 the VRAM need range ends at 96 GB (a 190000 MB need is a measurement error)", U.int_in(190000, *U.NEED_MB_RANGE) is None and U.int_in(24000, *U.NEED_MB_RANGE) == 24000, U.NEED_MB_RANGE)
fresh_live()
write_results([{"kind": "session", "run": R_NEW, "gpu": dict(CARD)}, rec(R_NEW, "stt", 110, 4000)])
rc, out, _ = runc("plan", "profile")
check(R5 + "N8 a VRAM need that more than doubles is a warning in the dry run", "warn   need" in out and "grow from 1540 to 4000" in out and rc == 0, out[:700])
write_results(RESULT_ROWS)
crlf = "[A]\r\nllm = 130\r\nstt = 100\r\n"
new_c, ch_c, pr_c = U.edit_conf(crlf, "A", {"llm": 120, "mosher": 100})
_crlf_p = os.path.join(os.environ.get("TMPDIR", "/tmp"), "crlf-read-check.conf")
with open(_crlf_p, "w", newline="") as _f:
    _f.write(crlf)
check(R5 + "R1 read_text(keep_newlines=True) keeps CRLF (the file the profile procedure rewrites)", U.read_text(_crlf_p, keep_newlines=True) == crlf and U.read_text(_crlf_p) == crlf.replace("\r\n", "\n"))
os.remove(_crlf_p)
check(R5 + "N8 a CRLF power_profiles.conf keeps CRLF on changed and added lines (no mixed line endings)", not pr_c and new_c.count("\n") == new_c.count("\r\n") and "mosher = 100\r\n" in new_c and "llm = 120\r\n" in new_c, repr(new_c))
check(R5 + "N8 UPKEEP.md documents the backup space (20 backups of up to 200 MB), the symlinked --dest, and the OVERRIDE/test marker rules",
      all(x in open(os.path.join(HERE, "UPKEEP.md")).read() for x in ("200 MB", "up to 4 GB", "itself a symlink", "OVERRIDE", "upkeep-selftest.marker", "core.fsmonitor")), None)

# ================================================================================================================ review fixes: hostcare's NEVER list against everything printed
HC = importlib.util.spec_from_file_location("hostcare_under_test", os.path.join(HERE, "..", "..", "aibridge", "ops", "hostcare", "hostcare_mcp.py"))
HCM = importlib.util.module_from_spec(HC)
HC.loader.exec_module(HCM)


def refused_by_hostcare(cmd):
    return [p for p in HCM.NEVER if re.search(p, cmd, re.I)]


host_state()
plan_out = run("plan", "driver", "--to", NEW)[1]
host_state(updated=True)
rb_out = run("rollback", env_extra={"UPKEEP_STATE_DIR": SNAPDIR})[1]
host_state(updated=True, dkms_missing={"nvidia": KERNELS[1]})
verify_out = run("verify", "--to", NEW, "--apply", sel_exit=0, env_extra={"UPKEEP_STATE_DIR": SNAPDIR})[1]
host_state()


def printed_commands(text):
    """[(tag, command)] of every `$ ` line of a plan/rollback output, with the tag of its step, plus the bot's file-route command in a `# or:` line."""
    out, tag = [], None
    for line in text.splitlines():
        m = re.match(r"^\s*\d+\. \[([^\]]+)\]", line)
        if m:
            tag = m.group(1)
        elif line.startswith("      $ "):
            out.append((tag, line[8:]))
        m = re.search(r"\(then the bot runs: (.*)\)\s*$", line)
        if m:
            out.append(("bot, no root", m.group(1)))
    return out


card_outs = [SHOW[k] for k in SHOW if k.startswith(("plan profile", "plan deploy", "plan kernel", "undo of the deploy", "unlock"))]
cmds = printed_commands(plan_out) + printed_commands(rb_out) + printed_commands(verify_out) + [c for o in card_outs for c in printed_commands(o)]
check("hostcare: the card plans (profile, deploy, kernel) are in the commands judged below", len(card_outs) >= 4 and sum(1 for o in card_outs for t, _c in printed_commands(o) if t == "bot, no root") >= 12, len(card_outs))
check("hostcare: the plans print many commands (the test is not vacuous)", len(cmds) > 25 and sum(1 for t, _c in cmds if t == "bot, no root") >= 8, len(cmds))
bad = [(t, c) for t, c in cmds if t == "bot, no root" and refused_by_hostcare(c)]
check("hostcare NEVER: no command the BOT runs (plan, rollback, verify output) is refused by hostcare's real NEVER regexes", not bad, bad)
owner_refused = sorted({c for t, c in cmds if t != "bot, no root" and refused_by_hostcare(c)})
check("hostcare NEVER: the only OWNER command it would refuse is the reboot (the owner runs it by hand, never through hostcare)", owner_refused == ["sudo reboot"], owner_refused)
check("hostcare NEVER: no owner step is tagged as a bot step by mistake", all(t in ("bot, no root", "owner, root", "owner, no root") for t, _c in cmds), {t for t, _c in cmds})
SK = open(os.path.join(HERE, "..", "..", "aibridge", "SKILL_host_upkeep.md")).read()
SUBS = ("plan driver", "plan profile", "plan deploy", "plan kernel", "check-sim", "verify", "rollback", "log --add", "busy", "idle", "snapshot", "unlock", "undo")
spans = []
for x in re.findall(r"`([^`\n]+)`", SK):
    if "upkeep.py" in x:
        spans.append(x)
    elif x.split(" ")[0] in {w.split(" ")[0] for w in SUBS} and not x.startswith("--"):
        spans.append("cd /x && python3 gpu-host/upkeep/upkeep.py " + x)          # the skill writes some commands without the prefix
subst = lambda c: c.replace("VERSION", NEW).replace("NEW", NEW).replace("OLD", OLD).replace("SNAPSHOT", "20261118T000000Z").replace("FILE", "/tmp/sim.txt")
bad = [c for c in spans if refused_by_hostcare(subst(c))]
check("hostcare NEVER: every upkeep.py command in the skill passes (nothing in it is refused)", len(spans) >= 10 and not bad, bad)
steps_in_skill = re.findall(r"`(owner-[a-z-]+)`", SK)
bad = [st for st in steps_in_skill if refused_by_hostcare(f'cd /x && python3 gpu-host/upkeep/upkeep.py log --add {st} --result done --note "pin swapped, no errors" --apply')]
check("hostcare NEVER: every log step name the skill and UPKEEP.md give the bot passes (owner-reboot is gone, it is owner-host-restart)",
      set(steps_in_skill) >= {"owner-apt-update", "owner-apt-pin", "owner-apt-driver", "owner-host-restart"} and "owner-reboot" not in steps_in_skill and not bad, (steps_in_skill, bad))
check("hostcare NEVER: the word the NEVER list refuses is not in any step name the docs print as one to log", not any(w in st for st in steps_in_skill for w in ("reboot", "shutdown", "poweroff", "halt")))
check("hostcare NEVER: the check really bites (owner-reboot WOULD be refused, a note with the word too)", bool(refused_by_hostcare("upkeep.py log --add owner-reboot --result done --apply"))
      and bool(refused_by_hostcare('upkeep.py log --add x --note "the owner did a reboot" --apply')))
check("skill: the bot never puts pasted text into a command: a file or the one-line verdict instead, and the old stdin route is gone",
      "Never run `check-sim -` with pasted text" in SK and "heredoc" in SK and "on stdin" not in SK and "paste their output to you" not in SK)
check("skill: it names the stale-list route (apt update, then plan again), the timeout, UPKEEP_STATE_DIR, the checkout path, and the wiring status",
      all(x in SK for x in ("sudo apt update", "plan again", "timeout=300", "UPKEEP_STATE_DIR", "cd PATH &&", "Status: NOT installed", "docker cp")), None)
check("skill: it covers the card as a whole (re-bench after a driver, unlock or kernel change; apply a proposal with the owner's yes and the confirm id of the dry run; undo; the kernel gate before the restart; the events stay on the host) and never runs root",
      all(x in SK for x in ("When to re-bench", "plan profile", "plan deploy", "undo ID --apply", "--confirm ID", "unlock --kernel RELEASE", "before** the owner restarts", "never add either on your own", "stay on")), None)
check("docs: UPKEEP.md has the GPU card management section (profile, deploy, unlock, kernel, undo, the gate rules, the change log, events stay on the host)",
      all(x in open(os.path.join(HERE, "UPKEEP.md")).read() for x in ("## GPU card management", "### Profile apply", "### Gate deploy", "### Unlock check", "### Kernel update", "### The gate restart rules", "### The change log",
                                                                   "The events stay on the host", "--restart-while-running", "Sys.act")))
check("skill: it labels owner steps [owner, root] / [owner, no root] and says snapshot REFUSED is not for --force on its own",
      all(x in SK for x in ("[owner, no root]", "[owner, root]", "snapshot REFUSED")))

# ================================================================================================================ no root command, no token
check("the traps (sudo, apt, apt-get, dpkg, reboot, modprobe, update-initramfs, dkms install) were never started",
      not os.path.exists(ROOTCALLS) or open(ROOTCALLS).read() == "", open(ROOTCALLS).read() if os.path.exists(ROOTCALLS) else "")
refused = 0
for argv in (["sudo", "true"], ["apt", "install", "x"], ["apt-get", "install", "x"], ["dpkg", "-i", "x"], ["reboot"], ["dkms", "install", "x"], ["apt-cache", "show", "x"],
             ["apt-mark", "hold", "x"], ["systemctl", "stop", "x"], ["sh", "-c", "true"]):
    try:
        U.Sys().cmd(argv)
    except U.Refused:
        refused += 1
check("Sys.cmd refuses every program outside the read-only allowlist", refused == 10, refused)
src = open(UPKEEP).read()
check("the source starts no root program (no sudo/apt install in a subprocess call)", "subprocess.run([\"sudo\"" not in src and "os.system" not in src and "shell=True" not in src)
check("the gate token never appears in anything the tool printed", not any(TOKEN in o for o in OUTS))
check("the fake gate was really queried (the test exercised the gate path)", GATE["calls"] > 10, GATE["calls"])
srv.shutdown()

if "--show" in sys.argv:
    for k, v in SHOW.items():
        print("\n=== " + k + "\n" + v)
print("\nFAILED: " + ", ".join(FAIL) if FAIL else "\nall ok")
sys.exit(1 if FAIL else 0)
