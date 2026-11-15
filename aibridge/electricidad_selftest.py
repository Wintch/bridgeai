#!/usr/bin/env python3
"""Offline checks for electricidad.py (`gateway electricidad`): each subcommand against cases solved by hand, edges and --json.
Run: python3 -I electricidad_selftest.py   (no network, no state on disk)"""
import contextlib, importlib.util, io, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append("FAIL " + name)


spec = importlib.util.spec_from_file_location("electricidad", os.path.join(HERE, "electricidad.py"))
el = importlib.util.module_from_spec(spec)
spec.loader.exec_module(el)


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = el.main([str(a) for a in argv])
    return rc, buf.getvalue()


def js(*argv):
    rc, out = run(*argv, "--json")
    return rc, json.loads(out)


def near(a, b, tol=0.01):
    return a is not None and abs(a - b) <= tol


def st(doc, check_name):
    return [f["status"] for f in doc["findings"] if f["check"] == check_name]


R70_CU = (234.5 + 70) / 254.5          # 1.196464: IEC 60228 annex B, copper from 20 °C to 70 °C

# --- general
rc, out = run()
check("no arguments: usage, exit 2", rc == 2 and "electricidad current" in out)
rc, out = run("help")
check("help: usage, exit 0", rc == 0 and "electricidad tables" in out)
rc, out = run("voltmeter")
check("unknown subcommand: plain sentence, exit 2", rc == 2 and "Unknown subcommand" in out)
check("AS_OF is the guide date", el.AS_OF == "2026-11-15")

# --- current
# 2200 W, cos φ 0.85, 220 V: I = 2200 / (220 × 0.85) = 2200 / 187 = 11.765 A
rc, d = js("current", "--power", "2200")
check("current: 2200 W single cos 0.85 = 11.76 A", rc == 0 and near(d["result"]["current_a"], 11.765))
# 2200 VA: I = 2200 / 220 = 10 A
rc, d = js("current", "--power", "2200", "--va")
check("current: 2200 VA single = 10 A", near(d["result"]["current_a"], 10.0))
# 10 kW three-phase cos 0.85: I = 10000 / (√3 × 380 × 0.85) = 10000 / 559.45 = 17.875 A
rc, d = js("current", "--power", "10000", "--system", "three")
check("current: 10 kW three = 17.87 A", near(d["result"]["current_a"], 17.875))
# reverse: 16 A single → S = 220 × 16 = 3520 VA, P = 3520 × 0.85 = 2992 W
rc, d = js("current", "--current", "16")
check("current: 16 A single = 3520 VA / 2992 W", near(d["result"]["power_va"], 3520) and near(d["result"]["power_w"], 2992))
rc, d = js("current", "--current", "10", "--pf", "0,9", "--voltage", "230")
check("current: comma decimal and custom voltage (10 A × 230 V × 0.9 = 2070 W)", near(d["result"]["power_w"], 2070))
check("current: every result carries the legend and as_of", d["legend"] == el.LEGEND and d["as_of"] == "2026-11-15")
rc, out = run("current", "--power", "2200", "--current", "10")
check("current: both directions at once is refused (exit 2)", rc == 2 and "one of the two" in out)
rc, out = run("current", "--power", "-5")
check("current: negative power refused", rc == 2 and "greater than zero" in out)
rc, out = run("current", "--power", "two thousand")
check("current: a word where a number goes is refused", rc == 2 and "number" in out)
rc, out = run("current", "--power", "100", "--pf", "1,2")
check("current: cos φ above 1 refused", rc == 2 and "--pf" in out)
rc, out = run("current", "--power", "100", "--watts", "3")
check("current: unknown option named in the error", rc == 2 and "--watts" in out)
rc, out = run("current", "--power", "2200")
check("text: decimal point, legend and the agent note", "11.76 A" in out and "Indicative" in out and "Internal note" in out)

# --- drop
# 10 A, 20 m, 2.5 mm² cu class 5, single, cos 0.85:
# R70 = 7.98 × 1.196464 = 9.5478 Ω/km; ΔU = 2 × 10 × 0.020 × 9.5478 × 0.85 = 3.2462 V → 3.2462 / 220 = 1.4756 %
rc, d = js("drop", "--current", "10", "--length", "20", "--section", "2.5")
check("drop: R at 70 °C = 9.548 Ω/km", near(d["result"]["r70_ohm_km"], 7.98 * R70_CU, 0.001))
check("drop: 10 A 20 m 2.5 mm² = 3.25 V / 1.48 %", near(d["result"]["drop_v"], 3.246) and near(d["result"]["drop_pct"], 1.4756))
check("drop: final circuit under 3 % is ok, exit 0", rc == 0 and st(d, "drop_final") == ["ok"])
# same calculation against AEA table 770.15.IV (cos 0.8, V/A·km): 2.5 mm² → 15. Our R: 2 × 9.5478 × 0.8 = 15.28
check("drop: our R reproduces AEA table 770.15.IV (2.5 mm² ≈ 15 V/A·km at cos 0.8)", abs(2 * 7.98 * R70_CU * 0.8 - 15) < 0.5)
# 16 A, 45 m, 2.5 mm²: ΔU = 2 × 16 × 0.045 × 9.5478 × 0.85 = 11.6865 V → 5.312 % > 3 %
rc, d = js("drop", "--current", "16", "--length", "45", "--section", "2.5")
check("drop: 16 A 45 m 2.5 mm² = 5.31 % fails the 3 % (exit 1)", rc == 1 and near(d["result"]["drop_pct"], 5.312) and st(d, "drop_final") == ["fail"])
# --upstream-drop: 2.5 % in this run + 1 % upstream > 3 %: 10 A × 34 m on 2.5 mm²: 2 × 10 × 0.034 × 8.1156 = 5.5186 V → 2.508 %
rc, d = js("drop", "--current", "10", "--length", "34", "--section", "2.5", "--upstream-drop", "1")
check("drop: upstream 1 % + 2.51 % here exceeds the 3 % total", rc == 1 and near(d["result"]["total_pct"], 3.508))
# three-phase: 20 A, 50 m, 6 mm²: R70 = 3.30 × 1.196464 = 3.94833; ΔU = √3 × 20 × 0.05 × 3.94833 × 0.85 = 5.8129 V → /380 = 1.5297 %
rc, d = js("drop", "--current", "20", "--length", "50", "--section", "6", "--system", "three", "--line", "submain")
check("drop: three 20 A 50 m 6 mm² = 5.81 V / 1.53 %", near(d["result"]["drop_v"], 5.813) and near(d["result"]["drop_pct"], 1.5297))
check("drop: submain over 1 % fails", rc == 1 and st(d, "drop_submain") == ["fail"])
# aluminium 16 mm², class 2: R70 = 1.91 × 298/248 = 2.29508; 40 A, 30 m single cos 1: ΔU = 2 × 40 × 0.03 × 2.29508 = 5.5082 V
rc, d = js("drop", "--current", "40", "--length", "30", "--section", "16", "--material", "al", "--pf", "1")
check("drop: aluminium uses its own R and coefficient (5.51 V)", near(d["result"]["drop_v"], 5.508))
# reactance: 100 A, 40 m, 35 mm², X = 0.08: ΔU = 2 × 100 × 0.04 × (0.554 × 1.196464 × 0.85 + 0.08 × 0.5268) = 8 × (0.56341 + 0.04214) = 4.8444 V
rc, d = js("drop", "--current", "100", "--length", "40", "--section", "35", "--reactance", "0,08")
check("drop: reactance term added (4.84 V)", near(d["result"]["drop_v"], 4.844))
rc, d = js("drop", "--current", "100", "--length", "40", "--section", "50")
check("drop: big section without reactance gets a warning", st(d, "reactance") == ["warn"])
rc, d = js("drop", "--current", "40", "--length", "15", "--section", "10", "--line", "main")
check("drop: main line has no verified limit, shown as unknown (never ok)", st(d, "drop_main") == ["unknown"] and rc == 0
      and d["result"]["limit_pct"] is None)
