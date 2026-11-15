---
title: Electrification grades, circuits and demand
scope: design of the internal installation of a house, apartment, office or single shop in Argentina under AEA 90364-7-771 and 7-770; electrification grade, circuit types and their limits, minimum outlet points (bocas) per room, socket outlets, nameplate power of appliances, calculation of the maximum simultaneous power demand (DPMS) and of the total load, moving to single-phase or three-phase supply, "all-electric" home and extensions
when_to_use: when designing or reviewing how many circuits and outlet points a unit needs; when building the load schedule; when deciding whether single-phase is enough or three-phase must be requested; when someone wants to hang an air conditioner, a cooktop, a heater or a water heater on a socket outlet circuit; before adding a large load to an existing installation; before sizing conductors, protection and panel
related: [README.md, regulations-and-permits.md, conductors-and-conduits.md, protection.md, earthing.md, panels.md, buildings.md, site-safety.md, testing-and-commissioning.md, troubleshooting-common-cases.md, special-installations.md, reviewing-a-panel.md]
as_of: 2026-11-15
sources: [AEA 90364-7-771 Viviendas, oficinas y locales (unitarios) (dwellings, offices and single shops) Ed. 2006 (clauses 771.7, 771.8, 771.9, 771.13), AEA 90364-7-770 Viviendas unifamiliares hasta 63 A (single-family houses up to 63 A) Ed. 2017 + Corrigendum 1 Aug 2018 (clauses 770.6 to 770.8, 770.11; edition prior to Ed. 2026, digital on sale and print on pre-order in the AEA store consulted 2026-11-15), AEA 90364-7-772 Espacios comunes y servicios generales (common areas and common services) Ed. 2019 (emergency regulation; 772.9.2 and table 772.9.III), AEA 90364-7-701 Ed. 2012 (bathrooms), ENRE Reglamento para la conexión de nuevos suministros domiciliarios (regulation for connecting new residential supplies) (Res. ENRE 225/2011, 2022 edition of the text), Decreto 452/2025 (ENReGE), EDELAP Reglamento de acometidas T1 (T1 service connection regulation) (2020), EDELAR EC 1.1.13.10 v3 (2023), Ley 19.587 and Decreto 351/79 (ch. 12 and annex IV)]
---
# Electrification grades, circuits and demand

