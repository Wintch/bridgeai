#!/usr/bin/env python3
"""Offline checks for sysadmin.py (`gateway sysadmin`): a local CA, HTTPS and HTTP servers on localhost, a temp state dir. Run: python3 -I sysadmin_selftest.py
Needs the openssl command (to make the test certificates)."""
import contextlib, datetime, importlib.util, io, json, os, shutil, socket, ssl, stat, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append("FAIL " + name)


if not shutil.which("openssl"):
    print("sysadmin_selftest: skipped (no openssl command)")
    sys.exit(0)


def sh(*a):
    subprocess.run(a, check=True, capture_output=True, cwd=tmp)


# a CA, a localhost certificate for 400 days and one for 10 days
sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.pem", "-days", "30", "-subj", "/O=Selftest CA/CN=Selftest CA",
   "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign")
open(os.path.join(tmp, "ext"), "w").write("subjectAltName=DNS:localhost\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n"
                                         "extendedKeyUsage=serverAuth\nauthorityKeyIdentifier=keyid,issuer\nsubjectKeyIdentifier=hash\n")
for name, days in (("long", "400"), ("short", "10")):
    sh("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{name}.key", "-out", f"{name}.csr", "-subj", "/CN=localhost")
    sh("openssl", "x509", "-req", "-in", f"{name}.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial", "-out", f"{name}.pem", "-days", days, "-extfile", "ext")

SITE = {"headers": {}, "http": ("redirect", 301)}