rc, out = run("drop", "--current", "10", "--length", "20", "--section", "3")
check("drop: a section that does not exist is refused with the list", rc == 2 and "Section 3 mm² does not exist" in out and "2.5" in out)
rc, out = run("drop", "--current", "10", "--length", "20", "--section", "2.5", "--material", "al")
check("drop: 2.5 mm² aluminium is refused", rc == 2 and "al class 2" in out)
rc, out = run("drop", "--current", "10", "--section", "2.5")
check("drop: missing --length is named", rc == 2 and "--length" in out)
rc, d = js("drop", "--current", "10", "--length", "20", "--section", "2.5", "--line", "service")
check("drop: unknown line type refused in JSON too", rc == 2 and "error" in d and "--line" in d["error"])

# --- size
# TUG 10 A, 20 m: minimum 2.5 mm² (770.11.I); Iz 21 A; MCB 10 A; drop 1.48 % (calculation above) → 2.5 mm², the minimum governs
rc, d = js("size", "--current", "10", "--length", "20", "--circuit", "tug")
r = d["result"]
check("size: TUG 10 A 20 m → 2.5 mm², MCB 10 A, up to 20 A", rc == 0 and r["section_mm2"] == 2.5 and r["mcb_a"] == 10 and r["mcb_max_a"] == 20)
check("size: the regulatory minimum governs", "minimum" in r["governed_by"])
# IUG 5 A, 10 m → minimum 1.5 mm²; Iz 15 A, MCB 6 A, max 16 (IUG cap 16 A and Iz 15 → 10 A)
rc, d = js("size", "--current", "5", "--length", "10", "--circuit", "iug")
check("size: IUG 5 A → 1.5 mm², MCB 6 A, top 10 A (Iz 15 A)", d["result"]["section_mm2"] == 1.5 and d["result"]["mcb_a"] == 6
      and d["result"]["mcb_max_a"] == 10)
# TUE 16 A, 45 m: 2.5 → 5.31 %; 4 mm² → 2 × 16 × 0.045 × 4.95 × 1.196464 × 0.85 = 7.2491 V = 3.295 %; 6 mm² → 4.8328 V = 2.197 % → 6 mm²
rc, d = js("size", "--current", "16", "--length", "45", "--circuit", "tue")
check("size: TUE 16 A 45 m → 6 mm² by voltage drop (2.20 %)", d["result"]["section_mm2"] == 6 and near(d["result"]["drop_pct"], 2.197)
      and "drop" in d["result"]["governed_by"])
# submain 30 A, 10 m, 2 circuits in the conduit (0.8): 6 mm² → 36 × 0.8 = 28.8 < 30; 10 mm² → 50 × 0.8 = 40 ≥ MCB 32 ≥ 30
# drop 10 mm²: 2 × 30 × 0.010 × 1.91 × 1.196464 × 0.85 = 1.1655 V = 0.530 % ≤ 1 %
rc, d = js("size", "--current", "30", "--length", "10", "--circuit", "submain", "--grouped", "2")
r = d["result"]
check("size: submain 30 A grouped ×0.8 → 10 mm², Iz 40 A, MCB 32 A", r["section_mm2"] == 10 and near(r["iz_a"], 40) and r["mcb_a"] == 32
      and near(r["drop_pct"], 0.530) and "current" in r["governed_by"])
# temperature 50 °C: table 771.16.II.a f = 0.82; TUG 18 A → 2.5 mm²: 21 × 0.82 = 17.22 < MCB 20; 4 mm²: 28 × 0.82 = 22.96 → MCB 20 ✓
rc, d = js("size", "--current", "18", "--length", "5", "--circuit", "tug", "--temp", "50")
check("size: 50 °C derates (f 0.82, table 771.16.II.a) → 4 mm² for 18 A TUG", d["result"]["section_mm2"] == 4
      and near(d["result"]["f_temp"], 0.82, 0.001) and d["result"]["mcb_a"] == 20)
check("size: a temperature off 40 °C cites table 771.16.II.a and is not flagged as unverified",
      st(d, "temperature") == ["ok"] and "unverified_data" not in [f["check"] for f in d["findings"]])
