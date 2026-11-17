#!/usr/bin/env python3
"""Offline checks for vehiculos.py (`gateway vehiculos`): fine and trip against cases solved by hand, number parsing, rule/search over the
guide, --json. Run: python3 -I vehiculos_selftest.py   (no network, no state on disk)"""
import contextlib, importlib.util, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append("FAIL " + name)


spec = importlib.util.spec_from_file_location("vehiculos", os.path.join(HERE, "vehiculos.py"))
ve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ve)
os.environ["VEHICULOS_GUIDE"] = os.path.join(HERE, "vehiculos")


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = ve.main([str(a) for a in argv])
    return rc, buf.getvalue()


def js(*argv):
    rc, out = run(*argv, "--json")
    return rc, json.loads(out)


def near(a, b, tol=0.01):
    return a is not None and abs(a - b) <= tol


# --- general
rc, out = run()
check("no arguments: usage, exit 2", rc == 2 and "vehiculos fine" in out)
rc, out = run("help")
check("help: usage, exit 0", rc == 0 and "vehiculos trip" in out)
rc, out = run("fine", "--help")
check("fine --help: only the fine lines", rc == 0 and "--uf-value" in out and "vehiculos trip" not in out)
rc, out = run("odometer")
check("unknown subcommand: plain sentence, exit 2", rc == 2 and "Unknown subcommand" in out)
check("AS_OF is the guide date", ve.AS_OF == "2026-11-15")

# --- numbers
check("num: decimal comma", ve.num("7,5", "x") == 7.5)
check("num: 1.250.000 is thousands", ve.num("1.250.000", "x") == 1250000)
check("num: 2.281,50 = 2281.5", ve.num("2.281,50", "x") == 2281.5)
try:
    ve.num("2.281", "x"); ok = False
except ve.Usage as e:
    ok = "ambiguous" in str(e)
check("num: 2.281 is refused as ambiguous", ok)
rc, d = js("fine", "--uf", "300", "--uf-value", "2.281")
check("fine: ambiguous UF value is exit 2 with an error in json", rc == 2 and "ambiguous" in d["error"])

# --- fine
# 300 UF × 2281 = 684300; 50 % off = 342150; break-even with no UF rise: p > 1 − 342150/684300 = 0.5
rc, d = js("fine", "--uf", "300", "--uf-value", "2281")
r = d["result"]
check("fine: 300 UF at 2281 = 684300", rc == 0 and near(r["amount_today"], 684300))
check("fine: voluntary 50 % = 342150", near(r["pay_voluntary"], 342150))
check("fine: break-even 50 % with no UF rise", near(r["p_win_break_even"], 0.5, 1e-4))
# a later UF of 2737.2 (+20 %): F' = 821160; p > 1 − 342150/821160 = 0.58333
rc, d = js("fine", "--uf", "300", "--uf-value", "2281", "--uf-later", "2737,2")
check("fine: UF +20 % raises the break-even to 58.33 %", near(d["result"]["p_win_break_even"], 0.58333, 1e-4) and near(d["result"]["amount_later"], 821160))
# reverse: amount 684300 at 2281 = 300 UF
rc, d = js("fine", "--amount", "684300", "--uf-value", "2281")
check("fine: amount back to 300 UF", near(d["result"]["units"], 300))
# with p 0.4: expected (1 − 0.4) × 684300 = 410580 > 342150 → paying now is cheaper (warn)
rc, d = js("fine", "--uf", "300", "--uf-value", "2281", "--p-win", "0.4")
check("fine: p 0.4 → pay now is cheaper (warn, exit 0)", rc == 0 and [f["status"] for f in d["findings"]] == ["warn"])
rc, d = js("fine", "--uf", "300", "--uf-value", "2281", "--p-win", "0.8")
check("fine: p 0.8 → disputing is cheaper (ok)", [f["status"] for f in d["findings"]] == ["ok"])
rc, out = run("fine", "--uf", "300", "--amount", "5", "--uf-value", "2281")
check("fine: --uf and --amount together is refused", rc == 2)
rc, out = run("fine", "--uf", "300", "--uf-value", "2281", "--discount", "1")
check("fine: discount 1 is refused", rc == 2)
rc, d = js("fine", "--uf", "100", "--uf-value", "1896", "--discount", "0")
check("fine: no discount → unknown finding asks to read the coupon", any(f["status"] == "unknown" for f in d["findings"]) and near(d["result"]["pay_voluntary"], 189600))

