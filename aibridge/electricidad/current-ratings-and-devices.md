---
title: Current ratings and devices (how much each thing can carry)
scope: quick-reference tables for low-voltage site work in Argentina (220 V single-phase / 3x380 V three-phase); current-carrying capacity of copper and aluminum cables per the AEA and manufacturers' catalogs; cross-section → MCB; typical loads → current → cross-section → MCB; ratings of MCBs (PIA), RCDs, socket outlets, plugs, power strips, extension cords, switches, terminals, busbar combs and fuses
when_to_use: you need to know quickly how much a cable, an MCB, an RCD, a socket outlet or a busbar comb can carry; choose the cross-section and MCB for a load; compare a manufacturer's catalog with the AEA table; check whether what is installed is properly coordinated; someone asks "can I put a 25 A one on this cable?" or "how much can I plug into this power strip (*zapatilla*)?"
related: [README.md, conductors-and-conduits.md, protection.md, grades-and-circuits.md, panels.md, special-installations.md, troubleshooting-common-cases.md, reviewing-a-panel.md, earthing.md, testing-and-commissioning.md, site-safety.md, regulations-and-permits.md, iram-standards.md, manufacturers-and-materials.md]
as_of: 2026-11-15
sources:
  - "AEA 90364-7-771 Ed. 2006 (still the edition sold in the AEA store as of 2026-11): clause 771.16 (771.16.2.1.5 note on solar radiation; 771.16.2.3.2 factor 0.85 in sun; 771.16.2.3.4 note factor 1.07; 771.16.2.3.7; 771.16.2.3.8 busbars), tables 771.16.I, 771.16.II.a/b, 771.16.III, 771.16.V, 771.16.VI, 771.16.VII, 771.16.VIII, 771.16.IX, 771.16.X, 771.16.XI, 771.16.XII; 771.12.3.13.2 d) (circuits that may share a conduit); table 771.7.I; table 771.13.I; p. 22 note 2 (IRAM-IEC 60309, colors); notes on IRAM 2158 and IRAM NM 247-5"
  - "AEA 90364-7-770 Ed. 2017 (text consulted; the AEA lists an Ed. 2026): 770.6 (circuit types and IRAM 2071 socket outlets), table 770.6.I, 770.12, 770.15.2.2.2 to 770.15.2.2.5, annex 770-B (tables 770-B.II, VIII, IX, X)"
  - "Prysmian Argentina, technical sheets Edition 2026: Superastic Jet/Flex (IRAM NM 247-3), Sintenax Valio and Retenax Valio (IRAM 2178-1), TPR Ecoplus (IRAM NM 247-5), VN 202 (IRAM NM 247-5), Retenax Preensamblado (IRAM 2263); Edition 2020: Afumex 750 (IRAM 62267), Prysal Aislado (IRAM 63002), ar.prysmian.com"
  - "Cimet, technical sheets A2301: CC/V (IRAM NM 247-3), Zerotox 750 V (IRAM 62267); A2212: Ecoport CMXCC (IRAM 2164), cimet.com"
  - "Marlew, data sheets for series VK (IRAM NM 247-3), EK (IRAM 62267), CT (IRAM NM 247-5); Empresa (company) page of marlew.com.ar (plant in Polo Industrial Ezeiza), consulted 2026-11-15"
  - "Jeluz, Catálogo Línea Protecciones (protection line catalog, downloaded from jeluz.net in 2026-11): MCBs 3, 4.5 and 6 kA; 80-125 A (IEC 60947-2); RCDs JZ/JZX; contactors TGC1 (p. 24, note 2: Ie in AC-1 = Ith)"
  - "IET (United Kingdom), 'RCDs: selection, types and testing — webinar Q&A' (BS 7671, Reg. 531.3.2: protective conductor current ≤ 30 % of IΔn), secondary source with respect to IEC 60364-5-53"
  - "Schneider Electric Argentina, product data sheets generated on 14/15 Nov 2026: Acti9 iC60N A9F74216, Easy9 EZ9F34216, Easy9 RCCB EZ9R36240, busbar comb A9XPH212, se.com/ar"
  - "Guía práctica SRT Res. 900/2015 (SRT practical guide; RCD tests: times at IΔn, 2 IΔn, 5 IΔn)"
  - "APSE, Ingeniería Eléctrica No. 304 (Nov 2015), 'Verificaciones para realizar en conductores y protecciones' (checks to perform on conductors and protective devices; I2 = 1.45 In for PIA; 1.6 In for gG fuses; standard Icn values)"
  - "Ingeniería Eléctrica No. 327 (Dec 2017), Edenor service connection diagrams (NH bases size 1 and 3)"
  - "Res. SIyC 236/2024 (Annex II as per Res. SIyC 26/2025) and Disp. DNRT 2/2025 (requirements for socket outlets, plugs, power strips and extension cords), as summarized in regulations-and-permits.md"
  - "Wikipedia (de), 'NH-Sicherung' (DIN 43620-1 size ranges), secondary source"
---
# Current ratings and devices