rc, d = js("size", "--current", "10", "--length", "5", "--circuit", "tug", "--temp", "42")
check("size: 42 °C is not in the table → takes the 45 °C row (0.91), the stricter one", near(d["result"]["f_temp"], 0.91, 0.001))
rc, d = js("size", "--current", "10", "--length", "5", "--circuit", "tug", "--temp", "12")
check("size: below 20 °C uses the 20 °C factor (1.29), no extra credit for cold", near(d["result"]["f_temp"], 1.29, 0.001))
rc, d = js("size", "--current", "10", "--length", "5", "--circuit", "tug", "--grouped", "4")
check("size: 4 grouped circuits uses 0.65 from table 771.16.IV (verified)", near(d["result"]["f_grouping"], 0.65)
      and "unverified_data" not in [f["check"] for f in d["findings"]])
rc, d = js("size", "--current", "10", "--length", "5", "--circuit", "tug", "--grouped", "7")
check("size: 7 grouped circuits uses the IEC factor and says it is not verified", near(d["result"]["f_grouping"], 0.54)
      and "unknown" in st(d, "unverified_data"))
# three-phase submain 25 A, 20 m, 3 conductors: 4 mm² 3x = 25 A passes on current (MCB 25 ≤ 25), but the drop
# √3 × 25 × 0.020 × 4.95 × 1.196464 × 0.85 = 0.86603 × 5.03409 = 4.3597 V = 1.147 % > 1 % → 6 mm²:
# √3 × 25 × 0.020 × 3.30 × 1.196464 × 0.85 = 0.86603 × 3.35608 = 2.9065 V = 0.765 % ✓ (Iz 3x 32 A)
rc, d = js("size", "--current", "25", "--length", "20", "--circuit", "submain", "--system", "three")
check("size: three submain 25 A 20 m → 6 mm² (3x column, drop governs), MCB 25 A", d["result"]["section_mm2"] == 6 and d["result"]["conductors"] == 3
      and d["result"]["iz_a"] == 32 and d["result"]["mcb_a"] == 25 and near(d["result"]["drop_pct"], 0.765) and "drop" in d["result"]["governed_by"])
# the same at 10 m: 4 mm² gives 0.574 % and is enough → 4 mm² by current
rc, d = js("size", "--current", "25", "--length", "10", "--circuit", "submain", "--system", "three")
check("size: three submain 25 A 10 m → 4 mm² (3x 25 A), MCB 25 A", d["result"]["section_mm2"] == 4 and near(d["result"]["drop_pct"], 0.574))
# main 40 A, 15 m: minimum 4 mm²; 6 mm² 36 < 40; 10 mm² 50 ≥ MCB 40 → 10 mm²; no verified drop limit → unknown
rc, d = js("size", "--current", "40", "--length", "15", "--circuit", "main")
check("size: main line 40 A → 10 mm², drop limit unknown (not ok)", d["result"]["section_mm2"] == 10 and st(d, "drop") == ["unknown"] and rc == 0)
rc, d = js("size", "--current", "40", "--length", "15", "--circuit", "main", "--max-drop", "0,5")
# with 0.5 %: 10 mm² → 2 × 40 × 0.015 × 2.28525 × 0.85 = 2.3309 V = 1.06 % ✗; 16 → 1.21 × 1.196464 = 1.44772 → 1.4767 V = 0.671 % ✗;
# 25 → 0.78 × 1.196464 = 0.93324 → 0.9519 V = 0.4327 % ✓ → 25 mm²
check("size: user drop limit 0.5 % pushes the main line to 25 mm²", d["result"]["section_mm2"] == 25 and st(d, "drop") == ["ok"])
rc, d = js("size", "--current", "500", "--length", "10", "--circuit", "submain")
check("size: 500 A fits no section of the table (max 398 A at 300 mm², exit 1)", rc == 1 and d["result"]["section_mm2"] is None
      and st(d, "section") == ["fail"])
# 100 A submain, 10 m, single: Iz ≥ 100 → 35 mm² (109 A); drop 2 × 100 × 0.010 × 0.554 × 1.196464 × 0.85 = 1.1268 V = 0.512 % ✓
rc, d = js("size", "--current", "100", "--length", "10", "--circuit", "submain")
check("size: 100 A sizes the cable (35 mm²) and warns there is no usual MCB above 63 A", rc == 0 and d["result"]["section_mm2"] == 35
      and d["result"]["mcb_a"] is None and st(d, "mcb") == ["warn"] and near(d["result"]["drop_pct"], 0.512))
rc, d = js("size", "--current", "60", "--length", "400", "--circuit", "submain")
check("size: a load that no section carries within the drop limit (exit 1)", rc == 1 and st(d, "section") == ["fail"])
rc, d = js("size", "--current", "18", "--length", "10", "--circuit", "iug")
check("size: 18 A on an IUG (max 16 A) is a fail with what to do", rc == 1 and st(d, "circuit_type") == ["fail"])
rc, out = run("size", "--current", "10", "--length", "10", "--circuit", "tug", "--material", "al")
check("size: aluminium refused (the table is copper only)", rc == 2 and "copper" in out)
rc, out = run("size", "--current", "10", "--length", "10")
check("size: missing --circuit lists the types", rc == 2 and "iug" in out and "tug" in out)
rc, out = run("size", "--current", "10", "--length", "10", "--circuit", "tug", "--system", "three")
check("size: TUG three-phase refused (770.6.6)", rc == 2 and "single-phase" in out)
rc, out = run("size", "--current", "10", "--length", "10", "--circuit", "tug", "--temp", "70")
check("size: temperature out of range refused", rc == 2 and "--temp" in out)
rc, out = run("size", "--current", "10", "--length", "10", "--circuit", "tug", "--grouped", "2,5")
check("size: a fractional circuit count is refused", rc == 2 and "--grouped" in out)

