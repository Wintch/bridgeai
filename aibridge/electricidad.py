#!/usr/bin/env python3
"""electricidad: offline electrical-work calculations for Argentina (guide in aibridge/electricidad/, README.md). Indicative, not a design.

  electricidad current --power W [--va] [--pf 0.85] [--system single|three] [--voltage V] [--json]
  electricidad current --current A [--pf 0.85] [--system single|three] [--voltage V] [--json]      the reverse: from current to power
  electricidad drop --current A --length M --section MM2 [--material cu|al] [--class 5|2] [--system single|three] [--pf 0.85]
                     [--reactance OHM_KM] [--line final|submain|motor|main] [--upstream-drop PCT] [--json]
  electricidad size --current A --length M --circuit iug|iugt|tug|tue|specific|motor|submain|main [--conductors 2|3]
                     [--temp C] [--grouped N] [--layout bunched|layer] [--max-drop PCT] [--upstream-drop PCT] [--reactance OHM_KM]
                     [--class 5|2] [--system single|three] [--pf 0.85] [--norm 770|771] [--json]
  electricidad coordinate [--ib A] --in A (--iz A | --section MM2 [--conductors 2|3] [--temp C] [--grouped N] [--layout bunched|layer])
                     [--device mcb|fuse] [--norm 770|771] [--json]
                     without --ib (load unknown) it checks only In ≤ Iz and I2 ≤ 1.45 Iz: "can I put a 25 A breaker on this cable?"
  electricidad demand --area M2 [--semi-covered M2] --iug POINTS [--iug POINTS ...] --tug POINTS [...] [--iugt POINTS] [--tue POINTS]
                     [--iue POINTS] [--specific VA ...] [--norm 770|771] [--system single|three] [--json]
                     770 = single-family house; an apartment in a building, an office or a shop takes --norm 771
  electricidad building --units N --dpms VA [--units N --dpms VA ...] [--grade minimum|medium|high|superior] [--common-3ph VA]
                     [--common-1ph VA] [--coef X] [--json]
                     demand of a building: single-phase units × diversity factor + common services, split per phase
                     (3/3/2...) and current of the most loaded phase. Each unit's DPMS comes first from "demand --norm 771".
  electricidad earth --ra OHM [--idn MA] [--ul V] [--json]
  electricidad tables [NAME | all] [--json]           without a name, the list; with a name, that table with its source and date, to cite it
  electricidad rule ELEC-PRO-7 [ELEC-REV-21 ...]      prints only that rule (or those) from the guide (up to the next heading)
  electricidad search WORD [WORD ...]                 searches the RULES.md index (in English; a Spanish word is
                                                      translated through GLOSSARY.md; accents and case do not matter)
  electricidad plan new|validate|draw|single-line|sheets|dxf|status|summary|symbols ...
                                                      job survey and drawings: done by electricidad-plan (electricidad_plan.py)

Help for one subcommand: electricidad size --help (or "help"). Options that often confuse:
  --grouped N      number of grouped circuits: in the same conduit, or separate conduits touching each other (riser). 1 = alone.
  --layout         bunched (default: together, embedded or enclosed) | layer (conduits in a single layer on the wall or a plain tray).
  --temp C         air temperature around the conduit in °C (40 by default; attic under a metal roof 50 or more).
  --conductors     loaded conductors: 2 single-phase, 3 three-phase (the PE does not count).
  --norm 771       apartment, office or shop: changes the citation (771 tables) and on the sub-main the 1 % becomes mandatory.
Each repeated option (--iug 8 --iug 6) is one circuit with that number of points. Decimals take a comma or a dot (0,85 = 0.85).
Every result carries findings with the same fields: check, rule (clause), status (ok | warn | fail | unknown) and evidence. `unknown` marks a
value that could not be confirmed in a primary source and is never shown as ok. Exit: 0 everything complies, 1 something does not comply,
2 invalid input.
Called as `gateway electricidad ...` (gateway.py passes the arguments through) or /usr/local/bin/electricidad.
Basis: AEA 90364-7-770 Ed. 2017 (single-family dwellings up to 63 A, in force since 2017-09-01) and AEA 90364-7-771 Ed. 2006 (everything
else: apartments in buildings, offices, shops). AEA already sells the 770 Ed. 2026 in digital form (print in presale, delivery from
2026-11-16) and has not published an effective date: until that text is read, its values may differ from the ones here.
Numbers: input takes a decimal comma (2,5) or a decimal point (2.5), but "3.500" is ambiguous (in Argentina it is three thousand five
hundred) and is refused: write 3500 or 3,5. "3.500,5" reads as 3500.5. Output uses a decimal point.
AEA standards are paid: this carries loose values with their clause, not the full tables.
"""
import json, math, re, sys

AS_OF = "2026-11-15"
LEGEND = "indicative only: the design calculation is signed by a licensed professional"
A770 = "AEA 90364-7-770 Ed. 2017"
A771 = "AEA 90364-7-771 Ed. 2006"
STATUS_MARK = {"ok": "✅", "warn": "⚠️", "fail": "❌", "unknown": "❔"}
ORDER = {"fail": 0, "warn": 1, "unknown": 2, "ok": 3}
SQ3 = math.sqrt(3)
NUM_MAX = 1e7                                       # sanity cap for any input (keeps inf/NaN out of the JSON output)
EDITION_NOTICE = ("AEA 90364-7-770 Ed. 2026 already on sale in digital form (print in presale, delivery announced from 2026-11-16) with no "
                  "published effective date: the values here are from Ed. 2017 + Corrigendum 1 (2018); say that they may have changed")

# ---------------------------------------------------------------- tables (source and verification in each one)
# Primary sources read on 2026-11-15:
#  - AEA 90364-7-770 Ed. 2017, text published by the Municipality of Junín (junin.gob.ar/.../reglamento_aea.pdf) and by ERSeP Córdoba.
#  - AEA 90364-7-771 Ed. 2006, text published at ele.chaco.gob.ar (virtual classroom of the Chaco government).
#  - IEC 60228 (conductor resistances), values reproduced by manufacturers (e.g. Bayka, "conductor resistance" data sheet).
# No edition of the 771 later than 2006 was found. For the 770, the AEA catalogue (checked 2026-11-15, see regulations-and-permits.md)
# lists Ed. 2026 (digital on sale; print in presale with delivery from 2026-11-16): until that text is read, this
# calculator stays with Ed. 2017.