"How much can it carry?" in tables: cables, MCBs (*térmicas*), RCDs (*diferenciales*), socket outlets, power strips, terminals, busbar combs and fuses. Each rule has a
stable ID (`ELEC-AMP-n`) so the agent, a report or a site report can cite it ("does not comply with ELEC-AMP-8: 25 A PIA on
2.5 mm²"). Rules are never renumbered; a withdrawn rule stays marked **Withdrawn** with a date and its replacement.

> **Warning: indicative values.** All tables are for quick reference. The design is checked against the current AEA
> table, the catalog of the product actually bought, and the real conditions (installation method,
> temperature, grouping, length, short-circuit current). If catalog and AEA differ, **for design use the lower**
> of the two: the AEA table, unless the manufacturer of the cable actually bought declares less (ELEC-AMP-1). AEA and IRAM
> standards are paid documents: here they are summarized and the table is cited; catalog numbers are reproduced citing the catalog.

**Safety first.** Measuring currents, tightening terminals, replacing an MCB (*térmica*) or a busbar comb (*peine*) is work inside the panel (distribution board, *tablero*): it is done
**dead**, isolating upstream, locking out, verifying absence of voltage and posting signs
([site-safety.md](site-safety.md)). Switching off the circuit's MCB is not enough: the MCB's incoming terminal and the busbar comb
stay live. The utility service box (*caja de toma*), the NH fuses and the service drop (*acometida*) belong to the utility (distribution company, *distribuidora*): don't touch them.

**Calculations:** the agent does not calculate from memory. It uses the offline calculator `gateway electricidad current|drop|size|coordinate|demand|building|earth|tables`
and shows the working. The worked examples here serve to check the result.

**Editions used (as of 2026-11-15):** AEA 90364-7-771 Ed. 2006 (current in the AEA store); AEA 90364-7-770, text of Ed. 2017
(the AEA lists an Ed. 2026 that was not reviewed: confirm the numbering and values in it); manufacturers' catalogs of the
editions indicated in each table. For standards and certification see [regulations-and-permits.md](regulations-and-permits.md) and
[iram-standards.md](iram-standards.md); for brands and origin, [manufacturers-and-materials.md](manufacturers-and-materials.md).

## Quick reference

| Situation | Rule |
|---|---|
| Why does the catalog give a different number than the AEA? Which one do I use? | ELEC-AMP-1 |
| How much a single-core cable in conduit can carry (1.5 to 120 mm²) | ELEC-AMP-2 |
| It is hotter, or there are several circuits in the same conduit (and which ones may share it) | ELEC-AMP-3 |
| Sheathed cable (IRAM 2178) in conduit, on cable tray, in free air or in sun | ELEC-AMP-4 |
| Buried cable (direct or in conduit) | ELEC-AMP-5 |
| Flexible cord (*tipo taller*), cord, twin parallel cord | ELEC-AMP-6 |
| Aluminum or aerial bundled service drop | ELEC-AMP-7 |
| "Can I put an X A MCB on this cable?" | ELEC-AMP-8 |
| Which cable and which MCB for an AC, water heater, oven, cooktop, pump, EV charger, electric shower | ELEC-AMP-9 |
| Ratings, B/C/D curves, when an MCB trips | ELEC-AMP-10 |
| How many kA the MCB has to break | ELEC-AMP-11 |
| Icn, Icu, Ics: which number to look at | ELEC-AMP-12 |
| MCB in a hot panel or many side by side | ELEC-AMP-13 |
| The RCD (*disyuntor* / *diferencial*) and overload; breaking capacity of the ID | ELEC-AMP-14 |
| 10, 30, 300 or 500 mA | ELEC-AMP-15 |
| AC, A, F, B, S | ELEC-AMP-16 |
| RCD trip times | ELEC-AMP-17 |
| How many circuits per RCD; leakage of appliances | ELEC-AMP-18 |
| 10 A or 20 A socket outlet | ELEC-AMP-19 |
| Power strips and extension cords (1 mm² vs 1.5 mm²) | ELEC-AMP-20 |
| Light switches | ELEC-AMP-21 |
| Which cross-section fits in the terminal of an MCB or an RCD | ELEC-AMP-22 |
| How much a busbar comb can carry | ELEC-AMP-23 |
| NH fuses | ELEC-AMP-24 |
| Rewirable fuses (*tabaquera*) | ELEC-AMP-25 |
| Does the cable withstand the short circuit until the MCB clears it? | ELEC-AMP-26 |
| Large load far from the panel: maximum length for voltage drop | ELEC-AMP-27 |
| Contactors, switch-disconnectors and motor protection circuit breakers (pumps, gates) | ELEC-AMP-28 |
| IEC 60309 industrial plugs and socket outlets (site compound, three-phase) | ELEC-AMP-29 |
| Panel copper busbars and distribution terminal blocks | ELEC-AMP-30 |

## Reference conditions: why not all tables say the same thing

### ELEC-AMP-1: A current-carrying capacity without its conditions is useless; for design, the AEA table or the catalog, whichever gives less
- **Rule:** before using a current-carrying capacity (Iz) figure, check the **installation method** (in conduit, on cable tray, buried,
  in free air, in sun), the **number of loaded conductors** (2 in single-phase, 3 in three-phase), the **reference ambient temperature**
  (30 °C or 40 °C in air; 20 °C or 25 °C in soil), the **maximum insulation temperature** (70 °C PVC/LS0H thermoplastic; 90 °C
  XLPE/EPR), the **soil resistivity**, **wind** (for overhead lines) and the **conductor class** (solid/stranded class 2 or flexible class 5).
  For the design and the technical report, use the AEA table with its correction factors. The catalog serves to
  confirm that the cable you buy is the one the table assumes; **if the manufacturer of that cable declares less current than the
  AEA under the same conditions, use the manufacturer's value** (never the higher of the two).
- **Why:** the same 2.5 mm² cable "carries" 24 A in an IEC table at 30 °C and 21 A in the AEA at 40 °C. Neither one is
  wrong: they are different conditions (24 × 0.87 ≈ 21). Mixing the number from one table with the conditions of another is the
  typical mistake that ends with a 25 A MCB on 2.5 mm².
- **How:** real differences found in Argentine catalogs (see the tables in ELEC-AMP-2 to ELEC-AMP-7):
  1. **Prysmian 2026 and Cimet (single-core cables in conduit):** same values as AEA 771 table 771.16.I, at 40 °C. They match.
  2. **Marlew (series VK and EK):** their values (2.5 mm² → 18 A) match, ±1 A, the column for **3 loaded conductors
     at 40 °C** of the AEA (table 771.16.I, column 3x), not the one for 2 loaded. Their note says "30 °C, tres cables en ductos" (three cables in ducts),
     which does not agree with the IEC: at 30 °C, the IEC B1 column for 3 loaded gives 2.5 mm² = 21 A; Marlew's numbers are that
     column multiplied by 0.87 (correction to 40 °C). Conclusion: take them as values at 40 °C with 3 loaded. If you use them
     as Iz in a single-phase circuit you are on the safe side (less current); for single-phase use the AEA column for 2 loaded.
     Don't "correct" them as if they were values at 30 °C (neither ×0.87 nor ×1.15) and don't apply other AEA factors to them
     without knowing their basis. Why the data sheet says 30 °C: **Not verified in a primary source** (it may be an error in the data sheet).
  3. **Prysmian Sintenax/Retenax (IRAM 2178) in conduit or buried:** **5 % less** than the AEA (from 1 A at 1.5 mm² up to about
     4-6 A at 25-35 mm²: B2 2x 25 mm² AEA 78 A / Prysmian 74 A; C 2x 35 mm² 120 / 114 A) because Prysmian makes those
     cross-sections with a **flexible class 5** conductor, and the AEA (notes to tables 771.16.III, 771.16.V and 771.16.VI) says to
     multiply by **0.95** when the conductor is flexible. Example: AEA D1 2x 1.5 mm² = 25 A × 0.95 = 23.75 → Prysmian 24 A.
  4. **Aluminum aerial bundled cables:** the difference goes both ways. Prysmian gives 85 A for 1x16/16 and the AEA 75 A (two-core
     16 mm²): for design, 75 A. In 3x150 + N the AEA gives 305 A and Prysmian 268 A for its cable: for design with that cable,
     268 A (the lower).
  5. **Catalogs of foreign brands** usually give IEC values at **30 °C**: multiply them by the 40 °C factor (0.87 for
     PVC) before comparing them with the AEA.
- **Verify:** in the technical report each circuit states the method, table used (AEA and number), I(table), factors, final Iz and In.
  On site, check that the cable bought is the one in the table (standard printed on the insulation: IRAM NM 247-3, 62267, 2178-1...).
- **Don't:** take the highest value you find among catalogs or between catalog and AEA; use a table at 30 °C without
  correcting it in a 40 °C zone; use the "free air" value for a cable that runs in embedded conduit.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.16.2 (design temperature 40 °C in air, 25 °C in soil, 1 K·m/W), table
  771.16.I (columns 2x and 3x), notes to tables 771.16.III, 771.16.V and 771.16.VI (factor 0.95 for class 5); Prysmian sheets
  Ed. 2026 (Superastic Jet/Flex p. 3; Sintenax Valio pp. 5-7, "condiciones establecidas en el REIEI de la AEA 90364-7-771
  (Marzo 2006)" (conditions established in the AEA REIEI)); Cimet A2301 CC/V; Marlew series VK p. 2, note (1) (1.5 = 13 A ... 120 = 207 A, "70 °C en el conductor, 30 °C
  de ambiente, tres cables en ductos" (conductor and ambient temperatures, three cables in ducts)); Prysmian Retenax Preensamblado Ed. 2026 p. 4-5, note (4); AEA 771 table 771.16.VIII.
  The relationship between Marlew's values and the IEC B1 column for 3 loaded is our own calculation.

## Copper and aluminum conductors

### ELEC-AMP-2: Single-core IRAM NM 247-3 and LS0H IRAM 62267 cables in conduit: the site table
- **Rule:** for single-core cables in embedded or surface conduit (and closed surface trunking), use the column for **2 loaded
  conductors** in single-phase circuits and the one for **3 loaded** in balanced three-phase circuits. The PE does not count as loaded; the
  neutral doesn't either if the harmonic content is below 15 %. Values for **a single circuit per conduit at 40 °C**; with more
  circuits or higher temperature apply ELEC-AMP-3.
- **Why:** in conduit little heat escapes; PVC must not exceed 70 °C in continuous service (160 °C in short circuit, 5 s). Above
  that, the insulation softens, ages and ends in a fault or a fire.
- **How:** table below. Thermoplastic LS0H (IRAM 62267) has the same maximum temperature (70 °C) and the same values.
- **Verify:** that the cable is single-core 450/750 V with the standard printed on it; that there is only one circuit in the conduit or that the
  grouping factor has been applied.
- **Don't:** use these values for flexible cords (*tipo taller*) or cords (ELEC-AMP-6); use IRAM NM 247-3 single-core cables buried,
  on cable tray or in free air as live conductors (not permitted: see [conductors-and-conduits.md](conductors-and-conduits.md)).
- **Source:** AEA 90364-7-771 Ed. 2006, 771.16.2.2 and table 771.16.I (basis: method B1, tables B52-2 and B52-4 of ch. 52);
  Prysmian Superastic Jet/Flex Ed. 2026 p. 3; Prysmian Afumex 750 Ed. 2020 p. 3; Cimet CC/V and Zerotox A2301 p. 1.

**Current-carrying capacity, copper, single-core PVC (IRAM NM 247-3) or LS0H (IRAM 62267), in conduit, 40 °C, 70 °C in the conductor [A]**

| Cross-section [mm²] | 2 loaded + PE (single-phase) [A] | 3 loaded + N + PE (three-phase) [A] | Same value at 30 °C (×1.15, 2 loaded) [A] |
|---|---|---|---|
| 1 | 11.5 | 10.5 | 13 |
| 1.5 | 15 | 14 | 17 |
| 2.5 | 21 | 18 | 24 |
| 4 | 28 | 25 | 32 |
| 6 | 36 | 32 | 41 |
| 10 | 50 | 44 | 57 |
| 16 | 66 | 59 | 76 |
| 25 | 88 | 77 | 101 |
| 35 | 109 | 96 | 125 |
| 50 | 131 | 117 | 151 |
| 70 | 167 | 149 | 192 |
| 95 | 202 | 180 | 232 |
| 120 | 234 | 208 | 269 |

Source: Prysmian, Superastic Jet/Flex sheet, Edition 2026, p. 3 (notes 1 and 2: "cables unipolares dispuestos en cañerías,
temperatura ambiente 40 °C" (single-core cables laid in conduit, at that ambient temperature); factor 1.15 for 30 °C and 1.29 for 20 °C). The values from 1.5 to 120 mm² match AEA 771
Ed. 2006 table 771.16.I and Cimet CC/V A2301. The 1 mm² value is Prysmian's only (the AEA does not allow 1 mm² in building
circuits); the calculator uses 11 A / 10 A for 1 mm² (table 770.12.I): the AEA value governs. The 30 °C column is our own calculation (×1.15) and serves **only** for comparison with catalogs at 30 °C.

**Comparison with other Argentine catalogs (same cable type)**

| Cross-section [mm²] | AEA 771 / Prysmian / Cimet, 2 loaded, 40 °C [A] | AEA 771 / Prysmian / Cimet, 3 loaded, 40 °C [A] | Marlew VK/EK, "3 cables en ducto, 30 °C" (cables in duct) per its note [A] |
|---|---|---|---|
| 1.5 | 15 | 14 | 13 |
| 2.5 | 21 | 18 | 18 |
| 4 | 28 | 25 | 24 |
| 6 | 36 | 32 | 31 |
| 10 | 50 | 44 | 43 |
| 16 | 66 | 59 | 59 |
| 25 | 88 | 77 | 77 |
| 35 | 109 | 96 | 96 |
| 50 | 131 | 117 | 116 |
| 70 | 167 | 149 | 148 |
| 95 | 202 | 180 | 180 |
| 120 | 234 | 208 | 207 |

Source: Marlew, series VK data sheet p. 2 and series EK, note (1); AEA 771 Ed. 2006 table 771.16.I (columns 2x and 3x). Marlew's
values match (±1 A) the column for 3 loaded at 40 °C: see ELEC-AMP-1. Argenplas ("Unipolar Flexible IRAM NM 247-3" sheet,
2024) shows, according to the excerpt returned by the search engine, 15/14, 21/18, 28/25 and 36/32 A for 1.5 to 6 mm² (2 and 3 loaded):
**Not verified in a primary source** (the PDF could not be opened: site certificate error).
### ELEC-AMP-3: Correct for temperature and grouping before choosing the MCB (*térmica*)
- **Rule:** Iz = I(table) × Ft × Fa. Ft corrects the ambient temperature when it differs from the reference one **for permanent
  reasons** (location, roof space, plant room); Fa corrects for several circuits in the same conduit, cable tray or trench.
  **Before applying Fa, check whether those circuits may share the conduit:** in buildings, general-use, special-use and
  specific-use circuits run in separate conduits; only **general-use** circuits may be grouped, **up to 3**, and
  with three conditions at once: (1) same phase and same panel (distribution board, *tablero*); (2) sum of the In of their protective devices **≤ 36 A**; (3) **15
  outlet points** (*bocas*) at most among all of them. Details in [conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-10.
- **Why:** two circuits in one conduit heat each other; a cable under a metal roof in summer works at 50 °C ambient. In
  both cases the cable reaches 70 °C with less current. The 36 A cap limits the total heat in the conduit and prevents a
  short circuit or work on one circuit from reaching other, more heavily loaded ones.
- **How:**
  - The AEA does **not** accept taking a lower temperature because there is air conditioning or fans (they can fail), unless
    failure of that equipment takes that installation out of service.
  - Permitted example: 3 general-use circuits of 2.5 mm² in one conduit at 40 °C, with 10 A MCBs → ΣIn = 30 A ≤ 36 A;
    Iz = 21 × 1 × 0.70 = 14.7 A ≥ 10 A. Complies. With 13 + 13 + 10 A (ΣIn = 36 A) it also complies (14.7 ≥ 13).
  - **Not permitted** example: 3 × 13 A = 39 A > 36 A, even though each cable carries 14.7 A. Nor 3 × 16 A (48 A).
  - With 2 general-use circuits of 2.5 mm²: Iz = 21 × 0.80 = 16.8 A → 16 A each (ΣIn = 32 A ≤ 36 A). Complies.
  - An air conditioner (AC), an oven on a TUE, a cooktop, an electric shower or a charger (special or specific use) run **in their own conduit**: for them
    Fa = 1 in conduit, and grouping only appears on cable tray, in a trench or with conduits in contact.
  - Heat example: 4 mm² in a roof space at 50 °C, one circuit: Iz = 28 × 0.82 = 23 A → maximum MCB 20 A (not 25 A).
- **Verify:** in the technical report, Ft and Fa per circuit; on site, count circuits per conduit, add up the In of those sharing a
  conduit (≤ 36 A), count outlet points (≤ 15), confirm they are general-use and on the same phase, and look for hot sections.
- **Don't:** apply Fa = 1 "because the circuits are not used at the same time"; correct upward because "in winter it is cold";
  use the 0.80 or 0.70 factor to "allow" two special-use or specific-use circuits in the same conduit.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.16.2.1.5 (note 1 and exception), table 771.16.II.a (based on B52-14), table
  771.16.II.b (based on B52-17 item 1) and 771.12.3.13.2 d) (p. 82: up to three general-use circuits, same phase and panel,
  ΣIn ≤ 36 A, ≤ 15 outlet points); AEA 90364-7-770 Ed. 2017, 770.10.3.8.2 (same rule, per ELEC-CON-10); Prysmian Superastic
  Ed. 2026 p. 3 (0.80 and 0.70 for 2 and 3 circuits).

**Air ambient temperature factor, 40 °C base (cables in air or in conduit in air)**

| Ambient [°C] | 20 | 25 | 30 | 35 | 40 | 45 | 50 | 55 | 60 |
|---|---|---|---|---|---|---|---|---|---|
| PVC / thermoplastic LS0H (70 °C) | 1.29 | 1.22 | 1.15 | 1.08 | 1.00 | 0.91 | 0.82 | 0.70 | 0.57 |
| XLPE / EPR (90 °C) | 1.19 | 1.14 | 1.10 | 1.05 | 1.00 | 0.96 | 0.90 | 0.84 | 0.78 |

Source: AEA 771 Ed. 2006 table 771.16.II.a (extract from 20 to 60 °C; the table runs from 10 to 80 °C).

**Grouping factor in one conduit (single-core cables, ELEC-AMP-2 table)**

| Circuits in the conduit | 1 | 2 | 3 |
|---|---|---|---|
| Single-phase (up to 4 / 6 loaded conductors) | 1.00 | 0.80 | 0.70 |
| Three-phase (up to 6 / 9 loaded conductors) | 1.00 | 0.80 | 0.70 |

Source: AEA 771 Ed. 2006 table 771.16.II.b; Prysmian Superastic Ed. 2026 p. 3. In buildings, the 2- and 3-circuit row is only
used for general-use circuits within the conditions of 771.12.3.13.2 d) (in practice 1.5 and 2.5 mm²). Since
"same phase" is a condition, two three-phase circuits do not share a conduit in a building: the three-phase row remains as data from the
AEA table.

### ELEC-AMP-4: Sheathed cables IRAM 2178 (Sintenax, Retenax) in conduit, on cable tray or in free air
- **Rule:** 0.6/1 kV insulated and sheathed cables (IRAM 2178-1; LS0H IRAM 62266) have their own tables by method:
  **B2** (multicore in conduit), **C** (unperforated cable tray or on a wall, touching), **E** (perforated cable tray or ladder,
  multicore), **F/G** (single-core on perforated cable tray, touching or spaced). Choose the column by method and loaded
  conductors; PVC at 70 °C (Sintenax) or XLPE at 90 °C (Retenax).
- **Why:** a multicore cable in conduit dissipates worse than loose single-core cables; on perforated cable tray it dissipates better. XLPE allows
  90 °C, so for the same cross-section and method it carries on the order of 30 to 45 % more than PVC (comparing the
  Sintenax and Retenax columns below).
- **How:** tables below (copper, 40 °C). For several cables on the same cable tray, factors from AEA table 771.16.IV.
  - **In sun:** for cables directly exposed to solar radiation, AEA 771 (771.16.2.3.2) requires an **additional factor
    of 0.85** on the current-carrying capacity, in addition to the temperature factor (table 771.16.II.a). The general note of 771.16.2.1.5
    adds that the table factors do not include radiation and allows calculating per IEC 60287, with justification in the technical report.
  - Example: Sintenax 3x4 mm² (three-phase, 3 loaded) on perforated cable tray in sun, ambient 40 °C: Iz = 29 × 0.85 = 24.7 A
    → maximum four-pole MCB 20 A (25 A > 24.7 A). If the cable tray is also at 45 °C: 29 × 0.91 × 0.85 = 22.4 A → 20 A.
  - In locations with explosion risk (BE3) the AEA requires another additional factor of 0.85 (771.16.2.3.2, note 9 of table 771.16.IV).
- **Verify:** actual installation method; if cable tray, its type (perforated or not); whether it is in sun; conductor class
  (flexible: ×0.95).
- **Don't:** use column E (perforated cable tray) for a cable that runs in conduit; put IRAM NM 247-3 single-core cables on cable tray;
  forget the 0.85 on a rooftop cable tray or a run along a sunny facade.
- **Source:** AEA 771 Ed. 2006, 771.16.2.3.1 and table 771.16.III (B2, C, E); 771.16.2.3.2 (table 771.16.IV, note 9: BE3, 0.85; p. 101: "factor
  de corrección adicional de 0,85" (additional correction factor) for cables directly exposed to solar radiation); 771.16.2.1.5 note (solar
  radiation and IEC 60287); Prysmian Sintenax Valio Ed. 2026 pp. 5-6 and Retenax Valio Ed. 2026 (equivalent tables, 90 °C).

**Copper, sheathed cables, 40 °C. PVC = Sintenax Valio (70 °C); XLPE = Retenax Valio (90 °C) [A]**

| Cross-section [mm²] | B2 conduit, 2 loaded PVC | B2 conduit, 3 loaded PVC | C unperforated tray / wall, 2 loaded PVC | E perforated tray, 3 loaded PVC | B2 conduit, 2 loaded XLPE | E perforated tray, 3 loaded XLPE |
|---|---|---|---|---|---|---|
| 1.5 | 13 | 12 | 16 | 15 | 19 | 20 |
| 2.5 | 19 | 16 | 22 | 21 | 26 | 28 |
| 4 | 25 | 22 | 29 | 29 | 34 | 36 |
| 6 | 31 | 29 | 38 | 35 | 44 | 47 |
| 10 | 43 | 38 | 52 | 49 | 60 | 65 |
| 16 | 57 | 51 | 70 | 67 | 79 | 86 |
| 25 | 74 | 67 | 92 | 84 | 103 | 110 |
| 35 | 92 | 82 | 114 | 105 | 126 | 137 |
| 50 | — | 103 | 146 | 133 | 159 | 175 |
| 70 | — | 130 | 185 | 171 | 201 | 224 |
| 95 | — | 156 | 224 | 207 | 241 | 271 |
| 120 | — | 179 | 260 | 240 | 278 | 315 |

Source: Prysmian Sintenax Valio Ed. 2026 p. 5 (columns 1, 2, 3, 6) and Retenax Valio Ed. 2026 (columns B2-1 and E-6). In AEA
771 table 771.16.III the PVC values are 5 % higher (e.g. B2 2x 1.5 mm² = 14 A; B2 2x 25 mm² = 78 A; E 3x 35 mm² = 110 A)
because they assume a solid/stranded conductor; see ELEC-AMP-1.

### ELEC-AMP-5: Buried cables: direct (D2) or in conduit (D1), at 25 °C soil and 1 K·m/W
- **Rule:** only sheathed cables (IRAM 2178-1 / 62266) may be buried, at a reference depth of 0.70 m. Correct for
  soil temperature, soil thermal resistivity and grouping of cables or conduits.
- **Why:** dry or sandy soil dissipates much worse; two cables together in the same trench heat each other. In very
  dry ground a directly buried cable can lose a third of its capacity (factor 0.67 at 2.5 K·m/W, table
  771.16.VII b).
- **How:** tables below. Example: 4 mm² multicore in buried conduit, 2 loaded, dry ground (1.5 K·m/W), soil at 25 °C,
  alone: Iz = 41 × 0.93 = 38 A. With another conduit touching it (Fa 0.85 for conduits with multicore cable): 38 × 0.85 = 32 A.
- **Verify:** type of ground (dry sand backfill = unfavorable), number of cables in the trench, depth, conduit.
- **Don't:** bury IRAM NM 247-3 single-core cables even "inside a conduit"; ignore grouping with the pump line
  that runs in the same trench.
- **Source:** AEA 771 Ed. 2006, 771.16.2.3.3 to 771.16.2.3.5 (note to 771.16.2.3.4: factor 1.07 for single-core cables spaced
  one diameter apart), tables 771.16.V (D1), 771.16.VI (D2, copper and aluminum) and 771.16.VII a) to d); Prysmian Sintenax Valio Ed. 2026
  p. 7 and Retenax Valio Ed. 2026 (D1 and D2).

