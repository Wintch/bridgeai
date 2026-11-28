#!/usr/bin/env python3
"""After every batch of changes: one pass over what people use, compared with the last pass, so we know what is still broken and what
broke unexpectedly, and tell people about it (ops/feature_status.py) when the fix needs work we cannot do right now.

  ops/after_batch.py                 read-only checks of the Docker host, the wake service, the registry, and the GPU host if it is awake
  ops/after_batch.py --wake          also the wake drill: wake the GPU host through the wake service (timed), its gate, and back to sleep on its own
  ops/after_batch.py --wake --place NAME
                                     and open + close that place through the gate with its own token (timed; the desktop must answer)
  ops/after_batch.py --chat          also one short message to the guest stack's API (a real model call; a few tokens)

Each check prints ok / FAIL with a short detail. Against the previous pass (BUILD_DIR/out/after-batch.json) a failure is NEW (was ok:
the batch probably broke it), STILL (known), or a check is FIXED. A failure that matches a person-facing feature prints the
feature_status.py line to tell people, for the operator to run (or not). Exit 1 when anything NEW failed.

Host details stay out of the repo: the environment or the untracked BUILD_DIR/after_batch.env (KEY=VALUE, read, never run):
  AIBRIDGE_HOST     user@host of the Docker host
  GPU_HOST          user@host of the GPU host (ssh, passwordless sudo for reading a place's gate token)
  GPU_SSH_ALIAS     its HostKeyAlias, when the plain name has a stale key
  GPU_MACHINE       the GPU host's name at the wake service (default: the part after @ in GPU_HOST)
  GPU_ADDR          its LAN address (default: the part after @ in GPU_HOST)
  WAKE_URL          the wake service's base URL (…/despertar, …/estado)
  GATE_PORT         the GPU gate's port on the GPU host
  PLACES_DIR        where the places live on the GPU host (NAME/.gate.token)
  REGISTRY, REGISTRY_CA   as in ops/lib/pipeline_env.sh (BUILD_DIR/pipeline.env is read too)
  ARCHIVE_EXEMPT    stacks never flagged for 7 days without use (the operator's own, business bots whose crons are their work)
Never prints a token or a key: the place token is read and used on the GPU host itself, the guest's key on the Docker host itself.
"""
import argparse, datetime, json, os, re, shlex, subprocess, sys, time, urllib.request, ssl

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.environ.get("BUILD_DIR", "/mnt/nvme/bridgeai-build")
STATE = os.path.join(BUILD_DIR, "out", "after-batch.json")
KEYS = ("AIBRIDGE_HOST", "ARCHIVE_EXEMPT", "GPU_HOST", "GPU_SSH_ALIAS", "GPU_MACHINE", "GPU_ADDR", "WAKE_URL", "GATE_PORT", "PLACES_DIR", "REGISTRY", "REGISTRY_CA")
# a failing check -> the person-facing feature it means (ops/feature_status.py key) and a draft of the words people would read
FEATURE_OF = {"gpu.wake": ("escritorio", "El escritorio remoto no está arrancando la máquina por ahora."),
              "place.open": ("escritorio", "El escritorio remoto no abre por ahora."),
              "gpu.gate": ("escritorio", "El escritorio remoto y las funciones con placa de video no responden por ahora.")}


def settings():
    conf = {}
    for f in (os.path.join(BUILD_DIR, "pipeline.env"), os.path.join(BUILD_DIR, "after_batch.env")):
        try:
            for line in open(f):
                k, sep, v = line.strip().partition("=")
                if sep and k in KEYS and not line.lstrip().startswith("#"):
                    conf[k] = v.strip().strip('"').strip("'")
        except OSError:
            pass
    conf.update({k: os.environ[k] for k in KEYS if os.environ.get(k)})
    gh = conf.get("GPU_HOST", "")
    conf.setdefault("GPU_MACHINE", gh.partition("@")[2])
    conf.setdefault("GPU_ADDR", gh.partition("@")[2])
    conf.setdefault("REGISTRY_CA", os.path.join(BUILD_DIR, "registry/certs/ca.crt"))
    return conf


class Pass:
    def __init__(self):
        self.res = {}          # name -> (ok, detail)

    def add(self, name, ok, detail=""):
        self.res[name] = (bool(ok), str(detail)[:200])
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""), flush=True)


