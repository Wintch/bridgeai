#!/usr/bin/env python3
"""Offline checks for `gateway enlaces` against local servers: ok, 404, redirects, 403, a site that refuses HEAD, a robot-check page,
a timeout, a refused port, a bad certificate, a name that does not exist, the private-address guard, --file extraction and the limit.
Run: python3 -I gateway_enlaces_selftest.py"""
import contextlib, importlib.util, io, json, os, shutil, socket, ssl, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body=b"", extra=()):
        self.send_response(code)
        for k, v in extra:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def handle_any(self):
        p = self.path.split("?")[0]
        if p == "/ok": return self.send(200, b"<html><title>Open call</title></html>")
        if p == "/missing": return self.send(404, b"nope")
        if p == "/gone": return self.send(410)
        if p == "/boom": return self.send(500)
        if p == "/redir": return self.send(302, extra=[("Location", "/ok")])
        if p == "/redir-root": return self.send(301, extra=[("Location", "/")])
        if p == "/redir-away": return self.send(302, extra=[("Location", f"http://localhost:{self.server.server_port}/ok")])
        if p == "/redir-dead": return self.send(302, extra=[("Location", "/missing")])
        if p == "/loop": return self.send(302, extra=[("Location", "/loop")])
        if p == "/cookie":                      # a session cookie first, then the page (a portal that redirects to itself until the cookie is back)
            return self.send(200, b"<title>session</title>") if "sid=abc" in (self.headers.get("Cookie") or "") else self.send(302, extra=[("Location", self.path), ("Set-Cookie", "sid=abc; Path=/; HttpOnly")])
        if p == "/cookie-gone":                 # the cookie is cleared again: never settles
            return self.send(302, extra=[("Location", self.path), ("Set-Cookie", "sid=; Max-Age=0")])
        if p == "/forbidden": return self.send(403, b"no robots")
        if p == "/rate": return self.send(429)
        if p == "/nohead": return self.send(405) if self.command == "HEAD" else self.send(200, b"<title>page</title>")
        if p == "/head404": return self.send(404) if self.command == "HEAD" else self.send(200, b"<title>page</title>")
        if p == "/challenge": return self.send(200, b"<html><head><title>Just a moment...</title></head></html>")
        if p == "/slow":
            time.sleep(3)
            return self.send(200, b"late")
        if p == "/":  return self.send(200, b"<title>front</title>")
        self.send(404)
    do_GET = do_HEAD = handle_any


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"

# a TLS server with a self-signed certificate (skipped when openssl is not there)
tls_base = None
if shutil.which("openssl"):
    r = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{tmp}/k.pem", "-out", f"{tmp}/c.pem", "-days", "2", "-subj", "/CN=localhost"],
                       capture_output=True)
    if r.returncode == 0:
        tsrv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(f"{tmp}/c.pem", f"{tmp}/k.pem")
        tsrv.socket = ctx.wrap_socket(tsrv.socket, server_side=True)
        threading.Thread(target=tsrv.serve_forever, daemon=True).start()
        tls_base = f"https://127.0.0.1:{tsrv.server_port}"

s = socket.socket(); s.bind(("127.0.0.1", 0)); closed_port = s.getsockname()[1]; s.close()   # nothing listens here

os.environ.update(GATEWAY_LOG=f"{tmp}/log", AIBRIDGE_PREFS=f"{tmp}/prefs.json", AIBRIDGE_LINKS_ALLOW_PRIVATE="1")
spec = importlib.util.spec_from_file_location("gw", f"{HERE}/gateway.py")
gw = importlib.util.module_from_spec(spec); spec.loader.exec_module(gw)
gw.LINKS_TIMEOUT = 1
gw.LINKS_DEADLINE = 2

fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)
def run(*argv):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        rc = gw.cmd_enlaces(list(argv))
    return rc, b.getvalue()
def line(out, path):
    return next((l for l in out.splitlines() if l.split(" ", 2)[-1].startswith(base + path) or (base + path) in l), "")