How to decide how many circuits and how many outlet points (*bocas*) a unit needs, what can be hung on each circuit and how much
power must be provided for. Each rule has an ID (`ELEC-CIR-n`) so the agent, a review or a message can cite it ("the AC is on a
TUG: see ELEC-CIR-9"). Numeric values carry their source. AEA standards are paid: here they are summarized and the clause or
table is cited; for the full text you need a copy.

For the calculations (DPMS, total load, current, split across phases) the agent uses the offline calculator
`gateway electricidad ...` (demand/grade, current, cross-section, coordination) and does not calculate from memory. The worked
examples below are for understanding the method and for checking what the calculator returns.

This guide covers **design on paper**. Wiring, connecting or modifying a panel (distribution board, *tablero*) is always done
dead: switched off, locked out, verified dead and tagged (see [site-safety.md](site-safety.md)). An MCB (*térmica*) in the off
position does not guarantee that the circuit is dead: verify with an instrument before touching.

## Which standard applies (as of 2026-11-15)
| Document | Edition | Covers | Source |
|---|---|---|---|
| AEA 90364-7-771 | 2006 (in force; no later edition was found) | Dwellings, offices and **single** shops: apartments in buildings, offices, shops, and houses outside the scope of the 770 | Foreword published by AEA; the AEA store lists "Ed. 2006" |
| AEA 90364-7-770 | **Ed. 2026 published** (digital on sale; print on pre-order). The values cited in this guide are from **Ed. 2017 + Corrigendum 1 (2018), the previous edition** (AEA has not published an effective date for the 2026 edition) | Single-family house with incoming device up to 63 A, prospective short circuit up to 10 kA at the origin, BA2 users and BD1 evacuation (see ELEC-CIR-1) | AEA store (consulted 2026-11-15): "DIGITAL AEA 90364-7-770" Ed. 2026 with no pre-order mark; 2017 text |
| AEA 90364-7-772 | 2019, approved as an **emergency regulation** (board of directors, session of 2019-09-25, for 2 years) and in force according to its text; the AEA store still lists Ed. 2019 | Common areas and common services of buildings (landings, elevator, pumps) and demand of the set of units (772.9.2) | Text of 772:2019; AEA store. Covered in [buildings.md](buildings.md) |

> **4-story apartment building** (this guide's example case): each apartment (*depto*) is designed with the **771**; the
> common services and the demand of the whole building, with the **772**. The 770 is the simplified section for the single-family house. The
> 770 values cited here are from **Ed. 2017, prior to Ed. 2026** (which AEA already sells, with no published effective date): the agent does not present them as
> in force for a new house without confirming them in the 2026 copy.

## Quick reference
| Situation | Rule |
|---|---|
| I don't know whether to use the 770 or the 771 | ELEC-CIR-1 |
| Calculate the area and the grade of a unit | ELEC-CIR-2, ELEC-CIR-3 |
| Minimum number of circuits it must have | ELEC-CIR-4 |
| What can be hung on each circuit type and how many outlet points; which MCB goes | ELEC-CIR-5, ELEC-CIR-6 |
| How many outlet points per room | ELEC-CIR-7 |
| A socket outlet in the light switch box, or in the small bathroom | ELEC-CIR-8 |
| Air conditioner (frigories), cooktop, oven, water heater | ELEC-CIR-9, ELEC-CIR-10, ELEC-CIR-22 |
| Yard, garden, balcony, water or booster pump, float switch | ELEC-CIR-11 |
| Build the load schedule (DPMS and total load) | ELEC-CIR-12, ELEC-CIR-13 |
| Single-phase or three-phase? How much power do I request? | ELEC-CIR-14, ELEC-CIR-15 |
| Split circuits across phases | ELEC-CIR-16 |
| Several apartments or shops in the same building | ELEC-CIR-17 |
| Office, shop or other use | ELEC-CIR-18 |
| Leave room to grow | ELEC-CIR-19 |
| What must be left in writing | ELEC-CIR-20 |
| Which socket outlet goes, at what height, "universal" socket outlets | ELEC-CIR-21 |
| How much each appliance draws; heaters and fan heaters | ELEC-CIR-22 |
| How many circuits per RCD (*disyuntor* / *diferencial*) | ELEC-CIR-23 |
| House or apartment without gas ("all-electric") | ELEC-CIR-24, Example C |
| Add an air conditioner or an electric cooker to an existing installation | ELEC-CIR-25 |
| From the apartment to the sub-panel (TS, *tablero seccional*) (4-story building case) | Example A, step 8 |

## Reference tables

### Electrification grades
Area = covered area + 50 % of the semi-covered area (ELEC-CIR-2). The maximum DPMS column exists only in the 771: in the 770
the grade comes from the area alone. In both, the DPMS is used to size the line and the power; in the 771 it also confirms
the grade (ELEC-CIR-3).

| Grade | House / apartment: area | House: max. DPMS (771 only) | Office or shop built for that purpose: area | Office/shop: max. DPMS |
|---|---|---|---|---|
| Minimum | up to 60 m² | up to 3.7 kVA | up to 30 m² | up to 4.5 kVA |
| Medium | over 60 m² up to 130 m² | up to 7 kVA | over 30 m² up to 75 m² | up to 7.8 kVA |
| High | over 130 m² up to 200 m² | up to 11 kVA | over 75 m² up to 150 m² | up to 12.2 kVA |
| Superior | over 200 m² | over 11 kVA | over 150 m² | over 12.2 kVA |

Source: AEA 90364-7-771:2006, 771.8.2.1 (see table 771.8.I) and 771.8.3.2.1 (see table 771.8.IV). The 770:2017 (edition
prior to 2026) uses the same area thresholds for houses, with no DPMS limit (770.7.3, see table 770.7.I).

### Minimum number of circuits (dwellings)
| Grade | 771:2006 (apartments, houses outside the 770) | 770:2017, edition prior to 2026 (single-family house) |
|---|---|---|
| Minimum | 2: 1 IUG + 1 TUG | 2: 1 IUG + 1 TUG |
| Medium | 3: 1 IUG + 1 TUG + a third one (IUG, TUG, IUE or TUE) | 3: 2 IUG + 1 TUG, or 1 IUG + 2 TUG |
| High | 5: 2 IUG + 2 TUG + 1 TUE | 5: 2 IUG + 3 TUG, or 3 IUG + 2 TUG |
| Superior | 6: 2 IUG + 2 TUG + 1 TUE + 1 of free choice | 6: either of the two High variants + 1 of free choice |

Source: 771.8.2.2 (see table 771.8.II); 770.7.4 (see table 770.7.II). Specific-use circuits (ACU, APM, etc.) are added
to these minimums, they do not replace them (771.7.6 c).

### Circuit types
| Code | What it is | Max. outlet points | Cap on the protection for the type (**not** the MCB to fit) | Load per outlet point / socket outlet | Min. cross-section |
|---|---|---|---|---|---|
| IUG | General-use lighting (includes ceiling fans, extractor fans) | 15 | 16 A | up to 10 A; 2P+E 10 A socket outlet IRAM 2071 | 1.5 mm² (2.5 mm² if it has branch socket outlets) |
| TUG | General-use socket outlets | 15 | 20 A | up to 10 A; 2P+E 10 A socket outlet IRAM 2071 | 2.5 mm² |
| IUE | Special-use lighting (outdoor, lighting loads > 10 A) | 12 | 32 A | lighting only | 2.5 mm² |
| TUE | Special-use socket outlets | 12 (771) / 15 (770:2017) | 32 A | up to 20 A with 2P+E 20 A socket outlet IRAM 2071 (or 16 A IEC 60309); 10 A socket outlets can be added at the same outlet point | 2.5 mm² |
| APM | Single-phase supply for small motors (ventilation, gates, roller shutters, small pumps, commercial refrigerators) | 15 | 25 A | up to 10 A | 2.5 mm² |
| MBTF | Supply for functional extra-low voltage sources (door entry phone, alarm, CCTV) | 15 (at 220 V) | 20 A | up to 10 A | 1.5 mm² |
| ATE | Stabilized voltage supply / UPS (red or identified socket outlets) | 15 | at the designer's discretion | at the designer's discretion | 2.5 mm² |
| MBTS | Unearthed extra-low voltage (up to 24 V); its source is fed from an ACU | no limit | at the designer's discretion | at the designer's discretion | 2.5 mm² (specific use, except MBTF); at 12-24 V the voltage drop usually calls for more |
| ACU | Single-load supply, single-phase or three-phase, without branches | not applicable (one load) | at the designer's discretion | the load | 2.5 mm² |
| ITE | Specific three-phase lighting (only with BA4/BA5 personnel) | 12 per phase | at the designer's discretion | up to 10 A | 2.5 mm² |
| OCE | Other specific circuits | no limit | at the designer's discretion | at the designer's discretion | 2.5 mm² |

Source: 771.7.6 and table 771.7.I (summary); minimum cross-sections: table 771.13.I and table 770.11.I (2017). In the 770:2017 only IUG,
TUG and TUE have their own limits (table 770.6.I); for the rest it refers to the 771. Feed and return of light switches
(*interruptores de efecto*): 1.5 mm² in the 771, 1 mm² in the 770:2017; protective conductor: 2.5 mm² minimum in both. The minimum cross-section of
0.5 mm² for control circuits that carry no power (home automation) is a note to table 770.11.I (Ed. 2017); the 771 does not
have it.

> **The cap is not the MCB.** The "cap" column says how far the protection for that circuit type may go. The
> actual MCB is chosen by the current-carrying capacity (Iz) of the cable **as installed**: Ib ≤ In ≤ Iz (see
> [protection.md](protection.md) ELEC-PRO-4 and [conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-8).
> A 25 or 32 A MCB on a 2.5 mm² cable **does not protect it against overload: fire risk.**

| Cross-section (copper, single-core cables in conduit, one circuit only, 40 °C) | Indicative Iz | Usual MCB | What it is enough for |
|---|---|---|---|
| 1.5 mm² | 15 A | **10 A** | IUG (16 A does not comply: 16 > 15) |
| 2.5 mm² | 21 A | **16 A** (20 A only if it runs alone in the conduit and the Iz of the installed cable allows it) | TUG, TUE, IUE, APM, small ACU; 16 A IUG |
| 4 mm² | 28 A | 25 A | 25 A TUE or ACU |
| 6 mm² | 36 A | 32 A | 32 A TUE or ACU (induction cooktop) |

Source of Iz: AEA 90364-7-770:2017, table 770.12.I, method B1, column for 2 loaded conductors (see
[conductors-and-conduits.md](conductors-and-conduits.md)); in the 771 the equivalent table is 771.16.I. With two or
more circuits in the same conduit, or higher temperature, Iz drops (grouping factor): recalculate with `gateway electricidad`.

### Conventional powers for the DPMS
| Circuit | 771:2006, dwellings | 771:2006, offices and shops | 770:2017 (edition prior to 2026) |
|---|---|---|---|
| IUG without branch socket outlets | 66 % × outlet points × 150 VA | 100 % × outlet points × 150 VA | 2/3 × outlet points × 60 VA |
| IUG with branch socket outlets | 2200 VA per circuit | 2200 VA per circuit | 2200 VA per circuit |
| TUG | 2200 VA per circuit | 2200 VA per circuit | 2200 VA per circuit |
| IUE | 66 % × outlet points × 500 VA | 100 % × outlet points × 500 VA | (it is specific in the 770) |
| TUE | 3300 VA per circuit | 3300 VA per circuit | 3300 VA per circuit |

| Diversity (simultaneity) factor of the unit | Value |
|---|---|
| 771, by grade: Minimum / Medium / High / Superior | 1 / 0.9 / 0.8 / 0.7 |
| 770:2017 (prior to 2026), by minimum number of circuits: 2 / 3 / 5 / 6 | 1 / 0.8 / 0.7 / 0.6 |

Source: tables 771.9.I and 771.9.II; tables 770.8.I and 770.8.II (2017). They are **minimums**: if you know the actual load and it is higher, the
actual load applies.

## Rules

### ELEC-CIR-1: First, define which section applies to each part of the property
- **Rule:** each apartment, office or shop in a building is designed with AEA 90364-7-771:2006; the common services of the
  building and the demand of the whole, with the 772:2019; the 770 is for the single-family house that meets all three at once: incoming device up to
  63 A, prospective short circuit up to 10 kA at the origin, and BA2 users / BD1 evacuation. If it fails any of the three, the 771 applies.
- **Why:** the 770 is a simplified version meant for the simple house; AEA itself says that for houses over
  63 A or over 10 kA, for BA3 to BA5 users, for BD2 to BD4 evacuation, and for offices and shops, you go with the 771. The
  two give different numbers (TUE outlet points, power per lighting outlet point, factors), so mixing them gives schedules that don't add up.
  The codes are external influences from AEA 90364 part 3 (equivalent to IEC 60364-5-51): **BA2** = children may be present;
  **BA3** = people with disabilities; **BA4 / BA5** = instructed / skilled personnel; **BD1** = low occupancy and easy
  evacuation; **BD2 to BD4** = more people or difficult evacuation.
- **How:** write in the design report (*memoria*), per unit: use (dwelling, office, shop), section applied and edition. If the
  authority having jurisdiction (municipality, provincial regulator) requires a particular section or edition, that governs (see
  [regulations-and-permits.md](regulations-and-permits.md)). In a mixed-use property (shop with a dwelling above) separate each
  use and calculate each one with its own table (771.8.1.4). For a new single-family house, get the 770 Ed. 2026: the numbers from
  Ed. 2017 in this guide may have changed.
- **Verify:** the design report names section and edition per unit; the prospective short circuit at the origin is given by the utility (distribution company) or
  calculated (see [protection.md](protection.md)); in a building near a transformer it can exceed 10 kA.
- **Don't:** apply the 770 to a commercial shop or an office; use the table of one section and the factors of the other.
  Some people apply the 770 to each apartment because its clause 770.4.1.3 (Ed. 2017) mentions dwellings that are part of
  buildings: if you want to do that, get the authority having jurisdiction to accept it, in writing.
- **Source:** AEA 90364-7-770:2017, Consideraciones generales (general considerations) and 770.1 (scope); AEA 90364-7-771:2006, 771.1 and
  771.8.1.4; AEA store (770 Ed. 2026 digital on sale and print on pre-order; 771 Ed. 2006; 772 Ed. 2019), consulted
  2026-11-15. BA/BD classification: AEA 90364 part 3 / IEC 60364-5-51. **Not verified in a primary source:** whether the 770 Ed. 2026
  changed the scope (63 A, 10 kA, BA2/BD1).
### ELEC-CIR-2: Area is measured per unit: covered area + 50 % of the semi-covered area
- **Rule:** the grade of each unit comes from its own covered area plus half of the semi-covered area (roofed balcony,
  gallery). It is calculated unit by unit, never with the area of the whole building.
- **Why:** the grade sets the minimum circuits and outlet points (*bocas*) of that unit. If you add up the whole building, a studio apartment ends up
  sized as Superior (the utility EDELAR flags this as a typical error in its procedure).
- **How:** covered area = sum of the rooms including walls and partitions; semi-covered = roofed but without full
  enclosure. Example: apartment (*depto*) of 55 m² covered with a 6 m² roofed balcony → 55 + 0.5 × 6 = **58 m²** → Minimum grade
  (up to 60 m²). A loft is taken by its total area. If a dwelling under 130 m² has a bedroom over 36 m²,
  the standard says that "los puntos mínimos de utilización deben ser tomados del grado de electrificación elevado" (the minimum points of use must be taken from the High electrification grade), without limiting it to
  that bedroom. Reading it as applying only to the bedroom is an interpretation; the conservative approach is to apply the minimum points of the
  High grade to the whole dwelling, or to consult the authority having jurisdiction.
- **Verify:** the design report shows both areas and the calculation; the architectural drawing matches.
- **Don't:** count the open balcony or the terrace at 50 % (it is not semi-covered); take the area of the lot.
- **Source:** AEA 90364-7-771:2006, 771.7.6 note 4 (area definitions), 771.8.1.1 and 771.8.2.3 note 1; 770:2017, 770.7.3
  and 770.7.5 note 1; EDELAR, EC 1.1.13.10 v3 (2023), p. 3-4.

### ELEC-CIR-3: In the 771 the grade is preset by area and confirmed with the DPMS
- **Rule:** with the area you preset the grade; you place the minimum outlet points, assign them to circuits, calculate the DPMS (maximum simultaneous power demand, with its
  factor) and compare it with the grade's limit. If it exceeds it, you move up to the next grade and repeat. If it comes out below the lower
  grade, you keep the grade from the area (it never goes down).
- **Why:** a small apartment with many loads (a kitchen TUE, an extra TUG) needs more circuits and outlet points than
  its area suggests. The 770 simplified this: the grade comes from the area alone.
- **How:** follow steps a) to d) of 771.8.1.5. Use `gateway electricidad` (demand/grade) to iterate. Worked examples further
  below: a 98 m² apartment preset as Medium gives 8267 VA > 7 kVA and moves to High (Example B); a 58 m² one to which
  a kitchen TUG is added moves from Minimum to Medium (Example A, step 7). Watch out: when the grade goes up the factor goes down, so the
  DPMS of the new grade can come out **lower** than that of the previous one. It is not a calculation error: what changes is that the unit must
  meet the minimum circuits and outlet points of the new grade. To size the line, use the DPMS of the final grade (or the actual
  loads, if higher); sizing with the larger of the two values is a conservative criterion of this guide, not of the standard.
- **Verify:** the schedule shows the DPMS after the factor and the limit of the chosen grade, and the comparison.
- **Don't:** keep the grade by area without doing the DPMS check when you apply the 771; apply the factor
  of the lower grade to "fit" into it.
- **Source:** AEA 90364-7-771:2006, 771.8.1.5, 771.8.2.1 (see table 771.8.I) and 771.9.1 (last paragraph, the grade does not go down because of the
  factor); 770:2017, 770.7.3.

### ELEC-CIR-4: The minimum number of circuits is a floor, and specific circuits come on top
- **Rule:** the unit has at least the general and special-use circuits set by its grade (table above). Specific-use
  circuits (ACU for an AC, APM for a gate, MBTF for a door entry phone) are added; they don't count toward meeting the minimum, except the
  "free-choice circuit" of the Superior grade.
- **Why:** the minimum spreads the load and makes a fault leave only part of the unit without service; an ACU for the AC does not replace the
  second socket outlet circuit.
- **How:** 771 Minimum = 1 IUG + 1 TUG; Medium = 3 (1 IUG, 1 TUG and a third IUG, TUG, IUE or TUE); High = 2 IUG + 2 TUG + 1 TUE;
  Superior = 2 IUG + 2 TUG + 1 TUE + 1 of free choice. In the 770:2017 there are variants without TUE (see table). If a circuit reaches
  its maximum number of outlet points (ELEC-CIR-5), add another one even if the minimum is already met.
- **Verify:** on the single-line diagram, count circuits by type and compare them with the grade; no circuit exceeds its maximum number of outlet points.
- **Don't:** "one for lights and one for sockets" for a 100 m² apartment; count the AC's ACU as the third circuit of the Medium grade.
- **Source:** AEA 90364-7-771:2006, 771.8.2.2 (see table 771.8.II) and 771.7.6 c) (specific circuits are supplementary); 770:2017,
  770.7.4 (see table 770.7.II).

