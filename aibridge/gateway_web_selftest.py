#!/usr/bin/env python3
"""Offline checks for `gateway web vista`, `gateway web variante` and `gateway web volver`. A local bare repo
stands in for Gitea; a fake renderer (AIBRIDGE_WEB_RENDERER) stands in for headless Chromium, so the orchestration is tested
anywhere: which folders are served, the side-by-side sheet, the MEDIA lines, the clean-up, the network-block flag. One real
render runs when Playwright and a Chromium exist on this machine (skipped otherwise).
The older `gateway web estado|publicar|deshacer|descartar|avif` checks are in gateway_pref_selftest.py.
Run: python3 -I gateway_web_selftest.py"""
import contextlib, datetime, glob, http.server, importlib.util, io, json, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
os.environ.update(GATEWAYS_CONFIG=f"{tmp}/gw.json", GATEWAY_LOG=f"{tmp}/log", AIBRIDGE_PREFS=f"{tmp}/prefs.json",
                  AIBRIDGE_WEB_VISTAS=f"{tmp}/vistas", TZ="America/Argentina/Buenos_Aires")
spec = importlib.util.spec_from_file_location("gw", f"{HERE}/gateway.py")
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)
from PIL import Image

os.makedirs(f"{tmp}/tmp")
import tempfile as _tf
_tf.tempdir = f"{tmp}/tmp"          # every temp dir the code makes lands here, so leaks are countable

fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")

BASE_ENV = dict(os.environ, GIT_AUTHOR_NAME="E", GIT_AUTHOR_EMAIL="e@x", GIT_COMMITTER_NAME="E", GIT_COMMITTER_EMAIL="e@x")
def G(*a, cwd=None, date=None):
    env = dict(BASE_ENV, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}))
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, env=env)

# ---- a fake renderer: fetches the page from the URL it was given (so the served folder is what is rendered), writes a PNG
# whose colour says which version it saw, and records everything it was asked
fake = f"{tmp}/fake_render.py"
open(fake, "w").write('''
import json, os, sys, urllib.request, urllib.error
url, out, width, maxh = sys.argv[1:5]
flags = sys.argv[5:]
body = urllib.request.urlopen(url, timeout=10).read().decode()
try:
    urllib.request.urlopen(url.split("/", 3)[0] + "//" + url.split("/", 3)[2] + "/.git/HEAD", timeout=10)
    git = 200
except urllib.error.HTTPError as e:
    git = e.code
from PIL import Image
col = (200, 40, 40) if "NUEVO" in body else (40, 40, 200)
Image.new("RGB", (int(width), 3000 if "LARGO" in body else 500 + len(body) % 7), col).save(out)
open(os.environ["FAKE_LOG"], "a").write(json.dumps({"url": url, "width": int(width), "flags": flags, "new": "NUEVO" in body,
    "git": git, "maxh": int(maxh)}) + "\\n")
print(json.dumps({"height": 9000 if "LARGO" in body else 600, "cut": "LARGO" in body, "blocked": ["fonts.googleapis.com"] if "FONT" in body else []}))
''')
os.environ.update(AIBRIDGE_WEB_RENDERER=fake, FAKE_LOG=f"{tmp}/render.log")
renders = lambda: [json.loads(l) for l in open(f"{tmp}/render.log")] if os.path.exists(f"{tmp}/render.log") else []

web_get_calls = []
_get, _wait, _poll, _conf = gw.web_get, gw.WEB_WAIT, gw.WEB_POLL, gw.CONF

def setup(name, seed_commits):
    """A bare origin with the given commits [(date, {file: text|None}, message)], a config pointing at it, a deploy fake."""
    root = f"{tmp}/{name}"
    origin, seed, W = f"{root}/origin.git", f"{root}/seed", f"{root}/work/site"
    os.makedirs(root)
    G("init", "-q", "--bare", "-b", "main", origin)
    G("clone", "-q", origin, seed)
    for date, files, msg in seed_commits:
        for f, text in files.items():
            if text is None:
                os.remove(f"{seed}/{f}")
            else:
                os.makedirs(os.path.dirname(f"{seed}/{f}") or seed, exist_ok=True)
                open(f"{seed}/{f}", "w").write(text)
        G("add", "-A", cwd=seed); G("commit", "-q", "-m", msg, cwd=seed, date=date); G("push", "-q", "origin", "main", cwd=seed)
    def fake_get(url, timeout=25):
        web_get_calls.append(url)
        path = urllib.parse.unquote(url.split("site.test/", 1)[1].split("?", 1)[0])
        for cand in ([path + "index.html"] if path == "" or path.endswith("/") else [path, path + ".html"]):
            r = subprocess.run(["git", f"--git-dir={origin}", "show", f"main:{cand}"], capture_output=True)
            if r.returncode == 0:
                return 200, r.stdout
        return 404, b""
    gw.web_get, gw.WEB_POLL = fake_get, 0.05
    json.dump({"web": {"repo": origin, "url": "https://site.test/", "dir": W}}, open(f"{root}/gw.json", "w"))
    gw.CONF = f"{root}/gw.json"
    return origin, W