**Copper, buried, soil 25 °C, 1 K·m/W, 0.70 m [A]** (Prysmian, flexible conductor up to 35 mm²; the 0.95 is already included)

| Cross-section [mm²] | D1 buried conduit, multicore 2 loaded PVC | D1 buried conduit, multicore 3 loaded PVC | D2 direct, 3 single-core touching PVC | D2 direct, multicore 2 loaded PVC | D2 direct, multicore 3 loaded PVC | D1 conduit, 2 loaded XLPE | D2 direct, multicore 3 loaded XLPE |
|---|---|---|---|---|---|---|---|
| 1.5 | 24 | 19 | 29 | 28 | 24 | 28 | 28 |
| 2.5 | 31 | 26 | 37 | 37 | 32 | 37 | 37 |
| 4 | 41 | 33 | 48 | 48 | 42 | 48 | 48 |
| 6 | 50 | 42 | 60 | 62 | 52 | 60 | 61 |
| 10 | 67 | 55 | 80 | 84 | 70 | 79 | 83 |
| 16 | 86 | 71 | 103 | 106 | 90 | 101 | 107 |
| 25 | 111 | 91 | 133 | 137 | 117 | 130 | 141 |
| 35 | 133 | 109 | 160 | 164 | 140 | 157 | 168 |

Source: Prysmian Sintenax Valio Ed. 2026 p. 7 (notes 12 to 16) and Retenax Valio Ed. 2026 (D1 col. 12 and D2 col. 16). Solid/stranded
conductor (AEA 771 tables 771.16.V and 771.16.VI): divide by 0.95 (e.g. D1 2x 1.5 mm² = 25 A in the AEA).

**Corrections for buried cables (extract)**

| Condition | Value → PVC factor | Source |
|---|---|---|
| Soil temperature | 20 °C → 1.05; 25 °C → 1.00; 30 °C → 0.94; 35 °C → 0.88; 40 °C → 0.81 | AEA 771 table 771.16.VII a) |
| Thermal resistivity, cables in conduit | 0.8 K·m/W (moist) → 1.02; 1 → 1.00; 1.5 (dry) → 0.93; 2.5 → 0.85 | AEA 771 table 771.16.VII b) |
| Thermal resistivity, directly buried | 0.8 → 1.08; 1 → 1.00; 1.5 → 0.85; 2.5 → 0.67 | AEA 771 table 771.16.VII b) |
| Directly buried circuits touching | 2 → 0.75; 3 → 0.65; 4 → 0.60 | AEA 771 table 771.16.VII c) |
| Conduits touching, one multicore per conduit | 2 → 0.85; 3 → 0.75; 4 → 0.70 | AEA 771 table 771.16.VII d1) |
| Directly buried single-core cables, spaced at least one diameter apart | × 1.07 on table 771.16.VI | AEA 771 771.16.2.3.4, note |

**Sheathed aluminum (IRAM 2178 / 62266) directly buried, soil 25 °C, 1 K·m/W, 0.70 m, solid/stranded conductor [A]** (extract,
for long feeders on country properties (*quintas*), large lots or sheds (*galpones*))

| Cross-section [mm²] | PVC, single-core | PVC, multicore 3 loaded | XLPE, single-core | XLPE, multicore 3 loaded |
|---|---|---|---|---|
| 16 | 84 | 73 | 98 | 88 |
| 25 | 109 | 94 | 128 | 115 |
| 35 | 130 | 113 | 153 | 137 |
| 50 | 153 | 135 | 180 | 162 |
| 95 | 226 | 202 | 265 | 239 |

Source: AEA 771 Ed. 2006 table 771.16.VI (aluminum, columns "1x" and "3x"; extract). Corrections: those in the table above.
Al-Cu joints only with bimetallic connectors (ELEC-CON-22). Compared with copper, 25 mm² single-core PVC aluminum (109 A)
carries the same as 16 mm² copper (108 A in the same table).

### ELEC-AMP-6: Flexible cord (*tipo taller*), cords and twin parallel cord: for connecting equipment, not for fixed wiring
- **Rule:** the "tipo taller" cable (sheathed flexible cord, today **IRAM NM 247-5** type 247 NM 53, H05VV-F 300/500 V;
  in practice it replaced the old **IRAM 2158**) and the "paralelo" (flat unsheathed cord, figure-eight profile, IRAM NM 247-5 type
  **247 NM 42**, equivalent to the harmonized H03VH-H, 300/300 V; the Prysmian sheet designates it H03V-F) are for supplying mobile
  or removable appliances: an appliance cord, an extension cord, a luminaire with a plug. They are not used in fixed wiring or on
  cable trays. Their current-carrying capacity is **lower** than that of a single-core cable in conduit of the same cross-section.
- **Why:** a 300/500 V cord with fine strands; the AEA and the manufacturer give low values (1.5 mm² = 10 A and 2.5 mm² =
  16 A at 40 °C) because it is used coiled, stepped on and on hot surfaces.
- **How:** table below. A 1 mm² extension cord carries 7 A (≈ 1500 W); a 1.5 mm² one, 10 A (2200 W), which is the limit of
  a 10 A plug. The twin parallel cord, according to the manufacturer's sheet, is only for lighting fittings and small,
  light appliances (citing IRAM 2092, the sheet says it is not suitable for supplying appliances in general): no heaters,
  irons, kettles or anything drawing more than a few amperes. It cannot be run exposed without mechanical protection.
- **Verify:** printed marking: tipo taller, "247 NM 53" on the sheath; paralelo, "247 NM 42" on the insulation; cross-section against
  the load; that it is not used as fixed wiring (ELEC-CON-3).
- **Don't:** wire a fixed circuit with tipo taller cord "because it is tougher"; supply a fan heater or a space heater with
  paralelo cord; use a 1 mm² extension cord for an electric oven.
- **Source:** AEA 771 Ed. 2006, 771.12 (list of what is not permitted, item l, notes 4 and 5: "IRAM NM 247-5 han reemplazado, en la
  práctica, a aquellos que responden a la Norma IRAM 2158" (the former have in practice replaced cables to the older standard)), 771.12.3.9.2 (not on cable trays), 771.16.2.3.7 and table 771.16.XI
  (p. 111: flexible cables in air at 40 °C, 3/4/5 conductors: 2.5 mm² = 16 A; 4 = 22 A; 6 = 30 A; 10 = 40 A; only for
  connecting mobile or portable equipment); Prysmian TPR Ecoplus Ed. 2026 pp. 2-3 (marking "NM 247-53 C5"); Prysmian VN
  202 Ed. 2026 pp. 2-3 (marking "247 NM 42-C5"; "artefactos de iluminación y pequeños aparatos" (lighting fittings and small appliances)); Marlew series CT (IRAM NM
  247-5, no current data). **Not verified in a primary source:** the equivalence 247 NM 42 ≈ H03VH-H (harmonized
  designation system, from prior knowledge).

**Copper flexible cords, PVC 70 °C, ambient temperature 40 °C [A]**

| Cross-section [mm²] | AEA table 771.16.XI, 3/4/5 conductors [A] | Tipo taller TPR Ecoplus 2 or 3 conductors [A] | Tipo taller 4 conductors [A] | Paralelo VN 202 2 conductors [A] |
|---|---|---|---|---|
| 0.5 | — | — | — | 3 |
| 0.75 | — | — | — | 5 |
| 1 | — | 7 | 7 | 7 |
| 1.5 | — | 10 | 10 | 10 |
| 2.5 | 16 | 16 | 16 | — |
| 4 | 22 | 22 | 22 | — |
| 6 | 30 | 30 | 30 | — |
| 10 | 40 | 45 (2x) / 40 (3x) | 40 | — |

Source: AEA 771 Ed. 2006 table 771.16.XI (p. 111, air at 40 °C); Prysmian TPR Ecoplus Ed. 2026 p. 3, note (1) "válida para
temperatura ambiente de 40 °C" (valid for that ambient temperature); Prysmian VN 202 Ed. 2026 p. 3. Where both give a value, they match (except 10 mm² two-core, which the
AEA does not list).

### ELEC-AMP-7: Service drops (*acometidas*) and aluminum aerial bundled cables: they belong to the utility; for design, the lower of AEA and manufacturer
- **Rule:** the overhead service drop (aluminum aerial bundled cable IRAM 2263, or copper concentric/aerial bundled cable IRAM 2164) is defined
  and installed by the utility (distribution company, *distribuidora*). If you have to check your own overhead run (for example, to a shed or a back house),
  use the AEA table for aerial bundled cables (40 °C, in sun, no wind, 90 °C in the conductor), correct for temperature and
  grouping, and compare with what the manufacturer of the cable you actually buy declares: **for design, the lower of the
  two** (ELEC-AMP-1). Every aluminum-copper joint is made with a bimetallic connector (ELEC-CON-22).
- **Why:** aluminum conducts less than copper (for the same current, more cross-section is needed) and it oxidizes and creeps in ordinary
  terminals: a direct Al-Cu splice overheats.
