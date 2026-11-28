#!/usr/bin/env python3
"""Offline test of ops/deploy_log.py (BuildKit log timings, phase lines, the deploys.log lines old and new) and of ops/lib/pipeline_env.sh
(the untracked host settings file and the throwaway registry login). No docker, no ssh.

  python3 -I ops/deploy_log_selftest.py
"""
import atexit, json, os, shutil, subprocess, sys, tempfile
tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-"); atexit.register(shutil.rmtree, tempfile.tempdir, True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deploy_log as dl  # noqa: E402

ok = True
def chk(cond, what, extra=""):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what + ("" if cond else f"\n     {extra}"), flush=True)
tmp = tempfile.mkdtemp()

# ---- BuildKit plain logs (shapes copied from real builds)
TAR_LOG = """#200 [agent] exporting to docker image format
#200 exporting layers
#200 exporting layers 4.9s done
#200 exporting manifest sha256:e3db380bd25946687dda4ad45d36488ff1ced3ad4b47caa8863b416b8662878b 0.0s done
#200 exporting config sha256:a219981cf5ac1c94b7393ac5419229997f3859e1837abdb8cde3ed79707554a0 0.0s done
#200 sending tarball
#200 sending tarball 14.2s done
#200 DONE 19.2s
"""
PUSH_LOG = """#202 [agent] exporting to image
#202 exporting layers done
#202 exporting layers 5.0s done
#202 exporting manifest sha256:adc3 0.0s done
#202 pushing layers
#202 pushing layers 1.5s done
#202 pushing manifest for registry.example:5000/aibridge-hermes-agent:build-x@sha256:adc3
#202 pushing manifest for registry.example:5000/aibridge-hermes-agent:build-x@sha256:adc3 0.1s done
#202 DONE 6.7s
#55 [base 12/40] RUN apt-get install -y something 12.0s done
"""
chk(dl.buildkit_times(TAR_LOG) == {"export": 4.9, "push": 0.0, "tar": 14.2}, "buildkit: a tar build: export and tarball", dl.buildkit_times(TAR_LOG))
chk(dl.buildkit_times(PUSH_LOG) == {"export": 5.0, "push": 1.6, "tar": 0.0}, "buildkit: a push: layers + manifest; a build step's own time is not counted", dl.buildkit_times(PUSH_LOG))
chk(dl.buildkit_times("") == {"export": 0.0, "push": 0.0, "tar": 0.0}, "buildkit: an empty log is all zero")

# ---- phase lines
l = dl.phase_line("recreate", 74, at="2026-11-27T22:00:00-03:00", stack="s1", result="ok")
chk(l == "at=2026-11-27T22:00:00-03:00 name=recreate secs=74.0 stack=s1 result=ok", "phase_line: one parseable line", l)
chk(dl.parse_kv(l)["secs"] == "74.0", "parse_kv: reads it back")
chk(dl.fmt_kv([("note", "two words"), ("x", "")]) == "note=two_words x=-", "fmt_kv: a value is one word")
try:
    dl.fmt_kv([("bad key", 1)]); chk(False, "fmt_kv: a bad key is refused")
except ValueError:
    chk(True, "fmt_kv: a bad key is refused")

# ---- the deploy log: start, phases, the classic end line with the counts
log = os.path.join(tmp, "deploys.log"); phases = os.path.join(tmp, "phases")
OLD = ("1111111 main (pending: waker applies when idle) 2026-11-26T07:29Z\n"
       "2026-11-27T03:21:00Z 1234567 abcdef123456 all (x pending idle)\n"
       "2026-11-27T21:10:42-03:00 rev=2222222 prev=3333333 image=444444444444 host=u@h rc=3 pending=alpha beta gamma \n")
open(log, "w").write(OLD)
def cli(*a):
    return subprocess.run([sys.executable, "-I", os.path.join(HERE, "deploy_log.py"), *a], capture_output=True, text=True)
for args in (["phase", phases, "build", "15", "delivery=registry"], ["phase", phases, "push", "1.5"], ["phase", phases, "pull", "4.0"],
             ["phase", phases, "recreate", "80", "stack=a", "result=ok", "rc=0"], ["phase", phases, "health", "40", "stack=a"],
             ["phase", phases, "stop", "35", "stack=a", "result=stopped"], ["phase", phases, "recreate", "1", "stack=b", "result=awake", "rc=3"],
             ["phase", phases, "recreate", "90", "stack=c", "result=failed", "rc=1"], ["phase", phases, "total", "300"]):
    r = cli(*args); chk(r.returncode == 0, "cli phase " + " ".join(args[2:4]), r.stderr)
r = cli("start", log, "--id", "D1", "--build", "abc1234", "delivery=registry"); chk(r.returncode == 0, "cli start", r.stderr)
r = cli("finish", log, "--id", "D1", "--build", "abc1234", "--phases", phases, "--rev-line", "rev=abc1234 prev=2222222 image=111111111111 host=u@h rc=1",
        "--pending", "b x", "delivery=registry")
chk(r.returncode == 0, "cli finish (went through)", r.stderr)
text = open(log).read()
chk(text.startswith(OLD), "deploys.log: the old lines are kept as they were")
new = text[len(OLD):].splitlines()
chk(new[0].split()[1] == "deploy-start" and "build=abc1234" in new[0] and "rev=" not in new[0], "deploys.log: a start line, with no rev= key", new[0])
chk(sum(1 for x in new if x.split()[1] == "phase") == 9 and all("rev=" not in x for x in new[:-1]), "deploys.log: one line per phase, none with rev=")
last = new[-1]
chk(last.split()[1].startswith("rev=abc1234") and " prev=2222222 image=111111111111 host=u@h rc=1 " in last and last.endswith(" pending=b x"),
    "deploys.log: the classic line, pending= still the rest of the line", last)
