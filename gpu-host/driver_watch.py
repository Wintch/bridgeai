#!/usr/bin/env python3
"""
driver_watch -- is there a newer NVIDIA driver, and what would a kernel or driver update need? On the GPU host, stdlib only.

  driver_watch.py run [--no-network]  look, write driver_watch.json into the gate's state dir (the weekly timer runs this). Exit 0.
                              --no-network skips the two public feeds below (the local look is the same).
  driver_watch.py status      print the last result and the operator steps (reads the file; `run` first if there is none)

It NEVER installs, removes or changes anything: no apt install, no apt update (that needs root; the lists are the operator's to
refresh, and their age is reported), no dkms, no reboot. It reads dpkg, apt-cache and `apt-get -s` (a simulation), dkms status,
/boot and the gpu-unlock packages, and reports:
  * the installed driver against the newest in the configured CUDA repo for the SAME branch and for NEWER branches. The pin
    (nvidia-driver-pinningVERSION) makes apt keep the installed version, so the comparison is explicit: candidates come from the
    pinning packages the repo offers and from `apt-cache madison` of the driver metapackages, which ignore the pin;
  * pending kernel updates (a new kernel needs the nvidia and gpu-unlock modules rebuilt by DKMS, and its headers) and installed
    kernels with no DKMS build of those modules (a reboot into one would come up without the driver or without the unlock);
  * while a kernel update is pending: /boot free space against the size of one kernel + initrd (the new one is written while the old
    ones are still there). Two installed kernels filling a small /boot with nothing pending is the steady state, not an alarm;
  * the gpu-unlock package versions, a newer one in the repo, and a version constraint that excludes the new driver.
and classifies every available update, so the operator knows how much hurry it is:
  * SECURITY (urgent): the installed driver is below the version a recent NVIDIA "GPU Display Driver" security bulletin fixes for its
    branch, and the repo offers a version at or above the fix. Read from the public GitHub repo NVIDIA/product-security (api.github.com
    contents listing, then the raw yearly index and the newest four bulletins; only the "Linux(R<branch>)" rows of the "Updated Version"
    table are used). "The fix exists but the configured repo does not offer it yet" is its own state (fix_not_in_repo).
  * PERFORMANCE / FEATURE (measure before adopting): an update that is not a proven security fix. It is adopted only after the selfcheck
    and a bench of the real jobs on the host (a new driver can drop the unlock or change a profile's best watts).
  * unknown: the bulletins could not be read (offline, rate limited, layout changed): reported as "could not check", never guessed.
  * gpu-unlock upstream (api.github.com/repos/Zagitta/gpu-unlock releases and tags): a newer STABLE version is reported; a pre-release
    (GitHub prerelease flag or an alpha/beta/rc suffix) is only mentioned, never recommended; tags that are not versions (packaging
    channels such as "unraid") are ignored.
The feeds are public and need no token: unauthenticated GETs, a generic User-Agent, at most four API calls a run, answers cached in
driver_watch_cache.json (a bulletin is fetched again only when its index row changes), the rate-limit headers respected (after a limit
the host stays off the network until the time GitHub gave), every failure a fixed word and the last cached answer, never a guess.
It then prints the exact operator steps: refresh the lists, read the simulation, make room, unpin and upgrade, rebuild DKMS, reboot, run
gpu_selfcheck.py, and how to roll back. A driver the gpu-unlock package was not built for may leave the card stock; the selfcheck
after the reboot is what tells.

Why: the unlock speeds FP16/TF32 work by about a third; a driver bump that silently drops it wastes energy on every job. Updating
the driver is how security fixes arrive, so it must stay current, and each update is verified by the selfcheck (GPU_WATCH.md).
The gate shows fixed words from the result in GET /state, and the ops bot tells the operator.
"""
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RESULT = "driver_watch.json"
DRIVER_META = ("cuda-drivers", "nvidia-open", "nvidia-driver", "nvidia-kernel-open-dkms")   # packages whose madison lists driver versions
PIN_PREFIX = "nvidia-driver-pinning-"
DKMS_MODULES = re.compile(r"^(nvidia|gpu[-_]unlock)", re.I)
MANUAL_PKG = re.compile(r"^(nvidia|libnvidia|cuda-drivers|xserver-xorg-video-nvidia|gpu-unlock)")
# /boot: apt writes the new kernel and a new initramfs while the old ones are still there, so one kernel's worth of space
# is not enough; 1.5x covers the temporary initramfs copy. It only matters while a kernel update is pending.
BOOT_MARGIN = 1.5
APT_STALE_DAYS = 14                                         # package lists older than this are reported; refreshing them is the operator's
VER = re.compile(r"^(?:\d+:)?(\d+(?:\.\d+){1,2})")