### ELEC-CIR-5: Each circuit type has a cap on outlet points, load per outlet point, protection and cross-section
- **Rule:** for each circuit respect the maximum number of outlet points, the maximum load per outlet point, the protection cap and the minimum cross-section from
  the "Circuit types" table. The MCB (*térmica*) you actually fit comes from the Iz of the installed cable and can (usually does) come out below
  the cap. If a load does not fit within those limits, it goes to another circuit type.
- **Why:** the caps are meant to make the statistical load of the circuit (2200 VA for a TUG, 3300 VA for a TUE) realistic;
  the cable's protection comes from the rule Ib ≤ In ≤ Iz. A 1.5 mm² IUG with a 16 A or 20 A MCB is not protected against
  overload (Iz ≈ 15 A).
- **How:** IUG: up to 15 outlet points; with 1.5 mm², a **10 A** MCB (16 A only with 2.5 mm²). TUG: up to 15 outlet points, 2.5 mm², usual
  MCB **16 A** (cap 20 A), loads up to 10 A with a 2P+E 10 A socket outlet. TUE: up to 12 outlet points (771), loads up to 20 A with a
  2P+E 20 A socket outlet; with 2.5 mm² a 16 A MCB (20 A if the Iz of the installed cable allows it). The cap for the type is 32 A (by Iz, 25 A
  calls for 4 mm² and 32 A for 6 mm²), but since TUE socket outlets are 20 A (or 16 A IEC 60309), this guide does not protect it with more than
  20 A (16 A with IEC 60309): safety criterion from [current-ratings-and-devices.md](current-ratings-and-devices.md)
  ELEC-AMP-19; a larger load goes to an ACU. The MCBs of these circuits are two-pole, with protection on both poles
  (phase and neutral): see [protection.md](protection.md) ELEC-PRO-1.
- **Verify:** in the panel (distribution board, *tablero*), each MCB meets In ≤ Iz of the cable it protects and does not exceed the cap of its type; no single-pole
  PIA nor "1P+N"; on the drawing, outlet points per circuit numbered and counted.
- **Don't:** fit a 25 or 32 A MCB on 2.5 mm² "because the table says max. protection 32 A"; increase the MCB rating
  "because it trips" (see [troubleshooting-common-cases.md](troubleshooting-common-cases.md)); use 10 A socket outlets as the only outlet of a
  TUE for a 16 A load; use single-pole MCBs on dwelling circuits; trust that an MCB in the off position leaves the circuit
  dead (verify absence of voltage: [site-safety.md](site-safety.md) ELEC-SEG-5).
- **Source:** AEA 90364-7-771:2006, 771.7.6 a), b), c), table 771.7.I, table 771.13.I, 771.16 (current-carrying capacities) and 771.19
  (overload); disconnection of all poles: 771.20.5 and foreword of the 771 ("corte bipolar, tripolar o tetrapolar según el tipo de
  circuito", two-pole, three-pole or four-pole disconnection according to the circuit type); 770:2017, 770.6 (table 770.6.I), table 770.11.I, table 770.12.I and 770.16.5.1 (prohibits single-pole PIA and 1P+N).
  **Not verified in a primary source:** the exact text of 771.20.5 (cited as given in [protection.md](protection.md)).

### ELEC-CIR-6: Count the outlet points correctly
- **Rule:** an outlet point is the point where an appliance is connected (socket outlet, splice or terminal block). Junction or branch boxes are not outlet points, nor
  are boxes that only hold switches. A rectangular box takes up to 2 socket outlets and a square one up to 4, and it counts as one outlet point.
- **Why:** the maximum per circuit is measured in outlet points; miscounting leads to 25-point circuits or to oversizing for no reason.
- **How:** more than 4 socket outlets in one box: outlet points = socket outlets ÷ 4, rounded up. Boxes in the concrete slab up to 100 × 100 mm count
  as an outlet point; larger ones do not. A mixed outlet point (switch + socket outlet, see ELEC-CIR-8) counts as one outlet point. A ceiling fan or
  extractor fan counts as one lighting outlet point. Each door entry phone or doorbell power supply hung on an IUG counts as one lighting outlet point; if
  instead they are handled as a specific circuit, all those supplies can go on one circuit as long as the sum of their
  powers does not exceed 2200 VA (771.8.5 j). Socket outlets mounted in the panel: up to 4 of the same circuit count as one outlet point
  (770.7.2, Ed. 2017).
- **Verify:** schedule with outlet points per circuit; each number on the drawing corresponds to a circuit.
- **Don't:** count the hallway junction box as an outlet point; put 6 socket outlets in a rectangular box.
- **Source:** AEA 90364-7-771:2006, 771.7.6 note 1 and 771.8.5 a), c), j), o), p); 770:2017, 770.7.1 a), c), f), l), m) and 770.7.2.

### ELEC-CIR-7: Meet the minimum points for each room
- **Rule:** each room has at least the lighting and socket outlet points set by its grade. Integrated rooms
  (kitchen with everyday dining area) meet the minimums of each part separately; a kitchenette adds its own minimums.
- **Why:** too few socket outlets end up in power strips and extension cords, which are a frequent cause of overheating.
- **How:** summary for dwellings under the 771:2006 (detail and exceptions in table 771.8.III and in 771.8.2.3; the 770:2017 has
  its own table 770.7.III, almost the same but without mandatory TUE outlet points):

  | Room | Lighting (IUG) | Socket outlets (TUG) | TUE |
  |---|---|---|---|
  | Living room, dining room, study, everyday dining area | 1 per 18 m² or fraction (min. 1) | 1 per 6 m² or fraction (min. 2) | High/Superior: 1 if the room exceeds 36 m² |
  | Bedroom < 10 m² (with built-in wardrobe) | 1 | 2 | — |
  | Bedroom from 10 to 36 m² | 1 | 3 | — |
  | Bedroom > 36 m² (High/Superior; see ELEC-CIR-2) | 2 | 3 | 1 |
  | Kitchen | Minimum 1; Medium and above 2 | Min./Medium: 3 outlet points + 2 socket outlets for fixed appliances; High: 3 + 3; Superior: 4 + 3 | High/Superior: 1 |
  | Bathroom (see note) | 1 (High/Superior: 1 per compartment if divided) | 1 | — |
  | Vestibule, hall, garage (up to 3 cars), gallery, dressing room | 1 | Minimum: 1; Medium and above: 1 per 12 m² or fraction | — |
  | Hallway | 1 per 5 m or fraction | Medium and above, if longer than 2 m: 1 per 5 m or fraction | — |
  | Laundry | 1 | Minimum: 1; Medium and above: 2 | High/Superior: 1 |
  | Balcony, atrium or external corridor that only needs light and is not exposed to the weather; stairs | 1 per 5 m of length (stairs: 1 per 5 m or per landing) | — | — |
  | Semi-covered balcony-terrace used as a room | as vestibule | as vestibule | — |
  | Kitchenette (in addition to the room where it is) | 1 over the countertop | 2 + 1 socket outlet for a fixed appliance | — |

  The kitchen's "socket outlets for fixed appliances" (refrigerator, dishwasher, microwave, oven, washing machine, gas cooktop with
  electric ignition) are additional socket outlets: they can go in the same boxes as the TUG.

  **Bathroom note:** the socket outlet goes **outside zones 0, 1 and 2** (never next to the shower or the bathtub) and with a
  30 mA RCD (*disyuntor* / *diferencial*): see [special-installations.md](special-installations.md) ELEC-ESP-3 and ELEC-ESP-4 (AEA 90364-7-701:2012) and
  [protection.md](protection.md).

  **Practical recommendation (not a requirement of the 771): a TUG for the kitchen only**, even if the grade calls for a single TUG. Electric
  kettle 2200 W + microwave 1200 W + air fryer 1500 W = 4900 W → 4900 ÷ 220 V = **22.3 A**, more than the TUG's 20 A cap
  and the usual 16 A MCB: this is the most common "the MCB trips" and "melted plug" case (see
  [troubleshooting-common-cases.md](troubleshooting-common-cases.md)). The same goes for the laundry if the washing machine heats water. Watch out:
  in the 771 that extra TUG adds 2200 VA to the DPMS and can raise the grade (Example A, step 7).
- **Verify:** go through the drawing room by room with the grade's table; hallways longer than 3 m have a two-way
  switch at each end.
- **Don't:** consider the kitchen done with "one socket outlet for the refrigerator"; forget the laundry or the balcony; put the bathroom socket outlet
  inside the zones.
- **Source:** AEA 90364-7-771:2006, 771.8.2.3.1 to 771.8.2.3.3 (see table 771.8.III; the table places the everyday dining area with the
  vestibule, but 771.8.5 f) and the 770 treat it as a living room: here the stricter criterion is taken), 771.8.5 d) to h) and r), 771.8.6.1;
  770:2017, 770.7.1 j) and o), 770.7.2, 770.7.5 (see table 770.7.III); AEA 90364-7-701:2012 (bathroom zones). Appliance
  powers: typical nameplate values, the nameplate governs (ELEC-CIR-22).

### ELEC-CIR-8: A socket outlet on the lighting circuit, only above 0.90 m and identified
- **Rule:** once the minimum points are met, a socket outlet may be fitted next to the light switch (mixed outlet point) connected to the
  lighting circuit of that box, always at 0.90 m or more above the finished floor and marked with the IEC 60417-5012 symbol. Below 0.90 m, every
  socket outlet goes on a socket outlet circuit.
- **Why:** low socket outlets are the ones used for large loads (heaters, vacuum cleaners); on a 1.5 mm² IUG with 10 A
  they overload or trip the lighting circuit and the room is left in the dark.