# --- coordinate
# Ib 10, In 16, Iz 21 (2.5 mm² 2x): 10 ≤ 16 ≤ 21; I2 = 1.45 × 16 = 23.2 ≤ 1.45 × 21 = 30.45 → complies
rc, d = js("coordinate", "--ib", "10", "--in", "16", "--section", "2.5")
check("coordinate: 10/16/21 A complies, exit 0", rc == 0 and d["result"]["complies"] and near(d["result"]["i2_a"], 23.2))
rc, d = js("coordinate", "--ib", "18", "--in", "16", "--iz", "21")
check("coordinate: Ib above In fails", rc == 1 and st(d, "ib_le_in") == ["fail"])
rc, d = js("coordinate", "--ib", "10", "--in", "25", "--iz", "21")
check("coordinate: In above Iz fails (and I2 too: 36.25 > 30.45)", rc == 1 and st(d, "in_le_iz") == ["fail"] and st(d, "i2_le_145iz") == ["fail"])
# grouped 2: Iz = 21 × 0.8 = 16.8 → In 16 complies, In 20 does not
rc, d = js("coordinate", "--ib", "10", "--in", "16", "--section", "2.5", "--grouped", "2")
check("coordinate: grouped Iz 16.8 A takes In 16", rc == 0 and near(d["result"]["iz_a"], 16.8))
# gG fuse In 20 on Iz 21: In ≤ Iz but I2 = 1.6 × 20 = 32 > 30.45 → fails (hence with fuses In ≤ 0.9 Iz)
rc, d = js("coordinate", "--ib", "15", "--in", "20", "--iz", "21", "--device", "fuse")
check("coordinate: gG fuse 20 A on Iz 21 A fails I2 ≤ 1.45 Iz though In ≤ Iz", rc == 1 and st(d, "in_le_iz") == ["ok"]
      and st(d, "i2_le_145iz") == ["fail"] and "unknown" in st(d, "unverified_data"))
rc, d = js("coordinate", "--ib", "10", "--in", "15", "--iz", "21")
check("coordinate: a non-standard rating gets a warning", st(d, "standard_rating") == ["warn"])
rc, out = run("coordinate", "--ib", "10", "--in", "16")
check("coordinate: needs --iz or --section", rc == 2 and "--iz" in out)
rc, out = run("coordinate", "--ib", "10", "--in", "16", "--section", "7")
check("coordinate: nonexistent section refused", rc == 2 and "Section 7 mm² does not exist" in out)

# --- demand (770 by default)
# 75 m² + 50 % × 10 m² = 80 m² → Medium. IUG 8 points: 2/3 × 8 × 60 = 320; IUG 6: 240; TUG 2200; TUE 3300 → 6060 VA
# Medium coefficient (3 minimum circuits) 0.8 → 4848 VA → 4848 / 220 = 22.036 A. Circuits: IUG 2 + TUG 1 = 3 → complies
rc, d = js("demand", "--area", "75", "--semi-covered", "10", "--iug", "8", "--iug", "6", "--tug", "10", "--tue", "1")
r = d["result"]
check("demand 770: 80 m² → Medium", r["grade"] == "medium" and near(r["calc_area_m2"], 80))
check("demand 770: sum 6060 VA × 0.8 = 4848 VA, 22.04 A", near(r["sum_va"], 6060) and near(r["dpms_va"], 4848) and near(r["dpms_current_a"], 22.036))
check("demand 770: minimum circuits met, exit 0", rc == 0 and r["missing"] == [])
# same dwelling under 771: IUG 0.66 × 150 × 8 = 792; 0.66 × 150 × 6 = 594; + 2200 + 3300 = 6886 VA ≤ 7 kVA → Medium; × 0.9 = 6197.4 VA → 28.17 A
rc, d = js("demand", "--area", "75", "--semi-covered", "10", "--iug", "8", "--iug", "6", "--tug", "10", "--tue", "1", "--norm", "771")
r = d["result"]
check("demand 771: sum 6886 VA, Medium, × 0.9 = 6197.4 VA, 28.17 A", near(r["sum_va"], 6886) and r["grade"] == "medium"
      and near(r["dpms_va"], 6197.4) and near(r["dpms_current_a"], 28.17))
# 771, 50 m² (Minimum by area) with IUG 10 points (990) + 2 TUG (4400) = 5390 VA > 3.7 kVA → up to Medium; × 0.9 = 4851 VA
rc, d = js("demand", "--area", "50", "--iug", "10", "--tug", "6", "--tug", "6", "--norm", "771")
r = d["result"]
check("demand 771: DPMS above the grade cap moves 50 m² up to Medium", r["grade_by_area"] == "minimum" and r["grade"] == "medium"
      and near(r["dpms_va"], 4851) and r["missing"] == [])
# 770, 150 m² → High; only 1 IUG and 1 TUG: missing 1 IUG, 1 TUG and 3 general-use
rc, d = js("demand", "--area", "150", "--iug", "10", "--tug", "8")
r = d["result"]
check("demand 770: High with 2 circuits lists what is missing (exit 1)", rc == 1 and r["grade"] == "high" and len(r["missing"]) == 3
      and all(s == "fail" for s in st(d, "min_circuits")))
# 770 Superior: 2 IUG + 3 TUG = 5 general-use, the sixth is missing (free choice); with a dedicated one of 3000 VA it is complete
rc, d = js("demand", "--area", "220", "--iug", "10", "--iug", "10", "--tug", "8", "--tug", "8", "--tug", "8")
check("demand 770: Superior needs a sixth circuit", rc == 1 and any("sixth" in x for x in d["result"]["missing"]))
# with a TUE: sum = 2/3 × 60 × 20 + 3 × 2200 + 3300 = 800 + 6600 + 3300 = 10700 VA; × 0.6 = 6420 VA; + dedicated 3000 = 9420 VA → 42.82 A
rc, d = js("demand", "--area", "220", "--iug", "10", "--iug", "10", "--tug", "8", "--tug", "8", "--tug", "8", "--tue", "2", "--specific", "3000")
r = d["result"]
check("demand 770: Superior complete, 10700 × 0.6 = 6420 VA + 3000 VA dedicated = 9420 VA", rc == 0 and near(r["dpms_va"], 6420)
      and near(r["total_load_va"], 9420) and near(r["total_current_a"], 42.818))