- **How:** table below. Example: shed with four-core aluminum aerial bundled cable 3x16+N at 45 °C: Iz = 60 × 0.95 = 57 A →
  maximum four-pole MCB 50 A. Large example: Prysmian 3x1x150/70 → 268 A (manufacturer) versus 305 A (AEA): with that cable,
  Iz = 268 A at 40 °C, and the protective device does not exceed 268 A (adjustable circuit breaker with Ir ≤ 268 A; a 300 A one won't do).
- **Verify:** cross-section and material of each phase and of the messenger neutral; bimetallic connectors; that your own run has not been
  hung from the utility's service drop.
- **Don't:** touch or splice the utility's service drop; splice Al to Cu by twisting; use the higher value
  when catalog and AEA differ; compare values calculated with wind against the AEA table (no wind).
- **Source:** AEA 771 Ed. 2006, 771.16.2.3.6, tables 771.16.VIII, 771.16.IX and 771.16.X; Prysmian Retenax Preensamblado Ed. 2026
  p. 4 (note 4: a single cable in sun, 1000 W/m², 40 °C, 90 °C, no wind); Prysmian Prysal Aislado Ed. 2020 p. 3; Cimet Ecoport
  CMXCC A2212 p. 1.

**Aerial bundled cables and service drops, 40 °C, in sun, no wind, 90 °C in the conductor [A]**

| Formation | AEA 771 table 771.16.VIII [A] | Catalog [A] | Catalog | For design (the lower) [A] |
|---|---|---|---|---|
| Copper 2x4 | 45 | 45 | Cimet CMXCC 2x4 | 45 |
| Copper 2x6 | 55 | 55 | Cimet CMXCC 2x6 | 55 |
| Copper 2x10 | 70 | 70 | Cimet CMXCC 2x10 | 70 |
| Copper 2x16 | — (not listed) | 90 | Cimet CMXCC 2x16 | 90 (catalog only) |
| Copper 4x4 | 35 | 35 | Cimet CMXCC 4x4 | 35 |
| Copper 4x6 | 45 | 45 | Cimet CMXCC 4x6 | 45 |
| Copper 4x10 | 55 | 55 | Cimet CMXCC 4x10 | 55 |
| Copper 4x16 | 75 | 75 | Cimet CMXCC 4x16 | 75 |
| Aluminum two-core 16 (1x16/16) | 75 | 85 | Prysmian Retenax Preensamblado | 75 |
| Aluminum four-core 3x16 + N | 60 | 60 | Prysmian (3x1x16/16) | 60 |
| Aluminum four-core 3x35 + N | 96 | 103 | Prysmian (3x1x35/50) | 96 |
| Aluminum four-core 3x50 + N | 117 | 124 | Prysmian (3x1x50/50) | 117 |
| Aluminum four-core 3x95 + N | 200 | 200 | Prysmian (3x1x95/50) | 200 |
| Aluminum four-core 3x150 + N | 305 | 268 | Prysmian (3x1x150/70) | 268 |

Source: AEA 771 Ed. 2006 table 771.16.VIII (p. 110: 40 °C, exposed to sun, zero wind, 90 °C; transcription of the
3x150 = 305 A value checked against the table); Cimet CMXCC A2212 p. 1 (note 1); Prysmian Retenax Preensamblado Ed. 2026 pp. 4-5, note
(4) (a single cable in sun, 1000 W/m², 40 °C, 90 °C, no wind).

**Another case, not comparable with the table above:** Prysmian Prysal Aislado (aluminum alloy, IRAM 63002), single-core
16 / 25 / 35 mm² = 102 / 136 / 166 A, but with **wind of 0.6 m/s and 80 °C in the conductor** (Prysal Aislado Ed. 2020 p. 3,
note 1: 40 °C, 1000 W/m²). With wind the cable cools more, so those numbers are not comparable with the AEA (zero wind).

Temperature correction for aerial bundled cables (AEA table 771.16.IX): 30 °C → 1.10; 35 °C → 1.05; 40 °C → 1.00; 45 °C → 0.95;
50 °C → 0.89. Grouping of aerial bundled cables in the same plane (table 771.16.X): 2 cables → 0.89; 3 → 0.80. The differences
between catalogs and the AEA are not explained in the documents (possibly differences in calculation model or in the messenger neutral).
## From cross-section to MCB

### ELEC-AMP-8: Ib ≤ In ≤ Iz, plus the cap for the circuit type
- **Rule:** the circuit's design current (Ib) ≤ rated current of the MCB (*térmica*) (In) ≤ corrected current-carrying capacity
  of the cable (Iz). With IEC 60898-1 MCBs the second condition (I2 ≤ 1.45 Iz) is met automatically because I2 = 1.45 In. In addition, the
  MCB cannot exceed the AEA **maximum for the circuit type**, even if the cable carries more.
- **Why:** the MCB protects **the cable**, not the appliance. If In > Iz, the cable can run overloaded for hours
  without the MCB tripping.
- **How:** the rating is the standard value immediately **below or equal to** the corrected Iz. Table below (copper, single-core in
  conduit, 40 °C). From 80 to 125 A there are modular MCBs on DIN rail (generally under IEC 60947-2, e.g. Jeluz 80/100/125 A);
  above 125 A they are molded-case circuit breakers (IEC 60947-2), often adjustable: set Ir ≤ Iz. The table
  also assumes that the cable withstands the short circuit until the MCB clears it (ELEC-AMP-26) and that the voltage drop is within limits
  (ELEC-AMP-27).
- **Verify:** in the panel (distribution board, *tablero*), compare the rating of each MCB with the cross-section leaving it (look at the cable, not the
  drawing); that no IUG has more than 16 A and no TUG more than 20 A; that the MCB of a TUE does not exceed the rating of its
  socket outlets.
- **Don't:** "upsize" the MCB because it trips (ELEC-PRO-6); put 16 A on 1.5 mm² (Iz = 15 A); put 25 A on 2.5 mm².
- **Source:** AEA 770 Ed. 2017, 770.15.3 and table 770-B.I (Ib ≤ In ≤ Iz; I2 ≤ 1.45 Iz "siempre verifica" (always satisfied) with IEC 60898-1); AEA
  771 Ed. 2006 table 771.7.I and AEA 770 table 770.6.I (maximums per circuit type); Iz from ELEC-AMP-2 and ELEC-AMP-3; APSE,
  Ingeniería Eléctrica No. 304 (Nov 2015) (I2 = 1.45 In for In ≤ 63 A).

**Cross-section → maximum MCB for the cable (copper, single-core IRAM NM 247-3 / 62267 in conduit, 40 °C) [A]**

| Cross-section [mm²] | Iz 1 single-phase circuit | Max. PIA 1 circuit | Iz three-phase 1 circuit → max. PIA | At 45 °C, 1 single-phase circuit (×0.91) → max. PIA |
|---|---|---|---|---|
| 1.5 | 15 | 13 (10 if 13 is not available) | 14 → 13 | 13.7 → 13 |
| 2.5 | 21 | 20 | 18 → 16 | 19.1 → 16 |
| 4 | 28 | 25 | 25 → 25 | 25.5 → 25 |
| 6 | 36 | 32 | 32 → 32 | 32.8 → 32 |
| 10 | 50 | 50 (40 recommended) | 44 → 40 | 45.5 → 40 |
| 16 | 66 | 63 | 59 → 50 | 60.1 → 50 |
| 25 | 88 | 80 (modular) | 77 → 63 | 80.1 → 80 |
| 35 | 109 | 100 (modular) | 96 → 80 | 99.2 → 80 |
| 50 | 131 | 125 (modular IEC 60947-2) | 117 → 100 | 119.2 → 100 |
| 70 | 167 | 160 (molded case) | 149 → 125 | 152 → 125 |
| 95 | 202 | 200 (molded case) | 180 → 160 | 183.8 → 160 |
| 120 | 234 | 200, or adjustable ≤ 234 | 208 → 200 | 212.9 → 200 |

Source: our own calculation with Iz from ELEC-AMP-2 and factors from ELEC-AMP-3; standard ratings from ELEC-AMP-10. The one-circuit
column matches the "Sección → PIA máximo" (cross-section → maximum PIA) table in [protection.md](protection.md).

**Several circuits in the same conduit: general-use only, up to 3, ΣIn ≤ 36 A, ≤ 15 outlet points (*bocas*), same phase and panel (ELEC-AMP-3)**

| Cross-section [mm²] | 2 circuits: Iz (×0.80) → max. PIA per cable | Fits within 36 A? | 3 circuits: Iz (×0.70) → max. PIA per cable | Fits within 36 A? |
|---|---|---|---|---|
| 1.5 | 12 → 10 A | 10 + 10 = 20 A: yes | 10.5 → 10 A | 3 × 10 = 30 A: yes |
| 2.5 | 16.8 → 16 A | 16 + 16 = 32 A: yes | 14.7 → 13 A | 3 × 13 = 39 A: **no**. Yes with 13 + 13 + 10 (36 A) or 3 × 10 (30 A) |
| 4 | 22.4 → 20 A | 20 + 20 = 40 A: **no**. Yes with 20 + 16 (36 A) | 19.6 → 16 A | 3 × 16 = 48 A: **no**. Yes with 16 + 10 + 10 (36 A) |
| 6 or more | — | Circuits of that current are special-use or specific-use, or sub-mains: they run in their own conduit (ELEC-CON-10) | — | — |

Source: AEA 771 Ed. 2006 771.12.3.13.2 d) and table 771.16.II.b; our own calculations. The cap for the circuit type also governs
(next table): a TUG does not exceed 20 A nor an IUG 16 A.

**Cap per circuit type (the lower of this cap and the previous table governs)**

| Circuit | Code | Minimum cross-section [mm²] | Maximum MCB [A] | Load per socket outlet or outlet point |
|---|---|---|---|---|
| General-use lighting | IUG | 1.5 | 16 | up to 10 A per outlet point |
| General-use socket outlets | TUG | 2.5 | 20 | up to 10 A, 2P+E 10 A IRAM 2071 socket outlet |
| Special-use lighting | IUE | 2.5 | 32 | — |
| Special-use socket outlets | TUE | 2.5 | 32 (AEA cap); **with 2P+E 20 A IRAM 2071 socket outlets, 20 A; with 16 A IEC 60309 socket outlets, 16 A** | up to 20 A, 2P+E 20 A IRAM 2071 socket outlet (or 16 A IEC 60309) |
| Small motor supply | APM | 2.5 | 25 | — |
| MBTF sources | MBTF | 1.5 | 20 | — |
| Single load and other specific circuits | ACU, OCE | by calculation (≥ 2.5) | designer's responsibility (Ib ≤ In ≤ Iz) | one load |

