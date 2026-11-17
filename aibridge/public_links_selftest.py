#!/usr/bin/env python3
"""Selftest for public_links.py (the private-link filter of the answers) and for its place in the stack: one output hook that runs the jobs notice
and then the filter, the gateways_sync entry, the image, the SOUL line. Offline: python3 -I public_links_selftest.py"""
import importlib.util
import json
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="public-links-selftest-")
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def load(name, path, env=None):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


os.environ["GATEWAY_LOG"] = os.path.join(TMP, "gateway-log.jsonl")
os.environ["AIBRIDGE_PREFS"] = os.path.join(TMP, "prefs.json")
pl = load("public_links", os.path.join(HERE, "public_links.py"))
L = "192." + "168."          # the home-network prefix, written in two pieces so that no fixture reads as a real address

BOARD = {"url": "http://10.20.7.20:3000", "repo": "acme/tareas", "me": "bot-x", "peers": [], "humans": []}
NOMAP = pl.build_rules({"tareas": BOARD})
MAP = pl.build_rules({"tareas": BOARD, "public_urls": {"http://10.20.7.20:3000": "https://board.example.org",
                                                      "http://10.20.7.20:3000/acme": "https://tasks.example.org/a",
                                                      "http://llm:8630": "https://llm.example.org/"}})


def rw(text, rules=NOMAP, lang="en"):
    return pl.rewrite(text, rules, lang)[0]


def changed(url):
    return rw(f"see {url} now") != f"see {url} now"


# ---------------------------------------------------------------------------------------------------- what is private
private = ["http://127.0.0.1:8096/v1", "http://localhost:3000/x", "https://10.0.0.5", "http://172.16.0.1/", "http://172.31.255.254:80", f"http://{L}1.10:3000/difusores/x",
           "http://169.254.169.254/latest/meta-data", "http://100.64.0.1:80", "http://0.0.0.0:8080", "http://[::1]:8080/a", "http://[fe80::1%25eth0]/", "http://[fd12:3456::1]:9000/",
           f"http://[::ffff:{L}1.5]/x", "http://2130706433/", "http://0x7f.1/", "http://0177.0.0.1/", "http://nas.local/share", "http://printer.lan:631", "http://gitea:3000/o/r",
           "http://llm/v1", "http://host.docker.internal:11434", "http://svc.home.arpa/", "http://app.localdomain", "http://anything.localhost:3000",
           "http://" + L.replace(".", "-") + "1-5.nip.io/x", "http://10.0.0.1.sslip.io", "http://foo.localtest.me:3000", f"ws://{L}0.2:81/socket", "ftp://10.1.1.1/pub",
           "HTTP://LOCALHOST:9/X", f"http://user:pw@{L}1.1/admin", "http://１２７.０.０.１/"]
for u in private:
    check(f"private: {u}", changed(u))
public = ["https://example.com/a", "http://8.8.8.8/", "https://172.32.0.1/", "http://172.15.255.255", "http://192.169.0.1", "http://11.0.0.1", "https://sub.example.org:8443/x?y=1#z",
          "http://[2001:4860:4860::8888]/", "https://1.1.1.1.nip.io.example.com/", "https://t.me/channel", "http://100.128.0.1/"]
for u in public:
    check(f"public stays: {u}", not changed(u))
check("a URL with a public host and a private name in the userinfo is public", not changed(f"https://{L}1.1@example.com/x"))
check("a private host after a public userinfo is still private", changed(f"https://example.com@{L}1.1/x"))
check("the port is not a host: example.com:80 stays", not changed("http://example.com:80/x"))
check("a broken URL does not raise and is left alone", rw("http://[::1 and http:// and https://:80") is not None)

