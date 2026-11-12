#!/usr/bin/env python3
"""Offline checks for soul_filter.py. Run: python3 -I soul_filter_selftest.py

A block marked `needs: KIND` stays only when the stack's gateways.json has a host of that kind, its `else:` line replaces it
otherwise, the markers never reach the output, and an unreadable config keeps everything. Also checks the real SOUL_bridgeai.md:
its image and video blocks are marked, and with every kind present nothing but the markers is removed."""
import importlib.util, json, os, subprocess, sys, tempfile
_TD = tempfile.TemporaryDirectory()

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sf", os.path.join(HERE, "soul_filter.py"))
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)
FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


T = """rule a
  <!-- needs: image -->
  - draw with gateway image
    more about pictures
  <!-- else: No pictures here: say so. -->
  <!-- end needs -->
  <!-- needs: video, vidpost -->
  - videos
  <!-- end needs -->
rule b
"""
check("kind present: the block stays, markers gone", sf.render(T, {"image", "video"}),
      "rule a\n  - draw with gateway image\n    more about pictures\n  - videos\nrule b\n")
check("kind missing: the else line replaces the block", sf.render(T, {"video"}), "rule a\n  - No pictures here: say so.\n  - videos\nrule b\n")
check("no else line: the block just goes", sf.render(T, {"image"}), "rule a\n  - draw with gateway image\n    more about pictures\nrule b\n")
check("several kinds: any one keeps the block", sf.render(T, {"vidpost"}).count("- videos"), 1)
check("nothing known: everything stays (fail open), markers gone", sf.render(T, None),
      "rule a\n  - draw with gateway image\n    more about pictures\n  - videos\nrule b\n")
check("an empty set leaves out every marked block", sf.render(T, set()), "rule a\n  - No pictures here: say so.\nrule b\n")

tmp = _TD.name
cfg = os.path.join(tmp, "gateways.json")
json.dump({"image": [{"name": "g", "url": "http://x:1"}], "video": [], "transcode": [{"name": "g"}], "stack": "s", "gates": {"g": {}}}, open(cfg, "w"))
check("kinds: only lists with a named host that has a url", sf.kinds(cfg), {"image"})
json.dump({"image": {"name": "g", "url": "http://x:1"}, "video": "g"}, open(os.path.join(tmp, "dicts.json"), "w"))
check("kinds: values that are not lists of hosts are ignored", sf.kinds(os.path.join(tmp, "dicts.json")), set())
check("kinds: missing file -> None", sf.kinds(os.path.join(tmp, "nope.json")), None)
open(os.path.join(tmp, "bad.json"), "w").write("{not json")
check("kinds: broken file -> None", sf.kinds(os.path.join(tmp, "bad.json")), None)

src = os.path.join(tmp, "soul.md")
open(src, "w").write(T)
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "soul_filter.py"), src], capture_output=True, text=True,
                   env={**os.environ, "GATEWAYS_CONFIG": cfg})
check("CLI: reads GATEWAYS_CONFIG and prints the filtered text", (r.returncode, "No pictures" in r.stdout, "- videos" in r.stdout),
      (0, False, False))
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "soul_filter.py"), os.path.join(tmp, "missing.md")], capture_output=True, text=True)
check("CLI: a missing SOUL file exits 1 with nothing on stdout (start_hermes then appends the file as it is)", (r.returncode, r.stdout), (1, ""))

real = open(os.path.join(HERE, "SOUL_bridgeai.md"), encoding="utf-8").read()
markers = [l for l in real.splitlines() if sf.NEEDS.match(l) or sf.ELSE.match(l) or sf.END.match(l)]
check("real SOUL: three marked blocks (image, image+video, video), two else lines", len(markers), 8)
full = sf.render(real, {"image", "video"})
check("real SOUL with every kind: only the marker lines are removed",
      full, "".join(l for l in real.splitlines(keepends=True) if not (sf.NEEDS.match(l) or sf.ELSE.match(l) or sf.END.match(l))))
bare = sf.render(real, {"transcode"})
check("real SOUL without image/video: no makevideo or gateway image instructions left", ("gateway makevideo" in bare, "gateway image --" in bare), (False, False))
check("real SOUL without image/video: the operator-rules marker stays (start_hermes looks for it)", "bridgeai: operator rules" in bare, True)
check("real SOUL without image/video: the 'Only promise what you can do' rule stays", "Only promise what you can do" in bare, True)

def has(text, s):
    return s in text


policy, ref, mkv, mkvfrom = "Adults in clothes", "gateway image --ref", "gateway makevideo", "makevideo --from"
for have, want in (
    ({"image", "video"}, (True, True, True, True)),
    ({"image"}, (True, True, False, False)),
    ({"video"}, (True, False, True, True)),
    (set(), (False, False, False, False)),
):
    t = sf.render(real, have)
    check(f"real SOUL with {sorted(have)}: policy / image --ref / makevideo / makevideo --from",
          (has(t, policy), has(t, ref), has(t, mkv), has(t, mkvfrom)), want)
    check(f"real SOUL with {sorted(have)}: no marker reaches the output", ("<!-- needs" in t, "<!-- else" in t, "<!-- end needs" in t), (False, False, False))
    check(f"real SOUL with {sorted(have)}: the operator-rules marker stays", "bridgeai: operator rules" in t, True)

# Malformed markers: never crash, never drop text outside a block.
check("unterminated block: the rest of the file belongs to it", sf.render("a\n<!-- needs: image -->\nb\n", set()), "a\n")
check("unterminated block with the kind present: kept", sf.render("a\n<!-- needs: image -->\nb\n", {"image"}), "a\nb\n")
check("else outside a block is kept as text", sf.render("a\n<!-- else: x -->\nb\n", set()), "a\n<!-- else: x -->\nb\n")
check("end without a start is dropped", sf.render("a\n<!-- end needs -->\nb\n", set()), "a\nb\n")
check("nested start: the inner one replaces the outer (text before it belonged to the outer block)", sf.render("<!-- needs: image -->\n1\n<!-- needs: video -->\n2\n<!-- end needs -->\n3\n", {"video"}), "2\n3\n")
check("CRLF line endings are handled", sf.render("a\r\n<!-- needs: image -->\r\nb\r\n<!-- end needs -->\r\nc\r\n", set()), "a\r\nc\r\n")
print(f"saved without image/video: {len(real) - len(bare)} characters (~{(len(real) - len(bare)) // 4} tokens)")
print("soul_filter_selftest: " + ("FAILED: " + "; ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
