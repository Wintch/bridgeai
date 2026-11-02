#!/usr/bin/env python3
"""Offline checks for the CARTO basemap in `gateway mapa` (2026-11-02). Run: python3 -I gateway_carto_selftest.py
Terms checked here: the person's own key only, no server-side tile cache for CARTO, the credit on the picture, and a
watermarked ("API KEY REQUIRED") tile never reaching a person's map."""
import hashlib, importlib.util, io, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
os.environ.update(GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log",
                  AIBRIDGE_MAPS=f"{tmp}/mapas", HERMES_HOME=tmp)
json.dump({}, open(f"{tmp}/gw.json", "w"))
spec = importlib.util.spec_from_file_location("gw", f"{HERE}/gateway.py")
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)
from PIL import Image

fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)

def png(color):
    b = io.BytesIO(); Image.new("RGB", (256, 256), color).save(b, "PNG"); return b.getvalue()
GOOD, MARK = png("#aad3df"), png("#ffffff")
KEY = "cb1_test_1_" + "x" * 20
urls = []
mode = {"carto": "good"}
def fake_get(url, body=None, timeout=20):
    urls.append(url)
    if "cartocdn" in url:
        return MARK if mode["carto"] == "mark" else GOOD
    return GOOD                                           # OSM
gw.map_get = fake_get
gw.CARTO_WATERMARK_SHA256 = hashlib.sha256(MARK).hexdigest()
pts = [{"lat": -34.6037, "lon": -58.3816, "name": "A"}, {"lat": -34.6118, "lon": -58.4173, "name": "B"}]

open(f"{tmp}/.env", "w").write(f"CARTO_API_KEY={KEY}\n")
path, src = gw.static_map(pts, None)
check("with the person's key the picture comes from CARTO", src == "carto" and path and os.path.exists(path))
check("every tile asked carries the key as ?key= on the CARTO host", urls and all(u.startswith("https://basemaps.cartocdn.com/") and u.endswith("?key=" + KEY) for u in urls))
check("no tile is kept on the server for CARTO (no .tiles cache)", not os.path.exists(f"{tmp}/mapas/.tiles"))
check("a picture needs at most 30 tiles", len(urls) <= 30)

urls.clear(); mode["carto"] = "mark"
path, src = gw.static_map(pts, None)
check("a watermarked tile means the key was refused: the map is drawn from OSM instead", src == "osm" and path and any("openstreetmap" in u for u in urls))
check("the OSM fallback still caches (its policy asks for it)", os.path.exists(f"{tmp}/mapas/.tiles"))
logtext = open(f"{tmp}/log").read() if os.path.exists(f"{tmp}/log") else ""
check("the log says the fallback happened and never holds the key", "carto_fallback" in logtext and KEY not in logtext)

os.remove(f"{tmp}/.env"); urls.clear(); mode["carto"] = "good"
path, src = gw.static_map(pts, None)
check("without a CARTO key nothing is asked from CARTO", src == "osm" and not any("cartocdn" in u for u in urls))

ok, why = gw.service_check("carto", KEY)
check("a key CARTO accepts passes the check", ok)
mode["carto"] = "mark"
ok, why = gw.service_check("carto", KEY)
check("a key CARTO answers with the watermark does not, and the message is clear", (not ok) and "API KEY REQUIRED" in why and KEY not in why)
check("carto is in the optional services list, es/ru/en, with the terms note",
      "carto" in gw.SERVICES and all(gw.SERVICES["carto"]["note"][l] and "carto.com/legal/basemap-terms" in gw.SERVICES["carto"]["note"][l] for l in ("es", "ru", "en")))

print("\n%d failed" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
