#!/usr/bin/env python3
"""Offline checks for place_memguard.py with a fake /proc and fake places. Run: python3 -I place_memguard_selftest.py"""
import importlib.util, json, os, shutil, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
fails = []
def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(f"{name}: {detail}")

tmp = tempfile.mkdtemp(prefix="memguard-selftest-")
try:
    root, proc = os.path.join(tmp, "places"), os.path.join(tmp, "proc")
    for name, uid, mem in (("hergam", 3004, "12g"), ("hermic", 3002, None)):
        os.makedirs(os.path.join(root, name))
        s = {"uid": uid, **({"mem": mem} if mem else {})}
        json.dump(s, open(os.path.join(root, name, ".settings.json"), "w"))
    os.makedirs(proc)
    open(os.path.join(proc, "meminfo"), "w").write("MemTotal: 32000000 kB\nMemAvailable: 20000000 kB\n")
    os.environ.update(PLACES_ROOT=root, MEMGUARD_PROC=proc, MEMGUARD_LOG=os.path.join(tmp, "log.jsonl"),
                      MEMGUARD_SPOOL=os.path.join(tmp, "spool"), MEMGUARD_DRY_RUN="1", PLACE_MEM="9g")
    spec = importlib.util.spec_from_file_location("mg", os.path.join(here, "place_memguard.py"))
    mg = importlib.util.module_from_spec(spec); spec.loader.exec_module(mg)

    owners = mg.places()
    check("places and their limits come from .settings.json (own mem, else PLACE_MEM)", owners == {3004: ("hergam", 12288), 3002: ("hermic", 9216)}, owners)
    procs = [(2600, 10, 3004, "GTAIV.exe", "GTAIV.exe"), (900, 11, 3004, "steamwebhelper", "")]
    check("normal use: nothing to kill", mg.decide(owners, procs, 20000, {}, 1000) == [])
    big = procs + [(15000, 12, 3004, "metro", "")]
    k = mg.decide(owners, big, 20000, {}, 1000)
    check("rule 1: one process over its place's limit is killed, alone", [(x[0], x[1], x[2]) for x in k] == [(12, "hergam", "over_place_limit")], k)
    k = mg.decide(owners, procs + [(5000, 20, 3002, "hog", "")], 2000, {}, 1000)
    check("rule 2: host under the floor -> the biggest place process (over 1 GB) is killed", [(x[0], x[2]) for x in k] == [(20, "host_low_memory")], k)
    k = mg.decide(owners, [(500, 30, 3004, "small", "")], 2000, {}, 1000)
    check("rule 2 never kills a small process", k == [], k)
    k = mg.decide(owners, big, 20000, {"hergam": 995}, 1000)
    check("no second kill of the same place within the cooldown", k == [], k)
    check("the game's name is the last .exe in the command line", mg.game_name("Z:\\x\\steam.exe C:\\Games\\GTAIV\\GTAIV.exe -x") == "GTAIV.exe")

    # step() on the fake /proc: a place process (owned by our own uid here) far over its limit, in dry-run
    me = os.getuid()
    json.dump({"uid": 3004, "mem": "12g"}, open(os.path.join(root, "hergam", ".settings.json"), "w"))
    mg.UID_RANGE = range(min(me, 3001), 4000) if me < 3001 else mg.UID_RANGE
    json.dump({"uid": me, "mem": "1g"}, open(os.path.join(root, "hermic", ".settings.json"), "w"))
    pd = os.path.join(proc, "4242"); os.makedirs(pd)
    open(os.path.join(pd, "status"), "w").write("Name:\tmetro\nVmRSS:\t 3000000 kB\n")
    open(os.path.join(pd, "comm"), "w").write("metro\n")
    open(os.path.join(pd, "cmdline"), "wb").write(b"./metro\0-benchmark\0")
    done = mg.step({}, now=2000)
    check("step: the over-limit process is found and logged (dry run: not killed, no incident file)",
          len(done) == 1 and done[0]["pid"] == 4242 and done[0]["killed"] is False and done[0]["rss_mb"] == 2929
          and not os.path.exists(os.path.join(tmp, "spool")), done)
    check("the log line has the place, reason and host memory", json.loads(open(os.path.join(tmp, "log.jsonl")).read().splitlines()[-1])["reason"] == "over_place_limit")
    mg.DRY = False
    mg.os.kill = lambda pid, sig: None                       # never signal a real process in a test
    done = mg.step({}, now=3000)
    sp = os.listdir(os.path.join(tmp, "spool"))
    check("a real kill writes an incident file for the gate (0644)", len(sp) == 1 and done[0]["killed"] is True
          and oct(os.stat(os.path.join(tmp, "spool", sp[0])).st_mode & 0o777) == "0o644", (sp, done))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("\n".join(fails) or "place_memguard_selftest: all ok")
sys.exit(1 if fails else 0)