# 1. one call, every kind of answer
paths = ["/ok", "/missing", "/gone", "/boom", "/redir", "/redir-root", "/redir-away", "/redir-dead", "/loop", "/cookie", "/cookie-gone", "/forbidden", "/rate", "/nohead", "/head404", "/challenge", "/slow"]
rc, out = run(*[base + p for p in paths], f"http://127.0.0.1:{closed_port}/x", "http://no-such-host-for-this-test.invalid/page")
check("a dead link makes the exit code 3", rc == 3)
check("200 is ok", line(out, "/ok").startswith("ok 200 "))
check("404 is dead", line(out, "/missing").startswith("dead 404 "))
check("410 is dead", line(out, "/gone").startswith("dead 410 "))
check("500 is dead", line(out, "/boom").startswith("dead 500 "))
check("a redirect to a page that opens is ok and shows nothing extra for the same site path", line(out, "/redir").startswith("ok 200 ") and "/redir ->" in line(out, "/redir"))
check("a redirect to the front page is ok but flagged", line(out, "/redir-root").startswith("ok 200 ") and "front page" in line(out, "/redir-root"))
check("a redirect to another host shows where it went", line(out, "/redir-away").startswith("ok 200 ") and "-> http://localhost:" in line(out, "/redir-away"))
check("a redirect to a missing page is dead with that code", line(out, "/redir-dead").startswith("dead 404 "))
check("a redirect loop is unclear, not dead", line(out, "/loop").startswith("unclear redirects ") and "not proven dead" in line(out, "/loop"))
check("a redirect to itself that sets a session cookie opens once the cookie is sent back", line(out, "/cookie").startswith("ok 200 "))
check("a redirect to itself that clears its cookie is unclear", line(out, "/cookie-gone").startswith("unclear redirects "))
check("403 is blocked and says to open it in a browser", line(out, "/forbidden").startswith("blocked 403 ") and "open it in a browser" in line(out, "/forbidden"))
check("429 is blocked", line(out, "/rate").startswith("blocked 429 "))
check("a site that refuses HEAD is checked with GET", line(out, "/nohead").startswith("ok 200 "))
check("a site that answers HEAD with 404 but serves the page is ok", line(out, "/head404").startswith("ok 200 "))
check("a 200 robot-check page is blocked, not ok", line(out, "/challenge").startswith("blocked 200 "))
check("a slow link is dead with the word timeout", line(out, "/slow").startswith("dead timeout "))
check("a refused port is dead with the word refused", f":{closed_port}/x" in out and any(l.startswith("dead refused ") for l in out.splitlines()))
check("a name that does not exist is dead with the word dns", any(l.startswith("dead dns ") and ".invalid" in l for l in out.splitlines()))
check("the summary counts every class", "checked 19: 7 ok, 3 blocked, 2 unclear, 7 dead" in out)
check("the closing note says what to do with dead and blocked links", "do not show them" in out and "never \"verified\"" in out)

# 2. all good: exit 0
rc, out = run(base + "/ok", base + "/forbidden")
check("no dead link: exit 0, summary line", rc == 0 and "checked 2: 1 ok, 1 blocked" in out and "do not show them" not in out)

# 3. the same URL twice is asked once; order is kept
rc, out = run(base + "/ok", base + "/missing", base + "/ok")
check("duplicates are asked once and the order of the arguments is kept", [l.split()[0] for l in out.splitlines()[:2]] == ["ok", "dead"] and "checked 2:" in out)

# 4. bad certificate
if tls_base:
    rc, out = run(tls_base + "/ok")
    check("a certificate that does not verify is dead with the word tls", rc == 3 and out.startswith("dead tls "))
else:
    print("skip tls (no openssl)")

# 5. the private-address guard (the test hook off)
os.environ.pop("AIBRIDGE_LINKS_ALLOW_PRIVATE")
rc, out = run(base + "/ok", "http://localhost:9/x", "http://10.0.0.1/", "http://[::1]/", "http://169.254.169.254/latest/")
check("loopback, LAN and metadata addresses are not asked", rc == 0 and out.count("unchecked private ") == 5 and "checked 5: 5 unchecked" in out)
rc, out = run(base + "/redir-away")
check("a redirect into a private address is not followed", out.startswith("unchecked private "))
os.environ["AIBRIDGE_LINKS_ALLOW_PRIVATE"] = "1"