# --- the public feeds -------------------------------------------------------------------------------------------------------
CACHE = "driver_watch_cache.json"
SEC_REPO, UNLOCK_REPO = "NVIDIA/product-security", "Zagitta/gpu-unlock"
API, RAW = "https://api.github.com", "https://raw.githubusercontent.com"
USER_AGENT = "bridgeai-driver-watch"                        # generic: no host, person or project detail leaves the machine
MAX_BYTES = 4 * 2**20                                       # the biggest real bulletin is 0.3 MB
BULLETINS_READ = 4                                          # newest "GPU Display Driver" bulletins read (about a year of them)
BACKOFF_MAX_S = 6 * 3600
BULLETIN_TITLE = re.compile(r"GPU Display Driver", re.I)
INDEX_ROW = re.compile(r"^\|\s*\[(\d{3,6})\]\([^)]*\)\s*\|\s*([^|]+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|")
LINUX_BRANCH = re.compile(r"^Linux\(R(\d{3,4})\)$")
PLAIN_VERSION = re.compile(r"^(\d{3,4}\.\d{1,3}(?:\.\d{1,3})?)$")
SEMVER_TAG = re.compile(r"^v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})(?:[-.+]?([A-Za-z][A-Za-z0-9.-]{0,20}))?$")
PRE_WORDS = re.compile(r"^(alpha|beta|rc|pre|preview|dev|snapshot|nightly|test)", re.I)
CHANNEL = re.compile(r"^[A-Za-z0-9._-]{1,30}$")
SECURITY_WORDS = {"current": "current", "vulnerable_fix_in_repo": "fix_available", "vulnerable_fix_not_in_repo": "fix_not_in_repo", "unknown": "unknown"}