# --- trip
# 1000 km at 8 l/100 = 80 l; price 1500 → 120000; tolls 3000 + 4500
rc, d = js("trip", "--km", "1000", "--consumption", "8", "--price", "1500", "--toll", "3000", "--toll", "4500")
check("trip: 80 l and 120000 of fuel", rc == 0 and near(d["result"]["litres"], 80) and near(d["result"]["fuel_cost"], 120000))
check("trip: tolls add up to 7500", near(d["result"]["tolls"], 7500))
# tank 47 l, reserve 15 %: usable 39.95 l → range 39.95/8×100 = 499.375 → 499 km; refuels ceil(80/39.95) − 1 = 3 − 1 = 2 (1000 km > 2 × 499)
rc, d = js("trip", "--km", "1000", "--consumption", "8", "--tank", "47")
check("trip: range 499 km, 2 refuels", near(d["result"]["range_km"], 499, 0.5) and d["result"]["refuels"] == 2)
# 900 km: ceil(72/39.95) − 1 = 1
rc, d = js("trip", "--km", "900", "--consumption", "8", "--tank", "47")
check("trip: 900 km needs 1 refuel", d["result"]["refuels"] == 1)
rc, d = js("trip", "--km", "1000", "--consumption", "8", "--tank", "47", "--longest-gap", "300")
check("trip: 300 km gap within 80 % of range is ok", rc == 0 and [f["status"] for f in d["findings"]] == ["ok"])
rc, d = js("trip", "--km", "1000", "--consumption", "8", "--tank", "47", "--longest-gap", "450")
check("trip: 450 km gap is tight (warn)", rc == 0 and [f["status"] for f in d["findings"]] == ["warn"])
rc, d = js("trip", "--km", "1000", "--consumption", "8", "--tank", "47", "--longest-gap", "520")
check("trip: 520 km gap does not fit (fail, exit 1)", rc == 1 and [f["status"] for f in d["findings"]] == ["fail"])
rc, out = run("trip", "--km", "100", "--consumption", "8", "--longest-gap", "50")
check("trip: --longest-gap without --tank is refused", rc == 2)
rc, out = run("trip", "--km", "100", "--consumption", "80")
check("trip: consumption above 60 l/100 km is refused", rc == 2)

# --- json shape
rc, d = js("fine", "--uf", "300", "--uf-value", "2281", "--p-win", "0.5")
check("json: findings always carry check, rule, status, evidence",
      all(set(f) == {"check", "rule", "status", "evidence"} and f["status"] in ve.ORDER for f in d["findings"]))
check("json: as_of and legend present", d["as_of"] == ve.AS_OF and "legal advice" in d["legend"])

# --- guide: rule and search (needs the guide folder next to this file)
if os.path.isfile(os.path.join(HERE, "vehiculos", "RULES.md")):
    rc, out = run("rule", "VEH-MUL-1")
    check("rule: prints that rule only", rc == 0 and out.count("### VEH-") == 1 and "### VEH-MUL-1:" in out)
    rc, out = run("rule", "VEH-MUL-1", "VEH-GOL-1")
    check("rule: two IDs from two documents", rc == 0 and out.count("### VEH-") == 2)
    rc, out = run("rule", "VEH-ZZZ-1")
    check("rule: unknown ID says so, exit 1", rc == 1 and "not in the guide" in out)
    rc, out = run("rule", "ELEC-PRO-7")
    check("rule: an ID of another guide is refused, exit 2", rc == 2)
    rc, out = run("search", "MULTA")
    check("search: a Spanish word goes through GLOSSARY.md (multa → fine)", rc == 0 and "VEH-MUL-" in out)
    rc, out = run("search", "telepase")
    check("search: 'telepase' finds the toll rules", rc == 0 and "VEH-PEA-" in out)
    rc, out = run("search", "burro")
    check("search: 'burro' (starter motor) finds a starter rule through the glossary", rc == 0 and "starter" in out.lower())
    rc, out = run("search", "carburador")
    check("search: 'carburador' finds a Gol rule", rc == 0 and ("VEH-GRP-" in out or "VEH-GOL-" in out))
else:
    check("the guide folder vehiculos/ with RULES.md exists", False)

print("\n".join(fails) or "vehiculos_selftest: all ok")
sys.exit(1 if fails else 0)