TABLES = {
    "voltage": {
        "title": "Nominal voltages of the public LV network",
        "source": f"{A770}, 770.4.2 b)", "verified": True,
        "note": "220 V phase to neutral (single-phase), 380 V between phases (three-phase), 50 Hz. The standard mentions 230/400 V in parentheses.",
        "rows": {"single": 220.0, "three": 380.0},
    },
    "resistance": {
        "title": "Maximum conductor resistance at 20 °C [Ω/km]",
        "source": "IEC 60228:2004 tables 2 (class 2) and 3 (class 5), plain (untinned) conductors; temperature correction per IEC 60228 annex B",
        "verified": True,
        "note": ("Class 5 = flexible cable (the usual IRAM NM 247-3 single-core); class 2 = rigid stranded. For the drop R is taken to 70 °C, the "
                 "maximum operating temperature of PVC (770.12.1 a): it is the worst case, with the cable at full load. With X = 0 it gives 2.5 mm² = "
                 "15.3 V/(A·km) at cos φ 0.8, like table 770.15.IV (15); the whole table (26 / 15 / 10 / 6.5 / 3.8 / 2.4 / 1.6 / 1.2 from 1.5 to "
                 "35 mm², per conductors-and-conduits.md) is reproduced by adding X ≈ 0.1 Ω/km: so the table includes reactance and "
                 "with X = 0 the drop comes out ~7 % low at 25 mm² and ~13 % at 35 mm² (hence the warning from 25 mm²). Copper: R70 = R20 × (234.5+70)/254.5 = R20 × 1.1965. Aluminium: R70 = R20 × (228+70)/248 = R20 × 1.2016. "
                 "The 1 mm² values were not cross-checked with a second source."),
        "rows": {
            "cu5": {1.0: 19.5, 1.5: 13.3, 2.5: 7.98, 4: 4.95, 6: 3.30, 10: 1.91, 16: 1.21, 25: 0.780, 35: 0.554, 50: 0.386, 70: 0.272,
                    95: 0.206, 120: 0.161, 150: 0.129, 185: 0.106, 240: 0.0801, 300: 0.0641},
            "cu2": {1.0: 18.1, 1.5: 12.1, 2.5: 7.41, 4: 4.61, 6: 3.08, 10: 1.83, 16: 1.15, 25: 0.727, 35: 0.524, 50: 0.387, 70: 0.268,
                    95: 0.193, 120: 0.153, 150: 0.124, 185: 0.0991, 240: 0.0754, 300: 0.0601},
            "al2": {10: 3.08, 16: 1.91, 25: 1.20, 35: 0.868, 50: 0.641, 70: 0.443, 95: 0.320, 120: 0.253, 150: 0.206, 185: 0.164,
                    240: 0.125, 300: 0.100},
        },
    },
    "drop_limits": {
        "title": "Maximum voltage drop [%]",
        "source": f"{A770}, 770.15.6; {A771}, 771.13 b)", "verified": True,
        "note": ("Measured from the output terminals of the main panel to any point of use. The 770 recommends ≤ 1 % on the "
                 "sub-main; the 771 requires it (and leaves 2 % for a final circuit leaving a sub-panel, 4 % if it feeds motors). "
                 "Motor starting: 15 %. The main line (meter → main panel) is governed by AEA 95150 and the utility: "
                 "the value was not found in a primary source, so it has no limit here."),
        "rows": {
            "final": {"max": 3.0, "rule": "770.15.6 1. / 771.13 b) 1.", "verified": True, "desc": "total up to the point of use (lighting and sockets)"},
            "motor": {"max": 5.0, "rule": "770.15.6 2. / 771.13 b) 2.", "verified": True, "desc": "circuits feeding only motors, in steady state"},
            "submain": {"max": 1.0, "rule": "770.15.6 note (recommendation) / 771.13 b) note (requirement)", "verified": True, "desc": "partial, of the sub-main circuit"},
            "main": {"max": None, "rule": "770.4.1.1 → AEA 95150", "verified": False, "desc": "meter → main panel: set by AEA 95150 / the utility"},
        },
    },
    "iz_b1": {
        "title": "Current-carrying capacity [A], IRAM NM 247-3 / IRAM 62267 copper cables in conduit (embedded or surface), method B1, air at 40 °C",
        "source": f"{A770}, table 770.12.I (see also {A771}, table 771.16.I)", "verified": True,
        "note": ("2x = 2 loaded conductors + PE (single-phase); 3x = 3 loaded + N + PE (three-phase). Reference temperature 40 °C "
                 "(770.12.2.1.2). For sheathed cables IRAM 2178 / 62266 buried or in duct use table 770.12.III, not this one."),
        "rows": {1.0: (11, 10), 1.5: (15, 14), 2.5: (21, 18), 4: (28, 25), 6: (36, 32), 10: (50, 44), 16: (66, 59), 25: (88, 77),
                 35: (109, 96), 50: (131, 117), 70: (167, 149), 95: (202, 180), 120: (234, 208), 150: (261, 228), 185: (297, 258),
                 240: (348, 301), 300: (398, 343)},
    },
    "f_grouping": {
        "title": "Factor for grouping of circuits in one wiring system",
        "source": (f"{A770}, table 770.12.II (1 to 3 circuits); 4, 5, 6 and 8: {A771}, table 771.16.IV item 1; 7, 9 and more: "
                   "IEC 60364-5-52 table B.52.17 item 1"), "verified": True,
        "note": ("770.12.II only gives 2 and 3 circuits and says it is based on table B52-17 item 1 of AEA 90364-5-52. 4, 5, 6 and 8 circuits: "
                 "table 771.16.IV item 1 (bunched, embedded or enclosed), as in conductors-and-conduits.md. The values "
                 "for 7, 9, 12, 16 and 20 circuits come from IEC 60364-5-52 and were not checked against the AEA text."),
        "rows": {1: (1.00, True), 2: (0.80, True), 3: (0.70, True), 4: (0.65, True), 5: (0.60, True), 6: (0.57, True), 7: (0.54, False),
                 8: (0.52, True), 9: (0.50, False), 12: (0.45, False), 16: (0.41, False), 20: (0.38, False)},
    },
    "f_grouping_layer": {
        "title": "Factor for grouping of circuits in a single layer (conduits or cables side by side on a wall, floor or unperforated tray)",
        "source": "IEC 60364-5-52 table B.52.17 item 2 (= AEA 90364-5-52); the 771.16.IV has the same item, not checked", "verified": False,
        "note": ("For separate conduits running in one layer on the shaft wall (ELEC-CON-23 uses 0.71 for 8). From 9 circuits there is no "
                 "further reduction. If the conduits run bunched or embedded together, use the f_grouping table (default). "
                 "IEC values, not reread in the AEA text: they come out as ❔."),
        "rows": {1: 1.00, 2: 0.85, 3: 0.79, 4: 0.75, 5: 0.73, 6: 0.72, 7: 0.72, 8: 0.71, 9: 0.70, 20: 0.70},
    },
    "f_temperature": {
        "title": "Factor for ambient temperature other than 40 °C (PVC, 70 °C)",
        "source": f"{A771}, table 771.16.II.a (base 40 °C, based on B52-14); the 770 refers to AEA 90364-5-52 annex B (770.12.2.1.3)",
        "verified": True,
        "note": ("Values of table 771.16.II.a from 20 to 60 °C (the same as conductors-and-conduits.md and "
                 "current-ratings-and-devices.md). A temperature not in the table takes the next row up (stricter); "
                 "below 20 °C the 20 °C factor (1.29) is used, with no credit for the cold. The formula √((70 − θ) / 30) gives almost "
                 "the same but is optimistic at 55 and 60 °C (0.71 and 0.58), so the table is used. Accepted range 10 °C to 60 °C."),
        "rows": {20: 1.29, 25: 1.22, 30: 1.15, 35: 1.08, 40: 1.00, 45: 0.91, 50: 0.82, 55: 0.70, 60: 0.57},
    },
    "min_section": {
        "title": "Minimum cross-section [mm²] by line or circuit type",
        "source": f"{A770}, table 770.11.I; {A771}, table 771.13.I", "verified": True,
        "note": ("Equal in 770 and 771 except the feed and return of switches (1 mm² in 770, 1.5 mm² in 771). The protective "
                 "conductor PE never below 2.5 mm² (770.14.4.5) and the earthing conductor never below 4 mm² (770.14.4.4)."),
        "rows": {"main": 4.0, "submain": 2.5, "iug": 1.5, "iugt": 2.5, "tug": 2.5, "tue": 2.5, "specific": 2.5, "motor": 2.5,
                 "mbtf": 1.5, "pe": 2.5, "earthing": 4.0},
    },
    "circuits": {
        "title": "Final circuit types: maximum protection and points",
        "source": f"{A770}, 770.6.6 and table 770.6.I", "verified": True,
        "note": ("IUG: loads up to 10 A, 2P+E 10 A IRAM 2071 sockets. TUG: loads up to 10 A. TUE: loads up to 20 A (2P+E 20 A socket) "
                 "or 16 A IEC 60309. Protection on both poles. Dedicated circuits are set by the designer per the 771."),
        "rows": {"iug": {"in_max": 16, "points_max": 15}, "iugt": {"in_max": 16, "points_max": 15}, "tug": {"in_max": 20, "points_max": 15},
                 "tue": {"in_max": 32, "points_max": 15}},
    },
    "points_771": {
        "title": "Maximum points per circuit under the 771 (apartments, offices, shops)",
        "source": f"{A771}, 771.7.6 and table 771.7.I", "verified": False,
        "note": ("IUG and TUG 15 points; IUE and TUE 12 points (in the 770, table 770.6.I, the TUE goes up to 15). Taken from grades-and-circuits.md "
                 "(ELEC-CIR-5), which cites table 771.7.I; not reread in the source in this review. It is the strictest value, so "
                 "going over it comes out as a non-compliance."),
        "rows": {"iug": 15, "iugt": 15, "tug": 15, "iue": 12, "tue": 12},
    },
    "mcb": {
        "title": "Usual rated currents of MCBs (PIA, miniature circuit breaker) [A]",
        "source": "IEC 60898-1, 5.3.2 (preferred values); I2 = 1.45 In (conventional tripping current, IEC 60898-1 table 7)",
        "verified": True,
        "note": ("The IEC 60898-1 preferred series also includes 8, 13, 80, 100 and 125 A; on the Argentine market this one is the usual. "
                 "With IEC 60898-1 MCBs, if In ≤ Iz then I2 ≤ 1.45 Iz holds too (770, annex 770-B, table 770-B.I)."),
        "rows": [6, 10, 16, 20, 25, 32, 40, 50, 63],
        "iec_series": [6, 8, 10, 13, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125],
    },
    "i2_fuse": {
        "title": "Conventional fusing current I2 of gG fuses (multiple of In)",
        "source": "IEC 60269-1 table 2", "verified": False,
        "note": "Not verified in a primary source in this review: 2.1 In (In ≤ 4 A), 1.9 In (4 < In < 16 A), 1.6 In (In ≥ 16 A).",
        "rows": {"up_to_4": 2.1, "4_to_16": 1.9, "from_16": 1.6},
    },
    "dpms_770": {
        "title": "DPMS per circuit and coefficients, single-family dwellings up to 63 A",
        "source": f"{A770}, tables 770.7.I, 770.7.II, 770.8.I and 770.8.II", "verified": True,
        "note": ("Area = covered + 50 % of the semi-covered; the grade comes from the area alone. IUG without sockets: 2/3 of 60 VA per point; "
                 "IUG with branch sockets: 2200 VA; TUG: 2200 VA; TUE: 3300 VA (minimums: if the real load is higher, the real one applies). "
                 "Coefficient 'by the minimum number of circuits': this calculator takes it from the grade (2, 3, 5, 6 minimum circuits); "
                 "reading it by the real number of circuits would give an equal or lower value."),
        "rows": {"va_per_point_iug": 60, "frac_iug": 2 / 3, "va_iugt": 2200, "va_tug": 2200, "va_tue": 3300,
                 "grades": [("minimum", 60, None, 1.0), ("medium", 130, None, 0.8), ("high", 200, None, 0.7), ("superior", None, None, 0.6)]},
    },
    "dpms_771": {
        "title": "DPMS per circuit and coefficients under the 771: apartments in buildings, offices, shops (and houses outside the scope of the 770)",
        "source": f"{A771}, tables 771.8.I, 771.8.II, 771.9.I and 771.9.II", "verified": True,
        "note": ("The grade comes from the area and from the DPMS: if the DPMS (with the coefficient of the grade being tried) exceeds "
                 "the cap of the grade, move to the next one and repeat (771.8.1.5 steps a-d, as grades-and-circuits.md ELEC-CIR-3 explains); "
                 "once moved up it does not go back down even if the new coefficient leaves the DPMS below the previous cap (771.9.1, "
                 "last paragraph). If comparing the sum before the coefficient would give a higher grade, the output warns it as the "
                 "conservative reading. IUG without sockets: 66 % of 150 VA per point (100 % in offices and shops); IUE: 66 % of 500 VA per point; "
                 "IUG with sockets and TUG: 2200 VA; TUE: 3300 VA."),
        "rows": {"va_per_point_iug": 150, "frac_iug": 0.66, "va_per_point_iue": 500, "frac_iue": 0.66, "va_iugt": 2200, "va_tug": 2200, "va_tue": 3300,
                 "grades": [("minimum", 60, 3700, 1.0), ("medium", 130, 7000, 0.9), ("high", 200, 11000, 0.8), ("superior", None, None, 0.7)]},
    },
    "building_diversity": {
        "title": "Diversity (simultaneity) factor for the set of dwellings of a building (feeder)",
        "source": f"{A771}, table 771.9.III", "verified": True,
        "note": ("Applied to the sum of the total loads of the units; common services are added separately. The standard gives it 'until "
                 "the sections on horizontal property are in force'. Columns: grades minimum and medium / high and superior."),
        "rows": [("2 to 4", 0.9, 0.7), ("5 to 15", 0.8, 0.6), ("15 to 25", 0.6, 0.5), ("over 25", 0.5, 0.4)],
    },
    "earth": {
        "title": "Protective earthing in a TT system",
        "source": f"{A770}, 770.3.2, 770.14.3.2 and 770.14.4.1; {A771}, 771.3 and table 771.3.I", "verified": True,
        "note": ("UL = 24 V: touch voltage limit that AEA adopts from Law 19587 (decrees 351/79 and 911/96). Permanent maximum Ra "
                 "40 Ω, measured on the disconnected electrodes. Column 3 of table 771.3.I leaves a margin of 2 over UL/IΔn and "
                 "never goes above 40 Ω: recommended Ra = min(UL / (2 · IΔn); 40 Ω). With a 30 mA RCD and Ra ≤ 40 Ω the condition holds by itself."),
        "rows": {"ul_v": 24.0, "ra_max_ohm": 40.0, "margin": 2.0},
    },
}

SECTIONS = sorted(TABLES["iz_b1"]["rows"])
FINALS = ("iug", "iugt", "tug", "tue", "specific", "motor", "mbtf")


class Usage(Exception):
    pass


# ---------------------------------------------------------------- helpers

def fmt(x, nd=2):
    """Number with a decimal point, no trailing zeros."""
    if x is None:
        return "—"
    return f"{x:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{x:.0f}"