def ssh(target, script, alias=None, timeout=60, stdin=None):
    """Runs `script` with bash on the target; with `stdin`, `script` is the remote command line and `stdin` is fed to it."""
    remote = script if stdin is not None else "bash -s"
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"] + (["-o", f"HostKeyAlias={alias}"] if alias else []) + [target, remote]
    try:
        r = subprocess.run(cmd, input=stdin if stdin is not None else script, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def http(url, timeout=5, ctx=None):
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
            return r.status, r.read(200_000)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:      # noqa: BLE001 (any network failure is a FAIL line, never a crash)
        return 0, str(e).encode()


def parse_lines(out, p, prefix):
    """Remote scripts print `CHECK name ok|fail detail` lines."""
    for line in out.splitlines():
        m = re.match(r"CHECK (\S+) (ok|fail) ?(.*)$", line)
        if m:
            p.add(f"{prefix}.{m.group(1)}", m.group(2) == "ok", m.group(3))


DOCKER_HOST_SCRIPT = r'''
cd ~/aibridge || exit 1
latest=$(docker image inspect -f '{{.Id}}' aibridge-hermes-agent:latest 2>/dev/null | cut -c8-19)
python3 - "$latest" <<'PY'
import json, os, subprocess, sys, time
latest = sys.argv[1]
names = [s["name"] for s in json.load(open("ops/wake/stacks.json"))["stacks"]]
ps = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.State}}"], capture_output=True, text=True).stdout
rows = dict((l.split("\t")[0], l.split("\t")[1:]) for l in ps.splitlines() if l)
def img(c):
    return subprocess.run(["docker", "inspect", "-f", "{{.Image}}", c], capture_output=True, text=True).stdout.strip()[7:19]
for n in names:
    c = next((x for x in (f"stack-{n}-hermes", "aibridge-hermes-agent") if x in rows and (x != "aibridge-hermes-agent" or n == "hernik")), None)
    if not c:
        print(f"CHECK stack.{n} fail no brain container"); continue
    canary = os.path.exists(f"ops/wake/{n}.canary")
    pend = f"ops/wake/{n}.update_pending"
    age = time.time() - os.path.getmtime(pend) if os.path.exists(pend) else 0
    cur = img(c)
    if canary:
        print(f"CHECK stack.{n} ok canary-pinned ({cur})")
    elif cur == latest:
        print(f"CHECK stack.{n} ok latest {latest} ({rows[c][1]})")
    elif age and age < 6 * 3600:
        print(f"CHECK stack.{n} ok update pending {age / 60:.0f} min (the waker applies it when idle)")
    else:
        print(f"CHECK stack.{n} fail runs {cur}, latest is {latest}" + (f", update pending {age / 3600:.1f} h" if age else ", no update pending"))
for d in ["gateways-hernik"] + [f"stacks/{n}/gateways" for n in names if n != "hernik"]:
    p = os.path.join(d, "provider-status.json")
    if os.path.isdir(d):
        a = time.time() - os.path.getmtime(p) if os.path.exists(p) else None
        if a is None or a > 3600 * 6:
            print(f"CHECK provider_status.{d.split('/')[-2] if d.startswith('stacks') else 'hernik'} fail " + ("missing" if a is None else f"{a / 3600:.1f} h old"))
PY
st=$(systemctl --user is-active aibridge-waker.service); [ "$st" = active ] && echo "CHECK waker ok active" || echo "CHECK waker fail $st"
tb=$(journalctl --user -u aibridge-waker.service --since -2h --no-pager -o cat 2>/dev/null | grep -c Traceback)
[ "$tb" = 0 ] && echo "CHECK waker_tracebacks ok none in 2 h" || echo "CHECK waker_tracebacks fail $tb in 2 h"
failed=$(systemctl --user --failed --plain --no-legend 2>/dev/null | awk '{print $1}' | tr '\n' ' ')
# a timer's run that failed and was not retried yet: say when it last ran (a run cut by a deploy is not the same as a broken unit)
detail=""; for u in $failed; do detail="$detail $u($(systemctl --user show -p ActiveExitTimestamp --value "$u" 2>/dev/null | cut -c5-20))"; done
[ -z "$failed" ] && echo "CHECK user_units ok none failed" || echo "CHECK user_units fail$detail"
free=$(df -BG --output=avail / | tail -1 | tr -dc 0-9); [ "$free" -ge 25 ] && echo "CHECK disk ok ${free} GB free" || echo "CHECK disk fail ${free} GB free (< 25)"
la=$(cut -d' ' -f1 /proc/loadavg); echo "CHECK load ok $la"
# telemetry (and its Zabbix push): ran in the last 15 min, last run succeeded, no refused push in 30 min
tr=$(systemctl --user show telemetry.service -p Result --value 2>/dev/null)
te=$(date -d "$(systemctl --user show telemetry.service -p ExecMainExitTimestamp --value 2>/dev/null)" +%s 2>/dev/null || echo 0); ts=$te
age=$(( ($(date +%s) - ${te:-0}) / 60 ))   # wall clock: the host suspends, and a monotonic clock stops meanwhile
zf=$(journalctl --user -u telemetry.service --since -30min --no-pager -o cat 2>/dev/null | grep -c "Zabbix push")
if [ "$tr" = success ] && [ "${ts:-0}" -gt 0 ] && [ "$age" -le 15 ] && [ "$zf" = 0 ]; then echo "CHECK telemetry ok last run ${age} min ago, Zabbix push clean"
else echo "CHECK telemetry fail result=$tr last run ${age} min ago, ${zf} failed Zabbix push(es) in 30 min"; fi
# the keys page of every awake stack answers (keys_server.py on 8700 inside the brain; 403 from localhost is an answer)
for c in $(docker ps --format '{{.Names}}' | grep -E '^stack-.*-hermes$|^aibridge-hermes-agent$'); do
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" 2>/dev/null | grep -qx 'HERMES_KEYS_UI=1' || continue   # the page is on only there
  code=$(docker exec "$c" curl -s -m4 -o /dev/null -w '%{http_code}' http://localhost:8700/keys/ 2>/dev/null)
  [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = true ] || continue   # went to sleep meanwhile: nothing to say
  n=${c#stack-}; n=${n%-hermes}; [ "$c" = aibridge-hermes-agent ] && n=hernik
  case "$code" in 2??|3??|401|403) echo "CHECK keys_page.$n ok answers $code";; *) echo "CHECK keys_page.$n fail answered ${code:-nothing}";; esac
done
[ -x ops/feature_status.py ] || [ -f ops/feature_status.py ] && python3 ops/feature_status.py list | sed 's/^/KNOWN /'
# 7 days without use (the person's own messages, as the waker records them): alert, then archive (ops/ARCHIVE_INACTIVE.md). Stacks whose
# crons are their work, and the operator's own, are listed in ARCHIVE_EXEMPT (BUILD_DIR/after_batch.env), passed in as $1.
python3 - "${ARCHIVE_EXEMPT:-}" <<'PY'
import json, sys, time
exempt = set(sys.argv[1].split())
for s in json.load(open("ops/wake/stacks.json"))["stacks"]:
    n = s["name"]
    if n in exempt:
        continue
    try:
        h = json.load(open(f"ops/wake/{n}.state.json")).get("human_ts")
    except (OSError, ValueError):
        h = None
    if not isinstance(h, (int, float)) or h <= 0:
        print(f"CHECK inactive.{n} fail no use on record: alert, then archive (ARCHIVE_INACTIVE.md)")
    elif time.time() - h >= 7 * 86400:
        print(f"CHECK inactive.{n} fail {(time.time() - h) / 86400:.0f} days without use: alert, then archive (ARCHIVE_INACTIVE.md)")
    else:
        print(f"CHECK inactive.{n} ok used {(time.time() - h) / 86400:.0f} days ago")
PY
if docker ps --format '{{.Names}}' | grep -qx guest-prueba; then   # up to 60 s: a deploy may have just recreated it
  g=fail; for i in $(seq 1 20); do docker exec guest-prueba curl -sf -m3 http://localhost:8642/health >/dev/null 2>&1 && { g=ok; break; }; sleep 3; done
  [ "$g" = ok ] && echo "CHECK guest ok answers /health" || echo "CHECK guest fail no /health in 60 s"
fi
'''

GPU_SCRIPT = r'''
st=$(systemctl --user is-active bridgeai-gate 2>/dev/null); [ "$st" = active ] && echo "CHECK gate ok active" || echo "CHECK gate fail $st"
f=$(systemctl --failed --plain --no-legend 2>/dev/null | awk '{print $1}' | tr '\n' ' '); [ -z "$f" ] && echo "CHECK system_units ok none failed" || echo "CHECK system_units fail $f"
f=$(systemctl --user --failed --plain --no-legend 2>/dev/null | awk '{print $1}' | tr '\n' ' '); [ -z "$f" ] && echo "CHECK user_units ok none failed" || echo "CHECK user_units fail $f"
u=$(df --output=pcent / | tail -1 | tr -dc 0-9); [ "$u" -lt 80 ] && echo "CHECK root_disk ok ${u}% used" || echo "CHECK root_disk fail ${u}% used (keep under 80)"
systemctl is-active gpu-host-sleep.timer >/dev/null 2>&1 && echo "CHECK sleep_timer ok active" || echo "CHECK sleep_timer fail not active"
nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1 && echo "CHECK gpu ok $(nvidia-smi --query-gpu=power.draw,temperature.gpu --format=csv,noheader | tr -d ' ')" || echo "CHECK gpu fail nvidia-smi"
'''

PLACE_SCRIPT = r'''
P="$1"; PORT="$2"; DIR="$3"
T=$(sudo -n cat "$DIR/$P/.gate.token" 2>/dev/null) || { echo "CHECK place_token fail no token readable"; exit 0; }
g() { curl -s -m90 -X "$1" -H "Authorization: Bearer $T" "http://127.0.0.1:$PORT$2"; }
before=$(g GET /place/state | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state","?"))' 2>/dev/null)
if [ "$before" = running ]; then echo "CHECK open ok already open (in use: not touched)"; exit 0; fi
t0=$(date +%s%N); s=$(g POST /place/start)
echo "$s" | grep -q '"running": true' || { echo "CHECK open fail start answered: $(echo "$s" | head -c 120)"; exit 0; }
url=$(echo "$s" | python3 -c 'import json,sys; print(json.load(sys.stdin)["urls"]["https"])')
for i in $(seq 1 60); do c=$(curl -sk -m3 -o /dev/null -w '%{http_code}' "$url/"); [ "$c" != 000 ] && break; sleep 1; done
t1=$(( ($(date +%s%N)-t0)/1000000 ))
case "$c" in 200|401) echo "CHECK open ok desktop answers $c after ${t1} ms";; *) echo "CHECK open fail desktop answered $c after ${t1} ms";; esac
sleep 5; r=$(docker inspect -f '{{.RestartCount}} {{.State.Running}}' "${P}doc" 2>/dev/null)
[ "${r%% *}" = 0 ] && echo "CHECK steady ok no restart" || echo "CHECK steady fail $r"
t0=$(date +%s%N); s=$(g POST /place/stop); t2=$(( ($(date +%s%N)-t0)/1000000 ))
echo "$s" | grep -q '"running": false' && echo "CHECK close ok in ${t2} ms" || echo "CHECK close fail: $(echo "$s" | head -c 120)"
'''


DEPLOY_SCRIPT = r'''
SINCE="$1"; shift
cd ~/aibridge || exit 0
python3 - "$SINCE" "$@" <<'PY'
import json, os, subprocess, sys, time
since = int(sys.argv[1]); rec, awake = [], []
for a in sys.argv[2:]:
    (rec if a.startswith("ok:") else awake).append(a.split(":", 1)[1])
brains = {s["name"]: s.get("brain") or f"stack-{s['name']}-hermes" for s in json.load(open("ops/wake/stacks.json"))["stacks"]}
running = set(subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split())
log = subprocess.run(["journalctl", "--user", "-u", "aibridge-waker.service", "--since", f"@{since}", "--no-pager", "-o", "cat"],
                     capture_output=True, text=True).stdout.splitlines()
mins = (time.time() - since) / 60
for n in rec:
    mine = [l for l in log if f"[{n}]" in l]
    woke = [l for l in mine if " wake" in l or "woken" in l]
    if brains.get(n) not in running:
        print(f"CHECK deploy.asleep.{n} ok asleep again" + (" (woken since and back to sleep)" if woke else ""))
    elif woke:
        print(f"CHECK deploy.asleep.{n} ok up: woken since the deploy ({woke[-1].split('] ', 1)[-1][:60]})")
    else:
        print(f"CHECK deploy.asleep.{n} fail still up {mins:.0f} min after its recreate and nobody woke it")
for n in awake:
    mine = [l for l in log if f"[{n}]" in l]
    pend = os.path.exists(f"ops/wake/{n}.update_pending")
    if any("update applied" in l for l in mine):
        print(f"CHECK deploy.update.{n} ok update applied")
    elif any("update" in l and "fail" in l.lower() for l in mine):
        print(f"CHECK deploy.update.{n} fail the update failed (waker log)")
    elif pend and mins > 6 * 60:
        print(f"CHECK deploy.update.{n} fail still pending {mins / 60:.1f} h after the deploy")
    else:
        print(f"CHECK deploy.update.{n} ok " + ("pending (applied when the stack is idle)" if pend else "no update needed"))
PY
'''


def last_deploy(path=None):
    """(end epoch, ["ok:stack" | "awake:stack"]) of the newest deploy in deploys.log that recreated stacks, or None. Pure apart from the read."""
    path = path or os.path.join(BUILD_DIR, "out", "deploys.log")
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return None
    last_id, stacks, end = None, [], None
    for line in lines:
        m = re.search(r" id=(\S+) .*name=recreate .*stack=(\S+) result=(\w+)", line)
        if m:
            if m.group(1) != last_id:
                last_id, stacks = m.group(1), []
            if m.group(3) in ("ok", "awake"):
                stacks.append(f"{m.group(3)}:{m.group(2)}")
        m2 = re.search(r" id=(\S+) .*name=total ", line)
        if m2 and m2.group(1) == last_id:
            try:
                end = int(datetime.datetime.fromisoformat(line.split()[0]).timestamp())
            except ValueError:
                end = None
    return (end, stacks) if last_id and end and stacks else None


def check_registry(conf, p):
    if not conf.get("REGISTRY"):
        return
    ctx = ssl.create_default_context(cafile=conf["REGISTRY_CA"]) if os.path.exists(conf["REGISTRY_CA"]) else None
    if ctx:
        ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    code, _ = http(f"https://{conf['REGISTRY']}/v2/", ctx=ctx)
    p.add("registry", code in (200, 401), f"/v2/ answered {code}")


def gpu_awake(conf):
    return subprocess.run(["ping", "-c1", "-W1", conf["GPU_ADDR"]], capture_output=True).returncode == 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--wake", action="store_true")
    ap.add_argument("--place")
    ap.add_argument("--chat", action="store_true")
    a = ap.parse_args(argv)
    conf = settings()
    p = Pass()
    t_all = time.time()
    known = []
    if conf.get("AIBRIDGE_HOST"):
        rc, out, err = ssh(conf["AIBRIDGE_HOST"], f"ARCHIVE_EXEMPT={shlex.quote(conf.get('ARCHIVE_EXEMPT', ''))}\n" + DOCKER_HOST_SCRIPT, timeout=120)
        p.add("docker_host.ssh", rc == 0, err.strip()[-120:] if rc else "")
        parse_lines(out, p, "docker_host")
        known = [l[6:] for l in out.splitlines() if l.startswith("KNOWN ") and "no known problems" not in l]
        dep = last_deploy()
        if dep and time.time() - dep[0] < 12 * 3600:
            script = "set -- " + " ".join(shlex.quote(x) for x in (str(dep[0]), *dep[1])) + "\n" + DEPLOY_SCRIPT
            rc, out, err = ssh(conf["AIBRIDGE_HOST"], script, timeout=60)
            parse_lines(out, p, "docker_host")
        elif dep:
            print(f"      last deploy {(time.time() - dep[0]) / 3600:.0f} h ago: its recreates are not checked any more")
    if conf.get("WAKE_URL"):
        code, body = http(conf["WAKE_URL"].rstrip("/") + "/estado")
        try:
            ok = code == 200 and isinstance(json.loads(body), dict)
        except ValueError:
            ok = False
        p.add("wake_service", ok, f"/estado answered {code}")
    check_registry(conf, p)
    gh, alias = conf.get("GPU_HOST"), conf.get("GPU_SSH_ALIAS")
    if gh:
        awake = gpu_awake(conf)
        if a.wake and not awake and conf.get("WAKE_URL"):
            t0 = time.time()
            code, body = http(conf["WAKE_URL"].rstrip("/") + f"/despertar?maquina={conf['GPU_MACHINE']}&motivo=after-batch-check")
            ssh_s = None
            for _ in range(90):
                if ssh(gh, "true", alias, timeout=4)[0] == 0:
                    ssh_s = time.time() - t0
                    break
                time.sleep(1)
            p.add("gpu.wake", ssh_s is not None and ssh_s < 60, f"ssh after {ssh_s:.1f} s" if ssh_s else f"no ssh in 90 s (wake answered {code})")
            awake = ssh_s is not None
        if awake:
            rc, out, err = ssh(gh, GPU_SCRIPT, alias)
            parse_lines(out, p, "gpu")
            caps = os.path.join(os.path.dirname(os.path.dirname(HERE)), "gpu-host", "host_caps.py")
            if os.path.exists(caps):   # every place image against this host (REQUIREMENTS.md); an image without the label is only noted
                imgs = ssh(gh, "docker images --format '{{.Repository}}:{{.Tag}}' | grep '^bridgeai-place' | sort", alias)[1].split()
                if imgs:
                    rc, out, err = ssh(gh, "python3 - check " + " ".join(shlex.quote(i) for i in imgs), alias, timeout=60, stdin=open(caps).read())
                    for line in out.splitlines():
                        img, _, verdict = line.partition(": ")
                        p.add(f"gpu.requires.{img.split(':')[0]}", not verdict.startswith("MISSING"), verdict)
            if a.place and conf.get("GATE_PORT") and conf.get("PLACES_DIR"):
                script = "set -- " + " ".join(shlex.quote(x) for x in (a.place, conf["GATE_PORT"], conf["PLACES_DIR"])) + "\n" + PLACE_SCRIPT
                rc, out, err = ssh(gh, script, alias, timeout=240)
                parse_lines(out, p, "place")
        else:
            print("      gpu host asleep: not checked (--wake to wake it)")
    if a.chat and conf.get("AIBRIDGE_HOST"):
        script = r'''cd ~/aibridge/guests/prueba && K=$(grep -i "API key" credentials.txt | head -1 | sed "s/.*: *//" | tr -d " ") && U=$(grep -oE "http://[0-9.]+:[0-9]+/v1" credentials.txt | head -1) &&
s=$(date +%s%N); r=$(curl -s -m120 -H "Authorization: Bearer $K" -H "Content-Type: application/json" -d '{"model":"hermes-agent","messages":[{"role":"user","content":"Respondé solo: ok"}]}' "$U/chat/completions"); t=$(( ($(date +%s%N)-s)/1000000 ))
echo "$r" | grep -q '"content"' && echo "CHECK chat ok answered in ${t} ms" || echo "CHECK chat fail no answer in ${t} ms"'''
        rc, out, err = ssh(conf["AIBRIDGE_HOST"], script, timeout=150)
        parse_lines(out, p, "guest")

    try:
        prev = json.load(open(STATE)).get("res", {})
    except (OSError, ValueError):
        prev = {}
    new = [n for n, (ok, _) in p.res.items() if not ok and prev.get(n, [True])[0]]
    still = [n for n, (ok, _) in p.res.items() if not ok and n in prev and not prev[n][0]]
    fixed = [n for n, (ok, _) in p.res.items() if ok and n in prev and not prev[n][0]]
    print(f"\n{len(p.res)} checks in {time.time() - t_all:.0f} s: {sum(1 for ok, _ in p.res.values() if ok)} ok, "
          f"{len(new)} NEW failure(s), {len(still)} still failing, {len(fixed)} fixed")
    for label, names in (("NEW (probably this batch)", new), ("STILL failing", still), ("FIXED", fixed)):
        if names:
            print(f"  {label}: {', '.join(names)}")
    if known:
        print("  known problems people are told about:\n    " + "\n    ".join(known))
    for n in new + still:
        for prefix, (key, es) in FEATURE_OF.items():
            if n.startswith(prefix) and not any(k.startswith(key + ":") for k in known):
                print(f"  to tell people (if the fix has to wait): ssh $AIBRIDGE_HOST 'cd ~/aibridge && python3 ops/feature_status.py set {key} "
                      f"--state off --es {shlex.quote(es)}'")
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE + ".n", "w") as f:
        json.dump({"at": int(time.time()), "res": {n: list(v) for n, v in p.res.items()}}, f, indent=1)
    os.replace(STATE + ".n", STATE)
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
