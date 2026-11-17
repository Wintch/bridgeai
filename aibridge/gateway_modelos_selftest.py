#!/usr/bin/env python3
"""Offline checks for `gateway modelos`: the catalog of the models behind the media commands, this bot's medians from its log,
the not-installed list, and that the catalog names the same models the GPU services load. Run: python3 -I gateway_modelos_selftest.py"""
import contextlib, importlib.util, io, json, os, re, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
os.environ.update(GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log")
json.dump({}, open(f"{tmp}/gw.json", "w"))
spec = importlib.util.spec_from_file_location("gw", f"{HERE}/gateway.py")
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)

fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")

def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = gw.cmd_modelos(list(argv))
    return rc, out.getvalue()

now = time.time()
rows = [{"gateway": "image", "ok": True, "seconds": s, "ts": now - 60, "quality": "better"} for s in (7.0, 9.0, 30.0)]
rows += [{"gateway": "image", "ok": True, "seconds": 27.0, "ts": now - 60, "quality": "photo"}]                 # one job: no median
rows += [{"gateway": "image", "ok": False, "seconds": 1.0, "ts": now - 60, "quality": "better"}]                # failures ignored
rows += [{"gateway": "image", "ok": True, "seconds": 500.0, "ts": now - 90 * 86400, "quality": "better"}]       # too old
rows += [{"gateway": "makevideo", "ok": True, "seconds": s, "ts": now - 60, "secs": 5} for s in (418.0, 420.0)]
rows += [{"gateway": "makevideo", "ok": True, "seconds": 900.0, "ts": now - 60, "secs": 30, "part": 1}]         # parts of a chain ignored
with open(f"{tmp}/log", "w") as f:
    f.write("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")

rc, out = run()
check("rc", rc, 0)
for verb in ("image", "makevideo", "enhance", "upscale", "transcode", "mosh"):
    check(f"section {verb}", f"== gateway {verb}" in out, True)
check("model names", all(n in out for n in ("FLUX.2 klein 4B", "Z-Image Turbo", "SDXL-Lightning", "MiniMax H3 (")), True)
check("better median from the log (old and failed jobs left out)", "this bot: median 9 s over 3 job(s), slowest 30 s" in out, True)
check("a single job gives no median", "over 1 job" in out, False)
check("makevideo median per length, chain parts left out", "this bot (5 s): median 419 s over 2 job(s)" in out, True)
check("30 s part not counted", "(30 s)" in out, False)
check("not-installed section names H3-Image and FaceRefine", ("NOT installed" in out, "H3-Image" in out, "FaceRefine" in out), (True, True, True))
rc, out = run("image")
check("one verb", (rc, "== gateway makevideo" in out, "NOT installed" in out), (0, False, False))
rc, out = run("nope")
check("unknown verb", (rc, out.startswith("unknown command")), (2, True))
os.environ["GATEWAY_LOG"] = gw.LOG = f"{tmp}/missing"
rc, out = run()
check("no log: still the catalog", (rc, "this bot: median" in out or "this bot (" in out, "FLUX.2 klein" in out), (0, False, True))

# The catalog must name what the GPU services load (gpu-host is next to aibridge in the repo).
gh = os.path.join(HERE, "..", "gpu-host")
if os.path.isdir(gh):
    img = open(os.path.join(gh, "imggen", "server.py"), encoding="utf-8").read()
    tiers = re.search(r"TIERS\s*=\s*\{(.*?)\n\}", img, re.S)
    if tiers:
        body = tiers.group(1)
        check("imggen tiers = catalog modes", sorted(set(re.findall(r'"(fast|better|photo)"\s*:', body))),
              sorted(m["mode"].split()[1] for m in gw.MEDIA_MODELS["image"]["modes"]))
        check("better is klein", "klein" in re.search(r'"better":\s*\{[^}]*\}', body).group(0), True)
        check("photo is zimage", "zimage" in re.search(r'"photo":\s*\{[^}]*\}', body).group(0), True)
        check("fast is sdxl lightning", "lightning" in re.search(r'"fast":\s*\{[^}]*\}', body).group(0).lower(), True)
    vid = open(os.path.join(gh, "vidgen", "server.py"), encoding="utf-8").read()
    check("vidgen loads MiniMax H3", "minimax_h3" in vid, True)
    vp = open(os.path.join(gh, "vidpost", "server.py"), encoding="utf-8").read()
    check("vidpost uses RIFE 4.26 and general-x4v3", ("rife_v4.26" in vp, "general-x4v3" in vp), (True, True))

if fails:
    print("\n".join("FAIL " + f for f in fails))
    sys.exit(1)
print("gateway_modelos_selftest: all checks passed")