def num(text, name):
    s = str(text).strip()
    if re.fullmatch(r"[+-]?[1-9]\d{0,2}(\.\d{3}){2,}", s):
        s = s.replace(".", "")                      # "1.250.000": two or more dots can only be thousands separators
    elif re.fullmatch(r"[+-]?[1-9]\d{0,2}\.\d{3}", s):
        # "3.500": in Argentina the dot separates thousands; taking it as 3.5 would give a result a thousand times smaller
        raise Usage(f"{name} '{s}' is ambiguous: if it means {s.replace('.', '')}, write it without the dot; if it means "
                    f"{fmt(float(s), 3)}, write it with a decimal comma ({fmt(float(s), 3).replace('.', ',')}).")
    if "," in s and "." in s:
        if not re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+,\d+", s):
            raise Usage(f"{name} must be a number (got '{text}'): use a comma or a dot for decimals, with no thousands separator.")
        s = s.replace(".", "")                      # "3.500,5" → 3500,5
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        raise Usage(f"{name} must be a number (got '{text}').")
    if math.isnan(v) or math.isinf(v):
        raise Usage(f"{name} must be a finite number.")
    if abs(v) > NUM_MAX:
        raise Usage(f"{name} = {text} is out of range for an installation (maximum {NUM_MAX:.0e}).")
    return v


def integer(opts, key, default):
    """Numeric option that must be whole (conductors): 2.9 is not silently truncated to 2."""
    v = opts.get(key, default)
    if v != int(v):
        raise Usage(f"--{key.replace('_', '-')} must be a whole number (got {fmt(v)}).")
    return int(v)


def finding(check, rule, status, evidence):
    return {"check": check, "rule": rule, "status": status, "evidence": str(evidence)[:300]}


def parse(argv, spec):
    """spec: {'--option': (kind, repeatable)}; kind 'num' | 'str' | 'flag'. Returns a dict keyed without the dashes."""
    out, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            out["json"] = True; i += 1; continue
        if a not in spec:
            raise Usage(f"Unknown option '{a}'. Valid options: {', '.join(sorted(spec))}, --json.")
        kind, rep = spec[a]
        key = a[2:].replace("-", "_")
        if kind == "flag":
            out[key] = True; i += 1; continue
        if i + 1 >= len(argv):
            raise Usage(f"Missing the value of {a}.")
        val = argv[i + 1]
        val = num(val, a) if kind == "num" else val.strip().lower()
        if rep:
            out.setdefault(key, []).append(val)
        elif key in out:
            raise Usage(f"{a} goes only once.")
        else:
            out[key] = val
        i += 2
    return out


def choice(opts, key, allowed, default):
    v = opts.get(key, default)
    if v not in allowed:
        raise Usage(f"--{key.replace('_', '-')} takes {' | '.join(allowed)} (got '{v}').")
    return v


def positive(opts, key, required=True, default=None, allow_zero=False):
    if key not in opts:
        if required:
            raise Usage(f"Missing --{key.replace('_', '-')}.")
        return default
    v = opts[key]
    if v < 0 or (v == 0 and not allow_zero):
        raise Usage(f"--{key.replace('_', '-')} must be greater than zero.")
    return v


def pf_of(opts):
    c = opts.get("pf", 0.85)                         # 770.15.6 note (1): with no data, cos φ = 0.85
    if not 0 < c <= 1:
        raise Usage("--pf goes between 0 and 1 (for example 0.85).")
    return c


def voltage(opts, system):
    v = opts.get("voltage", TABLES["voltage"]["rows"][system])
    if v <= 0:
        raise Usage("--voltage must be greater than zero.")
    return v


def emit(res, as_json):
    res.setdefault("as_of", AS_OF)
    res["legend"] = LEGEND
    res["edition_notice"] = EDITION_NOTICE
    if as_json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print(f"== {res['title']}")
        for line in res.get("lines", []):
            print(line)
        for f in sorted(res.get("findings", []), key=lambda f: ORDER[f["status"]]):
            print(f"{STATUS_MARK[f['status']]} {f['check']} [{f['rule']}]: {f['evidence']}")
        print(f"Source: {res['source']} (data as of {AS_OF}).")
        print(LEGEND.capitalize() + ".")
        print("\nInternal note for the agent: cite the clause of each line; if there is a ❔ say that the value is not verified in a primary "
              "source; do not recalculate from memory, and nothing here authorizes live work. " + EDITION_NOTICE + ".")
    return 1 if any(f["status"] == "fail" for f in res.get("findings", [])) else 0


def r_service(material, cls, s):
    key = {"cu": f"cu{cls}", "al": "al2"}[material]
    tab = TABLES["resistance"]["rows"][key]
    if s not in tab:
        raise Usage(f"No resistance for {fmt(s)} mm² in {material} class {cls}. Sections: {', '.join(fmt(x) for x in sorted(tab))} mm².")
    r20 = tab[s]
    factor = (234.5 + 70) / 254.5 if material == "cu" else (228 + 70) / 248
    return r20, r20 * factor


def drop_volts(i, length_m, r, x, pf, system):
    """ΔU [V] = k · I · L[km] · (R cos φ + X sin φ); k = 2 single-phase, √3 three-phase (770.15.6 a / 771.19.7 a)."""
    k = 2 if system == "single" else SQ3
    sin = math.sqrt(max(0.0, 1 - pf ** 2))
    return k * i * (length_m / 1000) * (r * pf + x * sin)


X_WARN_MM2 = 25         # from here on, leaving X out underestimates the drop by ≥ 7 % against table 770.15.IV (see the drop_limits note)


def reactance_finding(s, x):
    if x:
        return None
    if s < X_WARN_MM2:
        return finding("reactance", "770.15.6 a)", "ok", f"reactance taken as 0: with {fmt(s)} mm² it weighs little (under ~5 %)")
    return finding("reactance", "770.15.6 a) / table 770.15.IV", "warn",
                   f"reactance taken as 0 with {fmt(s)} mm²: the real drop is higher (the AEA quick table gives ~7 % more at 25 mm² and "
                   "~13 % more at 35 mm²); pass --reactance (≈ 0.08 to 0.1 Ω/km for single-core cables in conduit)")


def valid_section(s):
    if s not in SECTIONS:
        raise Usage(f"Section {fmt(s)} mm² does not exist. The standard ones are: {', '.join(fmt(x) for x in SECTIONS)} mm².")
    return s


def f_temp(t):
    """Factor of table 771.16.II.a: next row up if θ is not tabulated; below 20 °C, the 20 °C one."""
    if not 10 <= t <= 60:
        raise Usage("--temp goes between 10 and 60 °C (outside that the full AEA 90364-5-52 table is needed).")
    rows = TABLES["f_temperature"]["rows"]
    return rows[min(k for k in rows if k >= t - 1e-9)]


def f_group(n, layout="bunched"):
    if n != int(n) or n < 1:
        raise Usage("--grouped is the number of grouped circuits (in the same conduit or in conduits that touch): a whole number of 1 or more.")
    n = int(n)
    if n > 20:
        raise Usage("More than 20 grouped circuits: that is not calculated with this table (and is not advisable).")
    if layout == "layer":
        rows = TABLES["f_grouping_layer"]["rows"]
        return rows[min(k for k in rows if k >= n)], False   # IEC B.52.17 item 2: not checked against AEA → ❔
    rows = TABLES["f_grouping"]["rows"]
    key = min(k for k in rows if k >= n)                # 10 or 11 circuits use the 12 row (conservative)
    return rows[key]


def layout_of(o):
    d = choice(o, "layout", ("bunched", "layer"), "bunched")
    if d == "layer" and o.get("grouped", 1) == 1:
        raise Usage("--layout layer goes with --grouped N (N ≥ 2): with a single circuit there is no grouping.")
    return d


def group_text(n, layout):
    n = int(n)
    if n == 1:
        return "1 circuit alone in its conduit"
    return f"{n} grouped circuits ({'in a single layer' if layout == 'layer' else 'bunched: same conduit or conduits that touch'})"


def iz_of(s, conductors, t, n, layout="bunched"):
    base = TABLES["iz_b1"]["rows"][s][0 if conductors == 2 else 1]
    ft = f_temp(t)
    fg, fg_ok = f_group(n, layout)
    return base * ft * fg, base, ft, fg, fg_ok


def iz_findings(t, fg_ok, n, layout="bunched"):
    out = []
    if t != 40:
        rows = TABLES["f_temperature"]["rows"]
        k = min(x for x in rows if x >= t - 1e-9)
        note = "" if k == t else (f" ({k} °C row: {fmt(t, 1)} °C is not in the table and the next row up is taken)" if t > 20
                                  else " (below 20 °C the 20 °C factor is used)")
        out.append(finding("temperature", "table 771.16.II.a", "ok", f"factor {fmt(rows[k])} for {fmt(t, 1)} °C{note}"))
    if not fg_ok and layout == "layer":
        out.append(finding("unverified_data", "IEC 60364-5-52 B.52.17 item 2", "unknown",
                           f"factor for {int(n)} circuits in a single layer taken from IEC (not checked against 771.16.IV item 2); "
                           "valid only if the conduits really run in one layer, not bunched"))
    elif not fg_ok:
        out.append(finding("unverified_data", "IEC 60364-5-52 B.52.17", "unknown",
                           f"factor for {int(n)} grouped circuits taken from IEC: 770.12.II goes up to 3 and 771.16.IV was read for 4, 5, 6 and 8"))
    if int(n) > 1 and layout == "bunched":
        out.append(finding("grouping", "770.12.II / 771.16.IV item 1", "ok",
                           f"factor for {int(n)} bunched circuits (in the same conduit, or separate conduits that touch, as in a riser with one "
                           "conduit per apartment, ELEC-CON-23); if the conduits run in a single layer on the wall: --layout layer"))
    return out


# ---------------------------------------------------------------- current

def cmd_current(argv):
    o = parse(argv, {"--power": ("num", False), "--current": ("num", False), "--va": ("flag", False), "--pf": ("num", False),
                     "--system": ("str", False), "--voltage": ("num", False)})
    system = choice(o, "system", ("single", "three"), "single")
    u, c = voltage(o, system), pf_of(o)
    k = 1 if system == "single" else SQ3
    kt = "" if system == "single" else "√3 × "
    if ("power" in o) == ("current" in o):
        raise Usage("Pass --power (W, or VA with --va) or --current (A), one of the two.")
    if o.get("va") and "current" in o:
        raise Usage("--va goes with --power (it says the power is in VA); with --current the output already gives VA and W.")
    if "power" in o:
        p = positive(o, "power")
        if o.get("va"):
            i = p / (k * u)
            lines = [f"I = S / ({kt}U) = {fmt(p, 0)} VA / ({kt}{fmt(u, 0)} V) = {fmt(i)} A"]
            res = {"power_va": p, "current_a": round(i, 3)}
        else:
            i = p / (k * u * c)
            lines = [f"I = P / ({kt}U × cos φ) = {fmt(p, 0)} W / ({kt}{fmt(u, 0)} V × {fmt(c)}) = {fmt(i)} A",
                     f"(apparent power S = {fmt(p / c, 0)} VA)"]
            res = {"power_w": p, "power_va": round(p / c, 1), "current_a": round(i, 3)}
    else:
        i = positive(o, "current")
        s = k * u * i
        lines = [f"S = {kt}U × I = {kt}{fmt(u, 0)} V × {fmt(i)} A = {fmt(s, 0)} VA", f"P = S × cos φ = {fmt(s * c, 0)} W (cos φ {fmt(c)})"]
        res = {"current_a": i, "power_va": round(s, 1), "power_w": round(s * c, 1)}
    res.update(system=system, voltage_v=u, pf=c)
    return emit({"command": "current", "title": f"Power ↔ current ({system}-phase {fmt(u, 0)} V)", "result": res, "lines": lines,
                 "findings": [], "source": f"{A770} 770.4.2 b) (voltages), 770-B.I (I = DPMS/220 or DPMS/(√3·380)); "
                 + ("cos φ 0.85 by 770.15.6 note (1), for lack of a value" if "pf" not in o else f"cos φ {fmt(c)} (user value)")},
                o.get("json"))