kv = dl.parse_kv(last.partition(" pending=")[0])
chk((kv["recreated"], kv["skipped_awake"], kv["failed"], kv["results"], kv["total_s"], kv["id"]) == ("1", "1", "1", "a:ok,b:awake,c:failed", "300.0", "D1"),
    "deploys.log: the counts are what the deploy saw, stack by stack", kv)
deps = dl.parse_log(text)
chk([d["format"] for d in deps] == ["bare", "short", "classic", "phased"], "parse_log: the three older shapes and the new one", [d["format"] for d in deps])
d = deps[-1]
chk(d["rev"] == "abc1234" and d["rc"] == "1" and d["fields"]["pending"] == ["b", "x"] and len(d["phases"]) == 9, "parse_log: the new deploy with its phases and end line", d)
chk(deps[2]["fields"]["pending"] == ["alpha", "beta", "gamma"] and deps[2]["rev"] == "2222222", "parse_log: a classic line's pending list")
# the classic reader the deploy analysis used: lines whose second word starts with rev=
classic = [x for x in text.splitlines() if len(x.split()) > 1 and x.split()[1].startswith("rev=")]
chk(len(classic) == 2, "a reader of `<iso> rev=` lines sees one line per deploy, as before", classic)
# a deploy that did not go through
open(phases, "w").close(); cli("phase", phases, "deploy_ops", "5")
r = cli("finish", log, "--id", "D2", "--build", "def5678", "--phases", phases, "rc=1")
end = open(log).read().splitlines()[-1]
chk(r.returncode == 0 and end.split()[1] == "deploy-end" and "rc=1" in end and "rev=" not in end and "recreated=0" in end,
    "deploys.log: a failed deploy ends with deploy-end (no rev=: never mistaken for a deployed build)", end)
r = cli("show", "2", "--log", log)
chk(r.returncode == 0 and "abc1234" in r.stdout and "recreate" in r.stdout and "def5678" in r.stdout, "cli show: the last deploys with phases", r.stdout)

# ---- ops/lib/pipeline_env.sh
envf = os.path.join(tmp, "pipeline.env"); pw = os.path.join(tmp, "p.pass")
open(envf, "w").write('# host settings\nREGISTRY="reg.example:5000"\nAIBRIDGE_HOST=u@h\nPATH=/evil\nIMAGE_DELIVERY=both\n')
open(pw, "w").write("s3cr3t-value-123\n")
def sh(script, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("REGISTRY", "AIBRIDGE_HOST", "IMAGE_DELIVERY", "IMAGE_REPO", "PIPELINE_ENV")}
    e.update(BUILD_DIR=tmp, PIPELINE_ENV=envf, **env)
    return subprocess.run(["bash", "-c", f". {os.path.join(HERE, 'lib', 'pipeline_env.sh')}; " + script], capture_output=True, text=True, env=e)
r = sh('pipeline_env && echo "$REGISTRY|$AIBRIDGE_HOST|$IMAGE_DELIVERY|$IMAGE_REPO|$REGISTRY_PUSH_USER|$PATH"')
out = r.stdout.strip().split("|")
chk(r.returncode == 0 and out[:5] == ["reg.example:5000", "u@h", "both", "reg.example:5000/aibridge-hermes-agent", "pusher"] and out[5] != "/evil"
    and "ignoring PATH" in r.stderr, "pipeline_env: the file's settings, defaults, and PATH refused", (r.stdout, r.stderr))
r = sh('pipeline_env && echo "$REGISTRY|$IMAGE_DELIVERY"', REGISTRY="other:5000")
chk(r.stdout.strip() == "other:5000|both", "pipeline_env: the environment wins over the file", r.stdout)
open(envf, "w").write("")
r = sh('pipeline_env && echo "$IMAGE_DELIVERY|$IMAGE_REPO|"')
chk(r.returncode == 0 and r.stdout.strip() == "tar||", "pipeline_env: no registry -> the tar, as before", r.stdout)
r = sh('pipeline_env', IMAGE_DELIVERY="registry")
chk(r.returncode == 1 and "needs REGISTRY" in r.stderr, "pipeline_env: registry delivery without a registry is refused", r.stderr)
r = sh('pipeline_env', REGISTRY="bad host;rm")
chk(r.returncode == 1, "pipeline_env: an odd REGISTRY value is refused")
r = sh(f'pipeline_env && d=$(registry_auth_dir pusher {pw}) && cat "$d/config.json" && echo && stat -c %a "$d/config.json" && rm -rf "$d"', REGISTRY="reg.example:5000")
lines = r.stdout.strip().splitlines()
import base64
auth = json.loads(lines[0])["auths"]["reg.example:5000"]["auth"] if r.returncode == 0 else ""
chk(r.returncode == 0 and base64.b64decode(auth).decode() == "pusher:s3cr3t-value-123" and lines[1] == "600" and "s3cr3t" not in r.stderr,
    "registry_auth_dir: a 0600 client config with the login, the password read from its file and never printed", r.stdout + r.stderr)
r = sh(f'pipeline_env && registry_auth_dir pusher {tmp}/missing', REGISTRY="reg.example:5000")
chk(r.returncode != 0 and "not readable" in r.stderr, "registry_auth_dir: a missing password file is an error")

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
