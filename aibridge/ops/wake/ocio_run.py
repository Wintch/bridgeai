#!/usr/bin/env python3
"""Start ONE idle-time unit on a stack's bot (called by the waker, ocio_wake.py decides when; design: HERMES_ARCHITECTURE.md "Idle-time work").

  python3 ops/wake/ocio_run.py --stack NAME            ask the stack's own Hermes API for a run with a FIXED prompt; print nothing else
  python3 ops/wake/ocio_run.py --stack NAME --check    running | finished | unknown for the recorded run

The prompt carries no text of the queue: the bot reads its own queue with `gateway ocio siguiente`. It starts with "[SYSTEM: idle-time work run ...]", the
line the router's human_turn() skips, so an idle-time run never counts as the person using the stack (it would keep a warm stack awake) and the router
recognises it (a token budget, never a question about the cloud). The run record <stack>.ocio.run.json holds the run id and the start time only.
Exit codes: 0 started (or checked), 1 could not start (the waker waits retry_seconds).
Reuses tareas_run.py's API calls (the address and the key are found the same way, the key never printed).
"""
import argparse, importlib.util, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("tareas_run", os.path.join(HERE, "tareas_run.py"))
tr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tr)

TAG = "[SYSTEM: idle-time work run started by the waker, not a message from the person]\n"
PROMPT = (TAG + "There may be idle-time work. Run `gateway ocio siguiente`. If it says NADA, answer with one word and stop. Otherwise do ONLY that one unit "
          "and save its result with `gateway ocio hecho` (or `gateway ocio bloquear` if it cannot be done), following the ocio skill. Never publish, send, "
          "spend or delete anything in this run. Your answer is not shown to anyone: one short line.")


def record_path(name):
    return os.path.join(tr.STATE_DIR, f"{name}.ocio.run.json")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stack", required=True)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if not tr.STACK_RE.match(a.stack):
        sys.exit("bad stack name")
    test_url = os.environ.get("TAREAS_RUN_TEST_URL")
    conf = None if test_url else tr.stack_conf(a.stack)
    if conf is None and not test_url:
        tr.log(f"[{a.stack}] not in {tr.CONFIG}")
        return 1
    urls = (lambda: [test_url]) if test_url else (lambda: tr.container_urls(conf["brain"], str(conf.get("brain_api_port", 8642))))
    key = (lambda: os.environ.get("TAREAS_RUN_TEST_KEY", "")) if test_url else (lambda: tr.container_key(conf["brain"]))
    if a.check:
        try:
            rid = str(json.load(open(record_path(a.stack))).get("run_id") or "")
        except (OSError, ValueError, AttributeError):
            rid = ""
        print(tr.run_state(urls(), key(), rid) if rid else "unknown")
        return 0
    k, u = key(), urls()
    rid, err = (None, "no API key found in the container") if not k else ((None, "no address for the container") if not u else tr.start_run(u, k, PROMPT))
    if rid is None:
        tr.log(f"[{a.stack}] idle-time run NOT started ({err})")
        return 1
    tr.write_request(record_path(a.stack), {"stack": a.stack, "run_id": rid, "started": time.time()})
    tr.log(f"[{a.stack}] idle-time run started{' ' + rid if rid else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