check("demand: above 7 kVA / 32 A single-phase suggests three-phase", st(d, "supply") == ["warn"])
# 771 High needs a TUE
rc, d = js("demand", "--area", "160", "--iug", "8", "--iug", "8", "--tug", "6", "--tug", "6", "--norm", "771")
check("demand 771: High without a TUE is missing one", rc == 1 and any("TUE" in x for x in d["result"]["missing"]))
# 771 IUE: 0.66 × 500 × 2 = 660 VA
rc, d = js("demand", "--area", "50", "--iug", "4", "--tug", "5", "--iue", "2", "--norm", "771")
check("demand 771: IUE at 66 % of 500 VA per point (2 points = 660 VA)", any(c["type"] == "IUE" and near(c["va"], 660) for c in d["result"]["circuits"]))
rc, d = js("demand", "--area", "60", "--iug", "16", "--tug", "5")
check("demand: 16 points on one circuit fails (max 15)", rc == 1 and st(d, "points_per_circuit") == ["fail"])
rc, out = run("demand", "--area", "60", "--iug", "4", "--tug", "5", "--iue", "2")
check("demand: IUE under 770 refused with the way out", rc == 2 and "771" in out)
rc, out = run("demand", "--area", "60")
check("demand: no circuits refused with an example", rc == 2 and "--iug 8" in out)
rc, out = run("demand", "--area", "60", "--iug", "2,5", "--tug", "3")
check("demand: fractional points refused", rc == 2 and "whole number" in out)
rc, out = run("demand", "--iug", "4", "--tug", "3")
check("demand: missing area named", rc == 2 and "--area" in out)
rc, out = run("demand", "--area", "75", "--semi-covered", "10", "--iug", "8", "--tug", "10")
check("demand text: grade, DPMS and clause shown", "Medium" in out and "DPMS" in out and "770.8.1" in out)

# --- earth
# Ra 35 Ω, RCD 30 mA: 35 × 0.03 = 1.05 V ≤ 24 V; 35 ≤ 40 Ω → complies
rc, d = js("earth", "--ra", "35")
check("earth: 35 Ω with 30 mA = 1.05 V, complies", rc == 0 and near(d["result"]["touch_voltage_v"], 1.05) and d["result"]["complies"])
check("earth: default UL is 24 V (AEA)", d["result"]["ul_v"] == 24)
# Ra 50 Ω: 1.5 V ≤ 24 V but exceeds the 40 Ω permanent maximum
rc, d = js("earth", "--ra", "50")
check("earth: 50 Ω exceeds the 40 Ω maximum (exit 1)", rc == 1 and st(d, "ra_max") == ["fail"] and st(d, "ra_x_idn") == ["ok"])
# Ra 100 Ω with 300 mA: 30 V > 24 V
rc, d = js("earth", "--ra", "100", "--idn", "300")
check("earth: 100 Ω × 300 mA = 30 V > 24 V fails", rc == 1 and st(d, "ra_x_idn") == ["fail"])
# Ra 20 Ω with 1 A: 20 V ≤ 24 V; recommended = min(24 / (2 × 1); 40) = 12 Ω → warning
rc, d = js("earth", "--ra", "20", "--idn", "1000")
check("earth: 20 Ω with 1 A passes 24 V but warns above the 12 Ω recommended", rc == 0 and near(d["result"]["ra_recommended_ohm"], 12)
      and st(d, "ra_recommended") == ["warn"])
# reproduces column 3 of table 771.3.I: 300 mA → 40, 500 mA → 24, 3 A → 4
check("earth: recommended Ra reproduces table 771.3.I col. 3 (300 mA 40 Ω, 500 mA 24 Ω, 3 A 4 Ω)",
      all(near(js("earth", "--ra", "1", "--idn", str(i))[1]["result"]["ra_recommended_ohm"], v) for i, v in ((300, 40), (500, 24), (3000, 4))))
rc, d = js("earth", "--ra", "10", "--ul", "50")
check("earth: UL other than 24 V is allowed but warned", st(d, "ul") == ["warn"])
rc, out = run("earth")
check("earth: missing --ra named", rc == 2 and "--ra" in out)
rc, out = run("earth", "--ra", "0")
check("earth: zero resistance refused", rc == 2)

# --- tables
rc, out = run("tables")
check("tables: without a name, a short index of every table", rc == 0 and all(n in out for n in el.TABLES) and "data as of" not in out and len(out) < 4000)
rc, out = run("tables", "all")
check("tables all: prints every table with source and date", rc == 0 and all(n in out for n in el.TABLES) and out.count("data as of 2026-11-15") == len(el.TABLES))
check("tables: unverified tables are marked as such", "NOT VERIFIED" in out and "i2_fuse" in out)
rc, d = js("tables", "iz_b1")
check("tables: JSON of one table, keys as text", rc == 0 and d["tables"]["iz_b1"]["rows"]["2.5"] == [21, 18] and d["as_of"] == "2026-11-15")
rc, d = js("tables")
check("tables: full JSON parses and keeps the verification flag", d["tables"]["i2_fuse"]["verified"] is False and d["tables"]["f_temperature"]["verified"] is True
      and d["tables"]["earth"]["verified"] is True)
rc, out = run("tables", "prices")
check("tables: unknown table refused with the list", rc == 2 and "iz_b1" in out)
check("tables: every table names a source and a verification flag", all(t.get("source") and "verified" in t for t in el.TABLES.values()))
check("tables: Iz grows with section (no typo in 770.12.I)", all(a[0] < b[0] and a[1] < b[1] for a, b in zip(
    [el.TABLES["iz_b1"]["rows"][s] for s in el.SECTIONS], [el.TABLES["iz_b1"]["rows"][s] for s in el.SECTIONS][1:])))
check("tables: R falls with section (no typo in IEC 60228 values)", all(
    all(x > y for x, y in zip([t[s] for s in sorted(t)], [t[s] for s in sorted(t)][1:])) for t in el.TABLES["resistance"]["rows"].values()))

# --- review 2026-11-15: hand-solved cases asked for in the review
# apartment 220 V, 20 m line on 6 mm² at 25 A: R70 = 3.30 × 1.196464 = 3.94833; ΔU = 2 × 25 × 0.020 × 3.94833 × 0.85 = 3.3561 V → 1.5255 %
rc, d = js("drop", "--current", "25", "--length", "20", "--section", "6", "--line", "main")
check("review: main line 20 m 6 mm² 25 A = 3.36 V / 1.53 %, limit unknown", near(d["result"]["drop_v"], 3.356) and near(d["result"]["drop_pct"], 1.5255)
      and st(d, "drop_main") == ["unknown"])