# ---------------------------------------------------------------- voltage drop

def drop_limit(line, upstream):
    row = TABLES["drop_limits"]["rows"][line]
    if row["max"] is None:
        return None, row
    lim = row["max"] - (upstream if line in ("final", "motor") else 0)
    return lim, row


def cmd_drop(argv):
    o = parse(argv, {"--current": ("num", False), "--length": ("num", False), "--section": ("num", False), "--material": ("str", False),
                     "--class": ("str", False), "--system": ("str", False), "--pf": ("num", False), "--reactance": ("num", False),
                     "--line": ("str", False), "--upstream-drop": ("num", False), "--voltage": ("num", False)})
    i, length, s = positive(o, "current"), positive(o, "length"), positive(o, "section")
    material = choice(o, "material", ("cu", "al"), "cu")
    cls = choice(o, "class", ("5", "2"), "5" if material == "cu" else "2")
    if material == "al" and cls != "2":
        raise Usage("Aluminium is class 2 (rigid stranded).")
    system = choice(o, "system", ("single", "three"), "single")
    line = choice(o, "line", ("final", "submain", "motor", "main"), "final")
    c, u = pf_of(o), voltage(o, system)
    x = positive(o, "reactance", required=False, default=0.0, allow_zero=True)
    upstream = positive(o, "upstream_drop", required=False, default=0.0, allow_zero=True)
    if upstream and line not in ("final", "motor"):
        raise Usage("--upstream-drop is added only to a final or motor circuit; the sub-main limit is its own partial "
                    "and the main line's is set by the utility.")
    if material == "cu":
        valid_section(s)
    r20, r70 = r_service(material, cls, s)
    du = drop_volts(i, length, r70, x, c, system)
    pct = 100 * du / u
    k = "2" if system == "single" else "√3"
    sin = math.sqrt(1 - c ** 2)
    lines = [f"R at 70 °C = {fmt(r20, 4)} Ω/km (20 °C) × {fmt(r70 / r20, 4)} = {fmt(r70, 4)} Ω/km ({material} class {cls}, {fmt(s)} mm²)",
             f"ΔU = {k} × {fmt(i)} A × {fmt(length / 1000, 4)} km × ({fmt(r70, 4)} × {fmt(c)} + {fmt(x, 3)} × {fmt(sin)}) = {fmt(du)} V"
             f" → {fmt(pct)} % of {fmt(u, 0)} V"]
    f = []
    fx = reactance_finding(s, x)
    if fx:
        f.append(fx)
    lim, row = drop_limit(line, upstream)
    total = pct + (upstream if line in ("final", "motor") else 0)
    if lim is None:
        f.append(finding("drop_main", row["rule"], "unknown",
                         f"{fmt(pct)} %: there is no limit verified in a primary source for the main line; it is set by AEA 95150 / the utility"))
    else:
        st = "ok" if pct <= lim + 1e-9 else "fail"
        if line in ("final", "motor") and upstream:
            ev = f"{fmt(pct)} % in this run + {fmt(upstream)} % upstream = {fmt(total)} % (max. {fmt(row['max'])} %, {row['desc']})"
        else:
            ev = f"{fmt(pct)} % (max. {fmt(lim)} %, {row['desc']})"
        if line == "submain" and st == "fail":
            ev += "; mandatory in the 771, a recommendation in the 770"
        f.append(finding(f"drop_{line}", row["rule"], st, ev))
        if line == "final" and not upstream:
            f.append(finding("upstream_drop", "771.13 b) note", "ok",
                             "the circuit was taken as leaving the main panel; if it leaves a sub-panel add that drop with --upstream-drop"))
    res = {"current_a": i, "length_m": length, "section_mm2": s, "material": material, "class": int(cls), "system": system,
           "pf": c, "reactance_ohm_km": x, "r20_ohm_km": r20, "r70_ohm_km": round(r70, 5), "drop_v": round(du, 3),
           "drop_pct": round(pct, 3), "upstream_drop_pct": upstream, "total_pct": round(total, 3), "line": line, "limit_pct": lim}
    return emit({"command": "drop", "title": f"Voltage drop, {line} line", "result": res, "lines": lines, "findings": f,
                 "source": f"{A770} 770.15.6; {A771} 771.13 b) and 771.19.7; R per IEC 60228"}, o.get("json"))


# ---------------------------------------------------------------- cross-section

def mcb_for(ib, iz, in_max):
    """The smallest standard MCB with Ib ≤ In ≤ Iz and within the maximum of the circuit type, or None."""
    for n in TABLES["mcb"]["rows"]:
        if n >= ib - 1e-9:
            return n if n <= iz + 1e-9 and (in_max is None or n <= in_max) else None
    return None


