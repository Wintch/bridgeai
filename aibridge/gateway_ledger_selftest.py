#!/usr/bin/env python3
"""Offline checks that gateway's long verbs write their own start and end in the work ledger (trabajos.py), attach to a queued entry,
leave no trace when refused, and never fail because of the ledger. Fake video host, like gateway_makevideo_selftest.py.
Run: python3 -I gateway_ledger_selftest.py"""
import contextlib, importlib.util, io, json, os, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
WORK = os.path.join(tmp, "workdir")
os.makedirs(os.path.join(WORK, "descargas"))
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"fakeframes" * 30
state = {"mode": "ok"}
FAIL = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        FAIL.append(name)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self.send_response(200 if self.path == "/healthz" else 404); self.send_header("Content-Length", "8"); self.end_headers(); self.wfile.write(b"ok video")

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if state["mode"] == "ok":
            self.send_response(200); self.send_header("Content-Type", "video/mp4"); self.send_header("Content-Length", str(len(MP4)))
            self.send_header("X-Video-Seconds", "12.0"); self.send_header("X-Video-Seed", "7"); self.send_header("X-Video-Length", "3")
            self.end_headers(); self.wfile.write(MP4)
        else:
            self.send_response(int(state["mode"])); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"no")


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}"
cfgp, logp = os.path.join(tmp, "gateways.json"), os.path.join(tmp, "log.jsonl")
json.dump({"video": [{"name": "gpu-a", "url": url}]}, open(cfgp, "w"))
os.environ.update(GATEWAYS_CONFIG=cfgp, GATEWAY_LOG=logp, GATEWAY_WORKDIR=WORK, AIBRIDGE_DOWNLOADS=os.path.join(WORK, "descargas"), TRABAJOS_DIR=os.path.join(tmp, "ledger"),
                  TRABAJOS_MODULE=os.path.join(HERE, "trabajos.py"), AIBRIDGE_PREFS=os.path.join(tmp, "prefs.json"))
os.environ.pop("TRABAJO_ID", None)