# ---------------------------------------------------------------------------------------------------- where URLs sit in the text
n = pl.NOTES["en"]["internal"]
check("bare URL with a trailing sentence dot: the dot stays", rw("Open http://127.0.0.1:8096/v1.") == f"Open ({n}).", rw("Open http://127.0.0.1:8096/v1."))
check("trailing comma, colon, exclamation", rw("a http://llm/x, b http://llm/y: c http://llm/z!").count("(") == 3 and rw("http://llm/x,").endswith(","))
check("a URL in parentheses keeps the closing parenthesis of the sentence", rw("(see http://llm/x) ok") == f"(see ({n})) ok", rw("(see http://llm/x) ok"))
check("a URL with its own parentheses is one URL", rw("http://llm/a_(b)/c ok") == f"({n}) ok", rw("http://llm/a_(b)/c ok"))
check("angle brackets: <url> is replaced whole", rw("go <http://10.0.0.1:81/x> now") == f"go ({n}) now", rw("go <http://10.0.0.1:81/x> now"))
md = rw(f"[the board](http://{L}1.5:3000/x/y/issues/9) ok")
check("markdown link: the text stays, the target becomes a note", md == f"the board ({n}) ok", md)
check("markdown link with a title", rw('[t](http://llm/x "title") z') == f"t ({n}) z", rw('[t](http://llm/x "title") z'))
check("markdown link whose text is the URL: only the note", rw("[http://llm/x](http://llm/x)") == f"({n})", rw("[http://llm/x](http://llm/x)"))
check("markdown link with a public target is untouched", rw("[a](https://example.com/x)") == "[a](https://example.com/x)")
check("markdown link with an IPv6 literal host", changed("[a](http://[::1]:80/x)") if False else rw("[a](http://[::1]:80/x)") == f"a ({n})", rw("[a](http://[::1]:80/x)"))
check("bold and emphasis marks after a URL are not part of it", rw("**http://llm/x**") == f"**({n})**", rw("**http://llm/x**"))
fence = "before\n```\ncurl http://127.0.0.1:8096/v1\nhttp://10.0.0.1/x\n```\nafter http://llm/z\n"
out = rw(fence)
check("a fenced code block is not touched, the text after it is", "curl http://127.0.0.1:8096/v1\nhttp://10.0.0.1/x" in out and "after (" in out and "http://llm/z" not in out, out)
tilde = "~~~sh\nhttp://llm/x\n~~~\nhttp://llm/y"
check("a ~~~ fence too", rw(tilde).startswith("~~~sh\nhttp://llm/x\n~~~\n(") , rw(tilde))
check("an unclosed fence protects to the end", rw("x\n```\nhttp://llm/x\nhttp://llm/y") == "x\n```\nhttp://llm/x\nhttp://llm/y")
check("inline code with a command is not touched", rw("run `curl http://127.0.0.1:8096/v1 -s` now") == "run `curl http://127.0.0.1:8096/v1 -s` now")
check("inline code that is exactly one URL is a link in backticks: replaced (the person cannot open it either)", rw("open `http://127.0.0.1:8096/v1` now") == f"open ({n}) now", rw("open `http://127.0.0.1:8096/v1` now"))
check("double-backtick code span", rw("a ``http://llm/x -v`` b") == "a ``http://llm/x -v`` b")
check("MEDIA: lines stay", rw("MEDIA: /workdir/descargas/a.png http://10.0.0.1/x\nhttp://llm/x") == f"MEDIA: /workdir/descargas/a.png http://10.0.0.1/x\n({n})")
check("MEDIA: line with an indent stays", rw("  MEDIA:/workdir/a.mp4") == "  MEDIA:/workdir/a.mp4")
paths = "files in /workdir/descargas/video.mp4 and /root/.hermes/x and ~/notes.txt and C:\\dir\\f, file:///workdir/a"
check("file paths and file: URLs are not touched", rw(paths) == paths)
check("a path that looks like a URL piece is not a URL", rw("/workdir/descargas/http_10.0.0.1.txt") == "/workdir/descargas/http_10.0.0.1.txt")
check("a bare IP with no scheme is not a link: untouched (network diagnostics talk about addresses)", rw(f"the router is {L}1.1 and the DNS 127.0.0.1:53") == f"the router is {L}1.1 and the DNS 127.0.0.1:53")
check("plain text with no URL is the same object, no work", pl.rewrite("hola", NOMAP, "es")[0] == "hola")
two = rw("a http://llm/x b http://llm/x c http://10.0.0.9/")
check("repeats of the same kind of note are shortened after the first", two.count(n) == 1 and two.count("(" + pl.NOTES["en"]["short"] + ")") == 2, two)