# the same as a submain (meter panel → apartment) passes the 1 %: 10 mm² → 2 × 25 × 0.020 × 1.91 × 1.196464 × 0.85 = 1.9424 V = 0.883 %
rc, d = js("size", "--current", "25", "--length", "20", "--circuit", "submain")
r = d["result"]
check("review: submain 25 A 20 m → 10 mm² by drop (0.88 %), MCB 25 A, up to 50 A", r["section_mm2"] == 10 and near(r["drop_pct"], 0.883)
      and r["mcb_a"] == 25 and r["mcb_max_a"] == 50 and "drop" in r["governed_by"])
# TUG 25 m 2.5 mm² 16 A: ΔU = 2 × 16 × 0.025 × 9.54778 × 0.85 = 6.4925 V → 2.951 % ≤ 3 % (just)
rc, d = js("drop", "--current", "16", "--length", "25", "--section", "2,5")
check("review: TUG 25 m 2.5 mm² 16 A = 6.49 V / 2.95 %, ok by a hair", rc == 0 and near(d["result"]["drop_v"], 6.4925) and near(d["result"]["drop_pct"], 2.951))
# 3500 W electrical air conditioner: I = 3500 / (220 × 0.85) = 18.717 A
rc, d = js("current", "--power", "3500")
check("review: 3500 W air conditioner = 18.72 A", near(d["result"]["current_a"], 18.717))
# on a 10 m TUE: 2.5 mm², Iz 21, MCB 20 (18.72 ≤ 20 ≤ 21); drop 2 × 18.717 × 0.010 × 9.54778 × 0.85 = 3.0380 V = 1.381 %
rc, d = js("size", "--current", "18,717", "--length", "10", "--circuit", "tue")
check("review: 18.72 A on a TUE → 2.5 mm², MCB 20 A, 1.38 %, no unit-load warning (TUE takes up to 20 A)", rc == 0 and d["result"]["section_mm2"] == 2.5
      and d["result"]["mcb_a"] == 20 and near(d["result"]["drop_pct"], 1.381) and st(d, "unit_load") == [])
check("review: TUE with MCB 20 A raises no 20 A-socket warning", st(d, "tue_sockets") == [])
# consistency 2026-11-15: a 24 A TUE gives 4 mm² + MCB 25 A by Iz, but its sockets are 20 A → warning (ELEC-AMP-19, ELEC-CIR-5)
rc, d = js("size", "--current", "24", "--length", "15", "--circuit", "tue")
check("consistency: TUE needing MCB 25 A warns that its 20 A sockets cap the breaker at 20 A (ELEC-AMP-19)",
      rc == 0 and d["result"]["mcb_a"] == 25 and st(d, "tue_sockets") == ["warn"]
      and "dedicated circuit (ACU)" in [x["evidence"] for x in d["findings"] if x["check"] == "unit_load"][0]
      and "a TUE or" not in [x["evidence"] for x in d["findings"] if x["check"] == "unit_load"][0])

# --- review 2026-11-15: one test per bug fixed
# bug: "3.500" (thousands in Argentina) was read as 3.5 W
rc, out = run("current", "--power", "3.500")
check("bug: '3.500' is ambiguous (Argentine thousands) and refused, not read as 3.5", rc == 2 and "ambiguous" in out and "3500" in out)
rc, d = js("current", "--power", "3.500,5", "--va")
check("bug: '3.500,5' reads as 3500.5", near(d["result"]["power_va"], 3500.5))
rc, d = js("current", "--power", "1.250.000", "--va")
check("bug: '1.250.000' (two groups) is thousands", near(d["result"]["power_va"], 1250000))
rc, d = js("current", "--pf", "0.850", "--power", "1000")
check("bug: '0.850' (leading zero) is still a decimal", rc == 0 and d["result"]["pf"] == 0.85)
# bug: 1e308 gave Infinity in the JSON (invalid JSON)
rc, out = run("drop", "--current", "1e308", "--length", "1e308", "--section", "2.5", "--json")
check("bug: absurd magnitudes refused (no Infinity in JSON)", rc == 2 and "Infinity" not in out and "out of range" in json.loads(out)["error"])
# bug: --conductors 2.9 was silently truncated to 2
rc, out = run("size", "--current", "10", "--length", "10", "--circuit", "tug", "--conductors", "2,9")
check("bug: fractional --conductors refused, not truncated", rc == 2 and "whole number" in out)
rc, out = run("coordinate", "--ib", "10", "--in", "16", "--section", "2.5", "--conductors", "2.5")
check("bug: fractional --conductors refused in coordinate too", rc == 2 and "whole number" in out)
# bug: three-phase with the 2x column gave a higher Iz than the real one
rc, out = run("size", "--current", "10", "--length", "10", "--circuit", "submain", "--system", "three", "--conductors", "2")
check("bug: three-phase with 2 loaded conductors refused (would overstate Iz)", rc == 2 and "does not match" in out)
rc, out = run("size", "--current", "10", "--length", "10", "--circuit", "mbtf", "--system", "three")
check("bug: MBTF three-phase refused like IUG/TUG/TUE", rc == 2 and "single-phase" in out)
# bug: an --upstream-drop that used up the limit gave "fits no section"
rc, d = js("size", "--current", "10", "--length", "10", "--circuit", "tug", "--upstream-drop", "3")
check("bug: upstream drop that uses up the limit is named as such", rc == 1 and st(d, "upstream_drop") == ["fail"] and st(d, "section") == [])
# bug: --upstream-drop on submain/main was silently ignored
rc, out = run("drop", "--current", "10", "--length", "10", "--section", "2.5", "--line", "submain", "--upstream-drop", "0,5")
check("bug: --upstream-drop on a submain is refused instead of silently ignored", rc == 2 and "--upstream-drop" in out)
rc, out = run("size", "--current", "10", "--length", "10", "--circuit", "main", "--upstream-drop", "0,5")
check("bug: --upstream-drop on a main line is refused in size too", rc == 2 and "--upstream-drop" in out)
# bug: --va with --current was ignored
rc, out = run("current", "--current", "10", "--va")
check("bug: --va with --current refused", rc == 2 and "--va" in out)
# bug: reactance 0 marked ok up to 35 mm², but table 770.15.IV gives ~7 % more at 25 and ~13 % at 35
rc, d = js("drop", "--current", "80", "--length", "30", "--section", "25")
check("bug: X = 0 on 25 mm² is a warning, not ok", st(d, "reactance") == ["warn"])
rc, d = js("drop", "--current", "10", "--length", "20", "--section", "16")
check("bug: X = 0 on 16 mm² still ok", st(d, "reactance") == ["ok"])
# AEA quick table (cos 0.8) is reproduced with X ≈ 0.1 Ω/km: 35 mm² → 2 × (0.554 × 1.196464 × 0.8 + 0.1 × 0.6) = 1.180 ≈ 1.2 V/(A·km)
check("bug: AEA quick table 35 mm² ≈ 1.2 V/A·km needs the reactance term", abs(2 * (0.554 * R70_CU * 0.8 + 0.1 * 0.6) - 1.2) < 0.05
      and abs(2 * 0.554 * R70_CU * 0.8 - 1.2) > 0.1)