def cmd_size(argv):
    o = parse(argv, {"--current": ("num", False), "--length": ("num", False), "--circuit": ("str", False), "--conductors": ("num", False),
                     "--temp": ("num", False), "--grouped": ("num", False), "--max-drop": ("num", False), "--upstream-drop": ("num", False),
                     "--class": ("str", False), "--material": ("str", False), "--system": ("str", False), "--pf": ("num", False),
                     "--voltage": ("num", False), "--reactance": ("num", False), "--layout": ("str", False), "--norm": ("str", False)})
    ib, length = positive(o, "current"), positive(o, "length")
    layout = layout_of(o)
    norm = choice(o, "norm", ("770", "771"), "770")
    if "circuit" not in o:
        raise Usage("Missing --circuit (iug | iugt | tug | tue | specific | motor | submain | main).")
    circ = choice(o, "circuit", ("iug", "iugt", "tug", "tue", "specific", "motor", "submain", "main", "mbtf"), None)
    if o.get("material", "cu") != "cu":
        raise Usage("The internal current-carrying capacity table (770.12.I) is for copper only: aluminium needs AEA 90364-5-52.")
    system = choice(o, "system", ("single", "three"), "single")
    cls = choice(o, "class", ("5", "2"), "5")
    cond = integer(o, "conductors", 2 if system == "single" else 3)
    if cond not in (2, 3):
        raise Usage("--conductors is 2 (phase and neutral) or 3 (three-phase); the PE does not count.")
    if cond != (2 if system == "single" else 3):
        # three-phase with the 2x column would give a higher Iz than the real one; single-phase with 3x does not match the drop formula with k = 2
        raise Usage(f"--conductors {cond} does not match --system {system}: single-phase = 2 loaded conductors, three-phase = 3.")
    if circ in ("iug", "iugt", "tug", "tue", "mbtf") and system == "three":
        raise Usage("IUG, TUG, TUE and MBTF are single-phase circuits (770.6.6 / 771.7.6).")
    t = o.get("temp", 40.0)
    n = o.get("grouped", 1)
    c, u = pf_of(o), voltage(o, system)
    upstream = positive(o, "upstream_drop", required=False, default=0.0, allow_zero=True)
    x = positive(o, "reactance", required=False, default=0.0, allow_zero=True)
    if upstream and circ in ("submain", "main"):
        raise Usage("--upstream-drop is subtracted only on final or motor circuits.")
    f_temp(t); f_group(n, layout)
    if "max_drop" in o:
        dmax = positive(o, "max_drop")
        dmax_rule = "user value"
    elif circ == "main":
        dmax, dmax_rule = None, "770.4.1.1 → AEA 95150"
    else:
        line = "submain" if circ == "submain" else "motor" if circ == "motor" else "final"
        dmax, row = drop_limit(line, upstream)
        dmax_rule = row["rule"]
    smin = TABLES["min_section"]["rows"][circ]
    in_max = TABLES["circuits"]["rows"].get(circ, {}).get("in_max")
    f = iz_findings(t, f_group(n, layout)[1], n, layout)
    lines = [f"Ib = {fmt(ib)} A, {fmt(length)} m, {circ}, {cond} loaded conductors, {fmt(t, 0)} °C, {group_text(n, layout)}"]
    res = {"current_a": ib, "length_m": length, "circuit": circ, "conductors": cond, "temp_c": t, "grouped": int(n), "layout": layout,
           "norm": norm,
           "min_section_mm2": smin, "max_drop_pct": dmax, "circuit_in_max_a": in_max}
    if dmax is not None and dmax <= 1e-9:
        f.append(finding("upstream_drop", dmax_rule, "fail",
                         f"the upstream drop ({fmt(upstream)} %) already uses up the limit: no margin is left for this circuit; the drop "
                         "of the sub-main has to come down (larger section or shorter run)"))
        res["section_mm2"] = None
        return emit({"command": "size", "title": "Minimum cross-section", "result": res, "lines": lines, "findings": f,
                     "source": f"{A770} 770.15.6; {A771} 771.13 b)"}, o.get("json"))
    if in_max is not None and ib > in_max:
        f.append(finding("circuit_type", "770.6.6 / table 770.6.I", "fail",
                         f"a {circ.upper()} is protected with {in_max} A at most and the load asks for {fmt(ib)} A: split the circuit or use another type (TUE or a dedicated one)"))
        res["section_mm2"] = None
        return emit({"command": "size", "title": "Minimum cross-section", "result": res, "lines": lines, "findings": f,
                     "source": f"{A770} 770.6.6"}, o.get("json"))
    big = ib > TABLES["mcb"]["rows"][-1]               # over 63 A: outside the usual MCB series, only the cable is sized
    chosen = None
    reasons = []
    for s in SECTIONS:
        if s < smin:
            continue
        iz, base, ft, fg, _ = iz_of(s, cond, t, n, layout)
        mcb = mcb_for(ib, iz, in_max)
        _, r70 = r_service("cu", cls, s)
        pct = 100 * drop_volts(ib, length, r70, x, c, system) / u
        if iz < ib or (mcb is None and not big):
            reasons.append("current")
            continue
        if dmax is not None and pct > dmax + 1e-9:
            reasons.append("drop")
            continue
        chosen = (s, iz, base, ft, fg, mcb, pct)
        break
    if not chosen:
        f.append(finding("section", "770.12 / 770.15.6", "fail",
                         f"{fmt(ib)} A over {fmt(length)} m fits no section of the table (up to {fmt(SECTIONS[-1])} mm²): "
                         "it needs another installation method, parallel conductors or a shorter run; that is for the designer"))
        res["section_mm2"] = None
        return emit({"command": "size", "title": "Minimum cross-section", "result": res, "lines": lines, "findings": f,
                     "source": f"{A770} tables 770.11.I, 770.12.I, 770.12.II; 770.15.6"}, o.get("json"))
    s, iz, base, ft, fg, mcb, pct = chosen
    mcb_top = max([x for x in TABLES["mcb"]["rows"] if x <= iz + 1e-9 and (in_max is None or x <= in_max)], default=mcb)
    if s == smin and not reasons:
        governs = "the regulatory minimum section"
    else:
        governs = "the voltage drop" if reasons and reasons[-1] == "drop" else "the current-carrying capacity"
    lines += [f"Iz = {base} A (table 770.12.I, {cond}x) × {fmt(ft, 3)} (temp.) × {fmt(fg)} (grouping) = {fmt(iz, 1)} A",
              f"Section: {fmt(s)} mm² (governed by {governs}; regulatory minimum {fmt(smin)} mm²)",
              f"Drop with {fmt(s)} mm²: {fmt(pct)} %" + (f" (max. {fmt(dmax)} %)" if dmax is not None else ""),
              (f"Suggested MCB: {mcb} A (Ib {fmt(ib)} ≤ In {mcb} ≤ Iz {fmt(iz, 1)}); with this cable and this circuit type it takes up to {mcb_top} A"
               if not big else f"Protection: In between {fmt(ib)} A and {fmt(iz, 1)} A (over 63 A: not a usual MCB)")]
    f.append(finding("current_capacity", "770.12 / 770.15.2.1", "ok", f"Iz {fmt(iz, 1)} A ≥ Ib {fmt(ib)} A"))
    unit_max = {"iug": 10, "iugt": 10, "tug": 10, "tue": 20}.get(circ)
    if unit_max is not None and ib > unit_max + 1e-9:
        f.append(finding("unit_load", "770.6.6 / table 770.6.I", "warn",
                         f"a {circ.upper()} feeds loads of up to {unit_max} A each (2P+E {unit_max} A socket): if the {fmt(ib)} A are "
                         "one single appliance (an air conditioner, an oven), it does not go on this circuit but on "
                         + ("a dedicated circuit (ACU)" if circ == "tue" else "a TUE or a dedicated circuit (ACU)")))
    if circ == "tue" and not big and mcb is not None and mcb > 20:
        f.append(finding("tue_sockets", "ELEC-AMP-19 (safety criterion) / table 770.6.I", "warn",
                         f"{mcb} A MCB on a TUE: the type's cap is 32 A, but its sockets are 2P+E 20 A IRAM 2071 (or 16 A IEC 60309) and "
                         "this guide does not protect a 20 A socket with more than 20 A (16 A with IEC 60309): use 20 A or move the load to an ACU"))
    fx = reactance_finding(s, x)
    if fx and fx["status"] == "warn" and dmax is not None:
        f.append(fx)
    f.append(finding("min_section", "table 770.11.I / 771.13.I", "ok", f"{fmt(s)} mm² ≥ {fmt(smin)} mm² for {circ}"))
    if dmax is None:
        f.append(finding("drop", dmax_rule, "unknown", f"{fmt(pct)} %: no verified limit for the main line; pass --max-drop if the utility gave you one"))
    else:
        f.append(finding("drop", dmax_rule, "ok", f"{fmt(pct)} % ≤ {fmt(dmax)} %" + (f" ({fmt(upstream)} % upstream already subtracted)" if upstream and circ not in ("submain",) else "")))
    if big:
        mcb = mcb_top = None
        f.append(finding("mcb", "IEC 60898-1 5.3.2", "warn",
                         f"{fmt(ib)} A exceeds the usual MCB series (up to 63 A): molded-case circuit breaker or fuse with Ib ≤ In ≤ Iz and "
                         "I2 ≤ 1.45 Iz (check with 'coordinate'); the designer chooses it"))
    else:
        f.append(finding("coordination", "770.15.2.1 / 770-B.I", "ok", f"Ib {fmt(ib)} ≤ In {mcb} ≤ Iz {fmt(iz, 1)} A; I2 = 1.45 In holds by itself with an IEC 60898-1 MCB"))
    if circ in FINALS and circ != "mbtf":
        f.append(finding("rcd", "770.14.2.3 / 771.18.3.5", "ok", "final circuit: it also takes an RCD of IΔn ≤ 30 mA upstream"
                         + (" (type A at least if it feeds an inverter or a drive, ELEC-ESP-2)" if circ in ("tue", "specific", "motor") else "")))
    if circ in ("tue", "specific", "motor") and not big and mcb is not None:
        f.append(finding("starting_current", "ELEC-ESP-11 / IEC 60898-1 (curves)", "ok",
                         f"{mcb} A is the smallest MCB that complies; this calculation does not see the starting current: for a compressor or a "
                         f"motor (air conditioner, pump) curve C and a larger rating are usual, up to {mcb_top} A with this cable and this circuit"
                         + (" (20 A if it ends in a 2P+E 20 A socket, ELEC-AMP-19)" if circ == "tue" and mcb_top > 20 else "")
                         + "; the equipment manual governs, always with In ≤ Iz"))
    if norm == "771" and circ == "submain":
        f.append(finding("norm", "771.13 b) note", "ok", "771: the 1 % on the sub-main is mandatory (in the 770 it is a recommendation)"))
    res.update(reactance_ohm_km=x, section_mm2=s, iz_a=round(iz, 2), iz_table_a=base, f_temp=round(ft, 3), f_grouping=fg, drop_pct=round(pct, 3),
               mcb_a=mcb, mcb_max_a=mcb_top, governed_by=governs)
    source = (f"{A770} tables 770.11.I, 770.12.I, 770.12.II, 770.6.I; 770.15.6; IEC 60898-1" if norm == "770" else
              f"{A771} tables 771.13.I (minimum sections), 771.16.I (current-carrying capacity, same values as 770.12.I), 771.16.IV "
              f"(grouping), 771.7.I (circuit types); 771.13 b) (drop); IEC 60898-1")
    if layout == "layer":
        source += "; IEC 60364-5-52 table B.52.17 item 2 (single layer)"
    return emit({"command": "size", "title": "Minimum cross-section", "result": res, "lines": lines, "findings": f,
                 "source": source}, o.get("json"))


# ---------------------------------------------------------------- coordination

def cmd_coordinate(argv):
    o = parse(argv, {"--ib": ("num", False), "--in": ("num", False), "--iz": ("num", False), "--section": ("num", False),
                     "--conductors": ("num", False), "--temp": ("num", False), "--grouped": ("num", False), "--device": ("str", False),
                     "--i2": ("num", False), "--layout": ("str", False), "--norm": ("str", False)})
    ib, inn = positive(o, "ib", required=False), positive(o, "in")
    layout = layout_of(o)
    norm = choice(o, "norm", ("770", "771"), "770")
    dev = choice(o, "device", ("mcb", "fuse"), "mcb")
    lines, f = [], []
    if ("iz" in o) == ("section" in o):
        raise Usage("Pass --iz (A) or --section (mm², and it is taken from table 770.12.I), one of the two.")
    if "iz" in o:
        iz = positive(o, "iz")
        lines.append(f"Iz = {fmt(iz, 1)} A (given)")
    else:
        s = valid_section(o["section"])
        cond = integer(o, "conductors", 2)
        if cond not in (2, 3):
            raise Usage("--conductors is 2 or 3.")
        t, n = o.get("temp", 40.0), o.get("grouped", 1)
        iz, base, ft, fg, fg_ok = iz_of(s, cond, t, n, layout)
        f += iz_findings(t, fg_ok, n, layout)
        lines.append(f"Iz = {base} A (table 770.12.I, {fmt(s)} mm² {cond}x) × {fmt(ft, 3)} (temp.) × {fmt(fg)} ({group_text(n, layout)}) = {fmt(iz, 1)} A")
    if "i2" in o:
        i2, i2_src = positive(o, "i2"), "user value"
    elif dev == "mcb":
        i2, i2_src = 1.45 * inn, "IEC 60898-1: I2 = 1.45 In"
    else:
        mult = 2.1 if inn <= 4 else 1.9 if inn < 16 else 1.6
        i2, i2_src = mult * inn, f"IEC 60269-1: I2 = {fmt(mult)} In (not verified in a primary source)"
        f.append(finding("unverified_data", "IEC 60269-1 table 2", "unknown", f"I2 of the gG fuse = {fmt(mult)} In, not verified in this review"))
    lines.append(f"I2 = {fmt(i2, 1)} A ({i2_src}); 1.45 Iz = {fmt(1.45 * iz, 1)} A")
    if ib is None:
        f.append(finding("ib_le_in", "770.15.2.1", "unknown", "without --ib it was not checked that the load fits the protection (Ib ≤ In); "
                         "what follows only says whether the cable withstands that protection"))
    else:
        f.append(finding("ib_le_in", "770.15.2.1", "ok" if ib <= inn + 1e-9 else "fail",
                         f"Ib {fmt(ib)} A ≤ In {fmt(inn)} A" if ib <= inn + 1e-9 else f"Ib {fmt(ib)} A > In {fmt(inn)} A: the protection will trip with the normal load"))
    f.append(finding("in_le_iz", "770.15.2.1", "ok" if inn <= iz + 1e-9 else "fail",
                     f"In {fmt(inn)} A ≤ Iz {fmt(iz, 1)} A" if inn <= iz + 1e-9 else
                     f"In {fmt(inn)} A > Iz {fmt(iz, 1)} A: the cable can overheat without the protection tripping; lower the In or raise the section"))
    f.append(finding("i2_le_145iz", "770-B.I / AEA 90364-4-43", "ok" if i2 <= 1.45 * iz + 1e-9 else "fail",
                     f"I2 {fmt(i2, 1)} A {'≤' if i2 <= 1.45 * iz + 1e-9 else '>'} 1.45 Iz {fmt(1.45 * iz, 1)} A"))
    if dev == "mcb" and inn not in TABLES["mcb"]["rows"]:
        if inn in TABLES["mcb"]["iec_series"]:
            f.append(finding("standard_rating", "IEC 60898-1 5.3.2", "ok",
                             f"{fmt(inn)} A is an IEC 60898-1 preferred value, but on the Argentine market it is harder to find than "
                             f"{', '.join(map(str, TABLES['mcb']['rows']))} A: confirm it exists in the product line to be bought"))
        else:
            f.append(finding("standard_rating", "IEC 60898-1 5.3.2", "warn",
                             f"{fmt(inn)} A is not an IEC 60898-1 preferred value ({', '.join(map(str, TABLES['mcb']['iec_series']))} A)"))
    res = {"ib_a": ib, "in_a": inn, "iz_a": round(iz, 2), "i2_a": round(i2, 2), "device": dev,
           "complies": not any(x["status"] == "fail" for x in f)}
    return emit({"command": "coordinate", "title": f"Protection–cable coordination ({dev})", "result": res,
                 "lines": lines, "findings": f,
                 "source": (f"{A770} 770.15.2.1 and annex 770-B (table 770-B.I); IEC 60898-1" if norm == "770" else
                            f"{A771} 771.19 (overload protection, same conditions Ib ≤ In ≤ Iz and I2 ≤ 1.45 Iz) and table 771.16.I; "
                            "IEC 60898-1")}, o.get("json"))