# ---------------------------------------------------------------------------------------------------- the map
check("map: the exact origin", rw("http://10.20.7.20:3000/zed/r/issues/1", MAP) == "https://board.example.org/zed/r/issues/1", rw("http://10.20.7.20:3000/zed/r/issues/1", MAP))
check("map: longest prefix wins", rw("http://10.20.7.20:3000/acme/tareas/issues/3", MAP) == "https://tasks.example.org/a/tareas/issues/3", rw("http://10.20.7.20:3000/acme/tareas/issues/3", MAP))
check("map: path boundary (acme2 is not acme)", rw("http://10.20.7.20:3000/acme2/x", MAP) == "https://board.example.org/acme2/x")
check("map: the exact prefix with no rest", rw("http://10.20.7.20:3000/acme", MAP) == "https://tasks.example.org/a" and rw("http://10.20.7.20:3000", MAP) == "https://board.example.org")
check("map: query and fragment are kept", rw("http://10.20.7.20:3000/x?a=1&b=2#top", MAP) == "https://board.example.org/x?a=1&b=2#top")
check("map: the port is part of the key (3001 is not 3000)", "board.example.org" not in rw("http://10.20.7.20:30001/x", MAP) and "board.example.org" not in rw("http://10.20.7.20:3001/x", MAP))
check("map: host and scheme are case-insensitive", rw("HTTP://10.20.7.20:3000/x", MAP) == "https://board.example.org/x")
check("map: a docker name key with the default port implied", rw("http://llm:8630/v1/chat", MAP) == "https://llm.example.org/v1/chat" and rw("http://llm/v1", MAP) != "https://llm.example.org/v1")
check("map: a different scheme does not match", "board.example.org" not in rw("https://10.20.7.20:3000/x", MAP))
check("map: in markdown and angle brackets the text is kept", rw("[b](http://10.20.7.20:3000/x) <http://10.20.7.20:3000/y>", MAP) == "[b](https://board.example.org/x) <https://board.example.org/y>", rw("[b](http://10.20.7.20:3000/x) <http://10.20.7.20:3000/y>", MAP))
check("map: a link in backticks becomes a plain link", rw("`http://10.20.7.20:3000/x`", MAP) == "https://board.example.org/x")
check("map: not applied inside a code fence", rw("```\nhttp://10.20.7.20:3000/x\n```", MAP) == "```\nhttp://10.20.7.20:3000/x\n```")
check("map: trailing punctuation kept", rw("see http://10.20.7.20:3000/x.", MAP) == "see https://board.example.org/x.")
bad = pl.build_rules({"public_urls": {"http://a:1": "http://10.0.0.1", "http://b:1": "javascript:alert(1)", "http://c:1": "https://ok.example.org", "nonsense": "https://x.example.org",
                                      "http://d:1": "https://ok.example.org/ x", 5: "https://x", "http://e:1": 7, "ftp://f:1": "http://localhost/x", "http://g:1": "https://[::1]/"}})
check("map: private, non-http, malformed and non-string entries are dropped", [r[1] for r in bad["map"]] == ["c"], str(bad["map"]))
check("map: a value that is private leaves the URL to the note", "(" in rw("http://a:1/x", bad))
check("a map for a name that looks public applies (an internal domain that only resolves inside)",
      rw("https://git.corp-intranet.example/x", pl.build_rules({"public_urls": {"https://git.corp-intranet.example": "https://git.example.org"}})) == "https://git.example.org/x")
check("no public_urls at all, or not a dict", pl.build_rules({})["map"] == [] and pl.build_rules({"public_urls": ["x"]})["map"] == [] and pl.build_rules(None)["map"] == [])
check("the answer's public URLs are never rewritten by the map", rw("https://example.com/x http://10.20.7.20:3000/q", MAP) == "https://example.com/x https://board.example.org/q")

