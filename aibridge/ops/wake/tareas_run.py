#!/usr/bin/env python3
"""Start ONE run of a stack's bot for a task on the Gitea board (called by on_wake.d/40-task-run; design: ops/wake/TAREAS_HOOK.md).

  python3 ops/wake/tareas_run.py --stack NAME

Reads <stack>.task.json (written by tareas_hook.py), asks the stack's own Hermes API (POST /v1/runs, Bearer key) to start a run with
a FIXED prompt and returns as soon as the API accepted it: it never waits for the run and never reads its output. The text of the
issue never travels here: the bot fetches it itself with `gateway tareas ver`, which quotes it as data.

Where the call goes: the brain container's bridge address (docker inspect) on its API port (stacks.json brain_api_port, default
8642), the same way the waker probes it. The key is read from the container (/root/.hermes/.env API_SERVER_KEY, else the
HERMES_API_KEY of its environment) and lives only in this process: it is never printed, logged, or put in an argument list.

The run record: once the API accepted the run, <stack>.task.run.json (run id and start time, never a key or a text) is written next to the
request. The waker counts a stack with a record as busy while the run is not finished (it asks `--check`, below), so neither the idle sleep
nor the RAM guard's eviction cuts a long task. `--stack NAME --check` prints one word,
running | finished | unknown, from GET /v1/runs/<id> (field names are a guess, see TAREAS_HOOK.md: anything it cannot read is "unknown").

Exit codes (the waker's hook contract): 0 the run was accepted, or there was nothing to do; 1 it could not be started and the request
was kept for a later try (not_before moves 5 minutes on); 2 it failed 3 times and the request was dropped (the waker raises an ops
alert). The task itself stays open on the board either way.
Tests only: TAREAS_RUN_TEST_URL and TAREAS_RUN_TEST_KEY replace the container lookups.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("WAKE_STATE_DIR", HERE)
CONFIG = os.environ.get("WAKE_CONFIG", os.path.join(HERE, "stacks.json"))
# One run serves the whole request: a burst of tasks is ONE request and no later delivery will come for tasks 2..N, so the prompt says to
# empty the list, oldest first. A task the bot cannot finish goes to "bloqueado" with its reason (that takes it off the pending list),
# so the loop ends.
PROMPT = ("Tenés tareas nuevas en el tablero. Revisalas con gateway tareas listar --mias y trabajá todas las pendientes, una por una, "
          "de la más vieja a la más nueva, según la skill tareas, hasta que no quede ninguna pendiente. Dejá el resultado de cada una en su "
          "tarea; la que no puedas terminar, dejala en bloqueado con el motivo y seguí con la siguiente. Tu respuesta final le llega a la "
          "persona por Telegram: terminá con 2 a 4 líneas sobre qué hiciste y qué espera su OK.")
# A task THIS bot filed came back (closed, or left bloqueado): the request lists it under "done" (tareas_hook.py 6b). Only numbers travel.
DONE_PROMPT = ("Volvió el resultado de tareas que pediste vos en el tablero: {nums}. Leé cada una con gateway tareas ver N (el resultado está "
               "en su cierre y sus comentarios) y seguí con lo que te toque a vos con ese resultado, según la skill tareas. Lo que publique, "
               "gaste, borre o le escriba a terceros dejalo listo para la aprobación de la persona, como siempre. No las reabras ni las "
               "reasignes por tu cuenta. No rehagas el trabajo del otro bot: usá su resultado. Tu respuesta final le llega a la persona por "
               "Telegram: terminá con 2 a 4 líneas sobre qué cambia con ese resultado y qué espera su OK.")
STACK_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


def prompt_for(req):
    """The fixed prompt for one request: the work prompt when it has tasks to work (or no "done" part), the result prompt for what came back,
    both when it has both. Only integers from the request reach the text."""
    issues = [n for n in (req.get("issues") or []) if isinstance(n, int) and not isinstance(n, bool)]
    done = sorted({d["n"] for d in (req.get("done") or []) if isinstance(d, dict) and isinstance(d.get("n"), int)
                   and not isinstance(d.get("n"), bool) and 0 < d["n"] < 10 ** 9})
    parts = []
    if issues or not done:
        parts.append(PROMPT)
    if done:
        parts.append(DONE_PROMPT.format(nums=", ".join(f"#{n}" for n in done[:20])))
    return " ".join(parts)
RETRY_S = 300
MAX_ATTEMPTS = 3
TIMEOUT_S = 20
ENV_IN_CONTAINER = "/root/.hermes/.env"
RUNNING = {"queued", "pending", "started", "running", "in_progress", "in-progress", "active"}
FINISHED = {"completed", "complete", "finished", "done", "succeeded", "success", "failed", "error", "cancelled", "canceled", "stopped", "timeout"}


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "tareas_run:", msg, flush=True)


def docker(*args, timeout=30):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def stack_conf(name):
    for c in json.load(open(CONFIG)).get("stacks", []):
        if c.get("name") == name:
            return c
    return None


def container_key(brain):
    """The API key of the brain container: its own .env first (what the API server reads), else its HERMES_API_KEY. "" when neither."""
    try:
        r = docker("exec", brain, "cat", ENV_IN_CONTAINER)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                k, sep, v = line.partition("=")
                if sep and k.strip() == "API_SERVER_KEY" and v.strip().strip('"').strip("'"):
                    return v.strip().strip('"').strip("'")
        r = docker("exec", brain, "printenv", "HERMES_API_KEY")
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def container_urls(brain, port):
    try:
        r = docker("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", brain)
    except (OSError, subprocess.SubprocessError):
        return []
    return [f"http://{ip}:{port}" for ip in r.stdout.split()] if r.returncode == 0 else []


def start_run(urls, key, prompt=PROMPT):
    """POST /v1/runs on the first address that answers. -> (run id or "" when the answer carries none, error text or ""). The key is not in any message."""
    body = json.dumps({"input": prompt}).encode()
    err = "no address to call"
    for base in urls:
        req = urllib.request.Request(base + "/v1/runs", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                raw = resp.read(65536)
                if resp.status not in (200, 201, 202):
                    err = f"API answered {resp.status}"
                    continue
        except urllib.error.HTTPError as e:
            err = f"API answered {e.code}"
            continue
        except (OSError, ValueError) as e:
            err = f"cannot reach the API ({type(e).__name__})"
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            d = {}
        rid = d.get("run_id") or d.get("id") if isinstance(d, dict) else None
        return (str(rid)[:80] if rid else ""), ""
    return None, err


def write_request(path, req):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(req, f)
    os.replace(tmp, path)


def run_record_path(name):
    return os.path.join(STATE_DIR, f"{name}.task.run.json")


def run_state(urls, key, rid):
    """GET /v1/runs/<id> on the first address that answers -> "running", "finished" or "unknown" (no id, no answer, a field it does not know)."""
    if not rid or not key or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", rid):
        return "unknown"
    for base in urls:
        req = urllib.request.Request(f"{base}/v1/runs/{rid}", headers={"Authorization": "Bearer " + key})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                d = json.loads(resp.read(65536))
        except (OSError, ValueError):   # includes HTTPError and URLError
            continue
        if isinstance(d, dict):
            st = d.get("status") if isinstance(d.get("status"), str) else (d.get("state") if isinstance(d.get("state"), str) else "")
            st = st.strip().lower()
            if st in FINISHED:
                return "finished"
            if st in RUNNING:
                return "running"
        return "unknown"
    return "unknown"


def run_report(urls, key, rid):
    """GET /v1/runs/<id> -> (status word or "", the run's final answer or ""). Hermes puts the final response in "output" once the run is terminal."""
    if not rid or not key or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", rid):
        return "", ""
    for base in urls:
        req = urllib.request.Request(f"{base}/v1/runs/{rid}", headers={"Authorization": "Bearer " + key})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                d = json.loads(resp.read(262144))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            st = d.get("status") if isinstance(d.get("status"), str) else ""
            out = d.get("output") if isinstance(d.get("output"), str) else ""
            return st.strip().lower(), out
        return "", ""
    return "", ""


def report_text(output, cap=3500):
    """The run's answer as one Telegram message: MEDIA: lines become "(adjunto: name)" (the file stays with the bot), cut to `cap`."""
    lines = []
    for line in (output or "").replace("\r\n", "\n").split("\n"):
        m = re.match(r"^\s*MEDIA:\s*(\S+)", line)
        lines.append(f"(adjunto: {os.path.basename(m.group(1))})" if m else line)
    text = "\n".join(lines).strip()
    return text if len(text) <= cap else text[:cap].rstrip() + " …"


def check_run(name, urls_fn, key_fn):
    """--check: what the run recorded for `name` is doing. "finished" for no record is wrong (the waker owns removing it), so "unknown"."""
    try:
        rec = json.load(open(run_record_path(name)))
        rid = str(rec.get("run_id") or "")
    except (OSError, ValueError, AttributeError):
        return "unknown"
    return run_state(urls_fn(), key_fn(), rid) if rid else "unknown"


def run_for(name, urls_fn=None, key_fn=None):
    """-> exit code. urls_fn/key_fn are looked up lazily so a stack with no request costs no docker call."""
    path = os.path.join(STATE_DIR, f"{name}.task.json")
    try:
        raw = open(path, "rb").read(65536)
        req = json.loads(raw)
    except FileNotFoundError:
        log(f"[{name}] no task request: nothing to do")
        return 0
    except (OSError, ValueError):
        log(f"[{name}] task request unreadable: left for the waker to drop")
        return 1
    if not isinstance(req, dict):
        return 1
    urls, key = urls_fn(), key_fn()
    if not key:
        rid, err = None, "no API key found in the container"
    elif not urls:
        rid, err = None, "no address for the container"
    else:
        rid, err = start_run(urls, key, prompt_for(req))
    if rid is not None:
        log(f"[{name}] run started{' ' + rid if rid else ''} for {len(req.get('issues') or [])} task(s) and {len(req.get('done') or [])} result(s) (count {req.get('count', '?')})")
        try:   # before the request goes away, so the receiver never sees "neither a request nor a run" while the bot works
            write_request(run_record_path(name), {"stack": name, "run_id": rid, "started": time.time()})
        except OSError:
            pass
        try:
            if open(path, "rb").read(65536) == raw:   # a merged task changes the content (its count), whatever the timestamps say
                os.unlink(path)
            else:   # the receiver added a task while the run was starting: keep it, run again later
                req = json.load(open(path))
                req.pop("attempts", None)   # this run started fine: the failures before it do not count against the next one
                req["not_before"] = time.time() + 120
                write_request(path, req)
        except (OSError, ValueError):
            pass
        return 0
    return record_failure(name, path, req, err)


def record_failure(name, path, req, err):
    """Count one failed start in the request file: -> 1 (kept, next try in RETRY_S) or 2 (third failure: dropped, the waker alerts)."""
    attempts = int(req.get("attempts", 0) or 0) + 1
    if attempts >= MAX_ATTEMPTS:
        log(f"[{name}] run NOT started after {attempts} tries ({err}): request dropped, the task stays on the board")
        try:
            os.unlink(path)
        except OSError:
            pass
        return 2
    req["attempts"], req["not_before"] = attempts, time.time() + RETRY_S
    try:
        write_request(path, req)
    except OSError:
        pass
    log(f"[{name}] run NOT started ({err}): try {attempts} of {MAX_ATTEMPTS}, next in {RETRY_S}s")
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stack", required=True)
    ap.add_argument("--check", action="store_true", help="print running|finished|unknown for the run recorded for the stack, start nothing")
    ap.add_argument("--report", action="store_true", help="print one JSON line {status, text}: the recorded run's final answer for the person")
    a = ap.parse_args(argv)
    if not STACK_RE.match(a.stack):
        sys.exit("bad stack name")
    try:
        return main_run(a)
    except Exception as e:   # an uncaught crash must count as a failed try, not leave a request that wakes the stack forever (the waker caps too)
        log(f"[{a.stack}] crashed ({type(e).__name__}): counted as a failed try")
        if a.check or a.report:
            print("unknown" if a.check else json.dumps({"status": "", "text": ""}))
            return 0
        path = os.path.join(STATE_DIR, f"{a.stack}.task.json")
        try:
            req = json.load(open(path))
        except (OSError, ValueError):
            return 1
        return record_failure(a.stack, path, req, f"crash {type(e).__name__}") if isinstance(req, dict) else 1


def main_run(a):
    conf = None
    test_url = os.environ.get("TAREAS_RUN_TEST_URL")
    if not test_url:
        conf = stack_conf(a.stack)
        if conf is None:
            log(f"[{a.stack}] not in {CONFIG}")
            return 1
    urls_fn = (lambda: [test_url]) if test_url else (lambda: container_urls(conf["brain"], str(conf.get("brain_api_port", 8642))))
    key_fn = (lambda: os.environ.get("TAREAS_RUN_TEST_KEY", "")) if test_url else (lambda: container_key(conf["brain"]))
    if a.check:
        print(check_run(a.stack, urls_fn, key_fn))
        return 0
    if a.report:
        try:
            rid = str(json.load(open(run_record_path(a.stack))).get("run_id") or "")
        except (OSError, ValueError, AttributeError):
            rid = ""
        st, out = run_report(urls_fn(), key_fn(), rid) if rid else ("", "")
        print(json.dumps({"status": st, "text": report_text(out)}, ensure_ascii=False))
        return 0
    return run_for(a.stack, urls_fn, key_fn)


if __name__ == "__main__":
    sys.exit(main())