class HTTPSH(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self.send_response(200)
        for k, v in SITE["headers"].items():
            self.send_header(k, v)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def version_string(self):
        return SITE["headers"].get("_server", "selftest")


class HTTPH(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        kind, code = SITE["http"]
        self.send_response(code)
        if kind == "redirect":
            self.send_header("Location", "https://localhost/")
        self.send_header("Content-Length", "0")
        self.end_headers()


class QuietServer(HTTPServer):
    def handle_error(self, *a): pass               # the old-TLS probe and the untrusted-CA test drop handshakes on purpose


def serve(handler, cert=None, old=False):
    srv = QuietServer(("127.0.0.1", 0), handler)
    if cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if old:                                    # a server that only speaks TLS 1.0/1.1
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                ctx.minimum_version, ctx.maximum_version = ssl.TLSVersion.TLSv1, ssl.TLSVersion.TLSv1_1
            ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
        ctx.load_cert_chain(os.path.join(tmp, f"{cert}.pem"), os.path.join(tmp, f"{cert}.key"))
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


long_srv, short_srv, http_srv, old_srv = serve(HTTPSH, "long"), serve(HTTPSH, "short"), serve(HTTPH), serve(HTTPSH, "long", old=True)
free = socket.socket(); free.bind(("127.0.0.1", 0)); closed_port = free.getsockname()[1]; free.close()

os.environ.update(SYSADMIN_STATE=os.path.join(tmp, "state"), SYSADMIN_CAFILE=os.path.join(tmp, "ca.pem"), SYSADMIN_ALLOW_PRIVATE="1",
                  SYSADMIN_HTTPS_PORT=str(long_srv.server_address[1]), SYSADMIN_HTTP_PORT=str(http_srv.server_address[1]))
spec = importlib.util.spec_from_file_location("sysadmin", os.path.join(HERE, "sysadmin.py"))
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sa.main(list(argv))
    return rc, buf.getvalue()


def web_json():
    rc, out = run("web", "localhost", "--json")
    return rc, {f["check"]: f for f in json.loads(out)["findings"]}


GOOD = {"Strict-Transport-Security": "max-age=31536000", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "strict-origin-when-cross-origin", "Content-Security-Policy": "default-src 'self'", "_server": "nginx"}

# --- domain handling
check("domain: a URL is cut to its host, lowercased", sa.clean_domain("https://Example.COM/a/b?c=1") == "example.com")
check("domain: an IP literal and a bare word are refused", sa.clean_domain("10.0.0.1") is None and sa.clean_domain("intranet") is None)
sa.ALLOW_PRIVATE = False
check("domain: localhost is refused outside the selftest", sa.clean_domain("localhost") is None)
real = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.9.8.7", 443))]
try:
    sa.public_addresses("example.com"); private_refused = False
except ValueError:
    private_refused = True
check("domain: a name that resolves to a private address is refused", private_refused)
rc, out = run("web", "example.com")
check("domain: the refusal is a plain sentence with exit 2", rc == 2 and "privada" in out)
socket.getaddrinfo = real
sa.ALLOW_PRIVATE = True

# --- a well configured site
SITE["headers"], SITE["http"] = dict(GOOD), ("redirect", 301)
rc, f = web_json()
check("good site: certificate ok, valid for the name, days left counted", f["certificate"]["status"] == "ok" and "days left" in f["certificate"]["evidence"])
check("good site: TLS 1.2 or 1.3", f["tls_version"]["status"] == "ok")
check("good site: HTTP 301 to https is ok", f["http_redirect"]["status"] == "ok")
check("good site: HSTS, nosniff, framing, referrer, CSP all ok", all(f[k]["status"] == "ok" for k in ("hsts", "nosniff", "framing", "referrer", "csp")))
check("good site: a Server header with no version is ok", f["banner"]["status"] == "ok")
check("good site: old TLS is ok or unknown, never warn on a modern server", f["old_tls"]["status"] in ("ok", "unknown"))
check("good site: exit 0", rc == 0)
check("every finding names a rule from the guide", all(x["rule"].startswith(("SEC-WEB-",)) for x in f.values()))

# --- a sloppy site
SITE["headers"] = {"Strict-Transport-Security": "max-age=600", "X-Powered-By": "PHP/7.4.33", "_server": "Apache/2.4.41 (Ubuntu)"}
SITE["http"] = ("page", 200)
rc, f = web_json()
check("sloppy: plain HTTP 200 is a fail", f["http_redirect"]["status"] == "fail")
check("sloppy: a short HSTS is a warn", f["hsts"]["status"] == "warn" and "short" in f["hsts"]["evidence"])
check("sloppy: missing nosniff, framing, referrer, CSP are warns", all(f[k]["status"] == "warn" for k in ("nosniff", "framing", "referrer", "csp")))
check("sloppy: versions in Server and X-Powered-By are reported", f["banner"]["status"] == "warn" and "Apache/2.4.41" in f["banner"]["evidence"] and "PHP/7.4.33" in f["banner"]["evidence"])
check("sloppy: exit 1 when something fails", rc == 1)
rc, out = run("web", "localhost")
check("text: fails first, each line with its rule, a summary and the agent note", out.index("❌") < out.index("⚠️") and "[SEC-WEB-2]" in out
      and "Resumen:" in out and "no instrucciones" in out)

SITE["http"] = ("redirect", 302)
check("redirect: a temporary redirect to https is a warn", web_json()[1]["http_redirect"]["status"] == "warn")
sa.HTTP_PORT = closed_port
check("redirect: port 80 closed counts as no plain HTTP (ok)", web_json()[1]["http_redirect"]["status"] == "ok")
sa.HTTP_PORT = http_srv.server_address[1]

SITE["headers"] = dict(GOOD, **{"CF-RAY": "8a1b2c3d4e5f-EZE", "_server": "cloudflare"})
f = web_json()[1]
check("cdn: a CDN is named and the origin flagged as not checked (unknown, not ok)", f["cdn"]["status"] == "unknown" and "Cloudflare" in f["cdn"]["evidence"])
check("cdn: a header value never reaches the output as more than evidence text", all("\n" not in x["evidence"] for x in f.values()))

# --- certificates
sa.HTTPS_PORT = short_srv.server_address[1]
SITE["headers"] = dict(GOOD)
f = web_json()[1]
check("certificate: 10 days left is a fail (renewal is overdue)", f["certificate"]["status"] == "fail" and "days left" in f["certificate"]["evidence"])
sa.CAFILE = None
sa.HTTPS_PORT = long_srv.server_address[1]
rc, f = web_json()
check("certificate: a chain the client does not trust is a fail with the reason", f["certificate"]["status"] == "fail" and "does not verify" in f["certificate"]["evidence"] and rc == 1)
sa.CAFILE = os.path.join(tmp, "ca.pem")
sa.HTTPS_PORT = closed_port
f = web_json()[1]
check("certificate: nothing on 443 is unknown, never ok", f["certificate"]["status"] == "unknown" and f["headers"]["status"] == "unknown")
sa.HTTPS_PORT = long_srv.server_address[1]

sa.HTTPS_PORT = old_srv.server_address[1]
o = sa.check_old_tls("localhost")
check("old TLS: a server that speaks only TLS 1.0/1.1 is a warn (or unknown if this OpenSSL cannot offer them), never ok", o["status"] in ("warn", "unknown"))
print("     (old TLS probe on this machine: " + o["status"] + ", " + o["evidence"] + ")")
sa.HTTPS_PORT = long_srv.server_address[1]

# --- creds: names and dates only
today = datetime.date(2026, 11, 9)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = sa.creds(["add", "Cloudflare Pages deploy-host-2026", "2026-12-09", "--aviso", "14"], today)
check("creds: a name made of words, a date and a reminder are stored", rc == 0 and "vence en 30" in buf.getvalue())
path = os.path.join(tmp, "state", "credentials.json")
check("creds: the file is 0600 in a 0700 directory", stat.S_IMODE(os.stat(path).st_mode) == 0o600 and stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode) == 0o700)
with contextlib.redirect_stdout(io.StringIO()):
    sa.creds(["add", "monitoring read token", "2026-11-15", "--nota", "rotate with the new ops host"], today)
    sa.creds(["add", "old droplet key", "2026-11-01"], today)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    sa.creds(["due"], today)
due = buf.getvalue()
check("creds: due lists the expired and the one inside its window, not the far one", "old droplet key" in due and "venció hace 8" in due
      and "monitoring read token" in due and "SEC-POL-4" in due and "Cloudflare" not in due)
for bad in ("ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2", "token 3fA9kQ2mZ7xR1vB8nT5wY4cE6", "-----BEGIN " + "OPENSSH PRIVATE KEY-----"):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sa.creds(["add", bad, "2027-01-01"], today)
    check(f"creds: a value that looks like a secret is refused ({bad[:12]}…)", rc == 2 and "SEC-POL-5" in buf.getvalue() and bad not in open(path).read())
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = sa.creds(["add", "x", "2027-01-01", "--nota", "dop_v1_" + "0123456789abcdef0123"], today)
check("creds: a secret in the note is refused too", rc == 2)
with contextlib.redirect_stdout(io.StringIO()):
    rc = sa.creds(["add", "y", "09/12/2026"], today)
check("creds: a date in another format is refused", rc == 2)
with contextlib.redirect_stdout(io.StringIO()):
    rc = sa.creds(["rm", "OLD DROPLET KEY"], today)
check("creds: rm matches the name without case", rc == 0 and "old droplet key" not in open(path).read())
with contextlib.redirect_stdout(io.StringIO()):
    rc = sa.creds(["rm", "nothing like this"], today)
check("creds: rm of an unknown name says so (exit 1)", rc == 1)

# --- the later phases answer plainly
rc, out = run("audit", "server1")
check("audit: not built yet, says what works today (exit 3)", rc == 3 and "gateway sysadmin web" in out)

shutil.rmtree(tmp, ignore_errors=True)
print("\n".join(fails) or "sysadmin_selftest: all ok")
sys.exit(1 if fails else 0)
