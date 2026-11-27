#!/usr/bin/env python3
"""Offline test of the always-on worker (workers/worker.py + workers/apply.py, WORKERS.md).

No real Docker host, no real container: fake `ssh` and `docker` sit first in PATH. The fake ssh runs the remote command locally
(the "Docker host" is a temp folder; a file `asleep` makes it time out like a suspended host); the real rsync goes through it. The
fake docker logs its arguments and does what the job would do to the mounted folders (or hangs, for the timeout).
Covers: config validation; host asleep -> no pull, the last copy is used, outputs wait; host awake -> pull, run, push; a push never
replaces a newer person-owned file and never deletes; the jobfinder's person-owned files never go back, only the night summary
(merged with an undelivered one) and the early-alert lines; the hard timeout kills the container; the docker flags (caps, no keys);
events carry no text. Needs rsync (it is what the worker uses).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WDIR = os.path.join(HERE, "workers")
sys.path.insert(0, WDIR)
import apply as applymod  # noqa: E402
import worker  # noqa: E402

FAILS = []


def ok(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


FAKE_SSH = r'''#!/usr/bin/env python3
import json, os, sys
ctl = os.environ["FAKE_CTL"]
a = sys.argv[1:]
i = 0
while i < len(a) and a[i].startswith("-"):
    i += 2 if a[i] in ("-o", "-p", "-i", "-l", "-F", "-J", "-c", "-m", "-b", "-E") else 1
host, cmd = a[i], " ".join(a[i + 1:])
with open(os.path.join(ctl, "ssh.log"), "a") as f:
    f.write(json.dumps({"host": host, "cmd": cmd}) + "\n")
if os.path.exists(os.path.join(ctl, "asleep")):
    sys.stderr.write("ssh: connect to host port 22: Connection timed out\n")
    sys.exit(255)
home = os.path.join(ctl, "hosthome")
os.chdir(home)
os.environ["HOME"] = home
os.execvp("sh", ["sh", "-c", cmd])
'''

FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, signal, subprocess, sys, time
ctl = os.environ["FAKE_CTL"]
a = sys.argv[1:]
with open(os.path.join(ctl, "docker.log"), "a") as f:
    f.write(json.dumps(a) + "\n")
if a[0] in ("kill", "rm"):
    pidf = os.path.join(ctl, a[-1] + ".pid")
    if os.path.exists(pidf):
        try:
            os.kill(int(open(pidf).read()), signal.SIGKILL)
        except OSError:
            pass
        os.unlink(pidf)
    sys.exit(0)
if a[0] != "run":
    sys.exit(0)
VAL = {"--name", "--restart", "--network", "--memory", "--memory-swap", "--cpus", "--pids-limit", "--security-opt", "--cap-drop",
       "--cap-add", "--label", "-v", "-e", "--entrypoint", "--user"}
mounts, env, name, entry, i = {}, {}, None, None, 1
while i < len(a) and a[i].startswith("-"):
    k = a[i]
    if "=" in k and k.split("=")[0] in VAL | {"--restart"}:
        i += 1; continue
    if k in VAL:
        v = a[i + 1]
        if k == "-v":
            p = v.split(":"); mounts[p[1]] = p[0]
        elif k == "-e":
            env[v.split("=", 1)[0]] = v.split("=", 1)[1]
        elif k == "--name":
            name = v
        elif k == "--entrypoint":
            entry = v
        i += 2
    else:
        i += 1
image, rest = a[i], a[i + 1:]
def host(p):
    for dst in sorted(mounts, key=len, reverse=True):
        if p == dst or p.startswith(dst + "/"):
            return mounts[dst] + p[len(dst):]
    return p
if entry == "python3" and rest[:1] == ["-"]:       # apply.py on the Docker host
    os.execvp("python3", ["python3", "-"] + [host(x) for x in rest[1:]])
if name:
    open(os.path.join(ctl, name + ".pid"), "w").write(str(os.getpid()))
behavior = open(os.path.join(ctl, "behavior")).read().strip()
json.dump({k: host(v) for k, v in env.items()}, open(os.path.join(ctl, "env.json"), "w"))
if behavior == "hang":
    time.sleep(120)
elif behavior == "subs":
    d = host("/workdir/descargas")
    n = int(open(os.path.join(ctl, "count")).read()) if os.path.exists(os.path.join(ctl, "count")) else 0
    open(os.path.join(ctl, "count"), "w").write(str(n + 1))
    for ch in json.load(open(os.path.join(d, "channels.json"))):
        open(os.path.join(d, ch, f"New video {n} [NEWVIDEO{n:03d}].srt"), "w").write("1\n00:00:00,000 --> 00:00:01,000\nworker\n")
        if os.path.exists(os.path.join(ctl, "clash")):
            open(os.path.join(d, ch, "Clash [CLASHCLASH1].srt"), "w").write("worker\n")
        with open(os.path.join(d, ch, ".nocaps.tsv"), "a") as f:
            f.write(f"WORKERVID{n:02d}\t{int(time.time())}\tes\n")
    if os.path.exists(os.path.join(ctl, "notice")):
        print("subs-nuevos: aviso de prueba para una persona")
elif behavior == "jobnight":
    root = host("/workdir/jobfinder")
    assert os.path.exists(os.path.join(root, "scan.mjs"))
    data = os.path.join(root, "data")
    with open(os.path.join(data, "pipeline.md"), "a") as f:
        f.write("- [ ] https://example.org/job/2 | Company B | Role two\n")
    json.dump({"since": 100, "last": 100, "runs": 1, "failed": 0, "checked": 0, "new": 1,
               "rows": [[{"url": "https://example.org/job/2", "title": "Role two", "company": "Company B"}, "ok", ""]]},
              open(os.path.join(data, ".jobpush-pending.json"), "w"))
    st = json.load(open(os.path.join(data, ".jobpush-state.json")))
    st["night_done"] = "2026-11-26"
    json.dump(st, open(os.path.join(data, ".jobpush-state.json"), "w"))
    with open(host(env["JOBPUSH_EARLY_SIGNALS"]), "a") as f:
        f.write(json.dumps({"ts": 1, "cat": "scan_zero", "n": 1, "v": 5, "src": "jobpush"}) + "\n")
sys.exit(0)
'''


class Env:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="workers-selftest-")
        self.ctl = os.path.join(self.tmp, "ctl")
        self.shims = os.path.join(self.tmp, "shims")
        for d in (self.ctl, self.shims, os.path.join(self.ctl, "hosthome"), os.path.join(self.tmp, "home")):
            os.makedirs(d)
        for name, src in (("ssh", FAKE_SSH), ("docker", FAKE_DOCKER)):
            p = os.path.join(self.shims, name)
            open(p, "w").write(src)
            os.chmod(p, 0o755)
        self.host = os.path.join(self.tmp, "host")
        self.state = os.path.join(self.tmp, "state")
        self.cfgfile = os.path.join(self.tmp, "workers.json")

    def config(self, **over):
        cfg = {"host": "aibridge@fakehost", "image": "aibridge-hermes-agent:test", "apply": "direct",
               "remote_inbox": os.path.join(self.host, "inbox"), "state_dir": self.state,
               "types": {"subs": {"schedule": "*-*-* 00/3:00:00", "memory": "1g", "cpus": 1, "timeout_s": 60},
                         "jobnight": {"schedule": "*-*-* 04:30:00", "memory": "2g", "cpus": 2, "timeout_s": 60}},
               "people": {"stack-a": {"remote_workdir": os.path.join(self.host, "stack-a", "workdir"), "jobs": {"subs": {}}},
                          "stack-b": {"remote_workdir": os.path.join(self.host, "stack-b", "workdir"),
                                      "jobs": {"jobnight": {"timezone": "UTC", "lang": "es"}}}}}
        for k, v in over.items():
            cfg[k] = v
        json.dump(cfg, open(self.cfgfile, "w"))
        return cfg

    def set(self, name, value=True):
        p = os.path.join(self.ctl, name)
        if value is None or value is False:
            if os.path.exists(p):
                os.unlink(p)
        else:
            open(p, "w").write("" if value is True else str(value))

    def worker(self, *args, timeout=120):
        env = dict(os.environ, PATH=self.shims + os.pathsep + os.environ.get("PATH", ""), FAKE_CTL=self.ctl,
                   WORKERS_CONFIG=self.cfgfile, HOME=os.path.join(self.tmp, "home"), BUS_CONFIG=os.path.join(self.tmp, "no-bus.json"))
        return subprocess.run([sys.executable, "-I", os.path.join(WDIR, "worker.py"), *args], env=env, capture_output=True, text=True,
                              timeout=timeout)

    def log(self, name):
        try:
            return [json.loads(x) for x in open(os.path.join(self.ctl, name))]
        except OSError:
            return []

    def events(self):
        try:
            return [json.loads(x) for x in open(os.path.join(self.state, "events.jsonl"))]
        except OSError:
            return []

    def clear_logs(self):
        for n in ("ssh.log", "docker.log"):
            if os.path.exists(os.path.join(self.ctl, n)):
                os.unlink(os.path.join(self.ctl, n))


def write(path, text, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    if mtime:
        os.utime(path, (mtime, mtime))


def read(path):
    try:
        return open(path).read()
    except OSError:
        return None


def test_validation():
    good = json.load(open(os.path.join(WDIR, "workers.json.example")))
    ok(worker.validate(good) == [], "the example config is valid")

    def bad(mut, needle):
        c = json.loads(json.dumps(good))
        mut(c)
        errs = worker.validate(c)
        ok(any(needle in e for e in errs), f"validation catches: {needle} ({errs[:2]})")
    bad(lambda c: c.update(host="docker-host"), "host")
    bad(lambda c: c["types"].update(nope={"schedule": "daily"}), "unknown type")
    bad(lambda c: c["types"]["subs"].update(memory="lots"), "memory")
    bad(lambda c: c["types"]["subs"].update(timeout_s=0), "timeout_s")
    bad(lambda c: c["people"]["stack-b"]["jobs"]["jobnight"].pop("timezone"), "timezone")
    bad(lambda c: c["people"]["stack-a"].update(remote_workdir="aibridge/../etc"), "remote_workdir")
    bad(lambda c: c["people"]["stack-a"].update(remote_workdir="a; rm -rf x"), "remote_workdir")
    bad(lambda c: c["people"]["stack-a"]["jobs"]["subs"].update(env={"OPENAI_API_KEY": "x"}), "is not one of")
    bad(lambda c: c["people"]["stack-a"].update(keyfile="x"), "unknown key")
    bad(lambda c: c["people"].update({"Bad Name": {"jobs": {"subs": {}}}}), "stack name")


def test_merge_pending():
    old = {"since": 50, "last": 60, "runs": 1, "failed": 0, "checked": 3, "new": 1,
           "rows": [[{"url": "u1"}, "ok", ""], [{"url": "u2"}, "ok", ""]], "closing": [{"key": "c1"}], "expired": [{"key": "e1"}]}
    new = {"since": 100, "last": 100, "runs": 2, "failed": 1, "checked": 0, "new": 2,
           "rows": [[{"url": "u1"}, "muerta", "x"], [{"url": "u3"}, "ok", ""]], "closing": [], "expired": [{"key": "e1"}, {"key": "e2"}]}
    m = applymod.merge_pending(old, new)
    ok(m["runs"] == 3 and m["failed"] == 1 and m["new"] == 3 and m["since"] == 50 and m["last"] == 100, "merge: counters add up")
    ok([r[0]["url"] for r in m["rows"]] == ["u2", "u1", "u3"] and m["rows"][1][1] == "muerta", "merge: the latest verdict wins, goes last")
    ok(m["closing"] == [] and [e["key"] for e in m["expired"]] == ["e1", "e2"], "merge: latest closing list, expired once")
    ok(applymod.merge_pending({}, new) == new, "merge: nothing waiting on the host = the worker's summary")


def test_bus():
    sent = []

    class FakeBus:
        @staticmethod
        def send(subject, data, msg_id=None):
            sent.append((subject, data, msg_id))
            return "ok seq=1"
    tmp = tempfile.mkdtemp(prefix="workers-bus-")
    old_on, old_bus = worker.BUS_ON, worker.bus
    try:
        worker.BUS_ON, worker.bus = True, FakeBus
        worker.emit({"state_dir": tmp}, "subs", "done", stack="stack-a", secs=1.25, note="Hello there, a sentence", path="/workdir/x")
    finally:
        worker.BUS_ON, worker.bus = old_on, old_bus
        shutil.rmtree(tmp, ignore_errors=True)
    ok(len(sent) == 1 and sent[0][0] == "ev.worker.subs.done", "bus: ev.worker.<type>.<event> published when the bus is on")
    ok(sent and "note" not in sent[0][1] and "path" not in sent[0][1] and sent[0][1]["stack"] == "stack-a",
       "bus: free text and paths are dropped from the payload")


def test_subs(e):
    wd = os.path.join(e.host, "stack-a", "workdir")
    d = os.path.join(wd, "descargas")
    write(os.path.join(d, "channels.json"), json.dumps({"chan1_subs": {"url": "https://www.youtube.com/@x", "lang": "es-orig"}}))
    write(os.path.join(d, "chan1_subs", "Old [OLDOLDOLD01].srt"), "old\n")
    write(os.path.join(d, "chan1_subs", ".nocaps.tsv"), "HOSTVIDEO01\t1\tes-orig\n", mtime=time.time() - 3600)
    write(os.path.join(d, "a-movie.mp4"), "not a channel")
    write(os.path.join(d, "other", "file.txt"), "not a channel")
    e.set("behavior", "subs")
    copy = os.path.join(e.state, "stack-a", "subs", "copy")

    # 1. asleep, never pulled: nothing runs
    e.set("asleep")
    r = e.worker("run", "subs")
    ok(r.returncode == 0, f"asleep, no copy: run exits 0 ({r.stderr.strip()[-200:]})")
    ok(not any(x[0] == "run" for x in e.log("docker.log")), "asleep, no copy: no container started")
    ok(all(x["cmd"] == "true" for x in e.log("ssh.log")), "asleep: only the awake probe, no rsync")
    ok(any(x["subject"] == "ev.worker.subs.skipped_host_asleep" and x["data"].get("has_copy") is False for x in e.events()),
       "asleep, no copy: skipped_host_asleep event")

    # 2. awake: pull -> run -> push
    e.set("asleep", None)
    e.clear_logs()
    r = e.worker("run", "subs")
    ok(r.returncode == 0, f"awake: run exits 0 ({r.stderr.strip()[-300:]})")
    ok(os.path.isfile(os.path.join(copy, "chan1_subs", "Old [OLDOLDOLD01].srt")), "pull: the channel's subtitles are copied")
    ok(not os.path.exists(os.path.join(copy, "a-movie.mp4")) and not os.path.exists(os.path.join(copy, "other")),
       "pull: nothing outside the registered channels is copied")
    runs = [x for x in e.log("docker.log") if x[0] == "run"]
    ok(len(runs) == 1, "awake: one container")
    a = runs[0] if runs else []
    s = " ".join(a)
    ok("--rm" in a and "--restart=no" in a and a[a.index("--memory") + 1] == "1g" and "--cpus" in a and "--pids-limit" in a,
       "docker: --rm, --restart=no, memory/cpu/pids caps")
    ok(a.count("--cap-drop") == 1 and a[a.index("--cap-drop") + 1] == "ALL" and "--privileged" not in a and "SYS_ADMIN" not in s,
       "docker: all capabilities dropped but the stacks' profile")
    vols = [a[i + 1] for i, x in enumerate(a) if x == "-v"]
    ok(vols == [f"{copy}:/workdir/descargas"], f"docker: only the local copy is mounted ({vols})")
    ok("--env-file" not in a and ".env" not in s and "KEY" not in s and "gateways" not in s, "docker: no .env, keys or gateways")
    ok(a[a.index("--network") + 1] == "bridge" and "aibridge-hermes-agent:test" in a and "/root/.hermes/scripts/subs_new.py" in a,
       "docker: default bridge network, the stacks' image, subs_new.py")
    ok(os.path.isfile(os.path.join(d, "chan1_subs", "New video 0 [NEWVIDEO000].srt")), "push: the new subtitle reached the host")
    ok("WORKERVID00" in (read(os.path.join(d, "chan1_subs", ".nocaps.tsv")) or ""), "push: the newer scan state reached the host")
    ok(read(os.path.join(d, "chan1_subs", "Old [OLDOLDOLD01].srt")) == "old\n" and os.path.exists(os.path.join(d, "a-movie.mp4")),
       "push: nothing on the host was deleted or changed")
    names = [x["subject"].rsplit(".", 1)[-1] for x in e.events()]
    ok(all(n in names for n in ("pulled", "started", "done", "pushed")), f"events: pulled, started, done, pushed ({names})")

    # 3. asleep with a copy: runs on the last copy, outputs wait
    e.set("asleep")
    e.set("clash")
    e.set("notice")
    e.clear_logs()
    r = e.worker("run", "subs")
    ok(r.returncode == 0, "asleep with a copy: run exits 0")
    ok(any(x[0] == "run" for x in e.log("docker.log")), "asleep with a copy: the job runs on the last copy")
    ok(all(x["cmd"] == "true" for x in e.log("ssh.log")), "asleep with a copy: no rsync to the host")
    ok(not os.path.exists(os.path.join(d, "chan1_subs", "New video 1 [NEWVIDEO001].srt")), "asleep: the new subtitle waits")
    out = os.path.join(e.state, "stack-a", "subs", "outgoing")
    ok(os.path.isfile(os.path.join(out, "srt", "chan1_subs", "New video 1 [NEWVIDEO001].srt")) and os.listdir(os.path.join(out, "notices")),
       "asleep: subtitle and notice wait in outgoing/")
    ok(any(x["subject"] == "ev.worker.subs.notice" for x in e.events()), "a printed line is a notice event (count only)")

    # meanwhile the person's bot wrote the same name and a newer scan state on the host
    write(os.path.join(d, "chan1_subs", "Clash [CLASHCLASH1].srt"), "person\n")
    write(os.path.join(d, "chan1_subs", ".nocaps.tsv"), "person-nocaps\n", mtime=time.time() + 600)

    # 4. awake again: sync pushes, never over the person's newer files
    e.set("asleep", None)
    e.clear_logs()
    r = e.worker("sync")
    ok(r.returncode == 0, f"sync exits 0 ({r.stderr.strip()[-300:]})")
    ok(os.path.isfile(os.path.join(d, "chan1_subs", "New video 1 [NEWVIDEO001].srt")), "sync: the waiting subtitle reached the host")
    ok(read(os.path.join(d, "chan1_subs", "Clash [CLASHCLASH1].srt")) == "person\n", "sync: a subtitle the person has is never replaced")
    ok(read(os.path.join(d, "chan1_subs", ".nocaps.tsv")) == "person-nocaps\n", "sync: a newer scan state on the host is kept")
    notes = os.listdir(os.path.join(wd, ".worker-notices")) if os.path.isdir(os.path.join(wd, ".worker-notices")) else []
    ok(len(notes) == 1 and "aviso" in read(os.path.join(wd, ".worker-notices", notes[0])), "sync: the notice is a file in the workdir")
    ok(not any(f for _, _, f in os.walk(out)), "sync: outgoing/ is empty after the push")
    pushed = [x for x in e.events() if x["subject"] == "ev.worker.subs.pushed"]
    ok(pushed and pushed[-1]["data"].get("kept_host", 0) >= 2, "sync: the pushed event counts what the host kept")
    e.clear_logs()
    e.worker("sync")
    ok(e.log("ssh.log") == [], "sync with nothing waiting does not touch the host")

    # 5. apply through a one-shot container on the host (the default)
    e.config(apply="docker")
    e.set("clash", None)
    e.set("notice", None)
    e.clear_logs()
    r = e.worker("run", "subs")
    ok(os.path.isfile(os.path.join(d, "chan1_subs", "New video 2 [NEWVIDEO002].srt")), f"apply in a container: subtitle arrived ({r.stderr[-200:]})")
    ap = [x for x in e.log("docker.log") if "--entrypoint" in x and x[x.index("--entrypoint") + 1] == "python3"]
    ok(ap and ap[0][ap[0].index("--network") + 1] == "none" and "--rm" in ap[0], "apply container: --rm, no network")

    # 6. the hard timeout
    e.config(types={"subs": {"schedule": "hourly", "timeout_s": 2}, "jobnight": {"schedule": "daily"}})
    e.set("behavior", "hang")
    e.clear_logs()
    t0 = time.time()
    r = e.worker("run", "subs", "--stack", "stack-a", timeout=90)
    ok(r.returncode == 1 and time.time() - t0 < 60, f"timeout: the run ends with 1 in time ({time.time() - t0:.0f} s)")
    ok(any(x[0] == "kill" for x in e.log("docker.log")), "timeout: docker kill")
    ok(any(x["subject"] == "ev.worker.subs.failed" and x["data"].get("reason") == "timeout" for x in e.events()), "timeout: failed event")
    e.config()


def test_jobnight(e):
    wd = os.path.join(e.host, "stack-b", "workdir")
    jf = os.path.join(wd, "jobfinder")
    write(os.path.join(wd, ".prefs.json"), json.dumps({"avisos": "noche"}))
    for f in ("scan.mjs", "portals.yml", "config/profile.yml", "node_modules/dep/index.js", "output/cv.pdf", "reports/r.md"):
        write(os.path.join(jf, f), "x\n")
    pipeline = "# Pipeline\n- [ ] https://example.org/job/1 | Company A | Role one\n"
    write(os.path.join(jf, "data", "pipeline.md"), pipeline)
    host_state = json.dumps({"closing_told": ["k1"], "night_done": "2026-11-20", "failures": 0})
    write(os.path.join(jf, "data", ".jobpush-state.json"), host_state)
    waiting = {"since": 10, "last": 10, "runs": 1, "failed": 0, "checked": 0, "new": 1,
               "rows": [[{"url": "https://example.org/job/0", "title": "Role zero", "company": "Company Z"}, "ok", ""]]}
    write(os.path.join(jf, "data", ".jobpush-pending.json"), json.dumps(waiting))
    write(os.path.join(jf, "data", "scan-history.tsv"), "seed\n")
    e.set("behavior", "jobnight")
    e.clear_logs()
    r = e.worker("run", "jobnight")
    ok(r.returncode == 0, f"jobnight: run exits 0 ({r.stderr.strip()[-300:]})")
    local = os.path.join(e.state, "stack-b", "jobnight", "copy", "jobfinder")
    ok(os.path.isfile(os.path.join(local, "node_modules", "dep", "index.js")) and os.path.isfile(os.path.join(local, "data", "scan-history.tsv")),
       "jobnight pull: the jobfinder and its scan history are copied")
    ok(not os.path.exists(os.path.join(local, "output")) and not os.path.exists(os.path.join(local, "reports")),
       "jobnight pull: generated CVs and reports are not copied")
    env = json.load(open(os.path.join(e.ctl, "env.json")))
    ok(env.get("GATEWAYS_CONFIG", "").startswith("/worker/") and env.get("JOBPUSH_LANG") == "es"
       and "timezone: UTC" in (read(env.get("JOBPUSH_HERMES_CONFIG", "")) or ""), "jobnight container: no gateways (no key), zone from config")
    a = [x for x in e.log("docker.log") if x[0] == "run"][0]
    vols = [a[i + 1].split(":")[1] for i, x in enumerate(a) if x == "-v"]
    ok(sorted(vols) == sorted(["/workdir/jobfinder", "/workdir/.prefs.json", "/worker/hermes-config.yaml", "/workdir/.worker-out"]),
       f"jobnight container: only the jobfinder copy, prefs, zone and out are mounted ({vols})")
    ok(read(os.path.join(jf, "data", "pipeline.md")) == pipeline, "jobnight push: the person's pipeline.md is never written")
    ok(read(os.path.join(jf, "data", ".jobpush-state.json")) == host_state, "jobnight push: the host's state file is never written")
    p = json.load(open(os.path.join(jf, "data", ".jobpush-pending.json")))
    ok(p["runs"] == 2 and [r_[0]["url"] for r_ in p["rows"]] == ["https://example.org/job/0", "https://example.org/job/2"],
       "jobnight push: the summary is merged with the one still waiting on the host")
    sig = read(os.path.join(wd, ".early-signals.jsonl")) or ""
    ok(sig.count("scan_zero") == 1, "jobnight push: the early-alert line is appended")
    ok(os.path.isfile(os.path.join(jf, "output", "cv.pdf")), "jobnight push: nothing deleted on the host")

    # the person acknowledged on the host (told list) and handled nothing else; a second night on the same copy
    write(os.path.join(jf, "data", ".jobpush-state.json"), json.dumps({"closing_told": ["k1", "k2"], "night_done": "2026-11-20"}))
    e.set("behavior", "noop")
    r = e.worker("run", "jobnight")
    lp = read(os.path.join(local, "data", "pipeline.md")) or ""
    ok("job/1" in lp and lp.count("job/2") == 1, "jobnight pull: the worker's own new offers stay in the local pipeline (carry)")
    st = json.load(open(os.path.join(local, "data", ".jobpush-state.json")))
    ok("k2" in st.get("closing_told", []) and st.get("night_done") == "2026-11-26",
       "jobnight pull: told lists merged from the host, the worker's own night mark kept")


def test_events_clean(e):
    evs = e.events()
    import re
    bad = []
    for x in evs:
        if not re.match(r"^ev\.worker\.(subs|jobnight)\.[a-z_]+$", x["subject"]):
            bad.append(x["subject"])
        for k, v in x["data"].items():
            if isinstance(v, str) and (not re.match(r"^[a-z0-9_.:-]{1,64}$", v) or "chan1" in v or "example" in v or "/" in v):
                bad.append(f"{k}={v}")
    ok(evs and not bad, f"events: {len(evs)} lines, subjects ev.worker.<type>.<event>, no text or paths ({bad[:3]})")
    mode = os.stat(os.path.join(e.state, "events.jsonl")).st_mode & 0o777
    ok(mode == 0o600, f"events.jsonl is private (mode {oct(mode)})")


def main():
    test_validation()
    test_merge_pending()
    test_bus()
    if not shutil.which("rsync"):
        print("FAIL rsync is not installed: the worker needs it (apt install rsync)")
        return 1
    e = Env()
    try:
        e.config()
        test_subs(e)
        test_jobnight(e)
        test_events_clean(e)
    finally:
        shutil.rmtree(e.tmp, ignore_errors=True)
    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