- **How:** an IUG with branch socket outlets is counted at 2200 VA (not with the power per outlet point) and wired with 2.5 mm². In a
  powder room (bathroom without shower or bathtub) the minimum socket outlet may go on the lighting circuit. If a low socket outlet is controlled by a switch, the
  switch goes in a box separate from the light switches.
- **Verify:** height of each mixed outlet point; symbol on the cover plate; cross-section of the IUG with socket outlets.
- **Don't:** "hang" baseboard-level socket outlets off the lighting circuit; use mixed outlet points to meet the minimum socket outlet points.
- **Source:** AEA 90364-7-771:2006, 771.8.5 n) and p), table 771.9.I and table 771.13.I; 770:2017, 770.7.1 k) and m), table 770.8.I.

### ELEC-CIR-9: Loads over 10 A don't go on general-use socket outlets
- **Rule:** a TUG or an IUG feeds loads up to 10 A per 10 A socket outlet. Anything that draws more (electric oven, cooktop, large water
  heater, large air conditioner, multi-stage heater) goes on a TUE (up to 20 A per 20 A socket outlet) or on its own
  single-load circuit (ACU). Above 20 A, ACU or another specific circuit (OCE), without a 10 or 20 A socket outlet.
- **Why:** the TUG is sized with a statistical 2200 VA for the whole circuit. A 2.5 kW AC plus the refrigerator and the microwave
  on the same TUG take it to the MCB's limit, and 10 A plugs working near their maximum for hours are the ones that
  burn.
- **How:**
  - **Value to use:** the rated nameplate current (A) or the **electrical** power consumed (W). Never the frigories or the watts
    of cooling capacity: 1 frigorie/h = 1.163 W **thermal**, and the electrical power is about three times lower. With EER
    3.2: 2250 fg ≈ 0.8 kW electrical; 3000 fg ≈ 1.1 kW; 4500 fg ≈ 1.6 kW; 6000 fg ≈ 2.2 kW (order of magnitude; the nameplate and the
    energy efficiency label govern, which declares consumption separately from capacity). Detail in
    [special-installations.md](special-installations.md) ELEC-ESP-10.
  - **Current:** I = P ÷ (U × cos φ). For the schedule in VA: S = U × nameplate I, or S = P ÷ cos φ. Example: large AC (about
    7000 frigories) with 2600 W electrical consumption, cos φ 0.9, 220 V → I = 2600 ÷ (220 × 0.9) = **13.1 A** → does not fit on a TUG; it goes to a
    TUE or ACU. S = 2600 ÷ 0.9 = 2889 VA.
  - **Small split unit:** a 1000 W one gives 1000 ÷ (220 × 0.9) = 5.1 A and technically fits on a TUG, but in a new design each AC goes
    on its own circuit (ACU) or on a TUE (ELEC-CIR-10). In an existing installation, if it stays on a TUG, it should be the only significant fixed
    load on that circuit.
  - **Starting:** on-off units draw several times the rated current when the compressor starts (C curve MCB); inverter units start
    softly but go with a type A RCD (see [protection.md](protection.md) ELEC-PRO-2 and ELEC-PRO-9).
  - **Electric oven** up to about 3.5 kW (≤ 16 A on the nameplate): TUE with a 2P+E 20 A socket outlet, or ACU. At 3.5 kW (15.9 A) a 16 A
    MCB is tight: 4 mm² with 20 A gives margin (always In ≤ Iz). **Electric or induction cooktop**
    over 20 A (4 burners: about 6 to 7.4 kW → 7200 W ÷ 220 V = 32.7 A): its own ACU, fixed connection or whatever the
    manufacturer specifies, cross-section and MCB by calculation (typically 6 mm² and 32 A single-phase), and in the schedule with its nameplate power
    as a specific load, not as the TUE's 3300 VA. **Electric water heater:** this guide's recommendation is a dedicated ACU (continuous
    load for hours); the standard allows a TUE for loads up to 20 A.
  - The ACU has no branches: one load, one circuit, its protection and its RCD (see [protection.md](protection.md)).
- **Verify:** list of fixed appliances with nameplate current or power against the assigned circuit; no load over
  10 A on a 10 A socket outlet; none over 20 A with a socket outlet.
- **Don't:** plug the AC into the bedroom TUG "because there's a socket outlet"; swap the 10 A socket outlet for a 20 A one on a TUG;
  take "a 3000 AC" as 3000 W; feed a 7 kW induction cooktop from a 20 A socket outlet.
- **Source:** AEA 90364-7-771:2006, 771.7.6 a) II, b) II (TUE for single loads up to 20 A with a 2P+E 20 A or 16 A IEC
  60309 socket outlet) and c2) II; 771.8.5 b) (over 20 A: ACU or OCE); 770:2017, 770.6 a) II and b). 1 kcal/h = 1.163 W (definition).
  **Not verified in a primary source:** EER, cos φ and example powers (typical catalog values; always use the unit's nameplate).
### ELEC-CIR-10: Air conditioners and kitchen: dedicated circuits from the design stage
- **Rule:** plan from the design stage one circuit for each AC unit (ACU, or a TUE if they are small units grouped with
  calculation) and, if cooking or the oven is electric, its circuit: TUE for an oven up to 16 A, ACU for a cooktop or cooker over
  20 A (ELEC-CIR-9). The cable linking the indoor unit to the outdoor unit, if longer than 3 m, is part of the installation and
  complies with the regulations.
- **Why:** it is the most common design error in apartments (*deptos*): the AC is added later on the TUG and the circuit ends up
  overloaded right at the hottest hours. In hot provinces the utility (distribution company) may require a diversity (simultaneity) factor of 1 for the
  ACs (EDELAR recommends it for groups of up to 15 units).
- **How:** leave conduit and a box in the wall where each condensing unit will go, even if the unit is bought later. Assign the nameplate
  power (or a conservative estimate) in the schedule as a specific load (ELEC-CIR-13). In High and Superior the 771 already requires
  a TUE outlet point (*boca*) in living rooms or bedrooms over 36 m², and allows placing it on the outside wall for the AC.
- **Verify:** single-line diagram with one circuit per AC unit; spare conduit to each condensing unit position; interconnection
  cable suited to the voltage and the current.
- **Don't:** leave the kitchen without a special circuit when the cooktop or the oven is electric; feed two large ACs from the
  same TUE without calculation.
- **Source:** AEA 90364-7-771:2006, 771.8.2.3.3 a) and d), 771.7.6 c); 770:2017, 770.1 (cables between units longer than 3 m are
  part of the installation); EDELAR, EC 1.1.13.10 v3 (2023), p. 5. "One circuit per AC unit" is recommended practice, not
  a literal requirement of the standard.

### ELEC-CIR-11: Outdoors, weather exposure and wet locations have their own rules
- **Rule:** in the 771, lighting in locations exposed to the weather goes on **IUE** and socket outlets exposed to the weather on **TUE** (mandatory).
  General-use circuits (IUG, TUG) only allow outlet points outside if they are in **semi-covered** spaces, with IP44 fittings
  at minimum. Weather-exposed circuits should preferably be independent. **770:2017 (prior to 2026):** general
  circuits allow outlet points in semi-covered spaces (IP44) and exposed to the weather (IP54). Controls in wet locations (float switches for the tank and
  cistern, alarms) are fed with MBTS. Pumps go on an ACU or APM.
- **Why:** the outside gets wet and has more leakage; separating it prevents a fault outside from leaving the house without light and helps the
  selectivity (discrimination) of the RCD (*disyuntor* / *diferencial*).
- **How:** dedicated circuit for outdoors; if the installation is handed over without fittings, the design report says which outlet points are for
  semi-covered (IP44) or weather-exposed locations. The 771 does not set in that clause the IP of the weather-exposed fitting: as a reference, the
  770:2017 calls for IP54. MBTF/MBTS sources with a transformer with separate primary and secondary (never an autotransformer).
  **Apartment booster pump** (common in buildings with low pressure): APM if its nameplate current does not exceed 10 A (the
  circuit, up to 25 A) or its own ACU; C curve MCB (*térmica*) because of the motor's starting current (4 to 7 times rated), PE and
  30 mA RCD; if it sits in the laundry, on the roof terrace or next to the tank, box and fitting with the IP of the location, and the
  motor protection (its own MCB or motor protection circuit breaker, *guardamotor*) per the manufacturer. Pool, large pumps and the like: see
  [special-installations.md](special-installations.md); building pumps: [buildings.md](buildings.md).
- **Verify:** IP of each outdoor fitting; weather-exposed socket outlets on TUE (771); float switches on MBTS; separate outdoor circuit in
  the panel (distribution board, *tablero*); pump nameplate against the circuit.
- **Don't:** in the 771, run an indoor TUG out to the garden with an ordinary socket outlet; control the float switch at 220 V; hang the
  booster pump on a TUG with an extension cord.
- **Source:** AEA 90364-7-771:2006, 771.7.6 note 2, a) (general-use outlet points only in semi-covered spaces, IP44) and b) I and II (IUE and TUE
  "debe ser empleado" (must be used) for weather-exposed locations; independence recommended), 771.8.5 k) and l); 770:2017, 770.6 a) (IP44 semi-covered,
  IP54 weather-exposed), 770.7.1 g) and h). Motor starting current: typical order of magnitude,
  **not verified in a primary source** (the nameplate and the manual govern).

### ELEC-CIR-12: The DPMS is calculated with the conventional powers, per circuit
- **Rule:** DPMS (maximum simultaneous power demand) = sum of the conventional powers of each general and special-use circuit (or the actual one, if higher) ×
  diversity factor of the unit.
- **Why:** at the design stage you don't know what each person will plug in; the conventional values are the statistical floor that the
  standard accepts for sizing cables and protection and for checking the grade.
- **How:** (771, dwelling) IUG without socket outlets = 0.66 × outlet points × 150 VA; IUG with socket outlets = 2200 VA; TUG = 2200 VA; IUE = 0.66 × outlet points ×
  500 VA; TUE = 3300 VA. Factor by grade: 1 / 0.9 / 0.8 / 0.7. In offices and shops lighting goes at 100 %.
  **(770:2017, edition prior to 2026):** IUG without socket outlets = 2/3 × outlet points × 60 VA; factor by minimum number of circuits (2 → 1;
  3 → 0.8; 5 → 0.7; 6 → 0.6). The 770 table says "cantidad mínima de circuitos" (minimum number of circuits): the conservative criterion is to use the
  factor that matches the grade's minimum, not the total number of circuits you fitted. Confirm these values in Ed. 2026.
  Short example (771): 7 IUG outlet points + 1 TUG → 0.66 × 7 × 150 = 693 VA + 2200 VA = 2893 VA × 1 (Minimum) = **2893 VA** ≤ 3.7 kVA.