# ---------------------------------------------------------------- demand and grade

GRADES = ("minimum", "medium", "high", "superior")
GRADE_NAME = {"minimum": "Minimum", "medium": "Medium", "high": "High", "superior": "Superior"}


def grade_by_area(area, grades):
    for name, smax, _, _ in grades:
        if smax is None or area <= smax:
            return name
    return grades[-1][0]


def missing_circuits(norm, grade, n):
    """What is missing for the minimum number of circuits (table 770.7.II or 771.8.II). n: counts per type."""
    iug, tug, tue, iue, other = n["iug"] + n["iugt"], n["tug"], n["tue"], n["iue"], n["specific"]
    total = iug + tug + tue + iue + other
    missing = []

    def need(have, want, what):
        if have < want:
            missing.append(f"missing {want - have} {what} (has {have}, the grade asks for {want})")

    need(iug, 1 if grade in ("minimum", "medium") else 2, "general-use lighting circuit(s) (IUG)")
    need(tug, 1 if grade in ("minimum", "medium") else 2, "general-use socket circuit(s) (TUG)")
    if norm == "770":
        if grade == "medium":
            need(iug + tug, 3, "general-use circuit(s) (IUG or TUG; variants 2+1 or 1+2)")
        if grade in ("high", "superior"):
            need(iug + tug, 5, "general-use circuit(s) (IUG or TUG; variants 2+3 or 3+2)")
        if grade == "superior":
            need(total, 6, "circuit(s) in total (the sixth is of free choice)")
    else:
        if grade == "medium":
            need(iug + tug + iue + tue, 3, "general or special-use circuit(s) (the third IUG, TUG, IUE or TUE)")
        if grade in ("high", "superior"):
            need(tue, 1, "special-use socket circuit(s) (TUE)")
        if grade == "superior":
            need(total, 6, "circuit(s) in total (the sixth is of free choice)")
    return missing


def cmd_demand(argv):
    o = parse(argv, {"--area": ("num", False), "--semi-covered": ("num", False), "--iug": ("num", True), "--iugt": ("num", True),
                     "--tug": ("num", True), "--tue": ("num", True), "--iue": ("num", True), "--specific": ("num", True),
                     "--norm": ("str", False), "--system": ("str", False)})
    area = positive(o, "area")
    semi = positive(o, "semi_covered", required=False, default=0.0, allow_zero=True)
    norm = choice(o, "norm", ("770", "771"), "770")
    system = choice(o, "system", ("single", "three"), "single")
    tab = TABLES[f"dpms_{norm}"]["rows"]
    if norm == "770" and o.get("iue"):
        raise Usage("The 770 has no IUE circuits: use --norm 771, or enter it as --specific VA.")
    for k in ("iug", "iugt", "tug", "tue", "iue"):
        for b in o.get(k, []):
            if b != int(b) or b < 1:
                raise Usage(f"--{k} is the number of points of the circuit: a whole number of 1 or more (got {fmt(b)}).")
    for v in o.get("specific", []):
        if v <= 0:
            raise Usage("--specific is the power of the circuit in VA, greater than zero.")
    if not any(o.get(k) for k in ("iug", "iugt", "tug", "tue", "iue")):
        raise Usage("Missing the list of circuits: for example --iug 8 --iug 6 --tug 10 --tue 2 (each number is the points of that circuit).")
    area_calc = area + 0.5 * semi
    lines, f, det = [], [], []
    for b in o.get("iug", []):
        va = tab["frac_iug"] * tab["va_per_point_iug"] * b
        det.append(("IUG", int(b), va))
    for b in o.get("iugt", []):
        det.append(("IUGT", int(b), tab["va_iugt"]))
    for b in o.get("tug", []):
        det.append(("TUG", int(b), tab["va_tug"]))
    for b in o.get("iue", []):
        det.append(("IUE", int(b), tab["frac_iue"] * tab["va_per_point_iue"] * b))
    for b in o.get("tue", []):
        det.append(("TUE", int(b), tab["va_tue"]))
    total_sum = sum(va for _, _, va in det)
    grades = tab["grades"]
    g_area = grade_by_area(area_calc, grades)
    grade = g_area
    g_cons = g_area
    if norm == "771":
        # 771.8.1.5: the grade is tried with its own coefficient; if the DPMS exceeds the cap, next grade (and no going back)
        idx = GRADES.index(g_area)
        while grades[idx][2] is not None and total_sum * grades[idx][3] > grades[idx][2] + 1e-9:
            idx += 1
        grade = GRADES[idx]
        idx_c = GRADES.index(g_area)                    # conservative reading: the sum without coefficient against the cap
        while grades[idx_c][2] is not None and total_sum > grades[idx_c][2] + 1e-9:
            idx_c += 1
        g_cons = GRADES[idx_c]
    coef = dict((g[0], g[3]) for g in grades)[grade]
    dpms = total_sum * coef
    spec = sum(o.get("specific", []))
    total = dpms + spec
    k = 1 if system == "single" else SQ3
    u = TABLES["voltage"]["rows"][system]
    i_dpms, i_total = dpms / (k * u), total / (k * u)
    if norm == "770":
        iug_rule = f"2/3 × {tab['va_per_point_iug']} VA per point"
    else:
        iug_rule = f"66 % × {tab['va_per_point_iug']} VA per point"
    lines.append(f"Calculation area = {fmt(area)} + 50 % × {fmt(semi)} = {fmt(area_calc)} m² → grade by area: {GRADE_NAME[g_area]}")
    for name, b, va in det:
        extra = (f" ({iug_rule})" if name == "IUG" else " (66 % × 500 VA per point)" if name == "IUE"
                 else " (IUG with sockets)" if name == "IUGT" else "")
        lines.append(f"  {name:<12} {b:>2} point(s) → {fmt(va, 0)} VA{extra}")
    lines.append(f"Sum = {fmt(total_sum, 0)} VA" + (f"; the DPMS exceeds the cap of grade {GRADE_NAME[g_area]} and it becomes {GRADE_NAME[grade]}"
                                                   if norm == "771" and grade != g_area else ""))
    lines.append(f"DPMS = {fmt(total_sum, 0)} VA × {fmt(coef)} (coef. grade {GRADE_NAME[grade]}) = {fmt(dpms, 0)} VA → {fmt(i_dpms)} A")
    if spec:
        lines.append(f"Total load = DPMS + dedicated {fmt(spec, 0)} VA = {fmt(total, 0)} VA → {fmt(i_total)} A")
    rule_g = "770.7.3 / table 770.7.I" if norm == "770" else "771.8.2.1 / table 771.8.I"
    rule_c = "770.7.4 / table 770.7.II" if norm == "770" else "771.8.2.2 / table 771.8.II"
    rule_d = "770.8.1 / tables 770.8.I and 770.8.II" if norm == "770" else "771.9.1 / tables 771.9.I and 771.9.II"
    f.append(finding("grade", rule_g, "ok", f"{GRADE_NAME[grade]} ({fmt(area_calc)} m²" + (f", DPMS {fmt(dpms, 0)} VA" if norm == "771" else "") + ")"))
    if norm == "771" and g_cons != grade:
        f.append(finding("conservative_grade", "771.8.1.5 / 771.9.1", "warn",
                         f"comparing the sum without coefficient ({fmt(total_sum, 0)} VA) with the caps would give {GRADE_NAME[g_cons]}: it is the "
                         "stricter reading; the designer decides (more circuits and minimum points)"))
    if norm == "770":
        explicit = "norm" in o
        f.append(finding("applicable_norm", "770.1", "ok" if explicit else "warn",
                         "the 770 is only for single-family houses up to 63 A" + ("" if explicit else
                         " and it was used by default: if this is an apartment in a building, an office or a shop, repeat with --norm 771 "
                         "(150 VA per IUG point instead of 60 VA)")))
    f.append(finding("dpms", rule_d, "ok", f"{fmt(dpms, 0)} VA ({fmt(i_dpms)} A); the per-circuit values are minimums: if the real load is higher, the real one applies"))
    if norm == "770":
        nmin = {"minimum": 2, "medium": 3, "high": 5, "superior": 6}[grade]
        f.append(finding("coefficient", "table 770.8.II", "ok",
                         f"{fmt(coef)} taken from the grade ({nmin} minimum circuits); "
                         "the wording allows reading it by the real number of circuits, which would give the same or less"))
    counts = {k2: len(o.get(k2, [])) for k2 in ("iug", "iugt", "tug", "tue", "iue", "specific")}
    missing = missing_circuits(norm, grade, counts)
    for x in missing:
        f.append(finding("min_circuits", rule_c, "fail", x))
    if not missing:
        f.append(finding("min_circuits", rule_c, "ok", f"meets the minimum number of circuits of grade {GRADE_NAME[grade]}"))
    type_key = {"IUG": "iug", "IUGT": "iugt", "TUG": "tug", "IUE": "iue", "TUE": "tue"}
    for name, b, _ in det:
        if norm == "771":
            bmax, rule_b = TABLES["points_771"]["rows"][type_key[name]], "771.7.6 / table 771.7.I"
        else:
            bmax, rule_b = TABLES["circuits"]["rows"][type_key[name]]["points_max"], "770.6.6 / table 770.6.I"
        if b > bmax:
            f.append(finding("points_per_circuit", rule_b, "fail", f"a {name} with {b} points: the maximum is {bmax}"))
    if system == "single" and (total > 7000 or i_total > 32):
        f.append(finding("supply", "770.8.3.3 / 771.9.3.3", "warn",
                         f"total load {fmt(total, 0)} VA ({fmt(i_total)} A) exceeds 7 kVA or 32 A: a three-phase supply is advisable"))
    if norm == "770" and i_total > 63:
        f.append(finding("scope_770", "770.1 a)", "warn", f"{fmt(i_total)} A exceeds the 63 A incoming limit: this dwelling is designed with the 771 (--norm 771)"))
    if spec:
        f.append(finding("dedicated_circuits", "770.8.2 / 771.9.2", "ok", "dedicated circuits were added at 100 %: the designer may apply utilization coefficients"))
    res = {"norm": norm, "calc_area_m2": area_calc, "grade_by_area": g_area, "grade": grade, "sum_va": round(total_sum, 1),
           "coefficient": coef, "dpms_va": round(dpms, 1), "dpms_current_a": round(i_dpms, 2), "specific_va": spec,
           "total_load_va": round(total, 1), "total_current_a": round(i_total, 2), "system": system,
           "circuits": [{"type": nm, "points": b, "va": round(va, 1)} for nm, b, va in det], "missing": missing}
    src = (f"{A770} 770.7.3, 770.7.4, 770.8 (tables 770.7.I, 770.7.II, 770.8.I, 770.8.II)" if norm == "770" else
           f"{A771} 771.8.2, 771.9 (tables 771.8.I, 771.8.II, 771.9.I, 771.9.II)")
    return emit({"command": "demand", "title": f"Demand (DPMS) and electrification grade under the {norm}", "result": res, "lines": lines,
                 "findings": f, "source": src}, o.get("json"))


