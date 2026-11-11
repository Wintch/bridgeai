#!/usr/bin/env python3
"""Offline checks for ops/job_summary.py: a fake `docker` that runs the real jobpush.py on a temp jobfinder, and a fake Telegram Bot API
(no network, no containers). Run: python3 -I ops/job_summary_selftest.py"""
import contextlib, importlib.util, io, json, os, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FAIL, SENT = [], []
STATUS = {"ok": True}


def check(name, got, want):
    if got != want:
        FAIL.append(f"{name}: got {got!r}, want {want!r}")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SENT.append({"path": self.path, **body})
        out = json.dumps({"ok": STATUS["ok"], "result": {"message_id": len(SENT)}}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = tempfile.mkdtemp(prefix="js-")
os.makedirs(os.path.join(base, "ops", "wake"))
envf = os.path.join(base, "tg.env")
open(envf, "w").write("TELEGRAM_BOT_TOKEN=123:SECRET-TOKEN\nTELEGRAM_ALLOWED_USERS=777\n")
json.dump({"stacks": [{"name": "ana", "brain": "stack-ana-hermes", "telegram_env": envf},
                      {"name": "old", "brain": "stack-old-hermes", "telegram_env": envf}]}, open(os.path.join(base, "ops", "wake", "stacks.json"), "w"))
# the person's jobfinder with a summary waiting (written by the real jobpush.py code)
jf = os.path.join(base, "jf")
os.makedirs(os.path.join(jf, "data"))
bindir = os.path.join(base, "bin")
os.makedirs(bindir)
open(os.path.join(bindir, "docker"), "w").write(f"""#!/bin/sh
# docker exec BRAIN python3 SCRIPT ARGS...: the "old" stack has an image without --pending
[ "$1" = exec ] || exit 9
[ "$2" = stack-old-hermes ] && {{ echo "usage" >&2; exit 2; }}
shift 4
echo "$@" >> {base}/docker.log
exec {sys.executable} -I {REPO}/jobpush.py "$@"
""")
os.chmod(os.path.join(bindir, "docker"), 0o755)
os.environ.update(DAILY_AD_DIR=base, DAILY_AD_API_BASE=f"http://127.0.0.1:{srv.server_address[1]}", JOB_SUMMARY_LOG=os.path.join(base, "js.log"),
                  PATH=bindir + os.pathsep + os.environ["PATH"], JOBPUSH_ROOT=jf, JOBPUSH_PREFS=os.path.join(base, "prefs.json"),
                  GATEWAYS_CONFIG=os.path.join(base, "gw.json"))
spec = importlib.util.spec_from_file_location("jp", os.path.join(REPO, "jobpush.py"))
jp = importlib.util.module_from_spec(spec); spec.loader.exec_module(jp)
spec = importlib.util.spec_from_file_location("js", os.path.join(HERE, "job_summary.py"))
js = importlib.util.module_from_spec(spec); spec.loader.exec_module(js)
cfg = dict(jp.settings(), dry=False)
OFFER = {"url": "https://example.com/jobs/1", "company": "Studio One", "title": "Environment Artist"}


def waiting():
    jp.pending_add(cfg, ok=True, checked=100, new_n=1, rows=[(OFFER, "ok", "")])


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = js.main(list(argv))
    return rc, buf.getvalue()


check("nothing waiting: nothing sent", (run("wake", "--stack", "ana", "--chat", "777", "--delay", "0")[0], len(SENT)), (0, 0))
waiting()
check("a cron wake sends nothing", (run("wake", "--stack", "ana", "--chat", "777", "--reason", "cron", "--delay", "0")[0], len(SENT)), (0, 0))
check("another chat id is refused", (run("wake", "--stack", "ana", "--chat", "999", "--delay", "0")[0], len(SENT)), (2, 0))
rc, out = run("peek", "--stack", "ana")
check("operator peek: counts only, never the text", (rc, "summary is waiting" in out, "Studio" in out), (0, True, False))
STATUS["ok"] = False
check("a failed send keeps the summary", (run("wake", "--stack", "ana", "--chat", "777", "--delay", "0")[0],
                                          os.path.exists(os.path.join(jf, "data", ".jobpush-pending.json"))), (1, True))
STATUS["ok"] = True
SENT.clear()
rc, _ = run("wake", "--stack", "ana", "--chat", "777", "--delay", "0")
check("a Telegram wake sends the summary once to the person", (rc, len(SENT), SENT[-1]["chat_id"] if SENT else None), (0, 1, "777"))
m = SENT[-1]
check("the summary text, plain, previews off", (m["text"].splitlines()[0], "Environment Artist — Studio One" in m["text"], m["link_preview_options"]),
      ("Revisión de ofertas de anoche:", True, {"is_disabled": True}))
check("confirmed after the send: nothing waits, push-last.md written",
      (os.path.exists(os.path.join(jf, "data", ".jobpush-pending.json")), os.path.exists(os.path.join(jf, "data", "push-last.md"))), (False, True))
check("a second wake sends nothing", (run("wake", "--stack", "ana", "--chat", "777", "--delay", "0")[0], len(SENT)), (0, 1))
check("an old image (no --pending) is skipped quietly", run("wake", "--stack", "old", "--chat", "777", "--delay", "0")[0], 0)
check("an unknown stack is skipped", run("wake", "--stack", "nobody", "--chat", "777", "--delay", "0")[0], 0)
log = open(os.path.join(base, "js.log")).read()
check("the log has no token and no offer text", ("SECRET" in log, "Studio" in log, "event=sent" in log), (False, False, True))
hook = os.path.join(HERE, "wake", "on_wake.d", "50-job-summary")
check("the hook is executable and quiet for a cron wake",
      (os.access(hook, os.X_OK), subprocess.run([hook], env=dict(os.environ, WAKE_REASON="cron", WAKE_NAME="ana", WAKE_CHAT_ID="777")).returncode), (True, 0))

print("\n".join(FAIL) or "job_summary_selftest: all checks passed")
sys.exit(1 if FAIL else 0)