- **Verify:** the schedule shows outlet points, conventional power, subtotal, factor and DPMS; the calculator gives the same result.
- **Don't:** add up the nameplate watts of everything in the house and call it DPMS; apply 60 VA per outlet point (the 770 value) in an
  apartment calculated with the 771.
- **Source:** AEA 90364-7-771:2006, 771.9.1 (see tables 771.9.I and 771.9.II); 770:2017, 770.8.1 (see tables 770.8.I and 770.8.II).

### ELEC-CIR-13: Total load = DPMS + specific loads
- **Rule:** the total load of the unit is the DPMS plus the demand of the specific circuits (ACU, APM, MBTF, ATE, etc.), each
  with its utilization factor and the group's simultaneity, at the designer's discretion and written in the design report.
- **Why:** the ACs, the pump, the cooktop or the water heater are not in the DPMS; if you don't add them, the main line and the
  requested power fall short.
- **How:** specific load = nameplate power × utilization factor × simultaneity. Conservative criterion for ACs
  in summer, cooktop and water heater: 1. Example: DPMS 2893 VA + AC (ACU) of 1500 VA × 1 = **4393 VA**. Single-phase current:
  I = 4393 ÷ 220 = **20.0 A**.
- **Verify:** each specific circuit appears in the schedule with its power and its justified factor.
- **Don't:** apply the DPMS factor to the ACs; leave out the electric water heater "because it's rarely used".
- **Source:** AEA 90364-7-771:2006, 771.9.2 and 771.9.3.1; 770:2017, 770.8.2 and 770.8.3.1.

### ELEC-CIR-14: From total load to supply: single-phase as far as the utility allows, three-phase recommended from 7 kVA or 32 A
- **Rule:** with the total load you calculate the current. If it exceeds 7 kVA or 32 A, AEA recommends requesting a three-phase supply. The
  value from which three-phase is mandatory is set by each utility.
- **Why:** a 40-45 A single-phase supply requires a heavy service connection (*acometida*) and main line, increases the voltage drop and leaves little margin.
  On three-phase the same load is spread over three phases.
- **How:** single-phase: I = S ÷ 220 V. Balanced three-phase: I = S ÷ (√3 × 380 V) = S ÷ 658 V. Example: 10,148 VA → single-phase
  10,148 ÷ 220 = **46.1 A**; three-phase 10,148 ÷ 658 = **15.4 A per phase** (if balanced). Compare in the same units:
  the schedule gives kVA and the tariff talks about kW (kW = kVA × cos φ; 10,148 VA × 0.9 ≈ 9.1 kW). The **tariff category** (T1, T2...)
  is not the same as the **single-phase limit**: the cutoff between single-phase and three-phase and the maximum current of the single-phase
  service connection are set by the utility in its regulation. Utility data:
  - **Edenor and Edesur:** national regulator ENRE, now merged into the Ente Nacional Regulador del Gas y la Electricidad (national gas and electricity regulator) (ENReGE,
    Decreto 452/2025); ENRE resolutions remain the reference text until the new body replaces them (see
    [regulations-and-permits.md](regulations-and-permits.md)). The T1R residential tariff goes up to 10 kW of demand (above
    that, T2 on three-phase: see [buildings.md](buildings.md)). To connect a single-phase T1R the regulation requires a certificate from the
    municipality or from CABA or, failing that, an installation conformity declaration (DCI) signed by a registered professional, technician
    or installer with the relevant competence; three-phase requires municipal approval or a DCI plus filing of the application.
  - **EDELAP:** the ENRE regulation (2022 text) names it together with Edenor and Edesur, but its website refers to OCEBA (the
    regulatory body of the Province of Buenos Aires): confirm with the utility which connection regulation applies. Its
    T1 service connection regulation (2020) gives single-phase T1 up to 10 kW, with a 6 mm² copper service connection up to 5 kW and 16 mm² from over 5 kW to 10 kW.
  - Other utilities (EPEC, EPE Santa Fe, cooperatives) have their own cutoffs: check feasibility before finalizing the
    design.
  770:2017 limit: incoming device up to 63 A (≈ 13.9 kVA single-phase at 220 V; ≈ 41.5 kVA three-phase at 380 V).
- **Verify:** the design report has the total load, the current, the supply type and the utility's feasibility note.
- **Don't:** request single-phase for 10 kVA without consulting the utility; choose the supply type before doing the
  schedule; read "T1 up to 10 kW" as "single-phase guaranteed up to 10 kW".
- **Source:** AEA 90364-7-771:2006, 771.9.3.3; 770:2017, 770.1 a) and 770.8.3.3; ENRE, Reglamento para la conexión de nuevos
  suministros domiciliarios (regulation for connecting new residential supplies) (Res. ENRE 225/2011, 2022 edition of the text), sec. I (T1R up to 10 kW), II.2 (municipal certificate or, failing
  that, DCI) and III.2; Decreto 452/2025 (BO 2025-07-07) and argentina.gob.ar/enre (merger into ENReGE, consulted 2026-11-15);
  EDELAP, Reglamento de acometidas T1 (T1 service connection regulation) (2020); EDELAP website (link to OCEBA, consulted 2026-11-15).
  **Not verified in a primary source:** EDELAP's current jurisdiction and since when; EDELAP's service connection cross-sections (6 and 16 mm²) in the text
  in force; the single-phase cutoff of EPEC (an EPEC specification covers single-phase up to 5 kW with an overhead service drop) and of EPE
  Santa Fe (a distributed generation document mentions 7 kW single-phase): confirm with each utility.

### ELEC-CIR-15: Size for the calculated load; contracting less is the user's decision
- **Rule:** cables, protection, panel and conduits are sized for the calculated total load. The user may
  contract a lower power, but the installation is not downsized because of that.
- **Why:** contracted power changes with the tariff or with use; embedded conduits do not.
- **How:** in the design report, separate "calculated total load" from "power to request". The power to contract is agreed with the
  utility. Cable sizing: [conductors-and-conduits.md](conductors-and-conduits.md); incoming device:
  [protection.md](protection.md) and [panels.md](panels.md).
- **Verify:** the main line and the incoming protection cover the calculated load, not just the contracted one.
- **Don't:** reduce the cross-section of the main line "because they're going to contract 5 kW".
- **Source:** AEA 90364-7-771:2006, 771.8.1.1 and 771.9.3.2; 770:2017, 770.7.3 and 770.8.3.2.

### ELEC-CIR-16: On three-phase, split the circuits to balance the phases, without mixing phases in a box
- **Rule:** split the single-phase circuits across the phases to leave the system as balanced as possible (771). As a
  reference, the 770:2017 **recommends** that the imbalance between phases not exceed 30 %. What is mandatory is to calculate the line
  with the current of the most loaded phase.
- **Why:** with everything on one phase, three-phase is useless: that phase works like a single-phase supply and the neutral carries excess current.
  Also, between two phases there are **380 V**: if there are socket outlets from different phases in the same box or the same room, a person
  can end up across 380 V, and the risk grows during repairs (someone switches off "the MCB for that room" and the other phase is still
  live).
- **How:** add up per phase and take the largest. In this guide imbalance is measured as (I max − I min) ÷ I max. Example B (below):
  L1 3394 VA (15.4 A), L2 3560 VA (16.2 A), L3 3194 VA (14.5 A) → (16.2 − 14.5) ÷ 16.2 = **10 %**. The line is sized for
  16.2 A. Split by whole circuit and by room or zone: all socket outlets of a room on the same phase; never mix
  phases in the same box; identify the phase of each circuit in the panel and on the single-line diagram. If two phases must share
  a junction box, mark it "380 V". EV chargers and three-phase loads: see
  [special-installations.md](special-installations.md).
- **Verify:** schedule per phase; in the panel, the phase of each circuit marked and matching the schedule; in boxes,
  a single circuit or circuits of the same phase.
- **Don't:** put both ACs and the kitchen TUE on the same phase; feed neighboring socket outlets in the same room from different
  phases.
- **Source:** AEA 90364-7-771:2006, 771.8.5 q) ("se procurará mantener el sistema lo más equilibrado posible", efforts shall be made to keep the system as balanced as possible; the 771 does not set a
  percentage); 770:2017, 770.8.3.1 note 1 (most loaded phase) and 770.8.3.4 ("se recomienda", it is recommended, that the imbalance not exceed
  30 %). The percentage formula is this guide's interpretation: the standard does not define it in the text consulted. Splitting by
  room and not mixing phases in a box: **recommended practice** of this guide, not verified text of the 771.

### ELEC-CIR-17: The factors by number of units are for the building's supply, not for each unit
- **Rule:** the diversity (simultaneity) factors for groups of dwellings, offices and shops are used to size the
  common supply of the building. Each apartment is sized with its full total load.
- **Why:** not all apartments reach their peak at the same time, but each one, alone, can.
- **How:**
  - **Source in force:** AEA 90364-7-772:2019, 772.9.2 (maximum simultaneous power demand of the set of units) and table
    772.9.III (diversity factors for groups of units). Use that table with the copy in hand.
  - **Provisional precedent:** the 771:2006, 771.9.4.2, says that "hasta tanto estén vigentes" (until they are in force) the sections for condominium buildings (*propiedad horizontal*)
    "podrán adoptarse" (may be adopted, optional) these factors: 2 to 4 units: 0.9 (Minimum and Medium grades) or 0.7
    (High and Superior); 5 to 15: 0.8 / 0.6; 15 to 25: 0.6 / 0.5; more than 25: 0.5 / 0.4 (the table repeats 15 in two rows: with 15
    units, the larger value). With the 772 in force, they serve only as a reference.
  - **Illustrative example** with the 771 factors: 4-story building with 8 apartments like Example A (4393 VA,
    Minimum) → 8 × 4393 × 0.8 = **28,115 VA** for the apartments alone, plus the common services calculated separately (772).
    **Not verified in a primary source:** the factors in table 772.9.III may differ from those of the 771; redo the calculation with
    the 772.
  - **Per phase:** 8 single-phase units do not split evenly over 3 phases: they end up 3 / 3 / 2. Phases with 3 apartments:
    3 × 4393 × 0.8 = 10,543 VA → 10,543 ÷ 220 = **47.9 A**; phase with 2: 2 × 4393 × 0.8 = 7029 VA → **31.9 A**. The supply for
    the apartments is sized for about **48 A per phase** (not for the 28,115 ÷ 658 = 42.7 A of a perfect split), and the
    common services are preferably loaded on the lightest phase. With single-phase units the split is never perfect:
    size with the most loaded phase (ELEC-CIR-16). Applying the group factor to each phase subgroup is an
    approximation of this guide (the same one used in [buildings.md](buildings.md), which assumes 7 kVA per unit).
  - Each apartment keeps its single-phase supply with 20 A of load. In hot climates the utility may require a factor of 1
    (EDELAR recommends it up to 15 units). Full development: [buildings.md](buildings.md).