# size takes --reactance: 80 A, 30 m, submain: X 0 → 50 mm² 0.86 %; X 0.1 → 2 × 80 × 0.03 × (0.386 × 1.196464 × 0.85 + 0.1 × 0.52678) / 220 = 0.967 %
rc, d = js("size", "--current", "80", "--length", "30", "--circuit", "submain", "--reactance", "0,1")
check("bug: size takes --reactance into the drop (50 mm², 0.97 %)", d["result"]["section_mm2"] == 50 and near(d["result"]["drop_pct"], 0.967)
      and st(d, "reactance") == [])
rc, d = js("size", "--current", "80", "--length", "30", "--circuit", "submain")
check("bug: size warns when X = 0 governs a 25 mm²+ choice", st(d, "reactance") == ["warn"])
# bug: a single 18.7 A load (air conditioner) on a TUG came out all ok; the TUG is for loads up to 10 A
rc, d = js("size", "--current", "18,72", "--length", "10", "--circuit", "tug")
check("bug: 18.7 A on a TUG warns about the 10 A unit-load limit", st(d, "unit_load") == ["warn"])
# bug: 771 TUE and IUE have a maximum of 12 points, not 15
rc, d = js("demand", "--area", "75", "--iug", "8", "--tug", "5", "--tue", "13", "--norm", "771")
check("bug: 771 TUE with 13 points fails (max 12)", rc == 1 and st(d, "points_per_circuit") == ["fail"])
rc, d = js("demand", "--area", "75", "--iug", "8", "--tug", "5", "--tue", "13")
check("bug: 770 TUE with 13 points is fine (770.6.I allows 15)", st(d, "points_per_circuit") == [])
# bug/interpretation: 771 grade with the DPMS after the coefficient (771.8.1.5, as guide ELEC-CIR-3).
# 75 m² (Medium), IUG 8 = 792 + 3 TUG = 6600 → 7392 VA × 0.9 = 6652.8 VA ≤ 7 kVA → Medium; the sum alone (7392) would give High → warning
rc, d = js("demand", "--area", "75", "--iug", "8", "--tug", "5", "--tug", "5", "--tug", "5", "--norm", "771")
check("bug: 771 grade uses DPMS after the coefficient (6652.8 VA → Medium) and warns the stricter reading", d["result"]["grade"] == "medium"
      and near(d["result"]["dpms_va"], 6652.8) and st(d, "conservative_grade") == ["warn"])
# guide Example B: 98 m², 9185 VA → Medium 8266.5 > 7000 → High 7348 VA (no warning: both readings give High)
rc, d = js("demand", "--area", "98", "--iug", "8", "--iug", "7", "--tug", "9", "--tug", "14", "--tue", "2", "--norm", "771")
check("bug: guide example B (98 m², 9185 VA) → High, 7348 VA", d["result"]["grade"] == "high" and near(d["result"]["dpms_va"], 7348)
      and st(d, "conservative_grade") == [])
# bug: the default --norm 770 on an apartment gives 60 VA per point; it is warned when the norm was not chosen
rc, d = js("demand", "--area", "75", "--iug", "8", "--tug", "5", "--tug", "5")
check("bug: default 770 warns it is only for single-family houses", st(d, "applicable_norm") == ["warn"])
rc, d = js("demand", "--area", "75", "--iug", "8", "--tug", "5", "--tug", "5", "--norm", "770")
check("bug: explicit --norm 770 is not warned", st(d, "applicable_norm") == ["ok"])
check("edition notice: every answer says 770 Ed. 2026 is about to come out", "2026" in d.get("edition_notice", "") and "Ed. 2026" in run("earth", "--ra", "10")[1])

# --- frictions from the final evaluation (2026-11-15)
rc, out = run("size", "--help")
check("help: 'size --help' prints that subcommand's usage, exit 0", rc == 0 and "electricidad size" in out and "--layout" in out and "current --power" not in out)
rc, out = run("coordinate", "help")
check("help: 'coordinate help' works too", rc == 0 and "electricidad coordinate" in out)
rc, d = js("current", "--power", "1600", "--pf", "0,9")
check("current: the source names the cos φ actually used", "0.9 (user value)" in d["source"] and "0.85" not in d["source"])
rc, d = js("current", "--power", "1600")
check("current: default cos φ 0.85 cited as 770.15.6", "0.85 by 770.15.6" in d["source"])
rc, d = js("size", "--current", "8", "--length", "18", "--circuit", "specific")
check("size: a dedicated circuit also gets the 30 mA RCD finding", st(d, "rcd") == ["ok"])
check("size: a dedicated circuit warns that the starting current may ask for a bigger breaker", st(d, "starting_current") == ["ok"]
      and d["result"]["mcb_a"] == 10 and d["result"]["mcb_max_a"] == 20)