# ---------------------------------------------------------------- building

def diversity(n, column):
    """Table 771.9.III (precedent): 1 unit = 1; 2 to 4, 5 to 15 (15 takes the higher), 15 to 25, over 25."""
    if n <= 1:
        return 1.0
    rows = TABLES["building_diversity"]["rows"]
    lim = (4, 15, 25, None)
    for (name, a, b), top in zip(rows, lim):
        if top is None or n <= top:
            return a if column == 0 else b
    return rows[-1][1 + column]


def cmd_building(argv):
    o = parse(argv, {"--units": ("num", True), "--dpms": ("num", True), "--grade": ("str", False), "--common-3ph": ("num", False),
                     "--common-1ph": ("num", False), "--coef": ("num", False)})
    nn, vv = o.get("units", []), o.get("dpms", [])
    if not nn or len(nn) != len(vv):
        raise Usage("Pass --units N --dpms VA (one pair per unit type; the DPMS comes from 'demand --norm 771').")
    units = []
    for n, v in zip(nn, vv):
        if n != int(n) or n < 1:
            raise Usage("--units is a whole number of 1 or more.")
        if v <= 0:
            raise Usage("--dpms is the DPMS (or total load) of each unit in VA, greater than zero.")
        units += [v] * int(n)
    if len(units) > 200:
        raise Usage("More than 200 units: that is a network design, not this calculation.")
    grade = o.get("grade")
    if grade is not None:
        grade = choice(o, "grade", GRADES, None)
    col = 1 if grade in ("high", "superior") else 0
    common_3ph = positive(o, "common_3ph", required=False, default=0.0, allow_zero=True)
    common_1ph = positive(o, "common_1ph", required=False, default=0.0, allow_zero=True)
    n = len(units)
    f, lines = [], []
    if "coef" in o:
        c_tot = o["coef"]
        if not 0 < c_tot <= 1:
            raise Usage("--coef goes between 0 and 1 (for example 0.8).")
        src = "user value (table 772.9.III or asked by the utility)"
    else:
        c_tot = diversity(n, col)
        src = "table 771.9.III (optional precedent)"
    u_f, u_l = TABLES["voltage"]["rows"]["single"], TABLES["voltage"]["rows"]["three"]
    units_sum = sum(units)
    s_units = units_sum * c_tot
    total = s_units + common_3ph + common_1ph
    i_eq = total / (SQ3 * u_l)
    lines.append(f"Units: {n}, sum {fmt(units_sum, 0)} VA × {fmt(c_tot)} ({src}) = {fmt(s_units, 0)} VA")
    if common_3ph or common_1ph:
        lines.append(f"Common services: {fmt(common_3ph, 0)} VA three-phase + {fmt(common_1ph, 0)} VA single-phase")
    lines.append(f"Building total = {fmt(total, 0)} VA ({fmt(total / 1000, 1)} kVA) → {fmt(i_eq, 1)} A per phase if it were balanced "
                 f"(S / (√3 × {fmt(u_l, 0)} V))")
    # split: each unit to the least loaded phase (largest to smallest); ties, L1 → L3
    phases = {"L1": [], "L2": [], "L3": []}
    for v in sorted(units, reverse=True):
        dest = min(phases, key=lambda k: (sum(phases[k]), list(phases).index(k)))
        phases[dest].append(v)
    load = {}
    for k, lst in phases.items():
        cf = diversity(len(lst), col) if "coef" not in o else max(c_tot, diversity(len(lst), col))
        load[k] = [sum(lst) * cf, cf, len(lst)]
    lightest = min(load, key=lambda k: (load[k][0], list(load).index(k)))
    lines.append("Split per phase (coefficient of the units on that phase, stricter than the one for the whole set):")
    for k in phases:
        va, cf, cnt = load[k]
        extra = common_3ph / 3 + (common_1ph if k == lightest else 0)
        load[k][0] = va + extra
        lines.append(f"  {k}: {cnt} unit(s) × coef. {fmt(cf)} = {fmt(va, 0)} VA + CS {fmt(extra, 0)} VA = {fmt(va + extra, 0)} VA → "
                     f"{fmt((va + extra) / u_f, 1)} A" + (" (the single-phase common services go here)" if k == lightest and common_1ph else ""))
    kmax = max(load, key=lambda k: load[k][0])
    vmax = load[kmax][0]
    vmin = min(c[0] for c in load.values())
    imb = 100 * (vmax - vmin) / vmax if vmax else 0
    lines.append(f"Most loaded phase: {kmax}, {fmt(vmax, 0)} VA → {fmt(vmax / u_f, 1)} A (size with this one, not with the average)")
    rule_c = "771.9.4.2 / table 771.9.III"
    if "coef" in o:
        f.append(finding("coefficient", "772.9.2 / table 772.9.III", "ok", f"coefficient {fmt(c_tot)} given by the user"))
    else:
        f.append(finding("coefficient", rule_c, "unknown",
                         f"{fmt(c_tot)} for {n} units ({'high/superior' if col else 'minimum/medium'}) is the optional precedent of the 771; "
                         "the current one is table 772.9.III, which this guide does not have: redo the calculation with that copy (--coef X) (ELEC-CIR-17)"))
    if grade is None:
        f.append(finding("grade", rule_c, "warn", "without --grade the minimum/medium column was used (higher coefficients, more conservative)"))
    f.append(finding("most_loaded_phase", "ELEC-CIR-16 / ELEC-EDI-10", "ok" if imb <= 25 else "warn",
                     f"{kmax} with {fmt(vmax / u_f, 1)} A; difference between phases {fmt(imb, 0)} %"
                     + ("" if imb <= 25 else ": rotate units or move single-phase loads to the light phase")))
    if total > 60000:
        f.append(finding("transformer_room", "ENRE Supply Regulation art. 1 g) (ELEC-EDI-2)", "warn",
                         f"{fmt(total / 1000, 1)} kVA exceeds 60 kVA: in the Edenor/Edesur area the utility may ask for a room for a transformer "
                         "substation; ask in the feasibility request (other provinces: the utility's regulation)"))
    elif total > 50000:
        f.append(finding("transformer_room", "ENRE Supply Regulation art. 1 g) (ELEC-EDI-2)", "warn",
                         f"{fmt(total / 1000, 1)} kVA is close to 60 kVA: ask about the transformer substation in the feasibility request and do not "
                         "shrink the forecast to stay below (it is a sworn statement)"))
    large = [v for v in set(units) if v > 7000 or v / u_f > 32]
    if large:
        f.append(finding("unit_supply", "771.9.3.3", "warn",
                         f"unit(s) of {', '.join(fmt(v, 0) for v in sorted(large))} VA: over 7 kVA or 32 A, three-phase is advisable"))
    res = {"units": n, "units_sum_va": round(units_sum, 1), "coefficient": c_tot, "units_va": round(s_units, 1), "common_3ph_va": common_3ph,
           "common_1ph_va": common_1ph, "total_va": round(total, 1), "balanced_current_a": round(i_eq, 2),
           "phases": {k: {"units": load[k][2], "coefficient": load[k][1], "va": round(load[k][0], 1),
                          "current_a": round(load[k][0] / u_f, 2)} for k in load},
           "most_loaded_phase": kmax, "imbalance_pct": round(imb, 1)}
    return emit({"command": "building", "title": "Demand of a building with single-phase units (3×380/220 V)", "result": res,
                 "lines": lines, "findings": f,
                 "source": (f"{A771} 771.9.4.2 and table 771.9.III (precedent; current: AEA 90364-7-772:2019 table 772.9.III); "
                            "method of buildings.md (ELEC-EDI-10, ELEC-CIR-16, ELEC-CIR-17)")}, o.get("json"))


# ---------------------------------------------------------------- guide: one rule or a search

def guide_dir():
    import os
    for d in (os.environ.get("ELECTRICIDAD_GUIDE"), "/usr/local/share/aibridge/electricidad",
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "electricidad")):
        if d and os.path.isfile(os.path.join(d, "RULES.md")):
            return d
    raise Usage("Cannot find the guide (RULES.md): set ELECTRICIDAD_GUIDE to its folder.")


def cmd_rule(argv):
    import glob, os
    ids = [a.strip().upper() for a in argv if a != "--json"]
    if not ids:
        raise Usage("Usage: electricidad rule ELEC-PRO-7 [ELEC-REV-21 ...]")
    for i in ids:
        if not re.fullmatch(r"ELEC-[A-Z]{3}-\d{1,3}", i):
            raise Usage(f"'{i}' is not a rule ID (form ELEC-PRO-7). To search by word: electricidad search WORD")
    d = guide_dir()
    found = {}
    for path in sorted(glob.glob(os.path.join(d, "*.md"))):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        cur = None
        for ln in lines:
            m = re.match(r"### (ELEC-[A-Z]{3}-\d{1,3}):", ln)
            if m or ln.startswith("## ") or ln.startswith("# ") or (ln.startswith("### ") and not m):
                cur = m.group(1) if m and m.group(1) in ids else None
                if cur:
                    found[cur] = [f"({os.path.basename(path)})", ln]
                continue
            if cur:
                found[cur].append(ln)
    out = []
    for i in ids:
        if i not in found:
            out.append(f"{i} is not in the guide. Search by word: electricidad search WORD")
        else:
            out.append("\n".join(found[i]).rstrip())
    print("\n\n".join(out))
    return 0 if all(i in found for i in ids) else 1