# ---------------------------------------------------------------------------------------------------- the task board alternative
t = rw("Tarea: http://10.20.7.20:3000/acme/tareas/issues/12 y también http://10.20.7.20:3000/acme/tareas/pulls/4/files", NOMAP, "es")
check("task board: the issue number and the command to see it, in Spanish", "tarea #12 del tablero interno" in t and "`gateway tareas ver 12`" in t and "10.20" not in t, t)
check("task board: a pull request has its number too", "#4" in t or "tarea #" in t)
check("task board in English and Russian", "task #12 on the internal board" in rw("http://10.20.7.20:3000/acme/tareas/issues/12", NOMAP, "en") and "задача #12" in rw("http://10.20.7.20:3000/acme/tareas/issues/12", NOMAP, "ru"))
check("task board: the repo page gives the list command", "gateway tareas listar" in rw("http://10.20.7.20:3000/acme/tareas", NOMAP, "en") and "gateway tareas listar" in rw("http://10.20.7.20:3000/acme/tareas/issues", NOMAP, "en"))
check("task board: another repo of the same server gets the plain internal note, no invented number", "internal board link" in rw("http://10.20.7.20:3000/difusores/web/issues/5", NOMAP, "en"))
check("task board: a different server is not the board", "task #" not in rw("http://10.20.7.21:3000/acme/tareas/issues/12", NOMAP, "en"))
check("task board: a markdown link to an issue keeps its text and gets the number", rw("[Issue 12](http://10.20.7.20:3000/acme/tareas/issues/12)", NOMAP, "en").startswith("Issue 12 (task #12"))
check("task board: mapped, the issue link is the public one, not the note", rw("http://10.20.7.20:3000/acme/tareas/issues/12", MAP, "en") == "https://tasks.example.org/a/tareas/issues/12")
pub_board = pl.build_rules({"tareas": {"url": "https://git.example.org", "repo": "acme/tareas", "me": "b"}})
check("task board on a public server: its links are left alone", rw("https://git.example.org/acme/tareas/issues/1", pub_board, "en") == "https://git.example.org/acme/tareas/issues/1")

# ---------------------------------------------------------------------------------------------------- languages
for lg, word in (("es", "enlace interno"), ("ru", "внутренняя ссылка"), ("en", "internal link")):
    check(f"note language {lg}", word in rw("http://llm/x", NOMAP, lg))
check("an unknown language falls back to Spanish", "enlace interno" in rw("http://llm/x", NOMAP, "xx"))
json.dump({"lang": "ru"}, open(os.environ["AIBRIDGE_PREFS"], "w"))
check("person_lang: the person's /settings language wins over the text", pl.person_lang("hello there, this is a long english answer for you today") == "ru")
os.remove(os.environ["AIBRIDGE_PREFS"])
check("person_lang: Cyrillic text = ru, long ASCII = en, otherwise es", pl.person_lang("Готово") == "ru" and pl.person_lang("Here is a long answer in plain English words for you.") == "en" and pl.person_lang("Listo, ahí está") == "es")

# ---------------------------------------------------------------------------------------------------- counters and the file
logp = os.environ["GATEWAY_LOG"]
gw = os.path.join(TMP, "gateways.json")
json.dump({"tareas": BOARD, "public_urls": {"http://10.20.7.20:3000": "https://board.example.org"}}, open(gw, "w"))
r = pl.filter_text("Mirá http://10.20.7.20:3000/acme/tareas/issues/1 y http://127.0.0.1:8096/v1 y https://example.com", platform="telegram", lang="en", conf_path=gw, log=logp)
check("filter_text: maps one, notes the other, leaves the public one", r == "Mirá https://board.example.org/acme/tareas/issues/1 y (" + pl.NOTES["en"]["internal"] + ") y https://example.com", r)
rec = [json.loads(l) for l in open(logp)]
check("one counter line: cmd links, how many, by class, platform; no URL text, host or port",
      len(rec) == 1 and rec[0]["cmd"] == "links" and rec[0]["mapped"] == 1 and rec[0]["noted"] == 1 and rec[0]["classes"] == {"loopback": 1} and rec[0]["platform"] == "telegram"
      and not re.search(r"192|127|8096|3000|example|http", open(logp).read()), str(rec))
