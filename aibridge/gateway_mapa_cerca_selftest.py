#!/usr/bin/env python3
"""Offline checks for coordinates given to `gateway mapa cerca` (2026-11-02). Run: python3 -I gateway_mapa_cerca_selftest.py
The bot wrote `gateway mapa cerca "-34.5 -58.4"` twice in one night (coordinates where the KIND goes) and only got a list
of kinds back. Now a pair of coordinates anywhere in the arguments is the centre (--cerca) and the rest is the kind."""
import contextlib, importlib.util, io, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
os.environ.update(GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log",
                  AIBRIDGE_MAPS=f"{tmp}/mapas", HERMES_HOME=tmp)
json.dump({}, open(f"{tmp}/gw.json", "w"))
spec = importlib.util.spec_from_file_location("gw", f"{HERE}/gateway.py")
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)

fails = []
def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "  " + str(detail)))
    if not ok:
        fails.append(name)

sc = gw.split_coords
check("two coordinates with a space", sc(["-34.5219 -58.4803"]) == ([], "-34.5219,-58.4803"), sc(["-34.5219 -58.4803"]))
check("two coordinates as two arguments", sc(["-34.5219", "-58.4803"]) == ([], "-34.5219,-58.4803"))
check("comma with a space after", sc(["-34.5219, -58.4803"]) == ([], "-34.5219,-58.4803"))
check("the kind stays when the pair is at the end", sc(["cerveza", "-34.5,-58.4"]) == (["cerveza"], "-34.5,-58.4"))
check("a multi-word kind around the pair", sc(["para", "comprar", "-34.5,-58.4", "bebidas"]) == (["para comprar bebidas"], "-34.5,-58.4"))
check("no coordinates: untouched", sc(["supermercado"]) == (["supermercado"], None))
check("a single decimal is not a pair", sc(["2999.50"]) == (["2999.50"], None))
check("integers are not a pair", sc(["1500", "2000"]) == (["1500", "2000"], None))
check("out of range is not a pair", sc(["95.5 10.2"]) == (["95.5 10.2"], None))

seen = {}
def fake_places(sel, cats, near, radius):
    seen["near"] = (near["lat"], near["lon"], near.get("src"))
    return [{"name": "Kiosco X", "kind": "kiosco", "m": 120, "address": "Calle 1", "hours": "", "lat": near["lat"], "lon": near["lon"], "src": "osm"}]
gw.places_near = fake_places
gw.static_map = lambda pts, line: (None, None)
gw.last_pin = lambda: None

def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = gw.cmd_mapa(argv)
    return rc, out.getvalue()

rc, out = run(["cerca", "-34.5219 -58.4803"])
check("coordinates alone: exit 2 and the right usage", rc == 2 and "--cerca" in out and "gateway mapa cerca supermercado" in out and "mapa donde" in out, out[:200])
check("coordinates alone: no confusing 'no sé qué tipo'", "No sé qué tipo" not in out)
check("coordinates alone: nothing was searched", "near" not in seen)

rc, out = run(["cerca", "cerveza", "-34.5219", "-58.4803"])
check("kind + coordinates in the arguments: searched around that point", rc == 0 and seen.get("near") == (-34.5219, -58.4803, "coords"), (rc, seen, out[:200]))

seen.clear()
rc, out = run(["cerca", "cerveza", "--cerca", "-34.6,-58.4", "-34.5219,-58.4803"])
check("an explicit --cerca wins over coordinates in the arguments", seen.get("near") == (-34.6, -58.4, "coords"), seen)

seen.clear()
rc, out = run(["cerca", "cerveza"])
check("without coordinates and without a pin it still asks for the location", rc == 1 and "ubicación" in out and not seen, out[:200])

rc, out = run(["cerca", "zzzz"])
check("an unknown kind still lists the kinds", rc == 2 and "No sé qué tipo" in out)

print("\n" + ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