- **Verify:** the building schedule applies the factor only once and to the sum of the units' total loads;
  it cites table 772.9.III and its edition; the per-phase split is done with the actual units.
- **Don't:** use 0.5 to size an apartment's line; divide the building demand by 658 V as if the
  units split evenly; calculate the grade of the units with the area of the building (ELEC-CIR-2).
- **Source:** AEA 90364-7-772:2019, 772.9.2 and table 772.9.III (index of the copy; values not cross-checked); AEA 90364-7-771:2006,
  771.9.4.2 and table 771.9.III (provisional and optional precedent); EDELAR, EC 1.1.13.10 v3 (2023), p. 3-5.
### ELEC-CIR-18: Offices, shops and other uses have their own grades and outlet points (*bocas*)
- **Rule:** an office or shop in a building designed as housing uses the dwelling grades and minimums; if the property was
  designed as an office or shop, it uses its own table: Minimum up to 30 m² (4.5 kVA), Medium up to 75 m² (7.8 kVA), High up to
  150 m² (12.2 kVA), Superior over 150 m².
- **Why:** in offices the load per square meter is higher and all the lighting is used at the same time; that is why lighting
  counts at 100 % in the DPMS (maximum simultaneous power demand).
- **How:** minimum number of circuits same as in dwellings (2 / 3 / 5 / 6). Typical minimum points: general hall 1 lighting outlet
  point (*boca*) and 1 socket outlet point every 9 m² (minimum 2 socket outlets), in High and Superior plus 1 TUE every 18 m of
  perimeter; private office 1 light + 2 socket outlets. Detail: 771.8.3.2.3 (see table 771.8.VI). Before setting lighting outlet
  points you need a lighting design with the minimum levels of Ley 19.587 de Higiene y Seguridad en el Trabajo (occupational
  health and safety law), Decreto 351/79, chapter 12 and annex IV (lighting and color), or whatever the authority having jurisdiction sets.
  Other uses (educational establishments and others): 771.8.4; premises not covered: 771.8.3.6. This guide does not summarize
  those cases: use the actual copy of the standard.
- **Verify:** original intended use of the property in the design report (*memoria*); table applied consistent with that use.
- **Don't:** design a commercial shop with the 770; apply the dwelling table to a school.
- **Source:** AEA 90364-7-771:2006, 771.8.3, 771.8.3.1, 771.8.3.2.1 (see table 771.8.IV), 771.8.3.2.2, 771.8.3.2.3, 771.8.3.6,
  771.8.4 and note to 771.8.3 (refers to Ley 19.587 and its regulatory decrees); table 771.9.I; Decreto 351/79, ch. 12 and
  annex IV.

### ELEC-CIR-19: Leave spare capacity for what gets added later
- **Rule:** provide free space in the panel (distribution board, *tablero*), a spare conduit and a conduit run between the main panel (TP) and
  the sub-panel (TS, *tablero seccional*) of sufficient diameter: R19 (3/4") as a minimum, and the 770:2017 recommends R25 (1"). At the building supply yard
  (*corralón*): semi-heavy steel conduit RS19 / RS25, or the equivalent in rigid PVC or reinforced corrugated conduit (see
  [conductors-and-conduits.md](conductors-and-conduits.md)).
- **Why:** almost every installation adds loads (ACs, electric cooker, EV charger); without spare capacity you end up running
  cables on the surface or overloading circuits.
- **How:** leave 20-30 % of modules free in the sub-panel (common practice; the 770:2017 requires at
  least 20 %, see [panels.md](panels.md)); empty conduits to the AC positions and to the kitchen; building riser (*montante*) with
  room to change the cross-section.
- **Verify:** diameter of the TP-TS conduit; free modules in the panel ([panels.md](panels.md)).
- **Don't:** a 5/8" (RS16) conduit between main panel and sub-panel.
- **Source:** AEA 90364-7-771:2006, 771.8.5 t); 770:2017, 770.7.1 p) and 770.16.4. Commercial designation RS/RL of steel conduits:
  IRAM-IAS U500-2100 (commercial practice; **not verified in a primary source**).

### ELEC-CIR-20: Put it in writing: load schedule (*planilla de cargas*), single-line diagram (*unifilar*) and numbered drawing
- **Rule:** the project includes a load schedule (area, grade, outlet points per circuit, power ratings, factors, DPMS, total
  load, current, supply type), a single-line diagram and a drawing with every outlet point numbered by circuit. It is signed by a
  professional or a qualified electrician (*instalador habilitado*).
- **Why:** the utility (distribution company) asks for the schedule and the diversity (simultaneity) factor used; the inspector
  and whoever comes later need to know what is on each circuit.
- **How:** number the circuits 1, 2, 3... and put the number next to each outlet point; each lighting outlet point with the
  letter of its switch. Run the schedule with `gateway electricidad` and attach the result. In three-phase, the phase of each
  circuit.
- **Verify:** every circuit on the single-line diagram exists in the panel and on the drawing; the schedule total matches the
  calculator.
- **Don't:** hand over an installation without a schedule or a single-line diagram.
- **Source:** AEA 90364-7-771:2006, 771.2 (project with drawings and report); 770:2017, 770.2.1; EDELAR, EC 1.1.13.10 v3 (2023),
  p. 2 (requires a load schedule and diversity factor).

### ELEC-CIR-21: IRAM 2071 socket outlets (*tomas*) of 10 or 20 A, with shutters low down and at the right height
- **Rule:** the fixed installation uses 2P+E socket outlets to **IRAM 2071**: **10 A** on IUG and TUG, **20 A** on TUE (or 16 A
  IEC 60309). Earthed plugs are IRAM 2073 and the 20 A plug does not fit the 10 A socket outlet, on purpose. In dwellings, socket
  outlets less than 0.90 m from the floor have a protective **shutter** against insertion of objects (BA2 users: there may be
  children). Do not install "universal", "biuso" (dual-use) or combined socket outlets that accept plugs of different geometry,
  nor Schuko.
- **Why:** the different geometry prevents plugging a 20 A load into a 10 A socket outlet; the shutter stops a child from
  inserting an object; a universal socket outlet guarantees neither the earth nor the rating.
- **How:** when counting outlet points, state in the schedule which are 10 A and which are 20 A, and that the ones below 0.90 m
  have shutters. Heights: in the 771, low socket outlet at least **0.15 m** above the finished floor and socket outlets over a
  countertop **0.10 m** or more above the countertop; the 770:2017 placed low socket outlets between **0.20 and 0.30 m**. Mixed
  outlet points on IUG: 0.90 m or more (ELEC-CIR-8). Detail on earthing and adapters: [earthing.md](earthing.md) ELEC-PAT-14.
- **Verify:** rating marked on each socket outlet; shutters on the low ones; certification mark; 20 A socket outlets only on TUE.
- **Don't:** put a 20 A socket outlet on a TUG; install universal socket outlets or ones with a built-in adapter; low socket
  outlets without shutters in a dwelling.
- **Source:** AEA 90364-7-771:2006, foreword and 771.8.6.2 (shutter up to 0.9 m; heights above floor and countertop) and
  bibliography (IRAM 2071 and IRAM 2073); 770:2017, 770.6 a) and b) (IRAM 2071 socket outlets of 10 and 20 A) and 770.7.2
  (shutter); prohibition of multi-geometry socket outlets: Disp. DNRT 2/2025, Anexo, item 4.1 a), implementing Res. SIyC 236/2024
  (Anexo II per Res. SIyC 26/2025), according to [earthing.md](earthing.md) ELEC-PAT-14 and
  [iram-standards.md](iram-standards.md) ELEC-IRA-8. **Not verified in a primary source:** the clause of the 770:2017 with the
  0.20-0.30 m heights and whether Ed. 2026 changed them.

### ELEC-CIR-22: For the schedule, the appliance's nameplate governs, not the trade name
- **Rule:** every fixed or large load is entered with its **electrical** current or power from the nameplate. The table below
  is for estimating during a consultation or for spotting an error; for the project, use the nameplate.
- **Why:** the typical errors are taking frigories as watts, taking the microwave's cooking power as its consumption, or calling a
  2000 W heater "small": a 2000 W heater draws 9.1 A for hours from a 10 A socket outlet, and it is the classic case of an
  overheated socket outlet in winter.
- **How:** I = P ÷ 220 V for resistive loads (cos φ ≈ 1); with a motor or electronics, P ÷ (220 × cos φ) or directly the
  nameplate current. Typical values (order of magnitude):

  | Appliance | Typical nameplate power | Current at 220 V | Where it goes |
  |---|---|---|---|
  | Electric kettle | 2000-2200 W | 9.1-10 A | TUG (one at a time) |
  | Microwave (consumption, not cooking power) | 1200 W | 5.5 A | TUG |
  | Air fryer | 1500 W | 6.8 A | TUG |
  | Washing machine with water heating | 2000-2200 W while heating | 9.1-10 A | Laundry TUG or TUE |
  | Heater or fan heater | 2000 W | 9.1 A | at the limit of the 10 A socket outlet: the room's own TUG, TUE or ACU |
  | Electric water heater | 1500 / 2000 W | 6.8 / 9.1 A | ACU recommended (continuous load) or TUE |
  | Electric oven | 2500-3500 W | 11.4-15.9 A | TUE with 20 A socket outlet, or ACU |
  | 4-burner induction cooktop | 7000-7400 W | 31.8-33.6 A | ACU, fixed connection, ~6 mm² and 32 A |
  | Split 2250 / 3000 / 4500 / 6000 fg | ≈ 0.8 / 1.1 / 1.6 / 2.2 kW electrical | ≈ 3.9 / 5.2 / 7.8 / 10.4 A (cos φ 0.95) | ACU or TUE, one per unit |
  | Booster pump 0.5-1 HP | ≈ 0.6-1.3 kW consumed | ≈ 3.5-7 A rated; starting 4-7 times | APM or ACU, C curve |

  **Fixed electric heating** (panels, electric underfloor heating, several fixed fan heaters): its own circuit (ACU or OCE) sized
  by the sum of the nameplates, with diversity 1 in winter. **Inverter vs on-off:** at the same power, the on-off has a high
  starting current (MCB (*térmica*) C curve, see [protection.md](protection.md) ELEC-PRO-2); the inverter starts softly but
  requires a type A RCD (*diferencial*) (ELEC-PRO-9).