def load_gateway():
    spec = importlib.util.spec_from_file_location("gw", os.path.join(HERE, "gateway.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    m.VIDEO_QUEUE_WAIT = 0
    return m


gw = load_gateway()
tj = gw.ledger()
check("the gateway loads trabajos.py (TRABAJOS_MODULE, else /usr/local/bin/trabajos, else the repo copy)", tj is not None and tj.ROOT == os.environ["TRABAJOS_DIR"])


def run(argv, env=None):
    old_argv, old_env = sys.argv, {k: os.environ.get(k) for k in (env or {})}
    sys.argv = ["gateway"] + argv
    os.environ.update(env or {})
    buf, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            try:
                rc = gw.main()
            except SystemExit as e:
                rc = e.code
    finally:
        sys.argv = old_argv
        for k, v in old_env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return rc, buf.getvalue() + err.getvalue()


def entries():
    return tj.load()["entries"]


out1 = os.path.join(WORK, "descargas", "alfa.mp4")
rc, txt = run(["makevideo", "--secs", "5", "--", "a dog on the beach at sunset with waves", out1])
es = entries()
check("a long verb writes one entry: listo, exit 0, with its output and the pid of the command", rc == 0 and len(es) == 1 and es[0]["state"] == "listo"
      and es[0]["exit_code"] == 0 and es[0]["outputs"] == [out1] and es[0]["pid"] == os.getpid() and es[0]["started"] and es[0]["ended"], str(es))
check("label: the file's name and the head of the prompt; kind video; the command is kept (masked, 300 at most)",
      es[0]["label"] == "alfa: a dog on the beach at sunset with waves"[:46] and es[0]["kind"] == "video" and es[0]["command"].startswith("gateway makevideo --secs 5 --")
      and len(es[0]["command"]) <= 300, es[0]["label"])
check("the command's own output is unchanged", f"MEDIA:{out1}" in txt and txt.startswith("done: "), txt)
check("stdout is restored afterwards", not isinstance(sys.stdout, gw._Tee))

state["mode"] = "503"
out2 = os.path.join(WORK, "descargas", "beta.mp4")
rc, txt = run(["makevideo", "--", "cat", out2])
e = entries()[-1]
check("a failing run is fallo with the exit code and a reason line; quick failures are marked told (the model saw it)",
      rc != 0 and e["state"] == "fallo" and e["exit_code"] == rc and e["reason"] and e["notified"] is True and e["outputs"] == [], str(e))
gw.LEDGER_QUICK_FAIL = 0
rc, txt = run(["makevideo", "--", "cat", out2])
e = entries()[-1]
check("a failure that took longer than the quick window is not yet told (the router will say it)", e["state"] == "fallo" and e["notified"] is False)
gw.LEDGER_QUICK_FAIL = 15
state["mode"] = "ok"

n = len(entries())
rc, txt = run(["makevideo", "--secs", "4", "--", "p", out2])
check("a refused call (exit 2) leaves no entry at all", rc == 2 and len(entries()) == n)
rc, txt = run(["transcode", "only-one-argument"])
check("a usage exit with a message (sys.exit text) leaves no entry either", rc not in (0, None) and len(entries()) == n, str(entries()[n:]))
rc, txt = run(["bajar", "estado"])
check("`gateway bajar estado` is not a job", len(entries()) == n)
rc, txt = run(["status"])
check("other verbs are not jobs", len(entries()) == n)

# queued job: the planned command is simply run
ok, qid, _ = tj.plan("tercer clip", f"gateway makevideo --secs 3 -- 'a red fox' {WORK}/descargas/iota.mp4")
rc, txt = run(["makevideo", "--secs", "3", "--", "a red fox", f"{WORK}/descargas/iota.mp4"])
es = {e["id"]: e for e in entries()}
check("running the planned command attaches to the queued entry (no new entry, the planned label stays)",
      rc == 0 and es[qid]["state"] == "listo" and es[qid]["label"] == "tercer clip" and len(es) == n + 1, str(es[qid]))
ok, qid2, _ = tj.plan("cuarto", f"gateway makevideo -- 'x' {WORK}/descargas/kappa.mp4")
rc, txt = run(["makevideo", "--", "other words", f"{WORK}/descargas/other.mp4"], env={"TRABAJO_ID": qid2})
es = {e["id"]: e for e in entries()}
check("TRABAJO_ID names the queued entry to attach to", es[qid2]["state"] == "listo" and es[qid2]["label"] == "cuarto", str(es[qid2]))
ok, qid3, _ = tj.plan("quinto", f"gateway makevideo --secs 2 -- 'x' {WORK}/descargas/nu.mp4")
run(["makevideo", "--secs", "4", "--", "p", f"{WORK}/descargas/nu.mp4"])         # refused (4 s): the queued job must not be lost
check("a refused run of a queued job leaves a failure that says why, not a silent pending one", {e["id"]: e for e in entries()}[qid3]["state"] == "fallo")

# a long file name is a name: it stays in the label and in the output path
LONG = "Nombre_Largo_De_Una_Cancion_Con_Muchas_Palabras_en_el_archivo_final_v7"
out_long = os.path.join(WORK, "descargas", LONG + ".mp4")
rc, txt = run(["makevideo", "--secs", "5", "--", "a dog on the beach", out_long])
e = entries()[-1]
check("a 70-character file stem stays whole in the label and the output path", rc == 0 and e["label"].startswith(LONG[:50]) and e["outputs"] == [out_long], str(e))

# a refusal AFTER the host was called (the image host said 400 after the wait at the gate) is a failed run, not a vanished one
state["mode"] = "400"
n = len(entries())
rc, txt = run(["makevideo", "--", "refused by the host", os.path.join(WORK, "descargas", "omicron.mp4")])
check("exit 2 after the host was contacted is recorded as a failure", rc == 2 and len(entries()) == n + 1 and entries()[-1]["state"] == "fallo", str(entries()[n:]))
state["mode"] = "ok"

# the verb function itself: refusal before any network call vs failures after one, and a reason that is only on stderr
def fake_refuse(argv):
    sys.exit("unknown option --bogus")
def fake_usage_rc2(argv):
    print("usage: gateway image ...")
    return 2
def fake_touch_then_rc2(argv):
    import urllib.request
    urllib.request.urlopen(url + "/healthz", timeout=5).read()
    print("the host refused")
    return 2
def fake_stderr_failure(argv):
    print("working...")
    print("boom: the disk is full", file=sys.stderr)
    return 1
n = len(entries())
for fn in (fake_refuse, fake_usage_rc2):
    try:
        gw.run_ledgered("image", fn, ["--", "p", os.path.join(WORK, "x.jpg")])
    except SystemExit:
        pass
check("an option error (sys.exit text, rc 1) and a usage rc 2 before any network call leave no trace", len(entries()) == n, str(entries()[n:]))
gw.run_ledgered("image", fake_touch_then_rc2, ["--", "p", os.path.join(WORK, "y.jpg")])
check("rc 2 after a network call is a failure", entries()[-1]["state"] == "fallo" and entries()[-1]["reason"] == "the host refused", str(entries()[-1]))
gw.LEDGER_QUICK_FAIL = 15
buf_err = io.StringIO()
with contextlib.redirect_stderr(buf_err):
    gw.run_ledgered("image", fake_stderr_failure, ["--", "p", os.path.join(WORK, "z.jpg")])
check("a failure that was only printed to stderr is the reason (the last line of both streams); stderr still reaches the caller",
      entries()[-1]["reason"] == "boom: the disk is full" and "boom" in buf_err.getvalue(), str(entries()[-1]))
check("streams are restored", sys.stderr is not None and not isinstance(sys.stderr, gw._Tee) and not isinstance(sys.stdout, gw._Tee))
import urllib.request
check("urlopen is restored", urllib.request.urlopen.__name__ == "urlopen")

# the ledger can never break a render
class Boom:
    def start(self, *a, **k): raise RuntimeError("ledger broke")
    def finish(self, *a, **k): raise RuntimeError("ledger broke")
    def abort(self, *a, **k): raise RuntimeError("ledger broke")
gw._LEDGER[:] = [Boom()]
out3 = os.path.join(WORK, "descargas", "mu.mp4")
rc, txt = run(["makevideo", "--", "still works", out3])
check("a ledger that raises on start does not stop the render", rc == 0 and os.path.exists(out3))
class Boom2(Boom):
    def start(self, *a, **k): return "t999"
gw._LEDGER[:] = [Boom2()]
rc, txt = run(["makevideo", "--", "still works 2", out3 + ".x.mp4"])
check("a ledger that raises at the end does not change the exit code", rc == 0)
gw._LEDGER[:] = [None]
rc, txt = run(["makevideo", "--", "no ledger at all", os.path.join(WORK, "descargas", "xi.mp4")])
check("no ledger module: the verb runs as before", rc == 0)
gw._LEDGER[:] = []

# helpers
check("ledger_label: image uses the file stem and the prompt head", gw.ledger_label("image", ["--quality", "fast", "--", "a long prompt about ducks", "/workdir/imagenes/pato.jpg"]) == "pato: a long prompt about ducks")
check("ledger_label: upscale (no prompt) is the file stem", gw.ledger_label("upscale", ["/workdir/a.png", "/workdir/a4x.png"]) == "a4x")
check("ledger_label: bajar names the first item and counts the rest", gw.ledger_label("bajar", ["--calidad", "720", "https://x.example/v", "https://y.example/w"]) == "bajar https://x.example/v +1")
out = gw.ledger_outputs(f"done: {WORK}/a.mp4 (x)\ndone on h (GPU host) in 3.1s -> {WORK}/b.mp4\nMEDIA:{WORK}/c.mp4 MEDIA:/etc/passwd\n    {WORK}/d.mp4\nnoise {WORK}/e.mp4\n", [])
check("ledger_outputs reads done lines, MEDIA lines and indented paths, only inside the work folder",
      out == [f"{WORK}/a.mp4", f"{WORK}/b.mp4", f"{WORK}/c.mp4", f"{WORK}/d.mp4"], str(out))
check("the Dockerfile installs the program next to the other wrappers", "COPY trabajos.py /usr/local/bin/trabajos" in open(os.path.join(HERE, "Dockerfile.hermes-agent")).read())

print()
if FAIL:
    print(f"{len(FAIL)} FAILED: {FAIL}")
    sys.exit(1)
print("gateway_ledger_selftest: all ok")