Source: AEA 771 Ed. 2006 table 771.7.I (maximum outlet points and protection) and table 771.13.I (MBTF 1.5 mm²; other specific circuits
2.5 mm²); AEA 770 Ed. 2017 770.6 a) and b) and table 770.6.I (IUG 16 A, TUG 20 A, TUE 32 A; IRAM 2071 socket outlets). Minimum cross-sections:
[conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-5. With 1.5 mm² the IUG stays at 10 A (or 13 A): the
16 A one requires 2.5 mm². **Safety criterion (not AEA text):** the 32 A cap for the TUE does not authorize protecting a 20 A socket outlet
with 32 A. With unfused plugs, like the Argentine ones, a 25-30 A load on a 20 A socket outlet does not trip a
32 A MCB and the socket outlet melts (ELEC-AMP-19). If the circuit has socket outlets, the MCB does not exceed the socket outlet's rating.

**Quick reference: minimum cross-section of the protective conductor (PE) according to the phase (copper)**

| Phase cross-section S [mm²] | Minimum PE [mm²] | Example |
|---|---|---|
| S ≤ 16 | S (never less than 2.5) | phase 6 → PE 6; phase 1.5 (IUG) → PE 2.5 |
| 16 < S ≤ 35 | 16 | phase 25 → PE 16 |
| S > 35 | S / 2 | phase 70 → PE 35 |

Source: AEA 770 Ed. 2017 table 770.14.I, per [conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-6
(which also covers the earthing conductor, minimum 4 mm²). The PE does not count as a loaded conductor for current-carrying capacity.

### ELEC-AMP-9: From the appliance's power to current, cross-section and MCB (*térmica*) (typical loads)
- **Rule:** the current comes from the appliance's **nameplate** (rated and maximum current). If you only have the power: single-phase
  I = P / (U × cos φ); three-phase I = P / (√3 × U × cos φ). Then: Ib ≤ In ≤ Iz (ELEC-AMP-8), the circuit type
  (ELEC-AMP-8) and the voltage drop ([conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-9).
- **Why:** an appliance over 10 A does not go on a 10 A socket outlet; a continuous load (water heater, EV charger, electric shower)
  runs at maximum for hours and punishes terminals, plugs and MCBs.
- **How:** table below, at 220 V, one circuit per conduit, 40 °C, copper, single-core in conduit. Calculations shown in each row.
  - **Air conditioners:** thermal power = frigories × 1.163 W; electrical power = thermal / EER. EER = 3.2 and
    cos φ = 0.95 were used (same as [special-installations.md](special-installations.md) ELEC-ESP-10). With a less
    efficient unit (EER 2.6) the current goes up 23 %. **That calculation gives the rated cooling current and serves only as a check:**
    the design Ib (for the cross-section, the MCB and the demand on the main line) is the **maximum nameplate current**,
    which in inverter units is usually considerably higher than the rated one (heating with cold outdoor air, startup at maximum frequency). If
    the maximum nameplate current exceeds about 11 A, whatever the size of the unit: 4 mm² and C 20 A (ELEC-ESP-11).
  - **Single-phase pumps:** shaft power = HP × 746 W; efficiency 0.6 and cos φ 0.8 were assumed (small motors). The
    startup draws on the order of 4 to 7 times the rated current for fractions of a second; a C curve (5-10 In) usually copes.
  - **EV charger (Mode 3):** the charger draws the current it is configured for (16 A or 32 A), not exactly "3,7 / 7,4 kW":
    at 220 V, 16 A = 3.5 kW and 32 A = 7.0 kW. Diversity (simultaneity) factor 1.
  - **Continuous load (hours at full current):** the AEA requires Ib ≤ In; as a practical criterion (not AEA) it is advisable to leave a margin
    (Ib ≤ 0.8 In) because the MCB is calibrated at 30 °C and the panel is usually hotter (ELEC-AMP-13). An induction
    cooktop cycles (the zones regulate by pulses and are almost never all at maximum at once), so it is accepted that it runs
    close to In; the electric shower, the water heater and the EV charger don't cycle.
  - **Own conduit:** AC, oven on a TUE, cooktop, electric shower, charger and pump are special-use or specific-use circuits: they run in their own
    conduit and don't share a conduit with other circuits (ELEC-AMP-3), so the table uses one circuit per conduit.
  - **Length:** with large loads far from the panel, voltage drop governs: maximum lengths in ELEC-AMP-27.
- **Verify:** nameplate (rated current, maximum current and protective device recommended by the manufacturer: if the manual calls for a larger cross-section or
  a lower rating, the manual governs); RCD (*disyuntor* / *diferencial*) type (A for inverter, induction, charger: ELEC-AMP-16).
- **Don't:** size an AC by frigories as if they were watts; plug an appliance over 10 A into a 10 A socket outlet;
  supply an electric shower or an induction cooktop through a socket outlet and plug.
- **Source:** AEA 770 Ed. 2017 770.6 (limits of 10 A and 20 A per socket outlet; TUE ≤ 32 A) and 770.15.3; AEA 771 table 771.7.I (ACU);
  AEA 90364-7-722:2024 (factor 1 for chargers, per [special-installations.md](special-installations.md) ELEC-ESP-17);
  1 kcal/h = 1.163 W; 1 HP = 745.7 W. **Not verified in a primary source:** EER, efficiencies and cos φ (typical values; the nameplate
  governs); the 0.8 margin for continuous loads is a practical criterion.

**Typical loads, 220 V single-phase → current → cross-section → MCB (copper, single-core in conduit, 40 °C, one circuit)**

| Load | Calculation | Ib [A] | Circuit | Cross-section [mm²] | MCB (two-pole) | Notes |
|---|---|---|---|---|---|---|
| 15 LED lighting outlet points of 12 W | 180 W / (220 × 0.9) | 0.9 | IUG | 1.5 | 10 A (B or C) | Max. 15 outlet points per IUG |
| TUG (2200 VA design value) | 2200 / 220 | 10.0 | TUG | 2.5 | 16 A (20 A if alone in the conduit) | 2200 VA is a demand value, not one appliance |
| AC 2250 fg | 2250 × 1.163 = 2617 W; / 3.2 = 818 W; / (220 × 0.95) | 3.9 | own or TUE | 2.5 | C 16 A (or what the manual calls for) | Inverter → type A ID |
| AC 3000 fg | 3489 W thermal → 1090 W electrical | 5.2 | own or TUE | 2.5 | C 16 A | |
| AC 4500 fg | 5234 W → 1636 W | 7.8 | own | 2.5 | C 16 A | With EER 2.6: 9.6 A |
| AC 6000 fg | 6978 W → 2181 W | 10.4 | own | 2.5 | C 16 A; if the maximum nameplate current exceeds ~11 A: 4 mm² and C 20 A | With EER 2.6: 12.8 A → 4 mm² and C 20 A |
| Water heater 1500 W | 1500 / 220 | 6.8 | own or TUE | 2.5 | 16 A | Continuous load, PE and ID mandatory |
| Water heater 2000 W | 2000 / 220 | 9.1 | own or TUE | 2.5 | 16 A | At the limit of a 10 A socket outlet: better a 20 A socket outlet or fixed connection |
| Electric oven 2500 W | 2500 / 220 | 11.4 | TUE (20 A socket outlet) | 2.5 | 16 A | Does not go on a 10 A socket outlet |
| Electric oven 3500 W | 3500 / 220 | 15.9 | TUE (20 A socket outlet) or own | 4 | 20 A | With 2.5 mm² (Iz 21) it just complies; 4 mm² gives margin and less voltage drop |
| Induction cooktop 7.2 kW | 7200 / 220 | 32.7 | specific (ACU), fixed connection, own conduit | 6 with limiter; 10 without limiter | 32 A with the cooktop's limiter set to ≤ 32 A; 40 A with 10 mm² | 32.7 A > 32 A: either limit the cooktop, or 10 mm² + 40 A if the main line and the contracted power allow it. Type A ID. Same example as ELEC-ESP-12 |
| Pump 0.5 HP | 373 W / (0.6 × 0.8 × 220) | 3.5 | APM or own | 2.5 | C 10 A | + motor thermal protection; startup ≈ 21 A |
| Pump 0.75 HP | 559 W / (0.6 × 0.8 × 220) | 5.3 | APM or own | 2.5 | C 10 A | Startup ≈ 32 A |
| Pump 1 HP | 746 W / (0.6 × 0.8 × 220) | 7.1 | APM or own | 2.5 | C 16 A | Startup ≈ 42 A: with C 10 A (50-100 A) it is borderline |
| EV charger "3,7 kW" (16 A) | configured to 16 A | 16 | specific | 4 (regulatory min. 2.5) | 20 A | Continuous load: 2.5 mm² with 20 A just complies (Iz 21) |
| EV charger "7,4 kW" (32 A) | configured to 32 A | 32 | specific | 6 (minimum); 10 recommended | 32 A (minimum); 40 A with 10 mm² recommended | 32 A sustained on a 32 A PIA trips in a hot panel; type A ID + DC detection |
| Electric shower 5500 W | 5500 / 220 | 25.0 | specific, fixed connection | 6 | 32 A | 4 mm² with 25 A complies on paper but the MCB runs at 100 % |
| Electric shower 7500 W | 7500 / 220 | 34.1 | specific, fixed connection | 10 | 40 A | Check that the main line and the contracted power allow it |

Source: our own calculations with Iz from ELEC-AMP-2; circuit types from ELEC-AMP-8. Startup currents are an estimate
(6 × Ib). For three-phase equipment, use the 3-loaded column and the calculator `gateway electricidad current`. The AC rows
give the rated cooling current: for design, the maximum nameplate current.

## MCBs (*térmicas*, miniature circuit breakers, PIA)

### ELEC-AMP-10: Standard ratings, curves and conventional currents
- **Rule:** MCBs for dwellings and similar uses are IEC 60898-1 (two-pole in single-phase, breaking phase and neutral). Choose the
  rating by ELEC-AMP-8 and the curve by the load: **B** for resistive loads and long circuits (low minimum short-circuit
  current), **C** general use, lighting with drivers, small motors and ACs, **D** heavy inrush (transformers,
  large motors) only if the minimum short circuit at the end of the circuit exceeds the upper threshold of the D curve.
- **Why:** the thermal part (bimetal) clears overloads in minutes; the magnetic part clears short circuits in milliseconds only
  if the current exceeds its threshold. If the short circuit at the end of a long cable does not reach the magnetic threshold, clearing
  is left to the bimetal and takes seconds: the cable suffers.
- **How:** table below. Example: a C16 trips instantaneously between 80 and 160 A; if at the end of the circuit the fault current
  is 120 A, instantaneous tripping is not guaranteed: use a B16 (48-80 A) or a larger cross-section (see ELEC-PRO-5 in
  [protection.md](protection.md)).
- **Verify:** on the front: standard (IEC 60898-1), letter and rating (C16), breaking capacity in a rectangle (4500), energy
  limiting class in a square if it has one.
- **Don't:** fit a D curve "so it doesn't trip" on a socket-outlet circuit; mix MCBs without a printed standard in the same
  panel.
- **Source:** IEC 60898-1 (preferred values, curves, I1/I2); APSE, Ingeniería Eléctrica No. 304 (Nov 2015); AEA 770 Ed. 2017
  770.15.2.2.2 (marking of breaking capacity in a rectangle) and annex 770-B.2.3 (class in a square); Schneider Easy9 EZ9F34216
  ("límite de disparo magnético 5...10 x In" (magnetic tripping limit)); Jeluz Protecciones catalog pp. 5, 8, 11, 14.

| Data | Value | Source |
|---|---|---|
| Common ratings [A] | 6, 10, 16, 20, 25, 32, 40, 50, 63 (and 80, 100, 125 in some lines); 8 and 13 A are IEC preferred values but are available in fewer lines: confirm it exists before designing with it | IEC 60898-1 (preferred values); Jeluz: 6-63 A and 80/100/125 A; Schneider Easy9 2P: 6-63 A |
| B curve, instantaneous tripping | between 3 and 5 In | IEC 60898-1; Jeluz pp. 8, 11 |
| C curve | between 5 and 10 In | IEC 60898-1; Schneider Easy9 EZ9F34216 |
| D curve | between 10 and 20 In (standard); some manufacturers declare less: Jeluz 10-14 In (6-63 A) and 9.6-14.4 In (80-125 A, under IEC 60947-2) | IEC 60898-1; Jeluz pp. 8, 14 |
| Acti9 iC60 C curve (IEC 60947-2) | 8 In ± 20 % | Schneider A9F74216 p. 1 |
| Conventional non-tripping current I1 | 1.13 In: does not trip within 1 h (In ≤ 63 A) | IEC 60898-1 |
| Conventional tripping current I2 | 1.45 In: trips in less than 1 h (In ≤ 63 A) | IEC 60898-1; APSE Nov 2015 |
| Calibration temperature | 30 °C | IEC 60898-1; Jeluz pp. 5, 8, 11 ("temperatura de referencia 30 °C" (reference temperature)) |
### ELEC-AMP-11: Breaking capacity (*poder de corte*, Icn) ≥ prospective short-circuit current at that point
- **Rule:** the rated breaking capacity of the MCB (*térmica*) must be **greater than or equal to** the maximum prospective
  short-circuit current where it is installed. Ask the utility (distribution company, *distribuidora*) for the figure or calculate it (AEA 90909-0 or the tables in annex 770-B).
- **Why:** if the short circuit exceeds the breaking capacity, the MCB may fail to interrupt, weld its contacts or explode.
- **How:** guidance (always confirmed by calculation):
  - Near a transformer (building with its own transformer substation, shop right next to the substation vault): at the terminals of a
    315 kVA transformer there are about **11 kA**, at a 630 kVA one about **21 kA**. The main panel (distribution board, *tablero*) needs breakers of
    10 kA or more (or molded case), and the sub-panels are checked one by one.
  - Moving away, the cable limits the current: the AEA example gives 6.4 kA at 10.2 m from a 315 kVA transformer with 4x16 mm² Cu.
  - House at the end of an overhead network or with a long service connection (*acometida*): there are usually few kA; AEA 770 applies up to 10 kA at the
    origin. The 3 kA (Jeluz C 3 kA), 4.5 kA or 6 kA product lines cover many residential cases, **but only if the calculation
    confirms it**.
  - **Without data from the utility:** 6 kA minimum in the main panel and in the meter cabinet; 10 kA or more if
    there is a transformer substation in the building or right next to it. 4.5 kA (and 3 kA) only with a lower calculated Icc, typically in
    remote sub-panels (example in [protection.md](protection.md) ELEC-PRO-3: about 3 kA at the apartment → 4.5 kA).
    This is the practical criterion of ELEC-PRO-3 and [panels.md](panels.md) ELEC-TAB-9: the AEA sets the rule (Icn ≥ Icc), not a
    minimum kA value.
  - Apartment building: the meter panel and the ground-floor sub-panels see more kA than the top floor.
- **Verify:** technical report with the Icc of each panel and the breaking capacity chosen; the number in the rectangle on the front.
- **Don't:** put 3 kA MCBs in a building's main panel; assume "it's a house, it's more than enough" without data.
- **Source:** AEA 770 Ed. 2017 770.15.2.2.2 (PdCcc ≥ I"k; marking in a rectangle), annex 770-B.2 and table 770-B.II (Icc at the terminals
  of transformers: 315 kVA 11.028 kA; 630 kVA 21.458 kA; example 315 kVA + 10.2 m 4x16 mm² → 6 442 A), scope up to 10 kA
  (770.1); APSE Nov 2015 (standard Icn 1500, 3000, 4500, 6000, 10 000 A); Jeluz catalog Protecciones (protection devices) (3, 4.5 and 6 kA lines).
  **Not verified in a primary source:** the 6 kA / 10 kA criterion without data is practice (ELEC-PRO-3), not AEA text; in the
  reviewed text of AEA 771 Ed. 2006 no minimum kA per type of supply was found.

| Standard Icn (IEC 60898-1) [A] | Indicative use | Source |
|---|---|---|
| 1 500 | Practically not used | APSE Nov 2015 |
| 3 000 | Houses far from the transformer, only with calculated Icc < 3 kA | IEC 60898-1; Jeluz C line 3 kA |
| 4 500 | Sub-panels (e.g. the apartment's) with calculated Icc ≤ 4.5 kA | IEC 60898-1; Schneider Easy9; Jeluz |
| 6 000 | Minimum without utility data in the main panel and meter cabinet; ground-floor apartments, shops; Icc between 4.5 and 6 kA | IEC 60898-1; Schneider iC60N (Icn 6000 A); Jeluz; criterion ELEC-PRO-3 |
| 10 000 | Panels near the transformer, building main panels | IEC 60898-1 |

### ELEC-AMP-12: Icn (IEC 60898-1) is not the same as Icu/Ics (IEC 60947-2)
- **Rule:** for dwellings and unskilled users, the figure compared with the Icc is the **Icn** of IEC 60898-1 (the one in the
  rectangle). The **Icu** (ultimate) and **Ics** (service) of IEC 60947-2 are different tests, for industrial use with
  skilled personnel, and usually give larger numbers for the same device. Don't mix them.
- **Why:** after interrupting its Icu the breaker may be left unusable; after interrupting its Ics it must keep
  working. The Icn of 60898-1 is another test with other conditions. A catalog that says "20 kA" may be talking about the
  Icu at 230 V under IEC 60947-2 of a device whose Icn is 6 kA.
- **How:** real example, Schneider Acti9 iC60N 2P C16 (A9F74216): **Icn = 6 000 A** at 400 V (IEC 60898-1); **Icu = 20 kA** at
  220-240 V and **Ics = 15 kA** (75 % of Icu) under IEC 60947-2. For a dwelling, 6 kA is what counts. Easy9 EZ9F34216: IEC 60898-1 only,
  Icn = 4 500 A, Ics = 100 % of Icn.
- **Verify:** which standard goes with the kA number in the catalog and on the front of the device.
- **Don't:** choose an MCB by the 60947-2 Icu for a dwelling panel; compare one brand's Icn with another's Icu.
- **Source:** Schneider Electric, data sheets A9F74216 (Acti9 iC60N, generated 2026-11-15, p. 1) and EZ9F34216 (Easy9,
  2026-11-14, p. 1); AEA 770 Ed. 2017 770.15.2.2.2 (IEC 60898-1 marking).

### ELEC-AMP-13: MCB (*térmica*) in a closed, hot panel, or many side by side: consider derating
- **Rule:** IEC 60898-1 MCBs are calibrated at **30 °C**. Inside a closed panel, in the sun, next to other
  loaded devices, the temperature around the bimetal is higher and the MCB trips at a lower current (and the reverse in
  the cold). For continuous loads close to the rating (In), apply the derating factor from the **manufacturer's catalog** of the
  device you use.
- **Why:** it is the cause of "the MCB trips by itself in summer" with 14-15 A loads on a 16 A one. It is not a fault of the
  device: it is its characteristic.
- **How:** ask for or look up the model's "derating by temperature" and "by side-by-side mounting" table. If the panel
  gets very hot, the panel's thermal check is in [panels.md](panels.md). As an order of magnitude,
  the catalogs of the big brands show losses of a few percentage points at 40 °C and on the order of 10 % or more at
  50-60 °C, plus an additional factor when many loaded MCBs are mounted tight together.
- **Verify:** temperature inside the panel at peak load (thermometer or camera); actual circuit current with a clamp meter.
- **Don't:** "fix it" by raising the rating above Iz; cover the panel's vents.
- **Source:** reference temperature 30 °C: IEC 60898-1 and Jeluz catalog Protecciones pp. 5, 8, 11 (the 80-125 A ones state
  "temperatura ambiente nominal 50 °C" (rated ambient temperature), p. 14). **Not verified in a primary source:** the derating percentages (no
  manufacturer derating table could be downloaded for this guide); use the one for the specific model.

## RCDs (*disyuntores*, ID)

### ELEC-AMP-14: The RCD (*diferencial*) does not protect against overload or short circuit: size it and protect it
- **Rule:** the pure ID (IEC 61008-1) is chosen by rated current (25, 40, 63, 80, 100 A) and must meet one of two conditions:
  (a) In of the ID ≥ In of the MCB in series **upstream**, or (b) In of the ID ≥ **sum** of the MCBs it feeds
  downstream. In addition, its own making and breaking capacity is low: it needs a short-circuit protective device coordinated according to
  the manufacturer (conditional short-circuit current Inc / IΔc ≥ Icc of the panel).
- **Why:** it has no bimetal and no magnetic coil: if more current than rated flows it overheats, and in a phase-neutral
  short circuit its contacts are not made to interrupt thousands of amperes.
- **How:** example: 2x40 A ID feeding MCBs of 16 + 16 + 20 A = 52 A → does not meet (b); put a 2x40 A incoming MCB
  upstream (meets a) or a 63 A ID. Minimum and catalog data in the table below.
- **Verify:** single-line diagram (*unifilar*) with the ID's In against the MCB above or the sum below; manufacturer's sheet with Inc.
- **Don't:** a 25 A ID as the incoming device of a panel with a 40 A main and nothing in between; use an ID as the main
  switch without overcurrent protection.
- **Source:** AEA 770 Ed. 2017, 770.15.2.2.5 (conditions a, b, c, d) and annex 770-B.2.4, table 770-B.X; Schneider Easy9 RCCB
  EZ9R36240 (2026-11-15); Jeluz catalog Protecciones p. 18.

| ID | Rated current [A] | Minimum making and breaking capacity IEC 61008 (Im / IΔm) [A] | Source |
|---|---|---|---|
| Two-pole or four-pole | 25 | 500 | AEA 770 table 770-B.X |
| Two-pole or four-pole | 40 | 500 | AEA 770 table 770-B.X |
| Two-pole or four-pole | 63 | 630 | AEA 770 table 770-B.X |
| Two-pole | 80 | 800 | AEA 770 table 770-B.X |
| Two-pole | 100 | 1 000 | AEA 770 table 770-B.X |
| General rule | — | 10 In or 500 A, whichever is greater | AEA 770 annex 770-B.2.4 |
| Catalog example: Schneider Easy9 2P 40 A 30 mA AC | 40 | 500; Inc = 6 000 A with Easy9 MCB of 40 A | Schneider EZ9R36240 |
| Catalog example: Jeluz JZ / JZX | 16, 25, 40, 63 | IΔm = Im = 1 000; Inc = IΔc = 6 000 A (JZ) / 10 000 A (JZX) | Jeluz Protecciones p. 18 |

### ELEC-AMP-15: Sensitivity: 30 mA for people; 300 mA or more only as line or fire protection
- **Rule:** 30 mA instantaneous on all final circuits (additional protection against direct contact). 10 mA
  only where the manufacturer or the design justifies it (small circuits, In ≤ 32 A). 100/300 mA to protect a line
  (sub-main) against indirect contact, preferably selective (S). For protection against fire caused by earth leakage,
  **300 mA maximum** (it does not protect people). The IDs of up to 500 mA that AEA 771 allows in some exceptions
  do **not** fulfill the fire protection function.
- **Why:** with 30 mA, tripping happens before the current through the body causes fibrillation in most
  cases; a sustained leakage of 300 to 500 mA **can start** a fire, so the ID must interrupt before reaching that.
- **How:** table below; details of where each one goes in [protection.md](protection.md) ELEC-PRO-7 and ELEC-PRO-12.
- **Verify:** IΔn marked on the front; that the 30 mA one is on each final circuit.
- **Don't:** replace a 30 mA ID with a 300 mA one "because it trips".
- **Source:** AEA 770 Ed. 2017, 770.14.3.2 (note 1: 300 to 500 mA can cause a fire; a) ID ≤ 30 mA with Ra ≤ 40 Ω;
  b) up to 300 mA upstream); AEA 771 Ed. 2006 (exceptions with ID ≤ 500 mA in particular cases); Jeluz p. 18 (10 mA type
  AC with In ≤ 32 A; 30, 100, 300 mA). **Not verified in a primary source:** IEC 60364-4-42, 422.3.9 (ID ≤ 300 mA in locations
  with fire risk), cited from memory.

| IΔn | Use | Source |
|---|---|---|
| 10 mA | Small circuits where more sensitivity is wanted; offered only in In ≤ 32 A by some manufacturers | Jeluz p. 18 |
| 30 mA | All final circuits in dwellings, offices, shops; bathrooms, outdoors, EV chargers | AEA 770 770.14.3.2 a); AEA 722:2024 |
| 100 / 300 mA | Protection of sub-main lines or upstream panels, selective S; 300 mA maximum in that function | AEA 770 770.14.3.2 b) |
| ≤ 300 mA (usually 300 mA, type S if upstream) | Protection against fire caused by earth leakage (does not protect people) | AEA 770 770.14.3.2 note 1 (from 300 to 500 mA a leakage can start a fire) |
| 500 mA | Only in the specific exceptions of AEA 771; it is neither fire protection nor protection of people | AEA 771 Ed. 2006 |