- **Verify:** photo or data of the nameplate of each large load in the design report; the current of each one against the
  socket outlet and the circuit.
- **Don't:** write down "aire de 3000" (a "3000" AC) without a unit; leave 2000 W heaters as a permanent load on a TUG with a
  power strip.
- **Source:** I = P ÷ U (direct calculation); 1 kcal/h = 1.163 W; EER 3.2 and cos φ 0.95 as in
  [special-installations.md](special-installations.md) ELEC-ESP-10. **Not verified in a primary source:** the power ratings are
  typical of nameplates and catalogs, not from a standard; each model has its own.

### ELEC-CIR-23: Split the circuits among a few RCDs (*diferenciales*), thinking about what keeps working if one trips
- **Rule:** all final circuits are under a 30 mA RCD (ID). The AEA allows one ID per circuit or grouping several under one,
  without setting a maximum; this guide's criterion: **2 to 3 circuits per ID**, with light and socket outlets of the same room on
  different IDs.
- **Why:** every piece of equipment with electronics leaks a little to earth and the leakages add up: with many circuits on one
  ID, "unexplained" trips appear. And if the light and the socket outlets of a room are on the same ID, a fault in a socket
  outlet leaves the room in the dark.
- **How:** the rated current of the ID must be greater than or equal to the sum of the PIAs below it or to the upstream
  protection ([panels.md](panels.md) ELEC-TAB-10). Type A for circuits with inverter, induction or washing machine
  ([protection.md](protection.md) ELEC-PRO-9). Standing leakage per ID: see ELEC-PRO-11. Example of the split: Example A, step 8.
- **Verify:** on the single-line diagram, which circuits hang from each ID and the sum of their PIAs.
- **Don't:** a single ID for the whole house; put the refrigerator and the kitchen light on the same ID without thinking about it.
- **Source:** AEA 90364-7-770:2017, 770.14.2.3 (30 mA), 770.16.5.4 and note 1 (ID per circuit or grouped, no maximum), according
  to [reviewing-a-panel.md](reviewing-a-panel.md) and [panels.md](panels.md) ELEC-TAB-19. "2 to 3 circuits per ID" and the
  light/socket separation: practical criterion of this guide.

### ELEC-CIR-24: "All-electric" dwelling: cooking, hot water and heating change the grade and the supply
- **Rule:** if the unit has no gas (induction cooktop, electric water heater or heat pump, electric heating), each of those loads
  goes into the schedule with its nameplate power as a specific load, and the total load almost always forces a three-phase
  supply.
- **Why:** an induction cooktop alone (about 7 kW) already exceeds the 7 kVA from which the AEA recommends three-phase; added to
  ACs, water heater and the oven's TUE, a 75 m² apartment (*depto*) exceeds 18 kVA (Example C).
- **How:** circuits: ACU for the cooktop (fixed connection, type A ID), ACU for the water heater, ACU for each AC or fixed heater,
  TUE for the oven. Factor 1 for cooking, hot water and climate control, unless the designer justifies another in writing (some
  cooktops allow their power to be limited by configuration: if used, document it with the manual). Ask for three-phase
  feasibility (*factibilidad*) before closing the project and check the tariff category (above 10 kW it is no longer T1 in the
  Edenor/Edesur area). In a building, one such unit can count as much as two or three gas ones: carry it to the demand of the
  whole building ([buildings.md](buildings.md)).
- **Verify:** schedule with each nameplate load; split by phase; type A ID where required; feasibility note.
- **Don't:** design "all-electric" with a 40 A single-phase supply; put the induction cooktop on the kitchen TUE.
- **Source:** AEA 90364-7-771:2006, 771.8.5 b), 771.9.2 and 771.9.3.3; category T1R up to 10 kW: Reglamento ENRE de conexión
  (ENRE connection regulations) (2022 text). Power ratings: typical nameplate values (ELEC-CIR-22); the method is that of the
  previous rules.

### ELEC-CIR-25: Before adding an AC or an electric cooker to an existing installation, check the whole chain
- **Rule:** a large new load is added with its own circuit from the panel, and only after checking that the sub-main (feeder)
  (and the main line), its protection, the panel and the contracted power can take the new total load.
- **Why:** the AC "that works fine" on the TUG or the electric cooker on an old 4 mm² line are the cases of an overheated cable
  and a main MCB that trips; the fault does not appear on the new circuit but upstream.