check("filter_text: nothing changed = None and no log line", pl.filter_text("hola https://example.com", conf_path=gw, log=logp) is None and len(open(logp).read().splitlines()) == 1)
check("filter_text: a non-string, an empty text", pl.filter_text(None) is None and pl.filter_text("") is None)
time.sleep(0.05)
json.dump({"tareas": BOARD}, open(gw, "w"))
os.utime(gw, (time.time() + 5, time.time() + 5))
check("the file is read again when it changes (the operator edits gateways.json without a restart)", "(" in (pl.filter_text("http://10.20.7.20:3000/x", lang="en", conf_path=gw, log=logp) or ""))
check("a missing or broken gateways.json still applies the notes", "(" in (pl.filter_text("http://127.0.0.1/x", lang="en", conf_path=os.path.join(TMP, "none.json"), log=logp) or ""))
open(gw, "w").write("{not json")
os.utime(gw, (time.time() + 9, time.time() + 9))
check("a broken file does not raise", "(" in (pl.filter_text("http://127.0.0.1/x", lang="en", conf_path=gw, log=logp) or ""))
check("public_form (what tareas prints): mapped, public, private", pl.public_form("http://a:1/x", {"public_urls": {"http://a:1": "https://p.example.org"}}) == "https://p.example.org/x"
      and pl.public_form("https://example.com/x", {}) == "https://example.com/x" and pl.public_form("http://a:1/x", {}) is None)

# ---------------------------------------------------------------------------------------------------- never raises
hostile = ["http://" + "[" * 5000, "http://" + "a" * 100000, "`" * 500 + "http://llm/x", "```" * 300, "[" * 300 + "](http://llm/" + "(" * 300, "<" * 1000 + "http://llm/x", "http://%zz/\x00\x01", "http://[::1", "\u202ehttp://llm/x"]
t0 = time.time()
for h in hostile:
    try:
        pl.rewrite(h, MAP, "en")
        ok = True
    except Exception as exc:
        ok = False
        print("   raised", repr(exc)[:80])
    check(f"hostile input does not raise: {h[:20]!r}", ok)
check("hostile inputs finish quickly (no catastrophic backtracking)", time.time() - t0 < 5, f"{time.time() - t0:.1f}s")

# ---------------------------------------------------------------------------------------------------- one output hook, the notice first
plugin_dir = os.path.join(HERE, "hermes_plugins")
hooks = []
for d in sorted(os.listdir(plugin_dir)):
    src = open(os.path.join(plugin_dir, d, "__init__.py")).read() if os.path.isfile(os.path.join(plugin_dir, d, "__init__.py")) else ""
    if re.search(r"register_hook\(\s*[\"']transform_llm_output[\"']", src):
        hooks.append(d)
check("exactly one plugin registers transform_llm_output (Hermes uses only the first transform that returns a string)", hooks == ["aibridge-jobs"], str(hooks))

os.environ["TRABAJOS_DIR"] = os.path.join(TMP, "ledger")
os.environ["TRABAJOS_MODULE"] = os.path.join(HERE, "trabajos.py")
os.environ["PUBLIC_LINKS_MODULE"] = os.path.join(HERE, "public_links.py")
json.dump({"tareas": BOARD, "public_urls": {"http://10.20.7.20:3000": "https://board.example.org"}}, open(gw, "w"))
jp = load("jobs_plugin", os.path.join(HERE, "hermes_plugins", "aibridge-jobs", "__init__.py"))
jp._links().CONF = gw
jp._links().LOG = os.path.join(TMP, "plugin-log.jsonl")
tr = jp._ledger()
c1 = tr.start("clip v2", "video", "gateway makevideo --secs 5 -- 'a car' /workdir/descargas/v2.mp4", pid=None)
tr.finish(c1, 143, state="cortado", reason="stopped by a signal")
ans = "Listo: http://10.20.7.20:3000/acme/tareas/issues/2 y http://127.0.0.1:8096/v1\nMEDIA: /workdir/descargas/v2.mp4"
out = jp.transform_llm_output(response_text=ans, platform="telegram", turn_id="1")
check("the hook: the jobs notice FIRST, then the answer with its links mapped or replaced, MEDIA line intact",
      isinstance(out, str) and out.startswith("⚠️ ") and "clip v2" in out and out.index("clip v2") < out.index("Listo:") and "https://board.example.org/acme/tareas/issues/2" in out
      and "127.0.0.1" not in out and out.endswith("MEDIA: /workdir/descargas/v2.mp4"), repr(out))