### ELEC-AMP-16: Type AC, A, F, B and S: choose it by what it feeds
- **Rule:** AC only for loads without electronics; **A** as a minimum for single-phase electronics (inverter units, induction,
  washing machines, chargers, LED); **F** with single-phase drives; **B** with three-phase drives, inverters or EV
  chargers without DC detection. **S** is the time-delayed version, for going upstream.
- **Why:** leakage with a DC component "blinds" type AC: the ID may not trip on a real fault.
- **How:** full table and rules in [protection.md](protection.md) ELEC-PRO-9 and ELEC-PRO-12; chargers in
  [special-installations.md](special-installations.md) ELEC-ESP-17.
- **Verify:** type symbol on the front (AC, A, F, B) and "S" on the upstream one.
- **Don't:** put a type AC upstream of an EV charger, an inverter or an induction cooktop.
- **Source:** IEC 61008-1:2024 and IEC 62423 (via [protection.md](protection.md)); AEA 90364-7-722:2024 table 722.I; Jeluz
  p. 18-19 (types AC and A in the catalog).

### ELEC-AMP-17: Maximum tripping times: what the tester must show
- **Rule:** a general-type (instantaneous) ID does not trip at 0.5 IΔn, trips before reaching IΔn, and interrupts within the maximum
  times in the table. Type S has a minimum time (it does not trip earlier) and a maximum.
- **Why:** time is what limits the energy passing through the body; a slow or stuck ID does not protect even if the test
  button "works".
- **How:** test with an RCD tester (IEC 61557-6), at 0° and 180°, on each ID ([testing-and-commissioning.md](testing-and-commissioning.md)
  ELEC-MED-6).
- **Verify:** test report with tripping current and measured times.
- **Don't:** test "by hand" with a wire from phase to earth; accept an ID as good only because the button works.
- **Source:** Guía práctica SRT Res. 900/2015 (practical guide) (≤ 300 ms at IΔn, ≤ 150 ms at 2 IΔn, ≤ 40 ms at 5 IΔn; tripping between 0.5 and 1 IΔn),
  which cites IEC 61008 and AEA 90364; IEC 61008-1:2024 table 11 (full text not consulted). **Not verified in a primary
  source:** type S times (values from the IEC 61008-1 table cited from memory; confirm them in the manufacturer's sheet).

| Test current | General ID (instantaneous) | Selective ID S | Source |
|---|---|---|---|
| 0.5 IΔn | Does not trip | Does not trip | Guía SRT Res. 900/2015 |
| IΔn | ≤ 300 ms | between 130 and 500 ms | SRT (general); S: not verified |
| 2 IΔn | ≤ 150 ms | between 60 and 200 ms | SRT (general); S: not verified |
| 5 IΔn (150 mA on a 30 mA ID) | ≤ 40 ms | between 50 and 150 ms | SRT (general); S: not verified |

Test note: on IDs with IΔn ≤ 30 mA the product standard allows testing with **0.25 A** instead of 5 IΔn (same maximum time,
40 ms), and many testers and test reports do it that way: it is not an error in the report. On type A IDs, the test with pulsating DC
current uses other multipliers (on the order of 1.4 IΔn); use the tester function that matches the ID type.
**Not verified in a primary source:** the 0.25 A note and the 1.4 multiplier (IEC 61008-1, cited from memory; confirm it in
the tester's manual).

### ELEC-AMP-18: How many circuits per RCD (*diferencial*): keep standing leakage below ~30 % of IΔn
- **Rule:** the AEA does not set a number of circuits per ID. Group them so that the sum of the standing leakage of the equipment
  on one ID does not exceed approximately **30 % of IΔn** (≈ 9 mA on a 30 mA ID) and so that one trip does not black out the whole
  unit.
- **Why:** each piece of equipment with a line filter leaks something to earth by design; added up, plus the moisture of an outdoor outlet point (*boca*), they reach
  the tripping threshold (which can be at 15-30 mA for a 30 mA ID) and "unexplained" trips appear.
- **How:** example: office with 8 PCs of ~1 mA = 8 mA on a 30 mA ID → at the limit; split across two IDs. House: one ID for
  lighting and general socket outlets, another for kitchen, laundry and ACs (type A), another for outdoors if there is one.
- **Verify:** measure the leakage of each ID with a leakage clamp meter (mA) with everything on and record it in the test report.
- **Don't:** go up to 300 mA because it trips; hang a whole office on a single 30 mA ID.
- **Source:** AEA 770 Ed. 2017 770.16.5.4 note 1 (one per circuit or grouped), per [protection.md](protection.md)
  ELEC-PRO-11; the ≈ 0.3 IΔn limit appears in BS 7671, Reg. 531.3.2 ("standing protective conductor currents" ≤ 30 % of
  IΔn: 9 mA on a 30 mA ID), according to the IET (secondary source), and as practical guidance in RCD manufacturers' manuals.
  **Not verified in a primary source:** the equivalent subclause of IEC 60364-5-53:2019 (one secondary source places it in
  531.3.2; another states that, in the IEC text, 531.3.2 deals with the PEN conductor; the standard could not be read) and the leakage limits
  per piece of equipment in the product standards (IEC 60335-1: on the order of 0.75 mA in portable class I appliances and up to 3.5 mA in
  stationary ones with a motor; IEC 62368-1: on the order of 3.5 mA in pluggable IT equipment), cited from memory.
## Socket outlets, plugs, power strips, extension cords, switches, terminals and busbar combs

### ELEC-AMP-19: 10 A or 20 A socket outlet (*toma*, IRAM 2071) and IRAM 2073 plugs (*fichas*)
- **Rule:** the fixed installation uses 2P+E **IRAM 2071** socket outlets (*tomas*) of **10 A** (TUG and IUG: loads up to 10 A) or of **20 A**
  (TUE: loads up to 20 A; 10 A socket outlets can be added at the same outlet point (*boca*)). Plugs (*fichas*) with earth are **IRAM 2073**, 10 A
  and 20 A, 250 V. The 20 A plug does not fit in the 10 A socket outlet, on purpose.
- **Why:** a 10 A socket outlet with a 15 A load for hours overheats at the contacts even if the MCB (*térmica*) does not trip:
  it is the classic "melted socket outlet".
- **How:** 10 A × 220 V = 2200 W maximum per 10 A socket outlet; 20 A × 220 V = 4400 W per 20 A socket outlet. In dwellings, socket outlets less than 0.9 m
  from the floor have a shutter against insertion of objects. The MCB of a circuit with socket outlets does not exceed the rating
  of the socket outlet: TUE with 20 A socket outlets → 20 A MCB maximum, even though the AEA allows 32 A on the TUE (safety criterion,
  ELEC-AMP-8). EV chargers in Mode 1/2: IRAM 2071 socket outlet on a **dedicated circuit**, **20 A** if the charging cable draws
  more than about 8 A (a 10 A socket outlet is not made for 10 A for hours), with a type A RCD (*diferencial*, ID) + RDC-DD or type B; see
  [special-installations.md](special-installations.md) ELEC-ESP-17 and ELEC-ESP-18.
- **Verify:** certification mark and QR code; rating marked on the socket outlet; that the 20 A socket outlet is on a TUE (not on a TUG) and
  that its MCB does not exceed 20 A.
- **Don't:** put a 20 A socket outlet on a TUG to plug in an oven; use adapters to fit a 20 A plug into a
  10 A socket outlet; install "universal" socket outlets that accept several geometries.
- **Source:** AEA 770 Ed. 2017 770.6 a) and b) (IUG/TUG with 2P+E 10 A IRAM 2071 socket outlets; TUE with 20 A IRAM 2071 or 16 A
  IEC 60309 socket outlets; additional 10 A socket outlets); AEA 771 Ed. 2006 bibliography (IRAM 2071: socket outlets 10 A and 20 A, 250 V; IRAM 2073:
  plugs 10 A and 20 A, 250 V) and foreword (shutter up to 0.9 m); Res. SIyC 236/2024 / Disp. DNRT 2/2025 (socket outlets without multiple
  geometries), per [regulations-and-permits.md](regulations-and-permits.md) and [earthing.md](earthing.md)
  ELEC-PAT-14.