- **How:**
  1. Present total load (schedule or, if there is none, an as-found survey (*relevamiento*) of circuits) + new load from the nameplate.
  2. Sub-main: actual cross-section and Iz, and the MCB that protects it in the main panel: it must meet Ib ≤ In ≤ Iz with the
     new load (`gateway electricidad` current/cross-section/coordination).
  3. Panel: room for a new two-pole PIA and an ID (type A if inverter or induction) with enough capacity.
  4. Contracted power and supply type (bill): if it is not enough, application to the utility.
  5. Voltage drop of the new circuit ([conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-9).
  **Example (assumed values):** apartment like Example A (4393 VA, 20.0 A) with a 4 mm² sub-main (Iz 28 A) protected at 25 A. Add
  a 3000 fg split (≈ 1150 VA): 4393 + 1150 = 5543 VA → 25.2 A > 25 A: **at the limit, it does not fit without review** (either it
  is accepted with a diversity justification, or the line is changed). Add a 7000 W induction cooktop: 4393 + 7000 = 11,393 VA →
  51.8 A: **it does not fit**; a new line is needed (16 mm² in conduit, Iz 66 A, with its protection), review the meter and the
  power, and very probably move to three-phase, or choose a cooktop that limits its power.
- **Verify:** that the check is written down; that the new circuit is not branched off an existing TUG.
- **Don't:** "try" the new load and see if it trips; upsize the line's MCB so it holds; branch the AC off a TUG box.
- **Source:** method of AEA 90364-7-771:2006, 771.9 (total load) and 771.19 (Ib ≤ In ≤ Iz); Iz from table 770.12.I (2017)
  according to [conductors-and-conduits.md](conductors-and-conduits.md). Steps: practical criterion of this guide.

## Example A: single-phase apartment of about 60 m² in a 4-story building (771)
Apartment in a 4-story building: 55 m² covered + roofed balcony of 6 m² (3 m long). Living-dining room 22 m², separate kitchen
7 m², bedroom 12 m², bathroom 4 m², hallway 3 m. Single-phase supply from the meter on the ground floor.

1. **Area and grade:** 55 + 0.5 × 6 = 58 m² → Minimum (up to 60 m²) (ELEC-CIR-2).
2. **Minimum points (Minimum):**

   | Room | IUG | TUG |
   |---|---|---|
   | Living-dining room 22 m² | 22/18 → 2 | 22/6 = 3.7 → 4 |
   | Bedroom 12 m² | 1 | 3 |
   | Kitchen | 1 | 3 outlet points (+ 2 socket outlets for refrigerator and microwave in those boxes) |
   | Bathroom | 1 | 1 (outside the zones) |
   | Hallway 3 m | 1 | — |
   | Balcony 3 m (IP44 fitting, semi-covered) | 1 | — |
   | **Total** | **7** | **11** |

3. **Circuits:** 1 IUG (7 outlet points) + 1 TUG (11 outlet points): within the 15 of each. Plus 1 ACU for an AC in the living
   room.
4. **DPMS:** IUG 0.66 × 7 × 150 = 693 VA; TUG 2200 VA → 2893 VA × 1 = **2893 VA** ≤ 3.7 kVA: the Minimum grade is confirmed.
5. **Total load:** 2893 + 1500 VA AC (assumed nameplate value) = **4393 VA** → I = 4393 ÷ 220 = **20.0 A** → single-phase.
6. **Comparison (770:2017, edition prior to 2026):** the same unit as a single-family house would give IUG 2/3 × 7 × 60 = 280 VA +
   TUG 2200 VA = 2480 VA × 1, plus the AC = 3980 VA (18.1 A). Do not use in an apartment (ELEC-CIR-1).
7. **Recommended variant, with the kitchen's own TUG (ELEC-CIR-7):** IUG 693 VA + 2 TUG 4400 VA = 5093 VA × 1 = 5093 VA > 3.7 kVA
   → **moves to Medium** (ELEC-CIR-3). With the Medium minimums the kitchen gets 2 lighting outlet points and the 3 m hallway one
   socket outlet: IUG 8, TUG 12 (TUG1: living room, bedroom, bathroom and hallway, 9 outlet points; TUG2: kitchen, 3 outlet
   points). DPMS: 0.66 × 8 × 150 = 792 VA + 4400 VA = 5192 VA × 0.9 = **4673 VA** ≤ 7 kVA → Medium is confirmed (3 circuits:
   complies). Total load: 4673 + 1500 = **6173 VA** → 6173 ÷ 220 = **28.1 A**: single-phase, below 7 kVA and 32 A, but with little
   margin.
8. **Resulting sub-panel (variant from step 7)**, illustrative; check every number with `gateway electricidad` and with
   [panels.md](panels.md) ELEC-TAB-18 and ELEC-TAB-19:
   - In the main panel (meter cabinet, ground floor): PIA 2×32 A C curve protecting the sub-main; sub-main 2 × 6 mm² + PE in
     conduit (Iz 36 A): Ib 28.1 A ≤ In 32 A ≤ Iz 36 A. Voltage drop according to the length of the riser.
   - Sub-panel in the apartment: incoming switch-disconnector 2×40 A.
   - **ID1** 2×40 A, 30 mA: PIA 2×10 A C → IUG1 (1.5 mm²); PIA 2×16 A C → TUG2 kitchen (2.5 mm²). Sum 26 A ≤ 40 A.
   - **ID2** 2×40 A, 30 mA (type A if the AC is inverter): PIA 2×16 A C → TUG1 (2.5 mm²); PIA 2×16 A C → ACU1 AC (2.5 mm²;
     1500 VA → 6.8 A). Sum 32 A ≤ 40 A.
   - Modules: incoming 2 + 2 ID × 2 + 4 PIA × 2 = 14 occupied; with 20 % spare, 14 ≤ 0.8 × C → C ≥ 17.5 → enclosure of
     **18 modules or more** (24 if you plan to add another AC).
   - To compare with a real panel (for example, the photo of one from a job site), use [reviewing-a-panel.md](reviewing-a-panel.md).
## Example B: apartment of about 100 m² (771)
92 m² covered + roofed balcony of 12 m² (6 m long). Living-dining room 30 m², kitchen 10 m² with a 3 kW electric oven (13.6 A),
bedrooms of 14, 11 and 9 m², bathroom, guest toilet, entrance hall 5 m², hallway 6 m, laundry. Two air conditioners: living room
(1800 VA) and main bedroom (1000 VA).

1. **Area:** 92 + 0.5 × 12 = 98 m² → the grade is preset as Medium.
2. **Minimum points (Medium):** IUG: living room 2, bedrooms 3, kitchen 2, bathroom 1, guest toilet 1, entrance hall 1, hallway
   2, laundry 1, balcony 2 = **15**. TUG: living room 5, bedrooms 3 + 3 + 2, kitchen 3, bathroom 1, guest toilet 1, entrance hall
   1, hallway 2, laundry 2 = **23**.
3. **Proposed circuits:** IUG1 (8 outlet points (*bocas*)), IUG2 (7), TUG1 (kitchen, laundry, bathrooms, hallway: 9), TUG2
   (living room, bedrooms, entrance hall: 14), TUE1 (oven and the kitchen's TUE outlet points), ACU1 (living room AC), ACU2
   (bedroom AC). A single IUG of 15 outlet points would comply, but leaves no margin. The 13.6 A oven fits a 20 A socket outlet
   on the TUE (ELEC-CIR-9).
4. **DPMS with Medium:** IUG 0.66 × 15 × 150 = 1485 VA; TUG 2 × 2200 = 4400 VA; TUE 3300 VA → 9185 VA × 0.9 = **8267 VA** > 7 kVA
   → **it fails the Medium check** (ELEC-CIR-3).
5. **Iterate with High:** 9185 × 0.8 = **7348 VA** ≤ 11 kVA → **High** grade. The DPMS comes out lower than with Medium because
   the factor drops: that is the method of 771.8.1.5 / 771.9.1, not an error (ELEC-CIR-3). What changes is that the High
   minimums must be met: 5 circuits (2 IUG + 2 TUG + 1 TUE, already there); a TUE outlet point in the kitchen and in the laundry
   (both on TUE1, which allows 12); 3 socket outlets for fixed appliances in the kitchen. The living room (30 m²) and the bedrooms
   (≤ 36 m²) add no TUE. For the line, use 7348 VA (or more, if the actual loads are higher). Practice: if the washing machine
   heats water (≈ 10 A) on the same TUE as the oven (13.6 A), together they exceed 20 A; better to move the laundry to another
   circuit.
6. **Total load:** 7348 + 1800 + 1000 = **10,148 VA** → single-phase 10,148 ÷ 220 = **46.1 A**: exceeds 7 kVA and 32 A. In kW:
   10,148 × 0.9 ≈ 9.1 kW, within category T1 (up to 10 kW) in the Edenor/Edesur area, but that is the tariff, not a permission for
   a 46 A single-phase supply (heavy service connection (*acometida*), large meter, high voltage drop). **Recommendation: ask for three-phase**
   (ELEC-CIR-14) and confirm feasibility (*factibilidad*).
7. **Three-phase split** (factor 0.8 applied to each general and special circuit):
   - L1: IUG1 (0.66 × 8 × 150 × 0.8 = 634 VA) + TUG1 (1760 VA) + ACU2 (1000 VA) = 3394 VA → 15.4 A
   - L2: TUG2 (1760 VA) + ACU1 (1800 VA) = 3560 VA → 16.2 A
   - L3: TUE1 (2640 VA) + IUG2 (0.66 × 7 × 150 × 0.8 = 554 VA) = 3194 VA → 14.5 A
   - Imbalance (16.2 − 14.5) ÷ 16.2 = 10 %, well below the 30 % recommended by the 770:2017. Line sized for 16.2 A
     (ELEC-CIR-16). Each room stays on a single phase.
8. **Variant without electric oven** (gas cooking, no TUE): (1485 + 4400) × 0.9 = 5297 VA ≤ 7 kVA → stays Medium; with the two
   ACs, 5297 + 2800 = 8097 VA → 36.8 A: it still exceeds 32 A. With two ACs, a 100 m² apartment almost always ends up asking for
   three-phase or a large single-phase supply accepted by the utility (distribution company).

## Example C: "all-electric" apartment of 75 m² (771)
75 m² covered, no gas: 7000 W induction cooktop, 3 kW electric oven, 2000 W electric water heater, two heat-and-cool splits of
3000 fg (≈ 1150 VA each, ELEC-CIR-22). With the outlet points counted per ELEC-CIR-7 the result is 12 lighting outlet points
(assumed).

1. **Area:** 75 m² → the grade is preset as Medium.
2. **General circuits:** IUG (12 outlet points), TUG1, TUG2, TUE1 (oven). DPMS with Medium: 0.66 × 12 × 150 = 1188 VA + 4400 VA +
   3300 VA = 8888 VA × 0.9 = **7999 VA** > 7 kVA → it fails the Medium check.
3. **High:** 8888 × 0.8 = **7110 VA** ≤ 11 kVA → High. You must reach 2 IUG + 2 TUG + 1 TUE: split the IUG into IUG1 and IUG2 of
   6 outlet points each (the conventional power does not change, it goes per outlet point) and add the TUE outlet points and the
   kitchen socket outlets required for High.
4. **Specific loads** (factor 1): ACU1 cooktop 7000 VA; ACU2 water heater 2000 VA; ACU3 and ACU4 splits 1150 VA each.
5. **Total load:** 7110 + 7000 + 2000 + 2 × 1150 = **18,410 VA** → single-phase 18,410 ÷ 220 = **83.7 A**: not viable →
   **three-phase**. It also exceeds category T1 (≈ 17 kW with cos φ 0.95): check category and power with the utility.
6. **Split by phase:**
   - L1: ACU1 cooktop 7000 VA → **31.8 A**
   - L2: TUE1 (3300 × 0.8 = 2640 VA) + ACU2 2000 VA + ACU3 1150 VA = 5790 VA → 26.3 A
   - L3: IUG1 + IUG2 (1188 × 0.8 = 950 VA) + TUG1 + TUG2 (2 × 1760 = 3520 VA) + ACU4 1150 VA = 5620 VA → 25.5 A
   - Sum 7000 + 5790 + 5620 = 18,410 VA. Imbalance (31.8 − 25.5) ÷ 31.8 = 20 %. Line for **31.8 A per phase** (a perfect split
     would give 18,410 ÷ 658 = 28.0 A).
7. **Building:** 8 such units, with the 771's factor 0.6 for High (precedent; use table 772.9.III),
   8 × 18,410 × 0.6 = **88,368 VA** for the apartments alone: this enters the discussion of a transformer substation
   ([buildings.md](buildings.md)).

## Typical design errors
| Error | What happens | Rule |
|---|---|---|
| 25 or 32 A MCB (*térmica*) on 2.5 mm² cable ("the table says max. protection 32 A") | Cable without overload protection: fire risk | ELEC-CIR-5 |
| 1.5 mm² IUG with a 16 A MCB | In greater than Iz (≈ 15 A) | ELEC-CIR-5 |
| Everything on one circuit, or "one for lights and one for sockets" in a 3-room unit | One fault leaves the unit with nothing; MCB that trips; does not meet the grade minimum | ELEC-CIR-4, ELEC-CIR-5 |
| Air conditioner plugged into a TUG | Circuit overloaded in summer; overheated 10 A plugs | ELEC-CIR-9, ELEC-CIR-10 |
| "Aire de 3000" (a "3000" AC) entered as 3000 W | Inflated schedule (or, the other way round, an AC without a circuit) | ELEC-CIR-9, ELEC-CIR-22 |
| Kitchen without a special circuit with electric cooktop or oven; induction cooktop on a TUE | The circuit can't cope; 20 A socket outlets appear on 2.5 mm² circuits with an oversized MCB | ELEC-CIR-9, ELEC-CIR-10 |
| Kettle, microwave and air fryer on the only TUG | 22 A on a 16-20 A circuit: it trips or melts plugs | ELEC-CIR-7 |
| Grade taken from the building's area | Oversized studio apartments, or the other way round | ELEC-CIR-2 |
| Not verifying the DPMS in the 771 | The grade comes out too low and circuits and outlet points are missing | ELEC-CIR-3 |
| Mixing 770 and 771 (60 VA per outlet point in an apartment) | The DPMS comes out lower than the applicable standard requires | ELEC-CIR-1, ELEC-CIR-12 |
| Low socket outlets hung off the lighting circuit | Overloaded 1.5 mm² IUG | ELEC-CIR-8 |
| More than 15 outlet points on a TUG or an IUG | Circuit out of standard; the statistical DPMS is no longer valid | ELEC-CIR-5, ELEC-CIR-6 |
| ACs, cooktop and water heater left out of the schedule | Main line and requested power too small | ELEC-CIR-13, ELEC-CIR-24 |
| Building factor applied to each apartment | Unit line undersized | ELEC-CIR-17 |
| Building demand divided by 658 V with single-phase units | The phase with the most units falls short | ELEC-CIR-17 |
| Three-phase with everything on one phase, or phases mixed in one room | Overloaded phase, loaded neutral; 380 V between neighboring socket outlets | ELEC-CIR-16 |
| Outdoor circuit hung off an indoor TUG, float switch at 220 V | Leakage and trips; risk in a wet location | ELEC-CIR-11 |
| Universal socket outlets or no shutters below 0.90 m | No guarantee of earth or rating; risk for children | ELEC-CIR-21 |
| New load "tried out" without checking the line | Overheated sub-main (feeder), main MCB that trips | ELEC-CIR-25 |

## What this guide does not replace
The project, the calculation report and the signature are done by a professional or qualified electrician (*instalador
habilitado*) according to the jurisdiction, with the AEA text in force in hand (the 770 has Ed. 2026; the factors for groups of
units are in the 772.9.III). The utility decides the supply type, the power it accepts and what it requires to connect; the
municipality or provincial authority decides which regulations it requires and how approval is granted. This guide summarizes
criteria for understanding and reviewing a design; it is not the standard and does not replace it. See
[regulations-and-permits.md](regulations-and-permits.md).