out = jp.transform_llm_output(response_text="Otra: http://127.0.0.1:1/x", platform="api_server", turn_id="2")
check("the notice is acknowledged (no second notice) and the link filter still runs on the web chat", isinstance(out, str) and not out.startswith("⚠️") and "127.0.0.1" not in out, repr(out))
out = jp.transform_llm_output(response_text="Sin enlaces, https://example.com ok.", platform="telegram", turn_id="3")
check("nothing to say and no private link: None (the answer is not touched)", out is None, repr(out))
out = jp.transform_llm_output(response_text="cron: http://127.0.0.1:1/x", platform="cron", turn_id="4")
check("cron: no notice, but the link filter applies (cron answers reach people too)", isinstance(out, str) and "127.0.0.1" not in out and "⚠️" not in out, repr(out))
c2 = tr.start("clip v3", "video", "gateway makevideo --secs 5 -- 'a bus' /workdir/descargas/v3.mp4", pid=None)
tr.finish(c2, 1, reason="GPU busy")
out = jp.transform_llm_output(response_text="Hola, nada de links.", platform="telegram", turn_id="5")
check("a notice alone still works when the answer has no link", isinstance(out, str) and out.startswith("⚠️ ") and out.endswith("Hola, nada de links."), repr(out))
jp._state["links"] = False
out = jp.transform_llm_output(response_text="x http://127.0.0.1:1/x", platform="telegram", turn_id="6")
check("without the public_links module the hook returns None (never breaks a turn)", out is None, repr(out))
jp._state["links"] = None
_l = jp._links
jp._links = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
check("a filter error is swallowed", jp.transform_llm_output(response_text="x http://127.0.0.1:1/x", platform="telegram", turn_id="7") is None)
jp._links = _l

# ---------------------------------------------------------------------------------------------------- wiring
dock = open(os.path.join(HERE, "Dockerfile.hermes-agent")).read()
check("the Dockerfile installs public_links as a library under /usr/local/lib/aibridge", "COPY public_links.py /usr/local/lib/aibridge/public_links.py\n" in dock)
soul = open(os.path.join(HERE, "SOUL_bridgeai.md")).read()
check("the SOUL has the one line about private URLs", "Never write a URL on this installation's private network" in soul)
gs = load("gateways_sync", os.path.join(HERE, "ops", "gateways_sync.py"))
master = {"hosts": {}, "public_urls": {"http://g:3000": "https://g.example.org", "http://h:1": "https://h.example.org"},
          "stacks": {"s1": {"public_urls": {"http://g:3000": "https://g2.example.org", "bad": "https://x", "http://i:1": 5}}, "s2": {}}}
check("gateways_sync: the installation's map goes to every stack, the stack's own wins per key, junk is dropped",
      gs.build(master, "s1").get("public_urls") == {"http://g:3000": "https://g2.example.org", "http://h:1": "https://h.example.org"}
      and gs.build(master, "s2").get("public_urls") == {"http://g:3000": "https://g.example.org", "http://h:1": "https://h.example.org"}
      and "public_urls" not in gs.build({"hosts": {}, "stacks": {"s": {}}}, "s"))
check("gateways_sync: the summary shows a count, not the addresses", gs.summary(gs.build(master, "s1"))["public_urls"] == "2 mapped")
ex = json.load(open(os.path.join(HERE, "ops", "gateways.json.example")))
check("the gateways.json example is valid JSON, has the map and every example value is public", isinstance(ex.get("public_urls"), dict)
      and all(not pl.is_private_url(v) or "<" in v for v in ex["public_urls"].values()) and "public_urls" in ex["_comment"])
arch = open(os.path.join(HERE, "..", "HERMES_ARCHITECTURE.md")).read()
check("HERMES_ARCHITECTURE.md documents the filter and the one-hook rule", "public_urls" in arch and "public_links.py" in arch and "only the first `transform_llm_output`" in arch)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("public_links_selftest: all ok")