rc, d = js("size", "--current", "8", "--length", "18", "--circuit", "iug")
check("size: a lighting circuit gets no starting-current note", st(d, "starting_current") == [])
rc, d = js("size", "--current", "20,43", "--length", "20", "--circuit", "submain", "--grouped", "8")
check("size: grouped output does not say all circuits share one conduit", "in the conduit" not in " ".join(d["lines"]) and st(d, "grouping") == ["ok"])
# 16 mm² 2x = 66 A; single layer, 8 circuits: 0.71 → 46.86 A (IEC B.52.17 item 2, ❔); bunched 0.52 → 34.32 A
rc, d = js("coordinate", "--ib", "32", "--in", "32", "--section", "16", "--grouped", "8", "--layout", "layer")
check("coordinate: single layer of 8 conduits uses 0.71 and is marked unverified", near(d["result"]["iz_a"], 46.86) and "unknown" in st(d, "unverified_data"))
rc, d = js("coordinate", "--ib", "32", "--in", "32", "--section", "16", "--grouped", "8")
check("coordinate: bunched 8 conduits stay at 0.52", near(d["result"]["iz_a"], 34.32))
rc, out = run("coordinate", "--in", "32", "--section", "16", "--layout", "layer")
check("coordinate: --layout layer without --grouped is refused", rc == 2)
rc, d = js("coordinate", "--in", "25", "--section", "2,5")
check("coordinate: without --ib it still checks In ≤ Iz (25 on 2.5 fails) and marks Ib ❔", rc == 1 and st(d, "in_le_iz") == ["fail"]
      and st(d, "ib_le_in") == ["unknown"])
rc, d = js("coordinate", "--ib", "10", "--in", "13", "--iz", "21")
check("coordinate: 13 A is an IEC preferred rating (ok, with a market note), not a warning", st(d, "standard_rating") == ["ok"])
rc, d = js("size", "--current", "20", "--length", "20", "--circuit", "submain", "--norm", "771")
check("size --norm 771 cites the 771 tables and says the 1 % is mandatory", "771.16.I" in d["source"] and st(d, "norm") == ["ok"])
check("dpms_771 title no longer says the 771 is only beyond the 770", "over 63 A" not in el.TABLES["dpms_771"]["title"])
# building: 8 × 4495 VA, medium, 0.8 → 28 768 VA + CS 7000 three-phase + 1500 single-phase = 37 268 VA; 37 268 / (√3 × 380) = 56.62 A
# split 3/3/2: phase of 3 with coef. 0.9 (2 to 4 units) = 12 136.5 + 2333.3 = 14 469.8 VA → 65.77 A; single-phase CS on the phase of 2
rc, d = js("building", "--units", "8", "--dpms", "4495", "--grade", "medium", "--common-3ph", "7000", "--common-1ph", "1500")
r = d["result"]
check("building: 8 flats + services = 37 268 VA, 56.6 A balanced", near(r["total_va"], 37268, 1) and near(r["balanced_current_a"], 56.62))
check("building: 3/3/2 split, heaviest phase with the 3-unit coefficient (65.8 A)", [r["phases"][k]["units"] for k in ("L1", "L2", "L3")] == [3, 3, 2]
      and near(r["phases"]["L1"]["current_a"], 65.77) and r["phases"]["L1"]["coefficient"] == 0.9)
check("building: single-phase services go to the light phase", near(r["phases"]["L3"]["va"], 2 * 4495 * 0.9 + 7000 / 3 + 1500, 1))
check("building: the 771.9.III coefficient is flagged as not the current 772 table", st(d, "coefficient") == ["unknown"])
rc, d = js("building", "--units", "8", "--dpms", "7495", "--grade", "medium", "--common-3ph", "7000", "--common-1ph", "1500")
check("building: near 60 kVA warns about the transformer room; units over 7 kVA warned", st(d, "transformer_room") == ["warn"]
      and st(d, "unit_supply") == ["warn"])
rc, d = js("building", "--units", "8", "--dpms", "7000", "--coef", "1")
check("building: --coef from the 772 table or the utility is used as given", d["result"]["coefficient"] == 1 and st(d, "coefficient") == ["ok"])
rc, out = run("building", "--units", "8")
check("building: --units without --dpms refused", rc == 2)
rc, out = run("rule", "ELEC-EQU-36")
check("rule: prints only that rule and stops at the next heading (last rule of a document)", rc == 0 and "### ELEC-EQU-36:" in out
      and not any(l.startswith("## ") for l in out.split("\n")) and out.count("### ELEC-") == 1)
rc, out = run("rule", "ELEC-PRO-7")
check("rule: ELEC-PRO-7 does not pull ELEC-PRO-70 or others", rc == 0 and out.count("### ELEC-") == 1 and "### ELEC-PRO-7:" in out)
rc, out = run("rule", "ELEC-ZZZ-1")
check("rule: unknown ID says so, exit 1", rc == 1 and "not in the guide" in out)
rc, out = run("search", "PUENTEAR", "disyuntor")
check("search: a Spanish word goes through GLOSSARY.md; ignores case and accents; finds the bypass rule with all words", rc == 0 and "ELEC-DIA-34" in out and "no rule has all" not in out)
rc, out = run("search", "bypass", "RCD")
check("search: English words find the same rule", rc == 0 and "ELEC-DIA-34" in out and "no rule has all" not in out)
rc, out = run("search", "jabalina")
check("search: 'jabalina' finds the earth-rod rules", rc == 0 and "ELEC-PAT-" in out)

# --- every JSON answer of a calculation carries a source, the legend and findings with the four fields
docs = [js("current", "--power", "1000")[1], js("drop", "--current", "5", "--length", "5", "--section", "1.5")[1],
        js("size", "--current", "5", "--length", "5", "--circuit", "iug")[1], js("coordinate", "--ib", "5", "--in", "6", "--iz", "15")[1],
        js("demand", "--area", "40", "--iug", "4", "--tug", "4")[1], js("earth", "--ra", "10")[1]]
check("json: every calculation has source, legend, as_of", all(x.get("source") and x["legend"] == el.LEGEND and x["as_of"] == el.AS_OF for x in docs))
check("json: findings always carry check, rule, status, evidence", all(set(f) == {"check", "rule", "status", "evidence"} and f["status"] in el.ORDER
                                                                     for x in docs for f in x["findings"]))

# --- `electricidad plan ...` is handed whole to electricidad_plan.py (the repo copy here; /usr/local/bin/electricidad-plan in the image)
import subprocess as _sp
_r = _sp.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "electricidad.py"), "plan", "symbols", "--json"],
             capture_output=True, text=True)
check("plan: delegated to electricidad-plan (symbols answers JSON)", _r.returncode == 0 and _r.stdout.strip().startswith(("{", "[")))

print("\n".join(fails) or "electricidad_selftest: all ok")
sys.exit(1 if fails else 0)
