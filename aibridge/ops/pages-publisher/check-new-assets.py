#!/usr/bin/env python3
"""check-new-assets.py REPO OLD_SHA NEW_SHA — refuse a publish that INTRODUCES a reference to a file the site does not have.

A bot added a gallery tile whose two images did not exist yet; published as it was, the live page would show a broken image.
Only NEW breakage blocks: a reference that is already missing at OLD_SHA (what is live) is the site's own business and never
stops a publish. HTML files are read straight from git (no checkout). A reference is src, srcset, poster, data-full, data-src,
data-poster, or href/content of a local file with a known asset extension; absolute URLs, data:, mailto:, tel:, javascript: and
anchors are ignored; a leading / is the site root, other paths resolve from the page's folder; ?query and #fragment are dropped.
Exit 0 = fine, 3 = blocked (the missing references are printed, one per line, "page -> missing/file").
"""
import posixpath, re, subprocess, sys
from html.parser import HTMLParser
from urllib.parse import unquote

ASSET_EXT = {"avif", "webp", "jpg", "jpeg", "png", "gif", "svg", "ico", "mp4", "webm", "mov", "mp3", "ogg", "wav", "pdf",
             "css", "js", "mjs", "json", "woff", "woff2", "ttf", "otf", "txt", "xml", "vtt", "srt"}
ATTRS = {"src", "poster", "data-full", "data-src", "data-poster", "data-thumb", "data-large"}


def git(repo, *a, text=True):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=text, check=True).stdout


class Refs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.refs = set()
    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if not v:
                continue
            if k in ATTRS:
                self.refs.add(v.strip())
            elif k == "srcset":
                for part in v.split(","):
                    if part.strip():
                        self.refs.add(part.strip().split()[0])
            elif k == "href" and tag == "link":
                self.refs.add(v.strip())
            elif k == "href" and tag == "a":
                self.refs.add(v.strip())


def local(ref, page):
    ref = ref.split("#")[0].split("?")[0].strip()
    if not ref or re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*:|//)", ref):
        return None
    ext = ref.rsplit(".", 1)[-1].lower() if "." in posixpath.basename(ref) else ""
    if ext not in ASSET_EXT:
        return None
    ref = unquote(ref)
    path = ref.lstrip("/") if ref.startswith("/") else posixpath.join(posixpath.dirname(page), ref)
    return posixpath.normpath(path)


def missing_at(repo, rev):
    files = set(git(repo, "ls-tree", "-r", "--name-only", rev).split("\n")) - {""}
    out = set()
    for f in sorted(files):
        if not f.lower().endswith((".html", ".htm")) or "/_antes/" in "/" + f or f.startswith("_antes/"):
            continue
        p = Refs()
        try:
            p.feed(git(repo, "show", f"{rev}:{f}"))
        except Exception:
            continue
        for r in p.refs:
            t = local(r, f)
            if t and t not in files:
                out.add((f, t))
    return out


def main(argv):
    if len(argv) != 3:
        print(__doc__); return 2
    repo, old, new = argv
    new_missing = missing_at(repo, new)
    try:
        old_missing = missing_at(repo, old)
    except subprocess.CalledProcessError:
        print("note: the last published commit is unknown here; nothing compared, not blocking"); return 0
    introduced = sorted(new_missing - old_missing)
    for page, target in introduced:
        print(f"{page} -> {target}")
    return 3 if introduced else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