### ELEC-AMP-20: Power strip (*zapatilla*): 10 A in total. Extension cord (*prolongación*): what its cord can carry
- **Rule:** a power strip (multiple socket) carries **10 A in total** (2200 W at 220 V), no matter how many outlets it has; the
  certified ones on sale carry the legend of 10 A maximum simultaneous and an automatic limiter. An extension cord carries what
  its cord and its plug can: with a **1 mm²** cord, about **7 A** (≈ 1500 W); with **1.5 mm²**, **10 A** (2200 W).
- **Why:** the sum of the loads passes through a single plug and a single 10 A socket outlet; a coiled reel does not dissipate heat and gets hot
  with much less current than its rating.
- **How:** add up the powers: fan heater 2000 W + coffee maker 900 W = 2900 W / 220 = 13.2 A on a 10 A power strip → 32 %
  overload, even though the 16 A MCB does not trip. Extension cord: fully unwound; flexible cord (*tipo taller*) IRAM NM 247-5 of
  1.5 mm² for general use. The Prysmian TPR Ecoplus sheet excludes heating appliances: heaters and fan heaters are
  plugged directly into the socket outlet with the appliance's own cord, without an extension cord.
- **Verify:** maximum current legend, mark and QR code; cross-section printed on the cord; plug and power strip cool after a
  while of use.
- **Don't:** daisy-chain power strips; plug air conditioners, heaters, ovens or water heaters into power strips or extension cords; use
  extension cords (of any cross-section) for heaters and fan heaters; leave the extension cord coiled under load.
- **Source:** Res. SIyC 236/2024 and Disp. DNRT 2/2025 (power strips and extension cords with earth contact, legend of 10 A maximum
  simultaneous and automatic limiter on multiple ones), per [regulations-and-permits.md](regulations-and-permits.md);
  Prysmian TPR Ecoplus Ed. 2026 p. 2 ("excluyendo los aparatos de calefacción" (excluding heating appliances)) and p. 3 (1 mm² = 7 A, 1.5 mm² = 10 A at
  40 °C); example from
  [troubleshooting-common-cases.md](troubleshooting-common-cases.md) ELEC-DIA-18.

### ELEC-AMP-21: Light switch (*llave de efecto*): it controls lighting, don't switch a heater with it
- **Rule:** residential switches (*llaves*, *interruptores de efecto*) are usually sold for **10 A, 250 V** (IEC/IRAM-NM
  60669-1). They are for controlling lighting and small IUG loads. A load over 10 A or a motor is controlled with a
  switch of the right rating or a contactor.
- **Why:** the switch opens with an arc; with inductive loads or currents close to its maximum, the contacts pit and
  overheat.
- **How:** check the rating marked on the module. For LED lamp loads with many drivers, the inrush current is high:
  if a circuit has many, use a contactor or a relay rated for LED.
- **Verify:** module marking (A, V); module temperature with the load on.
- **Don't:** control a water heater, a pump or a 2000 W fan heater directly with a light switch.
- **Source:** **Not verified in a primary source:** the 10 A rating is the usual marking of residential modules on the
  market; IRAM-NM 60669-1 and a module data sheet were not consulted for this guide. 10 A limit per IUG outlet point: AEA 770
  Ed. 2017 770.6 a) I.

### ELEC-AMP-22: MCB (*térmica*) and RCD (*diferencial*) terminals: maximum cross-section and manufacturer's tightening torque
- **Rule:** each modular device accepts a range of cross-sections at its terminal and has a stated **tightening torque**. Don't put a
  cable thicker than the maximum (it does not fit or ends up poorly clamped) or two cables in a single-cable terminal, and tighten with a
  screwdriver or torque wrench to the manufacturer's value. Flexible cable: with a ferrule (bootlace ferrule, *puntera*).
- **Why:** poor contact at the terminal is the number one cause of burned MCBs: a loose terminal heats up from
  contact resistance even when the current is normal.
- **How:** table below with catalog data.
- **Verify:** cable cross-section against the terminal range; re-tighten at commissioning and during maintenance (with the
  voltage off); heat marks on the plastic.
- **Don't:** "trim strands" off a 16 mm² cable so it fits a 10 mm² terminal; put two flexible cables without a
  ferrule in the same terminal; tighten "as hard as it will go".
- **Source:** product data sheets cited in the table.

| Device | Cross-section accepted at the terminal | Tightening torque | Source |
|---|---|---|---|
| Schneider Acti9 iC60N (PIA) | 1 to 25 mm² solid; 1 to 16 mm² flexible (with or without ferrule); one cable | 2 N·m | Schneider A9F74216, p. 2 |
| Schneider Easy9 (PIA) | 1 to 25 mm² solid; 1 to 16 mm² flexible | 2 N·m | Schneider EZ9F34216, p. 2 |
| Schneider Easy9 RCCB 2P 40 A | 1 to 35 mm² solid; 1 to 25 mm² flexible | 3.5 N·m | Schneider EZ9R36240, p. 2 |
| Jeluz PIA 6-63 A (3, 4.5 and 6 kA) | up to 16 mm² | 2.5 N·m max. | Jeluz Protecciones pp. 5, 8, 11 |
| Jeluz PIA 80-125 A | 25 to 50 mm² | 3.5 N·m max. | Jeluz Protecciones p. 14 |
| Jeluz ID JZ/JZX | up to 16 mm² | 3 N·m max. | Jeluz Protecciones p. 18 |

Watch out: if the line of a 63 A ID is run in 25 mm² (because of voltage drop or grouping), the up-to-16 mm² terminal of the Jeluz
ID does not accept it: you need a distribution terminal block or a device with a larger terminal (e.g. Schneider Easy9 RCCB: up to 35 mm²
solid). Never trim strands off the cable. Choose the device by its terminal too.

### ELEC-AMP-23: Busbar comb (*peine*, connection bar): its current-carrying capacity is a limit of the panel
- **Rule:** the busbar comb that feeds a row of devices has a rated current (Ie) at a given temperature. The sum of
  currents flowing through the most heavily loaded section of the comb must not exceed it. Use a comb of the same brand and line as the
  devices (compatible pitch and tooth shape).
- **Why:** an overloaded comb, or one of another brand whose teeth do not seat properly, heats every terminal in the row.
- **How:** example with catalog data: Schneider A9XPH212 (two-pole, 12 pitches of 18 mm, Acti9 line): **Ie = 100 A at 40 °C**.
  Feeding the comb in the middle instead of at one end splits the current and lowers the load on the most heavily loaded section
  (practical criterion). If the incoming switch is larger than the comb's Ie, the comb is left unprotected.
- **Verify:** comb Ie figure (catalog or label); incoming device rating ≤ Ie; teeth seated and tightened to the torque
  of each device; caps fitted on free teeth.
- **Don't:** cut a comb and leave the end without a cap; mix a comb of one brand with devices of another; feed from one
  end a long comb with a 63 A incoming device if the comb has a lower Ie.
- **Source:** Schneider Electric, data sheet A9XPH212 (2026-11-15), p. 1 (Ie 100 A at 40 °C; IEC 61439; compatibility
  iC60, iK60, iID). **Not verified in a primary source:** Ie of generic combs and the recommendation to feed in the middle.

## Fuses

### ELEC-AMP-24: NH fuses: sizes, ratings and why gG needs In ≤ 0.9 Iz
- **Rule:** NH fuses (blade type, IEC 60269-2) are chosen by **size** (base dimensions) and **rating**, and by **class**:
  **gG** protects cables (overload and short circuit); **aM** only provides short-circuit backup for motors (the overload is
  covered by another device). For a gG to protect a cable against overload: I2 = 1.6 In ≤ 1.45 Iz → **In ≤ 0.9 Iz**. The NH fuses in the
  utility service box (*caja de toma*) and in the isolation box (*caja de seccionamiento*) belong to the utility (*distribuidora*) and are not touched; in dwellings and offices the AEA does not allow
  fuses as protection of the user's installation.
- **Why:** gG has a higher conventional fusing current than an MCB (1.6 In versus 1.45 In); without that
  adjustment, the cable can be overloaded without the fuse blowing.
- **How:** example: cable with Iz = 100 A → In ≤ 1.45 × 100 / 1.6 = 90.6 A → 80 A gG fuse, not 100 A. The 1.6 In applies
  to gG with **In ≥ 16 A**. For small fuses the conventional fusing current is higher: 4 A < In < 16 A, I2 = 1.9 In →
  **In ≤ 0.76 Iz**; In ≤ 4 A, I2 = 2.1 In → **In ≤ 0.69 Iz**. Example: control cable with Iz = 15 A → gG ≤ 0.76 × 15 =
  11.4 A → 10 A. Usual sizes in the table. NH fuses are operated off load (or with a fuse switch-disconnector base rated for switching under load), with a fuse puller handle and PPE
  ([site-safety.md](site-safety.md)).
- **Verify:** class (gG/aM), size, rating and voltage printed; that the size matches the base; In ≤ 0.9 Iz (≤ 0.76 Iz or ≤ 0.69 Iz for small
  gG).
- **Don't:** replace an NH fuse "because it blew" without looking for the cause; bypass it; put a fuse in the neutral; fit an NH fuse of
  a smaller size into a larger base with adapters.