def load_selfcheck():
    spec = importlib.util.spec_from_file_location("driver_watch_selfcheck", os.path.join(HERE, "gpu_selfcheck.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Host:
    def __init__(self, base):
        self.cmd, self.read = base.cmd, base.read

    def disk(self, path):
        try:
            st = os.statvfs(path)
        except OSError:
            return None
        return st.f_frsize * st.f_blocks, st.f_frsize * st.f_bavail

    def boot_sizes(self, release):
        """{file: bytes} of the /boot files of one kernel release (vmlinuz, initrd.img, System.map, config)."""
        out = {}
        try:
            for n in os.listdir("/boot"):
                if n.endswith("-" + release):
                    out[n] = os.path.getsize(os.path.join("/boot", n))
        except OSError:
            pass
        return out

    def mtime(self, path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    now = staticmethod(time.time)


def vtuple(v):
    m = VER.match(v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def clean_version(v):
    """'1:595.71.05-1' -> '595.71.05' (epoch and Debian revision dropped); None when it does not look like a driver version."""
    m = VER.match(v or "")
    return m.group(1) if m else None


# ------------------------------------------------------------------------------------------------------------ the public feeds
class NetError(Exception):
    """A request that got no usable answer. `word` is a fixed word (unreachable, too_big)."""
    def __init__(self, word):
        self.word = word
        super().__init__(word)


class Net:
    """The only network code: an unauthenticated GET of an https URL on api.github.com or raw.githubusercontent.com."""

    def get(self, url, accept="*/*", timeout=20):
        """(status, {lowercase header: value}, body bytes). Raises NetError when there is no answer at all."""
        if not url.startswith((API + "/", RAW + "/")):
            raise NetError("bad_url")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, headers, body = r.status, r.headers, r.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as e:
            status, headers, body = e.code, e.headers, e.read(65536)
        except (OSError, ValueError):
            raise NetError("unreachable")
        if len(body) > MAX_BYTES:
            raise NetError("too_big")
        return status, {k.lower(): v for k, v in headers.items()}, body


def read_cache(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


class Source:
    """GETs with the rate-limit rules: while a backoff is in force nothing goes out; a 403/429 sets the backoff from Retry-After or
    X-RateLimit-Reset (at most BACKOFF_MAX_S); the last request of a window also sets it. `problems` collects fixed words."""

    def __init__(self, net, cache, now):
        self.net, self.cache, self.now = net, cache, now
        self.problems = []
        self.calls = 0

    def problem(self, word):
        if word not in self.problems:
            self.problems.append(word)

    def get(self, url, accept="*/*"):
        """The body as text, or None (the reason is in `problems`)."""
        now = self.now()
        if (self.cache.get("backoff_until") or 0) > now:
            self.problem("rate_limited")
            return None
        self.calls += 1
        try:
            status, h, body = self.net.get(url, accept)
        except NetError as e:
            self.problem(e.word)
            return None
        remaining = h.get("x-ratelimit-remaining")
        if status in (403, 429):
            until = now + 3600                                   # a limit with no times given: an hour
            if (h.get("retry-after") or "").isdigit():
                until = now + int(h["retry-after"])
            elif (h.get("x-ratelimit-reset") or "").isdigit() and remaining == "0":
                until = int(h["x-ratelimit-reset"])
            self.cache["backoff_until"] = int(min(until, now + BACKOFF_MAX_S))
            self.problem("rate_limited")
            return None
        if status == 404:
            self.problem("not_found")                            # the layout changed or the repo moved
            return None
        if status != 200:
            self.problem("http_error")
            return None
        if remaining == "0" and (h.get("x-ratelimit-reset") or "").isdigit():
            self.cache["backoff_until"] = int(min(int(h["x-ratelimit-reset"]), now + BACKOFF_MAX_S))   # that was the last call of the window
        return body.decode("utf-8", "replace")

    def json(self, url):
        text = self.get(url, "application/vnd.github+json")
        if text is None:
            return None
        try:
            return json.loads(text)
        except ValueError:
            self.problem("bad_response")
            return None


def parse_year_dirs(listing):
    """Years (newest first) of the directories named like a year in api.github.com's contents listing of the repo root."""
    if not isinstance(listing, list):
        return []
    return sorted({e["name"] for e in listing if isinstance(e, dict) and e.get("type") == "dir" and re.fullmatch(r"20\d\d", str(e.get("name")))}, reverse=True)


def parse_index(md, year):
    """[{id, year, initial, updated}] of the "GPU Display Driver" rows of a yearly README table ("| [5861](5861/5861.md) | Security Bulletin:
    GPU Display Driver - September 2026 | 2026-09-30 | 2026-10-13 | CVEs |"). Only digits and dates are kept, never the title."""
    out = []
    for line in md.splitlines():
        m = INDEX_ROW.match(line)
        if m and BULLETIN_TITLE.search(m.group(2)):
            out.append({"id": m.group(1), "year": year, "initial": m.group(3), "updated": m.group(4)})
    return out


def parse_bulletin(md):
    """{"fixed": {branch: version}, "cves": n, "max_cvss": x} of one bulletin. The "Updated Version" table has one row per CVE, product and
    platform; the Linux(R<branch>) rows (GeForce, RTX/Quadro/NVS, Tesla; not the vGPU rows) give the fixed version of a branch, and the
    highest of them is kept (a bulletin may fix one CVE later than another). A row whose version is not of its own branch is ignored."""
    fixed, cves, score = {}, set(), None
    for line in md.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 5 and re.fullmatch(r"CVE-\d{4}-\d{4,7}", cells[0]):
            m, v = LINUX_BRANCH.match(cells[2]), PLAIN_VERSION.match(cells[4])
            if m and v and v.group(1).split(".")[0] == m.group(1):
                cves.add(cells[0])
                b = m.group(1)
                if b not in fixed or vtuple(v.group(1)) > vtuple(fixed[b]):
                    fixed[b] = v.group(1)
        elif len(cells) == 7 and re.fullmatch(r"CVE-\d{4}-\d{4,7}", cells[0]):
            try:
                x = float(cells[3])
            except ValueError:
                continue
            if 0 <= x <= 10 and (score is None or x > score):
                score = x
    return {"fixed": fixed, "cves": len(cves), "max_cvss": score}


def security_feed(src, now):
    """The newest BULLETINS_READ driver bulletins with their fixed versions: {"bulletins": [{id, initial, updated, fixed, cves, max_cvss}],
    "problems": [...], "stale": bool}. A request that fails falls back to the cached answer of the same thing (stale=True)."""
    cache = src.cache.setdefault("security", {"index": {}, "bulletins": {}})
    stale = False
    years = parse_year_dirs(src.json(f"{API}/repos/{SEC_REPO}/contents/"))[:2]
    if not years:
        years = [str(time.gmtime(now).tm_year), str(time.gmtime(now).tm_year - 1)]          # the listing failed: the clock's years
    entries = []
    for y in years:
        md = src.get(f"{RAW}/{SEC_REPO}/main/{y}/README.md")
        if md is not None and any(INDEX_ROW.match(l) for l in md.splitlines()):
            cache["index"][y] = parse_index(md, y)
        elif md is not None:
            src.problem("bad_response")                          # an answer that has no table: the layout changed
            stale = stale or y in cache["index"]
        else:
            stale = stale or y in cache["index"]
        entries += cache["index"].get(y, [])
    entries.sort(key=lambda e: (e["initial"], int(e["id"])), reverse=True)
    out = []
    for e in entries[:BULLETINS_READ]:
        have = cache["bulletins"].get(e["id"])
        if not (have and have.get("updated") == e["updated"]):
            md = src.get(f"{RAW}/{SEC_REPO}/main/{e['year']}/{e['id']}/{e['id']}.md")
            if md is not None:
                parsed = parse_bulletin(md)
                if parsed["fixed"]:
                    have = dict(parsed, updated=e["updated"])
                    cache["bulletins"][e["id"]] = have
                else:
                    src.problem("bad_response")                  # a bulletin with no Linux table: not one this reads
                    have = None
            else:
                stale = stale or bool(have)
        if have:
            out.append({"id": e["id"], "initial": e["initial"], "updated": have["updated"], "fixed": have["fixed"], "cves": have["cves"], "max_cvss": have.get("max_cvss")})
    keep = {e["id"] for e in entries[:BULLETINS_READ]}
    cache["bulletins"] = {k: v for k, v in cache["bulletins"].items() if k in keep}
    return {"bulletins": out, "problems": list(src.problems), "stale": stale}


def security_picture(installed, feed, candidates):
    """The security state of the installed driver. `candidates` are the repo versions newer than it, in the order of preference (the newest
    of the same branch first). Returns {"state": current | vulnerable_fix_in_repo | vulnerable_fix_not_in_repo | unknown, ...}. Never guesses:
    no bulletin read, or none listing the installed branch, is "unknown" with a fixed word for why."""
    it = vtuple(installed)
    if feed is None:
        return {"state": "unknown", "why": "not_checked"}
    bl = feed.get("bulletins") or []
    if not bl or not it:
        probs = feed.get("problems") or []
        return {"state": "unknown", "why": probs[0] if probs else "no_bulletins"}
    branch = str(it[0])
    listing = [(b, b["fixed"][branch]) for b in bl if branch in b["fixed"]]
    base = {"installed_branch": branch, "bulletins_read": [b["id"] for b in bl], "stale": bool(feed.get("stale"))}
    if not listing:
        return dict(base, state="unknown", why="branch_unlisted")
    affecting = [(b, f) for b, f in listing if vtuple(f) > it]
    if not affecting:
        if branch not in bl[0]["fixed"]:
            # The newest bulletin no longer lists this branch: it is unaffected, or it is out of support and gets no more fixes. The
            # tables cannot tell which, so "current" would be a guess.
            return dict(base, state="unknown", why="branch_unlisted_newest")
        return dict(base, state="current")
    b, f = max(affecting, key=lambda x: vtuple(x[1]))

    def fixes(v):
        tb = str(vtuple(v)[0])
        return all(tb in x["fixed"] and vtuple(v) >= vtuple(x["fixed"][tb]) for x, _ in affecting)

    fix_target = next((v for v in candidates if vtuple(v) and fixes(v)), None)
    scores = [x["max_cvss"] for x, _ in affecting if x.get("max_cvss") is not None]
    return dict(base, state="vulnerable_fix_in_repo" if fix_target else "vulnerable_fix_not_in_repo", fixed_in=f, bulletin=b["id"],
                bulletin_updated=b["updated"], cves=sum(x["cves"] for x, _ in affecting), max_cvss=max(scores) if scores else None, fix_target=fix_target)


def semver(tag):
    """((major, minor, patch), prerelease?) of a version tag, None for a tag that is not a version (a packaging channel such as "unraid")."""
    m = SEMVER_TAG.match(tag or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups()[:3]), bool(m.group(4))


def unlock_feed(src):
    """The versioned gpu-unlock releases and tags: {"stable": [(tuple, tag)], "beta": [...], "channels": [names that are not versions], "problems"}.
    A release is a pre-release when GitHub flags it or its tag has an alpha/beta/rc-like suffix; any other suffix is also not stable (never
    guess upward). A tag without a release object counts as stable only when it has no suffix at all."""
    rels = src.json(f"{API}/repos/{UNLOCK_REPO}/releases?per_page=30")
    tags = src.json(f"{API}/repos/{UNLOCK_REPO}/tags?per_page=30")
    if not isinstance(rels, list) and not isinstance(tags, list):
        return {"ok": False, "problems": list(src.problems)}
    kinds, channels = {}, []
    for r in rels if isinstance(rels, list) else []:
        if not isinstance(r, dict) or r.get("draft") is True or not isinstance(r.get("tag_name"), str):
            continue
        sv = semver(r["tag_name"])
        if sv:
            kinds[r["tag_name"]] = (sv[0], bool(r.get("prerelease")) or sv[1])
        elif CHANNEL.match(r["tag_name"]):
            channels.append(r["tag_name"])
    for t in tags if isinstance(tags, list) else []:
        name = t.get("name") if isinstance(t, dict) else None
        if not isinstance(name, str) or name in kinds:
            continue
        sv = semver(name)
        if sv:
            kinds[name] = (sv[0], sv[1])
        elif CHANNEL.match(name) and name not in channels:
            channels.append(name)
    stable = sorted((v, t) for t, (v, pre) in kinds.items() if not pre)
    beta = sorted((v, t) for t, (v, pre) in kinds.items() if pre)
    return {"ok": True, "stable": stable, "beta": beta, "channels": sorted(channels)[:5], "problems": list(src.problems)}


def unlock_picture(installed, feed):
    """{"state": none | stable_newer | beta_only | unknown, ...}: newer than the installed gpu-unlock-dkms version. A pre-release is only ever
    "beta_only": described, never recommended."""
    it = vtuple(installed)
    if feed is None:
        return {"state": "unknown", "why": "not_checked"}
    if not feed.get("ok"):
        probs = feed.get("problems") or []
        return {"state": "unknown", "why": probs[0] if probs else "no_answer"}
    if not it:
        return {"state": "unknown", "why": "not_installed"}
    ver = lambda t: ".".join(str(x) for x in t)
    it3 = (it + (0, 0, 0))[:3]
    st, be = feed["stable"], feed["beta"]
    newer_stable = [x for x in st if x[0] > it3]
    newer_beta = [x for x in be if x[0] > it3]
    pic = {"installed": installed, "stable_latest": ver(st[-1][0]) if st else None, "beta_latest": ver(be[-1][0]) if be else None,
           "versioned_releases": len(st) + len(be), "channels": feed["channels"]}
    if newer_stable:
        return dict(pic, state="stable_newer", stable_newer=ver(newer_stable[-1][0]))
    if newer_beta:
        return dict(pic, state="beta_only")
    return dict(pic, state="none")


def fetch_feeds(state_dir, installed, unlock_installed, deps=None):
    """(security feed, unlock feed) with the cache read and written in the state dir. A failing feed is None with its problem words."""
    deps = deps or {}
    path = os.path.join(state_dir, CACHE)
    cache = read_cache(path)
    now = deps.get("now") or time.time
    src = Source(deps.get("net") or Net(), cache, now)
    sec = security_feed(src, now())
    un = unlock_feed(src)
    try:
        write_json(path, cache)
    except OSError:
        pass                                                     # a cache that cannot be written only costs a few requests next time
    return sec, un


# ------------------------------------------------------------------------------------------------------------------ parsing
def parse_madison(text):
    """Versions from `apt-cache madison PKG` lines: 'PKG | 595.71.05-1 | http://... suite/main amd64 Packages'."""
    out = set()
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            v = clean_version(parts[1])
            if v:
                out.add(v)
    return out


def parse_pin_names(text):
    """Versions from the names of the pinning packages the repo offers (nvidia-driver-pinning-595.71.05)."""
    out = set()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(PIN_PREFIX):
            v = clean_version(line[len(PIN_PREFIX):])
            if v:
                out.add(v)
    return out


def parse_dpkg_installed(text):
    """{package: version} for the lines 'ii |package|version' of dpkg-query -W -f='${db:Status-Abbrev}|${Package}|${Version}\\n'."""
    out = {}
    for line in text.splitlines():
        st, _, rest = line.partition("|")
        pkg, _, ver = rest.partition("|")
        if st.strip().startswith("ii") and pkg:
            out[pkg.strip()] = ver.strip()
    return out


def kernels_from_packages(installed):
    """Kernel releases from linux-image-RELEASE packages (the linux-image-amd64 metapackage and -dbg are not kernels)."""
    rel = []
    for p in installed:
        m = re.match(r"^linux-image-(\d\S*)$", p)
        if m and not p.endswith("-dbg"):
            rel.append(m.group(1))
    return sorted(rel, key=lambda r: [int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", r)])


def parse_sim_installs(text):
    """Package names of the 'Inst NAME ...' lines of `apt-get -s dist-upgrade`."""
    return [m.group(1) for m in (re.match(r"^Inst (\S+)", l) for l in text.splitlines()) if m]


def parse_dkms_status(text):
    """[(module, version, kernel, status)] of `dkms status`, old ('mod, ver, kernel, arch: installed') and new ('mod/ver, kernel, arch: installed')."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*([\w.-]+)[/,]\s*([\w.+~:-]+),\s*([\w.+~-]+)(?:,\s*[\w-]+)?\s*:\s*([A-Za-z][\w -]*)", line)
        if m:
            out.append((m.group(1), m.group(2), m.group(3), m.group(4).strip().split(" ")[0].lower()))
    return out


def dkms_gaps(kernels, rows):
    """[(kernel, module)] for each installed kernel where a watched DKMS module (nvidia*, gpu-unlock*) is seen for another kernel but
    has no 'installed' build for this one."""
    mods = sorted({r[0] for r in rows if DKMS_MODULES.match(r[0])})
    built = {(r[0], r[2]) for r in rows if r[3] == "installed"}
    return [(k, m) for k in kernels for m in mods if (m, k) not in built]


def parse_policy_candidate(text):
    m = re.search(r"^\s*Candidate:\s*(\S+)", text, re.M)
    return None if not m or m.group(1) == "(none)" else m.group(1)


def depends_constraints(depends):
    """[(package, operator, version)] for the nvidia packages named with a version in a Depends line."""
    return [(m.group(1), m.group(2), m.group(3)) for m in re.finditer(r"(nvidia[\w.+-]*)\s*\(\s*([<>=]+)\s*([\w.:+~-]+)\s*\)", depends or "")]


def constraint_excludes(constraints, target):
    """True when one of the constraints is an exact or bounded version that the target driver does not satisfy."""
    t = vtuple(target)
    for _pkg, op, ver in constraints:
        v = vtuple(ver)
        if t is None or v is None:
            continue
        if (op in ("=", "==") and t != v) or (op == "<<" and not t < v) or (op == "<=" and not t <= v) or (op == ">>" and not t > v) or (op == ">=" and not t >= v):
            return True
    return False


# --------------------------------------------------------------------------------------------------------------- the picture
def newest_by_branch(versions):
    out = {}
    for v in versions:
        t = vtuple(v)
        if t and (t[0] not in out or t > vtuple(out[t[0]])):
            out[t[0]] = v
    return out


def boot_picture(disk, kernels, sizes_by_kernel, pending_kernel):
    """(free MB, one kernel MB, kernels that fit, low?) from /boot's free space and the biggest installed kernel's files. `low` means the
    pending kernel update does not fit in the free space (always False with nothing pending: a /boot that holds exactly the installed
    kernels is how it is meant to be)."""
    if not disk:
        return {"free_mb": None, "one_kernel_mb": None, "fits": None, "low": False}
    total, free = disk
    one = max((sum(s.values()) for s in sizes_by_kernel.values()), default=0)
    fits = int(total // one) if one else None
    low = bool(one) and bool(pending_kernel) and free < BOOT_MARGIN * one
    return {"free_mb": int(free // 2**20), "one_kernel_mb": int(one // 2**20) if one else None, "fits": fits, "low": low}


def gather(host):
    smi = host.cmd(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], 15)
    installed = clean_version((smi[1].strip().splitlines() or [""])[0]) if smi[0] == 0 else None
    if not installed:
        m = re.search(r"\s(\d+\.\d+(?:\.\d+)?)\s", host.read("/proc/driver/nvidia/version") or "")
        installed = m.group(1) if m else None
    versions = parse_pin_names(host.cmd(["apt-cache", "pkgnames", PIN_PREFIX], 30)[1])
    for pkg in DRIVER_META:
        versions |= parse_madison(host.cmd(["apt-cache", "madison", pkg], 30)[1])
    dpkg_all = parse_dpkg_installed(host.cmd(["dpkg-query", "-W", "-f=${db:Status-Abbrev}|${Package}|${Version}\n"], 30)[1])
    running = (host.read("/proc/sys/kernel/osrelease") or "").strip()
    kernels = kernels_from_packages(dpkg_all)
    sim = parse_sim_installs(host.cmd(["apt-get", "-s", "dist-upgrade"], 120)[1])
    pend_img = [p[len("linux-image-"):] for p in sim if re.match(r"^linux-image-\d", p) and not p.endswith("-dbg")]
    pend_hdr = {p[len("linux-headers-"):] for p in sim if re.match(r"^linux-headers-\d", p)}
    headers_have = {p[len("linux-headers-"):] for p in dpkg_all if re.match(r"^linux-headers-\d", p)}
    rows = parse_dkms_status(host.cmd(["dkms", "status"], 30)[1])
    sizes = {k: host.boot_sizes(k) for k in kernels}
    # the driver packages to upgrade together: not the pin itself (it is swapped for the new one) and not gpu-unlock (its own version)
    manual = [p for p in host.cmd(["apt-mark", "showmanual"], 20)[1].split() if MANUAL_PKG.match(p) and not p.startswith((PIN_PREFIX, "gpu-unlock"))]
    unlock_dkms, unlock_fw = dpkg_all.get("gpu-unlock-dkms"), dpkg_all.get("gpu-unlock-firmware")
    cand = parse_policy_candidate(host.cmd(["apt-cache", "policy", "gpu-unlock-dkms"], 20)[1]) if unlock_dkms else None
    deps = host.cmd(["dpkg-query", "-W", "-f=${Depends}", "gpu-unlock-dkms"], 10)[1] if unlock_dkms else ""
    stamp = host.mtime("/var/lib/apt/periodic/update-success-stamp") or host.mtime("/var/lib/apt/lists")
    return {"installed": installed, "versions": versions, "running": running, "kernels": kernels, "pending": pend_img,
            "pending_headers": pend_hdr, "headers_have": headers_have, "dkms": rows, "sizes": sizes, "manual": manual,
            "manual_versions": {p: dpkg_all[p] for p in manual if p in dpkg_all}, "unlock_dkms": unlock_dkms,
            "unlock_fw": unlock_fw, "unlock_candidate": cand, "unlock_depends": deps, "disk": host.disk("/boot"),
            "apt_age_days": round((host.now() - stamp) / 86400, 1) if stamp else None, "now": host.now()}


def build(g, feeds=None):
    """The result dict (and the operator steps) from the gathered facts and, when given, the two public feeds ((security feed, gpu-unlock
    feed) of fetch_feeds; None = not checked). Pure."""
    inst = g["installed"]
    it = vtuple(inst)
    newer = sorted((v for v in g["versions"] if it and vtuple(v) > it), key=vtuple)
    same = [v for v in newer if vtuple(v)[0] == it[0]]
    other = newest_by_branch([v for v in newer if vtuple(v)[0] > it[0]])
    updates = "same_branch" if same else "newer_branch" if other else "none"
    target = same[-1] if same else (other[max(other)] if other else None)
    # security: the installed driver against the fixed versions of the recent bulletins, and which repo version fixes it
    sec_feed, un_feed = feeds if feeds else (None, None)
    candidates = ([same[-1]] if same else []) + [other[b] for b in sorted(other)]
    sec = security_picture(inst, sec_feed, candidates)
    if sec["state"] == "vulnerable_fix_in_repo":
        target = sec["fix_target"]                                  # the update that fixes it beats "the newest": the steps name this one
        updates = "same_branch" if vtuple(target)[0] == it[0] else "newer_branch"
    update_class = ("none" if not target else "security" if sec["state"] == "vulnerable_fix_in_repo"
                    else "unknown" if sec["state"] == "unknown" else "performance")
    unlock_up = unlock_picture(g["unlock_dkms"] and clean_version(g["unlock_dkms"]), un_feed)
    gaps = dkms_gaps(g["kernels"], g["dkms"])
    pending = list(g["pending"])
    headers_missing = [k for k in pending if k not in g["pending_headers"] and k not in g["headers_have"]]
    boot = boot_picture(g["disk"], g["kernels"], g["sizes"], bool(pending))
    constraints = depends_constraints(g["unlock_depends"])
    mismatch = bool(target) and constraint_excludes(constraints, target)
    unlock_newer = bool(g["unlock_candidate"] and g["unlock_dkms"] and g["unlock_candidate"] != g["unlock_dkms"])
    apt_stale = g["apt_age_days"] is not None and g["apt_age_days"] > APT_STALE_DAYS
    res = {"schema": 1, "at": int(g["now"]), "installed": inst, "running_kernel": g["running"],
           "newest": target or inst,
           "updates": updates, "target": target, "same_branch_newer": same, "newer_branches": {str(k): v for k, v in sorted(other.items())},
           "kernel_pending": bool(pending), "pending_kernels": pending, "headers_missing": headers_missing,
           "dkms_gap": bool(gaps), "dkms_gaps": [f"{m} for {k}" for k, m in gaps],
           "boot_low": boot["low"], "boot": boot, "unlock_mismatch": mismatch, "unlock_pkg": g["unlock_dkms"], "unlock_fw": g["unlock_fw"],
           "unlock_candidate": g["unlock_candidate"] if unlock_newer else None, "apt_stale": apt_stale, "apt_age_days": g["apt_age_days"],
           # the words the gate shows (GET /state) and the ops bot reads; the detail stays in this file
           "security": SECURITY_WORDS[sec["state"]], "update_class": update_class, "unlock_upstream": unlock_up["state"],
           "security_detail": sec, "unlock_upstream_detail": unlock_up}
    res["advice"] = advice(res, g)
    return res


def advice(res, g):
    """Operator steps, as plain strings. Package names and versions come from this host's dpkg; nothing here is run."""
    lines = []
    inst, target = res["installed"], res["target"]
    sd, ud, cls = res["security_detail"], res["unlock_upstream_detail"], res["update_class"]
    if res["security"] == "fix_available":
        lines.append(f"SECURITY (urgent): installed {inst} is below {sd['fixed_in']}, which NVIDIA's bulletin {sd['bulletin']} (updated {sd['bulletin_updated']}; "
                     f"{sd['cves']} CVEs" + (f", highest CVSS {sd['max_cvss']}" if sd.get("max_cvss") is not None else "") + f") fixes for branch {sd['installed_branch']}. "
                     f"The repo offers {target}. Update it as soon as the card is free; this is not a measure-first update, but the selfcheck after the reboot still decides whether the unlock survived.")
    elif res["security"] == "fix_not_in_repo":
        lines.append(f"SECURITY: NVIDIA's bulletin {sd['bulletin']} (updated {sd['bulletin_updated']}) fixes branch {sd['installed_branch']} in {sd['fixed_in']}; installed {inst} is below it "
                     "and the repo configured here offers no version at or above it yet"
                     + (f" (the package lists are {res['apt_age_days']:.0f} days old: `sudo apt update` first)." if res["apt_stale"] else ". Check again after the repo catches up, or see NVIDIA's download page."))
    if target and cls == "performance":
        lines.append("Class: PERFORMANCE / FEATURE, not a proven security fix: measure before adopting (the selfcheck, then a bench of the real jobs; a new driver can drop the unlock or move a profile's best watts).")
    elif target and cls == "unknown":
        lines.append(f"Class: could not check NVIDIA's security bulletins ({sd.get('why', '?')}), so this update is not classified: treat it as measure-before-adopting, and read the newest "
                     f"'GPU Display Driver' bulletin at https://github.com/{SEC_REPO} to see whether {inst} is affected.")
    if ud.get("state") == "stable_newer":
        lines.append(f"gpu-unlock upstream has a newer STABLE release {ud['stable_newer']} (installed {ud['installed']}). A performance/feature change of the speed-up patch: "
                     "measure before adopting (selfcheck, then a bench); it is not part of the driver update.")
    elif ud.get("state") == "beta_only":
        lines.append(f"gpu-unlock upstream has only a pre-release newer than the installed {ud['installed']} (beta {ud.get('beta_latest')}): NOT recommended. Pre-release builds are never offered as updates; "
                     "try one only on a card nobody is using, with the selfcheck and the rollback ready.")
    if target:
        where = "same branch" if res["updates"] == "same_branch" else "a NEWER branch (check NVIDIA's notes that it is a production branch, not a new-feature one)"
        lines.append(f"A newer driver is in the repo: {inst} -> {target} ({where}).")
    if res["kernel_pending"]:
        lines.append("Kernel update pending (" + ", ".join(res["pending_kernels"]) + "): DKMS must rebuild the nvidia and gpu-unlock modules for it.")
    if res["headers_missing"]:
        lines.append("Headers for " + ", ".join(res["headers_missing"]) + " are not installed or pending: DKMS cannot build without them.")
    if res["dkms_gap"]:
        lines.append("DKMS has no build for: " + "; ".join(res["dkms_gaps"]) + ". A reboot into that kernel would come up without the driver or the unlock.")
    if res["boot_low"]:
        b = res["boot"]
        lines.append(f"/boot cannot take the pending kernel: {b['free_mb']} MB free, one kernel+initrd is {b['one_kernel_mb']} MB, {b['fits']} kernels fit. "
                     "Remove the oldest kernel first (its linux-image-RELEASE package, then `sudo apt autoremove --purge`), then update.")
    if res["unlock_mismatch"] and res["security"] == "fix_available":
        lines.append(f"gpu-unlock-dkms {res['unlock_pkg']} declares a version requirement that excludes {target}: the security fix and the unlock conflict (see the note after the steps).")
    elif res["unlock_mismatch"]:
        lines.append(f"gpu-unlock-dkms {res['unlock_pkg']} declares a version requirement that excludes {target}: do not upgrade the driver until a matching gpu-unlock exists.")
    elif target:
        lines.append(f"gpu-unlock-dkms {res['unlock_pkg']} and gpu-unlock-firmware {res['unlock_fw']} were checked only with driver {inst}: they may not support {target}. "
                     "The selfcheck after the reboot says whether the unlock is still active; keep the rollback below ready.")
    if res["unlock_candidate"]:
        lines.append(f"A newer gpu-unlock-dkms is in the repo ({res['unlock_candidate']}).")
    if res["apt_stale"]:
        lines.append(f"The package lists are {res['apt_age_days']:.0f} days old: this report may be missing newer versions.")
    if not (target or res["kernel_pending"] or res["dkms_gap"] or res["boot_low"]):
        return lines or ["Nothing to do: the installed driver is the newest the repo offers and no kernel update is pending."]
    pkgs = " ".join(g["manual"]) or "<the nvidia packages installed here>"
    old_pkgs = " ".join(f"{p}={v}" for p, v in sorted(g["manual_versions"].items())) or "<package=version of each nvidia package now>"
    steps = ["Steps for the operator (nothing is done for you; stop work on the card first: `gateway gpu off`, then check the gate's GET /state shows no service running):"]
    steps.append("  1. sudo apt update")
    if target:
        steps.append(f"  2. Simulate: sudo apt install -s {PIN_PREFIX}{target} {pkgs}   (read it: it must not remove gpu-unlock-dkms, gpu-unlock-firmware or the running kernel; replacing the old pin is expected)")
        steps.append(f"  3. Apply:    sudo apt install {PIN_PREFIX}{target} {pkgs}   (the old pin {PIN_PREFIX}{inst} is replaced; DKMS rebuilds for every installed kernel that has headers)")
    else:
        steps.append("  2. Simulate: sudo apt-get -s dist-upgrade   (read the kernel and headers lines)")
        steps.append("  3. Apply:    sudo apt-get dist-upgrade   (DKMS rebuilds nvidia and gpu-unlock for the new kernel)")
    steps.append("  4. Check:    dkms status   (nvidia and gpu-unlock must say `installed` for every kernel in /boot) and df -h /boot")
    steps.append("  5. Reboot in a quiet window.")
    steps.append("  6. Verify:   python3 gpu-host/gpu_selfcheck.py run --force   (ok = the unlock is active; degraded = it is not)")
    steps.append(f"  7. Roll back if degraded: sudo apt install {PIN_PREFIX}{inst} {old_pkgs}, reboot, selfcheck again.")
    if target and cls in ("performance", "unknown"):
        steps.append("  8. Adopt only if the selfcheck says ok and a bench of the real jobs (gpu-host/bench_gate.py) shows no slowdown or extra Wh; otherwise roll back.")
    if target and res["security"] == "fix_available" and res["unlock_mismatch"]:
        steps.append("  (The security fix and gpu-unlock's version requirement conflict: updating now means giving up the unlock until a matching gpu-unlock exists, "
                     "about a third more time and energy on image and video jobs. That is the operator's call; the fix wins unless the card is isolated.)")
    return lines + steps


# ------------------------------------------------------------------------------------------------------------------- driver
def write_json(path, obj):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def write_result(state_dir, res):
    write_json(os.path.join(state_dir, RESULT), res)


def render(res):
    out = [f"driver {res['installed']} (kernel {res['running_kernel']}): " + {"none": "up to date", "same_branch": "newer version in the same branch",
                                                                          "newer_branch": "newer branch available"}[res["updates"]]]
    sec = res.get("security")
    if sec:
        out.append("security: " + {"current": "no recent NVIDIA bulletin affects this version", "fix_available": "URGENT: a security fix is in the repo",
                                    "fix_not_in_repo": "a security fix exists but the repo does not offer it yet",
                                    "unknown": "could not check NVIDIA's bulletins (" + str((res.get("security_detail") or {}).get("why", "?")) + ")"}[sec]
                   + f"; update class: {res.get('update_class', '?')}; gpu-unlock upstream: {res.get('unlock_upstream', '?')}")
    out += res["advice"]
    return "\n".join(out)


def main(argv=None, deps=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("run", "status") or set(argv[1:]) - {"--no-network"}:
        print(__doc__)
        return 2
    deps = deps or {}
    sc = deps.get("selfcheck") or load_selfcheck()
    env = deps.get("env") if deps.get("env") is not None else sc.load_env()
    sd = deps.get("state_dir") or sc.state_dir_of(env)
    if argv[0] == "status":
        res = sc.read_json(os.path.join(sd, RESULT))
        if not res:
            print("no driver_watch result yet: run `driver_watch.py run`")
            return 0
        print(render(res))
        return 0
    host = deps.get("host") or Host(sc.Host())
    g = gather(host)
    if not g["installed"]:
        print("driver_watch: cannot read the installed driver (no nvidia-smi, no /proc/driver/nvidia/version)", file=sys.stderr)
        return 2
    feeds = None
    if "--no-network" not in argv:
        feeds = fetch_feeds(sd, g["installed"], g["unlock_dkms"], deps)
    res = build(g, feeds)
    write_result(sd, res)
    print(render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