# 6. --file: markdown links, bare URLs, table cells, punctuation, duplicates
md = f"""# Tracker
| Call | Link | Status |
|---|---|---|
| A | {base}/ok | open |
| B | [site]({base}/missing) | closed |
See {base}/redir, and also ({base}/gone). Again {base}/ok.
Wiki style {base}/ok_(x) is not a duplicate; trailing dot {base}/rate.
mailto:someone@example.org and ftp://example.org/file are not http links.
"""
p = os.path.join(tmp, "tracker.md"); open(p, "w").write(md)
found = gw.links_extract(md)
check("--file extraction: markdown, bare, table cells, trailing punctuation, parentheses, dedup",
      found == [base + "/ok", base + "/missing", base + "/redir", base + "/gone", base + "/ok_(x)", base + "/rate"])
rc, out = run("--file", p)
check("--file checks each link found", rc == 3 and "checked 6:" in out and line(out, "/missing").startswith("dead 404 "))
rc, out = run("--file", os.path.join(tmp, "nope.md"))
check("a missing file is said so, exit 2", rc == 2 and "cannot read" in out)
open(p, "w").write("no links here")
rc, out = run("--file", p)
check("a file with no link: usage, exit 2", rc == 2 and "usage:" in out)

# 7. the limit
many = [f"{base}/ok?n={i}" for i in range(85)]
rc, out = run(*many)
check("at most 80 links per call, the rest counted", rc == 0 and "checked 80: 80 ok" in out and "5 more not checked" in out)

# 8. usage and odd input
rc, out = run()
check("no argument: usage, exit 2", rc == 2 and "usage:" in out)
rc, out = run("--wat", base + "/ok")
check("an unknown option: exit 2", rc == 2 and "unknown option" in out)
rc, out = run("not a url", "ftp://example.org/x", "http://")
check("things that are not http(s) links are invalid with bad-url (not dead), exit 2, never a crash",
      rc == 2 and out.count("invalid bad-url ") == 3 and "checked 3: 3 invalid" in out and "needs http:// or https://" in out and "dead" not in out)
rc, out = run("not a url", base + "/missing")
check("a dead link next to an invalid one still gives exit 3", rc == 3)
# a bare host name is a page, tried with https:// (the local server speaks http, so the TLS one answers when openssl is there)
if tls_base:
    rc, out = run(tls_base.split("://", 1)[1] + "/ok")
    check("a bare host name is tried as https:// (a TLS answer, not bad-url)", out.startswith("dead tls ") and "-> " + tls_base + "/ok" in out)
rc, out = run("no-such-host-for-this-test.invalid/call", "some.org/x y")
check("a bare host name that does not exist is dead dns, one with a space is invalid",
      "dead dns no-such-host-for-this-test.invalid/call -> https://no-such-host-for-this-test.invalid/call" in out and "invalid bad-url some.org/x y" in out)
rc, out = run("mailto:someone@example.org", "example")
check("mailto: and a word without a dot are invalid, not guessed", out.count("invalid bad-url ") == 2)
rc, out = run(base + "/ok\x1b[31m‮\nINJECTED")
check("control characters of a link never start a line of their own in the output", not any(l.startswith("INJECTED") for l in out.splitlines()) and "\x1b" not in out)

# 9. aliases and help
os.environ["GATEWAY_LOG"] = f"{tmp}/log"
src = open(f"{HERE}/gateway.py", encoding="utf-8").read()
check("links and ссылки are registered next to enlaces", '"enlaces": cmd_enlaces, "links": cmd_enlaces, "ссылки": cmd_enlaces' in src)
b = io.StringIO()
with contextlib.redirect_stdout(b):
    rc1 = gw.cmd_help(["enlaces"]); a = b.getvalue()
    b.seek(0); b.truncate()
    rc2 = gw.cmd_help(["ссылки"]); c = b.getvalue()
check("gateway help enlaces and its alias print the usage entry", rc1 == 0 and rc2 == 0 and a == c and a.startswith("gateway enlaces URL"))

# 10. the log keeps counts only
log = open(f"{tmp}/log").read()
rows = [json.loads(l) for l in log.splitlines() if '"enlaces"' in l]
check("the log has one record per call with counts and no address", rows and all("http" not in json.dumps(r) and "n" in r for r in rows))

shutil.rmtree(tmp, ignore_errors=True)
print("\n".join(fails) or "gateway_enlaces_selftest: all ok")
sys.exit(1 if fails else 0)