- **Source:** APSE, Ingeniería Eléctrica No. 304 (Nov 2015) (1.6 In for gG; In ≤ 0.9 Iz); AEA 771 Ed. 2006 (foreword: fuse not
  allowed in dwellings and offices); Ingeniería Eléctrica No. 327 (Dec 2017), Edenor diagrams (three-phase utility service box with
  size 1 NH bases; isolation box with six size 3 NH bases, supplied by the utility); size ranges: Wikipedia
  (de) "NH-Sicherung" (DIN 43620-1), secondary source. **Not verified in a primary source:** the maximum gG rating per size in
  the table (usual values from European catalogs; confirm it in the manufacturer's catalog) and the conventional
  fusing currents 1.9 In and 2.1 In for small gG (IEC 60269-1, cited from memory).

| NH size | Usual maximum gG rating 400/500 V [A] | Total range of the size per DIN 43620-1 [A] | Where it shows up on site |
|---|---|---|---|
| 000 | 100 | 2 to 160 (000/00) | Small industrial panels |
| 00 | 160 | 2 to 160 (000/00) | Industrial sub-panels |
| 1 | 250 | 16 to 355 | Utility's three-phase service box (Edenor) |
| 2 | 400 | 25 to 500 | Main panels |
| 3 | 630 | 250 to 800 | Utility's isolation box (Edenor) |
| 4 / 4a | 1 250 | 400 to 1 600 | Large panels, transformer outgoing feeders |

Source: columns 3 and 4: Wikipedia (de) "NH-Sicherung" and Ingeniería Eléctrica Dec 2017; column 2: usual catalog
values, **not verified**. Typical breaking capacity of NH fuses: 100 to 120 kA (secondary source, same page).

### ELEC-AMP-25: "Tabaquera" fuses (rewirable porcelain fuses): replace them, don't "recalibrate" them
- **Rule:** the "tabaquera" porcelain fuse holders with replaceable fuse wire that remain in old installations are not
  an allowed protection for the installation of a dwelling or office: they are replaced by an MCB (IEC 60898-1) and an RCD.
  If they are in the utility service box or in an element belonging to the utility, they are not touched: ask the utility.
- **Why:** the wire is replaced by hand with any wire ("I calibrated it with a little wire"), and the real rating becomes
  unknown: the cable is no longer protected. They do not interrupt with the speed or the breaking capacity of an MCB.
- **How:** in a survey (*relevamiento*, [reviewing-a-panel.md](reviewing-a-panel.md)), record how many there are, what cross-section leaves each one
  and propose the new panel (*tablero*) with MCBs sized per ELEC-AMP-8.
- **Verify:** that no tabaquera remains downstream of the meter in the user's installation.
- **Don't:** replace the wire with copper wire or a paper clip; bypass the fuse holder; make the wire bigger "because it blows".
- **Source:** AEA 771 Ed. 2006 (foreword: fuse not allowed as protection in dwellings and offices); AEA 770 Ed. 2017
  (protection with IEC 60898-1 circuit breakers, 770.15.3). **Not verified in a primary source:** sizes and ratings of
  tabaquera fuses (no current manufacturer data sheet was found) and whether any utility still uses bases of that type.

## Checks that complete the cross-section → MCB table

### ELEC-AMP-26: The MCB (*térmica*) must also clear the short circuit before the cable is damaged (k²S² ≥ I²t)
- **Rule:** the table in ELEC-AMP-8 covers overload. In addition, each cable must withstand the energy of the maximum short circuit
  at its point until the protection interrupts: **k² × S² ≥ I²t**, with k = 115 for copper with PVC or thermoplastic LS0H
  (from 70 °C to 160 °C). With current-limiting PIAs, I²t is the let-through energy stated by the manufacturer (or the AEA's guidance
  table by limitation class) at the Icc of the point.
- **Why:** a small cable behind an MCB with a high breaking capacity can reach 160 °C in a bolted short circuit
  even if the MCB interrupts in milliseconds: the insulation is damaged and a latent fault remains.
- **How:** reference k²S² (copper/PVC): 1.5 mm² → 29 756 A²s; 2.5 mm² → 82 656 A²s; 4 mm² → 211 600 A²s; 6 mm² → 476 100
  A²s; 10 mm² → 1 322 500 A²s. Example that does **not** pass if the Icc at the point is high: 1.5 mm² with a C10 6 kA class 3, which
  according to the AEA guidance table can let through up to 42 000 A²s > 29 756 A²s; either the Icc is lower (remote point),
  or the manufacturer's real I²t at that Icc is used, or the cross-section is increased. Example that passes: 2.5 mm² with a C16 6 kA class 3,
  42 000 ≤ 82 656 A²s (the AEA's own example). Full calculations and cases with time delay in [protection.md](protection.md)
  ELEC-PRO-5 and [conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-26.
- **Verify:** in the technical report, Icc of each panel, limitation class and I²t of the PIA, k²S² of the cable; on the front of the PIA,
  the limitation class (number in a square).
- **Don't:** consider a 1.5 mm² protected with any PIA "because it's 6 kA"; use PIAs with no stated limitation
  class in panels with high Icc.
- **Source:** AEA 90364-7-771 Ed. 2006, p. 233 (example: TUG 2.5 mm², C16, 6000 A, class 3, Icc 3000 A, maximum I²t
  42 000 A²s per the let-through energy table in the annex), table 771.19.II (k = 115); AEA 770 Ed. 2017 tables 770-B.VIII and B.IX (via
  ELEC-PRO-5).
### ELEC-AMP-27: With large loads far from the panel, voltage drop (*caída de tensión*) decides the cross-section
- **Rule:** after choosing the cross-section by current (ELEC-AMP-8 and ELEC-AMP-9), check that the voltage drop does not exceed
  **3 %** from the main panel (TP, *tablero principal*) (5 % on circuits that feed only motors). In the 771, if the circuit leaves a
  sub-panel (TS, *tablero seccional*), the final circuit is held to **2 %** (4 % for motors) because the sub-main (feeder) uses up to 1 %
  ([conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-9).
- **Why:** an electric shower, a cooktop or an EV charger 30-50 m from the panel with the cross-section "just enough for the current" loses
  voltage, heats the cable and terminals more and, in motors, starts poorly and burns out.
- **How:** maximum length (distance from the panel to the load, not meters of cable), single-phase 220 V, copper, ρ = 0.0225 Ω·mm²/m
  at operating temperature. For resistive loads cos φ = 1 was used, which is the worst case with R alone (L = ΔU × S /
  (2 × ρ × I)); for the pump, cos φ = 0.8. If the real length exceeds the one in the table, go up one cross-section and recalculate with
  `gateway electricidad drop`.
- **Verify:** real length measured on site or on the drawing; sub-main drop added to the final circuit drop.
- **Don't:** size the charger for the garage at the back of the lot with the current table alone; count the length out and back
  in addition to the factor 2 in the formula.
- **Source:** limits: AEA 770 Ed. 2017 770.15.6 and AEA 771 Ed. 2006 771.13 b) (via ELEC-CON-9); ρ at operating temperature:
  IEC 60364-5-52 annex G (via ELEC-CON-9); lengths: own calculations.

**Maximum length by voltage drop (single-phase 220 V, copper) [m]**

| Load | Ib [A] | Cross-section [mm²] | L max. 3 % (6.6 V) | L max. 2 % (4.4 V, final circuit from sub-panel in the 771) |
|---|---|---|---|---|
| Oven 3500 W | 15.9 | 4 | 36 | 24 |
| EV charger 16 A | 16 | 4 | 36 | 24 |
| Electric shower 5500 W | 25.0 | 6 | 35 | 23 |
| Cooktop 7.2 kW limited to 32 A | 32 | 6 | 27 | 18 |
| EV charger 32 A | 32 | 6 / 10 / 16 | 27 / 45 / 73 | 18 / 30 / 48 |
| Electric shower 7500 W | 34.1 | 10 | 43 | 28 |
| Pump 1 HP (motor: 5 % / 4 %, cos φ 0.8) | 7.1 | 2.5 | 107 (5 %) | 86 (4 %) |

Source: own calculations, L = ΔU × S / (2 × 0.0225 × I × cos φ). Example: 32 A charger on 10 mm², ΔU 6.6 V: L = 6.6 × 10 /
(0.045 × 32) = 66 / 1.44 = 45.8 m (rounded down: 45 m; all lengths in the table are rounded down). It matches the case in [conductors-and-conduits.md](conductors-and-conduits.md)
ELEC-CON-30 (garage at 40 m: with the 771 sub-panel, 16 mm² is needed). The pump is also checked at starting (15 %) with the
calculator.

## Load switching, industrial socket outlets and busbars

### ELEC-AMP-28: Contactors, switch-disconnectors and motor protection circuit breakers (*guardamotores*): chosen by utilization category, not just by amperes
- **Rule:** a contactor or a switch-disconnector (*interruptor-seccionador*) has a rated current **per utilization category**, and that is the one
  compared with the load: **AC-1** (resistive loads: water heater, heating elements, incandescent lighting), **AC-3** (squirrel-cage
  motors: starting and switching off while running, such as pumps and three-phase gates), **AC-4** (inching and reversing); in
  modular contactors for dwellings, **AC-7a** (resistive) and **AC-7b** (household motors). In switch-disconnectors, **AC-22**
  (mixed loads, slightly inductive) and **AC-23** (motors). None of these devices protects: upstream goes the MCB (*térmica*) or the
  coordinated fuse, and for motors, in addition, the motor overload protection (thermal overload relay or motor protection circuit breaker).
- **Why:** switching off a starting motor demands much more from the contacts than switching off a resistor: the same contactor that
  handles 25 A in AC-1 handles quite a bit less in AC-3. Choosing it by the biggest number in the catalog ends in welded
  contacts (the motor does not stop) or pitted ones.
- **How:**
  - 2000 W water heater controlled by a timer or home automation: contactor with Ie in AC-1 (or AC-7a) ≥ 9.1 A, plus margin.
  - 1.5 kW three-phase pump (≈ 3.5 A): contactor chosen by power in AC-3 at 380 V ≥ 1.5 kW; motor protection circuit breaker set to the
    nameplate current ([buildings.md](buildings.md) ELEC-EDI-14; [protection.md](protection.md) ELEC-PRO-24).
  - Isolating switch-disconnector of a panel: rated current in AC-22 ≥ In of the upstream protection, and protected by it
    against short circuit according to the manufacturer's coordination table.
  - Catalog data: Jeluz states that in its TGC1 contactors, at 220/380 V, the operational current in AC-1 equals the
    conventional free-air thermal current (Ith); motor power is given separately in AC-3.
- **Verify:** device nameplate (Ie per category and voltage, Ith, power in kW AC-3); that the control of a load over
  10 A is not a light switch (ELEC-AMP-21); backup protection stated by the manufacturer.
- **Don't:** control a pump with a contactor chosen by its Ith or its AC-1; use a switch-disconnector as protection; set a
  motor protection circuit breaker "a bit higher so it doesn't trip".
- **Source:** Jeluz catalog Línea Protecciones (protection devices line) p. 24 (TGC1 contactors: table with AC-3/AC-4 and note 2 on AC-1 = Ith).
  **Not verified in a primary source:** the definitions of categories AC-1/AC-3/AC-4 (IEC 60947-4-1), AC-7a/AC-7b (IEC 61095)
  and AC-21A/AC-22A/AC-23A (IEC 60947-3), from prior knowledge; the texts of those standards were not consulted.

### ELEC-AMP-29: IEC 60309 industrial plugs and socket outlets: rating, color and protection
- **Rule:** industrial plugs (*fichas*) and socket outlets (*tomas*) (IRAM-IEC 60309 / IEC 60309) are identified by **rating** (16, 32, 63 and 125 A),
  **configuration** (2P+E single-phase; 3P+E or 3P+N+E three-phase) and **color by voltage**: **blue** for 220 V and **red** for
  380 V, with the earth contact at the 6 h position. The circuit MCB does not exceed the socket outlet rating, and the
  circuit has a 30 mA RCD (*diferencial*, ID) if it feeds equipment that is plugged and unplugged.
- **Why:** they keep the IP rating with the plug connected and cannot be crossed between voltages: a
  220 V piece of equipment does not fit in a 380 V socket outlet. That is why they are used in site compounds (*obradores*), three-phase TUE, concrete mixers, welders and construction equipment.
- **How:**
  - Single-phase TUE: the AEA allows **16 A** IEC 60309 socket outlets as an alternative to the 20 A IRAM 2071 → MCB ≤ 16 A.
  - Three-phase construction equipment with a red 32 A 3P+N+E plug → circuit with a four-pole MCB ≤ 32 A, cable with Iz ≥ In
    (3 loaded conductors) and a 30 mA ID; for the site compound, see [site-safety.md](site-safety.md).
  - Outdoors or with water jets, IP44 or IP55 depending on the location, considering the assembly with the plug inserted.
- **Verify:** color and rating marked, IP of the assembly, MCB ≤ rating, ID test.
- **Don't:** put an IRAM 2073 plug on three-phase equipment; adapt a blue plug to a red socket outlet; protect a
  16 A socket outlet with a 32 A MCB.
- **Source:** AEA 771 Ed. 2006 p. 22, note 2 (IRAM-IEC 60309 assemblies to keep the IP with the plug connected; "220 Vca:
  color azul 6h; 380 Vca: color rojo 6h" (Vca = V AC; azul = blue, rojo = red); IP44 or IP55); AEA 770 Ed. 2017 770.6 b) (TUE with 16 A IEC 60309 socket outlets); catalog
  Kalop CAR-JUL2026 (industrial plugs and socket outlets 2P+E, 3P+E, 3P+N+E, 220/380 V, IP44, interlocked). **Not verified in
  a primary source:** the 16/32/63/125 A rating series (IEC 60309-2, from prior knowledge; confirm it in the catalog).

### ELEC-AMP-30: Copper busbars and distribution terminal blocks (*borneras repartidoras*): rated current from the catalog or the AEA table
- **Rule:** the busbars of a panel and the distribution terminal blocks (including the neutral and earth terminals) have a
  rated current that must not fall below the protection that feeds them. For copper busbars built on
  site, AEA 771 has a table of continuous current by busbar dimension (table 771.16.XII); for factory-made terminal blocks and busbars,
  the product catalog governs.
- **Why:** a 63 A terminal block behind a 100 A breaker is left without overload protection and is a hot
  spot; a small busbar in a closed panel heats up and accelerates the aging of everything around it.
- **How:** AEA table 771.16.XII is given for busbars in air, without forced ventilation, with **35 °C ambient and
  65 °C on the busbar**, bare or painted, and with 1, 2 or more busbars per phase: look up the dimension in your copy and correct if
  the panel is hotter. For terminal blocks: rated current and accepted cross-section in the manufacturer's sheet, and tighten to the
  stated torque (ELEC-AMP-22). The complete panel is checked for temperature rise ([panels.md](panels.md)).
- **Verify:** rated current printed or from the catalog ≥ In of the incoming device; cable cross-section within the terminal range;
  heat marks.
- **Don't:** use a 4 mm² DIN rail terminal block as the distribution point for a 16 mm² line; join busbars without the
  contact area and the bolts stated by the manufacturer.
- **Source:** AEA 771 Ed. 2006, 771.16.2.3.8 and table 771.16.XII (pp. 111-112: copper busbars in unventilated air, 35 °C
  ambient, 65 °C in service). **Not verified in a primary source:** the table values per dimension (the extracted text
  did not allow reading them reliably) and rated currents of manufacturers' terminal blocks (no data sheets were consulted).

## Catalogs used and stated origin

This table only says what was read and what the document itself says about origin. It is not a brand recommendation; comparison and
criteria in [manufacturers-and-materials.md](manufacturers-and-materials.md).

| Manufacturer | Documents read | Origin according to the document |
|---|---|---|
| Prysmian Energía Cables y Sistemas de Argentina | Superastic Jet/Flex, Sintenax Valio, Retenax Valio, TPR Ecoplus, VN 202, Retenax Preensamblado (Ed. 2026); Afumex 750, Prysal Aislado (Ed. 2020) | The marking specified in each sheet includes "Industria Argentina" (made in Argentina) |
| Cimet | CC/V, Zerotox 750 V (A2301); Ecoport CMXCC (A2212) | The sheets read do not state the country of manufacture. Secondary sources (Ingeniería Eléctrica magazine / Editores; company registry with activity "fabricación de hilos y cables aislados" (manufacture of insulated wires and cables)) describe it as an Argentine manufacturer with a plant in José León Suárez (Bs. As.); not verified in a primary source or per series |
| Marlew | Series VK, EK, CT | The Empresa (company) page of marlew.com.ar (consulted 2026-11-15) says "empresa Argentina ... en la fabricación" (Argentine company ... in manufacturing) and shows a plant at the Polo Industrial Ezeiza (Carlos Spegazzini); the sheets read do not state where each series is made |
| Jeluz | Catálogo Línea Protecciones (2026) | It presents itself as "empresa argentina dedicada a la fabricación" (Argentine company dedicated to manufacturing) with a plant in Spegazzini; the catalog does not say where the MCBs and RCDs are made: origin of that line not verified |
| Schneider Electric | Data sheets A9F74216, EZ9F34216, EZ9R36240, A9XPH212 (Argentina, Nov 2026) | The PIA and ID sheets show an IRAM certificate number; they do not state the country of manufacture: origin not verified |

## What this guide does not replace

- **The current AEA tables** (90364-7-771, 90364-7-770 in its current edition, 90364-5-52) or the design calculation: here
  there are indicative extracts. An installation is designed, calculated and signed by a qualified professional or technician with
  the relevant scope of license (*incumbencia*), with a technical report (see [regulations-and-permits.md](regulations-and-permits.md)).
- **The catalog and manual of the product being bought:** cable current-carrying capacity, curves, derating,
  ID-MCB coordination (Inc), tightening torque, compatible busbar combs (*peines*) and recommended protection for each piece of equipment.
- **The utility's (*distribuidora*) data** on short-circuit current, service connection (*acometida*) and the fuses in the utility service box (*caja de toma*).
- **Measurement:** clamp meter, leakage clamp meter, RCD tester, thermography and megohmmeter (megger)
  ([testing-and-commissioning.md](testing-and-commissioning.md)).
- **The complete IRAM and IEC standards** (IRAM NM 247-3, IRAM 2178-1, IRAM 2071, IRAM 2073, IEC 60898-1, IEC 61008-1, IEC 60269,
  IEC 60947-3/-4-1, IEC 60309),
  which are paid and are consulted in their official text.
- **Work safety:** nothing in this guide authorizes live work; see [site-safety.md](site-safety.md).