def _no_accents(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _stem(w):
    # simple stem, Spanish and English: "puentear" → "puente", "tableros" → "tabler", "panels" → "panel", "tripping" → "tripp"
    if len(w) > 5 and w[-2:] in ("ar", "er", "ir", "as", "es", "os", "ed"):
        return w[:-2]
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("s"):
        return w[:-1]
    return w


def _glossary(d):
    """GLOSSARY.md: {stem of the Spanish word: [English terms the guide uses]}; rows '| Spanish | English | note |'."""
    import os
    out = {}
    p = os.path.join(d, "GLOSSARY.md")
    if not os.path.isfile(p):
        return out
    with open(p, encoding="utf-8") as fh:
        for ln in fh:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not ln.lstrip().startswith("|") or len(cells) < 2 or set(cells[0]) <= set("-: ") or cells[0].lower().startswith("spanish"):
                continue
            en = re.sub(r"\*[^*]*\*|\([^)]*\)|`", " ", cells[1])
            ens = [_no_accents(x).strip() for x in re.split(r"[,/;]", en)]
            ens = [x[:-1] if len(x) > 4 and x.endswith("s") else x for x in ens if len(x) > 2]
            for es in re.split(r"[,/;]", re.sub(r"[*`]|\([^)]*\)", " ", cells[0])):
                es = _no_accents(es).strip()
                if es:
                    out.setdefault(_stem(es.split()[0]) if len(es.split()) > 1 else _stem(es), []).extend(ens)
    return out


def cmd_search(argv):
    import os
    words = [_stem(_no_accents(a)) for a in argv if a != "--json"]
    if not words:
        raise Usage("Usage: electricidad search WORD [WORD ...]: lines of RULES.md that have all the words")
    d = guide_dir()
    glos = _glossary(d)
    # each word counts by itself or by its glossary translation: "puentear" finds "bypass", "disyuntor" finds "RCD"
    alts = [{w, *glos.get(w, [])} for w in words]
    with open(os.path.join(d, "RULES.md"), encoding="utf-8") as fh:
        rows = [ln for ln in fh.read().split("\n") if ln.startswith("- ELEC-")]
    has = lambda ln, a: any(x in _no_accents(ln) for x in a)
    hits = [ln for ln in rows if all(has(ln, a) for a in alts)]
    if not hits and len(words) > 1:
        hits = [ln for ln in rows if any(has(ln, a) for a in alts)]
        if hits:
            print("(no rule has all the words; these have some)")
    print("\n".join(hits[:40]) if hits else "Nothing in RULES.md. Try another word (the stem, in English or Spanish: 'bypass', 'leak', 'puente', 'fuga').")
    if len(hits) > 40:
        print(f"... and {len(hits) - 40} more: add another word to narrow it down.")
    print("Read only the rule that helps: electricidad rule ELEC-XXX-n")
    return 0


# ---------------------------------------------------------------- earthing

def cmd_earth(argv):
    o = parse(argv, {"--ra": ("num", False), "--idn": ("num", False), "--ul": ("num", False)})
    ra = positive(o, "ra")
    idn_ma = positive(o, "idn", required=False, default=30.0)
    ul = positive(o, "ul", required=False, default=TABLES["earth"]["rows"]["ul_v"])
    rmax = TABLES["earth"]["rows"]["ra_max_ohm"]
    idn = idn_ma / 1000
    uc = ra * idn
    r_theo = ul / idn
    r_rec = min(ul / (TABLES["earth"]["rows"]["margin"] * idn), rmax)
    lines = [f"Ra × IΔn = {fmt(ra)} Ω × {fmt(idn, 3)} A = {fmt(uc)} V (limit UL {fmt(ul, 0)} V)",
             f"Theoretical maximum Ra = UL / IΔn = {fmt(r_theo, 1)} Ω; recommended = min(UL / (2·IΔn); {fmt(rmax, 0)} Ω) = {fmt(r_rec, 1)} Ω"]
    f = []
    f.append(finding("ra_x_idn", "770.14.3.2 / 771.3", "ok" if uc <= ul + 1e-9 else "fail",
                     f"{fmt(uc)} V {'≤' if uc <= ul + 1e-9 else '>'} {fmt(ul, 0)} V" +
                     ("" if uc <= ul + 1e-9 else ": a fault to frame leaves a dangerous voltage on the metal parts; improve the earth or lower the IΔn")))
    f.append(finding("ra_max", "770.3.2 / 770.14.4.1 / 771.3.3.1", "ok" if ra <= rmax + 1e-9 else "fail",
                     f"Ra {fmt(ra)} Ω {'≤' if ra <= rmax + 1e-9 else '>'} {fmt(rmax, 0)} Ω (permanent maximum, measured with the electrodes disconnected)"))
    if ra <= rmax and uc <= ul and ra > r_rec + 1e-9:
        f.append(finding("ra_recommended", "table 771.3.I column 3", "warn",
                         f"Ra {fmt(ra)} Ω exceeds the recommended value {fmt(r_rec, 1)} Ω for IΔn {fmt(idn_ma, 0)} mA (margin for seasonal variation)"))
    if ul != TABLES["earth"]["rows"]["ul_v"]:
        f.append(finding("ul", "771.3 (Law 19587, decrees 351/79 and 911/96)", "warn", f"UL {fmt(ul, 0)} V: AEA adopts 24 V for dwellings, offices and shops"))
    if idn_ma > 30:
        f.append(finding("idn", "770.14.2.3 / 771.18.3.5", "warn",
                         f"IΔn {fmt(idn_ma, 0)} mA gives no additional protection against direct contact: final circuits take an RCD ≤ 30 mA"))
    res = {"ra_ohm": ra, "idn_ma": idn_ma, "ul_v": ul, "touch_voltage_v": round(uc, 3), "ra_max_theoretical_ohm": round(r_theo, 2),
           "ra_recommended_ohm": round(r_rec, 2), "ra_max_regulatory_ohm": rmax, "complies": not any(x["status"] == "fail" for x in f)}
    return emit({"command": "earth", "title": "Protective earthing (TT system)", "result": res, "lines": lines, "findings": f,
                 "source": TABLES["earth"]["source"]}, o.get("json"))


# ---------------------------------------------------------------- tables

def _jsonable(x):
    if isinstance(x, dict):
        return {(f"{k:g}" if isinstance(k, (int, float)) else str(k)): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def cmd_tables(argv):
    as_json = "--json" in argv
    rest = [a for a in argv if a != "--json"]
    if len(rest) > 1:
        raise Usage("Usage: electricidad tables [NAME] [--json]")
    if not rest and not as_json:
        print("Internal tables (electricidad tables NAME to see one; 'tables all' prints them all):")
        for n, t in TABLES.items():
            print(f"  {n:<24} {t['title']}" + ("" if t["verified"] else "  ❔"))
        return 0
    names = list(TABLES) if not rest or rest == ["all"] else rest
    for n in names:
        if n not in TABLES:
            raise Usage(f"No table '{n}'. Tables: {', '.join(TABLES)}.")
    if as_json:
        print(json.dumps({"as_of": AS_OF, "legend": LEGEND, "tables": {n: _jsonable(TABLES[n]) for n in names}}, ensure_ascii=False))
        return 0
    for n in names:
        t = TABLES[n]
        print(f"== {n}: {t['title']}")
        print(f"Source: {t['source']} · {'verified in a primary source' if t['verified'] else '❔ NOT VERIFIED in a primary source'} · data as of {AS_OF}")
        rows = t["rows"]
        if n == "resistance":
            print("  mm²     cu class 5   cu class 2   al class 2")
            for s in sorted(set(rows["cu5"]) | set(rows["al2"])):
                print(f"  {fmt(s):<7} {fmt(rows['cu5'].get(s), 4):>10}   {fmt(rows['cu2'].get(s), 4):>10}   {fmt(rows['al2'].get(s), 4):>10}")
        elif n == "iz_b1":
            print("  mm²     2x [A]   3x [A]")
            for s, (a2, a3) in rows.items():
                print(f"  {fmt(s):<7} {a2:>6}   {a3:>6}")
        elif n == "f_grouping":
            for k, (v, ok) in rows.items():
                print(f"  {k:>2} circuit(s): {fmt(v)}" + ("" if ok else "  ❔ (IEC, not verified in AEA)"))
        elif n == "drop_limits":
            for k, r in rows.items():
                print(f"  {k:<10} {('max. ' + fmt(r['max']) + ' %') if r['max'] is not None else '❔ no verified limit':<24} {r['desc']} [{r['rule']}]")
        elif n in ("dpms_770", "dpms_771"):
            for k, v in rows.items():
                if k == "grades":
                    for g, smax, pmax, coef in v:
                        print(f"  grade {GRADE_NAME[g]:<9} area {'up to ' + fmt(smax, 0) + ' m²' if smax else 'larger'}"
                              f"{'' if pmax is None and n == 'dpms_770' else ', DPMS ' + ('up to ' + fmt(pmax / 1000, 1) + ' kVA' if pmax else 'higher')}"
                              f", coefficient {fmt(coef)}")
                else:
                    print(f"  {k}: {fmt(v, 4) if isinstance(v, float) else v}")
        elif n == "building_diversity":
            print("  units        minimum/medium   high/superior")
            for r in rows:
                print(f"  {r[0]:<12} {fmt(r[1]):>14}   {fmt(r[2]):>13}")
        elif isinstance(rows, dict):
            for k, v in rows.items():
                print(f"  {fmt(k) if isinstance(k, float) else k}: {fmt(v, 3) if isinstance(v, float) else v}")
        else:
            print("  " + ", ".join(str(x) for x in rows))
        print(f"  Note: {t['note']}\n")
    print(LEGEND.capitalize() + ".")
    return 0


# ---------------------------------------------------------------- main

COMMANDS = {"current": cmd_current, "drop": cmd_drop, "size": cmd_size, "coordinate": cmd_coordinate, "demand": cmd_demand,
            "building": cmd_building, "earth": cmd_earth, "tables": cmd_tables, "rule": cmd_rule, "search": cmd_search}


def help_for(cmd):
    """The usage lines of one subcommand, plus the options that often confuse."""
    doc = __doc__.split("\n")
    out, on = [], False
    for ln in doc:
        if ln.startswith(f"  electricidad {cmd} ") or ln == f"  electricidad {cmd}":
            on = True
        elif on and ln.startswith("  electricidad "):
            on = False
        elif on and not ln.startswith(" " * 5):
            on = False
        if on:
            out.append(ln)
    extra = [ln for ln in doc if ln.startswith("  --")]
    return "\n".join(out + ([""] + extra if cmd in ("size", "coordinate") else []))


def cmd_plan(argv):
    """`electricidad plan ...`: handed whole to electricidad-plan (/usr/local/bin in the image, electricidad_plan.py next to this file in the repo)."""
    import os, shutil, subprocess
    exe = shutil.which("electricidad-plan") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "electricidad_plan.py")
    return subprocess.run([sys.executable, exe, *argv] if exe.endswith(".py") else [exe, *argv]).returncode


def main(argv):
    if argv and argv[0] == "plan":
        return cmd_plan(argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if argv else 2
    cmd = argv[0]
    if cmd not in COMMANDS:
        print(f"Unknown subcommand '{argv[0]}'. Subcommands: {', '.join(COMMANDS)}, plan. Help: electricidad help (or electricidad SUBCOMMAND --help)")
        return 2
    if any(a in ("-h", "--help", "help") for a in argv[1:2]):
        print(help_for(cmd) + "\nDecimals with a comma or a dot (2,5 = 2.5). Exit: 0 everything complies, 1 something does not comply, 2 invalid input.")
        return 0
    try:
        return COMMANDS[cmd](argv[1:])
    except Usage as e:
        if "--json" in argv:
            print(json.dumps({"command": cmd, "error": str(e), "as_of": AS_OF}, ensure_ascii=False))
        else:
            print(f"{e}\nUsage: electricidad {cmd} --help")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