def web(*a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gw.cmd_web(list(a))
    return rc, buf.getvalue()

def media(out):
    return re.findall(r"^MEDIA:(.+)$", out, re.M)

# =========================================================================== vista
origin, W = setup("vista", [("2026-01-01T12:00:00+0000", {"index.html": "<p>VIEJO</p>\n", "contacto.html": "<p>contacto</p>\n", ".secret": "x"}, "seed")])
head = lambda: G(f"--git-dir={origin}", "rev-parse", "main").stdout.strip()
rc, out = web()
check("vista: estado clones", rc, 0)
leaks = lambda: sorted(glob.glob(f"{tmp}/tmp/hermes-*"))

rc, out = web("vista")
check("vista: nothing to compare: copy only, 2 pictures (phone, desktop), no question to ask", (rc, len(media(out)), "¿publico?" in out, "No hay cambios sin publicar" in out), (0, 2, False, True))
check("vista: the files are JPEG under the vistas folder", [os.path.dirname(m) == f"{tmp}/vistas" and m.endswith(".jpg") and Image.open(m).format == "JPEG" for m in media(out)], [True, True])
rr = renders()
check("vista: served from 127.0.0.1 at 390 and 1280, network block asked for, .git not served",
      ([bool(re.match(r"http://127\.0\.0\.1:\d+/index\.html$", r["url"])) for r in rr], [r["width"] for r in rr], all("--block-external" in r["flags"] for r in rr),
       {r["git"] for r in rr}, {r["maxh"] for r in rr}), ([True, True], [390, 1280], True, {404}, {4000}))

def refused(url):
    try:
        urllib.request.urlopen(url, timeout=3)
        return False
    except urllib.error.HTTPError:
        return False
    except (urllib.error.URLError, OSError):
        return True
check("vista: the temp dirs are gone and the server is stopped", (leaks(), refused(rr[0]["url"])), ([], True))

# unpublished change: ONE comparison per width, left published, right working copy
open(f"{W}/index.html", "w").write("<p>NUEVO FONT</p>\n")
n0 = len(renders())
rc, out = web("vista")
rr = renders()[n0:]
ms = media(out)
check("vista: with changes, one sheet per width (2 files), the question to ask, the changed files named",
      (rc, len(ms), "¿publico?" in out, "index.html" in out, all("comparacion" in m for m in ms)), (0, 2, True, True, True))
check("vista: published and working copy are two different servers, in that order", (len(rr), len({urlp.split("/")[2] for urlp in (r["url"] for r in rr)}) >= 2,
      [r["new"] for r in rr]), (4, True, [False, True, False, True]))
phone, desk = (Image.open(m) for m in sorted(ms, key=lambda m: "movil" not in m))
check("vista: phone sheet is two 390 px panels side by side, the desktop one is scaled to at most 2000 px",
      (phone.width > 780, phone.width < 860, desk.width <= 2000, desk.width > 1500), (True, True, True, True))
def near(px, want):
    return all(abs(a - b) < 14 for a, b in zip(px, want))
check("vista: left label band is grey (Así está), right one green (Así quedaría)",
      (near(phone.getpixel((3, 3)), (90, 90, 90)), near(phone.getpixel((phone.width - 3, 3)), (24, 120, 70))), (True, True))
check("vista: published side shows the old page (blue), working copy the new one (red)",
      (near(phone.getpixel((20, 120)), (40, 40, 200)), near(phone.getpixel((phone.width - 20, 120)), (200, 40, 40))), (True, True))
check("vista: blocked third parties are said, the preview may differ", ("fonts.googleapis.com" in out, "distintos" in out), (True, True))
check("vista: nothing leaked after a comparison", leaks(), [])

# the published side is origin/<branch>, not a local commit that was never pushed
G("add", "-A", cwd=W); G("commit", "-q", "-m", "local, not pushed", cwd=W)
n0 = len(renders()); rc, out = web("vista")
check("vista: a local unpushed commit is not 'published'", [r["new"] for r in renders()[n0:]], [False, True, False, True])
G("reset", "-q", "--hard", "origin/main", cwd=W)
calls_before = len(web_get_calls); web("vista"); web("vista", "--publicado")
check("vista: no request to the (fake) live site during vista", len(web_get_calls), calls_before)

# --publicado: only the published one, no question, labelled
open(f"{W}/index.html", "w").write("<p>NUEVO</p>\n")
n0 = len(renders()); rc, out = web("vista", "--publicado")
rr = renders()[n0:]
check("vista --publicado: only the published copy is rendered, not asked to publish",
      (rc, len(rr), [r["new"] for r in rr], len(media(out)), "¿publico?" in out, all("publicado" in m for m in media(out))), (0, 2, [False, False], 2, False, True))

# a page that exists only in the working copy: left says it did not exist
open(f"{W}/nueva.html", "w").write("<p>NUEVO nueva</p>\n")
rc, out = web("vista", "nueva")
check("vista: a new page (no .html needed) gets a sheet with 'no existía' on the left", (rc, len(media(out)), len(renders()[-2:]), renders()[-1]["url"].endswith("/nueva")), (0, 2, 2, True))
rc, out = web("vista", "no-existe.html")
check("vista: a page that exists nowhere is an error", (rc, "no encuentro la página" in out), (1, True))
check("vista: odd page arguments are refused", [web("vista", p)[0] for p in ("../x", ".git/config", "a b c d")], [1, 1, 1])
os.remove(f"{W}/nueva.html")

# long pages are cut and it is said
open(f"{W}/contacto.html", "w").write("<p>NUEVO LARGO</p>\n")
rc, out = web("vista", "contacto.html")
check("vista: a page taller than the cap is cut and says so", (rc, "9000 px" in out, "4000" in out), (0, True, True))
G("checkout", "--", "contacto.html", cwd=W)

# only the last 10 pictures are kept
for _ in range(8):
    web("vista", "--publicado")
check("vista: only the last 10 pictures stay", len(glob.glob(f"{tmp}/vistas/*.jpg")), 10)
check("vista: ends with no temp leftovers", leaks(), [])

# a renderer that fails: clear error, no partial files and no temp dirs
bad = f"{tmp}/bad_render.py"
open(bad, "w").write("import sys\nsys.stderr.write('boom')\nsys.exit(3)\n")
os.environ["AIBRIDGE_WEB_RENDERER"] = bad
rc, out = web("vista")
check("vista: a renderer failure is reported, nothing leaks", (rc, "no pude sacar la vista previa" in out, leaks()), (1, True, []))
os.environ["AIBRIDGE_WEB_RENDERER"] = fake
G("checkout", "--", "index.html", cwd=W)

# =========================================================================== variantes
def tree(path):
    return {f: open(f"{path}/{f}").read() for f in sorted(os.listdir(path)) if os.path.isfile(f"{path}/{f}")}
remote_refs = lambda: G(f"--git-dir={origin}", "for-each-ref", "--format=%(refname)").stdout.split()
check("variante: lista starts empty", (web("variante", "lista")[0], "No hay variantes" in web("variante", "lista")[1]), (0, True))
h0 = head()
open(f"{W}/index.html", "w").write("<p>A: estrellitas</p>\n"); open(f"{W}/estrellas.js", "w").write("// stars\n")
rc, out = web("variante", "guardar", "estrellas")
check("variante guardar: saved, the working copy is the published site again, nothing pushed",
      (rc, G("status", "--porcelain", cwd=W).stdout, open(f"{W}/index.html").read(), os.path.exists(f"{W}/estrellas.js"), head() == h0, remote_refs()),
      (0, "", "<p>VIEJO</p>\n", False, True, ["refs/heads/main"]))
check("variante: the branch exists locally", G("branch", "--list", "hermes-variante-estrellas", cwd=W).stdout.strip(), "hermes-variante-estrellas")
open(f"{W}/index.html", "w").write("<p>B: copos de nieve</p>\n")
check("variante guardar: a repeated name is refused unless --reemplazar", (web("variante", "guardar", "estrellas")[0], "--reemplazar" in web("variante", "guardar", "estrellas")[1]), (1, True))
check("variante guardar: refused names", [web("variante", "guardar", n)[0] for n in ("Mayús", "con espacio", "../x", "")], [1, 1, 1, 1])
check("variante guardar: the refusal did not touch the work in progress", open(f"{W}/index.html").read(), "<p>B: copos de nieve</p>\n")
rc, out = web("variante", "guardar", "nieve")
rc2, out2 = web("variante", "lista")
check("variante lista: both, with their files", (rc, "estrellas" in out2, "nieve" in out2, "estrellas.js" in out2, remote_refs()), (0, True, True, True, ["refs/heads/main"]))
check("variante guardar: with nothing unpublished it refuses", web("variante", "guardar", "vacia")[0], 1)

rc, out = web("variante", "usar", "estrellas")
check("variante usar: A is in the working copy, unpublished, unstaged", (rc, open(f"{W}/index.html").read(), os.path.exists(f"{W}/estrellas.js"),
      G("diff", "--cached", "--name-only", cwd=W).stdout, head() == h0), (0, "<p>A: estrellitas</p>\n", True, "", True))
n0 = len(renders()); rc, out = web("vista")
check("variante: vista works on whichever variant is in the working copy (published left, A right)", (rc, len(media(out)), "¿publico?" in out, [r["new"] for r in renders()[n0:]]),
      (0, 2, True, [False, False, False, False]))
rc, out = web("variante", "usar", "nieve")
check("variante usar: switching from one untouched variant to the other works", (rc, open(f"{W}/index.html").read(), os.path.exists(f"{W}/estrellas.js")), (0, "<p>B: copos de nieve</p>\n", False))
check("variante lista: marks the one in use", "<- en la copia de trabajo ahora" in web("variante", "lista")[1].split("nieve")[1].split("\n")[0], True)
open(f"{W}/index.html", "a").write("<p>retoque sin guardar</p>\n")
rc, out = web("variante", "usar", "estrellas")
check("variante usar: unsaved edits are never discarded to switch", (rc, "no están guardados" in out, "retoque" in open(f"{W}/index.html").read()), (1, True, True))
check("variante: both variants are still in `estado`", "estrellas" in web("estado")[1], True)
rc, out = web("variante", "guardar", "nieve", "--reemplazar")
check("variante guardar --reemplazar replaces it", (rc, G("show", "hermes-variante-nieve:index.html", cwd=W).stdout), (0, "<p>B: copos de nieve</p>\n<p>retoque sin guardar</p>\n"))

# the person publishes something else meanwhile (another file): the variant is applied on top of it
other = f"{tmp}/vista/other"
G("clone", "-q", origin, other); open(f"{other}/contacto.html", "w").write("<p>contacto nuevo</p>\n")
G("commit", "-qam", "contacto", cwd=other); G("push", "-q", "origin", "main", cwd=other)
rc, out = web("variante", "usar", "estrellas")
check("variante usar: applied over what was published elsewhere meanwhile, both there",
      (rc, open(f"{W}/contacto.html").read(), open(f"{W}/index.html").read()), (0, "<p>contacto nuevo</p>\n", "<p>A: estrellitas</p>\n"))
# and a variant can be published like any change; the other stays local
rc, out = web("publicar", "estrellitas")
check("variante: publishing the one in use pushes only main, the branches stay local", (rc, remote_refs(), "estrellitas" in G(f"--git-dir={origin}", "show", "main:index.html").stdout), (0, ["refs/heads/main"], True))
rc, out = web("variante", "usar", "estrellas")
check("variante usar: one that is already published says so", (rc, "ya está incluida" in out), (0, True))
rc, out = web("variante", "usar", "nieve")
check("variante usar: one that clashes with what was published is reported, the copy is left as published", (rc, "ya no encaja" in out, G("status", "--porcelain", cwd=W).stdout), (1, True, ""))
web("descartar")
rc, out = web("variante", "borrar", "nieve")
check("variante borrar: gone, the site and the copy untouched", (rc, "nieve" in web("variante", "lista")[1], remote_refs()), (0, False, ["refs/heads/main"]))
check("variante borrar: an unknown name is an error", web("variante", "borrar", "nieve")[0], 1)
web("variante", "borrar", "estrellas")

# a crash left the folder on a variant branch: nothing pushes it, the next command is back on main
G("checkout", "-q", "-b", "hermes-variante-roto", cwd=W)
open(f"{W}/index.html", "a").write("<p>solo en la variante rota</p>\n"); G("commit", "-qam", "roto", cwd=W)
h0 = head(); rc, out = web("estado")
check("a folder left on a variant branch goes back to main before anything else", (rc, G("symbolic-ref", "--short", "HEAD", cwd=W).stdout.strip(), "roto" in open(f"{W}/index.html").read(), head() == h0),
      (0, "main", False, True))
G("branch", "-D", "hermes-variante-roto", cwd=W)

# =========================================================================== volver
tz = gw.now_local().tzinfo
today = gw.now_local().date()
at = lambda days, hhmm: datetime.datetime.combine(today - datetime.timedelta(days=days), datetime.time(*map(int, hhmm.split(":"))), tzinfo=tz).isoformat()
page = lambda v: f"<p>version {v}</p>\n"
origin, W = setup("volver", [
    (at(3, "12:00"), {"index.html": page(1), "viejo.html": "<p>viejo</p>\n"}, "dia -3"),
    (at(1, "10:00"), {"index.html": page(2), "extra.html": "<p>extra</p>\n"}, "ayer a la mañana"),
    (at(1, "22:00"), {"index.html": page(3)}, "ayer a la noche"),
    (at(0, "00:00"), {"index.html": page(4)}, "hoy a la madrugada"),
])
head = lambda: G(f"--git-dir={origin}", "rev-parse", "main").stdout.strip()
shown = lambda f="index.html": G(f"--git-dir={origin}", "show", f"main:{f}").stdout
count = lambda: int(G(f"--git-dir={origin}", "rev-list", "--count", "main").stdout)
web()
log0 = G(f"--git-dir={origin}", "rev-list", "main").stdout.split()
ds = lambda d: (today - datetime.timedelta(days=d)).isoformat()

check("volver: bad dates are refused", [web("volver", *a)[0] for a in (("mañana",), ("2999-01-01",), ())], [1, 1, 1])
rc, out = web("volver", "hace", "30", "días")
check("volver: before the first publication says so, nothing changes", (rc, "no tenía ninguna publicación" in out, head() == log0[0]), (1, True, True))
rc, out = web("volver", "hoy")
check("volver: today's end is the head: nothing to go back to", (rc, "ya está igual" in out, count()), (0, True, 4))

# default: the old files only go to the working copy, nothing is published, the day's publishes are listed
h1 = head(); rc, out = web("volver", "ayer")
check("volver ayer: stages the last publish of that day (22:00, not 10:00 and not today's), publishes nothing, lists both of yesterday's",
      (rc, head() == h1, count(), open(f"{W}/index.html").read(), G("diff", "--cached", "--name-only", cwd=W).stdout, "SIN publicar" in out, "gateway web publicar" in out,
       "ayer a la mañana" in out and "ayer a la noche" in out, "<- esta" in out, "dia -3" in out, "hoy a la madrugada" in out),
      (0, True, 4, page(3), "", True, True, True, True, False, False))
rc, out = web("vista")
check("volver ayer then vista: published (today) against yesterday's, asks before publishing", (rc, len(media(out)), "¿publico?" in out), (0, 2, True))
rc, out = web("publicar", f"Volver a como estaba el {ds(1)}")
check("volver ayer then publicar: a NEW commit on top, verified live, history only grows",
      (rc, shown(), count(), G(f"--git-dir={origin}", "rev-list", "main").stdout.split()[1:] == log0, "verificado en vivo" in out, G("status", "--porcelain", cwd=W).stdout), (0, page(3), 5, True, True, ""))
check("volver ayer: the person's file extra.html (existing then) is still there", shown("extra.html"), "<p>extra</p>\n")
rc, out = web("deshacer")
check("volver: deshacer undoes the volver (back to today's version), history only grows", (rc, shown(), count()), (0, page(4), 6))

# --directo: checks, publishes and verifies at once
rc, out = web("volver", "ayer", "--directo")
check("volver --directo: published at once, message names the day",
      (rc, shown(), count(), G(f"--git-dir={origin}", "log", "-1", "--format=%s", "main").stdout.strip(), "verificado en vivo" in out), (0, page(3), 7, f"Volver a como estaba el {ds(1)}", True))
rc, out = web("deshacer")
check("volver --directo: deshacer undoes it", (rc, shown(), count()), (0, page(4), 8))

# one commit of the day picked by its code (commit times are not push times: the person chooses among the listed ones)
rev = G(f"--git-dir={origin}", "rev-list", "main").stdout.split()
morning = next(h for h in rev if G(f"--git-dir={origin}", "log", "-1", "--format=%s", h).stdout.strip() == "ayer a la mañana")
rc, out = web("volver", morning[:7], "--directo")
check("volver CODE: that exact commit is restored, message has the code", (rc, shown(), G(f"--git-dir={origin}", "log", "-1", "--format=%s", "main").stdout.strip()),
      (0, page(2), f"Volver a como estaba el {ds(1)} ({morning[:7]})"))
web("deshacer")
check("volver CODE: an unknown code and a too short one are refused, nothing changes", [web("volver", c)[0] for c in ("deadbee", "ab")], [1, 1])
check("volver: weekday names (el lunes, sábado pasado) are the last such day before today",
      [(gw.web_when(a)[0].weekday(), 0 < (today - gw.web_when(a)[0]).days <= 7) for a in (["el", "lunes"], ["sábado", "pasado"], ["miercoles"])], [(0, True), (5, True), (2, True)])

h1 = head()
rc, out = web("volver", "hace", "3", "días", "--directo")
check("volver --directo: files that did not exist then need --borrar, are all listed, nothing pushed, copy back as published",
      (rc, "viejo.html" not in out, "extra.html" in out, "--borrar" in out, head() == h1, G("status", "--porcelain", cwd=W).stdout, shown("extra.html")),
      (1, True, True, True, True, "", "<p>extra</p>\n"))
rc, out = web("volver", "hace", "3", "días")
check("volver (staged): the files that would be deleted are listed, nothing pushed, the copy has them gone; descartar puts it back",
      (rc, "extra.html" in out, "--borrar" in out, head() == h1, os.path.exists(f"{W}/extra.html"), web("descartar")[0], open(f"{W}/extra.html").read()), (0, True, True, True, False, 0, "<p>extra</p>\n"))
rc, out = web("volver", ds(3), "--borrar", "--directo")
check("volver --borrar --directo with an ISO date: restored, extra.html deleted, viejo.html kept, new commit on top",
      (rc, shown(), G(f"--git-dir={origin}", "cat-file", "-e", "main:extra.html").returncode != 0, shown("viejo.html"), count()), (0, page(1), True, "<p>viejo</p>\n", 11))
rc, out = web("deshacer")
check("volver: deshacer brings extra.html back", (rc, shown("extra.html")), (0, "<p>extra</p>\n"))

# the old --ver spelling still means the default
h1 = head(); rc, out = web("volver", "anteayer", "--ver")
check("volver: anteayer is the day -3 publish (last before the end of day -2); only the working copy changes (--ver still accepted)",
      (rc, head() == h1, open(f"{W}/index.html").read(), G("diff", "--cached", "--name-only", cwd=W).stdout, "SIN publicar" in out, "--borrar" in out, "no hubo publicaciones" in out), (0, True, page(1), "", True, True, True))
web("descartar")

# commit times are not push times: a commit made on day -1 but pushed after one made on day -3 is on top of the history
origin, W = setup("volver2", [(at(1, "20:00"), {"index.html": page("A")}, "hecho ayer, subido antes"), (at(3, "09:00"), {"index.html": page("B")}, "hecho hace 3 días, subido después")])
web()
rc, out = web("volver", "ayer")
check("volver: a commit dated yesterday that sits under an older-dated one is listed and its code offered, never silently chosen",
      (rc, "hecho ayer, subido antes" in out, "gateway web volver CODIGO" in out, open(f"{W}/index.html").read()), (0, True, True, page("B")))
rc, out = web("volver", G(f"--git-dir={origin}", "rev-list", "main").stdout.split()[1][:7])
check("volver CODE: that commit can be picked", (rc, open(f"{W}/index.html").read()), (0, page("A")))
web("descartar")
check("volver: dirty copy is refused", (open(f"{W}/index.html", "a").write("x") and 0 or web("volver", "ayer")[0], "sin publicar" in web("volver", "ayer")[1]), (1, True))
G("checkout", "--", "index.html", cwd=W)
check("volver: DD/MM/AAAA is understood", gw.web_when([(today - datetime.timedelta(days=2)).strftime("%d/%m/%Y")])[0], today - datetime.timedelta(days=2))
logged = [json.loads(l) for l in open(os.environ["GATEWAY_LOG"]) if '"web"' in l]
check("web: the log has counts, never file names, pages or messages", any(k in json.dumps(logged) for k in ("index", "estrellas", "nieve", "viejo", "extra")), False)
gw.web_get, gw.WEB_WAIT, gw.WEB_POLL, gw.CONF = _get, _wait, _poll, _conf

# =========================================================================== one real render, when this machine can
def find_node_path():
    c = [os.environ.get("NODE_PATH", "")]
    c += glob.glob(os.path.expanduser("~/Documents/jobfinder/node_modules")) + glob.glob(os.path.expanduser("~/.npm/_npx/*/node_modules"))
    try:
        c.append(subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=30).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return next((p for p in c if p and os.path.isdir(os.path.join(p, "playwright"))), None)

np_ = find_node_path()
have_browser = bool(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium*")) or glob.glob("/opt/ms-playwright/chromium*"))
if shutil.which("node") and np_ and have_browser:
    os.environ["NODE_PATH"] = np_
    del os.environ["AIBRIDGE_WEB_RENDERER"]
    _, W = setup("real", [("2026-01-01T12:00:00+0000", {"index.html": '<link rel="stylesheet" href="https://example.invalid/x.css"><body style="margin:0"><div style="height:700px;background:#2a4"></div></body>\n'}, "seed")])
    web()
    open(f"{W}/index.html", "w").write('<link rel="stylesheet" href="https://example.invalid/x.css"><body style="margin:0"><div style="height:5000px;background:#c33"></div></body>\n')
    rc, out = web("vista")
    if rc and "Executable" in out:
        print("real render: skipped (the Chromium build Playwright wants is not installed)")
    else:
        ms = media(out)
        sizes = sorted(Image.open(m).size for m in ms)
        check("real render: two sheets, phone and desktop, taller page cut at 4000 css px and said, external host blocked",
              (rc, len(ms), "example.invalid" in out, "4000" in out), (0, 2, True, True))
        if len(ms) == 2:
            check("real render: the sheets have a plausible size and fit Telegram's width + height limit", (sizes[0][0] > 1000, sizes[0][1] > 4000, all(a + b <= 10000 for a, b in sizes)), (True, True, True))
        # the site's own scripts may call nothing but the served page: not another 127.0.0.1 port (the stack's MCP servers and
        # gateways listen there), not a WebSocket to one
        hits = []
        class Secret(http.server.BaseHTTPRequestHandler):
            def do_GET(self): hits.append("GET"); self.send_response(200); self.end_headers()
            def do_POST(self): hits.append("POST"); self.send_response(200); self.end_headers()
            def log_message(self, *a): pass
        sec = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Secret)
        threading.Thread(target=sec.serve_forever, daemon=True).start()
        wsock = socket.socket(); wsock.bind(("127.0.0.1", 0)); wsock.listen(5)
        def ws_listener():
            while True:
                try:
                    c, _ = wsock.accept()
                except OSError:
                    return
                hits.append("WS"); c.close()
        threading.Thread(target=ws_listener, daemon=True).start()
        sp, wp = sec.server_address[1], wsock.getsockname()[1]
        open(f"{W}/index.html", "w").write(f"<body style='margin:0'><div style='height:300px;background:#369'></div><script>"
            f"fetch('http://127.0.0.1:{sp}/a',{{mode:'no-cors'}});fetch('http://127.0.0.1:{sp}/b',{{mode:'no-cors',method:'POST',body:'x'}});"
            f"new Image().src='http://127.0.0.1:{sp}/c';try{{new WebSocket('ws://127.0.0.1:{wp}/')}}catch(e){{}}</script></body>\n")
        rc, out = web("vista")
        time.sleep(1)
        sec.shutdown(); wsock.close()
        check("real render: a page script reaching another 127.0.0.1 port (fetch, POST, image, WebSocket) gets nothing through, and the page still renders",
              (rc, len(media(out)), hits), (0, 2, []))
else:
    print("real render: skipped (needs node, playwright and a Chromium build)")

print("\n".join(fails) or "gateway_web_selftest: all checks passed")
sys.exit(1 if fails else 0)
