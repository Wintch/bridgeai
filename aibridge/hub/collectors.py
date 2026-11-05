"""The collectors the hub knows: `youtube` (channel captions, through subs-fetch), `rss` (news and any RSS/Atom feed) and `security` (the operator's
own advisory watch, system.json only).

A new kind (the job scan is the next one, designed in another session) is one more Collector subclass registered in
`registry()`: `canonical()` validates what a person asked for, `collect()` does the work and returns items. See hubcore.Collector.
"""
import hashlib
import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

try:
    from hubcore import Collector, Throttled
except ImportError:   # imported as a package in tests
    from .hubcore import Collector, Throttled

CODE = os.environ.get("HUB_CODE", os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [CODE, os.path.dirname(CODE)]   # in the container subs_digest.py sits next to this file; in the repo, one level up

YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
YT_PATH = re.compile(r"^/(@[A-Za-z0-9._-]{1,60}|channel/UC[A-Za-z0-9_-]{22}|c/[A-Za-z0-9._-]{1,60}|user/[A-Za-z0-9._-]{1,60})(/(videos|streams|featured|shorts))?/?$")
CAPTIONS = re.compile(r"^[a-z]{2,3}(-orig)?$")
SRT_NAME = re.compile(r"^(?P<title>.*?)\s*\[(?P<id>[A-Za-z0-9_-]{11})\](?:\.[A-Za-z0-9_-]+)*\.(?:srt|vtt)$")
SUBS_TIMEOUT_S = 50 * 60
RSS_MAX_BYTES = 2_000_000
RSS_ITEMS = 40
EXCERPT_CHARS = 6000


# ---------------------------------------------------------------- youtube
class YouTube(Collector):
    kind = "youtube"
    default_interval_min = 180
    priority = 60   # the slow one: after feeds and system checks

    def canonical(self, key, params):
        u = urllib.parse.urlparse(key.strip())
        if u.scheme not in ("http", "https") or (u.hostname or "").lower() not in YT_HOSTS or u.username or u.port:
            raise ValueError("a YouTube channel address (youtube.com/@name or /channel/UC...)")
        m = YT_PATH.match(u.path)
        if not m:
            raise ValueError("that is not a channel address (youtube.com/@name, /channel/UC..., /c/name or /user/name)")
        captions = (params or {}).get("captions")
        if not isinstance(captions, str) or not CAPTIONS.match(captions):
            raise ValueError("say the language of the channel's OWN captions, like es-orig, ru-orig or en-orig (a wrong one downloads almost nothing)")
        return f"https://www.youtube.com/{m.group(1)}", {"captions": captions}, m.group(1).split("/")[-1]

    @staticmethod
    def dirname(source):
        return "yt-" + re.sub(r"[^A-Za-z0-9._-]", "_", source["key"].rsplit("/", 1)[-1])[:60]

    def fetch_cmd(self):
        env = os.environ.get("HUB_SUBS_FETCH")
        if env:
            return shlex.split(env)
        local = os.path.join(CODE, "subs_fetch.py")
        return [sys.executable, local] if os.path.isfile(local) else ["subs-fetch"]

    def collect(self, ctx, source):
        d = ctx.store("youtube", self.dirname(source))
        cmd = self.fetch_cmd() + [source["key"], d, "--lang", source["params"]["captions"], "--new"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=SUBS_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise RuntimeError("subs-fetch took more than 50 minutes")
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 75:   # rate limit or soft block: subs-fetch keeps its own (shared, extend-only) pause file next to the folders
            raise Throttled(self.cooldown_minutes(d), "subs-fetch reported a rate limit or soft block")
        if r.returncode not in (0, 3):
            raise RuntimeError(f"subs-fetch exit {r.returncode}: {' | '.join(out.strip().splitlines()[-2:])[:160]}")
        return self.items_from_folder(ctx, source, d)

    @staticmethod
    def cooldown_minutes(directory):
        try:
            left = float(open(os.path.join(os.path.dirname(os.path.abspath(directory)), ".subs-cooldown")).read().strip()) - time.time()
        except (OSError, ValueError):
            left = 0
        return max(60.0, left / 60 + 1)

    def items_from_folder(self, ctx, source, d):
        """Items for the captions on disk that the hub has not stored yet (newest first, by subs-fetch's own listing)."""
        import subs_digest
        have = ctx.known_ext_ids(source["id"])
        try:
            order = json.load(open(os.path.join(d, ".ids.cache"))).get("ids", [])
        except (OSError, ValueError):
            order = []
        rank = {vid: i for i, vid in enumerate(order)}
        files = {}
        for name in os.listdir(d):
            m = SRT_NAME.match(name)
            if m:
                files.setdefault(m.group("id"), (name, m.group("title")))
        textdir = os.path.join(d, "text")
        os.makedirs(textdir, exist_ok=True)
        items = []
        for vid, (name, title) in sorted(files.items(), key=lambda kv: rank.get(kv[0], 10 ** 6)):
            if vid in have:
                continue
            try:
                lines, secs = subs_digest.clean_srt(open(os.path.join(d, name), encoding="utf-8", errors="replace").read())
            except OSError:
                continue
            if not lines:
                continue
            excerpt, cut = subs_digest.excerpts(lines, EXCERPT_CHARS)
            rel = os.path.join("youtube", os.path.basename(d), "text", f"{vid}.txt")
            tmp = os.path.join(textdir, f".{vid}.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            os.replace(tmp, os.path.join(textdir, f"{vid}.txt"))
            items.append({"ext_id": vid, "title": title or vid, "url": f"https://www.youtube.com/watch?v={vid}", "duration": secs,
                          "excerpt": ("[sample spread over the whole video] " if cut else "") + excerpt, "fulltext": rel,
                          "rank": rank.get(vid, 10 ** 6)})
        return items


# ---------------------------------------------------------------- rss
def host_is_public(host):
    """False for anything that resolves to a private, loopback, link-local or reserved address (the hub network is internet-only
    anyway; this is the second lock)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return bool(infos)


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlparse(newurl)
        if u.scheme not in ("http", "https") or not RSS.public_check(u.hostname or ""):
            raise urllib.error.URLError("redirect to a non-public address refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class RSS(Collector):
    kind = "rss"
    default_interval_min = 120
    priority = 30
    public_check = staticmethod(host_is_public)   # tests replace it
    opener_factory = staticmethod(lambda: urllib.request.build_opener(_CheckedRedirect))

    def canonical(self, key, params):
        u = urllib.parse.urlparse(key.strip())
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
            raise ValueError("an http(s) address of a feed, without a user or password in it")
        if u.port not in (None, 80, 443):
            raise ValueError("feeds on a non-standard port are not accepted")
        if not self.public_check(u.hostname):
            raise ValueError("that address does not resolve to a public server")
        clean = urllib.parse.urlunparse((u.scheme, u.netloc.lower(), u.path or "/", "", u.query, ""))
        return clean, {}, u.hostname

    def fetch(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; feed-reader)", "Accept": "application/rss+xml, application/atom+xml, text/xml"})
        try:
            with self.opener_factory().open(req, timeout=25) as r:
                raw = r.read(RSS_MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503):
                raise Throttled(60, f"HTTP {exc.code}")
            raise
        if len(raw) > RSS_MAX_BYTES:
            raise RuntimeError("feed larger than 2 MB")
        return raw

    def collect(self, ctx, source):
        return self.parse(self.fetch(source["key"]), salt=source["key"])

    @staticmethod
    def parse(raw, salt=""):
        """Item ids are global (rs:<hash>), so the hash includes the feed's own address: two feeds that carry the same article
        each keep their own copy of the item instead of the second one being silently dropped."""
        head = raw[:4096].lower()
        if b"<!doctype" in head or b"<!entity" in raw.lower():   # no DTDs, no entity tricks: a feed never needs them
            raise ValueError("feed uses a DTD or entities: refused")
        root = ET.fromstring(raw)
        ns = lambda t: t.rsplit("}", 1)[-1]
        entries = [e for e in root.iter() if ns(e.tag) in ("item", "entry")]
        items = []
        for e in entries[:RSS_ITEMS]:
            f = {ns(c.tag): c for c in e}
            title = (f["title"].text or "").strip() if "title" in f else ""
            link = ""
            if "link" in f:
                link = (f["link"].get("href") or f["link"].text or "").strip()
            guid = ((f["guid"].text if "guid" in f else None) or (f["id"].text if "id" in f else None) or link or title or "").strip()
            body = ""
            for tag in ("encoded", "content", "description", "summary"):
                if tag in f and (f[tag].text or "").strip():
                    body = f[tag].text
                    break
            body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
            if not guid:
                continue
            if link and urllib.parse.urlparse(link).scheme not in ("http", "https"):
                link = ""
            items.append({"ext_id": hashlib.sha1((salt + "\n" + guid).encode()).hexdigest()[:16], "title": title or link, "url": link or None,
                          "excerpt": body[:2000]})
        return items


# ---------------------------------------------------------------- security (operator-only)
DSA_FEED = "https://www.debian.org/security/dsa"   # RSS 1.0 (RDF); dsa.en.rdf is a 404 (found on the first real run, 2026-11-05)
YTDLP_FEED = "https://github.com/yt-dlp/yt-dlp/releases.atom"
DSA_TITLE = re.compile(r"^(DSA-\d+(?:-\d+)?)\s+([A-Za-z0-9+._-]+)")


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:5])


class Security(Collector):
    """What the operator wants to hear about without anyone asking: new Debian security advisories (DSA) for packages that are installed in
    THIS image (the hub runs the same image as the stacks), and a newer yt-dlp than the pinned one. Only system.json can create these
    (person_ok False). Findings go to the admin bot, never to a person. Host packages (docker-ce, the VM's own apt) are not visible from a
    container: hub_start.py checks those on the host."""
    kind = "security"
    default_interval_min = 720
    priority = 10
    person_ok = False
    KEYS = {"debian-dsa": "Avisos de seguridad de Debian (paquetes de la imagen)", "ytdlp-release": "yt-dlp"}
    fetch_url = staticmethod(lambda url: urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; advisory-watch)"}), timeout=25).read(RSS_MAX_BYTES))

    def canonical(self, key, params):
        if key not in self.KEYS:
            raise ValueError("known: " + ", ".join(sorted(self.KEYS)))
        return key, {}, self.KEYS[key]

    def installed_sources(self):
        """Source-package names of everything installed (a DSA names the source package: openssl covers libssl3)."""
        env = os.environ.get("HUB_DPKG_CMD")   # tests
        cmd = shlex.split(env) if env else ["dpkg-query", "-W", "-f", "${Package} ${source:Package}\\n"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.TimeoutExpired):
            return set()
        names = set()
        for line in out.splitlines():
            parts = line.split()
            names.update(p.split("(")[0] for p in parts[:2])
        return {n for n in names if n}

    def installed_ytdlp(self):
        try:
            return subprocess.run(shlex.split(os.environ.get("HUB_YTDLP_CMD", "yt-dlp --version")), capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def collect(self, ctx, source):
        if source["key"] == "debian-dsa":
            return self.dsa(ctx, source)
        return self.ytdlp(ctx, source)

    def dsa(self, ctx, source):
        have = ctx.known_ext_ids(source["id"])
        mine = self.installed_sources()
        if not mine:
            raise RuntimeError("cannot list the installed packages (dpkg-query)")
        quiet = not have   # first look: the feed's older advisories may be long patched; store them, announce only what comes after
        items = []
        for it in RSS.parse(self.fetch_url(DSA_FEED)):
            m = DSA_TITLE.match(it["title"] or "")
            if m and m.group(2) in mine:
                items.append({"ext_id": m.group(1), "title": f"{m.group(1)}: {m.group(2)} (instalado en la imagen; confirmar con ops/image_audit.sh)",
                              "url": it["url"], "excerpt": it["excerpt"][:600], "quiet": quiet})
        return items

    def ytdlp(self, ctx, source):
        mine = self.installed_ytdlp()
        entries = [e for e in RSS.parse(self.fetch_url(YTDLP_FEED)) if e.get("url")]
        tags = []
        for e in entries:
            tag = e["url"].rstrip("/").rsplit("/", 1)[-1]
            if version_tuple(tag):
                tags.append((version_tuple(tag), tag, e["url"]))
        if not tags or not version_tuple(mine):
            raise RuntimeError("could not read the yt-dlp releases or the installed version")
        newest = max(tags)
        if newest[0] > version_tuple(mine):
            return [{"ext_id": "yt-dlp-" + newest[1], "title": f"yt-dlp {newest[1]} disponible (la imagen tiene {mine}); subir el pin en Dockerfile.hermes-agent-base",
                     "url": newest[2], "excerpt": ""}]
        return []


# ---------------------------------------------------------------- jobfetch (operator-only): the shared job-board fetcher
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
REMOTE_VALUES = ("latam", "worldwide", "friendly")
PORTALS_SKELETON = "tracked_companies:\n\njob_boards:\n\ntitle_filter:\n  positive: []\n  negative: []\n"


class JobFetch(Collector):
    """One fetcher for everybody's job scans (jobfinder docs/SHARED_FETCH.md): it reads each board ONCE and keeps the public answer in
    <data>/shared/jobs-http, which every stack mounts read-only; each person's own scan (jobpush) then parses what was kept without
    touching the sites. Hub-owned code only: the jobfinder checkout in <data>/fetcher is installed by the operator (ops/hub_fetcher_install.sh),
    never taken from a person. What a person sends is a PROFILE (regions, sectors, remote, roles), checked against the catalog's own tags;
    the fetcher builds their employer list with select-portals.mjs from the operator's catalog, so no person can make it request an address
    of their own. The union of the profiles (plus the operator's `profiles` in system.json) is what gets fetched."""
    kind = "jobfetch"
    default_interval_min = 1440
    priority = 40
    person_ok = False
    person_ops = ("jobs_profile",)
    TTL_MS = 108_000_000   # 30 h: outlives a daily fetch by six hours; a night that failed leaves readers a clear miss, not stale postings
    _tags = None

    def canonical(self, key, params):
        if key != "union":
            raise ValueError("the only job fetch is 'union'")
        profiles = (params or {}).get("profiles", [])
        if not isinstance(profiles, list) or len(profiles) > 20:
            raise ValueError("params.profiles is a short list of profiles")
        clean = [self.clean_profile(p) for p in profiles]
        return key, {"profiles": clean}, "Job boards: one shared fetch for everybody"

    @staticmethod
    def checkout():
        return os.environ.get("HUB_FETCHER_DIR", "/data/fetcher")

    @staticmethod
    def node():
        return shlex.split(os.environ.get("HUB_NODE", "node"))

    def run_node(self, script, args, env=None, timeout=300):
        return subprocess.run(self.node() + [os.path.join(self.checkout(), script)] + args, cwd=self.checkout(), env=env or os.environ,
                              capture_output=True, text=True, timeout=timeout)

    def catalog_tags(self):
        """(regions, sectors, roles) the catalog offers, from the fetcher's own select-portals.mjs; cached for the process."""
        if JobFetch._tags is None:
            tags = json.loads(self.run_node("select-portals.mjs", ["--list-tags"], timeout=60).stdout)
            roles = json.loads(self.run_node("select-portals.mjs", ["--list-roles"], timeout=60).stdout)
            JobFetch._tags = (set(tags["regions"]), set(tags["sectors"]), set(roles))
            try:   # public: people read it (`hub jobs-profile --list`) to know which words are valid
                d = os.path.join(os.environ.get("HUB_DATA", "/data"), "shared")
                os.makedirs(d, exist_ok=True)
                tmp = os.path.join(d, ".jobs-tags.tmp")
                open(tmp, "w").write(json.dumps({"regions": sorted(tags["regions"]), "sectors": sorted(tags["sectors"]), "roles": sorted(roles),
                                                 "remote": list(REMOTE_VALUES)}))
                os.chmod(tmp, 0o644)
                os.replace(tmp, os.path.join(d, "jobs-tags.json"))
            except OSError:
                pass
        return JobFetch._tags

    def clean_profile(self, p):
        """-> a normalised profile or ValueError. Every word must be a tag the catalog really has."""
        if not isinstance(p, dict) or set(p) - {"regions", "sectors", "remote", "roles"}:
            raise ValueError("a profile has regions, sectors, remote and roles, nothing else")
        try:
            regions, sectors, roles = self.catalog_tags()
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            raise ValueError("the catalog's tags cannot be read (is the fetcher installed?)")
        out = {}
        for field, allowed in (("regions", regions), ("sectors", sectors), ("roles", roles), ("remote", set(REMOTE_VALUES))):
            vals = p.get(field, [])
            if not isinstance(vals, list) or len(vals) > 20 or not all(isinstance(v, str) and SLUG.match(v) for v in vals):
                raise ValueError(f"{field} is a short list of tags")
            bad = sorted(set(vals) - allowed)
            if bad:
                raise ValueError(f"unknown {field}: {', '.join(bad[:5])} (the catalog's own words: hub jobs-profile --list)")
            if vals:
                out[field] = sorted(set(vals))
        if not (out.get("roles") or (out.get("regions") and out.get("sectors"))):
            raise ValueError("give regions AND sectors (the employers), or roles (titles only)")
        return out

    def handle_op(self, db, person, req, now):
        if not os.path.isfile(os.path.join(self.checkout(), "select-portals.mjs")):
            return "rejected", "the shared job fetch is not enabled on this server yet"
        try:
            prof = self.clean_profile({k: req.get(k) for k in ("regions", "sectors", "remote", "roles") if req.get(k) is not None})
        except (ValueError, subprocess.SubprocessError, OSError, KeyError) as exc:
            return "rejected", str(exc) if isinstance(exc, ValueError) else "could not read the catalog's tags"
        db.execute("INSERT OR REPLACE INTO kv(k, v) VALUES (?, ?)", (f"jobs-profile:{person}", json.dumps(prof, sort_keys=True)))
        db.execute("UPDATE sources SET next_due = MIN(next_due, ?) WHERE kind = 'jobfetch'", (now,))   # tonight's fetch must cover it
        return "ok", "job profile saved: the next fetch (tonight) covers it"

    def profiles(self, db, source):
        out = list(source["params"].get("profiles", []))
        for (v,) in db.execute("SELECT v FROM kv WHERE k LIKE 'jobs-profile:%' ORDER BY k"):
            try:
                out.append(json.loads(v))
            except ValueError:
                pass
        return out

    def collect(self, ctx, source):
        profiles = self.profiles(ctx.db, source)
        co = self.checkout()
        have_code = all(os.path.isfile(os.path.join(co, f)) for f in ("scan.mjs", "union-portals.mjs", "select-portals.mjs"))
        if not profiles:
            return []   # nobody (and no operator profile) needs a fetch: nothing to keep fresh
        if not have_code:
            raise RuntimeError(f"no jobfinder checkout in {co}: run ops/hub_fetcher_install.sh")
        work = ctx.store("jobs", "profiles")
        for old in os.listdir(work):
            os.unlink(os.path.join(work, old))
        files = []
        for i, p in enumerate(profiles):
            path = os.path.join(work, f"p{i}.yml")
            open(path, "w").write(PORTALS_SKELETON)
            args = ["--into", path, "--write"]
            for flag, field in (("--regions", "regions"), ("--sectors", "sectors"), ("--remote", "remote"), ("--roles", "roles")):
                if p.get(field):
                    args += [flag, ",".join(p[field])]
            r = self.run_node("select-portals.mjs", args, timeout=120)
            if r.returncode != 0:
                raise RuntimeError(f"select-portals failed ({r.returncode}): {(r.stderr or r.stdout).strip().splitlines()[-1:]}")
            files.append(path)
        extra = shlex.split(os.environ.get("HUB_JOBFETCH_UNION_ARGS", ""))   # e.g. a switch that leaves keyword-built requests out of the shared store
        r = self.run_node("union-portals.mjs", ["--from", ",".join(files), "--out", os.path.join(co, "portals.yml")] + extra, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"union-portals failed ({r.returncode})")
        store = os.path.join(ctx.data, "shared", "jobs-http")
        os.makedirs(store, exist_ok=True)
        env = {**os.environ, "CAREER_OPS_ROOT": co, "CAREER_OPS_HTTP_CACHE_DIR": store, "CAREER_OPS_HTTP_CACHE_TTL_MS": str(self.TTL_MS)}
        if os.environ.get("HUB_JOBS_STORE_NO_STORE", "1") != "0":   # operator decision 2026-11-05: keep Workday's no-store answers, fetcher only
            env["CAREER_OPS_HTTP_CACHE_STORE_NO_STORE"] = "1"
        minutes = float(os.environ.get("HUB_JOBFETCH_TIMEOUT_MIN", "180"))
        try:
            r = self.run_node("scan.mjs", ["--quiet"], env=env, timeout=minutes * 60)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"the fetch took more than {minutes:.0f} minutes")
        if r.returncode != 0:
            raise RuntimeError(f"scan.mjs exit {r.returncode}: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")
        mark = os.path.join(store, ".fetched")
        tmp = mark + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"at": ctx.now, "ttl_ms": self.TTL_MS, "profiles": len(profiles)}, f)   # counts only: nothing about who asked for what
        os.chmod(tmp, 0o644)
        os.replace(tmp, mark)
        return []


def registry():
    return {c.kind: c for c in (YouTube(), RSS(), Security(), JobFetch())}
