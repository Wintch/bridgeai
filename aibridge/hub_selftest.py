#!/usr/bin/env python3
"""Offline selftest of the hub (hub/): store, inbox, run loop, feeds, collectors, the person's CLI and the host starter's decision.
No network, no docker, no real yt-dlp: collectors are fakes or run against a fake subs-fetch script."""
import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import time
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "hub"), HERE]
import hubcore  # noqa: E402
import collectors  # noqa: E402
import hub_start  # noqa: E402
import hub_client  # noqa: E402

hubcore.load_ok_default = lambda: True   # the tests must not depend on this machine's memory
FAILS = []


def check(cond, msg):
    print(("ok " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def quiet(msg):
    pass


class Fake(hubcore.Collector):
    kind = "fake"
    default_interval_min = 60

    def __init__(self):
        self.calls, self.behaviour = [], "items"

    def canonical(self, key, params):
        if not key.startswith("ok-"):
            raise ValueError("keys of this kind start with ok-")
        return key, {}, key

    def collect(self, ctx, source):
        self.calls.append(source["key"])
        if self.behaviour == "throttle":
            raise hubcore.Throttled(120, "slow down")
        if self.behaviour == "boom":
            raise RuntimeError("site down")
        if self.behaviour == "empty":
            return []
        text_rel = os.path.join("fake", "t1.txt")
        os.makedirs(ctx.store("fake"), exist_ok=True)
        open(os.path.join(ctx.data, "store", text_rel), "w").write("the full text\n")
        a, b = ("AAAA1111", "BBBB2222") if source["key"] == "ok-shared" else (hashlib.sha1((source["key"] + "a").encode()).hexdigest()[:10],
                                                                           hashlib.sha1((source["key"] + "b").encode()).hexdigest()[:10])
        return [{"ext_id": a, "title": "First", "url": "https://x.example/1", "excerpt": "excerpt one", "fulltext": text_rel},
                {"ext_id": b, "title": "Second", "url": "https://x.example/2", "excerpt": "excerpt two"}]


def drop(data, person, req, name=None):
    inbox = os.path.join(data, "people", person, "inbox")
    os.makedirs(inbox, exist_ok=True)
    name = name or f"r{len(os.listdir(inbox))}.json"
    open(os.path.join(inbox, name), "w").write(req if isinstance(req, str) else json.dumps(req))


def mk(data, *persons):
    for p in persons:
        os.makedirs(os.path.join(data, "people", p, "inbox"), exist_ok=True)


def requests_of(data, person):
    return json.load(open(os.path.join(data, "people", person, "requests.json")))


# ---------- canonical keys: the only code that sees what a person typed ----------
yt, rss = collectors.YouTube(), collectors.RSS()
good = yt.canonical("https://www.youtube.com/@SomeChannel/videos", {"captions": "es-orig"})
check(good == ("https://www.youtube.com/@SomeChannel", {"captions": "es-orig"}, "@SomeChannel"), f"youtube: a channel address is normalised ({good[0]})")
for bad, params, why in [
    ("https://youtube.com.evil.example/@x", {"captions": "es-orig"}, "lookalike host"),
    ("https://youtube.com@evil.example/@x", {"captions": "es-orig"}, "user info"),
    ("https://www.youtube.com/watch?v=AAAAAAAAAAA", {"captions": "es-orig"}, "a video, not a channel"),
    ("https://www.youtube.com/@x", {}, "no captions language"),
    ("https://www.youtube.com/@x", {"captions": "es; rm -rf /"}, "odd captions language"),
    ("file:///etc/passwd", {"captions": "es-orig"}, "file scheme"),
]:
    try:
        yt.canonical(bad, params)
        check(False, f"youtube refuses {why}")
    except ValueError:
        check(True, f"youtube refuses {why}")

collectors.RSS.public_check = staticmethod(lambda h: not h.startswith("10.") and h != "localhost")
for bad, why in [("http://localhost/feed", "loopback name"), ("http://10.1.2.3/feed", "private address"),
                 ("https://user:pw@news.example/feed", "credentials"), ("https://news.example:8443/feed", "odd port"), ("ftp://news.example/f", "scheme")]:
    try:
        rss.canonical(bad, {})
        check(False, f"rss refuses {why}")
    except ValueError:
        check(True, f"rss refuses {why}")
check(rss.canonical("HTTPS://News.Example/feed.xml#top", {})[0] == "https://news.example/feed.xml", "rss: host lowercased, fragment dropped")

# ---------- rss parsing ----------
RSS_DOC = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>One</title><link>https://n.example/1</link><guid>g1</guid><description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description></item>
<item><title>Two</title><link>javascript:alert(1)</link><description>no link</description></item></channel></rss>"""
items = collectors.RSS.parse(RSS_DOC)
check(len(items) == 2 and items[0]["excerpt"] == "Hello world" and items[0]["url"] == "https://n.example/1", "rss: items, HTML stripped from the text")
check(items[1]["url"] is None, "rss: a javascript: link is dropped")
check(collectors.RSS.parse(RSS_DOC, salt="a")[0]["ext_id"] != collectors.RSS.parse(RSS_DOC, salt="b")[0]["ext_id"], "rss: the same article in two feeds gets two item ids")
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A</title><id>urn:a</id><link href="https://n.example/a"/><summary>sum</summary></entry></feed>"""
check(collectors.RSS.parse(ATOM)[0]["url"] == "https://n.example/a", "rss: Atom entries work too")
try:
    collectors.RSS.parse(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>')
    check(False, "rss refuses a DTD with entities")
except ValueError:
    check(True, "rss refuses a DTD with entities")

# ---------- rss: big feeds are read in streaming, only up to their first entries ----------
def big_feed(n, body_bytes):
    yield b'<?xml version="1.0"?><rss version="2.0"><channel><title>Big</title>'
    for i in range(n):
        yield (f"<item><title>Advisory {i}</title><link>https://n.example/a{i}</link><guid>g{i}</guid>"
               f"<description>{'x' * body_bytes}</description></item>").encode()
    yield b"</channel></rss>"


def rechunk(parts, size=collectors.RSS_CHUNK):
    buf = b""
    for p in parts:
        buf += p
        while len(buf) >= size:
            yield buf[:size]
            buf = buf[size:]
    if buf:
        yield buf


pulled = [0]


def counted(gen):
    for c in gen:
        pulled[0] += len(c)
        yield c


items = collectors.RSS.parse_stream(counted(rechunk(big_feed(400, 30_000))), salt="https://n.example/big")   # about 12 MB
check(len(items) == collectors.RSS_ITEMS and items[0]["title"] == "Advisory 0" and items[-1]["title"] == f"Advisory {collectors.RSS_ITEMS - 1}",
      "rss: a feed far above 2 MB gives its first entries, in order")
check(pulled[0] < 2 * collectors.RSS_ITEMS * 30_000, "rss: the rest of a big feed is never read")
check(collectors.RSS.parse_stream(rechunk(big_feed(3, 10)), salt="s") == collectors.RSS.parse(b"".join(big_feed(3, 10)), salt="s"),
      "rss: streaming and whole-document reading give the same items")
saved = collectors.RSS_STREAM_MAX_BYTES
collectors.RSS_STREAM_MAX_BYTES = 200_000
try:
    collectors.RSS.parse_stream(rechunk([b'<?xml version="1.0"?><rss><channel><title>' + b"x" * 400_000 + b"</title></channel></rss>"]))
    check(False, "rss: refuses a feed that is huge before its first entry")
except RuntimeError:
    check(True, "rss: refuses a feed that is huge before its first entry")
finally:
    collectors.RSS_STREAM_MAX_BYTES = saved
doc = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
try:
    collectors.RSS.parse_stream([doc[:28], doc[28:]])   # the DOCTYPE keyword split across two chunks
    check(False, "rss: a DTD split across two chunks is still refused")
except ValueError:
    check(True, "rss: a DTD split across two chunks is still refused")
quoted = (b'<?xml version="1.0"?><rss><channel><item><title>XXE in a parser</title><guid>q1</guid>'
          b'<description><![CDATA[payload: <!ENTITY xxe SYSTEM "file:///etc/passwd">]]></description></item></channel></rss>')
check(len(collectors.RSS.parse(quoted)) == 1, "rss: an advisory that quotes <!ENTITY in its text is still read")
commented = b'<?xml version="1.0"?><!-- generated --><rss><channel><item><title>C</title><guid>c1</guid></item></channel></rss>'
check(len(collectors.RSS.parse_stream([commented[:23], commented[23:26], commented[26:]])) == 1, "rss: a comment before the root, split across chunks, is fine")


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeOpener:
    def __init__(self, data):
        self.data = data

    def open(self, req, timeout=None):
        return FakeResp(self.data)


saved_opener = collectors.RSS.opener_factory
collectors.RSS.opener_factory = staticmethod(lambda: FakeOpener(b"".join(big_feed(100, 40_000))))   # about 4 MB, like the large agency feeds
try:
    got = collectors.RSS().collect(None, {"key": "https://n.example/all.xml"})
    check(len(got) == collectors.RSS_ITEMS, "rss: collect reads a 4 MB feed instead of failing on it")
finally:
    collectors.RSS.opener_factory = saved_opener

# ---------- request files ----------
with tempfile.TemporaryDirectory() as d:
    mk(d, "pa")
    p = os.path.join(d, "people", "pa", "inbox")
    open(os.path.join(p, "big.json"), "w").write(" " * 5000)
    open(os.path.join(p, "bad.json"), "w").write("{nope")
    open(os.path.join(d, "secret.txt"), "w").write('{"op":"subscribe"}')
    os.symlink(os.path.join(d, "secret.txt"), os.path.join(p, "link.json"))
    for n, why in (("big.json", "too large"), ("bad.json", "not JSON"), ("link.json", "a symlink")):
        try:
            hubcore.read_request(os.path.join(p, n))
            check(False, f"request refused: {why}")
        except ValueError:
            check(True, f"request refused: {why}")

# ---------- run loop, sharing, privacy between people ----------
with tempfile.TemporaryDirectory() as d:
    fake = Fake()
    cols = {"fake": fake}
    mk(d, "pa", "pb", "pc")
    now = 1_000_000.0
    drop(d, "pa", {"op": "subscribe", "kind": "fake", "key": "ok-shared", "lang": "es"})
    drop(d, "pb", {"op": "subscribe", "kind": "fake", "key": "ok-shared", "lang": "ru"})
    drop(d, "pb", {"op": "subscribe", "kind": "fake", "key": "ok-private-b", "lang": "es"})
    drop(d, "pc", {"op": "subscribe", "kind": "fake", "key": "nope", "lang": "es"})
    drop(d, "pc", {"op": "subscribe", "kind": "nothing", "key": "x"})
    drop(d, "pc", {"op": "subscribe", "kind": "fake", "key": "ok-x", "lang": "xx"})
    drop(d, "pc", {"op": "exec", "cmd": "id"})
    drop(d, "pc", "[]")
    st = hubcore.run(d, cols, now=now, log=quiet)
    db = hubcore.open_db(d)
    check(db.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2, "two people on the same key share ONE source")
    check(fake.calls.count("ok-shared") == 1, "a shared source is collected once")
    check(st["checked"] == 2 and st["new_items"] == 4, f"run stats count checks and new items ({st['checked']}, {st['new_items']})")
    pc = requests_of(d, "pc")
    check(len(pc) == 5 and all(r["status"] == "rejected" for r in pc), "invalid requests (key, kind, lang, op, shape) are all rejected, none applied")
    check(os.listdir(os.path.join(d, "people", "pa", "inbox")) == [], "handled request files are removed from the inbox")
    fa = sqlite3.connect(os.path.join(d, "people", "pa", "feed.db"))
    fb = sqlite3.connect(os.path.join(d, "people", "pb", "feed.db"))
    check({r[0] for r in fa.execute("SELECT key FROM sources")} == {"ok-shared"}, "person A sees only their own sources")
    check(len(fb.execute("SELECT id FROM sources").fetchall()) == 2, "person B sees theirs")
    check("ok-private-b" not in open(os.path.join(d, "people", "pa", "feed.json")).read(), "A's manifest does not mention B's source")
    check(os.path.isfile(os.path.join(d, "people", "pa", "full", "fa_AAAA1111.txt")) and fa.execute("SELECT has_full FROM items WHERE id='fa:AAAA1111'").fetchone()[0] == 1,
          "an item with a full text gets a file in the person's own full/")
    check(not os.path.exists(os.path.join(d, "people", "pc", "full", "fa_AAAA1111.txt")), "a person who does not follow it gets no file")
    check(os.stat(os.path.join(d, "people", "pa", "full", "fa_AAAA1111.txt")).st_ino == os.stat(os.path.join(d, "store", "fake", "t1.txt")).st_ino, "the person's file is a hardlink, not a copy")
    nw = float(open(os.path.join(d, "state", "next-wake")).read())
    check(nw == now + 3600, "next-wake = the earliest next_due")
    # nothing due: no collection, but the run still exits cleanly
    fake.calls.clear()
    st2 = hubcore.run(d, cols, now=now + 60, log=quiet)
    check(not fake.calls and st2["checked"] == 0, "nothing due: nothing collected")
    # quiet checks counter and the "nothing since" data
    fake.behaviour = "empty"
    hubcore.run(d, cols, now=now + 3700, log=quiet)
    hubcore.run(d, cols, now=now + 7400, log=quiet)
    m = json.load(open(os.path.join(d, "people", "pa", "feed.json")))
    check(m["sources"][0]["checks_since_new"] == 2 and m["sources"][0]["last_new"] == now, "manifest says how many checks found nothing, and since when")
    # throttle: the whole kind waits, other work continues
    fake.behaviour = "throttle"; fake.calls.clear()
    hubcore.run(d, cols, now=now + 11000, log=quiet)
    check(len(fake.calls) == 1, "a throttle stops that kind for the rest of the run")
    fake.calls.clear()
    hubcore.run(d, cols, now=now + 11000 + 3600, log=quiet)
    check(not fake.calls, "and for its whole cooldown (120 min)")
    check(float(open(os.path.join(d, "state", "next-wake")).read()) >= now + 11000 + 7200, "next-wake respects the cooldown")
    fake.behaviour = "items"
    hubcore.run(d, cols, now=now + 11000 + 7300, log=quiet)
    check(len(fake.calls) >= 1, "after the cooldown it collects again")
    # failure backoff
    fake.behaviour = "boom"; fake.calls.clear()
    t = now + 40000
    hubcore.run(d, cols, now=t, log=quiet)
    s = db.execute("SELECT fail_count, next_due, last_error FROM sources WHERE key='ok-shared'").fetchone()
    db.close(); db = hubcore.open_db(d)
    s = db.execute("SELECT fail_count, next_due, last_error FROM sources WHERE key='ok-shared'").fetchone()
    check(s[0] == 1 and s[1] == t + 120 * 60 and "site down" in s[2], "a failing source backs off (interval x2) and keeps the reason")
    check("site down" not in open(os.path.join(d, "people", "pa", "feed.json")).read(), "the reason stays private to the operator; the person only sees 'failing'")
    # unsubscribe removes the person's view, keeps the store
    fake.behaviour = "items"
    drop(d, "pa", {"op": "unsubscribe", "source": hubcore.source_id("fake", "ok-shared")})
    hubcore.run(d, cols, now=t + 10, log=quiet)
    check(not os.path.exists(os.path.join(d, "people", "pa", "full", "fa_AAAA1111.txt")) and os.path.exists(os.path.join(d, "store", "fake", "t1.txt")),
          "unsubscribing removes the person's link and leaves the shared store alone")
    check(os.path.exists(os.path.join(d, "people", "pb", "full", "fa_AAAA1111.txt")), "the other follower keeps theirs")
    # quota
    mk(d, "pq")
    for i in range(hubcore.MAX_SOURCES_PER_PERSON + 2):
        drop(d, "pq", {"op": "subscribe", "kind": "fake", "key": f"ok-q{i}", "lang": "es"}, name=f"q{i:03d}.json")
    hubcore.run(d, cols, now=t + 20, log=quiet)
    qs = requests_of(d, "pq")
    check(sum(r["status"] == "ok" for r in qs) == hubcore.MAX_SOURCES_PER_PERSON and sum(r["status"] == "rejected" for r in qs) == 2, "per-person subscription quota is enforced")
    # only-new: sources never collected
    drop(d, "pb", {"op": "subscribe", "kind": "fake", "key": "ok-brand-new", "lang": "es"})
    fake.calls.clear()
    hubcore.run(d, cols, now=t + 30 + 10 ** 6, only_new=True, log=quiet)
    check(fake.calls == ["ok-brand-new"], "--only-new collects only sources never collected")
    # fetch op
    drop(d, "pb", {"op": "fetch", "item": "fa:AAAA1111"}, name="f1.json")
    drop(d, "pb", {"op": "fetch", "item": "fa:BBBB2222"}, name="f2.json")
    drop(d, "pb", {"op": "fetch", "item": "fa:NOTMINE0"}, name="f3.json")
    hubcore.run(d, cols, now=t + 40, log=quiet)
    msgs = {r["file"]: (r["status"], r["message"]) for r in requests_of(d, "pb")}
    check(msgs["f1.json"][0] == "ok" and msgs["f2.json"][0] == "rejected" and msgs["f3.json"][0] == "rejected", "fetch: has full text / only excerpt / not in your feed")
    db.close()

# ---------- summaries ----------
class LLM:
    model = "fake-model"
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []
    def summarize(self, title, text, lang):
        self.calls.append((title, lang))
        if self.fail:
            raise RuntimeError("provider down")
        return f"summary of {title} in {lang}"

with tempfile.TemporaryDirectory() as d:
    mk(d, "pa", "pb", "pc")
    cols = {"fake": Fake()}
    drop(d, "pa", {"op": "subscribe", "kind": "fake", "key": "ok-s", "lang": "es"})
    drop(d, "pb", {"op": "subscribe", "kind": "fake", "key": "ok-s", "lang": "es"})
    drop(d, "pc", {"op": "subscribe", "kind": "fake", "key": "ok-s", "lang": "ru"})
    llm = LLM()
    st = hubcore.run(d, cols, now=2_000_000.0, llm=llm, log=quiet)
    check(len(llm.calls) == 4 and st["summaries"] == 4, f"one summary per item and language, not per person ({len(llm.calls)} calls for 3 people)")
    fa = sqlite3.connect(os.path.join(d, "people", "pa", "feed.db")); fc = sqlite3.connect(os.path.join(d, "people", "pc", "feed.db"))
    check(fa.execute("SELECT summary FROM items WHERE title='First'").fetchone()[0] == "summary of First in es" and
          fc.execute("SELECT summary FROM items WHERE title='First'").fetchone()[0] == "summary of First in ru", "each person gets the summary in their language")
    llm2 = LLM()
    hubcore.run(d, cols, now=2_000_100.0, llm=llm2, log=quiet)
    check(not llm2.calls, "an item already summarised is never summarised again")
with tempfile.TemporaryDirectory() as d:
    mk(d, "pa")
    cols = {"fake": Fake()}
    drop(d, "pa", {"op": "subscribe", "kind": "fake", "key": "ok-s", "lang": "es"})
    llm = LLM(fail=True)
    st = hubcore.run(d, cols, now=3_000_000.0, llm=llm, log=quiet)
    check(st["summaries"] == 0 and sqlite3.connect(os.path.join(d, "people", "pa", "feed.db")).execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2,
          "a failing summariser costs nothing: items still published with their excerpt")
    check(os.environ.get("HUB_LLM_KEY") or hubcore.HttpLLM.from_env() is None, "summaries are off unless the three HUB_LLM_* variables are set")

# ---------- youtube collector against a fake subs-fetch ----------
FAKE_FETCH = r'''#!/usr/bin/env python3
import json, os, sys, time
url, d = sys.argv[1], sys.argv[2]
mode = open(os.path.join(os.path.dirname(d), "mode")).read().strip()
os.makedirs(d, exist_ok=True)
if mode == "limited":
    open(os.path.join(os.path.dirname(os.path.abspath(d)), ".subs-cooldown"), "w").write(str(time.time() + 3 * 3600))
    sys.exit(75)
if mode == "crash":
    print("boom"); sys.exit(1)
srt = "1\n00:00:01,000 --> 00:00:04,000\nHello there\n\n2\n00:00:05,000 --> 00:01:30,000\nsecond line of the video\n"
for vid, title in (("AAAAAAAAAAA", "Video One"), ("BBBBBBBBBBB", "Video Two")):
    open(os.path.join(d, f"{title} [{vid}].es-orig.srt"), "w").write(srt)
json.dump({"url": url, "ts": time.time(), "ids": ["BBBBBBBBBBB", "AAAAAAAAAAA"]}, open(os.path.join(d, ".ids.cache"), "w"))
'''
with tempfile.TemporaryDirectory() as d:
    script = os.path.join(d, "fake_fetch.py")
    open(script, "w").write(FAKE_FETCH)
    os.environ["HUB_SUBS_FETCH"] = f"{sys.executable} {script}"
    cols = collectors.registry()
    mk(d, "pa")
    os.makedirs(os.path.join(d, "store", "youtube"), exist_ok=True)
    open(os.path.join(d, "store", "youtube", "mode"), "w").write("ok")
    drop(d, "pa", {"op": "subscribe", "kind": "youtube", "key": "https://www.youtube.com/@Chan", "lang": "es", "params": {"captions": "es-orig"}})
    st = hubcore.run(d, cols, now=4_000_000.0, log=quiet)
    fa = sqlite3.connect(os.path.join(d, "people", "pa", "feed.db"))
    rows = fa.execute("SELECT id, title, duration, has_full FROM items ORDER BY rank").fetchall()
    check(rows == [("yt:BBBBBBBBBBB", "Video Two", 90, 1), ("yt:AAAAAAAAAAA", "Video One", 90, 1)], f"youtube: items from captions, newest first by the listing ({rows})")
    full = open(os.path.join(d, "people", "pa", "full", "yt_AAAAAAAAAAA.txt")).read()
    check("Hello there" in full and "-->" not in full, "youtube: the full text is clean (no timestamps)")
    # a rate limit becomes a cooldown for the kind, not a failure
    open(os.path.join(d, "store", "youtube", "mode"), "w").write("limited")
    drop(d, "pa", {"op": "subscribe", "kind": "youtube", "key": "https://www.youtube.com/@Other", "lang": "es", "params": {"captions": "es-orig"}})
    hubcore.run(d, cols, now=4_000_000.0 + 20000, log=quiet)
    db = hubcore.open_db(d)
    cd = hubcore.kind_cooldown(db, "youtube")
    check(cd >= 4_000_000.0 + 20000 + 3 * 3600 - 120, "youtube: exit 75 starts a cooldown as long as subs-fetch's own pause (3 h)")
    check(db.execute("SELECT COUNT(*) FROM sources WHERE fail_count > 0").fetchone()[0] == 0, "a rate limit does not count as a failing source")
    open(os.path.join(d, "store", "youtube", "mode"), "w").write("crash")
    db.execute("DELETE FROM kv"); db.commit()
    hubcore.run(d, cols, now=4_000_000.0 + 40000, log=quiet)
    check(db.execute("SELECT COUNT(*) FROM sources WHERE fail_count > 0").fetchone()[0] >= 1, "a crash counts as a failure with backoff")
    db.close()
    del os.environ["HUB_SUBS_FETCH"]

# ---------- the person's CLI ----------
with tempfile.TemporaryDirectory() as d:
    cols = {"fake": Fake()}
    mk(d, "pa")
    drop(d, "pa", {"op": "subscribe", "kind": "fake", "key": "ok-shared", "lang": "es"})
    hubcore.run(d, cols, now=time.time() - 120, log=quiet)
    mount = os.path.join(d, "people", "pa")
    open(os.path.join(mount, ".attached"), "w").close()
    hub_client.HUB = mount
    hub_client.STATE = os.path.join(d, "read.json")

    def cli(*argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                rc = hub_client.main(list(argv))
            except SystemExit as exc:
                rc = exc.code
        return rc, buf.getvalue()

    rc, out = cli("feed")
    check(rc == 0 and "fa:AAAA1111" in out and "excerpt one" in out, "hub feed lists items with the excerpt")
    cli("read", "fa:AAAA1111")
    rc, out = cli("feed", "--new")
    check("fa:AAAA1111" not in out and "fa:BBBB2222" in out, "hub feed --new hides what was read (kept on the person's side)")
    rc, out = cli("show", "fa:AAAA1111", "--full")
    check("the full text" in out, "hub show --full prints the full text from the person's mount")
    rc, out = cli("show", "fa:BBBB2222", "--full")
    check("Excerpt" in out and "excerpt two" in out, "--full on an item without one falls back to the excerpt, saying so")
    rc, out = cli("status")
    check(rc == 0 and "1 unread of 2" in out, f"hub status counts unread ({out.splitlines()[-1] if out else ''})")
    rc, out = cli("subscribe", "youtube", "https://www.youtube.com/@x")
    check(rc not in (0, None), "hub subscribe youtube without --captions is refused locally")
    rc, out = cli("subscribe", "rss", "https://news.example/feed")
    names = [n for n in os.listdir(os.path.join(mount, "inbox")) if n.startswith("req-")]
    check(rc == 0 and len(names) == 1 and json.load(open(os.path.join(mount, "inbox", names[0])))["kind"] == "rss", "hub subscribe drops one whole JSON file in the inbox")
    check(not any(n.startswith(".") for n in os.listdir(os.path.join(mount, "inbox"))), "no half-written request is left visible")
    rc, out = cli("requests")
    check("1 request(s) waiting" in out, "hub requests shows what waits")
with tempfile.TemporaryDirectory() as un:
    os.makedirs(os.path.join(un, "inbox"))
    hub_client.HUB = un   # an empty mounted folder, no .attached
    for argv in (["feed"], ["subscribe", "rss", "https://n.example/f"]):
        try:
            with redirect_stdout(io.StringIO()):
                hub_client.main(argv)
            check(False, f"an unattached stack gets a clear message ({argv[0]})")
        except SystemExit as exc:
            check("not attached" in str(exc.code), f"an unattached stack gets a clear message ({argv[0]})")
    check(os.listdir(os.path.join(un, "inbox")) == [], "and nothing is dropped in its dead inbox")

# ---------- host starter ----------
with tempfile.TemporaryDirectory() as d:
    os.makedirs(os.path.join(d, "state"))
    mk(d, "pa")
    now = time.mktime((2026, 11, 6, 3, 0, 0, 0, 0, -1))
    night, day = time.localtime(now), time.localtime(now + 10 * 3600)
    def dec(n=now, loc=night, avail=4000, awake=0, running=False):
        return hub_start.decide(n, loc, d, avail, awake, running)
    check(dec()[0] is None, "nothing due and nothing waiting: it does not start")
    open(os.path.join(d, "state", "next-wake"), "w").write(str(now - 5))
    check(dec()[0] == ["run"], "due inside the quiet window: full run")
    check(dec(loc=day)[0] is None and "quiet window" in dec(loc=day)[1], "due but outside the window: waits")
    check(dec(avail=1200)[0] is None and "memory" in dec(avail=1200)[1] and dec(avail=1200)[2] is True, "low memory: waits and the operator is told")
    check(dec(awake=3)[0] is None and "busy hour" in dec(awake=3)[1] and dec(awake=3)[2] is True, "too many people awake: waits and the operator is told")
    check(dec(loc=day)[2] is False and dec(running=True)[2] is False, "not the window / already running: nothing to tell")
    check(dec(running=True)[0] is None, "already running: does not start a second one")
    open(os.path.join(d, "state", "next-wake"), "w").write(str(now + 9999))
    drop(d, "pa", {"op": "subscribe", "kind": "rss", "key": "https://n.example/f"})
    check(dec(loc=day)[0] == ["run", "--only-new"], "a waiting request starts a short run at any hour")
    open(os.path.join(d, "state", "last-start"), "w").write(str(now - 60))
    check(dec(loc=day)[0] is None, "but not twice within 10 minutes")
    check(hub_start.in_window(time.localtime(time.mktime((2026, 11, 6, 23, 30, 0, 0, 0, -1))), "22:00-06:00") and
          not hub_start.in_window(time.localtime(time.mktime((2026, 11, 6, 12, 0, 0, 0, 0, -1))), "22:00-06:00"), "a window may cross midnight")

# ---------- the operator's own work: system sources, the admin outbox, security, load, priorities ----------
SEC_RDF = b"""<?xml version="1.0"?><rdf:RDF xmlns="http://purl.org/rss/1.0/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<item><title>DSA-9001-1 openssl - security update</title><link>https://www.debian.org/security/2026/dsa-9001</link><description>openssl fixes</description></item>
<item><title>DSA-9002-1 notinstalled - security update</title><link>https://www.debian.org/security/2026/dsa-9002</link><description>x</description></item>
<item><title>DSA-9003-1 curl - security update</title><link>https://www.debian.org/security/2026/dsa-9003</link><description>curl fixes</description></item></rdf:RDF>"""
YT_ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>2026.11.02</title><id>t1</id><link href="https://github.com/yt-dlp/yt-dlp/releases/tag/2026.11.02"/></entry>
<entry><title>2026.10.26</title><id>t0</id><link href="https://github.com/yt-dlp/yt-dlp/releases/tag/2026.10.26"/></entry></feed>"""
sec = collectors.Security()
os.environ["HUB_DPKG_CMD"] = "printf 'libssl3 openssl\\nopenssl openssl\\ncurl curl\\n'"
os.environ["HUB_YTDLP_CMD"] = "echo 2026.10.26"
docs = {collectors.DSA_FEED: SEC_RDF, collectors.YTDLP_FEED: YT_ATOM}
collectors.Security.fetch_url = staticmethod(lambda url: docs[url])
check(sec.installed_sources() >= {"openssl", "libssl3", "curl"}, "security: the installed source packages are read from dpkg")
check(collectors.version_tuple("2026.11.02") > collectors.version_tuple("2026.10.26") > collectors.version_tuple("2025.12.31"), "security: yt-dlp versions compare as numbers")
try:
    sec.canonical("https://evil.example/", {})
    check(False, "security: only known watches are accepted")
except ValueError:
    check(True, "security: only known watches are accepted")

with tempfile.TemporaryDirectory() as d:
    mk(d, "pa")
    cols = collectors.registry()
    check(cols["security"].person_ok is False, "security is operator-only")
    drop(d, "pa", {"op": "subscribe", "kind": "security", "key": "debian-dsa", "lang": "es"})
    json.dump([{"kind": "security", "key": "debian-dsa"}, {"kind": "security", "key": "ytdlp-release"}, {"kind": "security", "key": "bogus"}, {"kind": "nothing", "key": "x"}],
              open(os.path.join(d, "system.json"), "w"))
    t0 = 5_000_000.0
    st = hubcore.run(d, cols, now=t0, log=quiet)
    pa = requests_of(d, "pa")
    check(pa[0]["status"] == "rejected" and "security" not in pa[0]["message"].split("known:")[-1], "a person cannot subscribe to a system kind (and it is not even listed to them)")
    db = hubcore.open_db(d)
    check(db.execute("SELECT COUNT(*) FROM sources WHERE system=1").fetchone()[0] == 2, "system.json creates the listed sources, skips the invalid entries")
    check(st["checked"] == 2, "system sources are collected although nobody follows them")
    out = hubcore.take_admin_outbox(d)
    texts = " | ".join(m["text"] for m in out if m["level"] == "send")
    check("yt-dlp 2026.11.02" in texts and "DSA-9001" not in texts and "DSA-9003" not in texts, "first run: a newer yt-dlp is announced; the old advisories are only the baseline")
    check(all(os.path.exists(os.path.join(d, "people", "pa", "feed.json")) for _ in [0]) and "yt-dlp" not in open(os.path.join(d, "people", "pa", "feed.json")).read(),
          "system findings never reach a person's feed")
    check(db.execute("SELECT COUNT(*) FROM items WHERE id LIKE 'se:DSA%'").fetchone()[0] == 2, "the relevant advisories are stored (2 of 3: openssl, curl; not the uninstalled package)")
    # second run: a new advisory for an installed package is announced
    docs[collectors.DSA_FEED] = SEC_RDF.replace(b"</rdf:RDF>", b"<item><title>DSA-9004-1 openssl - security update</title><link>https://www.debian.org/security/2026/dsa-9004</link><description>again</description></item></rdf:RDF>")
    hubcore.run(d, cols, now=t0 + 13 * 3600, log=quiet)
    out = hubcore.take_admin_outbox(d)
    texts = " | ".join(m["text"] for m in out if m["level"] == "send")
    check("DSA-9004" in texts and "DSA-9001" not in texts and "yt-dlp" not in texts, "later: only the NEW advisory is announced, once")
    # failing system source: alert on the 3rd failure, resolve when it recovers
    docs[collectors.DSA_FEED] = b"<broken"
    tt = t0 + 40 * 3600
    for i in range(3):
        hubcore.run(d, cols, now=tt, log=quiet)
        tt += 24 * 3600 * 2
    out = hubcore.take_admin_outbox(d)
    check(sum(m["level"] == "alert" and m["key"].startswith("hub:fail:") for m in out) == 1, "a source that fails 3 times in a row alerts the operator once")
    docs[collectors.DSA_FEED] = SEC_RDF
    hubcore.run(d, cols, now=tt + 24 * 3600 * 3, log=quiet)
    out = hubcore.take_admin_outbox(d)
    check(any(m["level"] == "resolve" and m["key"].startswith("hub:fail:") for m in out), "and says so when it works again")
    db.close()

# priorities: a person's first collection, then cheap/urgent kinds, then the slow one
with tempfile.TemporaryDirectory() as d:
    mk(d, "pa")
    order = []

    class Mk(Fake):
        def __init__(self, kind, prio):
            super().__init__(); self.kind, self.priority = kind, prio
        def canonical(self, key, params):
            return key, {}, key
        def collect(self, ctx, source):
            order.append(source["key"]); return []
    cols = {"slow": Mk("slow", 60), "feed": Mk("feed", 30), "urgent": Mk("urgent", 10)}
    for k in ("slow", "feed", "urgent"):
        drop(d, "pa", {"op": "subscribe", "kind": k, "key": f"k-{k}", "lang": "es"}, name=f"{k}.json")
    hubcore.run(d, cols, now=6_000_000.0, log=quiet)
    check(order == ["k-urgent", "k-feed", "k-slow"], f"inside a run: urgent kinds first, the slow one last ({order})")
    order.clear()
    drop(d, "pa", {"op": "subscribe", "kind": "slow", "key": "k-slow2", "lang": "es"}, name="n.json")
    hubcore.run(d, cols, now=6_000_000.0 + 10 ** 6, log=quiet)
    check(order[0] == "k-slow2", "a source never collected goes before everything else (a person is waiting for it)")

# load: many Hermes awake -> the hub stops by itself and tells the operator
with tempfile.TemporaryDirectory() as d:
    mk(d, "pa")
    fake = Fake()
    drop(d, "pa", {"op": "subscribe", "kind": "fake", "key": "ok-l1", "lang": "es"})
    drop(d, "pa", {"op": "subscribe", "kind": "fake", "key": "ok-l2", "lang": "es"})
    n = [0]
    def ok_once():
        n[0] += 1
        return n[0] == 1
    st = hubcore.run(d, {"fake": fake}, now=7_000_000.0, log=quiet, load_ok=ok_once)
    out = hubcore.take_admin_outbox(d)
    check(st["stopped"] == "load" and st["checked"] == 1 and len(fake.calls) == 1, "low memory: the run stops after the current source")
    check(any(m["level"] == "alert" and m["key"] == "hub:load" for m in out), "and the admin bot is told")
    check(os.path.exists(os.path.join(d, "people", "pa", "feed.json")) and float(open(os.path.join(d, "state", "next-wake")).read()) <= 7_000_000.0 + 1, "the feed is still published and the rest stays due")
    st = hubcore.run(d, {"fake": fake}, now=7_000_000.0 + 10, log=quiet, load_ok=lambda: True)
    out = hubcore.take_admin_outbox(d)
    check(st["stopped"] is None and any(m["level"] == "resolve" and m["key"] == "hub:load" for m in out), "next run completes and clears the alert")

# the admin outbox and the host starter's side of it
with tempfile.TemporaryDirectory() as d:
    hubcore.admin_say(d, "send", "k1", "hello")
    hubcore.admin_say(d, "alert", "k2", "problem")
    hubcore.admin_say(d, "bogus", "k3", "x")
    got = []
    n = hub_start.flush_admin(d, send=lambda m: got.append(m["key"]))
    check(n == 2 and got == ["k1", "k2"] and hubcore.take_admin_outbox(d) == [], "flush sends valid messages and empties the outbox (an unknown level is dropped)")
    hubcore.admin_say(d, "send", "k4", "later")
    def boom(m):
        raise RuntimeError("telegram down")
    hub_start.flush_admin(d, send=boom)
    check([m["key"] for m in hubcore.take_admin_outbox(d)] == ["k4"], "a message that cannot be sent is kept for the next tick")
    for i in range(300):
        hubcore.admin_say(d, "send", f"n{i}", "x")
    check(len(hubcore.take_admin_outbox(d)) <= 200, "the outbox is capped")

UPG = """Listing...
libssl3/stable-security 3.0.16 amd64 [upgradable from: 3.0.15]
curl/stable-security 7.88 amd64 [upgradable from: 7.87]
vim/stable 9.0 amd64 [upgradable from: 8.9]
"""
check(hub_start.parse_upgradable(UPG) == (["libssl3", "curl"], 3), "apt list: security updates are told apart from ordinary ones")
with tempfile.TemporaryDirectory() as d:
    os.makedirs(os.path.join(d, "state"))
    said = []
    now = time.time()
    flag = os.path.join(d, "reboot-required")
    r = hub_start.host_checks(d, now, False, run=lambda: UPG, say=lambda *a: said.append(a), reboot_flag=flag)
    check(r is None and not said, "host check: only inside the quiet window")
    r = hub_start.host_checks(d, now, True, run=lambda: UPG, say=lambda *a: said.append(a), reboot_flag=flag)
    check(r == {"security": 2, "total": 3} and said[0][:2] == ("alert", "hub:host-patches") and "libssl3" in said[0][2], "host check: pending security updates alert the operator")
    said.clear()
    check(hub_start.host_checks(d, now + 3600, True, run=lambda: UPG, say=lambda *a: said.append(a), reboot_flag=flag) is None, "and it runs once a day, not every tick")
    said.clear(); open(flag, "w").close()
    hub_start.host_checks(d, now + 25 * 3600, True, run=lambda: "Listing...\n", say=lambda *a: said.append(a), reboot_flag=flag)
    check(("resolve", "hub:host-patches") == said[0][:2] and any(a[1] == "hub:host-reboot" and a[0] == "alert" for a in said), "nothing pending resolves the alert; a pending reboot is reported")

# ---------- jobfetch: the shared job-board fetcher ----------
STUB = r'''#!/usr/bin/env python3
import json, os, sys
script = os.path.basename(sys.argv[1]); a = sys.argv[2:]
co = os.path.dirname(sys.argv[1])
def flag(n):
    return a[a.index(n) + 1] if n in a else None
if script == "select-portals.mjs":
    if "--list-tags" in a:
        print(json.dumps({"regions": {"ar": 1, "latam": 2, "br": 3}, "sectors": {"tech": 1, "games": 2}})); sys.exit(0)
    if "--list-roles" in a:
        print(json.dumps({"sysadmin-devops": {"label": "x"}})); sys.exit(0)
    open(flag("--into"), "a").write("SELECTED " + " ".join(a) + "\\n"); sys.exit(0)
if script == "union-portals.mjs":
    out = flag("--out"); parts = flag("--from").split(",")
    open(out, "w").write("".join(open(p).read() for p in parts)); open(os.path.join(co, "union-args"), "w").write(" ".join(a)); sys.exit(0)
if script == "scan.mjs":
    os.makedirs(os.path.join(co, "data"), exist_ok=True)
    json.dump({k: os.environ.get(k) for k in ("CAREER_OPS_ROOT", "CAREER_OPS_HTTP_CACHE_DIR", "CAREER_OPS_HTTP_CACHE_TTL_MS", "CAREER_OPS_HTTP_CACHE_STORE_NO_STORE")},
              open(os.path.join(co, "data", "scan-env.json"), "w"))
    sys.exit(int(os.environ.get("FAKE_SCAN_RC", "0")))
sys.exit(9)
'''
with tempfile.TemporaryDirectory() as d:
    stub = os.path.join(d, "stub.py"); open(stub, "w").write(STUB)
    co = os.path.join(d, "fetcher")
    os.environ["HUB_NODE"] = f"{sys.executable} {stub}"
    os.environ["HUB_FETCHER_DIR"] = co
    os.environ["HUB_DATA"] = d
    collectors.JobFetch._tags = None
    cols = collectors.registry()
    jf = cols["jobfetch"]
    mk(d, "pa", "pb")
    check(jf.person_ok is False and "jobs_profile" in jf.person_ops, "jobfetch: operator-only source, but people may send a profile")
    # before the fetcher is installed
    drop(d, "pa", {"op": "jobs_profile", "regions": ["ar"], "sectors": ["tech"]})
    hubcore.run(d, cols, now=8_000_000.0, log=quiet)
    check("not enabled" in requests_of(d, "pa")[0]["message"], "a profile before the fetcher exists is refused with a clear reason")
    # install the (fake) checkout
    os.makedirs(co)
    for f in ("scan.mjs", "union-portals.mjs", "select-portals.mjs"):
        open(os.path.join(co, f), "w").close()
    collectors.JobFetch._tags = None
    bad = [{"op": "jobs_profile", "regions": ["atlantis"], "sectors": ["tech"]},
           {"op": "jobs_profile", "regions": ["ar"]},
           {"op": "jobs_profile", "regions": ["ar; rm -rf /"], "sectors": ["tech"]},
           {"op": "jobs_profile", "roles": ["nonsense"]},
           {"op": "jobs_profile", "regions": ["ar"], "sectors": ["tech"], "remote": ["moon"]},
           {"op": "jobs_profile", "regions": "ar", "sectors": ["tech"]}]
    for i, r in enumerate(bad):
        drop(d, "pa", r, name=f"bad{i}.json")
    drop(d, "pa", {"op": "jobs_profile", "regions": ["ar", "latam"], "sectors": ["tech"], "roles": ["sysadmin-devops"], "remote": ["latam"]}, name="good.json")
    drop(d, "pb", {"op": "jobs_profile", "regions": ["br"], "sectors": ["games"]}, name="good.json")
    json.dump([{"kind": "jobfetch", "key": "union", "params": {"profiles": [{"regions": ["ar"], "sectors": ["games"]}]}}], open(os.path.join(d, "system.json"), "w"))
    t0 = 8_100_000.0
    st = hubcore.run(d, cols, now=t0, log=quiet)
    res = {r["file"]: r["status"] for r in requests_of(d, "pa")}
    check(all(res[f"bad{i}.json"] == "rejected" for i in range(len(bad))) and res["good.json"] == "ok", "profiles: only words the catalog really has are accepted; shapes and injections refused")
    check(os.path.exists(os.path.join(d, "shared", "jobs-tags.json")) and "latam" in json.load(open(os.path.join(d, "shared", "jobs-tags.json")))["regions"], "the catalog's words are published for people (hub jobs-profile --list)")
    env = json.load(open(os.path.join(co, "data", "scan-env.json")))
    check(env["CAREER_OPS_ROOT"] == co and env["CAREER_OPS_HTTP_CACHE_DIR"] == os.path.join(d, "shared", "jobs-http") and env["CAREER_OPS_HTTP_CACHE_TTL_MS"] == "108000000",
          "the fetch runs in the hub's own checkout, writing the shared store with a 30 h TTL")
    check(env["CAREER_OPS_HTTP_CACHE_STORE_NO_STORE"] == "1", "no-store answers are kept (operator's decision), for the fetcher only")
    union = open(os.path.join(co, "portals.yml")).read()
    check(union.count("SELECTED") == 3 and "--regions ar,latam" in union and "--regions br" in union and "--roles sysadmin-devops" in union,
          "the union is built from the operator's profile plus each person's, through select-portals (the operator's catalog)")
    mark = json.load(open(os.path.join(d, "shared", "jobs-http", ".fetched")))
    check(mark["at"] == t0 and mark["ttl_ms"] == 108000000 and mark["profiles"] == 3 and set(mark) == {"at", "ttl_ms", "profiles"}, "the marker says when and how many profiles, nothing about who")
    ma = json.load(open(os.path.join(d, "people", "pa", "feed.json")))
    mb = json.load(open(os.path.join(d, "people", "pb", "feed.json")))
    check(ma["jobs"]["profile"]["regions"] == ["ar", "latam"] and ma["jobs"]["store_fetched_at"] == t0 and mb["jobs"]["profile"]["regions"] == ["br"],
          "each person's manifest shows their own profile and when the shared fetch last ran")
    check("br" not in json.dumps(ma["jobs"]) and "latam" not in json.dumps(mb["jobs"]), "a person never sees another's profile")
    # a profile change makes the fetch due at the next window
    drop(d, "pb", {"op": "jobs_profile", "regions": ["ar"], "sectors": ["tech"]}, name="again.json")
    hubcore.run(d, cols, now=t0 + 3600, only_new=True, log=quiet)   # a short run does not fetch, but the request is applied and the source becomes due
    db = hubcore.open_db(d)
    check(db.execute("SELECT next_due <= ? FROM sources WHERE kind='jobfetch'", (t0 + 3600,)).fetchone()[0] == 1, "a new profile makes tonight's fetch due")
    db.close()
    # failure keeps the old marker (readers fall back to their own scan once it ages out)
    os.environ["FAKE_SCAN_RC"] = "3"
    hubcore.run(d, cols, now=t0 + 4000, log=quiet)
    check(json.load(open(os.path.join(d, "shared", "jobs-http", ".fetched")))["at"] == t0, "a failed fetch never refreshes the marker")
    db = hubcore.open_db(d)
    check(db.execute("SELECT fail_count FROM sources WHERE kind='jobfetch'").fetchone()[0] == 1, "and counts as a failing source")
    db.close()
    del os.environ["FAKE_SCAN_RC"]
    os.environ["HUB_JOBS_STORE_NO_STORE"] = "0"
    hubcore.run(d, cols, now=t0 + 4000 + 3 * 86400, log=quiet)
    check(json.load(open(os.path.join(co, "data", "scan-env.json")))["CAREER_OPS_HTTP_CACHE_STORE_NO_STORE"] is None, "HUB_JOBS_STORE_NO_STORE=0 turns the no-store option off")
    del os.environ["HUB_JOBS_STORE_NO_STORE"]
    os.environ["HUB_JOBFETCH_UNION_ARGS"] = "--no-keyword-entries"
    hubcore.run(d, cols, now=t0 + 4000 + 8 * 86400, log=quiet)
    check(open(os.path.join(co, "union-args")).read().endswith("--no-keyword-entries"), "extra union arguments (a keyword-provider switch) pass through")
    del os.environ["HUB_JOBFETCH_UNION_ARGS"]
    # the client
    hub_client.HUB = os.path.join(d, "people", "pa"); open(os.path.join(hub_client.HUB, ".attached"), "w").close(); os.makedirs(os.path.join(hub_client.HUB, "inbox"), exist_ok=True)
    os.environ["HUB_SHARED"] = os.path.join(d, "shared")
    def cli2(*argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                rc = hub_client.main(list(argv))
            except SystemExit as exc:
                rc = exc.code
        return rc, buf.getvalue()
    rc, out = cli2("jobs-profile", "--list")
    check(rc == 0 and "regions: ar, br, latam" in out and "roles: sysadmin-devops" in out, "hub jobs-profile --list prints the catalog's words")
    rc, out = cli2("jobs-profile", "--show")
    check("shared job fetch last ran" in out and "latam" in out, "hub jobs-profile --show prints the profile and the last fetch")
    rc, out = cli2("jobs-profile", "--regions", "ar,latam")
    check(rc not in (0, None), "hub jobs-profile without sectors or roles is refused locally")
    rc, out = cli2("jobs-profile", "--regions", "AR, latam", "--sectors", "tech")
    sent = [json.load(open(os.path.join(hub_client.HUB, "inbox", n))) for n in os.listdir(os.path.join(hub_client.HUB, "inbox")) if n.startswith("req-")]
    check(rc == 0 and sent and sent[0]["op"] == "jobs_profile" and sent[0]["regions"] == ["ar", "latam"], "hub jobs-profile drops a normalised request")
    del os.environ["HUB_SHARED"]
    for k in ("HUB_NODE", "HUB_FETCHER_DIR", "HUB_DATA"):
        os.environ.pop(k, None)
    collectors.JobFetch._tags = None

# no profiles and no checkout: a quiet skip, not a failing source
with tempfile.TemporaryDirectory() as d:
    os.environ["HUB_FETCHER_DIR"] = os.path.join(d, "nothing-here")
    mk(d, "pa")
    json.dump([{"kind": "jobfetch", "key": "union"}], open(os.path.join(d, "system.json"), "w"))
    st = hubcore.run(d, collectors.registry(), now=9_000_000.0, log=quiet)
    db = hubcore.open_db(d)
    check(st["failed"] == 0 and db.execute("SELECT COUNT(*) FROM sources WHERE kind='jobfetch'").fetchone()[0] == 1, "no profiles and no fetcher yet: nothing fails, nothing is alerted")
    db.close()
    os.environ.pop("HUB_FETCHER_DIR", None)

# ---------- things only a real run found ----------
compose = open(os.path.join(HERE, "hub", "docker-compose.hub.yml")).read()
check(any(l.strip().startswith("- /tmp:") and "exec" in l for l in compose.splitlines()), "compose: /tmp is a tmpfs with exec (yt-dlp, a PyInstaller binary, cannot start from a noexec /tmp)")
check(collectors.DSA_FEED == "https://www.debian.org/security/dsa" and "dsa.en.rdf" not in collectors.DSA_FEED, "the Debian feed address is the live one (the old one is a 404)")
REAL_DSA = b"""<?xml version="1.0" encoding="UTF-8" ?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel rdf:about="https://www.debian.org/security/dsa.rdf"><title>Debian Security</title><link>x</link><description>d</description><items><rdf:Seq><rdf:li rdf:resource="https://lists.debian.org/m1.html"/></rdf:Seq></items></channel>
<item rdf:about="https://lists.debian.org/m1.html"><title>DSA-6612-1 symfony - security update</title><link>https://lists.debian.org/m1.html</link><description>text</description><dc:date>2026-11-04</dc:date></item></rdf:RDF>"""
parsed = collectors.RSS.parse(REAL_DSA)
check(len(parsed) == 1 and collectors.DSA_TITLE.match(parsed[0]["title"]).group(2) == "symfony", "the real Debian feed's RDF shape parses (the channel element is not an item)")
# retry: a failing source with a long back-off is tried again at the next run
with tempfile.TemporaryDirectory() as d:
    mk(d, "pa")
    fake = Fake(); fake.behaviour = "boom"
    drop(d, "pa", {"op": "subscribe", "kind": "fake", "key": "ok-r", "lang": "es"})
    hubcore.run(d, {"fake": fake}, now=1_000_000.0, log=quiet)
    fake.behaviour = "items"; fake.calls.clear()
    hubcore.run(d, {"fake": fake}, now=1_000_000.0 + 600, log=quiet)
    check(not fake.calls, "a failing source waits out its back-off")
    import subprocess as sp
    r = sp.run([sys.executable, os.path.join(HERE, "hub", "hub.py"), "retry"], env={**os.environ, "HUB_DATA": d}, capture_output=True, text=True)
    check("1 failing source" in r.stdout, "hub.py retry clears the back-off")
    hubcore.run(d, {"fake": fake}, now=1_000_000.0 + 700, log=quiet)
    check(len(fake.calls) == 1, "and the next run tries it")

# ---------- the compose patch (the VM's compose files drift from the repo: only the hub lines are inserted) ----------
sys.path.insert(0, os.path.join(HERE, "ops"))
import hub_compose_patch as cp  # noqa: E402
VM_HERNIK = """services:
  claude-agent:
    volumes:
      - ./user1-workdir:/workdir
  hermes-agent:
    image: x
    volumes:
      - ./user1-workdir:/workdir
      - ./hermes-config:/hermes-persist
  antigravity-agent:
    volumes:
      - ./user1-workdir:/workdir
"""
new, msg = cp.patch("hernik", VM_HERNIK)
blocks = new.split("  hermes-agent:")[1].split("  antigravity-agent:")[0]
check("/hub:ro" in blocks and new.count("/hub:ro") == 1 and "/hub/inbox" in blocks and "/hub-shared:ro" in blocks, "compose patch: the hub mounts go into the hermes-agent service only (not the legacy ones with the same line)")
check(cp.patch("hernik", new)[0] is None, "compose patch: running it twice changes nothing")
check(new.replace("\n".join(cp.HERNIK) + "\n", "") == VM_HERNIK, "compose patch: everything else in the file is untouched")
try:
    cp.patch("hernik", "services:\n  other:\n    image: y\n")
    check(False, "compose patch: a missing anchor is an error, nothing written")
except LookupError:
    check(True, "compose patch: a missing anchor is an error, nothing written")
VM_STACK = "services:\n  hermes:\n    volumes:\n      - ${STACK_DIR}/workdir:/workdir\n      - ${STACK_DIR}/web-outputs:/web-outputs\n  web:\n    volumes:\n      - ${STACK_DIR}/web-outputs:/web-outputs:ro\n"
new, msg = cp.patch("stack", VM_STACK)
check(new.index("/hub:ro") < new.index("  web:") and new.count("/hub:ro") == 1 and new.endswith("web-outputs:ro\n"), "compose patch: the stack template gets the mounts in the hermes service, not in web")
# the repo's own files already carry exactly these lines
for f, kind in (("docker-compose.yml", "hernik"), ("stacks/docker-compose.stack.yml", "stack")):
    check(cp.patch(kind, open(os.path.join(HERE, f)).read())[0] is None, f"{f} in the repo already has the hub mounts")

# ---------- modules: each person has only what they need ----------
def cli2(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            rc = hub_client.main(list(argv))
        except SystemExit as exc:
            rc = exc.code
    return rc, buf.getvalue()
import subprocess as sp  # noqa: E402
def reqs(db, person):
    return {r[0]: (r[1], r[2]) for r in db.execute("SELECT detail, status, message FROM requests WHERE person=?", (person,))}
collectors.RSS.public_check = staticmethod(lambda h: True)
with tempfile.TemporaryDirectory() as d:
    cols = collectors.registry()
    for p in ("pa", "pb", "pc"):
        mk(d, p); open(os.path.join(d, "people", p, ".attached"), "w").close()
    db = hubcore.open_db(d)
    drop(d, "pa", {"op": "subscribe", "kind": "rss", "key": "https://n.example/f", "lang": "es"}, name="a1.json")
    hubcore.process_inboxes(d, db, cols, 1_000_000.0, quiet)
    check(reqs(db, "pa")["a1.json"][0] == "ok", "no modules.json: nothing is restricted (the behaviour before modules)")
    drop(d, "pa", {"op": "module_request", "module": "jobfinder"}, name="m0.json")
    hubcore.process_inboxes(d, db, cols, 1_000_001.0, quiet)
    check(reqs(db, "pa")["jobfinder"][0] == "ok", "without restrictions a module request just says it is already available")
    hubcore.take_admin_outbox(d)

    def tool(*args):
        return sp.run([sys.executable, os.path.join(HERE, "ops", "stack_modules.py"), *args], env={**os.environ, "HUB_DATA": d, "AIBRIDGE_ROOT": HERE},
                      capture_output=True, text=True)
    r = tool("add", "pa", "youtube")
    check(r.returncode != 0 and "init" in r.stderr, "stack_modules: add before init is refused (a file with one person would lock everybody else out)")
    r = tool("init")
    check(r.returncode == 0 and tool("init").returncode != 0, "stack_modules: init seeds everybody once, a second init is refused")
    for p, mods in (("pa", ["jobfinder", "budgetai", "news", "telegram"]), ("pb", ["jobfinder", "budgetai", "youtube", "telegram"]), ("pc", ["jobfinder", "budgetai", "youtube", "news", "telegram"])):
        tool("remove", p, *mods)
    tool("add", "pa", "youtube"); tool("add", "pb", "news", "jobfinder")
    r = tool("add", "pa", "bogus"); check(r.returncode != 0 and "unknown module" in r.stderr, "stack_modules: an unknown module is refused")
    r = tool("add", "ghost", "news"); check(r.returncode != 0 and "not attached" in r.stderr, "stack_modules: a person who is not attached is refused")
    r = tool("add", "pb", "budgetai")
    check("projects.json" in r.stdout, "stack_modules: a module with a project reminds you of the second step (the project sync list)")
    tool("remove", "pb", "budgetai")
    reg = json.load(open(os.path.join(d, "modules.json")))["people"]
    check(reg == {"pa": ["youtube"], "pb": ["jobfinder", "news"], "pc": []}, f"modules.json holds exactly what was chosen ({reg})")
    check("jobfinder" in tool("list").stdout and "on" in tool("list").stdout, "stack_modules: list shows who has what")

    drop(d, "pa", {"op": "subscribe", "kind": "rss", "key": "https://n.example/f2", "lang": "es"}, name="s1.json")
    drop(d, "pa", {"op": "subscribe", "kind": "youtube", "key": "https://www.youtube.com/@Chan", "lang": "es", "params": {"captions": "es-orig"}}, name="s2.json")
    drop(d, "pb", {"op": "subscribe", "kind": "youtube", "key": "https://www.youtube.com/@Chan", "lang": "es", "params": {"captions": "es-orig"}}, name="s3.json")
    drop(d, "pc", {"op": "subscribe", "kind": "rss", "key": "https://n.example/f3", "lang": "es"}, name="s4.json")
    drop(d, "pa", {"op": "jobs_profile", "regions": ["ar"], "sectors": ["tech"]}, name="j1.json")
    drop(d, "pb", {"op": "jobs_profile", "regions": ["ar"], "sectors": ["tech"]}, name="j2.json")
    hubcore.process_inboxes(d, db, cols, 1_000_100.0, quiet)
    a, b, c = reqs(db, "pa"), reqs(db, "pb"), reqs(db, "pc")
    check(a["s1.json"][0] == "rejected" and "«news»" in a["s1.json"][1] and "hub modules request news" in a["s1.json"][1], "a source of a kind the person does not have is refused, naming the module to ask for")
    check(a["s2.json"][0] == "ok" and b["s3.json"][0] == "rejected", "the module that is on works; the one that is off does not")
    check(c["s4.json"][0] == "rejected", "a person with no modules cannot subscribe to anything")
    check(a["j1.json"][0] == "rejected" and "«jobfinder»" in a["j1.json"][1], "a job profile needs the jobfinder module")
    check("not enabled on this server" in b["j2.json"][1], "with the module on, the request gets past the gate (and meets the next check)")
    # module requests
    drop(d, "pc", {"op": "module_request", "module": "jobfinder"}, name="m1.json")
    drop(d, "pc", {"op": "module_request", "module": "jobfinder"}, name="m2.json")
    drop(d, "pc", {"op": "module_request", "module": "nope"}, name="m3.json")
    hubcore.process_inboxes(d, db, cols, 1_000_200.0, quiet)
    rows = db.execute("SELECT detail, status FROM requests WHERE person='pc' AND op='module_request' ORDER BY id").fetchall()
    check(rows[0] == ("jobfinder", "pending") and rows[1] == ("jobfinder", "pending") and rows[2][1] == "rejected", "module requests: pending, the repeat noted, an unknown name refused")
    told = [m for m in hubcore.take_admin_outbox(d) if m["key"].startswith("hub:module:")]
    check(len(told) == 1 and "ops/stack_modules.py add pc jobfinder" in told[0]["text"], "the operator is told once, with the exact command to switch it on")
    r = tool("pending"); check("pc asks for jobfinder" in r.stdout, "stack_modules: pending lists what people asked for")
    tool("add", "pc", "jobfinder")
    hubcore.resolve_module_requests(db, d, quiet)
    check(db.execute("SELECT status FROM requests WHERE person='pc' AND op='module_request' AND detail='jobfinder' ORDER BY id LIMIT 1").fetchone()[0] == "ok", "once switched on, the person's pending request turns ok")
    # the manifest and the client
    hubcore.publish_person(d, db, "pa", 1_000_300.0)
    mf = json.load(open(os.path.join(d, "people", "pa", "feed.json")))["modules"]
    check(mf["enforced"] and mf["enabled"] == ["youtube"] and "jobfinder" in mf["available"], "the person's manifest says what is on and what exists")
    hub_client.HUB = os.path.join(d, "people", "pa")
    rc, out = cli2("modules")
    check(rc == 0 and "[on]  youtube" in out and "[off] jobfinder" in out and "hub modules request jobfinder" in out, "hub modules shows on/off and how to ask")
    rc, out = cli2("modules", "request", "budgetai")
    check(rc == 0 and any(n.startswith("req-") for n in os.listdir(os.path.join(d, "people", "pa", "inbox"))), "hub modules request drops a request")
    # job profiles of a person who no longer has the module do not cost fetches
    db.execute("INSERT OR REPLACE INTO kv VALUES ('jobs-profile:pa', ?)", (json.dumps({"regions": ["ar"], "sectors": ["tech"]}),))
    db.execute("INSERT OR REPLACE INTO kv VALUES ('jobs-profile:pb', ?)", (json.dumps({"regions": ["br"], "sectors": ["games"]}),))
    got = collectors.JobFetch().profiles(db, {"params": {}}, d)
    check(got == [{"regions": ["br"], "sectors": ["games"]}], "the shared fetch only covers people who have the jobfinder module")
    # a broken registry is the safe failure
    open(os.path.join(d, "modules.json"), "w").write("{broken")
    check(hubcore.load_modules(d) == {} and hubcore.module_allows({}, "pb", kind="rss") is False, "a registry that cannot be read gives nobody anything")
    check(any(m["key"] == "hub:modules" and m["level"] == "alert" for m in hubcore.take_admin_outbox(d)), "and the operator is told")
    db.close()
cat = hubcore.catalog()
check({"jobfinder", "budgetai", "youtube", "news"} <= set(cat) and cat["jobfinder"]["project"] == "jobfinder" and "jobs_profile" in cat["jobfinder"]["hub_ops"], "the catalog names the modules, their project and what the hub allows")

if FAILS:
    print(f"\n{len(FAILS)} FAILED: {FAILS}")
    sys.exit(1)
print("\nall hub checks passed")
